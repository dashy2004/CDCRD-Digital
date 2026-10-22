# Familias de Revit del plugin (no van a git)

Carpeta para las `.rfa` que el plugin carga en el modelo. Los binarios de
Revit **no se commitean** (política del repo); aquí solo vive este README con
la receta.

## CDCRD Tag Losa.rfa — tag de losa con Mark arriba y espesor abajo

La API de Revit **no puede crear labels** en una familia de tag (limitación
conocida: `FamilyItemFactory` no tiene creación de Label), así que esta
familia se hace **una vez a mano** (o se usa la del despacho) y la tool
`tag_losas` la carga sola:

1. Revit → Nueva **familia** → plantilla **Metric Generic Tag** (tag genérico
   métrico).
2. *Family Category and Parameters* → categoría **Floor Tags** (Etiquetas de
   suelo).
3. *Create → Label*: colocar un label con el parámetro **Mark** (arriba).
4. Otro label DEBAJO con **Thickness** (espesor; con los tipos por sección
   aplicados — botón "Aplicar ESPESOR real" — muestra el espesor real).
   Opcional: añadir al mismo label el parámetro compartido **Seccion_Losa**
   (importarlo del archivo de parámetros compartidos del plugin,
   `%TEMP%\cdcrd_uso_losa_params.txt`, grupo "CDCRD plugin-losas").
5. Guardar como `CDCRD Tag Losa.rfa` **en esta carpeta**.

El botón **"Etiquetar losas (tag Mark + espesor)"** del panel busca la familia
en el modelo, la carga de aquí si falta, borra los tags previos de la familia
en cada planta y coloca un tag por losa en el centroide, verificando
releyendo.

## Pendientes de familias del despacho

- Nervios/bovedillas de losas aligeradas (PRIMIS las tiene): necesarias para
  modelar la geometría 1:1 de las aligeradas.
- Símbolos de armado (ganchos/bastones) si se quiere reemplazar la simbología
  nativa (líneas + notas) del dibujo en planta.
