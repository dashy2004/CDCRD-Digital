# Revisión MEP en el modelo de Revit

En la pestaña **RevitWrite**, panel **1-Leer**, el botón **Homologar redes MEP** genera un JSON nuevo del proyecto anfitrión. Primero elija **Inventario** y escriba la revisión de la copia. El archivo identifica el proyecto, los conectores físicos de tubería con sus tipos de sistema y los circuitos de potencia con tablero, equipos servidos y carga aparente en VA cuando Revit la devuelve. El modo **Comparar manifiesto** añade las observaciones relativas al diseño previsto y al unifilar. La revisión ingresada la declara el operador.

Para la independencia pluvial/sanitaria (Sanitaria 8), cada contacto listado enlaza dos propietarios distintos de conectores físicos de tubería registrados en `AllRefs` y confirmados por `IsConnectedTo`. Se puede clasificar por el UniqueId del tipo de sistema o declarar la red prevista de un elemento. Una discrepancia deja visibles ambas procedencias. Un tipo desconocido queda pendiente. El informe identifica cruces en enlaces directos. El revisor debe seguir las redes completas a través de equipos, accesorios y tramos intermedios y comprobar su descarga exterior.

Para Eléctrica 8 y 9, el modo de comparación contrasta el circuito con el tablero y los equipos de una fila del unifilar transcrita por el revisor. La lámina proviene de esa fila. El informe distingue el circuito sin tablero, el circuito sin correspondencia y una fila del unifilar que carece de circuito de potencia en la lectura. El inventario abarca los circuitos de potencia del modelo anfitrión y excluye reservas y espacios. La carga aparente es una lectura de la API de Revit. La comprobación de demanda, protecciones y caída de tensión requiere el cálculo eléctrico.

Ejemplo sintético de manifiesto. Sustituya los identificadores marcados por los UniqueId del inventario, y copie los tres campos de origen del documento y de la revisión que desea comprobar.

```json
{
  "documento": "ejemplo.rvt",
  "proyecto_uid": "ID-PROYECTO",
  "revision": "A",
  "tipos_red": {"ID-TIPO-1": "pluvial", "ID-TIPO-2": "sanitaria"},
  "redes_previstas": {"ID-BAJANTE": "pluvial"},
  "unifilar": [
    {"circuito": "ID-CIRCUITO", "tablero": "ID-TABLERO",
     "cargas": ["ID-CARGA-1"], "lamina": "E-01"}
  ]
}
```

La comparación utiliza únicamente las correspondencias suministradas. La revisión nativa pendiente debe realizarse con una copia sintética, un contacto conocido entre dos redes y un circuito que cambie de tablero. El informe generado se puede adjuntar como fuente al expediente local indicando el elemento, circuito o par de conectores en `localizador`. En una instalación de la extensión por copia, haga accesible la carpeta que contiene el paquete `mep` mediante `REVITWRITE_MEP_DIR`, como en los otros lectores MEP.
