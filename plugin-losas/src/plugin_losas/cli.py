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


def _cargar_json(ruta: str) -> dict:
    with open(ruta, encoding="utf-8-sig") as f:
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

    exportado = export_para_puente(filas) if args.dxf else None
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
            json.dump(exportado, f, indent=1, ensure_ascii=False)
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


def _cmd_secciones(args) -> int:
    from puente_losas.contrato import aplicar_usos, panos_desde_dict

    from plugin_losas.secciones_revit import (escribir_secciones_json,
                                              resolver_secciones)

    panos = panos_desde_dict(_cargar_json(args.proyecto))
    if args.usos:
        panos = aplicar_usos(panos, _cargar_json(args.usos))
    fijadas = _cargar_json(args.secciones) if args.secciones else None
    resueltas = resolver_secciones(panos, fijadas)
    os.makedirs(args.salida, exist_ok=True)
    ruta = os.path.join(args.salida, "secciones_losas.json")
    escribir_secciones_json(resueltas, ruta)
    autos = sum(1 for r in resueltas.values() if r.origen == "auto")
    print(f"{len(resueltas)} losas con sección resuelta ({autos} por reglamento).")
    for r in resueltas.values():
        print(f"  {r.mark}: {r.seccion} ({r.espesor_m} m, {r.origen})")
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
    mapa = renumerar(cajas, args.prefijo, inicio=args.inicio, relleno=args.relleno)
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


def _cmd_plano(args) -> int:
    from plugin_losas.plano_acero import escribir_plano_acero, plano_acero

    proyecto = _cargar_json(args.proyecto)
    resultados = _cargar_json(args.resultados)
    acero = _cargar_json(args.acero) if args.acero else None
    editados = _cargar_json(args.editados) if args.editados else None
    plan = plano_acero(proyecto, resultados, acero, editados)
    os.makedirs(args.salida, exist_ok=True)
    ruta = os.path.join(args.salida, "plan_acero.json")
    escribir_plano_acero(plan, ruta)
    n_trazos = sum(len(x["trazos"]) for x in plan["losas"]) + len(plan["apoyos"])
    print(f"Plano de acero: {len(plan['losas'])} losas, {len(plan['apoyos'])} bastones "
          f"de apoyo, {n_trazos} trazos.")
    print(f"  {ruta}")
    return 0


def _cmd_modelado(args) -> int:
    from plugin_losas.modelado_acero import escribir_plan_modelado, plan_modelado

    plan = plan_modelado(
        _cargar_json(args.proyecto), _cargar_json(args.resultados),
        acero_pm=_cargar_json(args.acero) if args.acero else None,
        editados=_cargar_json(args.editados) if args.editados else None,
        secciones=_cargar_json(args.secciones) if args.secciones else None,
        aligeradas=_cargar_json(args.aligeradas) if args.aligeradas else None)
    os.makedirs(args.salida, exist_ok=True)
    ruta = os.path.join(args.salida, "plan_modelado.json")
    escribir_plan_modelado(plan, ruta)
    n_sets = sum(x["resumen"]["sets"] for x in plan["losas"]) + len(plan["bastones"])
    n_barras = sum(x["resumen"]["barras"] for x in plan["losas"])
    n_solapes = sum(x["resumen"]["solapes"] for x in plan["losas"])
    print(f"Modelado 3D: {len(plan['losas'])} losas, {n_sets} sets, "
          f"{n_barras} barras, {n_solapes} solapes, {len(plan['bastones'])} bastones.")
    for aviso in plan["avisos"]:
        print(f"  aviso: {aviso}")
    print(f"  {ruta}")
    return 0


