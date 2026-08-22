#!/usr/bin/env python3
# CDCRD Digital - indice global datos/INDICE.json + INDICE.md
# Uso: gen_indice.py <dir_datos> <dir_md>
import json, sys, datetime
from pathlib import Path

def fila(doc, vol, jpath, mpath):
    pgs = [p for c in doc['clausulas'] for p in c['paginas']]
    return {"volumen": vol, "titulo": doc['titulo'], "nombre": doc['nombre'],
            "json": jpath, "md": mpath, "clausulas": len(doc['clausulas']),
            "paginas_pdf": [min(pgs), max(pgs)] if pgs else None,
            "capitulos": doc.get('capitulos') or None,
            "fuente_pdf": doc.get('fuente_pdf')}

def main(dir_datos, dir_md):
    dir_datos = Path(dir_datos)
    vols = {}
    t1 = dir_datos / "titulos"
    for f in sorted(t1.glob("T*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        vols.setdefault(1, {"volumen": 1, "sigla": None,
            "nombre": "Código de Construcción RD — Volumen I (Tomos 1-2)",
            "titulos": []})["titulos"].append(
            fila(d, 1, f"datos/titulos/{f.name}", f"md/vol-1/{f.stem}.md"))
    for vdir in sorted(dir_datos.glob("vol-*")):
        vol = int(vdir.name.split("-")[1])
        for f in sorted(vdir.glob("T*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            vols.setdefault(vol, {"volumen": vol, "sigla": d.get('sigla'),
                "nombre": d.get('nombre_volumen'), "titulos": []})["titulos"].append(
                fila(d, vol, f"datos/{vdir.name}/{f.name}", f"md/{vdir.name}/{f.stem}.md"))
    total = sum(t['clausulas'] for v in vols.values() for t in v['titulos'])
    idx = {"generado": datetime.date.today().isoformat(),
           "total_clausulas": total,
           "uso": "Buscar el Título por tema aquí; abrir SOLO el json o md de ese Título. "
                  "Cada cláusula trae su página del PDF oficial.",
           "volumenes": [vols[k] for k in sorted(vols)]}
    (dir_datos / "INDICE.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    L = ["# Índice global CDCRD-Digital", "",
         f"{total} cláusulas. Flujo: ubicar el Título aquí → abrir solo ese archivo.", ""]
    L.append("| Vol | Título | Nombre | Cláusulas | pp. PDF | JSON | MD |")
    L.append("|---|---|---|---|---|---|---|")
    for v in idx['volumenes']:
        for t in v['titulos']:
            pg = f"{t['paginas_pdf'][0]}-{t['paginas_pdf'][1]}" if t['paginas_pdf'] else "-"
            L.append(f"| {v['volumen']} | T{t['titulo']} | {t['nombre']} | {t['clausulas']} | {pg} | `{t['json']}` | `{t['md']}` |")
    (dir_datos / "INDICE.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("INDICE.json + INDICE.md:", total, "clausulas,", len(idx['volumenes']), "volumenes")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
