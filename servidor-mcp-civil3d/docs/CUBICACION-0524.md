# Espesores de pavimento, Datum y cubicación de corredores — 0.5.24

Tres operaciones sobre corredores existentes, de una o varias baselines y regiones (por ejemplo los ya divididos por tramos con [tipologías 0.5.23](TIPOLOGIAS-0523.md)): escribir los espesores de capa calculados en los carriles de todos sus ensamblajes, crear la superficie Datum del corredor y cubicar corte/relleno contra el terreno y volúmenes por capa. Módulo opcional `Cdcrd.Cubicacion.V1` **0.1.0**, comando `CDCRDCUBICACIONV1`, instalado con `instalar-cubicacion.ps1`; no inicia ni reinicia Civil 3D. [fable], 2026-11-06.

Motivación: un diseño de pavimento (AASHTO 93: asfalto 7,5 + 5 cm, base 25 cm, subbase 35 cm) tiene que llegar a los carriles `LaneSuperelevationAOR` de corredores ya modelados con la paleta métrica, cuyos espesores son los del catálogo, y de ahí salir la cubicación. Es un módulo nuevo y no una ampliación del de tipologías porque ese módulo aún no está en `master` (PR 66) y las tres acciones no dependen de él.

## Uso y contrato

```python
asignar_espesores_pavimento(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, corredor=HANDLE_O_NOMBRE,
    espesores='{"Pave1Depth": 0.075, "Pave2Depth": 0.05, "BaseDepth": 0.25, "SubBaseDepth": 0.35}',
    subensamblajes="[]", regiones="[]", tolerancia_m=0.001, simular=True, confirmar=True)
crear_datum_corredor(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, corredor=HANDLE_O_NOMBRE,
    nombre="", codigo="Datum", simular=True, confirmar=True)
cubicar_corredor(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, corredor=HANDLE_O_NOMBRE, terreno=HANDLE_O_NOMBRE_TIN,
    datum="", codigos="[]", nombre_volumen="", factor_corte=1, factor_relleno=1, simular=True, confirmar=True)
```

Transporte igual al de los módulos de targets y tipologías: solicitud inmutable con SHA-256, PID y documento exactos, vencimiento, archivo `.started` y recibo ligado a la solicitud. Las tres herramientas exigen `confirmar=True` y simulan por defecto; `simular=False` escribe. Ante timeout se consulta el recibo y la cola; **no se reenvía**. Todo sucede bajo bloqueo del documento y en una transacción que la simulación aborta. El contrato propio es el Xrecord `CDCRD_CUBICACION_V1` del diccionario de extensión del corredor, con una entrada por acción (`espesores`, `datum`, `cubicacion`) que una nueva ejecución de esa acción reemplaza.

**Espesores.** `espesores` es `{parámetro: metros}` (1..12 claves, 1 mm..5 m): cualquier parámetro doble que exista en el carril, no solo los cuatro de capa. Los carriles son los subensamblajes con `Width`, `DefaultSlope` y `Pave1Depth` (`LaneSuperelevationAOR` y equivalentes) de los ensamblajes que usan las regiones del corredor, de todas sus baselines; `regiones` limita a esas regiones y `subensamblajes` fija las piezas por nombre o handle (cualquier pieza que tenga al menos uno de los parámetros). Se rechaza un ensamblaje que también use otro corredor, o una región fuera de la selección, porque el cambio saldría del pedido. Pasos:

1. Lee los valores previos de cada carril, escribe cada parámetro, lo relee y exige igualdad; un parámetro de solo lectura distinto es error con nombre. Los parámetros que el carril no tiene se reportan como `ausentes`; si no tiene ninguno, error.
2. Ejecuta el subensamblaje (`Run`) y mide en su **geometría propia** el espesor vertical de las formas `Pave1`, `Pave2`, `Base` y `SubBase` en sus dos bordes (las capas de los carriles de catálogo tienen lados verticales): cada borde debe medir el espesor escrito dentro de `tolerancia_m` (1 mm). Esta comprobación vale en simulación, antes de reconstruir nada.
3. Guarda el contrato (espesores, handles de carril, regiones, tolerancia). Con `simular=True` la transacción se aborta aquí y el recibo lo dice.
4. Al confirmar, una **segunda transacción** reconstruye el corredor y sus superficies y repite la medida sobre las formas de las **secciones aplicadas** de cada estación de las regiones seleccionadas; el recibo trae `aplicado` y `verificacion_tras_confirmar`.
5. Después el envoltorio envía `reconstruir` en un comando propio y añade su recibo como `reconstruccion`.

