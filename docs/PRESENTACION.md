# Presentación del repositorio

El [README](../README.md) conecta normativa trazable, herramientas y ejemplos reproducibles.
La documentación pública explica capacidades y límites mediante datos sintéticos. Los
expedientes BIM que se están desarrollando se mantienen en sus proyectos privados.

## Ejemplos de la portada

| Ejemplo | Contenido |
|---|---|
| [Revisión BIM sintética](ejemplos/revision-bim.md) | Flujo didáctico de cobertura por disciplina y auditoría MEP |
| [Demostración ETABS](../revision/RESUMEN-CAPTURAS-2026-08-08.md) | Protocolo existente R01–R10 de herramientas y resultados |
| [Revit residencial de cuatro niveles](../revit-mcp-tools/ejemplos/residencial-4n/) | Receta de modelado con nombres inventados |
| [Herramientas locales](../herramientas-locales/README.md) | Planta CAD sintética, IFC/IDS y consultas normativas |

## Evidencia visual

Las nuevas imágenes públicas deben proceder de ejemplos sintéticos y llevar un pie que
identifique herramienta, operación, versión y alcance de la comprobación. Revisar nombres
de sesión, rutas y otros identificadores antes de añadir una captura. Preferir exportaciones
del área del modelo y conservar valores, unidades y leyendas.

Las capturas históricas ETABS se consultan en su protocolo existente. Algunas conservan
identificadores de interfaz; necesitan revisión antes de reutilizarse en una galería nueva.
No se publican modelos, planos, miniaturas, informes ni resultados del proyecto BIM actual.
Tampoco se convierten sus datos en ejemplos mediante un simple cambio de nombre.

## Descripción y temas de GitHub

**About**, aplicado el 10 de octubre de 2026:

> Código de Construcción de RD con fuentes trazables y herramientas BIM para Revit, ETABS y SAFE.

Temas aplicados: `bim`, `revit`, `etabs`, `safe`, `mcp`, `structural-engineering`,
`building-codes`, `dominican-republic`.

La descripción y los temas se comprobaron en GitHub el 10 de octubre de 2026; ya
están aplicados. No se anuncia una página web, paquete publicado o release que no exista.

## Distribución y reconocimiento

`herramientas-locales/pyproject.toml` define el paquete Python `cdcrd-local`, sus dependencias
y entradas `cdcrd-local` / `cdcrd-local-mcp`. La vía documentada es la instalación desde el
repositorio con `uv.lock`; véase [instalación](../herramientas-locales/README.md#instalación).
La existencia de metadatos de paquete no acredita publicación en PyPI o GitHub Packages.

**Asistencia de código y documentación: OpenAI Codex.** El historial permite atribuir cambios
concretos; no se inventa una identidad personal ni una cuenta de contribuidor.
