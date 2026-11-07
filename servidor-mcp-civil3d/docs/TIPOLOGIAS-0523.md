# Clasificación de bordes y tipología por tramo — 0.5.23

Dos operaciones sobre un corredor existente de una sola baseline y una sola región: decidir, lado por lado y estación por estación, dónde el borde de calzada es libre y dónde es unión con otro pavimento; y dividir esa región en tramos con variantes de la paleta métrica (bordillo-cuneta en los bordes libres, sección abierta en las uniones y sección completa con talud donde haga falta). Módulo opcional `Cdcrd.Tipologias.V1` **0.1.0**, comando `CDCRDTIPOLOGIASV1`, instalado con `instalar-tipologias.ps1`; no inicia ni reinicia Civil 3D. [fable], 2026-11-06.

Origen: una herramienta de un solo uso escrita para un modelo de proyecto, revisada aquí con criterio de herramienta pública. Lo que traía atado al proyecto (handles, rutas, prefijos de nombre, lock de sesión, archivo histórico de corredores, cambio de capa de todos los ensamblajes) se quitó o se convirtió en parámetro; lo que fallaba en silencio (copia de parámetros que tragaba excepciones) ahora falla con nombre de parámetro; y la verificación ya no excluye las estaciones de frontera entre regiones.

## Uso y contrato

```python
clasificar_bordes_corredor(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, corredor=HANDLE_O_NOMBRE,
    sonda_m=1.0, superficies_pavimento="[]", superficies_excluidas="[]", union_min_m=2.0, libre_min_m=5.0)
aplicar_tipologia_por_tramo(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, corredor=HANDLE_O_NOMBRE,
    segmentos='[[0, 35.5, "R"], [35.5, 47, "-"], [47, 139, "LR"]]', simular=True, confirmar=True)
reconstruir_tipologia_por_tramo(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, corredor=HANDLE_O_NOMBRE, confirmar=True)
verificar_tipologia_por_tramo(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, corredor=HANDLE_O_NOMBRE)
```

**Clasificar** (lectura, sin cambios). En cada estación aplicada toma el punto exterior de cada lado con el código de borde y un punto a `sonda_m` hacia afuera, en la dirección eje→borde, y comprueba si cae sobre alguna superficie de pavimento vigente con `FindElevationAtXY`. Por defecto las superficies de pavimento son las Top de los demás corredores del dibujo; `superficies_pavimento` las sustituye por una lista explícita (handles o nombres) y `superficies_excluidas` quita las que no deben contar (por ejemplo un corredor de talud superpuesto). Las propias superficies del corredor nunca cuentan. El código de borde se elige entre `ETW` y `Edge` según cuál lleve el **punto exterior** de la sección: con carriles y bandas el borde real es el `Edge` de la banda, no el `ETW` del carril; `codigo_borde` lo fija a mano. Dos filtros en este orden: uniones más cortas que `union_min_m` pasan a libres; tramos libres más cortos que `libre_min_m` pasan a unión. Los tramos propuestos cortan en la primera estación adyacente cuando un lado se cierra y en la última cuando se abre, de modo que una unión abarca exactamente sus estaciones adyacentes. Devuelve muestras por estación (unión, borde XYZ, sonda XY), inventario de la región (piezas con parámetros, objetivos, transiciones, superficies) y `segmentos` listos para aplicar. Exige corredor reconstruido; hasta 20.000 estaciones.

**Aplicar** (escritura bajo bloqueo y una transacción; `simular=True` por defecto aborta). `segmentos` son tramos contiguos `[inicio, fin, tipo]` que cubren la región; tipos `LR`, `L`, `R` (bordillo-cuneta en esos lados), `-` (unión abierta) y `talud` (ensamblaje completo con encuentro al terreno; exige `superficie_terreno`). El corredor debe tener una baseline, una región y una Top; el ensamblaje original solo carriles `LaneSuperelevationAOR` (uno por lado, de corona) y como máximo una banda `LinkWidthAndSlope` por lado enganchada al carril. Pasos:

