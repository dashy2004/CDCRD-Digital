using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.ApplicationServices;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil.Settings;
using Autodesk.Civil.DatabaseServices.Styles;
using CadApplication = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CadEntity = Autodesk.AutoCAD.DatabaseServices.Entity;

namespace Cdcrd.BeamngExport;

public sealed partial class ExportCommands
{
    /// <summary>Read native geometry without prompts, writes, rebuilds or saves.</summary>
    public static CivilSnapshot ReadSnapshot(string expectedDocument, string terrainHandle,
        string roadHandle, string alignmentHandle, double width, string sceneLayerPrefix)
    {
        var doc = CadApplication.DocumentManager.MdiActiveDocument
            ?? throw new InvalidOperationException("No active drawing.");
        if (!Path.IsPathFullyQualified(expectedDocument) ||
            !string.Equals(Path.GetFullPath(doc.Name), Path.GetFullPath(expectedDocument), StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Active drawing differs from expected_document.");
        if (doc.Database.Insunits != UnitsValue.Meters ||
            CivilDocument.GetCivilDocument(doc.Database).Settings.DrawingSettings.UnitZoneSettings.DrawingUnits != DrawingUnitType.Meters)
            throw new InvalidOperationException("Both CAD and Civil units must be metres.");
        if (!double.IsFinite(width) || width <= 0 || width > 100)
            throw new ArgumentException("width_m must be finite in (0,100].");
        if (sceneLayerPrefix.Length < 3)
            throw new ArgumentException("scene_layer_prefix must identify an explicit set of layers.");
        using var tr = doc.Database.TransactionManager.StartTransaction();
        ObjectId Resolve(string handle) => doc.Database.GetObjectId(false, new Handle(Convert.ToInt64(handle,16)),0);
        var terrain = tr.GetObject(Resolve(terrainHandle), OpenMode.ForRead) as TinSurface
            ?? throw new ArgumentException("terrain_handle is not a TIN.");
        var road = tr.GetObject(Resolve(roadHandle), OpenMode.ForRead) as TinSurface
            ?? throw new ArgumentException("road_handle is not a TIN.");
        if (terrain.ObjectId == road.ObjectId) throw new ArgumentException("Two distinct TIN surfaces required.");
        AlignmentSnapshot? guide = null;
        if (!string.IsNullOrWhiteSpace(alignmentHandle))
        {
            var alignment = tr.GetObject(Resolve(alignmentHandle), OpenMode.ForRead) as Alignment
                ?? throw new ArgumentException("alignment_handle is not an alignment.");
            VerifyReference(alignment);
            if (alignment.StationEquations.Count != 0) throw new InvalidOperationException("Station equations are unsupported.");
            guide = ReadAlignment(alignment, null, road, width);
        }
        var result = new CivilSnapshot
        {
            Surfaces = new SnapshotSurfaces { Terrain = ReadSurface(terrain), Road = ReadSurface(road) },
            Alignment = guide,
            Sources = new Dictionary<string,string>
            {
                ["cad_document"] = Path.GetFileName(doc.Name),
                ["exporter"] = "Cdcrd.BeamngExport/native-api-1",
                ["terrain_handle"] = terrainHandle, ["road_handle"] = roadHandle,
                ["coordinate_order"] = "E,N,Z", ["cad_write_operations"] = "none",
                ["created_utc"] = DateTimeOffset.UtcNow.ToString("O"),
                ["scene_layer_prefix"] = sceneLayerPrefix
            }
        };
        var model = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(doc.Database),OpenMode.ForRead);
        foreach (ObjectId id in model)
        {
            if (id == terrain.ObjectId || id == road.ObjectId) continue;
            if (tr.GetObject(id,OpenMode.ForRead) is not CadEntity entity || !entity.Visible ||
                !entity.Layer.StartsWith(sceneLayerPrefix,StringComparison.OrdinalIgnoreCase)) continue;
            var layer=(LayerTableRecord)tr.GetObject(entity.LayerId,OpenMode.ForRead);
            if (layer.IsOff || layer.IsFrozen) continue;
            ReadEntity(entity,Matrix3d.Identity,entity.Handle.ToString(),entity.Layer,null,0);
        }
        // No commit: all model access remains read-only.
        return result;

        void ReadEntity(CadEntity entity, Matrix3d transform, string source, string layerName, double[]? inheritedColor, int depth)
        {
            if (depth > 8) throw new InvalidOperationException("Nested block depth exceeds eight.");
            if (!entity.Visible) return;
            var color=entity.Color;
            bool inherit=(color.IsByBlock || (color.IsByLayer && entity.Layer == "0")) && inheritedColor is not null;
            if (color.IsByLayer && !inherit) color=((LayerTableRecord)tr.GetObject(entity.LayerId,OpenMode.ForRead)).Color;
            var resolved=color.ColorValue;
            var rgb=inherit ? inheritedColor! : new[]{resolved.R/255.0,resolved.G/255.0,resolved.B/255.0,1.0};
            if(entity is BlockReference block)
            {
                var definition=(BlockTableRecord)tr.GetObject(block.BlockTableRecord,OpenMode.ForRead);
                if(definition.IsFromExternalReference) throw new InvalidOperationException("External blocks are unsupported: "+source);
                foreach(ObjectId child in definition)
                    if(tr.GetObject(child,OpenMode.ForRead) is CadEntity member)
                        ReadEntity(member,transform*block.BlockTransform,source+"/"+member.Handle,layerName,rgb,depth+1);
                return;
            }
            var vertices=new List<double[]>(); var triangles=new List<int[]>();
            if(entity is TinSurface tin)
            {
                var native=ReadSurface(tin);
                vertices=native.VerticesAbsoluteMetres;
                triangles=native.Triangles;
                var style=(SurfaceStyle)tr.GetObject(tin.StyleId,OpenMode.ForRead);
                var tint=style.GetDisplayStyleModel(SurfaceDisplayStyleType.Triangles).Color.ColorValue;
                rgb=new[]{tint.R/255.0,tint.G/255.0,tint.B/255.0,1.0};
            }
            else if(entity is Face face)
            {
                for(short i=0;i<4;i++) vertices.Add(Point(face.GetVertexAt(i)));
                triangles.Add(new[]{0,1,2});
                if(!face.GetVertexAt(2).IsEqualTo(face.GetVertexAt(3))) triangles.Add(new[]{0,2,3});
            }
            else if(entity is Solid3d || entity is Autodesk.AutoCAD.DatabaseServices.Surface)
            {
                var mesh=SubDMesh.GetObjectMesh(entity,new MeshFaceterData { FaceterMeshType=2 });
                foreach(Point3d point in mesh.VertexArray) vertices.Add(Point(point));
                var faces=mesh.FaceArray;
                for(int i=0;i<faces.Count;)
                {
                    int n=faces[i++];
                    if(n<3 || i+n>faces.Count) throw new InvalidOperationException("Invalid native mesh face.");
                    for(int j=1;j<n-1;j++) triangles.Add(new[]{faces[i],faces[i+j],faces[i+j+1]});
                    i+=n;
                }
            }
            else { result.SceneSkipped.Add(source+":"+entity.GetType().Name+":"+layerName); return; }
            if(vertices.Count == 0 || triangles.Count == 0) throw new InvalidOperationException("Empty native mesh: "+source);
            if(vertices.Count>1000000 || triangles.Count>2000000) throw new InvalidOperationException("Native mesh exceeds export budget.");
            result.SceneMeshes.Add(new SceneMeshSnapshot { Handle=source, Layer=layerName, Kind=entity.GetType().Name,
                Color=rgb,Vertices=vertices,Triangles=triangles });
            double[] Point(Point3d p) { var q=p.TransformBy(transform); VerifyPoint(q); return new[]{q.X,q.Y,q.Z}; }
        }
    }
}
