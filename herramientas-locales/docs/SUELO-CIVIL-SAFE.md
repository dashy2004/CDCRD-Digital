# Terreno Civil 3D y geotecnia hacia SAFE

Este incremento convierte una consulta TIN y datos geotecnicos declarados en
un plan revisable de resortes de area. No mueve puntos, crea cimentaciones,
calcula excavaciones ni ejecuta analisis o diseno.

La escritura esta limitada a archivos `SYNTHETIC_*.FDB` nuevos de prueba.
El prefijo es una guarda adicional, no demuestra que el archivo sea limpio:
el operador debe crearlo como prueba controlada. La aplicacion a proyectos
heredados queda pendiente de verificar sus distintas clases de apoyo.

## Herramientas

| Servidor | Herramienta | Efecto |
|---|---|---|
| SAFE | `get_soil_transfer_context(expected_path, frame_id)` | Doble lectura de puntos, areas, secciones, ejes, unidades, bloqueo y asignaciones. |
| local | `cimentacion_preparar_suelo_safe(contexto_json, consulta_json, muestras_json, geotecnia_json, configuracion_json, salida_json)` | Plan JSON con hash; ninguna escritura en aplicaciones. |
| SAFE | `apply_soil_transfer(plan, expected_sha256, confirmed_copy=False)` | Agrega una propiedad nueva, asigna hasta 100 areas sin propiedad de resorte y relee los efectos. |

Se reutilizan `cimentacion_preparar_consulta` y `muestrear_cimentaciones` del
[intercambio de coordenadas](INTERCAMBIO-CIMENTACIONES.md). El TIN aporta cotas;
el operador aporta el estudio, sus parametros y su alcance.

## Unidades y datos independientes

`allowable_bearing_kpa` es presion; `subgrade_modulus_kn_m3` es rigidez por
unidad de area. SAFE recibe el segundo. El primero se conserva en el plan
para el chequeo manual posterior: **no se establece un limite de presion
admisible dentro de SAFE**. La herramienta antigua `define_soil_spring`
permanece por compatibilidad, pero su `factor * allowable_bearing` no participa
en este flujo ni constituye una correlacion geotecnica general.

| Unidades activas SAFE | Enum CSI | k=18000 kN/m3 expresado en ellas |
|---|---|---|
| kN, m, C | 6 | 18000 kN/m3 |
| N, mm, C | 9 | 0.018 N/mm3 |
| N, m, C | 10 | 18000000 N/m3 |

Otros sistemas se rechazan. El aplicador no cambia las unidades activas.
Se rechazan datos no finitos, desbordamientos, k/qa no positivos y conversiones
que redondean a cero. Los numeros anteriores son ejemplos sinteticos.

