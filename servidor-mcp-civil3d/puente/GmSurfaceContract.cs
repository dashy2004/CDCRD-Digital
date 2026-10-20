using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace Cdcrd.Civil3dBridge
{
    internal static class GmSurfaceContract
    {
        internal static void RequireLocations(IList<(string Id, double X, double Y)> points)
        {
            if (points.Count < 3 || points.Any(p => string.IsNullOrWhiteSpace(p.Id) ||
                !double.IsFinite(p.X) || !double.IsFinite(p.Y)) ||
                points.Select(p => p.Id).Distinct(StringComparer.OrdinalIgnoreCase).Count() != points.Count ||
                points.Select(p => (p.X, p.Y)).Distinct().Count() != points.Count)
                throw new ArgumentException("Se requieren al menos tres sondeos distintos, con ID y XY finitos y unicos.");
            var a = points[0];
            var b = points.OrderByDescending(p => Math.Pow(p.X-a.X,2)+Math.Pow(p.Y-a.Y,2)).First();
            double dx=b.X-a.X, dy=b.Y-a.Y, scale=dx*dx+dy*dy;
            if (!points.Any(p => Math.Abs(dx*(p.Y-a.Y)-dy*(p.X-a.X)) > 1e-10*scale))
                throw new ArgumentException("Los sondeos son colineales; no forman una superficie TIN.");
        }

        internal static string[] SurfaceNames(IEnumerable<string> graphNames)
        {
            var names = graphNames.ToArray();
            if (names.Length == 0 || names.Any(n => string.IsNullOrWhiteSpace(n) || n.Length > 180 ||
                n.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 || n.Contains('/') || n.Contains('\\')) ||
                names.Distinct(StringComparer.OrdinalIgnoreCase).Count() != names.Length)
                throw new ArgumentException("El grafo GM no contiene nombres de estrato unicos y utilizables.");
            return names.Select(n => "GM - Stratum - " + n).ToArray();
        }

        internal const string BottomName = "GM - Stratum - Borehole Bottom";

        internal static double BottomElevation(double elevation, double depth)
        {
            if (!double.IsFinite(elevation) || !double.IsFinite(depth) || depth <= 0 ||
                !double.IsFinite(elevation-depth))
                throw new ArgumentException("Fondo requiere cota finita y profundidad total positiva en cada sondeo.");
            return elevation-depth;
        }

        internal static bool Complete(IEnumerable<string> expected, IEnumerable<string> actual)
        {
            var e=expected.ToArray(); var a=actual.ToArray();
            return e.Length > 0 && a.Length == e.Length &&
                a.Distinct(StringComparer.OrdinalIgnoreCase).Count() == e.Length &&
                new HashSet<string>(e,StringComparer.OrdinalIgnoreCase).SetEquals(a);
        }

        internal static void RequireBottom(bool requested, IEnumerable<string> names)
        {
            if (requested && !names.Contains("GM - Stratum - Borehole Bottom", StringComparer.OrdinalIgnoreCase))
                throw new InvalidOperationException("GM no genero la superficie de fondo solicitada; se revierte la operacion. Para crear solo los estratos, use superficie_fondo=false.");
        }
    }
}
