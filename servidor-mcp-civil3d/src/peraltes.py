"""Superelevation module transport through the existing approved CAD command bridge.

No CAD launch, no second listener and no automatic retries. Requests and receipts
are immutable, local, and bound by SHA256, active drawing and process ID.
"""
import hashlib
import json
import math
import ntpath
from pathlib import Path
import time
import uuid
from datetime import datetime, timedelta, timezone

import puente_cliente as bridge


class PeralteError(RuntimeError):
    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt = receipt


def tabla_valida(value):
    rows = json.loads(value) if isinstance(value, str) else value
    if not isinstance(rows, list) or not 3 <= len(rows) <= 200:
        raise ValueError("tabla requiere 3..200 filas [estacion, pendiente_izq, pendiente_der]")
    for row in rows:
        if (not isinstance(row, list) or len(row) != 3 or
                any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in row)):
            raise ValueError("Cada fila requiere tres numeros finitos")
        if abs(row[1]) > .12 or abs(row[2]) > .12:
            raise ValueError("Pendientes fuera de -0.12..0.12 m/m")
    if any(b[0] - a[0] < .001 for a, b in zip(rows, rows[1:])):
        raise ValueError("Estaciones estrictamente crecientes, separacion minima 0.001 m")
    return rows


def ejecutar(dibujo, pid, corredor, tabla=None, simular=True, timeout=60):
    if not ntpath.isabs(dibujo) or not corredor or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("Ruta DWG absoluta, PID positivo y corredor requeridos")
    request = dict(dibujo=dibujo, pid=pid, corredor=corredor, accion="leer" if tabla is None else "aplicar", simular=simular,
                   vence_utc=(datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat())
    if tabla is not None:
        request["tabla"] = tabla_valida(tabla)
    info = bridge.llamar("doc.info")
    if not info.get("civil3d") or ntpath.normcase(info["dibujo"]) != ntpath.normcase(dibujo) or info["insunits"] != 6:
        raise ValueError("Documento Civil o unidades distintos a lo esperado")
    if bridge.llamar("diag.dialogos")["modal_abierto"] or bridge.llamar("diag.cola")["activas"]:
        raise RuntimeError("Civil ocupado; revisar cola/dialogo antes de enviar")
    root = Path(dibujo).parent
    key = uuid.uuid4().hex
    data = json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    request_path = root / ("cdcrd-peraltes-" + key + ".request.json")
    result_path = root / ("cdcrd-peraltes-" + key + ".result.json")
    with request_path.open("xb") as file:
        file.write(data)
    pending = {"id": key, "sha256": digest, "receipt_path": str(result_path), "estado": "desconocido"}
    try:
        bridge.llamar_con_aprobacion("cmd.run", {"linea": f"CDCRDPERALTESV1\n{key}\n{digest}\n"})
    except Exception as exc:
        raise PeralteError("Despacho incierto: consultar recibo y cola; no reintentar. " + str(exc), pending) from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("id") != key or result.get("sha256") != digest or result.get("module") != "cdcrd-peraltes" or result.get("pid") != pid:
                raise PeralteError("Recibo no corresponde a la solicitud/sesion; no reintentar", pending)
            if not result.get("ok"):
                raise PeralteError(result.get("error", "Fallo nativo"), result)
            return result
        time.sleep(.1)
    raise PeralteError("Sin recibo final. Verificar modulo cargado, cola y archivo indicado; no reintentar escrituras", pending)


def registrar(mcp, ok):
    @mcp.tool()
    def peraltes_por_tabla(dibujo: str, pid: int, corredor: str, tabla: str,
                          simular: bool = True, confirmar: bool = False) -> str:
        """Aplica peraltes nativos a eje/corredor independiente sin tabla existente.

        Requiere modulo Cdcrd.Peraltes cargado en la instancia YA abierta; no abre
        Civil. tabla JSON [[estacion,izq,der],...] en metros y m/m hacia afuera,
        incluyendo extremos; 3..200 filas; pendientes -0.12..0.12. Interpolacion
        lineal sin suavizado; dos carriles LaneSuperelevationAOR, eje de giro central.
        Una baseline/region sobre todo el eje. Rechaza ejes/ensamblajes compartidos,
        referencias, ecuaciones y targets de ancho/elevacion. Bermas y cunetas
        mantienen parametros. simular=True ejecuta y revierte; no calcula normas,
        velocidad ni seguridad vial. Timeout: consultar recibo, nunca repetir.
        """
        if not confirmar:
            return ok({"error": "Operacion de escritura: requiere confirmar=True"})
        try:
            return ok(ejecutar(dibujo, pid, corredor, tabla, simular))
        except PeralteError as exc:
            return ok({"error": str(exc), "receipt": exc.receipt})
        except (ValueError, TypeError, OSError, RuntimeError) as exc:
            return ok({"error": str(exc)})

    @mcp.tool()
    def leer_peraltes(dibujo: str, pid: int, corredor: str) -> str:
        """Relee tabla nativa, carriles y puntos XYZ/SOE del corredor en la sesion indicada.

        Requiere el modulo opcional y comandos habilitados. Transaccion abortada;
        no recalcula ni cambia peraltes. El recibo incluye PID y version del modulo.
        """
        try:
            return ok(ejecutar(dibujo, pid, corredor))
        except PeralteError as exc:
            return ok({"error": str(exc), "receipt": exc.receipt})
        except (ValueError, TypeError, OSError, RuntimeError) as exc:
            return ok({"error": str(exc)})
