using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.DatabaseServices;
using AcadApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivAlignment = Autodesk.Civil.DatabaseServices.Alignment;
using CivProfile = Autodesk.Civil.DatabaseServices.Profile;

namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        private static void SiteUnits()
        {
            if (Convert.ToInt32(AcadApp.GetSystemVariable("INSUNITS"))!=6 ||
                Civil().Settings.DrawingSettings.UnitZoneSettings.DrawingUnits.ToString()!="Meters")
                throw new BridgeException(Rpc.ErrParams,"Requiere INSUNITS y DrawingUnits Civil en metros. No convierte coordenadas.");
        }
        private static string SiteName(JsonObject p,string field)
        {
            string name=Txt(p,field);
            if(string.IsNullOrWhiteSpace(name) || name.Length>200 || name.Any(char.IsControl))
                throw new BridgeException(Rpc.ErrParams,"Nombre invalido: "+field);
            return name;
        }
        private static ObjectId SiteStyle(Transaction tr,string family,string name)
            => string.IsNullOrWhiteSpace(name)?PrimerEstilo(tr,family):EstiloPorNombre(tr,family,name,true);
        private static Polyline SitePolyline(Transaction tr,Database db,JsonObject p,bool closed,bool alignmentCurves=false)
        {
            var id=IdFromHandle(db,Txt(p,"polilinea"));
            var pl=tr.GetObject(id,OpenMode.ForRead) as Polyline;
            if(pl==null || pl.OwnerId!=SymbolUtilityServices.GetBlockModelSpaceId(db))
                throw new BridgeException(Rpc.ErrParams,"polilinea debe ser handle de LWPOLYLINE en ModelSpace.");
            if(pl.Closed!=closed || !pl.Normal.IsEqualTo(Vector3d.ZAxis,new Tolerance(1e-10,1e-10)))
                throw new BridgeException(Rpc.ErrParams,closed?"Se requiere polilinea cerrada en plano XY.":"Se requiere polilinea abierta en plano XY.");
            SiteDesignContract.Finite(pl.Elevation,"elevacion de polilinea");
            if(alignmentCurves && Enumerable.Range(0,pl.NumberOfVertices).Any(i=>pl.GetBulgeAt(i)!=0))
            {ValidateAlignmentPolyline(pl);return pl;}
            var points=new List<(double X,double Y)>();
            for(int i=0;i<pl.NumberOfVertices;i++)
            {
                if(pl.GetBulgeAt(i)!=0) throw new BridgeException(Rpc.ErrParams,"Esta version acepta segmentos rectos; arcos no implementados.");
                var point=pl.GetPoint2dAt(i);points.Add((point.X,point.Y));
            }
            SiteDesignContract.Polyline(points,closed);
            return pl;
        }
        private static object CrearAlineamientoPolilinea(JsonObject p,string method)
        {
            ExigirEscritura(method,p);SiteUnits();string name=SiteName(p,"nombre");
            var doc=Doc();var db=doc.Database;var civil=Civil();
            using(doc.LockDocument()) using(var tr=db.TransactionManager.StartTransaction())
            {
                foreach(ObjectId id in civil.GetAlignmentIds())
                    if(string.Equals(((CivAlignment)tr.GetObject(id,OpenMode.ForRead)).Name,name,StringComparison.OrdinalIgnoreCase))
                        throw new BridgeException(Rpc.ErrParams,"Ya existe el alineamiento; no se reemplaza ni se da por equivalente.");
                var pl=SitePolyline(tr,db,p,false,true);
                double station=Num(p,"estacion_inicial")??0;SiteDesignContract.Finite(station,"estacion inicial");
                var style=SiteStyle(tr,"AlignmentStyles",Txt(p,"estilo"));
                var labels=SiteStyle(tr,"AlignmentLabelSetStyles",Txt(p,"etiquetas"));
                var layer=CapaId(tr,db,Txt(p,"capa"),true);
                var idNew=CivAlignment.Create(civil,new PolylineOptions {PlineId=pl.ObjectId,EraseExistingEntities=false,AddCurvesBetweenTangents=false},name,ObjectId.Null,layer,style,labels);
                var alignment=(CivAlignment)tr.GetObject(idNew,OpenMode.ForWrite);
                alignment.ReferencePointStation=station;
                CurveQaCheckpoint?.Invoke("alignment-created");
                var geometry=VerifyAlignmentCurves(alignment,pl);
                if(Math.Abs(alignment.Length-pl.Length)>Math.Max(1e-6,pl.Length*1e-9)) throw new InvalidOperationException("Longitud del eje no coincide con polilinea.");
                bool simulate=p["simular"]?.GetValue<bool>()??false;
                var result=new {handle=simulate?null:HandleOf(idNew),nombre=alignment.Name,longitud_m=alignment.Length,
                    est_inicio=alignment.StartingStation,est_fin=alignment.EndingStation,polilinea=HandleOf(pl.ObjectId),
                    fuente_conservada=true,sin_sitio=true,geometria=geometry,simulacion=simulate,estilo=NombreDe(tr.GetObject(style,OpenMode.ForRead))};
                if(simulate)tr.Abort();else tr.Commit();return result;
            }
        }
        private static object CrearPerfilPvi(JsonObject p,string method)
        {
            ExigirEscritura(method,p);SiteUnits();string name=SiteName(p,"nombre");
            var doc=Doc();var db=doc.Database;var civil=Civil();
            using(doc.LockDocument()) using(var tr=db.TransactionManager.StartTransaction())
            {
                var aid=ResolverId(tr,db,civil.GetAlignmentIds(),Txt(p,"alineamiento"),"el alineamiento");
                var alignment=(CivAlignment)tr.GetObject(aid,OpenMode.ForRead);
                if(alignment.StationEquations.Count!=0) throw new BridgeException(Rpc.ErrParams,"Ejes con ecuaciones de estacion no soportados en esta version.");
                if(!PerfilExistente(tr,alignment,name).IsNull) throw new BridgeException(Rpc.ErrParams,"Ya existe el perfil; no se reemplaza.");
                var array=p["pvis"] as JsonArray;
                if(array==null)throw new BridgeException(Rpc.ErrParams,"pvis debe ser [[estacion,elevacion],...].");
                var pvis=new List<(double Station,double Elevation)>();
                foreach(var row in array)
                {
                    if(row is not JsonArray pair || pair.Count!=2)throw new BridgeException(Rpc.ErrParams,"Cada PVI requiere [estacion,elevacion].");
                    pvis.Add((pair[0].GetValue<double>(),pair[1].GetValue<double>()));
                }
                SiteDesignContract.Pvis(pvis,alignment.StartingStation,alignment.EndingStation);
                var curves=ReadVerticalCurves(p,pvis);
                var style=SiteStyle(tr,"ProfileStyles",Txt(p,"estilo"));
                var labels=SiteStyle(tr,"ProfileLabelSetStyles",Txt(p,"etiquetas"));
                var id=CivProfile.CreateByLayout(name,aid,CapaId(tr,db,Txt(p,"capa"),true),style,labels);
                var profile=(CivProfile)tr.GetObject(id,OpenMode.ForWrite);
                foreach(var point in pvis)profile.PVIs.AddPVI(point.Station,point.Elevation);
                foreach(var curve in curves)
                {
                    var point=pvis[curve.Pvi];
                    profile.Entities.AddFreeSymmetricParabolaByPVIAndCurveLength(profile.PVIs.GetPVIAt(point.Station,point.Elevation),curve.Length);
                    CurveQaCheckpoint?.Invoke("profile-curve-added");
                }
                var verification=VerifyVerticalCurves(profile,pvis,curves);
                var actual=profile.PVIs.Cast<ProfilePVI>().Select(v=>new[]{v.RawStation,v.Elevation}).ToArray();
                if(actual.Length!=pvis.Count || actual.Where((v,i)=>Math.Abs(v[0]-pvis[i].Station)>1e-7 || Math.Abs(v[1]-pvis[i].Elevation)>1e-7).Any())
                    throw new InvalidOperationException("La relectura de PVIs no coincide.");
                bool simulate=p["simular"]?.GetValue<bool>()??false;
                var result=new {handle=simulate?null:HandleOf(id),nombre=profile.Name,alineamiento=HandleOf(aid),pvis=actual,
                    pendientes=Enumerable.Range(1,pvis.Count-1).Select(i=>(pvis[i].Elevation-pvis[i-1].Elevation)/(pvis[i].Station-pvis[i-1].Station)).ToArray(),
                    unidades="m",curvas_verticales=curves.Length>0,verificacion=verification,simulacion=simulate};
                if(simulate)tr.Abort();else tr.Commit();return result;
            }
        }
        private static object CrearParcelaPolilinea(JsonObject p,string method)
        {
            ExigirEscritura(method,p);SiteUnits();string name=SiteName(p,"nombre"),siteName=SiteName(p,"sitio_nuevo");
            var doc=Doc();var db=doc.Database;var civil=Civil();
            using(doc.LockDocument()) using(var tr=db.TransactionManager.StartTransaction())
            {
                foreach(ObjectId id in civil.GetSiteIds())
                    if(string.Equals(((Site)tr.GetObject(id,OpenMode.ForRead)).Name,siteName,StringComparison.OrdinalIgnoreCase))
                        throw new BridgeException(Rpc.ErrParams,"sitio_nuevo ya existe. Use un sitio nuevo para evitar subdividir parcelas ajenas.");
                var pl=SitePolyline(tr,db,p,true);double expectedArea=pl.Area;
                var style=SiteStyle(tr,"ParcelStyles",Txt(p,"estilo"));
                var layer=CapaId(tr,db,Txt(p,"capa"),true);
                var sid=Site.Create(civil,siteName);var site=(Site)tr.GetObject(sid,OpenMode.ForWrite);
                // Civil's public parcel creation contract is COM; the AcadObject belongs
                // to this exact document, not GetActiveObject from another CAD process.
                dynamic comSite=site.AcadObject;
                comSite.ParcelSegments.AddFromEntity(pl.AcadObject,false);
                var ids=site.GetParcelIds();
                if(ids.Count!=1)throw new InvalidOperationException("Se esperaba una unica parcela en el sitio nuevo, obtenidas: "+ids.Count);
                var parcel=(Parcel)tr.GetObject(ids[0],OpenMode.ForWrite);
                parcel.Name=name;parcel.StyleId=style;parcel.LayerId=layer;
                double area=parcel.Area;
                if(Math.Abs(area-expectedArea)>Math.Max(1e-6,expectedArea*1e-8))throw new InvalidOperationException("Area nativa distinta de la polilinea.");
                bool simulate=p["simular"]?.GetValue<bool>()??false;
                var result=new {handle=simulate?null:HandleOf(parcel.ObjectId),nombre=parcel.Name,sitio=siteName,
                    sitio_handle=simulate?null:HandleOf(sid),area_m2=area,polilinea=HandleOf(pl.ObjectId),fuente_conservada=true,simulacion=simulate};
                if(simulate)tr.Abort();else tr.Commit();return result;
            }
        }
    }
}
