"""Contrato sintético del botón de lectura de coordenadas compartidas."""
import json
from pathlib import Path
from runpy import run_path
from types import SimpleNamespace
from unittest import TestCase

ROOT = Path(__file__).resolve().parents[1]
BUTTON = (ROOT / "RevitWrite.extension/RevitWrite.tab/5-Vistas.panel"
          / "MedirPunto.pushbutton/script.py")


class LecturaCompartidaTests(TestCase):
    def setUp(self):
        self.api = run_path(str(BUTTON))
        self.selection = object()
        self.pos = SimpleNamespace(EastWest=4.0, NorthSouth=-2.5, Elevation=0.0)
        self.location = SimpleNamespace(Name="Sitio sintético", GetProjectPosition=self.transform)
        self.doc = SimpleNamespace(PathName="sintetico.rvt", ActiveProjectLocation=self.location)
        self.element = SimpleNamespace(UniqueId="elemento-sintetico")
        self.reference = SimpleNamespace(GlobalPoint=self.selection)

    def transform(self, point):
        self.assertIs(point, self.selection)
        return self.pos

    def read(self, **overrides):
        values = dict(doc=self.doc, elemento=self.element, referencia=self.reference,
                      rol="umbral", revision="A", laminas=["A-1"], marco="LOCAL + BM")
        values.update(overrides)
        return self.api["registro"](**values)

    def test_contrato_y_conversion_despues_de_transformar(self):
        result = self.read()
        self.assertEqual(set(result), {"rol", "documento", "revision", "laminas",
                                      "elemento", "punto_m", "marco", "metodo"})
        self.assertEqual(result["punto_m"], [1.2192, -0.762, 0.0])
        self.assertEqual(result["documento"], "sintetico.rvt")
        self.assertEqual(result["elemento"], "elemento-sintetico")
        self.assertIn("Sitio sintético", result["metodo"])
        self.assertEqual(self.read(rol="control_revit")["rol"], "control_revit")

    def test_rechaza_punto_o_metadatos_incompletos(self):
        for args in (dict(rol="rampa"), dict(marco="  "), dict(revision=""),
                     dict(laminas=[]), dict(laminas=[" ", "S-01"]),
                     dict(referencia=SimpleNamespace(GlobalPoint=None)),
                     dict(elemento=SimpleNamespace(UniqueId="")),
                     dict(doc=SimpleNamespace(PathName=""))):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.read(**args)

    def test_rechaza_cota_no_finita(self):
        for z in (float("inf"), float("nan")):
            self.pos.Elevation = z
            with self.assertRaises(ValueError):
                self.read()

    def test_exportacion_atomica_sin_sobrescribir(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            dest = Path(directory) / "umbral.json"
            data = self.read(revision="Edición α")
            def publicar(src, dst):
                import os
                os.link(src, dst)
            self.api["exportar"](str(dest), data, publicar)
            self.assertEqual(json.loads(dest.read_text(encoding="utf-8")), data)
            before = dest.read_bytes()
            with self.assertRaises(OSError):
                self.api["exportar"](str(dest), self.read(), publicar)
            self.assertEqual(dest.read_bytes(), before)
            self.assertEqual(list(dest.parent.iterdir()), [dest])

    def test_flujo_desde_el_boton_y_cancelaciones(self):
        """Ejecuta el flujo completo con interfaces sustitutivas, sin abrir Revit."""
        import os
        from tempfile import TemporaryDirectory
        from unittest.mock import Mock, patch

        class Vista3D:
            pass

        class Vinculo:
            pass

        class Cancelada(Exception):
            pass

        db = SimpleNamespace(View3D=Vista3D, RevitLinkInstance=Vinculo,
                             ElementId=SimpleNamespace(InvalidElementId=-1), ViewSheet=object)
        self.doc.ActiveView = Vista3D()
        self.doc.IsFamilyDocument = False
        self.doc.GetElement = Mock(return_value=self.element)
        self.reference.ElementId = "ID"
        self.reference.LinkedElementId = -1
        sheets = [SimpleNamespace(SheetNumber="A-01", UniqueId="hoja-A", IsPlaceholder=False),
                  SimpleNamespace(SheetNumber="A-01", UniqueId="hoja-B", IsPlaceholder=False),
                  SimpleNamespace(SheetNumber="A-99", IsPlaceholder=True)]
        db.FilteredElementCollector = Mock(return_value=SimpleNamespace(OfClass=lambda _: sheets))
        selection = Mock()
        selection.PickObject.return_value = self.reference

        with TemporaryDirectory() as folder:
            destination = str(Path(folder) / "punto.json")
            forms = Mock()
            modules = {
                "pyrevit": SimpleNamespace(DB=db, forms=forms, revit=SimpleNamespace(
                    doc=self.doc, uidoc=SimpleNamespace(Selection=selection))),
                "Autodesk.Revit.Exceptions": SimpleNamespace(OperationCanceledException=Cancelada),
                "Autodesk.Revit.UI.Selection": SimpleNamespace(ObjectType=SimpleNamespace(PointOnElement=1)),
                "System.IO": SimpleNamespace(File=SimpleNamespace(Move=os.rename)),
            }
            with patch.dict("sys.modules", modules):
                forms.SelectFromList.show.side_effect = ["control_revit", ["A-01 [hoja-B]"]]
                forms.ask_for_string.side_effect = ["R01", "Marco de ensayo"]
                forms.save_file.return_value = destination
                self.api["ejecutar"]()
                data = json.loads(Path(destination).read_text(encoding="utf-8"))
                self.assertEqual(data["laminas"], ["A-01 [hoja-B]"])
                self.assertEqual(forms.SelectFromList.show.call_args.args[0], ["A-01 [hoja-A]", "A-01 [hoja-B]"])
                self.assertEqual(data["punto_m"], [1.2192, -0.762, 0.0])

                forms.save_file.reset_mock()
                forms.SelectFromList.show.side_effect = ["umbral"]
                selection.PickObject.side_effect = Cancelada
                self.api["ejecutar"]()
                forms.save_file.assert_not_called()
                self.doc.ActiveView = object()
                with self.assertRaisesRegex(ValueError, "3D"):
                    self.api["ejecutar"]()
                self.doc.ActiveView = Vista3D()
                selection.PickObject.side_effect = None
                self.reference.LinkedElementId = 133
                forms.SelectFromList.show.side_effect = ["umbral"]
                with self.assertRaisesRegex(ValueError, "geometría local"):
                    self.api["ejecutar"]()
                forms.save_file.assert_not_called()
