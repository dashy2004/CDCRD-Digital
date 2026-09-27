# Auditoría de citas de las verificaciones — 2026-09-27 [codex]

Alcance: `herramientas/verificacion_irregularidad_torsional.py` y
`herramientas/verificacion_zapata.py`, cotejadas contra el texto humano de
`md/vol-1/T02.md` y `md/vol-1/T04.md`. Los números de línea son de esos
archivos, no de un PDF. Las expresiones con OCR señalado como corrupto no
se consideran confirmadas por la transcripción.

## Título 2 — irregularidad torsional

| Afirmación de la herramienta | Texto cotejado | Resultado |
|---|---|---|
| CIT = deriva máxima / promedio de derivas extremas, por piso y dirección; se asigna el máximo de pisos | `T02.md:2963-2983` | Coincide en alcance. La ecuación 30 tiene símbolos OCR corruptos (`:2964,2969-2970`), aunque las definiciones de numerador y denominador son legibles. |
| H-1 si CIT > 1.20 | `T02.md:2394-2400` | Coincide como uno de **dos disparadores alternativos**. La tabla también dice H-1 cuando más del 75% de resistencia lateral está a un lado del centro de masa, para diafragma rígido o semirrígido. La herramienta no mide esa distribución. Se añadió `h1_por_resistencia` explícito: sin descartarla, un caso CIT regular queda `INCOMPLETO`. |
| Moderada `1.20 < CIT <= 1.40` (docstring original y clasificación original) | `T02.md:2431-2437` | **Discrepancia de transcripción.** La tabla escribe `1.40 > CIT > 1.20` y `CIT > 1.40`; el valor exactamente 1.40 no entra en ninguna categoría. Se corrigió el docstring y el caso exacto devuelve `INCOMPLETO`. **[D] Emil debe decidir su tratamiento normativo.** |
| Tope CIT 1.60 | `T02.md:2473-2476` | Confirmado: “en ningún caso podrá exceder 1.60”; igualdad no excede. |
| Prohibición de extrema en CDS D/E/F salvo vivienda unifamiliar hasta dos niveles | `T02.md:2478-2482` | Confirmados CDS y excepción. **[D]** El paréntesis de la cláusula escribe `1.40<CIT<1.60`, mientras el tope anterior admite 1.60. La herramienta trata 1.60 como extrema y prohibida; falta decisión sobre el extremo textual. |
| `rho = 1.3` con extrema en ambas direcciones | `T02.md:2484-2489` | Confirmado. |
| +25% en conexiones de diafragma con elementos verticales y colectores con H-1 en CDS C/F | `T02.md:2460-2466` | Confirmado, también aplica a H-2/H-3/H-4. Se corrigió la emisión para que solo aparezca en CDS C a F. |
| Excentricidad accidental 5% perpendicular y en ambos signos | `T02.md:2939-2946`, `:2963-2968` | Confirmado. `ecc_accidental=true` ahora documenta la certificación de ambos signos por quien genera el JSON; la herramienta no puede comprobar el modelo de ETABS. |
| Diafragma flexible comprobado excluye el chequeo torsional | `T02.md:2979-2981` | Confirmado. |
| Descartar resultado de deriva ortogonal al nombre de caso, citado a 2.10.7.2 | `T02.md:2763-2766` | **[D] Alcance no demostrado.** La cláusula dice que no se requiere aplicar simultáneamente fuerzas ortogonales; no dice que un resultado ortogonal de un caso unidireccional deba descartarse. La regla original se conserva a la espera de Emil. |
| Ax de 2.10.8.1.14 = cuadrado del cociente y acotado 1 a 3 | `T02.md:2985-3002` | El alcance a CDS C/F y el uso de desplazamientos **antes** de Ax son legibles. La ecuación 31 y la desigualdad tienen OCR corrupto (`:2986,2993-2997`): no se confirma el exponente 2 ni si los extremos son estrictos. **[D] Cotejar PDF/criterio con Emil.** |
| CIT sin excentricidad como “cota inferior” (texto original) | `T02.md:2939-2946`; fixture ING-CIV337 SIN/CON ecc | **Discrepancia.** La cláusula exige excentricidad, pero no garantiza monotonía; en el fixture X sin ecc fue 1.619 y con ecc 1.606. Se quitó la afirmación de cota inferior; sigue `INCOMPLETO`. |

## Título 4 — zapata

| Afirmación de la herramienta | Texto cotejado | Resultado |
|---|---|---|
| Resultante dentro de B/6 para evitar levantamiento | `T04.md:1470-1480`, en especial `:1478-1479` | Confirmado para la dirección B; la aplicación análoga en L es interpretación geométrica, no texto literal de esa cláusula. |
| Presión admisible como capacidad del chequeo gravitatorio | `T04.md:1470-1477` y `:1760-1768` | El texto exige el menor valor entre capacidad portante con FS y presión compatible con asentamientos; 4.4.5.6 presenta capacidad portante/FS. La fórmula implementada de presión máxima biaxial no aparece en esas líneas. **[D]** Confirmar fuente del modelo de distribución y del control geotécnico del `sigma_adm` de entrada. |
| Elevar `sigma_adm` sísmico con relación 3.0/2.5 | `T04.md:1354-1359`, `:1470-1477` | Factores 3.0 y 2.5 confirmados, pero 4.3.2.7 los limita a falla **por corte** y 2.5 incluye sismo **o viento**, el más desfavorable. No autoriza multiplicar automáticamente una presión gobernada por asentamiento. **[D]** Hasta decidir, si no se declara `sigma_adm_control="corte"`, este chequeo devuelve `INCOMPLETO`. |
| 4.4.5.6 como cita del chequeo de presión superficial | `T04.md:1760-1768` | Cita pertinente al cálculo de presión admisible por capacidad, pero no al cálculo directo de la presión de contacto máxima de la herramienta. El efecto de carga excéntrica sobre dimensiones efectivas está en 4.4.5.7 (`:1772-1783`) y no está cubierto aquí. **[D]** Revisar alcance antes de usar como verificación geotécnica completa. |

## Citas externas de ACI y SOP

Las citas ACI 318-19 de `verificacion_zapata.py` (Tabla 21.2.1, 19.2.4.2,
Tabla 22.6.5.3, 22.5.5.1, 22.6.5.2, 22.2, 7.6.1.1 y 25.4.3) no tienen
texto normativo en `md/vol-*` ni en `datos/titulos`. El [avance oficial de ACI
318-19](https://www.concrete.org/Portals/0/Files/PDF/Previews/318-19_preview.pdf)
confirma la existencia de capítulos, pero no expone las tablas y fórmulas
necesarias para auditar valores y alcance. **No se certifican esas citas** con
esta capa humana. **[D]** Emil debe aportar la edición aplicable o confirmar
una fuente autorizada antes de considerar auditados los coeficientes y
expresiones ACI.

El chequeo `~25 db` del SOP 3.4 no equivale a verificar `ldh` de ACI 25.4.3.
La herramienta ahora reporta `INCOMPLETO` para ese renglón, con demanda y
espesor disponible, hasta que se compruebe el desarrollo real.