def _cmd_acero(args) -> int:
    from plugin_losas.acero_pm import acero_pm_de_resultados, escribir_acero_pm

    acero = acero_pm_de_resultados(_cargar_json(args.resultados))
    os.makedirs(args.salida, exist_ok=True)
    ruta = os.path.join(args.salida, "acero_pm.json")
    escribir_acero_pm(acero, ruta)
    print(f"Acero PM comercial de {len(acero['losas'])} losas y {len(acero['apoyos'])} apoyos.")
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
    from plugin_losas.resultados_pm import dto_visor, escribir_visor

    proyecto = _cargar_json(args.proyecto)
    resultados = _cargar_json(args.resultados)
    if args.nivel:
        marks = {str(rec.get("mark") or rec.get("id")) for rec in proyecto.get("losas") or []
                 if (rec.get("nivel") or "") == args.nivel}
        if not marks:
            raise ValueError(f"ninguna losa en el nivel '{args.nivel}'.")
        proyecto = dict(proyecto)
        proyecto["losas"] = [rec for rec in proyecto["losas"]
                             if str(rec.get("mark") or rec.get("id")) in marks]
        pm = resultados["pieper_martens"]
        resultados = {
            "panos": [p for p in resultados.get("panos") or [] if p["mark"] in marks],
            "pieper_martens": {
                "metodo": pm.get("metodo"),
                "losas": {k: v for k, v in pm["losas"].items() if k in marks},
                "apoyos": [a for a in pm.get("apoyos") or []
                           if a["losa_i"] in marks and a["losa_j"] in marks],
            },
        }
    os.makedirs(args.salida, exist_ok=True)

    acero = None
    try:
        from plugin_losas.acero_pm import acero_pm_de_resultados, escribir_acero_pm
        acero = acero_pm_de_resultados(resultados)
        ruta_acero = os.path.join(args.salida, "acero_pm.json")
        escribir_acero_pm(acero, ruta_acero)
        print(f"Acero PM comercial calculado (motor EstructurasRD): {ruta_acero}")
    except ImportError:
        print("aviso: motor_fea no instalado — el visor sale sin acero comercial PM.")

    ruta = os.path.join(args.salida, "visor_losas.html")
    dto = dto_visor(proyecto, resultados, args.nombre, acero=acero)
    escribir_visor(dto, ruta)
    from plugin_losas.exportacion_pm import escribir_exportacion_pm
    ruta_excel = os.path.join(args.salida, "exportacion_pm.xlsx")
    escribir_exportacion_pm(proyecto, resultados, ruta_excel, args.nombre, acero=acero)
    print(f"Visor con {len(dto.panos)} paños y {len(dto.apoyos)} apoyos PM.")
    print(f"  {ruta}")
    print(f"  {ruta_excel}")
    return 0


