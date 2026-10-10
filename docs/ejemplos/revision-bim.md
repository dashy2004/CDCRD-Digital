# Ejemplo sintético: revisión BIM y auditoría MEP

Este ejemplo describe un flujo de uso de herramientas. **Todos los nombres y las entradas
siguientes son ficticios**, creados para explicar el método. No se ha ejecutado este escenario
como una revisión de un edificio real; no contiene capturas, conteos ni resultados de un
proyecto en desarrollo.

## Entradas didácticas

Supóngase un conjunto de documentos llamado `DEMO_COORDINACION`:

| Documento ficticio | Alcance supuesto |
|---|---|
| `DEMO_ARQ.rvt` | Arquitectura, niveles, recintos y elementos de cerramiento |
| `DEMO_EST.rvt` | Elementos estructurales y referencias de coordinación |
| `DEMO_MEP.rvt` | Conductos, tuberías y elementos eléctricos de demostración |
| `DEMO_REQUISITOS.ids` | Requisitos de información definidos para el ejercicio |

Estos archivos no se incluyen ni se afirma que existan. Para una prueba ejecutable, utilice
un modelo de referencia sintético preparado y guardado para ese fin. El ejemplo CAD local
sí incluye [una entrada JSON reproducible](../../herramientas-locales/ejemplos/planta-ejemplo.json).

## Recorrido propuesto

1. Registrar documentos, versiones, unidades y alcance. Decidir qué archivo contiene cada
   disciplina; la ausencia de tuberías en un archivo estructural no demuestra una omisión
   del conjunto.
2. Abrir el documento de referencia apropiado y consultar el inventario MEP de solo lectura.
3. Revisar conectores físicos abiertos y errores de lectura. Comprobar visualmente cada
   observación antes de calificarla como defecto.
4. Revisar los requisitos de información IFC/IDS cuando existan un IFC y un IDS de prueba.
5. Registrar criterio, evidencia, observación, responsable y siguiente comprobación.

Llamadas de ejemplo en un cliente MCP conectado a Revit:

```python
revit_mep_inventario(disciplines=["mechanical", "plumbing_fire", "electrical"], max_details=100)
revit_mep_conectividad(disciplines=["mechanical", "plumbing_fire", "electrical"], max_details=100)
```

Las firmas, límites y estado de pruebas se mantienen en la [documentación MEP](../../revit-mcp-tools/MEP.md).
Las llamadas leen el documento activo y no consolidan automáticamente los vínculos.

## Cómo interpretar observaciones hipotéticas

La tabla ilustra decisiones; **no representa una salida obtenida de las herramientas**.

| Situación hipotética | Interpretación y siguiente paso |
|---|---|
| No se observan elementos MEP | Confirmar documento, vínculos, categorías y alcance antes de concluir que faltan instalaciones |
| Aparece `OPEN_PHYSICAL_CONNECTOR` | Localizar el elemento y decidir si el extremo abierto es intencional |
| La lectura devuelve `partial` | Revisar los errores; una ausencia observada no es concluyente |
| La lectura devuelve `complete` | Terminó la lectura del alcance; no certifica cumplimiento del diseño |
| La lista tiene `details_truncated` | Solicitar un alcance o límite apropiado para revisar detalles; no confundir la lista limitada con los conteos agregados |

## Plantilla de registro

| Disciplina | Comprobación propuesta | Evidencia necesaria | Estado inicial |
|---|---|---|---|
| Arquitectura | Coherencia de niveles y recintos | Inventario, vistas y requisitos definidos | Por ejecutar |
| Estructura | Correspondencia entre elementos y documentación | Modelo, planos y criterios de revisión | Por ejecutar |
| Hidrosanitaria / incendio | Inventario y conectividad observada | Lectura MEP y revisión del alcance de cada sistema | Por ejecutar |
| Mecánica | Equipos, conductos y terminales | Lectura MEP y comprobación visual | Por ejecutar |
| Eléctrica | Elementos y sistemas observados | Lectura MEP y documentación de circuitos | Por ejecutar |

La auditoría inicial no dimensiona sistemas ni verifica caudales, presiones, pendientes,
ventilación, cargas eléctricas, interferencias o cumplimiento normativo integral. Esas
revisiones requieren criterios y datos adicionales. Un informe debe distinguir una operación
completada, una observación pendiente y una comprobación de ingeniería sustentada.

[Volver al README](../../README.md) · [Herramientas locales](../../herramientas-locales/README.md)
