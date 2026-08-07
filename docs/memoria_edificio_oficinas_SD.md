# Memoria de cálculo — Edificio de oficinas, 3 niveles, Santo Domingo

Modelo ETABS: `modelos\edificio_oficinas_SD.EDB`
Código: CDCRD versión 2026-07, Tomo 1
Fecha: 2026-08-06
Unidades: kN, m, C

---

## 0. Estado de ejecución

| # | Etapa | Estado |
|---|---|---|
| 1 | Conexión y unidades | Ejecutado |
| 2 | Geometría (puntos, frames, áreas) | Ejecutado |
| 2b | `set_stories` (Nivel 1/2/3) | **Bloqueado** — herramienta no expuesta |
| 3 | Materiales, secciones, apoyos | **Bloqueado** |
| 4 | Diafragmas rígidos | **Bloqueado** |
| 5 | Patrones y cargas en áreas | **Bloqueado** |
| 6 | Espectro CDCRD y casos Ex/Ey | **Bloqueado** (parámetros calculados abajo) |
| 7 | Combinaciones LRFD | **Bloqueado** (combinaciones definidas abajo) |
| 8 | Análisis y derivas | **Bloqueado** (límite normativo definido abajo) |
| 9 | Reacciones y equilibrio | **Bloqueado** (verificación analítica abajo) |

**Causa del bloqueo:** el proceso MCP `fea` en ejecución expone únicamente 10 herramientas
(`get_model_info`, `get_units`, `set_units`, `save_model`, `refresh_view`,
`create_objects_by_coordinates`, `get_all_geometries`, `get_points`, `get_frames`, `get_areas`).
`servidor-mcp/src/server.py` registra ~40, y `Etabs.py` define los 53 métodos correspondientes,
incluidos `set_stories`, `assign_sections`, `set_rigid_diaphragm`, `assign_area_uniform_load`,
`define_cdcrd_spectrum`, `add_response_spectrum_case`, `add_load_combo`, `run_analysis`,
`get_story_drifts`, `get_joint_reactions` y `describe_oapi`.
El `.pyc` de `server.py` está compilado (23:40:01) contra el fuente actualizado (23:39:52),
de modo que el código es correcto: el cliente MCP de esta sesión negoció la lista de
herramientas contra una instancia previa del servidor. **Requiere reconectar/reiniciar el
servidor MCP `fea` para que la lista completa quede disponible.** No es un error de firma,
por lo que `describe_oapi` tampoco es aplicable (también está fuera de la lista expuesta).

---

## 1. Geometría construida

Malla ortogonal 2x2 crujías de 6.00 m, 3 niveles de 3.00 m.

- Rejilla X: 0, 6, 12 m — Rejilla Y: 0, 6, 12 m — Cotas Z: 0, 3, 6, 9 m
- Puntos: 36 (9 por cota x 4 cotas) — verificado con `get_points`
- Frames: 63 = 27 columnas (9 ejes x 3 tramos) + 36 vigas (12 por nivel x 3 niveles)
- Áreas: 12 losas (4 paños x 3 niveles), paño de 6x6 m
- Área en planta: 144 m² por nivel; área total: 432 m²

---

## 2. Parámetros sísmicos

Datos de entrada: Ss = 0.62 g, S1 = 0.25 g, clase de sitio C.

### 2.1 Factores de sitio — cláusula 2.9.2, Tablas 7 y 8, Tomo 1 p. 44

Interpolación lineal admitida por nota (a) de la misma cláusula.

| Parámetro | Interpolación | Valor |
|---|---|---|
| Fa | entre Ss=0.60 (1.20) y Ss=0.70 (1.10), clase C | **1.180** |
| Fv | entre S1=0.20 (1.60) y S1=0.30 (1.50), clase C | **1.550** |

### 2.2 Aceleraciones espectrales — cláusula 2.9.4, Ecuaciones 7 y 8, Tomo 1 p. 45-47

Emplazamiento normal (no campo cercano; el proyecto no está a ≤ 5 km de las fallas de la Figura 6 —
verificar contra el mapa antes de cerrar la memoria).

