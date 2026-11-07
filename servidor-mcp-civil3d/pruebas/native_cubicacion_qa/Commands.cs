// Optional test-only harness for the cubicacion module. Never installed by the normal build.
// One job, read from cubicacion-qa.json next to the identified QA copy: arm a one-shot
// failure at a QaCheckpoint stage of Cdcrd.Cubicacion.V1 so the rollback can be observed.
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Autodesk.AutoCAD.Runtime;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using Exception = System.Exception;

public class CubicacionQa : IExtensionApplication
{
    const string BaseName = "Cdcrd.CubicacionV1Qa", BaseCommand = "CDCRDCUBICACIONV1QA";

    // Command name follows the assembly name (Cdcrd.CubicacionV1QaB -> CDCRDCUBICACIONV1QAB) so a
    // rebuilt harness can be loaded next to an earlier build in the same process.
    public void Initialize()
    {
        try
        {
            string name = typeof(CubicacionQa).Assembly.GetName().Name;
            string suffix = name.StartsWith(BaseName, StringComparison.Ordinal) ? name.Substring(BaseName.Length).ToUpperInvariant() : "";
            Autodesk.AutoCAD.Internal.Utils.AddCommand("CDCRDCUBICACIONQA", BaseCommand + suffix, BaseCommand + suffix, CommandFlags.Session, Run);
        }
        catch (Exception ex) { try { App.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nQA cubicacion: comando no registrado: " + ex.Message + "\n"); } catch (Exception) { } }
    }
    public void Terminate() { }

    private void Run()
    {
        try { Core(); }
        catch (Exception ex) { try { App.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nQA cubicacion: " + ex.Message + "\n"); } catch (Exception) { } }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private void Core()
    {
        var doc = App.DocumentManager.MdiActiveDocument;
        if (doc == null || !Path.GetFileName(doc.Name).StartsWith("CDCRD_QA_CUBICACION", StringComparison.Ordinal))
            throw new InvalidOperationException("Identified QA copy required.");
        string root = Path.GetDirectoryName(doc.Name);
        using var job = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "cubicacion-qa.json")));
        var r = job.RootElement;
        string output = r.GetProperty("output").GetString();
        if (Path.GetFileName(output) != output || !output.EndsWith(".json")) throw new ArgumentException("Invalid QA output.");
        string dest = Path.Combine(root, output); if (File.Exists(dest)) throw new IOException("Receipt exists.");
        string stage = r.GetProperty("stage").GetString();
        if (!new[] { "params-written", "datum-added", "corridor-rebuilt", "surfaces-rebuilt", "volume-created", "record-written" }.Contains(stage)) throw new ArgumentException("Invalid QA stage.");
        var module = AppDomain.CurrentDomain.GetAssemblies().Last(a => a.GetName().Name.StartsWith("Cdcrd.Cubicacion.V1", StringComparison.Ordinal));
        var field = module.GetType("Cdcrd.Cubicacion.CubicacionService").GetField("QaCheckpoint", BindingFlags.Static | BindingFlags.NonPublic);
        if (field.GetValue(null) != null) throw new InvalidOperationException("Failure already armed.");
        int remaining = r.TryGetProperty("occurrence", out var n) ? n.GetInt32() : 1;
        if (remaining < 1 || remaining > 20) throw new ArgumentException("Invalid occurrence");
        Action<string> fail = s => { if (s == stage && --remaining == 0) { field.SetValue(null, null); throw new InvalidOperationException("CDCRD_QA_CUBICACION_FAILURE:" + stage); } };
        field.SetValue(null, fail);
        File.WriteAllText(dest, JsonSerializer.Serialize(new { armed = stage, one_shot = true }));
    }
}
