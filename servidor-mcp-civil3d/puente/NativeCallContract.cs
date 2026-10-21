using System;
namespace Cdcrd.Civil3dBridge
{
 internal static class NativeCallContract
 {
  internal static void Validate(string typeName,string method)
  {
   // A Get prefix is not proof of read safety. Civil 2027 aborts the process
   // when GetSectionSources runs on a SampleLineGroup opened ForRead.
   if(typeName=="Autodesk.Civil.DatabaseServices.SampleLineGroup" && string.Equals(method,"GetSectionSources",StringComparison.OrdinalIgnoreCase))
    throw new ArgumentException("GetSectionSources no es seguro por reflexion generica; use civil.secciones_corredor con transaccion nativa ForWrite.");
  }
 }
}
