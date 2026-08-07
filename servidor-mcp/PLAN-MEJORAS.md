# Plan de mejoras del servidor FEA-MCP

Derivado de ejecutar el protocolo R01–R10 completo el 2026-08-07 contra
ETABS 23.3.0 / OAPI 2.016. Cada punto está clasificado por **quién lo puede
arreglar**, que es la pregunta que decide si se programa o se convive con ello.

Leyenda de clasificación:

- **CÓDIGO** — defecto del servidor. Se arregla programando.
- **ETABS** — límite de la aplicación o de la OAPI. No se arregla; se detecta
  temprano y se avisa con un mensaje útil.
- **PROTOCOLO** — falta en el guion de revisión, no en el software.

---

## 0. Corrección importante sobre el diagnóstico previo

Durante la sesión concluí tres veces que algo "no se podía verificar por API".
**Las tres conclusiones eran incorrectas.** El typelib muestra que los getters
existen; lo que faltaba eran herramientas que los expusieran:

| Lo que dije | Realidad | Método |
|---|---|---|
| "El espectro no se puede leer de vuelta" | Sí se puede | `Func.FuncRS.GetUser` (dispid 25) |
| "Las combinaciones no se pueden releer" | Sí se pueden | `RespCombo.GetCaseList` (dispid 8) |
| "El espesor de losa no se puede leer" | Sí se puede | `PropArea.GetSlab` (dispid 22) |

Causa del error: intenté leer todo por `get_table_data` y, cuando las tablas de
definición no devolvieron filas, di el canal por agotado sin buscar el getter
dedicado. **Regla: antes de declarar algo inaccesible, correr `describe_oapi`
sobre el namespace correspondiente.** La herramienta existe justamente para eso.

Consecuencia práctica: el espesor de losa de R10 **no requiere trabajo manual en
la interfaz**. `PropArea.SetSlab(Name, SlabType, ShellType, MatProp, Thickness)`
lo resuelve en una llamada.

---

## 1. Defectos de CÓDIGO — sin corregir

Ordenados por lo que más cuesta al reejecutar.

### 1.1 Ningún `add_*` es idempotente — BLOQUEANTE para reejecución

`add_load_pattern`, `add_load_combo`, `set_rigid_diaphragm` y las definiciones de
materiales y secciones fallan si el nombre ya existe. Peor: `RespCombo.SetCaseList`
**acumula** términos, así que reejecutar una combinación produce
`1.2D + 1.2D + 1.6L + 1.6L`.

Mordió de verdad en R04: el diafragma `D1` ya existía porque ETABS lo crea al
definir niveles, y hubo que liberarlo por tabla para poder crearlo.

**Corrección:** patrón uniforme en todas las herramientas de definición.

```python
# Pseudocodigo del patron a aplicar
try:
    crear()
except OapiError:
    if not existe(nombre):
        raise
    logger.info("'%s' ya existia: se actualiza en su lugar.", nombre)
    actualizar()          # y para combos: Delete() + Add() antes de SetCaseList
```

Para combinaciones, `Delete` antes de recrear es obligatorio, no opcional: es la
única forma de evitar la duplicación de factores.

### 1.2 No hay forma de borrar definiciones — BLOQUEANTE para trabajo iterativo

`delete_object` solo cubre puntos, frames y áreas. No hay manera de borrar un caso
de carga, un patrón, una combinación, una función o un material. Esta sesión dejó
dos residuos permanentes en el modelo (`ZZ_TEST_ESCRITURA`, `ZZ_TEST_FUNC`) que hay
que sacar a mano.

**Corrección:** una herramienta `delete_definition(kind, name)` que despache sobre
los `Delete` que ya existen en la OAPI:

| kind | Método |
|---|---|
| `load_case` | `LoadCases.Delete` (dispid 4) |
| `load_pattern` | `LoadPatterns.Delete` |
| `combo` | `RespCombo.Delete` |
| `function` | `Func.Delete` (dispid 4) |
| `material` | `PropMaterial.Delete` |
| `frame_section` | `PropFrame.Delete` |
| `area_section` | `PropArea.Delete` |
| `diaphragm` | `Diaphragm.Delete` (dispid 2) |

### 1.3 El parser de `get_table_data` no distingue una fila del encabezado

Separa campos de datos **por longitud**: busca una lista más corta que divida a la
más larga. Con una sola fila, datos y encabezado tienen el mismo largo y devuelve
"estructura no reconocible". Casi hace concluir que no había diafragmas en R04, y
bloqueó la lectura del espesor de losa en R10.

**Corrección:** dejar de adivinar. `GetTableForDisplayArray` devuelve
`NumberRecords` como parámetro `[out]`; usarlo para partir `TableData` en filas.

```python
# outs(result) -> (FieldKeyList, TableVersion, FieldsKeysIncluded, NumberRecords, TableData, ...)
n_rec  = <el int de outs que corresponde a NumberRecords>
fields = <la lista de strings que corresponde a FieldsKeysIncluded>
data   = <la lista de strings mas larga>
ncols  = len(data) // n_rec if n_rec else len(fields)
```

