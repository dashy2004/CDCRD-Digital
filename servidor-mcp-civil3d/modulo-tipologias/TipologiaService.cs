// Corridor edge classification and per-stretch palette typologies.
// All writes happen inside one transaction of the active document; simulation aborts it.
using System;
using System.Collections.Generic;
using System.IO;
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
using CivPoint = Autodesk.Civil.DatabaseServices.Point;

namespace Cdcrd.Tipologias;

internal static class TipologiaService
{
    internal static Action<string> QaCheckpoint = null;
    internal const string RecordName = "CDCRD_TIPOLOGIAS_V1";
    private const string CurbCode = "Back_Curb";
    private const string DaylightCode = "Daylight";
    private static readonly string[] LaneKeys = { "Width", "DefaultSlope", "Pave1Depth", "Pave2Depth", "BaseDepth", "SubBaseDepth" };

    private sealed record Transition(string Sub, string Param, double S0, double S1, double V0, double V1);
    private sealed record OldTarget(string Sub, string Type, string Logical, ObjectId[] Ids);

    // A library DWG opened read-only as a side database; the single assembly it holds is the source.
    private sealed class Library : IDisposable
    {
        internal readonly Database Db; internal readonly Transaction Tr; internal readonly CivAssembly Assembly; internal readonly Subassembly[] Parts; internal readonly string File;
        internal Library(string folder, string name)
        {
            File = Path.Combine(folder, name + ".dwg");
            if (!System.IO.File.Exists(File)) throw new FileNotFoundException("Ensamblaje de paleta no encontrado: " + File);
            Db = new Database(false, true);
            Db.ReadDwgFile(File, FileOpenMode.OpenForReadAndAllShare, false, null);
            Db.CloseInput(true);
            Tr = Db.TransactionManager.StartTransaction();
            var ids = CivilDocument.GetCivilDocument(Db).AssemblyCollection.Cast<ObjectId>().ToArray();
            if (ids.Length != 1) throw new InvalidOperationException("La paleta debe contener un solo ensamblaje: " + File);
            Assembly = (CivAssembly)Tr.GetObject(ids[0], OpenMode.ForRead);
            Parts = PartsOf(Assembly, Tr);
        }
        public void Dispose() { Tr.Abort(); Tr.Dispose(); Db.Dispose(); }
    }