1. Reconstruye el corredor y captura el borde de cada estación como referencia.
2. Abre como bases laterales los DWG de la biblioteca métrica instalada (`%PROGRAMDATA%\Autodesk\C3D <año>\enu\Assemblies\Metric`, o `biblioteca`): `ensamblaje_carriles` (por defecto `Primary Road - Through Intersection`), `ensamblaje_bordillo` (`Primary Road Full Section`, de donde se copian los parámetros del `subensamblaje_bordillo`, por defecto `UrbanCurbGutterGeneral`) y `ensamblaje_talud` (`Primary Road Full Section`).
3. Crea una variante por tipo usado, importada de la paleta y colocada desde `origen` cada `separacion_m`: renombra los carriles como los originales (objetivos y transiciones se resuelven por nombre), iguala `Width`, `DefaultSlope`, `Pave1Depth`, `Pave2Depth`, `BaseDepth` y `SubBaseDepth`, reimporta las bandas y agrega el bordillo. Cada copia de parámetros se relee: una diferencia tras copiar, o un parámetro de solo lectura distinto, es error con el nombre del parámetro; los parámetros que solo existen en la pieza de biblioteca se reportan como `ausentes`.
4. Divide la región con `BaselineRegion.Split` en cada corte y asigna la variante; nombra las regiones `<región original> - NN <tipo>`.
5. Reasigna los objetivos: cada objetivo original debe encontrar su equivalente (mismo subensamblaje, tipo y nombre lógico) en todas las regiones, si no, error; los objetivos de superficie de las piezas de encuentro al terreno apuntan a `superficie_terreno`.
6. Recorta las transiciones por región interpolando sus valores en los cortes, con el mismo subensamblaje.
7. Sustituye los contornos de la Top por `AddCorridorExtentsBoundary`, reconstruye el corredor y, de forma explícita, la Top: dentro de la transacción la Top no sigue sola a la reconstrucción del corredor y su conteo de triángulos sería el anterior.
8. Verifica (tolerancia `tolerancia_m`, 5 mm): bordes XY y Z contra la referencia en todas las estaciones comunes (al menos el 90 %), `Back_Curb` presente en cada estación y lado donde el tramo lo pide y ausente donde no, `Daylight` contra la TIN en los tramos `talud`, Top con triángulos y corredor al día. En las estaciones de frontera el ensamblaje aplicado tiene que ser el de una de las dos regiones vecinas, y la expectativa se evalúa con el tipo de esa región: no se excluyen.
9. Guarda el contrato `CDCRD_TIPOLOGIAS_V1` (segmentos, variantes, código de borde, carriles, terreno, biblioteca) en el diccionario de extensión del corredor. No reemplaza una tipología ya aplicada.
10. Al confirmar, una segunda transacción reconstruye corredor y Top y una tercera, de lectura, repite la verificación desde el contrato; el recibo trae `aplicado` y `verificacion_tras_confirmar`, ambos al día. Aun así, **al terminar el comando** Civil vuelve a marcar el corredor fuera de fecha (sus ensamblajes cambiaron), y `verificar` lo encuentra así en el comando siguiente. **Reconstruir** (`reconstruir_tipologia_por_tramo`, escritura confirmada) reconstruye corredor y Top en un comando propio, repite la verificación y deja el indicador limpio para guardar. La misma observación consta en la entrega de peraltes 0.5.18 ("indicador diferido de reconstrucción").

**Reconstruir** exige el contrato, reconstruye y verifica; informa si el corredor estaba fuera de fecha. **Verificar** relee el contrato y repite el punto 8 sin referencia de bordes.

Transporte igual al de los módulos de targets y corredores: solicitud inmutable con SHA-256, PID y documento exactos, vencimiento, archivo `.started` y recibo ligado a la solicitud. Ante timeout se consulta el recibo y la cola; **no se reenvía**.

## Resultados en una copia privada

Copia desechable de un modelo de proyecto (32 corredores, 63 superficies, metros), en la misma instancia de Civil 3D 2027, con el puente vivo 0.5.20. Los nombres, handles y geometría del modelo no se publican; los recibos quedan fuera del repositorio.

- Clasificación de 13 corredores de calzada con la misma lista de superficies de pavimento que usó la herramienta de un solo uso. La adyacencia cruda por estación coincidió exactamente con la del análisis original (por ejemplo 561/30 y 94/50 estaciones adyacentes por lado) y los tramos propuestos coincidieron en 11 de 13; los otros dos difieren solo por el tramo `talud` que el análisis original insertó a mano. Antes de la regla del punto exterior, el corredor con bandas se clasificaba con `ETW` y daba libre un borde que es unión.
- Aplicación simulada en cuatro corredores: uno simple (5 regiones, 122 estaciones, 188 bordillos esperados y encontrados), uno con bandas y código `Edge` (3 regiones, 113 bordillos), uno con 3 transiciones recortadas en 7 conjuntos (9 regiones, 845 estaciones, 1.561 bordillos) y uno con tramo `talud` (7 regiones, 349 estaciones, 557 bordillos, 200 puntos de encuentro con |Δz| máximo 2,9·10⁻¹² m contra la TIN). Bordes contra la referencia: 2,4·10⁻¹⁰ m en planta y 5·10⁻¹³ m en cota; ningún bordillo sobrante; Top con triángulos; nada fuera de fecha.
- Copia de parámetros verificada: en los carriles solo `Width` difería de la paleta; en el bordillo solo el entero `Version`, y `UseSE` existe en la pieza de biblioteca pero no en la importada (reportado como ausente, no copiado a ciegas).

