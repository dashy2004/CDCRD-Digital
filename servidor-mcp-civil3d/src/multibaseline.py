"""Multi-baseline corridor commands in the already open Civil process; immutable receipts."""
import hashlib
import json
import math
import ntpath
from pathlib import Path
import time
import uuid
from datetime import datetime, timedelta, timezone
import puente_cliente as bridge


class MultiError(RuntimeError):
    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt = receipt


def validar_baselines(value):
    rows = json.loads(value) if isinstance(value, str) else value
    if not isinstance(rows, list) or not 1 <= len(rows) <= 20:
        raise ValueError("1..20 baselines requeridas")
    names, regions, budget = set(), set(), 0
    def text(row, key):
        v = row.get(key)
        if not isinstance(v, str) or not v.strip() or len(v) > 200 or any(ord(c) < 32 for c in v):
            raise ValueError("Texto requerido: " + key)
        return v
    def number(v):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError("Numero finito requerido")
        return v
    for b in rows:
        if not isinstance(b, dict): raise ValueError("Baseline debe ser objeto")
        name = text(b, "nombre").casefold()
        if name in names: raise ValueError("Baseline duplicada")
        names.add(name)
        text(b, "alineamiento"); text(b, "perfil")
        rr = b.get("regiones")
        if not isinstance(rr, list) or not 1 <= len(rr) <= 100: raise ValueError("Regiones requeridas")
        previous = -math.inf
        for r in rr:
            if not isinstance(r, dict): raise ValueError("Region debe ser objeto")
            rn = text(r, "nombre").casefold()
            if rn in regions or len(regions) >= 100: raise ValueError("Hasta 100 regiones unicas")
            regions.add(rn); text(r, "ensamblaje")
            if r.get("superficie_objetivo") is not None: text(r, "superficie_objetivo")
            start, end, freq = [number(r.get(k)) for k in ("inicio", "fin", "frecuencia")]
            if max(abs(start), abs(end)) > 1e7 or end-start < .01 or not .1 <= freq <= 1000 or (end-start)/freq > 1000 or start < previous:
                raise ValueError("Intervalo/frecuencia invalido o regiones solapadas")
            extra = r.get("estaciones_extra")
            if not isinstance(extra, list) or len(extra) > 500: raise ValueError("Hasta 500 estaciones_extra")
            extra = [number(v) for v in extra]
            if any(v < start or v > end for v in extra) or any(b-a <= 1e-6 for a,b in zip(extra, extra[1:])):
                raise ValueError("Estaciones extra ordenadas, unicas y dentro de region")
            budget += math.ceil((end-start)/freq) + len(extra) + 2
            if budget > 20000: raise ValueError("Presupuesto de estaciones excedido")
            previous = end
    return rows


