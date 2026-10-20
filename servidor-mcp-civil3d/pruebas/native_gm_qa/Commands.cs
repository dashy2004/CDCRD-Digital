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
using CivilApp = Autodesk.Civil.ApplicationServices.CivilApplication;
using TinSurface = Autodesk.Civil.DatabaseServices.TinSurface;
using CogoPoint = Autodesk.Civil.DatabaseServices.CogoPoint;
using PointGroup = Autodesk.Civil.DatabaseServices.PointGroup;
using SurfaceStyle = Autodesk.Civil.DatabaseServices.Styles.SurfaceStyle;

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
    static PropertyInfo ReadableProperty(Type type,string name)
    {
        // Some Civil style subclasses hide the inherited getter with a setter.
        for(var current=type;current!=null;current=current.BaseType)
        {
            var property=current.GetProperty(name,BindingFlags.Public|BindingFlags.Instance|BindingFlags.DeclaredOnly);
            if(property!=null && property.CanRead && property.GetIndexParameters().Length==0)return property;
        }
        return null;
    }
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
            try{var p=ReadableProperty(obj.GetType(),name);if(p!=null){var value=p.GetValue(obj);if(value is string || value is double || value is int)r[name]=value;}}
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
            var civil=CivilApp.ActiveDocument;
            var surfaces=new List<object>();
            foreach(ObjectId id in civil.GetSurfaceIds())
            {
                if(tr.GetObject(id,OpenMode.ForRead) is not TinSurface surface)continue;
                var triangles=surface.GetTriangles(false).Cast<Autodesk.Civil.DatabaseServices.TinSurfaceTriangle>()
                    .Select(t => new[]{Pt(t.Vertex1.Location),Pt(t.Vertex2.Location),Pt(t.Vertex3.Location)}
                        .OrderBy(p=>p[0]).ThenBy(p=>p[1]).ThenBy(p=>p[2]).ToArray())
                    .OrderBy(t=>JsonSerializer.Serialize(t),StringComparer.Ordinal).ToArray();
                surfaces.Add(new {handle=H(id),name=surface.Name,style=H(surface.StyleId),triangles});
            }
            var points=new List<object>();
            foreach(ObjectId id in civil.CogoPoints)
            {
                var point=(CogoPoint)tr.GetObject(id,OpenMode.ForRead);
                points.Add(new{handle=H(id),number=point.PointNumber,description=point.RawDescription,
                    xyz=new[]{point.Easting,point.Northing,point.Elevation}});
            }
            var pointGroups=new List<object>();
            foreach(ObjectId id in civil.PointGroups)
            {
                var group=(PointGroup)tr.GetObject(id,OpenMode.ForRead);
                pointGroups.Add(new{handle=H(id),name=group.Name,points=group.GetPointNumbers().OrderBy(n=>n).ToArray()});
            }
            var styles=new List<object>();
            foreach(ObjectId id in civil.Styles.SurfaceStyles)styles.Add(Row(tr.GetObject(id,OpenMode.ForRead)));
            var layers=new List<object>();
            foreach(ObjectId id in (LayerTable)tr.GetObject(db.LayerTableId,OpenMode.ForRead))
            {
                var layer=(LayerTableRecord)tr.GetObject(id,OpenMode.ForRead);
                layers.Add(new{handle=H(id),name=layer.Name,color=layer.Color.ColorIndex,off=layer.IsOff,frozen=layer.IsFrozen,locked=layer.IsLocked});
            }
            return new {objects=rows,groups,surfaces,points,pointGroups,surfaceStyles=styles,layers};
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
    static object RenameSurfaceStyles(Database db,JsonElement job)
    {
        using var tr=db.TransactionManager.StartTransaction();
        var result=new List<object>();
        foreach(var change in job.GetProperty("changes").EnumerateArray())
        {
            string from=change.GetProperty("from").GetString(),to=change.GetProperty("to").GetString();
            bool Allowed(string name)=>name.StartsWith("GM - ",StringComparison.Ordinal)||name.StartsWith("CDCRD_QA_",StringComparison.Ordinal);
            if(!Allowed(from)||!Allowed(to))throw new Exception("Only GM or QA surface styles may be renamed in this fixture");
            var styles=CivilApp.ActiveDocument.Styles.SurfaceStyles;
            if(!styles.Contains(from)||styles.Contains(to))throw new Exception("Style fixture state mismatch");
            var style=(SurfaceStyle)tr.GetObject(styles[from],OpenMode.ForWrite);
            style.Name=to;result.Add(new{handle=H(style.ObjectId),from,to});
        }
        tr.Commit();return new{renamed=result};
    }
    static object ResiduesFixture(Database db)
    {
        const string prefix="GM - Profile - 2D - StickLog ~ CDCRD_QA_RESIDUES_";
        using var tr=db.TransactionManager.StartTransaction();
        var blocks=(BlockTable)tr.GetObject(db.BlockTableId,OpenMode.ForRead);
        var model=(BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db),OpenMode.ForWrite);
        var groups=(DBDictionary)tr.GetObject(db.GroupDictionaryId,OpenMode.ForWrite);
        var result=new Dictionary<string,string>();
        if(blocks.Has(prefix+"unused")||groups.Contains(prefix+"empty"))throw new Exception("QA fixture exists");
        var empty=new Group("QA synthetic empty group",true);groups.SetAt(prefix+"empty",empty);tr.AddNewlyCreatedDBObject(empty,true);result["empty"]=H(empty.ObjectId);
        foreach(string kind in new[]{"unused","valid","ungrouped"})
        {
            blocks.UpgradeOpen();var block=new BlockTableRecord{Name=prefix+kind};blocks.Add(block);tr.AddNewlyCreatedDBObject(block,true);
            var line=new Line(new Point3d(0,0,0),new Point3d(1,0,0));block.AppendEntity(line);tr.AddNewlyCreatedDBObject(line,true);
            result[kind+"_definition"]=H(block.ObjectId);
            if(kind=="unused")continue;
            var reference=new BlockReference(new Point3d(0,0,0),block.ObjectId);model.AppendEntity(reference);tr.AddNewlyCreatedDBObject(reference,true);result[kind]=H(reference.ObjectId);
            if(kind=="valid")
            {
                var group=new Group("QA synthetic valid group",true);groups.SetAt(prefix+kind,group);tr.AddNewlyCreatedDBObject(group,true);group.Append(reference.ObjectId);result["valid_group"]=H(group.ObjectId);
            }
        }
        tr.Commit();return new {handles=result};
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
                    case "residues_fixture":result=ResiduesFixture(doc.Database);break;
                    case "fixture":case "restore":result=Fixture(doc.Database,job,action=="restore");break;
                    case "surface_style_names":result=RenameSurfaceStyles(doc.Database,job);break;
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
