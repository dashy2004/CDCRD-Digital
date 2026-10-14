<#
  CDCRD-Digital - instalador del puente MCP para Civil 3D 2027
  Sin acentos a proposito: PowerShell 5.1 lee UTF-8 sin BOM como ANSI.

  Uso tipico (PowerShell normal, no es necesario Administrador):
      .\instalar.ps1
      .\instalar.ps1 -Probar                 # solo prueba el puente ya instalado
      .\instalar.ps1 -Civil3DPath "D:\Autodesk\AutoCAD 2027"
      .\instalar.ps1 -MostrarRegistroMCP     # imprime el JSON para el cliente MCP
#>
[CmdletBinding()]
param(
  [string]$Civil3DPath = "C:\Program Files\Autodesk\AutoCAD 2027",
  [string]$Configuracion = "Release",
  [int]$Puerto = 8760,
  [switch]$Probar,
  [switch]$SoloCompilar,
  [switch]$MostrarRegistroMCP
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$proyecto = Join-Path $raiz "puente\Cdcrd.Civil3dBridge.csproj"
$bundle = Join-Path $env:APPDATA "Autodesk\ApplicationPlugins\CDCRD-Civil3D.bundle"

function Paso($texto) { Write-Host "`n== $texto" -ForegroundColor Cyan }
function Bien($texto) { Write-Host "   OK  $texto" -ForegroundColor Green }
function Mal($texto)  { Write-Host "   --  $texto" -ForegroundColor Yellow }

function Probar-Puente([int]$p) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect("127.0.0.1", $p)
    $s = $c.GetStream()
    $w = New-Object System.IO.StreamWriter($s)
    $r = New-Object System.IO.StreamReader($s)
    $w.AutoFlush = $true
    $w.WriteLine('{"jsonrpc":"2.0","id":1,"method":"ping","params":{}}')
    $linea = $r.ReadLine()
    $c.Close()
    return $linea
  } catch {
    return $null
  }
}

if ($Probar) {
  Paso "Prueba del puente en el puerto $Puerto"
  $resp = Probar-Puente $Puerto
  if ($resp) { Bien "respuesta del puente:"; Write-Host "   $resp" }
  else { Mal "nadie responde en 127.0.0.1:$Puerto. Abra Civil 3D 2027 y, si hace falta, escriba CDCRDMCP en su linea de comandos" }
  return
}

if ($MostrarRegistroMCP) {
  $py = (Get-Command py -ErrorAction SilentlyContinue)
  $interprete = if ($py) { "py" } else { "python" }
  $servidor = (Join-Path $raiz "src\server.py")
  Paso "Entrada para el cliente MCP (dentro de mcpServers, sin borrar las existentes)"
  @"
    "civil3d": {
      "command": "<ruta completa del python real, no el shim>",
      "args": ["$($servidor -replace '\\','\\')"],
      "env": { "CDCRD_C3D_PORT": "$Puerto" }
    }
"@ | Write-Host
  Mal "obtenga la ruta real con:  $interprete -c `"import sys; print(sys.executable)`""
  return
}

Paso "1. Civil 3D 2027"
if (-not (Test-Path (Join-Path $Civil3DPath "acad.exe"))) { throw "No hay acad.exe en $Civil3DPath" }
if (-not (Test-Path (Join-Path $Civil3DPath "C3D\AeccDbMgd.dll"))) { throw "No hay C3D\AeccDbMgd.dll en ${Civil3DPath}: esa instalacion no es Civil 3D" }
Bien "referencias encontradas en $Civil3DPath"

Paso "2. SDK de .NET 10 (Civil 3D 2027 carga plugins en .NET 10)"
$sdks = & dotnet --list-sdks 2>$null
if (-not $sdks) { throw "No hay dotnet en el PATH. Instale el SDK con:  winget install Microsoft.DotNet.SDK.10" }
$tiene10 = @($sdks | Where-Object { $_ -match "^10\." }).Count -gt 0
if (-not $tiene10) {
  Write-Host ($sdks -join "`n")
  throw "Falta el SDK 10. Instalelo con:  winget install Microsoft.DotNet.SDK.10   (el runtime 10 ya esta, pero compilar necesita el SDK)"
}
Bien "SDK 10 disponible"

