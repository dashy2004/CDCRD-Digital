using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using AcadApp = Autodesk.AutoCAD.ApplicationServices.Application;
using CogoPoint = Autodesk.Civil.DatabaseServices.CogoPoint;
using TinSurface = Autodesk.Civil.DatabaseServices.TinSurface;

namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        // Prepare a fresh graph for this call; the DI StratumService has no graph.
        // Existing surfaces are never erased implicitly, including other GM strata.
        private static object GmConstruirSuperficies(JsonObject p, string method)
        {
            ExigirEscritura(method,p);
            bool bottom=p["superficie_fondo"]?.GetValue<bool>() ?? false;
            bool simulate=p["simular"]?.GetValue<bool>() ?? false;
            var result=new Dictionary<string,object> {
                {"aviso","Datos geotecnicos hipoteticos/preliminares"}, {"completo",false},
                {"simulacion",simulate}, {"superficies",Array.Empty<string>()}, {"superficies_creadas",0}
            };
            var container=ContenedorGm();
            using (AmbitoGm(container))
            {
                const string cad="Aecc.Gtm.CADServices";
                var docService=ResolverGm(container,TipoGm(cad,cad+".AcadDocumentService"));
                var land=ResolverGm(container,TipoGm(cad,cad+".LandServices"));
                var map=ResolverGm(container,TipoGm(cad,cad+".MapServices"));
                var repo=ResolverGm(container,TipoGm("Aecc.Gtm.DomainPersistence","Aecc.Gtm.DomainPersistence.AGMBoringRepository"));
                var settingsRepo=ResolverGm(container,TipoGm(cad,cad+".ApplicationSettingsRepository"));
                var appConfig=ResolverGm(container,TipoGm("Aecc.Gtm.Domain","Aecc.Gtm.Domain.IApplicationConfig"));
                var doc=AcadApp.DocumentManager.MdiActiveDocument;
                using(doc.LockDocument())
                using(var transaction=(IDisposable)TransaccionGm(docService))
                {
                    Exception operationFailure=null;
                    GmAtomicOperation.Execute(() => {
                        var temporaryFiles=new List<string>();
                        try
                        {
                            var unitZone=PropGm(PropGm(PropGm(CivilDoc(),"Settings"),"DrawingSettings"),"UnitZoneSettings");
                            if (Convert.ToInt32(AcadApp.GetSystemVariable("INSUNITS")) != 6 ||
                                Convert.ToString(PropGm(unitZone,"DrawingUnits")) != "Meters")
                                throw new ArgumentException("Superficies GM requiere INSUNITS y unidades Civil en metros; no convierte coordenadas.");
                            var settings=InvocarGm(settingsRepo,"GetApplicationSettings");
                            if(settings==null) throw new ArgumentException("No hay proyecto GM guardado en el dibujo.");
                            string project=Convert.ToString(PropGm(settings,"ProjectId"));
                            if(string.IsNullOrWhiteSpace(project)) throw new ArgumentException("ProjectId GM vacio.");
                            string field=GmProfileContract.Field(Txt(p,"campo_geologia"),
                                Convert.ToString(PropGm(settings,"StratumSurfacesGeologyField")));
                            result["campo_geologia"]=field;
                            var all=(IList)InvocarGm(repo,"GetBoreholes",project);
                            var manager=PropGm(land,"PointGroupManager");
                            var group=InvocarGm(manager,"GetPointGroup","GM - Filtered Boreholes");
                            if(group==null) throw new ArgumentException("Falta el grupo GM - Filtered Boreholes.");
                            var lookup=(IDictionary)InvocarGm(manager,"GetCogoPointByPointNumberLookup",group);
                            var locations=new List<(string Id,double X,double Y)>();
                            foreach(CogoPoint point in lookup.Values)
                                locations.Add((point.RawDescription,point.Easting,point.Northing));
                            GmSurfaceContract.RequireLocations(locations);
                            var selected=new List<object>();
                            var bottomVertices=new Point3dCollection();
                            var counts=new Dictionary<string,int>();
                            foreach(var point in locations)
                            {
                                var matches=all.Cast<object>().Where(b => string.Equals(
                                    Convert.ToString(PropGm(b,"BoringId")),point.Id,StringComparison.OrdinalIgnoreCase)).ToArray();
                                if(matches.Length!=1) throw new ArgumentException("Sondeo del grupo sin correspondencia unica en GM: "+point.Id);
                                selected.Add(matches[0]);
                                if(bottom)
                                {
                                    double elevation=Convert.ToDouble(PropGm(PropGm(matches[0],"Location"),"Elevation"));
                                    double depth=Convert.ToDouble(PropGm(matches[0],"TotalDepth"));
                                    bottomVertices.Add(new Point3d(point.X,point.Y,GmSurfaceContract.BottomElevation(elevation,depth)));
                                }
                                counts[point.Id]=((IList)InvocarGm(matches[0],"GetStrataByFieldName",field,false)).Count;
                            }
                            GmProfileContract.RequireStrata(counts);
                            result["sondeos"]=selected.Count; result["estratos_por_sondeo"]=counts;
                            // Same existing, non-interactive hatch assignment used by the profile.
                            var hatch=Activator.CreateInstance(TipoGm(cad,cad+".GeologyHatchStyleConfiguration"),
                                new object[]{docService,PropGm(appConfig,"GeologyHatchStyleConfigurationPath")});
                            InvocarGm(hatch,"LoadFromFile",true);
                            if(((IList)PropGm(hatch,"Errors")).Count>0)
                                throw new ArgumentException("Estilos GM invalidos: "+InvocarGm(hatch,"GetErrorMessage"));
                            foreach(var borehole in selected)
                            {
                                int matched=Convert.ToInt32(InvocarGm(borehole,"AssignHatchStylesToStrata",field,PropGm(hatch,"HatchStyleLookup"),PropGm(hatch,"DefaultHatchStyle")));
                                if(matched==0 || ((IList)InvocarGm(borehole,"GetStrataByFieldName",field,false)).Cast<object>().Any(s => PropGm(s,"HatchStyle")==null))
                                    throw new ArgumentException("Faltan estilos de estratos para "+PropGm(borehole,"BoringId"));
                            }
                            // GraphService replaces its scratch objects. Refuse pre-existing ones.
                            const string scratchSurface="GM - Subsurface Triangles Graph";
                            const string scratchGroup="GM - Subsurface Triangle Points";
                            if(InvocarGm(land,"GetSurface",scratchSurface)!=null || InvocarGm(manager,"GetPointGroup",scratchGroup)!=null)
                                throw new ArgumentException("Hay datos temporales GM anteriores; inventariarlos antes de limpiarlos.");
                            var tr=(Transaction)PropGm(transaction,"Transaction");
                            var layers=(LayerTable)tr.GetObject(doc.Database.LayerTableId,OpenMode.ForRead);
                            bool hadScratchLayer=layers.Has(scratchGroup);
                            var graph=Activator.CreateInstance(TipoGm(cad,cad+".StratumServices.GraphServices.GraphService"),
                                new object[]{land,CastLista(selected,all)});
                            // GM drops its zero-thickness bottom stratum. Build the registered
                            // borehole termination TIN directly, without inventing a thickness.
                            InvocarGm(graph,"BuildSubstrataGraphs",field,false,false);
                            var graphs=(IList)PropGm(graph,"StratumGraphs");
                            string[] names=GmSurfaceContract.SurfaceNames(graphs.Cast<object>().Select(g => Convert.ToString(PropGm(g,"Name"))));
                            string[] strataNames=names;
                            if(bottom)
                            {
                                if(names.Contains(GmSurfaceContract.BottomName,StringComparer.OrdinalIgnoreCase))
                                    throw new ArgumentException("Un estrato ya usa el nombre reservado para fondo de sondeos.");
                                names=names.Concat(new[]{GmSurfaceContract.BottomName}).ToArray();
                                result["origen_fondo"]="TIN nativo: XY del grupo filtrado, Location.Elevation - TotalDepth; modelo vertical";
                                result["limite_fondo"]="envolvente convexa de los sondeos; no interpreta una frontera geologica";
                            }
                            result["superficies_previstas"]=names;
                            GmSurfaceContract.RequireBottom(bottom,names);
                            var existing=names.Where(n => InvocarGm(land,"GetSurface",n)!=null).ToArray();
                            result["superficies_existentes"]=existing;
                            if(simulate) return false;
                            if(existing.Length>0) throw new ArgumentException("Se conservan superficies existentes; nombres en conflicto: "+string.Join(", ",existing));
                            string[] files=strataNames.Select(n => Path.Combine(Path.GetTempPath(),n+" - Breaklines.flt")).ToArray();
                            if(files.Any(f => File.Exists(f) || Directory.Exists(f)))
                                throw new IOException("Existe un archivo temporal GM previo; no se sobrescribira.");
                            temporaryFiles.AddRange(files);
                            var service=Activator.CreateInstance(TipoGm(cad,cad+".StratumServices.StratumService"),
                                new object[]{docService,land,graph,map});
                            var built=(IList)InvocarGm(service,"BuildStratumSurfaces",false);
                            var surfaces=built.Cast<TinSurface>().ToList();
                            if(!GmSurfaceContract.Complete(strataNames,surfaces.Select(s=>s.Name)))
                                throw new InvalidOperationException("GM devolvio estratos incompletos.");
                            if(bottom)
                            {
                                var id=TinSurface.Create(GmSurfaceContract.BottomName,surfaces[0].StyleId);
                                var termination=(TinSurface)tr.GetObject(id,OpenMode.ForWrite);
                                termination.Description="Fondo de sondeos: cota registrada menos profundidad total; interpolacion TIN, modelo vertical.";
                                termination.AddVertices(bottomVertices);
                                termination.Rebuild();
                                surfaces.Add(termination);
                            }
                            if(!GmSurfaceContract.Complete(names,surfaces.Select(s => s.Name)) || surfaces.Any(s => s.GetTriangles(false).Count==0))
                                throw new InvalidOperationException("GM devolvio superficies incompletas o sin triangulos.");
                            var folder=InvocarGm(land,"GetOrCreateGeotechModelerFullStratumSurfaceFolder",true);
                            foreach(var surface in surfaces) InvocarGm(folder,"AddEntity",surface.ObjectId);
                            InvocarGm(graph,"EraseTemporarySurfaceData");
                            if(!hadScratchLayer && layers.Has(scratchGroup))
                                tr.GetObject(layers[scratchGroup],OpenMode.ForWrite).Erase();
                            result["superficies"]=surfaces.Select(s => s.Name).ToArray();
                            result["superficies_creadas"]=surfaces.Count;
                            result["detalles"]=surfaces.Select(s => new {nombre=s.Name,handle=s.Handle.ToString(),triangulos=s.GetTriangles(false).Count}).ToArray();
                            return true;
                        }
                        catch(Exception ex)
                        {
                            operationFailure=ex;result["error"]=ExcepcionDetallada(ex);return false;
                        }
                        finally
                        {
                            // Only paths proven absent before this call can be removed.
                            foreach(string file in temporaryFiles) if(File.Exists(file)) File.Delete(file);
                        }
                    }, () => {
                        InvocarGm(transaction,"CommitTransaction");
                        result["completo"]=true; result["transaccion"]="confirmada";result["cambios_revertidos"]=false;
                    }, () => {
                        try { InvocarGm(transaction,"AbortTransaction"); }
                        catch(Exception abortFailure)
                        {
                            if(operationFailure!=null) throw new AggregateException(operationFailure,abortFailure);
                            throw;
                        }
                        result["transaccion"]="revertida";result["cambios_revertidos"]=true;
                        result["superficies"]=Array.Empty<string>();result["superficies_creadas"]=0;
                    });
                }
            }
            return result;
        }
    }
}
