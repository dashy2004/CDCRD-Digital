#!/usr/bin/env python3
"""Ejemplo ficticio: esquemas de secciones de columna y portico tipo en DXF.

Genera cuatro archivos .dxf (tres secciones de columna y un portico de tres
niveles) con capas separadas, cotas nativas y textos. Unidades: centimetros
(1 unidad DWG = 1 cm, $INSUNITS = 5).

Geometria ILUSTRATIVA: no corresponde a ningun proyecto y no sustituye calculo
ni validacion normativa. Requiere ezdxf.
"""
import ezdxf
from ezdxf.enums import TextEntityAlignment

# ---------- datos ----------
DB6 = 1.905        # diametro barra #6 (cm)
DB3 = 0.953        # diametro estribo #3 (cm)
REC = 4.0          # recubrimiento libre (cm)
OFF = REC + DB3 + DB6 / 2.0   # cara de hormigon -> centro de barra = 5.9055

SECCIONES = {
    "C1": dict(b=35.0, h=45.0 * 0 + 35.0, nx=4, ny=4),
    "C2": dict(b=40.0, h=40.0, nx=5, ny=4),
    "C3": dict(b=40.0, h=45.0, nx=5, ny=5),
}

LAYERS = [
    ("HORMIGON", 7, "CONTINUOUS", 50),
    ("ESTRIBO", 3, "DASHED", 25),
    ("ACERO", 1, "CONTINUOUS", 35),
    ("COTAS", 4, "CONTINUOUS", 18),
    ("TEXTO", 7, "CONTINUOUS", 18),
    ("EJES", 8, "CENTER", 13),
]


def nuevo_doc():
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 5          # centimetros
    doc.header["$MEASUREMENT"] = 1       # metrico
    doc.header["$LUNITS"] = 2
    for name, color, lt, lw in LAYERS:
        ly = doc.layers.add(name)
        ly.color = color
        ly.dxf.linetype = lt
        ly.dxf.lineweight = lw
    ds = doc.dimstyles.duplicate_entry("Standard", "ESQ")
    ds.dxf.dimtxt = 1.5      # altura texto cota
    ds.dxf.dimasz = 1.2      # flecha
    ds.dxf.dimexe = 0.8
    ds.dxf.dimexo = 0.6
    ds.dxf.dimgap = 0.5
    ds.dxf.dimtad = 1        # texto sobre la linea
    ds.dxf.dimdec = 1
    ds.dxf.dimlfac = 1.0
    ds.dxf.dimscale = 1.0
    ds.dxf.dimblk = "ARCHTICK"
    ds.dxf.dimclrd = 4       # color de la linea de cota (ezdxf la pone en capa 0)
    ds.dxf.dimclre = 4       # color de las lineas de extension
    ds.dxf.dimclrt = 4       # color del texto
    ds.dxf.dimdsep = ord(".")
    ds.dxf.dimzin = 0        # no suprimir el decimal (7.0 en vez de 7)
    ds.dxf.dimtih = 0
    ds.dxf.dimtoh = 0
    return doc


def rect(msp, x0, y0, b, h, layer):
    msp.add_lwpolyline(
        [(x0, y0), (x0 + b, y0), (x0 + b, y0 + h), (x0, y0 + h)],
        close=True, dxfattribs={"layer": layer},
    )


def rect_redondeado(msp, x0, y0, x1, y1, r, layer):
    """Rectangulo con esquinas redondeadas (radio r) como LWPOLYLINE con bulges."""
    B = 0.414213562373095  # bulge de un arco de 90 grados (sentido antihorario)
    pts = [
        (x0 + r, y0, 0, 0, 0.0),
        (x1 - r, y0, 0, 0, B),
        (x1, y0 + r, 0, 0, 0.0),
        (x1, y1 - r, 0, 0, B),
        (x1 - r, y1, 0, 0, 0.0),
        (x0 + r, y1, 0, 0, B),
        (x0, y1 - r, 0, 0, 0.0),
        (x0, y0 + r, 0, 0, B),
    ]
    msp.add_lwpolyline(pts, format="xyseb", close=True, dxfattribs={"layer": layer})


def estribo(msp, b, h, rec=REC, db=DB3, layer="ESTRIBO"):
    """Estribo dibujado con su ESPESOR real: cara externa a 'rec' de la cara de
    hormigon y cara interna a 'rec + db'. Dobleces redondeados (radio interior
    2 db) y gancho a 135 grados de longitud 6 db (>= 7.5 cm) tambien con espesor."""
    # cara externa del estribo
    xe, ye = b / 2.0 - rec, h / 2.0 - rec
    # cara interna
    xi, yi = xe - db, ye - db
    ri = 2.0 * db            # radio interior del doblez (diam. de doblez = 4 db)
    re = ri + db             # radio exterior
    rect_redondeado(msp, -xe, -ye, xe, ye, re, layer)
    rect_redondeado(msp, -xi, -yi, xi, yi, ri, layer)

    # gancho a 135 grados en la esquina superior izquierda, con espesor
    Lg = max(6.0 * db, 7.5)
    ux, uy = 0.70710678, -0.70710678          # direccion 45 grados hacia el nucleo
    px, py = -uy, ux                          # normal unitaria
    ax, ay = -xi + ri * 0.4, yi - ri * 0.4    # arranque sobre la esquina del estribo
    p1 = (ax + px * db / 2, ay + py * db / 2)
    p2 = (p1[0] + ux * Lg, p1[1] + uy * Lg)
    p3 = (p2[0] - px * db, p2[1] - py * db)
    p4 = (p1[0] - px * db, p1[1] - py * db)
    msp.add_lwpolyline([p1, p2, p3, p4], close=True, dxfattribs={"layer": layer})


