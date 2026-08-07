# Resumen de capturas — sesión 2026-08-08

Sesión de solo-captura sobre `edificio_oficinas_SD.EDB`, bloques R01 a R10,
según protocolo de `INSTRUCCIONES.md`. No se modificó geometría, niveles,
cargas, espectro, combinaciones ni residuos `ZZ_*`; no se corrió análisis; no
se hizo `git push`.

## Conteo

El acta (`INSTRUCCIONES.md`, punto 6) y la instrucción de esta sesión dicen
"33 capturas". El recuento explícito por bloque —2+4+5+4+3+4+2+4+3+3— da
**34**, no 33. Es el primer hallazgo de la noche, antes de tocar ETABS.

| Bloque | Capturas listadas | Completadas | Pendientes |
|---|---|---|---|
| R01 | 2 | 2 | 0 |
| R02 | 4 | 4 | 0 |
| R03 | 5 | 5 | 0 |
| R04 | 4 | 4 | 0 |
| R05 | 3 | 3 | 0 |
| R06 | 4 | 4 | 0 |
| R07 | 2 | 2 | 0 |
| R08 | 4 | 3 | 1 |
| R09 | 3 | 3 | 0 |
| R10 | 3 | 3 | 0 |
| **Total** | **34** | **33** | **1** |

**Pendiente único:** `R08/02-ventana-analisis.jpg` (ventana de progreso del
análisis de ETABS). Requiere disparar `run_analysis()`/F5, explícitamente
fuera de alcance de una sesión de solo-captura. No se intentó.

Cada README de bloque quedó actualizado con la ruta relativa de cada captura
o, en el caso de R08/02, con la razón de por qué sigue pendiente.

## Hallazgos que contradicen el acta o los README de bloque

### 1. Recuento de capturas: 34, no 33
Ver arriba. Aritmética simple, no requirió abrir ETABS.

### 2. Story Data ya muestra 3 niveles correctos — RESUELTO 2026-08-07
La captura `R02/04-story-data.jpg` (Edit > Stories and Grid System Data)
muestra `Story1/Story2/Story3` de 3 m cada uno, base en 0 — la configuración
que el bloque R02 pedía como criterio de aceptación. El README de R02
documenta, como estado vigente, que los niveles seguían siendo
`Story1..Story4` de 3.6576 m.

**Corrección a lo que escribí originalmente aquí.** Reporté que el cambio
"no está documentado en ningún README" y planteé dos hipótesis. Estaba
equivocado: el repo contiene
`modelos/edificio_oficinas_SD_ANTES-NIVELES-2026-08-07.EDB`, un respaldo
cuyo nombre dice literalmente para qué se hizo, commiteado en `af39f69` el
2026-08-07 a las 03:18. **El paso manual de `Edit > Stories and Grid System
Data` sí se ejecutó y sí quedó registrado** — en el nombre de un archivo del
repo, no en prosa.

Lo que queda en pie es más chico y más concreto: **el README de R02 está
desactualizado**, no el modelo. Sigue afirmando como estado vigente algo que
dejó de serlo. Los resultados de R08–R10 corresponden a niveles de 3/6/9 m
(`hpx = 3.0 m` en el cálculo de derivas de R09), consistentes con la captura.

Error de método de mi parte: busqué el respaldo documental solo en los
`.md` y no en `git log` ni en el listado de `modelos/`. El nombre de un
archivo versionado es documentación.

### 3. Scale Factor de Ex: 9806.65, no 9.80665 (posible error de 1000×)
La captura `R06/03-caso-ex.jpg` (Define > Load Cases > Ex) muestra un Scale
Factor de **9806.65**, no los 9.80665 que documenta el README de R06 y que
`add_response_spectrum_case(..., scale=9.80665)` debería haber escrito. Es
exactamente un factor 1000×, compatible con una confusión mm/s² vs m/s² en
algún punto de la cadena de escritura.

