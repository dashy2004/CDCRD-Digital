using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Cdcrd.Cubicacion;

// Thickness parameters to write on every lane, in metres, plus the optional lane/region selection.
internal sealed record ThicknessOptions(Dictionary<string, double> Thickness, string[] Subassemblies, string[] Regions, double Tolerance);
internal sealed record DatumOptions(string Name, string Code);
internal sealed record VolumeOptions(string Terrain, string Datum, string[] Codes, string VolumeName, double CutFactor, double FillFactor);

internal static class CubicacionContract
{
    internal static readonly string[] DefaultCodes = { "Pave1", "Pave2", "Base", "SubBase" };
    // Thickness parameter -> shape code of the stock lane subassemblies, used to verify the written depth geometrically.
    private static readonly Dictionary<string, string> ShapeByKey = new(StringComparer.Ordinal)
    { ["Pave1Depth"] = "Pave1", ["Pave2Depth"] = "Pave2", ["BaseDepth"] = "Base", ["SubBaseDepth"] = "SubBase" };

    internal static string ShapeCode(string key) => ShapeByKey.TryGetValue(key, out var code) ? code : null;

    internal static string Text(JsonObject p, string key, bool required = true, int max = 200)
    {
        var s = p[key]?.GetValue<string>();
        if ((s == null || s.Length == 0) && !required) return null;
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
        if (rows.Distinct(StringComparer.OrdinalIgnoreCase).Count() != rows.Length) throw new ArgumentException("Textos repetidos en " + key);
        return rows;
    }

    internal static Dictionary<string, double> ParseThickness(JsonNode node)
    {
        if (node is not JsonObject o || o.Count < 1 || o.Count > 12) throw new ArgumentException("espesores: objeto {parametro: metros} con 1..12 claves");
        var result = new Dictionary<string, double>(StringComparer.Ordinal);
        foreach (var pair in o)
        {
            if (!Regex.IsMatch(pair.Key, "^[A-Za-z][A-Za-z0-9_]{0,39}$")) throw new ArgumentException("Clave de parametro invalida: " + pair.Key);
            double v = Number(pair.Value, pair.Key);
            if (v < .001 || v > 5) throw new ArgumentException(pair.Key + " fuera de 0.001..5 m");
            result[pair.Key] = v;
        }
        return result;
    }

    internal static ThicknessOptions ParseThicknessOptions(JsonObject p) => new(
        ParseThickness(p["espesores"]), Texts(p, "subensamblajes"), Texts(p, "regiones"), Range(p, "tolerancia_m", .001, 1e-6, .1));

    internal static DatumOptions ParseDatum(JsonObject p) => new(Text(p, "nombre", false), Text(p, "codigo", false, 60) ?? "Datum");

    internal static VolumeOptions ParseVolume(JsonObject p)
    {
        var codes = Texts(p, "codigos", 20);
        if (codes.Length == 0) codes = DefaultCodes;
        var o = new VolumeOptions(Text(p, "terreno"), Text(p, "datum", false), codes, Text(p, "nombre_volumen", false),
            Range(p, "factor_corte", 1, .1, 10), Range(p, "factor_relleno", 1, .1, 10));
        if (o.Datum != null && string.Equals(o.Datum, o.Terrain, StringComparison.OrdinalIgnoreCase)) throw new ArgumentException("terreno y datum deben ser superficies distintas");
        return o;
    }
}
