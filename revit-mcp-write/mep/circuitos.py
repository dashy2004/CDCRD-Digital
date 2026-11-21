# -*- coding: utf-8 -*-
"""Circuitos de potencia para luminarias hacia un tablero.

La carga de cada luminaria se LEE del modelo (conector electrico o
RBS_ELEC_APPARENT_LOAD); si no hay dato, la luminaria queda fuera con
motivo. El limite por circuito es obligatorio: no hay valor por defecto.
Firmas: ver API-REVIT-2027.md. Cargas en VA, tensiones en V.
"""

from . import base, transaccion
from .base import ErrorApi, ErrorEntrada, exigir

NOMBRE_TRANSACCION = "MEP - crear circuitos de iluminacion"
CATEGORIA = "OST_LightingFixtures"
POTENCIA = ("PowerCircuit", "PowerBalanced", "PowerUnBalanced")
LOTE = 25
TOL_V = 0.5  # holgura al comparar tensiones, en voltios
CLAVES = ("luminarias", "categoria", "nivel", "tablero", "limite_va",
          "max_luminarias", "max_circuitos", "lote", "desde", "confirmar")


# --------------------------------------------------------------- lectura

def _valor_de_conector(DB, conector, parametro):
    """Valor de un parametro del conector de familia, o None si no hay."""
    info = conector.GetMEPConnectorInfo()
    lector = getattr(info, "GetConnectorParameterValue", None)
    if lector is None:
        return None
    try:
        valor = lector(DB.ElementId(parametro))
    except Exception:
        # El conector no define ese parametro: se sigue con instancia y tipo
        # (leer_dato); si tampoco estan, la luminaria queda fuera con motivo.
        return None
    return getattr(valor, "Value", None)


def _valor_de_parametro(elemento, parametro, entero):
    if elemento is None:
        return None
    p = elemento.get_Parameter(parametro)
    if p is None or not p.HasValue:
        return None
    return p.AsInteger() if entero else p.AsDouble()


def leer_dato(DB, doc, elemento, conector, nombre, entero=False):
    """Busca el dato en el conector, la instancia y el tipo, en ese orden.
    Devuelve (valor_interno, fuente) o (None, None)."""
    parametro = getattr(DB.BuiltInParameter, nombre)
    valor = _valor_de_conector(DB, conector, parametro)
    if valor is not None:
        return valor, "conector"
    valor = _valor_de_parametro(elemento, parametro, entero)
    if valor is not None:
        return valor, "instancia"
    tipo = doc.GetElement(elemento.GetTypeId())
    valor = _valor_de_parametro(tipo, parametro, entero)
    if valor is not None:
        return valor, "tipo"
    return None, None


def _conector_de_potencia(elemento):
    for conector in base.conectores(elemento):
        if (base.dominio(conector) == "electrico" and
                base.nombre_enum(conector.ElectricalSystemType) in POTENCIA):
            return conector
    return None


def _circuito_existente(elemento):
    modelo = getattr(elemento, "MEPModel", None)
    if modelo is None:
        return None
    for sistema in modelo.GetElectricalSystems() or []:
        if base.nombre_enum(sistema.SystemType) in POTENCIA:
            return base.eid_valor(sistema.Id)
    return None


def _rango(DB, tension):
    if tension is None:
        return None
    # VoltageType guarda voltios, no unidades internas (comprobado en vivo:
    # el tipo "120" da Min 110, Actual 120, Max 130). Los valores del
    # conector de la luminaria si son internos y se convierten aparte.
    return (float(tension.MinValue), float(tension.MaxValue))


def leer_distribucion(DB, tablero):
    """Sistema de distribucion del tablero: fase y rangos de tension (V)."""
    sistema = getattr(getattr(tablero, "MEPModel", None),
                      "DistributionSystem", None)
    if sistema is None:
        raise ErrorEntrada("el tablero no tiene sistema de distribucion asignado")
    return {"nombre": base.nombre_elemento(DB, sistema),
            "fase": base.nombre_enum(sistema.ElectricalPhase),
            "linea_linea_v": _rango(DB, sistema.VoltageLineToLine),
            "linea_tierra_v": _rango(DB, sistema.VoltageLineToGround)}


