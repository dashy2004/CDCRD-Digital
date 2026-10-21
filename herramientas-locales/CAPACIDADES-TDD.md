# Evidencia TDD: catálogo y diagnóstico

Fecha: 2026-10-21. Fuente: solicitud de implementar y publicar el catálogo y
diagnóstico reutilizando las herramientas existentes. Ejemplos sintéticos.

## Recorridos y garantías

| Recorrido | Garantía | Prueba |
|---|---|---|
| Consultar capacidades | IDs únicos, contratos, fuentes y evidencia por módulo; filtro explícito | `CatalogTests` |
| Diagnosticar una máquina | Reutiliza doctor; código/configuración no se convierten en instalación o conexión | `StateTests` |
| Leer configuración opcional | JSON/TOML acotados, errores explícitos y valores privados omitidos | `StateTests` |
| Usar CLI | JSON válido, selección de módulo y errores con código de salida | `CLITests` |
| Usar un cliente MCP | Lista 12 herramientas, consulta catálogo y estado, mantiene búsqueda y DXF | `test_real_mcp_stdio_search_path_boundaries_and_dxf` |

Los tres primeros grupos y la CLI están en `tests/test_ecosystem.py`; la
integración real por stdio está en `tests/test_integration.py`.

## RED y GREEN

1. Dos contratos ejecutados fallaron porque `cdcrd_local.capabilities` y el
   comando `capacidades` aún no existían. Checkpoint RED: `b48e0bc`.
2. Implementación mínima: los 14 casos nuevos pasaron en Windows/Python 3.13.
   Checkpoint GREEN: `86ce8ad`.
3. Un contrato adicional mostró dos fallos: `ok` no reflejaba configuración
   explícita ausente/inválida. Checkpoint RED: `c807cec`.
4. Se corrigió ese estado y se comprobó la compatibilidad MCP tanto con
   `structuredContent` como con JSON en bloques de texto. Resultado: **60
   pruebas y 14 subpruebas aprobadas**, Ruff sin hallazgos y **98 %** de
   cobertura de líneas en `capabilities.py` (99 sentencias, 2 sin ejecutar).

## Comandos de validación

Se utilizó el entorno Python 3.13 ya instalado, con `PYTHONPATH` apuntando al
`src` del checkout de prueba. Las operaciones ejecutadas fueron:

```console
python -m unittest test_ecosystem.CatalogTests.test_inventory_has_stable_metadata test_ecosystem.CLITests.test_catalog_cli_is_json
python -m unittest discover -s tests -p test_ecosystem.py -q
python -m ruff check src tests
python -m coverage run --source=cdcrd_local -m pytest -q
python -m coverage report --include="*/capabilities.py" --show-missing --fail-under=80
```

El primer comando se ejecutó desde `tests`; el resto desde
`herramientas-locales`. Coverage se cargó desde un directorio temporal, sin
modificar las dependencias ni `uv.lock`. La CI portable ejecuta únicamente el
archivo `test_ecosystem.py` con la biblioteca estándar; los paquetes opcionales
ausentes deben producir un diagnóstico negativo, no impedir la prueba.

## Límites

No se activaron Revit, ETABS, SAFE, Civil 3D ni AutoCAD. La prueba MCP valida
el transporte por stdio y operaciones locales, no aplicaciones BIM vivas.
La cobertura indicada corresponde al módulo nuevo y es de líneas, no de ramas.
El registro representa contratos por módulo, no un inventario exhaustivo de
métodos API ni una certificación de disponibilidad en producción.
