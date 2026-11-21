"""Pressure pipe networks: parts catalog, surface elevations, explicit network and verification; immutable receipts.

Same transport as the drainage module: request file + SHA-256, one-shot native command
CDCRDPRESIONV1 in the open Civil 3D process, receipt bound to the request. The layout
(node positions, depths, diameters) is decided by the caller in Python; the native module
only reads the pressure parts lists and surfaces, creates exactly the network it is given
(pipes between nodes, fittings/appurtenances at nodes, ports connected) and verifies it
against the stored contract CDCRD_PRESION_V1.
"""
import hashlib, json, math, ntpath, re, time, uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
import puente_cliente as bridge
import transporte

MODULE = "cdcrd-presion"
COMMAND = "CDCRDPRESIONV1"
VERSION_MINIMA = "0.2.0"
ACCIONES = ("catalogo", "cotas", "crear", "verificar", "trazado", "leer", "inspeccionar")
KINDS = {"libre": 0, "codo": 2, "te": 3, "cruz": 4, "tapon": 1, "reduccion": 2, "union": 2, "valvula": 2, "hidrante": 1, "bomba": 2}


class PresionError(RuntimeError):
    def __init__(self, message, receipt):
        super().__init__(message); self.receipt = receipt


def _texto(value, key, max_len=200):
    if not isinstance(value, str) or not value.strip() or len(value) > max_len or any(ord(c) < 32 for c in value):
        raise ValueError("Texto requerido: " + key)
    return value


def _numero(value, key, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{key} debe ser un numero entre {lo} y {hi}")
    return value


def _xyz(key, value):
    if not isinstance(value, (list, tuple)) or len(value) != 3: raise ValueError(key + " requiere XYZ")
    return [_numero(v, key, -1e8, 1e8) for v in value]


def validar_creacion(datos):
    out = dict(nombre=_texto(datos.get("nombre"), "nombre"), capa=_texto(datos.get("capa", "CDCRD-PRESION"), "capa"),
               tolerancia_m=_numero(datos.get("tolerancia_m", .005), "tolerancia_m", 1e-6, .1),
               tolerancia_conexion_m=_numero(datos.get("tolerancia_conexion_m", 1.0), "tolerancia_conexion_m", .001, 5),
               conectar=datos.get("conectar", True), rotar=datos.get("rotar", True))
    if not isinstance(out["conectar"], bool) or not isinstance(out["rotar"], bool): raise ValueError("conectar y rotar deben ser booleanos")
    for k in ("lista_partes", "superficie"):
        if datos.get(k): out[k] = _texto(datos[k], k)
    nodes = datos.get("nodos"); pipes = datos.get("tuberias")
    if not isinstance(nodes, list) or not 2 <= len(nodes) <= 300: raise ValueError("nodos: lista de 2..300")
    if not isinstance(pipes, list) or not 1 <= len(pipes) <= 300: raise ValueError("tuberias: lista de 1..300")
    ids = set(); out_n = []
    for n in nodes:
        if not isinstance(n, dict): raise ValueError("Cada nodo es un objeto")
        nid = _texto(n.get("id"), "id", 60)
        if nid in ids: raise ValueError("Nodo duplicado: " + nid)
        ids.add(nid)
        if n.get("tipo") not in KINDS: raise ValueError("tipo de nodo invalido: " + nid)
        row = dict(id=nid, tipo=n["tipo"], xyz=_xyz("xyz de " + nid, n.get("xyz")))
        if n["tipo"] != "libre": row["familia"] = _texto(n.get("familia"), "familia de " + nid)
        for k, lo, hi in (("diametro_nominal", .01, 1e4), ("diametro_nominal_2", .01, 1e4), ("angulo", 0, 180)):
            if n.get(k) is not None: row[k] = _numero(n[k], k + " de " + nid, lo, hi)
        if n.get("descripcion"): row["descripcion"] = _texto(n["descripcion"], "descripcion de " + nid)
        out_n.append(row)
    pids = set(); out_p = []
    for p in pipes:
        if not isinstance(p, dict): raise ValueError("Cada tuberia es un objeto")
        pid = _texto(p.get("id"), "id", 60)
        if pid in pids: raise ValueError("Tuberia duplicada: " + pid)
        pids.add(pid)
        a, b = p.get("desde"), p.get("hasta")
        if a not in ids or b not in ids or a == b: raise ValueError("Tuberia " + pid + " debe unir dos nodos distintos")
        out_p.append(dict(id=pid, desde=a, hasta=b, familia=_texto(p.get("familia"), "familia de " + pid), diametro_nominal=_numero(p.get("diametro_nominal"), "diametro_nominal de " + pid, .01, 1e4)))
    count = {n["id"]: sum(1 for p in out_p if n["id"] in (p["desde"], p["hasta"])) for n in out_n}
    for n in out_n:
        expected = KINDS[n["tipo"]]
        if count[n["id"]] == 0: raise ValueError("El nodo " + n["id"] + " no tiene tuberias")
        if expected and count[n["id"]] != expected: raise ValueError(f"El nodo {n['id']} ({n['tipo']}) requiere {expected} tuberias y tiene {count[n['id']]}")
    out["nodos"] = out_n; out["tuberias"] = out_p
    return out


def validar_cotas(datos):
    pts = datos.get("puntos")
    if not isinstance(pts, list) or not 1 <= len(pts) <= 5000: raise ValueError("puntos: lista de 1..5000")
    return dict(superficie=_texto(datos.get("superficie"), "superficie"), puntos=[[_numero(p[0], "x", -1e8, 1e8), _numero(p[1], "y", -1e8, 1e8)] for p in pts])


def _handle(value, key):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9A-Fa-f]{1,16}", value): raise ValueError(key + " debe ser un handle hexadecimal")
    return value.upper()


