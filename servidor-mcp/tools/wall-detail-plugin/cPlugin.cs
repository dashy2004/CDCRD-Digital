using System.Diagnostics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using ETABSv1;

namespace CDCRD.WallDetailProbe;

/// <summary>Experimental, exact-build, read-only native detail capture. No model setters.</summary>
public sealed class cPlugin : cPluginContract
{
    private const string HostHash = "595E2B1C673E931B69413EBB846AA99A95365CEDB79755A32731F9322400EE24";
    private const string DetailHash = "1167DF9CB40536B85C5955CF4B06F3DCA6314A3267B98E0391D89CF59DFA666A";
    private static readonly Guid HostMvid = new("784404f4-c29d-492e-b3b9-5e5b53e633af");

    public int Info(ref string Text)
    {
        Text = "CDCRD read-only wall detail capture for a specifically authorized ETABS 23.3.0 test copy. " +
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
            // Build-specific read-only accessor resolved by REA: a single static-field read.
            var getter = host.ManifestModule.ResolveMethod(0x06006732) as MethodInfo
                         ?? throw new InvalidOperationException("Native wall designer accessor is missing.");
            if (!getter.IsStatic || getter.GetParameters().Length != 0 ||
                getter.ReturnType.FullName != "CSI.CSiNAWallStackDesigner.WallStackDesigner")
                throw new InvalidOperationException("Native accessor contract changed.");
            object designer = getter.Invoke(null, null)
                              ?? throw new InvalidOperationException("Run native wall-stack detailing first.");
            if (designer.GetType().Assembly != detail) throw new InvalidOperationException("Designer assembly identity mismatch.");
            var capture = designer.GetType().GetMethod("GetDataObjet", BindingFlags.Instance | BindingFlags.Public,
                                                       null, Type.EmptyTypes, null)
                          ?? throw new InvalidOperationException("Native data serializer is unavailable.");
            object data = capture.Invoke(designer, null) ?? throw new InvalidOperationException("Native serializer returned null.");
            string nativeJson = data.GetType().GetProperty("JSonObject")?.GetValue(data) as string
                                ?? throw new InvalidOperationException("Native serializer did not provide JSON.");
            using var parsed = JsonDocument.Parse(nativeJson);
            if (parsed.RootElement.ValueKind != JsonValueKind.Object || !parsed.RootElement.EnumerateObject().Any())
                throw new InvalidOperationException("Empty native wall detail data.");
            if (SapModel.GetModelFilename(true) != model || !SapModel.GetModelIsLocked())
                throw new InvalidOperationException("Model context changed during capture.");
            output = Path.Combine(Path.GetDirectoryName(model)!, "wall-detail-capture-" + runId);
            Directory.CreateDirectory(output);
            File.WriteAllText(Path.Combine(output, "native-wall-detail.json"), nativeJson);
            WriteJson(Path.Combine(output, "capture.json"), new
            {
                status = "captured_not_validated", model, process_id = process.Id,
                source = "WallStackDesigner.GetDataObjet.JSonObject", host_sha256 = HostHash,
                detail_sha256 = DetailHash, host_mvid = HostMvid,
                database_unit = data.GetType().GetProperty("DatabaseUnit")?.GetValue(data)?.ToString(),
                display_unit = data.GetType().GetProperty("DisplayUnit")?.GetValue(data)?.ToString(),
                native_json_sha256 = Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(nativeJson))),
                complete_detailing = false, engineering_approval = false
            });
            error = 0;
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
