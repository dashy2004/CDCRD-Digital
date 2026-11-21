using System;
using Cdcrd.Civil3dBridge;

static class PlotRotationChecks
{
    internal static void Run(Action<bool, string> check)
    {
        check(PlotRotationContract.Parse(null) == null, "rotation omitted preserves layout");
        check(PlotRotationContract.Parse("") == null, "rotation empty preserves layout");
        foreach (var value in new[] { 0, 90, 180, 270 })
            check(PlotRotationContract.Parse(value.ToString()) == value, "explicit rotation " + value);
        foreach (var value in new[] { "-90", "45", "360", "90.0", "Landscape", "NaN" })
        {
            bool rejected = false;
            try { PlotRotationContract.Parse(value); }
            catch (ArgumentException) { rejected = true; }
            check(rejected, "invalid rotation rejected: " + value);
        }
    }
}
