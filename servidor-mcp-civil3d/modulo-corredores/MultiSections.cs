using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil.DatabaseServices.Styles;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivilApp = Autodesk.Civil.ApplicationServices.CivilApplication;
using SectionViewStyle = Autodesk.Civil.DatabaseServices.Styles.SectionViewStyle;
using Section = Autodesk.Civil.DatabaseServices.Section;
namespace Cdcrd.Corredores;
internal static partial class MultiService
{
    private static double Range(double value,double lo,double hi)
    {if(!double.IsFinite(value)||value<lo||value>hi)throw new ArgumentException("Valor fuera de rango");return value;}
    private static double[] Numbers(JsonObject p,string key)
    {return p[key] is JsonArray a?a.Select(MultiContract.Number).ToArray():throw new ArgumentException("Lista requerida: "+key);}
    private static object Sections(JsonObject p,Transaction tr)
    {
        string name=Text(p,"nombre");var xyz=Numbers(p,"origen");
        if(xyz.Length!=3)throw new ArgumentException("Origen XYZ requerido");var origin=new Point3d(xyz[0],xyz[1],xyz[2]);
        double width=Range(MultiContract.Number(p["semiancho"]),.01,100);
        double zmin=MultiContract.Number(p["cota_min"]),zmax=MultiContract.Number(p["cota_max"]);Range(zmax-zmin,.01,1000);
        var doc=App.DocumentManager.MdiActiveDocument;var civil=CivilApp.ActiveDocument;
        var cid=Resolve(tr,civil.CorridorCollection,Text(p,"corredor"));var corridor=(Corridor)tr.GetObject(cid,OpenMode.ForRead);
        Definitions(corridor,tr);
        if(corridor.IsOutOfDate||corridor.CorridorSurfaces.Count!=1)throw new ArgumentException("Requiere corredor actualizado con una superficie");
        string baselineName=Text(p,"baseline");
        var matches=corridor.Baselines.Cast<Baseline>().Where(b=>b.Name.Equals(baselineName,StringComparison.OrdinalIgnoreCase)).ToArray();
        if(matches.Length!=1)throw new ArgumentException("Baseline inexistente o ambigua");var baseline=matches[0];
        var alignment=(Alignment)tr.GetObject(baseline.AlignmentId,OpenMode.ForRead);
        if(alignment.IsReferenceObject||alignment.StationEquations.Count!=0)throw new ArgumentException("Eje local sin ecuaciones requerido");
        if(alignment.GetSampleLineGroupIds().Cast<ObjectId>().Any(id=>((SampleLineGroup)tr.GetObject(id,OpenMode.ForRead)).Name.Equals(name,StringComparison.OrdinalIgnoreCase)))throw new ArgumentException("Grupo ya existe");
        var stations=Numbers(p,"estaciones");
        if(stations.Length<1||stations.Length>100||stations.Skip(1).Where((s,i)=>s-stations[i]<=1e-6).Any())throw new ArgumentException("1..100 estaciones ordenadas y unicas requeridas");
        foreach(double station in stations)
        {
            var regions=baseline.BaselineRegions.Cast<BaselineRegion>().Where(r=>station>=r.StartStation-1e-6&&station<=r.EndStation+1e-6).ToArray();
            if(regions.Length!=1)throw new ArgumentException("Estacion en hueco o limite compartido: seleccione una estacion interior");
            if(!regions[0].AppliedAssemblies.Stations().Any(s=>Math.Abs(s-station)<1e-6))throw new ArgumentException("Incluya la estacion en estaciones_extra de la region");
        }
    var layer=Layer(tr,doc.Database,Text(p,"capa"));var gid=SampleLineGroup.Create(name,alignment.ObjectId);var group=(SampleLineGroup)tr.GetObject(gid,OpenMode.ForWrite);
    var sid=corridor.CorridorSurfaces[0].SurfaceId;bool found=false;
    foreach(SectionSource source in group.GetSectionSources())
    {source.IsSampled=source.SourceId==sid;if(source.IsSampled){found=true;source.StyleId=civil.Styles.SectionStyles[0];source.UpdateMode=SectionUpdateType.Dynamic;}}
    if(!found)throw new InvalidOperationException("Superficie de corredor no disponible para muestreo");
    var graphTemplate=(SectionViewStyle)tr.GetObject(civil.Styles.SectionViewStyles[0],OpenMode.ForRead);
    var graphId=graphTemplate.CopyAsSibling(name+"_GRAPH");var graph=(SectionViewStyle)tr.GetObject(graphId,OpenMode.ForWrite);graph.GraphStyle.VerticalExaggeration=1;
    double graphScale=Range(graph.GraphStyle.CurrentHorizontalScale,1e-9,1e12);
    void MetricAxis(AxisStyle axis,string field){axis.MajorTickStyle.TextHeight=.6/graphScale;axis.MajorTickStyle.Size=.15/graphScale;axis.MajorTickStyle.Interval=field=="Offset"?2:1;axis.MinorTickStyle.TextHeight=.3/graphScale;axis.MinorTickStyle.Size=.1/graphScale;axis.TitleStyle.TextHeight=.6/graphScale;axis.MajorTickStyle.LabelText="<[Section View Point "+field+"(Um|P2|RN|Sn|OF|AP|GC|UN)]> m";axis.MinorTickStyle.LabelText="";axis.TitleStyle.Text=field+" (m)";}
    MetricAxis(graph.BottomAxis,"Offset");MetricAxis(graph.TopAxis,"Offset");MetricAxis(graph.LeftAxis,"Elevation");MetricAxis(graph.RightAxis,"Elevation");MetricAxis(graph.CenterAxis,"Elevation");
    graph.TopAxis.TitleStyle.Text="";graph.RightAxis.TitleStyle.Text="";graph.CenterAxis.TitleStyle.Text="";
    graph.GraphStyle.TitleStyle.TextHeight=.85/graphScale;graph.GraphStyle.TitleStyle.OffsetY=1.5/graphScale;graph.GraphStyle.TitleStyle.Border=false;
    graph.GraphStyle.TitleStyle.Text="<[Section View Station(Um|FS|P2|RN|Sn|OF|AP|B2|TP|EN|W0|DZY|GC|UN)]> m";
    var rows=new List<object>();
    for(int i=0;i<stations.Length;i++)
    {
     double station=stations[i];Point2d Point(double offset){double x=0,y=0;alignment.PointLocation(station,offset,ref x,ref y);return new Point2d(x,y);}
     var left=Point(-width);var right=Point(width);
     var lid=SampleLine.Create(name+"_"+i.ToString("D3"),gid,new Point2dCollection(new[]{left,right}));var line=(SampleLine)tr.GetObject(lid,OpenMode.ForWrite);
     line.LayerId=layer;line.StyleId=civil.Styles.SampleLineStyles[0];line.LockToStation=true;
     // Point-based creation projects onto clothoids with a small station error.
     // Set the requested station explicitly, then restore both exact endpoints.
     line.Station=station;
     foreach(var vertex in line.Vertices)
     {
      if(vertex.Side.ToString()=="Left")vertex.Location=new Point3d(left.X,left.Y,0);
      else if(vertex.Side.ToString()=="Right")vertex.Location=new Point3d(right.X,right.Y,0);
     }
     var vertices=line.Vertices.Cast<SampleLineVertex>().ToArray();
     if(vertices.Length!=3 || !vertices.Any(v=>v.Location.DistanceTo(new Point3d(left.X,left.Y,0))<1e-6) || !vertices.Any(v=>v.Location.DistanceTo(new Point3d(right.X,right.Y,0))<1e-6))throw new InvalidOperationException("Vertices nativos no coinciden con la normal solicitada");
     if(Math.Abs(line.Station-station)>1e-6)throw new InvalidOperationException("Estacion nativa de linea no coincide");
     var vid=SectionView.Create(name+"_VIEW_"+i.ToString("D3"),lid,new Point3d(origin.X+(i%4)*(width*2+12),origin.Y-(i/4)*Math.Max(18,zmax-zmin+8),origin.Z));
     var view=(SectionView)tr.GetObject(vid,OpenMode.ForWrite);view.StyleId=graphId;view.LayerId=layer;view.IsOffsetRangeAutomatic=false;view.OffsetLeft=-width;view.OffsetRight=width;
     view.IsElevationRangeAutomatic=false;view.ElevationMin=zmin;view.ElevationMax=zmax;
     var sections=line.GetSectionIds().Cast<ObjectId>().Select(id=>{var s=(Section)tr.GetObject(id,OpenMode.ForRead);return new{handle=H(id),fuente=H(s.SourceId),estacion=s.Station,puntos=s.SectionPoints.Cast<SectionPoint>().Select(pt=>new{offset=pt.Location.X,cota=pt.Location.Y,segment_to=pt.SegmentTo}).ToArray()};}).ToArray();
     if(sections.Length!=1||sections[0].puntos.Length<2||!sections[0].puntos.Any(pt=>pt.segment_to>=0&&pt.segment_to<sections[0].puntos.Length))throw new InvalidOperationException("Seccion sin puntos muestreados");
     QaCheckpoint?.Invoke("section-created");
     rows.Add(new{estacion=station,linea=H(lid),vista=H(vid),izquierda=new[]{left.X,left.Y},derecha=new[]{right.X,right.Y},estacion_nativa=line.Station,vertices_nativos=vertices.Select(v=>Pt(v.Location)).ToArray(),secciones=sections});
    }
    bool sim=p["simular"]?.GetValue<bool>()??false;var result=new{handle=sim?null:H(gid),nombre=name,baseline=baseline.Name,corredor=H(cid),fuente=H(sid),secciones=rows,exageracion_vertical=1,simulacion=sim};
        return result;
    }
}
