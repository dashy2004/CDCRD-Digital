from pathlib import Path

import pytest

from cdcrd_local.sondeos import revisar


def caso(carpeta: Path, tramos):
    ubicaciones = carpeta / "ubic.csv"
    litologia = carpeta / "lit.csv"
    ubicaciones.write_text("Location ID,Easting,Northing,Ground Level,Final Depth\nS1,10,20,0,5\n")
    litologia.write_text("Location ID,Depth Top,Depth Base,Description\n" + tramos)
    return ubicaciones, litologia


def test_tramos_fuera_de_orden(tmp_path):
    assert revisar(*caso(tmp_path, "S1,2.30,5,Grava\nS1,0,2.3,Arena\n"))["ok"]


def test_detecta_inconsistencias(tmp_path):
    r = revisar(*caso(tmp_path, "S1,1,4,Arena\nS1,3,6,Grava\nS2,0,1,Arcilla\n"))
    assert not r["ok"]
    for palabra in ("Hueco", "Solape", "excede", "sin ubicación"):
        assert any(palabra in a["detalle"] for a in r["incidencias"])


def test_profundidad_invalida(tmp_path):
    with pytest.raises(ValueError, match="finito"):
        revisar(*caso(tmp_path, "S1,0,NaN,Arena\n"))
