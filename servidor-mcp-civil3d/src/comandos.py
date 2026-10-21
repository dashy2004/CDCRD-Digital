"""Tracked drawing commands shared by Civil 3D and the AutoCAD bridge."""
import json
import time


def registrar(mcp, llamar, ok):
    @mcp.tool()
    def ejecutar_comando_seguido(comando: str, argumentos_json: str = '[]',
                                 esperar_segundos: float = 0,
                                 confirmar: bool = False) -> str:
        """Ejecuta un comando de dibujo y devuelve un ticket de finalizacion.

        Argumentos: lista JSON de textos, numeros o puntos [x,y,z]. Incluir todos
        los argumentos, incluido "" para terminar una seleccion o una polilinea.
        Espera opcional de 0 a 30 s en el cliente, sin bloquear el hilo CAD.
        Si sigue en ejecucion, consultar el ticket; no repetir la escritura.
        Usa CommandEnded/Failed/Cancelled. No admite LISP ni cambios de documento.
        Un fin correcto del comando no certifica la geometria: releer el dibujo.
        """
        if not confirmar:
            return ok({'error': 'operacion de escritura: repita con confirmar=True'})
        try:
            args = json.loads(argumentos_json)
            if not isinstance(args, list) or not 0 <= esperar_segundos <= 30:
                raise ValueError('Se requiere lista de argumentos y espera de 0 a 30 s.')
        except (ValueError, TypeError) as exc:
            return ok({'error': str(exc)})
        result = llamar('cmd.ejecutar', {'comando': comando, 'argumentos': args}, escribe=True)
        state = json.loads(result)
        deadline = time.monotonic() + esperar_segundos
        while state.get('ticket') and not state.get('finalizado') and time.monotonic() < deadline:
            time.sleep(min(0.15, max(0, deadline - time.monotonic())))
            result = llamar('cmd.estado', {'ticket': state['ticket']})
            state = json.loads(result)
        return result

    @mcp.tool()
    def consultar_comando(ticket: str) -> str:
        """Consulta el recibo aunque Civil 3D/AutoCAD tenga un comando activo.

        Historial limitado a esta sesion. Un timeout de consulta o estado
        desconocido no permite inferir que la escritura no ocurrio.
        """
        return llamar('cmd.estado', {'ticket': ticket})
