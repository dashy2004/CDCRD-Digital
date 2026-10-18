using System.Collections;
using System.Reflection;
using System.Text.Json;

namespace CDCRD.WallDetailTrial;

/// <summary>Replace one detached leg's line pattern with fresh explicit native points.</summary>
internal static class ExplicitPointTrial
{
    internal readonly record struct Axis(double X, double Y, double Diameter);

    internal static void RequireSameLayout(IReadOnlyList<Axis> expected, IReadOnlyList<Axis> actual)
    {
        static void Check(IReadOnlyList<Axis> points)
        {
            if (points.Count == 0 || points.Count > 100)
                throw new InvalidOperationException("Invalid point inventory.");
            foreach (var point in points)
                if (!double.IsFinite(point.X) || !double.IsFinite(point.Y) ||
                    !double.IsFinite(point.Diameter) || point.Diameter <= 0 ||
                    Math.Abs(point.X) > 10000 || Math.Abs(point.Y) > 10000)
                    throw new InvalidOperationException("Invalid millimetre point.");
            for (int i = 0; i < points.Count; i++)
            for (int j = i + 1; j < points.Count; j++)
                if (Math.Abs(points[i].X - points[j].X) < 1e-5 && Math.Abs(points[i].Y - points[j].Y) < 1e-5)
                    throw new InvalidOperationException("Duplicate or ambiguous bar position.");
        }
        Check(expected); Check(actual);
        if (expected.Count != actual.Count) throw new InvalidOperationException("Bar inventory differs.");
        var used = new HashSet<int>();
        foreach (var point in expected)
        {
            int[] matches = Enumerable.Range(0, actual.Count).Where(i =>
                Math.Abs(point.X - actual[i].X) <= 1e-5 && Math.Abs(point.Y - actual[i].Y) <= 1e-5 &&
                Math.Abs(point.Diameter - actual[i].Diameter) <= 1e-5).ToArray();
            if (matches.Length != 1 || !used.Add(matches[0]))
                throw new InvalidOperationException("Plan and native cage bar axes differ or match ambiguously.");
        }
    }

    private static object[] Items(object value)
    {
        if (value is not IEnumerable sequence) throw new InvalidOperationException("Expected native collection.");
        var items = new List<object>();
        foreach (object? item in sequence)
        {
            if (item is null || items.Count >= 100) throw new InvalidOperationException("Invalid native inventory.");
            items.Add(item);
        }
        return items.ToArray();
    }

    private static Axis[] Points(object pattern) => Items(DetachedTrial.Call(pattern, "GetBarPoints"))
        .Select(point => new Axis(Field(point, "X"), Field(point, "Y"), Field(point, "Dia"))).ToArray();

    private static double Field(object value, string name) =>
        value.GetType().GetField(name, BindingFlags.Public | BindingFlags.Instance)?.GetValue(value) is double number
            ? number : throw new InvalidOperationException("Missing native coordinate field " + name);

    private static object Create(Type type) => Activator.CreateInstance(type)
        ?? throw new InvalidOperationException("Cannot construct independent native object.");

