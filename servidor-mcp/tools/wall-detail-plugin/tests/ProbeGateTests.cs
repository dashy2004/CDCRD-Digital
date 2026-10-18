using CDCRD.WallDetailProbe;
using Xunit;

public sealed class ProbeGateTests
{
    private static readonly DateTimeOffset Started = DateTimeOffset.Parse("2026-01-01T00:00:00Z");
    private static ProbeOptions Options => new(@"C:\Synthetic\copy.edb", 123, Started);

    [Fact]
    public void ExactAnalyzedFixtureIsAccepted() =>
        ProbeGate.Validate(Options, @"c:\SYNTHETIC\copy.EDB", 123, Started, true);

    [Theory]
    [InlineData(0)]
    [InlineData(124)]
    public void WrongProcessIsRejected(int pid) =>
        Assert.Throws<InvalidOperationException>(() => ProbeGate.Validate(Options, Options.ExpectedModel, pid, Started, true));

    [Fact]
    public void ReusedPidIsRejected() =>
        Assert.Throws<InvalidOperationException>(() => ProbeGate.Validate(Options, Options.ExpectedModel, 123, Started.AddSeconds(1), true));

    [Fact]
    public void UnanalyzedModelIsRejected() =>
        Assert.Throws<InvalidOperationException>(() => ProbeGate.Validate(Options, Options.ExpectedModel, 123, Started, false));

    [Theory]
    [InlineData(@"C:\Synthetic\other.edb")]
    [InlineData(@"C:\Original\copy.edb")]
    [InlineData(@"C:\Synthetic\copy.$et")]
    public void WrongDocumentIsRejected(string actual) =>
        Assert.Throws<InvalidOperationException>(() => ProbeGate.Validate(Options, actual, 123, Started, true));

    [Theory]
    [InlineData("copy.edb")]
    [InlineData(@"C:\Synthetic\copy.$et")]
    public void UnsafeAuthorizationIsRejected(string expected) =>
        Assert.Throws<InvalidOperationException>(() => ProbeGate.Validate(Options with { ExpectedModel = expected }, expected, 123, Started, true));

    [Fact]
    public void MissingAuthorizationIsRejected() =>
        Assert.Throws<ArgumentNullException>(() => ProbeGate.Validate(null!, Options.ExpectedModel, 123, Started, true));
}
