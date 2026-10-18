"""Strict, pure helpers for ETABS editable tables (no COM or model writes)."""
import math


def editing_rows(result):
    if not isinstance(result, (tuple, list)) or len(result) != 5 or result[-1] != 0:
        raise ValueError('Respuesta GetTableForEditingArray no reconocida')
    version, fields, count, data, _ = result
    if type(version) is not int or type(count) is not int or count < 0:
        raise ValueError('Version/conteo de tabla invalido')
    if not isinstance(fields, (tuple, list)) or not fields or len(set(fields)) != len(fields):
        raise ValueError('Campos de tabla vacios/duplicados')
    if count == 0 and data is None:
        data = []
    if not isinstance(data, (tuple, list)) or len(data) != count * len(fields):
        raise ValueError('Conteo de celdas no coincide con filas/campos')
    if not all(isinstance(v, str) for v in [*fields, *data]):
        raise ValueError('Celda/campo de tabla no textual')
    return list(fields), [list(data[i:i+len(fields)]) for i in range(0, len(data), len(fields))]


def mass_source_rows(fields, rows, name, patterns):
    required = {'Name','IsDefault','IncLateral','IncVertical','LumpMass','SourceSelf',
                'SourceAdded','SourceLoads','LoadPattern','Multiplier'}
    if not required <= set(fields):
        raise ValueError('Esquema Mass Source Definition incompleto')
    if not name or not patterns or any(not key or type(value) not in (float,int)
                                       or not math.isfinite(value) or value < 0
                                       for key,value in patterns.items()):
        raise ValueError('Nombre/patrones/factores de masa invalidos')
    if not any(patterns.values()):
        raise ValueError('La fuente requiere al menos un factor positivo')
    ni, di = fields.index('Name'), fields.index('IsDefault')
    kept = []
    owner = ''
    for row in rows:
        if len(row) != len(fields):
            raise ValueError('Fila de masa incompleta')
        owner = row[ni] or owner
        if not owner:
            raise ValueError('Fila de masa sin propietario')
        if owner != name:
            copy = list(row)
            if copy[di]: copy[di] = 'No'
            kept.append(copy)
    common = {'Name':name, 'IsDefault':'Yes', 'IncLateral':'Yes', 'IncVertical':'No',
              'LumpMass':'Yes', 'SourceSelf':'No', 'SourceAdded':'No', 'SourceLoads':'Yes',
              'MoveMass':'No', 'RatioX':'0', 'RatioY':'0'}
    return kept + [[{**common, 'LoadPattern':pat, 'Multiplier':format(sf,'.17g')}.get(f,'')
                    for f in fields] for pat,sf in patterns.items()]


def time_history_row(fields, name, function, direction, scale, step, count,
                     nonlinear=False, modal_case='Modal'):
    """ETABS 23 editable schema. Units for scale are current acceleration units."""
    if not name or not function or direction not in ('U1', 'U2', 'U3'):
        raise ValueError('Nombre, funcion o direccion de time-history invalidos')
    if (type(count) is not int or count <= 0 or type(nonlinear) is not bool or
            type(step) not in (int, float) or not math.isfinite(step) or step <= 0 or
            type(scale) not in (int, float) or not math.isfinite(scale)):
        raise ValueError('Pasos, escala o tipo de time-history invalidos')
    data = dict(Name=name, LoadType='Accel', LoadName=direction, Function=function,
                TransAccSF=format(scale, '.17g'), TimeFactor='1', ArrivalTime='0',
                Angle='0', NumSteps=str(count), StepSize=format(step, '.17g'))
    if nonlinear:
        # Explicit, reproducible starting state; not an assertion of structural
        # adequacy. Material nonlinearities must be defined separately by user.
        data.update(InitialCond='Unstressed', GeoNonlin='None', ProBy='Direct',
                    MassCoeff='0', StiffCoeff='0', IntType='Newmark', Gamma='0.5', Beta='0.25')
    else:
        if not modal_case:
            raise ValueError('Falta el caso modal')
        data.update(ModalCase=modal_case, MotionType='Transient')
    if not set(data) <= set(fields):
        raise ValueError('Esquema time-history incompatible: faltan campos requeridos')
    return [data.get(field, '') for field in fields], data
