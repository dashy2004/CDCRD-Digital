# CDCRD-Digital

**El Codigo de Construccion de la Republica Dominicana (julio 2026), organizado para
encontrar cualquier requisito en segundos — con la pagina exacta del documento oficial.**

Los dos tomos del Volumen I suman mas de 800 paginas. Este proyecto los convierte en un
archivo por Titulo donde cada articulo del codigo aparece con su numero, su texto y la pagina
del PDF oficial de donde salio. Ademas, las tablas mas usadas del dia a dia (cargas vivas,
espectro sismico, factores R, derivas) estan listas para usarse en calculo directamente.

> Fuente oficial: MIVHED — Ministerio de la Vivienda, Habitat y Edificaciones. Este proyecto
> reproduce el texto normativo citando la fuente, conforme al articulo 41 de la Ley 65-00 de
> Derecho de Autor. No es un documento oficial: ante cualquier diferencia, manda el PDF del
> MIVHED.

## Que hay aqui (sin necesidad de programar)

| Si usted busca... | Abra... |
|---|---|
| Que dice el articulo X del codigo | `datos/titulos/` — un archivo por Titulo (T02 = Cargas, T05 = Hormigon...) |
| La carga viva de un uso (oficina, aula, parqueo...) | `datos/machine/cargas_vivas.json` — los 45 usos de la Tabla 4 |
| Los factores R, Cd y limites de altura de su sistema estructural | `datos/machine/sistemas_estructurales.json` — la Tabla 11 completa (44 sistemas) |
| Como armar el espectro de diseño de su proyecto | `datos/machine/espectro_diseno.json` + `factores_sitio.json` — paso a paso con las Tablas 7-10 |
| Las combinaciones de carga LRFD y ASD | `datos/machine/combinaciones.json` |
| Conectar la IA (Claude) directo con ETABS | `servidor-mcp/` + la guia `instalacion/INSTALACION.md` |
| Ver un edificio completo modelado y verificado por la IA, paso a paso | `revision/` — 10 bloques con capturas de pantalla de ETABS |

Los archivos `.json` se abren con cualquier editor de texto (Bloc de notas incluido) o se
arrastran a una conversacion con una IA. Cada valor trae su clausula, tomo y pagina de origen:
**la cita para su memoria de calculo viaja con el numero**.

## Para que sirve en la practica

1. **Consultar el codigo con IA sin subir 800 paginas.** Suba solo el archivo del tema que
   necesita: la respuesta llega con articulo y pagina citados, gastando ~70 veces menos.
2. **Modelar en ETABS con ayuda de la IA.** El servidor MCP incluido conecta Claude con su
   ETABS y cubre el ciclo completo: geometria, materiales, secciones, apoyos, diafragmas,
   cargas, espectro sismico, combinaciones, correr el analisis y leer derivas y reacciones.
   Los parametros del codigo (cargas por uso, espectro, R, Cd) salen de estos mismos archivos.
3. **Auditar sus plantillas de Excel contra el codigo nuevo.** Primer resultado real en
   `validacion/`: una plantilla profesional en uso tenia la carga de escaleras 18% por debajo
   del CDCRD 2026 (3.92 vs 4.79 kN/m2). Ese tipo de hallazgo es el objetivo del proyecto.

## Estado actual

- Texto completo: **3,492 articulos** de los 11 Titulos, con pagina de origen. (El Titulo 6,
  MHADL, esta "en desarrollo" en el propio codigo — no tiene articulos todavia.)
- Tablas listas para calculo: **8 archivos** que cubren el flujo sismico completo del Titulo 2
  (cargas -> sitio -> espectro -> categoria de diseño -> sistema estructural -> combinaciones
  -> derivas). Verificado con un caso real de punta a punta.
- Servidor MCP para ETABS: **54 herramientas**, probadas contra ETABS 23.3.0 / OAPI 2.016
  modelando un edificio de oficinas de punta a punta (ver `revision/`).
- Pendiente: tablas de viento, Titulos 4 y 5, y formulas en notacion matematica limpia.

Advertencia honesta: los articulos marcados `"formula": true` y `"vision_ok": false` pueden
tener simbolos corruptos heredados del PDF — no los cite sin verificar contra el original.

## El servidor MCP, probado de punta a punta

