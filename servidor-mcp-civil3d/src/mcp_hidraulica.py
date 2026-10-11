"""Standalone MCP facade for offline hydraulic calculations (no CAD connection)."""
from mcp.server.fastmcp import FastMCP
from pydantic import StrictFloat, StrictStr
from hidraulica import calculate

mcp = FastMCP('cdcrd-hidraulica')


@mcp.tool()
def calcular_seccion_si(units: StrictStr, q_m3_s: StrictFloat, b_m: StrictFloat, z_h_v: StrictFloat,
                       n_s_m13: StrictFloat, slope_m_m: StrictFloat, bed_m: StrictFloat,
                       available_head_m: StrictFloat | None, losses_m: StrictFloat) -> dict:
    """Normal/critical trapezoidal flow in SI, local energy gate; never certifies a route.

    n_s_m13 is Manning n in s/m^(1/3); z_h_v is horizontal/vertical bank slope.
    available_head_m must be measured TOTAL head on the same datum as bed_m,
    or null when unknown. losses_m is an explicit assumed/verified input.
    Requires all inputs; units must be SI. No CAD or HCanales access.
    """
    return calculate(dict(units=units, q_m3_s=q_m3_s, b_m=b_m, z_h_v=z_h_v,
                          n_s_m13=n_s_m13, slope_m_m=slope_m_m, bed_m=bed_m,
                          available_head_m=available_head_m, losses_m=losses_m))


if __name__ == '__main__':
    mcp.run(transport='stdio')
