"""Acero comercial para los momentos Pieper-Martens (como el .TXT de Losas.exe).

Toma la salida del puente (``resultados.json``, bloque ``pieper_martens``) y
diseña el acero de cada momento PM — vano X/Y, apoyo X/Y y los apoyos
balanceados entre losas — con el MISMO módulo ACI 318-19 del motor de
EstructurasRD que ya usa el puente (``motor_fea.normativa.aci318``):
As de flexión + mínimo de retracción/temperatura y selección de **barra
comercial con su separación** (el "disponer" del flujo, p. ej. Ø3/8" @0.20).

Requiere ``motor_fea`` instalado (el motor de losas del que depende
puente-losas); si no está, el llamador decide (el CLI lo omite con aviso).
Materiales por defecto: los del encargo (f'c 21 MPa, fy 420 MPa, rec 25 mm).
"""
from __future__ import annotations

import json

TONF_M_A_N_MM = 9806.65 * 1000.0      # ton·m/m → N·mm/m (b = 1000 mm)
FC_MPA = 21.0
FY_MPA = 420.0
REC_MM = 25.0


def _franja_a_dict(f) -> dict:
    a = f.armadura
    return {"as_requerido": round(f.as_requerido, 1), "as_minimo": round(f.as_minimo, 1),
            "as_diseno": round(f.as_diseno, 1), "seccion_insuficiente": f.seccion_insuficiente,
            "gobierna_minimo": f.gobierna_minimo, "numero_barra": a.numero_barra,
            "espaciamiento": a.espaciamiento, "as_provista": round(a.as_provista, 1),
            "cumple": a.cumple, "disponer": a.disponer}


def _disenar(momento_tonm: float, h_m: float, fc: float, fy: float, rec_mm: float) -> dict:
    from motor_fea.normativa.aci318 import diseno_losa_franja
    h_mm = h_m * 1000.0
    d_mm = h_mm - rec_mm
    f = diseno_losa_franja(abs(momento_tonm) * TONF_M_A_N_MM, 1000.0, h_mm, d_mm, fc, fy)
    return _franja_a_dict(f)


def acero_pm_de_resultados(resultados: dict, fc: float = FC_MPA, fy: float = FY_MPA,
                           rec_mm: float = REC_MM) -> dict:
    """Acero comercial por losa (Mf/Ms según X e Y) y por apoyo balanceado.

    El espesor de cada losa es el ``h_usado`` de su corrida; en un apoyo entre
    dos losas se usa el MENOR de los dos espesores (menor d → más acero:
    conservador). ValueError si falta el bloque ``pieper_martens``.
    """
    pm = resultados.get("pieper_martens")
    if not pm or "losas" not in pm:
        raise ValueError("resultados.json sin bloque 'pieper_martens'.")
    h_de = {r["mark"]: (r.get("espesor") or {}).get("h_usado_m")
            for r in resultados.get("panos") or []}

    losas: dict[str, dict] = {}
    for mark, m in pm["losas"].items():
        h = h_de.get(mark)
        if not h:
            raise ValueError(f"{mark}: sin espesor h_usado en resultados.json.")
        losas[mark] = {
            "h_m": h,
            "armados": {clave: _disenar(m.get(clave, 0.0), h, fc, fy, rec_mm)
                        for clave in ("mfx", "mfy", "msx", "msy")},
        }

    apoyos = []
    for a in pm.get("apoyos") or []:
        h_i, h_j = h_de.get(a["losa_i"]), h_de.get(a["losa_j"])
        h = min(x for x in (h_i, h_j) if x) if (h_i or h_j) else None
        if not h:
            raise ValueError(f"apoyo {a['losa_i']}-{a['losa_j']}: sin espesor.")
        apoyos.append({"losa_i": a["losa_i"], "losa_j": a["losa_j"],
                       "direccion": a["direccion"], "mu_ij": a["mu_ij"], "h_m": h,
                       "armado": _disenar(a["mu_ij"], h, fc, fy, rec_mm)})

    return {"metodo": "As por momentos Pieper-Martens con ACI 318-19 del motor de "
                      "EstructurasRD (diseno_losa_franja); barra comercial y separación",
            "materiales": {"fc_mpa": fc, "fy_mpa": fy, "recubrimiento_mm": rec_mm},
            "losas": losas, "apoyos": apoyos}


def escribir_acero_pm(acero: dict, ruta: str) -> None:
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(acero, f, indent=1, ensure_ascii=False)
