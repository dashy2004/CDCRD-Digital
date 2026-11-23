// Optional module: NETLOAD in the existing Civil process; no listener or CAD launch.
// Geotechnical Modeler projects without its dialogs. Requests and receipts live in a fixed per-user
// folder, because the GM database is per machine and not tied to one drawing.
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

namespace Cdcrd.Geotecnia;

public class Commands : IExtensionApplication
{
    internal const string Version = "0.2.0";
    internal const string Module = "cdcrd-geotecnia";
    internal const string BaseName = "Cdcrd.Geotecnia.V1";
    internal const string BaseCommand = "CDCRDGEOTECNIAV1";
    internal static string Root => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "CdcrdCivil3dBridge", "geotecnia");
    // A build compiled as Cdcrd.Geotecnia.V1b additionally registers CDCRDGEOTECNIAV1B, so a
    // rebuilt module can be exercised next to the one already loaded in the same process.
    internal static string AliasSuffix
    {
        get
        {
            string name = typeof(Commands).Assembly.GetName().Name;
            string suffix = name.StartsWith(BaseName, StringComparison.Ordinal) ? name.Substring(BaseName.Length) : "";
            if (!Regex.IsMatch(suffix, "^[A-Za-z0-9]{0,8}$")) throw new InvalidOperationException("Nombre de ensamblado no admitido: " + name);
            return suffix.ToUpperInvariant();
        }
    }

    [CommandMethod("CDCRDGEOTECNIA", BaseCommand, CommandFlags.Modal)]
    public void Run() => RunCore(BaseCommand);

    public void Initialize()
    {
        try
        {
            string suffix = AliasSuffix;
            if (suffix.Length > 0) Autodesk.AutoCAD.Internal.Utils.AddCommand("CDCRDGEOTECNIA", BaseCommand + suffix, BaseCommand + suffix, CommandFlags.Modal, () => RunCore(BaseCommand + suffix));
        }
        catch (Exception ex) { Say("alias no registrado: " + ex.Message); }
    }
    public void Terminate() { }

    // The active document may have changed or closed since the command started: always ask again.
    private static void Say(string text)
    {
        try { App.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nGeotecnia: " + text + "\n"); }
        catch (Exception) { /* no document to write to; the receipt carries the outcome */ }
    }

    private static void RunCore(string commandName)
    {
        // Never let a transport error reach AutoCAD's unhandled-exception dialog.
        try { ExecuteCommand(commandName); }
        catch (Exception ex) { Say("sin recibo final; no reintentar. " + ex.Message); }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private static void ExecuteCommand(string commandName)
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
        if (!Directory.Exists(root)) throw new DirectoryNotFoundException("Falta la carpeta de intercambio " + root);
        string prefix = Path.Combine(root, Module + "-" + key);
        string receipt = prefix + ".result.json";
        // Immutable claim: a queued or repeated command never executes the same request twice.
        if (File.Exists(receipt) || File.Exists(prefix + ".started")) { Say("solicitud ya reclamada; consultar recibo."); return; }
        object result = null; string error = null; bool changed = false;
        try
        {
            byte[] bytes = File.ReadAllBytes(prefix + ".request.json");
            if (bytes.Length > 100000 || Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant() != digest)
                throw new ArgumentException("Solicitud alterada o demasiado grande.");
            var request = JsonNode.Parse(Encoding.UTF8.GetString(bytes)) as JsonObject ?? throw new ArgumentException("Objeto JSON requerido.");
            using (new FileStream(prefix + ".started", FileMode.CreateNew, FileAccess.Write)) { }
            result = GeotecniaService.Execute(request, out changed);
        }
        catch (Exception ex) { error = ex.GetBaseException().Message; }
        string active = null; int open = -1;
        try { active = App.DocumentManager.MdiActiveDocument?.Name; open = App.DocumentManager.Count; } catch (Exception ex) { error ??= "Estado final no legible: " + ex.Message; }
        // committed: true when the GM database, the drawing's GM settings or the session (GM started) changed.
        var payload = new { id = key, sha256 = digest, module = Module, version = Version, pid = Environment.ProcessId, ok = error == null, committed = changed, error,
            activo = active, abiertos = open, result };
        string temp = receipt + ".tmp";
        File.WriteAllText(temp, JsonSerializer.Serialize(payload), new UTF8Encoding(false));
        File.Move(temp, receipt, false);
        Say(error ?? (changed ? "aplicado" : "leido"));
    }
}
