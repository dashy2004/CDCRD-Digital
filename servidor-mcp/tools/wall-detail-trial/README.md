# Detached wall-detail trials — experimental R05

This separate .NET 8 plugin generates trial reinforcement patterns on detached
copies of two uniform wall sections with their end joints in an explicitly authorized ETABS 23.3.0 fixture.
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
- Calls the native section's public `Clone`, verifies its single leg and two end
  joints, independent data/zones/centreline/endpoints, no external parent and edit
  mode off. Native joint clones initially refer to the source leg: all joint
  objects, centres and mutable lists are checked before rebinding those clone
  lists to the detached leg. Any shared or unexpected object rejects the trial.
- Only detached clones receive setters. No original setters, model unlock, analysis,
  story regeneration, `UpdateDBFile`, save or native JSON deserialization.
- Verifies the metric catalog by area and actual selected diameter before using
  the names `16` and `12`; they are not imperial bar numbers.
- Serializes source sections/joints, legs and global wall preferences before and after, including
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

Add `CDCRD.WallDetailTrialR05.dll` through ETABS Tools → Add/Show Plugins and invoke
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

R04 completed ten native trials with all 70 manifest files verified and source
legs/preferences plus the four physical source cages identical before and after.
Its individual-leg control contained 30 plan points while the source cage has 34:
the four end-joint bars were outside that trial's scope. The 46 mm cover-label
candidate has 40 mm minimum end clearance at the exported horizontal points;
this is not a full curved-envelope verification.

R05 generates the detached section and both end joints together, then exports all
leg and joint patterns after native joint adjustment. It also reads the numeric
section `GetRebarFy`/`GetRebarFys` values from source and clone: material-name strings
alone are insufficient to establish the steel used by design. Native R05 execution
remains pending. Its 54 tests cover independent rebindings, rejection before any
list changes, read-only/fixed lists, aliases and existing ownership/export gates.
A new assembly identity preserves the previously loaded trials.

No fixture, CSI DLL or reconstructed implementation is distributed. REA 6.5 member
inspection and focused parser analysis were performed locally against the installed
binaries; private analysis bodies remain outside this repo.

`complete_detailing=false`, `engineering_approval=false`.
