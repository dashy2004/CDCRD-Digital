# Revisión ETABS — protocolo de ejecución y captura

Modelo: `modelos\edificio_oficinas_SD.EDB`
Proyecto: edificio de oficinas, Santo Domingo, 3 niveles, 2x2 crujías de 6x6 m.
Unidades: kN, m, C.

## Regla general para cada bloque

1. Ejecutar las herramientas MCP `fea` indicadas en el README del bloque.
2. Ajustar la vista de ETABS a la indicada (3D, planta, elevación o tabla).
3. `refresh_view`.
4. Captura de pantalla con `save_to_disk: true`.
5. Mover/renombrar la captura a la carpeta del bloque con el nombre indicado.
6. Anotar en el README del bloque: valor devuelto por la API vs valor visible en ETABS.

Si una herramienta falla por firma OAPI, ejecutar `describe_oapi` sobre ese
namespace, registrar la firma real en el README del bloque, y continuar.

## Captura limpia

- Las capturas guardadas no incluyen el overlay de control de Claude Desktop.
- Para grabación de video en OBS: usar fuente **Window Capture** sobre ETABS,
  no Display Capture, para excluir el overlay del sistema.
- Cerrar el Model Explorer (panel izquierdo) antes de capturar vistas 3D si se
  quiere el modelo a pantalla completa.

## Bloques

> **Capturas: cerradas el 2026-08-08.** 33 de 34 tomadas en una sesión de solo-captura con
> control de escritorio. La única pendiente es `R08/02-ventana-analisis.jpg`, que exige volver
> a correr el análisis. Detalle y hallazgos en `RESUMEN-CAPTURAS-2026-08-08.md`. La columna
> "faltan capturas" de la tabla de abajo ya no aplica a ningún bloque.

| Carpeta | Contenido | Estado |
|---|---|---|
| R01-conexion-unidades | Conexión OAPI, versión, unidades | Hecho, capturas ✅ |
| R02-geometria-niveles | Puntos, frames, áreas, story data | Geometría y unidades **OK**; niveles **no ejecutables por API** — paso manual **ya ejecutado** (respaldo `modelos/edificio_oficinas_SD_ANTES-NIVELES-2026-08-07.EDB`); capturas ✅ |

> **Los tres bloqueos del 2026-08-07 quedaron resueltos**: despliegue (config repuntado a la
> v1.1.0 de 44 herramientas), conexión COM (era desajuste de privilegios; ETABS y Claude Desktop
> como Administrador), y `describe_oapi` roto (leía mal el layout de `comtypes` 1.4.16). El
> servidor está operativo y las firmas de la OAPI ahora se pueden leer en vez de adivinar.
>
> **Hallazgo que cambia el protocolo.** La OAPI **no permite redefinir los niveles de un modelo
> que ya tiene objetos**. Tres rutas independientes rechazadas con `ret=1` — `SetStories`,
> `SetStories_2` y la edición por tablas — con las firmas verificadas contra el typelib y con el
> modelo escribible (un material de prueba se creó sin problema). Prueba decisiva: se le pidió a
> `SetStories` la configuración que el modelo ya tenía y también falló. `Story` no expone
> `DeleteStory` ni renombrado, así que los setters por nivel tampoco alcanzan.
>
> **Consecuencia:** definir los niveles es un paso **manual** en `Edit > Stories and Grid System
> Data`, verificable después por API con `get_stories`. Para modelos nuevos del CDCRD: **definir
> niveles antes de crear geometría**. Detalle y firmas en
> `revision\R02-geometria-niveles\README.md`; auditoría del servidor en
> `servidor-mcp\AUDITORIA-2026-08-07.md`.
>
> **Antes de R03:** borrar el material de prueba `ZZ_TEST_ESCRITURA` desde
> `Define > Material Properties`.
| R03-materiales-secciones | H28, C50x50, V30x50, asignación | **OK por API** (E=2.487e7, 27/36); capturas ✅ |
| R04-apoyos-diafragmas | Empotramiento en base, D1/D2/D3 | **OK por API** (9 apoyos, 3 diafragmas); capturas ✅ |
| R05-cargas | Patrones D/L/Lr y asignación a losas | **OK por API** (4 patrones, 12/8/4 áreas); capturas ✅ |
| R06-sismo-espectro | Fa, Fv, SDS, SD1, espectro, casos Ex/Ey | **PARCIAL** — espectro y casos creados; valores no legibles por API. Capturas ✅, pero solo se leyeron ~6 de los 13 puntos; **el Scale Factor de Ex muestra 9806.65, no 9.80665** |
| R07-combinaciones | Combinaciones LRFD del CDCRD | **OK** — 7 creadas con Ev correcto, releídas con `get_load_combos`; capturas ✅ |
| R08-analisis | Ejecución del análisis | **OK** — T₁ = 0.358 s, masa participante 1.0; capturas 3/4 (falta la ventana de progreso) |
| R09-derivas | Derivas vs límite CDCRD | **OK** — Δmáx 35.04 mm, cumple con ρ=1.0 y ρ=1.3; capturas ✅ |
| R10-reacciones | Reacciones y chequeo de equilibrio | **OK** — ΣFz 6365.5 kN, error −0.65%, ΣFx=ΣFy=0; capturas ✅ |

