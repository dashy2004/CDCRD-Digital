# -*- coding: utf-8 -*-
"""Dobles de la API de Revit para probar el paquete mep sin Revit.

Modelan lo minimo: ids, conectores con IsConnected controlable, tuberias,
accesorios, transacciones con deshacer real y circuitos electricos.
Todos los datos son sinteticos.
"""
import types

PIES_POR_M = 1.0 / 0.3048
FACTOR_ELEC = 10.763910416709722  # VA y V internos (base pies) por unidad SI


def ns(**kw):
    return types.SimpleNamespace(**kw)


class ElementId(object):
    def __init__(self, value):
        self.Value = value

    def __eq__(self, other):
        return isinstance(other, ElementId) and other.Value == self.Value

    def __hash__(self):
        return hash(self.Value)


class XYZ(object):
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.X, self.Y, self.Z = float(x), float(y), float(z)


class Conector(object):
    def __init__(self, indice, origen, direccion=(0, 0, -1), radio=0.082,
                 dominio="DomainPiping", clase="Sanitary", tipo="End",
                 forma="Round", conectado=False, sistema=None, info=None):
        self.Id = indice
        self.Origin = XYZ(*origen)
        self.CoordinateSystem = ns(BasisZ=XYZ(*direccion))
        self.Domain = dominio
        self.ConnectorType = tipo
        self.Shape = forma
        self.Radius = radio
        self.PipeSystemType = clase
        self.ElectricalSystemType = clase
        self.DuctSystemType = clase
        self.MEPSystem = sistema
        self.refs = set(["previo"]) if conectado else set()
        self.invalido = False
        self.info = info

    @property
    def IsConnected(self):
        if self.invalido:
            raise RuntimeError("conector leido despues de revertir su elemento")
        return bool(self.refs)

    diario = None  # pila de deshacer del documento en uso
    ids_referidos = ()  # ElementId de los elementos a los que esta unido

    @property
    def AllRefs(self):
        return [ns(Owner=ns(Id=valor)) for valor in self.ids_referidos]

    def ConnectTo(self, otro):
        self.refs.add(otro)
        otro.refs.add(self)
        if Conector.diario is not None:
            Conector.diario.append(
                lambda: (self.refs.discard(otro), otro.refs.discard(self)))

    def GetMEPConnectorInfo(self):
        return self.info


class Elemento(object):
    Category = ns(Name="categoria")
    Name = "elemento"

    def __init__(self, numero, conectores=None, nivel=None):
        self.Id = ElementId(numero)
        self.conectores = list(conectores or [])
        self.LevelId = ElementId(nivel if nivel is not None else -1)
        self.parametros = {}
        self.tipo = -1

    def get_Parameter(self, clave):
        return self.parametros.get(clave)

    def GetTypeId(self):
        return ElementId(self.tipo)


class Aparato(Elemento):
    """Instancia de familia: sus conectores cuelgan de MEPModel."""

    @property
    def MEPModel(self):
        return ns(ConnectorManager=ns(Connectors=self.conectores),
                  GetElectricalSystems=lambda: self.sistemas)

    sistemas = ()


class Parametro(object):
    HasValue = True

    def __init__(self, valor, al_fijar=None):
        self.valor, self.al_fijar = valor, al_fijar

    def AsDouble(self):
        return self.valor

    def AsInteger(self):
        return self.valor

    def AsString(self):
        return self.valor

    def Set(self, valor):
        self.valor = valor
        if self.al_fijar:
            self.al_fijar(valor)
        return True


class Tuberia(Elemento):
    def __init__(self, numero, a, b, radio=0.164, nivel=10):
        Elemento.__init__(self, numero, [Conector(0, a, radio=radio),
                                         Conector(1, b, radio=radio)], nivel)
        self.ReferenceLevel = None if nivel is None else ns(Id=ElementId(nivel))
        self.parametros["RBS_PIPE_DIAMETER_PARAM"] = Parametro(
            2 * radio, self._diametro)

    def _diametro(self, valor):
        for c in self.conectores:
            c.Radius = valor / 2.0

    @property
    def ConnectorManager(self):
        return ns(Connectors=self.conectores)

    @property
    def Location(self):
        return ns(Curve=ns(GetEndPoint=lambda i: self.conectores[i].Origin))


