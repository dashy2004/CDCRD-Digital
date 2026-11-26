// Puente de consola entre el servidor MCP (Python) y Tekla Open API.
// Lee UN comando JSON por stdin: {"op": "...", ...argumentos}
// Escribe UNA respuesta JSON por stdout: {"ok": true, "datos": ...} o {"ok": false, "error": "..."}
// Se compila con csc de .NET Framework 4 (C# 5): ver compilar.ps1.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using System.Web.Script.Serialization;
using T = Tekla.Structures.Model;
using U = Tekla.Structures.Model.UI;
using G = Tekla.Structures.Geometry3d;
using Op = Tekla.Structures.Model.Operations.Operation;

static class Puente
{
    static readonly T.Model modelo = new T.Model();
    static readonly JavaScriptSerializer json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };

    static int Main()
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        var salida = new Dictionary<string, object>();
        try
        {
            string texto;
            using (var lector = new StreamReader(Console.OpenStandardInput(), new UTF8Encoding(false))) texto = lector.ReadToEnd();
            var cmd = json.Deserialize<Dictionary<string, object>>(texto);
            if (!modelo.GetConnectionStatus()) throw new InvalidOperationException("Tekla Structures no está abierto o no responde a Open API.");
            salida["datos"] = Despachar(Texto(cmd, "op"), cmd);
            salida["ok"] = true;
        }
        catch (Exception e)
        {
            salida["ok"] = false;
            salida["error"] = e.GetType().Name + ": " + e.Message;
        }
        Console.Write(json.Serialize(salida));
        return 0;
    }

    static object Despachar(string op, Dictionary<string, object> c)
    {
        switch (op)
        {
            case "estado": return Estado();
            case "crear_modelo": return CrearModelo(c);
            case "abrir_modelo": return new T.ModelHandler().Open(Texto(c, "ruta"), false);
            case "guardar": return new T.ModelHandler().Save(Opcional(c, "comentario", "Servidor MCP"), Opcional(c, "usuario", ""));
            case "definir_ejes": return DefinirEjes(c);
            case "crear_piezas": return CrearPiezas(c);
            case "crear_placa": return CrearPlaca(c);
            case "crear_tornillos": return CrearTornillos(c);
            case "crear_soldadura": return CrearSoldadura(c);
            case "listar": return Listar(c);
            case "borrar": return Borrar(c);
            case "seleccionar": return Seleccionar(c);
            case "vista": return Vista(c);
            case "informe": return Informe(c);
            default: throw new ArgumentException("Operación desconocida: " + op);
        }
    }

    // ---------- lectura de argumentos ----------
    static string Texto(Dictionary<string, object> c, string k)
    {
        object v;
        if (!c.TryGetValue(k, out v) || v == null) throw new ArgumentException("Falta el argumento '" + k + "'.");
        return Convert.ToString(v, CultureInfo.InvariantCulture);
    }
    static string Opcional(Dictionary<string, object> c, string k, string def)
    {
        object v;
        return c.TryGetValue(k, out v) && v != null ? Convert.ToString(v, CultureInfo.InvariantCulture) : def;
    }
    static double Numero(object v) { return Convert.ToDouble(v, CultureInfo.InvariantCulture); }
    static double NumeroOpc(Dictionary<string, object> c, string k, double def)
    {
        object v;
        return c.TryGetValue(k, out v) && v != null ? Numero(v) : def;
    }
    static IList Lista(Dictionary<string, object> c, string k)
    {
        object v;
        if (!c.TryGetValue(k, out v) || !(v is IList)) throw new ArgumentException("El argumento '" + k + "' debe ser una lista.");
        return (IList)v;
    }
    static G.Point Punto(object v)
    {
        var l = v as IList;
        if (l == null || l.Count != 3) throw new ArgumentException("Un punto debe ser [x, y, z] en mm.");
        return new G.Point(Numero(l[0]), Numero(l[1]), Numero(l[2]));
    }
    static double[] P3(G.Point p) { return new[] { Math.Round(p.X, 3), Math.Round(p.Y, 3), Math.Round(p.Z, 3) }; }
    static TEnum Enumerado<TEnum>(string v) where TEnum : struct
    {
        TEnum r;
        if (!Enum.TryParse(v, true, out r)) throw new ArgumentException("Valor '" + v + "' no válido. Opciones: " + string.Join(", ", Enum.GetNames(typeof(TEnum))));
        return r;
    }
    static void Posicion(T.Position pos, Dictionary<string, object> c)
    {
        pos.Plane = Enumerado<T.Position.PlaneEnum>(Opcional(c, "plano", "MIDDLE"));
        pos.Rotation = Enumerado<T.Position.RotationEnum>(Opcional(c, "rotacion", "TOP"));
        pos.Depth = Enumerado<T.Position.DepthEnum>(Opcional(c, "profundidad", "MIDDLE"));
        pos.PlaneOffset = NumeroOpc(c, "desfase_plano", 0);
        pos.RotationOffset = NumeroOpc(c, "desfase_rotacion", 0);
        pos.DepthOffset = NumeroOpc(c, "desfase_profundidad", 0);
    }
    static T.ModelObject PorId(object id)
    {
        var o = modelo.SelectModelObject(new Tekla.Structures.Identifier(Convert.ToInt32(id, CultureInfo.InvariantCulture)));
        if (o == null) throw new ArgumentException("No existe el objeto con id " + id + ".");
        return o;
    }
    static T.Part Pieza(object id)
    {
        var p = PorId(id) as T.Part;
        if (p == null) throw new ArgumentException("El id " + id + " no es una pieza.");
        return p;
    }

    // ---------- operaciones ----------
    static object Estado()
    {
        var i = modelo.GetInfo();
        var d = new Dictionary<string, object>();
        d["modelo"] = i.ModelName; d["ruta"] = i.ModelPath; d["usuario_unico"] = i.SingleUserModel;
        d["version"] = Tekla.Structures.TeklaStructuresInfo.GetCurrentProgramVersion();
        int n = 0; var e = modelo.GetModelObjectSelector().GetAllObjectsWithType(new[] { typeof(T.Part) });
        while (e.MoveNext()) n++;
        d["piezas"] = n;
        return d;
    }

    static object CrearModelo(Dictionary<string, object> c)
    {
        string carpeta = Texto(c, "carpeta"), nombre = Texto(c, "nombre");
        bool ok = new T.ModelHandler().CreateNewSingleUserModel(nombre, carpeta, Opcional(c, "plantilla", ""));
        var d = new Dictionary<string, object>(); d["creado"] = ok; d["ruta"] = Path.Combine(carpeta, nombre); return d;
    }

    static object DefinirEjes(Dictionary<string, object> c)
    {
        var e = modelo.GetModelObjectSelector().GetAllObjectsWithType(T.ModelObject.ModelObjectEnum.GRID);
        T.Grid g = e.MoveNext() ? (T.Grid)e.Current : new T.Grid();
        if (c.ContainsKey("origen")) g.Origin = Punto(c["origen"]);
        g.CoordinateX = Texto(c, "x"); g.CoordinateY = Texto(c, "y"); g.CoordinateZ = Texto(c, "z");
        g.LabelX = Opcional(c, "rotulos_x", ""); g.LabelY = Opcional(c, "rotulos_y", ""); g.LabelZ = Opcional(c, "rotulos_z", "");
        bool existia = g.Identifier.ID > 0;
        bool ok = existia ? g.Modify() : g.Insert();
        modelo.CommitChanges();
        var d = new Dictionary<string, object>(); d["ok"] = ok; d["modificada"] = existia; d["id"] = g.Identifier.ID; return d;
    }

    static object CrearPiezas(Dictionary<string, object> c)
    {
        var res = new List<object>();
        foreach (var item in Lista(c, "piezas"))
        {
            var p = (Dictionary<string, object>)item;
            bool columna = Opcional(p, "tipo", "viga").ToLowerInvariant().StartsWith("col");
            var b = new T.Beam(columna ? T.Beam.BeamTypeEnum.COLUMN : T.Beam.BeamTypeEnum.BEAM);
            b.StartPoint = Punto(p["inicio"]); b.EndPoint = Punto(p["fin"]);
            b.Name = Opcional(p, "nombre", columna ? "COLUMNA" : "VIGA");
            b.Profile.ProfileString = Texto(p, "perfil"); b.Material.MaterialString = Texto(p, "material");
            b.Class = Opcional(p, "clase", columna ? "7" : "3");
            Posicion(b.Position, p);
            bool ok = b.Insert();
            var d = new Dictionary<string, object>(); d["nombre"] = b.Name; d["ok"] = ok; d["id"] = b.Identifier.ID; res.Add(d);
        }
        modelo.CommitChanges();
        return res;
    }

    static object CrearPlaca(Dictionary<string, object> c)
    {
        var pl = new T.ContourPlate();
        foreach (var v in Lista(c, "contorno")) pl.AddContourPoint(new T.ContourPoint(Punto(v), null));
        if (pl.Contour.ContourPoints.Count < 3) throw new ArgumentException("El contorno necesita al menos tres puntos.");
        pl.Name = Opcional(c, "nombre", "PLACA");
        pl.Profile.ProfileString = Texto(c, "perfil"); pl.Material.MaterialString = Texto(c, "material");
        pl.Class = Opcional(c, "clase", "99");
        pl.Position.Depth = Enumerado<T.Position.DepthEnum>(Opcional(c, "profundidad", "MIDDLE"));
        pl.Position.DepthOffset = NumeroOpc(c, "desfase_profundidad", 0);
        bool ok = pl.Insert(); modelo.CommitChanges();
        var d = new Dictionary<string, object>(); d["ok"] = ok; d["id"] = pl.Identifier.ID; return d;
    }

    static object CrearTornillos(Dictionary<string, object> c)
    {
        var bt = new T.BoltArray();
        bt.PartToBoltTo = Pieza(c["pieza_principal"]); bt.PartToBeBolted = Pieza(c["pieza_atornillada"]);
        bt.FirstPosition = Punto(c["inicio"]); bt.SecondPosition = Punto(c["fin"]);
        bt.BoltStandard = Texto(c, "norma"); bt.BoltSize = Numero(c["diametro"]);
        bt.Tolerance = NumeroOpc(c, "holgura", 2.0);
        bt.BoltType = Opcional(c, "montaje", "obra").ToLowerInvariant().StartsWith("t") ? T.BoltGroup.BoltTypeEnum.BOLT_TYPE_WORKSHOP : T.BoltGroup.BoltTypeEnum.BOLT_TYPE_SITE;
        bt.CutLength = NumeroOpc(c, "longitud_corte", 100);
        bt.Length = NumeroOpc(c, "longitud", 0); bt.ExtraLength = NumeroOpc(c, "longitud_extra", 0);
        bt.ThreadInMaterial = T.BoltGroup.BoltThreadInMaterialEnum.THREAD_IN_MATERIAL_YES;
        bt.Position.Depth = Enumerado<T.Position.DepthEnum>(Opcional(c, "profundidad", "MIDDLE"));
        bt.Position.Plane = Enumerado<T.Position.PlaneEnum>(Opcional(c, "plano", "MIDDLE"));
        bt.Position.Rotation = Enumerado<T.Position.RotationEnum>(Opcional(c, "rotacion", "FRONT"));
        bt.Bolt = true; bt.Washer1 = true; bt.Washer2 = false; bt.Washer3 = false; bt.Nut1 = true; bt.Nut2 = false; bt.Hole1 = true; bt.Hole2 = true; bt.Hole3 = true; bt.Hole4 = true; bt.Hole5 = true;
        bt.StartPointOffset.Dx = NumeroOpc(c, "desfase_inicio", 0);
        foreach (var v in Lista(c, "separaciones_x")) bt.AddBoltDistX(Numero(v));
        foreach (var v in Lista(c, "separaciones_y")) bt.AddBoltDistY(Numero(v));
        bool ok = bt.Insert(); modelo.CommitChanges();
        var d = new Dictionary<string, object>(); d["ok"] = ok; d["id"] = bt.Identifier.ID;
        var pos = new List<object>(); if (ok) { bt.Select(); foreach (G.Point p in bt.BoltPositions) pos.Add(P3(p)); }
        d["norma"] = bt.BoltStandard; d["diametro"] = bt.BoltSize;
        d["posiciones"] = pos; return d;
    }

    static object CrearSoldadura(Dictionary<string, object> c)
    {
        var w = new T.Weld();
        w.MainObject = Pieza(c["pieza_principal"]); w.SecondaryObject = Pieza(c["pieza_secundaria"]);
        w.TypeAbove = T.BaseWeld.WeldTypeEnum.WELD_TYPE_FILLET; w.SizeAbove = Numero(c["tamano"]);
        if (c.ContainsKey("tamano_inferior")) { w.TypeBelow = T.BaseWeld.WeldTypeEnum.WELD_TYPE_FILLET; w.SizeBelow = Numero(c["tamano_inferior"]); }
        w.ShopWeld = !Opcional(c, "montaje", "taller").ToLowerInvariant().StartsWith("o");
        bool ok = w.Insert(); modelo.CommitChanges();
        var d = new Dictionary<string, object>(); d["ok"] = ok; d["id"] = w.Identifier.ID; return d;
    }

    static Dictionary<string, object> Describir(T.Part p)
    {
        var d = new Dictionary<string, object>();
        d["id"] = p.Identifier.ID; d["nombre"] = p.Name; d["perfil"] = p.Profile.ProfileString; d["material"] = p.Material.MaterialString; d["clase"] = p.Class;
        d["tipo"] = p.GetType().Name;
        var b = p as T.Beam;
        if (b != null) { d["inicio"] = P3(b.StartPoint); d["fin"] = P3(b.EndPoint); }
        var s = p.GetSolid();
        if (s != null) { d["caja_min"] = P3(s.MinimumPoint); d["caja_max"] = P3(s.MaximumPoint); }
        double v = 0;
        if (p.GetReportProperty("LENGTH", ref v)) d["longitud_mm"] = Math.Round(v, 3);
        if (p.GetReportProperty("WEIGHT", ref v)) d["peso_kg"] = Math.Round(v, 3);
        return d;
    }

    static object Listar(Dictionary<string, object> c)
    {
        string filtro = Opcional(c, "nombre", "");
        var res = new List<object>();
        var e = modelo.GetModelObjectSelector().GetAllObjectsWithType(new[] { typeof(T.Part) });
        while (e.MoveNext())
        {
            var p = e.Current as T.Part;
            if (p == null || (filtro.Length > 0 && p.Name.IndexOf(filtro, StringComparison.OrdinalIgnoreCase) < 0)) continue;
            res.Add(Describir(p));
        }
        var d = new Dictionary<string, object>(); d["piezas"] = res;
        var grupos = new List<object>(); var soldaduras = new List<object>();
        var eb = modelo.GetModelObjectSelector().GetAllObjectsWithType(new[] { typeof(T.BoltGroup) });
        while (eb.MoveNext())
        {
            var bg = eb.Current as T.BoltGroup; if (bg == null) continue;
            var g = new Dictionary<string, object>(); g["id"] = bg.Identifier.ID; g["norma"] = bg.BoltStandard; g["diametro"] = bg.BoltSize;
            var pos = new List<object>(); foreach (G.Point p in bg.BoltPositions) pos.Add(P3(p));
            g["posiciones"] = pos; grupos.Add(g);
        }
        var ew = modelo.GetModelObjectSelector().GetAllObjectsWithType(new[] { typeof(T.BaseWeld) });
        while (ew.MoveNext())
        {
            var w = ew.Current as T.BaseWeld; if (w == null) continue;
            var g = new Dictionary<string, object>(); g["id"] = w.Identifier.ID; g["tamano"] = w.SizeAbove; g["tamano_inferior"] = w.SizeBelow;
            soldaduras.Add(g);
        }
        int nb = grupos.Count, nw = soldaduras.Count;
        d["tornillos"] = grupos; d["soldaduras_detalle"] = soldaduras;
        d["grupos_de_tornillos"] = nb; d["soldaduras"] = nw;
        return d;
    }

    static object Borrar(Dictionary<string, object> c)
    {
        var res = new List<object>();
        foreach (var id in Lista(c, "ids"))
        {
            var d = new Dictionary<string, object>(); d["id"] = id; d["borrado"] = PorId(id).Delete(); res.Add(d);
        }
        modelo.CommitChanges();
        return res;
    }

    static object Seleccionar(Dictionary<string, object> c)
    {
        var l = new ArrayList();
        foreach (var id in Lista(c, "ids")) l.Add(PorId(id));
        return new U.ModelObjectSelector().Select(l);
    }

    static object Vista(Dictionary<string, object> c)
    {
        var caja = new G.AABB(Punto(c["min"]), Punto(c["max"]));
        int n = 0;
        if (Opcional(c, "ajustar_area", "true").ToLowerInvariant() == "true")
        {
            var ve = U.ViewHandler.GetVisibleViews();
            while (ve.MoveNext())
            {
                var v = ve.Current; v.WorkArea = caja; v.ViewDepthUp = NumeroOpc(c, "profundidad_vista", 40000); v.ViewDepthDown = NumeroOpc(c, "profundidad_vista", 40000);
                if (v.Modify()) n++;
            }
        }
        var d = new Dictionary<string, object>(); d["vistas_ajustadas"] = n; d["zoom"] = U.ViewHandler.ZoomToBoundingBox(caja); return d;
    }

    static object Informe(Dictionary<string, object> c)
    {
        Seleccionar(c);
        return Op.CreateReportFromSelected(Texto(c, "plantilla"), Texto(c, "archivo"), Opcional(c, "titulo", ""), "", "");
    }
}
