// Optional module: NETLOAD in the existing Civil process; no listener or CAD launch.
// Same immutable-receipt transport as the targets/corredores modules.
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

namespace Cdcrd.Tipologias;

public class Commands : IExtensionApplication
{
    internal const string Version = "0.1.0";
    internal const string Module = "cdcrd-tipologias";
    internal const string BaseName = "Cdcrd.Tipologias.V1";
    internal const string BaseCommand = "CDCRDTIPOLOGIASV1";
    // The exchange directory is the DWG directory, shared with the bridge and the QA harness.
    internal static string Root => Path.GetDirectoryName(App.DocumentManager.MdiActiveDocument.Name);
    // The command name follows the assembly name: a build compiled as Cdcrd.Tipologias.V1b
    // registers CDCRDTIPOLOGIASV1B, so a rebuilt module can load next to an earlier one
    // in the same Civil process during QA. The normal build registers CDCRDTIPOLOGIASV1.
    internal static string CommandName
    {
        get
        {
            string name = typeof(Commands).Assembly.GetName().Name;
            string suffix = name.StartsWith(BaseName, StringComparison.Ordinal) ? name.Substring(BaseName.Length) : "";
            if (!Regex.IsMatch(suffix, "^[A-Za-z0-9]{0,8}$")) throw new InvalidOperationException("Nombre de ensamblado no admitido: " + name);
            return BaseCommand + suffix.ToUpperInvariant();
        }
    }

    public void Initialize()
    {
        string name = CommandName;
        Autodesk.AutoCAD.Internal.Utils.AddCommand("CDCRDTIPOLOGIAS", name, name, CommandFlags.Session, RunCore);
    }
    public void Terminate() { }

    private static void RunCore()
    {
        // Never let a transport error reach AutoCAD's unhandled-exception dialog.
        try { ExecuteCommand(); }
        catch (Exception ex)
        {
            try { App.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nTipologias: sin recibo final; no reintentar. " + ex.Message + "\n"); }
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
        string prefix = Path.Combine(root, Module + "-" + key);
        string receipt = prefix + ".result.json";
        // Immutable claim: a queued or repeated command never executes the same request twice.
        if (File.Exists(receipt) || File.Exists(prefix + ".started"))
        { ed.WriteMessage("\nSolicitud ya reclamada; consultar recibo.\n"); return; }
        object result = null; string error = null; bool committed = false;
        try
        {
            byte[] bytes = File.ReadAllBytes(prefix + ".request.json");
            if (bytes.Length > 200000 || Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant() != digest)
                throw new ArgumentException("Solicitud alterada o demasiado grande.");
            var request = JsonNode.Parse(Encoding.UTF8.GetString(bytes)) as JsonObject ?? throw new ArgumentException("Objeto JSON requerido.");
            using (new FileStream(prefix + ".started", FileMode.CreateNew, FileAccess.Write)) { }
            result = TipologiaService.Execute(request, out committed);
        }
        catch (Exception ex) { error = ex.GetBaseException().Message; }
        var payload = new { id = key, sha256 = digest, module = Module, version = Version,
            pid = Environment.ProcessId, ok = error == null, committed, error, result };
        string temp = receipt + ".tmp";
        File.WriteAllText(temp, JsonSerializer.Serialize(payload), new UTF8Encoding(false));
        File.Move(temp, receipt, false);
        ed.WriteMessage("\nTipologias: " + (error ?? (committed ? "aplicado" : "leido/simulado")) + "\n");
    }
}
