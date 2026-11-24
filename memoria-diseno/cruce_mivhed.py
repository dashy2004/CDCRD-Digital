"""Cruce de una memoria con el checklist de Estructura del MIVHED (CHECK-ESTRUCTURA).

Evalúa cada ítem con reglas sobre `data.json` (lo leído de ETABS, SAFE y las hojas) y
`memoria.json` (lo que declara el ingeniero). No dictamina: deja un estado y una nota para que
el responsable decida antes de someter el expediente.

Estados: «Está», «Parcial», «Falta», «No aplica», «Sin revisar» y «Planos» (se verifica en los
planos, fuera de este cruce). Para «Falta» y «Parcial» se citan los códigos de motivo de
incumplimiento del checklist que corresponden.

El checklist es el JSON del corpus `corpus-mivhed-checklists/data/mivhed-norm-checklists.json`.

Uso:  python cruce_mivhed.py data.json memoria.json checklist.json salida.md
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from typing import Any, Callable

CODIGO = "CHECK-ESTRUCTURA"
ESTA, PARCIAL, FALTA, NA, SIN_REVISAR, PLANOS = "Está", "Parcial", "Falta", "No aplica", "Sin revisar", "Planos"
ESTADOS = (ESTA, PARCIAL, FALTA, NA, SIN_REVISAR, PLANOS)
ITEMS_PLANOS = (2, 3) + tuple(range(14, 30))
TOLERANCIA = 0.05                 # diferencia relativa a partir de la que dos valores «no cuadran»
TON_M2_A_KG_CM2 = 0.1
TIPOS_BASICOS = {"dead", "super dead", "live", "roof live", "reducible live", "seismic", "wind", "other"}

Resultado = tuple[str, str, list[str]]


class ErrorDeChecklist(Exception):
    """El checklist no tiene la forma esperada."""


# ------------------------------------------------------------------ checklist
def cargar_checklist(ruta: str, codigo: str = CODIGO) -> dict[str, Any]:
    with open(ruta, encoding="utf-8") as f:
        d = json.load(f)
    cl = next((c for c in d.get("checklists", []) if c.get("codigo") == codigo), None)
    if not cl or not cl.get("items"):
        raise ErrorDeChecklist("el archivo no trae el checklist %s con ítems" % codigo)
    return cl


# ------------------------------------------------------------------ utilidades
def _norm(s: Any) -> str:
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def _kv(filas: Any, clave: str) -> str:
    """Valor de una tabla [[clave, valor], …] de memoria.json, buscando la clave sin acentos."""
    for f in filas or []:
        if isinstance(f, (list, tuple)) and len(f) >= 2 and _norm(clave) in _norm(f[0]):
            return str(f[1])
    return ""


def _texto(filas: Any) -> str:
    return " ".join(" ".join(map(str, f)) if isinstance(f, (list, tuple)) else str(f) for f in filas or [])


def _difiere(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and max(abs(a), abs(b)) > 0 and abs(a - b) / max(abs(a), abs(b)) > TOLERANCIA


def _fmt(x: float | None, nd: int = 2) -> str:
    return "—" if x is None else ("{:,.%df}" % nd).format(x)


def _lista(xs: list[str]) -> str:
    xs = list(dict.fromkeys(xs))
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " y " + xs[-1] if xs else ""


def _sistema(texto: str) -> str | None:
    t = _norm(texto)
    if "dual" in t:
        return "dual"
    if "muro" in t:
        return "muros"
    if "portic" in t or "pcr" in t:
        return "pórticos"
    return None


class Contexto:
    """Lo que las reglas necesitan de data.json y memoria.json, ya calculado."""

    def __init__(self, data: dict[str, Any], config: dict[str, Any]):
        self.D, self.C = data, config
        self.bloques = data.get("bloques") or []
        self.etabs = [(b["nombre"], b.get("etabs") or {}) for b in self.bloques]
        self.fund = data.get("fundaciones") or {}
        self.materiales = config.get("materiales") or []
        self.proyecto = config.get("proyecto") or []
        self.normas = config.get("normas") or []
        shapes = {_norm(fr.get("shape")) for _, e in self.etabs for fr in (e.get("frame") or {}).values()}
        self.acero = any(s and "concrete" not in s for s in shapes)

    def muros_en_modelo(self, e: dict[str, Any]) -> bool:
        muros = {a["name"] for a in e.get("area") or [] if _norm(a.get("type")) == "wall"}
        en_uso = e.get("area_en_uso")
        return bool(muros & set(en_uso)) if en_uso is not None else bool(muros)

    def fc_en_uso(self, e: dict[str, Any]) -> set[float]:
        """f'c (kg/cm²) de los concretos asignados a algún elemento; tonf/m² en el modelo."""
        mats = set()
        fr_uso, ar_uso = e.get("frame_en_uso"), e.get("area_en_uso")
        for n, fr in (e.get("frame") or {}).items():
            if fr_uso is None or n in fr_uso:
                mats.add(fr.get("mat"))
        for a in e.get("area") or []:
            if ar_uso is None or a["name"] in ar_uso:
                mats.add(a.get("mat"))
        fc = e.get("fc") or {}
        return {round(fc[m] * TON_M2_A_KG_CM2) for m in mats if fc.get(m)}


