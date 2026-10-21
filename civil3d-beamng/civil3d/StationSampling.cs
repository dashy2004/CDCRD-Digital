namespace Cdcrd.BeamngExport;

internal static class StationSampling
{
    // Preserve the actual endpoint while replacing a regular sample that only
    // differs by floating-point noise. This avoids zero-length final segments.
    internal const double EndpointToleranceMetres = 1e-8;

    internal static IEnumerable<double> CreateStations(double start, double end, double step)
    {
        if (!double.IsFinite(start) || !double.IsFinite(end) || !double.IsFinite(step) ||
            step <= EndpointToleranceMetres || end - start <= EndpointToleranceMetres)
            throw new ArgumentOutOfRangeException(nameof(end), "El intervalo y paso deben ser finitos, positivos y mayores que 1e-8 m.");

        var count = checked((long)Math.Ceiling((end - start) / step));
        for (long i = 0; i < count; i++)
        {
            var station = start + i * step;
            if (i > 0 && end - station <= EndpointToleranceMetres)
                break;
            yield return station;
        }
        yield return end;
    }
}
