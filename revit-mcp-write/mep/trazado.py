# -*- coding: utf-8 -*-
"""Conexion de aparatos sanitarios o rociadores a un ramal existente.

Cada conector libre se traza, se une y se VERIFICA (IsConnected tras
Regenerate) dentro de la transaccion. Un retorno None de la API es fallo.
Firmas: ver API-REVIT-2027.md. Unidades internas: pies.
"""

from . import base, geometria, transaccion
from .base import ErrorApi, ErrorEntrada
from .base import exigir as _exigir

NOMBRE_TRANSACCION = "MEP - conectar a ramal"
CATEGORIAS_APARATO = ("OST_PlumbingFixtures", "OST_Sprinklers")
UNIONES = ("te", "takeoff")
LOTE = 25
PENDIENTE_MAX = 0.5       # m/m
SALIDA_MM = 300.0         # tramo recto inicial si el conector no es vertical
TRAMO_MINIMO_MM = 50.0    # tramo mas corto que se intenta construir
MARGEN_EXTREMO_MM = 150.0  # distancia minima del entronque a un extremo
CLAVES = ("aparatos", "categoria", "ramal", "ramales", "tipo_tuberia",
          "tipo_sistema", "pendiente", "union", "nivel", "diametro_mm",
          "salida_mm", "tramo_minimo_mm", "margen_extremo_mm",
          "clasificaciones", "revertir_sueltos", "lote", "desde", "confirmar")


# ------------------------------------------------------------ validacion

def _booleano(opciones, clave, defecto):
    valor = opciones.get(clave, defecto)
    if not isinstance(valor, bool):
        raise ErrorEntrada("'%s' debe ser true o false" % clave)
    return valor


def _aparatos(DB, doc, opciones):
    ids, nombre = opciones.get("aparatos"), opciones.get("categoria")
    if (ids is None) == (nombre is None):
        raise ErrorEntrada("pase 'aparatos' (ids) o 'categoria', uno solo")
    if ids is not None:
        return base.elementos_por_ids(DB, doc, ids, "aparatos")
    if nombre not in CATEGORIAS_APARATO:
        raise ErrorEntrada("'categoria' debe ser una de %s" % (CATEGORIAS_APARATO,))
    return base.instancias_de_categoria(DB, doc, nombre)


def _ramales(DB, doc, opciones):
    uno, varios = opciones.get("ramal"), opciones.get("ramales")
    if (uno is None) == (varios is None):
        raise ErrorEntrada("pase 'ramal' (id) o 'ramales' (lista de ids), uno solo")
    ids = [base.entero(uno, "ramal")] if uno is not None else varios
    elementos = base.elementos_por_ids(DB, doc, ids, "ramales")
    for elemento in elementos:
        if not isinstance(elemento, DB.Plumbing.Pipe):
            raise ErrorEntrada("el ramal %s no es una tuberia (Pipe)"
                               % base.eid_valor(elemento.Id))
    return elementos


def _tipos(DB, doc, opciones):
    tubo = base.resolver_tipo(DB, doc, DB.Plumbing.PipeType,
                              opciones.get("tipo_tuberia"), "tipo_tuberia")
    if not DB.Plumbing.Pipe.IsPipeTypeId(doc, tubo.Id):
        raise ErrorEntrada("'tipo_tuberia' no es un PipeType valido")
    sistema = base.resolver_tipo(DB, doc, DB.Plumbing.PipingSystemType,
                                 opciones.get("tipo_sistema"), "tipo_sistema")
    if not DB.Plumbing.Pipe.IsPipingSystemTypeId(doc, sistema.Id):
        raise ErrorEntrada("'tipo_sistema' no es un PipingSystemType valido")
    return tubo, sistema


def _nivel(DB, doc, opciones, ramales):
    referencia = opciones.get("nivel")
    if referencia is not None:
        return base.resolver_tipo(DB, doc, DB.Level, referencia, "nivel").Id
    nivel = ramales[0].ReferenceLevel
    if nivel is None:
        raise ErrorEntrada("el ramal no tiene nivel de referencia; pase 'nivel'")
    return nivel.Id


