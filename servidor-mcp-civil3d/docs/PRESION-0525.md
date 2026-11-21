# Redes de tuberías a presión: catálogo, red explícita y verificación — 0.5.25

Cuatro operaciones sobre redes de presión de Civil 3D 2027 (`PressurePipeNetwork`, ensamblado `AeccPressurePipesMgd`): leer las listas de partes de presión del dibujo con sus piezas; obtener la cota de una superficie TIN en una lista de puntos; crear una red exactamente como se describe (tuberías rectas entre nodos y una pieza por nodo: codo, te, cruz, tapón, reducción, unión, válvula, hidrante o bomba) con las bocas giradas hacia las tuberías y conectadas; y releer la red contra el contrato guardado. Módulo opcional `Cdcrd.Presion.V1` **0.1.0**, comando `CDCRDPRESIONV1`, instalado con `instalar-presion.ps1`; no inicia ni reinicia Civil 3D. [fable], 2026-11-07.

Mismo reparto que el módulo de drenaje: el trazado (posiciones, profundidades, diámetros) lo decide el llamador en Python; el módulo nativo no calcula hidráulica ni cobertura, solo lee, crea lo que se le pasa y verifica. Transporte idéntico: solicitud inmutable con SHA-256, PID y documento exactos, vencimiento de 3 minutos, archivo `.started` y recibo ligado a la solicitud; toda escritura exige `confirmar=True` y simula por defecto (`simular=True` crea y aborta la transacción).

## Uso

```python
listar_catalogo_presion(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, lista_partes="")
cotas_superficie(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, superficie="TN", puntos="[[x, y], ...]")
crear_red_presion(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, nombre="RED AGUA",
    nodos='[{"id":"N1","tipo":"libre","xyz":[x,y,z]}, {"id":"N2","tipo":"codo","xyz":[x,y,z],"familia":"elbow","diametro_nominal":6,"angulo":90},
            {"id":"N3","tipo":"te","xyz":[x,y,z],"familia":"tee","diametro_nominal":6,"diametro_nominal_2":4}, ...]',
    tuberias='[{"id":"T1","desde":"N1","hasta":"N2","familia":"pipe","diametro_nominal":6}, ...]',
    lista_partes="Standard", superficie="TN", capa="CDCRD-PRESION", simular=True, confirmar=True)
verificar_red_presion(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, red="RED AGUA")
```

## Contrato

**Catálogo** (lectura). Por cada lista de partes de presión del dibujo (`PressurePartList.GetAvailablePartLists`): tuberías, accesorios y aparatos con descripción, tipo (`PressurePipe`, `Elbow`, `Tee`, `Cross`, `Valve`…), GUID de pieza y de familia y las propiedades `DiameterNominal`, `PipeDiameterOutside`, `FittingAngle`, `ConnectionPointCount`, `IdMaterial`, `PressureClass`, `CompatibleStandard`… **en las unidades del catálogo** de la lista (el imperial guarda pulgadas) y tal como las entrega `PressurePartSize.GetProperty`; `DiameterNominal` es un texto (`"6 in x 6 in x 4 in"`) del que se toma el primer número como diámetro del cuerpo y el último como el de la derivación. También lista las redes de presión existentes con conteo de piezas, superficie de referencia y si tienen contrato propio.

**Cotas** (lectura). `FindElevationAtXY` de la superficie TIN indicada en hasta 5 000 puntos; fuera de la superficie devuelve `null` en vez de error.

**Red** (escritura). `nodos` con `id`, `tipo`, `xyz` del eje de la tubería y, salvo en `libre`, `familia` (descripción exacta, GUID o fragmento único de la descripción), `diametro_nominal`, `diametro_nominal_2` (derivación) y `angulo` (codos); `tuberias` con `id`, `desde`, `hasta`, `familia` y `diametro_nominal`. Cada tipo exige su número de tuberías (codo 2, te 3, cruz 4, tapón 1, reducción 2, unión 2, válvula 2, hidrante 1, bomba 2; libre cualquiera ≥ 1); tramos menores de 0,5 m en planta se rechazan. El módulo, bajo bloqueo del documento y en una transacción:

