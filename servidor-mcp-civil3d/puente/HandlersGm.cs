// CDCRD-Digital - puente MCP para Civil 3D 2027
// Etapa 4: puente hacia el Geotechnical Modeler (GM) por reflexion sobre los
// ensamblados Aecc.Gtm.* ya cargados en el proceso. No referencia los DLL del
// GM en compilacion: todo se resuelve en runtime, con errores estructurados.
// Ademas: diag.dialogos (deteccion de ventanas modales abiertas).
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using AcadApp = Autodesk.AutoCAD.ApplicationServices.Application;

namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        private static object DispatchGm(string method, JsonObject p)
        {
            switch (method)
            {
                case "gm.diagnosticar": return GmDiagnosticar(p);
                case "gm.reparar": return GmReparar(p, method);
                case "gm.perfil_sondeos": return GmPerfilSondeos(p, method);
                case "gm.superficies": return GmConstruirSuperficies(p, method);
                case "gm.3d_boreholes": return Gm3dBoreholes(p, method);
                case "gm.stratum_display": return GmStratumDisplay(p, method);
                case "diag.dialogos": return DiagDialogos(p);
                default: return null; // no es gm.*: que siga la cadena de dispatch
            }
        }

        // ---------- infraestructura de reflexion sobre el GM ----------

        private static Assembly AsmCargado(string nombre)
        {
            return AppDomain.CurrentDomain.GetAssemblies()
                .FirstOrDefault(a => string.Equals(a.GetName().Name, nombre, StringComparison.OrdinalIgnoreCase));
        }

        private static Type TipoGm(string asm, string nombreCompleto)
        {
            var a = AsmCargado(asm);
            if (a == null)
                throw new BridgeException(Rpc.ErrParams, "ensamblado del GM no cargado: " + asm +
                    " (el bundle C3D-GeoTechModeler no esta cargado en este proceso)");
            var t = a.GetType(nombreCompleto, false);
            if (t == null)
                throw new BridgeException(Rpc.ErrParams, "tipo no encontrado en " + asm + ": " + nombreCompleto);
            return t;
        }

        private static object ContenedorGm()
        {
            var ioc = TipoGm("Aecc.Gtm.Domain", "Aecc.Gtm.Domain.IoC");
            var c = ioc.GetProperty("Container", BindingFlags.Public | BindingFlags.Static)?.GetValue(null);
            if (c == null)
                throw new BridgeException(Rpc.ErrParams,
                    "el contenedor IoC del GM no esta inicializado todavia (ningun comando del GM ha corrido en esta sesion)");
            return c;
        }

        private static IDisposable AmbitoGm(object contenedor)
        {
            // Castle.MicroKernel.Lifestyle.LifestyleExtensions.BeginScope(...)
            var asm = AsmCargado("Castle.Windsor");
            var ext = asm?.GetType("Castle.MicroKernel.Lifestyle.LifestyleExtensions", false);
            if (ext == null) return null; // sin ambito: Resolve puede fallar, se reporta alla
            foreach (var m in ext.GetMethods(BindingFlags.Public | BindingFlags.Static)
                                 .Where(x => x.Name == "BeginScope" && x.GetParameters().Length == 1))
            {
                var tp = m.GetParameters()[0].ParameterType;
                object arg = null;
                if (tp.IsInstanceOfType(contenedor)) arg = contenedor;
                else
                {
                    var kernel = contenedor.GetType().GetProperty("Kernel")?.GetValue(contenedor);
                    if (kernel != null && tp.IsInstanceOfType(kernel)) arg = kernel;
                }
                if (arg != null) return m.Invoke(null, new[] { arg }) as IDisposable;
            }
            return null;
        }

        private static object ResolverGm(object contenedor, Type servicio)
        {
            var m = contenedor.GetType().GetMethod("Resolve", new[] { typeof(Type) });
            if (m == null)
                throw new BridgeException(Rpc.ErrInternal, "el contenedor del GM no expone Resolve(Type)");
            return m.Invoke(contenedor, new object[] { servicio });
        }

        private static object InvocarGm(object objeto, string metodo, params object[] args)
        {
            var t = objeto.GetType();
            var cands = t.GetMethods(BindingFlags.Public | BindingFlags.Instance)
                .Where(m => m.Name == metodo && m.GetParameters().Length == args.Length).ToList();
            if (cands.Count == 0)
                throw new BridgeException(Rpc.ErrParams, t.Name + " no tiene " + metodo + " con " + args.Length + " parametros");
            // con sobrecargas (GetProfileView(string,string) vs (Alignment,string)),
            // elegir la primera cuyos tipos acepten los argumentos reales
            var mi = cands.FirstOrDefault(m =>
            {
                var ps = m.GetParameters();
                for (int i = 0; i < args.Length; i++)
                {
                    if (args[i] == null) continue;
                    var tp = ps[i].ParameterType;
                    if (tp.IsInstanceOfType(args[i])) continue;
                    if (tp.IsValueType && args[i] is IConvertible) continue;
                    return false;
                }
                return true;
            }) ?? cands[0];
            try { return mi.Invoke(objeto, args); }
            catch (TargetInvocationException tie)
            {
                throw new BridgeException(Rpc.ErrInternal, t.Name + "." + metodo + " fallo: " + ExcepcionDetallada(tie.InnerException ?? tie));
            }
        }

        private static object PropGm(object objeto, string prop)
        {
            if (ReflectionRead.TryRead(objeto, prop, out var value)) return value;
            throw new BridgeException(Rpc.ErrParams,
                (objeto == null ? "null" : objeto.GetType().Name) + " no tiene el campo o propiedad legible " + prop);
        }

        private static void FijarPropGm(object objeto, string prop, object valor)
        {
            var pi = objeto.GetType().GetProperty(prop, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
            if (pi == null || !pi.CanWrite) return;
            pi.SetValue(objeto, Coerce(valor, pi.PropertyType));
        }

        // Texto completo de una excepcion: tipo, mensaje, pila y anidadas. Es la
        // evidencia que pide el reporte del bug del GM.
        private static string ExcepcionDetallada(Exception ex)
        {
            var sb = new StringBuilder();
            int nivel = 0;
            for (var e = ex; e != null && nivel < 6; e = e.InnerException, nivel++)
            {
                if (nivel > 0) sb.Append(" <- ");
                sb.Append(e.GetType().FullName).Append(": ").Append(e.Message);
                if (e.TargetSite != null)
                    sb.Append(" [en ").Append(e.TargetSite.DeclaringType?.FullName).Append('.').Append(e.TargetSite.Name).Append(']');
            }
            if (ex.StackTrace != null)
                sb.Append(" | pila: ").Append(ex.StackTrace.Replace("\r", "").Replace("\n", " / ").Trim());
            return sb.ToString();
        }

        // Transaccion del GM (AcadDocumentService.StartTransaction + CommitTransaction),
        // igual que los presenters del plugin.
        private static object TransaccionGm(object docService)
        {
            return InvocarGm(docService, "StartTransaction", AcadApp.DocumentManager.MdiActiveDocument);
        }

        // ---------- gm.diagnosticar ----------

        private static object GmDiagnosticar(JsonObject p)
        {
            var r = new Dictionary<string, object>();
            var problemas = new List<string>();

            // 1. ensamblados
            var asms = new[] { "Aecc.Gtm.Domain", "Aecc.Gtm.DomainPersistence", "Aecc.Gtm.CADServices", "Aecc.Gtm.AutoCADPlugin" }
                .ToDictionary(n => n, n => AsmCargado(n) != null);
            r["ensamblados"] = asms;
            if (asms.Values.Any(v => !v)) problemas.Add("hay ensamblados del GM sin cargar");

            // 2. contenedor IoC
            bool contenedorOk = false;
            try { ContenedorGm(); contenedorOk = true; }
            catch (BridgeException ex) { problemas.Add(ex.Message); }
            r["ioc_inicializado"] = contenedorOk;

            // 3. config de la aplicacion
            var rutaCfg = Environment.ExpandEnvironmentVariables(
                "%PROGRAMDATA%\\Autodesk\\C3D-GeoTechModeler-2027\\Application.config");
            r["config"] = new Dictionary<string, object> { { "ruta", rutaCfg }, { "existe", File.Exists(rutaCfg) } };
            if (!File.Exists(rutaCfg)) problemas.Add("falta Application.config del GM");

            // 4. dibujo: superficies y estilos de nombre fijo que CreateStickLogProfile exige
            var doc = Doc();
            var db = doc.Database;
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                // superficies
                var superficies = new List<string>();
                foreach (ObjectId id in ObtenerSuperficies())
                { superficies.Add(NombreDe(tr.GetObject(id, OpenMode.ForRead))); }
                r["superficies"] = superficies;
                bool topOk = superficies.Contains("GM - Top Surface");
                r["superficie_top"] = topOk;
                if (!topOk) problemas.Add("no existe la superficie 'GM - Top Surface': CreateStickLogProfile lanza NullReferenceException al leer su estilo (TopSurface se busca por ese nombre exacto y el resultado se usa sin chequeo)");
                var huerfanas1 = superficies.Where(s => s != null && s.StartsWith("GM - Stratum - ") && s.EndsWith(".1")).ToList();
                r["superficies_sufijo_1"] = huerfanas1;

                // estilos fijos
                var estilos = new Dictionary<string, bool>();
                estilos["ProfileViewStyles/GM - Standard"] = ExisteEstilo(tr, "ProfileViewStyles", "GM - Standard");
                estilos["ProfileViewBandSetStyles/GM - Standard"] = ExisteEstilo(tr, "ProfileViewBandSetStyles", "GM - Standard");
                estilos["ProfileLabelSetStyles/GM - Standard"] = ExisteEstilo(tr, "ProfileLabelSetStyles", "GM - Standard");
                estilos["ProfileStyles/GM - Top Surface"] = ExisteEstilo(tr, "ProfileStyles", "GM - Top Surface");
                estilos["ProfileStyles/GM - Hidden"] = ExisteEstilo(tr, "ProfileStyles", "GM - Hidden");
                estilos["ProfileStyles/GM - Stratum Surface"] = ExisteEstilo(tr, "ProfileStyles", "GM - Stratum Surface");
                r["estilos_fijos"] = estilos;
                foreach (var kv in estilos.Where(kv => !kv.Value))
                    problemas.Add("falta el estilo " + kv.Key);

                // hatches huerfanos del sticklog
                int huerfanos = 0;
                var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
                foreach (ObjectId id in ms)
                {
                    if (!id.IsValid || id.IsErased) continue;
                    var e = tr.GetObject(id, OpenMode.ForRead) as Entity;
                    if (e is Hatch && e.Layer == "GM-PROF-STICKLOG-2D") huerfanos++;
                }
                r["hatches_sticklog"] = huerfanos;

                // grupos de ACAD_GROUP con miembros borrados: causa REAL del NRE
                // (DeleteStickLogProfile -> StickLogDiagram.Delete ->
                // ProfileStickLog.Delete -> ObjectId.GetObject sobre un miembro muerto)
                var muertos = GruposMuertos(tr, db);
                r["grupos_muertos"] = muertos.Count;
                if (muertos.Count > 0)
                    problemas.Add(muertos.Count + " grupo(s) con miembros borrados: DeleteStickLogProfile lanza NullReferenceException al recorrerlos (gm_reparar borrar_grupos_muertos=true)");
                tr.Commit();
            }

            // 5. servicios del GM: punto de grupo y settings (solo si hay contenedor)
            if (contenedorOk)
            {
                var cont = ContenedorGm();
                using (AmbitoGm(cont))
                {
                    try
                    {
                        var settingsRepo = ResolverGm(cont, TipoGm("Aecc.Gtm.CADServices", "Aecc.Gtm.CADServices.ApplicationSettingsRepository"));
                        var docService = ResolverGm(cont, TipoGm("Aecc.Gtm.CADServices", "Aecc.Gtm.CADServices.AcadDocumentService"));
                        using (var trGm = (IDisposable)TransaccionGm(docService))
                        {
                            var settings = InvocarGm(settingsRepo, "GetApplicationSettings");
                            r["project_id"] = settings == null ? null : PropGm(settings, "ProjectId");
                            if (settings != null)
                                r["perfil_configuracion"] = Val(PropGm(settings, "ProfileStickLogSettings"), 0, 1);
                            InvocarGm(trGm, "CommitTransaction");
                        }
                    }
                    catch (Exception ex) { r["settings_error"] = (ex is BridgeException) ? ex.Message : ExcepcionDetallada(ex); }
                }
            }

            r["problemas"] = problemas;
            r["ok"] = problemas.Count == 0;
            Log.Write("gm.diagnosticar problemas=" + problemas.Count);
            return r;
        }

        private static IEnumerable ObtenerSuperficies()
        {
            var civil = CivilDoc();
            var mi = civil.GetType().GetMethod("GetSurfaceIds", Type.EmptyTypes);
            var r = mi == null ? null : mi.Invoke(civil, null);
            return r as IEnumerable ?? new object[0];
        }

        private static bool ExisteEstilo(Transaction tr, string familia, string nombre)
        {
            try
            {
                object col = ColeccionEstilos(familia);
                foreach (ObjectId id in (IEnumerable)col)
                {
                    if (NombreDe(tr.GetObject(id, OpenMode.ForRead)) == nombre) return true;
                }
                return false;
            }
            catch { return false; }
        }

        // ---------- gm.reparar ----------

        private static object GmReparar(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            bool aplicar = p["aplicar"]?.GetValue<bool>() ?? false;
            bool quitarSufijo = p["renombrar_sufijo_1"]?.GetValue<bool>() ?? true;
            bool borrarHuerfanos = p["borrar_hatches_huerfanos"]?.GetValue<bool>() ?? false;
            bool borrarGrupos = p["borrar_grupos_muertos"]?.GetValue<bool>() ?? false;
            var acciones = new List<object>();
            var doc = Doc();
            var db = doc.Database;
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                if (quitarSufijo)
                {
                    var nombres = new Dictionary<string, ObjectId>();
                    foreach (ObjectId id in ObtenerSuperficies())
                        nombres[NombreDe(tr.GetObject(id, OpenMode.ForRead))] = id;
                    foreach (var kv in nombres.Where(kv => kv.Key != null && kv.Key.EndsWith(".1")).ToList())
                    {
                        var destino = kv.Key.Substring(0, kv.Key.Length - 2);
                        if (nombres.ContainsKey(destino))
                        {
                            acciones.Add(new Dictionary<string, object> { { "superficie", kv.Key },
                                { "accion", "sin cambio: ya existe '" + destino + "'" } });
                            continue;
                        }
                        if (aplicar)
                        {
                            var o = tr.GetObject(kv.Value, OpenMode.ForWrite);
                            var pi = o.GetType().GetProperty("Name");
                            pi.SetValue(o, destino);
                        }
                        acciones.Add(new Dictionary<string, object> { { "superficie", kv.Key },
                            { "accion", (aplicar ? "renombrada a " : "renombraria a ") + destino } });
                    }
                }
                if (borrarHuerfanos)
                {
                    int n = 0;
                    var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForRead);
                    foreach (ObjectId id in ms)
                    {
                        if (!id.IsValid || id.IsErased) continue;
                        var e = tr.GetObject(id, OpenMode.ForRead) as Entity;
                        if (e is Hatch && e.Layer == "GM-PROF-STICKLOG-2D")
                        {
                            if (aplicar) { e.UpgradeOpen(); e.Erase(); }
                            n++;
                        }
                    }
                    acciones.Add(new Dictionary<string, object> { { "hatches_sticklog", n },
                        { "accion", aplicar ? "borrados" : "se borrarian" } });
                }
                if (borrarGrupos)
                {
                    // port de la limpieza LISP del 2026-10-15 (dictremove sobre ACAD_GROUP).
                    // Se borra el grupo si TODOS sus miembros estan muertos, o si tiene
                    // miembros muertos y todos los identificables estan en capas GM-*.
                    // Un grupo ajeno al GM con miembros muertos se reporta y no se toca.
                    int n = 0;
                    var detalle = new List<object>();
                    foreach (var g in GruposMuertos(tr, db))
                    {
                        string accion;
                        if (!(bool)g["borrable"]) accion = "sin cambio: tiene miembros fuera de capas GM-*";
                        else if (!aplicar) { accion = "se borraria"; n++; }
                        else
                        {
                            accion = BorrarGrupo(tr, db, (ObjectId)g["_id"], (string)g["nombre"]);
                            if (accion.StartsWith("borrado")) n++;
                        }
                        g.Remove("_id");
                        g["accion"] = accion;
                        detalle.Add(g);
                    }
                    acciones.Add(new Dictionary<string, object> { { "grupos_muertos", n },
                        { "accion", aplicar ? "borrados" : "se borrarian" }, { "detalle", detalle } });
                }
                tr.Commit();
            }
            Log.Write("gm.reparar aplicar=" + aplicar + " acciones=" + acciones.Count);
            return new Dictionary<string, object> { { "aplicado", aplicar }, { "acciones", acciones },
                { "nota", aplicar ? null : "simulacion: repita con aplicar=true" } };
        }

        // Grupos de ACAD_GROUP con al menos un miembro muerto (nulo, invalido o
        // borrado). Abre los miembros borrados con openErased para leer su capa.
        // Cada registro: nombre, miembros, muertos, capas, borrable y _id (interno).
        private static List<Dictionary<string, object>> GruposMuertos(Transaction tr, Database db)
        {
            var r = new List<Dictionary<string, object>>();
            var gd = (DBDictionary)tr.GetObject(db.GroupDictionaryId, OpenMode.ForRead);
            var entradas = new List<KeyValuePair<string, ObjectId>>();
            foreach (DBDictionaryEntry de in gd) entradas.Add(new KeyValuePair<string, ObjectId>(de.Key, de.Value));
            foreach (var de in entradas)
            {
                if (de.Value.IsNull || de.Value.IsErased) continue;
                var g = tr.GetObject(de.Value, OpenMode.ForRead) as Group;
                if (g == null) continue;
                ObjectId[] ids;
                try { ids = g.GetAllEntityIds(); }
                catch (Exception ex) { throw new BridgeException(Rpc.ErrInternal, "No se pueden leer miembros del grupo " + de.Key + ": " + ex.Message); }
                int muertos = 0, vivos = 0;
                bool soloGm = true, capaDesconocida = false;
                var capas = new SortedSet<string>(StringComparer.OrdinalIgnoreCase);
                foreach (var id in ids)
                {
                    bool muerto = id.IsNull || !id.IsValid || id.IsErased || id.IsEffectivelyErased;
                    if (muerto) muertos++; else vivos++;
                    if (id.IsNull || !id.IsValid) { capaDesconocida = true; continue; }
                    try
                    {
                        var e = tr.GetObject(id, OpenMode.ForRead, true) as Entity;
                        if (e == null) { capaDesconocida = true; continue; }
                        capas.Add(e.Layer);
                        if (!e.Layer.StartsWith("GM-", StringComparison.OrdinalIgnoreCase)) soloGm = false;
                    }
                    catch { capaDesconocida = true; }
                }
                // NumEntities (leido por reflexion) mayor que los ids devueltos
                // tambien delata referencias que ya no resuelven
                try
                {
                    var pn = g.GetType().GetProperty("NumEntities");
                    int declarados = pn == null ? ids.Length : Convert.ToInt32(pn.GetValue(g));
                    if (declarados > ids.Length) muertos += declarados - ids.Length;
                }
                catch { }
                bool vacioGm = GmGroupPolicy.EmptyGm(de.Key, ids.Length, muertos);
                if (muertos == 0 && !vacioGm) continue;
                r.Add(new Dictionary<string, object>
                {
                    { "nombre", de.Key }, { "miembros", ids.Length }, { "muertos", muertos },
                    { "capas", capas.ToList() },
                    { "vacio_gm", vacioGm },
                    { "borrable", vacioGm || GmGroupPolicy.CanErase(de.Key, vivos, soloGm, capas.Count, capaDesconocida) },
                    { "_id", de.Value }
                });
            }
            return r;
        }

        // Erase del grupo (lo que hace GROUP > Explode); si falla, dictremove como
        // en la limpieza LISP original.
        private static string BorrarGrupo(Transaction tr, Database db, ObjectId id, string nombre)
        {
            try
            {
                var g = tr.GetObject(id, OpenMode.ForWrite);
                g.Erase();
                return "borrado (Erase)";
            }
            catch (Exception ex1)
            {
                try
                {
                    var gd = (DBDictionary)tr.GetObject(db.GroupDictionaryId, OpenMode.ForWrite);
                    gd.Remove(nombre);
                    return "borrado (dictremove; Erase fallo: " + ex1.Message + ")";
                }
                catch (Exception ex2) { return "error: " + ex1.Message + " / " + ex2.Message; }
            }
        }

        // ---------- gm.perfil_sondeos (CreateStickLogProfile + diagrama) ----------

        private static object GmPerfilSondeos(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string alinNombre = Txt(p, "alineamiento");
            string vistaNombre = Txt(p, "vista") ?? (alinNombre + " - Sondeos");
            string topSuperficie = Txt(p, "superficie_top") ?? "GM - Top Surface";
            double exag = Num(p, "exageracion") ?? 4.0;
            bool soloPerfil = p["solo_perfil"]?.GetValue<bool>() ?? false;
            if (string.IsNullOrEmpty(alinNombre))
                throw new BridgeException(Rpc.ErrParams, "falta 'alineamiento'");

            var cont = ContenedorGm();
            var r = new Dictionary<string, object> {
                { "aviso", "Datos geotecnicos hipoteticos/preliminares" }, { "completo", false }
            };
            using (AmbitoGm(cont))
            {
                var tCad = "Aecc.Gtm.CADServices";
                // el DebugLogger del GM es Scoped: habilitarlo en ESTE scope para que
                // CreateStickLogProfile deje su traza en DebugLog_*.txt
                try
                {
                    var lg = ResolverGm(cont, TipoGm("Aecc.Gtm.Domain", "Aecc.Gtm.Domain.DebugLogger"));
                    FijarPropGm(lg, "IsEnabled", true);
                }
                catch { }
                Log.Write("gm.perfil_sondeos: resolviendo servicios");
                var docService = ResolverGm(cont, TipoGm(tCad, tCad + ".AcadDocumentService"));
                var landServices = ResolverGm(cont, TipoGm(tCad, tCad + ".LandServices"));
                var profileService = ResolverGm(cont, TipoGm(tCad, tCad + ".ProfileService"));
                var repo = ResolverGm(cont, TipoGm("Aecc.Gtm.DomainPersistence", "Aecc.Gtm.DomainPersistence.AGMBoringRepository"));
                var settingsRepo = ResolverGm(cont, TipoGm(tCad, tCad + ".ApplicationSettingsRepository"));
                var appConfig = ResolverGm(cont, TipoGm("Aecc.Gtm.Domain", "Aecc.Gtm.Domain.IApplicationConfig"));

                var doc = AcadApp.DocumentManager.MdiActiveDocument;
                using (doc.LockDocument())
                using (var trGm = (IDisposable)TransaccionGm(docService))
                {
                    GmAtomicOperation.Execute(() =>
                    {
                        var settings = InvocarGm(settingsRepo, "GetApplicationSettings");
                        if (settings == null)
                            throw new BridgeException(Rpc.ErrParams, "el dibujo no tiene settings del GM guardados (no hay proyecto GM activo)");
                        var projectId = (string)PropGm(settings, "ProjectId");
                        r["project_id"] = projectId;

                        Log.Write("gm.perfil_sondeos: GetBoreholes");
                        var boreholes = (IList)InvocarGm(repo, "GetBoreholes", projectId);
                        var conEstratos = new List<object>();
                        double? minE = null, maxE = null;
                        foreach (var b in boreholes)
                        {
                            var strata = PropGm(b, "Strata") as IList;
                            if (strata == null || strata.Count == 0) continue;
                            conEstratos.Add(b);
                            double elev = Convert.ToDouble(PropGm(b, "Elevation"));
                            double fondo = elev - Convert.ToDouble(PropGm(b, "TotalDepth"));
                            if (maxE == null || elev > maxE) maxE = elev;
                            if (minE == null || fondo < minE) minE = fondo;
                        }
                        r["sondeos"] = conEstratos.Count;
                        if (conEstratos.Count == 0)
                            throw new BridgeException(Rpc.ErrParams, "el proyecto GM no tiene sondeos con estratos");

                        Log.Write("gm.perfil_sondeos: GetAlignment");
                        var alignment = InvocarGm(landServices, "GetAlignment", alinNombre);
                        if (alignment == null)
                            throw new BridgeException(Rpc.ErrParams, "no existe el alineamiento '" + alinNombre + "'");
                        double e0 = Num(p, "estacion_inicio") ?? Convert.ToDouble(PropGm(alignment, "StartingStation"));
                        double e1 = Num(p, "estacion_fin") ?? Convert.ToDouble(PropGm(alignment, "EndingStation"));

                        // configuracion del sticklog
                        var tCfg = TipoGm(tCad, tCad + ".StickLogConfiguration");
                        var cfg = Activator.CreateInstance(tCfg);
                        var saved = PropGm(settings, "ProfileStickLogSettings");
                        // Keep the drawing's existing dimensions/visibility settings.
                        // The native location color has a different representation; retain its default.
                        if (saved != null)
                            foreach (var target in tCfg.GetProperties(BindingFlags.Public | BindingFlags.Instance))
                            {
                                if (!target.CanWrite || target.GetIndexParameters().Length != 0) continue;
                                if (ReflectionRead.TryRead(saved, target.Name, out var value) &&
                                    value != null && target.PropertyType.IsInstanceOfType(value))
                                    target.SetValue(cfg, value);
                            }
                        if (!soloPerfil)
                        {
                            try
                            {
                                var field = GmProfileContract.Field(Txt(p, "campo_geologia"),
                                    saved == null ? null : PropGm(saved, "ProfileGeologyField") as string);
                                var counts = new Dictionary<string, int>();
                                foreach (var b in conEstratos)
                                    counts[Convert.ToString(PropGm(b, "BoringId"))] =
                                        ((IList)InvocarGm(b, "GetStrataByFieldName", field, false)).Count;
                                GmProfileContract.RequireStrata(counts);
                                FijarPropGm(cfg, "ProfileGeologyField", field);
                                r["campo_geologia"] = field;
                                r["estratos_por_sondeo"] = counts;
                            }
                            catch (ArgumentException ex) { throw new BridgeException(Rpc.ErrParams, ex.Message); }
                        }
                        FijarPropGm(cfg, "StratumProfiles", true);
                        FijarPropGm(cfg, "WaterTableProfile", true);
                        FijarPropGm(cfg, "VerticalExaggeration", exag);
                        FijarPropGm(cfg, "MinElev", (double)minE);
                        FijarPropGm(cfg, "MaxElev", (double)maxE);

                        // Load only existing styles through the non-interactive native API.
                        // AssignHatchStylesToBoreholeStrata may open a modal and rewrite the
                        // shared config when there are no matches; an MCP call must fail instead.
                        object hatchCfg = null;
                        bool conHatch = !soloPerfil && (p["hatch_geologia"]?.GetValue<bool>() ?? false);
                        if (conHatch)
                        {
                            var tHatchCfg = TipoGm(tCad, tCad + ".GeologyHatchStyleConfiguration");
                            var rutaHatch = PropGm(appConfig, "GeologyHatchStyleConfigurationPath");
                            hatchCfg = Activator.CreateInstance(tHatchCfg, new object[] { docService, rutaHatch });
                            InvocarGm(hatchCfg, "LoadFromFile", true);
                            var errors = (IList)PropGm(hatchCfg, "Errors");
                            if (errors.Count > 0)
                                throw new BridgeException(Rpc.ErrParams, "Estilos GM invalidos: " +
                                    InvocarGm(hatchCfg, "GetErrorMessage") + ". No se modificaron perfiles.");
                            var field = PropGm(cfg, "ProfileGeologyField");
                            var lookup = PropGm(hatchCfg, "HatchStyleLookup");
                            var defaultStyle = PropGm(hatchCfg, "DefaultHatchStyle");
                            int matches = 0;
                            foreach (var b in conEstratos)
                            {
                                int matched = Convert.ToInt32(InvocarGm(b, "AssignHatchStylesToStrata", field, lookup, defaultStyle));
                                var strata = (IList)InvocarGm(b, "GetStrataByFieldName", field, false);
                                if (matched == 0 || strata.Cast<object>().Any(x => PropGm(x, "HatchStyle") == null))
                                    throw new BridgeException(Rpc.ErrParams, "Faltan estilos GM para " +
                                        PropGm(b, "BoringId") + ". Configure los estilos existentes; no se modificaron perfiles.");
                                matches += matched;
                            }
                            r["estratos_con_estilo_coincidente"] = matches;
                        }
                        else
                        {
                            // GM's solid-fill renderer dereferences HatchStyle even when
                            // hatching is disabled. Keep an outline-only profile consistent.
                            FijarPropGm(cfg, "SolidFilledStrata", false);
                        }
                        r["hatch_geologia"] = conHatch;
                        r["relleno_solido"] = PropGm(cfg, "SolidFilledStrata");
                        Log.Write("gm.perfil_sondeos: GetProfileView");

                        // punto de insercion: la vista existente o el parametro 'origen'
                        object insertPoint;
                        var vistaExistente = InvocarGm(landServices, "GetProfileView", alinNombre, vistaNombre);
                        if (vistaExistente != null)
                            insertPoint = InvocarGm(profileService, "GetProfileViewInsertPoint", vistaExistente);
                        else
                        {
                            var o = p["origen"] as JsonArray;
                            if (o == null || o.Count < 2)
                                throw new BridgeException(Rpc.ErrParams, "la vista '" + vistaNombre + "' no existe: pase 'origen' [x,y]");
                            insertPoint = new Point3d(o[0].GetValue<double>(), o[1].GetValue<double>(), 0);
                        }

                        // LA llamada bajo investigacion (NRE del handoff): capturada con detalle
                        object desplazamiento = null;
                        Log.Write("gm.perfil_sondeos: CreateStickLogProfile");
                        try
                        {
                            desplazamiento = InvocarGm(profileService, "CreateStickLogProfile",
                                insertPoint, alignment, vistaNombre, e0, e1, topSuperficie, cfg, hatchCfg);
                            r["perfil"] = "CreateStickLogProfile OK";
                        }
                        catch (BridgeException bex)
                        {
                            r["perfil_error"] = bex.Message;
                            r["nota"] = "fallo CreateStickLogProfile; consultar el estado de la transaccion antes de reintentar";
                            return false;
                        }

                        if (!soloPerfil)
                        {
                            try
                            {
                                var diagService = ResolverGm(cont, TipoGm(tCad, tCad + ".DiagramingService"));
                                var project = InvocarGm(repo, "GetProject", projectId);
                                var cs = project == null ? "" : (string)PropGm(project, "CSCode");
                                var escala = InvocarGm(landServices, "GetDrawingScale");
                                var lista = CastLista(conEstratos, boreholes);
                                var tup = InvocarGm(diagService, "CreateStickLogDiagram", lista, cs, alinNombre, vistaNombre, cfg, escala, desplazamiento);
                                var diagrama = PropGm(tup, "Item1");
                                var outside = (IList)PropGm(tup, "Item2");
                                var outsideIds = new List<string>();
                                foreach (var b in outside) outsideIds.Add(Convert.ToString(PropGm(b, "BoringId")));
                                r["sondeos_fuera_rango"] = outsideIds;
                                var render = InvocarGm(diagrama, "Render");
                                r["sticklogs"] = Val(render);
                                int created = Convert.ToInt32(PropGm(render, "Item1"));
                                int missing = Convert.ToInt32(PropGm(render, "Item2"));
                                r["sticklogs_creados"] = created;
                                r["sticklogs_sin_estratos"] = missing;
                                bool complete = GmProfileContract.Complete(created, missing, conEstratos.Count - outside.Count);
                                r["completo"] = complete;
                                if (!complete)
                                    r["diagrama_error"] = "Render incompleto: " + created + " creados, " +
                                        missing + " sin estratos. Se revierte la operacion.";
                                InvocarGm(profileService, "SetDrawOrderForSolidFilledStickLogObjects", diagrama);
                            }
                            catch (Exception ex)
                            {
                                r["completo"] = false;
                                r["diagrama_error"] = (ex as BridgeException)?.Message ?? ExcepcionDetallada(ex);
                            }
                        }
                        return soloPerfil || (bool)r["completo"];
                    }, () => {
                        InvocarGm(trGm, "CommitTransaction");
                        r["transaccion"] = "confirmada";
                        r["cambios_revertidos"] = false;
                    }, () => {
                        // AbortTransaction also resets the GM document service's cached
                        // transaction. Dispose alone leaves that cache stale on this GM version.
                        r["completo"] = false;
                        r["transaccion"] = "reversion_pendiente";
                        InvocarGm(trGm, "AbortTransaction");
                        r["transaccion"] = "revertida";
                        r["cambios_revertidos"] = true;
                        if (r.TryGetValue("sticklogs_creados", out var attempted))
                            r["sticklogs_creados_intento"] = attempted;
                        r["sticklogs_creados"] = 0;
                        if (r.TryGetValue("perfil", out var profileAttempt))
                        {
                            r["perfil_intento"] = profileAttempt;
                            r["perfil"] = "revertido; perfiles anteriores conservados";
                        }
                    });
                }
            }
            Log.Write("gm.perfil_sondeos " + alinNombre + "/" + vistaNombre);
            return r;
        }

        // List<Borehole> tipada por reflexion a partir de objetos sueltos
        private static object CastLista(List<object> items, IList origen)
        {
            var tElem = origen.GetType().IsGenericType ? origen.GetType().GetGenericArguments()[0] : items[0].GetType();
            var lista = (IList)Activator.CreateInstance(typeof(List<>).MakeGenericType(tElem));
            foreach (var it in items) lista.Add(it);
            return lista;
        }

        // ---------- gm.superficies ----------

        private static object GmConstruirSuperficies(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            bool fondo = p["superficie_fondo"]?.GetValue<bool>() ?? false;
            var cont = ContenedorGm();
            using (AmbitoGm(cont))
            {
                var docService = ResolverGm(cont, TipoGm("Aecc.Gtm.CADServices", "Aecc.Gtm.CADServices.AcadDocumentService"));
                var stratum = ResolverGm(cont, TipoGm("Aecc.Gtm.CADServices", "Aecc.Gtm.CADServices.StratumServices.StratumService"));
                var doc = AcadApp.DocumentManager.MdiActiveDocument;
                using (var trGm = (IDisposable)TransaccionGm(docService))
                using (doc.LockDocument())
                {
                    try
                    {
                        var lista = InvocarGm(stratum, "BuildStratumSurfaces", fondo) as IList;
                        var nombres = new List<object>();
                        if (lista != null)
                            foreach (var s in lista) nombres.Add(NombreDe(s));
                        Log.Write("gm.superficies creadas=" + nombres.Count);
                        return new Dictionary<string, object> { { "superficies", nombres },
                            { "aviso", "Datos geotecnicos hipoteticos/preliminares" } };
                    }
                    finally { try { InvocarGm(trGm, "CommitTransaction"); } catch { } }
                }
            }
        }

        // ---------- gm.3d_boreholes ----------

        private static object Gm3dBoreholes(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            double altura = Num(p, "altura_rotulo") ?? 2.0;
            double diametro = Num(p, "diametro") ?? 2.0;
            double exag = Num(p, "exageracion") ?? 1.0;
            string campo = Txt(p, "campo_geologia") ?? "GeologyCode";
            var cont = ContenedorGm();
            using (AmbitoGm(cont))
            {
                var tCad = "Aecc.Gtm.CADServices";
                var docService = ResolverGm(cont, TipoGm(tCad, tCad + ".AcadDocumentService"));
                var servicio = ResolverGm(cont, TipoGm(tCad, tCad + ".Borehole3D.Borehole3DService"));
                var repo = ResolverGm(cont, TipoGm("Aecc.Gtm.DomainPersistence", "Aecc.Gtm.DomainPersistence.AGMBoringRepository"));
                var settingsRepo = ResolverGm(cont, TipoGm(tCad, tCad + ".ApplicationSettingsRepository"));
                var doc = AcadApp.DocumentManager.MdiActiveDocument;
                using (var trGm = (IDisposable)TransaccionGm(docService))
                using (doc.LockDocument())
                {
                    try
                    {
                        var settings = InvocarGm(settingsRepo, "GetApplicationSettings");
                        if (settings == null)
                            throw new BridgeException(Rpc.ErrParams, "el dibujo no tiene settings del GM guardados");
                        var projectId = (string)PropGm(settings, "ProjectId");
                        var boreholes = (IList)InvocarGm(repo, "GetBoreholes", projectId);
                        var n = InvocarGm(servicio, "Create3DBoreholes", boreholes, altura, diametro, exag, campo);
                        Log.Write("gm.3d_boreholes n=" + n);
                        return new Dictionary<string, object> { { "creados", n },
                            { "aviso", "Datos geotecnicos hipoteticos/preliminares" } };
                    }
                    finally { try { InvocarGm(trGm, "CommitTransaction"); } catch { } }
                }
            }
        }

        // ---------- gm.stratum_display ----------

        private static object GmStratumDisplay(JsonObject p, string method)
        {
            bool aplicar = p["exageracion"] != null || p["usar_exageracion"] != null;
            if (aplicar) ExigirEscritura(method, p);
            var cont = ContenedorGm();
            using (AmbitoGm(cont))
            {
                var tCad = "Aecc.Gtm.CADServices";
                var docService = ResolverGm(cont, TipoGm(tCad, tCad + ".AcadDocumentService"));
                var servicio = ResolverGm(cont, TipoGm(tCad, tCad + ".StratumVisibilityService"));
                var doc = AcadApp.DocumentManager.MdiActiveDocument;
                using (var trGm = (IDisposable)TransaccionGm(docService))
                using (doc.LockDocument())
                {
                    try
                    {
                        var settings = InvocarGm(servicio, "GetStratumVisibilitySettings");
                        if (aplicar && settings != null)
                        {
                            if (p["usar_exageracion"] != null)
                                FijarPropGm(settings, "UseVerticalExaggeration", p["usar_exageracion"].GetValue<bool>());
                            if (p["exageracion"] != null)
                                FijarPropGm(settings, "VerticalExag", p["exageracion"].GetValue<double>());
                            // GmSurfaceType.FullStratum = 1 (enum del dominio)
                            var tEnum = TipoGm("Aecc.Gtm.Domain", "Aecc.Gtm.Domain.GmSurfaceType");
                            var valor = Enum.Parse(tEnum, Txt(p, "tipo_superficie") ?? "FullStratum", true);
                            InvocarGm(servicio, "ApplyStratumVisibilitySettings", settings, valor);
                        }
                        Log.Write("gm.stratum_display aplicar=" + aplicar);
                        return new Dictionary<string, object> { { "settings", Val(settings, 0, 1) }, { "aplicado", aplicar } };
                    }
                    finally { try { InvocarGm(trGm, "CommitTransaction"); } catch { } }
                }
            }
        }

        // ---------- diag.dialogos ----------

        [DllImport("user32.dll")] private static extern bool IsWindowEnabled(IntPtr hWnd);
        [DllImport("user32.dll")] private static extern bool IsWindowVisible(IntPtr hWnd);
        [DllImport("user32.dll")] private static extern bool EnumThreadWindows(uint threadId, EnumThreadDelegate fn, IntPtr lp);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetWindowText(IntPtr h, StringBuilder sb, int max);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] private static extern int GetClassName(IntPtr h, StringBuilder sb, int max);
        [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
        [DllImport("user32.dll")] private static extern bool EnumWindows(EnumThreadDelegate fn, IntPtr lp);
        [DllImport("user32.dll")] private static extern bool EnumChildWindows(IntPtr parent, EnumThreadDelegate fn, IntPtr lp);
        private delegate bool EnumThreadDelegate(IntPtr hWnd, IntPtr lParam);

        // Handle de la ventana principal, capturado en el hilo principal al
        // inicializar (AcadApp.MainWindow no se toca desde el hilo del socket).
        internal static IntPtr HandlePrincipal = IntPtr.Zero;

        internal static void CapturarHandlePrincipal()
        {
            try { HandlePrincipal = AcadApp.MainWindow.Handle; } catch { }
        }

        private static object DiagDialogos(JsonObject p) { return DiagDialogosSinHilo(); }

        // Servido desde el hilo del socket (0.5.2): solo user32, sin API de AutoCAD,
        // asi responde aunque un modal tenga bloqueada la bomba de Idle. Para cada
        // dialogo clasico (#32770) devuelve tambien sus textos estaticos: el mensaje
        // de un MessageBox queda como evidencia sin captura de pantalla.
        internal static object DiagDialogosSinHilo()
        {
            IntPtr hMain = HandlePrincipal;
            if (hMain == IntPtr.Zero)
                try { hMain = System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle; } catch { }
            bool mainHabilitada = hMain != IntPtr.Zero && IsWindowEnabled(hMain);
            uint pidPropio = (uint)System.Diagnostics.Process.GetCurrentProcess().Id;
            var ventanas = new List<object>();
            EnumWindows((h, lp) =>
            {
                if (!IsWindowVisible(h) || h == hMain) return true;
                GetWindowThreadProcessId(h, out uint pid);
                if (pid != pidPropio) return true;
                var titulo = new StringBuilder(256); GetWindowText(h, titulo, 256);
                var clase = new StringBuilder(128); GetClassName(h, clase, 128);
                var cl = clase.ToString();
                // los dialogos modales clasicos de AutoCAD/WPF/WinForms
                if (cl == "#32770" || cl.StartsWith("WindowsForms10") || cl.StartsWith("HwndWrapper"))
                {
                    var v = new Dictionary<string, object> { { "titulo", titulo.ToString() }, { "clase", cl },
                        { "habilitada", IsWindowEnabled(h) } };
                    if (cl == "#32770")
                    {
                        var textos = new List<string>();
                        EnumChildWindows(h, (hc, lc) =>
                        {
                            var cc = new StringBuilder(64); GetClassName(hc, cc, 64);
                            var c = cc.ToString();
                            if (c == "Static" || c == "Button" || c == "DirectUIHWND")
                            {
                                var tx = new StringBuilder(1024); GetWindowText(hc, tx, 1024);
                                if (tx.Length > 0 && textos.Count < 20) textos.Add(tx.ToString());
                            }
                            return true;
                        }, IntPtr.Zero);
                        v["textos"] = textos;
                    }
                    ventanas.Add(v);
                }
                return true;
            }, IntPtr.Zero);
            return new Dictionary<string, object>
            {
                { "modal_abierto", !mainHabilitada },
                { "ventana_principal_habilitada", mainHabilitada },
                { "ventanas", ventanas },
                { "hilo", "socket" },
                { "nota", "modal_abierto=true significa que un dialogo bloquea Civil 3D y las peticiones al puente van a vencer por timeout" }
            };
        }
    }
}
