"""Input reconciliation must not promote native layers to fabrication approval."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from wall_reconciliation import length_unit, reconcile_layers


def inputs():
    layers = {
        "units_enum": 9,
        "units_basis": "database",
        "units_verified": True,
        "areas": [
            {
                "AreaObjName": "W",
                "StoryName": "L1",
                "PierLabel": "P",
                "layers": [
                    {
                        "LayerType": 2,
                        "BarSizeName": "12",
                        "BarArea": 113.1,
                        "BarSpacing": 450.0,
                        "ClearCover": 25.0,
                    },
                    {
                        "LayerType": 1,
                        "BarSizeName": "16",
                        "BarArea": 201.1,
                        "BarSpacing": 230.0,
                        "ClearCover": 0.0,
                    },
                ],
            }
        ],
    }
    rows = [
        {
            "Story": "L1",
            "Pier": "P",
            "Station": s,
            "DCRatio": ".589",
            "EndBar": "16",
            "EdgeBar": "16",
            "BarSpacing": "250",
            "ShearAv": ".5",
        }
        for s in ("Top", "Bottom")
    ]
    overwrites = [
        {
            "Story": "L1",
            "Pier": "P",
            "PierSecType": "Uniform Reinforcing Section",
            "EndBar": "16",
            "EdgeBar": "16",
            "EdgeBarSpc": "250",
            "ClearCover": "40",
        }
    ]
    return layers, rows, overwrites, 9


def test_four_layer_discrepancies_are_not_a_schedule():
    r = reconcile_layers(*inputs())
    assert r["status"] == "differences"
    assert r["complete_detailing"] is False
    h, v = r["layers"]
    assert h["distributed_area_mm2_per_mm_two_faces"] == pytest.approx(0.5026666667)
    assert h["shear_area_comparison"] == "not_below_reported_demand"
    assert v["bar_size_matches"] is True
    assert v["spacing_matches"] is False
    assert v["layer_spacing_mm"] == 230
    assert v["checked_spacing_mm"] == 250
    assert v["checked_cover_mm"] == 40
    assert v["cover_matches"] is False
    assert "cut_lengths" in r["missing_for_complete_detailing"]


def test_display_metres_and_database_mm_not_confused():
    layers, rows, overwrites, _ = inputs()
    for row in rows:
        row["BarSpacing"], row["ShearAv"] = ".25", ".0005"
    overwrites[0].update(EdgeBarSpc=".25", ClearCover=".04")
    r = reconcile_layers(layers, rows, overwrites, 6)
    assert r["layers"][1]["checked_spacing_mm"] == 250
    assert r["layers"][1]["layer_spacing_mm"] == 230
    assert r["layers"][0]["reported_shear_area_mm2_per_mm"] == 0.5


def test_equal_inputs_still_do_not_certify_detailing():
    layers, rows, overwrites, units = inputs()
    layers["areas"][0]["layers"] = [
        dict(layers["areas"][0]["layers"][1], BarSpacing=250.0, ClearCover=40.0)
    ]
    r = reconcile_layers(layers, rows, overwrites, units)
    assert r["status"] == "compared_inputs_match"
    assert r["complete_detailing"] is False


@pytest.mark.parametrize(
    "change",
    [
        "missing_overwrite",
        "duplicate_overwrite",
        "general",
        "stale_spacing",
        "mixed_stations",
        "missing_dc",
        "unknown_units",
    ],
)
def test_incomplete_or_incompatible_inputs_not_a_pass(change):
    layers, rows, overwrites, units = inputs()
    if change == "missing_overwrite":
        overwrites = []
    if change == "duplicate_overwrite":
        overwrites *= 2
    if change == "general":
        overwrites[0]["PierSecType"] = "General Reinforcing Section"
    if change == "stale_spacing":
        overwrites[0]["EdgeBarSpc"] = "300"
    if change == "mixed_stations":
        rows[1]["BarSpacing"] = "300"
    if change == "missing_dc":
        rows[0]["DCRatio"] = None
    if change == "unknown_units":
        layers["units_verified"] = False
    r = reconcile_layers(layers, rows, overwrites, units)
    assert r["status"] == "not_evaluated"
    assert r["complete_detailing"] is False


@pytest.mark.parametrize("value", [None, "NaN", "inf", "-1", "0", "Program Determined"])
def test_invalid_spacing_is_unknown_not_zero(value):
    layers, rows, overwrites, units = inputs()
    for r in rows:
        r["BarSpacing"] = value
    assert (
        reconcile_layers(layers, rows, overwrites, units)["status"] == "not_evaluated"
    )


@pytest.mark.parametrize("value", [0, 17, True, None])
def test_unknown_units_rejected(value):
    with pytest.raises(ValueError):
        length_unit(value)


def test_missing_story_pier_coverage_is_not_match():
    layers, rows, overwrites, units = inputs()
    rows.append(dict(rows[0], Story="L2"))
    assert (
        reconcile_layers(layers, rows, overwrites, units)["status"] == "not_evaluated"
    )


def test_empty_and_unsupported_layers_are_not_match():
    layers, rows, overwrites, units = inputs()
    layers["areas"][0]["layers"][0]["LayerType"] = 5
    assert (
        reconcile_layers(layers, rows, overwrites, units)["status"] == "not_evaluated"
    )
    layers["areas"][0]["layers"] = []
    assert (
        reconcile_layers(layers, rows, overwrites, units)["status"] == "not_evaluated"
    )


@pytest.mark.parametrize(
    "unit,factor",
    [
        (1, 25.4),
        (2, 304.8),
        (3, 25.4),
        (4, 304.8),
        (5, 1.0),
        (6, 1000.0),
        (13, 10.0),
        (16, 10.0),
    ],
)
def test_unit_conversion(unit, factor):
    assert length_unit(unit)[1] == factor
