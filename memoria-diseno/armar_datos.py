"""Arma data.json desde las fuentes reales declaradas en un manifiesto.

Uso: python armar_datos.py fuentes.json data.json

fuentes.json:
{
  "niveles": [ {"nombre": "Nivel 1", "txt": "nivel-1.TXT", "dl": "nivel-1.DL"} ],
  "cargas": {"libro": "cargas-y-espesores.xlsx"},   (opcional: sobrecarga y, por nivel, las hojas
                                                     «Espesor <nivel>» y «Carga <nivel>»; un nivel puede
                                                     indicar "hoja_espesor" y "hoja_carga", o "sin_hojas": true)
  "bloques_json": [ "bloque-a.json" ],     (opcional: bloques ya extraídos con el contrato del README)
  "bloques": [ {"nombre": "Bloque A", "etabs": "bloque-a.EDB", "espectro": "bloque-a-espectro.xls",
                "art38": "bloque-a-art38.xls", "diseno_guardado": false} ],
  "fundaciones": {"safe": "fundaciones.FDB"}
}
Un bloque con "etabs" abre una COPIA del modelo en una instancia propia de ETABS (requiere ETABS
instalado), corre el análisis y lee sus tablas en tonf y metros. Lo leído queda en la carpeta
`_trabajo` junto al manifiesto y se reutiliza mientras el modelo no cambie.
Las rutas relativas se resuelven contra la carpeta del manifiesto.
Termina con código 1 si falta un archivo o el manifiesto está mal formado; los avisos de
lectura no detienen el proceso: quedan en data.json y el generador los lleva al documento.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuentes_losas  # noqa: E402


class ErrorDeFuentes(Exception):
    pass


def _ruta(base, p, que):
    if not p:
        raise ErrorDeFuentes("falta la ruta de %s" % que)
    p = p if os.path.isabs(p) else os.path.join(base, p)
    if not os.path.isfile(p):
        raise ErrorDeFuentes("no existe el archivo de %s: %s" % (que, p))
    return p


def armar(man_path, carpeta_trabajo=None):
    base = os.path.dirname(os.path.abspath(man_path))
    try:
        with open(man_path, encoding="utf-8") as f:
            man = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ErrorDeFuentes("no se pudo leer el manifiesto %s: %s" % (man_path, e))
    data = {"referencia_pdf": False, "paginas_total": 0, "sobrecarga": [], "niveles": [], "bloques": [], "avisos": []}
    for i, n in enumerate(man.get("niveles", []), 1):
        nombre = n.get("nombre") or "Nivel %d" % i
        txt = _ruta(base, n.get("txt"), "listado .TXT del nivel «%s»" % nombre)
        dl = _ruta(base, n["dl"], "datos .DL del nivel «%s»" % nombre) if n.get("dl") else None
        nv = fuentes_losas.nivel(nombre, txt, dl)
        for a in nv["avisos"]:
            data["avisos"].append("Losas, nivel %s: %s." % (nombre, a))
        if nv["sin_leer"]:
            data["avisos"].append("Losas, nivel %s: %d fila(s) del listado no se pudieron leer: %s."
                                  % (nombre, len(nv["sin_leer"]), " | ".join(nv["sin_leer"][:5])))
        data["niveles"].append(nv)
    if (man.get("cargas") or {}).get("libro"):
        _cargas(base, man, data)
    for p in man.get("bloques_json", []):
        with open(_ruta(base, p, "bloque"), encoding="utf-8") as f:
            data["bloques"].append(json.load(f))
    trabajo = carpeta_trabajo or os.path.join(base, "_trabajo")
    for i, b in enumerate(man.get("bloques", []), 1):
        data["bloques"].append(_bloque(base, trabajo, b, i))
    if (man.get("fundaciones") or {}).get("safe"):
        data["fundaciones"] = _fundaciones(base, trabajo, man["fundaciones"]["safe"])
    return data


def _fundaciones(base, trabajo, ruta):
    """Fundaciones desde el modelo de SAFE; lo leído se reutiliza mientras el modelo no cambie."""
    import fuentes_safe

    modelo = _ruta(base, ruta, "modelo de SAFE")
    carpeta = os.path.join(trabajo, "fundaciones")
    sello = _sello(modelo)
    p_sello, p_tablas = os.path.join(carpeta, "sello.json"), os.path.join(carpeta, "tablas.json")
    try:
        tablas = _leer_json(p_tablas) if _leer_json(p_sello) == sello else None
        if not tablas:
            tablas = fuentes_safe.leer_tablas(modelo, carpeta)
            _guardar_json(p_tablas, tablas)
            _guardar_json(p_sello, sello)
        return fuentes_safe.fundaciones_de(tablas)
    except Exception as e:  # noqa: BLE001 - COM, permisos: todo sale como un mensaje, no un volcado
        raise ErrorDeFuentes("fundaciones: %s: %s" % (type(e).__name__, e))


VERSION_LECTORES = 4         # se sube al cambiar qué tablas se leen: invalida lo guardado en _trabajo


def _cargas(base, man, data):
    """Sobrecarga del libro de cargas y, por nivel, sus hojas de espesor y de carga."""
    import fuentes_cargas
    import fuentes_excel

    ruta = _ruta(base, man["cargas"]["libro"], "libro de cargas y espesores")
    try:
        libro = fuentes_excel.abrir(ruta)
        bloques = fuentes_cargas.sobrecarga_de(libro)
        data["sobrecarga"] = bloques[:2]
        if len(bloques) != 2:
            data["avisos"].append("Cargas: el libro trae %d bloque(s) de sobrecarga; se esperaban dos (entrepiso y techo)."
                                  % len(bloques))
        data["cargas_meta"] = dict(fuentes_cargas.encabezado_de(libro), archivo=os.path.basename(ruta))
        por_nombre = {n.get("nombre"): n for n in man.get("niveles", [])}
        for nv in data["niveles"]:
            decl = por_nombre.get(nv["nombre"]) or {}
            if decl.get("sin_hojas"):
                continue
            n_e, h_e = fuentes_cargas.hoja_del_nivel(libro, "Espesor", nv["nombre"], decl.get("hoja_espesor"))
            n_c, h_c = fuentes_cargas.hoja_del_nivel(libro, "Carga", nv["nombre"], decl.get("hoja_carga"))
            esp, car = fuentes_cargas.espesores_de(h_e, n_e), fuentes_cargas.cargas_de(h_c, n_c)
            nv["esp"], nv["carga"] = esp["losas"], car["losas"]
            nv["hojas"] = {"espesor": n_e, "carga": n_c}
            for hoja, leidas in ((n_e, esp), (n_c, car)):
                if leidas["declaradas"] is not None and leidas["declaradas"] != len(leidas["losas"]):
                    data["avisos"].append("Cargas, nivel %s: la hoja «%s» declara %d losas y trae %d."
                                          % (nv["nombre"], hoja, leidas["declaradas"], len(leidas["losas"])))
            if len(esp["losas"]) != len(car["losas"]):
                data["avisos"].append("Cargas, nivel %s: la hoja «%s» trae %d losas y «%s» trae %d."
                                      % (nv["nombre"], n_e, len(esp["losas"]), n_c, len(car["losas"])))
            d = fuentes_cargas.diferencias_de_luces(esp["losas"], nv["mom"])
            for clave, texto in (("distintas", "tienen luces distintas en la hoja «%s» y en el listado de diseño" % n_e),
                                 ("solo_hoja", "están en la hoja «%s» y no en el listado de diseño" % n_e),
                                 ("solo_listado", "están en el listado de diseño y no en la hoja «%s»" % n_e)):
                if d[clave]:
                    data["avisos"].append("Cargas, nivel %s: %d losa(s) %s: %s%s."
                                          % (nv["nombre"], len(d[clave]), texto, ", ".join(d[clave][:12]),
                                             "…" if len(d[clave]) > 12 else ""))
    except ErrorDeFuentes:
        raise
    except Exception as e:  # noqa: BLE001 - hoja dañada, formato inesperado: sale como mensaje, no como volcado
        raise ErrorDeFuentes("libro de cargas: %s: %s" % (type(e).__name__, e))


def _sello(path):
    st = os.stat(path)
    return {"archivo": os.path.abspath(path), "bytes": st.st_size, "modificado_ns": st.st_mtime_ns,
            "lectores": VERSION_LECTORES}


def _leer_json(path):
    """Contenido del JSON, o None si no existe o está dañado (se trata como «no hay caché»)."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _guardar_json(path, obj):
    """Escritura atómica: un corte a mitad no deja un archivo truncado."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def _tablas_etabs(modelo, carpeta, diseno_guardado):
    """Tablas del modelo; se reutilizan las ya leídas si el archivo no cambió (correr ETABS tarda minutos)."""
    import fuentes_etabs

    sello = dict(_sello(modelo), diseno_guardado=bool(diseno_guardado))
    p_sello, p_tablas = os.path.join(carpeta, "sello.json"), os.path.join(carpeta, "tablas.json")
    guardadas = _leer_json(p_tablas) if _leer_json(p_sello) == sello else None
    if guardadas and not _muros_fallidos(guardadas):
        return guardadas
    tablas = fuentes_etabs.leer_tablas(modelo, carpeta, diseno_guardado)
    _guardar_json(p_tablas, tablas)
    _guardar_json(p_sello, sello)
    return tablas


def _muros_fallidos(tablas):
    """Un diseño de muros que falló (por la interfaz de ETABS) se reintenta en la corrida siguiente."""
    return ((tablas.get("_muros") or [{}])[0]).get("estado") == "sin diseño"


def _bloque(base, trabajo, b, i):
    """Un bloque desde sus fuentes directas: modelo de ETABS y hojas de cálculo."""
    import fuentes_etabs
    import fuentes_excel

    nombre = b.get("nombre") or "Bloque %d" % i
    blk = {"nombre": nombre, "paginas": {}, "espectro": {}, "tabla_espectro": [], "torsion": [], "art38": [], "cuasi": {}}
    try:
        if b.get("espectro"):
            art = _ruta(base, b["art38"], "hoja del Art. 38 de «%s»" % nombre) if b.get("art38") else None
            blk.update(fuentes_excel.hojas_de_bloque(_ruta(base, b["espectro"], "hoja de espectro de «%s»" % nombre), art))
        modelo = _ruta(base, b.get("etabs"), "modelo de ETABS de «%s»" % nombre)
        carpeta = os.path.join(trabajo, "bloque-%02d-%s" % (i, "".join(c if c.isalnum() else "_" for c in nombre)))
        blk["etabs"] = fuentes_etabs.etabs_de(_tablas_etabs(modelo, carpeta, b.get("diseno_guardado")))
    except ErrorDeFuentes:
        raise
    except Exception as e:  # noqa: BLE001 - COM, hojas dañadas, permisos: todo sale como un mensaje, no un volcado
        raise ErrorDeFuentes("%s: %s: %s" % (nombre, type(e).__name__, e))
    return blk


def main(argv):
    if len(argv) != 3:
        sys.stderr.write(__doc__)
        return 1
    try:
        data = armar(argv[1])
    except ErrorDeFuentes as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1
    with open(argv[2], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    for nv in data["niveles"]:
        sys.stdout.write("%s: %d losas, %d bordes X, %d bordes Y\n" % (nv["nombre"], len(nv["mom"]), len(nv["apx"]), len(nv["apy"])))
    for a in data["avisos"]:
        sys.stderr.write("AVISO: %s\n" % a)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