    // ---------- helpers ----------
    private static string H(ObjectId id) => id.IsNull ? null : id.Handle.ToString();
    private static double[] Pt(Point3d p) => new[] { p.X, p.Y, p.Z };
    private static string Text(JsonObject p, string k) => TipologiaContract.Text(p, k);
    private static Subassembly[] PartsOf(CivAssembly a, Transaction tr) => a.Groups.Cast<AssemblyGroup>()
        .SelectMany(g => g.GetSubassemblyIds().Cast<ObjectId>()).Select(x => (Subassembly)tr.GetObject(x, OpenMode.ForRead)).ToArray();
    private static bool HasDouble(Subassembly s, string key) => s.ParamsDouble.Cast<ParamDouble>().Any(x => x.Key == key);
    private static bool IsLane(Subassembly s) => HasDouble(s, "Width") && HasDouble(s, "DefaultSlope") && HasDouble(s, "Pave1Depth");
    private static bool IsBand(Subassembly s) => HasDouble(s, "Width") && HasDouble(s, "Slope") && !HasDouble(s, "Pave1Depth");
    private static bool HasCode(CalculatedPoint p, string code) => p.CorridorCodes.Cast<string>().Contains(code);
    private static ObjectId Resolve(Transaction tr, IEnumerable<ObjectId> ids, string key, string what)
    {
        var found = ids.Where(id => string.Equals(H(id), key, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(((CivEntity)tr.GetObject(id, OpenMode.ForRead)).Name, key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (found.Length != 1) throw new ArgumentException(what + " inexistente o ambiguo: " + key);
        return found[0];
    }
    private static void Local(CivEntity e) { if (e.IsReferenceObject || e.IsCWSReferenceObject) throw new ArgumentException("Se requiere objeto local: " + e.Name); }
    private static ObjectId LayerId(Transaction tr, Database db, string name, ObjectId fallback)
    {
        if (name == null) return fallback;
        var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
        if (lt.Has(name)) return lt[name];
        lt.UpgradeOpen(); var rec = new LayerTableRecord { Name = name }; var id = lt.Add(rec); tr.AddNewlyCreatedDBObject(rec, true); return id;
    }

    // Outermost point of one side carrying a code; ties by the highest point.
    private static CalculatedPoint Extreme(AppliedAssembly aa, string code, int sign)
    {
        var side = aa.Points.Cast<CalculatedPoint>().Where(p => HasCode(p, code) && sign * p.StationOffsetElevationToBaseline.Y > 1e-6).ToArray();
        if (side.Length == 0) return null;
        double m = side.Max(p => Math.Abs(p.StationOffsetElevationToBaseline.Y));
        return side.Where(p => Math.Abs(Math.Abs(p.StationOffsetElevationToBaseline.Y) - m) < 1e-6).OrderByDescending(p => p.XYZ.Z).First();
    }
    // The edge code must belong to the outermost point of each side: a lane followed by a
    // band exposes ETW on the lane and Edge on the band, and the band edge is the real border.
    private static string EdgeCode(Baseline b, double station, string requested)
    {
        var points = b.GetAppliedAssemblyAtStation(station).Points.Cast<CalculatedPoint>().ToArray();
        var outer = new[] { -1, 1 }.Select(sign =>
        {
            var side = points.Where(p => sign * p.StationOffsetElevationToBaseline.Y > 1e-6).ToArray();
            if (side.Length == 0) throw new ArgumentException("La seccion aplicada no tiene puntos a un lado del eje");
            double m = side.Max(p => Math.Abs(p.StationOffsetElevationToBaseline.Y));
            return new HashSet<string>(side.Where(p => Math.Abs(Math.Abs(p.StationOffsetElevationToBaseline.Y) - m) < 1e-6).SelectMany(p => p.CorridorCodes.Cast<string>()));
        }).ToArray();
        if (requested != null)
        {
            if (!outer.All(c => c.Contains(requested))) throw new ArgumentException("codigo_borde no esta en el punto exterior de ambos lados: " + requested);
            return requested;
        }
        foreach (var code in new[] { "ETW", "Edge" }) if (outer.All(c => c.Contains(code))) return code;
        throw new ArgumentException("El punto exterior no lleva ETW ni Edge (codigos: " + string.Join(", ", outer[0].Intersect(outer[1])) + "); indique codigo_borde");
    }
    // Hook point of a subassembly: outermost offset, then the highest point (top of pavement).
    private static CivPoint Hook(Subassembly s) => s.Points.Cast<CivPoint>().OrderByDescending(p => Math.Round(Math.Abs(p.Offset), 6)).ThenByDescending(p => p.Elevation).First();

    private static bool OnAny(IEnumerable<TinSurface> surfaces, double x, double y)
    {
        foreach (var s in surfaces)
        {
            try { s.FindElevationAtXY(x, y); return true; }
            catch (PointNotOnEntityException) { }
        }
        return false;
    }

    // Copies every input parameter that exists on both subassemblies. A failed set or a
    // mismatch after copying is an error: nothing is silently skipped.
    private static object CopyParams(Subassembly src, Subassembly dst, string[] onlyKeys, string[] skipKeys)
    {
        var copied = new List<string>(); var unchanged = new List<string>(); var absent = new List<string>();
        bool Wanted(string k) => (onlyKeys == null || onlyKeys.Contains(k)) && !skipKeys.Contains(k);
        var dstD = dst.ParamsDouble.Cast<ParamDouble>().ToDictionary(x => x.Key);
        foreach (ParamDouble p in src.ParamsDouble)
        {
            if (!Wanted(p.Key)) continue;
            if (!dstD.TryGetValue(p.Key, out var d)) { absent.Add(p.Key); continue; }
            if (Math.Abs(d.Value - p.Value) < 1e-12) { unchanged.Add(p.Key); continue; }
            if (d.IsReadOnly) throw new InvalidOperationException("Parametro de solo lectura distinto en " + dst.Name + ": " + p.Key);
            d.Value = p.Value;
            if (Math.Abs(dst.ParamsDouble[p.Key].Value - p.Value) > 1e-12) throw new InvalidOperationException("No se pudo copiar " + p.Key + " en " + dst.Name);
            copied.Add(p.Key);
        }
        var dstL = dst.ParamsLong.Cast<ParamLong>().ToDictionary(x => x.Key);
        foreach (ParamLong p in src.ParamsLong)
        {
            if (!Wanted(p.Key)) continue;
            if (!dstL.TryGetValue(p.Key, out var d)) { absent.Add(p.Key); continue; }
            if (d.Value == p.Value) { unchanged.Add(p.Key); continue; }
            try { d.Value = p.Value; }
            catch (InvalidOperationException ex) { throw new InvalidOperationException("No se pudo copiar el entero " + p.Key + " (" + p.Value + ") en " + dst.Name + ": " + ex.Message); }
            if (dst.ParamsLong[p.Key].Value != p.Value) throw new InvalidOperationException("No se pudo copiar " + p.Key + " en " + dst.Name);
            copied.Add(p.Key);
        }
        var dstS = dst.ParamsString.Cast<ParamString>().ToDictionary(x => x.Key);
        foreach (ParamString p in src.ParamsString)
        {
            if (!Wanted(p.Key)) continue;
            if (!dstS.TryGetValue(p.Key, out var d)) { absent.Add(p.Key); continue; }
            if (d.Value == p.Value) { unchanged.Add(p.Key); continue; }
            d.Value = p.Value;
            if (dst.ParamsString[p.Key].Value != p.Value) throw new InvalidOperationException("No se pudo copiar " + p.Key + " en " + dst.Name);
            copied.Add(p.Key);
        }
        var dstB = dst.ParamsBool.Cast<ParamBool>().ToDictionary(x => x.Key);
        foreach (ParamBool p in src.ParamsBool)
        {
            if (!Wanted(p.Key)) continue;
            if (!dstB.TryGetValue(p.Key, out var d)) { absent.Add(p.Key); continue; }
            if (d.Value == p.Value) { unchanged.Add(p.Key); continue; }
            d.Value = p.Value;
            if (dst.ParamsBool[p.Key].Value != p.Value) throw new InvalidOperationException("No se pudo copiar " + p.Key + " en " + dst.Name);
            copied.Add(p.Key);
        }
        return new { copiados = copied, iguales = unchanged, ausentes = absent };
    }

    private static object Describe(Subassembly s) => new
    {
        handle = H(s.ObjectId), nombre = s.Name, lado = s.Side.ToString(), engancha_a = H(s.SubassemblyHookTo),
        dobles = s.ParamsDouble.Cast<ParamDouble>().ToDictionary(p => p.Key, p => p.Value),
        enteros = s.ParamsLong.Cast<ParamLong>().ToDictionary(p => p.Key, p => p.Value),
        textos = s.ParamsString.Cast<ParamString>().ToDictionary(p => p.Key, p => p.Value)
    };

    private static JsonNode Record(Corridor c, Transaction tr)
    {
        if (c.ExtensionDictionary.IsNull) throw new ArgumentException("Corredor sin contrato propio");
        var d = (DBDictionary)tr.GetObject(c.ExtensionDictionary, OpenMode.ForRead);
        if (!d.Contains(RecordName)) throw new ArgumentException("Corredor sin contrato " + RecordName);
        var x = (Xrecord)tr.GetObject(d.GetAt(RecordName), OpenMode.ForRead);
        return JsonNode.Parse(string.Concat(x.Data.AsArray().Select(v => (string)v.Value))) ?? throw new ArgumentException("Contrato invalido");
    }
    private static void Store(Corridor c, Transaction tr, JsonNode data)
    {
        if (c.ExtensionDictionary.IsNull) c.CreateExtensionDictionary();
        var dict = (DBDictionary)tr.GetObject(c.ExtensionDictionary, OpenMode.ForWrite);
        if (dict.Contains(RecordName)) throw new ArgumentException("El corredor ya tiene tipologia aplicada; no reemplazar");
        string json = data.ToJsonString();
        var x = new Xrecord { Data = new ResultBuffer(Enumerable.Range(0, (json.Length + 239) / 240)
            .Select(i => new TypedValue((int)DxfCode.Text, json.Substring(i * 240, Math.Min(240, json.Length - i * 240)))).ToArray()) };
        dict.SetAt(RecordName, x); tr.AddNewlyCreatedDBObject(x, true);
    }

    // ---------- entry ----------
    internal static object Execute(JsonObject p, out bool committed)
    {
        committed = false;
        var doc = App.DocumentManager.MdiActiveDocument ?? throw new InvalidOperationException("Sin documento");
        if (!DateTimeOffset.TryParse(Text(p, "vence_utc"), out var expires) || expires < DateTimeOffset.UtcNow || expires > DateTimeOffset.UtcNow.AddMinutes(5))
            throw new ArgumentException("Solicitud vencida o plazo invalido");
        if (p["pid"]?.GetValue<int>() != Environment.ProcessId || !Path.IsPathFullyQualified(Text(p, "dibujo")) ||
            !string.Equals(Path.GetFullPath(doc.Name), Path.GetFullPath(Text(p, "dibujo")), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Documento o PID distinto al esperado");
        if (Convert.ToInt32(App.GetSystemVariable("INSUNITS")) != 6 || CivilApp.ActiveDocument.Settings.DrawingSettings.UnitZoneSettings.DrawingUnits.ToString() != "Meters")
            throw new ArgumentException("Se requieren unidades Civil y AutoCAD en metros");
        string action = Text(p, "accion");
        if (!new[] { "clasificar", "aplicar", "reconstruir", "verificar" }.Contains(action)) throw new ArgumentException("Accion desconocida");
        bool write = action == "aplicar" || action == "reconstruir", sim = action == "aplicar" && (p["simular"]?.GetValue<bool>() ?? true);
        if (write && (Environment.GetEnvironmentVariable("CDCRD_C3D_SOLO_LECTURA") == "1" || Environment.GetEnvironmentVariable("CDCRD_C3D_PERMITIR_COMANDOS") != "1"))
            throw new InvalidOperationException("Escritura/comandos deshabilitados");
        using (doc.LockDocument())
        using (var tr = doc.Database.TransactionManager.StartTransaction())
        {
            var civil = CivilApp.ActiveDocument;
            var cid = Resolve(tr, civil.CorridorCollection, Text(p, "corredor"), "corredor");
            var c = (Corridor)tr.GetObject(cid, write ? OpenMode.ForWrite : OpenMode.ForRead);
            Local(c);
            object result = action switch
            {
                "clasificar" => Classify(c, tr, civil, TipologiaContract.ParseClassify(p)),
                "aplicar" => Apply(c, tr, doc.Database, civil, TipologiaContract.ParseApply(p), sim),
                "reconstruir" => Settle(c, tr),
                _ => Verify(c, tr, Record(c, tr) as JsonObject ?? throw new ArgumentException("Contrato invalido"), null, null)
            };
            if (write && !sim) { tr.Commit(); committed = true; } else tr.Abort();
            if (!committed || action != "aplicar") return result;
            // Civil flags the corridor out of date once the transaction commits (deferred
            // indicator): rebuild in a second transaction and verify again from the contract.
            using (var settle = doc.Database.TransactionManager.StartTransaction())
            {
                var c2 = (Corridor)settle.GetObject(cid, OpenMode.ForWrite);
                c2.Rebuild();
                ((TinSurface)settle.GetObject(c2.CorridorSurfaces[0].SurfaceId, OpenMode.ForWrite)).Rebuild();
                settle.Commit();
            }
            using (var check = doc.Database.TransactionManager.StartTransaction())
            {
                var c3 = (Corridor)check.GetObject(cid, OpenMode.ForRead);
                var after = Verify(c3, check, Record(c3, check) as JsonObject, null, null);
                check.Abort();
                return new { aplicado = result, verificacion_tras_confirmar = after };
            }
        }
    }

    // ---------- clasificar ----------
    private static object Classify(Corridor c, Transaction tr, CivilDocument civil, ClassifyOptions o)
    {
        if (c.Baselines.Count != 1) throw new ArgumentException("Se requiere un corredor con una sola baseline");
        if (c.IsOutOfDate) throw new ArgumentException("Corredor fuera de fecha: reconstruir antes de clasificar");
        var b = c.Baselines[0];
        var al = (Alignment)tr.GetObject(b.AlignmentId, OpenMode.ForRead);
        var own = new HashSet<ObjectId>(c.CorridorSurfaces.Cast<CorridorSurface>().Select(s => s.SurfaceId));
        var allSurfaces = civil.GetSurfaceIds().Cast<ObjectId>().ToArray();
        var excluded = new HashSet<ObjectId>(o.Excluded.Select(k => Resolve(tr, allSurfaces, k, "superficie excluida")));
        List<ObjectId> pavedIds;
        if (o.Paved.Length > 0) pavedIds = o.Paved.Select(k => Resolve(tr, allSurfaces, k, "superficie de pavimento")).ToList();
        else pavedIds = civil.CorridorCollection.Cast<ObjectId>().Where(id => id != c.ObjectId)
            .SelectMany(id => ((Corridor)tr.GetObject(id, OpenMode.ForRead)).CorridorSurfaces.Cast<CorridorSurface>().Select(s => s.SurfaceId)).ToList();
        var paved = pavedIds.Distinct().Where(id => !own.Contains(id) && !excluded.Contains(id))
            .Select(id => tr.GetObject(id, OpenMode.ForRead) as TinSurface).Where(s => s != null).ToArray();
        if (paved.Length == 0) throw new ArgumentException("Ninguna superficie de pavimento vigente contra la que clasificar");
        var regions = b.BaselineRegions.Cast<BaselineRegion>().ToArray();
        string code = EdgeCode(b, regions[0].SortedStations().First(), o.EdgeCode);
        var rows = new List<(double St, bool[] Adj, double[][] Edge, double[][] Probe)>();
        int budget = 0;
        foreach (var r in regions)
            foreach (var st in r.SortedStations())
            {
                if (++budget > 20000) throw new ArgumentException("Presupuesto de estaciones excedido");
                if (rows.Count > 0 && Math.Abs(rows[^1].St - st) < 1e-6) continue; // shared boundary station
                var aa = b.GetAppliedAssemblyAtStation(st);
                double bx = 0, by = 0; al.PointLocation(st, 0, ref bx, ref by);
                var adj = new bool[2]; var edge = new double[2][]; var probe = new double[2][];
                foreach (var (i, sign) in new[] { (0, -1), (1, 1) })
                {
                    var e = Extreme(aa, code, sign) ?? throw new InvalidOperationException("Sin punto " + code + " en la estacion " + st.ToString("F2"));
                    var v = new Vector2d(e.XYZ.X - bx, e.XYZ.Y - by);
                    if (v.Length < 1e-6) throw new InvalidOperationException("Borde sobre el eje en la estacion " + st.ToString("F2"));
                    v = v.GetNormal();
                    double px = e.XYZ.X + v.X * o.Probe, py = e.XYZ.Y + v.Y * o.Probe;
                    adj[i] = OnAny(paved, px, py); edge[i] = Pt(e.XYZ); probe[i] = new[] { px, py };
                }
                rows.Add((st, adj, edge, probe));
            }
        if (rows.Count < 2) throw new ArgumentException("Se requieren al menos dos estaciones aplicadas");
        // Runs per side with the two short-stretch filters, in this order: short junctions become free, then short free stretches become junctions.
        var free = new bool[2][];
        for (int i = 0; i < 2; i++)
        {
            var adj = rows.Select(r => r.Adj[i]).ToArray();
            adj = Filter(rows, adj, true, o.UnionMin);
            adj = Filter(rows, adj, false, o.FreeMin);
            free[i] = adj.Select(x => !x).ToArray();
        }
        string KindAt(int k) => free[0][k] && free[1][k] ? "LR" : free[0][k] ? "L" : free[1][k] ? "R" : "-";
        // A junction stretch spans exactly its adjacent stations: the cut sits on the first
        // adjacent station when a side closes and on the last adjacent station when it opens.
        var segments = new List<object>(); double from = regions[0].StartStation; string kind = KindAt(0);
        for (int k = 1; k < rows.Count; k++)
        {
            string next = KindAt(k); if (next == kind) continue;
            bool closes = Enumerable.Range(0, 2).Any(i => free[i][k - 1] && !free[i][k]), opens = Enumerable.Range(0, 2).Any(i => !free[i][k - 1] && free[i][k]);
            double cut = Math.Round(closes && opens ? (rows[k - 1].St + rows[k].St) / 2 : closes ? rows[k].St : rows[k - 1].St, 2);
            if (cut - from >= .01) { segments.Add(new object[] { from, cut, kind }); from = cut; }
            kind = next;
        }
        segments.Add(new object[] { from, regions[^1].EndStation, kind });
        var sides = new[] { "Left", "Right" }.Select((name, i) => new
        {
            lado = name, estaciones = rows.Count, adyacentes_crudos = rows.Count(r => r.Adj[i]), libres_filtrados = free[i].Count(x => x),
            estaciones_union = rows.Where((r, k) => !free[i][k]).Select(r => Math.Round(r.St, 2)).ToArray()
        }).ToArray();
        return new
        {
            corredor = H(c.ObjectId), nombre = c.Name, codigo_borde = code, sonda_m = o.Probe, union_min_m = o.UnionMin, libre_min_m = o.FreeMin,
            superficies_pavimento = paved.Select(s => new { handle = H(s.ObjectId), s.Name }).ToArray(),
            regiones = regions.Select(r => new
            {
                r.Name, inicio = r.StartStation, fin = r.EndStation, ensamblaje = H(r.AssemblyId),
                partes = PartsOf((CivAssembly)tr.GetObject(r.AssemblyId, OpenMode.ForRead), tr).Select(Describe).ToArray(),
                objetivos = r.GetTargets().Cast<SubassemblyTargetInfo>().Where(t => t.TargetIds != null && t.TargetIds.Count > 0)
                    .Select(t => new { t.SubassemblyName, t.LogicalName, tipo = t.TargetType.ToString(), ids = t.TargetIds.Cast<ObjectId>().Select(H).ToArray() }).ToArray()
            }).ToArray(),
            transiciones = b.getTransitions().Sum(s => s.TransitionCount),
            superficies = c.CorridorSurfaces.Cast<CorridorSurface>().Select(s => new { s.Name, handle = H(s.SurfaceId), contornos = s.Boundaries.BoundaryNames() }).ToArray(),
            lados = sides, segmentos = segments,
            muestras = rows.Select(r => new { estacion = r.St, izq = new { union = r.Adj[0], borde = r.Edge[0], sonda = r.Probe[0] }, der = new { union = r.Adj[1], borde = r.Edge[1], sonda = r.Probe[1] } }).ToArray()
        };
    }

    // Flips every run whose value equals `value` and whose station span is shorter than `min`.
    private static bool[] Filter(List<(double St, bool[] Adj, double[][] Edge, double[][] Probe)> rows, bool[] values, bool value, double min)
    {
        var result = (bool[])values.Clone();
        int start = 0;
        while (start < result.Length)
        {
            int end = start; while (end + 1 < result.Length && result[end + 1] == result[start]) end++;
            if (result[start] == value && rows[end].St - rows[start].St < min) for (int k = start; k <= end; k++) result[k] = !value;
            start = end + 1;
        }
        return result;
    }

    // ---------- aplicar ----------
    private static object Apply(Corridor c, Transaction tr, Database db, CivilDocument civil, ApplyOptions o, bool sim)
    {
        if (c.Baselines.Count != 1 || c.Baselines[0].BaselineRegions.Count != 1 || c.CorridorSurfaces.Count != 1)
            throw new ArgumentException("Se requiere un corredor con una baseline, una region y una superficie");
        if (!c.ExtensionDictionary.IsNull && ((DBDictionary)tr.GetObject(c.ExtensionDictionary, OpenMode.ForRead)).Contains(RecordName))
            throw new ArgumentException("El corredor ya tiene tipologia aplicada; no reemplazar");
        var segs = o.Segments;
        bool slopes = segs.Any(s => s.Kind == "talud");
        TinSurface terrain = null;
        if (slopes)
        {
            if (o.Terrain == null) throw new ArgumentException("Los tramos talud requieren superficie_terreno");
            terrain = tr.GetObject(Resolve(tr, civil.GetSurfaceIds().Cast<ObjectId>(), o.Terrain, "superficie_terreno"), OpenMode.ForRead) as TinSurface
                ?? throw new ArgumentException("superficie_terreno debe ser una TIN"); Local(terrain);
        }
        c.Rebuild(); // complete starting state before capturing reference edges
        var b = c.Baselines[0]; var region0 = b.BaselineRegions[0]; string regionName = region0.Name;
        if (Math.Abs(segs[0].From - region0.StartStation) > 1e-3 || Math.Abs(segs[^1].To - region0.EndStation) > 1e-3)
            throw new ArgumentException("Los tramos deben cubrir la region " + region0.StartStation.ToString("F3") + ".." + region0.EndStation.ToString("F3"));
        var oldSt = region0.SortedStations().ToArray();
        if (oldSt.Length < 2 || oldSt.Length > 20000) throw new ArgumentException("Estaciones aplicadas fuera de presupuesto");
        string code = EdgeCode(b, oldSt[0], o.EdgeCode);
        var oldEdge = new Dictionary<double, Point3d[]>();
        foreach (var st in oldSt)
        {
            var aa = b.GetAppliedAssemblyAtStation(st);
            var l = Extreme(aa, code, -1); var r = Extreme(aa, code, 1);
            if (l == null || r == null) throw new InvalidOperationException("Sin borde " + code + " a ambos lados en la estacion " + st.ToString("F2"));
            oldEdge[Math.Round(st, 4)] = new[] { l.XYZ, r.XYZ };
        }
        var baseAss = (CivAssembly)tr.GetObject(region0.AssemblyId, OpenMode.ForRead); Local(baseAss);
        var baseParts = PartsOf(baseAss, tr);
        var lanes = baseParts.Where(IsLane).ToArray();
        var bands = baseParts.Where(IsBand).ToArray();
        if (lanes.Length != 2 || lanes[0].Side == lanes[1].Side || lanes.Any(l => !l.SubassemblyHookTo.IsNull))
            throw new ArgumentException("Se requiere exactamente un carril de corona por lado (LaneSuperelevationAOR)");
        var laneBySide = lanes.ToDictionary(l => l.Side);
        if (bands.Length > 2 || bands.Select(x => x.Side).Distinct().Count() != bands.Length ||
            bands.Any(x => x.SubassemblyHookTo != laneBySide[x.Side].ObjectId))
            throw new ArgumentException("Las bandas deben ser un LinkWidthAndSlope por lado enganchado al carril");
        if (baseParts.Length != lanes.Length + bands.Length) throw new ArgumentException("El ensamblaje original tiene piezas no soportadas: solo carriles y bandas");
        var bandBySide = bands.ToDictionary(x => x.Side);
        var sideByName = baseParts.ToDictionary(x => x.Name, x => x.Side);
        var oldTargets = region0.GetTargets().Cast<SubassemblyTargetInfo>().Where(t => t.TargetIds != null && t.TargetIds.Count > 0)
            .Select(t => new OldTarget(t.SubassemblyName, t.TargetType.ToString(), t.LogicalName, t.TargetIds.Cast<ObjectId>().ToArray())).ToArray();
        var trans = b.getTransitions().SelectMany(set => Enumerable.Range(0, set.TransitionCount).Select(i => set.GetTransitionAt(i))
            .Select(t => new Transition(set.SubassemblyName, t.ParameterName, t.StartStation, t.EndStation, Convert.ToDouble(t.StartValue), Convert.ToDouble(t.EndValue)))).ToArray();
        if (trans.Any(t => !sideByName.ContainsKey(t.Sub))) throw new ArgumentException("Transicion sobre un subensamblaje que no esta en el ensamblaje original");

        string libraryFolder = o.Library ?? TipologiaContract.DefaultLibrary(App.Version.Major);
        using var laneLib = new Library(libraryFolder, o.LaneAssembly);
        using var curbLib = new Library(libraryFolder, o.CurbAssembly);
        using var slopeLib = slopes ? new Library(libraryFolder, o.SlopeAssembly) : null;
        var libCurb = curbLib.Parts.Where(x => x.Name.StartsWith(o.CurbSubassembly, StringComparison.Ordinal)).ToArray();
        if (libCurb.Length != 2 || libCurb[0].Side == libCurb[1].Side) throw new ArgumentException(o.CurbAssembly + " debe traer un " + o.CurbSubassembly + " por lado");
        var libCurbBySide = libCurb.ToDictionary(x => x.Side);
        if (laneLib.Parts.Count(IsLane) != 2) throw new ArgumentException(o.LaneAssembly + " debe traer dos carriles");
        if (slopes && (slopeLib.Parts.Count(IsLane) != 2 || !slopeLib.Parts.Any(x => !IsLane(x) && !IsBand(x) && !x.Name.StartsWith(o.CurbSubassembly, StringComparison.Ordinal))))
            throw new ArgumentException(o.SlopeAssembly + " debe traer dos carriles y un componente de encuentro al terreno");

        var layer = LayerId(tr, db, o.Layer, baseAss.LayerId);
        var origin = o.Origin == null ? new Point3d(baseAss.Location.X, baseAss.Location.Y - o.Spacing, baseAss.Location.Z) : new Point3d(o.Origin[0], o.Origin[1], o.Origin[2]);
        var variants = new Dictionary<string, ObjectId>(); var variantLog = new List<object>(); int vi = 0;
        var assemblyNames = new HashSet<string>(civil.AssemblyCollection.Cast<ObjectId>().Select(id => ((CivEntity)tr.GetObject(id, OpenMode.ForRead)).Name), StringComparer.OrdinalIgnoreCase);

        ObjectId MakeVariant(string kind)
        {
            if (variants.TryGetValue(kind, out var have)) return have;
            var loc = new Point3d(origin.X + o.Spacing * vi++, origin.Y, origin.Z);
            string name = c.Name + " - tipologia " + kind;
            if (!assemblyNames.Add(name)) throw new ArgumentException("Ya existe el ensamblaje " + name);
            var lib = kind == "talud" ? slopeLib : laneLib;
            var aid = civil.AssemblyCollection.ImportAssembly(name, lib.Db, lib.Assembly.Name, loc);
            var a = (CivAssembly)tr.GetObject(aid, OpenMode.ForWrite);
            a.Description = "CDCRD tipologia " + kind + ": " + Path.GetFileName(lib.File) + (kind == "talud" ? "" : "; bordillo " + o.CurbSubassembly + " de " + Path.GetFileName(curbLib.File)) + ". Espesores de catalogo sin disenar.";
            a.LayerId = layer;
            var parts = PartsOf(a, tr); var log = new List<object>();
            var newLanes = parts.Where(IsLane).ToDictionary(x => x.Side);
            if (newLanes.Count != 2) throw new InvalidOperationException("El ensamblaje importado no trae un carril por lado");
            foreach (var side in new[] { SubassemblySideType.Left, SubassemblySideType.Right })
            {
                var w = (Subassembly)tr.GetObject(newLanes[side].ObjectId, OpenMode.ForWrite);
                w.Name = laneBySide[side].Name; // same names: targets and transitions resolve by subassembly name
                var copy = CopyParams(laneBySide[side], w, LaneKeys, Array.Empty<string>());
                w.LayerId = layer; w.Run();
                log.Add(new { rol = "carril", lado = side.ToString(), parametros = copy, descripcion = Describe(w) });
            }
            foreach (var x in parts.Where(x => !IsLane(x))) { var w = (Subassembly)tr.GetObject(x.ObjectId, OpenMode.ForWrite); w.LayerId = layer; log.Add(new { rol = "paleta", descripcion = Describe(w) }); }
            if (kind != "talud")
                foreach (var side in new[] { SubassemblySideType.Left, SubassemblySideType.Right })
                {
                    var outer = (Subassembly)tr.GetObject(newLanes[side].ObjectId, OpenMode.ForRead);
                    if (bandBySide.TryGetValue(side, out var oldBand))
                    {
                        var sid = civil.SubassemblyCollection.ImportStockSubassembly(oldBand.Name, "Subassembly.LinkWidthAndSlope", loc);
                        var band = (Subassembly)tr.GetObject(sid, OpenMode.ForWrite);
                        band.Side = side; band.LayerId = layer;
                        var copy = CopyParams(oldBand, band, null, new[] { "Side" });
                        var hook = Hook(outer); a.AddSubassembly(sid, hook); band.Run();
                        if (band.AssemblyId != aid || band.SubassemblyHookTo != outer.ObjectId) throw new InvalidOperationException("La banda no quedo enganchada al carril");
                        log.Add(new { rol = "banda", lado = side.ToString(), parametros = copy, enganche = hook.Codes.Cast<string>().ToArray(), descripcion = Describe(band) });
                        outer = band;
                    }
                    bool curb = kind == "LR" || (kind == "L" && side == SubassemblySideType.Left) || (kind == "R" && side == SubassemblySideType.Right);
                    if (!curb) continue;
                    var cid = civil.SubassemblyCollection.ImportStockSubassembly(o.CurbSubassembly + " - " + side, "Subassembly." + o.CurbSubassembly, loc);
                    var cs = (Subassembly)tr.GetObject(cid, OpenMode.ForWrite);
                    cs.Side = side; cs.LayerId = layer;
                    var copyCurb = CopyParams(libCurbBySide[side], cs, null, new[] { "Side" });
                    var curbHook = Hook(outer); a.AddSubassembly(cid, curbHook); cs.Run();
                    if (cs.AssemblyId != aid || cs.SubassemblyHookTo != outer.ObjectId) throw new InvalidOperationException("El bordillo no quedo enganchado");
                    QaCheckpoint?.Invoke("variant-curb-added");
                    log.Add(new { rol = "bordillo", lado = side.ToString(), parametros = copyCurb, enganche = curbHook.Codes.Cast<string>().ToArray(), descripcion = Describe(cs) });
                }
            variants[kind] = aid; variantLog.Add(new { tipo = kind, handle = H(aid), nombre = name, piezas = log });
            return aid;
        }

        // Split the single region at every cut station, then assign variants.
        var regions = new List<BaselineRegion> { region0 };
        for (int i = 1; i < segs.Length; i++) regions.Add(regions[^1].Split(segs[i].From));
        if (b.BaselineRegions.Count != segs.Length) throw new InvalidOperationException("La division no produjo los tramos esperados");
        QaCheckpoint?.Invoke("regions-split");
        for (int i = 0; i < segs.Length; i++)
        {
            regions[i].AssemblyId = MakeVariant(segs[i].Kind);
            regions[i].Name = regionName + " - " + (i + 1).ToString("00") + " " + segs[i].Kind;
        }
        // Targets: every original target must find its equivalent in every region; daylight targets the terrain.
        var used = new HashSet<string>(); int targetsSet = 0;
        foreach (var r in regions)
        {
            var tg = r.GetTargets(); bool changed = false;
            var parts = PartsOf((CivAssembly)tr.GetObject(r.AssemblyId, OpenMode.ForRead), tr).ToDictionary(x => x.Name);
            foreach (SubassemblyTargetInfo t in tg)
            {
                string type = t.TargetType.ToString();
                if (!parts.TryGetValue(t.SubassemblyName, out var part)) throw new InvalidOperationException("Objetivo de un subensamblaje desconocido: " + t.SubassemblyName);
                bool daylight = !IsLane(part) && !IsBand(part) && !part.Name.StartsWith(o.CurbSubassembly, StringComparison.Ordinal);
                if (daylight && type == "Surface") { t.TargetIds = new ObjectIdCollection(new[] { terrain.ObjectId }); changed = true; targetsSet++; continue; }
                var src = oldTargets.Where(x => x.Sub == t.SubassemblyName && x.Type == type && x.Logical == t.LogicalName).ToArray();
                if (src.Length > 1) throw new InvalidOperationException("Objetivo original ambiguo: " + t.SubassemblyName + "/" + t.LogicalName);
                if (src.Length == 0) continue;
                t.TargetIds = new ObjectIdCollection(src[0].Ids); changed = true; targetsSet++; used.Add(src[0].Sub + "\0" + src[0].Type + "\0" + src[0].Logical);
            }
            if (changed) r.SetTargets(tg);
        }
        var orphan = oldTargets.Where(x => !used.Contains(x.Sub + "\0" + x.Type + "\0" + x.Logical)).Select(x => x.Sub + "/" + x.Type + "/" + x.Logical).ToArray();
        if (orphan.Length > 0) throw new InvalidOperationException("Objetivos originales sin equivalente en las variantes: " + string.Join(", ", orphan));
        QaCheckpoint?.Invoke("targets-set");
        // Transitions clipped per region, same subassembly names, values interpolated at the cuts.
        var sets = new List<CorridorTransitionSet>(); int n = 0;
        foreach (var r in regions)
            foreach (var g in trans.GroupBy(t => t.Sub))
            {
                CorridorTransitionSet set = null;
                foreach (var t in g)
                {
                    double a0 = Math.Max(t.S0, r.StartStation), a1 = Math.Min(t.S1, r.EndStation);
                    if (a1 - a0 < 1e-6) continue;
                    double f(double s) => t.V0 + (t.V1 - t.V0) * (s - t.S0) / (t.S1 - t.S0);
                    set ??= new CorridorTransitionSet(g.Key + " R" + (++n), r, g.Key, CorridorTransitionNameType.SubassemblyName);
                    var it = set.AddTransition(t.Param);
                    it.StartStation = a0; it.EndStation = a1; it.StartValue = f(a0); it.EndValue = f(a1); it.TransitionType = CorridorTransitionType.Linear;
                }
                if (set != null) sets.Add(set);
            }
        if (trans.Length > 0) b.SetTransitions(sets);
        var surf = c.CorridorSurfaces[0];
        foreach (var nm in surf.Boundaries.BoundaryNames()) surf.Boundaries.Remove(nm);
        surf.Boundaries.AddCorridorExtentsBoundary(surf.Name + "_Extents");
        c.Rebuild(); QaCheckpoint?.Invoke("corridor-rebuilt");
        ((TinSurface)tr.GetObject(surf.SurfaceId, OpenMode.ForWrite)).Rebuild(); // the Top does not follow the corridor rebuild inside the transaction
        var record = new JsonObject
        {
            ["version"] = 1, ["region_original"] = regionName, ["codigo_borde"] = code, ["tolerancia_m"] = o.Tolerance,
            ["segmentos"] = new JsonArray(segs.Select(s => (JsonNode)new JsonArray(s.From, s.To, s.Kind)).ToArray()),
            ["variantes"] = new JsonObject(variants.Select(v => KeyValuePair.Create(v.Key, (JsonNode)H(v.Value)))),
            ["carriles"] = new JsonObject { ["Left"] = laneBySide[SubassemblySideType.Left].Name, ["Right"] = laneBySide[SubassemblySideType.Right].Name },
            ["bordillo"] = o.CurbSubassembly, ["terreno"] = terrain == null ? null : H(terrain.ObjectId),
            ["biblioteca"] = new JsonObject { ["carriles"] = o.LaneAssembly, ["bordillo"] = o.CurbAssembly, ["talud"] = slopes ? o.SlopeAssembly : null },
            ["objetivos_originales"] = oldTargets.Length, ["transiciones_originales"] = trans.Length
        };
        var verify = Verify(c, tr, record, oldEdge, oldSt);
        Store(c, tr, record); QaCheckpoint?.Invoke("record-written");
        return new
        {
            corredor = H(c.ObjectId), nombre = c.Name, simulacion = sim, biblioteca = libraryFolder, variantes = variantLog,
            regiones = regions.Select((r, i) => new { r.Name, inicio = r.StartStation, fin = r.EndStation, tipo = segs[i].Kind, ensamblaje = H(r.AssemblyId) }).ToArray(),
            objetivos_originales = oldTargets.Length, objetivos_asignados = targetsSet, transiciones_originales = trans.Length, transiciones_recortadas = sets.Sum(s => s.TransitionCount),
            verificacion = verify
        };
    }

    // ---------- reconstruir ----------
    // Civil flags the corridor out of date again when the command that applied the typology
    // ends (its assemblies changed). A rebuild in a command of its own clears it for good.
    private static object Settle(Corridor c, Transaction tr)
    {
        var record = Record(c, tr) as JsonObject ?? throw new ArgumentException("Contrato invalido");
        bool wasOutOfDate = c.IsOutOfDate;
        c.Rebuild();
        ((TinSurface)tr.GetObject(c.CorridorSurfaces[0].SurfaceId, OpenMode.ForWrite)).Rebuild();
        return new { corredor = H(c.ObjectId), nombre = c.Name, estaba_fuera_de_fecha = wasOutOfDate, verificacion = Verify(c, tr, record, null, null) };
    }

    // ---------- verificar ----------
    private static object Verify(Corridor c, Transaction tr, JsonObject record, Dictionary<double, Point3d[]> oldEdge, double[] oldSt)
    {
        var b = c.Baselines[0];
        var regs = b.BaselineRegions.Cast<BaselineRegion>().ToArray();
        var segs = TipologiaContract.ParseSegments(record["segmentos"]);
        if (regs.Length != segs.Length) throw new InvalidOperationException("Regiones distintas del contrato");
        var variants = (JsonObject)record["variantes"];
        for (int i = 0; i < regs.Length; i++)
        {
            if (Math.Abs(regs[i].StartStation - segs[i].From) > 1e-3 || Math.Abs(regs[i].EndStation - segs[i].To) > 1e-3 || H(regs[i].AssemblyId) != variants[segs[i].Kind]?.GetValue<string>())
                throw new InvalidOperationException("Region " + regs[i].Name + " distinta del contrato");
        }
        string code = record["codigo_borde"].GetValue<string>(); double tol = record["tolerancia_m"]?.GetValue<double>() ?? .005;
        TinSurface terrain = record["terreno"] == null ? null : (TinSurface)tr.GetObject(c.Database.GetObjectId(false, new Handle(Convert.ToInt64(record["terreno"].GetValue<string>(), 16)), 0), OpenMode.ForRead);
        int stations = 0, shared = 0, common = 0, curbWant = 0, curbOk = 0, curbExtra = 0, dlN = 0; double xy = 0, z = 0, dl = 0;
        var bad = new List<string>();
        for (int i = 0; i < regs.Length; i++)
        {
            var r = regs[i];
            foreach (var st in r.SortedStations())
            {
                if (i > 0 && Math.Abs(st - r.StartStation) < 1e-6 && Math.Abs(regs[i - 1].EndStation - st) < 1e-6) continue; // counted with the previous region
                var aa = b.GetAppliedAssemblyAtStation(st);
                int owner = i;
                if (i < regs.Length - 1 && Math.Abs(st - r.EndStation) < 1e-6)
                {
                    // Shared boundary: the applied assembly belongs to exactly one of the two neighbours.
                    if (aa.AssemblyId == regs[i + 1].AssemblyId) owner = i + 1;
                    else if (aa.AssemblyId != r.AssemblyId) throw new InvalidOperationException("Ensamblaje aplicado ajeno en la frontera " + st.ToString("F2"));
                    shared++;
                }
                else if (aa.AssemblyId != r.AssemblyId) throw new InvalidOperationException("Ensamblaje aplicado distinto de la region en " + st.ToString("F2"));
                stations++;
                string kind = segs[owner].Kind;
                var eL = Extreme(aa, code, -1); var eR = Extreme(aa, code, 1);
                if (eL == null || eR == null) { if (bad.Count < 20) bad.Add("borde@" + st.ToString("F2")); continue; }
                if (oldEdge != null && oldEdge.TryGetValue(Math.Round(st, 4), out var prev))
                {
                    common++;
                    xy = Math.Max(xy, Math.Max(new Point2d(eL.XYZ.X, eL.XYZ.Y).GetDistanceTo(new Point2d(prev[0].X, prev[0].Y)), new Point2d(eR.XYZ.X, eR.XYZ.Y).GetDistanceTo(new Point2d(prev[1].X, prev[1].Y))));
                    z = Math.Max(z, Math.Max(Math.Abs(eL.XYZ.Z - prev[0].Z), Math.Abs(eR.XYZ.Z - prev[1].Z)));
                }
                foreach (var (side, sign) in new[] { ("L", -1), ("R", 1) })
                {
                    bool want = kind == "LR" || kind == side || kind == "talud";
                    bool has = Extreme(aa, CurbCode, sign) != null;
                    if (want) { curbWant++; if (has) curbOk++; else if (bad.Count < 20) bad.Add("bordillo" + side + "@" + st.ToString("F2")); }
                    else if (has) { curbExtra++; if (bad.Count < 20) bad.Add("bordillo_extra" + side + "@" + st.ToString("F2")); }
                }
                if (kind == "talud")
                    foreach (var sign in new[] { -1, 1 })
                    {
                        var d = Extreme(aa, DaylightCode, sign); dlN++;
                        double err = double.PositiveInfinity;
                        if (d != null && terrain != null) { try { err = Math.Abs(d.XYZ.Z - terrain.FindElevationAtXY(d.XYZ.X, d.XYZ.Y)); } catch (PointNotOnEntityException) { } }
                        dl = Math.Max(dl, err);
                        if (err > tol && bad.Count < 20) bad.Add("talud@" + st.ToString("F2"));
                    }
            }
        }
        var top = (TinSurface)tr.GetObject(c.CorridorSurfaces[0].SurfaceId, OpenMode.ForRead);
        int tri = top.GetTriangles(false).Count;
        var result = new
        {
            regiones = regs.Length, estaciones = stations, fronteras_compartidas = shared, estaciones_comunes = common, estaciones_previas = oldSt?.Length,
            borde_xy_max_m = xy, borde_z_max_m = z, bordillos_esperados = curbWant, bordillos_encontrados = curbOk, bordillos_sobrantes = curbExtra,
            puntos_talud = dlN, talud_vs_terreno_max_m = dlN == 0 ? 0 : dl, triangulos_top = tri, fuera_de_fecha = c.IsOutOfDate, tolerancia_m = tol, fallos = bad
        };
        bool fail = bad.Count > 0 || xy > tol || z > tol || (oldSt != null && common < oldSt.Length * .9) || curbOk != curbWant || curbExtra > 0 || tri == 0 || c.IsOutOfDate || (dlN > 0 && dl > tol);
        if (fail) throw new InvalidOperationException("Verificacion fallida: " + JsonSerializer.Serialize(result));
        return result;
    }
}
