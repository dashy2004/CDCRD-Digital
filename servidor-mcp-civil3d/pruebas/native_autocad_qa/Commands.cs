// Optional native AutoCAD test receipt. Only a dedicated synthetic drawing is allowed.
using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Drawing.Imaging;
using Autodesk.AutoCAD.ApplicationServices;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Runtime;
using App=Autodesk.AutoCAD.ApplicationServices.Core.Application;
using Exception=System.Exception;
public class AutoCadQa
{
    [CommandMethod("CDCRDACADQA",CommandFlags.Session)]
    public void Run()
    {
        string root=Environment.GetEnvironmentVariable("CDCRD_ACAD_QA_ROOT");
        var doc=App.DocumentManager.MdiActiveDocument;
        if(doc==null || string.IsNullOrEmpty(root) || !string.Equals(Path.GetFullPath(doc.Name),Path.Combine(Path.GetFullPath(root),"CDCRD_AUTOCAD_QA.dwg"),StringComparison.OrdinalIgnoreCase))
            throw new Exception("Only the synthetic CDCRD_AUTOCAD_QA.dwg in CDCRD_ACAD_QA_ROOT is allowed");
        using var job=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"job.json")));
        string output=job.RootElement.GetProperty("output").GetString();
        if(Path.GetFileName(output)!=output || !output.EndsWith(".json") || File.Exists(Path.Combine(root,output)))throw new Exception("Invalid receipt path");
        using(doc.LockDocument())
        using(var tr=doc.Database.TransactionManager.StartTransaction())
        {
            string image=null;
            if(job.RootElement.TryGetProperty("image",out var name))
            {
                image=name.GetString();
                if(Path.GetFileName(image)!=image || !image.EndsWith(".png") || File.Exists(Path.Combine(root,image)))throw new Exception("Invalid image path");
                doc.Editor.Regen();using(var bitmap=doc.CapturePreviewImage(1800,1000))bitmap.Save(Path.Combine(root,image),ImageFormat.Png);
            }
            var model=(BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(doc.Database),OpenMode.ForRead);
            var rows=model.Cast<ObjectId>().Where(id=>!id.IsNull&&!id.IsErased).Select(id=>{
                var entity=(Entity)tr.GetObject(id,OpenMode.ForRead);
                return new {handle=id.Handle.ToString(),type=entity.GetType().FullName,layer=entity.Layer};
            }).ToArray();
            var assemblies=AppDomain.CurrentDomain.GetAssemblies().Select(a=>a.GetName().Name).Where(n=>n.StartsWith("Aecc",StringComparison.OrdinalIgnoreCase)).OrderBy(n=>n).ToArray();
            File.WriteAllText(Path.Combine(root,output),JsonSerializer.Serialize(new {drawing=doc.Name,objects=rows,civil_assemblies=assemblies,insunits=App.GetSystemVariable("INSUNITS"),dbmod=App.GetSystemVariable("DBMOD"),image,source="Native AutoCAD API"},new JsonSerializerOptions{WriteIndented=true}));
        }
    }
}
