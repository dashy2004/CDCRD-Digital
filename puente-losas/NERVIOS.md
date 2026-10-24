# Comprobaciones de nervios y sensibilidad de placas

API Python de cálculo separada de cualquier escritura CAD. No convierte un
predimensionado en un diseño completo ni aprueba automáticamente un espesor.
`apoyos_losa` sigue siendo la fuente geométrica de solo lectura en Revit.

## Funciones y unidades

`nervios.RibSection`: geometría rectangular/T en mm; f'c, fy, Ec y Es en MPa.
`flexure`: compatibilidad de deformaciones con bloque de compresión y acero de
ambas caras; resta el concreto desplazado y devuelve equilibrio, deformación,
phi y capacidad en kN·m. La resistencia y el requisito de sección controlada por
tracción son comprobaciones distintas. Un `strength_pass=True` no aprueba el diseño.
Para negativo se usa el alma rectangular; no se supone una ala comprimida superior.

`cracked_inertia` y `effective_inertia`: sección transformada y transición de
inercia no pretensada, con resultados mm4. La primera omite acero de compresión.
`shear_without_stirrups`: concreto normal, sin fuerza axial, sin bonificación de
nervio; incluye límite de resistencia del concreto. No verifica estribos mínimos.
`anchored_cells`: intervalos de EPS con origen común y piezas terminales recortadas.
La alineación geométrica no demuestra continuidad estructural del armado.

`navier_center`: placa ortótropa de cuatro bordes simples, carga uniforme en N/m2,
rigideces Dx,Dy,H en N·m y flecha en m. H=0 representa una sensibilidad sin torsión.
`placa_ritz.solve`: comparación con bordes de giro restringido; mismo modelo
homogeneizado, D12=0, D66=H/2. No recupera momentos de una placa isotrópica con
acoplamiento de Poisson aunque su ecuación de desplazamientos pueda coincidir.
Devuelve flecha máxima muestreada en101×101puntos, residuo y condición numérica.
Se deben contrastar órdenes de aproximación y la condición física de los apoyos.

Instalación: `pip install -e './puente-losas[dev,calculo]'`.
Las funciones de nervios y Navier no necesitan NumPy; Ritz sí.

## Límites que deben conservar los consumidores

- La luz de la tabla8.3.1.2 es entre caras de vigas. No sustituir caras de columnas.
- No confundir espesor de peso, espesor equivalente de inercia y altura total.
- No usar momentos de losa maciza por metro como acero de un nervio sin convertir
  ancho tributario y comprobar la sección, las capas de barras y sus intersecciones.
- No tomar contacto/vecindad de Revit como empotramiento probado.
- La placa no representa bandas macizas, nervios discretos, flexibilidad de vigas,
  fisuración espacial, fases constructivas, torsión real ni asentamientos.
- Un estudio que falla no demuestra que toda solución del mismo espesor sea
  imposible; tampoco permite escribir automáticamente una alternativa más gruesa.
- No acreditar acero de compresión para fluencia si su posición queda del lado
  traccionado del eje neutro fisurado. Anclajes, juntas, fuego, exposición, cargas
  concentradas y encharcamiento requieren comprobaciones específicas.

## Pruebas

Las pruebas usan dimensiones sintéticas. Incluyen equilibrio cerrado de una
sección rectangular, compresión de barras sin fluencia y concreto desplazado,
límites de Ie, tope de cortante, rechazo de entradas no finitas/booleanas,
Navier cuadrado y límite de franja, Ritz frente a Fourier, placa con todos los
bordes empotrados, intercambio de ejes y convergencia de bordes mixtos.

Referencias: ACI318-19 §§8.3,8.8,21.2,22.5,24.2 y la discusión del fabricante
[StructurePoint sobre equivalencia por peso e inercia](https://structurepoint.org/spSlab-spBeam-Online-Manual/spSlabPlusBeam/Chapter_2/Chapter_2.htm?rhtocid=_2).
La biblioteca no selecciona por sí sola el régimen normativo de un expediente.
