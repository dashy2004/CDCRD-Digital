using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
namespace Cdcrd.Targets;
internal sealed record BindingSpec(string Baseline,string Region,string Subassembly,string Width,string Elevation);
internal static class TargetContract
{
 internal static string Text(JsonObject p,string key)
 {
  string s=p[key]?.GetValue<string>();
  if(string.IsNullOrWhiteSpace(s)||s.Length>200||s.Any(char.IsControl))throw new ArgumentException("Texto requerido de hasta 200 caracteres: "+key);
  return s;
 }
 internal static BindingSpec[] Parse(JsonArray array)
 {
  if(array==null||array.Count<1||array.Count>100)throw new ArgumentException("Se requieren 1..100 asignaciones");
  var keys=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
  return array.Select(node=>{
   var row=node as JsonObject??throw new ArgumentException("Asignacion debe ser objeto");
   string b=Text(row,"baseline"),r=Text(row,"region"),s=Text(row,"subensamblaje");
   if(!keys.Add(b+"\0"+r+"\0"+s))throw new ArgumentException("Asignacion duplicada");
   string w=row["alineamiento_ancho"]==null?null:Text(row,"alineamiento_ancho");
   string z=row["perfil_cota"]==null?null:Text(row,"perfil_cota");
   if(w==null&&z==null)throw new ArgumentException("Indique alineamiento_ancho o perfil_cota");
   return new BindingSpec(b,r,s,w,z);
  }).ToArray();
 }
 internal static double Width(double value)
 {if(!double.IsFinite(value)||value<.01||value>50)throw new ArgumentException("Ancho objetivo fuera de 0.01..50 m");return value;}
}
