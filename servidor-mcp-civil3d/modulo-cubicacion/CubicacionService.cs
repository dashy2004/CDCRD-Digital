// Pavement thicknesses on corridor lanes, Datum corridor surface and volumes.
// All writes happen inside one transaction of the active document; simulation aborts it.
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil;
using Autodesk.Civil.ApplicationServices;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil.Runtime;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivilApp = Autodesk.Civil.ApplicationServices.CivilApplication;
using CivAssembly = Autodesk.Civil.DatabaseServices.Assembly;
using CivEntity = Autodesk.Civil.DatabaseServices.Entity;
using CivSurface = Autodesk.Civil.DatabaseServices.Surface;
using CivPoint = Autodesk.Civil.DatabaseServices.Point;
using CivShape = Autodesk.Civil.DatabaseServices.Shape;
using CivLink = Autodesk.Civil.DatabaseServices.Link;

namespace Cdcrd.Cubicacion;

internal static class CubicacionService
{
    internal static Action<string> QaCheckpoint = null;
    internal const string RecordName = "CDCRD_CUBICACION_V1";
    private const int StationBudget = 20000;

    // ---------- helpers ----------
    private static string H(ObjectId id) => id.IsNull ? null : id.Handle.ToString();
    private static string Text(JsonObject p, string k) => CubicacionContract.Text(p, k);
    private static Subassembly[] PartsOf(CivAssembly a, Transaction tr) => a.Groups.Cast<AssemblyGroup>()
        .SelectMany(g => g.GetSubassemblyIds().Cast<ObjectId>()).Select(x => (Subassembly)tr.GetObject(x, OpenMode.ForRead)).ToArray();
    private static bool HasDouble(Subassembly s, string key) => s.ParamsDouble.Cast<ParamDouble>().Any(x => x.Key == key);
    private static bool IsLane(Subassembly s) => HasDouble(s, "Width") && HasDouble(s, "DefaultSlope") && HasDouble(s, "Pave1Depth");
    private static ObjectId Resolve(Transaction tr, IEnumerable<ObjectId> ids, string key, string what)
    {
        var found = ids.Where(id => string.Equals(H(id), key, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(((CivEntity)tr.GetObject(id, OpenMode.ForRead)).Name, key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (found.Length != 1) throw new ArgumentException(what + " inexistente o ambiguo: " + key);
        return found[0];
    }
    private static void Local(CivEntity e) { if (e.IsReferenceObject || e.IsCWSReferenceObject) throw new ArgumentException("Se requiere objeto local: " + e.Name); }
    private static ObjectId FromHandle(Database db, string handle) => db.GetObjectId(false, new Handle(Convert.ToInt64(handle, 16)), 0);
    private static TinSurface Tin(Transaction tr, ObjectId id, string what)
    {
        var s = tr.GetObject(id, OpenMode.ForRead) as TinSurface ?? throw new ArgumentException(what + " debe ser una superficie TIN");
        Local(s);
        if (s.IsOutOfDate) throw new ArgumentException(what + " fuera de fecha: " + s.Name);
        if (s.GetTinProperties().NumberOfTriangles == 0) throw new ArgumentException(what + " sin triangulos: " + s.Name);
        return s;
    }
    private static bool SurfaceNameExists(Transaction tr, CivilDocument civil, string name) =>
        civil.GetSurfaceIds().Cast<ObjectId>().Any(id => ((CivSurface)tr.GetObject(id, OpenMode.ForRead)).Name.Equals(name, StringComparison.OrdinalIgnoreCase));

    private static IEnumerable<(Baseline Baseline, BaselineRegion Region)> Regions(Corridor c) =>
        c.Baselines.Cast<Baseline>().SelectMany(b => b.BaselineRegions.Cast<BaselineRegion>().Select(r => (b, r)));

    // Stations of a region, without the boundary station already counted in the previous region of the same baseline.
    private static double[] OwnStations(Baseline b, BaselineRegion r)
    {
        var previous = b.BaselineRegions.Cast<BaselineRegion>().Where(o => o.Name != r.Name && Math.Abs(o.EndStation - r.StartStation) < 1e-6).ToArray();
        return r.SortedStations().Where(st => previous.Length == 0 || Math.Abs(st - r.StartStation) > 1e-6).ToArray();
    }

    private static Dictionary<string, double> Values(Subassembly s, IEnumerable<string> keys)
    {
        var doubles = s.ParamsDouble.Cast<ParamDouble>().ToDictionary(x => x.Key, x => x.Value);
        return keys.Where(doubles.ContainsKey).ToDictionary(k => k, k => doubles[k]);
    }
    private static object Describe(Subassembly s, IEnumerable<string> keys) => new
    { handle = H(s.ObjectId), nombre = s.Name, lado = s.Side.ToString(), ancho = HasDouble(s, "Width") ? s.ParamsDouble["Width"].Value : (double?)null, espesores = Values(s, keys) };

    private static JsonObject Record(Corridor c, Transaction tr)
    {
        if (c.ExtensionDictionary.IsNull) return null;
        var d = (DBDictionary)tr.GetObject(c.ExtensionDictionary, OpenMode.ForRead);
        if (!d.Contains(RecordName)) return null;
        var x = (Xrecord)tr.GetObject(d.GetAt(RecordName), OpenMode.ForRead);
        return JsonNode.Parse(string.Concat(x.Data.AsArray().Select(v => (string)v.Value))) as JsonObject ?? throw new ArgumentException("Contrato invalido");
    }
    // The record holds one entry per action (espesores, datum, cubicacion); a new run of an action replaces its entry.
    private static void Store(Corridor c, Transaction tr, string entry, JsonObject data)
    {
        var record = Record(c, tr) ?? new JsonObject { ["version"] = 1 };
        data["fecha_utc"] = DateTimeOffset.UtcNow.ToString("O");
        record[entry] = data;
        if (c.ExtensionDictionary.IsNull) c.CreateExtensionDictionary();
        var dict = (DBDictionary)tr.GetObject(c.ExtensionDictionary, OpenMode.ForWrite);
        string json = record.ToJsonString();
        using var buffer = new ResultBuffer(Enumerable.Range(0, (json.Length + 239) / 240)
            .Select(i => new TypedValue((int)DxfCode.Text, json.Substring(i * 240, Math.Min(240, json.Length - i * 240)))).ToArray());
        if (dict.Contains(RecordName)) ((Xrecord)tr.GetObject(dict.GetAt(RecordName), OpenMode.ForWrite)).Data = buffer;
        else { var x = new Xrecord { Data = buffer }; dict.SetAt(RecordName, x); tr.AddNewlyCreatedDBObject(x, true); }
    }

    private static object Surfaces(Corridor c, Transaction tr) => c.CorridorSurfaces.Cast<CorridorSurface>().Select(s =>
    {
        var tin = (TinSurface)tr.GetObject(s.SurfaceId, OpenMode.ForRead);
        return new { nombre = s.Name, handle = H(s.SurfaceId), enlaces = s.LinkCodes(), contornos = s.Boundaries.BoundaryNames(),
            triangulos = tin.GetTinProperties().NumberOfTriangles, fuera_de_fecha = tin.IsOutOfDate };
    }).ToArray();

    private static void RebuildAll(Corridor c, Transaction tr)
    {
        c.Rebuild(); QaCheckpoint?.Invoke("corridor-rebuilt");
        // Corridor surfaces do not follow the corridor rebuild inside the transaction: rebuild each one explicitly.
        foreach (CorridorSurface s in c.CorridorSurfaces) ((TinSurface)tr.GetObject(s.SurfaceId, OpenMode.ForWrite)).Rebuild();
        QaCheckpoint?.Invoke("surfaces-rebuilt");
    }

    // ---------- entry ----------
    internal static object Execute(JsonObject p, out bool committed)
    {
        committed = false;
        var doc = App.DocumentManager.MdiActiveDocument ?? throw new InvalidOperationException("Sin documento");
        if (!DateTimeOffset.TryParse(Text(p, "vence_utc"), CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var expires)
            || expires < DateTimeOffset.UtcNow || expires > DateTimeOffset.UtcNow.AddMinutes(5))
            throw new ArgumentException("Solicitud vencida o plazo invalido");
        if (p["pid"]?.GetValue<int>() != Environment.ProcessId || !System.IO.Path.IsPathFullyQualified(Text(p, "dibujo")) ||
            !string.Equals(System.IO.Path.GetFullPath(doc.Name), System.IO.Path.GetFullPath(Text(p, "dibujo")), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Documento o PID distinto al esperado");
        if (Convert.ToInt32(App.GetSystemVariable("INSUNITS")) != 6 || CivilApp.ActiveDocument.Settings.DrawingSettings.UnitZoneSettings.DrawingUnits.ToString() != "Meters")
            throw new ArgumentException("Se requieren unidades Civil y AutoCAD en metros");
        string action = Text(p, "accion");
        if (!new[] { "espesores", "datum", "cubicacion", "reconstruir", "leer" }.Contains(action)) throw new ArgumentException("Accion desconocida");
        bool write = action != "leer", sim = write && action != "reconstruir" && (p["simular"]?.GetValue<bool>() ?? true);
        if (write && (Environment.GetEnvironmentVariable("CDCRD_C3D_SOLO_LECTURA") == "1" || Environment.GetEnvironmentVariable("CDCRD_C3D_PERMITIR_COMANDOS") != "1"))
            throw new InvalidOperationException("Escritura/comandos deshabilitados");
        using (doc.LockDocument())
        {
            ObjectId cid; object result;
            using (var tr = doc.Database.TransactionManager.StartTransaction())
            {
                var civil = CivilApp.ActiveDocument;
                cid = Resolve(tr, civil.CorridorCollection, Text(p, "corredor"), "corredor");
                var c = (Corridor)tr.GetObject(cid, write ? OpenMode.ForWrite : OpenMode.ForRead);
                Local(c);
                result = action switch
                {
                    "espesores" => Thickness(c, tr, civil, CubicacionContract.ParseThicknessOptions(p), sim),
                    "datum" => Datum(c, tr, civil, CubicacionContract.ParseDatum(p), sim),
                    "cubicacion" => Volumes(c, tr, civil, CubicacionContract.ParseVolume(p), sim),
                    "reconstruir" => Settle(c, tr),
                    _ => Read(c, tr)
                };
                if (write && !sim) { tr.Commit(); committed = true; } else tr.Abort();
            }
            if (!committed || (action != "espesores" && action != "datum")) return result;
            // Inside the writing transaction the rebuilt corridor still applies the previous subassembly
            // parameters, so the geometric check of a committed change runs in a second transaction.
            // (Civil flags the corridor out of date again when the command ends: the wrapper's
            // `reconstruir` request settles that in a command of its own.)
            try
            {
                using var settle = doc.Database.TransactionManager.StartTransaction();
                var c2 = (Corridor)settle.GetObject(cid, OpenMode.ForWrite);
                RebuildAll(c2, settle);
                var after = action == "espesores" ? VerifyStoredThickness(c2, settle) : VerifyStoredDatum(c2, settle);
                settle.Commit();
                return new { aplicado = result, verificacion_tras_confirmar = after };
            }
            catch (Exception ex)
            {
                // The first transaction is already committed: keep what was applied in the receipt's error text.
                throw new InvalidOperationException("Aplicado y confirmado, pero la reconstruccion o verificacion posterior fallo: " + ex.GetBaseException().Message
                    + " | aplicado=" + JsonSerializer.Serialize(result), ex);
            }
        }
    }

    private static object VerifyStoredThickness(Corridor c, Transaction tr)
    {
        var stored = Record(c, tr)?["espesores"] as JsonObject ?? throw new InvalidOperationException("Contrato de espesores ausente");
        var lanes = stored["carriles"].AsArray().Select(n => FromHandle(c.Database, n.GetValue<string>())).ToHashSet();
        var thickness = ((JsonObject)stored["espesores"]).ToDictionary(kv => kv.Key, kv => kv.Value.GetValue<double>());
        var names = stored["regiones"].AsArray().Select(n => n.GetValue<string>()).ToHashSet(StringComparer.OrdinalIgnoreCase);
        return VerifyThickness(c, tr, lanes, thickness, stored["tolerancia_m"]?.GetValue<double>() ?? .001, Regions(c).Where(x => names.Contains(x.Region.Name)));
    }

    private static object VerifyStoredDatum(Corridor c, Transaction tr)
    {
        var stored = Record(c, tr)?["datum"] as JsonObject ?? throw new InvalidOperationException("Contrato de Datum ausente");
        var tin = (TinSurface)tr.GetObject(FromHandle(c.Database, stored["superficie"].GetValue<string>()), OpenMode.ForRead);
        return VerifyDatum(c, tr, tin, stored["codigo"].GetValue<string>());
    }

    // ---------- leer ----------
    private static object Read(Corridor c, Transaction tr)
    {
        var keys = CubicacionContract.DefaultCodes.Select(code => code + "Depth").ToArray();
        var assemblies = Regions(c).Select(x => x.Region.AssemblyId).Distinct().Select(id =>
        {
            var a = (CivAssembly)tr.GetObject(id, OpenMode.ForRead);
            return new { handle = H(id), nombre = a.Name, carriles = PartsOf(a, tr).Where(IsLane).Select(s => Describe(s, keys)).ToArray() };
        }).ToArray();
        return new { corredor = H(c.ObjectId), nombre = c.Name, fuera_de_fecha = c.IsOutOfDate, baselines = c.Baselines.Count,
            regiones = Regions(c).Count(), ensamblajes = assemblies, superficies = Surfaces(c, tr), contrato = Record(c, tr) };
    }

    // ---------- espesores ----------
    private static object Thickness(Corridor c, Transaction tr, CivilDocument civil, ThicknessOptions o, bool sim)
    {
        var all = Regions(c).ToArray();
        var selected = all;
        if (o.Regions.Length > 0)
        {
            selected = all.Where(x => o.Regions.Contains(x.Region.Name, StringComparer.OrdinalIgnoreCase)).ToArray();
            var missing = o.Regions.Where(n => !all.Any(x => x.Region.Name.Equals(n, StringComparison.OrdinalIgnoreCase))).ToArray();
            if (missing.Length > 0) throw new ArgumentException("Regiones inexistentes: " + string.Join(", ", missing));
        }
        var assemblyIds = selected.Select(x => x.Region.AssemblyId).Distinct().ToArray();
        // An assembly shared with another corridor, or with a region left out of the selection, would change geometry outside the request.
        foreach (ObjectId otherId in civil.CorridorCollection)
        {
            if (otherId == c.ObjectId) continue;
            var other = (Corridor)tr.GetObject(otherId, OpenMode.ForRead);
            var shared = Regions(other).Where(x => assemblyIds.Contains(x.Region.AssemblyId)).Select(x => x.Region.Name).ToArray();
            if (shared.Length > 0) throw new ArgumentException("Ensamblaje compartido con el corredor " + other.Name + " (regiones " + string.Join(", ", shared) + ")");
        }
        var outside = all.Except(selected).Where(x => assemblyIds.Contains(x.Region.AssemblyId)).Select(x => x.Region.Name).ToArray();
        if (outside.Length > 0) throw new ArgumentException("Ensamblaje compartido con regiones no seleccionadas: " + string.Join(", ", outside));

        var keys = o.Thickness.Keys.ToArray();
        var lanes = new Dictionary<ObjectId, Subassembly>();
        var log = new List<object>();
        var requested = new HashSet<string>(o.Subassemblies, StringComparer.OrdinalIgnoreCase);
        var matched = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var aid in assemblyIds)
        {
            var a = (CivAssembly)tr.GetObject(aid, OpenMode.ForRead); Local(a);
            var parts = PartsOf(a, tr);
            Subassembly[] chosen;
            if (requested.Count > 0)
            {
                chosen = parts.Where(s => requested.Contains(s.Name) || requested.Contains(H(s.ObjectId))).ToArray();
                foreach (var s in chosen) { matched.Add(s.Name); matched.Add(H(s.ObjectId)); }
            }
            else chosen = parts.Where(IsLane).ToArray();
            var rows = new List<object>();
            foreach (var s in chosen)
            {
                var before = Values(s, keys);
                var w = (Subassembly)tr.GetObject(s.ObjectId, OpenMode.ForWrite);
                var written = new List<string>(); var unchanged = new List<string>(); var absent = new List<string>();
                foreach (var key in keys)
                {
                    if (!before.ContainsKey(key)) { absent.Add(key); continue; }
                    var param = w.ParamsDouble[key];
                    if (Math.Abs(param.Value - o.Thickness[key]) < 1e-12) { unchanged.Add(key); continue; }
                    if (param.IsReadOnly) throw new InvalidOperationException("Parametro de solo lectura en " + w.Name + ": " + key);
                    param.Value = o.Thickness[key];
                    if (Math.Abs(w.ParamsDouble[key].Value - o.Thickness[key]) > 1e-12) throw new InvalidOperationException("No se pudo escribir " + key + " en " + w.Name);
                    written.Add(key);
                }
                if (absent.Count == keys.Length) throw new ArgumentException("El subensamblaje " + w.Name + " no tiene ninguno de los parametros pedidos");
                w.Run();
                lanes[w.ObjectId] = w;
                rows.Add(new { handle = H(w.ObjectId), nombre = w.Name, lado = w.Side.ToString(), antes = before, despues = Values(w, keys), escritos = written, iguales = unchanged, ausentes = absent });
            }
            log.Add(new { handle = H(aid), nombre = a.Name, piezas = parts.Length, carriles = rows });
        }
        var unmatched = requested.Where(k => !matched.Contains(k)).ToArray();
        if (unmatched.Length > 0) throw new ArgumentException("Subensamblajes no encontrados en los ensamblajes del corredor: " + string.Join(", ", unmatched));
        if (lanes.Count == 0) throw new ArgumentException("Ningun carril (Width, DefaultSlope, Pave1Depth) en los ensamblajes seleccionados");
        QaCheckpoint?.Invoke("params-written");
        var layout = VerifyLayout(lanes.Values, o.Thickness, o.Tolerance);
        var record = new JsonObject
        {
            ["espesores"] = new JsonObject(o.Thickness.Select(kv => KeyValuePair.Create(kv.Key, (JsonNode)kv.Value))),
            ["carriles"] = new JsonArray(lanes.Keys.Select(id => (JsonNode)H(id)).ToArray()),
            ["regiones"] = new JsonArray(selected.Select(x => (JsonNode)x.Region.Name).ToArray()),
            ["tolerancia_m"] = o.Tolerance
        };
        Store(c, tr, "espesores", record); QaCheckpoint?.Invoke("record-written");
        return new { corredor = H(c.ObjectId), nombre = c.Name, simulacion = sim, espesores = o.Thickness, regiones = selected.Select(x => x.Region.Name).ToArray(),
            ensamblajes = log, carriles = lanes.Count, verificacion_geometria_propia = layout,
            nota = sim ? "Las secciones aplicadas se comprueban al confirmar: dentro de la transaccion el corredor reconstruido conserva los espesores anteriores." : null };
    }

    // Vertical thickness of a layer shape measured at its two side edges (the stock lane layers have vertical sides).
    private sealed record Layer(double Width, double Inner, double Outer, double Area);
    private static Layer Measure(IList<(double Offset, double Z)> pts)
    {
        if (pts.Count < 4) return null;
        double lo = pts.Min(p => p.Offset), hi = pts.Max(p => p.Offset);
        double Span(double at) { var side = pts.Where(p => Math.Abs(p.Offset - at) < 1e-6).ToArray(); return side.Length < 2 ? double.NaN : side.Max(p => p.Z) - side.Min(p => p.Z); }
        // Shoelace over the distinct vertices in angular order around the centroid: the shapes are convex quadrilaterals.
        var v = pts.GroupBy(p => (Math.Round(p.Offset, 9), Math.Round(p.Z, 9))).Select(g => g.First()).ToArray();
        double cx = v.Average(p => p.Offset), cz = v.Average(p => p.Z);
        var ordered = v.OrderBy(p => Math.Atan2(p.Z - cz, p.Offset - cx)).ToArray();
        double area = 0;
        for (int i = 0; i < ordered.Length; i++) { var a = ordered[i]; var b = ordered[(i + 1) % ordered.Length]; area += a.Offset * b.Z - b.Offset * a.Z; }
        return new Layer(hi - lo, Span(lo), Span(hi), Math.Abs(area) / 2);
    }

    private sealed class Tally
    {
        public int Samples; public double MaxError; public readonly List<string> Bad = new();
        public readonly Dictionary<string, (int Samples, double MaxError)> PerCode = new();
        public void Add(string code, string where, Layer layer, double depth, double tol)
        {
            if (layer == null || !double.IsFinite(layer.Inner) || !double.IsFinite(layer.Outer)) { if (Bad.Count < 20) Bad.Add(code + "@" + where + ":sin bordes verticales"); return; }
            double err = Math.Max(Math.Abs(layer.Inner - depth), Math.Abs(layer.Outer - depth));
            Samples++; MaxError = Math.Max(MaxError, err);
            var e = PerCode.GetValueOrDefault(code); PerCode[code] = (e.Samples + 1, Math.Max(e.MaxError, err));
            if (err > tol && Bad.Count < 20) Bad.Add(code + "@" + where + "=" + err.ToString("E2"));
        }
    }

    // Layout geometry of the subassemblies themselves (Run already executed): valid in simulation, before any corridor rebuild.
    private static object VerifyLayout(IEnumerable<Subassembly> lanes, Dictionary<string, double> thickness, double tol)
    {
        var checks = thickness.Select(kv => (Code: CubicacionContract.ShapeCode(kv.Key), Depth: kv.Value)).Where(x => x.Code != null).ToArray();
        var tally = new Tally(); int laneCount = 0;
        foreach (var lane in lanes)
        {
            laneCount++;
            foreach (var check in checks)
            {
                var shapes = lane.Shapes.Cast<CivShape>().Where(s => s.Codes.Cast<string>().Contains(check.Code)).ToArray();
                if (shapes.Length == 0) { if (tally.Bad.Count < 20) tally.Bad.Add(check.Code + "@" + lane.Name + ":sin forma"); continue; }
                foreach (var shape in shapes)
                    tally.Add(check.Code, lane.Name, Measure(shape.Links.Cast<CivLink>().SelectMany(l => l.Points.Cast<CivPoint>()).Select(p => (p.Offset, p.Elevation)).ToList()), check.Depth, tol);
            }
        }
        var result = new { carriles = laneCount, muestras_forma = tally.Samples, error_max_m = tally.MaxError, tolerancia_m = tol,
            por_codigo = tally.PerCode.ToDictionary(kv => kv.Key, kv => new { muestras = kv.Value.Samples, error_max_m = kv.Value.MaxError }), fallos = tally.Bad };
        if (tally.Bad.Count > 0 || tally.MaxError > tol || laneCount == 0 || (checks.Length > 0 && tally.Samples == 0))
            throw new InvalidOperationException("Verificacion de espesores en la geometria de los carriles fallida: " + JsonSerializer.Serialize(result));
        return result;
    }

    // Applied sections of the rebuilt corridor: every lane shape with a known code must show the written depth at both edges.
    private static object VerifyThickness(Corridor c, Transaction tr, HashSet<ObjectId> lanes, Dictionary<string, double> thickness, double tol,
        IEnumerable<(Baseline Baseline, BaselineRegion Region)> regions)
    {
        var checks = thickness.Select(kv => (Code: CubicacionContract.ShapeCode(kv.Key), Depth: kv.Value)).Where(x => x.Code != null).ToArray();
        var tally = new Tally(); int stations = 0, laneHits = 0; var hit = new HashSet<ObjectId>();
        foreach (var (b, r) in regions)
            foreach (var st in OwnStations(b, r))
            {
                if (++stations > StationBudget) throw new ArgumentException("Presupuesto de estaciones excedido");
                string where = st.ToString("F2");
                foreach (AppliedSubassembly sa in b.GetAppliedAssemblyAtStation(st).GetAppliedSubassemblies())
                {
                    if (!lanes.Contains(sa.SubassemblyId)) continue;
                    laneHits++; hit.Add(sa.SubassemblyId);
                    foreach (var check in checks)
                    {
                        var shapes = sa.Shapes.Cast<CalculatedShape>().Where(s => s.CorridorCodes.Cast<string>().Contains(check.Code)).ToArray();
                        if (shapes.Length == 0) { if (tally.Bad.Count < 20) tally.Bad.Add(check.Code + "@" + where + ":sin forma"); continue; }
                        foreach (var shape in shapes)
                            tally.Add(check.Code, where, Measure(shape.CalculatedLinks.Cast<CalculatedLink>().SelectMany(l => l.CalculatedPoints.Cast<CalculatedPoint>())
                                .Select(p => (p.StationOffsetElevationToBaseline.Y, p.StationOffsetElevationToBaseline.Z)).ToList()), check.Depth, tol);
                    }
                }
            }
        var missing = lanes.Where(id => !hit.Contains(id)).Select(H).ToArray();
        var result = new { estaciones = stations, carriles_aplicados = laneHits, carriles_nunca_aplicados = missing, muestras_forma = tally.Samples, error_max_m = tally.MaxError, tolerancia_m = tol,
            por_codigo = tally.PerCode.ToDictionary(kv => kv.Key, kv => new { muestras = kv.Value.Samples, error_max_m = kv.Value.MaxError }),
            fuera_de_fecha = c.IsOutOfDate, superficies = Surfaces(c, tr), fallos = tally.Bad };
        bool fail = tally.Bad.Count > 0 || tally.MaxError > tol || laneHits == 0 || missing.Length > 0 || (checks.Length > 0 && tally.Samples == 0) || c.IsOutOfDate;
        if (fail) throw new InvalidOperationException("Verificacion de espesores en las secciones aplicadas fallida: " + JsonSerializer.Serialize(result));
        return result;
    }

    // ---------- datum ----------
    private static object Datum(Corridor c, Transaction tr, CivilDocument civil, DatumOptions o, bool sim)
    {
        c.Rebuild();
        string name = o.Name ?? c.Name + "_Datum";
        if (SurfaceNameExists(tr, civil, name) || c.CorridorSurfaces.SurfaceNames().Contains(name, StringComparer.OrdinalIgnoreCase))
            throw new ArgumentException("Ya existe una superficie llamada " + name);
        if (!c.GetLinkCodes().Contains(o.Code)) throw new ArgumentException("El corredor no produce el codigo de enlace " + o.Code + " (codigos: " + string.Join(", ", c.GetLinkCodes()) + ")");
        var existing = c.CorridorSurfaces.Cast<CorridorSurface>().Where(s => s.LinkCodes().Contains(o.Code)).Select(s => s.Name).ToArray();
        if (existing.Length > 0) throw new ArgumentException("El corredor ya tiene superficie con enlace " + o.Code + ": " + string.Join(", ", existing));
        var surf = c.CorridorSurfaces.Add(name);
        surf.AddLinkCode(o.Code, true);
        surf.OverhangCorrection = OverhangCorrectionType.BottomLinks;
        surf.Boundaries.AddCorridorExtentsBoundary(name + "_Extents");
        surf.IsBuild = true;
        QaCheckpoint?.Invoke("datum-added");
        RebuildAll(c, tr);
        var tin = (TinSurface)tr.GetObject(surf.SurfaceId, OpenMode.ForRead);
        var verify = VerifyDatum(c, tr, tin, o.Code);
        var record = new JsonObject { ["nombre"] = name, ["superficie"] = H(surf.SurfaceId), ["codigo"] = o.Code, ["contorno"] = name + "_Extents", ["voladizo"] = "BottomLinks" };
        Store(c, tr, "datum", record); QaCheckpoint?.Invoke("record-written");
        return new { corredor = H(c.ObjectId), nombre = c.Name, simulacion = sim,
            superficie = new { handle = sim ? null : H(surf.SurfaceId), nombre = name, codigo = o.Code, voladizo = "BottomLinks", contorno = name + "_Extents" }, verificacion = verify };
    }

    // The surface must have triangles and cover the datum links of the applied sections; the link points sit on or above
    // the surface (overhang correction keeps the lowest link where sections overlap).
    private static object VerifyDatum(Corridor c, Transaction tr, TinSurface tin, string code)
    {
        int triangles = tin.GetTinProperties().NumberOfTriangles, stations = 0, points = 0, covered = 0; double maxAbove = 0, maxBelow = 0;
        foreach (var (b, r) in Regions(c))
            foreach (var st in OwnStations(b, r))
            {
                if (++stations > StationBudget) throw new ArgumentException("Presupuesto de estaciones excedido");
                foreach (CalculatedLink link in b.GetAppliedAssemblyAtStation(st).GetLinksByCode(code))
                    foreach (CalculatedPoint pt in link.CalculatedPoints)
                    {
                        points++;
                        double z;
                        try { z = tin.FindElevationAtXY(pt.XYZ.X, pt.XYZ.Y); }
                        catch (PointNotOnEntityException) { continue; }
                        covered++;
                        double d = pt.XYZ.Z - z;
                        if (d >= 0) maxAbove = Math.Max(maxAbove, d); else maxBelow = Math.Max(maxBelow, -d);
                    }
            }
        double coverage = points == 0 ? 0 : (double)covered / points;
        var result = new { triangulos = triangles, estaciones = stations, puntos_enlace = points, puntos_cubiertos = covered, cobertura = coverage,
            enlace_sobre_superficie_max_m = maxAbove, enlace_bajo_superficie_max_m = maxBelow, fuera_de_fecha = tin.IsOutOfDate || c.IsOutOfDate };
        if (triangles == 0 || points == 0 || coverage < .95 || maxBelow > .005 || tin.IsOutOfDate || c.IsOutOfDate)
            throw new InvalidOperationException("Verificacion de Datum fallida: " + JsonSerializer.Serialize(result));
        return result;
    }

    // ---------- cubicacion ----------
    private static object Volumes(Corridor c, Transaction tr, CivilDocument civil, VolumeOptions o, bool sim)
    {
        if (c.IsOutOfDate) throw new ArgumentException("Corredor fuera de fecha: reconstruir antes de cubicar");
        var surfaceIds = civil.GetSurfaceIds().Cast<ObjectId>().ToArray();
        var terrain = Tin(tr, Resolve(tr, surfaceIds, o.Terrain, "terreno"), "terreno");
        ObjectId datumId;
        var record = Record(c, tr);
        if (o.Datum != null) datumId = Resolve(tr, surfaceIds, o.Datum, "datum");
        else if (record?["datum"]?["superficie"] is JsonValue stored) datumId = FromHandle(c.Database, stored.GetValue<string>());
        else
        {
            var candidates = c.CorridorSurfaces.Cast<CorridorSurface>().Where(s => s.LinkCodes().Contains("Datum")).ToArray();
            if (candidates.Length != 1) throw new ArgumentException("Indique datum: el corredor tiene " + candidates.Length + " superficies con enlace Datum");
            datumId = candidates[0].SurfaceId;
        }
        if (datumId == terrain.ObjectId) throw new ArgumentException("terreno y datum deben ser superficies distintas");
        var datum = Tin(tr, datumId, "datum");
        string name = o.VolumeName ?? c.Name + "_Cubicacion";
        if (SurfaceNameExists(tr, civil, name)) throw new ArgumentException("Ya existe una superficie llamada " + name);
        var vid = TinVolumeSurface.Create(name, terrain.ObjectId, datum.ObjectId);
        var v = (TinVolumeSurface)tr.GetObject(vid, OpenMode.ForWrite);
        v.CutFactor = o.CutFactor; v.FillFactor = o.FillFactor; v.Rebuild();
        QaCheckpoint?.Invoke("volume-created");
        var props = v.GetVolumeProperties();
        double[] values = { props.UnadjustedCutVolume, props.UnadjustedFillVolume, props.UnadjustedNetVolume, props.AdjustedCutVolume, props.AdjustedFillVolume, props.AdjustedNetVolume };
        if (values.Any(x => !double.IsFinite(x)) || v.IsOutOfDate) throw new InvalidOperationException("Volumen no finito o fuera de fecha");

        // Layer volumes: shape areas per code at every applied station, average end area inside each region.
        int stations = 0; var totals = o.Codes.ToDictionary(code => code, _ => 0.0); var areaSum = o.Codes.ToDictionary(code => code, _ => 0.0);
        var baselines = c.Baselines.Cast<Baseline>().Select(b => new
        {
            nombre = b.Name, alineamiento = H(b.AlignmentId), perfil = H(b.ProfileId),
            regiones = b.BaselineRegions.Cast<BaselineRegion>().Select(r =>
            {
                var sts = r.SortedStations().Distinct().OrderBy(x => x).ToArray();
                if (sts.Length < 2) throw new ArgumentException("Region con menos de dos estaciones aplicadas: " + r.Name);
                var rows = sts.Select(st =>
                {
                    if (++stations > StationBudget) throw new ArgumentException("Presupuesto de estaciones excedido");
                    var aa = b.GetAppliedAssemblyAtStation(st);
                    var areas = o.Codes.ToDictionary(code => code, code =>
                    {
                        double area = aa.GetShapesByCode(code).Cast<CalculatedShape>().Sum(s => s.Area);
                        if (!double.IsFinite(area) || area < 0) throw new InvalidOperationException("Area no finita en " + code + "@" + st.ToString("F2"));
                        return area;
                    });
                    return (Station: st, Areas: areas);
                }).ToArray();
                var volumes = o.Codes.ToDictionary(code => code, code => rows.Skip(1).Select((row, i) => (row.Areas[code] + rows[i].Areas[code]) * (row.Station - rows[i].Station) / 2).Sum());
                foreach (var code in o.Codes) { totals[code] += volumes[code]; areaSum[code] += rows.Sum(x => x.Areas[code]); }
                return new { nombre = r.Name, inicio = r.StartStation, fin = r.EndStation, longitud = sts[^1] - sts[0], estaciones = sts.Length, ensamblaje = H(r.AssemblyId),
                    volumenes_m3 = volumes, filas = rows.Select(x => new { estacion = x.Station, areas_m2 = x.Areas }).ToArray() };
            }).ToArray()
        }).ToArray();
        var layers = o.Codes.Select(code => new { codigo = code, volumen_m3 = totals[code], area_media_m2 = stations == 0 ? 0 : areaSum[code] / stations }).ToArray();
        var keys = CubicacionContract.DefaultCodes.Select(code => code + "Depth").ToArray();
        var thickness = Regions(c).Select(x => x.Region.AssemblyId).Distinct().Select(id =>
        {
            var a = (CivAssembly)tr.GetObject(id, OpenMode.ForRead);
            return new { handle = H(id), nombre = a.Name, carriles = PartsOf(a, tr).Where(IsLane).Select(s => Describe(s, keys)).ToArray() };
        }).ToArray();
        var volume = new { handle = sim ? null : H(vid), nombre = name, base_terreno = H(terrain.ObjectId), comparacion_datum = H(datum.ObjectId), unidad = "m3",
            corte = values[0], relleno = values[1], neto = values[2], factor_corte = props.CutFactor, factor_relleno = props.FillFactor,
            corte_ajustado = values[3], relleno_ajustado = values[4], neto_ajustado = values[5] };
        var entry = new JsonObject
        {
            ["terreno"] = H(terrain.ObjectId), ["datum"] = H(datum.ObjectId), ["volumen"] = sim ? null : H(vid), ["nombre_volumen"] = name,
            ["corte"] = values[0], ["relleno"] = values[1], ["neto"] = values[2], ["factor_corte"] = props.CutFactor, ["factor_relleno"] = props.FillFactor,
            ["capas_m3"] = new JsonObject(o.Codes.Select(code => KeyValuePair.Create(code, (JsonNode)totals[code]))), ["estaciones"] = stations, ["simulacion"] = sim
        };
        Store(c, tr, "cubicacion", entry); QaCheckpoint?.Invoke("record-written");
        return new { corredor = H(c.ObjectId), nombre = c.Name, simulacion = sim, volumen = volume, capas = layers, estaciones = stations, baselines,
            espesores_vigentes = thickness, fuera_de_fecha = c.IsOutOfDate };
    }

    // ---------- reconstruir ----------
    // Civil flags the corridor out of date again when the command that changed its assemblies or surfaces ends.
    // A rebuild in a command of its own clears it for good; the stored thickness contract is verified again.
    private static object Settle(Corridor c, Transaction tr)
    {
        bool wasOutOfDate = c.IsOutOfDate;
        RebuildAll(c, tr);
        var record = Record(c, tr);
        object thickness = record?["espesores"] is JsonObject ? VerifyStoredThickness(c, tr) : null;
        object datum = record?["datum"] is JsonObject ? VerifyStoredDatum(c, tr) : null;
        if (c.IsOutOfDate) throw new InvalidOperationException("El corredor sigue fuera de fecha tras reconstruir");
        return new { corredor = H(c.ObjectId), nombre = c.Name, estaba_fuera_de_fecha = wasOutOfDate, fuera_de_fecha = c.IsOutOfDate, superficies = Surfaces(c, tr),
            verificacion_espesores = thickness, verificacion_datum = datum };
    }
}
