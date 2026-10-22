"""Renumeración en orden de lectura (ley: izq→der, arriba→abajo; vuelos fuera)."""
import unittest

from plugin_losas.renumeracion import (CajaLosa, caja_desde_contorno,
                                       orden_lectura, renumerar,
                                       renumerar_por_grupos)


def _caja(mark, x0, y0, x1, y1, es_vuelo=False):
    return CajaLosa(mark, x0, y0, x1, y1, es_vuelo)


class TestOrdenLectura(unittest.TestCase):
    def test_rejilla_como_un_libro(self):
        # Rejilla 2x3 desordenada: la fila de arriba (y 6-12) va primero.
        cajas = [_caja("c", 10, 0, 15, 6), _caja("a", 0, 6, 5, 12),
                 _caja("f", 10, 6, 15, 12), _caja("d", 0, 0, 5, 6),
                 _caja("b", 5, 6, 10, 12), _caja("e", 5, 0, 10, 6)]
        orden = [c.mark for c in orden_lectura(cajas)]
        self.assertEqual(orden, ["a", "b", "f", "d", "e", "c"])

    def test_alturas_distintas_misma_banda(self):
        # Una losa más baja en la misma banda sigue siendo de esa fila
        # (solape vertical >= 50% de la altura menor).
        cajas = [_caja("alta", 0, 0, 5, 8), _caja("baja", 5, 2, 10, 6)]
        orden = [c.mark for c in orden_lectura(cajas)]
        self.assertEqual(orden, ["alta", "baja"])

    def test_sin_solape_abre_fila_nueva(self):
        cajas = [_caja("arriba", 0, 10, 5, 16), _caja("abajo", 2, 0, 7, 6)]
        orden = [c.mark for c in orden_lectura(cajas)]
        self.assertEqual(orden, ["arriba", "abajo"])


class TestRenumerar(unittest.TestCase):
    def test_prefijo_y_relleno(self):
        cajas = [_caja("x", 5, 6, 10, 12), _caja("y", 0, 6, 5, 12),
                 _caja("z", 0, 0, 5, 6)]
        self.assertEqual(renumerar(cajas, "T"), {"y": "T1", "x": "T2", "z": "T3"})
        self.assertEqual(renumerar(cajas, "N2-", relleno=2),
                         {"y": "N2-01", "x": "N2-02", "z": "N2-03"})

    def test_vuelo_conserva_marca_y_no_consume_numero(self):
        cajas = [_caja("V-BALCON", -2, 6, 0, 12, es_vuelo=True),
                 _caja("y", 0, 6, 5, 12), _caja("z", 0, 0, 5, 6)]
        mapa = renumerar(cajas, "L")
        self.assertEqual(mapa, {"y": "L1", "z": "L2"})
        self.assertNotIn("V-BALCON", mapa)

    def test_choque_con_marca_de_vuelo_falla(self):
        cajas = [_caja("L1", -2, 6, 0, 12, es_vuelo=True), _caja("y", 0, 6, 5, 12)]
        with self.assertRaises(ValueError):
            renumerar(cajas, "L")

    def test_grupos_niveles_y_colision_global(self):
        techo = [_caja("tb", 0, 0, 5, 6), _caja("ta", 0, 6, 5, 12)]
        n2 = [_caja("na", 0, 6, 5, 12)]
        mapa = renumerar_por_grupos({"techo": techo, "n2": n2},
                                    {"techo": "T", "n2": "N2-"},
                                    {"n2": 2})
        self.assertEqual(mapa, {"ta": "T1", "tb": "T2", "na": "N2-01"})
        with self.assertRaises(ValueError):
            renumerar_por_grupos({"a": [_caja("p", 0, 0, 5, 6)],
                                  "b": [_caja("q", 0, 0, 5, 6)]},
                                 {"a": "L", "b": "L"})

    def test_caja_desde_contorno(self):
        c = caja_desde_contorno("m", [[1, 2], [4, 2], [4, 7], [1, 7]])
        self.assertEqual((c.x0, c.y0, c.x1, c.y1), (1, 2, 4, 7))


if __name__ == "__main__":
    unittest.main()
