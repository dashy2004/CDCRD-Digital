# -*- coding: utf-8 -*-
"""Muestra si el servidor de routes esta activo y en que puerto."""
__title__ = "Estado\nRevitWrite"
__doc__ = "Verifica que el servidor de routes este escuchando y en que puerto."

from pyrevit import routes, forms, script

out = script.get_output()
srv = routes.get_active_server()

if srv is None:
    forms.alert(
        "El servidor de routes NO esta activo.\n\n"
        "Revisar: pyrevit configs routes enable, y reiniciar Revit.",
        title="RevitWrite", warn_icon=True,
    )
else:
    rutas = routes.get_routes("revitwrite")
    forms.alert(
        "Servidor activo.\n\nhttp://%s:%s\n\nEndpoints en /revitwrite/: %d"
        % (srv.host or "localhost", srv.port, len(rutas)),
        title="RevitWrite",
    )
    out.print_md("### RevitWrite")
    out.print_md("- Servidor: `http://%s:%s`" % (srv.host or "localhost", srv.port))
    for r in rutas:
        out.print_md("- `%s %s`" % (r.method, r.pattern))
