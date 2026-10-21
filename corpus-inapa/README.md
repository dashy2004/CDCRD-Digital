# corpus-inapa — Reglamento Técnico INAPA (DIG-PO-001) con procedencia

Corpus consultable del *Reglamento Técnico para Diseño de Obras e Instalaciones
Hidro-Sanitario del INAPA* (código DIG-PO-001, versión 01, emitido 4-julio-2018),
construido desde el PDF con `pdftotext`. Unidad del corpus: la **página**. Cada
página conserva su número PDF, su número impreso (leído del encabezado de esa misma
página, nunca inferido por desplazamiento: el total impreso declarado varía entre
410 y 413 dentro del mismo documento), la estructura vigente (título, capítulo,
sección numerada) y el hash de su texto.

Fuente oficial: <https://inapa.gob.do/wp-content/uploads/2024/11/ReglamentoTecnicoParaDisenoDeObrasEIstalacionesHidro.pdf>.
La identidad binaria entre ese archivo y el PDF usado para extraer queda registrada
por `sha256_pdf` en `resumen.json`; comprobarla antes de citar como "fuente oficial".

## Norma e hipótesis: dos clases que no se mezclan

| clase | qué es | cómo se construye | campos obligatorios |
|---|---|---|---|
| `norma` | texto del reglamento | `referencia_norma(doc, pagina_impresa=..., fragmento=...)`: falla si la página o el fragmento no existen | código, versión, fecha, título/capítulo/sección vigentes, página impresa, página PDF, `sha256_texto`, fuente, cita |
| `hipotesis` | supuesto del proyecto (caudal adoptado, `n`, nivel de agua, pérdidas) | `referencia_hipotesis(enunciado, justificacion, fuente, unidades)` | enunciado, justificación; siempre `normativa: false` |

`validar_referencias(lista)` comprueba que cada referencia esté completa según su clase.
El capítulo I (pág. impresa 4) fija el campo de aplicación en abastecimiento de agua
potable, aguas residuales y pluviales: la aplicabilidad del reglamento a un proyecto
de riego u otro es una decisión del proyectista y se registra como hipótesis, no como
norma.

## Uso

```powershell
# 1. extraer (una vez; requiere pdftotext de poppler en el PATH)
py extraer.py "<ruta al PDF>" datos/DIG-PO-001_v01_2018-07-04

# 2. buscar
py buscar.py datos/DIG-PO-001_v01_2018-07-04/corpus.json "velocidad minima" --limite 5 --solo-citas
py buscar.py datos/DIG-PO-001_v01_2018-07-04/corpus.json impresa:60
py buscar.py datos/DIG-PO-001_v01_2018-07-04/corpus.json "coeficiente rugosidad" --titulo II --capitulo V

# 3. pruebas (páginas sintéticas, sin PDF)
py -m unittest discover -s tests -v
```

Desde Python:

```python
import buscar
doc = buscar.cargar("datos/DIG-PO-001_v01_2018-07-04/corpus.json")
r = buscar.buscar("velocidad minima", doc, limite=3)
norma = buscar.referencia_norma(doc, pagina_impresa=r["resultados"][0]["pagina_impresa"],
                                fragmento="velocidad")
hip = buscar.referencia_hipotesis("Q adoptado 0.30 m3/s", "redondeo del caudal requerido", unidades="m3/s")
buscar.validar_referencias([norma, hip])
```

La búsqueda usa FTS5 de SQLite (todos los términos, orden `bm25`, sin diacríticos),
igual que `herramientas-locales/src/cdcrd_local/normativa.py` para el Código de
Construcción; los dos corpus se mantienen separados.

## Archivos

- `extraer.py` — PDF → `corpus.json` + `resumen.json`. `construir_corpus()` está
  separado de `pdftotext` para probarse con páginas sintéticas.
- `buscar.py` — búsqueda, cita, `referencia_norma`, `referencia_hipotesis`,
  `validar_referencias`.
- `tests/test_corpus.py` — 21 pruebas con páginas sintéticas.
- `datos/<codigo>_v<version>_<fecha>/corpus.json` — texto OCR por página. Es texto
  de un reglamento público; no contiene datos de ningún proyecto.

## Límites

- Texto OCR del escaneo original; `revision_humana: false` hasta que alguien coteje.
  Tablas y fórmulas salen como texto plano y pueden estar desordenadas.
- La "cláusula" es la estructura vigente detectada (título / capítulo / sección
  numerada). El reglamento numera secciones solo en parte; cuando no hay sección la
  cita lleva capítulo y página.
- El índice de contenido (págs. impresas 2-3) se excluye de la detección de
  estructura, pero su texto sí se indexa.
- No determina vigencia legal ni aplicabilidad a un expediente.
