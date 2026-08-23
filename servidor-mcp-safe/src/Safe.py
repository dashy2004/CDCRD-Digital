# SAFE MCP - v0.1.0 (primera version, NO verificada contra una instalacion
# real de SAFE: esta sesion no tuvo Windows ni SAFE disponibles).
#
# Interfaz Python <-> SAFE via COM (CSI OAPI). Estructura y disciplina de
# invocacion COPIADAS deliberadamente de servidor-mcp/src/Etabs.py (mismo
# autor de facto: mismo patron de conexion perezosa, mismo hilo COM dedicado
# via comthread.py, misma invocacion tolerante via oapi.call).
#
# LO QUE ESTA VERIFICADO (por el propio SOP de la firma, Pasos.pdf, seccion
# "Safe", paginas 23-51):
#   - SAFE importa un modelo desde ETABS via "Export > Story as SAFE F2K
#     File" (ETABS) seguido de "Import > SAFE .f2k Text File" (SAFE).
#   - SAFE tiene "Interactive Database Editing" (pag. 32): la misma
#     infraestructura de DatabaseTables que ya usa el servidor ETABS via
#     list_tables/get_table_data/set_table_data. Esto es la base mas segura
#     para las herramientas de este archivo, porque la tabla ya se sabe que
#     existe (se ve en el SOP), aunque el nombre exacto de tabla en la OAPI
#     no se haya confirmado todavia en esta instalacion.
#   - Los objetos de losa/zapata en SAFE tienen un "Slab Property Data" con
#     Type en {Slab, Drop, Footing, Stiff} (pag. 34, 45) y Thickness.
#   - El resorte de suelo es "Area Spring Property" con Subgrade Modulus
#     (pag. 37): k = 1.2 * sigma_admisible.
#   - Existen "Design Strips" (pag. 46) y resultados de presion de suelo y
#     punzonamiento (pag. 43-44) y export a DXF (pag. 49-50).
#
# LO QUE NO ESTA VERIFICADO (hay que confirmarlo en Windows con SAFE abierto,
# usando diagnose_safe.py y despues describe_oapi):
#   - El ProgID COM exacto de SAFE (ver _PROGID_CANDIDATES abajo).
#   - Los nombres exactos de metodo para Slab Property Data, Area Spring,
#     Design Strips, resultados de presion de suelo/punzonamiento y export
#     DXF. SAP2000/ETABS/SAFE comparten arquitectura de OAPI (PropMaterial,
#     PointObj, AreaObj, LoadPatterns, DatabaseTables son namespaces conocidos
#     y estables en toda la linea CSI), asi que esos SI se codifican con
#     confianza razonable. Los namespaces propios de SAFE (diseño de losa,
#     franjas, punzonamiento) se codifican con la MEJOR conjetura y quedan
#     marcados abajo; si fallan, describe_oapi(path="...") dice que existe
#     realmente en esta instalacion y se corrige.

import logging
import os
from typing import Any

import comtypes
import comtypes.client
from pydantic import BaseModel, Field

from comthread import com_call
import oapi

logger = logging.getLogger('safe_mcp_server')

# Candidatos de ProgID COM, en el orden en que se prueban. El primero sigue
# el patron documentado de CSI para el resto de su linea (ETABS:
# "CSI.ETABS.API.ETABSObject" / "ETABSv1.Helper"; SAP2000:
# "CSI.SAP2000.API.SapObject" / "SAP2000v1.Helper"). NINGUNO de estos se
# probo en esta sesion. diagnose_safe.py los prueba todos y reporta cual
# conecta; una vez confirmado, fijarlo en config.json (safe.prog_id /
# safe.helper_prog_id) para saltarse el sondeo.
_PROGID_CANDIDATES = [
    "CSI.SAFE.API.SapObject",
    "CSI.SAFE.API.SAFEObject",
    "CSI.SAFE.API.ETABSObject",
]
_HELPER_CANDIDATES = [
    "SAFEv1.Helper",
    "CSI.SAFE.API.Helper",
]

# eFileType, identificado EMPIRICAMENTE el 2026-08-10 con probe_file_types
# contra SAFE 23.3.0 (modelo vacio). El orden calca el menu File > Export:
#   1 = SAFE .f2k Text File   (formato TABLE, verificado leyendo el archivo)
#   2 = Database Tables to Excel (.xlsx)
#   3 = Database Tables to Access (.accdb)
#   4 = Database Tables to Text  (mismo formato TABLE, unidades N,mm)
#   5 = Database Tables to XML
#   0 y 6..20 devolvieron ret=0 SIN archivo con el modelo vacio.
#   RE-SONDEADO el 2026-08-10 con modelo poblado, analizado y disenado
#   (TORRE A (caso de prueba, 51 niveles), fundacion): 6..20 siguen devolviendo
#   ret=0 SIN producir archivo. CONCLUSION: el export a DXF NO es accesible
#   via File.ExportFile en esta version de la OAPI (cFile tiene 13 metodos,
#   ninguno DXF; el dialogo File > Export > Model as DXF de la interfaz no
#   tiene contraparte COM). ret=0 en 6..20 es un falso exito silencioso:
#   no usar esos codigos. El paso SAFE->AutoCAD (SOP 3.17) queda manual o
#   via la interfaz (computer use) hasta encontrar otra via.
FILE_TYPE_F2K = 1
FILE_TYPE_EXCEL = 2
FILE_TYPE_ACCESS = 3
FILE_TYPE_TEXT = 4
FILE_TYPE_XML = 5
FILE_TYPE_DXF = None  # NO EXISTE via ExportFile (sondeado 0-20, modelo poblado)

PRESET_UNITS = [
    "lb, in, F", "lb, ft, F", "kip, in, F", "kip, ft, F",
    "kN, mm, C", "kN, m, C", "kgf, mm, C", "kgf, m, C",
    "N, mm, C", "N, m, C", "Ton, mm, C", "Ton, m, C",
    "kN, cm, C", "kgf, cm, C", "N, cm, C", "Ton, cm, C",
]


class GeomObject(BaseModel):
    """Punto o area (losa/zapata) definido por coordenadas."""
    type: str = Field(description='Tipo: "point" o "surface".')
    xs: list[float] = Field(description="Coordenadas X.")
    ys: list[float] = Field(description="Coordenadas Y.")
    zs: list[float] = Field(description="Coordenadas Z.")
    id: str = Field(default="", description="ID del objeto.")


