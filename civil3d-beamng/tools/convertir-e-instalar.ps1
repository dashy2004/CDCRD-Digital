<# Convertir un snapshot y preparar un nivel nuevo. No requiere IA ni MCP. #>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Snapshot,
    [Parameter(Mandatory=$true)][string]$Output,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-z][a-z0-9_]{0,47}$')][string]$LevelId,
    [string]$Python = 'python',
    [string]$GameFolder = 'C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive',
    [string]$UserFolder = (Join-Path $env:LOCALAPPDATA 'BeamNG\BeamNG.drive\current'),
    [switch]$AutoImport
)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path -LiteralPath $Snapshot -PathType Leaf)) { throw 'Snapshot inexistente' }
if (Test-Path -LiteralPath $Output) { throw 'Use una carpeta de salida nueva' }
$Snapshot = (Resolve-Path -LiteralPath $Snapshot).ProviderPath
$Output = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($Output)
$GameFolder = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($GameFolder)
$UserFolder = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($UserFolder)
if ($Python.Contains('\') -or $Python.Contains('/')) {
    $Python = (Resolve-Path -LiteralPath $Python).ProviderPath
}
Push-Location $project
try {
    & $Python -m cdcrd_beamng build --snapshot $Snapshot --output $Output --level-id $LevelId
    if ($LASTEXITCODE -ne 0) { throw 'Fallo la conversion; no se instala un paquete incompleto' }
    $installArgs = @((Join-Path $project 'tools\prepare_drive.py'), '--package', $Output,
        '--user-folder', $UserFolder, '--game-folder', $GameFolder)
    if ($AutoImport) { $installArgs += '--auto-import' }
    & $Python @installArgs
    if ($LASTEXITCODE -ne 0) { throw 'Fallo la preparacion del nivel; consulte el error anterior' }
    Write-Output ('Nivel preparado: ' + $LevelId)
    Write-Output 'Abra este nivel en Freeroam. En World Editor: Window > Importar Civil 3D.'
} finally {
    Pop-Location
}
