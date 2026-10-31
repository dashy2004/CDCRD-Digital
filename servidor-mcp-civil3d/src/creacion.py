"""Herramientas MCP de creacion nativa de objetos Civil 3D y entidades.

Capa fina sobre los metodos civil.*, estilos.*, entity.* y objects.erase del
puente .NET (HandlersCreacion.cs). Helpers puros arriba (testeables sin CAD);
registro de herramientas abajo.
"""
import json


def parsear_punto(crudo, nombre='origen'):
    """'409000,2044000' o '[409000, 2044000]' -> [x, y] (o [x, y, z])."""
    if crudo is None:
        raise ValueError(f'falta {nombre}')
    if isinstance(crudo, (list, tuple)):
        partes = list(crudo)
    else:
        texto = str(crudo).strip()
        if texto.startswith('['):
            partes = json.loads(texto)
        else:
            partes = [p for p in texto.split(',') if p.strip()]
    if len(partes) not in (2, 3):
        raise ValueError(f'{nombre} debe ser [x,y] o [x,y,z]')
    return [float(p) for p in partes]


def parsear_num(crudo, nombre):
    """'' -> None; numero o texto numerico -> float; otra cosa -> ValueError."""
    if crudo is None or crudo == '':
        return None
    try:
        return float(crudo)
    except (TypeError, ValueError):
        raise ValueError(f'{nombre} debe ser numerico, no {crudo!r}')


def parsear_handles(crudo):
    lista = [h.strip() for h in str(crudo).split(',') if h.strip()]
    if not lista:
        raise ValueError('indique al menos un handle')
    return lista


def parsear_entidades(crudo):
    datos = json.loads(crudo)
    if isinstance(datos, dict):
        datos = [datos]
    if not isinstance(datos, list) or not datos:
        raise ValueError('entidades debe ser un objeto o lista JSON no vacia')
    for i, e in enumerate(datos):
        if not isinstance(e, dict) or 'tipo' not in e:
            raise ValueError(f'elemento {i}: cada entidad es un objeto con "tipo"')
    return datos


def sin_vacios(parametros):
    return {k: v for k, v in parametros.items() if v is not None and v != ''}


