using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil;
using Autodesk.Civil.DatabaseServices;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivilApp = Autodesk.Civil.ApplicationServices.CivilApplication;
using CivAssembly = Autodesk.Civil.DatabaseServices.Assembly;

namespace Cdcrd.Corredores;

internal static partial class MultiService
{
    internal static Action<string> QaCheckpoint = null;
    private const string RecordName = "CDCRD_MULTI_V1";
    private sealed record RegionPlan(RegionSpec Spec, ObjectId Assembly, ObjectId Target);
    private sealed record BasePlan(BaselineSpec Spec, ObjectId Alignment, ObjectId Profile, RegionPlan[] Regions);
    private static string Text(JsonObject p,string k) => MultiContract.Text(p,k);
    private static string H(ObjectId id) => id.IsNull ? null : id.Handle.ToString();
    private static double[] Pt(Point3d p) => new[]{p.X,p.Y,p.Z};
    private static ObjectId Resolve(Transaction tr,IEnumerable<ObjectId> ids,string key)
    {
        var matches=ids.Where(id=>H(id).Equals(key,StringComparison.OrdinalIgnoreCase) ||
            string.Equals(((Autodesk.Civil.DatabaseServices.Entity)tr.GetObject(id,OpenMode.ForRead)).Name,key,StringComparison.OrdinalIgnoreCase)).ToArray();
        if(matches.Length!=1)throw new ArgumentException("Referencia inexistente o ambigua: "+key);
        return matches[0];
    }
    private static ObjectId Layer(Transaction tr,Database db,string name)
    {
        SymbolUtilityServices.ValidateSymbolName(name,false);
        var table=(LayerTable)tr.GetObject(db.LayerTableId,OpenMode.ForRead);
        if(table.Has(name))return table[name];
        table.UpgradeOpen();var record=new LayerTableRecord{Name=name};var id=table.Add(record);tr.AddNewlyCreatedDBObject(record,true);return id;
    }
    private static BasePlan[] ResolvePlans(Transaction tr,BaselineSpec[] specs)
    {
        var civil=CivilApp.ActiveDocument;
        var seen=new HashSet<ObjectId>();
        return specs.Select(b=>{
            var aid=Resolve(tr,civil.GetAlignmentIds().Cast<ObjectId>(),b.Alignment);
            var a=(Alignment)tr.GetObject(aid,OpenMode.ForRead);
            if(!seen.Add(aid) || a.IsReferenceObject || a.StationEquations.Count!=0)throw new ArgumentException("Alineamiento repetido, de referencia o con ecuaciones de estacion");
            var pid=Resolve(tr,a.GetProfileIds().Cast<ObjectId>(),b.Profile);
            var p=(Profile)tr.GetObject(pid,OpenMode.ForRead);
            if(p.IsReferenceObject)throw new ArgumentException("Perfil de referencia no soportado");
            var regions=b.Regions.Select(r=>{
                if(r.Start<Math.Max(a.StartingStation,p.StartingStation) || r.End>Math.Min(a.EndingStation,p.EndingStation))
                    throw new ArgumentException("Region fuera del dominio de alineamiento/perfil");
                var sid=Resolve(tr,civil.AssemblyCollection,r.Assembly);
                var assembly=(CivAssembly)tr.GetObject(sid,OpenMode.ForRead);
                if(assembly.IsReferenceObject || assembly.Groups.Count==0)throw new ArgumentException("Ensamblaje vacio o de referencia");
                var tid=r.Target==null?ObjectId.Null:Resolve(tr,civil.GetSurfaceIds().Cast<ObjectId>(),r.Target);
                if(!tid.IsNull && (tr.GetObject(tid,OpenMode.ForRead) is not TinSurface tin || tin.IsReferenceObject))
                    throw new ArgumentException("Target debe ser TIN local");
                return new RegionPlan(r,sid,tid);
            }).ToArray();
            return new BasePlan(b,aid,pid,regions);
        }).ToArray();
    }
    internal static object Execute(JsonObject p,out bool committed)
    {
        committed=false;
        var doc=App.DocumentManager.MdiActiveDocument ?? throw new InvalidOperationException("Sin documento");
        if(!DateTimeOffset.TryParse(Text(p,"vence_utc"),out var expires) || expires<DateTimeOffset.UtcNow || expires>DateTimeOffset.UtcNow.AddMinutes(5))
            throw new ArgumentException("Solicitud vencida o plazo invalido");
        if(p["pid"]?.GetValue<int>()!=Environment.ProcessId || !Path.IsPathFullyQualified(Text(p,"dibujo")) ||
            !string.Equals(Path.GetFullPath(doc.Name),Path.GetFullPath(Text(p,"dibujo")),StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Documento o PID distinto al esperado");
        var civil=CivilApp.ActiveDocument;
        if(Convert.ToInt32(App.GetSystemVariable("INSUNITS"))!=6 || civil.Settings.DrawingSettings.UnitZoneSettings.DrawingUnits.ToString()!="Meters")
            throw new ArgumentException("Se requieren unidades Civil y AutoCAD en metros");
        string action=Text(p,"accion");
        if(!new[]{"crear","leer","secciones"}.Contains(action))throw new ArgumentException("Accion desconocida");
        bool write=action!="leer",sim=p["simular"]?.GetValue<bool>()??true;
        if(write && (Environment.GetEnvironmentVariable("CDCRD_C3D_SOLO_LECTURA")=="1" || Environment.GetEnvironmentVariable("CDCRD_C3D_PERMITIR_COMANDOS")!="1"))
            throw new InvalidOperationException("Escritura/comandos deshabilitados");
        using(doc.LockDocument())using(var tr=doc.Database.TransactionManager.StartTransaction())
        {
            object result;
            if(action=="secciones")result=Sections(p,tr);
            else
            {
                Corridor c;JsonArray definitions;
                if(action=="crear")
                {
                    definitions=p["baselines"] as JsonArray;
                    var plans=ResolvePlans(tr,MultiContract.Parse(definitions));
                    string name=Text(p,"nombre");
                    if(civil.CorridorCollection.Any(id=>((Corridor)tr.GetObject(id,OpenMode.ForRead)).Name.Equals(name,StringComparison.OrdinalIgnoreCase)) ||
                        civil.GetSurfaceIds().Cast<ObjectId>().Any(id=>((Autodesk.Civil.DatabaseServices.Surface)tr.GetObject(id,OpenMode.ForRead)).Name.Equals(name+"_Top",StringComparison.OrdinalIgnoreCase)))
                        throw new ArgumentException("Ya existe el corredor o su superficie Top");
                    var layer=Layer(tr,doc.Database,Text(p,"capa"));
                    var cid=civil.CorridorCollection.Add(name);c=(Corridor)tr.GetObject(cid,OpenMode.ForWrite);
                    c.LayerId=layer;c.RebuildAutomatic=false;
                    foreach(var b in plans)
                    {
                        var baseline=c.Baselines.Add(b.Spec.Name,b.Alignment,b.Profile);
                        QaCheckpoint?.Invoke("baseline-added");
                        foreach(var rp in b.Regions)
                        {
                            var r=rp.Spec;
                            var region=baseline.BaselineRegions.Add(r.Name,rp.Assembly,r.Start,r.End);
                            var settings=region.AppliedAssemblySetting;
                            settings.CorridorAlongCurvesOption=CorridorAlongCurveOption.CurveAtIncrement;
                            settings.FrequencyAlongTangents=r.Frequency;settings.FrequencyAlongCurves=r.Frequency;
                            settings.FrequencyAlongSpirals=r.Frequency;settings.FrequencyAlongProfileCurves=r.Frequency;
                            settings.AppliedAtHorizontalGeometryPoints=true;settings.AppliedAtProfileGeometryPoints=true;settings.AppliedAtProfileHighLowPoints=true;
                            settings.AppliedAtSuperelevationCriticalPoints=true;settings.AppliedAtOffsetTargetGeometryPoints=false;settings.AppliedAdjacentToOffsetTargetStartEnd=false;
                            foreach(double station in r.Extra)region.AddStation(station,"Explicit region sample");
                            var targets=region.GetTargets();int surfaceTargets=0;
                            foreach(SubassemblyTargetInfo target in targets)
                            {
                                if(target.TargetType.ToString()!="Surface")
                                {if(target.TargetIds.Count!=0)throw new ArgumentException("Targets de ancho/cota no soportados");continue;}
                                surfaceTargets++;
                                if(rp.Target.IsNull)throw new ArgumentException("Region requiere superficie_objetivo explicita");
                                var ids=new ObjectIdCollection();ids.Add(rp.Target);target.TargetIds=ids;
                            }
                            if(surfaceTargets==0 && !rp.Target.IsNull)throw new ArgumentException("Ensamblaje no expone targets de superficie");
                            region.SetTargets(targets);
                            QaCheckpoint?.Invoke("region-targets-assigned");
                        }
                    }
                    c.Rebuild();QaCheckpoint?.Invoke("corridor-rebuilt");
                    if(!c.GetLinkCodes().Contains("Top"))throw new InvalidOperationException("Corredor sin codigo Top");
                    var surface=c.CorridorSurfaces.Add(name+"_Top");surface.AddLinkCode("Top",true);
                    surface.Boundaries.AddCorridorExtentsBoundary(name+"_Extents");surface.IsBuild=true;
                    c.Rebuild();
                    ((TinSurface)tr.GetObject(surface.SurfaceId,OpenMode.ForWrite)).Rebuild();
                    QaCheckpoint?.Invoke("surface-rebuilt");
                    if(c.IsOutOfDate)throw new InvalidOperationException("Corredor requiere reconstruccion");
                    c.CreateExtensionDictionary();var dict=(DBDictionary)tr.GetObject(c.ExtensionDictionary,OpenMode.ForWrite);
                    string json=definitions.ToJsonString();var record=new Xrecord();
                    record.Data=new ResultBuffer(Enumerable.Range(0,(json.Length+239)/240).Select(i=>new TypedValue((int)DxfCode.Text,json.Substring(i*240,Math.Min(240,json.Length-i*240)))).ToArray());
                    dict.SetAt(RecordName,record);tr.AddNewlyCreatedDBObject(record,true);
                }
                else
                {
                    c=(Corridor)tr.GetObject(Resolve(tr,civil.CorridorCollection,Text(p,"corredor")),OpenMode.ForRead);
                    definitions=Definitions(c,tr);
                }
                result=Inspect(c,tr,definitions,action=="crear" && sim);
            }
            if(write && !sim){tr.Commit();committed=true;}else tr.Abort();
            return result;
        }
    }
    private static JsonArray Definitions(Corridor c,Transaction tr)
    {
        if(c.IsReferenceObject || c.ExtensionDictionary.IsNull)throw new ArgumentException("Requiere corredor local creado por este modulo");
        var dict=(DBDictionary)tr.GetObject(c.ExtensionDictionary,OpenMode.ForRead);
        if(!dict.Contains(RecordName))throw new ArgumentException("Falta contrato CDCRD_MULTI_V1");
        var record=(Xrecord)tr.GetObject(dict.GetAt(RecordName),OpenMode.ForRead);
        return JsonNode.Parse(string.Concat(record.Data.AsArray().Select(v=>v.Value as string))) as JsonArray;
    }
    private static object Inspect(Corridor c,Transaction tr,JsonArray definitions,bool simulation)
    {
        var plans=ResolvePlans(tr,MultiContract.Parse(definitions));
        if(c.Baselines.Count!=plans.Length || c.CorridorSurfaces.Count!=1)throw new InvalidOperationException("Topologia de corredor distinta del contrato");
        double xyError=0,zError=0,daylightError=0;int total=0;
        var bases=plans.Select(bp=>{
            var b=c.Baselines[bp.Spec.Name];
            if(b.AlignmentId!=bp.Alignment || b.ProfileId!=bp.Profile || b.BaselineRegions.Count!=bp.Regions.Length)
                throw new InvalidOperationException("Baseline distinta del contrato");
            var a=(Alignment)tr.GetObject(bp.Alignment,OpenMode.ForRead);var profile=(Profile)tr.GetObject(bp.Profile,OpenMode.ForRead);
            var regions=bp.Regions.Select(rp=>{
                var r=b.BaselineRegions[rp.Spec.Name];var setting=r.AppliedAssemblySetting;
                if(r.AssemblyId!=rp.Assembly || Math.Abs(r.StartStation-rp.Spec.Start)>1e-6 || Math.Abs(r.EndStation-rp.Spec.End)>1e-6 ||
                    new[]{setting.FrequencyAlongTangents,setting.FrequencyAlongCurves,setting.FrequencyAlongSpirals,setting.FrequencyAlongProfileCurves}.Any(f=>Math.Abs(f-rp.Spec.Frequency)>1e-9))
                    throw new InvalidOperationException("Region distinta del contrato");
                var targets=r.GetTargets().Cast<SubassemblyTargetInfo>().ToArray();
                if(targets.Any(t=>t.TargetType.ToString()=="Surface" ? t.TargetIds.Count!=1 || t.TargetIds[0]!=rp.Target : t.TargetIds.Count!=0))
                    throw new InvalidOperationException("Targets distintos del contrato");
                var stations=r.AppliedAssemblies.Stations().OrderBy(s=>s).ToArray();total+=stations.Length;
                if(stations.Length<2 || total>20000 || Math.Abs(stations.First()-r.StartStation)>1e-6 || Math.Abs(stations.Last()-r.EndStation)>1e-6 ||
                    rp.Spec.Extra.Any(s=>!stations.Any(t=>Math.Abs(t-s)<1e-6)))throw new InvalidOperationException("Faltan estaciones aplicadas o se supera presupuesto");
                var applied=stations.Select(s=>{
                    // Civil may alias the preceding assembly at a shared region boundary.
                    // Preserve and label the native result; never attribute it to the new template.
                    var aa=r.AppliedAssemblies.GetItemAt(s);
                    bool shared=bp.Regions.Count(other=>Math.Abs(other.Spec.Start-s)<1e-6||Math.Abs(other.Spec.End-s)<1e-6)>1;
                    var geometryRegion=rp;
                    if(aa.AssemblyId!=r.AssemblyId)
                    {
                        var owners=bp.Regions.Where(other=>other.Assembly==aa.AssemblyId && (Math.Abs(other.Spec.Start-s)<1e-6||Math.Abs(other.Spec.End-s)<1e-6)).ToArray();
                        if(!shared || owners.Length!=1)throw new InvalidOperationException("Ensamblaje aplicado ajeno a la region");
                        geometryRegion=owners[0];
                    }
                    var points=aa.Points.Cast<CalculatedPoint>().Select(pt=>new{soe=Pt(pt.StationOffsetElevationToBaseline),xyz=Pt(pt.XYZ),codes=pt.CorridorCodes.Cast<string>().OrderBy(x=>x).ToArray()}).ToArray();
                    if(points.Length<4 || points.Any(pt=>pt.xyz.Concat(pt.soe).Any(x=>!double.IsFinite(x))))throw new InvalidOperationException("Geometria vacia o no finita");
                    foreach(var point in points)
                    {
                        double x=0,y=0;a.PointLocation(s,point.soe[1],ref x,ref y);
                        xyError=Math.Max(xyError,Math.Max(Math.Abs(x-point.xyz[0]),Math.Abs(y-point.xyz[1])));
                        zError=Math.Max(zError,Math.Abs(profile.ElevationAt(s)+point.soe[2]-point.xyz[2]));
                    }
                    if(!geometryRegion.Target.IsNull)
                    {
                        var daylight=points.Where(pt=>pt.codes.Contains("Daylight")).ToArray();
                        if(!daylight.Any(pt=>pt.soe[1]<0) || !daylight.Any(pt=>pt.soe[1]>0))throw new InvalidOperationException("Daylight incompleto");
                        var target=(TinSurface)tr.GetObject(geometryRegion.Target,OpenMode.ForRead);
                        foreach(var point in daylight)daylightError=Math.Max(daylightError,Math.Abs(target.FindElevationAtXY(point.xyz[0],point.xyz[1])-point.xyz[2]));
                    }
                    if(points.Any(pt=>Math.Abs(pt.soe[0]-s)>1e-6))throw new InvalidOperationException("API devolvio otra estacion");
                    return new{station=s,assembly=H(aa.AssemblyId),boundary_shared=shared,geometry_region=geometryRegion.Spec.Name,points};
                }).ToArray();
                return new{name=r.Name,start=r.StartStation,end=r.EndStation,assembly=H(r.AssemblyId),frequency=setting.FrequencyAlongTangents,target=H(rp.Target),stations,applied};
            }).ToArray();
            return new{name=b.Name,alignment=H(b.AlignmentId),profile=H(b.ProfileId),regions};
        }).ToArray();
        if(xyError>1e-5 || zError>1e-6 || daylightError>1e-6)throw new InvalidOperationException("Geometria nativa no coincide con eje/rasante/target");
        var surface=c.CorridorSurfaces[0];var tin=(TinSurface)tr.GetObject(surface.SurfaceId,OpenMode.ForRead);
        var boundaries=surface.Boundaries.Cast<CorridorSurfaceBoundary>().ToArray();
        if(boundaries.Length!=1 || !boundaries[0].IsCorridorExtents)throw new InvalidOperationException("Falta limite por extensiones de corredor");
        var loops=boundaries[0].GetExtentsBoundaries().Select(loop=>loop.Select(Pt).ToArray()).ToArray();
        var triangles=tin.GetTriangles(false).Cast<TinSurfaceTriangle>().Select(t=>new[]{Pt(t.Vertex1.Location),Pt(t.Vertex2.Location),Pt(t.Vertex3.Location)}).ToArray();
        if(triangles.Length==0 || loops.Length==0)throw new InvalidOperationException("Superficie Top vacia");
        return new{handle=simulation?null:H(c.ObjectId),name=c.Name,baselines=bases,surface=H(surface.SurfaceId),surface_boundary="CorridorExtents",boundary_loops=loops,triangles,
            max_xy_error=xyError,max_z_error=zError,max_daylight_error=daylightError,out_of_date=c.IsOutOfDate,simulation,units="m"};
    }
}
