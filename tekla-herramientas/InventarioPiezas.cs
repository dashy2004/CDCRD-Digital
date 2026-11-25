#pragma warning disable 1633
#pragma reference "Tekla.Macros.Runtime"
#pragma reference "Tekla.Structures"
#pragma reference "Tekla.Structures.Model"
#pragma reference "Tekla.Structures.Drawing"
#pragma reference "System.Windows.Forms"
#pragma reference "System.Runtime.Serialization"
#pragma warning restore 1633

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.Serialization.Json;
using System.Windows.Forms;
using Tekla.Structures;
using Tekla.Structures.Model;
using Tekla.Structures.Drawing;
using TPart = Tekla.Structures.Model.Part;

namespace CDCRD.Tekla
{
    public class Pieza
    {
        public string guid { get; set; }
        public string perfil { get; set; }
        public string material { get; set; }
        public string conjunto_guid { get; set; }
        public string marca { get; set; }
    }

    public class PlanoConjunto
    {
        public string conjunto_guid { get; set; }
        public string marca { get; set; }
        public string nombre { get; set; }
        public string estado_de_actualizacion { get; set; }
    }

    public class Inventario
    {
        public string esquema { get; set; }
        public string modelo { get; set; }
        public List<Pieza> piezas { get; set; }
        public List<PlanoConjunto> planos_de_conjunto { get; set; }
        public int seleccion_omitida { get; set; }

        public static Inventario Crear(string modelo, List<Pieza> piezas, List<PlanoConjunto> planos, int omitidos)
        {
            if (string.IsNullOrWhiteSpace(modelo) || piezas == null || piezas.Count == 0)
                throw new ArgumentException("Seleccione al menos una pieza en un modelo identificado.");
            return new Inventario { esquema = "tekla-piezas/1", modelo = modelo, piezas = piezas,
                planos_de_conjunto = planos, seleccion_omitida = omitidos };
        }

        public void Exportar(string destino)
        {
            destino = Path.GetFullPath(destino);
            if (!string.Equals(Path.GetExtension(destino), ".json", StringComparison.OrdinalIgnoreCase))
                throw new ArgumentException("Se requiere un nombre .json.");
            string tmp = Path.Combine(Path.GetDirectoryName(destino), Path.GetRandomFileName());
            var archivo = new FileStream(tmp, FileMode.CreateNew, FileAccess.Write, FileShare.None);
            try
            {
                using (archivo)
                    new DataContractJsonSerializer(typeof(Inventario)).WriteObject(archivo, this);
                File.Move(tmp, destino);
            }
            finally { File.Delete(tmp); }
        }
    }

}

namespace UserMacros
{
    using CDCRD.Tekla;

    public sealed class Macro
    {
        [global::Tekla.Macros.Runtime.MacroEntryPointAttribute()]
        public static void Run(global::Tekla.Macros.Runtime.IMacroRuntime runtime)
        {
            try
            {
                var model = new Model();
                if (!model.GetConnectionStatus()) throw new InvalidOperationException("Abra un modelo de Tekla Structures.");
                var selected = new global::Tekla.Structures.Model.UI.ModelObjectSelector().GetSelectedObjects();
                var piezas = new List<Pieza>();
                var conjuntos = new Dictionary<int, string>();
                int omitidos = 0;
                while (selected.MoveNext())
                {
                    var part = selected.Current as TPart;
                    if (part == null) { omitidos++; continue; }
                    var conjunto = part.GetAssembly();
                    string guidConjunto = null;
                    if (conjunto != null)
                    {
                        guidConjunto = GuidModelo(model, conjunto.Identifier);
                        conjuntos[conjunto.Identifier.ID] = guidConjunto;
                    }
                    string marca = "";
                    bool hayMarca = part.GetReportProperty("PART_POS", ref marca);
                    piezas.Add(new Pieza { guid = GuidModelo(model, part.Identifier),
                        perfil = part.Profile.ProfileString, material = part.Material.MaterialString,
                        conjunto_guid = guidConjunto, marca = hayMarca ? marca : null });
                }
                if (piezas.Count == 0) throw new InvalidOperationException("Active el selector de piezas y seleccione una o más piezas.");
                var handler = new DrawingHandler();
                if (!handler.GetConnectionStatus())
                    throw new InvalidOperationException("Sin conexión de dibujos para comprobar los planos de conjunto.");
                var planos = new List<PlanoConjunto>();
                var drawings = handler.GetDrawings();
                while (drawings.MoveNext())
                {
                    var dibujo = drawings.Current as AssemblyDrawing;
                    if (dibujo == null) continue;
                    string conjunto;
                    if (!conjuntos.TryGetValue(dibujo.AssemblyIdentifier.ID, out conjunto)) continue;
                    planos.Add(new PlanoConjunto { conjunto_guid = conjunto, marca = dibujo.Mark,
                        nombre = dibujo.Name, estado_de_actualizacion = dibujo.UpToDateStatus.ToString() });
                }
                var informe = Inventario.Crear(model.GetInfo().ModelName, piezas.OrderBy(p => p.guid).ToList(),
                    planos.OrderBy(d => d.conjunto_guid).ThenBy(d => d.marca).ToList(), omitidos);
                using (var guardar = new SaveFileDialog { Filter = "Inventario JSON (*.json)|*.json",
                    AddExtension = true, DefaultExt = "json", Title = "Guardar inventario privado de piezas" })
                {
                    if (guardar.ShowDialog() != DialogResult.OK) return;
                    informe.Exportar(guardar.FileName);
                    MessageBox.Show(string.Format("Guardado: {0} piezas, {1} planos de conjunto, {2} selecciones omitidas.\n{3}",
                        piezas.Count, planos.Count, omitidos, guardar.FileName), "Inventario");
                }
            }
            catch (Exception ex) { MessageBox.Show(ex.Message, "Inventario interrumpido"); }
        }

        private static string GuidModelo(Model model, Identifier referencia)
        {
            Guid guid;
            if (!Guid.TryParse(model.GetGUIDByIdentifier(referencia), out guid) || guid == Guid.Empty)
                throw new InvalidOperationException("Tekla no devolvió GUID para el objeto " + referencia.ID);
            return guid.ToString("D");
        }
    }
}
