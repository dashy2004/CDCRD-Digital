# Procedimiento de modelado y revisión ETABS

La integración convierte las reglas aportadas por el usuario en un perfil explícito,
planes de configuración y verificaciones numéricas. El perfil `modeling_20261015`
se selecciona en cada llamada; no sustituye los valores predeterminados de las
herramientas existentes ni modifica automáticamente un modelo.

La configuración y las preferencias de armado son criterios de ese procedimiento,
no una norma universal. Los nombres, coordenadas, modelos, cargas especiales y
resultados de los proyectos de referencia no se incorporan como valores de otros
proyectos. Los respaldos anteriores no prevalecen sobre el prompt actualizado.

## Herramientas integradas

`server.py` registra estas ocho herramientas en la rama ETABS del servidor:

| Herramienta | Resultado |
|---|---|
| `get_etabs_procedure` | Biblioteca de materiales, barras, nueve losas y las 22 etapas, con herramientas existentes y comprobaciones pendientes |
| `prepare_etabs_modeling` | Plan de stories, patrones, masa, P-Delta, modos y EX/EY, sin ejecutar setters |
| `calculate_etabs_project_loads` | Componentes separados de sets, mampostería sobre losas/vigas y agua |
| `audit_etabs_modeling_snapshot` | Hallazgos sobre una lectura aportada: unidades, configuración, malla, diafragmas, shells, apoyos y persistencia |
| `prepare_etabs_slab_measurements` | Dimensiones al múltiplo superior de 0,05 m y máximo de totales de mampostería entre plantas |
| `review_etabs_longitudinal` | Comparación por viga, cara y zona con As total longitudinal, mínimos por luz, corridos y adicionales |
| `review_etabs_flexure_torsion` | Reserva de flexión y cobertura del faltante de torsión en la misma cara y zona |
| `read_etabs_design_summary_csv` | Importación de un CSV histórico con demandas totales, estaciones y errores conservados |

El código de estas herramientas no importa COM ni abre aplicaciones. En el servidor
MCP se conserva el ciclo de conexión de ETABS ya existente. También hay una CLI que
funciona sin ETABS ni el SDK MCP:

```powershell
py servidor-mcp/tools/etabs_procedure.py prepare_etabs_modeling `
  servidor-mcp/examples/procedure-model.json --output plan.json
py servidor-mcp/tools/etabs_procedure.py calculate_etabs_project_loads `
  servidor-mcp/examples/procedure-loads.json --output cargas.json
py servidor-mcp/tools/etabs_procedure.py review_etabs_longitudinal `
  servidor-mcp/examples/procedure-beams.json --output acero.json
py servidor-mcp/tools/etabs_procedure.py review_etabs_flexure_torsion `
  servidor-mcp/examples/procedure-torsion.json --output torsion.json
```

`input` es un objeto JSON con los argumentos de la herramienta. `--output` crea un
recibo nuevo y rechaza un archivo ya existente. Si se omite, escribe JSON por stdout.
No instala ni activa otra instancia del servidor MCP. Reiniciar el servidor que
use este checkout será una operación posterior.

## Configuración y espectro

`project` requiere `model_path` absoluto terminado en `.EDB`, `usage: residential`,
`has_parking` booleano y `stories` con `name` y `architectural_height_m`. Los stories
se proporcionan de abajo hacia arriba, excluyendo Base. El plan conserva las alturas
fuente y añade 0,50 m al primer story según el perfil. No deduce cotas de rampas ni
traslada automáticamente esos 0,50 m a un libro de espectro.

LiveT se mantiene como Live. LiveP sólo entra con parqueos: factor de masa 0,25 y
P-Delta 1,60. Masa incluye únicamente cargas, lateral sí y vertical no. El número
de modos propuesto es tres por story; no acredita masa participante.

`seismic` es opcional: si falta, queda pendiente y no se inventan parámetros.
Cuando se proporciona requiere `ss_g`, `s1_g`, `fa`, `fv`, `u`, `rd`, `near_fault`,
`source` y decisiones `reentrant`, `nonorthogonal`, `torsion` como `yes`, `no` o
`pending`. `rd` debe ser el valor final confirmado: el código no aplica
penalizaciones ni selecciona automáticamente zona, suelo, ocupación o sistema.

