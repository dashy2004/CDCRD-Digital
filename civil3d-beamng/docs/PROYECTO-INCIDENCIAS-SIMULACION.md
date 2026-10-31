# IncidenciasRD: de un reporte a una escena comprobable

Fecha: 2026-10-31. Proyecto en desarrollo.

El objetivo es documentar una incidencia, representar su geometría y comparar
recorridos en un entorno controlado. La escena permitirá comunicar el problema
y formular preguntas de ingeniería. Un resultado simulado deberá conservar sus
supuestos y contrastarse antes de aplicarlo a una carretera real.

## Avance y siguiente entrega

| Etapa | Disponible | Trabajo siguiente |
|---|---|---|
| Formación vial | Curso de Civil 3D con referencias al R-012 y tutorial de exportación a Drive | Enlazar el procedimiento con los casos de incidencias |
| Calle sintética | Eje, rasante, corredor, relieve, bache y bloques 3D; ejemplo por API | Validar las nuevas herramientas nativas y la importación de esta revisión |
| Herramientas Tech | BeamNGpy 1.36 instalado en entorno separado; compatible con Tech 0.39 | Activar y comprobar la instalación del motor y el escenario |
| Grabación | OBS 33 y WebSocket 5.7.6; consulta autenticada comprobada | Componer cámaras, pasada repetible y grabación autorizada |
| Estructura didáctica | Cuatro vigas de 20 m analizadas en ETABS 23.3.0, con equilibrio y flecha comprobados | Incorporar una representación visual del tablero y ampliar el modelo |
| Puentes especializados | Hoja de ruta | SAP2000/CSiBridge, cargas móviles y validación del intercambio |

## Qué mostrará el anuncio

1. Una incidencia registrada con su ubicación y evidencia.
2. Una escena de demostración con geometría y parámetros explícitos.
3. Recorridos comparables, cámaras y observaciones sobre el vehículo.
4. Una vista del modelo estructural didáctico y la ampliación prevista.

En esta primera entrega, el paso del reporte a la escena es preparado y revisado;
no se anuncia una reconstrucción automática desde cualquier fotografía. Las
estructuras visuales de BeamNG y el modelo ETABS tienen responsabilidades distintas.
El acoplamiento de cargas/deformaciones entre ellos todavía no está implementado.

## Datos que deberán acompañar cada experimento

- Fuente de la geometría y separación entre observación real y ejemplo sintético.
- Unidades, origen común, transformación de coordenadas y revisión del modelo.
- Vehículo, velocidad inicial, trayectoria, geometría del bache y estado del pavimento.
- Versión del simulador/SDK, parámetros de cámara y sensores realmente utilizados.
- Resultados medidos, comprobaciones, limitaciones y archivos para repetir la corrida.

La primera comparación puede usar la misma calle antes y después de reparar el
bache, manteniendo vehículo y recorrido. Velocidad y condiciones deberán quedar
registradas. No asignar una calificación de seguridad ni un diagnóstico estructural
a partir de una toma publicitaria.

## Fuentes e implementaciones

[Referencias originales y licencias](REFERENCIAS-BEAMNG.md),
[entorno Tech](../tools/tech/README.md),
[calle por API](../examples/calle_demo/README.md),
[modelo ETABS didáctico](../examples/puente_didactico/README.md).

