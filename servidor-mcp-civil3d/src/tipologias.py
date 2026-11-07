"""Corridor edge classification and per-stretch palette typologies; immutable receipts.

Same transport as targets/multibaseline: request file + SHA-256, one-shot native
command CDCRDTIPOLOGIASV1 in the open Civil 3D process, receipt bound to the request.
"""
import hashlib, json, math, ntpath, time, uuid
from pathlib import Path
from datetime import datetime, timedelta, timezone
import puente_cliente as bridge

KINDS = ("LR", "L", "R", "-", "talud")
MODULE = "cdcrd-tipologias"
COMMAND = "CDCRDTIPOLOGIASV1"


class TipologiaError(RuntimeError):
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


def _lista_textos(value, key):
    rows = json.loads(value) if isinstance(value, str) else value
    if rows is None: return []
    if not isinstance(rows, list) or len(rows) > 200: raise ValueError("Lista de hasta 200 textos: " + key)
    return [_texto(r, key) for r in rows]


def validar_segmentos(value):
    rows = json.loads(value) if isinstance(value, str) else value
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100: raise ValueError("segmentos: lista de 1..100 tramos [inicio, fin, tipo]")
    out = []
    for i, row in enumerate(rows):
        if not isinstance(row, (list, tuple)) or len(row) != 3: raise ValueError("Cada tramo es [inicio, fin, tipo]")
        start, end, kind = row
        _numero(start, "inicio", -1e7, 1e7); _numero(end, "fin", -1e7, 1e7)
        if kind not in KINDS: raise ValueError("tipo de tramo debe ser LR, L, R, - o talud")
        if end - start < .01: raise ValueError(f"Tramo {i + 1} vacio")
        if out and abs(start - out[-1][1]) > 1e-6: raise ValueError(f"Tramos discontinuos entre {i} y {i + 1}")
        out.append([start, end, kind])
    return out


def validar_clasificacion(datos):
    out = dict(corredor=_texto(datos.get("corredor"), "corredor"),
               sonda_m=_numero(datos.get("sonda_m", 1.0), "sonda_m", .05, 10),
               union_min_m=_numero(datos.get("union_min_m", 2.0), "union_min_m", 0, 100),
               libre_min_m=_numero(datos.get("libre_min_m", 5.0), "libre_min_m", 0, 100),
               superficies_pavimento=_lista_textos(datos.get("superficies_pavimento"), "superficies_pavimento"),
               superficies_excluidas=_lista_textos(datos.get("superficies_excluidas"), "superficies_excluidas"))
    if datos.get("codigo_borde"): out["codigo_borde"] = _texto(datos["codigo_borde"], "codigo_borde", 60)
    return out


def validar_aplicacion(datos):
    out = dict(corredor=_texto(datos.get("corredor"), "corredor"), segmentos=validar_segmentos(datos.get("segmentos")),
               separacion_m=_numero(datos.get("separacion_m", 30), "separacion_m", 1, 1000),
               tolerancia_m=_numero(datos.get("tolerancia_m", .005), "tolerancia_m", 1e-6, .1))
    for key in ("biblioteca", "ensamblaje_carriles", "ensamblaje_bordillo", "subensamblaje_bordillo", "ensamblaje_talud",
                "superficie_terreno", "capa", "codigo_borde"):
        if datos.get(key): out[key] = _texto(datos[key], key, 400 if key == "biblioteca" else 200)
    if any(s[2] == "talud" for s in out["segmentos"]) and "superficie_terreno" not in out:
        raise ValueError("Los tramos talud requieren superficie_terreno")
    origen = datos.get("origen")
    if origen:
        xyz = json.loads(origen) if isinstance(origen, str) else origen
        if not isinstance(xyz, list) or len(xyz) != 3: raise ValueError("origen requiere XYZ")
        out["origen"] = [_numero(v, "origen", -1e8, 1e8) for v in xyz]
    return out


def ejecutar(dibujo, pid, *, accion, simular=True, timeout=180, **datos):
    if not ntpath.isabs(dibujo) or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("Ruta DWG absoluta y PID positivo requeridos")
    if accion not in ("clasificar", "aplicar", "reconstruir", "verificar") or not isinstance(simular, bool):
        raise ValueError("Accion o simulacion invalida")
    if accion == "clasificar": datos = validar_clasificacion(datos)
    elif accion == "aplicar": datos = validar_aplicacion(datos)
    else: datos = dict(corredor=_texto(datos.get("corredor"), "corredor"))
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
        raise TipologiaError("Despacho incierto: consultar recibo y cola; no reintentar. " + str(exc), pending) from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("id") != key or result.get("sha256") != digest or result.get("module") != MODULE or result.get("pid") != pid:
                raise TipologiaError("Recibo no corresponde a la solicitud/sesion; no reintentar", pending)
            if not result.get("ok"):
                raise TipologiaError(result.get("error", "Fallo nativo"), result)
            return result
        time.sleep(.1)
    raise TipologiaError("Sin recibo final. Verificar modulo cargado, cola y archivo indicado; no reintentar escrituras", pending)


