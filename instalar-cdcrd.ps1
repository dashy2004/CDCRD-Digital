<#
.SYNOPSIS
    Instalador y panel de control de CDCRD-Digital.

.DESCRIPTION
    Menu interactivo para Windows PowerShell que diagnostica el equipo, instala
    las herramientas locales, conecta los servidores MCP de ETABS, SAFE, Revit y
    Civil 3D, comprueba el corpus normativo y deja configurado el asistente de IA
    que el usuario ya tenga instalado.

    Todo lo que escribe se respalda antes y se vuelve a leer para confirmarlo.
    No pide privilegios de administrador y no descarga nada por su cuenta: solo
    usa lo que ya esta en este repositorio y los programas que encuentre.

.PARAMETER Accion
    menu (por defecto) abre el panel. Las demas corren sin preguntar nada, para
    que un asistente de IA o un script pueda encadenarlas:
    diagnostico, locales, bim, corpus, clientes, todo.

.PARAMETER Cliente
    Que asistentes configurar con -Accion clientes|todo:
    claude-desktop, claude-code, codex, cursor, vscode. Vacio = los detectados.

.PARAMETER Json
    Imprime el resultado como JSON y suprime el texto decorativo.

.EXAMPLE
    .\instalar-cdcrd.ps1
.EXAMPLE
    .\instalar-cdcrd.ps1 -Accion diagnostico -Json
.EXAMPLE
    .\instalar-cdcrd.ps1 -Accion todo -Cliente claude-desktop,codex
#>
[CmdletBinding()]
param(
    [ValidateSet('menu', 'diagnostico', 'locales', 'bim', 'corpus', 'clientes', 'todo')]
    [string]$Accion = 'menu',
    [string[]]$Cliente,
    [switch]$Json,
    [switch]$SinColor
)

