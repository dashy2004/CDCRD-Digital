"""Reproducible JSON/CSV evidence export; no CAD connection."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from hidraulica import calculate


def export(source, destination):
    raw = source.read_bytes()
    result = calculate(json.loads(raw.decode('utf-8-sig')))
    result['input_sha256'] = hashlib.sha256(raw).hexdigest()
    result['engine_sha256'] = hashlib.sha256(Path(__file__).with_name('hidraulica.py').read_bytes()).hexdigest()
    destination.mkdir(parents=True, exist_ok=False)
    (destination/'resultado.json').write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    with (destination/'estados.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=['state', *result['normal']])
        writer.writeheader()
        for name in ('normal', 'critical'):
            writer.writerow({'state': name, **result[name]})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    export(args.input, args.output)
