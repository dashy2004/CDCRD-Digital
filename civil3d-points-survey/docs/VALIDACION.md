# Evidencia de puntos COGO y Survey

18 de octubre de 2026 · Civil 3D 2027 · Windows · COM 13.9 · módulo 0.1.0.

El fixture contiene 12 puntos en una malla de 15 × 10 m, cotas entre 10 y 10,7 m.
Se ejecutaron operaciones en Civil 3D y se compararon los CSV nativos con la entrada.
La evidencia publicable está en [native-verification.json](native-verification.json).

| Prueba | Resultado |
|---|---|
| Importación y auditoría COGO | 12 puntos; coordenadas y descripciones coincidentes |
| Grupo `DEMO_TN` | 101, 102, 105, 106, 109 y 110 |
| Guardar/cerrar/reabrir dibujo | Misma colección de puntos y pertenencia de grupos |
| Importación Survey | 12 NonControlPoints en una base previamente vacía |
| Cerrar/reabrir Survey y releer | Conteo, unidades, zona, coordenadas y descripciones verificados |
| Error máximo en coordenadas | 1,78e-15 m frente a tolerancia 1e-7 m |
| Dibujo equivocado, grupo repetido, Survey ocupado | Rechazados; puntos conservados |
| Pruebas Python | 13 pruebas de validación de entradas y comparación |

## Cinco operaciones, cinco láminas

![Inventario](images/audit.png)

`audit`: tabla obtenida del CSV después de reabrir el dibujo.

![Importación](images/import.png)

`import`: vista exportada por el trazador nativo. Se aplicó un estilo de etiqueta
común para presentar los 12 puntos; ese ajuste visual no forma parte del importador.

![Grupo](images/group.png)

`group`: vista nativa con los seis TN visibles; los otros puntos se ocultaron por
capa para la exportación y se restauraron después.

![Survey](images/survey.png)

`survey-import`: esquema basado en recibos nativos. No es una captura de Toolspace.

![Relectura](images/survey-read.png)

`survey-read`: cuadro de comparación y controles; no es una captura de escritorio.

## Límites comprobados

El control de ventanas no funcionó en este entorno, por lo que no se produjeron
capturas de escritorio. Las láminas distinguen exportación nativa e informe de API.
No se publican dibujos, bases Survey ni datos de proyectos privados.

La prueba de creación automática `Projects.Create` dejó una base vacía y necesitó
Escape manual. Esa operación se excluyó del módulo publicado. Crear la base vacía
es un requisito previo; importar, verificar, cerrar y restaurar la carpeta sí se
comprobaron mediante API. No se cambió la configuración de seguridad de Civil 3D.

No hubo observaciones instrumentales, estaciones, figuras ni compensación de red.
No se generaron líneas de quiebre ni superficies a partir de estos puntos en esta
etapa; las herramientas de superficies/taludes están en el módulo separado.

## Contratos consultados

Firmas públicas de las bibliotecas COM instaladas: `IAeccPoints.Add/Find`,
`IAeccPointGroup.QueryBuilder/ContainsPoint`, `IAeccSurveyProjects.FindItem`,
`IAeccSurveyProject.Open/Close/GetPointNumbers` y `NonControlPoints.Create`.
No se distribuyen bibliotecas Autodesk ni código descompilado.

La gestión de errores usa el mecanismo documentado por Autodesk:
[vl-catch-all-apply](https://help.autodesk.com/cloudhelp/2023/ENU/AutoCAD-AutoLISP/files/GUID-2138B8F3-F0E1-4DB4-97C4-EC26047550E0.htm).
Las operaciones COM pueden dejar cambios parciales; el recibo inicial `running`
y el checkpoint permiten identificar una interrupción sin confundirla con éxito.

## Comprobación de unidades

Se detectó que el dibujo de demostración tenía INSUNITS=6 pero DrawingUnits=Feet.
Se corrigió a Meters, se conservaron las coordenadas y se volvieron a exportar las
vistas. El ejecutor ahora comprueba ambas configuraciones y rechazó nativamente
la discrepancia antes de operar. Nunca se interpreta INSUNITS aislado como prueba
suficiente de las unidades de Civil 3D. La comparación tras la corrección volvió
a pasar sin escalar coordenadas.
