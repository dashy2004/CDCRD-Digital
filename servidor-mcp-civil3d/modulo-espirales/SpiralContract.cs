using System;
using System.Linq;
using System.Text.Json.Nodes;

namespace Cdcrd.Espirales;

// Independent numerical construction; no Autodesk types or unit conversion.
internal sealed class SpiralContract
{
    internal double[] Start, Pi, End;
    internal double Radius, InLength, OutLength, Station, Turn, Heading;
    internal double TrimIn, TrimOut, TangentIn, TangentOut, ArcLength;
    internal double Length => TangentIn + InLength + ArcLength + OutLength + TangentOut;
    internal double[] Breaks => new[] { 0.0, TangentIn, TangentIn + InLength,
        TangentIn + InLength + ArcLength, Length - TangentOut, Length };
    private static double Scalar(JsonNode node)
    {
        if (node is JsonValue value)
        {
            if (value.TryGetValue<double>(out var d)) return d;
            if (value.TryGetValue<int>(out var i)) return i;
            if (value.TryGetValue<long>(out var l)) return l;
            if (value.TryGetValue<decimal>(out var m)) return (double)m;
        }
        throw new ArgumentException("Valor numerico requerido.");
    }
    private static double Number(JsonObject p, string key)
    {
        double v = Scalar(p[key]);
        if (!double.IsFinite(v)) throw new ArgumentException("Numero finito requerido: " + key);
        return v;
    }
    private static double[] Point(JsonObject p, string key)
    {
        if (p[key] is not JsonArray a || a.Count != 2) throw new ArgumentException("Punto XY requerido: " + key);
        var v = a.Select(Scalar).ToArray();
        if (v.Any(x => !double.IsFinite(x) || Math.Abs(x) > 1e8)) throw new ArgumentException("Coordenada fuera de rango: " + key);
        return v;
    }
    internal static SpiralContract Parse(JsonObject p)
    {
        var c = new SpiralContract { Start = Point(p, "inicio"), Pi = Point(p, "pi"), End = Point(p, "fin"),
            Radius = Number(p, "radio"), InLength = Number(p, "longitud_entrada"),
            OutLength = Number(p, "longitud_salida"), Station = Number(p, "estacion_inicial") };
        if (c.Radius < 1 || c.Radius > 1e6 || c.InLength < .1 || c.InLength > 10000 ||
            c.OutLength < .1 || c.OutLength > 10000 || Math.Abs(c.Station) > 1e7)
            throw new ArgumentException("Radio 1..1000000 m, espirales 0.1..10000 m, estacion dentro de +/-10000000 m.");
        double ux = c.Pi[0] - c.Start[0], uy = c.Pi[1] - c.Start[1];
        double vx = c.End[0] - c.Pi[0], vy = c.End[1] - c.Pi[1];
        double a = Math.Sqrt(ux * ux + uy * uy), b = Math.Sqrt(vx * vx + vy * vy);
        if (a < 1 || b < 1) throw new ArgumentException("Tangentes iniciales menores de 1 m.");
        c.Turn = Math.Atan2(ux * vy - uy * vx, ux * vx + uy * vy);
        c.Heading = Math.Atan2(uy, ux);
        double delta = Math.Abs(c.Turn);
        if (delta < Math.PI / 180 || delta > 170 * Math.PI / 180)
            throw new ArgumentException("Deflexion requerida entre 1 y 170 grados.");
        c.ArcLength = c.Radius * delta - (c.InLength + c.OutLength) / 2;
        if (c.ArcLength < .1) throw new ArgumentException("Las espirales consumen la deflexion; arco circular minimo 0.1 m.");
        var displacement = c.CurvePoint(c.InLength + c.ArcLength + c.OutLength);
        c.TrimOut = displacement.Y / Math.Sin(delta);
        c.TrimIn = displacement.X - c.TrimOut * Math.Cos(delta);
        c.TangentIn = a - c.TrimIn; c.TangentOut = b - c.TrimOut;
        if (c.TrimIn <= 0 || c.TrimOut <= 0 || c.TangentIn < .01 || c.TangentOut < .01)
            throw new ArgumentException("La curva no cabe entre inicio, PI y fin; requiere tangentes residuales >= 0.01 m.");
        return c;
    }
    private static (double X, double Y) Integrate(double length, Func<double, double> angle)
    {
        const int n = 1024;
        double x = 0, y = 0, step = length / n;
        for (int i = 0; i <= n; i++)
        {
            double weight = i == 0 || i == n ? 1 : i % 2 == 0 ? 2 : 4;
            double theta = angle(step * i);
            x += weight * Math.Cos(theta); y += weight * Math.Sin(theta);
        }
        return (x * step / 3, y * step / 3);
    }
    // Positive turn in a local frame; mirror/rotate only at the final transform.
    private (double X, double Y, double Angle, double Curvature) CurvePoint(double s)
    {
        double first = Math.Min(s, InLength);
        var xy = Integrate(first, t => t * t / (2 * Radius * InLength));
        double angle = first * first / (2 * Radius * InLength), k = first / (Radius * InLength);
        if (s > InLength)
        {
            double arc = Math.Min(s - InLength, ArcLength), begin = InLength / (2 * Radius);
            angle = begin + arc / Radius; k = 1 / Radius;
            xy.X += Radius * (Math.Sin(angle) - Math.Sin(begin));
            xy.Y += Radius * (Math.Cos(begin) - Math.Cos(angle));
        }
        if (s > InLength + ArcLength)
        {
            double exit = Math.Min(s - InLength - ArcLength, OutLength);
            double begin = Math.Abs(Turn) - OutLength / (2 * Radius);
            var d = Integrate(exit, t => begin + t / Radius - t * t / (2 * Radius * OutLength));
            xy.X += d.X; xy.Y += d.Y;
            angle = begin + exit / Radius - exit * exit / (2 * Radius * OutLength);
            k = (1 - exit / OutLength) / Radius;
        }
        return (xy.X, xy.Y, angle, k);
    }
    internal (double X, double Y, double Heading, double Curvature) At(double station, double offset = 0)
    {
        double s = station - Station;
        if (!double.IsFinite(s) || s < -1e-7 || s > Length + 1e-7) throw new ArgumentOutOfRangeException(nameof(station));
        s = Math.Clamp(s, 0, Length);
        double x, y, theta, k;
        if (s <= TangentIn) { x = s; y = 0; theta = 0; k = 0; }
        else
        {
            var pt = CurvePoint(Math.Min(s - TangentIn, InLength + ArcLength + OutLength));
            x = TangentIn + pt.X; y = Math.Sign(Turn) * pt.Y;
            theta = Math.Sign(Turn) * pt.Angle; k = Math.Sign(Turn) * pt.Curvature;
            if (s > Length - TangentOut)
            { double t = s - (Length - TangentOut); x += t * Math.Cos(Turn); y += t * Math.Sin(Turn); }
        }
        double heading = Heading + theta;
        return (Start[0] + x * Math.Cos(Heading) - y * Math.Sin(Heading) + offset * Math.Sin(heading),
                Start[1] + x * Math.Sin(Heading) + y * Math.Cos(Heading) - offset * Math.Cos(heading), heading, k);
    }
}
