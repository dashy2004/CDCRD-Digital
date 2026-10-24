# Documentacion de una planta de losas existentes

`revit_documentar_losas(config)` ejecuta fases separadas dentro de una **copia**:
`inspect`, `views`, `annotate`, `schedule`, `sheets`, `layout`, `align`, `refine`.
`exportar_pdf` se ejecuta despues y el PDF se rasteriza/revisa antes de entregar.

La configuracion es privada y especifica de cada documento: `expected_path`,
`expected_pid`, `protected_paths`, `lock_path`, `lock_identity` (owner/session/task),
`floor_ids`, `trial_ids`, `inherited_reference_authorized`, `receipt_path`,
`min_free_mb` (minimo 1000), `prefix` CDX: y `view_prefix` CDX seguido de espacio.
Requiere turno exclusivo externo; comprobarlo antes de encolar cualquier llamada.

Cada `plan_views` declara name, bounds_m=[xmin,ymin,xmax,ymax], scale y role
(`scheme` o `reinforcement`). Cada losa debe aparecer exactamente una vez por
rol. Las cajas se usan para composicion grafica, nunca para calcular luces.
Las `sections` declaran name, origin_m, right/up/direction, bounds_m y scale.
`sheets` contiene number/name, con `titleblock_id` existente.
`layout` contiene sheet/view/paper_mm y scale; `sheet_notes` contiene
sheet/paper_mm/text/size/width_mm. Todas las posiciones de papel usan milimetros.

Reutiliza `vistas_planta`, `acero_losas_plano` y `exportar_pdf`. Los tags leen la
familia `Mark+H` o `tag_type` indicada. La tabla lee campos del modelo, no un
CSV dibujado. `CDX_Estado_Armado` distingue referencia heredada de ensayo.
El espesor de tabla procede del parametro **de tipo nativo**, seleccionado por
BuiltInParameter al refinar; verificar que coincide con el espesor real de cada
instancia. No confiar en un parametro compartido llamado "Thickness".

## Alcance

No crea acero fisico ni calcula/disena. El plano muestra Acero_X/Y/Apoyo
existentes. Las lineas indican direcciones, no longitudes, anclajes o empalmes.
La conversion de separacion a cm solo acepta sintaxis conocida `#n @ 0.xx`.
Otros textos se conservan; no se infieren unidades ambiguas.
Los Rebar de los ensayos se muestran en cortes sin alterar su geometria.
No elimina elementos del modelo, vistas o tags anteriores.

Cada fase usa TransactionGroup con rollback si falla. Crear con nombres
existentes se rechaza para no duplicar: consultar `inspect` y continuar en la
fase pendiente. `align` usa XY del centro; el Z de papel no decide ajustes.
`refine` limita correcciones a vistas del namespace del piloto.
No se fuerza Document.Regenerate en modelos con importaciones pesadas.

## Verificacion y fallos aprendidos

- Guardar antes de avanzar a CSI. Reabrir una copia de control de los bytes
  guardados; comparar geometria/parametros previos, IDs, etiquetas e imports.
- El recuento de warnings debe conservarse; esto no demuestra ausencia de
  interferencias existentes ni aprobacion de diseno.
- `DisplayStyle.HLR`, no `HiddenLine`, en Revit 2027.
- IDs devueltos por GetAllViewports ya son ElementId; no convertir con Int64.
- UseDefault debe ser false antes de editar FormatOptions.
- ISO_A1 y ARCH_D son enums diferentes: el exportador solo antepone ISO_ a A0-A9.
- Un fallo posterior al commit no implica rollback de lo ya confirmado. Leer
  recibos y estado antes de repetir una fase.
- La tabla inicial busca nombres de campos en ingles: localizaciones distintas
  requieren adaptacion; no se sustituye automaticamente un campo desconocido.

Probado con el nucleo IronPython cargado en Revit 2027: plantas, tags/notas,
cortes, tabla, hojas, PDF nativo, guardado y reapertura. La instalacion/recarga
del servidor MCP es una etapa distinta; el transporte HTTP existente se conserva.
