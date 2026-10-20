"""CLI del puente de losas.

Uso::

    puente-losas --proyecto proyecto.json --salida salidas/ [--usos usos.json]
                 [--nombre "Proyecto Ejemplo"]

``proyecto.json`` es el export de ``revit-mcp-tools/exportar_proyecto`` (marker
"MCP:LOSA-ESQ" para traer solo las losas esquemáticas) o un JSON plano con el
bloque ``losas``. ``usos.json`` sobrescribe por Mark uso/mampostería/vuelo/borde.

Escribe en la carpeta de salida: ``informe_losas.xlsx``, ``mapa_losas.svg``,
``plan_etabs.json`` y ``resultados.json`` (la corrida cruda, auditable).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from puente_losas import __version__
from puente_losas.contrato import aplicar_usos, asignar_bordes, panos_desde_json
from puente_losas.etabs_plan import escribir_plan
from puente_losas.informe_excel import escribir_informe, escribir_mapa_svg
from puente_losas.motor import analizar_panos


def _resultado_a_dict(r) -> dict:
    return {
        "mark": r.pano.mark, "nivel": r.pano.nivel, "uso": r.pano.uso,
        "borde": r.pano.borde, "es_vuelo": r.pano.es_vuelo,
        "params_motor": r.params,
        "cargas_tm2": {"peso_propio": r.cargas.peso_propio, "acabados": r.cargas.acabados_dead,
                       "mamposteria_asignada": r.cargas.mamposteria_asignada,
                       "patron_viva": r.cargas.patron_viva, "viva": r.cargas.viva,
                       "q_servicio": r.cargas.q_servicio, "q_ultima": r.cargas.q_ultima},
        "espesor": {"h_min_normativo_m": r.espesor.h_min_normativo,
                    "h_usado_m": r.espesor.h_usado, "criterio": r.espesor.criterio,
                    "seccion_etabs": r.espesor.seccion_etabs,
                    "modelo_insuficiente": r.espesor.espesor_modelo_insuficiente},
        "w_servicio_m": r.w_servicio_m, "limite_flecha_m": r.limite_flecha_m,
        "momentos_tonf_m": {"mx": r.mx_tonf_m, "my": r.my_tonf_m, "apoyo": r.m_apoyo_tonf_m},
        "franja_x": r.franja_x, "franja_y": r.franja_y, "franja_apoyo": r.franja_apoyo,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="puente-losas",
                                     description="Losas de Revit → motor FEM EstructurasRD → Excel/ETABS.")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--proyecto", metavar="PROYECTO.json",
                        help="export de exportar_proyecto o JSON plano con bloque 'losas'.")
    parser.add_argument("--usos", metavar="USOS.json",
                        help="JSON {mark: {uso, mamposteria_tm2, es_vuelo, borde, direccion, espesor}}.")
    parser.add_argument("--salida", default="salidas", help="carpeta de salida (default: salidas/).")
    parser.add_argument("--nombre", default="Proyecto Ejemplo",
                        help="nombre para el informe (NO usar nombres de cliente en repo público).")
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0
    if not args.proyecto:
        parser.print_help()
        return 1

    try:
        panos = panos_desde_json(args.proyecto)
        if args.usos:
            with open(args.usos, encoding="utf-8") as f:
                panos = aplicar_usos(panos, json.load(f))
        panos = asignar_bordes(panos)
        resultados = analizar_panos(panos)
    except (OSError, ValueError, KeyError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 1

    os.makedirs(args.salida, exist_ok=True)
    ruta_xlsx = os.path.join(args.salida, "informe_losas.xlsx")
    ruta_svg = os.path.join(args.salida, "mapa_losas.svg")
    ruta_plan = os.path.join(args.salida, "plan_etabs.json")
    ruta_res = os.path.join(args.salida, "resultados.json")

    escribir_informe(resultados, ruta_xlsx, proyecto=args.nombre)
    escribir_mapa_svg(resultados, ruta_svg)
    escribir_plan(resultados, ruta_plan, proyecto=args.nombre)
    with open(ruta_res, "w", encoding="utf-8") as f:
        json.dump([_resultado_a_dict(r) for r in resultados], f, indent=1, ensure_ascii=False)

    print(f"{len(resultados)} paños analizados.")
    for ruta in (ruta_xlsx, ruta_svg, ruta_plan, ruta_res):
        print(f"  {ruta}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
