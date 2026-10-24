using Cdcrd.Espirales;
using System.Text.Json.Nodes;
internal static class SpiralChecks
{
    internal static void Run(Action<bool,string> check)
    {
        JsonObject Input() => JsonNode.Parse("{\"inicio\":[0,0],\"pi\":[130,0],\"fin\":[195,112.58330249197702],\"radio\":50,\"longitud_entrada\":25,\"longitud_salida\":35,\"estacion_inicial\":100}")!.AsObject();
        void Reject(JsonObject p,string name)
        {try {SpiralContract.Parse(p);} catch(ArgumentException) {check(true,name);return;} throw new Exception(name+" accepted");}
        var c=SpiralContract.Parse(Input());
        check(Math.Abs(c.Length-253.8352233090478)<1e-8 && Math.Abs(c.TrimIn-42.21509713344724)<1e-8 && Math.Abs(c.TrimOut-46.309557117158285)<1e-8,"integracion coincide con serie Fresnel independiente");
        var end=c.At(100+c.Length);
        check(Math.Abs(end.X-195)<1e-8 && Math.Abs(end.Y-112.58330249197702)<1e-8,"espiral termina en punto solicitado");
        check(Math.Abs(c.ArcLength-(50*Math.PI/3-30))<1e-9,"arco conserva deflexion menos espirales");
        check(Math.Abs(c.At(100+c.TangentIn).Curvature)<1e-12,"curvatura cero al entrar");
        check(Math.Abs(c.At(100+c.TangentIn+25).Curvature-.02)<1e-12,"curvatura continua espiral-arco");
        check(Math.Abs(c.At(100+c.Length-c.TangentOut).Curvature)<1e-12,"curvatura cero al salir");
        double mid=100+c.TangentIn+12.5;
        var axis=c.At(mid);var offset=c.At(mid,3.5);
        check(Math.Abs(Math.Sqrt(Math.Pow(axis.X-offset.X,2)+Math.Pow(axis.Y-offset.Y,2))-3.5)<1e-10,"offset normal de ancho exacto");
        var mirror=Input(); mirror["fin"]![1]=-112.58330249197702;
        var m=SpiralContract.Parse(mirror).At(mid);
        check(Math.Abs(m.X-axis.X)<1e-10 && Math.Abs(m.Y+axis.Y)<1e-10 && Math.Abs(m.Curvature+axis.Curvature)<1e-12,"giro derecho espejo exacto");
        foreach(var field in new[]{"radio","longitud_entrada","longitud_salida"})
        {var p=Input();p[field]=0;Reject(p,"rechaza cero "+field);}
        var straight=Input();straight["fin"]=new JsonArray(260,0);Reject(straight,"rechaza tangentes colineales");
        var fit=Input();fit["radio"]=1000;Reject(fit,"rechaza curva que no cabe");
        var arc=Input();arc["longitud_entrada"]=100;arc["longitud_salida"]=100;Reject(arc,"rechaza espirales sin arco");
        var close=Input();close["pi"]=new JsonArray(.01,0);Reject(close,"rechaza tangente corta");
        try {c.At(99);throw new Exception("Extrapolation accepted");}catch(ArgumentOutOfRangeException){check(true,"sin extrapolacion");}
    }
}
