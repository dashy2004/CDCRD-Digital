$ErrorActionPreference = 'Stop'
try {
    $motor = Join-Path $PSScriptRoot 'memoria-diseno'
    $aplicacion = Join-Path $PSScriptRoot 'app/MemoriaPlus.exe'
    $candidatos = @(
        (Join-Path $motor '.venv/Scripts/python.exe')
        (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'MemoriaPlus/Runtime de fuentes/Scripts/python.exe')
        (Join-Path ([Environment]::GetFolderPath('UserProfile')) 'Documents/MemoriaPlus/Runtime de fuentes/Scripts/python.exe')
        foreach ($ruta in @($env:MEMORIA_DISENO_DIR, [Environment]::GetEnvironmentVariable('MEMORIA_DISENO_DIR', 'User'))) {
            if ($ruta) { Join-Path $ruta '.venv/Scripts/python.exe' }
        }
        (Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source)
    )
    $python = $null
    foreach ($candidato in $candidatos | Select-Object -Unique) {
        if (!$candidato -or !(Test-Path -LiteralPath $candidato -PathType Leaf) -or $candidato -match '\\Microsoft\\WindowsApps\\') { continue }
        & $candidato -c 'import docx, matplotlib, pymupdf, PIL, xlrd, openpyxl, comtypes, win32gui'
        if ($LASTEXITCODE -eq 0) { $python = $candidato; break }
    }
    if (!$python) { throw 'Faltan las dependencias Python del generador. Consulte LEEME.txt, apartado Primer uso en otro equipo.' }
    $env:PATH = (Split-Path $python) + ';' + $env:PATH
    $env:MEMORIA_DISENO_DIR = $motor
    $env:PYTHONDONTWRITEBYTECODE = "1"
    Start-Process -FilePath $aplicacion -WorkingDirectory $PSScriptRoot -ArgumentList '--diseno','--modo=calculos','--tab=Generar'
} catch {
    Write-Host $_.Exception.Message
    exit 1
}
