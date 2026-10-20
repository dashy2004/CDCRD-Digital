using Cdcrd.Civil3dBridge;
static class PlatformChecks
{
    internal static void Run(Action<bool,string> check)
    {
        var outer=new[]{(0d,0d),(48d,0d),(48d,32d),(0d,32d)};
        var inner=new[]{(4d,4d),(44d,4d),(44d,28d),(4d,28d)};
        check(PlatformContract.Convex(outer)==1536,"plataforma area exterior");
        PlatformContract.Inside(outer,inner);
        PlatformContract.Inside(outer.Reverse().ToArray(),inner.Reverse().ToArray());
        check(true,"anillos contenidos en ambos sentidos");
        check(PlatformContract.Elevations(new[]{102d},4).SequenceEqual(new[]{102d,102d,102d,102d}),"cota constante expandida");
        foreach(var action in new Action[]{
            ()=>PlatformContract.Elevations(new[]{100d,101d},4),
            ()=>PlatformContract.Elevations(new[]{double.NaN},4),
            ()=>PlatformContract.Convex(new[]{(0d,0d),(4d,0d),(2d,1d),(4d,4d),(0d,4d)}),
            ()=>PlatformContract.Convex(new[]{(0d,0d),(2d,0d),(4d,0d),(4d,4d),(0d,4d)}),
            ()=>PlatformContract.Inside(outer,outer),
            ()=>PlatformContract.Inside(inner,outer)})
        {
            try{action();throw new Exception("Contrato invalido aceptado");}
            catch(ArgumentException){check(true,"rechaza cotas o anillos invalidos");}
        }
    }
}
