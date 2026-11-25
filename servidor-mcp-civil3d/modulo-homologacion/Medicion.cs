using System.Text.Json;

namespace Cdcrd.Homologacion;

internal sealed record Medicion(string rol, string documento, string revision, string[] laminas,
    string elemento, double[] punto_m, string marco, string metodo)
{
    internal static Medicion Crear(string rol, string documento, string revision, string[] laminas,
        string elemento, double[] coordenadas, double metrosPorUnidad, string marco, string metodo)
    {
        if (rol is not ("llegada" or "control_civil" or "sumidero"))
            throw new ArgumentException("Rol de Civil desconocido.");
        if (new[] { documento, revision, elemento, marco, metodo }.Any(string.IsNullOrWhiteSpace))
            throw new ArgumentException("Faltan los datos de procedencia.");
        if (laminas.Length == 0 || laminas.Any(string.IsNullOrWhiteSpace))
            throw new ArgumentException("Indique una presentación identificable.");
        if (!double.IsFinite(metrosPorUnidad) || metrosPorUnidad <= 0 || coordenadas.Length != 3)
            throw new ArgumentException("Unidad o dimensión incorrecta.");
        var metros = coordenadas.Select(valor => valor * metrosPorUnidad).ToArray();
        if (metros.Any(valor => !double.IsFinite(valor)))
            throw new ArgumentException("La lectura contiene una coordenada no finita.");
        return new(rol, documento, revision, laminas, elemento, metros, marco, metodo);
    }

    internal void Exportar(string destino)
    {
        destino = Path.GetFullPath(destino);
        if (!string.Equals(Path.GetExtension(destino), ".json", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Elija un archivo .json.");
        var temporal = Path.Combine(Path.GetDirectoryName(destino)!, Path.GetRandomFileName());
        var archivo = new FileStream(temporal, FileMode.CreateNew, FileAccess.Write, FileShare.None);
        try
        {
            using (archivo)
                JsonSerializer.Serialize(archivo, this, new JsonSerializerOptions { WriteIndented = true });
            File.Move(temporal, destino, overwrite: false);
        }
        finally { File.Delete(temporal); }
    }
}
