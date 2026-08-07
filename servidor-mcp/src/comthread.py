# FEA MCP - fix
# Ejecutor COM de hilo unico (STA).
#
# Motivo: FastMCP ejecuta las herramientas sincronas en hilos worker de anyio,
# que cambian entre llamadas. Un puntero COM obtenido en un hilo no es valido
# en otro sin marshalling. Ademas cada hilo requiere su propio CoInitialize.
# La solucion correcta es confinar TODO el trabajo COM a un solo hilo que se
# inicializa una vez y nunca llama CoUninitialize mientras haya punteros vivos.

import functools
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger('fea_mcp_server')

_COM_THREAD_ID = None
_EXECUTOR = None
_LOCK = threading.Lock()


def _initializer():
    """Se ejecuta una sola vez, dentro del hilo COM dedicado."""
    global _COM_THREAD_ID
    import comtypes
    # STA: ETABS es un servidor COM out-of-process con affinity de apartment.
    comtypes.CoInitialize()
    _COM_THREAD_ID = threading.get_ident()
    logger.info("Hilo COM inicializado (STA), tid=%s", _COM_THREAD_ID)


def get_executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    with _LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="fea-com",
                initializer=_initializer,
            )
            # Forzar arranque del hilo para fijar _COM_THREAD_ID.
            _EXECUTOR.submit(lambda: None).result()
    return _EXECUTOR


def com_call(fn):
    """Decorador: enruta la ejecucion al hilo COM dedicado.

    Si ya estamos dentro del hilo COM (llamada anidada), ejecuta directo.
    Sin esta guarda, un submit() bloqueante desde el propio worker con
    max_workers=1 produce deadlock.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        ex = get_executor()
        if threading.get_ident() == _COM_THREAD_ID:
            return fn(*args, **kwargs)
        return ex.submit(fn, *args, **kwargs).result()
    return wrapper


def run_in_com(fn, *args, **kwargs):
    """Version imperativa de com_call, util desde corrutinas."""
    ex = get_executor()
    if threading.get_ident() == _COM_THREAD_ID:
        return fn(*args, **kwargs)
    return ex.submit(fn, *args, **kwargs).result()
