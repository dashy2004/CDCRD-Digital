"""Small local DXF plans; coordinates and dimension offsets use the declared unit.

This input is deliberately separate from the Revit proyecto.json schema. These
are drawing primitives, not structural calculations or approved construction
documents. The ezdxf/Matplotlib preview may differ from AutoCAD/Revit fonts and
dimension rendering; inspect the DXF in the target CAD application before use.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

import ezdxf
from ezdxf import bbox, units
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from shapely.geometry import Polygon


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


Point = tuple[float, float]


class _Outline(_Input):
    id: str = Field(min_length=1, max_length=100)
    points: list[Point] = Field(min_length=3)
    layer: str = "E-LOS"

    @field_validator("layer")
    @classmethod
    def valid_layer(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
            raise ValueError("layer must use 1–80 letters, digits, underscores or hyphens")
        return value

    @model_validator(mode="after")
    def valid_polygon(self) -> _Outline:
        polygon = Polygon(self.points)
        if (
            not polygon.is_valid
            or polygon.is_empty
            or polygon.area <= 0
            or not math.isfinite(polygon.area)
        ):
            raise ValueError(
                f"outline {self.id!r} must form a valid closed polygon with positive area"
            )
        return self


class _Dimension(_Input):
    p1: Point
    p2: Point
    offset: float

    @model_validator(mode="after")
    def valid_dimension(self) -> _Dimension:
        if self.p1 == self.p2:
            raise ValueError("dimension endpoints must differ")
        if not math.isfinite(math.dist(self.p1, self.p2)):
            raise ValueError("dimension measurement must be finite")
        if self.offset == 0:
            raise ValueError("dimension offset must be nonzero")
        return self


class _Note(_Input):
    text: str = Field(min_length=1, max_length=1000)
    position: Point

    @field_validator("text")
    @classmethod
    def plain_text(cls, value: str) -> str:
        if any(ord(char) < 32 for char in value):
            raise ValueError("notes must contain single-line text without control characters")
        return value


class _Plan(_Input):
    name: str = Field(min_length=1, max_length=200)
    units: Literal["m", "mm"]
    outlines: list[_Outline] = Field(min_length=1)
    dimensions: list[_Dimension] = Field(default_factory=list)
    notes: list[_Note] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self) -> _Plan:
        ids = [outline.id for outline in self.outlines]
        if len(set(ids)) != len(ids):
            raise ValueError("outline IDs must be unique")
        return self


@contextmanager
def _new_output(path: Path, *, binary: bool = False):
    """Reserve a new file atomically; on failure remove only our own inode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("xb" if binary else "x", **({} if binary else {"encoding": "utf-8"}))
    identity = path.stat()
    try:
        with stream:
            yield stream
    except BaseException:
        try:
            current = path.stat()
            if (identity.st_dev, identity.st_ino) == (current.st_dev, current.st_ino):
                path.unlink()
        except FileNotFoundError:
            pass
        raise


def _load_dxf(source: Path):
    try:
        return ezdxf.readfile(source)
    except (ezdxf.DXFError, UnicodeError, OSError) as exc:
        raise ValueError(f"Cannot read DXF {source}: {exc}") from exc


def _report(document, source: Path) -> dict:
    auditor = document.audit()
    if auditor.errors:
        raise ValueError(f"DXF audit failed with {len(auditor.errors)} unresolved errors")
    modelspace = document.modelspace()
    try:
        bounds = bbox.extents(modelspace)
    except Exception as exc:
        raise ValueError(f"Cannot compute DXF bounds: {exc}") from exc
    return {
        "path": str(source.resolve()),
        "dxf_version": document.dxfversion,
        "units": {units.M: "m", units.MM: "mm"}.get(document.units, "other"),
        "insunits": document.units,
        "entities": dict(sorted(Counter(entity.dxftype() for entity in modelspace).items())),
        "layers": sorted(layer.dxf.name for layer in document.layers),
        "bounds": {"min": list(bounds.extmin), "max": list(bounds.extmax)}
        if bounds.has_data
        else None,
        "audit": {"errors": 0, "repairs": len(auditor.fixes)},
    }


