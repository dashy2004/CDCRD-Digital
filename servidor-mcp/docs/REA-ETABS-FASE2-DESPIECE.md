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

### Captura V1 comprobada y ampliación V2.1

El usuario completó diseño y detallado nativos en la copia. V1 se ejecutó y produjo
un JSON de 238.383 bytes: una pila, dos niveles, geometría y cuatro estaciones de
diseño. Dos GUID de muros y sus ocho vértices coincidieron con OAPI; las estaciones
coincidieron dentro de la precisión de visualización. Los nueve casos siguen
Finished y los originales conservan sus hashes. Este JSON **no incluye los grupos
físicos de barras**: no se presenta como lista de cantidades o cortes.

Se comprobó una etiqueta externa de unidades imperial aunque la geometría y las
unidades internas del JSON son N-mm-C. REA localizó la dependencia de dos contextos
globales del detallador. No se aplicó una conversión de pulgadas a geometría ya
expresada en milímetros. Los valores nativos confirman recubrimiento 38,1 frente a
40 mm y área vertical preferida 283,8704 frente a 201,1 mm² comprobados. La separación
preferida es 250 mm. La preferencia horizontal de 129,032 mm² tampoco demuestra
equivalencia con las capas derivadas. Son diferencias pendientes, no correcciones.

V2 amplió la lectura al catálogo, grupos verticales/transversales, jaulas y caché
de cantidades, pero falló antes de capturar al buscar como público un método
privado de activación. V2.1 corrige la activación mediante los accesores públicos
verificados por REA y restaura ambos contextos en el orden requerido por sus
efectos cruzados. Una identidad de ensamblado nueva evita sustituir la DLL cargada.
La lectura exige concordancia de unidades; cada parte fallida queda explícita.
No se deserializan los metadatos `$type`, no se recalcula la caché ni se alteran
armado, resultados o archivo del modelo.

**Verificación de V2.1:** 19 pruebas C# de autorización/contexto aprobadas, build
sin avisos/errores y 184 pruebas Python aprobadas. V2.1 copiada y cotejada por SHA-256;
su ejecución posterior falló como se detalla abajo. El runtime MCP ya instalado
no se reemplazó. Una jaula 3D no acredita longitud de corte ni desarrollo de anclaje;
las preferencias de traslapo no son un cálculo aprobado. Despiece integral aún
abierto, sin pasar a otras aplicaciones.

### 2026-10-18: error de etiqueta de unidades y V2.2

V2.1 se ejecutó y se detuvo antes de exportar por `OAPI=N_mm_C,
payload=N_mm_C, wrapper=lb, inch, F`. La hipótesis de que activar el contexto
actualizaría la etiqueta era incorrecta. REA confirma que
`GetDataBaseUnitAsString` lee un campo estático independiente; en cambio,
`LengthFactorUnitToDB` consulta el modelo de objetos de CSICommon. No son una
sola fuente de verdad. Se mantiene el rótulo crudo y no se modifica ese campo.

V2.2 conserva la guarda N-mm-C para OAPI/base/payload y añade cotejo en vivo de
GUID/vértices de todos los muros con pier, sin conversión. Lee por separado las
unidades del contexto numérico y factores mm/m, guardando discrepancias y errores.
El JSON base y el diagnóstico se escriben antes de las validaciones posteriores;
un fallo no descarta la evidencia ya leída. Los grupos se capturan para diagnóstico,
no se declaran unidades/longitudes de barras aprobadas por coincidencia de etiquetas.
Un callback exitoso acredita extracción, no despiece correcto.

Validación V2.2: **34 pruebas C# y 184 Python**, compilación sin avisos/errores,
y repetición offline del cotejo sobre V1 y su auditoría OAPI: dos muros/ocho vértices.
No se midió cobertura porcentual de estas nuevas clases. Paquete separado y hashes
cotejados; ninguna DLL cargada se sobrescribió.

### Captura V2.2 verificada en ETABS y control geométrico

V2.2 se ejecutó sin error: diez partes exportadas, cero fallos, una pila y dos
niveles. Los dos GUID y ocho vértices coincidieron con OAPI. Contexto numérico
N/mm/C, factores mm=1 y m=1000; etiqueta imperial externa conservada, sin conversión.
La lectura OAPI posterior confirma nueve casos Finished y cuatro estaciones sin
mensajes; concreto de muros 30 MPa. La resistencia del acero disponible en catálogo
no debe confundirse con la asignación efectiva del diseño.

La auditoría independiente reconstruyó 68 segmentos verticales desde los grupos,
cotejándolos uno a uno con la jaula; suma recta 233.389,6 mm igual a la caché. Son
barras físicas de 20 mm, frente a 16 mm comprobados. Las horizontales son de 14 mm,
no 12 mm. Recubrimiento nominal nativo 38,1 mm frente a 40 mm del overwrite; aún
se debe comprobar su semántica y la envolvente geométrica de las barras.

REA confirmó dos contratos relevantes de esta compilación:

- El generador horizontal redondea al entero más próximo el número de intervalos.
  En la captura resultan siete formas con paso 474,6 mm, superior a los 450 mm
  declarados. Para ese mismo rango se requieren al menos ocho formas, paso 406,8 mm.
  La corrección propia usa techo y comprueba las posiciones finales; no parchea CSI.
- El generador vertical consulta la longitud de empalme con diámetro cero; ese
  camino usa una pulgada como referencia, dando 914,4 mm. No se interpreta como
  36 diámetros de la barra física ni como una verificación normativa.

Las horizontales tienen arcos y cambios locales de Z; `PLine.Length=0` no es una
longitud de corte utilizable. Cantidades de formas, longitudes rectas, pesos,
cortes y anclajes tienen estados de validación distintos. La cimentación no existe
en la captura; se prepara un ensayo sintético explícito, sin aprobación geotécnica,
sin convertirlo en una modificación ya realizada del EDB. Despiece integral abierto.
