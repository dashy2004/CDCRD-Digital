# -*- coding: utf-8 -*-
"""Sistema de distribucion de un tablero electrico: leer, crear y asignar.

Sin 'sistema' ni 'crear' es LECTURA: informa el sistema actual del tablero
y los que ofrece el documento. Con 'sistema' asigna uno existente; con
'crear' define primero las tensiones y el sistema.

Las tensiones van en VOLTIOS y asi las guarda Revit: VoltageType.ActualValue
de un tipo "208" vale 208.0. No se convierten a unidades internas; hacerlo
crea un tipo de unos 2239 V y Revit rechaza el sistema al confirmar con
"Selected distribution system type is invalid!".
Firmas: ver API-REVIT-2027.md.
"""

from . import base, circuitos, transaccion
from .base import ErrorApi, ErrorEntrada, exigir

NOMBRE_TRANSACCION = "MEP - sistema de distribucion del tablero"
CLAVES = ("tablero", "sistema", "crear", "confirmar")
CLAVES_CREAR = ("nombre", "fase", "configuracion", "hilos", "linea_linea_v",
                "linea_tierra_v", "tolerancia_pct")
FASES = {"monofasico": "SinglePhase", "trifasico": "ThreePhase"}
CONFIGURACIONES = {"sin_definir": "Undefined", "estrella": "Wye", "delta": "Delta"}
TOL_V = 0.5          # dos tensiones a menos de esto son la misma, en voltios
TOLERANCIA_PCT = 10.0
V_MIN, V_MAX = 1.0, 100000.0


# --------------------------------------------------------------- lectura

def _ajustes(DB, doc):
    return exigir(DB.Electrical.ElectricalSetting.GetElectricalSettings(doc),
                  "ElectricalSetting.GetElectricalSettings")


def _tension(tipo):
    if tipo is None:
        return None
    return {"nombre": tipo.Name, "real_v": float(tipo.ActualValue),
            "minimo_v": float(tipo.MinValue), "maximo_v": float(tipo.MaxValue)}


def ficha_sistema(sistema):
    """Datos de un DistributionSysType, con las tensiones en voltios."""
    return {"id": base.eid_valor(sistema.Id), "nombre": sistema.Name,
            "fase": base.nombre_enum(sistema.ElectricalPhase),
            "configuracion": base.nombre_enum(sistema.ElectricalPhaseConfiguration),
            "hilos": int(sistema.NumWires),
            "linea_linea": _tension(sistema.VoltageLineToLine),
            "linea_tierra": _tension(sistema.VoltageLineToGround)}


def _sistema_del_tablero(DB, doc, tablero):
    """DistributionSysType asignado al tablero, o None."""
    p = tablero.get_Parameter(
        DB.BuiltInParameter.RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM)
    if p is None:
        raise ErrorEntrada("el elemento %s no admite sistema de distribucion; "
                           "no es un tablero" % base.eid_valor(tablero.Id))
    actual = p.AsElementId()
    if actual is None or base.eid_valor(actual) < 0:
        return None
    return doc.GetElement(actual)


def _por_nombre(sistemas, nombre):
    return [s for s in sistemas if s.Name == nombre]


# ------------------------------------------------------------ validacion

def rango(valor_v, tolerancia_pct):
    """(minimo, maximo) en voltios alrededor de valor_v."""
    margen = valor_v * tolerancia_pct / 100.0
    return (valor_v - margen, valor_v + margen)


