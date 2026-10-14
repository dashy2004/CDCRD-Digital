# Dibujo de entidades en Civil 3D

Dos herramientas del servidor MCP para **crear geometría** en el dibujo activo sin
escribir AutoLISP a mano y sin los límites del envío por línea de comandos.

## Por qué existen

El puente .NET no expone un RPC de creación de entidades, así que la vía disponible
era `ejecutar_comando` con `entmake`/LISP por `cmd.run`. Esa vía tiene dos límites
reales, comprobados en Civil 3D 2027:

- **Longitud:** la línea de comandos de AutoCAD corta alrededor de **256 caracteres**;
  un `entmake` largo se trunca y deja a AutoCAD esperando entrada (cuelga la cola).
- **Codificación:** un `.lsp` leído por AutoCAD usa la **página ANSI** del sistema. Un
  archivo con `ñ`/acentos escrito como UTF-8 se lee mal y rompe rutas y textos.

Como el servidor MCP corre en la misma máquina que Civil 3D (se conecta a
`127.0.0.1:8760`), puede escribir un `.lsp` temporal local en ANSI (`cp1252`) y pedir
a Civil 3D que lo cargue con `(load ...)`. Eso elimina ambos límites.

## `ejecutar_lisp(codigo, confirmar=True)`

Ejecuta AutoLISP de cualquier longitud. Escribe `codigo` en
`%TEMP%\cdcrd_lisp\cdcrd_*.lsp` (ANSI) y lo carga con `(load ...)`. Limpia los
temporales de más de 10 min sin tocar el recién creado.

- Requiere `CDCRD_C3D_PERMITIR_COMANDOS=1` en el entorno de Civil 3D y `confirmar=True`
  (token de aprobación de un solo uso, como toda escritura).
- **Asíncrono:** el efecto se verifica con una consulta posterior (`consultar_objetos`).
- No sirve para código que abra **diálogos modales** (dejan el puente colgado hasta
  cerrarlos) — p. ej. `PLOT`/`PlotToFile`.

## `crear_entidades(entidades, confirmar=True)`

Recibe una **lista JSON** de entidades y genera el `entmake` por ti. Tipos y campos
(alias en inglés aceptados: `layer`, `line`, `polyline`, `text`, `circle`, `solid`,
`point`):

| tipo | campos |
|---|---|
| `capa` | `nombre`, `color` (ACI 1–255, def. 7) |
| `linea` | `capa`, `p1`, `p2` |
| `polilinea` | `capa`, `puntos` (≥2), `cerrada` (bool), `ancho` (opcional) |
| `texto` | `capa`, `punto`, `altura`, `texto`, `rotacion`, `centrado` (bool) |
| `circulo` | `capa`, `centro`, `radio` |
| `solido` | `capa`, `p1`, `p2`, `p3`, `p4` (def. = `p3`) |
| `punto` | `capa`, `punto` |

Los puntos son `[x, y]` o `[x, y, z]`. Incluye las **capas** que uses **antes** que las
entidades en la misma lista. Sin `confirmar=True` devuelve el conteo y un adelanto del
LISP; con él, carga el dibujo (asíncrono, verifícalo luego).

Ejemplo (lote rojo + rótulo centrado):

```json
[
  {"tipo":"capa","nombre":"UBIC-LOTE","color":1},
  {"tipo":"polilinea","capa":"UBIC-LOTE","puntos":[[0,0],[100,0],[100,60],[0,60]],"cerrada":true,"ancho":1.0},
  {"tipo":"texto","capa":"UBIC-LOTE","punto":[50,30],"altura":3,"texto":"SOLAR","centrado":true}
]
```

## Pruebas

`src/dibujo.py` son funciones puras (sin CAD ni puente). Contrato en
`tests/test_dibujo.py`:

```console
py -m unittest discover -s tests -v
```

La ejecución real en Civil 3D (crear entidades, verificar con `consultar_objetos`) se
reporta aparte, como pide `CONTRIBUTING.md`.

## Límite conocido: exportar a imagen/PDF

El ploteo de Civil 3D (`-PLOT`/`PlotToFile`) abre diálogos modales que el puente no
cierra, así que no hay una herramienta de export fiable por esta vía. La ruta
comprobada es **volcar la geometría** y renderizar fuera de Civil 3D.
