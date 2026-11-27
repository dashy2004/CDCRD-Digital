# Checklists del MIVHED — listas de verificación para la tramitación de proyectos

Los **14 checklists** que el Ministerio de la Vivienda, Hábitat y Edificaciones (MIVHED) publica en su
portal NORM para recibir y evaluar expedientes: **271 ítems**, 2,580 motivos de incumplimiento, 183 motivos
de no aplicabilidad, 533 referencias legales y el índice de 23 normas.

**No es una publicación oficial.** Es una copia estructurada, tomada el 2026-11-24 de la API pública del
portal `norm.mivhed.gob.do` (rutas `/api/public/templates` y `/api/public/norms`). El texto no se alteró,
salvo el colapso de espacios y saltos de línea. La fuente que manda es el portal: ante cualquier diferencia,
vale lo que él muestre.

**Cuatro checklists están en borrador** (`v1.0-draft`: Estructura, Eléctrica, Sanitaria y Geotecnia) y pueden
cambiar. El script `validar` avisa si los conteos dejan de cuadrar tras una nueva extracción.

Los términos de reutilización del portal no se revisaron. El contenido se reproduce como información pública
del ministerio, con su procedencia indicada; no incluye datos de proyectos ni de personas.

## Contenido

| Ruta | Qué es |
|---|---|
| `data/mivhed-norm-checklists.json` | Los 14 checklists completos: ítems, motivos, referencias legales e índice de normas. |
| `data/mapa-memoria-estructural.json` | Propuesta que agrupa los 65 ítems de Estructura en 11 grupos y sugiere la sección de memoria o el anexo de cada uno. No viene del ministerio. |
| `md/` | Un `.md` por checklist, `casos.csv` (un motivo por fila) e `indice-normas.md`. Se generan con el script. |
| `scripts/mivhed_checklists.py` | Valida los conteos, genera `md/` y comprueba el mapa. Solo usa la biblioteca estándar de Python. |
| `GUIA-IA-CHECKLISTS-MIVHED.md` | Reglas para que un asistente use los checklists al evaluar, diseñar o redactar memorias. |

## Uso

```powershell
python scripts\mivhed_checklists.py validar data\mivhed-norm-checklists.json
python scripts\mivhed_checklists.py generar data\mivhed-norm-checklists.json md
python scripts\mivhed_checklists.py mapa data\mivhed-norm-checklists.json data\mapa-memoria-estructural.json
```

`validar` y `mapa` terminan con código distinto de cero si algo no cuadra.

## Límites

- **Cumplir el checklist no es aprobar el proyecto.** Los checklists dicen qué revisa el ministerio, no
  sustituyen su evaluación. Ninguna herramienta de este repositorio debe declarar «cumple con el MIVHED».
- De las normas solo hay ruta, encabezado y extracto de cada disposición citada; no el texto completo. Parte
  de ese texto está en [`corpus-reglamentos`](../corpus-reglamentos).
- La API anuncia 27 normas y devuelve 23; las 4 restantes no se obtuvieron.
- Los códigos de motivo (por ejemplo `37.1`) se derivan del número de ítem y la posición del motivo. Coinciden
  con los que muestra el portal en los ítems cotejados de Recepción de Proyectos (1, 2, 3, 5, 6, 7, 10, 11, 12,
  13 y 20); el resto no se cotejó a mano.
- Solo Estructura tiene mapa de memoria.
