using System;
using System.Linq;
namespace Cdcrd.Civil3dBridge
{
 // Pavement layers and daylight slopes for the roadway assembly tools.
 internal static class CalzadaContract
 {
  internal static double[] Depths(double[] values)
  {
   if(values==null||values.Length!=4)throw new ArgumentException("espesores requiere exactamente [pave1,pave2,base,subbase]");
   foreach(double value in values)CorridorContract.Range(value,.01,2,"espesor");
   if(values.Sum()>5)throw new ArgumentException("espesores suman mas de 5 m");
   return values;
  }
  internal static double Talud(double value,string name)=>CorridorContract.Range(value,.1,10,name);
 }
}
