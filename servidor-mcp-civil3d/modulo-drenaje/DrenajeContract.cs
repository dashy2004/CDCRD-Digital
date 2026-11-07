using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;

namespace Cdcrd.Drenaje;

// One structure of the network to create. Kind: "imbornal" (grate inlet), "pozo" (manhole), "salida" (outlet).
// Rim is the finished-grade elevation at the structure (the gutter flowline for inlets).
internal sealed record StructureSpec(string Id, string Kind, string Family, string Size, double[] Xyz, double Rim, double SumpElevation, double Rotation);

// One pipe between two structures; inverts are the inside-bottom elevations at each end.
internal sealed record PipeSpec(string Id, string From, string To, string Family, double Diameter, double StartInvert, double EndInvert);

internal sealed record CreateOptions(string Name, string Layer, string PartsList, double MinSlope, double MinCover, double Tolerance, bool AddSizes,
    StructureSpec[] Structures, PipeSpec[] Pipes);

internal static class DrenajeContract
{
    internal static readonly string[] Kinds = { "imbornal", "pozo", "salida" };
    internal const int MaxParts = 200;

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
        else if (v.TryGetValue<long>(out var l)) r = l;
        else throw new ArgumentException("Numero requerido: " + key);
        if (!double.IsFinite(r)) throw new ArgumentException("Numero no finito: " + key);
        return r;
    }

    internal static double Range(JsonObject p, string key, double fallback, double lo, double hi)
    {
        double v = p[key] == null ? fallback : Number(p[key], key);
        if (v < lo || v > hi) throw new ArgumentException(key + " debe estar entre " + lo + " y " + hi);
        return v;
    }

    internal static double[] Xyz(JsonNode node, string key)
    {
        if (node is not JsonArray a || a.Count != 3) throw new ArgumentException(key + " requiere XYZ");
        var r = a.Select(n => Number(n, key)).ToArray();
        if (r.Any(v => Math.Abs(v) > 1e8)) throw new ArgumentException(key + " fuera de rango");
        return r;
    }

    internal static CreateOptions ParseCreate(JsonObject p)
    {
        if (p["estructuras"] is not JsonArray sa || sa.Count < 1 || sa.Count > MaxParts) throw new ArgumentException("estructuras: lista de 1.." + MaxParts);
        if (p["tuberias"] is not JsonArray pa || pa.Count < 1 || pa.Count > MaxParts) throw new ArgumentException("tuberias: lista de 1.." + MaxParts);
        var ids = new HashSet<string>(StringComparer.Ordinal);
        var structures = sa.Select(n =>
        {
            var o = n as JsonObject ?? throw new ArgumentException("Cada estructura es un objeto");
            string id = Text(o, "id", true, 60), kind = Text(o, "tipo", true, 20);
            if (!ids.Add(id)) throw new ArgumentException("Estructura duplicada: " + id);
            if (!Kinds.Contains(kind)) throw new ArgumentException("tipo de estructura debe ser imbornal, pozo o salida: " + id);
            var xyz = Xyz(o["xyz"], "xyz de " + id);
            double rim = o["rasante"] == null ? xyz[2] : Number(o["rasante"], "rasante de " + id);
            double sump = Number(o["cota_fondo"], "cota_fondo de " + id);
            if (sump >= rim) throw new ArgumentException("cota_fondo debe quedar bajo la rasante: " + id);
            if (rim - sump > 30) throw new ArgumentException("Estructura de mas de 30 m de profundidad: " + id);
            return new StructureSpec(id, kind, Text(o, "familia"), Text(o, "tamanio", false), xyz, rim, sump, Range(o, "rotacion", 0, -2 * Math.PI, 2 * Math.PI));
        }).ToArray();
        if (structures.Count(s => s.Kind == "salida") != 1) throw new ArgumentException("Se requiere exactamente una estructura de salida");
        var pipeIds = new HashSet<string>(StringComparer.Ordinal);
        var pipes = pa.Select(n =>
        {
            var o = n as JsonObject ?? throw new ArgumentException("Cada tuberia es un objeto");
            string id = Text(o, "id", true, 60), from = Text(o, "desde", true, 60), to = Text(o, "hasta", true, 60);
            if (!pipeIds.Add(id)) throw new ArgumentException("Tuberia duplicada: " + id);
            if (!ids.Contains(from) || !ids.Contains(to) || from == to) throw new ArgumentException("Tuberia " + id + " debe unir dos estructuras distintas de la lista");
            double d = Number(o["diametro_m"], "diametro_m de " + id);
            if (d < .1 || d > 3) throw new ArgumentException("diametro_m fuera de 0.1..3 m: " + id);
            double a = Number(o["cota_inicio"], "cota_inicio de " + id), b = Number(o["cota_fin"], "cota_fin de " + id);
            if (b > a) throw new ArgumentException("La tuberia " + id + " no desciende hacia aguas abajo");
            return new PipeSpec(id, from, to, Text(o, "familia"), d, a, b);
        }).ToArray();
        // A tree: every structure but the outlet has exactly one outgoing pipe and reaches the outlet.
        string outlet = structures.Single(s => s.Kind == "salida").Id;
        var downstream = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var x in pipes)
        {
            if (downstream.ContainsKey(x.From)) throw new ArgumentException("Mas de una tuberia sale de " + x.From);
            downstream[x.From] = x.To;
        }
        if (downstream.ContainsKey(outlet)) throw new ArgumentException("La salida no puede tener tuberia saliente");
        foreach (var s in structures)
        {
            if (s.Id == outlet) continue;
            var seen = new HashSet<string>(StringComparer.Ordinal); string cur = s.Id;
            while (cur != outlet)
            {
                if (!downstream.TryGetValue(cur, out var next) || !seen.Add(cur)) throw new ArgumentException("La estructura " + s.Id + " no drena a la salida");
                cur = next;
            }
        }
        return new CreateOptions(Text(p, "nombre"), Text(p, "capa", false) ?? "CDCRD-DRENAJE", Text(p, "lista_partes", false),
            Range(p, "pendiente_min", .005, .0005, .2), Range(p, "profundidad_min_m", 1.0, 0, 10), Range(p, "tolerancia_m", .005, 1e-6, .1),
            p["agregar_tamanios"]?.GetValue<bool>() ?? true, structures, pipes);
    }
}
