# Cálculo hidráulico local por API y MCP

Núcleo puro `src/hidraulica.py`, sin dependencias externas ni conexión CAD.
Fachada independiente `src/mcp_hidraulica.py`, compatible con las dependencias
MCP del servidor existente. Exportador `src/exportar.py` para tablas JSON/CSV.
La integración en `src/server.py` se coordina por separado; ejecutar esta fachada
no modifica dibujos ni carga el plugin .NET.

## Uso reproducible

Desde `servidor-mcp-civil3d`:

```powershell
py -m pip install "mcp>=1.10,<2"
py -m unittest discover -s tests -v
py src/exportar.py tests/ejemplo_sintetico.json salida-nueva
py src/mcp_hidraulica.py
```

El último comando sirve MCP por stdio. La herramienta es `calcular_seccion_si`.
La prueba `test_hidraulica_stdio.py` inicia un proceso real, negocia MCP, consulta
el esquema, ejecuta un cálculo, comprueba errores y recupera la sesión.
La fachada usa tipos estrictos de Pydantic (dependencia de MCP) para rechazar
booleanos y cadenas en campos numéricos antes de convertirlos.
Los ejemplos del repositorio son sintéticos.

## Contrato 0.1.0

`calculate(request: dict) -> dict` exige exactamente estas nueve claves;
la fachada expone los mismos nombres. No hay valores predeterminados ocultos.

| Clave | Unidad y condición |
|---|---|
| `units` | Cadena `SI` |
| `q_m3_s` | m³/s, positivo |
| `b_m` | ancho de fondo en m, no negativo |
| `z_h_v` | talud horizontal/vertical, no negativo; b y z no pueden ser ambos cero |
| `n_s_m13` | Manning en s/m^(1/3), positivo |
| `slope_m_m` | pendiente de energía m/m, positiva |
| `bed_m` | cota de solera en m, datum declarado por el proyecto |
| `available_head_m` | carga TOTAL disponible en m del mismo datum, o `null` si desconocida |
| `losses_m` | pérdidas locales asumidas/verificadas en m, no negativas; cero debe introducirse expresamente |

`normal` y `critical` devuelven geometría, tirante, velocidad, Froude, energía
específica, carga total y nivel de agua, con unidades en las claves. Se usa g=9.81
m/s² y alpha=1. La entrada se conserva en `inputs`, junto con `schema_version`
y la declaración de alcance `scope`.

`energy_gate.status` distingue `unverified`, `insufficient` y
`necessary_condition_met`. Un margen positivo es únicamente una condición
necesaria local. `route_verified` siempre es falso: no se ha solucionado la ruta.
Una cota topográfica de la toma no es una medida de carga total.

El exportador registra SHA256 de los bytes de entrada y del núcleo y genera
resultados deterministas. Rechaza una carpeta de salida existente. La procedencia
de los datos de diseño, hipótesis y capturas se conserva en el proyecto privado;
estos archivos de cálculo no constituyen por sí solos un informe APA.

## Modelo y límites

Geometría simétrica trapezoidal (también rectangular y triangular). Manning
resuelve flujo uniforme: solo en esa condición la pendiente de energía coincide
con la pendiente del fondo. El tirante crítico satisface g A³ = Q² T con alpha=1.
Las raíces se obtienen por acotación/bisección y se comprueba el residuo.

La comprobación energética resta carga requerida y pérdidas a la disponible.
No calcula todavía demanda de riego, Darcy, flujo gradualmente variado, remanso,
transiciones, resalto, control de cola ni disipadores. No permite certificar ni
implantar rasantes a partir de cálculos uniformes aislados. No invoca HCanales:
una comparación histórica externa no equivale a una API de ese programa.

Fuentes de las ecuaciones (consultadas 2026-10-11):

- [USACE HEC-RAS: Uniform Flow Computations, 6.6](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/6.6/stable-channel-design-functions/uniform-flow-computations).
- [USACE HEC-RAS: Equations for Basic Profile Calculations, 6.0](https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/6.0/theoretical-basis-for-one-dimensional-and-two-dimensional-hydrodynamic-calculations/1d-steady-flow-water-surface-profiles/equations-for-basic-profile-calculations).

Las pruebas incluyen solución crítica analítica, mínimo de energía, residuo de
Manning, rechazo de entradas, condición energética, exportación reproducible y MCP.
No sustituyen la validación de un proyecto, el control normativo ni las pruebas CAD.
