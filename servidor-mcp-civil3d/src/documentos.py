"""Documentos de la sesion de Civil 3D: listar, abrir, activar y cerrar sin guardar, sin dialogos.

El modulo nativo Cdcrd.Documentos.V1 corre como comando de sesion (contexto de
aplicacion), donde DocumentCollection puede abrir, activar y cerrar dibujos.
Las solicitudes y los recibos viven en una carpeta fija del usuario
(%LOCALAPPDATA%/CdcrdCivil3dBridge/documentos), nunca junto a un dibujo: el
documento activo cambia durante estas operaciones y puede no tener archivo.

Nunca guarda. Cerrar un documento con cambios sin guardar exige
descartar_cambios=True; el unico documento abierto no se cierra, porque el
puente despacha comandos a traves de un documento.
"""
import ntpath
import os
from pathlib import Path

import puente_cliente as bridge
import transporte
from transporte import ReciboError

MODULE = "cdcrd-documentos"
COMMAND = "CDCRDDOCUMENTOSV1"
ACCIONES = ("listar", "abrir", "activar", "cerrar")


def carpeta_intercambio():
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError("LOCALAPPDATA no esta definido")
    return Path(base) / "CdcrdCivil3dBridge" / "documentos"


def _texto(value, key, max_len=400):
    if not isinstance(value, str) or not value.strip() or len(value) > max_len or any(ord(c) < 32 for c in value):
        raise ValueError("Texto requerido: " + key)
    return value


def _booleano(value, key):
    if not isinstance(value, bool):
        raise ValueError(key + " debe ser booleano")
    return value


def _ruta_dwg(value):
    ruta = _texto(value, "ruta")
    if not ntpath.isabs(ruta) or not ruta.lower().endswith(".dwg"):
        raise ValueError("ruta debe ser la ruta absoluta de un .dwg")
    return ruta


def _documento(value, key="ruta"):
    """Un dibujo guardado se nombra por su ruta absoluta; uno sin archivo (Drawing1.dwg), por su nombre."""
    doc = _texto(value, key)
    if not ntpath.isabs(doc) and ntpath.basename(doc) != doc:
        raise ValueError(key + " debe ser una ruta absoluta o el nombre de un dibujo sin archivo")
    return doc


def validar(accion, datos):
    """Deja en la solicitud solo los campos de la accion, ya validados."""
    if accion not in ACCIONES:
        raise ValueError("Accion invalida")
    if accion == "listar":
        return {}
    if accion == "abrir":
        return dict(ruta=_ruta_dwg(datos.get("ruta")), solo_lectura=_booleano(datos.get("solo_lectura", False), "solo_lectura"))
    if accion == "activar":
        return dict(ruta=_documento(datos.get("ruta")))
    out = dict(ruta=_documento(datos.get("ruta")), descartar_cambios=_booleano(datos.get("descartar_cambios", False), "descartar_cambios"))
    if datos.get("activar_despues"):
        out["activar_despues"] = _documento(datos["activar_despues"], "activar_despues")
        if ntpath.normcase(out["activar_despues"]) == ntpath.normcase(out["ruta"]):
            raise ValueError("activar_despues debe ser otro documento")
    return out


def ejecutar(pid, *, accion, timeout=120, **datos):
    request = dict(validar(accion, datos), accion=accion)
    info = bridge.llamar("doc.info")
    if not info.get("dibujo"):
        raise RuntimeError("La sesion no tiene ningun dibujo abierto: el puente no puede despachar comandos; abra uno a mano")
    transporte.exigir_puente_libre()
    carpeta = carpeta_intercambio()
    carpeta.mkdir(parents=True, exist_ok=True)
    return transporte.despachar(MODULE, COMMAND, carpeta, pid, request, timeout)


def registrar(mcp, ok):
    def call(accion, pid, **datos):
        try:
            return ok(ejecutar(pid, accion=accion, **datos))
        except ReciboError as exc:
            return ok({"error": str(exc), "receipt": exc.receipt})
        except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
            return ok({"error": str(exc)})

    @mcp.tool()
    def listar_documentos(pid: int) -> str:
        """Lista los dibujos abiertos en la sesion de Civil 3D y dice cual esta activo.

        De cada uno: ruta, si tiene archivo, solo lectura, activo, modificado
        (cambios sin guardar, por DBMOD), y comando en curso. pid es el del
        proceso acad.exe esperado: el recibo solo vale si coincide. Lectura.
        """
        return call("listar", pid)

    @mcp.tool()
    def abrir_documento(pid: int, ruta: str, solo_lectura: bool = False, confirmar: bool = False) -> str:
        """Abre un .dwg en la sesion existente, sin dialogos, y lo deja activo.

        ruta absoluta. solo_lectura=True lo abre sin posibilidad de guardar. Si
        ya esta abierto en el mismo modo solo lo activa; en modo distinto es
        error. Sin solo_lectura rechaza un archivo en uso por otro proceso en vez
        de dejar que aparezca un dialogo. Devuelve la lista de documentos y la
        ruta activa. No inicia otra instancia de Civil 3D.
        """
        if not confirmar:
            return ok({"error": "Cambia el documento activo de la sesion: requiere confirmar=True"})
        return call("abrir", pid, ruta=ruta, solo_lectura=solo_lectura)

    @mcp.tool()
    def activar_documento(pid: int, ruta: str, confirmar: bool = False) -> str:
        """Activa un dibujo ya abierto (ruta absoluta, o nombre si no tiene archivo) y devuelve la ruta activa."""
        if not confirmar:
            return ok({"error": "Cambia el documento activo de la sesion: requiere confirmar=True"})
        return call("activar", pid, ruta=ruta)

    @mcp.tool()
    def cerrar_documento(pid: int, ruta: str, descartar_cambios: bool = False, activar_despues: str = "", confirmar: bool = False) -> str:
        """Cierra un dibujo abierto SIN guardar. Nunca guarda.

        Se niega si el dibujo tiene cambios sin guardar, salvo
        descartar_cambios=True (los cambios se pierden). Se niega tambien si es
        el unico documento abierto o si tiene un comando en curso. Si era el
        activo, antes activa activar_despues o, si no se indica, otro documento
        abierto. Devuelve la lista de documentos y la ruta activa.
        """
        if not confirmar:
            return ok({"error": "Cierra un documento de la sesion: requiere confirmar=True"})
        return call("cerrar", pid, ruta=ruta, descartar_cambios=descartar_cambios, activar_despues=activar_despues or None)
