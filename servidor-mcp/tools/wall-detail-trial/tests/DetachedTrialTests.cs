using CDCRD.WallDetailTrial;
using Xunit;

public sealed class DetachedTrialTests
{
    public sealed class Line
    {
        public object Pt1 { get; set; } = new();
        public object Pt2 { get; set; } = new();
    }
    public sealed class Data
    {
        public object StartZone { get; set; } = new();
        public object EndZone { get; set; } = new();
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
    [InlineData("Line")][InlineData("Point")][InlineData("CrossAlias")]
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
            case "Point": b.Data.CLine.Pt2 = a.Data.CLine.Pt2; break;
            case "CrossAlias": b.Data.EndZone = a.Data.StartZone; break;
        }
        Assert.Throws<InvalidOperationException>(() => DetachedTrial.RequireDetached(a, b));
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
