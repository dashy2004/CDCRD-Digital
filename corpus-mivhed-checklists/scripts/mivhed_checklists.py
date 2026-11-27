#!/usr/bin/env python3
"""Utilidades para el dataset de checklists del portal NORM del MIVHED.

Uso (ejecutar con -I para no cargar módulos de la carpeta actual):

  python3 -I mivhed_checklists.py validar  mivhed-norm-checklists.json
  python3 -I mivhed_checklists.py generar  mivhed-norm-checklists.json SALIDA/
  python3 -I mivhed_checklists.py mapa     mivhed-norm-checklists.json mapa-memoria-estructural.json

validar : recalcula los conteos y los compara con _meta.conteos.
generar : escribe un .md por checklist, casos.csv (un renglón por motivo) e indice-normas.md.
mapa    : comprueba que un mapa de grupos de ítems sigue apuntando a los mismos títulos
          (detecta que el MIVHED haya insertado, quitado o reordenado ítems) y que cubre
          todos los ítems del checklist una sola vez.

No requiere paquetes externos. No escribe fuera de la carpeta de salida.
"""
import csv
import json
import sys
import unicodedata
from pathlib import Path

ESQUEMA = "mivhed-norm-checklists/1"


def norm(s):
    """Minúsculas, sin acentos, espacios colapsados: solo para comparar títulos."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.casefold().split())


def cargar(ruta):
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    esquema = datos.get("_meta", {}).get("esquema")
    if esquema != ESQUEMA:
        sys.exit(f"Esquema inesperado: {esquema!r} (se esperaba {ESQUEMA!r})")
    return datos


def conteos(datos):
    cl = datos["checklists"]
    items = [i for c in cl for i in c["items"]]
    return {
        "checklists": len(cl),
        "items": len(items),
        "motivosIncumplimiento": sum(len(i["motivosIncumplimiento"]) for i in items),
        "motivosNoAplica": sum(len(i["motivosNoAplica"]) for i in items),
        "referenciasLegales": sum(len(i["baseLegal"]) for i in items),
        "normas": len(datos.get("normas", [])),
    }


def errores_de_validacion(datos):
    errores = []
    esperado = datos["_meta"].get("conteos", {})
    real = conteos(datos)
    for k, v in real.items():
        if esperado.get(k) != v:
            errores.append(f"conteo {k}: _meta={esperado.get(k)} real={v}")
    for c in datos["checklists"]:
        ids = set()
        for n, i in enumerate(c["items"], start=1):
            if i["numero"] != n:
                errores.append(f"{c['codigo']}: ítem en posición {n} dice numero={i['numero']}")
            if i["id"] != f"{c['codigo']}#{n}":
                errores.append(f"{c['codigo']}: id inesperado {i['id']}")
            if i["id"] in ids:
                errores.append(f"{c['codigo']}: id repetido {i['id']}")
            ids.add(i["id"])
            for k, m in enumerate(i["motivosIncumplimiento"], start=1):
                if m["codigo"] != f"{n}.{k}":
                    errores.append(f"{i['id']}: código {m['codigo']} != {n}.{k}")
            for k, m in enumerate(i["motivosNoAplica"], start=1):
                if m["codigo"] != f"{n}.NA{k}":
                    errores.append(f"{i['id']}: código {m['codigo']} != {n}.NA{k}")
    return errores


def slug(codigo):
    s = norm(codigo.replace("CHECK-", ""))
    return "".join(ch if ch.isalnum() else "-" for ch in s).strip("-")


def linea(s):
    return " ".join((s or "").split())


def md_checklist(c, meta):
    out = []
    out.append("---")
    out.append(f"codigo: {c['codigo']}")
    out.append(f"nombre: {c['nombre']}")
    out.append(f"version: {c['version']}")
    out.append(f"estado_publicacion: {c['estadoPublicacion']}")
    out.append(f"publicado_en: {c.get('publicadoEn')}")
    out.append(f"tipo: {c['tipo']['nombre']}")
    out.append(f"extraido_en: {meta['extraidoEn']}")
    out.append("fuente: Portal NORM del MIVHED (API pública)")
    out.append("---")
    out.append("")
    out.append(f"# {c['nombre']} ({c['codigo']} v{c['version']})")
    out.append("")
    if "draft" in str(c["version"]).lower():
        out.append("> Versión borrador (`-draft`) según el portal: puede cambiar. Citar siempre la versión.")
        out.append("")
    if c["documentosRequeridos"]:
        out.append("## Documentos requeridos (según el portal)")
        out.append("")
        for d in c["documentosRequeridos"]:
            obl = "obligatorio" if d.get("obligatorio") else "no obligatorio"
            fmt = d.get("formatosAceptados")
            fmt = ", ".join(fmt) if isinstance(fmt, list) else (fmt or "sin formato indicado")
            out.append(f"- {d['tipo']} ({obl}; {fmt})")
        out.append("")
    out.append("## Ítems")
    out.append("")
    for i in c["items"]:
        out.append(f"### {i['numero']}. {i['descripcion']}")
        out.append("")
        out.append(f"- ID: `{i['id']}` · evaluación: {' / '.join(i['evaluacion'])}")
        if i.get("justificacion"):
            out.append(f"- Justificación: {linea(i['justificacion'])}")
        out.append("")
        if i["motivosIncumplimiento"]:
            out.append("Motivos de incumplimiento:")
            out.append("")
            for m in i["motivosIncumplimiento"]:
                out.append(f"- **{m['codigo']}** {linea(m['texto'])}")
            out.append("")
        if i["motivosNoAplica"]:
            out.append("Motivos de no aplicabilidad:")
            out.append("")
            for m in i["motivosNoAplica"]:
                out.append(f"- **{m['codigo']}** {linea(m['texto'])}")
            out.append("")
        if i["baseLegal"]:
            out.append("Base legal:")
            out.append("")
            for r in i["baseLegal"]:
                partes = [r.get("instrumento") or "", r.get("edicion") or ""]
                cab = " · ".join(p for p in partes if p)
                det = linea(" ".join(p for p in [r.get("etiqueta"), r.get("encabezado")] if p))
                ruta = r.get("ruta") or ""
                out.append(f"- {cab}" + (f" — {det}" if det else "") + (f" (`{ruta}`)" if ruta else ""))
            out.append("")
    return "\n".join(out)


def cmd_validar(ruta):
    datos = cargar(ruta)
    errores = errores_de_validacion(datos)
    print(json.dumps(conteos(datos), ensure_ascii=False))
    if errores:
        print(f"{len(errores)} problema(s):")
        for e in errores[:50]:
            print(" -", e)
        return 1
    print("OK: conteos y códigos consistentes con _meta.")
    return 0


def cmd_generar(ruta, salida):
    datos = cargar(ruta)
    errores = errores_de_validacion(datos)
    if errores:
        print(f"El JSON no valida ({len(errores)} problema(s)); no se genera nada. Primera: {errores[0]}")
        return 1
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    meta = datos["_meta"]
    filas = []
    for orden, c in enumerate(datos["checklists"], start=1):
        nombre = f"{orden:02d}-{slug(c['codigo'])}.md"
        (salida / nombre).write_text(md_checklist(c, meta), encoding="utf-8")
        for i in c["items"]:
            for tipo, lista in (("incumplimiento", i["motivosIncumplimiento"]), ("no_aplica", i["motivosNoAplica"])):
                for m in lista:
                    filas.append([c["codigo"], c["version"], c["estadoPublicacion"], i["numero"],
                                  i["descripcion"], tipo, m["codigo"], m["texto"]])
    with open(salida / "casos.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["checklist", "version", "estado", "item", "item_descripcion", "tipo", "codigo", "texto"])
        w.writerows(filas)
    lineas = ["# Índice de normas del portal NORM", "",
              f"Extraído el {meta['extraidoEn']}. Instrumentos devueltos por la API: {len(datos['normas'])}.", ""]
    for n in sorted(datos["normas"], key=lambda x: (x.get("numero") or "")):
        vers = "; ".join(f"{v['nombre']} ({v.get('vigencia')})" for v in n.get("versiones", []))
        lineas.append(f"- **{n.get('numero')}** ({n.get('anio')}) {n['titulo']} — {vers}")
    (salida / "indice-normas.md").write_text("\n".join(lineas) + "\n", encoding="utf-8")
    print(f"Escritos {len(datos['checklists'])} .md, casos.csv ({len(filas)} filas) e indice-normas.md en {salida}")
    return 0


def cmd_mapa(ruta, ruta_mapa):
    datos = cargar(ruta)
    mapa = json.loads(Path(ruta_mapa).read_text(encoding="utf-8"))
    c = next((x for x in datos["checklists"] if x["codigo"] == mapa["checklist"]), None)
    if c is None:
        print("El checklist del mapa no existe en el JSON:", mapa["checklist"])
        return 1
    problemas = []
    if str(c["version"]) != str(mapa["version_mapeada"]):
        problemas.append(f"versión: el mapa se hizo sobre {mapa['version_mapeada']} y el JSON trae {c['version']}")
    cubiertos = {}
    for g in mapa["grupos"]:
        a, b = g["items"]
        for n in range(a, b + 1):
            if n in cubiertos:
                problemas.append(f"ítem {n} en dos grupos: {cubiertos[n]} y {g['id']}")
            cubiertos[n] = g["id"]
        for n, esperado in ((a, g["titulo_primero"]), (b, g["titulo_ultimo"])):
            if not 1 <= n <= len(c["items"]):
                problemas.append(f"{g['id']}: ítem {n} fuera de rango (hay {len(c['items'])})")
                continue
            real = c["items"][n - 1]["descripcion"]
            if not norm(real).startswith(norm(esperado)):
                problemas.append(f"{g['id']}: el ítem {n} ahora es «{real[:70]}» y el mapa esperaba «{esperado}»")
    sin = [i["numero"] for i in c["items"] if i["numero"] not in cubiertos]
    if sin:
        problemas.append(f"ítems sin grupo: {sin}")
    if problemas:
        print(f"{len(problemas)} problema(s) en el mapa:")
        for p in problemas:
            print(" -", p)
        return 1
    print(f"OK: {len(mapa['grupos'])} grupos cubren los {len(c['items'])} ítems de {c['codigo']} v{c['version']}.")
    return 0


def main(argv):
    if len(argv) >= 3 and argv[1] == "validar":
        return cmd_validar(argv[2])
    if len(argv) >= 4 and argv[1] == "generar":
        return cmd_generar(argv[2], argv[3])
    if len(argv) >= 4 and argv[1] == "mapa":
        return cmd_mapa(argv[2], argv[3])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
