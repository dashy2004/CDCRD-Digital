"""Orquestación Pieper-Martens del puente: paños → códigos → momentos → .DL.

Toma los mismos paños y cargas de la corrida FEM (``ResultadoPano``) y produce
la vía Losas.exe: momentos PM por losa, momentos balanceados por borde y el
``SistemaDL`` listo para guardarse como ``.DL`` (abrible en LosasPlus o
corrible en Losas.exe). La carga del .DL es la q ÚLTIMA (1.2D+1.6L), igual que
la columna CARGA del flujo del Excel: los Mu del .TXT son momentos de diseño.
"""
from __future__ import annotations

from dataclasses import dataclass

from puente_losas.dl_io import LosaDL, SistemaDL
from puente_losas.motor import FC_KG_CM2, RECUBRIMIENTO_LOSA_MM, ResultadoPano

# fy nominal del flujo Losas.exe/Excel: 4200 kg/cm² (A615 Gr60) = 4.2 ton/cm².
FY_TON_CM2 = 4.200
from puente_losas.pieper_martens import MomentoApoyo, MomentosLosa, balancear, momentos_losa
from puente_losas.tipo_pm import ClasificacionPM, clasificar_panos, pares_balanceo


@dataclass(frozen=True)
class ResultadoPM:
    """La vía Pieper-Martens completa de un sistema de losas."""
    clasificacion: dict[str, ClasificacionPM]
    momentos: dict[str, MomentosLosa]       # por Mark, ton·m/m
    apoyos: list[MomentoApoyo]              # bordes balanceados
    sistema: SistemaDL                      # el .DL equivalente


def calcular_pm(resultados: list[ResultadoPano],
                nombre_sistema: str = "Sistema No 1") -> ResultadoPM:
    """Calcula Pieper-Martens para los paños ya analizados por el FEM."""
    panos = [r.pano for r in resultados]
    clasif = clasificar_panos(panos)

    momentos: dict[str, MomentosLosa] = {}
    losas_dl: list[LosaDL] = []
    for i, r in enumerate(resultados, start=1):
        p = r.pano
        codigo = clasif[p.mark].codigo
        q_u = round(r.cargas.q_ultima, 3)           # la CARGA que viaja en el .DL
        momentos[p.mark] = momentos_losa(codigo, q_u, p.lx, p.ly)
        losas_dl.append(LosaDL(
            id=i, tipo=codigo, carga=q_u, espesor=r.espesor.h_usado,
            lx=round(p.lx, 3), ly=round(p.ly, 3),
            rec=RECUBRIMIENTO_LOSA_MM / 1000.0, mark=p.mark))

    px, py = pares_balanceo(panos)
    apoyos = [balancear(i, j, "X", modo, momentos) for i, j, modo in px]
    apoyos += [balancear(i, j, "Y", modo, momentos) for i, j, modo in py]

    id_de = {losa.mark: losa.id for losa in losas_dl}
    sistema = SistemaDL(
        nombre=nombre_sistema,
        fc_ton_cm2=round(FC_KG_CM2 / 1000.0, 3),    # 210 kg/cm² → 0.210 ton/cm²
        fy_ton_cm2=FY_TON_CM2,
        adicionales=0,
        losas=losas_dl,
        pares_x=[(id_de[i], id_de[j], m) for i, j, m in px],
        pares_y=[(id_de[i], id_de[j], m) for i, j, m in py],
    )
    return ResultadoPM(clasif, momentos, apoyos, sistema)


def pm_a_dict(pm: ResultadoPM) -> dict:
    """Serialización JSON-able de la vía PM (para resultados.json)."""
    return {
        "metodo": "Pieper-Martens (tablas de F. Perdomo, Losas v5.21)",
        "losas": {
            mark: {
                "codigo_dl": pm.clasificacion[mark].codigo,
                "bordes_empotrados": list(pm.clasificacion[mark].empotrados),
                "eps_recortado": pm.clasificacion[mark].eps_recortado,
                "nota": pm.clasificacion[mark].nota,
                "mfx": m.mfx, "mfy": m.mfy, "msx": m.msx, "msy": m.msy,
                "q_pm_tm2": next(l.carga for l in pm.sistema.losas if l.mark == mark),
                "unidades": "ton·m/m",
            }
            for mark, m in pm.momentos.items()
        },
        "apoyos": [
            {"losa_i": a.losa_i, "losa_j": a.losa_j, "direccion": a.direccion,
             "mu_i": a.mu_i, "mu_j": a.mu_j, "mu_ij": a.mu_ij, "modo": a.modo}
            for a in pm.apoyos
        ],
    }
