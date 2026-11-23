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

## Archivos

| Archivo | Qué hace |
|---|---|
| `generar.py` | Motor: `data.json` + `memoria.json` → Word. |
| `fuentes_losas.py` | Lee el listado `.TXT` de Losas.exe (v5.x) y el archivo de datos `.DL`. |
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
                 base, drift, shear, modal, col, beam, joint, msgs, unidad_long
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

- Lectores incluidos: solo losas (`.TXT` y `.DL`). Los capítulos de bloques de ETABS se
  generan si `data.json` trae `bloques`, pero este paquete aún no incluye el lector que los
  produce desde un modelo abierto.
- `generar.py` es un solo archivo largo; pendiente de dividir en módulos.
- `word_pdf.ps1` requiere Microsoft Word en Windows.

## Origen

El lector de Losas.exe sigue el criterio de `TxtParser.cs` de MemoriaPlus
([EstructurasRD](https://github.com/dashy2004/EstructurasRD), rama `archive/dotnet-suite`,
MIT). El sistema de ejemplo viene de los fixtures de ese mismo repositorio.
