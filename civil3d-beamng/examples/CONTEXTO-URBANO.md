# Contexto urbano editable en Civil 3D

`contexto_urbano.py` crea dos ejemplos esquemáticos: calle con bache/borde roto y
esquina con motos. Son aproximaciones con dimensiones supuestas, sin datos de
levantamiento. No identifica calles ni reproduce la geometría exacta de un lugar.

Requiere Civil 3D 2027, puente nativo 0.5.20 o compatible con escritura habilitada,
Python con `pywin32`, y turno exclusivo de la aplicación conforme al protocolo local.
No controla la pantalla. Usa superficies TIN, alineamiento, perfil, sólidos y bloques
nativos; las ruedas se orientan mediante AutoCAD ActiveX `Rotate3D`.

```powershell
py civil3d-beamng/examples/contexto_urbano.py D:/salidas/contexto `
  --template 'D:/plantillas/metric.dwt' --case A_CALLE_BACHE
py civil3d-beamng/examples/contexto_urbano.py D:/salidas/contexto `
  --template 'D:/plantillas/metric.dwt' --case B_ESQUINA_MOTOS
```

Cada ejecución exige una salida nueva y abre un dibujo nuevo desde una plantilla
sin objetos en model space. Verifica el dibujo activo antes de cada escritura;
se detiene si cambia. `--resume-empty` sirve únicamente para una creación de dibujo
interrumpida y comprobada: necesita `creation.json` y un dibujo todavía vacío.
Después de un timeout se inspeccionan `pending.json`, `operations.jsonl`, `diag.cola`
y el modelo; no se repite una escritura incierta.

Entrega DWG, plano PDF, cinco vistas PNG y metadatos de supuestos. Las capas
`CDX-PLANO` y `CDX-TRAYECTORIAS` deben encenderse para la planta y apagarse para
las vistas espaciales; las vistas guardadas no restauran por sí solas esas capas.
La perspectiva se configura sobre el ViewTableRecord por API, con distancia de
cámara explícita. `PERSPECTIVE` por COM puede reajustar el encuadre de forma no deseada.

Comprobado dentro de Civil 3D 2027/puente 0.5.20: dos dibujos, superficies y eje/perfil,
bloques de motos/vehículos, bache de 0.0635 m leído de la TIN, planos y vistas,
perspectiva nativa y grabación mediante OBS WebSocket. Los medios y los DWG de la
sesión se conservan en la entrega privada. Esta prueba no valida una reconstrucción
de accidente ni la importación de estos dos ejemplos nuevos a BeamNG.

Referencia: [Rotate3D, AutoCAD ActiveX](https://help.autodesk.com/cloudhelp/2024/PTB/AutoCAD-ActiveX-Reference/files/GUID-1057C914-CB4F-43C9-841F-F80207D9398E.htm).
