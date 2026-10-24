# Cunetas y bermas por API â€” 0.5.17

Ensamblaje, corredor y secciones probados en **otra copia** del ensayo sintÃ©tico de [calzada 0.5.16](CALZADA-0516.md). El original y las entregas anteriores permanecen intactos. Civil 3D 2027, .NET 10; resultado geomÃ©trico, sin aprobaciÃ³n de diseÃ±o. `[codex]`

## Contrato

`crear_ensamblaje_cunetas_bermas` / `civil.ensamblaje_cunetas_bermas` crea doce subensamblajes: por cada lado, carril con cuatro capas â†’ berma â†’ cara interior de cuneta â†’ fondo â†’ cara exterior â†’ daylight. La berma parte del borde superior del carril; el daylight parte del borde exterior de la cuneta. Usa `LaneSuperelevationAOR`, cuatro `LinkWidthAndSlope` y `DaylightMaxWidth` por lado. Se releen parÃ¡metros, lados, enganches y geometrÃ­a local antes de confirmar la transacciÃ³n.

| ParÃ¡metro nuevo | Unidad y rango |
|---|---|
| `ancho_berma_izq`, `ancho_berma_der` | 0,05â€“20 m |
| `pendiente_berma_izq`, `pendiente_berma_der` | âˆ’1..1 m/m, positivo hacia arriba al alejarse del eje |
| `profundidad_cuneta` | 0,05â€“5 m |
| `ancho_fondo_cuneta` | 0,05â€“10 m |
| `talud_cuneta_interior_hv`, `talud_cuneta_exterior_hv` | 0,25â€“10 H/V |

Carriles, espesores y daylight conservan los lÃ­mites de 0.5.16. **Los taludes del daylight son gradientes dz/dx; los de cuneta son H/V.** Unidades Civil e INSUNITS en metros, nombres nuevos, confirmaciÃ³n explÃ­cita y token ligado a los parÃ¡metros exactos. `simular=True` ejecuta y aborta la transacciÃ³n. La operaciÃ³n anterior `crear_ensamblaje_calzada` conserva su enganche a la subrasante.

La berma representa una superficie sin capas. La cuneta trapezoidal se coloca a **ambos lados tanto en corte como en relleno**, con fondo horizontal transversal; sigue longitudinalmente la rasante. No incluye revestimiento, dimensionamiento hidrÃ¡ulico, selecciÃ³n condicional de cuneta, peraltes ni una justificaciÃ³n constructiva. Esos lÃ­mites son explÃ­citos, no resultados deducidos de la geometrÃ­a.

`crear_corredor_calzada` asigna el terreno TIN a los targets y genera la superficie Top. Los cÃ³digos nuevos `BermaExterior`, `CunetaFondoInterior`, `CunetaFondoExterior` y `CunetaBordeExterior` permiten verificar cada vÃ©rtice. `crear_secciones_corredor` muestrea esa superficie con vistas H=V.

## Ensayo nativo y persistencia

Eje de 365,663706 m, dos arcos R40 y rasante con curvas verticales; 44 estaciones, terreno plano z=102. Carriles de 3,50 m a âˆ’2 %, capas 0,05/0,07/0,20/0,30 m. Berma izquierda de 1,50 m a âˆ’4 % y derecha de 2,00 m a âˆ’3 %. Cunetas de 0,60 m de profundidad, fondo 0,50 m, caras 2:1 y 1,5:1 H/V. Daylight de corte 3 y relleno 4 dz/dx. Ocho secciones, incluyendo corte y relleno.

**70 comprobaciones nativas**: 37 del ensamblaje/corredor, 20 de secciones, 8 de guardado/reapertura y 5 del cierre final. Nueve rechazos con auditorÃ­a completa antes/despuÃ©s sin residuos; incluyen fallos inyectados en `berma-cuneta-part-added` y `corridor-rebuilt`. Las simulaciones de ensamblaje, corredor y secciones tambiÃ©n revierten sin residuos.

| FÃ³rmula independiente | Error mÃ¡ximo (m) |
|---|---:|
| XY de puntos aplicados frente al eje | 9,313e-10 |
| Cota absoluta frente a rasante + cota relativa | 5,874e-12 |
| Anchos, pendientes y profundidad de bermas/cunetas | 1,110e-16 |
| Daylight frente al terreno z=102 | 1,421e-14 |
| Desarrollo horizontal del daylight segÃºn su gradiente | 2,726e-10 |
| Capas de pavimento | 1,110e-16 |
| VÃ©rtices de la superficie muestreada en secciones | 6,885e-10 |

