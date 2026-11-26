# Tekla MCP
# Captura de pantalla de la ventana principal de un programa (Tekla por defecto).
# Sirve para documentar guías y memorias: devuelve un PNG de la ventana completa
# o de una región, sin depender de scripts sueltos por proyecto.

import os
import time
from typing import Optional

REGIONES = {
    'completa': None,
    'vista': (0.13, 0.07, 0.535, 0.63),      # ventana de modelo acoplada por defecto
    'panel': (0.828, 0.12, 0.99, 0.73),      # panel de propiedades a la derecha
    'cinta': (0.0, 0.0, 0.60, 0.07),
}


def _ventana_principal(titulo_contiene: str) -> int:
    import win32gui
    encontradas = []

    def visitar(h, _):
        if win32gui.IsWindowVisible(h) and titulo_contiene.lower() in win32gui.GetWindowText(h).lower():
            izq, arr, der, aba = win32gui.GetWindowRect(h)
            encontradas.append(((der - izq) * (aba - arr), h))
    win32gui.EnumWindows(visitar, None)
    if not encontradas:
        raise RuntimeError(f"No hay ninguna ventana visible cuyo título contenga '{titulo_contiene}'.")
    return max(encontradas)[1]


def recorte_de(caja: tuple[int, int, int, int], region: str,
               fraccion: Optional[tuple[float, float, float, float]] = None) -> tuple[int, int, int, int]:
    """Convierte una región con nombre (o fracciones 0–1) en píxeles dentro de `caja`."""
    if fraccion is None:
        if region not in REGIONES:
            raise ValueError(f"Región '{region}' desconocida. Opciones: {', '.join(REGIONES)}.")
        fraccion = REGIONES[region]
    izq, arr, der, aba = caja
    if fraccion is None:
        return caja
    x0, y0, x1, y1 = fraccion
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        raise ValueError("Las fracciones deben cumplir 0 ≤ x0 < x1 ≤ 1 y 0 ≤ y0 < y1 ≤ 1.")
    ancho, alto = der - izq, aba - arr
    return (izq + round(x0 * ancho), arr + round(y0 * alto), izq + round(x1 * ancho), arr + round(y1 * alto))


def capturar(archivo: str, titulo_contiene: str = 'Tekla Structures', region: str = 'completa',
             fraccion: Optional[list[float]] = None, espera_s: float = 0.8) -> dict:
    """Trae la ventana al frente y guarda un PNG. Devuelve ruta, tamaño y caja capturada."""
    import win32con
    import win32gui
    from PIL import ImageGrab
    if not archivo.lower().endswith('.png'):
        raise ValueError("El archivo de salida debe terminar en .png.")
    h = _ventana_principal(titulo_contiene)
    if win32gui.IsIconic(h):
        win32gui.ShowWindow(h, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(h)
    except Exception:
        # Windows puede negar el foco a un proceso en segundo plano: una pulsación de Alt lo libera.
        import win32com.client
        win32com.client.Dispatch('WScript.Shell').SendKeys('%')
        win32gui.SetForegroundWindow(h)
    time.sleep(max(0.0, espera_s))
    caja = recorte_de(win32gui.GetWindowRect(h), region, tuple(fraccion) if fraccion else None)
    caja = (max(caja[0], 0), max(caja[1], 0), caja[2], caja[3])
    imagen = ImageGrab.grab(bbox=caja, all_screens=True)
    os.makedirs(os.path.dirname(os.path.abspath(archivo)), exist_ok=True)
    imagen.save(archivo)
    return {'archivo': os.path.abspath(archivo), 'ancho': imagen.width, 'alto': imagen.height, 'caja': list(caja)}


def dialogos(titulo_contiene: str = 'Tekla Structures') -> list[dict]:
    """Ventanas de diálogo visibles (clase #32770 o Afx pequeñas) con su texto y botones.

    Un diálogo modal deja a Open API esperando sin responder; esta lista dice cuál es."""
    import win32gui
    principal = _ventana_principal(titulo_contiene)
    res = []

    def visitar(h, _):
        if h == principal or not win32gui.IsWindowVisible(h):
            return
        if titulo_contiene.lower() not in win32gui.GetWindowText(h).lower():
            return
        textos, botones = [], []

        def hijo(c, _):
            clase, texto = win32gui.GetClassName(c), win32gui.GetWindowText(c)
            if clase == 'Button' and texto:
                botones.append(texto.replace('&', ''))
            elif clase == 'Static' and texto.strip():
                textos.append(texto.strip())
        win32gui.EnumChildWindows(h, hijo, None)
        if botones:
            res.append({'ventana': h, 'titulo': win32gui.GetWindowText(h), 'texto': '\n'.join(textos), 'botones': botones})
    win32gui.EnumWindows(visitar, None)
    return res


def pulsar_boton(ventana: int, boton: str) -> bool:
    """Pulsa un botón de un diálogo listado por `dialogos`. Devuelve True si el diálogo se cerró."""
    import win32con
    import win32gui
    if ventana not in [d['ventana'] for d in dialogos()]:
        raise ValueError(f"La ventana {ventana} no es un diálogo abierto de Tekla. Vuelva a listar los diálogos.")
    hijos = []
    win32gui.EnumChildWindows(ventana, lambda c, _: hijos.append(c), None)
    for c in hijos:
        if win32gui.GetClassName(c) == 'Button' and win32gui.GetWindowText(c).replace('&', '').lower() == boton.lower():
            win32gui.PostMessage(c, win32con.BM_CLICK, 0, 0)
            time.sleep(1.5)
            return not win32gui.IsWindow(ventana)
    raise ValueError(f"El diálogo no tiene un botón '{boton}'.")