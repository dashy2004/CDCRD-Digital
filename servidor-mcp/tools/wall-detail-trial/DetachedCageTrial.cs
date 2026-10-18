using System.Collections;

namespace CDCRD.WallDetailTrial;

/// <summary>Fresh native story container for cage reads; owns no live model objects.</summary>
internal static class DetachedCageTrial
{
    private static object Fresh(object prototype) => Activator.CreateInstance(prototype.GetType())
        ?? throw new InvalidOperationException("Cannot create independent native container.");

    private static IList List(object owner, string property, int count)
    {
        if (DetachedTrial.Read(owner, property) is not IList list || list.Count != count ||
            list.IsReadOnly || list.IsFixedSize)
            throw new InvalidOperationException("Unexpected native container list: " + property);
        return list;
    }

    private static void NoParent(object owner, string property)
    {
        var p = owner.GetType().GetProperty(property)
            ?? throw new InvalidOperationException("Missing native parent contract.");
        if (p.GetValue(owner) is not null) throw new InvalidOperationException("Native container has a parent.");
    }

    internal static object Build(object sourceStory, object detachedPier)
    {
        object sourceSection = List(sourceStory, "Sections", 1)[0]!;
        object sourcePier = List(sourceSection, "PierSections", 1)[0]!;
        if (ReferenceEquals(sourcePier, detachedPier)) throw new InvalidOperationException("Source pier cannot be used.");
        NoParent(detachedPier, "SectionCut");
        object sourceLeg = List(sourcePier, "DesignLegs", 1)[0]!;
        object candidateLeg = List(detachedPier, "DesignLegs", 1)[0]!;
        DetachedTrial.RequireDetached(sourceLeg, candidateLeg);
        foreach (object joint in List(detachedPier, "Joints", 2))
        {
            NoParent(joint, "PierSection");
            if (!ReferenceEquals(List(joint, "Legs", 1)[0], candidateLeg))
                throw new InvalidOperationException("Candidate joints must reference the detached leg.");
        }

        object sourceGeometry = DetachedTrial.Read(sourceStory, "Geom");
        object sourceBounds = DetachedTrial.Read(sourceGeometry, "Bounds");
        string[] coordinates = ["MinX", "MinY", "MinZ", "MaxX", "MaxY", "MaxZ"];
        double[] numbers = coordinates.Select(p => (double)DetachedTrial.Read(sourceBounds, p)).ToArray();
        if (numbers.Any(v => !double.IsFinite(v)) || numbers[3] < numbers[0] || numbers[4] < numbers[1] ||
            numbers[5] - numbers[2] != 3000 || (numbers[2] != 0 && numbers[2] != 3000))
            throw new InvalidOperationException("Unexpected authorized story bounds.");

        // Copy six numeric values explicitly; do not rely on a native bounds Clone.
        object bounds = Fresh(sourceBounds), geometry = Fresh(sourceGeometry);
        for (int i = 0; i < coordinates.Length; i++) DetachedTrial.Set(bounds, coordinates[i], numbers[i]);
        DetachedTrial.Set(geometry, "Bounds", bounds);
        if ((double)DetachedTrial.Read(geometry, "BaseZLevel") != numbers[2] ||
            (double)DetachedTrial.Read(geometry, "Height") != 3000)
            throw new InvalidOperationException("Fresh geometry did not preserve story extents.");

        object story = Fresh(sourceStory), section = Fresh(sourceSection);
        NoParent(story, "Stack"); NoParent(section, "Story");
        IList sections = List(story, "Sections", 0), piers = List(section, "PierSections", 0);
        DetachedTrial.Set(story, "Geom", geometry);
        DetachedTrial.Set(story, "StoryLocation", DetachedTrial.Read(sourceStory, "StoryLocation"));
        piers.Add(detachedPier); sections.Add(section);
        return story;
    }
}