def _base(e: dict[str, Any], caso: str, comp: str) -> float | None:
    v = (e.get("base") or {}).get(caso)
    return max(abs(x[comp]) for x in v) if v else None


# ------------------------------------------------------------------ reglas por ítem
def r_sistema(x: Contexto) -> Resultado:
    declarado = _kv(x.proyecto, "sistema estructural")
    if not declarado:
        return FALTA, "memoria.json no declara el sistema estructural.", ["1.1"]
    fuentes = [("la memoria", declarado)]
    for nombre, b in ((b["nombre"], b) for b in x.bloques):
        for hoja, clave in (("espectro", "espectro"), ("cuasiestático", "cuasi")):
            s = (b.get(clave) or {}).get("sistema")
            if s:
                fuentes.append(("la hoja de %s de %s" % (hoja, nombre), s))
    con_muros = [n for n, e in x.etabs if (e.get("muros") or {}).get("pilas")]
    tipos = {_sistema(s) for _, s in fuentes} - {None}
    notas = []
    if len(tipos) > 1:
        vistos = {}
        for donde, s in fuentes:
            vistos.setdefault(s.strip(), []).append(donde)
        notas.append("No coincide: " + "; ".join("«%s» en %s" % (s, _lista(d)) for s, d in vistos.items()) + ".")
    if con_muros and _sistema(declarado) == "pórticos":
        notas.append(("Además, los modelos de %s diseñan muros como pilas." if notas else
                      "La memoria declara «%s» y los modelos de %%s diseñan muros como pilas." % declarado)
                     % _lista(con_muros))
    if notas:
        return PARCIAL, " ".join(notas), ["1.3"]
    return ESTA, "«%s», coherente con las hojas de cálculo." % declarado, []


def r_materiales(x: Contexto) -> Resultado:
    if not x.materiales:
        return FALTA, "memoria.json no trae la tabla de materiales.", []
    return ESTA, "Tabla de materiales del capítulo 1 (%d filas)." % len(x.materiales), []


def r_fc(x: Contexto) -> Resultado:
    m = re.search(r"f'?c\s*=\s*([\d.,]+)", _kv(x.materiales, "concreto") or _texto(x.materiales))
    declarado = float(m.group(1).replace(",", "")) if m else None
    usados = sorted(set().union(*[x.fc_en_uso(e) for _, e in x.etabs])) if x.etabs else []
    safe = sorted({round(v * TON_M2_A_KG_CM2) for v in (x.fund.get("concretos") or {}).values()})
    if declarado is None:
        return FALTA, "La memoria no declara f'c.", []
    notas = []
    otros = [v for v in usados if abs(v - declarado) > 1]
    if otros:
        notas.append("La memoria declara %s kg/cm²; los elementos de ETABS usan %s kg/cm²."
                     % (_fmt(declarado, 0), _lista([_fmt(v, 0) for v in usados])))
    malos = _fc_safe_contra_nombre(x)
    if malos:
        notas.append("En SAFE " + _lista(["«%s» tiene f'c = %d kg/cm²" % m_ for m_ in malos]) + ".")
    elif safe and any(abs(v - declarado) > 1 for v in safe):
        notas.append("SAFE define %s kg/cm²." % _lista([_fmt(v, 0) for v in safe]))
    return (PARCIAL, " ".join(notas), []) if notas else (ESTA, "%s kg/cm², igual en los modelos." % _fmt(declarado, 0), [])


