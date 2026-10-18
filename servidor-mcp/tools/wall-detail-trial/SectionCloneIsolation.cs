using System.Collections;
using System.Reflection;

namespace CDCRD.WallDetailTrial;

internal static class SectionCloneIsolation
{
    private static object[] Items(object value) => value is IList list && list.Count is > 0 and <= 4
        ? list.Cast<object>().ToArray() : throw new InvalidOperationException("Unexpected fixture section collection.");

    private static void RequireNoParent(object value, string name)
    {
        var property = value.GetType().GetProperty(name, BindingFlags.Public | BindingFlags.Instance)
            ?? throw new InvalidOperationException("Missing section parent contract.");
        if (property.GetValue(value) is not null) throw new InvalidOperationException("Section clone has an external parent.");
    }

    /// <summary>Native joint cloning copies leg references; rebind only its independent lists.</summary>
    internal static object RebindFixtureJoints(object source, object clone)
    {
        if (ReferenceEquals(source, clone) || source.GetType() != clone.GetType())
            throw new InvalidOperationException("Section clone is not independent.");
        RequireNoParent(clone, "SectionCut");
        object sl = DetachedTrial.Read(source, "DesignLegs"), cl = DetachedTrial.Read(clone, "DesignLegs");
        object sj = DetachedTrial.Read(source, "Joints"), cj = DetachedTrial.Read(clone, "Joints");
        if (ReferenceEquals(sl, cl) || ReferenceEquals(sj, cj))
            throw new InvalidOperationException("Section collections alias source.");
        object[] sourceLegs = Items(sl), cloneLegs = Items(cl), sourceJoints = Items(sj), cloneJoints = Items(cj);
        if (sourceLegs.Length != 1 || cloneLegs.Length != 1 || sourceJoints.Length != 2 || cloneJoints.Length != 2)
            throw new InvalidOperationException("Expected one leg with two end joints.");
        DetachedTrial.RequireDetached(sourceLegs[0], cloneLegs[0]);
        var sourceNodes = new[] { sl, sj, sourceLegs[0] }
            .Concat(DetachedTrial.DataNodes(DetachedTrial.Call(sourceLegs[0], "GetLegData")))
            .Concat(sourceJoints.SelectMany(j => new[] { j, DetachedTrial.Read(j, "Center"), DetachedTrial.Read(j, "Legs") })).ToArray();
        var cloneNodes = new[] { cl, cj, cloneLegs[0] }
            .Concat(DetachedTrial.DataNodes(DetachedTrial.Call(cloneLegs[0], "GetLegData")))
            .Concat(cloneJoints.SelectMany(j => new[] { j, DetachedTrial.Read(j, "Center"), DetachedTrial.Read(j, "Legs") })).ToArray();
        if (sourceNodes.Any(a => cloneNodes.Any(b => ReferenceEquals(a, b))) ||
            cloneNodes.Distinct(ReferenceEqualityComparer.Instance).Count() != cloneNodes.Length)
            throw new InvalidOperationException("Joint clone shares mutable objects.");
        foreach (object joint in cloneJoints)
        {
            RequireNoParent(joint, "PierSection");
            var links = DetachedTrial.Read(joint, "Legs");
            object[] referenced = Items(links);
            if (((IList)links).IsReadOnly || ((IList)links).IsFixedSize ||
                referenced.Length != 1 || !ReferenceEquals(referenced[0], sourceLegs[0]))
                throw new InvalidOperationException("Unexpected native joint clone linkage.");
        }
        foreach (object joint in cloneJoints)
        {
            var links = (IList)DetachedTrial.Read(joint, "Legs");
            links.Clear(); links.Add(cloneLegs[0]);
        }
        return cloneLegs[0];
    }
}
