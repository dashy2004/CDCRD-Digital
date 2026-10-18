"""Grupos de puntos por descripcion + superficie TERRENO del polideportivo.

Corre EN VIVO por TCP contra el puente (el servidor MCP no recarga sus
herramientas, asi que se usan los metodos genericos objects.* del puente v0.5.4:
Coerce ya construye ObjectId desde handle y objetos desde JSON, que es lo que
hacia inalcanzable PointGroup.SetQuery y PointGroupsDefinition.AddPointGroup).

Pasos: lee los 122 puntos COGO, cuenta por RawDescription normalizada
(trim + mayusculas), verifica que ninguna descripcion sea prefijo de otra (si lo
fuera, el patron con comodin de una absorberia a la otra), crea un grupo por
descripcion con IncludeRawDescriptions = '<DESC>*', y alimenta la superficie
TERRENO con el grupo _All Points. No guarda el dibujo.

Uso:  py pruebas\\grupos_poli.py
"""
import json
import os
import sys
from collections import Counter

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, 'src'))

import puente_cliente as puente                         # noqa: E402

SALIDA = r'C:\Users\emilg\Artificial IQ\_diag\grupos_poli.json'
SUPERFICIE = 'TERRENO'
reporte = {'pasos': [], 'grupos': [], 'fallas': []}


def check(nombre, cond, detalle=''):
    linea = '%-52s %s %s' % (nombre, 'OK' if cond else 'FALLA', str(detalle)[:300])
    print(linea)
    reporte['pasos'].append({'paso': nombre, 'ok': bool(cond), 'detalle': str(detalle)[:500]})
    if not cond:
        reporte['fallas'].append(nombre)
    return cond


def norm(s):
    return (s or '').strip().upper()


# ---------------------------------------------------------------- 1. entorno
info = puente.llamar('doc.info')
check('puente 0.5.5+', info.get('puente_version') >= '0.5.5', info.get('puente_version'))
check('dwg del polideportivo', '16-POLIDEPORTIVO' in info.get('dibujo', ''), info.get('dibujo'))

# ---------------------------------------------------------------- 2. puntos
pts = puente.llamar('objects.query', {'coleccion': 'puntos',
                                      'props': ['PointNumber', 'RawDescription'],
                                      'limite': 500})
objetos = pts.get('objetos', [])
check('puntos leidos', len(objetos) == pts.get('coincidencias'), '%s de %s' % (len(objetos), pts.get('coincidencias')))
conteo = Counter(norm(o.get('RawDescription')) for o in objetos)
reporte['total_puntos'] = len(objetos)
reporte['conteo_por_descripcion'] = dict(conteo)
check('suma de descripciones = total', sum(conteo.values()) == len(objetos), sum(conteo.values()))
check('sin descripcion vacia', '' not in conteo, list(conteo))

