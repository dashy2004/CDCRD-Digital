<h1 align="center">Civil 3D por API</h1>
<p align="center"><strong>Herramientas MCP para Civil 3D 2027 · Misma sesión de trabajo · Evidencia nativa</strong></p>

<p align="center">
  <a href="#instalación"><img src="../docs/assets/nav/instalar.svg" alt="INSTALAR" height="34"></a>
  <a href="#qué-puedes-hacer"><img src="../docs/assets/nav/civil3d.svg" alt="CIVIL 3D" height="34"></a>
  <a href="docs/GALERIA.md"><img src="../docs/assets/nav/galeria.svg" alt="CAPTURAS" height="34"></a>
  <a href="../datos/INDICE.md"><img src="../docs/assets/nav/normativa.svg" alt="NORMATIVA" height="34"></a>
  <a href="#documentación-y-galería"><img src="../docs/assets/nav/docs.svg" alt="DOCUMENTACIÓN" height="34"></a>
</p>

**Entrega 0.5.23 · 90 herramientas MCP.** Incluye catálogo y asignación de partidas de pago, con informes XML/CSV nativos. [Prueba y capturas](docs/PARTIDAS-0523.md) · [Volver a CDCRD-Digital](../README.md).

## Qué puedes hacer

| Flujo | Capacidad y prueba |
|---|---|
| **Terreno y geometría** | [COGO/Survey](../civil3d-points-survey/README.md), [superficies y taludes](../civil3d-terrain-tools/README.md), [ejes y rasantes](docs/SITIO-0512.md), [curvas](docs/CURVAS-0514.md) |
| **Carretera** | [Calzada y capas](docs/CALZADA-0516.md), [cunetas y bermas](docs/CUNETAS-BERMAS-0517.md), [peraltes](docs/PERALTES-0518.md), [espirales](docs/ESPIRALES-0519.md) |
| **Corredor** | [Múltiples baselines y regiones](docs/MULTIBASELINE-0520.md), [targets de ancho y cota](docs/TARGETS-0521.md) |
| **Cantidades** | [Volúmenes TIN y materiales por secciones](docs/QTO-0522.md), [partidas de pago](docs/PARTIDAS-0523.md) |
| **Objetos AutoCAD** | [Operaciones comunes y límites](docs/AUTOCAD-0511.md) |

## Partidas de pago: resultado actual

![Informe de partidas creado en el DWG desde el XML nativo](docs/images/civil3d-partidas-report-0523.png)

La prueba usa 8 entidades sintéticas: puntos, líneas, polilínea, hatch y sólido. El informe confirma **3 EA, 35 M, 200 M2 y 24 M3**. Se verificaron rechazo de entradas inválidas, reversión del lote ante fallo, guardado y reapertura. [Contrato completo](docs/PARTIDAS-0523.md).

| Herramienta | Función |
|---|---|
| `cargar_catalogo_partidas` | Primer catálogo CSV propio; no sustituye otro existente |
| `asignar_partidas_objetos` | Añade partidas a handles explícitos en una transacción |
| `leer_partidas_objetos` | Relee las asignaciones nativas |
| `generar_informe_partidas` | Resumen XML/CSV de todo el dibujo |
| `estado_catalogo_partidas` | Ruta, formato y categorías actuales |

Las unidades pertenecen a cada partida. No se incluyen precios, fórmulas externas, selección parcial del informe ni asignación de partidas a códigos de corredor. Las cubicaciones de materiales siguen disponibles en el [módulo QTO](docs/QTO-0522.md).

## Instalación

Requiere **Windows x64, Civil 3D 2027, SDK .NET 10 y Python 3.10+**. Dependencia MCP: `mcp>=1.10,<2`. Los ensamblados Autodesk se referencian desde la instalación local y no se redistribuyen.

```powershell
.\instalar.ps1 -Probar
.\instalar.ps1 -MostrarRegistroMCP
# Módulos opcionales según el flujo que necesites:
.\instalar-peraltes.ps1
.\instalar-espirales.ps1
.\instalar-corredores.ps1
.\instalar-targets.ps1
.\instalar-qto.ps1
.\instalar-partidas.ps1
```

Los instaladores opcionales compilan y preparan bundles; no abren ni reinician Civil. Para una sesión que aún no tiene el módulo, usan la ruta `NETLOAD` indicada por el instalador. Una DLL ya cargada no se sustituye en caliente. [Instalación y permisos detallados](REFERENCIA.md#instalacion).

## Versiones y ejecución

| Componente | Estado de esta entrega |
|---|---|
| Catálogo MCP Python | 0.5.23, 90 herramientas |
| Módulo de partidas | 0.1.2, `Cdcrd.Partidas.V3`, comando `CDCRDPARTIDASV3` |
| Puente de la sesión de prueba | 0.5.17; se conservó la instancia existente |
| Puente preparado para próximo arranque | 0.5.18; su autocarga sigue pendiente de comprobar |
| Autocarga del módulo de partidas | Preparada; pendiente del siguiente arranque normal |

```text
Cliente MCP → Python por stdio → puente local 127.0.0.1:8760
                              → hilo principal de Civil 3D → API .NET
```

El puente y los módulos comprueban el documento esperado, unidades, permisos y estado de la cola. Las escrituras piden confirmación explícita y ofrecen simulación. Cada operación devuelve un recibo; tras un timeout se inspecciona ese recibo antes de continuar.

## Verificación

```powershell
uv run --with pytest --with 'mcp>=1.10,<2' python -m pytest tests -q
dotnet build modulo-partidas/Cdcrd.Partidas.csproj -c Release
```

**338 pruebas Python** pasan en esta entrega. Las pruebas nativas necesitan Civil 3D y una copia identificada; no se ejecutan en GitHub Actions. [Reproducción de partidas](pruebas/native_partidas_qa/README.md) · [Resultados y límites](docs/PARTIDAS-0523.md).

## Documentación y galería

| Buscar… | Abrir |
|---|---|
| Capturas por función, sin una portada interminable | [Galería](docs/GALERIA.md) |
| Contratos, permisos y operaciones anteriores | [Referencia técnica ampliada](REFERENCIA.md) |
| Diagnóstico y recuperación | [Recuperación GM](docs/RECUPERACION-GM-059.md) |
| Normativa y otras aplicaciones | [CDCRD-Digital](../README.md) |

Las capturas son del área gráfica nativa, sin retoque. Cada informe distingue lo probado, las restricciones y lo pendiente. El resultado de una prueba API no constituye aprobación de un diseño.
