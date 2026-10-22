"""Bounded, read-only ETABS observations. No COM imports or guessed defaults.

``read(path, *args)`` is injected by the STA adapter. Contracts come from the
ETABSv1 typelib and REA evidence in docs/AUDITOR-ETABS.md, not the shared SAP API.
"""

import math
from datetime import UTC, datetime
from pathlib import PureWindowsPath
from typing import Any
from uuid import uuid4

from wall_results import display_rows

SCHEMA = "cdcrd-etabs-capture/1"
MISSING = object()
UNIT_NAMES = (
    "lb_in_F",
    "lb_ft_F",
    "kip_in_F",
    "kip_ft_F",
    "kN_mm_C",
    "kN_m_C",
    "kgf_mm_C",
    "kgf_m_C",
    "N_mm_C",
    "N_m_C",
    "tonf_mm_C",
    "tonf_m_C",
    "kN_cm_C",
    "kgf_cm_C",
    "N_cm_C",
    "tonf_cm_C",
)
LENGTH_TO_M = (
    0.0254,
    0.3048,
    0.0254,
    0.3048,
    0.001,
    1.0,
    0.001,
    1.0,
    0.001,
    1.0,
    0.001,
    1.0,
    0.01,
    0.01,
    0.01,
    0.01,
)
SHELL_TYPES = {1: "Shell-Thin", 2: "Shell-Thick", 3: "Membrane", 6: "Layered"}
SLAB_TYPES = {
    0: "Slab",
    1: "Drop",
    2: "Stiff_DO_NOT_USE",
    3: "Ribbed",
    4: "Waffle",
    5: "Mat",
    6: "Footing",
}
LOAD_TYPES = {
    1: "Dead",
    2: "SuperDead",
    3: "Live",
    4: "ReduceLive",
    5: "Seismic",
    6: "Wind",
    7: "Snow",
    8: "Other",
    11: "RoofLive",
}
READ_METHODS = frozenset(
    {
        "GetModelFilename",
        "GetPresentUnits",
        "GetModelIsLocked",
        "GetVersion",
        "Story.GetStories_2",
        "Analyze.GetCaseStatus",
        "LoadCases.GetTypeOAPI",
        "LoadCases.ModalEigen.GetNumberModes",
        "LoadCases.ModalRitz.GetNumberModes",
        "LoadPatterns.GetNameList",
        "LoadPatterns.GetLoadType",
        "LoadPatterns.GetSelfWTMultiplier",
        "PropArea.GetNameList",
        "PropArea.GetTypeOAPI",
        "PropArea.GetSlab",
        "PropArea.GetSlabRibbed",
        "PropArea.GetSlabWaffle",
        "PropMaterial.GetNameList",
        "PropMaterial.GetMaterial",
        "PointObj.GetNameList",
        "PointObj.GetCoordCartesian",
        "PointObj.GetRestraint",
        "PointObj.GetDiaphragm",
        "PointObj.GetLabelFromName",
        "FrameObj.GetNameList",
        "FrameObj.GetPoints",
        "FrameObj.GetSection",
        "FrameObj.GetEndLengthOffset",
        "AreaObj.GetNameList",
        "AreaObj.GetPoints",
        "AreaObj.GetProperty",
        "AreaObj.GetOpening",
        "AreaObj.GetDiaphragm",
        "AreaObj.GetLabelFromName",
        "AreaObj.GetDesignOrientation",
        "AreaObj.GetLoadUniform",
        "AreaObj.GetLoadUniformToFrame",
        "DatabaseTables.GetTableForDisplayArray",
    }
)


def text(value):
    if type(value) is not str:
        raise ValueError("Se esperaba texto")
    return value


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Se esperaba numero finito")
    return value


def integer(value):
    if type(value) is not int:
        raise ValueError("Se esperaba entero (no booleano)")
    return value


def boolean(value):
    if type(value) is not bool:
        raise ValueError("Se esperaba booleano")
    return value


