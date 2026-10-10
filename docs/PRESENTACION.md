# Presentación del repositorio y evidencia visual

La portada conecta tres piezas: la norma de origen, las herramientas y los casos con
resultados verificables. El [README](../README.md) es el punto de entrada; los informes
contienen el detalle y las limitaciones de cada revisión.

## Casos publicados

| Caso | Contenido | Evidencia y alcance |
|---|---|---|
| Residencial BIM, identificación anónima | Coordinación de arquitectura, estructura e instalaciones | [Informe multidisciplinar](casos/residencial-bim/INFORME.md); consultar sus estados de verificación |
| Demostración ETABS de oficinas | Tres niveles y dos por dos crujías de seis metros | [Protocolo R01–R10](../revision/RESUMEN-CAPTURAS-2026-08-08.md); caso independiente del residencial |
| Ejemplo Revit residencial de cuatro niveles | Receta de modelado y documentación | [Ejemplo reproducible](../revit-mcp-tools/ejemplos/residencial-4n/); nombres inventados, distinto del caso BIM revisado |

## Galería del caso residencial

Las imágenes se incorporan cuando exista una exportación comprobada del modelo correspondiente.
Cada pie incluirá disciplina, vista, fecha de exportación y alcance de lo que muestra.

La portada incluye dos miniaturas de 128 × 128 píxeles extraídas del contenedor de los archivos
RVT guardados, sin transformación de píxeles. La arquitectónica muestra una vista del edificio;
la estructural, una planta. Se revisaron visualmente antes de incorporarlas y no muestran
nombres ni rutas. No permiten comprobar medidas, detalle constructivo, estado actual de la
sesión ni cumplimiento. Su fecha interna de captura no está verificada.

| Imagen prevista | Qué debe mostrar | Estado |
|---|---|---|
| Revit / arquitectura | Volumen exterior y una planta legible | Pendiente de exportación y revisión |
| Revit / estructura | Estructura aislada y un detalle de coordinación | Pendiente de exportación y revisión |
| Revit / MEP | Sistemas por disciplina, con leyenda | Pendiente de evidencia de modelos MEP |
| ETABS | Modelo analítico y resultados ligados al informe | Pendiente para este caso |
| SAFE | Cimentación y resultado con unidades y combinación | Pendiente para este caso |

Una imagen CAD puede documentar un plano fuente si su pie lo identifica como tal. No se
presenta como captura de Revit ni como prueba de que el modelo reproduce ese plano.
Una vista tridimensional muestra geometría; el cumplimiento requiere además datos,
criterios, cálculos y resultados revisados.

## Criterios de publicación

- Usar exportaciones del área del modelo, preferiblemente sin interfaz de la aplicación.
- Revisar nombres de sesión, títulos, rutas, cajetines, matrículas y otros identificadores
  antes de incorporar una imagen nueva a la portada.
- Conservar la geometría, las leyendas, los valores y las unidades de la evidencia original.
- Enlazar cada imagen al informe o paso que explica qué fue verificado.
- Distinguir resultados del caso, demostraciones de herramientas y material pendiente.
- Mantener modelos y documentación de trabajo en sus proyectos. Publicar únicamente la
  selección autorizada y anonimizada del caso, conforme al alcance acordado.

Las capturas históricas de ETABS conservan la interfaz de la aplicación y requieren revisión
de privacidad antes de reutilizarse en una nueva galería. En esta actualización se enlaza
su protocolo existente; las únicas imágenes nuevas del caso residencial son las miniaturas
embebidas de los archivos RVT, claramente identificadas en la portada.

## Datos de presentación en GitHub

Propuesta de descripción breve del repositorio:

> Código de Construcción de RD con fuentes trazables y herramientas BIM para Revit, ETABS y SAFE.

Temas sugeridos: `bim`, `revit`, `etabs`, `safe`, `mcp`, `structural-engineering`,
`building-codes`, `dominican-republic`.

La descripción y los temas son configuración de GitHub. Este documento los propone;
no afirma que ya estén aplicados.
