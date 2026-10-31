using System.Diagnostics;
using System.Text.Json;
using ETABSv1;

// Educational independent-beam model, not bridge design or vehicle co-simulation.
internal static class Program
{
    const string Material = "DEMO_CONCRETE", Section = "DEMO_BEAM", Load = "DEMO_STATIC";
    const double L = 20, W = 10, E = 25_000_000, B = .45, H = 1;
    static readonly double[] Offsets = [-2.7, -.9, .9, 2.7];
    static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true };

    static object Plan() => new {
        educational_only = true, units = "kN,m,C", span_m = L, width_reference_m = 7.2,
        independent_beams = 4, offsets_m = Offsets, elevation_m = 5,
        section_m = new { width = B, depth = H }, elastic_modulus_kN_m2 = E,
        load_kN_m_per_beam = W, self_weight_multiplier = 0,
        expected = new { total_load_kN = 4*W*L, reaction_per_support_kN = W*L/2,
            maximum_moment_kNm = W*L*L/8,
            euler_bernoulli_deflection_m = 5*W*Math.Pow(L,4)/(384*E*(B*Math.Pow(H,3)/12)) },
        limits = "No deck distribution, moving loads, seismic, fatigue, foundations, design checks or BeamNG coupling."
    };

    static void Check(int code, string operation)
    { if (code != 0) throw new InvalidOperationException($"ETABS {operation}: code {code}"); }

    [STAThread]
    static int Main(string[] args)
    {
        if (args.Length == 0) { Console.WriteLine(JsonSerializer.Serialize(Plan(), JsonOptions)); return 0; }
        if (args.Length != 2 || args[0] != "--apply")
            throw new ArgumentException("No arguments: plan only. --apply <new-absolute-output-folder>: native run.");
        string output = args[1];
        if (!Path.IsPathFullyQualified(output)) throw new ArgumentException("Absolute output path required.");
        if (Directory.Exists(output) && Directory.EnumerateFileSystemEntries(output).Any())
            throw new IOException("Output folder must be empty; do not resume uncertain native writes.");
        string install = Environment.GetEnvironmentVariable("ETABS_INSTALL_DIR") ??
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles), "Computers and Structures", "ETABS 23");
        string executable = Path.Combine(install, "ETABS.exe");
        if (!File.Exists(executable)) throw new FileNotFoundException("ETABS executable missing.", executable);
        Directory.CreateDirectory(output);
        File.WriteAllText(Path.Combine(output, "plan.json"), JsonSerializer.Serialize(Plan(), JsonOptions));
        try { Run(executable, output); return 0; }
        catch (Exception ex)
        {
            File.WriteAllText(Path.Combine(output, "failure.txt"), ex.ToString());
            Console.Error.WriteLine("Stopped. Inspect the new ETABS instance and failure.txt before any retry.");
            return 1;
        }
    }

    static void Run(string executable, string output)
    {
        var existingPids = Process.GetProcessesByName("ETABS").Select(p => p.Id).ToHashSet();
        cHelper helper = new Helper();
        cOAPI app = helper.CreateObject(executable); // New dedicated process, never GetActiveObject.
        Check(app.ApplicationStart(), "ApplicationStart");
        var newProcesses = Process.GetProcessesByName("ETABS").Where(p => !existingPids.Contains(p.Id)).ToArray();
        if (newProcesses.Length != 1)
            throw new InvalidOperationException("Cannot identify one new ETABS process. No model writes performed.");
        int ownedPid = newProcesses[0].Id;
        app = helper.GetObjectProcess("CSI.ETABS.API.ETABSObject", ownedPid);
        cSapModel model = app.SapModel;
        if (!string.IsNullOrEmpty(model.GetModelFilename(true)))
            throw new InvalidOperationException("New instance opened a named model; refusing initialization.");
        File.WriteAllText(Path.Combine(output, "owned-process.json"), JsonSerializer.Serialize(new { ownedPid, existingPids }));
        Check(model.InitializeNewModel(eUnits.kN_m_C), "InitializeNewModel");
        Check(model.File.NewBlank(), "NewBlank");
        Check(model.SetPresentUnits(eUnits.kN_m_C), "units");
        Check(model.PropMaterial.SetMaterial(Material, eMatType.Concrete, -1, "Synthetic linear-elastic demonstration", ""), "material");
        Check(model.PropMaterial.SetMPIsotropic(Material, E, .2, 1e-5, 0), "elasticity");
        Check(model.PropMaterial.SetWeightAndMass(Material, 1, 0, 0), "zero weight");
        Check(model.PropFrame.SetRectangle(Section, Material, H, B, -1, "Synthetic demonstration", ""), "section");
        Check(model.LoadPatterns.Add(Load, eLoadPatternType.Other, 0, true), "load pattern");
        var supports = new List<string>(); var centers = new List<string>(); var frames = new List<string>();
        for (int i = 0; i < Offsets.Length; i++)
        {
            for (int segment = 0; segment < 2; segment++)
            {
                string name = "";
                Check(model.FrameObj.AddByCoord(segment*L/2, Offsets[i], 5,
                    (segment+1)*L/2, Offsets[i], 5, ref name, Section, $"DEMO_B{i+1}_{segment+1}", "Global"), "frame");
                frames.Add(name);
                string a = "", b = "";
                Check(model.FrameObj.GetPoints(name, ref a, ref b), "frame endpoints");
                bool[] restraint = segment == 0 ? [true,true,true,true,false,false] : [false,true,true,false,false,false];
                string support = segment == 0 ? a : b;
                Check(model.PointObj.SetRestraint(support, ref restraint, eItemType.Objects), "support");
                supports.Add(support);
                if (segment == 0) centers.Add(b);
                // Direction 6 is global Z; negative value means downward.
                Check(model.FrameObj.SetLoadDistributed(name, Load, 1, 6, 0, 1, -W, -W,
                    "Global", true, true, eItemType.Objects), "distributed load");
            }
        }
        string file = Path.Combine(output, "PUENTE_DIDACTICO.edb");
        Check(model.File.Save(file), "save before analysis");
        Check(model.Analyze.SetRunCaseFlag("", false, true), "disable other cases");
        Check(model.Analyze.SetRunCaseFlag(Load, true, false), "select demonstration case");
        Check(model.Analyze.RunAnalysis(), "analysis");
        Check(model.Results.Setup.DeselectAllCasesAndCombosForOutput(), "clear output cases");
        Check(model.Results.Setup.SetCaseSelectedForOutput(Load, true), "select output case");
        var reactions = supports.Select(p => ReadJoint(model, p, true)).ToArray();
        var displacements = centers.Select(p => ReadJoint(model, p, false)).ToArray();
        if (reactions.Any(r => Math.Abs(r[2]-W*L/2) > 1e-4))
            throw new InvalidOperationException("Vertical support reactions disagree with the independent equilibrium check.");
        double expected = 5*W*Math.Pow(L,4)/(384*E*(B*Math.Pow(H,3)/12));
        if (displacements.Any(r => r[2] >= 0 || Math.Abs(Math.Abs(r[2])/expected-1) > .02))
            throw new InvalidOperationException("Midspan displacement outside 2% of the Euler-Bernoulli reference.");
        Check(model.File.Save(file), "save results");
        Check(model.View.RefreshView(0, false), "refresh");
        File.WriteAllText(Path.Combine(output, "receipt.json"), JsonSerializer.Serialize(new {
            native_analysis_completed = true, ownedPid, frames, supports, centers,
            reactions, displacements, equilibrium_kN = reactions.Sum(r => r[2]),
            beamng_coupling = false, structural_design_verified = false
        }, JsonOptions));
        Console.WriteLine("Synthetic model and checked results saved. ETABS remains open for review.");
    }

    static double[] ReadJoint(cSapModel model, string point, bool reaction)
    {
        int count = 0; string[] obj=[],elm=[],cases=[],steps=[];
        double[] times=[],a=[],b=[],c=[],d=[],e=[],f=[];
        int code = reaction
            ? model.Results.JointReact(point, eItemTypeElm.ObjectElm, ref count, ref obj, ref elm,
                ref cases, ref steps, ref times, ref a, ref b, ref c, ref d, ref e, ref f)
            : model.Results.JointDispl(point, eItemTypeElm.ObjectElm, ref count, ref obj, ref elm,
                ref cases, ref steps, ref times, ref a, ref b, ref c, ref d, ref e, ref f);
        Check(code, reaction ? "reaction" : "displacement");
        if (count != 1 || cases[0] != Load) throw new InvalidOperationException("Unexpected result row count or load case.");
        double[] values = [a[0], b[0], c[0], d[0], e[0], f[0]];
        if (values.Any(v => !double.IsFinite(v))) throw new InvalidOperationException("Non-finite native result.");
        return values;
    }
}
