// Geotechnical Modeler (GM) projects without its dialogs: list, create, import CSV, link to the drawing.
// The GM ships no public API: its services are reached by reflection through its own IoC container,
// the same objects its Manage Data panel uses. Nothing here opens a GM window.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using Exception = System.Exception;

namespace Cdcrd.Geotecnia;

internal static class Gm
{
    internal const string Domain = "Aecc.Gtm.Domain", Persistence = "Aecc.Gtm.DomainPersistence", Cad = "Aecc.Gtm.CADServices";

    internal static Type Tipo(string asm, string nombre)
    {
        var a = AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault(x => string.Equals(x.GetName().Name, asm, StringComparison.OrdinalIgnoreCase))
            ?? throw new InvalidOperationException("El Geotechnical Modeler no esta cargado en esta sesion (falta " + asm + "); use gm_iniciar o abra su panel una vez");
        return a.GetType(nombre, false) ?? throw new InvalidOperationException("Tipo no encontrado en " + asm + ": " + nombre);
    }

    internal static object Contenedor() =>
        Tipo(Domain, Domain + ".IoC").GetProperty("Container", BindingFlags.Public | BindingFlags.Static)?.GetValue(null)
        ?? throw new InvalidOperationException("El Geotechnical Modeler aun no se ha iniciado en esta sesion; use gm_iniciar o abra su panel una vez");

    internal const string Plugin = "Aecc.Gtm.AutoCADPlugin";

    internal static bool Cargado(string asm) =>
        AppDomain.CurrentDomain.GetAssemblies().Any(x => string.Equals(x.GetName().Name, asm, StringComparison.OrdinalIgnoreCase));

    // True only when the GM has built its container: the state every other action needs.
    internal static bool Iniciado()
    {
        if (!Cargado(Domain)) return false;
        try { return Tipo(Domain, Domain + ".IoC").GetProperty("Container", BindingFlags.Public | BindingFlags.Static)?.GetValue(null) != null; }
        catch (Exception) { return false; }
    }

    // The GM plug-in inside Autodesk's own bundle; it is registered to load on the first GM command.
    internal static string RutaPlugin()
    {
        var raices = new[] { Environment.SpecialFolder.ProgramFiles, Environment.SpecialFolder.CommonApplicationData, Environment.SpecialFolder.ApplicationData }
            .Select(f => Path.Combine(Environment.GetFolderPath(f), "Autodesk", "ApplicationPlugins")).Where(Directory.Exists);
        foreach (var raiz in raices)
            foreach (var bundle in Directory.GetDirectories(raiz, "C3D-GeoTechModeler-*.bundle").OrderByDescending(x => x, StringComparer.OrdinalIgnoreCase))
            {
                string dll = Path.Combine(bundle, "Contents", Plugin + ".dll");
                if (File.Exists(dll)) return dll;
            }
        return null;
    }

    // Castle Windsor scope, as the GM presenters open one per operation.
    internal static IDisposable Ambito(object contenedor)
    {
        var ext = AppDomain.CurrentDomain.GetAssemblies().FirstOrDefault(x => x.GetName().Name == "Castle.Windsor")
            ?.GetType("Castle.MicroKernel.Lifestyle.LifestyleExtensions", false);
        if (ext == null) return null;
        foreach (var m in ext.GetMethods(BindingFlags.Public | BindingFlags.Static).Where(x => x.Name == "BeginScope" && x.GetParameters().Length == 1))
        {
            var tp = m.GetParameters()[0].ParameterType;
            object arg = tp.IsInstanceOfType(contenedor) ? contenedor : contenedor.GetType().GetProperty("Kernel")?.GetValue(contenedor);
            if (arg != null && tp.IsInstanceOfType(arg)) return m.Invoke(null, new[] { arg }) as IDisposable;
        }
        return null;
    }

    internal static object Resolver(object contenedor, string asm, string nombre) =>
        contenedor.GetType().GetMethod("Resolve", new[] { typeof(Type) }).Invoke(contenedor, new object[] { Tipo(asm, nombre) });