def incompatibilidad(distribucion, polos, tension_v):
    """None si la luminaria cabe en el sistema del tablero; si no, el motivo."""
    ll, lg = distribucion["linea_linea_v"], distribucion["linea_tierra_v"]
    if polos == 1:
        rango = lg if lg is not None else ll
    elif polos == 2:
        rango = ll
    elif polos == 3:
        if distribucion["fase"] != "ThreePhase":
            return "3 polos en un tablero que no es trifasico"
        rango = ll
    else:
        return "numero de polos no soportado: %s" % polos
    if rango is None:
        return "el tablero no ofrece tension para %d polo(s)" % polos
    if tension_v < rango[0] - TOL_V or tension_v > rango[1] + TOL_V:
        return "tension %.1f V fuera del rango %.1f-%.1f V del tablero" % (
            tension_v, rango[0], rango[1])
    return None


def _fuera(elemento_id, motivo, detalle=None):
    return {"id": elemento_id, "motivo": motivo, "detalle": detalle}


def clasificar(DB, doc, elemento, distribucion):
    """Devuelve (apta, None) o (None, exclusion) para una luminaria."""
    elemento_id = base.eid_valor(elemento.Id)
    conector = _conector_de_potencia(elemento)
    if conector is None:
        return None, _fuera(elemento_id, "sin_conector_electrico")
    circuito = _circuito_existente(elemento)
    if circuito is not None:
        return None, _fuera(elemento_id, "ya_en_circuito", "circuito %s" % circuito)
    carga, fuente = leer_dato(DB, doc, elemento, conector, "RBS_ELEC_APPARENT_LOAD")
    carga_va = None if carga is None else base.a_unidad(DB, carga, "VoltAmperes")
    if carga_va is None or carga_va <= 0.0:
        return None, _fuera(elemento_id, "sin_carga",
                            "RBS_ELEC_APPARENT_LOAD sin valor positivo")
    tension, _ = leer_dato(DB, doc, elemento, conector, "RBS_ELEC_VOLTAGE")
    polos, _ = leer_dato(DB, doc, elemento, conector,
                         "RBS_ELEC_NUMBER_OF_POLES", True)
    if tension is None or polos is None:
        return None, _fuera(elemento_id, "sin_tension_o_polos",
                            "no se pudo leer tension o polos de la luminaria")
    tension_v = base.a_unidad(DB, tension, "Volts")
    motivo = incompatibilidad(distribucion, int(polos), tension_v)
    if motivo is not None:
        return None, _fuera(elemento_id, "incompatible_con_tablero", motivo)
    return {"id": elemento_id, "carga_va": carga_va, "fuente_carga": fuente,
            "polos": int(polos), "tension_v": round(tension_v, 1)}, None


def _clasificar_todas(DB, doc, luminarias, distribucion, registro):
    aptas, fuera = [], []
    for elemento in luminarias:
        elemento_id = base.eid_valor(elemento.Id)
        try:
            apta, exclusion = clasificar(DB, doc, elemento, distribucion)
        except Exception as exc:
            registro.error("leer_luminaria", exc, elemento_id)
            apta, exclusion = None, _fuera(elemento_id, "error_api", str(exc))
        if apta is not None:
            aptas.append(apta)
        else:
            fuera.append(exclusion)
    return aptas, fuera


# ------------------------------------------------------------ agrupacion

def agrupar(aptas, limite_va, max_luminarias=None):
    """Reparte las luminarias, en el orden dado, en grupos que no superan
    limite_va ni max_luminarias. Solo comparten grupo las de iguales polos
    y tension. Devuelve (grupos, fuera)."""
    grupos, abiertos, fuera = [], {}, []
    for apta in aptas:
        if apta["carga_va"] > limite_va:
            fuera.append(_fuera(apta["id"], "excede_limite",
                                "%.1f VA > limite %.1f VA" % (apta["carga_va"], limite_va)))
            continue
        clave = (apta["polos"], apta["tension_v"])
        grupo = abiertos.get(clave)
        lleno = grupo is not None and (
            grupo["carga_va"] + apta["carga_va"] > limite_va + 1e-9 or
            (max_luminarias is not None and len(grupo["elementos"]) >= max_luminarias))
        if grupo is None or lleno:
            grupo = {"polos": apta["polos"], "tension_v": apta["tension_v"],
                     "carga_va": 0.0, "elementos": []}
            grupos.append(grupo)
            abiertos[clave] = grupo
        grupo["elementos"].append(apta["id"])
        grupo["carga_va"] += apta["carga_va"]
    return grupos, fuera


# ------------------------------------------------------------ validacion

