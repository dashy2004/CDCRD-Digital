using CDCRD.WallDetailProbe;
using Xunit;

public sealed class NativeContextTests
{
    [Fact]
    public void PublicAccessorsActivateAndRestoreDistinctContextsWithoutPrivateMethod()
    {
        object common = new(), design = new(), wall = new();
        CSI.NADetDesign.xAppDSN.App = design;
        CSI.NADetBase.Common.xApp.App = common;
        CSI.CSiNAWallStackDesigner.xAppWD.App = wall;
        var assembly = typeof(NativeContextTests).Assembly;
        using (NativeDetailCapture.Activate(assembly, assembly, assembly))
        {
            Assert.Same(wall, CSI.NADetBase.Common.xApp.App);
            Assert.Same(wall, CSI.NADetDesign.xAppDSN.App);
        }
        Assert.Same(common, CSI.NADetBase.Common.xApp.App);
        Assert.Same(design, CSI.NADetDesign.xAppDSN.App);
    }

    [Fact]
    public void MissingWallContextFailsBeforeChangingEitherContext()
    {
        object common = new(), design = new();
        CSI.NADetDesign.xAppDSN.App = design;
        CSI.NADetBase.Common.xApp.App = common;
        CSI.CSiNAWallStackDesigner.xAppWD.App = null;
        var assembly = typeof(NativeContextTests).Assembly;
        Assert.Throws<InvalidOperationException>(() => NativeDetailCapture.Activate(assembly, assembly, assembly));
        Assert.Same(common, CSI.NADetBase.Common.xApp.App);
        Assert.Same(design, CSI.NADetDesign.xAppDSN.App);
    }
}

// Synthetic contract doubles, not CSI source. Deliberately no SetMeAsActiveApp.
namespace CSI.NADetBase.Common
{
    public static class xApp { public static object? App { get; set; } }
}
namespace CSI.NADetDesign
{
    public static class xAppDSN
    {
        private static object? app;
        public static object? App
        {
            get => app;
            set { app = value; CSI.NADetBase.Common.xApp.App = value; }
        }
    }
}
namespace CSI.CSiNAWallStackDesigner
{
    public static class xAppWD { public static object? App { get; set; } }
}
