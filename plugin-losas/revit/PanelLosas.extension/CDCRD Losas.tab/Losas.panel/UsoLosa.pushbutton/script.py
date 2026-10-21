# -*- coding: utf-8 -*-
"""Panel de losas (plugin-losas): nombres, uso Tabla 4 y tipo por apoyo, con
calculo Pieper-Martens y visor HTML desde el mismo panel.

Ventana ARRASTRABLE con una fila por losa MCP:LOSA-ESQ* del modelo:
Mark (L00, L01... segun la ley de numeracion), nivel, Lx/Ly/area, un
DESPLEGABLE con los 45 usos de la Tabla 4 del CDCRD y la columna "Tipo
(apoyo)" con el codigo de Losas.exe calculado por adyacencia (10..60, 71/72).

Botones:
- Guardar usos: escribe Uso_Losa en el modelo (crea el parametro si falta).
- Calcular y abrir visor: exporta las losas (exportar_proyecto de
  revit-mcp-tools), corre el MOTOR en CPython (plugin-losas tabla ->
  puente-losas [FEM + Pieper-Martens + Excel + .DL] -> tipos -> visor con
  acero comercial PM), escribe Tipo_Losa_PM en el modelo y abre el visor
  HTML (uno por nivel) en el navegador.
- Abrir ultimo visor: reabre los HTML de la ultima corrida.

Requisitos: el repo CDCRD-Digital con plugin-losas y puente-losas (este
archivo vive dentro), Python 3 (lanzador `py`) con motor-fea y openpyxl.
La ventana NO guarda el .rvt (eso lo decide el usuario).
IronPython de pyRevit: sin f-strings ni dataclasses.
"""
__title__ = "Uso_Losa"
__author__ = "CDCRD plugin-losas"

import io
import json
import os

import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")
try:
    # .NET Core (pyRevit 6.x): Process/ProcessStartInfo viven en este ensamblado
    clr.AddReference("System.Diagnostics.Process")
except Exception:
    pass  # .NET Framework: ya vienen con System
from System.Diagnostics import Process, ProcessStartInfo  # noqa: E402
from System.Drawing import Size  # noqa: E402
from System.Windows.Forms import (Button, DataGridView,                 # noqa: E402
                                  DataGridViewComboBoxColumn,
                                  DataGridViewTextBoxColumn, DialogResult,
                                  DockStyle, FolderBrowserDialog, Form,
                                  FormStartPosition, MessageBox)

from pyrevit import DB, revit  # noqa: E402

MARKER = "MCP:LOSA-ESQ"
PARAM_USO = "Uso_Losa"
PARAM_TIPO = "Tipo_Losa_PM"
GRUPO_PARAMS = "CDCRD plugin-losas"
FT_A_M = 0.3048


# ------------------------------ repo y datos ------------------------------
def _es_repo(base):
    return os.path.isdir(os.path.join(base, "plugin-losas")) and \
        os.path.isdir(os.path.join(base, "puente-losas"))


def _raiz_repo():
    """Raiz del repo CDCRD-Digital. La extension instalada vive FUERA del
    repo (%APPDATA%\\pyRevit\\Extensions), asi que se intenta en orden:
    (1) repo.txt junto al script (lo escribe la instalacion con la ruta),
    (2) variable de entorno CDCRD_REPO, (3) subir carpetas desde el script
    (caso: ejecutado desde el repo mismo)."""
    aqui = os.path.dirname(os.path.abspath(__file__))
    ruta_txt = os.path.join(aqui, "repo.txt")
    if os.path.isfile(ruta_txt):
        candidata = io.open(ruta_txt, encoding="utf-8").read().strip()
        if _es_repo(candidata):
            return candidata
        raise Exception("repo.txt apunta a '%s' pero ahi no esta el repo" % candidata)
    candidata = os.environ.get("CDCRD_REPO", "")
    if candidata and _es_repo(candidata):
        return candidata
    base = aqui
    for _ in range(10):
        if _es_repo(base):
            return base
        padre = os.path.dirname(base)
        if padre == base:
            break
        base = padre
    raise Exception("no se encontro el repo CDCRD-Digital: escribir su ruta en "
                    "repo.txt junto a script.py o en la variable CDCRD_REPO")


