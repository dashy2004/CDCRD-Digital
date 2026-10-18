"""Pure contracts for wall tables; no COM calls and no engineering approval."""
import math


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
