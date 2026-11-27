"""Dispara Design > Shear Wall Design > Start Design/Check en una instancia propia de ETABS.

La API de ETABS 23 (ETABSv1) no tiene StartDesign para muros: `cDesignShearWall` solo lee
resultados. Este módulo pulsa el menú por UI Automation de Windows, sobre la ventana del proceso
que abrió `fuentes_etabs.leer_tablas` (siempre una copia del modelo), y espera a que ETABS cierre
su ventana «Cancel Wall Design/Check».

Requisitos: sesión de escritorio interactiva y la ventana de ETABS visible. Ensayado con ETABS
23.3.0 en los tres bloques de Riviera Costeña Costa (2026-11-24).
"""
from __future__ import annotations

import csv
import io
import subprocess
import threading
import time
from typing import Any

RUTA_MENU = ("Design", "Shear Wall Design", "Start Design/Check")
VENTANA_PROGRESO = "Cancel Wall Design/Check"
ESPERA_MENU = 15.0          # s para que aparezca cada submenú
ESPERA_DISENO = 1200.0      # s como máximo para el diseño completo
PAUSA = 0.5
MARGEN_PROGRESO = 10.0      # s de espera a la ventana de progreso antes de darla por cerrada
INTENTOS_MENU = 3           # el árbol de UIA de ETABS a veces no está listo en el primer intento
SONDEOS_QUIETOS = 6        # sondeos seguidos sin ventana de progreso (3 s) para darlo por terminado


class ErrorDeMuros(Exception):
    """No se pudo disparar o completar el diseño de muros."""


def pids_etabs() -> set[int]:
    """PID de los procesos ETABS.exe en marcha."""
    r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ETABS.exe", "/FO", "CSV", "/NH"],
                       capture_output=True, text=True, check=False)
    pids = set()
    for fila in csv.reader(io.StringIO(r.stdout)):
        if len(fila) > 1 and fila[0].lower() == "etabs.exe" and fila[1].isdigit():
            pids.add(int(fila[1]))
    return pids


def _ventanas(pid: int) -> list[tuple[int, str, str]]:
    import win32gui
    import win32process

    out: list[tuple[int, str, str]] = []

    def cb(h: int, _: Any) -> None:
        if win32gui.IsWindowVisible(h) and win32process.GetWindowThreadProcessId(h)[1] == pid:
            out.append((h, win32gui.GetWindowText(h), win32gui.GetClassName(h)))
    win32gui.EnumWindows(cb, None)
    return out


def _uia() -> Any:
    import comtypes.client

    comtypes.client.GetModule("UIAutomationCore.dll")
    from comtypes.gen import UIAutomationClient as U

    return U, comtypes.client.CreateObject(U.CUIAutomation, interface=U.IUIAutomation)


def _items_de_menu(U: Any, uia: Any, pid: int) -> list[Any]:
    cond = uia.CreateAndCondition(uia.CreatePropertyCondition(U.UIA_ProcessIdPropertyId, pid),
                                  uia.CreatePropertyCondition(U.UIA_ControlTypePropertyId, U.UIA_MenuItemControlTypeId))
    arr = uia.GetRootElement().FindAll(U.TreeScope_Descendants, cond)
    return [arr.GetElement(i) for i in range(arr.Length)]


def _buscar(U: Any, uia: Any, pid: int, nombre: str) -> Any:
    fin = time.time() + ESPERA_MENU
    vistos: list[str] = []
    while time.time() < fin:
        try:
            elementos = _items_de_menu(U, uia, pid)
            vistos = [e.CurrentName for e in elementos]
            for e, n in zip(elementos, vistos):
                if n.replace("&", "").startswith(nombre):
                    return e
        except Exception:  # noqa: BLE001 - el árbol cambia mientras se recorre; se vuelve a intentar
            pass
        time.sleep(PAUSA)
    ventanas = [t or c for _, t, c in _ventanas(pid)]
    raise ErrorDeMuros("no apareció el menú «%s» (menús visibles: %s; ventanas: %s)"
                       % (nombre, ", ".join(vistos[:20]) or "ninguno", ", ".join(ventanas[:8]) or "ninguna"))


