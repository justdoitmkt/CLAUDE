"""mue_builder.py — MUE_1_carga: muelle de carga abandonado en la orilla de la playa (referencias refs_higgsfield/MUE_1_carga/).

Planta (Blender: z arriba, metros). El lado de tierra es -Y (fachada principal, como en el resto del kit) y el mar está hacia +Y.
Pedido del usuario (2026-11-12): rampa amplia, más ancha que el almacén, y espacio para que circulen vehículos de carga
alrededor de la nave (por eso no sigue la rampa angosta de la referencia):
  rampa      x -24..24 (47,4 m libres, el ancho de la cubierta) · y -25..0 · sube de la arena (z 0, pivote del modelo en x = 0)
             a la cubierta (z 2,5) al 10 %; estribo de concreto bajo la orilla de la cubierta, muros de contención con pretil
             y coronamiento, aleros abiertos al pie, barandal de tubo, guarniciones, juntas de acero cada 5 m, estrías
             antiderrapantes, rejilla de drenaje al pie, placa de transición atornillada arriba y bolardos de tubo.
  cubierta   L: A x -24..24 · y 0..40 y espigón de atraque B x -24..54 · y 40..52 (frente de atraque en y = 52, 78 m, y en
             x = 54); patio de maniobras de 10 m frente a la nave, carriles de 13 m a los lados y 6 m detrás;
             losa de 0,30 sobre vigas cabezal y pilotes tubulares de acero (Ø0,55, hasta z -7) con cruces;
             trabe de borde de 0,9 grafiteada, guarnición, bitas, defensas de llanta y de madera, escaleras marinas.
  nave       x -11..11 · y 10..34 · alero a 7,5 m sobre la cubierta, techo a dos aguas de 10°; marcos rígidos de acero en
             I, largueros, zócalo de concreto de 1,2 m y lámina trapezoidal (sólidos delgados) con hojas faltantes y
             vencidas; cortinas metálicas de 6 x 5,5 (frente y fondo) y 4 x 4,5 (lado este), ventanas altas de taller,
             tragaluces, entrepiso de oficina con escalera de acero.
  caseta     x -15,2..-11,15 · y 26..32, block aplanado, puerta hacia la nave.
  contenedores 20' (uno estibado), grúa pluma en el espigón, postes de luz, tarimas, cajas, tambos, cabos.
Nivel del mar: z = -0,5 (la cubierta queda 3 m sobre el agua). Sin terreno: la arena y el agua los pone el mapa.
Grupos: Shell (atlas con grafiti: zócalo, lámina, trabes de borde, pretiles, caseta, contenedores) · Interior (losa, rampa,
marcos, entrepiso, escalera, tarimas y cajas grandes: con colisión) · Details · Roof · Skirt (escombro en la arena).
"""
import math

from mathutils import Matrix, Vector

import apt_common as ac
from kit import port
from kit.common import MB, get_collection, rng, wall_with_openings

DECK_Z = 2.5
SEA_Z = -0.5
PILE_BOT = -7.0
SLAB_T = 0.30
FASCIA_W, FASCIA_Z0 = 0.4, 1.6
RAMP_X, RAMP_Y0, RAMP_WALL, PARAPET = 23.7, -25.0, 0.3, 0.9      # rampa del ancho de la cubierta (pretiles a ras de las trabes)
DECK_A = (-24.0, 24.0, 0.0, 40.0)
DECK_B = (-24.0, 54.0, 40.0, 52.0)
HOLE = (33.0, 35.5, 43.0, 45.5)
WH = dict(x0=-11.0, x1=11.0, y0=10.0, y1=34.0, eave=7.5, pitch=10.0, plinth=1.2, ovh=0.3)
ANNEX = dict(x0=-15.2, x1=-11.15, y0=26.0, y1=32.0, h=3.2, t=0.2)
CONTAINERS = [   # (x, y, giro en grados, z, puertas abiertas)  origen: esquina de la base; largo en +x local
    dict(x=20.5, y=20.0, rot=90, z=DECK_Z, open=False),
    dict(x=26.0, y=43.0, rot=0, z=DECK_Z, open=True),
    dict(x=26.4, y=43.1, rot=-3, z=DECK_Z + 2.591, open=False),
    dict(x=-23.3, y=2.5, rot=90, z=DECK_Z, open=False),
]
C_L, C_W, C_H = 6.058, 2.438, 2.591
CRANE_XY = (DECK_B[1] - 11.0, DECK_B[3] - 3.0)
POLES = [   # ((x, y), inclinación en grados, sin luminaria)
    ((DECK_A[1] - 0.8, DECK_A[2] + 1.2), 0.0, False), ((DECK_A[0] + 0.8, DECK_A[2] + 1.2), 0.0, False),
    ((DECK_A[0] + 0.8, DECK_A[3] - 1.0), 6.0, False), ((DECK_B[0] + 30.0, DECK_B[3] - 1.2), 0.0, False),
    ((DECK_B[1] - 0.8, DECK_B[2] + 1.2), 0.0, True), ((DECK_A[1] - 0.8, DECK_A[3] - 6.0), 0.0, False)]
P_TRAP, D_TRAP = 0.20, 0.032          # lámina trapezoidal: paso y peralte
SHEET_T = 0.0015


def _T(x, y, z):
    return Matrix.Translation((x, y, z))


