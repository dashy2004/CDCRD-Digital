using System;
using System.Runtime.ExceptionServices;

namespace Cdcrd.Civil3dBridge
{
    // A false result is a failed operation even if the native renderer did not throw.
    // Rollback is attempted exactly once, including when commit itself fails.
    internal static class GmAtomicOperation
    {
        public static bool Execute(Func<bool> operation, Action commit, Action rollback)
        {
            Exception failure = null;
            try
            {
                if (operation())
                {
                    commit();
                    return true;
                }
            }
            catch (Exception ex) { failure = ex; }

            try { rollback(); }
            catch (Exception rollbackFailure)
            {
                throw new AggregateException("GM rollback failed; inspect the drawing before retrying.",
                    failure == null ? new[] { rollbackFailure } : new[] { failure, rollbackFailure });
            }
            if (failure != null) ExceptionDispatchInfo.Capture(failure).Throw();
            return false;
        }
    }
}
