"""Generacion de LISP (entmake) para crear entidades en Civil 3D por el puente.

Son funciones PURAS: convierten una descripcion JSON de entidades en una
expresion AutoLISP ``(progn ... (princ))`` con ``entmakex``, sin tocar CAD ni el
puente. El servidor escribe esa expresion en un ``.lsp`` temporal y la carga con
``(load ...)``. Esa via resuelve dos limites reales del camino por ``cmd.run``:

* la linea de comandos de AutoCAD corta alrededor de 256 caracteres, asi que un
  ``entmake`` largo enviado como texto se trunca y deja a AutoCAD esperando;
* un ``.lsp`` leido por AutoCAD usa la pagina de codigos ANSI del sistema, de modo
  que escribir el temporal en ``cp1252`` hace que enes y acentos del texto
  dibujado salgan correctos (enviarlos como UTF-8 los rompe).

Nada aqui importa ``mcp`` ni abre sockets: se puede probar sin Civil 3D.
"""

from __future__ import annotations

import os
import tempfile
import time

# Alias de tipo aceptados (espanol primero; ingles por comodidad).
_TIPOS = {
    'capa': 'capa', 'layer': 'capa',
    'linea': 'linea', 'line': 'linea',
    'polilinea': 'polilinea', 'lwpolyline': 'polilinea', 'polyline': 'polilinea',
    'texto': 'texto', 'text': 'texto',
    'circulo': 'circulo', 'circle': 'circulo',
    'solido': 'solido', 'solid': 'solido',
    'punto': 'punto', 'point': 'punto',
}


def _f(valor) -> str:
    """Formatea un numero con 4 decimales; rechaza no-numericos y no-finitos."""
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        raise ValueError(f'{valor!r} no es un numero')
    if numero != numero or numero in (float('inf'), float('-inf')):
        raise ValueError(f'{valor!r} no es finito')
    return f'{numero:.4f}'


def _punto(valor, dim: int = 3) -> str:
    """Convierte [x, y] o [x, y, z] en ``(list x y [z])``."""
    if not isinstance(valor, (list, tuple)) or not (2 <= len(valor) <= 3):
        raise ValueError(f'punto {valor!r} debe ser [x, y] o [x, y, z]')
    xs = [float(v) for v in valor] + [0.0] * (3 - len(valor))
    if dim == 2:
        return f'(list {_f(xs[0])} {_f(xs[1])})'
    return f'(list {_f(xs[0])} {_f(xs[1])} {_f(xs[2])})'


def _cadena(texto) -> str:
    """Escapa una cadena para un literal LISP (barra invertida y comillas)."""
    if not isinstance(texto, str):
        raise ValueError('texto debe ser una cadena')
    return texto.replace('\\', '\\\\').replace('"', '\\"')


def _requerir(ent: dict, clave: str):
    if clave not in ent:
        raise ValueError(f'falta el campo obligatorio {clave!r}')
    return ent[clave]


def _capa_de(ent: dict) -> str:
    capa = ent.get('capa', '0')
    if not isinstance(capa, str) or not capa:
        raise ValueError("'capa' debe ser un nombre de capa no vacio")
    return _cadena(capa)


def _ent_capa(ent: dict) -> str:
    nombre = _requerir(ent, 'nombre')
    if not isinstance(nombre, str) or not nombre:
        raise ValueError("'nombre' de capa debe ser una cadena no vacia")
    color = int(ent.get('color', 7))
    if not 1 <= color <= 255:
        raise ValueError("'color' debe ser un indice ACI entre 1 y 255")
    return ('(entmakex (list (cons 0 "LAYER")(cons 100 "AcDbSymbolTableRecord")'
            '(cons 100 "AcDbLayerTableRecord")(cons 2 "%s")(cons 70 0)(cons 62 %d)))'
            % (_cadena(nombre), color))


def _ent_linea(ent: dict) -> str:
    return ('(entmakex (list (cons 0 "LINE")(cons 100 "AcDbEntity")(cons 8 "%s")'
            '(cons 100 "AcDbLine")(cons 10 %s)(cons 11 %s)))'
            % (_capa_de(ent), _punto(_requerir(ent, 'p1')), _punto(_requerir(ent, 'p2'))))


def _ent_polilinea(ent: dict) -> str:
    puntos = _requerir(ent, 'puntos')
    if not isinstance(puntos, (list, tuple)) or len(puntos) < 2:
        raise ValueError("'puntos' debe tener al menos 2 vertices")
    cerrada = 1 if ent.get('cerrada', False) else 0
    ancho = ent.get('ancho')
    cw = f'(cons 43 {_f(ancho)})' if ancho is not None else ''
    verts = ''.join(f'(cons 10 {_punto(p, dim=2)})' for p in puntos)
    return ('(entmakex (list (cons 0 "LWPOLYLINE")(cons 100 "AcDbEntity")(cons 8 "%s")'
            '(cons 100 "AcDbPolyline")(cons 90 %d)(cons 70 %d)%s%s))'
            % (_capa_de(ent), len(puntos), cerrada, cw, verts))


