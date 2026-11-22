# Documentos de la sesión: listar, abrir, activar y cerrar sin guardar — 0.5.26

Cuatro operaciones sobre los dibujos abiertos en la instancia existente de Civil 3D 2027, sin diálogos y sin iniciar otra instancia. Módulo opcional `Cdcrd.Documentos.V1` **0.1.0**, comando `CDCRDDOCUMENTOSV1`, instalado con `instalar-documentos.ps1`. [fable], 2026-11-21.

El comando se declara con `CommandFlags.Session`: corre en el contexto de aplicación, que es donde `DocumentCollection` permite abrir (`DocumentCollectionExtension.Open(docs, ruta, soloLectura)`), activar (`MdiActiveDocument`) y cerrar (`DocumentExtension.CloseAndDiscard`). Firmas comprobadas por reflexión de `AcMgd.dll` y `accoremgd.dll` de la instalación.

## Uso

```python
listar_documentos(pid=PID_VERIFICADO)
abrir_documento(pid=PID_VERIFICADO, ruta=r"C:\QA\copia.dwg", solo_lectura=False, confirmar=True)
activar_documento(pid=PID_VERIFICADO, ruta=r"C:\QA\otro.dwg", confirmar=True)
cerrar_documento(pid=PID_VERIFICADO, ruta=r"C:\QA\copia.dwg", descartar_cambios=False, activar_despues=r"C:\QA\otro.dwg", confirmar=True)
```

`pid` es el del proceso `acad.exe` esperado; el recibo solo vale si coincide. Un dibujo guardado se nombra por su ruta completa; uno sin archivo (`Drawing1.dwg`), por su nombre.

## Contrato

- **Transporte.** Solicitud inmutable con SHA-256, PID y vencimiento de 3 minutos, archivo `.started` y recibo ligado a la solicitud. A diferencia de los demás módulos, solicitudes y recibos viven en `%LOCALAPPDATA%\CdcrdCivil3dBridge\documentos`, nunca junto a un dibujo: el documento activo cambia durante estas operaciones y puede no tener archivo o ser de otra persona.
- **Estado en cada respuesta.** Todo recibo trae `activo` (ruta del documento activo al terminar) y `abiertos`; las operaciones que cambian la sesión devuelven además la lista completa con, por documento, `ruta`, `con_nombre`, `solo_lectura`, `activo`, `modificado`, `dbmod` y `comando_en_curso`.
- **Cambios sin guardar.** `modificado` sale de `DBMOD` y `Saved` del objeto COM de cada documento (`GetAcadDocument`), activo o no. Si no se puede leer, el documento se trata como modificado.
- **Abrir.** Ruta absoluta de un `.dwg` existente. Si ya está abierto en el mismo modo solo se activa (`ya_abierto: true`); en modo distinto es error. Sin `solo_lectura` se prueba antes un acceso exclusivo al archivo y, si otro proceso lo tiene, se rechaza: así no aparece el diálogo «¿abrir en solo lectura?». `PROXYNOTICE` se pone en 0 durante la apertura y se restaura. Tras abrir se comprueba que el modo real sea el pedido.
- **Cerrar.** Siempre `CloseAndDiscard`: el módulo no tiene ningún camino que guarde. Se niega si:
  - es el único documento abierto (el puente despacha comandos a través de un documento);
  - tiene cambios sin guardar y no se pasó `descartar_cambios=True`;
  - tiene un comando en curso distinto de este;
  - se pide `descartar_cambios=True` con la sesión en solo lectura (`CDCRD_C3D_SOLO_LECTURA=1`).

  Si era el documento activo, antes se activa `activar_despues` o, si no se indica, otro documento abierto. Después se comprueba que ya no figure en la colección.
- **Permisos.** `listar` siempre; el resto exige `CDCRD_C3D_PERMITIR_COMANDOS=1` en el entorno de Civil 3D y `confirmar=True` en la herramienta.

## Resultados en dibujos sintéticos

Instancia existente de Civil 3D 2027 con el puente 0.5.20 y un dibujo de trabajo ajeno abierto, que no se modificó (`DBMOD` 0 y fecha en disco iguales antes y después). Dos dibujos desechables creados de la plantilla métrica del producto.

| Caso | Resultado |
|---|---|
| Listar | 1 documento, activo, `modificado: false` |
| Abrir con escritura | 2 abiertos, el nuevo activo, sin diálogo |
| Abrir otro en solo lectura | 3 abiertos, `solo_lectura: true` |
| Abrir con escritura uno ya abierto en solo lectura | rechazado: «ya está abierto en solo lectura» |
| Activar | cambia el activo; la respuesta lo confirma |
| Cerrar uno inactivo y sin cambios | cerrado; el activo no cambia |
| Cerrar con cambios (`DBMOD` 1) sin `descartar_cambios` | rechazado; sigue abierto |
| Cerrar el activo con `descartar_cambios=True` | cerrado, activo pasa a `activar_despues`; archivo en disco idéntico al original (SHA-256) |
| Cerrar uno que no está abierto | rechazado |
| Abrir con escritura un archivo en uso por otro proceso | rechazado sin diálogo |

Probado después en una sesión recién iniciada: la negativa a cerrar el único documento. No probado en vivo: dibujos que disparan otros diálogos al abrir.

**«Drawing is busy» al cerrar un dibujo inactivo.** Reproducido con tres dibujos sintéticos: con A activo se abre B, desde B se abre C, se cierra C dejando activo A y se pide cerrar B. `CloseAndDiscard` responde «Drawing is busy» aunque B no informe comando en curso: el dibujo desde el que se abrió otro documento queda ocupado para Civil hasta que vuelve a estar activo. Activar B y cerrarlo entonces funciona. El servidor lo hace solo: ante ese error activa el dibujo, repite el cierre una vez dejando activo `activar_despues` o el que lo estaba, y lo dice en `reintento`. Ese reintento automático tiene pruebas unitarias; en vivo se hizo la misma secuencia a mano (activar y cerrar).

Offline: 11 pruebas Python (`tests/test_documentos.py`), compilación con 0 errores y 0 advertencias.

## Límites

- Necesita al menos un dibujo abierto: sin documento el puente no puede despachar el comando. Abrir el primer dibujo de una sesión vacía exige una función en el núcleo del puente, que este módulo no toca.
- Solo `.dwg`. No crea dibujos nuevos, no guarda, no hace «guardar como».
- Suprime el aviso de proxies y el de archivo en uso. Un dibujo con referencias externas o fuentes ausentes, o que pida recuperación, puede abrir otro diálogo: `eventos_dialogo` y `estado_cola` lo muestran, y hay que cerrarlo a mano.
- Cada compilación registra también el nombre canónico del comando: en una sesión donde ya se cargó una versión, la nueva solo entra al reiniciar Civil 3D.

## Reproducción

```powershell
py pruebas/humo_documentos.py --pid <PID> --accion listar
py pruebas/humo_documentos.py --pid <PID> --accion abrir --ruta <CDCRD_QA_*.dwg> [--solo-lectura]
py pruebas/humo_documentos.py --pid <PID> --accion cerrar --ruta <CDCRD_QA_*.dwg> [--descartar-cambios] [--activar-despues <ruta>]
```

El script solo abre, activa o cierra dibujos cuyo nombre empiece por `CDCRD_QA`.
