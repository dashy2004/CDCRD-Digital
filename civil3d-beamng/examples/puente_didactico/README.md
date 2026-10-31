# Puente didáctico: primer modelo estructural

Modelo sintético de cuatro vigas longitudinales independientes, luz de 20 m y
sección rectangular de 0.45 × 1.00 m. Sirve para mostrar apoyos, deformada y
respuesta a una carga estática uniforme de 10 kN/m por viga. Las dimensiones y
la carga son supuestos didácticos, sin comprobación de capacidad ni normativa.

La primera versión no incluye losa que distribuya cargas, diafragmas, tráfico
móvil, impacto, sismo, fatiga, cimentaciones ni dimensionamiento. Tampoco conecta
las fuerzas de BeamNG con ETABS. Los apoyos representan articulación/rodillo con
restricción torsional mínima. El peso propio está desactivado para permitir la
comprobación manual de un único caso.

## Preparación y ejecución

Requiere ETABS 23 instalado y .NET 10. El código usa la DLL OAPI local de CSI;
no redistribuye esa DLL. Compilar con `dotnet build -c Release` en esta carpeta.
Si la instalación está en otra ruta, usar `-p:EtabsInstallDir=...` al compilar
y la variable `ETABS_INSTALL_DIR` al ejecutar.

Sin argumentos, `dotnet run -c Release` solo imprime el plan y resultados
analíticos esperados. No inicia ETABS. Para una ejecución autorizada y con el
turno de ETABS coordinado, pasar `--apply` y una carpeta absoluta nueva.
Conserva los procesos existentes, exige identificar un proceso nuevo único y se
conecta por su PID antes de escribir. Rechaza un modelo con nombre en esa instancia.
La aplicación nueva se conserva abierta para revisar. Ante fallo conserva el
diagnóstico y exige inspección antes de repetir.

El ejecutor exige códigos OAPI correctos, guarda antes del análisis y compara
las reacciones con equilibrio: 100 kN por apoyo, total 800 kN. La flecha central
de referencia Euler-Bernoulli es 0.022222 m; la tolerancia del 2% permite la
contribución del cortante. Es un control de este ejemplo, no una aceptación de
servicio o seguridad. `receipt.json` solo se produce tras pasar esas comprobaciones.

**Estado comprobado el 2026-10-31:** compilación sin advertencias ni errores y
ejecución nativa en ETABS 23.3.0, en una instancia nueva conservando la anterior.
Ocho elementos, ocho apoyos y cuatro puntos centrales. Reacciones verticales de
100 kN por apoyo, suma 800.0000000000001 kN. Desplazamiento central de
−0.022350222240142246 m, diferencia del 0.576% frente a Euler-Bernoulli. La
contribución analítica del cortante es 0.000128 m y explica esa diferencia.
Modelo y recibo guardados localmente. Reapertura y acoplamiento con BeamNG pendientes.

## Continuación

La geometría visual del tablero podrá añadirse a la escena como objeto rígido.
El análisis especializado de puentes con SAP2000/CSiBridge y el intercambio de
cargas se desarrollarán y validarán por separado. ETABS está orientado a edificios:
[fuente CSI](https://www.csiamerica.com/products/etabs).

Referencia API: ayuda `CSI API ETABS v1.chm` de la instalación local y
[documentación del fabricante](https://www.csiamerica.com/developer).