## Cierre del protocolo — 2026-08-07

**R01 a R10 ejecutados.** El modelo corre, cumple derivas y cierra equilibrio. Lo
que sigue es la lista de lo que quedó abierto, ordenado por lo que bloquea usar
estos resultados para diseñar.

### Bloqueante para diseño

1. **ρ (factor de redundancia) sin resolver en las combinaciones.** R07 usa
   `1.0·Ex` y `1.0·Ey`, lo que asume ρ = 1.0. Si ρ = 1.3, C4x/C4y/C5x/C5y quedan
   del lado inseguro. Las derivas cumplen con cualquiera de los dos valores, así
   que esto **no afecta a R09** pero sí a R10 y a cualquier dimensionamiento.
   → cerrar la condición 2 de cl. 2.10.5.1.2, o adoptar 1.3 y rehacer las 4 combos.
2. **Espesor de losa: el modelo tiene ≈0.197 m, no 0.15 m.** Nunca se definió una
   propiedad de losa; las 12 áreas quedaron con `Slab1` por defecto de ETABS.
   Decidir si se actualiza la documentación o se redefine la losa y se rehace
   R08–R10. Verificar además el material de `Slab1`, que probablemente no es `H28`.

### Verificación incompleta

3. **Espectro CDCRD-SD: los valores no se pudieron leer de vuelta por API.**
   ~~Único canal: capturas~~ **Confirmado con `get_spectrum` (Tanda 1) que
   `GetUser` también devuelve −99** sobre esta función, igual que `SetUser`; la
   hipótesis es que la función importada por tabla no queda en el subtipo "User".
   Las capturas 01 y 02 de R06 siguen siendo el único canal. **Es el único ítem
   del protocolo en esa condición.**
4. ~~**Combinaciones: existen pero no se pudieron releer.**~~ ✅ **CERRADO** con
   `get_load_combos`: las 7 leídas del modelo con los factores exactos, incluidos
   1.2975 / 0.8025. Sin duplicados.
5. **Curva tensión-deformación del hormigón**: los valores 0.0022 / 0.0052 /
   −0.1 están escritos a mano en el servidor y nadie los contrastó con el CDCRD ni
   con ACI 318. No afectan el análisis lineal; sí el no lineal y el diseño.
6. ~~**Las 33 capturas de los 10 bloques están pendientes.**~~ ✅ **CERRADO 2026-08-08.**
   Eran **34**, no 33 (2+4+5+4+3+4+2+4+3+3): el conteo de este punto estaba mal desde el
   principio. 33 tomadas; queda `R08/02-ventana-analisis.jpg`, que exige correr el análisis.
   Ver `RESUMEN-CAPTURAS-2026-08-08.md`.
