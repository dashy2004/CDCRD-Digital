# -*- coding: utf-8 -*-
"""Exporta evidencia de independencia de redes y correspondencia circuito–tablero–cargas."""
__title__ = "Homologar\nredes MEP"

import io
import json
import os
import sys

from pyrevit import forms, revit
from pyrevit.api import DB
from System.IO import File, FileMode, FileAccess, FileShare, StreamWriter
from System.Text import UTF8Encoding


def cargar_lector():
    extension = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    carpetas = [os.environ.get("REVITWRITE_MEP_DIR"), os.path.dirname(os.path.realpath(extension)),
                os.path.join(extension, "lib"), extension]
    for carpeta in carpetas:
        if carpeta and os.path.isfile(os.path.join(carpeta, "mep", "homologacion_redes.py")):
            if carpeta not in sys.path:
                sys.path.insert(0, carpeta)
            from mep import homologacion_redes
            return homologacion_redes
    raise ValueError("No se localizó mep/homologacion_redes.py. Revise REVITWRITE_MEP_DIR.")


def ejecutar():
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument or not doc.PathName:
        raise ValueError("Abra un documento de proyecto guardado.")
    revision = forms.ask_for_string(prompt="Revisión del modelo anfitrión", title="Homologación MEP")
    if not revision or not revision.strip():
        return
    identidad = {"documento": os.path.basename(doc.PathName), "proyecto_uid": doc.ProjectInformation.UniqueId,
                 "revision": revision.strip()}
    modo = forms.CommandSwitchWindow.show(["Inventario", "Comparar manifiesto"], message="Lectura de redes")
    if modo is None:
        return
    datos = identidad.copy()
    if modo == "Comparar manifiesto":
        entrada = forms.pick_file(file_ext="json", title="Manifiesto de correspondencias")
        if not entrada:
            return
        with io.open(entrada, "r", encoding="utf-8-sig") as f:
            datos = json.load(f, object_pairs_hook=claves_unicas)
    lector = cargar_lector()
    resultado = lector.auditar(DB, doc, identidad, datos)
    texto = json.dumps(resultado, ensure_ascii=False, indent=2, allow_nan=False)
    ruta = forms.save_file(file_ext="json", default_name="observaciones-mep.json",
                           title="Guardar archivo nuevo de observaciones")
    if not ruta:
        return
    # Construir el JSON antes de abrir el archivo. CreateNew protege las evidencias previas.
    # La publicación por renombrado evita dejar una evidencia parcial en caso de escritura fallida.
    from System import Guid
    temporal = ruta + "." + str(Guid.NewGuid()) + ".tmp"
    stream = File.Open(temporal, FileMode.CreateNew, FileAccess.Write, getattr(FileShare, "None"))
    try:
        writer = StreamWriter(stream, UTF8Encoding(False))
        try:
            writer.Write(texto)
        finally:
            writer.Dispose()
        File.Move(temporal, ruta)
    finally:
        stream.Dispose()
        if File.Exists(temporal):
            File.Delete(temporal)
    forms.alert("Informe guardado en " + ruta, title="Homologación MEP")


def claves_unicas(pares):
    datos = {}
    for clave, valor in pares:
        if clave in datos:
            raise ValueError("Clave repetida en el manifiesto: " + clave)
        datos[clave] = valor
    return datos


try:
    ejecutar()
except Exception as exc:
    forms.alert("No se completó el informe: " + str(exc), title="Homologación MEP", warn_icon=True)