def barra(msp, x, y, d=DB6):
    msp.add_circle((x, y), d / 2.0, dxfattribs={"layer": "ACERO"})
    hatch = msp.add_hatch(dxfattribs={"layer": "ACERO", "color": 256})
    path = hatch.paths.add_edge_path()
    path.add_arc((x, y), d / 2.0, 0, 360)
    hatch.set_solid_fill(color=256)


def posiciones_barras(b, h, nx, ny):
    """Grid perimetral: nx barras en la cara de ancho b, ny en la cara de peralte h."""
    x0, x1 = -b / 2.0 + OFF, b / 2.0 - OFF
    y0, y1 = -h / 2.0 + OFF, h / 2.0 - OFF
    xs = [x0 + (x1 - x0) * i / (nx - 1) for i in range(nx)]
    ys = [y0 + (y1 - y0) * j / (ny - 1) for j in range(ny)]
    pts = []
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            if i in (0, nx - 1) or j in (0, ny - 1):
                pts.append((x, y))
    return pts, xs, ys


def texto(msp, s, x, y, h=1.6, layer="TEXTO", align=TextEntityAlignment.LEFT):
    t = msp.add_text(s, dxfattribs={"layer": layer, "height": h, "style": "OpenSans"})
    t.set_placement((x, y), align=align)
    return t


def dibujar_seccion(nombre, b, h, nx, ny, path):
    doc = nuevo_doc()
    msp = doc.modelspace()

    # contorno de hormigon
    rect(msp, -b / 2, -h / 2, b, h, "HORMIGON")

    # estribo No.3 con espesor real (doble linea) + gancho 135 grados
    estribo(msp, b, h)

    # acero longitudinal
    pts, xs, ys = posiciones_barras(b, h, nx, ny)
    for (x, y) in pts:
        barra(msp, x, y)

    # ejes de centro
    msp.add_line((-b / 2 - 4, 0), (b / 2 + 4, 0), dxfattribs={"layer": "EJES"})
    msp.add_line((0, -h / 2 - 4), (0, h / 2 + 4), dxfattribs={"layer": "EJES"})

    # cotas generales
    d1 = msp.add_linear_dim(base=(0, -h / 2 - 9), p1=(-b / 2, -h / 2), p2=(b / 2, -h / 2),
                            dimstyle="ESQ", dxfattribs={"layer": "COTAS"})
    d1.render()
    d2 = msp.add_linear_dim(base=(b / 2 + 9, 0), p1=(b / 2, -h / 2), p2=(b / 2, h / 2),
                            angle=90, dimstyle="ESQ", dxfattribs={"layer": "COTAS"})
    d2.render()

    # cotas de separacion de barras en la cara inferior
    yb = -h / 2
    for i in range(len(xs) - 1):
        d = msp.add_linear_dim(base=(0, yb - 4.5), p1=(xs[i], yb), p2=(xs[i + 1], yb),
                               dimstyle="ESQ", dxfattribs={"layer": "COTAS"})
        d.render()
    # cotas de separacion en la cara derecha
    xr = b / 2
    for j in range(len(ys) - 1):
        d = msp.add_linear_dim(base=(xr + 4.5, 0), p1=(xr, ys[j]), p2=(xr, ys[j + 1]),
                               angle=90, dimstyle="ESQ", dxfattribs={"layer": "COTAS"})
        d.render()

    # recubrimiento (cota corta en la esquina superior izquierda)
    d = msp.add_linear_dim(base=(-b / 2 - 4.5, h / 2 + 3), p1=(-b / 2, h / 2),
                           p2=(-b / 2 + REC, h / 2), dimstyle="ESQ",
                           dxfattribs={"layer": "COTAS"})
    d.render()

    # rotulos
    nb = len(pts)
    texto(msp, f"COLUMNA {nombre}   {b:.0f} x {h:.0f} cm   (EJEMPLO FICTICIO)",
           -b / 2, h / 2 + 14, h=2.4)
    yl = -h / 2 - 15
    lineas = [
        f"{nb} BARRAS No. 6  (Ø{DB6} cm)",
        f"ESTRIBOS No. 3 @ 20 cm  (Ø{DB3} cm)",
        f"RECUBRIMIENTO LIBRE = {REC:.0f} cm",
        "f'c = 240 kgf/cm2     fy = 4200 kgf/cm2  (GR-60)",
        f"Ag = {b*h:.0f} cm2     As = {nb*2.85:.2f} cm2     p = {nb*2.85/(b*h)*100:.2f} %",
        "COTAS EN cm.  SEPARACIONES MEDIDAS A EJES DE BARRA.",
        "GEOMETRIA ILUSTRATIVA; SIN CALCULO NI VALIDACION NORMATIVA.",
    ]
    for i, s in enumerate(lineas):
        texto(msp, s, -b / 2, yl - i * 3.2, h=1.6)

    doc.saveas(path)
    return nb


