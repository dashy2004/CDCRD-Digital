# Esquema del archivo de proyecto

Fecha: 2026-08-10. Estado: propuesta.

El archivo de proyecto es el bus del pipeline: lo escribe el extractor, lo
enriquecen las etapas de cálculo, lo leen Dynamo y el generador de
presupuesto. Cada etapa **agrega** campos sin borrar los anteriores, de modo
que el archivo terminado es también la trazabilidad completa del proyecto.

## Estructura de carpetas por proyecto

Extiende la que el SOP ya define (§1: carpeta por cliente con `AA REFERENCIA
MEMORIA`, `Modelos`, `Planos`), agregando lo que el pipeline necesita:

```
<CLIENTE>/
├── 00-ENTRADA/
│   ├── arquitectura.dwg          recibido del cliente
│   └── arquitectura.pdf          si no hay DWG
├── 01-ESQUEMA/
│   ├── <proyecto>-E1.dwg         esquema estructural por entrepiso
│   ├── <proyecto>-E1.dxf         export para el extractor
│   └── validacion-E1.txt         salida del validador de capas
├── 02-PROYECTO/
│   ├── proyecto.json             ← estado canónico
│   ├── entrada.xlsx              ← superficie de entrada humana
│   └── historial/                snapshots por etapa
├── Modelos/
│   ├── Revit/
│   ├── Etabs/
│   │   └── Espectro/
│   ├── Safe/
│   └── Losas/
├── Planos/
└── AA REFERENCIA MEMORIA/
```

## `proyecto.json` — bloques

### `meta`

```json
{
  "proyecto": "Proyecto Ejemplo",
  "cliente": "...",
  "ingeniero": "Ingeniero Ejemplo",
  "codia": "00000",
  "fecha": "2026-08-10",
  "version_codigo": "CDCRD 2026-07",
  "unidades": {"fuerza": "Ton", "longitud": "m"}
}
```

`version_codigo` apunta a la versión del CDCRD digitalizado que se usó. Sin
ese campo, dentro de dos años nadie puede reconstruir bajo qué norma se
calculó.

### `materiales`

```json
{
  "hormigon": [{"nombre": "C210", "fc": 210, "unidad_fc": "kg/cm2"}],
  "acero": [{"nombre": "A615Gr60", "fy": 4200, "unidad_fy": "kg/cm2"}],
  "mamposteria": {"peso_especifico": 1.80, "unidad": "ton/m3"}
}
```

`Ec = 15100·√f'c` (kg/cm²), según el paso 4 del SOP.

### `suelo`

```json
{"sigma_adm": 20.0, "unidad": "ton/m2", "factor_k": 1.2, "k": 24.0}
```

`k = factor_k · sigma_adm`, alimenta directo a `define_soil_spring` del SAFE
MCP.

### `entrepisos[]`

```json
{
  "id": "E1",
  "nombre": "1er nivel",
  "altura_arq": 3.00,
  "altura_est": 3.50,
  "uso_predominante": "residencial",
  "h_muro": 2.50
}
```

Nota del SOP a codificar: la altura del **primer** entrepiso en ETABS es la
arquitectónica más 0.50 m (paso 1 de la sección ETABS). Los cortes
arquitectónicos se hacen a nivel de piso terminado y los estructurales a
nivel de entrepiso (§2.1) — de ahí que sean dos campos y no uno.

### `ejes[]`

```json
{"id": "A", "direccion": "Y", "p1": [0.0, 0.0], "p2": [0.0, 25.0]}
```

Regla del SOP §3.2: en pórticos los ejes coinciden con ejes de vigas; en
mampostería, con el borde de los muros.

### `losas[]`

El bloque más denso. Se llena en tres momentos: el extractor pone la
geometría, el Excel/ingeniero pone el uso, el motor de losas pone el armado.