def _clasificaciones(opciones, sistema):
    pedidas = opciones.get("clasificaciones")
    if pedidas is None:
        return [base.nombre_enum(sistema.SystemClassification)]
    if (not isinstance(pedidas, (list, tuple)) or not pedidas or
            any(not isinstance(p, str) for p in pedidas)):
        raise ErrorEntrada("'clasificaciones' debe ser una lista de nombres "
                           "de PipeSystemType")
    return list(pedidas)


def _longitudes(DB, opciones):
    def pies(clave, defecto, minimo):
        mm = base.numero(opciones.get(clave, defecto), clave, minimo, 100000.0)
        return base.de_unidad(DB, mm, "Millimeters")

    diametro = opciones.get("diametro_mm")
    if diametro is not None:
        diametro = base.de_unidad(DB, base.numero(
            diametro, "diametro_mm", 0.0, 2000.0, True), "Millimeters")
    return {"diametro": diametro,
            "salida": pies("salida_mm", SALIDA_MM, 1.0),
            "minimo": pies("tramo_minimo_mm", TRAMO_MINIMO_MM, 1.0),
            "margen": pies("margen_extremo_mm", MARGEN_EXTREMO_MM, 0.0)}


def validar(DB, doc, opciones):
    """Entrada -> configuracion resuelta. Lanza ErrorEntrada; no escribe."""
    if not isinstance(opciones, dict):
        raise ErrorEntrada("'opciones' debe ser un objeto")
    sobran = sorted(k for k in opciones if k not in CLAVES)
    if sobran:
        raise ErrorEntrada("opciones desconocidas: %s" % sobran)
    base.exigir_documento_editable(doc)
    if "pendiente" not in opciones:
        raise ErrorEntrada("falta 'pendiente' (m/m; 0 para redes a presion)")
    cfg = {"pendiente": base.numero(opciones["pendiente"], "pendiente",
                                    0.0, PENDIENTE_MAX)}
    cfg["union"] = opciones.get("union", "te")
    if cfg["union"] not in UNIONES:
        raise ErrorEntrada("'union' debe ser una de %s" % (UNIONES,))
    cfg["confirmar"] = _booleano(opciones, "confirmar", False)
    cfg["revertir_sueltos"] = _booleano(opciones, "revertir_sueltos", True)
    cfg["lote"] = base.entero(opciones.get("lote", LOTE), "lote", 1, 200)
    cfg["desde"] = base.entero(opciones.get("desde", 0), "desde", 0)
    cfg["aparatos"] = sorted(_aparatos(DB, doc, opciones),
                             key=lambda e: base.eid_valor(e.Id))
    if not cfg["aparatos"]:
        raise ErrorEntrada("no hay aparatos en el alcance pedido")
    if cfg["desde"] >= len(cfg["aparatos"]):
        raise ErrorEntrada("'desde' (%d) fuera de rango: hay %d aparatos"
                           % (cfg["desde"], len(cfg["aparatos"])))
    ramales = _ramales(DB, doc, opciones)
    cfg["ramales"] = [base.eid_valor(r.Id) for r in ramales]
    tubo, sistema = _tipos(DB, doc, opciones)
    cfg["tipo_tuberia"], cfg["tipo_sistema"] = tubo.Id, sistema.Id
    cfg["clasificaciones"] = _clasificaciones(opciones, sistema)
    cfg["nivel"] = _nivel(DB, doc, opciones, ramales)
    cfg.update(_longitudes(DB, opciones))
    return cfg


# -------------------------------------------------------------- trazado

def _eje(ramal):
    curva = ramal.Location.Curve
    return base.punto(curva.GetEndPoint(0)), base.punto(curva.GetEndPoint(1))


def _elegir_ramal(DB, doc, ids, origen):
    """Ramal candidato mas cercano al conector (distancia 3D al eje)."""
    mejor = None
    for valor in ids:
        ramal = _exigir(base.elemento_por_id(DB, doc, valor),
                        "GetElement(ramal %s)" % valor)
        a, b = _eje(ramal)
        d = geometria.distancia_a_segmento(origen, a, b)
        if mejor is None or d < mejor[0]:
            mejor = (d, ramal, a, b)
    return mejor[1], mejor[2], mejor[3]


