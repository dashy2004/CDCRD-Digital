"""Verificacion EN VIVO del puente v0.5.2 tras el reinicio unico.

Corre por TCP contra el puente (el servidor MCP no recarga). Pasos:
build/version, diag.dialogos servido desde el hilo del socket,
gm.diagnosticar (nuevo conteo grupos_muertos), gm.reparar en simulacion con
borrar_grupos_muertos y una prueba POSITIVA: un grupo de prueba cuyo unico
miembro (capa GM-PRUEBA-GRUPO) se borra debe salir como muerto y borrable,
borrarse con aplicar=true y desaparecer del diagnostico. El dibujo NO se
guarda; la capa de prueba se purga al final.

Uso:  py pruebas\\humo_v052.py
"""
import json
import os
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'src'))

import dibujo                                           # noqa: E402
import puente_cliente as puente                         # noqa: E402

BUILD_VIEJO = '882828cd77d9'
GRUPO = 'CDCRD_PRUEBA_MUERTO'
fallas = []


def check(nombre, cond, detalle=''):
    print('%-56s %s %s' % (nombre, 'OK' if cond else 'FALLA', str(detalle)[:400]))
    if not cond:
        fallas.append(nombre)


def lisp(codigo):
    ruta = dibujo.escribir_lisp_temporal(codigo)
    return puente.llamar_con_aprobacion('cmd.run', {'linea': dibujo.ruta_load(ruta)})


def esperar(fn, segundos=25):
    t0 = time.time()
    while time.time() - t0 < segundos:
        try:
            v = fn()
            if v:
                return v
        except Exception:                               # noqa: BLE001
            pass
        time.sleep(1.5)
    return None


def grupo_prueba(rep):
    for acc in rep.get('acciones', []):
        for g in acc.get('detalle', []) or []:
            if str(g.get('nombre', '')).upper() == GRUPO:
                return g
    return None


def principal():
    print('== 1. build ==')
    r = puente.llamar('ping', {})
    check('version 0.5.2', r.get('version') == '0.5.2', r.get('version'))
    check('build nuevo (no %s)' % BUILD_VIEJO, r.get('build') != BUILD_VIEJO, r.get('build'))
    print('dll:', r.get('dll'))
    doc = puente.llamar('doc.info', {})
    print('dibujo:', doc.get('ruta') or doc.get('nombre'))

    print('== 2. diag.dialogos desde el hilo del socket ==')
    d = puente.llamar('diag.dialogos', {})
    check('servido por el socket', d.get('hilo') == 'socket', d.get('hilo'))
    check('sin modal abierto', d.get('modal_abierto') is False, d.get('ventanas'))

    print('== 3. gm.diagnosticar ==')
    g = puente.llamar('gm.diagnosticar', {})
    print(json.dumps({k: g.get(k) for k in ('ok', 'problemas', 'grupos_muertos', 'hatches_sticklog',
                                            'superficie_top', 'project_id')}, ensure_ascii=False))
    check('reporta grupos_muertos', 'grupos_muertos' in g, g.get('grupos_muertos'))
    base = g.get('grupos_muertos', 0)

    print('== 4. gm.reparar simulacion con borrar_grupos_muertos ==')
    rep = puente.llamar_con_aprobacion('gm.reparar', {
        'aplicar': False, 'renombrar_sufijo_1': False,
        'borrar_hatches_huerfanos': True, 'borrar_grupos_muertos': True})
    print(json.dumps(rep, ensure_ascii=False)[:800])
    check('accion grupos_muertos presente',
          any('grupos_muertos' in a for a in rep.get('acciones', [])), rep.get('acciones'))

    print('== 5. prueba positiva: grupo con miembro borrado ==')
    lisp('(progn (setvar "CMDECHO" 0)'
         ' (entmake (list (cons 0 "LINE") (cons 8 "GM-PRUEBA-GRUPO")'
         ' (list 10 0.0 0.0 0.0) (list 11 1.0 1.0 0.0)))'
         ' (setq cdcrd_e (entlast))'
         ' (command "_.-GROUP" "_C" "%s" "prueba puente v052" cdcrd_e "")'
         ' (entdel cdcrd_e) (princ))' % GRUPO)
    gd = esperar(lambda: (lambda x: x if x.get('grupos_muertos', 0) > base else None)(
        puente.llamar('gm.diagnosticar', {})))
    check('diagnosticar ve el grupo muerto', gd is not None,
          None if gd is None else (gd.get('grupos_muertos'), gd.get('problemas')))
    sim = puente.llamar_con_aprobacion('gm.reparar', {
        'aplicar': False, 'renombrar_sufijo_1': False, 'borrar_grupos_muertos': True})
    gp = grupo_prueba(sim)
    check('simulacion: grupo de prueba borrable', bool(gp and gp.get('borrable')), gp)
    apl = puente.llamar_con_aprobacion('gm.reparar', {
        'aplicar': True, 'renombrar_sufijo_1': False, 'borrar_grupos_muertos': True})
    ga = grupo_prueba(apl)
    check('aplicar: grupo de prueba borrado',
          bool(ga and str(ga.get('accion', '')).startswith('borrado')), ga)
    gf = puente.llamar('gm.diagnosticar', {})
    check('diagnostico vuelve a la base (%s)' % base, gf.get('grupos_muertos') == base,
          gf.get('grupos_muertos'))
    lisp('(progn (setvar "CMDECHO" 0) (command "_.-PURGE" "_LA" "GM-PRUEBA-GRUPO" "_N") (princ))')

    print('== resumen ==')
    print('FALLAS:', fallas if fallas else 'ninguna')
    return 1 if fallas else 0


if __name__ == '__main__':
    try:
        sys.exit(principal())
    except Exception as exc:                            # noqa: BLE001
        print('EXCEPCION:', repr(exc))
        sys.exit(2)
