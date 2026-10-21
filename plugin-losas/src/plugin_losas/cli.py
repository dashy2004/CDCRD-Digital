"""CLI del plugin de losas.

Subcomandos::

    plugin-losas tabla      --proyecto p.json | --dxf plano.dxf [...] --salida dir/
    plugin-losas aligeradas --proyecto p.json --salida dir/
    plugin-losas visor      --proyecto p.json --resultados resultados.json --salida dir/

``tabla`` escribe ``tabla_losas.xlsx`` + ``usos.json`` (+ ``avisos.txt``);
``usos.json`` alimenta directamente al CLI de ``puente-losas``, que calcula y
escribe el informe completo (reuso de ``informe_excel.py``, sin reimplementar).
``aligeradas`` escribe ``plan_aligeradas.json`` (nervios/ejes/conexiones).
``visor`` escribe ``visor_losas.html`` (offline, datos embebidos).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from plugin_losas import __version__
from plugin_losas.acad_dxf import export_para_puente, losas_desde_dxf
from plugin_losas.extraccion import (escribir_tabla_excel, escribir_usos_json,
                                     filas_desde_export, usos_para_puente)
from plugin_losas.usos_tabla4 import cargar_tabla4
from plugin_losas.resultados_pm import visor_desde_archivos


def _cargar_json(ruta: str) -> dict:
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _cmd_tabla(args) -> int:
    tabla = cargar_tabla4(args.tabla4)
    avisos: list[str] = []
    if args.proyecto:
        filas = filas_desde_export(_cargar_json(args.proyecto))
    else:
        with open(args.dxf, encoding=args.codificacion) as f:
            filas, avisos = losas_desde_dxf(
                f.read(), capa_losas=args.capa, capa_textos=args.capa_textos,
                espesor_m=args.espesor, escala_a_m=args.escala)
    if args.usos_marcados:
        marcados = _cargar_json(args.usos_marcados)
        from plugin_losas.extraccion import asignar_uso
        for mark, uso_id in marcados.items():
            if mark.startswith("_"):          # claves de nota/comentario del JSON
                continue
            filas = asignar_uso(filas, mark, uso_id, tabla)

    os.makedirs(args.salida, exist_ok=True)
    ruta_xlsx = os.path.join(args.salida, "tabla_losas.xlsx")
    ruta_usos = os.path.join(args.salida, "usos.json")
    escribir_tabla_excel(filas, tabla, ruta_xlsx, proyecto=args.nombre)
    usos, avisos_usos = usos_para_puente(filas, tabla)
    escribir_usos_json(usos, ruta_usos)
    avisos += avisos_usos
    rutas = [ruta_xlsx, ruta_usos]
    if args.dxf:
        ruta_exp = os.path.join(args.salida, "losas_acad.json")
        with open(ruta_exp, "w", encoding="utf-8") as f:
            json.dump(export_para_puente(filas), f, indent=1, ensure_ascii=False)
        rutas.append(ruta_exp)
    if avisos:
        ruta_avisos = os.path.join(args.salida, "avisos.txt")
        with open(ruta_avisos, "w", encoding="utf-8") as f:
            f.write("\n".join(avisos) + "\n")
        rutas.append(ruta_avisos)
    print(f"{len(filas)} losas en la tabla; {len(avisos)} aviso(s).")
    for r in rutas:
        print(f"  {r}")
    return 0


def _cmd_aligeradas(args) -> int:
    from puente_losas.contrato import aplicar_usos, panos_desde_dict

    from plugin_losas.aligeradas import escribir_plan_aligeradas

    panos = panos_desde_dict(_cargar_json(args.proyecto))
    if args.usos:
        panos = aplicar_usos(panos, _cargar_json(args.usos))
    secciones = _cargar_json(args.secciones) if args.secciones else None
    os.makedirs(args.salida, exist_ok=True)
    ruta = os.path.join(args.salida, "plan_aligeradas.json")
    escribir_plan_aligeradas(panos, ruta, secciones)
    print(f"{len(panos)} paños en el plan de aligeradas.")
    print(f"  {ruta}")
    return 0


def _cmd_tipos(args) -> int:
    from puente_losas.contrato import aplicar_usos, panos_desde_dict

    from plugin_losas.tipos_pm import escribir_tipos_json, tipos_de_panos

    panos = panos_desde_dict(_cargar_json(args.proyecto))
    if args.usos:
        panos = aplicar_usos(panos, _cargar_json(args.usos))
    tipos = tipos_de_panos(panos)
    os.makedirs(args.salida, exist_ok=True)
    ruta = os.path.join(args.salida, "tipos_pm.json")
    escribir_tipos_json(tipos, ruta)
    print(f"{len(tipos)} losas con tipo por apoyos (código DL).")
    for t in tipos.values():
        print(f"  {t.mark}: {t.texto_param}")
    print(f"  {ruta}")
    return 0


def _cmd_renumerar(args) -> int:
    from puente_losas.contrato import aplicar_usos, panos_desde_dict

    from plugin_losas.renumeracion import caja_desde_contorno, renumerar

    panos = panos_desde_dict(_cargar_json(args.proyecto))
    if args.usos:
        panos = aplicar_usos(panos, _cargar_json(args.usos))
    cajas = [caja_desde_contorno(
        p.mark, p.contorno or [[0, 0], [p.lx, 0], [p.lx, p.ly], [0, p.ly]],
        es_vuelo=p.es_vuelo) for p in panos]
    mapa = renumerar(cajas, args.prefijo, relleno=args.relleno)
    os.makedirs(args.salida, exist_ok=True)
    ruta = os.path.join(args.salida, "renumeracion.json")
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(mapa, f, indent=1, ensure_ascii=False)
    print(f"{len(mapa)} losas renumeradas en orden de lectura "
          f"({len(cajas) - len(mapa)} vuelo(s) conservan su marca).")
    for viejo, nuevo in mapa.items():
        print(f"  {viejo} -> {nuevo}")
    print(f"  {ruta}")
    return 0


def _cmd_usos(args) -> int:
    tabla = cargar_tabla4(args.tabla4)
    os.makedirs(args.salida, exist_ok=True)
    ruta = os.path.join(args.salida, "usos_tabla4.txt")
    with open(ruta, "w", encoding="utf-8") as f:
        for n, u in enumerate(tabla.usos, start=1):
            f.write(f"{n}\t{u.id}\t{u.etiqueta}\n")
    print(f"{len(tabla.usos)} usos de la Tabla 4 (para CARGAUSOS de panel_losas.lsp).")
    print(f"  {ruta}")
    return 0


def _cmd_visor(args) -> int:
    os.makedirs(args.salida, exist_ok=True)
    ruta = os.path.join(args.salida, "visor_losas.html")
    dto = visor_desde_archivos(args.proyecto, args.resultados, ruta, nombre=args.nombre)
    print(f"Visor con {len(dto.panos)} paños y {len(dto.apoyos)} apoyos PM.")
    print(f"  {ruta}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plugin-losas",
        description="Extracción de losas (Revit/AutoCAD), usos Tabla 4, aligeradas y visor PM.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="comando", required=True)

    t = sub.add_parser("tabla", help="tabla de losas + usos.json para puente-losas")
    origen = t.add_mutually_exclusive_group(required=True)
    origen.add_argument("--proyecto", help="export de exportar_proyecto (Revit)")
    origen.add_argument("--dxf", help="plano DXF ASCII con recuadros de losa (AutoCAD)")
    t.add_argument("--capa", default="LOSAS", help="capa de los recuadros (default LOSAS)")
    t.add_argument("--capa-textos", default=None, help="capa de la numeración (default: todas)")
    t.add_argument("--espesor", type=float, default=None, help="espesor de las losas del DXF (m)")
    t.add_argument("--escala", type=float, default=1.0, help="unidades del DXF → m (mm: 0.001)")
    t.add_argument("--codificacion", default="cp1252", help="codificación del DXF (default cp1252)")
    t.add_argument("--usos-marcados", help="JSON {mark: id_uso_tabla4} asignado en el panel")
    t.add_argument("--tabla4", default=None, help="ruta a cargas_vivas.json (default: la del repo)")
    t.add_argument("--salida", default="salidas", help="carpeta de salida")
    t.add_argument("--nombre", default="Proyecto Ejemplo",
                   help="nombre para la tabla (NO usar nombres de cliente en repo público)")
    t.set_defaults(func=_cmd_tabla)

    a = sub.add_parser("aligeradas", help="plan paramétrico de nervios/ejes/conexiones")
    a.add_argument("--proyecto", required=True)
    a.add_argument("--usos", help="usos.json (los del puente) para 1D/2D y vuelos")
    a.add_argument("--secciones", help="JSON {mark: seccion} para fijar secciones a mano")
    a.add_argument("--salida", default="salidas")
    a.set_defaults(func=_cmd_aligeradas)

    rn = sub.add_parser("renumerar",
                        help="marcas en orden de lectura (izq→der, arriba→abajo; vuelos fuera)")
    rn.add_argument("--proyecto", required=True)
    rn.add_argument("--prefijo", required=True, help="prefijo de la marca (T, N2-, L...)")
    rn.add_argument("--relleno", type=int, default=0, help="ceros a la izquierda (2 → N2-01)")
    rn.add_argument("--usos", help="usos.json del puente (marca los vuelos, que no se renumeran)")
    rn.add_argument("--salida", default="salidas")
    rn.set_defaults(func=_cmd_renumerar)

    tp = sub.add_parser("tipos", help="tipo de losa según apoyos (código DL) + payload para Revit")
    tp.add_argument("--proyecto", required=True)
    tp.add_argument("--usos", help="usos.json del puente (marca vuelos: cambian el tipo)")
    tp.add_argument("--salida", default="salidas")
    tp.set_defaults(func=_cmd_tipos)

    u = sub.add_parser("usos", help="lista numerada de los usos Tabla 4 (para el LISP/panel)")
    u.add_argument("--tabla4", default=None)
    u.add_argument("--salida", default="salidas")
    u.set_defaults(func=_cmd_usos)

    v = sub.add_parser("visor", help="visor HTML de la vía Pieper-Martens")
    v.add_argument("--proyecto", required=True)
    v.add_argument("--resultados", required=True, help="resultados.json del CLI puente-losas")
    v.add_argument("--salida", default="salidas")
    v.add_argument("--nombre", default="Proyecto Ejemplo")
    v.set_defaults(func=_cmd_visor)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, KeyError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
