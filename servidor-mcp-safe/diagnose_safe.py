# SAFE MCP
# Diagnostico de la cadena Python -> COM -> SAFE.
# Ejecutar EN WINDOWS, con SAFE abierto y un modelo cargado:
#     python diagnose_safe.py
#
# A diferencia de diagnose_etabs.py (que ya conoce el ProgID exacto de
# ETABS), este script todavia tiene que DESCUBRIR el ProgID de SAFE en esta
# instalacion: prueba varios candidatos y reporta cual funciona. Copie el
# resultado a config.json (safe.prog_id / safe.helper_prog_id) cuando lo
# tenga, para que el servidor no tenga que sondear en cada arranque.

import os
import platform
import struct
import sys

OK = "[ OK ]"
BAD = "[FALLA]"
WARN = "[AVISO]"

problems = []


def check(label, fn):
    try:
        result = fn()
        print(f"{OK}  {label}: {result}")
        return True
    except Exception as e:
        print(f"{BAD}  {label}: {type(e).__name__}: {e}")
        problems.append(label)
        return False


print("=" * 68)
print("DIAGNOSTICO SAFE-MCP")
print("=" * 68)

# 1. Entorno
print(f"{OK}  Python: {sys.version.split()[0]}  ({struct.calcsize('P') * 8} bits)")
print(f"{OK}  Ejecutable: {sys.executable}")
print(f"{OK}  Sistema: {platform.system()} {platform.release()}")

if platform.system() != "Windows":
    print(f"{BAD}  La OAPI de CSI solo funciona en Windows. Abortando.")
    sys.exit(1)

if struct.calcsize('P') * 8 != 64:
    print(f"{BAD}  Python de 32 bits. SAFE moderno es de 64 bits. "
          f"La conexion COM fallara. Instale Python 64 bits.")
    problems.append("arquitectura")

if sys.version_info < (3, 10):
    print(f"{WARN} Python {sys.version_info.major}.{sys.version_info.minor}. "
          f"El SDK de MCP requiere 3.10 o superior.")
    problems.append("version de Python")

# 2. Dependencias
print("-" * 68)


def _ver(mod):
    m = __import__(mod)
    return getattr(m, "__version__", "instalado")


check("comtypes", lambda: _ver("comtypes"))
check("pydantic", lambda: _ver("pydantic"))

try:
    mcp_ver = _ver("mcp")
    major = int(str(mcp_ver).split(".")[0])
    from mcp.server.fastmcp import FastMCP  # noqa: F401
    print(f"{OK}  mcp (SDK): {mcp_ver} - mcp.server.fastmcp importable")
    if major >= 2:
        print(f"{BAD}  SDK 2.x detectado pese al import. Fije: "
              f'pip install "mcp>=1.10,<2" --force-reinstall')
        problems.append("version de mcp")
except ImportError as e:
    print(f"{BAD}  mcp.server.fastmcp no importable: {e}")
    print(f'       Corrija con: pip install "mcp>=1.10,<2" --force-reinstall')
    problems.append("version de mcp")
except Exception as e:
    print(f"{BAD}  mcp (SDK): {e}")
    problems.append("mcp")

# 3. Cache de comtypes
print("-" * 68)
try:
    import comtypes.client
    gen_dir = comtypes.client.gen_dir
    print(f"{OK}  Cache comtypes.gen: {gen_dir}")
    if gen_dir and not os.access(gen_dir, os.W_OK):
        print(f"{BAD}  Sin permiso de escritura en el cache. comtypes no podra "
              f"generar el wrapper de la typelib de SAFE.")
        problems.append("permisos comtypes.gen")
except Exception as e:
    print(f"{BAD}  comtypes.client no disponible: {e}")
    problems.append("comtypes.client")
    sys.exit(1)

# 4. Sondeo de ProgID/Helper de SAFE
print("-" * 68)
print("Sondeando ProgID de SAFE (NINGUNO confirmado todavia)...")

PROGID_CANDIDATES = [
    "CSI.SAFE.API.SapObject",
    "CSI.SAFE.API.SAFEObject",
    "CSI.SAFE.API.ETABSObject",
]
HELPER_CANDIDATES = [
    "SAFEv1.Helper",
    "CSI.SAFE.API.Helper",
]

try:
    import comtypes
    comtypes.CoInitialize()
except Exception as e:
    print(f"{BAD}  CoInitialize fallo: {e}")
    sys.exit(1)

