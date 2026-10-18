# Civil 3D · Puntos COGO y Survey

Cinco operaciones reutilizables mediante la API COM nativa, con preparación y
comparación en Python. **Probadas en Civil 3D 2027 para Windows (COM 13.9)**.
No requieren el puente MCP privado ni una DLL adicional. Python prepara el archivo;
AutoLISP ejecuta la API dentro de Civil 3D.

| Operación | Resultado | Ejemplo |
|---|---|---|
| `audit` | CSV PENZD de todos los COGO, sin modificar puntos | [auditoría](examples/audit.json) |
| `import` | Puntos nativos; solo admite dibujo vacío | [12 puntos](examples/import.json) |
| `group` | Grupo por números explícitos, con verificación de pertenencia | [seis TN](examples/group.json) |
| `survey-import` | NonControlPoints en una base Survey existente y vacía; guarda/cierra/reabre | [base de coordenadas](examples/survey-import.json) |
| `survey-read` | Comprueba número total, coordenadas, descripción, unidades y zona | [relectura](examples/survey-read.json) |

![Importación nativa](docs/images/import.png)

[Galería y verificación](docs/VALIDACION.md) · [Claude o Codex](../docs/TRABAJAR-CON-IA.md)

## Preparar un ejercicio

Requisitos: Civil 3D 2027 abierto, Python 3.10+, una copia guardada en metros
(`INSUNITS=6` y Drawing Settings → Units and Zone → Meters), sin comandos activos. No hay conversión de coordenadas ni de datum.
Use datos ficticios al compartir resultados. Esta herramienta no solicita guardar
ni cerrar el dibujo original.

1. Cree `C:/CivilPractice/results` y un dibujo vacío guardado como
   `C:/CivilPractice/DEMO_COGO_SURVEY.dwg`. Ajuste las rutas de los JSON a su equipo.
2. Desde esta carpeta prepare la importación:

```powershell
python -m point_tools.prepare examples/import.json --points examples/points.csv --backend "C:/repos/CDCRD-Digital/civil3d-points-survey/native/points-survey.lsp" --runner "C:/CivilPractice/import.lsp"
```

3. Revise el JSON, CSV y runner. En la línea de comandos de Civil 3D cargue el
   runner con `(load "C:/CivilPractice/import.lsp")`. Si aparece una advertencia
   de seguridad, revise el archivo y su procedencia; no cambie la política global.
4. Espere `CDCRD Points/Survey: OK` y un recibo `ok:true` en `results/import-01.json`.
   Un recibo `state:running` no acredita finalización. Compare el CSV nativo:

```powershell
python -m point_tools.verify examples/points.csv C:/CivilPractice/results/import-01.csv
```

5. Prepare `group.json` del mismo modo, usando `--points examples/terrain.csv`.
   Use un runner nuevo por operación. `audit.json` no requiere `--points`.
6. Para Survey cree primero una **base nueva y vacía** `DEMO_SURVEY` desde la pestaña
   Survey de Toolspace dentro de `C:/CivilPractice/Survey`. Cierre esa base antes
   de ejecutar. Prepare `survey-import.json` con `points.csv`, y después
   `survey-read.json`. La zona vacía corresponde a coordenadas locales ficticias.
7. Guarde, cierre y reabra únicamente la copia. Ejecute una auditoría con otro
   nombre de salida y compare contra el CSV inicial.

La creación inicial de la base **no forma parte de la API publicada**: una prueba
COM `Projects.Create` requirió Escape y dejó una base vacía. El importador separado
sí fue comprobado. No anunciar creación completamente automática ni ajuste Survey.

## Contrato y límites

- CSV exacto: `number,easting,northing,elevation,description`. Separador coma y
  comillas CSV; las coordenadas son E, N, Z en metros. No se intercambia N/E.
- Número entero único 1..2147483647; 1..10000 puntos por solicitud; valores finitos.
- La ruta completa del dibujo y el conteo esperado se comprueban antes de operar.
- No sobreescribe grupos ni recibos. Importar COGO exige cero puntos; Survey exige
  base sin puntos, redes ni figuras. No actualiza puntos existentes.
- Survey conserva coordenadas como **NonControlPoints**, sin estaciones, ángulos,
  distancias observadas, figuras, ajuste ni vínculo que convierta los COGO en
  SurveyPoint. Cierra la base y restaura la carpeta de trabajo al terminar.
- Survey recorta espacios extremos de descripciones; el preparador rechaza esa
  entrada para evitar una normalización silenciosa. El usuario debe decidirla.
- `survey-read` recibe el listado esperado y exige que represente toda la base;
  no es un explorador general de bases Survey desconocidas.
- Las escrituras COM no son una transacción. Interrumpir o fallar puede dejar
  puntos parciales. No repetir automáticamente: releer, revisar el checkpoint
  `.state.json`, cerrar la base y restaurar su `prior_working_folder` si hace falta.
- El runner es código ejecutable generado para revisión. Ediciones directas pueden
  saltarse validaciones del preparador; no cargue runners de procedencia desconocida.
- Ejecutar con un único operador; sin Survey abierto por otra tarea. No se reivindica
  compatibilidad con otras versiones hasta probar su ProgID y contratos.

## Pruebas portables

```powershell
python -m unittest discover -s tests -v
```

Las pruebas Python validan entradas y comparaciones. La ejecución nativa y sus
límites se documentan aparte en [VALIDACION.md](docs/VALIDACION.md).
