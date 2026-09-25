# SAFE MCP - basado en servidor-mcp/src/oapi.py.
# CDX lote 2: exige ret=0 y no reintenta tras un retorno de error de CSI.
#
# Este modulo es la capa de compatibilidad con la OAPI de CSI (Computers and
# Structures Inc.). SAFE, ETABS y SAP2000 comparten la misma arquitectura de
# OAPI (SapModel como raiz, PropMaterial/PointObj/AreaObj/LoadPatterns/etc.
# como namespaces), por lo que este modulo es 100% reutilizable entre
# servidores: no contiene ninguna referencia a un producto en particular.
#
# Motivo de existir (igual razonamiento que en el servidor ETABS, y con mas
# razon aqui porque las firmas de SAFE no se han verificado todavia en esta
# instalacion -- ver Safe.py y diagnose_safe.py): las firmas de la OAPI
# cambian entre versiones. Codificar contra una firma supuesta produce dos
# fallos caros:
#   - excepcion COM opaca ("Parameter count mismatch") sin indicar cual metodo,
#   - peor: la llamada pasa pero con los argumentos desalineados y corrompe
#     el modelo en silencio.
#
# Este modulo centraliza tres cosas:
#   1. introspeccion real del typelib generado, para dejar de suponer firmas,
#   2. invocacion tolerante que prueba variantes conocidas en orden y reporta
#      cual funciono,
#   3. lectura del codigo de retorno y de valores [out] independiente de
#      cuantos parametros devuelva la version instalada.

import logging
from typing import Any, Sequence

logger = logging.getLogger('safe_mcp_server')


class OapiError(RuntimeError):
    """Fallo al invocar la OAPI. FastMCP lo convierte en isError."""


# ----------------------------------------------------------------------
# Lectura de resultados
# ----------------------------------------------------------------------

def ret_code(result: Any) -> int | None:
    """Extrae el codigo de retorno de una llamada OAPI.

    comtypes devuelve un int simple si el metodo no tiene parametros [out],
    o una tupla (out1, ..., outN, ret) si los tiene. El codigo de retorno de
    la OAPI es siempre el ultimo entero: 0 = exito.
    Devuelve None si la forma no es reconocible.
    """
    if isinstance(result, bool):
        return None
    if isinstance(result, int):
        return result
    if isinstance(result, (tuple, list)) and result:
        last = result[-1]
        if isinstance(last, int) and not isinstance(last, bool):
            return last
    return None


def outs(result: Any) -> tuple:
    """Devuelve los parametros [out] de una llamada, sin el codigo de retorno."""
    if isinstance(result, (tuple, list)):
        if result and isinstance(result[-1], int) and not isinstance(result[-1], bool):
            return tuple(result[:-1])
        return tuple(result)
    return ()


def find_str_list(result: Any, min_len: int = 1) -> list[str] | None:
    """Busca en un resultado OAPI la primera secuencia de strings."""
    for item in outs(result):
        if isinstance(item, (tuple, list)) and len(item) >= min_len:
            if all(isinstance(v, str) for v in item):
                return list(item)
    return None


def find_num_lists(result: Any, length: int) -> list[list[float]]:
    """Devuelve todas las secuencias numericas del resultado con longitud dada."""
    found: list[list[float]] = []
    for item in outs(result):
        if isinstance(item, (tuple, list)) and len(item) == length:
            if all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   for v in item):
                found.append([float(v) for v in item])
    return found


def find_str_lists(result: Any, length: int) -> list[list[str]]:
    """Devuelve todas las secuencias de strings del resultado con longitud dada."""
    found: list[list[str]] = []
    for item in outs(result):
        if isinstance(item, (tuple, list)) and len(item) == length:
            if all(isinstance(v, str) for v in item):
                found.append(list(item))
    return found


# ----------------------------------------------------------------------
# Invocacion tolerante
# ----------------------------------------------------------------------

