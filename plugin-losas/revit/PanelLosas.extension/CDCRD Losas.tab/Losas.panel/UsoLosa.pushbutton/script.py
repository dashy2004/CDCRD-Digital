# -*- coding: utf-8 -*-
"""Panel Uso_Losa: numeracion + dimensiones de las losas MCP:LOSA-ESQ* con el
uso de la Tabla 4 del CDCRD editable por desplegable (plugin-losas).

Ventana arrastrable con una fila por losa (Mark, nivel, Lx, Ly, area, espesor)
y un combo de los 45 usos de la Tabla 4 (datos/machine/cargas_vivas.json).
"Guardar" escribe el id del uso en el parametro de proyecto Uso_Losa (lo crea
si falta). "Exportar" deja usos_marcados.json + tabla_losas.json para el CLI:

    plugin-losas tabla --proyecto proyecto.json --usos-marcados usos_marcados.json

ESTADO: escrito siguiendo la API estandar de Revit/pyRevit pero NO verificado
en una sesion viva (regla de coordinacion: la sesion de Revit tiene su turno).
La logica de usos/sets si esta testeada en plugin_losas (54 tests).
IronPython de pyRevit: sin f-strings ni dataclasses.
"""
__title__ = "Uso_Losa"
__author__ = "CDCRD plugin-losas"

import json
import os

import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")
from System.Drawing import Size  # noqa: E402
from System.Windows.Forms import (Button, DataGridView,                 # noqa: E402
                                  DataGridViewComboBoxColumn,
                                  DataGridViewTextBoxColumn, DialogResult,
                                  DockStyle, Form, FormStartPosition,
                                  MessageBox, SaveFileDialog)

from pyrevit import DB, revit  # noqa: E402

MARKER = "MCP:LOSA-ESQ"
PARAM_USO = "Uso_Losa"
GRUPO_PARAMS = "CDCRD plugin-losas"
FT_A_M = 304.8 / 1000.0


# ----------------------- Tabla 4 (cargas_vivas.json) -----------------------
def _ruta_tabla4():
    base = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        ruta = os.path.join(base, "datos", "machine", "cargas_vivas.json")
        if os.path.isfile(ruta):
            return ruta
        padre = os.path.dirname(base)
        if padre == base:
            break
        base = padre
    raise Exception("no se encontro datos/machine/cargas_vivas.json sobre el script")


def _slug(texto):
    # misma regla que plugin_losas.usos_tabla4._slug (ids compatibles)
    import re
    t = texto.lower().replace("<=", " max ").replace(">", " mas ")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def _cargar_usos():
    with open(_ruta_tabla4()) as f:
        d = json.load(f)
    opciones = []
    for rec in d["valores"]:
        uso_id = _slug(rec["grupo"] + "/" + rec["uso"])
        if rec.get("uniforme") is not None:
            viva = "%.2f kN/m2" % rec["uniforme"]
        else:
            viva = "regla"
        etiqueta = "%s - %s (%s)" % (rec["grupo"], rec["uso"], viva)
        opciones.append((uso_id, etiqueta))
    return opciones


# ----------------------------- losas del modelo -----------------------------
def _comment(el):
    p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    return (p.AsString() or "") if p is not None else ""


def _mark(el):
    p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
    return (p.AsString() or "") if p is not None else ""


def _m(feet):
    return round(feet * FT_A_M, 3)


def _filas(doc):
    filas = []
    col = DB.FilteredElementCollector(doc) \
            .OfCategory(DB.BuiltInCategory.OST_Floors).WhereElementIsNotElementType()
    for f in col:
        if not _comment(f).startswith(MARKER):
            continue
        bb = f.get_BoundingBox(None)
        lx = _m(bb.Max.X - bb.Min.X) if bb else None
        ly = _m(bb.Max.Y - bb.Min.Y) if bb else None
        area = None
        p = f.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)
        if p is not None and p.HasValue:
            area = round(p.AsDouble() * 0.09290304, 2)
        nivel = None
        try:
            lv = doc.GetElement(f.LevelId)
            nivel = lv.Name if lv is not None else None
        except Exception:
            pass
        uso = None
        pu = f.LookupParameter(PARAM_USO)
        if pu is not None:
            uso = pu.AsString()
        filas.append({"el": f, "mark": _mark(f), "nivel": nivel, "lx": lx,
                      "ly": ly, "area": area, "uso": uso})
    return filas


def _crear_parametro_uso(doc):
    import tempfile
    app = doc.Application
    anterior = app.SharedParametersFilename
    ruta = os.path.join(tempfile.gettempdir(), "cdcrd_uso_losa_params.txt")
    if not os.path.exists(ruta):
        open(ruta, "w").close()
    app.SharedParametersFilename = ruta
    try:
        archivo = app.OpenSharedParameterFile()
        grupo = None
        for g in archivo.Groups:
            if g.Name == GRUPO_PARAMS:
                grupo = g
        if grupo is None:
            grupo = archivo.Groups.Create(GRUPO_PARAMS)
        definicion = grupo.Definitions.get_Item(PARAM_USO)
        if definicion is None:
            opciones = DB.ExternalDefinitionCreationOptions(PARAM_USO, DB.SpecTypeId.String.Text)
            definicion = grupo.Definitions.Create(opciones)
        cats = app.Create.NewCategorySet()
        cats.Insert(doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Floors))
        doc.ParameterBindings.Insert(definicion, app.Create.NewInstanceBinding(cats),
                                     DB.GroupTypeId.Data)
    finally:
        if anterior:
            app.SharedParametersFilename = anterior


