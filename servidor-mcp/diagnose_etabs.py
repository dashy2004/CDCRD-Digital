# FEA MCP - fix
# Diagnostico de la cadena Python -> COM -> ETABS.
# Ejecutar EN WINDOWS, con ETABS abierto y un modelo cargado:
#     python diagnose_etabs.py

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
print("DIAGNOSTICO FEA-MCP / ETABS")
print("=" * 68)

# 1. Entorno
print(f"{OK}  Python: {sys.version.split()[0]}  ({struct.calcsize('P') * 8} bits)")
print(f"{OK}  Ejecutable: {sys.executable}")
print(f"{OK}  Sistema: {platform.system()} {platform.release()}")

if platform.system() != "Windows":
    print(f"{BAD}  La OAPI de CSI solo funciona en Windows. Abortando.")
    sys.exit(1)

if struct.calcsize('P') * 8 != 64:
    print(f"{BAD}  Python de 32 bits. ETABS moderno es de 64 bits. "
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

# pywin32 es opcional: este codigo no lo importa.
try:
    __import__("win32com")
    print(f"{OK}  pywin32: instalado (opcional)")
except Exception:
    print(f"{WARN} pywin32 no instalado. No es requerido por este servidor.")

# El SDK de MCP debe ser 1.x: la 2.0.0 elimino mcp.server.fastmcp.
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
              f"generar el wrapper de la typelib de ETABS.")
        problems.append("permisos comtypes.gen")
except Exception as e:
    print(f"{BAD}  comtypes.client no disponible: {e}")
    problems.append("comtypes.client")
    sys.exit(1)

# 4. Conexion a ETABS
print("-" * 68)
PROG_ID = "CSI.ETABS.API.ETABSObject"
etabs_object = None

try:
    import comtypes
    comtypes.CoInitialize()
except Exception as e:
    print(f"{BAD}  CoInitialize fallo: {e}")
    sys.exit(1)

try:
    etabs_object = comtypes.client.GetActiveObject(PROG_ID)
    print(f"{OK}  GetActiveObject('{PROG_ID}') -> instancia encontrada")
except Exception as e:
    print(f"{WARN} GetActiveObject fallo: {type(e).__name__}: {e}")
    print(f"       Causa habitual: ETABS no esta abierto, o corre como "
          f"Administrador mientras Python no (o viceversa).")

if etabs_object is None:
    try:
        helper = comtypes.client.CreateObject('ETABSv1.Helper')
        print(f"{OK}  CreateObject('ETABSv1.Helper') -> typelib registrada")
        try:
            import comtypes.gen.ETABSv1 as ETABSv1
            helper = helper.QueryInterface(ETABSv1.cHelper)
            print(f"{OK}  QueryInterface(cHelper) -> wrapper generado")
        except Exception as e:
            print(f"{WARN} QueryInterface(cHelper): {e} (se usara late binding)")
        etabs_object = helper.GetObject(PROG_ID)
        print(f"{OK}  cHelper.GetObject -> instancia encontrada")
    except Exception as e:
        print(f"{BAD}  cHelper tambien fallo: {type(e).__name__}: {e}")
        problems.append("conexion ETABS")

if etabs_object is None:
    print("-" * 68)
    print("RESULTADO: sin conexion con ETABS.")
    print("Revise en orden:")
    print("  1. ETABS abierto con un modelo cargado (no solo la pantalla inicial).")
    print("  2. Python 64 bits (verificado arriba).")
    print("  3. Mismo nivel de privilegios: si ETABS corre como Administrador,")
    print("     Claude Desktop tambien debe correr como Administrador.")
    print("  4. Reparar la instalacion de ETABS para re-registrar la typelib COM.")
    sys.exit(1)

# 5. SapModel
print("-" * 68)
try:
    sap = etabs_object.SapModel
    print(f"{OK}  SapModel obtenido")
except Exception as e:
    print(f"{BAD}  SapModel: {e}")
    sys.exit(1)

check("GetOAPIVersionNumber", lambda: etabs_object.GetOAPIVersionNumber())
check("GetModelFilename", lambda: sap.GetModelFilename() or "(sin guardar)")
check("GetPresentUnits", lambda: sap.GetPresentUnits())
check("PointObj.GetAllPoints", lambda: f"{sap.PointObj.GetAllPoints()[0]} puntos")
check("FrameObj.GetAllFrames", lambda: f"{sap.FrameObj.GetAllFrames()[0]} frames")
check("AreaObj.GetAllAreas", lambda: f"{sap.AreaObj.GetAllAreas()[0]} areas")

print("=" * 68)
if problems:
    print(f"RESULTADO: {len(problems)} problema(s): {', '.join(problems)}")
    sys.exit(1)
print("RESULTADO: cadena Python -> COM -> ETABS operativa.")
print("Puede configurar el servidor MCP en Claude Desktop.")