def _crear_tuberia(DB, doc, cfg, inicio, fin, diametro):
    tubo = _exigir(DB.Plumbing.Pipe.Create(
        doc, cfg["tipo_sistema"], cfg["tipo_tuberia"], cfg["nivel"],
        base.xyz(DB, inicio), base.xyz(DB, fin)), "Pipe.Create")
    parametro = _exigir(
        tubo.get_Parameter(DB.BuiltInParameter.RBS_PIPE_DIAMETER_PARAM),
        "get_Parameter(RBS_PIPE_DIAMETER_PARAM)")
    if not parametro.Set(diametro):
        raise ErrorApi("no se pudo fijar el diametro de la tuberia nueva")
    return tubo


def _conector_en(elemento, p, que):
    conector = base.conector_mas_cercano(elemento, p)
    if conector is None:
        raise ErrorApi("%s: sin conector de tuberia" % que)
    if geometria.distancia(base.punto(conector.Origin), p) > 0.01:
        raise ErrorApi("%s: no hay conector en el punto esperado" % que)
    return conector


def _unir_aparato(DB, doc, conector, tubo, origen, direccion, siguiente):
    """Une el conector del aparato con el primer tramo. Devuelve
    (metodo, accesorio_o_None)."""
    extremo = _conector_en(tubo, origen, "primer tramo")
    crear = doc.Create
    if not geometria.son_colineales(direccion, geometria.resta(siguiente, origen)):
        return "NewElbowFitting", _exigir(
            crear.NewElbowFitting(conector, extremo), "NewElbowFitting(aparato)")
    conector.ConnectTo(extremo)
    return "ConnectTo", None


def _tramo_de_transicion(DB, doc, cfg, conector, puntos, diametro):
    """Diametro pedido distinto al del conector: Revit 2027 rechaza
    NewTransitionFitting contra el conector de un aparato ("The owner
    should be (flex) duct or pipe"), asi que el aparato recibe un tramo
    corto de su propio diametro y la transicion va entre dos tuberias.
    Devuelve (tramo_corto, punto_de_transicion)."""
    largo = geometria.distancia(puntos[0], puntos[1])
    corto = min(cfg["salida"], largo / 2.0)
    if corto < cfg["minimo"]:
        raise ErrorApi("el primer tramo (%.3f pies) no admite la transicion "
                       "de diametro junto al aparato" % largo)
    corte = geometria.suma(puntos[0], geometria.escala(
        geometria.versor(geometria.resta(puntos[1], puntos[0])), corto))
    tramo = _crear_tuberia(DB, doc, cfg, puntos[0], corte,
                           2.0 * float(conector.Radius))
    return tramo, corte


def _codos(doc, tuberias, puntos):
    accesorios = []
    for i in range(len(tuberias) - 1):
        vertice = puntos[i + 1]
        accesorios.append(_exigir(doc.Create.NewElbowFitting(
            _conector_en(tuberias[i], vertice, "tramo %d" % i),
            _conector_en(tuberias[i + 1], vertice, "tramo %d" % (i + 1))),
            "NewElbowFitting"))
    return accesorios


def _unir_ramal_te(DB, doc, ramal, tubo, entronque):
    """Parte el ramal en el entronque y coloca la te. Devuelve
    (accesorio, id_del_tramo_nuevo_del_ramal)."""
    nuevo_id = _exigir(DB.Plumbing.PlumbingUtils.BreakCurve(
        doc, ramal.Id, base.xyz(DB, entronque)), "PlumbingUtils.BreakCurve")
    if base.eid_valor(nuevo_id) < 0:
        raise ErrorApi("PlumbingUtils.BreakCurve devolvio InvalidElementId")
    nuevo = _exigir(doc.GetElement(nuevo_id), "GetElement(tramo partido)")
    te = _exigir(doc.Create.NewTeeFitting(
        _conector_en(ramal, entronque, "ramal partido"),
        _conector_en(nuevo, entronque, "tramo nuevo del ramal"),
        _conector_en(tubo, entronque, "derivacion")), "NewTeeFitting")
    return te, base.eid_valor(nuevo_id)


