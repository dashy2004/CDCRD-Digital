# -*- coding: utf-8 -*-
"""Utilidades comunes del paquete mep.

Python puro, valido en IronPython 3.4 (pyRevit) y en CPython (pruebas).
La API de Revit llega inyectada (DB, doc): este modulo no importa Autodesk.
Firmas usadas: ver API-REVIT-2027.md.
"""

try:  # IronPython dentro de Revit
    from System import Int64 as _Int64
    from System.Collections.Generic import List as _List
except ImportError:  # CPython (pruebas con dobles)
    _Int64 = int
    _List = None

DOMINIOS = {
    "DomainPiping": "tuberia",
    "DomainElectrical": "electrico",
    "DomainHvac": "ducto",
    "DomainCableTrayConduit": "bandeja_conduit",
}
TIPOS_FISICOS = ("End", "Curve", "Physical")
TOL_PIES = 0.001  # ~0.3 mm: dos puntos se consideran el mismo


class ErrorEntrada(ValueError):
    """Entrada invalida detectada ANTES de abrir transaccion."""


class ErrorApi(Exception):
    """La API devolvio None o un resultado invalido donde se esperaba obra."""


def exigir(valor, llamada):
    """Un retorno None de la API es un fallo explicito, nunca un exito."""
    if valor is None:
        raise ErrorApi("%s devolvio None" % llamada)
    return valor


class Registro(object):
    """Acumula errores y advertencias; nada se descarta en silencio."""

    def __init__(self):
        self.errores = []
        self.advertencias = []

    def error(self, etapa, exc, elemento=None):
        self.errores.append({"etapa": etapa, "elemento": elemento,
                             "tipo": type(exc).__name__, "mensaje": str(exc)})

    def nota(self, etapa, mensaje, elemento=None):
        self.errores.append({"etapa": etapa, "elemento": elemento,
                             "tipo": "nota", "mensaje": mensaje})


# ------------------------------------------------------------------- ids

def eid(DB, valor):
    """int -> ElementId. Revit 2027: solo existe el constructor Int64."""
    return DB.ElementId(_Int64(int(valor)))


def eid_valor(element_id):
    """ElementId -> int. Revit 2027: .Value (IntegerValue no existe)."""
    return int(element_id.Value)


def lista_ids(DB, element_ids):
    """Lista de ElementId como IList<ElementId> de .NET cuando hay CLR."""
    if _List is None:
        return list(element_ids)
    salida = _List[DB.ElementId]()
    for element_id in element_ids:
        salida.Add(element_id)
    return salida


ENTEROS_NET = ("Int64", "Int32")


def entero(valor, nombre, minimo=None, maximo=None):
    # ElementId.Value llega como System.Int64 en IronPython, que no es 'int'.
    if type(valor).__name__ in ENTEROS_NET:
        valor = int(valor)
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise ErrorEntrada("'%s' debe ser un entero" % nombre)
    if minimo is not None and valor < minimo:
        raise ErrorEntrada("'%s' debe ser >= %s" % (nombre, minimo))
    if maximo is not None and valor > maximo:
        raise ErrorEntrada("'%s' debe ser <= %s" % (nombre, maximo))
    return valor


def numero(valor, nombre, minimo=None, maximo=None, excluye_minimo=False):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErrorEntrada("'%s' debe ser un numero" % nombre)
    valor = float(valor)
    if valor != valor or valor in (float("inf"), float("-inf")):
        raise ErrorEntrada("'%s' debe ser un numero finito" % nombre)
    if minimo is not None and (valor < minimo or (excluye_minimo and valor == minimo)):
        raise ErrorEntrada("'%s' fuera de rango: minimo %s%s" % (
            nombre, minimo, " (excluido)" if excluye_minimo else ""))
    if maximo is not None and valor > maximo:
        raise ErrorEntrada("'%s' fuera de rango: maximo %s" % (nombre, maximo))
    return valor


def lista_enteros(valor, nombre):
    if not isinstance(valor, (list, tuple)) or not valor:
        raise ErrorEntrada("'%s' debe ser una lista no vacia de ids" % nombre)
    salida = []
    for item in valor:
        item = entero(item, nombre)
        if item not in salida:
            salida.append(item)
    return salida


# --------------------------------------------------------------- nombres

def nombre_enum(valor):
    """Nombre del miembro de un enum de .NET (o del doble de prueba)."""
    if valor is None:
        return None
    return str(valor).split(".")[-1]


def nombre_elemento(DB, elemento):
    """Nombre de un elemento. En IronPython el getter Name de los tipos
    solo es accesible por el descriptor de la clase base Element."""
    if elemento is None:
        return None
    descriptor = getattr(getattr(DB, "Element", None), "Name", None)
    lector = getattr(descriptor, "GetValue", None)
    if lector is not None:
        return lector(elemento)
    return getattr(elemento, "Name", None)


# -------------------------------------------------------------- unidades

def a_unidad(DB, valor_interno, unidad):
    """Unidades internas -> unidad nombrada de DB.UnitTypeId."""
    return DB.UnitUtils.ConvertFromInternalUnits(
        valor_interno, getattr(DB.UnitTypeId, unidad))


def de_unidad(DB, valor, unidad):
    """Unidad nombrada de DB.UnitTypeId -> unidades internas."""
    return DB.UnitUtils.ConvertToInternalUnits(
        valor, getattr(DB.UnitTypeId, unidad))


