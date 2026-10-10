# Caso residencial: revisión BIM y preparación de coordinación MEP

**Estado:** revisión documental en desarrollo. **Corte:** octubre de 2026.
Este caso anónimo muestra cómo relacionar evidencia CAD, información BIM y tareas de revisión. La información pública se limita al método y a las brechas de evidencia; los modelos y el expediente detallado permanecen fuera del repositorio.

[Descargar informe en PDF](INFORME.pdf) · [Auditoría MEP disponible](../../../revit-mcp-tools/MEP.md)

## Resultado de la revisión

La documentación disponible permite contrastar detalles arquitectónicos y estructurales y formular acciones concretas de coordinación. **No permite acreditar cumplimiento integral del proyecto.** Faltan comprobaciones independientes del estado del modelo, entregables de instalaciones y memorias de análisis vinculadas a la misma revisión.

“No evaluable” significa que no hay datos suficientes para decidir si cumple o incumple. Una contradicción entre documentos es un hallazgo de coordinación, mientras que un incumplimiento de diseño exige un criterio aplicable y evidencia directa del elemento evaluado.

| Frente | Evidencia de esta revisión | Conclusión permitida |
|---|---|---|
| Arquitectura | Archivos BIM y documentación CAD disponibles. | Es posible preparar el cotejo; no se acredita todavía el cumplimiento funcional o normativo. |
| Estructura | Detalles y notas recuperados del CAD; cambios de modelado registrados. | Las prescripciones documentales son trazables; los cambios deben releerse por host y resolverse las contradicciones. |
| Hidrosanitaria, eléctrica y mecánica | No se identificó un paquete suficiente de instalaciones dentro del expediente revisado. | No evaluable; se requieren modelos, planos y memorias por especialidad. |
| Protección contra incendios | Alcance y documentación técnica insuficientes para esta revisión. | No evaluable; establecer aplicabilidad y estrategia según las condiciones del proyecto. |
| Análisis estructural y cimentaciones | Sin resultados de cálculo del caso vinculados a la revisión BIM. | No evaluable; no se presentan resultados de ejemplos ajenos como propios. |
| Coordinación integrada | Información todavía incompleta para una federación multidisciplinaria. | Pendiente comprobar coordenadas, reservas, interferencias y espacios de mantenimiento. |

## Método de trabajo

1. **Preservar fuentes.** Convertir copias del CAD, comprobar su integridad y conservar tanto el texto como las entidades originales. Los renders ayudan a interpretar, pero no sustituyen cotas o notas.
2. **Recuperar evidencia localizable.** Identificar archivo, entidad/handle, texto y coordenada. Separar cantidades de rótulos de cantidades físicas de componentes.
3. **Detectar contradicciones.** Registrar diferencias entre notas, detalles e instrucciones de modelado. Una automatización no debe escoger silenciosamente entre materiales, recubrimientos o reglas de armado incompatibles.
4. **Exportar el estado BIM.** Obtener una revisión identificada con categorías, tipos, niveles, materiales, hosts, geometría y avisos. Verificar el resultado de cada edición y conservar las relaciones entre elementos.
5. **Revisar sistemas MEP.** Inventariar equipos y redes, comprobar pertenencia a sistemas y generar candidatos de conectividad. Un conector abierto puede ser intencional; necesita contexto antes de convertirse en incidencia.
6. **Coordinar y calcular.** Resolver unidades y transformaciones antes de comparar geometría. Contrastar capacidad y desempeño con memorias; las propiedades de un modelo por sí solas no demuestran suficiencia.
7. **Cerrar con evidencia.** Registrar criterio, resultado, responsable y prueba posterior a la corrección. Mantener separadas la validación del software y la revisión del diseño.

## Criterios de aceptación propuestos

| Puerta de revisión | Evidencia necesaria para cerrarla |
|---|---|
| Fidelidad de modelado | Elementos comparados con su fuente; diferencias justificadas y geometría releída/exportada después del ajuste. |
| Coherencia documental | Fuente aprobada para cada contradicción; revisión y responsable identificados. |
| Preparación MEP | Modelos y cálculos por especialidad; redes y equipos inventariados; conectividad y terminales previstos revisados. |
| Coordinación espacial | Coordenadas/niveles/fases compatibles; reglas y tolerancias definidas; incidencias geométricas y de mantenimiento resueltas. |
| Revisión normativa | Aplicabilidad y versión establecidas; cada comprobación enlazada a fuente primaria, entrada, unidad, límite, resultado y responsable. |
| Publicación de resultados | Figuras y tablas del propio caso con revisión y procedencia; sin datos personales ni resultados de otros ejemplos atribuidos al proyecto. |

## Evidencia visual y siguientes entregas

Las vistas CAD son renders de documentación fuente. Se recuperaron además miniaturas de 128×128 embebidas en archivos RVT guardados: su procedencia es Revit, pero no son exportaciones nuevas de vistas ni sirven para auditar geometría. Las capturas ARQ/EST de mayor resolución deben corresponder a una revisión exportada. La evidencia ETABS/SAFE de este caso se incorporará cuando existan modelos y resultados propios comprobados; su inclusión pendiente no se presenta como trabajo finalizado.

Las siguientes entregas son el inventario verificable del modelo, el cotejo de geometría y parámetros, la resolución de fuentes contradictorias y los insumos MEP. Este caso documenta un proceso auditable de revisión, sin anunciar una certificación que la evidencia disponible aún no permite emitir.
