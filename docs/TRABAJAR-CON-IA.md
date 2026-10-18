# Probar las herramientas con Claude o Codex

El ingeniero define el caso y revisa la evidencia. Claude y Codex pueden ayudar a
preparar entradas, ejecutar herramientas disponibles y explicar los resultados.
No necesitan aprender un lenguaje de programación para comenzar con un ejemplo,
pero sí confirmar unidades, geometría, aplicación y archivo de trabajo.

## Recorrido inicial

1. Abra el ejemplo ficticio del módulo y sus requisitos. Use una copia del dibujo.
2. Pida a su asistente que lea el README y muestre qué va a crear, con unidades,
   cantidades y restricciones. El mismo texto puede usarse con Claude o Codex.
3. Ejecute una operación a la vez. Una conexión disponible o un comando enviado
   no demuestran que Civil 3D terminó: compruebe el recibo, relea los objetos y guarde.
4. Cierre y reabra únicamente la copia, compare los datos y revise la vista exportada.
5. Si hay un error o falta el recibo, inspeccione antes de repetir. Survey y algunas
   API COM pueden haber dejado resultados parciales.

## Prompt reproducible

> Lee `civil3d-points-survey/README.md`. Prepara el ejemplo de 12 puntos ficticios
> en una copia vacía de Civil 3D, en metros. Enséñame los conteos y el archivo destino.
> Importa, exporta y compara los puntos; crea el grupo TN; verifica una base Survey
> separada sin inventar observaciones. Guarda y reabre la copia. Documenta qué pasó
> realmente, los recibos y lo pendiente. No modifiques los archivos normativos.

Los conectores dependen de la instalación y permisos de cada asistente. El módulo
COGO/Survey también se ejecuta manualmente desde Civil 3D sin un servicio de IA.
El prompt no acredita una prueba con ambos clientes: cada ejecución debe registrar
cliente, versión de Civil 3D y evidencias. Esta etapa se ejecutó con OpenAI Codex.

## Créditos

Proyecto y dirección: Emil / `dashy2004`. Desarrollo asistido y documentación:
**OpenAI Codex y Anthropic Claude**, conforme al historial de cada contribución.
La asistencia no representa cuentas humanas, permisos de colaborador concedidos
ni certificación del diseño. Las nuevas herramientas de esta entrega fueron
implementadas y probadas con Codex; Claude puede reproducir el mismo procedimiento.
