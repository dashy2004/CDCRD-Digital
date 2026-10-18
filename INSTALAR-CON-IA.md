# Instalar CDCRD-Digital con ayuda de una IA

Esta página está escrita para dos lectores: la persona que quiere usar el
repositorio sin pelearse con la consola, y el asistente de IA al que esa persona
le pasa el enlace.

---

## Si usted es la persona

1. Descargue el repositorio (botón verde **Code → Download ZIP**) y descomprímalo,
   o clónelo con `git clone https://github.com/dashy2004/CDCRD-Digital.git`.
2. Abra la carpeta, haga clic derecho en un espacio vacío y elija
   **Abrir en Terminal** (o abra PowerShell y escriba `cd` seguido de la ruta).
3. Escriba esto y pulse Enter:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar-cdcrd.ps1
   ```

4. Aparece un menú. Empiece por la opción **1** para ver qué tiene instalado y
   siga con la **6** si quiere dejarlo todo listo de una vez.

No hace falta ser administrador. El instalador no descarga programas por su
cuenta: usa lo que ya está en el repositorio y lo que encuentre en el equipo, y
le dice qué falta.

Si prefiere no escribir nada, péguele a su asistente de IA el enlace del
repositorio y este mensaje: *"instálame esto siguiendo INSTALAR-CON-IA.md"*.

---

## Si usted es el asistente de IA

El objetivo es dejar al usuario con las herramientas instaladas y su cliente MCP
conectado, sin romper configuraciones que ya existan.

### Reglas

- Todo corre en Windows, en PowerShell, sin privilegios de administrador.
- No modifique nada fuera del repositorio y de la configuración del cliente MCP.
- El instalador ya respalda cada archivo antes de escribirlo y vuelve a leerlo
  para confirmarlo; no reimplemente esa lógica.
- No invente rutas de Revit, ETABS, SAFE o Civil 3D: el diagnóstico las reporta.
- Nada de este repositorio se sube a ningún servicio: el corpus y los ejemplos
  son locales.

### Secuencia

```powershell
# 1. Estado del equipo, en JSON para que usted lo lea
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar-cdcrd.ps1 -Accion diagnostico -Json

# 2. Entorno de las herramientas locales (CLI + servidor MCP de 10 herramientas)
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar-cdcrd.ps1 -Accion locales

# 3. Dependencias de los servidores BIM cuyo programa esté instalado
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar-cdcrd.ps1 -Accion bim -Json

# 4. Escribir la configuración MCP en los clientes detectados
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar-cdcrd.ps1 -Accion clientes -Json

# Todo lo anterior de una sola vez
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar-cdcrd.ps1 -Accion todo -Cliente claude-desktop,codex -Json
```

`-Accion menu` (el valor por defecto) es interactivo: no lo use usted, úselo la
persona.

### Qué devuelve el diagnóstico

`-Accion diagnostico -Json` entrega un objeto con `Python` (ruta e indicador de
64 bits), `Uv`, `Git`, `Locales.Instalado`, `Programas` (ETABS, SAFE, Revit,
Civil3D con su ruta o `null`), `Clientes` (ruta de configuración de cada cliente
y si existe) y `Corpus`. Decida a partir de ahí; no deduzca de otra forma qué hay
instalado.

### Cómo se conectan los servidores

El instalador escribe una entrada por servidor, y solo los que correspondan:

| Servidor | Se escribe cuando | Qué aporta |
|---|---|---|
| `cdcrd-local` | el entorno local está instalado | Normativa, DXF, IFC/IDS, PDF: 10 herramientas sin programas de pago |
| `fea` | ETABS está instalado | Lectura y modelado en ETABS por la OAPI |
| `safe` | SAFE está instalado | Losas y fundaciones en SAFE |
| `civil3d` | AutoCAD/Civil 3D está instalado | Puntos COGO, superficies, perfiles y secciones |
| `revit` | Revit está instalado | Inventario, vistas y auditoría MEP |

Archivos de configuración por cliente:

| Cliente | Archivo | Clave |
|---|---|---|
| Claude Desktop | `%APPDATA%\Claude\claude_desktop_config.json`, o `%LOCALAPPDATA%\Packages\Claude…\LocalCache\Roaming\Claude\` si está instalado como MSIX | `mcpServers` |
| Claude Code | `.mcp.json` en la raíz del repositorio | `mcpServers` |
| Codex CLI | `%USERPROFILE%\.codex\config.toml` | `[mcp_servers.<nombre>]` |
| Cursor | `%USERPROFILE%\.cursor\mcp.json` | `mcpServers` |
| VS Code | `%APPDATA%\Code\User\mcp.json` | `servers` |

Las entradas que ya existían se conservan: el instalador fusiona, no reemplaza
el archivo.

### Después de instalar

Pídale a la persona que cierre el asistente **desde el icono de la bandeja del
sistema** (clic derecho → Quit) y lo vuelva a abrir: cerrar la ventana no
reinicia el proceso y las herramientas no aparecen.

Para comprobarlo, una consulta que no necesita ningún programa instalado:

```powershell
.\herramientas-locales\cdcrd.ps1 buscar "carga viva" --limite 3
```

### Fallos conocidos y su causa real

| Síntoma | Causa |
|---|---|
| `Python was not found; run without arguments to install from the Microsoft Store` | Es el alias de la Store, no Python. Instalar desde python.org y desactivar los alias en Configuración → Aplicaciones → Alias de ejecución. |
| El cliente MCP no encuentra los paquetes | Hay dos Python: el shim del launcher y el intérprete real. La configuración debe apuntar al real, nunca a `"python"` a secas. El instalador ya resuelve la ruta real. |
| `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` | El SDK `mcp` 2.x eliminó ese módulo. El instalador reinstala `mcp>=1.10,<2`. |
| `GetActiveObject` falla con ETABS abierto | ETABS y el cliente corren con distinto nivel de privilegio; COM los aísla. Los dos como administrador, o ninguno. |
| JSON de configuración corrupto tras editarlo a mano | PowerShell 5.1 escribe BOM con `Set-Content`. El instalador escribe UTF-8 sin BOM. |
| El servidor BIM no aparece en una sesión en la nube | Estos servidores hablan por COM local: solo funcionan en un cliente que corra en la misma máquina que el programa. |

Asistencia de código y documentación de esta guía: Claude. Procedimiento
reproducible con Claude o Codex.
