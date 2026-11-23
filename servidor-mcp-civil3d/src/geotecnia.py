"""Proyectos del Geotechnical Modeler sin sus dialogos: listar, crear, importar CSV y vincular al dibujo.

El modulo nativo Cdcrd.Geotecnia.V1 llega a los servicios del Geotechnical
Modeler por reflexion, a traves de su propio contenedor: son los mismos
objetos que usa el panel Manage Data. No abre ninguna ventana.

Toda escritura simula por defecto. Al confirmar, crear e importar copian
antes la base de datos del Geotechnical Modeler junto a ella, con fecha.
Vincular escribe el proyecto en los ajustes del dibujo activo y no guarda
el dibujo. Los datos geotecnicos que se cargan son responsabilidad de quien
los entrega: el modulo no los interpreta.
"""
import ntpath
import os
import re
from pathlib import Path

import puente_cliente as bridge
import transporte
from transporte import ReciboError

MODULE = "cdcrd-geotecnia"
COMMAND = "CDCRDGEOTECNIAV1"
ACCIONES = ("listar", "crear", "importar", "vincular")
ID_VALIDO = re.compile(r"^[\w \-\.\(\)]{1,100}$")


def carpeta_intercambio():
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError("LOCALAPPDATA no esta definido")
    return Path(base) / "CdcrdCivil3dBridge" / "geotecnia"


def _texto(value, key, max_len=260):
    if not isinstance(value, str) or not value.strip() or len(value) > max_len or any(ord(c) < 32 for c in value):
        raise ValueError("Texto requerido: " + key)
    return value


def _opcional(value, key, max_len):
    return _texto(value, key, max_len) if value not in (None, "") else None


def _proyecto(value):
    proyecto = _texto(value, "proyecto_id", 100)
    if not ID_VALIDO.match(proyecto):
        raise ValueError("proyecto_id admite letras, numeros, espacios, guion, punto y parentesis")
    return proyecto


def _csv(value, key, obligatorio=True):
    if value in (None, "") and not obligatorio:
        return None
    ruta = _texto(value, key)
    if not ntpath.isabs(ruta) or not ruta.lower().endswith(".csv"):
        raise ValueError(key + " debe ser la ruta absoluta de un .csv")
    return ruta


def validar(accion, datos):
    """Deja en la solicitud solo los campos de la accion, ya validados."""
    if accion not in ACCIONES:
        raise ValueError("Accion invalida")
    if accion == "listar":
        return {}
    confirmar = datos.get("confirmar", False)
    if not isinstance(confirmar, bool):
        raise ValueError("confirmar debe ser booleano")
    out = dict(proyecto_id=_proyecto(datos.get("proyecto_id")), confirmar=confirmar)
    if accion == "crear":
        campos = (("nombre", 200), ("ubicacion", 200), ("sistema_coord", 60))
        out.update({k: v for k, v in ((k, _opcional(datos.get(k), k, n)) for k, n in campos) if v})
    elif accion == "importar":
        out.update(ubicaciones=_csv(datos.get("ubicaciones"), "ubicaciones"), litologia=_csv(datos.get("litologia"), "litologia"))
        orientacion = _csv(datos.get("orientacion"), "orientacion", obligatorio=False)
        if orientacion:
            out["orientacion"] = orientacion
        delimitador = datos.get("delimitador", ",")
        if delimitador not in (",", ";", "\t", "|"):
            raise ValueError("delimitador debe ser coma, punto y coma, tabulador o barra")
        out["delimitador"] = delimitador
    return out


def ejecutar(pid, *, accion, timeout=180, **datos):
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
    def gm_listar_proyectos(pid: int) -> str:
        """Lista los proyectos de la base del Geotechnical Modeler y cual esta vinculado al dibujo activo.

        De cada uno: identificador, nombre, ubicacion, sistema de coordenadas y
        numero de sondeos y estratos. Devuelve tambien la ruta de la base de
        datos. Lectura sin cambios. pid es el del proceso acad.exe esperado.
        """
        return call("listar", pid)

    @mcp.tool()
    def gm_crear_proyecto(pid: int, proyecto_id: str, nombre: str = "", ubicacion: str = "", sistema_coord: str = "",
                          confirmar: bool = False) -> str:
        """Crea un proyecto vacio en la base del Geotechnical Modeler, sin su dialogo.

        Se niega si ya existe un proyecto con ese identificador. Sin
        confirmar=True simula y no escribe. Al confirmar copia antes la base
        de datos junto a ella y devuelve la ruta del respaldo. No vincula el
        proyecto a ningun dibujo: use gm_vincular_proyecto.
        """
        return call("crear", pid, proyecto_id=proyecto_id, nombre=nombre, ubicacion=ubicacion, sistema_coord=sistema_coord,
                    confirmar=confirmar)

    @mcp.tool()
    def gm_importar_csv(pid: int, proyecto_id: str, ubicaciones: str, litologia: str, orientacion: str = "",
                        delimitador: str = ",", confirmar: bool = False) -> str:
        """Importa sondeos y estratos a un proyecto existente desde CSV con el formato del Geotechnical Modeler.

        ubicaciones y litologia son rutas absolutas; orientacion es opcional.
        El mapeo de campos es el automatico del modulo de Autodesk para sus
        propias cabeceras (Location ID, Easting, Northing, Ground Level, Final
        Depth; Depth Top, Depth Base, Legend Code, Geology Code...). Sin
        confirmar=True comprueba el mapeo y cuenta las filas, sin escribir. Al
        confirmar respalda la base y devuelve los sondeos y estratos antes y
        despues, mas el informe del importador. No agrega los sondeos al
        dibujo ni importa muestras SPT.
        """
        return call("importar", pid, proyecto_id=proyecto_id, ubicaciones=ubicaciones, litologia=litologia,
                    orientacion=orientacion, delimitador=delimitador, confirmar=confirmar)

    @mcp.tool()
    def gm_vincular_proyecto(pid: int, proyecto_id: str, confirmar: bool = False) -> str:
        """Vincula el dibujo activo a un proyecto existente del Geotechnical Modeler (escribe su ProjectId).

        Sirve tambien para un dibujo ya vinculado a otro proyecto, que en el
        panel deja el selector deshabilitado. Sin confirmar=True informa el
        proyecto actual y el que quedaria. Relee el ajuste tras escribirlo y
        falla si no coincide. No guarda el dibujo.
        """
        return call("vincular", pid, proyecto_id=proyecto_id, confirmar=confirmar)
