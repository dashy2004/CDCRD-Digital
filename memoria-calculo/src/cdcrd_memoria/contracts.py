"""Versioned contract. Validation checks declarations, never engineering correctness."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")]
Text = Annotated[str, Field(min_length=1, max_length=2000)]
Number = StrictInt | Annotated[float, Field(strict=True, allow_inf_nan=False)]
Validation = Literal["verified", "pending", "contradicted"]
Topic = Literal[
    "geometry", "materials", "loads", "analysis", "drift", "stability", "geotechnical", "foundation"
]
PROFILE_TOPICS = list(Topic.__args__)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class Project(Record):
    id: Identifier
    name: Text
    revision: Text
    profile: Literal["structural_concrete_frame_v1"] = "structural_concrete_frame_v1"
    description: Text


class Source(Record):
    id: Identifier
    title: Text
    path: Text
    sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    kind: Literal["snapshot", "table", "document", "figure", "other"]


class DesignBasis(Record):
    normative_regime: Text | None = None
    edition: Text | None = None
    confirmation: Validation = "pending"
    source_id: Identifier | None = None
    reason: Text | None = None

    @model_validator(mode="after")
    def confirmed_basis(self):
        if self.confirmation == "verified" and not all((self.normative_regime, self.edition, self.source_id)):
            raise ValueError("La base confirmada necesita régimen, edición y fuente")
        return self


class Observation(Record):
    id: Identifier
    topic: Topic
    label: Text
    value: Number | Text | None
    unit: Text
    acquisition: Literal["read", "imported", "unavailable", "error"]
    validation: Validation = "pending"
    source_id: Identifier | None = None
    locator: Text | None = None
    reason: Text | None = None

    @model_validator(mode="after")
    def evidence(self):
        if isinstance(self.value, str) and self.unit != "texto":
            raise ValueError("Los valores textuales requieren unidad 'texto'; una magnitud necesita número JSON")
        if self.value is not None and not isinstance(self.value, str) and self.unit == "texto":
            raise ValueError("Una observación de texto no admite un valor numérico")
        if self.value is None:
            if not self.reason or self.validation == "verified":
                raise ValueError("Un valor ausente requiere motivo y no puede estar verificado")
        elif not self.source_id or not self.locator or self.acquisition in {"unavailable", "error"}:
            raise ValueError("Un valor presente requiere fuente, localizador y adquisición válida")
        return self


class Result(Record):
    id: Identifier
    label: Text
    value: Number | None
    unit: Text
    source_id: Identifier | None = None
    locator: Text | None = None
    model_id: Identifier | None = None
    model_revision: Text | None = None
    load_case: Text | None = None
    element_id: Text | None = None
    station: Number | None = None
    station_unit: Text | None = None
    coordinate_system: Text | None = None
    axis_definition: Text | None = None
    component: Text | None = None
    component_origin: Text | None = None
    validation: Validation = "pending"
    reason: Text | None = None

    @model_validator(mode="after")
    def evidence_and_axes(self):
        if self.value is None:
            if not self.reason or self.validation == "verified":
                raise ValueError("Resultado ausente: falta motivo o validación incorrecta")
        elif not all(
            (
                self.source_id,
                self.locator,
                self.model_id,
                self.model_revision,
                self.load_case,
                self.coordinate_system,
                self.axis_definition,
                self.component,
                self.component_origin,
            )
        ):
            raise ValueError("Resultado presente: faltan procedencia, caso o definición de ejes/componentes")
        if (self.station is None) != (self.station_unit is None):
            raise ValueError("La estación y su unidad deben declararse juntas")
        return self


class Calculation(Record):
    id: Identifier
    label: Text
    method: Text
    expression: Text
    input_ids: list[Identifier] = Field(min_length=1, max_length=100)
    value: Number | None
    unit: Text
    source_id: Identifier | None = None
    locator: Text | None = None
    validation: Validation = "pending"
    reason: Text | None = None

    @model_validator(mode="after")
    def recorded_only(self):
        if self.value is None and (not self.reason or self.validation == "verified"):
            raise ValueError("Cálculo pendiente requiere motivo y no puede verificarse")
        if self.value is not None and not all((self.source_id, self.locator)):
            raise ValueError("Cálculo registrado necesita fuente y localizador; no se ejecutan expresiones")
        return self


class Annex(Record):
    id: Identifier
    title: Text
    source_id: Identifier
    pages: list[Annotated[int, Field(strict=True, ge=1)]] | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def selection(self):
        if self.pages is not None and (not self.pages or len(set(self.pages)) != len(self.pages)):
            raise ValueError("Selección de páginas vacía o duplicada")
        return self


class Check(Record):
    topic: Topic
    applicability: Literal["required", "not_applicable"] = "required"
    validation: Validation = "pending"
    evidence_ids: list[Identifier] = Field(default_factory=list, max_length=100)
    reviewer: Text | None = None
    reason: Text

    @model_validator(mode="after")
    def reviewed(self):
        if self.validation == "verified" and not (self.evidence_ids and self.reviewer):
            raise ValueError("Comprobación verificada necesita evidencia y revisor")
        if self.applicability == "not_applicable" and self.validation != "verified":
            raise ValueError("No aplicable necesita justificación revisada y evidencia")
        return self


class Review(Record):
    engineering_approval: Literal[False] = False
    analysis_freshness: Literal["unverified"] = "unverified"
    reviewer: Text | None = None
    notes: Text = "Pendiente de revisión del ingeniero responsable."


class Dossier(Record):
    schema_version: Literal["cdcrd-design-memory/1"] = Field(alias="schema")
    project: Project
    design_basis: DesignBasis = Field(default_factory=DesignBasis)
    source_roots: list[Text] = Field(min_length=1, max_length=20)
    sources: list[Source] = Field(default_factory=list, max_length=100)
    observations: list[Observation] = Field(default_factory=list, max_length=10000)
    calculations: list[Calculation] = Field(default_factory=list, max_length=1000)
    results: list[Result] = Field(default_factory=list, max_length=10000)
    annexes: list[Annex] = Field(default_factory=list, max_length=100)
    checks: list[Check] = Field(default_factory=list, max_length=20)
    review: Review = Field(default_factory=Review)

    @model_validator(mode="after")
    def references(self):
        groups = [self.sources, self.observations, self.results, self.calculations, self.annexes]
        ids = [item.id for group in groups for item in group]
        if len(ids) != len(set(ids)):
            raise ValueError("Identificadores duplicados entre registros")
        source_ids = {s.id for s in self.sources}
        for item in [self.design_basis, *self.observations, *self.results, *self.calculations, *self.annexes]:
            if item.source_id is not None and item.source_id not in source_ids:
                raise ValueError(f"Fuente inexistente: {item.source_id}")
        for check in self.checks:
            if not set(check.evidence_ids) <= source_ids:
                raise ValueError("Comprobación con fuentes inexistentes")
        if len({c.topic for c in self.checks}) != len(self.checks):
            raise ValueError("Comprobaciones duplicadas para un tema")
        data_ids = {o.id for o in [*self.observations, *self.results]}
        for calculation in self.calculations:
            if not set(calculation.input_ids) <= data_ids:
                raise ValueError("Cálculo con entradas inexistentes o referencia circular")
        revisions: dict[str, str] = {}
        for result in self.results:
            if result.value is not None:
                if result.model_id in revisions and revisions[result.model_id] != result.model_revision:
                    raise ValueError("No se mezclan revisiones distintas del mismo modelo")
                revisions[result.model_id] = result.model_revision
        return self


def coverage(dossier: Dossier) -> dict:
    """Compute editorial readiness from declarations; never infer approval/freshness."""
    reasons = []
    if dossier.design_basis.confirmation != "verified":
        reasons.append("design_basis")
    checks = {c.topic: c for c in dossier.checks}
    for topic in PROFILE_TOPICS:
        if topic not in checks or checks[topic].validation != "verified":
            reasons.append(topic)
    for record in [*dossier.observations, *dossier.results, *dossier.calculations]:
        if record.value is None or record.validation != "verified":
            reasons.append(record.id)
    if not dossier.sources:
        reasons.append("sources")
    if not dossier.review.reviewer:
        reasons.append("reviewer")
    return {
        "status": "incomplete" if reasons else "declared_complete",
        "pending": reasons,
        "document_status": "draft" if reasons else "ready_for_review",
        "engineering_approval": False,
        "analysis_freshness": "unverified",
    }
