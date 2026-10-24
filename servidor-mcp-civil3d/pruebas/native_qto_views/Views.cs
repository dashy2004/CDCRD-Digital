// Native section views for the synthetic QTO QA copy. No screenshot compositing.
using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil.DatabaseServices.Styles;
using SectionViewStyle=Autodesk.Civil.DatabaseServices.Styles.SectionViewStyle;
using App=Autodesk.AutoCAD.ApplicationServices.Core.Application;
public class QtoViews
{
 [CommandMethod("CDCRDQTOVIEWS1",CommandFlags.Session)]
 public void Run(){try{Core();}catch(System.Exception e){App.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nQTO views: "+e.Message);}}
 [MethodImpl(MethodImplOptions.NoInlining)]
 static void Core()
 {
  var doc=App.DocumentManager.MdiActiveDocument;string root=Environment.GetEnvironmentVariable("CDCRD_GM_QA_ROOT");
  if(doc==null||Path.GetFileName(doc.Name)!="CDCRD_GM_RECOVERY_QTO.dwg"||Path.GetDirectoryName(doc.Name)!=root)throw new InvalidOperationException("Wrong QA copy");
  string dest=Path.Combine(root,"qto-views-result.json");if(File.Exists(dest))throw new IOException("Receipt exists");
  object result=null;string error=null;
  try{
   using var file=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"qto-views.json")));
   using(doc.LockDocument())using(var tr=doc.Database.TransactionManager.StartTransaction())
   {
    var civil=Autodesk.Civil.ApplicationServices.CivilApplication.ActiveDocument;var rows=new List<object>();
    var template=(SectionViewStyle)tr.GetObject(civil.Styles.SectionViewStyles[0],OpenMode.ForRead);
    var styleId=template.CopyAsSibling("CDX QA QTO GRAPH 0522");var graph=(SectionViewStyle)tr.GetObject(styleId,OpenMode.ForWrite);graph.GraphStyle.VerticalExaggeration=1;
    double scale=graph.GraphStyle.CurrentHorizontalScale;
    void Metric(AxisStyle a,string field){a.MajorTickStyle.TextHeight=.5/scale;a.MajorTickStyle.Size=.12/scale;a.MajorTickStyle.Interval=field=="Offset"?5:1;a.MinorTickStyle.TextHeight=.2/scale;a.TitleStyle.TextHeight=.5/scale;a.MajorTickStyle.LabelText="<[Section View Point "+field+"(Um|P2|RN|Sn|OF|AP|GC|UN)]> m";a.MinorTickStyle.LabelText="";a.TitleStyle.Text="";}
    Metric(graph.BottomAxis,"Offset");Metric(graph.TopAxis,"Offset");Metric(graph.LeftAxis,"Elevation");Metric(graph.RightAxis,"Elevation");Metric(graph.CenterAxis,"Elevation");
    graph.GraphStyle.TitleStyle.TextHeight=.7/scale;graph.GraphStyle.TitleStyle.OffsetY=1.5/scale;graph.GraphStyle.TitleStyle.Border=false;graph.GraphStyle.TitleStyle.Text="<[Section View Station(Um|FS|P2|RN|Sn|OF|AP|B2|TP|EN|W0|DZY|GC|UN)]> m";
    foreach(var job in file.RootElement.EnumerateArray())
    {
     var gid=doc.Database.GetObjectId(false,new Handle(Convert.ToInt64(job.GetProperty("group").GetString(),16)),0);var group=(SampleLineGroup)tr.GetObject(gid,OpenMode.ForRead);
     if(!group.Name.StartsWith("CDX QA QTO ")||group.MaterialLists.Count!=1)throw new InvalidOperationException("Owned computed QA group required");
     var lines=group.GetSampleLineIds().Cast<ObjectId>().Select(id=>(SampleLine)tr.GetObject(id,OpenMode.ForRead)).OrderBy(l=>l.Station).ToArray();
     var origin=job.GetProperty("origin").EnumerateArray().Select(n=>n.GetDouble()).ToArray();int j=0;
     foreach(int i in job.GetProperty("indices").EnumerateArray().Select(n=>n.GetInt32()))
     {
      var line=lines[i];string name=group.Name+"_VIEW_"+i;var loc=new Point3d(origin[0]+j*42,origin[1],0);
      var vid=SectionView.Create(name,line.ObjectId,loc);var view=(SectionView)tr.GetObject(vid,OpenMode.ForWrite);view.StyleId=styleId;view.IsOffsetRangeAutomatic=false;view.OffsetLeft=-job.GetProperty("width").GetDouble();view.OffsetRight=job.GetProperty("width").GetDouble();view.IsElevationRangeAutomatic=false;view.ElevationMin=job.GetProperty("zmin").GetDouble();view.ElevationMax=job.GetProperty("zmax").GetDouble();
      var list=group.MaterialLists[0];var materialIds=list.Cast<QTOMaterial>().Select(m=>line.GetMaterialSectionId(list.Guid,m.Guid)).Where(id=>!id.IsNull).Select(id=>id.Handle.ToString()).ToArray();
      rows.Add(new{group=gid.Handle.ToString(),station=line.Station,line=line.ObjectId.Handle.ToString(),view=vid.Handle.ToString(),sections=line.GetSectionIds().Cast<ObjectId>().Select(id=>id.Handle.ToString()).ToArray(),material_sections=materialIds,origin=new[]{loc.X,loc.Y}});j++;
     }
    }
    tr.Commit();result=rows;
   }
  }catch(System.Exception e){error=e.ToString();}
  File.WriteAllText(dest,JsonSerializer.Serialize(new{ok=error==null,error,result}));
 }
}
