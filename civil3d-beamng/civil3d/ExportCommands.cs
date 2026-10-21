using System.Globalization;
using System.Text.Json;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil.Settings;
using CadApplication = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivilEntity = Autodesk.Civil.DatabaseServices.Entity;

[assembly: CommandClass(typeof(Cdcrd.BeamngExport.ExportCommands))]

namespace Cdcrd.BeamngExport;

public sealed class ExportCommands
{
    private const double SampleStepMetres = 5;

    [CommandMethod("CDCRD", "CDCRDBEAMNGEXPORT", CommandFlags.Modal)]
    public void ExportSnapshot()
    {
        var document = CadApplication.DocumentManager.MdiActiveDocument;
        if (document is null)
            return;
        var editor = document.Editor;
        try
        {
            if (document.Database.Insunits != UnitsValue.Meters)
                throw new InvalidOperationException("El dibujo debe declarar INSUNITS=6 (metros). Revise las unidades del proyecto antes de exportar; el plugin no cambia el DWG.");
            var civilUnits = CivilDocument.GetCivilDocument(document.Database).Settings.DrawingSettings.UnitZoneSettings.DrawingUnits;
            if (civilUnits != DrawingUnitType.Meters)
                throw new InvalidOperationException("Las Drawing Settings de Civil 3D deben declarar DrawingUnits=Meters ademas de INSUNITS=6. Revise ambas unidades antes de exportar.");

            editor.WriteMessage("\nCDCRD BeamNG: exportacion de solo lectura, sin IA. Seleccione una TIN de terreno y una TIN de calzada final.");
            var terrainId = SelectEntity<TinSurface>(editor, "\nSeleccione TIN de terreno: ", false);
            var roadId = SelectEntity<TinSurface>(editor, "\nSeleccione TIN de calzada final (Top/pavimento): ", false);
            if (terrainId == roadId)
                throw new InvalidOperationException("Terreno y calzada deben ser superficies distintas.");
            var alignmentId = SelectEntity<Alignment>(editor, "\nSeleccione alineamiento opcional o Enter para omitir: ", true);

            CivilSnapshot snapshot;
            using (var transaction = document.Database.TransactionManager.StartTransaction())
            {
                var terrain = (TinSurface)transaction.GetObject(terrainId, OpenMode.ForRead);
                var road = (TinSurface)transaction.GetObject(roadId, OpenMode.ForRead);
                var terrainSnapshot = ReadSurface(terrain);
                var roadSnapshot = ReadSurface(road);
                editor.WriteMessage($"\nTIN completas: terreno {terrainSnapshot.Triangles.Count} triangulos; calzada {roadSnapshot.Triangles.Count} triangulos.");

                AlignmentSnapshot? alignmentSnapshot = null;
                if (!alignmentId.IsNull)
                {
                    var alignment = (Alignment)transaction.GetObject(alignmentId, OpenMode.ForRead);
                    VerifyReference(alignment);
                    // Station equations can make displayed stations ambiguous. Do not
                    // silently sample another chainage or truncate an alignment.
                    if (alignment.StationEquations.Count != 0)
                        throw new InvalidOperationException("El alineamiento tiene ecuaciones de estacion. Omita el alineamiento para exportar las TIN, o use un eje sin ecuaciones en este MVP.");
                    var profile = SelectProfile(editor, transaction, alignment);
                    var width = ReadWidth(editor);
                    alignmentSnapshot = ReadAlignment(alignment, profile, road, width);
                }

                snapshot = new CivilSnapshot
                {
                    Surfaces = new SnapshotSurfaces { Terrain = terrainSnapshot, Road = roadSnapshot },
                    Alignment = alignmentSnapshot,
                    Sources = new Dictionary<string, string>
                    {
                        ["cad_document"] = Path.GetFileName(document.Name),
                        ["exporter"] = "Cdcrd.BeamngExport/0.1.0",
                        ["created_utc"] = DateTimeOffset.UtcNow.ToString("O", CultureInfo.InvariantCulture),
                        ["drawing_units"] = "INSUNITS=6",
                        ["civil_drawing_units"] = civilUnits.ToString(),
                        ["terrain_handle"] = terrain.Handle.ToString(),
                        ["road_handle"] = road.Handle.ToString(),
                        ["road_geometry"] = "selected_visible_final_tin_not_reconstructed_from_width",
                        ["coordinate_order"] = "E,N,Z",
                        ["cad_write_operations"] = "none"
                    }
                };
                // Disposal aborts this read-only transaction; nothing is upgraded,
                // rebuilt, appended, committed, or saved in the drawing.
            }

            var options = new PromptSaveFileOptions("\nGuardar snapshot JSON externo:")
            {
                DialogCaption = "CDCRD BeamNG - snapshot externo",
                Filter = "JSON (*.json)|*.json",
                InitialFileName = "civil3d-beamng-" + DateTimeOffset.UtcNow.ToString("yyyyMMddTHHmmssfffZ", CultureInfo.InvariantCulture) + ".json"
            };
            var selection = editor.GetFileNameForSave(options);
            if (selection.Status != PromptStatus.OK)
                throw new OperationCanceledException();
            var target = Path.GetFullPath(selection.StringResult);
            if (!string.Equals(Path.GetExtension(target), ".json", StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Use un archivo con extension .json.");
            WriteSnapshot(snapshot, target);
            editor.WriteMessage($"\nSnapshot completo guardado: {target}\nConviertalo con la CLI civil3d-beamng. Las TIN conservan Z, bombeo, peralte y fronteras visibles de la superficie elegida.");
        }
        catch (OperationCanceledException)
        {
            editor.WriteMessage("\nExportacion cancelada. No se modifico el dibujo.");
        }
        catch (Autodesk.AutoCAD.Runtime.Exception exception) when (exception.ErrorStatus == ErrorStatus.UserBreak)
        {
            editor.WriteMessage("\nExportacion cancelada. No se modifico el dibujo.");
        }
        catch (System.Exception exception)
        {
            editor.WriteMessage($"\nCDCRD BeamNG: no se pudo exportar. {exception.Message}");
        }
    }

    private static ObjectId SelectEntity<T>(Editor editor, string prompt, bool optional) where T : Autodesk.AutoCAD.DatabaseServices.DBObject
    {
        var options = new PromptEntityOptions(prompt) { AllowNone = optional };
        options.SetRejectMessage("\nEl objeto no es del tipo requerido.");
        options.AddAllowedClass(typeof(T), true);
        var result = editor.GetEntity(options);
        if (optional && result.Status == PromptStatus.None)
            return ObjectId.Null;
        if (result.Status != PromptStatus.OK)
            throw new OperationCanceledException();
        return result.ObjectId;
    }

    private static void VerifyReference(CivilEntity entity)
    {
        if (entity.IsReferenceObject && (!entity.IsReferenceValid || entity.IsReferenceStale))
            throw new InvalidOperationException($"La referencia Civil 3D '{entity.Name}' no es valida o esta desactualizada. Sincronice primero el origen.");
    }

    private static SurfaceSnapshot ReadSurface(TinSurface surface)
    {
        VerifyReference(surface);
        if (surface.IsOutOfDate)
            throw new InvalidOperationException($"La TIN '{surface.Name}' esta desactualizada. Reconstruyala en Civil 3D antes de exportar.");
        var result = new SurfaceSnapshot { Name = surface.Name };
        var vertexIndices = new Dictionary<(double, double, double), int>();
        var edgeUses = new Dictionary<(int, int), int>();

        // false is essential: invisible faces outside a boundary or inside a
        // hidden area must not reappear as driveable terrain or pavement.
        using var triangles = surface.GetTriangles(false);
        foreach (TinSurfaceTriangle triangle in triangles)
        {
            using var triangleWrapper = triangle;
            using var vertex1 = triangle.Vertex1;
            using var vertex2 = triangle.Vertex2;
            using var vertex3 = triangle.Vertex3;
            var a = vertex1.Location;
            var b = vertex2.Location;
            var c = vertex3.Location;
            VerifyPoint(a); VerifyPoint(b); VerifyPoint(c);
            var crossZ = (b.X - a.X) * (c.Y - a.Y) - (b.Y - a.Y) * (c.X - a.X);
            if (!double.IsFinite(crossZ) || crossZ == 0)
                throw new InvalidOperationException($"La TIN '{surface.Name}' contiene un triangulo degenerado o coordenadas fuera de rango.");
            var face = new[] { Index(a), Index(b), Index(c) };
            result.Triangles.Add(face);
            AddEdge(face[0], face[1]); AddEdge(face[1], face[2]); AddEdge(face[2], face[0]);
        }
        if (result.Triangles.Count == 0)
            throw new InvalidOperationException($"La TIN '{surface.Name}' no contiene triangulos visibles.");
        foreach (var (edge, count) in edgeUses)
        {
            if (count == 1)
                result.BoundaryEdges.Add([edge.Item1, edge.Item2]);
            else if (count > 2)
                throw new InvalidOperationException($"La TIN '{surface.Name}' tiene una arista compartida por mas de dos triangulos.");
        }
        return result;

        int Index(Point3d point)
        {
            var key = (point.X, point.Y, point.Z);
            if (vertexIndices.TryGetValue(key, out var index))
                return index;
            index = result.VerticesAbsoluteMetres.Count;
            vertexIndices.Add(key, index);
            result.VerticesAbsoluteMetres.Add([point.X, point.Y, point.Z]);
            return index;
        }

        void AddEdge(int a, int b)
        {
            var key = a < b ? (a, b) : (b, a);
            edgeUses.TryGetValue(key, out var count);
            edgeUses[key] = count + 1;
        }
    }

    private static Profile? SelectProfile(Editor editor, Transaction transaction, Alignment alignment)
    {
        var profiles = new List<Profile>();
        foreach (ObjectId profileId in alignment.GetProfileIds())
            profiles.Add((Profile)transaction.GetObject(profileId, OpenMode.ForRead));
        if (profiles.Count == 0)
        {
            editor.WriteMessage("\nEl eje no tiene perfiles: se usara la cota de la TIN de calzada en cada nodo.");
            return null;
        }
        editor.WriteMessage("\nPerfiles del alineamiento (Enter: cotas de TIN calzada):");
        for (var i = 0; i < profiles.Count; i++)
            editor.WriteMessage($"\n  {i + 1}: {profiles[i].Name}");
        var options = new PromptIntegerOptions("\nNumero de perfil o Enter: ")
        {
            AllowNone = true,
            AllowNegative = false,
            AllowZero = false,
            LowerLimit = 1,
            UpperLimit = profiles.Count
        };
        var result = editor.GetInteger(options);
        if (result.Status == PromptStatus.None)
            return null;
        if (result.Status != PromptStatus.OK)
            throw new OperationCanceledException();
        var profile = profiles[result.Value - 1];
        VerifyReference(profile);
        if (profile.AlignmentId != alignment.ObjectId)
            throw new InvalidOperationException("El perfil elegido no pertenece al alineamiento.");
        return profile;
    }

    private static double ReadWidth(Editor editor)
    {
        var options = new PromptDoubleOptions("\nAncho en metros para nodos del eje (no modifica la malla): ")
        {
            AllowNone = true,
            AllowNegative = false,
            AllowZero = false,
            DefaultValue = 11.4,
            UseDefaultValue = true
        };
        var result = editor.GetDouble(options);
        if (result.Status != PromptStatus.OK)
            throw new OperationCanceledException();
        if (!double.IsFinite(result.Value) || result.Value <= 0)
            throw new InvalidOperationException("El ancho debe ser finito y mayor que cero.");
        return result.Value;
    }

    private static AlignmentSnapshot ReadAlignment(Alignment alignment, Profile? profile, TinSurface road, double width)
    {
        var start = alignment.StartingStation;
        var end = alignment.EndingStation;
        if (!double.IsFinite(start) || !double.IsFinite(end) || end <= start)
            throw new InvalidOperationException("El alineamiento debe tener un intervalo de estaciones finito y positivo.");
        if (profile is not null && (profile.StartingStation > start || profile.EndingStation < end))
            throw new InvalidOperationException("El perfil no cubre todo el alineamiento. No se recortara la ruta automaticamente.");
        var result = new AlignmentSnapshot
        {
            Name = alignment.Name,
            ElevationSource = profile is null ? "selected_road_tin" : "profile:" + profile.Name
        };
        foreach (var station in StationSampling.CreateStations(start, end, SampleStepMetres))
            AddNode(station);
        return result;

        void AddNode(double station)
        {
            double easting = 0, northing = 0;
            alignment.PointLocation(station, 0, ref easting, ref northing);
            var z = profile is null ? road.FindElevationAtXY(easting, northing) : profile.ElevationAt(station);
            VerifyPoint(new Point3d(easting, northing, z));
            result.NodesAbsoluteMetres.Add([easting, northing, z, width]);
            result.StationsMetres.Add(station);
        }
    }

    private static void VerifyPoint(Point3d point)
    {
        if (!double.IsFinite(point.X) || !double.IsFinite(point.Y) || !double.IsFinite(point.Z))
            throw new InvalidOperationException("Una coordenada no es finita (NaN o infinito).");
    }

    private static void WriteSnapshot(CivilSnapshot snapshot, string target)
    {
        if (File.Exists(target))
            throw new IOException("El archivo de destino ya existe. Elija otro nombre para conservar las exportaciones anteriores.");
        var temporary = target + ".tmp-" + Guid.NewGuid().ToString("N");
        try
        {
            using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                JsonSerializer.Serialize(output, snapshot, new JsonSerializerOptions { WriteIndented = false });
                output.Flush(flushToDisk: true);
            }
            File.Move(temporary, target, overwrite: false);
        }
        finally
        {
            if (File.Exists(temporary))
                File.Delete(temporary);
        }
    }
}