$ErrorActionPreference = 'Stop'
$script:Raiz = $PSScriptRoot
$script:ClientesValidos = @('claude-desktop', 'claude-code', 'codex', 'cursor', 'vscode')
if ($Cliente) {
    $Cliente = @($Cliente -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    $malos = @($Cliente | Where-Object { $script:ClientesValidos -notcontains $_ })
    if ($malos) { throw "Cliente no reconocido: $($malos -join ', '). Validos: $($script:ClientesValidos -join ', ')" }
}
$script:Color = -not $SinColor -and -not $Json

# ---------------------------------------------------------------- presentacion

function Write-Linea {
    param([string]$Texto, [string]$Color = 'Gray')
    if ($script:Json) { return }
    if ($script:Color) { Write-Host $Texto -ForegroundColor $Color } else { Write-Host $Texto }
}

function Show-Banner {
    if ($script:Json) { return }
    Clear-Host
    $arte = @(
        '   ####  ####   ####  ####   ####  ',
        '  ##     ##  ## ##     ##  ## ##  ##',
        '  ##     ##  ## ##     ####   ##  ##',
        '  ##     ##  ## ##     ##  ## ##  ##',
        '   ####  ####   ####  ##  ## ####  ',
        '  ----------------------------------'
    )
    foreach ($l in $arte) { Write-Linea $l 'Cyan' }
    Write-Linea '   C D C R D - D I G I T A L   |   normativa trazable + BIM' 'DarkCyan'
    Write-Linea ''
}

function Write-Titulo {
    param([string]$Texto)
    Write-Linea ''
    Write-Linea "-- $Texto" 'White'
}

function Write-Estado {
    param([string]$Etiqueta, [bool]$Ok, [string]$Detalle = '')
    $marca = if ($Ok) { '[ OK ]' } else { '[ -- ]' }
    $color = if ($Ok) { 'Green' } else { 'DarkYellow' }
    $texto = '{0} {1}' -f $marca, $Etiqueta.PadRight(40)
    if ($Detalle) { $texto += $Detalle }
    Write-Linea $texto $color
}

# ---------------------------------------------------------------- utilidades

function Get-PythonReal {
    # El interprete real, no el shim del launcher: el cliente MCP no hereda PATH.
    foreach ($cmd in @('py', 'python')) {
        $exe = Get-Command $cmd -ErrorAction SilentlyContinue
        if (-not $exe) { continue }
        try {
            $ruta = & $exe.Source -c "import sys;print(sys.executable)" 2>$null
            $bits = & $exe.Source -c "import struct;print(struct.calcsize('P')*8)" 2>$null
            if ($ruta -and (Test-Path -LiteralPath $ruta)) {
                return [pscustomobject]@{ Ruta = $ruta.Trim(); Bits = [int]$bits }
            }
        } catch { }
    }
    return $null
}

function Find-Programa {
    param([string]$Patron)
    $bases = @("$env:ProgramFiles", "${env:ProgramFiles(x86)}")
    foreach ($b in $bases) {
        if (-not $b -or -not (Test-Path -LiteralPath $b)) { continue }
        $hit = Get-ChildItem -LiteralPath $b -Directory -Recurse -Depth 1 -ErrorAction SilentlyContinue |
               Where-Object { $_.FullName -like $Patron } |
               Sort-Object FullName -Descending | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

function Get-RutasClienteIA {
    $claudeClasico = if ($env:APPDATA) { Join-Path $env:APPDATA 'Claude\claude_desktop_config.json' } else { 'claude_desktop_config.json' }
    $paquetes = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA 'Packages' } else { $null }
    $claudeMsix = $(if ($paquetes -and (Test-Path -LiteralPath $paquetes)) { Get-ChildItem -LiteralPath $paquetes -Directory -Filter 'Claude*' -ErrorAction SilentlyContinue }) |
                  ForEach-Object { Join-Path $_.FullName 'LocalCache\Roaming\Claude\claude_desktop_config.json' } |
                  Where-Object { Test-Path -LiteralPath (Split-Path $_ -Parent) } | Select-Object -First 1
    [pscustomobject]@{
        'claude-desktop' = if ($claudeMsix) { $claudeMsix } else { $claudeClasico }
        'claude-code'    = Join-Path $script:Raiz '.mcp.json'
        'codex'          = Join-Path $HOME '.codex\config.toml'
        'cursor'         = Join-Path $HOME '.cursor\mcp.json'
        'vscode'         = if ($env:APPDATA) { Join-Path $env:APPDATA 'Code\User\mcp.json' } else { Join-Path $HOME '.config/Code/User/mcp.json' }
    }
}

function ConvertTo-HashtableCompat {
    # ConvertFrom-Json -AsHashtable no existe en Windows PowerShell 5.1.
    param($Objeto)
    if ($null -eq $Objeto) { return $null }
    if ($Objeto -is [System.Collections.IDictionary]) {
        $h = @{}
        foreach ($k in $Objeto.Keys) { $h[$k] = ConvertTo-HashtableCompat $Objeto[$k] }
        return $h
    }
    if ($Objeto -is [System.Management.Automation.PSCustomObject]) {
        $h = @{}
        foreach ($p in $Objeto.PSObject.Properties) { $h[$p.Name] = ConvertTo-HashtableCompat $p.Value }
        return $h
    }
    if ($Objeto -is [System.Array]) {
        $lista = New-Object System.Collections.ArrayList
        foreach ($i in $Objeto) { [void]$lista.Add((ConvertTo-HashtableCompat $i)) }
        return , $lista.ToArray()
    }
    return $Objeto
}

function Save-Texto {
    # Escribe UTF-8 SIN BOM: Set-Content en PowerShell 5.1 mete BOM y rompe JSON/py.
    param([string]$Ruta, [string]$Texto)
    $dir = Split-Path -Parent $Ruta
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    if (Test-Path -LiteralPath $Ruta) {
        Copy-Item -LiteralPath $Ruta -Destination "$Ruta.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
    }
    [System.IO.File]::WriteAllText($Ruta, $Texto, (New-Object System.Text.UTF8Encoding($false)))
}

# ---------------------------------------------------------------- diagnostico

function Get-Diagnostico {
    $py = Get-PythonReal
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    $git = Get-Command git -ErrorAction SilentlyContinue
    $venv = Join-Path $script:Raiz 'herramientas-locales\.venv\Scripts\python.exe'
    $rutas = Get-RutasClienteIA

    $clientes = @{}
    foreach ($n in 'claude-desktop', 'claude-code', 'codex', 'cursor', 'vscode') {
        $r = $rutas.$n
        $clientes[$n] = [pscustomobject]@{
            Ruta      = $r
            Instalado = (Test-Path -LiteralPath $r) -or (Test-Path -LiteralPath (Split-Path $r -Parent))
        }
    }

    [pscustomobject]@{
        Repo       = $script:Raiz
        Windows    = [string][System.Environment]::OSVersion.Version
        PowerShell = [string]$PSVersionTable.PSVersion
        Python     = $py
        Uv         = if ($uv) { $uv.Source } else { $null }
        Git        = if ($git) { $git.Source } else { $null }
        Locales    = [pscustomobject]@{
            Instalado = Test-Path -LiteralPath $venv
            Python    = $venv
        }
        Programas  = [pscustomobject]@{
            ETABS    = Find-Programa '*Computers and Structures\ETABS*'
            SAFE     = Find-Programa '*Computers and Structures\SAFE*'
            Revit    = Find-Programa '*Autodesk\Revit*'
            Civil3D  = Find-Programa '*Autodesk\AutoCAD*'
        }
        Clientes   = [pscustomobject]$clientes
        Corpus     = [pscustomobject]@{
            Indice    = Test-Path -LiteralPath (Join-Path $script:Raiz 'datos\INDICE.md')
            Maquina   = Test-Path -LiteralPath (Join-Path $script:Raiz 'datos\machine')
            Reglamentos = Test-Path -LiteralPath (Join-Path $script:Raiz 'corpus-reglamentos')
        }
    }
}

function Show-Diagnostico {
    param($D)
    Write-Titulo 'Que hay en este equipo'
    Write-Estado 'Windows / PowerShell' $true "$($D.Windows)  |  PS $($D.PowerShell)"
    Write-Estado 'Python 64 bits' ($null -ne $D.Python -and $D.Python.Bits -eq 64) $(if ($D.Python) { "$($D.Python.Bits) bits  |  $($D.Python.Ruta)" } else { 'no encontrado: instalar desde python.org' })
    Write-Estado 'uv (gestor del entorno local)' ($null -ne $D.Uv) $(if ($D.Uv) { $D.Uv } else { 'falta: https://docs.astral.sh/uv/' })
    Write-Estado 'git' ($null -ne $D.Git) $D.Git
    Write-Estado 'Herramientas locales instaladas' $D.Locales.Instalado $(if ($D.Locales.Instalado) { $D.Locales.Python } else { 'opcion 2 del menu' })

    Write-Titulo 'Programas de calculo y BIM'
    foreach ($p in 'ETABS', 'SAFE', 'Revit', 'Civil3D') {
        $v = $D.Programas.$p
        Write-Estado $p ($null -ne $v) $(if ($v) { $v } else { 'no instalado en este equipo' })
    }

    Write-Titulo 'Asistentes de IA detectados'
    foreach ($n in 'claude-desktop', 'claude-code', 'codex', 'cursor', 'vscode') {
        $c = $D.Clientes.$n
        Write-Estado $n $c.Instalado $c.Ruta
    }

    Write-Titulo 'Corpus normativo en el repositorio'
    Write-Estado 'Indice de los 5 volumenes' $D.Corpus.Indice 'datos\INDICE.md'
    Write-Estado 'Tablas listas para calculo' $D.Corpus.Maquina 'datos\machine\'
    Write-Estado 'Reglamentos complementarios' $D.Corpus.Reglamentos 'corpus-reglamentos\'
    Write-Linea ''
}

# ---------------------------------------------------------------- instalacion

function Install-Locales {
    $script = Join-Path $script:Raiz 'herramientas-locales\instalar.ps1'
    if (-not (Test-Path -LiteralPath $script)) { throw "No existe $script" }
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Linea 'Falta uv. Instalelo con este comando y vuelva a entrar:' 'Yellow'
        Write-Linea '  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"' 'Yellow'
        return [pscustomobject]@{ ok = $false; motivo = 'falta uv' }
    }
    Write-Linea 'Creando el entorno bloqueado y corriendo las pruebas...' 'Cyan'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $script -Pruebas
    $ok = $LASTEXITCODE -eq 0
    Write-Estado 'Herramientas locales' $ok
    return [pscustomobject]@{ ok = $ok }
}

function Get-ServidoresMcp {
    param($D)
    $servidores = [ordered]@{}

    if ($D.Locales.Instalado) {
        $servidores['cdcrd-local'] = [pscustomobject]@{
            command = $D.Locales.Python
            args    = @('-m', 'cdcrd_local.server')
            env     = @{ CDCRD_REPO_ROOT = $script:Raiz; PYTHONUTF8 = '1' }
            motivo  = 'CLI y 10 herramientas locales (normativa, DXF, IFC, PDF)'
        }
    }
    if ($D.Python) {
        $mapa = @(
            @{ nombre = 'fea';     ruta = 'servidor-mcp\src\server.py';          requiere = 'ETABS' },
            @{ nombre = 'safe';    ruta = 'servidor-mcp-safe\src\server.py';     requiere = 'SAFE' },
            @{ nombre = 'civil3d'; ruta = 'servidor-mcp-civil3d\src\server.py';  requiere = 'Civil3D' },
            @{ nombre = 'revit';   ruta = 'revit-mcp-tools\src\server.py';       requiere = 'Revit' }
        )
        foreach ($m in $mapa) {
            $full = Join-Path $script:Raiz $m.ruta
            if (-not (Test-Path -LiteralPath $full)) { continue }
            if (-not $D.Programas.($m.requiere)) { continue }
            $servidores[$m.nombre] = [pscustomobject]@{
                command = $D.Python.Ruta
                args    = @($full)
                env     = @{ PYTHONUTF8 = '1' }
                motivo  = "$($m.requiere) detectado en este equipo"
            }
        }
    }
    return $servidores
}

function Install-DependenciasBim {
    param($D, $Servidores)
    if (-not $D.Python) { return }
    $reqs = @{
        'fea'     = 'servidor-mcp\requirements.txt'
        'safe'    = 'servidor-mcp-safe\requirements.txt'
        'civil3d' = 'servidor-mcp-civil3d\requirements.txt'
    }
    foreach ($n in $Servidores.Keys) {
        if (-not $reqs.ContainsKey($n)) { continue }
        $r = Join-Path $script:Raiz $reqs[$n]
        if (-not (Test-Path -LiteralPath $r)) { continue }
        Write-Linea "Instalando dependencias de $n ..." 'Cyan'
        & $D.Python.Ruta -m pip install -r $r --quiet
        Write-Estado "dependencias $n" ($LASTEXITCODE -eq 0)
    }
    # El fallo numero uno de la instalacion original: SDK mcp 2.x sin fastmcp.
    & $D.Python.Ruta -c "from mcp.server.fastmcp import FastMCP" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Linea 'El paquete mcp instalado no trae fastmcp (SDK 2.x). Corrigiendo a 1.x...' 'Yellow'
        & $D.Python.Ruta -m pip install "mcp>=1.10,<2" --force-reinstall --quiet
    }
}

