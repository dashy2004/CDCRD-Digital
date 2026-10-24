import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).parents[1] / 'src' / 'tools' / 'exportar_pdf.py'
spec = importlib.util.spec_from_file_location('exportar_pdf', path)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


@pytest.mark.parametrize('value,expected', [
    ('A1', 'ISO_A1'), ('a3', 'ISO_A3'), ('ARCH_D', 'ARCH_D'),
    ('ANSI_D', 'ANSI_D'), ('ARCH_E', 'ARCH_E'), ('bad', 'BAD'),
])
def test_paper_names_do_not_treat_all_a_prefixes_as_iso(value, expected):
    assert tool._pdf_paper_enum_name(value) == expected
