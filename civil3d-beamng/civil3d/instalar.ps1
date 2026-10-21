<#
  Exportador Civil 3D 2027 a BeamNG.drive. PowerShell 5.1+, .NET SDK 10.
  Texto ASCII para evitar problemas de codificacion en Windows PowerShell.
  .\instalar.ps1 -SoloCompilar
  .\instalar.ps1
#>
[CmdletBinding()]
param(
  [string]$Civil3DPath = "C:\Program Files\Autodesk\AutoCAD 2027",
  [ValidateSet("Debug", "Release")][string]$Configuracion = "Release",
  [string]$BundleRoot = (Join-Path $env:APPDATA "Autodesk\ApplicationPlugins\CDCRD-BeamNG.bundle"),
  [switch]$SoloCompilar
)

$ErrorActionPreference = "Stop"
$taskRoot = $PSScriptRoot
$project = Join-Path $taskRoot "Cdcrd.BeamngExport.csproj"
$dotnet = (Get-Command dotnet.exe -ErrorAction SilentlyContinue).Source
if (-not $dotnet) {
  $dotnet = Join-Path $env:ProgramFiles "dotnet\dotnet.exe"
}
if (-not (Test-Path -LiteralPath $dotnet)) { throw "Falta .NET SDK 10 en Windows." }
if (-not (Test-Path -LiteralPath (Join-Path $Civil3DPath "C3D\AeccDbMgd.dll"))) {
  throw "No se encontraron las DLL de Civil 3D 2027 en Civil3DPath."
}
$sdks = & $dotnet --list-sdks
if ($LASTEXITCODE -ne 0 -or -not @($sdks | Where-Object { $_ -match '^10\.' }).Count) {
  throw "Falta .NET SDK 10 (no basta tener el runtime)."
}
Write-Host "Compilando exportador de solo lectura..."
& $dotnet build $project -c $Configuracion "-p:Civil3DPath=$Civil3DPath" --nologo -v minimal
if ($LASTEXITCODE -ne 0) { throw "La compilacion fallo; no se modifico ningun bundle." }
$output = Join-Path $taskRoot "bin\$Configuracion"
$dll = Join-Path $output "Cdcrd.BeamngExport.dll"
if (-not (Test-Path -LiteralPath $dll)) { throw "No se genero la DLL esperada." }
$hash = (Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash.ToLowerInvariant()
Write-Host "Compilado: $dll"
Write-Host "SHA256: $hash"
if ($SoloCompilar) { return }

# Own bundle only. Old builds and manifests are never deleted or overwritten.
$buildName = "build-" + $hash.Substring(0, 12)
$destination = Join-Path $BundleRoot "Contents\$buildName"
if (Test-Path -LiteralPath $destination) {
  $installedDll = Join-Path $destination "Cdcrd.BeamngExport.dll"
  if (-not (Test-Path -LiteralPath $installedDll) -or
      (Get-FileHash -LiteralPath $installedDll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $hash) {
    throw "La carpeta versionada existe con contenido diferente. Se conserva sin cambios: $destination"
  }
  Write-Host "Se reutiliza el build identico ya conservado."
} else {
  New-Item -ItemType Directory -Path $destination | Out-Null
  Get-ChildItem -LiteralPath $output -File | Where-Object { $_.Name -like "Cdcrd.BeamngExport.*" } |
    ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $destination }
}
$manifestPath = Join-Path $BundleRoot "PackageContents.xml"
if (Test-Path -LiteralPath $manifestPath) {
  $archive = Join-Path $BundleRoot "Manifests"
  New-Item -ItemType Directory -Path $archive -Force | Out-Null
  $archiveName = "PackageContents-" + [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssfffZ") + "-" + [Guid]::NewGuid().ToString("N") + ".xml"
  Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $archive $archiveName)
}
$manifest = Get-Content -LiteralPath (Join-Path $taskRoot "PackageContents.xml") -Raw
$manifest = $manifest.Replace('SupportPath="./Contents"', ('SupportPath="./Contents/' + $buildName + '"'))
$manifest = $manifest.Replace('ModuleName="./Contents/Cdcrd.BeamngExport.dll"', ('ModuleName="./Contents/' + $buildName + '/Cdcrd.BeamngExport.dll"'))
$temporaryManifest = Join-Path $BundleRoot ("PackageContents-" + [Guid]::NewGuid().ToString("N") + ".tmp")
[System.IO.File]::WriteAllText($temporaryManifest, $manifest, [System.Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $temporaryManifest -Destination $manifestPath -Force
Write-Host "Bundle instalado: $BundleRoot"
Write-Host "Los builds y manifiestos anteriores se conservan. No se cargo codigo en Civil 3D."
Write-Host "En Civil 3D 2027, reinicie cuando corresponda y ejecute CDCRDBEAMNGEXPORT."
