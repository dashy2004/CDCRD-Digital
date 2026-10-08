"""Inspección IFC y requisitos IDS locales; no certifica cumplimiento CDCRD."""

from collections import Counter
from pathlib import Path
from typing import Any


def _input_file(path: Path, suffix: str) -> Path:
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"No existe el archivo: {path}")
    if path.suffix.lower() != suffix:
        raise ValueError(f"Se requiere un archivo {suffix}: {path}")
    return path


def _open_ifc(source: Path) -> tuple[Path, Any]:
    source = _input_file(source, ".ifc")
    try:
        import ifcopenshell
    except ImportError as exc:
        raise RuntimeError(
            "Falta IfcOpenShell; instala el entorno de herramientas-locales."
        ) from exc
    try:
        model = ifcopenshell.open(str(source))
    except Exception as exc:
        raise ValueError(f"No se pudo leer el IFC '{source.name}': {exc}") from exc
    return source, model


def _unit_data(value: Any, ancestors: frozenset[int] = frozenset()) -> Any:
    """Convierte unidades SI, derivadas y factores de conversión a JSON."""
    if isinstance(value, (tuple, list)):
        return [_unit_data(item, ancestors) for item in value]
    if not hasattr(value, "is_a"):
        return value
    identifier = value.id()
    if identifier and identifier in ancestors:
        return {"id": identifier, "type": value.is_a()}
    ancestors = ancestors | {identifier} if identifier else ancestors
    return {
        key: _unit_data(item, ancestors)
        for key, item in value.get_info().items()
    }


def inspect_ifc(source: Path) -> dict[str, Any]:
    """Devuelve inventario y unidades declaradas sin modificar el modelo IFC."""
    source, model = _open_ifc(source)
    projects = model.by_type("IfcProject")
    elements = model.by_type("IfcElement")
    products = model.by_type("IfcProduct")
    warnings: list[str] = []
    if len(projects) != 1:
        warnings.append(f"Se esperaba un IfcProject; se encontraron {len(projects)}.")
    units = []
    for project in projects:
        assignment = project.UnitsInContext
        units.append({
            "project_id": project.id(),
            "project_name": project.Name,
            "units": _unit_data(assignment.Units) if assignment else [],
        })
        if not assignment or not assignment.Units:
            warnings.append(f"El proyecto #{project.id()} no declara unidades.")
    if not elements:
        warnings.append("El IFC no contiene IfcElement.")
    return {
        "source": str(source),
        "schema": model.schema_identifier,
        "project_count": len(projects),
        "entity_count": sum(1 for _ in model),
        "element_count": len(elements),
        "product_count": len(products),
        "classes": dict(sorted(Counter(item.is_a() for item in products).items())),
        "units": units,
        "warnings": warnings,
        "scope": (
            "Inventario IFC y unidades declaradas; no es una revisión estructural ni normativa."
        ),
    }


def validate_ids(ifc_path: Path, ids_path: Path, output: Path) -> dict[str, Any]:
    """Valida un IFC contra un IDS y escribe un HTML nuevo, sin sobrescribir."""
    output = Path(output).resolve()
    if output.suffix.lower() != ".html":
        raise ValueError("El informe IDS debe terminar en .html.")
    if output.exists():
        raise FileExistsError(f"El informe ya existe; elige otra ruta: {output}")
    ifc_path, model = _open_ifc(ifc_path)
    ids_path = _input_file(ids_path, ".ids")
    try:
        from ifctester import ids, reporter
    except ImportError as exc:
        raise RuntimeError("Falta IfcTester; instala el entorno de herramientas-locales.") from exc
    try:
        specification = ids.open(str(ids_path), validate=True)
    except Exception as exc:
        raise ValueError(f"No se pudo leer el IDS '{ids_path.name}': {exc}") from exc
    if not specification.specifications:
        raise ValueError("El IDS no contiene especificaciones.")
    # Las especificaciones de otra versión IFC quedan sin evaluar.
    specification.validate(model, should_filter_version=True, filepath=str(ifc_path))
    summary = reporter.Json(specification)
    results = summary.report()
    html = reporter.Html(specification)
    html.report()
    rendered = html.to_string()
    specs = []
    for spec in specification.specifications:
        status = "not_evaluated" if spec.status is None else ("passed" if spec.status else "failed")
        specs.append({
            "name": spec.name,
            "status": status,
            "ifc_version_matches": bool(spec.is_ifc_version),
            "applicable_elements": len(spec.applicable_entities),
        })
    specs_failed = sum(item["status"] == "failed" for item in specs)
    specs_passed = sum(item["status"] == "passed" for item in specs)
    specs_skipped = sum(item["status"] == "not_evaluated" for item in specs)
    status = "failed" if specs_failed else ("incomplete" if specs_skipped else "passed")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Modo exclusivo: tampoco sobrescribe si aparece un archivo durante la evaluación.
    with output.open("x", encoding="utf-8") as stream:
        stream.write(rendered)
    return {
        "source": str(ifc_path),
        "ids": str(ids_path),
        "report": str(output),
        "status": status,
        "tests_passed": results["total_checks_pass"],
        "tests_failed": results["total_checks_fail"],
        "specs_passed": specs_passed,
        "specs_failed": specs_failed,
        "specs_skipped": specs_skipped,
        "specs": specs,
        "scope": "Requisitos de información del IDS suministrado; no certifica cumplimiento CDCRD.",
    }