def _recorrer_menu(U: Any, uia: Any, pid: int) -> None:
    for i, nombre in enumerate(RUTA_MENU):
        e = _buscar(U, uia, pid, nombre)
        final = i == len(RUTA_MENU) - 1
        patron = None if final else e.GetCurrentPattern(U.UIA_ExpandCollapsePatternId)
        if patron:
            patron.QueryInterface(U.IUIAutomationExpandCollapsePattern).Expand()
        else:
            e.GetCurrentPattern(U.UIA_InvokePatternId).QueryInterface(U.IUIAutomationInvokePattern).Invoke()


def _pulsar_menu(pid: int, resultado: dict[str, Any]) -> None:
    """Se ejecuta en un hilo propio: Invoke puede no volver hasta que ETABS termina."""
    import comtypes

    comtypes.CoInitialize()
    try:
        U, uia = _uia()
        errores = []
        for _ in range(INTENTOS_MENU):
            try:
                _recorrer_menu(U, uia, pid)
                resultado["pulsado"] = True
                return
            except Exception as ex:  # noqa: BLE001 - se reintenta y al final se informa
                errores.append(str(ex) or repr(ex))
                _cerrar_menus(pid)
                time.sleep(2)
        resultado["error"] = "; ".join(dict.fromkeys(errores))
    except Exception as ex:  # noqa: BLE001 - el error se informa al hilo principal
        resultado["error"] = str(ex) or repr(ex)
    finally:
        comtypes.CoUninitialize()


def _cerrar_menus(pid: int) -> None:
    """Escape a la ventana principal: deja el menú cerrado antes de reintentar."""
    import win32con
    import win32gui

    for h, titulo, _ in _ventanas(pid):
        if titulo.startswith("ETABS"):
            for _ in range(3):
                win32gui.PostMessage(h, win32con.WM_KEYDOWN, win32con.VK_ESCAPE, 0)
                win32gui.PostMessage(h, win32con.WM_KEYUP, win32con.VK_ESCAPE, 0)


def _cerrar_dialogos(pid: int, vistos: list[str], atendidos: set[int]) -> None:
    """Acepta los cuadros de aviso que ETABS abra durante el diseño y guarda su texto una vez."""
    import win32con
    import win32gui

    for h, titulo, clase in _ventanas(pid):
        if clase != "#32770" or titulo == VENTANA_PROGRESO:
            continue
        if h not in atendidos:
            atendidos.add(h)
            textos: list[str] = []
            win32gui.EnumChildWindows(h, lambda c, _: textos.append(win32gui.GetWindowText(c)), None)
            texto = " ".join(x for x in [titulo] + textos if x).strip()
            if texto not in vistos:
                vistos.append(texto)
        win32gui.PostMessage(h, win32con.WM_COMMAND, win32con.IDOK, 0)


def disenar_muros(pid: int) -> list[str]:
    """Pulsa Start Design/Check y espera a que termine. Devuelve el texto de los avisos aceptados."""
    resultado: dict[str, Any] = {}
    hilo = threading.Thread(target=_pulsar_menu, args=(pid, resultado), daemon=True)
    hilo.start()
    avisos: list[str] = []
    atendidos: set[int] = set()
    fin = time.time() + ESPERA_DISENO
    vio_progreso, pulsado_en, quietos = False, None, 0
    while time.time() < fin:
        _cerrar_dialogos(pid, avisos, atendidos)
        progreso = any(t == VENTANA_PROGRESO for _, t, _ in _ventanas(pid))
        vio_progreso = vio_progreso or progreso
        quietos = 0 if progreso else quietos + 1
        if "error" in resultado:
            raise ErrorDeMuros(resultado["error"])
        if resultado.get("pulsado") and pulsado_en is None:
            pulsado_en = time.time()
        # la ventana de progreso tarda en aparecer y puede reabrirse entre fases: se exigen varios
        # sondeos seguidos sin ella. Quien llama confirma además que la tabla de resumen tiene filas.
        listo = vio_progreso or (pulsado_en is not None and time.time() - pulsado_en > MARGEN_PROGRESO)
        if not hilo.is_alive() and pulsado_en is not None and quietos >= SONDEOS_QUIETOS and listo:
            return avisos
        time.sleep(PAUSA)
    raise ErrorDeMuros("el diseño de muros no terminó en %d s" % ESPERA_DISENO
                       + ("" if vio_progreso else " (no apareció la ventana de progreso)"))
