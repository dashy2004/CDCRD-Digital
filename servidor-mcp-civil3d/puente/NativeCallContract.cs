using System;
namespace Cdcrd.Civil3dBridge
{
 internal static class NativeCallContract
 {
  internal static void ValidateInspection(string typeName,bool values)
  {
   // A 2027 process terminated during broad Subassembly value inspection after
   // an aborted superelevation transaction. The exact getter is not established.
   // Keep signatures available, but do not auto-evaluate the native getters.
   if(values && typeName=="Autodesk.Civil.DatabaseServices.Subassembly")
    throw new ArgumentException("Inspeccion masiva de valores de Subassembly deshabilitada; use valores=false para firmas y operaciones nativas especificas para geometria/parametros.");
  }
  internal static void Validate(string typeName,string method)
  {
   // A Get prefix is not proof of read safety. Civil 2027 aborts the process
   // when GetSectionSources runs on a SampleLineGroup opened ForRead.
   if(typeName=="Autodesk.Civil.DatabaseServices.SampleLineGroup" && string.Equals(method,"GetSectionSources",StringComparison.OrdinalIgnoreCase))
    throw new ArgumentException("GetSectionSources no es seguro por reflexion generica; use civil.secciones_corredor con transaccion nativa ForWrite.");
  }
 }
}
