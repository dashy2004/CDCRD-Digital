# Rellenar usos y distinguir la base del acero

En `Uso_Losa`, elegir el uso de una celda y arrastrar el **cuadro verde de su esquina inferior izquierda** hacia arriba o abajo en la columna Uso. El cuadro se coloca a la izquierda para dejar libre el desplegable. Soltar fuera de esa columna o pulsar Escape cancela. Al llegar al borde de la tabla se desplazan las filas.

Alternativa: seleccionar varias celdas de Uso y pulsar **Ctrl+D**, o el botón `Uso: arrastrar cuadro verde / Ctrl+D rellena desde arriba`. Copia el uso de la celda superior seleccionada a las otras celdas seleccionadas; no rellena huecos de una selección discontinua ni otras columnas. Primero debe cerrarse el desplegable. Los cambios quedan en el panel hasta `Guardar en el modelo`; este botón no guarda el RVT en disco.

La columna `Base del acero` distingue franja maciza de 1 m de losa aligerada. La detección consulta también el nombre del tipo nativo: un selector en `auto` no convierte una losa aligerada en maciza.

El módulo `acero_pm.py` sigue calculando una franja rectangular de 1000 mm de ancho y el espesor completo. **No dimensiona una sección nervada/T**. Por eso, las columnas de acero de una aligerada se muestran como antecedentes de solo lectura; no se precargan desde el cálculo PM ni se reescriben al guardar usos. Las salidas antiguas pueden conservar textos heredados, identificados como tales.

Mientras haya aligeradas en el panel, sus acciones de plano y acero 3D se detienen con un mensaje explicativo: el flujo genera el lote completo y no debe presentar la equivalencia por metro como detalle de nervios. Esta restricción corresponde al panel; no constituye una validación de los CLI ni de salidas históricas abiertas por separado.

Para un futuro diseño de nervios hacen falta ancho/paso, capa de compresión, materiales, recubrimientos, posición del eje neutro, momentos por nervio y zona, cortante, mínimos, flechas y anclajes. Multiplicar As/m por el paso solo convierte unidades de cantidad, no demuestra resistencia ni permite seleccionar barras automáticamente.

Validación: pruebas de handlers con rejilla ficticia (relleno ascendente/descendente, cancelación, selección discontinua y exclusión de aligeradas); prueba adicional de los controles WinForms reales con filas sintéticas, sin transacción de Revit. El arrastre físico y la ergonomía del ratón pueden revisarse al abrir el panel; la prueba nativa invoca sus eventos con coordenadas de celdas reales.
