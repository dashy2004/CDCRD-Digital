# ---------------------------------------------------------------------------
# Repunta la entrada "fea" de Claude Desktop al servidor v1.1.0 (44 tools).
#
# No copia archivos ni sobrescribe C:\FEA-MCP: solo cambia la ruta que el
# cliente lanza. Reversible con el .bak que deja en el paso 3.
#
# Ejecutar en Windows PowerShell (5.1). No requiere Administrador.
# ---------------------------------------------------------------------------

[CmdletBinding()]
param(
    [string]$Config,     # por defecto, el archivo que Claude Desktop lee en este equipo
    [string]$Python      # por defecto, el interprete real detras de py/python
)

$ErrorActionPreference = 'Stop'

# Rutas de este equipo: la configuracion de Claude Desktop y el interprete real salen
# de las mismas funciones que usa instalar-cdcrd.ps1 (la app ha cambiado de carpeta
# entre versiones; ver Get-RutaClaudeDesktop). Se cargan en un ambito propio (& { })
# para que los parametros y variables del instalador no pisen los de este script.
$instalador = Join-Path (Split-Path -Parent $PSScriptRoot) 'instalar-cdcrd.ps1'
$equipo = & {
    $env:CDCRD_INSTALADOR_SOLO_FUNCIONES = '1'
    try { . $instalador } finally { Remove-Item Env:\CDCRD_INSTALADOR_SOLO_FUNCIONES }
    $real = Get-PythonReal
    [pscustomobject]@{ Config = Get-RutaClaudeDesktop; Python = $(if ($real) { $real.Ruta }) }
}
$cfg = if ($Config) { $Config } else { $equipo.Config }
$py  = if ($Python) { $Python } else { $equipo.Python }
if (-not $py) { throw "No se encontro Python. Instale Python 64 bits o pase -Python 'ruta'." }
$src   = Join-Path $PSScriptRoot "src"
$nuevo = Join-Path $src "server.py"
Write-Host "Config de Claude Desktop: $cfg"

# --- 1. Existencia -----------------------------------------------------------
foreach ($p in @($cfg, $nuevo, $py)) {
    if (-not (Test-Path -LiteralPath $p)) { throw "No existe: $p" }
}
Write-Host "[1/5] Rutas verificadas." -ForegroundColor Green

# --- 2. Imports con el interprete REAL ---------------------------------------
# Si esto falla, el config NO se toca. Es la comprobacion que evita dejar el
# cliente apuntando a un servidor que muere al arrancar.
$probe = @"
import sys
sys.path.insert(0, r'$src')
from mcp.server.fastmcp import FastMCP, Context
import comtypes, comtypes.client, pydantic
import config, comthread, oapi, Etabs
import mcp as _m
print('IMPORTS OK - mcp', _m.__version__ if hasattr(_m,'__version__') else '?')
"@
& $py -c $probe
if ($LASTEXITCODE -ne 0) {
    throw "Fallo de imports con $py. El config NO fue modificado. Revisar 'mcp<2' y comtypes."
}
Write-Host "[2/5] Imports OK con el interprete real." -ForegroundColor Green

# --- 3. Respaldo -------------------------------------------------------------
$bak = "$cfg.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
Copy-Item -LiteralPath $cfg -Destination $bak
Write-Host "[3/5] Respaldo: $bak" -ForegroundColor Green

# --- 4. Repuntar -------------------------------------------------------------
$j = Get-Content -LiteralPath $cfg -Raw | ConvertFrom-Json

Write-Host "`n--- entrada 'fea' ANTES ---" -ForegroundColor Yellow
if ($j.mcpServers) { $j.mcpServers.fea | ConvertTo-Json -Depth 10 }

if (-not $j.mcpServers -or -not $j.mcpServers.fea) {
    throw "El config no tiene la entrada 'fea'. Use instalar-cdcrd.ps1 para crearla."
}
$j.mcpServers.fea.args = @($nuevo)

# WriteAllText sin BOM: Set-Content -Encoding UTF8 en PS 5.1 escribe BOM y
# rompe a cualquier consumidor que parsee el texto.
$txt = $j | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($cfg, $txt, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "[4/5] Config reescrito sin BOM." -ForegroundColor Green

# --- 5. Releer desde disco y confirmar ---------------------------------------
$v = Get-Content -LiteralPath $cfg -Raw | ConvertFrom-Json
Write-Host "`n--- entrada 'fea' DESPUES ---" -ForegroundColor Yellow
$v.mcpServers.fea | ConvertTo-Json -Depth 10

if ($v.mcpServers.fea.args[0] -ne $nuevo) { throw "La ruta no quedo aplicada." }
Write-Host "`n[5/5] LISTO." -ForegroundColor Green
Write-Host "Siguiente: salir de Claude Desktop DESDE LA BANDEJA (cerrar la ventana no basta)," -ForegroundColor Cyan
Write-Host "reabrir Claude Desktop y ETABS al MISMO nivel de privilegio, y abrir una" -ForegroundColor Cyan
Write-Host "conversacion NUEVA. Deben aparecer 44 herramientas 'fea'." -ForegroundColor Cyan
Write-Host "`nPara revertir:  Copy-Item '$bak' '$cfg' -Force" -ForegroundColor DarkGray
