# liberar-ram.ps1 — sube la RAM disponible antes de operar Revit (E-133/E-137).
#
# Que hace (en orden, y reporta la RAM antes/despues de cada paso):
#   1. Mide la RAM libre.
#   2. Apaga la VM de WSL solo si NO hay distro corriendo (con -Wsl la apaga
#      aunque este corriendo: usar solo si la VM esta ociosa).
#   3. Vacia el working set de los procesos (EmptyWorkingSet): los obliga a
#      paginar a disco SIN cerrarlos — no se pierde nada; es lo que mas RAM
#      "Available" devuelve al instante. Excluye Revit y procesos del sistema.
#   4. Con -Cerrar: cierra con gracia (CloseMainWindow) las apps de la lista
#      -Apps; las que no respondan se reportan (con -Forzar se matan — OJO:
#      -Forzar pierde lo no guardado en esas apps).
#
# NOTA: "suspender" un proceso no libera RAM (solo congela su CPU); por eso
# este script pagina o cierra, que es lo que Revit necesita para sus picos.
#
# Uso tipico antes de una sesion pesada de Revit:
#   powershell -ExecutionPolicy Bypass -File .\liberar-ram.ps1            # seguro: pagina, no cierra nada
#   powershell -ExecutionPolicy Bypass -File .\liberar-ram.ps1 -Cerrar    # ademas cierra Chrome y compania
param(
    [switch]$Cerrar,
    [switch]$Forzar,
    [switch]$Wsl,
    [string[]]$Apps = @("chrome", "msedge", "brave", "firefox", "WhatsApp",
                        "Telegram", "Spotify", "Discord", "steam",
                        "EpicGamesLauncher", "Zoom", "ms-teams", "Teams"),
    [string[]]$NoTocar = @("Revit", "RevitWorker", "explorer", "powershell",
                           "pwsh", "Claude", "claude")
)

$ErrorActionPreference = "SilentlyContinue"

function Ram-LibreMB {
    (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024 -as [int]
}

$antes = Ram-LibreMB
Write-Host ("RAM libre al empezar: {0} MB" -f $antes)

# --- 1) WSL -----------------------------------------------------------------
$wslExe = Get-Command wsl.exe -ErrorAction SilentlyContinue
if ($wslExe) {
    # wsl.exe escribe UTF-16: limpiar los caracteres nulos antes de evaluar
    $corriendo = (& wsl.exe --list --running --quiet 2>$null) |
        ForEach-Object { ($_ -replace "`0", "").Trim() } | Where-Object { $_ }
    if (-not $corriendo) {
        & wsl.exe --shutdown 2>$null
        Write-Host "WSL: sin distros corriendo; VM apagada."
    } elseif ($Wsl) {
        & wsl.exe --shutdown 2>$null
        Write-Host ("WSL: APAGADA con distros corriendo ({0}) por -Wsl." -f ($corriendo -join ", "))
    } else {
        Write-Host ("WSL: hay distros corriendo ({0}); no se toca. Si la VM esta ociosa: -Wsl" -f ($corriendo -join ", "))
    }
}

# --- 2) vaciar working sets (paginar sin cerrar) ----------------------------
Add-Type -Namespace Win32 -Name Psapi -MemberDefinition @'
[DllImport("psapi.dll")] public static extern bool EmptyWorkingSet(System.IntPtr hProcess);
'@
$paginados = 0
foreach ($p in Get-Process) {
    if ($NoTocar | Where-Object { $p.ProcessName -like "$_*" }) { continue }
    try {
        if ($p.Handle -and [Win32.Psapi]::EmptyWorkingSet($p.Handle)) { $paginados++ }
    } catch { }
}
Write-Host ("Working set vaciado en {0} procesos (paginan a disco; nada se cierra)." -f $paginados)
Start-Sleep -Seconds 2
Write-Host ("RAM libre tras paginar: {0} MB" -f (Ram-LibreMB))

# --- 3) cerrar apps prescindibles (solo con -Cerrar) ------------------------
if ($Cerrar) {
    $objetivo = Get-Process | Where-Object { $n = $_.ProcessName; $Apps | Where-Object { $n -like "$_*" } }
    $nombres = $objetivo | Select-Object -ExpandProperty ProcessName -Unique
    if ($nombres) {
        Write-Host ("Cerrando con gracia: {0}" -f ($nombres -join ", "))
        $objetivo | ForEach-Object { $_.CloseMainWindow() | Out-Null }
        Start-Sleep -Seconds 4
        $vivos = Get-Process | Where-Object { $n = $_.ProcessName; $Apps | Where-Object { $n -like "$_*" } }
        if ($vivos) {
            $quedan = ($vivos | Select-Object -ExpandProperty ProcessName -Unique) -join ", "
            if ($Forzar) {
                $vivos | Stop-Process -Force
                Write-Host ("Matados por -Forzar: {0} (lo no guardado ahi se perdio)." -f $quedan)
            } else {
                Write-Host ("No cerraron solos: {0}. Cierralos a mano o repite con -Forzar." -f $quedan)
            }
        }
    } else {
        Write-Host "Ninguna app de la lista esta corriendo."
    }
}

Start-Sleep -Seconds 1
$despues = Ram-LibreMB
Write-Host ("RAM libre al terminar: {0} MB (gano {1} MB)" -f $despues, ($despues - $antes))
if ($despues -lt 1500) {
    Write-Host "AVISO: sigue por debajo de 1.5 GB; para MODELAR en Revit conviene cerrar mas apps (-Cerrar) o reiniciar."
}
