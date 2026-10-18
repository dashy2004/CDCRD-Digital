# Validación nativa ETABS 23.3.0 — 2026-10-17

Se ejecutaron modelos sintéticos en **ETABS 23.3.0 / OAPI 2.016**, por conexión
exclusiva a PID y hora de creación. Hay comprobaciones numéricas, lectura tras
escritura y reapertura. **La validación integral sigue abierta**: diseño de
despiece integral de muros y ejecución de historia no lineal directa tienen los límites indicados
abajo. No se afirma haber probado las 4.861 firmas del catálogo CSI.

## Correcciones y regresiones

- `Etabs(process_id=PID)` / `fea.process_id` / variable `ETABS_PROCESS_ID`:
  conexión a una instancia concreta mediante `GetObjectProcess`. Si falla,
  nunca se conecta a otra instancia del ROT ni inicia otra automáticamente.
- Los importadores `.e2k`/`.$et` y el cambio de niveles por texto requieren PID
  explícito. El vigilante de modales filtra por ese PID; no manipula ventanas de
  otras instancias. Sin PID, el import falla antes de escribir o conectar.
- `run_analysis` exige un archivo guardado y casos seleccionados. Tras la
  llamada revisa que todos los casos seleccionados tengan estado CSI 4
  (Finished). Un retorno 0 con casos incompletos es error, no éxito.
- Fuente de masa por `Mass Source Definition`: ETABSv1 no tiene `SourceMass`.
  Conserva las otras fuentes, fija la predeterminada y relee factores y flags.
- Creación de etiquetas por `PierLabel.SetPier` antes de asignarlas a áreas.
  Una asignación parcial es error, no éxito.
- Borrado de puntos aislados mediante `DeleteSpecialPoint`; rechaza puntos
  conectados y relee su ausencia.
- `JointDispl`: acepta `Obj=null` en nodos internos de la malla conservando
  `Elm`; los demás campos y longitudes siguen bajo contrato estricto.
- Importación de tablas: errores fatales o de importación no se anuncian como
  éxito. El mensaje advierte que puede haber cambios parciales.
- Time-history por tablas reales: creación y relectura de función, dirección,
  escala, paso y cantidad; conserva otros casos y rechaza sobrescribir nombres.
  El caso lineal modal se ejecutó. El directo no lineal solo se creó/releyó.
- P-Delta: no cambia silenciosamente a grandes desplazamientos si falla;
  cargas como arrays; `base_case` legado ya no promete una copia inexistente.
- Diafragma existente: rechaza un tipo rígido/semirrígido distinto antes de
  asignar puntos; no afirma haber cambiado una rigidez que no modificó.
- `close_model`: guarda si se solicita, obtiene unidades, llama
  `InitializeNewModel` y después `NewBlank`. La secuencia anterior cerró
  inesperadamente ETABS en la prueba de acero. La corregida pasó y reabrió el EDB.
- Lectores de muros: `GetPierSummaryResults` terminó el cliente Python incluso
  con diseño disponible. Se sustituyó por `GetTableForDisplayArray`; salida JSON
  con precisión de visualización, null y campos no aplicables conservados.
  Verifica todas las dependencias de combinaciones (incluidas anidadas) y rechaza
  casos no terminados. No convierte ausencia de DCRatio en cero.
  `GetRebar` retornó 0 con cero filas: el lector usa `AreaObj.GetRebarDataPier`
  para obtener capas nativas, identificadas por área, nivel y pier. Valida tipos,
  longitudes, números finitos y cobertura; propaga errores, conserva null y cero.
  Devuelve `rebar_source`, `rebar_status` y `area_rebar` separados del resumen.
  Mantiene `complete_detailing=false`: una capa nativa no prueba que coincida
  con la sección comprobada ni acredita anclajes o un despiece completo.
- `call_oapi(..., returns_status=False)` conserva el valor de getters como
  `GetPresentUnits` sin confundir el enum 6 con un código de error.
- Resultados de concreto: sin tolerancia adicional del 5% ni exenciones de
  juntas por contener el nombre del techo. Los valores no certifican un diseño.

La selección por PID no sustituye un protocolo de propietario único, ni evita
que el usuario cambie manualmente el modelo dentro de esa misma instancia.

## Verificación realizada

- 136 pruebas offline ETABS aprobadas; 10 regresiones del corpus aprobadas
  (**146 total**). No requieren conexión a modelos.
- Compilación Python y `git diff --check` correctos.
- Importación Windows y generación de los esquemas de las 76 herramientas MCP.
- Sesión nueva MCP por stdio contra ETABS: listado de 76 herramientas y llamadas
  reales a `get_model_info`, `call_oapi` (lectura del bloqueo),
  `get_shearwall_design`, `get_shearwall_rebar` y `search_oapi_catalog`.
- Regresiones en rojo/verde para conexión fijada, finalización de análisis y
  orden de cierre. Las discrepancias nativas se conservaron en registros privados.
