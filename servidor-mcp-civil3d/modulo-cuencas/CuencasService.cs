// Catchments: list with hydrological parameters, create from a boundary and a surface, update parameters,
// tie to a gravity network structure. No coefficient is ever assumed: values come in the request or stay as Civil left them.
// All writes happen inside one transaction of the active document; simulation aborts it.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.ApplicationServices;
using Autodesk.Civil.DatabaseServices;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivilApp = Autodesk.Civil.ApplicationServices.CivilApplication;
using CivEntity = Autodesk.Civil.DatabaseServices.Entity;
using CivSurface = Autodesk.Civil.DatabaseServices.Surface;

namespace Cdcrd.Cuencas;

internal static class CuencasService
{
    internal static Action<string> QaCheckpoint = null;
    private const int MaxVertices = 2000;
    private static readonly string[] Actions = { "listar", "crear", "actualizar" };
    // Keys of the request that change a catchment; anything else is rejected by the Python validator.
    internal static readonly string[] Writable = { "coeficiente_escorrentia", "tc_min", "metodo_tc", "trayectoria", "estructura", "superficie", "numero_curva" };
    private static readonly Dictionary<string, TimeOfConcentrationCalculationMethod> TcMethods = new(StringComparer.OrdinalIgnoreCase)
    {
        ["TR55"] = TimeOfConcentrationCalculationMethod.CalculationMethodTR55, ["usuario"] = TimeOfConcentrationCalculationMethod.CalculationMethodUserDefined,
        ["Kirpich"] = TimeOfConcentrationCalculationMethod.CalculationMethodKirpich, ["FAA"] = TimeOfConcentrationCalculationMethod.CalculationMethodFAA
    };

    // ---------- helpers ----------
    private static string H(ObjectId id) => id.IsNull ? null : id.Handle.ToString();
    private static double[] Pt(Point3d p) => new[] { p.X, p.Y, p.Z };
    private static string Text(JsonObject p, string key, bool required = true, int max = 200)
    {
        var s = p[key]?.GetValue<string>();
        if (s == null && !required) return null;
        if (string.IsNullOrWhiteSpace(s) || s.Length > max || s.Any(char.IsControl)) throw new ArgumentException("Texto requerido de hasta " + max + " caracteres: " + key);
        return s;
    }
    private static double Number(JsonNode node, string key)
    {
        if (node is not JsonValue v) throw new ArgumentException("Numero requerido: " + key);
        double r;
        if (v.TryGetValue<double>(out var d)) r = d;
        else if (v.TryGetValue<long>(out var l)) r = l;
        else throw new ArgumentException("Numero requerido: " + key);
        if (!double.IsFinite(r)) throw new ArgumentException("Numero no finito: " + key);
        return r;
    }
    private static double InRange(JsonNode node, string key, double lo, double hi)
    {
        double v = Number(node, key);
        if (!(v >= lo && v <= hi)) throw new ArgumentException(key + " debe estar entre " + lo + " y " + hi);
        return v;
    }
    private static double? Safe(Func<double> f) { try { double v = f(); return double.IsFinite(v) ? v : null; } catch (Exception) { return null; } }
    private static string SafeText(Func<string> f) { try { return f(); } catch (Exception) { return null; } }
    private static ObjectId FromHandle(Database db, string handle)
    {
        try { return db.GetObjectId(false, new Handle(Convert.ToInt64(handle, 16)), 0); }
        catch (Exception) { throw new ArgumentException("Objeto inexistente: " + handle); }
    }
    private static bool IsHandle(string key) => key.Length <= 16 && key.All(Uri.IsHexDigit);