def _slug(texto):
    # misma regla que plugin_losas.usos_tabla4._slug (ids compatibles)
    import re
    t = texto.lower().replace("<=", " max ").replace(">", " mas ")
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def _cargar_usos(raiz):
    with io.open(os.path.join(raiz, "datos", "machine", "cargas_vivas.json"),
                 encoding="utf-8") as f:
        d = json.load(f)
    opciones = []
    for rec in d["valores"]:
        uso_id = _slug(rec["grupo"] + "/" + rec["uso"])
        viva = ("%.2f kN/m2" % rec["uniforme"]) if rec.get("uniforme") is not None else "regla"
        opciones.append((uso_id, "%s - %s (%s)" % (rec["grupo"], rec["uso"], viva)))
    return opciones


# ----------------------------- losas del modelo -----------------------------
def _param_texto(el, nombre):
    p = el.LookupParameter(nombre)
    if p is None:
        return None
    return p.AsString()


def _filas(doc):
    filas = []
    col = DB.FilteredElementCollector(doc) \
            .OfCategory(DB.BuiltInCategory.OST_Floors).WhereElementIsNotElementType()
    for f in col:
        p_com = f.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if p_com is None or not (p_com.AsString() or "").startswith(MARKER):
            continue
        bb = f.get_BoundingBox(None)
        p_mark = f.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
        p_area = f.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)
        nivel = None
        try:
            lv = doc.GetElement(f.LevelId)
            nivel = lv.Name if lv is not None else None
        except Exception:
            pass
        filas.append({
            "el": f,
            "mark": (p_mark.AsString() or "") if p_mark else "",
            "nivel": nivel,
            "lx": round((bb.Max.X - bb.Min.X) * FT_A_M, 3) if bb else None,
            "ly": round((bb.Max.Y - bb.Min.Y) * FT_A_M, 3) if bb else None,
            "area": round(p_area.AsDouble() * 0.09290304, 2) if p_area and p_area.HasValue else None,
            "uso": _param_texto(f, PARAM_USO),
            "tipo": _param_texto(f, PARAM_TIPO),
        })
    filas.sort(key=lambda x: x["mark"])
    return filas


def _crear_parametro_texto(doc, nombre):
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
        definicion = grupo.Definitions.get_Item(nombre)
        if definicion is None:
            definicion = grupo.Definitions.Create(
                DB.ExternalDefinitionCreationOptions(nombre, DB.SpecTypeId.String.Text))
        cats = app.Create.NewCategorySet()
        cats.Insert(doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Floors))
        doc.ParameterBindings.Insert(definicion, app.Create.NewInstanceBinding(cats),
                                     DB.GroupTypeId.Data)
    finally:
        if anterior:
            app.SharedParametersFilename = anterior


def _correr_cpython(raiz, argumentos, errores):
    """`py -3 -m <modulo> ...` con el PYTHONPATH del repo; True si exit 0."""
    psi = ProcessStartInfo()
    psi.FileName = "py"
    psi.Arguments = "-3 -m " + argumentos
    psi.WorkingDirectory = raiz
    psi.UseShellExecute = False
    psi.CreateNoWindow = True
    psi.RedirectStandardOutput = True
    psi.RedirectStandardError = True
    psi.EnvironmentVariables["PYTHONPATH"] = \
        os.path.join(raiz, "plugin-losas", "src") + ";" + \
        os.path.join(raiz, "puente-losas", "src")
    proceso = Process.Start(psi)
    salida = proceso.StandardOutput.ReadToEnd()
    error = proceso.StandardError.ReadToEnd()
    proceso.WaitForExit()
    if proceso.ExitCode != 0:
        errores.append("py -3 -m %s\n%s\n%s" % (argumentos, salida, error))
        return False
    return True


