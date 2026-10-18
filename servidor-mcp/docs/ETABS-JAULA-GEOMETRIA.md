# Physical wall-cage geometry checks

`src/wall_cage_geometry.py` checks explicitly supplied millimetre centreline samples
against a straight, finite wall plan. It reads numeric fields only, ignores native
`$type` metadata and does not access ETABS. The CLI requires wall geometry and the
required cover; it never infers units from a wrapper label.

```powershell
python tools/check_wall_cage_geometry.py C:\Synthetic\horizontal-cage.json `
  --start 0 0 --end 0 4000 --thickness-mm 200 `
  --required-cover-mm 40 --maximum-spacing-mm 450
```

The sampled distance to a concrete face is reduced by the bar radius. For curved
bars, a sampled minimum is an **upper bound** on the unknown true minimum: a bad
sample disproves cover, while satisfactory samples cannot prove the envelope
between samples. Two-point straight spans without unresolved bends can be checked
against the planar wall faces. Top/bottom cover and continuity across stories are
not inferred from a 2D wall plan.

A prior synthetic capture had nominal cover 38.1 mm but horizontal sampled surface
clearances of 31.1 mm at its ends and approximately 37.084 mm at a side. Its straight
vertical minimum lateral clearance was 42.1 mm. These describe the captured geometry,
not a general CSI cover convention or an approved replacement detail.

The output reports bar count, diameters, exact represented straight spans, duplicate
sample paths and base-elevation spacing. Duplicate paths are reported without
silently deleting bars. Base elevations use the lowest point of each shape so
local crossover Z offsets do not become extra rows. It does not determine bend
radii, hooks, stock lengths, mass units, curved cut lengths, foundation adequacy,
confinement or professional approval. Cached `PLine.Length` is ignored.

The isolated trial plugin in `tools/wall-detail-trial` is a separate prerequisite
for testing proposed native settings. It does not alter the model's existing cage.
The API's derived layers, checked section, native settings and physical cage remain
separate evidence sources. Their discrepancies must not be reconciled by relabeling.
