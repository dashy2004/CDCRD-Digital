# FEA MCP - fix
# Interfaz Python <-> ETABS via COM (CSI OAPI v1).
#
# Correcciones respecto al original (GreatApo/FEA-MCP):
#   1. CoUninitialize ya no se ejecuta mientras hay punteros COM vivos.
#      Todo el trabajo COM se confina a un hilo dedicado (comthread.py).
#   2. self.versionString no existia -> AttributeError en cada ruta de error.
#      Reemplazado por self.version_string, inicializado siempre.
#   3. ctx.report_progress es corrutina: se invocaba sin await en
#      create_objects_by_coordinates. Ahora la herramienta es async.
#   4. La ruta de arranque automatico llamaba GetObject dos veces.
#      Ahora usa CreateObjectProgID / ApplicationStart correctamente.
#   5. Anotaciones de retorno inconsistentes (list[str] vs str) que rompen
#      la validacion de salida estructurada de MCP >= 1.10.
#   6. Mensajes de error que decian "LUSAS" dentro de la clase ETABS.
#   7. create_solid eliminado: SolidObj no existe en la OAPI de ETABS.
#   8. Validacion de la instancia cacheada en cada llamada.

import logging
import os
from typing import Any

import comtypes
import comtypes.client
from mcp.server.fastmcp import Context
from pydantic import BaseModel, Field

from comthread import com_call, run_in_com

logger = logging.getLogger('fea_mcp_server')

PROG_ID = "CSI.ETABS.API.ETABSObject"

PRESET_UNITS = [
    "lb, in, F", "lb, ft, F", "kip, in, F", "kip, ft, F",
    "kN, mm, C", "kN, m, C", "kgf, mm, C", "kgf, m, C",
    "N, mm, C", "N, m, C", "Ton, mm, C", "Ton, m, C",
    "kN, cm, C", "kgf, cm, C", "N, cm, C", "Ton, cm, C",
]


class GeomObject(BaseModel):
    """Punto / linea (frame) / superficie (area) definido por coordenadas."""
    type: str = Field(description='Tipo: "point", "line" o "surface".')
    xs: list[float] = Field(description="Coordenadas X.")
    ys: list[float] = Field(description="Coordenadas Y.")
    zs: list[float] = Field(description="Coordenadas Z.")
    id: str = Field(default="", description="ID del objeto (vacio si aun no existe).")


class EtabsError(RuntimeError):
    """Fallo de conexion u operacion en ETABS. FastMCP lo convierte en isError."""


