# Corrida viva de las tools de pilotes — procedimiento [T → H]

Fecha de implementación: 2026-11-02 (claude, Fable local). Tools: `get_pile_spacing`,
`get_pile_axial_reactions`. Solo lectura; no hace falta copia `_pruebas-mcp.FDB`, pero
tampoco estorba. Reiniciar Claude Desktop desde la bandeja para cargar la v0.3.0.

Nada de lo de abajo entra en el repo con nombre de proyecto, cliente ni coordenadas: el
resultado se registra en BRAIN y en el buzón; aquí solo el procedimiento y el estado.

## 1. Lectura de frames y secciones

1. `get_model_info()` y `get_units()`.
2. `describe_oapi(path="FrameObj", filter="GetAllFrames")` y
   `describe_oapi(path="PropFrame", filter="Circle")`: confirmar que las firmas coinciden
   con el bloque PILOTES de `Safe.py` (ENUMS-SAFE.md, sección Pilotes).
3. `call_oapi(path="PropFrame", method="GetNameList", args=[0, [], 9])`: debe devolver
   solo secciones circulares. Si devuelve todas, `get_pile_spacing` igual las filtra con
   `GetTypeOAPI` (anotar el comportamiento).
4. `get_pile_spacing(units="kN, m, C")`:
   - `n_frames_modelo` igual al conteo de frames de la interfaz;
   - `n_pilotes` igual al número de pilotes del modelo (si hay columnas/vigas con
     sección circular, usar `sections=[...]`);
   - `secciones_circulares[...]["diametro_mm"]` igual al diámetro de la sección;
   - `unidades` restauradas: `get_units()` devuelve las de antes de la llamada;
   - un pilote cualquiera: `x, y, z_cabeza` coinciden con la interfaz y `z_cabeza > z_punta`.
5. Repetir con `units="N, mm, C"`: mismos S/B, diámetros y distancias ×1000.

## 2. Criterio

6. Comparar `resumen.s_b` (min/mediana/max) e `histograma_s_b` con el conteo hecho a mano
   el 2026-11-02 (script de Cowork sobre el `.$sf`). Los promedios de factor deben salir con
   escalón inferior (step_down); con `interpolation="linear"` deben reproducir los valores
   interpolados del primer cálculo.
7. `resumen.fuera_de_tabla.ids` debe listar exactamente los pilotes con S/B < 3.
8. `scope="by_footing"`: cada cabezal con su número de pilotes; pilotes "fuera de todo
   cabezal" solo si realmente no hay área Footing bajo ellos (si los cabezales son Mat o
   Stiff, pasar `cap_types="footing,mat"` o el tipo que corresponda).
9. Con `q_ult`, `fs` o `q_adm`: la salida nunca dice "cumple"; (b) aparece como PENDIENTE.

## 3. Reacciones

10. Modelo analizado (`get_analysis_status` → todos listos).
11. `get_pile_axial_reactions(combos=["<una combinación gravitatoria>"])`:
    - `envolvente.critico` coincide con el pilote más cargado de la tabla de reacciones
      de la interfaz (Display > Show Tables > Joint Reactions) para ese combo;
    - **signo**: en un combo gravitatorio la `compresion_max` debe ser positiva. Si sale
      negativa, la convención de `F3` es la contraria y hay que invertirla en
      `_axial_pilote` (anotar aquí y en ENUMS-SAFE.md).
12. `source="frame"` con el mismo combo: `compresion_max` del mismo orden que por joint
    (difiere por el peso propio del pilote si está activo). Confirmar que `-P` es compresión.
13. Si `avisos` dice "sin reaccion/fuerza": las puntas no tienen restricción ni resorte
    (los pilotes están sobre resortes de área o de punto). Usar `source="frame"`.

## 4. Cierre

- Cada paso que pase: [H] con fecha y firma en ENUMS-SAFE.md (sección Pilotes) y en
  `OAPI-SAFE-real.md` §2.8 si cambia algo de Results.
- Un `ret != 0` o una forma distinta de salida: [X] con el código, sin reintentar con
  variantes.
