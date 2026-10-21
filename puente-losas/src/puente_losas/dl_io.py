"""Formatos de Losas.exe: lectura/escritura del ``.DL`` y lectura del ``.TXT``.

El ``.DL`` es el archivo de datos que LosasPlus le genera a ``Losas.exe``
(F. Perdomo, v5.21): texto con comentarios ``$``, cabecera del sistema
(NLOSA, f'c y fy en ton/cm², adicionales), una fila por losa (ID, TIPO,
CARGA ton/m², ESPESOR m, LX m, LY m, REC m) y los pares de balanceo de
momentos según X y según Y. El ``.TXT`` es la salida de Losas.exe (momentos y
armaduras); de él solo se parsean los momentos, que es lo que el puente
compara. Formato observado en los fixtures de EstructurasRD (RESTAURANTE 2).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LosaDL:
    id: int
    tipo: int
    carga: float      # ton/m²
    espesor: float    # m
    lx: float         # m
    ly: float         # m
    rec: float        # m
    mark: str = ""    # trazabilidad hacia Revit (no viaja en el .DL)


@dataclass(frozen=True)
class SistemaDL:
    nombre: str
    fc_ton_cm2: float
    fy_ton_cm2: float
    adicionales: int
    losas: list[LosaDL]
    pares_x: list[tuple[int, int, str]] = field(default_factory=list)   # (B-I, B-J, S/N)
    pares_y: list[tuple[int, int, str]] = field(default_factory=list)


# ----------------------------- escritura .DL -----------------------------
def _seccion_pares(titulo: str, pares: list[tuple[int, int, str]]) -> list[str]:
    lineas = ["$", f"$   ADIC. SEGUN {titulo}", f"{len(pares):>10}"]
    if pares:
        lineas += ["$", "$      B-I        B-J      BALANCEO"]
        lineas += [f"{i:>10}{j:>10}{modo:>10}" for i, j, modo in pares]
    return lineas


def escribir_dl(s: SistemaDL) -> str:
    """Serializa el sistema al formato del ``.DL`` (mismo esquema que el fixture)."""
    lineas = [
        "$  ARCHIVO DE DATOS DEL PROGRAMA LOSA",
        "$",
        s.nombre,
        "$",
        "$   NLOSA       FC        FY     ADICIONALES",
        "$    [-]    [ton/cm2]  [ton/cm2]     [-]",
        f"{len(s.losas):>7}{s.fc_ton_cm2:>12.3f}{s.fy_ton_cm2:>11.3f}{s.adicionales:>9}",
        "$",
        "$    ID    TIPO    CARGA   ESPESOR     LX       LY       REC",
        "$    [-]    [-]  [ton/m2]    [m]       [m]      [m]      [m]",
    ]
    for losa in s.losas:
        lineas.append(f"{losa.id:>7}{losa.tipo:>7}{losa.carga:>10.3f}{losa.espesor:>9.3f}"
                      f"{losa.lx:>10.3f}{losa.ly:>9.3f}{losa.rec:>9.3f}")
    lineas += _seccion_pares("X", s.pares_x)
    lineas += _seccion_pares("Y", s.pares_y)
    return "\n".join(lineas) + "\n"


def guardar_dl(s: SistemaDL, ruta: str) -> None:
    with open(ruta, "w", encoding="ascii", newline="\r\n") as f:
        f.write(escribir_dl(s))


# ------------------------------ lectura .DL ------------------------------
def leer_dl(texto: str) -> SistemaDL:
    """Parsea un ``.DL`` (tolerante al espaciado; ignora comentarios ``$``)."""
    lineas = [ln.strip() for ln in texto.splitlines()
              if ln.strip() and not ln.lstrip().startswith("$")]
    if len(lineas) < 2:
        raise ValueError("El .DL no tiene cabecera ni datos.")
    nombre = lineas[0]
    cab = lineas[1].split()
    if len(cab) < 4:
        raise ValueError(f"Cabecera NLOSA/FC/FY/ADICIONALES inválida: '{lineas[1]}'")
    nlosa, fc, fy, adic = int(cab[0]), float(cab[1]), float(cab[2]), int(cab[3])

    pos = 2
    losas = []
    for _ in range(nlosa):
        v = lineas[pos].split()
        if len(v) < 7:
            raise ValueError(f"Fila de losa inválida: '{lineas[pos]}'")
        losas.append(LosaDL(int(v[0]), int(v[1]), float(v[2]), float(v[3]),
                            float(v[4]), float(v[5]), float(v[6])))
        pos += 1

    def leer_pares() -> list[tuple[int, int, str]]:
        nonlocal pos
        n = int(lineas[pos])
        pos += 1
        pares = []
        for _ in range(n):
            v = lineas[pos].split()
            pares.append((int(v[0]), int(v[1]), v[2].upper()))
            pos += 1
        return pares

    pares_x = leer_pares()
    pares_y = leer_pares()
    return SistemaDL(nombre, fc, fy, adic, losas, pares_x, pares_y)


def cargar_dl(ruta: str) -> SistemaDL:
    with open(ruta, encoding="cp1252") as f:
        return leer_dl(f.read())


# --------------------------- lectura .TXT (salida) ---------------------------
@dataclass(frozen=True)
class MomentosTxt:
    """Fila de «CÁLCULO DE MOMENTOS» del .TXT (ton·m/m; H en cm)."""
    losa: int
    tipo: int
    carga: float
    h_cm: float
    lx: float
    ly: float
    mfx: float
    mfy: float
    msx: float
    msy: float


@dataclass(frozen=True)
class ApoyoTxt:
    """Fila de «ARMADURAS ... SOBRE LOS APOYOS» (solo los momentos)."""
    direccion: str    # "X" | "Y"
    losa_i: int
    losa_j: int
    mu_i: float
    mu_j: float
    mu_ij: float


_FILA_MOMENTOS = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+" + r"\s+".join([r"(-?\d+\.\d+)"] * 8) + r"\s*$")
_FILA_APOYO = re.compile(
    r"^\s*(\d+)-\s*(\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s")


def leer_txt(texto: str) -> tuple[list[MomentosTxt], list[ApoyoTxt]]:
    """Momentos por losa y por apoyo de la salida de Losas.exe."""
    momentos: list[MomentosTxt] = []
    apoyos: list[ApoyoTxt] = []
    seccion = ""
    for linea in texto.splitlines():
        mayus = linea.upper()
        if "LCULO DE MOMENTOS" in mayus:               # CÁLCULO con o sin tilde legible
            seccion = "momentos"
            continue
        if "SOBRE LOS APOYOS" in mayus:
            seccion = 'apoyos_x' if '"X"' in mayus else 'apoyos_y'
            continue
        if mayus.strip().startswith("CALCULO DE ARMADURAS") or "ARMADURAS SEG" in mayus:
            if "SOBRE LOS APOYOS" not in mayus:
                seccion = ""
            continue
        if seccion == "momentos":
            m = _FILA_MOMENTOS.match(linea)
            if m:
                g = m.groups()
                momentos.append(MomentosTxt(int(g[0]), int(g[1]), *map(float, g[2:])))
        elif seccion.startswith("apoyos"):
            m = _FILA_APOYO.match(linea)
            if m:
                g = m.groups()
                apoyos.append(ApoyoTxt("X" if seccion == "apoyos_x" else "Y",
                                       int(g[0]), int(g[1]),
                                       float(g[2]), float(g[3]), float(g[4])))
    if not momentos:
        raise ValueError("No se encontró la tabla CÁLCULO DE MOMENTOS en el .TXT.")
    return momentos, apoyos


def cargar_txt(ruta: str) -> tuple[list[MomentosTxt], list[ApoyoTxt]]:
    """La salida de Losas.exe viene en codificación Windows (cp1252)."""
    with open(ruta, encoding="cp1252") as f:
        return leer_txt(f.read())