1. Resuelve lista de partes, superficie de referencia y **todas** las piezas antes de crear nada (una ambigüedad o ausencia es error con las piezas disponibles de ese tipo).
2. Crea la red (`PressurePipeNetwork.Create`), le asigna lista de partes, capa (se crea si no existe) y superficie; añade cada tubería como segmento recto entre los ejes de sus nodos (`AddLinePipe`) y cada pieza en su nodo (`AddFitting` / `AddAppurtenance`).
3. En cada nodo con pieza lee las direcciones de sus bocas (`GetConnectionAt`), prueba como giro cada diferencia boca–tubería y elige el que minimiza la suma de errores angulares de la asignación boca→tubería; aplica el giro (`TransformBy` alrededor del nodo, `rotar=True`) y conecta cada boca al extremo correspondiente (`ConnectToPipe`, `conectar=True`). Civil recorta la tubería hasta la boca de la pieza: el extremo queda a medio cuerpo del nodo (0,15 m en un codo de 6 in).
4. Verifica (abajo) y guarda el contrato `CDCRD_PRESION_V1` (parámetros, nodos con handle, pieza, posición y bocas asignadas; tuberías con handle, pieza, extremos reales y diámetros) en el diccionario de extensión de la red.

**Verificar** (lectura). Relee el contrato y cada pieza por handle: pertenencia a la red, conteos, lista de partes; de cada tubería extremos iguales a los registrados (tolerancia 5 mm), pieza (GUID), diámetro nominal, capa y pieza conectada en cada extremo; de cada nodo con pieza posición registrada, desvío respecto del nodo de diseño (≤ `tolerancia_conexion_m`, 1 m), pieza, capa, bocas abiertas y que cada tubería del nodo esté conectada a esa pieza y la pieza la registre; de cada nodo libre que el extremo esté sobre el punto de diseño y sin conectar. Devuelve máximos de desvío, bocas abiertas, longitud 2D y el detalle por pieza; cualquier fallo es error.

## Adenda 0.5.26 — módulo 0.2.0: lectura, trazado con cobertura e inspección

Tres herramientas más: `leer_redes_presion`, `trazar_red_presion` e `inspeccionar_red_presion`. [fable], 2026-11-21.

```python
leer_redes_presion(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, red="")            # resumen; con red="..." el detalle
trazar_red_presion(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, nombre="AGUA POTABLE", superficie="TERRENO",
    familia="pipe-150 mm", diametro_nominal=150, cobertura_m=1.2, cobertura_min_m=1.0, polilinea="71B5",
    lista_partes="Water", simular=True, confirmar=True)
inspeccionar_red_presion(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, red="AGUA POTABLE", cobertura_min_m=1.0, paso_m=5)
```

**Leer** (lectura). De cualquier red de presión, tenga o no contrato. Sin `red`: por red, conteos, tramos (`PipeRuns`), longitud 2D y 3D, cotas mínima y máxima y longitud por pieza de tubería. Con `red`: además cada tubería (descripción y familia, `material` y `norma` leídos de los datos de catálogo de la pieza colocada —`ID_MATERIAL`, `COMPATIBLE_STANDARD`—, diámetro nominal del catálogo, diámetros nominal/interior/exterior y espesor en metros, extremos XYZ, longitudes, pendiente, cobertura mínima y máxima según Civil, pieza conectada en cada extremo, capa) y cada accesorio o aparato (tipo, posición, bocas con estado y objeto conectado). Hasta 2 000 partes en detalle.

**Trazado** (escritura). Ruta en planta por `ruta` (vértices) o `polilinea` (handle de una polilínea ligera o 3D abierta, sin arcos y sin ajuste de curva; de la 3D se toma solo la planta, y la polilínea no se consume: el tramo guarda su propia copia). Tubería de la lista de partes del dibujo, elegida como en la red explícita. Civil crea el tramo (`PipeRuns.createPipeRun`) con el eje a `cobertura_m` bajo la superficie y los codos en los vértices. `cobertura_m` es obligatoria: no hay valor por defecto. Después se inspecciona (abajo) y:

