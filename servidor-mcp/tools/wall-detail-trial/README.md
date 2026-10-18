# Detached wall-detail trials — experimental R07.1

This separate .NET 8 plugin generates trial reinforcement patterns on detached
copies of two uniform wall sections with their end joints in an explicitly authorized ETABS 23.3.0 fixture.
The existing V2.2 reader is unchanged. **The source cage and EDB are not corrected
by this plugin.** Native execution and interpretation of its results are required
before implementing a writer.

The physical cage captured by the earlier reader differs from the checked section.
Changing a cover label or bar preference does not establish physical agreement.
This tool measures what the native generator actually produces without assigning
those trial patterns to a source story or saving the model.

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

Historical R04–R06 cases: five trials per leg (ten detached trials):

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
R06 also exports native story cages in fresh detached containers. Neither output
is a validated fabrication schedule.

## Build and execution

```powershell
dotnet test tests/DetachedTrial.Tests.csproj
dotnet build CDCRD.WallDetailTrial.csproj -c Release
```

Deploy DLL/deps/runtimeconfig to a new directory; never replace a loaded DLL.
Provide `probe-options.json` using the same explicit authorization schema as V2.2
and `trial-options.json` with `ResourceLockPath` set to the actual cooperative
ETABS lock. A present lock blocks execution; do not remove another owner's lock.

Add `CDCRD.WallDetailTrialR071.dll` through ETABS Tools → Add/Show Plugins and invoke
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
alone are insufficient to establish the steel used by design. Native R05 completed ten trials with 110 manifest files verified, 34 unique
vertical points per section, and source sections/joints/cages unchanged. Its numeric
section yield getters returned zero; this is an unresolved detailing field, not a
verified steel property. The 54 tests cover independent rebindings, rejection before any
list changes, read-only/fixed lists, aliases and existing ownership/export gates.
A new assembly identity preserves the previously loaded trials.

R06 builds fresh native story/section/geometry/bounds objects containing each
isolated candidate pier, then exports native vertical/horizontal cages and groups.
It copies six finite bounds coordinates explicitly and checks the authorized
3000 mm story extents. The native bounds clone was not used. No source geometry,
parent stack, editor, elevation update, model setter or save is involved. R06 has
68 tests and builds without warnings. Native R06 completed ten trials; all 150
manifest files and four unchanged source cages were independently verified.

Private R05 curve analysis independently fitted the five circular bends and their
extrema. The reported native cut equals the 3D chord sum, not the circular-arc
centreline length. Native bend getters also reduce the code-returned radius and
tail for the generated drawing. Preserve raw values and do not label this drawing
as a fabrication schedule. R06 confirmed that the 16/12 mm, 46 mm cover-label candidate has 34 vertical
segments and eight horizontal rows per story, at 406.8 mm. However only the four
end-joint axes match the plan: thirty line-derived axes differ. Independent finite
line/circular-arc distance checks reject the resulting overlaps. Even the plan
end-joint bars interfere with the horizontal bends. The candidate remains rejected.
Local crossover Z is retained in the native cage; it must not be flattened.

No fixture, CSI DLL or reconstructed implementation is distributed. REA 6.5 member
inspection and focused parser analysis were performed locally against the installed
binaries; private analysis bodies remain outside this repo.

`complete_detailing=false`, `engineering_approval=false`.

## R07 point correspondence trial

Four detached trials replace the earlier ten-case matrix: the 46 mm cover-label
baseline and its explicit-point variant, once per story. The variant copies the
thirty generated leg coordinates into fresh native point objects and a new native
point-pattern collection. It uses the catalog size property, not the native
three-number constructor (whose first argument is area). Source patterns are read
only. End-joint patterns are preserved. Before assigning the new collection to the
detached leg, every coordinate and diameter is compared. After generating the
native cage, all 34 axes must match the complete section plan one-to-one. Counts,
finite coordinates, unique locations and straight vertical geometry are required.

This addresses a specific plan-to-cage discrepancy. It does not correct the four
end-bar interferences, horizontal hooks, vertical end elevations, native lap
geometry, material metadata, capacity or persistence. The original source cage and
EDB remain untouched. R07 stopped at its layout guard during point conversion;
source sections, preferences and all four source cages remained unchanged.
Native R07.1 execution is pending; passing tests is not native validation. `src/wall_cage_checks.py` adds independent signed-clearance checks for
finite vertical bars versus straight segments or explicitly identified horizontal
circular arcs. Negative means overlapping radius envelopes. The checks do not
infer arcs from arbitrary samples or approve positive clearance as code compliance.

R07 software validation: 85 C# tests and Release build with zero warnings/errors;
69 Python tests across the three geometry/check modules, including 28 new checks
and 98% statement coverage of the new interference module. These checks are not
a complete review of the native API or an engineering approval.


## R07.1 cache synchronization repair

The point group's area calculation consumes each child point's cached mesh.
Changing the size or coordinates and reading the point directly does not refresh
that mesh. R07 omitted this refresh, so a direct point read could pass while the
containing group still used the previous diameter.

R07.1 explicitly refreshes each freshly constructed point before adding it to the
new group, then refreshes the new group. The zero-argument public method must
return void. Identity guards run before refresh, and all original layout checks
remain. A mismatch reports the stage and expected/actual numeric coordinates and
diameters. No mesh of the source model is refreshed.

Validation: 89 C# tests, Release build without warnings/errors. Four new tests
cover stale child/group state, a guard stopping mutation, an incorrect diameter
after refresh, and an unsupported refresh signature. These use independent test
doubles; live execution against ETABS remains a separate requirement. Assembly
identity changes to R071 so the loaded R07 binary can be preserved.