```json
{
  "id": "L1",
  "entrepiso": "E1",
  "contorno": [[0,0],[5,0],[5,4],[0,4]],
  "lx": 5.00,
  "ly": 4.00,
  "tipo": "maciza",
  "condicion_apoyo": 32,
  "direccion_viguetas": null,

  "espesor": {
    "cond": "2D",
    "k": null,
    "ln": 4.00,
    "beta": 1.25,
    "h_calculado": 0.143,
    "h_usado": 0.15,
    "origen": "ACI 318 9.5.3"
  },

  "aligerada": null,

  "cargas": {
    "uso": "residencial - otras areas",
    "cv": 0.20,
    "coef_phi": 0.15,
    "q_mamp": 0.35,
    "q_muerta": 0.94,
    "q_ultima": 1.45,
    "unidad": "ton/m2",
    "fuente_cv": "CDCRD Tabla A-2"
  },

  "armado": {
    "as_x": {"requerido": 4.500, "disponer": "Ø3/8\" @ 15 cm", "provisto": 4.733},
    "as_y": {"requerido": 4.500, "disponer": "Ø3/8\" @ 15 cm", "provisto": 4.733},
    "unidad": "cm2/m",
    "motor": "motor-fea 0.x",
    "camellado": true
  }
}
```

Campos con reglas del SOP embebidas:

- `condicion_apoyo`: códigos del PROGRAMA-LOSA (10 simplemente apoyada, 21/22
  un extremo continuo, 31/32 ambos continuos, 71/72 voladizo).
- `lx`/`ly` se redondean al 0 o 5 más cercano (§5.2).
- `h_usado` se redondea a 12, 14, 15, 16, 20 o 25 cm (§5.3).
- `tipo` pasa a aligerada si `h_usado > 0.16` (§6).
- `aligerada` se llena solo en ese caso: `{"h_topping": 0.05, "h_bovedilla":
  0.15, "s": 0.15, "b": 0.50}`. Topping sube a 0.10 si la losa es de parqueo.
- `camellado`: `true` en macizas, `false` en aligeradas (SOP, pantalla del
  PROGRAMA-LOSA).
- `fuente_cv` obliga a declarar de dónde salió la carga viva. Es el campo que
  hace visible el déficit del 18% en CV de escaleras detectado en
  `validacion/2026-08-06-excel-plantilla-profesional.md`: si dice "plantilla 2025" en vez
  de "CDCRD Tabla A-2", está heredando un valor que no cumple.

### `columnas[]`, `muros[]`, `vigas[]`, `dinteles[]`

```json
{
  "id": "C1",
  "seccion": {"depth": 0.40, "width": 0.40, "material": "C210"},
  "insercion": [12.5, 8.0],
  "entrepisos": ["E1", "E2", "E3"],
  "modificadores": {"i22": 0.80, "i33": 0.80},
  "armado": {
    "long_3dir": 3, "long_2dir": 3, "barra": "#6",
    "recubrimiento": 0.04,
    "estribos": {"barra": "#3", "sep": 0.10, "n_3dir": 4, "n_2dir": 4}
  },
  "verificacion": {"ratio_pm": 0.87, "ratio_joint": 0.92, "estado": "OK"}
}
```

Reglas del SOP en `armado`: dimensión mayor como `depth`; columnas de pórtico
con Ø3/4"; si el espesor supera 40 cm, 4 barras en la cara larga; no más de 3
barras sueltas en ninguna dirección; estribos siempre a 10 cm. `modificadores`
0.80 en columnas y muros de HA, 0.60 en vigas y muros de mampostería.

### `zapatas[]`

```json
{
  "id": "Z1",
  "columna": "C1",
  "seccion": "Z40",
  "espesor": 0.40,
  "dimensiones": [1.20, 1.20],
  "verificacion": {
    "presion_max": 18.4, "presion_adm": 20.0, "estado": "OK",
    "punzonamiento": 0.87
  }
}
```

Reglas del SOP §3.4: espesor mínimo por longitud de desarrollo ≈ 25·Ø
(Ø3/4" → 40 cm; Ø1" → 50 cm); dimensión en planta ≥ 3× la longitud de la
columna o muro. Verificación: comb. 2 contra σadm y envolvente contra ¾·σadm
(§3.12); punzonamiento > 1 exige engrosar (§3.13).

### `sismo`

```json
{
  "ss": 1.20, "s1": 0.45, "sds": null,
  "espectro": "MOPC",
  "casos": ["Ex", "Ey"],
  "n_modos": 27,
  "verificacion": {
    "masa_participativa": 0.94,
    "t1": 0.31,
    "cortante_din_est_x": 0.9468,
    "cortante_din_est_y": 1.0185,
    "factor_ajuste_x": 1.0155,
    "factor_ajuste_y": 0.9266
  }
}
```

