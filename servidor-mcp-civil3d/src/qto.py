"""Native TIN volumes and sectional QTO in newly created objects."""
import hashlib,json,math,ntpath,time,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
import puente_cliente as bridge

class QtoError(RuntimeError):
    def __init__(self,message,receipt):
        super().__init__(message);self.receipt=receipt

def validar(accion, datos):
    def text(k):
        v=datos.get(k)
        if not isinstance(v,str) or not v.strip() or len(v)>200 or any(ord(c)<32 for c in v):raise ValueError('Texto requerido: '+k)
    def number(v,lo,hi):
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError('Numero fuera de rango')
    if accion.startswith('leer_') or accion=='calcular_formas':
        text('objeto');return
    text('nombre')
    if accion=='volumen':
        text('base');text('comparacion')
        if datos['base'].casefold()==datos['comparacion'].casefold():raise ValueError('Superficies deben ser diferentes')
        for k in ['factor_corte','factor_relleno']:number(datos.get(k,1),.1,10)
    elif accion=='materiales':
        text('alineamiento');number(datos.get('semiancho'),.1,100)
        stations=datos.get('estaciones')
        if isinstance(stations,str):stations=json.loads(stations);datos['estaciones']=stations
        if not isinstance(stations,list) or not 2<=len(stations)<=200:raise ValueError('2..200 estaciones requeridas')
        for v in stations:number(v,-1e8,1e8)
        if any(b-a<=1e-6 for a,b in zip(stations,stations[1:])):raise ValueError('Estaciones ordenadas y unicas requeridas')
        mode=datos.get('modo')
        if mode=='tierras':text('base');text('comparacion')
        elif mode=='formas':
            for k in ['corredor','baseline','region']:text(k)
            codes=datos.get('codigos')
            if isinstance(codes,str):codes=json.loads(codes);datos['codigos']=codes
            if not isinstance(codes,list) or not 1<=len(codes)<=20 or any(not isinstance(c,str) or not c or len(c)>100 or any(ord(x)<32 for x in c) for c in codes):raise ValueError('1..20 codigos requeridos')
            if len(set(codes))!=len(codes):raise ValueError('Codigos duplicados')
        else:raise ValueError('Modo tierras o formas requerido')

def ejecutar(dibujo, pid, *, accion, simular=True, timeout=60, **datos):
    if not ntpath.isabs(dibujo) or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("Ruta DWG absoluta y PID positivo requeridos")
    if accion not in ("volumen", "materiales", "leer_volumen", "leer_materiales", "calcular_formas") or not isinstance(simular, bool):
        raise ValueError("Accion o simulacion invalida")
    validar(accion, datos)
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
    request_path = root / ("cdcrd-qto-" + key + ".request.json")
    result_path = root / ("cdcrd-qto-" + key + ".result.json")
    with request_path.open("xb") as file:
        file.write(data)
    pending = {"id": key, "sha256": digest, "receipt_path": str(result_path), "estado": "desconocido"}
    try:
        bridge.llamar_con_aprobacion("cmd.run", {"linea": f"CDCRDQTOV8\n{key}\n{digest}\n"})
    except Exception as exc:
        raise QtoError("Despacho incierto: consultar recibo y cola; no reintentar. " + str(exc), pending) from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("id") != key or result.get("sha256") != digest or result.get("module") != "cdcrd-qto" or result.get("pid") != pid:
                raise QtoError("Recibo no corresponde a la solicitud/sesion; no reintentar", pending)
            if not result.get("ok"):
                raise QtoError(result.get("error", "Fallo nativo"), result)
            return result
        time.sleep(.1)
    raise QtoError("Sin recibo final. Verificar modulo cargado, cola y archivo indicado; no reintentar escrituras", pending)


def registrar(mcp,ok):
    def call(dibujo,pid,**args):
        try:return ok(ejecutar(dibujo,pid,**args))
        except QtoError as exc:return ok({'error':str(exc),'receipt':exc.receipt})
        except (ValueError,TypeError,OSError,RuntimeError) as exc:return ok({'error':str(exc)})
    @mcp.tool()
    def crear_cubicacion_tin(dibujo:str,pid:int,nombre:str,base:str,comparacion:str,factor_corte:float=1,factor_relleno:float=1,simular:bool=True,confirmar:bool=False)->str:
        """Crea una TinVolumeSurface nueva: corte/relleno bruto y ajustado en m3.
        Superficies TIN locales, actualizadas y diferentes; usa su interseccion.
        No recorta limites ni modifica fuentes. Factores explicitos 0.1..10.
        Requiere Cdcrd.Qto.V8. Ante timeout inspeccionar recibo, no repetir.
        """
        if not confirmar:return ok({'error':'Operacion de escritura: requiere confirmar=True'})
        return call(dibujo,pid,accion='volumen',nombre=nombre,base=base,comparacion=comparacion,factor_corte=factor_corte,factor_relleno=factor_relleno,simular=simular)
    @mcp.tool()
    def crear_materiales_qto(dibujo:str,pid:int,nombre:str,alineamiento:str,estaciones:str,semiancho:float,modo:str,base:str='',comparacion:str='',corredor:str='',baseline:str='',region:str='',codigos:str='[]',simular:bool=True,confirmar:bool=False)->str:
        """Crea grupo y lista QTO nuevos por areas medias, en metros.
        estaciones JSON ordenadas; tierras compara dos TIN; formas muestrea
        codigos de un corredor, baseline y region explicitamente elegidos.
        En modo formas PREPARA el grupo; luego completar_materiales_qto
        calcula la lista en otro comando. Una interrupcion deja grupo propio
        preparado, con recibo; no recrearlo ni repetir una fase confirmada.
        Formas: estaciones aplicadas interiores a la region, sin huecos;
        no mezcla baselines. Devuelve XML nativo de ReportQuantities.
        Fuentes intactas; no precios, partidas de pago ni criterio de diseno.
        """
        if not confirmar:return ok({'error':'Operacion de escritura: requiere confirmar=True'})
        return call(dibujo,pid,accion='materiales',nombre=nombre,alineamiento=alineamiento,estaciones=estaciones,semiancho=semiancho,modo=modo,base=base,comparacion=comparacion,corredor=corredor,baseline=baseline,region=region,codigos=codigos,simular=simular)
    @mcp.tool()
    def completar_materiales_qto(dibujo:str,pid:int,grupo:str,simular:bool=True,confirmar:bool=False)->str:
        """Calcula formas en grupo propio preparado por crear_materiales_qto.
        Solo acepta estado prepared y lista vacia. Conserva el grupo preparado
        ante rechazo; leer_cubicacion_qto permite comprobar su estado. Nunca
        repetir tras timeout sin inspeccionar recibo. simular revierte la lista.
        """
        if not confirmar:return ok({'error':'Operacion de escritura: requiere confirmar=True'})
        return call(dibujo,pid,accion='calcular_formas',objeto=grupo,simular=simular)
    @mcp.tool()
    def leer_cubicacion_qto(dibujo:str,pid:int,objeto:str,tipo:str='volumen')->str:
        """Relee volumen propio o grupo materiales propio y su XML nativo actual."""
        if tipo not in ('volumen','materiales'):return ok({'error':'tipo volumen o materiales requerido'})
        return call(dibujo,pid,accion='leer_'+tipo,objeto=objeto)
