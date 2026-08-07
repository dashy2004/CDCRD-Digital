# R06 — Espectro CDCRD y casos sísmicos

## Herramientas
```
define_cdcrd_spectrum(name="CDCRD-SD", SDS=0.4877, SD1=0.2583, campo_cercano=False)
add_response_spectrum_case(name="Ex", spectrum="CDCRD-SD", direction="X", scale=9.80665)
add_response_spectrum_case(name="Ey", spectrum="CDCRD-SD", direction="Y", scale=9.80665)
```

## Captura
| Archivo | Vista | Estado |
|---|---|---|
| `01-espectro-grafico.jpg` | Define > Functions > Response Spectrum > CDCRD-SD, con la gráfica | **PENDIENTE — crítica** |
| `02-espectro-tabla.jpg` | Tabla de valores T vs Sa de la misma función | **PENDIENTE — crítica** |
| `03-caso-ex.jpg` | Define > Load Cases > Ex, parámetros del caso | **PENDIENTE** |
| `04-casos-lista.jpg` | Lista de casos mostrando Ex y Ey | **PENDIENTE** |

Las dos primeras dejan de ser opcionales en este bloque: son el **único canal de
verificación disponible** para los valores del espectro, porque las tablas de
funciones no devuelven filas por API (ver más abajo).

## Criterio de aceptación — verificar 3 puntos a mano sobre la gráfica
- T = 0 → Sa = 0.4·SDS = 0.1951 g
- T0 = 0.106 s a Ts = 0.530 s → meseta Sa = 0.4877 g
- T = 1.0 s → Sa = SD1 = 0.2583 g
- T = 2.0 s → Sa = 0.1292 g

Si la meseta no arranca en 0.4·SDS, la rama ascendente está mal construida.

## Punto de riesgo
`Func.FuncRS.SetUser` y `LoadCases.ResponseSpectrum.SetLoads` son las firmas
menos verificadas. Si fallan, correr `describe_oapi(path="Func.FuncRS")` y
`describe_oapi(path="LoadCases.ResponseSpectrum")` y registrar aquí la firma real.

## Resultado

**Estado: PARCIAL.** El espectro y los dos casos están creados y la forma se
verificó por cálculo, pero **los valores dentro de ETABS no se pudieron leer de
vuelta por API**. La verificación numérica definitiva queda en las capturas 01 y 02.

| Punto del criterio | Valor calculado | Criterio | Veredicto |
|---|---|---|---|
| T = 0 | Sa = 0.19508 g | 0.4·SDS = 0.1951 g | **OK** (cálculo) |
| T0 = 0.106 s | Sa = 0.48770 g | meseta 0.4877 g | **OK** (cálculo) |
| Ts = 0.530 s | Sa = 0.48736 g | meseta 0.4877 g | **OK** (cálculo; 0.530 cae apenas después de Ts = 0.529629, ya en la rama descendente) |
| T = 1.0 s | Sa = 0.25830 g | SD1 = 0.2583 g | **OK** (cálculo) |
| T = 2.0 s | Sa = 0.12915 g | 0.1292 g | **OK** (cálculo) |
| Existencia de la función en ETABS | confirmada indirectamente | — | **OK** |
| Valores dentro de ETABS | no legibles por API | — | **PENDIENTE** (capturas) |

Parámetros usados, contrastados contra la tabla normativa de `INSTRUCCIONES.md`
antes de escribir: SDS = 0.4877 g, SD1 = 0.2583 g. Son internamente consistentes:
`Ts = SD1/SDS = 0.529629 s` y `T0 = 0.2·Ts = 0.105926 s`, que reproducen los
0.106 / 0.530 s de la tabla.

### Firmas reales (el bloque pedía registrarlas)

```
Func.FuncRS.SetUser([in] Name: BSTR, [in] NumberItems: long,
                    [in,out] Period: SAFEARRAY(double), [in,out] Value: SAFEARRAY(double),
                    [in] DampRatio: double)                                   [dispid 50]

LoadCases.ResponseSpectrum.SetLoads([in] Name, [in] NumberLoads,
                    [in,out] LoadName[], Func[], SF[], CSys[], Ang[])         [dispid 21]
```

Ambas **coinciden exactamente** con lo que el servidor invoca. Se leyeron con
`describe_oapi` **antes** de ejecutar, no después de fallar.

### Incidencia: `SetUser` devuelve `ret=-99` con la firma correcta

`define_cdcrd_spectrum` falla con `SetUser(5 args): ret=-99`. Descartado el nombre
como causa (se probó también sin guion). La firma es la del typelib y los datos son
válidos: 13 puntos, periodos estrictamente crecientes, amortiguamiento 0.05.
`-99` no es el `ret=1` habitual de rechazo por contenido; no se determinó su
significado.

