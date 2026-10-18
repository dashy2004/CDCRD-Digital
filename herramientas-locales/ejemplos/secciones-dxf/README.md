# Esquemas DXF de secciones y pórtico (ejemplo ficticio)

Ejemplo reproducible de generación de dibujo CAD por código: tres secciones de
columna con armadura y un pórtico tipo de tres niveles, en cuatro archivos
`.dxf` que se abren y se editan en AutoCAD, Civil 3D o cualquier CAD que lea
DXF R2010.

La geometría es **ficticia e ilustrativa**: no corresponde a ningún proyecto,
no proviene de un cálculo y no sustituye una verificación normativa.

## Qué produce

```powershell
python .\herramientas-locales\ejemplos\secciones-dxf\generar_secciones.py
```

| Archivo | Contenido | Entidades |
|---|---|---|
| `salidas/seccion_C1.dxf` | Columna 35 × 35 cm, 12 barras No. 6 | 47 |
| `salidas/seccion_C2.dxf` | Columna 40 × 40 cm, 14 barras No. 6 | 52 |
| `salidas/seccion_C3.dxf` | Columna 40 × 45 cm, 16 barras No. 6 | 57 |
| `salidas/portico.dxf` | Pórtico de 3 niveles × 310 cm, 4 columnas | 68 |

## Cómo está armado el dibujo

- **Unidades**: centímetros. `$INSUNITS = 5`, `$MEASUREMENT = 1`; 1 unidad de
  dibujo = 1 cm. Las cotas se escriben con un decimal y separador `.`.
- **Capas**: `HORMIGON` (contorno), `ESTRIBO` (estribo discontinuo), `ACERO`
  (barras), `COTAS`, `TEXTO`, `EJES`.
- **Estribo con espesor real**: dos polilíneas separadas el diámetro de la
  barra (No. 3, Ø 0,953 cm), con dobleces redondeados mediante *bulge* —radio
  interior 2 db— y gancho a 135° de longitud 6 db ≥ 7,5 cm.
- **Barras**: `CIRCLE` + sombreado sólido en una retícula perimetral. El centro
  de barra queda a `recubrimiento + Ø estribo + Ø barra / 2` de la cara.
- **Cotas**: `DIMENSION` nativas con un estilo propio (`ESQ`). El renderizador
  de ezdxf escribe la línea de cota y las líneas de extensión en la capa `0`,
  por eso el estilo fija `dimclrd`, `dimclre` y `dimclrt`.

Los parámetros de cada sección (ancho, peralte, número de barras por cara) están
en el diccionario `SECCIONES` del script; cambiarlos regenera el dibujo completo
con sus cotas.

## Alcance y límites

- Sin cajetín, sin láminas de presentación y sin despiece de armadura: el
  resultado es un esquema acotado, no un plano de taller.
- El script usa **ezdxf** directamente, la misma biblioteca de la operación
  `generar-dxf` de la CLI, pero no pasa por ella: el esquema JSON de
  `planta-ejemplo.json` describe polígonos, cotas y notas, y no incluye círculos
  ni sombreados.
- Las imágenes de
  [`../../docs/images/`](../../docs/images/) son vistas directas de estos mismos
  `.dxf`, dibujadas con ezdxf y Matplotlib, sin rótulos ni montaje añadidos. Hay
  una versión clara y una oscura de cada una para que el README se lea bien en
  los dos temas de GitHub. **No son capturas de AutoCAD.**
- Verificación aplicada: relectura de cada archivo con `ezdxf.readfile` y
  recuento de entidades por capa; los números de la tabla anterior son esos
  recuentos.

Asistencia de código y documentación de este ejemplo: Claude. Procedimiento
reproducible con Claude o Codex.