    internal static object Llamar(object objeto, string metodo, params object[] args)
    {
        var m = objeto.GetType().GetMethods(BindingFlags.Public | BindingFlags.Instance)
            .FirstOrDefault(x => x.Name == metodo && x.GetParameters().Length == args.Length
                && x.GetParameters().Select((p, i) => args[i] == null || p.ParameterType.IsInstanceOfType(args[i])).All(ok => ok))
            ?? throw new MissingMethodException(objeto.GetType().Name, metodo);
        try { return m.Invoke(objeto, args); }
        catch (TargetInvocationException ex) { throw new InvalidOperationException(objeto.GetType().Name + "." + metodo + ": " + ex.GetBaseException().Message, ex.GetBaseException()); }
    }

    internal static object Prop(object objeto, string nombre) => objeto?.GetType().GetProperty(nombre)?.GetValue(objeto);
}

internal static class GeotecniaService
{
    private static readonly string[] Actions = { "iniciar", "listar", "crear", "importar", "vincular", "agregar_sondeos", "superficie_superior", "sistema_coord" };
    internal const string TopSurface = "GM - Top Surface";

    private static string Text(JsonObject p, string key, bool required = true, int max = 260)
    {
        var s = p[key]?.GetValue<string>();
        if (string.IsNullOrWhiteSpace(s)) { if (required) throw new ArgumentException("Texto requerido: " + key); return null; }
        if (s.Length > max || s.Any(char.IsControl)) throw new ArgumentException("Texto invalido: " + key);
        return s;
    }

