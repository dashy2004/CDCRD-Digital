# FEA MCP - lector de modelos ETABS en texto (.e2k / .$et) desde disco.
#
# Motivo (2026-09-03, modelo de dos bloques): la OAPI no expone por tabla ni por
# getter dedicado el espesor de muros ('MH35'), los decks, ni las tablas
# 'Frame/Area Section Property Definitions' (vuelven sin filas). Ademas el
# puente COM solo ve UNA instancia y muere al cerrar el archivo. Pero cada
# File.Save regenera junto al .EDB un .$et que ES el formato e2k en texto
# plano. Leerlo desde disco cubre: secciones de muro/deck/losa con espesor y
# material, forma de cada seccion de frame, niveles, grillas, geometria y
# asignaciones -- sin COM, sin instancia, y sobre varios modelos a la vez.
#
# Limites: el .$et refleja el ULTIMO guardado, no el estado en memoria. Las
# dimensiones de perfiles de catalogo (W8X40) no viajan en el e2k: solo el
# SHAPE; las dimensiones viven en la libreria de secciones (xml de CSI o el
# catalogo AISC de Revit). Los puntos son 2D (x, y); la z sale del nivel.
#
# Uso fuera del MCP:  python e2k_reader.py "ruta.$et" [seccion]

import json
import os
import re
import sys
from typing import Any

_TOK = re.compile(r'"([^"]*)"|(\S+)')


class _Q(str):
    """Token que venia entre comillas: nunca se convierte a numero
    (LABEL "9" es una etiqueta, no un entero)."""


def _tokens(line: str) -> list[str]:
    """Tokeniza una linea e2k respetando comillas ("" -> cadena vacia)."""
    return [_Q(m.group(1)) if m.group(1) is not None else m.group(2)
            for m in _TOK.finditer(line)]


def _num(s: str) -> Any:
    if isinstance(s, _Q):
        return str(s)
    try:
        if re.fullmatch(r"[-+]?\d+", s):
            return int(s)
        return float(s)
    except ValueError:
        return s


def _kv(tokens: list[str], start: int) -> dict[str, Any]:
    """Convierte 'KEY value KEY value ...' en dict desde tokens[start:]."""
    out: dict[str, Any] = {}
    i = start
    while i < len(tokens):
        k = tokens[i]
        if (i + 1 < len(tokens) and not isinstance(k, _Q)
                and re.fullmatch(r"[A-Z][A-Z0-9_]*", k)):
            out[str(k)] = _num(tokens[i + 1])
            i += 2
        else:
            out.setdefault("_extra", []).append(k)
            i += 1
    return out


def split_sections(text: str) -> dict[str, list[str]]:
    """Divide el archivo en bloques '$ TITULO' -> lineas no vacias."""
    blocks: dict[str, list[str]] = {}
    current = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.startswith("$ "):
            title = line[2:].strip()
            if title.startswith("File ") or title == "END OF MODEL FILE":
                current = None
                continue
            current = title
            blocks.setdefault(current, [])
            continue
        if current is not None:
            blocks[current].append(line.strip())
    return blocks


