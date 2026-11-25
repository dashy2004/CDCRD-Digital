using Cdcrd.Homologacion;
using System.Text.Json;

static void Exige(bool ok, string caso)
{
    if (!ok) throw new Exception(caso);
}
static void Rechaza(Action accion)
{
    try { accion(); }
    catch (ArgumentException) { return; }
    throw new Exception("Se esperaba rechazo.");
}

var dir = Directory.CreateTempSubdirectory("homologacion-prueba-");
try
{
    foreach (var rol in new[] { "llegada", "sumidero", "control_civil" })
    {
        var fuente = Medicion.Crear(rol, "sintético.dwg", "R1", new[] { "C01", "C02" },
            "3AC", [1000, 2000, 5], 0.3048, "LOCAL / BM1", "Prueba");
        var archivo = Path.Combine(dir.FullName, rol + ".json");
        fuente.Exportar(archivo);
        using var doc = JsonDocument.Parse(File.ReadAllBytes(archivo));
        var raiz = doc.RootElement;
        Exige(raiz.EnumerateObject().Select(p => p.Name).ToHashSet().SetEquals(
            ["rol","documento","revision","laminas","elemento","punto_m","marco","metodo"]), "claves");
        Exige(raiz.GetProperty("punto_m")[2].GetDouble() == 5 * 0.3048, "cota en m");
        Exige(raiz.GetProperty("rol").GetString() == rol, "rol exportado");
        Exige(raiz.GetProperty("documento").GetString() == "sintético.dwg", "archivo origen");
        try { fuente.Exportar(archivo); throw new Exception("se sobrescribió"); }
        catch (IOException) { }
    }
    foreach (var z in new[] { double.NaN, double.PositiveInfinity })
        Rechaza(() => Medicion.Crear("llegada", "a.dwg", "R1", ["A"], "E0", [0, 1, z], 1, "m", "test"));
    Rechaza(() => Medicion.Crear("umbral", "a.dwg", "R1", ["A"], "E0", [0, 1, 2], 1, "m", "test"));
    Rechaza(() => Medicion.Crear("sumidero", "a.dwg", "R1", [], "E0", [0, 1, 2], 1, "m", "test"));
    Rechaza(() => Medicion.Crear("sumidero", "a.dwg", "R1", ["A"], "E0", [0, 1, 2], 1, " ", "test"));
    Exige(Directory.GetFiles(dir.FullName).Length == 3, "archivos temporales pendientes");
    Console.WriteLine("OK: tres roles, contrato, conversión, entradas inválidas y exportación sin sobrescritura.");
}
finally { dir.Delete(recursive: true); }
