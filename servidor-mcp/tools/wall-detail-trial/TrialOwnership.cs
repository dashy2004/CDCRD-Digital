using System.Text.Json;

namespace CDCRD.WallDetailTrial;

/// <summary>Cooperative exclusive ownership; an existing lock always blocks.</summary>
internal sealed class TrialOwnership : IDisposable
{
    private readonly string path;
    private readonly FileStream stream;
    private bool disposed;

    private TrialOwnership(string path, FileStream stream) { this.path = path; this.stream = stream; }

    public static TrialOwnership Acquire(string directory, string model, int pid, DateTime started)
    {
        using var config = JsonDocument.Parse(File.ReadAllText(Path.Combine(directory, "trial-options.json")));
        string path = config.RootElement.GetProperty("ResourceLockPath").GetString()
                      ?? throw new InvalidOperationException("Missing explicit resource lock.");
        if (!Path.IsPathFullyQualified(path) || Path.GetExtension(path) != ".lock")
            throw new InvalidOperationException("Resource lock must be an absolute .lock path.");
        var stream = new FileStream(path, FileMode.CreateNew, FileAccess.ReadWrite, FileShare.Read);
        var owner = new TrialOwnership(path, stream);
        try
        {
            JsonSerializer.Serialize(stream, new { agent = "codex", task = "detached-wall-trial-r03",
                pid, started_utc = started, model, created_utc = DateTime.UtcNow, in_flight = 1 });
            stream.Flush(true);
            return owner;
        }
        catch { owner.Dispose(); throw; }
    }

    public void Dispose()
    {
        if (disposed) return;
        disposed = true;
        stream.Dispose();
        File.Delete(path);
    }
}