# --------------------------------- ventana ---------------------------------
class PanelUsoLosa(Form):
    def __init__(self, doc, filas, opciones):
        self.doc = doc
        self.filas = filas
        self.por_etiqueta = dict((et, uid) for uid, et in opciones)
        self.por_id = dict((uid, et) for uid, et in opciones)

        self.Text = "Uso_Losa - Tabla 4 CDCRD (plugin-losas)"
        self.Size = Size(980, 520)
        self.StartPosition = FormStartPosition.CenterScreen

        self.grid = DataGridView()
        self.grid.Dock = DockStyle.Fill
        self.grid.AllowUserToAddRows = False
        self.grid.AllowUserToDeleteRows = False
        self.grid.RowHeadersVisible = False

        for titulo, ancho in (("Mark", 70), ("Nivel", 110), ("Lx [m]", 70),
                              ("Ly [m]", 70), ("Area [m2]", 80)):
            c = DataGridViewTextBoxColumn()
            c.HeaderText = titulo
            c.Width = ancho
            c.ReadOnly = True
            self.grid.Columns.Add(c)
        combo = DataGridViewComboBoxColumn()
        combo.HeaderText = "Uso (Tabla 4)"
        combo.Width = 520
        for _, etiqueta in opciones:
            combo.Items.Add(etiqueta)
        self.grid.Columns.Add(combo)

        for fila in filas:
            idx = self.grid.Rows.Add(fila["mark"], fila["nivel"] or "",
                                     fila["lx"], fila["ly"], fila["area"], None)
            if fila["uso"] and fila["uso"] in self.por_id:
                self.grid.Rows[idx].Cells[5].Value = self.por_id[fila["uso"]]

        boton_guardar = Button()
        boton_guardar.Text = "Guardar en el modelo (Uso_Losa)"
        boton_guardar.Dock = DockStyle.Bottom
        boton_guardar.Height = 32
        boton_guardar.Click += self.guardar

        boton_exportar = Button()
        boton_exportar.Text = "Exportar tabla + usos para el Excel (CLI plugin-losas)"
        boton_exportar.Dock = DockStyle.Bottom
        boton_exportar.Height = 32
        boton_exportar.Click += self.exportar

        self.Controls.Add(self.grid)
        self.Controls.Add(boton_guardar)
        self.Controls.Add(boton_exportar)

    def _seleccion(self):
        usos = {}
        for i in range(self.grid.Rows.Count):
            etiqueta = self.grid.Rows[i].Cells[5].Value
            mark = self.grid.Rows[i].Cells[0].Value
            if etiqueta and mark:
                usos[str(mark)] = self.por_etiqueta[str(etiqueta)]
        return usos

    def guardar(self, remitente, evento):
        usos = self._seleccion()
        if not usos:
            MessageBox.Show("Ninguna fila tiene uso elegido.")
            return
        doc = self.doc
        t = DB.Transaction(doc, "plugin-losas: Uso_Losa")
        t.Start()
        try:
            if self.filas and self.filas[0]["el"].LookupParameter(PARAM_USO) is None:
                _crear_parametro_uso(doc)
                doc.Regenerate()
            n = 0
            for fila in self.filas:
                if fila["mark"] in usos:
                    fila["el"].LookupParameter(PARAM_USO).Set(usos[fila["mark"]])
                    n += 1
            t.Commit()
            MessageBox.Show("%d losas con Uso_Losa guardado. El modelo NO se ha "
                            "guardado a disco (guardar aparte)." % n)
        except Exception as ex:
            t.RollBack()
            MessageBox.Show("Error (rollback): %s" % ex)

    def exportar(self, remitente, evento):
        dialogo = SaveFileDialog()
        dialogo.FileName = "usos_marcados.json"
        dialogo.Filter = "JSON|*.json"
        if dialogo.ShowDialog() != DialogResult.OK:
            return
        ruta = dialogo.FileName
        usos = self._seleccion()
        with open(ruta, "w") as f:
            json.dump(usos, f, indent=1)
        tabla = [{"mark": x["mark"], "nivel": x["nivel"], "lx": x["lx"],
                  "ly": x["ly"], "area_m2": x["area"],
                  "uso_tabla4": usos.get(x["mark"])} for x in self.filas]
        ruta_tabla = os.path.join(os.path.dirname(ruta), "tabla_losas.json")
        with open(ruta_tabla, "w") as f:
            json.dump(tabla, f, indent=1)
        MessageBox.Show("Exportado:\n%s\n%s\n\nSiguiente paso (CPython):\n"
                        "plugin-losas tabla --proyecto proyecto.json "
                        "--usos-marcados %s" % (ruta, ruta_tabla, os.path.basename(ruta)))


doc = revit.doc
filas = _filas(doc)
if not filas:
    MessageBox.Show("Ninguna losa con Comments '%s*' en el modelo." % MARKER)
else:
    PanelUsoLosa(doc, filas, _cargar_usos()).ShowDialog()
