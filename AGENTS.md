# CDCRD-Digital: trabajo público y reproducible

- Este repositorio es público. Publicar código, documentación, ejemplos sintéticos
  y pruebas; excluir secretos, rutas personales, material de clientes y datos privados.
- Para Civil 3D, usar API/MCP. Si falta una capacidad, implementarla y probarla
  en el puente y su herramienta MCP; no sustituirla por control de pantalla.
- Mantener aquí el código reutilizable y las instrucciones de ejecución.
  Las salidas locales y los binarios de trabajo van en carpetas ignoradas.
- Preservar cambios ajenos y registrar por separado qué se comprobó con pruebas
  automatizadas, qué se compiló y qué se ejecutó realmente dentro de CAD.
- Una instalación nueva no cambia una DLL ya cargada: comprobar versión activa
  antes de atribuir una prueba al código nuevo.
- Para BeamNG, consultar primero las APIs y repositorios originales documentados
  en `civil3d-beamng/docs/REFERENCIAS-BEAMNG.md`. Preferir dependencias externas;
  desarrollar aquí solo la integración necesaria. Si se incorpora código ajeno,
  registrar su origen, versión, licencia y cambios, conservando sus avisos.
