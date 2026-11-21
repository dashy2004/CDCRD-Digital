"""Transporte de solicitud y recibo inmutables hacia un modulo nativo opcional.

Mismo protocolo que usan los modulos de drenaje y presion: la solicitud se
escribe una sola vez con su SHA-256, se despacha un comando de un solo uso en
el proceso de Civil 3D ya abierto y el recibo queda ligado a la solicitud, al
modulo y al PID. Una solicitud nunca se reenvia: ante la duda se consulta el
recibo.
"""
import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import puente_cliente as bridge

VIGENCIA_MIN = 3


class ReciboError(RuntimeError):
    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt = receipt


def exigir_puente_libre():
    """Un modal o un despacho activo dejarian el comando encolado sin recibo."""
    if bridge.llamar("diag.dialogos")["modal_abierto"] or bridge.llamar("diag.cola")["activas"]:
        raise RuntimeError("Civil ocupado; revisar cola/dialogo antes de enviar")


_versiones = {}


def _tupla(version):
    try:
        return tuple(int(x) for x in str(version).split("."))
    except ValueError:
        return ()


def exigir_version(modulo, comando, carpeta, pid, minima):
    """Se niega a trabajar con un modulo nativo anterior al contrato de este servidor.

    Un modulo ya cargado no se reemplaza hasta reiniciar Civil 3D, y uno viejo
    ignoraria en silencio los campos que no conoce. La accion 'version' no
    existe en ningun modulo: el recibo de error trae igualmente la version del
    ensamblado que atendio el comando. Se consulta una vez por proceso y PID.
    """
    clave = (modulo, comando, pid)
    if clave not in _versiones:
        try:
            recibo = despachar(modulo, comando, carpeta, pid, {"accion": "version"}, timeout=60)
        except ReciboError as exc:
            recibo = exc.receipt
        version = recibo.get("version") if isinstance(recibo, dict) else None
        if not version:
            raise ReciboError("El modulo " + modulo + " no informo su version; verifique que este cargado", recibo)
        _versiones[clave] = version
    cargada = _versiones[clave]
    if _tupla(cargada) < _tupla(minima):
        raise RuntimeError(f"El modulo {modulo} cargado en Civil 3D es {cargada} y este servidor requiere {minima} o posterior: "
                           "instale el bundle y reinicie Civil 3D (un modulo cargado no se reemplaza en caliente)")
    return cargada


def despachar(modulo, comando, carpeta, pid, datos, timeout=180):
    """Escribe la solicitud en `carpeta`, ejecuta `comando` y devuelve el recibo verificado."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("PID positivo requerido")
    carpeta = Path(carpeta)
    request = dict(datos, pid=pid, vence_utc=(datetime.now(timezone.utc) + timedelta(minutes=VIGENCIA_MIN)).isoformat())
    key = uuid.uuid4().hex
    data = json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    request_path = carpeta / f"{modulo}-{key}.request.json"
    result_path = carpeta / f"{modulo}-{key}.result.json"
    with request_path.open("xb") as file:
        file.write(data)
    pending = {"id": key, "sha256": digest, "receipt_path": str(result_path), "estado": "desconocido"}
    try:
        bridge.llamar_con_aprobacion("cmd.run", {"linea": f"{comando}\n{key}\n{digest}\n"})
    except Exception as exc:
        raise ReciboError("Despacho incierto: consultar recibo y cola; no reintentar. " + str(exc), pending) from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("id") != key or result.get("sha256") != digest or result.get("module") != modulo or result.get("pid") != pid:
                raise ReciboError("Recibo no corresponde a la solicitud/sesion; no reintentar", pending)
            if not result.get("ok"):
                raise ReciboError(result.get("error", "Fallo nativo"), result)
            return result
        time.sleep(.1)
    raise ReciboError("Sin recibo final. Verificar modulo cargado, cola y archivo indicado; no reintentar escrituras", pending)
