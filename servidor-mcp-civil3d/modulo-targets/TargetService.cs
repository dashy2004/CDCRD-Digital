using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil;
using Cdcrd.Corredores;
using App=Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivilApp=Autodesk.Civil.ApplicationServices.CivilApplication;
using CivAssembly=Autodesk.Civil.DatabaseServices.Assembly;
namespace Cdcrd.Targets;

internal static class TargetService
{
 internal static Action<string> QaCheckpoint=null;
 private const string RecordName="CDCRD_TARGETS_V1";
 private sealed record Plan(BindingSpec Spec,Baseline Baseline,BaselineRegion Region,Subassembly Lane,Alignment Width,Profile Elevation,int Sign);
 private sealed record TargetRow(string baseline,string region,string group,string subassembly,string logical,string type,string[] ids);
 private static string H(ObjectId id)=>id.IsNull?null:id.Handle.ToString();
 private static double[] Pt(Point3d p)=>new[]{p.X,p.Y,p.Z};
 private static string Text(JsonObject p,string k)=>TargetContract.Text(p,k);
 private static ObjectId Resolve(Transaction tr,IEnumerable<ObjectId> ids,string key)
 {
  var found=ids.Where(id=>string.Equals(H(id),key,StringComparison.OrdinalIgnoreCase)||string.Equals(((Autodesk.Civil.DatabaseServices.Entity)tr.GetObject(id,OpenMode.ForRead)).Name,key,StringComparison.OrdinalIgnoreCase)).ToArray();
  if(found.Length!=1)throw new ArgumentException("Referencia inexistente o ambigua: "+key);return found[0];
 }
 private static void Local(Autodesk.Civil.DatabaseServices.Entity e)
 {if(e.IsReferenceObject||e.IsCWSReferenceObject)throw new ArgumentException("Se requiere objeto local");}
 private static void Axis(Alignment a){Local(a);if(a.StationEquations.Count!=0)throw new ArgumentException("Ecuaciones de estacion no soportadas");}
 private static TargetRow[] Catalog(Corridor c)
 {
  if(c.Baselines.Count>20||c.Baselines.Cast<Baseline>().Sum(b=>b.BaselineRegions.Count)>100)throw new ArgumentException("Corredor excede 20 baselines/100 regiones");
  return c.Baselines.Cast<Baseline>().SelectMany(b=>b.BaselineRegions.Cast<BaselineRegion>().SelectMany(r=>r.GetTargets().Cast<SubassemblyTargetInfo>().Select(t=>new TargetRow(b.Name,r.Name,t.AssemblyGroupName,t.SubassemblyName,t.LogicalName,t.TargetType.ToString(),t.TargetIds.Cast<ObjectId>().Select(H).ToArray())))).ToArray();
 }
 private static JsonNode Record(Corridor c,Transaction tr,string name)
 {
  if(c.ExtensionDictionary.IsNull)throw new ArgumentException("Corredor sin contrato propio");
  var d=(DBDictionary)tr.GetObject(c.ExtensionDictionary,OpenMode.ForRead);
  if(!d.Contains(name))throw new ArgumentException("Corredor sin contrato "+name);
  var x=(Xrecord)tr.GetObject(d.GetAt(name),OpenMode.ForRead);
  return JsonNode.Parse(string.Concat(x.Data.AsArray().Select(v=>(string)v.Value))) ??throw new ArgumentException("Contrato invalido");
 }
 private static void RequireMulti(Corridor c,Transaction tr)
 {
  if(c.ExtensionDictionary.IsNull||!((DBDictionary)tr.GetObject(c.ExtensionDictionary,OpenMode.ForRead)).Contains("CDCRD_MULTI_V1"))throw new ArgumentException("Requiere corredor propio multibaseline");
  Local(c);
  if(c.IsOutOfDate||c.RebuildAutomatic||c.CorridorSurfaces.Count!=1)throw new ArgumentException("Requiere corredor actualizado, rebuild manual y una Top");
  var surface=c.CorridorSurfaces[0];
  if(surface.Boundaries.Count!=1||!surface.Boundaries[0].IsCorridorExtents)throw new ArgumentException("Requiere limite por extensiones");
 }
 private static SubassemblyTargetInfo Slot(SubassemblyTargetInfoCollection targets,Plan p,string type)
 {
  string logical=type=="Offset"?"Width":"Outside Elevation";
  var matches=targets.Cast<SubassemblyTargetInfo>().Where(t=>t.SubassemblyName==p.Lane.Name&&t.TargetType.ToString()==type&&t.LogicalName==logical).ToArray();
  if(matches.Length!=1)throw new ArgumentException("Carril sin target unico "+type);return matches[0];
 }
 private static Plan[] Plans(Corridor c,Transaction tr,JsonArray bindings)
 {
  var civil=CivilApp.ActiveDocument;var keys=new HashSet<string>();
  return TargetContract.Parse(bindings).Select(spec=>{
   var bs=c.Baselines.Cast<Baseline>().Where(b=>b.Name.Equals(spec.Baseline,StringComparison.OrdinalIgnoreCase)).ToArray();
   if(bs.Length!=1)throw new ArgumentException("Baseline inexistente o ambigua");var b=bs[0];
   var rs=b.BaselineRegions.Cast<BaselineRegion>().Where(r=>r.Name.Equals(spec.Region,StringComparison.OrdinalIgnoreCase)).ToArray();
   if(rs.Length!=1)throw new ArgumentException("Region inexistente o ambigua");var r=rs[0];
   var a=(Alignment)tr.GetObject(b.AlignmentId,OpenMode.ForRead);Axis(a);
   var asm=(CivAssembly)tr.GetObject(r.AssemblyId,OpenMode.ForRead);Local(asm);
   var sid=Resolve(tr,asm.Groups.Cast<AssemblyGroup>().SelectMany(g=>g.GetSubassemblyIds().Cast<ObjectId>()),spec.Subassembly);
   if(!keys.Add(b.Name+"\0"+r.Name+"\0"+H(sid)))throw new ArgumentException("Asignacion duplicada resuelta");
   var lane=(Subassembly)tr.GetObject(sid,OpenMode.ForRead);Local(lane);
   if(!lane.SubassemblyHookTo.IsNull||!lane.HasSide)throw new ArgumentException("Solo carriles de corona soportados");
   int sign=lane.Side==SubassemblySideType.Left?-1:lane.Side==SubassemblySideType.Right?1:0;
   if(sign==0)throw new ArgumentException("Lado no soportado");
   Alignment w=null;Profile z=null;
   if(spec.Width!=null){w=(Alignment)tr.GetObject(Resolve(tr,civil.GetAlignmentIds().Cast<ObjectId>(),spec.Width),OpenMode.ForRead);Axis(w);if(w.ObjectId==a.ObjectId)throw new ArgumentException("Target de ancho debe ser eje lateral");}
   if(spec.Elevation!=null)
   {
    var parent=w??a;z=(Profile)tr.GetObject(Resolve(tr,parent.GetProfileIds().Cast<ObjectId>(),spec.Elevation),OpenMode.ForRead);Local(z);
    if(z.AlignmentId!=parent.ObjectId)throw new ArgumentException("Perfil no pertenece al eje objetivo");
   }
   var plan=new Plan(spec,b,r,lane,w,z,sign);
   // Stable typed logical names identify the stock crown lane contract.
   Slot(r.GetTargets(),plan,"Offset");Slot(r.GetTargets(),plan,"Elevation");
   return plan;
  }).ToArray();
 }
 private static (double? Width,double? Elevation,double TargetStation) Expected(Plan p,Alignment a,double station)
 {
  double targetStation=station;double? width=null,z=null;
  if(p.Width!=null)
  {
   double distance=0;a.DistanceToAlignment(station,p.Width,p.Sign<0?AlignmentSide.Left:AlignmentSide.Right,ref distance,ref targetStation);
   width=TargetContract.Width(Math.Abs(distance));
   double x=0,y=0,tx=0,ty=0;
   a.PointLocation(station,p.Sign*width.Value,ref x,ref y);p.Width.PointLocation(targetStation,0,ref tx,ref ty);
   if(Math.Max(Math.Abs(x-tx),Math.Abs(y-ty))>1e-5)throw new ArgumentException("Interseccion objetivo no coincide con la normal/lado");
  }
  if(p.Elevation!=null)
  {
   if(targetStation<p.Elevation.StartingStation-1e-7||targetStation>p.Elevation.EndingStation+1e-7)throw new ArgumentException("Perfil objetivo no cubre estacion proyectada");
   z=p.Elevation.ElevationAt(targetStation);if(!double.IsFinite(z.Value))throw new ArgumentException("Cota objetivo no finita");
  }
  return(width,z,targetStation);
 }
 private static void Preflight(Plan[] plans,Transaction tr)
 {
  int total=0;
  foreach(var p in plans)
  {
   var stations=p.Region.AppliedAssemblies.Stations().ToArray();total+=stations.Length;
   if(stations.Length<2||total>20000)throw new ArgumentException("Presupuesto de estaciones excedido o vacio");
   var a=(Alignment)tr.GetObject(p.Baseline.AlignmentId,OpenMode.ForRead);
   foreach(double s in stations)Expected(p,a,s);
  }
 }
 private static JsonArray Canonical(Plan[] plans)=>new JsonArray(plans.Select(p=>(JsonNode)new JsonObject{
  ["baseline"]=p.Baseline.Name,["region"]=p.Region.Name,["subensamblaje"]=H(p.Lane.ObjectId),["alineamiento_ancho"]=H(p.Width?.ObjectId??ObjectId.Null),["perfil_cota"]=H(p.Elevation?.ObjectId??ObjectId.Null)}).ToArray());
 private static void Store(Corridor c,Transaction tr,JsonNode data,string recordName=RecordName)
 {
  var dict=(DBDictionary)tr.GetObject(c.ExtensionDictionary,OpenMode.ForWrite);
  if(dict.Contains(recordName))throw new ArgumentException("Targets ya tienen contrato; no reemplazar");
  string json=data.ToJsonString();var x=new Xrecord();x.Data=new ResultBuffer(Enumerable.Range(0,(json.Length+239)/240).Select(i=>new TypedValue((int)DxfCode.Text,json.Substring(i*240,Math.Min(240,json.Length-i*240)))).ToArray());
  dict.SetAt(recordName,x);tr.AddNewlyCreatedDBObject(x,true);
 }
 private static Corridor CloneSource(Corridor source,Transaction tr,string name)
 {
  var civil=CivilApp.ActiveDocument;
  var definitions=Record(source,tr,"CDCRD_MULTI_V1") as JsonArray;
  var specs=MultiContract.Parse(definitions);
  if(source.Baselines.Count!=specs.Length)throw new ArgumentException("Topologia de origen alterada");
  if(civil.CorridorCollection.Any(id=>((Corridor)tr.GetObject(id,OpenMode.ForRead)).Name.Equals(name,StringComparison.OrdinalIgnoreCase))||
     civil.GetSurfaceIds().Cast<ObjectId>().Any(id=>((Autodesk.Civil.DatabaseServices.Surface)tr.GetObject(id,OpenMode.ForRead)).Name.Equals(name+"_Top",StringComparison.OrdinalIgnoreCase)))throw new ArgumentException("Ya existe el corredor o Top");
  var cid=civil.CorridorCollection.Add(name);var copy=(Corridor)tr.GetObject(cid,OpenMode.ForWrite);
  copy.LayerId=source.LayerId;copy.RebuildAutomatic=false;
  foreach(var spec in specs)
  {
   var sourceBase=source.Baselines[spec.Name];
   var axis=(Alignment)tr.GetObject(sourceBase.AlignmentId,OpenMode.ForRead);Axis(axis);
   var profile=(Profile)tr.GetObject(sourceBase.ProfileId,OpenMode.ForRead);Local(profile);
   if(sourceBase.AlignmentId!=Resolve(tr,civil.GetAlignmentIds().Cast<ObjectId>(),spec.Alignment)||sourceBase.ProfileId!=Resolve(tr,axis.GetProfileIds().Cast<ObjectId>(),spec.Profile)||sourceBase.BaselineRegions.Count!=spec.Regions.Length)throw new ArgumentException("Baseline origen difiere del contrato");
   var baseline=copy.Baselines.Add(spec.Name,sourceBase.AlignmentId,sourceBase.ProfileId);
   foreach(var regionSpec in spec.Regions)
   {
    var old=sourceBase.BaselineRegions[regionSpec.Name];var oldSettings=old.AppliedAssemblySetting;
    if(old.AssemblyId!=Resolve(tr,civil.AssemblyCollection,regionSpec.Assembly)||Math.Abs(old.StartStation-regionSpec.Start)>1e-6||Math.Abs(old.EndStation-regionSpec.End)>1e-6||
       new[]{oldSettings.FrequencyAlongTangents,oldSettings.FrequencyAlongCurves,oldSettings.FrequencyAlongSpirals,oldSettings.FrequencyAlongProfileCurves}.Any(f=>Math.Abs(f-regionSpec.Frequency)>1e-9))throw new ArgumentException("Region origen difiere del contrato");
    var region=baseline.BaselineRegions.Add(regionSpec.Name,old.AssemblyId,old.StartStation,old.EndStation);
    var settings=region.AppliedAssemblySetting;
    settings.CorridorAlongCurvesOption=CorridorAlongCurveOption.CurveAtIncrement;
    settings.FrequencyAlongTangents=regionSpec.Frequency;settings.FrequencyAlongCurves=regionSpec.Frequency;
    settings.FrequencyAlongSpirals=regionSpec.Frequency;settings.FrequencyAlongProfileCurves=regionSpec.Frequency;
    settings.AppliedAtHorizontalGeometryPoints=true;settings.AppliedAtProfileGeometryPoints=true;settings.AppliedAtProfileHighLowPoints=true;
    settings.AppliedAtSuperelevationCriticalPoints=true;settings.AppliedAtOffsetTargetGeometryPoints=false;settings.AppliedAdjacentToOffsetTargetStartEnd=false;
    foreach(double station in regionSpec.Extra)region.AddStation(station,"Explicit region sample");
    var targets=region.GetTargets();var oldTargets=old.GetTargets().Cast<SubassemblyTargetInfo>().ToArray();
    foreach(SubassemblyTargetInfo target in targets)
    {
     var origin=oldTargets.Single(t=>t.SubassemblyName==target.SubassemblyName&&t.AssemblyGroupName==target.AssemblyGroupName&&t.LogicalName==target.LogicalName&&t.TargetType==target.TargetType);
     if(target.TargetType.ToString()!="Surface")continue;
     if(origin.TargetIds.Count!=1||regionSpec.Target==null||origin.TargetIds[0]!=Resolve(tr,civil.GetSurfaceIds().Cast<ObjectId>(),regionSpec.Target))throw new ArgumentException("TargetTIN origen difiere del contrato");
     var terrain=tr.GetObject(origin.TargetIds[0],OpenMode.ForRead) as TinSurface??throw new ArgumentException("TIN requerido");Local(terrain);
     target.TargetIds=new ObjectIdCollection(origin.TargetIds.Cast<ObjectId>().ToArray());
    }
    region.SetTargets(targets);
   }
  }
  copy.Rebuild();
  foreach(Baseline b in copy.Baselines)foreach(BaselineRegion r in b.BaselineRegions)
   if(!r.AppliedAssemblies.Stations().OrderBy(x=>x).SequenceEqual(source.Baselines[b.Name].BaselineRegions[r.Name].AppliedAssemblies.Stations().OrderBy(x=>x)))throw new ArgumentException("Muestreo del origen difiere del contrato");
  if(!copy.GetLinkCodes().Contains("Top"))throw new InvalidOperationException("Corredor sin Top");
  var surface=copy.CorridorSurfaces.Add(name+"_Top");surface.AddLinkCode("Top",true);
  surface.Boundaries.AddCorridorExtentsBoundary(name+"_Extents");surface.IsBuild=true;
  copy.CreateExtensionDictionary();Store(copy,tr,definitions,"CDCRD_MULTI_V1");
  QaCheckpoint?.Invoke("copy-created");return copy;
 }
 internal static object Execute(JsonObject p,out bool committed)
 {
  committed=false;var doc=App.DocumentManager.MdiActiveDocument??throw new InvalidOperationException("Sin documento");
  if(!DateTimeOffset.TryParse(Text(p,"vence_utc"),out var expires)||expires<DateTimeOffset.UtcNow||expires>DateTimeOffset.UtcNow.AddMinutes(5))throw new ArgumentException("Solicitud vencida o plazo invalido");
  if(p["pid"]?.GetValue<int>()!=Environment.ProcessId||!Path.IsPathFullyQualified(Text(p,"dibujo"))||!string.Equals(Path.GetFullPath(doc.Name),Path.GetFullPath(Text(p,"dibujo")),StringComparison.OrdinalIgnoreCase))throw new ArgumentException("Documento o PID distinto al esperado");
  if(Convert.ToInt32(App.GetSystemVariable("INSUNITS"))!=6||CivilApp.ActiveDocument.Settings.DrawingSettings.UnitZoneSettings.DrawingUnits.ToString()!="Meters")throw new ArgumentException("Se requieren unidades Civil y AutoCAD en metros");
  string action=Text(p,"accion");if(!new[]{"catalogo","crear","leer"}.Contains(action))throw new ArgumentException("Accion desconocida");
  bool write=action=="crear",sim=p["simular"]?.GetValue<bool>()??true;
  if(write&&(Environment.GetEnvironmentVariable("CDCRD_C3D_SOLO_LECTURA")=="1"||Environment.GetEnvironmentVariable("CDCRD_C3D_PERMITIR_COMANDOS")!="1"))throw new InvalidOperationException("Escritura/comandos deshabilitados");
  using(doc.LockDocument())using(var tr=doc.Database.TransactionManager.StartTransaction())
  {
   var c=(Corridor)tr.GetObject(Resolve(tr,CivilApp.ActiveDocument.CorridorCollection,Text(p,write?"corredor_origen":"corredor")),OpenMode.ForRead);Local(c);
   object result;
   if(action=="catalogo")result=new{corredor=H(c.ObjectId),name=c.Name,targets=Catalog(c),out_of_date=c.IsOutOfDate};
   else
   {
    RequireMulti(c,tr);JsonObject record;
    if(write)
    {
     if(((DBDictionary)tr.GetObject(c.ExtensionDictionary,OpenMode.ForRead)).Contains(RecordName))throw new ArgumentException("Targets ya tienen contrato; no reemplazar");
     var before=Catalog(c);
     if(before.Any(t=>t.type!="Surface"&&t.ids.Length!=0))throw new ArgumentException("Targets de ancho/cota existentes; no reemplazar");
     var source=c;var preflight=Plans(source,tr,p["asignaciones"] as JsonArray);Preflight(preflight,tr);
     c=CloneSource(source,tr,Text(p,"nombre"));
     var plans=Plans(c,tr,p["asignaciones"] as JsonArray);
     foreach(var group in plans.GroupBy(plan=>(plan.Baseline.Name,plan.Region.Name)))
     {
      var region=group.First().Region;var targets=region.GetTargets();
      foreach(var plan in group)
      {
       if(plan.Width!=null)Slot(targets,plan,"Offset").TargetIds=new ObjectIdCollection(new[]{plan.Width.ObjectId});
       if(plan.Elevation!=null)Slot(targets,plan,"Elevation").TargetIds=new ObjectIdCollection(new[]{plan.Elevation.ObjectId});
      }
      region.SetTargets(targets);QaCheckpoint?.Invoke("targets-assigned");
     }
     var after=Catalog(c);
     // Only the selected target IDs can change; all surface/other target slots survive.
     for(int i=0;i<before.Length;i++)
     {
      var old=before[i];var selected=plans.SingleOrDefault(plan=>plan.Baseline.Name==old.baseline&&plan.Region.Name==old.region&&plan.Lane.Name==old.subassembly);
      string wanted=old.type=="Offset"&&old.logical=="Width"?H(selected?.Width?.ObjectId??ObjectId.Null):old.type=="Elevation"&&old.logical=="Outside Elevation"?H(selected?.Elevation?.ObjectId??ObjectId.Null):null;
      var expected=old with{ids=wanted==null?old.ids:new[]{wanted}};
      if(JsonSerializer.Serialize(expected)!=JsonSerializer.Serialize(after[i]))throw new InvalidOperationException("Asignacion modifico otro target");
     }
     c.Rebuild();QaCheckpoint?.Invoke("corridor-rebuilt");
     ((TinSurface)tr.GetObject(c.CorridorSurfaces[0].SurfaceId,OpenMode.ForWrite)).Rebuild();QaCheckpoint?.Invoke("surface-rebuilt");
     if(JsonSerializer.Serialize(Catalog(source))!=JsonSerializer.Serialize(before)||source.IsOutOfDate)throw new InvalidOperationException("Origen alterado");
     record=new JsonObject{["origen"]=H(source.ObjectId),["asignaciones"]=Canonical(plans),["targets"]=JsonSerializer.SerializeToNode(after)};
     result=Inspect(c,tr,record,sim);Store(c,tr,record);QaCheckpoint?.Invoke("target-record-written");
    }
    else{record=Record(c,tr,RecordName) as JsonObject??throw new ArgumentException("Contrato invalido");result=Inspect(c,tr,record,false);}
   }
   if(write&&!sim){tr.Commit();committed=true;}else tr.Abort();return result;
  }
 }
 private static object Inspect(Corridor c,Transaction tr,JsonObject record,bool sim)
 {
  var plans=Plans(c,tr,record["asignaciones"] as JsonArray);Preflight(plans,tr);
  if(JsonSerializer.Serialize(Catalog(c))!=record["targets"].ToJsonString())throw new InvalidOperationException("Targets distintos del contrato");
  double xyError=0,zError=0,widthError=0,elevationError=0,daylightError=0;int count=0,verified=0;
  var bases=c.Baselines.Cast<Baseline>().Select(b=>{
   var a=(Alignment)tr.GetObject(b.AlignmentId,OpenMode.ForRead);Axis(a);var profile=(Profile)tr.GetObject(b.ProfileId,OpenMode.ForRead);Local(profile);
   var regions=b.BaselineRegions.Cast<BaselineRegion>().Select(r=>{
    var rows=r.AppliedAssemblies.Stations().OrderBy(s=>s).Select(s=>{
     if(++count>20000)throw new ArgumentException("Presupuesto aplicado excedido");
     var preceding=b.BaselineRegions.Cast<BaselineRegion>().Where(other=>other.Name!=r.Name&&Math.Abs(other.EndStation-s)<1e-6&&Math.Abs(r.StartStation-s)<1e-6).ToArray();
     if(preceding.Length>1)throw new ArgumentException("Limite compartido ambiguo");
     var owner=preceding.Length==1?preceding[0]:r;
     var aa=r.AppliedAssemblies.GetItemAt(s);if(aa.AssemblyId!=owner.AssemblyId)throw new InvalidOperationException("Ensamblaje nativo distinto de region geometrica");
     var points=aa.Points.Cast<CalculatedPoint>().Select(pt=>new{soe=Pt(pt.StationOffsetElevationToBaseline),xyz=Pt(pt.XYZ),codes=pt.CorridorCodes.Cast<string>().OrderBy(x=>x).ToArray()}).ToArray();
     if(points.Length<4||points.Any(pt=>pt.soe.Concat(pt.xyz).Any(v=>!double.IsFinite(v))))throw new InvalidOperationException("Geometria vacia o no finita");
     foreach(var pt in points)
     {
      double x=0,y=0;a.PointLocation(s,pt.soe[1],ref x,ref y);
      xyError=Math.Max(xyError,Math.Max(Math.Abs(x-pt.xyz[0]),Math.Abs(y-pt.xyz[1])));zError=Math.Max(zError,Math.Abs(profile.ElevationAt(s)+pt.soe[2]-pt.xyz[2]));
      if(Math.Abs(pt.soe[0]-s)>1e-6)throw new InvalidOperationException("API devolvio otra estacion");
     }
     var laneChecks=plans.Where(p=>p.Baseline.Name==b.Name&&p.Region.Name==owner.Name).Select(p=>{
      var applied=aa.GetAppliedSubassemblies().Cast<AppliedSubassembly>().Where(sa=>sa.SubassemblyId==p.Lane.ObjectId).ToArray();
      if(applied.Length!=1)throw new InvalidOperationException("Carril aplicado ausente o ambiguo");
      var edges=applied[0].Points.Cast<CalculatedPoint>().Where(pt=>pt.CorridorCodes.Cast<string>().Contains("ETW")).ToArray();
      var crowns=applied[0].Points.Cast<CalculatedPoint>().Where(pt=>pt.CorridorCodes.Cast<string>().Contains("Crown")).ToArray();
      if(edges.Length!=1||crowns.Length!=1||Math.Abs(crowns[0].StationOffsetElevationToBaseline.Y)>1e-6)throw new InvalidOperationException("Carril requiere corona central y ETW unico");
      var edge=edges[0];double actualWidth=p.Sign*edge.StationOffsetElevationToBaseline.Y;TargetContract.Width(actualWidth);
      var expected=Expected(p,a,s);
      if(expected.Width.HasValue)widthError=Math.Max(widthError,Math.Abs(expected.Width.Value-actualWidth));
      if(expected.Elevation.HasValue)elevationError=Math.Max(elevationError,Math.Abs(expected.Elevation.Value-edge.XYZ.Z));
      verified++;return new{subassembly=H(p.Lane.ObjectId),side=p.Sign<0?"Left":"Right",width=actualWidth,elevation=edge.XYZ.Z,target_station=expected.TargetStation,expected_width=expected.Width,expected_elevation=expected.Elevation,edge=Pt(edge.XYZ)};
     }).ToArray();
     var surfaces=owner.GetTargets().Cast<SubassemblyTargetInfo>().Where(t=>t.TargetType.ToString()=="Surface").SelectMany(t=>t.TargetIds.Cast<ObjectId>()).Distinct().ToArray();
     if(surfaces.Length!=1)throw new ArgumentException("Solo un targetTIN por region soportado");
     var tin=(TinSurface)tr.GetObject(surfaces[0],OpenMode.ForRead);Local(tin);
     var daylight=points.Where(pt=>pt.codes.Contains("Daylight")).ToArray();
     if(!daylight.Any(pt=>pt.soe[1]<0)||!daylight.Any(pt=>pt.soe[1]>0))throw new InvalidOperationException("Daylight incompleto");
     foreach(var pt in daylight)daylightError=Math.Max(daylightError,Math.Abs(tin.FindElevationAtXY(pt.xyz[0],pt.xyz[1])-pt.xyz[2]));
     return new{station=s,geometry_region=owner.Name,boundary_shared=preceding.Length==1,lanes=laneChecks,points};
    }).ToArray();
    return new{name=r.Name,start=r.StartStation,end=r.EndStation,assembly=H(r.AssemblyId),applied=rows};
   }).ToArray();return new{name=b.Name,alignment=H(b.AlignmentId),profile=H(b.ProfileId),regions};
  }).ToArray();
  if(c.IsOutOfDate||widthError>1e-5||elevationError>1e-6||xyError>1e-5||zError>1e-6||daylightError>1e-6)throw new InvalidOperationException($"Geometria no alcanza targets: ancho={widthError:R},cota={elevationError:R},XY={xyError:R},Z={zError:R},daylight={daylightError:R}");
  var surface=c.CorridorSurfaces[0];var top=(TinSurface)tr.GetObject(surface.SurfaceId,OpenMode.ForRead);
  var triangles=top.GetTriangles(false).Cast<TinSurfaceTriangle>().Select(t=>new[]{Pt(t.Vertex1.Location),Pt(t.Vertex2.Location),Pt(t.Vertex3.Location)}).ToArray();
  if(triangles.Length==0)throw new InvalidOperationException("Top vacia");
  return new{corredor=sim?null:H(c.ObjectId),origen=record["origen"]?.GetValue<string>(),name=c.Name,baselines=bases,asignaciones=Canonical(plans),targets=Catalog(c),surface=H(surface.SurfaceId),triangles,boundary_loops=surface.Boundaries[0].GetExtentsBoundaries().Select(loop=>loop.Select(Pt).ToArray()).ToArray(),verified_lane_samples=verified,max_width_error=widthError,max_elevation_error=elevationError,max_xy_error=xyError,max_z_error=zError,max_daylight_error=daylightError,out_of_date=c.IsOutOfDate,simulation=sim};
 }
}
