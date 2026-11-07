"""Corridor gutter drainage: inlet proposal, gravity pipe network and verification; immutable receipts.

Same transport as targets/tipologias: request file + SHA-256, one-shot native command
CDCRDDRENAJEV1 in the open Civil 3D process, receipt bound to the request. The hydraulic
design (rational flows, inlet spacing, Manning sizing) runs here in drenaje_calculo; the
native module only reads gutter feature lines and the parts catalog, creates the explicit
network it is given and verifies it against the stored contract.
"""
import hashlib, json, math, ntpath, time, uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
import puente_cliente as bridge
import drenaje_calculo as calc

MODULE = "cdcrd-drenaje"
COMMAND = "CDCRDDRENAJEV1"
ACCIONES = ("catalogo", "cuneta", "crear", "verificar")
KINDS = ("imbornal", "pozo", "salida")


class DrenajeError(RuntimeError):
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


def validar_catalogo(datos):
    out = {}
    if datos.get("lista_partes"): out["lista_partes"] = _texto(datos["lista_partes"], "lista_partes")
    return out


def validar_cuneta(datos):
    out = dict(corredor=_texto(datos.get("corredor"), "corredor"))
    if datos.get("codigo"): out["codigo"] = _texto(datos["codigo"], "codigo", 60)
    return out


def validar_propuesta(datos):
    return dict(intensidad_mm_h=_numero(datos.get("intensidad_mm_h"), "intensidad_mm_h", .1, 1000),
                espaciamiento_max_m=_numero(datos.get("espaciamiento_max_m", 60), "espaciamiento_max_m", 5, 500),
                ancho_aporte_m=_numero(datos.get("ancho_aporte_m", 8), "ancho_aporte_m", .1, 500),
                coeficiente_c=_numero(datos.get("coeficiente_c", .9), "coeficiente_c", .05, 1),
                lados=datos.get("lados", "ambos") if datos.get("lados", "ambos") in ("ambos", "izq", "der") else _texto(None, "lados"))


def validar_creacion(datos):
    """Explicit network as the native module expects it: structures with family/size and pipes with inverts."""
    out = dict(nombre=_texto(datos.get("nombre"), "nombre"), capa=_texto(datos.get("capa", "CDCRD-DRENAJE"), "capa"),
               pendiente_min=_numero(datos.get("pendiente_min", .005), "pendiente_min", .0005, .2),
               profundidad_min_m=_numero(datos.get("profundidad_min_m", 1.0), "profundidad_min_m", 0, 10),
               tolerancia_m=_numero(datos.get("tolerancia_m", .005), "tolerancia_m", 1e-6, .1))
    if datos.get("lista_partes"): out["lista_partes"] = _texto(datos["lista_partes"], "lista_partes")
    structures = datos.get("estructuras"); pipes = datos.get("tuberias")
    if not isinstance(structures, list) or not 1 <= len(structures) <= 200: raise ValueError("estructuras: lista de 1..200")
    if not isinstance(pipes, list) or not 1 <= len(pipes) <= 200: raise ValueError("tuberias: lista de 1..200")
    ids = set(); out_s = []
    for s in structures:
        if not isinstance(s, dict): raise ValueError("Cada estructura es un objeto")
        sid = _texto(s.get("id"), "id", 60)
        if sid in ids: raise ValueError("Estructura duplicada: " + sid)
        ids.add(sid)
        if s.get("tipo") not in KINDS: raise ValueError("tipo de estructura invalido: " + sid)
        xyz = calc._xyz("xyz de " + sid, s.get("xyz"))
        rim = _numero(s.get("rasante", xyz[2]), "rasante de " + sid, -1e5, 1e5); sump = _numero(s.get("cota_fondo"), "cota_fondo de " + sid, -1e5, 1e5)
        if sump >= rim or rim - sump > 30: raise ValueError("cota_fondo invalida en " + sid)
        row = dict(id=sid, tipo=s["tipo"], familia=_texto(s.get("familia"), "familia de " + sid), xyz=xyz, rasante=rim, cota_fondo=sump,
                   rotacion=_numero(s.get("rotacion", 0), "rotacion de " + sid, -2 * math.pi, 2 * math.pi))
        if s.get("tamanio"): row["tamanio"] = _texto(s["tamanio"], "tamanio de " + sid)
        out_s.append(row)
    if sum(1 for s in out_s if s["tipo"] == "salida") != 1: raise ValueError("Se requiere exactamente una estructura de salida")
    pids = set(); out_p = []
    for p in pipes:
        if not isinstance(p, dict): raise ValueError("Cada tuberia es un objeto")
        pid = _texto(p.get("id"), "id", 60)
        if pid in pids: raise ValueError("Tuberia duplicada: " + pid)
        pids.add(pid)
        a, b = p.get("desde"), p.get("hasta")
        if a not in ids or b not in ids or a == b: raise ValueError("Tuberia " + pid + " debe unir dos estructuras distintas")
        d = _numero(p.get("diametro_m"), "diametro_m de " + pid, .1, 3)
        z0 = _numero(p.get("cota_inicio"), "cota_inicio de " + pid, -1e5, 1e5); z1 = _numero(p.get("cota_fin"), "cota_fin de " + pid, -1e5, 1e5)
        if z1 > z0: raise ValueError("Tuberia " + pid + " no desciende")
        out_p.append(dict(id=pid, desde=a, hasta=b, familia=_texto(p.get("familia"), "familia de " + pid), diametro_m=d, cota_inicio=z0, cota_fin=z1))
    out["estructuras"] = out_s; out["tuberias"] = out_p
    return out