- Resultado a BRAIN (nota del proyecto) y buzón; aquí solo el estado.

## Estado — corrida viva 2026-11-02 [claude, Fable local]

Conexión directa por COM con el código nuevo (sin pasar por el servidor MCP cargado en
Claude Desktop, que seguía en v0.2.1), SAFE 23.3.0 / OAPI 2.016, modelo real de pilotes
de la firma (847 frames, 561 pilotes de una sección circular Ø450, 44 cabezales tipo
Footing, 39 combinaciones, análisis sin correr). Nombre y coordenadas quedan en BRAIN.

| Paso | Estado | Evidencia |
|---|---|---|
| 1-3 firmas | **[H]** | `describe_oapi` en vivo coincide con el typelib; `PropFrame.GetNameList(0,[],9)` devuelve solo la circular (con modelo en blanco devolvió `(0, [])`, ret=0: el filtro funciona y el chequeo de tipo no estorba). |
| 4 lectura | **[H]** | `n_frames_modelo` = 847 = conteo del modelo; `n_pilotes` = 561 (solo P45; `BEAM1` y los `M*-W` quedan fuera sin filtrar por nombre); `diametro_mm` = 450.0 leído de T3 = 17.7165 in; `get_units` devuelve `lb, in, F` antes y después de cada llamada. |
| 5 unidades | **[H]** | `N, mm, C` da las mismas S/B y distancias ×1000 (mediana 2250 mm frente a 2.25 m). |
| 6-7 criterio | **[H]** | Mediana S/B 5.0 (malla a 2.25 m) con factor 0.9 por escalón inferior: el `_TOL_SB` evita que 2.25/0.45 caiga a 0.8. `linear` reproduce el promedio del cálculo manual del mismo día (0.889 frente a 0.89); el promedio `step_down` manual (0.81) quedó por debajo del de la tool (0.867), lo que es compatible con un escalón mal tomado en S/B = 5.0 por coma flotante en ese script. Lista `fuera_de_tabla` completa (12 en barrido global, 8 por cabezal). |
| 8 by_footing | **[H]** | 44 cabezales, 0 pilotes sin cabezal, 7 cabezales de un solo pilote reportados `sin_vecino` (factor 1.0, no fuera de tabla). Mismo S/B mínimo que el barrido global (2.157). |
| 9 capacidad | **[H]** | Con `q_ult` y `fs`: (a) por cabezal, (b) PENDIENTE y `capacidad_grupo` NO DETERMINADA en todos; ninguna salida dice "cumple". |
| avisos | **[H]** | Detectó 3 frames duplicados en la misma coordenada y 7 frames inclinados (varios de ellos son los que forman las parejas con S/B < 3): revisión de modelado para el ingeniero, no decisión de la tool. |
| 10 análisis | **[H]** | Autorizado por Emil; `run_analysis` 32 s, 9 casos listos (los 8 del modelo más `~LLRF`). **Corrección:** `RunAnalysis` guardó el FDB en disco (fecha del archivo = hora del análisis); la geometría y las cargas no cambiaron, pero el archivo ya no es el de antes del análisis. |
| 11 signo | **[H]** | Caso `Dead` por `joint` y por `frame`: mismo pilote crítico y misma cifra (659.0 kN, compresión positiva en los dos). `JointReact.F3 > 0` = compresión y `FrameForce.P < 0` = compresión confirmados; `StepType` = "Single Value" en casos, "Max"/"Min" en combos. |
| 12 envolvente | **[H]** | 39 combos por `joint`: 41 736 registros en 1.7 s, crítico con caso y paso, tracción máxima por pilote, ratio y lista `no_cumplen` contra `q_adm`. Los frames duplicados se leen (564, no 561) y se avisan. |
| 13 uso | **[H]** | El ratio contra una admisible de servicio solo vale con combos de servicio: la tool lo avisa cuando `q_adm` se combina con todas las combos. Los siete frames duplicados/inclinados salieron como los más cargados con ratios absurdos: el aviso de duplicados apunta ahí. |

