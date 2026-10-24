using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.DatabaseServices;
using CivAssembly = Autodesk.Civil.DatabaseServices.Assembly;
using CivPoint = Autodesk.Civil.DatabaseServices.Point;

namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        private static (ObjectId Id, CivPoint Hook) AddBermDitch(
            Transaction tr, CivAssembly assembly, ObjectId layer, string name,
            string suffix, SubassemblySideType side, Point3d origin,
            Subassembly lane, CunetaBermaContract section, List<object> parts)
        {
            // Attach at pavement surface, not at the bottom of its four layers.
            var hook = lane.Points.Cast<CivPoint>()
                .OrderByDescending(pt => Math.Abs(pt.Offset)).ThenByDescending(pt => pt.Elevation).First();
            var parent = lane.ObjectId;
            foreach (var spec in section.Links(side == SubassemblySideType.Left))
            {
                var id = Civil().SubassemblyCollection.ImportStockSubassembly(
                    name + "_" + spec.Role + suffix, "Subassembly.LinkWidthAndSlope", origin);
                var sub = (Subassembly)tr.GetObject(id, OpenMode.ForWrite);
                sub.LayerId=layer; sub.Side=side;
                sub.ParamsDouble["Width"].Value=spec.Width;
                sub.ParamsDouble["Slope"].Value=spec.Slope;
                sub.ParamsLong["UseSuperelevationSlope"].Value=0;
                sub.ParamsLong["SlopeDirection"].Value=0;
                sub.ParamsLong["OmitLink"].Value=0;
                sub.ParamsString["SurfaceCodes"].Value="Top,"+spec.Role;
                sub.ParamsString["PointCodes"].Value=spec.PointCode;
                assembly.AddSubassembly(id, hook); sub.Run();
                CorridorQaCheckpoint?.Invoke("berma-cuneta-part-added");
                if(sub.AssemblyId!=assembly.ObjectId || sub.SubassemblyHookTo!=parent || sub.Side!=side ||
                    Math.Abs(sub.ParamsDouble["Width"].Value-spec.Width)>1e-9 ||
                    Math.Abs(sub.ParamsDouble["Slope"].Value-spec.Slope)>1e-9)
                    throw new InvalidOperationException("Berma/cuneta no coincide con el contrato");
                var outer=sub.Points.Cast<CivPoint>().OrderByDescending(pt=>Math.Abs(pt.Offset)).First();
                // Points are local to EACH subassembly, including attached links.
                // Compare this link's endpoints; the parent hook uses another frame.
                var inner=sub.Points.Cast<CivPoint>().OrderBy(pt=>Math.Abs(pt.Offset)).First();
                double signedWidth=side==SubassemblySideType.Left?-spec.Width:spec.Width;
                if(Math.Abs(outer.Offset-inner.Offset-signedWidth)>1e-7 ||
                    Math.Abs(outer.Elevation-inner.Elevation-spec.Width*spec.Slope)>1e-7)
                    throw new InvalidOperationException("Geometria nativa de berma/cuneta incorrecta");
                parts.Add(new {handle=HandleOf(id),rol=spec.Role,lado=side.ToString(),engancha_a=HandleOf(parent),
                    ancho=spec.Width,pendiente=spec.Slope,codigo_punto=spec.PointCode,
                    extremo_local=new[]{outer.Offset,outer.Elevation}});
                parent=id; hook=outer;
            }
            return (parent,hook);
        }
    }
}
