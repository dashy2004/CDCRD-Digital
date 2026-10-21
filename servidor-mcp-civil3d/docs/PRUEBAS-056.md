# Regresiones del puente 0.5.6

## Cambios

- `ReflectionRead` reconoce campos publicos antes de propiedades; mantiene propiedades clasicas, null e indexadores rechazados. Lo usan `Invocar` y `PropGm`. `Val` serializa tuplas como Item1, Item2, etc.
- `GmGroupPolicy` incluye los grupos vacios con prefijo `GM - `. Conserva grupos vacios ajenos y grupos con miembros vivos. Una referencia desconocida ya no basta para atribuir un grupo ajeno al GM. No se purgan bloques huerfanos como efecto secundario.
- La cola decide atomicamente entre iniciar y cancelar. Una peticion vencida pendiente no puede escribir al reanudarse Idle; al desuscribir tambien se cancelan pendientes. Si ya empezo, se devuelve resultado incierto, sin afirmar cancelacion. Si termina justo al vencer la espera, se devuelve su resultado real.
- El error JSON-RPC incluye `request_id`, `estado`, `cancelada_antes_de_ejecutar` y `resultado_incierto`. El cliente Python conserva `datos` y el servidor MCP lo transmite.
- `diag.cola`, servido desde el socket, devuelve activas y ultimos 64 despachos terminados/cancelados. `estado_cola` lo expone como herramienta MCP. No almacena resultados ni parametros. Un cmd.run despachado no acredita finalizacion del comando en AutoCAD.

## Regresion sin CAD

Desde `servidor-mcp-civil3d`:

```powershell
py -m pytest tests -q
dotnet run --project pruebas/arnes_regresion/Regresion.csproj -c Release
dotnet build puente/Cdcrd.Civil3dBridge.csproj -c Release
```

El arnes compila Bridge.cs, Rpc.cs y los dos helpers reales; solo sustituye el host Autodesk. Comprueba resultados, errores, cancelacion pendiente, operacion ya iniciada, desuscripcion, estado por id y carreras de timeout. Las pruebas Python incluyen conservacion de metadatos y rechazo de un dibujo/resultado de prueba incorrectos.

## Humo nativo reproducible

Usar una instancia aislada de Civil 3D 2027 con estos ajustes de proceso, sin cambiar variables globales ni politicas de seguridad:

```powershell
$env:CDCRD_C3D_PORT='8761'
$env:CDCRD_C3D_TIMEOUT_MS='5000'
$env:CDCRD_C3D_PERMITIR_COMANDOS='1'
$env:CDCRD_C3D_SOLO_LECTURA='0'
$env:CDCRD_C3D_QA_ROOT='C:\CivilPractice\bridge-056\run'
```

La carpeta QA debe existir y estar vacia. Compilar `pruebas/native_qa/BridgeQa.csproj` y cargar la DLL de prueba con NETLOAD en esa instancia. El auxiliar no se instala con el puente y rechaza dibujos cuyo nombre no comience por `CDCRD_BRIDGE_SMOKE`. Guardar un DWG vacio con ese nombre, comprobar su ruta y cargar el puente 0.5.6. No cerrar ni reiniciar instancias con trabajo sin guardar.

```powershell
py pruebas/humo_v052.py --drawing C:\CivilPractice\bridge-056\CDCRD_BRIDGE_SMOKE.dwg --output C:\CivilPractice\bridge-056\run
```

Se conserva el nombre historico del script. Exige 0.5.6, ruta exacta y escritura/comandos habilitados. Cada comando usa un recibo nuevo; no se reenvia al faltar respuesta.

La prueba crea un grupo GM cuyo unico miembro se borra, un grupo vacio ajeno, un GM vivo y un grupo mixto. Bloquea temporalmente el hilo CAD y envia `gm.reparar` por TCP: debe vencer, cancelarse y dejar intacta la geometria al regresar Idle. Luego simula/aplica la limpieza, comprueba los grupos conservados y prueba una operacion iniciada que vence pero finaliza una sola vez. El estado se recupera por request_id.

`humo-result.json` contiene el veredicto y referencias; los otros JSON contienen los recibos nativos. El perfil de sondeos completo del GM requiere su propio proyecto y prueba separada. No se anuncia esa validacion a partir del productor ValueTuple sintetico.

## Resultado local del 2026-10-20

- Compilacion real contra Autodesk: cero errores y cero advertencias.
- Python: 110 pruebas aprobadas. Una corrida durante el arranque de otra instancia tuvo dos vencimientos de 10 s al inicializar subprocesses MCP; la corrida completa posterior paso sin ampliar tiempos ni cambiar esas pruebas.
- .NET: 24 comprobaciones y 100 carreras aprobadas.
- Humo Civil 3D 2027: 12 comprobaciones aprobadas, incluidas cancelacion TCP y conservacion de grupos/entidades.
- La instancia previa con trabajo sin guardar se conservo. La correccion esta instalada para siguientes arranques y se probo en el puerto 8761. Una instancia que ya tenia 0.5.5 cargado requiere un reinicio normal despues de conservar su trabajo.
- Sin commit remoto, push ni PR. Recibos y dibujos privados permanecen fuera del repositorio publico.
