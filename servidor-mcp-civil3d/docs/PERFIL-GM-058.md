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
0.5.8 en Civil 3D 2027, sobre una copia: 5 sondeos con 4 estratos cada uno,
5 perfiles de superficie, render `(5, 0)` tanto sin rellenos como con estilos.
Auditoria nativa: 20 limites de estrato, 20 tramas interiores, 40 rellenos
laterales, 5 grupos de 12 miembros y 5 simbolos de nivel de agua. Coordenadas,
espesores y materiales contrastados con los datos existentes. Guardado y
reapertura conservaron handles, geometria y propiedades comparadas.

La prueba negativa con un campo sin datos rechazo la llamada antes de cambiar
perfiles. El fallo anterior habia dejado un grupo vacio, un bloque con su
referencia y un rectangulo parcial. Se retiraron exclusivamente esos residuos
identificados en la copia antes de repetir. La limpieza automatica de grupos
vacios no sustituye una auditoria de bloques residuales. La atomicidad de todo
el flujo GM ante un fallo tardio era pendiente en 0.5.8. La correccion y su
prueba en otra copia se describen en [Recuperacion 0.5.9](RECUPERACION-GM-059.md);
no reintentar a ciegas ni tratar un timeout como reversion confirmada.

El humo sintetico de timeout mantiene las 12 comprobaciones nativas de 0.5.6;
no se presenta como un nuevo humo de timeout ejecutado bajo 0.5.8. Los recibos,
DWG y datos de proyecto se conservan fuera del repositorio. No se modifico la
base de sondeos ni se considera que el ensayo valide su calidad geotecnica.

La salida grafica se comprobo con cuatro vistas guardadas y exportaciones PDF
nativas, revisadas visualmente. La exportacion por ventana devolvio paginas
vacias en esta prueba: hasta corregir esa variante, utilizar `nombre_vista`.
La copia se dejo guardada con el perfil completo y las vistas de verificacion.