class Documento(object):
    """Documento falso con deshacer: cada cambio apila su inversa."""

    def __init__(self, elementos=()):
        self.elementos = dict((e.Id.Value, e) for e in elementos)
        self.siguiente_id = 5000
        self.deshacer = []
        Conector.diario = self.deshacer
        self.bitacora = []
        self.devuelve_none = set()   # nombres de llamadas que devuelven None
        self.suelta = set()          # llamadas que dejan su union sin conectar
        self.lanza = set()           # llamadas que lanzan
        self.fallos = []             # mensajes para el preprocesador
        self.estado_commit = "Committed"
        self.grupos_abiertos = 0     # TransactionGroup sin cerrar
        self.Title, self.PathName = "modelo_sintetico", ""
        self.IsLinked = self.IsReadOnly = self.IsModifiable = False
        self.Create = Creacion(self)
        self.Application = ns(Documents=[self])

    def GetElement(self, element_id):
        return self.elementos.get(element_id.Value)

    def Regenerate(self):
        self.bitacora.append("Regenerate")

    def Save(self, *a):
        self.bitacora.append("Save")
        raise AssertionError("el paquete nunca debe guardar el documento")

    SaveAs = Save

    def agregar(self, elemento):
        self.elementos[elemento.Id.Value] = elemento
        self.deshacer.append(lambda: self._quitar(elemento))
        return elemento

    def _quitar(self, elemento):
        del self.elementos[elemento.Id.Value]
        for c in elemento.conectores:
            c.invalido = True

    def nuevo_id(self):
        self.siguiente_id += 1
        return self.siguiente_id

    def enlazar(self, a, b):
        a.ConnectTo(b)

    def revertir_hasta(self, marca):
        while len(self.deshacer) > marca:
            self.deshacer.pop()()

    def llamada(self, nombre):
        self.bitacora.append(nombre)
        if nombre in self.lanza:
            raise RuntimeError("fallo simulado en %s" % nombre)
        return nombre not in self.devuelve_none


class Creacion(object):
    def __init__(self, doc):
        self.doc = doc

    def _accesorio(self, nombre, conectores, extra=0):
        doc = self.doc
        if not doc.llamada(nombre):
            return None
        propios = [Conector(i, (c.Origin.X, c.Origin.Y, c.Origin.Z),
                            clase="Fitting")
                   for i, c in enumerate(conectores)]
        propios += [Conector(len(propios) + i, (0, 0, 0), conectado=True)
                    for i in range(extra)]
        accesorio = doc.agregar(Aparato(doc.nuevo_id(), propios))
        if nombre not in doc.suelta:
            for propio, ajeno in zip(propios, conectores):
                doc.enlazar(propio, ajeno)
        return accesorio

    def NewTeeFitting(self, c1, c2, c3):
        return self._accesorio("NewTeeFitting", [c1, c2, c3])

    def NewElbowFitting(self, c1, c2):
        return self._accesorio("NewElbowFitting", [c1, c2])

    def NewTransitionFitting(self, c1, c2):
        return self._accesorio("NewTransitionFitting", [c1, c2])

    def NewTakeoffFitting(self, conector, curva):
        accesorio = self._accesorio("NewTakeoffFitting", [conector], extra=1)
        if accesorio is not None and "takeoff_sin_ramal" not in self.doc.suelta:
            accesorio.conectores[-1].ids_referidos = [curva.Id]
        return accesorio


