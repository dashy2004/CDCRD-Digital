using System.Security.Cryptography;

namespace Cdcrd.Homologacion;

internal static class CotasLlegada
{
    // Resolución de cotejo numérico en metros, independiente de cualquier límite de diseño.
    private const double Resolucion = 1e-6;

    internal static void ExigirCercania(double real, double esperado, string campo)
    {
        if (!double.IsFinite(real) || !double.IsFinite(esperado) || Math.Abs(real - esperado) > Resolucion)
            throw new InvalidOperationException($"{campo}: se esperaba {esperado:R} m y se leyó {real:R} m.");
    }

    internal static void ExigirCambio(double anterior, double nueva)
    {
        if (!double.IsFinite(nueva) || !double.IsFinite(anterior) || Math.Abs(anterior - nueva) <= Resolucion)
            throw new InvalidOperationException("Indique una cota finita diferente de la anterior.");
    }

    internal static string Huella(string ruta)
    {
        using var fuente = File.Open(ruta, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
        return Convert.ToHexString(SHA256.HashData(fuente));
    }

    internal static string CopiarVersion(string original, string destino)
    {
        var temporal = Path.Combine(Path.GetDirectoryName(Path.GetFullPath(destino))!, Path.GetRandomFileName());
        using (var origen = File.Open(original, FileMode.Open, FileAccess.Read, FileShare.ReadWrite))
        {
            var salida = new FileStream(temporal, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            try
            {
                using (salida) origen.CopyTo(salida);
                var hash = Huella(temporal);
                if (!string.Equals(hash, Huella(original), StringComparison.Ordinal))
                    throw new IOException("El DWG de origen cambió durante la copia.");
                File.Move(temporal, destino, overwrite: false);
                return hash;
            }
            finally { File.Delete(temporal); }
        }
    }
}
