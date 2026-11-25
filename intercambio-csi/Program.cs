using System.Text.Json;
using CSiAPIv1;

internal static class Program
{
    private static readonly JsonSerializerOptions Json = new() { WriteIndented = true };

    [STAThread]
    private static int Main(string[] args)
    {
        try
        {
            if (args is ["--verificar-api"])
            {
                Emitir(new { ensamblado = typeof(cSapModel).Assembly.FullName,
                    proceso64 = Environment.Is64BitProcess, conexion_solicitada = false });
                return 0;
            }
            if (args.Length is < 3 or > 4 || !int.TryParse(args[0], out int pid) || pid <= 0 ||
                !Path.IsPathFullyQualified(args[2]))
            {
                Console.Error.WriteLine("Uso: LectorCsi <PID> <ProgID del producto> <modelo absoluto> [clave de tabla]");
                return 2;
            }
            string esperado = Path.GetFullPath(args[2]);
            cHelper helper = new Helper();
            cOAPI app = helper.GetObjectProcess(args[1], pid)
                ?? throw new InvalidOperationException("La versión instalada no permitió conectar al PID.");
            var modelo = app.SapModel;
            string ruta = modelo.GetModelFilename(true);
            if (string.IsNullOrWhiteSpace(ruta) ||
                !string.Equals(esperado, Path.GetFullPath(ruta), StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("El archivo activo del PID no coincide con el solicitado.");
            string version = "";
            double numeroVersion = 0;
            Comprobar(modelo.GetVersion(ref version, ref numeroVersion), "GetVersion");
            var unidades = modelo.GetPresentUnits().ToString();
            var tablas = modelo.DatabaseTables;
            object lectura = args.Length == 4 ? Leer(tablas, args[3]) : Catalogo(tablas);
            // Volver a leer identidad y unidades antes de atribuir los datos al modelo.
            if (!string.Equals(ruta, modelo.GetModelFilename(true), StringComparison.OrdinalIgnoreCase) ||
                unidades != modelo.GetPresentUnits().ToString())
                throw new InvalidOperationException("Cambió el modelo o el sistema de unidades durante la lectura.");
            Emitir(new { modelo = Path.GetFileName(ruta), pid, progId = args[1], version,
                unidades_activas = unidades, lectura });
            return 0;
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine(ex.Message);
            return 2;
        }
    }

    private static object Catalogo(cDatabaseTables db)
    {
        int count = 0;
        string[] keys = Array.Empty<string>(), names = Array.Empty<string>();
        int[] imports = Array.Empty<int>();
        Comprobar(db.GetAvailableTables(ref count, ref keys, ref names, ref imports), "GetAvailableTables");
        if (count < 0 || (keys?.Length ?? 0) != count || (names?.Length ?? 0) != count)
            throw new InvalidDataException("Catálogo CSI inconsistente.");
        return new { tablas = Enumerable.Range(0, count).Select(i => new { clave = keys![i], nombre = names![i] }).ToArray() };
    }

    private static object Leer(cDatabaseTables db, string key)
    {
        var seleccion = Filtros(db);
        int version = 0, count = 0;
        string[] solicitados = Array.Empty<string>(), campos = Array.Empty<string>(), datos = Array.Empty<string>();
        Comprobar(db.GetTableForDisplayArray(key, ref solicitados, "All", ref version,
            ref campos, ref count, ref datos), "GetTableForDisplayArray");
        if (count < 0 || campos == null || campos.Length == 0 ||
            (datos?.Length ?? 0) != checked(count * campos.Length))
            throw new InvalidDataException("Las dimensiones declaradas por CSI no coinciden con la tabla.");
        var posterior = Filtros(db);
        if (seleccion.Any(par => !par.Value.SequenceEqual(posterior[par.Key])))
            throw new InvalidOperationException("Cambió la selección de resultados durante la lectura.");
        return new { clave = key, version_tabla = version, campos,
            unidades_por_campo = Unidades(db, key, campos),
            filas = (datos ?? Array.Empty<string>()).Chunk(campos.Length), seleccion };
    }

    private delegate int ObtenerFiltro(ref int cantidad, ref string[] nombres);

    private static string[] Seleccion(ObtenerFiltro obtener, string nombre)
    {
        int cantidad = 0;
        string[] nombres = Array.Empty<string>();
        Comprobar(obtener(ref cantidad, ref nombres), nombre);
        if (cantidad < 0 || (nombres?.Length ?? 0) != cantidad)
            throw new InvalidDataException($"Selección CSI inconsistente: {nombre}.");
        return (nombres ?? Array.Empty<string>()).Order(StringComparer.Ordinal).ToArray();
    }

    private static Dictionary<string, string[]> Filtros(cDatabaseTables db) => new()
    {
        ["casos"] = Seleccion(db.GetLoadCasesSelectedForDisplay, "GetLoadCasesSelectedForDisplay"),
        ["combinaciones"] = Seleccion(db.GetLoadCombinationsSelectedForDisplay, "GetLoadCombinationsSelectedForDisplay"),
        ["patrones"] = Seleccion(db.GetLoadPatternsSelectedForDisplay, "GetLoadPatternsSelectedForDisplay")
    };

    private static Dictionary<string, string?> Unidades(cDatabaseTables db, string key, string[] campos)
    {
        int version = 0, cantidad = 0;
        string[] claves = [], nombres = [], descripciones = [], unidades = [];
        bool[] importables = [];
        Comprobar(db.GetAllFieldsInTable(key, ref version, ref cantidad, ref claves,
            ref nombres, ref descripciones, ref unidades, ref importables), "GetAllFieldsInTable");
        if (cantidad < 1 || claves?.Length != cantidad || unidades?.Length != cantidad)
            throw new InvalidDataException("CSI no devolvió metadatos completos de los campos.");
        var medidas = claves.Zip(unidades).ToDictionary(x => x.First, x => x.Second);
        return campos.ToDictionary(campo => campo, campo =>
            medidas.TryGetValue(campo, out var unidad) ? (string?)unidad
            : throw new InvalidDataException($"Campo sin metadatos: {campo}"));
    }

    private static void Comprobar(int codigo, string metodo)
    {
        if (codigo != 0)
            throw new InvalidOperationException($"{metodo} devolvió {codigo}.");
    }

    private static void Emitir(object valor) => Console.WriteLine(JsonSerializer.Serialize(valor, Json));
}
