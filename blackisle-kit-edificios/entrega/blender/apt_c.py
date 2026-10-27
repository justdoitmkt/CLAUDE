"""apt_c.py — APT_C_3p: bloque en L de PB + 2 pisos con techos a dos aguas y limahoyas (concepto hero 18c151f9 / trasera c3ae54f0).

Malla xs = -6,0 | -2,4 | 1,2 | 4,2 | 6,0 · ys = -6,0 | -3,0 | -0,6 | 3,0 | 6,0
- Ala A (norte, cumbrera en X): x -6,0..6,0 · y -0,6..6,0 (12,0 x 6,6).
- Ala B (sur, cumbrera en Y): x -2,4..4,2 · y -6,0..-0,6 (6,6 x 5,4); deja una esquina entrante al SO (la del concepto) y un
  remetimiento chico al SE, así las dos limahoyas nacen en esquinas entrantes reales.
- Núcleo INTERIOR en la junta (crujía x -2,4..1,2 · y -0,6..3,0): escalera en U con tramos hacia +Y; vestíbulo al sur (dentro del
  ala B) y pasillo al oeste del núcleo hasta el vestíbulo trasero.
- PB: acceso principal en la cara oeste del ala B, bajo los balcones en L de la esquina entrante (que hacen de marquesina, con
  dos postes); puerta trasera en la fachada norte. Locales al oeste y al sur (cortina metálica), cuartos al este.
- Pisos 1–2: 3 departamentos (oeste, norte en L y sur) con estancia, recámaras, cocina y baño; balcones en L en la esquina.
- Hastiales de mampostería en los extremos oeste y este del ala A y en el sur del ala B; chimenea de ladrillo en el ala A.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402,F401
import bmesh  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import apt_builder as ab  # noqa: E402
import apt_common as ac  # noqa: E402
from apt_builder import BEAM_W, COL, COL_CORNER, GROUND, INFILL, RECESS, SLAB, _T, level_z, partition  # noqa: E402
from kit.common import MB, rng  # noqa: E402

PITCH, OVH = 30.0, 0.6
STAIR_W, STAIR_LANDING, STAIR_GOING = 1.0, 1.0, 0.27
EX = BEAM_W / 2
ac.OPENING.setdefault("lobby_door", (1.4, 2.3, 0.0))


def cfg_apt_c():
    xs = [-6.0, -2.4, 1.2, 4.2, 6.0]
    ys = [-6.0, -3.0, -0.6, 3.0, 6.0]
    h = [3.2, 2.9, 2.9]
    cells = {(i, j) for i in range(4) for j in (2, 3)} | {(i, j) for i in (1, 2) for j in (0, 1)}
    corners = {(0, 2), (0, 4), (4, 2), (4, 4), (1, 0), (3, 0)}
    # núcleo: crujía (1,2) libre x -2,225..1,025 · y -0,425..2,825; escalera pegada al este, termina contra la viga norte
    L = 8 * STAIR_GOING + STAIR_LANDING + 0.003
    sw = 2 * STAIR_W + 0.10
    stair = dict(x0=1.025 - sw, y0=2.825 - L, w=sw, l=L, origin=(1.025, 2.825 - L))
    rects = [(-6.0, 6.0, -0.6, 6.0), (-2.4, 4.2, -6.0, -0.6, (EX, EX, EX, -EX))]
    return dict(id="APT_C_3p", xs=xs, ys=ys, h=h, cells=cells, corner_nodes=corners, stair=stair, seed=37, loggia_depth=0.0,
                lookdev=dict(under="brick", paint_tint=(0.90, 0.89, 0.86)),
                stair_levels={1, 2}, slab_rects=rects)


# ----------------------------------------------------------------------------------------------
# fachadas
# ----------------------------------------------------------------------------------------------
def build_facades(cfg, shell):
    P = []
    pan = lambda *a, **k: ac.panel(cfg, shell, *a, collect=P, **k)  # noqa: E731
    up = (1, 2)
    # frente: ala A (crujías 0 y 3 sobre la línea y = -0,6) y hastial del ala B (línea y = -6,0)
    pan("front", 2, 0, 0, [("window", 0.3), ("window_small", 0.8)], tag="pb")
    pan("front", 2, 3, 0, [("window_small", 0.5)], tag="pb")
    pan("front", 0, 1, 0, [("shutter", 0.5)], tag="pb")
    pan("front", 0, 2, 0, [("window_high", 0.5)], tag="pb")
    for lv in up:
        pan("front", 2, 0, lv, [("window", 0.3), ("door_balcony", 0.8)])
        pan("front", 2, 3, lv, [("window_small", 0.5)])
        pan("front", 0, 1, lv, [("window", 0.5)])
        pan("front", 0, 2, lv, [("window", 0.5)])
    # oeste: testero del ala A (línea x = -6,0) y cara oeste del ala B (x = -2,4) con el acceso
    pan("west", 0, 2, 0, [("window_high", 0.5)], tag="pb")
    pan("west", 0, 3, 0, [("window", 0.5)], tag="pb")
    pan("west", 1, 0, 0, [("window_high", 0.5)], tag="pb")
    pan("west", 1, 1, 0, [("lobby_door", 0.4)], tag="pb")
    for lv in up:
        pan("west", 0, 2, lv, [("window", 0.5)])
        pan("west", 0, 3, lv, [("window_small", 0.5)])
        pan("west", 1, 0, lv, [("window", 0.5)])
        pan("west", 1, 1, lv, [("vent", 0.18), ("door_balcony", 0.74)])
    # este: testero del ala A (x = 6,0) y cara este del ala B (x = 4,2)
    pan("east", 4, 2, 0, [("window_high", 0.5)], tag="pb")
    pan("east", 4, 3, 0, [("window", 0.5)], tag="pb")
    pan("east", 3, 0, 0, [("window_high", 0.5)], tag="pb")
    pan("east", 3, 1, 0, [("door_service", 0.5)], tag="pb")
    for lv in up:
        pan("east", 4, 2, lv, [("window", 0.5)])
        pan("east", 4, 3, lv, [("window", 0.5)])
        pan("east", 3, 0, lv, [("window", 0.5)])
        pan("east", 3, 1, lv, [("window_small", 0.5)])
    # trasera (fracciones desde el ESTE): puerta trasera bajo una pila de ventanas angostas (vestíbulo)
    pan("back", 4, 0, 0, [("window", 0.5)], tag="pb")
    pan("back", 4, 1, 0, [("window_small", 0.3), ("door_service", 0.84)], tag="pb")
    pan("back", 4, 2, 0, [("window", 0.5)], tag="pb")
    pan("back", 4, 3, 0, [("window_small", 0.5)], tag="pb")
    for lv in up:
        pan("back", 4, 0, lv, [("window", 0.5)])
        pan("back", 4, 1, lv, [("window", 0.3), ("window_narrow", 0.84)])
        pan("back", 4, 2, lv, [("window", 0.5)])
        pan("back", 4, 3, lv, [("window_small", 0.5)])
    return P


def gable_wall(mb, origin, udir, inward, profile, t=INFILL, mat="plaster"):
    """Hastial: polígono (u, v) en el plano vertical del muro, extruido `t` hacia `inward`."""
    u, n = Vector(udir).normalized(), Vector(inward).normalized()
    M = Matrix(((u.x, 0, n.x, origin[0]), (u.y, 0, n.y, origin[1]), (0, 1, 0, origin[2]), (0, 0, 0, 1)))
    mb.plate(profile, t, mat, m=M)


def roof_dims(cfg):
    xs, ys = cfg["xs"], cfg["ys"]
    c = COL_CORNER / 2
    A = dict(w=xs[-1] - xs[0] + 2 * c, d=ys[-1] - ys[2] + 2 * c, cx=0.5 * (xs[0] + xs[-1]), cy=0.5 * (ys[2] + ys[-1]))
    yr = A["cy"]                                           # cumbrera del ala A
    y0 = ys[0] - c
    B = dict(w=yr - y0, d=xs[3] - xs[1] + 2 * c, cx=0.5 * (xs[1] + xs[3]), cy=0.5 * (yr + y0))
    return A, B


def top_A(A, x, y):
    from kit import roofing as rf
    return rf.roof_top("gable", A["w"], A["d"], PITCH, OVH, x=x - A["cx"], y=y - A["cy"])


def top_B(B, x, y):
    from kit import roofing as rf
    return rf.roof_top("gable", B["w"], B["d"], PITCH, OVH, x=y - B["cy"], y=-(x - B["cx"]))


def build_gables(cfg, shell):
    """Hastiales oeste y este del ala A y sur del ala B (corona en la losa de azotea, borde superior 18 cm bajo los cabios)."""
    A, B = roof_dims(cfg)
    z0 = level_z(cfg)[-1]
    c = COL_CORNER / 2
    xs, ys = cfg["xs"], cfg["ys"]
    k = COL / 2 - RECESS

    def prof(origin_u, sign, length, f, n=12):
        """[(u, v)]: u de 0 a length a lo largo del muro; f recibe la coordenada absoluta origin_u + sign * u."""
        pts = [(0.0, 0.0)]
        for i in range(n + 1):
            u = length * i / n
            pts.append((u, max(f(origin_u + sign * u) - 0.18, 0.02)))
        pts.append((length, 0.0))
        return pts
    ya0, ya1 = ys[2] - c, ys[-1] + c
    xw = xs[0] - k                                   # testero oeste del ala A: u hacia +Y, espesor hacia +X
    gable_wall(shell, (xw, ya0, z0), (0, 1, 0), (1, 0, 0), prof(ya0, 1, ya1 - ya0, lambda y: top_A(A, xw, y)))
    xe = xs[-1] + k                                  # testero este: u hacia -Y, espesor hacia -X
    gable_wall(shell, (xe, ya1, z0), (0, -1, 0), (-1, 0, 0), prof(ya1, -1, ya1 - ya0, lambda y: top_A(A, xe, y)))
    xb0, xb1 = xs[1] - c, xs[3] + c
    yb = ys[0] - k                                   # hastial sur del ala B: u hacia -X, espesor hacia +Y
    gable_wall(shell, (xb1, yb, z0), (-1, 0, 0), (0, 1, 0), prof(xb1, -1, xb1 - xb0, lambda x: top_B(B, x, yb)))


def build_balconies(cfg, shell, det):
    """Balcones en L en la esquina entrante (pisos 1–2) sobre dos postes; el del piso 1 es la marquesina del acceso."""
    from kit import circulation as circ
    r = rng(cfg["seed"] + 77)
    zl = level_z(cfg)
    ys, xs = cfg["ys"], cfg["xs"]
    fa = ys[2] - (COL / 2 - RECESS)            # cara del relleno sur del ala A (-0,695)
    fb = xs[1] - (COL / 2 - RECESS)            # cara del relleno oeste del ala B (-2,495)
    xa0, d = -5.2, 1.2
    wb = (fa - d) - (ys[1] + 0.2)              # el brazo del ala B baja hasta y ≈ -2,8
    out = []
    for lv in (1, 2):
        z = zl[lv] - 0.15
        sa = circ.balcony_slab(w=fb - xa0, d=d, t=0.15, seed=int(r.integers(1e6)), spalled=0.4)
        shell.join(sa, _T(xa0, fa, z))
        sb = circ.balcony_slab(w=wb, d=d, t=0.15, seed=int(r.integers(1e6)), spalled=0.4)
        shell.join(sb, _T(fb, fa - d - 0.002, z) @ ac._rot_z(-90))
        zt = zl[lv]
        ac.rail_along(det, "tube_metal", (xa0, fa - d + 0.07), (fb - d, fa - d + 0.07), zt, "-y", seed=int(r.integers(1e6)),
                      bend=0.1 if lv == 2 else 0.0, missing=0.12)
        ac.rail_along(det, "tube_metal", (xa0 + 0.07, fa - d), (xa0 + 0.07, fa), zt, "-x", seed=int(r.integers(1e6)), missing=0.1)
        ac.rail_along(det, "tube_metal", (fb - d + 0.07, fa - d - wb), (fb - d + 0.07, fa - d), zt, "-x", seed=int(r.integers(1e6)),
                      missing=0.1)
        ac.rail_along(det, "tube_metal", (fb - d, fa - d - wb + 0.07), (fb, fa - d - wb + 0.07), zt, "-y", seed=int(r.integers(1e6)),
                      missing=0.15)
        out.append(dict(lv=lv, z=zt))
    # postes de concreto en las esquinas exteriores del balcón (de la losa de desplante al balcón del piso 2)
    for (x, y) in ((xa0 + 0.22, fa - d + 0.22), (fb - d + 0.22, fa - d - wb + 0.22)):
        shell.box((x - 0.11, y - 0.11, 0.0), (x + 0.11, y + 0.11, zl[2] - 0.15), "concrete", bevel=0.012, seg=2)
    return dict(xa0=xa0, d=d, fa=fa, fb=fb, wb=wb)


# ----------------------------------------------------------------------------------------------
# interior
# ----------------------------------------------------------------------------------------------
def build_interior(cfg, mb, out):
    zl = level_z(cfg)
    st = cfg["stair"]
    k = COL / 2 - RECESS
    xa_in0 = cfg["xs"][0] - k + INFILL         # cara interior del testero oeste del ala A
    xa_in1 = cfg["xs"][-1] + k - INFILL
    ya_in1 = cfg["ys"][-1] + k - INFILL
    ya_in0 = cfg["ys"][2] - k + INFILL         # cara interior del muro sur del ala A
    xb_in0 = cfg["xs"][1] - k + INFILL
    xb_in1 = cfg["xs"][3] + k - INFILL
    yb_in0 = cfg["ys"][0] - k + INFILL
    xsw = st["x0"] - 0.075                     # muro oeste del núcleo
    for lv in range(len(cfg["h"])):
        z0 = zl[lv]
        H = cfg["h"][lv] - SLAB
        partition(mb, (xsw, st["y0"]), (xsw, 2.825), z0, H)                               # núcleo | pasillo
        partition(mb, (1.2, -0.6), (1.2, 3.0), z0, H, t=0.15)                             # núcleo | ala A este
        if lv == 0:
            partition(mb, (-2.4, ya_in0), (-2.4, ya_in1), z0, H, t=0.15)                  # local oeste | pasillo
            partition(mb, (xb_in0, -2.4), (1.2, -2.4), z0, H, t=0.15)                     # vestíbulo | local sur
            partition(mb, (1.2, -2.4), (1.2, -0.6), z0, H, t=0.15)
            partition(mb, (1.275, -3.0), (xb_in1, -3.0), z0, H)                           # local sur | cuarto este
            partition(mb, (1.2, 3.0), (1.2, ya_in1), z0, H, t=0.15)                       # vestíbulo trasero | cuartos este
            partition(mb, (1.275, 1.2), (xa_in1, 1.2), z0, H, doors=[(3.0, 0.9)], out=out)
            continue
        # vestíbulo de piso (al sur del núcleo, dentro del ala B) y pasillo al oeste del núcleo
        partition(mb, (xb_in0, -1.8), (1.2, -1.8), z0, H, doors=[(0.3, 0.9)], out=out, tag="entry")      # → depto sur
        partition(mb, (-2.4, ya_in0), (-2.4, 3.0), z0, H, t=0.15, doors=[(1.5, 0.9)], out=out, tag="entry")  # → depto oeste
        partition(mb, (-2.4, 3.0), (xsw + 0.05, 3.0), z0, H, doors=[(-1.7, 0.9)], out=out, tag="entry")      # → depto norte
        partition(mb, (-2.4, 3.0), (-2.4, ya_in1), z0, H, t=0.15)
        # depto oeste (ala A, crujía 0)
        partition(mb, (xa_in0, 2.2), (-2.475, 2.2), z0, H, doors=[(-3.4, 0.8)], out=out)
        partition(mb, (xa_in0, 3.8), (-2.475, 3.8), z0, H, doors=[(-3.4, 0.8)], out=out)
        partition(mb, (-4.4, 2.2), (-4.4, 3.8), z0, H, doors=[(3.0, 0.7)], out=out)
        # depto norte (crujía (1,3) + ala A este)
        partition(mb, (1.2, 3.0), (1.2, ya_in1), z0, H, doors=[(4.5, 0.8)], out=out)
        partition(mb, (1.275, 3.0), (xa_in1, 3.0), z0, H, doors=[(3.0, 0.8)], out=out)
        partition(mb, (4.2, -0.545), (4.2, 3.0), z0, H, doors=[(1.2, 0.7)], out=out)
        # depto sur (ala B)
        partition(mb, (xb_in0, -3.6), (xb_in1, -3.6), z0, H, doors=[(-0.6, 0.8), (2.6, 0.8)], out=out)
        partition(mb, (1.2, yb_in0), (1.2, -1.8), z0, H, t=0.15, doors=[(-2.7, 0.8)], out=out)
        partition(mb, (1.275, -1.8), (xb_in1, -1.8), z0, H, doors=[(2.0, 0.7)], out=out)
    return mb


# ----------------------------------------------------------------------------------------------
# techo
# ----------------------------------------------------------------------------------------------
def build_roof(cfg, roof, det):
    from kit import circulation as circ
    from kit import roofing as rf
    A, B = roof_dims(cfg)
    z0 = level_z(cfg)[-1]
    seed = cfg["seed"] + 404
    spA = rf.damage_spot("gable", A["w"], A["d"], PITCH, OVH, seed=seed, damage=0.45)
    spA = (spA[0], abs(spA[1]), spA[2])                    # el hueco en la vertiente norte (no lo tapa el ala B)
    spB = rf.damage_spot("gable", B["w"], B["d"], PITCH, OVH, seed=seed + 1, damage=0.4)
    spB = (-abs(spB[0]) * 0.6 - 1.0, spB[1], spB[2])       # hacia el hastial sur, vertiente oeste
    tA, tB = MB(), MB()
    tA.join(rf.roof_frame("gable", A["w"], A["d"], PITCH, OVH, seed=seed, cover="tile", damage=0.45, spot=spA), _T(A["cx"], A["cy"], 0))
    tA.join(rf.barrel_tiles(A["w"], A["d"], "gable", PITCH, OVH, seed=seed, missing=0.04, hole=spA, detail="low"), _T(A["cx"], A["cy"], 0))
    RB = _T(B["cx"], B["cy"], 0) @ ac._rot_z(90)
    tB.join(rf.roof_frame("gable", B["w"], B["d"], PITCH, OVH, seed=seed + 1, cover="tile", damage=0.4, spot=spB), RB)
    tB.join(rf.barrel_tiles(B["w"], B["d"], "gable", PITCH, OVH, seed=seed + 1, missing=0.05, hole=spB, detail="low"), RB)
    # limahoyas: cada cubierta pierde lo que queda bajo la otra (y el ala B todo lo que pasa la cumbrera del ala A)
    yA_eave = A["cy"] - A["d"] / 2 - OVH
    xB0, xB1 = B["cx"] - B["d"] / 2 - OVH, B["cx"] + B["d"] / 2 + OVH
    kB = ac.cull_pred(tB, lambda c: c.y > A["cy"] or (c.y > yA_eave - 0.05 and c.z < top_A(A, c.x, c.y) + 0.04))
    kA = ac.cull_pred(tA, lambda c: xB0 - 0.05 < c.x < xB1 + 0.05 and c.y < A["cy"] and c.z < top_B(B, c.x, c.y) + 0.04)
    # chimenea de ladrillo en la vertiente norte del ala A (las tejas y cabios que ocupa se retiran)
    chx, chy, cw, cd = -4.2, 4.3, 0.62, 0.5
    zr = rf.ridge_height("gable", A["w"], A["d"], PITCH, OVH)
    kC = ac.cull_pred(tA, lambda c: abs(c.x - chx) < cw / 2 + 0.04 and abs(c.y - chy) < cd / 2 + 0.04)
    roof.join(tA, _T(0, 0, z0))
    roof.join(tB, _T(0, 0, z0))
    ch = MB()
    zc = z0 + zr + 0.85
    ch.box((chx - cw / 2, chy - cd / 2, z0), (chx + cw / 2, chy + cd / 2, zc), "brick", bevel=0.01, seg=1)
    for i in range(3):                                     # hiladas salientes de remate
        e = 0.03 * (i + 1) if i < 2 else 0.02
        ch.box((chx - cw / 2 - e, chy - cd / 2 - e, zc - 0.24 + 0.08 * i), (chx + cw / 2 + e, chy + cd / 2 + e, zc - 0.16 + 0.08 * i), "brick",
               bevel=0.006, seg=1)
    ch.box((chx - cw / 2 - 0.08, chy - cd / 2 - 0.08, zc), (chx + cw / 2 + 0.08, chy + cd / 2 + 0.08, zc + 0.06), "concrete", bevel=0.01, seg=1)
    for dx in (-0.14, 0.14):
        ch.cyl((chx + dx, chy, zc + 0.06), (chx + dx, chy, zc + 0.36), 0.075, seg=12, mat="tile", r1=0.06)
    det.join(ch)
    # canalones (solo en aleros) y bajantes
    zeA = rf.roof_top("gable", A["w"], A["d"], PITCH, OVH, x=0.0, y=-(A["d"] / 2 + OVH) + 0.01) - 0.06
    zeB = rf.roof_top("gable", B["w"], B["d"], PITCH, OVH, x=0.0, y=-(B["d"] / 2 + OVH) + 0.01) - 0.06
    off = 0.0865
    yAs, yAn = yA_eave - off, A["cy"] + A["d"] / 2 + OVH + off
    xBw, xBe = xB0 - off, xB1 + off
    yBs = B["cy"] - B["w"] / 2 - 0.4
    gut = [("A_sur", [(A["cx"] - A["w"] / 2 - 0.4, yAs, zeA), (xB0 - 0.15, yAs, zeA)], [-5.6 - (A["cx"] - A["w"] / 2 - 0.4)], "front", ys_face(cfg, "front_A")),
           ("A_norte", [(A["cx"] + A["w"] / 2 + 0.4, yAn, zeA), (A["cx"] - A["w"] / 2 - 0.4, yAn, zeA)], [1.2, A["w"] - 0.4], "back",
            ys_face(cfg, "back")),
           ("B_oeste", [(xBw, yA_eave - 0.15, zeB), (xBw, yBs, zeB)], [(yA_eave - 0.15) - (-5.65)], "west", ys_face(cfg, "west_B")),
           ("B_este", [(xBe, yBs, zeB), (xBe, yA_eave - 0.15, zeB)], [-5.65 - yBs], "east", ys_face(cfg, "east_B"))]
    n = 0
    for i, (nm, path, outs, side, wall) in enumerate(gut):
        g = circ.gutter([Vector(p) for p in path], seed=seed + 20 + i, outlets=outs, dirt=False, hanger_step=1.0,
                        fault="bent" if nm == "B_este" else "none")
        roof.join(g, _T(0, 0, z0))
        for t in (g.meta.get("outlets", []) if hasattr(g, "meta") else []):
            ac.downpipe_on(det, Vector(t) + Vector((0, 0, z0)), side, wall, seed=seed + 40 + n)
            n += 1
    return dict(culled_A=kA, culled_B=kB, culled_chimney=kC, downpipes=n)


def ys_face(cfg, key):
    k = COL / 2 - RECESS
    xs, ys = cfg["xs"], cfg["ys"]
    return {"front_A": ys[2] - k, "back": ys[-1] + k, "west_B": xs[1] - k, "east_B": xs[3] + k}[key]


# ----------------------------------------------------------------------------------------------
# vestido
# ----------------------------------------------------------------------------------------------
def _p(P, side, lv, bay, line=None):
    for q in P:
        if q["side"] == side and q["level"] == lv and q["bay"] == bay and (line is None or q["line"] == line):
            return q
    raise KeyError((side, lv, bay, line))


def dress_services(cfg, P, bal, det, inter, far="low", near="mid"):
    from kit import services as sv
    r = rng(cfg["seed"] + 505)
    zl = level_z(cfg)
    n = {}

    def add(key, mb, M, target=det):
        target.join(mb, M)
        ac.counter(n, key)

    def mid(p, k=0):
        o = p["ops"][k][1]
        return (o[0] + o[1]) / 2
    for side, line, lv, bay, kind, d in (("back", 4, 1, 0, "split_outdoor", far), ("back", 4, 2, 2, "box_old", far),
                                         ("east", 4, 1, 3, "split_outdoor", far), ("west", 0, 2, 2, "split_outdoor", far),
                                         ("front", 0, 1, 2, "split_outdoor", near)):
        p = _p(P, side, lv, bay, line)
        add("ac_" + kind, sv.ac_unit(kind, seed=int(r.integers(1e6)), detail=d), p["m"] @ _T(mid(p), 0, 0.32))
    # tendederos en los balcones, arbotante y medidores junto al acceso, letrero sobre la cortina del local sur
    for lv in (1, 2):
        add("laundry_line", sv.laundry_line(length=2.4, seed=int(r.integers(1e6)), detail=near),
            _T(bal["xa0"] + 0.2, bal["fa"] - 0.55, zl[lv] + 1.95))
    p = _p(P, "west", 0, 1, 1)
    o = p["ops"][0][1]
    add("light_fixture", sv.light_fixture("wall", seed=int(r.integers(1e6)), detail=near), p["m"] @ _T(o[1] + 0.3, 0, o[3] + 0.2))
    p0 = _p(P, "west", 0, 0, 1)
    for i, u in enumerate((p0["L"] * 0.25, p0["L"] * 0.25 + 0.42)):
        add("meter_box", sv.meter_box(seed=int(r.integers(1e6)), open_door=bool(i), detail=near), p0["m"] @ _T(u, 0, 1.2))
    add("conduit", sv.conduit([(p0["L"] * 0.25 - 0.3, 0, 1.75), (p0["L"] * 0.25 - 0.3, 0, p0["H"] - 0.05)], seed=int(r.integers(1e6)),
                              detail=near), p0["m"])
    ps = _p(P, "front", 0, 1, 0)
    add("sign_torn", sv.sign_torn(w=min(2.6, ps["L"] - 0.3), h=0.42, seed=int(r.integers(1e6)), detail=near),
        ps["m"] @ _T(ps["L"] / 2, -0.03, ps["H"] + 0.04))
    # acometida: de la esquina del ala A al poste del balcón
    zc = zl[1] - 0.35
    add("cable_bundle", sv.cable_bundle([(-6.0, cfg["ys"][2] - COL / 2 - 0.01, zc), (bal["xa0"] + 0.12, bal["fa"] - bal["d"] + 0.0, zc - 0.25)],
                                        n=3, sag=0.25, seed=int(r.integers(1e6)), detail=near), Matrix())
    # vestíbulo: buzones y extintor
    add("mailboxes", sv.mailboxes(n=6, seed=int(r.integers(1e6)), detail=near), _T(-0.5, -2.4 + 0.075 + 0.001, zl[0] + 1.05) @ ac._rot_z(180), inter)
    add("extinguisher_cabinet", sv.extinguisher_cabinet(seed=int(r.integers(1e6)), detail=near),
        _T(1.2 - 0.075 - 0.001, -1.2, zl[1] + 1.05) @ ac._rot_z(-90), inter)
    # antena en la cumbrera del ala A y parabólica en el hastial oeste
    from kit import roofing as rf
    A, _ = roof_dims(cfg)
    zr = rf.roof_top("gable", A["w"], A["d"], PITCH, OVH, x=2.0, y=0.0)
    add("tv_antenna", sv.tv_antenna(seed=int(r.integers(1e6)), detail=far), _T(2.0, A["cy"], level_z(cfg)[-1] + zr + 0.05))
    add("satellite_dish", sv.satellite_dish(seed=int(r.integers(1e6)), detail=far),
        _T(cfg["xs"][0] - (COL / 2 - RECESS), 1.4, zl[2] + 1.6) @ ac._rot_z(-90))
    return n


def dress_damage(cfg, shell, det, inter, skirt, detail="low"):
    from kit import damage as dm
    r = rng(cfg["seed"] + 606)
    zl = level_z(cfg)
    n = {}

    def add(key, mb, M, target):
        target.join(mb, M)
        ac.counter(n, key)
    for (x, y, z, rad, tgt) in ((-4.6, -3.2, 0.0, 1.0, skirt), (2.5, -7.4, 0.0, 0.8, skirt), (-1.0, -1.3, zl[0], 0.6, inter),
                                (3.2, 7.4, 0.0, 1.2, skirt)):
        add("rubble_pile", dm.rubble_pile(radius=rad, seed=int(r.integers(1e6)), n=int(rad * 36), detail=detail), _T(x, y, z), tgt)
    for _ in range(18):
        x, y = float(r.uniform(-7.5, 6.5)), float(r.uniform(-8.0, -6.6))
        add("chunk", dm.chunk(size=float(r.uniform(0.1, 0.4)), seed=int(r.integers(1e6)), detail=detail),
            _T(x, y, 0.0) @ ac._rot_z(float(r.uniform(0, 360))), skirt)
    # muro de lindero demolido al norte (varillas de castillos)
    for x in (-5.0, -1.5, 2.0, 5.5):
        add("rebar_nest", dm.rebar_nest(seed=int(r.integers(1e6)), n=int(r.integers(4, 7)), length=float(r.uniform(0.5, 0.9)),
                                        stump=(0.2, 0.2, float(r.uniform(0.3, 0.8))), detail=detail), _T(x, 8.4, 0.0), skirt)
    return n


def build_apt_c(collection_root=None, dress_all=True):
    from kit.common import get_collection
    cfg = cfg_apt_c()
    cid = cfg["id"]
    root = collection_root or get_collection(cid)
    cols = {k: get_collection(f"{cid}_{k}", root) for k in ("Shell", "Details", "Interior", "Skirt", "Roof", "Damage")}
    out = {k: [] for k in cols}
    shell, det, inter, sk = MB(), MB(), MB(), MB()
    ab.build_frame(cfg, shell)
    P = build_facades(cfg, shell)
    build_gables(cfg, shell)
    doors = []
    build_interior(cfg, inter, doors)
    out["placed"] = P
    stats = {}
    if dress_all:
        r = rng(cfg["seed"] + 101)
        stats["openings"] = sum(ac.dress_panel(p, det, inter, r, primary=p["side"] == "front") for p in P)
        stats["interior_doors"] = ab.dress_interior_doors(cfg, doors, inter)
        st = cfg["stair"]
        ac.stair_core(cfg, inter, st["origin"], "+y", STAIR_W, STAIR_LANDING, levels=[0, 1], going=STAIR_GOING, limit=(st["l"], st["w"]))
        ac.rail_along(inter, "tube_metal", (st["origin"][0] - STAIR_W, st["y0"]), (st["origin"][0], st["y0"]), level_z(cfg)[2], "+y",
                      seed=cfg["seed"] + 5, missing=0.15)
        bal = build_balconies(cfg, shell, det)
        roof = MB()
        stats["roof"] = build_roof(cfg, roof, det)
        out["Roof"].append(roof.finish(f"{cid}_Roof", cols["Roof"], uv_size=2.0, merge=0))
        stats["services"] = dress_services(cfg, P, bal, det, inter)
    out["Shell"].append(shell.finish(f"{cid}_Shell", cols["Shell"], uv_size=3.0, merge=0))
    entry = (-5.4, -3.4, -2.4, -0.6)
    rear = (-2.4, 6.0, -0.4, 9.0)
    out["stats_skirt"] = build_skirt_l(cfg, sk, keep_clear=(entry, rear))
    if dress_all:
        dmg = {k: MB() for k in ("Shell", "Details", "Interior")}
        stats["damage"] = dress_damage(cfg, dmg["Shell"], dmg["Details"], dmg["Interior"], sk)
        out["Details"].append(det.finish(f"{cid}_Details", cols["Details"], uv_size=2.0, merge=0))
        for nm, mbd in dmg.items():
            if len(mbd.bm.faces):
                out["Damage"].append(mbd.finish(f"{cid}_Damage_{nm}", cols["Damage"], uv_size=2.0, merge=0))
    out["Interior"].append(inter.finish(f"{cid}_Interior", cols["Interior"], uv_size=3.0, merge=0))
    out["Skirt"].append(sk.finish(f"{cid}_Skirt", cols["Skirt"], uv_size=2.0, merge=0))
    out["stats"] = stats
    out["cfg"] = cfg
    return out


def build_skirt_l(cfg, sk, keep_clear=()):
    """Arena + hierba alrededor de la planta en L: se reutiliza build_skirt sobre el rectángulo envolvente y se retiran las caras
    que caen bajo el edificio (la esquina entrante SO y el remetimiento SE quedan con terreno)."""
    c = COL_CORNER / 2
    xs, ys = cfg["xs"], cfg["ys"]
    cfg = dict(cfg, footprint=[(xs[0] - c, xs[-1] + c, ys[2] - c, ys[-1] + c), (xs[1] - c, xs[3] + c, ys[0] - c, ys[2] - c)])
    return ab.build_skirt(cfg, sk, margin=3.0, keep_clear=keep_clear)