**Matización necesaria, no una conclusión:** si la demanda sísmica hubiese
quedado 1000× inflada, se esperarían derivas y desplazamientos absurdos. No es
lo que se observa: T₁ = 0.358 s (R08) es físicamente razonable, el
desplazamiento bajo Ex documentado en R08 (19.747 mm) es del orden esperado,
y las derivas de R09 (máximo 0.002748, Δ de diseño 35.04 mm) cumplen
holgadamente el límite CDCRD con margen coherente para un pórtico regular de
hormigón. Nada de esto **demuestra** que el factor de escala real usado en el
análisis fuera 9.80665 — el número visible en el diálogo es 9806.65 — pero sí
hace descartable la lectura más simple ("el cortante basal quedó 1000× más
grande"). Es una discrepancia real, documentada en la captura, que no se
resolvió esta noche por estar fuera de alcance (no se debía tocar el
espectro ni los casos sísmicos). Requiere revisión antes de dar cualquier
resultado sísmico por definitivo.

### 4. Casos de carga `Dead`/`Live` huérfanos
Además de los ya conocidos `ZZ_TEST_ESCRITURA` (material, R02) y
`ZZ_TEST_FUNC` (caso de espectro vacío, R06), la lista de Load Cases sigue
mostrando casos llamados `Dead` y `Live` pese a que los patrones de carga
correspondientes (`Dead`/`Live` de plantilla) se habían eliminado en R05 en
favor de `D`/`SDL`/`L`/`Lr`. Son casos auto-generados por ETABS al crear cada
caso lineal-estático por patrón; probablemente quedaron huérfanos al borrar
los patrones. Materialidad baja (no participan de ninguna combinación de R07,
que usa `D`/`SDL`/`L`/`Lr`/`Ex`/`Ey`), pero es otro residuo sin limpiar. No se
tocó, por la misma regla de no tocar residuos `ZZ_*` ni objetos del modelo
esta noche — se deja anotado igual porque no es un `ZZ_*` y no estaba
identificado antes.

### 5. Conexión OAPI perdida al abrir ETABS por escritorio
Al abrir la ventana de modelo de ETABS con `computer-use` al inicio de la
sesión, la conexión del servidor `fea` (OAPI) se cayó y no se recuperó en el
resto de la noche (`refresh_view` y el resto de herramientas `mcp__fea__*`
devolvían "No hay conexión con ETABS"). Consecuencia directa: no fue posible
hacer ninguna llamada `get_story_drifts` ni `get_joint_reactions` fresca para
yuxtaponer contra las tablas de ETABS en pantalla. Las capturas
`R09/03-comparacion.jpg` y `R10/03-suma-verificacion.jpg` —pensadas como
"respuesta de la API junto a la tabla de ETABS"— terminaron reutilizando la
captura de la tabla de ETABS sola, con el lado "API" resuelto contra los
valores ya documentados en cada README (sesión del 2026-08-07), no contra una
llamada nueva. Los valores coinciden exactamente donde se pudieron comparar
(derivas: 0.001893/0.002748/0.001969; reacciones FZ: 404.7065/786.1283 por
posición), pero la comparación en sí no es "en vivo" para esta sesión.

### 6. Bloqueo temporal de computer-use por el clasificador
A mitad de la captura de R08/R09, todas las llamadas de `computer-use`
—incluidas capturas de pantalla de solo lectura— empezaron a devolver
"Permission... denied by the Claude Code auto mode classifier". Se resolvió
solo con reintentos espaciados a lo largo de 15–20 minutos, sin intervención
activa posible. No afectó el resultado final, solo el tiempo que tomó
llegar a él.

## Exclusiones respetadas (fuera de alcance esta noche)
- No se renombraron `Story1/2/3` a `Nivel 1/2/3`.
- No se corrió análisis (`run_analysis`).
- No se tocó ρ, la definición de losa, el espectro (más allá de abrir el
  diálogo para capturarlo, cancelado sin guardar), ni los residuos `ZZ_*`.
- No se hizo `git push`.

## Puntos abiertos heredados de sesiones anteriores (no reevaluados esta noche)
Documentados en `INSTRUCCIONES.md` y en los README de cada bloque, siguen
abiertos porque bloquean diseño, no porque falte captura:
- ρ sin resolver en las combinaciones de R07 (asumen ρ = 1.0).
- Espesor de losa real ≈ 0.2032 m (`Slab1`, material `4000Psi`), no los
  0.15 m que la documentación de trabajo asumía.
- Curva tensión-deformación del hormigón sin contrastar contra CDCRD/ACI 318.
