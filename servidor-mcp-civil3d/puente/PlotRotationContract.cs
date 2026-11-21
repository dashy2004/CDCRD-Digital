using System;
using System.Globalization;

namespace Cdcrd.Civil3dBridge
{
    internal static class PlotRotationContract
    {
        // Null preserves the drawing's existing setting for older callers.
        internal static int? Parse(string text)
        {
            if (string.IsNullOrWhiteSpace(text)) return null;
            if (int.TryParse(text, NumberStyles.None, CultureInfo.InvariantCulture, out int value)
                && (value == 0 || value == 90 || value == 180 || value == 270))
                return value;
            throw new ArgumentException("rotacion debe ser 0, 90, 180 o 270 grados.");
        }
    }
}
