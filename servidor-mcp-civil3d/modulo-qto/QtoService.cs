using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Xml.Linq;
using System.Globalization;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil;
using App=Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivilApp=Autodesk.Civil.ApplicationServices.CivilApplication;
using CivilEntity=Autodesk.Civil.DatabaseServices.Entity;
using Surface=Autodesk.Civil.DatabaseServices.Surface;
using Section=Autodesk.Civil.DatabaseServices.Section;
namespace Cdcrd.Qto;

internal static class QtoService
{
 internal static Action<string> QaCheckpoint=null;
 const string RecordName="CDCRD_QTO_V1";
 static string H(ObjectId id)=>id.Handle.ToString();
 static string Text(JsonObject p,string key)
 {
  string s=p[key]?.GetValue<string>();
  if(string.IsNullOrWhiteSpace(s)||s.Length>200||s.Any(char.IsControl))throw new ArgumentException("Texto requerido: "+key);
  return s;
 }
 static double Num(JsonNode node,double lo=-1e8,double hi=1e8)
 {double v=node?.GetValue<double>()??throw new ArgumentException("Numero requerido");if(!double.IsFinite(v)||v<lo||v>hi)throw new ArgumentException("Numero fuera de rango");return v;}
 static ObjectId Resolve(Transaction tr,IEnumerable<ObjectId> ids,string key)
 {
  var found=ids.Where(id=>H(id).Equals(key,StringComparison.OrdinalIgnoreCase)||((CivilEntity)tr.GetObject(id,OpenMode.ForRead)).Name.Equals(key,StringComparison.OrdinalIgnoreCase)).ToArray();
  if(found.Length!=1)throw new ArgumentException("Objeto inexistente o ambiguo: "+key);return found[0];
 }
 static void Local(CivilEntity obj)
 {if(obj.IsReferenceObject||obj.IsCWSReferenceObject)throw new ArgumentException("Objeto local requerido");}
 static TinSurface Tin(Transaction tr,string key)
 {
  var s=tr.GetObject(Resolve(tr,CivilApp.ActiveDocument.GetSurfaceIds().Cast<ObjectId>(),key),OpenMode.ForRead) as TinSurface??throw new ArgumentException("Superficie TIN requerida");
  Local(s);if(s.IsOutOfDate||s.GetTinProperties().NumberOfTriangles==0)throw new ArgumentException("TIN vacia o desactualizada");return s;
 }
 static void Store(CivilEntity obj,Transaction tr,JsonObject data)
 {
  if(obj.ExtensionDictionary.IsNull)obj.CreateExtensionDictionary();var dict=(DBDictionary)tr.GetObject(obj.ExtensionDictionary,OpenMode.ForWrite);
  string json=data.ToJsonString();var x=new Xrecord{Data=new ResultBuffer(Enumerable.Range(0,(json.Length+239)/240).Select(i=>new TypedValue((int)DxfCode.Text,json.Substring(i*240,Math.Min(240,json.Length-i*240)))).ToArray())};
  if(dict.Contains(RecordName)){((Xrecord)tr.GetObject(dict.GetAt(RecordName),OpenMode.ForWrite)).Data=x.Data;x.Dispose();}
  else{dict.SetAt(RecordName,x);tr.AddNewlyCreatedDBObject(x,true);}
 }
 static JsonObject Record(CivilEntity obj,Transaction tr)
 {
  Local(obj);if(obj.ExtensionDictionary.IsNull)throw new ArgumentException("Objeto sin contrato QTO propio");
  var d=(DBDictionary)tr.GetObject(obj.ExtensionDictionary,OpenMode.ForRead);if(!d.Contains(RecordName))throw new ArgumentException("Objeto sin contrato QTO propio");
  return JsonNode.Parse(string.Concat(((Xrecord)tr.GetObject(d.GetAt(RecordName),OpenMode.ForRead)).Data.AsArray().Select(x=>(string)x.Value))) as JsonObject??throw new ArgumentException("Contrato invalido");
 }
 static object Volume(TinVolumeSurface s,bool sim)
 {
  if(s.IsOutOfDate)throw new ArgumentException("Volumen desactualizado; requiere reconstruccion explicita");
  var v=s.GetVolumeProperties();
  double[] values={v.UnadjustedCutVolume,v.UnadjustedFillVolume,v.UnadjustedNetVolume,v.AdjustedCutVolume,v.AdjustedFillVolume,v.AdjustedNetVolume};
  if(values.Any(x=>!double.IsFinite(x)))throw new InvalidOperationException("Volumen no finito");
  return new{handle=sim?null:H(s.ObjectId),name=s.Name,base_surface=H(v.BaseSurface),comparison_surface=H(v.ComparisonSurface),unit="m3",cut=v.UnadjustedCutVolume,fill=v.UnadjustedFillVolume,net=v.UnadjustedNetVolume,cut_factor=v.CutFactor,fill_factor=v.FillFactor,adjusted_cut=v.AdjustedCutVolume,adjusted_fill=v.AdjustedFillVolume,adjusted_net=v.AdjustedNetVolume,out_of_date=s.IsOutOfDate,simulation=sim};
 }
 static object CreateVolume(JsonObject p,Transaction tr,bool sim)
 {
  var a=Tin(tr,Text(p,"base"));var b=Tin(tr,Text(p,"comparacion"));
  if(a.ObjectId==b.ObjectId)throw new ArgumentException("Superficies deben ser diferentes");
  string name=Text(p,"nombre");double cut=Num(p["factor_corte"]??JsonValue.Create(1),.1,10),fill=Num(p["factor_relleno"]??JsonValue.Create(1),.1,10);
  if(CivilApp.ActiveDocument.GetSurfaceIds().Cast<ObjectId>().Any(id=>((Surface)tr.GetObject(id,OpenMode.ForRead)).Name.Equals(name,StringComparison.OrdinalIgnoreCase)))throw new ArgumentException("Nombre de superficie ya existe");
  var id=TinVolumeSurface.Create(name,a.ObjectId,b.ObjectId);var s=(TinVolumeSurface)tr.GetObject(id,OpenMode.ForWrite);
  s.CutFactor=cut;s.FillFactor=fill;s.Visible=false;s.Rebuild();QaCheckpoint?.Invoke("volume-created");
  Store(s,tr,new JsonObject{["kind"]="volume",["base"]=H(a.ObjectId),["comparison"]=H(b.ObjectId),["cut_factor"]=cut,["fill_factor"]=fill});
  QaCheckpoint?.Invoke("record-written");return Volume(s,sim);
 }
 static IEnumerable<ObjectId> Groups(Transaction tr)=>CivilApp.ActiveDocument.GetAlignmentIds().Cast<ObjectId>().SelectMany(id=>((Alignment)tr.GetObject(id,OpenMode.ForRead)).GetSampleLineGroupIds().Cast<ObjectId>());
 static double[] Stations(JsonObject p)
 {
  var a=p["estaciones"] as JsonArray??throw new ArgumentException("Estaciones requeridas");
  if(a.Count<2||a.Count>200)throw new ArgumentException("2..200 estaciones requeridas");var s=a.Select(n=>Num(n)).ToArray();
  if(s.Skip(1).Where((v,i)=>v-s[i]<=1e-6).Any())throw new ArgumentException("Estaciones ordenadas y unicas requeridas");return s;
 }
 static object CreateMaterials(JsonObject p,Transaction tr,bool sim)
 {
  var civil=CivilApp.ActiveDocument;var db=App.DocumentManager.MdiActiveDocument.Database;
  string name=Text(p,"nombre"),mode=Text(p,"modo");
  if(mode!="tierras"&&mode!="formas")throw new ArgumentException("Modo tierras o formas requerido");
  if(Groups(tr).Any(id=>((SampleLineGroup)tr.GetObject(id,OpenMode.ForRead)).Name.Equals(name,StringComparison.OrdinalIgnoreCase)))throw new ArgumentException("Grupo ya existe");
  var axis=(Alignment)tr.GetObject(Resolve(tr,civil.GetAlignmentIds().Cast<ObjectId>(),Text(p,"alineamiento")),OpenMode.ForRead);Local(axis);
  if(axis.StationEquations.Count!=0)throw new ArgumentException("Ecuaciones de estacion no soportadas");
  var stations=Stations(p);double width=Num(p["semiancho"],.1,100);
  if(stations[0]<axis.StartingStation||stations[^1]>axis.EndingStation)throw new ArgumentException("Estaciones fuera del eje");
  var sourceIds=new HashSet<ObjectId>();string[] codes=Array.Empty<string>();Corridor corridor=null;BaselineRegion region=null;
  if(mode=="tierras")
  {
   var a=Tin(tr,Text(p,"base"));var b=Tin(tr,Text(p,"comparacion"));if(a.ObjectId==b.ObjectId)throw new ArgumentException("Superficies deben ser diferentes");sourceIds.Add(a.ObjectId);sourceIds.Add(b.ObjectId);
  }
  else
  {
   corridor=(Corridor)tr.GetObject(Resolve(tr,civil.CorridorCollection,Text(p,"corredor")),OpenMode.ForRead);Local(corridor);
   if(corridor.IsOutOfDate)throw new ArgumentException("Corredor desactualizado");
   string bn=Text(p,"baseline"),rn=Text(p,"region");
   var bs=corridor.Baselines.Cast<Baseline>().Where(b=>b.Name.Equals(bn,StringComparison.OrdinalIgnoreCase)).ToArray();
   if(bs.Length!=1||bs[0].AlignmentId!=axis.ObjectId)throw new ArgumentException("Baseline no corresponde al eje");
   var rs=bs[0].BaselineRegions.Cast<BaselineRegion>().Where(r=>r.Name.Equals(rn,StringComparison.OrdinalIgnoreCase)).ToArray();
   if(rs.Length!=1)throw new ArgumentException("Region inexistente");region=rs[0];
   if(stations[0]<=region.StartStation+1e-6||stations[^1]>=region.EndStation-1e-6)throw new ArgumentException("Use estaciones interiores a una region; sin huecos ni limites compartidos");
   var ca=p["codigos"] as JsonArray??throw new ArgumentException("Codigos requeridos");codes=ca.Select(n=>n?.GetValue<string>()).ToArray();
   if(codes.Length<1||codes.Length>20||codes.Any(s=>string.IsNullOrWhiteSpace(s)||s.Length>100||s.Any(char.IsControl))||codes.Distinct().Count()!=codes.Length)throw new ArgumentException("Codigos invalidos o duplicados");
   foreach(double station in stations)
   {
    if(!region.AppliedAssemblies.Stations().Any(s=>Math.Abs(s-station)<1e-6))throw new ArgumentException("Estacion no aplicada en corredor");
    var applied=region.AppliedAssemblies.GetItemAt(station);
    foreach(string code in codes)
    {
     var shapes=applied.GetShapesByCode(code).Cast<CalculatedShape>().ToArray();
     if(shapes.Length==0||shapes.Any(s=>!double.IsFinite(s.Area)||s.Area<=0))throw new ArgumentException("Forma sin area: "+code);
     if(shapes.SelectMany(s=>s.CalculatedLinks.Cast<CalculatedLink>()).SelectMany(l=>l.CalculatedPoints.Cast<CalculatedPoint>()).Any(pt=>Math.Abs(pt.StationOffsetElevationToBaseline.Y)>width-1e-6))throw new ArgumentException("Semiancho no cubre formas");
    }
   }
   sourceIds.Add(corridor.ObjectId);
  }
  // New group owns all sampling/material changes. Existing groups stay read-only.
  var gid=SampleLineGroup.Create(name,axis.ObjectId);var group=(SampleLineGroup)tr.GetObject(gid,OpenMode.ForWrite);
  var found=new HashSet<ObjectId>();
  foreach(SectionSource source in group.GetSectionSources())
  {source.IsSampled=sourceIds.Contains(source.SourceId);if(source.IsSampled){found.Add(source.SourceId);source.UpdateMode=SectionUpdateType.Dynamic;}}
  if(!found.SetEquals(sourceIds))throw new InvalidOperationException("Fuentes no disponibles para muestreo");
  QaCheckpoint?.Invoke("group-created");
  for(int i=0;i<stations.Length;i++)
  {
   double station=stations[i];Point2d P(double offset){double x=0,y=0;axis.PointLocation(station,offset,ref x,ref y);return new Point2d(x,y);}
   var left=P(-width);var right=P(width);
   var lid=SampleLine.Create(name+"_"+i.ToString("D3"),gid,new Point2dCollection(new[]{left,right}));
   var line=(SampleLine)tr.GetObject(lid,OpenMode.ForWrite);line.LockToStation=true;line.Station=station;
   foreach(var vertex in line.Vertices){if(vertex.Side.ToString()=="Left")vertex.Location=new Point3d(left.X,left.Y,0);else if(vertex.Side.ToString()=="Right")vertex.Location=new Point3d(right.X,right.Y,0);}
   if(Math.Abs(line.Station-station)>1e-6)throw new InvalidOperationException("Estacion nativa distinta");
  }
  QaCheckpoint?.Invoke("samples-created");
  if(mode=="formas")
  {
   var pending=new JsonObject{["kind"]="materials",["state"]="prepared",["mode"]=mode,["list"]=name+"_MATERIALS",["alignment"]=H(axis.ObjectId),["stations"]=JsonSerializer.SerializeToNode(stations),["width"]=width,["sources"]=JsonSerializer.SerializeToNode(sourceIds.Select(H).ToArray()),["codes"]=JsonSerializer.SerializeToNode(codes),["corredor"]=H(corridor.ObjectId),["baseline"]=Text(p,"baseline"),["region"]=Text(p,"region")};
   Store(group,tr,pending);QaCheckpoint?.Invoke("record-written");
   return Prepared(group,pending,sim);
  }
  var lists=group.MaterialLists;lists.VolumeCalculationMethodType=MaterialVolumeCalculationMethodType.AverageEndArea;
  var list=lists.Add(name+"_MATERIALS");list.IsCurveCorrectionEnabled=false;
  if(mode=="tierras")
  {
   var mat=list.Add("Earthwork");mat.QuantityType=MaterialQuantityType.Earthwork;
   mat.Add(Tin(tr,Text(p,"base")).ObjectId).Condition=MaterialConditionType.Base;
   mat.Add(Tin(tr,Text(p,"comparacion")).ObjectId).Condition=MaterialConditionType.Compare;
  }
  else foreach(string code in codes){var mat=list.Add(code);mat.QuantityType=MaterialQuantityType.Structure;mat.Add(corridor.ObjectId,code).Condition=MaterialConditionType.Include;}
  if(!lists.Validate(MaterialVolumeCalculationMethodType.AverageEndArea))throw new InvalidOperationException("Lista QTO invalida");
  QaCheckpoint?.Invoke("materials-created");
  var record=new JsonObject{["kind"]="materials",["state"]="complete",["mode"]=mode,["list"]=list.Name,["alignment"]=H(axis.ObjectId),["stations"]=JsonSerializer.SerializeToNode(stations),["width"]=width,["sources"]=JsonSerializer.SerializeToNode(sourceIds.Select(H).ToArray()),["codes"]=JsonSerializer.SerializeToNode(codes)};
  Store(group,tr,record);QaCheckpoint?.Invoke("record-written");
  return Materials(group,tr,record,sim);
 }
 static object Prepared(SampleLineGroup g,JsonObject r,bool sim)=>new{handle=sim?null:H(g.ObjectId),name=g.Name,state="prepared",material_list_count=g.MaterialLists.Count,stations=r["stations"].DeepClone(),simulation=sim,simulation_scope="sampling only; native corridor QTO requires the next command after commit"};
 static object CompleteShapes(SampleLineGroup group,Transaction tr,JsonObject record,bool sim)
 {
  if(Text(record,"state")!="prepared"||group.MaterialLists.Count!=0)throw new ArgumentException("Se requiere grupo propio preparado, sin materiales; no repetir calculo confirmado");
  ValidateSampling(group,tr,record);
  var corridor=(Corridor)tr.GetObject(Resolve(tr,CivilApp.ActiveDocument.CorridorCollection,Text(record,"corredor")),OpenMode.ForRead);Local(corridor);
  if(corridor.IsOutOfDate)throw new ArgumentException("Corredor desactualizado");
  var codes=record["codes"].AsArray().Select(n=>n.GetValue<string>()).ToArray();
  foreach(ObjectId lid in group.GetSampleLineIds())
  {
   var line=(SampleLine)tr.GetObject(lid,OpenMode.ForRead);
   var sections=line.GetSectionIds().Cast<ObjectId>().Select(id=>tr.GetObject(id,OpenMode.ForRead)).OfType<CorridorSection>().ToArray();
   if(sections.Length!=1||sections[0].GetCorridor()!=corridor.ObjectId||codes.Any(code=>!sections[0].GetShapeCodes().Contains(code)))throw new InvalidOperationException("Muestreo de formas aun no disponible; conserve grupo y revise recibo");
  }
  var lists=group.MaterialLists;lists.VolumeCalculationMethodType=MaterialVolumeCalculationMethodType.AverageEndArea;
  var list=lists.Add(Text(record,"list"));list.IsCurveCorrectionEnabled=false;
  foreach(string code in codes){var mat=list.Add(code);mat.QuantityType=MaterialQuantityType.Structure;mat.Add(corridor.ObjectId,code).Condition=MaterialConditionType.Include;}
  QaCheckpoint?.Invoke("materials-created");record["state"]="complete";Store(group,tr,record);QaCheckpoint?.Invoke("record-written");return Materials(group,tr,record,sim);
 }
 static void ValidateSampling(SampleLineGroup group,Transaction tr,JsonObject record,bool surfaceCoverage=false)
 {
  if(Text(record,"kind")!="materials"||H(group.ParentAlignmentId)!=Text(record,"alignment"))throw new InvalidOperationException("Grupo distinto del contrato");
  var sources=group.GetSectionSources().Cast<SectionSource>().Where(s=>s.IsSampled).ToArray();
  var expected=record["sources"].AsArray().Select(n=>n.GetValue<string>()).ToHashSet();
  if(!expected.SetEquals(sources.Select(s=>H(s.SourceId)))||sources.Any(s=>s.UpdateMode!=SectionUpdateType.Dynamic))throw new InvalidOperationException("Fuentes o actualizacion modificadas");
  foreach(var source in sources){var e=(CivilEntity)tr.GetObject(source.SourceId,OpenMode.ForRead);Local(e);if(e is Surface surf&&surf.IsOutOfDate||e is Corridor c&&c.IsOutOfDate)throw new InvalidOperationException("Fuente desactualizada");}
  var axis=(Alignment)tr.GetObject(group.ParentAlignmentId,OpenMode.ForRead);Local(axis);if(axis.StationEquations.Count!=0)throw new InvalidOperationException("Ecuaciones no soportadas");
  double width=Num(record["width"]);
  var triangles=new Dictionary<ObjectId,double[][][]>();
  if(surfaceCoverage&&Text(record,"mode")=="tierras")foreach(var source in sources)
  {
   var tin=tr.GetObject(source.SourceId,OpenMode.ForRead) as TinSurface??throw new InvalidOperationException("TIN requerida");
   if(tin.GetTinProperties().NumberOfTriangles>100000)throw new InvalidOperationException("Presupuesto de cobertura: maximo 100000 triangulos por TIN");
   triangles[source.SourceId]=tin.GetTriangles(false).Cast<TinSurfaceTriangle>().Select(t=>new[]{new[]{t.Vertex1.Location.X,t.Vertex1.Location.Y},new[]{t.Vertex2.Location.X,t.Vertex2.Location.Y},new[]{t.Vertex3.Location.X,t.Vertex3.Location.Y}}).ToArray();
  }
  foreach(ObjectId id in group.GetSampleLineIds())
  {
   var line=(SampleLine)tr.GetObject(id,OpenMode.ForRead);var points=line.Vertices.Cast<SampleLineVertex>().Select(v=>v.Location).ToArray();
   if(points.Length!=3)throw new InvalidOperationException("Vertices de muestreo modificados");
   foreach(double offset in new[]{-width,0d,width}){double x=0,y=0;axis.PointLocation(line.Station,offset,ref x,ref y);if(!points.Any(pt=>Math.Abs(pt.X-x)<1e-6&&Math.Abs(pt.Y-y)<1e-6))throw new InvalidOperationException("Ancho/geometria de muestreo modificados");}
   if(surfaceCoverage&&Text(record,"mode")=="tierras")
   foreach(var source in sources)
   {
    double ax=0,ay=0,bx=0,by=0;axis.PointLocation(line.Station,-width,ref ax,ref ay);axis.PointLocation(line.Station,width,ref bx,ref by);
    if(!QtoCoverage.Covers(new[]{ax,ay},new[]{bx,by},triangles[source.SourceId]))throw new InvalidOperationException("Superficie no cubre todo el muestreo o tiene huecos");
   }
  }
 }
 static object Materials(SampleLineGroup group,Transaction tr,JsonObject record,bool sim)
 {
  ValidateSampling(group,tr,record);
  if(Text(record,"state")=="prepared")return Prepared(group,record,sim);
  string listName=Text(record,"list");var list=group.MaterialLists[listName];
  if(list==null||!group.MaterialLists.Validate(MaterialVolumeCalculationMethodType.AverageEndArea)||group.MaterialLists.VolumeCalculationMethodType!=MaterialVolumeCalculationMethodType.AverageEndArea)throw new InvalidOperationException("Lista QTO no valida o metodo alterado");
  if(group.MaterialLists.Count!=1||list.IsCurveCorrectionEnabled)throw new InvalidOperationException("Lista o correccion de curva modificada");
  bool earth=Text(record,"mode")=="tierras";var expectedMaterials=earth?new[]{"Earthwork"}:record["codes"].AsArray().Select(n=>n.GetValue<string>()).ToArray();
  if(!expectedMaterials.ToHashSet().SetEquals(list.Cast<QTOMaterial>().Select(m=>m.Name))||list.Count!=expectedMaterials.Length)throw new InvalidOperationException("Materiales distintos del contrato");
  foreach(QTOMaterial mat in list)
  {
   if(mat.QuantityType!=(earth?MaterialQuantityType.Earthwork:MaterialQuantityType.Structure)||mat.Count!=(earth?2:1))throw new InvalidOperationException("Criterio de materiales modificado");
   foreach(MaterialFactorType factor in new[]{MaterialFactorType.Cut,MaterialFactorType.Fill,MaterialFactorType.Refill})if(mat.IsFactorApplicable(factor)&&Math.Abs(mat.GetFactor(factor)-1)>1e-10)throw new InvalidOperationException("Factores QTO modificados; se requieren factores 1");
   if(earth){var items=mat.Cast<QTOMaterialItem>().ToArray();if(items[0].Condition!=MaterialConditionType.Base||items[1].Condition!=MaterialConditionType.Compare)throw new InvalidOperationException("Orden base/comparacion modificado");}
   else if(mat[0].Condition!=MaterialConditionType.Include)throw new InvalidOperationException("Condicion de forma modificada");
  }
  var lines=group.GetSampleLineIds().Cast<ObjectId>().Select(id=>(SampleLine)tr.GetObject(id,OpenMode.ForRead)).OrderBy(l=>l.Station).ToArray();
  var expected=record["stations"].AsArray().Select(n=>Num(n)).ToArray();
  if(lines.Length!=expected.Length||lines.Where((l,i)=>Math.Abs(l.Station-expected[i])>1e-6).Any())throw new InvalidOperationException("Estaciones modificadas");
  var materials=list.Cast<QTOMaterial>().Select(m=>new{name=m.Name,type=m.QuantityType.ToString(),items=m.Cast<QTOMaterialItem>().Select(i=>new{name=i.Name,type=i.Type.ToString(),condition=i.Condition.ToString()}).ToArray()}).ToArray();
  object totals=null;
  {
   using var q=group.GetTotalVolumeResultDataForMaterialList(group.GetMappingGuid(listName));
   totals=q.GetResultsAlongSampleLines().Select(s=>new{station=s.Station,cut_area=s.AreaResult.CutArea,fill_area=s.AreaResult.FillArea,cut=s.VolumeResult.IncrementalCutVolume,fill=s.VolumeResult.IncrementalFillVolume,cumulative_cut=s.VolumeResult.CumulativeCutVolume,cumulative_fill=s.VolumeResult.CumulativeFillVolume}).ToArray();
  }
  // Structure quantities are exposed through Autodesk's XML report, not the
  // total earthwork accessor. Keep raw native XML for independently parsed QA.
  string path=Path.Combine(Commands.Root,"cdcrd-qto-report-"+Guid.NewGuid().ToString("N")+".xml");
  string xml;
  try{SampleLineGroup.ReportQuantities(group.ObjectId,listName,path,"");xml=File.ReadAllText(path);}
  finally{if(File.Exists(path))File.Delete(path);}
  if(string.IsNullOrWhiteSpace(xml))throw new InvalidOperationException("Informe QTO vacio");
  ValidateSampling(group,tr,record,true);
  var parsed=XDocument.Parse(xml);var sections=parsed.Descendants("CrossSect").ToArray();
  if(parsed.Descendants("Volume").SingleOrDefault()?.Attribute("unit")?.Value!="cubic meter"||parsed.Descendants("Area").SingleOrDefault()?.Attribute("unit")?.Value!="square meter")throw new InvalidOperationException("Informe QTO no esta en m2/m3");
  double Number(XElement el,string name){double v=double.Parse(el.Attribute(name)?.Value??throw new InvalidOperationException("Informe incompleto"),CultureInfo.InvariantCulture);if(!double.IsFinite(v))throw new InvalidOperationException("Informe no finito");return v;}
  if(sections.Length!=lines.Length||sections.Where((s,i)=>Math.Abs(Number(s,"sta")-lines[i].Station)>1e-6).Any())throw new InvalidOperationException("Informe sin todas las estaciones");
  double maxShapeError=0;
  if(Text(record,"mode")=="formas")
  {
   var c=(Corridor)tr.GetObject(Resolve(tr,CivilApp.ActiveDocument.CorridorCollection,Text(record,"corredor")),OpenMode.ForRead);
   var b=c.Baselines.Cast<Baseline>().Single(x=>x.Name==Text(record,"baseline"));var region=b.BaselineRegions.Cast<BaselineRegion>().Single(x=>x.Name==Text(record,"region"));
   if(b.AlignmentId!=group.ParentAlignmentId||expected[0]<=region.StartStation+1e-6||expected[^1]>=region.EndStation-1e-6)throw new InvalidOperationException("Topologia de corredor modificada");
   foreach(string code in record["codes"].AsArray().Select(n=>n.GetValue<string>()))
   {
    double cumulative=0,previousArea=0,previousStation=0;
    for(int i=0;i<sections.Length;i++)
    {
     double station=lines[i].Station;if(!region.AppliedAssemblies.Stations().Any(s=>Math.Abs(s-station)<1e-6))throw new InvalidOperationException("Estacion aplicada desaparecio");
     double area=region.AppliedAssemblies.GetItemAt(station).GetShapesByCode(code).Cast<CalculatedShape>().Sum(s=>s.Area);
     var rows=sections[i].Descendants("MaterialCrossSect").Where(m=>m.Attribute("name")?.Value==code).ToArray();if(rows.Length!=1||area<=0)throw new InvalidOperationException("Material no muestreado");
     double increment=i==0?0:(area+previousArea)*(station-previousStation)/2;cumulative+=increment;
     maxShapeError=Math.Max(maxShapeError,Math.Max(Math.Abs(area-Number(rows[0],"area")),Math.Max(Math.Abs(increment-Number(rows[0],"volume")),Math.Abs(cumulative-Number(rows[0],"cumVolume")))));
     previousArea=area;previousStation=station;
    }
   }
   if(maxShapeError>1e-5)throw new InvalidOperationException("QTO difiere de formas de la baseline elegida: "+maxShapeError.ToString("R",CultureInfo.InvariantCulture));
  }
  var quantities=sections.Select(s=>new{station=Number(s,"sta"),materials=s.Descendants("MaterialCrossSect").Select(m=>new{name=m.Attribute("name")?.Value,area=Number(m,"area"),volume=Number(m,"volume"),cumulative=Number(m,"cumVolume")}).ToArray()}).ToArray();
  return new{handle=sim?null:H(group.ObjectId),name=group.Name,state="complete",alignment=H(group.ParentAlignmentId),method="AverageEndArea",curve_correction=list.IsCurveCorrectionEnabled,stations=lines.Select(l=>l.Station).ToArray(),materials,totals,quantities,max_shape_check_error=maxShapeError,report_xml=xml,unit="m3",simulation=sim};
 }
 internal static object Execute(JsonObject p,out bool committed)
 {
  committed=false;var doc=App.DocumentManager.MdiActiveDocument??throw new InvalidOperationException("Sin documento");
  if(!DateTimeOffset.TryParse(Text(p,"vence_utc"),out var expires)||expires<DateTimeOffset.UtcNow||expires>DateTimeOffset.UtcNow.AddMinutes(5))throw new ArgumentException("Solicitud vencida o plazo invalido");
  if(p["pid"]?.GetValue<int>()!=Environment.ProcessId||!Path.IsPathFullyQualified(Text(p,"dibujo"))||!Path.GetFullPath(doc.Name).Equals(Path.GetFullPath(Text(p,"dibujo")),StringComparison.OrdinalIgnoreCase))throw new ArgumentException("Documento o PID distinto");
  if(Convert.ToInt32(App.GetSystemVariable("INSUNITS"))!=6||CivilApp.ActiveDocument.Settings.DrawingSettings.UnitZoneSettings.DrawingUnits.ToString()!="Meters")throw new ArgumentException("Unidades Civil y AutoCAD en metros requeridas");
  string action=Text(p,"accion");bool write=action=="volumen"||action=="materiales"||action=="calcular_formas",sim=p["simular"]?.GetValue<bool>()??true;
  if(!write&&action!="leer_volumen"&&action!="leer_materiales")throw new ArgumentException("Accion desconocida");
  if(write&&(Environment.GetEnvironmentVariable("CDCRD_C3D_SOLO_LECTURA")=="1"||Environment.GetEnvironmentVariable("CDCRD_C3D_PERMITIR_COMANDOS")!="1"))throw new InvalidOperationException("Escritura deshabilitada");
  using(doc.LockDocument())using(var tr=doc.Database.TransactionManager.StartTransaction())
  {
   object result;
   if(action=="volumen")result=CreateVolume(p,tr,sim);
   else if(action=="materiales")result=CreateMaterials(p,tr,sim);
   else if(action=="calcular_formas"){var g=(SampleLineGroup)tr.GetObject(Resolve(tr,Groups(tr),Text(p,"objeto")),OpenMode.ForWrite);result=CompleteShapes(g,tr,Record(g,tr),sim);}
   else if(action=="leer_volumen")
   {
    var s=tr.GetObject(Resolve(tr,CivilApp.ActiveDocument.GetSurfaceIds().Cast<ObjectId>(),Text(p,"objeto")),OpenMode.ForRead) as TinVolumeSurface??throw new ArgumentException("Volumen requerido");
    var r=Record(s,tr);var v=s.GetVolumeProperties();
    if(Text(r,"kind")!="volume"||Text(r,"base")!=H(v.BaseSurface)||Text(r,"comparison")!=H(v.ComparisonSurface)||Num(r["cut_factor"])!=v.CutFactor||Num(r["fill_factor"])!=v.FillFactor)throw new InvalidOperationException("Volumen distinto al contrato");
    result=Volume(s,false);
   }
   else {var g=(SampleLineGroup)tr.GetObject(Resolve(tr,Groups(tr),Text(p,"objeto")),OpenMode.ForWrite);result=Materials(g,tr,Record(g,tr),false);}
   if(write&&!sim){tr.Commit();committed=true;}else tr.Abort();return result;
  }
 }
}
