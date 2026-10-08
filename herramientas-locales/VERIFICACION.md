# Verificación local — 2026-10-08

Instalación comprobada en Windows con Python 3.13.15 y uv 0.12.5.
El archivo `uv.lock` fija las dependencias del entorno aislado.

## Resultado

- `instalar.ps1 -Pruebas`: finaliza correctamente; diagnóstico de los 11
  paquetes principales y SQLite FTS5 satisfactorio.
- Pytest: **45 pruebas aprobadas en 5.63 s** durante la ejecución del instalador.
- Ruff: sin incidencias en `src/` y `tests/`.
- MCP stdio: inicialización y listado real de **10 herramientas**; búsqueda,
  generación DXF, rechazo de entradas/salidas fuera de las carpetas permitidas
  y preservación de archivos existentes comprobados con un cliente del SDK.

## Cobertura y muestras

| Grupo | Pruebas | Evidencia |
|---|---:|---|
| CAD | 21 | DXF nativo en metros/milímetros, cotas, polígonos inválidos, auditoría, previews y salidas exclusivas |
| IFC/IDS | 12 | IFC sintético real, unidades SI/conversión, propiedades requeridas, elementos ausentes, versión incompatible e informes HTML |
| PDF | 6 | PDF real, texto/medidas, PNG con tamaño esperado, páginas/DPI inválidos y limpieza tras error de codificación |
| Integración | 6 | Procedencia, IDs entre volúmenes, Unicode cp1252, cumplimiento/no cumplimiento de masa modal y MCP stdio |

Además de las pruebas, se generó `planta-ejemplo.json` como DXF R2018 con
3 polilíneas, 2 cotas nativas y 2 notas. Su auditoría informó cero errores y
cero reparaciones. Se generaron previews PNG/PDF y una página PNG desde el
PDF; se revisó visualmente la versión de fondo blanco. Las medidas ilustradas
son 6 × 4 m. Estos archivos quedan bajo `salidas/`, excluida de Git.

Una consulta real `2.10.11 --volumen 1` recuperó la cláusula de derivas,
páginas 95–96, en `datos/titulos/T02.json`. El ejemplo de masa modal con
SumUX=0.93 y SumUY=0.94 produjo CUMPLE mediante el script existente.

Durante la integración se observó un bloqueo al importar CAD/NumPy después
de iniciar el transporte stdio en Windows. Cargar CAD al iniciar el servidor
resolvió el caso y la prueba de extremo a extremo pasó.

## Versiones principales instaladas

| Componente | Versión |
|---|---|
| ezdxf | 1.4.4 |
| IfcOpenShell / IfcTester / IfcClash | 0.9.0 |
| Matplotlib | 3.11.2 |
| MCP Python SDK | 1.30.0 |
| pdfplumber | 0.11.10 |
| pypdfium2 | 5.14.0 |
| Pydantic | 2.14.0 |
| Pint | 0.26.1 |
| Shapely | 2.2.0 |

## Límites de lo comprobado

No se ejecutaron sesiones de Revit/ETABS/SAFE ni conversiones DWG/RVT.
No se abrió el ejemplo en AutoCAD/LibreCAD; queda pendiente verificar allí
tipografías, presentación y escala de entrega. IDS valida la información
especificada, no el diseño estructural. El verificador normativo ensayado en
integración fue masa modal; los demás adaptadores conservan los scripts
existentes y requieren sus propios casos de aceptación.

Los ensayos usan ejemplos sintéticos, sin documentos ni modelos de clientes.
No incluyen medición de rendimiento en proyectos grandes ni evaluación de
un modelo de IA. El fragmento MCP local se generó; activarlo en un cliente
concreto requiere incorporar su entrada a la configuración de ese cliente.
