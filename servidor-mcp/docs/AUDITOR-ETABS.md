# Captura automática e informe del auditor ETABS

La captura lee una instancia **ya abierta, fijada por PID y ruta absoluta del EDB**.
El informe reutiliza `modeling_checks.audit_modeling` y el perfil existente
`modeling_20261015`. Clasifica diferencias comprobadas, datos pendientes y errores de
lectura. No aplica cambios, ejecuta análisis, selecciona resultados, cambia unidades,
guarda ni abre otro modelo. La generación de informes también funciona sin Windows
ni COM, a partir de un JSON capturado.

## Uso por consola

Desde la raíz del repositorio, con Python y las dependencias de
`servidor-mcp/requirements.txt` instaladas. Para captura nativa se necesita Windows,
ETABS con licencia y Python de la arquitectura compatible con ETABS.

1. Preparar un JSON `project.json` con `profile` y `project`. Hay un ejemplo
   **sintético**, sin datos de clientes, en [examples/audit/project.json](../examples/audit/project.json).
   Ajustar explícitamente ruta, uso, niveles y demás datos del proyecto según
   [PROCEDIMIENTO-ETABS.md](PROCEDIMIENTO-ETABS.md). El perfil es un procedimiento
   particular; no convierte sus criterios en reglas universales de ingeniería.
2. Verificar el modelo abierto, el PID y el turno exclusivo de esa aplicación.
   Mantener ETABS sin edición durante toda la captura. La herramienta no impone un
   bloqueo al operador ni asegura una instantánea atómica.
3. Ejecutar, con valores propios y una carpeta de salida absoluta **nueva**:

```powershell
python servidor-mcp/tools/etabs_audit.py capture `
  --pid 12345 --project C:\Trabajo\project.json `
  --modal-case Modal --output C:\Trabajo\auditoria-001
```

`--modal-case` es opcional: si se omite, los modos quedan pendientes. No se deduce
el caso modal por su nombre. `--max-objects` limita cada inventario/array (10 000
por defecto, máximo 20 000). Las lecturas que excedan el límite se registran como
error, nunca como colecciones vacías o truncadas. Hay un límite de 200 000 llamadas.
No hay un timeout que pueda cancelar una llamada COM nativa bloqueada.

Para probar el informe sin ETABS (Windows o Linux; sustituir la salida por una ruta
absoluta de su sistema):

```powershell
python servidor-mcp/tools/etabs_audit.py report `
  --project servidor-mcp/examples/audit/project.json `
  --snapshot servidor-mcp/examples/audit/capture.json `
  --output C:\Trabajo\auditoria-demo-001
