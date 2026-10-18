using ETABSv1;

namespace CDCRD.WallDetailProbe;

internal static class OapiGeometry
{
    public static WallSnapshot[] Read(cSapModel model)
    {
        if ((int)model.GetPresentUnits() != 9)
            throw new InvalidOperationException("Geometry corroboration requires current N_mm_C; no units are changed.");
        int count = 0;
        string[] names = [];
        Check(model.AreaObj.GetNameList(ref count, ref names), "AreaObj.GetNameList");
        if (count != names.Length) throw new InvalidOperationException("OAPI area count mismatch.");
        var result = new List<WallSnapshot>();
        foreach (string name in names)
        {
            string pier = "";
            Check(model.AreaObj.GetPier(name, ref pier), "AreaObj.GetPier");
            if (string.IsNullOrWhiteSpace(pier) || pier == "None") continue;
            string guid = "";
            Check(model.AreaObj.GetGUID(name, ref guid), "AreaObj.GetGUID");
            int number = 0;
            string[] points = [];
            Check(model.AreaObj.GetPoints(name, ref number, ref points), "AreaObj.GetPoints");
            if (number != points.Length) throw new InvalidOperationException("OAPI vertex count mismatch.");
            var vertices = new List<Vertex>();
            foreach (string point in points)
            {
                double x = 0, y = 0, z = 0;
                Check(model.PointObj.GetCoordCartesian(point, ref x, ref y, ref z, "Global"), "PointObj.GetCoordCartesian");
                vertices.Add(new(x, y, z));
            }
            result.Add(new(guid, vertices.ToArray()));
        }
        return result.ToArray();
    }

    private static void Check(int result, string method)
    {
        if (result != 0) throw new InvalidOperationException($"{method} failed with OAPI code {result}.");
    }
}
