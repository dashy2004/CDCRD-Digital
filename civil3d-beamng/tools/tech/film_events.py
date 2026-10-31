"""Stage illustrative road incidents through BeamNGpy and an owned OBS session.

The external JSON config owns all local paths and scene parameters. No vendor
assets are redistributed. These staged examples do not reconstruct a real crash.
"""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import math
from pathlib import Path
import time

import numpy as np


class RoadAxis:
    def __init__(self, snapshot, origin):
        self.points = np.asarray(snapshot['alignment']['nodes_abs_m'], dtype=float)[:, :3]
        self.stations = np.asarray(snapshot['alignment']['station_m'], dtype=float)
        self.origin = np.asarray(origin, dtype=float)
        if (len(self.points) < 2 or self.points.shape != (len(self.stations), 3)
                or self.origin.shape != (3,) or not np.isfinite(self.origin).all()
                or not np.isfinite(self.points).all() or not np.isfinite(self.stations).all()
                or not np.all(np.diff(self.stations) > 0)
                or (np.linalg.norm(np.diff(self.points[:, :2],axis=0),axis=1) < 1e-9).any()):
            raise ValueError('Finite axis with strictly increasing stations required')

    def point(self, station, offset=1.7, lift=0):
        if not self.stations[0] <= station <= self.stations[-1]:
            raise ValueError('Station outside source alignment')
        i = int(np.clip(np.searchsorted(self.stations, station)-1, 0, len(self.stations)-2))
        a, z = self.points[i:i+2]
        d = z[:2]-a[:2]
        length = np.linalg.norm(d)
        if length <= 0:
            raise ValueError('Degenerate axis segment')
        direction = d/length
        p = a+(z-a)*(station-self.stations[i])/(self.stations[i+1]-self.stations[i])
        p[:2] += offset*np.array([direction[1], -direction[0]])
        p[2] += lift
        # BeamNG scenario rotation convention: zero faces -Y, positive yaw
        # turns the vehicle toward -X. Confirm against live state before motion.
        yaw = math.atan2(-direction[0], -direction[1])
        return tuple(p-self.origin), (0, 0, math.sin(yaw/2), math.cos(yaw/2))

    def station(self, local_position):
        xy = np.asarray(local_position)[:2]+self.origin[:2]
        a = self.points[:-1, :2]
        d = np.diff(self.points[:, :2], axis=0)
        u = np.clip(np.sum((xy-a)*d, axis=1)/np.sum(d*d, axis=1), 0, 1)
        distances = np.linalg.norm(xy-(a+u[:, None]*d), axis=1)
        i = int(np.argmin(distances))
        return float(self.stations[i]+u[i]*(self.stations[i+1]-self.stations[i]))

    def script(self, start, end, speed, offset=1.7, offsets=None):
        if speed <= 0 or start == end:
            raise ValueError('Positive speed and distinct stations required')
        result = []
        for s in np.linspace(start, end, max(3, int(abs(end-start)/2)+1)):
            lateral = float(np.interp(s, *zip(*offsets))) if offsets else offset
            p, _ = self.point(s, lateral)
            result.append(dict(x=p[0], y=p[1], z=p[2], t=float(abs(s-start)/speed)))
        return result


def vehicle_motion(axis, item):
    """Resolve an alignment route or a native CAD-coordinate crossing route.

    Explicit paths use metres in the same absolute frame as the CAD snapshot.
    Speed is a target for the simulator's AI, not a measured accident speed.
    """
    if 'path_abs_m' not in item:
        pos, rot = axis.point(item['start'], item.get('offset', 1.7), item.get('lift', .55))
        end = item.get('end', 160)
        if end < item['start']:
            rot = (0, 0, rot[3], -rot[2])
        script = axis.script(item['start'], end, item['speed'], item.get('offset', 1.7),
                             item.get('offsets')) if item.get('speed', 0) > 0 else None
        return pos, rot, script
    points = np.asarray(item['path_abs_m'], dtype=float)
    speed = float(item['speed'])
    lift = float(item.get('lift', .55))
    if (points.ndim != 2 or points.shape[1] != 3 or len(points) < 3
            or not np.isfinite(points).all() or not math.isfinite(speed) or speed <= 0
            or not math.isfinite(lift)):
        raise ValueError('Crossing path requires finite XYZ points, lift and positive speed')
    delta = np.diff(points, axis=0)
    lengths = np.linalg.norm(delta, axis=1)
    if (np.linalg.norm(delta[:, :2], axis=1) < 1e-6).any():
        raise ValueError('Crossing path has a zero horizontal segment')
    local = points - axis.origin
    local[:, 2] += lift
    yaw = math.atan2(-delta[0, 0], -delta[0, 1])
    rot = (0, 0, math.sin(yaw / 2), math.cos(yaw / 2))
    times = np.concatenate(([0.], np.cumsum(lengths) / speed))
    script = [dict(x=float(p[0]), y=float(p[1]), z=float(p[2]), t=float(t))
              for p, t in zip(local, times)]
    return tuple(local[0]), rot, script


