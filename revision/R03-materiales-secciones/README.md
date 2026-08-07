# R03 — Materiales y secciones

## Herramientas
```
define_concrete_material(name="H28", fc=28000)
define_rect_section(name="C50x50", material="H28", depth=0.50, width=0.50)
define_rect_section(name="V30x50", material="H28", depth=0.50, width=0.30)
assign_sections(column_section="C50x50", beam_section="V30x50")
```

## Captura
| Archivo | Vista | Estado |
|---|---|---|
| `01-material-h28.jpg` | Define > Materials > H28, propiedades | **hecha** — `R03-materiales-secciones/01-material-h28.jpg` |
| `02-secciones.jpg` | Define > Section Properties > Frame Sections | **hecha** — `R03-materiales-secciones/02-secciones.jpg` |
| `03-modelo-extruido.jpg` | Vista 3D con Extrude View activo (se ven las secciones reales) | **hecha** — `R03-materiales-secciones/03-modelo-extruido.jpg` |
| `04-seccion-columna.jpg` | Clic en una columna, ventana de propiedades mostrando C50x50 | **hecha** — `R03-materiales-secciones/04-seccion-columna.jpg` |
| `05-seccion-viga.jpg` | Clic en una viga, mostrando V30x50 | **hecha** — `R03-materiales-secciones/05-seccion-viga.jpg` |

Las cinco capturas se tomaron en la sesión de captura del 2026-08-08.

## Criterio de aceptación
- E ≈ 24.87e6 kN/m² (4700·√28 MPa convertido). **Verifica la corrección de unidades.**
- `assign_sections` reporta 27 columnas y 36 vigas. Si el reparto no es 27/36,
  la clasificación por geometría falló.
- En Extrude View las columnas se ven cuadradas y las vigas rectangulares peraltadas.

## Resultado

**Estado: OK por API.** Los tres puntos del criterio verificables por API se cumplen.
Capturas pendientes.

| Punto del criterio | Valor API | Criterio | Veredicto |
|---|---|---|---|
| Módulo de elasticidad | E = 2.48701e+07 kN/m² | ≈ 24.87e6 kN/m² | **OK** |
| Reparto columnas/vigas | 27 columnas, 36 vigas | 27 / 36 | **OK** |
| Extrude View | — | columnas cuadradas, vigas peraltadas | **PENDIENTE** (captura) |

El valor de E confirma la corrección de unidades, que es lo que este criterio
existe para probar: `4700·√28 MPa = 24 870 MPa`, y con el modelo en kN·m el
servidor lo devuelve como `2.48701e7 kN/m²`. La conversión la hace
`_stress_to_mpa()` leyendo `GetPresentUnits`, no por heurística de magnitud.

### Ejecutado

```
define_concrete_material(name="H28", fc=28000, unit_weight=23.5631)
define_rect_section(name="C50x50", material="H28", depth=0.50, width=0.50)
define_rect_section(name="V30x50", material="H28", depth=0.50, width=0.30)
assign_sections(column_section="C50x50", beam_section="V30x50")
save_model()
```

### Desviación respecto al script del bloque

Se agregó **`unit_weight=23.5631`** kN/m³, que el script original
no contemplaba porque el parámetro no existía. Sin él, ETABS crea el material con
peso por unidad de volumen **0** y el `self_weight_multiplier=1.0` del patrón `D`
en R05 no generaría ninguna carga muerta propia: el análisis correría sin error y
R08/R09/R10 darían resultados internamente consistentes pero equivocados. Era el
defecto más peligroso del informe `servidor-mcp\AUDITORIA-2026-08-07.md` (sección
4), corregido en esta sesión. La respuesta de la herramienta ahora incluye `w=` o
`SIN PESO`, para que la omisión sea visible en vez de silenciosa.

### Valores exactos que quedaron en el modelo

Elegidos explícitamente:

| Parámetro | Valor | Origen |
|---|---|---|
| Unidades | `kN, m, C` | el modelo abrió en `lb, in, F`; corregido con `set_units` |
| H28 · f'c | 28000 kN/m² (28 MPa) | script del bloque |
| H28 · peso volumétrico | 23.5631 kN/m³ | agregado en esta sesión; = 150 lb/ft³ = 2402.8 kgf/m³, el default de ETABS para hormigón de peso normal. El valor métrico redondo de 2400 kgf/m³ sería 23.536 kN/m³ (0.12% de diferencia) |
| C50x50 | t3 = 0.50 m, t2 = 0.50 m, H28 | script |
| V30x50 | t3 = 0.50 m, t2 = 0.30 m, H28 | script |

Puestos por defecto del servidor, **no revisados contra el CDCRD**:

| Parámetro | Valor | Dónde se fija |
|---|---|---|
| Poisson | 0.2 | default de `define_concrete_material` |
| E | 2.48701e7 kN/m² | calculado, `4700·√f'c` (ACI 318) |
| Coef. dilatación térmica | 9.9e-6 /°C | literal en `SetMPIsotropic` |
| Deformación en f'c | 0.0022 | literal en `SetOConcrete_1` |
| Deformación última | 0.0052 | literal en `SetOConcrete_1` |
| Pendiente final | -0.1 | literal en `SetOConcrete_1` |
| Hormigón liviano | No | literal en `SetOConcrete_1` |

Los cuatro últimos definen la curva tensión-deformación del hormigón. Están
escritos a mano en el servidor y nadie los contrastó con el CDCRD ni con ACI 318.
No afectan un análisis lineal, pero sí cualquier caso no lineal (R-P-Delta,
pushover) y el diseño. **Revisarlos antes de usarlos en esos contextos.**

Nota sobre la lectura de vuelta: `get_table_data` sobre
`Material Properties - Basic Mechanical Properties` y
`Frame Section Property Definitions - Concrete Rectangular` devuelve solo los
encabezados. La heurística de `get_table_data` separa campos de datos por
longitud y falla cuando la tabla tiene pocas filas. Es deuda del servidor, no un
problema del modelo; los valores de arriba provienen de las respuestas de cada
llamada de definición.

### Estado del modelo al cerrar

`save_model()` ejecutado. Dos condiciones heredadas de R02 que siguen abiertas y
que hay que tener presentes:

- **Los niveles siguen siendo `Story1..Story4` de 3.6576 m**, no `Nivel 1/2/3` de
  3 m. La OAPI no permite redefinirlos en un modelo poblado (ver README de R02).
  No afecta a R03: materiales y secciones no dependen de los niveles. **Sí va a
  afectar a R09**, donde las derivas se reportan por nivel y los niveles actuales
  no coinciden con las cotas reales de la geometría (0/3/6/9 m).
- **El material de prueba `ZZ_TEST_ESCRITURA` sigue en el modelo.** No se usó en
  ninguna asignación: `assign_sections` solo aplica `C50x50` y `V30x50`, ambas de
  `H28`. Borrarlo desde `Define > Material Properties` cuando se pase por la UI.
