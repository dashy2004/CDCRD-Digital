# -*- coding: utf-8 -*-
"""Panel de losas (plugin-losas): uso, tipo por apoyo, seccion y acero editable
por barra (#, fraccion de pulgada) y separacion S; calculo Pieper-Martens,
visor HTML, y dibujo del armado + tabla de detalles en la planta de Revit.

Convencion de aceros (boton "Esquema", y tooltip en cada columna):
- PRINCIPAL: barra inferior del vano en la direccion en que trabaja la losa.
- TEMPERATURA: retraccion, perpendicular al principal en losas 1D.
- ADICIONALES: bastones negativos sobre los apoyos (L/4 a cada pano).

ESTADO: abrir/listar verificado en vivo (2026-10-21); calcular/dibujar segun
se prueben. IronPython de pyRevit: sin f-strings ni dataclasses.
"""
__title__ = "Uso_Losa"
__author__ = "CDCRD plugin-losas"

import io
import json
import os
import re

import clr
clr.AddReference("System.Windows.Forms")
clr.AddReference("System.Drawing")
try:
    # .NET Core (pyRevit 6.x): Process/ProcessStartInfo viven en este ensamblado
    clr.AddReference("System.Diagnostics.Process")
except Exception:
    pass  # .NET Framework: ya vienen con System
from System.Diagnostics import Process, ProcessStartInfo  # noqa: E402
from System.Drawing import Color, Font, Pen, Size, SolidBrush  # noqa: E402
from System.Drawing.Drawing2D import DashStyle  # noqa: E402
from System.Windows.Forms import (Button, DataGridView,                 # noqa: E402
                                  DataGridViewComboBoxColumn,
                                  DataGridViewTextBoxColumn, DialogResult,
                                  DockStyle, FolderBrowserDialog, Form,
                                  FormStartPosition, MessageBox,
                                  MessageBoxButtons, Panel)

from pyrevit import DB, revit  # noqa: E402

MARKER = "MCP:LOSA-ESQ"
PARAM_USO = "Uso_Losa"
PARAM_TIPO = "Tipo_Losa_PM"
PARAM_SECCION = "Seccion_Losa"
PARAM_ACERO_X = "Acero_X"
PARAM_ACERO_Y = "Acero_Y"
PARAM_ACERO_APOYO = "Acero_Apoyo"
GRUPO_PARAMS = "CDCRD plugin-losas"
FT_A_M = 0.3048
SECCION_AUTO = "auto (reglamento)"
SECCIONES = [SECCION_AUTO, "L12", "L15", "L20", "L20A-1D", "L20A-2D", "L25A-1D", "L25A-2D"]
BARRAS = ["", "#3 (3/8\")", "#4 (1/2\")", "#5 (5/8\")", "#6 (3/4\")", "#8 (1\")"]

AYUDA_X = ("ACERO segun X: es el PRINCIPAL (barra inferior del vano) cuando la losa "
           "trabaja en X; en losas 1D que trabajan en Y es el de TEMPERATURA "
           "(retraccion). Ver boton Esquema.")
AYUDA_Y = ("ACERO segun Y: es el PRINCIPAL cuando la losa trabaja en Y; en losas 1D "
           "que trabajan en X es el de TEMPERATURA. Ver boton Esquema.")
AYUDA_APOYO = ("ACERO ADICIONAL (baston negativo): barra SUPERIOR sobre el apoyo, "
               "cruza el borde compartido y entra L/4 a cada pano. Ver boton Esquema.")


# ------------------------------ repo y datos ------------------------------
def _es_repo(base):
    return os.path.isdir(os.path.join(base, "plugin-losas")) and \
        os.path.isdir(os.path.join(base, "puente-losas"))


def _raiz_repo():
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


# --------------------- barra (#, pulgada) y separacion ---------------------
def _partir_acero(texto):
    """'#3 @ 150 mm' | '#3 @ 0.15' -> ('#3', '0.15'); (None, None) si no se lee."""
    m = re.match(r"\s*(#\d+)\s*@\s*([\d.]+)\s*(mm)?\s*$", texto or "")
    if not m:
        return None, None
    valor = float(m.group(2))
    if m.group(3) == "mm" or valor > 2.0:
        valor = valor / 1000.0
    return m.group(1), ("%.2f" % valor)


