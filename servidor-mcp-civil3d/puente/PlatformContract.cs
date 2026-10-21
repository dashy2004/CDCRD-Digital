using System;
using System.Collections.Generic;
using System.Linq;
namespace Cdcrd.Civil3dBridge
{
    internal static class PlatformContract
    {
        internal static double[] Elevations(IReadOnlyList<double> values,int count)
        {
            if(values==null || values.Count!=1 && values.Count!=count)
                throw new ArgumentException("elevaciones requiere una cota constante o una por vertice fuente.");
            foreach(double z in values)SiteDesignContract.Finite(z,"elevacion");
            return values.Count==1?Enumerable.Repeat(values[0],count).ToArray():values.ToArray();
        }
        static double Cross((double X,double Y) a,(double X,double Y) b,(double X,double Y) c)
            => (b.X-a.X)*(c.Y-a.Y)-(b.Y-a.Y)*(c.X-a.X);
        internal static double Convex(IReadOnlyList<(double X,double Y)> points)
        {
            double area=SiteDesignContract.Polyline(points,true);int sign=0;
            for(int i=0;i<points.Count;i++)
            {
                double c=Cross(points[i],points[(i+1)%points.Count],points[(i+2)%points.Count]);
                if(Math.Abs(c)<1e-8)throw new ArgumentException("El contorno debe ser estrictamente convexo, sin vertices colineales.");
                int next=Math.Sign(c);if(sign!=0 && next!=sign)throw new ArgumentException("Contorno concavo no soportado.");sign=next;
            }
            return area;
        }
        internal static void Inside(IReadOnlyList<(double X,double Y)> outer,IReadOnlyList<(double X,double Y)> inner)
        {
            Convex(outer);Convex(inner);
            int sign=Math.Sign(Cross(outer[0],outer[1],outer[2]));
            foreach(var point in inner)
                for(int i=0;i<outer.Count;i++)
                    if(sign*Cross(outer[i],outer[(i+1)%outer.Count],point)<=1e-8)
                        throw new ArgumentException("La linea interior debe estar estrictamente dentro del contorno, sin contacto.");
        }
    }
}
