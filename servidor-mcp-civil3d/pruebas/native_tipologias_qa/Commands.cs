// Optional test-only harness for the typology module. Never installed by the normal build.
// Two jobs, both read from tipologias-qa.json inside CDCRD_GM_QA_ROOT:
//  - "fault": arm a one-shot failure at a QaCheckpoint stage of Cdcrd.Tipologias.V1.
//  - "avisos": count first-chance exceptions "Add param returned null!" raised by
//    AeccDbMgd while the harness reproduces one of four operations on the identified copy.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.ExceptionServices;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil.Runtime;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivAssembly = Autodesk.Civil.DatabaseServices.Assembly;
using Exception = System.Exception;

public class TipologiasQa : IExtensionApplication
{
    static readonly JsonSerializerOptions Json = new JsonSerializerOptions { WriteIndented = true };
    const string BaseName = "Cdcrd.TipologiasV1Qa", BaseCommand = "CDCRDTIPOLOGIASV1QA";

    // Command name follows the assembly name (Cdcrd.TipologiasV1QaB -> CDCRDTIPOLOGIASV1QAB) so a
    // rebuilt harness can be loaded next to an earlier build in the same process.
    public void Initialize()
    {
        string name = typeof(TipologiasQa).Assembly.GetName().Name;
        string suffix = name.StartsWith(BaseName, StringComparison.Ordinal) ? name.Substring(BaseName.Length).ToUpperInvariant() : "";
        Autodesk.AutoCAD.Internal.Utils.AddCommand("CDCRDTIPOLOGIASQA", BaseCommand + suffix, BaseCommand + suffix, CommandFlags.Session, Run);
    }
    public void Terminate() { }

    private void Run()
    {
        try { Core(); }
        catch (Exception ex) { try { App.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nQA tipologias: " + ex.Message + "\n"); } catch (Exception) { } }
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    private void Core()
    {
        var doc = App.DocumentManager.MdiActiveDocument;
        // The identified copy's own folder is the QA root: the harness cannot read an
        // environment variable set after the Civil process started.
        if (doc == null || !Path.GetFileName(doc.Name).StartsWith("CDCRD_QA_TIPOLOGIAS", StringComparison.Ordinal))
            throw new InvalidOperationException("Identified QA copy required.");
        string root = Path.GetDirectoryName(doc.Name);
        using var job = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "tipologias-qa.json")));
        var r = job.RootElement;
        string output = r.GetProperty("output").GetString();
        if (Path.GetFileName(output) != output || !output.EndsWith(".json")) throw new ArgumentException("Invalid QA output.");
        string dest = Path.Combine(root, output); if (File.Exists(dest)) throw new IOException("Receipt exists.");
        string action = r.GetProperty("action").GetString();
        object result = action == "fault" ? Arm(r) : action == "avisos" ? Warnings(doc.Database, r) : throw new ArgumentException("Unknown QA action.");
        File.WriteAllText(dest, JsonSerializer.Serialize(result, Json));
    }

    private static object Arm(JsonElement r)
    {
        string stage = r.GetProperty("stage").GetString();
        if (!new[] { "variant-curb-added", "regions-split", "targets-set", "corridor-rebuilt", "record-written" }.Contains(stage)) throw new ArgumentException("Invalid QA stage.");
        var module = AppDomain.CurrentDomain.GetAssemblies().Last(a => a.GetName().Name.StartsWith("Cdcrd.Tipologias.V1", StringComparison.Ordinal));
        var field = module.GetType("Cdcrd.Tipologias.TipologiaService").GetField("QaCheckpoint", BindingFlags.Static | BindingFlags.NonPublic);
        if (field.GetValue(null) != null) throw new InvalidOperationException("Failure already armed.");
        int remaining = r.TryGetProperty("occurrence", out var n) ? n.GetInt32() : 1;
        if (remaining < 1 || remaining > 20) throw new ArgumentException("Invalid occurrence");
        Action<string> fail = s => { if (s == stage && --remaining == 0) { field.SetValue(null, null); throw new InvalidOperationException("CDCRD_QA_TIPOLOGIA_FAILURE:" + stage); } };
        field.SetValue(null, fail);
        return new { armed = stage, one_shot = true };
    }

