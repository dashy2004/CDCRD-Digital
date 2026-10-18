"""Inventory observed tool calls, NOT a claim of full behavioral coverage."""
import argparse
import csv
import json
import re
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    server = (Path(__file__).parents[1] / 'src/server.py').read_text(encoding='utf-8')
    names = sorted(set(re.findall(r'^    (\w+) = mcp\.tool\([^\n]*', server.split('elif')[0], re.M)))
    # Only the ETABS branch (LUSAS follows its end).
    names = [n for n in names if n not in {'select','sweep_points','sweep_lines','sweep_surfaces',
                                          'get_lines','get_surfaces','get_volumes'}]
    rows=[]
    for name in names:
        observations=[]
        for phase in ['baseline','suite','results','advanced','roundtrip','lifecycle','walls','close']:
            file=args.output / f'{phase}-calls.json'
            if file.exists():
                observations.extend((phase,row) for row in json.loads(file.read_text(encoding='utf-8')) if row['name']==name)
        returned=[p for p,r in observations if r['status']=='returned']
        failures=[p for p,r in observations if r['status']=='failed']
        rows.append(dict(tool=name, returned_in=','.join(sorted(set(returned))),
                         failed_in=','.join(sorted(set(failures))),
                         status='returned (review assertions/results)' if returned else
                         ('controlled error / pending positive test' if failures else 'not exercised')))
    with (args.output/'COBERTURA-HERRAMIENTAS.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({'tools':len(rows),'returned':sum(bool(r['returned_in']) for r in rows),
                      'not_exercised':[r['tool'] for r in rows if r['status']=='not exercised'],
                      'no_positive_return':[r['tool'] for r in rows if not r['returned_in']]},indent=2))


if __name__ == '__main__':
    main()
