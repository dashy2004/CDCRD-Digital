using System;
using Cdcrd.Civil3dBridge;

static class VerticalCurveChecks
{
    public static void Run(Action<bool,string> check)
    {
        var p = new[]{(0d,100d),(100d,104d),(200d,100d),(300d,102d)};
        var curves = VerticalCurveContract.Validate(p, new[]{new VerticalCurveSpec(1,40),new VerticalCurveSpec(2,60)});
        check(Math.Abs(VerticalCurveContract.Elevation(p,curves,100)-103.6)<1e-10,"parabola convexa: ordenada independiente");
        check(Math.Abs(VerticalCurveContract.Elevation(p,curves,200)-100.45)<1e-10,"parabola concava: ordenada independiente");
        check(Math.Abs(VerticalCurveContract.Elevation(p,curves,80)-103.2)<1e-10,"inicio de curva continuo con tangente");
        check(Math.Abs(VerticalCurveContract.Elevation(p,curves,120)-103.2)<1e-10,"fin de curva continuo con tangente");
        check(Math.Abs(VerticalCurveContract.Elevation(p,curves,150)-102)<1e-10,"tangente entre curvas conservada");
        foreach(var bad in new[]{
            new[]{new VerticalCurveSpec(0,20)}, new[]{new VerticalCurveSpec(3,20)},
            new[]{new VerticalCurveSpec(1,0)},new[]{new VerticalCurveSpec(1,double.NaN)},
            new[]{new VerticalCurveSpec(1,200)},new[]{new VerticalCurveSpec(1,201)},
            new[]{new VerticalCurveSpec(1,120),new VerticalCurveSpec(2,120)},
            new[]{new VerticalCurveSpec(1,100),new VerticalCurveSpec(2,100)},
            new[]{new VerticalCurveSpec(1,20),new VerticalCurveSpec(1,40)}})
        {
            try {VerticalCurveContract.Validate(p,bad);throw new Exception("Curva invalida aceptada");}
            catch(ArgumentException){check(true,"curva invalida rechazada antes de escribir");}
        }
        try {VerticalCurveContract.Validate(new[]{(0d,0d),(50d,1d),(100d,2d)},new[]{new VerticalCurveSpec(1,20)});throw new Exception("pendiente constante aceptada");}
        catch(ArgumentException){check(true,"parabola degenerada rechazada");}
    }
}
