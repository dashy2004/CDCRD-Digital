namespace CDCRD.WallDetailProbe;

/// <summary>Restores caller context on success, failure, and partial activation.</summary>
public sealed class ContextLease : IDisposable
{
    private Action? restore;

    public ContextLease(Action activate, Action restoreFirst, Action restoreLast)
        : this(activate, Combine(restoreFirst, restoreLast)) { }

    private static Action Combine(Action first, Action last)
    {
        ArgumentNullException.ThrowIfNull(first);
        ArgumentNullException.ThrowIfNull(last);
        return () => { try { first(); } finally { last(); } };
    }

    public ContextLease(Action activate, Action restore)
    {
        ArgumentNullException.ThrowIfNull(activate);
        ArgumentNullException.ThrowIfNull(restore);
        this.restore = restore;
        try { activate(); }
        catch { Dispose(); throw; }
    }

    public void Dispose() => Interlocked.Exchange(ref restore, null)?.Invoke();
}