    internal static object Replace(object original, object clone, Assembly design, Action guard)
    {
        guard(); DetachedTrial.RequireDetached(original, clone);
        object previous = DetachedTrial.Read(clone, "VerticalBars");
        object[] patterns = Items(previous);
        if (patterns.Length != 1) throw new InvalidOperationException("Expected one generated leg pattern.");
        Axis[] axes = Points(patterns[0]);
        RequireSameLayout(axes, axes);
        if (axes.Length != 30 || axes.Any(point => point.Diameter != 16))
            throw new InvalidOperationException("Expected thirty metric leg points, excluding end joints.");
        Type groupType = design.GetType("CSI.NADetDesign.Rebars.cRebarPatternPoints", true)!;
        Type pointType = design.GetType("CSI.NADetDesign.Rebars.cRebarPatternPoint", true)!;
        object group = Create(groupType);
        if (DetachedTrial.Read(group, "Points") is not IList points || points.IsReadOnly || points.IsFixedSize || points.Count != 0)
            throw new InvalidOperationException("Expected a fresh mutable native point list.");
        object material = DetachedTrial.Read(patterns[0], "MaterialID");
        DetachedTrial.Set(group, "MaterialID", material);
        foreach (Axis axis in axes)
        {
            guard();
            object point = Create(pointType);
            // Native three-double constructor takes area first, not diameter.
            // Use the named catalog size and independently check the resulting diameter.
            DetachedTrial.Set(point, "Diameter", "16");
            DetachedTrial.Set(point, "X", axis.X);
            DetachedTrial.Set(point, "Y", axis.Y);
            DetachedTrial.Set(point, "MaterialID", material);
            RequireSameLayout([axis], Points(point));
            points.Add(point);
        }
        RequireSameLayout(axes, Points(group));
        object replacement = Create(previous.GetType());
        if (Items(replacement).Length != 0 || ReferenceEquals(replacement, previous) ||
            ReferenceEquals(replacement, DetachedTrial.Read(original, "VerticalBars")))
            throw new InvalidOperationException("Pattern collection is not fresh.");
        Type basePattern = design.GetType("CSI.NADetDesign.Rebars.cRebarPattern", true)!;
        var add = replacement.GetType().GetMethod("Add", BindingFlags.Public | BindingFlags.Instance,
            null, [basePattern], null) ?? throw new InvalidOperationException("Missing typed native Add contract.");
        if (!basePattern.IsInstanceOfType(group)) throw new InvalidOperationException("Invalid native pattern type.");
        add.Invoke(replacement, [group]);
        if (Items(replacement).Length != 1 || !ReferenceEquals(Items(replacement)[0], group))
            throw new InvalidOperationException("Replacement collection did not retain the fresh group.");
        guard(); DetachedTrial.RequireDetached(original, clone);
        DetachedTrial.Set(clone, "VerticalBars", replacement);
        if (!ReferenceEquals(DetachedTrial.Read(clone, "VerticalBars"), replacement))
            throw new InvalidOperationException("Detached assignment did not persist.");
        RequireSameLayout(axes, Points(Items(DetachedTrial.Read(clone, "VerticalBars"))[0]));
        return new { converted_leg_points = axes.Length, source_points_reused = false,
            material_labels_preserved_not_validated = true, source_cage_modified = false };
    }

    internal static Axis[] CageAxes(string json)
    {
        using var document = JsonDocument.Parse(json);
        var root = document.RootElement;
        var bars = root.ValueKind == JsonValueKind.Array ? root : root.GetProperty("$values");
        if (bars.GetArrayLength() is < 1 or > 100) throw new InvalidOperationException("Invalid cage count.");
        var axes = new List<Axis>();
        foreach (var bar in bars.EnumerateArray())
        {
            var points = bar.GetProperty("PLine").GetProperty("Points").GetProperty("$values");
            if (points.GetArrayLength() != 2) throw new InvalidOperationException("Expected a straight native bar.");
            var a = points[0]; var b = points[1];
            double x = a.GetProperty("X").GetDouble(), y = a.GetProperty("Y").GetDouble();
            double endX = b.GetProperty("X").GetDouble(), endY = b.GetProperty("Y").GetDouble();
            double z = a.GetProperty("Z").GetDouble(), endZ = b.GetProperty("Z").GetDouble();
            if (!double.IsFinite(endX) || !double.IsFinite(endY) || !double.IsFinite(z) || !double.IsFinite(endZ) ||
                Math.Abs(x - endX) > 1e-5 || Math.Abs(y - endY) > 1e-5 || Math.Abs(z - endZ) < 1e-5 ||
                a.GetProperty("OnArc").GetBoolean() || b.GetProperty("OnArc").GetBoolean())
                throw new InvalidOperationException("Expected finite straight vertical cage axes.");
            axes.Add(new Axis(x, y, bar.GetProperty("Dia").GetDouble()));
        }
        RequireSameLayout(axes, axes);
        return axes.ToArray();
    }

    internal static object RequireCageMatches(object section, string cageJson)
    {
        var expected = new List<Axis>();
        foreach (string collection in new[] { "DesignLegs", "Joints" })
        foreach (object owner in Items(DetachedTrial.Read(section, collection)))
        foreach (object pattern in Items(DetachedTrial.Read(owner, "VerticalBars")))
            expected.AddRange(Points(pattern));
        Axis[] actual = CageAxes(cageJson);
        if (expected.Count != 34) throw new InvalidOperationException("Expected all thirty-four section points.");
        RequireSameLayout(expected, actual);
        return new { matched_plan_and_cage_axes = actual.Length, xy_and_diameters_agree = true,
            vertical_extents_corrected = false, clashes_checked = false, anchorage_verified = false };
    }
}
