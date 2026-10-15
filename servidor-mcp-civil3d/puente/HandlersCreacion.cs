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
using CivApp = Autodesk.Civil.ApplicationServices.CivilApplication;
using CivDoc = Autodesk.Civil.ApplicationServices.CivilDocument;
using CivProfile = Autodesk.Civil.DatabaseServices.Profile;
using CivProfileView = Autodesk.Civil.DatabaseServices.ProfileView;
using CivAlignment = Autodesk.Civil.DatabaseServices.Alignment;

namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        private static object DispatchExtra(string method, JsonObject p)
        {
            switch (method)
            {
                case "civil.perfil_superficie": return CrearPerfilSuperficie(p, method);
                case "civil.perfil_constante": return CrearPerfilConstante(p, method);
                case "civil.vista_perfil": return CrearVistaPerfil(p, method);
                case "civil.hatch_vista_perfil": return HatchVistaPerfil(p, method);
                case "estilos.listar": return EstilosListar(p);
                case "estilos.crear": return EstilosCrear(p, method);
                case "estilos.display": return EstilosDisplay(p, method);
                case "estilos.purgar": return EstilosPurgar(p, method);
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
                default: throw new BridgeException(Rpc.ErrMethod, "metodo desconocido: " + method);
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

        // ---------- resolucion por nombre o handle ----------

        private static CivDoc Civil()
        {
            var cd = CivApp.ActiveDocument;
            if (cd == null) throw new BridgeException(Rpc.ErrNoDoc, "CivilApplication.ActiveDocument devolvio null");
            return cd;
        }


        // Los estilos declaran un Name solo-escritura que oculta al legible de la
        // base: GetProperty("Name").GetValue lanza "Property Get method was not
        // found". Este lector busca cualquier Name legible en la jerarquia.
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

        private static object ColeccionEstilos(string familia)
        {
            var styles = Civil().Styles;
            var pr = styles.GetType().GetProperty(familia,
                BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
            if (pr != null) return pr.GetValue(styles);
            foreach (var raizNombre in new[] { "LabelSetStyles", "BandStyles", "LabelStyles", "TableStyles" })
            {
                var raizProp = styles.GetType().GetProperty(raizNombre);
                var raiz = raizProp == null ? null : raizProp.GetValue(styles);
                if (raiz == null) continue;
                var sub = raiz.GetType().GetProperty(familia,
                    BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                if (sub != null) return sub.GetValue(raiz);
            }
            throw new BridgeException(Rpc.ErrParams, "familia de estilos desconocida: " + familia +
                " (use estilos.listar para ver las familias)");
        }

        private static ObjectId EstiloPorNombre(Transaction tr, string familia, string nombre, bool obligatorio)
        {
            if (string.IsNullOrWhiteSpace(nombre))
            {
                if (!obligatorio) return ObjectId.Null;
                throw new BridgeException(Rpc.ErrParams, "falta el nombre del estilo (" + familia + ")");
            }
            var col = ColeccionEstilos(familia);
            var idx = col.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance)
                .FirstOrDefault(x => x.GetIndexParameters().Length == 1 &&
                                     x.GetIndexParameters()[0].ParameterType == typeof(string));
            if (idx != null)
            {
                try
                {
                    var v = idx.GetValue(col, new object[] { nombre });
                    if (v is ObjectId oid && !oid.IsNull) return oid;
                }
                catch { }
            }
            if (col is IEnumerable en)
            {
                foreach (var e in en)
                {
                    ObjectId id = e is ObjectId o ? o : ObjectId.Null;
                    if (id.IsNull) continue;
                    var ob = tr.GetObject(id, OpenMode.ForRead);
                    var nm = NombreDe(ob);
                    if (string.Equals(nm, nombre, StringComparison.OrdinalIgnoreCase)) return id;
                }
            }
            if (!obligatorio) return ObjectId.Null;
            throw new BridgeException(Rpc.ErrParams, "no existe el estilo '" + nombre + "' en " + familia);
        }

        private static ObjectId PrimerEstilo(Transaction tr, string familia)
        {
            var col = ColeccionEstilos(familia);
            if (col is IEnumerable en)
                foreach (var e in en)
                    if (e is ObjectId id && !id.IsNull) return id;
            throw new BridgeException(Rpc.ErrParams, "la familia " + familia + " no tiene estilos");
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

        private static IEnumerable<ObjectId> TodasVistasPerfil(Transaction tr, CivDoc civil)
        {
            foreach (var a in civil.GetAlignmentIds())
            {
                if (!(a is ObjectId aid) || aid.IsNull || aid.IsErased) continue;
                var alin = (CivAlignment)tr.GetObject(aid, OpenMode.ForRead);
                foreach (ObjectId v in alin.GetProfileViewIds())
                    if (!v.IsNull && !v.IsErased) yield return v;
            }
        }

        // ---------- perfiles y vistas de perfil ----------

        private static ObjectId PerfilExistente(Transaction tr, CivAlignment alin, string nombre)
        {
            foreach (ObjectId pid in alin.GetProfileIds())
            {
                if (pid.IsNull || pid.IsErased) continue;
                var pr = (CivProfile)tr.GetObject(pid, OpenMode.ForRead);
                if (string.Equals(pr.Name, nombre, StringComparison.OrdinalIgnoreCase)) return pid;
            }
            return ObjectId.Null;
        }

        private static Dictionary<string, object> DatosPerfil(Transaction tr, ObjectId pid, bool yaExistia)
        {
            var pr = (CivProfile)tr.GetObject(pid, OpenMode.ForRead);
            return new Dictionary<string, object>
            {
                { "handle", HandleOf(pid) }, { "ya_existia", yaExistia }, { "nombre", pr.Name },
                { "elev_min", pr.ElevationMin }, { "elev_max", pr.ElevationMax },
                { "est_inicio", pr.StartingStation }, { "est_fin", pr.EndingStation },
                { "estilo", LeerProp(pr, "StyleName") }
            };
        }

        // Profile.CreateFromSurface: perfil de superficie nativo (reemplaza el paso de UI).
        private static object CrearPerfilSuperficie(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string nombre = Txt(p, "nombre");
            if (string.IsNullOrWhiteSpace(nombre)) throw new BridgeException(Rpc.ErrParams, "falta nombre");
            var doc = Doc(); var db = doc.Database; var civil = Civil();
            Dictionary<string, object> res;
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var alinId = ResolverId(tr, db, civil.GetAlignmentIds(), Txt(p, "alineamiento"), "el alineamiento");
                var supId = ResolverId(tr, db, civil.GetSurfaceIds(), Txt(p, "superficie"), "la superficie");
                var alin = (CivAlignment)tr.GetObject(alinId, OpenMode.ForRead);
                var previo = PerfilExistente(tr, alin, nombre);
                if (!previo.IsNull)
                {
                    res = DatosPerfil(tr, previo, true);
                    tr.Commit();
                    return res;
                }
                var capaId = CapaId(tr, db, Txt(p, "capa"), true);
                var estiloId = EstiloPorNombre(tr, "ProfileStyles", Txt(p, "estilo"), false);
                if (estiloId.IsNull) estiloId = PrimerEstilo(tr, "ProfileStyles");
                var etiqId = EstiloPorNombre(tr, "ProfileLabelSetStyles", Txt(p, "etiquetas"), false);
                if (etiqId.IsNull) etiqId = PrimerEstilo(tr, "ProfileLabelSetStyles");
                var nuevo = CivProfile.CreateFromSurface(nombre, alinId, supId, capaId, estiloId, etiqId);
                res = DatosPerfil(tr, nuevo, false);
                tr.Commit();
            }
            Log.Write("civil.perfil_superficie '" + nombre + "'");
            return res;
        }

        // Perfil de elevacion constante (CreateByLayout + 2 PVIs). Sirve de limite
        // inferior para hatch hasta cota fija, actualizable y 100% nativo.
        private static object CrearPerfilConstante(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string nombre = Txt(p, "nombre");
            var elev = Num(p, "elevacion");
            if (string.IsNullOrWhiteSpace(nombre)) throw new BridgeException(Rpc.ErrParams, "falta nombre");
            if (elev == null) throw new BridgeException(Rpc.ErrParams, "falta elevacion");
            var doc = Doc(); var db = doc.Database; var civil = Civil();
            Dictionary<string, object> res;
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var alinId = ResolverId(tr, db, civil.GetAlignmentIds(), Txt(p, "alineamiento"), "el alineamiento");
                var alin = (CivAlignment)tr.GetObject(alinId, OpenMode.ForRead);
                var previo = PerfilExistente(tr, alin, nombre);
                if (!previo.IsNull)
                {
                    res = DatosPerfil(tr, previo, true);
                    tr.Commit();
                    return res;
                }
                var capaId = CapaId(tr, db, Txt(p, "capa"), true);
                var estiloId = EstiloPorNombre(tr, "ProfileStyles", Txt(p, "estilo"), false);
                if (estiloId.IsNull) estiloId = PrimerEstilo(tr, "ProfileStyles");
                var etiqId = EstiloPorNombre(tr, "ProfileLabelSetStyles", Txt(p, "etiquetas"), false);
                if (etiqId.IsNull) etiqId = PrimerEstilo(tr, "ProfileLabelSetStyles");
                var nuevo = CivProfile.CreateByLayout(nombre, alinId, capaId, estiloId, etiqId);
                var perfil = (CivProfile)tr.GetObject(nuevo, OpenMode.ForWrite);
                double e0 = Num(p, "est_inicio") ?? alin.StartingStation;
                double e1 = Num(p, "est_fin") ?? alin.EndingStation;
                perfil.PVIs.AddPVI(e0, elev.Value);
                perfil.PVIs.AddPVI(e1, elev.Value);
                res = DatosPerfil(tr, nuevo, false);
                tr.Commit();
            }
            Log.Write("civil.perfil_constante '" + nombre + "' @" + elev.Value);
            return res;
        }

        // ProfileView.Create + rangos de estacion/elevacion + Location real de una vez.
        private static object CrearVistaPerfil(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string nombre = Txt(p, "nombre");
            if (string.IsNullOrWhiteSpace(nombre)) throw new BridgeException(Rpc.ErrParams, "falta nombre");
            if (p["origen"] == null) throw new BridgeException(Rpc.ErrParams, "falta origen [x,y]");
            var origen = PuntoDe(p["origen"], "origen");
            var doc = Doc(); var db = doc.Database; var civil = Civil();
            Dictionary<string, object> res;
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var alinId = ResolverId(tr, db, civil.GetAlignmentIds(), Txt(p, "alineamiento"), "el alineamiento");
                ObjectId pvId = ObjectId.Null;
                bool yaExistia = false;
                foreach (var id in TodasVistasPerfil(tr, civil))
                {
                    var previa = (CivProfileView)tr.GetObject(id, OpenMode.ForRead);
                    if (string.Equals(previa.Name, nombre, StringComparison.OrdinalIgnoreCase))
                    { pvId = id; yaExistia = true; break; }
                }
                if (pvId.IsNull) pvId = CivProfileView.Create(alinId, origen);
                var pv = (CivProfileView)tr.GetObject(pvId, OpenMode.ForWrite);
                var fallidos = new Dictionary<string, object>();
                void Aplicar(string prop, object valor)
                {
                    if (valor == null) return;
                    var e = FijarPropiedad(pv, prop, valor);
                    if (e != null) fallidos[prop] = e;
                }
                Aplicar("Name", nombre);
                var estilo = Txt(p, "estilo");
                if (!string.IsNullOrWhiteSpace(estilo))
                {
                    var estId = EstiloPorNombre(tr, "ProfileViewStyles", estilo, true);
                    var err = FijarPropiedad(pv, "StyleId", estId);
                    if (err != null) Aplicar("StyleName", estilo);
                }
                var est0 = Num(p, "est_inicio"); var est1 = Num(p, "est_fin");
                if (est0 != null || est1 != null) Aplicar("StationRangeMode", "UserSpecified");
                Aplicar("StationStart", est0);
                Aplicar("StationEnd", est1);
                var el0 = Num(p, "elev_min"); var el1 = Num(p, "elev_max");
                if (el0 != null || el1 != null) Aplicar("ElevationRangeMode", "UserSpecified");
                Aplicar("ElevationMin", el0);
                Aplicar("ElevationMax", el1);
                // fijar StationStart desplaza Location: se reescribe al final
                Aplicar("Location", new List<object> { origen.X, origen.Y, origen.Z });
                var banda = Txt(p, "banda");
                if (!string.IsNullOrWhiteSpace(banda))
                {
                    try
                    {
                        var bandaId = EstiloPorNombre(tr, "ProfileViewBandSetStyles", banda, true);
                        var bands = pv.GetType().GetProperty("Bands")?.GetValue(pv);
                        var im = bands?.GetType().GetMethod("ImportBandSetStyle", new[] { typeof(ObjectId) });
                        if (im == null) fallidos["banda"] = "no se encontro Bands.ImportBandSetStyle(ObjectId)";
                        else im.Invoke(bands, new object[] { bandaId });
                    }
                    catch (Exception ex) { fallidos["banda"] = (ex.InnerException ?? ex).Message; }
                }
                res = new Dictionary<string, object>
                {
                    { "handle", HandleOf(pvId) }, { "ya_existia", yaExistia }, { "nombre", pv.Name },
                    { "location", Val(pv.Location) },
                    { "est_inicio", LeerProp(pv, "StationStart") }, { "est_fin", LeerProp(pv, "StationEnd") },
                    { "elev_min", LeerProp(pv, "ElevationMin") }, { "elev_max", LeerProp(pv, "ElevationMax") },
                    { "fallidos", fallidos }
                };
                tr.Commit();
            }
            Log.Write("civil.vista_perfil '" + nombre + "'");
            return res;
        }

        // Hatch nativo de la vista de perfil: ProfileView.HatchAreas.Add(nombre,
        // perfil_superior, perfil_inferior, estilo_forma). Equivale a Profile View
        // Properties > Hatch > Cut Area.
        private static object HatchVistaPerfil(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string nombre = Txt(p, "nombre");
            if (string.IsNullOrWhiteSpace(nombre)) throw new BridgeException(Rpc.ErrParams, "falta nombre");
            bool quitar = Flag(p, "quitar");
            var doc = Doc(); var db = doc.Database; var civil = Civil();
            Dictionary<string, object> res;
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var pvId = ResolverId(tr, db, TodasVistasPerfil(tr, civil).ToList(), Txt(p, "vista"), "la vista de perfil");
                var pv = (CivProfileView)tr.GetObject(pvId, OpenMode.ForWrite);
                var col = pv.HatchAreas;
                var existentes = new List<string>();
                foreach (var it in (IEnumerable)col)
                {
                    var nm = NombreDe(it);
                    if (nm != null) existentes.Add(nm);
                }
                if (quitar)
                {
                    if (!existentes.Contains(nombre))
                        throw new BridgeException(Rpc.ErrParams, "no hay hatch '" + nombre + "' en la vista (hay: " +
                            string.Join(", ", existentes) + ")");
                    col.Remove(nombre);
                    res = new Dictionary<string, object> { { "quitado", nombre } };
                    tr.Commit();
                    return res;
                }
                bool yaExistia = existentes.Contains(nombre);
                if (!yaExistia)
                {
                    var alinId = (ObjectId)pv.GetType().GetProperty("AlignmentId").GetValue(pv);
                    var alin = (CivAlignment)tr.GetObject(alinId, OpenMode.ForRead);
                    var supId = ResolverId(tr, db, alin.GetProfileIds(), Txt(p, "superior"), "el perfil superior");
                    var infId = ResolverId(tr, db, alin.GetProfileIds(), Txt(p, "inferior"), "el perfil inferior");
                    var estiloId = EstiloPorNombre(tr, "ShapeStyles", Txt(p, "estilo_forma"), true);
                    col.Add(nombre, supId, infId, estiloId);
                }
                res = new Dictionary<string, object>
                {
                    { "vista", HandleOf(pvId) }, { "nombre", nombre }, { "ya_existia", yaExistia },
                    { "hatches", Val(col, 0, 2) }
                };
                tr.Commit();
            }
            Log.Write("civil.hatch_vista_perfil '" + nombre + "'");
            return res;
        }

        // ---------- estilos ----------

        private static IEnumerable<KeyValuePair<string, object>> FamiliasEstilos()
        {
            var styles = Civil().Styles;
            foreach (var pr in styles.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
            {
                if (pr.GetIndexParameters().Length != 0 || !pr.CanRead) continue;
                object v;
                try { v = pr.GetValue(styles); } catch { continue; }
                if (v == null) continue;
                if (v.GetType().Name.EndsWith("Root"))
                {
                    foreach (var sub in v.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
                    {
                        if (sub.GetIndexParameters().Length != 0 || !sub.CanRead) continue;
                        object sv;
                        try { sv = sub.GetValue(v); } catch { continue; }
                        if (sv is IEnumerable && !(sv is string))
                            yield return new KeyValuePair<string, object>(sub.Name, sv);
                    }
                }
                else if (v is IEnumerable && !(v is string))
                    yield return new KeyValuePair<string, object>(pr.Name, v);
            }
        }

        private static object EstilosListar(JsonObject p)
        {
            string familia = Txt(p, "familia");
            string patron = Txt(p, "patron");
            Regex rx = null;
            if (!string.IsNullOrWhiteSpace(patron))
            {
                try { rx = new Regex(patron, RegexOptions.IgnoreCase); }
                catch (Exception ex) { throw new BridgeException(Rpc.ErrParams, "patron invalido: " + ex.Message); }
            }
            var db = Doc().Database;
            var filas = new List<object>();
            var familias = new List<string>();
            using (var tr = db.TransactionManager.StartTransaction())
            {
                foreach (var kv in FamiliasEstilos())
                {
                    familias.Add(kv.Key);
                    if (!string.IsNullOrWhiteSpace(familia) &&
                        kv.Key.IndexOf(familia, StringComparison.OrdinalIgnoreCase) < 0) continue;
                    foreach (var e in (IEnumerable)kv.Value)
                    {
                        if (!(e is ObjectId id) || id.IsNull || id.IsErased) continue;
                        object ob;
                        try { ob = tr.GetObject(id, OpenMode.ForRead); } catch { continue; }
                        var nm = NombreDe(ob);
                        if (rx != null && (nm == null || !rx.IsMatch(nm))) continue;
                        filas.Add(new Dictionary<string, object>
                        {
                            { "familia", kv.Key }, { "nombre", nm },
                            { "handle", HandleOf(id) }, { "tipo", ob.GetType().Name }
                        });
                    }
                }
                tr.Commit();
            }
            return new Dictionary<string, object>
            {
                { "cantidad", filas.Count }, { "estilos", filas },
                { "familias", familias.OrderBy(x => x).ToList() }
            };
        }

        private static object EstilosCrear(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string familia = Txt(p, "familia");
            string nombre = Txt(p, "nombre");
            string basee = Txt(p, "base");
            if (string.IsNullOrWhiteSpace(familia) || string.IsNullOrWhiteSpace(nombre))
                throw new BridgeException(Rpc.ErrParams, "se requieren familia y nombre");
            var doc = Doc(); var db = doc.Database;
            Dictionary<string, object> res;
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var previo = EstiloPorNombre(tr, familia, nombre, false);
                if (!previo.IsNull)
                {
                    res = new Dictionary<string, object>
                    { { "handle", HandleOf(previo) }, { "ya_existia", true }, { "nombre", nombre }, { "familia", familia } };
                    tr.Commit();
                    return res;
                }
                ObjectId nuevo = ObjectId.Null;
                if (!string.IsNullOrWhiteSpace(basee))
                {
                    var baseId = EstiloPorNombre(tr, familia, basee, true);
                    var ob = tr.GetObject(baseId, OpenMode.ForRead);
                    var ret = Invocar(ob, "CopyAsSibling", new List<object> { nombre });
                    if (ret is ObjectId rid && !rid.IsNull) nuevo = rid;
                    else nuevo = EstiloPorNombre(tr, familia, nombre, false);
                    if (nuevo.IsNull)
                        throw new BridgeException(Rpc.ErrInternal, "CopyAsSibling devolvio nulo para '" +
                            nombre + "' (el nombre puede estar ocupado por un estilo recien borrado y no purgado)");
                }
                else
                {
                    var col = ColeccionEstilos(familia);
                    var add = col.GetType().GetMethod("Add", new[] { typeof(string) });
                    if (add == null)
                        throw new BridgeException(Rpc.ErrParams, familia +
                            " no admite Add(nombre); indique 'base' para clonar un estilo existente");
                    var ret = add.Invoke(col, new object[] { nombre });
                    if (ret is ObjectId rid) nuevo = rid;
                    else nuevo = EstiloPorNombre(tr, familia, nombre, true);
                }
                res = new Dictionary<string, object>
                { { "handle", HandleOf(nuevo) }, { "ya_existia", false }, { "nombre", nombre }, { "familia", familia }, { "base", basee } };
                tr.Commit();
            }
            Log.Write("estilos.crear " + familia + " '" + nombre + "'");
            return res;
        }

        // Edita el DisplayStyle de un componente de un estilo: color, capa, tipo de
        // linea, grosor, visibilidad. vista = sufijo del metodo GetDisplayStyle*
        // (Profile, Plan, Section, Model...); componente = valor del enum (Line,
        // Circular Curve sin espacios: CircularCurve...).
        private static object EstilosDisplay(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            var doc = Doc(); var db = doc.Database;
            string vista = Txt(p, "vista") ?? "Profile";
            string componente = Txt(p, "componente");
            Dictionary<string, object> res;
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                ObjectId id;
                string handle = Txt(p, "handle");
                if (!string.IsNullOrWhiteSpace(handle)) id = IdFromHandle(db, handle);
                else id = EstiloPorNombre(tr, Txt(p, "familia") ?? "", Txt(p, "estilo"), true);
                var estilo = tr.GetObject(id, OpenMode.ForWrite);
                var metodo = estilo.GetType().GetMethods(BindingFlags.Public | BindingFlags.Instance)
                    .Where(m => string.Equals(m.Name, "GetDisplayStyle" + vista, StringComparison.OrdinalIgnoreCase))
                    .OrderBy(m => m.GetParameters().Length)
                    .LastOrDefault();
                if (metodo == null)
                {
                    var disponibles = estilo.GetType().GetMethods(BindingFlags.Public | BindingFlags.Instance)
                        .Where(m => m.Name.StartsWith("GetDisplayStyle")).Select(m => m.Name).Distinct().ToList();
                    throw new BridgeException(Rpc.ErrParams, "el estilo " + estilo.GetType().Name +
                        " no tiene GetDisplayStyle" + vista + "; tiene: " + string.Join(", ", disponibles));
                }
                object ds;
                var pars = metodo.GetParameters();
                if (pars.Length == 0) ds = metodo.Invoke(estilo, null);
                else if (pars.Length == 1 && pars[0].ParameterType.IsEnum)
                {
                    if (string.IsNullOrWhiteSpace(componente))
                        throw new BridgeException(Rpc.ErrParams, "falta componente; valores: " +
                            string.Join(", ", Enum.GetNames(pars[0].ParameterType)));
                    object ev;
                    try { ev = Enum.Parse(pars[0].ParameterType, componente.Replace(" ", ""), true); }
                    catch
                    {
                        throw new BridgeException(Rpc.ErrParams, "componente '" + componente + "' no valido; valores: " +
                            string.Join(", ", Enum.GetNames(pars[0].ParameterType)));
                    }
                    ds = metodo.Invoke(estilo, new[] { ev });
                }
                else throw new BridgeException(Rpc.ErrParams, "firma de " + metodo.Name + " no soportada");
                if (ds == null) throw new BridgeException(Rpc.ErrInternal, metodo.Name + " devolvio null");

                var aplicados = new Dictionary<string, object>();
                var fallidos = new Dictionary<string, object>();
                void Set(string prop, object valor)
                {
                    if (valor == null) return;
                    var e = FijarPropiedad(ds, prop, valor);
                    if (e == null) aplicados[prop] = Val(ds.GetType().GetProperty(prop,
                        BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase)?.GetValue(ds));
                    else fallidos[prop] = e;
                }
                if (p["color_aci"] != null || p["color_rgb"] != null)
                {
                    try
                    {
                        var color = ColorDe(p["color_rgb"] ?? p["color_aci"]);
                        var e = FijarPropiedad(ds, "Color", color);
                        if (e == null) aplicados["Color"] = color.ToString();
                        else fallidos["Color"] = e;
                    }
                    catch (Exception ex) { fallidos["Color"] = (ex.InnerException ?? ex).Message; }
                }
                Set("Layer", Txt(p, "capa"));
                Set("Linetype", Txt(p, "tipo_linea"));
                Set("Lineweight", Txt(p, "grosor"));
                if (p["visible"] != null) Set("Visible", Flag(p, "visible"));
                res = new Dictionary<string, object>
                {
                    { "estilo", HandleOf(id) }, { "metodo", metodo.Name }, { "componente", componente },
                    { "aplicados", aplicados }, { "fallidos", fallidos }
                };
                tr.Commit();
            }
            Log.Write("estilos.display " + Txt(p, "estilo") + "/" + vista + "/" + componente);
            return res;
        }

        private static object EstilosPurgar(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string familia = Txt(p, "familia");
            string patron = Txt(p, "patron");
            if (string.IsNullOrWhiteSpace(familia) || string.IsNullOrWhiteSpace(patron))
                throw new BridgeException(Rpc.ErrParams, "se requieren familia y patron");
            Regex rx;
            try { rx = new Regex(patron, RegexOptions.IgnoreCase); }
            catch (Exception ex) { throw new BridgeException(Rpc.ErrParams, "patron invalido: " + ex.Message); }
            var doc = Doc(); var db = doc.Database;
            var borrados = new List<string>();
            var fallidos = new Dictionary<string, object>();
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var col = ColeccionEstilos(familia);
                var candidatos = new List<KeyValuePair<string, ObjectId>>();
                foreach (var e in (IEnumerable)col)
                {
                    if (!(e is ObjectId id) || id.IsNull || id.IsErased) continue;
                    var ob = tr.GetObject(id, OpenMode.ForRead);
                    var nm = NombreDe(ob);
                    if (nm != null && rx.IsMatch(nm)) candidatos.Add(new KeyValuePair<string, ObjectId>(nm, id));
                }
                foreach (var kv in candidatos)
                {
                    try
                    {
                        var ob = tr.GetObject(kv.Value, OpenMode.ForWrite);
                        ob.Erase();
                        borrados.Add(kv.Key);
                    }
                    catch (Exception ex) { fallidos[kv.Key] = (ex.InnerException ?? ex).Message; }
                }
                tr.Commit();
            }
            Log.Write("estilos.purgar " + familia + " /" + patron + "/ borrados=" + borrados.Count);
            return new Dictionary<string, object> { { "borrados", borrados }, { "fallidos", fallidos } };
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
