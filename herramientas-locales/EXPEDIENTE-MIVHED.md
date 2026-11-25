# Expediente multidisciplinario del MIVHED

El comando inventaría las plantillas técnicas, administrativas y jurídicas de una extracción local del portal NORM. Para un proyecto puede registrar declaraciones de revisión con la hoja, el elemento o la página que aporta la evidencia. El resultado contiene trazabilidad documental para el responsable de la revisión.

```powershell
.\cdcrd.ps1 expediente-mivhed --esquemas .\esquemas --corpus .\mivhed-norm-checklists.json --evidencias .\expediente\evaluaciones.json
```

Para obtener todos los esquemas públicos desde PowerShell, ejecute `.\descargar-esquemas-mivhed.ps1 -Destino .\esquemas` en esta carpeta. El script comprueba cada identidad, registra fecha y SHA-256 y publica la captura en un directorio nuevo. Para una descarga manual, guarde cada respuesta oficial de `/api/public/schemas/templates/<templateVersionId>` como `schema<ID>.json` en el directorio de esquemas. El comando también funciona con alguno de esos esquemas por separado. Al pasar el corpus del PR 82, requiere el mismo conjunto de plantillas incluidas en el corpus, comprueba identidad, versión, ítems y referencias, y compara las opciones reproducidas con el esquema. Las referencias enlazadas a versiones archivadas llevan la marca original del corpus. Sin corpus el estado se consigna como desconocido. El esquema determina las respuestas y los motivos obligatorios. El número de versión y el ID nativo del ítem quedan en el informe para que se pueda repetir el análisis.

**Ejemplo sintético de manifiesto**

```json
{
  "evaluaciones": [
    {
      "criterio": "CHECK-SANITARIA#8",
      "templateVersionId": 48,
      "respuesta": "cumple",
      "justificacion": "El responsable cotejó las dos redes en la sección indicada.",
      "fuentes": [
        {"archivo": "evidencias/lamina-sintetica.pdf", "localizador": "HS-02, sección A"}
      ]
    }
  ]
}
```

Los archivos de respaldo se resuelven dentro de la carpeta del manifiesto. El informe registra su SHA-256. La fuente puede incluir un campo `sha256` para exigir una edición específica. El campo `localizador` indica dónde contrastar la declaración. El revisor aporta el juicio técnico. Los archivos y los informes de expedientes reales deben mantenerse en el proyecto privado.

Las opciones normalizadas son `cumple`, `no_cumple` y, donde lo permite el esquema, `no_aplica`. Para respuestas condicionadas use `"motivos": ["número oficial"]`. Los motivos admitidos y los casos que los requieren aparecen en el inventario sin evaluaciones. Este registro de auditoría pide justificar una declaración de no aplicabilidad y respeta el campo oficial de nota obligatoria para un incumplimiento. Una evaluación con problemas devuelve el código de salida 1. El inventario o un manifiesto documentado devuelve 0. Una entrada incompatible devuelve 2. Una fila sin evaluación conserva ese estado hasta recibir una declaración propia.
