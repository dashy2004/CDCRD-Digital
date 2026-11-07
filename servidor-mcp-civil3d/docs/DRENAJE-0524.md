# Drenaje de corredores: cunetas, imbornales y red de gravedad — 0.5.24

Tres operaciones sobre un corredor con bordillo-cuneta (código `Flowline_Gutter` de la paleta métrica): leer las líneas de cuneta y proponer imbornales con su caudal por el método racional; crear una red de tuberías de gravedad (`PipeNetwork`) con el catálogo métrico instalado, estructuras en imbornales y pozos, tuberías dimensionadas por Manning con pendiente y profundidad mínimas; y releer la red contra el contrato guardado. Más un catálogo de listas de partes para elegir familias y diámetros. Módulo opcional `Cdcrd.Drenaje.V1` **0.1.0**, comando `CDCRDDRENAJEV1`, instalado con `instalar-drenaje.ps1`; no inicia ni reinicia Civil 3D. [fable], 2026-11-06.

El reparto de trabajo es distinto al de los módulos anteriores: el cálculo hidráulico (caudales racionales, espaciamiento de imbornales, dimensionado por Manning) corre en Python (`src/drenaje_calculo.py`, sin CAD, con pruebas unitarias), y el módulo nativo solo lee las feature lines y el catálogo, crea exactamente la red que se le pasa y la verifica contra su contrato. Así cada cifra del diseño es reproducible sin Civil 3D y la escritura nativa no toma decisiones.

## Uso

```python
listar_catalogo_drenaje(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, lista_partes="")
proponer_imbornales_corredor(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, corredor=HANDLE_O_NOMBRE,
    intensidad_mm_h=120, espaciamiento_max_m=60, ancho_aporte_m=8, coeficiente_c=0.9, codigo="Flowline_Gutter", lados="ambos")
crear_red_drenaje(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, nombre="RED PLUVIAL",
    nodos='[{"id":"I1","tipo":"imbornal","xyz":[x,y,z],"q_m3_s":0.021,"hacia":"P1"}, {"id":"P1","tipo":"pozo","xyz":[x,y,z],"hacia":"S"}, {"id":"S","tipo":"salida","xyz":[x,y,z]}]',
    familia_tuberia="Concrete Pipe", familia_imbornal="...", familia_pozo="...", diametros_mm="[300, 375, 450, 525, 600]",
    pendiente_min=0.005, profundidad_min_m=1.0, capa="CDCRD-DRENAJE", simular=True, confirmar=True)
verificar_red_drenaje(dibujo=r"C:\QA\copia.dwg", pid=PID_VERIFICADO, red="RED PLUVIAL")
```

Transporte igual al de los módulos de targets y tipologías: solicitud inmutable con SHA-256, PID y documento exactos, vencimiento de 3 minutos, archivo `.started` y recibo ligado a la solicitud. Ante timeout se consulta el recibo y la cola; **no se reenvía**. Toda escritura exige `confirmar=True` y simula por defecto (`simular=True` crea y aborta la transacción).

## Contrato

**Catálogo** (lectura). Por cada lista de partes del dibujo (o la indicada): familias de tubería con nombre, material y diámetro interior de cada tamaño; familias de estructura con tipo (`StructInletOutlet`, `StructJunction`…), dimensiones interiores y altura rasante-fondo. Los valores del catálogo llevan sus propias unidades (el catálogo métrico guarda milímetros) y se devuelven **en metros**; una unidad desconocida es error, no una conversión a ciegas. También lista las redes existentes con conteo de piezas y si tienen contrato propio.

**Cuencas** (lectura). `proponer_imbornales_corredor` pide al módulo las feature lines de la baseline principal con el código dado (`Flowline_Gutter` por defecto): una línea por lado y por tramo continuo de bordillo (los tramos de unión sin bordillo cortan la línea), con estación, desplazamiento y XYZ de cada punto; el lado sale del signo del desplazamiento y una línea que cruce el eje es error. Exige corredor reconstruido y no cambia nada. Sobre cada línea, en Python:

1. Crestas y puntos bajos de la rasante de cuneta por los cambios de signo de la pendiente; las mesetas (diferencias bajo 1 mm) cuentan una vez, por su punto medio; una línea que solo baja tiene la cresta al inicio y el punto bajo al final; una línea plana se marca `plano` y se trata como si bajara hacia su final.
2. Un imbornal en cada punto bajo, obligatorio. Cada tramo monótono cresta→punto bajo de longitud L se divide en n = ⌈L / `espaciamiento_max_m`⌉ partes iguales desde la cresta; los imbornales intermedios van en los cortes y el último es el punto bajo. Así ningún tramo de cuneta supera el espaciamiento (60 m por defecto; con 60–80 m del enunciado se pasa el valor que corresponda).
3. Aporte de cada imbornal: la longitud de cuneta que drena hacia él (desde el imbornal o cresta aguas arriba); el del punto bajo recibe de los dos lados. Área = longitud × `ancho_aporte_m`; **Q = C · i · A / 3,6·10⁶** en m³/s, con i en mm/h y C = 0,90 por defecto. La intensidad es un dato de entrada (de la curva IDF del proyecto para el período de retorno elegido); el módulo no modela tiempo de concentración ni capacidad de captación de la reja.

Devuelve, por línea: longitud, crestas, puntos bajos e imbornales (`id`, estación, XYZ sobre la cuneta, tipo `punto_bajo`/`intermedio`, aportes con estaciones, longitud, área y caudal) y el espaciamiento real máximo; y un resumen con caudal total. Los XYZ y caudales son los `nodos` de la red.

