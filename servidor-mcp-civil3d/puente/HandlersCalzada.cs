// Roadway assembly with explicit pavement layers (shapes) and daylight, plus a
// corridor that assigns its surface targets and verifies daylight against the
// target TIN. All new geometry stays inside one transaction per operation.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil.Runtime;
using CivAssembly = Autodesk.Civil.DatabaseServices.Assembly;
using CivAlignment = Autodesk.Civil.DatabaseServices.Alignment;
using CivProfile = Autodesk.Civil.DatabaseServices.Profile;
using CivPoint = Autodesk.Civil.DatabaseServices.Point;
using CivTin = Autodesk.Civil.DatabaseServices.TinSurface;

namespace Cdcrd.Civil3dBridge
{
 internal static partial class Handlers
 {
  private static string ParamToken(string name)=>new string((name??"").Where(char.IsLetterOrDigit).ToArray()).ToLowerInvariant();
  private static ParamDouble CalzadaParam(Subassembly sub,params string[] aliases)
  {
   var wanted=aliases.Select(ParamToken).ToArray();
   foreach(ParamDouble q in sub.ParamsDouble)if(wanted.Contains(ParamToken(q.Key)))return q;
   throw new ArgumentException("Parametro "+aliases[0]+" no existe en "+sub.Name+"; claves: "+string.Join(", ",sub.ParamsDouble.Cast<ParamDouble>().Select(x=>x.Key)));
  }
  private static object CalzadaParamRow(ParamDouble q)=>new{clave=q.Key,valor=q.Value,tipo=q.TypeInfo.ToString()};
  private static object CreateRoadwayAssembly(JsonObject p,string method)
  {
   ExigirEscritura(method,p);SiteUnits();string name=SiteName(p,"nombre");var origin=CorridorOrigin(p);
   double left=CorridorContract.Range(RequiredNumber(p,"ancho_izq"),.01,50,"ancho_izq"),right=CorridorContract.Range(RequiredNumber(p,"ancho_der"),.01,50,"ancho_der");
   double sl=CorridorContract.Range(RequiredNumber(p,"pendiente_izq"),-1,1,"pendiente_izq"),sr=CorridorContract.Range(RequiredNumber(p,"pendiente_der"),-1,1,"pendiente_der");
   var depths=CalzadaContract.Depths(StationArray(p,"espesores"));
   double cut=CalzadaContract.Talud(RequiredNumber(p,"talud_corte"),"talud_corte"),fill=CalzadaContract.Talud(RequiredNumber(p,"talud_relleno"),"talud_relleno");
   double maxWidth=CorridorContract.Range(RequiredNumber(p,"ancho_daylight_max"),1,200,"ancho_daylight_max");
   var doc=Doc();var db=doc.Database;var civil=Civil();
   using(doc.LockDocument())using(var tr=db.TransactionManager.StartTransaction())
   {
    NewCivilName(tr,civil.AssemblyCollection,name);
    foreach(string suffix in new[]{"_L","_R","_DL_L","_DL_R"})NewCivilName(tr,civil.SubassemblyCollection,name+suffix);
    var layer=CapaId(tr,db,Txt(p,"capa"),true);
    var id=civil.AssemblyCollection.Add(name,AssemblyType.UndividedCrownedRoad,origin);
    var assembly=(CivAssembly)tr.GetObject(id,OpenMode.ForWrite);assembly.LayerId=layer;
    var parts=new List<object>();
    foreach(var side in new[]{(Suffix:"_L",Side:SubassemblySideType.Left,Width:left,Slope:sl),(Suffix:"_R",Side:SubassemblySideType.Right,Width:right,Slope:sr)})
    {
     var lid=civil.SubassemblyCollection.ImportStockSubassembly(name+side.Suffix,"Subassembly.LaneSuperelevationAOR",origin);
     var lane=(Subassembly)tr.GetObject(lid,OpenMode.ForWrite);lane.LayerId=layer;lane.Side=side.Side;
     CalzadaParam(lane,"Width").Value=side.Width;
     var slope=CalzadaParam(lane,"DefaultSlope","Slope","LaneSlope");slope.Value=side.Slope;
     var layerParams=new[]{CalzadaParam(lane,"Pave1Depth"),CalzadaParam(lane,"Pave2Depth"),CalzadaParam(lane,"BaseDepth"),CalzadaParam(lane,"SubBaseDepth","SubbaseDepth")};
     for(int i=0;i<4;i++)layerParams[i].Value=depths[i];
     assembly.AddSubassembly(lid);lane.Run();
     CorridorQaCheckpoint?.Invoke("calzada-part-added");
     if(lane.AssemblyId!=id||lane.Side!=side.Side||Math.Abs(CalzadaParam(lane,"Width").Value-side.Width)>1e-9||Math.Abs(slope.Value-side.Slope)>1e-9||
        Enumerable.Range(0,4).Any(i=>Math.Abs(layerParams[i].Value-depths[i])>1e-9)||lane.Shapes.Cast<Autodesk.Civil.DatabaseServices.Shape>().Count()<4)
      throw new InvalidOperationException("Carril no coincide con parametros solicitados o sin las cuatro capas");
     // Daylight hooks at the outermost, lowest lane point (subgrade edge).
     var hook=lane.Points.Cast<CivPoint>().OrderByDescending(pt=>Math.Abs(pt.Offset)).ThenBy(pt=>pt.Elevation).First();
     var did=civil.SubassemblyCollection.ImportStockSubassembly(name+"_DL"+side.Suffix,"Subassembly.DaylightMaxWidth",origin);
     var daylight=(Subassembly)tr.GetObject(did,OpenMode.ForWrite);daylight.LayerId=layer;daylight.Side=side.Side;
     var cutParam=CalzadaParam(daylight,"CutSlope");cutParam.Value=cut;
     var fillParam=CalzadaParam(daylight,"FillSlope");fillParam.Value=fill;
     var widthParam=CalzadaParam(daylight,"MaxWidth");widthParam.Value=maxWidth;
     assembly.AddSubassembly(did,hook);daylight.Run();
     CorridorQaCheckpoint?.Invoke("calzada-part-added");
     if(daylight.AssemblyId!=id||daylight.Side!=side.Side||daylight.SubassemblyHookTo!=lid||
        Math.Abs(cutParam.Value-cut)>1e-9||Math.Abs(fillParam.Value-fill)>1e-9||Math.Abs(widthParam.Value-maxWidth)>1e-9)
      throw new InvalidOperationException("Daylight no quedo enganchado al carril con los taludes solicitados");
     parts.Add(new{handle=HandleOf(lid),rol="carril",lado=lane.Side.ToString(),
      parametros=new[]{CalzadaParam(lane,"Width"),slope}.Concat(layerParams).Select(CalzadaParamRow).ToArray()});
     parts.Add(new{handle=HandleOf(did),rol="daylight",lado=daylight.Side.ToString(),engancha_a=HandleOf(lid),punto_enganche=hook.Index,
      codigos_enganche=hook.Codes.Cast<string>().ToArray(),parametros=new[]{cutParam,fillParam,widthParam}.Select(CalzadaParamRow).ToArray()});
    }
    bool sim=p["simular"]?.GetValue<bool>()??false;
    var result=new{handle=sim?null:HandleOf(id),nombre=name,subensamblajes=parts,espesores=depths,unidades="m",pendientes="m/m",simulacion=sim};
    if(sim)tr.Abort();else tr.Commit();return result;
   }
  }
  private static object CreateRoadwayCorridor(JsonObject p,string method)
  {
   ExigirEscritura(method,p);SiteUnits();string name=SiteName(p,"nombre");var doc=Doc();var db=doc.Database;var civil=Civil();
   using(doc.LockDocument())using(var tr=db.TransactionManager.StartTransaction())
   {
    NewCivilName(tr,civil.CorridorCollection,name);NewCivilName(tr,civil.GetSurfaceIds().Cast<ObjectId>(),name+"_Top");
    var aid=ResolverId(tr,db,civil.GetAlignmentIds(),Txt(p,"alineamiento"),"alineamiento");var a=(CivAlignment)tr.GetObject(aid,OpenMode.ForRead);
    if(a.IsReferenceObject||a.StationEquations.Count!=0)throw new ArgumentException("Eje de referencia o con ecuaciones no soportado");
    var pid=ResolverId(tr,db,a.GetProfileIds(),Txt(p,"perfil"),"perfil del alineamiento");if(!a.GetProfileIds().Cast<ObjectId>().Contains(pid))throw new ArgumentException("perfil no pertenece al alineamiento");var profile=(CivProfile)tr.GetObject(pid,OpenMode.ForRead);
    var sid=ResolverId(tr,db,new ObjectIdCollection(civil.AssemblyCollection.ToArray()),Txt(p,"ensamblaje"),"ensamblaje");
    var assembly=(CivAssembly)tr.GetObject(sid,OpenMode.ForRead);
    if(profile.IsReferenceObject||assembly.IsReferenceObject||assembly.Groups.Count==0)throw new ArgumentException("Perfil/ensamblaje invalido o de referencia");
    var tid=ResolverId(tr,db,civil.GetSurfaceIds(),Txt(p,"superficie_objetivo"),"superficie objetivo");
    if(tr.GetObject(tid,OpenMode.ForRead) is not CivTin target||target.IsReferenceObject)throw new ArgumentException("superficie_objetivo debe ser una TinSurface propia del dibujo");
    double start=RequiredNumber(p,"inicio"),end=RequiredNumber(p,"fin"),frequency=RequiredNumber(p,"frecuencia");
    CorridorContract.Region(start,end,Math.Max(a.StartingStation,profile.StartingStation),Math.Min(a.EndingStation,profile.EndingStation),frequency);
    var extra=CorridorContract.Stations(StationArray(p,"estaciones_extra"),start,end);
    var id=civil.CorridorCollection.Add(name,name+"_Baseline",aid,pid);var c=(Corridor)tr.GetObject(id,OpenMode.ForWrite);
    c.LayerId=CapaId(tr,db,Txt(p,"capa"),true);c.RebuildAutomatic=false;
    var baseline=c.Baselines[0];var region=baseline.BaselineRegions.Add(name+"_Region",sid,start,end);var settings=region.AppliedAssemblySetting;
    settings.CorridorAlongCurvesOption=Autodesk.Civil.CorridorAlongCurveOption.CurveAtIncrement;
    settings.FrequencyAlongTangents=frequency;settings.FrequencyAlongCurves=frequency;settings.FrequencyAlongSpirals=frequency;settings.FrequencyAlongProfileCurves=frequency;
    settings.AppliedAtHorizontalGeometryPoints=true;settings.AppliedAtProfileGeometryPoints=true;settings.AppliedAtProfileHighLowPoints=true;
    settings.AppliedAtSuperelevationCriticalPoints=false;settings.AppliedAtOffsetTargetGeometryPoints=false;settings.AppliedAdjacentToOffsetTargetStartEnd=false;
    foreach(double station in extra)region.AddStation(station,"Explicit sample station");
    // Every surface-type target of the region (daylight) points to the explicit TIN.
    var targets=region.GetTargets();var assigned=new List<object>();
    foreach(SubassemblyTargetInfo info in targets)
    {
     if(info.TargetType.ToString()!="Surface")continue;
     var ids=info.TargetIds;while(ids.Count>0)ids.RemoveAt(0);ids.Add(tid);info.TargetIds=ids;
     assigned.Add(new{logico=info.LogicalName,subensamblaje=info.SubassemblyName,objetivo=HandleOf(tid)});
    }
    if(assigned.Count==0)throw new ArgumentException("El ensamblaje no expone targets de superficie (daylight)");
    region.SetTargets(targets);
    CorridorQaCheckpoint?.Invoke("targets-assigned");
    c.Rebuild();CorridorQaCheckpoint?.Invoke("corridor-rebuilt");
    var codes=c.GetLinkCodes();
    if(region.AppliedAssemblies.Count==0||!codes.Contains("Top")||!codes.Contains("Daylight"))throw new InvalidOperationException("Corredor sin ensamblajes aplicados o sin codigos Top/Daylight");
    var stations=region.SortedStations();
    if(extra.Any(s=>!stations.Any(x=>Math.Abs(x-s)<1e-6)))throw new InvalidOperationException("Faltan estaciones explicitas");
    double maxDaylightDelta=0;
    var applied=stations.Select(s=>
    {
     var aa=baseline.GetAppliedAssemblyAtStation(s);
     var points=aa.Points.Cast<CalculatedPoint>().Select(pt=>new{
      soe=new[]{pt.StationOffsetElevationToBaseline.X,pt.StationOffsetElevationToBaseline.Y,pt.StationOffsetElevationToBaseline.Z},
      xyz=new[]{pt.XYZ.X,pt.XYZ.Y,pt.XYZ.Z},codigos=pt.CorridorCodes.Cast<string>().ToArray()}).ToArray();
     var daylight=points.Where(pt=>pt.codigos.Contains("Daylight")).ToArray();
     if(!daylight.Any(pt=>pt.soe[1]<0)||!daylight.Any(pt=>pt.soe[1]>0))throw new InvalidOperationException("Estacion "+s+" sin punto Daylight a ambos lados");
     foreach(var pt in daylight)
      maxDaylightDelta=Math.Max(maxDaylightDelta,Math.Abs(pt.xyz[2]-target.FindElevationAtXY(pt.xyz[0],pt.xyz[1])));
     return new{estacion=s,puntos=points};
    }).ToArray();
    if(maxDaylightDelta>1e-6)throw new InvalidOperationException("Daylight no alcanza la superficie objetivo; delta max "+maxDaylightDelta);
    if(applied.Any(row=>row.puntos.Length<4||row.puntos.Any(pt=>pt.xyz.Any(x=>!double.IsFinite(x)))))throw new InvalidOperationException("Geometria de corredor vacia o no finita");
    var surface=c.CorridorSurfaces.Add(name+"_Top");surface.AddLinkCode("Top",true);surface.Boundaries.Add(name+"_Boundary","Daylight");surface.IsBuild=true;
    c.Rebuild();
    if(c.IsOutOfDate)throw new InvalidOperationException("Corredor sin reconstruir");
    bool sim=p["simular"]?.GetValue<bool>()??false;
    var result=new{handle=sim?null:HandleOf(id),nombre=name,alineamiento=HandleOf(aid),perfil=HandleOf(pid),ensamblaje=HandleOf(sid),
     superficie_objetivo=HandleOf(tid),targets=assigned,inicio=start,fin=end,frecuencia=frequency,superficie=HandleOf(surface.SurfaceId),
     codigos_enlace=codes,delta_daylight_max=maxDaylightDelta,estaciones=stations,aplicados=applied,simulacion=sim};
    if(sim)tr.Abort();else tr.Commit();return result;
   }
  }
 }
}
