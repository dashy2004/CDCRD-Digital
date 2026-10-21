# 3D e isometricos (Etapa 3.4)

Recetas sobre primitivas nativas ya verificadas (`entity.create` con cilindro,
`vista.3d`, `vista.guardada`, `vista.exportar`, `layout.crear`). Codigo en
`src/tridimensional.py`; demo en vivo en `pruebas/demo_3d.py`. Datos
geotecnicos siempre hipoteticos/preliminares.

## isometrico_sondeos_3d

Columnas 3D de sondeos (un cilindro solido por estrato, a coordenadas reales)
mas las superficies de estrato, vista isometrica guardada y export PNG/PDF.

| Parametro del spec (JSON) | Notas |
|---|---|
| `prefijo` | de la capa, la vista guardada y los archivos (`ISO` por defecto) |
| `sondeos` | ids a dibujar; vacio = todos los de la base |
| `estratos` | `[{codigo, nombre, superficie, color_aci}]` |
| `superficie_terreno`, `mostrar_terreno` | el terreno opaco tapa todo: por defecto va apagado |
| `db_sondeos` / `csv_ubicaciones` + `csv_estratigrafia` | la DB SQLite se copia a local antes de abrirla (sobre carpeta montada da `disk I/O error`) |
| `radio`, `exageracion_z` | la boca del sondeo queda en su sitio; el fondo baja `exageracion_z` veces mas |
| `direccion` | `SE\|SW\|NE\|NW` o `[x,y,z]` |
| `estilo_visual` | `X-Ray` por defecto: deja ver las columnas bajo las superficies |
| `exportar` | `{png, pdf, papel, papel_png}` |

```
isometrico_sondeos_3d(spec='{"prefijo":"ISO","estratos":[...],"direccion":"SW"}')
```

Errores comunes: superficie de estrato inexistente (revisar el sufijo `.1` del
GM con `gm_diagnosticar`); export por ventana casi vacio (la receta usa vista
guardada justamente por eso).

## copiar_vista_perfil_a_3d

Copy to 3D nativo: cada perfil de la vista pasa a una polilinea 3D en
coordenadas del modelo (XY del eje por `PointLocation`, Z por `ElevationAt`).

| Parametro | Notas |
|---|---|
| `vista` | handle de la vista de perfil |
| `paso` | metros entre vertices (10 por defecto) |
| `prefijo` | capa `<prefijo>-PERFILES` |
| `solo` | prefijos de nombre de perfil separados por coma; vacio = todos |
| `confirmar` | escritura |

```
copiar_vista_perfil_a_3d(vista='86A0', paso=10, confirmar=True)
```

Si el alineamiento de la vista no tiene perfiles, la respuesta lo dice en
`advertencias` (y `creado` sale vacio). Verificada en vivo 2026-10-15:
6 polilineas del corte A-A' sin advertencias.

## toma_de_cerca_3d

Zoom 3D a un sondeo/estrato/objeto por `handles` o por `objetivo 'x,y,z'` +
`ancho`, lo guarda como vista (`nombre`) y lo exporta (`ruta`, PNG por
defecto). `estilo_visual` `Conceptual` por defecto.

## crear_layout

Presentacion con papel, viewports desde vistas guardadas y textos de rotulo.

| Parametro | Notas |
|---|---|
| `nombre` | la presentacion se crea o se reemplaza |
| `papel` | nombre canonico, visible o un pedazo (`A3`) |
| `viewports` | `[{"vista","centro":[x,y] mm,"ancho","alto","escala","bloquear"}]`; sin `escala` encuadra la vista |
| `textos` | `[{"punto":[x,y],"texto","altura"}]` en mm de papel |

Despues `exportar_vista(layout=nombre)` la plotea a 1:1. Nota: en layouts no
se centra el plot (`SetPlotCentered` es `eInvalidInput` con
`PlotType.Layout`; el puente >= 0.5.0 lo omite y plotea desde el origen).