`n_modos` = 3 por entrepiso como valor inicial, se sube hasta alcanzar 90% de
masa participativa (paso 23). `t1` recomendado ≈ 0.10·n. Las aceleraciones se
ingresan multiplicadas por g (paso 6).

### `combinaciones[]`

```json
{"nombre": "Comb3", "tipo": "Linear Add",
 "casos": {"Dead": 1.13, "Live": 1.0, "Qx": 0.714, "Qy": 0.2142},
 "fuente": "R-033 cap. III art. 58"}
```

## `entrada.xlsx` — hojas

Solo lo que un humano decide. Todo lo demás se calcula o se extrae.

| Hoja | Contenido | Escribe |
|---|---|---|
| `Proyecto` | Nombre, cliente, ingeniero, CODIA, fecha | Humano |
| `Materiales` | f'c, fy, peso específico de mampostería | Humano |
| `Suelo` | σadm, factor k | Humano |
| `Entrepisos` | Por entrepiso: altura arq., altura est., uso, h de muro | Humano |
| `Usos-Losas` | Por losa: uso → CV y coef. Øi (validación contra Tabla A-2) | Humano elige uso; CV se autocompleta del CDCRD |
| `Mamposteria` | Por losa: longitudes de muro por espesor (20/15/10 cm) | Humano |
| `Sismo` | Ss, S1, sistema estructural (intermedio/especial) | Humano |

Hojas de reporte (se generan, no se editan): `Espesores`, `Cargas`,
`Armado-Losas`, `Verificaciones`, `Cantidades`.

La diferencia con la plantilla actual es que las columnas calculadas salen del
motor y no de fórmulas en celdas. Ventaja: una sola implementación de cada
fórmula, testeable. Costo: se pierde la posibilidad de ver la fórmula en la
celda, que hoy es parte de cómo el equipo revisa. Vale considerar dejar las
fórmulas visibles en las hojas de reporte aunque el valor venga calculado
aparte, para que la revisión siga siendo posible del modo habitual.

## Validación

`proyecto.json` debe tener un JSON Schema. Sin él, cada etapa descubre a su
manera que un campo falta, normalmente a mitad de una operación que ya modificó
el modelo de Revit o de ETABS. Con esquema, la validación es una llamada al
inicio de cada etapa y el error dice exactamente qué falta.

Pendiente de crear: `esquemas/proyecto.schema.json`.

## Implementación desde Revit (2026-09-06)

`revit-mcp-tools/src/tools/exportar_proyecto.py` escribe este esquema desde el modelo
abierto. Cubre `meta`, `materiales.hormigon` (f'c y E leídos del StructuralAsset, en
kg/cm² y MPa), `entrepisos[]` (agrega `elevacion`), `ejes[]`, `columnas[]` (agrega
`revit_id`, `nivel_base`, `nivel_tope`, `z_base`, `z_tope`, `rotacion_deg`, `seccion.origen`
= `tipo` | `bbox`), `vigas[]` (`p1`/`p2` con z, `longitud`), `losas[]` (`contorno` desde el
sketch, `huecos`, `espesor.h_usado`, `area_m2`), `muros[]` y `zapatas[]` (`columna` = la
columna más baja en el mismo punto). `sismo`, `combinaciones`, `cargas` y `armado` quedan
en `null`/vacío: son decisión humana o salida de las etapas de cálculo.

Bloque nuevo `etabs`: los mismos datos traducidos a los argumentos del servidor `fea`
(`set_stories`, `define_concrete_material` con f'c en kN/m², `define_rect_section`,
`create_objects_by_coordinates` con `ref` y `seccion` por objeto). `assign_sections` de `fea`
asigna una sección por clase; con varios tipos hay que asignar por elemento.

Coordenadas: por defecto el mínimo X,Y de los puntos de inserción pasa a (0,0); la
traslación queda en `meta.traslacion_origen_mm`.

El JSON Schema (`esquemas/proyecto.schema.json`) sigue pendiente.
