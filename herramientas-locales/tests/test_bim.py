"""Pruebas con IFC e IDS reales, sintéticos y sin sesiones BIM abiertas."""

import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import pytest
from ifctester import ids

from cdcrd_local.bim import inspect_ifc, validate_ids


def make_model(path: Path, material: str | None = "CONCRETO") -> Path:
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name="Piloto CDCRD")
    millimetres = ifcopenshell.api.run(
        "unit.add_si_unit", model, unit_type="LENGTHUNIT", prefix="MILLI"
    )
    square_metres = ifcopenshell.api.run("unit.add_si_unit", model, unit_type="AREAUNIT")
    ifcopenshell.api.run("unit.assign_unit", model, units=[millimetres, square_metres])
    wall = ifcopenshell.api.run(
        "root.create_entity", model, ifc_class="IfcWall", name="Muro de prueba"
    )
    if material is not None:
        pset = ifcopenshell.api.run("pset.add_pset", model, product=wall, name="CDCRD_Informacion")
        ifcopenshell.api.run("pset.edit_pset", model, pset=pset, properties={"Material": material})
    model.write(str(path))
    return path


def make_ids(path: Path, version: str = "IFC4") -> Path:
    requirements = ids.Ids(title="Piloto informativo; no validación estructural")
    spec = ids.Specification(name="Muros con material", ifcVersion=[version], minOccurs=1)
    spec.applicability.append(ids.Entity(name="IFCWALL"))
    spec.requirements.append(
        ids.Property(propertySet="CDCRD_Informacion", baseName="Material", value="CONCRETO")
    )
    requirements.specifications.append(spec)
    assert requirements.to_xml(str(path))
    return path


def test_inventory_and_units_are_serializable(tmp_path):
    source = make_model(tmp_path / "model.ifc")
    original = source.read_bytes()
    result = inspect_ifc(source)
    assert result["schema"] == "IFC4"
    assert result["project_count"] == 1
    assert result["element_count"] == result["product_count"] == 1
    assert result["classes"] == {"IfcWall": 1}
    assert result["warnings"] == []
    assert any(unit.get("Prefix") == "MILLI" for unit in result["units"][0]["units"])
    json.dumps(result)
    assert source.read_bytes() == original


def test_missing_project_and_elements_are_visible(tmp_path):
    source = tmp_path / "empty.ifc"
    ifcopenshell.file(schema="IFC4").write(str(source))
    result = inspect_ifc(source)
    assert result["project_count"] == result["element_count"] == 0
    assert len(result["warnings"]) == 2


@pytest.mark.parametrize(
    "material, passed, failed", [("CONCRETO", 1, 0), (None, 0, 1), ("ACERO", 0, 1)]
)
def test_ids_checks_required_property(tmp_path, material, passed, failed):
    source = make_model(tmp_path / "model.ifc", material)
    requirements = make_ids(tmp_path / "requirements.ids")
    original_ifc, original_ids = source.read_bytes(), requirements.read_bytes()
    output = tmp_path / "reports" / "ids.html"
    result = validate_ids(source, requirements, output)
    assert result["tests_passed"] == passed
    assert result["tests_failed"] == failed
    assert result["status"] == ("failed" if failed else "passed")
    assert result["specs"][0]["applicable_elements"] == 1
    assert "<html" in output.read_text(encoding="utf-8").lower()
    assert source.read_bytes() == original_ifc
    assert requirements.read_bytes() == original_ids
    json.dumps(result)


def test_existing_report_preserved(tmp_path):
    source = make_model(tmp_path / "model.ifc")
    requirements = make_ids(tmp_path / "requirements.ids")
    output = tmp_path / "ids.html"
    output.write_text("INFORME ANTERIOR", encoding="utf-8")
    with pytest.raises(FileExistsError):
        validate_ids(source, requirements, output)
    assert output.read_text(encoding="utf-8") == "INFORME ANTERIOR"


def test_version_mismatch_is_not_passed(tmp_path):
    source = make_model(tmp_path / "model.ifc")
    requirements = make_ids(tmp_path / "requirements.ids", version="IFC2X3")
    result = validate_ids(source, requirements, tmp_path / "ids.html")
    assert result["status"] == "incomplete"
    assert result["specs_skipped"] == 1
    assert result["specs"][0]["ifc_version_matches"] is False
    assert result["specs_passed"] == 0


def test_required_entities_absent_fails_specification(tmp_path):
    source = tmp_path / "empty.ifc"
    ifcopenshell.file(schema="IFC4").write(str(source))
    requirements = make_ids(tmp_path / "requirements.ids")
    result = validate_ids(source, requirements, tmp_path / "ids.html")
    assert result["status"] == "failed"
    assert result["specs_failed"] == 1
    assert result["tests_failed"] == 0  # No hay elementos a los que aplicar facetas.


def test_invalid_and_missing_ifc_have_clear_errors(tmp_path):
    with pytest.raises(FileNotFoundError, match="No existe"):
        inspect_ifc(tmp_path / "missing.ifc")
    invalid = tmp_path / "invalid.ifc"
    invalid.write_text("no es un modelo IFC", encoding="utf-8")
    with pytest.raises(ValueError, match="No se pudo leer el IFC"):
        inspect_ifc(invalid)


def test_invalid_ids_does_not_create_report(tmp_path):
    source = make_model(tmp_path / "model.ifc")
    requirements = tmp_path / "invalid.ids"
    requirements.write_text("<otro/>", encoding="utf-8")
    output = tmp_path / "ids.html"
    with pytest.raises(ValueError, match="No se pudo leer el IDS"):
        validate_ids(source, requirements, output)
    assert not output.exists()


def test_conversion_units_retain_nested_factor(tmp_path):
    source = tmp_path / "feet.ifc"
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject")
    foot = ifcopenshell.api.run("unit.add_conversion_based_unit", model, name="foot")
    ifcopenshell.api.run("unit.assign_unit", model, units=[foot])
    model.write(str(source))
    result = inspect_ifc(source)
    unit = result["units"][0]["units"][0]
    assert unit["type"] == "IfcConversionBasedUnit"
    assert unit["ConversionFactor"]["ValueComponent"]["wrappedValue"] == pytest.approx(0.3048)
    assert unit["ConversionFactor"]["UnitComponent"]["Name"] == "METRE"
    json.dumps(result)


def test_project_without_units_is_visible(tmp_path):
    source = tmp_path / "unitless.ifc"
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject")
    model.write(str(source))
    result = inspect_ifc(source)
    assert result["units"][0]["units"] == []
    assert any("no declara unidades" in warning for warning in result["warnings"])