    private static CivSurface ResolveSurface(Transaction tr, CivilDocument civil, string key)
    {
        var found = civil.GetSurfaceIds().Cast<ObjectId>().Where(id => string.Equals(H(id), key, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(((CivEntity)tr.GetObject(id, OpenMode.ForRead)).Name, key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (found.Length != 1) throw new ArgumentException("Superficie inexistente o ambigua: " + key);
        return (CivSurface)tr.GetObject(found[0], OpenMode.ForRead);
    }

    // The group name is not in the reference metadata of this release but exists at run time: read by reflection.
    private static string GroupName(CatchmentGroup g)
    {
        try { return (string)g.GetType().GetProperty("Name")?.GetValue(g); } catch (Exception) { return null; }
    }
    private static (Catchment Catchment, CatchmentGroup Group)[] All(Transaction tr, Database db)
    {
        var rows = new List<(Catchment, CatchmentGroup)>();
        foreach (ObjectId gid in CatchmentGroupCollection.GetCatchmentGroups(db))
        {
            var g = (CatchmentGroup)tr.GetObject(gid, OpenMode.ForRead);
            foreach (ObjectId cid in g.GetAllCatchmentIds()) rows.Add(((Catchment)tr.GetObject(cid, OpenMode.ForRead), g));
        }
        return rows.ToArray();
    }
    private static (Catchment Catchment, CatchmentGroup Group) Resolve(Transaction tr, Database db, string key)
    {
        var found = All(tr, db).Where(r => string.Equals(H(r.Catchment.ObjectId), key, StringComparison.OrdinalIgnoreCase) || string.Equals(r.Catchment.Name, key, StringComparison.OrdinalIgnoreCase)).ToArray();
        if (found.Length != 1) throw new ArgumentException("Cuenca inexistente o ambigua: " + key);
        return found[0];
    }
    // A structure is named by handle, by its name when unique, or as "red/estructura".
    private static (ObjectId Network, ObjectId Structure, string Label) ResolveStructure(Transaction tr, CivilDocument civil, string key)
    {
        var found = new List<(ObjectId, ObjectId, string)>();
        foreach (ObjectId nid in civil.GetPipeNetworkIds())
        {
            var net = (Network)tr.GetObject(nid, OpenMode.ForRead);
            foreach (ObjectId sid in net.GetStructureIds())
            {
                var s = (Structure)tr.GetObject(sid, OpenMode.ForRead);
                string label = net.Name + "/" + s.Name;
                if (string.Equals(H(sid), key, StringComparison.OrdinalIgnoreCase) || string.Equals(s.Name, key, StringComparison.OrdinalIgnoreCase) || string.Equals(label, key, StringComparison.OrdinalIgnoreCase))
                    found.Add((nid, sid, label));
            }
        }
        if (found.Count != 1) throw new ArgumentException("Estructura de red de gravedad " + (found.Count == 0 ? "inexistente" : "ambigua (use red/estructura o el handle)") + ": " + key);
        return found[0];
    }

    // ---------- entry ----------
    internal static object Execute(JsonObject p, out bool committed)
    {
        committed = false;
        var doc = App.DocumentManager.MdiActiveDocument ?? throw new InvalidOperationException("Sin documento");
        if (!DateTimeOffset.TryParse(Text(p, "vence_utc"), out var expires) || expires < DateTimeOffset.UtcNow || expires > DateTimeOffset.UtcNow.AddMinutes(5))
            throw new ArgumentException("Solicitud vencida o plazo invalido");
        if (p["pid"]?.GetValue<int>() != Environment.ProcessId || !Path.IsPathFullyQualified(Text(p, "dibujo", true, 400)) ||
            !string.Equals(Path.GetFullPath(doc.Name), Path.GetFullPath(Text(p, "dibujo", true, 400)), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Documento o PID distinto al esperado");
        if (Convert.ToInt32(App.GetSystemVariable("INSUNITS")) != 6 || CivilApp.ActiveDocument.Settings.DrawingSettings.UnitZoneSettings.DrawingUnits.ToString() != "Meters")
            throw new ArgumentException("Se requieren unidades Civil y AutoCAD en metros");
        string action = Text(p, "accion");
        if (!Actions.Contains(action)) throw new ArgumentException("Accion desconocida");
        bool write = action != "listar", sim = write && (p["simular"]?.GetValue<bool>() ?? true);
        if (write && (Environment.GetEnvironmentVariable("CDCRD_C3D_SOLO_LECTURA") == "1" || Environment.GetEnvironmentVariable("CDCRD_C3D_PERMITIR_COMANDOS") != "1"))
            throw new InvalidOperationException("Escritura/comandos deshabilitados");
        using (doc.LockDocument())
        using (var tr = doc.Database.TransactionManager.StartTransaction())
        {
            var civil = CivilApp.ActiveDocument;
            object result = action switch
            {
                "listar" => List(tr, doc.Database, civil, Text(p, "cuenca", false)),
                "crear" => Create(tr, doc.Database, civil, p, sim),
                _ => Update(tr, doc.Database, civil, p, sim)
            };
            if (write && !sim) { tr.Commit(); committed = true; } else tr.Abort();
            return result;
        }
    }

    // ---------- lectura ----------
    // The API stores every catchment time in hours whatever the drawing's ambient time unit says (checked against a TR-55
    // shallow concentrated segment: 208.6 m at 0.849 m/s reads 0.0682). Requests and reports use minutes, converted here.
    private const double HourToMin = 60.0;
    private static string TimeUnit(CivilDocument civil) => SafeText(() => civil.Settings.DrawingSettings.AmbientSettings.Time.Unit.Value.ToString());

    private static object Row(Catchment c, CatchmentGroup g)
    {
        var segments = new List<object>();
        try
        {
            var path = c.FlowPath;
            for (int i = 0; path != null && i < path.FlowSegmentCount; i++)
            {
                var s = path.GetFlowSegmentAt(i);
                segments.Add(new { indice = i, tipo = SafeText(() => s.FlowType.ToString()), longitud_m = Safe(() => s.Length), pendiente = Safe(() => s.Slope), manning = Safe(() => s.ManningRoughness), tiempo_min = Safe(() => s.TravelTime) * HourToMin });
            }
        }
        catch (Exception) { /* a catchment without flow path has no segments */ }
        double? area = Safe(() => c.Area2d);
        return new
        {
            handle = H(c.ObjectId), nombre = c.Name, grupo = GroupName(g), grupo_handle = H(g.ObjectId), capa = c.Layer,
            area_m2 = area, area_ha = area / 10000.0, perimetro_m = Safe(() => c.Perimeter2d), superficie = SafeText(() => c.ReferenceSurfaceName),
            coeficiente_escorrentia = Safe(() => c.RunoffCoefficient), metodo_escorrentia = SafeText(() => c.RunoffMethod.ToString()),
            tc_min = Safe(() => c.TimeOfConcentration) * HourToMin, tc_h = Safe(() => c.TimeOfConcentration), metodo_tc = SafeText(() => c.TimeOfConcentrationCalculationMethod.ToString()),
            longitud_flujo_m = Safe(() => c.FlowPathLength), pendiente_media = Safe(() => c.AverageSlope),
            punto_descarga = SafeArray(() => Pt(c.DischargePoint)), punto_mas_distante = SafeArray(() => Pt(c.HydrologicallyMostDistantPoint)),
            numero_curva = Safe(() => c.CompositeCurveNumber), area_impermeable = Safe(() => c.ImperviousArea),
            red = SafeText(() => c.ReferencePipeNetworkName), estructura = SafeText(() => c.ReferenceDischargeObjectName), estructura_handle = SafeText(() => H(c.ReferenceDischargeObjectId)),
            segmentos_flujo = segments
        };
    }
    private static double[] SafeArray(Func<double[]> f) { try { return f(); } catch (Exception) { return null; } }

    private static object List(Transaction tr, Database db, CivilDocument civil, string key)
    {
        var rows = key == null ? All(tr, db) : new[] { Resolve(tr, db, key) };
        return new
        {
            nota = "Longitudes en metros y areas en m2 (unidad del dibujo). tc_min y tiempo_min en minutos, convertidos desde las horas que guarda la API (tc_h); unidad_tiempo_ajustes es solo la unidad de presentacion del dibujo. Los valores no indicados al crear son los que asigno Civil, no un criterio de diseno.",
            unidad_tiempo_ajustes = TimeUnit(civil), grupos = CatchmentGroupCollection.GetCatchmentGroups(db).Count, cuencas = rows.Select(r => Row(r.Catchment, r.Group)).ToArray()
        };
    }

    // ---------- contorno ----------
    private static (Point2d[] Points, string Source) Boundary(Transaction tr, Database db, JsonObject p)
    {
        string handle = Text(p, "polilinea", false);
        if ((handle == null) == (p["contorno"] == null)) throw new ArgumentException("Indique 'contorno' (vertices) o 'polilinea' (handle), uno solo");
        var pts = new List<Point2d>(); string source;
        if (handle == null)
        {
            if (p["contorno"] is not JsonArray ca) throw new ArgumentException("contorno: lista de puntos [x, y]");
            foreach (var n in ca)
            {
                if (n is not JsonArray a || a.Count < 2) throw new ArgumentException("Cada punto del contorno es [x, y]");
                pts.Add(new Point2d(Number(a[0], "x"), Number(a[1], "y")));
            }
            source = "vertices";
        }
        else
        {
            var ent = tr.GetObject(FromHandle(db, handle), OpenMode.ForRead);
            if (ent is Polyline lw)
            {
                if (!lw.Closed || !lw.Normal.IsEqualTo(Vector3d.ZAxis, new Tolerance(1e-9, 1e-9))) throw new ArgumentException("La polilinea debe ser cerrada y estar en el plano XY universal");
                for (int i = 0; i < lw.NumberOfVertices; i++)
                {
                    if (Math.Abs(lw.GetBulgeAt(i)) > 1e-9) throw new ArgumentException("La polilinea tiene arcos; el contorno admite solo tramos rectos");
                    pts.Add(lw.GetPoint2dAt(i));
                }
                source = "polilinea 2D " + handle;
            }
            else if (ent is Polyline3d p3)
            {
                if (!p3.Closed || p3.PolyType != Poly3dType.SimplePoly) throw new ArgumentException("La polilinea 3D debe ser cerrada y sin ajuste de curva");
                foreach (ObjectId vid in p3) { var v = (PolylineVertex3d)tr.GetObject(vid, OpenMode.ForRead); pts.Add(new Point2d(v.Position.X, v.Position.Y)); }
                source = "polilinea 3D " + handle + " (solo planta)";
            }
            else throw new ArgumentException("El handle no es una polilinea ligera ni una polilinea 3D: " + ent.GetType().Name);
        }
        var clean = new List<Point2d>();
        foreach (var q in pts) if (clean.Count == 0 || clean[^1].GetDistanceTo(q) > 1e-6) clean.Add(q);
        if (clean.Count > 1 && clean[0].GetDistanceTo(clean[^1]) <= 1e-6) clean.RemoveAt(clean.Count - 1);
        if (clean.Count < 3 || clean.Count > MaxVertices) throw new ArgumentException("El contorno requiere de 3 a " + MaxVertices + " vertices distintos");
        if (clean.Any(q => Math.Abs(q.X) > 1e8 || Math.Abs(q.Y) > 1e8)) throw new ArgumentException("Contorno fuera de rango");
        return (clean.ToArray(), source);
    }
    internal static double ShoelaceArea(IReadOnlyList<Point2d> pts)
    {
        double sum = 0;
        for (int i = 0; i < pts.Count; i++) { var a = pts[i]; var b = pts[(i + 1) % pts.Count]; sum += a.X * b.Y - b.X * a.Y; }
        return Math.Abs(sum) / 2;
    }

    // ---------- escritura de parametros ----------
    // Applies only the keys present in the request and returns what was asked, to be compared after re-reading.
    private static Dictionary<string, object> Apply(Transaction tr, Database db, CivilDocument civil, Catchment c, JsonObject p)
    {
        var asked = new Dictionary<string, object>();
        if (p["superficie"] != null && p["accion"]?.GetValue<string>() == "actualizar")
        {
            var surf = ResolveSurface(tr, civil, Text(p, "superficie"));
            c.ReferenceSurfaceId = surf.ObjectId; asked["superficie"] = surf.Name;
        }
        if (p["coeficiente_escorrentia"] != null) { double v = InRange(p["coeficiente_escorrentia"], "coeficiente_escorrentia", 0, 1); c.RunoffCoefficient = v; asked["coeficiente_escorrentia"] = v; }
        if (p["numero_curva"] != null) { int v = (int)InRange(p["numero_curva"], "numero_curva", 1, 100); c.CompositeCurveNumber = v; asked["numero_curva"] = (double)v; }
        if (p["trayectoria"] != null)
        {
            if (p["trayectoria"] is not JsonArray fa || fa.Count < 2 || fa.Count > MaxVertices) throw new ArgumentException("trayectoria: lista de 2.." + MaxVertices + " puntos [x, y] o [x, y, z], del punto mas distante a la descarga");
            var surf = c.ReferenceSurfaceId.IsNull ? null : tr.GetObject(c.ReferenceSurfaceId, OpenMode.ForRead) as CivSurface;
            var col = new Point3dCollection();
            foreach (var n in fa)
            {
                if (n is not JsonArray a || a.Count < 2) throw new ArgumentException("Cada punto de la trayectoria es [x, y] o [x, y, z]");
                double x = Number(a[0], "x"), y = Number(a[1], "y"), z;
                if (a.Count > 2) z = Number(a[2], "z");
                else if (surf == null) throw new ArgumentException("trayectoria sin z requiere que la cuenca tenga superficie de referencia");
                else { try { z = surf.FindElevationAtXY(x, y); } catch (Exception) { throw new ArgumentException("Punto de la trayectoria fuera de la superficie: " + x + ", " + y); } }
                col.Add(new Point3d(x, y, z));
            }
            // The attribute points to FlowPath.SetPath, which the installed assembly does not define: this overload is the only setter.
#pragma warning disable CS0618
            c.SetFlowPath(col);
#pragma warning restore CS0618
            asked["trayectoria_puntos"] = (double)col.Count;
        }
        if (p["metodo_tc"] != null)
        {
            string m = Text(p, "metodo_tc");
            if (!TcMethods.TryGetValue(m, out var method)) throw new ArgumentException("metodo_tc admite " + string.Join(", ", TcMethods.Keys));
            c.TimeOfConcentrationCalculationMethod = method; asked["metodo_tc"] = method.ToString();
        }
        if (p["tc_min"] != null)
        {
            // A given tc is a user value: Civil only keeps it under the user-defined method.
            if (p["metodo_tc"] != null && c.TimeOfConcentrationCalculationMethod != TimeOfConcentrationCalculationMethod.CalculationMethodUserDefined)
                throw new ArgumentException("tc_min explicito solo es compatible con metodo_tc=usuario");
            double v = InRange(p["tc_min"], "tc_min", 0, 14400) / HourToMin;
            c.TimeOfConcentrationCalculationMethod = TimeOfConcentrationCalculationMethod.CalculationMethodUserDefined;
            c.TimeOfConcentration = v; asked["tc_h"] = v; asked["metodo_tc"] = TimeOfConcentrationCalculationMethod.CalculationMethodUserDefined.ToString();
        }
        if (p["estructura"] != null)
        {
            var s = ResolveStructure(tr, civil, Text(p, "estructura"));
            // ReferencePipeNetworkId is read-only in this release: the structure is set as the discharge object and Civil derives the network.
            c.ReferenceDischargeObjectId = s.Structure; asked["estructura_handle"] = H(s.Structure);
        }
        return asked;
    }

    // Re-reads the catchment and compares every value that was asked for.
    private static List<string> Compare(Catchment c, Dictionary<string, object> asked)
    {
        var bad = new List<string>();
        void Check(string key, double? actual) { if (asked.TryGetValue(key, out var v) && !(actual.HasValue && Math.Abs(actual.Value - (double)v) <= 1e-9 * Math.Max(1, Math.Abs((double)v)))) bad.Add(key + ": pedido " + v + ", leido " + (actual?.ToString("R") ?? "nada")); }
        Check("coeficiente_escorrentia", Safe(() => c.RunoffCoefficient));
        Check("numero_curva", Safe(() => c.CompositeCurveNumber));
        Check("tc_h", Safe(() => c.TimeOfConcentration));
        if (asked.TryGetValue("metodo_tc", out var m) && SafeText(() => c.TimeOfConcentrationCalculationMethod.ToString()) != (string)m) bad.Add("metodo_tc: pedido " + m + ", leido " + SafeText(() => c.TimeOfConcentrationCalculationMethod.ToString()));
        if (asked.TryGetValue("estructura_handle", out var s) && SafeText(() => H(c.ReferenceDischargeObjectId)) != (string)s) bad.Add("estructura: pedida " + s + ", leida " + SafeText(() => H(c.ReferenceDischargeObjectId)));
        if (asked.TryGetValue("superficie", out var f) && !string.Equals(SafeText(() => c.ReferenceSurfaceName), (string)f, StringComparison.OrdinalIgnoreCase)) bad.Add("superficie: pedida " + f + ", leida " + SafeText(() => c.ReferenceSurfaceName));
        if (asked.ContainsKey("trayectoria_puntos") && !(Safe(() => c.FlowPathLength) > 0)) bad.Add("trayectoria: la cuenca no reporta longitud de flujo");
        return bad;
    }

    // ---------- crear ----------
    private static object Create(Transaction tr, Database db, CivilDocument civil, JsonObject p, bool sim)
    {
        string name = Text(p, "nombre"), groupName = Text(p, "grupo");
        if (All(tr, db).Any(r => string.Equals(r.Catchment.Name, name, StringComparison.OrdinalIgnoreCase))) throw new ArgumentException("Ya existe la cuenca " + name);
        var surf = ResolveSurface(tr, civil, Text(p, "superficie"));
        var boundary = Boundary(tr, db, p);
        double expected = ShoelaceArea(boundary.Points);
        if (expected < 1e-3) throw new ArgumentException("Contorno sin area");
        var styles = civil.Styles.CatchmentStyles;
        string styleName = Text(p, "estilo", false);
        ObjectId styleId;
        if (styleName != null) { if (!styles.Contains(styleName)) throw new ArgumentException("Estilo de cuenca inexistente: " + styleName); styleId = styles[styleName]; }
        else styleId = styles.Count > 0 ? styles[0] : styles.Add("Cuenca");
        var groups = CatchmentGroupCollection.GetCatchmentGroups(db);
        bool newGroup = !groups.Contains(groupName);
        ObjectId groupId = newGroup ? groups.Add(groupName) : groups[groupName];
        QaCheckpoint?.Invoke("group-ready");
        var col = new Point3dCollection();
        foreach (var q in boundary.Points) col.Add(new Point3d(q.X, q.Y, 0));
        col.Add(new Point3d(boundary.Points[0].X, boundary.Points[0].Y, 0));
        var id = Catchment.Create(name, styleId, groupId, surf.ObjectId, col);
        if (id.IsNull) throw new InvalidOperationException("Civil no creo la cuenca");
        var c = (Catchment)tr.GetObject(id, OpenMode.ForWrite);
        if (!string.Equals(c.Name, name, StringComparison.Ordinal)) throw new InvalidOperationException("Civil cambio el nombre de la cuenca a " + c.Name);
        QaCheckpoint?.Invoke("catchment-created");
        var asked = Apply(tr, db, civil, c, p);
        var bad = Compare(c, asked);
        double? area = Safe(() => c.Area2d);
        if (!(area.HasValue && Math.Abs(area.Value - expected) <= Math.Max(0.01, 1e-6 * expected))) bad.Add("area: contorno " + expected.ToString("R") + " m2, cuenca " + (area?.ToString("R") ?? "nada") + " m2");
        if (bad.Count > 0) throw new InvalidOperationException("Verificacion fallida; no se guardo nada: " + string.Join("; ", bad));
        var group = (CatchmentGroup)tr.GetObject(groupId, OpenMode.ForRead);
        return new
        {
            cuenca = sim ? null : H(id), nombre = name, simulacion = sim, grupo = groupName, grupo_nuevo = newGroup, origen_contorno = boundary.Source, vertices = boundary.Points.Length,
            area_contorno_m2 = expected, parametros_pedidos = asked.Keys.ToArray(), parametros_de_civil = Writable.Where(k => p[k] == null && k != "superficie" && !(k == "metodo_tc" && p["tc_min"] != null)).ToArray(),
            lectura = Row(c, group)
        };
    }

    // ---------- actualizar ----------
    private static object Update(Transaction tr, Database db, CivilDocument civil, JsonObject p, bool sim)
    {
        var found = Resolve(tr, db, Text(p, "cuenca"));
        if (!Writable.Any(k => p[k] != null)) throw new ArgumentException("Nada que actualizar: indique " + string.Join(", ", Writable));
        object before = Row(found.Catchment, found.Group);
        var c = (Catchment)tr.GetObject(found.Catchment.ObjectId, OpenMode.ForWrite);
        var asked = Apply(tr, db, civil, c, p);
        var bad = Compare(c, asked);
        if (bad.Count > 0) throw new InvalidOperationException("Verificacion fallida; no se guardo nada: " + string.Join("; ", bad));
        return new { cuenca = H(c.ObjectId), nombre = c.Name, simulacion = sim, parametros_pedidos = asked.Keys.ToArray(), antes = before, despues = Row(c, found.Group) };
    }
}
