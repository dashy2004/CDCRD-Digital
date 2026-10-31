"""Export traceable AdvancedIMU measurements from an incident receipt.

BeamNG.tech 0.39: accRaw uses dirX/dirY/dirZ, while angVel/angAccel
are world vectors. The supplied mounts use forward/up/right, respectively.
This is a vehicle-body measurement, not occupant acceleration or crash severity.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

G=9.80665


def validate_samples(samples, origin):
    if len(samples)<10:
        raise ValueError('At least ten IMU samples required')
    times=np.array([s['time'] for s in samples],dtype=float)
    acceleration=np.array([s['accRaw'] for s in samples],dtype=float)
    basis=np.array([[s[k] for k in ('dirX','dirY','dirZ')] for s in samples],dtype=float)
    if acceleration.shape!=(len(samples),3) or basis.shape!=(len(samples),3,3):
        raise ValueError('Malformed vectors')
    if not all(np.isfinite(x).all() for x in (times,acceleration,basis)) or not np.isfinite(origin):
        raise ValueError('Non-finite sensor data')
    dt=np.diff(times)
    if np.any(dt<=0):
        raise ValueError('Duplicate or reversed timestamps; inspect raw receipt')
    if np.max(dt)>np.median(dt)*1.5:
        raise ValueError('Missing samples: do not smooth across gaps')
    gram=np.einsum('nij,nkj->nik',basis,basis)
    error=float(np.max(np.abs(gram-np.eye(3))))
    if error>1e-3:
        raise ValueError('Invalid sensor basis')
    return times-origin,acceleration,basis,{'samples':len(samples),'median_dt_s':float(np.median(dt)),
        'max_dt_s':float(np.max(dt)),'rate_hz':float(1/np.median(dt)),'max_basis_error':error}


def centered_average(values, samples=5):
    if samples%2!=1 or samples<1 or len(values)<samples:
        raise ValueError('Odd positive window fitting the data required')
    result=np.full(values.shape,np.nan,dtype=float)
    half=samples//2
    stop=len(values)-half if half else len(values)
    for component in range(values.shape[1]):
        result[half:stop,component]=np.convolve(values[:,component],np.ones(samples)/samples,mode='valid')
    return result


def event_times(receipt, vehicle):
    result=[]
    rows=receipt['telemetry']
    for event in receipt['events']:
        nearest=min(rows,key=lambda row:abs(row['wall']-event['wall']))
        reference=receipt['parameters']['vehicles'][0]['id']
        result.append({'event':event['event'],'sim_s':nearest['vehicles'][reference]['sim_time'],
            'wall_s':event['wall'],'precision':'Observation at telemetry poll; not exact contact time'})
    return result


def export(source, output, startup_exclusion=.5):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    output.mkdir(parents=True,exist_ok=False)
    receipt=json.loads(source.read_text(encoding='utf-8'))
    origin=receipt['simulation_time_origin']
    report={'source_receipt':source.name,'event':receipt['event'],'simulation_time_origin':origin,
        'axis_order':['forward','up','right'],'gravity_included':False,'g_m_s2':G,
        'startup_excluded_from_peaks_s':startup_exclusion,
        'filter':'Centered arithmetic mean of 5 samples, no edge padding; duration from actual sample interval',
        'measurement':'Local attached body sensor; not occupant acceleration; not an injury/force criterion',
        'vehicles':{}}
    for vehicle,samples in receipt['imu_readings'].items():
        settings=dict(receipt['imu_settings'].get('defaults',{}))
        settings.update(receipt['imu_settings'].get('vehicles',{}).get(vehicle,{}))
        if settings.get('is_using_gravity',True):raise ValueError('This report requires gravity disabled explicitly')
        if settings.get('dir')!=[0,-1,0] or settings.get('up')!=[0,0,1]:
            raise ValueError('Axis labels require the documented forward/up/right mount')
        t,a,basis,qc=validate_samples(samples,origin)
        window_ms=qc['median_dt_s']*5000
        qc['average_nominal_window_ms']=window_ms
        avg=centered_average(a)
        norm=np.linalg.norm(a,axis=1)/G
        avg_norm=np.linalg.norm(avg,axis=1)/G
        mask=(t>=startup_exclusion)&np.isfinite(avg_norm)
        if not mask.any():raise ValueError('No post-startup samples')
        raw_index=np.where(mask)[0][np.argmax(norm[mask])]
        avg_index=np.where(mask)[0][np.argmax(avg_norm[mask])]
        events=event_times(receipt,vehicle)
        qc.update(raw_peak_resultant_g=float(norm[raw_index]),raw_peak_sim_s=float(t[raw_index]),
            average_5samples_peak_resultant_g=float(avg_norm[avg_index]),average_peak_sim_s=float(t[avg_index]),
            initial_attachment_world_m=samples[0]['pos'],mount_settings=settings,events=events)
        report['vehicles'][vehicle]=qc
        header=['sim_s','engine_time_s']
        header += [f'acc_{axis}_m_s2' for axis in report['axis_order']]
        header += [f'acc_mean5_{axis}_m_s2' for axis in report['axis_order']]
        header += ['resultant_raw_g','resultant_mean5_g']
        header += [f'angular_velocity_world_{axis}_rad_s' for axis in 'xyz']
        header += [f'angular_velocity_{axis}_rad_s' for axis in report['axis_order']]
        header += [f'position_world_{axis}_m' for axis in 'xyz']
        header += [f'dir{axis}_{coord}' for axis in 'XYZ' for coord in 'xyz']
        with (output/(vehicle+'.csv')).open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.writer(f);writer.writerow(header)
            for i,s in enumerate(samples):
                omega=np.array(s['angVel'])
                local=basis[i]@omega
                writer.writerow([t[i],s['time'],*a[i],*avg[i],norm[i],avg_norm[i],*omega,*local,*s['pos'],*basis[i].ravel()])
        fig,axes=plt.subplots(3,1,figsize=(16,9),sharex=True,gridspec_kw={'height_ratios':[2,1.1,.9]})
        fig.patch.set_facecolor('#f6f5f0')
        title={'rear':'Frenada ante bache y alcance de van','moto_crash':'Esquiva y conflicto con motocicleta'}.get(receipt['event'],receipt['event'])
        name={'cdx_inc_lead':'Camioneta','cdx_inc_rear':'Van','cdx_inc_moto':'Motocicleta'}.get(vehicle,vehicle)
        fig.suptitle(title+' / '+name,fontsize=22,fontweight='bold',x=.08,ha='left',y=.97,color='#203748')
        colors=['#2678aa','#d27430','#508366']
        for axis,label,color in zip(range(3),['Longitudinal','Vertical','Lateral'],colors):
            axes[0].plot(t,a[:,axis]/G,color=color,alpha=.18,linewidth=.6)
            axes[0].plot(t,avg[:,axis]/G,color=color,label=f'{label} · media {window_ms:.0f} ms',linewidth=1.4)
        axes[0].set_ylabel('Aceleración local (g)');axes[0].legend(loc='upper left',ncol=3,fontsize=10)
        axes[1].plot(t,norm,color='#9bafbb',linewidth=.7,label='Resultante cruda')
        axes[1].plot(t,avg_norm,color='#243f53',linewidth=1.5,label='Resultante tras media de componentes')
        axes[1].set_ylabel('Resultante (g)');axes[1].legend(loc='upper left',fontsize=10)
        telemetry=[row['vehicles'][vehicle] for row in receipt['telemetry']]
        axes[2].plot([r['sim_time'] for r in telemetry],[r['speed']*3.6 for r in telemetry],color='#243f53',linewidth=2)
        axes[2].set_ylabel('Velocidad (km/h)');axes[2].set_xlabel('Tiempo de simulación (s)')
        for ax in axes:
            ax.set_facecolor('#ffffff');ax.grid(alpha=.18);ax.spines[['top','right']].set_visible(False)
            for event in events:ax.axvline(event['sim_s'],color='#c45d49',linestyle='--',alpha=.7)
            ax.set_xlim(startup_exclusion,float(t[-1]))
        for event in events:
            axes[0].text(event['sim_s']+.05,.84,'Frenada' if event['event']=='brake' else 'Daño detectado',
                transform=axes[0].get_xaxis_transform(),va='top',fontsize=9,color='#a04432')
        fig.text(.08,.025,f'SIMULACIÓN ILUSTRATIVA · IMU en carrocería · {qc["rate_hz"]:.0f} Hz · gravedad excluida · no mide lesiones del ocupante',fontsize=10,color='#52616b')
        fig.subplots_adjust(left=.08,right=.97,top=.90,bottom=.10,hspace=.16)
        fig.savefig(output/(vehicle+'.png'),dpi=150)
        fig.savefig(output/(vehicle+'.svg'))
        plt.close(fig)
    (output/'RESUMEN.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    with (output/'PICOS.csv').open('w',newline='',encoding='utf-8-sig') as f:
        fields=['vehicle','samples','rate_hz','raw_peak_resultant_g','raw_peak_sim_s','average_5samples_peak_resultant_g','average_peak_sim_s']
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for vehicle,stats in report['vehicles'].items():writer.writerow({'vehicle':vehicle,**stats})
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('receipt',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args()
    export(args.receipt,args.output)
