# Política de seguridad

## Alcance

Este repositorio contiene servidores MCP y plugins que ejecutan código local contra
Revit, ETABS, SAFE, Civil 3D y AutoCAD, además de datos normativos. Un fallo de
seguridad puede significar:

- ejecución de código no previsto en la máquina del usuario desde un servidor MCP;
- lectura o escritura de archivos fuera de las carpetas del proyecto abierto;
- alteración silenciosa del texto normativo o de las tablas de cálculo
  (la integridad se verifica con `tools/verify_normative.py` y `normativa-lock.json`);
- credenciales, rutas personales o datos de proyectos reales dentro del repositorio.

## Versiones con soporte

| Rama o versión | Soporte |
|---|---|
| `master` | Sí: recibe correcciones. |
| Ramas `feat/*`, `fix/*`, `docs/*` | Solo mientras su PR esté abierto. |

## Cómo reportar una vulnerabilidad

No abra un issue público con los detalles.

1. Use el reporte privado de GitHub: pestaña **Security** → **Report a vulnerability**
   en <https://github.com/dashy2004/CDCRD-Digital/security/advisories/new>.
2. Incluya: módulo afectado, versión del programa (Revit, ETABS, etc.), pasos para
   reproducir con datos sintéticos, impacto estimado y, si la tiene, una corrección
   propuesta.
3. Recibirá acuse en un plazo de 7 días. La corrección se publica en `master` con
   una nota en el CHANGELOG y, si procede, un aviso de seguridad en GitHub.

Si encuentra un secreto o un dato de proyecto real en el historial, repórtelo por la
misma vía: se rota el secreto y se limpia el contenido antes de hacerlo público.

## Buenas prácticas para contribuidores

- Nunca incluya credenciales, tokens ni archivos `.env`; use variables de entorno.
- No agregue modelos, planos ni resultados de proyectos en desarrollo. Los ejemplos
  usan datos sintéticos.
- Los servidores MCP deben rechazar rutas fuera de la carpeta de trabajo y no deben
  ejecutar comandos construidos a partir de texto sin validar.
- Cualquier cambio en `datos/`, `md/`, `corpus-reglamentos/` o `verificacion-vols/`
  debe pasar la verificación normativa en CI y la revisión del propietario
  (`.github/CODEOWNERS`).
