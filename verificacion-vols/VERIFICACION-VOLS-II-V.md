# Verificación — digitalización Vols II-V (2026-08-22)

## Alcance procesado
| Vol | PDF | pp | Cláusulas | Títulos |
|---|---|---|---|---|
| II (DIHE) | Instalaciones Hidrosanitarias | 161 | 465 | 8 |
| III (IEL) | Instalaciones Eléctricas | 181 | 497 | 1 (Electricidad) |
| IV | Instalaciones Mecánicas | 305 | 976 | 8 |
| V | Diseño Arquitectónico | 348 | 1,150 | 6 |
Total nuevo: **3,088 cláusulas**. Con Vol I (3,492 intactas): **6,580**.

## Método
`pipeline/parse_mivhed.py`: mismo enfoque determinista que `parse_cdcrd.py` (pypdf,
segmentación por cláusula numerada), extendido con: config por volumen, blanqueo de
páginas-índice internas, definiciones `N)` de Vols III-IV como cláusulas `<capítulo>.dNNN`,
y **asignación posicional de Título** (marcadores TÍTULO validados por nombre en II/V,
anclas de capítulo en IV) porque la numeración impresa no es jerarquía confiable.

## Chequeos ejecutados
- Reproducibilidad Vol I: re-parse bit-a-bit idéntico al repo en 9/10 títulos; T02 difiere
  solo en enriquecimiento posterior (`vision_ok`), que se preservó. No se tocó `datos/titulos/`.
- Texto huérfano pre-primer-evento: 28-106 caracteres por volumen (portadillas). Todo lo
  demás queda asignado a alguna cláusula.
- Muestreo visual contra página renderizada (110 dpi, en esta carpeta):
  - `verif-v3-p44`: ids 1.2.1.1-1.2.1.4 duplicados **en el documento impreso** (reutiliza
    numeración bajo Capítulo 1.3). La extracción coincide con el impreso.
  - `verif-v4-p30`: definiciones `1) ACEITE COMBUSTIBLE...` correctamente segmentadas.
  - `verif-v5-p339`: Título 6 reinicia numeración (1.1.1, 1.2.1...) en el impreso; las
    cláusulas quedan en T06 con `num_conflicto: true` y el id impreso intacto.

## Limitaciones conocidas (no citar sin cotejar)
- Ids duplicados heredados del impreso: v3 (23), v2 (1), v4 (7), v5 (9). Desambiguar por página.
- Regresiones de orden de lectura por maquetación del PDF: 31 casos marcados en el reporte
  del parser (peor: v3 con 13, v4-T04 con 9). El texto está completo, el orden local puede variar.
- Cotas de figuras en v5-T06 capturadas como cláusulas cortas (marcadas `num_conflicto`).
- Tablas y fórmulas siguen como texto plano (`flags.tabla` / `flags.formula`); el pase de
  visión (`vision_ok`) queda pendiente, igual que en Vol I.
- `version_codigo: null` en Vols II-V: los PDF MIVHED no traen fecha de edición impresa.
