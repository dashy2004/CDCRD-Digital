using System.Collections;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;

namespace CDCRD.WallDetailProbe;

/// <summary>Exact-build read operations; never deserialize native type metadata.</summary>
internal static class NativeDetailCapture
{
    public static ContextLease Activate(Assembly detail, Assembly core, Assembly design)
    {
        PropertyInfo commonApp = StaticProperty(core, "CSI.NADetBase.Common.xApp", "App");
        PropertyInfo designApp = StaticProperty(design, "CSI.NADetDesign.xAppDSN", "App");
        object? previousCommon = commonApp.GetValue(null);
        object? previousDesign = designApp.GetValue(null);
        object active = StaticProperty(detail, "CSI.CSiNAWallStackDesigner.xAppWD", "App").GetValue(null)
                        ?? throw new InvalidOperationException("Wall application context missing.");
        // xAppDSN.App's setter also sets xApp.App. Restore design FIRST, common LAST.
        return new ContextLease(() => { commonApp.SetValue(null, active); designApp.SetValue(null, active); },
            () => designApp.SetValue(null, previousDesign),
            () => commonApp.SetValue(null, previousCommon));
    }

    public static (bool Success, object Manifest) Capture(object designer, Assembly detail, Assembly core, string output)
    {
        var serializer = core.GetType("CSI.NADetBase.Common.JSONIO", true)!
            .GetMethod("GetJSonString", BindingFlags.Public | BindingFlags.Static, null, [typeof(object)], null)
            ?? throw new InvalidOperationException("Native JSON serializer contract changed.");
        var files = new List<object>();
        int failures = 0;
        void Export(string name, Func<object> read)
        {
            try
            {
            object value = read();
            string json = serializer.Invoke(null, [value]) as string
                          ?? throw new InvalidOperationException("Native serializer returned no JSON for " + name);
            if (json.Length > 32 * 1024 * 1024) throw new InvalidOperationException("Capture exceeds 32 MiB character budget.");
            using var parsed = JsonDocument.Parse(json);
            if (parsed.RootElement.ValueKind is not (JsonValueKind.Object or JsonValueKind.Array))
                throw new InvalidOperationException("Native serializer returned no structured data for " + name);
            File.WriteAllText(Path.Combine(output, name + ".json"), json);
            files.Add(new { file = name + ".json", status = "captured_not_validated",
                item_count = value is ICollection collection ? (int?)collection.Count : null,
                sha256 = Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(json))) });
            }
            catch (Exception exception)
            {
                failures++;
                files.Add(new { file = name + ".json", status = "failed", error = exception.ToString() });
            }
        }

        object app = StaticProperty(detail, "CSI.CSiNAWallStackDesigner.xAppWD", "App").GetValue(null)
                     ?? throw new InvalidOperationException("Wall application context missing.");
        Export("native-rebar-catalog", () => Property(app, "RebarSet"));
        int stackNumber = 0, storyNumber = 0;
        var identities = new List<object>();
        foreach (object tower in Items(Property(designer, "WallTowers")))
        foreach (object stack in Items(Property(Property(tower, "WallStackSet"), "Stacks")))
        {
            stackNumber++;
            int inStack = 0;
            // Do not call UpdateQuantities: preserve any existing quantity cache.
            Export($"stack-{stackNumber:D3}-quantity-cache", () => Property(stack, "BOQSummary"));
            foreach (object story in Items(Property(stack, "Storys")))
            {
                inStack++;
                storyNumber++;
                string prefix = $"stack-{stackNumber:D3}-story-{inStack:D3}";
                Export(prefix + "-vertical-groups", () => Invoke(story, "GetVerticalBarGroups"));
                Export(prefix + "-horizontal-groups", () => Invoke(story, "GetTransBarSets"));
                Export(prefix + "-vertical-cage", () => Invoke(story, "GetVerticalBarsFor3DCage", false));
                Export(prefix + "-horizontal-cage", () => Invoke(story, "GetHorizontalBarsFor3DCage", false));
                var geom = Property(story, "Geom");
                identities.Add(new { prefix, story = Property(geom, "StoryName").ToString(),
                    base_z = Property(geom, "BaseZLevel"), height = Property(geom, "Height") });
            }
        }
        if (stackNumber == 0 || storyNumber == 0) throw new InvalidOperationException("No native wall stacks/stories captured.");
        return (failures == 0, new { status = failures == 0 ? "captured_not_validated" : "partial_capture_failed",
            failed_parts = failures, stacks = stackNumber, stories = storyNumber,
            files, identities, quantity_cache_may_be_stale = true,
            cage_is_not_cut_schedule = true, complete_detailing = false, engineering_approval = false });
    }

    private static PropertyInfo StaticProperty(Assembly assembly, string type, string name) =>
        assembly.GetType(type, true)!.GetProperty(name, BindingFlags.Public | BindingFlags.Static)
        ?? throw new InvalidOperationException($"Missing static property {type}.{name}.");

    private static object Property(object value, string name) =>
        value.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.Instance)?.GetValue(value)
        ?? throw new InvalidOperationException($"Missing native value {value.GetType().FullName}.{name}.");

    private static object Invoke(object value, string name, params object[] args)
    {
        var method = value.GetType().GetMethod(name, BindingFlags.Public | BindingFlags.Instance,
            null, args.Select(a => a.GetType()).ToArray(), null)
            ?? throw new InvalidOperationException("Native method contract changed: " + name);
        return method.Invoke(value, args) ?? (method.ReturnType == typeof(void)
            ? true : throw new InvalidOperationException("Native method returned null: " + name));
    }

    private static IEnumerable<object> Items(object value)
    {
        if (value is not IEnumerable sequence) throw new InvalidOperationException("Expected native collection.");
        int count = 0;
        foreach (object? item in sequence)
        {
            if (++count > 10000) throw new InvalidOperationException("Native collection exceeds fixture capture budget.");
            yield return item ?? throw new InvalidOperationException("Null native collection item.");
        }
    }
}
