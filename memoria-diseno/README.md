# memoria-diseno — motor de memorias de cálculo estructural

Arma una memoria de cálculo en Word (y PDF) con formato de informe técnico: portada, hoja
de control con revisiones y firmas, índice, tablas y figuras numeradas por capítulo.

No necesita un asistente de IA para funcionar: es un programa determinista. Las mismas
entradas producen el mismo documento.

Trabaja con dos archivos:

- `data.json` — **los números**. Lo producen los lectores de fuentes; no se edita a mano.
- `memoria.json` — **lo editable**: portada, responsable, hoja de control, revisiones,
  firmas, datos del proyecto, materiales, normas, vistas, fundaciones, figuras de anexo y
  observaciones. Se crea con campos vacíos la primera vez; los campos vacíos se omiten.

El motor no contiene datos de ningún proyecto.

## Uso

```powershell
pip install -r requirements.txt

# 1. Datos desde las fuentes reales de losas (listado .TXT de Losas.exe y, opcional, el .DL)
python armar_datos.py ejemplo\fuentes.json salida\data.json

# 2. Documento (se crea salida\memoria.json si no existe; edítelo y repita este paso)
python generar.py salida\data.json "" salida\memoria.docx salida\tmp salida\imagenes salida\memoria.json

# 3. Índice actualizado y PDF (requiere Microsoft Word)
.\word_pdf.ps1 -Docx (Resolve-Path salida\memoria.docx) -Pdf "$PWD\salida\memoria.pdf"
```

Sin el paso 3 el documento se abre igual; Word actualiza el índice al aceptar el aviso de
campos, o con clic derecho sobre el índice → *Actualizar campo*.

## Fuentes directas: ETABS, SAFE y Excel

`fuentes.json` declara de dónde sale cada parte. Las rutas pueden ser absolutas o relativas
al manifiesto:

```json
{
  "niveles": [ {"nombre": "Nivel 1", "txt": "nivel-1.TXT", "dl": "nivel-1.DL"} ],
  "cargas": {"libro": "cargas-y-espesores.xlsx"},
  "bloques": [ {"nombre": "Bloque A", "etabs": "bloque-a.EDB",
                "espectro": "bloque-a-espectro.xls", "art38": "bloque-a-art38.xls"} ],
  "fundaciones": {"safe": "fundaciones.FDB"}
}
```

Con `cargas`, cada nivel toma las hojas «Espesor <nombre>» y «Carga <nombre>» del libro. Si
se llaman de otro modo, el nivel las indica con `"hoja_espesor"` y `"hoja_carga"`; con
`"sin_hojas": true` el nivel se deja sin ellas.

Los modelos **nunca se abren en su sitio**: cada lector copia el archivo a `_trabajo`, arranca
una instancia propia del programa, corre el análisis sobre la copia y la cierra. Si ETABS o
SAFE ya están abiertos con otro trabajo, no se tocan. El esfuerzo admisible del suelo para
comparar presiones se indica en `memoria.json` (`fundaciones.esfuerzo_admisible_ton_m2`), y
`fundaciones.combinaciones` limita la tabla de presiones a las combinaciones que se nombren
(por ejemplo `["Comb2", "Envelope"]`); sin esa clave salen todas las de servicio y las
envolventes.

Las tablas de secciones del modelo solo listan las que están asignadas a algún elemento. Los
subtítulos de tercer nivel se numeran bajo su título (4.5.1, 4.5.2…) y no entran al índice.

## Uso desde LosasPlus

