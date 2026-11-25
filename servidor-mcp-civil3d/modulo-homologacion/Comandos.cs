using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil.Settings;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivilStructure = Autodesk.Civil.DatabaseServices.Structure;

namespace Cdcrd.Homologacion;

public class Comandos
{
    [CommandMethod("CDCRDMEDIRPUNTO", CommandFlags.Modal)]
    public void MedirPunto()
    {
        var doc = App.DocumentManager.MdiActiveDocument;
        if (doc == null) return;
        var ed = doc.Editor;
        try
        {
            if (Convert.ToInt32(App.GetSystemVariable("DWGTITLED")) != 1)
                throw new InvalidOperationException("Guarde la copia DWG antes de identificarla.");
            var pregunta = new PromptKeywordOptions("\nPunto [Llegada/Sumidero/Control]: ");
            foreach (var rol in new[] { "Llegada", "Sumidero", "Control" }) pregunta.Keywords.Add(rol);
            var eleccion = ed.GetKeywords(pregunta);
            if (eleccion.Status != PromptStatus.OK) return;
            var unidades = CivilApplication.ActiveDocument.Settings.DrawingSettings.UnitZoneSettings;
            var escala = unidades.DrawingUnits switch
            {
                DrawingUnitType.Meters => 1.0,
                DrawingUnitType.Feet => unidades.ImperialToMetricConversion switch
                {
                    ImperialToMetricConversionType.InternationalFoot => 0.3048,
                    ImperialToMetricConversionType.UsSurveyFoot => 1200.0 / 3937.0,
                    _ => throw new InvalidOperationException("Definición de pie desconocida.")
                },
                _ => throw new InvalidOperationException("Unidad civil desconocida.")
            };
            ed.WriteMessage($"\nZona del DWG: {unidades.CoordinateSystemCode}. Las coordenadas nativas son WCS locales.");
            var marco = Texto(ed, "Identificador del marco horizontal y vertical común, verificado por el operador");
            var revision = Texto(ed, "Revisión de la lectura");
            var lamina = Texto(ed, "Nombre de la presentación que documenta este punto");
            Medicion medicion;
            using (var tx = doc.Database.TransactionManager.StartOpenCloseTransaction())
            {
                var laminas = (DBDictionary)tx.GetObject(doc.Database.LayoutDictionaryId, OpenMode.ForRead);
                if (!laminas.Contains(lamina))
                    throw new ArgumentException("La presentación indicada no existe en el DWG.");
                var layout = (Layout)tx.GetObject(laminas.GetAt(lamina), OpenMode.ForRead);
                if (layout.ModelType) throw new ArgumentException("Indique una presentación de papel.");
                var (rol, handle, xyz, metodo) = Leer(ed, tx, eleccion.StringResult);
                metodo += FormattableString.Invariant($". WCS local, m/unidad={escala:R}.");
                medicion = Medicion.Crear(rol, Path.GetFileName(doc.Name), revision, [layout.LayoutName],
                    handle, xyz, escala, marco, metodo);
            }
            var nombre = ed.GetFileNameForSave(new PromptSaveFileOptions("\nExportar medición nueva")
                { Filter = "Medición JSON (*.json)|*.json" });
            if (nombre.Status != PromptStatus.OK) return;
            medicion.Exportar(nombre.StringResult);
            ed.WriteMessage("\nMedición exportada: " + nombre.StringResult);
        }
        catch (OperationCanceledException) { ed.WriteMessage("\nSelección cancelada."); }
        catch (System.Exception ex) { ed.WriteMessage("\nMedición interrumpida: " + ex.Message); }
    }

    private static (string, string, double[], string) Leer(Editor ed, Transaction tx, string opcion)
    {
        if (opcion == "Sumidero")
        {
            var estructura = Seleccionar<CivilStructure>(ed, tx, "Seleccione la estructura que representa la rejilla");
            return ("sumidero", estructura.Handle.ToString(),
                [estructura.Position.X, estructura.Position.Y, estructura.RimElevation],
                "Structure.Position XY + Structure.RimElevation (borde modelado)");
        }
        var punto = Seleccionar<CogoPoint>(ed, tx, opcion == "Control" ?
            "Seleccione el punto COGO de control independiente" :
            "Seleccione el punto COGO que localiza en planta el extremo de la rampa");
        if (opcion == "Control")
            return ("control_civil", punto.Handle.ToString(), [punto.Easting, punto.Northing, punto.Elevation],
                "CogoPoint.Easting/Northing/Elevation");
        var tin = Seleccionar<TinSurface>(ed, tx, "Seleccione la superficie TIN terminada de la rampa");
        if (tin.IsOutOfDate) throw new InvalidOperationException("Reconstruya la superficie TIN y repita la lectura.");
        var z = tin.FindElevationAtXY(punto.Easting, punto.Northing);
        return ("llegada", $"TIN:{tin.Handle}/COGO:{punto.Handle}", [punto.Easting, punto.Northing, z],
            "TinSurface.FindElevationAtXY en CogoPoint handle " + punto.Handle);
    }

    private static T Seleccionar<T>(Editor ed, Transaction tx, string etiqueta) where T : Autodesk.AutoCAD.DatabaseServices.Entity
    {
        var opciones = new PromptEntityOptions("\n" + etiqueta + ": ");
        opciones.SetRejectMessage("\nElija una entidad nativa del tipo solicitado en este DWG.");
        opciones.AddAllowedClass(typeof(T), exactMatch: false);
        var id = ed.GetEntity(opciones);
        if (id.Status != PromptStatus.OK) throw new OperationCanceledException();
        var obj = (T)tx.GetObject(id.ObjectId, OpenMode.ForRead);
        if (obj is Autodesk.Civil.DatabaseServices.Entity civil && civil.IsReferenceObject &&
            (!civil.IsReferenceValid || civil.IsReferenceStale))
            throw new InvalidOperationException("La referencia civil está obsoleta o es inválida.");
        return obj;
    }

    private static string Texto(Editor ed, string prompt)
    {
        var dato = ed.GetString(new PromptStringOptions("\n" + prompt + ": ") { AllowSpaces = true });
        if (dato.Status != PromptStatus.OK) throw new OperationCanceledException();
        if (string.IsNullOrWhiteSpace(dato.StringResult)) throw new ArgumentException("Falta " + prompt);
        return dato.StringResult.Trim();
    }
}
