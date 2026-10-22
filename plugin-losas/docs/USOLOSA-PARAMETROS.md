# UsoLosa: escritura de parámetros y diagnóstico de transacciones

El guardado del panel crea bindings de parámetros de texto cuando faltan y
escribe uso, sección y acero en las losas. La corrección elimina la llamada
explícita a `Document.Regenerate()` de este flujo. También evita informar éxito
cuando Revit rechaza una escritura o revierte la transacción.

**Esto no demuestra que un cierre nativo de Revit esté resuelto.**
`Transaction.Commit()` también regenera el documento, según la
[documentación de Autodesk](https://blog.autodesk.io/documentregenerate-can-be-called-when-necessary/).
El commit de bindings no ofrece una garantía de regeneración limitada. Los tests
portables simulan el contrato; la aceptación en Revit sigue siendo necesaria.

## Comportamiento

- Revisa todas las losas solicitadas antes de abrir la transacción: Mark único,
  elemento existente, parámetro sin ambigüedad, texto editable y valor textual.
- Si todos los valores coinciden, devuelve cero sin abrir transacción.
- Crea los bindings que faltan y comprueba el retorno de `BindingMap.Insert`.
  Restaura `SharedParametersFilename` incluso si originalmente estaba vacío.
- Si los parámetros son visibles, escribe y confirma en una sola transacción.
  Si todavía no aparecen, confirma solo los bindings, vuelve a obtener los
  elementos/parámetros y abre una segunda transacción para los valores.
- Exige `Start == Started`, `Set == True` y tanto el retorno de `Commit` como el
  estado final `Committed`. Relee cada valor después del commit antes de informar
  cuántos valores se guardaron.
- Si falla una operación, revierte la transacción que siga abierta y propaga el
  error al diálogo del panel. Si Revit devuelve `Pending`, conserva la transacción
  y bloquea otro intento en esa ventana hasta resolver el fallo en Revit y cerrarla.
- Usa `SetClearAfterRollback(True)` y manejo modal de fallos. No borra advertencias
  mediante un preprocesador ni trata estas opciones como protección contra un
  crash nativo.

En el flujo de dos transacciones, un fallo en la segunda puede dejar los bindings
creados, sin los valores solicitados. Un error de relectura posterior al commit
tampoco deshace automáticamente lo ya confirmado. Consultar el registro y el
estado del modelo antes de repetir. No se ejecutan purgas ni se eliminan imports,
tipos CAD o detalles. El panel no guarda el RVT en disco.

## Registro incremental local

`%TEMP%\plugin_losas_parametros.jsonl` se abre y sincroniza a disco en cada evento.
En IronPython usa `FileStream.Flush(true)` de .NET; en CPython, `os.fsync`.
La comprobación aislada de IronPython detectó que `_io.fileno()` no funciona
con `os.fsync` en ese motor.
Incluye un identificador de corrida, UTC, título de operación, fase, nombre del
parámetro e identificador/Mark de la losa; no registra los valores escritos.
Permanece local: puede contener identificadores del modelo y no debe subirse a Git.

Las fases incluyen `binding_before/after`, `set_before/after`,
`commit_before/after` (bindings o valores) y `verified`. Un `commit_before` sin
`commit_after` delimita la llamada interrumpida; no prueba por sí solo la causa
interna de Revit. El log de errores existente sigue en
`%TEMP%\plugin_losas_panel_error.log`.

Si no se puede escribir el registro, no se continúa con nuevas escrituras. Si el
fallo del registro llega después de un commit, el modelo puede tener cambios:
reconciliar el estado antes de volver a pulsar el botón.

## Verificación portable

Desde la raíz del repo:

```powershell
py -m pip install "./puente-losas[dev]"
py -m pytest plugin-losas/tests puente-losas/tests -q
```

`tests/test_panel_parametros.py` carga con AST las funciones reales del botón,
sin importar pyRevit ni conectarse a Revit. Simula 42 losas, bindings inmediatos o
visibles tras commit, rechazos de Insert/Set/Start/Commit, estado Pending,
relectura diferente, parámetros ambiguos o no editables y fallo del registro.
La API simulada rechaza cualquier llamada manual a `Regenerate`.
GitHub Actions ejecuta estos tests junto a las regresiones existentes del plugin
y del puente.

## Aceptación nativa pendiente

1. Obtener el turno exclusivo según el protocolo local. Preparar una copia de
   prueba del modelo y registrar identidad, estado y conteos de imports, tipos CAD
   y detalles. No purgar ni guardar el original desde este procedimiento.
2. Incorporar esta corrección en el checkout que usa la extensión. La ruta del
   script ejecutado importa: actualizar solo otro checkout no instala el cambio.
   Cerrar el panel antiguo y abrir de nuevo el botón con el script actualizado.
3. En una copia sin los parámetros nuevos, guardar los valores de las 42 losas.
   Confirmar que la sesión sigue viva y releer nativamente todos los valores.
   Debe existir `verified` en el log, después de los commits confirmados.
4. Repetir sin cambiar valores: cero valores y evento `no_changes`, sin nueva
   transacción. Probar CALCULAR verificando los parámetros que utilice ese flujo.
5. Comparar los conteos originales y confirmar que los detalles siguen presentes.
   Guardar y reabrir únicamente la copia si el responsable del turno lo autoriza.
   Registrar versión de Revit, commit del plugin y journal/log de esta prueba.
6. Si vuelve a cerrarse, detener los reintentos y correlacionar la última fase con
   el journal. No atribuirlo automáticamente a RAM o imports ni lanzar una purga.
