using System.Text.Json.Serialization;

namespace Cdcrd.BeamngExport;

public sealed class CivilSnapshot
{
    [JsonPropertyName("schema")]
    public string Schema { get; init; } = "cdcrd.civil3d.snapshot/1";

    [JsonPropertyName("units")]
    public string Units { get; init; } = "m";

    [JsonPropertyName("surfaces")]
    public required SnapshotSurfaces Surfaces { get; init; }

    [JsonPropertyName("alignment")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public AlignmentSnapshot? Alignment { get; init; }

    [JsonPropertyName("sources")]
    public Dictionary<string, string> Sources { get; init; } = [];

    [JsonPropertyName("scene_meshes")]
    public List<SceneMeshSnapshot> SceneMeshes { get; init; } = [];

    [JsonPropertyName("scene_skipped")]
    public List<string> SceneSkipped { get; init; } = [];
}

public sealed class SceneMeshSnapshot
{
    public required string Handle { get; init; }
    public required string Layer { get; init; }
    public required string Kind { get; init; }
    public required double[] Color { get; init; }
    public required List<double[]> Vertices { get; init; }
    public required List<int[]> Triangles { get; init; }
}

public sealed class SnapshotSurfaces
{
    [JsonPropertyName("terrain")]
    public required SurfaceSnapshot Terrain { get; init; }

    [JsonPropertyName("road")]
    public required SurfaceSnapshot Road { get; init; }
}

public sealed class SurfaceSnapshot
{
    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("vertices_abs_m")]
    public List<double[]> VerticesAbsoluteMetres { get; init; } = [];

    [JsonPropertyName("triangles")]
    public List<int[]> Triangles { get; init; } = [];

    // Each pair is an edge of the visible mesh used by exactly one triangle.
    // This includes outer edges and holes without adding entities to the DWG.
    [JsonPropertyName("boundary_edges")]
    public List<int[]> BoundaryEdges { get; init; } = [];

    [JsonPropertyName("triangles_include_invisible")]
    public bool TrianglesIncludeInvisible { get; init; }

    [JsonPropertyName("boundary_policy")]
    public string BoundaryPolicy { get; init; } = "visible_triangles_only";
}

public sealed class AlignmentSnapshot
{
    [JsonPropertyName("name")]
    public required string Name { get; init; }

    [JsonPropertyName("nodes_abs_m")]
    public List<double[]> NodesAbsoluteMetres { get; init; } = [];

    [JsonPropertyName("station_m")]
    public List<double> StationsMetres { get; init; } = [];

    [JsonPropertyName("sample_step_m")]
    public double SampleStepMetres { get; init; } = 5;

    [JsonPropertyName("width_source")]
    public string WidthSource { get; init; } = "user_constant_for_centerline_only";

    [JsonPropertyName("elevation_source")]
    public required string ElevationSource { get; init; }
}
