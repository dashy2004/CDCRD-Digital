using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;

namespace Cdcrd.Corredores;

internal sealed record RegionSpec(string Name, string Assembly, string Target, double Start, double End, double Frequency, double[] Extra);
internal sealed record BaselineSpec(string Name, string Alignment, string Profile, RegionSpec[] Regions);

internal static class MultiContract
{
    internal static string Text(JsonObject p, string key)
    {
        var value = p[key]?.GetValue<string>();
        if (string.IsNullOrWhiteSpace(value) || value.Length > 200 || value.Any(char.IsControl))
            throw new ArgumentException("Texto requerido de hasta 200 caracteres: " + key);
        return value;
    }
    internal static double Number(JsonNode node)
    {
        double result;
        if (node is not JsonValue v) throw new ArgumentException("Numero requerido");
        if (v.TryGetValue<double>(out var d)) result = d;
        else if (v.TryGetValue<int>(out var i)) result = i;
        else if (v.TryGetValue<long>(out var l)) result = l;
        else throw new ArgumentException("Numero requerido");
        if (!double.IsFinite(result)) throw new ArgumentException("Numero finito requerido");
        return result;
    }
    internal static BaselineSpec[] Parse(JsonArray array)
    {
        if (array == null || array.Count < 1 || array.Count > 20) throw new ArgumentException("Se requieren 1..20 baselines");
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var regionNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var result = new List<BaselineSpec>();
        double budget = 0;
        foreach (var node in array)
        {
            var b = node as JsonObject ?? throw new ArgumentException("Baseline debe ser objeto");
            string name = Text(b,"nombre");
            if (!names.Add(name)) throw new ArgumentException("Nombres de baseline duplicados");
            if (b["regiones"] is not JsonArray regions || regions.Count < 1 || regions.Count > 100)
                throw new ArgumentException("Se requieren 1..100 regiones por baseline");
            var parsed = new List<RegionSpec>();
            foreach (var item in regions)
            {
                var r = item as JsonObject ?? throw new ArgumentException("Region debe ser objeto");
                string rn = Text(r,"nombre");
                if (!regionNames.Add(rn) || regionNames.Count > 100) throw new ArgumentException("Hasta 100 regiones con nombres unicos en el corredor");
                double start = Number(r["inicio"]), end = Number(r["fin"]), frequency = Number(r["frecuencia"]);
                if (Math.Abs(start)>1e7 || Math.Abs(end)>1e7 || end-start<.01 || frequency<.1 || frequency>1000 || (end-start)/frequency>1000)
                    throw new ArgumentException("Intervalo/frecuencia fuera de rango o mas de 1000 intervalos por region");
                if (parsed.Count>0 && start<parsed.Last().End) throw new ArgumentException("Regiones deben venir ordenadas y sin solapamiento");
                if (r["estaciones_extra"] is not JsonArray extra || extra.Count>500) throw new ArgumentException("Lista de hasta 500 estaciones_extra requerida");
                double[] stations = extra.Select(Number).ToArray();
                if (stations.Any(s=>s<start || s>end) || stations.Skip(1).Where((s,i)=>s-stations[i]<=1e-6).Any())
                    throw new ArgumentException("Estaciones extra ordenadas, unicas y dentro de su region");
                budget += Math.Ceiling((end-start)/frequency)+stations.Length+2;
                if (budget>20000) throw new ArgumentException("Presupuesto superior a 20000 estaciones");
                parsed.Add(new RegionSpec(rn,Text(r,"ensamblaje"),r["superficie_objetivo"]==null?null:Text(r,"superficie_objetivo"),start,end,frequency,stations));
            }
            result.Add(new BaselineSpec(name,Text(b,"alineamiento"),Text(b,"perfil"),parsed.ToArray()));
        }
        return result.ToArray();
    }
}