def _fc_safe_contra_nombre(x: Contexto) -> list[tuple[str, int]]:
    """Concretos de SAFE cuyo nombre lleva un f'c (C210) distinto del valor definido."""
    malos = []
    for n, v in (x.fund.get("concretos") or {}).items():
        m = re.search(r"(?<!\d)(\d{3})(?!\d)", n)
        if m and abs(int(m.group(1)) - v * TON_M2_A_KG_CM2) > 5:
            malos.append((n, round(v * TON_M2_A_KG_CM2)))
    return malos


def r_fy(x: Contexto) -> Resultado:
    t = _texto(x.materiales)
    return (ESTA, "Declarado en la tabla de materiales.", []) if re.search(r"\bfy\b", t, re.I) else \
        (FALTA, "La tabla de materiales no declara fy.", [])


def r_norma_barras(x: Contexto) -> Resultado:
    t = _texto(x.materiales) + " " + _texto(x.normas)
    if re.search(r"ASTM|A\s?615|A\s?706|NORDOM", t, re.I):
        return ESTA, "La memoria cita la norma de las barras.", []
    mats = sorted({(e.get("muros") or {}).get("preferencias", {}).get("RebarMat", "") for _, e in x.etabs} - {""})
    if mats:
        return PARCIAL, "Los modelos usan %s; la memoria no cita la norma de las barras." % _lista(mats), []
    return FALTA, "La memoria no cita la norma de especificación de las barras.", []


def r_mamposteria(patron: str, nombre: str) -> Callable[[Contexto], Resultado]:
    def regla(x: Contexto) -> Resultado:
        if re.search(patron, _texto(x.materiales), re.I):
            return ESTA, "%s declarado en la tabla de materiales." % nombre, []
        return SIN_REVISAR, "La tabla de materiales no trae %s; confirmar si hay mampostería estructural." % nombre, []
    return regla


def r_acero(x: Contexto) -> Resultado:
    if x.acero:
        return SIN_REVISAR, "Los modelos tienen secciones de pórtico que no son de hormigón.", []
    return NA, "Todas las secciones de pórtico son de hormigón.", []


def r_analisis_cargas(x: Contexto) -> Resultado:
    if x.D.get("sobrecarga") or x.D.get("cargas_meta"):
        return ESTA, "Cuantificación de sobrecarga del libro de cargas.", []
    return FALTA, "No hay hojas de cuantificación de cargas.", []


def r_gravitacionales(x: Contexto) -> Resultado:
    faltan = [n for n, e in x.etabs if not {"dead", "live"} <= {_norm(p.get("type")) for p in e.get("patterns") or []}]
    if faltan:
        return PARCIAL, "Sin patrones de carga muerta y viva en %s." % _lista(faltan), []
    return ESTA, "Patrones de carga muerta y viva en los modelos y cargas por losa.", []


def r_sismicas(x: Contexto) -> Resultado:
    sin = [b["nombre"] for b in x.bloques if not b.get("espectro")]
    if sin:
        return PARCIAL, "Sin hoja de espectro en %s." % _lista(sin), []
    ubic = _norm(_kv(x.proyecto, "ubicacion"))
    otras = sorted({b["espectro"].get("ubicacion", "") for b in x.bloques
                    if b["espectro"].get("ubicacion") and _norm(b["espectro"]["ubicacion"]) not in ubic})
    if ubic and otras:
        return PARCIAL, "Las hojas de espectro indican %s y la memoria ubica el proyecto en %s." % (
            _lista(otras), _kv(x.proyecto, "ubicacion")), []
    return ESTA, "Espectro por bloque y casos espectrales en los modelos.", []


def r_viento(x: Contexto) -> Resultado:
    con = [n for n, e in x.etabs if e.get("tiene_viento")]
    if not x.etabs:
        return SIN_REVISAR, "No hay modelos de ETABS.", []
    if not con:
        return FALTA, "Ningún modelo de ETABS define un patrón de viento.", []
    if len(con) < len(x.etabs):
        return PARCIAL, "Solo %s define viento." % _lista(con), []
    return ESTA, "Todos los modelos definen patrones de viento.", []