# --------------------------------- ventana ---------------------------------
class PanelUsoLosa(Form):
    def __init__(self, doc, filas, opciones, raiz):
        self.doc = doc
        self.filas = filas
        self.raiz = raiz
        self.carpeta = None
        self.visores = []
        self.por_etiqueta = dict((et, uid) for uid, et in opciones)
        self.por_id = dict((uid, et) for uid, et in opciones)

        self.Text = "Losas - uso Tabla 4 y tipo por apoyo (plugin-losas, metodo Pieper-Martens)"
        self.Size = Size(1180, 560)
        self.StartPosition = FormStartPosition.CenterScreen

        self.grid = DataGridView()
        self.grid.Dock = DockStyle.Fill
        self.grid.AllowUserToAddRows = False
        self.grid.AllowUserToDeleteRows = False
        self.grid.RowHeadersVisible = False

        for titulo, ancho in (("Mark", 60), ("Nivel", 160), ("Lx [m]", 60),
                              ("Ly [m]", 60), ("Area [m2]", 70)):
            c = DataGridViewTextBoxColumn()
            c.HeaderText = titulo
            c.Width = ancho
            c.ReadOnly = True
            self.grid.Columns.Add(c)
        combo = DataGridViewComboBoxColumn()
        combo.HeaderText = "Uso (Tabla 4 CDCRD)"
        combo.Width = 420
        for _, etiqueta in opciones:
            combo.Items.Add(etiqueta)
        self.grid.Columns.Add(combo)
        c_tipo = DataGridViewTextBoxColumn()
        c_tipo.HeaderText = "Tipo (apoyo, cod. Losas.exe)"
        c_tipo.Width = 280
        c_tipo.ReadOnly = True
        self.grid.Columns.Add(c_tipo)

        self._poblar()

        for texto, manejador in (
                ("Abrir ultimo visor HTML", self.abrir_visor),
                ("CALCULAR (motor Pieper-Martens) y abrir visor", self.calcular),
                ("Guardar usos en el modelo (Uso_Losa)", self.guardar)):
            b = Button()
            b.Text = texto
            b.Dock = DockStyle.Bottom
            b.Height = 32
            b.Click += manejador
            self.Controls.Add(b)
        self.Controls.Add(self.grid)
        self.grid.BringToFront()

    def _poblar(self):
        self.grid.Rows.Clear()
        for fila in self.filas:
            idx = self.grid.Rows.Add(fila["mark"], fila["nivel"] or "", fila["lx"],
                                     fila["ly"], fila["area"], None, fila["tipo"] or "")
            if fila["uso"] and fila["uso"] in self.por_id:
                self.grid.Rows[idx].Cells[5].Value = self.por_id[fila["uso"]]

    def _seleccion(self):
        usos = {}
        for i in range(self.grid.Rows.Count):
            etiqueta = self.grid.Rows[i].Cells[5].Value
            mark = self.grid.Rows[i].Cells[0].Value
            if etiqueta and mark:
                usos[str(mark)] = self.por_etiqueta[str(etiqueta)]
        return usos

    def _escribir_param(self, nombre, valores, titulo):
        doc = self.doc
        t = DB.Transaction(doc, titulo)
        t.Start()
        try:
            if self.filas and self.filas[0]["el"].LookupParameter(nombre) is None:
                _crear_parametro_texto(doc, nombre)
                doc.Regenerate()
            n = 0
            for fila in self.filas:
                if fila["mark"] in valores:
                    fila["el"].LookupParameter(nombre).Set(valores[fila["mark"]])
                    n += 1
            t.Commit()
            return n
        except Exception as ex:
            t.RollBack()
            MessageBox.Show("Error (rollback): %s" % ex)
            return 0

    def guardar(self, remitente, evento):
        usos = self._seleccion()
        if not usos:
            MessageBox.Show("Ninguna fila tiene uso elegido.")
            return
        n = self._escribir_param(PARAM_USO, usos, "plugin-losas: Uso_Losa")
        MessageBox.Show("%d losas con Uso_Losa guardado. El .rvt NO se guarda a disco." % n)

    def calcular(self, remitente, evento):
        if self.carpeta is None:
            dialogo = FolderBrowserDialog()
            dialogo.Description = "Carpeta de salida del calculo (Excel, .DL, visores)"
            if dialogo.ShowDialog() != DialogResult.OK:
                return
            self.carpeta = dialogo.SelectedPath
        carpeta = self.carpeta
        raiz = self.raiz

        # 1) export de las losas (misma tool exportar_proyecto de revit-mcp-tools)
        ns = {"doc": self.doc, "uidoc": revit.uidoc, "DB": DB}
        base = os.path.join(raiz, "revit-mcp-tools", "src", "tools")
        for nombre in ("_common.py", "exportar_proyecto.py"):
            src = io.open(os.path.join(base, nombre), "r", encoding="utf-8").read()
            exec(compile(src, nombre, "exec"), ns)
        proyecto = os.path.join(carpeta, "proyecto.json")
        ns["run"](self.doc, revit.uidoc, DB,
                  {"path": proyecto, "marker": MARKER, "incluir": ["losas"]})

        # 2) usos elegidos en el panel
        marcados = os.path.join(carpeta, "usos_marcados.json")
        with io.open(marcados, "w", encoding="utf-8") as f:
            f.write(json.dumps(self._seleccion(), indent=1))

        # 3) motor en CPython: tabla -> puente-losas (FEM+PM) -> tipos -> visor
        errores = []
        pasos = [
            "plugin_losas.cli tabla --proyecto \"%s\" --usos-marcados \"%s\" --salida \"%s\"" %
            (proyecto, marcados, carpeta),
            "puente_losas.cli --proyecto \"%s\" --usos \"%s\" --salida \"%s\"" %
            (proyecto, os.path.join(carpeta, "usos.json"), carpeta),
            "plugin_losas.cli tipos --proyecto \"%s\" --usos \"%s\" --salida \"%s\"" %
            (proyecto, os.path.join(carpeta, "usos.json"), carpeta),
        ]
        for paso in pasos:
            if not _correr_cpython(raiz, paso, errores):
                MessageBox.Show("Fallo el calculo:\n\n%s" % errores[-1])
                return

        # 4) visor por nivel
        niveles = sorted(set(f["nivel"] for f in self.filas if f["nivel"]))
        self.visores = []
        for nivel in niveles:
            salida_nivel = os.path.join(carpeta, _slug(nivel))
            paso = ("plugin_losas.cli visor --proyecto \"%s\" --resultados \"%s\" "
                    "--salida \"%s\" --nombre \"%s\" --nivel \"%s\"" %
                    (proyecto, os.path.join(carpeta, "resultados.json"),
                     salida_nivel, nivel, nivel))
            if not _correr_cpython(raiz, paso, errores):
                MessageBox.Show("Fallo el visor de %s:\n\n%s" % (nivel, errores[-1]))
                return
            self.visores.append(os.path.join(salida_nivel, "visor_losas.html"))

        # 5) tipo por apoyo al modelo y a la columna del panel
        with io.open(os.path.join(carpeta, "tipos_pm.json"), encoding="utf-8") as f:
            payload = json.load(f)["asignar_en_revit"]
        n = self._escribir_param(PARAM_TIPO, payload, "plugin-losas: Tipo_Losa_PM")
        for fila in self.filas:
            fila["tipo"] = payload.get(fila["mark"], fila["tipo"])
        self._poblar()

        self.abrir_visor(None, None)
        MessageBox.Show("Calculo completo: %d losas, tipo por apoyo escrito en %d.\n"
                        "Salidas (Excel, .DL, visores): %s\n"
                        "El .rvt NO se guarda a disco." % (len(self.filas), n, carpeta))

    def abrir_visor(self, remitente, evento):
        if not self.visores:
            MessageBox.Show("Todavia no hay visor: usa CALCULAR.")
            return
        for ruta in self.visores:
            if os.path.exists(ruta):
                psi = ProcessStartInfo(ruta)
                psi.UseShellExecute = True
                Process.Start(psi)


def _principal():
    doc = revit.doc
    raiz = _raiz_repo()
    filas = _filas(doc)
    if not filas:
        MessageBox.Show("Ninguna losa con Comments '%s*' en el modelo." % MARKER)
        return
    PanelUsoLosa(doc, filas, _cargar_usos(raiz), raiz).ShowDialog()


try:
    _principal()
except Exception:
    # cualquier fallo queda en un archivo legible (ademas del dialogo), para
    # diagnosticar sin depender de copiar el traceback a mano
    import tempfile
    import traceback
    texto = traceback.format_exc()
    ruta_log = os.path.join(tempfile.gettempdir(), "plugin_losas_panel_error.log")
    try:
        with io.open(ruta_log, "a", encoding="utf-8") as f:
            import datetime
            f.write("\n=== %s ===\n%s\n" % (datetime.datetime.now().isoformat(), texto))
    except Exception:
        pass
    MessageBox.Show("Error del panel (anotado en %s):\n\n%s" % (ruta_log, texto[-1200:]))
