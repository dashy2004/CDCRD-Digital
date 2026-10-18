"""Wall result contracts and injected read-only calls; no engineering approval."""
import math
from typing import Any


def display_rows(result):
    """Decode GetTableForDisplayArray, preserving CSI's null/not-applicable cells."""
    if not isinstance(result, (list, tuple)) or len(result) != 6:
        raise ValueError('Contrato GetTableForDisplayArray desconocido')
    _, version, fields, count, data, ret = result
    if type(ret) is not int or ret != 0 or type(version) is not int:
        raise ValueError('Retorno/version de tabla invalido')
    if type(count) is not int or count < 0:
        raise ValueError('Conteo de tabla invalido')
    if (not isinstance(fields, (list, tuple)) or not fields
            or any(type(f) is not str or not f for f in fields)
            or len(set(fields)) != len(fields)):
        raise ValueError('Campos de tabla vacios/duplicados')
    if count == 0 and data is None:
        data = []
    if (not isinstance(data, (list, tuple)) or len(data) != count * len(fields)
            or any(v is not None and type(v) is not str for v in data)):
        raise ValueError('Celdas/conteo de tabla invalidos')
    return [dict(zip(fields, data[i:i+len(fields)])) for i in range(0, len(data), len(fields))]


def required_cases(combos, read_combo):
    """Expand nested combinations; refuse cycles and unknown item types."""
    required, visited = set(), set()

    def visit(name, ancestors):
        if name in ancestors:
            raise ValueError('Combinaciones con ciclo')
        if name in visited:
            return
        result = read_combo(name)
        if not isinstance(result, (list, tuple)) or len(result) != 5:
            raise ValueError('Contrato GetCaseList desconocido')
        count, kinds, names, factors, ret = result
        if type(ret) is not int or ret != 0 or type(count) is not int or count <= 0:
            raise ValueError('Combinacion vacia o retorno invalido')
        if any(not isinstance(v, (list, tuple)) or len(v) != count for v in (kinds, names, factors)):
            raise ValueError('Longitud de combinacion invalida')
        for kind, child, factor in zip(kinds, names, factors):
            if (type(kind) is not int or type(child) is not str or not child
                    or type(factor) not in (int, float) or not math.isfinite(factor)):
                raise ValueError('Item de combinacion invalido')
            if kind == 0:
                required.add(child)
            elif kind == 1:
                visit(child, ancestors | {name})
            else:
                raise ValueError('Tipo de item de combinacion desconocido')
        visited.add(name)

    for combo in combos:
        visit(combo, set())
    return sorted(required)


def assess_reinforcement(row):
    """Only compare reported percentages, not code compliance or full detailing."""
    try:
        required, current = float(row['ReinfPcent']), float(row['CurrPcent'])
    except (KeyError, TypeError, ValueError):
        return 'not_evaluated'
    if not all(math.isfinite(v) and v >= 0 for v in (required, current)):
        return 'not_evaluated'
    return 'current_below_required' if current < required else 'current_not_below_required'


LAYER_TYPES = {
    1: 'vertical_middle_each_face', 2: 'horizontal_middle_each_face',
    3: 'vertical_end_i_total', 4: 'vertical_end_j_total',
    5: 'confinement_end_i', 6: 'confinement_end_j', 7: 'diagonal_each',
}
LAYER_FIELDS = ('LayerID', 'LayerType', 'ClearCover', 'BarSizeName', 'BarArea',
                'BarSpacing', 'NumberBars', 'Confined', 'EndZoneLength',
                'EndZoneThickness', 'EndZoneOffset')


