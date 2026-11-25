using Cdcrd.Homologacion;

static void Rechaza(Action accion)
{
    try { accion(); }
    catch (InvalidOperationException) { return; }
    throw new Exception("La precondición debió rechazar el dato.");
}

CotasLlegada.ExigirCercania(2.0000005, 2, "E");
Rechaza(() => CotasLlegada.ExigirCercania(2.0002, 2, "E"));
Rechaza(() => CotasLlegada.ExigirCercania(double.NaN, 2, "N"));
Rechaza(() => CotasLlegada.ExigirCercania(1, double.PositiveInfinity, "Z"));
Rechaza(() => CotasLlegada.ExigirCambio(2, 2.0000005));
Rechaza(() => CotasLlegada.ExigirCambio(0, double.NaN));
CotasLlegada.ExigirCambio(3, -1);

var carpeta = Directory.CreateTempSubdirectory();
try
{
    var fuente = Path.Combine(carpeta.FullName, "origen.dwg");
    var copia = Path.Combine(carpeta.FullName, "copia.dwg");
    File.WriteAllBytes(fuente, [1, 2, 3]);
    var hash = CotasLlegada.CopiarVersion(fuente, copia);
    if (CotasLlegada.Huella(copia) != hash || CotasLlegada.Huella(fuente) != hash)
        throw new Exception("La copia no coincide.");
    try { CotasLlegada.CopiarVersion(fuente, copia); throw new Exception("Sobrescritura."); }
    catch (IOException) { }
    File.WriteAllBytes(copia, [5]);
    if (CotasLlegada.Huella(copia) == hash || File.ReadAllBytes(fuente)[0] != 1)
        throw new Exception("La copia no es independiente.");
    if (Directory.GetFiles(carpeta.FullName).Length != 2) throw new Exception("Temporal residual.");
}
finally { carpeta.Delete(true); }
Console.WriteLine("OK: lectura previa, tolerancia numérica, cotas finitas, cambio real, copia independiente y destino exclusivo.");