El perfil conserva Ss/S1 fuente en g para Qx/Qy y propone los parámetros de la
función multiplicados por 9,81, como indica el documento aportado. Esta instrucción
no prueba que la función normativa genere una curva compatible. Las funciones de
ETABS son normalizadas y el factor del caso tiene unidades de aceleración:
[funciones CSI](https://docs.csiamerica.com/help-files/etabs/Menus/Define/Functions/Response_Spectrum_Functions/Response_Spectrum_Functions.htm)
y [casos CSI](https://docs.csiamerica.com/help-files/etabs/Menus/Define/Load_Cases/Response_Spectrum.htm).

Para proponer EX/EY hay que aportar `scale_mps2`, `required_periods_s` y `samples`,
cada muestra con `period_s`, `function_ordinate` y `excel_sa_mps2`. Se compara
`function_ordinate × scale_mps2` con el Excel en todos los puntos suministrados;
deben incluirse los cambios de rama y al menos tres períodos. No hay interpolación,
extrapolación, otro factor g automático ni doble U/Rd. Una discrepancia impide
generar las filas de los casos. La prueba cubre esos puntos, no una curva completa
que no haya sido aportada.

EX/EY tienen dos filas MOPC con F y 0,30F, CQC/SRSS y excentricidad de caso cero.
Qx/Qy conservan 0,05. Estas elecciones reproducen el perfil; el escalado de la fila
transversal no se presenta como equivalente a todas las combinaciones normativas
100/30. El análisis siempre permanece sin autorizar.

## Cargas y mediciones

- Cada losa requiere identificación, `is_opening: false`, `support` (`supported` o
  `cantilever`), `set`, `architecture_set`, carga viva de Excel, unidad y lista de
  componentes existentes. Una lista vacía significa ausencia verificada; un dato
  ausente no equivale a cero.
- Entrepisos, Comun y Techo contienen acabados y viva por separado. Parqueos y
  Gimnasio necesitan `confirmed_live_tfm2` del proyecto; no se presupone 0,50.
- Unidades superficiales admitidas: `tonf/m2`, `kgf/m2`, `kN/m2`, `N/mm2`.
  La conversión de fuerza usa 1 tonf = 9,80665 kN; esto es independiente del
  multiplicador 9,81 particular del espectro.
- En paños apoyados: mampostería adicional = techo a 0,05 del máximo entre la
  lectura de Excel y 0,10 tonf/m². En vuelos se excluye esa carga y su mínimo.
  Se conservan el valor calculado y el asignado.
- Paredes sobre vigas: altura del espacio superior menos peralte, por espesor y
  1,80 tonf/m³. Se calculan ambos extremos; luego se redondean sus intensidades.
  `start/end` son posiciones relativas en el sentido de lectura; `reverse_ij`
  transforma posiciones e intensidades al sentido ETABS. Se rechazan intervalos
  solapados después de normalizar I/J.
- Agua: área horizontal mojada por profundidad media. La carga equivalente sobre
  un área mayor requiere declaración explícita. No se redondea con la regla de
  mampostería. El llamador debe verificar que las áreas mojadas sean disjuntas y
  que la suma física represente una sola piscina.
- Las dimensiones de Excel se redondean a 0,05 m; las longitudes medidas de paredes
  no. En plantas agrupadas se toma el máximo del total por losa/espesor, indicando
  qué planta gobierna. No se suman pisos ni máximos de segmentos independientes.

El calculador no aplica losas sobre huecos, no modifica Excel y no reconcilia
automáticamente cargas existentes. Si detecta componentes ya asignados, detiene
esa propuesta para evitar repetirlos.

## Snapshot de modelado

`snapshot` contiene `model_path`, `units`, `patterns`, `mass_source`, `pdelta`,
`modal_max_modes`, `spectrum_cases`, `slab_definitions`, `slabs`, `walls`, `frames`,
`joints`, `check_model` y `saved_readback_verified`. Los ajustes siguen el formato
del plan. Los datos deben proceder de lecturas nativas; este módulo no los captura.

Cada losa tiene `id`, `story`, `vertices_m` XYZ, `structural_block`, `diaphragm`,
`directions` (1/2), `mesh`, `is_opening`, `support` y `load_components`. Un diafragma
se agrupa por **story y nombre**, permitiendo reutilización entre pisos. Se detectan
alturas mezcladas, cuerpos independientes unidos, rampas con diafragma horizontal,
vértices repetidos, shells exactamente duplicados, falta de coplanaridad y puntos
fuera de retícula. No se implementa una prueba topológica completa de solapes,
contornos o conectividad con el DWG.

Se revisan también definiciones de losa sin usar (Shell-Thick), 1D incluso macizas
(No Auto Mesh), muros (Auto Rectangular), factor de zona rígida de frames, nudos de
Base y diafragmas explícitos en nudos. Una colección ausente queda como hallazgo;
una vacía declara que no existen objetos de esa clase.

`check_model` requiere `completed: true` y `warnings: []`; la persistencia requiere
`saved_readback_verified: true`. Son evidencias suministradas por el llamador. El
resultado `checked_snapshot_matches` sólo describe los datos recibidos y nunca
acredita por sí solo su origen, la preparación integral o la seguridad del modelo.

## Acero: dos contratos diferentes

**Revisión longitudinal:** `demand_kind: total_longitudinal`, unidades explícitas
y seis demandas (superior/inferior × i/center/j). Se usa el As total que contiene
la porción longitudinal de torsión; no se agrega Al otra vez.

Las barras se identifican físicamente con `id`, `face`, `role`, `count`,
`diameter_in`, `zones` y `drawing_verified`. Un adicional que recorre todo el vano
incluye las tres zonas, una sola vez; no cambia su clasificación a corrido para
determinar la base. Los corridos propuestos toman el máximo del eje, salvo una
excepción del plano explícitamente confirmada. Una sección fija conserva sus
corridos y recibe comparación de suficiencia y adicionales.

Las áreas de barras adoptadas por este procedimiento de revisión son distintas de
las definiciones nominales de la biblioteca ETABS; no se mezclan automáticamente.
No se propone 1/2 para flexión. Umbrales: inferior 11,40 cm², adicional superior
14,25 cm². Se informa el **total adicional necesario con los corridos actuales**,
no una lista de barras a retirar o añadir simultáneamente.

Para 7,50 m exactos se usa la fila 7,50–8,50. Los límites 6,00/8,50/10,00/11,00 y
luces superiores a 12 m quedan pendientes porque la fuente no resuelve el criterio.
Menos de 4 m usa sólo demanda ETABS. El mayor mínimo de sección del eje se reporta,
sin cambiar secciones. Los errores y avisos de diseño permanecen visibles.

**Flexión frente a torsión:** exige `demand_kind: flexure_only` y
`torsion_kind: longitudinal_area_per_face`. Al total necesita un reparto explícito
antes de invocar la herramienta; At/s no es un área longitudinal. Cada registro
incluye los cuatro valores demanda/colocado y una cara/zona identificada. El
excedente de flexión sólo puede cubrir el faltante de torsión de esa misma cara.
Sin datos: FALTAN DATOS. Una explicación de cobertura exige ausencia de errores
de diseño y confirmación de que las barras asignadas a ambas funciones no se
cuentan dos veces. No verifica anclaje, desarrollo o distribución perimetral.

**CSV:** se exige Design Summary con AsTopTotal/AsBotTotal, unidades de áreas y
estaciones, modelo fuente, fecha y confirmación de estaciones en caras. Se toma
máximo central entre L/4 y 3L/4 y se conservan errores. Los CSV flexenv no reemplazan
el total longitudinal. La lectura es histórica; todavía requiere asociar caras,
ejes y barras al plano vigente. No se presume una sección, modelo o unidad por
el nombre del archivo.

## Cobertura y límites de integración

Las 22 etapas están representadas en el perfil con sus herramientas existentes.
Se automatizaron los cálculos y comprobaciones descritos arriba. Continúan como
trabajo de integración nativa: interpretación de DWG/arquitectura, cambios en
libros con macros, construcción de geometría, creación R-001 por versión, Uniform
Load Sets, opciones P-Delta y captura completa de asignaciones.

Dos diferencias del servidor existente son explícitas: `add_pdelta_case` crea un
caso no lineal y no configura las opciones globales solicitadas;
`add_response_spectrum_case` sólo aplica una dirección. No se invocan como
sustitutos silenciosos del procedimiento. Tampoco se ejecuta Panel Zone ni
Run Analysis como parte de la preparación.

Los informes Excel/Word de revisión no se generan en esta integración; las
herramientas entregan JSON estructurado para incorporarlos posteriormente. No se
han modificado EDB, DWG ni libros fuente, ni se acredita una conexión viva.

Pruebas:

```powershell
py -m pytest servidor-mcp/tests -q
```

Los casos cubren unidades, parqueos, componentes duplicados, huecos, vuelos,
redondeo, agua, I/J, espectros inconsistentes, diafragmas, datos faltantes, tablas
de armado, doble conteo de barras/torsión, errores de diseño y lectura de CSV.

Validación local del 2026-10-20: 313 pruebas aprobadas, 70 de esta integración; cero fallos y cero omisiones. SDK MCP 1.30.0: ocho herramientas registradas y cuatro ejemplos ejecutados. Esta evidencia no incluye una sesión viva de ETABS.