### 1.4 Faltan lectores de definiciones

Sin esto no se puede verificar nada de lo que se escribe. Es la causa raíz de que
R06, R07 y R10 hayan quedado con verificación incompleta.

| Herramienta nueva | Método OAPI |
|---|---|
| `get_load_combos()` | `RespCombo.GetNameList` + `GetCaseList` |
| `get_load_patterns()` | `LoadPatterns.GetNameList` + `GetLoadType` + `GetSelfWTMultiplier` |
| `get_spectrum(name)` | `Func.FuncRS.GetUser` |
| `get_area_sections()` | `PropArea.GetNameList` + `GetSlab` |
| `get_frame_sections()` | `PropFrame.GetNameList` + `GetRectangle` |
| `get_materials()` | `PropMaterial.GetNameList` + `GetOConcrete_1` + `GetWeightAndMass` |
| `get_diaphragms()` | `Diaphragm.GetNameList` + `GetDiaphragm` |
| `get_restraints()` | `PointObj.GetRestraint` sobre los puntos |
| `get_modal_results()` | tabla `Modal Periods And Frequencies` (ya funciona) |

### 1.5 No hay forma de definir secciones de área

Existen `define_rect_section`, `define_i_section`, `define_pipe_section` — ninguna
para losas o muros. Por eso las 12 áreas del modelo quedaron con el `Slab1` por
defecto de ETABS y R08–R10 salieron con un espesor de ≈0.197 m en vez de los
0.15 m documentados.

**Corrección:** `define_slab_section(name, material, thickness, slab_type="Slab",
shell_type="ShellThin")` sobre `PropArea.SetSlab`, más `assign_area_sections`
análoga a `assign_sections`.

### 1.6 `_add_point` omite un argumento obligatorio

`AddCartesian` declara `[in,out] Name` en cuarta posición y el código llama
`AddCartesian(x, y, z)`. Confirmado contra el typelib; no se ejercitó porque no se
creó geometría nueva. `_add_frame` sí lo pasa correctamente.

### 1.7 `add_time_history_case` apunta a un namespace inexistente

Usa `ModHistoryLinear` / `ModHistoryNonlinear`; los reales son `ModHistLinear` /
`ModHistNonlinear`. Produce `AttributeError` crudo, fuera de `oapi.call`, sin
mensaje útil. Además `SetLoads` se invoca con 9 y 7 argumentos contra una firma
de 10.

### 1.8 `define_cdcrd_spectrum` devuelve `ret=-99`

Con la firma exacta del typelib y datos válidos. Causa no determinada. Funciona
escribiendo la tabla `Functions - Response Spectrum - User Defined`.

**Corrección:** que la herramienta caiga automáticamente a la tabla cuando
`SetUser` falle, en vez de abortar. Y validar `Ts < t_max`, que hoy puede dejar el
espectro sin rama descendente en silencio.

### 1.9 Robustez — de la auditoría previa, sin aplicar

- `comthread`: `.result()` sin timeout con un solo worker. Un diálogo modal de
  ETABS cuelga **todas** las herramientas siguientes, sin error y para siempre.
- `run_analysis`: no verifica que el modelo esté guardado, requisito de ETABS.
- `add_response_spectrum_case`: no fija `SetModalCase`; hereda el modal por defecto.
- `set_base_restraints`: reutiliza la misma lista `values` en el bucle; si el array
  es `[in,out]`, comtypes puede mutarla tras la primera llamada.
- Las dos herramientas `async` (`get_geometries`, `create_objects_by_coordinates`)
  bloquean el event loop porque llaman métodos `@com_call` sin `to_thread`.
- `server.py`: el `FileHandler` se evalúa fuera de cualquier `try`; si `src/` fuera
  de solo lectura el servidor muere en el import. `dependencies` declara `pywin32`,
  que no se usa. La rama LUSAS importa un módulo inexistente.
- `config.py`: un `config.json` que no sea objeto JSON produce `AttributeError`
  fuera del `try`.
- Coeficiente de dilatación térmica `9.9e-6` / `11.7e-6` aplicado sin mirar si las
  unidades de temperatura son °C o °F.

---

## 2. Límites de ETABS — convivir, no arreglar

### 2.1 No se pueden redefinir niveles en un modelo con objetos

Tres rutas rechazadas con `ret=1`, con las firmas verificadas: `SetStories`,
`SetStories_2` y la edición de la tabla `Story Definitions`. Prueba decisiva: se le
pidió a `SetStories` la configuración que el modelo ya tenía y también falló.

Además, **editarlos desde la interfaz desplaza la geometría**: ETABS mantiene cada
objeto pegado a su nivel conservando el offset relativo. En este modelo bajó todo
`n × 0.6576 m` y hubo que repararlo con tres traslaciones.

**Lo que sí puede hacer el código:** detectarlo y avisar antes de fallar.

