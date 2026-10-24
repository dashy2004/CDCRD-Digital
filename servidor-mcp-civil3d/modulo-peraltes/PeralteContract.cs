using System;
using System.Linq;
using System.Text.Json.Nodes;

namespace Cdcrd.Peraltes;

internal static class PeralteContract
{
    internal static double[][] Parse(JsonNode node)
    {
        if (node is not JsonArray rows || rows.Count < 3 || rows.Count > 200)
            throw new ArgumentException("tabla requiere 3..200 filas [estacion, pendiente_izq, pendiente_der].");
        var result = rows.Select(row =>
        {
            if (row is not JsonArray a || a.Count != 3)
                throw new ArgumentException("Cada fila requiere tres numeros.");
            var r = a.Select(n => n?.GetValue<double>() ?? double.NaN).ToArray();
            if (r.Any(x => !double.IsFinite(x)) || Math.Abs(r[1]) > .12 || Math.Abs(r[2]) > .12)
                throw new ArgumentException("Pendientes finitas entre -0.12 y 0.12 m/m requeridas.");
            return r;
        }).ToArray();
        for (int i = 1; i < result.Length; i++)
            if (result[i][0] - result[i - 1][0] < .001)
                throw new ArgumentException("Estaciones estrictamente crecientes, separacion minima 0.001 m.");
        return result;
    }

    internal static void Extent(double[][] rows, double start, double end)
    {
        if (Math.Abs(rows[0][0] - start) > 1e-7 || Math.Abs(rows[^1][0] - end) > 1e-7)
            throw new ArgumentException("La tabla debe cubrir exactamente inicio y fin del alineamiento.");
    }

    internal static double At(double[][] rows, double station, int column)
    {
        if (station < rows[0][0] - 1e-7 || station > rows[^1][0] + 1e-7)
            throw new ArgumentOutOfRangeException(nameof(station));
        for (int i = 1; i < rows.Length; i++)
            if (station <= rows[i][0] + 1e-9)
                return rows[i - 1][column] + (rows[i][column] - rows[i - 1][column]) *
                    (station - rows[i - 1][0]) / (rows[i][0] - rows[i - 1][0]);
        return rows[^1][column];
    }
}
