using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;

namespace Cdcrd.Presion;

// One node of the network. Kind "libre" places no part (open pipe ends: a tap on an existing main, a tank inlet,
// a building service entry); every other kind places a fitting or an appurtenance at Xyz (pipe centreline point).
internal sealed record NodeSpec(string Id, string Kind, double[] Xyz, string Family, double? Nominal, double? Nominal2, double? Angle, string Description);

// One straight pipe between two nodes; the centreline runs from the first node's Xyz to the second's.
internal sealed record PipeSpec(string Id, string From, string To, string Family, double Nominal);

internal sealed record CreateOptions(string Name, string Layer, string PartsList, string Surface, double Tolerance, double ConnectionTolerance,
    bool Connect, bool Rotate, NodeSpec[] Nodes, PipeSpec[] Pipes);

internal static class PresionContract
{
    // kind -> (domain, part type, expected pipe count; 0 = any)
    internal static readonly Dictionary<string, (string Domain, string PartType, int Pipes)> Kinds = new(StringComparer.Ordinal)
    {
        ["libre"] = ("", "", 0), ["codo"] = ("Fitting", "Elbow", 2), ["te"] = ("Fitting", "Tee", 3), ["cruz"] = ("Fitting", "Cross", 4),
        ["tapon"] = ("Fitting", "Cap", 1), ["reduccion"] = ("Fitting", "Reducer", 2), ["union"] = ("Fitting", "Coupling", 2),
        ["valvula"] = ("Appurtenance", "Valve", 2), ["hidrante"] = ("Appurtenance", "Hydrant", 1), ["bomba"] = ("Appurtenance", "Pump", 2)
    };
    internal const int MaxParts = 300;

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

    internal static double? Optional(JsonObject p, string key, double lo, double hi)
    {
        if (p[key] == null) return null;
        double v = Number(p[key], key);
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
        if (p["nodos"] is not JsonArray na || na.Count < 2 || na.Count > MaxParts) throw new ArgumentException("nodos: lista de 2.." + MaxParts);
        if (p["tuberias"] is not JsonArray pa || pa.Count < 1 || pa.Count > MaxParts) throw new ArgumentException("tuberias: lista de 1.." + MaxParts);
        var ids = new HashSet<string>(StringComparer.Ordinal);
        var nodes = na.Select(n =>
        {
            var o = n as JsonObject ?? throw new ArgumentException("Cada nodo es un objeto");
            string id = Text(o, "id", true, 60), kind = Text(o, "tipo", true, 20);
            if (!ids.Add(id)) throw new ArgumentException("Nodo duplicado: " + id);
            if (!Kinds.ContainsKey(kind)) throw new ArgumentException("tipo de nodo desconocido en " + id + " (admite " + string.Join(", ", Kinds.Keys) + ")");
            var xyz = Xyz(o["xyz"], "xyz de " + id);
            string family = Text(o, "familia", false);
            if (kind != "libre" && family == null) throw new ArgumentException("familia requerida en el nodo " + id);
            return new NodeSpec(id, kind, xyz, family, Optional(o, "diametro_nominal", 0.01, 10000), Optional(o, "diametro_nominal_2", 0.01, 10000), Optional(o, "angulo", 0, 180), Text(o, "descripcion", false));
        }).ToArray();
        var pipeIds = new HashSet<string>(StringComparer.Ordinal);
        var pipes = pa.Select(n =>
        {
            var o = n as JsonObject ?? throw new ArgumentException("Cada tuberia es un objeto");
            string id = Text(o, "id", true, 60), from = Text(o, "desde", true, 60), to = Text(o, "hasta", true, 60);
            if (!pipeIds.Add(id)) throw new ArgumentException("Tuberia duplicada: " + id);
            if (!ids.Contains(from) || !ids.Contains(to) || from == to) throw new ArgumentException("Tuberia " + id + " debe unir dos nodos distintos de la lista");
            return new PipeSpec(id, from, to, Text(o, "familia"), Range(o, "diametro_nominal", double.NaN, 0.01, 10000));
        }).ToArray();
        var byNode = nodes.ToDictionary(x => x.Id, x => pipes.Count(t => t.From == x.Id || t.To == x.Id));
        foreach (var x in nodes)
        {
            int expected = Kinds[x.Kind].Pipes, actual = byNode[x.Id];
            if (actual == 0) throw new ArgumentException("El nodo " + x.Id + " no tiene tuberias");
            if (expected > 0 && actual != expected) throw new ArgumentException("El nodo " + x.Id + " (" + x.Kind + ") requiere " + expected + " tuberias y tiene " + actual);
        }
        foreach (var t in pipes)
        {
            var a = nodes.First(x => x.Id == t.From); var b = nodes.First(x => x.Id == t.To);
            if (Math.Sqrt(Math.Pow(a.Xyz[0] - b.Xyz[0], 2) + Math.Pow(a.Xyz[1] - b.Xyz[1], 2)) < 0.5) throw new ArgumentException("Tuberia " + t.Id + " mas corta que 0,5 m en planta");
        }
        return new CreateOptions(Text(p, "nombre"), Text(p, "capa", false) ?? "CDCRD-PRESION", Text(p, "lista_partes", false), Text(p, "superficie", false),
            Range(p, "tolerancia_m", .005, 1e-6, .1), Range(p, "tolerancia_conexion_m", 1.0, .001, 5), p["conectar"]?.GetValue<bool>() ?? true,
            p["rotar"]?.GetValue<bool>() ?? true, nodes, pipes);
    }
}
