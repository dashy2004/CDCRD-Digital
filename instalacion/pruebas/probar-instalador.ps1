<#
  Pruebas de instalar-cdcrd.ps1 que no tocan la configuracion real del equipo.
  Sin acentos a proposito (PowerShell 5.1 lee UTF-8 sin BOM como ANSI).

      powershell -NoProfile -ExecutionPolicy Bypass -File instalacion\pruebas\probar-instalador.ps1

  Trabaja en una carpeta temporal y la borra al terminar. Sale con 1 si algo falla.
#>
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$env:CDCRD_INSTALADOR_SOLO_FUNCIONES = '1'
try { . (Join-Path $raiz 'instalar-cdcrd.ps1') } finally { Remove-Item Env:\CDCRD_INSTALADOR_SOLO_FUNCIONES }
$script:Raiz = $raiz
$script:Json = $true        # sin texto decorativo

$fallos = 0
function Assert-Igual {
    param([string]$Caso, $Obtenido, $Esperado)
    if ("$Obtenido" -eq "$Esperado") { Write-Host "[ OK ] $Caso" -ForegroundColor Green }
    else { Write-Host "[FALLA] $Caso`n        obtenido: $Obtenido`n        esperado: $Esperado" -ForegroundColor Red; $script:fallos++ }
}

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("cdcrd-inst-" + [guid]::NewGuid().ToString('N'))
$nombre = 'claude_desktop_config.json'
try {
    # ---- 1. Donde guarda Claude Desktop su configuracion -------------------
    function New-Equipo {
        param([string]$Id)
        $e = Join-Path $tmp $Id
        $local = Join-Path $e 'Local'; $roaming = Join-Path $e 'Roaming'
        New-Item -ItemType Directory -Path $local, $roaming -Force | Out-Null
        [pscustomobject]@{ Local = $local; Roaming = $roaming
                           Msix = Join-Path $local 'Packages\Claude_abc123\LocalCache\Roaming\Claude'
                           Datos = Join-Path $local 'Claude-Data\claude_abc123' }
    }

    $e = New-Equipo 'clasico'
    Assert-Igual 'sin MSIX ni Claude-Data usa %APPDATA%\Claude' `
        (Get-RutaClaudeDesktop -LocalAppData $e.Local -AppData $e.Roaming) (Join-Path $e.Roaming "Claude\$nombre")

    $e = New-Equipo 'msix'
    New-Item -ItemType Directory -Path $e.Msix -Force | Out-Null
    Assert-Igual 'MSIX en uso se respeta' `
        (Get-RutaClaudeDesktop -LocalAppData $e.Local -AppData $e.Roaming) (Join-Path $e.Msix $nombre)

    $e = New-Equipo 'migrado'
    New-Item -ItemType Directory -Path $e.Msix, $e.Datos -Force | Out-Null
    New-Item -ItemType File -Path (Join-Path $e.Msix '.user-data-left.claude_abc123') | Out-Null
    Set-Content -LiteralPath (Join-Path $e.Msix $nombre) -Value '{}'      # resto de una instalacion anterior
    Assert-Igual 'tras migrar, gana Claude-Data aunque quede un config viejo en MSIX' `
        (Get-RutaClaudeDesktop -LocalAppData $e.Local -AppData $e.Roaming) (Join-Path $e.Datos $nombre)

    $e = New-Equipo 'abandonada'
    New-Item -ItemType Directory -Path $e.Msix -Force | Out-Null
    New-Item -ItemType File -Path (Join-Path $e.Msix '.user-data-left.claude_abc123') | Out-Null
    Assert-Igual 'carpeta MSIX abandonada y sin Claude-Data no se usa' `
        (Get-RutaClaudeDesktop -LocalAppData $e.Local -AppData $e.Roaming) (Join-Path $e.Roaming "Claude\$nombre")

    $e = New-Equipo 'dos-paquetes'
    $vacio = Join-Path $e.Local 'Claude-Data\claude_otro'
    New-Item -ItemType Directory -Path $e.Datos, $vacio -Force | Out-Null
    Set-Content -LiteralPath (Join-Path $e.Datos $nombre) -Value '{}'
    (Get-Item -LiteralPath $vacio).LastWriteTime = (Get-Date).AddDays(1)
    Assert-Igual 'con dos carpetas en Claude-Data gana la que ya tiene config' `
        (Get-RutaClaudeDesktop -LocalAppData $e.Local -AppData $e.Roaming) (Join-Path $e.Datos $nombre)

    # ---- 2. Escritura: conserva lo ajeno, respalda y no mete BOM ------------
    $cfg = Join-Path $e.Datos $nombre
    $previo = '{"preferences":{"tema":"oscuro","lista":[1]},"mcpServers":{"ajeno":{"command":"x.exe","args":["a"]}}}'
    [System.IO.File]::WriteAllText($cfg, $previo, (New-Object System.Text.UTF8Encoding($false)))
    $nuevas = @{ tekla = @{ command = 'python.exe'; args = @('C:\repo\servidor-mcp-tekla\src\server.py'); env = @{ PYTHONUTF8 = '1' } } }
    $claves = Merge-JsonMcp -Ruta $cfg -Entradas $nuevas
    $leido = Get-Content -LiteralPath $cfg -Raw -Encoding UTF8 | ConvertFrom-Json
    Assert-Igual 'se anade tekla' (($claves | Sort-Object) -join ',') 'ajeno,tekla'
    Assert-Igual 'la entrada ajena se conserva' $leido.mcpServers.ajeno.command 'x.exe'
    Assert-Igual 'las preferencias se conservan' $leido.preferences.tema 'oscuro'
    Assert-Igual 'una lista de un elemento sigue siendo lista' ($leido.preferences.lista -is [array]) $true
    Assert-Igual 'args de tekla es una lista' ($leido.mcpServers.tekla.args -is [array]) $true
    Assert-Igual 'queda un respaldo' (@(Get-ChildItem -LiteralPath $e.Datos -Filter "$nombre.bak-*").Count) 1
    Assert-Igual 'sin BOM' ([System.IO.File]::ReadAllBytes($cfg)[0]) 123

    Set-Content -LiteralPath $cfg -Value '{ esto no es json'
    $mensaje = ''
    try { Merge-JsonMcp -Ruta $cfg -Entradas $nuevas | Out-Null } catch { $mensaje = $_.Exception.Message }
    Assert-Igual 'un config corrupto no se toca' ($mensaje -like '*no es JSON valido*') $true
    Assert-Igual 'y queda como estaba' ((Get-Content -LiteralPath $cfg -Raw).Trim()) '{ esto no es json'

    # ---- 3. Tekla entra en la lista solo si esta instalado -------------------
    $d = [pscustomobject]@{
        Locales   = [pscustomobject]@{ Instalado = $false; Python = '' }
        Python    = [pscustomobject]@{ Ruta = 'C:\py\python.exe'; Bits = 64 }
        Programas = [pscustomobject]@{ ETABS = $null; SAFE = $null; Revit = $null; Civil3D = $null; Tekla = 'C:\Program Files\Tekla Structures\2026.0' }
    }
    $srv = Get-ServidoresMcp $d
    Assert-Igual 'con Tekla instalado se ofrece el servidor tekla' (@($srv.Keys) -join ',') 'tekla'
    Assert-Igual 'apunta al server.py del repositorio' $srv['tekla'].args[0] (Join-Path $raiz 'servidor-mcp-tekla\src\server.py')
    $d.Programas.Tekla = $null
    Assert-Igual 'sin Tekla no se ofrece' (@((Get-ServidoresMcp $d).Keys).Count) 0
}
finally {
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
}

if ($fallos) { Write-Host "`n$fallos comprobaciones fallaron." -ForegroundColor Red; exit 1 }
Write-Host "`nTodas las comprobaciones pasaron." -ForegroundColor Green
