// CDCRD-Digital - puente MCP para Civil 3D 2027
// Exportacion sin dialogos (PlotEngine sincrono a PDF/PNG/DWF), vistas con
// nombre y vistas 3D. Complementa Handlers.cs via DispatchExtra.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.PlottingServices;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;

namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        // ---------- utilidades ----------

        private static Extents3d? ExtentsDe(JsonObject p, Transaction tr, Database db)
        {
            var ventana = p["ventana"] as JsonArray;
            if (ventana != null)
            {
                if (ventana.Count != 4)
                    throw new BridgeException(Rpc.ErrParams, "ventana debe ser [x1,y1,x2,y2]");
                double x1 = ventana[0].GetValue<double>(), y1 = ventana[1].GetValue<double>();
                double x2 = ventana[2].GetValue<double>(), y2 = ventana[3].GetValue<double>();
                return new Extents3d(new Point3d(Math.Min(x1, x2), Math.Min(y1, y2), 0),
                                     new Point3d(Math.Max(x1, x2), Math.Max(y1, y2), 0));
            }
            var handles = (p["handles"] as JsonArray)?.Select(x => x.GetValue<string>()).ToList();
            if (handles != null && handles.Count > 0)
            {
                Extents3d? ext = null;
                foreach (var h in handles)
                {
                    var ent = tr.GetObject(IdFromHandle(db, h), OpenMode.ForRead) as Entity;
                    if (ent == null) continue;
                    try
                    {
                        var e = ent.GeometricExtents;
                        if (ext == null) ext = e;
                        else { var u = ext.Value; u.AddExtents(e); ext = u; }
                    }
                    catch { }
                }
                if (ext == null) throw new BridgeException(Rpc.ErrParams, "los handles no tienen extension geometrica");
                return ext;
            }
            return null;
        }

        private static string NormalizarMedio(string s)
        {
            return new string(s.Where(char.IsLetterOrDigit).ToArray()).ToLowerInvariant();
        }

        // ---------- lista de dispositivos y papeles ----------

        private static object VistaPapeles(JsonObject p)
        {
            var psv = PlotSettingsValidator.Current;
            var dispositivos = new List<string>();
            foreach (string d in psv.GetPlotDeviceList()) dispositivos.Add(d);
            string dispositivo = Txt(p, "dispositivo");
            var res = new Dictionary<string, object> { { "dispositivos", dispositivos } };
            if (!string.IsNullOrWhiteSpace(dispositivo))
            {
                if (!dispositivos.Contains(dispositivo))
                    throw new BridgeException(Rpc.ErrParams, "dispositivo desconocido: " + dispositivo);
                using (var ps = new PlotSettings(true))
                {
                    psv.SetPlotConfigurationName(ps, dispositivo, null);
                    psv.RefreshLists(ps);
                    var medios = new List<object>();
                    var canonicos = psv.GetCanonicalMediaNameList(ps);
                    for (int i = 0; i < canonicos.Count; i++)
                        medios.Add(new Dictionary<string, object>
                        {
                            { "canonico", canonicos[i] },
                            { "nombre", psv.GetLocaleMediaName(ps, i) }
                        });
                    res["dispositivo"] = dispositivo;
                    res["papeles"] = medios;
                }
            }
            return res;
        }

        // ---------- exportacion sincrona (PlotEngine) ----------

        private static object VistaExportar(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string ruta = Txt(p, "ruta");
            if (string.IsNullOrWhiteSpace(ruta)) throw new BridgeException(Rpc.ErrParams, "falta ruta de salida");
            string dispositivo = Txt(p, "dispositivo") ?? "DWG To PDF.pc3";
            string papel = Txt(p, "papel");
            string estiloPlot = Txt(p, "estilo_plot");
            string nombreVista = Txt(p, "nombre_vista");
            string sombreado = Txt(p, "sombreado");
            double margen = Num(p, "margen") ?? 0.03;

            if (PlotFactory.ProcessPlotState != ProcessPlotState.NotPlotting)
                throw new BridgeException(Rpc.ErrBusy, "ya hay un ploteo en curso; reintente en unos segundos");

            var doc = Doc(); var db = doc.Database;
            Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(ruta)));
            if (File.Exists(ruta)) { try { File.Delete(ruta); } catch { } }

            object bgAnterior = AcApp.GetSystemVariable("BACKGROUNDPLOT");
            AcApp.SetSystemVariable("BACKGROUNDPLOT", 0);
            string papelUsado = null;
            try
            {
                using (doc.LockDocument())
                using (var tr = db.TransactionManager.StartTransaction())
                {
                    var btr = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
                    var layout = (Layout)tr.GetObject(btr.LayoutId, OpenMode.ForRead);
                    var psv = PlotSettingsValidator.Current;
                    using (var ps = new PlotSettings(layout.ModelType))
                    {
                        ps.CopyFrom(layout);
                        psv.SetPlotConfigurationName(ps, dispositivo, null);
                        psv.RefreshLists(ps);

                        // papel: se acepta el nombre canonico, el visible o un pedazo
                        var canonicos = psv.GetCanonicalMediaNameList(ps);
                        if (!string.IsNullOrWhiteSpace(papel))
                        {
                            string clave = NormalizarMedio(papel);
                            for (int i = 0; i < canonicos.Count; i++)
                            {
                                if (NormalizarMedio(canonicos[i]).Contains(clave) ||
                                    NormalizarMedio(psv.GetLocaleMediaName(ps, i)).Contains(clave))
                                { papelUsado = canonicos[i]; break; }
                            }
                            if (papelUsado == null)
                                throw new BridgeException(Rpc.ErrParams, "papel '" + papel +
                                    "' no existe en " + dispositivo + "; consulte vista.papeles");
                            psv.SetCanonicalMediaName(ps, papelUsado);
                        }

                        var ext = ExtentsDe(p, tr, db);
                        if (!string.IsNullOrWhiteSpace(nombreVista))
                        {
                            psv.SetPlotViewName(ps, nombreVista);
                            psv.SetPlotType(ps, Autodesk.AutoCAD.DatabaseServices.PlotType.View);
                        }
                        else if (ext != null)
                        {
                            var min = ext.Value.MinPoint; var max = ext.Value.MaxPoint;
                            double mx = (max.X - min.X) * margen, my = (max.Y - min.Y) * margen;
                            psv.SetPlotWindowArea(ps, new Extents2d(min.X - mx, min.Y - my, max.X + mx, max.Y + my));
                            psv.SetPlotType(ps, Autodesk.AutoCAD.DatabaseServices.PlotType.Window);
                        }
                        else
                        {
                            psv.SetPlotType(ps, Autodesk.AutoCAD.DatabaseServices.PlotType.Extents);
                        }
                        psv.SetUseStandardScale(ps, true);
                        psv.SetStdScaleType(ps, StdScaleType.ScaleToFit);
                        psv.SetPlotCentered(ps, true);
                        if (!string.IsNullOrWhiteSpace(estiloPlot)) psv.SetCurrentStyleSheet(ps, estiloPlot);
                        if (!string.IsNullOrWhiteSpace(sombreado))
                        {
                            var err = FijarPropiedad(ps, "ShadePlot", sombreado);
                            if (err != null) Log.Write("vista.exportar: ShadePlot no aplicado: " + err);
                        }

                        var pi = new PlotInfo { Layout = btr.LayoutId, OverrideSettings = ps };
                        var piv = new PlotInfoValidator { MediaMatchingPolicy = MatchingPolicy.MatchEnabled };
                        piv.Validate(pi);

                        using (var pe = PlotFactory.CreatePublishEngine())
                        using (var ppd = new PlotProgressDialog(false, 1, true))
                        {
                            ppd.set_PlotMsgString(PlotMessageIndex.DialogTitle, "CDCRD exportar");
                            ppd.LowerPlotProgressRange = 0;
                            ppd.UpperPlotProgressRange = 100;
                            ppd.PlotProgressPos = 0;
                            ppd.LowerSheetProgressRange = 0;
                            ppd.UpperSheetProgressRange = 100;
                            ppd.SheetProgressPos = 0;
                            ppd.IsVisible = false;
                            ppd.OnBeginPlot();
                            pe.BeginPlot(ppd, null);
                            pe.BeginDocument(pi, doc.Name, null, 1, true, ruta);
                            ppd.OnBeginSheet();
                            var ppi = new PlotPageInfo();
                            pe.BeginPage(ppi, pi, true, null);
                            pe.BeginGenerateGraphics(null);
                            pe.EndGenerateGraphics(null);
                            pe.EndPage(null);
                            ppd.OnEndSheet();
                            pe.EndDocument(null);
                            pe.EndPlot(null);
                            ppd.OnEndPlot();
                        }
                    }
                    tr.Commit();
                }
            }
            finally
            {
                try { AcApp.SetSystemVariable("BACKGROUNDPLOT", Convert.ToInt16(bgAnterior)); } catch { }
            }

            var fi = new FileInfo(ruta);
            if (!fi.Exists || fi.Length == 0)
                throw new BridgeException(Rpc.ErrInternal, "el ploteo termino pero no genero " + ruta);
            Log.Write("vista.exportar " + ruta + " (" + fi.Length + " bytes)");
            return new Dictionary<string, object>
            {
                { "ruta", fi.FullName }, { "bytes", fi.Length },
                { "dispositivo", dispositivo }, { "papel", papelUsado ?? "(por defecto)" }
            };
        }

        // ---------- vistas con nombre y vista 3D ----------

        private static readonly Dictionary<string, double[]> DireccionesNombradas =
            new Dictionary<string, double[]>(StringComparer.OrdinalIgnoreCase)
        {
            { "SE", new[] {  1.0, -1.0, 1.0 } }, { "SW", new[] { -1.0, -1.0, 1.0 } },
            { "NE", new[] {  1.0,  1.0, 1.0 } }, { "NW", new[] { -1.0,  1.0, 1.0 } },
            { "PLANTA", new[] { 0.0, 0.0, 1.0 } },
            { "FRENTE", new[] { 0.0, -1.0, 0.0 } }, { "DERECHA", new[] { 1.0, 0.0, 0.0 } }
        };

        private static Vector3d DireccionDe(JsonNode n)
        {
            if (n == null) return new Vector3d(0, 0, 1);
            if (n is JsonArray)
            {
                var pt = PuntoDe(n, "direccion");
                return new Vector3d(pt.X, pt.Y, pt.Z);
            }
            var s = n.GetValue<string>();
            if (!DireccionesNombradas.TryGetValue(s, out var v))
                throw new BridgeException(Rpc.ErrParams, "direccion '" + s + "' no valida; use " +
                    string.Join("|", DireccionesNombradas.Keys) + " o [x,y,z]");
            return new Vector3d(v[0], v[1], v[2]);
        }

        private static ObjectId EstiloVisualId(Transaction tr, Database db, string nombre)
        {
            if (string.IsNullOrWhiteSpace(nombre)) return ObjectId.Null;
            var dict = (DBDictionary)tr.GetObject(db.VisualStyleDictionaryId, OpenMode.ForRead);
            foreach (DBDictionaryEntry e in dict)
            {
                if (string.Equals(e.Key, nombre, StringComparison.OrdinalIgnoreCase)) return e.Value;
            }
            var hay = new List<string>();
            foreach (DBDictionaryEntry e in dict) hay.Add(e.Key);
            throw new BridgeException(Rpc.ErrParams, "estilo visual '" + nombre + "' no existe; hay: " +
                string.Join(", ", hay));
        }

        // Construye la vista: direccion + objetivo + ancho (en unidades del modelo,
        // medidos en el plano de la vista).
        private static ViewTableRecord ConstruirVista(JsonObject p, Transaction tr, Database db)
        {
            var dir = DireccionDe(p["direccion"]);
            if (dir.Length < 1e-9) throw new BridgeException(Rpc.ErrParams, "direccion nula");
            dir = dir.GetNormal();

            Point3d objetivo;
            double ancho, alto;
            var ext = ExtentsDe(p, tr, db);
            if (p["objetivo"] != null) objetivo = PuntoDe(p["objetivo"], "objetivo");
            else if (ext != null) objetivo = new Point3d(
                (ext.Value.MinPoint.X + ext.Value.MaxPoint.X) / 2,
                (ext.Value.MinPoint.Y + ext.Value.MaxPoint.Y) / 2,
                (ext.Value.MinPoint.Z + ext.Value.MaxPoint.Z) / 2);
            else
            {
                db.UpdateExt(true);
                objetivo = new Point3d((db.Extmin.X + db.Extmax.X) / 2,
                                       (db.Extmin.Y + db.Extmax.Y) / 2,
                                       (db.Extmin.Z + db.Extmax.Z) / 2);
                ext = new Extents3d(db.Extmin, db.Extmax);
            }
            var a = Num(p, "ancho");
            if (a != null) ancho = a.Value;
            else if (ext != null)
                ancho = 1.2 * ext.Value.MinPoint.DistanceTo(ext.Value.MaxPoint);
            else throw new BridgeException(Rpc.ErrParams, "falta ancho (o handles/ventana para deducirlo)");
            alto = Num(p, "alto") ?? ancho * 0.7;

            var vtr = new ViewTableRecord
            {
                ViewDirection = dir,
                Target = objetivo,
                CenterPoint = new Point2d(0, 0),
                Width = ancho,
                Height = alto,
                PerspectiveEnabled = false,
                IsPaperspaceView = false
            };
            var ev = EstiloVisualId(tr, db, Txt(p, "estilo_visual"));
            if (!ev.IsNull) vtr.VisualStyleId = ev;
            return vtr;
        }

        // vista.3d: cambia la vista ACTUAL del modelo (sin guardarla).
        private static object Vista3d(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            var doc = Doc(); var db = doc.Database;
            Dictionary<string, object> res;
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var vtr = ConstruirVista(p, tr, db);
                doc.Editor.SetCurrentView(vtr);
                res = new Dictionary<string, object>
                {
                    { "direccion", Val(vtr.ViewDirection) }, { "objetivo", Val(vtr.Target) },
                    { "ancho", vtr.Width }, { "alto", vtr.Height },
                    { "estilo_visual", Txt(p, "estilo_visual") }
                };
                tr.Commit();
            }
            Log.Write("vista.3d aplicada");
            return res;
        }

        // vista.guardada: crea o reemplaza una vista con nombre (para plotear con
        // PlotType.View o volver a ella con vista.activar).
        private static object VistaGuardada(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string nombre = Txt(p, "nombre");
            if (string.IsNullOrWhiteSpace(nombre)) throw new BridgeException(Rpc.ErrParams, "falta nombre");
            var doc = Doc(); var db = doc.Database;
            Dictionary<string, object> res;
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                ViewTableRecord vtr;
                if (p["direccion"] == null && p["ventana"] == null && p["handles"] == null &&
                    p["objetivo"] == null && p["ancho"] == null)
                {
                    vtr = doc.Editor.GetCurrentView();   // clon no residente de la vista actual
                    var ev = EstiloVisualId(tr, db, Txt(p, "estilo_visual"));
                    if (!ev.IsNull) vtr.VisualStyleId = ev;
                }
                else vtr = ConstruirVista(p, tr, db);
                vtr.Name = nombre;

                var tabla = (ViewTable)tr.GetObject(db.ViewTableId, OpenMode.ForWrite);
                bool reemplazada = false;
                if (tabla.Has(nombre))
                {
                    var vieja = tr.GetObject(tabla[nombre], OpenMode.ForWrite);
                    vieja.Erase();
                    reemplazada = true;
                }
                var id = tabla.Add(vtr);
                tr.AddNewlyCreatedDBObject(vtr, true);
                res = new Dictionary<string, object>
                {
                    { "handle", HandleOf(id) }, { "nombre", nombre }, { "reemplazada", reemplazada },
                    { "ancho", vtr.Width }, { "alto", vtr.Height }, { "direccion", Val(vtr.ViewDirection) }
                };
                tr.Commit();
            }
            Log.Write("vista.guardada '" + nombre + "'");
            return res;
        }

        private static object VistaActivar(JsonObject p)
        {
            string nombre = Txt(p, "nombre");
            if (string.IsNullOrWhiteSpace(nombre)) throw new BridgeException(Rpc.ErrParams, "falta nombre");
            var doc = Doc(); var db = doc.Database;
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var tabla = (ViewTable)tr.GetObject(db.ViewTableId, OpenMode.ForRead);
                if (!tabla.Has(nombre))
                    throw new BridgeException(Rpc.ErrParams, "no existe la vista '" + nombre + "'");
                var vtr = (ViewTableRecord)tr.GetObject(tabla[nombre], OpenMode.ForRead);
                doc.Editor.SetCurrentView((ViewTableRecord)vtr.Clone());
                tr.Commit();
            }
            return new Dictionary<string, object> { { "activada", nombre } };
        }
    }
}