def _punto_xy(p):
    if not isinstance(p, (list, tuple)) or len(p) < 2: raise ValueError("Cada punto de la ruta es [x, y]")
    return [_numero(p[0], "x", -1e8, 1e8), _numero(p[1], "y", -1e8, 1e8)]


def validar_trazado(datos):
    """Route from vertices or from an existing polyline (never both); design cover is required, not assumed."""
    ruta, polilinea = datos.get("ruta"), datos.get("polilinea")
    if (ruta is None) == (polilinea is None): raise ValueError("Indique ruta (vertices) o polilinea (handle), una sola")
    codos = datos.get("codos_automaticos", True)
    if not isinstance(codos, bool): raise ValueError("codos_automaticos debe ser booleano")
    out = dict(nombre=_texto(datos.get("nombre"), "nombre"), capa=_texto(datos.get("capa", "CDCRD-PRESION"), "capa"), superficie=_texto(datos.get("superficie"), "superficie"),
               cobertura_m=_numero(datos.get("cobertura_m"), "cobertura_m", 0, 10), familia=_texto(datos.get("familia"), "familia"),
               diametro_nominal=_numero(datos.get("diametro_nominal"), "diametro_nominal", .01, 1e4), codos_automaticos=codos,
               paso_m=_numero(datos.get("paso_m", 5.0), "paso_m", .1, 100))
    if ruta is not None:
        if not isinstance(ruta, list) or not 2 <= len(ruta) <= 500: raise ValueError("ruta: lista de 2..500 puntos")
        out["ruta"] = [_punto_xy(p) for p in ruta]
    else:
        out["polilinea"] = _handle(polilinea, "polilinea")
    if datos.get("cobertura_min_m") is not None:
        out["cobertura_min_m"] = _numero(datos["cobertura_min_m"], "cobertura_min_m", 0, 10)
        if out["cobertura_min_m"] > out["cobertura_m"]: raise ValueError("cobertura_min_m no puede superar cobertura_m")
    for k in ("lista_partes", "tramo"):
        if datos.get(k): out[k] = _texto(datos[k], k)
    return out


def validar_inspeccion(datos):
    out = dict(red=_texto(datos.get("red"), "red"), paso_m=_numero(datos.get("paso_m", 5.0), "paso_m", .1, 100))
    if datos.get("superficie"): out["superficie"] = _texto(datos["superficie"], "superficie")
    if datos.get("cobertura_min_m") is not None: out["cobertura_min_m"] = _numero(datos["cobertura_min_m"], "cobertura_min_m", 0, 20)
    return out