def punto(xyz):
    """XYZ de Revit -> tupla (x, y, z) en pies."""
    return (float(xyz.X), float(xyz.Y), float(xyz.Z))


def xyz(DB, p):
    return DB.XYZ(p[0], p[1], p[2])


def punto_m(DB, p):
    """Tupla en pies -> lista [x, y, z] en metros (redondeo a 0.1 mm)."""
    return [round(a_unidad(DB, c, "Meters"), 4) for c in p]


# ------------------------------------------------------------ documento

def elemento_por_id(DB, doc, valor):
    return doc.GetElement(eid(DB, valor))


def elementos_por_ids(DB, doc, ids, nombre):
    """Elementos de una lista de ids; aborta si falta alguno."""
    encontrados, faltan = [], []
    for valor in lista_enteros(ids, nombre):
        elemento = elemento_por_id(DB, doc, valor)
        if elemento is None:
            faltan.append(valor)
        else:
            encontrados.append(elemento)
    if faltan:
        raise ErrorEntrada("ids inexistentes en '%s': %s" % (nombre, faltan))
    return encontrados


def categoria(DB, nombre):
    if not isinstance(nombre, str) or not nombre.startswith("OST_"):
        raise ErrorEntrada("categoria invalida: %r (use un BuiltInCategory, "
                           "p. ej. OST_PlumbingFixtures)" % (nombre,))
    valor = getattr(DB.BuiltInCategory, nombre, None)
    if valor is None:
        raise ErrorEntrada("categoria desconocida en esta API: %s" % nombre)
    return valor


def instancias_de_categoria(DB, doc, nombre):
    bic = categoria(DB, nombre)
    coleccion = (DB.FilteredElementCollector(doc).OfCategory(bic)
                 .WhereElementIsNotElementType())
    return sorted(list(coleccion), key=lambda e: eid_valor(e.Id))


def resolver_tipo(DB, doc, clase, referencia, etiqueta):
    """Tipo por id (int) o por nombre exacto (str). Sin ambiguedad:
    cero o varias coincidencias de nombre son error de entrada."""
    if isinstance(referencia, bool) or referencia is None:
        raise ErrorEntrada("falta '%s' (id o nombre exacto)" % etiqueta)
    if isinstance(referencia, int):
        elemento = elemento_por_id(DB, doc, referencia)
        if elemento is None:
            raise ErrorEntrada("'%s': no existe el id %s" % (etiqueta, referencia))
        return elemento
    if not isinstance(referencia, str) or not referencia.strip():
        raise ErrorEntrada("'%s' debe ser id (entero) o nombre (texto)" % etiqueta)
    candidatos = [t for t in DB.FilteredElementCollector(doc).OfClass(clase)
                  if nombre_elemento(DB, t) == referencia]
    if not candidatos:
        raise ErrorEntrada("'%s': no hay tipo llamado '%s'" % (etiqueta, referencia))
    if len(candidatos) > 1:
        raise ErrorEntrada("'%s': nombre ambiguo '%s' (%d tipos: ids %s); pase el id" % (
            etiqueta, referencia, len(candidatos),
            [eid_valor(t.Id) for t in candidatos]))
    return candidatos[0]


def exigir_documento_editable(doc):
    if getattr(doc, "IsLinked", False):
        raise ErrorEntrada("el documento es un vinculo: no admite transacciones")
    if getattr(doc, "IsReadOnly", False):
        raise ErrorEntrada("el documento es de solo lectura")
    if getattr(doc, "IsModifiable", False):
        raise ErrorEntrada("el documento ya tiene una transaccion abierta")


# ------------------------------------------------------------ conectores

def gestor_conectores(elemento):
    """ConnectorManager de una curva MEP o de una instancia de familia."""
    gestor = getattr(elemento, "ConnectorManager", None)
    if gestor is not None:
        return gestor
    modelo = getattr(elemento, "MEPModel", None)
    if modelo is None:
        return None
    return modelo.ConnectorManager


def conectores(elemento):
    gestor = gestor_conectores(elemento)
    if gestor is None:
        return []
    return sorted(list(gestor.Connectors), key=lambda c: int(c.Id))


def es_fisico(conector):
    return nombre_enum(conector.ConnectorType) in TIPOS_FISICOS


def dominio(conector):
    crudo = nombre_enum(conector.Domain)
    return DOMINIOS.get(crudo, "otro")


def es_redondo(conector):
    return nombre_enum(conector.Shape) == "Round"


def conector_mas_cercano(elemento, p):
    """Conector fisico de tuberia mas cercano al punto p (tupla en pies)."""
    mejor, mejor_d = None, None
    for conector in conectores(elemento):
        if not es_fisico(conector) or dominio(conector) != "tuberia":
            continue
        o = punto(conector.Origin)
        d = ((o[0] - p[0]) ** 2 + (o[1] - p[1]) ** 2 + (o[2] - p[2]) ** 2) ** 0.5
        if mejor_d is None or d < mejor_d:
            mejor, mejor_d = conector, d
    return mejor


def trocear(items, desde, lote):
    """Devuelve (lote_actual, siguiente): 'siguiente' es el indice para
    continuar o None si no queda nada."""
    fin = desde + lote
    siguiente = fin if fin < len(items) else None
    return items[desde:fin], siguiente