# ---------------------------------------------------------------- clientes IA

function Merge-JsonMcp {
    param([string]$Ruta, [hashtable]$Entradas, [string]$Clave = 'mcpServers')
    $raiz = @{}
    if (Test-Path -LiteralPath $Ruta) {
        $texto = Get-Content -LiteralPath $Ruta -Raw -Encoding UTF8
        if ($texto.Trim()) {
            try { $raiz = ConvertTo-HashtableCompat ($texto | ConvertFrom-Json) } catch { throw "El archivo $Ruta no es JSON valido; no se toco." }
        }
    }
    if (-not $raiz.ContainsKey($Clave)) { $raiz[$Clave] = @{} }
    foreach ($n in $Entradas.Keys) { $raiz[$Clave][$n] = $Entradas[$n] }   # no borra entradas ajenas
    Save-Texto -Ruta $Ruta -Texto ($raiz | ConvertTo-Json -Depth 10)
    $releido = (ConvertTo-HashtableCompat (Get-Content -LiteralPath $Ruta -Raw -Encoding UTF8 | ConvertFrom-Json))[$Clave].Keys
    return @($releido)
}

function Merge-TomlMcp {
    param([string]$Ruta, [hashtable]$Entradas)
    $texto = if (Test-Path -LiteralPath $Ruta) { Get-Content -LiteralPath $Ruta -Raw -Encoding UTF8 } else { '' }
    $anadidos = @()
    foreach ($n in $Entradas.Keys) {
        if ($texto -match "(?m)^\s*\[mcp_servers\.$([regex]::Escape($n))\]") { continue }
        $e = $Entradas[$n]
        $argsTexto = ($e.args | ForEach-Object { '"' + ($_ -replace '\\', '\\') + '"' }) -join ', '
        $bloque = @"

[mcp_servers.$n]
command = "$($e.command -replace '\\','\\')"
args = [$argsTexto]
"@
        $texto += $bloque
        $anadidos += $n
    }
    if ($anadidos.Count) { Save-Texto -Ruta $Ruta -Texto $texto }
    return $anadidos
}

