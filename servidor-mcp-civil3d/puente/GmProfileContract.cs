using System;
using System.Collections.Generic;
using System.Linq;

namespace Cdcrd.Civil3dBridge
{
    // Contract of the installed GM: an empty/unknown field silently yields no strata.
    internal static class GmProfileContract
    {
        private static readonly string[] Fields = {
            "LegendCode", "LegendName", "GeologyCode1", "GeologyName1",
            "GeologyCode2", "GeologyName2", "BGSCode", "BGSName"
        };

        internal static string Field(string requested, string saved)
        {
            var field = string.IsNullOrWhiteSpace(requested) ? saved : requested;
            field = field?.Trim();
            if (!Fields.Contains(field))
                throw new ArgumentException("Indique campo_geologia valido o guarde la seleccion en el GM: "
                    + string.Join(", ", Fields) + ". No se modificaron perfiles.");
            return field;
        }

        internal static void RequireStrata(IDictionary<string, int> counts)
        {
            var missing = counts.Where(x => x.Value <= 0).Select(x => x.Key).ToArray();
            if (counts.Count == 0 || missing.Length > 0)
                throw new ArgumentException("El campo de geologia no produce estratos para: "
                    + string.Join(", ", missing) + ". No se modificaron perfiles.");
        }

        internal static bool Complete(int created, int withoutStrata, int inRange)
        {
            return inRange > 0 && created == inRange && withoutStrata == 0;
        }
    }
}
