using Cdcrd.BeamngExport;

var cases = new (double Start, double End, int Count)[]
{
    (0, 10.000000000000002, 3),
    (0, 10, 3),
    (0, 9.999999999999998, 3),
    (20, 32.2, 4),
    (-10, 2.5, 4),
    (1000000, 1000010.0000000001, 3)
};
foreach (var test in cases)
{
    var stations = StationSampling.CreateStations(test.Start, test.End, 5).ToArray();
    if (stations.Length != test.Count || stations[0] != test.Start || stations[^1] != test.End)
        throw new InvalidOperationException("Station count or exact endpoint regression.");
    for (var i = 1; i < stations.Length; i++)
    {
        // Straight synthetic alignment: XY distance equals station spacing.
        // These are consumer invariants, including Python's duplicate-node test.
        var gap = stations[i] - stations[i - 1];
        if (gap < 1e-9 || gap > 5 + StationSampling.EndpointToleranceMetres)
            throw new InvalidOperationException("Duplicate node or excessive sample spacing.");
    }
}
foreach (var bad in new[] { (0d, double.NaN, 5d), (10d, 0d, 5d), (0d, 10d, 0d) })
{
    try
    {
        _ = StationSampling.CreateStations(bad.Item1, bad.Item2, bad.Item3).ToArray();
        throw new InvalidOperationException("Invalid interval accepted.");
    }
    catch (ArgumentOutOfRangeException)
    {
        // Expected validation failure.
    }
}
Console.WriteLine($"STATION_SAMPLING_OK: {cases.Length} valid cases; 3 invalid cases; endpoint preserved; no duplicate final nodes.");
