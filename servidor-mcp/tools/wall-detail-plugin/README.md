# ETABS wall detail probe — experimental, read only

This .NET 8 V2.1 plugin captures the native wall-stack designer's serialized data in
one explicitly authorized, analyzed test copy. It is **not** a bar-bending
schedule generator, engineering check, or replacement for `GetRebar`.

## Compatibility and safety

- ETABS **23.3.0**, with the five exact binary SHA-256 identities in `cPlugin.cs`.
- Exact model path, process ID and UTC process creation time must match the local
  `probe-options.json`. A reused PID, another model, or an unlocked model fails.
- Uses ETABS's supported plugin entry point. REA static analysis identified a
  build-local read accessor to the already loaded wall designer. No assembly
  injection, patched CSI binary, license operation, or general reflection writer.
- No geometry/reinforcement setters, analysis, model unlock or model save.
  The native serializer may normalize tower identity metadata in memory; this
  must not be described as a byte-for-byte snapshot of all in-memory state.
- V2 temporarily activates the wall designer's common and design contexts and
  restores both on success or failure. The design-context setter also updates
  the common context, so restoration order matters. Both labels and OAPI must
  identify `N_mm_C`; other unit contexts fail closed. The original V1 capture's
  external label said inches while its geometry was in millimeters: do not use
  that label to convert old captures.
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

Copy the built `CDCRD.WallDetailProbeV21.dll`, `.deps.json`, and `.runtimeconfig.json`
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

V2 also requests the native rebar catalog, existing quantity caches, per-story
vertical/horizontal groups, and generated 3D cages. `expanded-capture.json`
records each output hash or explicit failure. An individual failed part does
not erase successful captures and produces a failure callback, not full success.
The quantity cache may be stale; a 3D cage does not by itself specify bend radii,
cut allowances or compliant anchorage. No native JSON `$type` is deserialized.

## Verification status

V1 loaded and captured real data from the synthetic copy. Two wall GUIDs and all
vertices matched OAPI; four native design stations matched displayed OAPI values
within display precision. V1 did not capture a physical bar schedule. It confirmed
vertical preferred area283.8704 versus checked201.1 mm² and cover38.1 versus40 mm.

V2 failed before capture because it requested a private activation method through
a public-method lookup. V2.1 uses the verified public context properties and has a
new assembly identity so it can load without replacing an already loaded DLL.
Its 19 gate/context tests pass, including public-accessor activation and restoration
with synthetic contract doubles; compilation has zero warnings/errors. V2.1 native
capture remains pending. Quantities, cut lengths, hooks, laps, anchorage and cover
semantics have **not** been fully verified. `complete_detailing` and
`engineering_approval` remain false.
