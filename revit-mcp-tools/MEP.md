# Auditoría MEP de solo lectura

Dos herramientas iniciales para inspeccionar proyectos antes de automatizar cambios.
Las herramientas previas del módulo cubrían principalmente arquitectura, estructura,
armado y documentación; no había una auditoría específica de sistemas o conectores MEP.

```python
revit_mep_inventario(disciplines=None, max_details=500)
revit_mep_conectividad(disciplines=["mechanical", "plumbing_fire", "electrical"], max_details=500)
```

También funcionan mediante `revit_ejecutar_tool(name="mep_inventario", params={})` y
`name="mep_conectividad"`. Reiniciar el servidor MCP para registrar los nuevos wrappers.
El ensamblador inyecta `_common.py`, `_mep.py` y el módulo solicitado. No abre transacciones.

## Alcance y resultados

- Categorías mecánicas: conductos rígidos/flexibles, accesorios, uniones, terminales y equipos.
- Hidrosanitarias e incendio: tuberías rígidas/flexibles, uniones, accesorios, aparatos y rociadores.
  Ambas comparten categorías; el nombre `plumbing_fire` no clasifica automáticamente el uso real.
- Eléctricas: equipos, aparatos, luminarias, dispositivos de iluminación/datos/comunicación/
  alarma/seguridad, bandejas, conduits, sus uniones y cables.
- Sistemas observados a través de los conectores y de `MEPModel.GetElectricalSystems()`.
  El conteo por sistema es de elementos observados, sin duplicar sus múltiples conectores.
- Conectores físicos `End`, `Curve`, `Physical`: `IsConnected=False` produce una observación
  para revisión. Otros tipos, incluidos los lógicos, se contabilizan sin consultar `IsConnected`.

`status` puede ser `complete`, `partial` o `no_elements_in_scope`. **Complete significa que
terminó la lectura del alcance, no que el proyecto cumple.** Errores de API producen `partial`
y se conservan por etapa. `max_details` (0–10000) limita listas de elementos, observaciones
y errores; los conteos agregados siguen recorriendo todo el alcance. `details_truncated`
indica cuándo faltan detalles. `systems` conserva el inventario completo de sistemas observados.

`OPEN_PHYSICAL_CONNECTOR`, `CONNECTORS_UNAVAILABLE`, `NO_CONNECTORS` y `NO_OBSERVED_SYSTEM`
son candidatos a revisión. Un extremo abierto puede ser intencional; conduits/bandejas o ciertas
familias pueden no tener un sistema. La ausencia de MEP en un archivo estructural no demuestra
que falte en el proyecto federado. Ante un error, la ausencia observada no es concluyente.

## Límites y validación

Solo documento activo, todas las fases y opciones de diseño: no consolida vínculos, no decide
la fase de entrega y no inspecciona familias genéricas usadas como sustitutos MEP ni piezas de
fabricación. No verifica interferencias, pendientes, caudales, presiones, cargas eléctricas,
circuitos completos, protección contra incendio, dimensionamiento ni cumplimiento normativo.
No crea tuberías, conductos, circuitos ni equipos. Los resultados requieren revisión profesional
y comparación con planos, memorias de cálculo y requisitos aplicables.

Pruebas offline con dobles del API:

```console
python -m unittest discover -s revit-mcp-tools/tests -v
```

Cubren conectores lógicos, sistemas compartidos, familias eléctricas, ausencia de datos,
lecturas parciales y límites de salida. **Pendiente: prueba de integración dentro de Revit**
con un modelo de referencia y verificación manual de los IDs y conteos. No se ha certificado
compatibilidad real con una versión concreta de Revit mediante estas pruebas offline.

Referencias del API Autodesk consultadas: [conectores](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API/files/Revit_API_Developers_Guide/Discipline_Specific_Functionality/MEP_Engineering/Revit_API_Revit_API_Developers_Guide_Discipline_Specific_Functionality_MEP_Engineering_Connectors_html.html),
[MEPModel y GetElectricalSystems](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/dd78bce5-2ed6-ed3c-f329-1663bf08afa6.htm).