**Rodeo aplicado:** se escribió la función por la tabla
`Functions - Response Spectrum - User Defined` con los 13 puntos generados por la
misma fórmula del CDCRD (cl. 2.9.4.4). La escritura devolvió el log de importación
de ETABS sin errores fatales.

### Cómo se confirmó que la función existe, sin poder leerla

`Functions - Response Spectrum - User Defined` y
`Load Case Definitions - Response Spectrum` devuelven **solo los encabezados**, sin
filas — incluso con dos casos que sabemos creados. No es el problema de parser de
una sola fila que apareció en R04: con dos casos sigue sin devolver datos. Estas
tablas de definición simplemente no exponen filas por `GetTableForDisplayArray` en
este estado del modelo.

Prueba indirecta, decisiva: se intentó crear un caso apuntando a una función
inexistente (`NO_EXISTE_ESTA_FUNCION`) y ETABS lo rechazó con `SetLoads: ret=1`.
Como los casos `Ex` y `Ey` apuntando a `CDCRD-SD` **sí** fueron aceptados con
`ret=0`, ETABS reconoce la función. **La escritura por tabla funcionó.**

Lo que esa prueba no demuestra es que los 13 pares (T, Sa) hayan quedado con los
valores correctos. Por eso las capturas 01 y 02 pasan a ser críticas.

**Actualización 2026-08-07, tras la Tanda 1:** se intentó cerrar la verificación
con la herramienta nueva `get_spectrum` (que llama `Func.FuncRS.GetUser`, firma
verificada del typelib) y devolvió **`ret=-99`, el mismo código que `SetUser`**.
El patrón completo queda así: sobre esta función, `SetUser` da −99, `GetUser` da
−99, y la tabla de funciones no devuelve filas — pero los casos `Ex`/`Ey` la
referencian y el análisis de R08 corrió con resultados espectrales coherentes.
Hipótesis más consistente: la función escrita por importación de tabla no queda
registrada en el subtipo "User" que `FuncRS.GetUser/SetUser` manejan, aunque sí
es una función RS válida para los casos. Sea cual sea la causa, **la verificación
numérica de los 13 puntos sigue dependiendo de las capturas 01 y 02** — es el
único ítem del protocolo en esa condición.

### Ejecutado

```
[describe_oapi de Func.FuncRS y LoadCases.ResponseSpectrum — firmas verificadas]
define_cdcrd_spectrum(...)                    -> FALLA, ret=-99
[escritura de la tabla Functions - Response Spectrum - User Defined, 13 puntos]
add_response_spectrum_case("Ex", "CDCRD-SD", "X", 9.80665)   -> OK, direccion U1
add_response_spectrum_case("Ey", "CDCRD-SD", "Y", 9.80665)   -> OK, direccion U2
save_model()
```

El factor 9.80665 es correcto: el espectro está en fracción de g y el modelo en
kN·m, así que la escala debe ser g en m/s².

### Pendiente de limpieza — hacer antes de R08

`ZZ_TEST_FUNC`: caso de espectro vacío que quedó de la prueba de validación. El
`SetCase` se ejecutó antes de que fallara el `SetLoads`, así que el caso existe sin
cargas asignadas. **Un caso de espectro sin cargas puede hacer fallar el análisis
de R08.** Borrarlo desde `Define > Load Cases`.

No se pudo borrar por MCP: `LoadCases.Delete` existe en la OAPI (dispid 4) pero
**ninguna herramienta del servidor lo expone**; `delete_object` solo cubre puntos,
frames y áreas. Es un hueco real, anotado como deuda.

### Deuda de código derivada

1. **Falta una herramienta de borrado para definiciones** (casos, patrones,
   combinaciones, funciones, materiales). Hoy cualquier objeto de prueba queda
   permanente. Ya hay dos residuos en el modelo: `ZZ_TEST_ESCRITURA` (material,
   de R02) y `ZZ_TEST_FUNC` (caso, de este bloque).
2. **`define_cdcrd_spectrum` no funciona contra esta instalación.** Mientras no se
   entienda el `ret=-99`, la vía es la tabla. Conviene que la herramienta caiga a
   la tabla automáticamente, como respaldo.
3. **`add_response_spectrum_case` no fija el caso modal** (`SetModalCase`, dispid
   22). Hereda el modal por defecto. El modelo tiene un caso `Modal` definido, así
   que R08 debería correr, pero conviene fijarlo explícitamente.