```

El ejemplo se identifica como `synthetic_fixture`, con fecha y PID ficticios.
Incluye una losa Membrane y patrones faltantes para mostrar diferencias frente al perfil.
No acredita una ejecución nativa. El comando devuelve código 0 cuando entrega el
paquete, **aunque el informe tenga diferencias o pendientes**; consultar `overall`
y `summary`. Código 1 indica fallo de captura/escritura/validación y código 2, uso
incorrecto de la consola.

## Herramientas MCP

- `capture_etabs_audit_snapshot(expected_model_path, modal_case="", max_objects=10000)`:
  método STA del adaptador ETABS. Exige `process_id` positivo configurado y
  `auto_start=False`; no recurre a otra instancia. Devuelve el objeto de captura.
- `write_etabs_audit_report(profile, project, capture, output_directory)`:
  generador independiente, registrado junto a las herramientas existentes.
  Escribe el paquete en una carpeta nueva y devuelve su ubicación, resumen y hashes.

La captura no modifica la configuración de conexión existente del servidor. Para
el servidor MCP se usa `ETABS_PROCESS_ID` o `fea.process_id` en su
`src/config.json`, manteniendo `fea.auto_start=false`; la CLI anterior configura
directamente el PID de su adaptador. No ejecutar dos capturas
simultáneas contra la misma instancia.

## Contenido y evidencia

| Archivo | Contenido |
|---|---|
| `proyecto.json` | Perfil y referencia proporcionada, para reproducir la comparación |
| `captura.json` | Identidad, unidades, inventarios y evidencia por lectura |
| `informe.json` | Hallazgos, valores esperados/leídos, estados y referencias de evidencia |
| `informe.html` | Informe estático en español, sin scripts ni recursos externos |
| `manifest.json` | SHA-256 de los cuatro archivos; se escribe al terminar |

El marcador `INCOMPLETE` permanece si una escritura falla. La herramienta rechaza
una carpeta existente y no reemplaza entregas. Un manifiesto completo acredita la
escritura del paquete, no la integridad del diseño. Los hashes detectan cambios
posteriores; no autentican al productor del JSON.

Cada lectura conserva operación, argumentos, objeto, campo, ID y estado: `read`,
`unavailable`, `error` o `pending`. Un `ret` distinto de cero, arrays incoherentes,
valores no finitos o tipos incorrectos producen evidencia de error. Cero y lista
vacía solo se aceptan si la API los devolvió con contrato válido. Una propiedad no
leída permanece ausente. El HTML escapa nombres, mensajes y valores aportados.

| Se captura | Límite de interpretación |
|---|---|
| Ruta, PID, versión, unidades, bloqueo; niveles del tower activo y base | Controles de identidad/unidades/bloqueo antes y después; no detectan toda edición concurrente |
| Nudos, XYZ, restricciones, diafragmas y niveles | Geometría convertida a metros sin llamar a `SetPresentUnits` |
| Barras, extremos, sección y factor de zona rígida | No se verifica dimensionamiento resistente de las barras |
| Áreas, vértices, Floor/Wall, huecos, sección, nivel, diafragma | Áreas sin clasificación se conservan explícitamente |
| Definiciones de losas, material, tipo shell y espesor; Ribbed/Waffle | Incluye propiedades sin asignar; no interpreta planos |
| Materiales (nombre/tipo), patrones y peso propio | No se atribuyen propiedades mecánicas no leídas |
| Cargas uniformes y uniformes a barras | Valores conservan fuerza/longitud² activas; no se adivinan acabados o mampostería |
| Fuente de masa predeterminada, máximo de modos del caso elegido | Tablas con esquema desconocido quedan como error |
| Estado de casos de análisis | `Finished` no demuestra vigencia frente a todas las ediciones |

Quedan pendientes el mallado nativo, P-Delta global, cotejo de curva/casos espectrales,
Check Model, reapertura del EDB, cuerpos estructurales, apoyos y dirección resistente,
y la correspondencia semántica con planos. No se ejecutan para completar casillas.
El informe no es certificación normativa, análisis estructural nuevo ni aprobación
para construcción. Los paquetes reales contienen rutas y datos privados; mantenerlos
fuera de GitHub. Solo el código y el ejemplo sintético son públicos.

## REA y contratos verificados

Se utilizó [REA](https://github.com/morluto/rea) 6.5.0 el 2026-10-22 mediante
`inspect-managed-artifact` e `inspect-managed-members` sobre la biblioteca instalada
`ETABSv1.dll` de ETABS 23. No se incorpora REA como dependencia de ejecución. Se
inspeccionaron tipos seleccionados y firmas públicas; no se publica la DLL,
implementación descompilada ni el volcado privado de la inspección.

- SHA-256 del artefacto: `92f6e9b7d0f03cb9b650c379e739b8b193806c6501b37ae7c42f1965ec842893`.
- MVID: `214c708b-592e-4e25-a036-6968485fda92`.
- Evidencia de artefacto: `ev_dd6a7ea695f80389a2383a3c356eb1286696c42f69dd1e786a760bef492900aa`.
- Evidencia de miembros: `ev_92f11c92c7de829989c5e1c7774e6b3a74a85369169ad6b9affa22d3885601f5`.
- Tipos seleccionados: `cAreaObj`, `cAnalyze`, `cPropArea`, `eSlabType`,
  `eShellType`, `eAreaDesignOrientation`; cobertura seleccionada completa.
- Se contrastaron también las firmas del typelib COM generado, sin conectar una
  instancia, y los valores de enums mediante reflexión de metadatos.

Hallazgo relevante: `AreaObj.GetAutoMesh` existe en el catálogo de la API compartida,
pero no en el contrato `ETABSv1.cAreaObj` inspeccionado. Por eso el mallado queda
pendiente. Las firmas usadas incluyen `GetStories_2` con base separada,
`GetLoadUniform` con cinco arrays, `GetLoadUniformToFrame` con seis y
`PointObj.GetDiaphragm` con opción y nombre. No se reutilizan layouts de SAP2000 ni
del antiguo `GetStories`. El contrato se rechaza si la versión de ejecución devuelve
una forma diferente. La inspección de firmas **no demuestra una captura nativa**.

## Validación reproducible

```text
python -m pip install pytest "mcp>=1.10,<2"
python -m pytest servidor-mcp/tests -q
```

GitHub Actions ejecuta esa suite completa en Linux. Las pruebas usan modelos
sintéticos y cubren identidad/PID, despacho STA, cambios entre extremos, límites,
retornos fallidos, unidades, masa, Ribbed/Waffle, Eigen/Ritz, valores desconocidos,
escapado HTML, carpeta no sobrescribible, hashes, escritura parcial, CLI sin COM y
registro real del SDK MCP. No inicia ETABS, SAFE ni Revit.

Validación inicial local: Windows/Python 3.14 con SDK MCP, 373 pruebas aprobadas;
Linux/Python 3.12, 371 aprobadas y 2 omitidas por SDK MCP ausente. Cobertura de los
módulos nuevos de captura/informe/MCP: 91%. Ruff y Pyright sin errores en los módulos
nuevos. La aceptación nativa sigue pendiente: ejecutar en una copia identificada,
cotejar conteos/propiedades contra ETABS y comprobar que el documento permaneció
sin modificación. No confundir las pruebas sintéticas con esa aceptación.
