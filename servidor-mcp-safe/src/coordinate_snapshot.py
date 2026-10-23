"""Read-only CSI points contract. Kept identical in the ETABS and SAFE adapters."""
import math
import ntpath
from datetime import datetime, timezone

LENGTH_UNITS = ("in", "ft", "in", "ft", "mm", "m", "mm", "m",
                "mm", "m", "mm", "m", "cm", "cm", "cm", "cm")


def capture_points(model, application, expected_path, frame_id, max_points=10000):
    """Run on the host adapter's COM thread. Never sets units or saves."""
    if application not in ("ETABS", "SAFE"):
        raise ValueError("Aplicacion no soportada")
    if not isinstance(frame_id, str) or not frame_id.strip():
        raise ValueError("Se requiere identificador del sistema Global del proyecto")
    if not isinstance(expected_path, str) or not ntpath.isabs(expected_path):
        raise ValueError("Se requiere ruta absoluta del modelo guardado esperado")
    if type(max_points) is not int or not 1 <= max_points <= 100000:
        raise ValueError("max_points fuera de 1-100000")
    path = model.GetModelFilename()
    if not path or ntpath.normcase(ntpath.normpath(path)) != ntpath.normcase(ntpath.normpath(expected_path)):
        raise ValueError("Modelo activo distinto del esperado")
    units = model.GetPresentUnits()
    if type(units) is not int or not 1 <= units <= len(LENGTH_UNITS):
        raise ValueError("Unidades CSI desconocidas")
    count = model.PointObj.Count()
    if type(count) is not int or count < 0 or count > max_points:
        raise ValueError("Conteo fuera de limite")
    points = []
    if count:
        raw = model.PointObj.GetAllPoints()
        if len(raw) != 6 or raw[-1] != 0:
            raise RuntimeError("GetAllPoints fallo o contrato distinto")
        n, names, xs, ys, zs, _ret = raw
        if n != count or any(len(a) != n for a in (names, xs, ys, zs)):
            raise RuntimeError("Arrays incompletos o modelo cambio durante lectura")
        if len(set(names)) != n or any(not isinstance(name, str) or not name for name in names):
            raise RuntimeError("IDs duplicados o vacios")
        for name, x, y, z in zip(names, xs, ys, zs):
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or
                   not math.isfinite(v) for v in (x, y, z)):
                raise RuntimeError("Coordenada no finita")
            points.append({"id": name, "xyz": [x, y, z]})
    if (model.GetModelFilename() != path or model.GetPresentUnits() != units
            or model.PointObj.Count() != count):
        raise RuntimeError("Modelo/unidades/conteo cambio durante lectura; descartar captura")
    return {"schema": "cdcrd.csi-points/1",
            "source": {"application": application, "model": path,
                       "captured_utc": datetime.now(timezone.utc).isoformat(),  # noqa: UP017 (Python 3.10)
                       "method": "PointObj.GetAllPoints", "units_enum": units},
            "frame": {"id": frame_id, "axes": "Global", "length_unit": LENGTH_UNITS[units-1]},
            "points": points, "model_writes": 0,
            "limits": ["Los joints no se clasifican automaticamente como cimentaciones.",
                       "Lectura con comprobacion de identidad/unidades/conteo; no bloqueo atomico."]}
