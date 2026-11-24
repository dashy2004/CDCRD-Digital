"""Lee las hojas de cálculo sísmicas de un bloque: espectro, cuasiestático y Art. 38.

Las hojas se localizan por sus rótulos («SDS», «CORTANTE BASAL», «Ratio X-X»), no por
posiciones fijas de celda, de modo que mover una tabla dentro de la hoja no rompe la lectura.
Cada función `*_de` recibe las hojas ya cargadas como {nombre: filas} y no toca el disco.
"""
from __future__ import annotations

import os
import re
import unicodedata
from typing import Any, Iterator

Hoja = list[list[Any]]
Libro = dict[str, Hoja]

ALCANCE_DERECHA = 4          # columnas que se miran a la derecha de un rótulo
ERRORES_DE_CELDA = ("#DIV/0!", "#N/A", "#NAME?", "#NULL!", "#NUM!", "#REF!", "#VALUE!")
ESPECTRO_OBLIGATORIAS = ("SDS", "SD1")
CUASI_OBLIGATORIAS = ("total", "Vx", "Vy")
ART38_HOJA = re.compile(r"art\.?\s*38\s*\(\s*(\d+)\s*\)", re.I)


class ErrorDeHoja(Exception):
    """La hoja de cálculo no tiene la forma esperada."""


# ------------------------------------------------------------------ carga del archivo
def abrir(path: str) -> Libro:
    """Carga todas las hojas de un .xls o .xlsx como listas de filas (celdas vacías = None)."""
    if not os.path.isfile(path):
        raise ErrorDeHoja("no existe la hoja de cálculo: %s" % path)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".xls":
        return _abrir_xls(path)
    if ext in (".xlsx", ".xlsm"):
        return _abrir_xlsx(path)
    raise ErrorDeHoja("formato de hoja de cálculo no admitido: %s" % ext)


def _abrir_xls(path: str) -> Libro:
    import xlrd

    libro: Libro = {}
    wb = xlrd.open_workbook(path, on_demand=True)
    try:
        for nombre in wb.sheet_names():
            sh = wb.sheet_by_name(nombre)
            libro[nombre] = [
                [None if sh.cell_type(r, c) in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR)
                 else sh.cell_value(r, c) for c in range(sh.ncols)]
                for r in range(sh.nrows)]
            wb.unload_sheet(nombre)
    finally:
        wb.release_resources()
    return libro


def _abrir_xlsx(path: str) -> Libro:
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        libro: Libro = {}
        for ws in wb.worksheets:
            ws.reset_dimensions()          # la dimensión declarada en el archivo puede estar mal
            libro[ws.title] = [[None if v in ERRORES_DE_CELDA else v for v in fila]
                               for fila in ws.iter_rows(values_only=True)]
        return libro
    finally:
        wb.close()


# ------------------------------------------------------------------ búsqueda por rótulo
def _norma(v: Any) -> str:
    """Texto comparable: sin tildes, sin espacios repetidos ni dos puntos finales, en minúsculas."""
    if not isinstance(v, str):
        return ""
    s = unicodedata.normalize("NFKD", v)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip().rstrip(":").strip().lower()


