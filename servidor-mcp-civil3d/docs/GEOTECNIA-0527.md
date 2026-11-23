# Proyectos del Geotechnical Modeler sin diálogos — 0.5.27

Módulo opcional `Cdcrd.Geotecnia.V1` 0.2.0 (`modulo-geotecnia/`, `src/geotecnia.py`). Hace sin pantalla lo que el panel **Manage Data** del Geotechnical Modeler (GM) de Civil 3D 2027 pide con diálogos: crear un proyecto, importar los CSV de sondeos y vincular el proyecto al dibujo.

El GM no publica una API. El módulo llega a sus servicios por reflexión, a través de su propio contenedor (`Aecc.Gtm.Domain.IoC`): son los mismos objetos que usa el panel. No abre ninguna ventana del GM.

## Uso

```python
gm_iniciar(pid=PID_VERIFICADO, confirmar=True)   # solo si nadie ha abierto el panel del GM en esta sesion
gm_listar_proyectos(pid=PID_VERIFICADO)
gm_crear_proyecto(pid=PID_VERIFICADO, proyecto_id="QA GM", nombre="Proyecto sintetico", confirmar=True)
gm_importar_csv(pid=PID_VERIFICADO, proyecto_id="QA GM", ubicaciones=r"C:\QA\qa_ubicaciones.csv",
                litologia=r"C:\QA\qa_litologia.csv", confirmar=True)
gm_vincular_proyecto(pid=PID_VERIFICADO, proyecto_id="QA GM", confirmar=True)
gm_agregar_sondeos_al_dibujo(pid=PID_VERIFICADO, confirmar=True)
gm_superficie_superior(pid=PID_VERIFICADO, confirmar=True)
gm_sistema_coord(pid=PID_VERIFICADO, codigo="UTM84-19N", confirmar=True)
```

Sin `confirmar=True` las escrituras simulan: validan y dicen qué harían, sin tocar la base ni el dibujo.

## Contrato

- **Listar.** Proyectos de la base del GM con identificador, nombre, ubicación, sistema de coordenadas y número de sondeos y estratos; el proyecto vinculado al dibujo activo (`proyecto_del_dibujo`, `null` si no tiene) y la ruta de la base de datos.
- **Crear.** `AGMBoringRepository.InsertProject`. Se niega si ya existe un proyecto con ese identificador. El identificador admite letras, números, espacios, guion, punto y paréntesis.
- **Importar.** `FieldMapConfiguration.CreateForGeotechnicalModelerCsv` (el mapeo automático de Autodesk para sus propias cabeceras) y `CustomCSVDataImporter.ImportBoreholesFromCustomCsvData`. Exige que el proyecto exista y que el mapeo sea válido. Devuelve sondeos y estratos antes y después y el informe del importador (insertados y actualizados).
- **Vincular.** Escribe el `ProjectId` en los ajustes del GM del dibujo activo (`ApplicationSettingsRepository.SaveApplicationSettings`, grupo `ManageData`) dentro de una transacción del GM, lo relee y falla si no coincide. Sirve para un dibujo sin proyecto y para uno ya vinculado a otro, que en el panel deja el selector deshabilitado. No guarda el dibujo.
- **Agregar sondeos.** `BoreholeManager.InsertAllBoreholes` sobre el dibujo activo, con los sondeos del proyecto que tiene vinculado: los inserta como puntos COGO y crea el grupo «GM - All Boreholes». Antes copia al dibujo los estilos del GM desde su plantilla (`StyleImporter.ImportStylesFromTemplate`, sin reemplazar los que ya existan), como hace el panel la primera vez.
- **Superficie superior.** `BoreholeManager.CreateTopSurfaceFromAllBoreholes` crea «GM - Top Surface», el nombre exacto que el perfil nativo del GM exige. Se niega si ya existe. Sin sondeos en el dibujo el GM la crearía vacía: el módulo cuenta sus puntos dentro de la misma transacción y, con menos de tres, aborta y no deja nada.
- **Sistema de coordenadas.** `CoordinateSystemManager` del GM sobre el dibujo activo: sin `codigo` lee; con `codigo` asigna, relee y falla si no coincide.
- **Respaldo.** Crear e importar copian antes la base de datos junto a ella (`<nombre>_respaldo_<fecha>_<hora>.db`) y devuelven la ruta. El módulo nunca borra un respaldo ni un proyecto.
- **Transporte.** El mismo de los demás módulos: solicitud con huella, recibo inmutable, PID y vencimiento de cinco minutos, en `%LOCALAPPDATA%\CdcrdCivil3dBridge\geotecnia`.

