// Pressure parts lists, surface elevations and pressure pipe networks with an explicit contract.
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
using AcDBObject = Autodesk.AutoCAD.DatabaseServices.DBObject;

namespace Cdcrd.Presion;

internal static class PresionService
{
    internal static Action<string> QaCheckpoint = null;
    internal const string RecordName = "CDCRD_PRESION_V1";
    private const int MaxPoints = 5000;
    private static readonly PressurePartContextType[] Props =
    {
        PressurePartContextType.DiameterNominal, PressurePartContextType.PipeDiamterInside, PressurePartContextType.PipeDiameterOutside,
        PressurePartContextType.PipeCutLength, PressurePartContextType.FittingAngle, PressurePartContextType.FittingBranchAngle1,
        PressurePartContextType.ConnectionPointCount, PressurePartContextType.IdMaterial, PressurePartContextType.PressureClass,
        PressurePartContextType.CompatibleStandard, PressurePartContextType.PartFamilyName, PressurePartContextType.AppurtIdSize
    };

    // ---------- helpers ----------
    private static string H(ObjectId id) => id.IsNull ? null : id.Handle.ToString();
    private static double[] Pt(Point3d p) => new[] { p.X, p.Y, p.Z };
    private static string Text(JsonObject p, string k) => PresionContract.Text(p, k);
    private static ObjectId FromHandle(Database db, string handle)
    {
        try { return db.GetObjectId(false, new Handle(Convert.ToInt64(handle, 16)), 0); }
        catch (Exception) { throw new InvalidOperationException("Objeto del contrato inexistente: " + handle); }
    }
    private static ObjectId LayerId(Transaction tr, Database db, string name)
    {
        var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
        if (lt.Has(name)) return lt[name];
        lt.UpgradeOpen(); var rec = new LayerTableRecord { Name = name }; var id = lt.Add(rec); tr.AddNewlyCreatedDBObject(rec, true); return id;
    }
    private static double Dist2d(double[] a, Point3d b) => Math.Sqrt((a[0] - b.X) * (a[0] - b.X) + (a[1] - b.Y) * (a[1] - b.Y));
    private static double Dist3d(double[] a, Point3d b) => Math.Sqrt((a[0] - b.X) * (a[0] - b.X) + (a[1] - b.Y) * (a[1] - b.Y) + (a[2] - b.Z) * (a[2] - b.Z));
    private static double? Num(object v)
    {
        if (v == null) return null;
        try { return Convert.ToDouble(v, System.Globalization.CultureInfo.InvariantCulture); } catch (Exception) { return null; }
    }
    private static object Prop(PressurePartSize s, PressurePartContextType t)
    {
        try { var v = s.GetProperty(t); return v is string || v == null ? v : (object)Num(v) ?? v.ToString(); } catch (Exception) { return null; }
    }
    // The catalog's nominal diameter is a text such as "6 in x 6 in x 4 in": the first number is the run, the last the branch.
    private static double[] Nominals(PressurePartSize s)
    {
        var text = Prop(s, PressurePartContextType.DiameterNominal)?.ToString() ?? "";
        return System.Text.RegularExpressions.Regex.Matches(text, @"[0-9]+(?:\.[0-9]+)?").Select(m => double.Parse(m.Value, System.Globalization.CultureInfo.InvariantCulture)).ToArray();
    }
    private static object DescribeSize(PressurePartSize s) => new
    {
        guid = s.PartSizeGuid, familia_guid = s.FamilyGuid, descripcion = s.Description, tipo = s.PartType.ToString(), dominio = s.Domain.ToString(),
        propiedades = Props.ToDictionary(t => t.ToString(), t => Prop(s, t))
    };
    private static PressurePartList ResolvePartsList(Transaction tr, Database db, string key)
    {
        var ids = PressurePartList.GetAvailablePartLists(db).Cast<ObjectId>().ToArray();
        if (ids.Length == 0) throw new ArgumentException("El dibujo no tiene listas de partes de presion");
        var lists = ids.Select(id => (PressurePartList)tr.GetObject(id, OpenMode.ForRead)).ToArray();
        if (key == null)
        {
            if (lists.Length != 1) throw new ArgumentException("Varias listas de partes de presion; indique lista_partes: " + string.Join(", ", lists.Select(l => l.Name)));
            return lists[0];
        }
        var found = lists.Where(l => string.Equals(H(l.ObjectId), key, StringComparison.OrdinalIgnoreCase) || string.Equals(l.Name, key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (found.Length != 1) throw new ArgumentException("Lista de partes de presion inexistente o ambigua: " + key);
        return found[0];
    }
    private static bool FamilyMatches(PressurePartSize s, string key) =>
        string.Equals(s.Description, key, StringComparison.OrdinalIgnoreCase) || string.Equals(s.PartSizeGuid, key, StringComparison.OrdinalIgnoreCase) ||
        string.Equals(s.FamilyGuid, key, StringComparison.OrdinalIgnoreCase) || (s.Description ?? "").Contains(key, StringComparison.OrdinalIgnoreCase);
    // Parts are chosen by type, a description fragment, the catalog's nominal diameter (its own units) and, for fittings, the angle.
    private static PressurePartSize ResolvePart(PressurePartList pl, string domain, string partType, string family, double? nominal, double? nominal2, double? angle, string what)
    {
        var dom = domain == "Fitting" ? PressurePartDomainType.Fitting : domain == "Appurtenance" ? PressurePartDomainType.Appurtenance : PressurePartDomainType.Pipe;
        var all = pl.GetParts(dom);
        var typed = partType == null ? all : all.Where(s => s.PartType.ToString() == partType).ToList();
        var exact = typed.Where(s => string.Equals(s.Description, family, StringComparison.OrdinalIgnoreCase) || string.Equals(s.PartSizeGuid, family, StringComparison.OrdinalIgnoreCase)).ToList();
        if (exact.Count == 1) return exact[0];
        var cand = typed.Where(s => FamilyMatches(s, family)).ToList();
        if (nominal.HasValue) cand = cand.Where(s => { var n = Nominals(s); return n.Length > 0 && Math.Abs(n[0] - nominal.Value) < 1e-3; }).ToList();
        if (nominal2.HasValue) cand = cand.Where(s => { var n = Nominals(s); return n.Length > 1 && Math.Abs(n[^1] - nominal2.Value) < 1e-3; }).ToList();
        if (angle.HasValue) cand = cand.Where(s => Num(Prop(s, PressurePartContextType.FittingAngle)) is double a && Math.Abs(a - angle.Value) < .5).ToList();
        if (cand.Count == 1) return cand[0];
        string offer = string.Join(" | ", typed.Take(60).Select(s => s.Description + " [DN " + Prop(s, PressurePartContextType.DiameterNominal) + (Prop(s, PressurePartContextType.FittingAngle) != null ? ", ang " + Prop(s, PressurePartContextType.FittingAngle) : "") + "]"));
        throw new ArgumentException("Pieza de " + what + " " + (cand.Count == 0 ? "inexistente" : "ambigua (" + cand.Count + ")") + " en " + pl.Name + ": " + family + (nominal.HasValue ? " DN " + nominal : "") + (nominal2.HasValue ? " x " + nominal2 : "") + (angle.HasValue ? " ang " + angle : "") + " (disponibles: " + offer + ")");
    }
    private static TinSurface ResolveSurface(Transaction tr, CivilDocument civil, string key)
    {
        var found = civil.GetSurfaceIds().Cast<ObjectId>().Where(id => string.Equals(H(id), key, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(((CivEntity)tr.GetObject(id, OpenMode.ForRead)).Name, key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (found.Length != 1) throw new ArgumentException("Superficie inexistente o ambigua: " + key);
        return tr.GetObject(found[0], OpenMode.ForRead) as TinSurface ?? throw new ArgumentException("La superficie no es TIN: " + key);
    }
    private static JsonObject Record(AcDBObject n, Transaction tr)
    {
        if (n.ExtensionDictionary.IsNull) throw new ArgumentException("Red sin contrato propio");
        var d = (DBDictionary)tr.GetObject(n.ExtensionDictionary, OpenMode.ForRead);
        if (!d.Contains(RecordName)) throw new ArgumentException("Red sin contrato " + RecordName);
        var x = (Xrecord)tr.GetObject(d.GetAt(RecordName), OpenMode.ForRead);
        return JsonNode.Parse(string.Concat(x.Data.AsArray().Select(v => (string)v.Value))) as JsonObject ?? throw new ArgumentException("Contrato invalido");
    }
    private static void Store(AcDBObject n, Transaction tr, JsonNode data)
    {
        if (n.ExtensionDictionary.IsNull) n.CreateExtensionDictionary();
        var dict = (DBDictionary)tr.GetObject(n.ExtensionDictionary, OpenMode.ForWrite);
        if (dict.Contains(RecordName)) throw new ArgumentException("La red ya tiene contrato; no reemplazar");
        string json = data.ToJsonString();
        var x = new Xrecord { Data = new ResultBuffer(Enumerable.Range(0, (json.Length + 239) / 240)
            .Select(i => new TypedValue((int)DxfCode.Text, json.Substring(i * 240, Math.Min(240, json.Length - i * 240)))).ToArray()) };
        dict.SetAt(RecordName, x); tr.AddNewlyCreatedDBObject(x, true);
    }
    private static ObjectId[] Networks(CivilDocument civil) => CivilDocumentPressurePipesExtension.GetPressurePipeNetworkIds(civil).Cast<ObjectId>().ToArray();
    private static PressurePipeNetwork ResolveNetwork(Transaction tr, CivilDocument civil, string key)
    {
        var found = Networks(civil).Where(id => string.Equals(H(id), key, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(((PressurePipeNetwork)tr.GetObject(id, OpenMode.ForRead)).Name, key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (found.Length != 1) throw new ArgumentException("Red de presion inexistente o ambigua: " + key);
        return (PressurePipeNetwork)tr.GetObject(found[0], OpenMode.ForRead);
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
        if (!new[] { "catalogo", "cotas", "crear", "verificar", "trazado" }.Contains(action)) throw new ArgumentException("Accion desconocida");
        bool write = action == "crear" || action == "trazado", sim = write && (p["simular"]?.GetValue<bool>() ?? true);
        if (write && (Environment.GetEnvironmentVariable("CDCRD_C3D_SOLO_LECTURA") == "1" || Environment.GetEnvironmentVariable("CDCRD_C3D_PERMITIR_COMANDOS") != "1"))
            throw new InvalidOperationException("Escritura/comandos deshabilitados");
        using (doc.LockDocument())
        using (var tr = doc.Database.TransactionManager.StartTransaction())
        {
            var civil = CivilApp.ActiveDocument;
            object result = action switch
            {
                "catalogo" => Catalog(tr, doc.Database, civil, PresionContract.Text(p, "lista_partes", false)),
                "cotas" => Elevations(tr, civil, p),
                "crear" => Create(tr, doc.Database, civil, PresionContract.ParseCreate(p), sim),
                "trazado" => PipeRun(tr, doc.Database, civil, p, sim),
                _ => VerifyNetwork(tr, doc.Database, civil, Text(p, "red"))
            };
            if (write && !sim) { tr.Commit(); committed = true; } else tr.Abort();
            return result;
        }
    }

    // ---------- catalogo ----------
    private static object Catalog(Transaction tr, Database db, CivilDocument civil, string key)
    {
        var lists = PressurePartList.GetAvailablePartLists(db).Cast<ObjectId>().Select(id => (PressurePartList)tr.GetObject(id, OpenMode.ForRead))
            .Where(l => key == null || string.Equals(l.Name, key, StringComparison.OrdinalIgnoreCase) || string.Equals(H(l.ObjectId), key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (key != null && lists.Length == 0) throw new ArgumentException("Lista de partes de presion inexistente: " + key);
        var networks = Networks(civil).Select(id => (PressurePipeNetwork)tr.GetObject(id, OpenMode.ForRead)).Select(n => new
        {
            handle = H(n.ObjectId), nombre = n.Name, lista_partes = n.PartsListName, tuberias = n.GetPipeIds().Count, accesorios = n.GetFittingIds().Count, aparatos = n.GetAppurtenanceIds().Count,
            superficie = n.ReferenceSurfaceName, contrato = !n.ExtensionDictionary.IsNull && ((DBDictionary)tr.GetObject(n.ExtensionDictionary, OpenMode.ForRead)).Contains(RecordName)
        }).ToArray();
        return new
        {
            nota = "Las propiedades llevan las unidades del catalogo de la lista (el imperial guarda pulgadas); DiameterNominal es la clave de diametro_nominal.",
            listas_partes = lists.Select(pl => new
            {
                handle = H(pl.ObjectId), nombre = pl.Name, catalogo_guid = pl.CatalogGuid,
                tuberias = pl.GetParts(PressurePartDomainType.Pipe).Select(DescribeSize).ToArray(),
                accesorios = pl.GetParts(PressurePartDomainType.Fitting).Select(DescribeSize).ToArray(),
                aparatos = pl.GetParts(PressurePartDomainType.Appurtenance).Select(DescribeSize).ToArray()
            }).ToArray(),
            redes = networks
        };
    }

    // ---------- cotas ----------
    private static object Elevations(Transaction tr, CivilDocument civil, JsonObject p)
    {
        var surf = ResolveSurface(tr, civil, Text(p, "superficie"));
        if (p["puntos"] is not JsonArray pa || pa.Count < 1 || pa.Count > MaxPoints) throw new ArgumentException("puntos: lista de 1.." + MaxPoints);
        var rows = pa.Select(n =>
        {
            if (n is not JsonArray a || a.Count < 2) throw new ArgumentException("Cada punto es [x, y]");
            double x = PresionContract.Number(a[0], "x"), y = PresionContract.Number(a[1], "y");
            double? z; try { z = surf.FindElevationAtXY(x, y); } catch (Exception) { z = null; }
            return new { x, y, z };
        }).ToArray();
        return new { superficie = surf.Name, handle = H(surf.ObjectId), puntos = rows.Length, sin_cota = rows.Count(r => r.z == null), cotas = rows };
    }

    // ---------- crear ----------
    private static object Create(Transaction tr, Database db, CivilDocument civil, CreateOptions o, bool sim)
    {
        if (Networks(civil).Any(id => string.Equals(((PressurePipeNetwork)tr.GetObject(id, OpenMode.ForRead)).Name, o.Name, StringComparison.OrdinalIgnoreCase)))
            throw new ArgumentException("Ya existe la red de presion " + o.Name);
        var pl = ResolvePartsList(tr, db, o.PartsList);
        var surf = o.Surface == null ? null : ResolveSurface(tr, civil, o.Surface);
        var layer = LayerId(tr, db, o.Layer);
        // Resolve every part size before creating anything.
        var pipeSize = o.Pipes.ToDictionary(x => x.Id, x => ResolvePart(pl, "Pipe", "PressurePipe", x.Family, x.Nominal, null, null, "tuberia " + x.Id));
        var nodeSize = new Dictionary<string, PressurePartSize>();
        foreach (var n in o.Nodes.Where(n => n.Kind != "libre"))
        {
            var k = PresionContract.Kinds[n.Kind];
            nodeSize[n.Id] = ResolvePart(pl, k.Domain, k.PartType, n.Family, n.Nominal, n.Nominal2, n.Angle, "nodo " + n.Id);
        }
        QaCheckpoint?.Invoke("sizes-ready");
        var nid = PressurePipeNetwork.Create(db, o.Name);
        var net = (PressurePipeNetwork)tr.GetObject(nid, OpenMode.ForWrite);
        if (!string.Equals(net.Name, o.Name, StringComparison.Ordinal)) throw new InvalidOperationException("Civil cambio el nombre de la red a " + net.Name);
        net.PartsListId = pl.ObjectId; net.LayerId = layer;
        if (surf != null) net.ReferenceSurfaceId = surf.ObjectId;
        try { net.PipePlanLayerName = o.Layer; net.FittingPlanLayerName = o.Layer; net.AppurtenancePlanLayerName = o.Layer; } catch (Exception) { /* plan layers are cosmetic; parts get the layer below */ }
        QaCheckpoint?.Invoke("network-created");
        var byId = o.Nodes.ToDictionary(n => n.Id);
        var pipeIds = new Dictionary<string, ObjectId>();
        foreach (var x in o.Pipes)
        {
            var a = byId[x.From]; var b = byId[x.To];
            var pid = net.AddLinePipe(new LineSegment3d(new Point3d(a.Xyz[0], a.Xyz[1], a.Xyz[2]), new Point3d(b.Xyz[0], b.Xyz[1], b.Xyz[2])), pipeSize[x.Id]);
            if (pid.IsNull) throw new InvalidOperationException("Civil no creo la tuberia " + x.Id);
            var pipe = (PressurePipe)tr.GetObject(pid, OpenMode.ForWrite);
            pipe.LayerId = layer;
            pipeIds[x.Id] = pid;
        }
        QaCheckpoint?.Invoke("pipes-added");
        var partIds = new Dictionary<string, ObjectId>(); var rotations = new Dictionary<string, double>(); var portMap = new Dictionary<string, List<object>>();
        foreach (var n in o.Nodes.Where(n => n.Kind != "libre"))
        {
            var k = PresionContract.Kinds[n.Kind]; var loc = new Point3d(n.Xyz[0], n.Xyz[1], n.Xyz[2]);
            var id = k.Domain == "Fitting" ? net.AddFitting(loc, nodeSize[n.Id]) : net.AddAppurtenance(loc, nodeSize[n.Id]);
            if (id.IsNull) throw new InvalidOperationException("Civil no creo la pieza del nodo " + n.Id);
            var part = (PressurePart)tr.GetObject(id, OpenMode.ForWrite);
            part.LayerId = layer;
            partIds[n.Id] = id;
            // Pipes at this node, with their outgoing plan direction, and the part's ports: choose the rotation about Z
            // that best aligns ports to pipes, apply it, then connect each port to its pipe end.
            var at = o.Pipes.Where(x => x.From == n.Id || x.To == n.Id).Select(x =>
            {
                var other = byId[x.From == n.Id ? x.To : x.From];
                double dx = other.Xyz[0] - n.Xyz[0], dy = other.Xyz[1] - n.Xyz[1], len = Math.Sqrt(dx * dx + dy * dy);
                return (pipe: x, port: x.From == n.Id ? 0 : 1, ang: Math.Atan2(dy, dx), ux: dx / len, uy: dy / len);
            }).ToArray();
            int ports = part.ConnectionCount;
            if (ports < at.Length) throw new ArgumentException("La pieza del nodo " + n.Id + " tiene " + ports + " bocas y llegan " + at.Length + " tuberias");
            var portDir = Enumerable.Range(0, ports).Select(i => { using var c = part.GetConnectionAt(i); return Math.Atan2(c.Direction.Y, c.Direction.X); }).ToArray();
            double bestRot = 0, bestErr = double.PositiveInfinity; int[] bestAssign = null;
            var candidates = new List<double> { 0 };
            foreach (var t in at) foreach (var pd in portDir) candidates.Add(t.ang - pd);
            foreach (double rot in candidates)
            {
                var used = new HashSet<int>(); var assign = new int[at.Length]; double err = 0; bool ok = true;
                foreach (var (t, i) in at.Select((t, i) => (t, i)))
                {
                    int best = -1; double bestD = double.PositiveInfinity;
                    for (int q = 0; q < ports; q++)
                    {
                        if (used.Contains(q)) continue;
                        double d = Math.Abs(Math.IEEERemainder(portDir[q] + rot - t.ang, 2 * Math.PI));
                        if (d < bestD) { bestD = d; best = q; }
                    }
                    if (best < 0) { ok = false; break; }
                    used.Add(best); assign[i] = best; err += bestD;
                }
                if (ok && err < bestErr - 1e-9) { bestErr = err; bestRot = rot; bestAssign = assign; }
            }
            if (bestAssign == null) throw new InvalidOperationException("Sin asignacion de bocas en " + n.Id);
            if (o.Rotate && Math.Abs(bestRot) > 1e-9) part.TransformBy(Matrix3d.Rotation(bestRot, Vector3d.ZAxis, loc));
            rotations[n.Id] = bestRot;
            var mapped = new List<object>();
            for (int i = 0; i < at.Length; i++)
            {
                if (o.Connect) part.ConnectToPipe(bestAssign[i], pipeIds[at[i].pipe.Id], at[i].port);
                mapped.Add(new { boca = bestAssign[i], tuberia = at[i].pipe.Id, extremo = at[i].port, error_angular_rad = Math.Abs(Math.IEEERemainder(portDir[bestAssign[i]] + bestRot - at[i].ang, 2 * Math.PI)) });
            }
            portMap[n.Id] = mapped;
        }
        QaCheckpoint?.Invoke("parts-connected");
        var record = new JsonObject
        {
            ["version"] = 1, ["nombre"] = o.Name, ["capa"] = o.Layer, ["lista_partes"] = pl.Name, ["superficie"] = surf?.Name, ["tolerancia_m"] = o.Tolerance,
            ["tolerancia_conexion_m"] = o.ConnectionTolerance, ["conectar"] = o.Connect,
            ["nodos"] = new JsonArray(o.Nodes.Select(n =>
            {
                var row = new JsonObject { ["id"] = n.Id, ["tipo"] = n.Kind, ["xyz"] = new JsonArray(n.Xyz[0], n.Xyz[1], n.Xyz[2]), ["tuberias"] = new JsonArray(o.Pipes.Where(x => x.From == n.Id || x.To == n.Id).Select(x => (JsonNode)x.Id).ToArray()) };
                if (partIds.TryGetValue(n.Id, out var pid))
                {
                    var part = (PressurePart)tr.GetObject(pid, OpenMode.ForRead);
                    row["handle"] = H(pid); row["descripcion"] = nodeSize[n.Id].Description; row["guid"] = nodeSize[n.Id].PartSizeGuid; row["rotacion"] = rotations[n.Id];
                    row["posicion"] = new JsonArray(Pt(part.Position).Select(v => (JsonNode)v).ToArray()); row["bocas"] = JsonSerializer.SerializeToNode(portMap[n.Id]);
                }
                return (JsonNode)row;
            }).ToArray()),
            ["tuberias"] = new JsonArray(o.Pipes.Select(x =>
            {
                var pipe = (PressurePipe)tr.GetObject(pipeIds[x.Id], OpenMode.ForRead);
                return (JsonNode)new JsonObject
                {
                    ["id"] = x.Id, ["handle"] = H(pipeIds[x.Id]), ["desde"] = x.From, ["hasta"] = x.To, ["descripcion"] = pipeSize[x.Id].Description, ["guid"] = pipeSize[x.Id].PartSizeGuid,
                    ["diametro_nominal"] = x.Nominal, ["inicio"] = new JsonArray(Pt(pipe.StartPoint).Select(v => (JsonNode)v).ToArray()), ["fin"] = new JsonArray(Pt(pipe.EndPoint).Select(v => (JsonNode)v).ToArray()),
                    ["diametro_interior_m"] = pipe.InnerDiameter, ["diametro_exterior_m"] = pipe.OuterDiameter, ["nominal_m"] = pipe.NominalDiameter
                };
            }).ToArray())
        };
        var verification = Verify(tr, db, net, record);
        Store(net, tr, record); QaCheckpoint?.Invoke("record-written");
        return new { red = sim ? null : H(nid), nombre = o.Name, simulacion = sim, capa = o.Layer, lista_partes = pl.Name, superficie = surf?.Name, nodos = o.Nodes.Length, piezas = partIds.Count, tuberias = o.Pipes.Length, verificacion = verification };
    }

    // ---------- trazado (experimental): one pipe run from a path, bends added by Civil, depth of cover from a surface ----------
    private static object PipeRun(Transaction tr, Database db, CivilDocument civil, JsonObject p, bool sim)
    {
        string name = Text(p, "nombre"); string layerName = PresionContract.Text(p, "capa", false) ?? "CDCRD-PRESION";
        if (Networks(civil).Any(id => string.Equals(((PressurePipeNetwork)tr.GetObject(id, OpenMode.ForRead)).Name, name, StringComparison.OrdinalIgnoreCase)))
            throw new ArgumentException("Ya existe la red de presion " + name);
        var pl = ResolvePartsList(tr, db, PresionContract.Text(p, "lista_partes", false));
        var surf = ResolveSurface(tr, civil, Text(p, "superficie"));
        double cover = PresionContract.Range(p, "cobertura_m", 1.0, 0, 10);
        var size = ResolvePart(pl, "Pipe", "PressurePipe", Text(p, "familia"), PresionContract.Range(p, "diametro_nominal", double.NaN, .01, 10000), null, null, "tuberia");
        if (p["ruta"] is not JsonArray ra || ra.Count < 2 || ra.Count > 500) throw new ArgumentException("ruta: lista de 2..500 puntos [x, y]");
        var layer = LayerId(tr, db, layerName);
        var poly = new Polyline(); poly.SetDatabaseDefaults(); poly.LayerId = layer;
        for (int i = 0; i < ra.Count; i++) { var a = ra[i] as JsonArray ?? throw new ArgumentException("Cada punto es [x, y]"); poly.AddVertexAt(i, new Point2d(PresionContract.Number(a[0], "x"), PresionContract.Number(a[1], "y")), 0, 0, 0); }
        var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForWrite);
        var polyId = ms.AppendEntity(poly); tr.AddNewlyCreatedDBObject(poly, true);
        var nid = PressurePipeNetwork.Create(db, name);
        var net = (PressurePipeNetwork)tr.GetObject(nid, OpenMode.ForWrite);
        net.PartsListId = pl.ObjectId; net.LayerId = layer; net.ReferenceSurfaceId = surf.ObjectId;
        net.PipeRuns.createPipeRun(PresionContract.Text(p, "tramo", false) ?? "T1", poly, size, cover, p["codos_automaticos"]?.GetValue<bool>() ?? true);
        var pipes = net.GetPipeIds().Cast<ObjectId>().Select(id => (PressurePipe)tr.GetObject(id, OpenMode.ForRead)).Select(x => new { handle = H(x.ObjectId), nombre = x.Name, inicio = Pt(x.StartPoint), fin = Pt(x.EndPoint), nominal_m = x.NominalDiameter, cobertura_min_m = x.MinimumCover, cobertura_max_m = x.MaximumCover, inicio_conectado = !x.StartPartId.IsNull, fin_conectado = !x.EndPartId.IsNull }).ToArray();
        var fittings = net.GetFittingIds().Cast<ObjectId>().Select(id => (PressureFitting)tr.GetObject(id, OpenMode.ForRead)).Select(f => new { handle = H(f.ObjectId), nombre = f.Name, tipo = f.PartType.ToString(), posicion = Pt(f.Position), bocas = f.ConnectionCount }).ToArray();
        return new { red = sim ? null : H(nid), nombre = name, simulacion = sim, ruta_handle = H(polyId), tramos = net.PipeRuns.Count, tuberias = pipes, accesorios = fittings };
    }

    // ---------- verificar ----------
    private static object VerifyNetwork(Transaction tr, Database db, CivilDocument civil, string key)
    {
        var net = ResolveNetwork(tr, civil, key);
        return Verify(tr, db, net, Record(net, tr));
    }

    // Re-reads every part named in the contract and compares position, size, connectivity and layer.
    private static object Verify(Transaction tr, Database db, PressurePipeNetwork net, JsonObject record)
    {
        double tol = record["tolerancia_m"].GetValue<double>(), ctol = record["tolerancia_conexion_m"].GetValue<double>();
        bool connect = record["conectar"].GetValue<bool>();
        string layer = record["capa"].GetValue<string>();
        var bad = new List<string>();
        void Fail(string s) { if (bad.Count < 40) bad.Add(s); }
        var nodes = ((JsonArray)record["nodos"]).Cast<JsonObject>().ToArray();
        var pipes = ((JsonArray)record["tuberias"]).Cast<JsonObject>().ToArray();
        var netPipes = new HashSet<ObjectId>(net.GetPipeIds().Cast<ObjectId>());
        var netParts = new HashSet<ObjectId>(net.GetFittingIds().Cast<ObjectId>().Concat(net.GetAppurtenanceIds().Cast<ObjectId>()));
        int partNodes = nodes.Count(n => n["handle"] != null);
        if (netPipes.Count != pipes.Length) Fail("tuberias en la red " + netPipes.Count + " != contrato " + pipes.Length);
        if (netParts.Count != partNodes) Fail("piezas en la red " + netParts.Count + " != contrato " + partNodes);
        if (!string.Equals(net.PartsListName, record["lista_partes"].GetValue<string>(), StringComparison.Ordinal)) Fail("lista de partes " + net.PartsListName);
        double posMax = 0, designMax = 0, endMax = 0; int open = 0;
        var pipeById = new Dictionary<string, (PressurePipe pipe, JsonObject spec)>();
        var pipeRows = new List<object>();
        foreach (var x in pipes)
        {
            string id = x["id"].GetValue<string>();
            var oid = FromHandle(db, x["handle"].GetValue<string>());
            if (!netPipes.Contains(oid)) { Fail("tuberia " + id + " no pertenece a la red"); continue; }
            var pipe = (PressurePipe)tr.GetObject(oid, OpenMode.ForRead);
            var s0 = ((JsonArray)x["inicio"]).Select(n => n.GetValue<double>()).ToArray(); var s1 = ((JsonArray)x["fin"]).Select(n => n.GetValue<double>()).ToArray();
            double e = Math.Max(Dist3d(s0, pipe.StartPoint), Dist3d(s1, pipe.EndPoint)); posMax = Math.Max(posMax, e);
            if (e > tol) Fail("extremos de " + id + " movidos " + e.ToString("R"));
            if (!string.Equals(pipe.GetPartSize().PartSizeGuid, x["guid"].GetValue<string>(), StringComparison.OrdinalIgnoreCase)) Fail("pieza de " + id + ": " + pipe.PartDescription + " / " + pipe.GetPartSize().Description);
            if (Math.Abs(pipe.NominalDiameter - x["nominal_m"].GetValue<double>()) > 1e-6) Fail("diametro nominal de " + id + " " + pipe.NominalDiameter.ToString("R"));
            if (!string.Equals(pipe.Layer, layer, StringComparison.OrdinalIgnoreCase)) Fail("capa de " + id + " " + pipe.Layer);
            pipeById[id] = (pipe, x);
            pipeRows.Add(new { id, handle = H(oid), nombre = pipe.Name, desde = x["desde"].GetValue<string>(), hasta = x["hasta"].GetValue<string>(), inicio = Pt(pipe.StartPoint), fin = Pt(pipe.EndPoint), longitud_2d_m = pipe.Length2DCenterToCenter, longitud_3d_m = pipe.Length3DCenterToCenter,
                nominal_m = pipe.NominalDiameter, interior_m = pipe.InnerDiameter, exterior_m = pipe.OuterDiameter, pendiente = pipe.Slope, inicio_pieza = H(pipe.StartPartId), fin_pieza = H(pipe.EndPartId), descripcion = pipe.GetPartSize().Description });
        }
        var nodeRows = new List<object>();
        foreach (var n in nodes)
        {
            string id = n["id"].GetValue<string>();
            var design = ((JsonArray)n["xyz"]).Select(v => v.GetValue<double>()).ToArray();
            var pipeNames = ((JsonArray)n["tuberias"]).Select(v => v.GetValue<string>()).ToArray();
            if (n["handle"] == null)
            {
                // Open node: each pipe end must sit on the design point and stay unconnected.
                foreach (var pn in pipeNames)
                {
                    if (!pipeById.TryGetValue(pn, out var pp)) continue;
                    bool start = pp.spec["desde"].GetValue<string>() == id;
                    double d = Dist3d(design, start ? pp.pipe.StartPoint : pp.pipe.EndPoint); designMax = Math.Max(designMax, d);
                    if (d > tol) Fail("extremo libre de " + pn + " en " + id + " a " + d.ToString("R"));
                    if (!(start ? pp.pipe.StartPartId : pp.pipe.EndPartId).IsNull) Fail("extremo libre de " + pn + " en " + id + " conectado");
                    open++;
                }
                nodeRows.Add(new { id, tipo = n["tipo"].GetValue<string>(), posicion = design, pieza = (string)null });
                continue;
            }
            var oid = FromHandle(db, n["handle"].GetValue<string>());
            if (!netParts.Contains(oid)) { Fail("pieza de " + id + " no pertenece a la red"); continue; }
            var part = (PressurePart)tr.GetObject(oid, OpenMode.ForRead);
            var stored = ((JsonArray)n["posicion"]).Select(v => v.GetValue<double>()).ToArray();
            double ep = Dist3d(stored, part.Position), ed = Dist3d(design, part.Position); posMax = Math.Max(posMax, ep); designMax = Math.Max(designMax, ed);
            if (ep > tol) Fail("posicion de " + id + " movida " + ep.ToString("R"));
            if (ed > ctol) Fail("pieza de " + id + " a " + ed.ToString("R") + " del nodo de diseno");
            if (!string.Equals(part.GetPartSize().PartSizeGuid, n["guid"].GetValue<string>(), StringComparison.OrdinalIgnoreCase)) Fail("pieza de " + id + ": " + part.GetPartSize().Description);
            if (!string.Equals(part.Layer, layer, StringComparison.OrdinalIgnoreCase)) Fail("capa de " + id + " " + part.Layer);
            var conns = new List<object>(); var connected = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (int i = 0; i < part.ConnectionCount; i++)
            {
                using var c = part.GetConnectionAt(i);
                string cid = H(c.ConnectedId); if (cid != null) connected.Add(cid);
                conns.Add(new { boca = i, abierta = c.Open, conectada_a = cid, indice = c.ConnectedIndex, posicion = Pt(c.Position), direccion = new[] { c.Direction.X, c.Direction.Y, c.Direction.Z }, dn = c.NominalDiameter, dn_unidad = c.NominalDiameterUnit });
                if (c.Open) open++;
            }
            foreach (var pn in pipeNames)
            {
                if (!pipeById.TryGetValue(pn, out var pp)) continue;
                bool start = pp.spec["desde"].GetValue<string>() == id;
                var endPt = start ? pp.pipe.StartPoint : pp.pipe.EndPoint;
                double d = Dist3d(design, endPt); endMax = Math.Max(endMax, d);
                if (d > ctol) Fail("extremo de " + pn + " a " + d.ToString("R") + " del nodo " + id);
                var partAtEnd = start ? pp.pipe.StartPartId : pp.pipe.EndPartId;
                if (connect)
                {
                    if (partAtEnd != oid) Fail("tuberia " + pn + " no conectada a la pieza de " + id + " (conectada a " + H(partAtEnd) + ")");
                    if (!connected.Contains(H(pp.pipe.ObjectId))) Fail("pieza de " + id + " no registra la tuberia " + pn);
                }
            }
            nodeRows.Add(new { id, tipo = n["tipo"].GetValue<string>(), handle = H(oid), nombre = part.Name, pieza = part.GetPartSize().Description, posicion = Pt(part.Position), bocas = part.ConnectionCount, conexiones = conns });
        }
        var result = new
        {
            red = H(net.ObjectId), nombre = net.Name, capa = layer, lista_partes = net.PartsListName, tuberias = pipeRows.Count, piezas = nodeRows.Count(r => true) - nodes.Count(n => n["handle"] == null), nodos_libres = nodes.Count(n => n["handle"] == null),
            posicion_max_m = posMax, desvio_diseno_max_m = designMax, extremo_a_nodo_max_m = endMax, bocas_abiertas = open, conectar = connect,
            longitud_2d_m = pipeById.Values.Sum(v => v.pipe.Length2DCenterToCenter), tolerancia_m = tol, tolerancia_conexion_m = ctol, fallos = bad, detalle_nodos = nodeRows, detalle_tuberias = pipeRows
        };
        if (bad.Count > 0) throw new InvalidOperationException("Verificacion fallida: " + JsonSerializer.Serialize(result));
        return result;
    }
}