def _ent_texto(ent: dict) -> str:
    punto = _punto(_requerir(ent, 'punto'))
    altura = _f(_requerir(ent, 'altura'))
    texto = _cadena(_requerir(ent, 'texto'))
    rot = _f(ent.get('rotacion', 0))
    base = ('(entmakex (list (cons 0 "TEXT")(cons 100 "AcDbEntity")(cons 8 "%s")'
            '(cons 100 "AcDbText")(cons 10 %s)(cons 40 %s)(cons 1 "%s")(cons 50 %s)'
            % (_capa_de(ent), punto, altura, texto, rot))
    if ent.get('centrado', False):
        base += '(cons 72 1)(cons 11 %s)(cons 100 "AcDbText")(cons 73 0)' % punto
    return base + '))'


def _ent_circulo(ent: dict) -> str:
    return ('(entmakex (list (cons 0 "CIRCLE")(cons 100 "AcDbEntity")(cons 8 "%s")'
            '(cons 100 "AcDbCircle")(cons 10 %s)(cons 40 %s)))'
            % (_capa_de(ent), _punto(_requerir(ent, 'centro')), _f(_requerir(ent, 'radio'))))


def _ent_solido(ent: dict) -> str:
    p1, p2, p3 = _requerir(ent, 'p1'), _requerir(ent, 'p2'), _requerir(ent, 'p3')
    p4 = ent.get('p4', p3)
    return ('(entmakex (list (cons 0 "SOLID")(cons 100 "AcDbEntity")(cons 8 "%s")'
            '(cons 100 "AcDbTrace")(cons 10 %s)(cons 11 %s)(cons 12 %s)(cons 13 %s)))'
            % (_capa_de(ent), _punto(p1), _punto(p2), _punto(p3), _punto(p4)))


def _ent_punto(ent: dict) -> str:
    return ('(entmakex (list (cons 0 "POINT")(cons 100 "AcDbEntity")(cons 8 "%s")'
            '(cons 100 "AcDbPoint")(cons 10 %s)))'
            % (_capa_de(ent), _punto(_requerir(ent, 'punto'))))


_CONSTRUCTORES = {
    'capa': _ent_capa,
    'linea': _ent_linea,
    'polilinea': _ent_polilinea,
    'texto': _ent_texto,
    'circulo': _ent_circulo,
    'solido': _ent_solido,
    'punto': _ent_punto,
}


def lisp_para_entidad(ent: dict) -> str:
    """Genera la expresion ``entmakex`` de UNA entidad descrita como dict."""
    if not isinstance(ent, dict):
        raise ValueError('cada entidad debe ser un objeto JSON')
    crudo = ent.get('tipo')
    if not isinstance(crudo, str) or crudo.strip().lower() not in _TIPOS:
        raise ValueError(f'tipo desconocido: {crudo!r}; use uno de '
                         f'{sorted(set(_TIPOS.values()))}')
    return _CONSTRUCTORES[_TIPOS[crudo.strip().lower()]](ent)


def lisp_para_entidades(entidades, marca: str = 'CREAR_OK') -> str:
    """Genera ``(progn <entmakex...> (princ "<marca>"))`` para una lista de entidades.

    Lanza ValueError con el indice de la entidad que falla, sin construir nada.
    """
    if isinstance(entidades, dict):
        entidades = [entidades]
    if not isinstance(entidades, (list, tuple)) or not entidades:
        raise ValueError('entidades debe ser una lista con al menos una entidad')
    partes = []
    for i, ent in enumerate(entidades):
        try:
            partes.append(lisp_para_entidad(ent))
        except ValueError as exc:
            raise ValueError(f'entidad #{i}: {exc}') from exc
    return '(progn %s (princ "%s"))' % (''.join(partes), _cadena(marca))


def ruta_load(ruta: str) -> str:
    """Linea ``(load "...")`` con barras normales (AutoLISP acepta '/')."""
    return '(load "%s")' % ruta.replace('\\', '/')


def escribir_lisp_temporal(codigo: str, tmpdir: str | None = None,
                           max_edad_s: float = 600.0, _ahora: float | None = None) -> str:
    """Escribe ``codigo`` en un .lsp temporal y devuelve su ruta absoluta.

    El archivo se escribe en ``cp1252`` (la pagina ANSI que AutoCAD lee en un
    Windows occidental) para que enes y acentos del texto dibujado salgan bien;
    si el codigo trae caracteres fuera de cp1252 cae a ``utf-8-sig``. De paso
    borra temporales de esta carpeta con mas de ``max_edad_s`` segundos, sin
    tocar el que acaba de crear.
    """
    carpeta = tmpdir or os.path.join(tempfile.gettempdir(), 'cdcrd_lisp')
    os.makedirs(carpeta, exist_ok=True)
    ahora = time.time() if _ahora is None else _ahora
    try:
        for nombre in os.listdir(carpeta):
            if not nombre.startswith('cdcrd_') or not nombre.endswith('.lsp'):
                continue
            viejo = os.path.join(carpeta, nombre)
            try:
                if ahora - os.path.getmtime(viejo) > max_edad_s:
                    os.remove(viejo)
            except OSError:
                pass
    except OSError:
        pass
    ruta = os.path.join(carpeta, f'cdcrd_{int(ahora * 1000)}_{os.getpid()}.lsp')
    try:
        with open(ruta, 'w', encoding='cp1252') as fh:
            fh.write(codigo)
    except UnicodeEncodeError:
        with open(ruta, 'w', encoding='utf-8-sig') as fh:
            fh.write(codigo)
    return ruta
