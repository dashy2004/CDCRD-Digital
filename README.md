<h1 align="center">CDCRD-Digital</h1>
<p align="center"><strong>Normativa trazable · Automatización BIM · Pruebas en las aplicaciones</strong></p>
<p align="center">Del Código de Construcción dominicano a flujos reproducibles en Civil 3D, AutoCAD, Revit, ETABS y SAFE.</p>

<p align="center">
  <a href="#instalar"><img src="docs/assets/nav/instalar.svg" alt="INSTALAR" height="34"></a>
  <a href="servidor-mcp-civil3d/README.md"><img src="docs/assets/nav/civil3d.svg" alt="CIVIL 3D" height="34"></a>
  <a href="#capturas-y-resultados"><img src="docs/assets/nav/galeria.svg" alt="CAPTURAS" height="34"></a>
  <a href="datos/INDICE.md"><img src="docs/assets/nav/normativa.svg" alt="NORMATIVA" height="34"></a>
  <a href="#documentación"><img src="docs/assets/nav/docs.svg" alt="DOCUMENTACIÓN" height="34"></a>
</p>

<p align="center">
  <a href="https://github.com/dashy2004/CDCRD-Digital/actions/workflows/verify.yml"><img src="https://github.com/dashy2004/CDCRD-Digital/actions/workflows/verify.yml/badge.svg" alt="Verificaciones del repositorio"></a>
  <a href="datos/INDICE.md"><img src="https://img.shields.io/badge/CDCRD-5_volúmenes_·_6%2C580_cláusulas-176349" alt="Normativa: 5 volúmenes y 6580 cláusulas"></a>
  <a href="servidor-mcp-civil3d/docs/PARTIDAS-0523.md"><img src="https://img.shields.io/badge/Civil_3D-entrega_0.5.23-165c85" alt="Civil 3D: entrega 0.5.23"></a>
</p>

![CDCRD-Digital: normativa y automatización BIM](docs/assets/banner-cdcrd-digital.png)

## Empieza aquí

