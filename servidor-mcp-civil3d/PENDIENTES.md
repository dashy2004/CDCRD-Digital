# Pendientes del puente MCP de Civil 3D

## Hecho el 2026-10-14 (v0.3.x, verificado EN VIVO 26/27)

Export sin dialogos y vistas (3.3): exportar_vista (PlotEngine sincrono
PDF/PNG/DWF), listar_papeles, vista_3d, crear_vista_guardada, activar_vista.
Fix v0.3.0: lectura de nombres de estilos (NombreDe); v0.3.1: Coerce pasa
valores ya tipados (Color), objects.read/invoke sin handle abren transaccion,
y rutas resuelven la propiedad legible cuando la visible es solo-escritura
(Name de estilos). Ver docs/VISTAS.md. Prueba de humo: pruebas/humo_creacion.py.

## Hecho el 2026-10-14 (v0.2.0, pendiente de reinicio y prueba en vivo)

Creacion nativa de objetos: perfiles (superficie y elevacion constante),
vistas de perfil con rangos exactos, hatch nativo de vista de perfil
(HatchAreas.Add), estilos (listar/crear/clonar/editar display/purgar),
entidades de dibujo nativas (reemplaza LISP), borrar objetos, orden de
dibujo. leer_ruta con argumentos y claves por nombre; inspeccionar_objeto
con filtro regex. Ver docs/CREACION.md.


Backlog de capacidades. El criterio de prioridad es cuantas veces hizo falta la
capacidad para resolver algo real y si existe una alternativa razonable sin ella.

## Hecho (pendiente de compilar y probar en vivo)

Implementado el 2026-10-10, verificado solo contra stubs con el SDK .NET 10
(0 errores, 0 advertencias). Falta `instalar.ps1`, reiniciar Civil 3D y probar.

- **Rutas a objetos anidados.** `ruta` en `objects.props`, `objects.invoke` y
  `objects.update`, mas `objects.read` nuevo. Sintaxis
  `Analysis.ElevationRanges[2].MaximumElevation`, con metodos sin argumentos
  (`GetGeneralProperties()`) e indices. Resuelve el limite que dejaba
  `SurfaceAnalysis` y `GeneralSurfaceProperties` como `{tipo, texto}`.
- **`Val` con expansion bajo demanda.** Parametro `maxExpand` (0 a 3): 0 mantiene
  el comportamiento anterior, 1-3 expanden propiedad por propiedad.
- **Capas.** `layers.query` y `layers.set`. Motivado por el caso real de
  TERRENO NATURAL: la capa `C-TOPO` apagada hacia invisible la superficie entera y
  el diagnostico costo una sesion de control remoto.
- **Guardado.** `doc.save` por reflexion sobre `Database.SaveAs`, porque hasta
  ahora no habia forma de persistir ningun cambio hecho por el puente.

## P1

- **`vista.captura`.** Render del viewport a PNG. Hoy ver el dibujo obliga a
  control remoto, donde las ventanas no permitidas se enmascaran con un
  rectangulo negro encima del area grafica.
- **`vista.encuadre`.** Centro y ancho por coordenadas. `view.zoom` solo acepta
  handles o la extension completa.
- **Estilos.** Recorrer `CivilDocument.Styles` (SurfaceStyles, AlignmentStyles,
  ProfileStyles, LabelStyles...) devolviendo nombre y handle; asignar estilo por
  nombre; leer y escribir los componentes de display via
  `SurfaceStyle.GetDisplayStyle(viewDirection, component)`. La coleccion `estilos`
  del alias actual devuelve 0 objetos.
- **Superficies.** Analisis (tipo, numero de rangos, correr, leer rangos);
  creacion y definiciones (breaklines, bordes, archivos de puntos, DEM); rebuild
  y snapshot; muestreo (`FindElevationAtXY`, `SampleElevations` sobre un
  alineamiento); volumenes con `TinVolumeSurface`; exportar curvas de nivel a
  polilineas y a LandXML/DEM.
- **Vial.** Estaciones de alineamiento (`StationOffset`, `PointLocation`,
  entidades de geometria con radios y longitudes); leer y crear perfiles desde
  superficie; rebuild de corredor con baselines y regiones; superficies de
  corredor; sample lines y vistas de seccion.

