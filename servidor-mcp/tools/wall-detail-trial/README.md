# Detached wall-detail trials — experimental R04

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

Five trials per leg (ten detached trials):

1. `control`: unchanged clone, regenerated to establish a control.
2. `metric-mid`: vertical 16 at 250 mm; horizontal 12, maximum 400 mm; cover 40 mm.
3. `metric-start-tie`: same, setting the native end-zone tie preference to 12.
4. `metric-both-ties-cover40`: same, explicitly setting both detached end data areas to the catalog area for 12.
5. `metric-both-ties-cover46`: the previous case with cover label 46 mm.

R03.1 proved that the native tie preference setter only changes the start zone.
The third scenario preserves that behavior as a control; the fourth addresses
both ends. The fifth tests the 6 mm radius of a 12 mm horizontal bar as a possible
difference between the native cover label and concrete-to-steel surface distance.
It does not assert that 46 mm is the correct setting: all generated positions and
curves still require measurement. The 400 mm horizontal input investigates the
observed native interval-rounding issue. It is not a verified story row spacing.

R04 exports `GetBarPoints` from each generated pattern and `GetPlines` from each
shape, including bar parameters, material identifiers and the unverified native
cut length. It rejects type-name strings, empty geometry, missing coordinates and
nonpositive diameters. Curves are preserved, not replaced by chord lengths.
Source vertical/horizontal 3D cages are captured before and after and compared in
addition to source leg data/preferences. Generators and setters operate on clones;
the output is plan geometry, not a regenerated full-story cage or a cutting list.

## Build and execution

```powershell
dotnet test tests/DetachedTrial.Tests.csproj
dotnet build CDCRD.WallDetailTrial.csproj -c Release
```

Deploy DLL/deps/runtimeconfig to a new directory; never replace a loaded DLL.
Provide `probe-options.json` using the same explicit authorization schema as V2.2
and `trial-options.json` with `ResourceLockPath` set to the actual cooperative
ETABS lock. A present lock blocks execution; do not remove another owner's lock.

Add `CDCRD.WallDetailTrialR04.dll` through ETABS Tools → Add/Show Plugins and invoke
it once on the authorized, already analyzed copy. No design/detailing rerun is
needed. A restarted process invalidates the configuration.

The new private `wall-detail-trial-*` folder contains source geometry, unit evidence,
trial input/generated data, numeric points/polylines, source cages, hashes and
`source-invariants.json`. Success means the detached trial ran, not that its
geometry, spacing, cuts, covers or anchorage are acceptable. A failure file beside
the plugin preserves the exception. Do not save on the strength of the callback.

## Verification status

The isolation/ownership and numeric export tests and compilation run without
ETABS. R03 stopped at the isolation gate because native line endpoints are public
fields, whereas the reader expected properties. R03.1 corrected that contract and
completed six native trials with source data/preferences unchanged. Its pattern
collections serialized as type-name strings, so geometric acceptability was not
established. The old `metric-all-ties` label was inaccurate: only StartZone changed.

R04 adds numeric geometry extraction, rejects the actual opaque output shape, and
sets both detached end-zone areas in explicitly named scenarios. Tests also check
source preservation and invalid areas. Native R04 execution remains pending. A new
assembly identity avoids replacing R03/R03.1 already loaded in the host.

No fixture, CSI DLL or reconstructed implementation is distributed. REA 6.5 member
inspection and focused parser analysis were performed locally against the installed
binaries; private analysis bodies remain outside this repo.

`complete_detailing=false`, `engineering_approval=false`.
