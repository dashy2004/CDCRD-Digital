"""Herramientas MCP de grupos de puntos COGO y superficies TIN.

Capa fina sobre los metodos puntos.* y superficie.* del puente .NET
(HandlersPuntos.cs). La membresia de un grupo se define por consulta
(StandardPointGroupQuery), no enumerando puntos: lo que se guarda en el DWG es
el patron, asi que los puntos nuevos que casen entran solos.
"""


def partir(crudo):
    """'ACERA*, CALLE*' -> ['ACERA*', 'CALLE*']; '' -> []."""
    if crudo is None:
        return []
    if isinstance(crudo, (list, tuple)):
        partes = [str(x).strip() for x in crudo]
    else:
        partes = [x.strip() for x in str(crudo).split(',')]
    return [x for x in partes if x]


def sin_vacios(parametros):
    return {k: v for k, v in parametros.items()
            if v is not None and v != '' and v != [] and v is not False}


def registrar(mcp, llamar, ok):
    """Registra las herramientas de puntos y superficies en el servidor MCP."""

    def pendiente(**datos):
        return ok({'error': 'operacion de escritura: repita con confirmar=True', **datos})

    @mcp.tool()
    def grupos_de_puntos(patron: str = '') -> str:
        """Lista los grupos de puntos con su cantidad de puntos y su consulta.

        Devuelve nombre, handle, puntos, si es el grupo de todos los puntos, la
        consulta vigente (IncludeRawDescriptions, IncludeNumbers, ...) y si tiene
        el estilo de punto sobrescrito.

        patron: subcadena para filtrar por nombre. Vacio = todos.
        """
        parametros = {}
        if patron:
            parametros['patron'] = patron
        return llamar('puntos.grupos', parametros)

    @mcp.tool()
    def crear_grupo_puntos(nombre: str, descripciones: str = '', numeros: str = '',
                           nombres_punto: str = '', excluir_descripciones: str = '',
                           excluir_numeros: str = '', todos: bool = False,
                           descripcion: str = '', estilo_punto: str = '',
                           estilo_etiqueta: str = '', case_sensitive: bool = False,
                           reemplazar: bool = True, confirmar: bool = False) -> str:
        """Crea (o reescribe) un grupo de puntos con membresia por consulta.

        descripciones: patrones de RawDescription separados por coma, con comodines
          de AutoCAD: 'TERRENO NATURAL*' tambien atrapa las que llevan espacio al
          final. Son patrones literales: esta herramienta no agrega el comodin.
        numeros: rangos de numero de punto, p. ej. '1-20,35'.
        nombres_punto: patrones de PointName. excluir_*: lo mismo para excluir.
        todos: IncludeAllPoints (todo el dibujo); se combina con los excluir_*.
        estilo_punto / estilo_etiqueta: nombres de estilo; al indicarlos se activa
          el override del grupo (IsPointStyleOverridden) y los simbolos de esos
          puntos cambian en el dibujo.
        reemplazar: si el grupo ya existe, reescribe su consulta (por defecto si).

        Idempotente por nombre. Devuelve el conteo de puntos que resolvio Civil 3D,
        no uno calculado aqui.
        """
        if not nombre.strip():
            return ok({'error': 'falta nombre del grupo'})
        incluye = partir(descripciones) or partir(numeros) or partir(nombres_punto)
        if not incluye and not todos:
            return ok({'error': 'indique descripciones, numeros, nombres_punto o todos=True'})
        parametros = sin_vacios(dict(
            nombre=nombre.strip(),
            descripciones=partir(descripciones),
            numeros=partir(numeros),
            nombres_punto=partir(nombres_punto),
            excluir_descripciones=partir(excluir_descripciones),
            excluir_numeros=partir(excluir_numeros),
            todos=todos,
            descripcion=descripcion,
            estilo_punto=estilo_punto,
            estilo_etiqueta=estilo_etiqueta,
            case_sensitive=case_sensitive))
        parametros['reemplazar'] = bool(reemplazar)
        if not confirmar:
            return pendiente(**parametros)
        return llamar('puntos.grupo_crear', parametros, escribe=True)

    @mcp.tool()
    def crear_superficie(nombre: str, estilo: str = '', capa: str = '',
                         confirmar: bool = False) -> str:
        """Crea una superficie TIN vacia (TinSurface.Create), sin UI.

        estilo: nombre de estilo de superficie (vacio = el estilo por defecto del
        dibujo). capa: se crea si no existe. Idempotente por nombre: si ya hay una
        superficie con ese nombre devuelve su handle con ya_existia=true.

        Para alimentarla use superficie_agregar_grupos (grupos de puntos) o
        inspeccionar_objeto con ruta='BreaklinesDefinition' / 'ContoursDefinition'
        para el resto de las definiciones.
        """
        if not nombre.strip():
            return ok({'error': 'falta nombre de la superficie'})
        parametros = sin_vacios(dict(nombre=nombre.strip(), estilo=estilo, capa=capa))
        if not confirmar:
            return pendiente(**parametros)
        return llamar('superficie.crear', parametros, escribe=True)

    @mcp.tool()
    def superficie_agregar_grupos(superficie: str, grupos: str, rebuild: bool = True,
                                  confirmar: bool = False) -> str:
        """Agrega grupos de puntos a la definicion de una superficie TIN y reconstruye.

        superficie: nombre o handle. grupos: nombres separados por coma.
        Equivale a Surface > Definition > Point Groups en la UI, asi que la
        superficie queda ligada a los grupos: al entrar puntos nuevos al grupo,
        basta reconstruir.

        Devuelve las estadisticas que reporta Civil 3D (puntos, triangulos, cotas
        minima y maxima) tras el rebuild.
        """
        lista = partir(grupos)
        if not superficie.strip():
            return ok({'error': 'falta la superficie'})
        if not lista:
            return ok({'error': 'indique al menos un grupo de puntos'})
        parametros = {'superficie': superficie.strip(), 'grupos': lista, 'rebuild': bool(rebuild)}
        if not confirmar:
            return pendiente(**parametros)
        return llamar('superficie.grupos', parametros, escribe=True)
