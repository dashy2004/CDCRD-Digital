# generar_perfil_estratigrafico (Etapa 3.2)

Una sola herramienta de alto nivel que arma un perfil estratigráfico completo de
cualquier corte, 100% con objetos nativos de Civil 3D y repetible por `spec`.
Cero constantes hardcodeadas: sondeos, estratos, colores, origen y export salen
del spec y de la base de sondeos. **Datos geotécnicos hipotéticos/preliminares.**

## Qué hace
1. Perfil de terreno + un perfil por superficie de estrato (CreateFromSurface) +
   perfil de fondo a cota fija (CreateByLayout).
2. Vista de perfil en el origen dado, con rango de elevación calculado de los
   sondeos si no se indica.
3. Un ShapeStyle por estrato (clon de una base SOLID) con su color.
4. Relleno nativo (HatchAreas.Add) entre perfiles consecutivos; el último estrato
   hasta el perfil de fondo.
5. Columnas de sondeo, etiquetas N-SPT y nivel freático dibujados en coordenadas
   exactas de la vista con `FindXYAtStationAndElevation` (sin matemática de
   escala). La estación de cada sondeo sale de `Alignment.StationOffset(x,y)`.
6. Leyenda de estratos.
7. Export a PDF/PNG por vista guardada en planta (sin diálogos).

## spec (JSON)
```json
{
  "prefijo": "PERFIL",
  "alineamiento": "Corte A-A'",
  "superficie_terreno": "TERRENO_FABDEM_SITIO",
  "sondeos": ["S-4","S-3","S-2"],
  "origen": [410000, 2044000],
  "db_sondeos": "C:/Civil3D_Geo/GeotechnicalModeler.db",
  "csv_ubicaciones": "C:/Civil3D_Geo/sondeos_ubicaciones.csv",
  "csv_estratigrafia": "C:/Civil3D_Geo/sondeos_estratigrafia.csv",
  "estilo_forma_base": "GEO - Relleno",
  "estratos": [
    {"codigo":101,"nombre":"RELLENO","superficie":"GM - Stratum - RELLENO.1","color_aci":34},
    {"codigo":205,"nombre":"ARCILLA RESIDUAL","superficie":"GM - Stratum - ARCILLA RESIDUAL.1","color_aci":12},
    {"codigo":310,"nombre":"CALIZA METEORIZADA","superficie":"GM - Stratum - CALIZA METEORIZADA.1","color_aci":51},
    {"codigo":320,"nombre":"CALIZA COMPETENTE","superficie":"GM - Stratum - CALIZA COMPETENTE.1","color_aci":8}
  ],
  "mostrar": {"spt": true, "nivel_freatico": true, "leyenda": true, "columnas": true},
  "exportar": {"pdf":"C:/.../perfil.pdf","png":"C:/.../perfil.png","papel":"full bleed A3"}
}
```
Fuente de sondeos: usa `db_sondeos` si existe (sobre COPIA local — SQLite en
carpeta montada da "disk I/O error"), si no los CSV. El N-SPT y el nivel freático
se leen de la columna Description cuando no vienen estructurados.

## Verificación en vivo (2026-10-14, v0.3.2, origen 410000) — COMPLETA
`pruebas/demo_perfil.py` reprodujo el corte A-A' desde cero con 0 advertencias:
6 perfiles, vista, 5 hatches nativos (terreno→techo del 1er estrato + 4 estratos),
33 entidades (columnas, N-SPT, N.F.), leyenda, PDF A3 (105 KB) y PNG.
**Estaciones S-4=0.00, S-3=243.52, S-2=502.94 — idénticas al perfil hecho a mano.**
Los rellenos coinciden con las columnas de sondeo (verificado visualmente sobre
el PDF). Cada superficie "GM - Stratum - X" es el TECHO de X: el relleno de X va
de su techo al techo del siguiente; `rellenar_hasta_terreno` (default true) pinta
con el color del 1er estrato el hueco entre el TIN del terreno y el techo
interpolado del relleno (diferencia real FABDEM vs sondeos, visible a la derecha).
El PNG de PublishToWeb sale en papel vertical por defecto: use `papel_png`.

## Estilo de vista y grilla (2026-10-15)
Claves nuevas del spec: `grilla_tenue` (default `true`) crea un
ProfileViewStyle propio `<prefijo>-VISTA_<base>` clonado de
`estilo_vista_base` (default `"Major Grids"`; el nombre lleva un slug de la
base para no purgar+recrear, que anula CopyAsSibling) y atenúa las grillas
mayores a `grilla_color_aci` (default 253) apagando las menores si la base
las trae. `exageracion` (número) escribe
`GraphStyle.VerticalExaggeration` en ese estilo. La grilla de la vista se
dibuja por encima de los HatchAreas nativos y ese orden no es controlable
por API: atenuarla es la salida. Ojo: `"Standard"` en este dibujo es la
plantilla imperial del GM — no usarla de base.

## Suite de humo
`pruebas/humo_perfil.py` (lanzada con `_diag/humo-perfil.ps1`): limpia,
genera el corte A-A' completo y verifica 0 advertencias, estaciones exactas,
PDF/PNG exportados y la presencia de los 4 colores de estrato en el PNG con
`pruebas/verificar_png.py` (decodificador PNG en Python puro, probado
offline en `tests/test_verificar_png.py`). Verificada en vivo 2026-10-15:
13/13 OK.

## MCP
`generar_perfil_estratigrafico(spec)` en el servidor (disponible cuando el
cliente MCP recargue el servidor Python). La lógica está en
`src/perfil_estratigrafico.py`; `generar(spec, puente)` es reutilizable.