class Transaccion(object):
    def __init__(self, doc, nombre=None):
        self.doc, self.nombre = doc, nombre
        self.iniciada = self.terminada = False
        self.opciones = Opciones()

    def Start(self):
        if "transaccion_no_inicia" in self.doc.suelta:
            raise RuntimeError("Starting a transaction is not permitted")
        self.iniciada, self.marca = True, len(self.doc.deshacer)
        self.doc.IsModifiable = True
        self.doc.bitacora.append("Start:%s" % self.nombre)

    def HasStarted(self):
        return self.iniciada

    def HasEnded(self):
        return self.terminada

    def GetFailureHandlingOptions(self):
        return self.opciones

    def SetFailureHandlingOptions(self, opciones):
        self.opciones = opciones

    def _cerrar(self, etiqueta):
        self.terminada, self.doc.IsModifiable = True, False
        self.doc.bitacora.append(etiqueta)
        return etiqueta

    def Commit(self, opciones=None):
        pre = (opciones or self.opciones).preprocesador
        if pre is not None and self.doc.fallos:
            veredicto = pre.PreprocessFailures(Accesor(self.doc))
            if veredicto == "ProceedWithRollBack":
                return self.RollBack()
        if self.doc.estado_commit != "Committed":
            self.doc.revertir_hasta(self.marca)
            return self._cerrar(self.doc.estado_commit)
        return self._cerrar("Committed")

    def RollBack(self, opciones=None):
        self.doc.revertir_hasta(self.marca)
        return self._cerrar("RolledBack")


class GrupoDeTransacciones(object):
    """TransactionGroup: al revertirlo deshace tambien lo ya confirmado dentro."""

    def __init__(self, doc, nombre=None):
        self.doc, self.nombre = doc, nombre
        self.iniciado = self.terminado = False

    def Start(self):
        self.iniciado, self.marca = True, len(self.doc.deshacer)
        self.doc.bitacora.append("GroupStart")
        self.doc.grupos_abiertos += 1

    def HasStarted(self):
        return self.iniciado

    def HasEnded(self):
        return self.terminado

    def RollBack(self):
        if "grupo_no_revierte" in self.doc.suelta:
            raise RuntimeError("no se pudo revertir el grupo")
        self.doc.revertir_hasta(self.marca)
        self.terminado = True
        self.doc.grupos_abiertos -= 1
        self.doc.bitacora.append("GroupRolledBack")
        return "RolledBack"


class SubTransaccion(Transaccion):
    def Start(self):
        self.iniciada, self.marca = True, len(self.doc.deshacer)
        self.doc.bitacora.append("SubStart")

    def Commit(self, opciones=None):
        return self._cerrar("Committed")

    def _cerrar(self, etiqueta):
        self.terminada = True
        self.doc.bitacora.append("Sub" + etiqueta)
        return etiqueta


class Opciones(object):
    preprocesador = None
    modal = None
    limpiar = None

    def SetFailuresPreprocessor(self, pre):
        self.preprocesador = pre
        return self

    def SetForcedModalHandling(self, valor):
        self.modal = valor
        return self

    def SetClearAfterRollback(self, valor):
        self.limpiar = valor
        return self


class Accesor(object):
    def __init__(self, doc):
        self.doc, self.borradas = doc, []

    def GetFailureMessages(self):
        return [ns(GetSeverity=lambda s=s: s, GetDescriptionText=lambda t=t: t,
                   GetFailingElementIds=lambda: [ElementId(1)])
                for s, t in self.doc.fallos]

    def DeleteWarning(self, fallo):
        self.borradas.append(fallo)
        self.doc.bitacora.append("DeleteWarning")


class Colector(object):
    def __init__(self, doc):
        self.doc, self.filtro = doc, None

    def OfCategory(self, categoria):
        self.filtro = lambda e: getattr(e, "bic", None) == categoria
        return self

    def OfClass(self, clase):
        self.filtro = lambda e: isinstance(e, clase)
        return self

    def WhereElementIsNotElementType(self):
        return self

    def __iter__(self):
        return iter([e for e in self.doc.elementos.values() if self.filtro(e)])


class TipoTuberia(Elemento):
    pass


class TipoSistema(Elemento):
    SystemClassification = "Sanitary"


class Nivel(Elemento):
    pass


