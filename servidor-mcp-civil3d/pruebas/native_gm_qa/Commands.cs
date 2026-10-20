// Optional native regression harness; never installed by the normal bridge build.
// Only operates in an explicitly configured QA directory and copy filename.
using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.Json;
using System.Reflection;
using System.Drawing.Imaging;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using Exception = System.Exception;

public class GmRecoveryQa
{
    static readonly JsonSerializerOptions Json = new JsonSerializerOptions { WriteIndented = true };
    static string Root => Environment.GetEnvironmentVariable("CDCRD_GM_QA_ROOT");
    static Database watched;
    static readonly List<object> events = new List<object>();
    static string FilePath(string name, string extension)
    {
        if(string.IsNullOrWhiteSpace(Root) || Path.GetFileName(name)!=name || !name.EndsWith(extension,StringComparison.Ordinal))
            throw new Exception("Invalid QA output path");
        return Path.Combine(Root,name);
    }
    static string H(ObjectId id) => id.IsNull ? "0" : id.Handle.ToString();
    static ObjectId Id(Database db,string handle) => db.GetObjectId(false,new Handle(Convert.ToInt64(handle,16)),0);
    static double[] Pt(Point3d p) => new[]{p.X,p.Y,p.Z};
    static object Row(DBObject obj)
    {
        var r=new SortedDictionary<string,object>{{"handle",H(obj.ObjectId)},{"type",obj.GetType().FullName},{"owner",H(obj.OwnerId)}};
        if(obj is SymbolTableRecord sr) r["name"]=sr.Name;
        if(obj is Entity e)
        {
            r["layer"]=e.Layer;r["color"]=e.ColorIndex;r["linetype"]=e.Linetype;r["visible"]=e.Visible;
            try{r["extents"]=new[]{Pt(e.GeometricExtents.MinPoint),Pt(e.GeometricExtents.MaxPoint)};}
            catch(Exception ex){r["extents_error"]=ex.Message;}
        }
        if(obj is BlockReference br){r["definition"]=H(br.BlockTableRecord);r["position"]=Pt(br.Position);r["rotation"]=br.Rotation;}
        if(obj is Line line){r["start"]=Pt(line.StartPoint);r["end"]=Pt(line.EndPoint);}
        if(obj is Polyline pl){r["vertices"]=Enumerable.Range(0,pl.NumberOfVertices).Select(i=>new{point=Pt(pl.GetPoint3dAt(i)),bulge=pl.GetBulgeAt(i)}).ToArray();r["closed"]=pl.Closed;}
        if(obj is MText mt)r["contents"]=mt.Contents;
        if(obj is DBText dt)r["text"]=dt.TextString;
        if(obj is Hatch ha){r["pattern"]=ha.PatternName;r["angle"]=ha.PatternAngle;r["scale"]=ha.PatternScale;r["loops"]=ha.NumberOfLoops;}
        foreach(string name in new[]{"Name","StartingStation","EndingStation","ElevationMin","ElevationMax","StyleName"})
        {
            try{var p=obj.GetType().GetProperty(name);if(p!=null && p.GetIndexParameters().Length==0){var value=p.GetValue(obj);if(value is string || value is double || value is int)r[name]=value;}}
            catch(Exception ex){r[name+"_error"]=ex.GetBaseException().Message;}
        }
        return r;
    }
    static object Audit(Database db)
    {
        using(var tr=db.TransactionManager.StartTransaction())
        {
            var rows=new List<object>();
            foreach(ObjectId id in (BlockTable)tr.GetObject(db.BlockTableId,OpenMode.ForRead))
            {
                if(id.IsErased)continue;
                var b=(BlockTableRecord)tr.GetObject(id,OpenMode.ForRead);rows.Add(Row(b));
                foreach(ObjectId eid in b){if(!eid.IsErased) rows.Add(Row(tr.GetObject(eid,OpenMode.ForRead)));}
            }
            var groups=new SortedDictionary<string,object>();
            foreach(DBDictionaryEntry entry in (DBDictionary)tr.GetObject(db.GroupDictionaryId,OpenMode.ForRead))
            {
                var group=(Group)tr.GetObject(entry.Value,OpenMode.ForRead);
                groups[entry.Key]=new {handle=H(entry.Value),members=group.GetAllEntityIds().Select(H).OrderBy(x=>x).ToArray()};
            }
            return new {objects=rows,groups};
        }
    }
    static void Appended(object sender,ObjectEventArgs e)
    {
        // Observes a real GM operation without injecting exceptions into CAD events.
        var obj=e.DBObject;
        events.Add(new{kind="appended",handle=H(obj.ObjectId),type=obj.GetType().FullName,
            name=obj is SymbolTableRecord sr?sr.Name:null});
    }
    static object Fixture(Database db,JsonElement job,bool restore)
    {
        using(var tr=db.TransactionManager.StartTransaction())
        {
            var gd=(DBDictionary)tr.GetObject(db.GroupDictionaryId,OpenMode.ForRead);
            string name=job.GetProperty("group").GetString();
            if(!name.StartsWith("GM - Profile - 2D - StickLog ~ ",StringComparison.Ordinal)) throw new Exception("Not a GM profile group");
            var group=(Group)tr.GetObject(gd.GetAt(name),OpenMode.ForWrite);
            var bodyId=Id(db,job.GetProperty("body_handle").GetString());
            var body=(BlockReference)tr.GetObject(bodyId,OpenMode.ForRead);
            var block=(BlockTableRecord)tr.GetObject(body.BlockTableRecord,OpenMode.ForRead);
            if(block.Name!=name)throw new Exception("Group/body ownership mismatch");
            bool member=group.GetAllEntityIds().Contains(bodyId);
            if(restore){if(member)throw new Exception("Fixture already restored");group.Append(bodyId);}
            else {if(!member)throw new Exception("Fixture already active");group.Remove(bodyId);}
            tr.Commit();return new {group=name,body=H(bodyId),definition=H(block.ObjectId),restored=restore};
        }
    }
    [CommandMethod("CDCRDGMRECOVERYQA",CommandFlags.Session)]
    public void Run()
    {
        var doc=App.DocumentManager.MdiActiveDocument;
        if(doc==null || string.IsNullOrWhiteSpace(Root) || !Path.GetFileName(doc.Name).StartsWith("CDCRD_GM_RECOVERY_",StringComparison.Ordinal) ||
            !string.Equals(Path.GetDirectoryName(Path.GetFullPath(doc.Name)),Path.GetFullPath(Root),StringComparison.OrdinalIgnoreCase))
            throw new Exception("Only an identified QA copy in CDCRD_GM_QA_ROOT is allowed");
        using var jobDoc=JsonDocument.Parse(File.ReadAllText(FilePath("job.json",".json")));
        var job=jobDoc.RootElement;string action=job.GetProperty("action").GetString(),output=FilePath(job.GetProperty("output").GetString(),".json");
        if(File.Exists(output))throw new Exception("QA receipt exists");
        try
        {
            object result;
            using(doc.LockDocument())
            {
                switch(action)
                {
                    case "audit":result=Audit(doc.Database);break;
                    case "fixture":case "restore":result=Fixture(doc.Database,job,action=="restore");break;
                    case "watch_begin":
                        if(watched!=null)throw new Exception("Watcher already active");
                        events.Clear();watched=doc.Database;watched.ObjectAppended+=Appended;result=new{watching=true};break;
                    case "watch_end":
                        if(watched!=doc.Database)throw new Exception("Wrong watched database");
                        watched.ObjectAppended-=Appended;watched=null;result=new{events=events.ToArray(),audit=Audit(doc.Database)};break;
                    case "capture":
                        string image=FilePath(job.GetProperty("image").GetString(),".png");
                        if(File.Exists(image))throw new Exception("Capture exists");
                        doc.Editor.Regen();
                        using(var bitmap=doc.CapturePreviewImage(1800,1000)){bitmap.Save(image,ImageFormat.Png);}
                        result=new{image,source="Native Document.CapturePreviewImage; drawing viewport only"};break;
                    default:throw new Exception("Unknown QA action");
                }
            }
            File.WriteAllText(output,JsonSerializer.Serialize(new{ok=true,action,drawing=doc.Name,result},Json));
        }
        catch(Exception e){File.WriteAllText(output,JsonSerializer.Serialize(new{ok=false,action,error=e.ToString()},Json));}
    }
}
