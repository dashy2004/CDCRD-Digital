# Exportación y vistas (puente 0.3.x)

Cinco herramientas que cierran el paso de "exportar desde Civil 3D sin
diálogos". Verificadas en vivo (SOLAR.dwg, 2026-10-14).

| Herramienta | Hace | Vía .NET |
|---|---|---|
| `exportar_vista` | PDF/PNG/DWF **síncrono**, sin diálogos | `PlotFactory.CreatePublishEngine` + `PlotInfo` |
| `listar_papeles` | dispositivos de ploteo y papeles (canónico+visible) | `PlotSettingsValidator` |
| `vista_3d` | vista actual del modelo en 3D (iso u ortho) | `ViewTableRecord` + `SetCurrentView` |
| `crear_vista_guardada` | Named View (actual o construida) | `ViewTable.Add` |
| `activar_vista` | restaura una vista guardada | `SetCurrentView` |

## exportar_vista
Área a plotear, en orden de prioridad: `nombre_vista` (vista guardada — única
vía correcta para una vista 3D), `ventana` `x1,y1,x2,y2` (coords del modelo),
`handles` (extensión de esos objetos + margen), o la extensión completa.
`papel` acepta el nombre canónico, el visible o un pedazo (`A3`,
`full bleed A3`). `sombreado`: Wireframe|HiddenLine|Rendered|AsDisplayed.
`BACKGROUNDPLOT` se fuerza a 0 para que el ploteo sea síncrono; la respuesta
vuelve cuando el archivo existe, con su tamaño en bytes. Sin
"Cannot append to plot stamp log" que bloquee.

Ejemplo (perfil a PDF A3):
```
exportar_vista(ruta="C:/.../perfil.pdf", papel="full bleed A3",
               handles="7A10", confirmar=True)
```
Ejemplo (isométrico a PNG):
```
vista_3d(direccion="SE", handles="<sólidos>", estilo_visual="Conceptual", confirmar=True)
crear_vista_guardada(nombre="ISO-SONDEOS", confirmar=True)
exportar_vista(ruta="C:/.../iso.png", dispositivo="PublishToWeb PNG.pc3",
               nombre_vista="ISO-SONDEOS", sombreado="AsDisplayed", confirmar=True)
```

## vista_3d / crear_vista_guardada
`direccion`: SE|SW|NE|NW|PLANTA|FRENTE|DERECHA o `[x,y,z]`. `objetivo` y
`ancho` se deducen de `handles` (o de la extensión del dibujo) si se omiten.
`estilo_visual`: Conceptual, Realistic, Shaded, Wireframe, Hidden, X-Ray...
Para exportar una vista 3D hay que guardarla primero (PlotType.View).
