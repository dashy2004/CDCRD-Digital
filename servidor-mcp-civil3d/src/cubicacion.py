"""Pavement thicknesses, Datum surface and corridor volumes; immutable receipts.

Same transport as targets/tipologias: request file + SHA-256, one-shot native
command CDCRDCUBICACIONV1 in the open Civil 3D process, receipt bound to the request.
A committed write that changes assemblies leaves the corridor out of date once the
native command ends, so the wrapper then sends a second request, `reconstruir`,
which rebuilds corridor and corridor surfaces in a command of its own.
"""
import hashlib, json, math, ntpath, re, time, uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
import puente_cliente as bridge

MODULE = "cdcrd-cubicacion"
COMMAND = "CDCRDCUBICACIONV1"
CAPAS = ("Pave1Depth", "Pave2Depth", "BaseDepth", "SubBaseDepth")
CODIGOS = ("Pave1", "Pave2", "Base", "SubBase")
ACCIONES = ("espesores", "datum", "cubicacion", "reconstruir", "leer")


class CubicacionError(RuntimeError):
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


def _lista_textos(value, key, max_len=200):
    rows = json.loads(value) if isinstance(value, str) else value
    if rows is None: return []
    if not isinstance(rows, list) or len(rows) > max_len: raise ValueError(f"Lista de hasta {max_len} textos: {key}")
    out = [_texto(r, key) for r in rows]
    if len({r.casefold() for r in out}) != len(out): raise ValueError("Textos repetidos en " + key)
    return out


def validar_espesores(value):
    """{clave: metros}: 1..12 claves de parametro (Pave1Depth, ...) entre 1 mm y 5 m."""
    rows = json.loads(value) if isinstance(value, str) else value
    if not isinstance(rows, dict) or not 1 <= len(rows) <= 12: raise ValueError("espesores: objeto {parametro: metros} con 1..12 claves")
    out = {}
    for key, metros in rows.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,39}", key): raise ValueError("Clave de parametro invalida: " + str(key))
        out[key] = _numero(metros, key, .001, 5)
    if len({k.casefold() for k in out}) != len(out): raise ValueError("Claves de parametro repetidas")
    return out


def _opcional(datos, key, max_len=200):
    """Optional text: absent when None or empty string; anything else must be a valid text."""
    value = datos.get(key)
    return None if value is None or value == "" else _texto(value, key, max_len)


def validar_accion_espesores(datos):
    return dict(corredor=_texto(datos.get("corredor"), "corredor"), espesores=validar_espesores(datos.get("espesores")),
                subensamblajes=_lista_textos(datos.get("subensamblajes"), "subensamblajes"),
                regiones=_lista_textos(datos.get("regiones"), "regiones"),
                tolerancia_m=_numero(datos.get("tolerancia_m", .001), "tolerancia_m", 1e-6, .1))


def validar_accion_datum(datos):
    out = dict(corredor=_texto(datos.get("corredor"), "corredor"), codigo=_opcional(datos, "codigo", 60) or "Datum")
    nombre = _opcional(datos, "nombre")
    if nombre: out["nombre"] = nombre
    return out


def validar_accion_cubicacion(datos):
    out = dict(corredor=_texto(datos.get("corredor"), "corredor"), terreno=_texto(datos.get("terreno"), "terreno"),
               codigos=_lista_textos(datos.get("codigos"), "codigos", 20) or list(CODIGOS),
               factor_corte=_numero(datos.get("factor_corte", 1), "factor_corte", .1, 10),
               factor_relleno=_numero(datos.get("factor_relleno", 1), "factor_relleno", .1, 10))
    for key in ("datum", "nombre_volumen"):
        value = _opcional(datos, key)
        if value: out[key] = value
    if out["terreno"].casefold() == out.get("datum", "").casefold(): raise ValueError("terreno y datum deben ser superficies distintas")
    return out