def r_otras(x: Contexto) -> Resultado:
    otros = sorted({p.get("type") for _, e in x.etabs for p in e.get("patterns") or []
                    if _norm(p.get("type")) not in TIPOS_BASICOS})
    if otros:
        return ESTA, "Patrones de otras solicitaciones: %s." % _lista(otros), []
    return FALTA, "Los modelos no definen otras solicitaciones y la memoria no las declara no aplicables.", []


def r_irregularidades(x: Contexto) -> Resultado:
    con = [b for b in x.bloques if b.get("art38")]
    if not con:
        return FALTA, "No hay verificación de irregularidades.", []
    nota = "Solo la torsional (Art. 38)."
    firmas = {json.dumps(b["art38"], sort_keys=True) for b in con}
    if len(con) > 1 and len(firmas) == 1:
        nota += " La tabla es idéntica en %s." % _lista([b["nombre"] for b in con])
    return PARCIAL, nota, []


def r_resultados(x: Contexto) -> Resultado:
    sin = [n for n, e in x.etabs if not (e.get("base") and e.get("modal"))]
    if not x.etabs or sin:
        return FALTA, "Sin resultados de análisis en %s." % (_lista(sin) or "ningún bloque"), []
    return ESTA, "Reacciones, modos, cortantes y derivas leídos de ETABS.", []


def r_derivas(x: Contexto) -> Resultado:
    if not any(e.get("drift") for _, e in x.etabs):
        return FALTA, "Sin derivas de entrepiso.", []
    return PARCIAL, "Se listan las derivas de ETABS; falta la verificación contra el límite del R-001.", []


def r_deriva_global(x: Contexto) -> Resultado:
    return FALTA, "No se calcula ni se verifica la deriva global.", []


def r_cortante_basal(x: Contexto) -> Resultado:
    sin = [b["nombre"] for b in x.bloques if not (b.get("cuasi") or {}).get("Vx")]
    if sin:
        return FALTA if len(sin) == len(x.bloques) else PARCIAL, "Sin hoja cuasiestática en %s." % _lista(sin), []
    notas = []
    for b in x.bloques:
        c, e = b["cuasi"], b.get("etabs") or {}
        for eje, caso, comp in (("X", "Ex", "FX"), ("Y", "Ey", "FY")):
            hoja, modelo = (c.get(caso) or [None])[0], _base(e, caso, comp)
            if _difiere(hoja, modelo):
                notas.append("%s %s: la hoja usa %s ton y ETABS da %s ton" % (b["nombre"], eje, _fmt(hoja), _fmt(modelo)))
    cuasis = {json.dumps({k: v for k, v in b["cuasi"].items() if k != "texto_cargas"}, sort_keys=True) for b in x.bloques}
    if len(x.bloques) > 1 and len(cuasis) < len(x.bloques):
        notas.append("hay bloques con la misma hoja cuasiestática")
    if notas:
        return PARCIAL, _cap("; ".join(notas)) + ".", []
    return ESTA, "Hoja cuasiestática por bloque, coherente con ETABS.", []


def r_diseno(x: Contexto) -> Resultado:
    if any(e.get("col") or e.get("beam") for _, e in x.etabs):
        return ESTA, "Diseño de columnas, vigas y nudos de ETABS.", []
    return FALTA, "Sin resultados de diseño.", []


def r_losas(x: Contexto) -> Resultado:
    niv = x.D.get("niveles") or []
    return (ESTA, "Losas.exe, %d nivel(es)." % len(niv), []) if niv else (FALTA, "Sin diseño de losas.", [])


def r_columnas(x: Contexto) -> Resultado:
    malas = []
    for n, e in x.etabs:
        peor = max((c for c in (e.get("col") or {}).items()), key=lambda kv: kv[1]["pmm"], default=None)
        if peor and peor[1]["pmm"] > 1.0:
            malas.append("%s %s (%s, %s)" % (n, _fmt(peor[1]["pmm"], 3), *peor[0].split("|")))
    if malas:
        return PARCIAL, "Relación P-M-M mayor que 1.00: " + "; ".join(malas) + ".", []
    if not any(e.get("col") for _, e in x.etabs):
        return FALTA, "Sin diseño de columnas.", []
    return ESTA, "Todas las columnas con relación P-M-M ≤ 1.00.", []