- simulando, se devuelve el resultado con `cumple` y se aborta;
- confirmando, si la red no queda en una sola componente conectada o no alcanza `cobertura_min_m`, es error y no se guarda nada.

El trazado no guarda contrato `CDCRD_PRESION_V1`; se comprueba con la inspección.

**Inspección** (lectura). Sin depender de contrato:

- *Conectividad.* Tuberías y piezas son nodos de un grafo unidos por la pieza de cada extremo de tubería y por cada boca cerrada. Devuelve `componentes_conectados` (1 = toda la red unida), `extremos_abiertos` (extremos de tubería sin pieza) y `bocas_abiertas`.
- *Cobertura.* Cada `paso_m` sobre la cuerda de cada tubería: cota de la superficie menos (eje + diámetro exterior / 2). Usa la superficie indicada o la de referencia de la red. Con `cobertura_min_m` lista las muestras por debajo y `cumple`; una muestra fuera de la superficie no cumple, porque no prueba la cobertura. El mínimo por tubería coincide con `MinimumCover` de Civil (se devuelven los dos).
- *Codos.* `codos_fuera_de_angulo`: codos cuyo ángulo de catálogo difiere más de 2° de la deflexión real entre sus dos tuberías. Civil coloca el codo de catálogo más cercano al quiebre de la ruta; la junta queda forzada. Se informa y no se rechaza: si esa deflexión es admisible es decisión de diseño. Desde el módulo 0.2.1 cada caso sale además como texto en `advertencias` («codo … de catálogo 90 grados colocado en un quiebre de 71,5 grados…»), y el servidor exige esa versión.

### Resultados en un dibujo sintético

Dibujo desechable de la plantilla métrica del producto (lista de partes `Water`: hierro dúctil push-on, tuberías de 150 a 400 mm, codos de 11,25°, 22,5°, 45° y 90°, tes y válvulas de compuerta) con una superficie TIN de 200 × 120 m.

| Caso | Resultado |
|---|---|
| Trazado simulado desde 4 vértices, cobertura 1,2 m | 3 tuberías, 2 codos, 1 componente, 2 extremos abiertos (los del tramo); cobertura por 46 muestras 1,2000 a 1,2874 m, igual a `MinimumCover`; tras abortar no queda red |
| El mismo desde una polilínea existente | resultado idéntico; la polilínea sigue en el dibujo |
| Confirmado con `cobertura_min_m=1.0` | red guardada, 212,6 m |
| Quiebre de 71,5° en la ruta | Civil colocó un codo de 90°: informado en `codos_fuera_de_angulo` (−18,5°) |
| Leer | resumen y detalle con `material: ductile iron`, `norma: AWWA C151` |
| Inspección exigiendo 1,25 m | `cumple: false`, 21 de 25 muestras bajo el mínimo, con su posición |
| Nombre de red repetido; `verificar` sobre una red sin contrato | rechazados con mensaje claro |
| Red explícita (5 tuberías, codo, te, válvula): simular, confirmar, `verificar` e `inspeccionar` | 0 fallos; 1 componente; cobertura mínima 0,83 m |

Offline: 19 pruebas Python del módulo; compilación con 0 errores y 0 advertencias.

### Versión cargada

Cada compilación registra el comando canónico; en una sesión que ya cargó la 0.1.0 la nueva solo entra al reiniciar Civil 3D. Como la 0.1.0 ejecutaría `trazado` sin inspección e ignoraría los campos nuevos, el servidor pregunta primero la versión del módulo cargado (el recibo la trae siempre) y se niega con una anterior a 0.2.0.

## Resultados en una copia privada

Misma instancia de Civil 3D 2027, puente vivo 0.5.20, módulo cargado por `NETLOAD` con alias (`V1b`) tras corregir la lectura de `DiameterNominal` como texto; el código final es el de la compilación canónica (SHA-256 `960cfa60…8118`). Copia desechable de un modelo de proyecto (lista `Standard` del catálogo **imperial**: hierro dúctil push-on AWWA, tuberías de 4 a 36 in, 48 codos, 71 tes, 56 cruces, 7 válvulas de compuerta; sin hidrantes ni tapones). Nombres y coordenadas no se publican.