def validar_crear(crear):
    """Definicion de un sistema nuevo -> datos normalizados, en voltios."""
    if not isinstance(crear, dict):
        raise ErrorEntrada("'crear' debe ser un objeto")
    sobran = sorted(k for k in crear if k not in CLAVES_CREAR)
    if sobran:
        raise ErrorEntrada("claves desconocidas en 'crear': %s" % sobran)
    nombre = crear.get("nombre")
    if not isinstance(nombre, str) or not nombre.strip() or len(nombre) > 100:
        raise ErrorEntrada("'crear.nombre' debe ser un texto de 1 a 100 caracteres")
    fase, configuracion = crear.get("fase"), crear.get("configuracion", "sin_definir")
    if fase not in FASES:
        raise ErrorEntrada("'crear.fase' debe ser una de %s" % sorted(FASES))
    if configuracion not in CONFIGURACIONES:
        raise ErrorEntrada("'crear.configuracion' debe ser una de %s"
                           % sorted(CONFIGURACIONES))
    if fase == "trifasico" and configuracion == "sin_definir":
        raise ErrorEntrada("un sistema trifasico necesita 'configuracion' "
                           "estrella o delta")
    if fase == "monofasico" and configuracion != "sin_definir":
        raise ErrorEntrada("un sistema monofasico no lleva 'configuracion'")
    datos = {"nombre": nombre.strip(), "fase": fase, "configuracion": configuracion,
             "hilos": base.entero(crear.get("hilos"), "crear.hilos", 2, 4),
             "tolerancia_pct": base.numero(
                 crear.get("tolerancia_pct", TOLERANCIA_PCT),
                 "crear.tolerancia_pct", 0.0, 50.0, True)}
    for clave in ("linea_linea_v", "linea_tierra_v"):
        valor = crear.get(clave)
        datos[clave] = None if valor is None else base.numero(
            valor, "crear." + clave, V_MIN, V_MAX)
    if datos["linea_linea_v"] is None and datos["linea_tierra_v"] is None:
        raise ErrorEntrada("'crear' necesita linea_linea_v o linea_tierra_v, "
                           "en voltios")
    return datos


def validar(DB, doc, opciones):
    """Entrada -> configuracion resuelta. Lanza ErrorEntrada; no escribe."""
    if not isinstance(opciones, dict):
        raise ErrorEntrada("'opciones' debe ser un objeto")
    sobran = sorted(k for k in opciones if k not in CLAVES)
    if sobran:
        raise ErrorEntrada("opciones desconocidas: %s" % sobran)
    confirmar = opciones.get("confirmar", False)
    if not isinstance(confirmar, bool):
        raise ErrorEntrada("'confirmar' debe ser true o false")
    sistema, crear = opciones.get("sistema"), opciones.get("crear")
    if sistema is not None and crear is not None:
        raise ErrorEntrada("pase 'sistema' (existente) o 'crear', no ambos")
    cfg = {"confirmar": confirmar, "crear": None, "sistema": None,
           "tablero": circuitos._tablero(DB, doc, opciones.get("tablero"))}
    cfg["anterior"] = _sistema_del_tablero(DB, doc, cfg["tablero"])
    ajustes = _ajustes(DB, doc)
    existentes = list(ajustes.DistributionSysTypes)
    cfg["ajustes"], cfg["existentes"] = ajustes, existentes
    cfg["lectura"] = sistema is None and crear is None
    if cfg["lectura"]:
        if confirmar:
            raise ErrorEntrada("'confirmar' necesita 'sistema' o 'crear'")
        return cfg
    base.exigir_documento_editable(doc)
    if sistema is not None:
        if not isinstance(sistema, str) or not sistema.strip():
            raise ErrorEntrada("'sistema' debe ser el nombre de un sistema de "
                               "distribucion del documento")
        hallados = _por_nombre(existentes, sistema)
        if len(hallados) != 1:
            raise ErrorEntrada("'sistema': %d sistemas se llaman '%s'; disponibles: %s"
                               % (len(hallados), sistema,
                                  sorted(s.Name for s in existentes)))
        cfg["sistema"] = hallados[0]
        return cfg
    cfg["crear"] = validar_crear(crear)
    if _por_nombre(existentes, cfg["crear"]["nombre"]):
        raise ErrorEntrada("ya existe un sistema llamado '%s'; asignelo con "
                           "'sistema'" % cfg["crear"]["nombre"])
    return cfg


# ------------------------------------------------------------- ejecucion

