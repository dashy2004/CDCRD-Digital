using System;
using System.IO;
using System.Linq;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using System.Xml.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.Civil.DatabaseServices;
using App=Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivilApp=Autodesk.Civil.ApplicationServices.CivilApplication;
using Entity=Autodesk.AutoCAD.DatabaseServices.Entity;
namespace Cdcrd.Partidas;

internal static class PartidasService
{
 internal static Action<string> QaCheckpoint=null;
 const string Record="CDCRD_PAYITEMS_V1";
 static string Text(JsonObject p,string k){string s=p[k]?.GetValue<string>();if(string.IsNullOrWhiteSpace(s)||s.Length>240||s.Any(char.IsControl))throw new ArgumentException("Texto invalido: "+k);return s;}
 static JsonArray Rows(JsonObject p,string k){var a=p[k] as JsonArray;if(a==null||a.Count<1||a.Count>200)throw new ArgumentException("Lista 1..200 requerida: "+k);return a;}
 static string Hash(byte[] b)=>Convert.ToHexString(SHA256.HashData(b)).ToLowerInvariant();
 static JsonObject ReadRecord(Transaction tr,Database db)
 {
  var d=(DBDictionary)tr.GetObject(db.NamedObjectsDictionaryId,OpenMode.ForRead);
  if(!d.Contains(Record))throw new ArgumentException("Primero cargar un catalogo propio; no reemplazar catalogos existentes");
  return JsonNode.Parse(string.Concat(((Xrecord)tr.GetObject(d.GetAt(Record),OpenMode.ForRead)).Data.AsArray().Select(v=>(string)v.Value))).AsObject();
 }
 static void Store(Transaction tr,Database db,JsonObject data)
 {
  var d=(DBDictionary)tr.GetObject(db.NamedObjectsDictionaryId,OpenMode.ForWrite);if(d.Contains(Record))throw new ArgumentException("Catalogo ya registrado");
  string s=data.ToJsonString();var x=new Xrecord{Data=new ResultBuffer(Enumerable.Range(0,(s.Length+239)/240).Select(i=>new TypedValue((int)DxfCode.Text,s.Substring(i*240,Math.Min(240,s.Length-i*240)))).ToArray())};
  d.SetAt(Record,x);tr.AddNewlyCreatedDBObject(x,true);
 }
 static JsonObject Catalog(Transaction tr,Database db)
 {
  var r=ReadRecord(tr,db);string path=Text(r,"path");
  if(!File.Exists(path)||Hash(File.ReadAllBytes(path))!=Text(r,"sha256")||!string.Equals(QTOUtility.PayItemFilePath,path,StringComparison.OrdinalIgnoreCase)||QTOUtility.PayItemFileFormat!=PayItemFileFormat.CommaSeparated||!string.IsNullOrEmpty(QTOUtility.PayItemCategorizationPath))throw new InvalidOperationException("Catalogo externo modificado, movido o distinto al contrato");
  if(File.Exists(Path.ChangeExtension(path,"for")))throw new InvalidOperationException("Formulas externas no soportadas por este contrato");
  return r;
 }
 static JsonObject PlanCatalog(JsonObject p,string root)
 {
  var items=Rows(p,"partidas");var codes=new HashSet<string>(StringComparer.OrdinalIgnoreCase);var clean=new JsonArray();var csv=new StringBuilder("Pay Item,Description,Unit\r\n");
  string Quote(string s)=>"\""+s.Replace("\"","\"\"")+"\"";
  foreach(var n in items)
  {
   var row=n as JsonObject??throw new ArgumentException("Partida debe ser objeto");string code=Text(row,"codigo"),desc=Text(row,"descripcion"),unit=Text(row,"unidad");
   if(!Regex.IsMatch(code,"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")||!codes.Add(code))throw new ArgumentException("Codigo invalido o duplicado");
   if(desc.Length>160||"=+-@".Contains(desc.TrimStart()[0])||!new[]{"EA","M","M2","M3"}.Contains(unit))throw new ArgumentException("Descripcion/unidad invalida");
   clean.Add(new JsonObject{["codigo"]=code,["descripcion"]=desc,["unidad"]=unit});csv.Append(Quote(code)).Append(',').Append(Quote(desc)).Append(',').Append(unit).Append("\r\n");
  }
  byte[] bytes=new UTF8Encoding(false).GetBytes(csv.ToString());string digest=Hash(bytes);return new JsonObject{["path"]=Path.Combine(root,"CDCRD-PARTIDAS-"+digest[..16]+".csv"),["sha256"]=digest,["csv"]=csv.ToString(),["partidas"]=clean};
 }
 static Entity Resolve(Transaction tr,Database db,string handle)
 {
  if(!Regex.IsMatch(handle,"^[A-Fa-f0-9]{1,16}$")||!long.TryParse(handle,NumberStyles.HexNumber,CultureInfo.InvariantCulture,out long value)||value<=0||!db.TryGetObjectId(new Handle(value),out var id)||id.IsErased)throw new ArgumentException("Handle inexistente");
  var e=tr.GetObject(id,OpenMode.ForRead) as Entity??throw new ArgumentException("Entidad requerida");
  var space=(BlockTableRecord)tr.GetObject(e.OwnerId,OpenMode.ForRead);if(e.OwnerId!=((BlockTable)tr.GetObject(db.BlockTableId,OpenMode.ForRead))[BlockTableRecord.ModelSpace]||e.IsAProxy)throw new ArgumentException("Entidad local de ModelSpace requerida");
  return e;
 }
 static void Compatible(Entity e,string unit)
 {
  bool valid=unit switch {"EA"=>e is DBPoint,"M"=>e is Line||e is Polyline,"M2"=>e is Hatch,"M3"=>e is Solid3d,_=>false};
  if(!valid)throw new ArgumentException("Tipo no soportado para unidad "+unit);
  if(e is Line l&&(l.Length<=1e-9||Math.Abs(l.StartPoint.Z-l.EndPoint.Z)>1e-9))throw new ArgumentException("Linea horizontal no degenerada requerida");
  if(e is Polyline p&&(p.Length<=1e-9||(p.Normal-Autodesk.AutoCAD.Geometry.Vector3d.ZAxis).Length>1e-9))throw new ArgumentException("Polilinea XY no degenerada requerida");
  if(e is Hatch h&&(!double.IsFinite(h.Area)||h.Area<=1e-9||(h.Normal-Autodesk.AutoCAD.Geometry.Vector3d.ZAxis).Length>1e-9))throw new ArgumentException("Hatch XY con area positiva requerido");
  if(e is Solid3d s&&(!double.IsFinite(s.MassProperties.Volume)||s.MassProperties.Volume<=1e-9))throw new ArgumentException("Solido con volumen positivo requerido");
 }
 static string[] Ids(ObjectId id)=>QTOUtility.GetPayItemIds(id).Cast<string>().OrderBy(s=>s,StringComparer.Ordinal).ToArray();
 static object Assign(JsonObject p,Transaction tr,Database db,JsonObject catalog,bool sim)
 {
  var items=catalog["partidas"].AsArray().Select(n=>n.AsObject()).ToDictionary(n=>Text(n,"codigo"),StringComparer.Ordinal);
  var pairs=new HashSet<string>(StringComparer.OrdinalIgnoreCase);var planned=new List<(Entity e,string code,string[] before)>();
  foreach(var n in Rows(p,"asignaciones"))
  {
   var row=n as JsonObject??throw new ArgumentException("Asignacion debe ser objeto");string code=Text(row,"partida");var e=Resolve(tr,db,Text(row,"handle"));
   if(!items.TryGetValue(code,out var item))throw new ArgumentException("Partida ausente del catalogo");
   if(!pairs.Add(e.Handle+"|"+code))throw new ArgumentException("Asignacion duplicada");Compatible(e,Text(item,"unidad"));
   var ids=Ids(e.ObjectId);if(ids.Contains(code))throw new ArgumentException("Partida ya asignada; no repetir");planned.Add((e,code,ids));
  }
  if(sim)return new{simulation=true,simulation_scope="validated plan only; no native assignment",assignments=planned.Select(x=>new{handle=x.e.Handle.ToString(),partida=x.code,before=x.before}).ToArray()};
  foreach(var x in planned){if(!x.e.IsWriteEnabled)x.e.UpgradeOpen();QTOUtility.AddPayItemId(x.e.ObjectId,x.code);QaCheckpoint?.Invoke("assigned");}
  foreach(var g in planned.GroupBy(x=>x.e.ObjectId)){var expected=g.First().before.Concat(g.Select(x=>x.code)).OrderBy(s=>s,StringComparer.Ordinal).ToArray();if(!Ids(g.Key).SequenceEqual(expected))throw new InvalidOperationException("Asignaciones nativas distintas");}
  return new{simulation=false,assignments=planned.GroupBy(x=>x.e.ObjectId).Select(g=>new{handle=g.Key.Handle.ToString(),payitems=Ids(g.Key)}).ToArray()};
 }
 static object Report(JsonObject catalog)
 {
  var detail=new QTOGenerateDetail{ReportType=QTOReportType.SummaryReport,ReportExtent=QTOReportExtent.DrawingExtent,ReportSheetOnly=false,ReportSelectedPayItemsOnly=false};
  string path="";string[] ids=Array.Empty<string>();
  if(!QTOUtility.GenerateXMLReport(detail,ref path,ref ids)||!File.Exists(path))throw new InvalidOperationException("Civil no genero informe QTO");
  string xml=File.ReadAllText(path),csvPath="";
  if(!QTOUtility.TransformXMLReport(QTOReportFormat.SummaryCSV,path,ids,ref csvPath)||!File.Exists(csvPath))throw new InvalidOperationException("Civil no transformo informe CSV");
  var parsed=XDocument.Parse(xml);var known=catalog["partidas"].AsArray().Select(n=>n.AsObject()).ToDictionary(n=>Text(n,"codigo"));
  string Value(XElement e,string name)=>e.Descendants().Single(n=>n.Name.LocalName==name).Value;
  var quantities=parsed.Descendants().Where(e=>e.Name.LocalName=="DesignProjectPayItem").Select(e=>{
   string code=Value(e,"referencePayItemID"),unit=Value(e,"unitOfMeasureID");
   double quantity=double.Parse(Value(e,"estimatedQuantity"),CultureInfo.InvariantCulture);
   if(!known.TryGetValue(code,out var item)||Text(item,"unidad")!=unit||!double.IsFinite(quantity)||quantity<0)throw new InvalidOperationException("Cantidad/unidad/codigo del informe fuera del contrato");
   return new{code,unit,quantity};
  }).ToArray();
  if(quantities.Select(q=>q.code).Distinct().Count()!=quantities.Length||!quantities.Select(q=>q.code).OrderBy(s=>s).SequenceEqual(ids.OrderBy(s=>s)))throw new InvalidOperationException("Partidas del informe inconsistentes");
  string declared=parsed.Root.Elements().Single(e=>e.Name.LocalName=="unitSystem").Value;
  return new{scope="entire drawing; no selection filter",payitems=ids,quantities,native_unit_system=declared,units_contract="Use each pay item unit EA/M/M2/M3; native XML header may say english even with metric rows",prices_supported=false,xml,csv=File.ReadAllText(csvPath),native_xml_path=path,native_csv_path=csvPath};
 }
 internal static object Execute(JsonObject p,out bool committed)
 {
  committed=false;var doc=App.DocumentManager.MdiActiveDocument??throw new InvalidOperationException("Sin dibujo");
  if(!DateTimeOffset.TryParse(Text(p,"vence_utc"),out var expires)||expires<DateTimeOffset.UtcNow||expires>DateTimeOffset.UtcNow.AddMinutes(5))throw new ArgumentException("Solicitud vencida o plazo invalido");
  if(p["pid"]?.GetValue<int>()!=Environment.ProcessId||!Path.IsPathFullyQualified(Text(p,"dibujo"))||!Path.GetFullPath(doc.Name).Equals(Path.GetFullPath(Text(p,"dibujo")),StringComparison.OrdinalIgnoreCase))throw new ArgumentException("Documento o PID distinto");
  if(Convert.ToInt32(App.GetSystemVariable("INSUNITS"))!=6||CivilApp.ActiveDocument.Settings.DrawingSettings.UnitZoneSettings.DrawingUnits.ToString()!="Meters")throw new ArgumentException("Unidades Civil/AutoCAD en metros requeridas");
  string action=Text(p,"accion");bool sim=p["simular"]?.GetValue<bool>()??true,write=action=="catalogo"||action=="asignar";
  if(!new[]{"catalogo","asignar","leer","informe","estado"}.Contains(action))throw new ArgumentException("Accion desconocida");
  if(write&&(Environment.GetEnvironmentVariable("CDCRD_C3D_SOLO_LECTURA")=="1"||Environment.GetEnvironmentVariable("CDCRD_C3D_PERMITIR_COMANDOS")!="1"))throw new InvalidOperationException("Escritura deshabilitada");
  using(doc.LockDocument())using(var tr=doc.Database.TransactionManager.StartTransaction())
  {
   if(action=="estado")return new{catalog=QTOUtility.PayItemFilePath,format=QTOUtility.PayItemFileFormat.ToString(),categories=QTOUtility.PayItemCategorizationPath};
   if(action=="catalogo")
   {
    var plan=PlanCatalog(p,Path.GetDirectoryName(doc.Name));if(!string.IsNullOrEmpty(QTOUtility.PayItemFilePath))throw new InvalidOperationException("Ya existe catalogo; no se reemplaza");
    var d=(DBDictionary)tr.GetObject(doc.Database.NamedObjectsDictionaryId,OpenMode.ForRead);if(d.Contains(Record))throw new InvalidOperationException("Contrato previo existente; inspeccionar");
    if(!sim)
    {
     string path=Text(plan,"path");byte[] bytes=new UTF8Encoding(false).GetBytes(plan["csv"].GetValue<string>());
     if(File.Exists(path)){if(Hash(File.ReadAllBytes(path))!=Text(plan,"sha256"))throw new IOException("Archivo de catalogo distinto");}
     else using(var f=new FileStream(path,FileMode.CreateNew,FileAccess.Write)){f.Write(bytes);}
     if(File.Exists(Path.ChangeExtension(path,"for")))throw new IOException("Formulas externas no soportadas");
     if(!QTOUtility.OpenPayItemFile(PayItemFileFormat.CommaSeparated,path,""))throw new InvalidOperationException("Civil rechazo catalogo");
     // Catalog loader changes native state outside transaction rollback.
     committed=true;plan.Remove("csv");Store(tr,doc.Database,plan);tr.Commit();
    }
    return new{simulation=sim,simulation_scope="catalog validation only; loader is not transactional",catalog=plan};
   }
   var catalog=Catalog(tr,doc.Database);object result;
   if(action=="asignar")result=Assign(p,tr,doc.Database,catalog,sim);
   else if(action=="leer")result=Rows(p,"handles").Select(n=>{var e=Resolve(tr,doc.Database,n.GetValue<string>());return new{handle=e.Handle.ToString(),type=e.GetType().Name,payitems=Ids(e.ObjectId)};}).ToArray();
   else result=Report(catalog);
   if(write&&!sim){tr.Commit();committed=true;}else tr.Abort();return result;
  }
 }
}

