# puente-losas — Revit → motor FEM (EstructurasRD) → Excel / ETABS

Puente de **predimensionado de losas**: lee los paños esquemáticos de un modelo
de Revit, los analiza con el motor FEM abierto de **EstructurasRD** y entrega
un informe Excel por losa más un **plan de export a ETABS** que respeta las
reglas de modelado del flujo AutoCAD ↔ Excel/ETABS de la Ing. Arlette Ramírez.

## Agradecimiento

Este puente replica, para losas en Revit, el patrón del puente
**AutoCAD ↔ Excel/ETABS** preparado por la **Ing. Arlette Ramírez**: su prompt
"Modelar en ETABS desde AutoCAD" (14/10/2026) define la biblioteca de losas,
los Uniform Load Sets, las unidades (tonf·m·°C), la regla Shell-Thick y los
redondeos a múltiplos de 0.05 m que este código aplica. Gracias, Arlette.

## El motor de cálculo

Los resultados numéricos salen de
[EstructurasRD](https://github.com/dashy2004/EstructurasRD)
(autor Emil Guillén De la Cruz, [@dashy2004](https://github.com/dashy2004),
MIT), el reemplazo propio y auditable de `Losas.exe`. Proceso, verificado
leyendo su código:

- `motor-fea/src/motor_fea/core/losa_fem.py` — FEM de placa con elemento ACM
  (rectangular no conforme), 3 GDL por nodo (w, θx, θy), malla (nx+1)×(ny+1),
  carga uniforme *lumped* por área tributaria. Bordes "simple" (apoyada) o
  "empotrado". Devuelve w central, Mx/My/Mxy máximos de vano (centros de
  elemento) y el momento máximo de apoyo en el contorno.
- `motor-fea/src/motor_fea/normativa/aci318.py` — ACI 318-19 en SI (N, mm,
  MPa): As de flexión = (0.85·f'c·b/fy)·(d−√(d²−2Mu/(φ·0.85·f'c·b))) con
  φ = 0.90; As mínimo por retracción/temperatura §24.4.3.2; selección de
  barra y espaciamiento (§8.7.2.2).
- `motor-fea/src/motor_fea/diseno_losa.py` — compone FEM → momentos → acero
  por franja (vano X, vano Y y apoyo). CLI: `motor-fea --disenar-losa params.json`.

Este paquete solo **adapta** la entrada/salida: no calcula nada por su cuenta
ni corrige los números del motor.

## Flujo completo

1. **Revit (sesión viva, con turno/lock):** correr la tool
   `exportar_proyecto` de `revit-mcp-tools` con
   `{"path": "...proyecto.json", "marker": "MCP:LOSA-ESQ", "incluir": ["losas"]}`.
   El bloque `losas` sale con Mark, contorno real del sketch, huecos, espesor,
   nivel y cota. *(Solo lectura del modelo.)*
2. **Local (este paquete, sin BIM vivo):**

   ```bash
   puente-losas --proyecto proyecto.json --usos usos.json --salida salidas/ --nombre "Proyecto X"
   ```

   `usos.json` declara por Mark el uso (set de carga), la mampostería medida,
   los vuelos y, si hace falta, borde/dirección/espesor. Salidas:
   `informe_losas.xlsx`, `mapa_losas.svg`, `plan_etabs.json`,
   `sistema_losas.DL` (abrible en LosasPlus / corrible en Losas.exe) y
   `resultados.json` (la corrida cruda, auditable).
3. **ETABS (sesión viva, con turno/lock):** ejecutar `plan_etabs.json` paso a
   paso con el servidor MCP [`fea`](../servidor-mcp/): cada paso nombra la tool
   y sus argumentos, y los pasos por `call_oapi` exigen confirmar la firma con
   `describe_oapi` antes de llamar. El plan se detiene **antes** de Run
   Analysis (regla §22 del prompt).

## Reglas de Arlette que el código aplica

