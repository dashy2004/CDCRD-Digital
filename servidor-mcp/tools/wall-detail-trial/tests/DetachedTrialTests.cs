using CDCRD.WallDetailTrial;
using Xunit;

public sealed class DetachedTrialTests
{
    public sealed class EndZone { public double ConfinedPrefTieArea { get; set; } = 129.032; }
    public sealed class Line
    {
        // Match the installed native line contract: endpoints are public fields.
        public object Pt1 = new();
        public object Pt2 = new();
    }
    public sealed class Data
    {
        public object StartZone { get; set; } = new EndZone();
        public object EndZone { get; set; } = new EndZone();
        public object MidZone { get; set; } = new();
        public Line CLine { get; set; } = new();
    }
    public sealed class Leg
    {
        public object? PierSection { get; set; }
        public bool InEditMode { get; set; }
        public Data Data { get; set; } = new();
        public Data GetLegData() => Data;
    }

    [Fact] public void IndependentCloneAccepted() => DetachedTrial.RequireDetached(new Leg(), new Leg());
    [Fact] public void TieAreaChangesBothDetachedEndsAndPreservesSource()
    {
        var original = new Leg(); var clone = new Leg();
        DetachedTrial.RequireDetached(original, clone);
        DetachedTrial.SetBothEndTieAreas(clone, 113.0999984741211);
        Assert.Equal(113.0999984741211, ((EndZone)clone.Data.StartZone).ConfinedPrefTieArea);
        Assert.Equal(113.0999984741211, ((EndZone)clone.Data.EndZone).ConfinedPrefTieArea);
        Assert.Equal(129.032, ((EndZone)original.Data.StartZone).ConfinedPrefTieArea);
        Assert.Equal(129.032, ((EndZone)original.Data.EndZone).ConfinedPrefTieArea);
    }
    [Theory]
    [InlineData(0)][InlineData(-1)][InlineData(double.NaN)][InlineData(double.PositiveInfinity)]
    public void InvalidTieAreasRejectedBeforeChangingEitherEnd(double area)
    {
        var clone = new Leg();
        Assert.Throws<InvalidOperationException>(() => DetachedTrial.SetBothEndTieAreas(clone, area));
        Assert.Equal(129.032, ((EndZone)clone.Data.StartZone).ConfinedPrefTieArea);
        Assert.Equal(129.032, ((EndZone)clone.Data.EndZone).ConfinedPrefTieArea);
    }
    [Fact] public void SourceIdentityRejected()
    {
        var a = new Leg();
        Assert.Throws<InvalidOperationException>(() => DetachedTrial.RequireDetached(a, a));
    }
    [Fact] public void ParentAttachmentRejected() => Assert.Throws<InvalidOperationException>(() =>
        DetachedTrial.RequireDetached(new Leg(), new Leg { PierSection = new object() }));
    [Fact] public void EditModeRejected() => Assert.Throws<InvalidOperationException>(() =>
        DetachedTrial.RequireDetached(new Leg(), new Leg { InEditMode = true }));
    [Theory]
    [InlineData("Data")][InlineData("Start")][InlineData("End")][InlineData("Mid")]
    [InlineData("Line")][InlineData("Point1")][InlineData("Point2")]
    [InlineData("CrossPointAlias")][InlineData("CrossAlias")]
    public void SharedMutableStateRejected(string node)
    {
        var a = new Leg(); var b = new Leg();
        switch (node)
        {
            case "Data": b.Data = a.Data; break;
            case "Start": b.Data.StartZone = a.Data.StartZone; break;
            case "End": b.Data.EndZone = a.Data.EndZone; break;
            case "Mid": b.Data.MidZone = a.Data.MidZone; break;
            case "Line": b.Data.CLine = a.Data.CLine; break;
            case "Point1": b.Data.CLine.Pt1 = a.Data.CLine.Pt1; break;
            case "Point2": b.Data.CLine.Pt2 = a.Data.CLine.Pt2; break;
            case "CrossPointAlias": b.Data.CLine.Pt2 = a.Data.CLine.Pt1; break;
            case "CrossAlias": b.Data.EndZone = a.Data.StartZone; break;
        }
        var error = Assert.Throws<InvalidOperationException>(() => DetachedTrial.RequireDetached(a, b));
        Assert.Equal("Clone shares mutable geometry or reinforcing data.", error.Message);
    }
    [Theory]
    [InlineData("Pt1")][InlineData("Pt2")]
    public void MissingEndpointRejected(string point)
    {
        var a = new Leg(); var b = new Leg();
        if (point == "Pt1") b.Data.CLine.Pt1 = null!;
        else b.Data.CLine.Pt2 = null!;
        var error = Assert.Throws<InvalidOperationException>(() => DetachedTrial.RequireDetached(a, b));
        Assert.Equal("Missing native field " + point, error.Message);
    }
    [Fact] public void ExistingLockIsNotReplacedOrDeleted()
    {
        string dir = Path.Combine(Path.GetTempPath(), "wall-trial-" + Guid.NewGuid());
        Directory.CreateDirectory(dir);
        string path = Path.Combine(dir, "etabs.lock");
        File.WriteAllText(Path.Combine(dir, "trial-options.json"), System.Text.Json.JsonSerializer.Serialize(new { ResourceLockPath = path }));
        File.WriteAllText(path, "other owner");
        try
        {
            Assert.Throws<IOException>(() => TrialOwnership.Acquire(dir, "test.EDB", 42, DateTime.UtcNow));
            Assert.Equal("other owner", File.ReadAllText(path));
        }
        finally { Directory.Delete(dir, true); }
    }
    [Fact] public void OwnedLockReleasedAtEnd()
    {
        string dir = Path.Combine(Path.GetTempPath(), "wall-trial-" + Guid.NewGuid());
        Directory.CreateDirectory(dir);
        string path = Path.Combine(dir, "etabs.lock");
        File.WriteAllText(Path.Combine(dir, "trial-options.json"), System.Text.Json.JsonSerializer.Serialize(new { ResourceLockPath = path }));
        try
        {
            using (TrialOwnership.Acquire(dir, "test.EDB", 42, DateTime.UtcNow)) Assert.True(File.Exists(path));
            Assert.False(File.Exists(path));
        }
        finally { Directory.Delete(dir, true); }
    }
}
