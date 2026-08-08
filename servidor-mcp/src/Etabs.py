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
import re
import shutil
import threading
from typing import Any

import comtypes
import comtypes.client
from mcp.server.fastmcp import Context
from pydantic import BaseModel, Field

from comthread import com_call, run_in_com
import oapi

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


def _descartar_modales_etabs(stop_event: threading.Event) -> None:
    """Descarta dialogos modales (#32770) de ETABS durante un import de texto.

    File.OpenFile sobre un .e2k/.$et puede levantar un modal ("System memory
    error in dimensioning Array AnalysisModelInfo") que bloquea el hilo COM
    para siempre (auditoria 7.6). Reproducido y verificado el 2026-08-07:
    descartado el modal, el import termina bien (ret=0, modelo correcto).
    Solo toca dialogos cuyo texto coincide con frases del importador; el
    boton se presiona con WM_COMMAND y el ID real del control (BM_CLICK
    posteado cross-thread no funciona; verificado). Cada descarte queda en
    el log.
    """
    import ctypes
    from ctypes import wintypes

    u32 = ctypes.windll.user32
    FRASES = ("error in dimensioning", "importing text file", "import log")
    ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    u32.EnumWindows.argtypes = (ENUM, wintypes.LPARAM)
    u32.EnumChildWindows.argtypes = (wintypes.HWND, ENUM, wintypes.LPARAM)
    u32.GetClassNameW.argtypes = (wintypes.HWND, ctypes.c_wchar_p, ctypes.c_int)
    u32.IsWindowVisible.argtypes = (wintypes.HWND,)
    u32.GetDlgCtrlID.argtypes = (wintypes.HWND,)
    u32.PostMessageW.argtypes = (wintypes.HWND, ctypes.c_uint,
                                 wintypes.WPARAM, wintypes.LPARAM)
    u32.SendMessageTimeoutW.argtypes = (wintypes.HWND, ctypes.c_uint,
                                        wintypes.WPARAM, ctypes.c_wchar_p,
                                        ctypes.c_uint, ctypes.c_uint,
                                        ctypes.POINTER(ctypes.c_size_t))

    def txt(h: int) -> str:
        buf = ctypes.create_unicode_buffer(1024)
        res = ctypes.c_size_t(0)
        # WM_GETTEXT via SendMessageTimeout: GetWindowText no lee controles
        # de otro proceso. SMTO_ABORTIFHUNG=2, 300 ms.
        u32.SendMessageTimeoutW(h, 0x000D, 1024, buf, 2, 300,
                                ctypes.byref(res))
        return buf.value

    while not stop_event.wait(1.0):
        tops: list[int] = []

        def _top(h, _l):
            cls = ctypes.create_unicode_buffer(64)
            u32.GetClassNameW(h, cls, 64)
            if cls.value == "#32770" and u32.IsWindowVisible(h):
                tops.append(h)
            return True

        u32.EnumWindows(ENUM(_top), 0)
        for dlg in tops:
            hijos: list[int] = []

            def _kid(h, _l):
                hijos.append(h)
                return True

            u32.EnumChildWindows(dlg, ENUM(_kid), 0)
            textos = " | ".join(txt(h) for h in hijos).lower()
            if not any(f in textos for f in FRASES):
                continue
            boton = next(
                (h for h in hijos if txt(h).strip().lstrip("&").upper()
                 in ("OK", "ACEPTAR", "YES", "CLOSE", "CERRAR")), None)
            if boton is not None:
                u32.PostMessageW(dlg, 0x0111,
                                 u32.GetDlgCtrlID(boton) & 0xFFFF, boton)
                logger.warning("Modal de ETABS descartado durante import: "
                               "%.200s", textos)


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
                # GetObject en late binding puede devolver None sin lanzar
                # excepcion. Sin este chequeo, el log anterior afirmaba un
                # "Adjuntado" que no habia ocurrido (ver ERRORES-IA E-017:
                # se detecto porque nunca aparecia el log de cierre
                # "ETABS conectado. OAPI version:" mas abajo).
                if etabs_object is not None:
                    logger.info("Adjuntado a ETABS via cHelper.")
                else:
                    logger.info("cHelper.GetObject devolvio None (sin instancia).")
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
        """Guarda el modelo. Si se indica path, guarda como archivo nuevo (.EDB).

        Crea el directorio destino si no existe: File.Save falla con un error
        opaco cuando la carpeta falta.
        """
        model = self._model()
        if path:
            parent = os.path.dirname(path)
            if parent and not os.path.isdir(parent):
                try:
                    os.makedirs(parent, exist_ok=True)
                    logger.info("Directorio creado: %s", parent)
                except OSError as e:
                    raise EtabsError(
                        f"No se pudo crear el directorio '{parent}': {e}")
        ret = model.File.Save(path) if path else model.File.Save()
        if ret != 0:
            raise EtabsError(
                "Error guardando el modelo."
                + (" Verifique permisos de escritura en la ruta." if path
                   else " El modelo nuevo requiere path la primera vez."))
        return f"Modelo guardado{(' en ' + path) if path else ''}."

    # ------------------------------------------------------------------
    # Conversion de unidades
    # ------------------------------------------------------------------

    _FORCE_TO_N = {"lb": 4.4482216, "kip": 4448.2216, "kN": 1000.0,
                   "kgf": 9.80665, "N": 1.0, "Ton": 9806.65}
    _LENGTH_TO_MM = {"in": 25.4, "ft": 304.8, "mm": 1.0, "m": 1000.0, "cm": 10.0}

    @com_call
    def _stress_to_mpa(self) -> float:
        """Factor que convierte esfuerzos de las unidades activas a MPa.

        Sustituye la heuristica por magnitud (fragil: f'c=280 kgf/cm2 y
        f'c=4000 psi la rompian). Lee las unidades reales del modelo.
        """
        # @com_call es latente aca: hoy solo se invoca desde metodos ya
        # decorados (la guarda de reentrada de comthread lo hace inocuo),
        # pero sin el decorador cualquier llamador futuro no decorado
        # tocaria COM desde el hilo equivocado.
        model = self._model()
        idx = model.GetPresentUnits()
        if not (1 <= idx <= len(PRESET_UNITS)):
            raise EtabsError("No se pudieron determinar las unidades activas.")
        force, length, _temp = [s.strip() for s in PRESET_UNITS[idx - 1].split(",")]
        return self._FORCE_TO_N[force] / (self._LENGTH_TO_MM[length] ** 2)

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
        (n, names, _design, _npts_total, delim, _pnames,
         xc, yc, zc, _ret) = model.AreaObj.GetAllAreas()
        # Se indexa por PointDelimiter, que es el indice 0-based del ULTIMO
        # vertice de cada area. La auditoria 2026-08-07 (seccion 7.3) propuso
        # indexar por NumberBoundaryPts suponiendolo un conteo por area; el
        # typelib de esta instalacion lo desmiente:
        #   GetAllAreas(..., [in,out] NumberBoundaryPts: long*, ...)
        # es un ESCALAR (total de vertices de todas las areas), no un array,
        # asi que npts[k] habria reventado. Verificado con describe_oapi
        # corregido, dispid 82. El indexado por delim es el correcto y
        # coincide con el runtime: 12 areas x 4 vertices, cotas homogeneas.
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

    # ------------------------------------------------------------------
    # Edicion: borrar, mover, liberar extremos
    # ------------------------------------------------------------------

    _OBJ_NAMESPACE = {"point": "PointObj", "line": "FrameObj", "frame": "FrameObj",
                      "beam": "FrameObj", "column": "FrameObj",
                      "area": "AreaObj", "surface": "AreaObj",
                      "slab": "AreaObj", "wall": "AreaObj"}

    @com_call
    def delete_object(self, obj_type: str, name: str) -> str:
        """Borra un objeto por tipo y nombre/ID (los que devuelve get_points/get_frames/get_areas).

        Args:
            obj_type: "point", "frame" (o "line"/"beam"/"column"), "area"
                      (o "surface"/"slab"/"wall").
            name: ID del objeto, ej. "14" o "Frame 14" segun lo reportado.
        """
        key = obj_type.strip().lower()
        ns = self._OBJ_NAMESPACE.get(key)
        if ns is None:
            raise EtabsError(
                f"Tipo no reconocido: '{obj_type}'. "
                f"Use point, frame o area.")
        model = self._model()
        owner = getattr(model, ns)
        oapi.call(owner, [("Delete", (name, 0)), ("Delete", (name,))],
                  f"borrado de {ns} '{name}'")
        return f"{ns} '{name}' borrado."

    @com_call
    def move_objects(self, obj_type: str, names: list[str],
                     dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> str:
        """Desplaza objetos existentes (traslacion rigida).

        Selecciona los objetos indicados y aplica EditGeneral.Move. Deselecciona
        todo lo demas primero para no arrastrar objetos ajenos por una
        seleccion previa que haya quedado activa en la interfaz.

        Args:
            obj_type: "point", "frame" o "area".
            names: IDs de los objetos a mover.
            dx, dy, dz: desplazamiento en cada eje, unidades activas.
        """
        key = obj_type.strip().lower()
        ns = self._OBJ_NAMESPACE.get(key)
        if ns is None:
            raise EtabsError(f"Tipo no reconocido: '{obj_type}'.")
        if not names:
            raise EtabsError("Debe indicar al menos un nombre.")
        model = self._model()

        oapi.call(model.SelectObj, [("ClearSelection", ())],
                  "limpieza de seleccion previa")
        owner = getattr(model, ns)
        for name in names:
            oapi.call(owner, [("SetSelected", (name, True)),
                              ("SetSelected", (name, True, 0))],
                      f"seleccion de {ns} '{name}'")
        oapi.call(model.EditGeneral, [("Move", (float(dx), float(dy), float(dz)))],
                  "desplazamiento de objetos seleccionados")
        oapi.call(model.SelectObj, [("ClearSelection", ())],
                  "limpieza de seleccion posterior")
        return f"{len(names)} {ns}(s) desplazado(s): dx={dx:g}, dy={dy:g}, dz={dz:g}."

    @com_call
    def set_frame_releases(self, frame_id: str,
                           start: list[str] | None = None,
                           end: list[str] | None = None) -> str:
        """Libera grados de libertad en los extremos de un frame (rotula, etc.).

        Args:
            frame_id: ID del frame (de get_frames).
            start: grados a liberar en el extremo I, subconjunto de
                   ["P","V2","V3","T","M2","M3"]. None o [] = sin liberar.
            end: idem para el extremo J. Ejemplo tipico de rotula en el
                 extremo J de una viga: end=["M3"].
        """
        order = ["P", "V2", "V3", "T", "M2", "M3"]
        start = start or []
        end = end or []
        bad = [d for d in start + end if d not in order]
        if bad:
            raise EtabsError(f"Grado(s) no reconocido(s): {bad}. Use {order}.")

        ii = [d in start for d in order]
        jj = [d in end for d in order]
        zeros = [0.0] * 6
        model = self._model()
        oapi.call(
            model.FrameObj,
            [("SetReleases", (frame_id, ii, jj, zeros, zeros)),
             ("SetReleases", (frame_id, ii, jj, zeros, zeros, 0))],
            f"liberaciones en el frame {frame_id}",
        )
        desc = (f"inicio: {start or 'ninguna'}; fin: {end or 'ninguna'}")
        return f"Liberaciones del frame {frame_id} fijadas ({desc})."

    # ------------------------------------------------------------------
    # Introspeccion de la OAPI
    # ------------------------------------------------------------------

    @com_call
    def describe_oapi(self, path: str = "", filter: str = "") -> str:
        """Muestra los metodos reales de la OAPI de ESTA instalacion de ETABS.

        Las firmas de la OAPI cambian entre versiones. Antes de asumir como se
        llama un metodo, consultelo aqui.

        Args:
            path: namespace bajo SapModel, ej. "Story", "PropFrame",
                  "LoadPatterns", "Results.Setup". Vacio = el propio SapModel.
            filter: subcadena para filtrar por nombre, ej. "Story", "Grid".
        """
        model = self._model()
        target = oapi.resolve_path(model, path) if path else model
        label = f"SapModel.{path}" if path else "SapModel"
        return f"--- {label} ---\n" + oapi.describe(target, filter)

    # ------------------------------------------------------------------
    # Story data (niveles)
    # ------------------------------------------------------------------

    @com_call
    def get_stories(self) -> str:
        """Devuelve los niveles (stories) definidos en el modelo.

        Tolera las distintas firmas de GetStories / GetStories_2: localiza la
        lista de nombres por forma en vez de suponer su posicion, porque
        GetStories_2 antepone BaseElevation y GetStories no.
        """
        model = self._model()
        result = oapi.call(
            model.Story,
            [("GetStories_2", ()), ("GetStories", ())],
            "lectura de niveles",
        )
        names = oapi.find_str_list(result)
        if not names:
            return "El modelo no tiene niveles definidos."
        numeric = oapi.find_num_lists(result, len(names))
        lines = []
        for i, name in enumerate(names):
            parts = [f"{name}"]
            if len(numeric) >= 1:
                parts.append(f"elevacion {numeric[0][i]:g}")
            if len(numeric) >= 2:
                parts.append(f"altura {numeric[1][i]:g}")
            lines.append(": ".join([parts[0], ", ".join(parts[1:])])
                         if len(parts) > 1 else parts[0])
        return f"{len(names)} nivel(es):\n" + "\n".join(lines)

    @com_call
    def set_stories(
        self,
        story_names: list[str],
        story_heights: list[float],
        base_elevation: float = 0.0,
    ) -> str:
        """Define los niveles del modelo (reemplaza los existentes).

        Args:
            story_names: nombres de abajo hacia arriba, ej.
                         ["Nivel 1", "Nivel 2", "Nivel 3"].
            story_heights: altura de cada nivel, misma longitud y orden,
                           ej. [3, 3, 3].
            base_elevation: elevacion de la base, normalmente 0.
        """
        if len(story_names) != len(story_heights):
            raise EtabsError(
                f"story_names ({len(story_names)}) y story_heights "
                f"({len(story_heights)}) deben tener la misma longitud.")
        if not story_names:
            raise EtabsError("Debe indicar al menos un nivel.")

        model = self._model()
        n = len(story_names)
        names = list(story_names)
        heights = [float(h) for h in story_heights]

        if self._count_objects() > 0:
            # SetStories_2 esta documentado "can only be used when no
            # objects exist in the model" (CHM oficial v23) y la tabla
            # Story Definitions es ImportType=1 (importable pero NO editable
            # interactivamente), asi que en un modelo poblado ninguna de las
            # rutas directas puede funcionar. Via verificada el 2026-08-07:
            # round-trip del texto del modelo ($et/e2k).
            return self._set_stories_via_texto(names, heights,
                                               float(base_elevation))

        # Todos master, ninguno similar: la configuracion que ETABS nunca
        # puede rechazar (es la que genera al no declarar plantas repetidas).
        # Dos configuraciones anteriores fallaron con ret=1 silencioso:
        # todos False sin SimilarTo (invalida), y master arriba con los demas
        # apuntandole -- convencion legal pero no default seguro. La variante
        # master-arriba queda como respaldo por si esta instalacion la exige.
        is_master_all = [True] * n
        similar_none = [""] * n
        is_master_top = [False] * (n - 1) + [True]
        similar_top = [names[-1]] * (n - 1) + [""]
        splice_above = [False] * n
        splice_height = [0.0] * n
        color = [0] * n

        # Elevaciones para el SetStories legado. El CHM exige longitud n+1
        # con la elevacion de la Base COMO PRIMER ELEMENTO ("This array has
        # length (Number of stories + 1). The first value in the array is
        # the 'Base' elevation"). La version anterior pasaba solo los n
        # topes, asi que el "no-op" de R02 nunca fue valido para ESTA
        # variante (la conclusion del bloque sobrevive por SetStories_2,
        # que no lleva elevaciones y tambien rechazo).
        elevations: list[float] = [float(base_elevation)]
        acc = float(base_elevation)
        for h in heights:
            acc += h
            elevations.append(acc)

        # Firma de SetStories en ETABS 23.3.0 / OAPI 2.016 -- siete arrays,
        # sin conteo lider, ELEVACIONES ANTES QUE ALTURAS:
        #
        #   SetStories(StoryNames[], StoryElevations[], StoryHeights[],
        #              IsMasterStory[], SimilarToStory[], SpliceAbove[],
        #              SpliceHeight[])
        #
        # Evidencia, cada pieza de una corrida distinta:
        #   - (n,) + 6 arrays -> "argument 1: object of type 'int' has no
        #     len()": el primer parametro es un SAFEARRAY, no el conteo.
        #   - 6 arrays -> "required argument 'SpliceHeight' missing": son
        #     siete; al omitir uno todo se corre una posicion.
        #   - 7 arrays con heights antes que elevations -> ret=1: marshalea
        #     (ambos son double[]) pero ETABS recibe [3,3,3] como elevaciones,
        #     tres niveles en la misma cota. GetStories_2 devuelve en runtime
        #     elevaciones primero (crecientes 3.6576..14.6304) y alturas
        #     despues (constantes 3.6576), y get_stories() en este archivo ya
        #     lee numeric[0] como elevacion: el setter debe usar ese orden.
        def _siete(master, similar):
            return (names, elevations, heights, master, similar,
                    splice_above, splice_height)

        # SetStories_2 antepone BaseElevation y NumberStories y NO lleva
        # elevaciones -- las deduce de la base mas las alturas. Firma leida
        # del typelib (dispid 17):
        #   SetStories_2(BaseElevation, NumberStories, StoryNames[],
        #                StoryHeights[], IsMasterStory[], SimilarToStory[],
        #                SpliceAbove[], SpliceHeight[], Color[])
        # Es la unica variante que consume base_elevation como parametro.
        # Sus arrays son [in,out], por eso pasar listas de Python produce
        # "unicode string expected instead of bool instance" cuando el orden
        # no calza exactamente: no tolera un argumento de mas.
        def _s2(master, similar, with_color):
            base = (float(base_elevation), n, names, heights,
                    master, similar, splice_above, splice_height)
            return base + ((color,) if with_color else ())

        if abs(float(base_elevation)) > 1e-9:
            logger.warning(
                "base_elevation=%g solo se aplica si cae a SetStories_2; "
                "la variante SetStories de 7 arrays no lo soporta.",
                base_elevation)

        # SetStories_2 va PRIMERO: en ETABS 23.3.0 el SetStories legado
        # devuelve ret=1 incluso ante un no-op. Prueba del 2026-08-07: se le
        # pidio exactamente la configuracion que el modelo ya tenia (Story1..4,
        # 3.6576 c/u, la que GetStories acababa de reportar) y tambien fallo.
        # Un no-op rechazado descarta el contenido como causa: el metodo esta
        # en el typelib (dispid 15) pero superseded por _2, que es justamente
        # la razon de que exista el sufijo. SetStories queda de ultimo por si
        # otra instalacion invierte la situacion.
        oapi.call(
            model.Story,
            [
                ("SetStories_2", _s2(is_master_all, similar_none, True)),
                ("SetStories_2", _s2(is_master_all, similar_none, False)),
                ("SetStories_2", _s2(is_master_top, similar_top, True)),
                ("SetStories", _siete(is_master_all, similar_none)),
                ("SetStories", _siete(is_master_top, similar_top)),
            ],
            "definicion de niveles",
        )
        total = sum(heights)
        return (f"{n} nivel(es) definidos desde elevacion {base_elevation:g}. "
                f"Altura total: {total:g}.")

    @com_call
    def _count_objects(self) -> int:
        model = self._model()
        return (int(model.PointObj.Count()) + int(model.FrameObj.Count())
                + int(model.AreaObj.Count()))

    @com_call
    def _set_stories_via_texto(self, names: list[str], heights: list[float],
                               base_elevation: float) -> str:
        """Redefine niveles en un modelo CON objetos via texto ($et/e2k).

        File.Save regenera el .$et (formato e2k); se reescribe el bloque
        $ STORIES y se renombran las referencias por token exacto; el
        File.OpenFile del texto editado importa y remapea los objetos; se
        verifica y se vuelve a guardar como .EDB. Verificado el 2026-08-07
        sobre el respaldo ANTES de R02: 4 niveles -> 3 renombrados a
        "Nivel 1/2/3" de 3 m, geometria intacta (36/63/12).

        ATENCION: invalida resultados de analisis; el mapeo de nombres
        viejo->nuevo es posicional de abajo hacia arriba; los niveles viejos
        que sobren (se eliminan) deben estar vacios; las alturas se pasan en
        las unidades ACTIVAS y se convierten a las del archivo (la linea
        UNITS del $et), que pueden diferir.
        """
        model = self._model()
        n = len(names)
        edb = str(model.GetModelFilename() or "")
        if not os.path.isfile(edb):
            raise EtabsError("El modelo debe estar guardado en disco antes "
                             "de redefinir niveles por texto.")

        r = oapi.call(model.Story, [("GetStories_2", ())], "niveles actuales")
        viejos = oapi.find_str_list(r) or []
        if not viejos:
            raise EtabsError("No se pudieron leer los niveles actuales.")

        respaldo = os.path.splitext(edb)[0] + ".respaldo-niveles.EDB"
        shutil.copy2(edb, respaldo)
        oapi.call_checked(model.File, "Save", (edb,), "guardado previo")
        et_path = os.path.splitext(edb)[0] + ".$et"
        if not os.path.isfile(et_path):
            raise EtabsError(f"ETABS no genero el texto del modelo: {et_path}")

        with open(et_path, "r", encoding="latin-1") as f:
            texto = f.read()

        # Los largos del $et van en las unidades DEL ARCHIVO (linea UNITS),
        # que pueden diferir de las activas (este modelo: LB/IN vs kN/m).
        m = re.search(r'UNITS\s+"[^"]+"\s+"([^"]+)"', texto)
        len_archivo = (m.group(1) if m else "m").strip().lower()
        idx = model.GetPresentUnits()
        _f, len_activa, _t = [s.strip()
                              for s in PRESET_UNITS[idx - 1].split(",")]
        try:
            factor = (self._LENGTH_TO_MM[len_activa]
                      / self._LENGTH_TO_MM[len_archivo])
        except KeyError:
            raise EtabsError(f"Unidad de longitud no reconocida: activa "
                             f"'{len_activa}', archivo '{len_archivo}'.")

        # 1) Reescribir el bloque $ STORIES (va de ARRIBA hacia abajo, con
        #    la Base al final). Sin atributo MASTERSTORY los niveles quedan
        #    todos independientes, igual que el modelo editado por GUI.
        salida: list[str] = []
        en_bloque = False
        for ln in texto.splitlines():
            s = ln.strip()
            if s.startswith("$ STORIES"):
                en_bloque = True
                salida.append(ln)
                # :.10g y no :.6g: con 6 cifras, 3 m -> 118.110 in ->
                # 2.99999 m al releer. Reproducido en la prueba 2026-08-07.
                for nm, h in zip(reversed(names), reversed(heights)):
                    salida.append(f'  STORY "{nm}"  HEIGHT {h * factor:.10g} ')
                salida.append(
                    f'  STORY "Base"  ELEV {base_elevation * factor:.10g} ')
                continue
            if en_bloque:
                if s.startswith("$"):
                    en_bloque = False
                    salida.append(ln)
                continue
            salida.append(ln)
        nuevo = "\n".join(salida)

        # 2) Renombrar referencias por token exacto entre comillas, en dos
        #    fases para tolerar colisiones (p.ej. Story1 -> Story2).
        pares = list(zip(viejos,
                         list(names) + [None] * max(0, len(viejos) - n)))
        for i, (viejo, _nv) in enumerate(pares):
            nuevo = nuevo.replace(f'"{viejo}"', f'"\x00NV{i}\x00"')
        for i, (viejo, nv) in enumerate(pares):
            marca = f'"\x00NV{i}\x00"'
            if nv is None:
                if marca in nuevo:
                    raise EtabsError(
                        f"El nivel '{viejo}' se eliminaria pero tiene "
                        f"objetos asignados; muevalos o borrelos primero. "
                        f"Respaldo: {respaldo}")
                continue
            nuevo = nuevo.replace(marca, f'"{nv}"')

        e2k = os.path.splitext(edb)[0] + ".niveles.e2k"
        with open(e2k, "w", encoding="latin-1") as f:
            f.write(nuevo)

        # 3) Importar con vigilante de modales: el import puede levantar un
        #    dialogo que bloquea el hilo COM (auditoria 7.6, reproducido el
        #    2026-08-07); descartado, el import termina bien.
        alto = threading.Event()
        vigia = threading.Thread(target=_descartar_modales_etabs,
                                 args=(alto,), daemon=True)
        vigia.start()
        try:
            oapi.call_checked(model.File, "OpenFile", (e2k,),
                              "import del texto del modelo")
        finally:
            alto.set()

        # 4) Verificar y devolver la identidad del archivo al .EDB.
        model.SetPresentUnits(idx)  # el import puede resetear las unidades
        r = oapi.call(model.Story, [("GetStories_2", ())],
                      "verificacion de niveles")
        leidos = oapi.find_str_list(r) or []
        if list(leidos) != list(names):
            raise EtabsError(
                f"Verificacion fallida: niveles leidos {leidos}, esperados "
                f"{list(names)}. Respaldo: {respaldo}")
        nums = oapi.find_num_lists(r, n)
        if len(nums) >= 2:  # (elevaciones, alturas, ...) segun 0.3
            alturas_leidas = nums[1]
            for esp, leida in zip(heights, alturas_leidas):
                if abs(leida - esp) > 1e-5 * max(1.0, abs(esp)):
                    raise EtabsError(
                        f"Verificacion fallida: alturas leidas "
                        f"{[round(x, 6) for x in alturas_leidas]}, esperadas "
                        f"{heights}. Respaldo: {respaldo}")
        oapi.call_checked(model.File, "Save", (edb,), "guardado final")
        return (f"{n} nivel(es) redefinidos via texto del modelo "
                f"(geometria remapeada por ETABS). Respaldo: {respaldo}. "
                f"Resultados de analisis invalidados.")

    # ------------------------------------------------------------------
    # Materiales y secciones
    # ------------------------------------------------------------------

    @com_call
    def define_concrete_material(self, name: str, fc: float,
                                 E: float = 0.0, poisson: float = 0.2,
                                 unit_weight: float = 0.0) -> str:
        """Define un material de hormigon armado.

        Args:
            name: nombre del material, ej. "H28".
            fc: resistencia a compresion f'c en las unidades activas
                (con kN, m: 28000 kN/m2 = 28 MPa).
            E: modulo de elasticidad. Si es 0, se estima como 4700*sqrt(f'c)
               segun ACI 318 (requiere f'c en MPa; se convierte internamente
               asumiendo las unidades activas).
            poisson: coeficiente de Poisson, por defecto 0.2.
            unit_weight: peso por unidad de volumen EN LAS UNIDADES ACTIVAS.
                Con kN, m: 23.5631 = default de ETABS para hormigon de peso
                normal (150 lb/ft3 = 2402.8 kgf/m3); si se prefiere el valor
                metrico redondo de 2400 kgf/m3, son 23.536. Si es 0, el
                material queda SIN peso y el multiplicador de peso propio
                del patron D no genera carga.
        """
        model = self._model()
        MATERIAL_CONCRETE = 2
        oapi.call(
            model.PropMaterial,
            [
                ("SetMaterial", (name, MATERIAL_CONCRETE, -1, "", "")),
                ("SetMaterial", (name, MATERIAL_CONCRETE)),
            ],
            f"creacion del material '{name}'",
        )

        if E <= 0:
            # ACI 318: Ec = 4700*sqrt(f'c) con ambos en MPa. La conversion usa
            # las unidades activas reales del modelo, no una heuristica.
            to_mpa = self._stress_to_mpa()
            fc_mpa = fc * to_mpa
            E_mpa = 4700.0 * (fc_mpa ** 0.5)
            E = E_mpa / to_mpa

        oapi.call(
            model.PropMaterial,
            [("SetMPIsotropic", (name, float(E), float(poisson), 9.9e-6))],
            f"propiedades mecanicas de '{name}'",
        )
        oapi.call(
            model.PropMaterial,
            [
                ("SetOConcrete_1", (name, float(fc), False, 0.0, 1, 0,
                                    0.0022, 0.0052, -0.1, 0.0, 0.0)),
                ("SetOConcrete", (name, float(fc), False, 0.0, 1, 0, 0.0022, 0.0052)),
            ],
            f"parametros de hormigon de '{name}'",
        )
        # Un material creado por API arranca con peso por unidad de volumen 0:
        # sin SetWeightAndMass, el self_weight_multiplier del patron "D"
        # genera peso propio NULO y el analisis corre sin ningun error visible
        # (el defecto mas peligroso de la auditoria 2026-08-07, seccion 4).
        w_note = ""
        if unit_weight > 0:
            oapi.call(
                model.PropMaterial,
                [("SetWeightAndMass", (name, 1, float(unit_weight)))],
                f"peso por unidad de volumen de '{name}'",
            )
            w_note = f", w={unit_weight:g}"
        else:
            logger.warning("Material '%s' creado sin peso por unidad de "
                           "volumen: el peso propio del patron D sera 0.", name)
            w_note = ", SIN PESO (unit_weight=0)"
        return (f"Material '{name}' creado: f'c={fc:g}, E={E:g}, v={poisson:g}"
                f"{w_note} (unidades activas del modelo).")

    @com_call
    def define_rect_section(self, name: str, material: str,
                            depth: float, width: float) -> str:
        """Define una seccion rectangular de hormigon.

        Args:
            name: nombre de la seccion, ej. "C50x50" o "V30x50".
            material: nombre de un material ya definido.
            depth: peralte total (dimension en el eje local 3), ej. 0.50.
            width: ancho (dimension en el eje local 2), ej. 0.30.
        """
        model = self._model()
        oapi.call(
            model.PropFrame,
            [
                ("SetRectangle", (name, material, float(depth), float(width), -1, "", "")),
                ("SetRectangle", (name, material, float(depth), float(width))),
            ],
            f"creacion de la seccion '{name}'",
        )
        return f"Seccion '{name}' creada: {depth:g} x {width:g}, material '{material}'."

    @com_call
    def assign_sections(self, column_section: str, beam_section: str) -> str:
        """Asigna secciones a todos los frames, clasificandolos por geometria.

        Un frame se considera columna si sus dos extremos comparten X e Y
        (elemento vertical); en caso contrario, viga. Evita tener que
        seleccionar elemento por elemento en la interfaz.

        Args:
            column_section: seccion a asignar a los elementos verticales.
            beam_section: seccion a asignar al resto.
        """
        model = self._model()
        frames = self._read_frames()
        if not frames:
            raise EtabsError("El modelo no contiene frames.")

        n_col = n_beam = 0
        errors: list[str] = []
        TOL = 1e-6
        for fr in frames:
            vertical = (abs(fr.xs[0] - fr.xs[1]) < TOL
                        and abs(fr.ys[0] - fr.ys[1]) < TOL)
            section = column_section if vertical else beam_section
            try:
                oapi.call(
                    model.FrameObj,
                    [("SetSection", (fr.id, section, 0)),
                     ("SetSection", (fr.id, section))],
                    f"asignacion de seccion al frame {fr.id}",
                )
                if vertical:
                    n_col += 1
                else:
                    n_beam += 1
            except Exception as e:
                errors.append(f"{fr.id}: {e}")

        msg = (f"Seccion '{column_section}' asignada a {n_col} columna(s); "
               f"'{beam_section}' a {n_beam} viga(s).")
        if errors:
            msg += f" {len(errors)} fallo(s): " + "; ".join(errors[:5])
        return msg

    @com_call
    def define_steel_material(self, name: str, fy: float, fu: float = 0.0,
                              E: float = 0.0, unit_weight: float = 0.0) -> str:
        """Define un material de acero estructural.

        Args:
            name: nombre del material, ej. "A992" o "A36".
            fy: esfuerzo de fluencia, en las unidades activas.
            fu: esfuerzo ultimo. Si es 0, se estima como 1.25*fy
                (relacion tipica A992; ajustar si el acero real difiere).
            E: modulo de elasticidad. Si es 0, se usa 200000 MPa convertido
               a las unidades activas del modelo.
            unit_weight: peso por unidad de volumen EN LAS UNIDADES ACTIVAS
                (con kN, m: 76.9729 kN/m3). Si es 0, el material queda SIN
                peso y el peso propio no genera carga.
        """
        model = self._model()
        MATERIAL_STEEL = 1
        oapi.call(
            model.PropMaterial,
            [("SetMaterial", (name, MATERIAL_STEEL, -1, "", "")),
             ("SetMaterial", (name, MATERIAL_STEEL))],
            f"creacion del material '{name}'",
        )
        if fu <= 0:
            fu = 1.25 * fy
        if E <= 0:
            to_mpa = self._stress_to_mpa()
            E = 200000.0 / to_mpa
        oapi.call(model.PropMaterial,
                  [("SetMPIsotropic", (name, float(E), 0.3, 11.7e-6))],
                  f"propiedades mecanicas de '{name}'")
        # SetOSteel_1(Name, Fy, Fu, EFy, EFu, SSType, SSHysType,
        #             StrainAtHardening, StrainAtMaxStress, StrainAtRupture,
        #             FinalSlope[, Temp])
        # La version anterior pasaba (..., 0.02, 0.1, -0.1, 0.0): el patron de
        # SetOConcrete_1 copiado tal cual, que dejaba StrainAtRupture=-0.1
        # (deformacion negativa, imposible) y FinalSlope=0.0. Se corrige a
        # StrainAtRupture=0.20 y FinalSlope=-0.10. La variante de respaldo
        # SetOSteel de 7 args tambien era invalida (SetOSteel tiene los mismos
        # 11 parametros); se reemplaza por SetOSteel_1 con Temp explicito.
        oapi.call(
            model.PropMaterial,
            [("SetOSteel_1", (name, float(fy), float(fu), float(fy), float(fu),
                              1, 0, 0.02, 0.10, 0.20, -0.10)),
             ("SetOSteel_1", (name, float(fy), float(fu), float(fy), float(fu),
                              1, 0, 0.02, 0.10, 0.20, -0.10, 0.0))],
            f"parametros de acero de '{name}'",
        )
        # Mismo defecto silencioso que en hormigon: sin SetWeightAndMass el
        # material queda con peso 0 y el peso propio no carga nada.
        w_note = ""
        if unit_weight > 0:
            oapi.call(
                model.PropMaterial,
                [("SetWeightAndMass", (name, 1, float(unit_weight)))],
                f"peso por unidad de volumen de '{name}'",
            )
            w_note = f", w={unit_weight:g}"
        else:
            logger.warning("Material '%s' creado sin peso por unidad de "
                           "volumen: el peso propio sera 0.", name)
            w_note = ", SIN PESO (unit_weight=0)"
        return f"Material '{name}' creado: fy={fy:g}, fu={fu:g}, E={E:g}{w_note}."

    @com_call
    def define_i_section(self, name: str, material: str, depth: float,
                         flange_width: float, flange_thickness: float,
                         web_thickness: float) -> str:
        """Define un perfil I/H de acero (seccion soldada o laminada equivalente).

        Args:
            name: nombre de la seccion, ej. "W14x90" o "PS-1".
            material: nombre de un material de acero ya definido.
            depth: peralte total.
            flange_width: ancho del patin.
            flange_thickness: espesor del patin.
            web_thickness: espesor del alma.
        """
        model = self._model()
        oapi.call(
            model.PropFrame,
            [("SetISection",
              (name, material, float(depth), float(flange_width),
               float(flange_thickness), float(web_thickness),
               float(flange_width), float(flange_thickness), -1, "", "")),
             ("SetISection",
              (name, material, float(depth), float(flange_width),
               float(flange_thickness), float(web_thickness),
               float(flange_width), float(flange_thickness)))],
            f"creacion de la seccion '{name}'",
        )
        return (f"Seccion I '{name}' creada: d={depth:g}, bf={flange_width:g}, "
                f"tf={flange_thickness:g}, tw={web_thickness:g}, "
                f"material '{material}'.")

    @com_call
    def define_pipe_section(self, name: str, material: str,
                            diameter: float, thickness: float) -> str:
        """Define un perfil tubular circular (HSS redondo) de acero.

        Args:
            name: nombre de la seccion.
            material: material de acero ya definido.
            diameter: diametro exterior.
            thickness: espesor de pared.
        """
        model = self._model()
        oapi.call(
            model.PropFrame,
            [("SetPipe", (name, material, float(diameter), float(thickness),
                          -1, "", "")),
             ("SetPipe", (name, material, float(diameter), float(thickness)))],
            f"creacion de la seccion '{name}'",
        )
        return f"Seccion tubular '{name}' creada: D={diameter:g}, t={thickness:g}."

    @com_call
    def run_steel_design(self, code: str = "") -> str:
        """Ejecuta el diseño de acero. Requiere analisis previo.

        Args:
            code: codigo de diseño, ej. "AISC 360-16". Vacio = el ya
                  configurado en el modelo.
        """
        model = self._model()
        if code:
            oapi.call(model.DesignSteel, [("SetCode", (code,))],
                      f"seleccion del codigo '{code}'")
        oapi.call(model.DesignSteel, [("StartDesign", ())], "diseño de acero")
        return "Diseño de acero ejecutado" + (f" con codigo '{code}'." if code else ".")

    # ------------------------------------------------------------------
    # Apoyos
    # ------------------------------------------------------------------

    @com_call
    def set_base_restraints(self, elevation: float = 0.0,
                            restraint: str = "empotrado") -> str:
        """Asigna apoyos a todos los puntos en una elevacion dada.

        Args:
            elevation: cota Z de los puntos a restringir, normalmente 0.
            restraint: "empotrado" (6 grados restringidos) o
                       "articulado" (3 traslaciones restringidas).
        """
        model = self._model()
        kind = restraint.strip().lower()
        if kind in ("empotrado", "fixed", "fijo"):
            values = [True, True, True, True, True, True]
        elif kind in ("articulado", "pinned", "rotula"):
            values = [True, True, True, False, False, False]
        else:
            raise EtabsError(
                f"Tipo de apoyo no reconocido: '{restraint}'. "
                f"Use 'empotrado' o 'articulado'.")

        points = self._read_points()
        TOL = 1e-6
        targets = [p for p in points if abs(p.zs[0] - elevation) < TOL]
        if not targets:
            raise EtabsError(
                f"No hay puntos en la elevacion Z={elevation:g}. "
                f"Cotas presentes: "
                f"{sorted({round(p.zs[0], 4) for p in points})}")

        for p in targets:
            oapi.call(
                model.PointObj,
                [("SetRestraint", (p.id, values, 0)),
                 ("SetRestraint", (p.id, values))],
                f"apoyo en el punto {p.id}",
            )
        return (f"Apoyo '{kind}' asignado a {len(targets)} punto(s) "
                f"en Z={elevation:g}.")

    # ------------------------------------------------------------------
    # Resortes (apoyos elasticos)
    # ------------------------------------------------------------------

    @com_call
    def set_point_spring(self, point_id: str, kx: float = 0.0, ky: float = 0.0,
                         kz: float = 0.0, krx: float = 0.0, kry: float = 0.0,
                         krz: float = 0.0, replace: bool = True) -> str:
        """Asigna rigidez de resorte a un punto (cimentacion flexible, etc.).

        Args:
            point_id: ID del punto (de get_points).
            kx, ky, kz: rigidez traslacional en cada eje global, en
                        fuerza/longitud de las unidades activas.
            krx, kry, krz: rigidez rotacional, en fuerza*longitud/radian.
            replace: True reemplaza el resorte previo; False lo suma.
        """
        k = [float(kx), float(ky), float(kz), float(krx), float(kry), float(krz)]
        if not any(k):
            raise EtabsError("Debe indicar al menos una rigidez distinta de cero.")
        model = self._model()
        oapi.call(
            model.PointObj,
            [("SetSpring", (point_id, k, bool(replace), True, "Global")),
             ("SetSpring", (point_id, k, bool(replace), True)),
             ("SetSpring", (point_id, k, bool(replace)))],
            f"resorte en el punto {point_id}",
        )
        return (f"Resorte asignado en {point_id}: "
                f"K=[{kx:g}, {ky:g}, {kz:g}, {krx:g}, {kry:g}, {krz:g}].")

    @com_call
    def set_base_springs(self, elevation: float = 0.0, kx: float = 0.0,
                         ky: float = 0.0, kz: float = 0.0, krx: float = 0.0,
                         kry: float = 0.0, krz: float = 0.0) -> str:
        """Asigna la misma rigidez de resorte a todos los puntos de una cota.

        Alternativa a set_base_restraints cuando la cimentacion no se modela
        como empotramiento rigido sino con rigidez de suelo (Winkler, pilotes
        equivalentes, etc.).
        """
        points = self._read_points()
        TOL = 1e-6
        targets = [p for p in points if abs(p.zs[0] - elevation) < TOL]
        if not targets:
            raise EtabsError(
                f"No hay puntos en Z={elevation:g}. Cotas presentes: "
                f"{sorted({round(p.zs[0], 4) for p in points})}")
        for p in targets:
            self.set_point_spring(p.id, kx, ky, kz, krx, kry, krz)
        return f"Resorte asignado a {len(targets)} punto(s) en Z={elevation:g}."

    # ------------------------------------------------------------------
    # Resultados dedicados (reacciones, fuerzas en frames)
    # ------------------------------------------------------------------
    # get_story_drifts ya cubre derivas. Estos dos wrappers cubren los otros
    # resultados de uso mas frecuente en una memoria de calculo. Cualquier
    # otro resultado sigue accesible de forma generica via get_table_data
    # sobre las tablas "Joint Reactions", "Element Forces - Frames", etc.
    # que aparecen despues de correr el analisis (verificar nombre exacto
    # con list_tables tras run_analysis, puede variar por version).

    @com_call
    def _select_output_cases(self, model: Any, cases: list[str] | None) -> None:
        # @com_call latente: hoy solo se invoca desde metodos ya decorados;
        # la guarda de reentrada de comthread evita el deadlock del executor
        # de 1 worker, y el decorador protege a llamadores futuros.
        if not cases:
            return
        oapi.call(model.Results.Setup,
                  [("DeselectAllCasesAndCombosForOutput", ())],
                  "limpieza de casos de salida")
        for case in cases:
            try:
                oapi.call(model.Results.Setup,
                          [("SetCaseSelectedForOutput", (case,))],
                          f"seleccion del caso '{case}'")
            except Exception:
                oapi.call(model.Results.Setup,
                          [("SetComboSelectedForOutput", (case,))],
                          f"seleccion de la combinacion '{case}'")

    @com_call
    def get_joint_reactions(self, point_ids: list[str] | None = None,
                            cases: list[str] | None = None) -> str:
        """Devuelve las reacciones de apoyo tras el analisis.

        Args:
            point_ids: puntos a consultar. None = todos los puntos con
                       restriccion o resorte (se detecta automaticamente).
            cases: casos/combinaciones a incluir. None = los ya seleccionados.
        """
        model = self._model()
        self._select_output_cases(model, cases)

        if point_ids is None:
            points = self._read_points()
            point_ids = [p.id for p in points]
        results: list[str] = []
        for pid in point_ids:
            try:
                r = oapi.call(
                    model.Results,
                    [("JointReact", (pid, 0)), ("JointReact", (pid, 0, 0))],
                    f"reaccion en el punto {pid}",
                )
            except Exception:
                continue
            n = oapi.outs(r)[0] if oapi.outs(r) else 0
            if not isinstance(n, int) or n == 0:
                continue
            strs = oapi.find_str_lists(r, n)
            nums = oapi.find_num_lists(r, n)
            # [out] de JointReact: NumberResults, Obj[], Elm[], LoadCase[],
            # StepType[], StepNum[], F1..F3, M1..M3. LoadCase es la TERCERA
            # lista de strings; strs[0] es Obj (el mismo pid repetido) y con
            # el codigo anterior el nombre del caso nunca se mostraba.
            case_col = strs[2] if len(strs) > 2 else (strs[0] if strs else ["?"] * n)
            # F1..M3 son las SEIS ULTIMAS columnas numericas: StepNum tambien
            # tiene longitud n y precede a F1, por eso [:6] reportaba
            # StepNum,F1..M2 bajo la etiqueta F1..M3 y perdia M3.
            force_cols = nums[-6:] if len(nums) >= 6 else nums
            for i in range(n):
                vals = ", ".join(f"{c[i]:.3f}" for c in force_cols)
                results.append(f"{pid} | {case_col[i]} | [{vals}]")
        if not results:
            return ("Sin reacciones. Verifique que el analisis corrio, que hay "
                    "casos seleccionados para salida, y que los puntos tienen "
                    "restriccion o resorte asignado.")
        return f"{len(results)} reaccion(es) (F1,F2,F3,M1,M2,M3):\n" + "\n".join(results)

    @com_call
    def get_frame_forces(self, frame_ids: list[str] | None = None,
                         cases: list[str] | None = None) -> str:
        """Devuelve fuerzas internas (P, V2, V3, T, M2, M3) en frames tras el analisis.

        Args:
            frame_ids: frames a consultar. None = todos.
            cases: casos/combinaciones a incluir. None = los ya seleccionados.
        """
        model = self._model()
        self._select_output_cases(model, cases)

        if frame_ids is None:
            frame_ids = [f.id for f in self._read_frames()]
        results: list[str] = []
        for fid in frame_ids:
            try:
                r = oapi.call(
                    model.Results,
                    [("FrameForce", (fid, 0)), ("FrameForce", (fid, 0, 0))],
                    f"fuerzas en el frame {fid}",
                )
            except Exception:
                continue
            n = oapi.outs(r)[0] if oapi.outs(r) else 0
            if not isinstance(n, int) or n == 0:
                continue
            strs = oapi.find_str_lists(r, n)
            nums = oapi.find_num_lists(r, n)
            # [out] de FrameForce: NumberResults, Obj[], ObjSta[], Elm[],
            # ElmSta[], LoadCase[], StepType[], StepNum[], P, V2, V3, T,
            # M2, M3. TRES columnas numericas (ObjSta, ElmSta, StepNum)
            # preceden a P: con [:6] la salida era ObjSta,ElmSta,StepNum,
            # P,V2,V3 etiquetada como P..M3 -- numeros plausibles, todos
            # equivocados. Las componentes son las seis ultimas.
            case_col = strs[2] if len(strs) > 2 else (strs[0] if strs else ["?"] * n)
            force_cols = nums[-6:] if len(nums) >= 6 else nums
            for i in range(n):
                vals = ", ".join(f"{c[i]:.3f}" for c in force_cols)
                results.append(f"{fid} | {case_col[i]} | [{vals}]")
        if not results:
            return ("Sin fuerzas. Verifique que el analisis corrio y que hay "
                    "casos seleccionados para salida.")
        return f"{len(results)} resultado(s) (P,V2,V3,T,M2,M3):\n" + "\n".join(results)

    # ------------------------------------------------------------------
    # Patrones de carga y combinaciones
    # ------------------------------------------------------------------

    _PATTERN_TYPES = {
        "muerta": 1, "dead": 1, "d": 1,
        "supermuerta": 2, "superdead": 2, "sdl": 2,
        "viva": 3, "live": 3, "l": 3,
        "viva_reducible": 4, "reducelive": 4,
        "sismo": 5, "quake": 5, "e": 5,
        "viento": 6, "wind": 6, "w": 6,
        "nieve": 7, "snow": 7,
        "otra": 8, "other": 8,
        "viva_techo": 11, "rooflive": 11, "lr": 11,
    }

    @com_call
    def add_load_pattern(self, name: str, pattern_type: str,
                         self_weight_multiplier: float = 0.0) -> str:
        """Crea un patron de carga.

        Args:
            name: nombre del patron, ej. "D", "L", "Lr", "Ex", "Ey".
            pattern_type: "muerta", "viva", "viva_techo", "sismo", "viento",
                          "nieve", "supermuerta" u "otra".
            self_weight_multiplier: multiplicador de peso propio. Use 1.0
                                    solo en el patron de carga muerta.
        """
        model = self._model()
        key = pattern_type.strip().lower()
        if key not in self._PATTERN_TYPES:
            raise EtabsError(
                f"Tipo de patron no reconocido: '{pattern_type}'. "
                f"Opciones: {', '.join(sorted(set(self._PATTERN_TYPES)))}")
        code = self._PATTERN_TYPES[key]
        oapi.call(
            model.LoadPatterns,
            [("Add", (name, code, float(self_weight_multiplier), True)),
             ("Add", (name, code, float(self_weight_multiplier)))],
            f"creacion del patron '{name}'",
        )
        return (f"Patron '{name}' creado (tipo {key}, "
                f"peso propio x{self_weight_multiplier:g}).")

    @com_call
    def add_load_combo(self, name: str, cases: dict[str, float]) -> str:
        """Crea una combinacion lineal aditiva de casos de carga.

        Args:
            name: nombre de la combinacion, ej. "1.2D+1.6L".
            cases: diccionario {nombre_del_caso: factor}, ej.
                   {"D": 1.2, "L": 1.6, "Lr": 0.5}.
        """
        if not cases:
            raise EtabsError("La combinacion debe incluir al menos un caso.")
        model = self._model()
        oapi.call(
            model.RespCombo,
            [("Add", (name, 0))],
            f"creacion de la combinacion '{name}'",
        )
        for case_name, factor in cases.items():
            oapi.call(
                model.RespCombo,
                [("SetCaseList", (name, 0, case_name, float(factor)))],
                f"caso '{case_name}' en la combinacion '{name}'",
            )
        terms = " + ".join(f"{v:g}{k}" for k, v in cases.items())
        return f"Combinacion '{name}' creada: {terms}."

    @com_call
    def assign_frame_distributed_load(self, load_pattern: str, value: float,
                                      direction: int = 10,
                                      only_beams: bool = True,
                                      replace: bool = True,
                                      elevation: float | None = None,
                                      elevations: list[float] | None = None,
                                      tolerance: float = 1e-6) -> str:
        """Aplica una carga uniformemente distribuida a los frames.

        Args:
            load_pattern: nombre de un patron ya creado, ej. "D".
            value: magnitud por unidad de longitud, en las unidades activas
                   (con kN, m: kN/m). Positiva hacia abajo si direction=10.
            direction: 10 = gravedad (eje Z global, sentido descendente).
            only_beams: si True, solo carga los elementos no verticales.
            replace: si True, reemplaza cargas previas de ese patron.
            elevation: cota Z unica a cargar, ej. 9.0 para las vigas de techo.
            elevations: varias cotas, ej. [3.0, 6.0]. Prioridad sobre elevation.
            tolerance: holgura para comparar cotas.
        """
        model = self._model()
        frames = self._read_frames()
        total = len(frames)
        TOL = tolerance
        if only_beams:
            frames = [f for f in frames
                      if not (abs(f.xs[0] - f.xs[1]) < TOL
                              and abs(f.ys[0] - f.ys[1]) < TOL)]

        wanted: list[float] | None = None
        if elevations:
            wanted = [float(z) for z in elevations]
        elif elevation is not None:
            wanted = [float(elevation)]
        if wanted is not None:
            frames = [f for f in frames
                      if all(any(abs(z - w) < TOL for w in wanted)
                             for z in f.zs)]

        if not frames:
            raise EtabsError(
                "No hay frames que cumplan el criterio"
                + (f" (cota(s) {wanted})." if wanted is not None else "."))

        for fr in frames:
            oapi.call(
                model.FrameObj,
                [("SetLoadDistributed",
                  (fr.id, load_pattern, 1, direction, 0.0, 1.0,
                   float(value), float(value), "Global", True, replace, 0))],
                f"carga distribuida en el frame {fr.id}",
            )
        scope = f" en Z={wanted}" if wanted is not None else ""
        return (f"Carga {value:g} aplicada en el patron '{load_pattern}' "
                f"a {len(frames)} de {total} frame(s){scope}.")

    # ------------------------------------------------------------------
    # Analisis y resultados
    # ------------------------------------------------------------------

    @com_call
    def run_analysis(self) -> str:
        """Ejecuta el analisis del modelo. Requiere que el modelo este guardado."""
        model = self._model()
        oapi.call(model.Analyze, [("RunAnalysis", ())], "ejecucion del analisis")
        return "Analisis ejecutado."

    @com_call
    def get_story_drifts(self, cases: list[str] | None = None) -> str:
        """Devuelve las derivas de piso resultantes del analisis.

        Args:
            cases: nombres de casos o combinaciones a incluir. Si se omite,
                   usa los que ya esten seleccionados para salida.
        """
        model = self._model()
        if cases:
            oapi.call(model.Results.Setup,
                      [("DeselectAllCasesAndCombosForOutput", ())],
                      "limpieza de casos de salida")
            for case in cases:
                try:
                    oapi.call(model.Results.Setup,
                              [("SetCaseSelectedForOutput", (case,))],
                              f"seleccion del caso '{case}'")
                except Exception:
                    oapi.call(model.Results.Setup,
                              [("SetComboSelectedForOutput", (case,))],
                              f"seleccion de la combinacion '{case}'")

        result = oapi.call(model.Results, [("StoryDrifts", ())],
                           "lectura de derivas de piso")
        values = oapi.outs(result)
        if not values or not isinstance(values[0], int) or values[0] == 0:
            return ("Sin resultados de deriva. Verifique que el analisis "
                    "corrio y que hay casos seleccionados para salida.")

        # Orden documentado (reciente): NumberResults, Story, LoadCase,
        # StepType, StepNum, Direction, Drift, Label, X, Y, Z. Pero el orden
        # no es contractual entre versiones: cada columna se identifica por
        # contenido, con el orden posicional solo como respaldo.
        n = values[0]
        strings = oapi.find_str_lists(result, n)
        numbers = oapi.find_num_lists(result, n)
        if len(strings) < 2 or not numbers:
            return f"{n} resultado(s) de deriva, formato no reconocido: {values!r}"

        story, case = strings[0], strings[1]
        direction = oapi.pick_direction(strings) or ["?"] * n
        drift = oapi.pick_drift(numbers)
        if drift is None:
            return f"{n} resultado(s), sin columna de derivas reconocible."

        lines = [f"{story[i]} | {case[i]} | dir {direction[i]} | "
                 f"deriva {drift[i]:.5f}" for i in range(n)]
        peak = max(range(n), key=lambda i: abs(drift[i]))
        return (f"{n} resultado(s):\n" + "\n".join(lines)
                + f"\n\nMaxima: {drift[peak]:.5f} en {story[peak]} "
                  f"({case[peak]}, dir {direction[peak]}).")

    # ------------------------------------------------------------------
    # Tablas interactivas (DatabaseTables)
    # ------------------------------------------------------------------
    # Acceso generico de lectura/escritura a TODAS las tablas del modelo:
    # grids ("Grid Definitions - Grid Lines"), masa sismica, definiciones de
    # carga, etc. Cubre lo que no tiene metodo dedicado en la OAPI.

    @com_call
    def list_tables(self, filter: str = "") -> str:
        """Lista las tablas de base de datos disponibles en el modelo.

        Args:
            filter: subcadena para filtrar, ej. "Grid", "Story", "Mass".
        """
        model = self._model()
        result = oapi.call(model.DatabaseTables,
                           [("GetAvailableTables", ())],
                           "listado de tablas")
        keys = oapi.find_str_list(result)
        if not keys:
            return "No hay tablas disponibles."
        all_lists = oapi.find_str_lists(result, len(keys))
        names = all_lists[1] if len(all_lists) > 1 else keys
        needle = filter.strip().lower()
        lines = [keys[i] if keys[i] == names[i] else f"{keys[i]}"
                 for i in range(len(keys))
                 if not needle or needle in keys[i].lower()
                 or needle in names[i].lower()]
        if not lines:
            return f"Ninguna tabla coincide con '{filter}'."
        return f"{len(lines)} tabla(s):\n" + "\n".join(lines)

    @com_call
    def get_table_data(self, table_key: str, max_rows: int = 100) -> str:
        """Lee el contenido de una tabla del modelo.

        Args:
            table_key: clave exacta obtenida con list_tables,
                       ej. "Grid Definitions - Grid Lines".
            max_rows: maximo de filas a mostrar.
        """
        model = self._model()
        # FieldKeyList vacio = "todos los campos". La version anterior pasaba
        # [""], que es una lista con UN campo de nombre vacio: ETABS devolvia
        # solo los encabezados, sin filas. Se manifiesta en las tablas de la
        # familia casos/combinaciones/funciones (Load Combination Definitions,
        # Load Case Definitions - Response Spectrum, Modal Case Definitions,
        # Functions - Response Spectrum - User Defined), mientras que otras
        # (Grid, Story, Diaphragm, Load Pattern, asignaciones) lo toleraban y
        # devolvian todo igual -- por eso el defecto paso inadvertido.
        # Detectado 2026-08-07 al no poder verificar las combinaciones de R07.
        result = oapi.call(
            model.DatabaseTables,
            [
                ("GetTableForDisplayArray", (table_key, [], "")),
                ("GetTableForDisplayArray", (table_key, [], "", 0, [], 0, [])),
                ("GetTableForEditingArray", (table_key, "")),
                ("GetTableForEditingArray", (table_key, "", 0, [], 0, [])),
                # Respaldo con la forma anterior, por si alguna tabla la exige.
                ("GetTableForDisplayArray", (table_key, [""], "")),
                ("GetTableForDisplayArray", (table_key, [""], "", 0, [""], 0, [""])),
            ],
            f"lectura de la tabla '{table_key}'",
        )
        out = oapi.outs(result)
        str_lists = [list(v) for v in out
                     if isinstance(v, (tuple, list)) and len(v) > 0
                     and all(isinstance(x, str) for x in v)]
        if not str_lists:
            return f"Tabla '{table_key}' sin datos."

        # Posiciones CONTRACTUALES segun el typelib (leido 2026-08-07):
        #   GetTableForDisplayArray -> (FieldKeyList, TableVersion,
        #       FieldsKeysIncluded, NumberRecords, TableData)
        #   GetTableForEditingArray -> (TableVersion, FieldsKeysIncluded,
        #       NumberRecords, TableData)
        # En ambas, TableData es la ULTIMA lista de strings y NumberRecords el
        # ULTIMO entero. Identificar data por max(len) fallaba con tablas de
        # UNA fila: encabezado y datos miden lo mismo y max() devolvia el eco
        # del encabezado (mordio en R04 con 'Diaphragm Definitions' y en R10
        # con 'Slab Property Definitions', reportadas "no reconocibles").
        data = str_lists[-1]
        ints = [v for v in out
                if isinstance(v, int) and not isinstance(v, bool)]
        n_rec = ints[-1] if ints else 0

        fields = None
        if n_rec > 0 and len(data) % n_rec == 0:
            ncols = len(data) // n_rec
            # FieldsKeysIncluded es la lista de strings anterior a TableData.
            for sl in reversed(str_lists[:-1]):
                if len(sl) == ncols and any(s.strip() for s in sl):
                    fields = sl
                    break
            if fields is None:
                # Sin encabezado legible: se muestran las filas igual, con
                # columnas numeradas. Los datos valen mas que los titulos.
                fields = [f"c{i+1}" for i in range(ncols)]
        else:
            # Respaldo sin NumberRecords (variantes viejas de la firma): la
            # heuristica anterior por divisibilidad, pero sobre la lista mas
            # larga como datos, que era el comportamiento historico.
            data = max(str_lists, key=len)
            for sl in sorted(str_lists, key=len, reverse=True):
                if sl is data or not any(s.strip() for s in sl):
                    continue
                if len(data) % len(sl) == 0 and len(sl) < len(data):
                    fields = sl
                    break
            if fields is None:
                return (f"Tabla '{table_key}': {len(data)} celda(s), estructura de "
                        f"campos no reconocible. Datos crudos: {data[:40]!r}...")
        ncols = len(fields)
        nrows = len(data) // ncols
        shown = min(nrows, max_rows)
        lines = [" | ".join(fields)]
        for r in range(shown):
            lines.append(" | ".join(data[r * ncols:(r + 1) * ncols]))
        suffix = "" if shown == nrows else f"\n... ({nrows - shown} fila(s) mas)"
        return f"'{table_key}': {nrows} fila(s) x {ncols} campo(s)\n" + "\n".join(lines) + suffix

    @com_call
    def set_table_data(self, table_key: str, fields: list[str],
                       rows: list[list[str]]) -> str:
        """Escribe filas en una tabla del modelo y aplica los cambios.

        Reemplaza el contenido de la tabla. Para editar (p.ej. los ejes en
        "Grid Definitions - Grid Lines"), lea primero con get_table_data,
        modifique las filas y escriba el conjunto completo.

        Args:
            table_key: clave exacta de la tabla.
            fields: nombres de campo, en el orden de las filas.
            rows: lista de filas; cada fila, una lista de strings del mismo
                  largo que fields.
        """
        if not fields or not rows:
            raise EtabsError("Debe indicar fields y al menos una fila.")
        flat: list[str] = []
        for i, row in enumerate(rows):
            if len(row) != len(fields):
                raise EtabsError(
                    f"La fila {i} tiene {len(row)} valores; "
                    f"se esperaban {len(fields)}.")
            flat.extend("" if v is None else str(v) for v in row)

        model = self._model()

        # TableVersion es [in,out] y ETABS lo usa para verificar que se
        # escribe contra el mismo esquema que se leyo. Pasar un literal (1 o
        # 0, como hacia la version anterior) hace que rechace la escritura con
        # ret=1 sin ningun mensaje: reproducido el 2026-08-07 sobre
        # "Story Definitions" con los 8 campos correctos. La version real solo
        # se obtiene de GetTableForEditingArray, que hay que llamar antes.
        table_version = None
        try:
            r0 = oapi.call(
                model.DatabaseTables,
                [
                    ("GetTableForEditingArray", (table_key, "", 0, [], 0, [])),
                    ("GetTableForEditingArray", (table_key, "")),
                    ("GetTableForEditingArray", (table_key, "", 0, [""], 0, [""])),
                ],
                f"lectura de la version de la tabla '{table_key}'",
            )
            # El primer [out] de GetTableForEditingArray es TableVersion.
            for v in oapi.outs(r0):
                if isinstance(v, int) and not isinstance(v, bool):
                    table_version = v
                    break
        except Exception as e:
            logger.warning("No se pudo leer TableVersion de '%s' (%s); "
                           "se intentara con valores literales.", table_key, e)

        variants = []
        if table_version is not None:
            variants.append(
                ("SetTableForEditingArray",
                 (table_key, table_version, list(fields), len(rows), flat)))
        # Respaldo con literales por si GetTableForEditingArray no esta
        # disponible; se sabe que suelen fallar, van al final.
        variants += [
            ("SetTableForEditingArray",
             (table_key, 1, list(fields), len(rows), flat)),
            ("SetTableForEditingArray",
             (table_key, 0, list(fields), len(rows), flat)),
        ]
        oapi.call(model.DatabaseTables, variants,
                  f"escritura de la tabla '{table_key}'")
        result = oapi.call(
            model.DatabaseTables,
            [
                ("ApplyEditedTables", (True,)),
                ("ApplyEditedTables", (True, 0, 0, 0, 0, "")),
            ],
            "aplicacion de tablas editadas",
        )
        out = oapi.outs(result)
        ints = [v for v in out if isinstance(v, int) and not isinstance(v, bool)]
        logs = [v for v in out if isinstance(v, str) and v.strip()]
        fatal = ints[0] if ints else 0
        msg = f"Tabla '{table_key}' escrita: {len(rows)} fila(s)."
        if fatal:
            msg += f" ATENCION: {fatal} error(es) fatal(es) al aplicar."
        if logs:
            msg += f" Log: {logs[0][:500]}"
        return msg

    # ------------------------------------------------------------------
    # Lectores de definiciones (PLAN-MEJORAS 1.4)
    # ------------------------------------------------------------------
    # Existen porque el protocolo R01..R10 demostro que sin releer lo escrito
    # no se detectan los fallos silenciosos: el mensaje de una herramienta
    # dice lo que ella creo, no lo que hay en el modelo (patrones Dead/Live
    # de plantilla, diafragma D1 preexistente, losa Slab1 por defecto). Las
    # tablas de definicion de casos/combos/funciones ademas no devuelven
    # filas por GetTableForDisplayArray, asi que el getter dedicado es la
    # UNICA via. Todas las firmas de esta seccion se leyeron del typelib con
    # describe_oapi el 2026-08-07 (no de la documentacion de CSI).

    @com_call
    def _name_list(self, owner: Any, what: str) -> list[str]:
        """GetNameList generico: (NumberNames, MyName[], ret)."""
        r = oapi.call(owner, [("GetNameList", ())], what)
        names = oapi.find_str_list(r)
        return names or []

    @com_call
    def get_load_patterns(self) -> str:
        """Lista los patrones de carga con tipo y multiplicador de peso propio.

        Marca los patrones con peso propio != 0: mas de uno casi siempre es un
        error (en R05 la plantilla de ETABS traia 'Dead' con multiplicador 1
        ademas del 'D' del protocolo -- masa sismica duplicada en silencio).
        """
        model = self._model()
        names = self._name_list(model.LoadPatterns, "listado de patrones")
        if not names:
            return "Sin patrones de carga definidos."
        type_names = {1: "muerta", 2: "supermuerta", 3: "viva",
                      4: "viva_reducible", 5: "sismo", 6: "viento",
                      7: "nieve", 8: "otra", 11: "viva_techo"}
        lines = []
        with_sw = []
        for nm in names:
            # GetLoadType(Name) -> (MyType, ret); GetSelfWTMultiplier -> (SW, ret)
            t = oapi.call(model.LoadPatterns, [("GetLoadType", (nm,))],
                          f"tipo del patron '{nm}'")
            sw = oapi.call(model.LoadPatterns, [("GetSelfWTMultiplier", (nm,))],
                           f"peso propio del patron '{nm}'")
            t_val = oapi.outs(t)[0] if oapi.outs(t) else -1
            sw_val = oapi.outs(sw)[0] if oapi.outs(sw) else 0.0
            if sw_val:
                with_sw.append(nm)
            lines.append(f"{nm}: tipo {type_names.get(t_val, t_val)}, "
                         f"peso propio x{sw_val:g}")
        header = f"{len(names)} patron(es):"
        if len(with_sw) > 1:
            header += (f"\nAVISO: {len(with_sw)} patrones con peso propio != 0 "
                       f"({', '.join(with_sw)}). El peso propio se contaria "
                       f"varias veces en combinaciones y masa sismica.")
        elif not with_sw:
            header += "\nAVISO: ningun patron tiene peso propio. La carga muerta propia sera 0."
        return header + "\n" + "\n".join(lines)

    @com_call
    def get_load_combos(self) -> str:
        """Lista las combinaciones con sus casos y factores.

        GetCaseList(Name) -> (NumberItems, CNameType[], CName[], SF[], ret).
        CNameType 0 = caso de carga, 1 = otra combinacion.
        """
        model = self._model()
        names = self._name_list(model.RespCombo, "listado de combinaciones")
        if not names:
            return "Sin combinaciones definidas."
        lines = []
        for nm in names:
            r = oapi.call(model.RespCombo, [("GetCaseList", (nm,))],
                          f"casos de la combinacion '{nm}'")
            out = oapi.outs(r)
            # out = (NumberItems, CNameType[], CName[], SF[])
            cases = oapi.find_str_list(r) or []
            nums = [list(v) for v in out
                    if isinstance(v, (tuple, list)) and v
                    and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                            for x in v)]
            # SF es la lista numerica con decimales; CNameType es entera.
            sf = None
            for cand in nums:
                if any(not float(x).is_integer() for x in cand):
                    sf = cand
                    break
            if sf is None and nums:
                sf = nums[-1]
            if cases and sf and len(cases) == len(sf):
                terms = " + ".join(f"{f:g}{c}" for c, f in zip(cases, sf))
            else:
                terms = f"(ilegible: {len(cases)} casos, sf={sf})"
            lines.append(f"{nm} = {terms}")
        return f"{len(names)} combinacion(es):\n" + "\n".join(lines)

    @com_call
    def get_spectrum(self, name: str) -> str:
        """Devuelve los puntos (T, Sa) de una funcion de espectro de respuesta.

        Usa Func.GetValues, el lector GENERICO de funciones (documentado en
        el CHM de ETABS y verificado en runtime el 2026-08-07 sobre
        CDCRD-SD). FuncRS.GetUser/SetUser NO existen en la OAPI de ETABS:
        pertenecen a la superficie unificada CSiAPIv1 (SAP2000) y ETABS los
        stubbea con ret=-99 — ese era el "-99 de causa no determinada" de
        R06. Los arrays de GetValues llegan con n+1 elementos y el [0] es
        relleno. El amortiguamiento no viene en GetValues; esta en la tabla
        'Functions - Response Spectrum - User Defined'.
        """
        model = self._model()
        r = oapi.call(model.Func, [("GetValues", (name,))],
                      f"lectura de la funcion '{name}'")
        out = oapi.outs(r)
        n = next((v for v in out
                  if isinstance(v, int) and not isinstance(v, bool)), 0)
        num_lists = [list(v) for v in out
                     if isinstance(v, (tuple, list)) and v
                     and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                             for x in v)]
        if len(num_lists) < 2:
            return f"Funcion '{name}': sin puntos legibles ({out!r})."
        periods, values = num_lists[0], num_lists[1]
        if n and len(periods) == n + 1:
            periods, values = periods[1:], values[1:]
        lines = [f"T={t:<10.6f} Sa={a:.6f}" for t, a in zip(periods, values)]
        return (f"Funcion '{name}': {len(periods)} punto(s)\n"
                + "\n".join(lines))

    @com_call
    def get_materials(self) -> str:
        """Lista los materiales con tipo, peso por unidad de volumen y f'c/fy.

        Un material con W=0 es el defecto silencioso mas peligroso detectado
        en la auditoria: el peso propio no genera carga y el analisis corre
        sin error. Este lector lo marca explicitamente.
        """
        model = self._model()
        names = self._name_list(model.PropMaterial, "listado de materiales")
        if not names:
            return "Sin materiales definidos."
        type_names = {1: "acero", 2: "hormigon", 3: "sin diseño", 4: "aluminio",
                      5: "conformado en frio", 6: "refuerzo", 7: "tendon",
                      8: "mamposteria"}
        lines = []
        sin_peso = []
        for nm in names:
            t = oapi.call(model.PropMaterial, [("GetMaterial", (nm,))],
                          f"tipo del material '{nm}'")
            t_val = oapi.outs(t)[0] if oapi.outs(t) else -1
            w = oapi.call(model.PropMaterial, [("GetWeightAndMass", (nm,))],
                          f"peso del material '{nm}'")
            w_out = oapi.outs(w)
            w_val = w_out[0] if w_out else 0.0
            extra = ""
            # f'c para hormigon, fy para acero; tolerante si el material no
            # tiene esos datos (p.ej. 'sin diseño').
            try:
                if t_val == 2:
                    fc = oapi.call(model.PropMaterial, [("GetOConcrete_1", (nm,))],
                                   f"f'c de '{nm}'")
                    fc_val = oapi.outs(fc)[0] if oapi.outs(fc) else None
                    if fc_val is not None:
                        extra = f", f'c={fc_val:g}"
                elif t_val == 1:
                    fy = oapi.call(model.PropMaterial, [("GetOSteel_1", (nm,))],
                                   f"fy de '{nm}'")
                    fy_val = oapi.outs(fy)[0] if oapi.outs(fy) else None
                    if fy_val is not None:
                        extra = f", fy={fy_val:g}"
            except Exception:
                pass
            marca = "" if w_val else "  <-- SIN PESO"
            if not w_val:
                sin_peso.append(nm)
            lines.append(f"{nm}: {type_names.get(t_val, t_val)}, "
                         f"w={w_val:g}{extra}{marca}")
        header = f"{len(names)} material(es):"
        if sin_peso:
            header += (f"\nAVISO: {len(sin_peso)} material(es) sin peso por "
                       f"unidad de volumen ({', '.join(sin_peso)}): su peso "
                       f"propio no genera carga.")
        return header + "\n" + "\n".join(lines)

    @com_call
    def get_frame_sections(self) -> str:
        """Lista las secciones de frame; para rectangulares, dimensiones y material.

        GetRectangle(Name) -> (FileName, MatProp, T3, T2, Color, Notes, GUID,
        ret). Las no rectangulares se listan por nombre (leer sus datos exige
        el getter de su tipo; fuera del alcance de esta tanda).
        """
        model = self._model()
        names = self._name_list(model.PropFrame, "listado de secciones de frame")
        if not names:
            return "Sin secciones de frame definidas."
        lines = []
        for nm in names:
            try:
                r = oapi.call(model.PropFrame, [("GetRectangle", (nm,))],
                              f"seccion '{nm}'")
                out = oapi.outs(r)
                strs = [v for v in out if isinstance(v, str)]
                nums = [v for v in out
                        if isinstance(v, float) and not isinstance(v, bool)]
                mat = strs[1] if len(strs) > 1 else "?"
                if len(nums) >= 2:
                    lines.append(f"{nm}: rectangular {nums[0]:g} x {nums[1]:g} "
                                 f"(t3 x t2), material '{mat}'")
                    continue
            except Exception:
                pass
            lines.append(f"{nm}: (no rectangular; datos no leidos)")
        return f"{len(names)} seccion(es) de frame:\n" + "\n".join(lines)

    @com_call
    def get_area_sections(self) -> str:
        """Lista las secciones de area (losas/muros) con material y espesor.

        PropArea.GetSlab(Name) -> (SlabType, ShellType, MatProp, Thickness,
        Color, Notes, GUID, ret). Es el lector que falto en R10: el espesor
        real de 'Slab1' (la propiedad por defecto de ETABS) hubo que deducirlo
        de las reacciones en vez de leerlo.
        """
        model = self._model()
        names = self._name_list(model.PropArea, "listado de secciones de area")
        if not names:
            return "Sin secciones de area definidas."
        lines = []
        for nm in names:
            try:
                r = oapi.call(model.PropArea, [("GetSlab", (nm,))],
                              f"losa '{nm}'")
                out = oapi.outs(r)
                strs = [v for v in out if isinstance(v, str)]
                floats = [v for v in out
                          if isinstance(v, float) and not isinstance(v, bool)]
                mat = strs[0] if strs else "?"
                thick = floats[0] if floats else None
                if thick is not None:
                    lines.append(f"{nm}: losa, espesor {thick:g}, material '{mat}'")
                    continue
            except Exception:
                pass
            lines.append(f"{nm}: (no es losa o datos no leidos)")
        return f"{len(names)} seccion(es) de area:\n" + "\n".join(lines)

    @com_call
    def get_diaphragms(self) -> str:
        """Lista los diafragmas definidos y su rigidez."""
        model = self._model()
        names = self._name_list(model.Diaphragm, "listado de diafragmas")
        if not names:
            return "Sin diafragmas definidos."
        lines = []
        for nm in names:
            r = oapi.call(model.Diaphragm, [("GetDiaphragm", (nm,))],
                          f"diafragma '{nm}'")
            out = oapi.outs(r)
            semi = bool(out[0]) if out else False
            lines.append(f"{nm}: {'semirrigido' if semi else 'rigido'}")
        return f"{len(names)} diafragma(s):\n" + "\n".join(lines)

    @com_call
    def get_restraints(self) -> str:
        """Lista los puntos con apoyo y sus grados restringidos.

        PointObj.GetRestraint(Name) -> (Value: bool[6], ret) con el orden
        UX, UY, UZ, RX, RY, RZ. Solo se reportan los puntos con al menos un
        grado restringido.
        """
        model = self._model()
        points = self._read_points()
        dof = ("UX", "UY", "UZ", "RX", "RY", "RZ")
        lines = []
        for p in points:
            try:
                r = oapi.call(model.PointObj, [("GetRestraint", (p.id,))],
                              f"apoyo del punto {p.id}")
            except Exception:
                continue
            vals = None
            for v in oapi.outs(r):
                if isinstance(v, (tuple, list)) and len(v) == 6:
                    vals = [bool(x) for x in v]
                    break
            if not vals or not any(vals):
                continue
            fijos = ",".join(d for d, f in zip(dof, vals) if f)
            tipo = "empotrado" if all(vals) else f"restringido ({fijos})"
            lines.append(f"punto {p.id} (z={p.zs[0]:g}): {tipo}")
        if not lines:
            return "Ningun punto tiene apoyo asignado."
        return f"{len(lines)} punto(s) con apoyo:\n" + "\n".join(lines)

    def get_modal_results(self) -> str:
        """Periodos, frecuencias y masa participante tras el analisis.

        Lee las tablas de resultados (que si devuelven filas, verificado en
        R08); no requiere metodo OAPI dedicado.
        """
        parts = [self.get_table_data("Modal Periods And Frequencies", 30)]
        try:
            parts.append(self.get_table_data("Modal Participating Mass Ratios", 30))
        except Exception as e:
            parts.append(f"(Masa participante no disponible: {e})")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Borrado de definiciones (PLAN-MEJORAS 1.2)
    # ------------------------------------------------------------------

    # Rutas verificadas contra el typelib el 2026-08-07 (todas con la firma
    # Delete(Name) -> ret). El dict mapea alias en español e ingles.
    _DELETE_KINDS = {
        "load_case": ("LoadCases", "caso de carga"),
        "caso": ("LoadCases", "caso de carga"),
        "load_pattern": ("LoadPatterns", "patron de carga"),
        "patron": ("LoadPatterns", "patron de carga"),
        "combo": ("RespCombo", "combinacion"),
        "combinacion": ("RespCombo", "combinacion"),
        "function": ("Func", "funcion"),
        "funcion": ("Func", "funcion"),
        "material": ("PropMaterial", "material"),
        "frame_section": ("PropFrame", "seccion de frame"),
        "seccion_frame": ("PropFrame", "seccion de frame"),
        "area_section": ("PropArea", "seccion de area"),
        "seccion_area": ("PropArea", "seccion de area"),
        "diaphragm": ("Diaphragm", "diafragma"),
        "diafragma": ("Diaphragm", "diafragma"),
    }

    @com_call
    def delete_definition(self, kind: str, name: str) -> str:
        """Borra una definicion del modelo (caso, patron, combinacion, funcion,
        material, seccion o diafragma).

        Complementa a delete_object, que solo cubre geometria. Sin esto, los
        objetos de prueba quedaban permanentes (ZZ_TEST_ESCRITURA y
        ZZ_TEST_FUNC en la corrida del 2026-08-07 hubo que borrarlos a mano).

        Args:
            kind: "load_case", "load_pattern", "combo", "function",
                  "material", "frame_section", "area_section" o "diaphragm"
                  (tambien alias en español: "caso", "patron", "combinacion",
                  "funcion", "seccion_frame", "seccion_area", "diafragma").
            name: nombre exacto de la definicion.
        """
        key = kind.strip().lower()
        if key not in self._DELETE_KINDS:
            raise EtabsError(
                f"Tipo '{kind}' no reconocido. Opciones: "
                + ", ".join(sorted(set(self._DELETE_KINDS)))
            )
        ns_name, label = self._DELETE_KINDS[key]
        model = self._model()
        owner = getattr(model, ns_name)
        oapi.call(owner, [("Delete", (name,))],
                  f"borrado de {label} '{name}'")
        return f"{label.capitalize()} '{name}' borrado."

    # ------------------------------------------------------------------
    # Diafragmas
    # ------------------------------------------------------------------

    @com_call
    def set_rigid_diaphragm(self, name: str, elevation: float,
                            semi_rigid: bool = False) -> str:
        """Define un diafragma y lo asigna a todos los puntos de una cota.

        Args:
            name: nombre del diafragma, ej. "D1".
            elevation: cota Z de los puntos a incluir, ej. 3.0.
            semi_rigid: False = rigido (lo usual para losas macizas).
        """
        model = self._model()
        oapi.call(model.Diaphragm,
                  [("SetDiaphragm", (name, bool(semi_rigid)))],
                  f"definicion del diafragma '{name}'")

        points = self._read_points()
        TOL = 1e-6
        targets = [p for p in points if abs(p.zs[0] - elevation) < TOL]
        if not targets:
            raise EtabsError(
                f"No hay puntos en Z={elevation:g}. Cotas presentes: "
                f"{sorted({round(p.zs[0], 4) for p in points})}")
        for p in targets:
            oapi.call(
                model.PointObj,
                [("SetDiaphragm", (p.id, 3, name)),
                 ("SetDiaphragm", (p.id, 3, name, 0))],
                f"diafragma en el punto {p.id}",
            )
        kind = "semirrigido" if semi_rigid else "rigido"
        return (f"Diafragma {kind} '{name}' asignado a {len(targets)} "
                f"punto(s) en Z={elevation:g}.")

    # ------------------------------------------------------------------
    # Cargas en areas
    # ------------------------------------------------------------------

    @com_call
    def assign_area_uniform_load(self, load_pattern: str, value: float,
                                 direction: int = 10,
                                 replace: bool = True,
                                 elevation: float | None = None,
                                 elevations: list[float] | None = None,
                                 tolerance: float = 1e-6) -> str:
        """Aplica carga uniforme a las areas (losas) del modelo.

        Sin filtro de elevacion carga TODAS las areas. Para diferenciar
        niveles (carga viva de oficinas en los pisos intermedios, carga de
        techo solo en la cubierta) use elevation o elevations: solo se cargan
        las areas cuyos vertices esten todos en la(s) cota(s) indicada(s).

        Args:
            load_pattern: patron ya creado, ej. "D", "L" o "Lr".
            value: magnitud por unidad de area (con kN, m: kN/m2).
                   Positiva hacia abajo si direction=10.
            direction: 10 = gravedad.
            replace: True reemplaza cargas previas del mismo patron.
            elevation: cota Z unica a cargar, ej. 9.0 para el techo.
            elevations: varias cotas, ej. [3.0, 6.0] para los niveles
                        intermedios. Tiene prioridad sobre elevation.
            tolerance: holgura para comparar cotas.
        """
        model = self._model()
        areas = self._read_areas()
        if not areas:
            raise EtabsError(
                "El modelo no contiene areas (losas/muros). Cree las losas "
                "primero o use assign_frame_distributed_load para cargar vigas.")

        targets = areas
        wanted: list[float] | None = None
        if elevations:
            wanted = [float(z) for z in elevations]
        elif elevation is not None:
            wanted = [float(elevation)]

        if wanted is not None:
            targets = [a for a in areas
                       if all(any(abs(z - w) < tolerance for w in wanted)
                              for z in a.zs)]
            if not targets:
                present = sorted({round(z, 4) for a in areas for z in a.zs})
                raise EtabsError(
                    f"Ninguna area en la(s) cota(s) {wanted}. "
                    f"Cotas presentes en las areas: {present}")

        for a in targets:
            oapi.call(
                model.AreaObj,
                [("SetLoadUniform",
                  (a.id, load_pattern, float(value), direction,
                   bool(replace), "Global", 0))],
                f"carga uniforme en el area {a.id}",
            )
        scope = (f" en Z={wanted}" if wanted is not None
                 else " (todas las areas)")
        return (f"Carga {value:g} aplicada en el patron '{load_pattern}' "
                f"a {len(targets)} de {len(areas)} area(s){scope}.")

    # ------------------------------------------------------------------
    # Espectro de diseño CDCRD y caso de espectro de respuesta
    # ------------------------------------------------------------------

    @com_call
    def define_cdcrd_spectrum(self, name: str, SDS: float, SD1: float,
                              campo_cercano: bool = False,
                              damping: float = 0.05,
                              t_max: float = 4.0) -> str:
        """Define la funcion de espectro de diseño del CDCRD (cl. 2.9.4.4).

        Forma normal (Figura 7): Sa = SDS*(0.4 + 0.6*T/T0) hasta T0, meseta
        SDS hasta Ts, luego SD1/T. Campo cercano (Figura 8): meseta SDS desde
        T=0. Los valores estan en fraccion de g; al crear el caso de espectro
        use un factor de escala igual a g en las unidades del modelo
        (9.80665 con kN, m).

        Args:
            name: nombre de la funcion, ej. "CDCRD-SD".
            SDS: aceleracion espectral de diseño en periodo corto (g).
            SD1: aceleracion espectral de diseño en T=1s (g).
            campo_cercano: True si el sitio esta a <= 5 km de las fallas de
                           la Figura 6 del CDCRD (usa SDS=SMS, SD1=SM1).
            damping: razon de amortiguamiento, 0.05 por defecto.
            t_max: periodo final de la rama descendente.
        """
        if SDS <= 0 or SD1 <= 0:
            raise EtabsError("SDS y SD1 deben ser positivos.")
        Ts = SD1 / SDS
        T0 = 0.2 * Ts
        if Ts >= t_max:
            raise EtabsError(
                f"Ts={Ts:.4f}s >= t_max={t_max}s: el espectro quedaria sin "
                f"rama descendente. Aumente t_max.")

        points: list[tuple[float, float]] = []
        if campo_cercano:
            points.append((0.0, SDS))
        else:
            points.append((0.0, 0.4 * SDS))
            points.append((round(T0, 6), SDS))
        points.append((round(Ts, 6), SDS))

        T = Ts
        while T < t_max:
            T = min(round(T * 1.25, 6), t_max)
            points.append((T, round(SD1 / T, 6)))

        model = self._model()

        # SetUser NO existe en la OAPI de ETABS: cFunctionRS (typelib
        # ETABSv1 y CHM v23) solo tiene NTC2008/2018. El SetUser dispid 50
        # que se invoco en R06 pertenece a la superficie unificada CSiAPIv1
        # (SAP2000) y ETABS lo stubbea con ret=-99, igual que GetUser. La
        # via soportada es la tabla interactiva (ImportType=2), la misma
        # que funciono como rodeo en R06 — con verificacion al final.
        key = "Functions - Response Spectrum - User Defined"

        # La escritura reemplaza la tabla COMPLETA: conservar las filas de
        # otras funciones usuario y descubrir el esquema real en runtime.
        fields: list[str] = ["Name", "Period", "Value", "Damping"]
        old_rows: list[list[str]] = []
        try:
            r0 = oapi.call(
                model.DatabaseTables,
                [("GetTableForEditingArray", (key, "", 0, [], 0, []))],
                f"esquema de '{key}'")
            out = oapi.outs(r0)
            str_lists = [list(v) for v in out
                         if isinstance(v, (tuple, list)) and v
                         and all(isinstance(x, str) for x in v)]
            ints = [v for v in out
                    if isinstance(v, int) and not isinstance(v, bool)]
            if len(str_lists) >= 2 and ints and ints[-1] > 0:
                fields = str_lists[0]
                data, n_rec = str_lists[-1], ints[-1]
                if len(data) % n_rec == 0:
                    ncols = len(data) // n_rec
                    filas = [data[i * ncols:(i + 1) * ncols]
                             for i in range(n_rec)]
                    i_nm = next((i for i, f in enumerate(fields)
                                 if "name" in f.lower()), 0)
                    old_rows = [f for f in filas if f[i_nm] != name]
        except Exception as e:
            logger.info("Tabla '%s' sin contenido previo legible (%s).",
                        key, e)

        def _fila(t: float, a: float) -> list[str]:
            # :.10g para no recortar el septimo digito significativo de los
            # periodos (con :g, 1.034431 se escribia como 1.03443).
            fila = []
            for f in fields:
                fl = f.lower()
                if "name" in fl:
                    fila.append(name)
                elif "period" in fl:
                    fila.append(f"{t:.10g}")
                elif "damp" in fl:
                    fila.append(f"{float(damping):.10g}")
                elif "value" in fl or "accel" in fl:
                    fila.append(f"{a:.10g}")
                else:
                    fila.append("")
            return fila

        self.set_table_data(key, list(fields),
                            old_rows + [_fila(t, a) for t, a in points])

        # Releer con el getter y comparar: la regla que dejo esta corrida
        # ("el mensaje dice lo que la herramienta creo, no lo que hay en el
        # modelo").
        chk = oapi.call(model.Func, [("GetValues", (name,))],
                        f"verificacion del espectro '{name}'")
        n_chk = next((v for v in oapi.outs(chk)
                      if isinstance(v, int) and not isinstance(v, bool)), -1)
        if n_chk != len(points):
            raise EtabsError(
                f"El espectro '{name}' quedo con {n_chk} punto(s); se "
                f"escribieron {len(points)}. Revise la tabla '{key}'.")
        return (f"Espectro '{name}' definido: {len(points)} puntos, "
                f"T0={T0:.4f}s, Ts={Ts:.4f}s, meseta Sa={SDS:g}g"
                f"{' (campo cercano)' if campo_cercano else ''}. "
                f"Valores en g: escale por 9.80665 al crear el caso (kN, m).")

    @com_call
    def add_response_spectrum_case(self, name: str, spectrum: str,
                                   direction: str = "X",
                                   scale: float = 9.80665) -> str:
        """Crea un caso de analisis de espectro de respuesta.

        Args:
            name: nombre del caso, ej. "Ex".
            spectrum: funcion de espectro ya definida (define_cdcrd_spectrum).
            direction: "X", "Y" o "Z".
            scale: factor de escala. Si el espectro esta en g y el modelo en
                   kN, m: 9.80665. Con otras unidades, el valor de g en esas
                   unidades.
        """
        u = {"x": "U1", "y": "U2", "z": "U3"}.get(direction.strip().lower())
        if u is None:
            raise EtabsError(f"Direccion no valida: '{direction}'. Use X, Y o Z.")
        model = self._model()
        rs = model.LoadCases.ResponseSpectrum
        oapi.call(rs, [("SetCase", (name,))],
                  f"creacion del caso de espectro '{name}'")
        oapi.call(
            rs,
            [
                ("SetLoads", (name, 1, [u], [spectrum], [float(scale)],
                              ["Global"], [0.0])),
                ("SetLoads", (name, 1, [u], [spectrum], [float(scale)],
                              ["Global"], [0.0], [0.0])),
            ],
            f"cargas del caso de espectro '{name}'",
        )
        return (f"Caso de espectro '{name}' creado: funcion '{spectrum}', "
                f"direccion {u}, escala {scale:g}.")

    # ------------------------------------------------------------------
    # Casos no lineales, P-Delta, time-history
    # ------------------------------------------------------------------
    # Mas riesgo de desalineacion de firma que el resto: LoadCases.StaticNonlinear
    # y .ModHistoryNonlinear tienen varias variantes segun version de ETABS.
    # oapi.call() garantiza que si la firma no coincide, falla con detalle en
    # vez de correr con argumentos desalineados; aun asi, verifique con
    # describe_oapi(path="LoadCases.StaticNonlinear") antes de usar en un
    # modelo de produccion.

    @com_call
    def add_pdelta_case(self, name: str, base_case: str = "Dead",
                        load_pattern: str = "", scale: float = 1.0) -> str:
        """Crea un caso estatico no lineal para P-Delta (cargas verticales).

        Este caso se usa luego como caso inicial ("P-Delta previo") de los
        casos de espectro de respuesta, para que el analisis sismico incluya
        el efecto P-Delta de las cargas gravitacionales.

        Args:
            name: nombre del caso, ej. "PDELTA".
            base_case: caso estatico existente del que copiar parametros
                       generales (normalmente el de carga muerta).
            load_pattern: patron de carga a aplicar en este caso, ej. "D".
                          Vacio = no agrega carga (util si solo se necesita
                          el caso como referencia para no linealidad geometrica).
            scale: factor de escala del patron de carga.
        """
        model = self._model()
        snl = model.LoadCases.StaticNonlinear
        oapi.call(snl, [("SetCase", (name,))], f"creacion del caso '{name}'")
        oapi.call(
            snl,
            [("SetGeometricNonlinearity", (name, 1)),
             ("SetGeometricNonlinearity", (name, 2))],
            f"no linealidad geometrica (P-Delta) en '{name}'",
        )
        if load_pattern:
            oapi.call(
                snl,
                [("SetLoads", (name, 1, "Load", [load_pattern], [float(scale)])),
                 ("SetLoads", (name, 1, ["Load"], [load_pattern], [float(scale)]))],
                f"cargas del caso '{name}'",
            )
        return (f"Caso P-Delta '{name}' creado (no linealidad geometrica activa)"
                + (f", carga '{load_pattern}' x{scale:g}." if load_pattern else "."))

    @com_call
    def add_nonlinear_static_case(self, name: str, load_pattern: str,
                                  scale: float = 1.0,
                                  initial_case: str = "") -> str:
        """Crea un caso estatico no lineal general (pushover simplificado, etc.).

        Args:
            name: nombre del caso.
            load_pattern: patron de carga a aplicar monotonicamente.
            scale: factor de escala.
            initial_case: caso del que parte (ej. el de P-Delta gravitacional
                          creado con add_pdelta_case). Vacio = parte de cero.
        """
        model = self._model()
        snl = model.LoadCases.StaticNonlinear
        oapi.call(snl, [("SetCase", (name,))], f"creacion del caso '{name}'")
        if initial_case:
            oapi.call(
                snl,
                [("SetInitialCase", (name, initial_case))],
                f"caso inicial de '{name}'",
            )
        oapi.call(
            snl,
            [("SetLoads", (name, 1, "Load", [load_pattern], [float(scale)])),
             ("SetLoads", (name, 1, ["Load"], [load_pattern], [float(scale)]))],
            f"cargas del caso '{name}'",
        )
        return (f"Caso no lineal '{name}' creado: carga '{load_pattern}' x{scale:g}"
                + (f", inicial '{initial_case}'." if initial_case else "."))

    @com_call
    def add_time_history_case(self, name: str, function_name: str,
                              load_pattern: str = "U1", scale: float = 1.0,
                              nonlinear: bool = False,
                              time_step: float = 0.02,
                              n_steps: int = 1500) -> str:
        """Crea un caso de historia en el tiempo (sismo registrado).

        Requiere una funcion de time-history ya importada o definida en
        ETABS (no la crea este metodo). Verifique el nombre exacto en la
        interfaz o con list_tables antes de llamar.

        Args:
            name: nombre del caso.
            function_name: funcion de time-history ya existente en el modelo.
            load_pattern: direccion de aplicacion: "U1", "U2" o "U3".
            scale: factor de escala de la funcion.
            nonlinear: False = lineal modal; True = no lineal directo.
            time_step: paso de tiempo de salida.
            n_steps: numero de pasos de salida.
        """
        if load_pattern not in ("U1", "U2", "U3"):
            raise EtabsError("load_pattern debe ser U1, U2 o U3.")
        model = self._model()
        th = (model.LoadCases.ModHistoryNonlinear if nonlinear
              else model.LoadCases.ModHistoryLinear)
        oapi.call(th, [("SetCase", (name,))], f"creacion del caso '{name}'")
        oapi.call(
            th,
            [("SetLoads", (name, 1, "Accel", [load_pattern], [function_name],
                          [float(scale)], [0.0], ["Global"], [0])),
             ("SetLoads", (name, 1, ["Accel"], [load_pattern], [function_name],
                          [float(scale)], [0.0]))],
            f"cargas del caso '{name}'",
        )
        oapi.call(
            th,
            [("SetTimeStep", (name, int(n_steps), float(time_step)))],
            f"paso de tiempo de '{name}'",
        )
        kind = "no lineal" if nonlinear else "lineal modal"
        return (f"Caso time-history {kind} '{name}' creado: funcion "
                f"'{function_name}' en {load_pattern} x{scale:g}, "
                f"{n_steps} pasos de {time_step:g}s.")

    # ------------------------------------------------------------------
    # Diseño de hormigon
    # ------------------------------------------------------------------

    @com_call
    def run_concrete_design(self, code: str = "") -> str:
        """Ejecuta el diseño de hormigon armado. Requiere analisis previo.

        Args:
            code: codigo de diseño a fijar antes, ej. "ACI 318-19".
                  Vacio = usar el codigo ya configurado en el modelo.
        """
        model = self._model()
        if code:
            oapi.call(model.DesignConcrete, [("SetCode", (code,))],
                      f"seleccion del codigo '{code}'")
        oapi.call(model.DesignConcrete, [("StartDesign", ())],
                  "diseño de hormigon")
        return ("Diseño de hormigon ejecutado"
                + (f" con codigo '{code}'." if code else "."))

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
