"""Pure SI hydraulic API. No CAD writes or implicit unit conversion."""
import math

G_M_S2 = 9.81
VERSION = "0.1.0"


def number(name, value, minimum=None, strict=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name}: expected finite number")
    if minimum is not None and (value < minimum or (strict and value == minimum)):
        raise ValueError(f"{name}: out of range")
    return value


def section(b_m, z_h_v, y_m):
    """Symmetric trapezoid; rectangular z=0, triangular b=0."""
    number("b_m", b_m, 0)
    number("z_h_v", z_h_v, 0)
    number("y_m", y_m, 0, True)
    if b_m == 0 and z_h_v == 0:
        raise ValueError("empty section")
    area = y_m * (b_m + z_h_v * y_m)
    perimeter = b_m + 2 * y_m * math.hypot(1, z_h_v)
    top = b_m + 2 * z_h_v * y_m
    for name, value in (("area_m2", area), ("perimeter_m", perimeter), ("top_width_m", top)):
        number(name, value, 0, True)
    number("radius_m", area / perimeter, 0, True)
    return {"area_m2": area, "perimeter_m": perimeter,
            "top_width_m": top, "radius_m": area / perimeter}


def manning(b_m, z_h_v, y_m, n_s_m13, slope_m_m):
    """Uniform flow only: slope is energy slope, equal to bed slope at uniform flow."""
    number("n_s_m13", n_s_m13, 0, True)
    number("slope_m_m", slope_m_m, 0, True)
    s = section(b_m, z_h_v, y_m)
    return number("computed_q_m3_s", s["area_m2"] * s["radius_m"] ** (2 / 3)
                  * math.sqrt(slope_m_m) / n_s_m13, 0, True)


def _depth(increasing_residual):
    def residual(y):
        try:
            return number("depth residual", increasing_residual(y))
        except (OverflowError, ZeroDivisionError) as exc:
            raise ValueError("inputs exceed numerical range") from exc
    low, high = 0.0, 1.0
    for _ in range(40):
        if residual(high) >= 0:
            break
        high *= 2
    else:
        raise ValueError("depth could not be bracketed")
    for _ in range(160):
        mid = (low + high) / 2
        if residual(mid) > 0:
            high = mid
        else:
            low = mid
    result = (low + high) / 2
    if abs(residual(result)) > 1e-9:
        raise ValueError("depth residual did not converge")
    return result


def normal_depth(q_m3_s, b_m, z_h_v, n_s_m13, slope_m_m):
    number("q_m3_s", q_m3_s, 0, True)
    return _depth(lambda y: manning(b_m, z_h_v, y, n_s_m13, slope_m_m) / q_m3_s - 1)


def critical_depth(q_m3_s, b_m, z_h_v):
    """Hydrostatic prismatic section, energy coefficient alpha=1."""
    number("q_m3_s", q_m3_s, 0, True)
    def residual(y):
        s = section(b_m, z_h_v, y)
        return G_M_S2 * s["area_m2"] ** 3 / (q_m3_s ** 2 * s["top_width_m"]) - 1
    return _depth(residual)


def state(q_m3_s, b_m, z_h_v, y_m, bed_m):
    number("q_m3_s", q_m3_s, 0, True)
    number("bed_m", bed_m)
    s = section(b_m, z_h_v, y_m)
    velocity = q_m3_s / s["area_m2"]
    specific = y_m + velocity ** 2 / (2 * G_M_S2)
    return {**s, "y_m": y_m, "velocity_m_s": velocity,
            "froude": velocity / math.sqrt(G_M_S2 * s["area_m2"] / s["top_width_m"]),
            "specific_energy_m": specific, "total_head_m": bed_m + specific,
            "water_level_m": bed_m + y_m, "alpha": 1.0}


def energy_gate(available_head_m, required_head_m, losses_m=0.0):
    """Necessary local energy condition. A pass never certifies the whole route."""
    number("required_head_m", required_head_m)
    number("losses_m", losses_m, 0)
    if available_head_m is None:
        return {"status": "unverified", "margin_m": None, "route_verified": False}
    number("available_head_m", available_head_m)
    margin = available_head_m - required_head_m - losses_m
    number("margin_m", margin)
    return {"status": "insufficient" if margin < 0 else "necessary_condition_met",
            "margin_m": margin, "route_verified": False}


def calculate(request):
    """JSON object API; explicit SI required, no hidden default roughness or slope."""
    expected = {"units", "q_m3_s", "b_m", "z_h_v", "n_s_m13", "slope_m_m", "bed_m", "available_head_m", "losses_m"}
    if not isinstance(request, dict) or set(request) != expected:
        raise ValueError("expected exactly: " + ", ".join(sorted(expected)))
    if request["units"] != "SI":
        raise ValueError("only explicit SI units supported")
    q, b, z = (request[k] for k in ("q_m3_s", "b_m", "z_h_v"))
    yn = normal_depth(q, b, z, request["n_s_m13"], request["slope_m_m"])
    yc = critical_depth(q, b, z)
    normal = state(q, b, z, yn, request["bed_m"])
    return {"schema_version": VERSION, "inputs": dict(request), "normal": normal,
            "critical": state(q, b, z, yc, request["bed_m"]),
            "energy_gate": energy_gate(request["available_head_m"], normal["total_head_m"], request["losses_m"]),
            "scope": "Local uniform/critical calculation, alpha=1. No GVF, transitions, tailwater or route certification."}
