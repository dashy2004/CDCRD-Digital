using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.DatabaseServices;
using DBObject = Autodesk.AutoCAD.DatabaseServices.DBObject;

namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        // Optional native QA harness can arm a one-shot exception. No RPC parameter
        // exposes this field; normal operation leaves it null.
        private static Action<string> CurveQaCheckpoint = null;

        private static void ValidateAlignmentPolyline(Polyline pl)
        {
            if (pl.NumberOfVertices < 2 || pl.NumberOfVertices > 200)
                throw new ArgumentException("Eje: requiere 2-200 vertices.");
            for (int i = 0; i < pl.NumberOfVertices; i++)
            {
                var point = pl.GetPoint2dAt(i);
                SiteDesignContract.Finite(point.X, "X"); SiteDesignContract.Finite(point.Y, "Y");
                double bulge = pl.GetBulgeAt(i);
                SiteDesignContract.Finite(bulge, "bulge");
                if (Math.Abs(bulge) > 1 || (i == pl.NumberOfVertices - 1 && bulge != 0))
                    throw new ArgumentException("Eje: arcos de hasta 180 grados y bulge final cero requeridos.");
                for (int j = 0; j < i; j++)
                    if (point.GetDistanceTo(pl.GetPoint2dAt(j)) <= 1e-6)
                        throw new ArgumentException("Eje: vertices repetidos o segmento nulo.");
            }
            var exploded = new DBObjectCollection();
            try
            {
                pl.Explode(exploded);
                var segments = exploded.Cast<DBObject>().OfType<Curve>().ToArray();
                if (segments.Length != pl.NumberOfVertices - 1 || segments.Any(c => c is not Line && c is not Arc))
                    throw new ArgumentException("Solo lineas y arcos circulares en el eje.");
                const double tol = 1e-6;
                for (int i = 0; i < segments.Length; i++)
                {
                    var a = segments[i];
                    if (a.GetDistanceAtParameter(a.EndParam) <= tol)
                        throw new ArgumentException("Eje: segmento demasiado corto.");
                    for (int j = i + 1; j < segments.Length; j++)
                    {
                        var b = segments[j]; bool adjacent = j == i + 1;
                        var shared = pl.GetPoint3dAt(j);
                        bool Forbidden(Point3d p) => !adjacent || p.DistanceTo(shared) > tol;
                        var hits = new Point3dCollection();
                        a.IntersectWith(b, Intersect.OnBothOperands, hits, IntPtr.Zero, IntPtr.Zero);
                        if (hits.Cast<Point3d>().Any(Forbidden))
                            throw new ArgumentException("Eje autointersectado o con segmentos en contacto.");
                        // IntersectWith need not return discrete points for coincident
                        // lines/circles. Test endpoints and interiors for overlaps too.
                        foreach (var pair in new[] { (a, b), (b, a) })
                            foreach (double fraction in new[] { 0d, .5, 1d })
                            {
                                double length = pair.Item1.GetDistanceAtParameter(pair.Item1.EndParam);
                                var point = pair.Item1.GetPointAtDist(length * fraction);
                                if (Forbidden(point) && point.DistanceTo(pair.Item2.GetClosestPointTo(point, false)) <= tol)
                                    throw new ArgumentException("Eje con segmentos superpuestos o en contacto.");
                            }
                    }
                }
            }
            finally { foreach (DBObject obj in exploded) obj.Dispose(); }
        }

        private static object VerifyAlignmentCurves(Alignment alignment, Polyline source)
        {
            double maxError = 0;
            // Endpoints and quarter points of every native source segment verify
            // orientation, station origin, circular shape and preservation of bulges.
            for (int i = 0; i < source.NumberOfVertices - 1; i++)
            {
                double start = source.GetDistanceAtParameter(i), end = source.GetDistanceAtParameter(i + 1);
                foreach (double fraction in new[] { 0d, .25, .5, .75, 1d })
                {
                    double distance = start + (end - start) * fraction;
                    var expected = source.GetPointAtDist(distance);
                    double e = 0, n = 0;
                    alignment.PointLocation(alignment.StartingStation + distance, 0, ref e, ref n);
                    maxError = Math.Max(maxError, new Point2d(expected.X, expected.Y).GetDistanceTo(new Point2d(e, n)));
                }
            }
            if (maxError > 1e-5) throw new InvalidOperationException("Geometria nativa del eje no coincide con la fuente.");
            var arcs = alignment.Entities.Cast<AlignmentEntity>().OfType<AlignmentArc>().ToArray();
            if (arcs.Length != Enumerable.Range(0, source.NumberOfVertices - 1).Count(i => source.GetBulgeAt(i) != 0))
                throw new InvalidOperationException("Numero de arcos nativos distinto de la fuente.");
            return new { max_error_xy_m = maxError, arcos = arcs.Select(a => new {
                radio_m = a.Radius, longitud_m = a.Length, inicio = a.StartStation, fin = a.EndStation,
                horario = a.Clockwise }).ToArray() };
        }

        private static VerticalCurveSpec[] ReadVerticalCurves(JsonObject p,
            IReadOnlyList<(double Station, double Elevation)> pvis)
        {
            if (p["curvas"] == null) return Array.Empty<VerticalCurveSpec>();
            if (p["curvas"] is not JsonArray array || array.Count > pvis.Count - 2)
                throw new ArgumentException("curvas debe ser una lista de PVI interiores y longitudes.");
            var values = array.Select(row => {
                if (row is not JsonObject o || o.Count != 2 || o["pvi"] == null || o["longitud"] == null)
                    throw new ArgumentException("Cada curva requiere {pvi: indice base cero, longitud: metros}.");
                return new VerticalCurveSpec(o["pvi"].GetValue<int>(), o["longitud"].GetValue<double>());
            });
            return VerticalCurveContract.Validate(pvis, values);
        }

        private static object VerifyVerticalCurves(Profile profile,
            IReadOnlyList<(double Station, double Elevation)> pvis, VerticalCurveSpec[] curves)
        {
            var actual = profile.Entities.Cast<ProfileEntity>().OfType<ProfileParabolaSymmetric>().OrderBy(c => c.PVIStation).ToArray();
            if (actual.Length != curves.Length) throw new InvalidOperationException("Numero de parabolas nativas incorrecto.");
            for (int i = 0; i < curves.Length; i++)
                if (Math.Abs(actual[i].Length - curves[i].Length) > 1e-6 ||
                    Math.Abs(actual[i].PVIStation - pvis[curves[i].Pvi].Station) > 1e-6)
                    throw new InvalidOperationException("Longitud o PVI nativo de curva distinto de lo solicitado.");
            var stations = new SortedSet<double>(pvis.Select(v => v.Station));
            for (int i = 1; i < pvis.Count; i++) stations.Add((pvis[i - 1].Station + pvis[i].Station) / 2);
            foreach (var c in curves)
                foreach (double fraction in new[] { -.5, -.25, 0, .25, .5 })
                    stations.Add(pvis[c.Pvi].Station + c.Length * fraction);
            var samples = stations.Select(s => new { estacion = s, elevacion = profile.ElevationAt(s),
                esperada = VerticalCurveContract.Elevation(pvis, curves, s) }).ToArray();
            double maxError = samples.Max(s => Math.Abs(s.elevacion - s.esperada));
            if (maxError > 1e-6) throw new InvalidOperationException("Rasante nativa distinta de ecuacion parabolica independiente.");
            return new { max_error_z_m = maxError, muestras = samples, curvas = actual.Select(c => new {
                tipo = c.CurveType.ToString(), longitud_m = c.Length, pvi_estacion = c.PVIStation,
                pvi_elevacion = c.PVIElevation, inicio = c.StartStation, fin = c.EndStation,
                pendiente_entrada = c.GradeIn, pendiente_salida = c.GradeOut }).ToArray() };
        }
    }
}
