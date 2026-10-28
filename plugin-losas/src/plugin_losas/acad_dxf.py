"""Lectura de los recuadros/numeración de losa de un plano de AutoCAD (DXF).

Convención del plano (la del flujo AutoCAD↔Excel/ETABS de la Ing. Arlette
Ramírez): cada paño es una **polilínea cerrada rectangular** en una capa de
losas, y su numeración es un **TEXT/MTEXT** cuyo punto de inserción cae dentro
del recuadro. El DWG se exporta/convierte a DXF ASCII (p. ej. con
``libredwg dwg2dxf``, igual que ``puente-autocad-etabs/inventario-ARDI.json``).

Parser mínimo propio (grupos código/valor del DXF ASCII): solo LWPOLYLINE,
TEXT y MTEXT, que es todo lo que esta extracción necesita. Sin dependencias.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

from plugin_losas.extraccion import FilaLosa

# Un recuadro "rectangular" admite este desvío entre el área del polígono y la
# de su caja (cubre dibujo impreciso; un paño en L real queda avisado).
TOL_RECTANGULO = 0.05


@dataclass(frozen=True)
class EntidadDxf:
    tipo: str                                  # LWPOLYLINE | TEXT | MTEXT
    capa: str
    puntos: tuple[tuple[float, float], ...]    # vértices (polilínea) o inserción (texto)
    cerrada: bool = False
    texto: str = ""
    datos_gr: tuple[str, ...] = ()
    curva: bool = False
    ocs_no_xy: bool = False


def _grupos(texto: str):
    """Pares (código, valor) del DXF ASCII."""
    lineas = texto.splitlines()
    for i in range(0, len(lineas) - 1, 2):
        codigo = lineas[i].strip()
        if not codigo.lstrip("-").isdigit():
            raise ValueError(f"DXF malformado: código de grupo no numérico en línea {i + 1}: {codigo!r}")
        yield int(codigo), lineas[i + 1].strip()


def leer_entidades(texto: str) -> list[EntidadDxf]:
    """Las LWPOLYLINE/TEXT/MTEXT de la sección ENTITIES de un DXF ASCII."""
    entidades: list[EntidadDxf] = []
    en_entities = False
    actual: dict | None = None

    def cerrar() -> None:
        nonlocal actual
        if actual is not None:
            puntos = tuple(zip(actual["xs"], actual["ys"]))
            entidades.append(EntidadDxf(actual["tipo"], actual["capa"], puntos,
                                        actual["cerrada"], actual["texto"], tuple(actual['gr']), actual['curva'],actual['ocs_no_xy']))
        actual = None

    for codigo, valor in _grupos(texto):
        if codigo == 2 and valor == "ENTITIES":
            en_entities = True
            continue
        if codigo == 0:
            if valor == "ENDSEC":
                cerrar()
                en_entities = False
                continue
            if en_entities:
                cerrar()
                if valor in ("LWPOLYLINE", "TEXT", "MTEXT"):
                    actual = {"tipo": valor, "capa": "", "xs": [], "ys": [],
                              "cerrada": False, "texto": "", 'gr':[], 'app':None, 'curva':False, 'ocs_no_xy':False}
            continue
        if actual is None:
            continue
        if codigo == 8:
            actual["capa"] = valor
        elif codigo == 10:
            actual["xs"].append(float(valor))
        elif codigo == 20:
            actual["ys"].append(float(valor))
        elif codigo == 70 and actual["tipo"] == "LWPOLYLINE":
            actual["cerrada"] = bool(int(valor) & 1)
        elif codigo == 42 and actual['tipo']=='LWPOLYLINE' and float(valor)!=0:
            actual['curva']=True
        elif codigo in (210,220,230) and actual['tipo']=='LWPOLYLINE':
            actual['ocs_no_xy'] |= abs(float(valor)-(1 if codigo==230 else 0))>1e-12
        elif codigo == 1001:
            actual['app']=valor
        elif codigo == 1000 and actual['app']=='GR_LOSAS':
            actual['gr'].append(valor)
        elif codigo == 1:
            actual["texto"] += valor
        elif codigo == 3 and actual["tipo"] == "MTEXT":   # continuación de texto largo
            actual["texto"] += valor
    cerrar()
    return entidades


# ------------------------------ geometría ------------------------------
def _area_poligono(pts) -> float:
    s = 0.0
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def _punto_en_poligono(x: float, y: float, pts) -> bool:
    dentro = False
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            dentro = not dentro
    return dentro


def _limpiar_mtext(texto: str) -> str:
    """Quita los códigos de formato más comunes de MTEXT ({\\f...;}, \\P)."""
    limpio = texto.replace("\\P", " ")
    while "{" in limpio and ";" in limpio:
        a = limpio.find("{")
        b = limpio.find(";", a)
        fin = limpio.find("}", a)
        if a < b < fin:
            limpio = limpio[:a] + limpio[b + 1:fin] + limpio[fin + 1:]
        else:
            break
    return limpio.strip()


@dataclass(frozen=True)
class RecuadroLosa:
    contorno: tuple[tuple[float, float], ...]
    lx: float
    ly: float
    area_m2: float
    es_rectangular: bool
    datos_gr: tuple[str, ...] = ()


def recuadros_losa(entidades: list[EntidadDxf], capa: str) -> list[RecuadroLosa]:
    """Las polilíneas cerradas de la capa de losas, como recuadros Lx×Ly."""
    out = []
    for e in entidades:
        if e.tipo != "LWPOLYLINE" or e.capa != capa or not e.cerrada or len(e.puntos) < 3:
            continue
        pts = e.puntos
        if e.curva:
            raise ValueError('Contorno DXF con arcos/bulge: no se convierte en segmentos rectos silenciosamente.')
        if e.ocs_no_xy:
            raise ValueError('Contorno DXF con OCS distinto de XY: transformar a WCS antes de importar.')
        if len(pts) > 3 and pts[0] == pts[-1]:
            pts = pts[:-1]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        lx = max(xs) - min(xs)
        ly = max(ys) - min(ys)
        if lx <= 0 or ly <= 0:
            continue
        area = _area_poligono(pts)
        es_rect = abs(area - lx * ly) <= TOL_RECTANGULO * lx * ly
        out.append(RecuadroLosa(tuple(pts), lx, ly, area, es_rect,e.datos_gr))
    return out


def textos_numeracion(entidades: list[EntidadDxf], capa: str | None = None
                      ) -> list[tuple[float, float, str]]:
    """(x, y, texto) de los TEXT/MTEXT (de la capa dada, o de todas si None)."""
    out = []
    for e in entidades:
        if e.tipo not in ("TEXT", "MTEXT") or not e.puntos:
            continue
        if capa is not None and e.capa != capa:
            continue
        if 'rol:espesor' in e.datos_gr:
            continue
        contenido = _limpiar_mtext(e.texto) if e.tipo == "MTEXT" else e.texto.strip()
        if contenido:
            out.append((e.puntos[0][0], e.puntos[0][1], contenido))
    return out


def losas_desde_dxf(texto_dxf: str, capa_losas: str = "LOSAS",
                    capa_textos: str | None = None, espesor_m: float | None = None,
                    escala_a_m: float = 1.0) -> tuple[list[FilaLosa], list[str]]:
    """Recuadros + numeración del DXF → filas del panel (fuente "acad") + avisos.

    ``escala_a_m`` convierte las unidades del dibujo a metros (1.0 si el plano
    está en metros; 0.001 si está en milímetros). El espesor no viaja en el
    plano 2D: se pasa como parámetro (o queda vacío para declararlo en el panel).
    """
    entidades = leer_entidades(texto_dxf)
    recuadros = recuadros_losa(entidades, capa_losas)
    textos = textos_numeracion(entidades, capa_textos)
    avisos: list[str] = []
    if not recuadros:
        raise ValueError(f"El DXF no tiene polilíneas cerradas en la capa '{capa_losas}'.")

    filas: list[FilaLosa] = []
    usados: set[int] = set()
    vistos: dict[str, int] = {}
    for n, r in enumerate(recuadros, start=1):
        meta=dict(v.split(':',1) for v in r.datos_gr if ':' in v)
        extras={key:float(meta[key]) for key in ('h_candidato_m','h_referencia_m') if key in meta}
        if any(not math.isfinite(v) or v<=0 for v in extras.values()):
            raise ValueError('Espesor candidato/referencia DXF invalido')
        h=espesor_m
        criterio='declarado al importar DXF' if h is not None else None
        if h is None and meta.get('estado')=='pendiente':
            criterio='pendiente: '+meta.get('origen','sin resultado')
        if h is None and 'h_m' in meta and meta.get('estado') in ('calculado','fijado'):
            h=float(meta['h_m'])
            if not math.isfinite(h) or h<=0 or not meta.get('origen'):
                raise ValueError('Espesor DXF sin valor/procedencia validos')
            criterio=meta['origen']
        marks = []
        for k, (x, y, t) in enumerate(textos):
            if k not in usados and _punto_en_poligono(x, y, r.contorno):
                marks.append((k, t))
        if marks:
            k, mark = marks[0]
            usados.add(k)
            if len(marks) > 1:
                avisos.append(f"recuadro {n}: {len(marks)} textos dentro; se toma '{mark}'.")
        else:
            mark = f"SN-{n}"
            avisos.append(f"recuadro {n} ({r.lx:.2f}×{r.ly:.2f}): sin numeración; se nombra '{mark}'.")
        if mark in vistos:
            vistos[mark] += 1
            nuevo = f"{mark}-{vistos[mark]}"
            avisos.append(f"numeración repetida '{mark}': el recuadro {n} pasa a '{nuevo}'.")
            mark = nuevo
        else:
            vistos[mark] = 1
        if not r.es_rectangular:
            avisos.append(f"{mark}: el contorno no es rectangular (área {r.area_m2:.2f} ≠ "
                          f"{r.lx:.2f}×{r.ly:.2f}); se conserva el contorno, Lx/Ly son del bbox.")
        e = escala_a_m
        filas.append(FilaLosa(
            mark=mark, nivel=meta.get('nivel'), lx=r.lx * e, ly=r.ly * e,
            area_m2=r.area_m2 * e * e, espesor_m=h, fuente="acad",
            revit_id=int(meta['id_revit']) if 'id_revit' in meta else None,
            criterio_espesor=criterio,
            espesor_candidato_m=extras.get('h_candidato_m'),
            espesor_referencia_m=extras.get('h_referencia_m'),
            contorno=tuple((x * e, y * e) for x, y in r.contorno)))
    sobran = len(textos) - len(usados)
    if sobran > 0:
        avisos.append(f"{sobran} texto(s) de numeración fuera de todo recuadro (ignorados).")
    return filas, avisos


def export_para_puente(filas: list[FilaLosa], espesor_defecto: float = 0.20) -> dict:
    """Bloque ``losas`` (contrato de puente-losas) desde filas de AutoCAD.

    Permite correr el mismo CLI ``puente-losas`` con losas que vienen del DWG.
    ``z_tope`` queda en 0 (el plano 2D no trae cota); la adyacencia funciona
    igual porque todos los paños comparten esa cota.
    """
    losas = []
    for f in filas:
        if f.espesor_m is None and (f.criterio_espesor or '').startswith('pendiente:'):
            raise ValueError(f'{f.mark}: espesor pendiente; no se aplica un espesor por defecto.')
        losas.append({
            "id": f.mark, "mark": f.mark, "nivel": f.nivel, "z_tope": 0.0,
            "revit_id":f.revit_id,
            "contorno": [[x, y] for x, y in f.contorno] or
                        [[0.0, 0.0], [f.lx, 0.0], [f.lx, f.ly], [0.0, f.ly]],
            "huecos": [], "lx": round(f.lx, 3), "ly": round(f.ly, 3),
            "area_m2": round(f.area_m2, 2) if f.area_m2 is not None else None,
            "espesor": {"h_usado": f.espesor_m or espesor_defecto,
                        "criterio":f.criterio_espesor},
        })
    return {"meta": {"fuente": "plugin-losas/acad_dxf", "unidades": {"longitud": "m"}},
            "losas": losas}
