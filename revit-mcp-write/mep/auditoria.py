# -*- coding: utf-8 -*-
"""Auditoria de conectores MEP. Solo lectura: no abre transacciones.

Complementa a revit-mcp-tools (mep_conectividad), que da hallazgos por
disciplina; aqui el detalle es por conector: dominio, sistema y diametro.
"""

from . import base
from .base import ErrorEntrada

# Categorias con conectores que se recorren si no se pide otra cosa.
CATEGORIAS = (
    "OST_PipeCurves", "OST_FlexPipeCurves", "OST_PipeFitting",
    "OST_PipeAccessory", "OST_PlumbingFixtures", "OST_Sprinklers",
    "OST_MechanicalEquipment", "OST_DuctCurves", "OST_DuctFitting",
    "OST_DuctAccessory", "OST_DuctTerminal", "OST_ElectricalEquipment",
    "OST_ElectricalFixtures", "OST_LightingFixtures", "OST_LightingDevices",
)
MAX_ELEMENTOS = 2000


def _clasificacion(conector, dom):
    if dom == "tuberia":
        return base.nombre_enum(conector.PipeSystemType)
    if dom == "electrico":
        return base.nombre_enum(conector.ElectricalSystemType)
    if dom == "ducto":
        return base.nombre_enum(conector.DuctSystemType)
    return None


def _sistema(DB, conector):
    sistema = conector.MEPSystem
    if sistema is None:
        return None, None
    return base.eid_valor(sistema.Id), base.nombre_elemento(DB, sistema)


def describir_conector(DB, conector):
    """Ficha de un conector. Unidades: posicion_m en metros, diametro_mm
    en milimetros (solo tuberia redonda), radio_interno_pies en pies."""
    dom = base.dominio(conector)
    fisico = base.es_fisico(conector)
    ficha = {
        "indice": int(conector.Id),
        "dominio": dom,
        "tipo": base.nombre_enum(conector.ConnectorType),
        "fisico": fisico,
        # IsConnected solo se consulta en conectores fisicos.
        "conectado": bool(conector.IsConnected) if fisico else None,
        "clasificacion": _clasificacion(conector, dom),
        "forma": None, "diametro_mm": None, "radio_interno_pies": None,
        "posicion_m": None,
    }
    ficha["libre"] = (ficha["conectado"] is False)
    ficha["sistema_id"], ficha["sistema"] = _sistema(DB, conector)
    if fisico:
        ficha["posicion_m"] = base.punto_m(DB, base.punto(conector.Origin))
    if dom in ("tuberia", "ducto"):
        ficha["forma"] = base.nombre_enum(conector.Shape)
    if dom == "tuberia" and ficha["forma"] == "Round":
        radio = float(conector.Radius)
        ficha["radio_interno_pies"] = radio
        ficha["diametro_mm"] = round(base.a_unidad(DB, 2.0 * radio, "Millimeters"), 2)
    return ficha


def _auditar_elemento(DB, elemento, registro):
    elemento_id = base.eid_valor(elemento.Id)
    categoria = getattr(elemento, "Category", None)
    fila = {"id": elemento_id,
            "categoria": getattr(categoria, "Name", None),
            "nombre": base.nombre_elemento(DB, elemento),
            "conectores": [], "total": 0, "libres": 0, "estado": "leido"}
    try:
        lista = base.conectores(elemento)
    except Exception as exc:
        registro.error("conectores", exc, elemento_id)
        fila["estado"] = "error"
        return fila
    if base.gestor_conectores(elemento) is None:
        fila["estado"] = "sin_gestor_de_conectores"
    for conector in lista:
        try:
            ficha = describir_conector(DB, conector)
        except Exception as exc:
            registro.error("conector", exc, elemento_id)
            fila["estado"] = "parcial"
            continue
        fila["conectores"].append(ficha)
        fila["total"] += 1
        fila["libres"] += 1 if ficha["libre"] else 0
    return fila


def _acumular(totales, fila):
    totales["conectores"] += fila["total"]
    totales["libres"] += fila["libres"]
    totales["elementos_con_libres"] += 1 if fila["libres"] else 0
    for ficha in fila["conectores"]:
        por_dominio = totales["por_dominio"].setdefault(
            ficha["dominio"], {"total": 0, "libres": 0})
        por_dominio["total"] += 1
        por_dominio["libres"] += 1 if ficha["libre"] else 0
        clave = ficha["clasificacion"] or "sin_clasificacion"
        totales["por_clasificacion"][clave] = (
            totales["por_clasificacion"].get(clave, 0) + 1)
        if ficha["diametro_mm"] is not None:
            diam = "%.2f" % ficha["diametro_mm"]
            totales["por_diametro_mm"][diam] = (
                totales["por_diametro_mm"].get(diam, 0) + 1)


def _alcance(DB, doc, categorias, ids):
    if ids is not None and categorias is not None:
        raise ErrorEntrada("pase 'ids' o 'categorias', no ambos")
    if ids is not None:
        return base.elementos_por_ids(DB, doc, ids, "ids"), None
    nombres = list(CATEGORIAS) if categorias is None else categorias
    if not isinstance(nombres, (list, tuple)) or not nombres:
        raise ErrorEntrada("'categorias' debe ser una lista no vacia")
    elementos = []
    for nombre in nombres:
        elementos.extend(base.instancias_de_categoria(DB, doc, nombre))
    return elementos, list(nombres)


def auditar_conectores(DB, doc, categorias=None, ids=None,
                       max_elementos=MAX_ELEMENTOS):
    """Conectores por elemento y en total. Solo lectura.

    categorias: lista de BuiltInCategory (texto); ids: lista de ids.
    max_elementos limita el detalle por elemento; los totales recorren
    siempre todo el alcance ('truncado' avisa si falta detalle).
    """
    base.entero(max_elementos, "max_elementos", 0, 100000)
    elementos, nombres = _alcance(DB, doc, categorias, ids)
    registro = base.Registro()
    totales = {"elementos": len(elementos), "conectores": 0, "libres": 0,
               "elementos_con_libres": 0, "por_dominio": {},
               "por_clasificacion": {}, "por_diametro_mm": {}}
    filas = []
    for elemento in elementos:
        fila = _auditar_elemento(DB, elemento, registro)
        _acumular(totales, fila)
        if len(filas) < max_elementos:
            filas.append(fila)
    return {
        "solo_lectura": True,
        "estado": "parcial" if registro.errores else "completo",
        "categorias": nombres,
        "totales": totales,
        "elementos": filas,
        "truncado": len(filas) < len(elementos),
        "errores": registro.errores,
        "unidades": {"diametro_mm": "mm", "radio_interno_pies": "pies",
                     "posicion_m": "m"},
    }
