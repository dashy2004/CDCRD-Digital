"""Native smoke test in a NEW synthetic drawing; never closes existing documents."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import puente_cliente as bridge


def run(template, output):
    if output.exists() and any(output.iterdir()):
        raise ValueError("Carpeta de evidencia no vacia.")
    version = bridge.llamar("ping", {})["version"]
    if tuple(map(int, version.split("."))) < (0, 5, 19):
        raise ValueError("El puente cargado es anterior a 0.5.19. No se modifica ningun dibujo.")
    drawing = bridge.llamar_con_aprobacion("doc.new", {"plantilla": str(template.resolve())})["dibujo"]
    output.mkdir(parents=True, exist_ok=True)
    receipt = {"version": version, "dibujo": drawing, "checks": []}

    def write(method, params):
        if bridge.llamar("doc.info", {})["dibujo"] != drawing:
            raise RuntimeError("Cambio el dibujo activo: prueba detenida.")
        return bridge.llamar_con_aprobacion(method, params)

    # A valid first primitive followed by an invalid second primitive must roll back.
    try:
        write("blocks.create", {"nombre": "DEMO_ATOMIC", "entidades": [
            {"tipo": "caja", "esquina": [0, 0, 0], "dx": 1, "dy": 1, "dz": 1},
            {"tipo": "esfera", "centro": [0, 0, 4.1], "radio": -1},
        ]})
    except bridge.PuenteError as exc:
        if "radio" not in str(exc):
            raise
    else:
        raise AssertionError("La definicion invalida no fue rechazada.")
    block = write("blocks.create", {"nombre": "DEMO_ATOMIC", "entidades": [
        {"tipo": "esfera", "centro": [0, 0, 4.1], "radio": 1.8, "color": [60, 140, 80]}
    ]})
    assert block["cantidad"] == 1
    receipt["checks"].append("atomic rollback and reuse of failed definition name")
    refs = write("entity.create", {"entidades": [
        {"tipo": "bloque", "nombre": "DEMO_ATOMIC", "punto": [x, 0, 0]} for x in [0, 15, 30]
    ]})
    assert not refs["errores"] and len(refs["creados"]) == 3
    handle = refs["creados"][0]["handle"]
    low = bridge.llamar("objects.read", {"handle": handle, "ruta": "GeometricExtents.MinPoint"})["valor"]
    high = bridge.llamar("objects.read", {"handle": handle, "ruta": "GeometricExtents.MaxPoint"})["valor"]
    assert abs(low[2] - 2.3) < 1e-8 and abs(high[2] - 5.9) < 1e-8
    receipt["checks"].append("sphere preserves exact Z without object snaps")
    write("vista.3d", {"direccion": "PLANTA", "objetivo": [15, 0, 4.1],
                      "ancho": 42, "alto": 24, "estilo_visual": "Shaded"})
    write("vista.guardada", {"nombre": "DEMO_QA"})
    for rotation in ["0", "90"]:
        result = write("vista.exportar", {"ruta": str(output / ("rotation_" + rotation + ".png")),
                        "dispositivo": "PublishToWeb PNG.pc3", "papel": "FHD_(1920.00_x_1080.00_Pixels)",
                        "nombre_vista": "DEMO_QA", "sombreado": "AsDisplayed", "rotacion": rotation})
        assert result["rotacion_solicitada"] == int(rotation) and result["bytes"] > 0
    receipt["checks"].append("PNG export completed at 0 and 90 degrees; inspect both images")
    write("doc.save", {"ruta": str(output / "DEMO_SCENE_API.dwg")})
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.template, args.output.resolve()), indent=2))
