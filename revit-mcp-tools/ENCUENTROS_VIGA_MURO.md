# Encuentros viga-muro

`revit_encuentros_viga_muro` corrige avisos de elemento completamente contenido
en otro mediante aberturas rectangulares nativas en muros no estructurales.
Retira la union viga-muro redundante despues de crear la abertura. No escribe
parametros de vigas ni elimina elementos mediante `Document.Delete`.

## Contrato

- Unico operador: `lock.path` apunta al JSON del turno; `owner`, `session`, `task`,
  estado activo y PID deben coincidir. El llamador adquiere/mantiene/libera el turno.
- Ruta exacta de la copia en `expected_document`, proceso en `expected_pid` y lista
  no vacia de originales en `protected_documents`. Rechaza originales y documentos
  compartidos, familias, transacciones abiertas o documentos de solo lectura.
- `pairs`: entre 1 y 20 pares `[wall_id, beam_id]`; un muro por par, ejes rectos,
  horizontales y paralelos, muro basico no estructural sin perfil editado ni grupo.
- `dry_run=True`: realiza el ensayo completo en un TransactionGroup y revierte.
  Los IDs de aberturas devueltos por el ensayo son provisionales, no persistentes.
- Para aplicar: `dry_run=False`, `allowed_column_floor_joins` exactamente igual al
  plan comprobado y `allowed_native_cleanup_ids` con los registros internos
  inspeccionados. No son permisos generales para borrar elementos.
- No guarda. `applied_unsaved` exige guardado y comprobacion de reapertura por el
  llamador. `already_resolved` no crea aberturas adicionales.

## Por que se comprueban tambien columnas y losas

Un muro puede participar en uniones con columnas. Crear una abertura cambia el
recorte parametrico del muro aunque su solido final sea identico al anterior.
Revit puede regenerar las columnas adyacentes. Si aumenta una interseccion
columna-losa, la herramienta propone una union donde la losa corta a la columna.
Solo se admiten columnas que ya estaban unidas a un muro objetivo; sus parametros
editables se conservan. Toda diferencia de solidos se cuantifica en el recibo.

La herramienta aborta si cambia cualquier otro solido controlado (incluidas
vigas, losas y muros), cambian parametros de vigas o tags, desaparece un elemento
de modelo/documentacion, aumenta un solape o aparecen avisos distintos.

Los avisos pueden tener registros internos `Autodesk.Revit.DB.Element` sin
categoria, nombre, tipo, vista, caja ni parametros editables. Su desaparicion
nativa se registra y exige una lista exacta al aplicar. No se suprimen avisos
mediante un procesador de fallos: cualquier nuevo fallo revierte la transaccion.

## Geometria y limites

- Booleanos de diferencia simetrica antes/despues, no solo volumen o bounding box.
- Todas las vigas, columnas, muros y losas nativos, mas solidos de categorias de
  modelo dentro de las cajas de los muros ampliadas 1 pie. Limite de 4000 candidatos.
- Comprueba cada solido modificado contra el conjunto capturado; tambien detecta
  aumentos de solapes preexistentes. No afirma eliminar interferencias anteriores.
- Tolerancia de volumen `1e-7 ft3` (aprox. `2.83e-9 m3`). Unidades internas Revit.
- Importaciones CAD y vinculos se enumeran como excluidos; no se inspecciona su
  contenido geometrico. Un booleano fallido provoca rollback, nunca un cero falso.
- No cubre muros curvos, encuentros inclinados, varios pares por muro, ni cambios
  posteriores de posicion de las vigas. Las aberturas son nativas pero no tienen
  una restriccion asociativa que las desplace automaticamente con la viga.
- No es una comprobacion ni aprobacion de calculo estructural.

## Integracion y pruebas

Modulo compatible con el contexto IronPython de pyRevit:
`src/tools/encuentros_viga_muro.py`, funcion `run(doc, uidoc, DB, P)`.
La funcion MCP esta registrada en `src/server.py`. El servidor instalado necesita
adoptar esta revision; ejecutar el nucleo por el puente Python no demuestra que
la herramienta nueva ya este cargada en todos los clientes MCP.

```powershell
python -m unittest discover -s revit-mcp-tools/tests -v
```

Pruebas offline: documento protegido, PID/operador incorrectos, turno liberado,
pares invalidos, plan exacto de uniones y aumentos de interseccion.
Validacion nativa en una copia privada: ensayo revertido, rechazo deliberado de
aplicacion sin plan, aplicacion, segunda llamada idempotente, guardado y reapertura
con comparacion booleana. El modelo, IDs reales, rutas y recibos privados no se
incluyen en el repositorio publico.

La capa de transporte HTTP preexistente se conserva en esta revision; esta prueba
no certifica sus variantes de content-type ni corrige otros errores del servidor.
