# ETABS wall detail probe — experimental, read only

This .NET 8 V2.2 plugin captures the native wall-stack designer's serialized data in
one explicitly authorized, analyzed test copy. It is **not** a bar-bending
schedule generator, engineering check, or replacement for `GetRebar`.

## Compatibility and safety

- ETABS **23.3.0**, with the six exact binary SHA-256 identities in `cPlugin.cs`.
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
  the common context, so restoration order matters. That activation does **not**
  refresh the separate static field used for the wrapper unit label. V2.1's
  assumption that it would was wrong; its strict label gate rejected the capture.
- V2.2 requires OAPI database/present and payload units to be `N_mm_C`, then matches
  current OAPI wall GUIDs and every vertex against the payload without conversion.
  Other base units, missing/duplicate identities or mismatching coordinates fail.
  It separately records the numeric object-model units and native mm/m factors.
  Wrapper disagreement stays explicit; it is never used to rescale geometry.
  Captured bar-group units still require independent validation.
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

Copy the built `CDCRD.WallDetailProbeV22.dll`, `.deps.json`, and `.runtimeconfig.json`
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

V2.2 writes `unit-evidence.json` and, after a successful match,
`geometry-evidence.json`. It saves the raw payload before later corroboration
gates, so a failure can reference partial diagnostic evidence. Complete extraction
with a unit disagreement is labeled `captured_with_wrapper_label_conflict` or
`captured_for_diagnosis_unit_conflict`; a zero plugin callback then means extraction
finished, **not** unit or engineering approval. No conversion is applied and
`bar_group_units_verified` stays false.

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
V2.1 passed its 19 gate/context tests but failed in ETABS at the incorrect wrapper
label gate. REA verified the independent static field and the separate source of
numeric conversion factors. V2.2 has 34 passing tests, including unit conflicts,
coordinate scale errors and incomplete/duplicate geometry; build has zero warnings
or errors. Its parser/matcher also passed against the real V1 capture and previously
recorded OAPI evidence (two walls/eight vertices).

V2.2 subsequently ran successfully in the synthetic copy: ten expanded outputs,
zero failed parts, one stack and two stories. Live OAPI matched both wall GUIDs
and all eight vertices. Numeric context was N/mm/C, with mm factor 1 and m factor
1000; the independent wrapper label remained imperial and was retained verbatim.
An independent audit matched all 68 vertical segments to the physical groups and
their total straight span to the existing quantity cache. This does not validate
the cache's weight units or convert the spans into approved cut lengths.

The captured physical cage has 20 mm vertical and 14 mm horizontal bars, not the
checked 16 mm vertical / derived 12 mm horizontal layers. Its seven horizontal
shapes per story have actual spacing 474.6 mm despite a declared 450 mm maximum.
REA identified nearest-integer interval rounding in this exact build's cage
generator. Consumers must check actual generated positions, not only preferences.
No proprietary generator is patched. The native polylines contain crossover Z
offsets and arc flags, and report a zero cached `Length`; neither planar perimeter
nor vertex chord sums may be presented as fabrication lengths.
Cut lengths, hooks, laps, anchorage and cover semantics have **not** been fully verified.
`complete_detailing` and `engineering_approval` remain false.
