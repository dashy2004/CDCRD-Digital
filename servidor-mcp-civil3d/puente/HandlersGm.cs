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
            var pi = objeto.GetType().GetProperty(prop, BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase);
            if (pi == null)
                throw new BridgeException(Rpc.ErrParams, objeto.GetType().Name + " no tiene la propiedad " + prop);
            return pi.GetValue(objeto);
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
                tr.Commit();
            }
            Log.Write("gm.reparar aplicar=" + aplicar + " acciones=" + acciones.Count);
            return new Dictionary<string, object> { { "aplicado", aplicar }, { "acciones", acciones },
                { "nota", aplicar ? null : "simulacion: repita con aplicar=true" } };
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
            var r = new Dictionary<string, object> { { "aviso", "Datos geotecnicos hipoteticos/preliminares" } };
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
                using (var trGm = (IDisposable)TransaccionGm(docService))
                using (doc.LockDocument())
                {
                    try
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
                        FijarPropGm(cfg, "StratumProfiles", true);
                        FijarPropGm(cfg, "WaterTableProfile", true);
                        FijarPropGm(cfg, "VerticalExaggeration", exag);
                        FijarPropGm(cfg, "MinElev", (double)minE);
                        FijarPropGm(cfg, "MaxElev", (double)maxE);

                        // estilos de hatch de geologia. Por defecto NO se arma:
                        // el propio comando de prueba del GM pasa null, y con un
                        // ProfileGeologyField vacio AssignHatchStylesToBoreholeStrata
                        // es sospechoso de colgar el hilo principal (hallazgo 2026-10-15)
                        object hatchCfg = null;
                        bool conHatch = p["hatch_geologia"]?.GetValue<bool>() ?? false;
                        if (conHatch)
                        try
                        {
                            var tHatch = TipoGm(tCad, tCad + ".GeologyHatchingService");
                            var geoField = PropGm(cfg, "ProfileGeologyField");
                            var rutaHatch = PropGm(appConfig, "GeologyHatchStyleConfigurationPath");
                            var mi = tHatch.GetMethod("AssignHatchStylesToBoreholeStrata", BindingFlags.Public | BindingFlags.Static);
                            var lista = CastLista(conEstratos, boreholes);
                            hatchCfg = mi.Invoke(null, new object[] { docService, rutaHatch, projectId, lista, geoField });
                        }
                        catch (Exception ex) { r["hatch_config"] = "no disponible: " + ((ex as TargetInvocationException)?.InnerException ?? ex).Message; }
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
                            r["nota"] = "fallo CreateStickLogProfile: evidencia para el reporte del bug (active GM_DebugLogging_On y repita para el paso exacto)";
                            return r;
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
                                var render = InvocarGm(diagrama, "Render");
                                r["sticklogs"] = Val(render);
                                InvocarGm(profileService, "SetDrawOrderForSolidFilledStickLogObjects", diagrama);
                            }
                            catch (Exception ex) { r["diagrama_error"] = (ex as BridgeException)?.Message ?? ExcepcionDetallada(ex); }
                        }
                    }
                    finally
                    {
                        try { InvocarGm(trGm, "CommitTransaction"); } catch { }
                    }
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
        private delegate bool EnumThreadDelegate(IntPtr hWnd, IntPtr lParam);

        private static object DiagDialogos(JsonObject p)
        {
            var principal = AcadApp.MainWindow;
            IntPtr hMain = IntPtr.Zero;
            try { hMain = principal.Handle; } catch { }
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
                    ventanas.Add(new Dictionary<string, object> { { "titulo", titulo.ToString() }, { "clase", cl },
                        { "habilitada", IsWindowEnabled(h) } });
                return true;
            }, IntPtr.Zero);
            return new Dictionary<string, object>
            {
                { "modal_abierto", !mainHabilitada },
                { "ventana_principal_habilitada", mainHabilitada },
                { "ventanas", ventanas },
                { "nota", "modal_abierto=true significa que un dialogo bloquea Civil 3D y las peticiones al puente van a vencer por timeout" }
            };
        }
    }
}
