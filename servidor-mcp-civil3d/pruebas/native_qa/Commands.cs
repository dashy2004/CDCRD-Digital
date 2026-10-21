// Auxiliar de pruebas, no se instala con el puente. Solo acepta un DWG sintetico
// CDCRD_BRIDGE_SMOKE y una carpeta QA explicita en el entorno del proceso.
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using Exception = System.Exception;

public class DiagramFixture { public string Render() => "render-ok"; }
public class TupleFixture { public (DiagramFixture, double) GetDiagram() => (new DiagramFixture(), 7.25); }

public class BridgeQa
{
    static readonly JsonSerializerOptions Json = new JsonSerializerOptions { WriteIndented = true };
    static string Root => Environment.GetEnvironmentVariable("CDCRD_C3D_QA_ROOT");
    static object Call(Type t, string name, params object[] args)
    {
        try { return t.GetMethod(name, BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic).Invoke(null,args); }
        catch(TargetInvocationException e) { System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(e.InnerException ?? e).Throw();throw; }
    }
    static Type BridgeType(string name) => AppDomain.CurrentDomain.GetAssemblies()
        .Single(a=>a.GetName().Name=="Cdcrd.Civil3dBridge").GetType("Cdcrd.Civil3dBridge."+name,true);
    static string SafePath(string name)
    {
        if(string.IsNullOrEmpty(Root) || Path.GetFileName(name)!=name || !name.EndsWith(".json")) throw new Exception("Ruta QA invalida");
        return Path.Combine(Root,name);
    }
    static ObjectId AddLine(Transaction tr, Database db, string layer)
    {
        var ms=(BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db),OpenMode.ForWrite);
        var line=new Line(new Point3d(0,0,0),new Point3d(1,1,0)){Layer=layer};
        var id=ms.AppendEntity(line);tr.AddNewlyCreatedDBObject(line,true);return id;
    }
    static void Group(Transaction tr, Database db, string name, ObjectId[] members)
    {
        var gd=(DBDictionary)tr.GetObject(db.GroupDictionaryId,OpenMode.ForWrite);
        if(gd.Contains(name)) throw new Exception("Fixture ya existente: "+name);
        var g=new Group("Synthetic CDCRD regression",true);gd.SetAt(name,g);tr.AddNewlyCreatedDBObject(g,true);
        foreach(var id in members)g.Append(id);
    }
    static object Audit()
    {
        var db=App.DocumentManager.MdiActiveDocument.Database;
        using(var tr=db.TransactionManager.StartTransaction())
        {
            var groups=new Dictionary<string,int>();
            var gd=(DBDictionary)tr.GetObject(db.GroupDictionaryId,OpenMode.ForRead);
            foreach(DBDictionaryEntry e in gd)
            {var g=(Group)tr.GetObject(e.Value,OpenMode.ForRead);groups[e.Key]=g.GetAllEntityIds().Length;}
            var ms=(BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db),OpenMode.ForRead);
            int entities=ms.Cast<ObjectId>().Count(x=>!x.IsErased);
            return new {groups,entities};
        }
    }
    static object Fixture()
    {
        var doc=App.DocumentManager.MdiActiveDocument;var db=doc.Database;
        using(doc.LockDocument()) using(var tr=db.TransactionManager.StartTransaction())
        {
            var lt=(LayerTable)tr.GetObject(db.LayerTableId,OpenMode.ForWrite);
            if(!lt.Has("GM-PRUEBA-GRUPO")){var l=new LayerTableRecord{Name="GM-PRUEBA-GRUPO"};lt.Add(l);tr.AddNewlyCreatedDBObject(l,true);}
            var dead=AddLine(tr,db,"GM-PRUEBA-GRUPO");
            Group(tr,db,"GM - CDCRD_EMPTY",new[]{dead});
            ((Entity)tr.GetObject(dead,OpenMode.ForWrite)).Erase();
            Group(tr,db,"CDCRD_FOREIGN_EMPTY",Array.Empty<ObjectId>());
            Group(tr,db,"GM - CDCRD_LIVE",new[]{AddLine(tr,db,"GM-PRUEBA-GRUPO")});
            Group(tr,db,"GM - CDCRD_MIXED",new[]{AddLine(tr,db,"GM-PRUEBA-GRUPO"),AddLine(tr,db,"0")});
            tr.Commit();
        }
        var h=BridgeType("Handlers");
        var tuple=Call(h,"Invocar",new TupleFixture(),"GetDiagram",new List<object>());
        var diagram=Call(h,"PropGm",tuple,"Item1");
        var render=Call(h,"InvocarGm",diagram,"Render",Array.Empty<object>());
        var second=Call(h,"Invocar",tuple,"Item2",new List<object>());
        var serialized=Call(h,"Val",tuple,0,1);
        if((string)render!="render-ok" || (double)second!=7.25)throw new Exception("Fallo ValueTuple real");
        return new {audit=Audit(),tuple=new{render,second,serialized},note="Contrato ValueTuple sintetico; no ejecuta el GM sobre sondeos de proyecto"};
    }
    static object Timeout(string mode,string output)
    {
        var main=BridgeType("HiloPrincipal");
        var doc=App.DocumentManager.MdiActiveDocument;
        var started=new ManualResetEventSlim();
        Task.Run(()=>{
            started.Set();
            try
            {
                var result=Call(main,"Ejecutar",(Func<object>)(()=>{
                    if(mode=="running")Thread.Sleep(1200);
                    using(doc.LockDocument())using(var tr=doc.Database.TransactionManager.StartTransaction())
                    {AddLine(tr,doc.Database,"0");tr.Commit();}
                    return "native-write";
                }), mode=="pending"?100:500,"qa."+mode);
                File.WriteAllText(SafePath(output),JsonSerializer.Serialize(new{unexpected_success=result},Json));
            }
            catch(Exception e)
            {
                var data=e.GetType().GetField("Detalle")?.GetValue(e);
                File.WriteAllText(SafePath(output),JsonSerializer.Serialize(new{error=e.Message,data},Json));
            }
        });
        if(!started.Wait(3000))throw new Exception("No inicio el worker");
        if(mode=="pending")Thread.Sleep(800); // hilo CAD ocupado; el delegado no puede empezar
        return new{scheduled=mode};
    }
    [CommandMethod("CDCRDBRIDGEQA",CommandFlags.Session)]
    public void Run()
    {
        var doc=App.DocumentManager.MdiActiveDocument;
        if(doc==null || !Path.GetFileName(doc.Name).StartsWith("CDCRD_BRIDGE_SMOKE",StringComparison.Ordinal))throw new Exception("Solo DWG sintetico CDCRD_BRIDGE_SMOKE");
        var job=JsonDocument.Parse(File.ReadAllText(SafePath("job.json"))).RootElement;
        string action=job.GetProperty("action").GetString(),output=job.GetProperty("output").GetString();
        if(File.Exists(SafePath(output)))throw new Exception("Recibo ya existe");
        try
        {
            object result;
            switch(action)
            {
                case "fixture":result=Fixture();break;
                case "hold":
                    int hold=job.GetProperty("hold_ms").GetInt32();
                    if(hold<1 || hold>20000)throw new Exception("hold_ms fuera de rango");
                    File.WriteAllText(SafePath(job.GetProperty("holding_output").GetString()), "{\"holding\":true}");
                    Thread.Sleep(hold);result=new{held_ms=hold};break;
                case "audit":result=Audit();break;
                case "pending":case "running":result=Timeout(action,job.GetProperty("timeout_output").GetString());break;
                default:throw new Exception("Accion QA desconocida");
            }
            File.WriteAllText(SafePath(output),JsonSerializer.Serialize(new{ok=true,action,drawing=doc.Name,result},Json));
        }
        catch(Exception e){File.WriteAllText(SafePath(output),JsonSerializer.Serialize(new{ok=false,error=e.ToString()},Json));}
    }
}
