# Detached wall-detail trials — experimental R03.1

This separate .NET 8 plugin generates trial reinforcement patterns on detached
copies of two uniform wall legs in an explicitly authorized ETABS 23.3.0 fixture.
The existing V2.2 reader is unchanged. **The source cage and EDB are not corrected
by this plugin.** Native execution and interpretation of its results are required
before implementing a writer.

The physical cage captured by the earlier reader differs from the checked section.
Changing a cover label or bar preference does not establish physical agreement.
This tool measures what the native generator actually produces without assigning
those trial patterns to a story or saving the model.

## Scope and guards

- Reuses the reader's exact binary hashes, PID/start/path/lock and geometry/unit
  gates. Numeric context must agree even if the independent wrapper label differs.
- Requires an exclusively acquired resource lock, two stories/two legs, uniform
  4000 × 200 mm wall plans and no boundary/confinement zones.
- Calls the native leg's public `Clone`, then verifies independent data, start/end/
  middle zones, centreline and endpoint objects, no parent section and edit mode off.
- Only detached clones receive setters. No original setters, model unlock, analysis,
  story regeneration, `UpdateDBFile`, save or native JSON deserialization.
- Verifies the metric catalog by area and actual selected diameter before using
  the names `16` and `12`; they are not imperial bar numbers.
- Serializes source legs and global wall preferences before and after, including
  failure paths. Any source mismatch fails visibly. An error is not approval.
- Restores both temporary native application contexts in the established order.

Three trials per leg:

1. `control`: unchanged clone, regenerated to establish a control.
2. `metric-mid`: vertical 16 at 250 mm; horizontal 12, maximum 400 mm; cover 40 mm.
3. `metric-all-ties`: same, also setting the dormant end-zone tie preference to 12.

The third trial is necessary because the inspected native generator reads the
end-zone tie preference when locating longitudinal bars, including uniform walls
without a confinement zone. The 400 mm horizontal setting is a conservative trial
input to investigate the observed interval-rounding issue; final physical row
spacing must still be measured. No setting here is presented as a design decision.

## Build and execution

```powershell
dotnet test tests/DetachedTrial.Tests.csproj
dotnet build CDCRD.WallDetailTrial.csproj -c Release
```

Deploy DLL/deps/runtimeconfig to a new directory; never replace a loaded DLL.
Provide `probe-options.json` using the same explicit authorization schema as V2.2
and `trial-options.json` with `ResourceLockPath` set to the actual cooperative
ETABS lock. A present lock blocks execution; do not remove another owner's lock.

Add `CDCRD.WallDetailTrialR031.dll` through ETABS Tools → Add/Show Plugins and invoke
it once on the authorized, already analyzed copy. No design/detailing rerun is
needed. A restarted process invalidates the configuration.

The new private `wall-detail-trial-*` folder contains source geometry, unit evidence,
trial input/generated data, vertical patterns, horizontal shapes, hashes and
`source-invariants.json`. Success means the detached trial ran, not that its
geometry, spacing, cuts, covers or anchorage are acceptable. A failure file beside
the plugin preserves the exception. Do not save on the strength of the callback.

## Verification status

The pure isolation/ownership tests and compilation can run without ETABS. They do
not prove that detached native generation works or that a native clone exposes all
required context. R03 stopped at its isolation gate before changing clone settings:
the native line endpoints are public fields, whereas the reader expected properties.
Source legs and preferences were confirmed unchanged by the failure-path invariant.
R03.1 reads those two fields explicitly; regression fixtures use the real field
shape and assert that shared endpoint rejection reaches the alias check. A new
assembly identity allows deployment without replacing the loaded R03 binary.
Native invocation of R03.1 is pending. No fixture, CSI DLL or reconstructed
CSI implementation is distributed. REA 6.5 parser analysis was performed locally
against the installed binaries; private analysis bodies remain outside this repo.

`complete_detailing=false`, `engineering_approval=false`.