class E2K:
    """Modelo ETABS leido desde texto e2k."""

    def __init__(self, path: str):
        self.path = path
        with open(path, "r", encoding="latin-1") as f:
            self.text = f.read()
        self.blocks = split_sections(self.text)
        self.units = self._units()
        self.stories = self._stories()
        self.grids = self._grids()
        self.materials = self._materials()
        self.frame_sections = self._frame_sections()
        self.shell_sections = self._shell_sections()
        self.points = self._points()
        self.lines = self._lines()
        self.areas = self._areas()
        self.line_assigns = self._line_assigns()
        self.area_assigns = self._area_assigns()
        self.point_assigns = self._point_assigns()

    # -- bloques de cabecera -------------------------------------------

    def _units(self) -> dict[str, str]:
        for ln in self.blocks.get("CONTROLS", []):
            t = _tokens(ln)
            if t and t[0] == "UNITS" and len(t) >= 4:
                return {"force": t[1], "length": t[2], "temp": t[3]}
        return {}

    def _stories(self) -> list[dict[str, Any]]:
        """De arriba hacia abajo en el archivo; devuelve de abajo hacia arriba
        con elevacion acumulada, como GetStories."""
        raw = []
        base_elev = 0.0
        for ln in self.blocks.get("STORIES - IN SEQUENCE FROM TOP", []):
            t = _tokens(ln)
            if not t or t[0] != "STORY":
                continue
            kv = _kv(t, 2)
            if "ELEV" in kv:
                base_elev = float(kv["ELEV"])
                continue
            raw.append({"name": t[1], "height": float(kv.get("HEIGHT", 0)),
                        "master": kv.get("MASTERSTORY", "No") == "Yes",
                        "similar_to": kv.get("SIMILARTO")})
        raw.reverse()
        elev = base_elev
        out = []
        for s in raw:
            elev += s["height"]
            out.append({**s, "elevation": elev})
        self.base_elevation = base_elev
        return out

    def story_elevation(self, name: str) -> float | None:
        if name == "Base":
            return getattr(self, "base_elevation", 0.0)
        for s in self.stories:
            if s["name"] == name:
                return s["elevation"]
        return None

    def story_below(self, name: str) -> str:
        names = ["Base"] + [s["name"] for s in self.stories]
        i = names.index(name) if name in names else -1
        return names[i - 1] if i > 0 else "Base"

    def _grids(self) -> list[dict[str, Any]]:
        out = []
        for ln in self.blocks.get("GRIDS", []):
            t = _tokens(ln)
            if t and t[0] == "GRID":
                kv = _kv(t, 2)
                out.append({"system": t[1], "label": kv.get("LABEL"),
                            "dir": kv.get("DIR"), "coord": kv.get("COORD"),
                            "visible": kv.get("VISIBLE", "Yes") == "Yes"})
        return out

    def _materials(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for ln in self.blocks.get("MATERIAL PROPERTIES", []):
            t = _tokens(ln)
            if t and t[0] == "MATERIAL" and len(t) > 2:
                out.setdefault(t[1], {}).update(_kv(t, 2))
        return out

    def _frame_sections(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for ln in self.blocks.get("FRAME SECTIONS", []):
            t = _tokens(ln)
            if t and t[0] == "FRAMESECTION" and len(t) > 2:
                out.setdefault(t[1], {}).update(_kv(t, 2))
        return out

    def _shell_sections(self) -> dict[str, dict[str, Any]]:
        """Losas, decks y muros: SHELLPROP con PROPTYPE Slab/Deck/Wall."""
        out: dict[str, dict[str, Any]] = {}
        for blk in ("SLAB PROPERTIES", "DECK PROPERTIES", "WALL PROPERTIES"):
            for ln in self.blocks.get(blk, []):
                t = _tokens(ln)
                if t and t[0] == "SHELLPROP" and len(t) > 2:
                    out.setdefault(t[1], {}).update(_kv(t, 2))
        return out

    # -- geometria -----------------------------------------------------

    def _points(self) -> dict[str, tuple[float, float]]:
        """POINT "id" x y [dz]. El tercer valor, cuando existe, es un
        desfase vertical respecto al nivel (ETABS lo usa para puntos que no
        estan en la cota del story; ej. un muro de Story1 con base a
        1.2344 mm). Se guarda aparte en point_dz."""
        out = {}
        self.point_dz: dict[str, float] = {}
        for ln in self.blocks.get("POINT COORDINATES", []):
            t = _tokens(ln)
            if t and t[0] == "POINT" and len(t) >= 4:
                out[t[1]] = (float(t[2]), float(t[3]))
                if len(t) >= 5:
                    try:
                        self.point_dz[t[1]] = float(t[4])
                    except ValueError:
                        pass
        return out

    def _lines(self) -> dict[str, dict[str, Any]]:
        out = {}
        for ln in self.blocks.get("LINE CONNECTIVITIES", []):
            t = _tokens(ln)
            if t and t[0] == "LINE" and len(t) >= 5:
                out[t[1]] = {"kind": t[2], "pi": t[3], "pj": t[4],
                             "flag": _num(t[5]) if len(t) > 5 else None}
        return out

    def _areas(self) -> dict[str, dict[str, Any]]:
        out = {}
        for ln in self.blocks.get("AREA CONNECTIVITIES", []):
            t = _tokens(ln)
            if t and t[0] == "AREA" and len(t) >= 4:
                n = int(t[3])
                pts = t[4:4 + n]
                flags = [_num(x) for x in t[4 + n:]]
                out[t[1]] = {"kind": t[2], "points": pts, "flags": flags}
        return out

    def _line_assigns(self) -> list[dict[str, Any]]:
        out = []
        for ln in self.blocks.get("LINE ASSIGNS", []):
            t = _tokens(ln)
            if t and t[0] == "LINEASSIGN" and len(t) >= 3:
                out.append({"label": t[1], "story": t[2], **_kv(t, 3)})
        return out

    def _area_assigns(self) -> list[dict[str, Any]]:
        out = []
        for ln in self.blocks.get("AREA ASSIGNS", []):
            t = _tokens(ln)
            if t and t[0] == "AREAASSIGN" and len(t) >= 3:
                out.append({"label": t[1], "story": t[2], **_kv(t, 3)})
        return out

    def _point_assigns(self) -> list[dict[str, Any]]:
        out = []
        for ln in self.blocks.get("POINT ASSIGNS", []):
            t = _tokens(ln)
            if t and t[0] == "POINTASSIGN" and len(t) >= 3:
                out.append({"label": t[1], "story": t[2], **_kv(t, 3)})
        return out

    # -- vistas derivadas ---------------------------------------------

    def frames3d(self) -> list[dict[str, Any]]:
        """Frames con coordenadas 3D y seccion, uno por (label, story).

        Las asignaciones LINEASSIGN son la unica fuente de que objeto existe
        en que nivel. Columnas: de la elevacion del nivel inferior al del
        nivel asignado. Vigas/riostras: en la elevacion del nivel asignado.
        """
        secs: dict[tuple[str, str], dict] = {}
        for a in self.line_assigns:
            secs.setdefault((a["label"], a["story"]), {}).update(a)
        out = []
        for (label, story), a in secs.items():
            ln = self.lines.get(label)
            if ln is None:
                continue
            pi = self.points.get(ln["pi"])
            pj = self.points.get(ln["pj"])
            if pi is None or pj is None:
                continue
            z_top = self.story_elevation(story)
            if z_top is None:
                continue
            # El entero final de LINE es cuantos niveles por debajo del story
            # asignado esta el punto i: COLUMN lleva 1, BEAM 0, y BRACE el
            # numero de pisos que cruza (una diagonal de 3 pisos lleva 3). Verificado
            # contra la OAPI el 2026-09-03.
            drop = ln.get("flag") if isinstance(ln.get("flag"), int) else 0
            st = story
            for _ in range(max(0, drop)):
                st = self.story_below(st)
            z_bot = self.story_elevation(st) if drop > 0 else z_top
            xs, ys, zs = [pi[0], pj[0]], [pi[1], pj[1]], [z_bot, z_top]
            out.append({"label": label, "story": story, "kind": ln["kind"],
                        "section": a.get("SECTION"), "xs": xs, "ys": ys,
                        "zs": zs})
        return out

    def areas3d(self) -> list[dict[str, Any]]:
        """Areas con coordenadas 3D y seccion, una por (label, story).

        PANEL con puntos repetidos (p, q, q, p) es un muro vertical: sube
        del nivel inferior al asignado. FLOOR/PANEL con 3+ puntos distintos
        es horizontal en la elevacion del nivel.
        """
        secs: dict[tuple[str, str], dict] = {}
        for a in self.area_assigns:
            secs.setdefault((a["label"], a["story"]), {}).update(a)
        out = []
        for (label, story), a in secs.items():
            ar = self.areas.get(label)
            if ar is None:
                continue
            pts = [self.points.get(p) for p in ar["points"]]
            if any(p is None for p in pts):
                continue
            z_top = self.story_elevation(story)
            if z_top is None:
                continue
            distinct_xy = list(dict.fromkeys(pts))
            vertical = ar["kind"] == "PANEL" and len(distinct_xy) == 2 \
                and len(ar["points"]) == 4
            if vertical:
                z_bot = self.story_elevation(self.story_below(story))
                p, q = distinct_xy[0], distinct_xy[1]
                # Puntos con desfase vertical (POINT x y dz): la base del
                # muro no esta en la cota del nivel. Se respeta el desfase
                # y se deja constancia en 'dz'.
                dzs = [self.point_dz.get(pid) for pid in ar["points"]]
                dz = [d for d in dzs if d is not None]
                if dz:
                    z_bot = z_top - max(dz)
                xs, ys = [p[0], q[0], q[0], p[0]], [p[1], q[1], q[1], p[1]]
                zs = [z_bot, z_bot, z_top, z_top]
            else:
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                zs = [z_top] * len(pts)
            sec = a.get("SECTION")
            if a.get("OPENING") == "Yes":
                sec = "OPENING"
            out.append({"label": label, "story": story, "kind": ar["kind"],
                        "vertical": vertical, "section": sec,
                        "xs": xs, "ys": ys, "zs": zs})
        return out

    def sections_in_use(self) -> dict[str, dict[str, int]]:
        """Conteo de asignaciones por seccion, frames y areas por separado."""
        fr: dict[str, int] = {}
        for a in self.line_assigns:
            s = a.get("SECTION")
            if s:
                fr[s] = fr.get(s, 0) + 1
        ar: dict[str, int] = {}
        for a in self.area_assigns:
            s = "OPENING" if a.get("OPENING") == "Yes" else a.get("SECTION")
            if s:
                ar[s] = ar.get(s, 0) + 1
        return {"frames": fr, "areas": ar}

    # -- resumen para el MCP ------------------------------------------

    def summary(self) -> dict[str, Any]:
        used = self.sections_in_use()
        return {
            "file": self.path,
            "units": self.units,
            "stories": self.stories,
            "grids": self.grids,
            "materials": {k: {kk: v for kk, v in d.items()
                              if kk in ("TYPE", "GRADE", "WEIGHTPERVOLUME",
                                        "E", "FC", "FY", "FU")}
                          for k, d in self.materials.items()},
            "frame_sections_defined": len(self.frame_sections),
            "frame_sections_in_use": {
                k: {"count": n, **self.frame_sections.get(k, {})}
                for k, n in used["frames"].items()},
            "shell_sections": self.shell_sections,
            "shell_sections_in_use": used["areas"],
            "counts": {"points": len(self.points), "lines": len(self.lines),
                       "areas": len(self.areas),
                       "frames_assigned": len(self.line_assigns),
                       "areas_assigned": len(self.area_assigns)},
        }


SECTIONS = ("summary", "stories", "grids", "materials", "frame_sections",
            "shell_sections", "frames", "areas", "sections_in_use",
            "blocks")


def query(path: str, section: str = "summary") -> Any:
    """Punto de entrada unico para el MCP y la linea de comandos."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    m = E2K(path)
    if section == "summary":
        return m.summary()
    if section == "stories":
        return {"base_elevation": m.base_elevation, "stories": m.stories}
    if section == "grids":
        return m.grids
    if section == "materials":
        return m.materials
    if section == "frame_sections":
        return m.frame_sections
    if section == "shell_sections":
        return m.shell_sections
    if section == "frames":
        return m.frames3d()
    if section == "areas":
        return m.areas3d()
    if section == "sections_in_use":
        return m.sections_in_use()
    if section == "blocks":
        return {k: len(v) for k, v in m.blocks.items()}
    raise ValueError(f"seccion '{section}' no valida; opciones: "
                     + ", ".join(SECTIONS))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"uso: {sys.argv[0]} archivo.e2k|.$et [{'|'.join(SECTIONS)}]")
        sys.exit(2)
    sec = sys.argv[2] if len(sys.argv) > 2 else "summary"
    print(json.dumps(query(sys.argv[1], sec), indent=1, ensure_ascii=False,
                     default=str))
