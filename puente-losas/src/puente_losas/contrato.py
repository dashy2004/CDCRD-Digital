"""Contrato de entrada del puente: paños de losa leídos del modelo Revit.

La fuente es el ``proyecto.json`` que escribe la tool ``exportar_proyecto`` de
``revit-mcp-tools`` (bloque ``losas``), normalmente con ``marker="MCP:LOSA-ESQ"``
para traer solo las losas esquemáticas creadas por el agente. También acepta un
JSON plano con una lista ``losas`` escrita a mano (ejemplos, tests).

Unidades del contrato: metros y t/m² (las unidades de obra del flujo de la
Ing. Arlette Ramírez). La conversión a SI del motor vive en ``motor.py``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace

USOS_VALIDOS = ("entrepisos", "comun", "techo", "parqueos", "gimnasio")
BORDES_VALIDOS = ("simple", "empotrado")

# Holgura para considerar dos bordes de paño como contiguos (m). Una junta
# sísmica de 0.10 m queda por encima y corta la continuidad a propósito.
TOL_ADYACENCIA_M = 0.06
# Solape mínimo del borde común, como fracción del borde más corto.
SOLAPE_MINIMO = 0.30


@dataclass(frozen=True)
class PanoLosa:
    """Un paño rectangular equivalente de losa, con su contorno real de origen."""
    mark: str                       # Mark de Revit (L1..L18, L4b, L8b) o id del export
    nivel: str | None               # nombre del nivel de Revit
    z_tope: float                   # cota superior (m)
    lx: float                       # dimensión X del rectángulo equivalente (m)
    ly: float                       # dimensión Y del rectángulo equivalente (m)
    espesor: float                  # espesor actual del paño (m)
    contorno: list[list[float]] = field(default_factory=list)   # [[x,y], ...] (m)
    huecos: list[list[list[float]]] = field(default_factory=list)
    area_m2: float | None = None
    uso: str = "entrepisos"         # set de carga (biblioteca de cargas.py)
    mamposteria_tm2: float | None = None   # carga de mampostería sobre losa (t/m²), sin redondear
    es_vuelo: bool = False          # vuelo/balcón: sin mampostería ni mínimo de 0.10
    borde: str | None = None        # None = decidir por adyacencia; "simple" | "empotrado"
    direccion: str | None = None    # "1D" | "2D" | None = por relación de luces
    tipo_revit: str | None = None
    revit_id: int | None = None

    @property
    def luz_corta(self) -> float:
        return min(self.lx, self.ly)

    @property
    def luz_larga(self) -> float:
        return max(self.lx, self.ly)

    @property
    def relacion_luces(self) -> float:
        return self.luz_larga / self.luz_corta if self.luz_corta > 0 else float("inf")

    @property
    def trabaja_1d(self) -> bool:
        """Losa en una dirección: declarada "1D" o relación de luces > 2 (criterio usual)."""
        if self.direccion in ("1D", "2D"):
            return self.direccion == "1D"
        return self.relacion_luces > 2.0


def _validar(p: PanoLosa) -> PanoLosa:
    if p.lx <= 0 or p.ly <= 0:
        raise ValueError(f"{p.mark}: luces no positivas (lx={p.lx}, ly={p.ly}).")
    if p.espesor <= 0:
        raise ValueError(f"{p.mark}: espesor no positivo ({p.espesor}).")
    if p.uso not in USOS_VALIDOS:
        raise ValueError(f"{p.mark}: uso '{p.uso}' no está en {USOS_VALIDOS}.")
    if p.borde is not None and p.borde not in BORDES_VALIDOS:
        raise ValueError(f"{p.mark}: borde '{p.borde}' no está en {BORDES_VALIDOS}.")
    return p


def _pano_desde_losa_export(rec: dict) -> PanoLosa:
    """Un registro del bloque ``losas`` de exportar_proyecto → PanoLosa."""
    esp = rec.get("espesor")
    if isinstance(esp, dict):
        esp = esp.get("h_usado")
    return _validar(PanoLosa(
        mark=str(rec.get("mark") or rec.get("id")),
        nivel=rec.get("nivel"),
        z_tope=float(rec.get("z_tope", 0.0)),
        lx=float(rec["lx"]),
        ly=float(rec["ly"]),
        espesor=float(esp or 0.0),
        contorno=[[float(x), float(y)] for x, y in rec.get("contorno") or []],
        huecos=[[[float(x), float(y)] for x, y in h] for h in rec.get("huecos") or []],
        area_m2=rec.get("area_m2"),
        uso=str(rec.get("uso", "entrepisos")),
        mamposteria_tm2=rec.get("mamposteria_tm2"),
        es_vuelo=bool(rec.get("es_vuelo", False)),
        borde=rec.get("borde"),
        direccion=rec.get("direccion"),
        tipo_revit=rec.get("tipo_revit"),
        revit_id=rec.get("revit_id"),
    ))


def panos_desde_dict(d: dict) -> list[PanoLosa]:
    """Lee los paños del dict de un ``proyecto.json`` (o de un JSON plano con ``losas``)."""
    losas = d.get("losas")
    if not losas:
        raise ValueError("El JSON no tiene bloque 'losas' o está vacío.")
    return [_pano_desde_losa_export(rec) for rec in losas]


def panos_desde_json(ruta: str) -> list[PanoLosa]:
    with open(ruta, encoding="utf-8") as f:
        return panos_desde_dict(json.load(f))


def aplicar_usos(panos: list[PanoLosa], usos: dict[str, dict]) -> list[PanoLosa]:
    """Sobrescribe por Mark los campos de uso/cargas/borde que el usuario declare.

    ``usos`` = {"L1": {"uso": "comun", "mamposteria_tm2": 0.12, "es_vuelo": false,
                "borde": "simple", "direccion": "1D", "espesor": 0.20}, ...}
    """
    campos = ("uso", "mamposteria_tm2", "es_vuelo", "borde", "direccion", "espesor")
    out = []
    for p in panos:
        extra = usos.get(p.mark)
        if extra:
            desconocidos = set(extra) - set(campos)
            if desconocidos:
                raise ValueError(f"{p.mark}: campos no reconocidos en usos: {sorted(desconocidos)}")
            p = _validar(replace(p, **{k: extra[k] for k in campos if k in extra}))
        out.append(p)
    return out


# ----------------------- Continuidad por adyacencia -----------------------
def _bbox(p: PanoLosa) -> tuple[float, float, float, float]:
    if p.contorno:
        xs = [q[0] for q in p.contorno]
        ys = [q[1] for q in p.contorno]
        return min(xs), min(ys), max(xs), max(ys)
    return 0.0, 0.0, p.lx, p.ly


def _solape(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def bordes_continuos(panos: list[PanoLosa], tol: float = TOL_ADYACENCIA_M) -> dict[str, int]:
    """Cuenta, por Mark, cuántos de los 4 bordes del bbox tienen un paño vecino.

    Dos bordes son vecinos si la separación perpendicular es ≤ ``tol`` y el
    solape paralelo cubre al menos ``SOLAPE_MINIMO`` del borde más corto, a la
    misma cota (±0.11 m, suficiente para un mismo entrepiso). Una junta de
    0.10 m NO es continuidad (0.10 > tol): ese es el comportamiento buscado.
    """
    cajas = {p.mark: (_bbox(p), p.z_tope) for p in panos}
    resultado: dict[str, int] = {}
    for p in panos:
        (x0, y0, x1, y1), z = cajas[p.mark]
        continuo = {"izq": False, "der": False, "inf": False, "sup": False}
        for q in panos:
            if q.mark == p.mark:
                continue
            (u0, v0, u1, v1), zq = cajas[q.mark]
            if abs(zq - z) > 0.11:
                continue
            sol_y = _solape(y0, y1, v0, v1) >= SOLAPE_MINIMO * min(y1 - y0, v1 - v0)
            sol_x = _solape(x0, x1, u0, u1) >= SOLAPE_MINIMO * min(x1 - x0, u1 - u0)
            if sol_y and abs(x0 - u1) <= tol:
                continuo["izq"] = True
            if sol_y and abs(x1 - u0) <= tol:
                continuo["der"] = True
            if sol_x and abs(y0 - v1) <= tol:
                continuo["inf"] = True
            if sol_x and abs(y1 - v0) <= tol:
                continuo["sup"] = True
        resultado[p.mark] = sum(continuo.values())
    return resultado


def asignar_bordes(panos: list[PanoLosa]) -> list[PanoLosa]:
    """Fija ``borde`` donde venga None: "empotrado" si los 4 bordes son continuos
    (paño interior), "simple" en el resto (conservador para el momento de vano).

    El modelo FEM solo admite el mismo borde en todo el contorno; la condición
    real mixta queda entre esos dos extremos y la decide ETABS en el análisis
    definitivo.
    """
    n_cont = bordes_continuos(panos)
    out = []
    for p in panos:
        if p.borde is None:
            p = replace(p, borde="empotrado" if n_cont[p.mark] == 4 else "simple")
        out.append(p)
    return out
