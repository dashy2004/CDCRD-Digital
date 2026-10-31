using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Autodesk.AutoCAD.DatabaseServices;
using Autodesk.AutoCAD.Geometry;

namespace Cdcrd.Civil3dBridge
{
    internal static partial class Handlers
    {
        // Local coordinates, no screen selection, command queue or source erasure.
        private static object CrearBloqueNativo(JsonObject p, string method)
        {
            ExigirEscritura(method, p);
            string name = Txt(p, "nombre");
            if (string.IsNullOrWhiteSpace(name) || name.StartsWith("*"))
                throw new ArgumentException("nombre de bloque publico no vacio requerido.");
            SymbolUtilityServices.ValidateSymbolName(name, false);
            var rows = p["entidades"] as JsonArray;
            if (rows == null || rows.Count < 1 || rows.Count > 1024)
                throw new ArgumentException("entidades requiere de 1 a 1024 primitivas.");
            var allowed = new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            { "linea", "polilinea", "polilinea3d", "texto", "mtexto", "circulo",
              "solido", "punto", "cilindro", "caja", "esfera" };
            foreach (var row in rows)
                if (row is not JsonObject entity || !allowed.Contains(Txt(entity, "tipo") ?? ""))
                    throw new ArgumentException("Primitiva no admitida en el bloque.");

            var doc = Doc(); var db = doc.Database;
            using (doc.LockDocument())
            using (var tr = db.TransactionManager.StartTransaction())
            {
                var table = (BlockTable)tr.GetObject(db.BlockTableId, OpenMode.ForRead);
                if (table.Has(name))
                    throw new ArgumentException("El bloque ya existe; use otro nombre para conservarlo.");
                table.UpgradeOpen();
                var block = new BlockTableRecord { Name = name, Origin = Point3d.Origin };
                table.Add(block); tr.AddNewlyCreatedDBObject(block, true);
                var handles = new List<string>();
                foreach (JsonObject row in rows)
                {
                    using (var entity = EntidadDe(row, tr, db))
                    {
                        entity.SetDatabaseDefaults(db);
                        entity.Layer = "0";
                        AplicarComunes(entity, row, tr, db);
                        block.AppendEntity(entity); tr.AddNewlyCreatedDBObject(entity, true);
                        if (entity is Polyline3d polyline)
                        {
                            foreach (var value in (JsonArray)row["puntos"])
                            {
                                var vertex = new PolylineVertex3d(PuntoDe(value, "puntos"));
                                polyline.AppendVertex(vertex); tr.AddNewlyCreatedDBObject(vertex, true);
                            }
                            polyline.Closed = Flag(row, "cerrada");
                        }
                        handles.Add(HandleOf(entity.ObjectId));
                    }
                }
                var result = new { nombre = name, handle = HandleOf(block.ObjectId),
                    entidades = handles, cantidad = handles.Count, origen = new[] { 0, 0, 0 },
                    instancias_creadas = 0, atomico = true };
                tr.Commit();
                return result;
            }
        }
    }
}
