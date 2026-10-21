"""Resultados Pieper-Martens → DTO del visor de losas (capa frontera).

Adaptación de ``motor_fea/viz/resultados_losa.py`` de EstructurasRD: misma
idea (función pura que empaqueta resultados en un DTO render-agnóstico con
unidades y min/max), pero la fuente es la **salida del puente-losas por la vía
Pieper-Martens** (``resultados.json`` + geometría del ``proyecto.json``), no el
FEM. Aquí no se calcula ningún momento: solo se reorganiza lo que ya calculó
``puente_losas.pm_puente`` (tablas del Ing. F. Perdomo, método de Losas.exe).

Campos del visor por paño: momentos PM de vano y apoyo (ton·m/m), acero de
diseño por franja (mm²/m) y espesor usado. Los apoyos balanceados van aparte,
como segmentos entre paños.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

CREDITOS = [
    "Método Pieper-Martens: tablas del Ing. F. Perdomo (Losas.exe v5.21), portadas y "
    "validadas en puente-losas contra la salida real de Losas.exe.",
    "Cargas y biblioteca de losas: flujo AutoCAD↔Excel/ETABS de la Ing. Arlette Ramírez.",
    "Interfaz reciclada del visor de EstructurasRD (Emil Guillén De la Cruz, MIT).",
]

CAMPOS_VISOR = {
    "codigo_dl": ("Tipo de losa según apoyos (código DL)", "código"),
    "mfx": ("PM Mf según X (vano)", "ton·m/m"),
    "mfy": ("PM Mf según Y (vano)", "ton·m/m"),
    "msx": ("PM Ms según X (apoyo)", "ton·m/m"),
    "msy": ("PM Ms según Y (apoyo)", "ton·m/m"),
    "as_x": ("Acero franja X", "mm²/m"),
    "as_y": ("Acero franja Y", "mm²/m"),
    "as_apoyo": ("Acero franja apoyo", "mm²/m"),
    "h_usado": ("Espesor usado", "m"),
    "q_ultima": ("q última 1.2D+1.6L", "t/m²"),
}


@dataclass(frozen=True)
class DtoVisor:
    proyecto: str
    panos: list[dict]
    campos: dict
    apoyos: list[dict]
    creditos: list[str]

    def como_dict(self) -> dict:
        return {"proyecto": self.proyecto, "panos": self.panos, "campos": self.campos,
                "apoyos": self.apoyos, "creditos": self.creditos}


def _contornos(proyecto: dict) -> dict[str, list[list[float]]]:
    contornos = {}
    for rec in proyecto.get("losas") or []:
        mark = str(rec.get("mark") or rec.get("id"))
        c = rec.get("contorno") or []
        if c:
            contornos[mark] = [[float(x), float(y)] for x, y in c]
    return contornos


def dto_visor(proyecto: dict, resultados: dict, nombre: str = "Proyecto Ejemplo",
              acero: dict | None = None) -> DtoVisor:
    """Arma el DTO del visor desde ``proyecto.json`` + ``resultados.json``.

    ``resultados`` debe traer el bloque ``pieper_martens`` (lo escribe el CLI
    de puente-losas). ValueError si falta: el visor es de la vía PM, no del FEM.
    """
    pm = resultados.get("pieper_martens")
    if not pm or "losas" not in pm:
        raise ValueError("resultados.json sin bloque 'pieper_martens': correr puente-losas "
                         "(el visor lee la vía Pieper-Martens, no el FEM).")
    contornos = _contornos(proyecto)
    por_mark = {r["mark"]: r for r in resultados.get("panos") or []}

    panos: list[dict] = []
    valores: dict[str, dict[str, float]] = {c: {} for c in CAMPOS_VISOR}
    for mark, m in pm["losas"].items():
        r = por_mark.get(mark) or {}
        contorno = contornos.get(mark)
        if contorno is None:
            lx = (r.get("params") or {}).get("a") or 1.0
            ly = (r.get("params") or {}).get("b") or 1.0
            contorno = [[0.0, 0.0], [lx, 0.0], [lx, ly], [0.0, ly]]
        fila = {
            "mark": mark,
            "contorno": contorno,
            "codigo_dl": m.get("codigo_dl"),
            "nota": m.get("nota") or "",
            "uso": r.get("uso") or "",
            "es_vuelo": bool(r.get("es_vuelo")),
            "armaduras": {
                "x": (r.get("franja_x") or {}).get("disponer", ""),
                "y": (r.get("franja_y") or {}).get("disponer", ""),
                "apoyo": (r.get("franja_apoyo") or {}).get("disponer", ""),
            },
        }
        if acero and mark in (acero.get("losas") or {}):
            armados = acero["losas"][mark]["armados"]
            fila["armado_pm"] = {clave: armados[clave]["disponer"] for clave in armados}
        valores["codigo_dl"][mark] = float(m.get("codigo_dl") or 0)
        valores["mfx"][mark] = m.get("mfx", 0.0)
        valores["mfy"][mark] = m.get("mfy", 0.0)
        valores["msx"][mark] = m.get("msx", 0.0)
        valores["msy"][mark] = m.get("msy", 0.0)
        valores["as_x"][mark] = (r.get("franja_x") or {}).get("as_diseno", 0.0)
        valores["as_y"][mark] = (r.get("franja_y") or {}).get("as_diseno", 0.0)
        valores["as_apoyo"][mark] = (r.get("franja_apoyo") or {}).get("as_diseno", 0.0)
        valores["h_usado"][mark] = (r.get("espesor") or {}).get("h_usado_m", 0.0)
        valores["q_ultima"][mark] = (r.get("cargas_tm2") or {}).get("q_ultima", 0.0)
        panos.append(fila)

    campos = {}
    for clave, (titulo, unidad) in CAMPOS_VISOR.items():
        vs = list(valores[clave].values())
        campos[clave] = {"titulo": titulo, "unidad": unidad,
                         "min": min(vs) if vs else 0.0, "max": max(vs) if vs else 0.0,
                         "valores": valores[clave]}

    armado_apoyo = {}
    if acero:
        for a in acero.get("apoyos") or []:
            armado_apoyo[(a["losa_i"], a["losa_j"], a["direccion"])] = a["armado"]["disponer"]
    apoyos = [{"losa_i": a["losa_i"], "losa_j": a["losa_j"], "direccion": a["direccion"],
               "mu_ij": a["mu_ij"], "modo": a["modo"],
               "disponer": armado_apoyo.get((a["losa_i"], a["losa_j"], a["direccion"]), "")}
              for a in pm.get("apoyos") or []]
    return DtoVisor(nombre, panos, campos, apoyos, list(CREDITOS))


def _ruta_plantilla() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "viz", "plantilla_visor.html")


MARCADOR_DATOS = "/*__DATOS_VISOR__*/null"


def escribir_visor(dto: DtoVisor, ruta_html: str, plantilla: str | None = None) -> None:
    """Escribe el visor HTML autónomo (datos embebidos: abre con doble clic, offline)."""
    with open(plantilla or _ruta_plantilla(), encoding="utf-8") as f:
        html = f.read()
    if MARCADOR_DATOS not in html:
        raise ValueError("La plantilla del visor no tiene el marcador de datos.")
    datos = json.dumps(dto.como_dict(), ensure_ascii=False)
    with open(ruta_html, "w", encoding="utf-8") as f:
        f.write(html.replace(MARCADOR_DATOS, datos, 1))


def visor_desde_archivos(ruta_proyecto: str, ruta_resultados: str, ruta_html: str,
                         nombre: str = "Proyecto Ejemplo") -> DtoVisor:
    with open(ruta_proyecto, encoding="utf-8") as f:
        proyecto = json.load(f)
    with open(ruta_resultados, encoding="utf-8") as f:
        resultados = json.load(f)
    dto = dto_visor(proyecto, resultados, nombre)
    escribir_visor(dto, ruta_html)
    return dto
