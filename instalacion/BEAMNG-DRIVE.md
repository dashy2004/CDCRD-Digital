# Instalar el puente Civil 3D → BeamNG.drive (Windows)

Lleva la superficie de un terreno y la de un corredor desde Civil 3D hasta un nivel
propio de BeamNG.drive. No usa modelo de IA, cuenta de IA ni servidor MCP, y no
necesita BeamNG.tech. El código está en [`civil3d-beamng/`](../civil3d-beamng/); este
documento es solo la instalación, pieza por pieza, con una comprobación al final de
cada una.

**Estado:** versión 0.1.0. La importación, el guardado, la recarga y la colisión
física se comprobaron en BeamNG.drive 0.39.4. En la 0.40 la importación aún no se ha
probado. No se han verificado todos los empalmes entre carretera y terreno ni el
recorrido completo de una vía.

## Requisitos

- Windows con Civil 3D 2027. El dibujo debe estar en metros, en AutoCAD y en Civil.
- Python 3.10 o superior.
- BeamNG.drive con su World Editor.
- SDK de .NET 10, solo si vas a compilar el plugin en vez de usar el bundle ya
  compilado.

## 1. Plugin de Civil 3D

Desde la carpeta `civil3d-beamng`:

```powershell
.\civil3d\instalar.ps1
```

Crea `%APPDATA%\Autodesk\ApplicationPlugins\CDCRD-BeamNG.bundle`, separado de
cualquier otro plugin MCP, y conserva las versiones anteriores. Civil 3D solo lo toma
al reiniciar: guarda tu trabajo antes.

**Comprobar:** en Civil 3D, el comando `CDCRDBEAMNGEXPORT` responde.

## 2. Conversor de Python

Las dependencias de ejecución son `numpy`, `Pillow` y `defusedxml`; están declaradas
en `pyproject.toml` y se instalan con el paquete. `pycollada` y `pytest` solo hacen
falta para correr las pruebas.

Usa un entorno virtual para no tocar el Python del sistema:

```powershell
py -3 -m venv "$env:USERPROFILE\cdcrd-beamng-venv"
& "$env:USERPROFILE\cdcrd-beamng-venv\Scripts\python.exe" -m pip install --upgrade pip
& "$env:USERPROFILE\cdcrd-beamng-venv\Scripts\python.exe" -m pip install .
```

Ejecuta el último comando dentro de `civil3d-beamng`.

**Comprobar:**

```powershell
& "$env:USERPROFILE\cdcrd-beamng-venv\Scripts\python.exe" -m cdcrd_beamng --help
```

> En Windows el `python` del PATH puede ser el alias de la Tienda de Windows, que no
> tiene las dependencias. Pasa siempre la ruta completa del intérprete del entorno.

## 3. Rutas del juego

`tools\convertir-e-instalar.ps1` usa dos rutas:

| Parámetro | Qué es | Valor por omisión |
|---|---|---|
| `-GameFolder` | Instalación de BeamNG.drive. De ahí toma la plantilla `content\levels\smallgrid.zip`. | `C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive` |
| `-UserFolder` | Carpeta de usuario, donde escribe el nivel nuevo. | `%LOCALAPPDATA%\BeamNG\BeamNG.drive\current` |

Si tu instalación no está en la ruta por omisión, pasa `-GameFolder`. En Steam: clic
derecho sobre el juego → Administrar → Explorar los archivos locales.

**Comprobar:**

```powershell
Test-Path 'C:\Program Files (x86)\Steam\steamapps\common\BeamNG.drive\content\levels\smallgrid.zip'
```

Debe devolver `True`.

## 4. Primer nivel

1. En Civil 3D, con terreno y superficie final del corredor: `CDCRDBEAMNGEXPORT`.
   Guarda el JSON **fuera de este repositorio**; contiene geometría y nombres del
   proyecto.
2. Convierte e instala. El id del nivel admite minúsculas, números y guion bajo, y
   cambia en cada revisión. La carpeta de salida no debe existir:

```powershell
& '.\tools\convertir-e-instalar.ps1' `
  -Snapshot 'D:\proyecto\exportacion.json' `
  -Output   'D:\proyecto\paquete_r01' `
  -LevelId  'mi_carretera_r01' `
  -Python   "$env:USERPROFILE\cdcrd-beamng-venv\Scripts\python.exe"
```

   Este comando es el que crea `/levels/mi_carretera_r01/manifest.json`, la ruta que
   pide el importador.
3. Reinicia BeamNG, abre ese nivel desde Freeroam y pulsa F11.
4. **Window → Importar Civil 3D**, ruta `/levels/mi_carretera_r01/manifest.json`,
   importa, guarda y recarga el nivel desde el menú del juego antes de conducir.

No cambies de nivel con scripts ni por la API con el juego abierto: forzar una
transición pendiente de la interfaz provocó un fallo C++ durante las pruebas.

## Después de actualizar BeamNG

Cada actualización mayor del juego mueve la carpeta de usuario a un respaldo, y con
ella se van la extensión del importador y los niveles instalados. Si desaparece el
menú **Importar Civil 3D**, vuelve a correr `convertir-e-instalar.ps1`: reinstala la
extensión junto con el nivel.

## Qué no incluye esta versión

Texturas del CAD, señales, tráfico, puentes ni túneles. Los materiales se reparten por
una franja guía y la frontera entre asfalto y talud es aproximada. Los huecos del
terreno se recortan por celdas completas y el borde puede pasarse hasta 1,414 m.
