<h1 align="center">CDCRD-Digital</h1>
<p align="center"><strong>Normativa trazable · Automatización BIM · Evidencia de ingeniería</strong></p>

<p align="center">
  <a href="#instalación-y-paquetes"><img src="docs/assets/nav/instalar.svg" alt="INSTALAR" height="34"></a>
  <a href="servidor-mcp-civil3d/README.md"><img src="docs/assets/nav/civil3d.svg" alt="CIVIL 3D" height="34"></a>
  <a href="#civil-3d-resultados-reproducibles"><img src="docs/assets/nav/galeria.svg" alt="CAPTURAS" height="34"></a>
  <a href="datos/INDICE.md"><img src="docs/assets/nav/normativa.svg" alt="NORMATIVA" height="34"></a>
  <a href="#documentacion-tecnica"><img src="docs/assets/nav/docs.svg" alt="DOCUMENTACIÓN" height="34"></a>
</p>

<p align="center">
  <a href="https://github.com/dashy2004/CDCRD-Digital/actions/workflows/verify.yml"><img src="https://github.com/dashy2004/CDCRD-Digital/actions/workflows/verify.yml/badge.svg" alt="Verificaciones del repositorio"></a>
  <a href="datos/INDICE.md"><img src="https://img.shields.io/badge/CDCRD-5_volúmenes_·_6%2C580_cláusulas-176349" alt="Normativa: 5 volúmenes y 6,580 cláusulas"></a>
  <a href="servidor-mcp-civil3d/docs/QTO-0522.md"><img src="https://img.shields.io/badge/Civil_3D-entrega_0.5.22-165c85" alt="Civil 3D: entrega 0.5.22"></a>
</p>

