# Civil 3D, ETABS y SAFE: primera API de intercambio

El flujo conecta joints seleccionados de CSI con cotas de una superficie TIN.
Conserva la procedencia y exige una transformacion declarada y comprobada con
al menos dos controles independientes. No ejecuta analisis ni diseno.

## Herramientas y responsabilidades

| API | Entrada | Resultado |
|---|---|---|
| ETABS/SAFE `get_coordinate_snapshot` | Ruta absoluta esperada, identificador de sistema Global | `cdcrd.csi-points/1`, IDs y XYZ con unidades reales |
| Local `cimentacion_preparar_consulta` | Snapshot y configuracion | Consulta de puntos en metros y controles comprobados |
| Civil 3D `muestrear_cimentaciones` | Consulta JSON, DWG, handle TIN, sistema y datum declarados | Cotas nativas o error individual; nunca extrapola |
| Local `cimentacion_revisar_cotas` | Consulta, muestras y geotecnia opcional | Diferencias terreno-joint, faltantes y procedencia |

Los servidores deben arrancar desde esta revision para descubrir las nuevas
herramientas. Los procesos MCP que ya estaban abiertos no recargan Python.
El adaptador Civil reutiliza el contrato en `herramientas-locales/src`; desplegar
el repositorio completo. No hace falta cambiar el puente .NET.

## Configuracion de ejemplo

```json
{
  "source_frame": "EDIFICIO_LOCAL",
  "source_origin": [0, 0, 0],
  "site_origin_m": [100, 200, 10],
  "rotation_deg": 90,
  "site_frame": "SITIO_SINTETICO",
  "vertical_datum": "DATUM_SINTETICO",
  "control_tolerance_m": 0.002,
  "controls": [
    {"id": "C1", "source_xyz": [0, 0, 0], "site_xyz_m": [100, 200, 10]},
    {"id": "C2", "source_xyz": [6000, 0, 0], "site_xyz_m": [100, 206, 10]}
  ],
  "point_ids": ["TEST-A", "TEST-B"]
}
```

Este ejemplo corresponde a un snapshot en **mm**. `source_origin` y los controles
fuente usan la unidad del snapshot; `site_origin_m` y el destino usan metros.
El giro positivo es antihorario sobre +Z. Se transforma `xyz - source_origin`,
se convierte a metros, se gira y se agrega `site_origin_m`.
No es una reproyeccion cartografica ni un ajuste automatico de controles.
Los controles deben medirse/verificarse aparte; copiarlos de la formula no
demuestra que dos proyectos reales esten correctamente ubicados.

```powershell
cdcrd-local preparar-cimentacion points.json config.json query.json
cdcrd-local revisar-cimentacion query.json samples.json review.json --geotecnia soil.json
```

Las salidas no se sobrescriben. La CLI devuelve codigo 1 si la revision tiene
puntos sin cota; errores de contrato no producen una revision aceptada.
Los hashes enlazan los datos aportados, no certifican su autenticidad ni actualidad.

## Geotecnia

`soil.json` opcional requiere `source`, `allowable_bearing_kpa`,
`subgrade_modulus_kn_m3` y `applicable_point_ids`. Son valores independientes,
positivos y con alcance explicito. No se calcula k a partir de qa, ni de curvas
de nivel, pendientes, estratos dibujados o colores de superficies.
La API heredada `define_soil_spring(allowable_bearing, factor)` queda fuera de
este flujo: no se adopta automaticamente su correlacion.
Ninguna propiedad de suelo se asigna a SAFE por estas herramientas.

## Guardas y limites

- CSI conserva unidades y archivo; comprueba identidad, enum de unidades,
  retornos, arrays completos y conteos antes/despues. Solo lee `Global`.
- `File.Save` en ETABS 23.3 puede reportar el sidecar `.$et`. El guard rechaza
  discrepancias; reabrir explicitamente el EDB autorizado y comprobar su ruta.
  No se equiparan extensiones por heuristica.
- Civil exige DWG esperado, INSUNITS=6, unidades Civil `Meters`, TinSurface
  actualizada y declaraciones de sistema/datum coincidentes. Usa
  `FindElevationAtXY`; errores quedan sin cota. No reconstruye superficies.
- El operador debe mantener las aplicaciones sin cambios mientras se lee.
  Comprobaciones entre llamadas no equivalen a una transaccion atomica.
- Los joints no se clasifican automaticamente como apoyos o fondos de zapata.
  La diferencia de cotas no es profundidad aprobada, volumen de excavacion,
  capacidad portante ni dimensionamiento.
