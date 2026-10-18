using System.Text.Json;

namespace CDCRD.WallDetailProbe;

internal readonly record struct Vertex(double X, double Y, double Z);
internal sealed record WallSnapshot(string Guid, Vertex[] Vertices);
internal sealed record UnitAssessment(bool WrapperAgrees, bool NumericContextAgrees);

/// <summary>Corroborates raw capture evidence; never rescales or approves detailing.</summary>
internal static class CaptureEvidence
{
    public static UnitAssessment AssessUnits(int databaseUnits, int presentUnits, string? payload,
        string? wrapper, string? numericContext, double millimeterFactor, double meterFactor)
    {
        if (databaseUnits != 9 || presentUnits != 9 || payload != "N_mm_C")
            throw new InvalidOperationException("OAPI/database/payload require the authorized N_mm_C fixture.");
        bool wrapperAgrees = Compact(wrapper) == "N,mm,C";
        bool numericAgrees = Compact(numericContext) == "N,mm,C" &&
                             Near(millimeterFactor, 1, 1e-9) && Near(meterFactor, 1000, 1e-6);
        return new(wrapperAgrees, numericAgrees);
    }

    private static string Compact(string? text) => new((text ?? "").Where(c => !char.IsWhiteSpace(c)).ToArray());
    private static bool Near(double value, double expected, double tolerance) =>
        double.IsFinite(value) && Math.Abs(value - expected) <= tolerance;

    public static WallSnapshot[] ReadWalls(JsonElement root)
    {
        var result = new List<WallSnapshot>();
        foreach (var stack in Values(root.GetProperty("Stacks")))
        foreach (var story in Values(stack.GetProperty("Stories")))
        foreach (var panel in Values(story.GetProperty("Panels")))
        foreach (var wall in Values(panel.GetProperty("WallObjects")))
        {
            string guid = wall.GetProperty("GUID").GetString()
                          ?? throw new InvalidOperationException("Native wall GUID is null.");
            var vertices = Values(wall.GetProperty("MidPlane").GetProperty("Points"))
                .Select(p => new Vertex(p.GetProperty("X").GetDouble(), p.GetProperty("Y").GetDouble(),
                                       p.GetProperty("Z").GetDouble())).ToArray();
            result.Add(new(guid, vertices));
        }
        if (result.Count == 0) throw new InvalidOperationException("No native wall geometry.");
        return result.ToArray();
    }

    private static IEnumerable<JsonElement> Values(JsonElement value) =>
        value.GetProperty("$values").EnumerateArray();

    public static int MatchWalls(WallSnapshot[] native, WallSnapshot[] current)
    {
        if (native.Length == 0 || native.Length != current.Length)
            throw new InvalidOperationException("Native/OAPI wall coverage differs.");
        var expected = Unique(current);
        var actual = Unique(native);
        int vertices = 0;
        foreach (var (guid, points) in actual)
        {
            if (!expected.TryGetValue(guid, out var other) || points.Length != other.Length)
                throw new InvalidOperationException("Native/OAPI wall identity or vertex count differs.");
            for (int i = 0; i < points.Length; i++)
                if (!Near(points[i].X, other[i].X, 1e-6) || !Near(points[i].Y, other[i].Y, 1e-6) ||
                    !Near(points[i].Z, other[i].Z, 1e-6))
                    throw new InvalidOperationException("Native/OAPI wall coordinates differ; no unit conversion is inferred.");
            vertices += points.Length;
        }
        return vertices;
    }

    private static Dictionary<string, Vertex[]> Unique(WallSnapshot[] walls)
    {
        var result = new Dictionary<string, Vertex[]>(StringComparer.OrdinalIgnoreCase);
        foreach (var wall in walls)
        {
            if (!System.Guid.TryParse(wall.Guid, out var guid) || wall.Vertices.Length < 3 ||
                wall.Vertices.Any(p => !double.IsFinite(p.X) || !double.IsFinite(p.Y) || !double.IsFinite(p.Z)) ||
                wall.Vertices.Distinct().Count() != wall.Vertices.Length ||
                !result.TryAdd(guid.ToString("D"), wall.Vertices.OrderBy(p => p.X).ThenBy(p => p.Y).ThenBy(p => p.Z).ToArray()))
                throw new InvalidOperationException("Invalid or duplicate wall geometry identity.");
        }
        return result;
    }
}
