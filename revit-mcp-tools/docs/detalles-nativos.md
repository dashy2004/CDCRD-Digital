# Detalles de losas directamente en Revit

`revit_detalles_losas` crea tres Drafting Views: seccion geometrica, modulacion
bidireccional y coordinacion muro/bovedilla. Usa DetailCurves, Dimensions y
TextNotes editables, sin importar DWG/DXF ni modificar elementos fisicos.
Es una plantilla de generacion JSON, no un archivo RTE ni un calculo estructural.

## Contrato

Anadir las guardas habituales `expected_path`, `protected_paths` (lista de rutas
absolutas), `expected_pid`, `lock_path` y `lock_identity` (owner/session/task).
El archivo de turno debe estar activo y coincidir tambien en process_id.

```json
{
  "action": "inspect",
  "view_prefix": "CDX EJEMPLO DETALLES",
  "text_type_name": "TEXTO GR- 2.00 mm",
  "dimension_type_name": "Dimensiones GR 2.00",
  "geometry": {
    "height_m": 0.25,
    "topping_m": 0.05,
    "block_m": 0.50,
    "rib_m": 0.15,
    "wall_m": 0.15,
    "wall_gap_m": 0.02
  }
}
```

Los numeros son una demostracion geometrica. No prescriben espesor, acero,
recubrimiento, junta, macizado ni capacidad. La separacion del muro es ilustrativa;
su funcion y encuentro real deben resolverse en cada proyecto. No usar esta
vista como seccion asociada a un pano real: Drafting Views no muestran el modelo.

1. Ejecutar `inspect`: devuelve geometria, digest y colisiones de nombres.
2. Guardar y respaldar la copia, preservar cualquier cambio previo del usuario.
3. Reenviar la misma configuracion con `action=apply` y `expected_digest`.
4. Verificar IDs, cotas, formato visible, inventario fisico y advertencias.
5. Guardar mediante API tras la verificacion; exportar y leer PNG/PDF.

La transaccion rechaza fallos y revierte el grupo si cambian las advertencias.
Necesita al menos 512 MB libres y no crea mas que tres vistas acotadas. Se reutiliza
el TextNoteType GR exacto; se duplica el DimensionType GR indicado y se fija
su formato en metros (precision 0.001). No altera los tipos originales.
La creacion no guarda automaticamente. Tras un timeout, inspeccionar nombres y
estado nativo antes de reintentar: no hay reintentos de escritura en transporte.
Si existe un nombre, `apply` rechaza el lote; `inspect` sigue disponible.
No hay actualizador automatico ni edicion/reemplazo de vistas existentes.

## Validacion y limites

- Tests puros: medidas, hueco bajo bovedilla, limites, valores no finitos,
  digest, PID/turno y rechazo de originales incluso con configuracion mal formada.
- Aceptacion nativa en copia Revit 2027: tres vistas, 66 lineas, 13 textos, 6 cotas;
  cotas internas y unidades comprobadas, PDF de tres paginas inspeccionado.
- El dibujo no genera cantidades; contar los EPS fisicos con `revit_eps_tabla`.
- Una tabla heredada hecha con textos necesita reconstruirse como ViewSchedule
  para vincular cantidades/estado. No se convierte automaticamente aqui.
- Los detalles de barras/anclajes requieren cargas, materiales, apoyos,
  recubrimientos y reglas aprobadas. No se copian armados heredados a este piloto.

## Transporte y recarga MCP

El POST usa `application/json; charset=utf-8`, igual que el puente Python.
`text/plain` puede dejar `request.data` como bytes y producir `bytes.get`/HTTP500.
Los errores HTTP se devuelven sin `code_attempted` ni traceback; no se reintentan.
`GET /routes/status` comprueba transporte, no ejecucion nativa.

Al agregar wrappers, reiniciar el servidor MCP desde el cliente. Una sesion stdio
nueva con la configuracion desplegada permite probar catalogo y llamadas reales;
no demuestra que un chat ya abierto haya recargado su proceso. Registrar ambos
estados por separado. No es necesario reiniciar Revit para cargar este modulo.

Referencias API: [ViewDrafting.Create](https://help.autodesk.com/cloudhelp/2026/ENU/Revit-API-MainReference/files/html/93dbfef8-b014-3912-124d-812c10b8ebdb.htm),
[DetailCurve](https://help.autodesk.com/cloudhelp/2024/ENU/Revit-API/files/Revit_API_Developers_Guide/Revit_Geometric_Elements/Annotation_Elements/Revit_API_Revit_API_Developers_Guide_Revit_Geometric_Elements_Annotation_Elements_Detail_Curve_html.html).
Sobrecargas y formato de cotas cotejados con RevitAPI.xml instalado 2027.

## Siguiente desarrollo de la biblioteca

| Contenido | Representacion apropiada | Condicion para automatizar |
| --- | --- | --- |
| Bovedillas, nervios, topping y macizados | Geometria 3D y secciones del modelo | Seccion y encuentros comprobados |
| Refuerzo | Rebar 3D, etiquetas y despiece | Calculo, apoyos, anclajes y recubrimientos validados |
| Esquemas de distribucion y condiciones de borde | Drafting Views o componentes de detalle | Parametros y significado de los ejes explicitos |
| Cantidades | ViewSchedule | Instancias individuales, filtro y membresia verificada |
| Tablas historicas dibujadas con textos | Referencia documental | Reconstruir desde datos; no tratarlas como cantidades vivas |

La siguiente fase debe separar el detalle generico de cada instancia vinculada
a un elemento: guardar revision de entradas, unidades, estado de validacion y
digest, detectar cambios del modelo y actualizar solo los objetos propios.
La herramienta actual crea una primera plantilla; no proporciona todavia esa
sincronizacion, una biblioteca RTE completa ni un diseno de refuerzo aprobado.
