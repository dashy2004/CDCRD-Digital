# SAFE MCP — lote 1 Claude (v0.2.1) + lote 2 CDX (2026-09-25).
# Fuente de firmas/estados: docs/OAPI-SAFE-real.md, docs/ENUMS-SAFE.md.
# Capa A: documentada por CSI para SAFE; capa B: typelib compartido.
# Tests mock no equivalen a verificacion viva. Solo Claude opera SAFE.
# Los comentarios historicos de cada metodo no reemplazan el registro de
# corrida por version. Ver README y docs/PRUEBA-VIVA-LOTE2.md.

import logging
import os
import math
from functools import wraps
from typing import Any

import comtypes
import comtypes.client
from pydantic import BaseModel, Field

from comthread import com_call as _com_call
import oapi
import pilotes
import pilotes_xlsx

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


def com_call(fn):
    """Mantiene el hilo COM y unifica los errores de compatibilidad."""
    @wraps(fn)
    def checked(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except oapi.OapiError as exc:
            raise SafeError(str(exc)) from exc
    return _com_call(checked)


def _result(result, method):
    if oapi.ret_code(result) != 0:
        raise SafeError(f"{method}: ret={oapi.ret_code(result)}; resultado={result!r}")
    return oapi.outs(result)


def _equal_number(a, b):
    return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-6)


