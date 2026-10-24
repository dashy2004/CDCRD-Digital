# Prueba nativa de partidas QTO

Este arnés crea geometría sintética y rótulos exclusivamente en `CDCRD_GM_RECOVERY_PAYITEMS.dwg`, bajo la raíz seleccionada con `CDCRDGMQAENTER`. No instalarlo como producto ni ejecutarlo sobre un original. Requiere el puente y el arnés `native_gm_qa` ya disponibles en la misma instancia de Civil 3D 2027.

1. Verificar turno exclusivo, proceso, DWG, metros, cola y modales. Conservar hashes y copiar la entrega QTO anterior a otra carpeta. Abrir solo esa copia en la instancia existente.
2. Compilar `modulo-partidas/Cdcrd.Partidas.csproj` y este `Qa.csproj`. No se redistribuyen DLL Autodesk.
3. Ejecutar `pruebas/humo_partidas.py --drawing <DWG-absoluto> --output <carpeta-DWG> --pid <PID-actual> --module <Cdcrd.Partidas.V3.dll> --qa-module <Cdcrd.PartidasEvidenceQa.dll>`. Requiere copia nueva sin catálogo ni fixture; no repetir una ejecución parcial.
4. El script carga las DLL propias, crea el fixture, simula, aplica catálogo, prueba rollback tras tres asignaciones, aplica y verifica cantidades; crea tabla/capturas nativas. `Grid.cs` recalcula el bloque de tabla tras cambiar sus alturas.
5. `persistencia_partidas.py` guarda/reabre solo la copia y verifica inventario, partidas y entregas previas. Pasar `--baseline` (auditoría anterior a la escritura), `--old-native` (persistencia QTO previa), `--acceptance` y `--regions` (recibos QTO anteriores), además de dibujo, output y PID. No reintenta Save/Close/Open; solo lecturas COM rechazadas temporalmente.

La entrega 0.5.23 se ejecutó por etapas durante el desarrollo. Sus recibos finales acreditan 22 controles de aceptación y 13 de persistencia; los checks de simulación/rollback anteriores también están conservados. El script consolidado reproduce ese flujo, pero no se volvió a escribir otro fixture solo para ejecutarlo íntegro.

El inyector `Commands.cs` arma un fallo de una sola vez en `assigned`, con `partidas-fault.json`. Nunca forma parte del bundle de producción. Los recibos, DWG, catálogo CSV y capturas originales quedan en la entrega privada; el resumen publicable está en [PARTIDAS-0523](../../docs/PARTIDAS-0523.md).
