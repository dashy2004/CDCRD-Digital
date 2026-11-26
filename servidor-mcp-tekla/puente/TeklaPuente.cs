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
using K = Tekla.Structures.Catalogs;
using D = Tekla.Structures.Drawing;
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
            case "abrir_modelo": return Exigir(new T.ModelHandler().Open(Texto(c, "ruta"), false), "Tekla no pudo abrir el modelo " + Texto(c, "ruta"));
            case "guardar": return Exigir(new T.ModelHandler().Save(Opcional(c, "comentario", "Servidor MCP"), Opcional(c, "usuario", "")), "Tekla no pudo guardar el modelo");
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
            case "ajustar_extremo": return CortePorPlano(c, true);
            case "cortar_plano": return CortePorPlano(c, false);
            case "cortar_con_pieza": return CortarConPieza(Pieza(c["pieza"]), Pieza(c["pieza_cortante"]), false);
            case "despuntar": return Despuntar(c);
            case "componente": return Componente(c);
            case "detalle": return Detalle(c);
            case "normas_tornillos": return NormasTornillos();
            case "catalogo_componentes": return CatalogoComponentes(c);
            case "planos": return Planos();
            case "numerar": return Numerar();
            case "crear_plano": return CrearPlano(c);
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
    // Una operación de Tekla que devuelve false no hizo nada: se informa como error, no como dato.
    static bool Exigir(bool ok, string mensaje)
    {
        if (!ok) throw new InvalidOperationException(mensaje + ".");
        return true;
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
    static G.Vector Vector(object v) { var p = Punto(v); return new G.Vector(p.X, p.Y, p.Z); }
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
        bool ok = Exigir(new T.ModelHandler().CreateNewSingleUserModel(nombre, carpeta, Opcional(c, "plantilla", "")), "Tekla no pudo crear el modelo " + nombre);
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
        bool ok = Exigir(existia ? g.Modify() : g.Insert(), "Tekla rechazó la cuadrícula");
        modelo.CommitChanges();
        var d = new Dictionary<string, object>(); d["ok"] = ok; d["modificada"] = existia; d["id"] = g.Identifier.ID; return d;
    }

    static object CrearPiezas(Dictionary<string, object> c)
    {
        var res = new List<object>();
        var pendientes = new List<Dictionary<string, object>>();
        foreach (var item in Lista(c, "piezas"))      // se valida el lote entero antes de insertar nada
        {
            var p = item as Dictionary<string, object>;
            if (p == null) throw new ArgumentException("Cada pieza debe ser un objeto.");
            Punto(p["inicio"]); Punto(p["fin"]); Texto(p, "perfil"); Texto(p, "material");
            pendientes.Add(p);
        }
        foreach (var p in pendientes)
        {
            bool columna = Opcional(p, "tipo", "viga").ToLowerInvariant().StartsWith("col");
            var b = new T.Beam(columna ? T.Beam.BeamTypeEnum.COLUMN : T.Beam.BeamTypeEnum.BEAM);
            b.StartPoint = Punto(p["inicio"]); b.EndPoint = Punto(p["fin"]);
            b.Name = Opcional(p, "nombre", columna ? "COLUMNA" : "VIGA");
            b.Profile.ProfileString = Texto(p, "perfil"); b.Material.MaterialString = Texto(p, "material");
            b.Class = Opcional(p, "clase", columna ? "7" : "3");
            Posicion(b.Position, p);
            bool ok = b.Insert();
            if (!ok) { modelo.CommitChanges(); throw new InvalidOperationException("Tekla rechazó la pieza '" + b.Name + "' (perfil " + b.Profile.ProfileString + "). Se insertaron antes " + res.Count + " piezas del lote."); }
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
        bool ok = Exigir(pl.Insert(), "Tekla rechazó la placa (perfil " + pl.Profile.ProfileString + ")"); modelo.CommitChanges();
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
        bool ok = Exigir(bt.Insert(), "Tekla rechazó el grupo de tornillos"); modelo.CommitChanges();
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
        bool ok = Exigir(w.Insert(), "Tekla rechazó la soldadura"); modelo.CommitChanges();
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
        if (p.GetReportProperty("WEIGHT_NET", ref v)) d["peso_neto_kg"] = Math.Round(v, 3);
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
        var componentes = new List<object>();
        var ec = modelo.GetModelObjectSelector().GetAllObjectsWithType(new[] { typeof(T.Connection), typeof(T.Detail) });
        while (ec.MoveNext())
        {
            var bc = ec.Current as T.BaseComponent; if (bc == null) continue;
            var g = new Dictionary<string, object>(); g["id"] = bc.Identifier.ID; g["numero"] = bc.Number; g["nombre"] = bc.Name; g["tipo"] = bc.GetType().Name;
            componentes.Add(g);
        }
        d["componentes"] = componentes;
        d["tornillos"] = grupos; d["soldaduras_detalle"] = soldaduras;
        d["grupos_de_tornillos"] = nb; d["soldaduras"] = nw;
        return d;
    }

    static object Borrar(Dictionary<string, object> c)
    {
        var res = new List<object>();
        var objetos = new List<T.ModelObject>();
        foreach (var id in Lista(c, "ids")) objetos.Add(PorId(id));      // si falta algún id no se borra ninguno
        foreach (var o in objetos)
        {
            var d = new Dictionary<string, object>(); d["id"] = o.Identifier.ID; d["borrado"] = o.Delete(); res.Add(d);
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
        return Exigir(Op.CreateReportFromSelected(Texto(c, "plantilla"), Texto(c, "archivo"), Opcional(c, "titulo", ""), "", ""), "Tekla no generó el informe (revise la plantilla)");
    }

    // ---------- cortes ----------
    static object CortePorPlano(Dictionary<string, object> c, bool ajuste)
    {
        var plano = new T.Plane();
        plano.Origin = Punto(c["origen"]); plano.AxisX = Vector(c["eje_x"]); plano.AxisY = Vector(c["eje_y"]);
        var padre = Pieza(c["pieza"]);
        bool ok; int id;
        if (ajuste) { var f = new T.Fitting(); f.Father = padre; f.Plane = plano; ok = f.Insert(); id = f.Identifier.ID; }
        else { var k = new T.CutPlane(); k.Father = padre; k.Plane = plano; ok = k.Insert(); id = k.Identifier.ID; }
        modelo.CommitChanges();
        Exigir(ok, "Tekla rechazó el corte por plano");
        var d = new Dictionary<string, object>(); d["ok"] = ok; d["id"] = id; return d;
    }

    // `temporal`: la pieza cortante la creó el servidor (despunte) y se borra siempre.
    // Una pieza del usuario solo se borra si el corte se hizo; si falla, recupera su clase.
    static object CortarConPieza(T.Part padre, T.Part cortante, bool temporal)
    {
        string clase = cortante.Class;
        cortante.Class = T.BooleanPart.BooleanOperativeClassName;
        Exigir(temporal ? cortante.Insert() : cortante.Modify(), "Tekla rechazó la pieza cortante");
        var b = new T.BooleanPart(); b.Father = padre; b.Type = T.BooleanPart.BooleanTypeEnum.BOOLEAN_CUT;
        bool ok = b.SetOperativePart(cortante) && b.Insert();
        if (ok || temporal) cortante.Delete();      // el corte conserva su propia copia de la pieza cortante
        else { cortante.Class = clase; cortante.Modify(); }
        modelo.CommitChanges();
        Exigir(ok, "Tekla rechazó el corte; la pieza cortante se conserva");
        var d = new Dictionary<string, object>(); d["ok"] = ok; d["id"] = b.Identifier.ID; return d;
    }

    // Despunte rectangular: resta a la pieza una caja alineada con los ejes globales.
    static object Despuntar(Dictionary<string, object> c)
    {
        var padre = Pieza(c["pieza"]);
        G.Point a = Punto(c["min"]), b = Punto(c["max"]);
        double alto = b.Z - a.Z, zm = (a.Z + b.Z) / 2;
        if (b.X <= a.X || b.Y <= a.Y || alto <= 0) throw new ArgumentException("La caja del despunte necesita max > min en los tres ejes.");
        var caja = new T.ContourPlate();
        foreach (var p in new[] { new G.Point(a.X, a.Y, zm), new G.Point(b.X, a.Y, zm), new G.Point(b.X, b.Y, zm), new G.Point(a.X, b.Y, zm) })
            caja.AddContourPoint(new T.ContourPoint(p, null));
        caja.Name = "CORTE"; caja.Profile.ProfileString = "PL" + alto.ToString("0.###", CultureInfo.InvariantCulture);
        caja.Material.MaterialString = padre.Material.MaterialString;
        caja.Position.Depth = T.Position.DepthEnum.MIDDLE;
        return CortarConPieza(padre, caja, true);
    }

    // ---------- componentes ----------
    // Devuelve si Tekla encontró el archivo de atributos; uno distinto de "standard" que no exista es un error.
    static bool Atributos(T.BaseComponent comp, Dictionary<string, object> c)
    {
        comp.Name = Opcional(c, "nombre", ""); comp.Number = Convert.ToInt32(c["numero"], CultureInfo.InvariantCulture);
        string archivo = Opcional(c, "archivo_atributos", "standard");
        bool cargado = comp.LoadAttributesFromFile(archivo);
        if (!cargado && archivo != "standard") throw new ArgumentException("Tekla no encontró el archivo de atributos '" + archivo + "' para el componente " + comp.Number + ".");
        object attrs;
        if (!c.TryGetValue("atributos", out attrs) || attrs == null) return cargado;
        foreach (var kv in (Dictionary<string, object>)attrs)
        {
            if (kv.Value is bool) comp.SetAttribute(kv.Key, (bool)kv.Value ? 1 : 0);
            else if (kv.Value is int) comp.SetAttribute(kv.Key, (int)kv.Value);
            else if (kv.Value is decimal || kv.Value is double) comp.SetAttribute(kv.Key, Numero(kv.Value));
            else comp.SetAttribute(kv.Key, Convert.ToString(kv.Value, CultureInfo.InvariantCulture));
        }
        return cargado;
    }

    static Dictionary<string, object> Creado(T.ModelObject o, bool ok)
    {
        var d = new Dictionary<string, object>(); d["ok"] = ok; d["id"] = o.Identifier.ID;
        var piezas = new List<object>(); int nb = 0, nw = 0;
        if (ok)
        {
            var e = o.GetChildren();
            while (e.MoveNext())
            {
                var p = e.Current as T.Part;
                if (p != null) { var x = new Dictionary<string, object>(); x["id"] = p.Identifier.ID; x["nombre"] = p.Name; x["perfil"] = p.Profile.ProfileString; piezas.Add(x); }
                else if (e.Current is T.BoltGroup) nb++;
                else if (e.Current is T.BaseWeld) nw++;
            }
        }
        d["piezas_creadas"] = piezas; d["grupos_de_tornillos"] = nb; d["soldaduras"] = nw;
        return d;
    }

    static object Componente(Dictionary<string, object> c)
    {
        var cn = new T.Connection();
        bool cargado = Atributos(cn, c);
        cn.UpVector = c.ContainsKey("vector_arriba") ? Vector(c["vector_arriba"]) : new G.Vector(0, 0, 1000);
        cn.PositionType = Enumerado<Tekla.Structures.PositionTypeEnum>(Opcional(c, "posicion", "COLLISION_PLANE"));
        cn.SetPrimaryObject(Pieza(c["pieza_principal"]));
        var sec = new ArrayList();
        foreach (var id in Lista(c, "piezas_secundarias")) sec.Add(Pieza(id));
        if (sec.Count == 0) throw new ArgumentException("Indique al menos una pieza secundaria.");
        if (sec.Count == 1) cn.SetSecondaryObject((T.ModelObject)sec[0]); else cn.SetSecondaryObjects(sec);
        bool ok = Exigir(cn.Insert(), "Tekla rechazó el componente " + cn.Number); modelo.CommitChanges();
        var r = Creado(cn, ok); r["archivo_de_atributos_cargado"] = cargado; return r;
    }

    static object Detalle(Dictionary<string, object> c)
    {
        var dt = new T.Detail();
        bool cargado = Atributos(dt, c);
        dt.UpVector = c.ContainsKey("vector_arriba") ? Vector(c["vector_arriba"]) : new G.Vector(0, 0, 1000);
        dt.PositionType = Enumerado<Tekla.Structures.PositionTypeEnum>(Opcional(c, "posicion", "MIDDLE_PLANE"));
        dt.DetailType = Enumerado<Tekla.Structures.DetailTypeEnum>(Opcional(c, "tipo_detalle", "END"));
        dt.SetPrimaryObject(Pieza(c["pieza"]));
        dt.SetReferencePoint(Punto(c["punto"]));
        bool ok = Exigir(dt.Insert(), "Tekla rechazó el detalle " + dt.Number); modelo.CommitChanges();
        var r = Creado(dt, ok); r["archivo_de_atributos_cargado"] = cargado; return r;
    }

    // ---------- catálogos ----------
    static object NormasTornillos()
    {
        var porNorma = new SortedDictionary<string, SortedSet<double>>(StringComparer.OrdinalIgnoreCase);
        var e = new K.CatalogHandler().GetBoltItems();
        while (e.MoveNext())
        {
            var b = e.Current; if (b == null || string.IsNullOrEmpty(b.Standard)) continue;
            if (!porNorma.ContainsKey(b.Standard)) porNorma[b.Standard] = new SortedSet<double>();
            porNorma[b.Standard].Add(Math.Round(b.Size, 4));
        }
        var res = new List<object>();
        foreach (var kv in porNorma) { var d = new Dictionary<string, object>(); d["norma"] = kv.Key; d["diametros_mm"] = new List<double>(kv.Value); res.Add(d); }
        return res;
    }

    static object CatalogoComponentes(Dictionary<string, object> c)
    {
        string filtro = Opcional(c, "filtro", "");
        var res = new List<object>();
        var e = new K.CatalogHandler().GetComponentItems();
        while (e.MoveNext())
        {
            var it = e.Current; if (it == null) continue;
            string texto = (it.UIName ?? "") + " " + (it.Name ?? "") + " " + it.Number;
            if (filtro.Length > 0 && texto.IndexOf(filtro, StringComparison.OrdinalIgnoreCase) < 0) continue;
            var d = new Dictionary<string, object>(); d["numero"] = it.Number; d["nombre"] = it.Name; d["titulo"] = it.UIName; d["tipo"] = it.Type.ToString(); res.Add(d);
        }
        return res;
    }

    // ---------- numeración ----------
    // Open API no numera: se lanza una macro de Tekla escrita en la carpeta del modelo.
    const string MacroNumerar = "namespace Tekla.Technology.Akit.UserScript { public class Script { " +
        "public static void Run(Tekla.Technology.Akit.IScript akit) { akit.Callback(\"acmd_partnumbers_all\", \"\", \"main_frame\"); } } }";

    static object Numerar()
    {
        string carpetas = "";
        Tekla.Structures.TeklaStructuresSettings.GetAdvancedOption("XS_MACRO_DIRECTORY", ref carpetas);
        string macros = (carpetas ?? "").Split(';')[0].Trim();
        if (macros.Length == 0) throw new InvalidOperationException("XS_MACRO_DIRECTORY no está definida; numere desde Tekla.");
        string archivo = Path.Combine(modelo.GetInfo().ModelPath, "mcp_numerar.cs");
        var relativa = new Uri(Path.Combine(macros, "modeling") + Path.DirectorySeparatorChar).MakeRelativeUri(new Uri(archivo));
        if (relativa.IsAbsoluteUri) throw new InvalidOperationException("El modelo está en otra unidad que las macros de Tekla; numere desde Tekla.");
        File.WriteAllText(archivo, MacroNumerar);
        var d = new Dictionary<string, object>();
        try
        {
            d["macro_lanzada"] = Exigir(Op.RunMacro(Uri.UnescapeDataString(relativa.ToString()).Replace('/', Path.DirectorySeparatorChar)), "Tekla no lanzó la macro de numeración");
            System.Threading.Thread.Sleep(500);      // margen para que Tekla lea el archivo antes de borrarlo
            var limite = DateTime.UtcNow.AddSeconds(80);      // por debajo del tiempo máximo del servidor (120 s)
            while (Op.IsMacroRunning() && DateTime.UtcNow < limite) System.Threading.Thread.Sleep(300);
            d["macro_terminada"] = !Op.IsMacroRunning();
        }
        finally { File.Delete(archivo); }
        d["numeracion_al_dia"] = Op.IsNumberingUpToDateAll();
        return d;
    }

    // ---------- planos ----------
    static D.DrawingHandler Dibujos()
    {
        var dh = new D.DrawingHandler();
        if (!dh.GetConnectionStatus()) throw new InvalidOperationException("La API de planos de Tekla no responde.");
        return dh;
    }

    static Dictionary<string, object> DescribirPlano(D.Drawing p)
    {
        var d = new Dictionary<string, object>();
        d["tipo"] = p.GetType().Name; d["marca"] = p.Mark; d["nombre"] = p.Name; d["titulo"] = p.Title1; d["estado"] = p.UpToDateStatus.ToString();
        return d;
    }

    static object Planos()
    {
        var res = new List<object>();
        var e = Dibujos().GetDrawings();
        while (e.MoveNext()) res.Add(DescribirPlano(e.Current));
        return res;
    }

    static object CrearPlano(Dictionary<string, object> c)
    {
        var dh = Dibujos();
        string tipo = Opcional(c, "tipo", "pieza").ToLowerInvariant(), attr = Opcional(c, "archivo_atributos", "standard");
        var pieza = Pieza(c["pieza"]);
        if (!Op.IsNumberingUpToDate(pieza)) throw new InvalidOperationException("La numeración de la pieza no está al día. Use antes la operación numerar.");
        D.Drawing plano;
        bool ok;
        if (tipo.StartsWith("conj")) { var a = new D.AssemblyDrawing(pieza.GetAssembly().Identifier, attr); ok = a.Insert(); plano = a; }
        else { var s = new D.SinglePartDrawing(pieza.Identifier, attr); ok = s.Insert(); plano = s; }
        Exigir(ok, "Tekla no creó el plano (puede que ya exista uno de esa pieza o conjunto)");
        var d = DescribirPlano(plano); d["ok"] = ok;
        if (dh.IsAnyDrawingOpen()) d["cerrado"] = dh.CloseActiveDrawing(true);
        return d;
    }
}
