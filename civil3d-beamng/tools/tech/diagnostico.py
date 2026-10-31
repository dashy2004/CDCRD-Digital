"""Read-only dependency/OBS checks. Does not launch BeamNG or record video."""
import argparse
from importlib.metadata import version
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tech-home', type=Path)
    parser.add_argument('--obs-config', type=Path, help='Local OBS WebSocket config; never committed.')
    args = parser.parse_args()
    report = {'packages': {name: version(name) for name in ('beamngpy', 'obsws-python')},
              'compatible_tech_series': '0.39', 'simulation_tested': False}
    if args.tech_home:
        report['tech'] = {'executable_found': (args.tech_home / 'Bin64/BeamNG.tech.x64.exe').is_file(),
                          'license_file_found': (args.tech_home / 'tech.key').is_file(),
                          'note': 'File existence does not verify license validity or engine version.'}
    if args.obs_config:
        import obsws_python as obs
        config = json.loads(args.obs_config.read_text(encoding='utf-8-sig'))
        if not config.get('auth_required') or not config.get('server_password'):
            raise ValueError('OBS authentication is required.')
        client = obs.ReqClient(host='127.0.0.1', port=config['server_port'],
                               password=config['server_password'], timeout=5)
        try:
            status = client.get_version()
            record = client.get_record_status()
            report['obs'] = {'version': status.obs_version,
                             'websocket_version': status.obs_web_socket_version,
                             'recording_active': record.output_active}
        finally:
            client.disconnect()
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
