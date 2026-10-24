# Arnés QTO nativo (solo pruebas)

Compilar Qa.csproj con .NET10 y referencias de Civil3D2027. Cargar la DLL
Cdcrd.QtoV8Qa en la instancia existente, además de Cdcrd.Qto.V8 y native_gm_qa.
CDCRD_GM_QA_ROOT debe apuntar a la carpeta de la copia identificada
CDCRD_GM_RECOVERY_QTO.dwg. Nunca usar el dibujo original.

CDCRDQTOFIXTURE crea dos TIN sintéticas una vez. CDCRDQTOV8QA arma un fallo
de una sola ocurrencia desde qto-fault.json. verificar_qto.py consume el fallo
y compara inventarios completos antes/después. No ejecutar el comando de
fixture ni repetir escrituras si ya existen recibos; inspeccionar primero.
El módulo productivo no carga estos auxiliares automáticamente.

Ver docs/QTO-0522.md para datos, fases, comandos, resultados y límites.