def registrar(mcp, ok):
    def call(dibujo, pid, **args):
        try: return ok(ejecutar(dibujo, pid, **args))
        except TipologiaError as exc: return ok({"error": str(exc), "receipt": exc.receipt})
        except (ValueError, TypeError, OSError, RuntimeError) as exc: return ok({"error": str(exc)})

    @mcp.tool()
    def clasificar_bordes_corredor(dibujo: str, pid: int, corredor: str, sonda_m: float = 1.0,
                                   superficies_pavimento: str = "[]", superficies_excluidas: str = "[]",
                                   codigo_borde: str = "", union_min_m: float = 2.0, libre_min_m: float = 5.0) -> str:
        """Clasifica cada borde de calzada como libre o union y propone tramos de tipologia.

        En cada estacion aplicada toma un punto a sonda_m fuera del borde (ETW o
        Edge) y comprueba si cae sobre otra superficie de pavimento vigente: por
        defecto las Top de los demas corredores, o la lista superficies_pavimento.
        Uniones mas cortas que union_min_m se consideran libres y tramos libres
        mas cortos que libre_min_m se consideran union. Devuelve muestras por
        estacion, inventario de la region (piezas, objetivos, transiciones) y
        segmentos [inicio, fin, tipo] listos para aplicar_tipologia_por_tramo.
        Lectura sin cambios; exige corredor reconstruido con una sola baseline.
        """
        try: paved, excluded = json.loads(superficies_pavimento), json.loads(superficies_excluidas)
        except (ValueError, TypeError) as exc: return ok({"error": str(exc)})
        return call(dibujo, pid, accion="clasificar", corredor=corredor, sonda_m=sonda_m, superficies_pavimento=paved,
                    superficies_excluidas=excluded, codigo_borde=codigo_borde, union_min_m=union_min_m, libre_min_m=libre_min_m)

    @mcp.tool()
    def aplicar_tipologia_por_tramo(dibujo: str, pid: int, corredor: str, segmentos: str, superficie_terreno: str = "",
                                    biblioteca: str = "", ensamblaje_carriles: str = "", ensamblaje_bordillo: str = "",
                                    subensamblaje_bordillo: str = "", ensamblaje_talud: str = "", origen: str = "",
                                    separacion_m: float = 30, capa: str = "", codigo_borde: str = "", tolerancia_m: float = .005,
                                    simular: bool = True, confirmar: bool = False) -> str:
        """Divide la unica region del corredor por tramos y asigna variantes de paleta.

        segmentos JSON [[inicio, fin, tipo], ...] contiguos que cubren la region;
        tipo LR/L/R (bordillo-cuneta en esos lados), - (union abierta) o talud
        (ensamblaje completo con encuentro al terreno; exige superficie_terreno).
        Importa de la biblioteca metrica instalada (o biblioteca) el ensamblaje de
        carriles, iguala ancho, bombeo y capas con los carriles originales, copia
        las bandas y el bordillo con parametros verificados, remapea todos los
        objetivos (falla si alguno queda sin equivalente), recorta transiciones
        por tramo y cambia el Top a contorno por extension. Verifica bordes contra
        la region original, bordillos por tramo y taludes contra el terreno; guarda
        el contrato CDCRD_TIPOLOGIAS_V1. Solo corredores con una baseline, una
        region (carriles LaneSuperelevationAOR y bandas opcionales) y un Top.
        Simula por defecto; no reemplaza una tipologia ya aplicada.
        """
        if not confirmar: return ok({"error": "Operacion de escritura: requiere confirmar=True"})
        try: segs = json.loads(segmentos)
        except (ValueError, TypeError) as exc: return ok({"error": str(exc)})
        return call(dibujo, pid, accion="aplicar", corredor=corredor, segmentos=segs, superficie_terreno=superficie_terreno,
                    biblioteca=biblioteca, ensamblaje_carriles=ensamblaje_carriles, ensamblaje_bordillo=ensamblaje_bordillo,
                    subensamblaje_bordillo=subensamblaje_bordillo, ensamblaje_talud=ensamblaje_talud, origen=origen,
                    separacion_m=separacion_m, capa=capa, codigo_borde=codigo_borde, tolerancia_m=tolerancia_m, simular=simular)

    @mcp.tool()
    def reconstruir_tipologia_por_tramo(dibujo: str, pid: int, corredor: str, confirmar: bool = False) -> str:
        """Reconstruye corredor y Top de una tipologia aplicada y repite la verificacion.

        Civil deja el corredor fuera de fecha al terminar el comando que aplico la
        tipologia; esta reconstruccion en comando propio lo deja al dia antes de
        guardar. Escritura confirmada; no cambia geometria ni contrato.
        """
        if not confirmar: return ok({"error": "Operacion de escritura: requiere confirmar=True"})
        return call(dibujo, pid, accion="reconstruir", corredor=corredor, simular=False)

    @mcp.tool()
    def verificar_tipologia_por_tramo(dibujo: str, pid: int, corredor: str) -> str:
        """Relee el contrato CDCRD_TIPOLOGIAS_V1 y comprueba regiones, bordillos y taludes aplicados."""
        return call(dibujo, pid, accion="verificar", corredor=corredor)
