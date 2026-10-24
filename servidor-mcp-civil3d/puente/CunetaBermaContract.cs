using System;
using System.Text.Json.Nodes;

namespace Cdcrd.Civil3dBridge
{
    // Geometric section only: unpaved berm and open trapezoidal ditch on each side.
    internal sealed class CunetaBermaContract
    {
        internal double LeftWidth, RightWidth, LeftSlope, RightSlope;
        internal double Depth, BottomWidth, InnerHV, OuterHV;

        internal static CunetaBermaContract Parse(JsonObject p)
        {
            double R(string key, double min, double max) => CorridorContract.Range(
                p[key]?.GetValue<double>() ?? throw new ArgumentException("Falta " + key), min, max, key);
            return new CunetaBermaContract {
                LeftWidth=R("ancho_berma_izq", .05, 20), RightWidth=R("ancho_berma_der", .05, 20),
                LeftSlope=R("pendiente_berma_izq", -1, 1), RightSlope=R("pendiente_berma_der", -1, 1),
                Depth=R("profundidad_cuneta", .05, 5), BottomWidth=R("ancho_fondo_cuneta", .05, 10),
                InnerHV=R("talud_cuneta_interior_hv", .25, 10), OuterHV=R("talud_cuneta_exterior_hv", .25, 10)
            };
        }

        internal (string Role, double Width, double Slope, string PointCode)[] Links(bool left) => new[] {
            ("berma", left ? LeftWidth : RightWidth, left ? LeftSlope : RightSlope, "BermaExterior"),
            ("cuneta_interior", Depth*InnerHV, -1/InnerHV, "CunetaFondoInterior"),
            ("cuneta_fondo", BottomWidth, 0.0, "CunetaFondoExterior"),
            ("cuneta_exterior", Depth*OuterHV, 1/OuterHV, "CunetaBordeExterior")
        };
    }
}