def run(config, event, camera, label, record, vr=False, ready_file=None, pov_vehicle=None):
    from beamngpy import BeamNGpy, Scenario, Vehicle
    from beamngpy.sensors import AdvancedIMU, Damage, Electrics
    from capturas_obs import CaptureSession
    if ready_file and ready_file.exists():
        raise FileExistsError('Readiness file must not exist before preparing the take')
    output = Path(config['output'])
    output.mkdir(parents=True, exist_ok=True)
    receipt_path = output/(label+'.json')
    if receipt_path.exists():
        raise FileExistsError(receipt_path)
    source = json.loads(Path(config['snapshot']).read_text())
    manifest = json.loads(Path(config['manifest']).read_text())
    axis = RoadAxis(source, manifest['origin_abs_m'])
    spec = config['events'][event]
    motions = {item['id']: vehicle_motion(axis, item) for item in spec['vehicles']}
    if len(motions) != len(spec['vehicles']):
        raise ValueError('Vehicle IDs must be unique')
    b = BeamNGpy('127.0.0.1', config['port'], quit_on_close=False, socket_timeout=120)
    c = None
    cars = {}
    imus, imu_readings = {}, {}
    background = {item['id'] for item in spec['vehicles'] if item.get('background', False)}
    imu_settings = config.get('imu')
    rows, events = [], []
    try:
        b.open(launch=False)
        if Path(b.system.get_environment_paths()['user']).resolve() != Path(config['user']).resolve():
            raise RuntimeError('Unexpected BeamNG user folder')
        active = b.control.queue_lua_command('return getCurrentLevelIdentifier()', response=True)
        if active not in config['allowed_levels']:
            raise RuntimeError('Unowned active level: '+str(active))
        b.control.queue_lua_command('if render_openxr then render_openxr.setStateUI("disabled") end', response=True)
        b.control.return_to_main_menu()
        scenario = Scenario(spec.get('level',manifest['level_id']), 'cdx_incident_'+label,
                            description='Illustrative road-risk scene, not a real-crash reconstruction',
                            restrict_actions=False)
        for item in spec['vehicles']:
            v = Vehicle(item['id'], model=item['model'], part_config=item.get('config'),
                        color=item.get('color', 'Blue'))
            v.sensors.attach('damage', Damage())
            v.sensors.attach('electrics', Electrics())
            pos, rot, _ = motions[item['id']]
            scenario.add_vehicle(v, pos=pos, rot_quat=rot)
            cars[v.vid] = v
        scenario.make(b)
        b.scenario.load(scenario, precompile_shaders=False)
        b.scenario.start()
        b.env.set_tod(tod=0.9, play=False)
        b.control.queue_lua_command('local s=scenetree.findObject("sunsky"); '
            'if s then s.flareScale=0; s:postApply() end; '
            'local p=scenetree.findObject("PostEffectBloomObject"); if p then p:disable() end',response=True)
        if config.get('illustrative_daylight', False):
            b.env.set_tod(tod=0, play=False)
            b.control.queue_lua_command('local s=scenetree.findObject("sunsky"); '
                'if s then s.castShadows=false; s.azimuth=180; s.elevation=55; '
                's.brightness=3; s.exposure=2; s:setField("ambientScale",0,"2 2 2 1"); '
                's:postApply() end; local c=scenetree.findObject("CloudLayer_1"); '
                'if c then c:setHidden(true) end', response=True)
        lead = cars[spec['vehicles'][0]['id']]
        for v in cars.values():
            if not v.is_connected():
                v.connect(b)
            v.set_shift_mode('realistic_automatic')
            if v.vid in background:
                v.control(throttle=0, brake=1, parkingbrake=1)
            script = motions[v.vid][2]
            if script:
                v.sensors.poll()
                direction = np.array([script[1]['x']-script[0]['x'],
                                      script[1]['y']-script[0]['y']])
                direction /= np.linalg.norm(direction)
                actual = np.asarray(v.state['dir'])[:2]
                if float(np.dot(actual, direction)) < .9:
                    raise RuntimeError('Spawn heading differs from route: '+v.vid)
        pov = cars[pov_vehicle] if pov_vehicle else lead
        b.vehicles.switch(pov)
        b.control.queue_lua_command('ui_visibility.set(false)', response=True)
        if camera == 'driver':
            b.camera.set_player_mode(pov,'driver',{})
        elif camera == 'orbit':
            b.camera.set_player_mode(lead,'orbit',{'distance':8})
        else:
            position, _ = axis.point(*spec.get('camera_pos',[108,13,6]))
            target, _ = axis.point(*spec.get('camera_target',[107,1.7,1]))
            b.camera.set_free(position,tuple(np.array(target)-position))
        b.control.pause()
        people = spec.get('visual_people')
        if people:
            payload = json.dumps(json.dumps(people, allow_nan=False))
            b.control.queue_lua_command('extensions.load("cdcrdVisualPeople"); '
                'cdcrdVisualPeople.setup(jsonDecode('+payload+'))', response=True)
        if imu_settings:
            for name, v in cars.items():
                if name in background:
                    continue
                settings = dict(imu_settings.get('defaults', {}))
                settings.update(imu_settings.get('vehicles', {}).get(name, {}))
                imus[name] = AdvancedIMU('cdx_imu_' + name, b, v, **settings)
                imu_readings[name] = []
        if vr:
            b.control.queue_lua_command('settings.setValue("fpsLimitEnabled",false); '
                'settings.setValue("fpsLimitBackgroundEnabled",false); extensions.load("render_openxr"); '
                'render_openxr.setStateUI("enabled")', response=True)
        if record:
            c = CaptureSession(config['obs_config'],config['obs_directory'],config['obs_name'],application='BeamNG')
            c.guard();c.idle()
            if vr:
                c.scene = c.name + '-VR'
                items = c.call('GetSceneItemList', sceneName=c.scene)['sceneItems']
                match = [i for i in items if i['sourceName'] == c.source]
                if len(match) != 1:
                    raise RuntimeError('Expected one owned capture source in VR scene')
                c.state['item_id'] = match[0]['sceneItemId']
            c.target('BeamNG.tech - 0.39.4.0.20999',executable='BeamNG.tech.x64.exe')
            if config.get('game_audio', False):
                c.call('SetInputSettings', inputName=c.source, overlay=True,
                       inputSettings={'capture_audio': True})
                c.call('SetInputMute', inputName=c.source, inputMuted=False)
            c.call('SetSceneItemTransform', sceneName=c.scene,sceneItemId=c.state['item_id'],
                   sceneItemTransform={'boundsType':'OBS_BOUNDS_SCALE_OUTER','cropToBounds':True,
                                       'cropTop':8,'cropLeft':400 if vr else 0,'cropRight':400 if vr else 0})
        print('SCENE_READY '+label,flush=True)
        if ready_file:
            deadline = time.monotonic() + 900
            while not ready_file.exists():
                if time.monotonic() > deadline:
                    raise TimeoutError('No participant readiness received; scene remains paused')
                time.sleep(.5)
        if vr:
            state = json.loads(b.control.queue_lua_command('return jsonEncode(render_openxr.state)',response=True))
            print('VR_STATE '+json.dumps(state),flush=True)
            if not state.get('sessionRunning'):
                raise RuntimeError('VR session is not running; scene remains paused')
            b.control.queue_lua_command('render_openxr.center()',response=True)
        with c.recording(label) if c else nullcontext():
            if ready_file:
                print('STARTING_IN_3_SECONDS',flush=True)
                time.sleep(3)
            start = time.monotonic()
            for item in spec['vehicles']:
                script = motions[item['id']][2]
                if script:
                    cars[item['id']].ai.set_script(script, cling=True)
            if people:
                b.control.queue_lua_command('cdcrdVisualPeople.start()', response=True)
            b.control.resume()
            triggered = False
            first_sim_time = None
            damage_started = None
            while time.monotonic()-start < spec.get('max_seconds',24):
                row = {'wall':round(time.monotonic()-start,3),'vehicles':{}}
                for name,v in cars.items():
                    v.sensors.poll()
                    state = dict(v.state)
                    if first_sim_time is None:first_sim_time=state['time']
                    e = v.sensors['electrics']
                    row['vehicles'][name] = {'pos':state['pos'],'vel':state['vel'],
                        'up':state['up'],'dir':state['dir'],'sim_time':state['time']-first_sim_time,
                        'station':axis.station(state['pos']),
                        'speed':float(np.linalg.norm(state['vel'])),
                        'damage':float(v.sensors['damage'].get('damage',0)),
                        'brake':e.get('brake',0),'gear':e.get('gear',None)}
                    if name in imus:
                        batch = imus[name].poll()
                        if not isinstance(batch, list):
                            raise TypeError('Expected a bulk IMU list, not a latest-only sample')
                        imu_readings[name].extend(batch)
                current = row['vehicles'][lead.vid]
                if not triggered and current['station']>=spec.get('brake_station',math.inf):
                    lead.queue_lua_command('ai.stopFollowing(true,false);ai.setMode("disabled")',response=True)
                    lead.set_shift_mode('realistic_automatic')
                    lead.control(throttle=0,brake=1,parkingbrake=0)
                    triggered=True
                    events.append({'event':'brake','wall':row['wall'],'station':current['station'],
                                   'speed':current['speed']})
                    print('BRAKE '+json.dumps(events[-1]),flush=True)
                if triggered:
                    lead.control(throttle=0,brake=spec.get('brake_force',1),parkingbrake=0)
                if people:
                    if triggered and current['speed'] < .2 and people.get('wait_for_stop'):
                        b.control.queue_lua_command('cdcrdVisualPeople.beginCrossing()', response=True)
                    row['visual_people'] = json.loads(b.control.queue_lua_command(
                        'return jsonEncode(cdcrdVisualPeople.readback())', response=True))
                if damage_started is None and any(v['damage']>50 for name,v in row['vehicles'].items()
                                                  if name not in background):
                    damage_started=row['wall'];events.append({'event':'damage','wall':row['wall']})
                    if spec.get('stop_after_damage'):
                        for v in cars.values():
                            v.queue_lua_command('ai.stopFollowing(true,false);ai.setMode("disabled")',response=True)
                            v.set_shift_mode('realistic_automatic')
                if damage_started is not None and spec.get('stop_after_damage'):
                    for v in cars.values():
                        v.control(throttle=0,brake=1,parkingbrake=0)
                rows.append(row)
                if damage_started is not None and row['wall']-damage_started>=spec.get('hold_after_damage',5):break
                time.sleep(.12)
            b.control.pause()
            for name, sensor in imus.items():
                # Let the final physics buffer reach GE Lua after pausing.
                time.sleep(.1)
                imu_readings[name].extend(sensor.poll())
            if c:
                c.snapshot(label+'_end')
            time.sleep(.4)
        result={'schema':'cdcrd.incident-take/1','event':event,'camera':camera,'illustrative':True,
                'vr':vr,'pov_vehicle':pov.vid,'participant_ready':bool(ready_file and vr),
                'inspection_gate':bool(ready_file),
                'illustrative_daylight':bool(config.get('illustrative_daylight', False)),
                'parameters':spec,'events':events,'telemetry':rows,
                'simulation_time_origin':first_sim_time,
                'imu_settings':imu_settings,'imu_readings':imu_readings,
                'video':c.state['recordings'][-1] if c else None}
        receipt_path.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({'receipt':str(receipt_path),'events':events,'last':rows[-1] if rows else None}),flush=True)
    finally:
        if b.connection:
            try:
                b.control.pause()
                for v in cars.values():
                    if v.is_connected():v.queue_lua_command('ai.stopFollowing(true,true);ai.setMode("disabled")',response=True)
                for sensor in imus.values():
                    sensor.remove()
            finally:b.disconnect()
        if c:c.close()


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('config',type=Path)
    p.add_argument('--event',required=True)
    p.add_argument('--camera',choices=['exterior','driver','orbit'],default='exterior')
    p.add_argument('--label',required=True)
    p.add_argument('--record',action='store_true')
    p.add_argument('--vr', action='store_true')
    p.add_argument('--ready-file',type=Path,help='Wait paused for a new readiness file before recording')
    p.add_argument('--pov-vehicle',help='Configured vehicle id to use as the driver camera')
    a=p.parse_args()
    if not a.label.replace('_','').isalnum() or not a.label.startswith('CDX_'):
        p.error('Use a new CDX_ prefixed alphanumeric label')
    run(json.loads(a.config.read_text(encoding='utf-8-sig')),a.event,a.camera,a.label,a.record,
        a.vr,a.ready_file,a.pov_vehicle)
