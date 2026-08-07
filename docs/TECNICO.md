# CDCRD Digital

Codigo de Construccion de la Republica Dominicana (CDCRD, julio 2026), Volumen I,
estructurado para consulta por humanos, por IA, y por herramientas de calculo
(ETABS via MCP `fea`, EstructurasRD, hojas Excel).

## Estado (2026-08-06)

| Pieza | Estado |
|---|---|
| Parseo de texto por clausula (11 titulos, 820 pags) | COMPLETO — 3,492 clausulas en `datos/titulos/` |
| Deteccion de formulas/tablas por clausula | COMPLETO — flags `formula`/`tabla` |
| Referencias externas (ACI, ASCE, AISC, AISI...) | COMPLETO — `refs.externas` por clausula |
| Capa machine (tablas listas para calculo) | 8 archivos del Titulo 2 (flujo sismico completo) |
| Pase de vision del resto de tablas (~187 clausulas con tabla) | PENDIENTE — pipeline listo |
| Formulas reconstruidas en LaTeX | PENDIENTE |
| Validacion contra hojas Excel de Emil | PENDIENTE — bloqueado: falta subirlas |

## Estructura

```
datos/titulos/T01..T11.json   capa humana: clausulas integras con paginas de origen
datos/machine/*.json          capa maquina: valores con clausula de origen
pipeline/parse_cdcrd.py       parser reproducible (pypdf, sin dependencias raras)
docs/ESQUEMA.md               contrato de datos de ambas capas
servidor-mcp/                 servidor MCP para ETABS (COM/OAPI), corregido y verificado
instalacion/INSTALACION.md    guia de instalacion battle-tested (cada aviso = un fallo real)
```

El servidor MCP conecta Claude (u otro cliente MCP) con ETABS en vivo. **54 herramientas**
que cubren geometria, materiales, secciones, apoyos, diafragmas, cargas, espectro sismico,
combinaciones, ejecucion del analisis y lectura de resultados (derivas, reacciones, modales),
mas introspeccion del typelib (`describe_oapi`) y acceso generico a tablas. La capa machine de
este repo es su complemento: los parametros del CDCRD listos para alimentar el modelo.

Probado de punta a punta contra ETABS 23.3.0 / OAPI 2.016 en `revision/` — 10 bloques con
criterio de aceptacion previo y capturas de pantalla. Limitaciones conocidas en el README.

## Capa machine disponible

| Archivo | Tabla | Clausula | Contenido |
|---|---|---|---|
| `cargas_vivas.json` | 4 | 2.7.2 | 45 usos con carga uniforme y concentrada |
| `cargas_muertas_techos.json` | — | 2.6.3/2.6.7 | pesos de terminaciones de techo y divisiones |
| `combinaciones.json` | — | 2.4.2/2.4.3 | LRFD (9) y ASD (13) completas, con regla de H |
| `sitio_clasificacion.json` | 6 | 2.9.1 | clases A-E con Vs, N, Su |
| `factores_sitio.json` | 7, 8 | 2.9.2 | Fa y Fv por clase de sitio, interpolables |
| `espectro_diseno.json` | 9, 10 | 2.9.4/2.9.5 | SMS/SM1 -> SDS/SD1, forma del espectro, CDS, campo cercano |
| `sistemas_estructurales.json` | 11 | 2.10.2 | 30 sistemas: P-1..P-8, M-1..M-14, PA-1..PA-4, D-1..D-4 (**faltan pags 57-58**) |
| `derivas_limites.json` | 19 | 2.10.11 | derivas admisibles por categoria de riesgo |

**Flujo sismico completo y calculable**: Ss/S1 (mapa) + clase de sitio -> Fa/Fv -> SMS/SM1 ->
SDS/SD1 -> CDS -> R/Omega0/Cd -> espectro Sa(T) -> combinaciones -> derivas. Verificado con
caso real (Ss=0.62, S1=0.25, sitio C): SDS=0.488, SD1=0.258, CDS=D, espectro listo para ETABS.

Cada valor lleva `fuente` con clausula, tomo y paginas: la cita legal viaja con el dato.

## Regla de confianza

- `flags.vision_ok: false` + `flags.formula: true` => las formulas de esa clausula pueden
  tener glifos corruptos del PDF; **no citar** hasta pasar vision.
- Todo archivo machine indica `metodo: vision_fable5` y fecha. La validacion cruzada contra
  las hojas Excel de calculo esta pendiente y es el siguiente candado de calidad.

## Como continuar el pase de vision

1. `python3 pipeline/parse_cdcrd.py <dir_pdfs> datos/titulos` (ya corrido)
2. Listar clausulas con `flags.tabla=true` y `vision_ok=false`
3. `pdftoppm -f <pag> -l <pag> -r 150 -png <pdf> pag_<pag>` y leer con el modelo (Fable 5)
4. Escribir el JSON machine con `fuente` completa y marcar `vision_ok`

## Pendientes de decision

- Derechos de autor: **resuelto**. Ley 65-00, art. 41: se permite reproducir leyes, decretos y
  reglamentos oficiales indicando la fuente y conforme al texto oficial. Ambas condiciones ya
  estan en el diseño (campo `fuente` + flag `vision_ok`). Viable como repo publico citando MIVHED.
- Grafo de referencias cruzadas CDCRD -> ACI/ASCE/AISC (los datos ya estan en `refs.externas`).
- Completar Tabla 11 (paginas posteriores a la 54) y parametros espectrales (2.9.5, pags 49-51).
