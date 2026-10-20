using System;

namespace Cdcrd.Civil3dBridge
{
    internal static class GmGroupPolicy
    {
        public static bool EmptyGm(string name, int members, int dead)
        {
            return members == 0 && dead == 0 &&
                name != null && name.StartsWith("GM - ", StringComparison.OrdinalIgnoreCase);
        }

        public static bool CanErase(string name, int live, bool onlyGm, int knownLayers, bool unknownLayer)
        {
            // Nunca borrar un grupo ajeno sin poder atribuir sus miembros al GM.
            return !unknownLayer && onlyGm &&
                (knownLayers > 0 || (live == 0 && name != null &&
                    name.StartsWith("GM - ", StringComparison.OrdinalIgnoreCase)));
        }
    }
}