| Quiero… | Abrir |
|---|---|
| Consultar una cláusula, tabla o referencia al PDF | [Índice normativo](datos/INDICE.md) |
| Instalar las herramientas y conectar mi asistente | [Inicio rápido](#instalar) · [Instalación con IA](INSTALAR-CON-IA.md) |
| Automatizar carreteras, superficies o cantidades | [Civil 3D: guía y herramientas](servidor-mcp-civil3d/README.md) |
| Trabajar con edificios y cálculo estructural | [Revit](revit-mcp-tools/) · [ETABS](servidor-mcp/) · [SAFE](servidor-mcp-safe/) |
| Generar DXF, revisar IFC/IDS o consultar datos localmente | [Herramientas locales](herramientas-locales/README.md) |

<a id="instalación-y-paquetes"></a>
## Instalar

Descarga el repositorio, abre su carpeta en PowerShell y ejecuta el menú:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\instalar-cdcrd.ps1
```

El menú ofrece diagnóstico, instalación y configuración del asistente. Los conectores de escritorio requieren la aplicación correspondiente. [Requisitos y pasos](instalacion/INSTALACION.md) · [Opciones sin menú](INSTALAR-CON-IA.md).

<a id="civil-3d-resultados-reproducibles"></a>
<a id="civil-3d-y-autocad-capturas-y-pruebas-nativas"></a>
<a id="ejemplos-de-herramientas"></a>
## Capturas y resultados

**Civil 3D 0.5.23: partidas de pago QTO.** Catálogo CSV, asignaciones y resumen nativo por API: **3 unidades · 35 m · 200 m² · 24 m³**. [Ver prueba, contrato y límites](servidor-mcp-civil3d/docs/PARTIDAS-0523.md).

![Resumen nativo QTO de cuatro partidas sintéticas en Civil 3D](servidor-mcp-civil3d/docs/images/civil3d-partidas-report-0523.png)

| Targets de ancho y cota | Cubicaciones por secciones |
|---|---|
| [![Targets en corredor nativo](servidor-mcp-civil3d/docs/images/civil3d-targets-planta-0521.png)](servidor-mcp-civil3d/docs/TARGETS-0521.md) | [![Secciones y cubicaciones nativas](servidor-mcp-civil3d/docs/images/civil3d-qto-a1-0522.png)](servidor-mcp-civil3d/docs/QTO-0522.md) |
| [8 asignaciones y 74 muestras verificadas](servidor-mcp-civil3d/docs/TARGETS-0521.md) | [Cuatro regiones y cuatro materiales](servidor-mcp-civil3d/docs/QTO-0522.md) |

Capturas reales del área gráfica de Civil 3D, con ejemplos sintéticos. La tabla QTO es un objeto del DWG poblado desde el XML nativo. Cada informe documenta sus pruebas y pendientes.

**[Galería completa de Civil 3D](servidor-mcp-civil3d/docs/GALERIA.md)** · [Revisión BIM](docs/ejemplos/revision-bim.md) · [DXF y ejemplos ETABS](README-AMPLIADO.md#ejemplos-de-herramientas)

<a id="los-servidores-mcp"></a>
## Herramientas y alcance

| Área | Qué encontrarás | Evidencia y documentación |
|---|---|---|
| **Civil 3D / AutoCAD** | Puntos, superficies, ejes, perfiles, corredores, secciones, targets, cubicaciones y partidas | [Guía Civil](servidor-mcp-civil3d/README.md) · [Adaptación AutoCAD](servidor-mcp-civil3d/docs/AUTOCAD-0511.md) |
| **Revit** | Lectura, modelado, documentación y auditoría BIM | [Herramientas](revit-mcp-tools/) · [Escritura](revit-mcp-write/) |
| **ETABS / SAFE** | Modelo, análisis y resultados mediante sus APIs | [ETABS](servidor-mcp/) · [SAFE](servidor-mcp-safe/) |
| **Intercambios** | Validación de unidades, coordenadas e identificadores | [Civil 3D → BeamNG](civil3d-beamng/docs/VALIDACION-INTERCAMBIOS.md) |

Las comprobaciones automáticas del repositorio y las pruebas en una aplicación son evidencias distintas. Los informes indican versión, caso probado y límites; no sustituyen la revisión del profesional responsable.

<a id="cobertura-de-la-capa-normativa"></a>
## Normativa

**5 volúmenes · 34 títulos · 6,580 cláusulas**, con volumen, cláusula y página de origen. [Explorar el corpus](datos/INDICE.md) · [Cobertura y método de verificación](README-AMPLIADO.md#cobertura-de-la-capa-normativa) · [Reglamentos complementarios](corpus-reglamentos/README.md).

La fuente es el MIVHED. Esta digitalización no es un documento oficial: ante una diferencia, prevalece el PDF oficial citado.

<a id="documentacion-tecnica"></a>
## Documentación

| Para… | Guía |
|---|---|
| Entender el conjunto de herramientas | [Arquitectura del ecosistema](docs/ARQUITECTURA-ECOSISTEMA.md) |
| Revisar contratos de datos | [Esquema normativo](docs/ESQUEMA.md) · [Proyecto JSON](docs/ESQUEMA-PROYECTO.md) |
| Desarrollar o verificar resultados | [Guía técnica](docs/TECNICO.md) · [Método de trabajo con IA](docs/TRABAJAR-CON-IA.md) |
| Consultar ejemplos e historial detallado | [Referencia ampliada](README-AMPLIADO.md) · [Civil 3D: referencia](servidor-mcp-civil3d/REFERENCIA.md) |

## Comunidad y datos

[Contribuir](CONTRIBUTING.md) · [Colaboradores](CONTRIBUTORS.md) · [Seguridad](SECURITY.md) · [Criterio de publicación](docs/PRESENTACION.md).

Solo publicamos ejemplos sintéticos revisados. Los modelos, credenciales y datos de proyectos privados permanecen fuera del repositorio.

**Desarrollo asistido por OpenAI Codex y Anthropic Claude**, con contribuciones identificadas en el historial. [Reconocimientos existentes](README-AMPLIADO.md#constructoras-que-confían-en-este-programa).
