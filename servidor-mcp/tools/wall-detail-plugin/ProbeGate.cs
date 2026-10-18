namespace CDCRD.WallDetailProbe;

public sealed record ProbeOptions(string ExpectedModel, int ExpectedProcessId, DateTimeOffset ExpectedStartUtc);

public static class ProbeGate
{
    public static void Validate(ProbeOptions options, string model, int pid, DateTimeOffset started, bool locked)
    {
        ArgumentNullException.ThrowIfNull(options);
        if (options.ExpectedProcessId <= 0 || options.ExpectedProcessId != pid || options.ExpectedStartUtc != started)
            throw new InvalidOperationException("ETABS process identity does not match the authorized fixture.");
        if (!Path.IsPathFullyQualified(options.ExpectedModel) ||
            !string.Equals(Path.GetExtension(options.ExpectedModel), ".EDB", StringComparison.OrdinalIgnoreCase) ||
            !string.Equals(Path.GetFullPath(options.ExpectedModel), Path.GetFullPath(model), StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Model path does not match the authorized EDB copy.");
        if (!locked) throw new InvalidOperationException("The authorized model must remain analyzed and locked.");
    }
}