class _Pipe(Tuberia):
    @staticmethod
    def Create(doc, sistema, tipo, nivel, inicio, fin):
        if not doc.llamada("Pipe.Create"):
            return None
        a, b = (inicio.X, inicio.Y, inicio.Z), (fin.X, fin.Y, fin.Z)
        tubo = _Pipe(doc.nuevo_id(), a, b, nivel=nivel.Value)
        tubo.creada_con = (sistema.Value, tipo.Value, nivel.Value, a, b)
        return doc.agregar(tubo)

    @staticmethod
    def IsPipeTypeId(doc, element_id):
        return isinstance(doc.GetElement(element_id), TipoTuberia)

    @staticmethod
    def IsPipingSystemTypeId(doc, element_id):
        return isinstance(doc.GetElement(element_id), TipoSistema)


def _partir(doc, pipe_id, punto_xyz):
    if not doc.llamada("BreakCurve"):
        return None
    original = doc.GetElement(pipe_id)
    p = (punto_xyz.X, punto_xyz.Y, punto_xyz.Z)
    fin = original.conectores[1]
    viejo = fin.Origin
    nuevo = _Pipe(doc.nuevo_id(), p, (viejo.X, viejo.Y, viejo.Z),
                  radio=fin.Radius)
    nuevo.conectores[1].refs, fin.refs = fin.refs, set()
    fin.Origin = XYZ(*p)

    def restaurar():
        fin.Origin, fin.refs = viejo, nuevo.conectores[1].refs

    doc.deshacer.append(restaurar)
    doc.agregar(nuevo)
    return nuevo.Id


class SistemaElectrico(Elemento):
    SystemType = "PowerCircuit"
    BaseEquipment = None
    PanelName = ""
    PolesNumber = 1

    @staticmethod
    def Create(doc, ids, tipo):
        if not doc.llamada("ElectricalSystem.Create"):
            return None
        sistema = SistemaElectrico(doc.nuevo_id())
        sistema.doc = doc
        sistema.Elements = [doc.GetElement(i) for i in ids]
        sistema.ApparentLoad = sum(
            (e.carga_va or 0.0) for e in sistema.Elements) * FACTOR_ELEC * getattr(doc, "factor_carga_revit", 1.0)
        sistema.CircuitNumber = str(len(doc.circuitos) + 1)
        doc.circuitos.append(sistema)
        doc.deshacer.append(lambda: doc.circuitos.remove(sistema))
        # Como en Revit: los miembros pasan a pertenecer al circuito.
        for miembro in sistema.Elements:
            previo = miembro.sistemas
            miembro.sistemas = (sistema,)
            doc.deshacer.append(
                lambda m=miembro, p=previo: setattr(m, "sistemas", p))
        sistema.tipo_pedido = tipo
        return doc.agregar(sistema)

    def SelectPanel(self, tablero):
        if self.doc.llamada("SelectPanel"):
            self.BaseEquipment, self.PanelName = tablero, tablero.nombre


class Luminaria(Aparato):
    bic = "OST_LightingFixtures"

    def __init__(self, numero, carga_va=50.0, tension_v=120.0, polos=1,
                 nivel=10, en_circuito=False, con_conector=True):
        datos = {"RBS_ELEC_APPARENT_LOAD":
                 None if carga_va is None else ns(Value=carga_va * FACTOR_ELEC),
                 "RBS_ELEC_VOLTAGE": ns(Value=tension_v * FACTOR_ELEC),
                 "RBS_ELEC_NUMBER_OF_POLES": ns(Value=polos)}
        info = ns(GetConnectorParameterValue=lambda eid: datos.get(eid.Value))
        conectores = [Conector(0, (0, 0, 0), dominio="DomainElectrical",
                               clase="PowerBalanced", info=info)]
        Aparato.__init__(self, numero, conectores if con_conector else [], nivel)
        self.carga_va = carga_va
        if en_circuito:
            self.sistemas = (SistemaElectrico(numero + 90000),)


