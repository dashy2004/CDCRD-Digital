"""Lector DXF de AutoCAD: recuadros de losa + numeración (fixture inventado)."""
import unittest

from puente_losas.contrato import panos_desde_dict

from plugin_losas.acad_dxf import (export_para_puente, leer_entidades,
                                   losas_desde_dxf, recuadros_losa,
                                   textos_numeracion)


def _dxf(*grupos) -> str:
    """Arma un DXF ASCII desde pares (código, valor)."""
    lineas = []
    for codigo, valor in grupos:
        lineas.append(str(codigo))
        lineas.append(str(valor))
    return "\n".join(lineas) + "\n"


def _rect(capa, x0, y0, x1, y1):
    return [(0, "LWPOLYLINE"), (8, capa), (90, 4), (70, 1),
            (10, x0), (20, y0), (10, x1), (20, y0),
            (10, x1), (20, y1), (10, x0), (20, y1)]


def _texto(capa, x, y, contenido, tipo="TEXT"):
    return [(0, tipo), (8, capa), (10, x), (20, y), (1, contenido)]


# Plano inventado: dos paños de 5×6 m contiguos (LA1, LA2) y uno de 4×6 sin
# numeración; un texto fuera de todo recuadro. Nada corresponde a un plano real.
FIXTURE = _dxf(
    (0, "SECTION"), (2, "HEADER"), (0, "ENDSEC"),
    (0, "SECTION"), (2, "ENTITIES"),
    *_rect("LOSAS", 0.0, 0.0, 5.0, 6.0),
    *_rect("LOSAS", 5.0, 0.0, 10.0, 6.0),
    *_rect("LOSAS", 10.1, 0.0, 14.1, 6.0),
    *_rect("OTRA-CAPA", 20.0, 0.0, 22.0, 2.0),
    *_texto("LOSAS-NUM", 2.5, 3.0, "LA1"),
    *_texto("LOSAS-NUM", 7.5, 3.0, "LA2", tipo="MTEXT"),
    *_texto("LOSAS-NUM", 50.0, 50.0, "NOTA SUELTA"),
    (0, "ENDSEC"),
    (0, "EOF"),
)


class TestLectorDxf(unittest.TestCase):
    def test_entidades_basicas(self):
        ents = leer_entidades(FIXTURE)
        self.assertEqual(sum(e.tipo == "LWPOLYLINE" for e in ents), 4)
        self.assertEqual(sum(e.tipo in ("TEXT", "MTEXT") for e in ents), 3)

    def test_recuadros_solo_de_la_capa_de_losas(self):
        recs = recuadros_losa(leer_entidades(FIXTURE), "LOSAS")
        self.assertEqual(len(recs), 3)
        self.assertAlmostEqual(recs[0].lx, 5.0)
        self.assertAlmostEqual(recs[0].ly, 6.0)
        self.assertTrue(all(r.es_rectangular for r in recs))

    def test_textos_y_mtext(self):
        ts = textos_numeracion(leer_entidades(FIXTURE), "LOSAS-NUM")
        self.assertEqual([t[2] for t in ts], ["LA1", "LA2", "NOTA SUELTA"])

    def test_losas_numeradas_y_avisos(self):
        filas, avisos = losas_desde_dxf(FIXTURE, capa_losas="LOSAS",
                                        capa_textos="LOSAS-NUM", espesor_m=0.20)
        self.assertEqual([f.mark for f in filas], ["LA1", "LA2", "SN-3"])
        self.assertEqual(filas[0].fuente, "acad")
        self.assertAlmostEqual(filas[2].lx, 4.0)
        self.assertEqual(filas[0].espesor_m, 0.20)
        self.assertTrue(any("sin numeración" in a for a in avisos))
        self.assertTrue(any("fuera de todo recuadro" in a for a in avisos))

    def test_escala_milimetros(self):
        fixture_mm = FIXTURE.replace("5.0", "5000.0").replace("6.0", "6000.0") \
                            .replace("10.1", "10100.0").replace("14.1", "14100.0") \
                            .replace("2.5", "2500.0").replace("3.0", "3000.0") \
                            .replace("7.5", "7500.0").replace("50.0", "50000.0") \
                            .replace("10.0", "10000.0")
        filas, _ = losas_desde_dxf(fixture_mm, capa_losas="LOSAS", escala_a_m=0.001)
        self.assertAlmostEqual(filas[0].lx, 5.0)
        self.assertAlmostEqual(filas[0].ly, 6.0)

    def test_capa_sin_losas_falla_claro(self):
        with self.assertRaises(ValueError):
            losas_desde_dxf(FIXTURE, capa_losas="NO-EXISTE")

    def test_dxf_malformado_falla_claro(self):
        with self.assertRaises(ValueError):
            leer_entidades("esto no\nes un dxf\nvalido")

    def test_numeracion_repetida_se_renombra(self):
        fixture = _dxf(
            (0, "SECTION"), (2, "ENTITIES"),
            *_rect("LOSAS", 0.0, 0.0, 5.0, 6.0),
            *_rect("LOSAS", 5.0, 0.0, 10.0, 6.0),
            *_texto("N", 2.5, 3.0, "LA1"), *_texto("N", 7.5, 3.0, "LA1"),
            (0, "ENDSEC"), (0, "EOF"))
        filas, avisos = losas_desde_dxf(fixture, capa_losas="LOSAS")
        self.assertEqual([f.mark for f in filas], ["LA1", "LA1-2"])
        self.assertTrue(any("repetida" in a for a in avisos))

    def test_export_para_puente_cierra_el_circuito(self):
        """El export del DXF lo acepta el contrato PanoLosa de puente-losas."""
        filas, _ = losas_desde_dxf(FIXTURE, capa_losas="LOSAS",
                                   capa_textos="LOSAS-NUM", espesor_m=0.20)
        panos = panos_desde_dict(export_para_puente(filas))
        self.assertEqual([p.mark for p in panos], ["LA1", "LA2", "SN-3"])
        self.assertEqual(panos[0].espesor, 0.20)
        # la adyacencia del contrato ve LA1 y LA2 contiguas (borde x=5 compartido)
        from puente_losas.contrato import lados_continuos
        lados = lados_continuos(panos)
        self.assertEqual(lados["LA1"]["der"], "LA2")
        self.assertIsNone(lados["LA2"]["der"])      # la junta de 0.10 m no es continuidad


if __name__ == "__main__":
    unittest.main()
