<#
  CDCRD-Digital - instalador del puente MCP para AutoCAD 2027
  Sin acentos a proposito: PowerShell 5.1 lee UTF-8 sin BOM como ANSI.

  Uso tipico (PowerShell normal, no es necesario Administrador):
      .\instalar-autocad.ps1
      .\instalar-autocad.ps1 -Probar                 # solo prueba el puente ya instalado
      .\instalar-autocad.ps1 -AutoCADPath "D:\Autodesk\AutoCAD 2027"
      .\instalar-autocad.ps1 -MostrarRegistroMCP     # imprime el JSON para el cliente MCP
#>
[CmdletBinding()]
param(
  [string]$AutoCADPath = "C:\Program Files\Autodesk\AutoCAD 2027",
  [string]$Configuracion = "Release",
  [int]$Puerto = 8764,
  [switch]$Probar,
  [switch]$SoloCompilar,
  [switch]$MostrarRegistroMCP
)

$ErrorActionPreference = "Stop"
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$proyecto = Join-Path $raiz "puente-autocad\Cdcrd.AutoCadBridge.csproj"
$bundle = Join-Path $env:APPDATA "Autodesk\ApplicationPlugins\CDCRD-AutoCAD.bundle"

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
  else { Mal "nadie responde en 127.0.0.1:$Puerto. Abra AutoCAD 2027 y, si hace falta, escriba CDCRDMCP en su linea de comandos" }
  return
}

if ($MostrarRegistroMCP) {
  $py = (Get-Command py -ErrorAction SilentlyContinue)
  $interprete = if ($py) { "py" } else { "python" }
  $servidor = (Join-Path $raiz "src\server.py")
  Paso "Entrada para el cliente MCP (dentro de mcpServers, sin borrar las existentes)"
  @"
    "autocad": {
      "command": "<ruta completa del python real, no el shim>",
      "args": ["$($servidor -replace '\\','\\')"],
      "env": { "CDCRD_C3D_PORT": "$Puerto" }
    }
"@ | Write-Host
  Mal "obtenga la ruta real con:  $interprete -c `"import sys; print(sys.executable)`""
  return
}

Paso "1. AutoCAD 2027"
if (-not (Test-Path (Join-Path $AutoCADPath "acad.exe"))) { throw "No hay acad.exe en $AutoCADPath" }
Bien "referencias encontradas en $AutoCADPath"

Paso "2. SDK de .NET 10 (AutoCAD 2027 carga plugins en .NET 10)"
$sdks = & dotnet --list-sdks 2>$null
if (-not $sdks) { throw "No hay dotnet en el PATH. Instale el SDK con:  winget install Microsoft.DotNet.SDK.10" }
$tiene10 = @($sdks | Where-Object { $_ -match "^10\." }).Count -gt 0
if (-not $tiene10) {
  Write-Host ($sdks -join "`n")
  throw "Falta el SDK 10. Instalelo con:  winget install Microsoft.DotNet.SDK.10   (el runtime 10 ya esta, pero compilar necesita el SDK)"
}
Bien "SDK 10 disponible"

Paso "3. Compilar el puente"
& dotnet build $proyecto -c $Configuracion -p:AutoCADPath="$AutoCADPath" -v minimal --nologo | Write-Host
if ($LASTEXITCODE -ne 0) { throw "la compilacion fallo" }
$salida = Join-Path $raiz "puente-autocad\bin\$Configuracion"
$dll = Join-Path $salida "Cdcrd.AutoCadBridge.dll"
if (-not (Test-Path $dll)) { throw "no se genero $dll" }
Bien "compilado: $dll"

if ($SoloCompilar) { return }

Paso "4. Instalar el bundle en ApplicationPlugins"
# Cada build va a su propia carpeta Contents\build-<hash> y el manifiesto apunta a ella:
# asi se puede instalar con AutoCAD abierto (el DLL cargado queda bloqueado y no se
# puede borrar) y el reinicio toma la version nueva. Los builds viejos se borran si
# se dejan; si estan bloqueados se conservan y se avisa.
$hash = (Get-FileHash $dll -Algorithm SHA256).Hash.ToLower()
$carpetaBuild = "build-" + $hash.Substring(0, 12)
$contents = Join-Path $bundle "Contents"
$destino = Join-Path $contents $carpetaBuild
New-Item -ItemType Directory -Path $destino -Force | Out-Null
# Solo lo propio: las DLL de Autodesk no se copian (se referencian desde la instalacion)
Get-ChildItem $salida -File | Where-Object {
  $_.Name -like "Cdcrd.AutoCadBridge.*"
} | ForEach-Object { Copy-Item $_.FullName $destino -Force }
$manifiesto = Get-Content (Join-Path $raiz "puente-autocad\PackageContents.xml") -Raw
$manifiesto = $manifiesto -replace 'SupportPath="\./Contents"', ('SupportPath="./Contents/' + $carpetaBuild + '"')
$manifiesto = $manifiesto -replace 'ModuleName="\./Contents/Cdcrd\.AutoCadBridge\.dll"', ('ModuleName="./Contents/' + $carpetaBuild + '/Cdcrd.AutoCadBridge.dll"')
Set-Content (Join-Path $bundle "PackageContents.xml") $manifiesto -Encoding UTF8
# Builds anteriores se conservan para permitir rollback.
Bien "bundle en $bundle"
Bien "manifiesto -> Contents/$carpetaBuild (SHA256 $hash)"
Get-ChildItem $destino | ForEach-Object { Write-Host "       $($_.Name)" }

Paso "5. Que falta (lo hace usted)"
Write-Host @"
   a) Cierre y vuelva a abrir AutoCAD 2027. El puente arranca solo con el dibujo
      abierto; CDCRDMCPINFO en la linea de comandos muestra su estado.
   b) Verifique:  .\instalar-autocad.ps1 -Probar
   c) Registre el servidor MCP:  .\instalar-autocad.ps1 -MostrarRegistroMCP
   d) Variables opcionales del entorno de AutoCAD:
        CDCRD_C3D_PORT=$Puerto               puerto del puente
        CDCRD_C3D_SOLO_LECTURA=1             apaga toda escritura
        CDCRD_C3D_PERMITIR_COMANDOS=1        habilita ejecutar_comando
      Se definen para el usuario y AutoCAD debe reiniciarse para verlas.
   Log del puente: %LOCALAPPDATA%\CdcrdCivil3dBridge\puente.log
"@
