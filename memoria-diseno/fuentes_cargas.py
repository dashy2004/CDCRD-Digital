"""Lee el libro de cargas y espesores de losa: cuantificación de sobrecarga y hojas por nivel.

Como `fuentes_excel`, localiza todo por rótulos y encabezados, no por posiciones de celda.
Las funciones `*_de` reciben hojas ya cargadas ({nombre: filas}) y no tocan el disco.
"""
from __future__ import annotations

import re
from typing import Any

from fuentes_excel import ErrorDeHoja, Hoja, Libro, _es_numero, _norma, _rotulos, _vacio, _valor

ROTULO_BLOQUE = "cuantificacion de sobre carga"
FILA_ESPESOR = re.compile(r"^losa de \d+")
TOLERANCIA_LUZ = 0.011          # m: dos luces «iguales» escritas con dos decimales


# ------------------------------------------------------------------ utilidades
def _texto_de_fila(fila: list[Any]) -> tuple[int, str] | None:
    """(columna, texto normalizado) de la primera celda de texto de la fila."""
    for c, v in enumerate(fila):
        if isinstance(v, str) and v.strip():
            return c, _norma(v)
    return None


def _numeros(fila: list[Any], desde: int = 0) -> list[float]:
    return [float(v) for v in fila[desde:] if _es_numero(v)]


def _dos(v: Any) -> str:
    return "%.2f" % float(v)


# ------------------------------------------------------------------ sobrecarga
def sobrecarga_de(libro: Libro) -> list[dict[str, Any]]:
    """Bloques de cuantificación de sobrecarga (entrepiso, techo, …) en el orden en que aparecen."""
    bloques: list[dict[str, Any]] = []
    for hoja in libro.values():
        inicios = [r for r, fila in enumerate(hoja)
                   if any(_norma(v).startswith(ROTULO_BLOQUE) for v in fila)]
        for k, r0 in enumerate(inicios):
            fin = inicios[k + 1] if k + 1 < len(inicios) else len(hoja)
            bloques.append(_bloque_sobrecarga(hoja[r0 + 1:fin]))
        if bloques:
            break
    if not bloques:
        raise ErrorDeHoja("el libro no tiene ninguna hoja de «Cuantificación de Sobre Carga»")
    return bloques


def _bloque_sobrecarga(filas: Hoja) -> dict[str, Any]:
    out: dict[str, Any] = {"titulo": None, "espesores": [], "pesos": [], "vivas": [], "resumen": []}
    seccion = None
    for fila in filas:
        t = _texto_de_fila(fila)
        if t is None:
            if seccion == "resumen" and out["resumen"]:
                break                                   # la tabla resumen termina en la primera fila vacía
            continue
        c, texto = t
        nums = _numeros(fila, c + 1)
        original = fila[c].strip()
        if out["titulo"] is None and not nums and "carga muerta" not in texto:
            out["titulo"] = original
        elif FILA_ESPESOR.match(texto):
            if len(nums) >= 4:
                out["espesores"].append(nums[:4])       # h, densidad, peso propio, qd
        elif texto == "pesos propios":
            seccion = "pesos"
        elif texto == "carga viva":
            seccion = "vivas"
        elif texto.startswith("qu="):
            seccion = None
        elif texto == "descripcion":
            seccion = "resumen"
        elif seccion == "pesos" and len(nums) >= 3:
            out["pesos"].append([original] + nums[:3])  # nombre, espesor, densidad, peso
        elif seccion == "vivas" and nums:
            out["vivas"].append([original, nums[0]])
        elif seccion == "resumen" and len(nums) >= 3:
            out["resumen"].append([original] + nums[:3])  # descripción, qd, ql, qu
    return out


def encabezado_de(libro: Libro) -> dict[str, Any]:
    """Proyecto y fecha que el libro declara en su primera hoja con rótulo «Proyecto»."""
    for hoja in libro.values():
        proyecto = _valor(hoja, "Proyecto", numero=False)
        if proyecto is not None:
            fecha = _valor(hoja, "Fecha", numero=False)
            return {"proyecto": str(proyecto), "fecha": fecha.strftime("%d/%m/%Y") if hasattr(fecha, "strftime")
                    else (str(fecha) if fecha is not None else None)}
    return {"proyecto": None, "fecha": None}


# ------------------------------------------------------------------ hojas por nivel
def _fila_de_encabezado(hoja: Hoja, nombre: str) -> tuple[int, dict[str, int]]:
    """Fila cuyo primer rótulo es LOSA y que trae Lx; devuelve su índice y {encabezado: columna}."""
    for r, fila in enumerate(hoja):
        col: dict[str, int] = {}
        for c, v in enumerate(fila):
            if isinstance(v, str):
                col.setdefault(_norma(v), c)
        if "losa" in col and "lx" in {k.split(" ")[0] for k in col}:
            return r, col
    raise ErrorDeHoja("la hoja «%s» no tiene el encabezado LOSA / Lx" % nombre)


def _columna(col: dict[str, int], *prefijos: str) -> int | None:
    """Primera columna cuyo encabezado empieza por alguno de los prefijos."""
    for p in prefijos:
        for k, c in col.items():
            if k.startswith(p):
                return c
    return None


def _declaradas(hoja: Hoja) -> int | None:
    """Cantidad de losas que declara la hoja; None si la celda junto al rótulo está vacía."""
    for r, c in _rotulos(hoja, "Cant. de Losas"):
        siguiente = hoja[r][c + 1] if c + 1 < len(hoja[r]) else None
        return int(siguiente) if _es_numero(siguiente) else None
    return None


