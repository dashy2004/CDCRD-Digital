using System;
using System.Collections.Generic;
namespace Cdcrd.Earthworks;

public sealed class MeshInput
{
    public string Name { get; set; } = "";
    public double[][] Vertices { get; set; } = Array.Empty<double[]>();
    public int[][] Faces { get; set; } = Array.Empty<int[]>();
    public short ColorAci { get; set; } = 3;
    public Dictionary<string, double> Expected { get; set; } = new();
}
public sealed class SectionInput
{
    public string AlignmentName { get; set; } = "";
    public string GroupName { get; set; } = "";
    public double[] Start { get; set; } = Array.Empty<double>();
    public double[] End { get; set; } = Array.Empty<double>();
    public double HalfWidth { get; set; }
    public double Spacing { get; set; } = 1;
    public int ViewEvery { get; set; } = 2;
    public double[] ViewOrigin { get; set; } = Array.Empty<double>();
    public double[] ElevationRange { get; set; } = Array.Empty<double>();
    public string[] Surfaces { get; set; } = Array.Empty<string>();
}
public sealed class Request
{
    public string Action { get; set; } = "audit";
    public string ExpectedDrawing { get; set; } = "";
    public string OutputDirectory { get; set; } = "";
    public string RunId { get; set; } = "";
    public string NamePrefix { get; set; } = "CDCRD_";
    public string BaseSurface { get; set; } = "";
    public MeshInput BaseMesh { get; set; }
    public double[][] BaseCheckPoints { get; set; } = Array.Empty<double[]>();
    public int ExpectedBaseTriangleCount { get; set; }
    public int ExpectedCogoCount { get; set; } = -1;
    public MeshInput[] Meshes { get; set; } = Array.Empty<MeshInput>();
    public SectionInput Sections { get; set; }
    public double VolumeTolerance { get; set; } = 0.0001;
}