def call(owner: Any, variants: Sequence[tuple[str, tuple]], what: str = "") -> Any:
    """Invoca la primera variante (metodo, args) que funcione.

    Una variante se considera exitosa si la llamada no lanza excepcion y el
    codigo de retorno es 0. Se prueban en el orden dado, asi que la variante
    mas moderna/especifica debe ir primero.

    Args:
        owner: objeto COM (ej. SapModel.PropMaterial).
        variants: lista de (nombre_metodo, tupla_de_argumentos).
        what: descripcion para el mensaje de error.

    Returns:
        El resultado crudo de la llamada que tuvo exito.

    Raises:
        OapiError con el detalle de cada intento fallido.
    """
    attempts: list[str] = []
    for method_name, args in variants:
        fn = getattr(owner, method_name, None)
        if fn is None:
            attempts.append(f"{method_name}: no existe en esta version")
            continue
        try:
            result = fn(*args)
        except Exception as e:
            attempts.append(f"{method_name}({len(args)} args): {e}")
            continue
        code = ret_code(result)
        if code == 0:
            logger.info("OAPI %s -> %s OK", what or "call", method_name)
            return result
        attempts.append(f"{method_name}({len(args)} args): ret={code}")
        # Un retorno de CSI es una respuesta, no un error de firma. No
        # repetir escrituras ni cambiar su significado tras ret != 0.
        break

    detail = "; ".join(attempts) if attempts else "sin variantes"
    raise OapiError(
        f"No se pudo ejecutar {what or 'la operacion'}. Intentos: {detail}. "
        f"Use describe_oapi para ver las firmas reales de esta instalacion."
    )


def call_checked(owner: Any, method_name: str, args: tuple, what: str = "") -> Any:
    """Invoca un unico metodo y exige ret == 0."""
    return call(owner, [(method_name, args)], what or method_name)


# ----------------------------------------------------------------------
# Introspeccion del typelib
# ----------------------------------------------------------------------

_PARAMFLAG_BITS = ((1, "in"), (2, "out"), (4, "lcid"), (8, "retval"), (16, "optional"))
_PARAMFLAG_BY_NAME = {n: b for b, n in _PARAMFLAG_BITS}

_TYPE_ALIASES = {
    "c_double": "double", "c_float": "float", "c_long": "long", "c_int": "int",
    "c_short": "short", "c_ubyte": "byte", "c_longlong": "int64",
    "c_wchar_p": "wstr", "c_char_p": "str", "VARIANT_BOOL": "bool",
}


def _type_name(t: Any) -> str:
    """Nombre legible de un tipo ctypes/comtypes."""
    if t is None:
        return "void"
    item = getattr(t, "_itemtype_", None)
    if item is not None:
        return f"SAFEARRAY({_type_name(item)})"
    pointee = getattr(t, "_type_", None)
    if isinstance(pointee, type):
        return _type_name(pointee) + "*"
    name = getattr(t, "__name__", None) or str(t)
    return _TYPE_ALIASES.get(name, name)


def _flag_names(pflags: Any) -> str:
    try:
        bits = int(pflags)
    except Exception:
        return str(pflags)
    names = [n for b, n in _PARAMFLAG_BITS if bits & b]
    return ",".join(names) if names else "none"


def _unpack_spec(entry: Any):
    """Normaliza una entrada de _methods_ / _disp_methods_.

    _ComMemberSpec (COMMETHOD/STDMETHOD) tiene 6 campos:
        (restype, name, argtypes, paramflags, idlflags, doc)
    _DispMemberSpec (DISPMETHOD/DISPPROPERTY) tiene 5 y otro layout:
        (what, name, idlflags, restype, argspec)
    Se distinguen por el primer campo: en Disp es el string "DISPMETHOD"/
    "DISPPROPERTY"; en Com es un tipo o None.
    """
    what = entry[0] if isinstance(entry, tuple) and entry else None
    if isinstance(what, str) and what.startswith("DISP"):
        _w, name, idlflags, restype, argspec = entry[:5]
        params = []
        for i, item in enumerate(argspec or ()):
            idl = item[0] if len(item) > 0 else []
            typ = item[1] if len(item) > 1 else None
            argname = item[2] if len(item) > 2 else None
            bits = sum(_PARAMFLAG_BY_NAME.get(x, 0) for x in idl)
            params.append((bits or None, argname or f"arg{i}", typ, ""))
        return name, restype, params, tuple(idlflags or ())

    restype, name, argtypes, paramflags, idlflags, _doc = (list(entry) + [None] * 6)[:6]
    params = []
    for i, atype in enumerate(argtypes or ()):
        pf = paramflags[i] if paramflags and i < len(paramflags) else None
        if pf:
            bits = pf[0]
            argname = pf[1] if len(pf) > 1 and pf[1] else f"arg{i}"
            default = f" = {pf[2]!r}" if len(pf) > 2 else ""
        else:  # STDMETHOD: no hay paramflags
            bits, argname, default = None, f"arg{i}", ""
        params.append((bits, argname, atype, default))
    return name, restype, params, tuple(idlflags or ())


