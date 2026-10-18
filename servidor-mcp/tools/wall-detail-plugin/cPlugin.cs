using System.Diagnostics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using ETABSv1;
using CDCRD.WallDetailProbe;

namespace CDCRD.WallDetailProbeV21;

/// <summary>Experimental, exact-build, read-only native detail capture. No model setters.</summary>
public sealed class cPlugin : cPluginContract
{
    private const string HostHash = "595E2B1C673E931B69413EBB846AA99A95365CEDB79755A32731F9322400EE24";
    private const string DetailHash = "1167DF9CB40536B85C5955CF4B06F3DCA6314A3267B98E0391D89CF59DFA666A";
    private static readonly Guid HostMvid = new("784404f4-c29d-492e-b3b9-5e5b53e633af");

    public int Info(ref string Text)
    {
        Text = "CDCRD V2.1 read-only wall detail, catalog and bar group capture for an authorized ETABS 23.3.0 test copy. " +
               "No geometry, reinforcement, analysis or model save operations. Does not approve detailing.";
        return 0;
    }

    public void Main(ref cSapModel SapModel, ref cPluginCallback ISapPlugin)
    {
        int error = 1;
        string pluginDirectory = Path.GetDirectoryName(typeof(cPlugin).Assembly.Location)!;
        string runId = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N")[..8];
        string? output = null;
        try
        {
            var options = JsonSerializer.Deserialize<ProbeOptions>(File.ReadAllText(Path.Combine(pluginDirectory, "probe-options.json")))
                          ?? throw new InvalidOperationException("Missing explicit fixture authorization.");
            using var process = Process.GetCurrentProcess();
            string model = SapModel.GetModelFilename(true);
            ProbeGate.Validate(options, model, process.Id, process.StartTime.ToUniversalTime(), SapModel.GetModelIsLocked());
            string program = "", version = "", level = "";
            if (SapModel.GetProgramInfo(ref program, ref version, ref level) != 0 || program != "ETABS" || version != "23.3.0")
                throw new InvalidOperationException("Unsupported ETABS version.");
            var assemblies = AppDomain.CurrentDomain.GetAssemblies();
            Assembly host = RequireAssembly(assemblies, "ETABS", HostHash);
            if (host.ManifestModule.ModuleVersionId != HostMvid) throw new InvalidOperationException("Host MVID mismatch.");
            Assembly detail = RequireAssembly(assemblies, "CSiNAWallStackDesigner", DetailHash);
            Assembly core = RequireAssembly(assemblies, "CSiNADetBase", "0DB0AFCDE330B40F5AA8BDF3CA8EAB38BDE72CB86C419226979A366686EA5608");
            Assembly design = RequireAssembly(assemblies, "CSiNADetDesign", "CD983AC8F5D1223A535F92511B2F289C9FECEE9FA03EE13FE0975A224BBAD84C");
            RequireAssembly(assemblies, "CSiDetGeomModel", "78575429D65BE5CDD44788F10C765F597AF9FC8D69EB4DF1AF83E89DAE6207A5");
            // Build-specific read-only accessor resolved by REA: a single static-field read.
            var getter = host.ManifestModule.ResolveMethod(0x06006732) as MethodInfo
                         ?? throw new InvalidOperationException("Native wall designer accessor is missing.");
            if (!getter.IsStatic || getter.GetParameters().Length != 0 ||
                getter.ReturnType.FullName != "CSI.CSiNAWallStackDesigner.WallStackDesigner")
                throw new InvalidOperationException("Native accessor contract changed.");
            object designer = getter.Invoke(null, null)
                              ?? throw new InvalidOperationException("Run native wall-stack detailing first.");
            if (designer.GetType().Assembly != detail) throw new InvalidOperationException("Designer assembly identity mismatch.");
            // Native getters depend on both global application contexts; restore both on every exit.
            using var context = NativeDetailCapture.Activate(detail, core, design);
            var capture = designer.GetType().GetMethod("GetDataObjet", BindingFlags.Instance | BindingFlags.Public,
                                                       null, Type.EmptyTypes, null)
                          ?? throw new InvalidOperationException("Native data serializer is unavailable.");
            object data = capture.Invoke(designer, null) ?? throw new InvalidOperationException("Native serializer returned null.");
            string nativeJson = data.GetType().GetProperty("JSonObject")?.GetValue(data) as string
                                ?? throw new InvalidOperationException("Native serializer did not provide JSON.");
            using var parsed = JsonDocument.Parse(nativeJson);
            if (parsed.RootElement.ValueKind != JsonValueKind.Object || !parsed.RootElement.EnumerateObject().Any())
                throw new InvalidOperationException("Empty native wall detail data.");
            string? wrapperUnits = data.GetType().GetProperty("DatabaseUnit")?.GetValue(data)?.ToString();
            string? modelUnits = parsed.RootElement.GetProperty("ModelInformation").GetProperty("DatabaseUnit").GetString();
            if ((int)SapModel.GetDatabaseUnits() != 9 || modelUnits != "N_mm_C" ||
                wrapperUnits?.Replace(" ", "") != "N,mm,C")
                throw new InvalidOperationException($"Native unit context not corroborated: OAPI={SapModel.GetDatabaseUnits()}, payload={modelUnits}, wrapper={wrapperUnits}.");
            if (SapModel.GetModelFilename(true) != model || !SapModel.GetModelIsLocked())
                throw new InvalidOperationException("Model context changed during capture.");
            output = Path.Combine(Path.GetDirectoryName(model)!, "wall-detail-capture-" + runId);
            Directory.CreateDirectory(output);
            File.WriteAllText(Path.Combine(output, "native-wall-detail.json"), nativeJson);
            var expanded = NativeDetailCapture.Capture(designer, detail, core, output);
            WriteJson(Path.Combine(output, "expanded-capture.json"), expanded.Manifest);
            if (SapModel.GetModelFilename(true) != model || !SapModel.GetModelIsLocked())
                throw new InvalidOperationException("Model context changed during expanded capture.");
            context.Dispose();
            WriteJson(Path.Combine(output, "capture.json"), new
            {
                status = expanded.Success ? "captured_not_validated" : "partial_capture_failed", model, process_id = process.Id,
                source = "WallStackDesigner.GetDataObjet.JSonObject", host_sha256 = HostHash,
                detail_sha256 = DetailHash, host_mvid = HostMvid,
                database_unit = wrapperUnits, serialized_model_unit = modelUnits, oapi_database_units_enum = 9,
                active_context_restored = true, native_labels_agree = true,
                geometry_unit_validation = "requires_external_OAPI_coordinate_match",
                display_unit = data.GetType().GetProperty("DisplayUnit")?.GetValue(data)?.ToString(),
                native_json_sha256 = Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(nativeJson))),
                complete_detailing = false, engineering_approval = false
            });
            error = expanded.Success ? 0 : 1;
        }
        catch (Exception exception)
        {
            WriteJson(Path.Combine(pluginDirectory, "failure-" + runId + ".json"), new
            { status = "failed", error = exception.ToString(), partial_output = output });
        }
        finally
        {
            ISapPlugin.Finish(error);
        }
    }

    private static Assembly RequireAssembly(Assembly[] assemblies, string name, string expectedHash)
    {
        var candidates = assemblies.Where(a => a.GetName().Name == name).ToArray();
        if (candidates.Length != 1) throw new InvalidOperationException($"Expected exactly one loaded {name} assembly.");
        using var stream = File.OpenRead(candidates[0].Location);
        if (Convert.ToHexString(SHA256.HashData(stream)) != expectedHash)
            throw new InvalidOperationException($"Unsupported {name} binary identity.");
        return candidates[0];
    }

    private static void WriteJson(string path, object value) =>
        File.WriteAllText(path, JsonSerializer.Serialize(value, new JsonSerializerOptions { WriteIndented = true }));
}
