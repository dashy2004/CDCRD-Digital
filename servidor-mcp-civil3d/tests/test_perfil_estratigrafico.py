"""Contrato de los helpers puros de perfil_estratigrafico.py; sin CAD."""
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import perfil_estratigrafico as pe  # noqa: E402


class Extraccion(unittest.TestCase):
    def test_spt(self):
        self.assertEqual(pe._spt_de_texto('blanda (RQD 10-40%). SPT N~35'), 35)
        self.assertEqual(pe._spt_de_texto('SPT N=60; rechazo'), 60)
        self.assertIsNone(pe._spt_de_texto('sin dato'))
        self.assertIsNone(pe._spt_de_texto(None))

    def test_freatico(self):
        self.assertEqual(pe._freatico_de_texto('Nivel freatico hipotetico ~14.0 m'), 14.0)
        self.assertEqual(pe._freatico_de_texto('nivel freatico 7 m'), 7.0)
        self.assertIsNone(pe._freatico_de_texto('sin agua'))


class LecturaCSV(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        with open(os.path.join(self.d, 'u.csv'), 'w', encoding='utf-8') as fh:
            fh.write('Location ID,Location Type,Easting,Northing,Ground Level,Final Depth\n')
            fh.write('S-1,CP,100,200,40.0,20.0\n')
        with open(os.path.join(self.d, 'e.csv'), 'w', encoding='utf-8') as fh:
            fh.write('Location ID,Depth Top,Depth Base,Legend Code,Geology Code,Geology Code 2,BGS Lexicon,Description\n')
            fh.write('S-1,0,2,101,RELLENO,,,limo. SPT N~3\n')
            fh.write('S-1,2,20,320,CALIZA,,,dura. SPT N~60. Nivel freatico ~8.0 m\n')

    def test_estructura(self):
        s = pe.leer_sondeos_csv(os.path.join(self.d, 'u.csv'), os.path.join(self.d, 'e.csv'))
        self.assertEqual(s['S-1']['elev'], 40.0)
        self.assertEqual(len(s['S-1']['estratos']), 2)
        self.assertEqual(s['S-1']['estratos'][0]['spt'], 3)
        self.assertEqual(s['S-1']['estratos'][1]['codigo'], 320)
        self.assertEqual(s['S-1']['prof_agua'], 8.0)

    def test_rango(self):
        s = pe.leer_sondeos_csv(os.path.join(self.d, 'u.csv'), os.path.join(self.d, 'e.csv'))
        lo, hi = pe.rango_elevaciones(s, ['S-1'])
        self.assertLessEqual(lo, 20.0)   # fondo 40-20=20
        self.assertGreaterEqual(hi, 40.0)


class LecturaDB(unittest.TestCase):
    def test_db_minima(self):
        d = tempfile.mkdtemp()
        db = os.path.join(d, 'gm.db')
        con = sqlite3.connect(db)
        con.execute('CREATE TABLE Borehole (BoringId TEXT, XCoord REAL, YCoord REAL, '
                    'Elevation REAL, TotalDepth REAL, DepthToWater REAL)')
        con.execute("INSERT INTO Borehole VALUES ('S-1',100,200,40,20,8)")
        con.execute('CREATE TABLE Stratum (BoringId TEXT, TopDepth REAL, BaseDepth REAL, '
                    'LegendCode INT, LegendName TEXT, GeologyName1 TEXT, Description TEXT, '
                    'Red INT, Green INT, Blue INT)')
        con.execute("INSERT INTO Stratum VALUES ('S-1',0,2,101,'R','RELLENO','SPT N~3',150,120,80)")
        con.execute('CREATE TABLE Sample (BoringId TEXT, TopDepth REAL, BottomDepth REAL, BlowCount TEXT)')
        con.execute("INSERT INTO Sample VALUES ('S-1',0.4,0.85,'12')")
        con.commit()
        con.close()
        s = pe.leer_sondeos_db(db)
        self.assertEqual(s['S-1']['prof_agua'], 8.0)
        self.assertEqual(s['S-1']['estratos'][0]['rgb'], [150, 120, 80])
        self.assertEqual(s['S-1']['estratos'][0]['spt'], 3)
        self.assertEqual(len(s['S-1']['spt']), 1)


class Fuente(unittest.TestCase):
    def test_sin_fuente(self):
        with self.assertRaises(ValueError):
            pe.cargar_sondeos({})


if __name__ == '__main__':
    unittest.main()
