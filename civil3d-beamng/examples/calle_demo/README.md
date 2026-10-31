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
- El 2026-10-31 se completó la nueva generación en Civil 3D 2027 con puente
  activo 0.5.19: 61 bloques, profundidad releída de 0.06350000000000477 m,
  13 comprobaciones de eje/rasante y corredor reconstruido, `IsOutOfDate=false`.
  Se revisaron las imágenes generales y de detalle y se grabó el proceso con OBS.
- La revisión visual detectó estilos de planta heredados y etiquetas del eje
  fuera de la escena. Se corrigieron por API y en el generador: triángulos con
  colores propios también en Plan, contornos ocultos y grupos de etiquetas
  auxiliares invisibles. Las tomas iniciales se conservan como antecedente.
- La exportación y conducción de esta revisión en BeamNG siguen pendientes.

Consultar [APIs, repositorios y atribución de BeamNG](../../docs/REFERENCIAS-BEAMNG.md).

[Grabación por API de OBS](../../docs/CAPTURAS-OBS.md): `filmar.py` registra
la generación por etapas y las vistas de inspección en archivos separados.
