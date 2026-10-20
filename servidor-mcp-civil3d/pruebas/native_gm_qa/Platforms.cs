// Synthetic 40 x 24 m platform, offset 4 m, heights 100/102 m. QA only.
using System;
using System.Linq;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.DatabaseServices;
using TinSurface = Autodesk.Civil.DatabaseServices.TinSurface;
public partial class GmRecoveryQa
{
    static object VolumeRow(TinVolumeSurface volume)
    {
        var v=volume.GetVolumeProperties();
        return new {handle=H(volume.ObjectId),name=volume.Name,cut=v.UnadjustedCutVolume,fill=v.UnadjustedFillVolume,
            cutFactor=v.CutFactor,fillFactor=v.FillFactor,baseHandle=H(v.BaseSurface),comparisonHandle=H(v.ComparisonSurface)};
    }
    static object PlatformVolume(Database db,JsonElement job)
    {
        using(var tr=db.TransactionManager.StartTransaction())
        {
            var design=(TinSurface)tr.GetObject(Id(db,job.GetProperty("design").GetString()),OpenMode.ForRead);
            if(design.Name!="CDX QA PLATFORM 0513")throw new Exception("Only synthetic QA platform allowed");
            foreach(var id in Autodesk.Civil.ApplicationServices.CivilApplication.ActiveDocument.GetSurfaceIds().Cast<ObjectId>())
                if(((Autodesk.Civil.DatabaseServices.Surface)tr.GetObject(id,OpenMode.ForRead)).Name.StartsWith("CDX QA PLATFORM BASE") ||
                   ((Autodesk.Civil.DatabaseServices.Surface)tr.GetObject(id,OpenMode.ForRead)).Name.StartsWith("CDX QA PLATFORM VOLUME"))
                    throw new Exception("QA volume fixture already exists");
            var bid=TinSurface.Create(db,"CDX QA PLATFORM BASE 0513");
            var basis=(TinSurface)tr.GetObject(bid,OpenMode.ForWrite);
            basis.AddVertices(new Point3dCollection(new[]{new Point3d(610000,2100000,100),new Point3d(610048,2100000,100),new Point3d(610048,2100032,100),new Point3d(610000,2100032,100)}));
            basis.Rebuild();basis.Visible=false;
            var vid=TinVolumeSurface.Create("CDX QA PLATFORM VOLUME 0513",bid,design.ObjectId);
            var volume=(TinVolumeSurface)tr.GetObject(vid,OpenMode.ForWrite);volume.Visible=false;volume.Rebuild();
            var row=VolumeRow(volume);tr.Commit();return row;
        }
    }
}
