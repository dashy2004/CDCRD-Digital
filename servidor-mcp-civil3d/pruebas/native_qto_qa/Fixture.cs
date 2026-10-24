// Synthetic 40 x 20 m base at 100; design plane rises from 98 to 102.
// Analytic cut=fill=400 m3. No real site or project quantities.
using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Runtime.CompilerServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using Autodesk.AutoCAD.Runtime;
using Autodesk.Civil.DatabaseServices;
using App=Autodesk.AutoCAD.ApplicationServices.Core.Application;
public class QtoFixture
{
 [CommandMethod("CDCRDQTOFIXTURE",CommandFlags.Session)]
 public void Run(){try{Core();}catch(System.Exception e){App.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nQTO fixture: "+e.Message);}}
 [MethodImpl(MethodImplOptions.NoInlining)]
 static void Core()
 {
  var doc=App.DocumentManager.MdiActiveDocument;
  string root=Environment.GetEnvironmentVariable("CDCRD_GM_QA_ROOT");
  if(doc==null||Path.GetFileName(doc.Name)!="CDCRD_GM_RECOVERY_QTO.dwg"||Path.GetDirectoryName(doc.Name)!=root)throw new InvalidOperationException("Wrong QA copy");
  string dest=Path.Combine(root,"qto-native-fixture.json");if(File.Exists(dest))throw new IOException("Receipt exists");
  object result=null;string error=null;
  try{
   using(doc.LockDocument())using(var tr=doc.Database.TransactionManager.StartTransaction())
   {
    var existing=Autodesk.Civil.ApplicationServices.CivilApplication.ActiveDocument.GetSurfaceIds().Cast<ObjectId>().Select(id=>((Autodesk.Civil.DatabaseServices.Surface)tr.GetObject(id,OpenMode.ForRead)).Name).ToArray();
    if(existing.Any(n=>n.StartsWith("CDX QA QTO ")))throw new InvalidOperationException("Fixture already exists");
    ObjectId Make(string name,bool design){var id=TinSurface.Create(doc.Database,name);var s=(TinSurface)tr.GetObject(id,OpenMode.ForWrite);s.AddVertices(new Point3dCollection(new[]{new Point3d(620500,2100000,design?98:100),new Point3d(620540,2100000,design?102:100),new Point3d(620540,2100020,design?102:100),new Point3d(620500,2100020,design?98:100)}));s.Rebuild();return id;}
    var a=Make("CDX QA QTO BASE 0522",false);var b=Make("CDX QA QTO DESIGN 0522",true);
    result=new{base_surface=a.Handle.ToString(),comparison=b.Handle.ToString(),expected_cut=400,expected_fill=400};tr.Commit();
   }
  }catch(System.Exception e){error=e.GetBaseException().Message;}
  File.WriteAllText(dest,JsonSerializer.Serialize(new{ok=error==null,error,result}));
 }
}