def _luminarias(DB, doc, opciones):
    ids = opciones.get("luminarias")
    nombre = opciones.get("categoria")
    if ids is not None and nombre is not None:
        raise ErrorEntrada("pase 'luminarias' (ids) o 'categoria', no ambos")
    if ids is not None:
        elementos = base.elementos_por_ids(DB, doc, ids, "luminarias")
    else:
        if nombre not in (None, CATEGORIA):
            raise ErrorEntrada("'categoria' solo admite %s" % CATEGORIA)
        elementos = base.instancias_de_categoria(DB, doc, CATEGORIA)
    nivel = opciones.get("nivel")
    if nivel is not None:
        nivel_id = base.eid_valor(
            base.resolver_tipo(DB, doc, DB.Level, nivel, "nivel").Id)
        elementos = [e for e in elementos
                     if base.eid_valor(e.LevelId) == nivel_id]
    if not elementos:
        raise ErrorEntrada("no hay luminarias en el alcance pedido")
    return elementos


def _tablero(DB, doc, referencia):
    if isinstance(referencia, bool) or referencia is None:
        raise ErrorEntrada("falta 'tablero' (id o nombre de panel)")
    if isinstance(referencia, int):
        tablero = base.elemento_por_id(DB, doc, referencia)
        if tablero is None:
            raise ErrorEntrada("'tablero': no existe el id %s" % referencia)
        return tablero
    if not isinstance(referencia, str) or not referencia.strip():
        raise ErrorEntrada("'tablero' debe ser id (entero) o nombre (texto)")
    parametro = DB.BuiltInParameter.RBS_ELEC_PANEL_NAME
    hallados = []
    for equipo in base.instancias_de_categoria(DB, doc, "OST_ElectricalEquipment"):
        p = equipo.get_Parameter(parametro)
        if p is not None and p.AsString() == referencia:
            hallados.append(equipo)
    if len(hallados) != 1:
        raise ErrorEntrada("'tablero': %d equipos con nombre de panel '%s'; "
                           "pase el id" % (len(hallados), referencia))
    return hallados[0]


def validar(DB, doc, opciones):
    """Entrada -> configuracion resuelta. Lanza ErrorEntrada; no escribe."""
    if not isinstance(opciones, dict):
        raise ErrorEntrada("'opciones' debe ser un objeto")
    sobran = sorted(k for k in opciones if k not in CLAVES)
    if sobran:
        raise ErrorEntrada("opciones desconocidas: %s" % sobran)
    base.exigir_documento_editable(doc)
    if opciones.get("limite_va") is None:
        raise ErrorEntrada("falta 'limite_va': el limite de carga por circuito "
                           "es obligatorio y no tiene valor por defecto")
    cfg = {"limite_va": base.numero(opciones["limite_va"], "limite_va",
                                    0.0, 1.0e7, True),
           "max_luminarias": None, "max_circuitos": None}
    for clave in ("max_luminarias", "max_circuitos"):
        if opciones.get(clave) is not None:
            cfg[clave] = base.entero(opciones[clave], clave, 1, 100000)
    cfg["confirmar"] = opciones.get("confirmar", False)
    if not isinstance(cfg["confirmar"], bool):
        raise ErrorEntrada("'confirmar' debe ser true o false")
    cfg["lote"] = base.entero(opciones.get("lote", LOTE), "lote", 1, 200)
    cfg["desde"] = base.entero(opciones.get("desde", 0), "desde", 0)
    if cfg["confirmar"] and cfg["desde"] != 0:
        # Al confirmar, las luminarias ya circuitadas salen del plan de la
        # llamada siguiente: el plan es siempre el remanente y empieza en 0.
        raise ErrorEntrada("'desde' solo sirve en ensayo; al confirmar el plan "
                           "se recalcula sin las luminarias ya circuitadas: "
                           "repita la llamada con desde=0 hasta que "
                           "'siguiente' sea null")
    cfg["tablero"] = _tablero(DB, doc, opciones.get("tablero"))
    cfg["distribucion"] = leer_distribucion(DB, cfg["tablero"])
    cfg["luminarias"] = _luminarias(DB, doc, opciones)
    return cfg


# ------------------------------------------------------------- ejecucion

