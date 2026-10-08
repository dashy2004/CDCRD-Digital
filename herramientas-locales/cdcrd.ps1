$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Ejecute primero .\herramientas-locales\instalar.ps1'
}
$env:PYTHONUTF8 = '1'
& $pythonPath -m cdcrd_local.cli @args
exit $LASTEXITCODE
