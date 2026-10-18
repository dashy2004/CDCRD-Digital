# Contrato de solicitudes

`plugin/Contracts.cs` define el contrato completo. JSON usa camelCase y acepta propiedades adicionales; no dependa de ellas para controles de seguridad.

| Campo común | Regla |
|---|---|
| `action` | `build`, `sections`, `audit` |
| `expectedDrawing` | Ruta absoluta; debe coincidir con el documento activo |
| `outputDirectory` | Directorio absoluto de recibos |
| `runId` | Nombre de archivo válido y único para esta acción |
| `namePrefix` | Namespace que empiece por `CD`; los objetos nuevos deben usarlo |
| `expectedCogoCount` | Conteo exigido; -1 desactiva este control |
| `volumeTolerance` | Mayor que cero y hasta 0,01 m³; predeterminado 0,0001 |

`build` requiere `baseSurface` y de una a diez `meshes`. Cada malla contiene `name`, `vertices` (XYZ), `faces` (tríos de índices base cero), `colorAci` y `expected: {cut_m3, fill_m3}`. Para crear una base nueva se incluye `baseMesh` con el mismo nombre. Para una base existente se recomienda exigir `expectedBaseTriangleCount` y `baseCheckPoints` distribuidos por el área de trabajo. No se reconstruye una base que esté desactualizada: se rechaza. La coincidencia de checkpoints no es una comparación completa del TIN; la aplicación debe auditarlo antes de usarlo.

Una transacción contiene las superficies de diseño y de volumen de una solicitud. Nombres existentes, mallas inválidas, alteración del interpolante o discrepancia de volúmenes provocan una excepción antes de confirmar la transacción. Los conteos límite son 100.000 vértices y 200.000 caras por malla. La malla debe ser una superficie continua y sin huecos; el constructor no implementa límites internos arbitrarios.

`sections` requiere `sections` con `alignmentName`, `groupName`, `start`, `end`, `halfWidth`, `spacing`, `viewEvery`, `viewOrigin`, `elevationRange` y `surfaces`. Se admiten hasta 501 estaciones ordinarias y, cuando corresponde, una estación final adicional. Las coordenadas Z del eje no controlan las cotas de las secciones; estas se obtienen de las superficies. Los valores de la vista se expresan en metros, H=V. Las vistas se distribuyen en cuatro columnas; los puntos de sección nativos contienen offset y elevación. Sobre un eje de oeste a este, offset positivo corresponde al sur.

`audit` lee todas las superficies, COGO y alineamientos del dibujo, no únicamente el namespace solicitado. **Sus salidas de proyectos reales son privadas.** Cada sección incluye `segmentTo`; un perfil con discontinuidades debe tratarse por segmentos. El verificador de la demostración exige perfiles continuos y no conecta huecos automáticamente.

## Estados y reintentos

Una respuesta `ok: true` confirma la acción en memoria. No confirma guardado ni persistencia en disco. Verifique el contenido nativo, guarde/cierre/reabra y compare otra auditoría. Si un comando se ha encolado en un puente, espere su recibo antes del siguiente. No interprete un timeout como cancelación.

La escritura del recibo ocurre después del `Commit`. Una excepción de disco en ese punto puede ocultar una creación ya confirmada. Ante un recibo ausente, incompleto o fallido, revise el dibujo con una auditoría independiente antes de repetir. No hay recuperación automática de recibos ni actualización idempotente de objetos existentes. El bloqueo por nombres y recibos evita repetir solicitudes normales, pero no sustituye la coordinación de un único escritor.
