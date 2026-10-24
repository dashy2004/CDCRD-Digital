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
    def crear_ensamblaje_calzada(nombre: str, origen: str, ancho_izq: float, ancho_der: float,
                                pendiente_izq: float, pendiente_der: float, espesores: str,
                                talud_corte: float, talud_relleno: float, ancho_daylight_max: float,
                                capa: str = "", simular: bool = False, confirmar: bool = False) -> str:
        """Calzada nativa: LaneSuperelevationAOR con 4 capas + DaylightMaxWidth por lado.

        espesores = [pave1, pave2, base, subbase] en m (0.01-2 c/u, suma <= 5).
        Taludes 0.1-10; su interpretacion la reporta el tipo releido (Slope/Grade).
        ancho_daylight_max 1-200 m limita el enlace de daylight. El daylight se
        engancha al punto exterior mas bajo del carril. Sin peraltes ni targets
        (eso lo hace crear_corredor_calzada). Nombre nuevo. simular ejecuta y revierte.
        """
        try:
            xyz, depths = numeros(origen, 3), numeros(espesores, 4)
        except (ValueError, TypeError, OverflowError) as exc:
            return ok({"error": str(exc)})
        return run("civil.ensamblaje_calzada", dict(nombre=nombre, origen=xyz, ancho_izq=ancho_izq,
                   ancho_der=ancho_der, pendiente_izq=pendiente_izq, pendiente_der=pendiente_der,
                   espesores=depths, talud_corte=talud_corte, talud_relleno=talud_relleno,
                   ancho_daylight_max=ancho_daylight_max, capa=capa, simular=simular), confirmar)

    @mcp.tool()
    def crear_ensamblaje_cunetas_bermas(
        nombre: str, origen: str, ancho_izq: float, ancho_der: float,
        pendiente_izq: float, pendiente_der: float, espesores: str,
        ancho_berma_izq: float, ancho_berma_der: float,
        pendiente_berma_izq: float, pendiente_berma_der: float,
        profundidad_cuneta: float, ancho_fondo_cuneta: float,
        talud_cuneta_interior_hv: float, talud_cuneta_exterior_hv: float,
        talud_corte: float, talud_relleno: float, ancho_daylight_max: float,
        capa: str = "", simular: bool = False, confirmar: bool = False,
    ) -> str:
        """Carriles con cuatro capas, bermas sin capas y cunetas trapezoidales nativas.

        Geometria explicita a AMBOS lados, tanto en corte como en relleno.
        Metros; pendientes de carril/berma m/m hacia afuera; taludes de cuneta
        H/V positivos. Daylight usa dz/dx positivo y parte del borde exterior
        de la cuneta. Fondo horizontal transversal; sin revestimiento, calculo
        hidraulico, peraltes ni seleccion automatica corte/relleno de cuneta.
        Usar crear_corredor_calzada para targets TIN. simular crea y revierte.
        """
        params = dict(nombre=nombre, ancho_izq=ancho_izq, ancho_der=ancho_der,
                      pendiente_izq=pendiente_izq, pendiente_der=pendiente_der,
                      ancho_berma_izq=ancho_berma_izq, ancho_berma_der=ancho_berma_der,
                      pendiente_berma_izq=pendiente_berma_izq, pendiente_berma_der=pendiente_berma_der,
                      profundidad_cuneta=profundidad_cuneta, ancho_fondo_cuneta=ancho_fondo_cuneta,
                      talud_cuneta_interior_hv=talud_cuneta_interior_hv,
                      talud_cuneta_exterior_hv=talud_cuneta_exterior_hv,
                      talud_corte=talud_corte, talud_relleno=talud_relleno,
                      ancho_daylight_max=ancho_daylight_max, capa=capa, simular=simular)
        try:
            params["origen"] = numeros(origen, 3)
            params["espesores"] = numeros(espesores, 4)
        except (ValueError, TypeError, OverflowError) as exc:
            return ok({"error": str(exc)})
        return run("civil.ensamblaje_cunetas_bermas", params, confirmar)

    @mcp.tool()
    def crear_corredor_calzada(alineamiento: str, perfil: str, ensamblaje: str, nombre: str,
                              superficie_objetivo: str, inicio: float, fin: float, frecuencia: float,
                              estaciones_extra: str = "[]", capa: str = "", simular: bool = False,
                              confirmar: bool = False) -> str:
        """Corredor con targets: todo target de superficie apunta a la TIN indicada.

        Mismo contrato de region que crear_corredor. Exige codigos Top y Daylight,
        daylight a ambos lados en cada estacion y |z_daylight - z_TIN| <= 1e-6;
        superficie Top con contorno por codigo Daylight. Devuelve los puntos
        aplicados con sus codigos. simular ejecuta y revierte.
        """
        try:
            stations = numeros(estaciones_extra)
        except (ValueError, TypeError, OverflowError) as exc:
            return ok({"error": str(exc)})
        return run("civil.corredor_calzada", dict(alineamiento=alineamiento, perfil=perfil,
                   ensamblaje=ensamblaje, nombre=nombre, superficie_objetivo=superficie_objetivo,
                   inicio=inicio, fin=fin, frecuencia=frecuencia, estaciones_extra=stations,
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
