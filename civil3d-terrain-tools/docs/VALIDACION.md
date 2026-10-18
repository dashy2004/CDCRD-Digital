# Validación de la entrega 0.2.0

Fecha: 2026-10-18. Ejecución local sobre dibujos sintéticos nuevos, con Civil 3D 2027. Los recibos exitosos identificaron `Cdcrd.Earthworks, Version=0.2.0.0`; el hash del ensamblado está en `native-verification.json`. No se utilizó un dibujo de cliente para generar esta galería.

- **17 pruebas Python**: volúmenes analíticos de corte/relleno, simetría y valor conocido de un plano inclinado, conservación del área de malla, inversión de orientación, traslación a coordenadas grandes, planos coincidentes, modos solo corte/solo relleno, cobertura incompleta/excesiva, encuentro fuera del dominio, parámetros no finitos y áreas de sección con cambio de signo.
- **Compilación .NET**: Release x64 contra la instalación local de Autodesk; cero errores y cero advertencias de la compilación final.
- **Creación nativa**: dos bases, tres superficies de diseño y tres superficies de volumen. Valores de referencia: corte 276; relleno 276; mixto 58/9 de corte y 58/9 de relleno, en m³. Error máximo frente al cálculo independiente: 3,57e-8 m³.
- **Secciones nativas**: dos alineamientos, dos grupos, 194 líneas, 485 secciones dinámicas y 14 vistas. Cadenas `SegmentTo` continuas. Elevaciones comprobadas contra intersecciones de los TIN: error máximo 3,08e-9 m. Áreas extremas promedio a 0,25 m: 275,958333 m³ para corte/relleno puros; 6,464141 m³ por lado para el caso mixto. Diferencia máxima respecto al TIN: 0,306 %.
- **Rechazos ejecutados**: dibujo esperado incorrecto, nombre ya existente y volumen esperado deliberadamente incorrecto. El tercer caso comprobó la reversión de la transacción; las superficies, COGO y secciones auditadas quedaron iguales.
- **Persistencia**: guardar, cerrar, abrir y comparar las auditorías de COGO, triángulos, volúmenes, alineamientos, secciones y vistas. Coincidencia exacta; ninguna superficie desactualizada.
- **Galería**: PDFs del motor de trazado nativo, normalizados por su rotación de página y montados en láminas con títulos. Se revisaron visualmente las imágenes finales. `verificacion.png` es una tabla generada a partir de los resultados, no una captura de Civil 3D.

## Lo que estas pruebas no cubren

Compatibilidad con otras versiones o plantillas, curvas de alineamiento, límites interiores de malla, dominios desconectados, cambios de geometría de origen después del ejercicio, cargas de miles de superficies, fallos de disco durante la escritura de recibos, validación geotécnica y cubicación contractual. Los perfiles requieren continuidad; la comprobación de área del dominio no demuestra una topología arbitraria correcta. La auditoría recorre todo el dibujo y puede generar datos privados; no se debe subir una auditoría de un proyecto real a este repositorio.

La prueba de sesión instalada se realiza manualmente con el ejemplo reproducible: los tests Python por sí solos no prueban una conexión con Civil 3D.

## Comprobación de unidades pendiente en la demostración R2

La etapa COGO/Survey detectó que una plantilla podía tener INSUNITS=6 y
DrawingUnits=Feet, además de etiquetas en pies. Se corrigió y verificó la nueva
demostración COGO. La copia privada de trabajo sí tiene DrawingUnits=Meters.
La demostración sintética histórica de terreno R2 todavía no se ha inspeccionado
para estas dos configuraciones adicionales. Sus comparaciones numéricas y la
persistencia permanecen documentadas, pero la presentación métrica integral de
esa demostración queda pendiente.

El guard del plugin 0.2.0 solo comprueba INSUNITS. Antes de cerrar esta entrega:
comprobar Civil DrawingUnits y unidades de estilos en una copia de la demo R2,
añadir el guard correspondiente y repetir la comprobación nativa con una nueva
versión del ensamblado. No interpretar una compilación como prueba de la DLL
cargada, ni reiniciar una sesión que contenga un original con cambios sin guardar.