def area_rebar_rows(result):
    """Decode cAreaObj.GetRebarDataPier; preserve zero/default and null IDs.

    These are native layer data, not proof of checked design, current detailing,
    or anchorage. Layer types follow ETABSv1.eWallPierRebarLayerType.
    """
    if not isinstance(result, (list, tuple)) or len(result) != 13:
        raise ValueError('GetRebarDataPier: contrato desconocido')
    count, *columns, ret = result
    if type(ret) is not int or ret != 0 or type(count) is not int or count < 0:
        raise ValueError('GetRebarDataPier: retorno/conteo invalido')
    if count == 0:
        columns = [[] if c is None else c for c in columns]
    if any(not isinstance(c, (list, tuple)) or len(c) != count for c in columns):
        raise ValueError('GetRebarDataPier: longitudes incompatibles')
    rows = []
    for values in zip(*columns):
        row: dict[str, Any] = dict(zip(LAYER_FIELDS, values))
        if (row['LayerID'] is not None and type(row['LayerID']) is not str
                or type(row['LayerType']) is not int or row['LayerType'] not in LAYER_TYPES
                or type(row['BarSizeName']) is not str or not row['BarSizeName']
                or type(row['NumberBars']) is not int or row['NumberBars'] < 0
                or type(row['Confined']) is not bool):
            raise ValueError('GetRebarDataPier: identificador/tipo de capa invalido')
        for key in ('ClearCover', 'BarArea', 'BarSpacing', 'EndZoneLength',
                    'EndZoneThickness', 'EndZoneOffset'):
            value = row[key]
            if type(value) not in (float, int) or not math.isfinite(value):
                raise ValueError('GetRebarDataPier: valor no finito/numerico')
            if key != 'EndZoneOffset' and value < 0:
                raise ValueError('GetRebarDataPier: valor negativo')
        if row['BarArea'] <= 0:
            raise ValueError('GetRebarDataPier: area de barra no positiva')
        row['LayerTypeName'] = LAYER_TYPES[row['LayerType']]
        rows.append(row)
    return rows


def read_wall_area_layers(model, summary_rows, call_checked):
    """Read only areas mapped to the designed story/pier pairs, no mutations.

    Errors are propagated. Coverage describes retrieved layers, never a design
    pass. Native layer spacing/cover may differ from the checked pier section.
    """
    expected = {(r['Story'], r['Pier']) for r in summary_rows}
    result = call_checked(model.AreaObj, 'GetNameList', ())
    if (not isinstance(result, (list, tuple)) or len(result) != 3
            or type(result[0]) is not int or result[0] < 0
            or type(result[-1]) is not int or result[-1] != 0
            or not isinstance(result[1], (list, tuple)) or len(result[1]) != result[0]
            or any(type(n) is not str or not n for n in result[1])
            or len(set(result[1])) != result[0]):
        raise ValueError('AreaObj.GetNameList: contrato invalido')
    areas, covered, missing_areas = [], set(), []
    for name in result[1]:
        pier = call_checked(model.AreaObj, 'GetPier', (name,))
        if (len(pier) != 2 or type(pier[-1]) is not int or pier[-1] != 0
                or type(pier[0]) is not str):
            raise ValueError('AreaObj.GetPier: contrato invalido')
        if pier[0] in ('', 'None'):
            continue
        label = call_checked(model.AreaObj, 'GetLabelFromName', (name,))
        if (len(label) != 3 or type(label[-1]) is not int or label[-1] != 0
                or any(type(s) is not str or not s for s in label[:2])):
            raise ValueError('AreaObj.GetLabelFromName: contrato invalido')
        pair = (label[1], pier[0])
        if pair not in expected:
            continue
        layers = area_rebar_rows(call_checked(model.AreaObj, 'GetRebarDataPier', (name,)))
        areas.append({'AreaObjName': name, 'StoryName': pair[0], 'PierLabel': pair[1],
                      'layers': layers})
        if layers:
            covered.add(pair)
        else:
            missing_areas.append(name)
    return {'source': 'AreaObj.GetRebarDataPier', 'areas': areas,
            'layer_count': sum(len(a['layers']) for a in areas),
            'missing_area_layers': missing_areas,
            'missing_story_piers': [{'Story': s, 'Pier': p} for s, p in sorted(expected-covered)],
            'all_designed_story_piers_have_layers': bool(expected) and covered == expected and not missing_areas,
            'matches_checked_section': 'not_verified',
            'complete_detailing': False}
