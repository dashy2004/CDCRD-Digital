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


def _cerrar_grupo(grupo, registro):
    """Revierte el grupo del ensayo y devuelve su estado: 'RolledBack',
    'sin_iniciar' (no llego a abrirse, nada que deshacer) o 'abierto' (no se
    pudo revertir: el modelo pudo quedar modificado; va tambien a 'errores')."""
    try:
        if not grupo.HasStarted():
            return "sin_iniciar"
        if not grupo.HasEnded():
            grupo.RollBack()
        return "RolledBack"
    except Exception as exc:
        registro.error("rollback_del_ensayo", exc)
        return "abierto"


def _confirmar(DB, doc, nombre, registro, trabajo, salida):
    """Abre la transaccion, corre trabajo() y hace Commit. Devuelve el
    TransactionStatus como texto; cualquier fallo revierte y da RolledBack."""
    transaccion = DB.Transaction(doc, nombre)
    try:
        transaccion.Start()
        opciones = _opciones(DB, transaccion, registro)
        salida["datos"] = trabajo()
        return nombre_enum(transaccion.Commit(opciones))
    except Exception as exc:
        registro.error("transaccion", exc)
        _revertir(transaccion, registro)
        return "RolledBack"


def ejecutar(DB, doc, nombre, confirmar, registro, trabajo):
    """Corre trabajo() dentro de una transaccion con nombre.

    trabajo() debe crear, regenerar y verificar; lo que devuelve se copia
    en 'datos'. Devuelve {"ensayo", "confirmado", "transaccion", "estado",
    "datos"} y, en un ensayo, 'commit_de_ensayo', 'ensayo_valido',
    'estado_del_grupo' y 'ensayo_revertido'; si trabajo() o el inicio de la
    transaccion lanzan, se revierte y 'datos' es None. El grupo del ensayo
    se cierra siempre, tambien si la transaccion no llega a abrirse: un
    TransactionGroup abierto impide cerrar el documento.
    """
    salida = {"ensayo": not confirmar, "confirmado": False,
              "transaccion": nombre, "estado": None, "datos": None}
    if confirmar:
        salida["estado"] = _confirmar(DB, doc, nombre, registro, trabajo, salida)
        salida["confirmado"] = salida["estado"] == "Committed"
        return salida
    grupo = DB.TransactionGroup(doc, nombre + " (ensayo)")
    commit = "RolledBack"
    try:
        grupo.Start()
        commit = _confirmar(DB, doc, nombre, registro, trabajo, salida)
    except Exception as exc:
        registro.error("grupo_del_ensayo", exc)
    finally:
        del_grupo = _cerrar_grupo(grupo, registro)
    revertido = del_grupo != "abierto"
    salida.update({"commit_de_ensayo": commit, "estado_del_grupo": del_grupo,
                   "ensayo_revertido": revertido,
                   "ensayo_valido": commit == "Committed" and revertido})
    # Si el grupo no se pudo revertir, 'estado' dice lo que quedo en el modelo.
    salida["estado"] = "RolledBack" if revertido else commit
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
