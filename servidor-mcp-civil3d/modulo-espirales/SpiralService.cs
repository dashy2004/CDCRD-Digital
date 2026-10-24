using System;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil;
using Autodesk.Civil.DatabaseServices;
using App = Autodesk.AutoCAD.ApplicationServices.Core.Application;
using CivilApp = Autodesk.Civil.ApplicationServices.CivilApplication;

namespace Cdcrd.Espirales;

internal static class SpiralService
{
    internal static Action<string> QaCheckpoint = null;
    private const string RecordName = "CDCRD_SPIRAL_V1";
    private static string Text(JsonObject p, string key) => p[key]?.GetValue<string>() ?? "";
    private static Point3d Pt(double[] p) => new Point3d(p[0], p[1], 0);
    private static double[] XY(Point2d p) => new[] { p.X, p.Y };
    internal static object Execute(JsonObject p, out bool committed)
    {
        committed = false;
        var doc = App.DocumentManager.MdiActiveDocument ?? throw new InvalidOperationException("Sin documento.");
        if (!DateTimeOffset.TryParse(Text(p,"vence_utc"),out var expires) || expires < DateTimeOffset.UtcNow || expires > DateTimeOffset.UtcNow.AddMinutes(5))
            throw new ArgumentException("Solicitud vencida o plazo invalido.");
        if (p["pid"]?.GetValue<int>() != Environment.ProcessId || !Path.IsPathFullyQualified(Text(p,"dibujo")) ||
            !string.Equals(Path.GetFullPath(doc.Name),Path.GetFullPath(Text(p,"dibujo")),StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Documento o PID distinto al esperado.");
        var civil = CivilApp.ActiveDocument;
        if (Convert.ToInt32(App.GetSystemVariable("INSUNITS")) != 6 || civil.Settings.DrawingSettings.UnitZoneSettings.DrawingUnits.ToString() != "Meters")
            throw new ArgumentException("Se requieren unidades Civil y AutoCAD en metros.");
        string action = Text(p,"accion");
        if (action != "crear" && action != "leer") throw new ArgumentException("accion debe ser crear o leer.");
        bool create = action == "crear", simulate = p["simular"]?.GetValue<bool>() ?? true;
        if (create && (Environment.GetEnvironmentVariable("CDCRD_C3D_SOLO_LECTURA") == "1" || Environment.GetEnvironmentVariable("CDCRD_C3D_PERMITIR_COMANDOS") != "1"))
            throw new InvalidOperationException("Escritura/comandos deshabilitados.");
        using (doc.LockDocument())
        using (var tr = doc.Database.TransactionManager.StartTransaction())
        {
            Alignment axis;
            JsonObject geometry;
            if (create)
            {
                geometry = p["geometria"] as JsonObject ?? throw new ArgumentException("geometria requerida.");
                var c = SpiralContract.Parse(geometry); // Validate fit before adding any native object.
                string name = Text(p,"nombre"), layerName = Text(p,"capa");
                if (string.IsNullOrWhiteSpace(name) || name.Length > 200 || name.Any(char.IsControl) || string.IsNullOrWhiteSpace(layerName))
                    throw new ArgumentException("Nombre/capa invalidos.");
                if (civil.GetAlignmentIds().Cast<ObjectId>().Any(id => string.Equals(((Alignment)tr.GetObject(id,OpenMode.ForRead)).Name,name,StringComparison.OrdinalIgnoreCase)))
                    throw new ArgumentException("Ya existe el alineamiento; no se reemplaza.");
                SymbolUtilityServices.ValidateSymbolName(layerName,false);
                var layers = (LayerTable)tr.GetObject(doc.Database.LayerTableId,OpenMode.ForRead);
                ObjectId layer;
                if (layers.Has(layerName)) layer = layers[layerName];
                else
                {
                    layers.UpgradeOpen(); var record = new LayerTableRecord { Name = layerName, Color = Autodesk.AutoCAD.Colors.Color.FromColorIndex(Autodesk.AutoCAD.Colors.ColorMethod.ByAci,3) };
                    layer = layers.Add(record); tr.AddNewlyCreatedDBObject(record,true);
                }
                if (civil.Styles.AlignmentStyles.Count == 0 || civil.Styles.LabelSetStyles.AlignmentLabelSetStyles.Count == 0)
                    throw new InvalidOperationException("Se requieren estilos de alineamiento y etiquetas en el dibujo.");
                var idNew = Alignment.Create(civil,name,ObjectId.Null,layer,civil.Styles.AlignmentStyles[0],civil.Styles.LabelSetStyles.AlignmentLabelSetStyles[0]);
                axis = (Alignment)tr.GetObject(idNew,OpenMode.ForWrite);
                var first = axis.Entities.AddFixedLine(Pt(c.Start),Pt(c.Pi));
                var last = axis.Entities.AddFixedLine(Pt(c.Pi),Pt(c.End));
                QaCheckpoint?.Invoke("tangents-created");
                axis.Entities.AddFreeSCS(first.EntityId,last.EntityId,c.InLength,c.OutLength,SpiralParamType.Length,c.Radius,false,SpiralType.Clothoid);
                axis.ReferencePointStation = c.Station;
                QaCheckpoint?.Invoke("scs-created");
                axis.CreateExtensionDictionary();
                var dict = (DBDictionary)tr.GetObject(axis.ExtensionDictionary,OpenMode.ForWrite);
                var xr = new Xrecord(); string json = geometry.ToJsonString();
                xr.Data = new ResultBuffer(Enumerable.Range(0,(json.Length + 239)/240)
                    .Select(i => new TypedValue((int)DxfCode.Text,json.Substring(i*240,Math.Min(240,json.Length-i*240)))).ToArray());
                dict.SetAt(RecordName,xr); tr.AddNewlyCreatedDBObject(xr,true);
            }
            else
            {
                var candidates = civil.GetAlignmentIds().Cast<ObjectId>().Select(id => (Alignment)tr.GetObject(id,OpenMode.ForRead))
                    .Where(a => a.Handle.ToString().Equals(Text(p,"alineamiento"),StringComparison.OrdinalIgnoreCase) || a.Name == Text(p,"alineamiento")).ToArray();
                if (candidates.Length != 1) throw new ArgumentException("Alineamiento inexistente o ambiguo.");
                axis = candidates[0];
                if (axis.IsReferenceObject || axis.ExtensionDictionary.IsNull) throw new ArgumentException("Requiere alineamiento local creado por este modulo.");
                var dict = (DBDictionary)tr.GetObject(axis.ExtensionDictionary,OpenMode.ForRead);
                if (!dict.Contains(RecordName)) throw new ArgumentException("Falta contrato geometrico CDCRD_SPIRAL_V1.");
                var xr = (Xrecord)tr.GetObject(dict.GetAt(RecordName),OpenMode.ForRead);
                geometry = JsonNode.Parse(string.Concat(xr.Data.AsArray().Select(v => v.Value as string))) as JsonObject;
            }
            var spec = SpiralContract.Parse(geometry);
            if (axis.StationEquations.Count != 0) throw new ArgumentException("Ecuaciones de estacion no soportadas.");
            var entities = axis.Entities.Cast<AlignmentEntity>().ToArray();
            var scs = entities.OfType<AlignmentSCS>().Single();
            var parts = entities.SelectMany(e => Enumerable.Range(0,e.SubEntityCount).Select(i => e[i])).OrderBy(s => s.StartStation).ToArray();
            if (entities.Length != 3 || parts.Length != 5 || scs.SpiralIn.SpiralDefinition != SpiralType.Clothoid || scs.SpiralOut.SpiralDefinition != SpiralType.Clothoid)
                throw new InvalidOperationException("Topologia nativa inesperada: requiere linea-espiral-arco-espiral-linea.");
            double tolerance = Math.Max(1e-6,spec.Length*1e-10), maxError = 0;
            var stations = Enumerable.Range(0,101).Select(i => axis.StartingStation+axis.Length*i/100)
                .Concat(spec.Breaks.Select(s=>Math.Clamp(spec.Station+s,axis.StartingStation,axis.EndingStation))).Distinct().OrderBy(s=>s).ToArray();
            var samples = stations.Select(s => new { station=s, points=new[]{-3.5,0.0,3.5}.Select(offset => {
                double x=0,y=0; axis.PointLocation(s,offset,ref x,ref y); var expected=spec.At(s,offset);
                double error=Math.Max(Math.Abs(x-expected.X),Math.Abs(y-expected.Y)); maxError=Math.Max(maxError,error);
                return new {offset,xy=new[]{x,y},error,heading=expected.Heading,curvature=expected.Curvature}; }).ToArray() }).ToArray();
            double[] expectedLengths={spec.TangentIn,spec.InLength,spec.ArcLength,spec.OutLength,spec.TangentOut};
            if (Math.Abs(axis.Length-spec.Length)>tolerance || Math.Abs(axis.StartingStation-spec.Station)>tolerance ||
                Math.Abs(axis.EndingStation-spec.Station-spec.Length)>tolerance || maxError>tolerance ||
                parts.Where((s,i)=>Math.Abs(s.Length-expectedLengths[i])>tolerance).Any() ||
                Math.Abs(scs.Arc.Radius-spec.Radius)>tolerance || Math.Abs(scs.SpiralIn.A-Math.Sqrt(spec.Radius*spec.InLength))>tolerance ||
                Math.Abs(scs.SpiralOut.A-Math.Sqrt(spec.Radius*spec.OutLength))>tolerance)
                throw new InvalidOperationException("Geometria nativa distinta al contrato; max XY="+maxError+", longitud="+axis.Length+"/"+spec.Length);
            QaCheckpoint?.Invoke("geometry-verified");
            var result = new { handle=create && simulate?null:axis.Handle.ToString(), name=axis.Name, geometry,
                start_station=axis.StartingStation, end_station=axis.EndingStation, length=axis.Length, max_xy_error=maxError,
                turn=spec.Turn, trim_in=spec.TrimIn, trim_out=spec.TrimOut, spiral_in_a=scs.SpiralIn.A, spiral_out_a=scs.SpiralOut.A,
                parts=parts.Select(s=>new {type=s.SubEntityType.ToString(),length=s.Length,start_station=s.StartStation,end_station=s.EndStation,start=XY(s.StartPoint),end=XY(s.EndPoint)}).ToArray(),
                samples, simulation=create && simulate, units="m", spiral="Clothoid", siteless=axis.IsSiteless };
            if (create && !simulate) {tr.Commit();committed=true;} else tr.Abort();
            return result;
        }
    }
}
