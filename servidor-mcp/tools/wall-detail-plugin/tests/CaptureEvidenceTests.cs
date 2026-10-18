using CDCRD.WallDetailProbe;
using Xunit;

public sealed class CaptureEvidenceTests
{
    private static readonly string Id = "a0000000-0000-0000-0000-000000000001";
    private static WallSnapshot Wall() => new(Id, [new(0, 0, 0), new(4000, 0, 0), new(4000, 0, 3000), new(0, 0, 3000)]);

    [Fact]
    public void StaleImperialWrapperIsRetainedAsConflictNotUsedForScaling()
    {
        var units = CaptureEvidence.AssessUnits(9, 9, "N_mm_C", "lb, inch, F", "N, mm, C", 1, 1000);
        Assert.False(units.WrapperAgrees);
        Assert.True(units.NumericContextAgrees);
    }

    [Fact]
    public void ConsistentLabelsAndFactorsAreRecognizedWithoutApprovingBars()
    {
        var units = CaptureEvidence.AssessUnits(9, 9, "N_mm_C", "N, mm, C", "N, mm, C", 1, 1000);
        Assert.True(units.WrapperAgrees);
        Assert.True(units.NumericContextAgrees);
    }

    [Theory]
    [InlineData("lb, inch, F", 1, 1000)]
    [InlineData("N, mm, C", 0.0393700787, 39.3700787)]
    [InlineData("N, mm, C", double.NaN, 1000)]
    [InlineData("N, mm, C", 1, double.PositiveInfinity)]
    [InlineData(null, 1, 1000)]
    public void NumericUnitConflictDoesNotPass(string? context, double mm, double m)
    {
        Assert.False(CaptureEvidence.AssessUnits(9, 9, "N_mm_C", "N, mm, C", context, mm, m).NumericContextAgrees);
    }

    [Theory]
    [InlineData(6, 9, "N_mm_C")]
    [InlineData(9, 6, "N_mm_C")]
    [InlineData(9, 9, "kN_m_C")]
    [InlineData(9, 9, null)]
    public void UnsupportedBaseUnitsStillFailClosed(int database, int present, string? payload)
    {
        Assert.Throws<InvalidOperationException>(() => CaptureEvidence.AssessUnits(database, present, payload,
            "N, mm, C", "N, mm, C", 1, 1000));
    }

    [Fact]
    public void MatchingVerticesMayHaveDifferentOrder()
    {
        var wall = Wall();
        Assert.Equal(4, CaptureEvidence.MatchWalls([wall], [wall with { Vertices = wall.Vertices.Reverse().ToArray() }]));
    }

    [Fact]
    public void ScaleConflictIsRejectedWithoutAutomaticConversion()
    {
        var wall = Wall();
        var scaled = wall with { Vertices = wall.Vertices.Select(p => new Vertex(p.X / 25.4, p.Y / 25.4, p.Z / 25.4)).ToArray() };
        Assert.Throws<InvalidOperationException>(() => CaptureEvidence.MatchWalls([wall], [scaled]));
    }

    [Fact]
    public void MissingWallOrWrongGuidIsRejected()
    {
        Assert.Throws<InvalidOperationException>(() => CaptureEvidence.MatchWalls([Wall()], []));
        Assert.Throws<InvalidOperationException>(() => CaptureEvidence.MatchWalls([Wall()], [Wall() with { Guid = System.Guid.NewGuid().ToString() }]));
    }

    [Fact]
    public void DuplicateWallAndNonFiniteOrRepeatedVerticesAreRejected()
    {
        var wall = Wall();
        Assert.Throws<InvalidOperationException>(() => CaptureEvidence.MatchWalls([wall, wall], [wall, wall]));
        Assert.Throws<InvalidOperationException>(() => CaptureEvidence.MatchWalls([wall], [wall with { Vertices = [new(double.NaN, 0, 0), new(1, 0, 0), new(1, 1, 0)] }]));
        Assert.Throws<InvalidOperationException>(() => CaptureEvidence.MatchWalls([wall], [wall with { Vertices = [new(0, 0, 0), new(0, 0, 0), new(1, 1, 0)] }]));
    }
}