Hallazgo que fija esa estructura: dentro de la transacción que escribe los parámetros, `Corridor.Rebuild()` **sigue aplicando los espesores anteriores**. La primera versión medía las secciones aplicadas en la misma transacción y falló con errores relativos exactamente iguales a (nuevo − viejo)/nuevo: 0,667 en `Pave1` (0,025→0,075), 0,5 en `Pave2`, 0,6 en `Base` y 0,143 en `SubBase`. Tras confirmar, la reconstrucción en una segunda transacción sí aplica los nuevos valores, y al terminar el comando Civil vuelve a marcar el corredor fuera de fecha (igual que en tipologías y peraltes): `reconstruir` lo encontró fuera de fecha y lo dejó al día.

**Datum.** Agrega al corredor la superficie `nombre` (por defecto `<corredor>_Datum`) con el código de enlace `codigo` (`Datum`) como línea de rotura, corrección de voladizo por enlaces inferiores (`OverhangCorrection = BottomLinks`) y contorno por extensión del corredor; reconstruye corredor y superficies dentro de la transacción (la superficie no sigue sola al corredor) y verifica: triángulos, y en cada estación aplicada los puntos de los enlaces con ese código contra `FindElevationAtXY` de la Datum (cobertura ≥ 95 %, ningún punto más de 5 mm **por debajo** de la superficie; por encima pueden quedar, porque donde dos secciones se cruzan la corrección conserva el enlace más bajo). Rechaza nombres existentes, corredores que no produzcan ese código y corredores que ya tengan una superficie con él. Al confirmar repite la verificación en segunda transacción y el envoltorio envía `reconstruir`. A diferencia de los espesores, añadir la superficie **no** dejó el corredor fuera de fecha al terminar el comando.

**Cubicación.** Exige corredor al día. `terreno` es la TIN base (local, al día, con triángulos) y `datum` la de comparación: por defecto la del contrato, o la única superficie del corredor con enlace `Datum`. Crea una `TinVolumeSurface` (`nombre_volumen`, por defecto `<corredor>_Cubicacion`) con los factores dados y lee corte, relleno y neto brutos y ajustados. Por capa, suma las áreas de las formas con cada código (`Pave1`, `Pave2`, `Base`, `SubBase` por defecto; hasta 20 códigos) en cada estación aplicada y las integra por **áreas medias** dentro de cada región de cada baseline; una estación de frontera cuenta como extremo de las dos regiones vecinas y los huecos entre regiones no aportan. Devuelve totales, por baseline/región (longitud, estaciones, volúmenes) y por estación (áreas), más el inventario de espesores vigentes en los carriles. `simular=True` calcula y aborta sin dejar objetos; `simular=False` conserva la superficie de volumen y escribe el resultado en el contrato. No envía `reconstruir`: no cambia ensamblajes.

Presupuesto: 20.000 estaciones por acción. Unidades: metros en Civil y AutoCAD. Objetos locales.

## Resultados en una copia privada

Copia desechable de un modelo de proyecto (32 corredores, 63 superficies, metros), abierta en la misma instancia de Civil 3D 2027 que el modelo, con el puente vivo 0.5.20 y el módulo cargado por `NETLOAD`. Nombres, handles y geometría no se publican; los recibos quedan fuera del repositorio. Corredor A: una baseline dividida en 7 regiones por tipologías (bordillo LR/R, cruce y un tramo talud), 4 ensamblajes con 2 carriles `LaneSuperelevationAOR` cada uno, 349 estaciones aplicadas, Top de 6.679 triángulos. Corredor B: una región, mismo catálogo.

