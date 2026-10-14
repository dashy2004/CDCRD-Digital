using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
namespace Arnes {
static class Rpc { public const int ErrParams = -32602; }
class BridgeException : Exception { public int Code; public BridgeException(int c, string m) : base(m) { Code = c; } }
public class Alineamiento {
    public double StartingStation = 100.0;
    public void PointLocation(double station, double offset, ref double easting, ref double northing) { easting = 1000 + station; northing = 2000 + offset; }
    public void PointLocation(double station, double offset, double tol, ref double easting, ref double northing, ref double Bearing) { easting = 1; northing = 2; Bearing = 3; }
    public void StationOffsetAcceptOutOfRange(double e, double n, ref double station, ref double offset, ref bool outofrange) { station = e - 1000; offset = n - 2000; outofrange = station < 0; }
    public double ElevationAt(double station) { return 400 + station * 0.001; }
    public string Nombre(string a, int b) { return a + b; }
}
static partial class H {
    // <extracto de Handlers.cs: lo inserta correr.py>
    static int fallos = 0;
    static void Check(bool ok, string msg) { Console.WriteLine((ok ? "OK   " : "FAIL ") + msg); if (!ok) fallos++; }
    static void Main() {
        var a = new Alineamiento();
        // 1 ref con nulls de entrada
        var r = (Dictionary<string, object>)Invocar(a, "PointLocation", new List<object> { 150.0, 2.5, null, null });
        var s = (Dictionary<string, object>)r["salidas"];
        Check(r["retorno"] == null && (double)s["easting"] == 1150.0 && (double)s["northing"] == 2002.5, "PointLocation ref con null: " + s["easting"] + "," + s["northing"]);
        // 2 ref con valores de entrada (se ignoran)
        r = (Dictionary<string, object>)Invocar(a, "pointlocation", new List<object> { 10.0, 0.0, 5.0, 5.0 });
        s = (Dictionary<string, object>)r["salidas"];
        Check((double)s["easting"] == 1010.0 && s.Count == 2, "PointLocation case-insensitive, 2 salidas");
        // 3 sobrecarga de 6
        r = (Dictionary<string, object>)Invocar(a, "PointLocation", new List<object> { 1.0, 0.0, 0.01, null, null, null });
        s = (Dictionary<string, object>)r["salidas"];
        Check(s.Count == 3 && (double)s["Bearing"] == 3.0, "sobrecarga 6 params, 3 salidas");
        // 4 ref bool
        r = (Dictionary<string, object>)Invocar(a, "StationOffsetAcceptOutOfRange", new List<object> { 900.0, 2000.0, null, null, null });
        s = (Dictionary<string, object>)r["salidas"];
        Check((bool)s["outofrange"] == true && (double)s["station"] == -100.0, "ref bool y double");
        // 5 sin ref: retorno plano
        var e = Invocar(a, "ElevationAt", new List<object> { 200.0 });
        Check(e is double d && Math.Abs(d - 400.2) < 1e-12, "sin ref devuelve valor plano " + e);
        // 6 sin ref con coercion string/int
        Check((string)Invocar(a, "Nombre", new List<object> { "x", 3.0 }) == "x3", "coercion string/int");
        // 7 conteo de args incorrecto
        try { Invocar(a, "ElevationAt", new List<object>()); Check(false, "debia fallar"); }
        catch (BridgeException ex) { Check(ex.Code == Rpc.ErrParams, "args incorrectos -> ErrParams"); }
        // 8 metodo inexistente
        try { Invocar(a, "NoExiste", new List<object> { 1.0 }); Check(false, "debia fallar"); }
        catch (BridgeException) { Check(true, "metodo inexistente -> BridgeException"); }
        Console.WriteLine(fallos == 0 ? "TODOS OK" : fallos + " FALLOS");
        Environment.Exit(fallos);
    }
}}
