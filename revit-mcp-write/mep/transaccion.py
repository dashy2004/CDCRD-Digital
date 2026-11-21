# -*- coding: utf-8 -*-
"""Transaccion con ensayo por defecto y captura de fallos sin dialogos.

Contrato:
  - confirmar=False: se ejecuta y se verifica DENTRO de la transaccion y
    se hace RollBack. Nada se lee despues del RollBack.
  - confirmar=True: Commit; 'confirmado' solo es True si Revit devuelve
    TransactionStatus.Committed.
  - Nunca se guarda el documento.
"""

from .base import eid_valor, nombre_enum


def _mensaje(fallo):
    return {
        "severidad": nombre_enum(fallo.GetSeverity()),
        "descripcion": fallo.GetDescriptionText(),
        "elementos": [eid_valor(i) for i in fallo.GetFailingElementIds()],
    }


def crear_preprocesador(DB, registro):
    """IFailuresPreprocessor: anota cada fallo, borra las advertencias y,
    si hay errores, ordena revertir. Asi nunca queda un dialogo modal."""

    class Preprocesador(DB.IFailuresPreprocessor):
        def PreprocessFailures(self, accesor):
            try:
                hay_error = False
                for fallo in list(accesor.GetFailureMessages()):
                    dato = _mensaje(fallo)
                    registro.advertencias.append(dato)
                    if dato["severidad"] == "Warning":
                        accesor.DeleteWarning(fallo)
                    else:
                        hay_error = True
                if hay_error:
                    return DB.FailureProcessingResult.ProceedWithRollBack
                return DB.FailureProcessingResult.Continue
            except Exception as exc:
                registro.error("preprocesador_de_fallos", exc)
                return DB.FailureProcessingResult.ProceedWithRollBack

    return Preprocesador()


def _opciones(DB, transaccion, registro):
    opciones = transaccion.GetFailureHandlingOptions()
    opciones.SetFailuresPreprocessor(crear_preprocesador(DB, registro))
    opciones.SetForcedModalHandling(False)
    opciones.SetClearAfterRollback(True)
    transaccion.SetFailureHandlingOptions(opciones)
    return opciones


def _revertir(transaccion, registro):
    try:
        if transaccion.HasStarted() and not transaccion.HasEnded():
            transaccion.RollBack()
    except Exception as exc:
        registro.error("rollback", exc)


def ejecutar(DB, doc, nombre, confirmar, registro, trabajo):
    """Corre trabajo() dentro de una transaccion con nombre.

    trabajo() debe crear, regenerar y verificar; lo que devuelve se copia
    en 'datos'. Devuelve {"ensayo", "confirmado", "transaccion", "estado",
    "datos"}; si trabajo() lanza, se revierte y 'datos' es None.
    """
    salida = {"ensayo": not confirmar, "confirmado": False,
              "transaccion": nombre, "estado": None, "datos": None}
    transaccion = DB.Transaction(doc, nombre)
    transaccion.Start()
    try:
        opciones = _opciones(DB, transaccion, registro)
        salida["datos"] = trabajo()
        if confirmar:
            estado = transaccion.Commit(opciones)
        else:
            estado = transaccion.RollBack(opciones)
        salida["estado"] = nombre_enum(estado)
        salida["confirmado"] = bool(confirmar and salida["estado"] == "Committed")
    except Exception as exc:
        registro.error("transaccion", exc)
        _revertir(transaccion, registro)
        salida["estado"] = "RolledBack"
    return salida


def en_subtransaccion(DB, doc, registro, etapa, elemento, paso):
    """Corre paso() en una SubTransaction. paso() devuelve (mantener, valor).

    Se revierte la subtransaccion si paso() lanza o pide no mantener, de
    modo que un aparato fallido no deja piezas a medias en el lote.
    Devuelve (mantenido, valor, mensaje_de_error).
    """
    sub = DB.SubTransaction(doc)
    sub.Start()
    try:
        mantener, valor = paso()
    except Exception as exc:
        registro.error(etapa, exc, elemento)
        sub.RollBack()
        return False, None, "%s: %s" % (type(exc).__name__, exc)
    if mantener:
        sub.Commit()
    else:
        sub.RollBack()
    return mantener, valor, None