Paso "3. Compilar el puente"
& dotnet build $proyecto -c $Configuracion -p:Civil3DPath="$Civil3DPath" -v minimal --nologo | Write-Host
if ($LASTEXITCODE -ne 0) { throw "la compilacion fallo" }
$salida = Join-Path $raiz "puente\bin\$Configuracion"
$dll = Join-Path $salida "Cdcrd.Civil3dBridge.dll"
if (-not (Test-Path $dll)) { throw "no se genero $dll" }
Bien "compilado: $dll"

if ($SoloCompilar) { return }

Paso "4. Instalar el bundle en ApplicationPlugins"
# Cada build va a su propia carpeta Contents\build-<hash> y el manifiesto apunta a ella:
# asi se puede instalar con Civil 3D abierto (el DLL cargado queda bloqueado y no se
# puede borrar) y el reinicio toma la version nueva. Los builds viejos se borran si
# se dejan; si estan bloqueados se conservan y se avisa.
$hash = (Get-FileHash $dll -Algorithm SHA256).Hash.ToLower()
$carpetaBuild = "build-" + $hash.Substring(0, 12)
$contents = Join-Path $bundle "Contents"
$destino = Join-Path $contents $carpetaBuild
New-Item -ItemType Directory -Path $destino -Force | Out-Null
# Solo lo propio: las DLL de Autodesk no se copian (se referencian desde la instalacion)
Get-ChildItem $salida -File | Where-Object {
  $_.Name -like "Cdcrd.Civil3dBridge.*"
} | ForEach-Object { Copy-Item $_.FullName $destino -Force }
$manifiesto = Get-Content (Join-Path $raiz "puente\PackageContents.xml") -Raw
$manifiesto = $manifiesto -replace 'SupportPath="\./Contents"', ('SupportPath="./Contents/' + $carpetaBuild + '"')
$manifiesto = $manifiesto -replace 'ModuleName="\./Contents/Cdcrd\.Civil3dBridge\.dll"', ('ModuleName="./Contents/' + $carpetaBuild + '/Cdcrd.Civil3dBridge.dll"')
Set-Content (Join-Path $bundle "PackageContents.xml") $manifiesto -Encoding UTF8
# limpiar builds anteriores y el DLL suelto de la primera version; lo bloqueado se queda
Get-ChildItem $contents -Directory | Where-Object { $_.Name -like "build-*" -and $_.Name -ne $carpetaBuild } | ForEach-Object {
  $viejo = $_   # dentro de catch, $_ es el error, no el elemento
  try { Remove-Item $viejo.FullName -Recurse -Force -ErrorAction Stop; Write-Host "       borrado build anterior $($viejo.Name)" }
  catch { Write-Host "       AVISO: $($viejo.Name) bloqueado (Civil 3D abierto); se borra en la proxima instalacion" }
}
Get-ChildItem $contents -File | ForEach-Object {
  $suelto = $_
  try { Remove-Item $suelto.FullName -Force -ErrorAction Stop } catch { Write-Host "       AVISO: $($suelto.Name) bloqueado; se borra en la proxima instalacion" }
}
Bien "bundle en $bundle"
Bien "manifiesto -> Contents/$carpetaBuild (SHA256 $hash)"
Get-ChildItem $destino | ForEach-Object { Write-Host "       $($_.Name)" }

Paso "5. Que falta (lo hace usted)"
Write-Host @"
   a) Cierre y vuelva a abrir Civil 3D 2027. El puente arranca solo con el dibujo
      abierto; CDCRDMCPINFO en la linea de comandos muestra su estado.
   b) Verifique:  .\instalar.ps1 -Probar
   c) Registre el servidor MCP:  .\instalar.ps1 -MostrarRegistroMCP
   d) Variables opcionales del entorno de Civil 3D:
        CDCRD_C3D_PORT=$Puerto               puerto del puente
        CDCRD_C3D_SOLO_LECTURA=1             apaga toda escritura
        CDCRD_C3D_PERMITIR_COMANDOS=1        habilita ejecutar_comando
      Se definen para el usuario y Civil 3D debe reiniciarse para verlas.
   Log del puente: %LOCALAPPDATA%\CdcrdCivil3dBridge\puente.log
"@
