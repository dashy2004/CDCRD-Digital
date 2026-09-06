# Ejemplo: Residencial 4N (edificio residencial de 4 niveles, 8 apartamentos)

Caso generico para probar el flujo completo **modelar desde cero -> verificar con vision ->
documentar -> exportar a ETABS** con `revit-mcp-tools`. Coincide con el proyecto tipico de un
curso universitario de diseño asistido por computadora para edificaciones: un edificio
residencial de 4 niveles con 2 apartamentos por nivel, modelado estructural y planos.

Todos los nombres son inventados. No hay datos de ningun proyecto real.

## Geometria

| Dato | Valor |
|---|---|
| Planta | 20.00 x 12.00 m |
| Ejes | A-E cada 5.00 m (verticales), 1-4 cada 4.00 m (horizontales) |
| Niveles | CIMENTACION -1.50 · N1 0.00 · N2 3.00 · N3 6.00 · N4 9.00 · TECHO 12.00 |
| Columnas | C40x40, 20 por nivel, 4 tramos (80) |
| Vigas | V30x50 en todos los ejes de N2 a TECHO (31 por nivel, 124) |
| Losas | maciza 15 cm, envolvente de ejes, N2 a TECHO (4) |
| Zapatas | 1.20 x 1.20 x 0.40 bajo cada columna de CIMENTACION (20) |
| Muros | bloque 15 cm, perimetro de N1 y divisorio en eje C (no estructurales) |

## Como correrlo

Sobre un **proyecto nuevo** (plantilla Structural Analysis-DefaultMetric) o una copia
sacrificable. Nunca sobre un modelo de trabajo: la receta crea niveles y ejes con nombres
comunes (A, B, 1, 2...) y si ya existen los reutiliza.

```
cd revit-mcp-tools\ejemplos
python correr_receta.py residencial-4n\receta.json                    # todo en dry_run: plan, sin escribir
python correr_receta.py residencial-4n\receta.json --real --salida C:\salidas\r4n
python correr_receta.py residencial-4n\receta.json --limpiar --real   # borra todo lo creado
```

Desde un cliente MCP es lo mismo paso a paso: cada entrada de `pasos` es una llamada
`revit_<tool>(**params)`.

## Lo que produce

- Modelo estructural completo con cada elemento marcado en `Comments` (`AGENTE:COL`,
  `AGENTE:VIGA`, ...): `revit_borrar_por_marca` lo deja como estaba.
- Plantas estructurales por nivel (sin underlay, corte a 1.50 m, recortadas al edificio).
- Vista `3D ESTRUCTURA` con caja de seccion y PNG de verificacion.
- Tablas de columnas, vigas, losas y zapatas.
- Laminas E-01..E-05 con planta + tablas, escala ajustada a la lamina.
- `residencial-4n-estructura.pdf`, `residencial-4n.ifc`, `proyecto.json`.

Corrida verificada 2026-09-06 en Revit 2027 sobre un proyecto nuevo: 30 pasos, ~15 s, 233
elementos, 0 advertencias en `auditar`.

## Continuar en ETABS

`proyecto.json` trae el bloque `etabs` con los argumentos ya traducidos para el servidor `fea`
(`servidor-mcp/`): `set_stories`, `define_concrete_material`, `define_rect_section`,
`create_objects_by_coordinates`. Secuencia sugerida: `set_units(kN, m)` -> `set_stories` ->
materiales -> secciones -> `create_objects_by_coordinates` -> `assign_sections` ->
`set_base_restraints` -> cargas del CDCRD (`datos/machine/`) -> `run_analysis`.

## Que mirar antes de dar por buena una corrida

La receta exporta PNG en los pasos 22 y 26. Abrirlos. Lo que se busca: columnas que sobresalen
del techo (Top Offset residual), vistas que se salen de la lamina, tablas sobre el cajetin,
ejes que no aparecen en planta. Las cuatro cosas pasaron durante el desarrollo y ninguna la
reportaba la API.
