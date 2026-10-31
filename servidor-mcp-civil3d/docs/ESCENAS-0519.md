# Herramientas nativas para escenas — 0.5.19

La exportación heredaba el giro del layout Model. Al pasar de un papel vertical
a un PNG horizontal, la vista podía quedar girada 90 grados. Ahora
`exportar_vista(..., rotacion="0")` configura el giro en el PlotSettings temporal
de esa exportación, sin abrir el diálogo ni cambiar el layout del usuario.
Se admiten 0, 90, 180 y 270; omitirlo conserva el comportamiento anterior.

| Herramienta MCP | Método RPC | Comportamiento |
|---|---|---|
| `exportar_vista` | `vista.exportar` | Nuevo parámetro opcional `rotacion`; valida antes de iniciar la exportación. |
| `crear_bloque_3d` | `blocks.create` | Definición atómica desde primitivas locales. Rechaza nombres existentes; no selecciona ni borra entidades del dibujo. |
| `crear_entidad` | `entity.create` | Añade `esfera {centro:[x,y,z], radio}`; usa geometría nativa y conserva Z sin osnaps. |
| `crear_dibujo` | `doc.new` | Abre un DWT absoluto existente y conserva los documentos anteriores. Devuelve nombre y unidades. |

Todas las escrituras mantienen el token de un solo uso ligado a método y
parámetros. La creación de bloques no depende de habilitar comandos de texto.
Para insertar un bloque, usar el tipo `bloque` de `crear_entidad`.

## Comprobación

Se compilan los adaptadores Civil 3D y AutoCAD. Las pruebas de Python cubren
registro MCP, confirmación, rotación y precondiciones; el arnés C# prueba el
contrato de giro y las regresiones existentes.

La prueba nativa se ejecuta con un puente 0.5.19 ya cargado:

```powershell
python pruebas/humo_escena_0519.py `
  --template "C:/Templates/metric.dwt" `
  --output "../.local/qa-escenas/nueva-corrida"
```

Crea un dibujo nuevo, comprueba la reversión de un bloque parcialmente inválido,
relee los límites Z de una esfera y exporta vistas a 0/90 grados. Conserva
recibo y DWG sintéticos. Revisar las dos imágenes. Un puente anterior se rechaza
antes de crear el dibujo.

**Comprobación nativa, 2026-10-31:** después de reiniciar Civil 3D 2027 se
confirmó el puente activo 0.5.19. El arnés terminó con PASS: bloque inválido
revertido, nombre reutilizable, tres referencias y límites Z entre 2.3 y 5.9 m.
Se revisaron visualmente los PNG de 0° y 90°: disposición horizontal y vertical
respectivamente, sin giro heredado imprevisto. El recibo y DWG permanecen en
la salida local de QA. Un primer intento se detuvo al cambiar el dibujo activo;
se conservó como parcial y se realizó una nueva prueba en otro dibujo.

[Ejemplo de calle](../../civil3d-beamng/examples/calle_demo/README.md) ·
[Referencias originales de BeamNG](../../civil3d-beamng/docs/REFERENCIAS-BEAMNG.md).