safe_object = None
prog_id_ok = None
helper_ok = None

# Ruta A: GetActiveObject directo por cada ProgID candidato.
for pid in PROGID_CANDIDATES:
    try:
        safe_object = comtypes.client.GetActiveObject(pid)
        prog_id_ok = pid
        print(f"{OK}  GetActiveObject('{pid}') -> instancia encontrada")
        break
    except Exception as e:
        print(f"{WARN} GetActiveObject('{pid}') fallo: {type(e).__name__}: {e}")

# Ruta B: cHelper, si la Ruta A no encontro nada.
if safe_object is None:
    for helper_pid in HELPER_CANDIDATES:
        try:
            helper = comtypes.client.CreateObject(helper_pid)
            print(f"{OK}  CreateObject('{helper_pid}') -> typelib registrada")
        except Exception as e:
            print(f"{WARN} CreateObject('{helper_pid}') fallo: {type(e).__name__}: {e}")
            continue
        for pid in PROGID_CANDIDATES:
            try:
                obj = helper.GetObject(pid)
                if obj is not None:
                    safe_object = obj
                    prog_id_ok = pid
                    helper_ok = helper_pid
                    print(f"{OK}  {helper_pid}.GetObject('{pid}') -> instancia encontrada")
                    break
                print(f"{WARN} {helper_pid}.GetObject('{pid}') devolvio None")
            except Exception as e:
                print(f"{WARN} {helper_pid}.GetObject('{pid}') fallo: "
                      f"{type(e).__name__}: {e}")
        if safe_object is not None:
            break

if safe_object is None:
    print("-" * 68)
    print("RESULTADO: sin conexion con SAFE con NINGUNO de los candidatos probados.")
    print("Revise en orden:")
    print("  1. SAFE abierto con un modelo cargado (no solo la pantalla inicial).")
    print("  2. Python 64 bits (verificado arriba).")
    print("  3. Mismo nivel de privilegios: si SAFE corre como Administrador,")
    print("     Claude Desktop tambien debe correr como Administrador.")
    print("  4. Busque el ProgID real en el registro de Windows:")
    print(r"     reg query HKCR /f SAFE /k /s   (o revise HKEY_CLASSES_ROOT con")
    print(r"     regedit, buscando 'SAFE' bajo CSI / SAFE.API / similar).")
    print("  5. Con el ProgID encontrado, agreguelo a PROGID_CANDIDATES arriba")
    print("     y vuelva a correr este script.")
    sys.exit(1)

print("-" * 68)
print(f"RESULTADO: conectado con ProgID='{prog_id_ok}'"
      + (f", Helper='{helper_ok}'" if helper_ok else " (via GetActiveObject directo)"))
print()
print("Copie esto a servidor-mcp-safe/src/config.json:")
print("  \"safe\": {")
print(f"    \"prog_id\": \"{prog_id_ok}\",")
print(f"    \"helper_prog_id\": \"{helper_ok or ''}\",")
print("    ...")
print("  }")

# 5. SapModel y llamadas basicas
print("-" * 68)
try:
    sap = safe_object.SapModel
    print(f"{OK}  SapModel obtenido")
except Exception as e:
    print(f"{BAD}  SapModel: {e}")
    sys.exit(1)

check("GetOAPIVersionNumber", lambda: safe_object.GetOAPIVersionNumber())
check("GetModelFilename", lambda: sap.GetModelFilename() or "(sin guardar)")
check("GetPresentUnits", lambda: sap.GetPresentUnits())
check("PointObj.GetAllPoints", lambda: f"{sap.PointObj.GetAllPoints()[0]} puntos")
check("AreaObj.GetAllAreas", lambda: f"{sap.AreaObj.GetAllAreas()[0]} areas")
check("DatabaseTables.GetAvailableTables",
      lambda: f"{sap.DatabaseTables.GetAvailableTables()[0]} tablas")

print("=" * 68)
if problems:
    print(f"RESULTADO: {len(problems)} problema(s): {', '.join(problems)}")
    sys.exit(1)
print("RESULTADO: cadena Python -> COM -> SAFE operativa.")
print("Siguiente paso: fijar prog_id/helper_prog_id en config.json y usar")
print("describe_oapi (path='PropArea', 'PropAreaSpring', 'File', etc.) desde")
print("el servidor MCP para confirmar los metodos que Safe.py todavia marca")
print("como NO VERIFICADO.")
