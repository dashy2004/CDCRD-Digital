using System;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.Civil;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil.Runtime;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivilApp = Autodesk.Civil.ApplicationServices.CivilApplication;
using CivAssembly = Autodesk.Civil.DatabaseServices.Assembly;

namespace Cdcrd.Peraltes;

internal static class PeralteService
{
    // Optional QA harness can install a one-shot failure; never set by production.
    internal static Action<string> QaCheckpoint = null;
    private static string H(ObjectId id) => id.Handle.ToString();
    private static string Text(JsonObject p, string key) => p[key]?.GetValue<string>() ?? "";
    private static readonly SuperelevationCrossSegmentType[] Segments = {
        SuperelevationCrossSegmentType.LeftOutLaneCrossSlope, SuperelevationCrossSegmentType.RightOutLaneCrossSlope };

    internal static object Execute(JsonObject p, out bool committed)
    {
        committed = false;
        if (!DateTimeOffset.TryParse(Text(p, "vence_utc"), out var expires) || expires < DateTimeOffset.UtcNow || expires > DateTimeOffset.UtcNow.AddMinutes(5))
            throw new ArgumentException("Solicitud vencida o sin plazo valido; no ejecutar una escritura pendiente antigua.");
        var doc = App.DocumentManager.MdiActiveDocument ?? throw new InvalidOperationException("Sin documento.");
        if (p["pid"]?.GetValue<int>() != Environment.ProcessId || string.IsNullOrWhiteSpace(Text(p, "dibujo")) ||
            !Path.IsPathFullyQualified(Text(p, "dibujo")) || !string.Equals(Path.GetFullPath(doc.Name), Path.GetFullPath(Text(p, "dibujo")), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Documento o PID distinto al esperado.");
        var civil = CivilApp.ActiveDocument;
        if (Convert.ToInt32(App.GetSystemVariable("INSUNITS")) != 6 || civil.Settings.DrawingSettings.UnitZoneSettings.DrawingUnits.ToString() != "Meters")
            throw new ArgumentException("Se requieren unidades Civil y AutoCAD en metros.");
        string action = Text(p, "accion");
        if (action != "leer" && action != "aplicar") throw new ArgumentException("accion debe ser leer o aplicar.");
        bool apply = action == "aplicar", simulation = p["simular"]?.GetValue<bool>() ?? true;
        if (apply && (Environment.GetEnvironmentVariable("CDCRD_C3D_SOLO_LECTURA") == "1" ||
            Environment.GetEnvironmentVariable("CDCRD_C3D_PERMITIR_COMANDOS") != "1"))
            throw new InvalidOperationException("Escritura/comandos deshabilitados.");
        double[][] rows = apply ? PeralteContract.Parse(p["tabla"]) : null;
        using (doc.LockDocument())
        using (var tr = doc.Database.TransactionManager.StartTransaction())
        {
            var matches = civil.CorridorCollection.Select(id => (Corridor)tr.GetObject(id, OpenMode.ForRead))
                .Where(c => c.Name == Text(p, "corredor") || H(c.ObjectId).Equals(Text(p, "corredor"), StringComparison.OrdinalIgnoreCase)).ToArray();
            if (matches.Length != 1) throw new ArgumentException("Corredor inexistente o ambiguo.");
            var corridor = matches[0];
            if (corridor.IsReferenceObject || corridor.Baselines.Count != 1 || corridor.Baselines[0].BaselineRegions.Count != 1)
                throw new ArgumentException("Requiere corredor local con una baseline y una region.");
            var baseline = corridor.Baselines[0]; var region = baseline.BaselineRegions[0];
            var axis = (Alignment)tr.GetObject(baseline.AlignmentId, OpenMode.ForWrite);
            var assembly = (CivAssembly)tr.GetObject(region.AssemblyId, OpenMode.ForWrite);
            if (axis.IsReferenceObject || assembly.IsReferenceObject || axis.StationEquations.Count != 0)
                throw new ArgumentException("Eje/ensamblaje de referencia o ecuaciones no soportados.");
            var parts = assembly.Groups.Cast<AssemblyGroup>().SelectMany(g => g.GetSubassemblyIds().Cast<ObjectId>())
                .Select(id => (Subassembly)tr.GetObject(id, OpenMode.ForWrite)).ToArray();
            var lanes = parts.Where(s => s.ParamsLong.Cast<ParamLong>().Any(x => x.Key == "UseSuperelevation")).ToArray();
            if (lanes.Length != 2 || lanes.Select(s => s.Side).Distinct().Count() != 2 ||
                lanes.Any(s => !s.SubassemblyHookTo.IsNull || !s.ParamsDouble.Cast<ParamDouble>().Any(x => x.Key == "DefaultSlope")))
                throw new ArgumentException("Se requieren dos carriles LaneSuperelevationAOR raiz, uno por lado.");
            // This API never silently changes other corridors sharing the same axis/assembly.
            if (apply && civil.CorridorCollection.Where(id => id != corridor.ObjectId).Select(id => (Corridor)tr.GetObject(id, OpenMode.ForRead))
                .Any(c => c.Baselines.Any(b => b.AlignmentId == axis.ObjectId || b.BaselineRegions.Any(r => r.AssemblyId == assembly.ObjectId))))
                throw new ArgumentException("Eje o ensamblaje compartido con otro corredor; use copias independientes.");
            var stations = axis.SuperelevationCriticalStations;
            bool configured = stations.Count > 0;
            if (stations.Count == 2 && stations.All(s => s.StationType == SuperelevationCriticalStationType.BeginAlignment || s.StationType == SuperelevationCriticalStationType.EndAlignment))
            {
                // Civil retains lazy-initialized endpoints after Abort. GetSlope
                // reports 0 there although interpolation is still undefined.
                // A valid flat table must still be treated as existing data.
                configured = false;
                foreach (var segment in Segments)
                {
                    try { axis.GetCrossSlopeAtStation((axis.StartingStation + axis.EndingStation) / 2, segment, false); configured = true; }
                    catch (InvalidOperationException) { /* Native empty/unset segment. */ }
                }
            }
            if (apply)
            {
                PeralteContract.Extent(rows, axis.StartingStation, axis.EndingStation);
                if (Math.Abs(region.StartStation - axis.StartingStation) > 1e-7 || Math.Abs(region.EndStation - axis.EndingStation) > 1e-7)
                    throw new ArgumentException("La region debe cubrir todo el eje.");
                if (configured) throw new ArgumentException("Ya existen peraltes; no se reemplazan ni se fusionan implicitamente.");
                if (region.GetTargets().Cast<SubassemblyTargetInfo>().Any(t => t.TargetType.ToString() != "Surface" && t.TargetIds.Count != 0))
                    throw new ArgumentException("Targets de ancho/elevacion no soportados.");
                corridor.UpgradeOpen();
                // First interior Add initializes BeginAlignment/EndAlignment automatically.
                // Adding the first endpoint instead creates a duplicate Manual station.
                foreach (var row in rows.Skip(1).SkipLast(1))
                    stations.Add(row[0], SuperelevationCriticalStationType.Manual, SuperelevationAttainmentRegionType.AutoAttainmentRegionType);
                if (stations.Count != rows.Length) throw new InvalidOperationException("Numero inesperado de estaciones nativas.");
                foreach (var row in rows)
                {
                    var s = stations.GetCriticalStationAt(row[0], 1e-7);
                    for (int side = 0; side < 2; side++) { s.SetSlope(Segments[side], row[side + 1]); s.SetSmoothingLength(Segments[side], 0); }
                }
                QaCheckpoint?.Invoke("table-written");
                foreach (var lane in lanes)
                {
                    string enumName = lane.Side == SubassemblySideType.Left ? "LeftLO" : "RightLO";
                    var param = lane.ParamsLong["UseSuperelevation"]; bool found = false;
                    for (uint i = 0; i < param.EnumCount(); i++)
                    { string name = "", display = ""; int value = 0; param.GetEnumData(i, ref name, ref display, ref value);
                      if (name == enumName) { param.Value = value; found = true; break; } }
                    if (!found) throw new InvalidOperationException("Enum de peralte no encontrado: " + enumName);
                    lane.ParamsLong["SlopeDirection"].Value = 0;
                    lane.ParamsLong["SupportAOR"].Value = 1;
                }
                region.AppliedAssemblySetting.AppliedAtSuperelevationCriticalPoints = true;
                foreach (var row in rows)
                    if (!region.SortedStations().Any(s => Math.Abs(s - row[0]) < 1e-7)) region.AddStation(row[0], "Explicit superelevation station");
                corridor.Rebuild();
                QaCheckpoint?.Invoke("corridor-rebuilt");
                configured = true;
            }
            var table = stations.Select(s => new { station = s.Station, type = s.StationType.ToString(),
                left = s.GetSlope(Segments[0]), right = s.GetSlope(Segments[1]) }).ToArray();
            var validationRows = apply ? rows : table.Select(s => new[] { s.station, s.left, s.right }).ToArray();
            var samples = region.SortedStations().Select(station =>
            {
                var points = baseline.GetAppliedAssemblyAtStation(station).Points.Cast<CalculatedPoint>().ToArray();
                var slopes = !configured ? null : Segments.Select(t => axis.GetCrossSlopeAtStation(station, t, false)).ToArray();
                double error = 0;
                if (configured)
                {
                    for (int side = 0; side < 2; side++)
                    {
                        var lane = lanes.Single(l => l.Side == (side == 0 ? SubassemblySideType.Left : SubassemblySideType.Right));
                        double width = lane.ParamsDouble["Width"].Value, sign = side == 0 ? -1 : 1;
                        var crown = points.Where(pt => pt.CorridorCodes.Cast<string>().Contains("Crown") && Math.Abs(pt.StationOffsetElevationToBaseline.Y) < 1e-6).ToArray();
                        var edge = points.Where(pt => pt.CorridorCodes.Cast<string>().Contains("ETW") && Math.Abs(pt.StationOffsetElevationToBaseline.Y - sign * width) < 1e-6).ToArray();
                        if (crown.Length == 0 || edge.Length != 1) throw new InvalidOperationException("Crown/ETW inesperados.");
                        double expected = PeralteContract.At(validationRows, station, side + 1);
                        error = Math.Max(error, Math.Abs(slopes[side] - expected));
                        error = Math.Max(error, Math.Abs((edge[0].XYZ.Z - crown[0].XYZ.Z) / width - expected));
                    }
                    if (apply && error > 1e-6) throw new InvalidOperationException("La geometria no coincide con la tabla en " + station + "; error " + error);
                }
                return new { station, slopes, error, points = points.Select(pt => new {
                    xyz = new[] { pt.XYZ.X, pt.XYZ.Y, pt.XYZ.Z },
                    soe = new[] { pt.StationOffsetElevationToBaseline.X, pt.StationOffsetElevationToBaseline.Y, pt.StationOffsetElevationToBaseline.Z },
                    codes = pt.CorridorCodes.Cast<string>().ToArray() }).ToArray() };
            }).ToArray();
            if (apply && corridor.IsOutOfDate) throw new InvalidOperationException("Corredor pendiente de reconstruccion.");
            var result = new { corridor = H(corridor.ObjectId), alignment = H(axis.ObjectId), assembly = H(assembly.ObjectId),
                table, configured, samples, lanes = lanes.Select(s => new { handle = H(s.ObjectId), side = s.Side.ToString(), use = s.ParamsLong["UseSuperelevation"].Value }).ToArray(),
                critical_frequency = region.AppliedAssemblySetting.AppliedAtSuperelevationCriticalPoints,
                out_of_date = corridor.IsOutOfDate, simulation = apply && simulation, units = "m; slopes m/m outward from crown", berms = "unchanged parameters" };
            if (apply && !simulation) { tr.Commit(); committed = true; } else tr.Abort();
            return result;
        }
    }
}