def ejecutar(dibujo, pid, *, accion, simular=True, timeout=180, **datos):
    if not ntpath.isabs(dibujo) or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("Ruta DWG absoluta y PID positivo requeridos")
    if accion not in ACCIONES or not isinstance(simular, bool):
        raise ValueError("Accion o simulacion invalida")
    if accion == "catalogo": datos = validar_catalogo(datos)
    elif accion == "cuneta": datos = validar_cuneta(datos)
    elif accion == "crear": datos = validar_creacion(datos)
    else: datos = dict(red=_texto(datos.get("red"), "red"))
    request = dict(datos, dibujo=dibujo, pid=pid, accion=accion, simular=simular,
                   vence_utc=(datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat())
    info = bridge.llamar("doc.info")
    if not info.get("civil3d") or ntpath.normcase(info["dibujo"]) != ntpath.normcase(dibujo) or info["insunits"] != 6:
        raise ValueError("Documento Civil o unidades distintos a lo esperado")
    if bridge.llamar("diag.dialogos")["modal_abierto"] or bridge.llamar("diag.cola")["activas"]:
        raise RuntimeError("Civil ocupado; revisar cola/dialogo antes de enviar")
    root = Path(dibujo).parent
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
        raise DrenajeError("Despacho incierto: consultar recibo y cola; no reintentar. " + str(exc), pending) from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("id") != key or result.get("sha256") != digest or result.get("module") != MODULE or result.get("pid") != pid:
                raise DrenajeError("Recibo no corresponde a la solicitud/sesion; no reintentar", pending)
            if not result.get("ok"):
                raise DrenajeError(result.get("error", "Fallo nativo"), result)
            return result
        time.sleep(.1)
    raise DrenajeError("Sin recibo final. Verificar modulo cargado, cola y archivo indicado; no reintentar escrituras", pending)


def proponer(dibujo, pid, corredor, **opciones):
    """Native gutter read followed by the pure inlet proposal."""
    codigo = opciones.pop("codigo", "") or ""
    props = validar_propuesta(opciones)
    receipt = ejecutar(dibujo, pid, accion="cuneta", corredor=corredor, codigo=codigo or None)
    cuneta = receipt["result"]
    proposal = calc.proponer_imbornales(cuneta["cunetas"], **props)
    return dict(corredor=cuneta["corredor"], nombre=cuneta["nombre"], codigo=cuneta["codigo"], lineas=cuneta["lineas"], puntos=cuneta["puntos"],
                codigos_disponibles=cuneta["codigos_disponibles"], recibo=dict(id=receipt["id"], version=receipt.get("version")), propuesta=proposal)


def disenar(nodos, familias, **parametros):
    """Pure design plus family/size assignment per node kind, ready for the native `crear` action."""
    design = calc.disenar_red(nodos, **parametros)
    structures = []
    for s in design["estructuras"]:
        row = dict(s, familia=familias[s["tipo"]]["familia"])
        if familias[s["tipo"]].get("tamanio"): row["tamanio"] = familias[s["tipo"]]["tamanio"]
        structures.append(row)
    pipes = [dict(p, familia=familias["tuberia"]["familia"]) for p in design["tuberias"]]
    return design, structures, pipes


def registrar(mcp, ok):
    def call(fn, *args, **kwargs):
        try: return ok(fn(*args, **kwargs))
        except DrenajeError as exc: return ok({"error": str(exc), "receipt": exc.receipt})
        except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc: return ok({"error": str(exc)})

    @mcp.tool()
    def listar_catalogo_drenaje(dibujo: str, pid: int, lista_partes: str = "") -> str:
        """Lista las listas de partes del dibujo con sus familias y tamanios en metros, y las redes existentes.

        Para cada familia de tuberia: nombre, material y diametro interior de cada
        tamanio; para cada estructura: dimensiones interiores y altura rasante-fondo.
        Sirve para elegir familia_tuberia, familia_imbornal, familia_pozo y los
        diametros_mm que crear_red_drenaje puede usar. Lectura sin cambios.
        """
        return call(ejecutar, dibujo, pid, accion="catalogo", lista_partes=lista_partes or None)

    @mcp.tool()
    def proponer_imbornales_corredor(dibujo: str, pid: int, corredor: str, intensidad_mm_h: float, espaciamiento_max_m: float = 60,
                                     ancho_aporte_m: float = 8, coeficiente_c: float = .9, codigo: str = "Flowline_Gutter", lados: str = "ambos") -> str:
        """Lee las lineas de cuneta del corredor, propone imbornales y calcula su caudal por el metodo racional.

        Toma las feature lines de la baseline principal con el codigo dado
        (Flowline_Gutter en la paleta metrica), una por lado y tramo de bordillo,
        localiza crestas y puntos bajos de la rasante de cuneta y coloca un imbornal
        en cada punto bajo mas los intermedios necesarios para que ningun tramo de
        cuneta supere espaciamiento_max_m (reparto uniforme desde la cresta). El
        aporte de cada imbornal es la longitud de cuneta que drena hacia el (desde el
        imbornal o cresta aguas arriba) por ancho_aporte_m; Q = C i A / 3.6e6 con i en
        mm/h. Devuelve cunetas, crestas, puntos bajos e imbornales con estacion, XYZ,
        aportes y caudal, listos para armar los nodos de crear_red_drenaje. Lectura sin
        cambios; exige corredor reconstruido. No modela tiempo de concentracion ni
        capacidad de reja: el caudal es el aporte de calculo, no la captacion real.
        """
        return call(proponer, dibujo, pid, corredor, intensidad_mm_h=intensidad_mm_h, espaciamiento_max_m=espaciamiento_max_m,
                    ancho_aporte_m=ancho_aporte_m, coeficiente_c=coeficiente_c, codigo=codigo, lados=lados)

    @mcp.tool()
    def crear_red_drenaje(dibujo: str, pid: int, nombre: str, nodos: str, familia_tuberia: str, familia_imbornal: str, familia_pozo: str,
                          familia_salida: str = "", tamanio_imbornal: str = "", tamanio_pozo: str = "", tamanio_salida: str = "", lista_partes: str = "",
                          diametros_mm: str = "[300, 375, 450, 525, 600]", pendiente_min: float = .005, profundidad_min_m: float = 1.0,
                          n_manning: float = .013, sumidero_m: float = 0.0, capa: str = "CDCRD-DRENAJE", tolerancia_m: float = .005,
                          simular: bool = True, confirmar: bool = False) -> str:
        """Dimensiona y crea una red de tuberias de gravedad (PipeNetwork) con el catalogo metrico instalado.

        nodos JSON [{id, tipo (imbornal|pozo|salida), xyz [x, y, rasante], q_m3_s, hacia}]:
        un arbol que drena a exactamente una salida (estructura de retencion); los
        imbornales traen el caudal de proponer_imbornales_corredor y los pozos van
        en los cambios de alineacion. Diseno aguas arriba hacia abajo: radier de
        salida = min(rasante - profundidad_min_m - D, radieres entrantes); radier
        de llegada con pendiente_min o mas si la rasante de llegada lo exige;
        diametro = el menor del catalogo (nunca menor que uno entrante) cuya
        capacidad a seccion llena por Manning cubre el caudal acumulado. Luego crea
        la red nativa: estructuras por tipo con la familia/tamanio indicados (rasante
        y fondo explicitos), tuberias con familia_tuberia y el tamanio del catalogo
        cuyo diametro interior coincide, conectadas y en la capa propia; verifica
        posiciones, cotas, pendientes, diametros y conexiones y guarda el contrato
        CDCRD_DRENAJE_V1 en la red. Simula por defecto (crea y aborta). Las familias
        aceptan nombre exacto o fragmento unico (ver listar_catalogo_drenaje).
        profundidad_min_m es la profundidad minima sobre la clave. No aplica reglas
        de Civil ni calcula lineas de energia.
        """
        if not confirmar: return ok({"error": "Operacion de escritura: requiere confirmar=True"})
        try:
            diam = json.loads(diametros_mm)
            familias = dict(tuberia=dict(familia=familia_tuberia), imbornal=dict(familia=familia_imbornal, tamanio=tamanio_imbornal),
                            pozo=dict(familia=familia_pozo, tamanio=tamanio_pozo), salida=dict(familia=familia_salida or familia_pozo, tamanio=tamanio_salida or tamanio_pozo))
            design, structures, pipes = disenar(nodos, familias, diametros_mm=diam, pendiente_min=pendiente_min, profundidad_min_m=profundidad_min_m,
                                                n_manning=n_manning, sumidero_m=sumidero_m)
        except (ValueError, TypeError, KeyError) as exc: return ok({"error": str(exc)})
        def run():
            receipt = ejecutar(dibujo, pid, accion="crear", simular=simular, nombre=nombre, capa=capa, lista_partes=lista_partes or None,
                               pendiente_min=pendiente_min, profundidad_min_m=profundidad_min_m, tolerancia_m=tolerancia_m, estructuras=structures, tuberias=pipes)
            return dict(diseno=design, recibo=receipt)
        return call(run)

    @mcp.tool()
    def verificar_red_drenaje(dibujo: str, pid: int, red: str) -> str:
        """Relee el contrato CDCRD_DRENAJE_V1 de la red y comprueba tramos, cotas, pendientes, diametros, conexiones y capa."""
        return call(ejecutar, dibujo, pid, accion="verificar", red=red)
