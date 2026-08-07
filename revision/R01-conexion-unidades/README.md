# R01 — Conexión y unidades

## Herramientas
`get_model_info`, `get_units`, `set_units("kN, m, C")`

## Captura
| Archivo | Vista | Estado |
|---|---|---|
| `01-etabs-abierto.jpg` | Ventana de ETABS con el modelo cargado, barra de título visible | **hecha** — `R01-conexion-unidades/01-etabs-abierto.jpg` |
| `02-unidades.jpg` | Esquina inferior derecha con el selector de unidades en kN, m, C | **hecha** — `R01-conexion-unidades/02-unidades.jpg` |

## Criterio de aceptación
- ETABS 23.3.0, OAPI 2.016.
- Unidades activas kN, m, C tanto en la API como en el selector de la interfaz.
- El título de la ventana muestra `edificio_oficinas_SD`.

## Resultado
- API: ETABS 23.3.0 / OAPI 2.016, unidades kN, m, C. **OK**
- Interfaz: verificada por captura (sesión 2026-08-08), unidades kN, m, C confirmadas en el selector inferior derecho. **OK**
