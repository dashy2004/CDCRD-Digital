# -*- coding: utf-8 -*-
"""Auditoría de redes y del unifilar. Compatible con el motor IronPython de pyRevit."""

from . import base

REDES = ("pluvial", "sanitaria")
POTENCIA = ("PowerCircuit", "PowerBalanced", "PowerUnBalanced")
CATEGORIAS = (
    "OST_PipeCurves",
    "OST_FlexPipeCurves",
    "OST_PipeFitting",
    "OST_PipeAccessory",
    "OST_PlumbingFixtures",
    "OST_Sprinklers",
    "OST_MechanicalEquipment",
)


def _texto(dato):
    return isinstance(dato, str) and dato.strip() != ""


def validar_config(datos, identidad):
    if not isinstance(datos, dict):
        raise ValueError("Manifiesto inválido")
    for campo in ("documento", "proyecto_uid", "revision"):
        if not _texto(datos.get(campo)) or datos[campo] != identidad[campo]:
            raise ValueError("Documento o revisión incompatible en " + campo)
    for campo in ("tipos_red", "redes_previstas"):
        mapa = datos.get(campo, {})
        if not isinstance(mapa, dict) or any(
            not _texto(k) or v not in REDES for k, v in mapa.items()
        ):
            raise ValueError("Mapa de redes inválido en " + campo)
    unifilar = datos.get("unifilar", [])
    if not isinstance(unifilar, list):
        raise ValueError("unifilar debe ser una lista")
    ids = set()
    for fila in unifilar:
        if not isinstance(fila, dict) or not all(
            _texto(fila.get(c)) for c in ("circuito", "tablero", "lamina")
        ):
            raise ValueError("Cada fila debe identificar circuito, tablero y lámina")
        cargas = fila.get("cargas")
        if (
            not isinstance(cargas, list)
            or not all(_texto(c) for c in cargas)
            or len(set(cargas)) != len(cargas)
            or fila["circuito"] in ids
        ):
            raise ValueError("Cargas inválidas o identificación de circuito duplicada")
        ids.add(fila["circuito"])
    return datos


def _fisico(con):
    return base.es_fisico(con) and base.dominio(con) == "tuberia"


def _id(con):
    return (str(con.Owner.UniqueId), int(con.Id))


def _ficha(doc, con, cfg):
    uid, puerto = _id(con)
    # La API documenta InvalidOperationException al obtener MEPSystem. Conservar
    # el enlace físico y su diagnóstico permite inspeccionar los demás circuitos.
    try:
        sistema = con.MEPSystem
        tipo = doc.GetElement(sistema.GetTypeId()) if sistema is not None else None
        uid_tipo = tipo.UniqueId if tipo is not None else None
        diagnostico = None
    except Exception as exc:
        uid_tipo = None
        diagnostico = str(exc)
    return {
        "elemento": uid,
        "conector": puerto,
        "tipo_sistema": uid_tipo,
        "red_segun_tipo": cfg.get("tipos_red", {}).get(uid_tipo),
        "red_prevista": cfg.get("redes_previstas", {}).get(uid),
        "error_sistema": diagnostico,
    }


def _estado_red(extremos):
    observadas = set(f["red_segun_tipo"] for f in extremos)
    previstas = set(f["red_prevista"] or f["red_segun_tipo"] for f in extremos)
    if set(REDES) in (observadas, previstas):
        return "cruce_pluvial_sanitaria"
    if any(
        f["red_prevista"]
        and f["red_segun_tipo"]
        and f["red_prevista"] != f["red_segun_tipo"]
        for f in extremos
    ):
        return "tipo_distinto_del_previsto"
    return "clasificacion_pendiente" if None in previstas else "misma_red_clasificada"


def leer_enlaces(doc, conectores, cfg):
    """Solo enlaces físicos DIRECTOS entre propietarios distintos. Cada par aparece una vez."""
    pares = {}
    fichas = {}
    for con in conectores:
        if not _fisico(con):
            continue
        origen = _id(con)
        if origen not in fichas:
            fichas[origen] = _ficha(doc, con, cfg)
        for ref in con.AllRefs:
            if not _fisico(ref):
                continue
            destino = _id(ref)
            if origen[0] == destino[0] or not con.IsConnectedTo(ref):
                continue
            pareja = tuple(sorted((origen, destino)))
            if pareja not in pares:
                if destino not in fichas:
                    fichas[destino] = _ficha(doc, ref, cfg)
                extremos = [fichas[k] for k in pareja]
                pares[pareja] = {"extremos": extremos, "estado": _estado_red(extremos)}
    elementos = set(f["elemento"] for f in fichas.values())
    tipos = set(f["tipo_sistema"] for f in fichas.values())
    return {
        "conectores": [fichas[k] for k in sorted(fichas)],
        "enlaces": [pares[k] for k in sorted(pares)],
        "elementos_previstos_no_leidos": sorted(
            set(cfg.get("redes_previstas", {})) - elementos
        ),
        "tipos_previstos_no_leidos": sorted(set(cfg.get("tipos_red", {})) - tipos),
    }


def leer_circuitos(sistemas, referencia, DB=None):
    """Circuitos de potencia activos. Excluye reservas y espacios sin componentes."""
    declarados = {fila["circuito"]: fila for fila in referencia}
    circuitos = []
    for c in sistemas:
        if (
            base.nombre_enum(c.CircuitType) != "Circuit"
            or base.nombre_enum(c.SystemType) not in POTENCIA
        ):
            continue
        uid = c.UniqueId
        panel = c.BaseEquipment
        tablero = panel.UniqueId if panel is not None else None
        cargas = sorted(e.UniqueId for e in c.Elements)
        externo = declarados.pop(uid, None)
        dif = []
        if externo:
            if externo["tablero"] != tablero:
                dif.append("tablero")
            if sorted(externo["cargas"]) != cargas:
                dif.append("cargas")
        row = {
            "circuito": uid,
            "numero": c.CircuitNumber,
            "tablero": tablero,
            "cargas": cargas,
            "estado_tablero": "identificado" if tablero else "sin_tablero",
            "lamina": externo["lamina"] if externo else None,
            "diferencias": dif,
            "unifilar_declarado": externo,
            "comparado": externo is not None,
        }
        if DB is not None:
            row["carga_aparente_VA"] = base.a_unidad(DB, c.ApparentLoad, "VoltAmperes")
        circuitos.append(row)
    return {
        "circuitos": sorted(circuitos, key=lambda r: r["circuito"]),
        "unifilar_sin_circuito": sorted(declarados),
    }


def auditar(DB, doc, identidad, datos):
    cfg = validar_config(datos, identidad)

    def puertos():
        for cat in CATEGORIAS:
            for elemento in base.instancias_de_categoria(DB, doc, cat):
                for con in base.conectores(elemento):
                    yield con

    sistemas = (
        DB.FilteredElementCollector(doc)
        .OfCategory(DB.BuiltInCategory.OST_ElectricalCircuit)
        .WhereElementIsNotElementType()
    )
    return {
        "esquema": "observaciones-mep/1",
        "origen": identidad,
        "hidrosanitaria": leer_enlaces(doc, puertos(), cfg),
        "electrica": leer_circuitos(sistemas, cfg.get("unifilar", []), DB),
        "alcance": "Enlaces físicos directos y circuitos de potencia del documento anfitrión. "
        "El unifilar se coteja contra las correspondencias declaradas.",
    }