    // Reproduces one operation while counting the runtime's "Add param returned null!" exceptions.
    private static object Warnings(Database db, JsonElement r)
    {
        string mode = r.GetProperty("mode").GetString();
        var handles = r.TryGetProperty("corridors", out var hs) ? hs.EnumerateArray().Select(x => x.GetString()).ToArray() : Array.Empty<string>();
        var byPart = new Dictionary<string, int>(); var samples = new List<object>(); var others = new Dictionary<string, int>();
        string current = "(ninguno)"; int total = 0;
        EventHandler<FirstChanceExceptionEventArgs> handler = (s, e) =>
        {
            string key = e.Exception.GetType().Name + ": " + e.Exception.Message;
            if (e.Exception.Message.Contains("Add param returned null", StringComparison.Ordinal))
            {
                total++; byPart[current] = byPart.GetValueOrDefault(current) + 1;
                if (samples.Count < 3) samples.Add(new { part = current, type = e.Exception.GetType().FullName, stack = e.Exception.StackTrace });
            }
            else others[key] = others.GetValueOrDefault(key) + 1;
        };
        AppDomain.CurrentDomain.FirstChanceException += handler;
        try
        {
            int described = 0, subs = 0;
            if (mode == "side_describe" || mode == "live_describe")
            {
                Database side = null;
                if (mode == "side_describe")
                {
                    side = new Database(false, true);
                    side.ReadDwgFile(App.DocumentManager.MdiActiveDocument.Name, FileOpenMode.OpenForReadAndAllShare, false, null);
                    side.CloseInput(true);
                }
                var target = side ?? db;
                using (var tr = target.TransactionManager.StartTransaction())
                {
                    var civil = CivilDocument.GetCivilDocument(target);
                    foreach (ObjectId id in civil.CorridorCollection)
                    {
                        var c = (Corridor)tr.GetObject(id, OpenMode.ForRead);
                        if (handles.Length > 0 && !handles.Contains(c.Handle.ToString(), StringComparer.OrdinalIgnoreCase)) continue;
                        foreach (Baseline b in c.Baselines) foreach (BaselineRegion reg in b.BaselineRegions)
                        {
                            var a = (CivAssembly)tr.GetObject(reg.AssemblyId, OpenMode.ForRead);
                            foreach (var sid in a.Groups.Cast<AssemblyGroup>().SelectMany(g => g.GetSubassemblyIds().Cast<ObjectId>()))
                            {
                                var sub = (Subassembly)tr.GetObject(sid, OpenMode.ForRead);
                                current = sub.Name.Split(" - ")[0];
                                described++;
                                foreach (ParamDouble p in sub.ParamsDouble) _ = p.Value; // same read the audit performed
                            }
                        }
                    }
                    tr.Abort();
                }
                side?.Dispose();
            }
            else if (mode == "side_targets" || mode == "live_targets")
            {
                // The one-off audit also asked every region for its targets from the side database.
                Database side = null;
                if (mode == "side_targets")
                {
                    side = new Database(false, true);
                    side.ReadDwgFile(App.DocumentManager.MdiActiveDocument.Name, FileOpenMode.OpenForReadAndAllShare, false, null);
                    side.CloseInput(true);
                }
                var target = side ?? db;
                using (var tr = target.TransactionManager.StartTransaction())
                {
                    var civil = CivilDocument.GetCivilDocument(target);
                    foreach (ObjectId id in civil.CorridorCollection)
                    {
                        var c = (Corridor)tr.GetObject(id, OpenMode.ForRead);
                        if (handles.Length > 0 && !handles.Contains(c.Handle.ToString(), StringComparer.OrdinalIgnoreCase)) continue;
                        foreach (Baseline b in c.Baselines) foreach (BaselineRegion reg in b.BaselineRegions)
                        {
                            var a = (CivAssembly)tr.GetObject(reg.AssemblyId, OpenMode.ForRead);
                            current = "region " + reg.Name + " / " + a.Name; subs++;
                            described += reg.GetTargets().Cast<SubassemblyTargetInfo>().Count();
                        }
                    }
                    tr.Abort();
                }
                side?.Dispose();
            }
            else if (mode == "run_parts")
            {
                using (App.DocumentManager.MdiActiveDocument.LockDocument())
                using (var tr = db.TransactionManager.StartTransaction())
                {
                    var civil = CivilApplication.ActiveDocument;
                    foreach (ObjectId id in civil.CorridorCollection)
                    {
                        var c = (Corridor)tr.GetObject(id, OpenMode.ForRead);
                        if (handles.Length > 0 && !handles.Contains(c.Handle.ToString(), StringComparer.OrdinalIgnoreCase)) continue;
                        foreach (Baseline b in c.Baselines) foreach (BaselineRegion reg in b.BaselineRegions)
                        {
                            var a = (CivAssembly)tr.GetObject(reg.AssemblyId, OpenMode.ForRead);
                            foreach (var sid in a.Groups.Cast<AssemblyGroup>().SelectMany(g => g.GetSubassemblyIds().Cast<ObjectId>()))
                            {
                                var sub = (Subassembly)tr.GetObject(sid, OpenMode.ForWrite);
                                current = sub.Name.Split(" - ")[0]; subs++;
                                sub.Run(); // standalone preview run, as the one-off tool did after copying params
                            }
                        }
                    }
                    tr.Abort();
                }
            }
            else if (mode == "rebuild")
            {
                using (App.DocumentManager.MdiActiveDocument.LockDocument())
                using (var tr = db.TransactionManager.StartTransaction())
                {
                    var civil = CivilApplication.ActiveDocument;
                    foreach (ObjectId id in civil.CorridorCollection)
                    {
                        var c = (Corridor)tr.GetObject(id, OpenMode.ForWrite);
                        if (handles.Length > 0 && !handles.Contains(c.Handle.ToString(), StringComparer.OrdinalIgnoreCase)) continue;
                        current = "corredor " + c.Handle; subs++;
                        c.Rebuild();
                    }
                    tr.Abort();
                }
            }
            else throw new ArgumentException("Unknown mode.");
            return new { mode, corridors = handles, parts_described = described, operations = subs, add_param_null = total, by_part = byPart, samples, other_first_chance = others };
        }
        finally { AppDomain.CurrentDomain.FirstChanceException -= handler; }
    }
}