def ejecutar(dibujo, pid, *, accion, simular=True, timeout=180, **datos):
    if not ntpath.isabs(dibujo) or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("Ruta DWG absoluta y PID positivo requeridos")
    if accion not in ACCIONES or not isinstance(simular, bool):
        raise ValueError("Accion o simulacion invalida")
    if accion == "catalogo": datos = dict(lista_partes=_texto(datos["lista_partes"], "lista_partes")) if datos.get("lista_partes") else {}
    elif accion == "cotas": datos = validar_cotas(datos)
    elif accion == "crear": datos = validar_creacion(datos)
    elif accion == "trazado": datos = validar_trazado(datos)
    elif accion == "leer": datos = dict(red=_texto(datos["red"], "red")) if datos.get("red") else {}
    elif accion == "inspeccionar": datos = validar_inspeccion(datos)
    else: datos = dict(red=_texto(datos.get("red"), "red"))
    request = dict(datos, dibujo=dibujo, pid=pid, accion=accion, simular=simular,
                   vence_utc=(datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat())
    info = bridge.llamar("doc.info")
    if not info.get("civil3d") or ntpath.normcase(info["dibujo"]) != ntpath.normcase(dibujo) or info["insunits"] != 6:
        raise ValueError("Documento Civil o unidades distintos a lo esperado")
    if bridge.llamar("diag.dialogos")["modal_abierto"] or bridge.llamar("diag.cola")["activas"]:
        raise RuntimeError("Civil ocupado; revisar cola/dialogo antes de enviar")
    root = Path(dibujo).parent
    # A 0.1.0 module still loaded would run 'trazado' without inspection and ignore the new fields.
    transporte.exigir_version(MODULE, COMMAND, root, pid, VERSION_MINIMA)
    key = uuid.uuid4().hex
    data = json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    request_path = root / (MODULE + "-" + key + ".request.json")
    result_path = root / (MODULE + "-" + key + ".result.json")
    with request_path.open("xb") as file:
        file.write(data)
    pending = {"id": key, "sha256": digest, "receipt_path": str(result_path), "estado": "desconocido"}
    try:
        bridge.llamar_con_aprobacion("cmd.run", {"linea": f"{COMMAND}\n{key}\n{digest}\n"})
    except Exception as exc:
        raise PresionError("Despacho incierto: consultar recibo y cola; no reintentar. " + str(exc), pending) from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("id") != key or result.get("sha256") != digest or result.get("module") != MODULE or result.get("pid") != pid:
                raise PresionError("Recibo no corresponde a la solicitud/sesion; no reintentar", pending)
            if not result.get("ok"):
                raise PresionError(result.get("error", "Fallo nativo"), result)
            return result
        time.sleep(.1)
    raise PresionError("Sin recibo final. Verificar modulo cargado, cola y archivo indicado; no reintentar escrituras", pending)


def registrar(mcp, ok):
    def call(fn, *args, **kwargs):
        try: return ok(fn(*args, **kwargs))
        except PresionError as exc: return ok({"error": str(exc), "receipt": exc.receipt})
        except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc: return ok({"error": str(exc)})

    @mcp.tool()
    def listar_catalogo_presion(dibujo: str, pid: int, lista_partes: str = "") -> str:
        """Lista las listas de partes de presion del dibujo (tuberias, accesorios y aparatos con sus propiedades de catalogo) y las redes de presion existentes.

        Las propiedades (DiameterNominal, FittingAngle, PipeDiameterOutside...) llevan
        las unidades del catalogo de la lista: el imperial guarda pulgadas. Sirve para
        elegir familia y diametro_nominal de crear_red_presion. Lectura sin cambios.
        """
        return call(ejecutar, dibujo, pid, accion="catalogo", lista_partes=lista_partes or None)

    @mcp.tool()
    def cotas_superficie(dibujo: str, pid: int, superficie: str, puntos: str) -> str:
        """Cota de una superficie TIN en una lista de puntos JSON [[x, y], ...] (null fuera de la superficie). Lectura sin cambios."""
        try: pts = json.loads(puntos)
        except ValueError as exc: return ok({"error": str(exc)})
        return call(ejecutar, dibujo, pid, accion="cotas", superficie=superficie, puntos=pts)

    @mcp.tool()
    def crear_red_presion(dibujo: str, pid: int, nombre: str, nodos: str, tuberias: str, lista_partes: str = "", superficie: str = "",
                          capa: str = "CDCRD-PRESION", conectar: bool = True, rotar: bool = True, tolerancia_conexion_m: float = 1.0,
                          simular: bool = True, confirmar: bool = False) -> str:
        """Crea una red de tuberias a presion (PressurePipeNetwork) exactamente como se describe, con contrato CDCRD_PRESION_V1.

        nodos JSON [{id, tipo, xyz, familia, diametro_nominal, angulo}]: tipo libre
        (extremo abierto: toma en la red existente, entrada a cisterna, acometida al
        edificio), codo (2 tuberias), te (3), cruz (4), tapon (1), reduccion (2),
        union (2), valvula (2), hidrante (1), bomba (2). xyz es el eje de la tuberia.
        tuberias JSON [{id, desde, hasta, familia, diametro_nominal}]: tramos rectos
        entre nodos. Las piezas se eligen por tipo, fragmento de descripcion, diametro
        nominal en unidades del catalogo y angulo (ver listar_catalogo_presion). En
        cada nodo con pieza el modulo gira la pieza para alinear sus bocas con las
        tuberias y conecta cada boca; verifica posiciones, piezas, conexiones y capa
        y guarda el contrato en la red. Simula por defecto (crea y aborta). No
        calcula hidraulica ni profundidades: las cotas del eje vienen en xyz.
        """
        if not confirmar: return ok({"error": "Operacion de escritura: requiere confirmar=True"})
        try: n = json.loads(nodos); t = json.loads(tuberias)
        except ValueError as exc: return ok({"error": str(exc)})
        return call(ejecutar, dibujo, pid, accion="crear", simular=simular, nombre=nombre, nodos=n, tuberias=t, lista_partes=lista_partes or None,
                    superficie=superficie or None, capa=capa, conectar=conectar, rotar=rotar, tolerancia_conexion_m=tolerancia_conexion_m)

    @mcp.tool()
    def verificar_red_presion(dibujo: str, pid: int, red: str) -> str:
        """Relee el contrato CDCRD_PRESION_V1 de la red de presion y comprueba tuberias, piezas, posiciones, conexiones y capa."""
        return call(ejecutar, dibujo, pid, accion="verificar", red=red)

    @mcp.tool()
    def leer_redes_presion(dibujo: str, pid: int, red: str = "") -> str:
        """Lee las redes de tuberias a presion del dibujo, tengan o no contrato propio.

        Sin red: resumen de cada una (tuberias, accesorios, aparatos, tramos,
        longitud 2D/3D, cotas minima y maxima, longitud por diametro). Con red
        (nombre o handle): ademas el detalle de cada tuberia (pieza, material y
        diametro nominal del catalogo, diametros interior/exterior, extremos XYZ,
        longitudes, pendiente, cobertura minima y maxima segun Civil, piezas en
        cada extremo) y de cada accesorio o aparato (tipo, posicion y bocas con
        lo que tienen conectado). Metros; lectura sin cambios.
        """
        return call(ejecutar, dibujo, pid, accion="leer", red=red or None)

    @mcp.tool()
    def trazar_red_presion(dibujo: str, pid: int, nombre: str, superficie: str, familia: str, diametro_nominal: float, cobertura_m: float,
                           ruta: str = "", polilinea: str = "", cobertura_min_m: float = -1.0, lista_partes: str = "", capa: str = "CDCRD-PRESION",
                           codos_automaticos: bool = True, paso_m: float = 5.0, simular: bool = True, confirmar: bool = False) -> str:
        """Crea una red a presion nueva con un tramo que sigue una ruta en planta a una cobertura dada bajo una superficie TIN.

        La ruta es `ruta` (JSON [[x, y], ...]) o `polilinea` (handle de una
        polilinea ligera o 3D abierta y sin arcos; de la 3D se toma solo la
        planta y no se consume). La tuberia sale de la lista de partes del dibujo
        (familia y diametro_nominal como en listar_catalogo_presion). Civil
        coloca el eje a cobertura_m bajo la superficie y anade los codos en los
        vertices. Despues se inspecciona: una sola componente conectada y, si se
        da cobertura_min_m (>= 0), cobertura por muestras cada paso_m. Simula por
        defecto (crea, inspecciona y aborta); al confirmar, si la inspeccion no
        cumple no se guarda nada. No calcula hidraulica.
        """
        if not confirmar: return ok({"error": "Operacion de escritura: requiere confirmar=True"})
        if bool(ruta) == bool(polilinea): return ok({"error": "Indique ruta o polilinea, una sola"})
        try: pts = json.loads(ruta) if ruta else None
        except ValueError as exc: return ok({"error": str(exc)})
        return call(ejecutar, dibujo, pid, accion="trazado", simular=simular, nombre=nombre, superficie=superficie, familia=familia, diametro_nominal=diametro_nominal,
                    cobertura_m=cobertura_m, cobertura_min_m=cobertura_min_m if cobertura_min_m >= 0 else None, ruta=pts, polilinea=polilinea or None,
                    lista_partes=lista_partes or None, capa=capa, codos_automaticos=codos_automaticos, paso_m=paso_m, timeout=600)

    @mcp.tool()
    def inspeccionar_red_presion(dibujo: str, pid: int, red: str, superficie: str = "", cobertura_min_m: float = -1.0, paso_m: float = 5.0) -> str:
        """Comprueba una red a presion existente sin depender de contrato: conectividad y cobertura por muestras.

        Conectividad: componentes conectados (1 = toda la red unida), extremos
        de tuberia sin pieza y bocas abiertas de accesorios y aparatos.
        Cobertura: cada paso_m sobre cada tuberia, cota de la superficie menos
        (eje + diametro exterior / 2), contra la superficie indicada o la de
        referencia de la red; con cobertura_min_m (>= 0) lista las muestras por
        debajo y dice si cumple (una muestra fuera de la superficie no cumple).
        Lectura sin cambios.
        """
        return call(ejecutar, dibujo, pid, accion="inspeccionar", red=red, superficie=superficie or None,
                    cobertura_min_m=cobertura_min_m if cobertura_min_m >= 0 else None, paso_m=paso_m)
