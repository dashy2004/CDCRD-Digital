// Optional test-only hook. Does not inspect arbitrary native property getters.
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Autodesk.AutoCAD.Runtime;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
public class EspiralesQa
{
    [CommandMethod("CDCRDESPIRALESV1QA", CommandFlags.Session)]
    public void Arm()
    {
        var doc = App.DocumentManager.MdiActiveDocument;
        string root = Environment.GetEnvironmentVariable("CDCRD_GM_QA_ROOT");
        if (doc == null || Path.GetFileName(doc.Name) != "CDCRD_GM_RECOVERY_ESPIRALES.dwg" || Path.GetDirectoryName(doc.Name) != root)
            throw new InvalidOperationException("Identified QA copy required.");
        using var job = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "espirales-fault.json")));
        string stage = job.RootElement.GetProperty("stage").GetString();
        string output = job.RootElement.GetProperty("output").GetString();
        if (!new[] { "tangents-created", "scs-created", "geometry-verified" }.Contains(stage) || Path.GetFileName(output) != output || !output.EndsWith(".json"))
            throw new ArgumentException("Invalid QA stage/output.");
        string dest = Path.Combine(root, output); if (File.Exists(dest)) throw new IOException("Receipt exists.");
        var module = AppDomain.CurrentDomain.GetAssemblies().Single(a => a.GetName().Name == "Cdcrd.Espirales.V1");
        var field = module.GetType("Cdcrd.Espirales.SpiralService").GetField("QaCheckpoint", BindingFlags.Static | BindingFlags.NonPublic);
        if (field.GetValue(null) != null) throw new InvalidOperationException("Failure already armed.");
        Action<string> fail = s => { if (s == stage) { field.SetValue(null, null); throw new InvalidOperationException("CDCRD_QA_SPIRAL_FAILURE:" + stage); } };
        field.SetValue(null, fail);
        File.WriteAllText(dest, JsonSerializer.Serialize(new { armed = stage, one_shot = true }));
    }
}
