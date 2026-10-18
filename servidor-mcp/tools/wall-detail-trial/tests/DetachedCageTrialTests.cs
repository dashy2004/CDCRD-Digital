using System.Collections;
using CDCRD.WallDetailTrial;
using Xunit;
using Leg = DetachedTrialTests.Leg;
using Pier = SectionCloneIsolationTests.Section;
using Joint = SectionCloneIsolationTests.Joint;

public sealed class DetachedCageTrialTests
{
    public sealed class Bounds
    {
        public double MinX { get; set; }
        public double MinY { get; set; }
        public double MinZ { get; set; }
        public double MaxX { get; set; }
        public double MaxY { get; set; } = 4000;
        public double MaxZ { get; set; } = 3000;
        public Bounds Clone() => throw new InvalidOperationException("Do not use native bounds cloning.");
    }
    public sealed class Geometry
    {
        public Bounds Bounds { get; set; } = new();
        public double BaseZLevel => Bounds.MinZ;
        public double Height => Bounds.MaxZ - Bounds.MinZ;
    }
    public sealed class Section
    {
        public IList PierSections { get; } = new List<Pier>();
        public object? Story { get; set; }
    }
    public sealed class Story
    {
        public IList Sections { get; } = new List<Section>();
        public Geometry Geom { get; set; } = new();
        public int StoryLocation { get; set; } = 2;
        public object? Stack { get; set; }
    }

    private static (Story source, Pier candidate) Fixture(double baseZ = 0)
    {
        var source = new Story { Stack = new object() };
        source.Geom.Bounds.MinZ = baseZ; source.Geom.Bounds.MaxZ = baseZ + 3000;
        var section = new Section { Story = source }; var pier = new Pier { SectionCut = section };
        ((Leg)pier.DesignLegs[0]!).PierSection = pier;
        section.PierSections.Add(pier); source.Sections.Add(section);
        var candidate = new Pier();
        for (int i = 0; i < 2; i++)
            candidate.Joints.Add(new Joint { Legs = new List<Leg> { (Leg)candidate.DesignLegs[0]! } });
        return (source, candidate);
    }

    [Theory][InlineData(0)][InlineData(3000)]
    public void CageContainerCopiesNumericBoundsWithoutRetainingSourceObjects(double baseZ)
    {
        var (source, pier) = Fixture(baseZ);
        var result = (Story)DetachedCageTrial.Build(source, pier);
        Assert.NotSame(source, result); Assert.NotSame(source.Geom, result.Geom);
        Assert.NotSame(source.Geom.Bounds, result.Geom.Bounds);
        Assert.Equal(baseZ, result.Geom.BaseZLevel); Assert.Equal(3000, result.Geom.Height);
        Assert.Equal(4000, result.Geom.Bounds.MaxY);
        Assert.Equal(baseZ + 3000, result.Geom.Bounds.MaxZ);
        Assert.Null(result.Stack); Assert.Null(((Section)result.Sections[0]!).Story);
        Assert.Same(pier, ((Section)result.Sections[0]!).PierSections[0]);
        result.Geom.Bounds.MinZ = -800;
        Assert.Equal(baseZ, source.Geom.BaseZLevel);
        Assert.Single(source.Sections.Cast<object>());
    }

    [Theory]
    [InlineData("nan")][InlineData("infinity")][InlineData("height")][InlineData("base")]
    [InlineData("reversed-x")][InlineData("reversed-y")][InlineData("source-pier")]
    [InlineData("pier-parent")][InlineData("joint-parent")][InlineData("joint-source-leg")]
    [InlineData("extra-section")][InlineData("extra-pier")]
    public void InvalidNativeContextIsRejectedWithoutChangingSource(string defect)
    {
        var (source, candidate) = Fixture();
        var section = (Section)source.Sections[0]!;
        var sourcePier = (Pier)section.PierSections[0]!;
        switch (defect)
        {
            case "nan": source.Geom.Bounds.MinX = double.NaN; break;
            case "infinity": source.Geom.Bounds.MaxY = double.PositiveInfinity; break;
            case "height": source.Geom.Bounds.MaxZ = 2999; break;
            case "base": source.Geom.Bounds.MinZ = 1; source.Geom.Bounds.MaxZ = 3001; break;
            case "reversed-x": source.Geom.Bounds.MinX = 1; break;
            case "reversed-y": source.Geom.Bounds.MaxY = -1; break;
            case "source-pier": candidate = sourcePier; break;
            case "pier-parent": candidate.SectionCut = section; break;
            case "joint-parent": ((Joint)candidate.Joints[0]!).PierSection = sourcePier; break;
            case "joint-source-leg": ((Joint)candidate.Joints[0]!).Legs[0] = sourcePier.DesignLegs[0]; break;
            case "extra-section": source.Sections.Add(new Section()); break;
            case "extra-pier": section.PierSections.Add(new Pier()); break;
        }
        var geometry = source.Geom; var bounds = geometry.Bounds;
        Assert.Throws<InvalidOperationException>(() => DetachedCageTrial.Build(source, candidate));
        Assert.Same(geometry, source.Geom); Assert.Same(bounds, source.Geom.Bounds);
        Assert.Same(sourcePier, section.PierSections[0]);
    }
}
