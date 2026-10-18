using CDCRD.WallDetailTrial;
using Xunit;

public sealed class TrialGeometryEvidenceTests
{
    [Fact]
    public void OpaqueNativeTypeLabelsCannotCountAsGeometry()
    {
        const string json = """{"$values":["CSI.NADetDesign.Rebars.cRebarPatternLineMultiLayer"]}""";
        Assert.Throws<InvalidOperationException>(() => TrialGeometryEvidence.RequireBarPoints(json));
        Assert.Throws<InvalidOperationException>(() => TrialGeometryEvidence.RequirePolylines(json));
    }

    [Fact]
    public void NumericBarPointsAccepted()
    {
        const string json = """{"$values":[{"X":40,"Y":60,"Dia":16},{"X":40,"Y":310,"Dia":16}]}""";
        Assert.Equal(2, TrialGeometryEvidence.RequireBarPoints(json));
    }

    [Theory]
    [InlineData("{\"$values\":[]}")]
    [InlineData("[{\"X\":0,\"Y\":0,\"Dia\":0}]")]
    [InlineData("[{\"X\":0,\"Y\":0}]")]
    [InlineData("[{\"X\":1e309,\"Y\":0,\"Dia\":16}]")]
    [InlineData("[{\"X\":\"40\",\"Y\":0,\"Dia\":16}]")]
    public void EmptyOrNonNumericGeometryRejected(string json) =>
        Assert.Throws<InvalidOperationException>(() => TrialGeometryEvidence.RequireBarPoints(json));

    [Fact]
    public void NumericPolylineRetainsCurvesWithoutApprovingTheirLength()
    {
        const string json = """{"$values":[{"Thickness":12,"Points":{"$values":[{"X":46,"Y":46,"OnArc":false},{"X":46,"Y":100,"OnArc":true}]}}]}""";
        Assert.Equal(1, TrialGeometryEvidence.RequirePolylines(json));
    }

    [Theory]
    [InlineData("[{\"Thickness\":12,\"Points\":[] }]")]
    [InlineData("[{\"Thickness\":12,\"Points\":[{\"X\":0,\"Y\":0}]}]")]
    [InlineData("[{\"Thickness\":0,\"Points\":[{\"X\":0,\"Y\":0},{\"X\":0,\"Y\":1}]}]")]
    public void IncompletePolylineRejected(string json) =>
        Assert.Throws<InvalidOperationException>(() => TrialGeometryEvidence.RequirePolylines(json));

    [Fact]
    public void CageSnapshotRequiresThreeDimensionalCoordinates()
    {
        const string good = """[{"Dia":16,"PLine":{"Points":[{"X":0,"Y":0,"Z":0},{"X":0,"Y":0,"Z":3000}]}}]""";
        TrialGeometryEvidence.RequireCage(good);
        Assert.Throws<InvalidOperationException>(() => TrialGeometryEvidence.RequireCage(good.Replace("\"Z\":3000", "\"W\":3000")));
    }
}