def outputs(result, count):
    if (
        not isinstance(result, (list, tuple))
        or len(result) != count + 1
        or type(result[-1]) is not int
        or result[-1] != 0
    ):
        raise ValueError(f"Contrato OAPI invalido: {count} salidas y ret=0 requeridos")
    return result[:-1]


def array(value, count, convert):
    if value is None and count == 0:
        return []
    if not isinstance(value, (list, tuple)) or len(value) != count:
        raise ValueError("Longitud de array distinta del conteo")
    return [convert(v) for v in value]


def counted(result, converters, limit):
    vals = outputs(result, len(converters) + 1)
    n = integer(vals[0])
    if not 0 <= n <= limit:
        raise ValueError(f"Conteo fuera del limite 0..{limit}; no se trunca")
    columns = [array(v, n, fn) for v, fn in zip(vals[1:], converters)]
    return list(zip(*columns))


def names(result, limit):
    result = [r[0] for r in counted(result, [text], limit)]
    if len(set(result)) != len(result) or any(not x for x in result):
        raise ValueError("Nombres vacios o duplicados")
    return result


def model_path(value):
    p = PureWindowsPath(text(value))
    if not p.is_absolute() or p.suffix.lower() != ".edb":
        raise ValueError("Se requiere ruta Windows absoluta del modelo .EDB")
    return p


def mass_source(result):
    """Known ETABS table schema; continuation rows inherit only their source."""
    rows = display_rows(result)
    fields = {
        "Name",
        "IsDefault",
        "SourceSelf",
        "SourceAdded",
        "SourceLoads",
        "IncLateral",
        "IncVertical",
        "LoadPattern",
        "Multiplier",
    }
    if not rows or not fields <= rows[0].keys():
        raise ValueError("Fuente de masa vacia o esquema desconocido")
    groups = {}
    current = None
    for row in rows:
        if row["Name"]:
            current = row["Name"]
            groups.setdefault(current, [])
        if current is None:
            raise ValueError("Fila de masa sin fuente")
        groups[current].append(row)
    selected = []
    for members in groups.values():
        head = members[0]
        if head["IsDefault"] not in ("Yes", "No"):
            raise ValueError("IsDefault desconocido")
        for row in members[1:]:
            for key in fields - {"Name", "LoadPattern", "Multiplier"}:
                if row[key] not in (None, "", head[key]):
                    raise ValueError("Flags contradictorios en fuente de masa")
        if head["IsDefault"] != "Yes":
            continue
        flags = {}
        for out, key in (
            ("source_self", "SourceSelf"),
            ("source_added", "SourceAdded"),
            ("source_loads", "SourceLoads"),
            ("lateral", "IncLateral"),
            ("vertical", "IncVertical"),
        ):
            if head[key] not in ("Yes", "No"):
                raise ValueError(f"Flag de masa desconocido: {key}")
            flags[out] = head[key] == "Yes"
        factors = {}
        for row in members:
            pat = row["LoadPattern"]
            if not pat and not flags["source_loads"] and not row["Multiplier"]:
                continue
            if not pat or pat in factors:
                raise ValueError("Patron de masa vacio o duplicado")
            factor = number(float(row["Multiplier"]))
            if factor < 0:
                raise ValueError("Factor de masa negativo")
            factors[pat] = factor
        selected.append({**flags, "factors": factors})
    if len(selected) != 1:
        raise ValueError("Debe existir una unica fuente de masa predeterminada")
    return selected[0]