def _despachar(dibujo, pid, request, timeout):
    """One immutable request, one native command, one receipt bound to it."""
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
        raise CubicacionError("Despacho incierto: consultar recibo y cola; no reintentar. " + str(exc), pending) from exc
    deadline = time.monotonic() + timeout
    while True:
        if result_path.exists():
            # An existing receipt is always read, even past the deadline: binding and outcome come from it, never from a guess.
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if (not isinstance(result, dict) or result.get("id") != key or result.get("sha256") != digest or result.get("module") != MODULE
                    or result.get("pid") != pid or not isinstance(result.get("result"), (dict, type(None)))):
                raise CubicacionError("Recibo no corresponde a la solicitud/sesion; no reintentar", pending)
            if not result.get("ok"):
                raise CubicacionError(result.get("error", "Fallo nativo"), result)
            return result
        if time.monotonic() >= deadline: break
        time.sleep(.1)
    raise CubicacionError("Sin recibo final. Verificar modulo cargado, cola y archivo indicado; no reintentar escrituras", pending)


ESPERA_COLA_S = 60


def _esperar_cola():
    """The second request must not queue behind a modal or a command still running."""
    deadline = time.monotonic() + ESPERA_COLA_S
    while True:
        busy = bridge.llamar("diag.dialogos").get("modal_abierto") or bridge.llamar("diag.cola").get("activas")
        if not busy: return
        if time.monotonic() >= deadline: raise RuntimeError("Civil sigue ocupado tras la escritura confirmada; revisar cola/dialogo")
        time.sleep(.5)


