"""Build a public signature inventory from local REA evidence, without code bodies.

Run REA locally first; neither the vendor DLL nor raw decompiled evidence is copied
into this repository. Metadata presence does not imply ETABS runtime support.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path


def build_catalog(artifact: dict, members: dict, source: str) -> dict:
    a, m = artifact['normalized_result'], members['normalized_result']
    if a['artifact']['sha256'] != m['artifact']['sha256']:
        raise ValueError('Artifact and members refer to different DLLs')
    if m['coverage']['state'] != 'complete':
        raise ValueError('Complete member coverage required')
    types = {t['token']: t for t in m['types']}
    interfaces = {k: t for k, t in types.items()
                  if t['flags'] & 0x20 and t['flags'] & 7 == 1}

    def decode_type(value: str) -> str:
        import re
        def replace(match):
            code = int(match.group(2))
            # ECMA-335 TypeDefOrRef coded index: lower 2 bits identify the table.
            if code & 3 == 0:
                token = f'0x{0x02000000 | (code >> 2):08x}'
                return types.get(token, {}).get('full_name', match.group(0))
            return match.group(0)
        return re.sub(r'(class|valuetype):(\d+)', replace, value)

    methods = []
    for row in m['methods']:
        if row['declaring_type_token'] not in interfaces or row['flags'] & 7 != 6:
            continue
        sig = row['signature']
        if sig['parse_status'] != 'decoded':
            raise ValueError(f'Undecoded signature: {row["token"]}')
        methods.append({'interface': row['declaring_type'], 'name': row['name'],
                        'token': row['token'], 'signature_sha256': sig['raw_sha256'],
                        'return_type': decode_type(sig['return_type']),
                        'parameter_types': [decode_type(v) for v in sig['parameter_types']]})
    methods.sort(key=lambda r: (r['interface'], r['name'], r['token']))
    tree = ast.parse(source)
    exposed = sorted({n.value.args[0].attr for n in ast.walk(tree)
                      if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                      and isinstance(n.value.func, ast.Call)
                      and isinstance(n.value.func.func, ast.Attribute)
                      and n.value.func.func.attr == 'tool' and n.value.args
                      and isinstance(n.value.args[0], ast.Attribute)
                      and isinstance(n.value.args[0].value, ast.Name)
                      and n.value.args[0].value.id == 'etabs'})
    return {'schema': 'cdcrd-oapi-catalog/1', 'rea_version': '6.5.0',
            'source_repository': 'https://github.com/morluto/rea',
            'artifact': {'name': 'CSiAPIv1.dll', 'sha256': a['artifact']['sha256'],
                         'assembly_version': a['assembly']['version'],
                         'mvid': a['module']['mvid'],
                         'managed_architecture': a['classification']['managed_architecture']},
            'evidence': {'artifact': artifact['evidence_id'], 'members': members['evidence_id']},
            'scope': 'Public interfaces of shared CSI API installed with ETABS 23; static metadata only.',
            'runtime_verified': False,
            'limitations': ['Shared CSI declarations can be unavailable in ETABS.',
                            'REF parameters require runtime typelib direction/name inspection.',
                            'No code bodies, models or customer data are included.'],
            'server_source_sha256': hashlib.sha256(source.encode()).hexdigest(),
            'mcp_tools': exposed, 'interface_count': len(interfaces),
            'method_count': len(methods), 'methods': methods}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', type=Path)
    parser.add_argument('members', type=Path)
    parser.add_argument('server', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    result = build_catalog(json.loads(args.artifact.read_text(encoding='utf-8-sig')),
                           json.loads(args.members.read_text(encoding='utf-8-sig')),
                           args.server.read_text(encoding='utf-8'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('interface_count', 'method_count', 'mcp_tools')}))


if __name__ == '__main__':
    main()
