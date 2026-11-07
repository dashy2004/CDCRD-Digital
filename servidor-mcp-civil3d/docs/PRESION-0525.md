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

**Tramo** (escritura, experimental). `trazado`: una polilínea de ruta `[[x, y], ...]`, una tubería y una superficie con cobertura; Civil crea el tramo (`PipeRuns.createPipeRun`) con codos automáticos en los vértices y el perfil a la cobertura pedida. Devuelve tuberías y codos creados con sus extremos y coberturas; no guarda contrato ni verifica. Expuesto solo por `presion.ejecutar(accion="trazado")`, no como herramienta MCP.

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
- `CDCRDPRESIONV1` se declara por atributo (carga por demanda del bundle); una compilación `-p:AssemblyName=Cdcrd.Presion.V1b` registra además `CDCRDPRESIONV1B` para ensayar junto a la ya cargada.

## Reproducción

Copia desechable cuyo nombre empiece por `CDCRD_QA_PRESION`, abierta como documento activo en la instancia existente, con el puente cargado. Compilar el módulo (`instalar-presion.ps1 -SoloCompilar`).

```powershell
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa cargar
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa catalogo
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa cotas --superficie <nombre> --puntos puntos.json
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa red --nodos nodos.json [--confirmar]
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa verificar --red "CDCRD QA PRESION"
py pruebas/humo_presion.py --drawing <copia> --pid <PID> --etapa trazado --ruta ruta.json --superficie <nombre> --familia pipe --diametro 6
```

Los scripts rechazan recibos existentes y nunca reenvían una escritura.
