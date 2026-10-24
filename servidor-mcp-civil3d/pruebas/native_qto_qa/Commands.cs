// Optional test-only hook. Does not inspect arbitrary native property getters.
using System;
using System.IO;
using System.Runtime.CompilerServices;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Autodesk.AutoCAD.Runtime;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
public class QtoQa
{
    [CommandMethod("CDCRDQTOV8QA", CommandFlags.Session)]
    public void Arm()
    {
        try { ArmCore(); }
        catch (System.Exception ex) { try { App.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nQA no armado: "+ex.Message+"\n"); } catch (System.Exception) { } }
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    private void ArmCore()
    {
        var doc = App.DocumentManager.MdiActiveDocument;
        string root = Environment.GetEnvironmentVariable("CDCRD_GM_QA_ROOT");
        if (doc == null || Path.GetFileName(doc.Name) != "CDCRD_GM_RECOVERY_QTO.dwg" || Path.GetDirectoryName(doc.Name) != root)
            throw new InvalidOperationException("Identified QA copy required.");
        using var job = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "qto-fault.json")));
        string stage = job.RootElement.GetProperty("stage").GetString();
        string output = job.RootElement.GetProperty("output").GetString();
        if (!new[] { "volume-created", "group-created", "samples-created", "materials-created", "record-written" }.Contains(stage) || Path.GetFileName(output) != output || !output.EndsWith(".json"))
            throw new ArgumentException("Invalid QA stage/output.");
        string dest = Path.Combine(root, output); if (File.Exists(dest)) throw new IOException("Receipt exists.");
        var module = AppDomain.CurrentDomain.GetAssemblies().Single(a => a.GetName().Name == "Cdcrd.Qto.V8");
        var field = module.GetType("Cdcrd.Qto.QtoService").GetField("QaCheckpoint", BindingFlags.Static | BindingFlags.NonPublic);
        if (field.GetValue(null) != null) throw new InvalidOperationException("Failure already armed.");
        int remaining=job.RootElement.TryGetProperty("occurrence",out var n)?n.GetInt32():1;
        if(remaining<1||remaining>20)throw new ArgumentException("Invalid occurrence");
        Action<string> fail = s => { if (s == stage && --remaining==0) { field.SetValue(null, null); throw new InvalidOperationException("CDCRD_QA_QTO_FAILURE:" + stage); } };
        field.SetValue(null, fail);
        File.WriteAllText(dest, JsonSerializer.Serialize(new { armed = stage, one_shot = true }));
    }
}
