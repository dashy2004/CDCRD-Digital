# Compila TeklaPuente.exe contra la instalación local de Tekla Structures.
# Uso: .\compilar.ps1 [-Tekla "C:\Program Files\Tekla Structures\2026.0\bin"]
param([string]$Tekla = '')
$ErrorActionPreference = 'Stop'
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Tekla) {
    $Tekla = Get-ChildItem 'C:\Program Files\Tekla Structures' -Directory -ErrorAction SilentlyContinue |
        Sort-Object { [double]($_.Name -replace '[^0-9.]', '') } -Descending | ForEach-Object { Join-Path $_.FullName 'bin' } |
        Where-Object { Test-Path (Join-Path $_ 'Tekla.Structures.Model.dll') } | Select-Object -First 1
}
if (-not $Tekla) { throw 'No se encontró Tekla.Structures.Model.dll. Indique -Tekla con la carpeta bin.' }
$fx = "$env:windir\Microsoft.NET\Framework64\v4.0.30319"
$csc = Join-Path $fx 'csc.exe'
if (-not (Test-Path $csc)) { throw "No se encontró csc.exe en $fx" }
$refs = @('Tekla.Structures.dll', 'Tekla.Structures.Model.dll', 'Tekla.Structures.Catalogs.dll', 'Tekla.Structures.Drawing.dll') | ForEach-Object {
    $p = Join-Path $Tekla $_
    if (-not (Test-Path $p)) { $p = Join-Path $Tekla "Net48Runtime\$_" }
    if (-not (Test-Path $p)) { throw "Falta $_ en $Tekla" }
    "/r:$p"
}
$netstd = Get-ChildItem "$env:windir\Microsoft.NET" -Recurse -File -Filter 'netstandard.dll' -ErrorAction SilentlyContinue | Select-Object -Last 1 -ExpandProperty FullName
if ($netstd) { $refs += "/r:$netstd" }
$salida = Join-Path $aqui 'TeklaPuente.exe'
& $csc /nologo /target:exe /platform:x64 "/out:$salida" /r:System.Web.Extensions.dll @refs (Join-Path $aqui 'TeklaPuente.cs')
if ($LASTEXITCODE -ne 0) { throw 'La compilación falló.' }
# El ejecutable resuelve los ensamblados de Tekla con la misma configuración que TeklaStructures.exe.
$cfg = Join-Path $Tekla 'TeklaStructures.exe.config'
if (-not (Test-Path $cfg)) { throw "Falta $cfg" }
Copy-Item $cfg "$salida.config" -Force
Write-Output "Compilado: $salida"
Write-Output "Tekla: $Tekla"