| Parámetro | Expresión | Valor (g) |
|---|---|---|
| SMS | Fa · Ss = 1.180 × 0.62 | 0.7316 |
| SM1 | Fv · S1 = 1.550 × 0.25 | 0.3875 |
| SDS | (2/3) · SMS — Ec. 7 | **0.4877** |
| SD1 | (2/3) · SM1 — Ec. 8 | **0.2583** |
| T0 | 0.2 · SD1/SDS | 0.1059 s |
| Ts | SD1/SDS | 0.5297 s |

### 2.3 Categoría de Diseño Sísmico — cláusula 2.9.5, Tablas 9 y 10, Tomo 1 p. 49-51

Categoría de riesgo II (edificio de oficinas ordinario).

- Por SDS = 0.4877 (0.33 ≤ SDS < 0.50) → CDS **C**
- Por SD1 = 0.2583 (SD1 ≥ 0.20) → CDS **D**
- Regla: se asigna la más severa, independiente del período → **CDS D**
- Excepción 2.9.5.1 no aplica (S1 = 0.25 < 0.75)

### 2.4 Espectro de diseño — cláusula 2.9.4.4, Figura 7, Tomo 1 p. 50

Forma normal (arranca en 0.4·SDS en T = 0):

- 0 ≤ T ≤ T0: Sa = SDS · (0.4 + 0.6·T/T0)
- T0 < T ≤ Ts: Sa = SDS
- T > Ts: Sa = SD1 / T

| T (s) | Sa (g) |
|---|---|
| 0.000 | 0.1951 |
| 0.050 | 0.3332 |
| 0.106 (T0) | 0.4877 |
| 0.300 | 0.4877 |
| 0.530 (Ts) | 0.4877 |
| 0.800 | 0.3229 |
| 1.000 | 0.2583 |
| 2.000 | 0.1292 |
| 4.000 | 0.0646 |

Casos Ex y Ey: espectro de respuesta con factor de escala 9.80665 (conversión de g a m/s²),
dirección U1 y U2 respectivamente.

---

## 3. Cargas

### 3.1 Carga muerta (D)

- Peso propio de la estructura: factor 1.0 (autopeso ETABS)
- Sobrecarga muerta superpuesta: 2.50 kN/m² en las 12 losas

Peso propio calculado con γ_hormigón = 24 kN/m³:

| Componente | Volumen | Peso |
|---|---|---|
| Columnas C50x50 (27 x 3.00 m) | 20.25 m³ | 486.0 kN |
| Vigas V30x50 (36 x 6.00 m) | 32.40 m³ | 777.6 kN |
| Sobrecarga muerta (2.5 x 144 x 3) | — | 1080.0 kN |
| Losas | según espesor | ver tabla §5 |

### 3.2 Carga viva (L) — cláusula 2.7.2, Tabla 4, Tomo 1 p. 34-36

- Niveles 1 y 2, grupo "Edificios para oficinas", uso "Oficinas": **Lo = 2.40 kN/m²**
  (concentrada 8.9 kN, no gobierna en losa de 6x6 m)
- Total L aplicado: 2.40 × 144 × 2 = **691.2 kN**

### 3.3 Carga viva de techo (Lr) — cláusula 2.7.2, Tabla 4, Tomo 1 p. 34-36

- Nivel 3, grupo "Techos", uso "Techos planos, inclinados y curvos": **Lr = 0.96 kN/m²**
- Total Lr aplicado: 0.96 × 144 = **138.2 kN**

---

## 4. Combinaciones LRFD — cláusula 2.4.2.1, Tomo 1 p. 28-29

Aplicables al caso (sin viento W, sin fluidos F, sin lluvia R, sin empuje de terreno H):

| # | Combinación | Origen |
|---|---|---|
| C1 | 1.4 D | 2.4.2.1.1 |
| C2 | 1.2 D + 1.6 L + 0.5 Lr | 2.4.2.1.2 |
| C3 | 1.2 D + 1.6 Lr + 1.0 L | 2.4.2.1.3 |
| C4 | 1.2 D + 1.0 L + Eh + Ev | 2.4.2.1 con sismo |
| C5 | 0.9 D + Eh − Ev | 2.4.2.1 con sismo |

Con Ev = 0.2 · SDS · D = 0.0975 D, las combinaciones sísmicas quedan:

- C4: **1.2975 D + 1.0 L + Eh**
- C5: **0.8025 D + Eh**

Eh se instancia como Ex y Ey por separado, con los efectos de torsión accidental
y la regla de combinación direccional 100/30 que correspondan.

