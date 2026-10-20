# Perfil completo del Geotechnical Modeler — 0.5.8

El render puede devolver `(0, 5)` sin lanzar una excepcion: significa cero
sondeos dibujados y cinco sin estratos, no cinco sondeos creados. Ahora se
informan `sticklogs_creados`, `sticklogs_sin_estratos`, `sondeos_fuera_rango`
y `completo`; este ultimo exige un render positivo de todos los incluidos.

`gm_crear_perfil_sondeos` reutiliza `ProfileStickLogSettings` del dibujo,
incluido el campo geologico. El parametro optativo `campo_geologia` permite
seleccionarlo explicitamente. Un campo inexistente, vacio o sin estratos en
algun sondeo incluido se rechaza antes de reemplazar perfiles.

`hatch_geologia=False` produce limites y rotulos sin relleno solido: el
renderizador del GM requiere un estilo para rellenar, aunque la preferencia
guardada solicite rellenos. `hatch_geologia=True` carga y valida los estilos
existentes por la API nativa, exige coincidencias y estilos para los estratos,
sin abrir el dialogo de generacion ni modificar el archivo compartido.

Ejemplo con nombres ficticios, exclusivamente en una copia identificada:

```python
gm_crear_perfil_sondeos(
    alineamiento="Eje QA", vista="Perfil QA", exageracion=4.0,
    campo_geologia="GeologyCode1", hatch_geologia=True, confirmar=True,
)
```

La operacion reemplaza perfiles del alineamiento. Inspeccione el dibujo tras
cualquier error; no reintente automaticamente, pues el GM puede dejar cambios
parciales. `completo` se refiere al diagrama en memoria: guardar, reabrir y
verificar objetos sigue siendo una comprobacion separada.

Las superficies existentes necesitan pertenecer a la carpeta nativa del GM
(`GeotechModeler/Full Stratums`); los nombres por si solos no bastan. El puente
no reclasifica automaticamente superficies ajenas ni reconstruye estratos.
El render tampoco acredita la calidad de los datos ni la representatividad
de sondeos proyectados fuera del eje.

Verificacion local: 113 pruebas Python; 33 comprobaciones .NET y 100 carreras
de timeout; compilacion Release sin errores ni advertencias. Prueba nativa
completa de 0.5.8 pendiente de cargar el puente en la instancia aislada.
El ensayo 0.5.7 identifico correctamente 5 sondeos y 20 estratos, rechazo un
campo sin datos antes de modificar perfiles y creo 5 perfiles de superficie;
el render fallo por relleno sin estilos. No se considera una prueba positiva.

Los recibos, DWG y datos de proyecto se conservan fuera del repositorio.