- Cotas: 9 puntos sobre la superficie de terreno (9 cotas) y sobre una superficie de plataforma que no los cubre (9 `null`), sin error.
- Red de prueba: 5 tuberías (6 y 4 in), codo de 90°, te 6 × 4 y válvula de 6 in; 3 extremos libres. Simulación: posiciones de piezas con desvío 0, extremos de tubería a 0,1524 m del nodo (medio cuerpo de la pieza), 3 bocas abiertas (las libres), **0 fallos**; longitud 119,07 m. Confirmación con el mismo resultado, `verificar` igual, guardado por COM, cierre, reapertura en el mismo proceso y nueva verificación idéntica.
- Tramo experimental con la misma ruta de 3 vértices: 3 tuberías y 2 codos de 90° creados por Civil, cobertura mínima 0,96–1,00 m y máxima 1,07 m sobre el terreno; extremos conectados a los codos.
- Dos redes de proyecto (4 y 15 tuberías, 3 y 10 piezas, 274,6 y 372,8 m) simuladas y confirmadas con 0 fallos sobre el modelo de trabajo.

Offline: 14 pruebas Python del módulo (`tests/test_presion.py`), compilación con 0 errores y 0 advertencias.

## Límites

- Tuberías rectas entre nodos; sin curvas, sin perfil, sin hidráulica, sin cobertura calculada (las cotas del eje vienen en `xyz`; `cotas_superficie` sirve para derivarlas).
- Piezas de la lista de partes del dibujo; el módulo no importa piezas del catálogo (`PressurePartList.AddPart` requiere una `PressurePartSize` del catálogo, cuyo acceso no está expuesto). Un hidrante sin pieza en la lista se modela como derivación con extremo libre.
- La asignación de bocas supone piezas con bocas coplanares en planta; piezas de más bocas que tuberías dejan bocas abiertas (se informan).
- `TransformBy` gira la pieza sobre su nodo; si Civil la recoloca al conectar, la verificación lo detecta por el desvío al nodo de diseño.
- No edita redes existentes ni reemplaza un contrato ya guardado. El `trazado` no deja contrato.
- El `trazado` crea un solo tramo sin derivaciones; el perfil lo fija la cobertura (las cotas de una polilínea 3D no se usan). Rutas con arcos se rechazan.
- La cobertura se muestrea sobre la cuerda: en una tubería curva es aproximada y la inspección lo advierte. `cumple` vale para las muestras tomadas: un punto bajo entre dos muestras no se ve, así que conviene un `paso_m` menor que la longitud de onda del terreno. La inspección admite hasta 200 000 muestras por llamada; una tubería sin diámetro exterior legible no acredita la cobertura mínima.
- `CDCRDPRESIONV1` se declara por atributo (carga por demanda del bundle); una compilación `-p:AssemblyName=Cdcrd.Presion.V1b` registra además `CDCRDPRESIONV1B` para ensayar junto a la ya cargada.

## Reproducción

Copia desechable cuyo nombre empiece por `CDCRD_QA_PRESION`, abierta como documento activo en la instancia existente, con el puente cargado. Compilar el módulo (`instalar-presion.ps1 -SoloCompilar`).

```powershell
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa cargar
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa catalogo
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa cotas --superficie <nombre> --puntos puntos.json
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa red --nodos nodos.json [--confirmar]
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa verificar --red "CDCRD QA PRESION"
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa trazado --ruta ruta.json --superficie <nombre> --familia pipe --diametro 6 --cobertura 1.2 --cobertura-min 1.0 [--confirmar]
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa trazado --polilinea <handle> --superficie <nombre> --familia pipe --diametro 6 --cobertura 1.2
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa leer [--red <nombre>]
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa inspeccionar --red <nombre> --cobertura-min 1.0
```

Los scripts rechazan recibos existentes y nunca reenvían una escritura.
