using System;
using System.Collections.Generic;
using System.Linq;

namespace Cdcrd.Civil3dBridge
{
    // Deliberately straight segments only: do not approximate arcs or silently flatten 3D.
    internal static class SiteDesignContract
    {
        const double Tol = 1e-8;
        internal static void Finite(double value, string field)
        { if (!double.IsFinite(value)) throw new ArgumentException(field + " debe ser finito."); }
        internal static double Polyline(IReadOnlyList<(double X,double Y)> points, bool closed)
        {
            if (points.Count < (closed ? 3 : 2) || points.Count > 1000)
                throw new ArgumentException("Polilinea: requiere 2-1000 vertices (3 minimo si cerrada).");
            foreach (var p in points) { Finite(p.X,"X"); Finite(p.Y,"Y"); }
            for (int i=0;i<points.Count;i++)
                for (int j=i+1;j<points.Count;j++)
                    if (Math.Abs(points[i].X-points[j].X)<=Tol && Math.Abs(points[i].Y-points[j].Y)<=Tol)
                        throw new ArgumentException("Vertices repetidos o segmento nulo.");
            int count=closed?points.Count:points.Count-1;
            for (int i=0;i<count;i++)
            {
                var a=points[i]; var b=points[(i+1)%points.Count];
                for (int j=i+1;j<count;j++)
                {
                    var c=points[j]; var d=points[(j+1)%points.Count];
                    bool adjacent=j==i+1 || (closed && i==0 && j==count-1);
                    if (adjacent)
                    {
                        // Adjacent segments may share one endpoint but cannot double back.
                        var shared=j==i+1?b:a;var u=j==i+1?a:b;var v=j==i+1?d:c;
                        if (Math.Abs(Cross(shared,u,v))<=Tol &&
                            (u.X-shared.X)*(v.X-shared.X)+(u.Y-shared.Y)*(v.Y-shared.Y)>0)
                            throw new ArgumentException("Segmentos consecutivos superpuestos.");
                    }
                    else if (Intersects(a,b,c,d)) throw new ArgumentException("Polilinea autointersectada o con segmentos en contacto.");
                }
            }
            double area=0;var origin=points[0];
            if(closed) for(int i=1;i<points.Count-1;i++) area+=Cross(origin,points[i],points[i+1])/2;
            if(closed && Math.Abs(area)<=Tol) throw new ArgumentException("Area nula.");
            return Math.Abs(area);
        }
        static double Cross((double X,double Y) a,(double X,double Y) b,(double X,double Y) c)
            => (b.X-a.X)*(c.Y-a.Y)-(b.Y-a.Y)*(c.X-a.X);
        static bool On((double X,double Y) a,(double X,double Y) b,(double X,double Y) p)
            => Math.Abs(Cross(a,b,p))<=Tol && p.X>=Math.Min(a.X,b.X)-Tol && p.X<=Math.Max(a.X,b.X)+Tol && p.Y>=Math.Min(a.Y,b.Y)-Tol && p.Y<=Math.Max(a.Y,b.Y)+Tol;
        static bool Intersects((double X,double Y) a,(double X,double Y) b,(double X,double Y) c,(double X,double Y) d)
        {
            double x=Cross(a,b,c),y=Cross(a,b,d),z=Cross(c,d,a),w=Cross(c,d,b);
            return (x>0 && y<0 || x<0 && y>0) && (z>0 && w<0 || z<0 && w>0) || On(a,b,c)||On(a,b,d)||On(c,d,a)||On(c,d,b);
        }
        internal static void Pvis(IReadOnlyList<(double Station,double Elevation)> values,double start,double end)
        {
            Finite(start,"estacion inicial");Finite(end,"estacion final");
            if(end<=start || values.Count<2 || values.Count>1000) throw new ArgumentException("Se requieren 2-1000 PVI y un eje de longitud positiva.");
            double previous=double.NegativeInfinity;
            foreach(var value in values)
            {
                Finite(value.Station,"estacion");Finite(value.Elevation,"elevacion");
                if(value.Station<start || value.Station>end || value.Station-previous<=Tol)
                    throw new ArgumentException("PVI fuera del eje, duplicados o sin orden estrictamente creciente.");
                previous=value.Station;
            }
        }
    }
}