La correspondencia de licencia, la clave personal y enlaces privados se conservan
fuera del material público. El uso promocional y la distribución de datos se
consultan con BeamNG: [acuerdo sobre datos](https://beamng.tech/policies/database-licensing/).

## Texto del slide propuesto

**Del reporte a la simulación**

Proyecto en desarrollo. Recrear incidencias viales y comparar recorridos en
BeamNG.tech. Puente didáctico con ETABS. Próxima ampliación: SAP2000 y CSiBridge.
Objetivo: conectar documentación, simulación y análisis estructural.

Crédito del fotograma: tutorial propio en BeamNG.drive. El fotograma ilustra
el antecedente del curso, no una ejecución de Tech ni el caso de la calle R02.
El slide y el post quedan como borradores; no se han publicado en redes.

## Enfoque editorial acordado: problema, procedimiento y resultados

Actualización del 31 de octubre de 2026: el primer carrusel abre con los videos
originales de denuncias de Cambita. La demostración debe enseñar cómo el código
de CDCRD-Digital crea los objetos en Civil 3D y ETABS, con qué datos los crea y
qué comprobaciones devuelve. La edición final y la integración del canal de
reportes continuarán en Linux; los archivos nativos se producen en Windows.

Gancho propuesto: **«¿Qué podemos hacer con una denuncia, además de publicarla?»**
Primero se escucha el problema; luego se muestra el proceso y una respuesta
comprobable. El detalle de código puede ocupar una franja breve; el objeto que
aparece en la aplicación y el dato que devuelve deben dominar la imagen.

| Lámina | Imagen o clip | Mensaje y evidencia necesaria |
|---|---|---|
| 1. El problema | Denuncia original de Cambita, con voz y subtítulos | Fecha y lugar contrastados. Un testimonio se presenta como testimonio. |
| 2. Dar seguimiento | Ficha, mapa e historial de la incidencia | ID del caso y fecha de corte. Separar reportes, personas, duplicados y reparaciones verificadas. |
| 3. Los parámetros | Entrada del generador y vista Civil 3D | Unidades, procedencia de geometría, eje, rasante, sección y relieve. |
| 4. Lo que genera el código | Aparición de corredor, superficies y bloques 3D | Mostrar objetos nativos y consulta de resultados; indicar qué acabados son TIN muestreados. |
| 5. Experimentar | Recorrido de vehículo, cámaras y datos | La nueva corrida de la calle R02 está pendiente. El video del curso en Drive solo ilustra el antecedente. |
| 6. Análisis didáctico | Modelo ETABS y tabla de resultados | Cuatro vigas independientes: carga, apoyos, reacciones y desplazamiento. Identificar el caso estático y sus supuestos. |
| 7. Información para actuar | Extracto de solicitud y lista de documentos | Identificar la entidad responsable del tramo y pedir planos, inspecciones, mantenimiento y programación. Carta y recepción deben tener estados distintos. |
| 8. Próximo paso | Hoja de ruta y agradecimiento | Canal de reportes cuando esté comprobado; ampliación SAP2000/CSiBridge y validación del intercambio. |

## Parámetros que pueden aparecer en pantalla

Estos valores corresponden a ejemplos de demostración. No acreditan un diseño
normativo ni una reconstrucción topográfica del tramo de Cambita.

| Etapa | Entrada | Resultado comprobado | Límite que debe acompañar la toma |
|---|---|---|---|
| Civil 3D R02 | Eje curvo, dos carriles de 3.60 m y relieve sintético | Longitud de eje 215.663706 m; corredor, rasante y 61 referencias a bloques 3D | No es levantamiento de una calle real; los acabados muestreados no implican dependencia dinámica completa del corredor. |
| Bache R02 | Envolvente de referencia 2.75 × 1.79 m y contorno irregular | Profundidad central 0.0635 m respecto al pavimento sin bache | La envolvente no equivale al borde medido. No atribuir estas dimensiones a otro punto del testimonio. |
| ETABS | Cuatro vigas de 20 m; sección 0.45 × 1.00 m; 10 kN/m por viga; peso propio desactivado | Ocho elementos y apoyos; reacción vertical 100 kN por apoyo, total 800 kN | Modelo didáctico sin losa distribuidora ni cargas móviles. |
| ETABS: desplazamiento | Caso estático DEMO_STATIC; módulo E = 25 GPa | Desplazamiento central −22.350222 mm, cotejado con referencia analítica | No es comprobación de capacidad, límite de servicio o aprobación de puente. |
| BeamNG.tech | Vehículo, velocidad, ruta y escenario con revisión identificable | Pendiente de ejecutar la nueva escena | No presentar sensores, aceleraciones, impactos o reparación comparada como resultados obtenidos. |

Para cada toma técnica conservar una cadena simple: **entrada → llamada API →
objeto nativo → consulta de resultado → recibo**. La generación programática y
el análisis numérico no acreditan por sí solos cumplimiento del reglamento.
Cuando se muestre una comprobación normativa, deberá tener requisito, edición,
artículo, datos de entrada y resultado trazables. El ejemplo del puente no
incorpora todavía ese módulo de comprobación.

## Continuación de campaña en Linux

1. Reunir originales de Cambita, seleccionar testimonios y contrastar el punto
   de cada medición. Respetar las restricciones de imagen de quienes aparecen.
2. Revisar servidor, acceso y registros antes de conectar la recepción de
   incidencias. Registrar hallazgos y correcciones; disponibilidad y ausencia
   de intrusión son comprobaciones diferentes.
3. Identificar cuenta, canal y número de Bird; verificar recepción, autenticidad,
   deduplicación y creación de un registro revisable en IncidenciasRD. Una
   conexión MCP del asistente no demuestra que exista ese flujo persistente.
4. Actualizar cifras con fecha de corte y filtros, revisar destinatario y
   documentos de la carta y registrar separadamente borrador, envío y respuesta.
5. Terminar capturas nativas, simulación, voz, subtítulos y montaje. Mostrar en
   el cierre agradecimiento, canal probado y siguiente objetivo alcanzable.

La solicitud a BeamNG contempla agradecimiento, prórroga y orientación técnica.
El borrador permanece sin enviar; los requisitos de licencia para el uso
promocional y para distribuir datos se consultan con el fabricante.