def _barra_combo(numero):
    for opcion in BARRAS:
        if opcion.startswith(numero + " "):
            return opcion
    return ""


def _formatear_acero(combo_barra, s_texto):
    """('#4 (1/2\")', '0.15') -> '#4 @ 0.15'; None si falta una de las dos."""
    if not combo_barra or not s_texto:
        return None
    numero = combo_barra.split(" ")[0]
    try:
        s = float(str(s_texto).replace(",", "."))
    except ValueError:
        raise Exception("separacion invalida: '%s' (usar metros, p. ej. 0.15)" % s_texto)
    if s > 2.0:
        s = s / 1000.0          # lo teclearon en mm
    if not 0.02 <= s <= 1.0:
        raise Exception("separacion fuera de rango: %s m" % s)
    return "%s @ %.2f" % (numero, s)


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
            "uso": _param_texto(f, PARAM_USO),
            "tipo": _param_texto(f, PARAM_TIPO),
            "seccion": _param_texto(f, PARAM_SECCION),
            "acero_x": _param_texto(f, PARAM_ACERO_X),
            "acero_y": _param_texto(f, PARAM_ACERO_Y),
            "acero_apoyo": _param_texto(f, PARAM_ACERO_APOYO),
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


def _exec_tool(raiz, nombres, P_tool, doc):
    """Carga tools de revit-mcp-tools desde el repo y corre run() de la ultima."""
    ns = {"doc": doc, "uidoc": revit.uidoc, "DB": DB}
    base = os.path.join(raiz, "revit-mcp-tools", "src", "tools")
    for nombre in nombres:
        src = io.open(os.path.join(base, nombre), "r", encoding="utf-8").read()
        exec(compile(src, nombre, "exec"), ns)
    return ns["run"](doc, revit.uidoc, DB, P_tool)


def _registrar_error(texto):
    import tempfile
    try:
        ruta_log = os.path.join(tempfile.gettempdir(), "plugin_losas_panel_error.log")
        with io.open(ruta_log, "a", encoding="utf-8") as f:
            import datetime
            f.write("\n=== %s ===\n%s\n" % (datetime.datetime.now().isoformat(), texto))
        return ruta_log
    except Exception:
        return "(no se pudo escribir el log)"


def _seguro(metodo):
    """Blinda un handler de boton: el traceback va al log + dialogo legible,
    nunca al 'Unhandled exception' crudo de WinForms."""
    def envoltura(self, remitente, evento):
        try:
            metodo(self, remitente, evento)
        except Exception:
            import traceback
            texto = traceback.format_exc()
            ruta = _registrar_error(texto)
            MessageBox.Show("Error del panel (anotado en %s):\n\n%s" %
                            (ruta, texto[-1200:]))
    return envoltura