class Collector:
    def __init__(self, read, expected_path, process_id, max_objects):
        self.read = read
        self.expected = model_path(expected_path)
        if type(process_id) is not int or process_id <= 0:
            raise ValueError("PID positivo explicito requerido")
        if type(max_objects) is not int or not 1 <= max_objects <= 20000:
            raise ValueError("max_objects debe estar entre 1 y 20000")
        self.process_id, self.limit = process_id, max_objects
        self.observations = []
        self.snapshot = {}
        self.calls = 0

    def probe(self, section, obj, field, operation, args, decode) -> Any:
        # OAPI decoders validate heterogeneous payloads before this boundary.
        if operation not in READ_METHODS:
            raise ValueError("Operacion fuera de la lista de lecturas")
        record = {
            "id": f"E{len(self.observations) + 1:06d}",
            "section": section,
            "object": obj,
            "field": field,
            "operation": operation,
            "arguments": list(args),
        }
        self.observations.append(record)
        try:
            if self.calls >= 200000:
                raise ValueError("Limite de 200000 llamadas alcanzado")
            self.calls += 1
            value = decode(self.read(operation, *args))
            record.update(status="read", value=value)
            return value
        except AttributeError as exc:
            record.update(status="unavailable", message=str(exc)[:1000])
        except Exception as exc:  # noqa: BLE001 -- COM failures become explicit field evidence.
            record.update(status="error", message=f"{type(exc).__name__}: {exc}"[:1000])
        return MISSING

    def pending(self, section, obj, field, reason):
        self.observations.append(
            {
                "id": f"E{len(self.observations) + 1:06d}",
                "section": section,
                "object": obj,
                "field": field,
                "status": "pending",
                "message": reason,
            }
        )

    def put(self, row, section, obj, field, operation, args, decode):
        value = self.probe(section, obj, field, operation, args, decode)
        if value is not MISSING:
            row[field] = value
        return value

    def inventory(self, owner):
        return self.probe(
            owner,
            "inventory",
            "names",
            owner + ".GetNameList",
            (),
            lambda r: names(r, self.limit),
        )

    def boundary(self):
        path = self.probe(
            "identity", "model", "model_path", "GetModelFilename", (), text
        )
        units = self.probe("identity", "model", "units", "GetPresentUnits", (), integer)
        locked = self.probe(
            "identity", "model", "locked", "GetModelIsLocked", (), boolean
        )
        if path is MISSING or model_path(path) != self.expected:
            raise ValueError("Identidad del modelo no coincide con el EDB solicitado")
        if units is MISSING or not 1 <= units <= len(UNIT_NAMES) or locked is MISSING:
            raise ValueError("No se pueden acreditar unidades/bloqueo del modelo")
        return {"model_path": path, "units_enum": units, "locked": locked}

    def stories(self, scale):
        def decode(r):
            v = outputs(r, 10)
            base = number(v[0]) * scale
            n = integer(v[1])
            if not 0 <= n <= self.limit:
                raise ValueError("Conteo de niveles invalido")
            columns = [
                array(a, n, conv)
                for a, conv in zip(
                    v[2:],
                    (text, number, number, boolean, text, boolean, number, integer),
                )
            ]
            if len(set(columns[0])) != n:
                raise ValueError("Niveles duplicados")
            return {
                "base_elevation_m": base,
                "stories": [
                    {"name": a, "elevation_m": b * scale, "height_m": c * scale}
                    for a, b, c in zip(*columns[:3])
                ],
            }

        value = self.probe(
            "stories", "inventory", "levels", "Story.GetStories_2", (), decode
        )
        if value is not MISSING:
            self.snapshot.update(value)

    def patterns(self, inventory):
        if inventory is MISSING:
            return
        rows = []
        for name in inventory:
            row = {"name": name}
            self.put(
                row,
                "patterns",
                name,
                "type",
                "LoadPatterns.GetLoadType",
                (name,),
                lambda r: LOAD_TYPES.get(
                    integer(outputs(r, 1)[0]), f"Unknown({outputs(r, 1)[0]})"
                ),
            )
            self.put(
                row,
                "patterns",
                name,
                "self_weight",
                "LoadPatterns.GetSelfWTMultiplier",
                (name,),
                lambda r: number(outputs(r, 1)[0]),
            )
            rows.append(row)
        self.snapshot["patterns"] = rows

    def definitions(self, inventory, scale):
        if inventory is MISSING:
            return
        rows, unknown = [], []
        for name in inventory:
            kind = self.probe(
                "slab_definitions",
                name,
                "property_type",
                "PropArea.GetTypeOAPI",
                (name,),
                lambda r: integer(outputs(r, 1)[0]),
            )
            if kind is MISSING:
                unknown.append(name)
                continue
            if kind != 2:  # Wall=1, Slab=2, Deck=3. Never treat a wall as a slab.
                continue
            row = {"name": name}

            def slab(r):
                t, shell, mat, thick, color, notes, guid = outputs(r, 7)
                integer(color)
                text(notes)
                text(guid)
                return {
                    "type": SLAB_TYPES.get(integer(t), f"Unknown({t})"),
                    "modeling_type": SHELL_TYPES.get(
                        integer(shell), f"Unknown({shell})"
                    ),
                    "material": text(mat),
                    "h_m": number(thick) * scale,
                }

            values = self.probe(
                "slab_definitions",
                name,
                "definition",
                "PropArea.GetSlab",
                (name,),
                slab,
            )
            if values is not MISSING:
                row.update(values)
                if row["type"] in ("Ribbed", "Waffle"):
                    method = "PropArea.GetSlab" + row["type"]
                    vals = self.probe(
                        "slab_definitions",
                        name,
                        "rib_geometry",
                        method,
                        (name,),
                        lambda r: [number(v) for v in outputs(r, 6)],
                    )
                    if vals is not MISSING:
                        row.update(h_m=vals[0] * scale, topping_m=vals[1] * scale)
            rows.append(row)
        self.snapshot["slab_definitions"] = rows
        if unknown:
            self.snapshot["unclassified_area_definitions"] = unknown

    def points(self, inventory, scale):
        if inventory is MISSING:
            return {}
        rows, vertices = [], {}
        for name in inventory:
            row = {"id": name}
            xyz = self.put(
                row,
                "joints",
                name,
                "xyz_m",
                "PointObj.GetCoordCartesian",
                (name,),
                lambda r: [number(v) * scale for v in outputs(r, 3)],
            )
            if xyz is not MISSING:
                vertices[name] = xyz
                row["z_m"] = xyz[2]
                if "base_elevation_m" in self.snapshot:
                    row["at_base"] = (
                        abs(xyz[2] - self.snapshot["base_elevation_m"]) <= 1e-6
                    )
            self.put(
                row,
                "joints",
                name,
                "restraints",
                "PointObj.GetRestraint",
                (name,),
                lambda r: array(outputs(r, 1)[0], 6, boolean),
            )

            def diaphragm(r):
                option, label = outputs(r, 2)
                integer(option)
                text(label)
                if option == 1:
                    return ""
                if option == 2:
                    return "From Shell Object"
                if option == 3 and label:
                    return label
                raise ValueError("Opcion de diafragma desconocida")

            self.put(
                row,
                "joints",
                name,
                "diaphragm",
                "PointObj.GetDiaphragm",
                (name,),
                diaphragm,
            )
            self.put(
                row,
                "joints",
                name,
                "story",
                "PointObj.GetLabelFromName",
                (name,),
                lambda r: text(outputs(r, 2)[1]),
            )
            rows.append(row)
        self.snapshot["joints"] = rows
        return vertices

    def frames(self, inventory, vertices):
        if inventory is MISSING:
            return
        rows = []
        for name in inventory:
            row = {"id": name}
            pts = self.put(
                row,
                "frames",
                name,
                "points",
                "FrameObj.GetPoints",
                (name,),
                lambda r: [text(v) for v in outputs(r, 2)],
            )
            if pts is not MISSING and all(p in vertices for p in pts):
                row["vertices_m"] = [vertices[p] for p in pts]
            self.put(
                row,
                "frames",
                name,
                "section",
                "FrameObj.GetSection",
                (name,),
                lambda r: text(outputs(r, 2)[0]),
            )

            def offsets(r):
                auto, one, two, rz = outputs(r, 4)
                boolean(auto)
                number(one)
                number(two)
                return number(rz)

            self.put(
                row,
                "frames",
                name,
                "rigid_zone_factor",
                "FrameObj.GetEndLengthOffset",
                (name,),
                offsets,
            )
            rows.append(row)
        self.snapshot["frames"] = rows

    def areas(self, inventory, vertices):
        if inventory is MISSING:
            return
        slabs, walls, unknown = [], [], []
        for name in inventory:
            row = {"id": name}
            orientation = self.put(
                row,
                "areas",
                name,
                "orientation",
                "AreaObj.GetDesignOrientation",
                (name,),
                lambda r: integer(outputs(r, 1)[0]),
            )
            pts = self.put(
                row,
                "areas",
                name,
                "points",
                "AreaObj.GetPoints",
                (name,),
                lambda r: names(r, self.limit),
            )
            if pts is not MISSING and all(p in vertices for p in pts):
                row["vertices_m"] = [vertices[p] for p in pts]
            self.put(
                row,
                "areas",
                name,
                "section",
                "AreaObj.GetProperty",
                (name,),
                lambda r: text(outputs(r, 1)[0]),
            )
            self.put(
                row,
                "areas",
                name,
                "is_opening",
                "AreaObj.GetOpening",
                (name,),
                lambda r: boolean(outputs(r, 1)[0]),
            )
            self.put(
                row,
                "areas",
                name,
                "story",
                "AreaObj.GetLabelFromName",
                (name,),
                lambda r: text(outputs(r, 2)[1]),
            )
            self.put(
                row,
                "areas",
                name,
                "diaphragm",
                "AreaObj.GetDiaphragm",
                (name,),
                lambda r: text(outputs(r, 1)[0]),
            )
            for suffix, field, converters in (
                ("", "uniform_loads", [text, text, text, integer, number]),
                (
                    "ToFrame",
                    "uniform_to_frame_loads",
                    [text, text, text, integer, number, integer],
                ),
            ):
                keys = ["area", "pattern", "csys", "direction", "value"] + (
                    ["distribution"] if suffix else []
                )
                self.put(
                    row,
                    "areas",
                    name,
                    field,
                    "AreaObj.GetLoadUniform" + suffix,
                    (name,),
                    lambda r, keys=keys, conv=converters: [
                        dict(zip(keys, vals)) for vals in counted(r, conv, self.limit)
                    ],
                )
            self.pending(
                "areas",
                name,
                "mesh",
                "Mallado no expuesto por AreaObj en este contrato ETABS; no inferido",
            )
            if orientation == 2:
                self.pending(
                    "slabs",
                    name,
                    "design_context",
                    "Direccion resistente, apoyo, cuerpo estructural y componentes semanticos de carga requieren planos",
                )
                slabs.append(row)
            elif orientation == 1:
                walls.append(row)
            else:
                unknown.append(row)
        self.snapshot.update(slabs=slabs, walls=walls, unclassified_areas=unknown)

    def modal(self, name):
        if not name:
            self.pending(
                "settings",
                "modal",
                "modal_max_modes",
                "Seleccionar explicitamente modal_case",
            )
            return
        kind = self.probe(
            "settings",
            name,
            "case_type",
            "LoadCases.GetTypeOAPI",
            (name,),
            lambda r: [integer(v) for v in outputs(r, 2)],
        )
        if kind is MISSING:
            return
        if kind[0] != 3 or kind[1] not in (1, 2):
            self.pending(
                "settings",
                name,
                "modal_max_modes",
                "Caso no modal Eigen/Ritz reconocido",
            )
            return
        path = (
            "LoadCases."
            + ("ModalEigen" if kind[1] == 1 else "ModalRitz")
            + ".GetNumberModes"
        )
        self.put(
            self.snapshot,
            "settings",
            name,
            "modal_max_modes",
            path,
            (name,),
            lambda r: integer(outputs(r, 2)[0]),
        )