def _tipo_de_tension(ajustes, valor_v, tolerancia_pct, notas):
    """VoltageType de valor_v voltios: reutiliza el que ya exista con ese
    valor real; si no, lo crea con los voltios tal cual."""
    if valor_v is None:
        return None
    tipos = list(ajustes.VoltageTypes)
    for tipo in tipos:
        if abs(float(tipo.ActualValue) - valor_v) <= TOL_V:
            notas.append({"tension_v": valor_v, "tipo": tipo.Name, "accion": "reutilizada"})
            return tipo
    nombre, usados = "%g V" % valor_v, set(t.Name for t in tipos)
    if nombre in usados:
        # Mismo nombre con otro valor: suele ser un tipo creado en unidades internas.
        nombre = "%g V (voltios)" % valor_v
    if nombre in usados:
        raise ErrorApi("ya existen tipos de tension '%g V' y '%s' con otro valor"
                       % (valor_v, nombre))
    minimo, maximo = rango(valor_v, tolerancia_pct)
    tipo = exigir(ajustes.AddVoltageType(nombre, valor_v, minimo, maximo),
                  "ElectricalSetting.AddVoltageType")
    notas.append({"tension_v": valor_v, "tipo": nombre, "accion": "creada",
                  "minimo_v": round(minimo, 3), "maximo_v": round(maximo, 3)})
    return tipo


def _crear_sistema(DB, ajustes, datos, notas):
    electrico = DB.Electrical
    ll = _tipo_de_tension(ajustes, datos["linea_linea_v"], datos["tolerancia_pct"], notas)
    lg = _tipo_de_tension(ajustes, datos["linea_tierra_v"], datos["tolerancia_pct"], notas)
    return exigir(ajustes.AddDistributionSysType(
        datos["nombre"],
        getattr(electrico.ElectricalPhase, FASES[datos["fase"]]),
        getattr(electrico.ElectricalPhaseConfiguration,
                CONFIGURACIONES[datos["configuracion"]]),
        datos["hilos"], ll, lg), "ElectricalSetting.AddDistributionSysType")


def _trabajo(DB, doc, cfg):
    notas = []
    sistema = cfg["sistema"]
    if sistema is None:
        sistema = _crear_sistema(DB, cfg["ajustes"], cfg["crear"], notas)
    tablero = cfg["tablero"]
    p = tablero.get_Parameter(
        DB.BuiltInParameter.RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM)
    if p.IsReadOnly:
        raise ErrorApi("el sistema de distribucion del tablero es de solo lectura")
    if not p.Set(sistema.Id):
        raise ErrorApi("Revit no acepto el sistema de distribucion en el tablero")
    doc.Regenerate()
    leido = _sistema_del_tablero(DB, doc, tablero)
    if leido is None or base.eid_valor(leido.Id) != base.eid_valor(sistema.Id):
        raise ErrorApi("el tablero no quedo con el sistema pedido tras regenerar")
    return {"sistema": ficha_sistema(leido), "tensiones": notas,
            "creado": cfg["sistema"] is None}


def distribucion_del_tablero(DB, doc, opciones):
    """Lee, o crea y asigna, el sistema de distribucion de un tablero. Ver README.

    Ensayo por defecto: Revit valida la compatibilidad al confirmar, y el
    ensayo hace ese Commit dentro de un grupo que despues se revierte.
    """
    cfg = validar(DB, doc, opciones)
    registro = base.Registro()
    anterior = cfg["anterior"]
    salida = {"lectura": cfg["lectura"], "ensayo": not cfg["confirmar"],
              "confirmado": False, "transaccion": NOMBRE_TRANSACCION,
              "estado": "sin_transaccion",
              "tablero": base.eid_valor(cfg["tablero"].Id),
              "sistema_anterior": None if anterior is None else ficha_sistema(anterior),
              "sistemas_disponibles": [ficha_sistema(s) for s in cfg["existentes"]],
              "sistema": None, "tensiones": [], "creado": False}
    if not cfg["lectura"]:
        tx = transaccion.ejecutar(DB, doc, NOMBRE_TRANSACCION, cfg["confirmar"],
                                  registro, lambda: _trabajo(DB, doc, cfg))
        datos = tx.pop("datos")
        salida.update(tx)
        if datos is not None:
            salida.update(datos)
    salida.update({"ids_efimeros": not salida["confirmado"] and salida["creado"],
                   "advertencias": registro.advertencias, "errores": registro.errores,
                   "unidades": {"real_v": "V", "minimo_v": "V", "maximo_v": "V",
                                "linea_linea_v": "V", "linea_tierra_v": "V"}})
    return salida
