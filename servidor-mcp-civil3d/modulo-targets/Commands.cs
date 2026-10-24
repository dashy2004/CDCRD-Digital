// Optional module: NETLOAD in the existing Civil process; no listener or CAD launch.
using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Runtime.CompilerServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using Exception = System.Exception;

namespace Cdcrd.Targets;

public class Commands
{
    internal const string Version = "0.1.1";
    // Use the actual DWG directory, already shared with the bridge/native QA.
    // Do not derive the exchange location independently from process profiles.
    internal static string Root => Path.GetDirectoryName(App.DocumentManager.MdiActiveDocument.Name);

    [CommandMethod("CDCRDTARGETSV2", CommandFlags.Session)]
    public void Run()
    {
        // Includes prompt, filesystem and JIT failures: never let an extension
        // transport error escape to AutoCAD's unhandled-exception modal dialog.
        try { ExecuteCommand(); }
        catch (Exception ex)
        {
            try { App.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nTargets: sin recibo final; no reintentar. " + ex.Message + "\n"); }
            catch (Exception) { /* CAD may already be closing; no further calls. */ }
        }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void ExecuteCommand()
    {
        var ed = App.DocumentManager.MdiActiveDocument?.Editor;
        if (ed == null) return;
        var id = ed.GetString(new PromptStringOptions("Solicitud: ") { AllowSpaces = false });
        var hash = ed.GetString(new PromptStringOptions("SHA256: ") { AllowSpaces = false });
        if (id.Status != PromptStatus.OK || hash.Status != PromptStatus.OK ||
            !Regex.IsMatch(id.StringResult, "^[a-f0-9]{32}$") || !Regex.IsMatch(hash.StringResult, "^[a-f0-9]{64}$"))
            return;
        string key = id.StringResult, digest = hash.StringResult;
        string root = Root;
        if (!Path.IsPathFullyQualified(root) || !Directory.Exists(root))
            throw new DirectoryNotFoundException("El DWG debe estar guardado en una carpeta accesible.");
        string prefix = Path.Combine(root, "cdcrd-targets-" + key);
        string receipt = prefix + ".result.json";
        // Immutable claim prevents a queued/repeated command from executing twice,
        // even after a timeout or process restart. No automatic write retries.
        if (File.Exists(receipt) || File.Exists(prefix + ".started"))
        { ed.WriteMessage("\nSolicitud ya reclamada; consultar recibo.\n"); return; }
        object result = null; string error = null; bool committed = false;
        try
        {
            byte[] bytes = File.ReadAllBytes(prefix + ".request.json");
            if (bytes.Length > 100000 || Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant() != digest)
                throw new ArgumentException("Solicitud alterada o demasiado grande.");
            var request = JsonNode.Parse(Encoding.UTF8.GetString(bytes)) as JsonObject ?? throw new ArgumentException("Objeto JSON requerido.");
            using (new FileStream(prefix + ".started", FileMode.CreateNew, FileAccess.Write)) { }
            result = TargetService.Execute(request, out committed);
        }
        catch (Exception ex) { error = ex.GetBaseException().Message; }
        var payload = new { id = key, sha256 = digest, module = "cdcrd-targets", version = Version,
            pid = Environment.ProcessId, ok = error == null, committed, error, result };
        // Write and rename in the same directory; readers never see partial JSON.
        string temp = receipt + ".tmp";
        File.WriteAllText(temp, JsonSerializer.Serialize(payload), new UTF8Encoding(false));
        File.Move(temp, receipt, false);
        ed.WriteMessage("\nTargets: " + (error ?? (committed ? "aplicado" : "leido/simulado")) + "\n");
    }
}
