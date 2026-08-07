# CDCRD Digital — Esquema de datos

Doble capa sobre la misma fuente. La capa `humana` conserva el texto legal integro y citable;
la capa `machine` extrae los parametros que un motor de calculo consume directo.

## Capa 1 — Clausulas (`datos/titulos/T<NN>.json`)

Unidad atomica: la clausula numerada del codigo (`2.10.3.2.1`). Un JSON por titulo.

```json
{
  "titulo": 2,
  "nombre": "Cargas Minimas para Analisis y Diseño Estructural",
  "tomo": 1,
  "version_codigo": "2026-07",
  "clausulas": [
    {
      "id": "2.10.3.2.1",
      "capitulo": "2.10",
      "encabezado": "EXCEPCION",
      "texto": "...texto integro de la clausula...",
      "paginas": [58],
      "flags": { "formula": true, "tabla": false, "vision_ok": false },
      "refs": { "internas": ["2.10.3.2"], "externas": ["ASCE/SEI 7"] },
      "tablas": [],
      "formulas": []
    }
  ]
}
```

Reglas:
- `texto` se conserva tal como extrae el parser; si `flags.formula` es true, las formulas
  dentro del texto pueden tener glifos corruptos y NO deben citarse hasta `vision_ok: true`.
- `tablas[]` y `formulas[]` se llenan solo por el pase de vision (Fable 5 leyendo la pagina
  renderizada). `vision_ok` marca que ese contenido ya es confiable.
- `refs.externas` usa nombres canonicos: `ACI 318`, `ASCE/SEI 7`, `ANSI/AISC 360`, `AISI S100`,
  `ASTM`, `AWS`, `NDS`, `TMS 402`. Sin numero de año salvo que la clausula lo fije.

## Capa 2 — Parametros de maquina (`datos/machine/*.json`)

Lo que ETABS (via MCP `fea`), EstructurasRD u otra IA consume sin leer prosa. Cada valor
lleva su clausula de origen — trazabilidad legal completa.

```json
{
  "parametro": "clasificacion_sitio",
  "fuente": { "clausula": "2.7.x", "tomo": 1, "paginas": [37, 38] },
  "unidades": { "Vs": "m/s", "N": "golpes", "Su": "kPa" },
  "valores": [
    { "clase": "C", "Vs_min": 360, "Vs_max": 760, "N_min": 50, "Su_min": 98 }
  ]
}
```

Archivos machine previstos (se llenan por vision + validacion contra Excel de Emil):
- `cargas_vivas.json` — sobrecargas de uso por ocupacion (tabla del T2)
- `cargas_muertas.json` — pesos de materiales
- `sitio_clasificacion.json` — clases de sitio A-E
- `espectro_parametros.json` — Ss, S1, Fa, Fv, TL por zona/municipio si el codigo los tabula
- `sistemas_estructurales.json` — R, Cd, Omega0, limites de altura por sistema
- `combinaciones.json` — combinaciones de carga LRFD/ASD
- `derivas_limites.json` — limites de deriva por categoria

## Por que este diseño ahorra tokens

Una IA que necesita "el R de un portico especial de hormigon" carga
`machine/sistemas_estructurales.json` (unos cientos de tokens) en vez de 90 paginas del T2.
La clausula de origen viaja con el valor, asi que la cita legal no se pierde al comprimir.

## Flujo con ETABS (MCP fea)

```
usuario: "portico 3 niveles, oficina, sitio C, Santo Domingo"
  -> machine/cargas_vivas.json        (sobrecarga oficinas)
  -> machine/espectro_parametros.json (Ss, S1, Fa, Fv)
  -> machine/sistemas_estructurales.json (R, Cd)
  -> calculo del espectro y combinaciones
  -> mcp fea: crear geometria + (futuro) definir casos de carga
  -> memoria de calculo citando clausula por clausula
```