Guardado, cierre y reapertura reales, sin reiniciar la aplicaciÃ³n: colecciones y geometrÃ­a Civil persistidas, todos los corredores con `IsOutOfDate=false`, `Saved=true`, `DBMOD=0`, sin comando pendiente. Conservados los 1.303 objetos previos y todas sus colecciones; comparaciÃ³n numÃ©rica con tolerancia 1e-6. Tras el primer guardado reapareció DBMOD=16; cinco controles adicionales confirmaron inventario y geometría iguales, corredores actualizados y una segunda reapertura correcta. La copia se guardó y cerró para dejar el archivo final estable. Ocho archivos protegidos conservan sus SHA-256. DWG final del ensayo: `bbb0ed8fecc20f08b6777a35250fea0f4b5a2482b30fdce12198d69404cce453`.

Pruebas offline: **175 Python**, **187 .NET + 100 carreras de concurrencia**; puente y arnÃ©s nativo compilados sin errores ni advertencias. [Resumen verificable](CUNETAS-BERMAS-0517-resultados.json).

## DiagnÃ³stico y reproducciÃ³n

Un primer intento de simulaciÃ³n detectÃ³ una comparaciÃ³n incorrecta entre puntos de dos sistemas locales y abortÃ³ sin residuos. Una sonda nativa confirmÃ³ que `Subassembly.Points` devuelve coordenadas locales de **cada** subensamblaje: la berma termina en (âˆ’1,50; âˆ’0,06), aunque estÃ© enganchada al borde de carril (âˆ’3,50; âˆ’0,07). La validaciÃ³n corregida compara los extremos del mismo enlace. Las coordenadas acumuladas se comprueban independientemente en el corredor y sus secciones. El intento rechazado no se cuenta como pase.

Para reproducir, preparar otra copia del fixture 0.5.16 con prefijo `CDCRD_GM_RECOVERY_CUNETAS_BERMAS`, compilar/cargar el puente 0.5.17 y el arnÃ©s opcional `pruebas/native_gm_qa`; activar la raÃ­z QA explÃ­citamente con `CDCRDGMQAENTER` sobre esa copia. El arnÃ©s no se instala con el puente normal. Los comandos de QA requieren `CDCRD_C3D_PERMITIR_COMANDOS=1`; para persistencia se necesita `pywin32`.

```powershell
py pruebas/humo_cunetas_bermas.py --drawing <copia.dwg> --output <carpeta-copia> --port 8760
py pruebas/secciones_cunetas_bermas.py --drawing <copia.dwg> --output <carpeta-copia> --smoke <cunetas-smoke.json>
py pruebas/persistencia_cunetas_bermas.py --drawing <copia.dwg> --output <carpeta-copia> --smoke <cunetas-smoke.json> --pid <PID-Civil>
```

Los recibos existentes nunca se sobrescriben ni se reintentan escrituras automÃ¡ticamente. Inspeccionar cola, documento y recibos despuÃ©s de una interrupciÃ³n. La herramienta MCP nueva requiere que el servidor Python use este cÃ³digo y vuelva a cargar su catÃ¡logo; la prueba nativa aquÃ­ usa el mismo mÃ©todo JSON-RPC y su aprobaciÃ³n exacta.

## Capturas reales

PNG directos de `Document.CapturePreviewImage`, sin recorte, retoque ni generaciÃ³n de imÃ¡genes. Las anotaciones del ensamblaje son entidades del DWG. Planta y secciones se aislaron temporalmente para capturarlas y se restaurÃ³ la visibilidad antes del guardado verificado. Las imÃ¡genes muestran el Ã¡rea grÃ¡fica; no son capturas de toda la ventana.

![Ensamblaje nativo con dos bermas y cunetas](images/civil3d-cunetas-ensamblaje-0517.png)

![Corredor nativo en planta sobre eje curvo](images/civil3d-cunetas-planta-0517.png)

![SecciÃ³n nativa 1+10 en corte](images/civil3d-cunetas-corte-0517.png)

![SecciÃ³n nativa 1+80 en relleno](images/civil3d-cunetas-relleno-0517.png)

## Pendientes

Cunetas condicionales corte/relleno y revestimiento, dimensionamiento hidrÃ¡ulico, peraltes, espirales, mÃºltiples baselines/regiones, targets de ancho/cota, QTO y barrido vehicular. La verificaciÃ³n geomÃ©trica de esta versiÃ³n no acredita esas capacidades.