6c. **Hallazgo de las capturas, sin resolver: el Scale Factor del caso `Ex` lee 9806.65**,
   no los 9.80665 que R06 documenta haber escrito. Factor exacto de 1000×, compatible con
   una confusión mm/s² vs m/s². Los resultados aguas abajo (T₁ = 0.358 s, derivas que cumplen
   con margen coherente) no muestran señal de una demanda sísmica 1000× inflada, así que la
   lectura simple no cierra. **Revisar antes de dar por definitivo cualquier resultado
   sísmico.**
6b. **Espesor de losa CONFIRMADO por lectura directa** (`get_area_sections`):
   `Slab1` = **0.2032 m** (8 in), material **`4000Psi`** (27.6 MPa), no H28. La
   deducción de R10 (0.1969 m) quedó a 3 % del valor real. La decisión de
   redefinir a 0.15 m o documentar 0.2032 sigue abierta (punto 2 de arriba).

### Residuos en el modelo

7. `ZZ_TEST_ESCRITURA` (material) y `ZZ_TEST_FUNC` (caso de espectro vacío).
   Ya existe `delete_definition` (Tanda 1), pero el primer intento devolvió
   `ret=1` — **el modelo está bloqueado tras el análisis de R08** (candado).
   Desbloquear y reintentar: `delete_definition("material","ZZ_TEST_ESCRITURA")`
   y `delete_definition("load_case","ZZ_TEST_FUNC")`. Nota: el análisis se
   invalida al desbloquear; correrlo de nuevo toma segundos en este modelo.

### Deuda del servidor

Consolidada en `servidor-mcp\AUDITORIA-2026-08-07.md`. Lo que más va a doler al
reejecutar: **ningún `add_*` es idempotente** (patrones, combinaciones, diafragmas
fallan si el nombre existe, y `SetCaseList` **duplica factores** en vez de
reemplazarlos). Reejecutar R05 o R07 tal cual sobre este modelo no funciona.

### Regla de método que salió de esta corrida

El mensaje de retorno de una herramienta dice **lo que ella creó**, no **lo que hay
en el modelo**. ETABS aporta objetos por defecto que colisionan con el protocolo:
apareció con el diafragma `D1` (R04), con los patrones `Dead`/`Live` —y `Dead`
traía peso propio = 1, que habría duplicado la masa sísmica— (R05), y con la losa
`Slab1` (R10). **Leer la tabla y contar**, siempre.

## Parámetros normativos ya fijados (no recalcular)

| Parámetro | Valor | Fuente CDCRD |
|---|---|---|
| Fa | 1.180 | cl. 2.9.2, Tabla 7, T1 p.44 |
| Fv | 1.550 | cl. 2.9.2, Tabla 8, T1 p.44 |
| SDS | 0.4877 g | cl. 2.9.4, Ec. 7 |
| SD1 | 0.2583 g | cl. 2.9.4, Ec. 8 |
| T0 / Ts | 0.106 s / 0.530 s | cl. 2.9.4.4 |
| CDS | D | cl. 2.9.5, Tablas 9-10 |
| Sistema P-4 | R=6, Ω0=3, Cd=4.25, hn=SL | cl. 2.10.2, Tabla 11, T1 p.53-58 |
| L oficinas | 2.40 kN/m² | Tabla 4, T1 p.34-36 |
| Lr techo | 0.96 kN/m² | Tabla 4, T1 p.34-36 |
| Ev | 0.2·SDS·D | cl. 2.10.6.3, Ec. 17, T1 p.71-72 |
| Δa | 0.020·hpx = 60.0 mm | cl. 2.10.11, Tabla 19, T1 p.95-96 |
| ρ (límite deriva) | **Derivas: irrelevante** — cumple con 1.0 y con 1.3 (R09). **Combinaciones: ABIERTO** — R07 asume ρ=1.0 al usar 1.0·Ex; si ρ=1.3 hay que rehacer C4x/C4y/C5x/C5y | cl. 2.10.5.1.2, T1 p.70 |
| Espesor losa | ⚠️ **el modelo tiene ≈0.197 m**, no 0.15 — las áreas quedaron con la propiedad `Slab1` por defecto de ETABS; nunca se definió una losa. Derivado de las reacciones de R10. R08–R10 corresponden a ese espesor | Sin dato del proyecto |
