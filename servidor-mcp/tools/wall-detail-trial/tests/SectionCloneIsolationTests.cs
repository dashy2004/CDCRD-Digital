using System.Collections;
using CDCRD.WallDetailTrial;
using Xunit;
using Leg = DetachedTrialTests.Leg;

public sealed class SectionCloneIsolationTests
{
    public sealed class Joint
    {
        public object Center { get; set; } = new();
        public IList Legs { get; set; } = new List<Leg>();
        public object? PierSection { get; set; }
    }
    public sealed class Section
    {
        public object? SectionCut { get; set; }
        public IList DesignLegs { get; set; } = new List<Leg> { new() };
        public IList Joints { get; set; } = new List<Joint>();
    }

    private static (Section source, Section clone) Fixture()
    {
        var source = new Section(); var clone = new Section();
        var sourceLeg = (Leg)source.DesignLegs[0]!;
        sourceLeg.PierSection = source;
        for (int i = 0; i < 2; i++)
        {
            source.Joints.Add(new Joint { Legs = new List<Leg> { sourceLeg }, PierSection = source });
            // Match the pinned native Clone: new joint/list/centre, original leg reference.
            clone.Joints.Add(new Joint { Legs = new List<Leg> { sourceLeg } });
        }
        return (source, clone);
    }

    [Fact] public void RebindsOnlyIndependentCloneLists()
    {
        var (source, clone) = Fixture();
        var result = SectionCloneIsolation.RebindFixtureJoints(source, clone);
        Assert.Same(clone.DesignLegs[0], result);
        foreach (Joint joint in clone.Joints) Assert.Same(result, joint.Legs[0]);
        foreach (Joint joint in source.Joints) Assert.Same(source.DesignLegs[0], joint.Legs[0]);
        Assert.Same(source, ((Leg)source.DesignLegs[0]!).PierSection);
        Assert.Null(((Leg)clone.DesignLegs[0]!).PierSection);
    }

    [Theory]
    [InlineData("section")][InlineData("section-parent")][InlineData("legs-list")]
    [InlineData("joints-list")][InlineData("joint")][InlineData("centre")]
    [InlineData("links")][InlineData("joint-parent")][InlineData("wrong-leg")]
    [InlineData("readonly-links")][InlineData("fixed-links")]
    [InlineData("duplicate-joint")][InlineData("duplicate-centre")]
    [InlineData("duplicate-links")][InlineData("extra-leg")][InlineData("missing-joint")]
    [InlineData("shared-leg-data")]
    [InlineData("links-to-source-leg-list")][InlineData("centre-to-source-line-point")]
    public void InvalidOwnershipStopsBeforeRebindingAnyList(string defect)
    {
        var (source, clone) = Fixture();
        var originalLeg = (Leg)source.DesignLegs[0]!;
        var firstCloneJoint = (Joint)clone.Joints[0]!;
        var secondCloneJoint = (Joint)clone.Joints[1]!;
        var sourceJoint = (Joint)source.Joints[1]!;
        switch (defect)
        {
            case "section": clone = source; break;
            case "section-parent": clone.SectionCut = new object(); break;
            case "legs-list": clone.DesignLegs = source.DesignLegs; break;
            case "joints-list": clone.Joints = source.Joints; break;
            case "joint": clone.Joints[1] = sourceJoint; break;
            case "centre": secondCloneJoint.Center = sourceJoint.Center; break;
            case "links": secondCloneJoint.Legs = sourceJoint.Legs; break;
            case "joint-parent": secondCloneJoint.PierSection = source; break;
            case "wrong-leg": secondCloneJoint.Legs[0] = new Leg(); break;
            case "readonly-links": secondCloneJoint.Legs = ArrayList.ReadOnly(new ArrayList { originalLeg }); break;
            case "fixed-links": secondCloneJoint.Legs = new[] { originalLeg }; break;
            case "duplicate-joint": clone.Joints[1] = firstCloneJoint; break;
            case "duplicate-centre": secondCloneJoint.Center = firstCloneJoint.Center; break;
            case "duplicate-links": secondCloneJoint.Legs = firstCloneJoint.Legs; break;
            case "extra-leg": clone.DesignLegs.Add(new Leg()); break;
            case "missing-joint": clone.Joints.RemoveAt(1); break;
            case "shared-leg-data": ((Leg)clone.DesignLegs[0]!).Data = originalLeg.Data; break;
            case "links-to-source-leg-list": secondCloneJoint.Legs = source.DesignLegs; break;
            case "centre-to-source-line-point": secondCloneJoint.Center = originalLeg.Data.CLine.Pt1; break;
        }
        Assert.Throws<InvalidOperationException>(() => SectionCloneIsolation.RebindFixtureJoints(source, clone));
        Assert.Same(originalLeg, firstCloneJoint.Legs[0]);
        foreach (Joint joint in source.Joints) Assert.Same(originalLeg, joint.Legs[0]);
    }
}
