"""Native corridor width/elevation target assignment with immutable receipts."""
import hashlib,json,ntpath,time,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
import puente_cliente as bridge

class TargetError(RuntimeError):
    def __init__(self,message,receipt):
        super().__init__(message);self.receipt=receipt

def validar_asignaciones(value):
    rows=json.loads(value) if isinstance(value,str) else value
    if not isinstance(rows,list) or not 1<=len(rows)<=100:raise ValueError('1..100 asignaciones requeridas')
    keys=set()
    def text(row,key):
        v=row.get(key)
        if not isinstance(v,str) or not v.strip() or len(v)>200 or any(ord(c)<32 for c in v):raise ValueError('Texto requerido: '+key)
        return v
    for r in rows:
        if not isinstance(r,dict):raise ValueError('Asignacion debe ser objeto')
        key=tuple(text(r,k).casefold() for k in ['baseline','region','subensamblaje'])
        if key in keys:raise ValueError('Asignacion duplicada')
        keys.add(key)
        if r.get('alineamiento_ancho') is None and r.get('perfil_cota') is None:raise ValueError('Indique ancho o cota')
        for k in ['alineamiento_ancho','perfil_cota']:
            if r.get(k) is not None:text(r,k)
    return rows

def ejecutar(dibujo, pid, *, accion, simular=True, timeout=60, **datos):
    if not ntpath.isabs(dibujo) or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("Ruta DWG absoluta y PID positivo requeridos")
    if accion not in ("crear", "leer", "catalogo") or not isinstance(simular, bool):
        raise ValueError("Accion o simulacion invalida")
    if accion == "crear": datos["asignaciones"] = validar_asignaciones(datos.get("asignaciones"))
    request = dict(datos, dibujo=dibujo, pid=pid, accion=accion, simular=simular,
                   vence_utc=(datetime.now(timezone.utc)+timedelta(minutes=2)).isoformat())
    info = bridge.llamar("doc.info")
    if not info.get("civil3d") or ntpath.normcase(info["dibujo"]) != ntpath.normcase(dibujo) or info["insunits"] != 6:
        raise ValueError("Documento Civil o unidades distintos a lo esperado")
    if bridge.llamar("diag.dialogos")["modal_abierto"] or bridge.llamar("diag.cola")["activas"]:
        raise RuntimeError("Civil ocupado; revisar cola/dialogo antes de enviar")
    root = Path(dibujo).parent
    key = uuid.uuid4().hex
    data = json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(data).hexdigest()
    request_path = root / ("cdcrd-targets-" + key + ".request.json")
    result_path = root / ("cdcrd-targets-" + key + ".result.json")
    with request_path.open("xb") as file:
        file.write(data)
    pending = {"id": key, "sha256": digest, "receipt_path": str(result_path), "estado": "desconocido"}
    try:
        bridge.llamar_con_aprobacion("cmd.run", {"linea": f"CDCRDTARGETSV2\n{key}\n{digest}\n"})
    except Exception as exc:
        raise TargetError("Despacho incierto: consultar recibo y cola; no reintentar. " + str(exc), pending) from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("id") != key or result.get("sha256") != digest or result.get("module") != "cdcrd-targets" or result.get("pid") != pid:
                raise TargetError("Recibo no corresponde a la solicitud/sesion; no reintentar", pending)
            if not result.get("ok"):
                raise TargetError(result.get("error", "Fallo nativo"), result)
            return result
        time.sleep(.1)
    raise TargetError("Sin recibo final. Verificar modulo cargado, cola y archivo indicado; no reintentar escrituras", pending)


def registrar(mcp,ok):
    def call(dibujo,pid,**args):
        try:return ok(ejecutar(dibujo,pid,**args))
        except TargetError as exc:return ok({'error':str(exc),'receipt':exc.receipt})
        except (ValueError,TypeError,OSError,RuntimeError) as exc:return ok({'error':str(exc)})
    @mcp.tool()
    def listar_targets_corredor(dibujo:str,pid:int,corredor:str)->str:
        """Lista targets nativos por baseline/region/subensamblaje y sus IDs, sin asignarlos."""
        return call(dibujo,pid,accion='catalogo',corredor=corredor)
    @mcp.tool()
    def crear_corredor_con_targets(dibujo:str,pid:int,corredor_origen:str,nombre:str,asignaciones:str,
                                  simular:bool=True,confirmar:bool=False)->str:
        """Crea un corredor nuevo con targets de carriles, desde un multibaseline propio.

        asignaciones JSON [{baseline,region,subensamblaje,alineamiento_ancho,perfil_cota}].
        Ancho: alineamiento lateral; cota: perfil de ese eje, o del eje baseline
        cuando no se asigna ancho. Solo objetos locales, metros, sin ecuaciones.
        Origen de solo lectura, con targets de ancho/cota vacios. Nombre nuevo.
        Copia baselines/regiones/frecuencias del contrato; crea su propia Top.
        Un target por slot; simular=True crea y aborta solo objetos nuevos.
        Comprueba ETW nativo contra interseccion normal/perfil, reconstruye Top.
        Requiere Cdcrd.Targets.V2. Ante timeout consultar recibo; nunca reenviar.
        """
        if not confirmar:return ok({'error':'Operacion de escritura: requiere confirmar=True'})
        return call(dibujo,pid,accion='crear',corredor_origen=corredor_origen,nombre=nombre,asignaciones=asignaciones,simular=simular)
    @mcp.tool()
    def leer_targets_ancho_cota(dibujo:str,pid:int,corredor:str)->str:
        """Relee contrato propio, targets y geometria; verifica anchos/cotas en estaciones aplicadas."""
        return call(dibujo,pid,accion='leer',corredor=corredor)
