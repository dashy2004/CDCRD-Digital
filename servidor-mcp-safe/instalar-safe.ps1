# ---------------------------------------------------------------------------
# Agrega (o actualiza) la entrada "safe" en Claude Desktop, sin tocar la
# entrada "fea" existente. Mismo patron de seguridad que
# servidor-mcp/desplegar-v1.1.ps1: prueba los imports con el interprete real
# ANTES de tocar el config, respalda el config antes de escribir, relee desde
# disco para confirmar.
#
# Ejecutar en Windows PowerShell (5.1). No requiere Administrador.
# PRERREQUISITO: haber corrido diagnose_safe.py con SAFE abierto y haber
# confirmado (o al menos intentado) el prog_id en src/config.json. Este
# script NO lo hace por usted: solo conecta el servidor a Claude Desktop.
# ---------------------------------------------------------------------------

$ErrorActionPreference = 'Stop'

$cfg = "C:\Users\emilg\AppData\Local\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json"
$src = "C:\Users\emilg\Artificial IQ\CDCRD-Digital\servidor-mcp-safe\src"
$srv = Join-Path $src "server.py"
$py  = "C:\Users\emilg\AppData\Local\Python\pythoncore-3.14-64\python.exe"

# --- 1. Existencia -----------------------------------------------------------
foreach ($p in @($cfg, $srv, $py)) {
    if (-not (Test-Path -LiteralPath $p)) { throw "No existe: $p" }
}
Write-Host "[1/5] Rutas verificadas." -ForegroundColor Green

# --- 2. Imports con el interprete REAL ---------------------------------------
$probe = @"
import sys
sys.path.insert(0, r'$src')
from mcp.server.fastmcp import FastMCP, Context
import comtypes, comtypes.client, pydantic
import config, comthread, oapi, Safe
import mcp as _m
print('IMPORTS OK - mcp', _m.__version__ if hasattr(_m,'__version__') else '?')
"@
& $py -c $probe
if ($LASTEXITCODE -ne 0) {
    throw "Fallo de imports con $py. El config NO fue modificado. Revisar 'mcp<2', comtypes y pydantic instalados para este interprete (pip install -r requirements.txt)."
}
Write-Host "[2/5] Imports OK con el interprete real." -ForegroundColor Green

# --- 3. Respaldo -------------------------------------------------------------
$bak = "$cfg.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
Copy-Item -LiteralPath $cfg -Destination $bak
Write-Host "[3/5] Respaldo: $bak" -ForegroundColor Green

# --- 4. Agregar/actualizar la entrada "safe" (sin tocar "fea") ---------------
$j = Get-Content -LiteralPath $cfg -Raw | ConvertFrom-Json

if (-not $j.mcpServers) {
    throw "El config no tiene mcpServers. Reviselo manualmente antes de continuar."
}

$entradaSafe = [PSCustomObject]@{
    command = $py
    args    = @($srv)
}

if ($j.mcpServers.PSObject.Properties.Name -contains 'safe') {
    Write-Host "`n--- entrada 'safe' ANTES ---" -ForegroundColor Yellow
    $j.mcpServers.safe | ConvertTo-Json -Depth 10
    $j.mcpServers.safe = $entradaSafe
} else {
    $j.mcpServers | Add-Member -NotePropertyName 'safe' -NotePropertyValue $entradaSafe
}

$txt = $j | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($cfg, $txt, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "[4/5] Config reescrito sin BOM." -ForegroundColor Green

# --- 5. Releer desde disco y confirmar ---------------------------------------
$v = Get-Content -LiteralPath $cfg -Raw | ConvertFrom-Json
Write-Host "`n--- entrada 'safe' DESPUES ---" -ForegroundColor Yellow
$v.mcpServers.safe | ConvertTo-Json -Depth 10

if ($v.mcpServers.safe.args[0] -ne $srv) { throw "La ruta no quedo aplicada." }
Write-Host "`n[5/5] LISTO." -ForegroundColor Green
Write-Host "Siguiente: salir de Claude Desktop DESDE LA BANDEJA (cerrar la ventana no basta)," -ForegroundColor Cyan
Write-Host "reabrir Claude Desktop y SAFE al MISMO nivel de privilegio, y abrir una" -ForegroundColor Cyan
Write-Host "conversacion NUEVA. Deben aparecer las herramientas 'safe' junto a las 'fea'." -ForegroundColor Cyan
Write-Host "`nPara revertir:  Copy-Item '$bak' '$cfg' -Force" -ForegroundColor DarkGray