def _unir_ramal(DB, doc, cfg, ramal, tubo, entronque):
    if cfg["union"] == "takeoff":
        accesorio = _exigir(doc.Create.NewTakeoffFitting(
            _conector_en(tubo, entronque, "derivacion"), ramal),
            "NewTakeoffFitting")
        return accesorio, []
    accesorio, nuevo = _unir_ramal_te(DB, doc, ramal, tubo, entronque)
    return accesorio, [nuevo]


# ---------------------------------------------------------- verificacion

def _fila_suelto(DB, elemento_id, rol, conector, motivo):
    return {"elemento": elemento_id, "rol": rol,
            "conector": None if conector is None else int(conector.Id),
            "posicion_m": None if conector is None else base.punto_m(
                DB, base.punto(conector.Origin)),
            "motivo": motivo}


def _conectores_a_verificar(elemento, item):
    if item["modo"] == "indice":
        return [c for c in base.conectores(elemento)
                if int(c.Id) == item["indice"]]
    if item["modo"] == "cerca":
        cercano = base.conector_mas_cercano(elemento, item["punto"])
        return [] if cercano is None else [cercano]
    tipos = ("End",) if item["modo"] == "extremos" else base.TIPOS_FISICOS
    return [c for c in base.conectores(elemento)
            if base.nombre_enum(c.ConnectorType) in tipos]


def sueltos_de(DB, doc, implicados):
    """IsConnected de cada conector implicado. Llamar tras Regenerate y
    con la transaccion abierta. Devuelve la lista de sueltos."""
    sueltos = []
    for item in implicados:
        elemento = base.elemento_por_id(DB, doc, item["id"])
        if elemento is None:
            sueltos.append(_fila_suelto(DB, item["id"], item["rol"], None,
                                        "el elemento no existe tras regenerar"))
            continue
        revisar = _conectores_a_verificar(elemento, item)
        if not revisar:
            sueltos.append(_fila_suelto(DB, item["id"], item["rol"], None,
                                        "no se hallo el conector a verificar"))
        for conector in revisar:
            if not conector.IsConnected:
                sueltos.append(_fila_suelto(DB, item["id"], item["rol"],
                                            conector, "IsConnected=False"))
    return sueltos


def _unido_a(accesorio, elemento_id):
    """True si algun conector del accesorio refiere al elemento dado."""
    for conector in base.conectores(accesorio):
        for referido in conector.AllRefs:
            if base.eid_valor(referido.Owner.Id) == elemento_id:
                return True
    return False


def _implicados(aparato_id, indice, tuberias, accesorios, piezas, entronque):
    lista = [{"id": aparato_id, "rol": "aparato", "modo": "indice",
              "indice": indice}]
    for valor in tuberias:
        lista.append({"id": valor, "rol": "tramo_nuevo", "modo": "extremos"})
    for valor in accesorios:
        lista.append({"id": valor, "rol": "accesorio", "modo": "todos"})
    for valor in piezas:
        lista.append({"id": valor, "rol": "ramal", "modo": "cerca",
                      "punto": entronque})
    return lista


# ------------------------------------------------------------- ejecucion

def _tender(DB, doc, cfg, conector, puntos, direccion, diametro):
    """Tuberias y accesorios del aparato hasta el entronque, sin unir al
    ramal. Devuelve (metodo_de_union_al_aparato, tuberias, accesorios)."""
    origen, corto = puntos[0], None
    if abs(diametro - 2.0 * float(conector.Radius)) > 1e-6:
        corto, corte = _tramo_de_transicion(DB, doc, cfg, conector, puntos,
                                            diametro)
        puntos = [corte] + list(puntos[1:])
    tuberias = [_crear_tuberia(DB, doc, cfg, puntos[i], puntos[i + 1], diametro)
                for i in range(len(puntos) - 1)]
    metodo, primero = _unir_aparato(DB, doc, conector, corto or tuberias[0],
                                    origen, direccion, puntos[1])
    accesorios = [] if primero is None else [primero]
    if corto is not None:
        metodo = "NewTransitionFitting"
        accesorios.append(_exigir(doc.Create.NewTransitionFitting(
            _conector_en(corto, puntos[0], "tramo corto"),
            _conector_en(tuberias[0], puntos[0], "primer tramo")),
            "NewTransitionFitting"))
        tuberias_todas = [corto] + tuberias
    else:
        tuberias_todas = tuberias
    accesorios.extend(_codos(doc, tuberias, puntos))
    return metodo, tuberias_todas, accesorios


