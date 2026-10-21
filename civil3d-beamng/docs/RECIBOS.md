# Recibos unificados Civil 3D → BeamNG

El esquema `cdcrd.operation-receipt/1` registra una ejecución de `validate`,
`build` o `verify`. Reutiliza el validador, el conversor, `verify_package`, los
hashes del manifest y la función SHA256 existente. No ejecuta comandos CAD ni
abre el juego. Sin `--receipt` se conserva la salida anterior de cada comando.

## Uso

Desde la raíz del repositorio, con las dependencias del conversor disponibles
en el entorno de herramientas-locales:

```powershell
.\herramientas-locales\cdcrd.ps1 validar-intercambio --modulo beamng `
  --snapshot .\civil3d-beamng\examples\snapshot-synthetic.json `
  --recibo .\recibos\validacion-r01.json --json
```

Desde `civil3d-beamng`, para registrar conversión y verificación:

```powershell
python -m cdcrd_beamng build --snapshot .\examples\snapshot-synthetic.json `
  --output .\paquetes\ejemplo_r01 --level-id ejemplo_r01 --road-is-drivable `
  --receipt .\recibos\conversion-r01.json
python -m cdcrd_beamng verify .\paquetes\ejemplo_r01 `
  --receipt .\recibos\verificacion-r01.json
```

`--road-is-drivable` solo corresponde a una superficie completa de pavimento
verificada por el operador; el ejemplo geométrico es sintético. Las entradas
LandXML y guía opcional conservan las opciones del validador/conversor.

`--evidence ARCHIVO` puede repetirse para adjuntar un recibo nativo existente,
captura o informe. En la CLI común se llama `--evidencia ARCHIVO`. Requiere
`--receipt`/`--recibo`. Se registra el hash antes/después del archivo; sus
afirmaciones no se interpretan ni se elevan a prueba de ejecución o geometría.

## Contenido

| Campo | Significado |
|---|---|
| `id`, `module`, `tool`, `operation` | UUID, módulo, versión del paquete Python y operación ejecutada. No es la versión cargada en Civil 3D. |
| `started_utc`, `finished_utc`, `duration_seconds` | Marcas UTC y duración monotónica. |
| `parameters` | Parámetros de la operación; los archivos se enumeran aparte. |
| `files.inputs` | Identificador por función, ruta, bytes y SHA256 antes/después, estado `unchanged`, `changed` o `unavailable`. En `verify` incluye manifest y activos. |
| `files.outputs` | Archivos del paquete generado, incluido manifest, con bytes/SHA256; no incluye el propio recibo. |
| `execution.attempted/completed` | Si se llamó a la operación y si devolvió resultado. Una comprobación posterior puede invalidar un resultado devuelto. |
| `result` | Resultado real del validador o resumen del manifest. Se conserva si el control posterior de hashes falla. |
| `ok`, `status`, `errors` | Resultado final y errores de acceso, operación o estabilidad. |
| `evidence.level` | `source_contract`, `package_file_integrity` o `none`. |
| `evidence.attachments` | Archivos aportados, marcados `assessment=hash_only`, con hashes antes/después. |
| `evidence.native_operation/consumer_validation` | Siempre `not_checked`: no se ejecutó una prueba nativa. |
| `authenticity` | `unsigned`: un hash no autentica al autor ni impide editar el JSON. |

Las rutas se expresan respecto al directorio del recibo; en unidades Windows
distintas se guarda la ruta absoluta. Los recibos de proyectos reales pueden
contener nombres, rutas y resultados privados: permanecen fuera del repositorio.

## Escritura y fallos

Se exige un archivo nuevo fuera del paquete: añadirlo dentro rompería la lista
cerrada de archivos verificada por `verify_package`. Se rechazan archivos ya
existentes y enlaces simbólicos de destino, incluidos enlaces colgantes. La
publicación usa un temporal completo y un hard link exclusivo, sin sobrescribir
otro escritor; requiere soporte de hard links en el sistema de archivos.

Salida 0: recibo con `ok=true`. Salida 1: recibo fallido guardado, incluidos los
rechazos del validador. Salida 2: opciones o guardado del recibo fallaron. Un error
de guardado no significa que la operación no se ejecutó: revisar primero el
paquete/salidas antes de repetir una conversión.

Si falta una entrada o evidencia, se guarda el fallo sin ejecutar la operación.
Si cambia una entrada/evidencia, o un activo generado difiere del manifest, el
recibo final falla. Los archivos generados se conservan para su revisión. Los
hashes se comparan alrededor de la operación; no sustituyen un lock, una copia
inmutable o una firma, ni detectan todas las modificaciones transitorias que
restauran los bytes originales. Evitar otros escritores durante la ejecución.

El recibo nativo Civil 3D de `CommandReceipts` mantiene su contrato y sus tickets:
`CommandEnded` acredita fin del comando, no geometría. Puede adjuntarse como
archivo existente; no se modifica su estado ni se afirma una operación nueva.

## Pruebas

La suite existente y los casos nuevos cubren éxito/fallo, hashes antes/después,
entradas/evidencias ausentes, corrupción posterior, enlaces de paquetes/recibos,
publicación concurrente sin sobrescritura y ambas CLI reales. Los recibos de
conversión se contrastan con el manifest existente. RED/GREEN se conserva en
los commits de este PR: `21771e0→9c233d5` y `c764eed→cdf60c7`.

Resultado local final: **145 pruebas y 19 subpruebas aprobadas**, **96 %** de
cobertura en `receipts.py`, **100 %** en el adaptador y **86 %** en el conjunto
instrumentado. Los procesos CLI reales se prueban sin instrumentar su cobertura.
Los ejemplos completos de validación, conversión y verificación también se
ejecutaron por CLI. Cuatro advertencias externas de pycollada/NumPy 2.5 no
afectaron la lectura de geometría. La CI existente descubre estos casos junto a
las regresiones del conversor y las comprobaciones del adaptador común.