def r_muros(x: Contexto) -> Resultado:
    con = [(n, e) for n, e in x.etabs if x.muros_en_modelo(e)]
    if not con:
        return NA, "Los modelos no tienen muros asignados.", []
    sin = [n for n, e in con if (e.get("muros") or {}).get("estado") != "diseñado"]
    if sin:
        return FALTA, "Hay muros en %s y no hay diseño de muros." % _lista(sin), ["43.1"]
    notas, codigos = [], []
    for n, e in con:
        m = e["muros"]
        lim = float(m.get("preferencias", {}).get("DCLimit") or 1.0)
        pilas = m.get("pilas") or {}
        cort = sum(p["cortante"] for p in pilas.values())
        est = sum(p["estaciones"] for p in pilas.values())
        altas = [k for k, p in pilas.items() if (p.get("dc") or 0) > lim]
        cortas = [k for k, p in pilas.items() if p.get("rho_req") is not None and p.get("rho_act") is not None
                  and p["rho_req"] > p["rho_act"]]
        partes = []
        if cort:
            partes.append("cortante sobre el máximo en %d de %d estaciones" % (cort, est))
            codigos.append("43.2")
        if altas:
            partes.append("D/C sobre %s en %s" % (_fmt(lim), _lista(altas)))
            codigos.append("43.3")
        if cortas:
            partes.append("cuantía colocada menor que la requerida en %s" % _lista(cortas))
            codigos.append("43.6")
        if m.get("sin_pila"):
            partes.append("%d área(s) de muro sin pila, sin diseñar" % m["sin_pila"])
            codigos.append("43.1")
        if partes:
            notas.append("%s: %s" % (n, "; ".join(partes)))
    if notas:
        return PARCIAL, ". ".join(notas) + ".", sorted(set(codigos), key=lambda c: float(c))
    return ESTA, "Diseño de muros por pila de ETABS sin observaciones.", []


def r_vigas(x: Contexto) -> Resultado:
    notas = []
    for n, e in x.etabs:
        k = sum(v for m, v in (e.get("msgs") or {}).items() if m.startswith("viga:"))
        if k:
            notas.append("%s %d" % (n, k))
    if notas:
        return PARCIAL, "Estaciones de viga con mensajes de ETABS (cortante con torsión u otros): %s." % _lista(notas), []
    if not any(e.get("beam") for _, e in x.etabs):
        return FALTA, "Sin diseño de vigas.", []
    return ESTA, "Acero requerido en vigas sin mensajes de ETABS.", []


def r_cimentaciones(x: Contexto) -> Resultado:
    f = x.fund
    if not f:
        return FALTA, "No hay capítulo de fundaciones.", ["46.1"]
    notas = []
    q_adm = (x.C.get("fundaciones") or {}).get("esfuerzo_admisible_ton_m2")
    q = max((-p["min"] for p in f.get("presiones") or [] if p.get("min") is not None), default=None)
    if q_adm and q and q > q_adm:
        notas.append("presión máxima %s ton/m² frente a %s admisible" % (_fmt(q), _fmt(q_adm)))
    pz = f.get("punzonado") or {}
    if pz.get("sin_calcular"):
        notas.append("SAFE no calcula el punzonado en %d de %d puntos" % (pz["sin_calcular"], pz.get("n", 0)))
    notas.append("faltan dimensiones en planta y armado de las zapatas")
    return PARCIAL, _cap("; ".join(notas)) + ".", []


def r_archivo_etabs(x: Contexto) -> Resultado:
    if not x.etabs:
        return FALTA, "No se leyó ningún modelo de ETABS.", []
    return ESTA, "Leídos: %s." % _lista([e.get("archivo") or n for n, e in x.etabs]), []


def r_leido_del_modelo(que: str) -> Callable[[Contexto], Resultado]:
    def regla(x: Contexto) -> Resultado:
        if not x.etabs:
            return SIN_REVISAR, "No se leyó ningún modelo de ETABS.", []
        return ESTA, "Leído directamente de los modelos: %s." % que, []
    return regla