def generate_plan(source: Path, output: Path) -> dict:
    """Generate a R2018 DXF from a validated, explicitly unit-tagged JSON plan.

    Dimension endpoints are used as supplied, with no inferred snapping. All
    coordinates, offsets, and resulting native dimensions share the same unit.
    Existing output files are never overwritten.
    """
    source, output = Path(source), Path(output)
    if output.suffix.lower() != ".dxf":
        raise ValueError("output must have the .dxf extension")
    try:
        plan = _Plan.model_validate_json(source.read_text(encoding="utf-8"))
    except (ValidationError, UnicodeError, OSError) as exc:
        raise ValueError(f"Invalid plan JSON {source}: {exc}") from exc

    document = ezdxf.new("R2018", setup=True)
    document.units = units.M if plan.units == "m" else units.MM
    document.header["$MEASUREMENT"] = 1
    scale = 1.0 if plan.units == "m" else 1000.0
    # 1:50 plan convention: 2.5 mm printed text occupies 0.125 m in model space.
    document.dimstyles.new(
        "CDX_METRIC",
        dxfattribs={
            "dimtxt": 0.125 * scale,
            "dimasz": 0.125 * scale,
            "dimexo": 0.05 * scale,
            "dimexe": 0.1 * scale,
            "dimgap": 0.05 * scale,
            "dimlfac": 1.0,
            "dimdec": 3 if plan.units == "m" else 1,
            "dimzin": 8,
        },
    )
    for layer_name in sorted(
        {"E-LOS", "E-COT", "E-TEX", *(outline.layer for outline in plan.outlines)}
    ):
        document.layers.new(layer_name)
    modelspace = document.modelspace()
    for outline in plan.outlines:
        modelspace.add_lwpolyline(outline.points, close=True, dxfattribs={"layer": outline.layer})
    for dimension in plan.dimensions:
        modelspace.add_aligned_dim(
            p1=dimension.p1,
            p2=dimension.p2,
            distance=dimension.offset,
            dimstyle="CDX_METRIC",
            dxfattribs={"layer": "E-COT"},
        ).render()
    for note in plan.notes:
        modelspace.add_text(
            note.text,
            dxfattribs={
                "layer": "E-TEX",
                "height": 0.125 * scale,
                "insert": note.position,
            },
        )
    document.header["$PROJECTNAME"] = plan.name
    with _new_output(output) as stream:
        document.write(stream)
        stream.flush()
        report = _report(_load_dxf(output), output)
    report["name"] = plan.name
    return report


def inspect_dxf(source: Path) -> dict:
    """Read, audit and summarize a DXF without modifying the source file.

    ezdxf may repair an in-memory document during auditing; the report includes
    those repairs. No repaired data is written back to the original file.
    """
    source = Path(source)
    return _report(_load_dxf(source), source)


def preview_dxf(source: Path, output: Path) -> dict:
    """Render SVG, PNG or PDF headlessly through ezdxf and Matplotlib.

    Fonts, hatch styles, external references and CAD-specific objects may have
    renderer differences. This preview is a visual aid, not conversion parity.
    """
    source, output = Path(source), Path(output)
    format_name = output.suffix.lower().lstrip(".")
    if format_name not in {"svg", "png", "pdf"}:
        raise ValueError("preview output must be SVG, PNG or PDF")
    document = _load_dxf(source)
    report = _report(document, source)
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(12, 8), dpi=150)
    FigureCanvasAgg(figure)
    axes = figure.add_axes((0, 0, 1, 1))
    try:
        with _new_output(output, binary=True) as stream:
            config = Configuration(background_policy=BackgroundPolicy.WHITE,
                                   color_policy=ColorPolicy.BLACK)
            Frontend(RenderContext(document), MatplotlibBackend(axes), config=config).draw_layout(
                document.modelspace(), finalize=True
            )
            figure.savefig(stream, format=format_name, dpi=150)
    except FileExistsError:
        raise
    except Exception as exc:
        raise ValueError(f"Cannot render DXF preview: {exc}") from exc
    finally:
        figure.clear()
    return {
        "source": report["path"],
        "path": str(output.resolve()),
        "format": format_name,
        "renderer": "ezdxf + Matplotlib (headless)",
        "limitation": "Preview appearance may differ from the target CAD application.",
    }
