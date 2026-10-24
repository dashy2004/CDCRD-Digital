using System;
using System.Text.Json.Nodes;
using Cdcrd.Corredores;

internal static class MultiChecks
{
    internal static void Run(Action<bool,string> check)
    {
        JsonArray Input() => JsonNode.Parse("""[{"nombre":"A","alineamiento":"A1","perfil":"P1","regiones":[{"nombre":"R1","ensamblaje":"S1","inicio":100,"fin":200,"frecuencia":10,"estaciones_extra":[100,150,200]},{"nombre":"R2","ensamblaje":"S2","inicio":200,"fin":300,"frecuencia":5,"estaciones_extra":[200,250,300]}]}]""") as JsonArray;
        var value=MultiContract.Parse(Input());
        check(value.Length==1 && value[0].Regions.Length==2 && value[0].Regions[1].Assembly=="S2","regiones contiguas con ensamblajes distintos");
        var gap=Input();gap[0]["regiones"][1]["inicio"]=210;gap[0]["regiones"][1]["estaciones_extra"]=new JsonArray(210,250,300);
        check(MultiContract.Parse(gap)[0].Regions[1].Start==210,"huecos explicitos conservados");
        var two=Input();var b=two[0].DeepClone();b["nombre"]="B";b["alineamiento"]="A2";b["perfil"]="P2";b["regiones"][0]["nombre"]="R3";b["regiones"][1]["nombre"]="R4";two.Add(b);
        check(MultiContract.Parse(two).Length==2,"dos baselines conservadas");
        void Bad(Action<JsonArray> edit,string label) { var p=Input();edit(p);bool rejected=false;try{MultiContract.Parse(p);}catch(ArgumentException){rejected=true;}check(rejected,label); }
        Bad(a=>a[0]["regiones"][1]["inicio"]=199,"rechaza solapamiento sin recortar");
        Bad(a=>a[0]["regiones"][1]["nombre"]="r1","rechaza nombre region duplicado");
        Bad(a=>a.Add(a[0].DeepClone()),"rechaza baseline duplicada");
        Bad(a=>a[0]["regiones"][0]["frecuencia"]=0,"rechaza frecuencia cero");
        Bad(a=>a[0]["regiones"][0]["fin"]=100,"rechaza region vacia");
        Bad(a=>a[0]["regiones"][0]["estaciones_extra"]=new JsonArray(150,100),"rechaza estaciones desordenadas");
        Bad(a=>a[0]["regiones"][0]["estaciones_extra"]=new JsonArray(99),"rechaza estaciones fuera de region");
        Bad(a=>a[0]["regiones"][0]["estaciones_extra"]=new JsonArray(150,150),"rechaza estaciones duplicadas");
        Bad(a=>a[0]["regiones"][0]["inicio"]=-10000,"limita intervalos antes de acceder a CAD");
        Bad(a=>a[0]["regiones"]=new JsonArray(),"rechaza baseline vacia");
        Bad(a=>a[0]["perfil"]=" ","requiere perfil explicito");
    }
}
