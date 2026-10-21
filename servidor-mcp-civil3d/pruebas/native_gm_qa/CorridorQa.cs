using System;
using System.Linq;
using System.Collections.Generic;
using System.Text.Json;
using System.Reflection;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.Civil.DatabaseServices;
using CivilApp=Autodesk.Civil.ApplicationServices.CivilApplication;
using Assembly=Autodesk.Civil.DatabaseServices.Assembly;
using Section=Autodesk.Civil.DatabaseServices.Section;
using SectionViewStyle=Autodesk.Civil.DatabaseServices.Styles.SectionViewStyle;
public partial class GmRecoveryQa
{
 static object ArmCorridorFailure(JsonElement job)
 {
  string stage=job.GetProperty("stage").GetString();
  if(!new[]{"assembly-part-added","corridor-rebuilt","section-created"}.Contains(stage))throw new ArgumentException("Invalid corridor QA stage");
  var assembly=AppDomain.CurrentDomain.GetAssemblies().Single(a=>a.GetName().Name=="Cdcrd.Civil3dBridge");
  var field=assembly.GetType("Cdcrd.Civil3dBridge.Handlers").GetField("CorridorQaCheckpoint",BindingFlags.Static|BindingFlags.NonPublic);
  if(field==null||field.GetValue(null)!=null)throw new InvalidOperationException("QA failure already armed or unavailable");
  Action<string> fail=s=>{if(s==stage){field.SetValue(null,null);throw new InvalidOperationException("CDCRD_QA_CORRIDOR_FAILURE:"+stage);}};
  field.SetValue(null,fail);return new{armed=stage,one_shot=true};
 }
 static object CorridorAudit(Database db)
 {
  using var tr=db.TransactionManager.StartTransaction();var civil=CivilApp.ActiveDocument;
  var assemblies=civil.AssemblyCollection.Select(id=>{var a=(Assembly)tr.GetObject(id,OpenMode.ForRead);return new{handle=H(id),name=a.Name,origin=Pt(a.Location),parts=a.Groups.Cast<AssemblyGroup>().SelectMany(g=>g.GetSubassemblyIds().Cast<ObjectId>()).Select(sid=>{var sub=(Subassembly)tr.GetObject(sid,OpenMode.ForRead);return new{handle=H(sid),name=sub.Name,side=sub.Side.ToString(),width=sub.ParamsDouble["Width"].Value,slope=sub.ParamsDouble["Slope"].Value,assembly=H(sub.AssemblyId)};}).ToArray()};}).ToArray();
  var corridors=civil.CorridorCollection.Select(id=>{var c=(Corridor)tr.GetObject(id,OpenMode.ForRead);return new{handle=H(id),name=c.Name,out_of_date=c.IsOutOfDate,baselines=c.Baselines.Select(b=>new{alignment=H(b.AlignmentId),profile=H(b.ProfileId),regions=b.BaselineRegions.Select(r=>new{start=r.StartStation,end=r.EndStation,assembly=H(r.AssemblyId),frequency=r.AppliedAssemblySetting.FrequencyAlongTangents,curve_frequency=r.AppliedAssemblySetting.FrequencyAlongCurves,stations=r.SortedStations(),applied=r.SortedStations().Select(s=>new{station=s,points=b.GetAppliedAssemblyAtStation(s).Points.Cast<CalculatedPoint>().Select(p=>new{soe=Pt(p.StationOffsetElevationToBaseline),xyz=Pt(p.XYZ)}).ToArray()}).ToArray()}).ToArray()}).ToArray(),surfaces=c.CorridorSurfaces.Select(s=>new{handle=H(s.SurfaceId),name=s.Name,links=s.LinkCodes(),boundaries=s.Boundaries.Count}).ToArray()};}).ToArray();
  var groups=new List<object>();
  foreach(ObjectId aid in civil.GetAlignmentIds())
  {
   var a=(Alignment)tr.GetObject(aid,OpenMode.ForRead);
   foreach(ObjectId gid in a.GetSampleLineGroupIds())
   {
    var g=(SampleLineGroup)tr.GetObject(gid,OpenMode.ForRead);
    groups.Add(new{handle=H(gid),name=g.Name,alignment=H(aid),lines=g.GetSampleLineIds().Cast<ObjectId>().Select(lid=>{var l=(SampleLine)tr.GetObject(lid,OpenMode.ForRead);return new{handle=H(lid),station=l.Station,vertices=l.Vertices.Cast<SampleLineVertex>().Select(v=>new{xyz=Pt(v.Location),side=v.Side.ToString()}).ToArray(),sections=l.GetSectionIds().Cast<ObjectId>().Select(sid=>{var s=(Section)tr.GetObject(sid,OpenMode.ForRead);return new{handle=H(sid),source=H(s.SourceId),station=s.Station,points=s.SectionPoints.Cast<SectionPoint>().Select(p=>new{xyz=Pt(p.Location),segment_to=p.SegmentTo}).ToArray()};}).ToArray(),views=l.GetSectionViewIds().Cast<ObjectId>().Select(vid=>{var v=(SectionView)tr.GetObject(vid,OpenMode.ForRead);var style=(SectionViewStyle)tr.GetObject(v.StyleId,OpenMode.ForRead);return new{handle=H(vid),exaggeration=style.GraphStyle.VerticalExaggeration,label_height_model=style.BottomAxis.MajorTickStyle.TextHeight*style.GraphStyle.CurrentHorizontalScale,title_height_model=style.GraphStyle.TitleStyle.TextHeight*style.GraphStyle.CurrentHorizontalScale,left=v.OffsetLeft,right=v.OffsetRight,zmin=v.ElevationMin,zmax=v.ElevationMax};}).ToArray()};}).ToArray()});
   }
  }
  return new{assemblies,corridors,groups,section_view_styles=civil.Styles.SectionViewStyles.Cast<ObjectId>().Select(H).OrderBy(x=>x).ToArray()};
 }
}