def r_congruencia(x: Contexto) -> Resultado:
    notas = []
    for b in x.bloques:
        e, c = b.get("etabs") or {}, b.get("cuasi") or {}
        niveles = len([s for s in e.get("mass_story") or [] if s[0] != "Base" and s[1] > 0])
        if c.get("pisos") and niveles and int(c["pisos"]) != niveles:
            notas.append("%s: %d pisos en la hoja y %d niveles con masa en ETABS" % (b["nombre"], int(c["pisos"]), niveles))
        w = ((e.get("auto_seis") or {}).get("Qx") or {}).get("W")
        if _difiere(c.get("total"), w):
            notas.append("%s: peso sísmico %s ton en la hoja y %s ton en ETABS" % (b["nombre"], _fmt(c["total"], 0), _fmt(w, 0)))
    if notas:
        return PARCIAL, ". ".join(notas) + ".", []
    return ESTA, "Pisos y peso sísmico coherentes entre hojas y modelos.", []


def r_archivo_safe(x: Contexto) -> Resultado:
    if not x.fund:
        return FALTA, "No se leyó el modelo de cimentaciones.", []
    return ESTA, "Leído: %s." % (x.fund.get("archivo") or x.fund.get("modelo")), []


def r_safe(que: str) -> Callable[[Contexto], Resultado]:
    def regla(x: Contexto) -> Resultado:
        if not x.fund:
            return SIN_REVISAR, "No se leyó el modelo de cimentaciones.", []
        return ESTA, "Leído del modelo de SAFE: %s." % que, []
    return regla


def r_cargas_safe(x: Contexto) -> Resultado:
    base = x.fund.get("base") or {}
    if not base or not x.etabs:
        return SIN_REVISAR, "Faltan las reacciones de ETABS o las cargas de SAFE.", []
    etabs = {c: sum(_base(e, c, "FZ") or 0 for _, e in x.etabs) for c in ("Dead", "Live")}
    notas = ["%s: SAFE %s ton, suma de ETABS %s ton" % (c, _fmt(base.get(c), 0), _fmt(v, 0))
             for c, v in etabs.items() if v and _difiere(base.get(c), v)]
    if notas:
        return PARCIAL, "; ".join(notas) + ". En carga muerta la diferencia puede incluir el peso propio de las zapatas.", []
    return ESTA, "Cargas muerta y viva de SAFE coherentes con la suma de reacciones de ETABS.", []


def r_congruencia_safe(x: Contexto) -> Resultado:
    if not x.fund:
        return SIN_REVISAR, "No se leyó el modelo de cimentaciones.", []
    notas = []
    proy = x.fund.get("proyecto")
    if proy and _norm(proy) not in _norm(_kv(x.proyecto, "proyecto")):
        notas.append("SAFE lleva como proyecto «%s»" % proy)
    malos = _fc_safe_contra_nombre(x)
    if malos:
        notas.append("en SAFE " + _lista(["«%s» tiene f'c = %d kg/cm²" % m for m in malos]))
    if notas:
        return PARCIAL, _cap("; ".join(notas)) + ".", []
    return ESTA, "Modelo de SAFE coherente con la memoria.", []


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


REGLAS: dict[int, Callable[[Contexto], Resultado]] = {
    1: r_sistema, 4: r_materiales, 5: r_fc, 6: r_fy, 7: r_norma_barras,
    8: r_mamposteria(r"f'?b\b", "f'b"), 9: r_mamposteria(r"f'?j\b", "f'j"), 10: r_mamposteria(r"f'?cm\b", "f'cm"),
    11: r_acero, 12: r_acero, 13: r_acero,
    30: r_analisis_cargas, 31: r_gravitacionales, 32: r_sismicas, 33: r_viento, 34: r_otras, 35: r_irregularidades,
    36: r_resultados, 37: r_derivas, 38: r_deriva_global, 39: r_cortante_basal,
    40: r_diseno, 41: r_losas, 42: r_columnas, 43: r_muros, 44: r_vigas, 45: r_acero, 46: r_cimentaciones,
    47: r_archivo_etabs, 48: r_leido_del_modelo("niveles, secciones y materiales"),
    49: r_leido_del_modelo("patrones de carga"), 50: r_leido_del_modelo("carga muerta, viva y por losa"),
    51: r_leido_del_modelo("patrones y casos sísmicos"),
    52: r_viento, 53: r_otras, 54: r_leido_del_modelo("combinaciones de carga"), 55: r_congruencia,
    56: r_archivo_safe, 57: r_safe("espesores, materiales y resortes de suelo"), 58: r_cargas_safe,
    59: r_safe("combinaciones de carga"),
    60: r_congruencia_safe,
    61: r_acero, 62: r_acero, 63: r_acero, 64: r_acero, 65: r_acero,
}