    private static string Csv(JsonObject p, string key, bool required)
    {
        var s = Text(p, key, required);
        if (s == null) return null;
        if (!Path.IsPathFullyQualified(s) || !string.Equals(Path.GetExtension(s), ".csv", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException(key + " debe ser la ruta absoluta de un .csv");
        if (!File.Exists(s)) throw new FileNotFoundException("No existe el archivo", s);
        return Path.GetFullPath(s);
    }

    internal static object Execute(JsonObject p, out bool changed)
    {
        changed = false;
        if (!DateTimeOffset.TryParse(Text(p, "vence_utc"), out var expires) || expires < DateTimeOffset.UtcNow || expires > DateTimeOffset.UtcNow.AddMinutes(5))
            throw new ArgumentException("Solicitud vencida o plazo invalido");
        if (p["pid"]?.GetValue<int>() != Environment.ProcessId) throw new ArgumentException("PID distinto al esperado");
        string action = Text(p, "accion");
        if (!Actions.Contains(action)) throw new ArgumentException("Accion desconocida");
        bool confirm = p["confirmar"]?.GetValue<bool>() ?? false;
        if (action != "listar" && confirm && Environment.GetEnvironmentVariable("CDCRD_C3D_SOLO_LECTURA") == "1")
            throw new InvalidOperationException("Sesion en solo lectura");
        if (action == "iniciar") return Iniciar(confirm, ref changed);
        var cont = Gm.Contenedor();
        using (Gm.Ambito(cont))
        {
            var repo = Gm.Resolver(cont, Gm.Persistence, Gm.Persistence + ".AGMBoringRepository");
            var settingsRepo = Gm.Resolver(cont, Gm.Cad, Gm.Cad + ".ApplicationSettingsRepository");
            var docService = Gm.Resolver(cont, Gm.Cad, Gm.Cad + ".AcadDocumentService");
            switch (action)
            {
                case "listar": return Listar(repo, settingsRepo, docService);
                case "crear": return Crear(repo, p, confirm, ref changed);
                case "importar": return Importar(repo, p, confirm, ref changed);
                case "vincular": return Vincular(repo, settingsRepo, docService, p, confirm, ref changed);
                case "sistema_coord": return SistemaCoord(cont, docService, p, confirm, ref changed);
                default: return EnDibujo(cont, repo, settingsRepo, docService, action, p, confirm, ref changed);
            }
        }
    }

    // Loads Autodesk's GM plug-in the way its first command would, without running any command or opening its panel.
    private static object Iniciar(bool confirm, ref bool changed)
    {
        if (Gm.Iniciado()) return new Dictionary<string, object> { ["ya_iniciado"] = true, ["iniciado"] = true };
        string dll = Gm.RutaPlugin() ?? throw new FileNotFoundException("No se encontro el Geotechnical Modeler instalado (C3D-GeoTechModeler-*.bundle)");
        var estado = new Dictionary<string, object> { ["ya_iniciado"] = false, ["plugin"] = dll, ["ensamblado_cargado"] = Gm.Cargado(Gm.Plugin) };
        if (!confirm) { estado["simulado"] = true; estado["iniciado"] = false; return estado; }
        Autodesk.AutoCAD.Runtime.ExtensionLoader.Load(dll);
        if (!Gm.Iniciado())
            throw new InvalidOperationException("El modulo de Autodesk se cargo pero no inicio sus servicios; abra su panel una vez");
        changed = true;
        estado["iniciado"] = true;
        return estado;
    }

    // Boreholes as COGO points and the top surface: BoreholeManager, the object behind "Add Boreholes To Drawing".
    private static object EnDibujo(object cont, object repo, object settingsRepo, object docService, string action, JsonObject p, bool confirm, ref bool changed)
    {
        var doc = App.DocumentManager.MdiActiveDocument ?? throw new InvalidOperationException("No hay dibujo activo");
        string id = EnTransaccion(docService, () => Vinculado(settingsRepo));
        if (string.IsNullOrEmpty(id)) throw new InvalidOperationException("El dibujo activo no esta vinculado a un proyecto del Geotechnical Modeler; use gm_vincular_proyecto");
        var proyecto = Existente(repo, id) ?? throw new InvalidOperationException("El proyecto del dibujo no existe en la base: " + id);
        var sondeos = (IList)Gm.Llamar(repo, "GetBoreholes", id);
        if (sondeos.Count == 0) throw new InvalidOperationException("El proyecto no tiene sondeos: " + id);
        var land = Gm.Resolver(cont, Gm.Cad, Gm.Cad + ".LandServices");
        bool SuperficieExiste() => EnTransaccion(docService, () => Existe(land));
        bool antes = SuperficieExiste();
        if (action == "superficie_superior")
        {
            bool recortar = p["recortar_bordes"]?.GetValue<bool>() ?? false;
            double largo = p["largo_maximo_m"]?.GetValue<double>() ?? 0.0;
            if (largo < 0 || largo > 100000) throw new ArgumentException("largo_maximo_m fuera de rango");
            if (antes) throw new InvalidOperationException("Ya existe la superficie '" + TopSurface + "'; no se reemplaza");
            if (!confirm) return new { simulacion = true, dibujo = doc.Name, proyecto_id = id, sondeos = sondeos.Count, superficie = TopSurface, existe = false };
            var manager = Gm.Resolver(cont, Gm.Cad, Gm.Cad + ".BoreholeManager");
            int puntos;
            using (doc.LockDocument())
                puntos = EnTransaccion(docService, () =>
                {
                    ImportarEstilos(cont, land);
                    Gm.Llamar(manager, "CreateTopSurfaceFromAllBoreholes", recortar, largo);
                    // Without boreholes in the drawing the GM still creates the surface, empty: throwing here aborts it.
                    int n = Puntos(Gm.Llamar(land, "GetSurface", TopSurface));
                    if (n < 3) throw new InvalidOperationException("La superficie '" + TopSurface + "' quedaria con " + n + " puntos; agregue antes los sondeos al dibujo (gm_agregar_sondeos_al_dibujo). No se creo");
                    return n;
                });
            changed = true;
            return new { simulacion = false, dibujo = doc.Name, proyecto_id = id, sondeos = sondeos.Count, superficie = TopSurface, existe = true, puntos, guardado = false };
        }
        string cs = (string)Gm.Prop(proyecto, "CSCode") ?? "";
        if (!confirm) return new { simulacion = true, dibujo = doc.Name, proyecto_id = id, sondeos = sondeos.Count, sistema_coord_del_proyecto = cs };
        var mgr = Gm.Resolver(cont, Gm.Cad, Gm.Cad + ".BoreholeManager");
        using (doc.LockDocument())
            EnTransaccion(docService, () =>
            {
                ImportarEstilos(cont, land);
                // InsertAllBoreholes also creates the point group "GM - All Boreholes".
                Gm.Llamar(mgr, "InsertAllBoreholes", ListaPara(mgr, "InsertAllBoreholes", repo, id), cs);
                return 0;
            });
        changed = true;
        return new { simulacion = false, dibujo = doc.Name, proyecto_id = id, sondeos = sondeos.Count, sistema_coord_del_proyecto = cs, guardado = false };
    }

    // The GM draws with its own styles ("GM - Hidden", "GM - Standard"...), copied from its template drawing the first
    // time its panel opens on a drawing. Existing styles are kept (replaceExistingStyles = false).
    private static void ImportarEstilos(object cont, object land)
    {
        var tipo = Gm.Tipo(Gm.Cad, Gm.Cad + ".StyleImporter.StyleImporter");
        var config = Gm.Resolver(cont, Gm.Domain, Gm.Domain + ".IApplicationConfig");
        var importer = Activator.CreateInstance(tipo, config, land);
        var metodo = tipo.GetMethod("ImportStylesFromTemplate") ?? throw new MissingMethodException("StyleImporter", "ImportStylesFromTemplate");
        var cuales = metodo.GetParameters()[0].ParameterType;
        var valores = Enum.IsDefined(cuales, "All") ? new[] { Enum.Parse(cuales, "All") } : Enum.GetValues(cuales).Cast<object>().ToArray();
        foreach (var v in valores)
        {
            try { metodo.Invoke(importer, new[] { v, (object)false }); }
            catch (TargetInvocationException ex) { throw new InvalidOperationException("Estilos del Geotechnical Modeler (" + v + "): " + ex.GetBaseException().Message); }
        }
    }

    // InsertAllBoreholes takes the repository's own list type: ask the repository for whichever list fits its first parameter.
    private static object ListaPara(object manager, string metodo, object repo, string id)
    {
        var tipo = manager.GetType().GetMethods().First(m => m.Name == metodo).GetParameters()[0].ParameterType;
        foreach (string fuente in new[] { "GetBoreholes", "GetBoreholeLocations" })
        {
            var lista = Gm.Llamar(repo, fuente, id);
            if (tipo.IsInstanceOfType(lista)) return lista;
        }
        throw new InvalidOperationException("El repositorio no ofrece la lista que pide " + metodo + " (" + tipo + ")");
    }

    // Number of points of a Civil TIN surface, read by reflection (this module does not reference the Civil assemblies).
    private static int Puntos(object superficie)
    {
        if (superficie == null) return 0;
        try
        {
            var general = superficie.GetType().GetMethod("GetGeneralProperties", Type.EmptyTypes)?.Invoke(superficie, null);
            object n = general?.GetType().GetProperty("NumberOfPoints")?.GetValue(general);
            return n == null ? 0 : Convert.ToInt32(n);
        }
        // Civil refuses the statistics of an empty surface ("The surface has no point or triangle").
        catch (TargetInvocationException) { return 0; }
    }

    // Must run inside EnTransaccion.
    private static bool Existe(object land)
    {
        try { return Gm.Llamar(land, "GetSurface", TopSurface) != null; }
        catch (InvalidOperationException) { return false; }
    }

    // Coordinate system of the active drawing, through the GM's own manager (the one its panel calls).
    private static object SistemaCoord(object cont, object docService, JsonObject p, bool confirm, ref bool changed)
    {
        var doc = App.DocumentManager.MdiActiveDocument ?? throw new InvalidOperationException("No hay dibujo activo");
        string codigo = Text(p, "codigo", false, 60);
        // Not registered in the GM container: built the way its presenter receives it, from the map services.
        var csm = Activator.CreateInstance(Gm.Tipo(Gm.Cad, Gm.Cad + ".CoordinateSystemManager"), Gm.Resolver(cont, Gm.Cad, Gm.Cad + ".MapServices"));
        string Actual() => EnTransaccion(docService, () => (string)Gm.Llamar(csm, "GetCurrentCoordinateSystem"));
        string antes = Actual();
        if (codigo == null) return new { dibujo = doc.Name, sistema_coord = antes };
        if (!confirm) return new { simulacion = true, dibujo = doc.Name, antes, despues = codigo };
        using (doc.LockDocument())
        {
            try { EnTransaccion(docService, () => { Gm.Llamar(csm, "SetCurrentCoordinateSystem", codigo); return 0; }); }
            catch (InvalidOperationException ex) { throw new InvalidOperationException("Civil no acepto el codigo de sistema de coordenadas '" + codigo + "': " + ex.Message); }
        }
        string despues = Actual();
        if (!string.Equals(despues, codigo, StringComparison.OrdinalIgnoreCase)) throw new InvalidOperationException("El dibujo quedo con el sistema '" + despues + "', no con '" + codigo + "'");
        changed = true;
        return new { simulacion = false, dibujo = doc.Name, antes, despues, guardado = false };
    }

    // The drawing's GM settings are only readable or writable inside a GM transaction on the active document,
    // exactly as its presenters do (AcadDocumentService.StartTransaction ... CommitTransaction).
    private static T EnTransaccion<T>(object docService, Func<T> trabajo)
    {
        var doc = App.DocumentManager.MdiActiveDocument ?? throw new InvalidOperationException("No hay dibujo activo");
        var tr = Gm.Llamar(docService, "StartTransaction", doc);
        try
        {
            T valor = trabajo();
            Gm.Llamar(tr, "CommitTransaction");
            return valor;
        }
        finally { (tr as IDisposable)?.Dispose(); }
    }

    private static Dictionary<string, object> Fila(object repo, object proyecto)
    {
        string id = (string)Gm.Prop(proyecto, "ProjectId");
        // A count that cannot be read is reported as null with its reason in 'avisos', never as a silent number.
        var avisos = new List<string>();
        int? Cuenta(string metodo)
        {
            try { return ((IList)Gm.Llamar(repo, metodo, id)).Count; }
            catch (Exception ex) { avisos.Add(metodo + ": " + ex.GetBaseException().Message); return null; }
        }
        return new Dictionary<string, object>
        {
            ["proyecto_id"] = id, ["nombre"] = Gm.Prop(proyecto, "ProjectName"), ["ubicacion"] = Gm.Prop(proyecto, "ProjectLocation"),
            ["sistema_coord"] = Gm.Prop(proyecto, "CSCode"), ["sondeos"] = Cuenta("GetBoreholes"), ["estratos"] = Cuenta("GetStrata"),
            ["avisos"] = avisos
        };
    }

    // Must run inside EnTransaccion. null means the drawing has no GM project.
    private static string Vinculado(object settingsRepo) =>
        (string)Gm.Prop(Gm.Llamar(settingsRepo, "GetApplicationSettings"), "ProjectId");

    private static object Listar(object repo, object settingsRepo, object docService)
    {
        var filas = ((IEnumerable)Gm.Llamar(repo, "GetProjects")).Cast<object>().Select(x => Fila(repo, x)).ToList();
        string vinculado = null, aviso = null;
        try { vinculado = EnTransaccion(docService, () => Vinculado(settingsRepo)); }
        catch (Exception ex) { aviso = "ajustes del dibujo no legibles: " + ex.GetBaseException().Message; }
        return new { proyectos = filas, proyecto_del_dibujo = vinculado, aviso, dibujo = App.DocumentManager.MdiActiveDocument?.Name, base_de_datos = BaseDeDatos() };
    }

    private static object Existente(object repo, string id) =>
        ((IEnumerable)Gm.Llamar(repo, "GetProjects")).Cast<object>().FirstOrDefault(x => string.Equals((string)Gm.Prop(x, "ProjectId"), id, StringComparison.OrdinalIgnoreCase));

    private static object Crear(object repo, JsonObject p, bool confirm, ref bool changed)
    {
        string id = Text(p, "proyecto_id", true, 100);
        if (!Regex.IsMatch(id, @"^[\w \-\.\(\)]+$")) throw new ArgumentException("proyecto_id admite letras, numeros, espacios, guion, punto y parentesis");
        string nombre = Text(p, "nombre", false, 200) ?? id, ubicacion = Text(p, "ubicacion", false, 200) ?? "", cs = Text(p, "sistema_coord", false, 60) ?? "";
        if (Existente(repo, id) != null) throw new InvalidOperationException("Ya existe un proyecto con ese identificador: " + id);
        if (!confirm) return new { simulacion = true, proyecto_id = id, nombre, ubicacion, sistema_coord = cs, existe = false };
        string respaldo = Respaldar();
        var nuevo = Gm.Llamar(repo, "InsertProject", id, nombre, ubicacion, cs);
        changed = true;
        return new { simulacion = false, respaldo, proyecto = Fila(repo, nuevo ?? Existente(repo, id)) };
    }

    private static object Importar(object repo, JsonObject p, bool confirm, ref bool changed)
    {
        string id = Text(p, "proyecto_id", true, 100);
        var proyecto = Existente(repo, id) ?? throw new InvalidOperationException("No existe el proyecto: " + id);
        string loc = Csv(p, "ubicaciones", true), lit = Csv(p, "litologia", true), ori = Csv(p, "orientacion", false);
        string delim = Text(p, "delimitador", false, 1) ?? ",";
        var tCfg = Gm.Tipo(Gm.Domain, Gm.Domain + ".CustomCSV.FieldMapConfiguration");
        var cfg = tCfg.GetMethod("CreateForGeotechnicalModelerCsv", BindingFlags.Public | BindingFlags.Static)
            .Invoke(null, new object[] { loc, lit, ori, delim });
        bool valido = (bool)Gm.Llamar(cfg, "IsValid");
        var antes = Fila(repo, proyecto);
        var lineas = new { ubicaciones = File.ReadAllLines(loc).Count(l => l.Trim().Length > 0) - 1, litologia = File.ReadAllLines(lit).Count(l => l.Trim().Length > 0) - 1 };
        if (!valido) throw new InvalidOperationException("El mapeo automatico de campos no es valido para esos CSV (cabeceras del formato Geotechnical Modeler)");
        if (!confirm) return new { simulacion = true, proyecto_id = id, mapeo_valido = true, filas_csv = lineas, antes };
        string respaldo = Respaldar();
        var importer = Activator.CreateInstance(Gm.Tipo(Gm.Persistence, Gm.Persistence + ".Importers.CustomCSVDataImporter"), repo);
        var tupla = Gm.Llamar(importer, "ImportBoreholesFromCustomCsvData", proyecto, cfg);
        changed = true;
        return new { simulacion = false, proyecto_id = id, respaldo, filas_csv = lineas, antes, despues = Fila(repo, Existente(repo, id)), informe = Informe(tupla) };
    }

    // The importer returns a ValueTuple whose items are the insert counts, a success flag and messages; report them as they come.
    private static List<object> Informe(object tupla)
    {
        var salida = new List<object>();
        foreach (var f in tupla.GetType().GetFields())
        {
            object v = f.GetValue(tupla);
            if (v == null || v is string || v.GetType().IsPrimitive) { salida.Add(v); continue; }
            if (v is IEnumerable lista) { salida.Add(lista.Cast<object>().Select(x => x?.ToString()).Take(50).ToList()); continue; }
            salida.Add(v.GetType().GetProperties().Where(q => q.GetIndexParameters().Length == 0 && (q.PropertyType.IsPrimitive || q.PropertyType == typeof(string)))
                .ToDictionary(q => q.Name, q => q.GetValue(v)));
        }
        return salida;
    }

    private static object Vincular(object repo, object settingsRepo, object docService, JsonObject p, bool confirm, ref bool changed)
    {
        string id = Text(p, "proyecto_id", true, 100);
        if (Existente(repo, id) == null) throw new InvalidOperationException("No existe el proyecto: " + id);
        var doc = App.DocumentManager.MdiActiveDocument ?? throw new InvalidOperationException("No hay dibujo activo");
        string antes = EnTransaccion(docService, () => Vinculado(settingsRepo));
        if (!confirm) return new { simulacion = true, dibujo = doc.Name, proyecto_antes = antes, proyecto_despues = id };
        string despues = EnTransaccion(docService, () => { Escribir(settingsRepo, doc, id); return Vinculado(settingsRepo); });
        if (!string.Equals(despues, id, StringComparison.Ordinal)) throw new InvalidOperationException("El dibujo quedo con el proyecto '" + despues + "', no con '" + id + "'");
        changed = true;
        return new { simulacion = false, dibujo = doc.Name, proyecto_antes = antes, proyecto_despues = despues, guardado = false };
    }

    private static void Escribir(object settingsRepo, object doc, string id)
    {
        var settings = Gm.Llamar(settingsRepo, "GetApplicationSettings")
            ?? Activator.CreateInstance(Gm.Tipo(Gm.Cad, Gm.Cad + ".ApplicationSettings.ApplicationSettings"));
        var prop = settings.GetType().GetProperty("ProjectId") ?? throw new MissingMemberException("ApplicationSettings.ProjectId");
        prop.SetValue(settings, id);
        var guardar = settingsRepo.GetType().GetMethods().First(m => m.Name == "SaveApplicationSettings");
        var ps = guardar.GetParameters();
        var args = new object[ps.Length];
        for (int i = 0; i < ps.Length; i++)
        {
            var t = ps[i].ParameterType;
            if (t.IsInstanceOfType(settings)) args[i] = settings;
            else if (t.IsInstanceOfType(doc)) args[i] = doc;
            else if (t.IsEnum) args[i] = TodosLosAjustes(t);
            else args[i] = t.IsValueType ? Activator.CreateInstance(t) : null;
        }
        try { guardar.Invoke(settingsRepo, args); }
        catch (TargetInvocationException ex) { throw new InvalidOperationException("SaveApplicationSettings: " + ex.GetBaseException().Message); }
    }

    // SettingsType is not a flags enum (ManageData, BuildSurfaces, ...): the project id belongs to the ManageData group.
    private static object TodosLosAjustes(Type t)
    {
        if (Enum.IsDefined(t, "ManageData")) return Enum.Parse(t, "ManageData");
        throw new MissingMemberException(t.Name, "ManageData");
    }

    private static string BaseDeDatos()
    {
        string config = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), "Autodesk", "C3D-GeoTechModeler-2027", "Application.config");
        if (!File.Exists(config)) return null;
        var m = Regex.Match(File.ReadAllText(config), @"Data Source\s*=\s*([^;""'<]+)", RegexOptions.IgnoreCase);
        return m.Success ? m.Groups[1].Value.Trim() : null;
    }

    // Every write to the GM database is preceded by a dated copy next to it; the copy is never deleted here.
    private static string Respaldar()
    {
        string db = BaseDeDatos();
        if (db == null || !File.Exists(db)) throw new InvalidOperationException("No se encontro la base de datos del Geotechnical Modeler para respaldarla");
        string copia = Path.Combine(Path.GetDirectoryName(db), Path.GetFileNameWithoutExtension(db) + "_respaldo_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + Path.GetExtension(db));
        File.Copy(db, copia, false);
        return copia;
    }
}
