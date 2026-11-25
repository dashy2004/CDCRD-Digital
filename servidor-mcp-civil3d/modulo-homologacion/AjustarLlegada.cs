using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.ApplicationServices;
using Autodesk.Civil.DatabaseServices;
using Autodesk.Civil.Settings;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;

namespace Cdcrd.Homologacion;

public class AjustarLlegada
{
    // Sólo se habilitan copias creadas por esta instancia y comprobadas en disco.
    private static readonly Dictionary<string, string> Copias = new(StringComparer.OrdinalIgnoreCase);

    [CommandMethod("CDCRDAJUSTARLLEGADA", CommandFlags.Modal)]
    public void Ajustar()
    {
        var doc = App.DocumentManager.MdiActiveDocument;
        if (doc == null) return;
        var ed = doc.Editor;
        try
        {
            if (Convert.ToInt32(App.GetSystemVariable("DWGTITLED")) != 1 ||
                (Convert.ToInt32(App.GetSystemVariable("DBMOD")) & 1) != 0)
                throw new InvalidOperationException("Se requiere un DWG guardado sin cambios de base de datos pendientes.");
            var ruta = Path.GetFullPath(doc.Name);
            if (!Copias.TryGetValue(ruta, out var origenHash))
            {
                ed.WriteMessage("\nEl ajuste requiere una copia independiente. Ahora sólo se copiará el DWG guardado.");
                var destino = ed.GetFileNameForSave(new PromptSaveFileOptions("\nRuta de una copia de ensayo NUEVA")
                    { Filter = "Dibujo DWG (*.dwg)|*.dwg" });
                if (destino.Status != PromptStatus.OK) return;
                var copia = Path.GetFullPath(destino.StringResult);
                if (!string.Equals(Path.GetExtension(copia), ".dwg", StringComparison.OrdinalIgnoreCase))
                    throw new ArgumentException("Seleccione una ruta DWG.");
                Copias[copia] = CotasLlegada.CopiarVersion(ruta, copia);
                ed.WriteMessage($"\nAbra la copia {copia} y ejecute CDCRDAJUSTARLLEGADA en esta sesión.");
                return;
            }
            if (CotasLlegada.Huella(ruta) != origenHash)
                throw new InvalidOperationException("El contenido de la copia cambió. Prepare otra desde la versión aprobada.");
            var civil = CivilApplication.ActiveDocument;
            if (civil.Settings.DrawingSettings.UnitZoneSettings.DrawingUnits != DrawingUnitType.Meters)
                throw new InvalidOperationException("Este ajuste usa un DWG en metros.");
            using var tx = doc.Database.TransactionManager.StartTransaction();
            var punto = Elegir<CogoPoint>(ed, tx, "Punto COGO de diseño que define la llegada");
            var tin = Elegir<TinSurface>(ed, tx, "TIN de la rasante terminada de DISEÑO");
            if (punto.IsLocked || punto.IsSurveyPoint || punto.IsProjectPoint || tin.Lock ||
                punto.OwnerId != SymbolUtilityServices.GetBlockModelSpaceId(doc.Database) || tin.IsReferenceObject || tin.IsCWSReferenceObject || tin.IsOutOfDate)
                throw new InvalidOperationException("Se requiere un punto de diseño editable y un TIN local actualizado.");
            if (((LayerTableRecord)tx.GetObject(punto.LayerId, OpenMode.ForRead)).IsLocked ||
                ((LayerTableRecord)tx.GetObject(tin.LayerId, OpenMode.ForRead)).IsLocked)
                throw new InvalidOperationException("La capa del punto o del TIN está bloqueada.");
            VerificarGrupos(civil, tx, punto, tin);
            var identidad = ed.GetString(new PromptStringOptions(
                "\nPegue el identificador TIN:…/COGO:… de la medición ANTERIOR: "));
            if (identidad.Status != PromptStatus.OK) return;
            if (!string.Equals(identidad.StringResult.Trim(), $"TIN:{tin.Handle}/COGO:{punto.Handle}",
                StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("TIN o COGO distinto de la lectura anterior.");
            ed.WriteMessage($"\nTIN {tin.Name} (handle {tin.Handle}), punto {punto.PointNumber} (handle {punto.Handle}).");
            var nombre = ed.GetString(new PromptStringOptions("\nConfirme que ES rasante de diseño escribiendo su nombre exacto: ")
                { AllowSpaces = true });
            if (nombre.Status != PromptStatus.OK) return;
            if (!string.Equals(nombre.StringResult, tin.Name, StringComparison.Ordinal))
                throw new InvalidOperationException("La identificación de la superficie de diseño no coincide.");
            double este = Numero(ed, "E de la lectura anterior (WCS local, m)");
            double norte = Numero(ed, "N de la lectura anterior (WCS local, m)");
            double anterior = Numero(ed, "Cota de la lectura anterior (m)");
            CotasLlegada.ExigirCercania(punto.Easting, este, "E");
            CotasLlegada.ExigirCercania(punto.Northing, norte, "N");
            CotasLlegada.ExigirCercania(punto.Elevation, anterior, "COGO");
            CotasLlegada.ExigirCercania(punto.ElevationOverride, anterior, "Elevación efectiva del COGO");
            CotasLlegada.ExigirCercania(tin.FindElevationAtXY(punto.Easting, punto.Northing), anterior, "TIN anterior");
            double nueva = Numero(ed, "Nueva cota de diseño indicada por el responsable (m)");
            CotasLlegada.ExigirCambio(anterior, nueva);
            ed.WriteMessage(FormattableString.Invariant($"\nCota {anterior:R} → {nueva:R} m. Diferencia {nueva - anterior:R} m."));
            var opciones = new PromptKeywordOptions("\nAplicar y reconstruir sólo en esta copia [Aplicar/Cancelar] <Cancelar>: ");
            opciones.Keywords.Add("Aplicar");
            opciones.Keywords.Add("Cancelar");
            opciones.AllowNone = true;
            var confirmar = ed.GetKeywords(opciones);
            if (confirmar.Status != PromptStatus.OK || confirmar.StringResult != "Aplicar") return;
            punto = (CogoPoint)tx.GetObject(punto.ObjectId, OpenMode.ForWrite);
            punto.Elevation = nueva;
            tin = (TinSurface)tx.GetObject(tin.ObjectId, OpenMode.ForWrite);
            tin.Rebuild();
            if (tin.IsOutOfDate) throw new InvalidOperationException("El TIN sigue desactualizado.");
            CotasLlegada.ExigirCercania(punto.Easting, este, "E final");
            CotasLlegada.ExigirCercania(punto.Northing, norte, "N final");
            CotasLlegada.ExigirCercania(punto.Elevation, nueva, "COGO final");
            CotasLlegada.ExigirCercania(punto.ElevationOverride, nueva, "Elevación efectiva final");
            CotasLlegada.ExigirCercania(tin.FindElevationAtXY(punto.Easting, punto.Northing), nueva, "TIN reconstruido");
            tx.Commit();
            Copias.Remove(ruta);
            ed.WriteMessage("\nAjuste confirmado en memoria. Relea con CDCRDMEDIRPUNTO. Para conservarlo, guarde la copia.");
        }
        catch (OperationCanceledException) { ed.WriteMessage("\nAjuste cancelado."); }
        catch (System.Exception ex) { ed.WriteMessage("\nAjuste interrumpido: " + ex.Message); }
    }

    private static void VerificarGrupos(CivilDocument civil, Transaction tx, CogoPoint punto, TinSurface elegida)
    {
        bool origen = false;
        foreach (ObjectId id in civil.GetSurfaceIds())
        {
            if (tx.GetObject(id, OpenMode.ForRead) is not TinSurface superficie || superficie.IsReferenceObject ||
                superficie.IsCWSReferenceObject) continue;
            var operaciones = superficie.Operations;
            for (int i = 0; i < operaciones.Count; i++)
            {
                using var paso = operaciones[i];
                if (paso is not SurfaceOperationAddPointGroup operacion || !operacion.Enabled) continue;
                var grupo = (PointGroup)tx.GetObject(operacion.PointGroupId, OpenMode.ForRead);
                if (grupo.IsOutOfDate)
                    throw new InvalidOperationException("Actualice los grupos de puntos fuente antes de auditar sus miembros.");
                if (!grupo.ContainsPoint(punto.PointNumber)) continue;
                if (superficie.ObjectId != elegida.ObjectId)
                    throw new InvalidOperationException("El mismo punto alimenta también el TIN " + superficie.Name);
                if (grupo.IsLocked || grupo.IsElevationOverridden)
                    throw new InvalidOperationException("Un grupo fuente está bloqueado o modifica la elevación.");
                origen = true;
            }
        }
        if (!origen) throw new InvalidOperationException("El COGO debe pertenecer a un grupo fuente activo del TIN.");
    }

    private static double Numero(Editor ed, string texto)
    {
        var valor = ed.GetDouble(new PromptDoubleOptions("\n" + texto + ": ") { AllowNone = false });
        if (valor.Status != PromptStatus.OK) throw new OperationCanceledException();
        return valor.Value;
    }

    private static T Elegir<T>(Editor ed, Transaction tx, string texto) where T : Autodesk.AutoCAD.DatabaseServices.Entity
    {
        var opciones = new PromptEntityOptions("\n" + texto + ": ");
        opciones.SetRejectMessage("\nSeleccione una entidad del tipo solicitado.");
        opciones.AddAllowedClass(typeof(T), false);
        var id = ed.GetEntity(opciones);
        if (id.Status != PromptStatus.OK) throw new OperationCanceledException();
        return (T)tx.GetObject(id.ObjectId, OpenMode.ForRead);
    }
}
