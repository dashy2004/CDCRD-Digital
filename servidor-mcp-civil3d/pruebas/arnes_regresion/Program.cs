using Cdcrd.Civil3dBridge;
using System.Text.Json;
using System.Text.Json.Nodes;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;

class Sample {
 public int Field = 9;
 public string NullField = null;
 public int Property => 12;
 public int this[int i] => i;
 public int Broken => throw new InvalidOperationException("getter real");
}
class Program {
 static int checks;
 static void Check(bool condition, string name) {
  if (!condition) throw new Exception("FAIL " + name);
  checks++; Console.WriteLine("OK " + name);
 }
 static object Read(object target, string name) {
  if (!ReflectionRead.TryRead(target,name,out var value)) throw new Exception("Miembro ausente " + name);
  return value;
 }
 static JsonElement Queue() => JsonSerializer.SerializeToElement(HiloPrincipal.EstadoCola());
 static void Queued() {
  if (!SpinWait.SpinUntil(()=>Queue().GetProperty("activas").GetArrayLength()>0,3000)) throw new Exception("No se encolo");
 }
 static async Task Main() {
  ThreadPool.SetMinThreads(8,8);
  SpiralChecks.Run(Check);
  MultiChecks.Run(Check);
  PeralteChecks.Run(Check);
  SiteDesignChecks.Run(Check);
  CorridorChecks.Run(Check);
  CalzadaChecks.Run(Check);
  CunetaBermaChecks.Run(Check);
  PlatformChecks.Run(Check);
  VerticalCurveChecks.Run(Check);
  long commandClock=0;
  var receipts=new CommandReceipts(()=>commandClock,100);
  var commandId=receipts.Add("A.dwg","LINE");
  try {receipts.Add("A.dwg","CIRCLE");throw new Exception("Doble comando aceptado");}
  catch(InvalidOperationException){Check(true,"un comando seguido por documento");}
  commandClock=100;
  Check(!receipts.Start(commandId),"ticket vencido no ejecuta al volver Idle");
  commandId=receipts.Add("A.dwg","LINE");
  Check(receipts.Start(commandId),"ticket vivo inicia una vez");
  Check(!receipts.Start(commandId),"ticket no ejecuta dos veces");
  commandClock=1000;
  Check((string)((Dictionary<string,object>)receipts.Get(commandId))["estado"]=="en_ejecucion","timeout no cancela comando iniciado");
  receipts.Event(commandId,"fin:LINE");receipts.Finish(commandId,"terminado");
  receipts.Finish(commandId,"fallido");
  Check((bool)((Dictionary<string,object>)receipts.Get(commandId))["correcto"],"estado final no se sobrescribe");
  foreach(var state in new[]{"fallido","cancelado","desconocido"}) {
   commandId=receipts.Add("A.dwg","LINE");receipts.Start(commandId);receipts.Finish(commandId,state);
   Check(!(bool)((Dictionary<string,object>)receipts.Get(commandId))["correcto"],"solo CommandEnded acredita fin correcto");
  }
  GmSurfaceContract.RequireLocations(new[]{("A",0d,0d),("B",10d,0d),("C",0d,10d)});
  Check(true,"GM superficie acepta sondeos no colineales");
  foreach(var points in new[] {
   new[]{("A",0d,0d),("B",1d,1d)},
   new[]{("A",0d,0d),("B",1d,1d),("C",2d,2d)},
   new[]{("A",0d,0d),("a",10d,0d),("C",0d,10d)},
   new[]{("A",0d,0d),("B",0d,0d),("C",0d,10d)},
   new[]{("A",0d,0d),("B",double.NaN,0d),("C",0d,10d)}}) {
   try {GmSurfaceContract.RequireLocations(points);throw new Exception("TIN degenerado aceptado");}
   catch(ArgumentException){Check(true,"GM superficie rechaza geometria o identidad invalida");}
  }
  Check(GmSurfaceContract.BottomElevation(100,20)==80,"fondo usa cota menos profundidad registrada");
  foreach(var pair in new[]{(double.NaN,20d),(100d,0d),(100d,-1d),(100d,double.PositiveInfinity)}) {
   try {GmSurfaceContract.BottomElevation(pair.Item1,pair.Item2);throw new Exception("Fondo invalido aceptado");}
   catch(ArgumentException){Check(true,"fondo rechaza profundidad o cota invalida");}
  }
  var expectedSurfaces=GmSurfaceContract.SurfaceNames(new[]{"Sand.1","Rock.1"});
  GmSurfaceContract.RequireBottom(false,expectedSurfaces);
  GmSurfaceContract.RequireBottom(true,new[]{"GM - Stratum - Borehole Bottom"});
  Check(true,"GM fondo solo es obligatorio si fue solicitado");
  try {GmSurfaceContract.RequireBottom(true,expectedSurfaces);throw new Exception("GM omitio fondo solicitado");}
  catch(InvalidOperationException){Check(true,"GM no confirma exito si falta el fondo solicitado");}
  Check(GmSurfaceContract.Complete(expectedSurfaces,expectedSurfaces.Reverse()),"GM superficie valida nombres, sin depender del orden");
  Check(!GmSurfaceContract.Complete(expectedSurfaces,new[]{expectedSurfaces[0],expectedSurfaces[0]}) &&
   !GmSurfaceContract.Complete(expectedSurfaces,expectedSurfaces.Take(1)) &&
   !GmSurfaceContract.Complete(Array.Empty<string>(),Array.Empty<string>()),"GM superficie rechaza resultado duplicado, parcial o vacio");
  foreach(var names in new[]{new[]{"sand","SAND"},new[]{"../outside"},new[]{"folder\\file"},Array.Empty<string>()}) {
   try {GmSurfaceContract.SurfaceNames(names);throw new Exception("Nombre peligroso aceptado");}
   catch(ArgumentException){Check(true,"GM superficie rechaza colisiones y rutas de archivo invalidas");}
  }
  var steps = new List<string>();
  Check(GmAtomicOperation.Execute(()=>{steps.Add("work");return true;},
   ()=>steps.Add("commit"),()=>steps.Add("abort")) && steps.SequenceEqual(new[]{"work","commit"}),
   "GM completo confirma una vez sin abortar");
  steps.Clear();
  Check(!GmAtomicOperation.Execute(()=>{steps.Add("partial");return false;},
   ()=>steps.Add("commit"),()=>steps.Add("abort")) && steps.SequenceEqual(new[]{"partial","abort"}),
   "GM parcial sin excepcion revierte sin confirmar");
  steps.Clear();
  var originalFailure = new InvalidOperationException("render late failure");
  try {
   GmAtomicOperation.Execute(()=>{steps.Add("partial");throw originalFailure;},
    ()=>steps.Add("commit"),()=>steps.Add("abort"));
   throw new Exception("GM acepto fallo tardio");
  } catch(InvalidOperationException e) {
   Check(ReferenceEquals(e,originalFailure) && steps.SequenceEqual(new[]{"partial","abort"}),
    "GM fallo tardio revierte una vez y conserva excepcion");
  }
  steps.Clear();
  try {
   GmAtomicOperation.Execute(()=>true,
    ()=>{steps.Add("commit");throw new InvalidOperationException("commit");},()=>steps.Add("abort"));
   throw new Exception("GM acepto commit fallido");
  } catch(InvalidOperationException) {
   Check(steps.SequenceEqual(new[]{"commit","abort"}),"GM commit fallido intenta revertir");
  }
  int aborts=0;
  try {
   GmAtomicOperation.Execute(()=>throw originalFailure,()=>{},
    ()=>{aborts++;throw new IOException("abort");});
   throw new Exception("GM oculto rollback fallido");
  } catch(AggregateException e) {
   Check(aborts==1 && e.InnerExceptions.Count==2 && ReferenceEquals(e.InnerExceptions[0],originalFailure),
    "GM no oculta error original ni fallo de reversion");
  }
  aborts=0;
  try {
   GmAtomicOperation.Execute(()=>false,()=>{},()=>{aborts++;throw new IOException("abort");});
   throw new Exception("GM oculto rollback de resultado parcial");
  } catch(AggregateException e) {
   Check(aborts==1 && e.InnerExceptions.Count==1,"GM parcial no anuncia reversion si abort falla");
  }
  Check(GmProfileContract.Field("GeologyCode1","LegendCode")=="GeologyCode1","campo explicito conserva eleccion");
  Check(GmProfileContract.Field("", "LegendName")=="LegendName","reutiliza campo guardado");
  foreach(var field in new[] {"", "GeologyCode", "GeologyCode3"}) {
   try {GmProfileContract.Field(field, "");throw new Exception("campo invalido aceptado");}
   catch(ArgumentException) {Check(true,"rechaza campo vacio/desconocido antes de escribir");}
  }
  try {GmProfileContract.RequireStrata(new Dictionary<string,int>{{"S1",4},{"S2",0}});throw new Exception("cobertura incompleta aceptada");}
  catch(ArgumentException) {Check(true,"rechaza campo sin estratos en un sondeo");}
  GmProfileContract.RequireStrata(new Dictionary<string,int>{{"S1",4},{"S2",4}});
  Check(GmProfileContract.Complete(5,0,5),"render completo positivo");
  Check(!GmProfileContract.Complete(0,5,5),"no confunde cinco omitidos con exito");
  Check(!GmProfileContract.Complete(0,0,0)&&!GmProfileContract.Complete(4,0,5),"rechaza render vacio o parcial");
  var tuple=("diagrama",42);
  Check((string)Read(tuple,"Item1")=="diagrama","ValueTuple.Item1 campo");
  Check((int)Read(tuple,"item2")==42,"campo sin distinguir mayusculas");
  Check((string)Read(Tuple.Create("clasica",2),"Item1")=="clasica","Tuple.Item1 propiedad conservada");
  var nested=((1,2),3);
  Check((int)Read(Read(nested,"Item1"),"Item2")==2,"tupla anidada");
  Check((int)Read(new Sample(),"Field")==9 && (int)Read(new Sample(),"Property")==12,"campos y propiedades normales");
  Check(ReflectionRead.TryRead(new Sample(),"NullField",out var v)&&v==null,"campo existente null");
  Check(!ReflectionRead.TryRead(new Sample(),"Item",out _)&&!ReflectionRead.TryRead(null,"Item1",out _),"indexador y null rechazados");
  try { Read(new Sample(),"Broken"); throw new Exception("no lanzo"); }
  catch (InvalidOperationException e) {Check(e.Message=="getter real","excepcion original del getter");}
  Check(GmGroupPolicy.EmptyGm("GM - test",0,0),"grupo GM vacio detectado");
  Check(!GmGroupPolicy.EmptyGm("AJENO",0,0),"grupo ajeno vacio conservado");
  Check(!GmGroupPolicy.EmptyGm("GM - ocupado",1,0),"grupo GM vivo conservado");
  Check(!GmGroupPolicy.CanErase("AJENO",0,true,0,true),"referencias desconocidas ajenas conservadas");
  Check(GmGroupPolicy.CanErase("residual",0,true,1,false),"miembros GM muertos identificados");
  Check(!GmGroupPolicy.CanErase("GM - mixto",1,false,2,false),"grupo mixto conservado");
  HiloPrincipal.Suscribir();
  int writes=0;
  var pending=Task.Run(()=> {
   try {HiloPrincipal.Ejecutar(()=> {Interlocked.Increment(ref writes);return 1;},30,"cancel-test");return (BridgeException)null;}
   catch(BridgeException e){return e;}
  });
  var cancelled=await pending;
  Check(cancelled!=null && JsonSerializer.SerializeToElement(cancelled.Detalle).GetProperty("cancelada_antes_de_ejecutar").GetBoolean(),"timeout pendiente identificado como cancelado");
  App.Pump();
  Check(writes==0,"peticion cancelada no escribe al volver Idle");
  var call=Task.Run(()=>HiloPrincipal.Ejecutar(()=>42,2000,"success"));Queued();App.Pump();
  Check((int)await call==42,"resultado normal");
  var running=Task.Run(()=> {
   try {HiloPrincipal.Ejecutar(()=>{Thread.Sleep(250);Interlocked.Increment(ref writes);return 8;},100,"running-test");return (BridgeException)null;}
   catch(BridgeException e){return e;}
  });
  Queued(); App.Pump(); var uncertain=await running;
  var data=JsonSerializer.SerializeToElement(uncertain.Detalle);
  Check(data.GetProperty("resultado_incierto").GetBoolean() && writes==1,"operacion iniciada no se anuncia cancelada");
  var id=data.GetProperty("request_id").GetString();
  Check(Queue().GetProperty("recientes").EnumerateArray().Any(x=>x.GetProperty("request_id").GetString()==id && x.GetProperty("estado").GetString()=="terminada"),"finalizacion consultable por id");
  var fault=Task.Run(()=> {
   try {HiloPrincipal.Ejecutar(()=>throw new InvalidOperationException("fallo real"),2000,"fault");return "missing";}
   catch(InvalidOperationException e){return e.Message;}
  });Queued();App.Pump();Check(await fault=="fallo real","propaga error de operacion");
  var stop=Task.Run(()=> {
   try{HiloPrincipal.Ejecutar(()=>{Interlocked.Increment(ref writes);return 1;},2000,"stop");return false;}
   catch(BridgeException e){return e.Code==Rpc.ErrBusy;}
  });Queued();HiloPrincipal.Desuscribir();Check(await stop && writes==1,"desuscribir cancela pendientes");
  HiloPrincipal.Suscribir();
  for(int i=0;i<100;i++) {
   var raced=Task.Run(()=>{try{HiloPrincipal.Ejecutar(()=>{Interlocked.Increment(ref writes);return 1;},1,"race");return false;}catch(BridgeException e){return JsonSerializer.SerializeToElement(e.Detalle).GetProperty("cancelada_antes_de_ejecutar").GetBoolean();}});
   if(i%2==0) await Task.Delay(2);
   int before=writes;App.Pump();bool c=await raced;App.Pump();
   if(c && writes!=before) throw new Exception("cancelada escribio en carrera");
  }
  Check(Queue().GetProperty("activas").GetArrayLength()==0,"100 carreras: ninguna cancelada ejecutada, sin activas");
  Check(Queue().GetProperty("recientes").GetArrayLength()<=64,"historial acotado");
  var rpc=JsonNode.Parse(Rpc.Err(null,Rpc.ErrBusy,"timeout",cancelled.Detalle));
  Check(rpc["error"]["data"]["cancelada_antes_de_ejecutar"].GetValue<bool>(),"RPC conserva data estructurada");
  HiloPrincipal.Desuscribir();
  Console.WriteLine($"PASS {checks} comprobaciones + 100 carreras (codigo real Bridge/Rpc)");
 }
}
