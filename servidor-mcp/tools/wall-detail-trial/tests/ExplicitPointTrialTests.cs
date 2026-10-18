using System.Text.Json;
using CDCRD.WallDetailTrial;
using Xunit;
using Axis = CDCRD.WallDetailTrial.ExplicitPointTrial.Axis;

public sealed class ExplicitPointTrialTests
{
    [Fact] public void OrderingDoesNotChangePhysicalLayout()
    {
        Axis[] plan = [new(-34, 250, 16), new(34, 250, 16), new(30, 62, 16)];
        ExplicitPointTrial.RequireSameLayout(plan, plan.Reverse().ToArray());
    }
    [Theory]
    [InlineData(42, 250, 16)][InlineData(34, 275, 16)][InlineData(34, 250, 20)]
    [InlineData(double.NaN, 250, 16)][InlineData(34, double.PositiveInfinity, 16)]
    [InlineData(34, 250, 0)][InlineData(10001, 250, 16)]
    public void ShiftWrongDiameterOrInvalidCoordinatesRejected(double x, double y, double dia) =>
        Assert.Throws<InvalidOperationException>(() => ExplicitPointTrial.RequireSameLayout(
            [new Axis(34, 250, 16)], [new Axis(x, y, dia)]));
    [Fact] public void LostEndBarsRejected() => Assert.Throws<InvalidOperationException>(() =>
        ExplicitPointTrial.RequireSameLayout([new Axis(34, 250, 16), new Axis(30, 62, 16)], [new Axis(34, 250, 16)]));
    [Fact] public void DuplicateCoordinatesRejectedEvenWithDifferentDiameters() => Assert.Throws<InvalidOperationException>(() =>
        ExplicitPointTrial.RequireSameLayout([new Axis(34, 250, 16), new Axis(34, 250, 20)], [new Axis(34, 250, 16)]));
    [Fact] public void TwoPlanBarsCannotReuseOneCageMatch() => Assert.Throws<InvalidOperationException>(() =>
        ExplicitPointTrial.RequireSameLayout([new Axis(0, 0, 16), new Axis(0.000015, 0, 16)],
            [new Axis(0.0000075, 0, 16), new Axis(1, 1, 16)]));
    [Fact] public void EmptyInventoryRejected() => Assert.Throws<InvalidOperationException>(() =>
        ExplicitPointTrial.RequireSameLayout([], []));

    private static string Cage(double endX = 34, double endZ = 3000, bool arc = false, double diameter = 16)
    {
        var points = new[] { new { X = 34.0, Y = 250.0, Z = 25.0, OnArc = false },
            new { X = endX, Y = 250.0, Z = endZ, OnArc = arc } };
        return JsonSerializer.Serialize(new[] { new { Dia = diameter,
            PLine = new { Points = new Dictionary<string, object> { ["$values"] = points } } } });
    }
    [Fact] public void StraightCageAxesReadWithoutClaimingEndpointApproval()
    {
        var axes = ExplicitPointTrial.CageAxes(Cage());
        Assert.Equal(new Axis(34, 250, 16), Assert.Single(axes));
    }
    [Theory]
    [InlineData(42, 3000, false, 16)][InlineData(34, 25, false, 16)]
    [InlineData(34, 3000, true, 16)][InlineData(34, 3000, false, 0)]
    public void NonverticalDegenerateCurvedOrInvalidCageRejected(double x, double z, bool arc, double diameter) =>
        Assert.Throws<InvalidOperationException>(() => ExplicitPointTrial.CageAxes(Cage(x, z, arc, diameter)));
}
