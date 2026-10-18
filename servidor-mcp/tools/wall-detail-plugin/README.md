# ETABS wall detail probe — experimental, read only

This .NET 8 plugin captures the native wall-stack designer's serialized data in
one explicitly authorized, analyzed test copy. It is **not** a bar-bending
schedule generator, engineering check, or replacement for `GetRebar`.

## Compatibility and safety

- ETABS **23.3.0**, with the two exact binary SHA-256 identities in `cPlugin.cs`.
- Exact model path, process ID and UTC process creation time must match the local
  `probe-options.json`. A reused PID, another model, or an unlocked model fails.
- Uses ETABS's supported plugin entry point. REA static analysis identified a
  build-local read accessor to the already loaded wall designer. No assembly
  injection, patched CSI binary, license operation, or general reflection writer.
- No geometry/reinforcement setters, analysis, model unlock or model save.
  The native serializer may normalize tower identity metadata in memory; this
  must not be described as a byte-for-byte snapshot of all in-memory state.
- The native wall designer must already be initialized for the current copy.
  A model path check alone does **not** prove that its cached detailing is current.
  Run wall design and wall-stack detailing in this copy before capture, then
  validate the captured identities and contents against OAPI results.
- Raw captures remain private alongside the test model. Never commit them.

## Build and test (Windows)

```powershell
dotnet test tests/ProbeGate.Tests.csproj
dotnet build CDCRD.WallDetailProbe.csproj -c Release
```

The default reference directory is `C:\Program Files\Computers and Structures\ETABS 23`.
Override with `-p:EtabsInstallDir="..."` when compiling. This does not relax the
runtime compatibility checks. Do **not** redistribute `ETABSv1.dll` or CSI binaries.

Copy the built `CDCRD.WallDetailProbe.dll`, `.deps.json`, and `.runtimeconfig.json`
to a new versioned local folder. Add a local configuration, for example:

```json
{
  "ExpectedModel": "C:\\Synthetic\\authorized-copy.EDB",
  "ExpectedProcessId": 12345,
  "ExpectedStartUtc": "2026-01-01T00:00:00.0000000Z"
}
```

Use the actual values, not this example. In ETABS, choose **Tools → Add/Show
Plugins → Browse**, select the plugin DLL, add it, and invoke it from Tools.
See [CSI's .NET 8 plugin instructions](https://web.wiki.csiamerica.com/wiki/spaces/kb/pages/2011456/NET%2B8%2BPlugin%2BExample%2B-%2BAll%2BProducts).

Successful capture produces a new `wall-detail-capture-*` directory beside the
model with `native-wall-detail.json` and `capture.json`. A failure produces a
`failure-*.json` beside the plugin and signals failure through the CSI callback.
Neither successful compilation nor successful capture proves valid detailing.

## Verification status

The process/model gate has 11 passing automated tests and the plugin builds with
zero warnings. Native loading and capture are still pending live validation.
Quantities, cut lengths, hooks, laps, anchorage and cover semantics have **not**
been verified by this plugin. `complete_detailing` and `engineering_approval`
remain false in its output.
