using System;
using System.Linq;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.DatabaseServices;
using CivilApp = Autodesk.Civil.ApplicationServices.CivilApplication;

public partial class GmRecoveryQa
{
    static object CurveFixture(Database db)
    {
        using var tr = db.TransactionManager.StartTransaction();
        var model = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db),OpenMode.ForWrite);
        const string layerName="CDX-QA-CURVES-SOURCE";
        var layers=(LayerTable)tr.GetObject(db.LayerTableId,OpenMode.ForRead);
        if(layers.Has(layerName))throw new InvalidOperationException("Curve fixture already exists");
        layers.UpgradeOpen();var layer=new LayerTableRecord{Name=layerName,Color=Autodesk.AutoCAD.Colors.Color.FromColorIndex(Autodesk.AutoCAD.Colors.ColorMethod.ByAci,8)};
        var layerId=layers.Add(layer);tr.AddNewlyCreatedDBObject(layer,true);
        string Add(double x,double y,(double X,double Y,double Bulge)[] points)
        {
            var pl=new Polyline();pl.LayerId=layerId;
            for(int i=0;i<points.Length;i++)pl.AddVertexAt(i,new Point2d(x+points[i].X,y+points[i].Y),points[i].Bulge,0,0);
            model.AppendEntity(pl);tr.AddNewlyCreatedDBObject(pl,true);return H(pl.ObjectId);
        }
        double b=Math.Tan(Math.PI/8);
        string axis=Add(620000,2100000,new[]{(0d,0d,0d),(80d,0d,b),(120d,40d,0d),(120d,120d,-b),(160d,160d,0d),(240d,160d,0d)});
        // A line crosses the preceding semicircle away from their common endpoint.
        string crossing=Add(620400,2100000,new[]{(0d,0d,1d),(100d,0d,0d),(50d,-75d,0d)});
        // Two collinear segments double back and overlap.
        string overlap=Add(620600,2100000,new[]{(0d,0d,0d),(100d,0d,0d),(50d,0d,0d)});
        // Bulge magnitude greater than one is outside the supported arc contract.
        string major=Add(620800,2100000,new[]{(0d,0d,1.2d),(100d,0d,0d)});
        tr.Commit();return new{axis,crossing,overlap,major,expected_length=240+40*Math.PI};
    }
    static object ArmCurveFailure(JsonElement job)
    {
        string stage=job.GetProperty("stage").GetString();
        if(stage!="alignment-created" && stage!="profile-curve-added")throw new ArgumentException("Invalid curve QA stage");
        var assembly=AppDomain.CurrentDomain.GetAssemblies().Single(a=>a.GetName().Name=="Cdcrd.Civil3dBridge");
        var field=assembly.GetType("Cdcrd.Civil3dBridge.Handlers").GetField("CurveQaCheckpoint",BindingFlags.Static|BindingFlags.NonPublic);
        if(field==null || field.GetValue(null)!=null)throw new InvalidOperationException("Curve fault probe unavailable or already armed");
        Action<string> fail=s=>{if(s==stage){field.SetValue(null,null);throw new InvalidOperationException("CDCRD_QA_CURVE_FAILURE:"+stage);}};
        field.SetValue(null,fail);return new{armed=stage,one_shot=true};
    }
    static object CurveAudit(Database db)
    {
        using var tr=db.TransactionManager.StartTransaction();
        var result=new List<object>();
        foreach(ObjectId id in CivilApp.ActiveDocument.GetAlignmentIds())
        {
            var a=(Alignment)tr.GetObject(id,OpenMode.ForRead);
            if(!a.Name.StartsWith("CDX QA CURVE",StringComparison.Ordinal))continue;
            var arcs=a.Entities.Cast<AlignmentEntity>().OfType<AlignmentArc>().Select(c=>new{radius=c.Radius,length=c.Length,start=c.StartStation,end=c.EndStation,clockwise=c.Clockwise}).ToArray();
            var xy=Enumerable.Range(0,21).Select(i=>{double s=a.StartingStation+a.Length*i/20,e=0,n=0;a.PointLocation(s,0,ref e,ref n);return new[]{s,e,n};}).ToArray();
            var profiles=a.GetProfileIds().Cast<ObjectId>().Select(pid=>{
                var p=(Profile)tr.GetObject(pid,OpenMode.ForRead);
                return new{handle=H(pid),name=p.Name,entities=p.Entities.Cast<ProfileEntity>().Select(e=>new{type=e.EntityType.ToString(),start=e.StartStation,end=e.EndStation,z0=e.StartElevation,z1=e.EndElevation}).ToArray(),
                    curves=p.Entities.Cast<ProfileEntity>().OfType<ProfileParabolaSymmetric>().Select(c=>new{type=c.CurveType.ToString(),length=c.Length,pvi=c.PVIStation,elevation=c.PVIElevation,gin=c.GradeIn,gout=c.GradeOut}).ToArray(),
                    samples=Enumerable.Range(0,101).Select(i=>{double s=p.StartingStation+(p.EndingStation-p.StartingStation)*i/100;return new[]{s,p.ElevationAt(s)};}).ToArray()};
            }).ToArray();
            result.Add(new{handle=H(id),name=a.Name,length=a.Length,start=a.StartingStation,end=a.EndingStation,arcs,xy,profiles});
        }
        return new{alignments=result};
    }
}
