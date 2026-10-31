using System;
using System.IO;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.ApplicationServices;
using AcApp = Autodesk.AutoCAD.ApplicationServices.Core.Application;

namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        private static object CrearDocumento(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string template = Txt(p, "plantilla");
            if (string.IsNullOrWhiteSpace(template) || !Path.IsPathFullyQualified(template)
                || !string.Equals(Path.GetExtension(template), ".dwt", StringComparison.OrdinalIgnoreCase)
                || !File.Exists(template))
                throw new ArgumentException("plantilla requiere ruta absoluta a un DWT existente.");
            // Add keeps all previous documents open, including unsaved drawings.
            var document = AcApp.DocumentManager.Add(template);
            AcApp.DocumentManager.MdiActiveDocument = document;
            return new { dibujo = document.Name, insunits = (int)document.Database.Insunits,
                plantilla = Path.GetFileName(template), documentos_anteriores_conservados = true };
        }
    }
}