```python
# En set_stories, antes de intentar nada:
if self._count_objects() > 0:
    raise EtabsError(
        "El modelo ya tiene objetos (36 puntos, 63 frames, 12 areas). La OAPI de "
        "ETABS no permite redefinir niveles en ese estado: hay que hacerlo desde "
        "Edit > Stories and Grid System Data, y ESO DESPLAZA LA GEOMETRIA "
        "(cada objeto conserva su offset relativo al nivel). Guarde una copia "
        "antes. Para modelos nuevos: definir niveles ANTES de crear geometria.")
```

Un mensaje así ahorra el ciclo completo de diagnóstico que costó esta sesión.

### 2.2 Algunas tablas de definición no devuelven filas

`Load Combination Definitions`, `Load Case Definitions - Response Spectrum`,
`Modal Case Definitions` y `Functions - Response Spectrum - User Defined` devuelven
solo encabezados por `GetTableForDisplayArray`, con `ret=0`. Las tablas de
asignaciones y las de resultados sí funcionan.

**No hace falta resolverlo:** los getters dedicados de §1.4 cubren esos casos.

### 2.3 ETABS inyecta objetos por defecto que colisionan

Apareció tres veces: el diafragma `D1`, los patrones `Dead` y `Live` —con `Dead`
trayendo peso propio = 1, que habría duplicado la masa sísmica— y la losa `Slab1`.

**Lo que puede hacer el código:** ver §3.1.

---

## 3. Lo que falta para el caso de uso "otro modelo, un arreglo específico"

El servidor está construido para **crear** un modelo desde cero siguiendo un guion.
Para **abrir un modelo ajeno y hacerle un cambio puntual** faltan tres cosas.

### 3.1 `audit_model()` — inventario completo en una llamada

Lo primero que hace falta al abrir un modelo que no armaste vos. Debería devolver,
en un solo texto:

- Archivo, versión, unidades activas, si está bloqueado.
- Niveles con elevaciones y alturas; ejes.
- Conteo de puntos, frames y áreas, y su distribución por nivel.
- Materiales, con **peso por unidad de volumen** y f'c (para detectar los que
  quedaron en cero).
- Secciones de frame y de área, con dimensiones y espesores.
- Patrones de carga, marcando **cuáles tienen multiplicador de peso propio ≠ 0**
  (para detectar el `Dead` duplicado).
- Combinaciones con sus factores.
- Diafragmas y a cuántos puntos está asignado cada uno.
- Casos definidos; si hay resultados de análisis disponibles.
- **Sección de avisos**: materiales sin peso, más de un patrón con peso propio,
  objetos huérfanos, geometría que no coincide con los niveles, nombres que parecen
  residuos (`ZZ_*`, `TEST*`), secciones por defecto de ETABS sin revisar.

Esa última sección es la que convierte la herramienta en algo útil: los tres
hallazgos silenciosos de esta sesión habrían salido en el primer minuto.

### 3.2 Selectores en vez de listas de IDs a mano

Hoy, para mover 9 puntos de un nivel hubo que enumerar sus IDs leyendo la salida
de `get_points` y agrupándolos a ojo. Falta:

```python
select(obj_type, story=None, elevation=None, section=None,
       x_range=None, y_range=None, z_range=None, orientation=None)
# orientation: "vertical" | "horizontal" -> columnas vs vigas
```

Con eso, `move_objects`, `assign_sections`, `set_frame_releases` y las de carga
aceptarían un selector en lugar de una lista explícita.

### 3.3 Modo de simulación y verificación posterior

Para tocar un modelo ajeno hacen falta dos garantías:

- **`dry_run=True`** en toda herramienta que escriba: informa qué objetos afectaría
  y con qué valores, sin tocar nada.
- **Verificación automática de escritura**: releer con el getter correspondiente
  después de escribir y comparar. Es lo que hice a mano todo el protocolo y es lo
  que atrapó los tres defectos silenciosos.
- **Respaldo automático** antes de una operación destructiva, como el `.EDB` que
  copié antes de tocar los niveles.

---

## 4. Orden de implementación sugerido

Por relación entre lo que desbloquea y lo que cuesta.

**Tanda 1 — desbloquea verificar lo que ya existe.** §1.3 (parser por
`NumberRecords`), §1.4 (los nueve getters), §1.2 (`delete_definition`). Con esto
se cierran los huecos de verificación de R06, R07 y R10, y desaparecen los residuos.

**Tanda 2 — permite reejecutar sin romper.** §1.1 (idempotencia en todas las
definiciones), §1.5 (secciones de área), §2.1 (guarda de niveles con mensaje útil).

**Tanda 3 — robustez.** §1.6, §1.7, §1.8, §1.9.

**Tanda 4 — el caso de uso nuevo.** §3.1 (`audit_model`), §3.2 (selectores),
§3.3 (dry-run y verificación automática).

Cada tanda es independiente y verificable por separado. **Regla que sale de esta
sesión: agrupar en una tanda solo lo que está confirmado, y correr `describe_oapi`
para convertir sospechas en hechos antes de tocar nada** — aplicar un parche basado
en una suposición ya costó una reversión (ver `BRAIN\99_META\ERRORES-IA.md` E-019).
