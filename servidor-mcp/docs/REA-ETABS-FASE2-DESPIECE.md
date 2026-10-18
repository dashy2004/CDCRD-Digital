# ETABS: unidades de capas, conciliación y límite del despiece

Fecha: 2026-10-17. ETABS 23.3.0 / OAPI 2.016. Esta fase corrige el lector;
**no declara terminado el despiece de fabricación ni certifica un proyecto**.

## Uso efectivo de REA

Se utilizó [REA 6.5.0](https://github.com/morluto/rea) con Node 24.16.0:
`inspect-managed-artifact`, `inspect-managed-members` e
`inspect-managed-native-boundaries` sobre las interfaces y componentes de
detallado instalados. También se analizaron los miembros de
`CSiDetOAPIHandler.dll` y `CSiNAWallStackDesigner.dll`.

El análisis integral de algunas DLL grandes alcanzó el límite de representación
de 64 MiB. No se presenta como cobertura completa. Un arnés privado, construido
con los parsers de REA, resolvió las asignaciones `MethodImpl` entre contratos e
implementaciones y decodificó solo los cuerpos CIL pertinentes. Sus resultados
se identifican como **arnés focalizado**, no como evidencia canónica emitida por
el CLI. Se realizó además un cotejo independiente con ILSpy 9.1.0.7988.

Referencia: [alcance y límites del análisis administrado de REA](https://github.com/morluto/rea/blob/main/docs/managed-code-analysis.md).
No se ejecutaron las DLL para el análisis estático, se parchearon binarios ni se
alteró la licencia. Las DLL, cuerpos reconstruidos y registros detallados
permanecen privados; aquí solo se publican hallazgos y código propio.

Identidad de la implementación investigada (`ETABS.dll`):

- SHA-256: `595e2b1c673e931b69413ebb846aa99a95365cedb79755a32731f9322400ee24`.
- MVID: `784404f4-c29d-492e-b3b9-5e5b53e633af`.

## Hallazgos y correcciones

| Contrato | Evidencia de esta versión | Tratamiento |
|---|---|---|
| `AreaObj.GetRebarDataPier` | Implementación `0x06002a2a`: copia las capas sin conversión a unidades de visualización. Cambiar N-mm a kN-m no cambió 450/230; `PropRebar.GetRebarProps` sí cambió de escala. | `area_rebar.units_enum` identifica unidades de base de datos, separadas de `units_enum` del resumen. Otras versiones quedan `units_verified=false`. |
| Generador interno de capas | Helper `0x060066d8`: puede derivar separación de áreas/razones de acero, con recubrimientos por defecto. | No se trata la capa como una lectura fiel del armado comprobado ni como lista de barras cortadas. |
| `Detailing.StartDetailing` | Cadena `0x06002932` → `0x06002933` → `0x060043a7`: termina actualizando el estado de interfaz sin generar el detalle. En vivo retornó 0 con contadores vacíos. | `call_oapi` rechaza este falso positivo en ETABS 23.3.0 y remite al flujo nativo de wall stacks. |
| `DesignShearWall.GetRebar` | Implementación `0x06002687`; sigue devolviendo arrays vacíos en la prueba, incluso después del detallado GUI. | Se conserva `native_rebar_count=0`; la alternativa se identifica explícitamente como `AreaObj.GetRebarDataPier`. No se afirma haber reparado el método propietario. |
| Nuevo componente de wall stacks | Se localizaron generador y `ExportRebarsToExcel` (`0x060003f5` del componente), no una exportación COM pública equivalente. | La presencia del método no demuestra que la opción esté expuesta en el editor o edición instalada. Extracción integral aún pendiente. |

## Conciliación numérica de las cuatro capas

Dos áreas de muro de 4.000 × 3.000 × 200 mm, una por nivel. Por cada área:

| Dato | Capa nativa | Sección/resumen comprobado | Resultado |
|---|---|---|---|
| Vertical | Barra 16, separación 230 mm | Barra 16, separación 250 mm | Separación distinta |
| Recubrimiento vertical crudo | 0 mm | 40 mm | Distinto; cero no significa recubrimiento constructivo aprobado |
| Horizontal | Barra 12 a 450 mm, dos caras: 0,502667 mm²/mm | `ShearAv=0,5 mm²/mm` | No inferior al valor mostrado; no prueba conformidad del detalle |
| Recubrimiento horizontal crudo | 25 mm | 40 mm | Comparación literal distinta, no equivalencia geométrica |

Las cuatro estaciones de diseño conservan D/C 0,412; 0,247; 0,276; 0,589
con límite 0,95. Los nueve casos estaban Finished en la lectura de esta fase.
El lector ahora devuelve `reconciliation.status="differences"`, valores
normalizados a mm y los datos faltantes. No cambia armado ni geometría para
forzar una igualdad artificial.

El editor GUI muestra un wall stack generado con etiquetas `30-#6`, `2-#6`
y `#4@450`. Es evidencia visual de detalle, **no una exportación de barras ni
prueba de equivalencia con los tamaños nombrados 16/12 por la API**. Faltan
identidades, cantidades verificables, formas, longitudes de corte, anclajes,
ganchos, traslapos y su conciliación con la sección comprobada.
Las propiedades de la sección TEST_L2 del editor muestran `Cover=38,1 mm`,
otro valor distinto del recubrimiento comprobado de 40 mm. No se sustituyó
ninguna de estas fuentes ni se ajustó el modelo para ocultar la diferencia.
Una captura adicional de propiedades muestra vertical `#6` a 250 mm y
horizontal `As=500 mm²/m`, `#4`, separación máxima 450 mm. La separación
vertical del editor sí coincide con el overwrite de 250 mm, pero no con la
capa derivada de 230 mm. El catálogo `PropRebar` del modelo contiene barras
métricas 6–50, no los nombres `#4`/`#6`: **no se elimina el prefijo # para
convertirlos**. Por API, la barra `6` tiene diámetro 6 mm, no es prueba de
equivalencia con la designación `#6` del editor.

## Pruebas

- 184 pruebas offline aprobadas: 174 ETABS y 10 del corpus.
- Cobertura de sentencias: `wall_reconciliation.py` 97%, `wall_results.py` 90%.
  No representa cobertura de toda la API ni de todas las ramas.
- Ruff y Pyright sin errores en ambos módulos puros.
- Casos negativos: falta/ambigüedad de overwrites, incompatibilidad entre
  estaciones, D/C ausente, números inválidos, cobertura incompleta y versiones
  sin evidencia de unidades. La igualdad numérica tampoco autoriza despiece.
- Lectura real del modelo: cuatro registros conciliados con estado `differences`.
  Cambio temporal de unidades restaurado; modelo bloqueado y nueve casos Finished.
- Instalación de la corrección `d6cc8e1` verificada por SHA-256, con respaldo
  y configuración preservada. Dos sesiones nuevas MCP por stdio, una con cada
  runtime configurado, comprobaron las 76 herramientas, los cuatro D/C, las
  cuatro capas, el rechazo del comando legado y nueve casos Finished.
  Los clientes que ya estaban abiertos requieren recargar `fea`; no se cerraron
  sus procesos. Los EDB de referencia y corregido conservaron sus hashes.

`complete_detailing=false` y `engineering_approval=false` permanecen explícitos.
El siguiente paso es obtener y verificar los datos del editor nativo, no repetir
el comando legado ni pasar a las otras aplicaciones.

## Continuación: copia aislada y lector nativo experimental

Se creó una revisión sintética independiente para el despiece. En esta sesión,
`File.Save(nueva_ruta)` devolvió cero, pero dejó el nombre activo con extensión
`.$et`, el modelo desbloqueado y los casos sin ejecutar. Se detectó mediante
relectura, no se confundió con una copia analizada correctamente. Tras abrir el
EDB nuevo y analizarlo, los **nueve casos terminaron** y quedó bloqueado. Los
hashes de los dos EDB anteriores permanecieron iguales. El diseño de muros y
el detallado deben regenerarse en esta copia antes de leerlos; los resultados
del modelo anterior no prueban esta nueva revisión.

La continuación con REA, limitada a esta compilación, identificó:

- Un accesor de lectura del objeto de wall stacks cargado dentro de ETABS.
  No es un endpoint COM público. Se resolvió por token solo después de fijar
  SHA-256 y MVID; el análisis amplio alcanzó de nuevo el límite de representación,
  por lo que se usaron consultas focalizadas, no cobertura completa.
- El serializador nativo `GetDataObjet` y su cadena de construcción del modelo
  de intercambio. Puede normalizar identidades de torres en memoria; no se
  asume que exporte toda la lista de barras ni que sea una instantánea íntegra.
- `ExportRebarsToExcel` llega a una tabla de propiedades de `DesignLeg`, y su
  retorno booleano no acredita la creación de un archivo. No se invoca esa
  exportación ni se presenta como lista de cortes validada.

Se añadió [wall-detail-plugin](../tools/wall-detail-plugin/README.md), un lector
.NET 8 que usa el mecanismo de plugins de CSI y el accesor investigado. Exige
versión/binarios exactos, modelo autorizado, PID y hora de creación del proceso,
y modelo bloqueado. No modifica armado, geometría, análisis ni guarda el EDB.
No se distribuyen dependencias CSI ni cuerpos reconstruidos.

**Verificación actual:** 11 pruebas del control de acceso pasan y la compilación
termina sin avisos/errores; las 184 pruebas Python existentes siguen pasando.
El paquete experimental fue copiado y cotejado por SHA-256 en una carpeta nueva.
**Carga dentro de ETABS, captura y validación de contenido pendientes**. No se
reemplazó el runtime MCP ya instalado ni se publicó esto como corrección final
del despiece. Barras, recubrimientos, cantidades, cortes, ganchos, traslapos y
anclajes siguen sin cierre. No se trabajó en otras aplicaciones.
