// CDCRD-Digital - puente MCP para Civil 3D 2027
// Grupos de puntos COGO (membresia por consulta) y superficies TIN.
// Complementa Handlers.cs y HandlersCreacion.cs: DispatchExtra delega aqui.
//
// Por que existe este archivo: la membresia de un point group se define con una
// PointGroupQuery (StandardPointGroupQuery.IncludeRawDescriptions / IncludeNumbers)
// y se aplica con PointGroup.SetQuery(query). Ni objects.invoke ni objects.update
// pueden construir ese objeto, y el COM AeccPointGroup de 2027 no expone la query
// (sondeado el 2026-10-16: solo Name, Description y los overrides de estilo). Lo
// mismo con TinSurface.PointGroupsDefinition.AddPointGroup(ObjectId): el puente no
// convierte un handle en ObjectId al pasar argumentos.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using CivPointGroup = Autodesk.Civil.DatabaseServices.PointGroup;
using CivStdQuery = Autodesk.Civil.DatabaseServices.StandardPointGroupQuery;
using CivTinSurface = Autodesk.Civil.DatabaseServices.TinSurface;

namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        // Devuelve null cuando el metodo no es de este modulo (igual que DispatchGm).
        private static object DispatchPuntos(string method, JsonObject p)
        {
            switch (method)
            {
                case "puntos.grupos": return GruposPuntosListar(p);
                case "puntos.grupo_crear": return GrupoPuntosCrear(p, method);
                case "superficie.crear": return SuperficieCrear(p, method);
                case "superficie.grupos": return SuperficieGrupos(p, method);
                default: return null;
            }
        }

        // ---------- utilidades ----------

        private static object ColeccionGruposPuntos()
        {
            var civil = Civil();
            var pr = civil.GetType().GetProperty("PointGroups",
                BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
            var col = pr == null ? null : pr.GetValue(civil);
            if (col == null)
                throw new BridgeException(Rpc.ErrParams,
                    "esta version no expone CivilDocument.PointGroups (use civil.colecciones)");
            return col;
        }

        private static List<ObjectId> IdsGruposPuntos()
        {
            var salida = new List<ObjectId>();
            var col = ColeccionGruposPuntos();
            var en = col as IEnumerable;
            if (en == null) return salida;
            foreach (var e in en)
            {
                if (e is ObjectId id)
                {
                    if (!id.IsNull && !id.IsErased) salida.Add(id);
                    continue;
                }
                if (e == null) continue;
                // por si la coleccion enumera objetos abiertos en vez de ObjectId
                var pr = e.GetType().GetProperty("ObjectId") ?? e.GetType().GetProperty("Id");
                if (pr == null) continue;
                try
                {
                    var v = pr.GetValue(e);
                    if (v is ObjectId oid && !oid.IsNull && !oid.IsErased) salida.Add(oid);
                }
                catch { }
            }
            return salida;
        }

        private static ObjectId GrupoPuntosPorNombre(Transaction tr, Database db, string clave)
        {
            if (string.IsNullOrWhiteSpace(clave)) return ObjectId.Null;
            foreach (var id in IdsGruposPuntos())
            {
                object ob;
                try { ob = tr.GetObject(id, OpenMode.ForRead); } catch { continue; }
                if (string.Equals(NombreDe(ob), clave, StringComparison.OrdinalIgnoreCase)) return id;
            }
            if (System.Text.RegularExpressions.Regex.IsMatch(clave, "^[0-9A-Fa-f]{1,16}$"))
            {
                try
                {
                    var idh = IdFromHandle(db, clave);
                    if (!idh.IsNull && !idh.IsErased) return idh;
                }
                catch { }
            }
            return ObjectId.Null;
        }

        // "A*,B*" tanto si llega como texto o como arreglo JSON de textos.
        private static string ListaTexto(JsonObject p, string clave)
        {
            var n = p[clave];
            if (n == null) return null;
            if (n is JsonArray a)
            {
                var partes = new List<string>();
                foreach (var e in a)
                {
                    if (e == null) continue;
                    string s;
                    try { s = e.GetValue<string>(); } catch { s = e.ToJsonString().Trim('"'); }
                    if (!string.IsNullOrWhiteSpace(s)) partes.Add(s.Trim());
                }
                return partes.Count == 0 ? null : string.Join(",", partes);
            }
            var t = Txt(p, clave);
            return string.IsNullOrWhiteSpace(t) ? null : t;
        }

        private static List<string> ListaValores(JsonObject p, string clave)
        {
            var junto = ListaTexto(p, clave);
            if (junto == null) return new List<string>();
            return junto.Split(',').Select(x => x.Trim()).Where(x => x.Length > 0).ToList();
        }

        private static Dictionary<string, object> DescribirConsulta(object q)
        {
            var d = new Dictionary<string, object>();
            if (q == null) return d;
            d["tipo"] = q.GetType().Name;
            foreach (var pr in q.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
            {
                if (!pr.CanRead || pr.GetIndexParameters().Length != 0) continue;
                object v;
                try { v = pr.GetValue(q); } catch { continue; }
                if (v is string s) { if (s.Length > 0) d[pr.Name] = s; }
                else if (v is bool b) { if (b) d[pr.Name] = true; }
            }
            return d;
        }

        private static Dictionary<string, object> PropiedadesSuperficie(object surf)
        {
            var d = new Dictionary<string, object>();
            object gp;
            try { gp = Invocar(surf, "GetGeneralProperties", new List<object>()); }
            catch (Exception ex) { d["error"] = (ex.InnerException ?? ex).Message; return d; }
            if (gp == null) return d;
            foreach (var pr in gp.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance))
            {
                if (!pr.CanRead || pr.GetIndexParameters().Length != 0) continue;
                try
                {
                    var v = pr.GetValue(gp);
                    if (v == null) continue;
                    var t = v.GetType();
                    if (t.IsPrimitive || v is string || v is decimal) d[pr.Name] = v;
                }
                catch { }
            }
            return d;
        }

        // ---------- puntos.grupos ----------

        private static object GruposPuntosListar(JsonObject p)
        {
            string patron = Txt(p, "patron");
            var db = Doc().Database;
            var filas = new List<object>();
            using (var tr = db.TransactionManager.StartTransaction())
            {
                foreach (var id in IdsGruposPuntos())
                {
                    object ob;
                    try { ob = tr.GetObject(id, OpenMode.ForRead); } catch { continue; }
                    var nm = NombreDe(ob);
                    if (!string.IsNullOrWhiteSpace(patron) && (nm == null ||
                        nm.IndexOf(patron, StringComparison.OrdinalIgnoreCase) < 0)) continue;
                    var fila = new Dictionary<string, object>
                    { { "nombre", nm }, { "handle", HandleOf(id) }, { "tipo", ob.GetType().Name } };
                    var pg = ob as CivPointGroup;
                    if (pg != null)
                    {
                        try { fila["puntos"] = pg.PointsCount; } catch { }
                        try { fila["todos_los_puntos"] = pg.IsAllPointsGroup; } catch { }
                        try { fila["consulta"] = DescribirConsulta(pg.GetQuery()); } catch { }
                        try { fila["estilo_sobrescrito"] = pg.IsPointStyleOverridden; } catch { }
                    }
                    filas.Add(fila);
                }
                tr.Commit();
            }
            return new Dictionary<string, object> { { "cantidad", filas.Count }, { "grupos", filas } };
        }

        // ---------- puntos.grupo_crear ----------

        private static object GrupoPuntosCrear(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string nombre = Txt(p, "nombre");
            if (string.IsNullOrWhiteSpace(nombre))
                throw new BridgeException(Rpc.ErrParams, "falta nombre del grupo");

            string incDesc = ListaTexto(p, "descripciones");
            string incNum = ListaTexto(p, "numeros");
            string incNombres = ListaTexto(p, "nombres_punto");
            string excDesc = ListaTexto(p, "excluir_descripciones");
            string excNum = ListaTexto(p, "excluir_numeros");
            bool todos = Flag(p, "todos");
            if (incDesc == null && incNum == null && incNombres == null && !todos)
                throw new BridgeException(Rpc.ErrParams,
                    "indique al menos descripciones, numeros, nombres_punto o todos=true");
            bool reemplazar = p["reemplazar"] == null || Flag(p, "reemplazar");

            var doc = Doc();
            var db = doc.Database;
            bool creado = false;
            string handle;
            object puntos = null;
            var avisos = new List<string>();

            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var gid = GrupoPuntosPorNombre(tr, db, nombre);
                if (gid.IsNull)
                {
                    var res = Invocar(ColeccionGruposPuntos(), "Add", new List<object> { nombre });
                    if (!(res is ObjectId nuevo) || nuevo.IsNull)
                        throw new BridgeException(Rpc.ErrParams,
                            "PointGroups.Add no devolvio un ObjectId valido");
                    gid = nuevo;
                    creado = true;
                }
                else if (!reemplazar)
                {
                    throw new BridgeException(Rpc.ErrParams, "ya existe el grupo '" + nombre +
                        "'; use reemplazar=true para reescribir su consulta");
                }

                var pg = tr.GetObject(gid, OpenMode.ForWrite) as CivPointGroup;
                if (pg == null)
                    throw new BridgeException(Rpc.ErrParams, "el objeto no es un PointGroup");

                var q = new CivStdQuery();
                q.IncludeAllPoints = todos;
                if (incDesc != null) q.IncludeRawDescriptions = incDesc;
                if (incNum != null) q.IncludeNumbers = incNum;
                if (incNombres != null) q.IncludeNames = incNombres;
                if (excDesc != null) q.ExcludeRawDescriptions = excDesc;
                if (excNum != null) q.ExcludeNumbers = excNum;
                q.UseCaseSensitiveMatch = Flag(p, "case_sensitive");
                pg.SetQuery(q);

                var desc = Txt(p, "descripcion");
                if (desc != null)
                {
                    try { pg.Description = desc; }
                    catch (Exception ex) { avisos.Add("descripcion: " + (ex.InnerException ?? ex).Message); }
                }

                var estilo = Txt(p, "estilo_punto");
                if (!string.IsNullOrWhiteSpace(estilo))
                {
                    var eid = EstiloPorNombre(tr, "PointStyles", estilo, true);
                    pg.PointStyleId = eid;
                    pg.IsPointStyleOverridden = true;
                }
                var etiqueta = Txt(p, "estilo_etiqueta");
                if (!string.IsNullOrWhiteSpace(etiqueta))
                {
                    var lid = EstiloPorNombre(tr, "PointLabelStyles", etiqueta, true);
                    pg.PointLabelStyleId = lid;
                    pg.IsPointLabelStyleOverridden = true;
                }

                try { pg.Update(); }
                catch (Exception ex) { avisos.Add("Update: " + (ex.InnerException ?? ex).Message); }
                try { puntos = pg.PointsCount; }
                catch (Exception ex) { avisos.Add("PointsCount: " + (ex.InnerException ?? ex).Message); }
                handle = HandleOf(gid);
                tr.Commit();
            }

            Log.Write("puntos.grupo_crear " + nombre + " creado=" + creado + " puntos=" + puntos);
            var salida = new Dictionary<string, object>
            {
                { "grupo", nombre }, { "handle", handle }, { "creado", creado }, { "puntos", puntos },
                { "consulta", new Dictionary<string, object>
                    {
                        { "IncludeAllPoints", todos }, { "IncludeRawDescriptions", incDesc },
                        { "IncludeNumbers", incNum }, { "IncludeNames", incNombres },
                        { "ExcludeRawDescriptions", excDesc }, { "ExcludeNumbers", excNum }
                    } }
            };
            if (avisos.Count > 0) salida["avisos"] = avisos;
            return salida;
        }

        // ---------- superficie.crear ----------

        private static ObjectId CrearTinSurface(Database db, string nombre, ObjectId estilo)
        {
            var t = typeof(CivTinSurface);
            if (!estilo.IsNull)
            {
                var m2 = t.GetMethod("Create", BindingFlags.Public | BindingFlags.Static, null,
                    new[] { typeof(string), typeof(ObjectId) }, null);
                if (m2 != null) return (ObjectId)m2.Invoke(null, new object[] { nombre, estilo });
            }
            var m1 = t.GetMethod("Create", BindingFlags.Public | BindingFlags.Static, null,
                new[] { typeof(Database), typeof(string) }, null);
            if (m1 != null) return (ObjectId)m1.Invoke(null, new object[] { db, nombre });
            throw new BridgeException(Rpc.ErrParams,
                "TinSurface.Create no tiene una sobrecarga conocida en esta version");
        }

        private static object SuperficieCrear(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string nombre = Txt(p, "nombre");
            if (string.IsNullOrWhiteSpace(nombre))
                throw new BridgeException(Rpc.ErrParams, "falta nombre de la superficie");

            var doc = Doc();
            var db = doc.Database;
            bool creada = false;
            string handle;

            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var civil = Civil();
                var sid = ObjectId.Null;
                foreach (ObjectId id in civil.GetSurfaceIds())
                {
                    if (id.IsNull || id.IsErased) continue;
                    var ob = tr.GetObject(id, OpenMode.ForRead);
                    if (string.Equals(NombreDe(ob), nombre, StringComparison.OrdinalIgnoreCase))
                    { sid = id; break; }
                }
                if (sid.IsNull)
                {
                    var estilo = EstiloPorNombre(tr, "SurfaceStyles", Txt(p, "estilo"), false);
                    sid = CrearTinSurface(db, nombre, estilo);
                    creada = true;
                }
                var surf = tr.GetObject(sid, OpenMode.ForWrite) as CivTinSurface;
                if (surf == null)
                    throw new BridgeException(Rpc.ErrParams, "el objeto '" + nombre + "' no es una TinSurface");
                var capa = Txt(p, "capa");
                if (!string.IsNullOrWhiteSpace(capa)) surf.LayerId = CapaId(tr, db, capa, true);
                handle = HandleOf(sid);
                tr.Commit();
            }

            Log.Write("superficie.crear " + nombre + " creada=" + creada);
            return new Dictionary<string, object>
            { { "superficie", nombre }, { "handle", handle }, { "creada", creada }, { "ya_existia", !creada } };
        }

        // ---------- superficie.grupos ----------

        private static object SuperficieGrupos(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string clave = Txt(p, "superficie");
            var grupos = ListaValores(p, "grupos");
            if (grupos.Count == 0)
                throw new BridgeException(Rpc.ErrParams, "indique al menos un grupo de puntos");
            bool rebuild = p["rebuild"] == null || Flag(p, "rebuild");

            var doc = Doc();
            var db = doc.Database;
            var agregados = new List<string>();
            var fallidos = new Dictionary<string, object>();
            Dictionary<string, object> estad;
            string handle;
            int definiciones;

            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var civil = Civil();
                var sid = ResolverId(tr, db, civil.GetSurfaceIds(), clave, "la superficie");
                var surf = tr.GetObject(sid, OpenMode.ForWrite) as CivTinSurface;
                if (surf == null)
                    throw new BridgeException(Rpc.ErrParams, "el objeto no es una TinSurface");
                var def = surf.PointGroupsDefinition;
                foreach (var g in grupos)
                {
                    var gid = GrupoPuntosPorNombre(tr, db, g);
                    if (gid.IsNull) { fallidos[g] = "no existe el grupo de puntos"; continue; }
                    try { def.AddPointGroup(gid); agregados.Add(g); }
                    catch (Exception ex) { fallidos[g] = (ex.InnerException ?? ex).Message; }
                }
                if (rebuild)
                {
                    try { surf.Rebuild(); }
                    catch (Exception ex) { fallidos["rebuild"] = (ex.InnerException ?? ex).Message; }
                }
                definiciones = def.Count;
                estad = PropiedadesSuperficie(surf);
                handle = HandleOf(sid);
                tr.Commit();
            }

            Log.Write("superficie.grupos " + clave + " agregados=" + agregados.Count);
            return new Dictionary<string, object>
            {
                { "superficie", clave }, { "handle", handle }, { "agregados", agregados },
                { "fallidos", fallidos }, { "definiciones_grupo", definiciones },
                { "rebuild", rebuild }, { "estadisticas", estad }
            };
        }
    }
}
