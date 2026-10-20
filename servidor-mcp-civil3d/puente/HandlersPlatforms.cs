using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil;
using Autodesk.Civil.DatabaseServices;
using FeatureLine = Autodesk.Civil.DatabaseServices.FeatureLine;
using TinSurface = Autodesk.Civil.DatabaseServices.TinSurface;

namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        private static object PlatformOperation(Func<object> work)
        {
            try{return work();}
            catch(ArgumentException ex){Log.Write("Plataforma: "+ex);throw new BridgeException(Rpc.ErrParams,ex.Message);}
        }
        private static List<Point3d> FeaturePoints(FeatureLine feature,bool requireClosed)
        {
            if(feature.GetType()!=typeof(FeatureLine) || feature.IsReferenceObject || !feature.SiteId.IsNull || feature.CurvesCount!=0)
                throw new ArgumentException("Requiere FeatureLine recta, sin sitio y sin referencia externa/corredor.");
            var points=feature.GetPoints(FeatureLinePointType.AllPoints).Cast<Point3d>().ToList();
            if(points.Count>1 && points[0].DistanceTo(points[points.Count-1])<1e-8)points.RemoveAt(points.Count-1);
            if(requireClosed && !feature.Closed)throw new ArgumentException("Requiere feature line cerrada.");
            foreach(var pt in points)SiteDesignContract.Finite(pt.Z,"elevacion");
            SiteDesignContract.Polyline(points.Select(pt=>(pt.X,pt.Y)).ToArray(),feature.Closed);
            return points;
        }
        private static object CreateFeatureLine(JsonObject p,string method)
        {
            ExigirEscritura(method,p);SiteUnits();string name=SiteName(p,"nombre");
            var doc=Doc();var db=doc.Database;
            using(doc.LockDocument()) using(var tr=db.TransactionManager.StartTransaction())
            {
                var source=tr.GetObject(IdFromHandle(db,Txt(p,"polilinea")),OpenMode.ForRead) as Polyline;
                if(source==null)throw new ArgumentException("Se requiere handle de LWPOLYLINE.");
                source=SitePolyline(tr,db,p,source.Closed);
                // Scan model space, including features in sites, so duplicate names fail before writes.
                var model=(BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db),OpenMode.ForRead);
                foreach(ObjectId id in model)
                    if(tr.GetObject(id,OpenMode.ForRead) is FeatureLine other && string.Equals(other.Name,name,StringComparison.OrdinalIgnoreCase))
                        throw new ArgumentException("Ya existe una feature line con ese nombre.");
                var values=(p["elevaciones"] as JsonArray)?.Select(n=>n.GetValue<double>()).ToArray();
                var elevations=PlatformContract.Elevations(values,source.NumberOfVertices);
                var style=SiteStyle(tr,"FeatureLineStyles",Txt(p,"estilo"));
                var layer=CapaId(tr,db,Txt(p,"capa"),true);
                // Only the temporary clone is passed to Civil; source ownership/geometry is preserved.
                model.UpgradeOpen();var clone=(Polyline)source.Clone();model.AppendEntity(clone);tr.AddNewlyCreatedDBObject(clone,true);
                var fid=FeatureLine.Create(name,clone.ObjectId);
                var feature=(FeatureLine)tr.GetObject(fid,OpenMode.ForWrite);feature.StyleId=style;feature.LayerId=layer;
                // Civil returns the closing point twice; SetPointElevation accepts
                // only distinct point indexes. Use the normalized ring here too.
                var points=FeaturePoints(feature,false);
                for(int i=0;i<points.Count;i++)
                {
                    int match=-1;
                    for(int j=0;j<source.NumberOfVertices;j++)
                    {
                        var pt=source.GetPoint2dAt(j);
                        if(Math.Abs(points[i].X-pt.X)<1e-7 && Math.Abs(points[i].Y-pt.Y)<1e-7){match=j;break;}
                    }
                    if(match<0)throw new InvalidOperationException("Civil genero un vertice no presente en la fuente.");
                    feature.SetPointElevation(i,elevations[match]);
                }
                if(!clone.IsErased)clone.Erase();
                var actual=FeaturePoints(feature,false);
                if(actual.Count!=source.NumberOfVertices || feature.Closed!=source.Closed)throw new InvalidOperationException("Topologia de la feature line distinta de la fuente.");
                for(int j=0;j<source.NumberOfVertices;j++)
                {
                    var pt=source.GetPoint2dAt(j);
                    if(!actual.Any(a=>Math.Abs(a.X-pt.X)<1e-7 && Math.Abs(a.Y-pt.Y)<1e-7 && Math.Abs(a.Z-elevations[j])<1e-7))
                        throw new InvalidOperationException("Relectura XYZ distinta de las cotas solicitadas.");
                }
                bool simulate=p["simular"]?.GetValue<bool>()??false;
                var result=new {handle=simulate?null:HandleOf(fid),nombre=feature.Name,polilinea=HandleOf(source.ObjectId),fuente_conservada=true,
                    cerrada=feature.Closed,sin_sitio=true,puntos=actual.Select(pt=>new[]{pt.X,pt.Y,pt.Z}).ToArray(),longitud_2d_m=feature.Length2D,longitud_3d_m=feature.Length3D,simulacion=simulate};
                if(simulate)tr.Abort();else tr.Commit();return result;
            }
        }
        private static object CreateFeatureSurface(JsonObject p,string method)
        {
            ExigirEscritura(method,p);SiteUnits();string name=SiteName(p,"nombre");
            var doc=Doc();var db=doc.Database;
            using(doc.LockDocument()) using(var tr=db.TransactionManager.StartTransaction())
            {
                foreach(ObjectId id in Civil().GetSurfaceIds())
                    if(string.Equals(((Autodesk.Civil.DatabaseServices.Surface)tr.GetObject(id,OpenMode.ForRead)).Name,name,StringComparison.OrdinalIgnoreCase))
                        throw new ArgumentException("Ya existe una superficie con ese nombre.");
                FeatureLine Read(string handle)
                {
                    if(tr.GetObject(IdFromHandle(db,handle),OpenMode.ForRead) is not FeatureLine f)throw new ArgumentException("El handle debe ser una FeatureLine.");return f;
                }
                var outer=Read(Txt(p,"contorno"));var boundary=FeaturePoints(outer,true);
                double expectedArea=PlatformContract.Convex(boundary.Select(pt=>(pt.X,pt.Y)).ToArray());
                var ids=new ObjectIdCollection(new[]{outer.ObjectId});var vertices=new List<Point3d>(boundary);
                if(!string.IsNullOrWhiteSpace(Txt(p,"linea_interior")))
                {
                    var inner=Read(Txt(p,"linea_interior"));var points=FeaturePoints(inner,true);
                    PlatformContract.Inside(boundary.Select(pt=>(pt.X,pt.Y)).ToArray(),points.Select(pt=>(pt.X,pt.Y)).ToArray());
                    ids.Add(inner.ObjectId);vertices.AddRange(points);
                }
                var style=SiteStyle(tr,"SurfaceStyles",Txt(p,"estilo"));var layer=CapaId(tr,db,Txt(p,"capa"),true);
                var sid=TinSurface.Create(db,name);var surface=(TinSurface)tr.GetObject(sid,OpenMode.ForWrite);surface.StyleId=style;surface.LayerId=layer;
                // Civil requires a positive mid-ordinate distance even for lines
                // without arcs; no supplementary or weeding distances are used.
                surface.BreaklinesDefinition.AddStandardBreaklines(ids,0.01,0,0,0);
                var closed=new Point3dCollection(boundary.Concat(new[]{boundary[0]}).ToArray());
                surface.BoundariesDefinition.AddBoundaries(closed,0.01,SurfaceBoundaryType.Outer,true);
                surface.Rebuild();
                var triangles=surface.GetTriangles(false).Cast<TinSurfaceTriangle>().ToArray();double area=0;
                foreach(var triangle in triangles)
                {
                    var a=triangle.Vertex1.Location;var b=triangle.Vertex2.Location;var c=triangle.Vertex3.Location;
                    area+=Math.Abs((b.X-a.X)*(c.Y-a.Y)-(b.Y-a.Y)*(c.X-a.X))/2;
                }
                if(triangles.Length==0 || Math.Abs(area-expectedArea)>Math.Max(1e-6,expectedArea*1e-8))throw new InvalidOperationException("El TIN no cubre el contorno completo.");
                foreach(var point in vertices)
                    if(Math.Abs(surface.FindElevationAtXY(point.X,point.Y)-point.Z)>1e-6)throw new InvalidOperationException("El TIN no respeta las cotas de las feature lines.");
                bool simulate=p["simular"]?.GetValue<bool>()??false;
                var result=new {handle=simulate?null:HandleOf(sid),nombre=surface.Name,contorno=HandleOf(outer.ObjectId),lineas=ids.Cast<ObjectId>().Select(HandleOf).ToArray(),
                    area_2d_m2=area,triangulos=triangles.Length,simulacion=simulate,tipo="TinSurface",grading_nativo=false,
                    limite="Contorno XY por copia de coordenadas; cambios de XY requieren crear otra superficie. Rebuild para cambios de cotas."};
                if(simulate)tr.Abort();else tr.Commit();return result;
            }
        }
    }
}
