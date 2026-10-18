using System.Collections;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;

namespace CDCRD.WallDetailTrial;

/// <summary>Generate candidates on detached clones only. No source setters or story updates.</summary>
internal static class DetachedTrial
{
    internal static object Read(object value, string name) =>
        value.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.Instance)?.GetValue(value)
        ?? throw new InvalidOperationException("Missing native value " + name);

    internal static object Call(object value, string name, params object[] args)
    {
        var matches = value.GetType().GetMethods(BindingFlags.Public | BindingFlags.Instance)
            .Where(m => m.Name == name && m.GetParameters().Length == args.Length &&
                m.GetParameters().Select((p, i) => p.ParameterType.IsInstanceOfType(args[i])).All(x => x)).ToArray();
        if (matches.Length != 1) throw new InvalidOperationException("Ambiguous or missing contract: " + name);
        return matches[0].Invoke(value, args) ?? throw new InvalidOperationException("Null native result: " + name);
    }

    private static void Set(object value, string name, object data)
    {
        var property = value.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.Instance)
                       ?? throw new InvalidOperationException("Missing clone setting " + name);
        if (property.SetMethod?.IsPublic != true || !property.PropertyType.IsInstanceOfType(data))
            throw new InvalidOperationException("Unexpected clone setting type: " + name);
        property.SetValue(value, data);
    }

    private static object[] Items(object value)
    {
        if (value is not IEnumerable sequence) throw new InvalidOperationException("Expected native collection.");
        var result = new List<object>();
        foreach (object? item in sequence)
        {
            if (item is null || result.Count >= 100) throw new InvalidOperationException("Invalid fixture collection.");
            result.Add(item);
        }
        return result.ToArray();
    }

    internal static void RequireDetached(object original, object clone)
    {
        if (ReferenceEquals(original, clone) || clone.GetType() != original.GetType())
            throw new InvalidOperationException("Clone identity is not independent.");
        var parent = clone.GetType().GetProperty("PierSection", BindingFlags.Public | BindingFlags.Instance)
                     ?? throw new InvalidOperationException("Missing parent contract.");
        if (parent.GetValue(clone) is not null || (bool)Read(clone, "InEditMode"))
            throw new InvalidOperationException("Clone is attached or in edit mode.");
        object source = Call(original, "GetLegData"), candidate = Call(clone, "GetLegData");
        var sourceNodes = DataNodes(source);
        var candidateNodes = DataNodes(candidate);
        if (sourceNodes.Any(a => candidateNodes.Any(b => ReferenceEquals(a, b))))
            throw new InvalidOperationException("Clone shares mutable geometry or reinforcing data.");
    }

    private static object[] DataNodes(object data)
    {
        object line = Read(data, "CLine");
        return [data, Read(data, "StartZone"), Read(data, "EndZone"), Read(data, "MidZone"),
            line, Read(line, "Pt1"), Read(line, "Pt2")];
    }

    public static object Run(object designer, Assembly detail, Assembly core, Assembly design, string output, Action guard)
    {
        guard();
        var serializer = core.GetType("CSI.NADetBase.Common.JSONIO", true)!.GetMethod("GetJSonString",
            BindingFlags.Public | BindingFlags.Static, null, [typeof(object)], null)
            ?? throw new InvalidOperationException("Native serializer missing.");
        string Serialize(object value)
        {
            string text = serializer.Invoke(null, [value]) as string
                          ?? throw new InvalidOperationException("Native serialization failed.");
            if (text.Length > 32 * 1024 * 1024) throw new InvalidOperationException("Trial data exceeds limit.");
            using var parsed = JsonDocument.Parse(text);
            return text;
        }
        var manifest = new List<object>();
        void Save(string name, object value)
        {
            string text = Serialize(value);
            File.WriteAllText(Path.Combine(output, name + ".json"), text);
            manifest.Add(new { file = name + ".json", sha256 = Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(text))) });
        }
        object preferences = detail.GetType("CSI.CSiNAWallStackDesigner.xAppWD", true)!
            .GetField("WallStackPref", BindingFlags.Public | BindingFlags.Static)?.GetValue(null)
            ?? throw new InvalidOperationException("Native wall preferences unavailable.");
        object pierPreferences = Read(preferences, "PierPref");
        string preferencesBefore = Serialize(preferences);
        object app = design.GetType("CSI.NADetDesign.xAppDSN", true)!
            .GetProperty("App", BindingFlags.Public | BindingFlags.Static)?.GetValue(null)
            ?? throw new InvalidOperationException("Active design context unavailable.");
        object catalog = Read(app, "RebarSet");
        foreach (string name in new[] { "16", "12" })
        {
            double area = (double)Call(catalog, "get_Area", name);
            double diameter = (double)Call(catalog, "get_Dia", area);
            double expected = double.Parse(name, System.Globalization.CultureInfo.InvariantCulture);
            if (!double.IsFinite(area) || area <= 0 || diameter != expected ||
                Math.Abs(area - Math.PI * expected * expected / 4) > 0.2)
                throw new InvalidOperationException("Metric catalog identity mismatch for " + name);
        }
        var legs = new List<object>();
        var stories = new List<object>();
        foreach (object tower in Items(Read(designer, "WallTowers")))
        foreach (object stack in Items(Read(Read(tower, "WallStackSet"), "Stacks")))
        foreach (object story in Items(Read(stack, "Storys")))
        {
            stories.Add(story);
            foreach (object section in Items(Read(story, "Sections")))
            foreach (object pier in Items(Read(section, "PierSections")))
            foreach (object leg in Items(Read(pier, "DesignLegs"))) legs.Add(leg);
        }
        if (stories.Count != 2 || legs.Count != 2)
            throw new InvalidOperationException("Expected exactly two stories and two isolated test legs.");
        string[] sourceBefore = legs.Select(l => Serialize(Call(l, "GetLegData"))).ToArray();
        string[] patternsBefore = legs.Select(Serialize).ToArray();
        var results = new List<object>();
        try
        {
            for (int i = 0; i < legs.Count; i++)
            {
                object original = legs[i], sourceData = Call(original, "GetLegData");
                if (!(bool)Read(sourceData, "UniformThickness") || (bool)Read(sourceData, "UseBoundaryZones") ||
                    (bool)Read(sourceData, "UseConfinement") || (double)Read(sourceData, "PanelLength") != 4000 ||
                    (double)Read(Read(sourceData, "MidZone"), "Thickness") != 200)
                    throw new InvalidOperationException("Fixture is not the authorized uniform 4000 x 200 mm wall.");
                Save($"leg-{i + 1:D2}-source-data", sourceData);
                foreach (string scenario in new[] { "control", "metric-mid", "metric-all-ties" })
                {
                    guard();
                    object clone = Call(original, "Clone");
                    void Change(string name, object value) { guard(); Set(clone, name, value); }
                    RequireDetached(original, clone);
                    Change("RebarMatID", Read(original, "RebarMatID"));
                    if (scenario != "control")
                    {
                        Change("Cover", 40.0);
                        Change("UniformBarSize", "16");
                        Change("UniformBarSizeEnds", "16");
                        Change("UniformBarSpacing", 250.0);
                        Change("BarSizeHBars", "12");
                        Change("MaxBarSpacingHBars", 400.0);
                        if (scenario == "metric-all-ties") Change("ConfinedPrefTieSize", "12");
                    }
                    // InEditMode stays false: do not invoke parent/story updates.
                    RequireDetached(original, clone);
                    string prefix = $"leg-{i + 1:D2}-{scenario}";
                    Save(prefix + "-input", Call(clone, "GetLegData"));
                    guard();
                    Save(prefix + "-vertical-patterns", Call(clone, "GenerateVerticalRebarPatterns", pierPreferences));
                    guard();
                    Save(prefix + "-horizontal-shapes", Call(clone, "GenerateHorizontalRebarShapes", pierPreferences));
                    Save(prefix + "-generated-data", Call(clone, "GetLegData"));
                    results.Add(new { leg = i + 1, scenario, status = "generated_on_detached_clone_only",
                        not_applied = true, physical_cage_spacing_verified = false, cover_verified = false });
                }
            }
        }
        finally
        {
            bool unchanged = legs.Select((l, i) => sourceBefore[i] == Serialize(Call(l, "GetLegData")) &&
                patternsBefore[i] == Serialize(l)).All(x => x) && preferencesBefore == Serialize(preferences);
            File.WriteAllText(Path.Combine(output, "source-invariants.json"), JsonSerializer.Serialize(new
            { source_legs_and_preferences_unchanged = unchanged, source_leg_count = legs.Count }));
            if (!unchanged) throw new InvalidOperationException("Source invariant changed; do not save or claim isolation.");
        }
        return new { status = "detached_trials_completed_not_applied", results, files = manifest,
            source_cage_changed = false, source_preferences_changed = false, no_story_regeneration = true,
            complete_detailing = false, engineering_approval = false };
    }
}