def collect_snapshot(
    read, expected_model_path, process_id, modal_case="", max_objects=10000
):
    """Capture getters only; unavailable observations remain absent, never zero.

    Boundary checks detect file/unit/lock or inventory changes, not every possible
    edit within the same model. The caller must hold the application's turn.
    """
    if type(modal_case) is not str:
        raise ValueError("modal_case debe ser texto")
    c = Collector(read, expected_model_path, process_id, max_objects)
    started = datetime.now(UTC).isoformat()
    before = c.boundary()
    units = before["units_enum"]
    c.snapshot.update(model_path=before["model_path"], units=UNIT_NAMES[units - 1])
    version = c.probe(
        "identity",
        "model",
        "version",
        "GetVersion",
        (),
        lambda r: {
            "version": text(outputs(r, 2)[0]),
            "number": number(outputs(r, 2)[1]),
        },
    )
    c.stories(LENGTH_TO_M[units - 1])
    inventories = {
        owner: c.inventory(owner)
        for owner in (
            "PointObj",
            "FrameObj",
            "AreaObj",
            "PropArea",
            "PropMaterial",
            "LoadPatterns",
        )
    }
    c.patterns(inventories["LoadPatterns"])
    c.definitions(inventories["PropArea"], LENGTH_TO_M[units - 1])
    vertices = c.points(inventories["PointObj"], LENGTH_TO_M[units - 1])
    c.frames(inventories["FrameObj"], vertices)
    c.areas(inventories["AreaObj"], vertices)
    if inventories["PropMaterial"] is not MISSING:
        materials = []
        for name in inventories["PropMaterial"]:
            row = {"name": name}
            c.put(
                row,
                "materials",
                name,
                "type_enum",
                "PropMaterial.GetMaterial",
                (name,),
                lambda r: integer(outputs(r, 4)[0]),
            )
            materials.append(row)
        c.snapshot["materials"] = materials
    c.put(
        c.snapshot,
        "settings",
        "mass",
        "mass_source",
        "DatabaseTables.GetTableForDisplayArray",
        ("Mass Source Definition", [], "", 0),
        mass_source,
    )
    c.modal(modal_case)
    c.put(
        c.snapshot,
        "analysis",
        "cases",
        "analysis_status",
        "Analyze.GetCaseStatus",
        (),
        lambda r: [
            {"name": name, "status": status}
            for name, status in counted(r, [text, integer], max_objects)
        ],
    )
    for field, reason in (
        (
            "pdelta",
            "Opciones P-Delta globales no leidas; un caso no lineal no las sustituye",
        ),
        ("spectrum_cases", "EX/EY y curva nativa no cotejados"),
        ("check_model", "No se ejecuta Check Model durante una captura de lectura"),
        ("saved_readback_verified", "No se guarda/reabre el EDB durante la captura"),
    ):
        c.pending("settings", "model", field, reason)
    for owner, initial in inventories.items():
        final = c.inventory(owner)
        if (
            initial is not MISSING
            and final is not MISSING
            and set(initial) != set(final)
        ):
            raise ValueError(
                f"Inventario {owner} cambio durante la captura; repetir con turno exclusivo"
            )
    after = c.boundary()
    if before != after:
        raise ValueError("Identidad/unidades/bloqueo cambiaron durante la captura")
    return {
        "schema": SCHEMA,
        "capture_id": str(uuid4()),
        "started_at": started,
        "finished_at": datetime.now(UTC).isoformat(),
        "source": {
            "kind": "etabs_oapi",
            "process_id": process_id,
            "version": None if version is MISSING else version,
            **before,
        },
        "snapshot": c.snapshot,
        "observations": c.observations,
        "model_modified": False,
        "analysis_executed": False,
        "consistency": {
            "identity_units_lock_stable": True,
            "scope": "Controles de extremos; no garantiza instantanea atomica ni detecta toda edicion concurrente",
        },
        "units": {
            "source_enum": units,
            "geometry": "m",
            "uniform_load_values": UNIT_NAMES[units - 1],
            "note": "Cargas conservan fuerza/longitud^2 activas; geometria convertida a metros",
        },
        "coverage": "partial",
        "engineering_approval": False,
    }