## P2

- **Redes.** Gravedad y presion: partes, invertidas, pendientes, estructuras,
  chequeo de interferencias.
- **Planos y cantidades.** View frame groups y `CreateSheets`; quantity takeoff y
  listas de materiales del corredor; etiquetas y tablas, incluida
  `AddSurfaceLegendTable` para la leyenda de rangos de un analisis.
- **Infraestructura.**
  - `cmd.run` sincrono con captura de resultado via el evento `CommandEnded`. Hoy
    es dispara-y-olvida y hay comandos sin equivalente en la API.
  - Lote de operaciones en una sola transaccion, con undo como unidad.
  - `getvar` / `setvar`, layouts y viewports.
  - Error estructurado cuando un dialogo modal bloquea el hilo, en vez de dejar
    vencer el timeout de 55 s sin explicacion.

## Reglas que ya costaron un ciclo de build

- Cuando un miembro de la API no esta confirmado, leerlo por reflexion en vez de
  compilarlo duro.
- `Autodesk.AutoCAD.Runtime` define su propia `Exception`: hace falta
  `using Exception = System.Exception;` o cualquier `catch (Exception)` es
  ambiguo (CS0104).
- `IsReadOnly` esta en `Document`, no en `Database`.
- Verificacion barata antes de molestar a nadie con un build real: compilar los
  `.cs` contra stubs minimos de la API con el SDK .NET 10. Los stubs tienen que
  incluir `Autodesk.AutoCAD.Runtime.Exception` o el chequeo no detecta el CS0104.

## Despliegue Windows — 2026-10-10 [codex]

Las capacidades de la primera seccion ya compilaron contra las DLL reales de Civil 3D 2027 con .NET 10: 0 errores y 0 advertencias. Python carga las 17 herramientas MCP; sintaxis de server.py y puente_cliente.py verificada. Se conserva el codigo desarrollado por Claude.

Bundle actualizado en ApplicationPlugins, con DLL en Contents/build-d561ae1e011d y manifiesto apuntando a ella. SHA-256: D561AE1E011DAD09D92B22A9138876275C097286F0ECBA52270FD6A0DEEF2B11. Instalacion anterior respaldada fuera del bundle. No se ha reiniciado Civil 3D ni modificado el dibujo.

Pendiente: guardar y cerrar Civil 3D de forma normal, abrirlo de nuevo y verificar objects.read, layers.query y las escrituras sobre un dibujo de prueba. El ping anterior respondio 0.1.0; esa version tambien esta en el codigo nuevo, por lo que no distingue builds. La deteccion geometria.cruces no existe en este build; sigue siendo desarrollo pendiente. El Event Viewer no se ha expuesto por API.

### Verificacion posterior al reinicio — 2026-10-10 [codex]
DLL build-d561ae1e011d confirmado en modulos del proceso AutoCAD. Lecturas reales correctas: objects.read (objeto compuesto y propiedad anidada), objects.props con ruta, objects.invoke con expansion y layers.query. Activacion del DLL comprobada. Guardias Python de confirmar y rechazo -32002 sin token de layers.set/doc.save comprobados. Edicion y guardado reales NO probados; requieren dibujo desechable. Cliente MCP de Claude no inspeccionado; verificacion realizada mediante servidor Python y puente TCP.

## Incremento 2026-10-11 [claude] — ref/out, perfil por progresiva, corpus INAPA

- **`Invocar` con parametros `ref`/`out`** (puente/Handlers.cs). Antes `m.Invoke` descartaba
  los valores de salida, asi que `PointLocation` y `StationOffset` corrian pero no
  devolvian nada. Ahora, si la sobrecarga tiene `Double&`/`Boolean&`, el argumento de
  entrada puede ser `null` y el resultado es `{retorno, salidas:{easting, northing, ...}}`.
  `Val` expande ese diccionario. Lista de lectura ampliada con `^ElevationAt`, `^PointAt`,
  `^DistanceTo`, `^Contains`, `^Offset` (y la misma lista en `src/server.py`, que antes
  no incluia `PointLocation` y pedia confirmar sin motivo).
  Verificado con `pruebas/arnes_invocar/correr.py`: extrae Invocar/Coerce/IsSimple
  tal cual de Handlers.cs, compila con .NET 10 contra fixtures y corre 8 casos
  (ref con null, ref con valor, sobrecarga de 6, ref bool, sin ref, coercion, conteo
  de args, metodo inexistente): 8/8 OK en el contenedor. **Falta** `instalar.ps1`,
  reinicio de Civil 3D y `PointLocation(est, 0, null, null)` en vivo.
