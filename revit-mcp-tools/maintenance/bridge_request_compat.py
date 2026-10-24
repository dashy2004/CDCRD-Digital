"""Narrow, reversible source patch for the legacy pyRevit JSON request parser.

No process restart, route registration, model access or file write occurs here.
The caller must back up and hash-check the exact deployed module before writing.
"""
import json


def parse_payload(value):
    """Accept the dict/UTF-8/text representations used by pyRevit transports."""
    try:
        text_types = (basestring,)  # noqa: F821 - IronPython 2 compatibility
    except NameError:
        text_types = (str,)
    if isinstance(value, (bytes, bytearray)):
        value = value.decode('utf-8')
    if isinstance(value, text_types):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError('Request payload must be a JSON object')
    return value


OLD = '''            data = (
                json.loads(request.data)
                if isinstance(request.data, str)
                else request.data
            )'''
NEW = '            data = _mcp_compat_parse_payload(request.data)'


def patch_source(source, helper_source):
    """Refuse unknown/already-patched variants instead of patching heuristically."""
    if source.count(OLD) != 1 or '_mcp_compat_parse_payload' in source:
        raise ValueError('Unexpected parser source; inspect before patching')
    anchor = 'def register_code_execution_routes(api):'
    if source.count(anchor) != 1 or helper_source.count('def parse_payload(') != 1:
        raise ValueError('Unexpected registration/helper source')
    helper = helper_source.replace('def parse_payload(', 'def _mcp_compat_parse_payload(', 1)
    result = source.replace(OLD, NEW, 1).replace(anchor, helper + '\n\n' + anchor, 1)
    compile(result, '<bridge-parser-patch>', 'exec')
    return result