def ejecutar(dibujo, pid, *, accion, simular=True, timeout=60, **datos):
    if not ntpath.isabs(dibujo) or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("Ruta DWG absoluta y PID positivo requeridos")
    if accion not in ("crear", "leer", "secciones") or not isinstance(simular, bool):
        raise ValueError("Accion o simulacion invalida")
    if accion == "crear": datos["baselines"] = validar_baselines(datos.get("baselines"))
    request = dict(datos, dibujo=dibujo, pid=pid, accion=accion, simular=simular,
                   vence_utc=(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat())
    info = bridge.llamar("doc.info")
    if not info.get("civil3d") or ntpath.normcase(info["dibujo"]) != ntpath.normcase(dibujo) or info["insunits"] != 6:
        raise ValueError("Documento Civil o unidades distintos a lo esperado")
    if bridge.llamar("diag.dialogos")["modal_abierto"] or bridge.llamar("diag.cola")["activas"]:
        raise RuntimeError("Civil ocupado; revisar cola/dialogo antes de enviar")
    root = Path(dibujo).parent
    key = uuid.uuid4().hex
    data = json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    request_path = root / ("cdcrd-corredores-" + key + ".request.json")
    result_path = root / ("cdcrd-corredores-" + key + ".result.json")
    with request_path.open("xb") as file:
        file.write(data)
    pending = {"id": key, "sha256": digest, "receipt_path": str(result_path), "estado": "desconocido"}
    try:
        bridge.llamar_con_aprobacion("cmd.run", {"linea": f"CDCRDCORREDORESV4\n{key}\n{digest}\n"})
    except Exception as exc:
        raise MultiError("Despacho incierto: consultar recibo y cola; no reintentar. " + str(exc), pending) from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("id") != key or result.get("sha256") != digest or result.get("module") != "cdcrd-corredores" or result.get("pid") != pid:
                raise MultiError("Recibo no corresponde a la solicitud/sesion; no reintentar", pending)
            if not result.get("ok"):
                raise MultiError(result.get("error", "Fallo nativo"), result)
            return result
        time.sleep(.1)
    raise MultiError("Sin recibo final. Verificar modulo cargado, cola y archivo indicado; no reintentar escrituras", pending)


def registrar(mcp, ok):
    def call(dibujo, pid, **args):
        try: return ok(ejecutar(dibujo, pid, **args))
        except MultiError as exc: return ok({"error": str(exc), "receipt": exc.receipt})
        except (ValueError, TypeError, OSError, RuntimeError) as exc: return ok({"error": str(exc)})

    @mcp.tool()
    def crear_corredor_multibaseline(dibujo: str, pid: int, nombre: str, baselines: str,
                                    capa: str = "CDX-MULTIBASELINE", simular: bool = True, confirmar: bool = False) -> str:
        """Crea corredor y Top con limites de extensiones, sin abrir otra instancia.

        baselines JSON: [{nombre,alineamiento,perfil,regiones:[{nombre,ensamblaje,
        superficie_objetivo (TIN o null),inicio,fin,frecuencia,estaciones_extra:[]}]}].
        Ejes distintos, locales, sin ecuaciones. Regiones ordenadas, sin solapar;
        permite contiguas y huecos. Metros, maximo 20 baselines/100 regiones.
        Requiere modulo Cdcrd.Corredores.V4; no modifica corredores existentes.
        Simula por defecto. Ante timeout consultar recibo y cola, sin reintentar.
        """
        if not confirmar: return ok({"error": "Operacion de escritura: requiere confirmar=True"})
        return call(dibujo, pid, accion="crear", nombre=nombre, baselines=baselines, capa=capa, simular=simular)

    @mcp.tool()
    def leer_corredor_multibaseline(dibujo: str, pid: int, corredor: str) -> str:
        """Verifica contrato propio, estaciones por region, XYZ, targets y Top nativos."""
        return call(dibujo, pid, accion="leer", corredor=corredor)

    @mcp.tool()
    def crear_secciones_multibaseline(dibujo: str, pid: int, corredor: str, baseline: str,
                                     nombre: str, estaciones: str, semiancho: float, origen: str,
                                     cota_min: float, cota_max: float, capa: str = "CDX-MULTI-SECTIONS",
                                     simular: bool = True, confirmar: bool = False) -> str:
        """Secciones nativas H=V sobre una baseline explicita y su Top.

        estaciones y origen son listas JSON (origen XYZ). Requiere estaciones
        aplicadas; rechaza huecos y limites compartidos entre regiones.
        """
        if not confirmar: return ok({"error": "Operacion de escritura: requiere confirmar=True"})
        try:
            stations, xyz = json.loads(estaciones), json.loads(origen)
        except (ValueError, TypeError) as exc: return ok({"error": str(exc)})
        return call(dibujo, pid, accion="secciones", corredor=corredor, baseline=baseline,
                    nombre=nombre, estaciones=stations, semiancho=semiancho, origen=xyz,
                    cota_min=cota_min, cota_max=cota_max, capa=capa, simular=simular)
