# Guía para el asistente de IA: memoria de cálculo estructural

Si le piden una **memoria de cálculo**, **memoria de diseño** o **memoria estructural** de un
proyecto, el documento se genera con este motor. No lo redacte a mano ni invente otro
formato: el motor fija la portada, la hoja de control, los capítulos, las tablas y la
numeración, y por eso dos equipos distintos producen el mismo documento.

Su trabajo es reunir las fuentes, llenar los dos archivos de entrada, ejecutar el motor y
revisar el resultado. El `README.md` de esta carpeta documenta cada clave.

## Procedimiento

1. **Ubique las fuentes en la carpeta del proyecto.** Pregunte por las que no encuentre; no
   las sustituya por valores supuestos.

   | Fuente | Archivo | Capítulo que alimenta |
   |---|---|---|
   | Listados de losas de Losas.exe, uno por nivel | `.TXT` (y `.DL` si existe) | Diseño de losas |
   | Libro de cargas y espesores | `.xlsx` con hojas «Espesor …» y «Carga …» | Cuantificación de cargas |
   | Modelo de cada bloque | `.EDB` de ETABS | Modelo, resultados y diseño del bloque |
   | Hojas de espectro y de Art. 38 de cada bloque | `.xls` / `.xlsx` | Parámetros sísmicos, irregularidad torsional |
   | Modelo de fundaciones | `.FDB` de SAFE | Fundaciones |
   | Portada, logo y una vista de cada bloque | imágenes | Portada y apertura de cada capítulo |

2. **Cree una carpeta de salida fuera del repositorio**, por ejemplo
   `<proyecto>\Memoria\`, con una subcarpeta `imagenes`. Los datos de un proyecto no se suben
   al repositorio.

3. **Copie las dos plantillas** de `ejemplo\` a esa carpeta y llénelas:
   - `fuentes.plantilla.json` → `fuentes.json`: rutas de las fuentes del paso 1. Quite las
     secciones que el proyecto no tenga.
   - `memoria.plantilla.json` → `memoria.json`: portada, responsable, datos del proyecto,
     materiales, normas, vistas y fundaciones. Los datos salen de los planos y de lo que diga
     el ingeniero; lo que no se sepa se deja vacío (los campos vacíos se omiten).

4. **Ejecute**, desde esta carpeta (use `.venv\Scripts\python` si existe):

   ```powershell
   python armar_datos.py "<salida>\fuentes.json" "<salida>\data.json"
   python generar.py "<salida>\data.json" "" "<salida>\Memoria <proyecto>.docx" "<salida>\_tmp" "<salida>\imagenes" "<salida>\memoria.json"
   .\word_pdf.ps1 -Docx "<salida>\Memoria <proyecto>.docx" -Pdf "<salida>\Memoria <proyecto>.pdf"
   ```

   El primer paso abre copias de los modelos en ETABS y SAFE y corre el análisis: tarda
   minutos y necesita los programas instalados y una sesión de escritorio. Los modelos
   originales no se tocan. Si ETABS o SAFE no están en el equipo, dígalo; no rellene esos
   capítulos con datos de otra procedencia sin avisar.

5. **Revise el PDF página por página** contra los criterios de abajo y lea el capítulo de
   observaciones: ahí el motor deja lo que no cuadra entre fuentes. Lo que haya que
   corregir se corrige en `memoria.json` o en las fuentes y se regenera; lo que se edite a
   mano en Word se pierde al regenerar.

## Criterios de formato

Son los del ingeniero responsable y aplican a toda memoria, no a un proyecto en particular.
El motor ya cumple la mayoría; verifíquelos en el resultado.

- Las tablas de secciones (vigas, columnas, losas, muros, espesores de fundación) listan solo
  las que están **en uso** en el modelo.
- Presiones sobre el suelo: solo la combinación gravitacional de servicio y la envolvente.
  Se indica en `memoria.json`, clave `fundaciones.combinaciones`, con los nombres que tengan
  en el modelo de SAFE (por ejemplo `["Comb2", "Envelope"]`). Sin esa clave salen todas.
- Sin tablas ni columnas de mensajes crudos de ETABS.
- Los subtítulos de tercer nivel van numerados bajo su título (4.5.1, 4.5.2…) y no entran al
  índice.
- Toda magnitud lleva su unidad, también cuando es adimensional.
- Las cargas se detallan: la muerta y cada viva con su factor de participación, no una línea
  resumida.
- Si falta una hoja de cálculo (por ejemplo la de reducción de la constante de torsión), el
  dato se toma del modelo de ETABS en vez de declararlo ausente.
- Junto a la tabla modal se señala cuando la participación de masa acumulada queda por debajo
  del 90 %.
- El documento nace como borrador, con marca de agua. La marca se quita
  (`control.marca_de_agua: ""`) y las firmas se colocan solo cuando el ingeniero responsable
  lo indique. La imagen de una firma la pone únicamente su titular.

## Lo que no debe hacer

- Escribir la memoria como texto libre, en Markdown o con otra plantilla de Word.
- Abrir los modelos originales o trabajar sobre una sesión de ETABS o SAFE que el usuario
  tenga abierta. Los lectores ya trabajan sobre copias en `_trabajo`.
- Inventar parámetros de suelo, materiales, normas o responsables.
- Quitar observaciones del capítulo final porque «se ven mal»: se omiten con
  `observaciones_omitir` solo si el ingeniero lo pide.
- Subir al repositorio `data.json`, `memoria.json`, modelos o documentos de un proyecto.

## Cruce con el checklist del MIVHED (opcional)

Con el JSON de checklists del corpus (`corpus-mivhed-checklists/data/mivhed-norm-checklists.json`):

```powershell
python cruce_mivhed.py "<salida>\data.json" "<salida>\memoria.json" "<checklist>.json" "<salida>\Cruce MIVHED Estructura.md"
```

Para incluirlo como anexo de la memoria, ponga esa ruta en `memoria.json`, clave
`checklist_mivhed`, y regenere.

## Comprobación del motor

```powershell
python -m pytest tests -q
```
