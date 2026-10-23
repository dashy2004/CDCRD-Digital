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