function Set-ClientesIA {
    param($D, $Servidores, [string[]]$Objetivo)
    $rutas = Get-RutasClienteIA
    $limpias = @{}
    foreach ($n in $Servidores.Keys) {
        $s = $Servidores[$n]
        $limpias[$n] = @{ command = $s.command; args = $s.args; env = $s.env }
    }
    if (-not $limpias.Count) {
        Write-Linea 'No hay servidores que conectar todavia: instale primero las herramientas locales (opcion 2).' 'Yellow'
        return @()
    }

    $resultado = @()
    foreach ($n in 'claude-desktop', 'claude-code', 'codex', 'cursor', 'vscode') {
        if ($Objetivo -and $Objetivo -notcontains $n) { continue }
        $ruta = $rutas.$n
        $existe = (Test-Path -LiteralPath $ruta) -or (Test-Path -LiteralPath (Split-Path $ruta -Parent))
        if (-not $Objetivo -and -not $existe) { continue }
        try {
            switch ($n) {
                'codex'  { $hechos = Merge-TomlMcp -Ruta $ruta -Entradas $limpias }
                'vscode' { $hechos = Merge-JsonMcp -Ruta $ruta -Entradas $limpias -Clave 'servers' }
                default  { $hechos = Merge-JsonMcp -Ruta $ruta -Entradas $limpias }
            }
            Write-Estado "configurado $n" $true ($hechos -join ', ')
            $resultado += [pscustomobject]@{ cliente = $n; ruta = $ruta; servidores = $hechos }
        } catch {
            Write-Estado "configurado $n" $false $_.Exception.Message
        }
    }
    Write-Linea ''
    Write-Linea 'Cierre el asistente desde el icono de la bandeja (no solo la ventana) y vuelvalo a abrir.' 'Cyan'
    return $resultado
}

