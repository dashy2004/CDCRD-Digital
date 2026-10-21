using System;
using System.Collections.Generic;
using System.Linq;

namespace Cdcrd.Civil3dBridge
{
    internal readonly record struct VerticalCurveSpec(int Pvi, double Length);

    internal static class VerticalCurveContract
    {
        internal static VerticalCurveSpec[] Validate(
            IReadOnlyList<(double Station, double Elevation)> pvis,
            IEnumerable<VerticalCurveSpec> curves)
        {
            var result = curves.OrderBy(c => c.Pvi).ToArray();
            var seen = new HashSet<int>();
            double previousEnd = double.NegativeInfinity;
            foreach (var curve in result)
            {
                if (curve.Pvi <= 0 || curve.Pvi >= pvis.Count - 1 || !seen.Add(curve.Pvi))
                    throw new ArgumentException("Curva: indice PVI interior requerido, sin duplicados (base cero).");
                SiteDesignContract.Finite(curve.Length, "longitud de curva");
                if (curve.Length <= 1e-6)
                    throw new ArgumentException("Curva: longitud debe ser mayor que 0.000001 m.");
                var p = pvis[curve.Pvi];
                double start = p.Station - curve.Length / 2, end = p.Station + curve.Length / 2;
                if (start <= pvis[curve.Pvi - 1].Station + 1e-6 ||
                    end >= pvis[curve.Pvi + 1].Station - 1e-6 || start <= previousEnd + 1e-6)
                    throw new ArgumentException("Curvas solapadas, en contacto o fuera de sus tangentes. Debe quedar tangente positiva.");
                double g1 = Grade(pvis[curve.Pvi - 1], p), g2 = Grade(p, pvis[curve.Pvi + 1]);
                if (!double.IsFinite(g1) || !double.IsFinite(g2) || Math.Abs(g2 - g1) <= 1e-10)
                    throw new ArgumentException("Curva sin cambio de pendiente finito suficiente.");
                previousEnd = end;
            }
            return result;
        }

        static double Grade((double Station, double Elevation) a, (double Station, double Elevation) b)
            => (b.Elevation - a.Elevation) / (b.Station - a.Station);

        // Independent equation used to check the native profile, never to draw a substitute.
        internal static double Elevation(IReadOnlyList<(double Station, double Elevation)> pvis,
            IReadOnlyList<VerticalCurveSpec> curves, double station)
        {
            foreach (var curve in curves)
            {
                var p = pvis[curve.Pvi];
                double start = p.Station - curve.Length / 2;
                if (station < start || station > start + curve.Length) continue;
                double g1 = Grade(pvis[curve.Pvi - 1], p), g2 = Grade(p, pvis[curve.Pvi + 1]);
                double x = station - start;
                return p.Elevation - g1 * curve.Length / 2 + g1 * x + (g2 - g1) * x * x / (2 * curve.Length);
            }
            for (int i = 1; i < pvis.Count; i++)
                if (station <= pvis[i].Station)
                    return pvis[i - 1].Elevation + Grade(pvis[i - 1], pvis[i]) * (station - pvis[i - 1].Station);
            throw new ArgumentOutOfRangeException(nameof(station));
        }
    }
}
