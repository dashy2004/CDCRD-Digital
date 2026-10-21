using Cdcrd.Civil3dBridge;
static class CalzadaChecks
{
 internal static void Run(Action<bool,string> check)
 {
  var depths=CalzadaContract.Depths(new[]{.05,.07,.2,.3});
  check(depths.Length==4&&depths[3]==.3,"espesores validos conservados sin reordenar");
  foreach(var bad in new[]{null,new double[0],new[]{.05,.07,.2},new[]{.05,.07,.2,.3,.1},new[]{0d,.07,.2,.3},new[]{.005,.07,.2,.3},new[]{.05,.07,.2,2.1},new[]{double.NaN,.07,.2,.3},new[]{2d,2d,1.5,.5}})
  {try{CalzadaContract.Depths(bad);throw new Exception("accepted");}catch(ArgumentException){check(true,"rechaza espesores invalidos (cantidad, rango, suma, no finitos)");}}
  check(CalzadaContract.Talud(3,"talud_corte")==3&&CalzadaContract.Talud(.1,"t")==.1&&CalzadaContract.Talud(10,"t")==10,"talud valido conservado con extremos");
  foreach(double bad in new[]{0d,.05,10.5,-3,double.NaN,double.PositiveInfinity})
  {try{CalzadaContract.Talud(bad,"talud");throw new Exception("accepted");}catch(ArgumentException){check(true,"rechaza talud fuera de 0.1-10 o no finito");}}
 }
}