def _trazar_conector(DB, doc, cfg, ramales, aparato, conector):
    """Crea y une el trazado de un conector. Devuelve (mantener, ficha)."""
    if not base.es_redondo(conector):
        raise ErrorApi("el conector del aparato no es redondo")
    origen = base.punto(conector.Origin)
    direccion = base.punto(conector.CoordinateSystem.BasisZ)
    diametro = cfg["diametro"] or 2.0 * float(conector.Radius)
    ramal, a, b = _elegir_ramal(DB, doc, ramales, origen)
    ruta = geometria.calcular_ruta(
        origen, direccion, a, b, cfg["pendiente"], cfg["salida"],
        cfg["minimo"], cfg["margen"], base.TOL_PIES)
    entronque = ruta["entronque"]
    metodo, tuberias, accesorios = _tender(
        DB, doc, cfg, conector, ruta["puntos"], direccion, diametro)
    union, nuevos = _unir_ramal(DB, doc, cfg, ramal, tuberias[-1], entronque)
    accesorios.append(union)
    doc.Regenerate()
    ficha = {
        "ramal": base.eid_valor(ramal.Id),
        "tuberias": [base.eid_valor(t.Id) for t in tuberias],
        "accesorios": [base.eid_valor(x.Id) for x in accesorios],
        "union_aparato": metodo, "union_ramal": cfg["union"],
        "entronque_m": base.punto_m(DB, entronque),
        "diametro_mm": round(base.a_unidad(DB, diametro, "Millimeters"), 2),
        "ramales_nuevos": nuevos,
    }
    piezas = [ficha["ramal"]] + nuevos if cfg["union"] == "te" else []
    ficha["implicados"] = _implicados(
        base.eid_valor(aparato.Id), int(conector.Id), ficha["tuberias"],
        ficha["accesorios"], piezas, entronque)
    ficha["sueltos"] = sueltos_de(DB, doc, ficha["implicados"])
    if cfg["union"] == "takeoff" and not _unido_a(union, ficha["ramal"]):
        # IsConnected del accesorio no dice a que quedo unido: se exige
        # que alguno de sus conectores refiera al ramal pedido.
        ficha["sueltos"].append(_fila_suelto(
            DB, base.eid_valor(union.Id), "accesorio", None,
            "el takeoff no quedo unido al ramal %s" % ficha["ramal"]))
    mantener = not (ficha["sueltos"] and cfg["revertir_sueltos"])
    return mantener, ficha


def _motivo_omision(cfg, conector):
    if conector.IsConnected:
        return "conector ya conectado"
    clase = base.nombre_enum(conector.PipeSystemType)
    if clase not in cfg["clasificaciones"]:
        return "clasificacion %s no corresponde al sistema (%s)" % (
            clase, ", ".join(cfg["clasificaciones"]))
    return None


def _intentar(DB, doc, cfg, registro, estado, aparato, conector):
    aparato_id = base.eid_valor(aparato.Id)
    fila = {"aparato": aparato_id, "conector": int(conector.Id)}
    try:
        motivo = _motivo_omision(cfg, conector)
    except Exception as exc:
        # Un conector ilegible no debe tumbar el lote entero.
        registro.error("leer_conector", exc, aparato_id)
        fila.update({"estado": "fallido",
                     "motivo": "no se pudo leer el conector: %s" % exc})
        return fila
    if motivo is not None:
        fila.update({"estado": "omitido", "motivo": motivo})
        return fila
    mantenido, ficha, error = transaccion.en_subtransaccion(
        DB, doc, registro, "conectar", aparato_id,
        lambda: _trazar_conector(DB, doc, cfg, estado["ramales"], aparato,
                                 conector))
    if ficha is None:
        fila.update({"estado": "fallido", "motivo": error})
        return fila
    implicados, sueltos = ficha.pop("implicados"), ficha.pop("sueltos")
    nuevos = ficha.pop("ramales_nuevos")
    fila.update(ficha)
    if mantenido:
        estado["ramales"].extend(nuevos)
        estado["implicados"].extend(implicados)
        fila.update({"estado": "suelto" if sueltos else "conectado",
                     "motivo": None})
        return fila
    for suelto in sueltos:
        suelto.update({"aparato": aparato_id, "revertido": True})
    estado["sueltos_revertidos"].extend(sueltos)
    fila.update({"estado": "suelto_revertido",
                 "motivo": "%d conector(es) sin conectar; intento revertido"
                           % len(sueltos)})
    return fila


