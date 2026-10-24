# Auditoría de apoyos y propuesta geométrica de nervios

La herramienta `revit_apoyos_losa(config)` inspecciona una copia autorizada sin transacción, guardado o edición de elementos. En una conexión MCP ya abierta puede usarse el despacho existente:

```python
revit_ejecutar_tool(name="apoyos_losa", params=config)
```

El catálogo de módulos se relee con `revit_listar_tools`; añadir el archivo permite ese despacho inmediatamente. El wrapper dedicado se anuncia al abrir una conexión MCP nueva.

## Contrato y alcance

```json
{
  "action": "inspect",
  "expected_path": "D:\\Pruebas\\MODELO_COPIA.rvt",
  "expected_pid": 12345,
  "protected_paths": [
    "D:\\Originales\\MODELO.rvt"
  ],
  "lock_path": "D:\\Pruebas\\revit-session.lock",
  "lock_identity": {
    "owner": "operador",
    "session": "sesion-de-prueba",
    "task": "auditar-apoyos"
  },
  "floor_ids": [
    1001
  ],
  "rib_candidate": {
    "height_m": 0.2,
    "topping_m": 0.05,
    "block_m": 0.5,
    "rib_m": 0.15,
    "border_m": 0.3
  }
}
```

El lock debe estar activo y coincidir en identidad y PID. Solo una losa rectangular alineada con XY, sin huecos interiores, sin edición de forma y de espesor horizontal constante. Se rechaza cualquier acción distinta de inspect. Se informa el estado Modified anterior/posterior y se aborta si cambia durante la consulta.

- Apoyos: sólidos de StructuralFraming y StructuralColumns, a 1 mm bajo la cara inferior; cuatro líneas de borde y cinco cuerdas por dirección. Los intervalos se unen para no contar dos veces apoyos superpuestos. Las cuerdas son muestras, no certifican contacto de toda una superficie.
- Los muros no se contabilizan como apoyos. Los huecos son distancias entre los sólidos de las categorías consultadas, **no una selección automática de la luz normativa**.
- Se informan secciones, materiales y módulo elástico nativo, perfiles vecinos, volumen, cortadores y Rebar directamente hospedado. No certifica ausencia de todas las clases de refuerzo.
- El contacto o un paño vecino no prueba continuidad de momentos, anclaje o validez del diseño.

`rib_candidate` es opcional y **nunca cambia el Floor**. Define una grilla centrada de bovedillas completas, máximo 150; el margen dado es mínimo, y se devuelven los márgenes reales. Se comprueban posibles cruces con muros, vigas y columnas del documento mediante cajas y, cuando coinciden, intersección booleana de sólidos temporales. No se evalúan vínculos u otras categorías. Cero pruebas booleanas con cajas disjuntas constituye ausencia de intersección en ese ámbito. `intersection_sum_m3` es suma de intersecciones, no volumen de unión.

Los sólidos temporales no pertenecen al documento. No se crea ninguna bovedilla ni cantidad de obra. Fallos de geometría se propagan; no se convierten en “sin colisiones”. Los límites de 80 obstáculos/apoyos se comprueban antes de acumular geometría, liberada mediante finally.

## Pruebas

```powershell
python -m pytest revit-mcp-tools/tests -q
```

Cobertura: intervalos solapados, recorte, huecos, datos no finitos, acción de escritura rechazada, grilla centrada, nervios/márgenes y límites de tamaño. La aceptación nativa se mantiene privada:

- escenario geométrico: 80 celdas completas, sin interferencias de las categorías consultadas;
- control negativo deliberadamente inválido: 108 celdas temporales, 18 intersecciones detectadas; no aplicado;
- comparación posterior: sin cambios de geometría o parámetros físicos, tags o imports;
- conexión nueva: 46 wrappers; cliente existente: estado y nuevos módulos por despacho genérico.

No son ensayos de resistencia, flecha, cortante o aprobación de armado. La herramienta no selecciona espesores.

## Compatibilidad del puente pyRevit

El servidor envía JSON con Content-Type application/json. Un cliente antiguo en memoria puede seguir enviando text/plain y obtener `'bytes' object has no attribute 'get'` del receptor nativo.

`maintenance/bridge_request_compat.py` prepara un cambio acotado del parser: admite dict, texto y bytes UTF-8, rechaza JSON no objeto. Es una función pura: no instala, no registra rutas, no ejecuta código del payload ni escribe modelos. Rechaza versiones desconocidas y aplicación repetida.

Despliegue probado, bajo turno exclusivo y con copia identificada:

1. Respaldar el módulo nativo completo y conservar SHA256 de origen y candidato.
2. Comprobar que el origen sigue coincidiendo; instalar solamente el candidato revisado.
3. Cargar ese módulo y registrar su única ruta mediante la API pública de pyRevit. Conservar la referencia del handler anterior.
4. Verificar que las 18 claves de rutas se conservan y los otros 17 handlers mantienen identidad. Ante fallo, restaurar el handler anterior y registrar el resultado.
5. Probar estado desde el cliente antiguo y despacho de un módulo nuevo. Abrir conexión nueva para verificar anuncio de wrappers.
6. Para revertir en disco, exigir el hash del candidato instalado y restaurar los bytes del respaldo; recargar únicamente el handler respaldado o reiniciar normalmente cuando sea seguro. No matar procesos con operaciones en curso.

Los recibos privados deben consignar started antes del despacho, éxito/fracaso, hashes, rutas comparadas y estado del documento. No reintentar una escritura con resultado desconocido. Si el add-in se actualiza, revisar el parser nuevo; no aplicar el parche por similitud.

Para el arnés stdio se usa el MCP SDK 1.x compatible con este servidor (`mcp>=1.10,<2`). Una ejecución de diagnóstico con SDK 2.3 falló durante la conexión; la versión instalada 1.30 completó catálogo y lectura nativa. Esto no exige cambiar la configuración del usuario ni reiniciar Revit.

Referencias: [Autodesk Solid.IntersectWithCurve](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/8e04f956-b262-7f3e-59cb-d2c02c2769d7.htm); contratos de GeometryCreationUtilities/BooleanOperationsUtils contrastados con RevitAPI.xml instalado.