class Tablero(Aparato):
    bic = "OST_ElectricalEquipment"

    def __init__(self, numero, nombre="TA", con_distribucion=True,
                 fase="SinglePhase", lg=(110.0, 130.0), ll=(220.0, 250.0)):
        Aparato.__init__(self, numero)
        self.nombre = nombre
        self.parametros["RBS_ELEC_PANEL_NAME"] = Parametro(nombre)
        self.distribucion = None
        if con_distribucion:
            self.distribucion = ns(
                Name="120/240", ElectricalPhase=fase,
                VoltageLineToGround=self._tension(lg),
                VoltageLineToLine=self._tension(ll))

    @staticmethod
    def _tension(rango):
        if rango is None:
            return None
        return ns(MinValue=float(rango[0]), MaxValue=float(rango[1]))  # voltios, como en Revit

    @property
    def MEPModel(self):
        return ns(ConnectorManager=ns(Connectors=[]),
                  DistributionSystem=self.distribucion,
                  GetElectricalSystems=lambda: ())


class _Nombres(object):
    """Enum falso: cualquier atributo OST_/RBS_ vale su propio nombre."""

    def __init__(self, ausentes=()):
        self.ausentes = ausentes

    def __getattr__(self, nombre):
        if nombre.startswith("_") or nombre in self.ausentes:
            raise AttributeError(nombre)
        return nombre


class _Unidades(object):
    FACTORES = {"Millimeters": 304.8, "Meters": 0.3048, "Feet": 1.0,
                "VoltAmperes": 1.0 / FACTOR_ELEC, "Volts": 1.0 / FACTOR_ELEC}

    @classmethod
    def ConvertFromInternalUnits(cls, valor, unidad):
        return valor * cls.FACTORES[unidad]

    @classmethod
    def ConvertToInternalUnits(cls, valor, unidad):
        return valor / cls.FACTORES[unidad]


def crear_db():
    return ns(
        ElementId=ElementId, XYZ=XYZ, UnitUtils=_Unidades,
        UnitTypeId=_Nombres(), BuiltInParameter=_Nombres(),
        BuiltInCategory=_Nombres(ausentes=("OST_NoExiste",)),
        FilteredElementCollector=Colector, Transaction=Transaccion,
        SubTransaction=SubTransaccion, TransactionGroup=GrupoDeTransacciones,
        IFailuresPreprocessor=object,
        FailureProcessingResult=ns(Continue="Continue",
                                   ProceedWithRollBack="ProceedWithRollBack"),
        Level=Nivel,
        Plumbing=ns(Pipe=_Pipe, PipeType=TipoTuberia,
                    PipingSystemType=TipoSistema,
                    PlumbingUtils=ns(BreakCurve=_partir)),
        Electrical=ns(ElectricalSystem=SistemaElectrico,
                      ElectricalSystemType=ns(PowerCircuit="PowerCircuit")),
    )


def mm(valor):
    """mm -> pies."""
    return valor / 304.8


def modelo_sanitario(n_aparatos=1, altura_mm=600.0, separacion_mm=1000.0):
    """Ramal horizontal sobre X (id 100) y aparatos con conector vertical
    hacia abajo, a 1 m del eje y por encima de el."""
    ramal = _Pipe(100, (0.0, 0.0, 0.0), (mm(20000.0), 0.0, 0.0))
    for c in ramal.conectores:
        c.refs.add("red existente")
    elementos = [ramal, TipoTuberia(200), TipoSistema(300), Nivel(10)]
    elementos[1].Name, elementos[2].Name, elementos[3].Name = (
        "PVC sintetico", "Sanitario sintetico", "Nivel 1")
    for i in range(n_aparatos):
        x = mm(2000.0 + i * separacion_mm)
        aparato = Aparato(1001 + i, [Conector(
            0, (x, mm(1000.0), mm(altura_mm)), radio=mm(25.0))])
        aparato.bic = "OST_PlumbingFixtures"
        elementos.append(aparato)
    doc = Documento(elementos)
    return doc, crear_db()


def opciones_conectar(**extra):
    base = {"categoria": "OST_PlumbingFixtures", "ramal": 100,
            "tipo_tuberia": 200, "tipo_sistema": 300, "pendiente": 0.02}
    base.update(extra)
    return base


def modelo_electrico(luminarias, tablero=None):
    tablero = tablero or Tablero(700)
    doc = Documento([tablero, Nivel(10), Nivel(11)] + list(luminarias))
    doc.circuitos = []
    return doc, crear_db()
