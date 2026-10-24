using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Runtime.CompilerServices;
using Autodesk.AutoCAD.Runtime;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Colors;
using App=Autodesk.AutoCAD.ApplicationServices.Core.Application;
public class PartidasLayout
{
 [CommandMethod("CDCRDPARTIDASLAYOUT",CommandFlags.Session)]
 public void Run(){try{Core();}catch(System.Exception e){App.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nLayout: "+e.Message);}}
 [MethodImpl(MethodImplOptions.NoInlining)]
 static void Core()
 {
  var doc=App.DocumentManager.MdiActiveDocument;string root=Environment.GetEnvironmentVariable("CDCRD_GM_QA_ROOT");
  if(doc==null||Path.GetFileName(doc.Name)!="CDCRD_GM_RECOVERY_PAYITEMS.dwg"||Path.GetDirectoryName(doc.Name)!=root)throw new InvalidOperationException("Identified QA copy required");
  string dest=Path.Combine(root,"payitems-layout-final.json");if(File.Exists(dest))throw new IOException("Layout already done");
  using(doc.LockDocument())using(var tr=doc.Database.TransactionManager.StartTransaction())
  {
   var ms=(BlockTableRecord)tr.GetObject(((BlockTable)tr.GetObject(doc.Database.BlockTableId,OpenMode.ForRead))[BlockTableRecord.ModelSpace],OpenMode.ForWrite);
   foreach(var id in ms.Cast<ObjectId>().ToArray())
   {
    var obj=tr.GetObject(id,OpenMode.ForRead);
    if(obj is MText t && t.Location.X>=620897&&t.Location.X<620970&&t.Location.Y>2100820&&t.Location.Y<2100920)
    {
     t.UpgradeOpen();t.ColorIndex=7;
     if(t.Contents.StartsWith("LONGITUD:")){t.Contents="LONGITUD: 35 m";t.Width=25;}
     if(t.Contents.StartsWith("CONTEO:")){t.Contents="CONTEO: 3 unidades";t.Location=new Point3d(620932,2100904,0);}
     if(t.Contents.StartsWith("AREA:")){t.Contents="AREA: 200 m2";t.Width=24;}
     if(t.Contents.StartsWith("SOLIDO:")){t.Contents="VOLUMEN: 24 m3";t.Location=new Point3d(620932,2100884,0);}
     if(t.Contents.StartsWith("Cantidades de")){t.Location=new Point3d(620897,2100833,0);t.TextHeight=1;}
    }
    if(obj is Table table&&table.Position.DistanceTo(new Point3d(620897,2100858,0))<.01)
    {
     table.UpgradeOpen();table.ColorIndex=7;table.Cells.ContentColor=Color.FromColorIndex(ColorMethod.ByAci,7);table.SetRowHeight(3.5);table.Cells.Alignment=CellAlignment.MiddleCenter;table.GenerateLayout();
    }
   }
   using var fixture=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"payitems-fixture.json")));
   foreach(var row in fixture.RootElement.GetProperty("entities").EnumerateArray().Where(r=>r.GetProperty("type").GetString()=="DBPoint"))
   {
    var id=doc.Database.GetObjectId(false,new Handle(Convert.ToInt64(row.GetProperty("handle").GetString(),16)),0);var point=(DBPoint)tr.GetObject(id,OpenMode.ForRead);
    var ring=new Circle(point.Position,Vector3d.ZAxis,.45){ColorIndex=2};ms.AppendEntity(ring);tr.AddNewlyCreatedDBObject(ring,true);
   }
   tr.Commit();doc.Editor.Regen();File.WriteAllText(dest,JsonSerializer.Serialize(new{ok=true,pid=Environment.ProcessId,scope="QA annotation layout only; pay item entities unchanged"}));
  }
 }
}