LosasPlus ([EstructurasRD](https://github.com/dashy2004/EstructurasRD), rama
`archive/dotnet-suite`) llama a este motor desde su botón «Generar memoria»: escribe junto
al proyecto una carpeta `<proyecto>-memoria` con `data.json` y `memoria.json` (este último
solo la primera vez, para no pisar lo que se haya editado), ejecuta `generar.py` y abre el
Word. Para que lo encuentre:

```powershell
# 1. Entorno propio del motor, con sus dependencias (una sola vez)
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# 2. Decirle a LosasPlus dónde está el motor (una sola vez; reiniciar LosasPlus después)
[Environment]::SetEnvironmentVariable("MEMORIA_DISENO_DIR", (Get-Location).Path, "User")
```

Sin esa variable, LosasPlus busca una carpeta `memoria-diseno` junto a su ejecutable o en
sus carpetas superiores; si no la encuentra, abre MemoriaPlus como antes.

## Archivos

| Archivo | Qué hace |
|---|---|
| `generar.py` | Motor: `data.json` + `memoria.json` → Word. |
| `fuentes_losas.py` | Lee el listado `.TXT` de Losas.exe (v5.x) y el archivo de datos `.DL`. |
| `fuentes_excel.py` | Lee las hojas de espectro, cuasiestático y Art. 38 de un bloque (`.xls` o `.xlsx`), buscándolas por sus rótulos. |
| `fuentes_cargas.py` | Lee el libro de cargas y espesores de losa: cuantificación de sobrecarga y las hojas «Espesor …» y «Carga …» de cada nivel; avisa de lo que no cuadra con el listado de diseño. |
| `fuentes_etabs.py` | Abre una copia del modelo en ETABS, corre análisis y diseño y lee sus tablas en tonf y metros. |
| `muros_ui.py` | Pulsa *Design → Shear Wall Design → Start Design/Check* en la instancia de ETABS de la lectura (la API no tiene ese comando) y espera a que termine. |
| `cruce_mivhed.py` | Cruza la memoria con el checklist de Estructura del MIVHED (`CHECK-ESTRUCTURA`): estado, nota y motivos de incumplimiento por ítem, en Markdown o como anexo de la memoria. |
| `fuentes_safe.py` | Abre una copia del modelo de fundaciones en SAFE y lee presiones de suelo, punzonado y franjas. |
| `armar_datos.py` | Junta las fuentes declaradas en un `fuentes.json` en un `data.json`. |
| `word_pdf.ps1` | Abre el Word, actualiza el índice y exporta a PDF. |
| `ejemplo/` | Sistema de demostración de 27 losas (`.TXT` y `.DL`) y su `fuentes.json`. |

## Lo que se edita en `memoria.json`

| Clave | Para qué |
|---|---|
| `portada` | Título, subtítulo, alcance, imagen de portada, logo, lugar y fecha. |
| `responsable` | Nombre, credencial profesional, contacto, diseño. |
| `control` | Código, revisión, fecha, estado, origen de los datos y `marca_de_agua`. |
| `revisiones` | Filas del registro de revisiones. |
| `firmas` | Rol, nombre, credencial e `imagen` (firma escaneada) de cada firmante. |
| `proyecto`, `materiales`, `normas` | Tablas y lista del capítulo 1. |
| `vistas_bloque` | Imagen del modelo que abre el capítulo de cada bloque. |
| `fundaciones` | Texto y figuras del capítulo de fundaciones. |
| `anexo_figuras` | Planos y vistas; sin `ruta` queda un espacio reservado con su rótulo. |
| `observaciones_extra`, `observaciones_omitir` | Añadir o quitar puntos del capítulo de observaciones. |
| `checklist_mivhed` | Ruta al JSON de checklists del corpus (`corpus-mivhed-checklists/data/mivhed-norm-checklists.json`); agrega el anexo del cruce con el checklist de Estructura. |

Las rutas de imagen pueden ser absolutas o relativas a la carpeta de imágenes o a la de
`memoria.json`.

### Marca de agua

`control.marca_de_agua` pone un texto en diagonal en todas las páginas (por defecto
`"BORRADOR"`). Para emitir el documento se deja en `""`. Es la misma marca de agua de Word,
así que también se quita o cambia desde *Diseño → Marca de agua*.

### Firma

Cada firmante tiene una línea con espacio libre para firma y sello. Si se indica
`firmas[i].imagen`, la firma escaneada se coloca sobre esa línea. **La imagen de una firma
solo debe ponerla su titular**, sobre un documento que ya revisó; por eso el valor por
defecto es vacío y el documento nace como borrador.

### Seguir editando en Word

El `.docx` es un documento normal:

- Los títulos usan los estilos *Título 1, 2 y 3*; cambiar el estilo cambia todos a la vez.
- El índice se actualiza solo (*Referencias → Actualizar tabla*).
- Encabezado y pie se editan con doble clic; el pie lleva «Página X de Y» automático.
- Las tablas son tablas de Word; se pueden pegar valores desde Excel.
- Para proteger el documento emitido: *Revisar → Restringir edición*, o exportar a PDF.

Lo que se cambie a mano en Word se pierde al regenerar. Lo que deba sobrevivir va en
`memoria.json`.

## Contrato de `data.json`

```
referencia_pdf   bool    true si los datos vienen de una memoria ya emitida en PDF (se citan sus páginas)
sobrecarga       lista   hojas de cuantificación: titulo, espesores, pesos, vivas, resumen   (puede ir vacía)
niveles          lista   un elemento por nivel de losas
  nombre, fuente, paginas
  meta           sistema, archivo, version, reglamento, fc, fecha
  esp            {losa: Lx, Ly, cond, h}             espesor adoptado
  carga          {losa: qu, ...}                     carga última
  mom            {losa: tipo, q, H, Lx, Ly, Mfx, Mfy, Msx, Msy}
  ax, ay         {losa: d, Mu, As, barra, Asd}       armadura de vano
  apx, apy       [ {i, j, Mu, DAs, barra, ...} ]     armadura sobre apoyos
bloques          lista   un elemento por modelo de ETABS   (puede ir vacía)
  nombre, paginas
  espectro, tabla_espectro, torsion, art38, cuasi          hojas de cálculo
  etabs          stories, frame, area, patterns, loadsets, mass_story, auto_seis, cases, combos,
                 base, drift, shear, modal, col, beam, joint, msgs, unidad_long,
                 muros (null sin pilas; si no: estado, motivo | codigo, preferencias, combinaciones,
                        pilas {pila: secciones, niveles, L, t, dc, dc_nivel, av, cortante, estaciones,
                        mensajes}, sin_diseno, sin_asignar, sin_pila)
```

Un lector nuevo (ETABS o SAFE en vivo con los servidores MCP de este repositorio, una hoja
de cálculo, el proyecto de otra aplicación) solo tiene que producir estas claves;
`generar.py` no cambia.

## Pruebas

```powershell
pip install pytest
python -m pytest tests -q
```

## Limitaciones

- Los lectores de ETABS y SAFE necesitan el programa instalado en la misma máquina (probado
  con la versión 23.3) y tardan minutos: corren el análisis. Lo leído queda en `_trabajo` y
  se reutiliza mientras el modelo no cambie.
- Un modelo guardado con una versión anterior se recalcula con la instalada; el documento lo
  deja dicho en sus observaciones. `"diseno_guardado": true` conserva el diseño tal como se
  guardó.
- El diseño de muros se dispara por la interfaz de ETABS (UI Automation), porque ETABSv1 23
  no tiene `StartDesign` para muros: necesita una sesión de escritorio con la ventana de ETABS
  visible. Si falla, el bloque se lee igual y la memoria dice por qué falta ese diseño. Se
  diseña siempre sobre el análisis recién corrido, también con `"diseno_guardado": true`.
- Sin lector todavía: las dimensiones en planta de las zapatas.
- El cruce con el MIVHED evalúa por reglas lo que el motor lee; no revisa planos (ítems 2, 3 y
  14 a 29), no verifica derivas contra el límite del R-001 y sus estados son una ayuda para el
  ingeniero, no la evaluación oficial. Las reglas siguen la versión 1.0-draft del checklist.
- `generar.py` es un solo archivo largo; pendiente de dividir en módulos.
- `word_pdf.ps1` requiere Microsoft Word en Windows.

## Origen

El lector de Losas.exe sigue el criterio de `TxtParser.cs` de MemoriaPlus
([EstructurasRD](https://github.com/dashy2004/EstructurasRD), rama `archive/dotnet-suite`,
MIT). El sistema de ejemplo viene de los fixtures de ese mismo repositorio.