- Cobertura de sentencias/ramas del módulo `wall_results.py`: **87%**.
  No se atribuye ese porcentaje al servidor completo ni a las 4.861 firmas.
- Ruff y Pyright sin errores en el módulo de contratos de muros; Ruff también
  en las nuevas pruebas de capas. Lint/tipado del servidor completo pendiente.

## Arnés de prueba (opt-in, Windows)

`tools/validate_etabs_live.py` requiere Python con `comtypes`, `mcp` y `pydantic`.
La fase `launch` crea una instancia nueva; exige un directorio de salida nuevo
y registra PID + hora de creación. Las siguientes fases verifican esa identidad
y rechazan archivos abiertos fuera del directorio de prueba. No usa ROT.

```powershell
python tools/validate_etabs_live.py --phase launch --output C:\TEMP\ETABS_TEST_01
python tools/validate_etabs_live.py --phase baseline --output C:\TEMP\ETABS_TEST_01
python tools/validate_etabs_live.py --phase suite --output C:\TEMP\ETABS_TEST_01
python tools/validate_etabs_live.py --phase advanced --output C:\TEMP\ETABS_TEST_01
python tools/validate_etabs_live.py --phase lifecycle --output C:\TEMP\ETABS_TEST_01
python tools/validate_etabs_live.py --phase roundtrip --output C:\TEMP\ETABS_TEST_01
python tools/validate_etabs_live.py --phase walls --output C:\TEMP\ETABS_TEST_01
python tools/validate_etabs_live.py --phase close --output C:\TEMP\ETABS_TEST_01
```

No ejecutar las fases en paralelo. Si ETABS muestra un aviso al arrancar,
resolverlo en la instancia nueva y esperar que termine `launch`; no relanzar.
Un timeout del cliente no cancela una llamada COM.

`relaunch` solo se permite si el PID anterior ya no existe; archiva su identidad
y no borra modelos/logs. `summarize_etabs_live.py` inventaría llamadas, **no**
convierte automáticamente un retorno de texto en una prueba aprobada.

## Evidencia numérica y persistencia

| Ensayo | Resultado comprobado |
|---|---|
| Voladizo 3 m, 0,30 × 0,40 m, E=25.000.000 kN/m²; 100 kN axiales | U3=−0,100000 mm, coincide con FL/EA |
| Mismo voladizo, 10 kN lateral | U1=2,278800 mm; flexión más cortante rectangular, tolerancia relativa 0,2% |
| Reacción axial | 100 kN; desplazamiento cotejado también con tabla nativa |
| Pórtico de dos niveles, 16 frames, 4 áreas (2 losas y 2 muros) | 6/6 casos seleccionados terminados: G, X, modal, espectro, P-Delta, estático no lineal |
| Gravedad aplicada: 96 kN en losas + 40 kN en vigas | Suma Fz=135,999999999999 kN frente a 136 kN |
| Diseño ACI 318-19 | Lectura positiva: 18 estaciones de viga, 3 de columna y 1 nudo |
| Acero AISC 360-16 | Análisis y diseño ejecutados; ratio leído 0,1335024405, sin mensajes de error/advertencia |
| Time-history lineal modal | 5 pasos × 0,02 s completados; envolventes de desplazamientos no nulas |
| Guardado/reapertura | Geometría conservada; resultado axial idéntico |
| Exportación/importación `.$et` + recálculo | 1 frame, 2 puntos, U3=−0,100000 mm |
| Cierre de modelo / aplicación | Modelo vacío, EDB reabierto y proceso cerrado verificadamente |
| Muros ACI 318-19, prueba posterior | Dead/Live ejecutados; 9 estados Finished incluyendo caso interno; 4 estaciones de pier cotejadas contra tabla, guardadas y reabiertas idénticas |

En la primera prueba de dos niveles, Dead/Live no se habían ejecutado y las
combinaciones automáticas de diseño carecían de resultados. Las lecturas
positivas anteriores de concreto no acreditaban cobertura completa de diseño.
El arnés ya selecciona Dead/Live. En la copia de muros se verificaron DWalS1–4:
dependen de Dead, Live y TEST_RS. El usuario ejecutó Start Design/Check en GUI
después del análisis, ya sin aviso de combinaciones omitidas.

Las cuatro filas no tienen mensajes de error/advertencia, pero requieren
0,25–0,49 % frente a 0,21 % actual. Se conserva ese hallazgo, sin aumentar barras
en esa primera copia ni certificar armado. El resumen y las respuestas de ambos
lectores coinciden antes/después de guardar/reabrir; GetRebar sigue sin detalle.
La reapertura, no solo File.Save ret=0, fue la comprobación de persistencia.

### Corrección posterior del armado, autorizada en otra copia sintética

