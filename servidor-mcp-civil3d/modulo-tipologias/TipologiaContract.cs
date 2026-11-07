using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;

namespace Cdcrd.Tipologias;

// One stretch of the single region: [From, To) with its curb kind.
// Kinds: "LR" curb both sides, "L"/"R" one side, "-" none (junction), "talud" full palette section with daylight.
internal sealed record Segment(double From, double To, string Kind);

internal sealed record ClassifyOptions(double Probe, double UnionMin, double FreeMin, string EdgeCode, string[] Paved, string[] Excluded);

internal sealed record ApplyOptions(Segment[] Segments, string Library, string LaneAssembly, string CurbAssembly, string CurbSubassembly,
    string SlopeAssembly, string Terrain, double[] Origin, double Spacing, string Layer, string EdgeCode, double Tolerance);

internal static class TipologiaContract
{
    internal static readonly string[] Kinds = { "LR", "L", "R", "-", "talud" };

    internal static string Text(JsonObject p, string key, bool required = true, int max = 200)
    {
        var s = p[key]?.GetValue<string>();
        if (s == null && !required) return null;
        if (string.IsNullOrWhiteSpace(s) || s.Length > max || s.Any(char.IsControl))
            throw new ArgumentException("Texto requerido de hasta " + max + " caracteres: " + key);
        return s;
    }

    internal static double Number(JsonNode node, string key)
    {
        if (node is not JsonValue v) throw new ArgumentException("Numero requerido: " + key);
        double r;
        if (v.TryGetValue<double>(out var d)) r = d;
        else if (v.TryGetValue<int>(out var i)) r = i;
        else if (v.TryGetValue<long>(out var l)) r = l;
        else throw new ArgumentException("Numero requerido: " + key);
        if (!double.IsFinite(r)) throw new ArgumentException("Numero finito requerido: " + key);
        return r;
    }

    internal static double Range(JsonObject p, string key, double fallback, double min, double max)
    {
        double v = p[key] == null ? fallback : Number(p[key], key);
        if (v < min || v > max) throw new ArgumentException(key + " fuera de " + min + ".." + max);
        return v;
    }

    internal static string[] Texts(JsonObject p, string key, int max = 200)
    {
        if (p[key] == null) return Array.Empty<string>();
        if (p[key] is not JsonArray a || a.Count > max) throw new ArgumentException("Lista de hasta " + max + " textos: " + key);
        var rows = a.Select(n => n?.GetValue<string>()).ToArray();
        if (rows.Any(s => string.IsNullOrWhiteSpace(s) || s.Length > 200 || s.Any(char.IsControl))) throw new ArgumentException("Textos invalidos en " + key);
        return rows;
    }

    internal static ClassifyOptions ParseClassify(JsonObject p) => new(
        Range(p, "sonda_m", 1.0, .05, 10), Range(p, "union_min_m", 2.0, 0, 100), Range(p, "libre_min_m", 5.0, 0, 100),
        Text(p, "codigo_borde", false, 60), Texts(p, "superficies_pavimento"), Texts(p, "superficies_excluidas"));

    internal static Segment[] ParseSegments(JsonNode node)
    {
        if (node is not JsonArray a || a.Count < 1 || a.Count > 100) throw new ArgumentException("segmentos: lista de 1..100 tramos [inicio, fin, tipo]");
        var rows = a.Select(item =>
        {
            if (item is not JsonArray t || t.Count != 3) throw new ArgumentException("Cada tramo es [inicio, fin, tipo]");
            string kind = t[2]?.GetValue<string>();
            if (!Kinds.Contains(kind)) throw new ArgumentException("tipo de tramo debe ser LR, L, R, - o talud");
            return new Segment(Number(t[0], "inicio"), Number(t[1], "fin"), kind);
        }).ToArray();
        for (int i = 0; i < rows.Length; i++)
        {
            if (rows[i].To - rows[i].From < .01 || Math.Abs(rows[i].From) > 1e7 || Math.Abs(rows[i].To) > 1e7) throw new ArgumentException("Tramo " + (i + 1) + " vacio o fuera de rango");
            if (i > 0 && Math.Abs(rows[i].From - rows[i - 1].To) > 1e-6) throw new ArgumentException("Tramos discontinuos entre " + i + " y " + (i + 1));
        }
        return rows;
    }

    internal static ApplyOptions ParseApply(JsonObject p)
    {
        var segments = ParseSegments(p["segmentos"]);
        string library = Text(p, "biblioteca", false, 400);
        if (library != null && (!Path.IsPathFullyQualified(library) || library.Any(c => c == '"' || c == '<' || c == '>' || c == '|')))
            throw new ArgumentException("biblioteca debe ser una carpeta absoluta");
        double[] origin = null;
        if (p["origen"] != null)
        {
            if (p["origen"] is not JsonArray o || o.Count != 3) throw new ArgumentException("origen requiere XYZ");
            origin = o.Select(n => Number(n, "origen")).ToArray();
            if (origin.Any(v => Math.Abs(v) > 1e8)) throw new ArgumentException("origen fuera de rango");
        }
        return new ApplyOptions(segments, library,
            Text(p, "ensamblaje_carriles", false) ?? "Primary Road - Through Intersection",
            Text(p, "ensamblaje_bordillo", false) ?? "Primary Road Full Section",
            Text(p, "subensamblaje_bordillo", false) ?? "UrbanCurbGutterGeneral",
            Text(p, "ensamblaje_talud", false) ?? "Primary Road Full Section",
            Text(p, "superficie_terreno", false), origin, Range(p, "separacion_m", 30, 1, 1000),
            Text(p, "capa", false), Text(p, "codigo_borde", false, 60), Range(p, "tolerancia_m", .005, 1e-6, .1));
    }

    internal static string DefaultLibrary(int majorVersion)
    {
        // AutoCAD R26.0 ships Civil 3D 2027: product year = major + 2001.
        string folder = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
            "Autodesk", "C3D " + (majorVersion + 2001), "enu", "Assemblies", "Metric");
        if (!Directory.Exists(folder)) throw new DirectoryNotFoundException("Biblioteca metrica no encontrada; indique biblioteca: " + folder);
        return folder;
    }
}