- Fallo inyectado en `corridor-rebuilt` (dos veces, en corredores distintos): error explícito `CDCRD_QA_TIPOLOGIA_FAILURE` y conteos de corredores, ensamblajes, subensamblajes y superficies idénticos antes y después.
- Aplicación confirmada en dos corredores (el simple y el de bandas). En el comando siguiente ambos aparecían fuera de fecha; `reconstruir` los dejó al día (Top de 1.951 y 1.800 triángulos con bordillo). Guardado por COM, cierre, reapertura en el mismo proceso y `verificar` desde el contrato: 188/188 y 113/113 bordillos, sin sobrantes, nada fuera de fecha.

Pruebas: 27 pruebas Python del envoltorio (`tests/test_tipologias.py`), compilación de módulo y arnés con 0 errores y 0 advertencias, `pruebas/humo_tipologias.py` (carga, avisos, clasificar, aplicar, reconstruir, verificar) y `pruebas/persistencia_tipologias.py` (fallo inyectado, aplicación, reconstrucción, guardado, reapertura y verificación). La autocarga del bundle al próximo arranque normal no se ha comprobado.

## El aviso `Add param returned null` del visor de eventos

La herramienta de un solo uso registró unos 236 avisos de `C3DStockSubassemblies` con ese texto y se atribuyeron a la reconstrucción. No es así. El texto es el mensaje de la excepción que lanza `Autodesk.Civil.Runtime.ParamCollectionBase<T>.ImplementAdd` (en `AeccDbMgd.dll`) cuando el lado nativo rechaza añadir un parámetro; existe para los tipos `ParamDouble`, `ParamLong`, `ParamString`, `ParamBool`, `ParamAlignment`, `ParamProfile`, `ParamSurface`, `ParamPoint`, `ParamOffsetTarget` y `ParamElevationTarget`. Un arnés con `AppDomain.FirstChanceException` reprodujo en la copia, con el conteo exacto, cuándo ocurre:

| Operación sobre la copia | Excepciones `Add param returned null` |
|---|---|
| Leer `ParamsDouble` de las 332 piezas por región desde una base lateral del archivo guardado | 0 |
| Lo mismo sobre el documento vivo | 0 |
| `Subassembly.Run()` suelto de las 332 piezas | 0 |
| Reconstruir los 32 corredores | 0 (sí 10.416 `Target Not Found!` internas, propias de los scripts de paleta) |
| `BaselineRegion.GetTargets()` de las 94 regiones **desde una base lateral** | **236** |
| `BaselineRegion.GetTargets()` de las 94 regiones sobre el documento vivo | 0 |

La pila es `Subassembly.LinkWidthAndSlope.GetLogicalNamesImplement(CorridorState)` (y sus equivalentes de carril y encuentro al terreno): al pedir los objetivos de una región cuyo dibujo está abierto como base lateral, cada subensamblaje con objetivos intenta registrar sus parámetros de objetivo en un `CorridorState` sin documento, la adición devuelve nulo y el script registra la excepción como aviso. Se produce una por pieza con objetivos y región: 332 piezas menos 96 de `UrbanCurbGutterGeneral`, que no declara objetivos, son 236. La causa fue la acción `audit_file` de la herramienta original, que leía el DWG recién guardado en una base lateral y pedía `GetTargets()` por región; la reconstrucción no interviene y el modelo no quedó afectado. Regla: leer objetivos solo en el documento vivo; en una base lateral limitarse a regiones, ensamblajes y parámetros.

## Límites

- Solo corredores locales con una baseline, una región, carriles de corona y bandas opcionales; no edita corredores ya divididos ni reemplaza una tipología aplicada.
- La tipología `talud` usa el ensamblaje de paleta completo tal cual; la decisión de dónde va un talud no se deduce de la clasificación.
- No agrega aceras, no modela intersecciones nativas ni radios de bordillo, no archiva ni elimina otros corredores, no cambia capas de ensamblajes ajenos y no reconstruye superficies compuestas de terceros.
- Espesores y dimensiones son los del catálogo instalado; el diseño de pavimento y el bordillo real quedan fuera.
- El comando se registra al cargar con el nombre derivado del ensamblado: `Cdcrd.Tipologias.V1` registra `CDCRDTIPOLOGIASV1`; una compilación de prueba `-p:AssemblyName=Cdcrd.Tipologias.V1b` registra `CDCRDTIPOLOGIASV1B` y puede cargarse junto a la anterior en el mismo proceso (igual el arnés `Cdcrd.TipologiasV1Qa` → `CDCRDTIPOLOGIASV1QA`). `humo_tipologias.py --comando` y `--modulo-dll` eligen cuál usar; el envoltorio MCP usa siempre el nombre canónico.