def espesores_de(hoja: Hoja, nombre: str = "") -> dict[str, Any]:
    """Hoja «Espesor …»: una fila por losa con luces, condición y espesor calculado y adoptado."""
    r0, col = _fila_de_encabezado(hoja, nombre)
    c_id, c_lx, c_ly = col["losa"], _columna(col, "lx"), _columna(col, "ly")
    c_cond, c_k, c_ln, c_h = _columna(col, "cond"), _columna(col, "k"), _columna(col, "ln"), _columna(col, "h [")
    if None in (c_lx, c_ly, c_h):
        raise ErrorDeHoja("la hoja «%s» no tiene las columnas Lx, Ly y h" % nombre)
    losas: dict[str, dict[str, str]] = {}
    for fila in hoja[r0 + 1:]:
        if len(fila) <= c_h or not all(_es_numero(fila[c]) for c in (c_id, c_lx, c_ly)) or fila[c_lx] <= 0:
            continue
        adoptado = next((fila[c + 1] for c, v in enumerate(fila[:-1])
                         if _norma(v).startswith("usar h") and _es_numero(fila[c + 1])), None)
        k = fila[c_k] if c_k is not None else None
        losas[str(int(fila[c_id]))] = {
            "Lx": _dos(fila[c_lx]), "Ly": _dos(fila[c_ly]),
            "cond": str(fila[c_cond]).strip() if c_cond is not None and not _vacio(fila[c_cond]) else "—",
            "K": _dos(k) if _es_numero(k) else (str(k).strip() if not _vacio(k) else "—"),
            "Ln": _dos(fila[c_ln]) if c_ln is not None and _es_numero(fila[c_ln]) else "—",
            "hcalc": _dos(fila[c_h]) if _es_numero(fila[c_h]) else "—",
            "h": _dos(adoptado) if adoptado is not None else "—"}
    if not losas:
        raise ErrorDeHoja("la hoja «%s» no tiene ninguna losa con luces" % nombre)
    return {"losas": losas, "declaradas": _declaradas(hoja)}


def cargas_de(hoja: Hoja, nombre: str = "") -> dict[str, Any]:
    """Hoja «Carga …»: una fila por losa con área, mampostería y cargas muerta, viva y última."""
    r0, col = _fila_de_encabezado(hoja, nombre)
    c = {"id": col["losa"], "Lx": _columna(col, "lx"), "Ly": _columna(col, "ly"), "h": _columna(col, "espesor (m)"),
         "area": _columna(col, "area"), "qmamp_ton": _columna(col, "q mamp"), "qmamp": _columna(col, "qmap", "qmamp"),
         "qd": _columna(col, "q muerta"), "ql": _columna(col, "q viva"), "qu": _columna(col, "q ultima")}
    faltan = [k for k in ("Lx", "Ly", "qd", "ql", "qu") if c[k] is None]
    if faltan:
        raise ErrorDeHoja("la hoja «%s» no tiene las columnas: %s" % (nombre, ", ".join(faltan)))
    losas: dict[str, dict[str, str]] = {}
    for fila in hoja[r0 + 1:]:
        if len(fila) <= c["qu"] or not all(_es_numero(fila[c[k]]) for k in ("id", "Lx", "Ly", "qu")) or fila[c["Lx"]] <= 0:
            continue
        losas[str(int(fila[c["id"]]))] = {
            k: (_dos(fila[c[k]]) if c[k] is not None and _es_numero(fila[c[k]]) else "—")
            for k in ("Lx", "Ly", "h", "area", "qmamp_ton", "qmamp", "qd", "ql", "qu")}
    if not losas:
        raise ErrorDeHoja("la hoja «%s» no tiene ninguna losa con carga" % nombre)
    return {"losas": losas, "declaradas": _declaradas(hoja)}


def hoja_del_nivel(libro: Libro, prefijo: str, nivel: str, indicada: str | None = None) -> tuple[str, Hoja]:
    """Hoja «<prefijo> <nivel>» (sin distinguir mayúsculas), o la indicada en el manifiesto."""
    buscado = _norma(indicada) if indicada else _norma("%s %s" % (prefijo, nivel))
    for nombre, hoja in libro.items():
        if _norma(nombre) == buscado:
            return nombre, hoja
    raise ErrorDeHoja("el libro no tiene la hoja «%s»" % (indicada or "%s %s" % (prefijo, nivel)))


# ------------------------------------------------------------------ cruce con el listado
def diferencias_de_luces(hoja_losas: dict[str, dict[str, str]], listado: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Losas cuyas luces en la hoja no coinciden con las del listado de diseño, y las que faltan en cada lado."""
    distintas = []
    for k, e in hoja_losas.items():
        m = listado.get(k)
        if m is None:
            continue
        try:
            dx, dy = abs(float(e["Lx"]) - float(m["Lx"])), abs(float(e["Ly"]) - float(m["Ly"]))
        except (KeyError, TypeError, ValueError):
            continue
        if dx > TOLERANCIA_LUZ or dy > TOLERANCIA_LUZ:
            distintas.append(k)
    return {"distintas": sorted(distintas, key=int),
            "solo_hoja": sorted((k for k in hoja_losas if k not in listado), key=int),
            "solo_listado": sorted((k for k in listado if k not in hoja_losas), key=int)}