IMPORT_TYPES = {
    0: "no importable",
    1: "importable, no editable interactivamente",
    2: "editable interactivamente solo desbloqueado",
    3: "editable interactivamente bloqueado o desbloqueado",
}


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
        version, _num = _result(model.GetVersion(), "GetVersion")
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
                if model.GetPresentUnits() != i:
                    raise SafeError("SetPresentUnits: unidades distintas al releer.")
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
        _result(model.View.RefreshView(0, False), "View.RefreshView")
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
        n, names, xs, ys, zs = _result(model.PointObj.GetAllPoints(), "PointObj.GetAllPoints")
        return [GeomObject(type="point", xs=[xs[i]], ys=[ys[i]], zs=[zs[i]], id=names[i])
                for i in range(n)]

    @com_call
    def get_areas(self) -> list[GeomObject]:
        """Devuelve todas las areas (losas/zapatas) del modelo."""
        model = self._model()
        (n, names, _design, _npts_total, delim, _pnames,
         xc, yc, zc, _ret) = model.AreaObj.GetAllAreas()
        _result(_ret, "AreaObj.GetAllAreas")
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
        if len(xs) < 3 or not len(xs) == len(ys) == len(zs):
            raise SafeError("Se necesitan al menos tres vertices con X/Y/Z de igual longitud.")
        _x, _y, _z, name, ret = model.AreaObj.AddByCoord(
            len(xs), list(xs), list(ys), list(zs), "", section)
        if ret != 0:
            raise SafeError(f"Error creando area de {len(xs)} vertices "
                            f"con seccion '{section}'.")
        pts = self._area_points(name)
        actual = [self._coords(pt) for pt in pts]
        expected = list(zip(xs, ys, zs))
        # SAFE puede rotar el primer vertice del poligono.
        if len(actual) != len(expected) or not any(
                all(all(_equal_number(a, b) for a, b in zip(actual[(i + shift) % len(actual)], xyz))
                    for i, xyz in enumerate(expected)) for shift in range(len(actual))):
            raise SafeError("AddByCoord: geometria distinta al releer GetPoints/GetCoordCartesian.")
        prop, = _result(model.AreaObj.GetProperty(name), "GetProperty")
        if section != "Default" and prop != section:
            raise SafeError("AddByCoord: seccion distinta al releer.")
        return f"Area '{name}' creada con seccion '{prop}' (releida)."

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
            slab_type: Slab, Drop, Stiff, Ribbed, Waffle, Mat o Footing.
                Enums confirmados por Claude (2026-09-25); ver ENUMS-SAFE.md.
                Relee tipo, shell, material y espesor despues de escribir.
        """
        model = self._model()
        # eSlabType VERIFICADO EN VIVO 2026-09-25 [claude] escribiendo cada
        # entero con SetSlab y releyendo la tabla 'Slab Property Definitions':
        # 0=Slab, 1=Drop, 2=Stiff, 3=Ribbed, 4=Waffle, 5=Mat, 6=Footing.
        # La v0.1.0 usaba footing=3, que en SAFE es RIBBED (losa nervada).
        type_map = {"slab": 0, "drop": 1, "stiff": 2, "ribbed": 3,
                    "waffle": 4, "mat": 5, "footing": 6}
        key = slab_type.strip().lower()
        if key not in type_map:
            raise SafeError(f"slab_type no reconocido: '{slab_type}'. "
                            f"Use uno de: {', '.join(type_map)}.")
        # eShellType: 1=Shell-Thin, 2=Shell-Thick (verificado en vivo: Z40
        # Footing es Shell-Thick; S40 Stiff es Shell-Thin).
        shell = 2 if key in ("footing", "mat") else 1
        oapi.call(
            model.PropArea,
            [("SetSlab", (name, type_map[key], shell, material,
                          float(thickness), -1, "", "")),
             ("SetSlab", (name, type_map[key], shell, material,
                          float(thickness)))],
            f"creacion de la seccion de losa '{name}'",
        )
        got = model.PropArea.GetSlab(name)
        values = _result(got, "PropArea.GetSlab")
        if (int(values[0]) != type_map[key] or int(values[1]) != shell or
                values[2] != material or not _equal_number(values[3], thickness)):
            raise SafeError(f"GetSlab: releido {values[:4]!r}; esperaba "
                            f"{(type_map[key], shell, material, thickness)!r}.")
        return (f"Seccion '{name}' definida: tipo={slab_type} (enum {type_map[key]}), "
                f"shell={'thick' if shell == 2 else 'thin'}, "
                f"espesor={thickness:g}, material '{material}' (verificado releyendo).")

    # ------------------------------------------------------------------
    # Resorte de suelo [namespace y metodo NO VERIFICADOS -- SOP pag. 37,
    # 41-42: 'Area Spring Property', Subgrade Modulus, Compression Only]
    # ------------------------------------------------------------------

    @com_call
    def define_soil_spring(self, name: str, allowable_bearing: float,
                           factor: float = 1.2, compression_only: bool = True) -> str:
        """Define un resorte de area para el suelo (SOP Safe 3.6).

        k = factor * esfuerzo_admisible (factor=1.2 es el valor del SOP).

        Firma confirmada en SAFE 23.3.0. NonlinearOption3 verificado por
        Claude el 2026-09-25: 0=None, 1=Compression Only, 2=Tension Only.
        GetAreaSpringProp no confirma ese valor: se relee por tabla.
        Ver docs/ENUMS-SAFE.md y claude-212.

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
        # NonlinearOption3 VERIFICADO EN VIVO 2026-09-25 [claude] escribiendo
        # 0/1/2 y releyendo la tabla 'Spring Property Definitions - Area
        # Springs': 0=None (lineal), 1=Compression Only, 2=Tension Only.
        # La v0.1.0 usaba 2, que en SAFE es TENSION ONLY (resorte invertido).
        # GetAreaSpringProp devuelve siempre 0 en SAFE 23: NO sirve para
        # releer; se verifica por tabla.
        NONLINEAR_NONE, NONLINEAR_COMPRESSION_ONLY, NONLINEAR_TENSION_ONLY = 0, 1, 2
        nonlinear = NONLINEAR_COMPRESSION_ONLY if compression_only else NONLINEAR_NONE
        oapi.call_checked(
            model.PropAreaSpring, "SetAreaSpringProp",
            (name, 0.0, 0.0, k, nonlinear),
            f"creacion del resorte de suelo '{name}'",
        )
        esperado = "Compression Only" if compression_only else "None"
        _, fields, rows = self._read_table("Spring Property Definitions - Area Springs")
        matches = [dict(zip(fields, row)) for row in rows if row[fields.index("Name")] == name]
        if (len(matches) != 1 or matches[0].get("NonlinOpt3") != esperado or
                any(not _equal_number(matches[0].get(field, "nan"), expected)
                    for field, expected in (("StiffU1", 0), ("StiffU2", 0), ("StiffU3", k)))):
            raise SafeError(f"Resorte no confirmado por tabla: {matches!r}; esperaba k={k}, '{esperado}'.")
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
                _, fields, rows = self._read_table("Area Assignments - Area Springs")
                if not any(row[fields.index("UniqueName")] == aid and
                           row[fields.index("SpringProp")] == spring_name for row in rows):
                    raise SafeError(f"Resorte no confirmado para {aid}.")
            except Exception as e:
                errors.append(f"{aid}: {e}")
        msg = f"Resorte '{spring_name}' asignado a {len(area_ids) - len(errors)} area(s)."
        if errors:
            raise SafeError(msg + f" {len(errors)} fallo(s): " + "; ".join(errors[:5]))
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
                    raise SafeError(f"GetDesignStrip_1({name}): ret={ret2}")
                tipo = {0: "columna", 1: "media", 2: "otra"}.get(dtype, str(dtype))
                rows.append(
                    f"{name} [{tipo}]: {len(pts)} punto(s), "
                    f"anchos B izq/der {wbl[0]:g}/{wbr[0]:g}, "
                    f"A izq/der {wal[0]:g}/{war[0]:g}"
                    + (", auto-widen" if auto and auto[0] else ""))
            except Exception as e:
                raise SafeError(f"GetDesignStrip_1({name}): {e}") from e
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
                raise SafeError(f"{key}: no legible ({e})") from e
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
                raise SafeError(f"{key}: no legible ({e})") from e
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
        n, keys, names, import_type, ret = \
            model.DatabaseTables.GetAvailableTables()
        if ret != 0:
            raise SafeError("Error leyendo la lista de tablas disponibles.")
        # GetAvailableTables: ImportType es int[], no enum declarado.
        # Dominio 0..3 documentado en el CHM; ver docs/ENUMS-SAFE.md.
        rows = []
        for i in range(n):
            if filter and filter.lower() not in str(names[i]).lower():
                continue
            rows.append(f"{keys[i]}: {names[i]} [ImportType={import_type[i]}: "
                        f"{IMPORT_TYPES.get(import_type[i], 'desconocido; confirmar con CSI')}]")
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
    def set_table_data(self, table_key: str, fields: list[str], rows: list[list[str]]) -> str:
        """Escribe filas completas, aplica y relee cada valor. [capa A, T]

        No es una transaccion con rollback: si ApplyEditedTables falla puede
        haber cambios parciales. Trabajar sobre copia. GUID vacio permite a
        SAFE generar uno; los demas valores deben coincidir en la relectura.
        """
        version, available, _ = self._read_table(table_key)
        if not fields or len(set(fields)) != len(fields) or not set(fields) <= set(available):
            raise SafeError("Columnas vacias, repetidas o ajenas al esquema leido.")
        if any(len(row) != len(fields) for row in rows):
            raise SafeError("Todas las filas deben tener exactamente len(fields) valores.")
        expected = [[str(v) for v in row] for row in rows]
        db = self._model().DatabaseTables
        _, count, keys, _, _, _, importable = _result(
            db.GetAllFieldsInTable(table_key), "GetAllFieldsInTable")
        if count != len(keys) or len(importable) != count:
            raise SafeError("GetAllFieldsInTable: metadata incoherente.")
        editable = {key for key, enabled in zip(keys, importable) if enabled}
        write_fields = [field for field in fields if field in editable]
        if not write_fields:
            raise SafeError(f"{table_key}: ninguna columna importable.")
        # NumSegs es de solo lectura segun claude-212; se relee, no se envia.
        flat = [row[fields.index(f)] for row in expected for f in write_fields]
        logger.info("CDX: set_table_data %s: %d filas, %d campos importables",
                    table_key, len(expected), len(write_fields))
        oapi.call_checked(db, "SetTableForEditingArray",
                          (table_key, version, write_fields, len(expected), flat), table_key)
        result = oapi.call_checked(db, "ApplyEditedTables", (False,), table_key)
        fatal, errors, warnings, info, log = oapi.outs(result)
        if fatal or errors:
            raise SafeError(f"{table_key}: fatal={fatal}, errores={errors}, avisos={warnings}: {log}. "
                            "Puede haber cambios parciales; revisar la copia.")
        _, got_fields, got_rows = self._read_table(table_key)
        if not set(fields) <= set(got_fields):
            raise SafeError(f"{table_key}: faltan columnas al releer.")
        actual = [[row[got_fields.index(f)] for f in fields] for row in got_rows]
        # Comparacion independiente del orden de filas. Preserva multiplicidad.
        pending = list(actual)
        for row in expected:
            for i, got in enumerate(pending):
                if all(self._table_cell_equal(f, a, b) for f, a, b in zip(fields, row, got)):
                    pending.pop(i)
                    break
            else:
                raise SafeError(f"{table_key}: fila no confirmada al releer: {row!r}. "
                                "No se revierte automaticamente.")
        if pending:
            raise SafeError(f"{table_key}: {len(pending)} fila(s) inesperadas al releer.")
        return (f"Tabla '{table_key}' escrita y releida: {len(rows)} fila(s). "
                f"Advertencias: {warnings}. {log if warnings else ''}")

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

    # ==================================================================
    # LOTE 1 (claude, 2026-09-25). Herramientas que hoy obligaban a usar
    # control total del PC. Base: docs\OAPI-SAFE-real.md. Cada metodo
    # indica capa A (documentada por CSI para SAFE) o capa B (typelib
    # compartido con ETABS; funciona solo si SAFE lo implementa) y su
    # estado [T] typelib / [H] verificado en vivo / [X] falla en SAFE.
    # Regla: un [T] pasa a [H] solo releyendo el efecto con otra llamada.
    # ==================================================================

    _OBJ_NAMESPACE = {
        "point": "PointObj", "joint": "PointObj",
        "frame": "FrameObj", "line": "FrameObj", "beam": "FrameObj",
        "area": "AreaObj", "surface": "AreaObj", "slab": "AreaObj",
        "footing": "AreaObj", "zapata": "AreaObj", "losa": "AreaObj",
    }
    _SELECT_TYPE_NAMES = {1: "point", 2: "frame", 3: "cable", 4: "tendon",
                          5: "area", 6: "solid", 7: "link"}

    def _ns(self, obj_type: str) -> str:
        key = (obj_type or "").strip().lower()
        ns = self._OBJ_NAMESPACE.get(key)
        if ns is None:
            raise SafeError(f"Tipo no reconocido: '{obj_type}'. "
                            f"Use point, frame o area.")
        return ns

    # ---------------- Archivo (capa A, documentado) ----------------

    @com_call
    def open_model(self, path: str, units: str = "") -> str:
        """Abre un .FDB / .F2K en la instancia activa de SAFE. [capa A]

        El modelo que estuviera abierto se cierra SIN guardar (File.OpenFile
        no pregunta). Guardar antes con save_model si hace falta. Para
        pruebas de escritura usar SIEMPRE una copia (ver copy_model_file).

        Args:
            path: ruta absoluta del archivo.
            units: opcional, unidades activas tras abrir (ej. "N, mm, C").
        """
        if not os.path.isfile(path):
            raise SafeError(f"No existe: {path}")
        model = self._model()
        oapi.call_checked(model.File, "OpenFile", (path,),
                          f"apertura de '{os.path.basename(path)}'")
        if units:
            self.set_units(units)
        return "Abierto. " + self.get_model_info().replace("\n", " | ")

    @com_call
    def close_model(self, save: bool = False) -> str:
        """Cierra el modelo actual dejando SAFE abierto en blanco. [capa A]

        La OAPI no tiene 'cerrar'; File.NewBlank es el equivalente.
        """
        model = self._model()
        try:
            filename = model.GetModelFilename()
        except Exception:
            filename = "(sin nombre)"
        if save:
            oapi.call_checked(model.File, "Save", (), "guardado previo")
        oapi.call_checked(model.File, "NewBlank", (), "modelo en blanco")
        return (f"Cerrado {filename}{' (guardado)' if save else ' (sin guardar)'}. "
                f"SAFE sigue abierto en blanco.")

    @com_call
    def copy_model_file(self, dest_path: str, overwrite: bool = False) -> str:
        """Copia en disco el .FDB abierto a dest_path SIN cambiar el modelo activo.

        Sirve para crear la copia de pruebas (_pruebas-mcp.FDB) antes de
        cualquier escritura. Copia el archivo tal como esta guardado en disco:
        si hay cambios sin guardar, guardarlos primero con save_model.
        """
        import shutil
        model = self._model()
        src = model.GetModelFilename()
        if not src or not os.path.isfile(src):
            raise SafeError(f"El modelo activo no tiene archivo en disco: {src!r}")
        if os.path.exists(dest_path) and not overwrite:
            raise SafeError(f"Ya existe {dest_path}; use overwrite=True.")
        shutil.copy2(src, dest_path)
        return f"Copiado {src} -> {dest_path} ({os.path.getsize(dest_path)} bytes)."

    # ---------------- Llamada generica (capa A/B, [H] patron de ETABS) --

    @com_call
    def call_oapi(self, path: str, method: str,
                  args: list[Any] | None = None) -> str:
        """Invoca CUALQUIER metodo de la OAPI y devuelve ret y [out] crudos.

        Consultar primero describe_oapi(path, method) para la firma real:
        los argumentos [in] se pasan en orden; los [out] NO se pasan
        (comtypes los devuelve). Arreglos [in] se pasan como listas JSON.
        Puede ESCRIBIR en el modelo: cada llamada queda en el log. No hay
        deshacer. Es la via para convertir cada [T] de OAPI-SAFE-real.md
        en [H] o [X] sin escribir una tool por prueba.

        Args:
            path: namespace bajo SapModel, ej. "AreaObj", "File",
                  "DesignConcreteSlab.DesignStrip". Vacio = SapModel.
            method: nombre exacto del metodo, ej. "GetProperty".
            args: lista de argumentos [in], ej. ["12"].
        """
        import json
        model = self._model()
        target = oapi.resolve_path(model, path) if path else model
        fn = getattr(target, method, None)
        if fn is None:
            raise SafeError(f"'{method}' no existe en SapModel.{path or ''}. "
                            f"Use describe_oapi.")
        args = list(args or [])
        logger.warning("call_oapi SapModel.%s.%s(%r)", path, method, args)
        try:
            result = fn(*args)
        except Exception as e:
            raise SafeError(f"SapModel.{path}.{method}{tuple(args)!r} fallo: {e}")
        # Estos getters devuelven el valor directamente, no pRetVal.
        if not path and method in {"GetModelFilename", "GetModelIsLocked", "GetPresentUnits"}:
            return json.dumps({"ret": None, "value": result}, ensure_ascii=False)
        _result(result, f"{path}.{method}")
        code = oapi.ret_code(result)
        outs = [list(v) if isinstance(v, (tuple, list)) else v
                for v in oapi.outs(result)]
        return json.dumps({"ret": code, "outs": outs,
                           "raw_type": type(result).__name__},
                          ensure_ascii=False, default=str)

    # ---------------- Seleccion (capa A SelectObj + capa B SetSelected) --

    @com_call
    def clear_selection(self) -> str:
        """Deselecciona todo (SelectObj.ClearSelection). [capa A]"""
        model = self._model()
        oapi.call(model.SelectObj, [("ClearSelection", ())], "limpieza de seleccion")
        n, _, _ = _result(model.SelectObj.GetSelected(), "GetSelected")
        if n:
            raise SafeError("ClearSelection: quedan objetos seleccionados.")
        return "Seleccion limpiada."

    @com_call
    def select_objects(self, obj_type: str, names: list[str],
                       clear_first: bool = True) -> str:
        """Selecciona objetos por tipo y nombre (AreaObj/PointObj/FrameObj.SetSelected). [capa B, T]

        Args:
            obj_type: "point", "frame" o "area".
            names: IDs (los que devuelven get_points / get_areas).
            clear_first: limpiar la seleccion previa (recomendado).
        """
        ns = self._ns(obj_type)
        if not names:
            raise SafeError("Debe indicar al menos un nombre.")
        model = self._model()
        if clear_first:
            oapi.call(model.SelectObj, [("ClearSelection", ())], "limpieza previa")
        owner = getattr(model, ns)
        for name in names:
            oapi.call(owner, [("SetSelected", (str(name), True)),
                              ("SetSelected", (str(name), True, 0))],
                      f"seleccion de {ns} '{name}'")
        _, types, selected = _result(model.SelectObj.GetSelected(), "GetSelected")
        kind = {"PointObj": 1, "FrameObj": 2, "AreaObj": 5}[ns]
        got = set(zip(types, selected))
        wanted = {(kind, str(name)) for name in names}
        if not wanted <= got or (clear_first and got != wanted):
            raise SafeError("SetSelected: seleccion distinta al releer.")
        return f"{len(names)} {ns}(s) seleccionado(s)."

    @com_call
    def get_selection(self) -> str:
        """Lista lo seleccionado ahora (SelectObj.GetSelected). [capa A]"""
        model = self._model()
        n, types, names, ret = model.SelectObj.GetSelected()
        if ret != 0:
            raise SafeError("GetSelected devolvio error.")
        if n == 0:
            return "Nada seleccionado."
        rows = [f"{self._SELECT_TYPE_NAMES.get(types[i], types[i])} {names[i]}"
                for i in range(n)]
        return f"{n} objeto(s):\n" + "\n".join(rows)

    # ---------------- Geometria: borrar / mover / editar (capa B, [T]) --

    @com_call
    def delete_object(self, obj_type: str, name: str) -> str:
        """Borra un objeto por tipo y nombre (AreaObj/PointObj/FrameObj.Delete). [capa B, T]

        Sin deshacer. Trabajar sobre copia. Un punto compartido por un
        area no se borra hasta que el area deje de usarlo.
        """
        ns = self._ns(obj_type)
        model = self._model()
        owner = getattr(model, ns)
        if ns == "PointObj":
            # PointObj no tiene Delete en el typelib; DeleteSpecialPoint
            # borra el punto si ningun objeto lo usa. [H] 2026-09-25.
            oapi.call(owner, [("DeleteSpecialPoint", (str(name), 0)),
                              ("DeleteSpecialPoint", (str(name),))],
                      f"borrado del punto '{name}'")
            x, y, z, r = model.PointObj.GetCoordCartesian(str(name))
            if r == 0:
                raise SafeError(f"El punto {name} sigue existiendo en ({x:g},{y:g},{z:g}): "
                                f"probablemente lo usa un area o franja.")
            if r != 1:
                raise SafeError(f"DeleteSpecialPoint: relectura ret={r}; ausencia no confirmada.")
            return f"Punto '{name}' borrado (verificado releyendo)."
        oapi.call(owner, [("Delete", (str(name), 0)), ("Delete", (str(name),))],
                  f"borrado de {ns} '{name}'")
        if ns == "AreaObj":
            prop, r = model.AreaObj.GetProperty(str(name))
            if r == 0:
                raise SafeError(f"El area {name} sigue existiendo (seccion {prop}).")
            if r != 1:
                raise SafeError(f"Delete: relectura ret={r}; ausencia no confirmada.")
        return f"{ns} '{name}' borrado (verificado releyendo)."

    @com_call
    def move_objects(self, obj_type: str, names: list[str],
                     dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> str:
        """Traslada seleccion y confirma coordenadas de sus vertices. [capa B, T]

        Si SAFE fusiona puntos y cambia sus IDs, la verificacion falla;
        inspeccionar el modelo antes de repetir la escritura.
        """
        ns = self._ns(obj_type)
        if not names:
            raise SafeError("Debe indicar al menos un nombre.")
        model = self._model()
        before = {}
        for name in names:
            if ns == "PointObj":
                points = [str(name)]
            elif ns == "AreaObj":
                points = self._area_points(str(name))
            else:
                points = _result(model.FrameObj.GetPoints(str(name)), "FrameObj.GetPoints")
            before[str(name)] = [self._coords(pt) for pt in points]
        try:
            self.select_objects(obj_type, names)
            oapi.call_checked(model.EditGeneral, "Move", (float(dx), float(dy), float(dz)))
            for name, original in before.items():
                # SAFE puede generar otros IDs de vertices al mover un area
                # compartida: releer conectividad, no los IDs anteriores (§7).
                points = ([name] if ns == "PointObj" else self._area_points(name)
                          if ns == "AreaObj" else _result(model.FrameObj.GetPoints(name), "FrameObj.GetPoints"))
                got = [self._coords(pt) for pt in points]
                expected = [tuple(a + d for a, d in zip(xyz, (dx, dy, dz))) for xyz in original]
                if len(got) != len(expected) or not got or not any(
                        all(all(_equal_number(a, b) for a, b in zip(got[(i + shift) % len(got)], xyz))
                            for i, xyz in enumerate(expected)) for shift in range(len(got))):
                    raise SafeError(f"Move: {name}, releido {got!r}, delta no confirmado.")
        finally:
            self.clear_selection()
        return f"{len(names)} {ns}(s) desplazado(s) y releidos: dx={dx:g}, dy={dy:g}, dz={dz:g}."

    @com_call
    def get_area_info(self, name: str) -> str:
        """Propiedad, vertices, abertura y espesor de UN area (AreaObj.Get*). [capa B, T]"""
        model = self._model()
        ao = model.AreaObj
        prop, = _result(ao.GetProperty(str(name)), "GetProperty")
        npts, pts = _result(ao.GetPoints(str(name)), "GetPoints")
        is_open, = _result(ao.GetOpening(str(name)), "GetOpening")
        r1 = r2 = r3 = 0
        coords = []
        for p in list(pts)[:npts]:
            x, y, z = self._coords(str(p))
            coords.append(f"{p}:({x:g},{y:g},{z:g})")
        return (f"Area {name}: seccion={prop} (ret {r1}); abertura={is_open} (ret {r3}); "
                f"{npts} vertice(s) (ret {r2}): " + " ".join(coords))

    @com_call
    def set_area_property(self, name: str, section: str) -> str:
        """Cambia la seccion de losa/zapata de un area (AreaObj.SetProperty). [capa B, T]

        Args:
            name: ID del area.
            section: nombre de seccion existente (ver tabla 'Slab Property Definitions').
        """
        model = self._model()
        oapi.call(model.AreaObj, [("SetProperty", (str(name), section, 0)),
                                  ("SetProperty", (str(name), section))],
                  f"SetProperty {name} -> {section}")
        prop, = _result(model.AreaObj.GetProperty(str(name)), "GetProperty")
        if prop != section:
            raise SafeError(f"Releido '{prop}', esperaba '{section}'.")
        return f"Area {name}: seccion = {prop} (verificado releyendo)."

    @com_call
    def set_area_opening(self, name: str, is_opening: bool = True,
                         section: str = "") -> str:
        """Marca/desmarca un area como abertura (AreaObj.SetOpening). [capa B, H 2026-09-25]

        VERIFICADO: SetOpening(True) deja la seccion del area en None y
        SetOpening(False) NO la restaura. Al desmarcar, pasar `section`
        (ej. "Z40") para reasignarla; si se omite se reasigna la que tenia
        antes de esta misma llamada, cuando se conoce.
        """
        model = self._model()
        antes, = _result(model.AreaObj.GetProperty(str(name)), "GetProperty")
        oapi.call(model.AreaObj, [("SetOpening", (str(name), bool(is_opening), 0)),
                                  ("SetOpening", (str(name), bool(is_opening)))],
                  f"SetOpening {name}")
        val, = _result(model.AreaObj.GetOpening(str(name)), "GetOpening")
        if bool(val) != bool(is_opening):
            raise SafeError("SetOpening: abertura distinta al releer.")
        if is_opening:
            return (f"Area {name}: abertura = {val} (releido); la seccion previa "
                    f"'{antes}' queda en None mientras sea abertura.")
        destino = section or (antes if antes and antes != "None" else "")
        if destino:
            oapi.call(model.AreaObj, [("SetProperty", (str(name), destino, 0))],
                      f"SetProperty {name} -> {destino}")
        prop, = _result(model.AreaObj.GetProperty(str(name)), "GetProperty")
        if destino and prop != destino:
            raise SafeError(f"SetOpening: seccion '{prop}', esperaba '{destino}'.")
        aviso = "" if prop != "None" else " (SIN SECCION: repetir con section=...)"
        return f"Area {name}: abertura = {val} (releido); seccion = {prop}{aviso}."

    @com_call
    def set_point_coordinates(self, name: str, x: float, y: float,
                              z: float) -> str:
        """Mueve UN punto a coordenadas absolutas (SetSelected + EditGeneral.Move). [capa B, H 2026-09-25]

        Arrastra las areas que comparten el punto: es la via limpia para
        ajustar una esquina de zapata. Unidades activas.
        """
        # EditPoint.ChangeCoordinates devuelve -99 en SAFE 23 [X 2026-09-25].
        # Via que SI funciona [H]: seleccionar el punto y EditGeneral.Move
        # con el delta. Si el destino coincide con otro punto, SAFE los
        # fusiona y el nombre puede pasar a ser el del punto existente.
        model = self._model()
        x0, y0, z0, r = model.PointObj.GetCoordCartesian(str(name))
        if r != 0:
            raise SafeError(f"El punto {name} no existe.")
        self.move_objects("point", [str(name)], float(x) - x0, float(y) - y0, float(z) - z0)
        rx, ry, rz, r = model.PointObj.GetCoordCartesian(str(name))
        if r != 0:
            raise SafeError(f"Punto {name}: no se pudo releer; posible fusion, no confirmada.")
        if abs(rx - x) > 1e-6 or abs(ry - y) > 1e-6 or abs(rz - z) > 1e-6:
            raise SafeError(f"Releido ({rx:g},{ry:g},{rz:g}), esperaba ({x:g},{y:g},{z:g}).")
        return f"Punto {name}: ({x0:g},{y0:g},{z0:g}) -> ({rx:g},{ry:g},{rz:g}) (releido)."

    @com_call
    def set_area_points(self, name: str, point_names: list[str]) -> str:
        """Redefine los vertices de un area (EditArea.ChangeConnectivity). [capa B, X en SAFE 23: ret -99 el 2026-09-25]

        NO FUNCIONA en SAFE 23.3.0. Alternativa verificada: move_objects("point", [...])
        sobre los vertices (arrastra el contorno) o borrar y recrear el area.

        Args:
            name: ID del area.
            point_names: IDs de puntos existentes, en orden de contorno.
        """
        if len(point_names) < 3:
            raise SafeError("Se necesitan al menos 3 puntos.")
        model = self._model()
        pts = [str(p) for p in point_names]
        oapi.call(model.EditArea,
                  [("ChangeConnectivity", (str(name), len(pts), pts))],
                  f"ChangeConnectivity {name}")
        got = self._area_points(str(name))
        if got != pts:
            raise SafeError(f"ChangeConnectivity: releido {got!r}, esperaba {pts!r}.")
        return f"Area {name}: vertices ahora {got} (releido)."

    # ---------------- Puntos y cargas puntuales (capa B, [T]) ----------

    @com_call
    def add_point(self, x: float, y: float, z: float = 0.0,
                  user_name: str = "") -> str:
        """Crea un punto (PointObj.AddCartesian). [capa B, T]"""
        model = self._model()
        res = oapi.call(model.PointObj,
                        [("AddCartesian", (float(x), float(y), float(z), "", user_name)),
                         ("AddCartesian", (float(x), float(y), float(z), ""))],
                        "AddCartesian")
        name = None
        for v in oapi.outs(res):
            if isinstance(v, str) and v:
                name = v
        if not name or not all(_equal_number(a, b) for a, b in zip(self._coords(name), (x, y, z))):
            raise SafeError("AddCartesian: coordenadas distintas al releer.")
        return f"Punto '{name}' creado en ({x:g}, {y:g}, {z:g}) (releido)."

    @com_call
    def assign_point_load(self, name: str, load_pattern: str,
                          fx: float = 0.0, fy: float = 0.0, fz: float = 0.0,
                          mx: float = 0.0, my: float = 0.0, mz: float = 0.0,
                          replace: bool = True) -> str:
        """Carga puntual de columna sobre un punto (PointObj.SetLoadForce). [capa B, T]

        Fuerzas y momentos en el sistema Global, unidades activas.
        fz negativo = hacia abajo (compresion sobre la zapata).
        """
        model = self._model()
        vals = [float(v) for v in (fx, fy, fz, mx, my, mz)]
        before = self._point_load(str(name), load_pattern) if not replace else [0.0] * 6
        oapi.call(model.PointObj,
                  [("SetLoadForce", (str(name), load_pattern, vals, bool(replace), "Global", 0)),
                   ("SetLoadForce", (str(name), load_pattern, vals, bool(replace)))],
                  f"SetLoadForce {name}/{load_pattern}")
        got = self._point_load(str(name), load_pattern, required=True)
        expected = [v + b for v, b in zip(vals, before)]
        if not all(_equal_number(a, b) for a, b in zip(got, expected)):
            raise SafeError(f"GetLoadForce: releido {got!r}, esperaba {expected!r}.")
        n = 1
        return (f"Carga {load_pattern} en punto {name}: F=({fx:g},{fy:g},{fz:g}) "
                f"M=({mx:g},{my:g},{mz:g}). El punto tiene ahora {n} carga(s) (releido).")

    # ---------------- Diseño: acero requerido por estacion (capa B) -----

    @com_call
    def get_strip_rebar_stations(self, strip_filter: str = "",
                                 max_rows: int = 60, offset: int = 0) -> str:
        """Acero requerido por estacion de franja (DesignConcreteSlab.GetFlexureAndShear). [capa B, T]

        Requiere run_slab_design. Devuelve por estacion: ancho, combo y
        momento/As arriba y abajo (con As minimo), cortante y estado.

        Args:
            strip_filter: subcadena del nombre de franja (vacio = todas).
            max_rows, offset: paginacion sobre las filas filtradas.
        """
        model = self._model()
        res = model.DesignConcreteSlab.GetFlexureAndShear()
        ret = res[-1]
        if ret != 0:
            raise SafeError("GetFlexureAndShear devolvio error. ¿Diseño corrido?")
        (story, strip, station, width, ftc, ftm, fta, ftmin, fbc, fbm, fba,
         fbmin, axial, vc, vf, va, status, gx, gy, layer) = res[:20]
        rows = []
        for i in range(len(strip)):
            if strip_filter and strip_filter.lower() not in str(strip[i]).lower():
                continue
            rows.append(f"{strip[i]}, {layer[i]}, {station[i]:g}, {width[i]:g}, "
                        f"{ftc[i]}, {ftm[i]:g}, {fta[i]:g}, {ftmin[i]:g}, "
                        f"{fbc[i]}, {fbm[i]:g}, {fba[i]:g}, {fbmin[i]:g}, "
                        f"{vc[i]}, {vf[i]:g}, {va[i]:g}, {status[i]}, {gx[i]:g}, {gy[i]:g}")
        total = len(rows)
        page = rows[offset:offset + max_rows]
        header = ("Strip, Layer, Station, Width, TopCombo, TopM, TopAs, TopAsMin, "
                  "BotCombo, BotM, BotAs, BotAsMin, VCombo, V, VAs, Status, X, Y")
        resto = total - (offset + len(page))
        suf = f"\n... ({resto} mas; offset={offset + len(page)})" if resto > 0 else ""
        return f"{total} estacion(es)\n{header}\n" + "\n".join(page) + suf

    # CDX: lote 2. Helpers privados: nunca se registran como tools MCP.

    def _coords(self, name):
        return _result(self._model().PointObj.GetCoordCartesian(name), "GetCoordCartesian")

    def _area_points(self, name):
        n, points = _result(self._model().AreaObj.GetPoints(name), "GetPoints")
        if n != len(points):
            raise SafeError("GetPoints: longitud incoherente.")
        return [str(p) for p in points]

    def _point_load(self, name, pattern, required=False):
        # SAFEv1.cPointObj.GetLoadForce: n, point, pattern, step, csys,
        # F1/F2/F3/M1/M2/M3, ret (wrapper, lineas 10859-10873).
        n, names, patterns, steps, systems, *components = _result(
            self._model().PointObj.GetLoadForce(name), "GetLoadForce")
        arrays = [names, patterns, steps, systems, *components]
        if len(components) != 6 or any(len(a) != n for a in arrays):
            raise SafeError("GetLoadForce: forma incoherente.")
        indices = [i for i in range(n) if names[i] == name and patterns[i] == pattern]
        if required and not indices:
            raise SafeError("GetLoadForce: asignacion no encontrada al releer.")
        if any(systems[i] != "Global" for i in indices):
            raise SafeError("GetLoadForce: no se comparan cargas en otro sistema de coordenadas.")
        if len({steps[i] for i in indices}) > 1:
            raise SafeError("GetLoadForce: varios pasos de carga; comparacion ambigua.")
        return [sum(float(c[i]) for i in indices) for c in components]

    def _read_table(self, key):
        echo, version, fields, n, flat = _result(
            self._model().DatabaseTables.GetTableForDisplayArray(key, [], "", 0),
            f"GetTableForDisplayArray({key})")
        fields, flat = list(fields), list(flat)
        if not fields or len(set(fields)) != len(fields) or n < 0 or len(flat) != n * len(fields):
            raise SafeError(f"{key}: esquema o longitud de datos incoherente.")
        return version, fields, [list(map(str, flat[i:i + len(fields)]))
                                for i in range(0, len(flat), len(fields))]

    @staticmethod
    def _table_cell_equal(field, expected, actual):
        if expected == actual:
            return True
        if field == "GUID" and expected == "":
            return bool(actual)
        # IDs numericos ("001") no equivalen a "1". Solo normalizar medidas.
        if field in {"NumSegs", "WStartLeft", "WStartRight", "WEndLeft", "WEndRight"}:
            try:
                return _equal_number(expected, actual)
            except (TypeError, ValueError):
                pass
        return False

    def _editable_table(self, key, required):
        model = self._model()
        n, keys, _, types = _result(model.DatabaseTables.GetAvailableTables(), "GetAvailableTables")
        if key not in keys:
            raise SafeError(f"{key}: no disponible; no se inventa un esquema.")
        kind = types[list(keys).index(key)]
        if kind not in (2, 3):
            raise SafeError(f"{key}: ImportType={kind}, no admite edicion interactiva.")
        if kind == 2 and model.GetModelIsLocked():
            raise SafeError(f"{key}: requiere modelo desbloqueado; no se desbloquea automaticamente.")
        _, fields, rows = self._read_table(key)
        if set(fields) != set(required):
            raise SafeError(f"{key}: esquema distinto de OAPI-SAFE-real.md §6.1: {fields!r}.")
        return fields, rows

    _STRIP_TABLE = "Strip Object Connectivity"
    _STRIP_FIELDS = ("Name", "NumSegs", "StartPoint", "EndPoint", "WStartLeft",
                     "WStartRight", "WEndLeft", "WEndRight", "AutoWiden", "Layer", "GUID")
    _PUNCH_TABLE = "Concrete Slab Design Overwrites - Punching Shear - General"
    _PUNCH_FIELDS = ("UniqueName", "CheckPunchingShear", "LocationType", "Perimeter",
                     "EffDepthType", "OpeningDef", "RebarType")

    @staticmethod
    def _width(value):
        if not math.isfinite(value) or value < 0:
            raise SafeError("Semi-anchos deben ser finitos y no negativos.")
        return format(value, ".15g")

    @com_call
    def add_design_strip(self, name: str, start_point: str, end_point: str,
                         w_left: float, w_right: float, layer: str = "A",
                         auto_widen: bool = False) -> str:
        """Crea franja de un segmento por tabla completa y relee. [capa A, T]

        Semi-anchos en unidades activas, iguales al inicio y final. Layer=A/B.
        AutoWiden se envia Yes/No: confirmar Yes en la corrida viva.
        No sobrescribe nombres existentes ni desbloquea el modelo.
        """
        if not name.strip() or layer not in ("A", "B") or start_point == end_point:
            raise SafeError("Nombre no vacio, capa A/B y puntos distintos requeridos.")
        left, right = self._width(w_left), self._width(w_right)
        if left == right == "0":
            raise SafeError("El ancho total debe ser positivo.")
        fields, rows = self._editable_table(self._STRIP_TABLE, self._STRIP_FIELDS)
        if any(row[fields.index("Name")] == name for row in rows):
            raise SafeError(f"La franja '{name}' ya existe.")
        a, b = self._coords(start_point), self._coords(end_point)
        if all(_equal_number(x, y) for x, y in zip(a, b)):
            raise SafeError("Los extremos de la franja coinciden geometricamente.")
        values = dict(zip(self._STRIP_FIELDS, (name, "1", start_point, end_point,
                           left, right, left, right, "Yes" if auto_widen else "No", layer, "")))
        rows.append([values[f] for f in fields])
        return self.set_table_data(self._STRIP_TABLE, fields, rows)

    @com_call
    def set_strip_widths(self, name: str, w_start_left: float, w_start_right: float,
                         w_end_left: float, w_end_right: float) -> str:
        """Cambia semi-anchos de una franja de un segmento. [capa A, T]

        Unidades activas. Conserva AutoWiden y todas las otras filas/columnas.
        Rechaza franjas multisegmento: hace falta un selector por segmento.
        Con AutoWiden=Yes SAFE puede recalcular anchos; la relectura lo detecta.
        """
        widths = [self._width(v) for v in (w_start_left, w_start_right, w_end_left, w_end_right)]
        if widths[:2] == ["0", "0"] or widths[2:] == ["0", "0"]:
            raise SafeError("El ancho total debe ser positivo en ambos extremos.")
        fields, rows = self._editable_table(self._STRIP_TABLE, self._STRIP_FIELDS)
        matches = [row for row in rows if row[fields.index("Name")] == name]
        if len(matches) != 1 or matches[0][fields.index("NumSegs")] != "1":
            raise SafeError("Se requiere una franja existente de un unico segmento.")
        for field, width in zip(self._STRIP_FIELDS[4:8], widths):
            matches[0][fields.index(field)] = width
        return self.set_table_data(self._STRIP_TABLE, fields, rows)

    @com_call
    def set_punching_overwrite(self, point: str, check: str | None = None,
                               location: str | None = None, perimeter: str | None = None,
                               eff_depth: str | None = None, opening: str | None = None,
                               rebar_type: str | None = None) -> str:
        """Edita overwrite de punzonamiento por tabla completa. [capa A, T]

        None conserva la columna. Para agregar fila nueva se requieren todos
        los valores: no se inventan defaults. eff_depth es EffDepthType (texto),
        no una profundidad numerica. Dominios pendientes de Claude: el XML
        no los declara. SAFE debe aceptar y devolver exactamente cada texto.
        """
        values = (check, location, perimeter, eff_depth, opening, rebar_type)
        if not point.strip() or any(v is not None and not v.strip() for v in values):
            raise SafeError("Punto y valores especificados no pueden estar vacios.")
        fields, rows = self._editable_table(self._PUNCH_TABLE, self._PUNCH_FIELDS)
        matches = [row for row in rows if row[fields.index("UniqueName")] == point]
        if len(matches) > 1:
            raise SafeError("UniqueName duplicado: no se elige una fila arbitraria.")
        if not matches:
            if any(v is None for v in values):
                raise SafeError("Fila nueva requiere los seis valores; defaults no confirmados.")
            self._coords(point)
            row = [""] * len(fields)
            row[fields.index("UniqueName")] = point
            rows.append(row)
        else:
            row = matches[0]
        if all(v is None for v in values):
            return f"Punto {point}: sin cambios solicitados."
        for field, value in zip(self._PUNCH_FIELDS[1:], values):
            if value is not None:
                row[fields.index(field)] = value
        return self.set_table_data(self._PUNCH_TABLE, fields, rows)

    # ---------------- Tablas: campos y tipo de importacion (capa A) -----

    @com_call
    def get_table_fields(self, table_key: str) -> str:
        """Campos de una tabla (DatabaseTables.GetAllFieldsInTable): clave, nombre, descripcion, importable. [capa A]"""
        model = self._model()
        res = model.DatabaseTables.GetAllFieldsInTable(table_key)
        ret = res[-1]
        if ret != 0:
            raise SafeError(f"No se pudo leer los campos de '{table_key}'.")
        # Firma ETABS: (TableVersion, NumberFields, FieldKey[], FieldName[],
        # Description[], UnitsString[], IsImportable[], ret)
        vals = list(res[:-1])
        lists = [v for v in vals if isinstance(v, (tuple, list))]
        if len(lists) < 2:
            return f"Respuesta cruda: {res!r}"
        keys, names = lists[0], lists[1]
        desc = lists[2] if len(lists) > 2 else [""] * len(keys)
        units = lists[3] if len(lists) > 3 else [""] * len(keys)
        imp = lists[4] if len(lists) > 4 else [""] * len(keys)
        rows = [f"{keys[i]} | {names[i]} | {units[i]} | importable={imp[i]} | {desc[i]}"
                for i in range(len(keys))]
        return f"{table_key}: {len(keys)} campo(s)\n" + "\n".join(rows)

    # ==================================================================
    # PILOTES (claude, 2026-11-02). Separacion S/B con el factor de grupo de
    # la tabla 5.1 del MOPC R-024 y reaccion axial por pilote. SOLO LECTURA:
    # nunca File.Save (sin ruta cuelga el hilo COM; con ruta descarta
    # resultados). El criterio vive en src/pilotes.py (puro, sin COM).
    #
    # Via elegida para leer frames: OAPI directa, no tablas ni call_oapi.
    #   FrameObj.GetAllFrames() py-> (n, Name[], PropName[], Story[], P1[],
    #     P2[], X1[], Y1[], Z1[], X2[], Y2[], Z2[], Angle[], Offset..[6],
    #     CardinalPoint[], ret)  -- UNA llamada COM para los 1112 pilotes,
    #     con extremos y seccion; por tabla serian 3 lecturas + parseo.
    #   PropFrame.GetNameList(n, names, PropType=9) + GetTypeOAPI(Name)
    #     py-> (PropType, ret): 9 = Circle (enum eFramePropType, typelib).
    #   PropFrame.GetCircle(Name) py-> (FileName, MatProp, T3, Color, notes,
    #     GUID, ret): T3 es el diametro.
    #   Results.Setup.DeselectAllCasesAndCombosForOutput / Set*SelectedForOutput
    #   Results.JointReact(Name, 0) py-> (n, Obj, Elm, LoadCase, StepType,
    #     StepNum, F1, F2, F3, M1, M2, M3, ret)
    #   Results.FrameForce(Name, 0) py-> (n, Obj, ObjSta, Elm, ElmSta,
    #     LoadCase, StepType, StepNum, P, V2, V3, T, M2, M3, ret)
    # Firmas del typelib SAFEv1 real (SAFE 23 NativeAPI). Estado [T] hasta
    # corrida viva de Claude; ver docs/PRUEBA-VIVA-PILOTES.md.
    # ==================================================================

    _FRAME_PROP_CIRCLE = 9       # eFramePropType_Circle
    _ITEM_TYPE_OBJECT = 0        # eItemTypeElm_ObjectElm
    _CASE_FINISHED = 4           # Analyze.GetCaseStatus
    _LENGTH_MM = {"in": 25.4, "ft": 304.8, "mm": 1.0, "m": 1000.0, "cm": 10.0}
    _SLAB_TYPES = {"slab": 0, "drop": 1, "stiff": 2, "ribbed": 3, "waffle": 4, "mat": 5, "footing": 6}

    def _unidades_activas(self) -> tuple[int, str, str, str]:
        idx = self._model().GetPresentUnits()
        if not (1 <= idx <= len(PRESET_UNITS)):
            raise SafeError("No se pudieron determinar las unidades activas.")
        force, length, _t = [s.strip() for s in PRESET_UNITS[idx - 1].split(",")]
        return idx, PRESET_UNITS[idx - 1], force, length

    def _con_unidades(self, units: str, fn):
        """Fija unidades, ejecuta fn y restaura las previas (lectura sin huella)."""
        model = self._model()
        previo = model.GetPresentUnits()
        try:
            self.set_units(units)
            return fn()
        finally:
            # set_units puede fallar DESPUES de cambiar las unidades: restaurar siempre.
            if 1 <= previo <= len(PRESET_UNITS) and model.GetPresentUnits() != previo:
                if model.SetPresentUnits(previo) != 0 or model.GetPresentUnits() != previo:
                    logger.error("No se pudieron restaurar las unidades previas (%s).", PRESET_UNITS[previo - 1])

    def _frames_todos(self) -> list[dict]:
        outs = _result(self._model().FrameObj.GetAllFrames(), "FrameObj.GetAllFrames")
        if len(outs) < 12:
            raise SafeError(f"GetAllFrames: forma inesperada ({len(outs)} salidas).")
        n, names, props, _story, p1, p2, x1, y1, z1, x2, y2, z2 = outs[:12]
        arrays = (names, props, p1, p2, x1, y1, z1, x2, y2, z2)
        if any(len(a) != n for a in arrays):
            raise SafeError("GetAllFrames: longitud de arreglos incoherente con NumberNames.")
        return [{"id": str(names[i]), "seccion": str(props[i]), "p1": str(p1[i]), "p2": str(p2[i]),
                 "x1": float(x1[i]), "y1": float(y1[i]), "z1": float(z1[i]),
                 "x2": float(x2[i]), "y2": float(y2[i]), "z2": float(z2[i])} for i in range(n)]

    def _secciones_circulares(self) -> dict[str, dict]:
        pf = self._model().PropFrame
        n, names = _result(pf.GetNameList(0, [], self._FRAME_PROP_CIRCLE), "PropFrame.GetNameList")[:2]
        if len(names) != n:
            raise SafeError(f"PropFrame.GetNameList: {len(names)} nombres para NumberNames={n}.")
        out: dict[str, dict] = {}
        for name in names:
            # ret=0 fuera de rango es falso exito: se confirma el tipo de cada una.
            tipo, = _result(pf.GetTypeOAPI(name), f"PropFrame.GetTypeOAPI({name})")
            if int(tipo) != self._FRAME_PROP_CIRCLE:
                continue
            _file, material, t3, *_rest = _result(pf.GetCircle(name), f"PropFrame.GetCircle({name})")
            if float(t3) <= 0:
                raise SafeError(f"PropFrame.GetCircle({name}): diametro {t3!r} no valido.")
            out[str(name)] = {"diametro": float(t3), "material": str(material)}
        return out

    def _cabezales(self, cap_types: str) -> list[dict]:
        """Areas de cabezal: por tipo de losa (footing, mat...) o por NOMBRE de seccion (p. ej. Z50).

        cap_types es una lista separada por comas; cada token que no sea un tipo de losa se
        toma como nombre de seccion de area y debe existir en el modelo.
        """
        tipos, secciones = set(), set()
        for t in cap_types.split(","):
            key = t.strip()
            if not key:
                continue
            if key.lower() in self._SLAB_TYPES:
                tipos.add(self._SLAB_TYPES[key.lower()])
            else:
                secciones.add(key)
        if not tipos and not secciones:
            raise SafeError("cap_types vacio: indique tipos de losa (footing, mat...) o nombres de seccion (Z50).")
        model = self._model()
        cache: dict[str, int | None] = {}
        out, vistas = [], set()
        for area in self.get_areas():
            prop, = _result(model.AreaObj.GetProperty(area.id), f"AreaObj.GetProperty({area.id})")
            prop = str(prop)
            vistas.add(prop)
            if prop in secciones:
                out.append({"id": area.id, "seccion": prop, "xs": list(area.xs), "ys": list(area.ys)})
                continue
            if not tipos:
                continue
            if prop not in cache:
                if not prop or prop == "None":
                    cache[prop] = None
                else:
                    cache[prop] = int(_result(model.PropArea.GetSlab(prop), f"PropArea.GetSlab({prop})")[0])
            if cache[prop] in tipos:
                out.append({"id": area.id, "seccion": prop, "xs": list(area.xs), "ys": list(area.ys)})
        faltan = sorted(secciones - vistas)
        if faltan:
            raise SafeError(f"cap_types: ninguna area usa la(s) seccion(es) {faltan}. Secciones de area del "
                            f"modelo: {sorted(v for v in vistas if v)}.")
        return out

    def _pilotes_leidos(self, sections, diameter: float, mm: float, necesita_diametro: bool):
        frames = self._frames_todos()
        secciones = self._secciones_circulares()
        try:
            pil, avisos = pilotes.pilotes_desde_frames(
                frames, secciones, sections, diameter, tol_inclinacion=1.0 / mm,
                necesita_diametro=necesita_diametro)
        except pilotes.PilotesError as e:
            raise SafeError(str(e)) from e
        if not pil:
            raise SafeError(f"Ningun frame usa las secciones {sections!r}. Secciones circulares del "
                            f"modelo: {sorted(secciones) or 'ninguna'}; frames: {len(frames)}.")
        return pil, avisos, secciones, len(frames)

    @com_call
    def get_pile_spacing(self, sections: str | list[str] = "auto", diameter_mm: float = 0.0,
                         scope: str = "nearest_neighbor", neighbors: int = 1,
                         interpolation: str = "step_down", units: str = "kN, m, C",
                         cap_types: str = "footing", q_ult: float = 0.0, fs: float = 0.0,
                         q_adm: float = 0.0, max_detail: int = 300) -> str:
        """Separacion entre pilotes, S/B y factor de grupo de la tabla 5.1 del MOPC R-024. [T, solo lectura]

        Lee los frames de pilote (FrameObj.GetAllFrames) y sus secciones circulares
        (PropFrame), toma la cabeza como el extremo de Z mayor y mide la distancia
        en planta al vecino mas cercano por grilla espacial. Devuelve JSON con cada
        pilote, resumen (min/p5/mediana/p95/max, histograma <3,3-4,4-5,5-6,>=6),
        lista de S/B < 3, factor minimo y capacidad de grupo por R-024 5.1.7.1.
        La tool reporta y senala; no decide ni propone cambios.

        Args:
            sections: "auto" = todas las secciones de frame circulares del modelo, o
                lista explicita de nombres de seccion. No se filtra por nombre de frame.
            diameter_mm: override del diametro en mm (secciones no circulares o malla
                mixta). 0 = diametro T3 de cada seccion circular.
            scope: "nearest_neighbor" (barrido rapido, vecino mas cercano global) o
                "by_footing" (grupo = pilotes dentro de la misma area de cabezal por
                punto-en-poligono; el concepto de grupo del R-024).
            neighbors: k vecinos a reportar por pilote.
            interpolation: "step_down" (defecto, escalon inferior de la tabla; la
                norma no autoriza interpolar) o "linear" (declarado en la salida).
            units: unidades activas durante la lectura (se restauran al terminar).
            cap_types: areas que cuentan como cabezal en by_footing: tipos de losa
                (footing; p.ej. "footing,mat") o nombres de seccion de area (p.ej. "Z50").
            q_ult: capacidad ULTIMA de un pilote (unidades de fuerza de `units`); el
                factor reduce esta, y Qadm = Qult_reducida / fs.
            fs: factor de seguridad para Qadm (R-024 5.2).
            q_adm: alternativa si solo se tiene la admisible ya dividida por su FS;
                aplicar el factor equivale solo si el FS no cambia (se declara).
            max_detail: maximo de pilotes con detalle en la salida (el resumen y la
                lista de S/B < 3 siempre van completos).
        """
        import json

        return json.dumps(self._con_unidades(units, lambda: self._informe_separacion(sections, diameter_mm, scope, neighbors, interpolation, cap_types, q_ult, fs, q_adm, max_detail)),
                          ensure_ascii=False, default=str)

    def _informe_separacion(self, sections, diameter_mm, scope, neighbors, interpolation, cap_types, q_ult, fs, q_adm, max_detail) -> dict:
        """Cuerpo de la tool, con las unidades ya fijadas; lo reutiliza export_pile_check_xlsx."""
        _idx, preset, force, length = self._unidades_activas()
        mm = self._LENGTH_MM[length]
        pil, avisos, secciones, n_frames = self._pilotes_leidos(sections, diameter_mm / mm, mm, True)
        try:
            cabezales = self._cabezales(cap_types) if scope == "by_footing" else None
            out = pilotes.evaluar_separacion(pil, scope, neighbors, interpolation, cabezales,
                                             q_ult, fs, q_adm)
        except pilotes.PilotesError as e:
            raise SafeError(str(e)) from e
        detalle = [pilotes.pilote_a_dict(p, mm) for p in out["pilotes"]]
        try:
            modelo = self._model().GetModelFilename()
        except Exception:
            modelo = "(sin nombre)"
        return {
            "herramienta": "get_pile_spacing", "solo_lectura": True, "modelo": modelo,
            "unidades": {"preset": preset, "fuerza": force, "longitud": length},
            "criterio": {
                "norma": "MOPC R-024 5.1.7.1, tabla 5.1 (S/B 6->1.0, 5->0.9, 4->0.8, 3->0.7)",
                "interpolacion": out["interpolacion"],
                "fuera_de_tabla": "S/B < 3 devuelve factor null; no se extrapola.",
                "diametros_mezclados": "S/B de cada pareja usa el mayor de los dos diametros.",
                "factor_reduce": "la capacidad ULTIMA; Qadm = Qult_reducida / FS.",
                "s_b_del_pilote": "menor S/B entre sus parejas a menos de 6*Dmax (pareja_s_b).",
                "sin_vecino": "pilote solo en su cabezal o en el modelo: sin interaccion, factor 1.0.",
                "capacidad_de_grupo": "solo por cabezal (scope by_footing); el barrido global no es un grupo.",
                "sections_auto": "todo frame con seccion circular; columnas circulares se excluyen con sections explicito.",
                "cabeza": "extremo de Z mayor; inclinados usan su proyeccion en planta."},
            "alcance": out["alcance"],
            "secciones_circulares": {k: {**v, "diametro_mm": round(v["diametro"] * mm, 3)}
                                     for k, v in secciones.items()},
            "n_frames_modelo": n_frames, "n_pilotes": len(detalle),
            "resumen": out["resumen"], "grupos": out["grupos"], "capacidad": out["capacidad"],
            "pilotes": detalle[:max(0, max_detail)],
            "pilotes_omitidos_en_detalle": max(0, len(detalle) - max(0, max_detail)),
            "avisos": avisos + out["avisos"],
            "pendiente": ["(b) capacidad de la pila equivalente del grupo: parametros de suelo",
                          "pilote mas cargado: ver get_pile_axial_reactions",
                          "estado [T]: firmas del typelib, sin corrida viva"],
        }

    def _exigir_analisis(self) -> list[str]:
        n, names, status, ret = self._model().Analyze.GetCaseStatus(0, [], [])
        if ret != 0:
            raise SafeError("Analyze.GetCaseStatus fallo (ret != 0).")
        if len(names) != n or len(status) != n:
            raise SafeError("Analyze.GetCaseStatus: longitud incoherente.")
        listos = [str(names[i]) for i in range(n) if status[i] == self._CASE_FINISHED]
        if not listos:
            raise SafeError("Ningun caso de carga tiene resultados: correr run_analysis y "
                            "sondear con get_analysis_status.")
        return listos

    def _seleccionar_salida(self, combos, cases, listos) -> tuple[list[str], list[str]]:
        model = self._model()
        setup = model.Results.Setup
        n, nombres = _result(model.RespCombo.GetNameList(), "RespCombo.GetNameList")[:2]
        if len(nombres) != n:
            raise SafeError(f"RespCombo.GetNameList: {len(nombres)} nombres para NumberNames={n}.")
        disponibles = [str(c) for c in nombres]
        if combos is None and cases is None:
            combos = disponibles
            cases = [] if disponibles else listos
        combos, cases = [str(c) for c in (combos or [])], [str(c) for c in (cases or [])]
        if not combos and not cases:
            raise SafeError("Sin combinaciones ni casos que leer.")
        faltan = [c for c in combos if c not in disponibles]
        if faltan:
            raise SafeError(f"Combinaciones inexistentes: {faltan}. Disponibles: {disponibles}.")
        faltan = [c for c in cases if c not in listos]
        if faltan:
            raise SafeError(f"Casos sin resultados o inexistentes: {faltan}. Listos: {listos}.")
        oapi.call_checked(setup, "DeselectAllCasesAndCombosForOutput", (), "limpieza de salida")
        for c in combos:
            oapi.call_checked(setup, "SetComboSelectedForOutput", (c,), f"salida combo {c}")
        for c in cases:
            oapi.call_checked(setup, "SetCaseSelectedForOutput", (c,), f"salida caso {c}")
        return combos, cases

    _REINTENTOS_RESULTADOS = (15, 2.0)   # intentos, segundos entre ellos

    def _leer_con_reintento(self, fn, what: str):
        """ret=1 en una lectura de resultados justo despues de RunAnalysis significa que SAFE aun no
        termino de volcarlos (visto en vivo 2026-11-04: la primera JointReact tras el analisis dio
        ret=1 y 2 min despues la misma llamada devolvia n=1). Se reintenta un rato antes de abortar."""
        import time
        intentos, pausa = self._REINTENTOS_RESULTADOS
        for k in range(intentos):
            result = fn()
            if oapi.ret_code(result) == 0:
                return oapi.outs(result)
            if oapi.ret_code(result) != 1 or k == intentos - 1:
                return _result(result, what)
            logger.warning("%s: ret=1 (resultados aun no disponibles); reintento %d/%d", what, k + 1, intentos)
            time.sleep(pausa)
        return _result(fn(), what)

    def _axial_pilote(self, p, source: str) -> list[dict]:
        res = self._model().Results
        if source == "joint":
            outs = self._leer_con_reintento(lambda: res.JointReact(p.punto_punta, self._ITEM_TYPE_OBJECT),
                                            f"Results.JointReact({p.punto_punta})")
            n, _obj, _elm, casos, pasos, stepnum, _f1, _f2, f3 = outs[:9]
            if any(len(a) != n for a in (casos, pasos, stepnum, f3)):
                raise SafeError(f"JointReact({p.punto_punta}): longitud incoherente.")
            return [{"pilote": p.id, "punto": p.punto_punta, "caso": str(casos[i]),
                     "paso": self._paso(pasos[i], stepnum[i]), "axial": float(f3[i])} for i in range(n)]
        outs = _result(res.FrameForce(p.id, self._ITEM_TYPE_OBJECT), f"Results.FrameForce({p.id})")
        n, _obj, objsta, _elm, _elmsta, casos, pasos, stepnum, axial_p = outs[:9]
        if any(len(a) != n for a in (objsta, casos, pasos, stepnum, axial_p)):
            raise SafeError(f"FrameForce({p.id}): longitud incoherente.")
        # Por (caso, paso): la estacion mas comprimida y, si existe, la mas traccionada.
        extremos: dict[tuple[str, str], list[dict]] = {}
        for i in range(n):
            clave = (str(casos[i]), self._paso(pasos[i], stepnum[i]))
            reg = {"pilote": p.id, "caso": clave[0], "paso": clave[1],
                   "axial": -float(axial_p[i]), "estacion": float(objsta[i])}   # CSI: P<0 comprime
            par = extremos.setdefault(clave, [reg, reg])
            if reg["axial"] > par[0]["axial"]:
                par[0] = reg
            if reg["axial"] < par[1]["axial"]:
                par[1] = reg
        salida = []
        for mayor, menor in extremos.values():
            salida.append(mayor)
            if menor["axial"] < 0 and menor is not mayor:
                salida.append(menor)
        return salida

    @staticmethod
    def _paso(step_type, step_num) -> str:
        """'Max' / 'Min' en combos; en casos multipaso conserva el numero de paso."""
        paso = str(step_type or "")
        try:
            num = float(step_num)
        except (TypeError, ValueError):
            return paso
        return f"{paso} {num:g}".strip() if num else paso

    @com_call
    def get_pile_axial_reactions(self, sections: str | list[str] = "auto",
                                 combos: list[str] | None = None, cases: list[str] | None = None,
                                 source: str = "joint", units: str = "kN, m, C",
                                 q_adm: float = 0.0, max_detail: int = 300) -> str:
        """Carga axial por pilote y combinacion, envolvente y pilote critico. [T, solo lectura]

        El control del R-024 es el pilote mas cargado, no el promedio: esta tool da
        ese dato para que get_pile_spacing cierre una verificacion. Requiere analisis
        corrido. Devuelve JSON con registros por pilote/caso/paso, la compresion
        maxima de cada pilote (caso y paso), traccion si existe, ratio contra q_adm
        si se da, y la lista de los que no cumplen. No propone nada.

        Args:
            sections: "auto" (secciones circulares) o lista explicita de secciones.
            combos: combinaciones a leer; None = todas las definidas (RespCombo).
            cases: casos de carga a leer ademas; None = ninguno salvo que no haya combos.
            source: "joint" = reaccion F3 en el nudo de punta (Results.JointReact,
                F3 positivo = compresion en el pilote; convencion a confirmar en
                vivo con un caso gravitatorio) o "frame" = fuerza axial del frame
                (Results.FrameForce, compresion = -P, la peor estacion).
            units: unidades activas durante la lectura (se restauran al terminar).
            q_adm: carga admisible por pilote en unidades de `units`; si aplica el
                factor de grupo, debe venir ya reducido (ver get_pile_spacing). Es
                una carga de SERVICIO: compararla solo con combinaciones de servicio
                (pasar `combos` explicitos); contra combos mayoradas de diseno el
                ratio no significa nada.
            max_detail: maximo de registros crudos en la salida.
        """
        import json
        if source not in ("joint", "frame"):
            raise SafeError("source debe ser \"joint\" o \"frame\".")

        return json.dumps(self._con_unidades(units, lambda: self._informe_reacciones(sections, combos, cases, source, q_adm, max_detail)),
                          ensure_ascii=False, default=str)

    def _informe_reacciones(self, sections, combos, cases, source, q_adm, max_detail) -> dict:
        """Cuerpo de la tool, con las unidades ya fijadas; lo reutiliza export_pile_check_xlsx."""
        _idx, preset, force, length = self._unidades_activas()
        mm = self._LENGTH_MM[length]
        listos = self._exigir_analisis()
        pil, avisos, secciones, n_frames = self._pilotes_leidos(sections, 0.0, mm, False)
        combos_sel, cases_sel = self._seleccionar_salida(combos, cases, listos)
        # Se leen TODOS los frames (duplicados incluidos: cada uno tiene su punta),
        # pero se avisa igual que en get_pile_spacing.
        _unicos, dup = pilotes.separar_duplicados(pil)
        avisos += [a.replace("excluido del analisis", "incluido en la lectura") for a in dup]
        if q_adm > 0 and (combos is None or combos):
            avisos.append("q_adm es carga de servicio: el ratio solo vale contra combinaciones "
                          "de servicio; con combos mayoradas (diseno) no significa nada.")
        registros, sin_resultado = [], []
        for p in pil:
            regs = self._axial_pilote(p, source)
            if not regs:
                sin_resultado.append(p.id)
            registros.extend(regs)
        if sin_resultado:
            avisos.append(f"{len(sin_resultado)} pilote(s) sin reaccion/fuerza para la salida "
                          f"seleccionada (punta sin restriccion ni resorte?): "
                          f"{sin_resultado[:20]}{'...' if len(sin_resultado) > 20 else ''}")
        try:
            env = pilotes.envolvente_axial(registros, q_adm)
        except pilotes.PilotesError as e:
            raise SafeError(str(e)) from e
        try:
            modelo = self._model().GetModelFilename()
        except Exception:
            modelo = "(sin nombre)"
        return {
            "herramienta": "get_pile_axial_reactions", "solo_lectura": True, "modelo": modelo,
            "unidades": {"preset": preset, "fuerza": force, "longitud": length},
            "fuente": source,
            "convencion": ("Results.JointReact F3 positivo = compresion en el pilote (reaccion "
                           "hacia arriba); confirmar en corrida viva." if source == "joint" else
                           "Results.FrameForce: compresion = -P (CSI, P negativo comprime)."),
            "salida_seleccionada": {"combos": combos_sel, "casos": cases_sel,
                                    "nota": "Results.Setup queda con esta seleccion activa."},
            "casos_con_resultados": listos,
            "secciones": sorted(secciones), "n_frames_modelo": n_frames, "n_pilotes": len(pil),
            "envolvente": env,
            "registros": registros[:max(0, max_detail)],
            "registros_omitidos": max(0, len(registros) - max(0, max_detail)),
            "avisos": avisos,
            "pendiente": ["estado [T]: firmas del typelib, sin corrida viva",
                          "q_adm con factor de grupo: ver get_pile_spacing"],
        }

    # ---------------- Libro de verificacion (claude, 2026-11-02) ----------

    def _combos_definidos(self) -> dict[str, dict]:
        """RespCombo.GetCaseList(Name) py-> (n, CNameType[], CName[], SF[], ret); 0=caso, 1=combo.

        Anade por miembro caso tipos_caso (eLoadCaseType: 4 = espectro) y tipos_patron
        (eLoadPatternType del DesignType: 5 = Quake, 6 = Wind) via LoadCases.GetTypeOAPI_1
        py-> (CaseType, SubType, DesignType, DesignTypeOption, Auto, ret); 0 para miembros
        combo. Asi un caso estatico equivalente de sismo cuenta como lateral, no como
        gravedad. Confirmado en vivo 2026-11-02 (Qx(1/2): CaseType 1, DesignType 5).
        """
        model = self._model()
        n, nombres = _result(model.RespCombo.GetNameList(), "RespCombo.GetNameList")[:2]
        if len(nombres) != n:
            raise SafeError(f"RespCombo.GetNameList: {len(nombres)} nombres para NumberNames={n}.")
        tipo_caso: dict[str, tuple[int, int]] = {}
        out = {}
        for nombre in nombres:
            m, tipos, casos, sf = _result(model.RespCombo.GetCaseList(nombre), f"RespCombo.GetCaseList({nombre})")[:4]
            if any(len(a) != m for a in (tipos, casos, sf)):
                raise SafeError(f"RespCombo.GetCaseList({nombre}): longitud incoherente.")
            tipos_caso, tipos_patron = [], []
            for t, c in zip(tipos, casos):
                if int(t) != 0:
                    tipos_caso.append(0)
                    tipos_patron.append(0)
                    continue
                if str(c) not in tipo_caso:
                    ct, _sub, dt = _result(model.LoadCases.GetTypeOAPI_1(str(c)), f"LoadCases.GetTypeOAPI_1({c})")[:3]
                    tipo_caso[str(c)] = (int(ct), int(dt))
                tipos_caso.append(tipo_caso[str(c)][0])
                tipos_patron.append(tipo_caso[str(c)][1])
            out[str(nombre)] = {"tipos": [int(t) for t in tipos], "casos": [str(c) for c in casos],
                                "sf": [float(f) for f in sf], "tipos_caso": tipos_caso,
                                "tipos_patron": tipos_patron}
        return out

    @com_call
    def export_pile_check_xlsx(self, path: str, q_adm: float = 0.0, q_ult: float = 0.0, fs: float = 0.0,
                               service_combos: str | list[str] = "auto", sections: str | list[str] = "auto",
                               diameter_mm: float = 0.0, cap_types: str = "footing",
                               interpolation: str = "step_down", margen_candidato: float = 0.9,
                               units: str = "kN, m, C", overwrite: bool = False,
                               seismic_combos: list[str] | None = None,
                               seismic_factor: float = 4.0 / 3.0) -> str:
        """Libro .xlsx de verificacion de pilotes: geometria (R-024 tabla 5.1), demanda y candidatos. [solo lectura del modelo]

        Cruza get_pile_spacing(scope=by_footing) con get_pile_axial_reactions(source=joint)
        sobre todas las combinaciones definidas, clasificadas por su definicion
        (RespCombo.GetCaseList). Hojas: Resumen (conformidad geometrica SI/NO, critico,
        conteos, (b) pendiente), Pilotes, Cabezales, Candidatos, Combos, Criterios.
        Requiere analisis corrido. No guarda el modelo. Los candidatos a eliminar son
        una lista con motivo para el ingeniero firmante; toda eliminacion exige reanalisis.

        Args:
            path: ruta del .xlsx a escribir (no sobrescribe salvo overwrite=True).
            q_adm: carga admisible de SERVICIO por pilote (FS incluido), en la fuerza de `units`.
            q_ult, fs: alternativa: capacidad ultima y FS (q_adm = q_ult / fs).
            service_combos: "auto" (factores de gravedad <= 1.2 y sin prefijo DCon) o lista explicita.
            sections, diameter_mm, cap_types, interpolation: como en get_pile_spacing.
            margen_candidato: fraccion de (a) que el cabezal no debe superar con un pilote menos.
            units: unidades activas durante la lectura (se restauran); el libro las declara.
            overwrite: permitir sobrescribir un archivo existente.
            seismic_combos: combinaciones sismicas (p. ej. ["Envelope"] o ["E"]) que se comparan con
                seismic_factor x q_adm x xi en vez de con q_adm x xi; se restan de las de servicio.
                Criterio doble: gravedad (service_combos, p. ej. ["Comb2"]) contra la admisible tal
                cual y sismo contra 4/3 de la admisible.
            seismic_factor: 4/3 por defecto (aumento de un tercio para cargas transitorias).
        """
        import json
        if not path.lower().endswith(".xlsx"):
            raise SafeError("path debe terminar en .xlsx.")
        if os.path.exists(path) and not overwrite:
            raise SafeError(f"Ya existe {path}; use overwrite=True.")
        if q_adm > 0 and (q_ult > 0 or fs > 0):
            raise SafeError("Indique q_adm o (q_ult y fs), no ambos.")
        if q_adm <= 0:
            if q_ult <= 0 or fs <= 0:
                raise SafeError("Indique q_adm > 0, o q_ult > 0 y fs > 0.")
            q_adm = q_ult / fs
        parent = os.path.dirname(path)
        if parent and not os.path.isdir(parent):
            raise SafeError(f"No existe la carpeta {parent}.")

        def leer():
            ver, sep, rea, a_leer = self._verificacion_dict(sections, diameter_mm, cap_types, interpolation,
                                                            q_adm, service_combos, margen_candidato,
                                                            seismic_combos, seismic_factor)
            hojas = self._escribir_libro(ver, sep, path)
            return {"herramienta": "export_pile_check_xlsx", "solo_lectura_del_modelo": True,
                    "archivo": path, "bytes": os.path.getsize(path), "hojas": hojas,
                    "unidades": sep["unidades"], "resumen": ver["resumen"],
                    "propuesta": ver["propuesta"],
                    "combos_leidas": a_leer, "avisos": sep["avisos"] + rea["avisos"],
                    "pendiente": ["(b) pila equivalente: parametros de suelo",
                                  "candidatos y propuesta: reanalisis obligatorio (ver trial_pile_changes)",
                                  "frames REVISAR MODELO: decision del ingeniero"]}
        return json.dumps(self._con_unidades(units, leer), ensure_ascii=False, default=str)

    def _verificacion_dict(self, sections, diameter_mm, cap_types, interpolation, q_adm,
                           service_combos, margen_candidato, seismic_combos=None, seismic_factor=1.0):
        """Geometria por cabezal + reacciones de todas las combos no envolventes + cruce. Unidades ya fijadas.

        Con seismic_combos (p. ej. ["Envelope"]) se leen tambien esas combos aunque sean
        envolventes y se comparan con seismic_factor x q_adm x xi.
        """
        sep = self._informe_separacion(sections, diameter_mm, "by_footing", 1, interpolation,
                                       cap_types, 0.0, 0.0, 0.0, 10 ** 9)
        combos = self._combos_definidos()
        clase = pilotes_xlsx.clasificar_combos(combos)
        a_leer = [c for c, k in clase.items() if k != pilotes_xlsx.CLASE_ENVOLVENTE]
        if not isinstance(service_combos, str):
            a_leer = sorted(set(a_leer) | {str(c) for c in service_combos})
        if seismic_combos:
            faltan = [str(c) for c in seismic_combos if str(c) not in combos]
            if faltan:
                raise SafeError(f"seismic_combos inexistentes: {faltan}. Definidas: {sorted(combos)}.")
            a_leer = sorted(set(a_leer) | {str(c) for c in seismic_combos})
        rea = self._informe_reacciones(sections, a_leer, [], "joint", 0.0, 10 ** 9)
        try:
            ver = pilotes_xlsx.armar_verificacion(sep, rea, combos, q_adm, service_combos, margen_candidato,
                                                  seismic_combos, seismic_factor)
        except pilotes.PilotesError as e:
            raise SafeError(str(e)) from e
        return ver, sep, rea, a_leer

    def _escribir_libro(self, ver, sep, path) -> list[str]:
        try:
            hojas = pilotes_xlsx.escribir_libro(ver, path, {
                "modelo": sep["modelo"], "unidades": sep["unidades"]["preset"],
                "origen": "SAFE-MCP export_pile_check_xlsx: get_pile_spacing(by_footing) + "
                          "get_pile_axial_reactions(joint) + RespCombo.GetCaseList"})
        except pilotes.PilotesError as e:
            raise SafeError(str(e)) from e
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise SafeError(f"El libro no quedo escrito en {path}.")
        return hojas

    @staticmethod
    def _q_adm_base(q_adm, q_ult, fs) -> float:
        if q_adm > 0 and (q_ult > 0 or fs > 0):
            raise SafeError("Indique q_adm o (q_ult y fs), no ambos.")
        if q_adm <= 0:
            if q_ult <= 0 or fs <= 0:
                raise SafeError("Indique q_adm > 0, o q_ult > 0 y fs > 0.")
            return q_ult / fs
        return q_adm

    @com_call
    def suggest_pile_changes(self, q_adm: float = 0.0, q_ult: float = 0.0, fs: float = 0.0,
                             service_combos: str | list[str] = "auto", sections: str | list[str] = "auto",
                             diameter_mm: float = 0.0, cap_types: str = "footing",
                             interpolation: str = "step_down", margen_candidato: float = 0.9,
                             units: str = "kN, m, C", seismic_combos: list[str] | None = None,
                             seismic_factor: float = 4.0 / 3.0) -> str:
        """Propuesta de cambios por cabezal (anadir / quitar / reespaciar) desde la verificacion. [solo lectura]

        Misma lectura que export_pile_check_xlsx (geometria por cabezal, reacciones de todas las
        combos, clasificacion por definicion) y la hoja Propuesta en JSON: por cabezal, pilotes
        hoy, demanda, factor, (a), ratio, n minimo con el factor actual y con malla de 5 diametros,
        accion y pilotes a quitar (los menos cargados). Es una sugerencia por capacidad (a) con
        margen: exige reanalisis (trial_pile_changes) y decision del ingeniero firmante.
        """
        import json
        q = self._q_adm_base(q_adm, q_ult, fs)

        def leer():
            ver, sep, rea, a_leer = self._verificacion_dict(sections, diameter_mm, cap_types, interpolation,
                                                            q, service_combos, margen_candidato,
                                                            seismic_combos, seismic_factor)
            return {"herramienta": "suggest_pile_changes", "solo_lectura": True, "modelo": sep["modelo"],
                    "unidades": sep["unidades"], "resumen": ver["resumen"], "propuesta": ver["propuesta"],
                    "avisos": sep["avisos"] + rea["avisos"]}
        return json.dumps(self._con_unidades(units, leer), ensure_ascii=False, default=str)

    # ---------------- Ensayo de cambios en COPIA (claude, 2026-11-02) -----

    @staticmethod
    def _mtime(path):
        try:
            return os.path.getmtime(path)
        except OSError:
            return None

    def _exigir_modelo(self, esperado: str) -> None:
        actual = self._model().GetModelFilename()
        if not actual or os.path.normcase(os.path.abspath(str(actual))) != os.path.normcase(os.path.abspath(esperado)):
            raise SafeError(f"El modelo activo es {actual!r}, no la copia {esperado!r}: no se escribe nada.")

    @staticmethod
    def _asignacion_opcional(result, what):
        """outs si ret=0; None si ret=1 (CSI: sin asignacion); error en cualquier otro caso."""
        code = oapi.ret_code(result)
        if code == 0:
            return oapi.outs(result)
        if code == 1:
            return None
        raise SafeError(f"{what}: ret={code}; resultado={result!r}")

    def _borrar_frames(self, copia: str, nombres: list[str]) -> list[str]:
        model = self._model()
        existentes = {f["id"] for f in self._frames_todos()}
        faltan = [n for n in nombres if n not in existentes]
        if faltan:
            raise SafeError(f"Frames inexistentes en la copia: {faltan}.")
        for n in nombres:
            self._exigir_modelo(copia)
            oapi.call_checked(model.FrameObj, "Delete", (str(n), 0), f"borrado del frame {n}")
        quedan = {f["id"] for f in self._frames_todos()}
        no_borrados = [n for n in nombres if n in quedan]
        if no_borrados:
            raise SafeError(f"FrameObj.Delete ret=0 pero siguen en el modelo: {no_borrados}.")
        return list(nombres)

    def _anadir_pilote(self, copia: str, x: float, y: float, ref: str, section: str = "") -> dict:
        """AddByCoord entre la Z de cabeza y de punta del pilote de referencia; copia sus apoyos de punta."""
        model = self._model()
        frames = {f["id"]: f for f in self._frames_todos()}
        if ref not in frames:
            raise SafeError(f"Pilote de referencia {ref!r} no existe en la copia.")
        r = frames[ref]
        z_cab, z_pun = max(r["z1"], r["z2"]), min(r["z1"], r["z2"])
        punta_ref = r["p1"] if r["z1"] < r["z2"] else r["p2"]
        prop = section or r["seccion"]
        self._exigir_modelo(copia)
        res = oapi.call_checked(model.FrameObj, "AddByCoord",
                                (float(x), float(y), z_cab, float(x), float(y), z_pun, "", prop),
                                f"AddByCoord pilote en ({x:g}, {y:g})")
        nombre = next((v for v in oapi.outs(res) if isinstance(v, str) and v), None)
        if not nombre:
            raise SafeError("AddByCoord no devolvio el nombre del frame nuevo.")
        nuevo = {f["id"]: f for f in self._frames_todos()}.get(nombre)
        if nuevo is None or not all(_equal_number(a, b) for a, b in
                                    ((nuevo["x1"], x), (nuevo["y1"], y), (nuevo["x2"], x), (nuevo["y2"], y))):
            raise SafeError(f"Frame {nombre}: coordenadas distintas al releer.")
        punta = nuevo["p1"] if nuevo["z1"] < nuevo["z2"] else nuevo["p2"]
        copiado = []
        # Los getters de asignacion devuelven ret=1 cuando NO hay asignacion (visto en vivo
        # 2026-11-02 con GetSpring): se toma como "sin asignacion", no como error.
        restr = self._asignacion_opcional(model.PointObj.GetRestraint(punta_ref), f"GetRestraint({punta_ref})")
        if restr and any(bool(v) for v in restr[0]):
            oapi.call_checked(model.PointObj, "SetRestraint", (punta, [bool(v) for v in restr[0]], 0), "restriccion de punta")
            copiado.append("restraint")
        k = self._asignacion_opcional(model.PointObj.GetSpring(punta_ref), f"GetSpring({punta_ref})")
        if k and any(float(v) != 0 for v in k[0]):
            oapi.call_checked(model.PointObj, "SetSpring", (punta, [float(v) for v in k[0]], 0, True, True), "resorte de punta")
            copiado.append("point_spring")
        sp = self._asignacion_opcional(model.PointObj.GetSpringAssignment(punta_ref), f"GetSpringAssignment({punta_ref})")
        if sp and sp[0] and sp[0] != "None":
            oapi.call_checked(model.PointObj, "SetSpringAssignment", (punta, str(sp[0]), 0), "resorte puntual asignado")
            copiado.append(f"point_spring_prop:{sp[0]}")
        ls = self._asignacion_opcional(model.FrameObj.GetSpringAssignment(ref), f"FrameObj.GetSpringAssignment({ref})")
        if ls and ls[0] and ls[0] != "None":
            oapi.call_checked(model.FrameObj, "SetSpringAssignment", (nombre, str(ls[0]), 0), "resorte de linea")
            copiado.append(f"line_spring_prop:{ls[0]}")
        return {"frame": nombre, "x": x, "y": y, "z_cabeza": z_cab, "z_punta": z_pun, "seccion": prop,
                "punta": punta, "referencia": ref, "apoyos_copiados": copiado}

    @com_call
    def trial_pile_changes(self, copy_path: str, q_adm: float = 0.0, q_ult: float = 0.0, fs: float = 0.0,
                           delete_frames: list[str] | None = None, add_piles: list[dict] | None = None,
                           xlsx_path: str = "", service_combos: str | list[str] = "auto",
                           sections: str | list[str] = "auto", diameter_mm: float = 0.0,
                           cap_types: str = "footing", interpolation: str = "step_down",
                           margen_candidato: float = 0.9, units: str = "kN, m, C",
                           overwrite: bool = False, seismic_combos: list[str] | None = None,
                           seismic_factor: float = 4.0 / 3.0) -> str:
        """Ensaya cambios de pilotes en una COPIA: copia, borra/anade, reanaliza y compara antes/despues. [escribe solo en la copia]

        El original NUNCA se guarda ni se modifica (se comprueba su fecha en disco al final).
        La copia si se guarda (el analisis la guarda) y queda abierta en SAFE. Pasos: baseline
        sobre el modelo activo (requiere analisis corrido) -> copy_model_file -> open_model(copia)
        -> FrameObj.Delete de delete_frames -> AddByCoord de add_piles copiando los apoyos de
        punta del pilote de referencia -> run_analysis -> verificacion de nuevo -> comparacion.

        Args:
            copy_path: ruta .FDB de la copia (no sobrescribe salvo overwrite=True).
            q_adm | q_ult+fs: carga admisible de servicio por pilote.
            delete_frames: nombres de frames a borrar en la copia.
            add_piles: [{"x":, "y":, "ref": "<pilote de referencia>", "section": opcional}] en
                unidades de `units`; Z de cabeza y punta, seccion y apoyos de punta se copian de ref.
            xlsx_path: si se indica, escribe el libro de verificacion DESPUES del cambio.
            resto: como export_pile_check_xlsx.
        """
        import json
        q = self._q_adm_base(q_adm, q_ult, fs)
        delete_frames = [str(n) for n in (delete_frames or [])]
        add_piles = list(add_piles or [])
        if not delete_frames and not add_piles:
            raise SafeError("Indique delete_frames y/o add_piles.")
        for a in add_piles:
            if not all(k in a for k in ("x", "y", "ref")):
                raise SafeError("Cada add_piles necesita x, y y ref (pilote de referencia).")
        if not copy_path.lower().endswith(".fdb"):
            raise SafeError("copy_path debe terminar en .fdb.")
        if xlsx_path and os.path.exists(xlsx_path) and not overwrite:
            raise SafeError(f"Ya existe {xlsx_path}; use overwrite=True.")
        model = self._model()
        original = model.GetModelFilename()
        if not original or not os.path.isfile(str(original)):
            raise SafeError("El modelo activo no tiene archivo en disco; no hay original que copiar.")
        if os.path.normcase(os.path.abspath(copy_path)) == os.path.normcase(os.path.abspath(str(original))):
            raise SafeError("copy_path no puede ser el original.")
        mtime0 = self._mtime(str(original))

        def ensayar():
            avisos_analisis: list[str] = []
            antes, _sep0, _rea0, _ = self._verificacion_dict(sections, diameter_mm, cap_types, interpolation,
                                                             q, service_combos, margen_candidato,
                                                             seismic_combos, seismic_factor)
            self.copy_model_file(copy_path, overwrite)
            self.open_model(copy_path)
            self._exigir_modelo(copy_path)
            borrados = self._borrar_frames(copy_path, delete_frames) if delete_frames else []
            anadidos = [self._anadir_pilote(copy_path, float(a["x"]), float(a["y"]), str(a["ref"]),
                                            str(a.get("section", ""))) for a in add_piles]
            self._exigir_modelo(copy_path)
            avisos_analisis.append(self._analizar_tolerante())
            self._exigir_analisis()
            despues, sep, rea, a_leer = self._verificacion_dict(sections, diameter_mm, cap_types, interpolation,
                                                                q, service_combos, margen_candidato,
                                                                seismic_combos, seismic_factor)
            hojas = self._escribir_libro(despues, sep, xlsx_path) if xlsx_path else []
            comparacion = pilotes_xlsx.comparar_verificaciones(antes, despues)
            if self._mtime(str(original)) != mtime0:
                raise SafeError(f"El ORIGINAL cambio en disco durante el ensayo: {original}. Revisar.")
            return {"herramienta": "trial_pile_changes", "original": str(original), "original_intacto": True,
                    "copia": copy_path, "copia_abierta_en_safe": True, "unidades": sep["unidades"],
                    "cambios": {"borrados": borrados, "anadidos": anadidos},
                    "comparacion": comparacion,
                    "resumen_despues": despues["resumen"], "propuesta_despues": despues["propuesta"],
                    "libro_despues": xlsx_path or None, "hojas": hojas,
                    "avisos": sep["avisos"] + rea["avisos"] + [a for a in avisos_analisis if a],
                    "pendiente": ["(b) pila equivalente: parametros de suelo",
                                  "capacidad a traccion no evaluada: ver traccion_max antes/despues",
                                  "decision del ingeniero firmante"]}
        return json.dumps(self._con_unidades(units, ensayar), ensure_ascii=False, default=str)


    # ---------------- Aplicar la Propuesta en COPIA (claude, 2026-11-03) --

    @com_call
    def apply_pile_proposal(self, copy_path: str, q_adm: float = 0.0, q_ult: float = 0.0, fs: float = 0.0,
                            xlsx_path: str = "", acciones: list[str] | None = None,
                            solo_cabezales: list[str] | None = None, s_min_d: float = 5.0,
                            s_fallback_d: float = 0.0, borde_d: float = 1.0,
                            service_combos: str | list[str] = "auto",
                            seismic_combos: list[str] | None = None, seismic_factor: float = 4.0 / 3.0,
                            sections: str | list[str] = "auto", diameter_mm: float = 0.0,
                            cap_types: str = "footing", interpolation: str = "step_down",
                            margen_candidato: float = 0.9, units: str = "kN, m, C",
                            overwrite: bool = False) -> str:
        """Aplica la hoja Propuesta en una COPIA del modelo y la reanaliza: quita los candidatos y anade pilotes colocados automaticamente. [escribe solo en la copia]

        Generaliza trial_pile_changes: la lista de cambios sale de suggest_pile_changes.
        - "quitar": borra los pilotes de baja demanda listados por cabezal.
        - "modelo": borra los frames duplicados (artefactos).
        - "anadir": coloca los pilotes que faltan dentro del area del cabezal, lo mas lejos
          posible de los existentes, a >= s_min_d diametros entre ejes y >= borde_d del borde
          (colocar_pilotes); copia seccion, Z y apoyos de punta de un pilote del cabezal.
          Si no caben a s_min_d, lo reporta ("no cabe") y no fuerza nada.
        - "redistribuir" y "reespaciar" NO se automatizan: se reportan para el ingeniero.
        Despues corre el analisis de la copia y compara antes/despues (comparar_verificaciones).
        El original no se guarda; se verifica su fecha en disco.

        Args:
            copy_path: .FDB de la copia (no sobrescribe salvo overwrite=True).
            acciones: subconjunto de ["quitar", "anadir", "modelo"]; None = las tres.
            solo_cabezales: limitar a estos cabezales (None = todos).
            s_min_d, borde_d: separacion minima entre ejes y al borde, en diametros.
            s_fallback_d: si > 0, lo que no cabe a s_min_d se intenta a esta separacion menor
                (p. ej. 4 = factor 0.8); se reporta con que separacion quedo cada pilote.
            resto: como export_pile_check_xlsx / trial_pile_changes.

        AVISO (corrida 2026-11-03): aplicar "quitar" por capacidad en bloque puede EMPEORAR el
        modelo (la carga se redistribuye peor que la suma); usar optimize_pile_removal, que
        quita de uno en uno y valida cada paso con reanalisis.
        """
        import json
        q = self._q_adm_base(q_adm, q_ult, fs)
        acciones = set(acciones or ["quitar", "anadir", "modelo"])
        if not acciones <= {"quitar", "anadir", "modelo"}:
            raise SafeError("acciones admite solo quitar, anadir y modelo.")
        if not copy_path.lower().endswith(".fdb"):
            raise SafeError("copy_path debe terminar en .fdb.")
        if xlsx_path and os.path.exists(xlsx_path) and not overwrite:
            raise SafeError(f"Ya existe {xlsx_path}; use overwrite=True.")
        model = self._model()
        original = model.GetModelFilename()
        if not original or not os.path.isfile(str(original)):
            raise SafeError("El modelo activo no tiene archivo en disco; no hay original que copiar.")
        if os.path.normcase(os.path.abspath(copy_path)) == os.path.normcase(os.path.abspath(str(original))):
            raise SafeError("copy_path no puede ser el original.")
        mtime0 = self._mtime(str(original))
        filtro = {str(c) for c in solo_cabezales} if solo_cabezales else None

        def aplicar():
            avisos_analisis: list[str] = []
            antes, sep0, _rea0, _ = self._verificacion_dict(sections, diameter_mm, cap_types, interpolation,
                                                            q, service_combos, margen_candidato,
                                                            seismic_combos, seismic_factor)
            _idx, _preset, _f, length = self._unidades_activas()
            mm = self._LENGTH_MM[length]
            poligonos = {str(c["id"]): c for c in self._cabezales(cap_types)}
            por_cab: dict[str, list[dict]] = {}
            for f in antes["filas"]:
                if f["cabezal"] is not None and not f["revisar"]:
                    por_cab.setdefault(str(f["cabezal"]), []).append(f)
            diametro = {k: v["diametro"] for k, v in sep0["secciones_circulares"].items()}
            plan, borrar, anadir, no_auto = [], [], [], []
            if "modelo" in acciones:
                dup = [c["id"] for c in antes["candidatos"] if c["motivo"].startswith("modelo")]
                borrar += dup
                if dup:
                    plan.append({"cabezal": None, "accion": "modelo", "borrar": dup})
            for fila in antes["propuesta"]["filas"]:
                cid = str(fila["cabezal"])
                if filtro and cid not in filtro:
                    continue
                if fila["accion"] == "quitar" and "quitar" in acciones:
                    ids = [x for x in fila["pilotes"].split(", ") if x]
                    borrar += ids
                    plan.append({"cabezal": cid, "accion": "quitar", "borrar": ids})
                elif fila["accion"] == "anadir" and "anadir" in acciones:
                    miembros = por_cab.get(cid, [])
                    pol = poligonos.get(cid)
                    if not miembros or pol is None:
                        no_auto.append({"cabezal": cid, "accion": "anadir", "motivo": "sin pilotes o sin area"})
                        continue
                    sec = next((p["seccion"] for p in sep0["pilotes"] if p["id"] == miembros[0]["id"]), None)
                    d = diametro.get(sec) or max(diametro.values())
                    existentes = [(p["x"], p["y"]) for p in miembros]
                    col = pilotes.colocar_pilotes(pol["xs"], pol["ys"], existentes, int(fila["delta"]), d, s_min_d, borde_d)
                    puestos = list(col["puestos"])
                    separacion_usada = s_min_d
                    if col["faltan"] and s_fallback_d > 0 and s_fallback_d < s_min_d:
                        col2 = pilotes.colocar_pilotes(pol["xs"], pol["ys"],
                                                       existentes + [(p["x"], p["y"]) for p in puestos],
                                                       col["faltan"], d, s_fallback_d, borde_d)
                        puestos += col2["puestos"]
                        col = {**col2, "mejor_s_b_disponible": col2["mejor_s_b_disponible"] or col["mejor_s_b_disponible"]}
                        separacion_usada = s_fallback_d if col2["puestos"] else s_min_d
                    for pt in puestos:
                        anadir.append({"cabezal": cid, "x": pt["x"], "y": pt["y"], "ref": miembros[0]["id"],
                                       "s_b_min": pt["s_b_min"]})
                    plan.append({"cabezal": cid, "accion": "anadir", "pedidos": int(fila["delta"]),
                                 "colocados": len(puestos), "faltan": col["faltan"],
                                 "separacion_minima_usada_d": separacion_usada,
                                 "mejor_s_b_disponible": col["mejor_s_b_disponible"]})
                    if col["faltan"]:
                        no_auto.append({"cabezal": cid, "accion": "anadir", "faltan": col["faltan"],
                                        "motivo": f"no caben a {s_fallback_d or s_min_d:g} diametros; mejor separacion "
                                                  f"disponible {col['mejor_s_b_disponible']} D: ampliar el cabezal o reespaciar"})
                elif fila["accion"] in ("redistribuir", "reespaciar"):
                    no_auto.append({"cabezal": cid, "accion": fila["accion"], "motivo": fila["detalle"]})
            if not borrar and not anadir:
                # Nada que aplicar (p. ej. tras optimize_pile_removal ya no queda cabezal por reforzar):
                # respuesta limpia sin crear copia, no un error.
                return {"herramienta": "apply_pile_proposal", "original": str(original), "original_intacto": True,
                        "sin_cambios": True, "copia": None, "acciones": sorted(acciones), "plan": plan,
                        "no_automatizado": no_auto,
                        "resumen_antes": {k: antes["resumen"][k] for k in ("n_pilotes", "n_no_cumplen", "cabezales_no_cumplen", "n_candidatos")},
                        "nota": "La propuesta no deja ningun cambio automatizable con las acciones pedidas; no se creo copia."}
            self.copy_model_file(copy_path, overwrite)
            self.open_model(copy_path)
            self._exigir_modelo(copy_path)
            borrados = self._borrar_frames(copy_path, sorted(set(borrar), key=lambda s: (len(s), s))) if borrar else []
            anadidos = []
            for a in anadir:
                r = self._anadir_pilote(copy_path, float(a["x"]), float(a["y"]), str(a["ref"]))
                r["cabezal"], r["s_b_min_previsto"] = a["cabezal"], a["s_b_min"]
                anadidos.append(r)
            self._exigir_modelo(copy_path)
            avisos_analisis.append(self._analizar_tolerante())
            self._exigir_analisis()
            despues, sep, rea, _ = self._verificacion_dict(sections, diameter_mm, cap_types, interpolation,
                                                           q, service_combos, margen_candidato,
                                                           seismic_combos, seismic_factor)
            hojas = self._escribir_libro(despues, sep, xlsx_path) if xlsx_path else []
            comparacion = pilotes_xlsx.comparar_verificaciones(antes, despues)
            if self._mtime(str(original)) != mtime0:
                raise SafeError(f"El ORIGINAL cambio en disco durante la aplicacion: {original}. Revisar.")
            return {"herramienta": "apply_pile_proposal", "original": str(original), "original_intacto": True,
                    "copia": copy_path, "copia_abierta_en_safe": True, "unidades": sep["unidades"],
                    "acciones": sorted(acciones), "s_min_d": s_min_d, "borde_d": borde_d,
                    "plan": plan, "no_automatizado": no_auto,
                    "cambios": {"n_borrados": len(borrados), "borrados": borrados,
                                "n_anadidos": len(anadidos), "anadidos": anadidos},
                    "comparacion": comparacion,
                    "resumen_antes": {k: antes["resumen"][k] for k in ("n_pilotes", "n_no_cumplen", "cabezales_no_cumplen", "n_candidatos")},
                    "resumen_despues": despues["resumen"], "propuesta_despues": despues["propuesta"],
                    "libro_despues": xlsx_path or None, "hojas": hojas,
                    "avisos": sep["avisos"] + rea["avisos"] + [a for a in avisos_analisis if a],
                    "pendiente": ["redistribuir y reespaciar: a mano (ver no_automatizado)",
                                  "posiciones de pilotes nuevos: propuestas, las fija el ingeniero",
                                  "(b) pila equivalente y capacidad a traccion: sin evaluar"]}
        return json.dumps(self._con_unidades(units, aplicar), ensure_ascii=False, default=str)

    def _analizar_tolerante(self) -> str:
        """run_analysis para bucles: si RunAnalysis devuelve ret != 0 pero GetCaseStatus dice que todos
        los casos quedaron listos (visto en vivo 2026-11-03 tras reabrir modelos en la misma
        instancia), se acepta con aviso en vez de abortar; si no, se propaga el error."""
        import time
        model = self._model()
        t0 = time.time()
        ret = model.Analyze.RunAnalysis()
        if ret == 0:
            return ""
        # GetCaseStatus puede estar RANCIO (la copia hereda los resultados de la base): exigir ademas
        # que el LOG del modelo diga ANALYSIS COMPLETE con fecha posterior al arranque.
        log_ok = self._esperar_log_analisis(t0)
        try:
            self._exigir_analisis()
        except SafeError as e:
            raise SafeError(f"RunAnalysis ret={ret} y casos sin terminar: {e}") from e
        if log_ok is False:
            raise SafeError(f"RunAnalysis ret={ret} y el LOG del modelo no reporta ANALYSIS COMPLETE posterior al arranque.")
        aviso = (f"RunAnalysis devolvio ret={ret} pero GetCaseStatus reporta todos los casos listos"
                 + (" y el LOG dice ANALYSIS COMPLETE" if log_ok else "") + "; se acepta.")
        logger.warning(aviso)
        return aviso

    _ESPERA_LOG_S = 900.0

    def _esperar_log_analisis(self, t0: float) -> bool | None:
        """True si <modelo>.LOG tiene fecha >= t0 y termina en ANALYSIS COMPLETE (esperando hasta
        _ESPERA_LOG_S); False si no llega; None si el modelo no tiene archivo/LOG que consultar."""
        import time
        activo = str(self._model().GetModelFilename() or "")
        if not activo:
            return None
        log = os.path.splitext(activo)[0] + ".LOG"
        try:
            os.stat(log)
        except OSError:
            return None          # sin LOG en disco (modelo sin archivo, mock...): nada que esperar
        limite = time.time() + self._ESPERA_LOG_S
        while True:
            try:
                if os.path.getmtime(log) >= t0 - 1.0:
                    with open(log, "r", encoding="latin-1", errors="replace") as fh:
                        cola = fh.read()[-600:]
                    if "A N A L Y S I S   C O M P L E T E" in cola:
                        return True
            except OSError:
                pass
            if time.time() >= limite:
                return False
            time.sleep(3.0)

    def _copia_desde_base(self, base: str, copia: str) -> None:
        """Reabre la base (cierra la copia sin guardar), copia el archivo base y abre la copia."""
        import shutil
        activo = str(self._model().GetModelFilename() or "")
        if os.path.normcase(os.path.abspath(activo)) != os.path.normcase(os.path.abspath(base)):
            self.open_model(base)
        shutil.copy2(base, copia)
        self.open_model(copia)

    # ---------------- Quitar iterativo validado por reanalisis -------------

    @com_call
    def optimize_pile_removal(self, copy_path: str, q_adm: float = 0.0, q_ult: float = 0.0, fs: float = 0.0,
                              xlsx_path: str = "", max_iter: int = 6, por_iteracion: int = 1,
                              solo_cabezales: list[str] | None = None, incluir_modelo: bool = True,
                              service_combos: str | list[str] = "auto",
                              seismic_combos: list[str] | None = None, seismic_factor: float = 4.0 / 3.0,
                              sections: str | list[str] = "auto", diameter_mm: float = 0.0,
                              cap_types: str = "footing", interpolation: str = "step_down",
                              margen_candidato: float = 0.9, units: str = "kN, m, C",
                              overwrite: bool = False, progress_path: str = "",
                              max_reparaciones: int = 2, radio_reparacion_d: float = 6.0) -> str:
        """Quita pilotes de baja demanda de uno en uno por cabezal, reanalizando y validando cada paso. [escribe solo en la copia]

        Cada iteracion parte del modelo base (copia nueva), borra el conjunto acumulado,
        reanaliza y verifica. Un cabezal se CONGELA (se revierte su ultima quita) en cuanto
        algun pilote suyo deja de cumplir, su suma (a) supera 1 o su propuesta ya no dice
        "quitar". Termina cuando no queda cabezal activo o al llegar a max_iter. Deja la copia
        con la ultima configuracion valida y el libro de esa configuracion.

        Fase de reparacion (efecto vecino, visto en vivo 2026-11-03: quitar en un cabezal carga
        al de al lado): tras las iteraciones, los pilotes que NO cumplen y si cumplian en la
        base se tratan restaurando las quitas a menos de radio_reparacion_d diametros de cada
        uno y reanalizando, hasta max_reparaciones veces o hasta que no quede fallo nuevo.

        Args:
            max_iter: iteraciones maximas (cada una = un analisis).
            por_iteracion: pilotes a quitar por cabezal en cada iteracion (1 = conservador).
            incluir_modelo: borrar tambien los frames duplicados (artefactos) desde la primera iteracion.
            max_reparaciones, radio_reparacion_d: fase de reparacion (0 = sin reparar).
            resto: como apply_pile_proposal.
        """
        import json
        q = self._q_adm_base(q_adm, q_ult, fs)
        if max_iter < 1 or por_iteracion < 1:
            raise SafeError("max_iter y por_iteracion deben ser >= 1.")
        if not copy_path.lower().endswith(".fdb"):
            raise SafeError("copy_path debe terminar en .fdb.")
        if xlsx_path and os.path.exists(xlsx_path) and not overwrite:
            raise SafeError(f"Ya existe {xlsx_path}; use overwrite=True.")
        model = self._model()
        original = model.GetModelFilename()
        if not original or not os.path.isfile(str(original)):
            raise SafeError("El modelo activo no tiene archivo en disco; no hay base que copiar.")
        if os.path.normcase(os.path.abspath(copy_path)) == os.path.normcase(os.path.abspath(str(original))):
            raise SafeError("copy_path no puede ser el original.")
        mtime0 = self._mtime(str(original))
        filtro = {str(c) for c in solo_cabezales} if solo_cabezales else None

        def verificar():
            return self._verificacion_dict(sections, diameter_mm, cap_types, interpolation, q,
                                           service_combos, margen_candidato, seismic_combos, seismic_factor)

        def optimizar():
            avisos_analisis: list[str] = []
            base, _s, _r, _ = verificar()
            estado_cab = {c["cabezal"]: c for c in base["cabezales"]}
            quitados: dict[str, list[str]] = {}
            congelados: set = set()
            borrar_modelo = [c["id"] for c in base["candidatos"] if c["motivo"].startswith("modelo")] if incluir_modelo else []
            historial = []
            ultima_valida = base
            ultima_borrados: list[str] = list(borrar_modelo)
            actual = base
            for it in range(1, max_iter + 1):
                # 1) proponer una quita por cabezal activo a partir de la verificacion actual
                nuevos: dict[str, list[str]] = {}
                for fila in actual["propuesta"]["filas"]:
                    cid = str(fila["cabezal"])
                    if cid in congelados or (filtro and cid not in filtro) or fila["accion"] != "quitar":
                        continue
                    cands = [x for x in fila["pilotes"].split(", ") if x and x not in quitados.get(cid, [])][:por_iteracion]
                    if cands:
                        nuevos[cid] = cands
                if not nuevos:
                    break
                conjunto = list(borrar_modelo)
                for cid, lst in quitados.items():
                    conjunto += lst
                for cid, lst in nuevos.items():
                    conjunto += lst
                # 2) copia nueva desde la BASE (no desde la copia activa), borrar, reanalizar, verificar
                self._copia_desde_base(str(original), copy_path)
                self._exigir_modelo(copy_path)
                self._borrar_frames(copy_path, sorted(set(conjunto), key=lambda s: (len(s), s)))
                avisos_analisis.append(self._analizar_tolerante())
                self._exigir_analisis()
                ver, _s, _r, _ = verificar()
                por_cab = {c["cabezal"]: c for c in ver["cabezales"]}
                fallan = {str(f["cabezal"]) for f in ver["filas"] if f["estado"].startswith("NO CUMPLE")}
                fallan_a = {str(c["cabezal"]) for c in ver["cabezales"] if c["estado"].startswith("NO CUMPLE")}
                aceptados, revertidos = [], []
                for cid, lst in nuevos.items():
                    antes_c = estado_cab.get(cid)
                    ya_fallaba = bool(antes_c and (antes_c["estado"].startswith("NO CUMPLE") or antes_c.get("no_cumplen")))
                    if (cid in fallan or cid in fallan_a) and not ya_fallaba:
                        revertidos.append(cid)
                        congelados.add(cid)
                    elif cid in fallan or cid in fallan_a:
                        # ya fallaba antes: no se toca
                        revertidos.append(cid)
                        congelados.add(cid)
                    else:
                        quitados.setdefault(cid, []).extend(lst)
                        aceptados.append(cid)
                historial.append({"iteracion": it, "propuestos": {k: v for k, v in nuevos.items()},
                                  "aceptados": aceptados, "revertidos": revertidos,
                                  "n_borrados_total_valido": len(borrar_modelo) + sum(len(v) for v in quitados.values()),
                                  "no_cumplen_tras": ver["resumen"]["n_no_cumplen"],
                                  "n_pilotes_tras": ver["resumen"]["n_pilotes"]})
                if progress_path:
                    with open(progress_path, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(historial[-1], ensure_ascii=False) + "\n")
                if not revertidos:
                    ultima_valida, ultima_borrados = ver, list(set(conjunto))
                    actual = ver
                else:
                    # el modelo de esta iteracion incluye quitas revertidas: la configuracion
                    # valida es la acumulada sin ellas; se reconstruye en la siguiente vuelta o al final
                    actual = ver
                    for cid in revertidos:
                        for f in actual["propuesta"]["filas"]:
                            if str(f["cabezal"]) == cid:
                                f["accion"] = "congelado"
            # 3) dejar la copia en la ultima configuracion VALIDA (sin las quitas revertidas)
            final = list(borrar_modelo)
            for cid, lst in quitados.items():
                final += lst
            self._copia_desde_base(str(original), copy_path)
            self._exigir_modelo(copy_path)
            if final:
                self._borrar_frames(copy_path, sorted(set(final), key=lambda s: (len(s), s)))
            avisos_analisis.append(self._analizar_tolerante())
            self._exigir_analisis()
            despues, sep, rea, _ = verificar()
            # 4) reparacion del efecto vecino: fallos nuevos -> restaurar quitas cercanas
            fallaban_base = {f["id"] for f in base["filas"] if f["estado"].startswith("NO CUMPLE")}
            xy = {f["id"]: (f["x"], f["y"]) for f in base["filas"] if f["x"] is not None}
            d_ref = max(sep["secciones_circulares"][k]["diametro"] for k in sep["secciones_circulares"]) if sep["secciones_circulares"] else 0.0
            reparaciones = []
            for rep in range(1, max_reparaciones + 1):
                nuevos_fallos = [f["id"] for f in despues["filas"]
                                 if f["estado"].startswith("NO CUMPLE") and f["id"] not in fallaban_base]
                if not nuevos_fallos or d_ref <= 0:
                    break
                restaurar = set()
                for pid in nuevos_fallos:
                    px_, py_ = xy.get(pid, (None, None))
                    if px_ is None:
                        continue
                    for q in final:
                        if q in borrar_modelo or q not in xy:
                            continue
                        if math.hypot(xy[q][0] - px_, xy[q][1] - py_) <= radio_reparacion_d * d_ref:
                            restaurar.add(q)
                if not restaurar:
                    reparaciones.append({"reparacion": rep, "fallos_nuevos": nuevos_fallos, "restaurados": [],
                                         "nota": "sin quitas dentro del radio; fallos no atribuibles a las quitas"})
                    break
                final = [q for q in final if q not in restaurar]
                for cid in list(quitados):
                    quitados[cid] = [q for q in quitados[cid] if q not in restaurar]
                    if not quitados[cid]:
                        del quitados[cid]
                self._copia_desde_base(str(original), copy_path)
                self._exigir_modelo(copy_path)
                if final:
                    self._borrar_frames(copy_path, sorted(set(final), key=lambda s: (len(s), s)))
                avisos_analisis.append(self._analizar_tolerante())
                self._exigir_analisis()
                despues, sep, rea, _ = verificar()
                reparaciones.append({"reparacion": rep, "fallos_nuevos": nuevos_fallos,
                                     "restaurados": sorted(restaurar, key=lambda s: (len(s), s)),
                                     "no_cumplen_tras": despues["resumen"]["n_no_cumplen"],
                                     "n_pilotes_tras": despues["resumen"]["n_pilotes"]})
                if progress_path:
                    with open(progress_path, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(reparaciones[-1], ensure_ascii=False) + "\n")
            fallos_restantes = [f["id"] for f in despues["filas"]
                                if f["estado"].startswith("NO CUMPLE") and f["id"] not in fallaban_base]
            hojas = self._escribir_libro(despues, sep, xlsx_path) if xlsx_path else []
            comparacion = pilotes_xlsx.comparar_verificaciones(base, despues)
            if self._mtime(str(original)) != mtime0:
                raise SafeError(f"El ORIGINAL cambio en disco durante la optimizacion: {original}. Revisar.")
            return {"herramienta": "optimize_pile_removal", "original": str(original), "original_intacto": True,
                    "copia": copy_path, "copia_abierta_en_safe": True, "unidades": sep["unidades"],
                    "iteraciones": len(historial), "historial": historial,
                    "reparaciones": reparaciones, "fallos_nuevos_restantes": fallos_restantes,
                    "quitados_por_cabezal": quitados, "frames_modelo_borrados": borrar_modelo,
                    "n_borrados": len(set(final)), "cabezales_congelados": sorted(congelados),
                    "comparacion": comparacion,
                    "resumen_antes": {k: base["resumen"][k] for k in ("n_pilotes", "n_no_cumplen", "cabezales_no_cumplen")},
                    "resumen_despues": despues["resumen"], "libro_despues": xlsx_path or None, "hojas": hojas,
                    "avisos": sep["avisos"] + rea["avisos"] + [a for a in avisos_analisis if a],
                    "pendiente": ["anadir / redistribuir / reespaciar: apply_pile_proposal o a mano",
                                  "(b) pila equivalente y capacidad a traccion: sin evaluar",
                                  "cada iteracion es un analisis completo de la copia"]}
        return json.dumps(self._con_unidades(units, optimizar), ensure_ascii=False, default=str)

    # ---------------- Densificar: anadir junto a los que fallan, ampliando el cabezal (claude, 2026-11-04) --

    def _vertices_cabezal(self, cid: str, xs, ys) -> list[str]:
        """Nombres de los puntos del area en el orden del poligono (xs, ys) leido con GetAllAreas."""
        nombres = self._area_points(cid)
        coords = {n: self._coords(n) for n in nombres}
        out: list[str] = []
        for x, y in zip(xs, ys):
            n = next((n for n, (cx, cy, _z) in coords.items()
                      if n not in out and _equal_number(cx, x) and _equal_number(cy, y)), None)
            if n is None:
                raise SafeError(f"Cabezal {cid}: el vertice ({x:g}, {y:g}) no corresponde a ningun punto del area.")
            out.append(n)
        return out

    def _lados_fijos(self, cid: str, nombres: list[str]) -> set[int]:
        """Indices de lado del cabezal con algun vertice conectado a OTRO objeto (no se mueven)."""
        model = self._model()
        compartidos = set()
        for k, n in enumerate(nombres):
            res = self._asignacion_opcional(model.PointObj.GetConnectivity(n), f"GetConnectivity({n})")
            if res is None:
                continue
            num, tipos, objs = int(res[0]), list(res[1]), list(res[2])
            pares = [(int(t), str(o)) for t, o in zip(tipos[:num], objs[:num])]
            if any(p != (5, str(cid)) for p in pares):
                compartidos.add(k)
        n = len(nombres)
        return {i for i in range(n) if i in compartidos or (i + 1) % n in compartidos}

    def _ampliar_cabezal(self, copia: str, cid: str, puntos: list[str], dx: float, dy: float) -> dict:
        """Mueve los dos vertices de un lado del cabezal (SetSelected + EditGeneral.Move) y relee."""
        self._exigir_modelo(copia)
        self.move_objects("point", list(puntos), float(dx), float(dy), 0.0)
        return {"cabezal": cid, "puntos": list(puntos), "dx": dx, "dy": dy}

    def _frame_en(self, x: float, y: float, seccion: str = "") -> str:
        """Nombre del frame cuya cabeza (extremo de Z mayor) esta en (x, y). Los nombres que SAFE asigna
        a los frames nuevos dependen del orden de creacion (visto en vivo 2026-11-04: al rehacer la copia
        sin los cambios rechazados, la referencia '289' ya no existia), asi que el replay resuelve la
        referencia por coordenadas."""
        cands = []
        for f in self._frames_todos():
            hx, hy = (f["x1"], f["y1"]) if f["z1"] >= f["z2"] else (f["x2"], f["y2"])
            if math.isclose(float(hx), x, abs_tol=1e-4) and math.isclose(float(hy), y, abs_tol=1e-4):
                if not seccion or f["seccion"] == seccion:
                    cands.append(f["id"])
        if len(cands) != 1:
            raise SafeError(f"Pilote de referencia en ({x:g}, {y:g}): {len(cands)} frame(s) con cabeza ahi: {cands[:5]}.")
        return cands[0]

    def _aplicar_cambios(self, copia: str, cambios: list[dict]) -> list[dict]:
        """Reaplica en orden una lista de cambios (ampliar / anadir) sobre la copia recien creada."""
        hechos = []
        for c in cambios:
            if c["tipo"] == "ampliar":
                hechos.append({**c, **self._ampliar_cabezal(copia, c["cabezal"], c["puntos"], c["dx"], c["dy"])})
            elif c["tipo"] == "anadir":
                ref = self._frame_en(float(c["ref_xy"][0]), float(c["ref_xy"][1])) if c.get("ref_xy") else str(c["ref"])
                r = self._anadir_pilote(copia, float(c["x"]), float(c["y"]), ref)
                hechos.append({**c, "ref_usada": ref, "frame": r["frame"], "apoyos_copiados": r["apoyos_copiados"]})
            else:
                raise SafeError(f"cambio desconocido: {c!r}")
        return hechos

    @com_call
    def optimize_pile_addition(self, copy_path: str, q_adm: float = 0.0, q_ult: float = 0.0, fs: float = 0.0,
                               xlsx_path: str = "", max_iter: int = 8, pasos: list[str] | None = None,
                               borde_d: float = 1.0, holgura_d: float = 2.0, max_por_cabezal: int = 0,
                               max_por_pilote: int = 2, solo_cabezales: list[str] | None = None,
                               service_combos: str | list[str] = "auto",
                               seismic_combos: list[str] | None = None, seismic_factor: float = 4.0 / 3.0,
                               sections: str | list[str] = "auto", diameter_mm: float = 0.0,
                               cap_types: str = "footing", interpolation: str = "step_down",
                               margen_candidato: float = 0.9, units: str = "kN, m, C",
                               overwrite: bool = False, progress_path: str = "") -> str:
        """Anade pilotes junto a cada pilote que NO cumple, ampliando el cabezal si no hay hueco, con reanalisis por iteracion hasta que todos cumplan. [escribe solo en la copia]

        Criterio pilote por pilote: gravedad contra q_adm x factor de grupo y sismo contra
        seismic_factor x q_adm x factor. Cada iteracion: para cada pilote que falla (peor ratio
        primero) se busca UNA posicion nueva a s diametros de el siguiendo `pasos`:
          "5i" dentro del cabezal a 5 D, "4i" a 4 D, "5a" ampliando el cabezal (mover un lado
          hacia fuera lo justo) a 5 D, "4a" idem a 4 D, "3i" dentro a 3 D (factor 0.7).
        La posicion debe quedar a >= s D de todos los pilotes y a >= borde_d D del borde; la
        ampliacion no puede invadir otros cabezales (holgura_d D) ni mover vertices compartidos
        con otros objetos. Luego copia nueva desde la base, reaplica todo lo aceptado + lo nuevo,
        reanaliza y verifica: un cabezal cuyo numero de fallos o ratio maximo NO mejora se
        CONGELA y sus cambios de esa iteracion se descartan. Termina cuando no queda pilote
        que falle (fuera de los congelados), cuando no hay posicion para ninguno o en max_iter.
        Deja la copia con la ultima configuracion aceptada y el libro de verificacion.
        `cumple_todo` exige ademas que ningun pilote nuevo quede SIN FACTOR (S/B < 3); los que ya
        estaban sin factor en la base se listan en sin_factor_base (reespaciar a mano).

        Args:
            max_iter: iteraciones maximas (cada una = un analisis completo de la copia).
            pasos: orden de busqueda; None = ["5i", "4i", "5a", "4a", "3i"]. Minimo 3 D.
            borde_d, holgura_d: margen al borde y holgura entre cabezales, en diametros.
            max_por_cabezal: tope de pilotes nuevos por cabezal e iteracion (0 = sin tope).
            max_por_pilote: pilotes nuevos junto a cada pilote que falla, por iteracion: se ponen
                ceil(ratio - 1) acotados a este valor (ratio 1.3 -> 1, ratio 2.4 -> 2).
            resto: como optimize_pile_removal.
        """
        import json
        from collections import Counter
        q = self._q_adm_base(q_adm, q_ult, fs)
        if max_iter < 1 or max_por_cabezal < 0 or max_por_pilote < 1 or borde_d < 0 or holgura_d < 0:
            raise SafeError("max_iter >= 1; max_por_pilote >= 1; max_por_cabezal, borde_d y holgura_d >= 0.")
        try:
            pasos_l = pilotes.parsear_pasos(pasos)
        except pilotes.PilotesError as e:
            raise SafeError(str(e)) from e
        if not copy_path.lower().endswith(".fdb"):
            raise SafeError("copy_path debe terminar en .fdb.")
        if xlsx_path and os.path.exists(xlsx_path) and not overwrite:
            raise SafeError(f"Ya existe {xlsx_path}; use overwrite=True.")
        model = self._model()
        original = model.GetModelFilename()
        if not original or not os.path.isfile(str(original)):
            raise SafeError("El modelo activo no tiene archivo en disco; no hay base que copiar.")
        if os.path.normcase(os.path.abspath(copy_path)) == os.path.normcase(os.path.abspath(str(original))):
            raise SafeError("copy_path no puede ser el original.")
        mtime0 = self._mtime(str(original))
        filtro = {str(c) for c in solo_cabezales} if solo_cabezales else None

        def verificar():
            return self._verificacion_dict(sections, diameter_mm, cap_types, interpolation, q,
                                           service_combos, margen_candidato, seismic_combos, seismic_factor)

        def falla(f):
            return f["estado"].startswith("NO CUMPLE") and f["cabezal"] is not None and not f["revisar"]

        def estado_por_cabezal(ver):
            out: dict[str, list] = {}
            for f in ver["filas"]:
                if falla(f):
                    e = out.setdefault(str(f["cabezal"]), [0, 0.0])
                    e[0] += 1
                    e[1] = max(e[1], f["ratio"] or 0.0)
            return {k: tuple(v) for k, v in out.items()}

        def anotar(path, fila):
            if path:
                with open(path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(fila, ensure_ascii=False) + "\n")

        def densificar():
            avisos_analisis: list[str] = []
            base, sep, _r, _ = verificar()
            diam = {k: v["diametro"] for k, v in sep["secciones_circulares"].items()}
            if not diam:
                raise SafeError("Sin secciones circulares: no hay diametro para separar los pilotes nuevos.")
            fallaban_base = {f["id"] for f in base["filas"] if falla(f)}
            cambios: list[dict] = []
            congelados: dict[str, str] = {}
            sin_posicion: list[dict] = []
            historial: list[dict] = []
            actual = base
            for it in range(1, max_iter + 1):
                fallan = [f for f in actual["filas"] if falla(f) and str(f["cabezal"]) not in congelados
                          and (not filtro or str(f["cabezal"]) in filtro) and f["x"] is not None]
                if not fallan:
                    break
                fallan.sort(key=lambda f: -(f["ratio"] or 0.0))
                poligonos = {str(c["id"]): {"id": str(c["id"]), "xs": list(c["xs"]), "ys": list(c["ys"])}
                             for c in self._cabezales(cap_types)}
                seccion_de = {p["id"]: p["seccion"] for p in sep["pilotes"]}
                pil_cab: dict[str, list[tuple]] = {}
                for f in actual["filas"]:
                    if f["cabezal"] is not None and f["x"] is not None:
                        pil_cab.setdefault(str(f["cabezal"]), []).append((f["id"], f["x"], f["y"]))
                antes_cab = estado_por_cabezal(actual)
                nuevos: list[dict] = []
                cuenta: Counter = Counter()
                lados_cache: dict[str, tuple] = {}
                pendientes = []
                for f in fallan:
                    k = max(1, min(max_por_pilote, math.ceil((f["ratio"] or 1.0) - 1.0 - 1e-9)))
                    pendientes += [f] * k
                for f in pendientes:
                    cid = str(f["cabezal"])
                    if max_por_cabezal and cuenta[cid] >= max_por_cabezal:
                        continue
                    pol = poligonos.get(cid)
                    if pol is None:
                        sin_posicion.append({"iteracion": it, "pilote": f["id"], "cabezal": cid, "motivo": "cabezal sin area"})
                        continue
                    d = diam.get(seccion_de.get(f["id"])) or max(diam.values())
                    otros = [(x, y) for pid, x, y in pil_cab.get(cid, []) if pid != f["id"]]
                    otros += [(c["x"], c["y"]) for c in nuevos if c["tipo"] == "anadir" and c["cabezal"] == cid]
                    vecinos = [p for k, p in poligonos.items() if k != cid]
                    pos = None
                    try:
                        for s, modo in pasos_l:
                            if modo == "dentro":
                                pos = pilotes.posicion_junto_a(f["x"], f["y"], pol["xs"], pol["ys"], otros, d, s, borde_d)
                            else:
                                if cid not in lados_cache:
                                    nombres = self._vertices_cabezal(cid, pol["xs"], pol["ys"])
                                    lados_cache[cid] = (nombres, self._lados_fijos(cid, nombres))
                                nombres, fijos = lados_cache[cid]
                                pos = pilotes.posicion_ampliando(f["x"], f["y"], pol["xs"], pol["ys"], otros, d, s,
                                                                 borde_d, vecinos, holgura_d * d, fijos)
                            if pos:
                                pos["s_d"] = s
                                break
                    except pilotes.PilotesError as e:
                        raise SafeError(str(e)) from e
                    if pos is None:
                        sin_posicion.append({"iteracion": it, "pilote": f["id"], "cabezal": cid, "ratio": f["ratio"],
                                             "motivo": "sin posicion en ningun paso (ni ampliando el cabezal)"})
                        continue
                    if pos["modo"] == "ampliando":
                        nombres, _fijos = lados_cache[cid]
                        i, j = pos["lado"], (pos["lado"] + 1) % len(nombres)
                        nuevos.append({"tipo": "ampliar", "iteracion": it, "cabezal": cid, "lado": i,
                                       "puntos": [nombres[i], nombres[j]], "dx": pos["dx"], "dy": pos["dy"], "delta": pos["delta"]})
                        pol["xs"], pol["ys"] = pos["xs"], pos["ys"]
                    nuevos.append({"tipo": "anadir", "iteracion": it, "cabezal": cid, "x": pos["x"], "y": pos["y"],
                                   "ref": f["id"], "ref_xy": [f["x"], f["y"]], "junto_a": f["id"], "s_d": pos["s_d"],
                                   "modo": pos["modo"], "s_b_min_previsto": pos["s_b_min"]})
                    cuenta[cid] += 1
                if not nuevos:
                    break
                self._copia_desde_base(str(original), copy_path)
                self._exigir_modelo(copy_path)
                self._aplicar_cambios(copy_path, cambios + nuevos)
                avisos_analisis.append(self._analizar_tolerante())
                self._exigir_analisis()
                ver, sep, _r, _ = verificar()
                despues_cab = estado_por_cabezal(ver)
                aceptados, rechazados = [], []
                for cid in sorted({c["cabezal"] for c in nuevos}, key=lambda s: (len(s), s)):
                    n0, r0 = antes_cab.get(cid, (0, 0.0))
                    n1, r1 = despues_cab.get(cid, (0, 0.0))
                    if n1 < n0 or (n1 == n0 and r1 < r0 - 1e-6):
                        aceptados.append(cid)
                    else:
                        rechazados.append(cid)
                        congelados[cid] = f"sin mejora al anadir: fallan {n0} -> {n1}, ratio max {r0:.3f} -> {r1:.3f}"
                cambios += [c for c in nuevos if c["cabezal"] in aceptados]
                detalle = {cid: {"fallaban": antes_cab.get(cid, (0, 0.0))[0], "ratio_max": round(antes_cab.get(cid, (0, 0.0))[1], 3),
                                 "fallan_tras": despues_cab.get(cid, (0, 0.0))[0], "ratio_max_tras": round(despues_cab.get(cid, (0, 0.0))[1], 3),
                                 "anadidos": sum(1 for c in nuevos if c["cabezal"] == cid and c["tipo"] == "anadir"),
                                 "ampliaciones": sum(1 for c in nuevos if c["cabezal"] == cid and c["tipo"] == "ampliar"),
                                 "resultado": "aceptado" if cid in aceptados else "rechazado"}
                           for cid in sorted({c["cabezal"] for c in nuevos}, key=lambda s: (len(s), s))}
                historial.append({"iteracion": it, "pilotes_que_fallaban": len(fallan), "cabezales": detalle,
                                  "propuestos": {cid: sum(1 for c in nuevos if c["cabezal"] == cid and c["tipo"] == "anadir") for cid in sorted({c["cabezal"] for c in nuevos})},
                                  "ampliaciones": [{k: c[k] for k in ("cabezal", "lado", "delta")} for c in nuevos if c["tipo"] == "ampliar"],
                                  "aceptados": aceptados, "rechazados": rechazados,
                                  "n_anadidos_total_valido": sum(1 for c in cambios if c["tipo"] == "anadir"),
                                  "no_cumplen_tras": ver["resumen"]["n_no_cumplen"], "n_pilotes_tras": ver["resumen"]["n_pilotes"]})
                anotar(progress_path, historial[-1])
                actual = ver
            # copia final con SOLO lo aceptado
            self._copia_desde_base(str(original), copy_path)
            self._exigir_modelo(copy_path)
            hechos = self._aplicar_cambios(copy_path, cambios)
            avisos_analisis.append(self._analizar_tolerante())
            self._exigir_analisis()
            despues, sep, rea, _ = verificar()
            hojas = self._escribir_libro(despues, sep, xlsx_path) if xlsx_path else []
            comparacion = pilotes_xlsx.comparar_verificaciones(base, despues)
            if self._mtime(str(original)) != mtime0:
                raise SafeError(f"El ORIGINAL cambio en disco durante la densificacion: {original}. Revisar.")
            fallan_final = [{"id": f["id"], "cabezal": f["cabezal"], "ratio": f["ratio"], "estado": f["estado"]}
                            for f in despues["filas"] if falla(f)]
            sin_factor_base = {f["id"] for f in base["filas"] if f["estado"].startswith("SIN FACTOR")}
            sin_factor_nuevos = [f["id"] for f in despues["filas"]
                                 if f["estado"].startswith("SIN FACTOR") and f["id"] not in sin_factor_base]
            anadidos = [h for h in hechos if h["tipo"] == "anadir"]
            ampliaciones = [h for h in hechos if h["tipo"] == "ampliar"]
            por_cab: dict[str, int] = Counter(h["cabezal"] for h in anadidos)
            return {"herramienta": "optimize_pile_addition", "original": str(original), "original_intacto": True,
                    "copia": copy_path, "copia_abierta_en_safe": True, "unidades": sep["unidades"],
                    "criterio": {"pasos": [f"{s:g}{'i' if m == 'dentro' else 'a'}" for s, m in pasos_l],
                                 "borde_d": borde_d, "holgura_d": holgura_d, "seismic_factor": seismic_factor},
                    "iteraciones": len(historial), "historial": historial,
                    "n_anadidos": len(anadidos), "anadidos_por_cabezal": dict(por_cab), "anadidos": anadidos,
                    "n_ampliaciones": len(ampliaciones), "ampliaciones": ampliaciones,
                    "cabezales_congelados": congelados, "sin_posicion": sin_posicion,
                    "cumple_todo": not fallan_final and not sin_factor_nuevos,
                    "pilotes_que_siguen_fallando": fallan_final,
                    "sin_factor_nuevos": sin_factor_nuevos,
                    "sin_factor_base": sorted(sin_factor_base, key=lambda s: (len(s), s)),
                    "fallos_nuevos": [f["id"] for f in fallan_final if f["id"] not in fallaban_base],
                    "comparacion": comparacion,
                    "resumen_antes": {k: base["resumen"][k] for k in ("n_pilotes", "n_no_cumplen", "cabezales_no_cumplen")},
                    "resumen_despues": despues["resumen"], "libro_despues": xlsx_path or None, "hojas": hojas,
                    "avisos": sep["avisos"] + rea["avisos"] + [a for a in avisos_analisis if a],
                    "pendiente": ["posiciones y ampliaciones: propuesta automatica, las fija el ingeniero",
                                  "reubicar los pilotes existentes en malla uniforme: no automatizado",
                                  "(b) pila equivalente y capacidad a traccion: sin evaluar",
                                  "cada iteracion es un analisis completo de la copia"]}
        return json.dumps(self._con_unidades(units, densificar), ensure_ascii=False, default=str)

    # ---------------- Grupos de SAFE por cabezal (claude, 2026-11-03) ---

    _GROUP_OBJ_TYPES = {1: "point", 2: "frame", 3: "cable", 4: "tendon", 5: "area", 6: "solid", 7: "link"}

    @com_call
    def assign_pile_groups(self, cap_types: str = "footing", sections: str | list[str] = "auto",
                           diameter_mm: float = 0.0, prefix: str = "", include_points: bool = False,
                           save: bool = False, units: str = "kN, m, C") -> str:
        """Crea en SAFE un grupo por cabezal (CAB-<area>) con el area y sus pilotes, para revisar por grupo. [escribe grupos en el modelo activo]

        Mismo agrupamiento que get_pile_spacing(scope=by_footing): el pilote pertenece al
        cabezal cuya area contiene su cabeza. Los grupos son datos del modelo: sin
        save=True se pierden al cerrar; con save=True se llama File.Save (hacerlo solo
        sobre una copia o con autorizacion). Un grupo existente con el mismo nombre se
        reutiliza (no se vacia): los objetos se agregan.

        Args:
            cap_types: areas de cabezal por tipo de losa o por seccion (p. ej. "Z50").
            sections, diameter_mm: filtro de pilotes como en get_pile_spacing.
            prefix: prefijo del nombre del grupo (vacio = "CAB-", el mismo que usa el libro).
            include_points: agregar tambien los nudos de cabeza y punta de cada pilote.
            save: guardar el modelo activo tras asignar.
            units: unidades activas durante la lectura (se restauran).
        """
        import json
        prefix = prefix or pilotes_xlsx.GROUP_PREFIX
        if not prefix.strip():
            raise SafeError("prefix no puede estar vacio.")

        def asignar():
            _idx, preset, _f, length = self._unidades_activas()
            mm = self._LENGTH_MM[length]
            pil, avisos, _secciones, n_frames = self._pilotes_leidos(sections, diameter_mm / mm, mm, True)
            cabezales = self._cabezales(cap_types)
            try:
                out = pilotes.evaluar_separacion(pil, "by_footing", 1, "step_down", cabezales)
            except pilotes.PilotesError as e:
                raise SafeError(str(e)) from e
            model = self._model()
            existentes = set(_result(model.GroupDef.GetNameList(), "GroupDef.GetNameList")[1])
            por_cab: dict[str, list] = {}
            for p in out["pilotes"]:
                if p.grupo is not None:
                    por_cab.setdefault(str(p.grupo), []).append(p)
            grupos, reutilizados = [], []
            for cab in cabezales:
                cid = str(cab["id"])
                nombre = f"{prefix}{cid}"
                miembros = por_cab.get(cid, [])
                if nombre in existentes:
                    reutilizados.append(nombre)
                else:
                    oapi.call_checked(model.GroupDef, "SetGroup", (nombre,), f"grupo {nombre}")
                oapi.call_checked(model.AreaObj, "SetGroupAssign", (cid, nombre, False, 0), f"area {cid} -> {nombre}")
                for p in miembros:
                    oapi.call_checked(model.FrameObj, "SetGroupAssign", (p.id, nombre, False, 0), f"pilote {p.id} -> {nombre}")
                    if include_points:
                        for pt in (p.punto_cabeza, p.punto_punta):
                            oapi.call_checked(model.PointObj, "SetGroupAssign", (pt, nombre, False, 0), f"punto {pt} -> {nombre}")
                n, tipos, nombres = _result(model.GroupDef.GetAssignments(nombre), f"GroupDef.GetAssignments({nombre})")[:3]
                if len(tipos) != n or len(nombres) != n:
                    raise SafeError(f"GetAssignments({nombre}): longitud incoherente.")
                asignados = {(int(t), str(o)) for t, o in zip(tipos, nombres)}
                esperados = {(5, cid)} | {(2, p.id) for p in miembros}
                if not esperados <= asignados:
                    raise SafeError(f"Grupo {nombre}: faltan al releer {sorted(esperados - asignados)[:5]}.")
                grupos.append({"grupo": nombre, "cabezal": cid, "seccion": cab["seccion"], "n_pilotes": len(miembros),
                               "pilotes": [p.id for p in miembros], "objetos_en_grupo": n})
            sueltos = [p.id for p in out["pilotes"] if p.grupo is None]
            guardado = False
            if save:
                oapi.call_checked(model.File, "Save", (), "guardado del modelo con grupos")
                guardado = True
            return {"herramienta": "assign_pile_groups", "modelo": model.GetModelFilename(),
                    "unidades": {"preset": preset},
                    "cap_types": cap_types, "prefijo": prefix, "n_grupos": len(grupos),
                    "n_pilotes_agrupados": sum(g["n_pilotes"] for g in grupos),
                    "pilotes_sin_cabezal": sueltos, "grupos_reutilizados": reutilizados,
                    "guardado": guardado, "grupos": grupos, "avisos": avisos + out["avisos"],
                    "nota": "Los grupos coinciden con la columna 'Grupo SAFE' y la hoja Grupos del libro. "
                            "Sin save=True se pierden al cerrar el modelo."}
        return json.dumps(self._con_unidades(units, asignar), ensure_ascii=False, default=str)
