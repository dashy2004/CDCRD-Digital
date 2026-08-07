# Instalar el servidor MCP de ETABS (Windows)

Guia battle-tested: cada advertencia de este documento corresponde a un fallo real ocurrido
durante la primera instalacion. Si se siguen los pasos en orden, la instalacion toma ~15 min.

## Requisitos

- Windows con ETABS instalado (probado con ETABS 23.3, OAPI 2.016)
- Python 3.10+ de **64 bits** (3.14 verificado)
- Claude Desktop (u otro cliente MCP por stdio)

La OAPI de CSI **no se instala aparte**: viene con ETABS. Desde Python no hay nada de CSI
que instalar; `comtypes` lee la typelib del COM que el instalador de ETABS ya registro.

## 1. Python

```powershell
py -c "import sys,struct; print(sys.version, struct.calcsize('P')*8, 'bits'); print(sys.executable)"
```

Debe decir `64 bits`. **Anote la ruta** que imprime `sys.executable` — la necesita en el paso 5.

| Problema real | Causa |
|---|---|
| `Python was not found; run without arguments to install from the Microsoft Store` | Es el stub de la Store, no Python. Use `py`, o instale desde python.org y desactive los alias en Configuracion > Aplicaciones > Alias de ejecucion de aplicaciones. |
| Todo instala pero el cliente MCP no encuentra los paquetes | Hay DOS python: el shim del launcher (`...\Python\bin\python.exe`) y el interprete real (`...\pythoncore-X.Y-64\python.exe`). `pip` instala en el real. El config del cliente debe apuntar al **real**, nunca a `"python"` a secas: el cliente no hereda su PATH. |

## 2. Dependencias

```powershell
py -m pip install -r requirements.txt
py -c "import importlib.metadata as m; print('mcp', m.version('mcp'))"
py -c "from mcp.server.fastmcp import FastMCP; print('fastmcp OK')"
```

`mcp` debe ser **1.x** y el segundo comando debe imprimir `fastmcp OK`.

| Problema real | Causa |
|---|---|
| `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` | Tiene `mcp` 2.x. El SDK 2.0.0 elimino ese modulo. Corrija: `py -m pip install "mcp>=1.10,<2" --force-reinstall`. Este fue el fallo numero uno de la instalacion original. |

## 3. Verificar la cadena COM (antes de tocar el cliente)

Con ETABS **abierto y un modelo cargado** (no la pantalla de inicio):

```powershell
py diagnose_etabs.py
```

Debe terminar en `RESULTADO: cadena Python -> COM -> ETABS operativa`. Prueba minima equivalente:

```powershell
py -c "import comtypes.client as c; c.CreateObject('ETABSv1.Helper'); o=c.GetActiveObject('CSI.ETABS.API.ETABSObject'); print(o.SapModel.GetModelFilename())"
```

| Problema real | Causa |
|---|---|
| `GetActiveObject` falla con ETABS visiblemente abierto | **Niveles de privilegio distintos**: si ETABS corre como Administrador y el cliente no (o al reves), COM los aisla y no hay error claro. Ejecute AMBOS al mismo nivel. Fue la causa final de la instalacion original, despues de que todo lo demas estaba correcto. |
| `ETABSv1.Helper` no registrado | Ejecute ETABS una vez como Administrador, o repare la instalacion (Panel de control > ETABS > Repair). |

## 4. Copiar el servidor

Copie la carpeta `servidor-mcp/` a una ruta estable sin espacios, p. ej. `C:\FEA-MCP\`.
Debe quedar `C:\FEA-MCP\src\server.py`.

**Verifique cada archivo despues de copiar** (conteo de lineas o parseo):

```powershell
py -c "import ast; ast.parse(open(r'C:\FEA-MCP\src\server.py',encoding='utf-8').read()); print('OK')"
```

| Problema real | Causa |
|---|---|
| `can't open file '...server.py': No such file or directory` en el log del cliente | Un archivo no se copio y nadie lo verifico. Verificar N archivos requiere N confirmaciones. |
| `SyntaxError: invalid non-printable character U+FEFF` | El archivo se genero con `Set-Content -Encoding UTF8` en PowerShell 5.1, que escribe BOM. Regenerarlo con `[System.IO.File]::WriteAllText($ruta,$texto,(New-Object System.Text.UTF8Encoding($false)))`. |

## 5. Registrar en el cliente

`claude_desktop_config.json` — agregue dentro de `mcpServers`, sin borrar entradas existentes:

```json
{
  "mcpServers": {
    "fea": {
      "command": "C:\\ruta\\exacta\\del\\paso1\\python.exe",
      "args": ["C:\\FEA-MCP\\src\\server.py"]
    }
  }
}
```

Doble backslash en todas las rutas. `command` = la ruta del paso 1, no `"python"`.

| Problema real | Causa |
|---|---|
| El archivo de config no esta en `%APPDATA%\Claude` | Claude Desktop empaquetado como **MSIX** escribe en `%LOCALAPPDATA%\Packages\<paquete-Claude>\LocalCache\Roaming\Claude\`. Busque ahi antes de concluir que no existe. |
| JSON roto tras editarlo | No tipear bloques multilinea en Notepad (el auto-indent los rompe). Pegar desde el portapapeles o usar Find & Replace para cambios puntuales. |

## 6. Reiniciar de verdad y verificar

Cierre el cliente desde el **icono de la bandeja del sistema** (clic derecho > Quit) — cerrar
la ventana no reinicia el proceso. Reabra y pregunte: "Lista las herramientas FEA disponibles".

Deben aparecer 10: `get_model_info`, `get_units`, `set_units`, `save_model`, `refresh_view`,
`create_objects_by_coordinates`, `get_all_geometries`, `get_points`, `get_frames`, `get_areas`.

Log por servidor: `...\LocalCache\Roaming\Claude\logs\mcp-server-fea.log`. Un
`Server started and connected successfully` seguido de `Server transport closed unexpectedly`
significa que el proceso arranco y murio en el import — el traceback esta unas lineas arriba.

## 7. Antes de crear geometria

Use `File > New Model` con grillas y niveles definidos, no el modelo en blanco:
`AddByCoord` necesita stories para asignar los objetos.

## Nota de arquitectura

El servidor habla con ETABS por COM local: **solo funciona en un cliente que corra en la misma
maquina que ETABS**. Una sesion en la nube puede editar estos archivos pero jamas vera las
herramientas.