def ejecutar(dibujo, pid, *, accion, simular=True, timeout=300, **datos):
    if not ntpath.isabs(dibujo) or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("Ruta DWG absoluta y PID positivo requeridos")
    if accion not in ACCIONES or not isinstance(simular, bool):
        raise ValueError("Accion o simulacion invalida")
    if accion == "espesores": datos = validar_accion_espesores(datos)
    elif accion == "datum": datos = validar_accion_datum(datos)
    elif accion == "cubicacion": datos = validar_accion_cubicacion(datos)
    else: datos = dict(corredor=_texto(datos.get("corredor"), "corredor"))
    info = bridge.llamar("doc.info") or {}
    if not info.get("civil3d") or ntpath.normcase(info.get("dibujo") or "") != ntpath.normcase(dibujo) or info.get("insunits") != 6:
        raise ValueError("Documento Civil o unidades distintos a lo esperado")
    if bridge.llamar("diag.dialogos").get("modal_abierto") or bridge.llamar("diag.cola").get("activas"):
        raise RuntimeError("Civil ocupado; revisar cola/dialogo antes de enviar")

    def request(action, payload, sim):
        return dict(payload, dibujo=dibujo, pid=pid, accion=action, simular=sim,
                    vence_utc=(datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat())
    result = _despachar(dibujo, pid, request(accion, datos, simular), timeout)
    if accion not in ("espesores", "datum") or not result.get("committed"):
        return result
    # Assemblies or corridor surfaces changed: Civil flags the corridor out of date when the
    # command ends. Rebuild in a command of its own so the drawing can be saved up to date.
    try:
        _esperar_cola()
        result["reconstruccion"] = _despachar(dibujo, pid, request("reconstruir", dict(corredor=datos["corredor"]), False), timeout)
    except Exception as exc:
        receipt = exc.receipt if isinstance(exc, CubicacionError) else None
        raise CubicacionError("Aplicado y confirmado, pero la reconstruccion en comando propio fallo: " + str(exc),
                              dict(aplicado=result, reconstruccion=receipt)) from exc
    return result


def registrar(mcp, ok):
    def call(dibujo, pid, **args):
        try: return ok(ejecutar(dibujo, pid, **args))
        except CubicacionError as exc: return ok({"error": str(exc), "receipt": exc.receipt})
        except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc: return ok({"error": str(exc)})

    def lista(value):
        try: return json.loads(value) if value else []
        except (ValueError, TypeError) as exc: raise ValueError("JSON invalido: " + str(exc)) from exc

    @mcp.tool()
    def asignar_espesores_pavimento(dibujo: str, pid: int, corredor: str, espesores: str, subensamblajes: str = "[]",
                                    regiones: str = "[]", tolerancia_m: float = .001,
                                    simular: bool = True, confirmar: bool = False) -> str:
        """Asigna espesores de capa a los carriles de todos los ensamblajes de un corredor.

        espesores JSON {"Pave1Depth": 0.075, "Pave2Depth": 0.05, "BaseDepth": 0.25,
        "SubBaseDepth": 0.35} en metros; cualquier parametro doble que exista en
        el carril. Carriles: subensamblajes con Width, DefaultSlope y Pave1Depth
        (LaneSuperelevationAOR y equivalentes) de los ensamblajes usados por las
        regiones del corredor (o solo por `regiones`); `subensamblajes` los fija
        por nombre o handle. Lee los valores previos, escribe, relee cada valor y
        mide en la geometria propia de cada carril el espesor vertical de las
        formas Pave1/Pave2/Base/SubBase en sus dos bordes (tolerancia_m). Al
        confirmar, reconstruye corredor y superficies en una segunda transaccion
        y repite la medida sobre las secciones aplicadas; dentro de la misma
        transaccion el corredor reconstruido aun usa los espesores anteriores.
        Despues envia `reconstruir` en comando propio (el corredor queda fuera de
        fecha al terminar el comando). Rechaza ensamblajes compartidos con otro
        corredor. Guarda el contrato CDCRD_CUBICACION_V1. Simula por defecto;
        confirmar=True es obligatorio tambien para simular (envia un comando).
        """
        if not confirmar: return ok({"error": "Operacion de escritura: requiere confirmar=True"})
        try: thick, subs, regs = json.loads(espesores), lista(subensamblajes), lista(regiones)
        except (ValueError, TypeError) as exc: return ok({"error": str(exc)})
        return call(dibujo, pid, accion="espesores", corredor=corredor, espesores=thick, subensamblajes=subs,
                    regiones=regs, tolerancia_m=tolerancia_m, simular=simular)

    @mcp.tool()
    def crear_datum_corredor(dibujo: str, pid: int, corredor: str, nombre: str = "", codigo: str = "Datum",
                             simular: bool = True, confirmar: bool = False) -> str:
        """Crea la superficie Datum del corredor (enlace Datum, contorno por extension).

        Agrega una superficie de corredor `nombre` (por defecto <corredor>_Datum)
        con el codigo de enlace `codigo` como linea de rotura, correccion de
        voladizo por enlaces inferiores y contorno por extension del corredor;
        reconstruye corredor y superficie y exige triangulos. Rechaza nombres
        existentes y corredores que ya tengan una superficie con ese codigo.
        Guarda el contrato y, al confirmar, reconstruye en comando propio.
        Simula por defecto.
        """
        if not confirmar: return ok({"error": "Operacion de escritura: requiere confirmar=True"})
        return call(dibujo, pid, accion="datum", corredor=corredor, nombre=nombre, codigo=codigo, simular=simular)

    @mcp.tool()
    def cubicar_corredor(dibujo: str, pid: int, corredor: str, terreno: str, datum: str = "", codigos: str = "[]",
                         nombre_volumen: str = "", factor_corte: float = 1, factor_relleno: float = 1,
                         simular: bool = True, confirmar: bool = False) -> str:
        """Corte/relleno terreno-Datum y volumenes por capa de un corredor reconstruido.

        Crea una TinVolumeSurface entre `terreno` (base) y `datum` (comparacion;
        por defecto la Datum del contrato o la unica superficie del corredor con
        enlace Datum) y lee corte, relleno y neto brutos y ajustados. Por capa,
        suma las areas de las formas con cada codigo (Pave1, Pave2, Base,
        SubBase por defecto) en cada estacion aplicada y las integra por areas
        medias dentro de cada region de cada baseline; los huecos entre regiones
        no aportan. Devuelve totales, por baseline/region y por estacion, y el
        inventario de espesores vigentes. simular=True calcula y aborta sin
        dejar objetos; simular=False conserva la superficie de volumen y escribe
        el resultado en el contrato CDCRD_CUBICACION_V1 del corredor.
        """
        if not confirmar: return ok({"error": "Operacion de escritura: requiere confirmar=True"})
        try: codes = lista(codigos)
        except ValueError as exc: return ok({"error": str(exc)})
        return call(dibujo, pid, accion="cubicacion", corredor=corredor, terreno=terreno, datum=datum, codigos=codes,
                    nombre_volumen=nombre_volumen, factor_corte=factor_corte, factor_relleno=factor_relleno, simular=simular)
