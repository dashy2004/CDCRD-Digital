"""Flujo sintético del botón de emisión, desde el orden de láminas hasta el PDF publicado."""
import os
from pathlib import Path
from runpy import run_path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

BUTTON = (Path(__file__).resolve().parents[1] / "RevitWrite.extension/RevitWrite.tab"
          / "5-Vistas.panel/EmitirPDF.pushbutton/script.py")


class EmisionPDFTests(TestCase):
    def setUp(self):
        self.api = run_path(str(BUTTON))
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dest = Path(folder.name) / "Emisión sintética.pdf"
        self.exportacion_completa = True
        self.n_paginas = 2
        self.crear_archivo = True
        self.export_opts = SimpleNamespace(SetExportInBackground=Mock(), Dispose=Mock())
        self.pdf_opts = SimpleNamespace(Dispose=Mock())
        self.pdf_opts.IsValid = lambda doc: 0 < self.pdf_opts.PageNumber <= self.n_paginas
        self.db = SimpleNamespace(
            PDFExportOptions=lambda: self.export_opts, ExportPaperFormat=SimpleNamespace(Default=42), ImageTypeSource=SimpleNamespace(Import=1),
            ImageTypeOptions=self.leer_pdf)
        self.doc = SimpleNamespace(Export=self.exportar)
        self.ids = [10, 13]

    def leer_pdf(self, path, relativo, tipo):
        self.assertTrue(Path(path).is_file())
        self.assertFalse(relativo)
        return self.pdf_opts

    def exportar(self, folder, ids, opciones):
        self.assertEqual(ids, self.ids)
        self.assertEqual(opciones.PaperFormat, 42)
        self.assertTrue(opciones.Combine)
        self.assertTrue(opciones.StopOnError)
        self.assertTrue(opciones.FileName)
        self.export_opts.SetExportInBackground.assert_called_once_with(False)
        if self.crear_archivo:
            (Path(folder) / (opciones.FileName + ".pdf")).write_bytes(b"%PDF-ensayo")
        return self.exportacion_completa

    def emitir(self):
        return self.api["emitir"](self.doc, self.ids, str(self.dest),
                                  self.db, lambda src, dst: os.link(src, dst))

    def test_publica_y_relee_dos_paginas(self):
        self.assertEqual(self.emitir(), 2)
        self.assertEqual(self.dest.read_bytes(), b"%PDF-ensayo")
        self.assertEqual(list(self.dest.parent.iterdir()), [self.dest])
        self.pdf_opts.Dispose.assert_called_once()

    def test_rechaza_dos_cantidades_incorrectas(self):
        for number in (1, 3):
            with self.subTest(number=number):
                self.n_paginas = number
                self.export_opts.SetExportInBackground.reset_mock()
                with self.assertRaisesRegex(ValueError, "páginas"):
                    self.emitir()
                self.assertFalse(self.dest.exists())

    def test_exportacion_parcial_y_faltante_se_descartan(self):
        self.exportacion_completa = False
        with self.assertRaisesRegex(ValueError, "parcial"):
            self.emitir()
        self.exportacion_completa = True
        self.crear_archivo = False
        self.export_opts.SetExportInBackground.reset_mock()
        with self.assertRaisesRegex(ValueError, "archivo"):
            self.emitir()
        self.assertEqual(list(self.dest.parent.iterdir()), [])

    def test_conserva_el_destino_anterior(self):
        self.dest.write_bytes(b"otro")
        with self.assertRaisesRegex(ValueError, "existe"):
            self.emitir()
        self.assertEqual(self.dest.read_bytes(), b"otro")
        self.export_opts.SetExportInBackground.assert_not_called()

    def test_destino_creado_durante_la_exportacion(self):
        def carrera(src, dst):
            Path(dst).write_bytes(b"otra emision")
            os.link(src, dst)
        with self.assertRaises(FileExistsError):
            self.api["emitir"](self.doc, self.ids, str(self.dest), self.db, carrera)
        self.assertEqual(self.dest.read_bytes(), b"otra emision")
        self.assertEqual(list(self.dest.parent.iterdir()), [self.dest])

    def test_flujo_del_boton_ordena_conserva_ids_y_descarta_no_imprimibles(self):
        from unittest.mock import patch

        class Ids(list):
            @classmethod
            def __class_getitem__(cls, _item):
                return cls

            Add = list.append

        sheets = [SimpleNamespace(SheetNumber="A-01", Name="Plano", Id=SimpleNamespace(Value=n),
                                  CanBePrinted=True, IsPlaceholder=False) for n in self.ids]
        sheets.append(SimpleNamespace(CanBePrinted=False, IsPlaceholder=True))
        self.db.ViewSheet = object
        self.db.ElementId = object
        self.db.FilteredElementCollector = lambda _: SimpleNamespace(OfClass=lambda _: sheets)
        self.doc.IsFamilyDocument = False
        forms = Mock()
        forms.SelectFromList.show.side_effect = lambda names, **kwargs: list(reversed(names))
        forms.save_file.return_value = str(self.dest)
        modules = {
            "pyrevit": SimpleNamespace(DB=self.db, forms=forms,
                                       revit=SimpleNamespace(doc=self.doc)),
            "System.IO": SimpleNamespace(File=SimpleNamespace(Move=lambda src, dst: os.link(src, dst))),
            "System.Collections.Generic": SimpleNamespace(List=Ids),
        }
        self.doc.Export = lambda folder, ids, options: self.exportar(folder, [i.Value for i in ids], options)
        with patch.dict("sys.modules", modules):
            self.api["ejecutar"]()
            self.assertIn("2", forms.alert.call_args.args[0])
            self.assertTrue(self.dest.exists())
            forms.SelectFromList.show.side_effect = None
            forms.SelectFromList.show.return_value = None
            forms.alert.reset_mock()
            self.api["ejecutar"]()
            forms.alert.assert_not_called()
