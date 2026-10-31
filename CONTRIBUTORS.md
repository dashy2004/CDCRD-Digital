# Colaboración y créditos

El mantenimiento del proyecto corresponde a [dashy2004](https://github.com/dashy2004).
Las contribuciones concretas se identifican en los commits y pull requests.

## Personas

| Persona | Rol | Contribución |
|---|---|---|
| **Emil Guillen De la Cruz** ([dashy2004](https://github.com/dashy2004)) | Mantenedor | Dirección del proyecto, transcripción y verificación normativa, revisión y fusión de cambios, pruebas reales en Revit, ETABS, SAFE y Civil 3D. |
| **Rodolfo** (perfil de GitHub por confirmar) | Colaborador | Línea base del puente .NET y servidor MCP de Civil 3D, creación nativa de objetos, exportación sin diálogos, vistas 3D y perfil estratigráfico por receta (octubre de 2026). |

Para figurar en esta tabla, o en el panel de contribuidores de GitHub, hay dos vías
que se combinan:

- **Commits con su cuenta.** GitHub solo cuenta los commits cuyo correo está vinculado
  a una cuenta. Configure `git config user.email` con un correo registrado en su perfil.
- **Trailer `Co-authored-by`.** Cuando una persona participa en un cambio que confirma
  otra, el commit lleva al final una línea por cada coautor:

  ```
  Co-authored-by: Nombre Apellido <correo-vinculado-a-github@ejemplo.com>
  ```

  GitHub muestra al coautor en el commit y lo acredita en el gráfico de contribuidores.

Al abrir un pull request, añada su fila a esta tabla si aún no está. El mantenedor la
revisa junto con el cambio.

Para citar el proyecto en un trabajo, use los datos de [CITATION.cff](CITATION.cff)
(GitHub muestra el botón "Cite this repository" en la barra lateral).

## Asistentes de IA

| Colaborador | Contribución |
|---|---|
| **Codex (OpenAI)** | Asistencia de desarrollo: catálogo y diagnóstico común, validador Civil 3D → BeamNG, recibos unificados, pruebas y documentación de estas entregas. Los commits correspondientes llevan autoría identificable de Codex. |
| **Claude (Anthropic)** | Asistencia de desarrollo reconocida en el historial del repositorio y en CONTRIBUTING.md. |

El crédito de los asistentes describe su participación como herramientas de IA;
no representa una cuenta personal de GitHub ni sustituye la revisión humana.
Véanse [las reglas para contribuir](CONTRIBUTING.md).

Las ramas nuevas usan nombres del trabajo, por ejemplo
`feat/recibos-civil3d-beamng`, sin prefijos del asistente.
