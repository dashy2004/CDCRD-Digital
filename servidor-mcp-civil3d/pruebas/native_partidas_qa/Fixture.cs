using System;
using System.IO;
using System.Collections.Generic;
using System.Text.Json;
using System.Runtime.CompilerServices;
using Autodesk.AutoCAD.Runtime;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;
using App=Autodesk.AutoCAD.ApplicationServices.Core.Application;
public class PartidasFixture
{
 [CommandMethod("CDCRDPARTIDASFIXTURE",CommandFlags.Session)]
 public void Run(){try{Core();}catch(System.Exception e){App.DocumentManager.MdiActiveDocument?.Editor.WriteMessage("\nFixture: "+e.Message);}}
 [MethodImpl(MethodImplOptions.NoInlining)]
 static void Core()
 {
  var doc=App.DocumentManager.MdiActiveDocument;string root=Environment.GetEnvironmentVariable("CDCRD_GM_QA_ROOT");
  if(doc==null||Path.GetFileName(doc.Name)!="CDCRD_GM_RECOVERY_PAYITEMS.dwg"||Path.GetDirectoryName(doc.Name)!=root)throw new InvalidOperationException("Identified QA copy required");
  string path=Path.Combine(root,"payitems-fixture.json");if(File.Exists(path))throw new IOException("Fixture already exists");
  using(doc.LockDocument())using(var tr=doc.Database.TransactionManager.StartTransaction())
  {
   var db=doc.Database;var ms=(BlockTableRecord)tr.GetObject(((BlockTable)tr.GetObject(db.BlockTableId,OpenMode.ForRead))[BlockTableRecord.ModelSpace],OpenMode.ForWrite);
   var rows=new List<object>();
   void Add(Entity e,string name,string unit,double expected,short color=3){e.ColorIndex=color;ms.AppendEntity(e);tr.AddNewlyCreatedDBObject(e,true);rows.Add(new{name,handle=e.Handle.ToString(),type=e.GetType().Name,unit,expected});}
   double x=620900,y=2100900;
   Add(new Line(new Point3d(x,y,0),new Point3d(x+10,y,0)),"line10","M",10);
   Add(new Line(new Point3d(x,y-5,0),new Point3d(x+15,y-5,0)),"line15","M",15);
   var pl=new Polyline();pl.AddVertexAt(0,new Point2d(x,y-10),0,0,0);pl.AddVertexAt(1,new Point2d(x+3,y-6),0,0,0);pl.AddVertexAt(2,new Point2d(x+6,y-10),0,0,0);Add(pl,"poly10","M",10);
   for(int i=0;i<3;i++)Add(new DBPoint(new Point3d(x+25+i*3,y,0)),"point"+i,"EA",1,2);
   var boundary=new Polyline();for(int i=0;i<4;i++)boundary.AddVertexAt(i,new Point2d(x+(i==1||i==2?20:0),y-20-(i>=2?10:0)),0,0,0);boundary.Closed=true;ms.AppendEntity(boundary);tr.AddNewlyCreatedDBObject(boundary,true);
   var hatch=new Hatch();hatch.SetDatabaseDefaults();ms.AppendEntity(hatch);tr.AddNewlyCreatedDBObject(hatch,true);hatch.ColorIndex=4;hatch.SetHatchPattern(HatchPatternType.PreDefined,"ANSI31");hatch.PatternScale=1;hatch.Associative=true;hatch.AppendLoop(HatchLoopTypes.External,new ObjectIdCollection(new[]{boundary.ObjectId}));hatch.EvaluateHatch(true);rows.Add(new{name="hatch200",handle=hatch.Handle.ToString(),type="Hatch",unit="M2",expected=200.0});
   var solid=new Solid3d();solid.CreateBox(2,3,4);solid.TransformBy(Matrix3d.Displacement(new Vector3d(x+30,y-25,0)));Add(solid,"solid24","M3",24,6);
   void Label(string text,double xx,double yy,double height=1.1){var t=new MText{Contents=text,Location=new Point3d(xx,yy,0),TextHeight=height,Width=70,ColorIndex=7};ms.AppendEntity(t);tr.AddNewlyCreatedDBObject(t,true);}
   Label("CDCRD | PARTIDAS DE PAGO QTO | PRUEBA API",x-3,y+12,1.6);
   Label("Civil 3D 2027 - copia de ensayo - unidades metricas",x-3,y+8);
   Label("LONGITUD: 10 + 15 + 10 = 35 m",x-3,y+4);
   Label("CONTEO: 3 puntos",x+24,y+4);
   Label("AREA: hatch 20 x 10 = 200 m2",x-3,y-16);
   Label("SOLIDO: 2 x 3 x 4 = 24 m3",x+25,y-16);
   tr.Commit();File.WriteAllText(path,JsonSerializer.Serialize(new{pid=Environment.ProcessId,entities=rows},new JsonSerializerOptions{WriteIndented=true}));
  }
  App.SetSystemVariable("PDMODE",35);App.SetSystemVariable("PDSIZE",.7);doc.Editor.Regen();
 }
}