def _procesar_aparato(DB, doc, cfg, registro, estado, aparato):
    aparato_id = base.eid_valor(aparato.Id)
    try:
        candidatos = [c for c in base.conectores(aparato)
                      if base.es_fisico(c) and base.dominio(c) == "tuberia"]
    except Exception as exc:
        registro.error("conectores_del_aparato", exc, aparato_id)
        return [{"aparato": aparato_id, "conector": None, "estado": "fallido",
                 "motivo": "no se pudieron leer los conectores: %s" % exc}]
    if not candidatos:
        return [{"aparato": aparato_id, "conector": None, "estado": "omitido",
                 "motivo": "sin conectores fisicos de tuberia"}]
    return [_intentar(DB, doc, cfg, registro, estado, aparato, c)
            for c in candidatos]


def _trabajo(DB, doc, cfg, registro, lote):
    estado = {"ramales": list(cfg["ramales"]), "implicados": [],
              "sueltos_revertidos": []}
    filas = []
    for aparato in lote:
        filas.extend(_procesar_aparato(DB, doc, cfg, registro, estado, aparato))
    doc.Regenerate()
    finales = sueltos_de(DB, doc, estado["implicados"])
    por_elemento = set(s["elemento"] for s in finales)
    for fila in filas:
        if fila["estado"] != "conectado":
            continue
        propios = [fila["aparato"]] + fila["tuberias"] + fila["accesorios"]
        if any(p in por_elemento for p in propios):
            fila.update({"estado": "suelto",
                         "motivo": "suelto en la verificacion final del lote"})
    for suelto in finales:
        suelto["revertido"] = False
    return {"conexiones": filas, "ramales": estado["ramales"],
            "sueltos": finales + estado["sueltos_revertidos"]}


def _resumen(filas, sueltos):
    cuenta = {}
    for fila in filas:
        cuenta[fila["estado"]] = cuenta.get(fila["estado"], 0) + 1
    cuenta["sueltos"] = len(sueltos)
    return cuenta


def conectar_a_ramal(DB, doc, opciones):
    """Conecta aparatos a un ramal y verifica cada conector. Ver README.

    Ensayo por defecto (confirmar=False -> RollBack). Un lote por llamada.
    """
    cfg = validar(DB, doc, opciones)
    registro = base.Registro()
    lote, siguiente = base.trocear(cfg["aparatos"], cfg["desde"], cfg["lote"])
    tx = transaccion.ejecutar(
        DB, doc, NOMBRE_TRANSACCION, cfg["confirmar"], registro,
        lambda: _trabajo(DB, doc, cfg, registro, lote))
    datos = tx.pop("datos") or {"conexiones": [], "ramales": cfg["ramales"],
                                "sueltos": []}
    salida = dict(tx)
    salida.update({
        "aparatos_total": len(cfg["aparatos"]),
        "desde": cfg["desde"], "procesados": len(lote), "siguiente": siguiente,
        "conexiones": datos["conexiones"], "sueltos": datos["sueltos"],
        "resumen": _resumen(datos["conexiones"], datos["sueltos"]),
        # Tras un ensayo el ramal no quedo partido: se devuelven los originales.
        "ramales_siguientes": datos["ramales"] if tx["confirmado"]
        else cfg["ramales"],
        "ids_efimeros": not tx["confirmado"],
        "advertencias": registro.advertencias, "errores": registro.errores,
        "unidades": {"entronque_m": "m", "posicion_m": "m",
                     "diametro_mm": "mm", "pendiente": "m/m"},
    })
    return salida