class SafeError(RuntimeError):
    """Fallo de conexion u operacion en SAFE. FastMCP lo convierte en isError."""


class Safe:
    def __init__(self, auto_start: bool = False, exe_path: str = "",
                 prog_id: str = "", helper_prog_id: str = ""):
        self.SapModel = None
        self._safe_object = None
        self.auto_start = auto_start
        self.exe_path = exe_path
        self.version_string = "desconocida"
        self._prog_id_used = ""
        # Si config.json ya trae un ProgID confirmado, se prueba primero y
        # unico; si no, se sondea la lista completa de candidatos.
        self._prog_id_list = [prog_id] if prog_id else list(_PROGID_CANDIDATES)
        self._helper_list = [helper_prog_id] if helper_prog_id else list(_HELPER_CANDIDATES)
        # Conexion perezosa: el servidor debe poder arrancar aunque SAFE
        # todavia no este abierto.

    # ------------------------------------------------------------------
    # Conexion
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """Se ejecuta SIEMPRE dentro del hilo COM dedicado."""
        if self.SapModel is not None:
            try:
                self.SapModel.GetModelFilename()
                return
            except Exception as e:
                logger.warning("Referencia a SAFE invalida (%s). Reconectando.", e)
                self.SapModel = None
                self._safe_object = None

        safe_object = None
        intentos: list[str] = []

        # Ruta 1: adjuntarse a una instancia ya abierta, probando cada
        # ProgID candidato (GetActiveObject).
        for pid in self._prog_id_list:
            try:
                safe_object = comtypes.client.GetActiveObject(pid)
                self._prog_id_used = pid
                logger.info("Adjuntado a instancia de SAFE via GetActiveObject('%s').", pid)
                break
            except Exception as e:
                intentos.append(f"GetActiveObject('{pid}'): {e}")

        # Ruta 2: cHelper, probando cada combinacion de helper/ProgID.
        if safe_object is None:
            for helper_pid in self._helper_list:
                try:
                    helper = comtypes.client.CreateObject(helper_pid)
                except Exception as e:
                    intentos.append(f"CreateObject('{helper_pid}'): {e}")
                    continue
                for pid in self._prog_id_list:
                    try:
                        obj = helper.GetObject(pid)
                        if obj is not None:
                            safe_object = obj
                            self._prog_id_used = pid
                            logger.info(
                                "Adjuntado a SAFE via %s.GetObject('%s').",
                                helper_pid, pid)
                            break
                        intentos.append(
                            f"{helper_pid}.GetObject('{pid}'): devolvio None")
                    except Exception as e:
                        intentos.append(f"{helper_pid}.GetObject('{pid}'): {e}")
                if safe_object is not None:
                    break

        # Ruta 3: arrancar una instancia nueva (solo si esta habilitado).
        if safe_object is None and self.auto_start:
            for helper_pid in self._helper_list:
                for pid in self._prog_id_list:
                    try:
                        helper = comtypes.client.CreateObject(helper_pid)
                        if self.exe_path and os.path.isfile(self.exe_path):
                            safe_object = helper.CreateObject(self.exe_path)
                        else:
                            safe_object = helper.CreateObjectProgID(pid)
                        safe_object.ApplicationStart()
                        self._prog_id_used = pid
                        logger.info("Instancia nueva de SAFE arrancada (%s / %s).",
                                   helper_pid, pid)
                        break
                    except Exception as e:
                        intentos.append(
                            f"arranque nuevo ({helper_pid}/{pid}): {e}")
                if safe_object is not None:
                    break

        if safe_object is None:
            raise SafeError(
                "No hay conexion con SAFE. Verifique: (a) SAFE esta abierto "
                "con un modelo cargado, (b) Python y SAFE son ambos de 64 "
                "bits, (c) SAFE se ejecuta con el mismo nivel de privilegios "
                "que Claude Desktop. El ProgID COM de SAFE NO esta confirmado "
                "en esta instalacion: ejecute diagnose_safe.py para "
                "identificarlo y fijelo en config.json (safe.prog_id). "
                f"Intentos: {'; '.join(intentos[:8])}"
                + (f" (+{len(intentos) - 8} mas)" if len(intentos) > 8 else "")
            )

        self._safe_object = safe_object
        self.SapModel = safe_object.SapModel

        try:
            self.version_string = str(safe_object.GetOAPIVersionNumber())
        except Exception:
            self.version_string = "desconocida"
        logger.info("SAFE conectado (ProgID '%s'). OAPI version: %s",
                   self._prog_id_used, self.version_string)

    def _model(self):
        self._connect()
        return self.SapModel

    # ------------------------------------------------------------------
    # Lectura basica [namespaces compartidos con ETABS/SAP2000: confianza
    # razonable, sin verificar en esta instalacion]
    # ------------------------------------------------------------------

    @com_call
    def get_model_info(self) -> str:
        """Devuelve archivo del modelo, ProgID usado y version de la OAPI."""
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
                f"ProgID conectado: {self._prog_id_used}\n"
                f"Version SAFE: {version}\n"
                f"Version OAPI: {self.version_string}")

    @com_call
    def get_units(self) -> str:
        """Devuelve las unidades activas del modelo."""
        model = self._model()
        my_units = model.GetPresentUnits()
        if my_units < 1 or my_units > len(PRESET_UNITS):
            return "Unidades desconocidas."
        return f"Unidades activas: {PRESET_UNITS[my_units - 1]}"

    @com_call
    def set_units(self, units: str) -> str:
        """Fija las unidades activas del modelo (ver get_units para opciones)."""
        model = self._model()
        target = units.strip().lower().replace(" ", "")
        for i, preset in enumerate(PRESET_UNITS, start=1):
            if preset.lower().replace(" ", "") == target:
                ret = model.SetPresentUnits(i)
                if ret != 0:
                    raise SafeError(f"Error fijando unidades a {preset}.")
                return f"Unidades fijadas en {preset}."
        raise SafeError(f"Unidades no reconocidas: {units}. "
                        f"Opciones: {', '.join(PRESET_UNITS)}")

    @com_call
    def save_model(self, path: str = "") -> str:
        """Guarda el modelo (.FDB). Si se indica path, guarda como archivo nuevo."""
        model = self._model()
        if path:
            parent = os.path.dirname(path)
            if parent and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
        ret = model.File.Save(path) if path else model.File.Save()
        if ret != 0:
            raise SafeError("Error guardando el modelo.")
        return f"Modelo guardado{(' en ' + path) if path else ''}."

    @com_call
    def refresh_view(self) -> str:
        """Refresca la vista de SAFE."""
        model = self._model()
        model.View.RefreshView(0, False)
        return "Vista refrescada."

    @com_call
    def describe_oapi(self, path: str = "", filter: str = "") -> str:
        """Muestra los metodos reales de la OAPI de ESTA instalacion de SAFE.

        Usar esto ANTES de confiar en cualquier herramienta de este archivo
        marcada como no verificada: el namespace real puede diferir del
        candidato usado (ver comentarios al inicio de Safe.py).

        Args:
            path: namespace bajo SapModel, ej. "PropArea", "AreaObj",
                  "PointSpring", "DatabaseTables". Vacio = el propio SapModel.
            filter: subcadena para filtrar por nombre, ej. "Slab", "Spring",
                    "Strip", "Punch", "Export".
        """
        model = self._model()
        target = oapi.resolve_path(model, path) if path else model
        label = f"SapModel.{path}" if path else "SapModel"
        return f"--- {label} ---\n" + oapi.describe(target, filter)

    # ------------------------------------------------------------------
    # Geometria
    # ------------------------------------------------------------------

    @com_call
    def get_points(self) -> list[GeomObject]:
        """Devuelve todos los puntos/joints del modelo."""
        model = self._model()
        n, names, xs, ys, zs, _csys = model.PointObj.GetAllPoints()
        return [GeomObject(type="point", xs=[xs[i]], ys=[ys[i]], zs=[zs[i]], id=names[i])
                for i in range(n)]

    @com_call
    def get_areas(self) -> list[GeomObject]:
        """Devuelve todas las areas (losas/zapatas) del modelo."""
        model = self._model()
        (n, names, _design, _npts_total, delim, _pnames,
         xc, yc, zc, _ret) = model.AreaObj.GetAllAreas()
        out = []
        i = 0
        for count, j in enumerate(delim):
            out.append(GeomObject(
                type="surface", xs=list(xc[i:j + 1]), ys=list(yc[i:j + 1]),
                zs=list(zc[i:j + 1]), id=names[count]))
            i = j + 1
        return out

    @com_call
    def create_area_by_coordinates(self, xs: list[float], ys: list[float],
                                   zs: list[float], section: str = "Default") -> str:
        """Crea una losa/zapata a partir de sus vertices.

        Args:
            xs, ys, zs: coordenadas de los vertices en orden.
            section: nombre de una seccion de losa ya definida
                     (ver define_slab_section).
        """
        model = self._model()
        _x, _y, _z, name, ret = model.AreaObj.AddByCoord(
            len(xs), list(xs), list(ys), list(zs), "", section)
        if ret != 0:
            raise SafeError(f"Error creando area de {len(xs)} vertices "
                            f"con seccion '{section}'.")
        return f"Area '{name}' creada con seccion '{section}'."

    # ------------------------------------------------------------------
    # Materiales [namespace PropMaterial: compartido con ETABS, confianza
    # razonable]
    # ------------------------------------------------------------------

    @com_call
    def define_concrete_material(self, name: str, fc: float,
                                 E: float = 0.0, poisson: float = 0.2,
                                 unit_weight: float = 0.0) -> str:
        """Define o modifica un material de hormigon (ver SOP Safe 3: 'Definir materiales').

        Args:
            name: nombre del material, ej. "C210".
            fc: resistencia a compresion f'c en las unidades activas.
            E: modulo de elasticidad. 0 = estimar por ACI 318 (4700*sqrt(f'c) en MPa).
            poisson: coeficiente de Poisson.
            unit_weight: peso por unidad de volumen EN LAS UNIDADES ACTIVAS.
                0 deja el material sin peso propio.
        """
        model = self._model()
        MATERIAL_CONCRETE = 2
        oapi.call(
            model.PropMaterial,
            [("SetMaterial", (name, MATERIAL_CONCRETE, -1, "", "")),
             ("SetMaterial", (name, MATERIAL_CONCRETE))],
            f"creacion/seleccion del material '{name}'",
        )
        if E <= 0:
            idx = model.GetPresentUnits()
            if not (1 <= idx <= len(PRESET_UNITS)):
                raise SafeError("No se pudieron determinar las unidades activas.")
            force, length, _t = [s.strip() for s in PRESET_UNITS[idx - 1].split(",")]
            force_n = {"lb": 4.4482216, "kip": 4448.2216, "kN": 1000.0,
                      "kgf": 9.80665, "N": 1.0, "Ton": 9806.65}[force]
            length_mm = {"in": 25.4, "ft": 304.8, "mm": 1.0, "m": 1000.0,
                        "cm": 10.0}[length]
            to_mpa = force_n / (length_mm ** 2)
            E = (4700.0 * ((fc * to_mpa) ** 0.5)) / to_mpa
        oapi.call(model.PropMaterial,
                  [("SetMPIsotropic", (name, float(E), float(poisson), 9.9e-6))],
                  f"propiedades mecanicas de '{name}'")
        oapi.call(
            model.PropMaterial,
            [("SetOConcrete_1", (name, float(fc), False, 0.0, 1, 0,
                                 0.0022, 0.0052, -0.1, 0.0, 0.0)),
             ("SetOConcrete", (name, float(fc), False, 0.0, 1, 0, 0.0022, 0.0052))],
            f"parametros de hormigon de '{name}'",
        )
        if unit_weight > 0:
            oapi.call(model.PropMaterial,
                      [("SetWeightAndMass", (name, 1, float(unit_weight)))],
                      f"peso por unidad de volumen de '{name}'")
        return f"Material '{name}' definido: f'c={fc:g}, E={E:g}, v={poisson:g}."

    @com_call
    def define_rebar_material(self, name: str, fy: float, fu: float = 0.0,
                              E: float = 0.0) -> str:
        """Define un material de acero de refuerzo (barras), ver SOP Safe 3.

        Args:
            name: nombre, ej. "A615Gr60".
            fy: esfuerzo de fluencia en las unidades activas.
            fu: esfuerzo ultimo. 0 = estimar como 1.5*fy (relacion tipica Grado 60).
            E: modulo de elasticidad. 0 = 200000 MPa convertido a unidades activas.
        """
        model = self._model()
        MATERIAL_REBAR = 6
        oapi.call(model.PropMaterial,
                  [("SetMaterial", (name, MATERIAL_REBAR, -1, "", "")),
                   ("SetMaterial", (name, MATERIAL_REBAR))],
                  f"creacion del material de refuerzo '{name}'")
        if fu <= 0:
            fu = 1.5 * fy
        if E <= 0:
            idx = model.GetPresentUnits()
            force, length, _t = [s.strip() for s in PRESET_UNITS[idx - 1].split(",")]
            force_n = {"lb": 4.4482216, "kip": 4448.2216, "kN": 1000.0,
                      "kgf": 9.80665, "N": 1.0, "Ton": 9806.65}[force]
            length_mm = {"in": 25.4, "ft": 304.8, "mm": 1.0, "m": 1000.0,
                        "cm": 10.0}[length]
            E = 200000.0 / (force_n / (length_mm ** 2))
        oapi.call(model.PropMaterial,
                  [("SetMPIsotropic", (name, float(E), 0.3, 11.7e-6))],
                  f"propiedades mecanicas de '{name}'")
        oapi.call(model.PropMaterial,
                  [("SetORebar_1", (name, float(fy), float(fu), float(fy), float(fu),
                                    1, 0, 0.02, 0.10, 0.09, -0.10)),
                   ("SetORebar", (name, float(fy), float(fu), float(fy), float(fu),
                                  1, 0))],
                  f"parametros de refuerzo de '{name}'")
        return f"Material de refuerzo '{name}' definido: fy={fy:g}, fu={fu:g}."

    # ------------------------------------------------------------------
    # Secciones de losa/zapata [namespace PropArea: compartido con ETABS
    # para 'Slab'/'Deck'/'Wall'; el Type Footing/Stiff/Drop de SAFE (SOP
    # pag. 34-35, 45) NO ESTA VERIFICADO -- confirmar con
    # describe_oapi(path="PropArea")]
    # ------------------------------------------------------------------

    @com_call
    def define_slab_section(self, name: str, material: str, thickness: float,
                            slab_type: str = "Slab") -> str:
        """Define una seccion de losa, dropcap o zapata (SOP Safe 3.4/3.14).

        Args:
            name: nombre de la seccion, ej. "S40" (losa 0.40) o "Z40" (zapata).
            material: material de hormigon ya definido.
            thickness: espesor en las unidades activas.
            slab_type: "Slab" (losa normal, Stiff), "Footing" (zapata) o
                       "Drop" (pedestal/dropcap). Ver SOP pag. 34 (Type=
                       Footing), pag. 35 (Type=Stiff) y pag. 45 (Type=Drop).
                       NO VERIFICADO el nombre/indice exacto que espera la
                       OAPI para cada tipo en esta instalacion; si falla,
                       revisar con describe_oapi(path="PropArea", filter="Slab").
        """
        model = self._model()
        type_map = {"slab": 0, "drop": 1, "stiff": 2, "footing": 3}
        key = slab_type.strip().lower()
        if key not in type_map:
            raise SafeError(f"slab_type no reconocido: '{slab_type}'. "
                            f"Use uno de: {', '.join(type_map)}.")
        # SHELL_THIN = 1 (mismo valor que en la OAPI de ETABS/SAP2000 para
        # PropArea.SetSlab: Name, SlabType, ShellType, MatProp, Thickness).
        SHELL_THIN = 1
        oapi.call(
            model.PropArea,
            [("SetSlab", (name, type_map[key], SHELL_THIN, material,
                          float(thickness), -1, "", "")),
             ("SetSlab", (name, type_map[key], SHELL_THIN, material,
                          float(thickness)))],
            f"creacion de la seccion de losa '{name}'",
        )
        return (f"Seccion '{name}' definida: tipo={slab_type}, "
                f"espesor={thickness:g}, material '{material}'.")

    # ------------------------------------------------------------------
    # Resorte de suelo [namespace y metodo NO VERIFICADOS -- SOP pag. 37,
    # 41-42: 'Area Spring Property', Subgrade Modulus, Compression Only]
    # ------------------------------------------------------------------

    @com_call
    def define_soil_spring(self, name: str, allowable_bearing: float,
                           factor: float = 1.2, compression_only: bool = True) -> str:
        """Define un resorte de area para el suelo (SOP Safe 3.6).

        k = factor * esfuerzo_admisible (factor=1.2 es el valor del SOP).

        [VERIFICADO en vivo el 2026-08-10 contra SAFE v23.3.0, OAPI v2.016
        via describe_oapi(path="PropAreaSpring"):
        SetAreaSpringProp(Name, U1, U2, U3, NonlinearOption3, SpringOption=1,
        SoilProfile='', EndLengthRatio=0.0, Period=0.0, Color=0, Notes='',
        iGUID=''). U1/U2 son los resortes horizontales (0 para este caso: el
        SOP solo define resorte vertical de suelo); U3 es el resorte
        vertical = k. El orden de NonlinearOption3 (0=None/Linear,
        1=TensionOnly, 2=CompressionOnly, 3=ElastoPlastic) se infiere del
        orden de los radio-botones en el dialogo del SOP (pag. 37: "None
        (Linear)", "Tension Only", "Compression Only", "Elasto-Plastic") y
        AUN NO esta confirmado contra un modelo real -- si el resorte queda
        con el comportamiento equivocado, revisar con GetAreaSpringProp
        despues de definirlo.]

        Args:
            name: nombre del resorte, ej. "SOIL1".
            allowable_bearing: esfuerzo admisible del suelo, en las unidades
                                activas (fuerza/longitud^2).
            factor: multiplicador sobre el esfuerzo admisible (SOP: 1.2).
            compression_only: True = el resorte solo trabaja a compresion
                              (SOP: "Compression Only"), evita traccion
                              irreal del suelo sobre la losa.
        """
        model = self._model()
        k = float(factor) * float(allowable_bearing)
        NONLINEAR_NONE, NONLINEAR_TENSION_ONLY = 0, 1
        NONLINEAR_COMPRESSION_ONLY, NONLINEAR_ELASTO_PLASTIC = 2, 3
        nonlinear = NONLINEAR_COMPRESSION_ONLY if compression_only else NONLINEAR_NONE
        oapi.call_checked(
            model.PropAreaSpring, "SetAreaSpringProp",
            (name, 0.0, 0.0, k, nonlinear),
            f"creacion del resorte de suelo '{name}'",
        )
        return (f"Resorte de suelo '{name}' definido: k={k:g} "
                f"({factor:g} x {allowable_bearing:g}), "
                f"{'compresion unicamente' if compression_only else 'lineal'}. "
                f"Verificar comportamiento con get_table_data o "
                f"describe_oapi si el resultado no coincide con lo esperado.")

    @com_call
    def assign_area_spring(self, area_ids: list[str], spring_name: str) -> str:
        """Asigna un resorte de suelo a una o mas areas (SOP Safe 3.10-3.11).

        Args:
            area_ids: IDs de area (de get_areas), tipicamente las zapatas.
            spring_name: nombre de un resorte ya definido (define_soil_spring).
        """
        model = self._model()
        errors = []
        for aid in area_ids:
            try:
                oapi.call(
                    model.AreaObj,
                    [("SetSpringAssignment", (aid, spring_name)),
                     ("SetSpringAssignment", (aid, spring_name, 0))],
                    f"asignacion de resorte al area {aid}",
                )
            except Exception as e:
                errors.append(f"{aid}: {e}")
        msg = f"Resorte '{spring_name}' asignado a {len(area_ids) - len(errors)} area(s)."
        if errors:
            msg += f" {len(errors)} fallo(s): " + "; ".join(errors[:5])
        return msg

    # ------------------------------------------------------------------
    # Cargas y combinaciones [LoadPatterns/RespCombo: compartidos con ETABS]
    # ------------------------------------------------------------------

    @com_call
    def add_load_pattern(self, name: str, load_type: str = "Dead",
                         self_weight_multiplier: float = 0.0) -> str:
        """Define un patron de carga (Dead, Live, LiveT, LiveP, Seismic, etc.)."""
        model = self._model()
        oapi.call(model.LoadPatterns,
                  [("Add", (name, load_type, float(self_weight_multiplier), True))],
                  f"creacion del patron de carga '{name}'")
        return f"Patron de carga '{name}' ({load_type}) creado."

    @com_call
    def add_load_combo(self, name: str, cases: dict[str, float],
                       combo_type: str = "Linear Add") -> str:
        """Define una combinacion de carga (SOP Safe 3.1-3.3, Art. 58 R-033).

        Args:
            name: nombre de la combinacion, ej. "Comb1".
            cases: diccionario {nombre_de_caso_o_patron: factor}, ej.
                   {"Dead": 1.354, "Live": 1.11}.
            combo_type: tipo de combinacion, normalmente "Linear Add".
        """
        model = self._model()
        LINEAR_ADD = 0
        oapi.call(model.RespCombo,
                  [("Add", (name, LINEAR_ADD))],
                  f"creacion de la combinacion '{name}'")
        for case, factor in cases.items():
            oapi.call(
                model.RespCombo,
                [("SetCaseList", (name, 0, case, float(factor))),
                 ("SetCaseList", (name, 1, case, float(factor)))],
                f"agregado de '{case}' a la combinacion '{name}'",
            )
        return f"Combinacion '{name}' creada con {len(cases)} caso(s)."

    # ------------------------------------------------------------------
    # Analisis y diseño de losa [DesignConcrete/StartDesign: NO VERIFICADO
    # si SAFE usa el mismo namespace que el diseño de frames de ETABS o uno
    # propio -- SOP pag. 47: 'View/Revise Slab Flexural Design Overwrites']
    # ------------------------------------------------------------------

    @com_call
    def run_analysis(self) -> str:
        """Corre el analisis (equivalente a F5 en la interfaz).

        LLAMADA BLOQUEANTE: puede exceder el timeout del cliente MCP sin que
        eso cancele nada del lado COM (E-035). Tras un timeout, sondear con
        get_analysis_status en vez de relanzar a ciegas.
        """
        model = self._model()
        ret = model.Analyze.RunAnalysis()
        if ret != 0:
            raise SafeError("Error al correr el analisis.")
        return "Analisis ejecutado."

    @com_call
    def get_analysis_status(self) -> str:
        """Estado por caso de carga: no corrido / no pudo / incompleto / listo.

        Sondeo barato para despues de un timeout MCP en run_analysis.

        [Firma verificada en vivo 2026-08-10 via describe_oapi contra esta
        instalacion: Analyze.GetCaseStatus -> (NumberItems, CaseName, Status,
        pRetVal). Codigos CSI: 1=Not run, 2=Could not start, 3=Not finished,
        4=Finished.]
        """
        model = self._model()
        (n, names, status, ret) = model.Analyze.GetCaseStatus(0, [], [])
        if ret != 0:
            raise SafeError("GetCaseStatus fallo (ret != 0).")
        if n == 0:
            return "Sin casos de carga definidos."
        etiquetas = {1: "no corrido", 2: "NO PUDO ARRANCAR",
                     3: "INCOMPLETO (corriendo o interrumpido)", 4: "listo"}
        lines = [f"{names[i]}: {etiquetas.get(status[i], status[i])}"
                 for i in range(n)]
        pendientes = sum(1 for i in range(n) if status[i] != 4)
        resumen = ("todos los casos listos" if pendientes == 0
                   else f"{pendientes} caso(s) sin terminar de {n}")
        return f"Estado del analisis ({resumen}):\n" + "\n".join(lines)

    @com_call
    def run_slab_design(self) -> str:
        """Corre el diseño de losa/zapata (SOP Safe 3.16: 'Verificar el armado').

        [VERIFICADO en vivo el 2026-08-10 contra SAFE v23.3.0: existe
        SapModel.DesignConcreteSlab.StartSlabDesign() -> pRetVal, sin
        argumentos. El namespace tambien expone GetFlexureAndShear y
        GetSummaryResultsFlexureAndShear para leer resultados de acero por
        franja/estacion despues de correr esto, y DesignStrip como
        subobjeto propio -- pendiente de exponer como herramienta aparte
        si se necesitan franjas explicitas (el SOP pag. 47 muestra que esta
        version tambien soporta diseño 'Finite Element Based', que no
        requiere franjas).]
        """
        model = self._model()
        oapi.call_checked(model.DesignConcreteSlab, "StartSlabDesign", (),
                          "diseño de losa/zapata")
        return "Diseño de losa/zapata ejecutado (DesignConcreteSlab.StartSlabDesign)."

    @com_call
    def get_slab_design_summary(self) -> str:
        """Lee el resumen de acero de flexion y corte por franja de diseño.

        [VERIFICADO en vivo: DesignConcreteSlab.GetSummaryResultsFlexureAndShear
        existe y devuelve, por franja/tramo: combo y momento/area de acero
        superior e inferior, combo/fuerza/area de corte, estado y capa.
        Requiere haber corrido run_slab_design primero.]
        """
        model = self._model()
        (story, strip, span, location, ftop_combo, ftop_m, ftop_as,
         fbot_combo, fbot_m, fbot_as, vcombo, vforce, varea, status, layer,
         ret) = model.DesignConcreteSlab.GetSummaryResultsFlexureAndShear(
            [], [], [], [], [], [], [], [], [], [], [], [], [], [], [])
        if ret != 0:
            raise SafeError("Error leyendo el resumen de diseño de losa. "
                            "¿Se corrio run_slab_design?")
        rows = []
        for i in range(len(story)):
            rows.append(
                f"{story[i]}/{strip[i]}/{span[i]} ({location[i]}): "
                f"As_top={ftop_as[i]:g} ({ftop_combo[i]}), "
                f"As_bot={fbot_as[i]:g} ({fbot_combo[i]}), "
                f"Av={varea[i]:g} ({vcombo[i]}), estado={status[i]}")
        if not rows:
            return "Sin resultados. ¿Se corrio run_slab_design y run_analysis?"
        return f"{len(rows)} fila(s):\n" + "\n".join(rows)

    @com_call
    def get_design_strips(self) -> str:
        """Lista las franjas de diseño y su geometria (SOP Safe 3.15).

        [VERIFICADO 2026-08-10: DesignConcreteSlab.DesignStrip expone
        GetNameList y GetDesignStrip_1 (con DesignType). NO hay metodo de
        creacion de franjas en este namespace (solo ChangeName/Delete/Get*):
        las franjas se dibujan en la interfaz (Draw > Design Strips) o via
        tablas; este lector permite verificar que existen antes de diseñar.]
        """
        model = self._model()
        ds = model.DesignConcreteSlab.DesignStrip
        n, names, ret = ds.GetNameList(0, [])
        if ret != 0:
            raise SafeError("GetNameList de franjas fallo.")
        if n == 0:
            return ("Sin franjas de diseño. Dibujarlas en la interfaz "
                    "(Draw > Design Strips) o usar diseño Finite Element "
                    "Based, que no las requiere.")
        rows = []
        for name in names:
            try:
                (dtype, pts, xs, ys, zs, wbl, wbr, wal, war, auto,
                 ret2) = ds.GetDesignStrip_1(
                    name, 0, [], [], [], [], [], [], [], [], [])
                if ret2 != 0:
                    rows.append(f"{name}: (no legible)")
                    continue
                tipo = {0: "columna", 1: "media", 2: "otra"}.get(dtype, str(dtype))
                rows.append(
                    f"{name} [{tipo}]: {len(pts)} punto(s), "
                    f"anchos B izq/der {wbl[0]:g}/{wbr[0]:g}, "
                    f"A izq/der {wal[0]:g}/{war[0]:g}"
                    + (", auto-widen" if auto and auto[0] else ""))
            except Exception as e:
                rows.append(f"{name}: error ({e})")
        return f"{n} franja(s):\n" + "\n".join(rows)

    @com_call
    def get_slab_design_detail(self) -> str:
        """Lee el diseño de losa por estacion (mas fino que el resumen).

        [VERIFICADO 2026-08-10: DesignConcreteSlab.GetFlexureAndShear
        devuelve por estacion: momento y area sup/inf con su minimo, axial,
        corte, estado, coordenadas globales y capa. Es el insumo directo del
        detallado en Revit (C6): las coordenadas permiten mapear cada
        estacion a su posicion en el modelo.]
        """
        model = self._model()
        (story, strip, station, width, ftop_combo, ftop_m, ftop_as, ftop_min,
         fbot_combo, fbot_m, fbot_as, fbot_min, axial, vcombo, vforce, varea,
         status, gx, gy, layer, ret) = \
            model.DesignConcreteSlab.GetFlexureAndShear(
                [], [], [], [], [], [], [], [], [], [], [], [], [], [], [],
                [], [], [], [], [])
        if ret != 0:
            raise SafeError("GetFlexureAndShear fallo. ¿Se corrio "
                            "run_slab_design?")
        n = len(story)
        if n == 0:
            return "Sin resultados. ¿run_analysis y run_slab_design corridos?"
        rows = []
        for i in range(n):
            rows.append(
                f"{story[i]}/{strip[i]} @ {station[i]:.2f} "
                f"({gx[i]:.2f},{gy[i]:.2f}) b={width[i]:g}: "
                f"M_sup={ftop_m[i]:g} As_sup={ftop_as[i]:g} "
                f"(min {ftop_min[i]:g}, {ftop_combo[i]}); "
                f"M_inf={fbot_m[i]:g} As_inf={fbot_as[i]:g} "
                f"(min {fbot_min[i]:g}, {fbot_combo[i]}); "
                f"V={vforce[i]:g} Av={varea[i]:g} ({vcombo[i]}); "
                f"{status[i]} [{layer[i]}]")
        return f"{n} estacion(es):\n" + "\n".join(rows)

    @com_call
    def get_span_definitions(self) -> str:
        """Lee los tramos de cada franja de diseño (longitudes y extremos).

        [VERIFICADO 2026-08-10: GetSummaryResultsSpanDefinition. Insumo para
        reglas de solape del SOP (a 3/4 de la losa principal cruzando a 3/4
        de la continua): da la longitud de cada tramo y sus coordenadas.]
        """
        model = self._model()
        (story, strip, span, length, start_d, end_d, x1, y1, x2, y2, ret) = \
            model.DesignConcreteSlab.GetSummaryResultsSpanDefinition(
                [], [], [], [], [], [], [], [], [], [])
        if ret != 0:
            raise SafeError("GetSummaryResultsSpanDefinition fallo. "
                            "¿Diseño corrido?")
        n = len(story)
        if n == 0:
            return "Sin tramos definidos."
        rows = [
            f"{story[i]}/{strip[i]}/{span[i]}: L={length[i]:g} "
            f"({x1[i]:.2f},{y1[i]:.2f})->({x2[i]:.2f},{y2[i]:.2f})"
            for i in range(n)]
        return f"{n} tramo(s):\n" + "\n".join(rows)

    @com_call
    def get_punching_check(self) -> str:
        """Lee el chequeo de punzonamiento via tablas (SOP Safe 3.13).

        [DesignConcreteSlab NO tiene metodo de punzonamiento (verificado:
        8 metodos, ninguno Punch). La via es DatabaseTables: este metodo
        busca la clave de tabla que contenga 'Punch' y la lee. El nombre
        exacto de la clave se descubre en runtime porque depende de tener
        un modelo con diseño corrido. Regla del SOP: ratio > 1 -> crecer el
        espesor. Decision del ingeniero, no de esta herramienta.]
        """
        model = self._model()
        n, keys, names, _imp, ret = model.DatabaseTables.GetAvailableTables()
        if ret != 0:
            raise SafeError("No se pudo listar tablas.")
        candidatas = [keys[i] for i in range(n)
                      if "punch" in str(keys[i]).lower()
                      or "punch" in str(names[i]).lower()]
        if not candidatas:
            return ("Ninguna tabla de punzonamiento disponible. Correr "
                    "run_analysis + run_slab_design primero; si persiste, "
                    "usar list_tables para inspeccionar las claves.")
        out = []
        for key in candidatas:
            try:
                out.append(self.get_table_data(key))
            except Exception as e:
                out.append(f"{key}: no legible ({e})")
        return "\n\n".join(out)

    @com_call
    def get_soil_pressure(self) -> str:
        """Lee la presion de contacto suelo-losa via tablas (SOP Safe 3.12).

        [Misma via que get_punching_check: se busca la clave con 'Soil
        Pressure'. Verificacion del SOP a aplicar sobre el resultado:
        combo 2 contra sigma_adm; envolvente contra 3/4 de sigma_adm. Si no
        cumple, ampliar el area de la zapata -- decision del ingeniero.]
        """
        model = self._model()
        n, keys, names, _imp, ret = model.DatabaseTables.GetAvailableTables()
        if ret != 0:
            raise SafeError("No se pudo listar tablas.")
        candidatas = [keys[i] for i in range(n)
                      if "soil" in str(keys[i]).lower()
                      or "pressure" in str(names[i]).lower()]
        if not candidatas:
            return ("Ninguna tabla de presion de suelo disponible. Correr "
                    "run_analysis primero; si persiste, usar list_tables.")
        out = []
        for key in candidatas:
            try:
                out.append(self.get_table_data(key))
            except Exception as e:
                out.append(f"{key}: no legible ({e})")
        return "\n\n".join(out)

    # ------------------------------------------------------------------
    # Tablas interactivas [DatabaseTables: SOP pag. 32 confirma que SAFE
    # tiene 'Interactive Database Editing', igual que ETABS. Mecanismo mas
    # confiable para lo que no tiene metodo dedicado: presion de suelo,
    # punzonamiento, combinaciones pegadas desde Excel.]
    # ------------------------------------------------------------------

    @com_call
    def list_tables(self, filter: str = "") -> str:
        """Lista las tablas de base de datos disponibles en el modelo.

        [Corregido el 2026-08-10 tras error en vivo: GetAvailableTables NO
        devuelve IsEmpty (eso solo lo hace GetAllTables). Firma real,
        confirmada via describe_oapi(path="DatabaseTables"):
        GetAvailableTables(NumberTables, TableKey[], TableName[],
        ImportType[]) -> 5 valores (n, keys, names, import_type, ret).]
        """
        model = self._model()
        n, keys, names, _import_type, ret = \
            model.DatabaseTables.GetAvailableTables()
        if ret != 0:
            raise SafeError("Error leyendo la lista de tablas disponibles.")
        rows = []
        for i in range(n):
            if filter and filter.lower() not in str(names[i]).lower():
                continue
            rows.append(f"{keys[i]}: {names[i]}")
        if not rows:
            return "Ninguna tabla coincide." if filter else "Sin tablas disponibles."
        return f"{len(rows)} tabla(s):\n" + "\n".join(rows)

    @com_call
    def get_table_data(self, table_key: str, max_rows: int = 100,
                       offset: int = 0) -> str:
        """Lee una tabla de base de datos por su clave, con paginacion.

        Utilizar para leer, por ejemplo, presion de contacto contra el suelo
        o resultados de punzonamiento (SOP Safe 3.12-3.13), cuyo nombre
        exacto de tabla en esta instalacion se confirma con list_tables.

        PARA TABLAS DE RESULTADOS MASIVAS (ej. 'Soil Pressures', >1M filas)
        ni siquiera la lectura COM completa es viable dentro del timeout del
        cliente: usar export_file tipo 4 (texto) y parsear el archivo
        (E-035). La paginacion de aca recorta la RESPUESTA, no la lectura.

        Args:
            table_key: clave de tabla (ver list_tables).
            max_rows: maximo de filas a mostrar en esta pagina.
            offset: fila inicial (0 = primera).

        [Corregido el 2026-08-10 tras error en vivo: la firma real
        (GetTableForDisplayArray) devuelve 6 valores, no 7, y en otro orden:
        (FieldKeyList_eco, TableVersion, FieldsKeysIncluded, NumberRecords,
        TableData, pRetVal). El numero de columnas es len(FieldsKeysIncluded),
        no un parametro aparte.]
        """
        model = self._model()
        (_field_key_echo, _table_version, fields_keys, num_records,
         table_data, ret) = model.DatabaseTables.GetTableForDisplayArray(
            table_key, [], "", 0)
        num_fields = len(fields_keys)
        if ret != 0 or num_fields == 0:
            raise SafeError(f"No se pudo leer la tabla '{table_key}' "
                            f"(o esta vacia). Use list_tables para ver claves validas.")
        start = max(0, offset)
        if start >= num_records and num_records > 0:
            return (f"{table_key} ({num_records} fila(s)); "
                    f"offset {start} fuera de rango.")
        end = min(num_records, start + max_rows)
        header = ", ".join(fields_keys)
        lines = []
        for r in range(start, end):
            row = table_data[r * num_fields:(r + 1) * num_fields]
            lines.append(", ".join(str(v) for v in row))
        resto = num_records - end
        suffix = "" if resto == 0 else (
            f"\n... ({resto} fila(s) mas; siguiente pagina: offset={end})")
        rango = f" [filas {start}..{end - 1}]" if start > 0 else ""
        return (f"{table_key} ({num_records} fila(s)){rango}\n{header}\n"
                + "\n".join(lines) + suffix)

    @com_call
    def set_table_data(self, table_key: str, fields: list[str],
                       rows: list[list[str]]) -> str:
        """Escribe una tabla de base de datos (ej. pegar combinaciones desde Excel).

        Args:
            table_key: clave de tabla (ver list_tables).
            fields: nombres de columna, en el mismo orden que cada fila.
            rows: filas de datos, todas como texto (la OAPI convierte).

        [Corregido el 2026-08-10: ApplyEditedTables devuelve 6 valores
        (NumFatalErrors, NumErrorMsgs, NumWarnMsgs, NumInfoMsgs, ImportLog,
        pRetVal), no 5 -- faltaba NumErrorMsgs en el desempaquetado.]
        """
        model = self._model()
        flat = [str(v) for row in rows for v in row]
        result = model.DatabaseTables.SetTableForEditingArray(
            table_key, 0, fields, len(rows), flat)
        ret = result[-1] if isinstance(result, (tuple, list)) else result
        if ret != 0:
            raise SafeError(f"Error escribiendo la tabla '{table_key}'.")
        (n_fatal, n_errmsg, n_warn, n_info, import_log, ret2) = \
            model.DatabaseTables.ApplyEditedTables(False)
        if n_fatal or ret2 != 0:
            raise SafeError(f"{n_fatal} error(es) fatal(es) al aplicar la tabla "
                            f"'{table_key}': {import_log}")
        return (f"Tabla '{table_key}' escrita: {len(rows)} fila(s). "
                f"Errores: {n_errmsg}, advertencias: {n_warn}.")

    # ------------------------------------------------------------------
    # Import/Export de archivo [SOP: ETABS "Export > Story as SAFE F2K
    # File" -> SAFE "Import > SAFE .f2k Text File" (paso 1 de la seccion
    # Safe); "Export > .DXF/.DWG File" para detallar (paso 3.17).
    # cFile SI tiene ImportFile/ExportFile genericos (confirmado en vivo
    # 2026-08-10, describe_oapi(path="File")), pero NO hay metodo dedicado
    # a DXF ni a F2K: son casos particulares de un FileType numerico cuyo
    # enum (eFileType de la OAPI de CSI) esta documentado en la ayuda oficial
    # de SAFE, no descubrible via introspeccion de tipos porque los enums
    # COM no traen los nombres de sus miembros en el typelib generado por
    # comtypes. Falta: abrir la ayuda de la OAPI en SAFE (Help > CSI OAPI
    # Documentation, o el .chm que instala SAFE) y buscar "eFileType" para
    # obtener los valores de DXF/DWG y de F2K, y fijarlos abajo.
    # ------------------------------------------------------------------

    @com_call
    def import_file(self, path: str, file_type: int = FILE_TYPE_F2K,
                    import_type: int = 0) -> str:
        """Importa un archivo (ej. el .F2K exportado desde ETABS) al modelo activo.

        file_type identificado empiricamente el 2026-08-10 (probe_file_types):
        1 = SAFE .f2k Text File -- el formato del paso ETABS -> SAFE del SOP.
        El lado EXPORT de f2k esta verificado (produjo archivo TABLE valido);
        el lado IMPORT usa el mismo enum pero no se ha probado todavia con un
        F2K real exportado desde ETABS.

        Args:
            path: ruta del archivo a importar.
            file_type: codigo eFileType (1=F2K, 2=Excel, 3=Access, 4=Texto,
                       5=XML; ver constantes FILE_TYPE_* al inicio del modulo).
            import_type: 0 = reemplazar geometria existente (default tipico
                         de la OAPI; no verificado).
        """
        model = self._model()
        if not os.path.isfile(path):
            raise SafeError(f"No existe el archivo: {path}")
        ret = model.File.ImportFile(path, int(file_type), int(import_type))
        if isinstance(ret, (tuple, list)):
            ret = ret[-1]
        if ret != 0:
            raise SafeError(f"Error importando '{path}' (file_type={file_type}).")
        return f"Importado: {path}."

    @com_call
    def probe_file_types(self, out_dir: str, type_min: int = 0,
                         type_max: int = 20) -> str:
        """Descubre el enum eFileType por prueba y error (HUECOS S-1).

        Llama File.ExportFile con cada valor del rango, cada uno a una ruta
        distinta en out_dir, y reporta que valores devolvieron ret=0 y que
        archivo produjeron (nombre + tamaño). El enum no es introspectable
        (los enums COM no traen nombres de miembro en el typelib), asi que
        esta sonda es la via mas barata para identificar los codigos de F2K
        y DXF sin abrir la ayuda de CSI.

        USAR CON UN MODELO DE PRUEBA GUARDADO: la sonda solo exporta, no
        modifica el modelo, pero conviene correrla sobre un modelo pequeño
        con algo de contenido para que los archivos exportados no salgan
        vacios.

        Args:
            out_dir: carpeta de salida para los archivos de prueba.
            type_min, type_max: rango de enteros a probar.
        """
        model = self._model()
        os.makedirs(out_dir, exist_ok=True)
        resultados = []
        for ft in range(int(type_min), int(type_max) + 1):
            base = os.path.join(out_dir, f"probe_type_{ft}")
            try:
                ret = model.File.ExportFile(base, ft)
                if isinstance(ret, (tuple, list)):
                    ret = ret[-1]
            except Exception as e:
                resultados.append(f"tipo {ft}: excepcion ({e})")
                continue
            if ret != 0:
                resultados.append(f"tipo {ft}: ret={ret}")
                continue
            # ExportFile puede haber agregado extension propia: buscar que
            # aparecio en el directorio con ese prefijo.
            producidos = [f for f in os.listdir(out_dir)
                          if f.startswith(f"probe_type_{ft}")]
            detalle = ", ".join(
                f"{f} ({os.path.getsize(os.path.join(out_dir, f))} bytes)"
                for f in producidos) or "ret=0 pero sin archivo visible"
            resultados.append(f"tipo {ft}: OK -> {detalle}")
        return ("Sonda de eFileType (fijar los valores encontrados en "
                "import_file/export_file y anotarlos en HUECOS-ETABS-SAFE.md):\n"
                + "\n".join(resultados))

    @com_call
    def export_file(self, path: str, file_type: int) -> str:
        """Exporta el modelo/vista actual (ej. a DXF para detallar, SOP 3.17).

        NO VERIFICADO el valor numerico de file_type para DXF en esta
        instalacion. Mismo procedimiento de confirmacion que import_file.

        Args:
            path: ruta de salida.
            file_type: codigo numerico del tipo de archivo (eFileType).
        """
        model = self._model()
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        ret = model.File.ExportFile(path, int(file_type))
        if isinstance(ret, (tuple, list)):
            ret = ret[-1]
        if ret != 0:
            raise SafeError(f"Error exportando a '{path}' (file_type={file_type}).")
        return f"Exportado: {path}."
