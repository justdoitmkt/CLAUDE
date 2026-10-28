"""apt_d.py — APT_D_4p: bloque de paneles prefabricados (PB + 3 pisos), concepto hero 5dac2101 / trasera 09afc20e.

A diferencia de A/B/C (pórtico de concreto visible), aquí NO hay columnas ni vigas a la vista (R10): muros portantes de 0,30
de grandes paneles de 2,7 m con juntas selladas en relieve (cordones claros, como en el concepto), zócalo corrido, losas ocultas.
Malla de módulos: xs = -8,1 … 8,1 (6 x 2,7) · ys = -4,05 … 4,05 (3 x 2,7). Decisión R8: 6 módulos en vez de 5 (KIT) para
acercarse a la proporción alargada del concepto aprobado.
- 2 secciones con escalera INTERIOR en los módulos extremos (0 y 5), tramos a lo largo de +Y; franja de celosías chicas en los
  testeros a la altura de la escalera (concepto). Descanso de piso al frente, nicho atrás.
- PB: dos vestíbulos pasantes (módulos 1 y 4) de la puerta delantera a la trasera, abiertos al descanso de su escalera;
  dos cuartos de servicio en el centro.
- Pisos 1–3: 2 departamentos por piso (módulos 1–2 y 3–4) con estancia y recámara al frente, vestíbulo con baño al centro,
  cocina y recámara atrás; balcones colgados al frente (módulos 2 y 3) y atrás (módulo 1).
- Techo a dos aguas con 3 buhardillas al frente; marquesinas sobre los 4 accesos.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402,F401
from mathutils import Matrix, Vector  # noqa: E402

import apt_builder as ab  # noqa: E402
import apt_common as ac  # noqa: E402
from apt_builder import GROUND, SLAB, _T, level_z, m_wall_x, m_wall_y, partition  # noqa: E402
from kit.common import MB, rng, wall_with_openings  # noqa: E402

TW = 0.30                 # muro de panel
FO = TW / 2               # la cara exterior va 0,15 fuera de la línea de módulo
PITCH, OVH = 28.0, 0.5
STAIR_W, STAIR_LANDING, STAIR_GOING = 1.1, 1.1, 0.27
STAIR_GAP = 0.275
AC_HOLES = {("front", 2): 6, ("back", 2): 5}   # (fachada, nivel) → índice de la ventana bajo la que entra un equipo viejo
DORMERS = (-5.4, 0.0, 5.4)


def cfg_apt_d():
    xs = [-8.1 + 2.7 * i for i in range(7)]
    ys = [-4.05, -1.35, 1.35, 4.05]
    h = [3.0, 2.9, 2.9, 2.9]
    L = 8 * STAIR_GOING + STAIR_LANDING + 0.003
    sw = 2 * STAIR_W + STAIR_GAP                # de la cara de la partición (±5,475) a la cara interior del testero (±7,95)
    y0 = -0.9
    stairs = [dict(x0=-5.475 - sw, y0=y0, w=sw, l=L, origin=(-5.475, y0)), dict(x0=7.95 - sw, y0=y0, w=sw, l=L, origin=(7.95, y0))]
    holes = {k: [(s["x0"], s["x0"] + s["w"], s["y0"], s["y0"] + s["l"]) for s in stairs] for k in (1, 2, 3)}
    return dict(id="APT_D_4p", xs=xs, ys=ys, h=h, cells=set(), stair=stairs[0], stairs=stairs, stair_levels=set(), holes=holes,
                slab_rects=[(xs[0], xs[-1], ys[0], ys[-1], (0.12, 0.12, 0.12, 0.12))], seed=41, loggia_depth=0.0,
                footprint=[(xs[0] - FO, xs[-1] + FO, ys[0] - FO, ys[-1] + FO)], lookdev=dict(paint_tint=(0.60, 0.68, 0.80)))


# ----------------------------------------------------------------------------------------------
# muros de panel
# ----------------------------------------------------------------------------------------------
def facade_wall(cfg, mb, side, lv, ops_by_bay, P):
    """Muro de panel de una fachada completa en el nivel lv (de losa a losa). ops_by_bay: {módulo: [(tipo, fracción)]}.
    Devuelve el dict de panel (m, ops) compatible con ac.dress_panel y con los keepouts del grafiti."""
    xs, ys = cfg["xs"], cfg["ys"]
    zl = level_z(cfg)
    z0 = zl[lv]
    H = cfg["h"][lv]
    if side in ("front", "back"):
        a0, a1 = xs[0] - FO, xs[-1] + FO
        coords = xs
        face = ys[0] - FO if side == "front" else ys[-1] + FO
    else:
        a0, a1 = ys[0] + FO, ys[-1] - FO                     # entre las caras interiores de frente y fondo
        coords = ys
        face = xs[0] - FO if side == "west" else xs[-1] + FO
    L = a1 - a0
    ops = []
    nb = len(coords) - 1
    for b, kinds in ops_by_bay.items():
        # en 'back' y 'west' la u corre al revés (mirando desde afuera): el módulo b ocupa u desde el otro extremo
        c0, c1 = coords[b], coords[b + 1]
        if side in ("back", "west"):
            u_a, u_b = a1 - c1, a1 - c0
        else:
            u_a, u_b = c0 - a0, c1 - a0
        u_a, u_b = max(u_a, 0.0), min(u_b, L)
        for kind, (o0, o1, v0, v1) in ac.layout_openings(kinds, u_b - u_a, H - 0.25):
            ops.append((kind, (round(u_a + o0, 4), round(u_a + o1, 4), v0, v1)))
    if (side, lv) in AC_HOLES:
        _, (o0, o1, v0, _v1) = ops[AC_HOLES[(side, lv)]]
        uc = 0.5 * (o0 + o1)
        ops.append(("ac_box", (round(uc - 0.333, 4), round(uc + 0.333, 4), round(v0 - 0.596, 4), round(v0 - 0.15, 4))))
    m = ac.panel_matrix(side, a0, a1, face, z0)
    wall_with_openings(mb, L, H, TW, [o for _, o in ops], mat_out="plaster", mat_in="plaster", mat_reveal="concrete", m=m)
    p = dict(side=side, line=0, bay=-1, level=lv, a0=a0, a1=a1, L=L, z0=z0, H=H, face=face, recess=0.0, m=m, ops=ops, tag="panel")
    P.append(p)
    return p


def vent_grid(cfg, lv, side, center_u, cols=2, rows=4, s=0.2, gap=0.12, z_mid=1.45):
    """Celosía de huecos cuadrados de la escalera (franja del testero)."""
    out = []
    w = cols * s + (cols - 1) * gap
    hh = rows * s + (rows - 1) * gap
    for i in range(cols):
        for j in range(rows):
            u0 = center_u - w / 2 + i * (s + gap)
            v0 = z_mid - hh / 2 + j * (s + gap)
            out.append(("vent_sq", (round(u0, 4), round(u0 + s, 4), round(v0, 4), round(v0 + s, 4))))
    return out


def side_wall(cfg, mb, side, lv, P):
    """Testeros: franja de celosías en el módulo central (la escalera) + una ventana chica en el módulo delantero (descanso)."""
    ys = cfg["ys"]
    zl = level_z(cfg)
    H = cfg["h"][lv]
    a0, a1 = ys[0] + FO, ys[-1] - FO
    L = a1 - a0
    face = cfg["xs"][0] - FO if side == "west" else cfg["xs"][-1] + FO
    # u: oeste corre de norte a sur, este de sur a norte
    uc = (a1 - 0.0) if side == "west" else (0.0 - a0)          # u del eje y = 0
    ops = vent_grid(cfg, lv, side, uc, z_mid=1.45 if lv else 1.6)
    yw = -2.7                                                   # ventana del descanso (módulo delantero)
    uw = (a1 - yw) if side == "west" else (yw - a0)
    if lv > 0:
        ops.append(("window_small", (round(uw - 0.45, 4), round(uw + 0.45, 4), 1.1, 1.9)))
    m = ac.panel_matrix(side, a0, a1, face, zl[lv])
    wall_with_openings(mb, L, H, TW, [o for _, o in ops], mat_out="plaster", mat_in="plaster", mat_reveal="concrete", m=m)
    P.append(dict(side=side, line=0, bay=-1, level=lv, a0=a0, a1=a1, L=L, z0=zl[lv], H=H, face=face, recess=0.0, m=m, ops=ops,
                  tag="panel"))


FRONT = {0: {0: [("window", 0.5)], 1: [("lobby_door", 0.5)], 2: [("window", 0.5)], 3: [("window", 0.5)], 4: [("lobby_door", 0.5)],
             5: [("window", 0.5)]},
         "up": {0: [("window_small", 0.5)], 1: [("window", 0.5)], 2: [("door_balcony", 0.3), ("window_narrow", 0.78)],
                3: [("window_narrow", 0.22), ("door_balcony", 0.7)], 4: [("window", 0.5)], 5: [("window_small", 0.5)]}}
BACK = {0: {0: [("window_small", 0.5)], 1: [("door_service", 0.5)], 2: [("window", 0.5)], 3: [("window", 0.5)],
            4: [("door_service", 0.5)], 5: [("window_small", 0.5)]},
        "up": {0: [("window_small", 0.5)], 1: [("door_balcony", 0.3), ("window_narrow", 0.78)], 2: [("window", 0.5)],
               3: [("window", 0.5)], 4: [("window", 0.5)], 5: [("window_small", 0.5)]}}
ac.OPENING.setdefault("lobby_door", (1.4, 2.3, 0.0))
ac.OPENING.setdefault("vent_sq", (0.2, 0.2, 1.0))


def build_walls(cfg, shell):
    P = []
    for lv in range(len(cfg["h"])):
        facade_wall(cfg, shell, "front", lv, FRONT[0] if lv == 0 else FRONT["up"], P)
        facade_wall(cfg, shell, "back", lv, BACK[0] if lv == 0 else BACK["up"], P)
        side_wall(cfg, shell, "west", lv, P)
        side_wall(cfg, shell, "east", lv, P)
    return P


def _minus(a, b, holes):
    """Tramos de [a, b] fuera de los intervalos holes."""
    segs, cur = [], a
    for h0, h1 in sorted(holes):
        if h1 <= cur or h0 >= b:
            continue
        if h0 > cur:
            segs.append((cur, h0))
        cur = max(cur, h1)
    if cur < b:
        segs.append((cur, b))
    return segs


def build_joints(cfg, shell, P):
    """Cordones de sellado de las juntas de panel (verticales en cada módulo, horizontales en cada losa) y zócalo corrido."""
    xs, ys = cfg["xs"], cfg["ys"]
    zl = level_z(cfg)
    top = zl[-1]
    jw, jp = 0.035, 0.012
    n = 0
    for side, coords, face, sgn in (("front", xs, ys[0] - FO, -1), ("back", xs, ys[-1] + FO, 1)):
        for x in coords[1:-1]:
            y0, y1 = sorted((face, face + sgn * jp))
            shell.box((x - jw / 2, y0, 0.5), (x + jw / 2, y1, top), "mortar")
            n += 1
        p0 = next(p for p in P if p["side"] == side and p["level"] == 0)
        to_x = (lambda u: p0["a0"] + u) if side == "front" else (lambda u: p0["a1"] - u)
        doors = [tuple(sorted((to_x(o[0]), to_x(o[1])))) for k, o in p0["ops"] if "door" in k]
        for z in zl[1:-1]:
            y0, y1 = sorted((face, face + sgn * jp))
            shell.box((coords[0] - FO, y0, z - jw / 2), (coords[-1] + FO, y1, z + jw / 2), "mortar")
            n += 1
        y0, y1 = sorted((face, face + sgn * jp))
        for a, b in _minus(coords[0] - FO, coords[-1] + FO, doors):                  # junta de PB, cortada en las puertas
            shell.box((a, y0, zl[0] + 0.45 - jw / 2), (b, y1, zl[0] + 0.45 + jw / 2), "mortar")
            n += 1
        # zócalo (no pasa por las puertas: el umbral queda al nivel del escalón de llegada)
        y0, y1 = sorted((face, face + sgn * 0.03))
        for a, b in _minus(coords[0] - FO - 0.03, coords[-1] + FO + 0.03, doors):
            shell.box((a, y0, -0.05), (b, y1, 0.5), "concrete", bevel=0.008, seg=1)
    for side, face, sgn in (("west", xs[0] - FO, -1), ("east", xs[-1] + FO, 1)):
        for y in ys[1:-1]:
            x0, x1 = sorted((face, face + sgn * jp))
            shell.box((x0, y - jw / 2, 0.5), (x1, y + jw / 2, top), "mortar")
            n += 1
        for z in zl[1:-1]:
            x0, x1 = sorted((face, face + sgn * jp))
            shell.box((x0, ys[0] - FO, z - jw / 2), (x1, ys[-1] + FO, z + jw / 2), "mortar")
            n += 1
        x0, x1 = sorted((face, face + sgn * 0.03))
        shell.box((x0, ys[0] - FO, -0.05), (x1, ys[-1] + FO, 0.5), "concrete", bevel=0.008, seg=1)
    # cornisa: anillo alrededor del canto de la losa de azotea (antes un bloque macizo que duplicaba la losa: el techo del
    # último piso y la azotea quedaban con caras coplanares -> z-fighting)
    ex = 0.12                                                    # vuelo de la losa (slab_rects)
    ox0, ox1, oy0, oy1 = xs[0] - FO - 0.06, xs[-1] + FO + 0.06, ys[0] - FO - 0.06, ys[-1] + FO + 0.06
    ix0, ix1, iy0, iy1 = xs[0] - ex, xs[-1] + ex, ys[0] - ex, ys[-1] + ex
    for (a0, b0, a1, b1) in ((ox0, oy0, ox1, iy0), (ox0, iy1, ox1, oy1), (ox0, iy0, ix0, iy1), (ix1, iy0, ox1, iy1)):
        shell.box((a0, b0, top - SLAB), (a1, b1, top), "concrete", bevel=0.012, seg=2)
    return n


def canopy(shell, x0, x1, face, sgn, z, depth=1.1):
    """Marquesina de concreto en voladizo sobre ménsulas de lámina, con escalón de llegada."""
    y0, y1 = sorted((face, face + sgn * depth))
    shell.box((x0, y0, z), (x1, y1, z + 0.12), "concrete", bevel=0.012, seg=2)
    yb0, yb1 = sorted((face + sgn * (depth - 0.08), face + sgn * depth))
    shell.box((x0, yb0, z + 0.12), (x1, yb1, z + 0.30), "concrete", bevel=0.008, seg=1)
    for x in (x0 + 0.15, x1 - 0.15):
        a, b = sorted((face, face + sgn * (depth - 0.15)))
        shell.box((x - 0.04, a, z - 0.35), (x + 0.04, b, z), "metal_paint", bevel=0.004, seg=1)
    s0, s1 = sorted((face, face + sgn * 0.9))
    shell.box((x0 + 0.1, s0, 0.0), (x1 - 0.1, s1, GROUND), "concrete", bevel=0.01, seg=1)


# ----------------------------------------------------------------------------------------------
# interior
# ----------------------------------------------------------------------------------------------
def build_interior(cfg, mb, out):
    zl = level_z(cfg)
    yi0, yi1 = cfg["ys"][0] + FO, cfg["ys"][-1] - FO
    for lv in range(len(cfg["h"])):
        z0 = zl[lv]
        H = cfg["h"][lv] - SLAB
        for sg in (-1, 1):
            xc = sg * 5.4
            if lv == 0:
                partition(mb, (xc, yi0), (xc, yi1), z0, H, t=0.15, doors=[(-2.3, 1.4)], out=out, tag="open")   # vestíbulo | escalera
                partition(mb, (sg * 3.2, yi0), (sg * 3.2, yi1), z0, H, doors=[(0.0, 0.9)], out=out)             # vestíbulo | cuarto
                continue
            partition(mb, (xc, yi0), (xc, yi1), z0, H, t=0.15, doors=[(-1.4, 0.9)], out=out, tag="entry")
            # depto: frente y-3,9..-1,9 · vestíbulo -1,9..0,6 · fondo 0,6..3,9
            xa, xb = sg * 5.325, sg * 0.075
            lo, hi = min(xa, xb), max(xa, xb)
            partition(mb, (lo, -1.9), (hi, -1.9), z0, H, doors=[(sg * 4.0, 0.8), (sg * 2.05, 0.8)], out=out)   # libre del muro del baño
            partition(mb, (lo, 0.6), (hi, 0.6), z0, H, doors=[(sg * 4.0, 0.8), (sg * 1.9, 0.8)], out=out)
            partition(mb, (sg * 2.7, yi0), (sg * 2.7, -1.9), z0, H)
            partition(mb, (sg * 2.7, 0.6), (sg * 2.7, yi1), z0, H)
            partition(mb, (sg * 1.4, -1.9), (sg * 1.4, 0.6), z0, H, doors=[(-0.5, 0.7)], out=out)                 # baño
        partition(mb, (0.0, yi0), (0.0, yi1), z0, H, t=0.15)                                                       # medianera
        for sg in (-1, 1):                         # cierre del núcleo tras el descanso: sin caída a la bodega trasera
            partition(mb, (sg * 7.95, 2.443), (sg * 5.475, 2.443), z0, H, t=0.10)
    return mb


# ----------------------------------------------------------------------------------------------
# balcones, techo, buhardillas
# ----------------------------------------------------------------------------------------------
BALC = [("front", 2, (1, 2, 3)), ("front", 3, (1, 2, 3)), ("back", 1, (1, 2, 3))]


def build_balconies(cfg, shell, det):
    from kit import circulation as circ
    r = rng(cfg["seed"] + 77)
    zl = level_z(cfg)
    xs, ys = cfg["xs"], cfg["ys"]
    w, d = 2.3, 1.15
    n = 0
    for side, b, levels in BALC:
        xc = 0.5 * (xs[b] + xs[b + 1])
        for lv in levels:
            z = zl[lv] - 0.15
            broken = side == "front" and b == 3 and lv == 3
            if side == "front":
                M = _T(xc - w / 2, ys[0] - FO, z)
            else:
                M = _T(xc + w / 2, ys[-1] + FO, z) @ ac._rot_z(180)
            shell.join(circ.balcony_slab(w=w, d=d, t=0.15, seed=int(r.integers(1e6)), spalled=0.8 if broken else 0.08), M)
            zt = zl[lv]
            # antepecho de lámina corrugada pintada al frente + barandal de tubo a los lados
            par = MB()
            par.box((0.04, -d + 0.03, 0.02), (w - 0.04, -d + 0.06, 0.95), "metal_paint")
            for k in range(int((w - 0.08) / 0.08)):
                x = 0.06 + k * 0.08
                par.box((x, -d + 0.015, 0.03), (x + 0.03, -d + 0.03, 0.94), "metal_paint")
            if broken:
                par = MB()                                         # antepecho arrancado: queda el barandal doblado
            det.join(par, M @ _T(0, 0, 0.15))
            sides = MB()
            ac.rail_along(sides, "tube_metal", (0.07, -d), (0.07, 0.0), 0.0, "-x", seed=int(r.integers(1e6)), missing=0.08)
            ac.rail_along(sides, "tube_metal", (w - 0.07, -d), (w - 0.07, 0.0), 0.0, "+x", seed=int(r.integers(1e6)), missing=0.08)
            if broken:                                             # el frente solo lleva barandal donde se perdió el antepecho
                ac.rail_along(sides, "tube_metal", (0.0, -d + 0.07), (w, -d + 0.07), 0.0, "-y", seed=int(r.integers(1e6)),
                              bend=0.3, missing=0.3)
            det.join(sides, M @ _T(0, 0, 0.15))
            n += 1
    return n


def roof_dims(cfg):
    xs, ys = cfg["xs"], cfg["ys"]
    return dict(w=xs[-1] - xs[0] + 2 * FO, d=ys[-1] - ys[0] + 2 * FO)


def build_roof(cfg, roof, shell, det):
    from kit import circulation as circ
    from kit import roofing as rf
    R = roof_dims(cfg)
    W, D = R["w"], R["d"]
    z0 = level_z(cfg)[-1]
    seed = cfg["seed"] + 404
    top = lambda x, y: rf.roof_top("gable", W, D, PITCH, OVH, x=x, y=y)  # noqa: E731
    sp = rf.damage_spot("gable", W, D, PITCH, OVH, seed=seed, damage=0.35)
    sp = (sp[0], abs(sp[1]), sp[2])                         # vertiente trasera
    fr = rf.roof_frame("gable", W, D, PITCH, OVH, seed=seed, cover="tile", damage=0.35, spot=sp)
    tl = rf.barrel_tiles(W, D, "gable", PITCH, OVH, seed=seed, missing=0.03, hole=sp, detail="low")
    # buhardillas: frente en y = yf, mejilla hasta donde el faldón alcanza la cumbrera de la buhardilla
    bw, bh = 1.7, 1.25
    yf = -D / 2 + 1.0
    zb = top(0.0, yf)
    zt = zb + bh
    yb = yf + (zt - zb) / math.tan(math.radians(PITCH))
    for xc in DORMERS:
        box = lambda c, xc=xc: abs(c.x - xc) < bw / 2 + 0.06 and yf - 0.05 < c.y < yb + 0.05  # noqa: E731
        ac.cull_pred(tl, box)
        ac.cull_pred(fr, lambda c, xc=xc: abs(c.x - xc) < bw / 2 - 0.05 and yf + 0.1 < c.y < yb - 0.1 and c.z > zb - 0.05)
    roof.join(fr, _T(0, 0, z0))
    roof.join(tl, _T(0, 0, z0))
    for i, xc in enumerate(DORMERS):
        build_dormer(roof, det, xc, yf, yb, z0 + zb, z0 + zt, bw, seed + 30 + i)
    # hastiales
    xs, ys = cfg["xs"], cfg["ys"]
    for sgn in (-1, 1):
        xg = sgn * (xs[-1] + FO)
        prof = [(0.0, 0.0)] + [(D * i / 12, max(top(xg, -D / 2 + D * i / 12) - 0.18, 0.02)) for i in range(13)] + [(D, 0.0)]
        if sgn < 0:
            M = Matrix(((0, 0, 1, xg), (1, 0, 0, -D / 2), (0, 1, 0, z0), (0, 0, 0, 1)))
        else:
            M = Matrix(((0, 0, -1, xg), (1, 0, 0, -D / 2), (0, 1, 0, z0), (0, 0, 0, 1)))
        shell.plate(prof, TW, "plaster", m=M)
    # canalones frente y fondo + 4 bajantes
    ex, ey = W / 2 + min(OVH, 0.45), D / 2 + OVH
    ze = top(0.0, -ey + 0.01) - 0.06
    off = 0.0865
    n = 0
    for side, path, outs, wall in (("front", [(-ex + 0.05, -ey - off, ze), (ex - 0.05, -ey - off, ze)], [0.8, 2 * ex - 0.9], ys[0] - FO),
                                   ("back", [(ex - 0.05, ey + off, ze), (-ex + 0.05, ey + off, ze)], [0.8, 2 * ex - 0.9], ys[-1] + FO)):
        g = circ.gutter([Vector(p) for p in path], seed=seed + (1 if side == "front" else 2), outlets=outs, dirt=False, hanger_step=1.0,
                        fault="fallen" if side == "back" else "none")
        roof.join(g, _T(0, 0, z0))
        for t in (g.meta.get("outlets", []) if hasattr(g, "meta") else []):
            ac.downpipe_on(det, Vector(t) + Vector((0, 0, z0)), side, wall, seed=seed + 40 + n)
            n += 1
    return dict(downpipes=n, dormers=len(DORMERS))


def build_dormer(roof, det, xc, yf, yb, zb, zt, bw, seed):
    """Buhardilla: frente de tablero con ventana, mejillas triangulares y cubierta de teja a dos aguas (cumbrera en Y)."""
    from kit import openings as op
    from kit import roofing as rf
    mb = MB()
    t = 0.08
    # frente con vano de ventana
    H = zt - zb
    win = (round(bw / 2 - 0.45, 4), round(bw / 2 + 0.45, 4), 0.25, round(min(0.95, H - 0.15), 4))
    m = m_wall_x(xc - bw / 2, yf, zb - 0.05, +1)
    wall_with_openings(mb, bw, H + 0.05, t, [win], mat_out="wood_grey", mat_in="wood_grey", mat_reveal="wood_grey", m=m)
    det.join(op.window("casement", win[1] - win[0], win[3] - win[2], t, seed=seed, broken=0.9, curtain=False, sill=False),
             m @ _T(win[0], 0, win[2]))
    # mejillas
    for sx in (-1, 1):
        x = xc + sx * bw / 2
        prof = [(0.0, 0.0), (0.0, H + 0.05), (yb - yf, H + 0.05)]
        M = Matrix(((0, 0, -sx, x + (t if sx < 0 else 0) * 0), (1, 0, 0, yf), (0, 1, 0, zb - 0.05), (0, 0, 0, 1)))
        mb.plate(prof, t, "wood_grey", m=M)
    # cubierta
    L = (yb - yf) + 0.25
    dd = bw + 0.25
    tiles = rf.barrel_tiles(L, dd, "gable", 35.0, 0.12, seed=seed, missing=0.02, detail="low", rake=0.12)
    frame = rf.roof_frame("gable", L, dd, 35.0, 0.12, seed=seed, cover="tile", tails=False, ties=False, blocking=False, rake=0.12)
    Mr = _T(xc, yf + (yb - yf) / 2 - 0.1, zt) @ ac._rot_z(90)
    mb.join(frame, Mr)
    mb.join(tiles, Mr)
    roof.join(mb)


# ----------------------------------------------------------------------------------------------
# vestido
# ----------------------------------------------------------------------------------------------
def dress_services(cfg, P, det, inter, far="low", near="mid"):
    from kit import services as sv
    r = rng(cfg["seed"] + 505)
    zl = level_z(cfg)
    xs, ys = cfg["xs"], cfg["ys"]
    n = {}

    def add(key, mb, M, target=det):
        target.join(mb, M)
        ac.counter(n, key)

    def wall(side, lv):
        return next(p for p in P if p["side"] == side and p["level"] == lv)

    def op_mid(p, kind_idx):
        o = p["ops"][kind_idx][1]
        return (o[0] + o[1]) / 2, o
    # A/C bajo ventanas: frente lejano, trasera
    for side, lv, k, kind in (("front", 1, 1, "split_outdoor"), ("front", 2, -1, "box_old"), ("back", 1, 3, "split_outdoor"),
                              ("back", 3, 4, "split_outdoor"), ("back", 2, -1, "box_old")):
        p = wall(side, lv)
        u, o = op_mid(p, k)                       # box_old: el último vano del panel es su hueco (AC_HOLES)
        add("ac_" + kind, sv.ac_unit(kind, seed=int(r.integers(1e6)), detail=far), p["m"] @ _T(u, 0, o[2] if kind == "box_old" else o[2] - 0.6))
    # parabólicas en los balcones y tendederos
    for lv in (1, 2, 3):
        xc = 0.5 * (xs[2] + xs[3])
        posts = MB()                              # dos postes de tubo sobre los barandales laterales del balcón
        for x in (xc - 1.08, xc + 1.08):
            posts.box((x - 0.02, ys[0] - FO - 0.62, zl[lv]), (x + 0.02, ys[0] - FO - 0.58, zl[lv] + 2.05), "metal_rust", bevel=0.004, seg=1)
        add("laundry_post", posts, Matrix())
        add("laundry_line", sv.laundry_line(length=2.12, seed=int(r.integers(1e6)), detail=near if lv == 1 else far),
            _T(xc - 1.06, ys[0] - FO - 0.6, zl[lv] + 1.9))
    for lv in (2, 3):
        add("satellite_dish", sv.satellite_dish(seed=int(r.integers(1e6)), detail=far), _T(0.5 * (xs[3] + xs[4]) - 0.16, ys[0] - FO, zl[lv] + 1.7))   # sobre el machón entre ventana y puerta
    # accesos: arbotantes, medidores, buzones
    for sg in (-1, 1):
        x = sg * 4.05                                   # centro del módulo 1 / 4 = eje de las puertas de PB
        add("light_fixture", sv.light_fixture("wall", seed=int(r.integers(1e6)), detail=near), _T(x + 1.25, ys[0] - FO, zl[0] + 2.65))
        add("light_fixture", sv.light_fixture("wall", seed=int(r.integers(1e6)), detail=far),
            _T(x - 0.95, ys[-1] + FO, zl[0] + 2.45) @ ac._rot_z(180))
        add("mailboxes", sv.mailboxes(n=6, seed=int(r.integers(1e6)), detail=near),
            _T(sg * (3.2 + 0.051), -2.1, zl[0] + 1.05) @ ac._rot_z(-90 if sg < 0 else 90), inter)   # 1,6 m libre del vano (y = 0)
    for i, x in enumerate((-3.05, -2.55)):              # machón entre la puerta del vestíbulo y la ventana
        add("meter_box", sv.meter_box(seed=int(r.integers(1e6)), open_door=bool(i), detail=near), _T(x, ys[0] - FO, 1.2))
    add("cable_bundle", sv.cable_bundle([(-8.25, ys[0] - FO - 0.03, zl[1] + 0.15), (-2.45, ys[0] - FO - 0.03, zl[1] + 0.15)], n=3, sag=0.2,
                                        seed=int(r.integers(1e6)), detail=near), Matrix())
    add("conduit", sv.conduit([(0, 0, 1.7), (0, 0, zl[1] + 0.12)], seed=int(r.integers(1e6)), detail=near), _T(-2.45, ys[0] - FO, 0.0))
    for lv in (1, 3):
        add("extinguisher_cabinet", sv.extinguisher_cabinet(seed=int(r.integers(1e6)), detail=near),
            _T(-5.4 - 0.075 - 0.001, -2.9, zl[lv] + 1.05) @ ac._rot_z(-90), inter)
    from kit import roofing as rf
    R = roof_dims(cfg)
    for x in (-3.0, 4.2):
        zr = rf.roof_top("gable", R["w"], R["d"], PITCH, OVH, x=x, y=0.0)
        add("tv_antenna", sv.tv_antenna(seed=int(r.integers(1e6)), detail=far), _T(x, 0.0, level_z(cfg)[-1] + zr + 0.05))
    return n


def dress_damage(cfg, shell, det, inter, skirt, detail="low"):
    from kit import damage as dm
    r = rng(cfg["seed"] + 606)
    zl = level_z(cfg)
    n = {}

    def add(key, mb, M, target):
        target.join(mb, M)
        ac.counter(n, key)
    for (x, y, z, rad, tgt) in ((1.2, -5.6, 0.0, 0.9, skirt), (-7.0, 5.6, 0.0, 1.2, skirt), (2.0, -1.0, zl[0], 0.7, inter),
                                (-1.5, 2.0, zl[2], 0.5, inter)):
        add("rubble_pile", dm.rubble_pile(radius=rad, seed=int(r.integers(1e6)), n=int(rad * 36), detail=detail), _T(x, y, z), tgt)
    for _ in range(16):
        x, y = float(r.uniform(-9.5, 9.5)), float(r.uniform(-6.8, -4.9))
        add("chunk", dm.chunk(size=float(r.uniform(0.1, 0.35)), seed=int(r.integers(1e6)), detail=detail),
            _T(x, y, 0.0) @ ac._rot_z(float(r.uniform(0, 360))), skirt)
    # varillas de la losa de balcón rota (frente, módulo 3, piso 3) y trozos caídos bajo ella
    xc = 0.5 * (cfg["xs"][3] + cfg["xs"][4])
    for _ in range(5):
        add("chunk", dm.chunk(size=float(r.uniform(0.15, 0.45)), seed=int(r.integers(1e6)), kind="slab", detail=detail),
            _T(xc + float(r.uniform(-1.2, 1.2)), cfg["ys"][0] - FO - float(r.uniform(0.6, 2.0)), 0.0) @ ac._rot_z(float(r.uniform(0, 360))),
            skirt)
    return n


def build_apt_d(collection_root=None, dress_all=True):
    from kit.common import get_collection
    cfg = cfg_apt_d()
    cid = cfg["id"]
    root = collection_root or get_collection(cid)
    cols = {k: get_collection(f"{cid}_{k}", root) for k in ("Shell", "Details", "Interior", "Skirt", "Roof", "Damage")}
    out = {k: [] for k in cols}
    shell, det, inter, sk = MB(), MB(), MB(), MB()
    ab.build_frame(cfg, shell)                       # solo losas (sin columnas ni vigas a la vista)
    P = build_walls(cfg, shell)
    stats = dict(joints=build_joints(cfg, shell, P))
    zl = level_z(cfg)
    for sg in (-1, 1):
        x = sg * 4.05
        canopy(shell, x - 1.05, x + 1.05, cfg["ys"][0] - FO, -1, zl[0] + 2.6)
        canopy(shell, x - 0.85, x + 0.85, cfg["ys"][-1] + FO, 1, zl[0] + 2.45, depth=0.9)
    doors = []
    build_interior(cfg, inter, doors)
    out["placed"] = P
    if dress_all:
        r = rng(cfg["seed"] + 101)
        stats["openings"] = sum(ac.dress_panel(p, det, inter, r, primary=p["side"] == "front", depth=TW) for p in P)
        stats["interior_doors"] = ab.dress_interior_doors(cfg, doors, inter)
        for k, st in enumerate(cfg["stairs"]):
            c2 = dict(cfg, seed=cfg["seed"] + 13 * k)
            ac.stair_core(c2, inter, st["origin"], "+y", STAIR_W, STAIR_LANDING, levels=[0, 1, 2], gap=STAIR_GAP, going=STAIR_GOING,
                          limit=(st["l"], st["w"]))
            ac.rail_along(inter, "tube_metal", (st["origin"][0] - STAIR_W, st["y0"]), (st["origin"][0], st["y0"]), zl[3], "+y",
                          seed=cfg["seed"] + 5 + k, missing=0.15)
        stats["balconies"] = build_balconies(cfg, shell, det)
        roof = MB()
        stats["roof"] = build_roof(cfg, roof, shell, det)
        out["Roof"].append(roof.finish(f"{cid}_Roof", cols["Roof"], uv_size=2.0, merge=0))
        stats["services"] = dress_services(cfg, P, det, inter)
    out["Shell"].append(shell.finish(f"{cid}_Shell", cols["Shell"], uv_size=3.0, merge=0))
    keep = [(sg * 4.05 - 1.2, cfg["ys"][0] - 3.0, sg * 4.05 + 1.2, cfg["ys"][0]) for sg in (-1, 1)] + \
           [(sg * 4.05 - 1.0, cfg["ys"][-1], sg * 4.05 + 1.0, cfg["ys"][-1] + 3.0) for sg in (-1, 1)]
    out["stats_skirt"] = ab.build_skirt(cfg, sk, margin=3.0, keep_clear=keep)
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
