using System;
using System.Text.Json.Nodes;
using Cdcrd.Targets;
internal static class TargetChecks
{
 internal static void Run(Action<bool,string> check)
 {
  JsonArray Input()=>JsonNode.Parse("""[{"baseline":"A","region":"A1","subensamblaje":"AA","alineamiento_ancho":"BB","perfil_cota":"CC"}]""") as JsonArray;
  check(TargetContract.Parse(Input())[0].Elevation=="CC","targets ancho y cota explicitos");
  var width=Input();width[0]["perfil_cota"]=null;check(TargetContract.Parse(width)[0].Elevation==null,"target solo ancho");
  var height=Input();height[0]["alineamiento_ancho"]=null;check(TargetContract.Parse(height)[0].Width==null,"target solo cota");
  void Bad(Action<JsonArray> edit,string name){var a=Input();edit(a);bool rejected=false;try{TargetContract.Parse(a);}catch(ArgumentException){rejected=true;}check(rejected,name);}
  Bad(a=>a.Clear(),"rechaza lista vacia de targets");
  Bad(a=>{a[0]["alineamiento_ancho"]=null;a[0]["perfil_cota"]=null;},"rechaza asignacion sin objetivo");
  Bad(a=>a[0]["subensamblaje"]=" ","requiere subensamblaje explicito");
  Bad(a=>a[0]["baseline"]="A\nB","rechaza control en nombre de baseline");
  Bad(a=>a[0]["perfil_cota"]=new string('a',201),"limita nombres objetivo");
  Bad(a=>{var b=a[0].DeepClone();b["baseline"]="a";a.Add(b);},"rechaza duplicados sin distinguir mayusculas");
  Bad(a=>{for(int i=0;i<100;i++){var b=a[0].DeepClone();b["region"]="R"+i;a.Add(b);}},"limita presupuesto de asignaciones");
  foreach(double value in new[]{double.NaN,double.PositiveInfinity,0,.009,50.001})
  {bool rejected=false;try{TargetContract.Width(value);}catch(ArgumentException){rejected=true;}check(rejected,"ancho objetivo invalido "+value);}
  check(TargetContract.Width(.01)==.01&&TargetContract.Width(50)==50,"acepta limites de ancho sin recortar");
 }
}
