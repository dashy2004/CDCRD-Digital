using Cdcrd.Peraltes;
using Cdcrd.Civil3dBridge;
using System.Text.Json.Nodes;
internal static class PeralteChecks
{
 internal static void Run(Action<bool,string> check)
 {
  void Reject(Action fn,string name){try{fn();}catch(ArgumentException){check(true,name);return;}throw new Exception(name+" accepted");}
  var rows=PeralteContract.Parse(JsonNode.Parse("[[100,-0.02,-0.02],[140,-0.02,-0.02],[180,0.06,-0.06],[240,0.06,-0.06],[280,-0.02,-0.02]]"));
  PeralteContract.Extent(rows,100,280);
  check(Math.Abs(PeralteContract.At(rows,160,1)-.02)<1e-12,"peralte lado izquierdo interpolado");
  check(Math.Abs(PeralteContract.At(rows,160,2)+.04)<1e-12,"peralte lado derecho interpolado");
  check(Math.Abs(PeralteContract.At(rows,280,1)+.02)<1e-12,"peralte extremo final");
  Reject(()=>PeralteContract.Extent(rows,0,280),"tabla debe cubrir extremos");
  Reject(()=>PeralteContract.Parse(JsonNode.Parse("[[0,0,0],[0,0,0],[1,0,0]]")),"rechaza estaciones duplicadas");
  Reject(()=>PeralteContract.Parse(JsonNode.Parse("[[0,0,0],[1,0.13,0],[2,0,0]]")),"rechaza pendiente fuera de contrato");
  Reject(()=>PeralteContract.Parse(JsonNode.Parse("[[0,0,0],[2,0,0]]")),"requiere estacion interior");
  Reject(()=>PeralteContract.At(rows,300,1),"no extrapola peraltes");
  Reject(()=>NativeCallContract.ValidateInspection("Autodesk.Civil.DatabaseServices.Subassembly",true),"bloquea barrido de getters Subassembly");
  NativeCallContract.ValidateInspection("Autodesk.Civil.DatabaseServices.Subassembly",false);
  NativeCallContract.ValidateInspection("Autodesk.Civil.DatabaseServices.Alignment",true);
  check(true,"inspeccion de firmas disponible");
 }
}