**Red** (escritura). `nodos` es un árbol: imbornales (con `q_m3_s` de la propuesta), pozos en los cambios de alineación y exactamente una `salida` (la estructura de retención); cada nodo salvo la salida indica `hacia`. Se rechazan ciclos, nodos que no llegan a la salida, dos salidas o tramos menores de 0,5 m. Diseño aguas arriba → abajo (post-orden desde la salida):

- Caudal del tramo = caudal propio del nodo + caudales de los tramos entrantes.
- Radier de salida del nodo = mín(rasante − `profundidad_min_m` − D, radieres de llegada de los tramos entrantes): nunca se sube el agua en un pozo.
- Radier de llegada = mín(radier de salida − L · `pendiente_min`, rasante aguas abajo − `profundidad_min_m` − D): la pendiente nunca baja del mínimo (0,5 % por defecto) y sube si la rasante de llegada lo exige.
- Diámetro = el menor de `diametros_mm` (300–600 mm por defecto), nunca menor que un tramo entrante, cuya capacidad a sección llena por Manning (n = 0,013) a esa pendiente cubre el caudal; si ninguno alcanza, error con el caudal.
- Fondo de cada estructura = radier más bajo conectado − `sumidero_m`. `profundidad_min_m` es la profundidad mínima sobre la **clave** (1,0 m por defecto). Se informa velocidad a sección llena y se advierte fuera de 0,6–5 m/s.

El módulo nativo recibe estructuras (id, tipo, familia, tamaño opcional, XYZ, rasante, cota de fondo) y tuberías (desde, hasta, familia, diámetro interior, radier inicial y final) y, bajo bloqueo del documento y en una transacción: resuelve lista de partes, familias (nombre exacto o fragmento único; una ambigüedad es error con las familias disponibles) y tamaños (estructuras: el nombre dado o el primero; tuberías: el único tamaño cuyo diámetro interior del catálogo coincide con el pedido a ±0,5 mm) **antes de crear nada**; crea la red (`Network.Create`) con esa lista de partes y la capa propia (se crea si no existe); añade cada estructura en su XYZ y fija rasante y fondo por cota (`ControlSumpBy = ByElevation`); añade cada tubería como segmento recto entre centros (radier + D/2) con el tamaño del catálogo; conecta inicio y fin a sus estructuras; verifica (abajo) y guarda el contrato `CDCRD_DRENAJE_V1` (parámetros, estructuras y tuberías con handle, familia, tamaño y cotas) en el diccionario de extensión de la red. No aplica reglas de Civil, no calcula líneas de energía ni etiqueta.

**Verificar** (lectura). Relee el contrato de la red y cada pieza por handle: pertenencia a la red, posición XY (tolerancia 5 mm), rasante y fondo de estructuras, conexiones por estructura, familia y tamaño, capa; de cada tubería radier inicial/final (centro − D/2), diámetro interior (±1 mm), conectividad inicio/fin, extremos sobre las estructuras, pendiente ≥ mínima, profundidad sobre clave ≥ mínima en ambos extremos, fondo de estructura no sobre el radier. Devuelve máximos de error, pendiente y profundidad mínimas reales, detalle por pieza y lista de fallos; cualquier fallo es error. La misma verificación corre dentro de `crear` antes de guardar el contrato.

## Resultados en una copia privada

Pendiente de la prueba nativa (ver abajo).

## Límites

- Solo feature lines de la baseline principal con un código; los tramos sin bordillo cortan la línea y se tratan como cunetas independientes, sin trasvase entre ellas ni hacia las intersecciones.
- Imbornales sobre la línea de cuneta; no se ofrecen a la calzada, no se calcula captación de reja ni caudal de paso (by-pass), ni tiempo de concentración: la intensidad entra como dato.
- Red en árbol con una salida; tuberías rectas, sección llena por Manning, sin perfil hidráulico, sin reglas de Civil, sin sumideros/caídas calculados más allá de `sumidero_m`; sin etiquetas ni vistas de perfil.
- Familias y tamaños son los de la lista de partes del dibujo; el módulo no importa familias del catálogo. `listar_catalogo_drenaje` muestra lo disponible.
- No edita redes existentes ni reemplaza un contrato ya guardado.
- `CDCRDDRENAJEV1` se declara por atributo (carga por demanda del bundle). Una compilación `-p:AssemblyName=Cdcrd.Drenaje.V1b` registra además el alias `CDCRDDRENAJEV1B` para ensayar junto a la compilación ya cargada (igual el arnés `Cdcrd.DrenajeV1Qa` → `CDCRDDRENAJEV1QA` + sufijo); `humo_drenaje.py --comando/--modulo-dll` eligen cuál usar.

## Reproducción

Copia desechable con nombre que empiece por `CDCRD_QA_DRENAJE`, abierta como documento activo en la instancia existente, con el puente cargado. Compilar el módulo (`instalar-drenaje.ps1 -SoloCompilar`) y el arnés opcional `pruebas/native_drenaje_qa` (no se instala con producción).

```powershell
py pruebas/humo_drenaje.py --drawing <copia> --pid <PID> --etapa cargar
py pruebas/humo_drenaje.py --drawing <copia> --pid <PID> --etapa catalogo
py pruebas/humo_drenaje.py --drawing <copia> --pid <PID> --etapa cuencas --corredor <handle> --intensidad 120 --espaciamiento 60 --ancho 8
py pruebas/humo_drenaje.py --drawing <copia> --pid <PID> --etapa red --nodos nodos.json --familia-imbornal <familia> --familia-pozo <familia>
py pruebas/persistencia_drenaje.py --drawing <copia> --pid <PID> --nodos nodos.json --familia-imbornal <familia> --familia-pozo <familia>
py pruebas/humo_drenaje.py --drawing <copia> --pid <PID> --etapa verificar --red "CDCRD QA DRENAJE"
```

Los scripts rechazan recibos existentes y nunca reenvían una escritura.
