#!/usr/bin/env python3
# CDCRD Digital - genera espejo Markdown por Titulo desde los JSON.
# Uso: gen_md.py <dir_datos> <dir_md>
#   dir_datos: contiene titulos/ (Vol I) y vol-2..vol-5/
import json, sys
from pathlib import Path

def render(doc, vol, es_vol1):
    L = []
    sig = f" ({doc.get('sigla')})" if doc.get('sigla') else ""
    nvol = doc.get('nombre_volumen') or "Código de Construcción de la República Dominicana, Volumen I"
    L.append(f"# Vol {vol}{sig} — Título {doc['titulo']}. {doc['nombre']}")
    L.append("")
    fuente = doc.get('fuente_pdf') or "TOMO-1-VOLUMEN-1-JULIO-2026.pdf / MIVHED-...Vol-1-Tomo-2.pdf (ver campo tomo)"
    L.append(f"{nvol}. Fuente: `{fuente}`. `p.` = página del PDF. "
             f"Generado desde el JSON correspondiente en `datos/`; ante diferencias manda el PDF del MIVHED.")
    caps = doc.get('capitulos') or {}
    ultimo_cap = None
    for c in doc['clausulas']:
        cap = c.get('capitulo')
        if cap != ultimo_cap:
            ultimo_cap = cap
            nom = caps.get(cap, "")
            L.append("")
            L.append(f"## Capítulo {cap}" + (f". {nom.title()}" if nom else ""))
        pp = c['paginas']
        ppt = f"p. {pp[0]}" if len(pp) == 1 else f"pp. {pp[0]}-{pp[-1]}"
        if es_vol1 and c.get('tomo'):
            ppt += f", Tomo {c['tomo']}"
        enc = (c.get('encabezado') or "").strip()
        tit = f"### {c['id']}" + (f" — {enc}" if enc else "") + f" ({ppt})"
        L.append("")
        L.append(tit)
        fl = c.get('flags', {})
        if fl.get('formula') and not fl.get('vision_ok'):
            L.append("> ⚠ fórmula con posibles símbolos corruptos; cotejar el PDF antes de citar.")
        if c.get('num_conflicto'):
            L.append("> ⚠ numeración impresa no coincide con el Título posicional (rareza del documento fuente).")
        L.append("")
        L.append(c['texto'].strip())
        refs = (c.get('refs') or {}).get('externas') or []
        if refs:
            L.append("")
            L.append(f"*Refs: {', '.join(refs)}*")
    L.append("")
    return "\n".join(L)

def main(dir_datos, dir_md):
    dir_datos, dir_md = Path(dir_datos), Path(dir_md)
    # Vol I desde titulos/
    t1 = dir_datos / "titulos"
    if t1.is_dir():
        out = dir_md / "vol-1"; out.mkdir(parents=True, exist_ok=True)
        for f in sorted(t1.glob("T*.json")):
            doc = json.loads(f.read_text(encoding="utf-8"))
            (out / (f.stem + ".md")).write_text(render(doc, 1, True), encoding="utf-8")
            print("md/vol-1/" + f.stem + ".md", len(doc['clausulas']), "cl")
    # Vols 2-5
    for vdir in sorted(dir_datos.glob("vol-*")):
        vol = int(vdir.name.split("-")[1])
        out = dir_md / vdir.name; out.mkdir(parents=True, exist_ok=True)
        for f in sorted(vdir.glob("T*.json")):
            doc = json.loads(f.read_text(encoding="utf-8"))
            (out / (f.stem + ".md")).write_text(render(doc, vol, False), encoding="utf-8")
            print(f"md/{vdir.name}/{f.stem}.md", len(doc['clausulas']), "cl")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
