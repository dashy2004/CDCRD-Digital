"""One presentation model for all formats. No numerical recalculation or axis mapping."""

from .contracts import Dossier, coverage

LABELS = {
    "pending": "Pendiente",
    "verified": "Verificado (declarado)",
    "contradicted": "Contradicho",
    "required": "Requerido",
    "not_applicable": "No aplica",
    "design_basis": "bases de diseño",
    "geometry": "geometría",
    "materials": "materiales",
    "loads": "cargas",
    "analysis": "análisis",
    "drift": "derivas",
    "stability": "estabilidad",
    "geotechnical": "geotecnia",
    "foundation": "cimentación",
    "sources": "fuentes",
    "reviewer": "revisor",
    "snapshot": "Captura",
    "table": "Tabla",
    "document": "Documento",
    "figure": "Figura",
    "other": "Otro",
    "read": "Leído",
    "imported": "Importado",
    "unavailable": "No disponible",
    "error": "Error de adquisición",
}


def _label(value):
    return LABELS.get(value, value)


def _display(value):
    return "PENDIENTE" if value is None else str(value)


def _table(title, columns, rows):
    return {"title": title, "columns": columns, "rows": rows}


def prepare(dossier: Dossier) -> dict:
    state = coverage(dossier)
    basis = dossier.design_basis
    sections = [
        {
            "title": "1. Alcance y estado",
            "paragraphs": [
                dossier.project.description,
                (
                    "Documento generado a partir de datos declarados y fuentes identificadas. "
                    "La validación del expediente no comprueba el diseño estructural."
                ),
                "Aprobación de ingeniería: NO. Vigencia del análisis: NO VERIFICADA.",
                dossier.review.notes,
            ],
            "tables": [],
        },
        {
            "title": "2. Bases de diseño",
            "paragraphs": [
                f"Régimen: {_display(basis.normative_regime)}. Edición: {_display(basis.edition)}.",
                f"Confirmación: {_label(basis.confirmation)}. Fuente: {_display(basis.source_id)}.",
                basis.reason or "La selección normativa corresponde al responsable del proyecto.",
            ],
            "tables": [],
        },
        {
            "title": "3. Datos de entrada",
            "paragraphs": [],
            "tables": [
                _table(
                    "Observaciones",
                    ["ID / dato", "Valor", "Unidad", "Fuente / localizador", "Validación"],
                    [
                        [
                            f"{o.id}: {o.label}",
                            _display(o.value),
                            o.unit,
                            f"{o.source_id or '-'} / {o.locator or '-'}"
                            + (f"; {o.reason}" if o.reason else ""),
                            f"{_label(o.validation)} / {_label(o.acquisition)}",
                        ]
                        for o in dossier.observations
                    ],
                )
            ],
        },
        {
            "title": "4. Cálculos registrados",
            "paragraphs": [
                "Las expresiones siguientes son registros documentales; este generador no las ejecuta."
            ],
            "tables": [],
        },
        {
            "title": "5. Resultados registrados",
            "paragraphs": [
                "Se conserva el sistema de referencia de origen. No se transforman fuerzas ni momentos."
            ],
            "tables": [],
        },
        {
            "title": "6. Cobertura y revisión",
            "paragraphs": [
                "Pendientes: "
                + (
                    ", ".join(_label(item) for item in state["pending"])
                    or "Ninguno declarado; requiere revisión técnica."
                ),
                "Revisor declarado: " + (dossier.review.reviewer or "PENDIENTE"),
            ],
            "tables": [
                _table(
                    "Comprobaciones declaradas",
                    ["Tema", "Aplicación", "Estado", "Evidencia / motivo"],
                    [
                        [
                            _label(c.topic),
                            _label(c.applicability),
                            _label(c.validation),
                            f"{', '.join(c.evidence_ids) or '-'}; {c.reason}; revisor: {c.reviewer or '-'}",
                        ]
                        for c in dossier.checks
                    ],
                )
            ],
        },
        {
            "title": "7. Registro de fuentes",
            "paragraphs": [
                (
                    "Los hashes SHA-256 completos se incluyen en manifest.json. "
                    "El identificador permite seguir cada dato hasta su documento de origen."
                )
            ],
            "tables": [
                _table(
                    "Fuentes",
                    ["ID", "Título", "Tipo", "SHA-256 (inicio)"],
                    [[s.id, s.title, _label(s.kind), s.sha256[:16]] for s in dossier.sources],
                )
            ],
        },
    ]
    for section in sections:
        section["tables"] = [table for table in section["tables"] if table["rows"]]
    if not dossier.observations:
        sections[2]["paragraphs"].append("No se han registrado datos de entrada.")
    if not dossier.calculations:
        sections[3]["paragraphs"] = ["No se han registrado cálculos en este expediente."]
    if not dossier.results:
        sections[4]["paragraphs"].append("No se han registrado resultados.")
    if not dossier.checks:
        sections[5]["paragraphs"].append("No se han registrado comprobaciones del responsable.")
    for c in dossier.calculations:
        sections[3]["paragraphs"].extend(
            [
                f"{c.id} — {c.label}: {_display(c.value)} {c.unit}. Estado: {_label(c.validation)}.",
                f"Método: {c.method}. Expresión: {c.expression}. Entradas: {', '.join(c.input_ids)}.",
                f"Fuente: {c.source_id or '-'} / {c.locator or '-'}. {c.reason or ''}",
            ]
        )
    for r in dossier.results:
        sections[4]["paragraphs"].extend(
            [
                f"{r.id} — {r.label}: {_display(r.value)} {r.unit}. Estado: {_label(r.validation)}.",
                (
                    f"Modelo: {r.model_id or '-'}, revisión: {r.model_revision or '-'}, "
                    f"caso/combinación: {r.load_case or '-'}, elemento: {r.element_id or '-'}."
                ),
                (
                    f"Sistema: {r.coordinate_system or '-'}; ejes: {r.axis_definition or '-'}; "
                    f"componente: {r.component or '-'}; origen: {r.component_origin or '-'}."
                ),
                f"Fuente: {r.source_id or '-'} / {r.locator or '-'}. {r.reason or ''}",
            ]
        )
        if r.station is not None:
            sections[4]["paragraphs"].append(f"Estación: {r.station} {r.station_unit}.")
    return {
        "title": "Memoria de diseño",
        "subtitle": dossier.project.name,
        "project_id": dossier.project.id,
        "revision": dossier.project.revision,
        "document_status": state["document_status"],
        "engineering_approval": False,
        "sections": sections,
        "annexes": [a.model_dump() for a in dossier.annexes],
    }
