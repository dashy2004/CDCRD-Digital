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

## Verificación en vivo (2026-10-14, v0.3.0, origen 410000)
`pruebas/demo_perfil.py` reprodujo el corte A-A' desde cero: 6 perfiles, vista,
4 hatches encadenados, 33 entidades, export. **Estaciones S-4=0.00, S-3=243.52,
S-2=502.94 — coinciden exactamente con el perfil hecho a mano.** Pendiente de
v0.3.1: color por estrato (en v0.3.0 el color quedaba como fallido silencioso) y
export por vista guardada en planta (el plot por ventana salía casi vacío).

## MCP
`generar_perfil_estratigrafico(spec)` en el servidor (disponible cuando el
cliente MCP recargue el servidor Python). La lógica está en
`src/perfil_estratigrafico.py`; `generar(spec, puente)` es reutilizable.
