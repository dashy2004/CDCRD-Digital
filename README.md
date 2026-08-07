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

Los archivos `.json` se abren con cualquier editor de texto (Bloc de notas incluido) o se
arrastran a una conversacion con una IA. Cada valor trae su clausula, tomo y pagina de origen:
**la cita para su memoria de calculo viaja con el numero**.

## Para que sirve en la practica

1. **Consultar el codigo con IA sin subir 800 paginas.** Suba solo el archivo del tema que
   necesita: la respuesta llega con articulo y pagina citados, gastando ~70 veces menos.
2. **Modelar en ETABS con ayuda de la IA.** El servidor MCP incluido conecta Claude con su
   ETABS: hoy crea y lee geometria; los parametros del codigo (cargas, espectro, R) salen de
   estos mismos archivos.
3. **Auditar sus plantillas de Excel contra el codigo nuevo.** Primer resultado real en
   `validacion/`: una plantilla profesional en uso tenia la carga de escaleras 18% por debajo
   del CDCRD 2026 (3.92 vs 4.79 kN/m2). Ese tipo de hallazgo es el objetivo del proyecto.

## Estado actual

- Texto completo: **3,492 articulos** de los 11 Titulos, con pagina de origen. (El Titulo 6,
  MHADL, esta "en desarrollo" en el propio codigo — no tiene articulos todavia.)
- Tablas listas para calculo: **8 archivos** que cubren el flujo sismico completo del Titulo 2
  (cargas -> sitio -> espectro -> categoria de diseño -> sistema estructural -> combinaciones
  -> derivas). Verificado con un caso real de punta a punta.
- Pendiente: tablas de viento, Titulos 4 y 5, y formulas en notacion matematica limpia.

Advertencia honesta: los articulos marcados `"formula": true` y `"vision_ok": false` pueden
tener simbolos corruptos heredados del PDF — no los cite sin verificar contra el original.

## Documentacion tecnica

Como se construyo, como continuarlo y el contrato de datos: `docs/TECNICO.md` y
`docs/ESQUEMA.md`. Guia de instalacion del servidor de ETABS: `instalacion/INSTALACION.md`.