colisiones = [(a, b) for a in conteo for b in conteo if a != b and b.startswith(a)]
check('ninguna descripcion es prefijo de otra', not colisiones, colisiones)
if colisiones:
    json.dump(reporte, open(SALIDA, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    sys.exit(1)

# -------------------------------------------------- 3. grupos ya existentes
def grupos_actuales():
    r = puente.llamar('objects.query', {'coleccion': 'grupos_puntos',
                                        'props': ['Name', 'PointsCount'], 'limite': 500})
    return {norm(o.get('Name')): o for o in r.get('objetos', [])}


previos = grupos_actuales()
check('grupos previos', True, ', '.join(sorted(previos)) or '(ninguno)')

# ------------------------------------------------------- 4. crear los grupos
for desc, esperado in sorted(conteo.items(), key=lambda kv: (-kv[1], kv[0])):
    patron = desc + '*'
    fila = {'grupo': desc, 'patron': patron, 'esperado': esperado}
    try:
        if desc in previos:
            handle = previos[desc]['handle']
            fila['creado'] = False
        else:
            r = puente.llamar_con_aprobacion('objects.invoke',
                                             {'ruta': 'PointGroups', 'metodo': 'Add', 'args': [desc]})
            handle = r.get('resultado')
            fila['creado'] = True
        fila['handle'] = handle
        # La query va como TEXTO JSON, no como objeto: JsonToClr del puente solo
        # digiere arreglos y valores; Coerce reconstruye el objeto desde el texto.
        consulta = json.dumps({'$tipo': 'StandardPointGroupQuery',
                               'IncludeRawDescriptions': patron,
                               'UseCaseSensitiveMatch': False})
        puente.llamar_con_aprobacion('objects.invoke', {
            'handle': handle, 'metodo': 'SetQuery', 'args': [consulta]})
        puente.llamar_con_aprobacion('objects.invoke', {'handle': handle, 'metodo': 'Update', 'args': []})
        q = puente.llamar('objects.query', {'handles': [handle], 'props': ['Name', 'PointsCount']})
        obtenido = q['objetos'][0].get('PointsCount')
        fila['puntos'] = obtenido
        check('grupo %-18s %3s pts' % (desc, obtenido), obtenido == esperado,
              'esperado %s' % esperado)
    except Exception as exc:                                   # noqa: BLE001
        fila['error'] = '%s: %s' % (type(exc).__name__, exc)
        check('grupo %s' % desc, False, fila['error'])
    reporte['grupos'].append(fila)

suma = sum(g.get('puntos') or 0 for g in reporte['grupos'])
check('suma de los grupos = total de puntos', suma == len(objetos), '%s vs %s' % (suma, len(objetos)))

# --------------------------------------------------------- 5. superficie TIN
sup = puente.llamar('objects.query', {'coleccion': 'superficies', 'props': ['Name'], 'limite': 50})
h_sup = next((o['handle'] for o in sup.get('objetos', []) if norm(o.get('Name')) == SUPERFICIE), None)
check('superficie %s' % SUPERFICIE, h_sup is not None, h_sup)

try:
  if h_sup:
    todos = grupos_actuales().get('_ALL POINTS')
    check('grupo _All Points', todos is not None, todos and todos.get('handle'))
    antes = puente.llamar('objects.read', {'handle': h_sup,
                                           'ruta': 'PointGroupsDefinition.Count'}).get('valor')
    reporte['definiciones_antes'] = antes
    if antes:
        check('definicion de grupos ya cargada (no se duplica)', True, 'Count=%s' % antes)
    elif todos:
        puente.llamar_con_aprobacion('objects.invoke', {
            'handle': h_sup, 'ruta': 'PointGroupsDefinition',
            'metodo': 'AddPointGroup', 'args': [todos['handle']]})
        check('AddPointGroup(_All Points)', True, '')
    puente.llamar_con_aprobacion('objects.invoke', {'handle': h_sup, 'metodo': 'Rebuild', 'args': []})
    gp = puente.llamar('objects.invoke', {'handle': h_sup, 'metodo': 'GetGeneralProperties',
                                          'args': [], 'profundidad': 2})
    est = gp.get('resultado') or {}
    reporte['estadisticas_superficie'] = est
    npts = est.get('NumberOfPoints')
    check('superficie con los 122 puntos', npts == len(objetos), 'NumberOfPoints=%s' % npts)
    # NumberOfTriangles no esta en GeneralSurfaceProperties sino en GetTinProperties
    tin = puente.llamar('objects.invoke', {'handle': h_sup, 'metodo': 'GetTinProperties',
                                           'args': [], 'profundidad': 2}).get('resultado') or {}
    reporte['estadisticas_tin'] = tin
    ntri = tin.get('NumberOfTriangles')
    check('superficie triangulada', bool(ntri), 'NumberOfTriangles=%s' % ntri)
    print('cotas: min %s  max %s' % (est.get('MinimumElevation'), est.get('MaximumElevation')))
except Exception as exc:                                       # noqa: BLE001
    check('superficie', False, '%s: %s' % (type(exc).__name__, exc))

json.dump(reporte, open(SALIDA, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
print('\nfallas: %s' % (reporte['fallas'] or 'ninguna'))
print('reporte: %s' % SALIDA)