def _es_numero(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _vacio(v: Any) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _rotulos(hoja: Hoja, rotulo: str) -> Iterator[tuple[int, int]]:
    objetivo = _norma(rotulo)
    for r, fila in enumerate(hoja):
        for c, v in enumerate(fila):
            if _norma(v) == objetivo:
                yield r, c


def _a_la_derecha(hoja: Hoja, r: int, c: int, solo_numero: bool = False) -> list[Any]:
    """Celdas no vacías a la derecha de (r, c), dentro del alcance."""
    fila = hoja[r]
    vals = [v for v in fila[c + 1:c + 1 + ALCANCE_DERECHA] if not _vacio(v)]
    return [v for v in vals if _es_numero(v)] if solo_numero else vals


def _valor(hoja: Hoja, rotulo: str, numero: bool = True, n: int = 0) -> Any:
    """Primer valor a la derecha de la n-ésima aparición del rótulo; None si no está."""
    for k, (r, c) in enumerate(_rotulos(hoja, rotulo)):
        if k == n:
            vals = _a_la_derecha(hoja, r, c, solo_numero=numero)
            if not vals:
                return None
            return vals[0].strip() if isinstance(vals[0], str) else vals[0]
    return None


def _hoja_con(libro: Libro, *rotulos: str) -> tuple[str, Hoja]:
    """Primera hoja que contiene todos los rótulos."""
    for nombre, hoja in libro.items():
        if all(next(_rotulos(hoja, x), None) is not None for x in rotulos):
            return nombre, hoja
    raise ErrorDeHoja("ninguna hoja contiene los rótulos: %s" % ", ".join(rotulos))


def _entero_como_texto(v: Any) -> Any:
    """2.0 -> '2'; deja igual lo que no es un número entero."""
    return str(int(v)) if _es_numero(v) and float(v).is_integer() else v


# ------------------------------------------------------------------ espectro
def espectro_de(libro: Libro) -> dict[str, Any]:
    """Parámetros sísmicos de la hoja de espectro (la que rotula SDS, SD1, Fa y Fv)."""
    _, h = _hoja_con(libro, "SDS", "SD1", "Fa =", "Fv =")
    nota = None
    for r, c in _rotulos(h, "Rd (final)="):
        textos = [v.strip() for v in _a_la_derecha(h, r, c) if isinstance(v, str)]
        nota = textos[0] if textos else None
        break
    for rotulo in ESPECTRO_OBLIGATORIAS:
        if _valor(h, rotulo) is None:
            raise ErrorDeHoja("la hoja de espectro no tiene valor para «%s» (¿fórmula sin calcular?)" % rotulo)
    return {
        "proyecto": _valor(h, "Proyecto", numero=False),
        "uso": _valor(h, "Uso", numero=False),
        "ubicacion": _valor(h, "Ubicación", numero=False),
        "pisos": _valor(h, "No. De Pisos"),
        "h1": _valor(h, "Altura de 1er Entrepiso"),
        "hotros": _valor(h, "Altura otros entrepisos"),
        "htotal": _valor(h, "Altura Total de Edificio"),
        "dx": _valor(h, "Dirección x-x"),
        "dy": _valor(h, "Dirección y-y"),
        "I": _entero_como_texto(_valor(h, "I=", numero=False)),
        "Z": _entero_como_texto(_valor(h, "Z=", numero=False)),
        "U": _entero_como_texto(_valor(h, "U=", numero=False)),
        "S": _entero_como_texto(_valor(h, "S=", numero=False)),
        "sistema": _valor(h, "Sistema Estructural =", numero=False),
        "Rd": _valor(h, "Rd="),
        "Rd_final": _valor(h, "Rd (final)="),
        "Rd_nota": nota,
        "Ss": _valor(h, "Ss ="),
        "S1": _valor(h, "S1 ="),
        "Fa": _valor(h, "Fa ="),
        "Fv": _valor(h, "Fv ="),
        "SDS": _valor(h, "SDS"),
        "SD1": _valor(h, "SD1"),
        "To": _valor(h, "To ="),
        "Ts": _valor(h, "Ts ="),
    }


def tabla_espectro_de(libro: Libro) -> list[tuple[float, float]]:
    """Pares (período, aceleración) de la tabla del espectro de diseño, ordenados por período."""
    puntos: dict[float, float] = {}
    for hoja in libro.values():
        for r, fila in enumerate(hoja):
            for c, v in enumerate(fila[:-1]):
                if _norma(v) == "periodo" and _norma(fila[c + 1]) == "aceleracion":
                    for abajo in hoja[r + 1:]:
                        if c + 1 >= len(abajo) or not (_es_numero(abajo[c]) and _es_numero(abajo[c + 1])):
                            break
                        puntos[round(float(abajo[c]), 6)] = float(abajo[c + 1])
        if puntos:
            break
    return sorted(puntos.items())


# ------------------------------------------------------------------ cuasiestático
def cuasi_de(libro: Libro) -> dict[str, Any]:
    """Hoja de cortante basal por el método cuasiestático."""
    _, h = _hoja_con(libro, "CORTANTE BASAL", "Carga Total de Edificio")
    ta = [x for x in (_valor(h, "Ta =", n=0), _valor(h, "Ta =", n=1)) if x is not None]
    d: dict[str, Any] = {
        "pisos": _valor(h, "No. De Pisos"),
        "htotal": _valor(h, "Altura Total de Edificio"),
        "dx": _valor(h, "Dirección x-x"),
        "dy": _valor(h, "Dirección y-y"),
        "sistema": " ".join(str(v).strip() for r, c in list(_rotulos(h, "Sistema Estructural Sismo Resistente"))[:1]
                            for v in _a_la_derecha(h, r, c) if isinstance(v, str)) or None,
        "muerta": _valor(h, "Carga Muerta"),
        "viva_part": _valor(h, "Totales"),
        "total": _valor(h, "Carga Total de Edificio"),
        "phi_entrepiso": _valor(h, "Entrepisos"),
        "phi_comun": _valor(h, "Común"),
        "phi_techo": _valor(h, "Techo"),
        "Ct": _valor(h, "Ct="),
        "X": _valor(h, "X="),
        "Ko": _valor(h, "Ko="),
        "Ta": ta,
        "Tx1": _valor(h, "Tx1 ="), "Ty1": _valor(h, "Ty1 ="),
        "Tx": _valor(h, "Tx ="), "Ty": _valor(h, "Ty ="),
        "CBX": _valor(h, "CBX ="), "CBY": _valor(h, "CBY ="),
        "Vx": _valor(h, "V x-x ="), "Vy": _valor(h, "V y-y ="),
        "Vx65": _valor(h, "V x-x (65%) ="), "Vy65": _valor(h, "V y-y (65%) ="),
        "texto_cargas": [],
    }
    faltan = [k for k in CUASI_OBLIGATORIAS if d[k] is None]
    if faltan:
        raise ErrorDeHoja("la hoja de cuasiestático no tiene valor para: %s" % ", ".join(faltan))
    for clave, rotulo in (("Ex", "Ex-x"), ("Ey", "Ey-y")):
        for r, c in _rotulos(h, rotulo):
            vals = _a_la_derecha(h, r, c)
            nums = [v for v in vals if _es_numero(v)]
            txt = [v.strip() for v in vals if isinstance(v, str)]
            if len(nums) >= 2:
                d[clave] = [float(nums[0]), txt[0] if txt else "", float(nums[1])]
            break
    return d


# ------------------------------------------------------------------ Art. 38
def art38_de(libro: Libro) -> list[dict[str, Any]]:
    """Relación desplazamiento máximo / promedio por nivel, una entrada por hoja «Art.38(n)»."""
    casos = []
    for nombre, hoja in libro.items():
        m = ART38_HOJA.search(nombre)
        if not m:
            continue
        cab = next(((r, fila) for r, fila in enumerate(hoja)
                    if any(_norma(v) == "ratio x-x" for v in fila) and any(_norma(v) == "story" for v in fila)), None)
        if cab is None:
            raise ErrorDeHoja("la hoja «%s» no tiene el encabezado Story / Ratio X-X" % nombre)
        r0, fila_cab = cab
        col: dict[str, int] = {}
        for c, v in enumerate(fila_cab):
            if isinstance(v, str):
                col.setdefault(_norma(v), c)          # si un encabezado se repite, vale el primero
        if "ratio y-y" not in col or "point" not in col:
            raise ErrorDeHoja("la hoja «%s» no tiene las columnas Point y Ratio Y-Y" % nombre)
        cs, cp, cx, cy = col["story"], col["point"], col["ratio x-x"], col["ratio y-y"]
        if cy - cx < 2:
            raise ErrorDeHoja("la hoja «%s» no deja dos columnas para Ratio X-X" % nombre)
        filas = []
        for fila in hoja[r0 + 1:]:
            if len(fila) <= cy + 1 or not _es_numero(fila[cs]) or fila[cs] < 1 or _norma(fila[cp]) != "a":
                continue
            ratios = [fila[cx], fila[cx + 1], fila[cy], fila[cy + 1]]
            if not all(_es_numero(v) for v in ratios):
                continue
            filas.append({"story": int(fila[cs]), "rx1": float(ratios[0]), "rx2": float(ratios[1]),
                          "ry1": float(ratios[2]), "ry2": float(ratios[3]),
                          "ok": [v.strip() for v in fila[cy + 2:] if isinstance(v, str) and v.strip()]})
        casos.append({"caso": m.group(1), "hoja": nombre, "filas": filas})
    if not casos:
        raise ErrorDeHoja("el libro no tiene hojas «Art.38(n)»")
    return sorted(casos, key=lambda c_: int(c_["caso"]))


# ------------------------------------------------------------------ bloque
def hojas_de_bloque(espectro_xls: str, art38_xls: str | None = None) -> dict[str, Any]:
    """Claves `espectro`, `tabla_espectro`, `cuasi`, `art38` y `torsion` de un bloque de data.json."""
    libro = abrir(espectro_xls)
    return {
        "espectro": espectro_de(libro),
        "tabla_espectro": [list(p) for p in tabla_espectro_de(libro)],
        "cuasi": cuasi_de(libro),
        "art38": art38_de(abrir(art38_xls)) if art38_xls else [],
        "torsion": [],
    }
