"""Native read-only scene snapshot; explicit document and layer scope."""


def registrar(mcp, llamar):
    @mcp.tool()
    def leer_escena_beamng(expected_document: str, terrain_handle: str,
                          road_handle: str, alignment_handle: str,
                          scene_layer_prefix: str, width_m: float = 7.2) -> str:
        """Lee TIN completas, eje y mallas de caras/solidos/bloques sin modificar CAD.

        Exige dibujo absoluto esperado y unidades CAD/Civil en metros. Devuelve
        geometria nativa y lista explicita de entidades no exportadas. No guarda,
        reconstruye ni simplifica superficies. El resultado puede ser grande.
        """
        return llamar('scene.snapshot', dict(expected_document=expected_document,
            terrain_handle=terrain_handle, road_handle=road_handle,
            alignment_handle=alignment_handle, scene_layer_prefix=scene_layer_prefix,
            width_m=width_m))
