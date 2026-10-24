using System;
using System.IO;
using System.Linq;
using System.Xml.Linq;
using System.Text.Json;
using System.Runtime.CompilerServices;
using Autodesk.AutoCAD.Runtime;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.Civil.DatabaseServices;
using App=Autodesk.AutoCAD.ApplicationServices.Core.Application;
public class PartidasEvidence
{
 [CommandMethod("CDCRDPARTIDASEVIDENCEFINAL",CommandFlags.Session)]
 public void Run(){try{Core();}catch(System.Exception e){App.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nEvidence: "+e.Message);}}
 [MethodImpl(MethodImplOptions.NoInlining)]
 static void Core()
 {
  var doc=App.DocumentManager.MdiActiveDocument;string root=Environment.GetEnvironmentVariable("CDCRD_GM_QA_ROOT");
  if(doc==null||Path.GetFileName(doc.Name)!="CDCRD_GM_RECOVERY_PAYITEMS.dwg"||Path.GetDirectoryName(doc.Name)!=root)throw new InvalidOperationException("Identified QA copy required");
  using var job=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"partidas-evidence-job.json")));string mode=job.RootElement.GetProperty("mode").GetString();
  string dest=Path.Combine(root,"payitems-evidence-"+mode+".json"); mode=mode.Replace("-final", "");if(File.Exists(dest))throw new IOException("Evidence already exists");
  if(!new[]{"table","plan","report","solid"}.Contains(mode))throw new ArgumentException("Invalid view");
  using(doc.LockDocument())
  {
   if(mode=="table")
   {
    string xmlPath="";string[] ids=Array.Empty<string>();if(!QTOUtility.GenerateXMLReport(new QTOGenerateDetail{ReportType=QTOReportType.SummaryReport,ReportExtent=QTOReportExtent.DrawingExtent},ref xmlPath,ref ids))throw new InvalidOperationException("No report");
    var xml=XDocument.Load(xmlPath);var rows=xml.Descendants().Where(x=>x.Name.LocalName=="DesignProjectPayItem").ToArray();
    string V(XElement e,string name)=>e.Descendants().Single(n=>n.Name.LocalName==name).Value;
    using var tr=doc.Database.TransactionManager.StartTransaction();var ms=(BlockTableRecord)tr.GetObject(((BlockTable)tr.GetObject(doc.Database.BlockTableId,OpenMode.ForRead))[BlockTableRecord.ModelSpace],OpenMode.ForWrite);
    var table=new Autodesk.AutoCAD.DatabaseServices.Table{TableStyle=doc.Database.Tablestyle,Position=new Point3d(620897,2100858,0)};table.SetSize(rows.Length+2,3);table.SetRowHeight(2.5);table.SetColumnWidth(17);table.Cells.TextHeight=1.0;
    table.Cells[0,0].TextString="QTO NATIVO | RESUMEN POR PARTIDA";table.Cells[1,0].TextString="CODIGO";table.Cells[1,1].TextString="CANTIDAD";table.Cells[1,2].TextString="UNIDAD";
    for(int i=0;i<rows.Length;i++){table.Cells[i+2,0].TextString=V(rows[i],"referencePayItemID");table.Cells[i+2,1].TextString=V(rows[i],"estimatedQuantity");table.Cells[i+2,2].TextString=V(rows[i],"unitOfMeasureID");}
    table.GenerateLayout();ms.AppendEntity(table);tr.AddNewlyCreatedDBObject(table,true);
    var text=new MText{Contents=@"Cantidades de GenerateXMLReport | Sin precios\PEnsayo sintetico: 8 entidades, 4 partidas\PInforme completo del dibujo; originales conservados",Location=new Point3d(620897,2100839,0),TextHeight=1.1,Width=65};ms.AppendEntity(text);tr.AddNewlyCreatedDBObject(text,true);tr.Commit();
   }
   else
   {
    using var view=doc.Editor.GetCurrentView();view.ViewDirection=mode=="solid"?new Vector3d(1,-1,1):Vector3d.ZAxis;view.ViewTwist=0;
    view.Target=mode=="solid"?new Point3d(620930,2100875,0):mode=="report"?new Point3d(620925,2100844,0):new Point3d(620923,2100874,0);view.CenterPoint=Point2d.Origin;
    view.Height=mode=="solid"?12:mode=="report"?38:100;view.Width=view.Height*1.8;doc.Editor.SetCurrentView(view);
   }
   doc.Editor.Regen();File.WriteAllText(dest,JsonSerializer.Serialize(new{mode,pid=Environment.ProcessId,source="Native Civil 3D API; table populated from unmodified native QTO XML"}));
  }
 }
}



