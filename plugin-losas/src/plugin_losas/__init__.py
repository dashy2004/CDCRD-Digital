"""plugin-losas: extracción de losas (Revit/AutoCAD) + usos Tabla 4 + aligeradas + visor PM.

Capa de plugin sobre ``puente-losas``: no calcula nada por su cuenta. Los
momentos salen de la vía Pieper-Martens (tablas del Ing. F. Perdomo, el método
de Losas.exe) y las reglas de carga/biblioteca del flujo AutoCAD↔Excel/ETABS
de la Ing. Arlette Ramírez, ambos ya portados y validados en ``puente_losas``.
"""
__version__ = "0.1.0"
