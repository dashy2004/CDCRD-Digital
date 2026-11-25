# -*- coding: utf-8 -*-
"""Emite y relee un PDF de las láminas seleccionadas en el proyecto abierto."""
from __future__ import unicode_literals

import os
import shutil
import tempfile

__title__ = "Emitir PDF"


def emitir(doc, ids, destino, db, publicar):
    """Publica en un archivo nuevo después de que Revit exporte y compruebe N páginas."""
    paginas = len(ids)
    if not paginas or not destino.lower().endswith(".pdf"):
        raise ValueError("Seleccione láminas y un destino con extensión PDF.")
    if os.path.exists(destino):
        raise ValueError("El archivo de destino ya existe. Elija un nombre nuevo.")
    carpeta = tempfile.mkdtemp(prefix="emision-", dir=os.path.dirname(destino))
    try:
        opciones = db.PDFExportOptions()
        try:
            opciones.Combine = True
            opciones.FileName = "laminas"
            opciones.PaperFormat = db.ExportPaperFormat.Default
            opciones.StopOnError = True
            opciones.SetExportInBackground(False)
            if not doc.Export(carpeta, ids, opciones):
                raise ValueError("Revit notificó una exportación parcial o fallida.")
        finally:
            opciones.Dispose()
        borrador = os.path.join(carpeta, "laminas.pdf")
        if not os.path.isfile(borrador) or not os.path.getsize(borrador):
            raise ValueError("Revit no produjo el archivo PDF esperado.")
        # IsValid comprueba la presencia de PageNumber sin importar la imagen al RVT.
        lectura = db.ImageTypeOptions(borrador, False, db.ImageTypeSource.Import)
        try:
            lectura.PageNumber = paginas
            if not lectura.IsValid(doc):
                raise ValueError("El número de páginas es inferior al previsto o el PDF es ilegible.")
            lectura.PageNumber = paginas + 1
            if lectura.IsValid(doc):
                raise ValueError("El PDF contiene más páginas que las láminas seleccionadas.")
        finally:
            lectura.Dispose()
        publicar(borrador, destino)
        return paginas
    finally:
        shutil.rmtree(carpeta)


def ejecutar():
    from System.Collections.Generic import List
    from System.IO import File
    from pyrevit import DB, forms, revit

    doc = revit.doc
    if doc is None or doc.IsFamilyDocument:
        raise ValueError("Abra un documento de proyecto.")
    catalogo = {}
    for hoja in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
        if hoja.CanBePrinted and not hoja.IsPlaceholder:
            # El identificador distingue numeraciones repetidas entre colecciones.
            etiqueta = "{0} · {1} [ID {2}]".format(hoja.SheetNumber, hoja.Name, hoja.Id.Value)
            catalogo[etiqueta] = hoja.Id
    if not catalogo:
        raise ValueError("El proyecto carece de láminas imprimibles.")
    elegidas = forms.SelectFromList.show(sorted(catalogo), multiselect=True,
                                        title="Láminas a emitir, ordenadas por número")
    if not elegidas:
        return
    ids = List[DB.ElementId]()
    for nombre in sorted(elegidas):
        ids.Add(catalogo[nombre])
    destino = forms.save_file(file_ext="pdf", default_name="Láminas.pdf",
                              title="Guardar emisión en un archivo nuevo")
    if destino:
        paginas = emitir(doc, ids, destino, DB, File.Move)
        forms.alert("PDF verificado en {0}. Páginas: {1}.".format(destino, paginas), title=__title__)


if __name__ == "__main__":
    try:
        ejecutar()
    except Exception as error:
        from pyrevit import forms
        forms.alert("No se pudo completar la emisión. {0}".format(error), title=__title__)
