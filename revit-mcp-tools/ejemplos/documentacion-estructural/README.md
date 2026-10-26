# Perfil documental de ejemplo

`perfil-documentacion.json` es una especificación de presentación. Los nombres
DEMO son ficticios; no contiene diseño ni geometría de un edificio real.
**No hay un runner que lea este perfil completo.** Solo `parametros_laminas`
representa el objeto de parámetros de la herramienta `revit_laminas`.

Antes de usar ese objeto:

1. Leer [el estándar](../../../docs/ESTANDAR-PLANOS-REVIT.md).
2. Crear/cargar una familia de cajetín propia y reemplazar su nombre en el perfil.
3. Medir su área útil y ajustar márgenes, columna reservada y franja de detalles.
4. Crear las dos vistas del ejemplo y asignar sus plantillas y escalas por separado.
5. Mantener `dry_run=true` para comprobar nombres y disponibilidad. Este modo no
   coloca vistas y no demuestra que la composición quepa.
6. Ejecutar la colocación en una copia cuando corresponda al encargo; inspeccionar
   la hoja y el PDF antes de extender el procedimiento.

La plantilla de detalle a 1:20 se configura en su vista. `auto_scale=false`
conserva esa escala; la lista automática de `laminas` no contempla 1:20.
La familia ficticia y las vistas no se distribuyen como RFA/RTE/RVT en este ejemplo.

Los tamaños de texto, pesos y plantillas son propuestas de arranque. La familia
de cajetín y su validación nativa siguen pendientes.
