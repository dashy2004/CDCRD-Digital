"""Etapa 4: herramientas del Geotechnical Modeler (GM) y diagnostico de dialogos.

Capa fina sobre los handlers gm.* y diag.dialogos del puente (v0.5.0+). El
trabajo pesado (reflexion sobre los ensamblados Aecc.Gtm.* cargados en el
proceso de Civil 3D) vive en puente/HandlersGm.cs.

Requisitos del lado CAD: el bundle del GM cargado y, para gm_crear_perfil_
sondeos / gm_construir_superficies / gm_3d_boreholes, un proyecto GM activo
(settings guardados en el dibujo). Todos los datos geotecnicos son
hipoteticos/preliminares.
"""

AVISO = 'Datos geotecnicos hipoteticos/preliminares; no sustituyen un estudio geotecnico.'


def registrar(mcp, llamar, ok):
    """Registra las herramientas gm_* y eventos_dialogo en el servidor MCP."""

    def pendiente(**datos):
        return ok({'error': 'operacion de escritura: repita con confirmar=True', **datos})

    @mcp.tool()
    def gm_diagnosticar() -> str:
        """Diagnostico del Geotechnical Modeler: que falta para que funcione.

        Revisa ensamblados cargados, contenedor IoC, Application.config,
        la superficie 'GM - Top Surface', las superficies con sufijo .1, los
        estilos de nombre fijo que GM exige, los hatches huerfanos del
        sticklog, los grupos con miembros borrados (causa real del
        NullReferenceException de DeleteStickLogProfile) y el ProjectId
        guardado en el dibujo.
        """
        return llamar('gm.diagnosticar', {})

    @mcp.tool()
    def gm_reparar(aplicar: bool = False, renombrar_sufijo_1: bool = True,
                   borrar_hatches_huerfanos: bool = False, borrar_grupos_muertos: bool = False,
                   confirmar: bool = False) -> str:
        """Repara lo reparable del estado del GM en el dibujo.

        Por defecto SIMULA (aplicar=False) y lista las acciones. Con
        aplicar=True: renombra superficies 'GM - ... .1' a su nombre base
        cuando el base no existe; si se pide borra los hatches huerfanos de
        la capa GM-PROF-STICKLOG-2D; y con borrar_grupos_muertos borra los
        grupos vacios cuyo nombre empieza por "GM - " y los grupos de
        ACAD_GROUP con miembros borrados atribuibles al GM (causa real del
        NullReferenceException de DeleteStickLogProfile). Un grupo con
        miembros vivos fuera de capas GM-* se reporta y no se toca.
        """
        if not confirmar:
            return pendiente(aplicar=aplicar)
        return llamar('gm.reparar', {'aplicar': aplicar,
                                     'renombrar_sufijo_1': renombrar_sufijo_1,
                                     'borrar_hatches_huerfanos': borrar_hatches_huerfanos,
                                     'borrar_grupos_muertos': borrar_grupos_muertos},
                      escribe=True)

    @mcp.tool()
    def gm_crear_perfil_sondeos(alineamiento: str, vista: str = '', origen: str = '',
                                exageracion: float = 4.0, estacion_inicio: str = '',
                                estacion_fin: str = '', superficie_top: str = 'GM - Top Surface',
                                solo_perfil: bool = False, confirmar: bool = False) -> str:
        """Perfil de sondeos del GM (CreateStickLogProfile + diagrama de sticklogs).

        Reproduce el flujo del panel Subsurface Profiles sin UI: borra los
        perfiles del alineamiento, crea/reusa la vista, perfiles de estratos y
        sticklogs con los sondeos del proyecto GM activo. origen '[x,y]' es
        obligatorio si la vista no existe. Si CreateStickLogProfile falla, la
        respuesta trae la excepcion completa (evidencia del bug del GM); con
        GM_DebugLogging_On activo el log del GM dice el paso exacto.
        solo_perfil=True se detiene tras CreateStickLogProfile.
        """
        if not confirmar:
            return pendiente(alineamiento=alineamiento, vista=vista)
        import json as _json
        parametros = {'alineamiento': alineamiento, 'exageracion': exageracion,
                      'superficie_top': superficie_top, 'solo_perfil': solo_perfil,
                      'hatch_geologia': False}
        if vista:
            parametros['vista'] = vista
        if origen:
            try:
                parametros['origen'] = _json.loads(origen)
            except ValueError:
                return ok({'error': "origen debe ser '[x,y]'"})
        for clave, v in (('estacion_inicio', estacion_inicio), ('estacion_fin', estacion_fin)):
            if v != '':
                parametros[clave] = float(v)
        return llamar('gm.perfil_sondeos', parametros, escribe=True)

    @mcp.tool()
    def gm_construir_superficies(superficie_fondo: bool = False, confirmar: bool = False) -> str:
        """Construye las superficies de estrato del GM (StratumService.BuildStratumSurfaces).

        Equivale al boton Build Surfaces del GM. superficie_fondo=True crea
        ademas la superficie del fondo de los sondeos.
        """
        if not confirmar:
            return pendiente()
        return llamar('gm.superficies', {'superficie_fondo': superficie_fondo}, escribe=True)

    @mcp.tool()
    def gm_3d_boreholes(altura_rotulo: float = 2.0, diametro: float = 2.0,
                        exageracion: float = 1.0, campo_geologia: str = 'GeologyCode',
                        confirmar: bool = False) -> str:
        """Sondeos 3D nativos del GM (Borehole3DService.Create3DBoreholes)."""
        if not confirmar:
            return pendiente()
        return llamar('gm.3d_boreholes', {'altura_rotulo': altura_rotulo, 'diametro': diametro,
                                          'exageracion': exageracion,
                                          'campo_geologia': campo_geologia}, escribe=True)

    @mcp.tool()
    def gm_stratum_display(usar_exageracion: str = '', exageracion: str = '',
                           tipo_superficie: str = 'FullStratum', confirmar: bool = False) -> str:
        """Lee (y opcionalmente aplica) la visibilidad/exageracion de las superficies GM.

        Sin parametros devuelve los settings actuales. Con usar_exageracion
        ('true'/'false') y/o exageracion (numero) los aplica al tipo indicado
        (FullStratum o Lens); eso requiere confirmar=True.
        """
        parametros = {'tipo_superficie': tipo_superficie}
        escribe = False
        if usar_exageracion != '':
            parametros['usar_exageracion'] = usar_exageracion.strip().lower() == 'true'
            escribe = True
        if exageracion != '':
            parametros['exageracion'] = float(exageracion)
            escribe = True
        if escribe and not confirmar:
            return pendiente()
        return llamar('gm.stratum_display', parametros, escribe=escribe)

    @mcp.tool()
    def eventos_dialogo() -> str:
        """Detecta dialogos modales abiertos en Civil 3D (diag.dialogos).

        modal_abierto=true significa que una ventana modal tiene bloqueada la
        ventana principal: las peticiones al puente venceran por timeout hasta
        que alguien cierre ese dialogo. Lista las ventanas candidatas.
        """
        return llamar('diag.dialogos', {})
