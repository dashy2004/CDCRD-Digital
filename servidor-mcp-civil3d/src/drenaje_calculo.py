"""Pure drainage design in SI: inlets along gutter runs (rational method) and gravity network sizing (Manning).

No CAD access. Inputs are plain dicts: gutter runs as returned by the native `cuneta`
action (points ordered by station with xyz) and design nodes supplied by the user.
"""
import math

RATIONAL_DIVISOR = 3.6e6   # Q [m3/s] = C * i [mm/h] * A [m2] / 3.6e6
FLAT_TOLERANCE_M = 1e-3    # elevation differences below this are a plateau
MIN_PIPE_LENGTH_M = .5
MAX_SLOPE = .5           # steeper reaches need drop structures, not a pipe


def _num(name, value, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{name} debe ser un numero entre {lo} y {hi}")
    return float(value)


def _xyz(name, value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(name + " requiere XYZ")
    return [_num(name, v, -1e8, 1e8) for v in value]


def caudal_racional(coeficiente_c, intensidad_mm_h, area_m2):
    """Rational method: Q = C i A / 3.6e6 in m3/s with i in mm/h and A in m2."""
    return _num("coeficiente_c", coeficiente_c, .05, 1) * _num("intensidad_mm_h", intensidad_mm_h, .1, 1000) * _num("area_m2", area_m2, 0, 1e9) / RATIONAL_DIVISOR


def capacidad_manning(diametro_m, pendiente, n_manning):
    """Full-flow capacity of a circular pipe: Q = (1/n) A R^(2/3) S^(1/2)."""
    d = _num("diametro_m", diametro_m, .05, 5); s = _num("pendiente", pendiente, 1e-6, 1); n = _num("n_manning", n_manning, .005, .1)
    area = math.pi * d * d / 4
    return area * (d / 4) ** (2 / 3) * math.sqrt(s) / n


def _dist2d(a, b):
    return math.hypot(b[0] - a[0], b[1] - a[1])


def _interpolar(puntos, acumulada, distancia):
    """Point (station, xyz) at a 2D distance along the run, by linear interpolation."""
    if distancia <= 0: p = puntos[0]; return p["estacion"], list(p["xyz"])
    if distancia >= acumulada[-1]: p = puntos[-1]; return p["estacion"], list(p["xyz"])
    k = 1
    while acumulada[k] < distancia: k += 1
    a, b = puntos[k - 1], puntos[k]
    span = acumulada[k] - acumulada[k - 1]
    t = 0 if span <= 0 else (distancia - acumulada[k - 1]) / span
    return a["estacion"] + t * (b["estacion"] - a["estacion"]), [a["xyz"][i] + t * (b["xyz"][i] - a["xyz"][i]) for i in range(3)]


def extremos_cuneta(puntos):
    """Indices of crests and sags of a run; plateaus count once (their middle point).

    Returns (crests, sags, flat) with indices in station order. Every run has at least one
    crest and one sag: a run that only descends has its crest at the start and its sag at the
    end; a flat run is reported as flat with the crest at the start and the sag at the end.
    The ends of a run are treated as physical boundaries: where a gutter is cut by a driveway
    or an open junction, the end inlet of the run must be reviewed by the designer.
    """
    z = [p["xyz"][2] for p in puntos]
    groups = []  # [first_index, last_index, z]
    for i, v in enumerate(z):
        if groups and abs(v - groups[-1][2]) <= FLAT_TOLERANCE_M: groups[-1][1] = i
        else: groups.append([i, i, v])
    if len(groups) == 1: return [0], [len(puntos) - 1], True
    crests, sags = [], []
    for k, (first, last, v) in enumerate(groups):
        mid = (first + last) // 2
        lower_prev = k > 0 and groups[k - 1][2] < v
        lower_next = k < len(groups) - 1 and groups[k + 1][2] < v
        higher_prev = k > 0 and groups[k - 1][2] > v
        higher_next = k < len(groups) - 1 and groups[k + 1][2] > v
        if k == 0:
            (crests if lower_next else sags).append(mid)
        elif k == len(groups) - 1:
            (crests if lower_prev else sags).append(mid)
        elif lower_prev and lower_next: crests.append(mid)
        elif higher_prev and higher_next: sags.append(mid)
    return crests, sags, False


def proponer_imbornales(cunetas, intensidad_mm_h, espaciamiento_max_m=60, ancho_aporte_m=8, coeficiente_c=.9, lados="ambos"):
    """Inlets at every sag plus intermediate inlets so that no stretch exceeds the spacing.

    Each monotone stretch between a crest and a sag is split into n = ceil(L / spacing) equal
    parts measured from the crest; the last inlet of the stretch is the sag itself. The
    tributary of an inlet is the stretch of gutter between the previous upstream inlet (or
    the crest) and the inlet; the sag inlet collects from both sides. Tributary area is the
    tributary length times the contributing width, and the flow is the rational method.
    """
    i = _num("intensidad_mm_h", intensidad_mm_h, .1, 1000)
    spacing = _num("espaciamiento_max_m", espaciamiento_max_m, 5, 500)
    width = _num("ancho_aporte_m", ancho_aporte_m, .1, 500)
    c = _num("coeficiente_c", coeficiente_c, .05, 1)
    if lados not in ("ambos", "izq", "der"): raise ValueError("lados debe ser ambos, izq o der")
    if not isinstance(cunetas, list) or not 1 <= len(cunetas) <= 100: raise ValueError("cunetas: lista de 1..100 lineas")
    runs = []; total_q = 0.0; total_len = 0.0; total_inlets = 0
    for r, run in enumerate(cunetas):
        if not isinstance(run, dict) or run.get("lado") not in ("izq", "der"): raise ValueError(f"cuneta {r + 1}: lado invalido")
        if lados != "ambos" and run["lado"] != lados: continue
        pts = run.get("puntos")
        if not isinstance(pts, list) or len(pts) < 2 or len(pts) > 50000: raise ValueError(f"cuneta {r + 1}: se requieren 2..50000 puntos")
        for p in pts:
            if not isinstance(p, dict): raise ValueError(f"cuneta {r + 1}: punto invalido")
            p["xyz"] = _xyz("xyz", p.get("xyz")); p["estacion"] = _num("estacion", p.get("estacion"), -1e7, 1e7)
        if any(pts[k + 1]["estacion"] < pts[k]["estacion"] for k in range(len(pts) - 1)): raise ValueError(f"cuneta {r + 1}: puntos fuera de orden de estacion")
        acc = [0.0]
        for k in range(1, len(pts)): acc.append(acc[-1] + _dist2d(pts[k - 1]["xyz"], pts[k]["xyz"]))
        length = acc[-1]
        if length < .01: raise ValueError(f"cuneta {r + 1}: longitud nula")
        crests, sags, flat = extremos_cuneta(pts)
        extremes = sorted([(idx, "cresta") for idx in crests] + [(idx, "punto_bajo") for idx in sags])
        inlets = {}  # key: rounded distance along run
        def add(dist, kind, upstream_from, upstream_to):
            key = round(dist, 4)
            if key not in inlets:
                station, xyz = _interpolar(pts, acc, dist)
                inlets[key] = dict(distancia_m=dist, estacion=station, xyz=xyz, tipo=kind, aportes=[])
            inlets[key]["aportes"].append(dict(desde_m=min(upstream_from, upstream_to), hasta_m=max(upstream_from, upstream_to), longitud_m=abs(upstream_to - upstream_from)))
        for (ia, ka), (ib, kb) in zip(extremes, extremes[1:]):
            crest_dist, sag_dist = (acc[ia], acc[ib]) if ka == "cresta" else (acc[ib], acc[ia])
            stretch = abs(sag_dist - crest_dist)
            if stretch < 1e-6: continue
            n = max(1, math.ceil(stretch / spacing - 1e-9)); step = stretch / n
            direction = 1 if sag_dist > crest_dist else -1
            for k in range(1, n + 1):
                here = crest_dist + direction * step * k
                add(sag_dist if k == n else here, "punto_bajo" if k == n else "intermedio", crest_dist + direction * step * (k - 1), sag_dist if k == n else here)
        rows = []
        for k, key in enumerate(sorted(inlets)):
            row = inlets[key]
            trib = sum(a["longitud_m"] for a in row["aportes"])
            for a in row["aportes"]:
                a["desde_estacion"] = _interpolar(pts, acc, a["desde_m"])[0]; a["hasta_estacion"] = _interpolar(pts, acc, a["hasta_m"])[0]
            area = trib * width; q = caudal_racional(c, i, area)
            rows.append(dict(id=f"I{r + 1}-{k + 1}", lado=run["lado"], baseline=run.get("baseline"), cuneta=r, **row, longitud_aporte_m=trib, area_m2=area, q_m3_s=q))
            total_q += q
        total_inlets += len(rows); total_len += length
        runs.append(dict(cuneta=r, baseline=run.get("baseline"), lado=run["lado"], indice=run.get("indice"), longitud_m=length, plano=flat,
                         estacion_inicio=pts[0]["estacion"], estacion_fin=pts[-1]["estacion"],
                         crestas=[dict(estacion=pts[k]["estacion"], xyz=pts[k]["xyz"]) for k in crests],
                         puntos_bajos=[dict(estacion=pts[k]["estacion"], xyz=pts[k]["xyz"]) for k in sags],
                         imbornales=rows, espaciamiento_max_real_m=max((b["distancia_m"] - a["distancia_m"] for a, b in zip(rows, rows[1:])), default=rows[0]["distancia_m"] if rows else 0)))
    if not runs: raise ValueError("Ninguna cuneta del lado pedido")
    return dict(metodo="racional Q=C*i*A/3.6e6", intensidad_mm_h=i, coeficiente_c=c, ancho_aporte_m=width, espaciamiento_max_m=spacing,
                cunetas=runs, resumen=dict(cunetas=len(runs), longitud_cunetas_m=total_len, imbornales=total_inlets, q_total_m3_s=total_q))


def validar_nodos(value):
    """Design nodes: a tree of inlets/manholes draining to exactly one outlet."""
    import json
    rows = json.loads(value) if isinstance(value, str) else value
    if not isinstance(rows, list) or not 2 <= len(rows) <= 200: raise ValueError("nodos: lista de 2..200 nodos")
    out = {}
    for r in rows:
        if not isinstance(r, dict): raise ValueError("Cada nodo es un objeto")
        node_id = r.get("id")
        if not isinstance(node_id, str) or not node_id.strip() or len(node_id) > 60 or any(ord(ch) < 32 for ch in node_id): raise ValueError("id de nodo invalido")
        if node_id in out: raise ValueError("Nodo duplicado: " + node_id)
        kind = r.get("tipo")
        if kind not in ("imbornal", "pozo", "salida"): raise ValueError("tipo de nodo debe ser imbornal, pozo o salida: " + node_id)
        downstream = r.get("hacia")
        if kind == "salida":
            if downstream is not None: raise ValueError("La salida no tiene hacia: " + node_id)
        elif not isinstance(downstream, str) or not downstream.strip(): raise ValueError("hacia requerido en " + node_id)
        out[node_id] = dict(id=node_id, tipo=kind, xyz=_xyz("xyz de " + node_id, r.get("xyz")), q_m3_s=_num("q_m3_s de " + node_id, r.get("q_m3_s", 0), 0, 100), hacia=downstream)
    outlets = [n for n in out.values() if n["tipo"] == "salida"]
    if len(outlets) != 1: raise ValueError("Se requiere exactamente un nodo salida")
    for n in out.values():
        if n["hacia"] is not None and n["hacia"] not in out: raise ValueError("hacia desconocido en " + n["id"])
        if n["hacia"] == n["id"]: raise ValueError("Nodo que drena a si mismo: " + n["id"])
        seen = set(); cur = n
        while cur["hacia"] is not None:
            if cur["id"] in seen: raise ValueError("Ciclo en la red desde " + n["id"])
            seen.add(cur["id"]); cur = out[cur["hacia"]]
    return list(out.values())


def disenar_red(nodos, diametros_mm=(300, 375, 450, 525, 600), pendiente_min=.005, profundidad_min_m=1.0, n_manning=.013, sumidero_m=0.0):
    """Sizes a gravity tree: inverts from the rim with a minimum cover over the crown, minimum slope, catalog diameters.

    Upstream first. At each node the outgoing invert is the lowest of (rim - cover - D) and
    the incoming inverts; the downstream invert is the lower of (invert - L * minimum slope)
    and the downstream rim constraint, so the slope is never below the minimum. The diameter
    is the smallest catalog diameter, never smaller than an incoming one, whose full-flow
    Manning capacity at that slope carries the accumulated rational flow. The cover is
    measured from the rim to the inner crown (invert + inner diameter); the wall thickness of
    the catalog part is not added.
    """
    nodes = {n["id"]: n for n in validar_nodos(nodos)}
    diam = sorted({int(_num("diametros_mm", d, 100, 3000)) for d in diametros_mm})
    if not 1 <= len(diam) <= 20: raise ValueError("diametros_mm: 1..20 valores")
    s_min = _num("pendiente_min", pendiente_min, .0005, .2); cover = _num("profundidad_min_m", profundidad_min_m, 0, 10)
    n_m = _num("n_manning", n_manning, .008, .05); sump = _num("sumidero_m", sumidero_m, 0, 3)
    children = {k: [] for k in nodes}
    for n in nodes.values():
        if n["hacia"] is not None: children[n["hacia"]].append(n["id"])
    outlet = next(n for n in nodes.values() if n["tipo"] == "salida")
    order = []  # post-order: upstream nodes first
    def visit(node_id):
        for ch in children[node_id]: visit(ch)
        order.append(node_id)
    visit(outlet["id"])
    if len(order) != len(nodes): raise ValueError("Nodos que no drenan a la salida")
    incoming = {k: [] for k in nodes}  # (invert at this node, diameter_m, flow)
    pipes = []
    for node_id in order:
        n = nodes[node_id]
        if n["hacia"] is None: continue
        v = nodes[n["hacia"]]
        length = _dist2d(n["xyz"], v["xyz"])
        if length < MIN_PIPE_LENGTH_M: raise ValueError(f"Tramo {node_id}->{v['id']} mas corto que {MIN_PIPE_LENGTH_M} m")
        q = n["q_m3_s"] + sum(f for _, _, f in incoming[node_id])
        d_floor = max((d for _, d, _ in incoming[node_id]), default=0)
        chosen = None
        for d_mm in diam:
            d = d_mm / 1000
            if d + 1e-9 < d_floor: continue
            inv_up = min([n["xyz"][2] - cover - d] + [inv for inv, _, _ in incoming[node_id]])
            inv_down = min(inv_up - length * s_min, v["xyz"][2] - cover - d)
            slope = (inv_up - inv_down) / length
            if slope > MAX_SLOPE: raise ValueError(f"Tramo {node_id}->{v['id']}: pendiente {slope:.3f} supera {MAX_SLOPE}; revisar cotas o intercalar pozos")
            cap = capacidad_manning(d, slope, n_m)
            if cap >= q or q == 0:
                chosen = (d_mm, d, inv_up, inv_down, slope, cap); break
        if chosen is None: raise ValueError(f"El caudal {q:.4f} m3/s del tramo {node_id}->{v['id']} excede el catalogo de diametros")
        d_mm, d, inv_up, inv_down, slope, cap = chosen
        area = math.pi * d * d / 4
        pipes.append(dict(id=f"T-{node_id}-{v['id']}", desde=node_id, hasta=v["id"], diametro_mm=d_mm, diametro_m=d, cota_inicio=inv_up, cota_fin=inv_down,
                          longitud_m=length, pendiente=slope, q_m3_s=q, capacidad_m3_s=cap, velocidad_llena_m_s=cap / area, relacion_q=(q / cap if cap > 0 else 0),
                          profundidad_clave_inicio_m=n["xyz"][2] - (inv_up + d), profundidad_clave_fin_m=v["xyz"][2] - (inv_down + d)))
        incoming[v["id"]].append((inv_down, d, q))
    structures = []
    for node_id in order:
        n = nodes[node_id]
        own = [p["cota_inicio"] for p in pipes if p["desde"] == node_id] + [inv for inv, _, _ in incoming[node_id]]
        structures.append(dict(id=node_id, tipo=n["tipo"], xyz=n["xyz"], rasante=n["xyz"][2], cota_fondo=min(own) - sump, q_propio_m3_s=n["q_m3_s"],
                               q_acumulado_m3_s=n["q_m3_s"] + sum(f for _, _, f in incoming[node_id])))
    warnings = [f"{p['id']}: velocidad a seccion llena {p['velocidad_llena_m_s']:.2f} m/s fuera de 0.6..5 m/s" for p in pipes if not .6 <= p["velocidad_llena_m_s"] <= 5]
    return dict(estructuras=structures, tuberias=pipes, parametros=dict(diametros_mm=diam, pendiente_min=s_min, profundidad_min_m=cover, n_manning=n_m, sumidero_m=sump),
                resumen=dict(estructuras=len(structures), tuberias=len(pipes), longitud_total_m=sum(p["longitud_m"] for p in pipes), q_salida_m3_s=structures[-1]["q_acumulado_m3_s"],
                             diametro_max_mm=max(p["diametro_mm"] for p in pipes), pendiente_min=min(p["pendiente"] for p in pipes), profundidad_clave_min_m=min(min(p["profundidad_clave_inicio_m"], p["profundidad_clave_fin_m"]) for p in pipes)),
                advertencias=warnings)
