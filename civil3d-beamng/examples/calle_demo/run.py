"""Generate a synthetic street through the native bridge, without UI automation."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

PLAN = {
    "tipo": "demostracion sintetica; no proyecto constructivo",
    "longitud_m": 215.66370614359175,
    "carriles": 2,
    "ancho_calzada_m": 7.2,
    "curvas_horizontales": {"cantidad": 2, "radio_m": 120},
    "pendientes_rasante": [0.02, -0.015714285714285632, 0.02536847541128854],
    "bache": {"estacion_m": 112, "offset_m": 1.05, "envolvente_m": [2.75, 1.79],
              "profundidad_m": 0.0635, "contorno": "irregular"},
    "bloques_3d": ["vivienda", "arbol", "luminaria", "senal", "banco", "imbornal"],
    "instancias": 61,
    "puente_minimo": "0.5.19",
    "exportacion": {"formato": "PNG", "rotacion": "0", "vista_guardada": True},
}


def preflight(expected, actual, version, objects, output):
    if not expected or expected != actual:
        raise ValueError("El dibujo activo no coincide exactamente con --drawing.")
    try:
        parts = tuple(int(part) for part in version.split("."))
    except (AttributeError, ValueError):
        raise ValueError("Version del puente no reconocida.")
    if parts < (0, 5, 19):
        raise ValueError("Requiere puente activo 0.5.19 o posterior; una DLL compilada no basta.")
    if objects != 0:
        raise ValueError("El ejemplo requiere un dibujo metrico nuevo con espacio modelo vacio.")
    if output.exists() and any(output.iterdir()):
        raise ValueError("La carpeta de salida debe estar vacia. No se reanuda una corrida incierta.")


def verify_and_export(base, model):
    point = model.xyz(model.BS, model.BO)
    pavement = base.state["pavimento"]["handle"]
    result = base.call("objects.invoke", {"handle": pavement, "metodo": "FindElevationAtXY",
                                        "args": point[:2]})["resultado"]
    depth = model.grade(model.BS) - .02 * model.BO - result
    if abs(depth - .0635) > 1e-7:
        raise RuntimeError("La profundidad releida del bache no coincide con el modelo.")
    report = {"centro": point[:2] + [result], "profundidad_m": depth,
              "instancias": len(base.state["instancias"]["creados"]),
              "nota": "Comprobado por API en el dibujo activo; no prueba de BeamNG."}
    (base.OUT / "VERIFICACION_MODELO.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    model.invoke(base.state["corredor"]["handle"], "Rebuild")
    for name, target, height in [
        ("CDX2_GENERAL", [17, 108, 103], 155),
        ("CDX2_CALLE_BACHE", model.xyz(model.BS, 0), 23),
    ]:
        base.call("vista.3d", {"direccion": [.8, -1, .65], "objetivo": target,
                             "alto": height, "ancho": height * 1.78,
                             "estilo_visual": "Shaded"}, True)
        base.call("vista.guardada", {"nombre": name}, True)
        base.call("vista.exportar", {"ruta": str(base.OUT / (name + ".png")),
                                   "dispositivo": "PublishToWeb PNG.pc3",
                                   "papel": "FHD_(1920.00_x_1080.00_Pixels)",
                                   "nombre_vista": name, "sombreado": "AsDisplayed",
                                   "rotacion": "0"}, True)
    base.call("vista.activar", {"nombre": "CDX2_GENERAL"}, True)
    base.call("doc.save", {"ruta": str(base.OUT / "CALLE_REALISTA_R02.dwg")}, True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Crear el ejemplo en CAD; por defecto solo muestra el plan.")
    drawing = parser.add_mutually_exclusive_group()
    drawing.add_argument("--template", type=Path, help="DWT metrico absoluto; crea un dibujo por doc.new conservando los anteriores.")
    drawing.add_argument("--drawing", help="Nombre/ruta exactos que devuelve doc.info; requiere dibujo vacio.")
    parser.add_argument("--output", type=Path, help="Directorio local nuevo, recomendado dentro de .local/escenas/.")
    args = parser.parse_args(argv)
    if not args.apply:
        print(json.dumps(PLAN, ensure_ascii=False, indent=2))
        return 0
    if not args.output or not (args.drawing or args.template):
        parser.error("--apply requiere --output y --drawing o --template.")
    import construir_base as base
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("La carpeta de salida debe estar vacia.")
    if args.template:
        if not args.template.is_absolute() or not args.template.is_file() or args.template.suffix.lower() != '.dwt':
            raise ValueError('Se requiere una plantilla DWT absoluta existente.')
        version = base.b.llamar('ping', {}).get('version', '')
        preflight('new', 'new', version, 0, args.output)
        created = base.b.llamar_con_aprobacion('doc.new', {'plantilla': str(args.template)})
        args.drawing = created['dibujo']
    info = base.b.llamar("doc.info", {})
    count = base.b.llamar("objects.query", {"limite": 1})["coincidencias"]
    preflight(args.drawing, info["dibujo"], info.get("puente_version"), count, args.output)
    if not info.get("civil3d") or info.get("insunits") != 6:
        raise ValueError("Requiere Civil 3D y unidades en metros; no cambia las unidades.")
    base.configure(args.output, info["dibujo"])
    (base.OUT / "PARAMETROS.json").write_text(json.dumps(PLAN, indent=2), encoding="utf-8")
    base.stage1()
    base.stage2()
    import modelar_escena as model
    model.finish()
    import acabados
    acabados.terrain_relief()
    import bloques_entorno
    bloques_entorno.definitions()
    bloques_entorno.place()
    acabados.markings()
    verify_and_export(base, model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
