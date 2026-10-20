using System;
using System.Reflection;

namespace Cdcrd.Civil3dBridge
{
    // ValueTuple.ItemN son campos publicos; Tuple.ItemN son propiedades.
    internal static class ReflectionRead
    {
        public static bool TryRead(object target, string name, out object value)
        {
            value = null;
            if (target == null) return false;
            const BindingFlags flags = BindingFlags.Public | BindingFlags.Instance | BindingFlags.IgnoreCase;
            var type = target.GetType();
            var field = type.GetField(name, flags);
            if (field != null) { value = field.GetValue(target); return true; }
            var prop = type.GetProperty(name, flags);
            if (prop == null || !prop.CanRead || prop.GetIndexParameters().Length != 0) return false;
            try { value = prop.GetValue(target); return true; }
            catch (TargetInvocationException ex)
            {
                System.Runtime.ExceptionServices.ExceptionDispatchInfo.Capture(ex.InnerException ?? ex).Throw();
                throw;
            }
        }
    }
}
