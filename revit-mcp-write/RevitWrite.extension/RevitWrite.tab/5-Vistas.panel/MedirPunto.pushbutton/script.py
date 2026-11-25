# -*- coding: utf-8 -*-
"""Exporta un punto físico en coordenadas compartidas para homologación."""
from __future__ import unicode_literals

import json
import math
import ntpath
import os
import tempfile

__title__ = "Medir punto"
ROLES = ("umbral", "control_revit")
METROS_POR_PIE = 0.3048


def registro(doc, elemento, referencia, rol, revision, laminas, marco):
    """Convierte las coordenadas compartidas de Revit (pies internos) en metros."""
    if not doc.PathName:
        raise ValueError("Guarde una copia identificable del proyecto antes de medir.")
    if rol not in ROLES or not revision.strip() or not marco.strip():
        raise ValueError("Se requieren rol, revisión y marco horizontal y vertical.")
    if not laminas or not all(n.strip() for n in laminas):
        raise ValueError("Seleccione al menos una lámina afectada.")
    if referencia.GlobalPoint is None or not elemento.UniqueId:
        raise ValueError("La referencia necesita un punto físico y un elemento identificable.")
    sitio = doc.ActiveProjectLocation
    posicion = sitio.GetProjectPosition(referencia.GlobalPoint)
    punto = [v * METROS_POR_PIE for v in
             (posicion.EastWest, posicion.NorthSouth, posicion.Elevation)]
    if any(math.isnan(v) or math.isinf(v) for v in punto):
        raise ValueError("La ubicación de proyecto produjo coordenadas no finitas.")
    return {
        "rol": rol, "documento": ntpath.basename(doc.PathName),
        "revision": revision.strip(), "laminas": sorted(set(laminas)),
        "elemento": elemento.UniqueId, "punto_m": punto, "marco": marco.strip(),
        "metodo": ("PickObject(PointOnElement) en 3D y GetProjectPosition, "
                   "sitio activo «{0}». Conversión de pies a metros. "
                   "Láminas afectadas y revisión declaradas por el operador.").format(sitio.Name),
    }


def exportar(destino, datos, publicar):
    """Publica un JSON completo en la misma carpeta. File.Move exige destino nuevo."""
    contenido = json.dumps(datos, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    # Nombre temporal fuera del patrón *.json usado para importar mediciones.
    descriptor, temporal = tempfile.mkstemp(dir=os.path.dirname(destino), suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as archivo:
            archivo.write(contenido.encode("utf-8"))
        publicar(temporal, destino)
    finally:
        if os.path.exists(temporal):
            os.remove(temporal)


def ejecutar():
    from Autodesk.Revit.Exceptions import OperationCanceledException
    from Autodesk.Revit.UI.Selection import ObjectType
    from System.IO import File
    from pyrevit import DB, forms, revit

    doc = revit.doc
    if doc is None or doc.IsFamilyDocument or not isinstance(doc.ActiveView, DB.View3D):
        raise ValueError("Abra una vista 3D del proyecto. La cota seleccionada en planta es ambigua.")
    if not doc.PathName:
        raise ValueError("Guarde primero el documento para identificar su revisión.")
    rol = forms.SelectFromList.show(list(ROLES), title="Función del punto")
    if not rol:
        return
    try:
        referencia = revit.uidoc.Selection.PickObject(
            ObjectType.PointOnElement, "Seleccione el punto físico del umbral o del hito de control.")
    except OperationCanceledException:
        return
    elemento = doc.GetElement(referencia.ElementId)
    if (elemento is None or isinstance(elemento, DB.RevitLinkInstance)
            or referencia.LinkedElementId != DB.ElementId.InvalidElementId):
        raise ValueError("Seleccione geometría local del proyecto. Los vínculos requieren su propia transformación.")
    revision = forms.ask_for_string(prompt="Revisión del modelo o de la emisión medida")
    if revision is None:
        return
    marco = forms.ask_for_string(prompt="Identificador común del marco horizontal y vertical acordado con Civil 3D")
    if marco is None:
        return
    disponibles = sorted("{0} [{1}]".format(hoja.SheetNumber, hoja.UniqueId) for hoja in
                         DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)
                         if not hoja.IsPlaceholder)
    if not disponibles:
        raise ValueError("El proyecto carece de láminas emitibles para vincular la medición.")
    laminas = forms.SelectFromList.show(disponibles, multiselect=True, title="Láminas afectadas según el operador")
    if not laminas:
        return
    datos = registro(doc, elemento, referencia, rol, revision, laminas, marco)
    destino = forms.save_file(file_ext="json", default_name=rol + ".json",
                              title="Guardar medición en un archivo nuevo")
    if not destino:
        return
    exportar(destino, datos, File.Move)
    forms.alert("Medición guardada en {0}".format(destino), title=__title__)


if __name__ == "__main__":
    try:
        ejecutar()
    except Exception as error:
        from pyrevit import forms
        forms.alert("No se pudo exportar la medición. {0}".format(error), title=__title__)
