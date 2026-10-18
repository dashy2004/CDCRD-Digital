# Ensayo sintético de continuidad y anclaje — no construir

Caso auxiliar reproducible, **no aplicado al EDB**. No es el diseño de una
cimentación ni una lista de cortes autorizada. No modifica el análisis ni el
detallador propietario. El resultado conserva `complete_detailing=false` y
`engineering_approval=false` aunque pasen los controles geométricos.

## Hipótesis elegidas para el ensayo

Bloque de 4.800 × 1.600 × 1.000 mm, coronación z=0; muro de 4.000 × 200 mm y
altura 6.000 mm. Concreto normal de 30 MPa, acero vertical recto sin revestir ni
agrupar, fy=60.000 psi (413,685 MPa). La asignación efectiva del acero del diseño
ETABS debe cotejarse aparte: su existencia en el catálogo no la demuestra.

34 barras de 16 mm, continuas desde z=-800 hasta z=5.960 mm, sin empalmes ni
dobleces. Posiciones candidatas x=±40 mm, y=60…3.940 mm con paso242,5 mm.
Convención propuesta: 40 mm hasta la barra horizontal exterior de 12 mm y
vertical tangente por dentro. **No se presume equivalente al overwrite de
recubrimiento de ETABS**: la sección resistente con estas posiciones necesita
verificación. No se han generado ni aprobado los cercos, ganchos o confinamiento.

## Cálculo acotado

Referencia: [ACI 318-19](https://www.ocf.berkeley.edu/~chiep/wp-content/uploads/2024/01/CE-123-ACI-318-19.pdf),
25.4.2.4a, 25.4.2.1 y 18.10.2.3(b). El motor calcula en las unidades originales
psi/pulgadas y convierte explícitamente a mm; no usa un coeficiente SI aproximado.
Usa Ktr=0, factores psi=1, sin reducción por acero excedente, cb=40 mm y límite
de confinamiento2,5. Incluye el mínimo12 in y factor1,25 por posible fluencia.

Resultado del ensayo: ld requerido545,760 mm; empotramiento800 mm. Reserva al
fondo200 mm frente a75 mm adoptados. Cada recta mide6.760 mm, total229.840 mm.
Estos números pertenecen **a la alternativa sintética**, no a la jaula nativa
capturada, cuyas barras no se prolongan por debajo de la base. No hay traslapos
en esta alternativa; eso no valida los914,4 mm de empalme del detalle anterior.

## Alcance excluido

Capacidad y asentamientos del terreno; estabilidad y dimensionado de la zapata;
armado a flexión/cortante/punzonamiento de la cimentación; transferencia de
cortante en junta; capacidad del muro con las posiciones propuestas; requisitos
de confinamiento, producto, tolerancias, corrosión y construcción. Requiere
revisión profesional antes de cualquier uso real.

## Reproducir y detectar la regresión del detallador

```powershell
python tools/check_wall_anchorage_fixture.py
python -m pytest tests/test_wall_detail_checks.py -q
```

`wall_detail_checks.py` es puro y no se conecta a ETABS. Las posiciones horizontales
de ensayo usan techo, no redondeo: en el rango76,2…2.923,8 mm, máximo450 mm implica
ocho formas, paso406,8 mm. Esto prueba un límite de separación, no el corte de
una barra horizontal. El lector rechaza derivar una recta de una polilínea con
arcos/dobleces; la geometría completa sigue siendo un pendiente explícito.
