using Cdcrd.Civil3dBridge;
using System.Text.Json.Nodes;
static class CunetaBermaChecks
{
    internal static void Run(Action<bool,string> check)
    {
        var p=JsonNode.Parse("{\"ancho_berma_izq\":1.5,\"ancho_berma_der\":2,\"pendiente_berma_izq\":-0.04,\"pendiente_berma_der\":-0.03,\"profundidad_cuneta\":0.6,\"ancho_fondo_cuneta\":0.5,\"talud_cuneta_interior_hv\":2,\"talud_cuneta_exterior_hv\":1.5}").AsObject();
        var c=CunetaBermaContract.Parse(p);var l=c.Links(true);var r=c.Links(false);
        check(l[0].Width==1.5 && r[0].Width==2 && l[0].Slope==-.04 && r[0].Slope==-.03,"bermas asimetricas conservadas");
        check(Math.Abs(l[1].Width-1.2)<1e-12 && l[1].Slope==-.5 && l[2].Width==.5 && l[2].Slope==0 && Math.Abs(l[3].Width-.9)<1e-12,"cuneta convierte H/V a ancho y pendiente");
        check(Math.Abs(l.Skip(1).Sum(x=>x.Width*x.Slope))<1e-12,"cuneta recupera cota del borde de berma");
        foreach(var key in p.Select(kv=>kv.Key).ToArray())
        {
            var missing=(JsonObject)p.DeepClone();missing.Remove(key);
            try{CunetaBermaContract.Parse(missing);throw new Exception("accepted");}
            catch(ArgumentException){check(true,"rechaza campo ausente: "+key);}
            foreach(double bad in new[]{-100d,100d,double.NaN,double.PositiveInfinity})
            {
                var invalid=(JsonObject)p.DeepClone();invalid[key]=JsonValue.Create(bad);
                try{CunetaBermaContract.Parse(invalid);throw new Exception("accepted");}
                catch(ArgumentException){check(true,"rechaza rango/no finito: "+key);}
            }
        }
    }
}
