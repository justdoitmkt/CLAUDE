"""cabin_builder.py — cabañas de madera BLACKISLE (CAB_1_tablones, CAB_2_pilotes, CAB_3_ladrillo), con interior completo.

Sistema: planta w (X) x d (Y) centrada; fachada principal hacia -Y; cumbrera en X (hastiales en x = ±w/2).
Estructura: base (dados, pilotes con cruces de San Andrés o PB de ladrillo), plataforma de vigas + duela, muros de bastidor con el
revestimiento del kit (tablón y junquillo / tabla traslapada / ladrillo), entrepiso de vigas y duela con hueco de escalera,
escalera interior recta de madera, divisiones de tabla, hastiales de tabla cortados al faldón, cubierta del kit (estructura de
cabios con colas + lámina ondulada o tablones escalonados) y los elementos propios de cada concepto.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402,F401
from mathutils import Matrix, Vector  # noqa: E402

import apt_common as ac  # noqa: E402
from kit.common import MB, rng, wall_with_openings  # noqa: E402

T = lambda x=0.0, y=0.0, z=0.0: Matrix.Translation((x, y, z))  # noqa: E731
RZ = ac._rot_z
WALL_T = {"board_and_batten": 0.125, "clapboard": 0.13, "brick": 0.14}


def cfg_cab(bid):
    if bid == "CAB_1_tablones":
        return dict(id=bid, w=9.0, d=6.0, levels=2, floor_h=2.8, base="piers", z0=0.40, siding="board_and_batten", pitch=35.0,
                    ovh=0.5, roof="corrugated_rust", seed=5, porch=dict(side="west", depth=2.4), stove_pipe=True,
                    stair=dict(x=-3.9, along="+x", y_side="back"), split_x=1.2)
    if bid == "CAB_2_pilotes":
        return dict(id=bid, w=7.0, d=6.0, levels=1, floor_h=2.6, base="stilts", z0=2.0, siding="clapboard", pitch=28.0, ovh=0.45,
                    roof="corrugated_light", seed=9, veranda=1.2, ext_stair=True, cistern=True, torn=True, loft=True, split_x=0.6)
    if bid == "CAB_3_ladrillo":
        return dict(id=bid, w=8.0, d=6.5, levels=2, floor_h=2.8, base="slab", z0=0.15, siding="clapboard", ground="brick", pitch=30.0,
                    ovh=0.45, roof="boards", seed=14, porch=dict(side="front", depth=2.4, x0=-0.6, x1=4.0), chimney=True,
                    stair=dict(x=-3.6, along="+x", y_side="back"), split_x=0.4, gutter=True)
    raise KeyError(bid)


# ----------------------------------------------------------------------------------------------
# utilidades
# ----------------------------------------------------------------------------------------------
def wall_m(cfg, side, z0, t):
    """Matriz del muro (u a lo largo, cara exterior hacia afuera). Frente y fondo de esquina a esquina; testeros entre ellos."""
    w, d = cfg["w"], cfg["d"]
    yf = cfg.get("front_y", -d / 2)
    if side == "front":
        return T(-w / 2, yf, z0), w
    if side == "back":
        return T(w / 2, d / 2, z0) @ RZ(180), w
    L = (d / 2 - t) - (yf + t)
    if side == "west":
        return T(-w / 2, d / 2 - t, z0) @ RZ(-90), L
    return T(w / 2, yf + t, z0) @ RZ(90), L


def siding(kind, L, H, seed, ops, rot=0.08):
    from kit import cladding as cl
    o = [x for _, x in ops]
    if kind == "board_and_batten":
        return cl.board_and_batten(L, H, seed=seed, openings=o, rot=rot)
    if kind == "clapboard":
        return cl.clapboard(L, H, seed=seed, openings=o, loose=0.08)
    return cl.brick_wall(L, H, seed=seed, openings=o, missing=0.03, detail="mid")


def place_ops(L, H, spec):
    """spec: [(tipo, u_centro, ancho, alto, antepecho)] -> [(tipo, (u0, u1, v0, v1))] recortados al muro."""
    out = []
    for kind, uc, w, h, sill in spec:
        u0 = min(max(uc - w / 2, 0.25), L - 0.25 - w)
        out.append((kind, (round(u0, 4), round(u0 + w, 4), round(sill, 4), round(min(sill + h, H - 0.12), 4))))
    return out


def dress_ops(det, M, ops, t, r):
    from kit import openings as op
    n = 0
    for kind, (u0, u1, v0, v1) in ops:
        w, h = u1 - u0, v1 - v0
        Mi = M @ T(u0, 0, v0)
        s = int(r.integers(1e6))
        if kind == "win":
            k = "shutter" if r.random() < 0.6 else ("boarded" if r.random() < 0.3 else "casement")
            det.join(op.window(k, w, h, t, seed=s, broken=float(r.uniform(0.5, 1.0)), curtain=r.random() < 0.35), Mi)
        elif kind == "door":
            det.join(op.door("plank", w, h, t, seed=s, open_angle=max(60.0, float(r.uniform(10, 70)))), Mi)
        else:
            continue
        n += 1
    return n


def boards_floor(mb, x0, x1, y0, y1, z, r, holes=(), board=0.14, t=0.028, missing=0.05, mat="wood"):
    """Duela: tablas a lo largo de X (tramos de 2–3 m con juntas desfasadas), faltantes al azar; respeta huecos (x0, x1, y0, y1)."""
    y = y0
    row = 0
    while y < y1 - 0.02:
        yb = min(y + board - 0.004, y1)
        segs = [(x0, x1)]
        for (hx0, hx1, hy0, hy1) in holes:
            if yb > hy0 and y < hy1:
                nxt = []
                for a, b in segs:
                    if hx1 <= a or hx0 >= b:
                        nxt.append((a, b))
                    else:
                        if hx0 > a:
                            nxt.append((a, hx0))
                        if hx1 < b:
                            nxt.append((hx1, b))
                segs = nxt
        for a, b in segs:
            xs = [a]
            xx = a + (0.9 if row % 2 else 1.7)
            while xx < b - 0.4:
                xs.append(xx)
                xx += 2.6
            xs.append(b)
            for p, q in zip(xs, xs[1:]):
                if r.random() < missing:
                    continue
                dz = float(r.uniform(-0.006, 0.004))
                mb.box((p + 0.002, y, z - t + dz), (q - 0.002, yb, z + dz), mat, bevel=0.003, seg=1)
        y += board
        row += 1


def joists(mb, x0, x1, y0, y1, z_top, step=0.45, h=0.20, b=0.05, skip=(), mat="wood"):
    """Vigas de entrepiso a lo largo de Y cada `step`; `skip` = rangos x del hueco (ahí las vigas se cortan en un brochal)."""
    x = x0 + b / 2
    n = 0
    while x < x1:
        cut = [s for s in skip if s[0] < x < s[1]]
        if cut:
            hx0, hx1, hy0, hy1 = cut[0]
            if hy0 - y0 > 0.1:
                mb.box((x - b / 2, y0, z_top - h), (x + b / 2, hy0, z_top), mat)
            if y1 - hy1 > 0.1:
                mb.box((x - b / 2, hy1, z_top - h), (x + b / 2, y1, z_top), mat)
        else:
            mb.box((x - b / 2, y0, z_top - h), (x + b / 2, y1, z_top), mat)
        x += step
        n += 1
    for (hx0, hx1, hy0, hy1) in skip:                      # brochales
        for yy in (hy0 - b, hy1):
            mb.box((hx0, yy, z_top - h), (hx1, yy + b, z_top), mat)
    return n


def gable(mb, cfg, side, z_crown, t, r, top_fn):
    """Hastial de tablas cortadas bajo el faldón: verticales (tablón y junquillo) u horizontales traslapadas (clapboard)."""
    w, d = cfg["w"], cfg["d"]
    yf = -d / 2                                       # el hastial cubre toda la profundidad del techo
    sx = -1 if side == "west" else 1
    x_out = sx * w / 2
    xin = x_out - sx * t
    if cfg["siding"] == "board_and_batten":
        y = yf + 0.02
        while y < d / 2 - 0.02:
            yc = y + 0.11
            ztop = min(top_fn(x_out, y), top_fn(x_out, y + 0.22)) - 0.16
            if ztop > 0.05:
                jag = float(r.uniform(-0.04, 0.0))
                mb.box((min(x_out, x_out - sx * 0.022), y, z_crown), (max(x_out, x_out - sx * 0.022), y + 0.22, z_crown + ztop + jag), "wood",
                       bevel=0.004, seg=1)
                yb = y + 0.22 + 0.02
                zt2 = min(top_fn(x_out, yb - 0.025), top_fn(x_out, yb + 0.025)) - 0.16
                if zt2 > 0.05 and yb < d / 2 - 0.05:
                    mb.box((min(x_out + sx * 0.021, x_out), yb - 0.025, z_crown), (max(x_out + sx * 0.021, x_out), yb + 0.025, z_crown + zt2),
                           "wood", bevel=0.003, seg=1)
            y += 0.26
        # bastidor detrás (pies derechos) para que el desván no se vea hueco desde dentro
        y = yf + 0.3
        while y < d / 2 - 0.3:
            zt = top_fn(x_out, y) - 0.2
            if zt > 0.1:
                mb.box((min(xin, xin + sx * 0.1), y - 0.025, z_crown), (max(xin, xin + sx * 0.1), y + 0.025, z_crown + zt), "wood")
            y += 0.6
    else:
        z = 0.0
        k = 0
        while True:
            yl, yh = yf - 0.0, d / 2
            # ancho de la hilada a la altura z: donde el faldón queda 0,16 por encima
            ys = [yf + (d) * i / 40 for i in range(41)]
            ok = [yy for yy in ys if top_fn(x_out, yy) - 0.16 > z + 0.15]
            if not ok:
                break
            a, b = min(ok), max(ok)
            mat = "wood_grey"
            M = T(x_out, 0, z_crown + z) @ Matrix.Rotation(math.radians(sx * 4.0), 4, "Y")
            mb.box((-0.016 if sx > 0 else 0.0, a, 0.0), (0.0 if sx > 0 else 0.016, b, 0.17), mat, bevel=0.003, seg=1, m=M)
            z += 0.15
            k += 1
        y = yf + 0.3
        while y < d / 2 - 0.3:
            zt = top_fn(x_out, y) - 0.2
            if zt > 0.1:
                mb.box((min(xin, xin + sx * 0.1), y - 0.025, z_crown), (max(xin, xin + sx * 0.1), y + 0.025, z_crown + zt), "wood")
            y += 0.6


def partition_wood(mb, p0, p1, z0, H, doors=(), t=0.05, out=None, r=None):
    """División de tabla (una capa de tablones verticales sobre bastidor implícito)."""
    (xa, ya), (xb, yb) = p0, p1
    along_x = abs(yb - ya) < 1e-6
    a0 = min(xa, xb) if along_x else min(ya, yb)
    L = abs(xb - xa) + abs(yb - ya)
    ops = []
    for c, w in doors:
        u0, u1 = max(c - w / 2 - a0, 0.05), min(c + w / 2 - a0, L - 0.05)
        if u1 - u0 > 0.3:
            ops.append((round(u0, 4), round(u1, 4), 0.0, min(2.0, H - 0.1)))
    if along_x:
        m = Matrix(((1, 0, 0, a0), (0, 1, 0, ya - t / 2), (0, 0, 1, z0), (0, 0, 0, 1)))
    else:
        m = Matrix(((0, -1, 0, xa + t / 2), (1, 0, 0, a0), (0, 0, 1, z0), (0, 0, 0, 1)))
    wall_with_openings(mb, L, H, t, ops, mat_out="wood_grey", mat_in="wood_grey", mat_reveal="wood", m=m)
    if out is not None:
        for (u0, u1, v0, v1) in ops:
            out.append(dict(m=m, u0=u0, w=u1 - u0, h=v1, t=t))


# ----------------------------------------------------------------------------------------------
# constructor
# ----------------------------------------------------------------------------------------------
def build_cabin(bid, collection_root=None, dress_all=True):
    from kit import circulation as circ
    from kit import openings as op
    from kit import roofing as rf
    from kit.common import get_collection
    cfg = cfg_cab(bid)
    cid = cfg["id"]
    root = collection_root or get_collection(cid)
    cols = {k: get_collection(f"{cid}_{k}", root) for k in ("Shell", "Details", "Interior", "Skirt", "Roof")}
    out = {k: [] for k in cols}
    r = rng(cfg["seed"])
    w, d = cfg["w"], cfg["d"]
    if cfg.get("veranda"):
        cfg["front_y"] = -d / 2 + cfg["veranda"]
    yf = cfg.get("front_y", -d / 2)
    shell, det, inter, roof, sk = MB(), MB(), MB(), MB(), MB()
    t = WALL_T[cfg["siding"]]
    z0 = cfg["z0"]
    fh = cfg["floor_h"]
    nl = cfg["levels"]
    z_crown = z0 + nl * fh
    stats = {}
    # ---------------- base ----------------
    if cfg["base"] == "piers":
        for x in (-w / 2 + 0.15, -w / 2 + w / 3, w / 2 - w / 3, w / 2 - 0.15):
            for y in (yf + 0.15, 0.0, d / 2 - 0.15):
                shell.box((x - 0.18, y - 0.18, -0.1), (x + 0.18, y + 0.18, z0 - 0.25), "concrete", bevel=0.02, seg=2)
        for y in (yf + 0.15, 0.0, d / 2 - 0.15):                                   # durmientes
            shell.box((-w / 2, y - 0.08, z0 - 0.25), (w / 2, y + 0.08, z0 - 0.03), "wood_dark", bevel=0.006, seg=1)
    elif cfg["base"] == "stilts":
        xs = [-w / 2 + 0.12, -w / 6, w / 6, w / 2 - 0.12]
        ys = [-d / 2 + 0.12, 0.0, d / 2 - 0.12]
        for x in xs:
            for y in ys:
                tilt = float(r.uniform(-0.6, 0.6))
                shell.box((x - 0.3, y - 0.3, -0.15), (x + 0.3, y + 0.3, 0.25), "concrete", bevel=0.03, seg=2)            # dado
                M = T(x, y, 0.25) @ Matrix.Rotation(math.radians(tilt), 4, "X")
                shell.box((-0.09, -0.09, 0.0), (0.09, 0.09, z0 - 0.25 - 0.25), "wood_dark", bevel=0.008, seg=1, m=M)
        for y in ys:                                                               # vigas madre
            shell.box((-w / 2, y - 0.1, z0 - 0.5), (w / 2, y + 0.1, z0 - 0.25), "wood_dark", bevel=0.008, seg=1)
        for i in range(len(xs) - 1):                                               # cruces de San Andrés
            for y in (ys[0], ys[-1]):
                for (a, b) in (((xs[i], 0.35), (xs[i + 1], z0 - 0.6)), ((xs[i], z0 - 0.6), (xs[i + 1], 0.35))):
                    p0 = Vector((a[0], y + (0.12 if y < 0 else -0.12), a[1]))
                    p1 = Vector((b[0], y + (0.12 if y < 0 else -0.12), b[1]))
                    _plank(shell, p0, p1, 0.12, 0.04)
        for j in range(len(ys) - 1):
            for x in (xs[0], xs[-1]):
                p0 = Vector((x + (0.12 if x < 0 else -0.12), ys[j], 0.35))
                p1 = Vector((x + (0.12 if x < 0 else -0.12), ys[j + 1], z0 - 0.6))
                _plank(shell, p0, p1, 0.12, 0.04, axis="x")
    else:                                                                          # losa
        shell.box((-w / 2 - 0.05, yf - 0.05, -0.1), (w / 2 + 0.05, d / 2 + 0.05, z0), "concrete", bevel=0.02, seg=2)
    # ---------------- plataforma de PB (vigas + duela) ----------------
    if cfg["base"] != "slab":
        joists(shell, -w / 2 + t, w / 2 - t, yf + t, d / 2 - t, z0 - 0.03, mat="wood_dark")
    st = cfg.get("stair")
    sw, going = 0.85, 0.24
    hole = None
    if st and nl > 1:
        N = max(14, int(round(fh / 0.18)))
        run = (N - 1) * going
        y_st = d / 2 - t - sw - 0.02
        hole = (st["x"] + 0.6, st["x"] + run + 0.05, y_st - 0.05, d / 2 - t)
    boards_floor(inter, -w / 2 + t, w / 2 - t, yf + t, d / 2 - t, z0, r, missing=0.03)
    # ---------------- muros ----------------
    P = []
    spec = SPECS[bid]
    for lv in range(nl):
        zl = z0 + lv * fh
        H = fh
        kind = cfg.get("ground", cfg["siding"]) if lv == 0 else cfg["siding"]
        tk = WALL_T[kind]
        for side in ("front", "back", "west", "east"):
            M, L = wall_m(cfg, side, zl, t)
            ops = place_ops(L, H, spec.get((side, lv), []))
            shell.join(siding(kind, L, H, int(r.integers(1e6)), ops), M)
            P.append(dict(side=side, level=lv, m=M, L=L, H=H, ops=ops, t=tk))
        if lv > 0 or cfg.get("ground"):
            # cinta de entrepiso (tabla horizontal) sobre la junta de niveles
            if lv > 0:
                for (a, b) in (((-w / 2 - 0.03, yf - 0.035), (w / 2 + 0.03, yf - 0.005)), ((-w / 2 - 0.03, d / 2 + 0.005), (w / 2 + 0.03, d / 2 + 0.035)),
                               ((-w / 2 - 0.035, yf), (-w / 2 - 0.005, d / 2)), ((w / 2 + 0.005, yf), (w / 2 + 0.035, d / 2))):
                    shell.box((a[0], a[1], zl - 0.12), (b[0], b[1], zl + 0.06), "wood_dark" if bid == "CAB_1_tablones" else "wood_grey", bevel=0.005, seg=1)
    # ---------------- esquineros (y sillares en la PB de ladrillo) ----------------
    # los testeros van entre las caras interiores de frente y fondo: sin esquinero quedaría una rendija por la que se ve el interior
    trim_mat = "wood_dark" if bid == "CAB_1_tablones" else "wood_grey"
    for sx in (-1, 1):
        for (yc, sy) in ((yf, -1), (d / 2, 1)):
            xo = sx * w / 2
            for lv in range(nl):
                zl, zh = z0 + lv * fh, z0 + (lv + 1) * fh
                if lv == 0 and cfg.get("ground") == "brick":
                    k = 0
                    z = zl
                    while z < zh - 0.05:                                  # sillares alternos de 0,28 de alto
                        hq = min(0.28, zh - z)
                        lq = 0.42 if k % 2 == 0 else 0.26
                        shell.box((min(xo, xo + sx * 0.035), min(yc, yc - sy * lq), z + 0.005),
                                  (max(xo, xo + sx * 0.035), max(yc, yc - sy * lq), z + hq - 0.005), "concrete", bevel=0.012, seg=1)
                        lq2 = 0.26 if k % 2 == 0 else 0.42
                        shell.box((min(xo, xo - sx * lq2), min(yc, yc + sy * 0.035), z + 0.005),
                                  (max(xo, xo - sx * lq2), max(yc, yc + sy * 0.035), z + hq - 0.005), "concrete", bevel=0.012, seg=1)
                        z += 0.28
                        k += 1
                    continue
                # tabla en la cara del testero (cubre el canto del muro de frente/fondo) y tabla en la cara de frente/fondo
                shell.box((min(xo, xo + sx * 0.026), min(yc + sy * 0.026, yc - sy * (t + 0.12)), zl),
                          (max(xo, xo + sx * 0.026), max(yc + sy * 0.026, yc - sy * (t + 0.12)), zh), trim_mat, bevel=0.004, seg=1)
                shell.box((min(xo + sx * 0.026, xo - sx * 0.15), min(yc, yc + sy * 0.026), zl),
                          (max(xo + sx * 0.026, xo - sx * 0.15), max(yc, yc + sy * 0.026), zh), trim_mat, bevel=0.004, seg=1)
    # ---------------- entrepiso ----------------
    if nl > 1:
        z1 = z0 + fh
        joists(inter, -w / 2 + t, w / 2 - t, yf + t, d / 2 - t, z1 - 0.03, skip=[hole] if hole else [])
        boards_floor(inter, -w / 2 + t, w / 2 - t, yf + t, d / 2 - t, z1, r, holes=[hole] if hole else [], missing=0.06)
    if cfg.get("loft"):                                                            # tapanco sobre la mitad trasera
        zl = z0 + fh
        joists(inter, -w / 2 + t, w / 2 - t, 0.2, d / 2 - t, zl - 0.03)
        boards_floor(inter, -w / 2 + t, w / 2 - t, 0.2, d / 2 - t, zl, r, missing=0.08)
        det.join(circ.railing("wood", w - 2 * t - 0.2, h=0.9, seed=cfg["seed"] + 3, missing=0.15), T(-w / 2 + t + 0.1, 0.25, zl))
    # ---------------- escalera interior ----------------
    if hole:
        s = circ.stair_straight(width=sw, rise_total=fh, seed=cfg["seed"] + 1, kind="wood", going=going, broken=0.08, rail="wood",
                                rail_side="left")
        inter.join(s, T(st["x"], d / 2 - t - sw - 0.02, z0))
        stats["stair_N"] = getattr(s, "meta", {}).get("N")
    if cfg.get("loft"):                                                            # escalera de mano al tapanco
        lad = MB()
        for sx in (-0.22, 0.22):
            lad.box((sx - 0.025, -0.02, 0.0), (sx + 0.025, 0.02, fh + 0.9), "wood")
        for k in range(1, 11):
            lad.box((-0.22, -0.015, k * 0.27), (0.22, 0.015, k * 0.27 + 0.035), "wood")
        inter.join(lad, T(w / 2 - t - 0.6, 0.05, z0) @ Matrix.Rotation(math.radians(-14), 4, "X"))
    # ---------------- divisiones ----------------
    idoors = []
    for lv in range(nl):
        zl = z0 + lv * fh
        Hp = fh - 0.05
        xs_ = cfg["split_x"]
        partition_wood(inter, (xs_, yf + t), (xs_, d / 2 - t), zl, Hp, doors=[(-0.6 if lv == 0 else 2.4, 0.85)], out=idoors)
        if lv == 0:
            partition_wood(inter, (xs_, 0.9), (w / 2 - t, 0.9), zl, Hp, doors=[(xs_ + 1.0, 0.8)], out=idoors)
        elif hole:
            partition_wood(inter, (-w / 2 + t, hole[2] - 0.15), (xs_, hole[2] - 0.15), zl, Hp, doors=[(hole[1] + 0.6, 0.85)], out=idoors)
    if cfg.get("loft"):
        pass
    n_id = 0
    for dd in idoors:
        if r.random() < 0.35:
            inter.join(op.door("plank", dd["w"], dd["h"], dd["t"], seed=int(r.integers(1e6)), open_angle=max(80.0, float(r.uniform(0, 90)))),
                       dd["m"] @ T(dd["u0"], 0, 0))
            n_id += 1
    stats["interior_doors"] = n_id
    # ---------------- cubierta ----------------
    D = d                                   # la cubierta abarca toda la planta (en CAB_2 también la veranda)
    yc = 0.0
    seed = cfg["seed"] + 404
    P_, O_ = cfg["pitch"], cfg["ovh"]
    top = lambda x, y: rf.roof_top("gable", w, D, P_, O_, x=x, y=y - yc)  # noqa: E731
    cover = "boards" if cfg["roof"] == "boards" else "sheet"
    spot = None
    if cfg.get("torn"):
        spot = rf.damage_spot("gable", w, D, P_, O_, seed=seed, damage=0.7)
        spot = (w / 2 - 1.6, -abs(spot[1]), spot[2])                                  # junto al hastial este, vertiente delantera
    fr = rf.roof_frame("gable", w, D, P_, O_, seed=seed, cover=cover, tails=cfg["roof"] != "boards", damage=0.7 if spot else 0.0, spot=spot)
    if cfg["roof"] == "boards":
        cv = rf.board_roof_stepped(w, D, P_, O_, seed=seed, missing=0.04)
    else:
        cv = rf.corrugated_roof(w, D, P_, O_, seed=seed, light=cfg["roof"] == "corrugated_light", torn=spot, detail="mid")
    MR = T(0, yc, z_crown)
    if cfg.get("chimney"):
        chx, chy = 2.6, yc + 1.2
        ac.cull_pred(cv, lambda c: abs(c.x - chx) < 0.36 and abs(c.y - (chy - yc)) < 0.32)
        ac.cull_pred(fr, lambda c: abs(c.x - chx) < 0.30 and abs(c.y - (chy - yc)) < 0.26 and c.z > 0.2)
    roof.join(fr, MR)
    roof.join(cv, MR)
    for side in ("west", "east"):
        gable(shell, cfg, side, z_crown, t, r, top)
    # ---------------- detalles propios ----------------
    stats["openings"] = sum(dress_ops(det, p["m"], p["ops"], p["t"], r) for p in P)
    if cfg.get("porch"):
        stats["porch"] = build_porch(cfg, shell, det, roof, r)
    if cfg.get("veranda"):
        stats["veranda"] = build_veranda(cfg, shell, det, r, top, z_crown)
    if cfg.get("stove_pipe"):
        sp = MB()
        x, y = -1.8, yc + 1.1
        zr = z_crown + top(x, y)
        sp.cyl((x, y, z0 + 0.9), (x, y, zr + 1.3), 0.075, seg=12, mat="metal_rust")
        sp.cyl((x, y, zr + 1.3), (x, y, zr + 1.45), 0.13, seg=12, mat="metal_rust", r1=0.02)
        sp.cyl((x, y, zr + 0.02), (x, y, zr + 0.14), 0.16, seg=12, mat="metal_rust", r1=0.09)
        det.join(sp)
        ac.cull_pred(roof, lambda c: math.hypot(c.x - x, c.y - y) < 0.1 and c.z > z_crown)
    if cfg.get("chimney"):
        ch = MB()
        chx, chy = 2.6, yc + 1.2
        ztop = z_crown + rf.ridge_height("gable", w, D, P_, O_) + 0.75
        ch.box((chx - 0.3, chy - 0.26, z0), (chx + 0.3, chy + 0.26, ztop), "brick", bevel=0.01, seg=1)
        ch.box((chx - 0.36, chy - 0.32, ztop - 0.2), (chx + 0.36, chy + 0.32, ztop - 0.1), "brick", bevel=0.006, seg=1)
        for k in range(5):                                                         # ladrillos sueltos del remate
            a = float(r.uniform(-0.25, 0.25))
            ch.box((chx + a - 0.12, chy - 0.3, ztop + 0.0), (chx + a + 0.12, chy - 0.18, ztop + 0.06), "brick", bevel=0.004, seg=1) if k < 2 else None
        det.join(ch)
    if cfg.get("cistern"):
        tk = MB()
        tk.box((-1.2, 0.2, 0.25), (0.6, 1.6, 1.55), "metal_rust", bevel=0.02, seg=2)
        for k in range(5):
            x = -1.2 + 0.36 * k + 0.18
            tk.box((x - 0.02, 0.18, 0.27), (x + 0.02, 1.62, 1.53), "metal_rust")
        tk.cyl((0.4, 0.2, 0.5), (0.4, -0.25, 0.5), 0.04, seg=8, mat="metal_rust")
        det.join(tk)
    if cfg.get("gutter"):
        stats["gutters"] = build_gutters(cfg, roof, det, top, z_crown, yf, yc, D)
    if bid == "CAB_1_tablones":
        det.join(barrel(int(r.integers(1e6))), T(1.6, yf - 0.55, 0.0))
        det.join(woodpile(int(r.integers(1e6)), 2.4, 1.0), T(2.8, yf - 0.9, 0.0))
    # ---------------- base de arena y hierba ----------------
    acfg = dict(id=cid, xs=[-w / 2, w / 2], ys=[yf if not cfg.get("veranda") else -d / 2, d / 2], seed=cfg["seed"],
                footprint=[(-w / 2, w / 2, (yf if not cfg.get("veranda") else -d / 2), d / 2)])
    if cfg.get("porch") and cfg["porch"]["side"] == "west":
        acfg["footprint"].append((-w / 2 - cfg["porch"]["depth"], -w / 2, yf, d / 2))
    import apt_builder as ab
    if cfg["base"] == "stilts":
        acfg["footprint"] = [(-w / 2 + 0.12 + dx - 0.3, -w / 2 + 0.12 + dx + 0.3, y - 0.3, y + 0.3) for dx in (0, w / 3 - 0.12, 2 * w / 3 - 0.12, w - 0.24)
                             for y in (-d / 2 + 0.12, 0.0, d / 2 - 0.12)]
    stats["tufts"] = ab.build_skirt(acfg, sk, margin=3.0, keep_clear=((-1.0, -d / 2 - 3.0, 1.0, -d / 2),), inset=0.05)
    for nm, mb in (("Shell", shell), ("Details", det), ("Interior", inter), ("Roof", roof), ("Skirt", sk)):
        if len(mb.bm.faces):
            out[nm].append(mb.finish(f"{cid}_{nm}", cols[nm], uv_size=2.0, merge=0))
    out["stats"] = stats
    out["cfg"] = cfg
    out["placed"] = [dict(p, side=p["side"], level=p["level"]) for p in P]
    return out


def _plank(mb, p0, p1, wdt, th, axis="y"):
    """Tablón recto de p0 a p1 (sección wdt x th), con la cara ancha perpendicular a `axis`."""
    d = (p1 - p0)
    L = d.length
    z = d.normalized()
    n = Vector((0, 1, 0)) if axis == "y" else Vector((1, 0, 0))
    x = n.cross(z).normalized()
    y = z.cross(x)
    M = Matrix(((x.x, y.x, z.x, p0.x), (x.y, y.y, z.y, p0.y), (x.z, y.z, z.z, p0.z), (0, 0, 0, 1)))
    mb.box((-wdt / 2, -th / 2, 0.0), (wdt / 2, th / 2, L), "wood_grey", bevel=0.004, seg=1, m=M)


def barrel(seed):
    mb = MB()
    mb.cyl((0, 0, 0), (0, 0, 0.88), 0.29, seg=16, mat="wood_dark")
    for z in (0.08, 0.3, 0.58, 0.8):
        mb.cyl((0, 0, z), (0, 0, z + 0.04), 0.302, seg=16, mat="metal_rust")
    return mb


def woodpile(seed, L, H):
    r = rng(seed)
    mb = MB()
    z = 0.0
    row = 0
    while z < H:
        x = 0.0 + (0.06 if row % 2 else 0.0)
        while x < L - 0.12:
            rad = float(r.uniform(0.05, 0.075))
            ln = float(r.uniform(0.45, 0.6))
            mb.cyl((x + rad, -ln / 2, z + rad), (x + rad, ln / 2, z + rad), rad, seg=6, mat="wood")
            x += 2 * rad + 0.005
        z += 0.12
        row += 1
    return mb


def build_porch(cfg, shell, det, roof, r):
    """Porche: deck de duela sobre dados, postes, viga, barandal de madera y cubierta de un agua (media cubierta del kit)."""
    from kit import circulation as circ
    from kit import roofing as rf
    w, d = cfg["w"], cfg["d"]
    yf = cfg.get("front_y", -d / 2)
    pc = cfg["porch"]
    dep = pc["depth"]
    z0 = cfg["z0"]
    if pc["side"] == "west":
        x0, x1, y0, y1 = -w / 2 - dep, -w / 2, yf + 0.3, d / 2 - 0.3
    else:
        x0, x1, y0, y1 = pc["x0"], pc["x1"], yf - dep, yf
    zdeck = z0 if cfg["base"] != "slab" else 0.45
    boards_floor(shell, x0 + 0.02, x1 - 0.02, y0, y1, zdeck, r, missing=0.08, mat="wood_grey")
    joists(shell, x0 + 0.02, x1 - 0.02, y0, y1, zdeck - 0.03, step=0.6, h=0.15)
    zb = cfg["z0"] + cfg["floor_h"] - 0.35 if cfg["levels"] > 1 else cfg["z0"] + cfg["floor_h"] - 0.2
    posts = []
    if pc["side"] == "west":
        for y in (y0 + 0.1, (y0 + y1) / 2, y1 - 0.1):
            posts.append((x0 + 0.1, y))
    else:
        for x in (x0 + 0.1, (x0 + x1) / 2, x1 - 0.1):
            posts.append((x, y0 + 0.1))
    zpost = zb - (dep - 0.1) * math.tan(math.radians(18))
    for (x, y) in posts:
        shell.box((x - 0.07, y - 0.07, 0.0), (x + 0.07, y + 0.07, zpost), "wood_grey", bevel=0.006, seg=1)
        shell.box((x - 0.15, y - 0.15, -0.05), (x + 0.15, y + 0.15, 0.12), "concrete", bevel=0.01, seg=1)
    if pc["side"] == "west":
        shell.box((x0 + 0.02, y0, zpost), (x0 + 0.18, y1, zpost + 0.16), "wood_grey", bevel=0.006, seg=1)
        ac.rail_along(det, "wood", (x0 + 0.08, y0 + 0.2), (x0 + 0.08, y1 - 1.4), zdeck, "-x", seed=cfg["seed"] + 21, bend=0.2, missing=0.2)
    else:
        shell.box((x0, y0 + 0.02, zpost), (x1, y0 + 0.18, zpost + 0.16), "wood_grey", bevel=0.006, seg=1)
        det.join(circ.railing("wood", (x1 - x0) / 2 - 0.7, h=0.9, seed=cfg["seed"] + 21, missing=0.15), T(x0 + 0.15, y0 + 0.08, zdeck))
        det.join(circ.railing("wood", (x1 - x0) / 2 - 0.7, h=0.9, seed=cfg["seed"] + 22, missing=0.1, bend=0.2),
                 T(x1 - 0.15 - ((x1 - x0) / 2 - 0.7), y0 + 0.08, zdeck))
        st = circ.stair_straight(width=1.2, rise_total=zdeck, seed=cfg["seed"] + 23, kind="wood", going=0.28, broken=0.15)
        run = (st.meta["N"] - 1) * 0.28 if hasattr(st, "meta") and "N" in st.meta else 0.56
        det.join(st, T((x0 + x1) / 2 + 0.6, y0 - run, 0.0) @ RZ(90))
    # cubierta de un agua: media cubierta a dos aguas del kit (cumbrera contra el muro) + su estructura
    pitch = 18.0
    if pc["side"] == "west":
        Lr, depth = (y1 - y0) + 0.4, dep
        frame = rf.roof_frame("gable", Lr, 2 * depth, pitch, 0.35, seed=cfg["seed"] + 30, cover="sheet", tails=True, ties=False, blocking=False)
        sheet = rf.corrugated_roof(Lr, 2 * depth, pitch, 0.35, seed=cfg["seed"] + 30, detail="low")
        for mb in (frame, sheet):
            ac.cull_pred(mb, lambda c: c.y > 0.0)
        M = T(-w / 2, (y0 + y1) / 2, zpost + 0.16) @ RZ(-90)
    else:
        Lr, depth = (x1 - x0) + 0.4, dep
        frame = rf.roof_frame("gable", Lr, 2 * depth, pitch, 0.35, seed=cfg["seed"] + 30, cover="boards", tails=False, ties=False, blocking=False)
        sheet = rf.board_roof_stepped(Lr, 2 * depth, pitch, 0.35, seed=cfg["seed"] + 30)
        for mb in (frame, sheet):
            ac.cull_pred(mb, lambda c: c.y > 0.0)
        M = T((x0 + x1) / 2, yf, zpost + 0.16)
    roof.join(frame, M)
    roof.join(sheet, M)
    return dict(posts=len(posts))


def build_veranda(cfg, shell, det, r, top, z_crown):
    """Veranda bajo el faldón delantero (CAB_2): deck, postes hasta la viga de alero, barandal y escalera exterior a la arena."""
    from kit import circulation as circ
    w, d = cfg["w"], cfg["d"]
    yf = cfg["front_y"]
    z0 = cfg["z0"]
    y0 = -d / 2
    boards_floor(shell, -w / 2, w / 2, y0 + 0.02, yf, z0, r, missing=0.07, mat="wood_grey")
    joists(shell, -w / 2 + 0.05, w / 2 - 0.05, y0 + 0.02, yf, z0 - 0.03, step=0.5, h=0.18)
    xs = [-w / 2 + 0.08, -w / 6, w / 6, w / 2 - 0.08]
    for x in xs:
        shell.box((x - 0.06, y0 + 0.02, z0), (x + 0.06, y0 + 0.14, z_crown + 0.02), "wood_grey", bevel=0.006, seg=1)
    # barandal: tramos entre postes (deja libre el arranque de la escalera en el tramo oeste)
    for i in range(len(xs) - 1):
        a, b = xs[i] + 0.06, xs[i + 1] - 0.06
        if i == 0:
            a = a + 1.0
        det.join(circ.railing("wood", b - a, h=0.95, seed=int(r.integers(1e6)), missing=0.12, bend=0.2 if i == 2 else 0.0),
                 T(a, y0 + 0.08, z0))
    for sx in (-1, 1):
        x = sx * (w / 2 - 0.04)
        ac.rail_along(det, "wood", (x, y0 + 0.14), (x, yf), z0, "-x" if sx < 0 else "+x", seed=int(r.integers(1e6)), h=0.95, missing=0.1)
    st = circ.stair_straight(width=1.0, rise_total=z0, seed=cfg["seed"] + 23, kind="wood", going=0.26, broken=0.12, rail="wood", rail_side="both")
    run = (st.meta["N"] - 1) * 0.26 if hasattr(st, "meta") and "N" in st.meta else 2.6
    det.join(st, T(xs[0] + 1.06, y0 - run, 0.0) @ RZ(90))
    # el muro delantero (retranqueado) sube hasta los cabios: faja de tabla que cierra el triángulo bajo el faldón
    zt = top(0.0, yf) - 0.18
    if zt > 0.05:
        shell.box((-w / 2, yf, z_crown), (w / 2, yf + 0.03, z_crown + zt), "wood_grey", bevel=0.004, seg=1)
    return dict(posts=len(xs), stair_run=round(run, 2))


def build_gutters(cfg, roof, det, top, z_crown, yf, yc, D):
    from kit import circulation as circ
    w, d = cfg["w"], cfg["d"]
    O_ = cfg["ovh"]
    ey = D / 2 + O_
    ex = w / 2 + min(O_, 0.45)
    ze = top(0.0, yc - ey + 0.01) - 0.06
    off = 0.0865
    g = circ.gutter([Vector((-ex + 0.05, yc - ey - off, ze)), Vector((ex - 0.05, yc - ey - off, ze))], seed=cfg["seed"] + 50, outlets=[0.6],
                    dirt=True, hanger_step=0.9, fault="bent")
    roof.join(g, T(0, 0, z_crown))
    n = 0
    for tpt in (g.meta.get("outlets", []) if hasattr(g, "meta") else []):
        ac.downpipe_on(det, Vector(tpt) + Vector((0, 0, z_crown)), "front", yf, seed=cfg["seed"] + 60)
        n += 1
    return n


# vanos por muro y nivel: (tipo, u_centro, ancho, alto, antepecho) — u medida mirando el muro desde afuera
SPECS = {
    "CAB_1_tablones": {
        ("front", 0): [("win", 3.4, 0.8, 1.1, 0.9), ("door", 5.6, 0.95, 2.05, 0.0), ("win", 7.6, 0.6, 0.9, 1.0)],
        ("front", 1): [("win", 1.6, 0.6, 0.9, 1.0), ("win", 3.4, 0.8, 1.1, 0.9), ("win", 7.0, 0.8, 1.1, 0.9)],
        ("back", 0): [("win", 2.0, 0.8, 1.1, 0.9), ("door", 6.4, 0.9, 2.0, 0.0)],
        ("back", 1): [("win", 2.5, 0.8, 1.1, 0.9), ("win", 6.5, 0.8, 1.1, 0.9)],
        ("west", 0): [("door", 2.9, 0.9, 2.0, 0.0), ("win", 4.5, 0.7, 1.0, 1.0)],
        ("west", 1): [("win", 2.9, 0.7, 1.0, 1.0)],
        ("east", 0): [("win", 2.9, 0.8, 1.1, 0.9)],
        ("east", 1): [("win", 2.9, 0.8, 1.1, 0.9)],
    },
    "CAB_2_pilotes": {
        ("front", 0): [("win", 1.2, 0.8, 1.1, 0.9), ("door", 2.6, 0.9, 2.0, 0.0), ("door", 4.4, 0.9, 2.0, 0.0), ("win", 5.8, 0.8, 1.1, 0.9)],
        ("back", 0): [("win", 1.8, 0.8, 1.1, 0.9), ("win", 3.6, 0.7, 1.0, 1.0), ("win", 5.4, 0.8, 1.1, 0.9)],   # sin puerta: atrás no hay escalera
        ("west", 0): [("win", 2.4, 0.8, 1.1, 0.9)],
        ("east", 0): [("win", 1.4, 0.8, 1.1, 0.9), ("win", 3.4, 0.8, 1.1, 0.9)],
    },
    "CAB_3_ladrillo": {
        ("front", 0): [("win", 1.2, 0.8, 1.3, 0.85), ("win", 4.6, 0.8, 1.3, 0.85), ("door", 5.9, 0.95, 2.1, 0.0), ("win", 7.2, 0.7, 1.2, 0.9)],
        ("front", 1): [("win", 1.0, 0.75, 1.2, 0.85), ("win", 2.8, 0.75, 1.2, 0.85), ("win", 4.9, 0.75, 1.2, 0.85), ("win", 7.0, 0.75, 1.2, 0.85)],
        ("back", 0): [("win", 1.6, 0.8, 1.2, 0.9), ("door", 4.0, 0.9, 2.05, 0.0), ("win", 6.4, 0.8, 1.2, 0.9)],
        ("back", 1): [("win", 2.0, 0.75, 1.2, 0.85), ("win", 6.0, 0.75, 1.2, 0.85)],
        ("west", 0): [("win", 3.2, 0.8, 1.2, 0.9)],
        ("west", 1): [("win", 2.0, 0.7, 1.1, 0.9), ("win", 4.4, 0.7, 1.1, 0.9)],
        ("east", 0): [("win", 2.0, 0.8, 1.2, 0.9)],
        ("east", 1): [("win", 3.2, 0.75, 1.2, 0.85)],
    },
}
