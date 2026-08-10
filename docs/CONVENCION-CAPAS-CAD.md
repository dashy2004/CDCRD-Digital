# Convención de capas CAD — contrato de entrada del pipeline

Fecha: 2026-08-10. Estado: propuesta, no aplicada a ningún proyecto todavía.

Este documento define el único punto donde el dibujo se vuelve dato. Todo lo
que está aguas abajo (extractor, Revit, ETABS, SAFE, planos, presupuesto)
depende de que esto se respete. Un DWG que no cumple la convención no entra al
pipeline: el extractor debe fallar con un mensaje claro, no adivinar.

## Por qué capas y no colores

El SOP (`Pasos.pdf`, §2.4 y §3) ya define una convención por color: vigas
morado con líneas interrumpidas, ejes rosado interrumpido, muros y columnas
rojo, dinteles morado con eje rosado, losas en cyan con etiqueta `L1` /
`H=0.16`. Esa convención es correcta como lenguaje visual y **se conserva
tal cual**.

Lo que cambia es de dónde sale el color. Hoy el color puede estar asignado
directo a la entidad; en la convención nueva sale de la capa (`ByLayer`).
Razones:

- El color de entidad se hereda de bloques y se cambia sin intención al
  copiar de otro dibujo. La capa es explícita y se audita de un vistazo en el
  administrador de capas.
- Dos elementos distintos comparten color en el SOP actual (vigas y dinteles,
  ambos morado). Distinguirlos exige mirar la longitud o la etiqueta — es
  decir, heurística. Con capas separadas es determinista.
- `ezdxf` filtra por capa de forma trivial y estable entre versiones de DXF.

El dibujo se sigue viendo idéntico. Cambia solo dónde vive la información.

## Tabla de capas

Prefijo `E-` = estructural. El extractor ignora toda capa que no empiece con
`E-`, lo que permite conservar la arquitectura, cotas y textos del dibujo
original sin ensuciar la extracción.

| Capa | Contenido | Color | Tipo de línea | Geometría esperada |
|---|---|---|---|---|
| `E-EJE` | Ejes estructurales | Rosado (6) | Discontinua (CENTER) | Líneas + texto de etiqueta |
| `E-COL` | Columnas | Rojo (1) | Continua | Polilínea **cerrada** |
| `E-MUR` | Muros (HA o mampostería) | Rojo (1) | Continua | Polilínea cerrada |
| `E-VIG` | Vigas (luz libre > 2 m) | Morado (200) | Discontinua (DASHED) | Línea de eje |
| `E-DIN` | Dinteles (luz ≤ 2 m, con puerta/ventana) | Morado (200) | Discontinua (DASHED) | Línea de eje |
| `E-LOS-MAC` | Losas macizas | Cyan (4) | Continua | Polilínea cerrada |
| `E-LOS-2D` | Losas aligeradas en dos direcciones | Cyan (4) | Continua | Polilínea cerrada |
| `E-LOS-1D` | Losas aligeradas en una dirección | Cyan (4) | Continua | Polilínea cerrada + flecha de dirección |
| `E-TXT-LOS` | Etiquetas de losa (`L1`, `H=0.16`) | Cyan (4) | — | TEXT / MTEXT |
| `E-TXT-SEC` | Etiquetas de sección (`C1 40x40`, `V1 30x50`) | Blanco (7) | — | TEXT / MTEXT |
| `E-VUELO` | Voladizos | Cyan (4) | Continua | Polilínea cerrada |

Un archivo por entrepiso, o un archivo con un bloque/layout por entrepiso.
El nombre del entrepiso se toma del layout o del nombre de archivo según el
patrón `<proyecto>-E<n>.dwg` (ej. `Proyecto-E1.dwg`).

## Reglas de dibujo que el extractor asume

Estas no son estilo, son precondiciones. Si no se cumplen, la extracción
produce basura o falla.

