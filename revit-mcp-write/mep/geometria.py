# -*- coding: utf-8 -*-
"""Geometria del trazado, en tuplas (x, y, z) y PIES (unidad interna).

Sin API de Revit: es aritmetica pura y se prueba sola.
"""

VERTICAL = 0.99  # |dz| del versor a partir del cual un conector es vertical


class ErrorTrazado(Exception):
    """El trazado pedido no es construible; el mensaje es el motivo."""


def resta(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def suma(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def escala(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def punto_escalar(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def norma(a):
    return punto_escalar(a, a) ** 0.5


def distancia(a, b):
    return norma(resta(a, b))


def distancia_planta(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def versor(a):
    n = norma(a)
    if n == 0.0:
        raise ErrorTrazado("direccion nula")
    return escala(a, 1.0 / n)


def distancia_a_segmento(p, a, b):
    """Distancia 3D minima del punto p al segmento a-b."""
    ab = resta(b, a)
    largo2 = punto_escalar(ab, ab)
    if largo2 == 0.0:
        return distancia(p, a)
    t = punto_escalar(resta(p, a), ab) / largo2
    t = max(0.0, min(1.0, t))
    return distancia(p, suma(a, escala(ab, t)))


def entronque_en_planta(p, a, b, margen):
    """Punto del eje a-b cuya proyeccion en planta es la mas cercana a p.

    La cota Z sale del propio eje (respeta la pendiente del ramal).
    Falla si cae fuera del tramo o a menos de 'margen' de un extremo:
    no se desplaza el entronque para hacerlo caber.
    """
    abx, aby = b[0] - a[0], b[1] - a[1]
    largo = (abx ** 2 + aby ** 2) ** 0.5
    if largo < 1e-9:
        raise ErrorTrazado("el ramal es vertical: entronque no soportado")
    t = ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / (largo ** 2)
    if t * largo < margen or (1.0 - t) * largo < margen:
        raise ErrorTrazado(
            "el entronque cae fuera del ramal o a menos del margen de un extremo")
    return suma(a, escala(resta(b, a), t))


def calcular_ruta(origen, direccion, eje_a, eje_b, pendiente,
                  salida, minimo, margen, tol):
    """Vertices del trazado desde el conector del aparato hasta el ramal.

    origen, direccion: posicion y versor saliente del conector.
    pendiente: m/m (adimensional); el tramo horizontal SUBE al alejarse
    del ramal, de modo que el flujo cae hacia el. 0 = sin pendiente.
    salida: largo del tramo recto inicial cuando el conector no es vertical.
    minimo: largo minimo construible de un tramo. tol: igualdad de puntos.

    Devuelve {"puntos": [origen, ..., entronque], "entronque": P}.
    """
    d = versor(direccion)
    es_vertical = abs(d[2]) >= VERTICAL
    puntos = [origen]
    inicio = origen
    if not es_vertical:
        inicio = suma(origen, escala(d, salida))
        puntos.append(inicio)
    entronque = entronque_en_planta(inicio, eje_a, eje_b, margen)
    recorrido = distancia_planta(inicio, entronque)
    if recorrido < minimo:
        raise ErrorTrazado("el aparato queda sobre el eje del ramal: "
                           "no hay tramo horizontal construible")
    codo = (inicio[0], inicio[1], entronque[2] + pendiente * recorrido)
    desnivel = codo[2] - inicio[2]
    if abs(desnivel) >= tol:
        if abs(desnivel) < minimo:
            raise ErrorTrazado("desnivel menor que el tramo minimo: "
                               "no caben bajante y codo")
        if es_vertical and desnivel * d[2] <= 0.0:
            raise ErrorTrazado("el conector apunta en sentido contrario "
                               "a la cota del ramal")
        puntos.append(codo)
    puntos.append(entronque)
    return {"puntos": puntos, "entronque": entronque}


def son_colineales(a, b, tolerancia=0.999):
    """True si dos direcciones apuntan en el mismo sentido."""
    return punto_escalar(versor(a), versor(b)) >= tolerancia
