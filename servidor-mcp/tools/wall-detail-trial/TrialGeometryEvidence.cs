using System.Text.Json;

namespace CDCRD.WallDetailTrial;

/// <summary>Reject opaque type labels before claiming a numeric geometry export.</summary>
internal static class TrialGeometryEvidence
{
    private static JsonElement Collection(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object && value.TryGetProperty("$values", out var items))
            value = items;
        if (value.ValueKind != JsonValueKind.Array || value.GetArrayLength() is < 1 or > 10000)
            throw new InvalidOperationException("Expected a nonempty bounded numeric geometry collection.");
        return value;
    }

    private static double Number(JsonElement item, string name)
    {
        if (item.ValueKind != JsonValueKind.Object || !item.TryGetProperty(name, out var value) ||
            value.ValueKind != JsonValueKind.Number || !value.TryGetDouble(out double result) || !double.IsFinite(result))
            throw new InvalidOperationException("Missing finite geometry coordinate/size: " + name);
        return result;
    }

    private static int Points(JsonElement value, bool requireDiameter, bool requireZ)
    {
        JsonElement points = Collection(value);
        foreach (JsonElement point in points.EnumerateArray())
        {
            Number(point, "X"); Number(point, "Y");
            if (requireZ) Number(point, "Z");
            if (requireDiameter && Number(point, "Dia") <= 0)
                throw new InvalidOperationException("Nonpositive bar point diameter.");
        }
        return points.GetArrayLength();
    }

    internal static int RequireBarPoints(string json)
    {
        using var doc = JsonDocument.Parse(json);
        return Points(doc.RootElement, requireDiameter: true, requireZ: false);
    }

    internal static int RequirePolylines(string json)
    {
        using var doc = JsonDocument.Parse(json);
        JsonElement lines = Collection(doc.RootElement);
        foreach (JsonElement line in lines.EnumerateArray())
        {
            if (Number(line, "Thickness") <= 0 || !line.TryGetProperty("Points", out var points) ||
                Points(points, requireDiameter: false, requireZ: false) < 2)
                throw new InvalidOperationException("Incomplete generated polyline geometry.");
        }
        return lines.GetArrayLength();
    }

    internal static void RequireCage(string json)
    {
        using var doc = JsonDocument.Parse(json);
        foreach (JsonElement bar in Collection(doc.RootElement).EnumerateArray())
        {
            if (Number(bar, "Dia") <= 0 || !bar.TryGetProperty("PLine", out var line) ||
                line.ValueKind != JsonValueKind.Object || !line.TryGetProperty("Points", out var points) ||
                Points(points, requireDiameter: false, requireZ: true) < 2)
                throw new InvalidOperationException("Incomplete source cage geometry.");
        }
    }
}
