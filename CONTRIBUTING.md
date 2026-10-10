# Contribuir a CDCRD-Digital

Las contribuciones pueden mejorar herramientas, referencias normativas, documentación o
pruebas con ejemplos sintéticos. Antes de cambiar un módulo, revise su README, contratos de
entrada y limitaciones conocidas.

## Preparar una contribución

1. Describir el problema, el comportamiento esperado y el alcance del cambio.
2. Mantener las referencias de cláusula, volumen y página cuando se usen datos normativos.
3. Añadir una prueba que compruebe el comportamiento modificado cuando corresponda.
4. Indicar versión del programa y entorno de prueba, distinguiendo pruebas offline de
   ejecución real en Revit, ETABS o SAFE.
5. Documentar resultados y limitaciones en la propuesta de cambio.

No incluir credenciales, rutas personales, modelos, planos, miniaturas ni resultados de
proyectos en desarrollo. Los ejemplos nuevos usan datos sintéticos creados para la prueba.
Las capturas deben revisarse antes de publicarlas.

## Entorno local

Desde la raíz del repositorio, con `uv` instalado:

```powershell
.\herramientas-locales\instalar.ps1 -Pruebas
.\herramientas-locales\cdcrd.ps1 doctor
```

El instalador usa Python 3.13 y `uv.lock`. Los metadatos de
[cdcrd-local](herramientas-locales/pyproject.toml) admiten Python `>=3.11,<3.14`; la
[verificación documentada](herramientas-locales/VERIFICACION.md) define el entorno probado.
La instalación se realiza desde el código del repositorio, sin presuponer un paquete público
en un registro.

Las pruebas offline de las herramientas Revit se ejecutan desde la raíz con:

```console
python -m unittest discover -s revit-mcp-tools/tests -v
```

Las pruebas con dobles del API comprueban lógica local. Cualquier afirmación de compatibilidad
con una aplicación debe respaldarse además con evidencia de integración en esa aplicación.

## Reconocimientos

**Asistencia de código y documentación: OpenAI Codex.**

El historial de cambios y las propuestas de contribución registran el trabajo concreto.
El reconocimiento de una herramienta de asistencia no sustituye la revisión humana ni
representa una cuenta personal de GitHub.
