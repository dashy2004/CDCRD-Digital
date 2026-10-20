// CDCRD-Digital - puente MCP para Civil 3D 2027
// Creacion de objetos Civil 3D (perfiles, vistas de perfil, hatch de vista,
// estilos) y entidades de dibujo por API nativa, sin LISP ni dialogos.
// Complementa Handlers.cs: Dispatch delega aqui en su caso default.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Autodesk.AutoCAD.Colors;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;

namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        private static object DispatchExtra(string method, JsonObject p)
        {
            switch (method)
            {
#if CIVIL3D
                case "civil.parcela_polilinea": return CrearParcelaPolilinea(p, method);
                case "civil.alineamiento_polilinea": return CrearAlineamientoPolilinea(p, method);
                case "civil.perfil_pvi": return CrearPerfilPvi(p, method);
                case "civil.perfil_superficie": return CrearPerfilSuperficie(p, method);
                case "civil.perfil_constante": return CrearPerfilConstante(p, method);
                case "civil.vista_perfil": return CrearVistaPerfil(p, method);
                case "civil.hatch_vista_perfil": return HatchVistaPerfil(p, method);
                case "estilos.listar": return EstilosListar(p);
                case "estilos.crear": return EstilosCrear(p, method);
                case "estilos.display": return EstilosDisplay(p, method);
                case "estilos.purgar": return EstilosPurgar(p, method);
#endif
                case "entity.create": return CrearEntidadesNativo(p, method);
                case "entity.draworder": return OrdenDibujo(p, method);
                case "objects.erase": return BorrarObjetos(p, method);
                case "vista.exportar": return VistaExportar(p, method);
                case "vista.papeles": return VistaPapeles(p);
                case "vista.guardada": return VistaGuardada(p, method);
                case "vista.activar": return VistaActivar(p);
                case "vista.3d": return Vista3d(p, method);
                case "layout.crear": return LayoutCrear(p, method);
                case "doc.undo": return DocUndo(p, method);
                default:
#if CIVIL3D
                    var rpt = DispatchPuntos(method, p);
                    if (rpt != null) return rpt;
                    var rgm = DispatchGm(method, p);
                    if (rgm != null) return rgm;
#endif
                    throw new BridgeException(Rpc.ErrMethod, "metodo desconocido: " + method);
            }
        }

        // ---------- utilidades de parametros ----------

        private static string Txt(JsonObject p, string k)
        {
            var n = p[k];
            if (n == null) return null;
            try { return n.GetValue<string>(); } catch { return n.ToJsonString().Trim('"'); }
        }

        private static double? Num(JsonObject p, string k)
        {
            var n = p[k];
            if (n == null) return null;
            try { return n.GetValue<double>(); } catch { }
            double d;
            var s = Txt(p, k);
            if (s != null && double.TryParse(s, System.Globalization.NumberStyles.Float,
                System.Globalization.CultureInfo.InvariantCulture, out d)) return d;
            return null;
        }

        private static bool Flag(JsonObject p, string k)
        {
            var n = p[k];
            if (n == null) return false;
            try { return n.GetValue<bool>(); } catch { return Txt(p, k) == "true"; }
        }

        private static Point3d PuntoDe(JsonNode n, string quees)
        {
            var a = n as JsonArray;
            if (a == null || a.Count < 2)
                throw new BridgeException(Rpc.ErrParams, quees + " debe ser [x,y] o [x,y,z]");
            double x = a[0].GetValue<double>(), y = a[1].GetValue<double>();
            double z = a.Count > 2 ? a[2].GetValue<double>() : 0.0;
            return new Point3d(x, y, z);
        }

        private static string NombreDe(object ob)
        {
            if (ob == null) return null;
            foreach (var pr in ob.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
            {
                if (pr.Name != "Name" || !pr.CanRead || pr.GetIndexParameters().Length != 0) continue;
                try { return pr.GetValue(ob) as string; } catch { }
            }
            var g = ob.GetType().GetMethod("get_Name", BindingFlags.Public | BindingFlags.Instance, null, Type.EmptyTypes, null);
            if (g != null)
            {
                try { return g.Invoke(ob, null) as string; } catch { }
            }
            return null;
        }

        private static ObjectId ResolverId(Transaction tr, Database db, IEnumerable ids, string clave, string quees)
        {
            if (string.IsNullOrWhiteSpace(clave))
                throw new BridgeException(Rpc.ErrParams, "falta " + quees);
            if (Regex.IsMatch(clave, "^[0-9A-Fa-f]{1,16}$"))
            {
                try
                {
                    var idh = IdFromHandle(db, clave);
                    if (!idh.IsNull && !idh.IsErased) return idh;
                }
                catch { }
            }
            foreach (var o in ids)
            {
                if (!(o is ObjectId id) || id.IsNull || id.IsErased) continue;
                var ob = tr.GetObject(id, OpenMode.ForRead);
                var nombre = NombreDe(ob);
                if (string.Equals(nombre, clave, StringComparison.OrdinalIgnoreCase)) return id;
            }
            throw new BridgeException(Rpc.ErrParams, "no se encontro " + quees + " '" + clave + "'");
        }

        private static ObjectId CapaId(Transaction tr, Database db, string nombre, bool crear)
        {
            if (string.IsNullOrWhiteSpace(nombre)) return db.Clayer;
            var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
            if (lt.Has(nombre)) return lt[nombre];
            if (!crear) throw new BridgeException(Rpc.ErrParams, "no existe la capa " + nombre);
            lt.UpgradeOpen();
            var ltr = new LayerTableRecord { Name = nombre };
            var id = lt.Add(ltr);
            tr.AddNewlyCreatedDBObject(ltr, true);
            return id;
        }

        private static Color ColorDe(JsonNode n)
        {
            if (n == null) return null;
            if (n is JsonArray a && a.Count == 3)
                return Color.FromRgb((byte)a[0].GetValue<double>(), (byte)a[1].GetValue<double>(), (byte)a[2].GetValue<double>());
            int aci;
            try { aci = (int)n.GetValue<double>(); }
            catch { aci = int.Parse(n.ToJsonString().Trim('"')); }
            if (aci < 0 || aci > 256) throw new BridgeException(Rpc.ErrParams, "color ACI fuera de rango: " + aci);
            return Color.FromColorIndex(ColorMethod.ByAci, (short)aci);
        }

        private static string FijarPropiedad(object o, string nombre, object valor)
        {
            var pr = o.GetType().GetProperty(nombre, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
            if (pr == null || !pr.CanWrite) return "la propiedad no existe o es de solo lectura";
            try { pr.SetValue(o, valor is JsonNode jn ? Coerce(JsonToClr(jn), pr.PropertyType) : Coerce(valor, pr.PropertyType)); return null; }
            catch (Exception ex) { return (ex.InnerException ?? ex).Message; }
        }

        // ---------- entidades de dibujo nativas ----------

        private static void AplicarComunes(Entity ent, JsonObject e, Transaction tr, Database db)
        {
            string capa = Txt(e, "capa");
            if (!string.IsNullOrWhiteSpace(capa)) { CapaId(tr, db, capa, true); ent.Layer = capa; }
            if (e["color"] != null) ent.Color = ColorDe(e["color"]);
            string tl = Txt(e, "tipo_linea");
            if (!string.IsNullOrWhiteSpace(tl)) ent.Linetype = tl;
            var g = Num(e, "grosor");
            if (g != null) ent.LineWeight = (LineWeight)(int)Math.Round(g.Value * 100);
        }

        private static Entity EntidadDe(JsonObject e, Transaction tr, Database db)
        {
            string tipo = (Txt(e, "tipo") ?? "").ToLowerInvariant();
            switch (tipo)
            {
                case "linea":
                    return new Line(PuntoDe(e["p1"], "p1"), PuntoDe(e["p2"], "p2"));
                case "polilinea":
                {
                    var puntos = e["puntos"] as JsonArray;
                    if (puntos == null || puntos.Count < 2) throw new BridgeException(Rpc.ErrParams, "polilinea requiere puntos [[x,y],...]");
                    var pl = new Polyline();
                    for (int i = 0; i < puntos.Count; i++)
                    {
                        var pt = PuntoDe(puntos[i], "puntos[" + i + "]");
                        pl.AddVertexAt(i, new Point2d(pt.X, pt.Y), 0, 0, 0);
                    }
                    pl.Closed = Flag(e, "cerrada");
                    var ancho = Num(e, "ancho");
                    if (ancho != null) pl.ConstantWidth = ancho.Value;
                    var elev = Num(e, "elevacion");
                    if (elev != null) pl.Elevation = elev.Value;
                    return pl;
                }
                case "polilinea3d":
                {
                    var puntos = e["puntos"] as JsonArray;
                    if (puntos == null || puntos.Count < 2) throw new BridgeException(Rpc.ErrParams, "polilinea3d requiere puntos [[x,y,z],...]");
                    var pl = new Polyline3d();
                    pl.SetDatabaseDefaults();
                    return pl;   // los vertices se agregan tras anexarla a la BTR (ver CrearEntidadesNativo)
                }
                case "texto":
                {
                    var tx = new DBText
                    {
                        TextString = Txt(e, "texto") ?? "",
                        Height = Num(e, "altura") ?? 2.5,
                        Position = PuntoDe(e["punto"], "punto")
                    };
                    var rot = Num(e, "rotacion");
                    if (rot != null) tx.Rotation = rot.Value * Math.PI / 180.0;
                    if (Flag(e, "centrado"))
                    {
                        tx.HorizontalMode = TextHorizontalMode.TextCenter;
                        tx.VerticalMode = TextVerticalMode.TextVerticalMid;
                        tx.AlignmentPoint = PuntoDe(e["punto"], "punto");
                    }
                    return tx;
                }
                case "mtexto":
                {
                    var mt = new MText
                    {
                        Contents = Txt(e, "texto") ?? "",
                        TextHeight = Num(e, "altura") ?? 2.5,
                        Location = PuntoDe(e["punto"], "punto")
                    };
                    var ancho = Num(e, "ancho");
                    if (ancho != null) mt.Width = ancho.Value;
                    return mt;
                }
                case "circulo":
                    return new Circle(PuntoDe(e["centro"], "centro"), Vector3d.ZAxis, Num(e, "radio") ?? 1.0);
                case "solido":
                    return new Solid(PuntoDe(e["p1"], "p1"), PuntoDe(e["p2"], "p2"),
                                     PuntoDe(e["p3"], "p3"), PuntoDe(e["p4"], "p4"));
                case "punto":
                    return new DBPoint(PuntoDe(e["punto"], "punto"));
                case "cilindro":
                {
                    // base = centro de la cara inferior; eje vertical (Z)
                    var b = PuntoDe(e["base"], "base");
                    double rad = Num(e, "radio") ?? 1.0, alt = Num(e, "altura") ?? 1.0;
                    if (rad <= 0 || alt == 0) throw new BridgeException(Rpc.ErrParams, "cilindro requiere radio > 0 y altura != 0");
                    var sol = new Solid3d();
                    sol.SetDatabaseDefaults();
                    sol.RecordHistory = false;
                    sol.CreateFrustum(Math.Abs(alt), rad, rad, rad);
                    double zc = alt > 0 ? b.Z + alt / 2.0 : b.Z + alt / 2.0;
                    sol.TransformBy(Matrix3d.Displacement(new Vector3d(b.X, b.Y, zc)));
                    return sol;
                }
                case "caja":
                {
                    // esquina = esquina minima; dx, dy, dz tamanos (dz puede ser negativo: hacia abajo)
                    var c = PuntoDe(e["esquina"], "esquina");
                    double dx = Num(e, "dx") ?? 1.0, dy = Num(e, "dy") ?? 1.0, dz = Num(e, "dz") ?? 1.0;
                    if (dx == 0 || dy == 0 || dz == 0) throw new BridgeException(Rpc.ErrParams, "caja requiere dx, dy, dz != 0");
                    var sol = new Solid3d();
                    sol.SetDatabaseDefaults();
                    sol.RecordHistory = false;
                    sol.CreateBox(Math.Abs(dx), Math.Abs(dy), Math.Abs(dz));
                    sol.TransformBy(Matrix3d.Displacement(new Vector3d(c.X + dx / 2.0, c.Y + dy / 2.0, c.Z + dz / 2.0)));
                    return sol;
                }
                default:
                    throw new BridgeException(Rpc.ErrParams, "tipo de entidad no soportado: '" + tipo +
                        "' (soportados: capa, linea, polilinea, polilinea3d, texto, mtexto, circulo, solido, punto, hatch, bloque, cilindro, caja)");
            }
        }

        private static object CrearEntidadesNativo(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            var lista = p["entidades"] as JsonArray;
            if (lista == null || lista.Count == 0)
                throw new BridgeException(Rpc.ErrParams, "entidades debe ser una lista JSON con al menos un elemento");
            var doc = Doc(); var db = doc.Database;
            var creados = new List<object>();
            var errores = new List<object>();
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                var ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite);
                for (int i = 0; i < lista.Count; i++)
                {
                    var e = lista[i] as JsonObject;
                    try
                    {
                        if (e == null) throw new BridgeException(Rpc.ErrParams, "el elemento no es un objeto JSON");
                        string tipo = (Txt(e, "tipo") ?? "").ToLowerInvariant();
                        if (tipo == "capa")
                        {
                            string nombre = Txt(e, "nombre");
                            if (string.IsNullOrWhiteSpace(nombre)) throw new BridgeException(Rpc.ErrParams, "capa requiere nombre");
                            var id = CapaId(tr, db, nombre, true);
                            if (e["color"] != null)
                            {
                                var ltr = (LayerTableRecord)tr.GetObject(id, OpenMode.ForWrite);
                                ltr.Color = ColorDe(e["color"]);
                            }
                            creados.Add(new Dictionary<string, object> { { "indice", i }, { "tipo", "capa" }, { "handle", HandleOf(id) } });
                            continue;
                        }
                        if (tipo == "hatch")
                        {
                            var contornos = e["contornos"] as JsonArray ?? new JsonArray { e["contorno"]?.DeepClone() };
                            var hatch = new Hatch();
                            ms.AppendEntity(hatch);
                            tr.AddNewlyCreatedDBObject(hatch, true);
                            hatch.SetDatabaseDefaults();
                            AplicarComunes(hatch, e, tr, db);
                            hatch.PatternScale = Num(e, "escala") ?? 1.0;
                            hatch.SetHatchPattern(HatchPatternType.PreDefined, (Txt(e, "patron") ?? "SOLID").ToUpperInvariant());
                            var ang = Num(e, "angulo");
                            if (ang != null) hatch.PatternAngle = ang.Value * Math.PI / 180.0;
                            hatch.Associative = false;
                            foreach (var cont in contornos)
                            {
                                var puntos = cont as JsonArray;
                                if (puntos == null || puntos.Count < 3)
                                    throw new BridgeException(Rpc.ErrParams, "cada contorno del hatch requiere >= 3 puntos [x,y]");
                                var p2d = new Point2dCollection();
                                var bulges = new DoubleCollection();
                                foreach (var ptn in puntos)
                                {
                                    var pt = PuntoDe(ptn, "contorno");
                                    p2d.Add(new Point2d(pt.X, pt.Y));
                                    bulges.Add(0);
                                }
                                if (p2d[0] != p2d[p2d.Count - 1]) { p2d.Add(p2d[0]); bulges.Add(0); }
                                hatch.AppendLoop(HatchLoopTypes.Polyline, p2d, bulges);
                            }
                            hatch.EvaluateHatch(true);
                            creados.Add(new Dictionary<string, object> { { "indice", i }, { "tipo", "hatch" }, { "handle", HandleOf(hatch.ObjectId) } });
                            continue;
                        }
                        if (tipo == "bloque")
                        {
                            string nombre = Txt(e, "nombre");
                            if (string.IsNullOrWhiteSpace(nombre) || !bt.Has(nombre))
                                throw new BridgeException(Rpc.ErrParams, "no existe el bloque '" + nombre + "'");
                            var br = new BlockReference(PuntoDe(e["punto"], "punto"), bt[nombre]);
                            var esc = Num(e, "escala");
                            if (esc != null) br.ScaleFactors = new Scale3d(esc.Value);
                            var rot = Num(e, "rotacion");
                            if (rot != null) br.Rotation = rot.Value * Math.PI / 180.0;
                            AplicarComunes(br, e, tr, db);
                            ms.AppendEntity(br);
                            tr.AddNewlyCreatedDBObject(br, true);
                            creados.Add(new Dictionary<string, object> { { "indice", i }, { "tipo", "bloque" }, { "handle", HandleOf(br.ObjectId) } });
                            continue;
                        }
                        var ent = EntidadDe(e, tr, db);
                        AplicarComunes(ent, e, tr, db);
                        ms.AppendEntity(ent);
                        tr.AddNewlyCreatedDBObject(ent, true);
                        if (ent is Polyline3d p3)
                        {
                            var puntos = e["puntos"] as JsonArray;
                            foreach (var ptn in puntos)
                            {
                                var v = new PolylineVertex3d(PuntoDe(ptn, "puntos"));
                                p3.AppendVertex(v);
                                tr.AddNewlyCreatedDBObject(v, true);
                            }
                            if (Flag(e, "cerrada")) p3.Closed = true;
                        }
                        creados.Add(new Dictionary<string, object> { { "indice", i }, { "tipo", Txt(e, "tipo") }, { "handle", HandleOf(ent.ObjectId) } });
                    }
                    catch (Exception ex)
                    {
                        errores.Add(new Dictionary<string, object>
                        { { "indice", i }, { "tipo", e == null ? null : Txt(e, "tipo") }, { "error", (ex.InnerException ?? ex).Message } });
                    }
                }
                tr.Commit();
            }
            Log.Write("entity.create creados=" + creados.Count + " errores=" + errores.Count);
            return new Dictionary<string, object> { { "creados", creados }, { "errores", errores } };
        }

        private static object OrdenDibujo(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            var handles = (p["handles"] as JsonArray)?.Select(x => x.GetValue<string>()).ToList();
            string accion = (Txt(p, "accion") ?? "").ToLowerInvariant();
            if (handles == null || handles.Count == 0) throw new BridgeException(Rpc.ErrParams, "faltan handles");
            if (accion != "arriba" && accion != "abajo" && accion != "encima" && accion != "debajo")
                throw new BridgeException(Rpc.ErrParams, "accion debe ser arriba|abajo|encima|debajo");
            var doc = Doc(); var db = doc.Database;
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                var ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForWrite);
                var dot = (DrawOrderTable)tr.GetObject(ms.DrawOrderTableId, OpenMode.ForWrite);
                var ids = new ObjectIdCollection();
                foreach (var h in handles) ids.Add(IdFromHandle(db, h));
                switch (accion)
                {
                    case "arriba": dot.MoveToTop(ids); break;
                    case "abajo": dot.MoveToBottom(ids); break;
                    case "encima": dot.MoveAbove(ids, IdFromHandle(db, Txt(p, "referencia"))); break;
                    case "debajo": dot.MoveBelow(ids, IdFromHandle(db, Txt(p, "referencia"))); break;
                }
                tr.Commit();
            }
            Log.Write("entity.draworder " + accion + " n=" + handles.Count);
            return new Dictionary<string, object> { { "accion", accion }, { "objetos", handles.Count } };
        }

        private static object BorrarObjetos(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            var handles = (p["handles"] as JsonArray)?.Select(x => x.GetValue<string>()).ToList();
            if (handles == null || handles.Count == 0) throw new BridgeException(Rpc.ErrParams, "faltan handles");
            var doc = Doc(); var db = doc.Database;
            var borrados = new List<string>();
            var fallidos = new Dictionary<string, object>();
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                foreach (var h in handles)
                {
                    try
                    {
                        var ob = tr.GetObject(IdFromHandle(db, h), OpenMode.ForWrite);
                        ob.Erase();
                        borrados.Add(h);
                    }
                    catch (Exception ex) { fallidos[h] = (ex.InnerException ?? ex).Message; }
                }
                tr.Commit();
            }
            Log.Write("objects.erase borrados=" + borrados.Count + " fallidos=" + fallidos.Count);
            return new Dictionary<string, object> { { "borrados", borrados }, { "fallidos", fallidos } };
        }
    }
}
