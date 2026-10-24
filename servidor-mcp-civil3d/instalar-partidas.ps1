<# Optional Native pay item module. Never launches or restarts Civil 3D. #>
[CmdletBinding()]
param(
  [string]$Civil3DPath = 'C:\Program Files\Autodesk\AutoCAD 2027',
  [switch]$SoloCompilar
)
$ErrorActionPreference = 'Stop'
$project = Join-Path $PSScriptRoot 'modulo-partidas\Cdcrd.Partidas.csproj'
if (-not (Test-Path -LiteralPath (Join-Path $Civil3DPath 'C3D\AeccDbMgd.dll'))) {
  throw 'Civil 3D API references are required.'
}
& dotnet build $project -c Release "-p:Civil3DPath=$Civil3DPath" --nologo -v minimal
if ($LASTEXITCODE -ne 0) { throw 'Module build failed.' }
$source = Join-Path $PSScriptRoot 'modulo-partidas\bin\Release\net10.0-windows'
$dll = Join-Path $source 'Cdcrd.Partidas.V3.dll'
$hash = (Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant()
if ($SoloCompilar) { Write-Output $dll; return }
$bundle = Join-Path $env:APPDATA 'Autodesk\ApplicationPlugins\CDCRD-Partidas.bundle'
$build = 'build-' + $hash.Substring(0, 12)
$destination = Join-Path $bundle "Contents\$build"
New-Item -ItemType Directory -Path $destination -Force | Out-Null
Get-ChildItem -LiteralPath $source -File -Filter 'Cdcrd.Partidas.V3.*' | ForEach-Object {
  $target = Join-Path $destination $_.Name
  if (Test-Path -LiteralPath $target) {
    if ((Get-FileHash -LiteralPath $target).Hash -ne (Get-FileHash -LiteralPath $_.FullName).Hash) {
      throw "Existing immutable build differs: $target"
    }
  } else { Copy-Item -LiteralPath $_.FullName -Destination $target }
}
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'modulo-partidas\PackageContents.xml') -Raw
$manifest = $manifest.Replace('./Contents/', "./Contents/$build/")
Set-Content -LiteralPath (Join-Path $bundle 'PackageContents.xml') -Value $manifest -Encoding UTF8
Write-Output "Installed module SHA256 $hash. Existing loaded modules remain in use."
Write-Output "At the next normal Civil 3D start the bundle loads automatically. Do not open a second instance."
Write-Output "For a session without this assembly, NETLOAD once: $(Join-Path $destination 'Cdcrd.Partidas.V3.dll')"
