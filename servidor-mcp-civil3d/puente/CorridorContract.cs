using System;
using System.Linq;
namespace Cdcrd.Civil3dBridge
{
 internal static class CorridorContract
 {
  internal static double Range(double value,double min,double max,string name)
  {if(!double.IsFinite(value)||value<min||value>max)throw new ArgumentException(name+" fuera de rango finito");return value;}
  internal static void Region(double start,double end,double axisStart,double axisEnd,double frequency)
  {
   Range(start,axisStart,axisEnd,"inicio");Range(end,axisStart,axisEnd,"fin");Range(frequency,.1,1000,"frecuencia");
   if(end-start<=1e-6 || (end-start)/frequency>1000)throw new ArgumentException("Region vacia o mas de 1000 intervalos");
  }
  internal static double[] Stations(double[] values,double start,double end)
  {
   if(values==null||values.Length>500)throw new ArgumentException("Hasta 500 estaciones");
   for(int i=0;i<values.Length;i++)
   {Range(values[i],start,end,"estacion");if(i>0&&values[i]-values[i-1]<=1e-6)throw new ArgumentException("Estaciones deben estar ordenadas sin duplicados");}
   return values;
  }
 }
}
