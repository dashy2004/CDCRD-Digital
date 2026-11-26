# Revisión de estado de PR y pendientes

Corte consultado: 2026-10-27 (noche local). Es una conciliación documental y de
evidencias, no una aprobación de todos los cambios de código ni una orden de merge.
Los estados se deben volver a consultar antes de integrar.

| PR | Revisión consultada | Estado y siguiente paso |
|---|---|---|
| [#6](https://github.com/dashy2004/CDCRD-Digital/pull/6) | `fcbdbf4` | Abierto. Revisar si el texto de protección aún refleja la configuración vigente. La respuesta de checks contiene un registro `in_progress` con conclusión `success`; no se interpreta como un estado final coherente. |
| [#9](https://github.com/dashy2004/CDCRD-Digital/pull/9) | `8340d0e` | Abierto, conflictos con destino; pruebas portable e integridad publicadas correctas. Resolver conflictos conservando ambos desarrollos y completar aceptación #22–#27. |
| [#33](https://github.com/dashy2004/CDCRD-Digital/pull/33) | `71d1d9e` | Borrador sobre la rama de #9. Checks API, portable e integridad correctos. La integración depende de la base y la aceptación del conjunto sigue abierta. |
| [#40](https://github.com/dashy2004/CDCRD-Digital/pull/40) | `68e575a` | Abierto, checks portable e integridad correctos. Entrega QTO 0.5.23 documentada; preservar ese estado al combinar cambios del README. No se repitió aquí su prueba nativa. |
| [#42](https://github.com/dashy2004/CDCRD-Digital/pull/42) | `27cc256` | Abierto; checks de memoria Windows/Linux, portable e integridad correctos. #41 distingue primera implementación del piloto y ampliaciones todavía pendientes. |
| [#43](https://github.com/dashy2004/CDCRD-Digital/pull/43) | `e13489e` | Abierto; diff documental leído, checks correctos. El perfil declara que no hay runner completo ni RTE/RFA validados. Conservar esa limitación e incorporar las convenciones del encargo. |
| [#44](https://github.com/dashy2004/CDCRD-Digital/pull/44) | `6f54a7a` | Abierto; diff de instalación leído, checks correctos. Comparar el README con #40: anuncia 0.5.22/85 herramientas frente al desarrollo 0.5.23/90 de #40. No son fallos del motor: requieren conciliación al integrar ambos. |

Hay correcciones locales de exportación PM que no forman parte del head público
consultado de #9. No deben darse por distribuidas ni usarse para cerrar la entrega
pública hasta su publicación y verificación en la revisión correspondiente.

## Conciliación de issues

- **#25:** la geometría nativa de aligeradas y EPS ya tiene implementación y
  evidencia de ensayos en #33. El estado inicial «geometría pendiente» no describe
  todo el avance. Quedan validación del conjunto, continuidad, edición, ejemplo
  reproducible y aceptación del contrato anunciado.
- **#23 y #24:** el tamaño del inventario es parte de la revisión del modelo de
  prueba; no un número fijo universal. Un cambio en el inventario obliga a
  actualizar el recibo y la matriz, sin contar elementos eliminados o duplicados.
- **#27:** conservar por separado motor PM, UI, exportación, plantilla histórica,
  planos y armado. Una copia Excel correcta no acredita acero nativo ni una UI
  completamente ensayada.
- **#14 y #32:** enlazar los PR recientes y mantener la distinción entre
  implementación, pruebas, integración y aceptación de ingeniería.
- **#22, #26, #29–#31 y #41:** no se obtuvo nueva evidencia que cierre sus criterios.
  Continúan abiertos; no se sustituyen ensayos faltantes por revisión documental.

Las [lecciones de IA/BIM](LECCIONES-IA-BIM.md) explican los controles reutilizables.
Los archivos y resultados de proyectos reales permanecen privados.

## Trabajo ya fusionado según GitHub

La consulta también encontró 17 PR fusionados: #1–#5, #7, #8, #10–#13 y
#34–#39. Abarcan auditoría MEP y separación de expedientes privados; unidades,
COGO/Survey y ampliaciones de Civil 3D; puente de losas; catálogo, validación y
recibos de intercambios; captura/contratos de ETABS y corrección de UsoLosa.
Son registros de integración, no una repetición de sus pruebas nativas.

El #12 se fusionó sobre la rama de #9: su estado «merged» no acredita que todo
ese desarrollo esté en master. La consulta de issues cerrados devolvió cero;
los avances implementados dentro de issues abiertos deben conservar sus
criterios de aceptación pendientes, sin cerrarlos por asociación con un PR.
