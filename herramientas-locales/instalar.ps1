param([switch]$Pruebas)
$ErrorActionPreference = 'Stop'
$projectPath = $PSScriptRoot
$repoPath = Split-Path -Parent $projectPath
$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uvCommand) {
    throw 'Falta uv. Instalarlo desde https://docs.astral.sh/uv/getting-started/installation/ y repetir.'
}

& $uvCommand.Source sync --project $projectPath --python 3.13 --locked
if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar el entorno bloqueado.' }
$pythonPath = Join-Path $projectPath '.venv\Scripts\python.exe'
& $pythonPath -m cdcrd_local.cli doctor
if ($LASTEXITCODE -ne 0) { throw 'Fallo el diagnostico del entorno.' }

$localPath = Join-Path $projectPath '.local'
New-Item -ItemType Directory -Path $localPath -Force | Out-Null
$mcpConfig = @{mcpServers = @{'cdcrd-local' = @{
    command = $pythonPath
    args = @('-m','cdcrd_local.server')
    env = @{CDCRD_REPO_ROOT = $repoPath; PYTHONUTF8 = '1'}
}}}
$mcpConfig | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $localPath 'mcp-config.json') -Encoding UTF8
Write-Output "Configuracion MCP: $localPath\mcp-config.json"
if ($Pruebas) {
    & $uvCommand.Source run --project $projectPath --frozen pytest (Join-Path $projectPath 'tests')
    if ($LASTEXITCODE -ne 0) { throw 'Fallaron las pruebas locales.' }
}
Write-Output 'Entorno listo. Uso: .\herramientas-locales\cdcrd.ps1 doctor'