| Paso | Resultado |
|---|---|
| Lectura | 8 carriles con los espesores del catálogo métrico 0,025 / 0,025 / 0,10 / 0,30 m; sin contrato |
| Espesores, simulación | 8 carriles escritos y releídos; 32 formas de la geometría propia con error máximo 5,6·10⁻¹⁷ m |
| Espesores, confirmación | segunda transacción: 349 estaciones, 698 carriles aplicados, 2.792 formas, error máximo 5,6·10⁻¹⁷ m, nada fuera de fecha; `reconstruir` en comando propio: estaba fuera de fecha → al día |
| Datum, simulación y confirmación | 5.161 triángulos; 3.684 puntos de enlace `Datum` en 349 estaciones, cobertura 100 %, 7·10⁻¹⁵ m por debajo y hasta 0,604 m por encima (cruces de sección corregidos por enlaces inferiores); corredor al día al terminar el comando |
| Cubicación, simulación y confirmación | corte 1.181,5 m³, relleno 124,6 m³, neto −1.056,9 m³ (factores 1); capas: `Pave1` 95,86, `Pave2` 63,90, `Base` 319,52, `SubBase` 515,88 m³ en 355 estaciones (349 + 6 fronteras contadas dos veces como extremo) y 170,41 m; área media `Pave1` 0,5625 m² = 7,5 m × 0,075. Cifras idénticas al confirmar; superficie de volumen conservada |
| Fallo inyectado `record-written` (espesores, corredor B) | error explícito `CDCRD_QA_CUBICACION_FAILURE`, `committed=false`, espesores de catálogo y 65 superficies iguales antes y después |
| Fallo inyectado `corridor-rebuilt` (Datum, corredor B) | ídem; ninguna superficie nueva |
| Corredor B (una región, 845 estaciones), compilación revisada | espesores simulados sin fallos; Datum simulada de 6.498 triángulos, 6.502 puntos de enlace cubiertos, 7·10⁻¹⁵ m por encima y por debajo (sin cruces de sección) |
| Guardado, cierre y reapertura (`pruebas/persistencia_cubicacion.py`) | ver nota al final de la sección |

La TIN de terreno "pegada" del modelo estaba fuera de fecha y la cubicación la rechazó con el nombre de la superficie; se usó la TIN de implantación al día. La suma de las capas por región coincide con los totales (por ejemplo `Pave1`: 6,47 + 2,81 + 18,84 + 28,12 + 17,72 + 8,72 + 13,17 = 95,85 m³). `SubBase` tiene área media 3,02 m² > 7,5 × 0,35 porque el ensamblaje de talud y los bordillos de la paleta aportan formas con ese código fuera de los carriles: la cubicación por capa es del corredor completo, no solo de los carriles.

Persistencia (`pruebas/persistencia_cubicacion.py`): guardado por COM, cierre solo de la copia, reapertura en el mismo proceso y las diez comprobaciones aprobadas: `DBMOD=0` al guardar y al reabrir, contrato, espesores y superficies iguales, corredor al día y volúmenes de terreno y por capa reproducidos (simulación) tras reabrir; la simulación de la instantánea deja `DBMOD=1` sin geometría, por lo que el script guarda una vez más antes de la comprobación final. Que la simulación no deja objetos lo prueban dos cosas: el inventario de 65 superficies igual tras el fallo inyectado posterior a `CorridorSurfaces.Add`, y que la confirmación de la cubicación creó la superficie de volumen con su nombre por defecto después de dos simulaciones con ese mismo nombre.

Pruebas: 26 pruebas Python del envoltorio (`tests/test_cubicacion.py`; 318 en la suite), compilación de módulo y arnés con 0 errores y 0 advertencias, `pruebas/humo_cubicacion.py` (cargar, leer, espesores, datum, cubicacion, fallo) y `pruebas/persistencia_cubicacion.py`.

## Límites

- Mide espesores solo en formas con lados verticales (`Pave1`, `Pave2`, `Base`, `SubBase` de los carriles de catálogo); otros parámetros se escriben y releen pero no se miden geométricamente.
- No edita ensamblajes compartidos entre corredores ni crea variantes: el corredor debe tener ensamblajes propios (los de tipologías lo son).
- La Datum usa el código de enlace y el contorno por extensión; no modela islas, rotondas ni superficies compuestas, y los puntos de enlace por encima de la superficie en cruces de sección se reportan, no se corrigen.
- Los volúmenes por capa son por áreas medias entre estaciones aplicadas, sin corrección de curvatura, y cuentan todas las formas del código en la sección (bordillos y taludes incluidos). Corte/relleno es el de la `TinVolumeSurface` nativa entre terreno y Datum, sin descontar la estructura de pavimento.
- `CDCRDCUBICACIONV1` se declara por atributo; una compilación `-p:AssemblyName=Cdcrd.Cubicacion.V1b` registra además el alias `CDCRDCUBICACIONV1B` para ensayar junto a la ya cargada (`humo_cubicacion.py --comando --modulo-dll`). La autocarga del bundle por `instalar-cubicacion.ps1` sigue el mismo manifiesto verificado en tipologías 0.5.23, pero no se ha comprobado en un arranque normal.