| 14 export | **[H]** | `export_pile_check_xlsx` sobre el mismo modelo analizado: 3.2 s, 124 KB, seis hojas; `RespCombo.GetCaseList` y `LoadCases.GetTypeOAPI_1` [H] (los casos de sismo del modelo son estáticos equivalentes: CaseType 1 con DesignType 5 = Quake; sin ese dato las combos puramente laterales se habrían tomado como servicio). Cifras idénticas al prototipo hecho a mano con las salidas JSON: mismas combos de servicio, mismo crítico, mismos conteos de no cumplen / tracción / cabezales / candidatos. Unidades restauradas. |

| 15 propuesta | **[H]** | `suggest_pile_changes`: 9 añadir, 3 quitar, 19 redistribuir, 2 reespaciar, 11 mantener; 557 → 546 pilotes. |
| 16 ensayo en copia | **[H]** | `trial_pile_changes`: copia `_ensayo-mcp.FDB`, 12 `FrameObj.Delete` verificados por relectura, 1 `AddByCoord` (frame nuevo con la sección y las Z del de referencia, restricción de punta copiada; `GetSpring` devolvió ret=1 = sin resorte), `run_analysis` 20 s, verificación y comparación en 30 s totales. Original con la misma fecha y tamaño antes y después. Un cabezal pasó de NO CUMPLE a OK al añadir el tercer pilote y otro recuperó factor al borrar la pareja con S/B < 3; el crítico bajó un 21 %. |

Tiempos: 0.2 s el barrido global, 0.6 s por cabezal (una llamada `GetAllFrames` + 240 `GetProperty`/`GetSlab` cacheados por sección), 1.5-1.7 s las reacciones de 564 pilotes, 3.2 s el libro completo, 30 s el ensayo en copia.

## Segundo modelo — ~1100 pilotes, corrida de aceptación antes del PR (2026-11-02, tarde)

Sobre una **copia** del segundo modelo de pilotes de la firma (1123 frames, 1112 pilotes de una
sección circular Ø600 en malla a 2.4 m, 174 cabezales), en una instancia de SAFE arrancada por
COM (`auto_start`), porque la ventana de SAFE abierta por el usuario no estaba registrada en COM
(segunda instancia). Código del commit `1d36851`, sin cambios.

| Paso | Estado | Evidencia |
|---|---|---|
| arranque | **[H]** con salvedad | `SAFEv1.Helper.CreateObjectProgID` + `ApplicationStart` + `open_model(copia)` funcionan. El **primer** `run_analysis` tras arrancar la instancia dejó el solver completo (LOG "ANALYSIS COMPLETE") pero SAFE reportó los casos "no corrido" y la llamada COM no regresó; matado el proceso cliente y relanzado, el análisis terminó en 74 s y quedó "listo". Pendiente de reproducir. |
| 1 separación | **[H]** | 1.1 s el barrido global, 29.5 s por cabezal (174 áreas). Mediana S/B 4.0, mínimo 2.33, 114 pilotes con S/B < 3 en barrido global: **coincide exactamente** con el conteo independiente hecho ese mismo día con otro script sobre el `.$sf`. Promedio step_down 0.793 frente a 0.78 del conteo manual (misma explicación que en el primer modelo). Dos pilotes caen en dos cabezales solapados: avisado y asignado al primero. |
| 2 reacciones | **[H]** | 88 s por `joint` y 88 s por `frame` (1112 llamadas a `JointReact`/`FrameForce`); mismo crítico y misma cifra por las dos vías. |
| 3-4 libro y propuesta | **[H]** | 126-128 s cada uno (incluyen las dos lecturas). 22 combos de servicio clasificadas por definición; 163 pilotes sobre q_adm·ξ; 16 sin factor; 266 candidatos (250 baja demanda, 16 geometría). Propuesta: 6 añadir, 109 quitar, 9 redistribuir, 4 reespaciar, 46 mantener. |
| 5 ensayo | **[H]** | `trial_pile_changes` sobre copia de la copia: 1 `FrameObj.Delete` (candidato de baja demanda) y 1 `AddByCoord` en un cabezal a reforzar (restricción de punta copiada del de referencia), `run_analysis` y dos verificaciones completas: 456 s en total con 1112 pilotes. Antes/después: 163 → 161 pilotes sobre q_adm·ξ, crítico sin cambio (otro cabezal), 2 cabezales mejoran y 1 empeora. Archivo base de la copia con la misma fecha y tamaño; el original del proyecto con su fecha de marzo. |

