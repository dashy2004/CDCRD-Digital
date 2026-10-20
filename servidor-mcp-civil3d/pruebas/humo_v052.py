"""Humo de regresion 0.5.6; se conserva el nombre historico del script.

Solo DWG sintetico CDCRD_BRIDGE_SMOKE y auxiliar native_qa cargado. No usa
sondeos de proyecto ni cambia seguridad. Requiere CDCRD_C3D_QA_ROOT en el
proceso CAD y un timeout del puente <= 10000 ms (instancia aislada).
Uso: py humo_v052.py --drawing C:/QA/CDCRD_BRIDGE_SMOKE.dwg --output C:/QA/run
La carpeta output debe coincidir con CDCRD_C3D_QA_ROOT y estar vacia.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import puente_cliente as puente


def preflight(drawing, info, ping):
    expected = os.path.normcase(os.path.abspath(drawing))
    actual = os.path.normcase(os.path.abspath(info.get('dibujo', '')))
    if not Path(drawing).name.startswith('CDCRD_BRIDGE_SMOKE') or actual != expected:
        raise RuntimeError('Se exige el DWG sintetico exacto indicado; no se escribio')
    if ping.get('version') != '0.5.6':
        raise RuntimeError('Se requiere puente 0.5.6, recibido %s' % ping.get('version'))
    if not ping.get('comandos') or not ping.get('escritura'):
        raise RuntimeError('La instancia de prueba debe permitir comandos y escritura')
    timeout = ping.get('timeout_ms', 55000)
    if not 5000 <= timeout <= 10000:
        raise RuntimeError('Use una instancia QA con CDCRD_C3D_TIMEOUT_MS=5000..10000')


def wait_json(path, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            # El escritor puede estar terminando el recibo; solo se reintenta lectura.
            try:
                return json.loads(path.read_text(encoding='utf-8-sig'))
            except json.JSONDecodeError:
                pass
        time.sleep(0.1)
    raise RuntimeError('Sin recibo %s; NO reenviar el comando' % path)


def run(drawing, output):
    out = Path(output)
    if not out.is_dir() or any(out.iterdir()):
        raise RuntimeError('La carpeta QA debe existir y estar vacia')
    ping = puente.llamar('ping')
    preflight(drawing, puente.llamar('doc.info'), ping)
    if puente.llamar('diag.dialogos').get('modal_abierto'):
        raise RuntimeError('Hay un modal; no se inicia la prueba')
    checks = []
    report = {'ping': ping, 'drawing': drawing, 'checks': checks, 'ok': False}
    counter = 0

    def check(name, condition):
        checks.append({'name': name, 'pass': bool(condition)})
        print(('OK ' if condition else 'FAIL ') + name, flush=True)
        if not condition:
            raise AssertionError(name)

    def send_qa(action, **extra):
        nonlocal counter
        preflight(drawing, puente.llamar('doc.info'), ping)
        counter += 1
        name = '%02d-%s.json' % (counter, action)
        job = {'action': action, 'output': name, **extra}
        temp = out / 'job.tmp'
        temp.write_text(json.dumps(job), encoding='utf-8')
        temp.replace(out / 'job.json')
        puente.llamar_con_aprobacion('cmd.run', {'linea': 'CDCRDBRIDGEQA\n'})
        return out / name

    def qa(action, **extra):
        value = wait_json(send_qa(action, **extra))
        if not value.get('ok'):
            raise RuntimeError(value)
        return value['result']

    def repair(apply):
        return puente.llamar_con_aprobacion('gm.reparar', {
            'aplicar': apply, 'renombrar_sufijo_1': False,
            'borrar_hatches_huerfanos': False, 'borrar_grupos_muertos': True})

    try:
        fixture = qa('fixture')
        report['fixture'] = fixture
        initial = fixture['audit']
        check('ValueTuple por Invocar/PropGm/InvocarGm del DLL cargado',
              fixture['tuple']['render'] == 'render-ok' and fixture['tuple']['second'] == 7.25)
        check('grupo GM residual vacio real', initial['groups'].get('GM - CDCRD_EMPTY') == 0)
        hold_ms = ping['timeout_ms'] + 2500
        receipt = send_qa('hold', hold_ms=hold_ms, holding_output='holding.json')
        wait_json(out / 'holding.json')
        try:
            repair(True)
            raise AssertionError('La escritura debia vencer mientras CAD estaba ocupado')
        except puente.PuenteError as exc:
            report['cancelled_rpc'] = {'code': exc.codigo, 'message': exc.mensaje, 'data': exc.datos}
            check('timeout TCP: cancelada antes de ejecutar',
                  exc.codigo == -32000 and isinstance(exc.datos, dict)
                  and exc.datos.get('cancelada_antes_de_ejecutar') is True)
        check('bloqueo QA termino', wait_json(receipt)['ok'])
        after_cancel = qa('audit')
        check('al volver Idle el grupo sigue presente y no hubo escritura', after_cancel == initial)
        sim = repair(False)
        report['simulation'] = sim
        details = [g for a in sim['acciones'] for g in a.get('detalle', [])]
        check('simulacion detecta solo el grupo vacio GM',
              len(details) == 1 and details[0]['nombre'] == 'GM - CDCRD_EMPTY'
              and details[0]['borrable'] and details[0]['vacio_gm'])
        report['applied'] = repair(True)
        after = qa('audit')
        expected = dict(initial['groups'])
        del expected['GM - CDCRD_EMPTY']
        check('borrado positivo conserva grupo ajeno, GM vivo y mixto', after['groups'] == expected)
        check('limpieza conserva todas las entidades vivas', after['entities'] == initial['entities'])
        qa('running', timeout_output='running-timeout.json')
        running = wait_json(out / 'running-timeout.json')
        report['running_timeout'] = running
        check('timeout iniciado declara resultado incierto',
              running.get('data', {}).get('resultado_incierto') is True
              and running['data'].get('cancelada_antes_de_ejecutar') is False)
        request_id = running['data']['request_id']
        deadline = time.monotonic() + 15
        finished = False
        while time.monotonic() < deadline:
            state = puente.llamar('diag.cola')
            finished = any(x['request_id'] == request_id and x['estado'] == 'terminada'
                           and x['error'] is None for x in state['recientes'])
            if finished:
                break
            time.sleep(0.1)
        check('finalizacion de operacion incierta consultable por id', finished)
        final = qa('audit')
        check('operacion iniciada se ejecuto exactamente una vez', final['entities'] == after['entities'] + 1)
        report['final_audit'] = final
        report['queue'] = puente.llamar('diag.cola')
        check('sin despachos activos al cierre', report['queue']['activas'] == [])
        report['ok'] = True
        return 0
    finally:
        (out / 'humo-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--drawing', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()
    try:
        return run(args.drawing, args.output)
    except Exception as exc:
        print('FALLA:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