def registrar(mcp, llamar, ok):
    """Registra las herramientas de creacion en el servidor MCP."""

    def pendiente(**datos):
        return ok({'error': 'operacion de escritura: repita con confirmar=True', **datos})

    @mcp.tool()
    def crear_perfil_desde_superficie(alineamiento: str, superficie: str, nombre: str,
                                      estilo: str = '', etiquetas: str = '', capa: str = '',
                                      confirmar: bool = False) -> str:
        """Crea un perfil de superficie nativo (Profile.CreateFromSurface), sin UI.

        alineamiento y superficie aceptan nombre o handle. estilo y etiquetas son
        nombres de estilo de perfil y de conjunto de etiquetas (vacio = el primero
        disponible). Idempotente: si el alineamiento ya tiene un perfil con ese
        nombre devuelve su handle con ya_existia=true.
        """
        parametros = sin_vacios(dict(alineamiento=alineamiento, superficie=superficie,
                                     nombre=nombre, estilo=estilo, etiquetas=etiquetas, capa=capa))
        if not confirmar:
            return pendiente(**parametros)
        return llamar('civil.perfil_superficie', parametros, escribe=True)

    @mcp.tool()
    def crear_perfil_constante(alineamiento: str, nombre: str, elevacion: float,
                               est_inicio: str = '', est_fin: str = '', estilo: str = '',
                               capa: str = '', confirmar: bool = False) -> str:
        """Crea un perfil de elevacion constante (CreateByLayout + 2 PVIs).

        Uso tipico: limite inferior de un hatch de vista de perfil hasta una cota
        fija (p. ej. el fondo del perfil estratigrafico). est_inicio/est_fin vacios
        cubren todo el alineamiento. Idempotente por nombre.
        """
        try:
            parametros = sin_vacios(dict(alineamiento=alineamiento, nombre=nombre,
                                         elevacion=elevacion, estilo=estilo, capa=capa,
                                         est_inicio=parsear_num(est_inicio, 'est_inicio'),
                                         est_fin=parsear_num(est_fin, 'est_fin')))
        except ValueError as exc:
            return ok({'error': str(exc)})
        if not confirmar:
            return pendiente(**parametros)
        return llamar('civil.perfil_constante', parametros, escribe=True)

    @mcp.tool()
    def crear_vista_perfil(alineamiento: str, origen: str, nombre: str,
                           estilo: str = '', banda: str = '',
                           est_inicio: str = '', est_fin: str = '',
                           elev_min: str = '', elev_max: str = '',
                           confirmar: bool = False) -> str:
        """Crea una vista de perfil (ProfileView.Create) con rangos y origen exactos.

        origen: 'x,y' o '[x,y]'. Si se dan est_*/elev_* el modo de rango pasa a
        UserSpecified y el Location se reescribe al final (fijar StationStart
        desplaza la vista; esta herramienta lo compensa). banda = nombre de un
        ProfileViewBandSetStyle (opcional). Idempotente por nombre: si ya existe,
        actualiza rangos/estilo/origen de esa vista.
        """
        try:
            parametros = sin_vacios(dict(alineamiento=alineamiento, nombre=nombre,
                                         origen=parsear_punto(origen), estilo=estilo, banda=banda,
                                         est_inicio=parsear_num(est_inicio, 'est_inicio'),
                                         est_fin=parsear_num(est_fin, 'est_fin'),
                                         elev_min=parsear_num(elev_min, 'elev_min'),
                                         elev_max=parsear_num(elev_max, 'elev_max')))
        except ValueError as exc:
            return ok({'error': str(exc)})
        if not confirmar:
            return pendiente(**parametros)
        return llamar('civil.vista_perfil', parametros, escribe=True)

    @mcp.tool()
    def agregar_hatch_vista_perfil(vista: str, nombre: str, superior: str = '',
                                   inferior: str = '', estilo_forma: str = '',
                                   quitar: bool = False, confirmar: bool = False) -> str:
        """Agrega (o quita) un relleno nativo de la vista de perfil entre dos perfiles.

        Equivale a Profile View Properties > Hatch > Cut Area: el relleno es del
        objeto vista de perfil y se actualiza si cambian los perfiles. vista,
        superior e inferior aceptan nombre o handle; estilo_forma es un ShapeStyle
        (p. ej. 'GEO - Relleno'). Para rellenar hasta una cota fija use como
        inferior un perfil de crear_perfil_constante. quitar=True elimina el
        relleno 'nombre'. Idempotente por nombre.
        """
        parametros = sin_vacios(dict(vista=vista, nombre=nombre, superior=superior,
                                     inferior=inferior, estilo_forma=estilo_forma))
        if quitar:
            parametros['quitar'] = True
        if not confirmar:
            return pendiente(**parametros)
        return llamar('civil.hatch_vista_perfil', parametros, escribe=True)

    @mcp.tool()
    def listar_estilos(familia: str = '', patron: str = '') -> str:
        """Lista estilos por familia con nombre y handle (lo que la API no dejaba leer).

        familia: subcadena del nombre de la coleccion (ProfileStyles,
        ProfileViewStyles, ShapeStyles, SurfaceStyles, ProfileLabelSetStyles...);
        vacio = todas. patron: regex sobre el nombre del estilo. La respuesta
        incluye la lista completa de familias disponibles en esta version.
        """
        return llamar('estilos.listar', sin_vacios(dict(familia=familia, patron=patron)))

    @mcp.tool()
    def crear_estilo(familia: str, nombre: str, base: str = '', confirmar: bool = False) -> str:
        """Crea un estilo por nombre en una familia; con base, clona (CopyAsSibling).

        Clonar un estilo existente (base) es la via recomendada: hereda todos los
        componentes (p. ej. el relleno SOLID de un ShapeStyle) y despues se ajusta
        color/capa con editar_estilo_display. Idempotente por nombre.
        """
        parametros = sin_vacios(dict(familia=familia, nombre=nombre, base=base))
        if not confirmar:
            return pendiente(**parametros)
        return llamar('estilos.crear', parametros, escribe=True)

    @mcp.tool()
    def editar_estilo_display(estilo: str = '', familia: str = '', handle: str = '',
                              vista: str = 'Profile', componente: str = '',
                              color_aci: str = '', color_rgb: str = '', capa: str = '',
                              tipo_linea: str = '', grosor: str = '', visible: str = '',
                              confirmar: bool = False) -> str:
        """Cambia color/capa/tipo de linea/grosor/visibilidad de un componente de estilo.

        Identifique el estilo por handle, o por familia + estilo (nombre). vista es
        el sufijo de GetDisplayStyle* (Profile, Plan, Model, Section segun el tipo
        de estilo); componente, el valor del enum (Line, CircularCurve, Shape...);
        si falta, el error lista los valores validos. color_aci: indice 0-256;
        color_rgb: 'r,g,b'. Esto resuelve el color por estrato sin UI (el color de
        una linea de perfil lo manda el estilo, no la entidad).
        """
        try:
            parametros = sin_vacios(dict(estilo=estilo, familia=familia, handle=handle,
                                         vista=vista, componente=componente, capa=capa,
                                         tipo_linea=tipo_linea, grosor=grosor,
                                         color_aci=parsear_num(color_aci, 'color_aci')))
        except ValueError as exc:
            return ok({'error': str(exc)})
        if color_rgb:
            try:
                parametros['color_rgb'] = parsear_punto(color_rgb, 'color_rgb')
            except ValueError as exc:
                return ok({'error': str(exc)})
        if visible != '':
            if visible.strip().lower() not in ('true', 'false'):
                return ok({'error': "visible debe ser 'true' o 'false'"})
            parametros['visible'] = visible.strip().lower() == 'true'
        if not confirmar:
            return pendiente(**parametros)
        return llamar('estilos.display', parametros, escribe=True)

    @mcp.tool()
    def purgar_estilos(familia: str, patron: str, confirmar: bool = False) -> str:
        """Borra los estilos de una familia cuyo nombre cumple el regex patron.

        Pensado para los huerfanos '.1' que deja el Geotechnical Modeler
        (patron=r'\\.1$'). Un estilo en uso no se borra: queda en 'fallidos' con el
        motivo. Pruebe primero el patron con listar_estilos.
        """
        parametros = dict(familia=familia, patron=patron)
        if not confirmar:
            return pendiente(**parametros)
        return llamar('estilos.purgar', parametros, escribe=True)

    @mcp.tool()
    def crear_entidad(entidades: str, confirmar: bool = False) -> str:
        """Crea entidades de dibujo por la API nativa (sin LISP y sin dialogos).

        entidades: objeto JSON o lista de objetos, cada uno con 'tipo':
          capa {nombre,color}, linea {p1,p2}, polilinea {puntos,cerrada,ancho,elevacion},
          polilinea3d {puntos,cerrada}, texto {punto,texto,altura,rotacion,centrado},
          mtexto {punto,texto,altura,ancho}, circulo {centro,radio},
          solido {p1,p2,p3,p4}, punto {punto},
          hatch {patron,contorno|contornos,escala,angulo},
          bloque {nombre,punto,escala,rotacion}.
        Comunes: capa, color (ACI o [r,g,b]), tipo_linea, grosor (mm). Devuelve el
        handle de cada entidad creada y los errores por elemento. Reemplaza a
        crear_entidades/ejecutar_lisp para dibujo (estas quedan para LISP legado).
        """
        try:
            lista = parsear_entidades(entidades)
        except (ValueError, json.JSONDecodeError) as exc:
            return ok({'error': f'entidades invalidas: {exc}'})
        if not confirmar:
            return pendiente(entidades=len(lista))
        return llamar('entity.create', {'entidades': lista}, escribe=True)

    @mcp.tool()
    def crear_dibujo(plantilla: str, confirmar: bool = False) -> str:
        """Abre un dibujo nuevo desde un DWT absoluto, conservando los anteriores.

        Requiere puente 0.5.19. Devuelve nombre activo y unidades; comprobar
        unidades Civil antes de crear geometria. No cierra ni guarda otros DWG.
        """
        if not confirmar:
            return pendiente(plantilla=plantilla)
        return llamar('doc.new', {'plantilla': plantilla}, escribe=True)

    @mcp.tool()
    def crear_bloque_3d(nombre: str, entidades: str, confirmar: bool = False) -> str:
        """Crea una definicion de bloque nativa, atomica, en coordenadas locales.

        Acepta primitivas de crear_entidad (incluida esfera {centro,radio}),
        excepto capas, hatch y referencias a otros bloques. Origen [0,0,0].
        No selecciona objetos en pantalla ni borra fuentes. Un nombre existente
        se rechaza. Insertar luego con crear_entidad tipo='bloque'.
        Requiere puente 0.5.19; toda la definicion se revierte si falla un elemento.
        """
        try:
            rows = parsear_entidades(entidades)
        except (ValueError, json.JSONDecodeError) as exc:
            return ok({'error': str(exc)})
        if not confirmar:
            return pendiente(nombre=nombre, entidades=len(rows))
        return llamar('blocks.create', {'nombre': nombre, 'entidades': rows}, escribe=True)

    @mcp.tool()
    def borrar_objeto(handles: str, confirmar: bool = False) -> str:
        """Borra objetos por handle (entidades, perfiles, vistas, estilos...).

        handles: lista separada por comas. Reemplaza el borrado por LISP. La
        respuesta separa borrados de fallidos con su motivo.
        """
        try:
            lista = parsear_handles(handles)
        except ValueError as exc:
            return ok({'error': str(exc)})
        if not confirmar:
            return pendiente(handles=lista)
        return llamar('objects.erase', {'handles': lista}, escribe=True)

    @mcp.tool()
    def orden_dibujo(handles: str, accion: str, referencia: str = '',
                     confirmar: bool = False) -> str:
        """Cambia el orden de dibujo: rellenos al fondo, etiquetas y grilla encima.

        accion: arriba | abajo | encima | debajo (encima/debajo requieren
        referencia, el handle del objeto de referencia). Es la via para que los
        rellenos del perfil estratigrafico no tapen las etiquetas de elevacion.
        """
        try:
            lista = parsear_handles(handles)
        except ValueError as exc:
            return ok({'error': str(exc)})
        parametros = sin_vacios(dict(handles=lista, accion=accion, referencia=referencia))
        if not confirmar:
            return pendiente(**parametros)
        return llamar('entity.draworder', parametros, escribe=True)

    return mcp
