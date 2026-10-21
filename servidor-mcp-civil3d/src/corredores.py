"""Explicit SI assemblies, one-region corridors and native curved-axis sections."""
import json
import math


def numeros(value, count=None):
    rows = json.loads(value) if isinstance(value, str) else value
    if not isinstance(rows, list) or len(rows) > 500 or (count is not None and len(rows) != count):
        raise ValueError("lista de numeros invalida")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in rows):
        raise ValueError("numeros finitos requeridos")
    return rows


def registrar(mcp, llamar, ok):
    def run(method, params, confirmar):
        if not confirmar:
            return ok({"error": "operacion de escritura: repita con confirmar=True", **params})
        return llamar(method, {k: v for k, v in params.items() if v != ""}, escribe=True)

    @mcp.tool()
    def crear_ensamblaje_enlaces(nombre: str, origen: str, ancho_izq: float, ancho_der: float,
                                pendiente_izq: float, pendiente_der: float, capa: str = "",
                                simular: bool = False, confirmar: bool = False) -> str:
        """Dos LinkWidthAndSlope nativos: XYZ y anchos en m, pendientes m/m.

        Anchos 0.01-50 m, pendientes -1..1, sin peraltes ni targets. Nombre nuevo.
        No representa pavimento ni daylight. simular ejecuta y revierte.
        """
        try:
            xyz = numeros(origen, 3)
        except (ValueError, TypeError, OverflowError) as exc:
            return ok({"error": str(exc)})
        return run("civil.ensamblaje_enlaces", dict(nombre=nombre, origen=xyz, ancho_izq=ancho_izq,
                   ancho_der=ancho_der, pendiente_izq=pendiente_izq, pendiente_der=pendiente_der,
                   capa=capa, simular=simular), confirmar)

    @mcp.tool()
    def crear_corredor(alineamiento: str, perfil: str, ensamblaje: str, nombre: str,
                      inicio: float, fin: float, frecuencia: float, estaciones_extra: str = "[]",
                      capa: str = "", simular: bool = False, confirmar: bool = False) -> str:
        """Corredor nuevo: una baseline/region, frecuencia explicita y superficie Top.

        Metros, perfil del eje indicado, sin referencias ni ecuaciones de estacion.
        Maximo 1000 intervalos, 500 estaciones extra ordenadas. Reconstruye y relee.
        No asigna targets ni dimensiona una carretera. simular ejecuta y revierte.
        """
        try:
            stations = numeros(estaciones_extra)
        except (ValueError, TypeError, OverflowError) as exc:
            return ok({"error": str(exc)})
        return run("civil.corredor", dict(alineamiento=alineamiento, perfil=perfil,
                   ensamblaje=ensamblaje, nombre=nombre, inicio=inicio, fin=fin, frecuencia=frecuencia,
                   estaciones_extra=stations, capa=capa, simular=simular), confirmar)

    @mcp.tool()
    def crear_secciones_corredor(corredor: str, nombre: str, estaciones: str, semiancho: float,
                                origen: str, cota_min: float, cota_max: float, capa: str = "",
                                simular: bool = False, confirmar: bool = False) -> str:
        """Muestrea superficie Top del corredor y crea vistas H=V con estilos propios.

        Estaciones deben existir entre los ensamblajes aplicados. Posiciones se
        calculan con estacion/offset del eje curvo. Unidades m. Maximo 500 vistas.
        Requiere una baseline, region y superficie. simular ejecuta y revierte.
        """
        try:
            stations, xyz = numeros(estaciones), numeros(origen, 3)
        except (ValueError, TypeError, OverflowError) as exc:
            return ok({"error": str(exc)})
        return run("civil.secciones_corredor", dict(corredor=corredor, nombre=nombre,
                   estaciones=stations, semiancho=semiancho, origen=xyz, cota_min=cota_min,
                   cota_max=cota_max, capa=capa, simular=simular), confirmar)
