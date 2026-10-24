using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using Autodesk.AutoCAD.Runtime;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using App=Autodesk.AutoCAD.ApplicationServices.Core.Application;
public class PartidasGrid
{
 [CommandMethod("CDCRDPARTIDASGRID",CommandFlags.Session)]
 public void Run()
 {
  try
  {
   var doc=App.DocumentManager.MdiActiveDocument;string root=Environment.GetEnvironmentVariable("CDCRD_GM_QA_ROOT");
   if(doc==null||Path.GetFileName(doc.Name)!="CDCRD_GM_RECOVERY_PAYITEMS.dwg"||Path.GetDirectoryName(doc.Name)!=root)throw new InvalidOperationException("Identified copy required");
   string dest=Path.Combine(root,"payitems-grid.json");if(File.Exists(dest))throw new IOException("Already done");
   using(doc.LockDocument())using(var tr=doc.Database.TransactionManager.StartTransaction())
   {
    var ms=(BlockTableRecord)tr.GetObject(((BlockTable)tr.GetObject(doc.Database.BlockTableId,OpenMode.ForRead))[BlockTableRecord.ModelSpace],OpenMode.ForRead);
    var table=ms.Cast<ObjectId>().Select(id=>tr.GetObject(id,OpenMode.ForRead)).OfType<Table>().Single(t=>t.Position.DistanceTo(new Point3d(620897,2100858,0))<.01);
    table.UpgradeOpen();table.RecomputeTableBlock(true);tr.Commit();doc.Editor.Regen();
    File.WriteAllText(dest,JsonSerializer.Serialize(new{ok=true,handle=table.Handle.ToString(),rows=table.Rows.Count}));
   }
  }catch(System.Exception e){App.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nGrid: "+e.Message);}
 }
}
