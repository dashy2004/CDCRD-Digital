# ETABS — fase 1 de compatibilidad basada en evidencia

Fecha: 2026-10-17. Alcance: código y contratos estáticos; **sin conectar a un modelo vivo**.

## Qué se implementó

- `search_oapi_catalog`: búsqueda offline, paginada, de 4.861 firmas públicas en 527 interfaces de la DLL compartida CSI instalada con ETABS 23.
- `get_joint_displacements`: lectura de `JointDispl`, con objetos/elementos, casos, pasos, U1–U3, R1–R3, unidades y paginación. Si se solicitan casos, cambia la selección de salida, no la geometría.
- `get_story_drifts`: identifica columnas por nombres del typelib o por el contrato explícito CSI, nunca por el tamaño del número. Conserva casos y pasos. Antes un paso fraccionario o una coordenada pequeña podía confundirse con `Drift`.
- `oapi.call`: una respuesta sin código OAPI reconocible ahora falla; no se considera éxito ni se reintenta otra variante dentro del helper ante una respuesta ambigua.
- Contratos verifican cantidad de columnas, `NumberResults`, longitudes, tipos, valores finitos y código de retorno.

No se publica la DLL, cuerpos descompilados, modelos ni evidencia con rutas privadas.

## Origen del catálogo

Se usó realmente [REA](https://github.com/morluto/rea), paquete `rea-agents@6.5.0`, sobre `CSiAPIv1.dll` (1.218.416 bytes), SHA-256:

`776704be956e8afc7c0d7c9c6f77d3262ce6daac710bf54ef885cfc3b7ebccd6`

Assembly 1.0.0.0, .NET Standard 2.0, AnyCPU. El catálogo conserva MVID, tokens, hashes de firmas e identificadores de evidencia. El análisis de miembros informó cobertura completa del artefacto; eso no es cobertura funcional del servidor ni prueba de ejecución.

Comandos reproducibles (PowerShell, sustituir rutas locales):

```powershell
npx -y rea-agents@6.5.0 inspect-managed-artifact "C:\ruta\CSiAPIv1.dll" --json | Out-File -Encoding utf8 artifact.json
npx -y rea-agents@6.5.0 inspect-managed-members "C:\ruta\CSiAPIv1.dll" --json | Out-File -Encoding utf8 members.json
python servidor-mcp/tools/build_rea_catalog.py artifact.json members.json servidor-mcp/src/server.py servidor-mcp/docs/oapi-catalog.json
```

REA analiza metadata; la [documentación de análisis administrado](https://github.com/morluto/rea/blob/main/docs/managed-code-analysis.md) describe su alcance. La DLL comparte declaraciones con otros productos CSI: **una firma presente no implica soporte en ETABS**. En particular, `StoryForces` no aparece como método; no se añadió una llamada inventada. Para cortantes por nivel, la siguiente fase debe contrastar las tablas disponibles en un modelo analizado.

Los nombres y las direcciones COM de `StoryDrifts` y `JointDispl` se cotejaron además con el typelib generado localmente. La documentación pública de [JointDispl](https://docs.csiamerica.com/help-files/etabs-api-2015/html/514a8cd4-eabe-e493-5689-ba0ac7f98068.htm) es de ETABS 2015: sirve como antecedente, no como prueba de ETABS 23. [CSI Analysis Reference](https://docs.csiamerica.com/manuals/etabs/Analysis%20Reference.pdf) define U1–U3 y R1–R3 respecto de los ejes locales del punto.

## Uso

```text
search_oapi_catalog(query="cAnalysisResults JointDispl", limit=10)
describe_oapi(path="Results", filter="JointDispl")
get_joint_displacements(name="P1", item_type=0, max_results=100, offset=0)
get_story_drifts()
```

`item_type`: 0 objeto, 1 elemento, 2 grupo, 3 selección actual. U en la unidad de longitud actual; R en radianes. Una respuesta vacía no certifica que el análisis haya corrido. La paginación limita la respuesta, no el tamaño de la lectura COM. `cases=None` preserva la selección existente; una lista cambia la selección de salida.

## Pruebas y siguiente etapa

```bash
python -m pytest servidor-mcp/tests/test_rea_contracts.py -q
```

Pruebas offline: códigos ausentes/no cero, derivas cero/negativas/grandes, pasos fraccionarios, nombres parecidos a direcciones, orden del typelib, arrays truncados, NaN, unidades, paginación y registro de herramientas. Los tests de adaptadores ejecutan los cuerpos reales de los métodos sin el decorador STA; **no validan marshalling COM, arranque MCP ni un modelo de ETABS**.

Resultado de esta entrega: **29 tests ETABS aprobados**. Importación de `Etabs.py` en Python 3.14/Windows comprobada sin instanciar la clase; decodificación de un resultado sintético cotejada con el typelib real generado `ETABSv1.cAnalysisResults` usando un puntero nulo, sin invocar COM.

Pendiente antes de declarar compatibilidad operativa: modelo sintético desechable, cotejo de derivas/desplazamientos contra tablas GUI y validación de unidades/casos, sin tocar proyectos de clientes. Después: fuerzas por nivel y auditoría por familias (geometría, materiales, cargas, análisis, diseño). Revit, SAFE, Civil 3D y AutoCAD quedan para etapas posteriores.
