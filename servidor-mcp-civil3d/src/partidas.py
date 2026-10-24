"""Native pay-item catalog, assignments and whole-drawing QTO reports."""
import hashlib,json,math,ntpath,time,uuid
from pathlib import Path
from datetime import datetime,timedelta,timezone
import puente_cliente as bridge

class PartidasError(RuntimeError):
    def __init__(self,message,receipt):
        super().__init__(message);self.receipt=receipt

def validar(accion, datos):
    def rows(key):
        v=datos.get(key)
        if isinstance(v,str):v=json.loads(v);datos[key]=v
        if not isinstance(v,list) or not 1<=len(v)<=200:raise ValueError('Lista de 1..200 elementos requerida')
        return v
    def text(v):
        if not isinstance(v,str) or not v.strip() or len(v)>160 or any(ord(c)<32 for c in v):raise ValueError('Texto invalido')
    if accion=='catalogo':
        items=rows('partidas');codes=[]
        for item in items:
            if not isinstance(item,dict):raise ValueError('Partida debe ser objeto')
            for k in ('codigo','descripcion','unidad'):text(item.get(k))
            if item['unidad'] not in ('EA','M','M2','M3') or item['descripcion'].lstrip()[0] in '=+-@':raise ValueError('Unidad o descripcion invalida')
            if not __import__('re').fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,39}',item['codigo']):raise ValueError('Codigo invalido')
            codes.append(item['codigo'].casefold())
        if len(set(codes))!=len(codes):raise ValueError('Codigos duplicados')
    elif accion=='asignar':
        pairs=[]
        for item in rows('asignaciones'):
            if not isinstance(item,dict):raise ValueError('Asignacion debe ser objeto')
            text(item.get('handle'));text(item.get('partida'))
            if not __import__('re').fullmatch(r'[A-Fa-f0-9]{1,16}',item['handle']):raise ValueError('Handle hexadecimal requerido')
            pairs.append((item['handle'].upper(),item['partida'].casefold()))
        if len(set(pairs))!=len(pairs):raise ValueError('Asignaciones duplicadas')
    elif accion=='leer':
        for h in rows('handles'):
            if not isinstance(h,str) or not __import__('re').fullmatch(r'[A-Fa-f0-9]{1,16}',h):raise ValueError('Handle hexadecimal requerido')

def ejecutar(dibujo, pid, *, accion, simular=True, timeout=60, **datos):
    if not ntpath.isabs(dibujo) or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError("Ruta DWG absoluta y PID positivo requeridos")
    if accion not in ("catalogo", "asignar", "leer", "informe", "estado") or not isinstance(simular, bool):
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
    request_path = root / ("cdcrd-partidas-" + key + ".request.json")
    result_path = root / ("cdcrd-partidas-" + key + ".result.json")
    with request_path.open("xb") as file:
        file.write(data)
    pending = {"id": key, "sha256": digest, "receipt_path": str(result_path), "estado": "desconocido"}
    try:
        bridge.llamar_con_aprobacion("cmd.run", {"linea": f"CDCRDPARTIDASV3\n{key}\n{digest}\n"})
    except Exception as exc:
        raise PartidasError("Despacho incierto: consultar recibo y cola; no reintentar. " + str(exc), pending) from exc
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if result.get("id") != key or result.get("sha256") != digest or result.get("module") != "cdcrd-partidas" or result.get("pid") != pid:
                raise PartidasError("Recibo no corresponde a la solicitud/sesion; no reintentar", pending)
            if not result.get("ok"):
                raise PartidasError(result.get("error", "Fallo nativo"), result)
            return result
        time.sleep(.1)
    raise PartidasError("Sin recibo final. Verificar modulo cargado, cola y archivo indicado; no reintentar escrituras", pending)

def registrar(mcp,ok):
    def call(dibujo,pid,**args):
        try:return ok(ejecutar(dibujo,pid,**args))
        except PartidasError as exc:return ok({'error':str(exc),'receipt':exc.receipt})
        except (ValueError,TypeError,OSError,RuntimeError) as exc:return ok({'error':str(exc)})
    @mcp.tool()
    def cargar_catalogo_partidas(dibujo:str,pid:int,partidas:str,simular:bool=True,confirmar:bool=False)->str:
        """Carga primer catalogo propio CSV, sin reemplazar uno existente.
        partidas: JSON [{codigo,descripcion,unidad}], 1..200, EA/M/M2/M3.
        Crea CSV inmutable junto al DWG y contrato persistente con SHA256.
        Conservar CSV junto a la entrega. Sin precios/formulas/categorias.
        Simular valida el plan sin ejecutar el cargador no transaccional.
        Si committed=true y ok=false, catalogo pudo cambiar: inspeccionar.
        Requiere modulo Cdcrd.Partidas; no repetir tras timeout.
        """
        if not confirmar:return ok({'error':'Operacion de escritura: requiere confirmar=True'})
        return call(dibujo,pid,accion='catalogo',partidas=partidas,simular=simular)
    @mcp.tool()
    def asignar_partidas_objetos(dibujo:str,pid:int,asignaciones:str,simular:bool=True,confirmar:bool=False)->str:
        """Anade partidas a entidades explicitas locales en ModelSpace.
        JSON [{handle,partida}], maximo200. EA: DBPoint; M: Line horizontal
        o Polyline XY; M2: Hatch XY; M3: Solid3d. Conserva partidas previas;
        rechaza duplicados, codigos inexistentes y geometria incompatible.
        Todo el lote en una transaccion. Simular solo valida el plan.
        No enlaza formas/materiales de corredor ni calcula precios.
        """
        if not confirmar:return ok({'error':'Operacion de escritura: requiere confirmar=True'})
        return call(dibujo,pid,accion='asignar',asignaciones=asignaciones,simular=simular)
    @mcp.tool()
    def leer_partidas_objetos(dibujo:str,pid:int,handles:str)->str:
        """Relee IDs nativos de partidas en handles JSON explicitos (1..200)."""
        return call(dibujo,pid,accion='leer',handles=handles)
    @mcp.tool()
    def generar_informe_partidas(dibujo:str,pid:int)->str:
        """Genera XML/CSV nativos QTO de TODO el dibujo y cantidades por ID.
        API no soporta filtro por seleccion. Unidades de cada partida;
        el encabezado XML nativo puede declarar english con filas metricas.
        Precios cero del XML no son presupuesto. Sin formulas externas.
        """
        return call(dibujo,pid,accion='informe')
    @mcp.tool()
    def estado_catalogo_partidas(dibujo:str,pid:int)->str:
        """Consulta ruta, formato y categorias del catalogo activo sin cambiarlo."""
        return call(dibujo,pid,accion='estado')

