using CDCRD.WallDetailProbe;
using Xunit;

public sealed class ContextLeaseTests
{
    [Fact]
    public void RestoreRunsOnceAfterSuccess()
    {
        int state = 10, restored = 0;
        var scope = new ContextLease(() => state = 20, () => { state = 10; restored++; });
        Assert.Equal(20, state);
        scope.Dispose(); scope.Dispose();
        Assert.Equal(10, state);
        Assert.Equal(1, restored);
    }

    [Fact]
    public void FailedPartialActivationRestoresCaller()
    {
        int state = 10;
        Assert.Throws<InvalidOperationException>(() => new ContextLease(
            () => { state = 20; throw new InvalidOperationException(); }, () => state = 10));
        Assert.Equal(10, state);
    }

    [Fact]
    public void FailedCaptureRestoresCaller()
    {
        int state = 10;
        Assert.Throws<InvalidOperationException>((Action)(() =>
        {
            using var scope = new ContextLease(() => state = 20, () => state = 10);
            throw new InvalidOperationException();
        }));
        Assert.Equal(10, state);
    }

    [Fact]
    public void RestoreFailureIsNotHidden()
    {
        var scope = new ContextLease(() => { }, () => throw new InvalidOperationException());
        Assert.Throws<InvalidOperationException>(() => scope.Dispose());
    }

    [Fact]
    public void CoupledDesignSetterCannotOverwriteOriginalCommonContext()
    {
        int common = 10, design = 20;
        using (new ContextLease(() => { common = 30; design = 30; },
                   () => { design = 20; common = 20; }, () => common = 10))
            Assert.Equal(30, common);
        Assert.Equal(10, common);
        Assert.Equal(20, design);
    }

    [Fact]
    public void LastRestoreRunsEvenWhenFirstRestoreFails()
    {
        int common = 10;
        var scope = new ContextLease(() => common = 30,
            () => throw new InvalidOperationException(), () => common = 10);
        Assert.Throws<InvalidOperationException>(() => scope.Dispose());
        Assert.Equal(10, common);
    }
}
