# Prueba nativa de recuperación GM

Auxiliar opcional para Civil 3D 2027. No se instala con el puente normal.
Compilar `GmRecoveryQa.csproj` y cargar su DLL solamente en la instancia de
prueba. Antes de iniciarla, definir `CDCRD_GM_QA_ROOT` con una carpeta privada.
El DWG activo debe estar directamente en esa carpeta y empezar por
`CDCRD_GM_RECOVERY_`. Usar una copia de un perfil ya verificado.

El comando `CDCRDGMRECOVERYQA` lee `job.json` de esa carpeta y genera un recibo
JSON nuevo. No sobreescribe recibos. Ejemplo con nombre ficticio:

```json
{"action":"audit","output":"before.json"}
```

Acciones:

- `audit`: inventario de entidades, definiciones de bloque, grupos, superficies
  TIN (triangulos y estilos), puntos COGO, grupos de puntos, estilos de
  superficie y capas. Los triangulos se ordenan para comparar su geometria.
- `capture`: exige también `image`, un nombre `.png` nuevo. Usa
  `Document.CapturePreviewImage`; captura el área gráfica, no una ventana de
  Windows ni sus diálogos.
- `fixture`: exige `group` y `body_handle`, obtenidos del inventario actual.
  Verifica que la referencia pertenezca al grupo y que su bloque tenga el mismo
  nombre GM; retira únicamente la referencia de la lista del grupo.
- `restore`: vuelve a añadir esa referencia al mismo grupo.
- `watch_begin` / `watch_end`: observa `Database.ObjectAppended`, sin lanzar
  excepciones en eventos CAD. `watch_end` incluye un nuevo inventario.
- `surface_style_names`: recibe `changes`, lista de pares `from`/`to` para
  renombrar estilos existentes con prefijo `GM - ` o `CDCRD_QA_`. Rechaza
  destinos ocupados. Solo sirve en la copia protegida de pruebas.

Para superficies: obtener primero los nombres previstos con `simular=true`,
comprobar que la simulacion revierte el inventario, y escoger el segundo
estrato de la lista. Renombrar temporalmente su estilo y la plantilla
`GM - Stratum` a nombres QA nuevos; conservar el estilo del primer estrato.
El constructor nativo debe crear la primera superficie antes de fallar al
buscar la plantilla para la segunda. Comparar el inventario completo con el
de la fixture y comprobar los eventos de TIN creados transitoriamente.
Repetir el fallo, restaurar exactamente los dos nombres y comparar con la
linea base. Despues ejecutar el caso correcto, rechazar nombres repetidos,
guardar/reabrir y verificar la geometria. Una peticion de fondo omitido por
GM debe abortar y nunca devolver `completo=true`.

Secuencia: auditar y capturar; preparar la colisión en el segundo sondeo;
auditar; iniciar observación; ejecutar `gm.perfil_sondeos` una vez; detener
observación; exigir igualdad de inventarios y ausencia de objetos nuevos.
Repetir el fallo comprueba que el servicio GM no conserva una transacción
caducada. Restaurar la relación de prueba, comprobarla y ejecutar el render
correcto. Guardar, reabrir y comparar la copia.

Las llamadas `cmd.run` solo encolan el comando: esperar su recibo antes de
cambiar `job.json` o enviar otra operación. Ante un error o timeout, inspeccionar
estado/cola y no reenviar automáticamente. Los casos ficticios de la
documentación no autorizan modificar un dibujo diferente.

El inventario incluye extensiones calculadas por Civil 3D. Un cambio de rango
puede invalidar su caché gráfica: iniciar la prueba sobre una copia recién
abierta, con rango ya establecido y regenerada, y no mezclar pruebas de rango
con la comparación de recuperación.

## Residuos selectivos en 0.5.11

La acción `residues_fixture` crea un grupo vacío y tres definiciones GM identificadas `CDCRD_QA_RESIDUES_`: una sin uso, otra con referencia agrupada y otra con referencia sin grupo. Conservar el recibo `handles`. Probar la vista previa, rechazo de huella caducada/objeto no elegible y eliminación de los dos candidatos seguros. Para retirar los fixtures restantes, borrar únicamente sus handles conocidos (referencias, grupo y definiciones, en ese orden) y comparar el inventario. No limpiar objetos históricos por prefijo.

## Plataformas 0.5.13

`audit` incluye XYZ, cierre, sitio y longitudes de FeatureLine, más cantidades separadas de corte/relleno y superficies base/comparación de TinVolumeSurface.

`platform_volume` es una fixture **sintética fija**: recibe `design` (handle del TIN llamado `CDX QA PLATFORM 0513`), añade un plano Z=100 m de 48 × 32 m en las coordenadas de `humo_plataformas.py` y crea su volumen. Rechaza nombres QA existentes y opera en una transacción. No es una herramienta de cubicación general ni interpreta un terreno de proyecto. Debe usarse después del humo y comparar con 0 m³ de corte y 2474,666666667 m³ de relleno.