`revision/` documenta un protocolo de 10 bloques ejecutado contra un edificio real de
oficinas — 3 niveles, 2x2 crujias de 6x6 m, Santo Domingo. Cada bloque tiene su criterio de
aceptacion escrito **antes** de ejecutarlo, la respuesta de la API, y capturas de la pantalla
de ETABS que permiten cotejar el numero de la API contra el que muestra el programa.

| Bloque | Que verifica | Resultado |
|---|---|---|
| R01 | Conexion OAPI y unidades | OK |
| R02 | Geometria: 36 puntos, 63 frames, 12 areas | OK — niveles: paso manual, ver abajo |
| R03 | Materiales y secciones (H28, C50x50, V30x50) | OK — E = 2.487e7 kN/m² |
| R04 | Apoyos empotrados y diafragmas rigidos | OK — 9 apoyos, 3 diafragmas |
| R05 | Patrones de carga y asignacion a losas | OK — 12/8/4 areas segun cota |
| R06 | Espectro CDCRD y casos Ex/Ey | PARCIAL — ver limitaciones |
| R07 | Combinaciones LRFD con Ev | OK — 7 combos, factores 1.2975 / 0.8025 |
| R08 | Ejecucion del analisis | OK — T₁ = 0.358 s, masa participante 1.0 |
| R09 | Derivas contra el limite del CDCRD | OK — cumple con ρ=1.0 y con ρ=1.3 |
| R10 | Reacciones y equilibrio | OK — ΣFz cierra al 0.65% |

**33 de 34 capturas** de pantalla tomadas (`revision/RESUMEN-CAPTURAS-2026-08-08.md`). La que
falta requiere volver a correr el analisis.

### Limitaciones conocidas del servidor

Se listan porque quien vaya a usarlo las va a encontrar, y porque un README que solo cuenta lo
que funciona no sirve para decidir si adoptarlo.

- **No redefine los niveles de un modelo que ya tiene objetos.** No es un defecto del servidor:
  la OAPI lo rechaza. Se probaron `SetStories`, `SetStories_2` y la edicion por tablas, incluso
  pidiendole la configuracion que el modelo ya tenia. **Definir los niveles antes de crear la
  geometria**, o hacerlo a mano en `Edit > Stories and Grid System Data`.
- **`define_cdcrd_spectrum` falla contra esta instalacion** (`ret=-99` en `FuncRS.SetUser`, con
  la firma verificada del typelib). El rodeo funciona: escribir la funcion por la tabla
  `Functions - Response Spectrum - User Defined`. `get_spectrum` da el mismo `-99`, asi que la
  verificacion numerica del espectro depende de las capturas de R06.
- **No hay herramienta para definir secciones de area (losas).** Consecuencia real en este
  modelo: las 12 areas quedaron con `Slab1` de plantilla — 0.2032 m y material `4000Psi`, no
  los 0.15 m de H28 que el protocolo asumia. R08–R10 corresponden a ese espesor.
- **Ningun `add_*` es idempotente.** Reejecutar un bloque sobre el mismo modelo falla si el
  nombre existe, y `SetCaseList` **agrega** factores en vez de reemplazarlos.

### La regla de metodo que salio de esta corrida

El mensaje de retorno de una herramienta dice **lo que ella creo**, no **lo que hay en el
modelo**. ETABS aporta objetos por defecto que colisionan con el protocolo: aparecio con el
diafragma `D1`, con los patrones `Dead`/`Live` —y `Dead` traia peso propio = 1, que habria
duplicado la masa sismica sin ningun error visible— y con la losa `Slab1`. **Leer la tabla y
contar**, siempre. Por eso el servidor incluye lectores dedicados (`get_load_patterns`,
`get_materials`, `get_area_sections`, `get_diaphragms`...) y no solo escritores.

## Documentacion tecnica

Como se construyo, como continuarlo y el contrato de datos: `docs/TECNICO.md` y
`docs/ESQUEMA.md`. Guia de instalacion del servidor de ETABS: `instalacion/INSTALACION.md`.
Gotchas verificados del API (semántica real de `set_table_data`, filtros por elevación,
timeouts de `run_analysis`) con causa raíz y regla: `servidor-mcp/ERRORES.md`.