def _format_method(entry: Any) -> tuple[str, str]:
    """Devuelve (nombre_plano_para_filtrar, linea_legible)."""
    name, restype, params, idlflags = _unpack_spec(entry)
    plain, kind = name or "?", ""
    for prefix, tag in (("_get_", "propget"), ("_set_", "propput"),
                        ("_setref_", "propputref")):
        if plain.startswith(prefix):
            plain, kind = plain[len(prefix):], tag
            break
    sig = ", ".join(
        f"[{_flag_names(b) if b is not None else '?'}] {n}: {_type_name(t)}{d}"
        for b, n, t, d in params)
    returns = [n for b, n, _t, _d in params if b is not None and (b & 10)]
    extra = []
    if kind:
        extra.append(kind)
    dispid = next((f for f in idlflags if isinstance(f, int)), None)
    if dispid is not None:
        extra.append(f"dispid {dispid}")
    if returns:
        extra.append("py-> (" + ", ".join(returns) + ")")
    tail = ("   [" + "; ".join(extra) + "]") if extra else ""
    return plain, f"{plain}({sig}) -> {_type_name(restype)}{tail}"


def _iter_specs(interface: Any):
    """Recolecta _methods_/_disp_methods_ propios de cada clase COM del MRO."""
    seen = set()
    for klass in getattr(interface, "__mro__", [interface]):
        if getattr(klass, "__name__", "") in (
                "IUnknown", "IDispatch", "_compointer_base", "object", "c_void_p"):
            continue
        for attr in ("_methods_", "_disp_methods_"):
            for entry in vars(klass).get(attr, ()) or ():
                if id(entry) in seen:
                    continue
                seen.add(id(entry))
                yield entry


def describe(obj: Any, filter_text: str = "") -> str:
    """Describe los metodos disponibles en un objeto COM de la OAPI.

    Si el typelib esta generado, devuelve la firma real con nombre, direccion
    y tipo de cada parametro. Si no, cae a un listado de nombres via dir().

    Esta funcion es la herramienta principal para descubrir, EN ESTA
    instalacion de SAFE, los namespaces y metodos reales de losa/zapata,
    resortes de suelo, franjas de diseño y punzonamiento que Safe.py todavia
    no expone con un metodo dedicado (ver README.md: catalogo pendiente de
    verificar).
    """
    needle = filter_text.strip().lower()
    interface = type(obj)
    com_itf = getattr(interface, "__com_interface__", interface)
    itf_name = getattr(com_itf, "__name__", str(com_itf))

    specs = list(_iter_specs(interface))
    if specs:
        total, lines = 0, []
        for entry in specs:
            try:
                plain, line = _format_method(entry)
            except Exception as e:
                lines.append(f"(entrada no interpretable: {e!r})")
                continue
            total += 1
            if needle and needle not in plain.lower():
                continue
            lines.append(line)
        if needle and not lines:
            return (f"{itf_name}: ninguno de los {total} metodos coincide con "
                    f"'{filter_text}'. Llame sin filtro para ver la lista completa.")
        header = f"{itf_name}: {len(lines)} de {total} metodo(s)"
        if needle:
            header += f" que coinciden con '{filter_text}'"
        return header + "\n" + "\n".join(sorted(lines))

    names = [n for n in dir(obj)
             if not n.startswith("_") and (not needle or needle in n.lower())]
    if not names:
        return (f"{itf_name}: sin metodos visibles"
                f"{' que coincidan con ' + filter_text if needle else ''} "
                f"(typelib no generado; solo late binding).")
    return (f"{itf_name}: {len(names)} nombre(s) (sin firma: typelib no generado)\n"
            + "\n".join(sorted(names)))


def resolve_path(model: Any, path: str) -> Any:
    """Resuelve 'PropArea', 'AreaSpring', 'Results.Setup' sobre SapModel."""
    target = model
    for part in path.split("."):
        part = part.strip()
        if not part:
            continue
        target = getattr(target, part, None)
        if target is None:
            raise OapiError(f"Ruta OAPI no valida: '{path}' (fallo en '{part}').")
    return target
