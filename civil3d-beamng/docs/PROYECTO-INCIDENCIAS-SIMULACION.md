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
