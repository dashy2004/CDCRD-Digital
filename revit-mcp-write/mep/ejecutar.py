# -*- coding: utf-8 -*-
"""Ejecutor unico del paquete mep, para endpoints y para codigo suelto.

Uso desde un canal que ejecuta IronPython con 'doc' disponible:

    import sys
    carpeta = r"<ruta>/revit-mcp-write"      # la que contiene 'mep'
    if carpeta not in sys.path:
        sys.path.insert(0, carpeta)
    from Autodesk.Revit import DB
    from mep import ejecutar
    resultado = ejecutar.correr("conectores", {"ids": [1001]}, doc, DB)

Para recoger cambios del paquete sin reiniciar Revit: ejecutar.recargar().
"""

import sys

from . import auditoria, circuitos, trazado
from .base import ErrorEntrada

OPERACIONES = ("conectores", "conectar", "circuitos")
CLAVES_CONECTORES = ("categorias", "ids", "max_elementos")


def _conectores(DB, doc, opciones):
    sobran = sorted(k for k in opciones if k not in CLAVES_CONECTORES)
    if sobran:
        raise ErrorEntrada("opciones desconocidas: %s" % sobran)
    return auditoria.auditar_conectores(
        DB, doc, opciones.get("categorias"), opciones.get("ids"),
        opciones.get("max_elementos", auditoria.MAX_ELEMENTOS))


def resolver_documento(doc_activo, referencia):
    """Documento sobre el que operar: el activo si no se pide otro, o uno
    YA abierto (tambien en segundo plano) por titulo o ruta exactos.
    Nunca abre archivos ni usa vinculos."""
    if referencia is None:
        return doc_activo
    if not isinstance(referencia, str) or not referencia.strip():
        raise ErrorEntrada("'documento' debe ser el titulo o la ruta de un "
                           "documento abierto")
    buscado = referencia.strip().lower()
    hallados = []
    for abierto in doc_activo.Application.Documents:
        if abierto.IsLinked:
            continue
        if buscado in (abierto.Title.lower(), (abierto.PathName or "").lower()):
            hallados.append(abierto)
    if len(hallados) != 1:
        raise ErrorEntrada("'documento': %d documentos abiertos coinciden con "
                           "'%s'" % (len(hallados), referencia))
    return hallados[0]


def despachar(operacion, opciones, doc, DB):
    """Corre la operacion y devuelve su resultado; lanza ErrorEntrada."""
    opciones = {} if opciones is None else opciones
    if not isinstance(opciones, dict):
        raise ErrorEntrada("'opciones' debe ser un objeto")
    if operacion == "conectores":
        return _conectores(DB, doc, opciones)
    if operacion == "conectar":
        return trazado.conectar_a_ramal(DB, doc, opciones)
    if operacion == "circuitos":
        return circuitos.crear_circuitos(DB, doc, opciones)
    raise ErrorEntrada("operacion desconocida: %r (use una de %s)"
                       % (operacion, OPERACIONES))


def correr(operacion, opciones, doc, DB):
    """Igual que despachar, pero nunca lanza: devuelve siempre un dict con
    'ok'. Una entrada invalida da ok=False y 'error', sin tocar el modelo.
    Con confirmar=True, ok=False si la transaccion no quedo Committed."""
    try:
        resultado = despachar(operacion, opciones, doc, DB)
    except ErrorEntrada as exc:
        return {"ok": False, "error": str(exc), "tipo_error": "entrada"}
    except Exception as exc:
        return {"ok": False, "tipo_error": "interno",
                "error": "%s: %s" % (type(exc).__name__, exc)}
    resultado["ok"] = _corrio(resultado)
    return resultado


def _corrio(resultado):
    """False cuando se pidio confirmar y Revit no dejo la transaccion en
    Committed (el modelo no cambio y 'errores' dice por que), y cuando un
    ensayo no se pudo revertir (el modelo pudo quedar modificado)."""
    if resultado.get("ensayo") is not False:
        return resultado.get("ensayo_revertido") is not False
    return resultado.get("estado") in ("Committed", "sin_transaccion")


def recargar():
    """Descarta los modulos 'mep' ya importados para que el proximo import
    lea el codigo actual del disco. Devuelve los nombres descartados."""
    nombres = sorted(n for n in sys.modules if n == "mep" or n.startswith("mep."))
    for nombre in nombres:
        del sys.modules[nombre]
    return nombres
