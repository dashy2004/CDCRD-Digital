using System;
using System.IO;
using System.Text.Json;
using Autodesk.AutoCAD.Runtime;
using Autodesk.AutoCAD.EditorInput;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;
namespace Cdcrd.Earthworks;

public sealed class Commands
{
    [CommandMethod("CDCRDEARTHWORKS")]
    public void Run()
    {
        var editor = AcApp.DocumentManager.MdiActiveDocument.Editor;
        var answer = editor.GetString(new PromptStringOptions("\nAbsolute request JSON path: ") { AllowSpaces = true }); if (answer.Status != PromptStatus.OK) return;
        Request request = null; string receipt = null;
        try
        {
            request = JsonSerializer.Deserialize<Request>(File.ReadAllText(answer.StringResult.Trim('"')), TerrainApi.JsonOptions);
            if (request == null || !Path.IsPathFullyQualified(request.OutputDirectory) || string.IsNullOrWhiteSpace(request.RunId) || request.RunId.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0) throw new ArgumentException("Absolute output directory and safe runId required");
            if (request.Action != "build" && request.Action != "sections" && request.Action != "audit") throw new ArgumentException("Unknown action");
            Directory.CreateDirectory(request.OutputDirectory); receipt = Path.Combine(request.OutputDirectory, request.RunId + "-" + request.Action + ".json");
            if (File.Exists(receipt)) throw new IOException("Receipt already exists; inspect previous outcome before using a new runId");
            object result = request.Action switch { "build" => TerrainApi.Build(request), "sections" => TerrainApi.Sections(request), "audit" => TerrainApi.Audit(request), _ => throw new ArgumentException("Unknown action") };
            File.WriteAllText(receipt, JsonSerializer.Serialize(new { ok = true, assembly = typeof(TerrainApi).Assembly.FullName, utc = DateTime.UtcNow, action = request.Action, result }, TerrainApi.JsonOptions)); editor.WriteMessage("\nCDCRD Terrain Tools OK: " + receipt);
        }
        catch (System.Exception e)
        {
            // A failed receipt is never overwritten; a duplicate request must remain visible.
            if (receipt != null && !File.Exists(receipt)) File.WriteAllText(receipt, JsonSerializer.Serialize(new { ok = false, error = e.ToString() }, TerrainApi.JsonOptions));
            editor.WriteMessage("\nCDCRD Terrain Tools ERROR: " + e.Message);
        }
    }
}
