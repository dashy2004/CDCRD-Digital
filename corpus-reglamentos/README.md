# Reglamentos complementarios — texto trazable por página

Primera extracción de **12 documentos técnicos / 1.370 páginas PDF** de la biblioteca proporcionada por el autor. Se conserva el corpus CDCRD existente sin mezclar ediciones ni inferir sustituciones normativas.

**No es una edición oficial ni una base numérica validada para cálculo.** El texto proviene de la capa del PDF o de OCR local en español/inglés. Tablas, fórmulas, subíndices, figuras y cifras requieren cotejo visual; la presencia de texto no acredita su exactitud. La vigencia y relación entre reglamentos no se han evaluado.

## Documentos

| ID | Documento | Páginas PDF | Texto |
|---|---|---:|---|
| R-001 | Análisis y diseño sísmico | 65 | [Leer](data/R-001.md) |
| R-002 | Estacionamiento vehicular | 80 | [Leer](data/R-002.md) |
| R-008 | Instalaciones sanitarias en edificaciones | 102 | [Leer](data/R-008.md) |
| R-012 | Diseño geométrico de carreteras; portada M-012 | 53 | [Leer](data/R-012.md) |
| R-013 | Presentación de estudios y proyectos de carreteras | 77 | [Leer](data/R-013.md) |
| R-014 | Construcción de carreteras | 208 | [Leer](data/R-014.md) |
| R-024 | Estudios geotécnicos en edificaciones | 60 | [Leer](data/R-024.md) |
| R-026 | Excavaciones en vías públicas | 27 | [Leer](data/R-026.md) |
| R-033 | Estructuras en hormigón armado | 171 | [Leer](data/R-033.md) |
| DEC-42-05 | Aguas para consumo humano | 102 | [Leer](data/DEC-42-05.md) |
| INAPA-2018 | Obras e instalaciones hidro-sanitarias | 414 | [Leer](data/INAPA-2018.md) |
| REF-TUNEL | Obras próximas al túnel Ortega y Gasset–UASD | 11 | [Leer](data/REF-TUNEL.md) |

**REF-TUNEL es una referencia documental con número de decreto sin completar; no se presenta como norma promulgada.**

## Referencias y calidad

- [sources.json](sources.json): archivo relativo, título, SHA-256 original, páginas, catálogo de procedencia cuando está identificado y advertencias.
- [data/manifest.json](data/manifest.json): conteos, versiones de extracción, páginas con OCR/alertas y hashes de JSON y Markdown.
- `data/ID.json`: una entrada por página; `page_pdf` empieza en 1. `printed_page=null` evita inventar equivalencias con la numeración impresa.
- `visually_verified=false` en todas las páginas: no hay aprobación profesional de fórmulas/tablas. Las alertas automáticas solo detectan ciertos defectos, no toda corrupción de texto.
- Se conserva el texto nativo cuando se aplica OCR nuevo. No se autocorrigen cifras ni se rellenan páginas faltantes mediante IA. El OCR trabaja localmente; los PDF originales no se modifican ni se suben.

R-002 es mayormente escaneado. También hay capas OCR preexistentes, especialmente en documentos hidrosanitarios, con errores como `10s` por `los`. El pipeline conserva esa evidencia y no convierte sus cifras en reglas ejecutables.

Catálogos de referencia: [MOPC/DGRS](https://portalweb.mopc.gob.do/dgrs/reglamentos/) e [INAPA](https://inapa.gob.do/transparencia/base-legal-de-la-institucion/resoluciones-base-legal/). Los hashes identifican exactamente los PDF de la biblioteca local: no se afirma que sean idénticos a una descarga actual de esos catálogos.

## Buscar sin instalar paquetes

La consulta de los JSON generados solo requiere Python 3.10+:

```bash
python corpus-reglamentos/buscar.py "estacionamiento" --limit 2
python corpus-reglamentos/buscar.py "sismico" --limit 2 --offset 2
python corpus-reglamentos/digitalizar.py --verify
```

Cada coincidencia devuelve documento, página, SHA-256 del PDF, texto y advertencias. La búsqueda ignora tildes; exige que aparezcan todos los términos en la misma página. No reconstruye palabras partidas ni interpreta jurídicamente los resultados.

## Reproducir

```bash
python -m pip install -r corpus-reglamentos/requirements.txt
python corpus-reglamentos/digitalizar.py --library "/ruta/REGLAMENTOS" --ocr
python corpus-reglamentos/digitalizar.py --verify
python -m pytest corpus-reglamentos/tests -q
```

Para `--ocr`, instalar Tesseract con los idiomas `spa` y `eng` y disponer de `tesseract` en PATH. Esta extracción usó Tesseract 5.3.4 a 250 dpi; las versiones restantes quedan en el manifiesto. Sin `--ocr`, las páginas escaneadas quedan marcadas sin texto, por lo que no equivale a esta entrega.

## Exclusiones y siguiente revisión

Se excluyeron los dos reglamentos académicos solicitados, libros/manuales comerciales ACI y AASHTO, y material docente. R-012 e INAPA se deduplicaron por hash. Se priorizó el R-008 completo de 102 páginas: el archivo comprimido de 94 páginas comienza con contenido ajeno y no se asumió equivalente.

Los PDF CDCRD/MIVHED de otras ediciones requieren un cotejo de versiones aparte; no se añadieron como si fueran reglamentos nuevos. Siguiente paso: revisión de tablas/fórmulas contra imágenes y estructuración de artículos y datos numéricos solo después de verificarlos.

## Verificación de esta entrega (2026-10-17)

- Integridad: 12 documentos, 1.370 páginas consecutivas, hashes de textos/JSON/Markdown correctos; los 12 PDF originales mantienen su SHA-256.
- OCR nuevo en 110 páginas, todas marcadas para revisión. Permanecen 14 sin texto y 18 con texto escaso; no se completaron inventando contenido.
- Muestreo visual contra render: R-002 p.12, R-014 p.25, INAPA p.100 y Decreto 42-05 p.9. Se confirmó correspondencia temática y se observaron errores de OCR/segmentación, no precisión numérica integral.
- Seis páginas sin texto inspeccionadas (R-002 p.3/15/55 y R-026 p.16/20/24) son hojas visualmente en blanco. Las restantes siguen señaladas para revisión.
- 10 pruebas del pipeline/búsqueda aprobadas; junto con 29 pruebas ETABS, 39 aprobadas. Búsquedas reales comprobadas: `estacionamiento`, `clases tanques` y `sismico`.