- **`src/perfil.py`**: muestreo de cota de superficie por progresiva sobre un
  alineamiento (XY por `GetPointAtDist(est - StartingStation)`, sin `ref`, o por
  `PointLocation` cuando el DLL nuevo este activo) y comparacion contra un perfil
  nativo (`Profile.ElevationAt`). Nucleo puro con 13 pruebas en `tests/test_perfil.py`
  (doble del puente, sin CAD). Validado en vivo a mano (DLL viejo) en Fantino:
  E469/E400/E46C, estacion 0 -> superficie 445.000, perfil 445.000; estacion 10000 ->
  superficie 138.4979, perfil 138.4979 (diferencia 3.6e-11 m). La corrida completa
  (`py src\perfil.py --alineamiento E469 --superficie E400 --perfil E46C --paso 20
  --csv ... --json ...`) la ejecuta Emil en Windows: el puente escucha solo en el
  localhost de Windows y no es alcanzable desde el sandbox.
- **`corpus-inapa/`** (carpeta nueva en la raiz del repo): extraccion por pagina del
  Reglamento Tecnico INAPA DIG-PO-001 v01 (2018-07-04) con pagina impresa leida de cada
  encabezado, estructura vigente (titulo/capitulo/seccion), hash por pagina y fuente;
  busqueda FTS5 con cita completa; `referencia_norma` vs `referencia_hipotesis`
  (`normativa` true/false) y `validar_referencias`. 21 pruebas con paginas sinteticas.
  Corpus real generado: 414 paginas PDF, 413 con numero impreso (desplazamiento
  PDF-impresa = 1 en todas), 417 secciones numeradas detectadas, `revision_humana: false`.

### Build real y ref/out en vivo — 2026-10-11 [claude]
Emil compilo con `instalar.ps1` (0 errores, 0 advertencias) e instalo en `Contents/build-22e027ce32cd`;
tras reiniciar Civil 3D, `ping` devuelve `build cbad60b24d04` (MVID) y la ruta del DLL nuevo, y
`PointLocation(10000, 0, null, null)` sobre E469 devolvio `salidas {easting 389459.0959, northing 2110500}`,
igual que `GetPointAtDist(10000)`. ref/out VALIDADO EN VIVO. `instalar.ps1` ahora instala cada build en
`Contents/build-<hash>` y reescribe el manifiesto, asi se puede instalar con Civil 3D abierto; el DLL
cargado queda bloqueado y se borra en la instalacion siguiente. Pendiente: corrida completa de
`src/perfil.py` (puede usar `--pointlocation`).

### Corrida completa de perfil.py — 2026-10-11 [claude]
`perfil.py --alineamiento E469 --superficie E400 --perfil E46C --paso 20 --pointlocation` en Fantino
(Emil, Windows): 1096 estaciones, 1096 con cota, 0 errores; superficie 445.00 (est 0) a 94.11 (fin),
min 91.04; comparacion contra el perfil nativo EG: max_abs 0.0, rms 0.0, veredicto coincide (el perfil
E46C es muestreo de la misma superficie, asi que la auditoria confirma que el muestreo por API reproduce
lo que Civil 3D dibuja). Salida privada en HIDRAULICA 1/04_CALCULOS/02_TRABAJO/MCP_PERFIL_B/. Dos
defectos corregidos por la corrida: la ultima estacion se redondeaba por encima del fin del eje
(PointNotOnEntity) y `objects.query` recibe `handles`/`props` como listas, no cadenas. Mejoras
pendientes: progreso ya existe (cada 50); usar `SampleElevations` por tramo para reducir 3300 llamadas.
