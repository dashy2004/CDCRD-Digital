<#
.SYNOPSIS
  Deja el motor memoria-diseno listo en este equipo y le enseña a Claude a usarlo.

.DESCRIPTION
  1. Crea el entorno .venv del motor e instala sus dependencias.
  2. Guarda la ruta del motor en la variable de usuario MEMORIA_DISENO_DIR (la usa LosasPlus).
  3. Copia la skill «memoria-de-calculo» a la carpeta de skills de Claude del usuario, con la
     ruta de este motor, para que cualquier sesión genere la memoria con el mismo formato.

  No necesita privilegios de administrador. Se puede volver a ejecutar sin daño.

.PARAMETER Destino
  Carpeta donde se escribe la skill. Por defecto, %USERPROFILE%\.claude\skills\memoria-de-calculo.

.PARAMETER SinEntorno
  No crea el entorno ni instala dependencias; solo escribe la skill.
#>
[CmdletBinding()]
param(
    [string]$Destino = (Join-Path $env:USERPROFILE '.claude\skills\memoria-de-calculo'),
    [switch]$SinEntorno
)
$ErrorActionPreference = 'Stop'
$motor = $PSScriptRoot

if (-not $SinEntorno) {
    $venvPython = Join-Path $motor '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython)) {
        $lanzador = Get-Command py, python -ErrorAction SilentlyContinue |
            Where-Object { $_.Source -notlike '*WindowsApps*' } | Select-Object -First 1
        if (-not $lanzador) {
            throw 'No se encontró Python. Instálelo desde https://www.python.org/downloads/ y repita.'
        }
        & $lanzador.Source -m venv (Join-Path $motor '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno .venv.' }
    }
    & $venvPython -m pip install --quiet -r (Join-Path $motor 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias del motor.' }
    [Environment]::SetEnvironmentVariable('MEMORIA_DISENO_DIR', $motor, 'User')
    Write-Host "Entorno listo: $venvPython"
}

$plantilla = Get-Content -LiteralPath (Join-Path $motor 'skill\SKILL.md') -Raw -Encoding UTF8
New-Item -ItemType Directory -Force -Path $Destino | Out-Null
$salida = Join-Path $Destino 'SKILL.md'
[IO.File]::WriteAllText($salida, $plantilla.Replace('{{MOTOR}}', $motor), [Text.UTF8Encoding]::new($false))

Write-Host "Skill instalada: $salida"
Write-Host "Motor: $motor"
Write-Host 'Abra una sesión nueva de Claude y pida la memoria de cálculo del proyecto.'