# ------------------------------------------------------------------ cruce
def cruzar(data: dict[str, Any], config: dict[str, Any], checklist: dict[str, Any]) -> list[dict[str, Any]]:
    x = Contexto(data, config)
    filas = []
    for it in sorted(checklist["items"], key=lambda i: i["numero"]):
        n = it["numero"]
        motivos = {m["codigo"]: m["texto"] for m in it.get("motivosIncumplimiento") or []}
        if n in ITEMS_PLANOS:
            estado, nota, codigos = PLANOS, "Se verifica en los planos.", []
        elif n in REGLAS:
            estado, nota, codigos = REGLAS[n](x)
        else:
            estado, nota, codigos = SIN_REVISAR, "Sin regla automática para este ítem.", []
        if estado == FALTA and not codigos:
            codigos = [c for c, t in motivos.items() if _norm(t).startswith("no se presenta")][:1]
        filas.append({"numero": n, "requisito": it["descripcion"].rstrip("."), "estado": estado, "nota": nota,
                      "motivos": [(c, motivos[c]) for c in codigos if c in motivos]})
    return filas


def resumen(filas: list[dict[str, Any]]) -> dict[str, int]:
    return {e: sum(1 for f in filas if f["estado"] == e) for e in ESTADOS}


def a_markdown(filas: list[dict[str, Any]], checklist: dict[str, Any], titulo: str) -> str:
    r = resumen(filas)
    out = ["# %s — cruce con el checklist de Estructura del MIVHED" % titulo, "",
           "Checklist `%s`, versión %s (publicado %s). Cruce automático contra lo leído de los modelos, las hojas "
           "de cálculo y `memoria.json`; no sustituye la revisión del ingeniero responsable."
           % (checklist.get("codigo"), checklist.get("version"), (checklist.get("publicadoEn") or "")[:10]), "",
           "Resumen: " + " · ".join("%s %d" % (e, n) for e, n in r.items() if n) + ".", "",
           "| Ítem | Requisito | Estado | Nota | Motivos |", "|---|---|---|---|---|"]
    for f in filas:
        mot = "<br>".join("%s %s" % (c, t) for c, t in f["motivos"]) or ""
        out.append("| %d | %s | %s | %s | %s |" % (f["numero"], f["requisito"], f["estado"],
                                                 f["nota"].replace("|", "/"), mot.replace("|", "/")))
    pendientes = [f for f in filas if f["estado"] in (FALTA, PARCIAL)]
    if pendientes:
        out += ["", "## Pendientes", ""] + ["- **%d %s** (%s): %s" % (f["numero"], f["requisito"], f["estado"], f["nota"])
                                           for f in pendientes]
    return "\n".join(out) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 5:
        sys.stderr.write("uso: python cruce_mivhed.py data.json memoria.json checklist.json salida.md\n")
        return 2
    with open(argv[1], encoding="utf-8") as f:
        data = json.load(f)
    with open(argv[2], encoding="utf-8") as f:
        config = json.load(f)
    try:
        cl = cargar_checklist(argv[3])
    except (OSError, ValueError, ErrorDeChecklist) as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1
    filas = cruzar(data, config, cl)
    titulo = _kv(config.get("proyecto"), "proyecto") or "Proyecto"
    with open(argv[4], "w", encoding="utf-8") as f:
        f.write(a_markdown(filas, cl, titulo))
    sys.stdout.write(" · ".join("%s %d" % (e, n) for e, n in resumen(filas).items() if n) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
