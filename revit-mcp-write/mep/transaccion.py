# -*- coding: utf-8 -*-
"""Transaccion con ensayo por defecto y captura de fallos sin dialogos.

Contrato:
  - confirmar=False (ensayo): la transaccion se abre dentro de un
    TransactionGroup, se ejecuta, se verifica y se hace Commit REAL, que es
    donde Revit evalua los fallos; despues se revierte el grupo entero. El
    resultado de ese Commit va en 'commit_de_ensayo' y 'ensayo_valido' dice
    si Revit lo habria aceptado. Un RollBack directo no evalua los fallos
    del Commit y deja pasar ensayos que luego no confirman.
  - confirmar=True: Commit; 'confirmado' solo es True si Revit devuelve
    TransactionStatus.Committed.
  - Los fallos de Revit con severidad distinta de Warning van a 'errores'
    con su texto; los Warning, a 'advertencias'.
  - Nada se lee despues de revertir. Nunca se guarda el documento.
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
    si hay errores, ordena revertir. Asi nunca queda un dialogo modal:
    devolver Continue con errores pendientes deja a Revit esperando en
    pantalla."""

    class Preprocesador(DB.IFailuresPreprocessor):
        def PreprocessFailures(self, accesor):
            try:
                hay_error = False
                for fallo in list(accesor.GetFailureMessages()):
                    dato = _mensaje(fallo)
                    if dato["severidad"] == "Warning":
                        registro.advertencias.append(dato)
                        accesor.DeleteWarning(fallo)
                    else:
                        registro.fallo(dato)
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


def _abrir_grupo(DB, doc, nombre):
    grupo = DB.TransactionGroup(doc, nombre + " (ensayo)")
    grupo.Start()
    return grupo


def _cerrar_grupo(grupo, registro):
    """Revierte el grupo del ensayo; si no se puede, lo dice en 'errores'."""
    try:
        if grupo.HasStarted() and not grupo.HasEnded():
            grupo.RollBack()
            return True
    except Exception as exc:
        registro.error("rollback_del_ensayo", exc)
    return False


def ejecutar(DB, doc, nombre, confirmar, registro, trabajo):
    """Corre trabajo() dentro de una transaccion con nombre.

    trabajo() debe crear, regenerar y verificar; lo que devuelve se copia
    en 'datos'. Devuelve {"ensayo", "confirmado", "transaccion", "estado",
    "datos"} y, en un ensayo, 'commit_de_ensayo' y 'ensayo_valido'; si
    trabajo() lanza, se revierte y 'datos' es None.
    """
    salida = {"ensayo": not confirmar, "confirmado": False,
              "transaccion": nombre, "estado": None, "datos": None}
    grupo = None if confirmar else _abrir_grupo(DB, doc, nombre)
    transaccion = DB.Transaction(doc, nombre)
    transaccion.Start()
    commit = "RolledBack"
    try:
        opciones = _opciones(DB, transaccion, registro)
        salida["datos"] = trabajo()
        commit = nombre_enum(transaccion.Commit(opciones))
    except Exception as exc:
        registro.error("transaccion", exc)
        _revertir(transaccion, registro)
    if grupo is None:
        salida["estado"] = commit
        salida["confirmado"] = commit == "Committed"
        return salida
    revertido = _cerrar_grupo(grupo, registro)
    salida["commit_de_ensayo"] = commit
    salida["ensayo_valido"] = commit == "Committed"
    salida["estado"] = "RolledBack" if (revertido or commit != "Committed") else commit
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
