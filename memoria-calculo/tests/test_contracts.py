from copy import deepcopy

import pytest
from pydantic import ValidationError

from cdcrd_memoria.compose import prepare
from cdcrd_memoria.contracts import PROFILE_TOPICS, Dossier, coverage


def test_absence_is_not_zero_and_prevents_readiness(dossier_data):
    observation = dossier_data["observations"][0]
    observation.update(value=None, acquisition="unavailable", reason="Falta documento")
    dossier = Dossier.model_validate(dossier_data)
    assert "O1" in coverage(dossier)["pending"]
    assert prepare(dossier)["sections"][2]["tables"][0]["rows"][0][1] == "PENDIENTE"


@pytest.mark.parametrize("value", [float("inf"), float("nan"), True, "NaN", "Infinity", "123"])
def test_invalid_numbers_rejected(dossier_data, value):
    dossier_data["observations"][0]["value"] = value
    with pytest.raises(ValidationError):
        Dossier.model_validate(dossier_data)


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d["observations"][0].pop("unit"),
        lambda d: d["observations"][0].update(source_id="NO-SOURCE"),
        lambda d: d["observations"][0].update(value=None, validation="verified", reason="Missing"),
        lambda d: d["observations"].append(deepcopy(d["observations"][0])),
        lambda d: d.update(review={"engineering_approval": True}),
        lambda d: d.update(review={"analysis_freshness": "evidenced"}),
        lambda d: d["project"].update(profile="unsupported_profile"),
        lambda d: d.update(coverage={"status": "complete"}),
        lambda d: d.update(design_basis={"confirmation": "verified"}),
        lambda d: d.update(
            checks=[{"topic": "foundation", "applicability": "not_applicable", "reason": "Excluded"}]
        ),
    ],
)
def test_rejects_unsubstantiated_contracts(dossier_data, edit):
    edit(dossier_data)
    with pytest.raises(ValidationError):
        Dossier.model_validate(dossier_data)


def _result(**overrides):
    return {
        "id": "R1",
        "label": "Fuerza local",
        "value": 123.123456789,
        "unit": "kN",
        "source_id": "S1",
        "locator": "table/row1",
        "model_id": "M1",
        "model_revision": "R00",
        "load_case": "C1",
        "coordinate_system": "Local",
        "axis_definition": "1 girado 30 grados desde X; 3 vertical",
        "component": "F1",
        "component_origin": "Extremo I de B1",
        **overrides,
    }


def test_rotated_axes_preserved_without_implicit_conversion(dossier_data):
    dossier_data["results"] = [_result()]
    dossier = Dossier.model_validate(dossier_data)
    text = " ".join(prepare(dossier)["sections"][4]["paragraphs"])
    assert "123.123456789" in text and "30 grados" in text and "F1" in text
    assert dossier.results[0].coordinate_system == "Local"


@pytest.mark.parametrize(
    "field",
    [
        "coordinate_system",
        "axis_definition",
        "component",
        "component_origin",
        "model_id",
        "model_revision",
        "load_case",
        "locator",
    ],
)
def test_present_results_require_reference_frame(dossier_data, field):
    result = _result()
    result[field] = None
    dossier_data["results"] = [result]
    with pytest.raises(ValidationError):
        Dossier.model_validate(dossier_data)


def test_multiple_models_allowed_but_no_mixing_revisions(dossier_data):
    dossier_data["results"] = [_result(), _result(id="R2", model_id="M2", model_revision="R01")]
    Dossier.model_validate(dossier_data)
    dossier_data["results"][1]["model_id"] = "M1"
    with pytest.raises(ValidationError, match="revisiones"):
        Dossier.model_validate(dossier_data)


def test_complete_declarations_never_approve_engineering(dossier_data):
    dossier_data["design_basis"] = {
        "normative_regime": "Régimen ficticio",
        "edition": "DEMO",
        "confirmation": "verified",
        "source_id": "S1",
    }
    dossier_data["observations"][0]["validation"] = "verified"
    dossier_data["checks"] = [
        {
            "topic": t,
            "validation": "verified",
            "evidence_ids": ["S1"],
            "reviewer": "Revisor ficticio",
            "reason": "Solo prueba",
        }
        for t in PROFILE_TOPICS
    ]
    dossier_data["review"] = {"reviewer": "Revisor ficticio"}
    result = coverage(Dossier.model_validate(dossier_data))
    assert result["document_status"] == "ready_for_review"
    assert result["engineering_approval"] is False and result["analysis_freshness"] == "unverified"
