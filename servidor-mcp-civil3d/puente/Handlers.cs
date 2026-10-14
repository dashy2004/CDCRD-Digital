// CDCRD-Digital - puente MCP para Civil 3D 2027
// Manejadores. El acceso a los objetos de Civil 3D es por reflexion: asi el puente
// no se rompe cuando cambian firmas entre versiones y cubre cualquier coleccion que
// exponga el CivilDocument de la version instalada.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;

namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        public const string Version = "0.2.0";
        private const int MaxItems = 500;

        // Alias en espanol -> candidatos de miembro del CivilDocument, en orden.
        // En Civil 3D 2027 unas familias son metodos GetXxxIds y otras son
        // propiedades de coleccion (verificado en vivo: CorridorCollection,
        // AssemblyCollection, SubassemblyCollection, CogoPoints, PointGroups).
        // Se prueban en orden y gana el primero que exista; civil.colecciones
        // sigue siendo la fuente de verdad de la instalacion.
        private static readonly Dictionary<string, string[]> Alias = new Dictionary<string, string[]>(StringComparer.OrdinalIgnoreCase)
        {
            { "alineamientos", new[] { "GetAlignmentIds" } },
            { "alineamientos_sin_sitio", new[] { "GetSitelessAlignmentIds" } },
            { "superficies", new[] { "GetSurfaceIds" } },
            { "corredores", new[] { "CorridorCollection", "GetCorridorIds" } },
            { "ensamblajes", new[] { "AssemblyCollection", "GetAssemblyIds" } },
            { "subensamblajes", new[] { "SubassemblyCollection", "GetSubassemblyIds" } },
            { "redes_gravedad", new[] { "GetPipeNetworkIds", "PipeNetworks", "NetworkCollection" } },
            { "redes_presion", new[] { "GetPressurePipeNetworkIds", "PressurePipeNetworks" } },
            { "sitios", new[] { "GetSiteIds" } },
            { "grupos_puntos", new[] { "PointGroups", "GetPointGroupIds" } },
            { "puntos", new[] { "CogoPoints", "GetAllPointIds" } },
            { "grupos_view_frame", new[] { "GetViewFrameGroupIds", "ViewFrameGroups" } },
            { "vistas_perfil", new[] { "GetProfileViewIds", "ProfileViews" } },
            { "vistas_seccion", new[] { "GetSectionViewIds", "SectionViews" } },
            { "cuencas", new[] { "GetCatchmentIds", "Catchments" } },
            { "grupos_cuencas", new[] { "GetCatchmentGroupIds" } },
            { "tablas_alineamiento", new[] { "GetAlignmentTableIds" } },
            { "puentes", new[] { "GetBridgeIds" } },
            { "intersecciones", new[] { "GetIntersectionIds" } },
            { "estilos", new[] { "Styles" } }
        };

        private static readonly string[] ReadOnlyMethodPatterns =
        {
            "^Get", "^Find", "^Sample", "^Station", "^PointLocation", "^Has", "^Is", "^Compute", "^Count",
            "^ElevationAt", "^PointAt", "^DistanceTo", "^Contains", "^Offset"
        };

        public static object Dispatch(string method, JsonObject p)
        {
            switch (method)
            {
                case "doc.info": return DocInfo();
                case "civil.colecciones": return CivilCollections();
                case "types.discover": return TypesDiscover(p);
                case "objects.query": return ObjectsQuery(p);
                case "objects.aggregate": return ObjectsAggregate(p);
                case "objects.props": return ObjectsProps(p);
                case "objects.update": return ObjectsUpdate(p, method);
                case "objects.invoke": return ObjectsInvoke(p, method);
                case "selection.set": return SelectionSet(p);
                case "view.zoom": return ViewZoom(p);
                case "cmd.run": return CmdRun(p, method);
                case "objects.read": return ObjectsRead(p);
                case "layers.query": return LayersQuery(p);
                case "layers.set": return LayersSet(p, method);
                case "doc.save": return DocSave(p, method);
                default: return DispatchExtra(method, p);
            }
        }

        // ---------- utilidades ----------

        private static Autodesk.AutoCAD.ApplicationServices.Document Doc()
        {
            var d = AcApp.DocumentManager.MdiActiveDocument;
            if (d == null) throw new BridgeException(Rpc.ErrNoDoc, "no hay dibujo abierto en Civil 3D");
            return d;
        }

        private static Type FindType(string full)
        {
            foreach (var a in AppDomain.CurrentDomain.GetAssemblies())
            {
                try { var t = a.GetType(full); if (t != null) return t; } catch { }
            }
            foreach (var name in new[] { "AeccDbMgd", "AeccUiMgd", "AeccPressurePipesMgd" })
            {
                try { var t = Assembly.Load(name).GetType(full); if (t != null) return t; } catch { }
            }
            return null;
        }

        private static object CivilDoc()
        {
            var t = FindType("Autodesk.Civil.ApplicationServices.CivilApplication");
            if (t == null) throw new BridgeException(Rpc.ErrNoDoc, "no se encontro la API de Civil 3D (AeccDbMgd): el dibujo puede estar abierto en AutoCAD puro");
            var prop = t.GetProperty("ActiveDocument", BindingFlags.Public | BindingFlags.Static);
            var cd = prop == null ? null : prop.GetValue(null);
            if (cd == null) throw new BridgeException(Rpc.ErrNoDoc, "CivilApplication.ActiveDocument devolvio null");
            return cd;
        }

        private static string HandleOf(ObjectId id)
        {
            return id.Handle.ToString();
        }

        private static ObjectId IdFromHandle(Database db, string handle)
        {
            long h = Convert.ToInt64(handle, 16);
            return db.GetObjectId(false, new Handle(h), 0);
        }

        private static object Val(object v, int depth = 0, int maxExpand = 0)
        {
            if (v == null) return null;
            var t = v.GetType();
            if (v is string || v is bool || v is double || v is float || v is decimal
                || v is int || v is long || v is short || v is byte || v is uint || v is ulong)
                return v is float ? (object)Convert.ToDouble(v) : v;
            if (t.IsEnum) return v.ToString();
            if (v is DateTime dt) return dt.ToString("yyyy-MM-dd HH:mm:ss");
            if (v is ObjectId oid) return oid.IsNull ? null : (object)HandleOf(oid);
            if (v is Handle hh) return hh.ToString();

            // Point3d / Point2d / Vector3d y similares
            var px = t.GetProperty("X"); var py = t.GetProperty("Y");
            if (px != null && py != null && px.PropertyType == typeof(double))
            {
                var pz = t.GetProperty("Z");
                var arr = new List<double> { (double)px.GetValue(v), (double)py.GetValue(v) };
                if (pz != null && pz.PropertyType == typeof(double)) arr.Add((double)pz.GetValue(v));
                return arr;
            }

            if (v is ObjectIdCollection oc)
            {
                var ids = new List<string>();
                foreach (ObjectId i in oc) ids.Add(HandleOf(i));
                return new Dictionary<string, object> { { "cantidad", ids.Count }, { "handles", ids.Take(MaxItems) } };
            }

            // Diccionarios propios del puente (p. ej. {retorno, salidas} de Invocar con ref/out)
            if (v is IDictionary<string, object> dic)
                return dic.ToDictionary(kv => kv.Key, kv => Val(kv.Value, depth, maxExpand));

            if ((depth < 1 || depth <= maxExpand) && v is IEnumerable en && !(v is string))
            {
                var items = new List<object>();
                int n = 0;
                foreach (var e in en)
                {
                    if (n++ >= 50) break;
                    items.Add(Val(e, depth + 1, maxExpand));
                }
                return new Dictionary<string, object> { { "items", items }, { "truncado", n >= 50 } };
            }

            // Expansion bajo demanda: sin maxExpand un objeto compuesto sale como
            // {tipo, texto}, que es lo que hacia opaco a SurfaceAnalysis y companhia.
            if (depth < maxExpand)
            {
                var exp = new Dictionary<string, object> { { "tipo", t.Name } };
                foreach (var pr in t.GetProperties(BindingFlags.Public | BindingFlags.Instance))
                {
                    if (pr.GetIndexParameters().Length != 0 || !pr.CanRead) continue;
                    try { exp[pr.Name] = Val(pr.GetValue(v), depth + 1, maxExpand); }
                    catch (Exception ex) { exp[pr.Name] = "<" + (ex.InnerException ?? ex).GetType().Name + ">"; }
                }
                return exp;
            }

            return new Dictionary<string, object> { { "tipo", t.Name }, { "texto", SafeToString(v) } };
        }

        // IsReadOnly esta declarado en Document, no en Database (y puede moverse entre
        // versiones): se lee por reflexion para no amarrar el puente a una de las dos.
        private static object LeerProp(object obj, string nombre)
        {
            if (obj == null) return null;
            var pr = obj.GetType().GetProperty(nombre, BindingFlags.Public | BindingFlags.Instance);
            if (pr == null || !pr.CanRead) return null;
            try { return Val(pr.GetValue(obj)); } catch { return null; }
        }

        private static string SafeToString(object v)
        {
            try { return v.ToString(); } catch (Exception ex) { return "<" + ex.GetType().Name + ">"; }
        }

        private static bool IsSimple(Type t)
        {
            if (t == null) return false;
            if (t.IsEnum) return true;
            return t == typeof(string) || t == typeof(bool) || t == typeof(double) || t == typeof(float)
                || t == typeof(int) || t == typeof(long) || t == typeof(short) || t == typeof(byte)
                || t == typeof(decimal) || t == typeof(uint) || t == typeof(ulong) || t == typeof(DateTime);
        }

        // ---------- rutas a objetos anidados ----------
        // Llega a lo que no tiene handle propio: "Analysis",
        // "Analysis.ElevationRanges[2].MaximumElevation", "GetGeneralProperties()".
        // Cada tramo es una propiedad o un metodo sin argumentos, mas cero o mas indices.
        private static readonly Regex RutaTramo = new Regex(@"^([A-Za-z_][A-Za-z0-9_]*)(\((?<args>[^()]*)\))?(?<idx>(?:\[[^\[\]]+\])*)$");
        private static readonly Regex RutaIndice = new Regex(@"\[([^\[\]]+)\]");
        private const int MaxExpand = 3;

        private static object Indexar(object col, int i)
        {
            if (col == null) throw new BridgeException(Rpc.ErrParams, "no se puede indexar null");
            if (col is ObjectIdCollection oc)
            {
                if (i < 0 || i >= oc.Count) throw new BridgeException(Rpc.ErrParams, "indice " + i + " fuera de rango (" + oc.Count + ")");
                return oc[i];
            }
            if (col is Array arr)
            {
                if (i < 0 || i >= arr.Length) throw new BridgeException(Rpc.ErrParams, "indice " + i + " fuera de rango (" + arr.Length + ")");
                return arr.GetValue(i);
            }
            if (col is IList il)
            {
                if (i < 0 || i >= il.Count) throw new BridgeException(Rpc.ErrParams, "indice " + i + " fuera de rango (" + il.Count + ")");
                return il[i];
            }
            var idx = col.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance)
                .FirstOrDefault(x => x.GetIndexParameters().Length == 1 &&
                                     x.GetIndexParameters()[0].ParameterType == typeof(int));
            if (idx != null)
            {
                try { return idx.GetValue(col, new object[] { i }); }
                catch (TargetInvocationException ex) { throw ex.InnerException ?? ex; }
            }
            if (col is IEnumerable en)
            {
                int n = 0;
                foreach (var e in en) { if (n++ == i) return e; }
                throw new BridgeException(Rpc.ErrParams, "indice " + i + " fuera de rango (" + n + ")");
            }
            throw new BridgeException(Rpc.ErrParams, col.GetType().Name + " no se puede indexar");
        }

        // Si un tramo devolvio un ObjectId y la ruta sigue, se abre en la misma transaccion.
        private static object AbrirSiEsId(Transaction tr, object v, OpenMode modo)
        {
            if (tr != null && v is ObjectId oid && !oid.IsNull && !oid.IsErased) return tr.GetObject(oid, modo);
            return v;
        }

        private static object ResolverRuta(Transaction tr, object raiz, string ruta, OpenMode modo,
                                           out object dueno, out PropertyInfo propFinal)
        {
            dueno = null;
            propFinal = null;
            object actual = raiz;
            if (string.IsNullOrWhiteSpace(ruta)) return actual;

            foreach (var bruto in PartirRuta(ruta))
            {
                var tramo = bruto.Trim();
                if (tramo.Length == 0) continue;
                if (actual == null)
                    throw new BridgeException(Rpc.ErrParams, "la ruta se corta antes de '" + tramo + "': el tramo anterior es null");
                actual = AbrirSiEsId(tr, actual, modo);

                var m = RutaTramo.Match(tramo);
                if (!m.Success)
                    throw new BridgeException(Rpc.ErrParams,
                        "tramo de ruta invalido: '" + tramo + "'. Formas validas: Nombre, Nombre(), Nombre(a;b), Nombre[0], Nombre[\"x\"], Nombre()[0]");
                string nombre = m.Groups[1].Value;
                bool esLlamada = m.Groups[2].Success;
                string indices = m.Groups["idx"].Value;
                var t = actual.GetType();

                PropertyInfo pr = esLlamada ? null
                    : t.GetProperty(nombre, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                if (pr != null && pr.GetIndexParameters().Length != 0) pr = null;

                if (pr != null)
                {
                    if (!pr.CanRead) throw new BridgeException(Rpc.ErrParams, nombre + " no es de lectura en " + t.Name);
                    dueno = actual;
                    propFinal = pr;
                    try { actual = pr.GetValue(actual); }
                    catch (TargetInvocationException ex) { throw ex.InnerException ?? ex; }
                }
                else
                {
                    dueno = actual;
                    propFinal = null;
                    actual = Invocar(actual, nombre, esLlamada ? ArgsDeTramo(m.Groups["args"].Value) : new List<object>());
                }

                foreach (Match mi in RutaIndice.Matches(indices))
                {
                    actual = AbrirSiEsId(tr, actual, modo);
                    actual = IndexarPorClave(tr, actual, mi.Groups[1].Value);
                    propFinal = null;   // tras indexar ya no queda propiedad escribible
                }
            }
            return actual;
        }

        // Divide la ruta por '.' respetando los puntos dentro de comillas y de
        // parentesis: Styles.ProfileStyles["GEO - 1.5"].Name, ElevationAt(243.51).
        private static IEnumerable<string> PartirRuta(string ruta)
        {
            var partes = new List<string>();
            var sb = new System.Text.StringBuilder();
            bool com = false; char comc = '"'; int par = 0;
            foreach (var c in ruta)
            {
                if (com) { sb.Append(c); if (c == comc) com = false; continue; }
                if (c == '"' || c == '\'') { com = true; comc = c; sb.Append(c); continue; }
                if (c == '(') { par++; sb.Append(c); continue; }
                if (c == ')') { par--; sb.Append(c); continue; }
                if (c == '.' && par == 0) { partes.Add(sb.ToString()); sb.Clear(); continue; }
                sb.Append(c);
            }
            partes.Add(sb.ToString());
            return partes;
        }

        // Argumentos de un tramo Metodo(a;b;c): numero, bool, null, "texto" o texto
        // suelto (Coerce lo convierte a enum o string segun el parametro real).
        private static List<object> ArgsDeTramo(string crudo)
        {
            var args = new List<object>();
            if (string.IsNullOrWhiteSpace(crudo)) return args;
            foreach (var parte in crudo.Split(';'))
            {
                var v = parte.Trim();
                if (v.Length == 0) continue;
                if ((v.StartsWith("\"") && v.EndsWith("\"")) || (v.StartsWith("'") && v.EndsWith("'")))
                { args.Add(v.Substring(1, v.Length - 2)); continue; }
                if (v == "null") { args.Add(null); continue; }
                if (v == "true" || v == "false") { args.Add(v == "true"); continue; }
                double d;
                if (double.TryParse(v, System.Globalization.NumberStyles.Float,
                    System.Globalization.CultureInfo.InvariantCulture, out d)) { args.Add(d); continue; }
                args.Add(v);
            }
            return args;
        }

        // Indice numerico o clave con nombre: Styles.ProfileStyles["GEO - TERRENO"].
        private static object IndexarPorClave(Transaction tr, object col, string clave)
        {
            if (col == null) throw new BridgeException(Rpc.ErrParams, "no se puede indexar null");
            int n;
            if (int.TryParse(clave, out n)) return Indexar(col, n);
            string nombre = clave.Trim();
            if ((nombre.StartsWith("\"") && nombre.EndsWith("\"")) || (nombre.StartsWith("'") && nombre.EndsWith("'")))
                nombre = nombre.Substring(1, nombre.Length - 2);
            var idx = col.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance)
                .FirstOrDefault(x => x.GetIndexParameters().Length == 1 &&
                                     x.GetIndexParameters()[0].ParameterType == typeof(string));
            if (idx != null)
            {
                try { return idx.GetValue(col, new object[] { nombre }); }
                catch (TargetInvocationException ex) { throw ex.InnerException ?? ex; }
            }
            if (col is IEnumerable en2 && !(col is string))
            {
                foreach (var e in en2)
                {
                    var item = AbrirSiEsId(tr, e, OpenMode.ForRead);
                    if (item == null) continue;
                    var prn = item.GetType().GetProperty("Name");
                    var nm = prn == null ? null : prn.GetValue(item) as string;
                    if (string.Equals(nm, nombre, StringComparison.OrdinalIgnoreCase)) return item;
                }
                throw new BridgeException(Rpc.ErrParams, "no hay elemento con Name '" + nombre + "' en " + col.GetType().Name);
            }
            throw new BridgeException(Rpc.ErrParams, col.GetType().Name + " no se puede indexar por nombre");
        }

        private static Dictionary<string, object> DescribirObjeto(object o, bool valores,
                                                                  string patron = null, bool soloEscribibles = false, string incluir = null)
        {
            var t = o.GetType();
            Regex rxm = null;
            if (!string.IsNullOrWhiteSpace(patron))
            {
                try { rxm = new Regex(patron, RegexOptions.IgnoreCase); }
                catch (Exception ex) { throw new BridgeException(Rpc.ErrParams, "patron invalido: " + ex.Message); }
            }
            bool conProps = string.IsNullOrEmpty(incluir) || incluir == "ambos" || incluir == "props";
            bool conMetodos = (string.IsNullOrEmpty(incluir) || incluir == "ambos" || incluir == "metodos") && !soloEscribibles;
            var props = new List<object>();
            var metodos = new List<object>();
            foreach (var pr in t.GetProperties(BindingFlags.Public | BindingFlags.Instance))
            {
                if (pr.GetIndexParameters().Length != 0) continue;
                if (!conProps) break;
                if (rxm != null && !rxm.IsMatch(pr.Name)) continue;
                if (soloEscribibles && !pr.CanWrite) continue;
                var fila = new Dictionary<string, object>
                {
                    { "nombre", pr.Name }, { "tipo", pr.PropertyType.Name },
                    { "lectura", pr.CanRead }, { "escritura", pr.CanWrite },
                    { "simple", IsSimple(pr.PropertyType) }
                };
                if (valores && pr.CanRead)
                {
                    try { fila["valor"] = Val(pr.GetValue(o)); }
                    catch (Exception ex) { fila["valor"] = "<" + (ex.InnerException ?? ex).GetType().Name + ">"; }
                }
                props.Add(fila);
            }
            foreach (var m in t.GetMethods(BindingFlags.Public | BindingFlags.Instance))
            {
                if (m.IsSpecialName) continue;
                if (m.DeclaringType == typeof(object)) continue;
                if (!conMetodos) break;
                if (rxm != null && !rxm.IsMatch(m.Name)) continue;
                metodos.Add(new Dictionary<string, object>
                {
                    { "nombre", m.Name },
                    { "parametros", m.GetParameters().Select(x => x.ParameterType.Name + " " + x.Name).ToList() },
                    { "retorno", m.ReturnType.Name },
                    { "solo_lectura", EsMetodoDeLectura(m.Name) }
                });
            }
            return new Dictionary<string, object>
            {
                { "tipo", t.FullName },
                { "propiedades", props.OrderBy(x => (string)((Dictionary<string, object>)x)["nombre"]).ToList() },
                { "metodos", metodos.OrderBy(x => (string)((Dictionary<string, object>)x)["nombre"]).ToList() }
            };
        }

        // ---------- lectura ----------

        private static object DocInfo()
        {
            var doc = Doc();
            var res = new Dictionary<string, object>
            {
                { "dibujo", doc.Name },
                { "solo_lectura", LeerProp(doc, "IsReadOnly") ?? LeerProp(doc.Database, "IsReadOnly") },
                { "insunits", AcApp.GetSystemVariable("INSUNITS") },
                { "lunits", AcApp.GetSystemVariable("LUNITS") },
                { "measurement", AcApp.GetSystemVariable("MEASUREMENT") },
                { "producto", AcApp.GetSystemVariable("PRODUCT") },
                { "version_acad", AcApp.GetSystemVariable("ACADVER") },
                { "puente_version", Version }
            };
            try
            {
                var cd = CivilDoc();
                res["civil3d"] = true;
                foreach (var nombre in new[] { "Name", "DrawingName" })
                {
                    var pr = cd.GetType().GetProperty(nombre);
                    if (pr != null) { res["civil_doc_" + nombre.ToLowerInvariant()] = Val(pr.GetValue(cd)); break; }
                }
                var settings = cd.GetType().GetProperty("Settings");
                if (settings != null) res["civil_settings"] = settings.PropertyType.Name;
            }
            catch (BridgeException ex)
            {
                res["civil3d"] = false;
                res["civil3d_motivo"] = ex.Message;
            }
            return res;
        }

        private static object CivilCollections()
        {
            var cd = CivilDoc();
            var t = cd.GetType();
            var salida = new List<object>();
            foreach (var m in t.GetMethods(BindingFlags.Public | BindingFlags.Instance))
            {
                if (m.GetParameters().Length != 0) continue;
                if (!m.Name.StartsWith("Get") || !m.Name.EndsWith("Ids")) continue;
                int cant = -1; string err = null;
                try
                {
                    var v = m.Invoke(cd, null);
                    cant = CountIds(v);
                }
                catch (Exception ex) { err = (ex.InnerException ?? ex).Message; }
                salida.Add(new Dictionary<string, object>
                {
                    { "miembro", m.Name }, { "clase", "metodo" }, { "cantidad", cant }, { "error", err }
                });
            }
            foreach (var pr in t.GetProperties(BindingFlags.Public | BindingFlags.Instance))
            {
                if (pr.GetIndexParameters().Length != 0) continue;
                int cant = -1; string err = null; bool esColeccion = false;
                try
                {
                    var v = pr.GetValue(cd);
                    if (v is ObjectIdCollection || v is IEnumerable<ObjectId>)
                    {
                        esColeccion = true;
                        cant = CountIds(v);
                    }
                }
                catch (Exception ex) { err = (ex.InnerException ?? ex).Message; }
                if (esColeccion || err != null && pr.PropertyType.Name.Contains("Collection"))
                    salida.Add(new Dictionary<string, object>
                    {
                        { "miembro", pr.Name }, { "clase", "propiedad" }, { "cantidad", cant }, { "error", err }
                    });
            }
            return new Dictionary<string, object>
            {
                { "tipo_documento", t.FullName },
                { "colecciones", salida.OrderBy(x => ((Dictionary<string, object>)x)["miembro"]).ToList() },
                { "alias", Alias }
            };
        }

        private static int CountIds(object v)
        {
            if (v is ObjectIdCollection oc) return oc.Count;
            if (v is IEnumerable<ObjectId> ei) return ei.Count();
            if (v is IEnumerable en) { int n = 0; foreach (var _ in en) n++; return n; }
            return -1;
        }

        private static List<ObjectId> Ids(object v)
        {
            var res = new List<ObjectId>();
            if (v is ObjectIdCollection oc) { foreach (ObjectId i in oc) res.Add(i); return res; }
            if (v is IEnumerable<ObjectId> ei) { res.AddRange(ei); return res; }
            if (v is IEnumerable en)
            {
                foreach (var e in en)
                {
                    if (e is ObjectId i) { res.Add(i); continue; }
                    var pr = e?.GetType().GetProperty("ObjectId");
                    if (pr != null && pr.GetValue(e) is ObjectId j) res.Add(j);
                }
            }
            return res;
        }

        private static List<ObjectId> Seleccionar(JsonObject p, Database db)
        {
            var handles = p["handles"] as JsonArray;
            if (handles != null && handles.Count > 0)
            {
                var res = new List<ObjectId>();
                foreach (var h in handles)
                {
                    try { res.Add(IdFromHandle(db, h.GetValue<string>())); }
                    catch { throw new BridgeException(Rpc.ErrParams, "handle invalido: " + h); }
                }
                return res;
            }

            string col = p["coleccion"]?.GetValue<string>();
            if (!string.IsNullOrEmpty(col))
            {
                string[] candidatos;
                if (!Alias.TryGetValue(col, out candidatos)) candidatos = new[] { col };
                var cd = CivilDoc();
                var t = cd.GetType();
                var probados = new List<string>();
                foreach (var miembro in candidatos)
                {
                    probados.Add(miembro);
                    var m = t.GetMethod(miembro, BindingFlags.Public | BindingFlags.Instance, null, Type.EmptyTypes, null);
                    if (m != null) return Ids(m.Invoke(cd, null));
                    var pr = t.GetProperty(miembro, BindingFlags.Public | BindingFlags.Instance);
                    if (pr != null) return Ids(pr.GetValue(cd));
                }
                throw new BridgeException(Rpc.ErrParams,
                    "la coleccion '" + col + "' no existe en esta version (probado: " +
                    string.Join(", ", probados) + "); consulte civil.colecciones");
            }

            // por defecto: espacio modelo
            var res2 = new List<ObjectId>();
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var bt = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                var ms = (BlockTableRecord)tr.GetObject(bt[BlockTableRecord.ModelSpace], OpenMode.ForRead);
                foreach (ObjectId id in ms) res2.Add(id);
                tr.Commit();
            }
            return res2;
        }

        private static object TypesDiscover(JsonObject p)
        {
            var db = Doc().Database;
            var ids = Seleccionar(p, db);
            var cuenta = new Dictionary<string, int>();
            var dxf = new Dictionary<string, string>();
            using (var tr = db.TransactionManager.StartTransaction())
            {
                foreach (var id in ids)
                {
                    if (id.IsNull || id.IsErased) continue;
                    DBObject o;
                    try { o = tr.GetObject(id, OpenMode.ForRead); } catch { continue; }
                    string tn = o.GetType().FullName;
                    cuenta[tn] = cuenta.TryGetValue(tn, out var n) ? n + 1 : 1;
                    if (!dxf.ContainsKey(tn))
                    {
                        try { dxf[tn] = o.GetRXClass().DxfName + "/" + o.GetRXClass().Name; } catch { dxf[tn] = ""; }
                    }
                }
                tr.Commit();
            }
            return new Dictionary<string, object>
            {
                { "total_objetos", ids.Count },
                { "tipos", cuenta.OrderByDescending(k => k.Value).Select(k => new Dictionary<string, object>
                    { { "tipo", k.Key }, { "cantidad", k.Value }, { "clase_rx", dxf[k.Key] } }).ToList() }
            };
        }

        private static object ObjectsQuery(JsonObject p)
        {
            var db = Doc().Database;
            var ids = Seleccionar(p, db);
            string filtroTipo = p["tipo"]?.GetValue<string>();
            string capa = p["capa"]?.GetValue<string>();
            int limite = p["limite"] != null ? p["limite"].GetValue<int>() : 100;
            int salto = p["salto"] != null ? p["salto"].GetValue<int>() : 0;
            if (limite > MaxItems) limite = MaxItems;
            var props = (p["props"] as JsonArray)?.Select(x => x.GetValue<string>()).ToList() ?? new List<string>();
            bool todas = props.Contains("*");

            var filas = new List<Dictionary<string, object>>();
            int vistos = 0, coincidencias = 0;

            using (var tr = db.TransactionManager.StartTransaction())
            {
                foreach (var id in ids)
                {
                    if (id.IsNull || id.IsErased) continue;
                    DBObject o;
                    try { o = tr.GetObject(id, OpenMode.ForRead); } catch { continue; }
                    var t = o.GetType();
                    if (!string.IsNullOrEmpty(filtroTipo) &&
                        t.FullName.IndexOf(filtroTipo, StringComparison.OrdinalIgnoreCase) < 0) continue;
                    var ent = o as Entity;
                    if (!string.IsNullOrEmpty(capa) && (ent == null || !string.Equals(ent.Layer, capa, StringComparison.OrdinalIgnoreCase))) continue;
                    coincidencias++;
                    if (vistos++ < salto) continue;
                    if (filas.Count >= limite) continue;

                    var fila = new Dictionary<string, object>
                    {
                        { "handle", HandleOf(id) },
                        { "tipo", t.FullName }
                    };
                    if (ent != null) fila["capa"] = ent.Layer;
                    var pn = t.GetProperty("Name");
                    if (pn != null && pn.CanRead) { try { fila["nombre"] = Val(pn.GetValue(o)); } catch { } }
                    var pd = t.GetProperty("Description");
                    if (pd != null && pd.CanRead) { try { fila["descripcion"] = Val(pd.GetValue(o)); } catch { } }

                    if (todas)
                    {
                        foreach (var pr in t.GetProperties(BindingFlags.Public | BindingFlags.Instance))
                        {
                            if (pr.GetIndexParameters().Length != 0 || !pr.CanRead) continue;
                            if (!IsSimple(pr.PropertyType) && pr.PropertyType != typeof(ObjectId)) continue;
                            try { fila[pr.Name] = Val(pr.GetValue(o)); } catch { }
                        }
                    }
                    else
                    {
                        foreach (var nombre in props)
                        {
                            var pr = t.GetProperty(nombre, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                            if (pr == null || !pr.CanRead) { fila[nombre] = null; continue; }
                            try { fila[nombre] = Val(pr.GetValue(o)); }
                            catch (Exception ex) { fila[nombre] = "<error: " + (ex.InnerException ?? ex).Message + ">"; }
                        }
                    }
                    filas.Add(fila);
                }
                tr.Commit();
            }

            return new Dictionary<string, object>
            {
                { "coincidencias", coincidencias },
                { "devueltos", filas.Count },
                { "truncado", coincidencias > salto + filas.Count },
                { "objetos", filas }
            };
        }

        private static object ObjectsAggregate(JsonObject p)
        {
            string prop = p["prop"]?.GetValue<string>();
            if (string.IsNullOrEmpty(prop)) throw new BridgeException(Rpc.ErrParams, "falta prop");
            string op = (p["op"]?.GetValue<string>() ?? "suma").ToLowerInvariant();
            var db = Doc().Database;
            var ids = Seleccionar(p, db);
            string filtroTipo = p["tipo"]?.GetValue<string>();

            var valores = new List<double>();
            int nulos = 0, objetos = 0;
            using (var tr = db.TransactionManager.StartTransaction())
            {
                foreach (var id in ids)
                {
                    if (id.IsNull || id.IsErased) continue;
                    DBObject o;
                    try { o = tr.GetObject(id, OpenMode.ForRead); } catch { continue; }
                    var t = o.GetType();
                    if (!string.IsNullOrEmpty(filtroTipo) &&
                        t.FullName.IndexOf(filtroTipo, StringComparison.OrdinalIgnoreCase) < 0) continue;
                    objetos++;
                    var pr = t.GetProperty(prop, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                    if (pr == null || !pr.CanRead) { nulos++; continue; }
                    try
                    {
                        var v = pr.GetValue(o);
                        if (v == null) { nulos++; continue; }
                        valores.Add(Convert.ToDouble(v));
                    }
                    catch { nulos++; }
                }
                tr.Commit();
            }

            double res;
            switch (op)
            {
                case "conteo": res = valores.Count; break;
                case "suma": res = valores.Sum(); break;
                case "min": res = valores.Count == 0 ? double.NaN : valores.Min(); break;
                case "max": res = valores.Count == 0 ? double.NaN : valores.Max(); break;
                case "promedio": res = valores.Count == 0 ? double.NaN : valores.Average(); break;
                default: throw new BridgeException(Rpc.ErrParams, "op debe ser conteo|suma|min|max|promedio");
            }
            return new Dictionary<string, object>
            {
                { "op", op }, { "prop", prop }, { "resultado", double.IsNaN(res) ? (object)null : res },
                { "objetos", objetos }, { "valores_usados", valores.Count }, { "sin_valor", nulos }
            };
        }

        private static object ObjectsProps(JsonObject p)
        {
            string handle = p["handle"]?.GetValue<string>();
            if (string.IsNullOrEmpty(handle)) throw new BridgeException(Rpc.ErrParams, "falta handle");
            string ruta = p["ruta"]?.GetValue<string>();
            bool valores = p["valores"] != null && p["valores"].GetValue<bool>();
            string patron = p["patron"]?.GetValue<string>();
            bool soloEscribibles = p["solo_escribibles"] != null && p["solo_escribibles"].GetValue<bool>();
            string incluir = p["incluir"]?.GetValue<string>();
            var db = Doc().Database;
            var id = IdFromHandle(db, handle);
            Dictionary<string, object> res;
            using (var tr = db.TransactionManager.StartTransaction())
            {
                object destino = tr.GetObject(id, OpenMode.ForRead);
                object dueno; PropertyInfo prf;
                destino = ResolverRuta(tr, destino, ruta, OpenMode.ForRead, out dueno, out prf);
                if (destino == null) throw new BridgeException(Rpc.ErrParams, "la ruta devolvio null: " + ruta);
                destino = AbrirSiEsId(tr, destino, OpenMode.ForRead);
                res = DescribirObjeto(destino, valores, patron, soloEscribibles, incluir);
                tr.Commit();
            }
            res["handle"] = handle;
            if (!string.IsNullOrWhiteSpace(ruta)) res["ruta"] = ruta;
            return res;
        }

        // Lee el valor al final de una ruta. profundidad > 0 expande los objetos
        // que de otro modo saldrian como {tipo, texto}.
        private static object ObjectsRead(JsonObject p)
        {
            string handle = p["handle"]?.GetValue<string>();
            string ruta = p["ruta"]?.GetValue<string>();
            if (string.IsNullOrWhiteSpace(ruta)) throw new BridgeException(Rpc.ErrParams, "falta ruta");
            int prof = p["profundidad"] != null ? p["profundidad"].GetValue<int>() : 1;
            if (prof < 0) prof = 0;
            if (prof > MaxExpand) prof = MaxExpand;
            object dueno; PropertyInfo prf;

            if (string.IsNullOrEmpty(handle))
            {
                var v0 = ResolverRuta(null, CivilDoc(), ruta, OpenMode.ForRead, out dueno, out prf);
                return new Dictionary<string, object>
                { { "objetivo", "CivilDocument" }, { "ruta", ruta }, { "profundidad", prof }, { "valor", Val(v0, 0, prof) } };
            }

            var db = Doc().Database;
            object valor;
            using (var tr = db.TransactionManager.StartTransaction())
            {
                object o = tr.GetObject(IdFromHandle(db, handle), OpenMode.ForRead);
                var v = ResolverRuta(tr, o, ruta, OpenMode.ForRead, out dueno, out prf);
                v = AbrirSiEsId(tr, v, OpenMode.ForRead);
                valor = Val(v, 0, prof);
                tr.Commit();
            }
            return new Dictionary<string, object>
            { { "objetivo", handle }, { "ruta", ruta }, { "profundidad", prof }, { "valor", valor } };
        }

        private static bool EsMetodoDeLectura(string nombre)
        {
            return ReadOnlyMethodPatterns.Any(rx => Regex.IsMatch(nombre, rx));
        }

        // ---------- escritura ----------

        private static void ExigirEscritura(string method, JsonObject p)
        {
            if (!BridgeServer.AllowWrite)
                throw new BridgeException(Rpc.ErrForbidden, "el puente esta en modo solo lectura (CDCRD_C3D_SOLO_LECTURA=1)");
            string token = p["token"]?.GetValue<string>();
            if (!Approvals.Consume(token, Approvals.Hash(method, p)))
                throw new BridgeException(Rpc.ErrApproval,
                    "falta token de aprobacion valido para estos parametros exactos: pida approval.request primero");
        }

        private static object Coerce(object json, Type destino)
        {
            if (json == null) return null;
            if (destino == typeof(string)) return Convert.ToString(json);
            if (destino.IsEnum) return Enum.Parse(destino, Convert.ToString(json), true);
            if (IsSimple(destino)) return Convert.ChangeType(json, destino);
            // Point3d, Point2d, Vector3d: desde [x,y,z]
            if (json is List<object> lista)
            {
                var ctor = destino.GetConstructors()
                    .FirstOrDefault(c => c.GetParameters().Length == lista.Count &&
                                         c.GetParameters().All(x => x.ParameterType == typeof(double)));
                if (ctor != null)
                    return ctor.Invoke(lista.Select(x => (object)Convert.ToDouble(x)).ToArray());
            }
            throw new BridgeException(Rpc.ErrParams, "no se puede convertir el valor a " + destino.Name);
        }

        private static object JsonToClr(JsonNode n)
        {
            if (n == null) return null;
            if (n is JsonArray a) return a.Select(JsonToClr).ToList();
            var v = n.AsValue();
            if (v.TryGetValue<bool>(out var b)) return b;
            if (v.TryGetValue<double>(out var d)) return d;
            if (v.TryGetValue<string>(out var s)) return s;
            return n.ToJsonString();
        }

        private static object ObjectsUpdate(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string handle = p["handle"]?.GetValue<string>();
            string ruta = p["ruta"]?.GetValue<string>();
            var cambios = p["props"] as JsonObject;
            if (string.IsNullOrEmpty(handle) || cambios == null || cambios.Count == 0)
                throw new BridgeException(Rpc.ErrParams, "se requieren handle y props");

            var doc = Doc();
            var db = doc.Database;
            var aplicados = new Dictionary<string, object>();
            var fallidos = new Dictionary<string, object>();

            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                object o = tr.GetObject(IdFromHandle(db, handle), OpenMode.ForWrite);
                object dueno; PropertyInfo prf;
                o = ResolverRuta(tr, o, ruta, OpenMode.ForWrite, out dueno, out prf);
                if (o == null) throw new BridgeException(Rpc.ErrParams, "la ruta devolvio null: " + ruta);
                o = AbrirSiEsId(tr, o, OpenMode.ForWrite);
                if (!string.IsNullOrWhiteSpace(ruta) && o.GetType().IsValueType)
                    throw new BridgeException(Rpc.ErrParams, o.GetType().Name +
                        " es un tipo por valor: escribir ahi no afecta al dibujo. Use el metodo Set... del objeto padre con objects.invoke");
                var t = o.GetType();
                foreach (var kv in cambios)
                {
                    var pr = t.GetProperty(kv.Key, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
                    if (pr == null || !pr.CanWrite) { fallidos[kv.Key] = "la propiedad no existe o es de solo lectura"; continue; }
                    try
                    {
                        var antes = pr.CanRead ? Val(pr.GetValue(o)) : null;
                        pr.SetValue(o, Coerce(JsonToClr(kv.Value), pr.PropertyType));
                        aplicados[kv.Key] = new Dictionary<string, object>
                        { { "antes", antes }, { "despues", pr.CanRead ? Val(pr.GetValue(o)) : null } };
                    }
                    catch (Exception ex) { fallidos[kv.Key] = (ex.InnerException ?? ex).Message; }
                }
                tr.Commit();
            }
            Log.Write("objects.update " + handle + " aplicados=" + aplicados.Count + " fallidos=" + fallidos.Count);
            return new Dictionary<string, object>
            { { "handle", handle }, { "ruta", ruta }, { "aplicados", aplicados }, { "fallidos", fallidos } };
        }

        private static object ObjectsInvoke(JsonObject p, string method)
        {
            string handle = p["handle"]?.GetValue<string>();
            string nombre = p["metodo"]?.GetValue<string>();
            if (string.IsNullOrEmpty(nombre)) throw new BridgeException(Rpc.ErrParams, "falta metodo");
            var args = (p["args"] as JsonArray)?.Select(JsonToClr).ToList() ?? new List<object>();
            bool lectura = EsMetodoDeLectura(nombre);
            if (!lectura) ExigirEscritura(method, p);

            string ruta = p["ruta"]?.GetValue<string>();
            int prof = p["profundidad"] != null ? p["profundidad"].GetValue<int>() : 0;
            if (prof < 0) prof = 0;
            if (prof > MaxExpand) prof = MaxExpand;

            var doc = Doc();
            var db = doc.Database;
            object destino;
            object resultado;
            object dueno; PropertyInfo prf;

            if (string.IsNullOrEmpty(handle))
            {
                destino = ResolverRuta(null, CivilDoc(), ruta, OpenMode.ForRead, out dueno, out prf);
                resultado = Invocar(destino, nombre, args);
                return new Dictionary<string, object>
                { { "objetivo", "CivilDocument" }, { "ruta", ruta }, { "metodo", nombre }, { "resultado", Val(resultado, 0, prof) } };
            }

            using (lectura ? null : doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var modo = lectura ? OpenMode.ForRead : OpenMode.ForWrite;
                object o = tr.GetObject(IdFromHandle(db, handle), modo);
                o = ResolverRuta(tr, o, ruta, modo, out dueno, out prf);
                if (o == null) throw new BridgeException(Rpc.ErrParams, "la ruta devolvio null: " + ruta);
                o = AbrirSiEsId(tr, o, modo);
                resultado = Invocar(o, nombre, args);
                tr.Commit();
            }
            if (!lectura) Log.Write("objects.invoke escritura " + handle + "." + (ruta ?? "") + "." + nombre);
            return new Dictionary<string, object>
            { { "objetivo", handle }, { "ruta", ruta }, { "metodo", nombre }, { "solo_lectura", lectura }, { "resultado", Val(resultado, 0, prof) } };
        }

        private static object Invocar(object obj, string nombre, List<object> args)
        {
            var candidatos = obj.GetType().GetMethods(BindingFlags.Public | BindingFlags.Instance)
                .Where(m => string.Equals(m.Name, nombre, StringComparison.OrdinalIgnoreCase)
                            && m.GetParameters().Length == args.Count).ToList();
            if (candidatos.Count == 0)
                throw new BridgeException(Rpc.ErrParams,
                    "no existe " + nombre + " con " + args.Count + " parametros en " + obj.GetType().Name +
                    "; use objects.props para ver la firma");
            foreach (var m in candidatos)
            {
                try
                {
                    var ps = m.GetParameters();
                    var vals = new object[args.Count];
                    bool conRef = false;
                    for (int i = 0; i < args.Count; i++)
                    {
                        var tp = ps[i].ParameterType;
                        if (tp.IsByRef)
                        {
                            // Parametros ref/out (PointLocation, StationOffset): el argumento de
                            // entrada puede ser null; el valor de salida se devuelve en "salidas".
                            conRef = true;
                            vals[i] = Coerce(args[i], tp.GetElementType());
                        }
                        else vals[i] = Coerce(args[i], tp);
                    }
                    var ret = m.Invoke(obj, vals);
                    if (!conRef) return ret;
                    var salidas = new Dictionary<string, object>();
                    for (int i = 0; i < ps.Length; i++)
                        if (ps[i].ParameterType.IsByRef) salidas[ps[i].Name] = vals[i];
                    return new Dictionary<string, object> { { "retorno", ret }, { "salidas", salidas } };
                }
                catch (BridgeException) { continue; }
                catch (TargetInvocationException ex) { throw ex.InnerException ?? ex; }
            }
            throw new BridgeException(Rpc.ErrParams, "los argumentos no encajan con ninguna sobrecarga de " + nombre);
        }

        private static object SelectionSet(JsonObject p)
        {
            var doc = Doc();
            var db = doc.Database;
            var ids = Seleccionar(p, db);
            doc.Editor.SetImpliedSelection(ids.Where(i => !i.IsNull && !i.IsErased).ToArray());
            return new Dictionary<string, object> { { "seleccionados", ids.Count } };
        }

        // Zoom por API (ViewTableRecord), no por comando: dentro del contexto de
        // aplicacion los comandos no se pueden invocar de forma sincrona.
        private static object ViewZoom(JsonObject p)
        {
            var doc = Doc();
            var db = doc.Database;
            bool extension = p["extension"] != null && p["extension"].GetValue<bool>();
            double margen = p["margen"] != null ? p["margen"].GetValue<double>() : 0.10;

            Extents3d? ext = null;
            if (extension)
            {
                db.UpdateExt(true);
                ext = new Extents3d(db.Extmin, db.Extmax);
            }
            else
            {
                var ids = Seleccionar(p, db).Where(i => !i.IsNull && !i.IsErased).ToArray();
                if (ids.Length == 0) throw new BridgeException(Rpc.ErrParams, "no hay objetos a los que hacer zoom");
                using (var tr = db.TransactionManager.StartTransaction())
                {
                    foreach (var id in ids)
                    {
                        var ent = tr.GetObject(id, OpenMode.ForRead) as Entity;
                        if (ent == null) continue;
                        try
                        {
                            var e = ent.GeometricExtents;
                            if (ext == null) ext = e;
                            else { var u = ext.Value; u.AddExtents(e); ext = u; }
                        }
                        catch { }
                    }
                    tr.Commit();
                }
                if (ext == null) throw new BridgeException(Rpc.ErrParams, "los objetos indicados no tienen extension geometrica");
                doc.Editor.SetImpliedSelection(ids);
            }

            var min = ext.Value.MinPoint;
            var max = ext.Value.MaxPoint;
            double ancho = Math.Max(max.X - min.X, 1e-6) * (1 + 2 * margen);
            double alto = Math.Max(max.Y - min.Y, 1e-6) * (1 + 2 * margen);
            var vista = new ViewTableRecord
            {
                CenterPoint = new Point2d((min.X + max.X) / 2.0, (min.Y + max.Y) / 2.0),
                Width = ancho,
                Height = alto
            };
            doc.Editor.SetCurrentView(vista);
            return new Dictionary<string, object>
            {
                { "centro", new[] { vista.CenterPoint.X, vista.CenterPoint.Y } },
                { "ancho", ancho }, { "alto", alto },
                { "modo", extension ? "extension" : "objetos" }
            };
        }

        // Asincrono por diseno: en contexto de aplicacion la unica via segura de
        // correr un comando es encolarlo en el documento. El resultado no vuelve
        // en esta respuesta; verifiquelo con una consulta posterior.
        private static object CmdRun(JsonObject p, string method)
        {
            if (!BridgeServer.AllowCommands)
                throw new BridgeException(Rpc.ErrForbidden,
                    "cmd.run esta apagado: defina CDCRD_C3D_PERMITIR_COMANDOS=1 antes de abrir Civil 3D");
            ExigirEscritura(method, p);
            string linea = p["linea"]?.GetValue<string>();
            if (string.IsNullOrWhiteSpace(linea)) throw new BridgeException(Rpc.ErrParams, "falta linea");
            if (!linea.EndsWith("\n")) linea += "\n";
            var doc = Doc();
            doc.SendStringToExecute(linea, true, false, true);
            Log.Write("cmd.run encolado: " + linea.Replace("\n", " "));
            return new Dictionary<string, object>
            {
                { "encolado", linea }, { "sincrono", false },
                { "nota", "el comando corre en el documento despues de esta respuesta; verifique con objects.query" }
            };
        }

        // ---------- capas ----------
        // Una capa apagada o congelada hace invisible al objeto entero por mas
        // que su estilo este bien: esto se consulta antes de depurar un estilo.

        private static object LayersQuery(JsonObject p)
        {
            string filtro = p["nombre"]?.GetValue<string>();
            var db = Doc().Database;
            var filas = new List<object>();
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var tabla = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
                foreach (ObjectId id in tabla)
                {
                    var ltr = (LayerTableRecord)tr.GetObject(id, OpenMode.ForRead);
                    if (!string.IsNullOrEmpty(filtro) &&
                        ltr.Name.IndexOf(filtro, StringComparison.OrdinalIgnoreCase) < 0) continue;
                    filas.Add(new Dictionary<string, object>
                    {
                        { "nombre", ltr.Name },
                        { "apagada", ltr.IsOff },
                        { "congelada", ltr.IsFrozen },
                        { "bloqueada", ltr.IsLocked },
                        { "trazable", ltr.IsPlottable },
                        { "color", LeerProp(ltr.Color, "ColorIndex") },
                        { "handle", HandleOf(id) }
                    });
                }
                tr.Commit();
            }
            return new Dictionary<string, object> { { "cantidad", filas.Count }, { "capas", filas } };
        }

        private static object LayersSet(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            var nombres = (p["nombres"] as JsonArray)?.Select(x => x.GetValue<string>()).ToList();
            if (nombres == null || nombres.Count == 0)
                throw new BridgeException(Rpc.ErrParams, "se requiere nombres");
            bool? apagada = p["apagada"] == null ? (bool?)null : p["apagada"].GetValue<bool>();
            bool? congelada = p["congelada"] == null ? (bool?)null : p["congelada"].GetValue<bool>();
            bool? bloqueada = p["bloqueada"] == null ? (bool?)null : p["bloqueada"].GetValue<bool>();
            if (apagada == null && congelada == null && bloqueada == null)
                throw new BridgeException(Rpc.ErrParams, "indique al menos apagada, congelada o bloqueada");

            var doc = Doc();
            var db = doc.Database;
            var aplicados = new List<object>();
            var fallidos = new Dictionary<string, object>();
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var tabla = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
                foreach (var n in nombres)
                {
                    if (string.IsNullOrWhiteSpace(n)) continue;
                    if (!tabla.Has(n)) { fallidos[n] = "la capa no existe"; continue; }
                    try
                    {
                        var ltr = (LayerTableRecord)tr.GetObject(tabla[n], OpenMode.ForWrite);
                        if (apagada != null) ltr.IsOff = apagada.Value;
                        if (congelada != null) ltr.IsFrozen = congelada.Value;
                        if (bloqueada != null) ltr.IsLocked = bloqueada.Value;
                        aplicados.Add(new Dictionary<string, object>
                        {
                            { "nombre", ltr.Name }, { "apagada", ltr.IsOff },
                            { "congelada", ltr.IsFrozen }, { "bloqueada", ltr.IsLocked }
                        });
                    }
                    catch (Exception ex) { fallidos[n] = (ex.InnerException ?? ex).Message; }
                }
                tr.Commit();
            }
            try { doc.Editor.Regen(); } catch { }
            Log.Write("layers.set aplicadas=" + aplicados.Count + " fallidas=" + fallidos.Count);
            return new Dictionary<string, object> { { "aplicados", aplicados }, { "fallidos", fallidos } };
        }

        // ---------- guardado ----------
        // Por reflexion sobre Database.SaveAs: la sobrecarga y el enum DwgVersion
        // cambian entre versiones y Coerce convierte "Current" al valor del enum.
        private static object DocSave(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            var doc = Doc();
            string ruta = p["ruta"]?.GetValue<string>();
            if (string.IsNullOrWhiteSpace(ruta)) ruta = doc.Name;
            string version = p["version"]?.GetValue<string>();
            if (string.IsNullOrWhiteSpace(version)) version = "Current";
            using (doc.LockDocument())
            {
                Invocar(doc.Database, "SaveAs", new List<object> { ruta, version });
            }
            Log.Write("doc.save " + ruta);
            return new Dictionary<string, object> { { "guardado", ruta }, { "version", version } };
        }
    }
}