1. **Las polilíneas de columna, muro y losa deben estar cerradas.** Una
   polilínea visualmente cerrada pero con el flag `closed` en falso no
   produce un contorno válido. Verificar con `PEDIT > Cerrar`, no a ojo.
2. **Las líneas de eje de viga van de centro a centro de apoyo**, coherente
   con el paso 1 de la sección ETABS del SOP ("definir grid con ejes de centro
   a centro de vigas").
3. **Cada losa tiene exactamente una etiqueta** en `E-TXT-LOS`, ubicada
   *dentro* de su contorno. El extractor asocia texto a losa por contención
   geométrica, no por proximidad.
4. **Formato de etiqueta de losa**: dos líneas, `L<n>` y `H=<espesor en m>`.
   El SOP indica que los espesores de 12 cm no se rotulan; el extractor asume
   `H=0.12` cuando falta la segunda línea. Esa asunción queda registrada acá
   para que no sea una sorpresa.
5. **La numeración de losas sigue el SOP**: izquierda a derecha, arriba hacia
   abajo. El extractor no renumera, respeta lo dibujado — pero avisa si
   detecta huecos o duplicados en la secuencia.
6. **Unidades del dibujo en metros.** Si el DWG está en milímetros, se
   convierte antes de exportar el DXF. Un error de escala acá se propaga a
   todo el pipeline y es difícil de detectar aguas abajo porque el modelo
   "se ve bien", solo que 1000 veces más grande.
7. **Las losas aligeradas en una dirección llevan una flecha en `E-LOS-1D`**
   indicando la dirección de las viguetas. Sin ella, el extractor no puede
   decidir la dirección y debe fallar en vez de suponer. Corresponde al
   `Use special One-way Load Distribution` del paso 5 del SOP.
8. **Vigas y dinteles no se distinguen por longitud automáticamente.** La
   regla del SOP (2 m) se aplica al *dibujar*, decidiendo en qué capa va cada
   elemento. El extractor confía en la capa. Motivo: la regla real del SOP
   depende de si hay puerta o ventana en ese vano, dato que el dibujo
   estructural no contiene.

## Plantilla

La convención se materializa en un archivo `.dwt` con las capas ya creadas,
sus colores y tipos de línea. Eso vuelve la adopción una decisión de una vez
en lugar de disciplina sostenida: quien empieza un proyecto arranca del `.dwt`
y las capas ya están.

Pendiente de crear: `plantillas/ESTRUCTURAL-CDCRD.dwt`.

## Validador

Antes de correr el extractor conviene un paso de verificación que revise el
DXF y reporte, sin calcular nada:

- Capas `E-*` presentes y ninguna capa `E-*` desconocida.
- Polilíneas abiertas en capas que exigen contorno cerrado.
- Losas sin etiqueta, etiquetas fuera de todo contorno, etiquetas duplicadas.
- Losas `E-LOS-1D` sin flecha de dirección.
- Huecos o duplicados en la numeración de losas.
- Extensión del dibujo fuera de un rango razonable (detector de escala mal).

Ese validador es más valioso que el extractor mismo en las primeras semanas:
es lo que convierte "el pipeline no funcionó" en "la losa L7 no tiene
etiqueta".

## Camino PDF

No hay extracción confiable desde PDF raster. Los dos caminos posibles:

- **PDF vectorial**: convertir a DWG, revisar el resultado (los conversores
  producen líneas fragmentadas y capas arbitrarias), y reasignar capas según
  esta convención. El trabajo de reasignación es real, no trivial.
- **PDF raster**: usar como *underlay* escalado y redibujar el esquema
  estructural encima, directo en las capas correctas. Es lo que el SOP ya
  describe en §2.3 ("dibujar el esquema estructural en AutoCAD o a mano"), o
  sea que no agrega trabajo al proceso actual — solo lo redirige a capas
  nombradas.

En ambos casos el resultado entra al pipeline por la misma puerta que un DWG
nativo. No hay una segunda ruta que mantener.
