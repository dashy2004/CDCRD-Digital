<#
  CDCRD-Digital - registra el servidor MCP de Civil 3D en el cliente.
  Sin acentos a proposito (PowerShell 5.1 lee UTF-8 sin BOM como ANSI).

      .\registrar-mcp.ps1              # muestra que haria, no escribe nada
      .\registrar-mcp.ps1 -Aplicar     # escribe, con respaldo del archivo

  Si el cliente no usa claude_desktop_config.json, el script lo dice y deja el
  bloque JSON listo para pegar en la configuracion de servidores MCP locales.
#>
[CmdletBinding()]
param(
  [string]$Config = (Join-Path $env:APPDATA "Claude\claude_desktop_config.json"),
  [string]$Python,
  [int]$Puerto = 8760,
  [switch]$Aplicar
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$servidor = Join-Path $raiz "src\server.py"

if (-not (Test-Path $servidor)) { throw "No se encontro $servidor" }

if (-not $Python) {
  $Python = (& py -c "import sys; print(sys.executable)" 2>$null)
  if (-not $Python) { throw "No se pudo determinar el python real. Pase -Python 'ruta'." }
}
if (-not (Test-Path $Python)) { throw "No existe el interprete $Python" }

# Verificar que ese interprete tiene el SDK correcto antes de registrar nada
$chequeo = & $Python -c "from mcp.server.fastmcp import FastMCP; import importlib.metadata as m; print(m.version('mcp'))" 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host $chequeo
  throw "Ese interprete no puede importar mcp.server.fastmcp. Instale:  `"$Python`" -m pip install -r requirements.txt"
}
Write-Host "   OK  interprete $Python con mcp $chequeo" -ForegroundColor Green

$entrada = [ordered]@{
  command = $Python
  args    = @($servidor)
  env     = @{ CDCRD_C3D_PORT = "$Puerto" }
}

$json = [ordered]@{ mcpServers = [ordered]@{ civil3d = $entrada } } | ConvertTo-Json -Depth 6
Write-Host "`n== Entrada 'civil3d'" -ForegroundColor Cyan
Write-Host $json

if (-not (Test-Path $Config)) {
  Write-Host "`n   --  No existe $Config" -ForegroundColor Yellow
  Write-Host "       Este cliente administra los servidores MCP locales desde su propia"
  Write-Host "       configuracion (los mismos ajustes donde ya estan fea, revit y safe)."
  Write-Host "       Agregue ahi el servidor con:"
  Write-Host "         comando:   $Python"
  Write-Host "         argumento: $servidor"
  Write-Host "         variable:  CDCRD_C3D_PORT=$Puerto"
  return
}

if (-not $Aplicar) {
  Write-Host "`n   --  Simulacion. Repita con -Aplicar para escribir en $Config" -ForegroundColor Yellow
  return
}

$respaldo = "$Config.bak_" + (Get-Date -Format "yyyyMMdd_HHmmss")
Copy-Item $Config $respaldo
Write-Host "   OK  respaldo en $respaldo" -ForegroundColor Green

$cfg = Get-Content $Config -Raw | ConvertFrom-Json
if (-not $cfg.mcpServers) { $cfg | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) }
$cfg.mcpServers | Add-Member -NotePropertyName civil3d -NotePropertyValue ([pscustomobject]$entrada) -Force
$texto = $cfg | ConvertTo-Json -Depth 20
[System.IO.File]::WriteAllText($Config, $texto, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "   OK  civil3d registrado en $Config" -ForegroundColor Green
Write-Host "       Reinicie el cliente MCP para que lo cargue."