> **Nota de verificación pendiente:** el coeficiente Ev = 0.2·SDS·D es la formulación
> convencional ASCE 7. `combinaciones.json` lista Ev como símbolo pero no define su
> expresión. Confirmar la cláusula del CDCRD que define Ev antes de fijar el valor
> en la memoria.

Las combinaciones con sobrerresistencia (EΩh) aplican a elementos que requieren
diseño por capacidad; no se instancian en este modelo global.

---

## 5. Verificación de equilibrio prevista (paso 9)

Reacción vertical total en la base bajo 1.2D + 1.6L, según espesor de losa
(el espesor no fue especificado en el encargo):

| Espesor losa | W_losa | D total | ΣFz = 1.2D + 1.6L |
|---|---|---|---|
| 0.12 m | 1244.2 kN | 3587.8 kN | **5411.2 kN** |
| 0.15 m | 1555.2 kN | 3898.8 kN | **5784.5 kN** |
| 0.20 m | 2073.6 kN | 4417.2 kN | **6406.6 kN** |

El equilibrio se verifica cuando la suma de `get_joint_reactions` sobre los 9 nudos
de base (Z = 0) iguala el valor de la tabla dentro de una tolerancia del 0.1 %.
Discrepancias mayores indican masa no asignada, losas sin espesor estructural,
o cargas no aplicadas a alguna área.

---

## 6. Límite de deriva — cláusula 2.10.11, Tabla 19, Tomo 1 p. 95-96

Clasificación: "Estructuras ≤ 4 niveles, sin muros de mampostería u hormigón,
divisiones que acomodan desplazamientos", categoría de riesgo II.

| Concepto | Valor |
|---|---|
| Δa (Tabla 19) | 0.020 · hpx |
| hpx | 3.00 m |
| **Δa admisible** | **0.060 m = 60.0 mm por piso** |
| Cd / Ie | 4.25 / 1.00 = 4.25 |
| **Deriva elástica máxima admisible** (δe = Δa · Ie / Cd) | **14.12 mm** |

Amplificación: δx = Cd · δxe / Ie. La deriva leída de `get_story_drifts` para Ex y Ey
es elástica y debe multiplicarse por 4.25 antes de comparar contra 60.0 mm.

**Restricción adicional aplicable — nota 2.10.11.1:** la estructura está en CDS D
y es un sistema exclusivamente de pórticos a momento. El límite debe dividirse entre
el factor de redundancia ρ. Con ρ = 1.30:

| Concepto | Valor |
|---|---|
| Δa / ρ | 0.060 / 1.30 = **46.2 mm por piso** |
| Deriva elástica máxima admisible | **10.87 mm** |

ρ = 1.30 es el valor por defecto; verificar si la configuración de 3 líneas resistentes
por dirección permite ρ = 1.00 según el criterio del código.

La nota 2.10.11.2 (límite 0.010·hpx para estructuras con solo dos líneas de resistencia)
**no aplica**: el edificio tiene 3 líneas de pórticos en cada dirección.

**Veredicto de deriva:** pendiente de `run_analysis` + `get_story_drifts`.
Criterio de aceptación fijado: δxe·4.25 ≤ 46.2 mm en los tres niveles, para Ex y Ey.

---

## 7. Fuentes citadas

| Dato | Cláusula | Tabla/Fig./Ec. | Tomo | Página |
|---|---|---|---|---|
| Factores de sitio Fa, Fv | 2.9.2 | Tablas 7, 8 | 1 | 44 |
| SMS, SM1, SDS, SD1 | 2.9.4.1–2.9.4.3 | Ec. 7, 8 | 1 | 45–47 |
| Forma del espectro | 2.9.4.4 | Figura 7 | 1 | 50 |
| Categoría de Diseño Sísmico | 2.9.5 | Tablas 9, 10 | 1 | 49–51 |
| Cargas vivas mínimas | 2.7.2 | Tabla 4 | 1 | 34–36 |
| Combinaciones LRFD | 2.4.2.1.1–2.4.2.1.4 | — | 1 | 28–29 |
| Derivas admisibles | 2.10.11 | Tabla 19 | 1 | 95–96 |

Versión del código extraída: 2026-07. Método de extracción de datos: `vision_fable5`,
fecha 2026-08-06.