Se asignó refuerzo uniforme con barras de borde y extremo de 16 mm,
separación nominal de 250 mm y recubrimiento de 40 mm; se solicitó modo Check.
Se conservaron geometría, asignaciones de sección, preferencias y combinaciones.
La tabla de overwrites normaliza `DesignCheck=Check` a `Program Determined`:
no se aceptó ese texto como prueba; el nuevo resultado contiene efectivamente
`DCRatio` en las cuatro estaciones, en lugar de los porcentajes de diseño.

| Nivel | Estación | D/C comprobado |
|---|---|---:|
| TEST_L2 | Top | 0,412 |
| TEST_L2 | Bottom | 0,247 |
| TEST_L1 | Top | 0,276 |
| TEST_L1 | Bottom | 0,589 |

Todos quedan por debajo de `DCLimit=0,95`, sin mensajes nativos de error o
advertencia. Nueve casos Finished, resumen, overwrites y capas coinciden antes
de guardar, después de guardar y después de reabrir el EDB. Original SHA-256
intacto. Esta prueba de integración no certifica un proyecto real.

`GetRebar` sigue vacío aun pasando nombres de áreas, seleccionando los muros
y después de que el usuario ejecutara en GUI **Concrete Detailing → Run/Update
Wall Stack Detailing/Check**. `Detailing.StartDetailing(False)` retornó 0, pero
`GetDetailingAvailable` siguió false y `GetNumberDetailedWallStacks` dio cero.
No se usa ese retorno como éxito ni se automatiza ese comando en el lector.

La alternativa `AreaObj.GetRebarDataPier` devolvió dos capas por cada muro:
horizontal 12 mm / 450 mm y vertical 16 mm / 230 mm, ambas por cara según el
enum CSI. Los recubrimientos nativos son 25 y 0 mm; el cero se conserva, no se
interpreta como recubrimiento constructivo aprobado. Estos datos **no son
idénticos a los overwrites de la sección comprobada**; el lector separa ambas
fuentes y deja `matches_checked_section=not_verified`. No transforma capas en
longitudes de corte, ganchos o planos que ETABS no haya proporcionado.

La definición geométrica de una sección rectangular no define su función de
armado: la viga sintética recibió `PropFrame.SetRebarBeam` antes del diseño.
Los valores negativos de acero provisto que devuelve CSI se conservan como
datos crudos; no son un despiece ni aprobación profesional. Los resultados de
texto E2K usan las unidades del archivo (mm en estas pruebas), no necesariamente
las unidades activas de la interfaz (m).

## Puertas pendientes antes de otras aplicaciones

1. **Muros:** resumen por tablas y persistencia comprobados; la API instalada
   no expone `DesignShearWall.StartDesign`, por lo que sigue requiriendo GUI.
   Armado uniforme corregido y D/C comprobados; queda pendiente despiece nativo
   completo y conciliación entre las capas devueltas y la sección comprobada.
   GetPierSummaryResults también queda bloqueado en call_oapi antes de acceder
   al modelo; se dirige al lector seguro por tablas.
2. **Historia no lineal directa:** definición y relectura correctas, pero
   `TEST_TH_NL` queda en estado 1 y ETABS desactiva su bandera. La edición en
   ejecución se identifica como **Nonlinear**, no Ultimate. La documentación
   de CSI asigna integración directa a Ultimate; la licencia es la hipótesis
   principal, no una comprobación del contrato de licencia de esta máquina.
   La reapertura del EDB avanzado devolvió `ret=1` y la sesión dejó de estar
   disponible; no se atribuye todavía una causa definitiva a ese cierre.
   La rama queda bloqueada por defecto: solo permite diagnóstico en copia con
   `experimental_nonlinear=True`. Falta ejecución y reapertura positivas en una
   edición habilitada; no se eluden licencias.
3. Probar matrices más amplias (otras versiones, unidades, geometrías,
   materiales no lineales, parámetros y errores). Una llamada por herramienta
   no acredita todas sus ramas. La prueba end-to-end por stdio cubre las cinco
   herramientas indicadas arriba, no la totalidad del servidor.

No se pasa a SAFE/Revit/Civil 3D/AutoCAD dentro de esta etapa. EDB, resultados,
logs, rutas de usuario y licencia quedan fuera del repositorio público.

Referencias CSI: [NewBlank e inicialización previa](https://docs.csiamerica.com/help-files/etabs-api-2016/html/343e38b3-b137-cadc-26a7-8a97247fe5bd.htm),
[secuencia de análisis y diseño de muros](https://docs.csiamerica.com/help-files/etabs/Getting_Started/Shear_Wall_Design_Procedure.htm),
[niveles del producto, manual histórico](https://docs.csiamerica.com/manuals/etabs/Welcome%20to%20ETABS.pdf).
Las firmas y campos se cotejaron además con ETABSv1 y `Table and Field Keys.xml`
de la instalación real 23.3.0, no se dedujeron solo del catálogo compartido.
