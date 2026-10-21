// Narrow SI corridor workflow. All new geometry remains inside one transaction.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil.DatabaseServices.Styles;
using SectionViewStyle = Autodesk.Civil.DatabaseServices.Styles.SectionViewStyle;
using Section = Autodesk.Civil.DatabaseServices.Section;
using CivAssembly = Autodesk.Civil.DatabaseServices.Assembly;
using CivAlignment = Autodesk.Civil.DatabaseServices.Alignment;
using CivProfile = Autodesk.Civil.DatabaseServices.Profile;

namespace Cdcrd.Civil3dBridge
{
 internal static partial class Handlers
 {
  private static Action<string> CorridorQaCheckpoint = null;
  private static double RequiredNumber(JsonObject p,string key) => Num(p,key) ?? throw new ArgumentException("Falta "+key);
  private static double[] StationArray(JsonObject p,string key)
   => p[key] is JsonArray a ? a.Select(x=>x.GetValue<double>()).ToArray() : throw new ArgumentException("Falta lista "+key);
  private static Point3d CorridorOrigin(JsonObject p)
  {
   var v=StationArray(p,"origen");if(v.Length!=3||v.Any(x=>!double.IsFinite(x)))throw new ArgumentException("origen requiere XYZ finitos");
   return new Point3d(v[0],v[1],v[2]);
  }
  private static void NewCivilName(Transaction tr,IEnumerable<ObjectId> ids,string name)
  {if(ids.Any(id=>string.Equals(NombreDe(tr.GetObject(id,OpenMode.ForRead)),name,StringComparison.OrdinalIgnoreCase)))throw new ArgumentException("Ya existe: "+name);}
  private static object CreateLinkAssembly(JsonObject p,string method)
  {
   ExigirEscritura(method,p);SiteUnits();string name=SiteName(p,"nombre");var origin=CorridorOrigin(p);
   double left=CorridorContract.Range(RequiredNumber(p,"ancho_izq"),.01,50,"ancho_izq"),right=CorridorContract.Range(RequiredNumber(p,"ancho_der"),.01,50,"ancho_der");
   double sl=CorridorContract.Range(RequiredNumber(p,"pendiente_izq"),-1,1,"pendiente_izq"),sr=CorridorContract.Range(RequiredNumber(p,"pendiente_der"),-1,1,"pendiente_der");
   var doc=Doc();var db=doc.Database;var civil=Civil();
   using(doc.LockDocument())using(var tr=db.TransactionManager.StartTransaction())
   {
    NewCivilName(tr,civil.AssemblyCollection,name);
    foreach(string suffix in new[]{"_L","_R"})NewCivilName(tr,civil.SubassemblyCollection,name+suffix);
    var layer=CapaId(tr,db,Txt(p,"capa"),true);
    var id=civil.AssemblyCollection.Add(name,AssemblyType.UndividedCrownedRoad,origin);
    var assembly=(CivAssembly)tr.GetObject(id,OpenMode.ForWrite);assembly.LayerId=layer;
    var parts=new List<object>();
    foreach(var side in new[]{(Suffix:"_L",Side:SubassemblySideType.Left,Width:left,Slope:sl),(Suffix:"_R",Side:SubassemblySideType.Right,Width:right,Slope:sr)})
    {
     var sid=civil.SubassemblyCollection.ImportStockSubassembly(name+side.Suffix,"Subassembly.LinkWidthAndSlope",origin);
     var sub=(Subassembly)tr.GetObject(sid,OpenMode.ForWrite);sub.LayerId=layer;
     sub.ParamsDouble["Width"].Value=side.Width;sub.ParamsDouble["Slope"].Value=side.Slope;
     sub.ParamsLong["UseSuperelevationSlope"].Value=0;sub.ParamsLong["SlopeDirection"].Value=0;sub.ParamsLong["OmitLink"].Value=0;
     sub.ParamsString["SurfaceCodes"].Value="Top,Datum";sub.ParamsString["PointCodes"].Value="Edge";
     sub.Side=side.Side;assembly.AddSubassembly(sid);sub.Run();
     CorridorQaCheckpoint?.Invoke("assembly-part-added");
     if(sub.AssemblyId!=id||sub.Side!=side.Side||Math.Abs(sub.ParamsDouble["Width"].Value-side.Width)>1e-9||Math.Abs(sub.ParamsDouble["Slope"].Value-side.Slope)>1e-9)
      throw new InvalidOperationException("Subensamblaje no coincide con parametros solicitados");
     parts.Add(new{handle=HandleOf(sid),lado=sub.Side.ToString(),ancho=sub.ParamsDouble["Width"].Value,pendiente=sub.ParamsDouble["Slope"].Value});
    }
    bool sim=p["simular"]?.GetValue<bool>()??false;
    var result=new{handle=sim?null:HandleOf(id),nombre=name,subensamblajes=parts,unidades="m",pendientes="m/m",simulacion=sim};
    if(sim)tr.Abort();else tr.Commit();return result;
   }
  }
  private static object CreateCorridor(JsonObject p,string method)
  {
   ExigirEscritura(method,p);SiteUnits();string name=SiteName(p,"nombre");var doc=Doc();var db=doc.Database;var civil=Civil();
   using(doc.LockDocument())using(var tr=db.TransactionManager.StartTransaction())
   {
    NewCivilName(tr,civil.CorridorCollection,name);NewCivilName(tr,civil.GetSurfaceIds().Cast<ObjectId>(),name+"_Top");
    var aid=ResolverId(tr,db,civil.GetAlignmentIds(),Txt(p,"alineamiento"),"alineamiento");var a=(CivAlignment)tr.GetObject(aid,OpenMode.ForRead);
    if(a.IsReferenceObject||a.StationEquations.Count!=0)throw new ArgumentException("Eje de referencia o con ecuaciones no soportado");
    var pid=ResolverId(tr,db,a.GetProfileIds(),Txt(p,"perfil"),"perfil del alineamiento");if(!a.GetProfileIds().Cast<ObjectId>().Contains(pid))throw new ArgumentException("perfil no pertenece al alineamiento");var profile=(CivProfile)tr.GetObject(pid,OpenMode.ForRead);
    var sid=ResolverId(tr,db,new ObjectIdCollection(civil.AssemblyCollection.ToArray()),Txt(p,"ensamblaje"),"ensamblaje");
    var assembly=(CivAssembly)tr.GetObject(sid,OpenMode.ForRead);
    if(profile.IsReferenceObject||assembly.IsReferenceObject||assembly.Groups.Count==0)throw new ArgumentException("Perfil/ensamblaje invalido o de referencia");
    double start=RequiredNumber(p,"inicio"),end=RequiredNumber(p,"fin"),frequency=RequiredNumber(p,"frecuencia");
    CorridorContract.Region(start,end,Math.Max(a.StartingStation,profile.StartingStation),Math.Min(a.EndingStation,profile.EndingStation),frequency);
    var extra=CorridorContract.Stations(StationArray(p,"estaciones_extra"),start,end);
    var id=civil.CorridorCollection.Add(name,name+"_Baseline",aid,pid);var c=(Corridor)tr.GetObject(id,OpenMode.ForWrite);
    c.LayerId=CapaId(tr,db,Txt(p,"capa"),true);c.RebuildAutomatic=false;
    var baseline=c.Baselines[0];var region=baseline.BaselineRegions.Add(name+"_Region",sid,start,end);var settings=region.AppliedAssemblySetting;
    settings.CorridorAlongCurvesOption=Autodesk.Civil.CorridorAlongCurveOption.CurveAtIncrement;
    settings.FrequencyAlongTangents=frequency;settings.FrequencyAlongCurves=frequency;settings.FrequencyAlongSpirals=frequency;settings.FrequencyAlongProfileCurves=frequency;
    settings.AppliedAtHorizontalGeometryPoints=true;settings.AppliedAtProfileGeometryPoints=true;settings.AppliedAtProfileHighLowPoints=true;
    settings.AppliedAtSuperelevationCriticalPoints=false;settings.AppliedAtOffsetTargetGeometryPoints=false;settings.AppliedAdjacentToOffsetTargetStartEnd=false;
    foreach(double station in extra)region.AddStation(station,"Explicit sample station");
    c.Rebuild();CorridorQaCheckpoint?.Invoke("corridor-rebuilt");
    if(region.AppliedAssemblies.Count==0||!c.GetLinkCodes().Contains("Top"))throw new InvalidOperationException("Corredor sin ensamblajes aplicados o codigo Top");
    var surface=c.CorridorSurfaces.Add(name+"_Top");surface.AddLinkCode("Top",true);surface.Boundaries.Add(name+"_Boundary","Edge");surface.IsBuild=true;
    c.Rebuild();
    var stations=region.SortedStations();
    if(extra.Any(s=>!stations.Any(x=>Math.Abs(x-s)<1e-6))||c.IsOutOfDate)throw new InvalidOperationException("Corredor sin reconstruir o faltan estaciones");
    var applied=stations.Select(s=>{var aa=baseline.GetAppliedAssemblyAtStation(s);return new{estacion=s,puntos=aa.Points.Cast<CalculatedPoint>().Select(pt=>new{soe=new[]{pt.StationOffsetElevationToBaseline.X,pt.StationOffsetElevationToBaseline.Y,pt.StationOffsetElevationToBaseline.Z},xyz=new[]{pt.XYZ.X,pt.XYZ.Y,pt.XYZ.Z}}).ToArray()};}).ToArray();
    if(applied.Any(row=>row.puntos.Length<4||row.puntos.Any(pt=>pt.xyz.Any(x=>!double.IsFinite(x)))))throw new InvalidOperationException("Geometria de corredor vacia o no finita");
    bool sim=p["simular"]?.GetValue<bool>()??false;
    var result=new{handle=sim?null:HandleOf(id),nombre=name,alineamiento=HandleOf(aid),perfil=HandleOf(pid),ensamblaje=HandleOf(sid),inicio=start,fin=end,frecuencia=frequency,
     superficie=HandleOf(surface.SurfaceId),estaciones=stations,aplicados=applied,simulacion=sim};
    if(sim)tr.Abort();else tr.Commit();return result;
   }
  }
  // Adapted from civil3d-terrain-tools TerrainApi.Sections: reuse sampling/source/style
  // workflow, accepting an existing curved alignment and native station/offset XY.
  private static object CreateCorridorSections(JsonObject p,string method)
  {
   ExigirEscritura(method,p);SiteUnits();string name=SiteName(p,"nombre");var origin=CorridorOrigin(p);
   double width=CorridorContract.Range(RequiredNumber(p,"semiancho"),.01,100,"semiancho");
   double zmin=RequiredNumber(p,"cota_min"),zmax=RequiredNumber(p,"cota_max");
   if(!double.IsFinite(zmin)||!double.IsFinite(zmax)||zmax-zmin<.01||zmax-zmin>1000)throw new ArgumentException("Rango de cotas invalido");
   var doc=Doc();var db=doc.Database;var civil=Civil();
   using(doc.LockDocument())using(var tr=db.TransactionManager.StartTransaction())
   {
    var cid=ResolverId(tr,db,new ObjectIdCollection(civil.CorridorCollection.ToArray()),Txt(p,"corredor"),"corredor");var corridor=(Corridor)tr.GetObject(cid,OpenMode.ForRead);
    if(corridor.IsReferenceObject||corridor.IsOutOfDate||corridor.Baselines.Count!=1||corridor.Baselines[0].BaselineRegions.Count!=1||corridor.CorridorSurfaces.Count!=1)
     throw new ArgumentException("Requiere corredor actualizado con una baseline, region y superficie");
    var baseline=corridor.Baselines[0];var region=baseline.BaselineRegions[0];var alignment=(CivAlignment)tr.GetObject(baseline.AlignmentId,OpenMode.ForRead);
    if(alignment.StationEquations.Count!=0)throw new ArgumentException("Ecuaciones de estacion no soportadas");
    NewCivilName(tr,alignment.GetSampleLineGroupIds().Cast<ObjectId>(),name);
    var stations=CorridorContract.Stations(StationArray(p,"estaciones"),region.StartStation,region.EndStation);
    if(stations.Length==0)throw new ArgumentException("Se requiere al menos una estacion");
    var actual=region.SortedStations();if(stations.Any(s=>!actual.Any(t=>Math.Abs(t-s)<1e-6)))throw new ArgumentException("Secciones requieren estaciones aplicadas del corredor; incluyalas en estaciones_extra");
    var layer=CapaId(tr,db,Txt(p,"capa"),true);var gid=SampleLineGroup.Create(name,alignment.ObjectId);var group=(SampleLineGroup)tr.GetObject(gid,OpenMode.ForWrite);
    var sid=corridor.CorridorSurfaces[0].SurfaceId;bool found=false;
    foreach(SectionSource source in group.GetSectionSources())
    {source.IsSampled=source.SourceId==sid;if(source.IsSampled){found=true;source.StyleId=civil.Styles.SectionStyles[0];source.UpdateMode=SectionUpdateType.Dynamic;}}
    if(!found)throw new InvalidOperationException("Superficie de corredor no disponible para muestreo");
    var graphTemplate=(SectionViewStyle)tr.GetObject(civil.Styles.SectionViewStyles[0],OpenMode.ForRead);
    var graphId=graphTemplate.CopyAsSibling(name+"_GRAPH");var graph=(SectionViewStyle)tr.GetObject(graphId,OpenMode.ForWrite);graph.GraphStyle.VerticalExaggeration=1;
    double graphScale=CorridorContract.Range(graph.GraphStyle.CurrentHorizontalScale,1e-9,1e12,"escala de grafico");
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
     if(Math.Abs(line.Station-station)>1e-6)throw new InvalidOperationException("Estacion nativa de linea no coincide");
     var vid=SectionView.Create(name+"_VIEW_"+i.ToString("D3"),lid,new Point3d(origin.X+(i%4)*(width*2+12),origin.Y-(i/4)*Math.Max(18,zmax-zmin+8),origin.Z));
     var view=(SectionView)tr.GetObject(vid,OpenMode.ForWrite);view.StyleId=graphId;view.LayerId=layer;view.IsOffsetRangeAutomatic=false;view.OffsetLeft=-width;view.OffsetRight=width;
     view.IsElevationRangeAutomatic=false;view.ElevationMin=zmin;view.ElevationMax=zmax;
     var sections=line.GetSectionIds().Cast<ObjectId>().Select(id=>{var s=(Section)tr.GetObject(id,OpenMode.ForRead);return new{handle=HandleOf(id),fuente=HandleOf(s.SourceId),estacion=s.Station,puntos=s.SectionPoints.Cast<SectionPoint>().Select(pt=>new{offset=pt.Location.X,cota=pt.Location.Y,segment_to=pt.SegmentTo}).ToArray()};}).ToArray();
     if(sections.Length!=1||sections[0].puntos.Length<2||!sections[0].puntos.Any(pt=>pt.segment_to>=0&&pt.segment_to<sections[0].puntos.Length))throw new InvalidOperationException("Seccion sin puntos muestreados");
     CorridorQaCheckpoint?.Invoke("section-created");
     rows.Add(new{estacion=station,linea=HandleOf(lid),vista=HandleOf(vid),izquierda=new[]{left.X,left.Y},derecha=new[]{right.X,right.Y},secciones=sections});
    }
    bool sim=p["simular"]?.GetValue<bool>()??false;var result=new{handle=sim?null:HandleOf(gid),nombre=name,corredor=HandleOf(cid),fuente=HandleOf(sid),secciones=rows,exageracion_vertical=1,simulacion=sim};
    if(sim)tr.Abort();else tr.Commit();return result;
   }
  }
 }
}