| Regla | Dónde |
|---|---|
| Unidades Ton, m, °C | `etabs_plan.py` (primer paso, `set_units`) |
| C210: E = 2 188 197.76 tonf/m², peso 2.4028 | `etabs_plan.py` / `motor.py` (Ec = 15100·√f'c) |
| **Shell-Thick en TODAS las losas** | `etabs_plan.py` (nunca Membrane/Shell-Thin) |
| Biblioteca L12/L15/L20 macizas, L25A-1D/2D aligeradas | `espesor.py` → `seccion_biblioteca` |
| Geometría en múltiplos de 0.05 m | `etabs_plan.py` (`ajustar_005`, desviación reportada) |
| Dimensiones del Excel SIEMPRE ↑ a 0.05 (1.56→1.60) | `espesor.py` / `informe_excel.py` |
| Sets: Entrepisos 0.16+0.20 · Comun 0.18+0.40 · Techo 0.16+0.10 · Parqueos 0.16+0.50 · Gimnasio 0.18+0.50 (t/m²) | `cargas.py` |
| Mampostería aparte, mínimo 0.10 en paños apoyados, redondeo ↑0.05 al asignar | `cargas.py` |
| **Vuelos sin mampostería y sin el mínimo** | `cargas.py` (excepción obligatoria §13.1) |
| LiveP solo si hay parqueos | `etabs_plan.py` |
| Peso propio en el patrón Dead (multiplicador 1), nunca duplicado | `etabs_plan.py` |
| Detenerse antes de Run Analysis | `plan_etabs.json` → `meta.requisitos` |

## La vía Pieper-Martens (el método de Losas.exe)

Además del FEM, el puente calcula cada paño por el **método de Pieper-Martens**
(Prof. Dr. Ing. Klaus Pieper y Dipl. Ing. Peter Martens, TU Braunschweig), el
mismo del motor `Losas.exe` del Ing. Francisco E. Perdomo (Losas v5.21) que
LosasPlus invoca con archivos `.DL`:

- `pieper_martens.py` — tablas de coeficientes (`datos/TablasPerdomo.json`,
  21 subtipos × 31 filas, extraídas y validadas en EstructurasRD desde el PDF
  de Perdomo), interpolación lineal en ε=Ly/Lx (0.50–2.00) y balanceo de
  momentos de borde (promedio con piso 0.75·max; en vuelos gobierna el vuelo).
- `tipo_pm.py` — clasifica cada paño en el código de TIPO del `.DL` (10..60,
  71/72 voladizos) a partir de la adyacencia; un vuelo vecino **no** empotra
  (convención verificada en el fixture). Las losas de TRES bordes (borde libre
  real, códigos x3/x4) exigen declaración manual.
- `dl_io.py` — escribe/lee el `.DL` y parsea el `.TXT` de salida de Losas.exe.
- El informe trae las columnas **PM Mfx/Mfy/Msx/Msy** junto a las del FEM y la
  hoja **Apoyos PM** con los momentos de borde balanceados.

**Validación:** fixture de oro `restaurante_2.DL` → `restaurante_2.TXT`
(salida real de Losas.exe v5.21, tomado de EstructurasRD): los 20 momentos de
losa y los 6 de apoyo coinciden con tolerancia **0.01 ton·m/m** — la misma del
motor C# verificado, porque los coeficientes S del PDF vienen a 2 decimales
(introduce ~0.007 al interpolar). Solo los códigos 40 y 71 tienen verificación
numérica contra Losas.exe; el resto del mapeo viene del PDF.

Diferencia de fondo entre vías: PM asume **apoyos rígidos** y paños
rectangulares; el FEM acota con bordes simple/empotrado; **ETABS** analiza la
estructura real. Tener las tres columnas en el mismo informe es el chequeo.

## Qué es (y qué no es) este cálculo

- **Es predimensionado.** Cada paño se analiza como rectángulo equivalente
  Lx×Ly con borde uniforme ("empotrado" solo si sus 4 bordes tienen vecino
  contiguo; una junta de 0.10 m corta la continuidad). Huecos y entrantes no
  entran al FEM; viajan al plan de ETABS, donde se modelan como aberturas.
- **Los vuelos no pasan por el FEM** (el modelo de placa apoya los 4 bordes y
  un voladizo quedaría falsamente rígido): van como franja en voladizo
  analítica — M = q·l²/2, w = q·l⁴/(8D) — con el acero del mismo módulo
  ACI 318-19 del motor.
- Momentos y acero con **q última = 1.2D + 1.6L** (CDCRD Vol I T02 / ACI
  318-19 §5.3.1b). Flecha en servicio (D+L), **elástica inmediata** con
  sección bruta, contra el límite informativo l/240 (T.24.2.2).
- Espesor mínimo: ACI 318-19 T.7.3.1.1 (1D, incluido voladizo l/10) o
  §8.3.1.2(b) (2D con vigas, supuesto αfm > 2).
- El análisis **definitivo** es el de ETABS con la geometría real; nada de lo
  que este puente imprime sustituye esa corrida ni la revisión de un ingeniero.

## Instalación y tests

```bash
cd puente-losas
python -m venv .venv && .venv/Scripts/activate      # en Windows
pip install -e .[dev]                                # instala motor-fea desde GitHub
pytest
```

Para desarrollo sin red: clonar EstructurasRD en `.vendor/EstructurasRD`
(gitignorado) y `pip install -e .vendor/EstructurasRD/motor-fea`.

## Ejemplo publicable

`ejemplo/edificio-ejemplo.json` + `ejemplo/usos-ejemplo.json`: seis paños con
dimensiones **inventadas** (no corresponden a ningún proyecto real), que
cubren junta sísmica, hueco de escalera, vuelo y mampostería declarada.

```bash
puente-losas --proyecto ejemplo/edificio-ejemplo.json --usos ejemplo/usos-ejemplo.json --salida salidas/
```

## Verificación

Las nuevas [comprobaciones de nervios y placas ortótropas](NERVIOS.md) separan
resistencia, deformaciones y geometría; no escriben cambios en Revit.

`tests/` (pytest) incluye un caso de referencia contra la **solución analítica
de Navier** (placa simplemente apoyada con carga uniforme, serie doble de
Timoshenko): la flecha central del FEM queda dentro del 3–4 % y el momento de
vano dentro del 10 % (momentos en centros de elemento). El resto de los tests
cubre las reglas de carga (con los ejemplos literales de los redondeos), el
espesor mínimo, la continuidad por adyacencia, el plan de ETABS y la corrida
completa del CLI sobre el ejemplo.