class Etabs:
    def __init__(self, auto_start: bool = False, exe_path: str = ""):
        self.SapModel = None
        self._etabs_object = None
        self.auto_start = auto_start
        self.exe_path = exe_path
        self.version_string = "desconocida"
        # No se conecta en el constructor: el servidor debe poder arrancar
        # aunque ETABS todavia no este abierto. La conexion es perezosa.

    # ------------------------------------------------------------------
    # Conexion
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """Se ejecuta SIEMPRE dentro del hilo COM dedicado."""
        if self.SapModel is not None:
            # Validar que el puntero cacheado siga vivo.
            try:
                self.SapModel.GetModelFilename()
                return
            except Exception as e:
                logger.warning("Referencia a ETABS invalida (%s). Reconectando.", e)
                self.SapModel = None
                self._etabs_object = None

        etabs_object = None

        # Ruta 1: adjuntarse a una instancia ya abierta (la mas comun).
        try:
            etabs_object = comtypes.client.GetActiveObject(PROG_ID)
            logger.info("Adjuntado a instancia de ETABS en ejecucion.")
        except Exception as e:
            logger.info("GetActiveObject fallo (%s). Probando via cHelper.", e)

        # Ruta 2: cHelper (necesario en algunas instalaciones/versiones).
        if etabs_object is None:
            try:
                helper = comtypes.client.CreateObject('ETABSv1.Helper')
                try:
                    import comtypes.gen.ETABSv1 as ETABSv1
                    helper = helper.QueryInterface(ETABSv1.cHelper)
                except Exception as e:
                    logger.info("QueryInterface(cHelper) no disponible (%s); "
                                "usando late binding.", e)
                etabs_object = helper.GetObject(PROG_ID)
                logger.info("Adjuntado a ETABS via cHelper.")
            except Exception as e:
                logger.info("cHelper.GetObject fallo (%s).", e)
                etabs_object = None

        # Ruta 3: arrancar una instancia nueva (solo si esta habilitado).
        if etabs_object is None and self.auto_start:
            try:
                helper = comtypes.client.CreateObject('ETABSv1.Helper')
                try:
                    import comtypes.gen.ETABSv1 as ETABSv1
                    helper = helper.QueryInterface(ETABSv1.cHelper)
                except Exception:
                    pass
                if self.exe_path and os.path.isfile(self.exe_path):
                    etabs_object = helper.CreateObject(self.exe_path)
                else:
                    etabs_object = helper.CreateObjectProgID(PROG_ID)
                etabs_object.ApplicationStart()
                etabs_object.SapModel.InitializeNewModel(6)  # kN, m, C
                etabs_object.SapModel.File.NewBlank()
                logger.info("Instancia nueva de ETABS arrancada.")
            except Exception as e:
                logger.error("No se pudo arrancar ETABS: %s", e)
                etabs_object = None

        if etabs_object is None:
            raise EtabsError(
                "No hay conexion con ETABS. Verifique: (a) ETABS esta abierto "
                "con un modelo cargado, (b) Python y ETABS son ambos de 64 bits, "
                "(c) ETABS se ejecuta con el mismo nivel de privilegios que "
                "Claude Desktop. Ejecute diagnose_etabs.py para detalle."
            )

        self._etabs_object = etabs_object
        self.SapModel = etabs_object.SapModel

        try:
            self.version_string = str(etabs_object.GetOAPIVersionNumber())
        except Exception:
            self.version_string = "desconocida"
        logger.info("ETABS conectado. OAPI version: %s", self.version_string)

    def _model(self):
        self._connect()
        return self.SapModel

    # ------------------------------------------------------------------
    # Lectura
    # ------------------------------------------------------------------

    @com_call
    def get_model_info(self) -> str:
        """Devuelve archivo del modelo, version de ETABS y version de la OAPI."""
        model = self._model()
        try:
            filename = model.GetModelFilename()
        except Exception:
            filename = "(sin guardar)"
        try:
            version, _num, ret = model.GetVersion()
            version = version if ret == 0 else "desconocida"
        except Exception:
            version = "desconocida"
        return (f"Archivo: {filename}\n"
                f"Version ETABS: {version}\n"
                f"Version OAPI: {self.version_string}")

    @com_call
    def get_units(self) -> str:
        """Devuelve las unidades activas del modelo (fuerza, longitud, temperatura)."""
        model = self._model()
        my_units = model.GetPresentUnits()
        if my_units < 1 or my_units > len(PRESET_UNITS):
            return "Unidades desconocidas."
        return f"Unidades activas: {PRESET_UNITS[my_units - 1]}"

    @com_call
    def set_units(self, units: str) -> str:
        """Fija las unidades activas del modelo.

        Args:
            units: una de "lb, in, F", "kip, ft, F", "kN, m, C", "kgf, m, C",
                   "N, mm, C", "Ton, m, C", etc. (ver get_units).
        """
        model = self._model()
        target = units.strip().lower().replace(" ", "")
        for i, preset in enumerate(PRESET_UNITS, start=1):
            if preset.lower().replace(" ", "") == target:
                ret = model.SetPresentUnits(i)
                if ret != 0:
                    raise EtabsError(f"Error fijando unidades a {preset}.")
                return f"Unidades fijadas en {preset}."
        raise EtabsError(f"Unidades no reconocidas: {units}. "
                         f"Opciones: {', '.join(PRESET_UNITS)}")

    @com_call
    def save_model(self, path: str = "") -> str:
        """Guarda el modelo. Si se indica path, guarda como archivo nuevo (.EDB)."""
        model = self._model()
        ret = model.File.Save(path) if path else model.File.Save()
        if ret != 0:
            raise EtabsError("Error guardando el modelo.")
        return f"Modelo guardado{(' en ' + path) if path else ''}."

    @com_call
    def _read_points(self) -> list[GeomObject]:
        model = self._model()
        n, names, xs, ys, zs, _csys = model.PointObj.GetAllPoints()
        return [GeomObject(type="point", xs=[xs[i]], ys=[ys[i]], zs=[zs[i]], id=names[i])
                for i in range(n)]

    @com_call
    def _read_frames(self) -> list[GeomObject]:
        model = self._model()
        f = model.FrameObj.GetAllFrames()
        out = []
        for i in range(f[0]):
            out.append(GeomObject(
                type="line",
                xs=[f[6][i], f[9][i]],
                ys=[f[7][i], f[10][i]],
                zs=[f[8][i], f[11][i]],
                id=f[1][i],
            ))
        return out

    @com_call
    def _read_areas(self) -> list[GeomObject]:
        model = self._model()
        (n, names, _design, _n2, delim, _n3, xc, yc, zc, _n4) = model.AreaObj.GetAllAreas()
        out = []
        i = 0
        for count, j in enumerate(delim):
            out.append(GeomObject(
                type="surface",
                xs=list(xc[i:j + 1]),
                ys=list(yc[i:j + 1]),
                zs=list(zc[i:j + 1]),
                id=names[count],
            ))
            i = j + 1
        return out

    def get_points(self) -> list[GeomObject]:
        """Devuelve todos los puntos/joints del modelo."""
        return self._read_points()

    def get_frames(self) -> list[GeomObject]:
        """Devuelve todos los frames (vigas/columnas) del modelo."""
        return self._read_frames()

    def get_areas(self) -> list[GeomObject]:
        """Devuelve todas las areas (losas/muros) del modelo."""
        return self._read_areas()

    async def get_geometries(self, ctx: Context) -> list[GeomObject]:
        """Devuelve toda la geometria del modelo: puntos, frames y areas.

        Operacion lenta en modelos grandes; prefiera get_points/get_frames/get_areas
        si solo necesita una categoria.
        """
        geoms: list[GeomObject] = []
        await ctx.report_progress(0, 3)
        geoms.extend(self._read_points())
        await ctx.report_progress(1, 3)
        geoms.extend(self._read_frames())
        await ctx.report_progress(2, 3)
        geoms.extend(self._read_areas())
        await ctx.report_progress(3, 3)
        if not geoms:
            raise EtabsError("El modelo no contiene geometria.")
        return geoms

    # ------------------------------------------------------------------
    # Creacion
    # ------------------------------------------------------------------

    @com_call
    def _add_point(self, x: float, y: float, z: float) -> str:
        model = self._model()
        name, ret = model.PointObj.AddCartesian(x, y, z)
        if ret != 0:
            raise EtabsError(f"Error creando punto ({x}, {y}, {z}).")
        return name

    @com_call
    def _add_frame(self, xi: float, yi: float, zi: float,
                   xj: float, yj: float, zj: float, prop: str = "Default") -> str:
        model = self._model()
        name, ret = model.FrameObj.AddByCoord(xi, yi, zi, xj, yj, zj, "", prop)
        if ret != 0:
            raise EtabsError(
                f"Error creando frame ({xi},{yi},{zi})-({xj},{yj},{zj}) "
                f"con seccion '{prop}'."
            )
        return name

    @com_call
    def _add_area(self, xs: list[float], ys: list[float], zs: list[float],
                  prop: str = "Default") -> str:
        model = self._model()
        _x, _y, _z, name, ret = model.AreaObj.AddByCoord(
            len(xs), list(xs), list(ys), list(zs), "", prop)
        if ret != 0:
            raise EtabsError(f"Error creando area de {len(xs)} vertices "
                             f"con seccion '{prop}'.")
        return name

    @com_call
    def refresh_view(self) -> str:
        """Refresca la vista de ETABS para mostrar los objetos creados."""
        model = self._model()
        model.View.RefreshView(0, False)
        return "Vista refrescada."

    async def create_objects_by_coordinates(
        self,
        objects: list[GeomObject],
        ctx: Context,
    ) -> list[str]:
        """Crea en lote objetos geometricos en ETABS a partir de coordenadas.

        Acepta puntos, lineas (frames) y superficies (areas) en una sola llamada.
        La geometria de orden inferior se genera automaticamente; no hace falta
        crear los puntos de un frame por separado.

        Args:
            objects: lista de GeomObject. Cada uno con type = "point" | "line" |
                     "surface" y las listas xs, ys, zs correspondientes.

        Returns:
            Una linea de estado por objeto procesado.
        """
        results: list[str] = []
        total = len(objects)
        for i, obj in enumerate(objects):
            await ctx.report_progress(i, total)
            obj_type = (obj.type or "").strip().lower()
            try:
                if obj_type == "point":
                    name = self._add_point(obj.xs[0], obj.ys[0], obj.zs[0])
                    results.append(f"Punto {name} creado.")
                elif obj_type in ("line", "frame", "beam", "column"):
                    name = self._add_frame(obj.xs[0], obj.ys[0], obj.zs[0],
                                           obj.xs[1], obj.ys[1], obj.zs[1])
                    results.append(f"Frame {name} creado.")
                elif obj_type in ("surface", "area", "slab", "wall"):
                    name = self._add_area(obj.xs, obj.ys, obj.zs)
                    results.append(f"Area {name} creada.")
                else:
                    results.append(f"Error: tipo no soportado '{obj.type}'.")
            except IndexError:
                results.append(
                    f"Error: '{obj_type}' requiere mas coordenadas de las recibidas.")
            except Exception as e:
                results.append(f"Error procesando '{obj_type}': {e}")
        await ctx.report_progress(total, total)
        try:
            self.refresh_view()
        except Exception as e:
            logger.warning("RefreshView fallo: %s", e)
        return results


# Prueba manual: python Etabs.py  (con ETABS abierto y un modelo cargado)
if __name__ == "__main__":
    import sys
    m = Etabs()
    try:
        print(m.get_model_info())
        print(m.get_units())
        print("Puntos:", len(m.get_points()))
        print("Frames:", len(m.get_frames()))
        print("Areas: ", len(m.get_areas()))
    except Exception as exc:
        sys.exit(f"FALLO: {exc}")
