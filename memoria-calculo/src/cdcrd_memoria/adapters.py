"""Offline adapters for existing captures. Never import COM or launch native applications."""

from .contracts import Dossier


def import_etabs_capture(capture: dict, dossier: Dossier, source_id: str) -> Dossier:
    """Map explicit capture fields; do not turn model inventory into analysis results."""
    if capture.get("schema") != "cdcrd-etabs-capture/1":
        raise ValueError("Captura ETABS no compatible; se requiere cdcrd-etabs-capture/1")
    if source_id not in {s.id for s in dossier.sources}:
        raise ValueError("La captura debe estar registrada como fuente con SHA-256")
    snapshot = capture.get("snapshot")
    if not isinstance(snapshot, dict):
        raise ValueError("Captura sin snapshot")  # noqa: TRY004 -- stable intake error API
    observations = []

    def add(suffix, topic, label, value, unit, locator):
        observations.append(
            {
                "id": f"ETABS-{source_id}-{suffix}",
                "topic": topic,
                "label": label,
                "value": value,
                "unit": unit,
                "acquisition": "imported" if value is not None else "unavailable",
                "validation": "pending",
                "source_id": source_id,
                "locator": locator,
                "reason": "Dato importado, pendiente de cotejo técnico"
                if value is not None
                else "Campo no disponible",
            }
        )

    if len(source_id) > 40:
        raise ValueError("El ID de la fuente ETABS debe tener 40 caracteres o menos")
    for key, topic, label in [
        ("stories", "geometry", "Niveles capturados"),
        ("joints", "geometry", "Nudos capturados"),
        ("frames", "geometry", "Barras capturadas"),
        ("slabs", "geometry", "Losas capturadas"),
        ("walls", "geometry", "Muros capturados"),
        ("patterns", "loads", "Patrones capturados"),
    ]:
        value = snapshot.get(key)
        if value is not None and (not isinstance(value, list) or not all(isinstance(v, dict) for v in value)):
            raise ValueError(f"snapshot.{key} debe ser una lista de objetos")
        add(key, topic, label, len(value) if value is not None else None, "1", f"snapshot.{key}")
    add(
        "units",
        "geometry",
        "Unidades declaradas por la captura",
        snapshot.get("units"),
        "texto",
        "snapshot.units",
    )
    for index, story in enumerate(snapshot.get("stories") or []):
        for key in ("height_m", "elevation_m"):
            value = story.get(key)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int))):
                raise ValueError(f"{key} no es numérico")
            add(
                f"story-{index}-{key}",
                "geometry",
                f"Nivel {story.get('name', index)}: {key}",
                value,
                "m",
                f"snapshot.stories[{index}].{key}",
            )
    data = dossier.model_dump(by_alias=True)
    data["observations"].extend(observations)
    return Dossier.model_validate(data)