# ---------------------------------------------------------------- corpus

function Test-Corpus {
    param($D)
    Write-Titulo 'Corpus normativo'
    $indice = Join-Path $script:Raiz 'datos\INDICE.md'
    Write-Estado 'Indice de volumenes' (Test-Path -LiteralPath $indice) $indice
    $maquina = Get-ChildItem -LiteralPath (Join-Path $script:Raiz 'datos\machine') -Filter *.json -ErrorAction SilentlyContinue
    Write-Estado 'Tablas para calculo' ($null -ne $maquina) "$(@($maquina).Count) archivos .json"
    if ($D.Locales.Instalado) {
        Write-Linea 'Probando una consulta real al corpus...' 'Cyan'
        & (Join-Path $script:Raiz 'herramientas-locales\cdcrd.ps1') buscar 'carga viva' --limite 3
        Write-Estado 'Consulta de prueba' ($LASTEXITCODE -eq 0)
    } else {
        Write-Linea 'Para consultar el corpus desde la consola, instale antes las herramientas locales (opcion 2).' 'Yellow'
    }
}

# ---------------------------------------------------------------- faq

function Show-Faq {
    Write-Titulo 'Preguntas frecuentes'
    $faq = @(
        @('No se que es MCP',
          'Es el canal por el que su asistente de IA usa programas de su equipo. Si el asistente aparece conectado, ya funciona.'),
        @('El asistente no ve las herramientas',
          'Cierrelo desde el icono de la bandeja del sistema (clic derecho > Quit) y reabralo. Cerrar la ventana no reinicia el proceso.'),
        @('Dice que falta Python',
          'Instale Python 64 bits desde python.org y desactive los alias de la Microsoft Store en Configuracion > Aplicaciones > Alias de ejecucion.'),
        @('ETABS/SAFE abiertos pero el servidor no conecta',
          'El programa y el asistente deben correr con el mismo nivel de privilegio: los dos como administrador, o ninguno.'),
        @('Puedo usar esto sin tener Revit o ETABS',
          'Si. Las herramientas locales y el corpus normativo funcionan solos; los servidores BIM solo aparecen si el programa esta instalado.'),
        @('Donde quedan mis archivos',
          'Nada sale de su equipo: el instalador solo escribe en el repositorio y en la configuracion de su asistente, con respaldo previo.')
    )
    foreach ($f in $faq) {
        Write-Linea ''
        Write-Linea ("  " + $f[0]) 'White'
        Write-Linea ("  " + $f[1]) 'Gray'
    }
    Write-Linea ''
}