[![Verificación del repositorio](https://github.com/dashy2004/CDCRD-Digital/actions/workflows/verify.yml/badge.svg?branch=master)](https://github.com/dashy2004/CDCRD-Digital/actions/workflows/verify.yml)
[![Licencia Apache 2.0](https://img.shields.io/badge/licencia-Apache%202.0-blue.svg)](LICENSE)
[![Última versión](https://img.shields.io/github/v/release/dashy2004/CDCRD-Digital?include_prereleases&label=versi%C3%B3n&color=informational)](https://github.com/dashy2004/CDCRD-Digital/releases)
[![Último commit en master](https://img.shields.io/github/last-commit/dashy2004/CDCRD-Digital/master?label=%C3%BAltimo%20commit)](https://github.com/dashy2004/CDCRD-Digital/commits/master)
[![Python 3.11 a 3.13](https://img.shields.io/badge/python-3.11%20%E2%80%93%203.13-3776AB.svg?logo=python&logoColor=white)](herramientas-locales/pyproject.toml)
[![Citar este repositorio](https://img.shields.io/badge/citar-CITATION.cff-6f42c1.svg)](CITATION.cff)

[![CDCRD Digital: normativa trazable y APIs para Revit, ETABS, SAFE, Civil 3D y AutoCAD](docs/assets/banner-cdcrd-digital.png)](https://www.canva.com/design/DAHYTip4pJ8/Cw9S-5IRfy_MZrj0EXIeaA/edit)

**Consulta el Código de Construcción de la República Dominicana con referencia a su página
de origen y conecta sus datos con flujos de trabajo en Revit, ETABS, SAFE, Civil 3D y AutoCAD.**

El proyecto reúne **5 volúmenes, 34 títulos y 6,580 cláusulas**, tablas listas para cálculo,
herramientas MCP y revisiones documentadas. Su propósito es hacer que cada decisión pueda
rastrearse desde la fuente normativa hasta los datos y la evidencia del modelo.

[Explorar la norma](datos/INDICE.md) · [Instalar el servidor MCP de Civil 3D](#instalar-el-servidor-mcp-de-civil-3d-2027) ·
[Civil 3D a BeamNG.drive](#instalar-el-puente-de-civil-3d-a-beamngdrive) · [Herramientas](#los-servidores-mcp) ·
[Ejemplos](#ejemplos-de-herramientas) · [Contribuir](CONTRIBUTING.md)

| Capa | Qué aporta | Punto de entrada |
|---|---|---|
| **Normativa** | Cláusulas, tablas y referencias al PDF oficial | [Índice del código](datos/INDICE.md) |
| **BIM y cálculo** | Lectura, modelado y documentación mediante herramientas especializadas | [Arquitectura del ecosistema](docs/ARQUITECTURA-ECOSISTEMA.md) |
| **Verificación** | Evidencia, hallazgos y límites de cada caso | [Ejemplo de revisión BIM](docs/ejemplos/revision-bim.md) |

La cobertura del texto normativo y la disponibilidad de herramientas son distintas de la
verificación de un proyecto. Cada informe identifica qué se comprobó y qué evidencia falta.

> Fuente oficial: MIVHED — Ministerio de la Vivienda, Habitat y Edificaciones. Este proyecto
> reproduce el texto normativo citando la fuente, conforme al articulo 41 de la Ley 65-00 de
> Derecho de Autor. No es un documento oficial: ante cualquier diferencia, manda el PDF del
> MIVHED.

## Constructoras que confían en este programa

**Guillen Rosa & Associados**

## Civil 3D y AutoCAD: capturas y pruebas nativas

[Civil 3D 0.5.22: cubicaciones y QTO por API — volumen TIN y materiales por secciones, cinco capturas reales](servidor-mcp-civil3d/docs/QTO-0522.md).

[Civil 3D 0.5.21: targets de ancho y cota en un corredor nuevo — 8 asignaciones, 74 muestras de carril, 8 secciones](servidor-mcp-civil3d/docs/TARGETS-0521.md).

[Civil 3D 0.5.20: corredores con varios baselines y regiones, secciones nativas](servidor-mcp-civil3d/docs/MULTIBASELINE-0520.md).

[Civil 3D 0.5.19: espirales clotoide espiral-curva-espiral con evidencia de corredor](servidor-mcp-civil3d/docs/ESPIRALES-0519.md).

[Civil 3D 0.5.18: tablas de peralte explícitas con evidencia nativa](servidor-mcp-civil3d/docs/PERALTES-0518.md).

[Civil 3D 0.5.17: cunetas, bermas y secciones — 70 comprobaciones nativas y capturas crudas](servidor-mcp-civil3d/docs/CUNETAS-BERMAS-0517.md).

[Civil 3D 0.5.16: calzada con capas, targets y daylight — capturas crudas](servidor-mcp-civil3d/docs/CALZADA-0516.md).

[Civil 3D 0.5.15: ensamblaje, corredor y secciones — capturas crudas](servidor-mcp-civil3d/docs/CORREDOR-0515.md).

[Civil 3D 0.5.14: arcos y curvas verticales — capturas crudas](servidor-mcp-civil3d/docs/CURVAS-0514.md).

[Civil 3D 0.5.13: feature lines y plataforma — capturas crudas](servidor-mcp-civil3d/docs/PLATAFORMAS-0513.md).

[Civil 3D 0.5.12: parcela, eje y rasante — capturas crudas](servidor-mcp-civil3d/docs/SITIO-0512.md).

[Ver las capturas crudas y resultados de Civil 3D 0.5.11](servidor-mcp-civil3d/docs/CIERRE-0511.md) · [Perfil de sondeos y recuperación](servidor-mcp-civil3d/docs/RECUPERACION-GM-059.md) · [Adaptación común para AutoCAD](servidor-mcp-civil3d/docs/AUTOCAD-0511.md).

![Superficies y fondo en Civil 3D, captura nativa sin retoque](servidor-mcp-civil3d/docs/images/gm-surfaces-bottom-0511.png)

Pruebas sobre copias y datos hipotéticos. Capturas del área de dibujo; cada informe separa lo comprobado de lo pendiente.

## Que hay aqui (sin necesidad de programar)

| Si usted busca... | Abra... |
|---|---|
| Por donde empezar cualquier busqueda | [datos/INDICE.md](datos/INDICE.md) — mapa de los 5 volumenes, **6,580 clausulas** |
| Que dice la clausula X del Volumen I (estructural) | `datos/titulos/` — un archivo por Titulo (T02 = Cargas, T05 = Hormigon...) |
| Hidrosanitaria, electrica, mecanica o arquitectura (Vols II-V) | `datos/vol-2/` a `datos/vol-5/` (JSON) o `md/` (legible aqui mismo en GitHub) |
| La carga viva de un uso (oficina, aula, parqueo...) | `datos/machine/cargas_vivas.json` — los 45 usos de la Tabla 4 |
| Los factores R, Cd y limites de altura de su sistema | `datos/machine/sistemas_estructurales.json` — la Tabla 11 completa (44 sistemas) |
| Como armar el espectro de diseño de su proyecto | `datos/machine/espectro_diseno.json` + `factores_sitio.json` |
| Las combinaciones de carga LRFD y ASD | `datos/machine/combinaciones.json` |
| Conectar la IA con ETABS, SAFE o Revit | [ETABS](servidor-mcp/), [SAFE](servidor-mcp-safe/), [Revit](revit-mcp-tools/) + [instalacion](instalacion/INSTALACION.md) |
| Conectar la IA con Civil 3D 2027 | [Civil 3D](servidor-mcp-civil3d/) — puente .NET 10 propio, alineamientos, corredores, superficies, redes, planos |
| Que la IA modele un edificio en Revit desde cero y saque planos | `revit-mcp-tools/ejemplos/residencial-4n/` — receta de 30 pasos, corrida verificada |
| Un edificio completo modelado y verificado por IA, paso a paso | `revision/` — 10 bloques con capturas de pantalla de ETABS |
| Como se verifico la digitalizacion | `verificacion-vols/` |
| Reglamentos R-001, R-002, R-008, carreteras, geotecnia e INAPA | [Corpus complementario](corpus-reglamentos/README.md) — 12 documentos, 1.370 páginas, texto/OCR con referencia; revisión numérica pendiente |
| Generar DXF, convertir previews, revisar IFC/IDS y consultar CDCRD localmente | [herramientas-locales/](herramientas-locales/README.md) — CLI, entorno reproducible y MCP de 12 herramientas |
| Validar fuentes Civil 3D → BeamNG antes de convertir | [Validador de intercambios](civil3d-beamng/docs/VALIDACION-INTERCAMBIOS.md) — unidades, coordenadas, IDs y referencias; JSON sin activar aplicaciones |
| Recorrer en BeamNG.drive una carretera diseñada en Civil 3D | [Puente Civil 3D → BeamNG.drive](instalacion/BEAMNG-DRIVE.md) — exporta terreno y calzada a un nivel propio del juego; sin IA ni MCP; [instalación copiar y pegar](#instalar-el-puente-de-civil-3d-a-beamngdrive) |

Los `.json` se abren con cualquier editor de texto (Bloc de notas incluido) o se arrastran a
una conversacion con una IA. Cada valor trae su clausula, tomo y pagina de origen: **la cita
para su memoria de calculo viaja con el numero**.

## Cobertura de la capa normativa

| Vol | Contenido | Clausulas | Titulos |
|---|---|---|---|
| I | Estructural (cargas, suelos, hormigon, acero, madera, mamposteria...) | 3,492 | 11 |
| II | Instalaciones Hidrosanitarias | 465 | 8 |
| III | Instalaciones Electricas | 497 | 1 |
| IV | Instalaciones Mecanicas | 976 | 8 |
| V | Diseño Arquitectonico | 1,150 | 6 |
| | **Total** | **6,580** | **34** |

El Titulo 6 del Vol I (MHADL) figura "en desarrollo" en el propio codigo: no tiene clausulas.

**Como se verifico** (`verificacion-vols/`): el parser es determinista, sin IA en el camino
critico. El Vol I se volvio a procesar con el codigo nuevo y salio **bit a bit identico** al
que ya estaba en el repo, lo que descarta regresiones. El texto huerfano previo a la primera
clausula es de 28 a 106 caracteres por volumen (portadillas): todo lo demas queda asignado.
El muestreo se hizo contra la pagina renderizada a 110 dpi, no contra la extraccion.

Un hallazgo del metodo, por si sirve a quien digitalice normas: **la numeracion impresa no es
jerarquia confiable** — hay ids duplicados en el documento oficial —, asi que el Titulo se
asigna por posicion en el documento, no por el prefijo del id.

## Para que sirve en la practica

1. **Consultar el codigo con IA sin subir 1,800 paginas.** Suba solo el archivo del tema que
   necesita: la respuesta llega con clausula y pagina citadas, gastando ~70 veces menos.
2. **Modelar y diseñar con ayuda de la IA.** Los servidores MCP cubren el ciclo: geometria,
   materiales, secciones, apoyos, diafragmas, cargas, espectro, combinaciones, correr el
   analisis y leer derivas, reacciones y resultados de diseño. Los parametros del codigo
   (cargas por uso, espectro, R, Cd) salen de estos mismos archivos.
3. **Auditar sus plantillas de Excel contra el codigo nuevo.** Primer resultado real en
   `validacion/`: una plantilla profesional en uso tenia la carga de escaleras **18% por
   debajo** del CDCRD (3.92 vs 4.79 kN/m²). Ese tipo de hallazgo es el objetivo del proyecto.
4. **Levantar un modelo BIM completo en Revit desde una descripcion.** `revit-mcp-tools`
   cubre niveles y ejes, tipos, columnas, vigas, losas, muros, zapatas,
   plantas, tablas, laminas, PDF, IFC y la exportacion a `proyecto.json` para ETABS. Cada
   herramienta de escritura simula primero (`dry_run`), marca lo que crea para poder
   deshacerlo, y la salida grafica se exporta a PNG para que la IA la **mire** antes de
   entregarla. El ejemplo `ejemplos/residencial-4n` (edificio de 4 niveles y 8
   apartamentos, nombres inventados) corre de punta a punta en ~15 s.

## Civil 3D: resultados reproducibles

Una galería con el mismo formato permite ver **qué hace cada herramienta, qué se
probó y cómo repetirlo**. Todos estos ejemplos usan geometría ficticia.

### Puntos COGO y Survey

[Guía y ejemplos](civil3d-points-survey/README.md) ·
[Entradas y resultados](civil3d-points-survey/docs/VALIDACION.md)

| Inventario y exportación | Importación COGO |
|---|---|
| ![Inventario de puntos](civil3d-points-survey/docs/images/audit.png) | ![Importación de puntos](civil3d-points-survey/docs/images/import.png) |
| Coordenadas y descripciones para comparar antes/después. | 12 puntos ficticios en un dibujo vacío, en metros. |

| Grupos de puntos | Survey y persistencia |
|---|---|
| ![Grupo TN](civil3d-points-survey/docs/images/group.png) | ![Base Survey](civil3d-points-survey/docs/images/survey.png) |
| Selección explícita de seis puntos de terreno. | Base separada; coordenadas importadas, sin observaciones de campo. |

![Verificación de COGO y Survey](civil3d-points-survey/docs/images/survey-read.png)

Relectura, comparación de coordenadas y controles tras guardar y reabrir.

### Superficies, taludes y secciones

[Instalación y API](civil3d-terrain-tools/README.md) ·
[Verificaciones nativas](civil3d-terrain-tools/docs/VALIDACION.md)

| Excavación | Relleno |
|---|---|
| ![Excavación con taludes](civil3d-terrain-tools/docs/images/excavacion.png) | ![Plataforma de relleno](civil3d-terrain-tools/docs/images/relleno.png) |
| Corte verificado: 276 m³. | Relleno verificado: 276 m³. |

| Caso mixto | Secciones |
|---|---|
| ![Corte y relleno](civil3d-terrain-tools/docs/images/mixta.png) | ![Secciones nativas](civil3d-terrain-tools/docs/images/secciones.png) |
| Corte y relleno separados: 6,444444 m³ cada uno. | Muestreo nativo y comparación con el volumen TIN. |

![Comparación de volúmenes y secciones](civil3d-terrain-tools/docs/images/verificacion.png)

**Pendiente de cierre en terreno:** los valores numéricos de R2 están comparados,
pero falta verificar por separado las unidades de Civil y de las etiquetas de su
demostración histórica. INSUNITS por sí solo no basta; véase la
[limitación de unidades](civil3d-terrain-tools/docs/VALIDACION.md#comprobación-de-unidades-pendiente-en-la-demostración-r2).

Las imágenes identifican su origen: exportación nativa del modelo o informe de
lecturas de la API. No se presentan como capturas de escritorio. Civil 3D 2027 es
la versión probada; cada módulo documenta sus límites.

## Usarlo con Claude o Codex

[Guía para el ingeniero y prompt de prueba](docs/TRABAJAR-CON-IA.md).
Puede pedir a cualquiera de los dos asistentes que prepare un ejemplo, muestre
los supuestos y compare los resultados. Las herramientas también tienen un
procedimiento manual reproducible.

## Conservar la normativa revisada

[Estado y propuesta de protección](docs/PROTECCION-NORMATIVA.md): manifiesto de
111 archivos, verificador local, CI de GitHub activa (desde 2026-10-21) y
responsables de revisión. La protección de rama de `master` aún no está
activada. Tampoco cambian las marcas
de fórmulas/tablas pendientes de cotejo.

## Los servidores MCP

| Servidor | Que opera | Estado |
|---|---|---|
| `herramientas-locales/` | Archivos DXF/IFC/IDS/PDF y corpus CDCRD, sin aplicaciones BIM vivas | CLI y **12 herramientas MCP stdio**, entorno Python aislado; [instalacion y ejemplos](herramientas-locales/README.md) |
| `servidor-mcp/` | ETABS (OAPI 2.016) | Herramientas OAPI con pruebas sintéticas en ETABS 23.3.0: [evidencia y límites](servidor-mcp/docs/VALIDACION-ETABS.md). Ocho herramientas adicionales de [procedimiento, cargas y revisión de acero](servidor-mcp/docs/PROCEDIMIENTO-ETABS.md) trabajan con entradas explícitas, sin modificar el modelo. Dos herramientas de [captura e informe del auditor](servidor-mcp/docs/AUDITOR-ETABS.md) agregan lectura por PID/EDB e informes HTML/JSON; pruebas sintéticas completas, aceptación nativa pendiente. Despiece integral e historia no lineal directa pendientes. |
| `servidor-mcp-safe/` | SAFE — losas, zapatas, franjas, punzonamiento, presion de suelo | v0.1.0, probado en vivo contra un modelo real de fundacion |
| [revit-mcp-tools/](revit-mcp-tools/README.md) | Revit 2027 via pyRevit Routes — modelar, documentar, armado, exportacion a ETABS y auditoría MEP de solo lectura | Modelado y documentacion probados en la receta `residencial-4n`; [alcance y validación MEP](revit-mcp-tools/MEP.md) |
| `revit-mcp-write/` | Revit 2027 via pyRevit Routes — lectura e inventario, y escritura (pushbuttons) | 9 herramientas; las tres que **mutan** el modelo aun sin corridas reales |
| `servidor-mcp-civil3d/` | Civil 3D 2027 (serie R26.0) via puente .NET 10 propio en el proceso | v0.5.22, **85 herramientas**; lectura y escritura **probadas en vivo** sobre copias sinteticas: sitio, plataformas, curvas, corredor, secciones, calzada con capas/targets/daylight, cunetas y bermas, peraltes, espirales, varios baselines, targets de ancho y cota y cubicaciones/QTO ([ultima evidencia](servidor-mcp-civil3d/docs/QTO-0522.md)); [como instalarlo](#instalar-el-servidor-mcp-de-civil-3d-2027) |
| `corpus-inapa/` | Reglamento Tecnico INAPA DIG-PO-001 (2018) por pagina, con pagina impresa, estructura, hash y fuente; busqueda FTS5 y referencias `norma` vs `hipotesis` | corpus generado (414 pag.), 21 pruebas sinteticas; OCR sin revision humana |
| `puente-autocad-etabs/` | Extraccion de geometria desde DWG por convencion de capas | Inventario y convencion definidos (`docs/CONVENCION-CAPAS-CAD.md`) |

Como encajan entre si: [arquitectura del ecosistema](docs/ARQUITECTURA-ECOSISTEMA.md).
Capacidades pendientes y su estado: [huecos ETABS/SAFE](docs/HUECOS-ETABS-SAFE.md).

## Ejemplos de herramientas

### Revisión BIM y auditoría MEP

[**Recorrer el ejemplo sintético de revisión BIM →**](docs/ejemplos/revision-bim.md)

Un flujo didáctico muestra cómo reunir archivos por disciplina, leer el inventario,
examinar conectividad y registrar observaciones con evidencia. Sus entradas son ficticias;
no contiene datos, imágenes ni resultados de un proyecto en desarrollo.

| Ejemplo | Qué permite aprender |
|---|---|
| [Revisión BIM sintética](docs/ejemplos/revision-bim.md) | Separar cobertura de modelos, hallazgos y criterios pendientes |
| [Auditoría MEP](revit-mcp-tools/MEP.md) | Inventariar categorías/sistemas y revisar conectores físicos abiertos |
| [Revit residencial de cuatro niveles](revit-mcp-tools/ejemplos/residencial-4n/) | Seguir una receta de modelado y documentación |
| [Planta CAD sintética](herramientas-locales/README.md#ejemplo-de-plano-reproducible) | Generar DXF, inspeccionarlo y producir vistas previas |
| [Esquemas DXF de secciones y pórtico](herramientas-locales/ejemplos/secciones-dxf/README.md) | Dibujar secciones acotadas y un pórtico tipo por código, con capas y cotas nativas |

El inventario y la conectividad ayudan a localizar omisiones; no sustituyen el cálculo de
caudales, cargas, ventilación, protección contra incendios ni una revisión normativa completa.
El estado de las pruebas de cada herramienta está documentado en su módulo.

### Esquemas DXF: secciones y pórtico

[Ejemplo y parámetros](herramientas-locales/ejemplos/secciones-dxf/README.md) ·
[Operaciones de la CLI](herramientas-locales/README.md#ejemplo-de-plano-reproducible)

Cuatro archivos `.dxf` generados por código y abiertos después en CAD. Unidades
en centímetros, capas separadas y cotas nativas. Geometría ficticia.

| Sección 35 × 35 | Sección 40 × 40 |
|---|---|
| <picture><source media="(prefers-color-scheme: dark)" srcset="herramientas-locales/docs/images/seccion-c1-dark.png"><img alt="Sección de columna 35 x 35 con 12 barras No. 6" height="430" src="herramientas-locales/docs/images/seccion-c1.png"></picture> | <picture><source media="(prefers-color-scheme: dark)" srcset="herramientas-locales/docs/images/seccion-c2-dark.png"><img alt="Sección de columna 40 x 40 con 14 barras No. 6" height="430" src="herramientas-locales/docs/images/seccion-c2.png"></picture> |
| 12 barras No. 6; estribo No. 3 dibujado con su espesor. | 14 barras No. 6; separaciones acotadas a ejes de barra. |

| Sección 40 × 45 | Pórtico tipo |
|---|---|
| <picture><source media="(prefers-color-scheme: dark)" srcset="herramientas-locales/docs/images/seccion-c3-dark.png"><img alt="Sección de columna 40 x 45 con 16 barras No. 6" height="430" src="herramientas-locales/docs/images/seccion-c3.png"></picture> | <picture><source media="(prefers-color-scheme: dark)" srcset="herramientas-locales/docs/images/portico-tipo-dark.png"><img alt="Pórtico tipo de tres niveles de 310 cm" height="430" src="herramientas-locales/docs/images/portico-tipo.png"></picture> |
| 16 barras No. 6; dobleces redondeados y gancho a 135°. | Tres niveles de 310 cm con empotramientos y cotas. |

Son vistas directas de esos `.dxf`, sin rótulos ni montaje añadidos; cada una se
sirve en versión clara u oscura según el tema de quien lee. El ejemplo produce
esquemas acotados: no incluye cajetín, láminas de presentación ni despiece de
armadura, y no sustituye cálculo ni verificación normativa.

### Demostración ETABS — oficinas de tres niveles

**Demostración de herramientas.** El protocolo existente permite seguir la
geometría, las cargas, el análisis y la lectura de resultados de una demostración controlada.

| Recorrido visual y técnico | Evidencia existente |
|---|---|
| Geometría y secciones | [R02 · Geometría](revision/R02-geometria-niveles/README.md) / [R03 · Materiales y secciones](revision/R03-materiales-secciones/README.md) |
| Espectro y análisis | [R06 · Espectro](revision/R06-sismo-espectro/README.md) / [R08 · Análisis](revision/R08-analisis/README.md) |
| Derivas y equilibrio | [R09 · Derivas](revision/R09-derivas/README.md) / [R10 · Reacciones](revision/R10-reacciones/README.md) |

Las capturas históricas se consultan dentro de su protocolo. Los ejemplos visuales nuevos
deben seguir el [criterio de presentación y evidencia](docs/PRESENTACION.md).

<details>
<summary>Consultar el informe detallado de pruebas ETABS y pendientes normativos</summary>

## El servidor de ETABS, probado de punta a punta

`revision/` documenta un protocolo de 10 bloques ejecutado contra un edificio de oficinas de
3 niveles, 2x2 crujias de 6x6 m. Cada bloque tiene su criterio de aceptacion escrito **antes**
de ejecutarlo, la respuesta de la API, y capturas de la pantalla de ETABS que permiten cotejar
el numero de la API contra el que muestra el programa.

| Bloque | Que verifica | Resultado |
|---|---|---|
| R01 | Conexion OAPI y unidades | OK |
| R02 | Geometria: 36 puntos, 63 frames, 12 areas | OK — niveles: paso manual, ver abajo |
| R03 | Materiales y secciones | OK — E = 2.487e7 kN/m² |
| R04 | Apoyos empotrados y diafragmas rigidos | OK — 9 apoyos, 3 diafragmas |
| R05 | Patrones de carga y asignacion a losas | OK — 12/8/4 areas segun cota |
| R06 | Espectro CDCRD y casos Ex/Ey | PARCIAL — ver limitaciones |
| R07 | Combinaciones LRFD con Ev | OK — 7 combos, factores 1.2975 / 0.8025 |
| R08 | Ejecucion del analisis | OK — T₁ = 0.358 s, masa participante 1.0 |
| R09 | Derivas contra el limite del CDCRD | OK — cumple con ρ=1.0 y con ρ=1.3 |
| R10 | Reacciones y equilibrio | OK — ΣFz cierra al 0.65% |

**33 de 34 capturas** tomadas (`revision/RESUMEN-CAPTURAS-2026-08-08.md`).

Despues del protocolo se corrio un caso de mayor escala (**TORRE A**, 51 niveles, 224 m,
4,529 objetos cargados por API en un modelo en blanco): la clasificacion automatica de ETABS
cuadro grupo por grupo con el dataset y los nudos coincidieron exactos a 1 mm. El equilibrio
cerro al **−0.24%**. Ese ejercicio destapo dos desconexiones de geometria que el dataset de
origen escondia y que se manifestaron como autovalores negativos: util como recordatorio de
que **el analisis es tambien un control de calidad del modelo**, no solo un resultado.

### Limitaciones conocidas

Se listan porque quien vaya a usarlo las va a encontrar, y porque un README que solo cuenta lo
que funciona no sirve para decidir si adoptarlo.

- **No redefine los niveles de un modelo que ya tiene objetos.** No es un defecto del servidor:
  la OAPI lo rechaza. **Definir los niveles antes de crear la geometria**, o hacerlo a mano en
  `Edit > Stories and Grid System Data`.
- **`define_cdcrd_spectrum` fallaba con `ret=-99`** en instalaciones donde `FuncRS.SetUser` no
  responde; el rodeo es escribir la funcion por la tabla `Functions - Response Spectrum - User
  Defined`. En el caso de 51 niveles la herramienta **si funciono** y `get_spectrum` releyo los
  12 puntos, que verifican contra el calculo manual.
- **Ningun `add_*` es idempotente.** Reejecutar un bloque sobre el mismo modelo falla si el
  nombre existe, y `SetCaseList` **agrega** factores en vez de reemplazarlos.
- **Tablas de diseño por API**: los lectores de columnas y juntas funcionan; el de vigas
  requirio corregir la firma (23 arrays, no 22).

### La regla de metodo que salio de estas corridas

El mensaje de retorno de una herramienta dice **lo que ella creo**, no **lo que hay en el
modelo**. ETABS aporta objetos por defecto que colisionan con el protocolo: aparecio con el
diafragma `D1`, con los patrones `Dead`/`Live` —y `Dead` traia peso propio = 1, que habria
duplicado la masa sismica sin ningun error visible— y con la losa `Slab1`. **Leer la tabla y
contar**, siempre. Por eso los servidores incluyen lectores dedicados (`get_load_patterns`,
`get_materials`, `get_area_sections`, `get_diaphragms`...) y no solo escritores.

La misma regla, en el puente Revit → ETABS: **un export a CSV es una proyeccion con perdida**.
Cruzando el CSV contra la API del modelo abierto aparecieron un tipo cuyo nombre mentia sobre
su geometria, y vigas que el export omitia por completo. Si el modelo origen esta abierto,
verificar contra su API antes de modelar.

## Estado y pendientes

- Capa normativa: **6,580 clausulas** en los 5 volumenes, con espejo legible en `md/`.
- Tablas listas para calculo: **8 archivos** que cubren el flujo sismico completo del Titulo 2
  (cargas → sitio → espectro → categoria de diseño → sistema → combinaciones → derivas).
- Pendiente: tablas de viento; pase de vision sobre tablas y formulas de los Vols II-V;
  formulas en notacion matematica limpia.

Advertencia honesta: las clausulas marcadas `"formula": true` y `"vision_ok": false` pueden
tener simbolos corruptos heredados del PDF — **no las cite sin verificar contra el original**.

</details>

## Politica de datos

Este es un repositorio **publico** y su contenido es la norma (publica) y las herramientas.
Los ejemplos utilizan nombres inventados y datos sintéticos. Los modelos, planos, informes,
miniaturas, memorias y resultados de proyectos en desarrollo permanecen fuera del repositorio,
aunque se hayan anonimizado. Tampoco se publican nombres de clientes, rutas personales ni
credenciales. Las salidas de corrida de los scripts (`_log/`), que contienen ids y geometría
del modelo abierto, están excluidas por `.gitignore`. Véase el
[criterio de publicación](docs/PRESENTACION.md).

## Documentacion tecnica

| Documento | Contenido |
|---|---|
| [Guía técnica](docs/TECNICO.md) | Construcción del corpus y continuidad del proyecto |
| [Esquema normativo](docs/ESQUEMA.md) | Contrato de los datos del código |
| [Esquema de proyecto](docs/ESQUEMA-PROYECTO.md) | Contrato de `proyecto.json` |
| [Instalación de servidores](instalacion/INSTALACION.md) | Conexión con las aplicaciones |
| [Hallazgos del API ETABS](servidor-mcp/ERRORES.md) | Causas y soluciones documentadas para tablas, filtros y análisis |
| [ETABS + REA: primera etapa](servidor-mcp/docs/REA-ETABS-FASE1.md) | Catálogo estático de 4.861 firmas CSI, desplazamientos y lectura de derivas por contrato; validación viva pendiente |

## Instalación y paquetes

Todo se instala en **Windows, desde PowerShell, sin privilegios de administrador**.
Cada bloque de esta sección se copia y se pega tal cual en la terminal; los comandos
que necesitan una ruta suya la llevan marcada en el ejemplo. Lo que exige programas
de pago (ETABS, SAFE, Revit, Civil 3D, BeamNG.drive) se instala solo donde esos
programas existen; el corpus normativo y las herramientas locales funcionan en
cualquier equipo.

[Requisitos](#requisitos-solo-si-faltan) ·
[Tres comandos](#descargar-e-instalar-en-tres-comandos) ·
[Civil 3D 2027](#instalar-el-servidor-mcp-de-civil-3d-2027) ·
[Civil 3D a BeamNG.drive](#instalar-el-puente-de-civil-3d-a-beamngdrive) ·
[Manual](#instalación-manual-paso-a-paso) · [Fallos frecuentes](#fallos-frecuentes-y-su-causa-real)

### Requisitos (solo si faltan)

Git, Python de 64 bits y `uv`. Si ya los tiene, salte al siguiente bloque. Con
`winget` (viene con Windows 10/11):

```powershell
winget install --id Git.Git -e
winget install --id Python.Python.3.13 -e
winget install --id astral-sh.uv -e
```

Cierre y vuelva a abrir PowerShell para que tome el PATH nuevo. Compruebe:

```powershell
git --version
py -c "import sys,struct; print(sys.version.split()[0], struct.calcsize('P')*8, 'bits')"
uv --version
```

Python debe decir `64 bits`. Si en vez de eso aparece `Python was not found; run
without arguments to install from the Microsoft Store`, es el alias de la Tienda:
desactívelo en Configuración → Aplicaciones → Alias de ejecución de aplicaciones.

### Descargar e instalar en tres comandos

```powershell
git clone https://github.com/dashy2004/CDCRD-Digital.git
cd CDCRD-Digital
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar-cdcrd.ps1
```

Sin git: botón verde **Code → Download ZIP**, descomprima, abra la carpeta, clic
derecho en un espacio vacío → **Abrir en Terminal** y pegue solo el tercer comando.

```
   ####  ####   ####  ####   ####
  ##     ##  ## ##     ##  ## ##  ##
  ##     ##  ## ##     ####   ##  ##
  ##     ##  ## ##     ##  ## ##  ##
   ####  ####   ####  ##  ## ####

  1  Ver que hay en este equipo (diagnostico)
  2  Instalar las herramientas locales
  3  Conectar ETABS, SAFE, Revit y Civil 3D
  4  Comprobar el corpus normativo
  5  Configurar mi asistente de IA
  6  Instalarlo todo de una vez
  7  Preguntas frecuentes
  0  Salir
```

Empiece por la **1** para ver qué detecta y siga con la **6**. El menú detecta qué
hay en el equipo (Python, `uv`, git, ETABS, SAFE, Revit, Civil 3D y qué asistente de
IA tiene instalado), instala solo lo que falta y escribe la configuración de su
asistente **sin borrar lo que ya tuviera**. No descarga programas por su cuenta y
respalda cada archivo antes de tocarlo.

**Sin menú, todo de una vez** (lo mismo que la opción 6):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar-cdcrd.ps1 -Accion todo
```

Para elegir qué asistentes configurar: `-Cliente claude-desktop,claude-code,codex,cursor,vscode`
(uno o varios, separados por coma). `-Json` imprime el resultado para que lo lea un script o una IA.

**Comprobar que funciona**, sin tener ningún programa BIM instalado:

```powershell
.\herramientas-locales\cdcrd.ps1 doctor
.\herramientas-locales\cdcrd.ps1 buscar "carga viva" --limite 3
```

Después cierre el asistente **desde el icono de la bandeja del sistema** (clic
derecho → Quit) y vuelva a abrirlo: cerrar la ventana no reinicia el proceso y las
herramientas no aparecen.

**Ya lo tenía descargado:** entre a la carpeta, actualice y repita el instalador.

```powershell
git pull
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar-cdcrd.ps1 -Accion todo
```

¿Prefiere que lo haga su asistente? Pásele el enlace de este repositorio y
pídale que siga [INSTALAR-CON-IA.md](INSTALAR-CON-IA.md): ahí están los mismos
pasos sin menú (`-Accion diagnostico|locales|bim|clientes|todo`, con `-Json`),
los archivos de configuración de Claude Desktop, Claude Code, Codex, Cursor y
VS Code, y los fallos conocidos con su causa real.

### Instalar el servidor MCP de Civil 3D 2027

Conecta la IA con el **dibujo abierto** en Civil 3D 2027: alineamientos,
perfiles, corredores, superficies, redes, secciones y cubicaciones. Son dos piezas:
un servidor MCP en Python (lo instala y registra el menú anterior cuando detecta
Civil 3D) y un **puente .NET 10 que corre dentro de Civil 3D** y que hay que
compilar una vez en su equipo, porque las DLL de Autodesk se referencian desde su
instalación y no se redistribuyen. Esta parte **no la hace el menú**; son los
comandos de abajo.

**Requisitos:** Civil 3D 2027 (serie R26.0) en Windows x64 y el **SDK de .NET 10**.
El *runtime* 10 llega con Civil 3D; el SDK no, y el runtime solo no alcanza.

```powershell
winget install --id Microsoft.DotNet.SDK.10 -e
dotnet --list-sdks
```

Debe listar una versión `10.x`. Luego, desde la raíz del repositorio:

```powershell
cd .\servidor-mcp-civil3d
py -m pip install -r requirements.txt
.\instalar.ps1
```

Si Civil 3D no está en `C:\Program Files\Autodesk\AutoCAD 2027`, indique la ruta:
`.\instalar.ps1 -Civil3DPath "D:\Autodesk\AutoCAD 2027"`.

El bundle queda en `%APPDATA%\Autodesk\ApplicationPlugins\CDCRD-Civil3D.bundle`,
que Civil 3D carga solo al arrancar: no hace falta `NETLOAD` ni Startup Suite, que la
seguridad de AutoCAD puede bloquear en silencio. **Reinicie Civil 3D**, abra un dibujo
(trabaje sobre una copia) y, si el puente no arrancó solo, escriba `CDCRDMCP` en su
línea de comandos. Compruebe desde PowerShell:

```powershell
.\instalar.ps1 -Probar
```

Debe responder el puente en `127.0.0.1:8760`. Si "nadie responde", Civil 3D no está
abierto o falta ejecutar `CDCRDMCP`. Prueba de humo completa, con un dibujo abierto:

```powershell
py src\prueba_humo.py
```

**Registrar en el asistente.** Si corrió el menú con Civil 3D instalado, la entrada
`civil3d` ya está escrita. Para hacerlo a mano (Claude Desktop) o ver el bloque JSON
que se pega en otro cliente:

```powershell
.\registrar-mcp.ps1            # muestra la entrada; no escribe nada
.\registrar-mcp.ps1 -Aplicar   # escribe con respaldo del archivo
```

**Módulos opcionales.** Cada uno compila y despliega su DLL sin abrir ni reiniciar
Civil 3D; el programa los toma en el siguiente arranque. Instale solo los que vaya a usar:

```powershell
.\instalar-peraltes.ps1      # tablas de peralte explícitas
.\instalar-espirales.ps1     # clotoides espiral-curva-espiral
.\instalar-corredores.ps1    # corredores con varios baselines y regiones
.\instalar-targets.ps1       # targets de ancho y cota
.\instalar-qto.ps1           # cubicaciones: volumen TIN y materiales por secciones
```

Solo AutoCAD 2027, sin Civil 3D: `.\instalar-autocad.ps1` despliega la adaptación
común en el puerto `8764` ([detalle](servidor-mcp-civil3d/docs/AUTOCAD-0511.md)).

**Permisos.** El puente escucha solo en `127.0.0.1`. Toda escritura exige
`confirmar=True` y un token de un solo uso ligado a esos parámetros exactos;
`CDCRD_C3D_SOLO_LECTURA=1` apaga toda escritura y `ejecutar_comando` está apagado
salvo `CDCRD_C3D_PERMITIR_COMANDOS=1`. Log del puente:
`%LOCALAPPDATA%\CdcrdCivil3dBridge\puente.log`.

| Síntoma | Causa |
|---|---|
| `Falta .NET SDK 10 (no basta tener el runtime)` | Instalar el SDK con el `winget` de arriba; Civil 3D solo trae el runtime. |
| `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` | SDK `mcp` 2.x. Corregir: `py -m pip install "mcp>=1.10,<2" --force-reinstall`. |
| La petición vuelve con `-32000` a los 55 s | Civil 3D está dentro de un comando o un diálogo modal. Ciérrelo y repita; el puente no reintenta en bucle. |
| El asistente no muestra las herramientas | Reiniciar el asistente desde la bandeja del sistema; o el `command` de la configuración apunta a `"python"` a secas en vez de la ruta real del intérprete. |

Catálogo de las 85 herramientas: [herramientas.md](servidor-mcp-civil3d/herramientas.md).
Límites verificados en vivo: [LIMITACIONES.md](servidor-mcp-civil3d/docs/LIMITACIONES.md).
Guía completa del servidor: [servidor-mcp-civil3d/README.md](servidor-mcp-civil3d/README.md).

### Instalar el puente de Civil 3D a BeamNG.drive

Lleva la superficie del terreno y la superficie final de un corredor desde Civil 3D
2027 hasta un **nivel propio de BeamNG.drive** para recorrer la carretera. No usa IA,
ni servidor MCP, ni BeamNG.tech. **No lo instala el menú**: son los comandos de abajo.

**Estado (versión 0.1.0):** importación, guardado, recarga y colisión física
comprobados en BeamNG.drive 0.39.4 con un nivel de prueba; en 0.40 no se ha probado.
La exportación en vivo desde Civil 3D 2027 y los empalmes carretera-terreno a lo largo
de una vía completa aún no están validados de extremo a extremo.

**Requisitos:** Civil 3D 2027 y el SDK de .NET 10 (mismo `winget` de la sección
anterior) para compilar el exportador; Python 3.10 o superior; BeamNG.drive con su
World Editor. Blender es opcional.

**Paso 1 · Exportador dentro de Civil 3D.** Desde la raíz del repositorio:

```powershell
cd .\civil3d-beamng
.\civil3d\instalar.ps1
```

Crea `%APPDATA%\Autodesk\ApplicationPlugins\CDCRD-BeamNG.bundle`, separado del
puente MCP, y conserva las versiones anteriores. Reinicie Civil 3D y compruebe que el
comando `CDCRDBEAMNGEXPORT` responde en su línea de comandos. Si Civil 3D está en
otra ruta: `.\civil3d\instalar.ps1 -Civil3DPath "D:\Autodesk\AutoCAD 2027"`.

**Paso 2 · Conversor en Python**, en un entorno virtual para no tocar el Python del
sistema (siga dentro de `civil3d-beamng`):

```powershell
py -3 -m venv "$env:USERPROFILE\cdcrd-beamng-venv"
& "$env:USERPROFILE\cdcrd-beamng-venv\Scripts\python.exe" -m pip install --upgrade pip
& "$env:USERPROFILE\cdcrd-beamng-venv\Scripts\python.exe" -m pip install .
& "$env:USERPROFILE\cdcrd-beamng-venv\Scripts\python.exe" -m cdcrd_beamng --help
```

Pase siempre la ruta completa de ese intérprete: el `python` del PATH puede ser el
alias de la Tienda, sin las dependencias.

**Paso 3 · Ruta del juego.** La plantilla de nivel sale de la instalación de
BeamNG.drive; debe devolver `True`:

```powershell
Test-Path 'C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive\content\levels\smallgrid.zip'
```

Si su Steam está en otro disco, en el paso 5 añada `-GameFolder 'D:\SteamLibrary\steamapps\common\BeamNG.drive'`
(Steam → clic derecho sobre el juego → Administrar → Explorar los archivos locales).

**Paso 4 · Probar el conversor sin abrir nada**, con el ejemplo sintético del repositorio:

```powershell
& "$env:USERPROFILE\cdcrd-beamng-venv\Scripts\python.exe" -m cdcrd_beamng validate --snapshot .\examples\snapshot-synthetic.json
```

Valida unidades, orden de coordenadas, geometría, IDs y referencias, y sale con
código 0 si el contrato es válido ([alcance](civil3d-beamng/docs/VALIDACION-INTERCAMBIOS.md)).

**Paso 5 · Primer nivel.**

1. En Civil 3D, con el dibujo **en metros** (`INSUNITS=6` y Drawing Settings → Units
   and Zone → Meters), ejecute `CDCRDBEAMNGEXPORT`, seleccione la TIN del terreno y la
   TIN final de la calzada, y guarde el JSON **fuera de este repositorio**: contiene
   geometría y nombres del proyecto.
2. Convierta e instale el nivel. Cambie las tres rutas; la carpeta de salida no debe
   existir y el id del nivel (minúsculas, números y guion bajo) cambia en cada revisión:

```powershell
& '.\tools\convertir-e-instalar.ps1' `
  -Snapshot 'D:\proyecto\exportacion.json' `
  -Output   'D:\proyecto\paquete_r01' `
  -LevelId  'mi_carretera_r01' `
  -Python   "$env:USERPROFILE\cdcrd-beamng-venv\Scripts\python.exe"
```

3. Reinicie BeamNG.drive, abra el nivel `mi_carretera_r01` desde **Freeroam** y pulse
   **F11** para el World Editor.
4. **Window → Importar Civil 3D**, ruta `/levels/mi_carretera_r01/manifest.json`,
   importe, **guarde** y vuelva a cargar el nivel desde el menú del juego antes de conducir.

Cada actualización mayor de BeamNG mueve la carpeta de usuario a un respaldo y con ella
se van el importador y los niveles: si desaparece el menú **Importar Civil 3D**, repita el
paso 5.2. No cambie de nivel con scripts ni por la API con el juego abierto: forzar una
transición pendiente de la interfaz provocó un fallo C++ durante las pruebas.

Lo que esta versión no incluye: texturas del CAD, señales, tráfico, puentes ni túneles;
la frontera entre asfalto y talud es aproximada y los huecos del terreno se recortan por
celdas completas. Guía pieza por pieza con una comprobación al final de cada una:
[instalacion/BEAMNG-DRIVE.md](instalacion/BEAMNG-DRIVE.md). Flujo con LandXML, recibos
y pruebas: [civil3d-beamng/README.md](civil3d-beamng/README.md).

### Instalación manual, paso a paso

<details>
<summary>Herramientas locales sin el menú, y conectores ETABS, SAFE y Revit</summary>

El módulo local se distribuye en este repositorio como el paquete Python `cdcrd-local`
(versionado en [pyproject.toml](herramientas-locales/pyproject.toml)), con CLI y servidor MCP.
La instalación documentada utiliza el código fuente y `uv.lock`:

```powershell
.\herramientas-locales\instalar.ps1 -Pruebas
.\herramientas-locales\cdcrd.ps1 doctor
```

Requiere `uv`; el instalador prepara Python 3.13 y un entorno aislado. Véanse los
[requisitos e instalación](herramientas-locales/README.md#instalación). No se presupone
publicación en PyPI ni en GitHub Packages.

Los conectores de ETABS, SAFE y Revit requieren las aplicaciones correspondientes y
tienen sus [propias instrucciones](instalacion/INSTALACION.md), escritas a partir de los
fallos reales de la primera instalación. El índice por herramienta está en
[instalacion/README.md](instalacion/README.md).

</details>

### Fallos frecuentes y su causa real

| Síntoma | Causa |
|---|---|
| `Python was not found; run without arguments to install from the Microsoft Store` | Es el alias de la Tienda, no Python. Instalar desde python.org o con el `winget` de arriba y desactivar los alias en Configuración → Aplicaciones → Alias de ejecución. |
| El asistente no encuentra los paquetes aunque `pip` los instaló | Hay dos Python: el shim del launcher y el intérprete real. La configuración debe apuntar al real, nunca a `"python"` a secas. El instalador ya resuelve la ruta real. |
| `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` | El SDK `mcp` 2.x eliminó ese módulo. El instalador reinstala `mcp>=1.10,<2`. |
| `GetActiveObject` falla con ETABS abierto | ETABS y el asistente corren con distinto nivel de privilegio; COM los aísla. Los dos como administrador, o ninguno. |
| JSON de configuración corrupto tras editarlo a mano | PowerShell 5.1 escribe BOM con `Set-Content`. El instalador escribe UTF-8 sin BOM. |
| El servidor BIM no aparece en una sesión en la nube | Estos servidores hablan por COM o por un puerto local: solo funcionan en un asistente que corra en la misma máquina que el programa. |
| `Falta uv` al elegir la opción 2 | `winget install --id astral-sh.uv -e`, o `powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"`; reabrir PowerShell. |

## Contribuir y reconocimientos

Las mejoras de herramientas, documentación y ejemplos se describen en
[CONTRIBUTING.md](CONTRIBUTING.md).

[Colaboradores y contribuciones](CONTRIBUTORS.md).

**Desarrollo asistido: OpenAI Codex y Anthropic Claude**, según el historial de cada cambio.
[Probar las herramientas con IA](docs/TRABAJAR-CON-IA.md). Las contribuciones concretas quedan
registradas en el historial del repositorio. Este reconocimiento no representa una cuenta
personal de GitHub ni una certificación de los resultados de ingeniería.

Los cambios publicados se resumen en [CHANGELOG.md](CHANGELOG.md). Para reportar un fallo
de seguridad sin exponerlo en público, siga [SECURITY.md](SECURITY.md).

## Licencia y cita

El código, las herramientas MCP, los scripts y la documentación técnica se distribuyen bajo la
[Licencia Apache 2.0](LICENSE). El texto normativo no está cubierto por esa licencia: es obra
del MIVHED y se reproduce citando la fuente conforme al artículo 41 de la Ley 65-00, como
detalla [NOTICE](NOTICE).

Para citar el proyecto use [CITATION.cff](CITATION.cff) o el botón "Cite this repository"
de GitHub.
