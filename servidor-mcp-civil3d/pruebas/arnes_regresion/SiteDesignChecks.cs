using Cdcrd.Civil3dBridge;
static class SiteDesignChecks
{
 internal static void Run(Action<bool,string> check)
 {
  var rectangle=new[]{(400000d,2000000d),(400080d,2000000d),(400080d,2000050d),(400000d,2000050d)};
  check(SiteDesignContract.Polyline(rectangle,true)==4000,"parcela area independiente de coordenadas grandes");
  check(SiteDesignContract.Polyline(rectangle.Reverse().ToArray(),true)==4000,"area independiente del sentido");
  foreach(var bad in new[]{new[]{(0d,0d),(10d,10d),(0d,10d),(10d,0d)},new[]{(0d,0d),(10d,0d),(5d,0d),(5d,10d)},new[]{(0d,0d),(10d,0d),(0d,0d)},new[]{(double.NaN,0d),(10d,0d),(0d,10d)},new[]{(0d,0d),(5d,0d),(10d,0d)}})
  { try{SiteDesignContract.Polyline(bad,true);throw new Exception("bad polygon accepted");}catch(ArgumentException){check(true,"rechaza poligono degenerado o cruzado");} }
  check(SiteDesignContract.Polyline(new[]{(0d,0d),(10d,0d),(20d,5d)},false)==0,"eje abierto no devuelve area de parcela");
  SiteDesignContract.Pvis(new[]{(0d,100d),(50d,101d),(100d,99d)},0,100);check(true,"PVI ordenados dentro del eje");
  foreach(var bad in new[]{new[]{(0d,100d)},new[]{(0d,100d),(0d,101d)},new[]{(100d,100d),(0d,101d)},new[]{(-1d,100d),(100d,101d)},new[]{(0d,100d),(101d,101d)},new[]{(0d,100d),(100d,double.NaN)}})
  {try{SiteDesignContract.Pvis(bad,0,100);throw new Exception("bad PVIs accepted");}catch(ArgumentException){check(true,"rechaza PVI invalidos sin ordenar o recortar silenciosamente");}}
 }
}
