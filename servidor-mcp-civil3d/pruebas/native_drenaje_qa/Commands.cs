// Optional test-only harness for the drainage module. Never installed by the normal build.
// Job "fault" (read from drenaje-qa.json inside the identified copy's folder): arm a one-shot
// failure at a QaCheckpoint stage of Cdcrd.Drenaje.V1 so the simulated/committed creation
// aborts after partial work and the transaction rollback can be audited.
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Autodesk.AutoCAD.Runtime;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using Exception = System.Exception;

public class DrenajeQa : IExtensionApplication
{
    const string BaseName = "Cdcrd.DrenajeV1Qa", BaseCommand = "CDCRDDRENAJEV1QA";
    static readonly string[] Stages = { "network-created", "structures-added", "pipes-added", "pipes-connected", "record-written" };

    // Command name follows the assembly name (Cdcrd.DrenajeV1QaB -> CDCRDDRENAJEV1QAB) so a
    // rebuilt harness can be loaded next to an earlier build in the same process.
    public void Initialize()
    {
        string name = typeof(DrenajeQa).Assembly.GetName().Name;
        string suffix = name.StartsWith(BaseName, StringComparison.Ordinal) ? name.Substring(BaseName.Length).ToUpperInvariant() : "";
        Autodesk.AutoCAD.Internal.Utils.AddCommand("CDCRDDRENAJEQA", BaseCommand + suffix, BaseCommand + suffix, CommandFlags.Session, Run);
    }
    public void Terminate() { }

    private void Run()
    {
        try { Core(); }
        catch (Exception ex) { try { App.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nQA drenaje: " + ex.Message + "\n"); } catch (Exception) { } }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private void Core()
    {
        var doc = App.DocumentManager.MdiActiveDocument;
        if (doc == null || !Path.GetFileName(doc.Name).StartsWith("CDCRD_QA_DRENAJE", StringComparison.Ordinal))
            throw new InvalidOperationException("Identified QA copy required.");
        string root = Path.GetDirectoryName(doc.Name);
        using var job = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "drenaje-qa.json")));
        var r = job.RootElement;
        string output = r.GetProperty("output").GetString();
        if (Path.GetFileName(output) != output || !output.EndsWith(".json")) throw new ArgumentException("Invalid QA output.");
        string dest = Path.Combine(root, output); if (File.Exists(dest)) throw new IOException("Receipt exists.");
        if (r.GetProperty("action").GetString() != "fault") throw new ArgumentException("Unknown QA action.");
        string stage = r.GetProperty("stage").GetString();
        if (!Stages.Contains(stage)) throw new ArgumentException("Invalid QA stage.");
        var module = AppDomain.CurrentDomain.GetAssemblies().Last(a => a.GetName().Name.StartsWith("Cdcrd.Drenaje.V1", StringComparison.Ordinal));
        var field = module.GetType("Cdcrd.Drenaje.DrenajeService").GetField("QaCheckpoint", BindingFlags.Static | BindingFlags.NonPublic);
        if (field.GetValue(null) != null) throw new InvalidOperationException("Failure already armed.");
        int remaining = r.TryGetProperty("occurrence", out var n) ? n.GetInt32() : 1;
        if (remaining < 1 || remaining > 20) throw new ArgumentException("Invalid occurrence");
        Action<string> fail = s => { if (s == stage && --remaining == 0) { field.SetValue(null, null); throw new InvalidOperationException("CDCRD_QA_DRENAJE_FAILURE:" + stage); } };
        field.SetValue(null, fail);
        File.WriteAllText(dest, JsonSerializer.Serialize(new { armed = stage, one_shot = true }));
    }
}
