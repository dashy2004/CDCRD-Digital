"""Generate and record the native street in separate, reproducible OBS takes."""
import argparse
import json
import math
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / "tools" / "tech"))
import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--template", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--obs-config", type=Path)
    parser.add_argument("--obs-directory", type=Path)
    parser.add_argument("--obs-session")
    args = parser.parse_args()
    if not args.apply:
        print(json.dumps({"modelo": run.PLAN, "tomas": [
            "eje", "terreno-rasante-corredor", "bache-aceras-relieve", "bloques",
            "marcas", "general", "planta", "bache", "entorno", "orbita",
            "bache-detalle", "relieve-lateral"]}, indent=2))
        return
    if not all([args.template, args.output, args.obs_config, args.obs_directory, args.obs_session]):
        parser.error("--apply requiere plantilla, output y los tres parametros OBS.")
    if not args.template.is_absolute() or not args.template.is_file() or args.template.suffix.lower() != ".dwt":
        raise ValueError("Se requiere una plantilla metrica DWT absoluta existente.")
    import construir_base as base
    from capturas_obs import CaptureSession
    run.preflight("new", "new", base.b.llamar("ping", {})["version"], 0, args.output)
    capture = CaptureSession(args.obs_config, args.obs_directory, args.obs_session)
    try:
        # The operator first prepares and checks this isolated OBS session.
        if not capture.state or not capture.state.get("recordings"):
            raise RuntimeError("Primero validar una toma corta con este perfil OBS.")
        capture.guard()
        capture.idle()
        created = base.b.llamar_con_aprobacion("doc.new", {"plantilla": str(args.template)})
        info = base.b.llamar("doc.info", {})
        count = base.b.llamar("objects.query", {"limite": 1})["coincidencias"]
        run.preflight(created["dibujo"], info["dibujo"], info["puente_version"], count, args.output)
        if not info.get("civil3d") or info.get("insunits") != 6:
            raise ValueError("Se requiere Civil 3D con unidades en metros.")
        base.configure(args.output, info["dibujo"])
        (base.OUT / "PARAMETROS.json").write_text(json.dumps(run.PLAN, indent=2), encoding="utf-8")
        capture.target("[" + Path(info["dibujo"]).name + "]")

        def view(direction, target, height):
            base.call("vista.3d", {"direccion": direction, "objetivo": target,
                "alto": height, "ancho": height * 1.78, "estilo_visual": "Shaded"}, True)

        def take(label, action, after=None):
            print("TAKE", label, flush=True)
            with capture.recording(label):
                time.sleep(2)
                action()
                if after:
                    after()
                time.sleep(5)

        view([0, 0, 1], [16, 105, 0], 250)
        take("01_generacion_eje", base.stage1)
        view([.8, -1, .8], [16, 105, 102], 210)
        take("02_generacion_corredor", base.stage2,
             lambda: view([.8, -1, .8], [16, 105, 102], 210))
        import modelar_escena as model
        import acabados
        import bloques_entorno
        take("03_bache_aceras_relieve", lambda: (model.finish(), acabados.terrain_relief()))
        take("04_bloques_3d", lambda: (bloques_entorno.definitions(), bloques_entorno.place()))
        take("05_marcas_viales", acabados.markings)
        run.verify_and_export(base, model)
        shots = [
            ("06_general", [.8, -1, .65], [17, 108, 103], 155),
            ("07_planta", [0, 0, 1], [16, 105, 102], 235),
            ("08_bache", [.8, -1, .65], model.xyz(model.BS, 0), 16),
            ("09_entorno", [-1, -.7, .55], model.xyz(155, 0), 55),
            ("11_bache_detalle", [.4, -1, .5], model.xyz(model.BS, model.BO, -.0635 - .02 * model.BO), 4),
            ("12_relieve_lateral", [-1, -.2, .25], [10, 135, 103], 75),
        ]
        for label, direction, target, height in shots:
            view(direction, target, height)
            base.call("vista.guardada", {"nombre": "CDX_TOMA_" + label}, True)
            take(label, lambda: None)
            capture.snapshot(label)
        view([.8, -1, .65], [17, 108, 103], 155)
        def orbit():
            # Deliberate API steps, not a claim of a smooth cinematic camera.
            for angle in range(-50, 131, 10):
                radians = math.radians(angle)
                view([math.cos(radians), math.sin(radians), .65], [17, 108, 103], 155)
                time.sleep(.3)
        take("10_orbita_inspeccion", orbit)
        view([.8, -1, .65], [17, 108, 103], 155)
        base.call("doc.save", {"ruta": str(base.OUT / "CALLE_REALISTA_R02.dwg")}, True)
        (base.OUT / "CAPTURAS.json").write_text(json.dumps({
            "drawing": info["dibujo"], "obs_receipt": str(capture.state_path),
            "phase": "completed", "visual_review": "pending"}, indent=2), encoding="utf-8")
    finally:
        capture.close()


if __name__ == "__main__":
    main()
