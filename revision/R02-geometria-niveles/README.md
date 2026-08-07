# R02 — Geometría y niveles

## Herramientas
`get_points`, `get_frames`, `get_areas`, `set_stories`, `get_stories`

`set_stories(story_names=["Nivel 1","Nivel 2","Nivel 3"], story_heights=[3,3,3], base_elevation=0)`

## Captura
| Archivo | Vista | Estado |
|---|---|---|
| `01-vista-3d.jpg` | Vista 3D completa del modelo | **PENDIENTE** |
| `02-planta-nivel1.jpg` | Planta del Nivel 1 (Ctrl+W o View > Set Plan View) | **PENDIENTE** |
| `03-elevacion-eje1.jpg` | Elevación del eje 1 | **PENDIENTE** |
| `04-story-data.jpg` | Define > Story Data, mostrando los 3 niveles | **PENDIENTE** |

Las cuatro capturas quedan pendientes para una sesión con control de escritorio
aprobado. Ninguna se ha tomado a la fecha.

## Criterio de aceptación
- 36 puntos, 63 frames (27 columnas + 36 vigas), 12 áreas.
- Ninguna barra duplicada ni nodo colgado.
- Story Data: Nivel 1/2/3, altura 3 m cada uno, base en 0.

## Nota
Primera prueba real del mecanismo `oapi.call` con variantes de firma.
Revisar `servidor-mcp\src\fea_mcp.log` y anotar aquí qué variante de
`SetStories` funcionó.

---

# Resultado

