using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;

namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        // An ungrouped entity is suspicious, not proof of garbage. Only empty
        // groups and unused generated definitions are eligible for this endpoint.
        private static object GmResidues(JsonObject p,string method)
        {
            bool apply=Flag(p,"aplicar");
            if(apply)ExigirEscritura(method,p);
            var doc=Doc();var db=doc.Database;
            using(doc.LockDocument())
            using(var tr=db.TransactionManager.StartTransaction())
            {
                var rows=new List<Dictionary<string,object>>();
                var ids=new Dictionary<string,ObjectId>(StringComparer.OrdinalIgnoreCase);
                var grouped=new HashSet<ObjectId>();
                foreach(DBDictionaryEntry e in (DBDictionary)tr.GetObject(db.GroupDictionaryId,OpenMode.ForRead))
                {
                    var group=(Group)tr.GetObject(e.Value,OpenMode.ForRead);
                    foreach(var id in group.GetAllEntityIds())if(!id.IsNull && id.IsValid && !id.IsErased)grouped.Add(id);
                }
                void Add(ObjectId id,string kind,string name,bool eligible,string reason,string[] contents)
                {
                    string handle=id.Handle.ToString();ids[handle]=id;
                    rows.Add(new Dictionary<string,object>{{"handle",handle},{"tipo",kind},{"nombre",name},
                        {"borrable",eligible},{"motivo",reason},{"referencias",contents.OrderBy(x=>x,StringComparer.Ordinal).ToArray()}});
                }
                foreach(var old in GruposMuertos(tr,db))
                {
                    var id=(ObjectId)old["_id"];
                    var group=(Group)tr.GetObject(id,OpenMode.ForRead);
                    var live=group.GetAllEntityIds().Where(x=>!x.IsNull && x.IsValid && !x.IsErased && !x.IsEffectivelyErased).ToArray();
                    bool eligible=live.Length==0 && ((string)old["nombre"]).StartsWith("GM - ",StringComparison.OrdinalIgnoreCase);
                    Add(id,"grupo",(string)old["nombre"],eligible,
                        eligible?"Grupo GM sin miembros vivos":"Conservar: grupo con miembros vivos o identidad ajena",
                        live.Select(x=>x.Handle.ToString()).ToArray());
                }
                const string prefix="GM - Profile - 2D - StickLog ~ ";
                var blocks=(BlockTable)tr.GetObject(db.BlockTableId,OpenMode.ForRead);
                var unused=new ObjectIdCollection();
                foreach(ObjectId id in blocks)
                {
                    var block=(BlockTableRecord)tr.GetObject(id,OpenMode.ForRead);
                    if(block.IsLayout||block.IsFromExternalReference||!block.Name.StartsWith(prefix,StringComparison.Ordinal))continue;
                    var refs=block.GetBlockReferenceIds(false,true);
                    if(refs.Count==0)unused.Add(id);
                }
                // Purge computes eligibility; it does not erase the objects.
                db.Purge(unused);
                foreach(ObjectId id in unused)
                {
                    var block=(BlockTableRecord)tr.GetObject(id,OpenMode.ForRead);
                    Add(id,"definicion_bloque",block.Name,true,"Definicion generada GM sin referencias, purgable",
                        block.Cast<ObjectId>().Select(x=>x.Handle.ToString()).ToArray());
                }
                var model=(BlockTableRecord)tr.GetObject(SymbolUtilityServices.GetBlockModelSpaceId(db),OpenMode.ForRead);
                foreach(ObjectId id in model)
                {
                    if(grouped.Contains(id))continue;
                    var entity=tr.GetObject(id,OpenMode.ForRead) as Entity;
                    if(entity is BlockReference reference)
                    {
                        var definition=(BlockTableRecord)tr.GetObject(reference.BlockTableRecord,OpenMode.ForRead);
                        if(definition.Name.StartsWith(prefix,StringComparison.Ordinal))
                            Add(id,"referencia_sin_grupo",definition.Name,false,
                                "Revisar: ausencia de grupo no acredita residuo; no se borra automaticamente",new[]{definition.Handle.ToString()});
                    }
                    else if(entity is Hatch && entity.Layer=="GM-PROF-STICKLOG-2D")
                        Add(id,"hatch_sin_grupo",entity.Layer,false,
                            "Revisar: capa y ausencia de grupo no acreditan residuo",Array.Empty<string>());
                }
                rows=rows.OrderBy(x=>(string)x["handle"],StringComparer.Ordinal).ToList();
                string fingerprint=Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(
                    db.FingerprintGuid.ToString()+JsonSerializer.Serialize(rows)))).ToLowerInvariant();
                var removed=new List<string>();
                if(apply)
                {
                    if(Txt(p,"huella")!=fingerprint)throw new ArgumentException("Inventario distinto; volver a previsualizar residuos.");
                    var selection=(p["handles"] as JsonArray)?.Select(x=>x.GetValue<string>()).ToArray() ?? Array.Empty<string>();
                    if(selection.Length==0 || selection.Distinct(StringComparer.OrdinalIgnoreCase).Count()!=selection.Length)
                        throw new ArgumentException("Indique handles concretos, sin duplicados, de la previsualizacion.");
                    foreach(var handle in selection)
                    {
                        var row=rows.SingleOrDefault(x=>string.Equals((string)x["handle"],handle,StringComparison.OrdinalIgnoreCase));
                        if(row==null || !(bool)row["borrable"])throw new ArgumentException("Objeto no elegible para limpieza: "+handle);
                    }
                    foreach(var handle in selection)
                    {
                        tr.GetObject(ids[handle],OpenMode.ForWrite).Erase();removed.Add(handle);
                    }
                    tr.Commit();
                }
                return new {dibujo=doc.Name,huella=fingerprint,aplicado=apply,objetos=rows,borrados=removed,
                    nota="Seleccion explicita; no se borran entidades vivas sin grupo, superficies ni objetos de otros perfiles por nombre."};
            }
        }
    }
}
