"""Clothoid SCS commands in the already open Civil process; immutable receipts."""
import hashlib
import json
import math
import ntpath
from pathlib import Path
import time
import uuid
from datetime import datetime, timedelta, timezone
import puente_cliente as bridge


class SpiralError(RuntimeError):
    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt = receipt


def validar_geometria(value):
    g = json.loads(value) if isinstance(value, str) else value
    if not isinstance(g, dict):
        raise ValueError("geometria debe ser un objeto JSON")
    for key in ("inicio", "pi", "fin"):
        p = g.get(key)
        if not isinstance(p, list) or len(p) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > 1e8 for v in p):
            raise ValueError("Punto XY finito requerido: " + key)
    for key, lo, hi in [("radio",1,1e6),("longitud_entrada",.1,10000),("longitud_salida",.1,10000),("estacion_inicial",-1e7,1e7)]:
        v = g.get(key)
        if isinstance(v, bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError("Parametro fuera de rango: " + key)
    return g


def ejecutar(dibujo, pid, *, nombre=None, geometria=None, alineamiento=None, capa="CDX-ESPIRALES", simular=True, timeout=60):
    if not ntpath.isabs(dibujo) or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("Ruta DWG absoluta y PID positivo requeridos")
    create = geometria is not None
    if create and (not nombre or not capa) or not create and not alineamiento:
        raise ValueError("Nombre/capa o alineamiento requeridos")
    request = dict(dibujo=dibujo, pid=pid, accion="crear" if create else "leer", simular=simular,
                   vence_utc=(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat())
    if create:
        request.update(nombre=nombre, capa=capa, geometria=validar_geometria(geometria))
    else:
        request["alineamiento"] = alineamiento
    info = bridge.llamar("doc.info")
    if not info.get("civil3d") or ntpath.normcase(info["dibujo"]) != ntpath.normcase(dibujo) or info["insunits"] != 6:
        raise ValueError("Documento Civil o unidades distintos a lo esperado")
    if bridge.llamar("diag.dialogos")["modal_abierto"] or bridge.llamar("diag.cola")["activas"]:
        raise RuntimeError("Civil ocupado; revisar cola/dialogo antes de enviar")
    root = Path(dibujo).parent
    key = uuid.uuid4().hex
    data = json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    request_path = root / ("cdcrd-espirales-" + key + ".request.json")
    result_path = root / ("cdcrd-espirales-" + key + ".result.json")
    with request_path.open("xb") as file:
        file.write(data)
    pending = {"id": key, "sha256": digest, "receipt_path": str(result_path), "estado": "desconocido"}
    try:
        bridge.llamar_con_aprobacion("cmd.run", {"linea": f"CDCRDESPIRALESV1\n{key}\n{digest}\n"})
    except Exception as exc:
        raise SpiralError("Despacho incierto: consultar recibo y cola; no reintentar. " + str(exc), pending) from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("id") != key or result.get("sha256") != digest or result.get("module") != "cdcrd-espirales" or result.get("pid") != pid:
                raise SpiralError("Recibo no corresponde a la solicitud/sesion; no reintentar", pending)
            if not result.get("ok"):
                raise SpiralError(result.get("error", "Fallo nativo"), result)
            return result
        time.sleep(.1)
    raise SpiralError("Sin recibo final. Verificar modulo cargado, cola y archivo indicado; no reintentar escrituras", pending)


def registrar(mcp, ok):
    @mcp.tool()
    def crear_alineamiento_espirales(dibujo: str, pid: int, nombre: str, geometria: str,
                                     capa: str = "CDX-ESPIRALES", simular: bool = True,
                                     confirmar: bool = False) -> str:
        """Crea eje nativo linea-clotoide-arco-clotoide-linea en la instancia actual.

        geometria JSON: inicio/pi/fin [X,Y], radio, longitud_entrada,
        longitud_salida, estacion_inicial. Metros; longitudes positivas distintas
        admitidas; deflexion 1..170 grados, arco minimo 0.1 m. Las tangentes
        deben contener la curva. Giro determinado por los tres puntos. Requiere
        modulo Cdcrd.Espirales.V1 y comandos habilitados. Simula por defecto;
        no reemplaza nombres existentes ni calcula longitudes normativas.
        Ante timeout, inspeccionar recibo/cola; no repetir escrituras.
        """
        if not confirmar:
            return ok({"error": "Operacion de escritura: requiere confirmar=True"})
        try:
            return ok(ejecutar(dibujo, pid, nombre=nombre, geometria=geometria, capa=capa, simular=simular))
        except SpiralError as exc:
            return ok({"error": str(exc), "receipt": exc.receipt})
        except (ValueError, TypeError, OSError, RuntimeError) as exc:
            return ok({"error": str(exc)})

    @mcp.tool()
    def leer_espirales(dibujo: str, pid: int, alineamiento: str) -> str:
        """Relee y valida el eje creado por este modulo, con contrato Xrecord propio.

        Devuelve cinco subentidades, muestras XY/offset y error respecto a la
        integracion independiente de clotoides. No edita el eje ni inicia CAD.
        """
        try:
            return ok(ejecutar(dibujo, pid, alineamiento=alineamiento))
        except SpiralError as exc:
            return ok({"error": str(exc), "receipt": exc.receipt})
        except (ValueError, TypeError, OSError, RuntimeError) as exc:
            return ok({"error": str(exc)})