## Resultados en vivo

Sesión de Civil 3D 2027 con el GM ya iniciado, dibujo sintético y CSV sintéticos de tres sondeos y seis estratos:

| Caso | Resultado |
|---|---|
| Listar | proyectos existentes con sus conteos; ruta de la base |
| Crear, simulado | no escribe; `existe: false` |
| Crear, confirmado | proyecto nuevo con 0 sondeos; respaldo creado |
| Crear con identificador repetido | rechazado |
| Importar, simulado | mapeo válido; 3 y 6 filas contadas; nada escrito |
| Importar, confirmado | 3 sondeos y 6 estratos insertados, 0 actualizados; respaldo creado |
| Vincular, simulado | informa `proyecto_antes: null` y el que quedaría |
| Vincular, confirmado | el dibujo queda con el proyecto; releído también con `gm_diagnosticar` del núcleo |
| Vincular a un proyecto inexistente | rechazado |
| Agregar sondeos, simulado | informa 3 sondeos; nada creado |
| Agregar sondeos, confirmado | 3 puntos COGO en las coordenadas del CSV, releídos con `consultar_objetos` |
| Superficie superior sin sondeos en el dibujo | rechazada; no queda superficie |
| Superficie superior, confirmada | creada con 3 puntos |
| Superficie superior repetida | rechazada |
| Sistema de coordenadas: leer, simular, asignar `UTM84-19N` y releer | asignado y releído |
| Sistema de coordenadas con un código inexistente | rechazado |

Offline: 12 pruebas Python (`tests/test_geotecnia.py`), compilación con 0 errores y 0 advertencias.

## Límites

- El GM tiene que haberse iniciado en la sesión: su contenedor se crea la primera vez que corre uno de sus comandos. En una sesión donde nadie ha abierto el GM, el módulo responde que hay que abrir su panel una vez. Iniciarlo sin pantalla queda pendiente.
- Solo importa ubicaciones, litología y orientación en el formato CSV del GM. No importa muestras (SPT), ni AGS ni gINT.
- Agregar sondeos inserta todos los del proyecto; no filtra por tipo ni por fecha. Repetirlo sobre un dibujo que ya los tiene no se probó.
- El sistema de coordenadas se asigna al dibujo, no al proyecto en la base del GM.
- La superficie superior sale de las cotas de boca de los sondeos, no de un levantamiento.
- La base del GM es una por máquina: un proyecto de prueba creado aquí queda en ella. El módulo no borra proyectos.
- Vincular no se probó sobre un dibujo que ya tuviera otro proyecto; el caso probado es el de un dibujo sin proyecto.
- Depende de nombres internos del GM 2027 (`AGMBoringRepository`, `ApplicationSettingsRepository`, `SettingsType.ManageData`). Otra versión del GM puede cambiarlos; el módulo falla con el nombre que no encontró.

## Reproducción

```powershell
.\instalar-geotecnia.ps1 -SoloCompilar
py -m pytest tests/test_geotecnia.py -q
```

## Iniciar el GM sin abrir su panel (0.2.0)

Autodesk registra el Geotechnical Modeler para cargarse con su primer comando: en una sesión recién abierta sus servicios no existen y toda herramienta `gm_*` responde «no está cargado en esta sesión». `gm_iniciar(pid, confirmar=True)` carga el módulo de Autodesk desde su propia instalación (`C3D-GeoTechModeler-*.bundle`, `Aecc.Gtm.AutoCADPlugin.dll`) y comprueba que su contenedor de servicios quedó creado. No ejecuta ningún comando del GM, no abre su panel y no toca el dibujo ni la base de datos.

- Sin `confirmar` informa si hace falta y qué archivo cargaría.
- Si ya estaba iniciado devuelve `ya_iniciado: true` y no hace nada.
- El recibo marca `committed: true` cuando lo inició: lo que cambia es la sesión, no el dibujo.
- Sigue haciendo falta un dibujo abierto, porque el puente despacha comandos a través de un documento.