Límite encontrado: con ~1100 pilotes, `export_pile_check_xlsx` y `suggest_pile_changes` tardan
más de 2 min por las 1112 llamadas individuales a `Results.JointReact`; el cliente MCP puede
cortar por timeout antes (E-035) aunque el servidor termine. Mitigación anotada en BACKLOG:
leer las reacciones de todas las puntas con una sola llamada (grupo o `SelectionElm`).
**Matiz (tercer modelo, 2026-11-03):** el tiempo depende sobre todo de cuántas combos hay
seleccionadas para salida, no solo del número de pilotes: con `service_combos=["Comb2"]` y
`seismic_combos=["Envelope"]` (dos combos) el libro completo de 897 pilotes tardó **6 s**.
Para modelos grandes conviene indicar las combos explícitas.

## Tercer modelo — criterio doble Comb2 / Envelope (2026-11-03)

Pedido del usuario: la combinación de gravedad se compara con la admisible tal cual y la
envolvente sísmica con 4/3 de la admisible. Implementado como `seismic_combos` +
`seismic_factor` (4/3) en libro, propuesta y ensayo (276 tests). Corrida sobre una **copia** de
un tercer modelo (935 frames, 897 pilotes Ø600, 158 cabezales) en instancia SAFE arrancada por
COM; la ventana del usuario con el original no estaba registrada en COM.

| Paso | Estado | Evidencia |
|---|---|---|
| arranque | **[H]** con la misma salvedad | De nuevo el primer `run_analysis` tras `ApplicationStart` no devolvió la llamada aunque el solver terminó (LOG); al matar el cliente y reconectar, SAFE ya reportaba "todos los casos listos" (ayer no). Reproducido dos veces: queda como comportamiento conocido en BACKLOG. |
| criterio doble | **[H]** | `Comb2` (D+L+LT) contra q_adm·ξ y `Envelope` (envolvente de las combos sísmicas de servicio, miembros tipo combo) contra 4/3·q_adm·ξ. 136 pilotes no cumplen (86 por gravedad, 134 por sismo, la mayoría por los dos); 16 sin factor; 138 con tracción; 19 cabezales sobre (a). Crítico con ratio 2.4 en Comb2. 6 s en total. |
| lectura selectiva | **[H]** | `Envelope` se clasifica como envolvente (no se leería sola) y se lee solo porque va en `seismic_combos`; las DCon quedan fuera. Unidades restauradas; original del proyecto intacto. |
| aplicar propuesta en bloque | **[H]**, resultado negativo | `apply_pile_proposal` sobre copia del tercer modelo (Comb2 / Envelope×4/3, cabezales Z50): 59 s; quitó 275 pilotes en 132 cabezales (los candidatos de baja demanda) y no pudo añadir ninguno de los 91 pedidos a 5 D (hueco disponible 2.6 D en 16 cabezales de 4 pilotes, 3.1 D en uno, 4.8 D en dos). Tras reanalizar: pilotes que no cumplen 136 → 246, 132 cabezales empeoran aunque ninguno supere la suma (a). Conclusión: la quita por suma no vale; la carga se redistribuye a los pilotes de borde. La copia resultante se descarta como propuesta. |
| grupos por cabezal | **[H]** | `assign_pile_groups(cap_types="Z50", save=True)` sobre la copia: 158 grupos `CAB-<área>` (áreas con sección Z50) con sus 897 pilotes, cada uno releído con `GroupDef.GetAssignments` (área + frames); `GroupDef.GetNameList` pasa de 1 a 159; 15 s; `File.Save` sobre la copia. Tres pilotes bajo dos cabezales solapados quedan en el primero (avisado). Libro reexportado con hoja Grupos en 7 s. |