CSI define el modulo como fuerza/longitud/area y permite asignarlo a objetos
de area: [Soil Subgrade Properties](https://docs.csiamerica.com/help-files/safe/Menus/Define/Soil_Subgrade_Properties.htm).
Desde SAFE 22.5 existen rigideces en las direcciones locales 1, 2 y 3:
[historial oficial](https://www.csiamerica.com/products/safe/enhancements).
Este piloto escribe U1=U2=0 y U3=k; admite solo areas horizontales con eje
local 3 hacia +Z. El comportamiento compresion/unicamente o lineal se declara
explicitamente y se relee por tabla. Esto no demuestra el comportamiento de
un caso de analisis: el usuario debe configurar y revisar sus casos.

## Procedimiento

1. Obtener turno exclusivo de SAFE/Civil y abrir un modelo nuevo de prueba
   guardado como `SYNTHETIC_*.FDB`.
   Configurar `SAFE_PROCESS_ID` para la instancia elegida, `auto_start=false`.
   Registrar hashes de originales. Confirmar ruta, unidades, TIN y datum.
2. Leer `get_soil_transfer_context`; guardar resultado en `context.json` y
   `context.snapshot` en `snapshot.json`. Limites: 10000 puntos, 1000 areas.
3. Preparar consulta con ese snapshot exacto, transformacion explicita y dos
   controles independientes, seleccionando todos los vertices receptores.
   Muestrear Civil con el DWG y handle TIN esperados.
4. Aportar geotecnia y configuracion como los ejemplos siguientes. Usar IDs
   reales del contexto, no indices inventados.
5. Ejecutar `cimentacion_preparar_suelo_safe`; revisar fuente, areas, unidades,
   cotas, comportamiento y hash del plan. La salida local se crea bajo
   `herramientas-locales/salidas`, sin sobrescritura.
6. Invocar `apply_soil_transfer` con el plan completo, su hash revisado y
   `confirmed_copy=true` exclusivamente en la copia autorizada. Esa bandera
   confirma una decision del operador; no descubre que un archivo sea copia.
7. Exigir `ok=true`, `geometry_unchanged=true`, propiedad/asignaciones
   confirmadas. Guardar separadamente, reabrir y releer contexto y tabla
   `Spring Property Definitions - Area Springs`. Comparar hashes protegidos.

Ejemplo exclusivamente sintetico, **no recomendacion de suelo**:

```json
{
  "source": "SYNTHETIC API TEST ONLY; qa y k declarados independientemente",
  "allowable_bearing_kpa": 150,
  "subgrade_modulus_kn_m3": 18000,
  "applicable_point_ids": ["1", "2", "3", "4"]
}
```

```json
{
  "area_ids": ["1"],
  "property_name": "CDX_TEST_SOIL_18000",
  "compression_only": true
}
```

Cada vertice receptor debe tener cota TIN valida y estar en el alcance
geotecnico declarado. Esto no prueba continuidad del estrato ni ausencia de
huecos de TIN dentro del poligono. Son muestras puntuales, no volumen ni fondo
de excavacion. Revisar representatividad del estudio para cada cimentacion.

## Fallos, concurrencia y limites

Los setters CSI no forman una transaccion con rollback. Se validan todas las
areas antes del primer setter; no se reemplazan propiedades o asignaciones
por propiedad existentes. Ante fallo posterior: `ok=false`, acciones
intentadas/confirmadas, error y `partial_write_possible=true`. Conservar
recibo e inspeccionar; no repetir ni borrar automaticamente. Un timeout MCP
no demuestra que la escritura no ocurrio. Repetir un plan ya aplicado se rechaza.

La doble lectura no constituye un lock atomico. El turno exclusivo sigue
siendo obligatorio. La geometria comprobada comprende puntos, conectividad,
secciones, aberturas y ejes de areas; no audita todas las cargas, restricciones
ni apoyos heredados. Antes de usar una copia heredada, revisar los apoyos
existentes; el ensayo nativo se hace sobre un modelo nuevo controlado.

En SAFE 23.3 `GetSpringAssignment` sin propiedad devuelve `[None, 1]`.
No se transforma ese error en ausencia: se consulta `GetAllTables/IsEmpty`
o la tabla completa de asignaciones. `AreaObj.GetSpring` (API compartida de
resortes directos) devolvio `-99` en el ensayo: no se usa para certificar su
ausencia. La guarda de esta herramienta cubre asignaciones por propiedad.
`NonlinOpt3` se verifica por tabla porque el getter de propiedades no lo
devuelve de forma fiable en esta instalacion.

Hashes de contexto, geometria, consulta, muestras y geotecnia detectan cambios
accidentales; no son firma digital ni autorizacion. Civil no se refresca
durante la escritura SAFE: si cambia el terreno, regenerar contexto, muestras
y plan bajo turno exclusivo. La herramienta no guarda automaticamente.

## Pruebas

```powershell
python -m pytest servidor-mcp-safe/tests -q
$env:PYTHONPATH = 'herramientas-locales/src'
python -m pytest herramientas-locales/tests/test_safe_soil_plan.py -q
```

Pruebas offline: conversiones, datos independientes, modelo/unidades distintos,
errores parciales/silenciosos, cobertura incompleta, ejes y planes repetidos.
No abren SAFE. La aceptacion nativa se registra con version, recibos MCP y
guardado/reapertura; binarios y rutas privadas quedan fuera de Git.
