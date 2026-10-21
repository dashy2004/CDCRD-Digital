# Validación previa Civil 3D → BeamNG

El validador lee fuentes y devuelve `cdcrd.interchange-validation/1`; no crea
mapas, modifica los archivos ni activa aplicaciones. Comparte `load_sources`
con `build_package`, que aplica las mismas reglas antes de crear su salida.
`verify` conserva su función existente de verificar paquetes, rutas y hashes.

## Uso

Desde `civil3d-beamng`, con las dependencias de su `pyproject.toml` instaladas:

```powershell
python -m cdcrd_beamng validate --snapshot .\examples\snapshot-synthetic.json
python -m cdcrd_beamng validate `
  --terrain-landxml 'D:\ejemplo\terreno.xml' --terrain-surface 'Terreno' `
  --road-landxml 'D:\ejemplo\carretera.xml' --road-surface 'Carretera' `
  --road-guide 'D:\ejemplo\guia.json'
```

Desde la raíz, la CLI común ejecuta ese módulo con el mismo intérprete, sin
shell y resolviendo las rutas de entrada antes de cambiar su directorio:

```powershell
uv pip install --python .\herramientas-locales\.venv\Scripts\python.exe .\civil3d-beamng
.\herramientas-locales\cdcrd.ps1 validar-intercambio --modulo beamng `
  --snapshot .\civil3d-beamng\examples\snapshot-synthetic.json --json
```

El ejemplo es enteramente sintético. Los archivos de proyectos reales y sus
informes permanecen fuera del repositorio público. No se agrega una herramienta
MCP: las 12 existentes conservan sus interfaces.

## Comprobaciones

| Aspecto | Regla del contrato |
|---|---|
| Unidades | Snapshot `units=m`; LandXML `Metric linearUnit=meter`. Sin conversión implícita. |
| Unidades CAD declaradas | Si están presentes, `sources.drawing_units=INSUNITS=6` y `civil_drawing_units=Meters` deben coincidir con metros. |
| Coordenadas | Valores numéricos finitos, sin booleanos/texto; snapshot `[E,N,Z]`, LandXML `N E Z` convertido a `[E,N,Z]`. Se rechaza un `coordinate_order` declarado contradictorio. |
| Guía vial | Al menos dos nodos, anchos positivos, distancias XY finitas/no nulas y estaciones finitas crecientes si se declaran. |
| IDs de objetos CAD | Si se declara cualquiera de los dos handles, se exigen ambos: hexadecimales no nulos de hasta 64 bits y distintos, comparando su valor sin distinguir mayúsculas ni ceros iniciales. |
| IDs LandXML | No vacíos, sin espacios y únicos dentro de cada superficie; no se confunden con posiciones del arreglo. |
| Referencias | Índices enteros de triángulos dentro del arreglo; referencias LandXML existentes, incluso en caras invisibles. Estas caras se excluyen de la geometría. |
| Fronteras opcionales | `boundary_edges` sin índices inválidos, autorreferencias ni duplicados; deben coincidir exactamente con las aristas usadas una vez en la malla visible. Se rechazan aristas usadas por más de dos caras cuando se declaran fronteras. |
| Geometría existente | Se conservan los rechazos de caras degeneradas, verticales, duplicadas y desbordamientos de coordenadas. |
| Formato | Esquema esperado, modo snapshot o pareja LandXML, JSON sin claves duplicadas/NaN/infinito y XML sin entidades externas. |

## Resultado y límites

Salida **0**: contrato válido. Salida **1**: fuente rechazada, con `ok=false` y
`errors`; se informa el primer error, no una lista exhaustiva. Opciones CLI
incorrectas o fallo de ejecución del adaptador: salida **2**.

En éxito se informan metros, orden de coordenadas, límites absolutos y recuentos.
`declared_source_ids_checked` solo indica que se comprobaron los dos handles
declarados; no confirma objetos dentro de un DWG. Si faltan ambos se acepta el
snapshot histórico, devuelve `false` y una advertencia. LandXML tampoco demuestra
identidad de objetos CAD. Las fronteras ausentes siguen siendo opcionales.

`scope=source_contract_only`, `crs=not_verified` y
`consumer_validation=not_checked` se conservan incluso en éxito. No se deduce CRS,
se reproyecta, se comprueba un origen topográfico común ni se acredita escala
física, exportación viva, colisión, conducción o guardado/recarga en el motor.
Tampoco se ejecuta la rasterización ni se garantiza que los parámetros de
rejilla/materiales de un `build` posterior sean adecuados.

## Pruebas y trazabilidad

```powershell
python -m pytest tests tools/test_prepare_drive.py -q
```

Los nuevos casos cubren snapshot y LandXML, los cuatro grupos de comprobaciones,
compatibilidad con metadatos opcionales, archivos inalterados, errores sin salida
parcial, guías externas y ambas CLI en procesos reales. La CLI común añade pruebas
de protocolo JSON, rutas relativas, argumentos literales, errores y timeout.
La CI ejecuta estas pruebas y las regresiones del conversor existente, incluido
el lector COLLADA instalado mediante el extra `test`.

TDD conservado en la rama del cambio: `1207003` (RED: 33 fallos), `e7d5856`
(GREEN: 33 casos); `70e0392` (RED: estaciones fuera de float64 y nombre explícito
del estado de IDs declarados), `a34c0d0` (GREEN: suite conjunta 128 casos y
19 subpruebas). `594bbf5` añadió otro caso RED de distancia XY desbordada;
`21d80eb` lo corrigió y dejó **129 pruebas y 19 subpruebas aprobadas**.
Cobertura: **100 %** en `validation.py` y el adaptador `interchange.py`,
**85 %** en el conjunto instrumentado del conversor/adaptador. Los procesos
reales de las CLI se prueban, pero no están instrumentados por esa medición.
Ruff sin hallazgos en herramientas-locales y comprobaciones F/I de los archivos
Python modificados del conversor. El lector pycollada emitió cuatro advertencias
de deprecación con NumPy 2.5, sin fallos de lectura de la geometría.
Estas pruebas son de archivos y código; la
validación en Civil 3D y BeamNG sigue teniendo su evidencia y alcance propios.
