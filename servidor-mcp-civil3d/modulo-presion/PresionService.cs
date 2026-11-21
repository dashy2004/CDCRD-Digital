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
        if (!new[] { "catalogo", "cotas", "crear", "verificar", "trazado", "leer", "inspeccionar" }.Contains(action)) throw new ArgumentException("Accion desconocida");
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
                "leer" => ReadNetworks(tr, civil, PresionContract.Text(p, "red", false)),
                "inspeccionar" => InspectNetwork(tr, civil, p),
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

    // ---------- lectura de cualquier red (con o sin contrato) ----------
    private const int MaxDetail = 2000;
    private const long MaxSamples = 200000;
    private static double? Safe(Func<double> f)
    {
        // Some part properties throw when the network has no reference surface or alignment: report them as absent.
        try { double v = f(); return double.IsFinite(v) ? v : null; } catch (Exception) { return null; }
    }
    private static string SafeText(Func<string> f) { try { return f(); } catch (Exception) { return null; } }
    // The placed part carries the catalog texts (ID_MATERIAL = "ductile iron"); the part size only has their numeric ids.
    private static string DataText(PressurePart x, string name)
    {
        try
        {
            foreach (var prop in x.PartData)
                if (prop.HasValue && string.Equals(prop.Name, name, StringComparison.OrdinalIgnoreCase) && prop.Value is string s && s.Length > 0) return s;
        }
        catch (Exception) { /* part without catalog data: reported as absent */ }
        return null;
    }
    private static PressurePipe[] PipesOf(Transaction tr, PressurePipeNetwork n) => n.GetPipeIds().Cast<ObjectId>().Select(id => (PressurePipe)tr.GetObject(id, OpenMode.ForRead)).ToArray();
    private static PressurePart[] PartsOf(Transaction tr, PressurePipeNetwork n) =>
        n.GetFittingIds().Cast<ObjectId>().Concat(n.GetAppurtenanceIds().Cast<ObjectId>()).Select(id => (PressurePart)tr.GetObject(id, OpenMode.ForRead)).ToArray();
    private static object PipeRow(PressurePipe x) => new
    {
        handle = H(x.ObjectId), nombre = x.Name, descripcion = SafeText(() => x.GetPartSize().Description), familia = SafeText(() => x.PartFamilyName),
        material = DataText(x, "ID_MATERIAL"), norma = DataText(x, "COMPATIBLE_STANDARD"),
        diametro_nominal_catalogo = SafeText(() => Prop(x.GetPartSize(), PressurePartContextType.DiameterNominal)?.ToString()),
        nominal_m = Safe(() => x.NominalDiameter), interior_m = Safe(() => x.InnerDiameter), exterior_m = Safe(() => x.OuterDiameter), espesor_m = Safe(() => x.WallThickness),
        inicio = Pt(x.StartPoint), fin = Pt(x.EndPoint), longitud_2d_m = Safe(() => x.Length2DCenterToCenter), longitud_3d_m = Safe(() => x.Length3DCenterToCenter),
        pendiente = Safe(() => x.Slope), curva = x.IsCurve, cobertura_min_m = Safe(() => x.MinimumCover), cobertura_max_m = Safe(() => x.MaximumCover),
        inicio_pieza = H(x.StartPartId), fin_pieza = H(x.EndPartId), capa = x.Layer
    };
    private static object PartRow(PressurePart f)
    {
        var conns = new List<object>();
        for (int i = 0; i < f.ConnectionCount; i++)
        {
            using var c = f.GetConnectionAt(i);
            conns.Add(new { boca = i, abierta = c.Open, conectada_a = H(c.ConnectedId), posicion = Pt(c.Position) });
        }
        return new
        {
            handle = H(f.ObjectId), nombre = f.Name, dominio = f.PartDomain.ToString(), tipo = f.PartType.ToString(), descripcion = SafeText(() => f.GetPartSize().Description),
            familia = SafeText(() => f.PartFamilyName), material = DataText(f, "ID_MATERIAL"), norma = DataText(f, "COMPATIBLE_STANDARD"),
            diametro_nominal_catalogo = SafeText(() => Prop(f.GetPartSize(), PressurePartContextType.DiameterNominal)?.ToString()),
            posicion = Pt(f.Position), bocas = f.ConnectionCount, conexiones = conns, capa = f.Layer
        };
    }
    private static object ReadNetworks(Transaction tr, CivilDocument civil, string key)
    {
        var nets = (key == null ? Networks(civil) : new[] { ResolveNetwork(tr, civil, key).ObjectId }).Select(id => (PressurePipeNetwork)tr.GetObject(id, OpenMode.ForRead)).ToArray();
        return new
        {
            nota = "Longitudes, cotas y diametros en metros (unidad del dibujo); diametro_nominal_catalogo y material vienen del catalogo de la lista de partes. Sin 'red' solo se devuelve el resumen de cada red.",
            redes = nets.Select(n => DescribeNetwork(tr, n, key != null)).ToArray()
        };
    }
    private static object DescribeNetwork(Transaction tr, PressurePipeNetwork n, bool detail)
    {
        var pipes = PipesOf(tr, n); var parts = PartsOf(tr, n);
        if (detail && pipes.Length + parts.Length > MaxDetail) throw new ArgumentException("La red tiene " + (pipes.Length + parts.Length) + " partes; el detalle admite hasta " + MaxDetail);
        var sizes = pipes.GroupBy(x => SafeText(() => x.GetPartSize().Description) ?? "?").Select(g => new
        {
            descripcion = g.Key, nominal_m = Safe(() => g.First().NominalDiameter), tuberias = g.Count(), longitud_2d_m = g.Sum(x => Safe(() => x.Length2DCenterToCenter) ?? 0)
        }).ToArray();
        return new
        {
            handle = H(n.ObjectId), nombre = n.Name, lista_partes = SafeText(() => n.PartsListName), superficie = SafeText(() => n.ReferenceSurfaceName), alineamiento = SafeText(() => n.ReferenceAlignmentName),
            tuberias = pipes.Length, accesorios = parts.Count(x => x is PressureFitting), aparatos = parts.Count(x => x is PressureAppurtenance), tramos = n.PipeRuns.Count,
            longitud_2d_m = pipes.Sum(x => Safe(() => x.Length2DCenterToCenter) ?? 0), longitud_3d_m = pipes.Sum(x => Safe(() => x.Length3DCenterToCenter) ?? 0),
            cota_min = Safe(() => n.MinimumElevation), cota_max = Safe(() => n.MaximumElevation), por_diametro = sizes,
            contrato = !n.ExtensionDictionary.IsNull && ((DBDictionary)tr.GetObject(n.ExtensionDictionary, OpenMode.ForRead)).Contains(RecordName),
            detalle_tuberias = detail ? pipes.Select(PipeRow).ToArray() : null, detalle_piezas = detail ? parts.Select(PartRow).ToArray() : null
        };
    }

    // ---------- inspeccion: conectividad y cobertura por muestras, sin depender del contrato ----------
    private static object InspectNetwork(Transaction tr, CivilDocument civil, JsonObject p)
    {
        var net = ResolveNetwork(tr, civil, Text(p, "red"));
        string key = PresionContract.Text(p, "superficie", false);
        var surf = key != null ? ResolveSurface(tr, civil, key) : net.ReferenceSurfaceId.IsNull ? null : tr.GetObject(net.ReferenceSurfaceId, OpenMode.ForRead) as TinSurface;
        return Inspect(tr, net, surf, PresionContract.Optional(p, "cobertura_min_m", 0, 20), PresionContract.Range(p, "paso_m", 5, .1, 100)).Report;
    }

    internal sealed record Inspection(object Report, bool Connected, bool CoverOk);

    // Connectivity: pipes and parts are graph nodes joined by the part at each pipe end and by each closed port.
    // Cover: samples every paso_m along the chord of each pipe; cover = surface - (centreline + outer diameter / 2).
    private static Inspection Inspect(Transaction tr, PressurePipeNetwork net, TinSurface surf, double? minCover, double step)
    {
        if (minCover.HasValue && surf == null) throw new ArgumentException("cobertura_min_m requiere una superficie (la de referencia de la red o 'superficie')");
        var pipes = PipesOf(tr, net); var parts = PartsOf(tr, net);
        var parent = pipes.Select(x => x.ObjectId).Concat(parts.Select(x => x.ObjectId)).ToDictionary(id => id, id => id);
        ObjectId Find(ObjectId a) { while (parent[a] != a) { parent[a] = parent[parent[a]]; a = parent[a]; } return a; }
        void Union(ObjectId a, ObjectId b) { if (!parent.ContainsKey(a) || !parent.ContainsKey(b)) return; var ra = Find(a); var rb = Find(b); if (ra != rb) parent[ra] = rb; }
        var openEnds = new List<object>(); var openPorts = new List<object>(); var warnings = new List<string>();
        foreach (var x in pipes)
            foreach (var (id, end, pt) in new[] { (x.StartPartId, "inicio", x.StartPoint), (x.EndPartId, "fin", x.EndPoint) })
            {
                if (id.IsNull) openEnds.Add(new { tuberia = H(x.ObjectId), nombre = x.Name, extremo = end, xyz = Pt(pt) });
                else if (!parent.ContainsKey(id)) warnings.Add("tuberia " + x.Name + " conectada en " + end + " a un objeto fuera de la red: " + H(id));
                else Union(x.ObjectId, id);
            }
        foreach (var f in parts)
            for (int i = 0; i < f.ConnectionCount; i++)
            {
                using var c = f.GetConnectionAt(i);
                if (c.Open || c.ConnectedId.IsNull) openPorts.Add(new { pieza = H(f.ObjectId), nombre = f.Name, tipo = f.PartType.ToString(), boca = i, xyz = Pt(c.Position) });
                else Union(f.ObjectId, c.ConnectedId);
            }
        int components = parent.Keys.Select(Find).Distinct().Count();
        bool connected = pipes.Length > 0 && components == 1;
        var bends = BendMismatches(pipes, parts, warnings);
        object coverReport = null; bool coverOk = true;
        if (surf != null)
        {
            var rows = new List<object>(); var below = new List<object>(); double gmin = double.PositiveInfinity, gmax = double.NegativeInfinity; int samples = 0, noElevation = 0, belowCount = 0, noDiameter = 0;
            // Every sample is a surface query on the UI thread: refuse a request that would freeze the session.
            long planned = pipes.Sum(x => (long)Math.Max(1, Math.Ceiling(Math.Sqrt(Math.Pow(x.EndPoint.X - x.StartPoint.X, 2) + Math.Pow(x.EndPoint.Y - x.StartPoint.Y, 2)) / step)) + 1);
            if (planned > MaxSamples) throw new ArgumentException("La inspeccion pide " + planned + " muestras y admite hasta " + MaxSamples + "; aumente paso_m");
            foreach (var x in pipes)
            {
                if (x.IsCurve) warnings.Add("tuberia " + x.Name + " es curva: la cobertura se muestrea sobre la cuerda");
                Point3d a = x.StartPoint, b = x.EndPoint; double? outer = Safe(() => x.OuterDiameter);
                if (outer == null) { noDiameter++; warnings.Add("tuberia " + x.Name + " sin diametro exterior legible: su cobertura se mide al eje y no acredita el minimo"); }
                double radius = (outer ?? 0) / 2;
                double len = Math.Sqrt((b.X - a.X) * (b.X - a.X) + (b.Y - a.Y) * (b.Y - a.Y));
                int n = Math.Max(1, (int)Math.Ceiling(len / step)); double pmin = double.PositiveInfinity, pmax = double.NegativeInfinity;
                for (int i = 0; i <= n; i++)
                {
                    double t = (double)i / n, px = a.X + (b.X - a.X) * t, py = a.Y + (b.Y - a.Y) * t, pz = a.Z + (b.Z - a.Z) * t;
                    samples++;
                    double zs; try { zs = surf.FindElevationAtXY(px, py); } catch (Exception) { noElevation++; continue; }
                    double cover = zs - (pz + radius); pmin = Math.Min(pmin, cover); pmax = Math.Max(pmax, cover);
                    if (minCover.HasValue && cover < minCover.Value - 1e-6)
                    {
                        belowCount++;
                        if (below.Count < 60) below.Add(new { tuberia = H(x.ObjectId), nombre = x.Name, xyz = new[] { px, py, pz }, cota_superficie = zs, cobertura_m = cover });
                    }
                }
                gmin = Math.Min(gmin, pmin); gmax = Math.Max(gmax, pmax);
                rows.Add(new { tuberia = H(x.ObjectId), nombre = x.Name, muestras = n + 1, cobertura_min_m = double.IsFinite(pmin) ? pmin : (double?)null, cobertura_max_m = double.IsFinite(pmax) ? pmax : (double?)null,
                    cobertura_min_civil_m = Safe(() => x.MinimumCover), cobertura_max_civil_m = Safe(() => x.MaximumCover) });
            }
            // A sample outside the surface, or a pipe without a readable outer diameter, cannot prove the required cover.
            coverOk = !minCover.HasValue || (belowCount == 0 && noElevation == 0 && noDiameter == 0);
            coverReport = new
            {
                superficie = surf.Name, criterio = "cota de superficie - (eje de tuberia + diametro exterior / 2)", paso_m = step, muestras = samples, sin_cota = noElevation,
                min_m = double.IsFinite(gmin) ? gmin : (double?)null, max_m = double.IsFinite(gmax) ? gmax : (double?)null, minima_exigida_m = minCover, bajo_minimo = belowCount,
                cumple = minCover.HasValue ? coverOk : (bool?)null, muestras_bajo_minimo = below, por_tuberia = rows
            };
        }
        var report = new
        {
            red = H(net.ObjectId), nombre = net.Name, tuberias = pipes.Length, piezas = parts.Length, componentes_conectados = components, conectada = connected,
            extremos_abiertos = openEnds, bocas_abiertas = openPorts, codos_fuera_de_angulo = bends, cobertura = coverReport, advertencias = warnings
        };
        return new Inspection(report, connected, coverOk);
    }

    private const double BendToleranceDegrees = 2.0;

    // Civil places the nearest catalog elbow at a bend; when the route deflects by another angle the joint is forced.
    // Reported, never failed: whether the joint deflection is admissible is a design decision.
    private static List<object> BendMismatches(PressurePipe[] pipes, PressurePart[] parts, List<string> warnings)
    {
        var rows = new List<object>();
        foreach (var f in parts.Where(x => x.PartType.ToString() == "Elbow"))
        {
            double? catalog = Num(Prop(f.GetPartSize(), PressurePartContextType.FittingAngle));
            // Direction of each connected pipe leaving the elbow.
            var away = pipes.Where(x => x.StartPartId == f.ObjectId || x.EndPartId == f.ObjectId)
                .Select(x => x.StartPartId == f.ObjectId ? x.StartPoint.GetVectorTo(x.EndPoint) : x.EndPoint.GetVectorTo(x.StartPoint)).Where(v => v.Length > 1e-9).ToArray();
            if (catalog == null || away.Length != 2) continue;
            double deflection = 180.0 - away[0].GetAngleTo(away[1]) * 180.0 / Math.PI;
            if (Math.Abs(deflection - catalog.Value) <= BendToleranceDegrees) continue;
            warnings.Add(string.Format(System.Globalization.CultureInfo.InvariantCulture,
                "codo {0} de catalogo {1:0.##} grados colocado en un quiebre de {2:0.##} grados (diferencia {3:0.##}): la union queda forzada; cambie el trazado o use una pieza del angulo correcto",
                f.Name, catalog.Value, deflection, deflection - catalog.Value));
                rows.Add(new { pieza = H(f.ObjectId), nombre = f.Name, descripcion = SafeText(() => f.GetPartSize().Description), posicion = Pt(f.Position),
                    angulo_catalogo_grados = catalog, deflexion_real_grados = deflection, diferencia_grados = deflection - catalog.Value });
        }
        return rows;
    }

    // ---------- trazado: one pipe run from vertices or an existing polyline, bends added by Civil, depth of cover from a surface ----------
    private static (Point2d[] Points, string Source) Route(Transaction tr, Database db, JsonObject p)
    {
        string handle = PresionContract.Text(p, "polilinea", false);
        if ((handle == null) == (p["ruta"] == null)) throw new ArgumentException("Indique 'ruta' (vertices) o 'polilinea' (handle), una sola");
        var pts = new List<Point2d>(); string source;
        if (handle == null)
        {
            if (p["ruta"] is not JsonArray ra) throw new ArgumentException("ruta: lista de puntos [x, y]");
            foreach (var n in ra)
            {
                if (n is not JsonArray a || a.Count < 2) throw new ArgumentException("Cada punto de la ruta es [x, y]");
                pts.Add(new Point2d(PresionContract.Number(a[0], "x"), PresionContract.Number(a[1], "y")));
            }
            source = "vertices";
        }
        else
        {
            var ent = tr.GetObject(FromHandle(db, handle), OpenMode.ForRead);
            if (ent is Polyline lw)
            {
                if (lw.Closed || !lw.Normal.IsEqualTo(Vector3d.ZAxis, new Tolerance(1e-9, 1e-9))) throw new ArgumentException("La polilinea debe ser abierta y estar en el plano XY universal");
                for (int i = 0; i < lw.NumberOfVertices; i++)
                {
                    if (i < lw.NumberOfVertices - 1 && Math.Abs(lw.GetBulgeAt(i)) > 1e-9) throw new ArgumentException("La polilinea tiene arcos; el trazado admite solo tramos rectos");
                    pts.Add(lw.GetPoint2dAt(i));
                }
                source = "polilinea 2D " + handle;
            }
            else if (ent is Polyline3d p3)
            {
                if (p3.Closed || p3.PolyType != Poly3dType.SimplePoly) throw new ArgumentException("La polilinea 3D debe ser abierta y sin ajuste de curva");
                foreach (ObjectId vid in p3) { var v = (PolylineVertex3d)tr.GetObject(vid, OpenMode.ForRead); pts.Add(new Point2d(v.Position.X, v.Position.Y)); }
                source = "polilinea 3D " + handle + " (solo planta; el perfil lo fija la cobertura)";
            }
            else throw new ArgumentException("El handle no es una polilinea ligera ni una polilinea 3D: " + ent.GetType().Name);
        }
        var clean = new List<Point2d>();
        foreach (var q in pts) if (clean.Count == 0 || clean[^1].GetDistanceTo(q) > 1e-6) clean.Add(q);
        if (clean.Count < 2 || clean.Count > 500) throw new ArgumentException("La ruta requiere de 2 a 500 vertices distintos");
        if (clean.Any(q => Math.Abs(q.X) > 1e8 || Math.Abs(q.Y) > 1e8)) throw new ArgumentException("Ruta fuera de rango");
        return (clean.ToArray(), source);
    }

    private static object PipeRun(Transaction tr, Database db, CivilDocument civil, JsonObject p, bool sim)
    {
        string name = Text(p, "nombre"); string layerName = PresionContract.Text(p, "capa", false) ?? "CDCRD-PRESION";
        if (Networks(civil).Any(id => string.Equals(((PressurePipeNetwork)tr.GetObject(id, OpenMode.ForRead)).Name, name, StringComparison.OrdinalIgnoreCase)))
            throw new ArgumentException("Ya existe la red de presion " + name);
        var pl = ResolvePartsList(tr, db, PresionContract.Text(p, "lista_partes", false));
        var surf = ResolveSurface(tr, civil, Text(p, "superficie"));
        double cover = PresionContract.Range(p, "cobertura_m", double.NaN, 0, 10);
        double? minCover = PresionContract.Optional(p, "cobertura_min_m", 0, 10);
        if (minCover > cover) throw new ArgumentException("cobertura_min_m no puede superar cobertura_m");
        double step = PresionContract.Range(p, "paso_m", 5, .1, 100);
        var size = ResolvePart(pl, "Pipe", "PressurePipe", Text(p, "familia"), PresionContract.Range(p, "diametro_nominal", double.NaN, .01, 10000), null, null, "tuberia");
        var route = Route(tr, db, p);
        var layer = LayerId(tr, db, layerName);
        // The run keeps its own path: an existing polyline is read, never consumed.
        var poly = new Polyline(); poly.SetDatabaseDefaults(); poly.LayerId = layer;
        for (int i = 0; i < route.Points.Length; i++) poly.AddVertexAt(i, route.Points[i], 0, 0, 0);
        var ms = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db), OpenMode.ForWrite);
        var polyId = ms.AppendEntity(poly); tr.AddNewlyCreatedDBObject(poly, true);
        var nid = PressurePipeNetwork.Create(db, name);
        var net = (PressurePipeNetwork)tr.GetObject(nid, OpenMode.ForWrite);
        net.PartsListId = pl.ObjectId; net.LayerId = layer; net.ReferenceSurfaceId = surf.ObjectId;
        QaCheckpoint?.Invoke("run-network-created");
        net.PipeRuns.createPipeRun(PresionContract.Text(p, "tramo", false) ?? "T1", poly, size, cover, p["codos_automaticos"]?.GetValue<bool>() ?? true);
        var pipeIds = net.GetPipeIds().Cast<ObjectId>().ToArray();
        if (pipeIds.Length == 0) throw new InvalidOperationException("Civil no creo ninguna tuberia para el tramo");
        foreach (ObjectId id in pipeIds.Concat(net.GetFittingIds().Cast<ObjectId>())) ((CivEntity)tr.GetObject(id, OpenMode.ForWrite)).LayerId = layer;
        QaCheckpoint?.Invoke("run-created");
        var inspection = Inspect(tr, net, surf, minCover, step);
        bool ok = inspection.Connected && inspection.CoverOk;
        if (!sim && !ok) throw new InvalidOperationException("El trazado no cumple conectividad o cobertura; no se guardo nada: " + JsonSerializer.Serialize(inspection.Report));
        return new
        {
            red = sim ? null : H(nid), nombre = name, simulacion = sim, cumple = ok, origen_ruta = route.Source, vertices = route.Points.Length, ruta_handle = sim ? null : H(polyId), capa = layerName,
            lista_partes = pl.Name, superficie = surf.Name, pieza = size.Description, cobertura_diseno_m = cover, tramos = net.PipeRuns.Count,
            tuberias = PipesOf(tr, net).Select(PipeRow).ToArray(), accesorios = PartsOf(tr, net).Select(PartRow).ToArray(), inspeccion = inspection.Report
        };
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
