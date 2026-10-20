using System;
using System.IO;
using System.Linq;
using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using Autodesk.AutoCAD.Colors;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil;
using Autodesk.Civil.ApplicationServices;
using Autodesk.Civil.Settings;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil.DatabaseServices.Styles;
using SectionViewStyle = Autodesk.Civil.DatabaseServices.Styles.SectionViewStyle;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivilSurface = Autodesk.Civil.DatabaseServices.Surface;
namespace Cdcrd.Earthworks;

/// <summary>Native API called on the Civil 3D document thread. No save or global setting changes.</summary>
public static class TerrainApi
{
    public static readonly JsonSerializerOptions JsonOptions = new() { WriteIndented = true, PropertyNamingPolicy = JsonNamingPolicy.CamelCase, PropertyNameCaseInsensitive = true };
    static void Require(bool condition, string text) { if (!condition) throw new InvalidOperationException(text); }
    static Point3d P(double[] a) { Require(a != null && a.Length == 3 && a.All(double.IsFinite), "Expected finite XYZ"); return new(a[0], a[1], a[2]); }
    static double[] XYZ(Point3d p) => new[] { p.X, p.Y, p.Z };
    static void MetricAxis(AxisStyle axis, string field, string title)
    {
        string text = "<[Section View Point " + field + "(Um|P2|RN|Sn|OF|AP|GC|UN)]> m";
        axis.MajorTickStyle.LabelText = text;
        axis.MinorTickStyle.LabelText = text;
        axis.TitleStyle.Text = title + " (m)";
    }
    static object GraphUnits(SectionViewStyle style) => new
    {
        name = style.Name,
        handle = style.ObjectId.Handle.ToString(),
        title = style.GraphStyle.TitleStyle.Text,
        axes = new[] { style.BottomAxis, style.TopAxis, style.LeftAxis, style.RightAxis, style.CenterAxis }
            .Select(a => new { major = a.MajorTickStyle.LabelText, minor = a.MinorTickStyle.LabelText, title = a.TitleStyle.Text }).ToArray()
    };
    static void Guard(Request r, bool requireMetric = true)
    {
        var d = AcApp.DocumentManager.MdiActiveDocument;
        Require(d != null && !string.IsNullOrWhiteSpace(r.ExpectedDrawing) && Path.IsPathFullyQualified(r.ExpectedDrawing), "An absolute expected drawing path is required");
        Require(string.Equals(Path.GetFullPath(d.Name), Path.GetFullPath(r.ExpectedDrawing), StringComparison.OrdinalIgnoreCase), "Active drawing does not match request");
        var civil = CivilApplication.ActiveDocument;
        Require(civil != null, "Terrain operations require a Civil 3D document; plain AutoCAD does not provide TIN surfaces or Civil sections");
        if (requireMetric)
        {
            Require(d.Database.Insunits == UnitsValue.Meters, $"Drawing INSUNITS must be Meters; found {d.Database.Insunits}. No coordinates were scaled");
            var units = civil.Settings.DrawingSettings.UnitZoneSettings.DrawingUnits;
            Require(units == DrawingUnitType.Meters, $"Civil DrawingUnits must be Meters; found {units}. INSUNITS alone is insufficient. No coordinates were scaled");
        }
        Require(!string.IsNullOrWhiteSpace(r.NamePrefix) && r.NamePrefix.StartsWith("CD"), "Explicit CD-prefixed namespace required");
        Require(r.VolumeTolerance > 0 && r.VolumeTolerance <= 0.01 && double.IsFinite(r.VolumeTolerance), "Invalid volume tolerance");
        if (r.ExpectedCogoCount >= 0) Require(CivilApplication.ActiveDocument.CogoPoints.Count == r.ExpectedCogoCount, "Unexpected COGO count");
    }
    static ObjectId FindSurface(Transaction tr, string name)
    {
        return CivilApplication.ActiveDocument.GetSurfaceIds().Cast<ObjectId>().FirstOrDefault(id => ((CivilSurface)tr.GetObject(id, OpenMode.ForRead)).Name == name);
    }
    static ObjectId Layer(Transaction tr, string name, short color, bool off = false)
    {
        var db = AcApp.DocumentManager.MdiActiveDocument.Database; var lt = (LayerTable)tr.GetObject(db.LayerTableId, OpenMode.ForRead);
        Require(!lt.Has(name), "Layer already exists: " + name); lt.UpgradeOpen(); var layer = new LayerTableRecord { Name = name, Color = Color.FromColorIndex(ColorMethod.ByAci, color), IsOff = off };
        var id = lt.Add(layer); tr.AddNewlyCreatedDBObject(layer, true); return id;
    }
    static void Display(object style, string method, string component, short color, bool visible)
    {
        var m = style.GetType().GetMethods().Single(x => x.Name == method && x.GetParameters().Length == 1);
        var arg = Enum.Parse(m.GetParameters()[0].ParameterType, component); var display = m.Invoke(style, new[] { arg });
        display.GetType().GetProperty("Visible").SetValue(display, visible);
        display.GetType().GetProperty("Color").SetValue(display, Color.FromColorIndex(ColorMethod.ByAci, color));
    }
    static void ValidateMesh(MeshInput m)
    {
        Require(m.Vertices.Length >= 3 && m.Faces.Length > 0 && m.Vertices.Length <= 100000 && m.Faces.Length <= 200000, "Invalid mesh size");
        foreach (var v in m.Vertices) P(v);
        foreach (var f in m.Faces) { Require(f.Length == 3 && f.All(i => i >= 0 && i < m.Vertices.Length) && f.Distinct().Count() == 3, "Invalid face indices"); var a = P(m.Vertices[f[0]]); var b = P(m.Vertices[f[1]]); var c = P(m.Vertices[f[2]]); Require(Math.Abs((b.X - a.X) * (c.Y - a.Y) - (b.Y - a.Y) * (c.X - a.X)) > 1e-12, "Degenerate XY face"); }
        Require(m.ColorAci > 0 && m.ColorAci < 256, "Invalid ACI color");
    }
    static ObjectId AddMesh(Transaction tr, MeshInput mesh, string prefix)
    {
        Require(mesh.Name.StartsWith(prefix, StringComparison.Ordinal), "Surface outside namespace"); ValidateMesh(mesh);
        Require(FindSurface(tr, mesh.Name).IsNull, "Surface already exists: " + mesh.Name);
        var db = AcApp.DocumentManager.MdiActiveDocument.Database; var cd = CivilApplication.ActiveDocument;
        var layer = Layer(tr, mesh.Name, mesh.ColorAci);
        var id = TinSurface.Create(db, mesh.Name); var tin = (TinSurface)tr.GetObject(id, OpenMode.ForWrite);
        tin.LayerId = layer; tin.Description = "API practice surface: explicit input mesh; no engineering approval.";
        var template = (SurfaceStyle)tr.GetObject(cd.Styles.SurfaceStyles[0], OpenMode.ForRead); var styleId = template.CopyAsSibling(mesh.Name + "_STYLE");
        var style = tr.GetObject(styleId, OpenMode.ForWrite);
        foreach (var method in new[] { "GetDisplayStylePlan", "GetDisplayStyleModel" })
        {
            Display(style, method, "Triangles", mesh.ColorAci, true); Display(style, method, "Boundary", mesh.ColorAci, true);
            foreach (var component in new[] { "MajorContour", "MinorContour", "Points" }) Display(style, method, component, mesh.ColorAci, false);
        }
        tin.StyleId = styleId;
        var edges = new HashSet<(int, int)>(); foreach (var f in mesh.Faces) for (int i = 0; i < 3; i++) { int a = f[i], b = f[(i + 1) % 3]; edges.Add(a < b ? (a, b) : (b, a)); }
        tin.DrawingObjectsDefinition.AddFrom3DFaces(new Point3dCollection(mesh.Vertices.Select(P).ToArray()), edges.Select(e => new KeyValuePair<int, int>(e.Item1, e.Item2)), "Explicit mesh edges from analytical clipping");
        tin.AutoRebuild = true; tin.Rebuild();
        // Check the native interpolant, not just vertex counts.
        foreach (var v in mesh.Vertices) { var p = P(v); Require(Math.Abs(tin.FindElevationAtXY(p.X, p.Y) - p.Z) < 1e-6, "Native surface changed input vertex"); }
        foreach (var f in mesh.Faces) { var p = f.Select(i => P(mesh.Vertices[i])).ToArray(); double x = p.Average(q => q.X), y = p.Average(q => q.Y), z = p.Average(q => q.Z); Require(Math.Abs(tin.FindElevationAtXY(x, y) - z) < 1e-6, "Native surface changed face plane"); }
        return id;
    }
    public static object Build(Request r)
    {
        Guard(r); Require(r.Meshes.Length > 0 && r.Meshes.Length <= 10, "Supply 1-10 design meshes");
        var doc = AcApp.DocumentManager.MdiActiveDocument; using var tr = doc.Database.TransactionManager.StartTransaction();
        foreach (var m in r.Meshes) { ValidateMesh(m); Require(FindSurface(tr, m.Name).IsNull && FindSurface(tr, m.Name + "_VOLUME").IsNull, "Output already exists"); }
        var baseId = FindSurface(tr, r.BaseSurface);
        if (r.BaseMesh != null) { Require(baseId.IsNull && r.BaseMesh.Name == r.BaseSurface, "New base conflicts with drawing"); baseId = AddMesh(tr, r.BaseMesh, r.NamePrefix); }
        Require(!baseId.IsNull, "Base surface not found"); var basis = (TinSurface)tr.GetObject(baseId, OpenMode.ForRead);
        Require(!basis.IsOutOfDate, "Base surface needs rebuild");
        if (r.ExpectedBaseTriangleCount > 0) Require(basis.GetTriangles(false).Count == r.ExpectedBaseTriangleCount, "Base triangle count changed");
        foreach (var v in r.BaseCheckPoints) { var p = P(v); Require(Math.Abs(basis.FindElevationAtXY(p.X, p.Y) - p.Z) < 1e-6, "Base check elevation changed"); }
        var created = new List<object>();
        foreach (var mesh in r.Meshes)
        {
            var designId = AddMesh(tr, mesh, r.NamePrefix); string name = mesh.Name + "_VOLUME";
            var volumeId = TinVolumeSurface.Create(name, baseId, designId); var volume = (TinVolumeSurface)tr.GetObject(volumeId, OpenMode.ForWrite);
            volume.CutFactor = 1; volume.FillFactor = 1; volume.AutoRebuild = true; volume.Rebuild(); volume.LayerId = Layer(tr, name, 8, true);
            var v = volume.GetVolumeProperties();
            Require(mesh.Expected.ContainsKey("cut_m3") && mesh.Expected.ContainsKey("fill_m3"), "Expected independent volumes required");
            Require(Math.Abs(v.UnadjustedCutVolume - mesh.Expected["cut_m3"]) <= r.VolumeTolerance && Math.Abs(v.UnadjustedFillVolume - mesh.Expected["fill_m3"]) <= r.VolumeTolerance, "Native volumes differ from independent calculation");
            created.Add(new { name = mesh.Name, surfaceHandle = designId.Handle.ToString(), volumeHandle = volumeId.Handle.ToString(), cut = v.UnadjustedCutVolume, fill = v.UnadjustedFillVolume });
        }
        tr.Commit(); doc.Editor.Regen(); return new { created };
    }
    public static object Sections(Request r)
    {
        Guard(r); var s = r.Sections; Require(s != null && s.AlignmentName.StartsWith(r.NamePrefix) && s.GroupName.StartsWith(r.NamePrefix), "Names must use namespace");
        var start = P(s.Start); var end = P(s.End); var delta = end - start; double length = Math.Sqrt(delta.X * delta.X + delta.Y * delta.Y);
        Require(length > 0 && s.Spacing > 0 && s.HalfWidth > 0 && double.IsFinite(s.Spacing) && double.IsFinite(s.HalfWidth) && length / s.Spacing <= 500 && s.ViewEvery >= 1, "Invalid section dimensions or count");
        Require(s.ElevationRange.Length == 2 && s.ElevationRange.All(double.IsFinite) && s.ElevationRange[1] > s.ElevationRange[0], "Invalid elevation range"); var origin = P(s.ViewOrigin);
        var doc = AcApp.DocumentManager.MdiActiveDocument; var cd = CivilApplication.ActiveDocument; using var tr = doc.Database.TransactionManager.StartTransaction();
        Require(!cd.GetAlignmentIds().Cast<ObjectId>().Any(id => ((Alignment)tr.GetObject(id, OpenMode.ForRead)).Name == s.AlignmentName), "Alignment already exists");
        var ids = s.Surfaces.Select(n => FindSurface(tr, n)).ToArray(); Require(ids.Length >= 2 && ids.All(id => !id.IsNull) && ids.Distinct().Count() == ids.Length, "Missing/duplicate section surfaces");
        var layer = Layer(tr, s.AlignmentName, 6); var alignId = Alignment.Create(cd, s.AlignmentName, ObjectId.Null, layer, cd.Styles.AlignmentStyles[0], cd.Styles.LabelSetStyles.AlignmentLabelSetStyles[0]);
        var alignment = (Alignment)tr.GetObject(alignId, OpenMode.ForWrite); alignment.Entities.AddFixedLine(start, end);
        var groupId = SampleLineGroup.Create(s.GroupName, alignId); var group = (SampleLineGroup)tr.GetObject(groupId, OpenMode.ForWrite);
        var sectionStyleIds = new Dictionary<ObjectId, ObjectId>(); short[] colors = { 8, 1, 5, 3, 6 };
        for (int i = 0; i < ids.Length; i++)
        {
            var original = (SectionStyle)tr.GetObject(cd.Styles.SectionStyles[0], OpenMode.ForRead); var styleId = original.CopyAsSibling(s.GroupName + "_STYLE_" + i); var style = (SectionStyle)tr.GetObject(styleId, OpenMode.ForWrite);
            var method = style.GetType().GetMethod("GetDisplayStyleSection"); var enumType = method.GetParameters()[0].ParameterType;
            foreach (string component in Enum.GetNames(enumType)) Display(style, "GetDisplayStyleSection", component, colors[i % colors.Length], component.Contains("Segment"));
            sectionStyleIds[ids[i]] = styleId;
        }
        foreach (SectionSource source in group.GetSectionSources())
        {
            source.IsSampled = ids.Contains(source.SourceId);
            if (source.IsSampled) source.StyleId = sectionStyleIds[source.SourceId];
        }
        // Own the graph style so existing drawing styles are never changed.
        var graphTemplate = (SectionViewStyle)tr.GetObject(cd.Styles.SectionViewStyles[0], OpenMode.ForRead);
        var graphId = graphTemplate.CopyAsSibling(s.GroupName + "_GRAPH");
        var graph = (SectionViewStyle)tr.GetObject(graphId, OpenMode.ForWrite); graph.GraphStyle.VerticalExaggeration = 1;
        graph.GraphStyle.TitleStyle.Text = "<[Section View Station(Um|FS|P2|RN|Sn|OF|AP|B2|TP|EN|W0|DZY|GC|UN)]> m";
        MetricAxis(graph.BottomAxis, "Offset", "Offset"); MetricAxis(graph.TopAxis, "Offset", "Offset");
        MetricAxis(graph.LeftAxis, "Elevation", "Elevation"); MetricAxis(graph.RightAxis, "Elevation", "Elevation");
        MetricAxis(graph.CenterAxis, "Elevation", "Elevation");
        var model = (BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(doc.Database), OpenMode.ForWrite);
        double ux = delta.X / length, uy = delta.Y / length; int n = (int)Math.Floor(length / s.Spacing); var stations = Enumerable.Range(0, n + 1).Select(i => i * s.Spacing).ToList(); if (length - stations.Last() > 1e-8) stations.Add(length);
        var handles = new List<object>(); int viewIndex = 0;
        for (int i = 0; i < stations.Count; i++)
        {
            double station = stations[i], x = start.X + ux * station, y = start.Y + uy * station;
            var points = new Point2dCollection(new[] { new Point2d(x - uy * s.HalfWidth, y + ux * s.HalfWidth), new Point2d(x + uy * s.HalfWidth, y - ux * s.HalfWidth) });
            var id = SampleLine.Create(s.GroupName + "_" + i.ToString("D3"), groupId, points); var line = (SampleLine)tr.GetObject(id, OpenMode.ForWrite); line.LayerId = layer; line.StyleId = cd.Styles.SampleLineStyles[0]; line.LockToStation = true;
            ObjectId viewId = ObjectId.Null;
            if (i % s.ViewEvery == 0 || i == stations.Count - 1)
            {
                var location = new Point3d(origin.X + (viewIndex % 4) * (2 * s.HalfWidth + 12), origin.Y - (viewIndex / 4) * Math.Max(18, s.ElevationRange[1] - s.ElevationRange[0] + 8), 0);
                viewId = SectionView.Create(s.GroupName + "_VIEW_" + i.ToString("D3"), id, location); var view = (SectionView)tr.GetObject(viewId, OpenMode.ForWrite);
                view.StyleId = graphId; view.LayerId = layer; view.IsOffsetRangeAutomatic = false; view.OffsetLeft = -s.HalfWidth; view.OffsetRight = s.HalfWidth; view.IsElevationRangeAutomatic = false; view.ElevationMin = s.ElevationRange[0]; view.ElevationMax = s.ElevationRange[1]; viewIndex++;
                var ext = view.GeometricExtents;
                var label = new DBText { TextString = "STA " + station.ToString("0.000", System.Globalization.CultureInfo.InvariantCulture) + " m | H=V", Height = 0.45, Position = new Point3d(ext.MinPoint.X, ext.MaxPoint.Y + 0.7, 0), LayerId = layer, Color = Color.FromColorIndex(ColorMethod.ByAci, 7) };
                model.AppendEntity(label); tr.AddNewlyCreatedDBObject(label, true);
            }
            handles.Add(new { station, sampleLine = id.Handle.ToString(), view = viewId.IsNull ? null : viewId.Handle.ToString() });
        }
        tr.Commit(); doc.Editor.Regen(); return new { alignment = alignId.Handle.ToString(), group = groupId.Handle.ToString(), sampleLines = handles };
    }
    public static object Audit(Request r)
    {
        // An audit must remain available to diagnose incompatible drawing units.
        Guard(r, requireMetric: false); var doc = AcApp.DocumentManager.MdiActiveDocument; var cd = CivilApplication.ActiveDocument; using var tr = doc.Database.TransactionManager.StartTransaction();
        var surfaces = new List<object>(); foreach (ObjectId id in cd.GetSurfaceIds())
        {
            var surface = (CivilSurface)tr.GetObject(id, OpenMode.ForRead); var triangles = new List<double[][]>();
            if (surface is TinSurface tin) foreach (TinSurfaceTriangle t in tin.GetTriangles(false)) triangles.Add(new[] { XYZ(t.Vertex1.Location), XYZ(t.Vertex2.Location), XYZ(t.Vertex3.Location) });
            object volume = null; if (surface is TinVolumeSurface vs) { var v = vs.GetVolumeProperties(); volume = new { cut = v.UnadjustedCutVolume, fill = v.UnadjustedFillVolume, cutFactor = v.CutFactor, fillFactor = v.FillFactor, baseHandle = v.BaseSurface.Handle.ToString(), comparisonHandle = v.ComparisonSurface.Handle.ToString() }; }
            surfaces.Add(new { name = surface.Name, handle = id.Handle.ToString(), isOutOfDate = surface.IsOutOfDate, autoRebuild = surface.AutoRebuild, isReference = surface.IsReferenceObject, triangles, volume });
        }
        var graphStyles = new HashSet<ObjectId>();
        var alignments = new List<object>(); foreach (ObjectId id in cd.GetAlignmentIds())
        {
            var a = (Alignment)tr.GetObject(id, OpenMode.ForRead); var groups = new List<object>(); foreach (ObjectId gid in a.GetSampleLineGroupIds())
            {
                var g = (SampleLineGroup)tr.GetObject(gid, OpenMode.ForRead); var lines = new List<object>(); foreach (ObjectId lid in g.GetSampleLineIds())
                {
                    var line = (SampleLine)tr.GetObject(lid, OpenMode.ForRead); var sections = new List<object>(); foreach (ObjectId sid in line.GetSectionIds())
                    {
                        var section = (Autodesk.Civil.DatabaseServices.Section)tr.GetObject(sid, OpenMode.ForRead); var pts = new List<object>(); foreach (SectionPoint p in section.SectionPoints) pts.Add(new { location = XYZ(p.Location), segmentTo = p.SegmentTo });
                        sections.Add(new { name = section.Name, handle = sid.Handle.ToString(), source = section.SourceName, station = section.Station, updateMode = section.UpdateMode.ToString(), points = pts });
                    }
                    var viewIds = line.GetSectionViewIds().Cast<ObjectId>().ToArray();
                    foreach (var viewId in viewIds) graphStyles.Add(((SectionView)tr.GetObject(viewId, OpenMode.ForRead)).StyleId);
                    lines.Add(new { name = line.Name, handle = lid.Handle.ToString(), station = line.Station, sections, views = viewIds.Select(v => v.Handle.ToString()).ToArray() });
                }
                groups.Add(new { name = g.Name, handle = gid.Handle.ToString(), lines });
            }
            alignments.Add(new { name = a.Name, handle = id.Handle.ToString(), start = a.StartingStation, end = a.EndingStation, groups });
        }
        var cogo = cd.CogoPoints.Cast<ObjectId>().Select(id => { var p = (CogoPoint)tr.GetObject(id, OpenMode.ForRead); return new { number = p.PointNumber, e = p.Easting, n = p.Northing, z = p.Elevation, description = p.RawDescription }; }).ToArray();
        var civilUnits = cd.Settings.DrawingSettings.UnitZoneSettings.DrawingUnits;
        var sectionViewStyles = graphStyles.OrderBy(id => id.Handle.Value).Select(id => GraphUnits((SectionViewStyle)tr.GetObject(id, OpenMode.ForRead))).ToArray();
        tr.Commit(); return new { utc = DateTime.UtcNow, drawing = doc.Name, units = doc.Database.Insunits.ToString(), civilUnits = civilUnits.ToString(),
            metricDrawingUnits = doc.Database.Insunits == UnitsValue.Meters && civilUnits == DrawingUnitType.Meters,
            cogo, surfaces, alignments, sectionViewStyles };
    }
}
