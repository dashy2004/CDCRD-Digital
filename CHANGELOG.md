# Registro de cambios

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
Cada entrada enlaza el pull request que la introdujo; el detalle técnico y las
pruebas están en la descripción del PR y en el README del módulo.

Las versiones se etiquetan en `master` con el prefijo `v` y se publican como releases de
GitHub con estas mismas notas. Lo que aún no tiene versión va bajo "Sin publicar".

## Sin publicar

Nada todavía.

## [0.1.0] - 2026-10-31

Primera versión etiquetada. Reúne todo lo fusionado en `master` desde la apertura del
repositorio: la capa normativa con verificación de integridad, los servidores MCP de
Revit, ETABS, SAFE, Civil 3D y AutoCAD, el puente Civil 3D a BeamNG y la base documental
del repositorio. Los PRs abiertos en esta fecha (losas, memorias de diseño, estándar de
planos, README de instalación) quedan para la siguiente versión.

### Base del repositorio

- Licencia Apache 2.0 para el código, con NOTICE que separa el texto normativo del
  MIVHED; CITATION.cff; política de seguridad; plantillas de issue y PR; Dependabot;
  badges en el README; créditos de personas en CONTRIBUTORS.md.

### Civil 3D y AutoCAD

- Cubicaciones TIN y QTO nativo por regiones (0.5.22)
  ([#39](https://github.com/dashy2004/CDCRD-Digital/pull/39)).
- Targets de ancho y cota en corredor nuevo
  ([#38](https://github.com/dashy2004/CDCRD-Digital/pull/38)).
- Múltiples baselines, regiones y secciones por API
  ([#37](https://github.com/dashy2004/CDCRD-Digital/pull/37)).
- Espirales nativas SCS con pruebas y capturas reales
  ([#36](https://github.com/dashy2004/CDCRD-Digital/pull/36)).
- Peraltes por tabla, transporte corregido y evidencia nativa
  ([#35](https://github.com/dashy2004/CDCRD-Digital/pull/35)).
- Cunetas y bermas nativas con pruebas y capturas reales (0.5.17)
  ([#34](https://github.com/dashy2004/CDCRD-Digital/pull/34)).
- Validación de unidades métricas del dibujo y las secciones
  ([#4](https://github.com/dashy2004/CDCRD-Digital/pull/4)).
- API COGO, Survey, taludes y portada con evidencia
  ([#3](https://github.com/dashy2004/CDCRD-Digital/pull/3)).

### Civil 3D → BeamNG

- Recibos unificados de exportación
  ([#10](https://github.com/dashy2004/CDCRD-Digital/pull/10)).
- Validador de intercambios Civil 3D a BeamNG
  ([#8](https://github.com/dashy2004/CDCRD-Digital/pull/8)).

### ETABS

- Contratos corregidos tras captura nativa; informe admitido sin referencia de diseño
  ([#13](https://github.com/dashy2004/CDCRD-Digital/pull/13)).
- Captura de solo lectura e informe del auditor
  ([#11](https://github.com/dashy2004/CDCRD-Digital/pull/11)).

### Revit y losas

- UsoLosa sin regeneración explícita y con guardado verificado
  ([#12](https://github.com/dashy2004/CDCRD-Digital/pull/12)).
- Puente de losas Revit → motor FEM (EstructurasRD) → Excel/ETABS
  ([#5](https://github.com/dashy2004/CDCRD-Digital/pull/5)).
- Auditoría MEP de Revit e informe BIM con evidencia trazable
  ([#1](https://github.com/dashy2004/CDCRD-Digital/pull/1)).

### Transversal

- Catálogo de capacidades y diagnóstico unificado
  ([#7](https://github.com/dashy2004/CDCRD-Digital/pull/7)).
- Ejemplos de herramientas publicados; expedientes BIM privados separados del repo
  ([#2](https://github.com/dashy2004/CDCRD-Digital/pull/2)).

[0.1.0]: https://github.com/dashy2004/CDCRD-Digital/releases/tag/v0.1.0
