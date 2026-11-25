[CmdletBinding()]
param([string]$TeklaBin = 'C:\Program Files\Tekla Structures\2026.0\bin')
$ErrorActionPreference = 'Stop'
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
$refs = @(
    (Join-Path $TeklaBin 'Tekla.Macros.Runtime.dll'),
    (Join-Path $TeklaBin 'Net48Runtime\Tekla.Structures.dll'),
    (Join-Path $TeklaBin 'Tekla.Structures.Model.dll'),
    (Join-Path $TeklaBin 'Tekla.Structures.Drawing.dll'),
    (Join-Path (Split-Path $compiler) 'netstandard.dll')
)
foreach ($file in @($compiler) + $refs) {
    if (!(Test-Path -LiteralPath $file -PathType Leaf)) { throw "Falta $file." }
}
$out = Join-Path ([System.IO.Path]::GetTempPath()) ('pruebas-tekla-' + [guid]::NewGuid().ToString('N'))
New-Item $out -ItemType Directory | Out-Null
try {
    $dll = Join-Path $out 'InventarioPiezas.dll'
    $exe = Join-Path $out 'Prueba.exe'
    $references = $refs | ForEach-Object { "/reference:$_" }
    & $compiler /nologo /target:library /platform:x64 "/out:$dll" @references '/r:System.Windows.Forms.dll' '/r:System.Runtime.Serialization.dll' (Join-Path $PSScriptRoot '../InventarioPiezas.cs')
    if ($LASTEXITCODE) { throw 'Falló la compilación con Tekla Open API 2026.' }
    & $compiler /nologo /target:exe /platform:x64 "/out:$exe" "/r:$dll" '/r:System.Runtime.Serialization.dll' (Join-Path $PSScriptRoot 'Prueba.cs')
    if ($LASTEXITCODE) { throw 'Falló la compilación de la prueba.' }
    & $exe
    if ($LASTEXITCODE) { throw 'Falló la prueba de contrato.' }
} finally {
    foreach ($name in 'InventarioPiezas.dll','Prueba.exe') {
        $file = Join-Path $out $name
        if (Test-Path -LiteralPath $file -PathType Leaf) { Remove-Item -LiteralPath $file }
    }
    [System.IO.Directory]::Delete($out)
}
