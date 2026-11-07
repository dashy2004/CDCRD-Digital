// Gutter flowlines of a corridor, parts catalog and gravity pipe networks with an explicit contract.
// All writes happen inside one transaction of the active document; simulation aborts it.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.ApplicationServices;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil.DatabaseServices.Styles;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivilApp = Autodesk.Civil.ApplicationServices.CivilApplication;
using CivEntity = Autodesk.Civil.DatabaseServices.Entity;
using CivDBObject = Autodesk.Civil.DatabaseServices.DBObject;

namespace Cdcrd.Drenaje;

internal static class DrenajeService
{
    internal static Action<string> QaCheckpoint = null;
    internal const string RecordName = "CDCRD_DRENAJE_V1";
    private const int MaxRuns = 100, MaxPoints = 50000;

    // ---------- helpers ----------
    private static string H(ObjectId id) => id.IsNull ? null : id.Handle.ToString();
    private static double[] Pt(Point3d p) => new[] { p.X, p.Y, p.Z };
    private static string Text(JsonObject p, string k) => DrenajeContract.Text(p, k);
    private static ObjectId Resolve(Transaction tr, IEnumerable<ObjectId> ids, string key, string what)
    {
        var found = ids.Where(id => string.Equals(H(id), key, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(((CivEntity)tr.GetObject(id, OpenMode.ForRead)).Name, key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (found.Length != 1) throw new ArgumentException(what + " inexistente o ambiguo: " + key);
        return found[0];
    }
    private static ObjectId FromHandle(Database db, string handle)
    {
        try { return db.GetObjectId(false, new Handle(Convert.ToInt64(handle, 16)), 0); }
        catch (Exception) { throw new InvalidOperationException("Objeto del contrato inexistente: " + handle); }
    }
    private static void Local(CivEntity e) { if (e.IsReferenceObject || e.IsCWSReferenceObject) throw new ArgumentException("Se requiere objeto local: " + e.Name); }
    private static ObjectId LayerId(Transaction tr, Database db, string name)
    {
        var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
        if (lt.Has(name)) return lt[name];
        lt.UpgradeOpen(); var rec = new LayerTableRecord { Name = name }; var id = lt.Add(rec); tr.AddNewlyCreatedDBObject(rec, true); return id;
    }
    private static double Dist2d(double[] a, Point3d b) => Math.Sqrt((a[0] - b.X) * (a[0] - b.X) + (a[1] - b.Y) * (a[1] - b.Y));

    // Catalog values carry their own units (the metric catalog stores millimetres); everything is reported in metres.
    private static double ToMetres(double value, string units)
    {
        string u = (units ?? "").Trim().ToLowerInvariant();
        if (u == "" || u == "m" || u == "meter" || u == "meters" || u == "metre" || u == "metres") return value;
        if (u == "mm" || u == "millimeter" || u == "millimeters") return value / 1000;
        if (u == "cm" || u == "centimeter" || u == "centimeters") return value / 100;
        if (u == "in" || u == "inch" || u == "inches") return value * .0254;
        if (u == "ft" || u == "foot" || u == "feet") return value * .3048;
        throw new InvalidOperationException("Unidad de catalogo no reconocida: " + units);
    }
    private static double? Field(PartDataRecord rec, PartContextType ctx)
    {
        if (rec == null || !rec.GetSupportedContexts().Contains(ctx)) return null;
        var f = rec.GetDataFieldBy(ctx);
        if (f?.Value == null) return null;
        try { return ToMetres(Convert.ToDouble(f.Value), f.Units); } catch (FormatException) { return null; } catch (InvalidCastException) { return null; }
    }
    private static string Material(PartDataRecord rec)
    {
        if (rec == null || !rec.GetSupportedContexts().Contains(PartContextType.Material)) return null;
        return rec.GetDataFieldBy(PartContextType.Material)?.Value?.ToString();
    }
    private static object DescribeSize(Transaction tr, ObjectId sizeId)
    {
        var size = (PartSize)tr.GetObject(sizeId, OpenMode.ForRead);
        var rec = size.SizeDataRecord;
        return new
        {
            handle = H(sizeId), nombre = size.Name, material = Material(rec),
            diametro_interior_m = Field(rec, PartContextType.PipeInnerDiameter), ancho_interior_m = Field(rec, PartContextType.PipeInnerWidth) ?? Field(rec, PartContextType.StructInnerWidth),
            alto_interior_m = Field(rec, PartContextType.PipeInnerHeight), espesor_pared_m = Field(rec, PartContextType.WallThickness),
            diametro_interior_estructura_m = Field(rec, PartContextType.StructInnerDiameter), largo_interior_m = Field(rec, PartContextType.StructInnerLength),
            rasante_a_fondo_m = Field(rec, PartContextType.StructRimToSumpHeight), altura_m = Field(rec, PartContextType.StructHeight)
        };
    }
    private static object DescribeFamily(Transaction tr, ObjectId famId)
    {
        var f = (PartFamily)tr.GetObject(famId, OpenMode.ForRead);
        return new
        {
            handle = H(famId), nombre = f.Name, descripcion = f.Description, dominio = f.Domain.ToString(), tipo = f.PartType.ToString(),
            forma = f.BoundingShape.ToString(), tamanios = Enumerable.Range(0, f.PartSizeCount).Select(i => DescribeSize(tr, f[i])).ToArray()
        };
    }
    private static PartsList ResolvePartsList(Transaction tr, CivilDocument civil, string key)
    {
        var ids = civil.Styles.PartsListSet.Cast<ObjectId>().ToArray();
        if (ids.Length == 0) throw new ArgumentException("El dibujo no tiene listas de partes");
        if (key == null)
        {
            if (ids.Length != 1) throw new ArgumentException("Varias listas de partes; indique lista_partes: " + string.Join(", ", ids.Select(id => ((PartsList)tr.GetObject(id, OpenMode.ForRead)).Name)));
            return (PartsList)tr.GetObject(ids[0], OpenMode.ForRead);
        }
        var found = ids.Where(id => string.Equals(H(id), key, StringComparison.OrdinalIgnoreCase) || string.Equals(((PartsList)tr.GetObject(id, OpenMode.ForRead)).Name, key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (found.Length != 1) throw new ArgumentException("Lista de partes inexistente o ambigua: " + key);
        return (PartsList)tr.GetObject(found[0], OpenMode.ForRead);
    }
    // Exact name/description/handle first; otherwise a single case-insensitive substring match.
    private static ObjectId ResolveFamily(Transaction tr, PartsList pl, DomainType domain, string key)
    {
        var ids = pl.GetPartFamilyIdsByDomain(domain).Cast<ObjectId>().ToArray();
        var fams = ids.Select(id => (id, f: (PartFamily)tr.GetObject(id, OpenMode.ForRead))).ToArray();
        var exact = fams.Where(x => string.Equals(H(x.id), key, StringComparison.OrdinalIgnoreCase) || string.Equals(x.f.Name, key, StringComparison.OrdinalIgnoreCase) || string.Equals(x.f.Description, key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (exact.Length == 1) return exact[0].id;
        var partial = fams.Where(x => (x.f.Name ?? "").Contains(key, StringComparison.OrdinalIgnoreCase) || (x.f.Description ?? "").Contains(key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (partial.Length == 1) return partial[0].id;
        throw new ArgumentException("Familia de " + domain + " inexistente o ambigua en " + pl.Name + ": " + key + " (hay " + string.Join(", ", fams.Select(x => x.f.Name)) + ")");
    }
    private static ObjectId ResolveStructureSize(Transaction tr, ObjectId famId, string key)
    {
        var f = (PartFamily)tr.GetObject(famId, OpenMode.ForRead);
        if (f.PartSizeCount == 0) throw new ArgumentException("Familia sin tamanios: " + f.Name);
        if (key == null) return f[0];
        var sizes = Enumerable.Range(0, f.PartSizeCount).Select(i => f[i]).ToArray();
        var found = sizes.Where(id => string.Equals(H(id), key, StringComparison.OrdinalIgnoreCase) || string.Equals(((PartSize)tr.GetObject(id, OpenMode.ForRead)).Name, key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (found.Length != 1) throw new ArgumentException("Tamanio inexistente o ambiguo en " + f.Name + ": " + key);
        return found[0];
    }
    private static ObjectId ResolvePipeSize(Transaction tr, ObjectId famId, double diameter)
    {
        var f = (PartFamily)tr.GetObject(famId, OpenMode.ForRead);
        var matches = Enumerable.Range(0, f.PartSizeCount).Select(i => f[i])
            .Where(id => { var d = Field(((PartSize)tr.GetObject(id, OpenMode.ForRead)).SizeDataRecord, PartContextType.PipeInnerDiameter); return d.HasValue && Math.Abs(d.Value - diameter) < 5e-4; }).ToArray();
        if (matches.Length != 1) throw new ArgumentException("Sin tamanio unico de diametro interior " + (diameter * 1000).ToString("F0") + " mm en " + f.Name + "; consultar catalogo");
        return matches[0];
    }

    private static JsonObject Record(Network n, Transaction tr)
    {
        if (n.ExtensionDictionary.IsNull) throw new ArgumentException("Red sin contrato propio");
        var d = (DBDictionary)tr.GetObject(n.ExtensionDictionary, OpenMode.ForRead);
        if (!d.Contains(RecordName)) throw new ArgumentException("Red sin contrato " + RecordName);
        var x = (Xrecord)tr.GetObject(d.GetAt(RecordName), OpenMode.ForRead);
        return JsonNode.Parse(string.Concat(x.Data.AsArray().Select(v => (string)v.Value))) as JsonObject ?? throw new ArgumentException("Contrato invalido");
    }
    private static void Store(Network n, Transaction tr, JsonNode data)
    {
        if (n.ExtensionDictionary.IsNull) n.CreateExtensionDictionary();
        var dict = (DBDictionary)tr.GetObject(n.ExtensionDictionary, OpenMode.ForWrite);
        if (dict.Contains(RecordName)) throw new ArgumentException("La red ya tiene contrato; no reemplazar");
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
        if (!new[] { "catalogo", "cuneta", "crear", "verificar" }.Contains(action)) throw new ArgumentException("Accion desconocida");
        bool write = action == "crear", sim = write && (p["simular"]?.GetValue<bool>() ?? true);
        if (write && (Environment.GetEnvironmentVariable("CDCRD_C3D_SOLO_LECTURA") == "1" || Environment.GetEnvironmentVariable("CDCRD_C3D_PERMITIR_COMANDOS") != "1"))
            throw new InvalidOperationException("Escritura/comandos deshabilitados");
        using (doc.LockDocument())
        using (var tr = doc.Database.TransactionManager.StartTransaction())
        {
            var civil = CivilApp.ActiveDocument;
            object result = action switch
            {
                "catalogo" => Catalog(tr, civil, DrenajeContract.Text(p, "lista_partes", false)),
                "cuneta" => Gutter(tr, civil, Text(p, "corredor"), DrenajeContract.Text(p, "codigo", false, 60) ?? "Flowline_Gutter"),
                "crear" => Create(tr, doc.Database, civil, DrenajeContract.ParseCreate(p), sim),
                _ => VerifyNetwork(tr, doc.Database, civil, Text(p, "red"))
            };
            if (write && !sim) { tr.Commit(); committed = true; } else tr.Abort();
            return result;
        }
    }

    // ---------- catalogo ----------
    private static object Catalog(Transaction tr, CivilDocument civil, string key)
    {
        var lists = civil.Styles.PartsListSet.Cast<ObjectId>().Select(id => (PartsList)tr.GetObject(id, OpenMode.ForRead))
            .Where(pl => key == null || string.Equals(pl.Name, key, StringComparison.OrdinalIgnoreCase) || string.Equals(H(pl.ObjectId), key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (key != null && lists.Length == 0) throw new ArgumentException("Lista de partes inexistente: " + key);
        var networks = civil.GetPipeNetworkIds().Cast<ObjectId>().Select(id => (Network)tr.GetObject(id, OpenMode.ForRead)).Select(n => new
        {
            handle = H(n.ObjectId), nombre = n.Name, lista_partes = n.PartsListName, tuberias = n.GetPipeIds().Count, estructuras = n.GetStructureIds().Count,
            contrato = !n.ExtensionDictionary.IsNull && ((DBDictionary)tr.GetObject(n.ExtensionDictionary, OpenMode.ForRead)).Contains(RecordName)
        }).ToArray();
        return new
        {
            listas_partes = lists.Select(pl => new
            {
                handle = H(pl.ObjectId), nombre = pl.Name,
                tuberias = pl.GetPartFamilyIdsByDomain(DomainType.Pipe).Cast<ObjectId>().Select(id => DescribeFamily(tr, id)).ToArray(),
                estructuras = pl.GetPartFamilyIdsByDomain(DomainType.Structure).Cast<ObjectId>().Select(id => DescribeFamily(tr, id)).ToArray()
            }).ToArray(),
            redes = networks
        };
    }

    // ---------- cuneta ----------
    // Feature lines of the main baseline carrying the gutter code; one run per feature line, with its side.
    private static object Gutter(Transaction tr, CivilDocument civil, string corridorKey, string code)
    {
        var c = (Corridor)tr.GetObject(Resolve(tr, civil.CorridorCollection, corridorKey, "corredor"), OpenMode.ForRead);
        Local(c);
        if (c.IsOutOfDate) throw new ArgumentException("Corredor fuera de fecha: reconstruir antes de leer la cuneta");
        var runs = new List<object>(); int points = 0; var codes = new SortedSet<string>(StringComparer.Ordinal);
        foreach (Baseline b in c.Baselines)
        {
            var map = b.MainBaselineFeatureLines.FeatureLineCollectionMap;
            foreach (var name in map.CodeNames()) codes.Add(name);
            if (!map.CodeNames().Contains(code)) continue;
            var col = map[code]; int index = 0;
            foreach (CorridorFeatureLine fl in col)
            {
                var pts = fl.FeatureLinePoints.Cast<FeatureLinePoint>().Select(fp => new { estacion = fp.Station, desplazamiento = fp.Offset, xyz = Pt(fp.XYZ) }).OrderBy(x => x.estacion).ToArray();
                if (pts.Length < 2) continue;
                points += pts.Length;
                if (runs.Count >= MaxRuns || points > MaxPoints) throw new ArgumentException("Presupuesto de lineas/puntos de cuneta excedido");
                if (pts.Any(x => x.xyz.Any(v => !double.IsFinite(v)))) throw new InvalidOperationException("Cuneta con coordenadas no finitas");
                bool left = pts.All(x => x.desplazamiento < -1e-6), right = pts.All(x => x.desplazamiento > 1e-6);
                if (!left && !right) throw new InvalidOperationException("Linea " + code + " que cruza el eje de la baseline " + b.Name);
                runs.Add(new { baseline = b.Name, lado = left ? "izq" : "der", indice = index++, estacion_inicio = pts[0].estacion, estacion_fin = pts[^1].estacion, puntos = pts });
            }
        }
        if (runs.Count == 0) throw new ArgumentException("El corredor no tiene lineas " + code + " (codigos: " + string.Join(", ", codes) + ")");
        return new { corredor = H(c.ObjectId), nombre = c.Name, codigo = code, baselines = c.Baselines.Count, lineas = runs.Count, puntos = points, codigos_disponibles = codes.ToArray(), cunetas = runs };
    }

    // ---------- crear ----------
    private static object Create(Transaction tr, Database db, CivilDocument civil, CreateOptions o, bool sim)
    {
        if (civil.GetPipeNetworkIds().Cast<ObjectId>().Any(id => string.Equals(((Network)tr.GetObject(id, OpenMode.ForRead)).Name, o.Name, StringComparison.OrdinalIgnoreCase)))
            throw new ArgumentException("Ya existe la red " + o.Name);
        var pl = ResolvePartsList(tr, civil, o.PartsList);
        var layer = LayerId(tr, db, o.Layer);
        // Resolve every family and size before creating anything.
        var structFam = o.Structures.ToDictionary(s => s.Id, s => ResolveFamily(tr, pl, DomainType.Structure, s.Family));
        var structSize = o.Structures.ToDictionary(s => s.Id, s => ResolveStructureSize(tr, structFam[s.Id], s.Size));
        var pipeFam = o.Pipes.ToDictionary(x => x.Id, x => ResolveFamily(tr, pl, DomainType.Pipe, x.Family));
        var pipeSize = o.Pipes.ToDictionary(x => x.Id, x => ResolvePipeSize(tr, pipeFam[x.Id], x.Diameter));
        string name = o.Name;
        var nid = Network.Create(civil, ref name);
        var net = (Network)tr.GetObject(nid, OpenMode.ForWrite);
        if (!string.Equals(name, o.Name, StringComparison.Ordinal)) throw new InvalidOperationException("Civil cambio el nombre de la red a " + name);
        net.PartsListId = pl.ObjectId; net.LayerId = layer;
        QaCheckpoint?.Invoke("network-created");
        var structIds = new Dictionary<string, ObjectId>();
        foreach (var s in o.Structures)
        {
            ObjectId sid = ObjectId.Null;
            net.AddStructure(structFam[s.Id], structSize[s.Id], new Point3d(s.Xyz[0], s.Xyz[1], s.Rim), s.Rotation, ref sid, false);
            if (sid.IsNull) throw new InvalidOperationException("Civil no creo la estructura " + s.Id);
            var st = (Structure)tr.GetObject(sid, OpenMode.ForWrite);
            st.LayerId = layer; st.RimElevation = s.Rim; st.ControlSumpBy = StructureControlSumpType.ByElevation; st.SumpElevation = s.SumpElevation;
            st.Description = "CDCRD " + s.Kind + " " + s.Id;
            structIds[s.Id] = sid;
        }
        QaCheckpoint?.Invoke("structures-added");
        var pipeIds = new Dictionary<string, ObjectId>();
        var byId = o.Structures.ToDictionary(s => s.Id);
        foreach (var x in o.Pipes)
        {
            var a = byId[x.From]; var b = byId[x.To];
            // Pipe points are centreline points: invert + inner radius.
            var seg = new LineSegment3d(new Point3d(a.Xyz[0], a.Xyz[1], x.StartInvert + x.Diameter / 2), new Point3d(b.Xyz[0], b.Xyz[1], x.EndInvert + x.Diameter / 2));
            ObjectId pid = ObjectId.Null;
            net.AddLinePipe(pipeFam[x.Id], pipeSize[x.Id], seg, ref pid, false);
            if (pid.IsNull) throw new InvalidOperationException("Civil no creo la tuberia " + x.Id);
            var pipe = (Pipe)tr.GetObject(pid, OpenMode.ForWrite);
            pipe.LayerId = layer; pipe.Description = "CDCRD " + x.Id;
            pipeIds[x.Id] = pid;
        }
        QaCheckpoint?.Invoke("pipes-added");
        foreach (var x in o.Pipes)
        {
            var pipe = (Pipe)tr.GetObject(pipeIds[x.Id], OpenMode.ForWrite);
            pipe.ConnectToStructure(ConnectorPositionType.Start, structIds[x.From], false);
            pipe.ConnectToStructure(ConnectorPositionType.End, structIds[x.To], false);
        }
        QaCheckpoint?.Invoke("pipes-connected");
        var record = new JsonObject
        {
            ["version"] = 1, ["nombre"] = o.Name, ["capa"] = o.Layer, ["lista_partes"] = pl.Name, ["pendiente_min"] = o.MinSlope, ["profundidad_min_m"] = o.MinCover, ["tolerancia_m"] = o.Tolerance,
            ["estructuras"] = new JsonArray(o.Structures.Select(s => (JsonNode)new JsonObject
            {
                ["id"] = s.Id, ["tipo"] = s.Kind, ["handle"] = H(structIds[s.Id]), ["familia"] = ((PartFamily)tr.GetObject(structFam[s.Id], OpenMode.ForRead)).Name,
                ["tamanio"] = ((PartSize)tr.GetObject(structSize[s.Id], OpenMode.ForRead)).Name, ["xyz"] = new JsonArray(s.Xyz[0], s.Xyz[1], s.Xyz[2]),
                ["rasante"] = s.Rim, ["cota_fondo"] = s.SumpElevation, ["rotacion"] = s.Rotation
            }).ToArray()),
            ["tuberias"] = new JsonArray(o.Pipes.Select(x => (JsonNode)new JsonObject
            {
                ["id"] = x.Id, ["handle"] = H(pipeIds[x.Id]), ["desde"] = x.From, ["hasta"] = x.To, ["familia"] = ((PartFamily)tr.GetObject(pipeFam[x.Id], OpenMode.ForRead)).Name,
                ["tamanio"] = ((PartSize)tr.GetObject(pipeSize[x.Id], OpenMode.ForRead)).Name, ["diametro_m"] = x.Diameter, ["cota_inicio"] = x.StartInvert, ["cota_fin"] = x.EndInvert
            }).ToArray())
        };
        var verification = Verify(tr, db, net, record);
        Store(net, tr, record); QaCheckpoint?.Invoke("record-written");
        return new { red = sim ? null : H(nid), nombre = o.Name, simulacion = sim, capa = o.Layer, lista_partes = pl.Name, estructuras = o.Structures.Length, tuberias = o.Pipes.Length, verificacion = verification };
    }

    // ---------- verificar ----------
    private static object VerifyNetwork(Transaction tr, Database db, CivilDocument civil, string key)
    {
        var net = (Network)tr.GetObject(Resolve(tr, civil.GetPipeNetworkIds().Cast<ObjectId>(), key, "red"), OpenMode.ForRead);
        Local(net);
        return Verify(tr, db, net, Record(net, tr));
    }

    // Re-reads every structure and pipe named in the contract and compares geometry, sizes, connectivity, layer and rules.
    private static object Verify(Transaction tr, Database db, Network net, JsonObject record)
    {
        double tol = record["tolerancia_m"].GetValue<double>(), minSlope = record["pendiente_min"].GetValue<double>(), minCover = record["profundidad_min_m"].GetValue<double>();
        string layer = record["capa"].GetValue<string>();
        var bad = new List<string>();
        void Fail(string s) { if (bad.Count < 40) bad.Add(s); }
        var structs = ((JsonArray)record["estructuras"]).Cast<JsonObject>().ToArray();
        var pipes = ((JsonArray)record["tuberias"]).Cast<JsonObject>().ToArray();
        var netStructs = new HashSet<ObjectId>(net.GetStructureIds().Cast<ObjectId>());
        var netPipes = new HashSet<ObjectId>(net.GetPipeIds().Cast<ObjectId>());
        if (netStructs.Count != structs.Length) Fail("estructuras en la red " + netStructs.Count + " != contrato " + structs.Length);
        if (netPipes.Count != pipes.Length) Fail("tuberias en la red " + netPipes.Count + " != contrato " + pipes.Length);
        if (!string.Equals(net.PartsListName, record["lista_partes"].GetValue<string>(), StringComparison.Ordinal)) Fail("lista de partes " + net.PartsListName);
        double xyMax = 0, rimMax = 0, sumpMax = 0, invMax = 0, slopeMin = double.PositiveInfinity, coverMin = double.PositiveInfinity, diamMax = 0;
        var structRows = new List<object>(); var byId = new Dictionary<string, (Structure st, JsonObject spec)>();
        foreach (var s in structs)
        {
            string id = s["id"].GetValue<string>();
            var oid = FromHandle(db, s["handle"].GetValue<string>());
            if (!netStructs.Contains(oid)) { Fail("estructura " + id + " no pertenece a la red"); continue; }
            var st = (Structure)tr.GetObject(oid, OpenMode.ForRead);
            var xyz = ((JsonArray)s["xyz"]).Select(n => n.GetValue<double>()).ToArray();
            double exy = Dist2d(xyz, st.Position), erim = Math.Abs(st.RimElevation - s["rasante"].GetValue<double>()), esump = Math.Abs(st.SumpElevation - s["cota_fondo"].GetValue<double>());
            xyMax = Math.Max(xyMax, exy); rimMax = Math.Max(rimMax, erim); sumpMax = Math.Max(sumpMax, esump);
            if (exy > tol) Fail("posicion de " + id + " " + exy.ToString("R"));
            if (erim > tol) Fail("rasante de " + id + " " + erim.ToString("R"));
            if (esump > tol) Fail("fondo de " + id + " " + esump.ToString("R"));
            if (!string.Equals(st.PartFamilyName, s["familia"].GetValue<string>(), StringComparison.Ordinal) || !string.Equals(st.PartSizeName, s["tamanio"].GetValue<string>(), StringComparison.Ordinal)) Fail("familia/tamanio de " + id);
            if (!string.Equals(st.Layer, layer, StringComparison.OrdinalIgnoreCase)) Fail("capa de " + id + " " + st.Layer);
            int expected = pipes.Count(x => x["desde"].GetValue<string>() == id || x["hasta"].GetValue<string>() == id);
            if (st.ConnectedPipesCount != expected) Fail("conexiones de " + id + " " + st.ConnectedPipesCount + " != " + expected);
            // The largest connected pipe must fit the structure: its outer diameter against the largest inner dimension.
            double inner = Math.Max(st.InnerDiameterOrWidth, st.InnerLength), largest = 0;
            for (int k = 0; k < st.ConnectedPipesCount; k++) largest = Math.Max(largest, ((Pipe)tr.GetObject(st.ConnectedPipe[k], OpenMode.ForRead)).OuterDiameterOrWidth);
            if (largest > inner + tol) Fail("tuberia de " + largest.ToString("F3") + " m no cabe en " + id + " (interior " + inner.ToString("F3") + " m)");
            byId[id] = (st, s);
            structRows.Add(new { id, handle = H(oid), nombre = st.Name, tipo = s["tipo"].GetValue<string>(), posicion = Pt(st.Position), rasante = st.RimElevation, cota_fondo = st.SumpElevation, conexiones = st.ConnectedPipesCount, interior_max_m = inner, tuberia_exterior_max_m = largest, familia = st.PartFamilyName, tamanio = st.PartSizeName });
        }
        var pipeRows = new List<object>();
        foreach (var x in pipes)
        {
            string id = x["id"].GetValue<string>(), from = x["desde"].GetValue<string>(), to = x["hasta"].GetValue<string>();
            var oid = FromHandle(db, x["handle"].GetValue<string>());
            if (!netPipes.Contains(oid)) { Fail("tuberia " + id + " no pertenece a la red"); continue; }
            var pipe = (Pipe)tr.GetObject(oid, OpenMode.ForRead);
            double d = x["diametro_m"].GetValue<double>(), a = x["cota_inicio"].GetValue<double>(), b = x["cota_fin"].GetValue<double>();
            double invStart = pipe.StartPoint.Z - pipe.InnerDiameterOrWidth / 2, invEnd = pipe.EndPoint.Z - pipe.InnerDiameterOrWidth / 2;
            double einv = Math.Max(Math.Abs(invStart - a), Math.Abs(invEnd - b)), ed = Math.Abs(pipe.InnerDiameterOrWidth - d);
            invMax = Math.Max(invMax, einv); diamMax = Math.Max(diamMax, ed);
            if (einv > tol) Fail("cotas de " + id + " " + einv.ToString("R"));
            if (ed > 1e-3) Fail("diametro de " + id + " " + pipe.InnerDiameterOrWidth.ToString("R"));
            double len = Math.Sqrt(Math.Pow(pipe.EndPoint.X - pipe.StartPoint.X, 2) + Math.Pow(pipe.EndPoint.Y - pipe.StartPoint.Y, 2));
            double slope = len > 1e-9 ? (invStart - invEnd) / len : double.NaN;
            if (!double.IsFinite(slope)) Fail("tuberia " + id + " sin longitud en planta");
            else { slopeMin = Math.Min(slopeMin, slope); if (slope < minSlope - 1e-9) Fail("pendiente de " + id + " " + slope.ToString("R")); }
            if (!byId.TryGetValue(from, out var sa) || !byId.TryGetValue(to, out var sb)) { Fail("extremos de " + id + " sin estructura"); continue; }
            if (pipe.StartStructureId != sa.st.ObjectId || pipe.EndStructureId != sb.st.ObjectId) Fail("conectividad de " + id);
            double exyA = Dist2d(Pt(sa.st.Position), pipe.StartPoint), exyB = Dist2d(Pt(sb.st.Position), pipe.EndPoint);
            xyMax = Math.Max(xyMax, Math.Max(exyA, exyB));
            if (exyA > tol || exyB > tol) Fail("extremos en planta de " + id + " " + Math.Max(exyA, exyB).ToString("R"));
            // Cover is measured to the inner crown, as designed; the outer-crown value is reported alongside.
            double cover = Math.Min(sa.st.RimElevation - (invStart + pipe.InnerDiameterOrWidth), sb.st.RimElevation - (invEnd + pipe.InnerDiameterOrWidth));
            double outerCover = cover - (pipe.OuterDiameterOrWidth - pipe.InnerDiameterOrWidth) / 2;
            coverMin = Math.Min(coverMin, cover);
            if (cover < minCover - tol) Fail("profundidad sobre clave de " + id + " " + cover.ToString("R"));
            if (sa.st.SumpElevation > invStart + tol || sb.st.SumpElevation > invEnd + tol) Fail("fondo de estructura sobre el radier de " + id);
            if (!string.Equals(pipe.PartFamilyName, x["familia"].GetValue<string>(), StringComparison.Ordinal) || !string.Equals(pipe.PartSizeName, x["tamanio"].GetValue<string>(), StringComparison.Ordinal)) Fail("familia/tamanio de " + id);
            if (!string.Equals(pipe.Layer, layer, StringComparison.OrdinalIgnoreCase)) Fail("capa de " + id + " " + pipe.Layer);
            pipeRows.Add(new { id, handle = H(oid), nombre = pipe.Name, desde = from, hasta = to, diametro_interior_m = pipe.InnerDiameterOrWidth, diametro_exterior_m = pipe.OuterDiameterOrWidth, cota_inicio = invStart, cota_fin = invEnd, longitud_2d_m = len, pendiente = double.IsFinite(slope) ? slope : (double?)null, pendiente_nativa = pipe.Slope, profundidad_clave_min_m = cover, profundidad_clave_exterior_min_m = outerCover, familia = pipe.PartFamilyName, tamanio = pipe.PartSizeName, flujo = pipe.FlowDirection.ToString() });
        }
        var result = new
        {
            red = H(net.ObjectId), nombre = net.Name, capa = layer, estructuras = structRows.Count, tuberias = pipeRows.Count,
            posicion_max_m = xyMax, rasante_max_m = rimMax, fondo_max_m = sumpMax, radier_max_m = invMax, diametro_max_m = diamMax,
            pendiente_min = double.IsFinite(slopeMin) ? slopeMin : (double?)null, profundidad_clave_min_m = double.IsFinite(coverMin) ? coverMin : (double?)null,
            pendiente_min_exigida = minSlope, profundidad_min_exigida_m = minCover, tolerancia_m = tol, fallos = bad, detalle_estructuras = structRows, detalle_tuberias = pipeRows
        };
        if (bad.Count > 0) throw new InvalidOperationException("Verificacion fallida: " + JsonSerializer.Serialize(result));
        return result;
    }
}