**Estado del bloque: PARCIAL.** Geometría y unidades verificadas OK por API.
Niveles **no ejecutables por MCP**: no es un defecto del servidor, es una
limitación de la OAPI de ETABS sobre modelos ya poblados (ver "Hallazgo
principal"). Capturas pendientes.

## Tabla de verificación

| Punto del criterio | Valor API | Criterio | Veredicto |
|---|---|---|---|
| Conexión ETABS / OAPI | 23.3.0 / 2.016 | 23.3.0 / 2.016 | **OK** |
| Unidades | `lb, in, F` → `kN, m, C` vía `set_units` | kN, m, C | **OK** |
| Puntos | 36 | 36 | **OK** |
| Frames | 63 (27 columnas + 36 vigas) | 63 | **OK** |
| Áreas | 12, todas de 4 vértices con cota homogénea | 12 | **OK** |
| Barras duplicadas | 0 | ninguna | **OK** |
| Nodos colgados | 0 | ninguno | **OK** |
| Story Data (Nivel 1/2/3, 3 m, base 0) | sigue Story1..4 de 3.6576 m | 3 niveles de 3 m | **NO EJECUTABLE POR API** |
| Variante de `SetStories` que funcionó | ninguna | — | **NINGUNA** — las 5 devuelven `ret=1` |

Clasificación de columnas y detección de duplicados/colgados: hecha
programáticamente sobre la respuesta cruda de `get_points`/`get_frames`
(comparación de coordenadas y de pares de extremos), no visualmente.

---

## Hallazgo principal: la OAPI no redefine niveles en un modelo poblado

Tres rutas independientes, todas rechazadas con el mismo código:

| Ruta | Firma verificada contra el typelib | Resultado |
|---|---|---|
| `Story.SetStories` (7 arrays) | sí, dispid 15 | `ret=1` |
| `Story.SetStories_2` (9 args) | sí, dispid 17 | `ret=1` |
| `DatabaseTables.SetTableForEditingArray` | sí, dispid 21 | `ret=1` |

La prueba que cierra el diagnóstico: se le pidió a `SetStories` **exactamente la
configuración que el modelo ya tenía** — los mismos `Story1..Story4` de 3.6576 m
que `GetStories` acababa de reportar. También `ret=1`. Un no-op rechazado
descarta como causa el contenido, los nombres, los espacios en los nombres, las
unidades, el orden de los arrays y la convención master/similar.

Tampoco es permisos ni bloqueo del modelo:

- El candado se abrió y no cambió nada.
- El modelo **sí acepta escrituras**: `define_concrete_material` creó
  `ZZ_TEST_ESCRITURA` con su peso por unidad de volumen sin error.
- `GetTableForEditingArray` sobre `Story Definitions` devuelve `ret=1`: la tabla
  ni siquiera se puede **abrir** para edición, por eso `TableVersion` nunca se
  obtuvo y la escritura cayó a valores literales.

Interpretación: `SetStories*` **reconstruye** la estructura de niveles, y ETABS
la rechaza cuando hay objetos asignados a esos niveles (36 puntos, 63 frames,
12 áreas). Coincide con lo que ya estaba anotado en [[EQUIPO - Windows]]: que
`AddByCoord` necesita stories definidos previamente. **El flujo soportado es
niveles primero, geometría después; este modelo se construyó al revés.**

`Story` sí expone setters por nivel que probablemente funcionen
(`SetHeight`, `SetElevation`, `SetMasterStory`, `SetSimilarTo`, `SetSplice`),
pero **no hay `DeleteStory` ni forma de renombrar**, así que no permiten pasar de
4 niveles `Story*` a 3 niveles `Nivel*`. No alcanzan para el criterio.

### Consecuencia operativa

El paso de niveles de R02 pasa a ser **manual**: `Edit > Stories and Grid System
Data` en ETABS, definir Nivel 1/2/3 de 3 m con base en 0. Después se verifica por
API con `get_stories`. No es una regresión del servidor: es el orden correcto de
construcción del modelo, que el protocolo asumía invertido.

Para modelos futuros del CDCRD: **definir los niveles antes de crear geometría**.
Con el modelo vacío, `set_stories` debería funcionar; conviene confirmarlo la
primera vez que se cree un modelo desde cero.

---

## Firmas reales leídas del typelib (`describe_oapi` corregido)

Esto es lo que el bloque pedía anotar. Ninguna se obtuvo por conjetura.

```
SetStories([in] StoryNames: SAFEARRAY(BSTR), [in] StoryElevations: SAFEARRAY(double),
           [in] StoryHeights: SAFEARRAY(double), [in] IsMasterStory: SAFEARRAY(bool),
           [in] SimilarToStory: SAFEARRAY(BSTR), [in] SpliceAbove: SAFEARRAY(bool),
           [in] SpliceHeight: SAFEARRAY(double), [out,retval] pRetVal: long*)   [dispid 15]

SetStories_2([in] BaseElevation: double, [in] NumberStories: long,
             [in,out] StoryNames, StoryHeights, IsMasterStory, SimilarToStory,
             SpliceAbove, SpliceHeight, Color, [out,retval] pRetVal)            [dispid 17]
```

Dos correcciones importantes que esto dejó firmes:

- **`SetStories` lleva elevaciones ANTES que alturas**, y no lleva conteo líder.
  La deducción previa desde `GetStories_2` en runtime era correcta.
- **`SetStories_2` NO lleva elevaciones**: las deduce de base + alturas. Cualquier
  variante que se las pase falla en el marshaling con
  `unicode string expected instead of bool instance`.

Otras firmas volcadas en la misma sesión, que cierran sospechas del informe de
auditoría sin gastar ciclos:

- `JointReact` → `Obj, Elm, LoadCase, StepType` (el caso es la **tercera** lista
  de strings) y `StepNum, F1..F3, M1..M3` (las componentes son las **seis
  últimas** numéricas). Confirma el parche §3.
- `FrameForce` → tres columnas numéricas (`ObjSta, ElmSta, StepNum`) preceden a
  `P`. Confirma el parche §3.
- `StoryDrifts` → `Story, LoadCase, StepType, Direction, Label` + `StepNum,
  Drift, X, Y, Z`. `get_story_drifts` ya los leía bien.
- `SetOSteel_1` y `SetWeightAndMass` → coinciden con los parches §5 y §4.
- `AddCartesian([in] X, Y, Z, [in,out] Name, ...)` → en la contradicción §6 del
  informe, el método mal escrito es **`_add_point`** (omite `Name`), no
  `_add_frame`. Anotado, sin corregir en esta pasada.
- `GetAllAreas(..., [in,out] NumberBoundaryPts: long*, ...)` → es un **escalar**
  (total de vértices), no un array por área. Refuta el parche §7.3 del informe,
  que fue **revertido**. El indexado original por `PointDelimiter` era correcto.

---

## Cronología de bloqueos resueltos

Tres bloqueos distintos, encadenados, cada uno enmascarando al siguiente:

1. **Despliegue** — el config MSIX lanzaba la v1.0 de 10 herramientas.
   Repuntado a la v1.1.0 de 44. **Resuelto.**
2. **Conexión COM** — `MK_E_UNAVAILABLE`, desajuste de privilegios entre
   Claude Desktop y ETABS. Resuelto reiniciando la máquina y abriendo ambos como
   Administrador. **Resuelto.** El log mentía con `Adjuntado a ETABS via cHelper`
   sin comprobar el retorno; corregido (ver [[ERRORES-IA]] E-017).
3. **`describe_oapi` roto** — leía `entry[2]` como nombre de método asumiendo un
   layout de `comtypes` anterior; en 1.4.16 ese campo es `argtypes`. Corregido, y
   es lo que permitió leer todas las firmas de arriba de una sola vez en vez de
   un reinicio por método. **Resuelto.**

## Estado del modelo al cerrar

Intacto en lo relevante. Los cinco intentos de `set_stories` y los dos de tabla
fallaron de forma atómica: `get_stories` sigue devolviendo los 4 niveles
originales y `get_areas` las 12 áreas correctas.

**Pendiente de limpieza:** el material de prueba `ZZ_TEST_ESCRITURA` quedó en el
modelo (se creó para descartar el bloqueo de escritura). No hay herramienta MCP
para borrar materiales: sacarlo desde `Define > Material Properties` antes de
R03, para que no se cuele en las asignaciones.

## Deuda de código abierta

Del informe `servidor-mcp\AUDITORIA-2026-08-07.md`, sin aplicar en esta pasada:
§6 (`_add_point` omite `Name`, ya confirmado por typelib), §7.1 y §7.2
(idempotencia de patrones y combinaciones), §7.4 (`ModHistLinear` mal escrito),
§7.5, §7.6 (timeout del hilo COM) y los menores de §8.