# ----------------------------- esquema de aceros -----------------------------
class EsquemaAceros(Form):
    """Mini esquema (como en los planos): que acero es cual."""

    def __init__(self):
        self.Text = "Esquema de aceros de losa (plugin-losas)"
        self.Size = Size(520, 420)
        self.StartPosition = FormStartPosition.CenterParent
        lienzo = Panel()
        lienzo.Dock = DockStyle.Fill
        lienzo.BackColor = Color.White
        lienzo.Paint += self._pintar
        self.Controls.Add(lienzo)

    def _pintar(self, remitente, e):
        g = e.Graphics
        negro = Pen(Color.Black, 2)
        gris = Pen(Color.Gray, 2)
        gris.DashStyle = DashStyle.Dash
        rojo = Pen(Color.Firebrick, 3)
        texto = SolidBrush(Color.Black)
        fuente = Font("Segoe UI", 9.0)
        fuente_n = Font("Segoe UI", 9.5)

        # dos panos contiguos (apoyo comun vertical en x=250)
        g.DrawRectangle(negro, 60, 40, 190, 220)
        g.DrawRectangle(negro, 250, 40, 190, 220)

        # PRINCIPAL (vano, inferior) del pano izquierdo: segun X, con ganchos
        g.DrawLine(negro, 95, 150, 215, 150)
        g.DrawLine(negro, 95, 150, 95, 138)
        g.DrawLine(negro, 215, 150, 215, 138)
        g.DrawString("PRINCIPAL (vano)", fuente_n, texto, 85, 155)

        # TEMPERATURA perpendicular (discontinua)
        g.DrawLine(gris, 155, 95, 155, 205)
        g.DrawString("TEMPERATURA", fuente, texto, 160, 85)

        # ADICIONAL (baston) sobre el apoyo comun: cruza el borde, L/4 y L/4
        g.DrawLine(rojo, 202, 110, 298, 110)
        g.DrawLine(rojo, 202, 110, 202, 122)
        g.DrawLine(rojo, 298, 110, 298, 122)
        g.DrawString("ADICIONAL (baston sobre el apoyo, L/4 + L/4)",
                     fuente_n, SolidBrush(Color.Firebrick), 120, 92)

        g.DrawString("Convencion del plugin (metodo Pieper-Martens / Losas.exe):",
                     fuente_n, texto, 20, 280)
        g.DrawString("- PRINCIPAL: barra inferior del vano, en la direccion en que "
                     "trabaja la losa.", fuente, texto, 20, 302)
        g.DrawString("- TEMPERATURA: retraccion, perpendicular al principal "
                     "(losas 1D).", fuente, texto, 20, 320)
        g.DrawString("- ADICIONALES: bastones superiores sobre cada apoyo "
                     "compartido (L/4 a cada pano).", fuente, texto, 20, 338)
        g.DrawString("En losas 2D ambas direcciones llevan principal.",
                     fuente, texto, 20, 356)


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

        self.Text = "Losas - uso, tipo por apoyo, seccion y acero (plugin-losas, Pieper-Martens)"
        self.Size = Size(1460, 620)
        self.StartPosition = FormStartPosition.CenterScreen

        self.grid = DataGridView()
        self.grid.Dock = DockStyle.Fill
        self.grid.AllowUserToAddRows = False
        self.grid.AllowUserToDeleteRows = False
        self.grid.RowHeadersVisible = False
        self.grid.ShowCellToolTips = True

        def _col_texto(titulo, ancho, solo_lectura, ayuda=None):
            c = DataGridViewTextBoxColumn()
            c.HeaderText = titulo
            c.Width = ancho
            c.ReadOnly = solo_lectura
            if ayuda:
                c.ToolTipText = ayuda
                c.HeaderCell.ToolTipText = ayuda
            self.grid.Columns.Add(c)
            return c

        def _col_combo(titulo, ancho, items, ayuda=None):
            c = DataGridViewComboBoxColumn()
            c.HeaderText = titulo
            c.Width = ancho
            for it in items:
                c.Items.Add(it)
            if ayuda:
                c.ToolTipText = ayuda
                c.HeaderCell.ToolTipText = ayuda
            self.grid.Columns.Add(c)
            return c

        _col_texto("Mark", 52, True)
        _col_texto("Nivel", 125, True)
        _col_texto("Lx [m]", 52, True)
        _col_texto("Ly [m]", 52, True)
        _col_combo("Uso (Tabla 4 CDCRD)", 295, [et for _, et in opciones])   # 4
        _col_texto("Tipo (apoyo)", 170, True,
                   "Tipo de losa segun sus apoyos (codigo de Losas.exe), "
                   "calculado por adyacencia al CALCULAR.")                   # 5
        _col_combo("Seccion", 110, SECCIONES,
                   "Seccion de la biblioteca: maciza o aligerada; "
                   "'auto (reglamento)' la decide el espesor y la relacion de luces.")  # 6
        _col_combo("# X", 80, BARRAS, AYUDA_X)                                # 7
        _col_texto("S X [m]", 58, False, AYUDA_X)                             # 8
        _col_combo("# Y", 80, BARRAS, AYUDA_Y)                                # 9
        _col_texto("S Y [m]", 58, False, AYUDA_Y)                             # 10
        _col_combo("# Apoyo", 80, BARRAS, AYUDA_APOYO)                        # 11
        _col_texto("S Ap [m]", 58, False, AYUDA_APOYO)                        # 12

        self._poblar()

        for texto, manejador in (
                ("Esquema: que acero es cual", self.esquema),
                ("Abrir ultimo visor HTML", self.abrir_visor),
                ("Dibujar acero en la PLANTA ACTIVA + tabla de detalles", self.dibujar_plano),
                ("Aplicar ESPESOR real (tipos de Floor por seccion)", self.aplicar_espesor),
                ("Etiquetar losas (tag Mark + espesor)", self.etiquetar),
                ("MODELAR acero 3D (solape 50db; piloto 1 losa)", self.modelar),
                ("CALCULAR (motor Pieper-Martens) y abrir visor", self.calcular),
                ("Guardar en el modelo (uso, seccion y aceros editados)", self.guardar)):
            b = Button()
            b.Text = texto
            b.Dock = DockStyle.Bottom
            b.Height = 30
            b.Click += manejador
            self.Controls.Add(b)
        self.Controls.Add(self.grid)
        self.grid.BringToFront()

    # ------------------------------ grilla ------------------------------
    def _poblar(self):
        self.grid.Rows.Clear()
        for fila in self.filas:
            idx = self.grid.Rows.Add(fila["mark"], fila["nivel"] or "",
                                     fila["lx"], fila["ly"], None,
                                     fila["tipo"] or "", None,
                                     "", "", "", "", "", "")
            if fila["uso"] and fila["uso"] in self.por_id:
                self.grid.Rows[idx].Cells[4].Value = self.por_id[fila["uso"]]
            seccion = fila["seccion"] if fila["seccion"] in SECCIONES else SECCION_AUTO
            self.grid.Rows[idx].Cells[6].Value = seccion
            for texto_acero, col in ((fila["acero_x"], 7), (fila["acero_y"], 9),
                                     (fila["acero_apoyo"], 11)):
                numero, s = _partir_acero(texto_acero or "")
                if numero:
                    self.grid.Rows[idx].Cells[col].Value = _barra_combo(numero)
                    self.grid.Rows[idx].Cells[col + 1].Value = s

    def _celda(self, i, col):
        v = self.grid.Rows[i].Cells[col].Value
        return str(v) if v else ""

    def _seleccion(self):
        usos = {}
        for i in range(self.grid.Rows.Count):
            etiqueta = self._celda(i, 4)
            mark = self._celda(i, 0)
            if etiqueta and mark:
                usos[mark] = self.por_etiqueta[etiqueta]
        return usos

    def _secciones(self, solo_fijadas=True):
        out = {}
        for i in range(self.grid.Rows.Count):
            mark = self._celda(i, 0)
            s = self._celda(i, 6)
            if mark and s and (s != SECCION_AUTO or not solo_fijadas):
                out[mark] = s
        return out

    def _aceros(self):
        out = {}
        for i in range(self.grid.Rows.Count):
            mark = self._celda(i, 0)
            if not mark:
                continue
            entrada = {}
            for clave, col in (("x", 7), ("y", 9), ("apoyo", 11)):
                texto = _formatear_acero(self._celda(i, col), self._celda(i, col + 1))
                if texto:
                    entrada[clave] = texto
            if entrada:
                out[mark] = entrada
        return out

    # ---------------------------- escrituras ----------------------------
    def _escribir_params(self, escrituras, titulo):
        doc = self.doc
        t = DB.Transaction(doc, titulo)
        t.Start()
        try:
            for nombre in escrituras:
                if self.filas and self.filas[0]["el"].LookupParameter(nombre) is None:
                    _crear_parametro_texto(doc, nombre)
            doc.Regenerate()
            n = 0
            for nombre, valores in escrituras.items():
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

    @_seguro
    def guardar(self, remitente, evento):
        escrituras = {}
        usos = self._seleccion()
        if usos:
            escrituras[PARAM_USO] = usos
        secciones = self._secciones(solo_fijadas=False)
        if secciones:
            escrituras[PARAM_SECCION] = secciones
        try:
            aceros = self._aceros()
        except Exception as ex:
            MessageBox.Show(str(ex))
            return
        for clave, nombre in (("x", PARAM_ACERO_X), ("y", PARAM_ACERO_Y),
                              ("apoyo", PARAM_ACERO_APOYO)):
            valores = dict((mk, a[clave]) for mk, a in aceros.items() if a.get(clave))
            if valores:
                escrituras[nombre] = valores
        if not escrituras:
            MessageBox.Show("Nada que guardar: elige usos/seccion o completa # y S.")
            return
        n = self._escribir_params(escrituras, "plugin-losas: uso, seccion y aceros")
        MessageBox.Show("%d valores guardados en los parametros de las losas (%s). "
                        "El .rvt NO se guarda a disco." %
                        (n, ", ".join(sorted(escrituras.keys()))))

    # ----------------------------- acciones -----------------------------
    @_seguro
    def esquema(self, remitente, evento):
        EsquemaAceros().ShowDialog(self)

    @_seguro
    def calcular(self, remitente, evento):
        if self.carpeta is None:
            dialogo = FolderBrowserDialog()
            dialogo.Description = "Carpeta de salida del calculo (Excel, .DL, visores)"
            if dialogo.ShowDialog() != DialogResult.OK:
                return
            self.carpeta = dialogo.SelectedPath
        carpeta = self.carpeta
        raiz = self.raiz

        proyecto = os.path.join(carpeta, "proyecto.json")
        _exec_tool(raiz, ("_common.py", "exportar_proyecto.py"),
                   {"path": proyecto, "marker": MARKER, "incluir": ["losas"]}, self.doc)

        marcados = os.path.join(carpeta, "usos_marcados.json")
        with io.open(marcados, "w", encoding="utf-8") as f:
            f.write(json.dumps(self._seleccion(), indent=1))
        secciones = self._secciones()
        ruta_secciones = os.path.join(carpeta, "secciones.json")
        with io.open(ruta_secciones, "w", encoding="utf-8") as f:
            f.write(json.dumps(secciones, indent=1))

        errores = []
        usos_json = os.path.join(carpeta, "usos.json")
        pasos = [
            "plugin_losas.cli tabla --proyecto \"%s\" --usos-marcados \"%s\" --salida \"%s\"" %
            (proyecto, marcados, carpeta),
            "puente_losas.cli --proyecto \"%s\" --usos \"%s\" --salida \"%s\"" %
            (proyecto, usos_json, carpeta),
            "plugin_losas.cli tipos --proyecto \"%s\" --usos \"%s\" --salida \"%s\"" %
            (proyecto, usos_json, carpeta),
            "plugin_losas.cli aligeradas --proyecto \"%s\" --usos \"%s\" --secciones \"%s\" "
            "--salida \"%s\"" % (proyecto, usos_json, ruta_secciones, carpeta),
            "plugin_losas.cli secciones --proyecto \"%s\" --usos \"%s\" --secciones \"%s\" "
            "--salida \"%s\"" % (proyecto, usos_json, ruta_secciones, carpeta),
            "plugin_losas.cli acero --resultados \"%s\" --salida \"%s\"" %
            (os.path.join(carpeta, "resultados.json"), carpeta),
        ]
        for paso in pasos:
            if not _correr_cpython(raiz, paso, errores):
                MessageBox.Show("Fallo el calculo:\n\n%s" % errores[-1])
                return

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

        with io.open(os.path.join(carpeta, "tipos_pm.json"), encoding="utf-8") as f:
            payload = json.load(f)["asignar_en_revit"]
        n = self._escribir_params({PARAM_TIPO: payload}, "plugin-losas: Tipo_Losa_PM")
        with io.open(os.path.join(carpeta, "acero_pm.json"), encoding="utf-8") as f:
            acero = json.load(f)["losas"]

        try:
            ediciones = self._aceros()
        except Exception:
            ediciones = {}
        usos_grid = self._seleccion()
        secciones_grid = self._secciones(solo_fijadas=False)
        for fila in self.filas:
            mk = fila["mark"]
            fila["tipo"] = payload.get(mk, fila["tipo"])
            if mk in usos_grid:
                fila["uso"] = usos_grid[mk]
            if mk in secciones_grid:
                fila["seccion"] = secciones_grid[mk]
            editado = ediciones.get(mk, {})
            armados = (acero.get(mk) or {}).get("armados")
            for clave, campo in (("x", "acero_x"), ("y", "acero_y"), ("apoyo", "acero_apoyo")):
                if editado.get(clave):
                    fila[campo] = editado[clave]
                elif armados and not fila[campo]:
                    if clave == "x":
                        fila[campo] = armados["mfx"]["disponer"]
                    elif clave == "y":
                        fila[campo] = armados["mfy"]["disponer"]
                    else:
                        peor = armados["msx"] if armados["msx"]["as_diseno"] >= \
                            armados["msy"]["as_diseno"] else armados["msy"]
                        fila[campo] = peor["disponer"]
        self._poblar()

        self.abrir_visor(None, None)
        MessageBox.Show("Calculo completo: %d losas; tipo por apoyo escrito en %d.\n"
                        "Acero comercial PM precargado (columnas # y S): ajusta y pulsa "
                        "Guardar, y/o Dibujar para el plano.\n"
                        "Salidas: %s\nEl .rvt NO se guarda a disco." %
                        (len(self.filas), n, carpeta))

    @_seguro
    def dibujar_plano(self, remitente, evento):
        if self.carpeta is None or not os.path.isfile(
                os.path.join(self.carpeta, "resultados.json")):
            MessageBox.Show("Primero CALCULAR (hace falta resultados.json).")
            return
        carpeta = self.carpeta
        try:
            ediciones = self._aceros()
        except Exception as ex:
            MessageBox.Show(str(ex))
            return
        ruta_editados = os.path.join(carpeta, "aceros_editados.json")
        with io.open(ruta_editados, "w", encoding="utf-8") as f:
            f.write(json.dumps(ediciones, indent=1))
        errores = []
        paso = ("plugin_losas.cli plano --proyecto \"%s\" --resultados \"%s\" "
                "--acero \"%s\" --editados \"%s\" --salida \"%s\"" %
                (os.path.join(carpeta, "proyecto.json"),
                 os.path.join(carpeta, "resultados.json"),
                 os.path.join(carpeta, "acero_pm.json"), ruta_editados, carpeta))
        if not _correr_cpython(self.raiz, paso, errores):
            MessageBox.Show("Fallo el plano:\n\n%s" % errores[-1])
            return
        try:
            res = _exec_tool(self.raiz, ("_common.py", "acero_losas_plano.py"),
                             {"plan": os.path.join(carpeta, "plan_acero.json")}, self.doc)
        except Exception as ex:
            MessageBox.Show("No se pudo dibujar: %s" % ex)
            return
        partes = []
        for r in res["vistas"]:
            partes.append("- %s: %d losas, %d bastones, %d trazos, %d notas "
                          "(borrado previo %d)" %
                          (r["vista"], r["losas_dibujadas"], r["bastones"],
                           r["trazos"], r["notas"], r["elementos_borrados"]))
        MessageBox.Show("Dibujado:\n%s\nTabla: %s.\nEl .rvt NO se guarda." %
                        ("\n".join(partes),
                         (res.get("tabla") or {}).get("nombre") or "sin cambios"))

    @_seguro
    def aplicar_espesor(self, remitente, evento):
        ruta = os.path.join(self.carpeta or "", "secciones_losas.json")
        if self.carpeta is None or not os.path.isfile(ruta):
            MessageBox.Show("Primero CALCULAR (hace falta secciones_losas.json).")
            return
        with io.open(ruta, encoding="utf-8") as f:
            payload = json.load(f)["asignar_en_revit"]
        marks = sorted(payload["asignar"].keys())
        r = MessageBox.Show(
            "Cambiar el tipo de Floor de %d losas segun su seccion (crea los "
            "tipos que falten: %s).\n\nSi = TODAS; No = PILOTO (solo %s, "
            "revisar y repetir); Cancelar = nada.\n\nOJO: cambiar el tipo "
            "regenera la geometria; la tool verifica releyendo." %
            (len(marks), ", ".join(sorted(payload["tipos_floor"])), marks[0]),
            "Aplicar espesor real", MessageBoxButtons.YesNoCancel)
        if r == DialogResult.Cancel:
            return
        P_tool = {"asignar": payload["asignar"],
                  "tipos_floor": payload["tipos_floor"]}
        if r == DialogResult.No:
            P_tool["solo_marks"] = [marks[0]]
        res = _exec_tool(self.raiz, ("_common.py", "espesor_losas.py"),
                         P_tool, self.doc)
        aviso = ""
        if res["mal"]:
            aviso = "\n\nNO COINCIDEN (revisar): %s" % json.dumps(res["mal"])
        MessageBox.Show(
            "%d losas verificadas releyendo; %d cambiadas de tipo.\n"
            "Tipos creados: %s; ajustados: %s.%s\nEl .rvt NO se guarda." %
            (res["total"], res["cambiadas"],
             ", ".join(res["tipos_creados"]) or "ninguno",
             ", ".join(res["tipos_ajustados"]) or "ninguno", aviso))

    @_seguro
    def modelar(self, remitente, evento):
        if self.carpeta is None or not os.path.isfile(
                os.path.join(self.carpeta, "resultados.json")):
            MessageBox.Show("Primero CALCULAR (hace falta resultados.json).")
            return
        carpeta = self.carpeta
        try:
            ediciones = self._aceros()
        except Exception as ex:
            MessageBox.Show(str(ex))
            return
        ruta_editados = os.path.join(carpeta, "aceros_editados.json")
        with io.open(ruta_editados, "w", encoding="utf-8") as f:
            f.write(json.dumps(ediciones, indent=1))
        paso = ("plugin_losas.cli modelado --proyecto \"%s\" --resultados \"%s\" "
                "--editados \"%s\" --salida \"%s\"" %
                (os.path.join(carpeta, "proyecto.json"),
                 os.path.join(carpeta, "resultados.json"), ruta_editados, carpeta))
        for bandera, nombre in (("--acero", "acero_pm.json"),
                                ("--secciones", "secciones_losas.json"),
                                ("--aligeradas", "plan_aligeradas.json")):
            ruta_extra = os.path.join(carpeta, nombre)
            if os.path.isfile(ruta_extra):
                paso += " %s \"%s\"" % (bandera, ruta_extra)
        errores = []
        if not _correr_cpython(self.raiz, paso, errores):
            MessageBox.Show("Fallo el plan de modelado:\n\n%s" % errores[-1])
            return
        r = MessageBox.Show(
            "Modelar el acero 3D (parrilla, temperatura, bastones; solape 50db "
            "mitad y mitad, barra de 9 m; una transaccion POR LOSA).\n\n"
            "Si = TODAS las losas; No = PILOTO (1 losa, revisar en 3D y "
            "repetir); Cancelar = nada.", "Modelar acero 3D",
            MessageBoxButtons.YesNoCancel)
        if r == DialogResult.Cancel:
            return
        P_tool = {"plan": os.path.join(carpeta, "plan_modelado.json")}
        if r == DialogResult.Yes:
            P_tool["todas"] = True
        res = _exec_tool(self.raiz, ("_common.py", "acero_losas_modelar.py"),
                         P_tool, self.doc)
        partes = []
        for x in res["losas"]:
            partes.append("- %s: %d sets / %d barras (releido %s; %d previos "
                          "borrados)" % (x["mark"], x["sets_leidos"],
                                         x["barras_leidas"],
                                         "OK" if x["ok"] else "NO COINCIDE",
                                         x["previos_borrados"]))
        aviso = ""
        if res["fallos"]:
            aviso = "\n\nFALLOS: %s" % json.dumps(res["fallos"])
        if res["piloto"]:
            aviso += ("\n\nPILOTO: %d losas pendientes; revisar en 3D y repetir "
                      "con Si (todas)." % res["n_pendientes"])
        MessageBox.Show("Acero 3D modelado:\n%s%s\nEl .rvt NO se guarda." %
                        ("\n".join(partes), aviso))

    @_seguro
    def etiquetar(self, remitente, evento):
        ruta_rfa = os.path.join(self.raiz, "plugin-losas", "revit", "familias",
                                "CDCRD Tag Losa.rfa")
        res = _exec_tool(self.raiz, ("_common.py", "tag_losas.py"),
                         {"ruta_rfa": ruta_rfa}, self.doc)
        partes = []
        for r in res["vistas"]:
            partes.append("- %s: %d tags en %d losas (%d previos borrados)" %
                          (r["vista"], r["tags_puestos"], r["losas"],
                           r["tags_borrados"]))
        mal = [v for v in res["verificacion"] if not v["ok"]]
        aviso = ""
        if mal:
            aviso = "\n\nNO COINCIDE la relectura: %s" % json.dumps(mal)
        if res["familia_cargada"]:
            aviso += "\n(familia '%s' cargada desde el repo)" % res["familia"]
        MessageBox.Show("Etiquetado (familia %s):\n%s%s\nEl .rvt NO se guarda." %
                        (res["familia"], "\n".join(partes), aviso))

    @_seguro
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