def _cmd_dxf_salida(args) -> int:
    from pathlib import Path
    from plugin_losas.acad_dxf_out import EspesorRotulo, escribir_dxf, guardar_dxf
    offset=(0.,0.)
    if args.proyecto:
        data=_cargar_json(args.proyecto)
        records=data.get('losas') or []
        selected=[r for r in records if not args.nivel or r.get('nivel')==args.nivel]
        if any(r.get('huecos') for r in selected):
            raise ValueError('Esta salida no admite huecos; no se omiten del contorno silenciosamente.')
        filas=filas_desde_export({**data,'losas':selected})
        if args.usar_origen_modelo:
            origin=data.get('meta',{}).get('traslacion_origen_mm')
            if not origin or len(origin)!=2:raise ValueError('Sin traslacion_origen_mm XY en el proyecto')
            offset=tuple(float(v)/1000 for v in origin)
    else:
        if args.usar_origen_modelo:raise ValueError('--usar-origen-modelo requiere --proyecto')
        text=Path(args.dxf).read_text(encoding=args.codificacion)
        filas,avisos=losas_desde_dxf(text,args.capa,args.capa_textos,escala_a_m=args.escala)
        for aviso in avisos:print('aviso: '+aviso)
        if args.nivel:filas=[f for f in filas if f.nivel==args.nivel]
    if not filas:raise ValueError('No hay losas en el nivel seleccionado')
    espesores={}
    if args.espesores:
        try:
            espesores={mark:EspesorRotulo(**r) for mark,r in _cargar_json(args.espesores).items()}
        except TypeError as ex:
            raise ValueError('Formato de --espesores invalido: '+str(ex)) from ex
    elif args.secciones:
        data=_cargar_json(args.secciones)
        for mark,r in data['secciones'].items():
            h=r.get('espesor_m');origen=r.get('criterio') or r.get('origen') or ''
            estado='pendiente' if h is None else 'fijado' if r.get('origen')=='fijada' else 'calculado'
            espesores[mark]=EspesorRotulo(h,origen,estado)
    elif args.resultados:
        for r in _cargar_json(args.resultados).get('panos',[]):
            e=r.get('espesor') or {};h=e.get('h_usado_m')
            espesores[r['mark']]=EspesorRotulo(h,e.get('criterio') or '','pendiente' if h is None else 'calculado')
    else:
        # Solo reusar un dato de DXF que ya trae procedencia; h de Revit es geometria.
        for f in filas:
            if f.fuente=='acad' and f.espesor_m is not None and f.criterio_espesor:
                espesores[f.mark]=EspesorRotulo(f.espesor_m,f.criterio_espesor,h_modelo_m=f.espesor_referencia_m)
            elif f.fuente=='acad' and (f.criterio_espesor or '').startswith('pendiente:'):
                espesores[f.mark]=EspesorRotulo(f.espesor_candidato_m,f.criterio_espesor.removeprefix('pendiente: '),
                                               'pendiente',f.espesor_referencia_m)
    text=escribir_dxf(filas,espesores,unidad=args.unidad,desplazamiento_m=offset,
                      altura_texto_m=args.altura_texto)
    path=Path(args.salida);path.parent.mkdir(parents=True,exist_ok=True)
    guardar_dxf(text,path)
    pendientes=sum(f.mark not in espesores or espesores[f.mark].estado=='pendiente' for f in filas)
    print(f'{len(filas)} contornos originales y rotulos GR; {pendientes} espesores pendientes: {path}')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="plugin-losas",
        description="Extracción de losas (Revit/AutoCAD), usos Tabla 4, aligeradas y visor PM.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="comando", required=True)

    dx=sub.add_parser('dxf-salida',help='DXF GR con contorno original, Mark y espesor con procedencia')
    source=dx.add_mutually_exclusive_group(required=True)
    source.add_argument('--proyecto');source.add_argument('--dxf')
    heights=dx.add_mutually_exclusive_group()
    heights.add_argument('--espesores',help='JSON {Mark:{h_m,origen,estado,h_modelo_m}}')
    heights.add_argument('--secciones',help='secciones_losas.json')
    heights.add_argument('--resultados',help='resultados.json con panos/espesor/criterio')
    dx.add_argument('--nivel');dx.add_argument('--capa',default='GR_LOSAS_CONTORNO')
    dx.add_argument('--capa-textos',default='GR_LOSAS_ROTULOS')
    dx.add_argument('--escala',type=float,default=.001,help='unidades del DXF de entrada a m')
    dx.add_argument('--codificacion',default='cp1252')
    dx.add_argument('--unidad',choices=['m','mm'],default='mm')
    dx.add_argument('--usar-origen-modelo',action='store_true',help='sumar traslacion_origen_mm del export Revit')
    dx.add_argument('--altura-texto',type=float,default=.18,help='altura del Mark en m de modelo')
    dx.add_argument('--salida',required=True,help='archivo DXF nuevo')
    dx.set_defaults(func=_cmd_dxf_salida)

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
    rn.add_argument("--relleno", type=int, default=2, help="ceros a la izquierda (2 → L00)")
    rn.add_argument("--inicio", type=int, default=0, help="primer número (ley: 0 → L00)")
    rn.add_argument("--usos", help="usos.json del puente (marca los vuelos, que no se renumeran)")
    rn.add_argument("--salida", default="salidas")
    rn.set_defaults(func=_cmd_renumerar)

    se = sub.add_parser("secciones", help="sección final por losa (fijada o reglamento) "
                                          "+ payload de tipos de Floor para Revit")
    se.add_argument("--proyecto", required=True)
    se.add_argument("--usos", help="usos.json del puente (1D/2D, vuelos, bordes)")
    se.add_argument("--secciones", help="JSON {mark: seccion} fijadas en el panel")
    se.add_argument("--salida", default="salidas")
    se.set_defaults(func=_cmd_secciones)

    tp = sub.add_parser("tipos", help="tipo de losa según apoyos (código DL) + payload para Revit")
    tp.add_argument("--proyecto", required=True)
    tp.add_argument("--usos", help="usos.json del puente (marca vuelos: cambian el tipo)")
    tp.add_argument("--salida", default="salidas")
    tp.set_defaults(func=_cmd_tipos)

    pl = sub.add_parser("plano", help="trazos del armado en planta (principal/temp/bastones)")
    pl.add_argument("--proyecto", required=True)
    pl.add_argument("--resultados", required=True)
    pl.add_argument("--acero", help="acero_pm.json (armado comercial calculado)")
    pl.add_argument("--editados", help="JSON {mark: {x,y,apoyo}} con el acero editado (manda)")
    pl.add_argument("--salida", default="salidas")
    pl.set_defaults(func=_cmd_plano)

    md = sub.add_parser("modelado", help="plan de modelado 3D del acero (sets de Rebar, "
                                         "solape 50db mitad y mitad, nervios y bastones)")
    md.add_argument("--proyecto", required=True)
    md.add_argument("--resultados", required=True)
    md.add_argument("--acero", help="acero_pm.json (armado comercial calculado)")
    md.add_argument("--editados", help="JSON {mark: {x,y,apoyo}} con el acero editado (manda)")
    md.add_argument("--secciones", help="secciones_losas.json (sección/espesor final por losa)")
    md.add_argument("--aligeradas", help="plan_aligeradas.json (posiciones de nervios)")
    md.add_argument("--salida", default="salidas")
    md.set_defaults(func=_cmd_modelado)

    ac = sub.add_parser("acero", help="acero comercial PM (barra y separación) de resultados.json")
    ac.add_argument("--resultados", required=True)
    ac.add_argument("--salida", default="salidas")
    ac.set_defaults(func=_cmd_acero)

    u = sub.add_parser("usos", help="lista numerada de los usos Tabla 4 (para el LISP/panel)")
    u.add_argument("--tabla4", default=None)
    u.add_argument("--salida", default="salidas")
    u.set_defaults(func=_cmd_usos)

    v = sub.add_parser("visor", help="visor HTML de la vía Pieper-Martens")
    v.add_argument("--proyecto", required=True)
    v.add_argument("--resultados", required=True, help="resultados.json del CLI puente-losas")
    v.add_argument("--salida", default="salidas")
    v.add_argument("--nombre", default="Proyecto Ejemplo")
    v.add_argument("--nivel", default=None,
                   help="limitar el visor a un nivel (nombre exacto del nivel de Revit)")
    v.set_defaults(func=_cmd_visor)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, KeyError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