def dibujar_portico(path):
    doc = nuevo_doc()
    msp = doc.modelspace()

    BIG = {"dimtxt": 14.0, "dimasz": 10.0, "dimexe": 6.0, "dimexo": 5.0, "dimgap": 4.0}
    H = 310.0                      # altura de entrepiso (cm)
    niveles = 3
    vanos = [340.0, 350.0, 340.0]  # vanos esquematicos
    xs = [0.0]
    for v in vanos:
        xs.append(xs[-1] + v)
    ys = [i * H for i in range(niveles + 1)]
    L = xs[-1]

    # columnas (linea de eje)
    for x in xs:
        msp.add_line((x, ys[0]), (x, ys[-1]), dxfattribs={"layer": "HORMIGON"})
    # vigas
    for y in ys[1:]:
        msp.add_line((xs[0], y), (xs[-1], y), dxfattribs={"layer": "HORMIGON"})

    # empotramientos en la base: linea de terreno + achurado inclinado
    msp.add_line((xs[0] - 40, 0), (xs[-1] + 40, 0), dxfattribs={"layer": "HORMIGON"})
    for x in xs:
        msp.add_lwpolyline([(x - 22, 0), (x + 22, 0)],
                           dxfattribs={"layer": "HORMIGON", "const_width": 2.0})
        for k in range(8):
            xa = x - 22 + k * 6.3
            msp.add_line((xa, 0), (xa - 9, -13), dxfattribs={"layer": "HORMIGON"})

    # cotas de altura de entrepiso
    for i in range(niveles):
        d = msp.add_linear_dim(base=(xs[0] - 55, 0), p1=(xs[0], ys[i]), p2=(xs[0], ys[i + 1]),
                               angle=90, dimstyle="ESQ", override=BIG,
                               dxfattribs={"layer": "COTAS"})
        d.render()
    # cota total
    dt = msp.add_linear_dim(base=(xs[0] - 125, 0), p1=(xs[0], ys[0]), p2=(xs[0], ys[-1]),
                            angle=90, dimstyle="ESQ", override=BIG,
                            dxfattribs={"layer": "COTAS"})
    dt.render()
    # cotas de vanos
    for i in range(len(vanos)):
        d = msp.add_linear_dim(base=(0, ys[-1] + 55), p1=(xs[i], ys[-1]), p2=(xs[i + 1], ys[-1]),
                               dimstyle="ESQ", override=BIG,
                               dxfattribs={"layer": "COTAS"})
        d.render()

    # rotulos de nivel y de miembros
    for i, y in enumerate(ys):
        et = "BASE (EMPOTRAMIENTO)" if i == 0 else f"NIVEL {i}   (+{y/100:.2f} m)"
        texto(msp, et, xs[-1] + 55, y - 7, h=14)
    for y in ys[1:]:
        texto(msp, "V1  30 x 50", (xs[0] + xs[1]) / 2 - 60, y + 10, h=13)
    texto(msp, "COLUMNA (TIPO C1 / C2 / C3 SEGUN PLANTA)", xs[1] + 12,
          (ys[0] + ys[1]) / 2, h=13)
    texto(msp, "COTAS EN cm", xs[0], -60, h=14)

    # titulo y notas
    texto(msp, "PORTICO TIPO - 3 NIVELES   (h entrepiso = 3.10 m)   EJEMPLO FICTICIO",
          xs[0], ys[-1] + 130, h=26)
    notas = [
        "VERIFICACION DE ESBELTEZ:",
        "Lu = 310 - 50 = 260 cm   (altura libre de columna; viga V1 h = 50 cm)",
        "r = 0.30 h   (seccion rectangular)",
        "ARRIOSTRADO:      limite  k Lu / r  <=  34 - 12 (M1/M2)",
        "NO ARRIOSTRADO:   limite  k Lu / r  <=  22",
        "k se obtiene de los nomogramas de Jackson - Moreland segun psi A y psi B.",
        "GEOMETRIA ILUSTRATIVA; SIN CALCULO NI VALIDACION NORMATIVA.",
    ]
    for i, s in enumerate(notas):
        texto(msp, s, xs[0], -95 - i * 26, h=15)

    doc.saveas(path)
    return len(xs), niveles


if __name__ == "__main__":
    import os
    out = os.path.dirname(os.path.abspath(__file__))
    for nombre, s in SECCIONES.items():
        p = os.path.join(out, f"seccion_{nombre}.dxf")
        nb = dibujar_seccion(nombre, s["b"], s["h"], s["nx"], s["ny"], p)
        print(f"{nombre}: {s['b']:.0f}x{s['h']:.0f}  grid {s['nx']}x{s['ny']}  barras={nb}  -> {p}")
    p = os.path.join(out, "portico.dxf")
    print("portico:", dibujar_portico(p), "->", p)