# ---------------------------------------------------------------- acciones

function Invoke-Todo {
    param([string[]]$Objetivo)
    $d = Get-Diagnostico
    Show-Diagnostico $d
    Install-Locales | Out-Null
    $d = Get-Diagnostico
    $srv = Get-ServidoresMcp $d
    Install-DependenciasBim -D $d -Servidores $srv
    Test-Corpus $d
    return Set-ClientesIA -D $d -Servidores $srv -Objetivo $Objetivo
}

function Show-Menu {
    while ($true) {
        Show-Banner
        Write-Linea '  1  Ver que hay en este equipo (diagnostico)' 'White'
        Write-Linea '  2  Instalar las herramientas locales' 'White'
        Write-Linea '  3  Conectar ETABS, SAFE, Revit y Civil 3D' 'White'
        Write-Linea '  4  Comprobar el corpus normativo' 'White'
        Write-Linea '  5  Configurar mi asistente de IA' 'White'
        Write-Linea '  6  Instalarlo todo de una vez' 'White'
        Write-Linea '  7  Preguntas frecuentes' 'White'
        Write-Linea '  0  Salir' 'White'
        Write-Linea ''
        $op = Read-Host '  Elija una opcion'
        switch ($op) {
            '1' { Show-Diagnostico (Get-Diagnostico) }
            '2' { Install-Locales | Out-Null }
            '3' {
                $d = Get-Diagnostico
                $srv = Get-ServidoresMcp $d
                if (-not $srv.Count) { Write-Linea 'No se detecto ningun programa BIM en este equipo.' 'Yellow' }
                else {
                    Install-DependenciasBim -D $d -Servidores $srv
                    foreach ($n in $srv.Keys) { Write-Estado "servidor $n" $true $srv[$n].motivo }
                    Write-Linea 'Use la opcion 5 para escribirlos en su asistente.' 'Cyan'
                }
            }
            '4' { Test-Corpus (Get-Diagnostico) }
            '5' {
                $d = Get-Diagnostico
                Set-ClientesIA -D $d -Servidores (Get-ServidoresMcp $d) -Objetivo $Cliente | Out-Null
            }
            '6' { Invoke-Todo -Objetivo $Cliente | Out-Null }
            '7' { Show-Faq }
            '0' { return }
            default { Write-Linea '  Opcion no reconocida.' 'Yellow' }
        }
        Write-Linea ''
        Read-Host '  Enter para volver al menu' | Out-Null
    }
}

# ---------------------------------------------------------------- entrada

$salida = switch ($Accion) {
    'menu'        { Show-Banner; Show-Menu; $null }
    'diagnostico' { $d = Get-Diagnostico; if (-not $Json) { Show-Banner; Show-Diagnostico $d }; $d }
    'locales'     { Install-Locales }
    'bim'         { $d = Get-Diagnostico; $srv = Get-ServidoresMcp $d; Install-DependenciasBim -D $d -Servidores $srv; $srv }
    'corpus'      { $d = Get-Diagnostico; Test-Corpus $d; $d.Corpus }
    'clientes'    { $d = Get-Diagnostico; Set-ClientesIA -D $d -Servidores (Get-ServidoresMcp $d) -Objetivo $Cliente }
    'todo'        { Invoke-Todo -Objetivo $Cliente }
}

if ($Json) { $salida | ConvertTo-Json -Depth 10 }