def _Rz(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Z")


def ramp_z(y):
    return DECK_Z * (y - RAMP_Y0) / (0.0 - RAMP_Y0)


def roof_z(x):
    """Cota inferior de la lámina del techo (sobre largueros) en la nave."""
    return DECK_Z + WH["eave"] + (WH["x1"] - abs(x)) * math.tan(math.radians(WH["pitch"]))


def cfg_mue(bid="MUE_1_carga"):
    fp = [(WH["x0"] - 0.05, WH["x1"] + 0.05, WH["y0"] - 0.05, WH["y1"] + 0.05),
          (ANNEX["x0"], ANNEX["x1"], ANNEX["y0"], ANNEX["y1"])]
    return dict(id=bid, seed=71, xs=[DECK_B[0], DECK_B[1]], ys=[RAMP_Y0, DECK_B[3]], h=[DECK_Z], deck_z=DECK_Z, sea_z=SEA_Z,
                band_top=6.6, graffiti_bounds=(-RAMP_X - RAMP_WALL - 2.6, DECK_B[1] + 0.5, RAMP_Y0 - 4.0, DECK_B[3] + 0.5),
                graffiti_px_per_m=150.0,
                exterior_footprint=fp,
                lookdev=dict(base_z=DECK_Z, graffiti_mats=("concrete", "plaster", "cladding", "container"),
                             paint_tint=(0.80, 0.80, 0.78)))


# ------------------------------------------------------------------------------------------------------------ primitivas
def frame_on(p0, p1, up=(0, 0, 1)):
    """Matriz con X a lo largo de p0→p1 y Z lo más cerca posible de `up`; origen en p0."""
    p0, p1 = Vector(p0), Vector(p1)
    X = (p1 - p0).normalized()
    U = Vector(up)
    if abs(X.dot(U)) > 0.99:
        U = Vector((0, 1, 0)) if abs(X.y) < 0.9 else Vector((1, 0, 0))
    Z = (U - X * X.dot(U)).normalized()
    Y = Z.cross(X)
    return Matrix(((X.x, Y.x, Z.x, p0.x), (X.y, Y.y, Z.y, p0.y), (X.z, Y.z, Z.z, p0.z), (0, 0, 0, 1))), (p1 - p0).length


def member(mb, p0, p1, rects, mat, up=(0, 0, 1)):
    """Barra prismática de p0 a p1 con sección = unión de rectángulos [(y0, y1, z0, z1)] en el plano local YZ."""
    M, L = frame_on(p0, p1, up)
    for (y0, y1, z0, z1) in rects:
        mb.box((0.0, y0, z0), (L, y1, z1), mat, m=M)


def i_sec(h, b, tw=0.012, tf=0.016):
    return [(-tw / 2, tw / 2, -h / 2 + tf, h / 2 - tf), (-b / 2, b / 2, h / 2 - tf, h / 2), (-b / 2, b / 2, -h / 2, -h / 2 + tf)]


def c_sec(h, b, t=0.006):
    """Canal (C) abierto hacia +Y local."""
    return [(0.0, t, -h / 2, h / 2), (t, b, h / 2 - t, h / 2), (t, b, -h / 2, -h / 2 + t)]


def grid_solid(mb, x0, x1, y0, y1, ztop, zbot, mat, cell=1.0, holes=()):
    """Losa cerrada en rejilla: cara superior subdividida (AO por vértice), inferior y cantos (también alrededor de huecos).
    ztop(x, y) / zbot(x, y): cotas."""
    def axis(a0, a1, cuts):
        vals = {round(a0, 4), round(a1, 4)}
        k = math.floor(a0 / cell) + 1
        while k * cell < a1 - 1e-6:
            vals.add(round(k * cell, 4))
            k += 1
        for c in cuts:
            if a0 < c < a1:
                vals.add(round(c, 4))
        return sorted(vals)
    xs = axis(x0, x1, [c for h in holes for c in h[:2]])
    ys = axis(y0, y1, [c for h in holes for c in h[2:]])
    nx, ny = len(xs) - 1, len(ys) - 1

    def solid(i, j):
        if not (0 <= i < nx and 0 <= j < ny):
            return False
        cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
        return not any(h[0] <= cx <= h[1] and h[2] <= cy <= h[3] for h in holes)
    top, bot = {}, {}

    def T(i, j):
        if (i, j) not in top:
            top[(i, j)] = mb.bm.verts.new((xs[i], ys[j], ztop(xs[i], ys[j])))
        return top[(i, j)]

    def B(i, j):
        if (i, j) not in bot:
            bot[(i, j)] = mb.bm.verts.new((xs[i], ys[j], zbot(xs[i], ys[j])))
        return bot[(i, j)]
    for i in range(nx):
        for j in range(ny):
            if not solid(i, j):
                continue
            mb.face([T(i, j), T(i + 1, j), T(i + 1, j + 1), T(i, j + 1)], mat)
            mb.face([B(i, j), B(i, j + 1), B(i + 1, j + 1), B(i + 1, j)], mat)
            if not solid(i - 1, j):
                mb.face([B(i, j), T(i, j), T(i, j + 1), B(i, j + 1)], mat)
            if not solid(i + 1, j):
                mb.face([B(i + 1, j), B(i + 1, j + 1), T(i + 1, j + 1), T(i + 1, j)], mat)
            if not solid(i, j - 1):
                mb.face([B(i, j), B(i + 1, j), T(i + 1, j), T(i, j)], mat)
            if not solid(i, j + 1):
                mb.face([B(i, j + 1), T(i, j + 1), T(i + 1, j + 1), B(i + 1, j + 1)], mat)


# ------------------------------------------------------------------------------------------------------------ lámina
def _trap_d(u):
    f = (u % P_TRAP)
    if f < 0.045 or f >= 0.155:
        return 0.0
    if f < 0.075:
        return D_TRAP * (f - 0.045) / 0.03
    if f < 0.125:
        return D_TRAP
    return D_TRAP * (0.155 - f) / 0.03


def _trap_pts(u0, u1):
    us = {round(u0, 5), round(u1, 5)}
    k = math.floor(u0 / P_TRAP)
    while k * P_TRAP < u1:
        for du in (0.045, 0.075, 0.125, 0.155):
            u = k * P_TRAP + du
            if u0 < u < u1:
                us.add(round(u, 5))
        k += 1
    return sorted(us)


def sheet(mb, u0, u1, zb, zt, mat, M, hinge=0.0, out=-1.0, lift=0.0):
    """Hoja trapezoidal como sólido delgado (sin caras sueltas: el recálculo de normales la deja bien orientada).
    Local: u en X, cota en Z, peralte hacia `out`*Y (-Y = afuera en los muros del kit). zb/zt: funciones de u.
    hinge (rad): la hoja gira sobre su borde superior hacia afuera (hoja vencida). lift: despegue hacia afuera (la hoja
    de arriba monta sobre la de abajo en el traslape del techo)."""
    us = _trap_pts(u0, u1)

    def P(u, z, y):
        if hinge:
            ztop = zt(u)
            dz = z - ztop
            y, z = y * math.cos(hinge) - out * dz * math.sin(hinge), ztop + dz * math.cos(hinge) + out * y * math.sin(hinge)
        return mb.bm.verts.new(M @ Vector((u, y, z)))
    ob, ot, ib, it = [], [], [], []
    for u in us:
        d = out * (_trap_d(u) + lift)
        ob.append(P(u, zb(u), d))
        ot.append(P(u, zt(u), d))
        ib.append(P(u, zb(u), d - out * SHEET_T))
        it.append(P(u, zt(u), d - out * SHEET_T))
    n = len(us)
    for i in range(n - 1):
        mb.face([ob[i], ob[i + 1], ot[i + 1], ot[i]], mat)
        mb.face([ib[i], it[i], it[i + 1], ib[i + 1]], mat)
        mb.face([ob[i], ib[i], ib[i + 1], ob[i + 1]], mat)
        mb.face([ot[i], ot[i + 1], it[i + 1], it[i]], mat)
    mb.face([ob[0], ot[0], it[0], ib[0]], mat)
    mb.face([ob[-1], ib[-1], it[-1], ot[-1]], mat)


def clad_wall(mb, M, L, z0, ztop_fn, openings, r, mat="cladding", width=1.0, rows=(4.35,), missing=0.06, bent=0.05,
              kill=()):
    """Muro de lámina en hojas de `width` m. openings/kill: [(u0, u1, z0, z1)] (kill = hojas arrancadas a propósito)."""
    n = int(math.ceil(L / width - 1e-6))
    stats = dict(sheets=0, missing=0, bent=0)
    for k in range(n):
        u0, u1 = k * width, min((k + 1) * width, L)
        if u1 - u0 < 0.05:
            continue
        cuts = [z0] + [z for z in rows if z > z0] + [None]
        for ri in range(len(cuts) - 1):
            za = cuts[ri]
            zb_ = cuts[ri + 1]
            top = (lambda u, zb_=zb_: min(zb_, ztop_fn(u))) if zb_ is not None else ztop_fn
            if za >= max(top(u0), top(u1)) - 0.05:
                continue
            um = (u0 + u1) / 2
            segs = [(za, top)]                     # intervalos de cota libres de vanos
            for (o0, o1, oz0, oz1) in openings:
                if o0 <= um <= o1:
                    new = []
                    for (a, tf) in segs:
                        b = tf(um)
                        if oz1 <= a or oz0 >= b:
                            new.append((a, tf))
                            continue
                        if oz0 > a:
                            new.append((a, (lambda u, v=oz0: v)))
                        if oz1 < b:
                            new.append((oz1, tf))
                    segs = new
            for (a, tf) in segs:
                if tf(um) - a < 0.08:
                    continue
                if any(o0 <= um <= o1 and oz0 <= (a + tf(um)) / 2 <= oz1 for (o0, o1, oz0, oz1) in kill) or r.random() < missing:
                    stats["missing"] += 1
                    continue
                hinge = float(r.uniform(0.05, 0.22)) if r.random() < bent else 0.0
                stats["bent"] += hinge > 0
                sheet(mb, u0 + 0.004, u1 - 0.004, lambda u, a=a: a, tf, mat, M, hinge=hinge)
                stats["sheets"] += 1
    return stats


# ------------------------------------------------------------------------------------------------------------ cubierta
def build_deck(shell, inter, det, r):
    zt = lambda x, y: DECK_Z  # noqa: E731
    zb = lambda x, y: DECK_Z - SLAB_T  # noqa: E731
    w = FASCIA_W
    ax0, ax1, ay0, ay1 = DECK_A
    bx0, bx1, by0, by1 = DECK_B
    grid_solid(inter, ax0 + w, ax1 - w, ay0 + w, by0, zt, zb, "concrete")
    grid_solid(inter, bx0 + w, ax1 - w, by0, by1 - w, zt, zb, "concrete")
    grid_solid(inter, ax1 - w, bx1 - w, by0 + w, by1 - w, zt, zb, "concrete", holes=[HOLE])
    # trabes de borde (Shell: atlas con óxido, salitre y grafiti)
    z0, z1 = FASCIA_Z0, DECK_Z
    for (a, b) in [((ax0, ay0), (ax1, ay0 + w)), ((ax0, ay0 + w), (ax0 + w, by1)), ((ax1 - w, ay0 + w), (ax1, by0 + w)),
                   ((ax1, by0), (bx1, by0 + w)), ((bx1 - w, by0 + w), (bx1, by1)), ((ax0 + w, by1 - w), (bx1 - w, by1))]:
        shell.box((a[0], a[1], z0), (b[0], b[1], z1), "concrete")
    # vigas cabezal bajo la losa y pilotes de acero con cruces
    piles = []
    xa = [ax0 + 2.0 + k * (ax1 - ax0 - 4.0) / 8 for k in range(9)]
    ya = [ay0 + 2.5 + 5 * k for k in range(int((by0 - ay0) / 5))]
    for yb in ya:
        det.box((ax0 + w, yb - 0.4, 1.5), (ax1 - w, yb + 0.4, DECK_Z - SLAB_T), "concrete")
        for xp in xa:
            piles.append((xp, yb))
    xb_ = [bx0 + 2.5 + 5 * k for k in range(int((bx1 - bx0) / 5))]
    yb3 = (by0 + 1.6, (by0 + by1) / 2, by1 - 1.6)
    for xb in xb_:
        det.box((xb - 0.4, by0 + w, 1.5), (xb + 0.4, by1 - w, DECK_Z - SLAB_T), "concrete")
        for yp in yb3:
            piles.append((xb, yp))
    for (x, y) in piles:
        det.cyl((x, y, PILE_BOT), (x, y, 1.5), 0.275, seg=14, mat="metal_rust")
        det.cyl((x, y, SEA_Z - 0.7), (x, y, SEA_Z + 0.3), 0.30, seg=14, mat="rubble")      # costra marina en la línea de agua

    def brace(p, q):
        if r.random() < 0.08:
            return
        det.cyl(p, q, 0.055, seg=4, mat="metal_rust")
    for yb in ya:
        for a, b in zip(xa[:-1], xa[1:]):
            brace((a + 0.25, yb, 1.2), (b - 0.25, yb, -2.2))
            brace((a + 0.25, yb, -2.2), (b - 0.25, yb, 1.2))
            brace((a + 0.25, yb, 1.25), (b - 0.25, yb, 1.25))
            brace((a + 0.25, yb, -2.25), (b - 0.25, yb, -2.25))
    for xb in xb_:
        for a, b in zip(yb3[:-1], yb3[1:]):
            brace((xb, a + 0.25, 1.2), (xb, b - 0.25, -2.2))
            brace((xb, a + 0.25, -2.2), (xb, b - 0.25, 1.2))
            brace((xb, a + 0.25, 1.25), (xb, b - 0.25, 1.25))
    # juntas de dilatación de la losa: solera de acero de 8 cm al ras, por los carriles (no pasan bajo la nave ni la caseta)
    def joint(p0, p1):
        det.box((min(p0[0], p1[0]) - (0.04 if p0[0] == p1[0] else 0), min(p0[1], p1[1]) - (0.04 if p0[1] == p1[1] else 0), DECK_Z),
                (max(p0[0], p1[0]) + (0.04 if p0[0] == p1[0] else 0), max(p0[1], p1[1]) + (0.04 if p0[1] == p1[1] else 0),
                 DECK_Z + 0.006), "metal_rust")
    joint((ax0 + w, 5.0), (ax1 - w, 5.0))
    joint((ax0 + w, 37.5), (ax1 - w, 37.5))
    joint((ax0 + w, by0), (ax1 - w, by0))
    for x in (-19.0, 17.0):
        joint((x, ay0 + w), (x, by0 - 0.04))
    for x in (6.0, 18.0, 30.0, 39.5, 50.0):
        joint((x, by0 + 0.04), (x, by1 - w))
    # largueros longitudinales bajo la cubierta A (entre vigas cabezal, en algunas líneas de pilotes)
    for xp in xa[::2]:
        det.box((xp - 0.2, ya[0] + 0.4, 1.7), (xp + 0.2, ya[-1] - 0.4, DECK_Z - SLAB_T), "concrete")
    return dict(piles=len(piles))


def berth_layout():
    """Ejes x de las bitas del frente de atraque y de las escaleras marinas."""
    bx0, bx1 = DECK_B[0], DECK_B[1]
    return [bx0 + 5.0 + 8.0 * k for k in range(int((bx1 - bx0 - 6) / 8) + 1)], (bx0 + 14.5, bx0 + 38.5, bx0 + 62.5)


def bollard_xy():
    xs_b, lad = berth_layout()
    by0, by1, bx1 = DECK_B[2], DECK_B[3], DECK_B[1]
    return [(x, by1 - 0.75) for x in xs_b if not any(abs(x - l) < 1.0 for l in lad)] + [(bx1 - 0.75, by0 + 3.0),
                                                                                       (bx1 - 0.75, by1 - 4.0)]


def collision_proxies():
    """Formas simples que se suman a la malla de colisión del kit: la grúa, los postes y las bitas son Detalle (sin colisión)."""
    mb = MB()
    cx, cy = CRANE_XY
    mb.cyl((cx, cy, DECK_Z), (cx, cy, DECK_Z + 0.45), 1.3, seg=16, mat="concrete")
    mb.cyl((cx, cy, DECK_Z + 0.45), (cx, cy, DECK_Z + 4.6), 0.75, seg=16, mat="concrete")
    mb.cyl((cx, cy, DECK_Z + 4.6), (cx, cy, DECK_Z + 8.4), 2.4, seg=16, mat="concrete")
    for ((x, y), _, _) in POLES:
        mb.cyl((x, y, DECK_Z), (x, y, DECK_Z + 8.6), 0.16, seg=8, mat="concrete")
    for (x, y) in bollard_xy():
        mb.box((x - 0.26, y - 0.22, DECK_Z), (x + 0.26, y + 0.22, DECK_Z + 0.6), "concrete")
    return mb


def build_berth(det, r):
    """Frente de atraque: guarnición, bitas, defensas de llanta y de madera, escaleras marinas, cabos."""
    bx0, bx1, by0, by1 = DECK_B
    stats = dict(bollards=0, tyres=0, timbers=0, ladders=0)
    xs_b, lad = berth_layout()
    # guarnición (con cortes en las escaleras)
    cuts = sorted([(x - 0.6, x + 0.6) for x in lad])
    cur = bx0
    for (c0, c1) in cuts:
        det.box((cur, by1 - 0.3, DECK_Z), (c0, by1, DECK_Z + 0.22), "concrete")
        cur = c1
    det.box((cur, by1 - 0.3, DECK_Z), (bx1, by1, DECK_Z + 0.22), "concrete")
    det.box((bx1 - 0.3, by0, DECK_Z), (bx1, by1 - 0.3, DECK_Z + 0.22), "concrete")
    for x in xs_b:
        if any(abs(x - l) < 1.0 for l in lad):
            continue
        det.join(port.bollard(int(r.integers(1e6))), _T(x, by1 - 0.75, DECK_Z) @ _Rz(float(r.uniform(-4, 4))))
        stats["bollards"] += 1
    for y in (by0 + 3.0, by1 - 4.0):
        det.join(port.bollard(int(r.integers(1e6))), _T(bx1 - 0.75, y, DECK_Z) @ _Rz(90 + float(r.uniform(-4, 4))))
        stats["bollards"] += 1
    # ángulo de protección de acero en la arista de la guarnición
    for (p0, p1, ax) in (((bx0, by1), (bx1, by1), "x"), ((bx1, by0), (bx1, by1), "y")):
        zt = DECK_Z + 0.22
        if ax == "x":
            det.box((p0[0], by1 - 0.15, zt), (p1[0], by1 + 0.012, zt + 0.012), "metal_rust")
            det.box((p0[0], by1, zt - 0.15), (p1[0], by1 + 0.012, zt), "metal_rust")
        else:
            det.box((bx1 - 0.15, p0[1], zt), (bx1 + 0.012, p1[1] - 0.15, zt + 0.012), "metal_rust")
            det.box((bx1, p0[1], zt - 0.15), (bx1 + 0.012, p1[1] - 0.15, zt), "metal_rust")
    # imbornales: tubos de desagüe por la trabe de borde cada 6 m
    x = bx0 + 1.5
    while x < bx1 - 1:
        det.cyl((x, by1 - 0.3, DECK_Z - 0.18), (x, by1 + 0.16, DECK_Z - 0.18), 0.055, seg=10, mat="metal_rust")
        x += 6.0
    # defensas: llantas colgando de cadena y pilotes de madera
    x = bx0 + 2.0
    while x < bx1 - 1.0:
        if r.random() > 0.12 and not any(abs(x - l) < 0.8 for l in lad):
            ztop = DECK_Z - 0.62
            det.join(port.fender_tyre(int(r.integers(1e6))), _T(x, by1 + 0.15, ztop - 0.55) @
                     Matrix.Rotation(float(r.uniform(-0.15, 0.15)), 4, "Y"))
            det.box((x - 0.05, by1, DECK_Z - 0.12), (x + 0.05, by1 + 0.04, DECK_Z - 0.02), "metal_rust")      # argolla
            port.chain(det, [(x, by1 + 0.07, DECK_Z - 0.09), (x, by1 + 0.11, ztop + 0.0)], r=r)
            stats["tyres"] += 1
        x += 3.0
    x = bx0 + 3.5
    while x < bx1 - 1.0:
        if not any(abs(x - l) < 0.8 for l in lad):
            lean = float(r.uniform(-0.02, 0.02))
            det.join(port.timber_fender(DECK_Z - 0.05 + 1.6, int(r.integers(1e6))),
                     _T(x, by1 + 0.005, -1.6) @ Matrix.Rotation(lean, 4, "Y"))
            stats["timbers"] += 1
        x += 6.0
    for x in lad:
        det.join(port.marine_ladder(-1.4, DECK_Z, int(r.integers(1e6))), _T(x, by1, 0.0))
        stats["ladders"] += 1
    # cabos deshilachados de dos bitas al agua
    for x in (xs_b[2], xs_b[6]):
        y = by1 - 0.7
        pts = [(x, y, DECK_Z + 0.35), (x + 0.3, y + 0.6, DECK_Z + 0.25), (x + 0.6, y + 1.0, DECK_Z - 0.2),
               (x + 0.9, y + 1.3, DECK_Z - 1.5), (x + 1.4, y + 1.6, SEA_Z + 0.1)]
        det.tube(pts, 0.022, seg=6, mat="plastic")
    return stats


def tyre(mb, c, r, axis="z"):
    """Llanta detallada (kit.port) acostada (axis z) o de canto (axis y), centrada en c."""
    t = port.fender_tyre(int(r.integers(1e6)))
    M = _T(*c) @ _Rz(float(r.uniform(0, 360)))
    if axis == "z":
        M = _T(c[0], c[1], c[2] - 0.13 + 0.115) @ _Rz(float(r.uniform(0, 360))) @ Matrix.Rotation(math.pi / 2, 4, "X")
    mb.join(t, M)


# ------------------------------------------------------------------------------------------------------------ rampa
def build_ramp(shell, inter, det, r):
    """Rampa de acceso del ancho de la cubierta, apoyada en un terraplén con muros de contención (los pretiles quedan a ras de
    las trabes de borde de la cubierta) y estribo bajo la orilla de la losa."""
    W = RAMP_X
    up_n = Vector((0.0, -math.sin(math.atan(DECK_Z / -RAMP_Y0)), math.cos(math.atan(DECK_Z / -RAMP_Y0))))
    grid_solid(inter, -W, W, RAMP_Y0, 0.0, lambda x, y: ramp_z(y), lambda x, y: -0.8, "concrete", cell=1.0)
    for sg in (-1, 1):
        x0 = W if sg > 0 else -W - RAMP_WALL
        x1 = x0 + RAMP_WALL
        xm = (x0 + x1) / 2
        prof = [(RAMP_Y0, -0.8), (0.0, -0.8), (0.0, ramp_z(0.0) + PARAPET), (RAMP_Y0, ramp_z(RAMP_Y0) + PARAPET)]
        vl = [shell.bm.verts.new((x0, y, z)) for (y, z) in prof]
        vr = [shell.bm.verts.new((x1, y, z)) for (y, z) in prof]
        shell.face(list(reversed(vl)), "concrete")
        shell.face(vr, "concrete")
        for i in range(4):
            j = (i + 1) % 4
            shell.face([vl[i], vl[j], vr[j], vr[i]], "concrete")
        # coronamiento con goteros (sobresale 5 cm a cada lado)
        port.member(shell, (xm, RAMP_Y0, ramp_z(RAMP_Y0) + PARAPET), (xm, 0.0, ramp_z(0.0) + PARAPET),
                    [(-0.2, 0.2, 0.0, 0.09)], "concrete", up=(0, 0, 1))
        # alero al pie: muro abierto 30° hacia afuera que baja de 0,9 a 0,3 m
        ang = math.radians(30.0)
        L = 4.0
        pw = [(0.0, -0.8), (L, -0.8), (L, 0.3), (0.0, PARAPET)]
        dirv = Vector((sg * math.sin(ang), -math.cos(ang), 0.0))
        nrm = Vector((-dirv.y, dirv.x, 0.0)) * RAMP_WALL / 2
        base = Vector((xm, RAMP_Y0, 0.0))
        side_a = [shell.bm.verts.new(base + dirv * u - nrm + Vector((0, 0, z))) for (u, z) in pw]
        side_b = [shell.bm.verts.new(base + dirv * u + nrm + Vector((0, 0, z))) for (u, z) in pw]
        shell.face(side_a, "concrete")
        shell.face(list(reversed(side_b)), "concrete")
        for i in range(4):
            j = (i + 1) % 4
            shell.face([side_a[i], side_b[i], side_b[j], side_a[j]], "concrete")
        # guarnición interior (rueda) de concreto
        port.member(inter, (sg * (W - 0.15), RAMP_Y0 + 0.4, ramp_z(RAMP_Y0 + 0.4)), (sg * (W - 0.15), -0.3, ramp_z(-0.3)),
                    [(-0.15, 0.15, 0.0, 0.2)], "concrete", up=tuple(up_n))
        # barandal de tubo sobre el coronamiento (un tramo arrancado en el pretil oeste)
        zc = PARAPET + 0.09
        segs = [(RAMP_Y0 + 0.3, -17.0), (-16.5, -8.5), (-8.0, -0.3)]
        for k, (ya, yb) in enumerate(segs):
            if sg < 0 and k == 1:
                continue
            port.handrail(det, (xm, ya, ramp_z(ya) + zc), (xm, yb, ramp_z(yb) + zc), h=1.0, post_step=2.0, r=r)
    # juntas de dilatación de acero cada 5 m y estrías antiderrapantes entre juntas
    for yj in (-20.0, -15.0, -10.0, -5.0):
        port.member(det, (-W + 0.3, yj, ramp_z(yj)), (W - 0.3, yj, ramp_z(yj)), [(-0.04, 0.04, 0.0, 0.006)], "metal_rust",
                    up=tuple(up_n))
    y = RAMP_Y0 + 0.9
    while y < -0.6:
        if min(abs(y - yj) for yj in (-20.0, -15.0, -10.0, -5.0)) > 0.3:
            port.member(det, (-W + 0.35, y, ramp_z(y)), (W - 0.35, y, ramp_z(y)), [(-0.012, 0.012, 0.0, 0.005)], "concrete",
                        up=tuple(up_n))
        y += 0.32
    # rejilla de drenaje al pie (de lado a lado) con su marco de ángulo
    yg0, yg1 = RAMP_Y0 + 0.15, RAMP_Y0 + 0.55
    for yy in (yg0, yg1 - 0.03):
        det.box((-W + 0.3, yy, ramp_z(yy) - 0.002), (W - 0.3, yy + 0.03, ramp_z(yy) + 0.008), "metal_rust")
    x = -W + 0.35
    while x < W - 0.35:
        det.box((x, yg0 + 0.03, ramp_z(yg0) - 0.002), (x + 0.008, yg1 - 0.03, ramp_z(yg1) + 0.006), "metal_rust")
        x += 0.045
    # ángulo de nariz al pie y placa de transición atornillada arriba
    det.box((-W, RAMP_Y0 - 0.012, -0.08), (W, RAMP_Y0 + 0.012, 0.005), "metal_rust")
    det.box((-W + 0.3, -0.35, DECK_Z - 0.03), (W - 0.3, 0.35, DECK_Z + 0.012), "metal_rust")
    x = -W + 0.8
    while x < W - 0.5:
        for yb_ in (-0.27, 0.27):
            port.bolt(det, _T(x, yb_, DECK_Z + 0.012), d=0.02, stud=0.006)
        x += 1.2
    # estribo: viga de apoyo bajo la orilla de la cubierta (y 0..1)
    det.box((-RAMP_X - RAMP_WALL, 0.0, 1.3), (RAMP_X + RAMP_WALL, 1.0, DECK_Z - SLAB_T), "concrete")
    # bolardos de tubo relleno en las esquinas del pie
    for sg in (-1, 1):
        for xx in (W - 1.0, W - 2.6):
            port.lathe(det, [(0.11, -0.3), (0.11, 0.9), (0.095, 0.97), (0.0, 0.99)], seg=16, mat="metal_paint",
                       M=_T(sg * xx, RAMP_Y0 - 0.8, 0.0))


# ------------------------------------------------------------------------------------------------------------ nave
def wh_openings():
    """Vanos por fachada en coordenadas del muro (u desde a0 mirando de afuera, z local sobre la cubierta)."""
    return {
        "front": [("shutter_big", (8.0, 14.0, 0.0, 5.5)), ("door", (17.0, 18.0, 0.0, 2.1))],
        "back": [("shutter_big_open", (8.0, 14.0, 0.0, 5.5))],
        "east": [("shutter_open", (1.4, 5.4, 0.0, 4.5)), ("shutter", (7.0, 11.0, 0.0, 4.5))]
                + [("clerestory", (a, a + 4.0, 5.9, 6.9)) for a in (1.0, 7.0, 13.0, 19.0)],
        "west": [("door", (6.3, 7.3, 0.0, 2.1))] + [("clerestory", (a, a + 4.0, 5.9, 6.9)) for a in (1.0, 7.0, 13.0, 19.0)],
    }


def wh_side(side):
    x0, x1, y0, y1 = WH["x0"], WH["x1"], WH["y0"], WH["y1"]
    if side in ("front", "back"):
        a0, a1, face = x0, x1, (y0 if side == "front" else y1)
    else:
        a0, a1, face = y0, y1, (x0 if side == "west" else x1)
    return a0, a1, face


def build_warehouse(shell, inter, det, roof, r):
    tp = math.tan(math.radians(WH["pitch"]))
    stats = {}
    ops = wh_openings()
    PL = WH["plinth"]
    for side in ("front", "back", "west", "east"):
        a0, a1, face = wh_side(side)
        L = a1 - a0
        M = ac.panel_matrix(side, a0, a1, face, DECK_Z)
        cut = [o for _, o in ops[side] if o[2] < PL]
        # el zócalo de los costados arranca dentro del de frente y fondo: en la esquina no quedan caras coplanares encimadas
        e = 0.25 if side in ("west", "east") else 0.0
        wall_with_openings(shell, L - 2 * e, PL, 0.25, [(o[0] - e, o[1] - e, 0.0, PL + 0.01) for o in cut], mat_out="concrete",
                           mat_in="concrete", mat_reveal="concrete", m=M @ _T(e, 0, 0))
        if side in ("front", "back"):
            ztop = lambda u, side=side, a0=a0: (roof_z((a0 + u) if side == "front" else (WH["x1"] - u)) - DECK_Z) - 0.012  # noqa
            Mc = M @ _T(0.0, 0.0, 0.0)
            uu0, uu1 = 0.04, L - 0.04
            Mc = M @ _T(uu0, 0, 0)
            Lc = uu1 - uu0
            opc = [(o[0] - uu0, o[1] - uu0, o[2], o[3]) for _, o in ops[side]]
            kill = [] if side == "front" else [(15.0 - uu0, 19.0 - uu0, 4.4, 9.9)]
            st = clad_wall(shell, Mc, Lc, PL, lambda u, f=ztop, d=uu0: f(u + d), opc, r, kill=kill)
        else:
            kill = [(10.0, 16.0, 4.4, 7.6)] if side == "west" else []
            st = clad_wall(shell, M, L, PL, lambda u: WH["eave"] - 0.005, [o for _, o in ops[side]], r, kill=kill)
        stats[f"lamina_{side}"] = st
        # piezas en los vanos
        for kind, (u0, u1, v0, v1) in ops[side]:
            w, h = u1 - u0, v1 - v0
            Mo = M @ _T(u0, 0, v0)
            seed = int(r.integers(1e6))
            from kit import openings as op
            if kind.startswith("shutter"):
                of = 0.55 if kind == "shutter_big_open" else (0.97 if kind == "shutter_open" else float(r.uniform(0.0, 0.08)))
                det.join(op.rolling_shutter(w, h, seed=seed, dent=float(r.uniform(0.5, 0.9)), open_frac=of), Mo)
                # marco de acero del vano
                for uu in (u0 - 0.2, u1):
                    inter.box((uu, 0.05, 0.0), (uu + 0.2, 0.25, v1 + 0.3), "metal_paint", m=M)
                inter.box((u0 - 0.2, 0.05, v1), (u1 + 0.2, 0.25, v1 + 0.3), "metal_paint", m=M)
            elif kind == "door":
                det.join(op.door("metal", w, h, 0.25, seed=seed, open_angle=float(r.uniform(35, 85))), Mo)
            elif kind == "clerestory":
                factory_window(det, Mo, w, h, r)
    # marcos rígidos (Interior: dan colisión), largueros, contravientos
    xc = WH["x1"] - 0.1515 - 0.2
    frames = [WH["y0"] + 0.45, 16.0, 22.0, 28.0, WH["y1"] - 0.45]
    zbp = DECK_Z + 0.055                                   # lecho de mortero 3 cm + placa base 25 mm

    def base_plate(x, y, ax="x"):
        hx, hy = (0.30, 0.20) if ax == "x" else (0.20, 0.30)
        inter.box((x - hx - 0.03, y - hy - 0.03, DECK_Z), (x + hx + 0.03, y + hy + 0.03, DECK_Z + 0.03), "concrete")
        inter.box((x - hx, y - hy, DECK_Z + 0.03), (x + hx, y + hy, zbp), "metal_rust")
        for (bx, by) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            port.bolt(det, _T(x + bx * (hx - 0.045), y + by * (hy - 0.06), zbp), d=0.03, stud=0.035)
    for yf in frames:
        for sg in (-1, 1):
            x = sg * xc
            zt = roof_z(x) - 0.2 - 0.02
            base_plate(x, yf)
            member(inter, (x, yf, zbp), (x, yf, zt - 0.2), i_sec(0.40, 0.25), "metal_paint", up=(1, 0, 0))
            p0 = Vector((x, yf, zt - 0.22))
            p1 = Vector((0.0, yf, roof_z(0.0) - 0.2 - 0.22))
            member(inter, p0, p1, i_sec(0.42, 0.2), "metal_paint", up=(0, 0, 1))
            # cartela en el codo
            member(inter, (x, yf, zt - 1.1), (x - sg * 1.2, yf, zt - 0.22 + 1.2 * tp - 0.21), [(-0.006, 0.006, -0.12, 0.12)],
                   "metal_paint")
    # postes de hastial en los marcos extremos (sostienen los largueros de las fachadas frente y fondo)
    for yf in (frames[0], frames[-1]):
        for x in (-5.0, 5.0):
            base_plate(x, yf, ax="y")
            member(inter, (x, yf, zbp), (x, yf, roof_z(x) - 0.66), i_sec(0.30, 0.18, tw=0.009, tf=0.012), "metal_paint",
                   up=(0, 1, 0))
    # largueros del techo (Z) y largueros de muro (C)
    nP = 8
    zs = port.z_sec(0.2, 0.07, 0.003)
    for sg in (-1, 1):
        nr = Vector((sg * math.sin(math.radians(WH["pitch"])), 0.0, math.cos(math.radians(WH["pitch"]))))
        for k in range(nP + 1):
            x = sg * (WH["x1"] + 0.1 - k * (WH["x1"] + 0.1 - 0.35) / nP)
            z = roof_z(x)
            c = Vector((x, 0.0, z)) - nr * 0.102
            port.member(det, (c.x, WH["y0"] - WH["ovh"] + 0.05, c.z), (c.x, WH["y1"] + WH["ovh"] - 0.05, c.z), zs, "metal_paint",
                        up=tuple(nr))
            if abs(x) <= xc + 0.05:
                for yf in frames:                       # clip de larguero atornillado a la viga
                    det.box((x + 0.0016, yf - 0.004, z - 0.235), (x + 0.08, yf + 0.004, z - 0.06), "metal_paint")
                    port.bolt(det, _T(x - 0.0015, yf + 0.03, z - 0.13) @ Matrix.Rotation(-math.pi / 2, 4, "Y"), d=0.016, stud=0.01)
    for side in ("front", "back", "west", "east"):
        a0, a1, face = wh_side(side)
        M = ac.panel_matrix(side, a0, a1, face, DECK_Z)
        L = a1 - a0
        for zg in (1.95, 3.9, 5.85, 7.35):
            if side in ("front", "back") and zg > 7.0:
                continue
            gt = MB()
            for (ua, ub) in _gaps(0.3, L - 0.3, [o for _, o in ops[side] if o[2] < zg + 0.1 < o[3] + 0.2]):
                port.member(gt, (ua, 0.0, zg), (ub, 0.0, zg),
                            [(0.0016, 0.0046, -0.08, 0.08), (0.0046, 0.066, 0.077, 0.08), (0.0046, 0.066, -0.08, -0.077),
                             (0.063, 0.066, 0.058, 0.077), (0.063, 0.066, -0.077, -0.058)], "metal_paint", up=(0, 0, 1))
            det.join(gt, M)
    # contravientos en cruz (barras) en las crujías extremas del techo
    def rod(p0, p1, t=0.3):
        p0, p1 = Vector(p0), Vector(p1)
        det.cyl(p0, p1, 0.012, seg=6, mat="metal_rust")
        Mf, Lr = port.frame_on(p0, p1)
        port.lathe(det, [(0.0125, -0.17), (0.016, -0.14), (0.016, -0.11), (0.024, -0.1), (0.024, 0.1), (0.016, 0.11),
                         (0.016, 0.14), (0.0125, 0.17)], seg=8, mat="metal_rust",
                   M=Mf @ _T(Lr * t, 0, 0) @ Matrix.Rotation(math.pi / 2, 4, "Y"))
    for (ya, yb) in ((frames[0], frames[1]), (frames[-2], frames[-1])):
        for sg in (-1, 1):
            xa, xb = sg * (xc - 0.1), sg * 0.4
            rod((xa, ya + 0.12, roof_z(xa) - 0.25), (xb, yb - 0.12, roof_z(xb) - 0.25), 0.3)
            rod((xa, yb - 0.12, roof_z(xa) - 0.25), (xb, ya + 0.12, roof_z(xb) - 0.25), 0.7)
        x = -xc
        z0, z1 = DECK_Z + PL + 0.35, DECK_Z + WH["eave"] - 0.9
        rod((x, ya + 0.14, z0), (x, yb - 0.14, z1), 0.35)
        rod((x, yb - 0.14, z0), (x, ya + 0.14, z1), 0.65)
        for (yy, zz) in ((ya + 0.125, z0), (ya + 0.125, z1), (yb - 0.125, z0), (yb - 0.125, z1)):
            sgn = 1 if yy < (ya + yb) / 2 else -1
            det.box((x - 0.005, min(yy, yy + sgn * 0.16), zz - 0.07), (x + 0.005, max(yy, yy + sgn * 0.16), zz + 0.07),
                    "metal_paint")
    # esquineros y tapajuntas del alero
    for (x, y) in ((WH["x0"], WH["y0"]), (WH["x1"], WH["y0"]), (WH["x0"], WH["y1"]), (WH["x1"], WH["y1"])):
        sx = -1 if x < 0 else 1
        sy = -1 if y < 10 else 1
        cx0, cx1 = sorted((x - sx * 0.02, x + sx * 0.05))
        cy0, cy1 = sorted((y - sy * 0.15, y + sy * 0.05))
        det.box((cx0, cy0, DECK_Z + PL), (cx1, cy1, DECK_Z + WH["eave"] - 0.02), "metal_paint")
        cx0, cx1 = sorted((x - sx * 0.15, x + sx * 0.05))
        cy0, cy1 = sorted((y - sy * 0.02, y + sy * 0.05))
        det.box((cx0, cy0, DECK_Z + PL), (cx1, cy1, DECK_Z + WH["eave"] - 0.02), "metal_paint")
    stats["roof"] = build_roof(roof, det, r)
    stats["mezzanine"] = build_mezzanine(inter, det, r)
    return stats


def _gaps(a, b, ops):
    """Tramos de [a, b] fuera de los vanos (u0, u1, ...)."""
    out, cur = [], a
    for o in sorted(ops):
        if o[0] - 0.05 > cur:
            out.append((cur, o[0] - 0.05))
        cur = max(cur, o[1] + 0.05)
    if b > cur:
        out.append((cur, b))
    return out


def factory_window(mb, M, w, h, r):
    """Ventana alta de taller: marco y montantes de acero, vidrios en cuadrícula (muchos rotos)."""
    t = 0.05
    for (u0, u1, z0, z1) in [(0, w, 0, t), (0, w, h - t, h), (0, t, 0, h), (w - t, w, 0, h)]:
        mb.box((u0, 0.02, z0), (u1, 0.08, z1), "metal_paint", m=M)
    nc, nr = int(round(w / 0.5)), 2
    for i in range(1, nc):
        u = i * w / nc
        mb.box((u - 0.015, 0.03, t), (u + 0.015, 0.07, h - t), "metal_paint", m=M)
    mb.box((t, 0.03, h / 2 - 0.015), (w - t, 0.07, h / 2 + 0.015), "metal_paint", m=M)
    for i in range(nc):
        for j in range(nr):
            if r.random() < 0.45:
                continue
            u0, u1 = i * w / nc + 0.02, (i + 1) * w / nc - 0.02
            z0, z1 = j * h / nr + 0.02, (j + 1) * h / nr - 0.02
            if r.random() < 0.3:     # vidrio partido: queda la mitad de abajo en diagonal
                pts = [(u0, 0.048, z0), (u1, 0.048, z0), (u1, 0.048, z0 + (z1 - z0) * float(r.uniform(0.2, 0.7))),
                       (u0, 0.048, z0 + (z1 - z0) * float(r.uniform(0.3, 0.9)))]
                tmp = MB()
                tmp.plate([(p[0], p[2]) for p in pts], 0.004, "glass", m=Matrix.Rotation(math.pi / 2, 4, "X"))
                mb.join(tmp, M @ _T(0, 0.052, 0))
            else:
                mb.box((u0, 0.046, z0), (u1, 0.05, z1), "glass", m=M)


def build_roof(roof, det, r):
    """Dos aguas de lámina trapezoidal (óxido) sobre largueros, con tragaluces, huecos y hojas levantadas; caballete,
    canalones y bajantes."""
    p = math.radians(WH["pitch"])
    ov = WH["ovh"]
    xe = WH["x1"] + ov
    Ls = xe / math.cos(p)
    ylen = (WH["y1"] - WH["y0"]) + 2 * ov
    stats = dict(sheets=0, missing=0, skylights=0)
    holes = [(5.0, 9.0, 0.45, 0.85), (16.0, 19.0, 0.2, 0.55)]     # (u0, u1, s0, s1) en fracción de faldón (solo faldón este)
    for sg in (1, -1):
        s = Vector((-sg * math.cos(p), 0.0, math.sin(p)))
        n = Vector((sg * math.sin(p), 0.0, math.cos(p)))
        X = Vector((0.0, sg * 1.0, 0.0))
        Y = -n
        o = Vector((sg * xe, WH["y0"] - ov if sg > 0 else WH["y1"] + ov, roof_z(xe)))
        M = Matrix(((X.x, Y.x, s.x, o.x), (X.y, Y.y, s.y, o.y), (X.z, Y.z, s.z, o.z), (0, 0, 0, 1)))
        nsh = int(math.ceil(ylen))
        for k in range(nsh):
            u0, u1 = k * 1.0, min(ylen, (k + 1) * 1.0)
            for (za, zb) in ((0.0, Ls * 0.52), (Ls * 0.5, Ls - 0.02)):
                if sg > 0 and any(h[0] <= u0 < h[1] and h[2] * Ls <= (za + zb) / 2 <= h[3] * Ls for h in holes):
                    stats["missing"] += 1
                    continue
                if r.random() < 0.03:
                    stats["missing"] += 1
                    continue
                mat = "metal_rust"
                if za > 0 and k % 5 == 2:
                    if r.random() < 0.3:
                        stats["missing"] += 1
                        continue
                    mat = "glass"
                    stats["skylights"] += 1
                hinge = 0.0
                if za == 0.0 and r.random() < 0.04:
                    hinge = float(r.uniform(0.03, 0.07))    # hoja del alero levantada por el viento (0,2–0,4 m)
                sheet(roof, u0 + 0.003, u1 - 0.003, lambda u, a=za: a, lambda u, b=zb: b, mat, M, hinge=hinge, out=-1.0,
                      lift=0.0 if za == 0.0 else SHEET_T * 2.5)
                stats["sheets"] += 1
        # caballete
        roof.box((WH["y0"] - ov, -0.003, roof_z(0.0) + 0.03), (WH["y1"] + ov, 0.003, roof_z(0.0) + 0.06), "metal_rust",
                 m=Matrix(((0, 1, 0, 0), (1, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1))))
        member(roof, (sg * 0.32, WH["y0"] - ov, roof_z(0.32) + 0.035), (sg * 0.32, WH["y1"] + ov, roof_z(0.32) + 0.035),
               [(-0.32, 0.32, -0.003, 0.003)], "metal_rust", up=(sg * math.sin(p), 0, math.cos(p)))
        # tapajuntas de remate en los hastiales
        for yb in (WH["y0"] - ov, WH["y1"] + ov):
            member(roof, (sg * xe, yb, roof_z(xe) + 0.02), (0.0, yb, roof_z(0.0) + 0.06), [(-0.05, 0.05, -0.06, 0.05)],
                   "metal_paint")
    # canalones y bajantes
    from kit import circulation as circ
    for sg in (-1, 1):
        x = sg * (xe + 0.07)
        path = [(x, WH["y0"] - ov + 0.1, roof_z(xe) - 0.06), (x, WH["y1"] + ov - 0.1, roof_z(xe) - 0.06)]
        if sg > 0:
            g = circ.gutter(path, seed=int(r.integers(1e6)), outlets=(1.0,), mat="metal_paint")
        else:
            g = circ.gutter(list(reversed(path)), seed=int(r.integers(1e6)), outlets=(1.0,), mat="metal_paint")
        det.join(g)
        for top in g.meta.get("outlets", []):
            bottom = Vector((top[0] - sg * 0.18, top[1], DECK_Z + 0.05))
            M = Matrix(((0, -sg, 0, 0), (sg, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
            Mi = M.inverted()
            pipe = circ.downpipe(Mi @ Vector(top), Mi @ bottom, seed=int(r.integers(1e6)), mat="metal_paint")
            det.join(pipe, M)
    return stats


def build_mezzanine(inter, det, r):
    """Entrepiso de oficina en la esquina NE: plataforma de lámina estriada a +3,2, oficina de panel y escalera de acero."""
    z = DECK_Z + 3.2
    x0, x1, y0, y1 = 5.5, WH["x1"] - 0.4, WH["y0"] + 15.5, WH["y1"] - 0.3
    for (x, y) in ((x0 + 0.1, y0 + 0.1), (x0 + 0.1, y1 - 0.1), (x1 - 0.1, y0 + 0.1), (8.2, y0 + 0.1)):
        inter.box((x - 0.1, y - 0.1, DECK_Z), (x + 0.1, y + 0.1, z - 0.3), "metal_paint")
    for y in (y0 + 0.1, (y0 + y1) / 2, y1 - 0.1):
        inter.box((x0, y - 0.075, z - 0.3), (x1, y + 0.075, z - 0.012), "metal_paint")
    inter.box((x0, y0, z - 0.012), (x1, y1, z), "metal_rust")
    # oficina de panel (puerta y ventanas rotas)
    yo = WH["y0"] + 18.0
    H = 2.6
    M = ac.panel_matrix("front", x0, x1, yo, z)
    wall_with_openings(inter, x1 - x0, H, 0.08, [(0.6, 1.5, 0.0, 2.1), (2.0, 4.6, 1.0, 2.2)], mat_out="metal_paint",
                       mat_in="metal_paint", mat_reveal="metal_paint", m=M)
    from kit import openings as op
    det.join(op.door("metal", 0.9, 2.1, 0.08, seed=int(r.integers(1e6)), open_angle=70), M @ _T(0.6, 0, 0.0))
    factory_window(det, M @ _T(2.0, 0.0, 1.0), 2.6, 1.2, r)
    Mw = ac.panel_matrix("west", yo, y1, x0, z)
    wall_with_openings(inter, y1 - yo, H, 0.08, [(1.6, 3.6, 1.0, 2.2)], mat_out="metal_paint", mat_in="metal_paint",
                       mat_reveal="metal_paint", m=Mw)
    factory_window(det, Mw @ _T(1.6, 0, 1.0), 2.0, 1.2, r)
    inter.box((x0, yo, z + H), (x1, y1, z + H + 0.06), "metal_paint")
    # barandal en el borde libre del pasillo (y = y0) y en el lado oeste
    from kit import circulation as circ
    det.join(circ.railing("tube_metal", length=x1 - x0 - 1.3, h=1.0, seed=int(r.integers(1e6)), missing=0.12),
             _T(x0 + 1.3, y0 + 0.03, z))
    det.join(circ.railing("tube_metal", length=yo - y0 - 0.1, h=1.0, seed=int(r.integers(1e6)), missing=0.1),
             _T(x0 + 0.03, y0 + 0.1, z) @ Matrix.Rotation(math.pi / 2, 4, "Z"))
    # escalera recta de acero: sube en +y y llega al pasillo por el borde y = y0, entre x0 y x0 + 1,2
    n = 12
    rise = 3.2 / n
    going = 0.27
    ys = y0 - (n - 1) * going
    xa, xb = x0 + 0.05, x0 + 1.15
    for i in range(n - 1):
        yt = ys + i * going
        zt = DECK_Z + (i + 1) * rise
        inter.box((xa + 0.05, yt, zt - 0.012), (xb - 0.05, yt + going + 0.03, zt), "metal_rust")
    for xx in (xa, xb - 0.05):
        member(inter, (xx + 0.025, ys - 0.25, DECK_Z), (xx + 0.025, y0, z - 0.05), [(-0.025, 0.025, -0.13, 0.05)], "metal_paint",
               up=(0, 0, 1))
    pts = [(xb + 0.0, ys + i * going + going / 2, DECK_Z + (i + 1) * rise) for i in range(0, n - 1, 2)] + [(xb, y0, z)]
    det.join(circ.stair_railing(pts, h=0.95, kind="tube_metal", seed=int(r.integers(1e6)), missing=0.1))
    return dict(z=z, risers=n)


# ------------------------------------------------------------------------------------------------------------ caseta
def build_annex(shell, inter, det, r):
    from kit import openings as op
    from kit import services as sv
    A = ANNEX
    t, H = A["t"], A["h"]
    sides = {
        "front": (A["x0"], A["x1"], A["y0"], [("door", (0.4, 1.4, 0.0, 2.1)), ("window", (1.9, 3.0, 0.9, 2.0))]),
        "back": (A["x0"], A["x1"], A["y1"], [("window", (1.0, 2.2, 0.9, 2.0))]),
        "west": (A["y0"], A["y1"], A["x0"], [("window", (1.0, 2.2, 0.9, 2.0)), ("window", (3.6, 4.8, 0.9, 2.0))]),
        "east": (A["y0"], A["y1"], A["x1"], [("door_in", (2.0, 3.0, 0.0, 2.1))]),
    }
    for side, (a0, a1, face, ops) in sides.items():
        L = a1 - a0
        M = ac.panel_matrix(side, a0, a1, face, DECK_Z)
        if side in ("west", "east"):
            M = ac.panel_matrix(side, a0 + t, a1 - t, face, DECK_Z)
            L = L - 2 * t
            ops = [(k, (o[0] - t, o[1] - t, o[2], o[3])) for k, o in ops]
        wall_with_openings(shell, L, H, t, [o for _, o in ops], mat_out="plaster", mat_in="plaster", mat_reveal="concrete", m=M)
        for kind, (u0, u1, v0, v1) in ops:
            w, h = u1 - u0, v1 - v0
            Mo = M @ _T(u0, 0, v0)
            seed = int(r.integers(1e6))
            if kind == "window":
                k = "boarded" if r.random() < 0.35 else "sliding"
                det.join(op.window(k, w, h, t, seed=seed, broken=float(r.uniform(0.6, 1.0)), curtain=r.random() < 0.4), Mo)
                if k != "boarded" and r.random() < 0.5:
                    det.join(op.security_grille(w, h, seed=seed + 1), Mo)
            else:
                det.join(op.door("metal", w, h, t, seed=seed, open_angle=float(r.uniform(30, 80))), Mo)
    # losa de azotea con pretil bajo
    shell.box((A["x0"] - 0.05, A["y0"] - 0.05, DECK_Z + H), (A["x1"] + 0.05, A["y1"] + 0.05, DECK_Z + H + 0.2), "concrete")
    for (a, b) in [((A["x0"] - 0.05, A["y0"] - 0.05), (A["x1"] + 0.05, A["y0"] + 0.1)),
                   ((A["x0"] - 0.05, A["y1"] - 0.1), (A["x1"] + 0.05, A["y1"] + 0.05)),
                   ((A["x0"] - 0.05, A["y0"] + 0.1), (A["x0"] + 0.1, A["y1"] - 0.1))]:
        shell.box((a[0], a[1], DECK_Z + H + 0.2), (b[0], b[1], DECK_Z + H + 0.5), "concrete")
    # servicios: aire acondicionado, medidor, letrero
    det.join(sv.ac_unit("window", seed=int(r.integers(1e6)), detail="mid"),
             _T(A["x0"], A["y0"] + 4.4, DECK_Z + 2.35) @ _Rz(90))
    det.join(sv.meter_box(seed=int(r.integers(1e6)), open_door=True, detail="mid"), _T(A["x1"] - 0.8, A["y0"], DECK_Z + 1.4))
    # mobiliario: escritorio volcado y papeles
    import interior_dress as idr
    tmp = MB()
    tmp.box((0, 0, 0.72), (1.4, 0.7, 0.75), "wood")
    for (x, y) in ((0.05, 0.05), (1.3, 0.05), (0.05, 0.6), (1.3, 0.6)):
        tmp.box((x, y, 0), (x + 0.05, y + 0.05, 0.72), "metal_paint")
    inter.join(tmp, _T(A["x0"] + 0.4, A["y0"] + 4.2, DECK_Z) @ _Rz(8))
    tmp = MB()
    idr.trash(tmp, r, n_papers=9, n_bottles=2)
    det.join(tmp, _T(A["x0"] + 2.0, A["y0"] + 2.0, DECK_Z))
    tmp = MB()
    idr.broken_chair(tmp, r)
    det.join(tmp, _T(A["x0"] + 1.6, A["y0"] + 3.3, DECK_Z))


# ------------------------------------------------------------------------------------------------------------ contenedores
def build_containers(shell, r):
    out = []
    for c in CONTAINERS:
        tmp = port.container(int(r.integers(1e6)), open_doors=c["open"])
        M = _T(c["x"], c["y"], c["z"]) @ _Rz(c["rot"])
        if c["rot"] == 90:
            M = _T(c["x"] + C_W, c["y"], c["z"]) @ _Rz(90)
        shell.join(tmp, M)
        out.append(M)
    return out


# ------------------------------------------------------------------------------------------------------------ grúa, postes
def build_crane(det, r):
    """Grúa de pedestal (kit.port) junto al frente de atraque: pluma sobre el barco (+y) a 38°, gancho en reposo a ~5 m."""
    cx, cy = CRANE_XY
    det.join(port.pedestal_crane(int(r.integers(1e6)), yaw=158.0, luff=38.0, boom_len=15.0, hook_z=2.5), _T(cx, cy, DECK_Z))


def light_pole(det, p, r, lean=0.0, broken=False, yaw=None):
    """Poste de alumbrado (kit.port) sobre la cubierta; yaw orienta el brazo (por defecto hacia el centro de la cubierta)."""
    x, y = p
    if yaw is None:
        yaw = math.degrees(math.atan2(-(y - 20.0), -(x - 0.0))) + 90.0
    tilt = Matrix.Rotation(math.radians(lean), 4, "X")
    det.join(port.light_pole(9.0, int(r.integers(1e6)), broken=broken), _T(x, y, DECK_Z) @ _Rz(yaw) @ tilt)


# ------------------------------------------------------------------------------------------------------------ objetos sueltos
def pallet(mb, M, r):
    tmp = MB()
    for y in (0.0, 0.45, 0.9):
        for x in (0.0, 0.55, 1.1):
            tmp.box((x, y, 0.022), (x + 0.1, y + 0.1, 0.122), "wood_grey")
        tmp.box((0.0, y, 0.0), (1.2, y + 0.1, 0.022), "wood_grey")
    n = 0
    for k in range(7):
        x = k * 0.183
        if r.random() < 0.12:
            continue
        tmp.box((x, 0.0, 0.122), (x + 0.1, 1.0, 0.144), "wood_grey")
        n += 1
    mb.join(tmp, M)


def pallet_stack(mb, p, r, n=None, rot=0.0):
    n = n or int(r.integers(2, 8))
    for k in range(n):
        M = _T(*p) @ _Rz(rot + float(r.uniform(-6, 6))) @ _T(float(r.uniform(-0.04, 0.04)), float(r.uniform(-0.04, 0.04)),
                                                                k * 0.144)
        pallet(mb, M, r)


def crate(mb, p, size, r, rot=0.0):
    sx, sy, sz = size
    tmp = MB()
    tmp.box((0.03, 0.03, 0.03), (sx - 0.03, sy - 0.03, sz - 0.03), "wood")
    for (x0, y0, x1, y1) in ((0, 0, 0.06, 0.06), (sx - 0.06, 0, sx, 0.06), (0, sy - 0.06, 0.06, sy), (sx - 0.06, sy - 0.06, sx, sy)):
        tmp.box((x0, y0, 0), (x1, y1, sz), "wood_dark")
    for z in (0.0, sz - 0.06):
        tmp.box((0, 0, z), (sx, 0.06, z + 0.06), "wood_dark")
        tmp.box((0, sy - 0.06, z), (sx, sy, z + 0.06), "wood_dark")
    mb.join(tmp, _T(*p) @ _Rz(rot))


def drum(mb, p, r, lying=False, rot=0.0):
    """Tambo de 200 L (kit.port), de pie o acostado sobre su costado."""
    tmp = port.drum(int(r.integers(1e6)))
    M = _T(*p) @ _Rz(rot + float(r.uniform(0, 360)) * (0 if lying else 1))
    if lying:
        M = _T(p[0], p[1], p[2] + 0.293) @ _Rz(rot) @ Matrix.Rotation(math.pi / 2, 4, "Y") @ _T(0, 0, -0.44)
    mb.join(tmp, M)


def rope_coil(mb, p, r, R=0.4, turns=5):
    pts = []
    for i in range(turns * 16 + 1):
        a = 2 * math.pi * i / 16
        rr = R - 0.035 * (i / 16) * 0.6
        pts.append((p[0] + rr * math.cos(a), p[1] + rr * math.sin(a), p[2] + 0.025 + 0.045 * (i // 16)))
    mb.tube(pts, 0.022, seg=6, mat="plastic")


def sand_drift(mb, p, sx, sy, h, r, zf=None):
    """Montículo bajo de arena (domo achatado); zf(x, y) da la cota del piso bajo el montículo (rampa)."""
    n, m = 10, 4
    cx, cy, cz = p
    zf = zf or (lambda x, y: cz)
    rings = []
    for j in range(1, m + 1):
        t = j / m
        ring = []
        for i in range(n):
            a = 2 * math.pi * i / n
            k = float(r.uniform(0.85, 1.1))
            px, py = cx + sx * t * k * math.cos(a), cy + sy * t * k * math.sin(a)
            ring.append(mb.bm.verts.new((px, py, zf(px, py) + h * (1 - t * t))))
        rings.append(ring)
    top = mb.bm.verts.new((cx, cy, zf(cx, cy) + h))
    for i in range(n):
        mb.face([top, rings[0][i], rings[0][(i + 1) % n]], "sand")
    for j in range(m - 1):
        for i in range(n):
            a, b = rings[j], rings[j + 1]
            mb.face([a[i], b[i], b[(i + 1) % n], a[(i + 1) % n]], "sand")
    bot = [mb.bm.verts.new((v.co.x, v.co.y, zf(v.co.x, v.co.y) - 0.002)) for v in rings[-1]]
    for i in range(n):
        mb.face([rings[-1][i], bot[i], bot[(i + 1) % n], rings[-1][(i + 1) % n]], "sand")
    mb.face(list(reversed(bot)), "sand")


def build_props(inter, det, sk, r):
    """Objetos sueltos. Los carriles de circulación alrededor de la nave quedan libres: las cosas van pegadas a muros y orillas."""
    from kit import damage as dm
    from kit import services as sv
    z = DECK_Z
    X0, X1, Y0, Y1 = WH["x0"], WH["x1"], WH["y0"], WH["y1"]
    ax0, ax1, ay0, ay1 = DECK_A
    bx0, bx1, by0, by1 = DECK_B
    # dentro de la nave (coordenadas relativas a su esquina SO)
    W = lambda x, y: (X0 + x, Y0 + y, z)  # noqa: E731
    for (p, n, rot) in ((W(1.5, 2.0), 6, 3), (W(1.2, 3.4), 4, -5), (W(4.0, 21.0), 3, 10), (W(13.5, 18.8), 5, 30),
                        (W(9.0, 8.0), 2, 60)):
        pallet_stack(inter, p, r, n=n, rot=rot)
    for k in range(6):
        pallet(det, _T(float(r.uniform(X0 + 3, X1 - 3)), float(r.uniform(Y0 + 2, Y1 - 2)), z) @ _Rz(float(r.uniform(0, 360))) @
               Matrix.Rotation(float(r.uniform(-0.25, 0.25)), 4, "X"), r)
    for (p, sz, rot) in ((W(1.4, 9.0), (1.2, 1.0, 1.0), 4), (W(1.6, 10.3), (1.0, 1.0, 0.8), -3), (W(1.5, 9.2), (0.9, 0.8, 0.7), 12),
                         (W(17.5, 3.0), (1.5, 1.2, 1.1), 20), (W(6.5, 22.2), (1.3, 1.0, 1.0), 0)):
        crate(inter, p, sz, r, rot=rot)
    for p in (W(1.2, 16.5), W(1.8, 17.3), W(1.1, 17.9), W(20.5, 13.0), W(19.8, 13.6)):
        drum(inter, p, r)
    drum(det, W(14.5, 11.0), r, lying=True, rot=40)
    drum(det, W(6.0, 14.0), r, lying=True, rot=-20)
    for p in (W(4.5, 5.0), W(15.0, 22.0), W(20.0, 4.0)):
        rope_coil(det, p, r)
    for (p, sx, sy, h) in ((W(0.8, 14.0), 0.9, 3.2, 0.18), (W(11.0, 0.9), 3.5, 0.8, 0.22), (W(21.2, 6.5), 0.8, 2.4, 0.15),
                           (W(8.0, 23.0), 2.0, 0.7, 0.12)):
        sand_drift(inter, p, sx, sy, h, r)
    for k in range(10):
        det.join(dm.chunk(size=float(r.uniform(0.1, 0.3)), seed=int(r.integers(1e6)), detail="low"),
                 _T(float(r.uniform(X0 + 2, X1 - 2)), float(r.uniform(Y0 + 2, Y1 - 2)), z))
    # en la cubierta: junto a las orillas
    for (p, n, rot) in (((ax1 - 2.5, ay0 + 2.0, z), 4, 0), ((bx0 + 3.0, by1 - 2.5, z), 3, 15), ((ax0 + 1.5, ay1 - 4.0, z), 5, -8),
                        ((bx1 - 6.0, by0 + 1.2, z), 2, 40), ((ax1 - 1.6, ay0 + 14.0, z), 3, 5)):
        pallet_stack(inter, p, r, n=n, rot=rot)
    for p in ((ax1 - 1.2, ay0 + 6.0, z), (ax1 - 1.9, ay0 + 6.7, z), (bx0 + 20.0, by1 - 1.6, z), (ax0 + 1.2, by0 + 5.0, z),
              (bx1 - 1.8, by1 - 1.6, z)):
        drum(inter, p, r)
    drum(det, (bx0 + 12.0, by0 + 6.0, z), r, lying=True, rot=75)
    for p in ((ax0 + 1.0, ay0 + 22.0, z), (bx0 + 44.0, by1 - 2.0, z)):
        crate(inter, p, (1.2, 1.0, 1.0), r, rot=float(r.uniform(0, 30)))
    for p in ((bx0 + 26.0, by1 - 1.8, z), (bx1 - 14.0, by0 + 2.0, z), (bx0 + 16.0, by0 + 2.5, z)):
        rope_coil(det, p, r, R=0.5)
    for p in ((bx0 + 34.0, by0 + 3.5, z + 0.13), (bx0 + 20.0, by1 - 3.0, z + 0.13)):
        tyre(det, p, r, axis="z")
    # hueco en la losa del espigón: varillas colgando y trozos
    hx0, hx1, hy0, hy1 = HOLE
    for (x, y) in ((hx0 + 0.6, hy0), (hx1 - 0.5, hy1), (hx0, (hy0 + hy1) / 2), (hx1, hy0 + 0.6)):
        det.join(dm.rebar_nest(seed=int(r.integers(1e6)), n=5, length=0.7, stump=(0.2, 0.2, 0.02), detail="low"),
                 _T(x, y, DECK_Z - 0.28) @ Matrix.Rotation(math.pi, 4, "X"))
    det.join(dm.rubble_pile(radius=0.9, seed=int(r.integers(1e6)), n=26, detail="low"), _T(hx1 + 1.3, hy0 - 0.4, z))
    for k in range(6):
        det.join(dm.chunk(size=float(r.uniform(0.15, 0.4)), seed=int(r.integers(1e6)), kind="slab", detail="low"),
                 _T(float(r.uniform(hx0 - 1.5, hx1 + 2)), float(r.uniform(hy0 - 1.2, hy1 + 1.2)), z))
    # postes de luz en las orillas (uno inclinado y uno sin luminaria) y cable hacia la nave
    for (pp, lean, broken) in POLES:
        light_pole(det, pp, r, lean=lean, broken=broken)
    det.join(sv.cable_bundle([(ax1 - 0.8, ay1 - 6.0, z + 7.6), (X1 + 0.05, Y1 - 4.0, z + 6.9)], n=3, sag=0.8,
                             seed=int(r.integers(1e6)), detail="low"))
    # letrero rasgado (sin texto) sobre la cortina del frente y arbotantes sobre las puertas
    det.join(sv.sign_torn(w=4.0, h=0.8, seed=int(r.integers(1e6)), detail="mid"), _T(0.0, Y0 - 0.05, z + 5.9))
    for (M, u) in ((ac.panel_matrix("front", X0, X1, Y0, z), 17.5), (ac.panel_matrix("east", Y0, Y1, X1, z), 7.0),
                   (ac.panel_matrix("back", X0, X1, Y1, z), 11.0)):
        det.join(sv.light_fixture("bracket", seed=int(r.integers(1e6)), detail="mid"), M @ _T(u, -0.04, 6.0))
    # arena que el viento sube a la rampa: contra los pretiles y una lengua delgada en el pie
    rz = lambda x, y: ramp_z(y)  # noqa: E731
    for (x, y, sx_, sy_, h) in ((-RAMP_X + 0.55, -21.0, 0.6, 3.6, 0.16), (RAMP_X - 0.55, -22.5, 0.55, 2.4, 0.13),
                                (-RAMP_X + 0.5, -12.0, 0.45, 1.8, 0.08), (-6.0, -23.6, 5.5, 0.9, 0.05),
                                (9.0, -23.9, 3.5, 0.6, 0.04)):
        sand_drift(inter, (x, y, ramp_z(y)), sx_, sy_, h, r, zf=rz)
    # en la arena junto a la rampa (pieza Escombro)
    sk.join(dm.rubble_pile(radius=1.2, seed=int(r.integers(1e6)), n=34, detail="low"), _T(-RAMP_X - 2.5, RAMP_Y0 + 3.0, 0.0))
    sk.join(dm.rubble_pile(radius=0.8, seed=int(r.integers(1e6)), n=20, detail="low"), _T(RAMP_X + 2.0, RAMP_Y0 + 12.0, 0.0))
    for k in range(9):
        sx = float(r.choice([-1, 1]))
        sk.join(dm.chunk(size=float(r.uniform(0.15, 0.45)), seed=int(r.integers(1e6)), detail="low"),
                _T(sx * float(r.uniform(RAMP_X + 0.8, RAMP_X + 4.0)), float(r.uniform(RAMP_Y0, -3)), 0.0) @
                _Rz(float(r.uniform(0, 360))))
    tyre(sk, (-RAMP_X - 3.4, RAMP_Y0 + 1.6, 0.13), r, axis="z")
    drum(sk, (RAMP_X + 1.8, RAMP_Y0 + 1.0, 0.0), r, lying=True, rot=30)
    sk.cyl((-RAMP_X - 3.5, -14.0, 0.18), (-RAMP_X - 2.2, -9.4, 0.15), 0.18, seg=8, mat="wood_grey")       # tronco de deriva


# ------------------------------------------------------------------------------------------------------------ grafiti
def graffiti_zones():
    """Zonas de pared por cara donde puede haber grafiti, en coordenadas de panel (u, z) del compositor:
    front u = x - gx0 · back u = gx1 - x · west u = gy1 - y · east u = y - gy0 (gx0, gx1, gy0, gy1 = graffiti_bounds)."""
    gx0, gx1, gy0, gy1 = cfg_mue()["graffiti_bounds"]
    Z = {"front": [], "back": [], "west": [], "east": []}
    K = {"front": [], "back": [], "west": [], "east": []}

    def add(side, a0, a1, z0, z1, keep=False):
        if a1 - a0 < 0.3 or z1 - z0 < 0.2:
            return
        if side == "front":
            u0, u1 = a0 - gx0, a1 - gx0
        elif side == "back":
            u0, u1 = gx1 - a1, gx1 - a0
        elif side == "west":
            u0, u1 = gy1 - a1, gy1 - a0
        else:
            u0, u1 = a0 - gy0, a1 - gy0
        (K if keep else Z)[side].append((round(u0, 3), round(z0, 3), round(u1, 3), round(z1, 3)))
    zf0, zf1 = FASCIA_Z0 + 0.05, DECK_Z - 0.05
    ax0, ax1, ay0, ay1 = DECK_A
    bx0, bx1, by0, by1 = DECK_B
    add("front", ax0, -RAMP_X - RAMP_WALL - 0.05, zf0, zf1)
    add("front", RAMP_X + RAMP_WALL + 0.05, ax1, zf0, zf1)
    add("front", ax1, bx1, zf0, zf1)
    add("back", bx0, bx1, zf0, zf1)
    add("west", ay0, by1, zf0, zf1)
    add("east", ay0, by0, zf0, zf1)
    add("east", by0, by1, zf0, zf1)
    # pretiles de la rampa (cara exterior: desde la arena; cara interior: sobre la rampa), por tramos de 2 m
    y = RAMP_Y0
    while y < -0.01:
        y2 = y + 2.0
        add("west", y, y2, 0.05, ramp_z(y) + PARAPET - 0.05)
        add("east", y, y2, 0.05, ramp_z(y) + PARAPET - 0.05)
        add("east", y, y2, ramp_z(y2) + 0.05, ramp_z(y) + PARAPET - 0.05)       # cara interior del pretil oeste
        add("west", y, y2, ramp_z(y2) + 0.05, ramp_z(y) + PARAPET - 0.05)       # cara interior del pretil este
        y = y2
    # nave: zócalo y lámina baja
    zb0, zb1 = DECK_Z + 0.08, DECK_Z + 3.5
    add("front", WH["x0"], WH["x1"], zb0, zb1)
    add("back", WH["x0"], WH["x1"], zb0, zb1)
    add("west", WH["y0"], WH["y1"], zb0, zb1)
    add("east", WH["y0"], WH["y1"], zb0, zb1)
    for side, lst in wh_openings().items():
        a0, a1, _ = wh_side(side)
        for kind, (u0, u1, v0, v1) in lst:
            if kind == "clerestory":
                continue
            if side == "front":
                add(side, a0 + u0 - 0.1, a0 + u1 + 0.1, DECK_Z, DECK_Z + v1 + 0.6, keep=True)
            elif side == "back":
                add(side, a1 - u1 - 0.1, a1 - u0 + 0.1, DECK_Z, DECK_Z + v1 + 0.6, keep=True)
            elif side == "west":
                add(side, a1 - u1 - 0.1, a1 - u0 + 0.1, DECK_Z, DECK_Z + v1 + 0.3, keep=True)
            else:
                add(side, a0 + u0 - 0.1, a0 + u1 + 0.1, DECK_Z, DECK_Z + v1 + 0.6, keep=True)
    # caseta
    A = ANNEX
    add("front", A["x0"], A["x1"], DECK_Z + 0.08, DECK_Z + A["h"])
    add("back", A["x0"], A["x1"], DECK_Z + 0.08, DECK_Z + A["h"])
    add("west", A["y0"], A["y1"], DECK_Z + 0.08, DECK_Z + A["h"])
    add("front", A["x0"] + 0.3, A["x0"] + 1.5, DECK_Z, DECK_Z + 2.2, keep=True)
    add("front", A["x0"] + 1.8, A["x0"] + 3.1, DECK_Z + 0.8, DECK_Z + 2.1, keep=True)
    add("back", A["x1"] - 2.3, A["x1"] - 0.9, DECK_Z + 0.8, DECK_Z + 2.1, keep=True)
    for (u0, u1) in ((1.0, 2.2), (3.6, 4.8)):
        add("west", A["y1"] - u1 - 0.1, A["y1"] - u0 + 0.1, DECK_Z + 0.8, DECK_Z + 2.1, keep=True)
    # contenedores (caras exteriores)
    for c in CONTAINERS:
        z0, z1 = c["z"] + 0.2, min(c["z"] + C_H - 0.15, cfg_mue()["band_top"] - 0.1)
        if z1 - z0 < 0.4:
            continue
        if c["rot"] == 90:       # largo en +y
            x0, x1, y0, y1 = c["x"], c["x"] + C_W, c["y"], c["y"] + C_L
        else:
            x0, x1, y0, y1 = c["x"], c["x"] + C_L, c["y"], c["y"] + C_W
        add("front", x0, x1, z0, z1)
        add("back", x0, x1, z0, z1)
        add("west", y0, y1, z0, z1)
        add("east", y0, y1, z0, z1)
    return Z, K


# ------------------------------------------------------------------------------------------------------------ ensamblado
def build_mue(bid="MUE_1_carga", collection_root=None, dress=True):
    cfg = cfg_mue(bid)
    cid = cfg["id"]
    root = collection_root or get_collection(cid)
    cols = {k: get_collection(f"{cid}_{k}", root) for k in ("Shell", "Details", "Interior", "Skirt", "Roof", "Damage")}
    out = {k: [] for k in cols}
    shell, det, inter, roof, sk = MB(), MB(), MB(), MB(), MB()
    r = rng(cfg["seed"])
    stats = {}
    stats["deck"] = build_deck(shell, inter, det, rng(cfg["seed"] + 1))
    stats["berth"] = build_berth(det, rng(cfg["seed"] + 2))
    build_ramp(shell, inter, det, rng(cfg["seed"] + 3))
    stats["warehouse"] = build_warehouse(shell, inter, det, roof, rng(cfg["seed"] + 4))
    build_annex(shell, inter, det, rng(cfg["seed"] + 5))
    build_containers(shell, rng(cfg["seed"] + 6))
    if dress:
        build_crane(det, rng(cfg["seed"] + 7))
        build_props(inter, det, sk, rng(cfg["seed"] + 8))
    del r
    for nm, mb in (("Shell", shell), ("Details", det), ("Interior", inter), ("Roof", roof), ("Skirt", sk)):
        if len(mb.bm.faces):
            out[nm].append(mb.finish(f"{cid}_{nm}", cols[nm], uv_size=2.0, merge=0))
    out["stats"] = stats
    out["cfg"] = cfg
    return out