def _crear_circuito(DB, doc, tablero, grupo, limite_va):
    """Crea, asigna tablero y verifica un circuito. Devuelve (True, ficha)."""
    ids = base.lista_ids(DB, [base.eid(DB, i) for i in grupo["elementos"]])
    electrico = DB.Electrical
    sistema = exigir(electrico.ElectricalSystem.Create(
        doc, ids, electrico.ElectricalSystemType.PowerCircuit),
        "ElectricalSystem.Create")
    sistema.SelectPanel(tablero)
    doc.Regenerate()
    equipo = sistema.BaseEquipment
    if equipo is None or base.eid_valor(equipo.Id) != base.eid_valor(tablero.Id):
        raise ErrorApi("el circuito no quedo asignado al tablero pedido")
    miembros = sorted(base.eid_valor(e.Id) for e in sistema.Elements)
    faltan = [i for i in grupo["elementos"] if i not in miembros]
    if faltan:
        raise ErrorApi("el circuito no contiene las luminarias %s" % faltan)
    carga = base.a_unidad(DB, sistema.ApparentLoad, "VoltAmperes")
    if carga > limite_va + 1e-6:
        # La carga que calcula Revit manda sobre la suma leida de los
        # conectores: un circuito por encima del limite no se conserva.
        raise ErrorApi("la carga del circuito segun Revit (%.2f VA) supera "
                       "limite_va (%.2f VA)" % (carga, limite_va))
    return True, {
        "id": base.eid_valor(sistema.Id), "numero": sistema.CircuitNumber,
        "tablero": sistema.PanelName, "polos": int(sistema.PolesNumber),
        "tension_v": grupo["tension_v"], "carga_va": round(carga, 2),
        "carga_va_calculada": round(grupo["carga_va"], 2),
        "dentro_del_limite": carga <= limite_va + 1e-6,
        "elementos": miembros,
    }


def _trabajo(DB, doc, cfg, registro, lote):
    creados, fuera = [], []
    for grupo in lote:
        _, ficha, error = transaccion.en_subtransaccion(
            DB, doc, registro, "crear_circuito", grupo["elementos"][0],
            lambda: _crear_circuito(DB, doc, cfg["tablero"], grupo,
                                    cfg["limite_va"]))
        if ficha is None:
            fuera.extend(_fuera(i, "error_api", error) for i in grupo["elementos"])
        else:
            creados.append(ficha)
    return {"circuitos": creados, "fuera": fuera}


def _recortar(grupos, maximo):
    if maximo is None or len(grupos) <= maximo:
        return grupos, []
    fuera = [_fuera(i, "supera_max_circuitos", "limite de %d circuitos" % maximo)
             for grupo in grupos[maximo:] for i in grupo["elementos"]]
    return grupos[:maximo], fuera


def crear_circuitos(DB, doc, opciones):
    """Agrupa luminarias en circuitos de potencia hacia un tablero. Ver README.

    Ensayo por defecto (confirmar=False -> RollBack). Un lote de circuitos
    por llamada; 'siguiente' indica desde donde continuar.
    """
    cfg = validar(DB, doc, opciones)
    registro = base.Registro()
    aptas, fuera = _clasificar_todas(DB, doc, cfg["luminarias"],
                                     cfg["distribucion"], registro)
    grupos, excedidas = agrupar(aptas, cfg["limite_va"], cfg["max_luminarias"])
    grupos, sobrantes = _recortar(grupos, cfg["max_circuitos"])
    fuera = fuera + excedidas + sobrantes
    if grupos and cfg["desde"] >= len(grupos):
        raise ErrorEntrada("'desde' (%d) fuera de rango: hay %d circuitos planeados"
                           % (cfg["desde"], len(grupos)))
    lote, siguiente = base.trocear(grupos, cfg["desde"], cfg["lote"])
    salida = {"ensayo": not cfg["confirmar"], "confirmado": False,
              "transaccion": NOMBRE_TRANSACCION, "estado": "sin_transaccion"}
    datos = {"circuitos": [], "fuera": []}
    if lote:
        tx = transaccion.ejecutar(
            DB, doc, NOMBRE_TRANSACCION, cfg["confirmar"], registro,
            lambda: _trabajo(DB, doc, cfg, registro, lote))
        leidos = tx.pop("datos")
        if leidos is None:  # la transaccion entera fallo y se revirtio
            datos["fuera"] = [
                _fuera(i, "error_api", "transaccion revertida; ver 'errores'")
                for grupo in lote for i in grupo["elementos"]]
        else:
            datos = leidos
        salida.update(tx)
    if salida["confirmado"] and siguiente is not None:
        siguiente = 0  # el remanente se replanifica desde el principio
    salida.update({
        "tablero": base.eid_valor(cfg["tablero"].Id),
        "distribucion": cfg["distribucion"], "limite_va": cfg["limite_va"],
        "luminarias_total": len(cfg["luminarias"]),
        "circuitos_planeados": len(grupos), "desde": cfg["desde"],
        "siguiente": siguiente, "circuitos": datos["circuitos"],
        "sin_circuito": fuera + datos["fuera"],
        "ids_efimeros": not salida["confirmado"],
        "advertencias": registro.advertencias, "errores": registro.errores,
        "unidades": {"carga_va": "VA", "limite_va": "VA", "tension_v": "V"},
    })
    return salida
