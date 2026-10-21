using Cdcrd.Civil3dBridge;
static class CorridorChecks
{
 internal static void Run(Action<bool,string> check)
 {
  foreach(string name in new[]{"GetSectionSources","getsectionsources"})
  {try{NativeCallContract.Validate("Autodesk.Civil.DatabaseServices.SampleLineGroup",name);throw new Exception("accepted");}catch(ArgumentException){check(true,"bloquea consulta nativa fatal por reflexion");}}
  NativeCallContract.Validate("Autodesk.Civil.DatabaseServices.SampleLineGroup","GetSampleLineIds");check(true,"conserva otras consultas genericas");
  CorridorContract.Region(100,465.663706,100,465.663706,10);check(true,"corredor region metrica valida");
  foreach(var tuple in new[]{(100d,100d,10d),(99d,300d,10d),(100d,501d,10d),(100d,300d,0d),(100d,300d,double.NaN),(100d,300d,.1d)})
  {try{CorridorContract.Region(tuple.Item1,tuple.Item2,100,500,tuple.Item3);throw new Exception("accepted");}catch(ArgumentException){check(true,"rechaza region o frecuencia invalida");}}
  foreach(var a in new[]{new[]{150d,140d},new[]{150d,150d},new[]{99d},new[]{501d},new[]{double.NaN},new double[501]})
  {try{CorridorContract.Stations(a,100,500);throw new Exception("accepted");}catch(ArgumentException){check(true,"rechaza estaciones invalidas sin ordenar ni recortar");}}
  check(CorridorContract.Stations(new[]{100d,250d,500d},100,500).Length==3,"conserva extremos y estacion interior");
  foreach(double bad in new[]{double.NaN,double.PositiveInfinity,-.01,51})
  {try{CorridorContract.Range(bad,.01,50,"ancho");throw new Exception("accepted");}catch(ArgumentException){check(true,"rechaza ancho no finito o excesivo");}}
 }
}