- Footings, cargas, reacciones, signos, combinaciones y resultados de diseno
  siguen fuera de esta primera version. El calculo en CSI queda manual.
- Las copias `coordinate_snapshot.py` de ambos servidores son identicas;
  una prueba impide que se desincronicen sin detectar el cambio.

## Verificacion

Pruebas de unidades, giro, datum, controles, arrays, errores CSI, modelos
equivocados, muestras faltantes/duplicadas, hash y no sobrescritura.
Ensayo nativo separado sobre modelos sinteticos: ETABS 23.3 en kN-m y SAFE
23.3 en N-mm, tres joints, guardado y reapertura. Sin analisis/diseno.
La validez de un ensayo Civil nativo debe registrarse por corrida; los mocks
del contrato no acreditan una superficie viva ni una integracion de proyecto.

Contratos de referencia: [CSI PointObj](https://docs.csiamerica.com/help-files/etabs-api-2016/html/9146996a-b33f-ee29-d662-b9364f6c6dc7.htm)
y ensamblados instalados consultados mediante `describe_oapi`.

## Ensayo reproducible mediante MCP stdio

`scripts/verify_civil_csi_mcp.py` ejecuta el intercambio real con procesos MCP
nuevos, de uno en uno. Usa `ClientSession` y `stdio_client`, descubre las
herramientas con `list_tools` y guarda cada respuesta. No conecta COM
directamente ni crea, abre, guarda, analiza o disena modelos. Antes del ensayo,
el operador debe tener turno exclusivo, las tres aplicaciones abiertas en los
modelos sinteticos guardados y la TIN actualizada. Los servidores CSI deben
tener `auto_start=false`; los PID del manifest se pasan por `ETABS_PROCESS_ID`
y `SAFE_PROCESS_ID`. El arnes rechaza nombres distintos de `SYNTHETIC_*`.

El runner requiere Python 3.11+ y `mcp>=1.10,<2`. Los dos runtimes indicados en
CLI deben tener ya instaladas las dependencias de los servidores respectivos.
El runtime CSI tambien ejecuta el servidor Civil. No instala paquetes durante
la corrida ni reintenta llamadas fallidas. `--timeout` limita cada operacion
MCP; un fallo produce `RESULT.json` con estado `failed` y codigo de salida 1.
Un fallo de prevalidacion ocurre antes de arrancar servidores.

Ejemplo **ficticio** de manifest privado; sustituir las rutas absolutas, PID,
handle, controles y expectativas por datos verificados por separado. En este
ejemplo, ETABS usa kN-m (enum 6), SAFE usa N-mm (enum 9), los dos transforman
con giro de 90 grados y origen de sitio `[100, 200, 10]`. Las cotas esperadas
corresponden a un plano de prueba `z = 10 + 0.1*(x-100) + 0.2*(y-200)` que
debe haberse construido y comprobado aparte. No copiar esta geometria a un
proyecto real.

```json
{
  "schema": "cdcrd.civil-csi-test/1",
  "tolerance_m": 0.000001,
  "site_frame": "SITIO_SINTETICO",
  "vertical_datum": "DATUM_SINTETICO",
  "drawing": "D:/LAB_SINTETICO/SYNTHETIC_TERRAIN.dwg",
  "surface_handle": "ABC",
  "models": {
    "ETABS": {
      "path": "D:/LAB_SINTETICO/SYNTHETIC_ETABS.EDB",
      "process_id": 1234,
      "source_frame": "ETABS_LOCAL",
      "config": "D:/LAB_SINTETICO/CONFIG_ETABS.json",
      "expected_units_enum": 6,
      "expected_length_unit": "m",
      "expected_source_points": {
        "TEST-A": [0, 0, -1],
        "TEST-B": [6, 0, -1],
        "TEST-C": [0, 4, -1]
      }
    },
    "SAFE": {
      "path": "D:/LAB_SINTETICO/SYNTHETIC_SAFE.FDB",
      "process_id": 5678,
      "source_frame": "SAFE_LOCAL",
      "config": "D:/LAB_SINTETICO/CONFIG_SAFE.json",
      "expected_units_enum": 9,
      "expected_length_unit": "mm",
      "expected_source_points": {
        "TEST-A": [0, 0, -1000],
        "TEST-B": [6000, 0, -1000],
        "TEST-C": [0, 4000, -1000]
      }
    }
  },
  "expected_points": {
    "TEST-A": {"site_xyz_m": [100, 200, 9], "terrain_z_m": 10},
    "TEST-B": {"site_xyz_m": [100, 206, 9], "terrain_z_m": 11.2},
    "TEST-C": {"site_xyz_m": [96, 200, 9], "terrain_z_m": 9.6}
  }
}
```

Los archivos `CONFIG_ETABS.json` y `CONFIG_SAFE.json` usan el contrato de
configuracion de esta guia: controles en m y mm respectivamente,
`source_frame` distinto para cada origen, los mismos `site_frame` y
`vertical_datum`, y `point_ids` con los tres IDs declarados. Deben incluir al
menos dos controles separados horizontalmente 1 m; el arnes no los infiere.
`expected_source_points` describe **todos** los joints del modelo sintetico;
`expected_points` describe la seleccion que se consulta en Civil.

Desde PowerShell, con rutas ficticias de runtimes ya preparados:

```powershell
& 'D:/RUNTIMES/local/python.exe' 'D:/src/CDCRD-Digital/herramientas-locales/scripts/verify_civil_csi_mcp.py' --help
& 'D:/RUNTIMES/local/python.exe' 'D:/src/CDCRD-Digital/herramientas-locales/scripts/verify_civil_csi_mcp.py' --manifest 'D:/LAB_SINTETICO/manifest.json' --repo 'D:/src/CDCRD-Digital' --python-csi 'D:/RUNTIMES/csi/python.exe' --python-local 'D:/RUNTIMES/local/python.exe' --run-id 'synthetic-001' --timeout 120
```

Los archivos privados quedan exclusivamente en
`herramientas-locales/salidas/<run-id>/`, ignorado por Git. Una corrida requiere
nombre nuevo; no sobrescribe recibos ni archivos de salida. Conserva manifest,
catalogos MCP, respuestas completas, stderr, snapshots, consultas, muestras,
revisiones y hashes SHA-256. Solo declara `native_verified=true` si pasan las
expectativas de XYZ/cotas, la paridad ETABS/SAFE, la relectura de todos los
points/unidades/rutas y los hashes de EDB/FDB/DWG antes/despues. El dictamen es
de ese ensayo sintetico: no acredita cargas, reacciones, suelo ni diseno.

El arranque de estos procesos demuestra la carga de esta revision en el
cliente de prueba. No reinicia ni actualiza automaticamente los servidores
MCP que otro cliente de escritorio mantenga abiertos; ese despliegue necesita
su propia verificacion de `list_tools`.

Pruebas offline del arnes:

```powershell
python -m pytest herramientas-locales/tests/test_civil_csi_mcp_runner.py -q
```

Estas pruebas comprueban validadores, resultados adversos, rechazo de
originales, parser de errores MCP y no sobrescritura. No son evidencia de
una llamada a Civil, ETABS o SAFE.

### Ensayo nativo realizado el 2026-10-23

Civil 3D 2027, puente 0.5.16, ETABS y SAFE 23.3: el arnes MCP completo
paso en tres archivos sinteticos. La TIN tenia cuatro vertices y dos triangulos
en el plano `z = 10 + 0.1*(x-100) + 0.2*(y-200)`, con unidades Civil y AutoCAD
en metros. Se guardo y reabrio antes del ensayo; `IsOutOfDate=false`,
`Saved=true` y `DBMOD=0` se comprobaron por separado.

| Punto | XYZ sitio (m) | Cota TIN (m) | Terreno menos joint (m) |
|---|---|---|---|
| TEST-A | 100, 200, 9 | 10.0 | 1.0 |
| TEST-B | 100, 206, 9 | 11.2 | 2.2 |
| TEST-C | 96, 200, 9 | 9.6 | 0.6 |

Las dos cadenas CSI produjeron los mismos valores a partir de m y mm. Los
snapshots antes/despues y hashes EDB/FDB/DWG permanecieron iguales durante
las lecturas MCP. Se comprobaron tambien rechazos por dibujo y sistema
equivocados, y un punto fuera de la TIN produjo cota nula, sin extrapolacion.
No se ejecuto analisis, diseno ni asignacion geotecnica. Los recibos completos
con rutas locales permanecen fuera del repositorio publico.

El bloqueo anterior no se reprodujo en la nueva instancia de Civil: la sonda
del despachador y consultas respondieron. No se modifico el dispatcher ni se
atribuye una causa raiz no demostrada. Consulte `docs/DIAGNOSTICO.md` del
servidor Civil para no repetir escrituras tras un timeout.

### Incremento siguiente: suelo hacia SAFE

El [piloto de geotecnia](SUELO-CIVIL-SAFE.md) agrega un plan con k independiente
y su aplicacion verificada a areas sinteticas. Mantiene el calculo manual y
la presion admisible separada; no modifica este contrato de coordenadas.
