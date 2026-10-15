"""Aplana el DWG del polideportivo (La Salvia, Bonao) a elevacion 0 EN VIVO.

Requiere el dwg abierto y ACTIVO en Civil 3D. Dos pasadas: la primera aplana,
la segunda verifica idempotencia (modificadas=0). Si todo cuadra, guarda el
dibujo (hay respaldo *_respaldo_preAplanado.dwg en la misma carpeta).
"""
import json
import os
import sys

RAIZ = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(RAIZ, 'src'))
import puente_cliente as puente  # noqa: E402
import dibujo                    # noqa: E402
import aplanar                   # noqa: E402

ESPERADO = 'POLIDEPORTIVO'


def principal():
    print('== pasada 1: aplanar ==')
    r1 = aplanar.aplanar(puente, dibujo, esperado=ESPERADO, timeout=300)
    print(json.dumps(r1, ensure_ascii=False))
    print('== pasada 2: verificacion (debe modificar 0) ==')
    r2 = aplanar.aplanar(puente, dibujo, esperado=ESPERADO, timeout=300)
    print(json.dumps(r2, ensure_ascii=False))
    if r2.get('modificadas', -1) != 0 or r2.get('fallidas', -1) not in (0, r1.get('fallidas')):
        print('VEREDICTO: FALLA (la segunda pasada siguio modificando o fallando)')
        return 1
    print('== guardar ==')
    try:
        g = puente.llamar_con_aprobacion('doc.save', {})
        print('guardado:', json.dumps(g, ensure_ascii=False)[:200])
    except Exception as exc:  # noqa: BLE001
        print('doc.save fallo (%s); intento _.QSAVE' % exc)
        puente.llamar_con_aprobacion('cmd.run', {'linea': '_.QSAVE '})
    print('VEREDICTO: OK (modificadas pasada 1: %s; no_aplanables: %s; fallidas: %s)'
          % (r1.get('modificadas'), r1.get('no_aplanables'), r1.get('fallidas')))
    return 0


if __name__ == '__main__':
    sys.exit(principal())
