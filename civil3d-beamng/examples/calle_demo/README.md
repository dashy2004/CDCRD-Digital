# Calle sintética por API de Civil 3D

Ejemplo propio de CDCRD: dos curvas de radio 120 m, rasante con curvas verticales,
corredor nativo con capas de pavimento, terreno ondulado, aceras, marcas viales,
bache irregular y 61 referencias a seis definiciones de bloques 3D.
No representa una calle levantada ni un diseño constructivo.

## Ejecución

Requiere Civil 3D 2027 y **puente activo 0.5.19**. Compilar o instalar un bundle
no reemplaza la DLL de una sesión que ya está abierta. Comprobar primero la
versión devuelta por el puente.

Desde la raíz del repositorio:

```powershell
# Solo imprime parámetros; no conecta con CAD.
python civil3d-beamng/examples/calle_demo/run.py

# Usar la ruta real de una plantilla métrica instalada.
# doc.new conserva abiertos los dibujos anteriores.
python civil3d-beamng/examples/calle_demo/run.py --apply `
  --template "C:/Templates/metric.dwt" `
  --output ".local/escenas/calle-demo/nueva-revision"
```

También puede usarse un dibujo métrico vacío abierto, pasando su nombre/ruta
exactos mediante `--drawing` en lugar de `--template`.
Se rechazan dibujos con objetos en espacio modelo y carpetas con resultados previos.
La identidad del dibujo se vuelve a comprobar antes de cada escritura.

Todos los pasos usan el puente. No hay selección por coordenadas de pantalla,
comandos de esfera/bloque, LISP ni automatización de ventanas. `blocks.create`
crea cada definición en una transacción; `entity.create` inserta las referencias.
Las vistas PNG pasan `rotacion="0"` explícitamente al exportador.

## Archivos y límites

- El DWG, las vistas y las comprobaciones se guardan en la carpeta indicada.
- `control/estado.json` identifica los objetos creados; los registros no guardan
  tokens de aprobación.
- Ante un fallo o timeout, inspeccionar el registro y el dibujo antes de actuar.
  El programa no reintenta ni reanuda automáticamente una escritura incierta.
- El eje, la rasante, el ensamblaje y el corredor son objetos nativos Civil.
  El acabado con bache, las aceras y las marcas son superficies muestreadas para
  esta demostración: no son una dependencia dinámica completa del corredor.
- La profundidad nominal es 0.0635 m. La envolvente de referencia mide
  2.75 × 1.79 m; el contorno irregular queda dentro de ella.
- La versión previa del ejemplo se construyó y releyó en Civil 3D.
  La nueva ejecución completa con las herramientas 0.5.19 está pendiente de
  recargar el puente y realizar la prueba nativa; no se presenta como ya validada.
- La exportación y conducción de esta revisión en BeamNG siguen pendientes.

Consultar [APIs, repositorios y atribución de BeamNG](../../docs/REFERENCIAS-BEAMNG.md).
