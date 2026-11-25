using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.EditorInput;
using Autodesk.AutoCAD.PlottingServices;
using Autodesk.AutoCAD.Runtime;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;

namespace Cdcrd.Homologacion;

public class Planos
{
    [CommandMethod("CDCRDREEMITIRPDF", CommandFlags.Modal)]
    public void ExportarPresentacion()
    {
        var doc = App.DocumentManager.MdiActiveDocument;
        if (doc == null) return;
        var ed = doc.Editor;
        try
        {
            if (PlotFactory.ProcessPlotState != ProcessPlotState.NotPlotting)
                throw new InvalidOperationException("Hay otro trazado en ejecución.");
            if (doc.Database.TileMode || Convert.ToInt32(App.GetSystemVariable("CVPORT")) != 1)
                throw new InvalidOperationException("Active la presentación a emitir y salga de su ventana gráfica.");
            using var tx = doc.Database.TransactionManager.StartOpenCloseTransaction();
            var id = LayoutManager.Current.GetLayoutId(LayoutManager.Current.CurrentLayout);
            var layout = (Layout)tx.GetObject(id, OpenMode.ForRead);
            var pc3 = layout.PlotConfigurationName;
            if (!(pc3.Equals("DWG To PDF.pc3", StringComparison.OrdinalIgnoreCase) ||
                 (pc3.StartsWith("AutoCAD PDF", StringComparison.OrdinalIgnoreCase) &&
                  pc3.EndsWith(".pc3", StringComparison.OrdinalIgnoreCase))))
                throw new InvalidOperationException("Seleccione un trazador PDF de AutoCAD en la configuración de la presentación.");
            using var info = new PlotInfo { Layout = id };
            using var validador = new PlotInfoValidator { MediaMatchingPolicy = MatchingPolicy.MatchDisabled };
            validador.Validate(info);
            var resp = ed.GetFileNameForSave(new PromptSaveFileOptions("\nEmitir " + layout.LayoutName)
                { Filter = "PDF (*.pdf)|*.pdf" });
            if (resp.Status != PromptStatus.OK) return;
            var destino = Path.GetFullPath(resp.StringResult);
            if (!Path.GetExtension(destino).Equals(".pdf", StringComparison.OrdinalIgnoreCase) || File.Exists(destino))
                throw new IOException("Seleccione un nombre PDF nuevo para la revisión.");
            var tmp = Path.Combine(Path.GetDirectoryName(destino)!, Guid.NewGuid().ToString("N") + ".pdf");
            try
            {
                ed.Regen();
                using (var motor = PlotFactory.CreatePublishEngine())
                using (var pagina = new PlotPageInfo())
                {
                    motor.BeginPlot(null, null);
                    try
                    {
                        motor.BeginDocument(info, doc.Name, null, 1, true, tmp);
                        try
                        {
                            motor.BeginPage(pagina, info, true, null);
                            try { motor.BeginGenerateGraphics(null); motor.EndGenerateGraphics(null); }
                            finally { motor.EndPage(null); }
                        }
                        finally { motor.EndDocument(null); }
                    }
                    finally { motor.EndPlot(null); }
                }
                using (var archivo = File.OpenRead(tmp))
                {
                    Span<byte> encabezado = stackalloc byte[5];
                    archivo.ReadExactly(encabezado);
                    if (!encabezado.SequenceEqual("%PDF-"u8)) throw new IOException("Salida PDF inválida.");
                }
                File.Move(tmp, destino, overwrite: false);
                ed.WriteMessage("\nPresentación emitida: " + layout.LayoutName + " → " + destino);
            }
            finally { File.Delete(tmp); }
        }
        catch (System.Exception ex) { ed.WriteMessage("\nEmisión interrumpida: " + ex.Message); }
    }
}
