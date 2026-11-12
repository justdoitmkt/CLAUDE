"""gra_builder.py — GRA_1_tienda: granero de una granja de la costa seca mexicana con una tienda comunitaria chica al lado.

Ejes de Blender, metros; fachada principal hacia -Y; pivote al centro del granero a nivel de piso (z = 0). Sin terreno.
  granero  x -6..6 · y -8..8: base de block 1,2 m, muros de tabla roja con tapajuntas hasta el alero (4,2 m), techo a dos aguas
           quebrado (gambrel) de lámina galvanizada: quiebre en x ±4,1 / z 7,0, cumbrera a 8,5. Hastial del frente con puertas
           corredizas (vano 4,0 x 3,6), puerta del tapanco y viga de polea; hastial trasero con puerta de 2,4 m.
           Dentro: postes y vigas de madera con tornapuntas, tapanco al poniente (z 3,3), corrales vacíos al oriente.
  tejaban  al poniente, x -10..-6 · y -6..6, sobre postes; bajo él pacas, costales y un corral vacío.
  tienda   x 9,5..15,5 · y -8..0: block aplanado amarillo con zoclo azul, losa con pretil (COMMUNITY STORE), tejaban de lámina
           en postes sobre el pórtico, ventanilla con barrotes. Dentro: piso de barro, mostrador, munición, botiquín,
           abarrotes, refrigerador de cerveza.
Grafiti (regla R-GRAF): solo un par de piezas chicanas en el costado oriente del granero (graffiti_gra.py).
Cumple R-AAA (CLAUDE.md): utilería de kit/farm.py y kit/store.py; aquí la arquitectura con su construcción real.
"""
import math

import bpy  # noqa: F401
import numpy as np
from mathutils import Matrix, Vector

import apt_common as ac
from kit import clinic as cl
from kit import services as sv
from kit.common import MB, get_collection, rng, wall_with_openings

# ---------------------------------------------------------------------------------------------------------- granero
BX0, BX1, BY0, BY1 = -6.0, 6.0, -8.0, 8.0
TB = 0.20                       # block
TW = 0.06                       # tabla + bastidor (cara exterior al paño del block + 2 cm de vuelo)
H_BASE = 1.2
H_EAVE = 4.2
KNEE = (4.1, 7.0)
RIDGE = 8.5
LOFT = 3.30                     # piso del tapanco
OVH_E, OVH_G = 0.30, 0.35       # vuelo del techo en aleros y en hastiales
DOOR_W, DOOR_H = 4.0, 3.6
LOFT_DOOR = (-0.8, 0.8, 5.0, 6.8)
# tejaban poniente
LX0, LY0, LY1 = -10.0, -6.0, 6.0
# ---------------------------------------------------------------------------------------------------------- tienda
SX0, SX1, SY0, SY1 = 9.5, 15.5, -8.0, 0.0
TS = 0.20
S_FFL, S_CEIL, S_SB, S_ST, S_PARA = 0.15, 3.00, 3.00, 3.20, 3.75
PORCH_Y = -10.1


def _T(x=0.0, y=0.0, z=0.0):
    return Matrix.Translation((x, y, z))


def _Rz(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Z")


def _Rx(deg):
    return Matrix.Rotation(math.radians(deg), 4, "X")


def _Ry(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Y")


def face_to(d):
    """Giro en Z para que el frente local (-Y) de una pieza mire hacia d ('-y', '+x', '+y', '-x')."""
    return _Rz({"-y": 0, "+x": 90, "+y": 180, "-x": -90}[d])


def cfg_gra(bid="GRA_1_tienda"):
    fp = [(BX0, BX1, BY0, BY1), (SX0, SX1, SY0, SY1)]
    return dict(id=bid, seed=91, xs=[LX0, SX1], ys=[PORCH_Y, BY1], h=[0.0], band_top=2.6,
                graffiti_bounds=(LX0 - 0.5, SX1 + 0.5, PORCH_Y - 0.5, BY1 + 0.5), graffiti_px_per_m=150.0,
                exterior_footprint=fp,
                lookdev=dict(base_z=0.0, graffiti_mats=("block", "wood_red"), paint_tint=(0.98, 0.90, 0.62), wear=0.25,
                             band=(1.0, (0.02, 0.05, 0.16)), paint_sat=1.0))


# ------------------------------------------------------------------------------------------------------------ registros
LIGHTS = []        # focos para el motor
PROXIES = []       # cajas de colisión de la utilería (va en Mobiliario; su colisión simple, en Colision)


def _proxy(piece, M, pad=0.0):
    pts = [M @ v.co for v in piece.bm.verts]
    if not pts:
        return
    mn = [min(p[i] for p in pts) - pad for i in range(3)]
    mx = [max(p[i] for p in pts) + pad for i in range(3)]
    PROXIES.append([[round(c, 3) for c in mn], [round(c, 3) for c in mx]])


def gable_top(x):
    """Altura del perfil gambrel (cara exterior del muro) en x."""
    ax = abs(x)
    if ax >= BX1:
        return H_EAVE
    if ax >= KNEE[0]:
        return H_EAVE + (KNEE[1] - H_EAVE) * (BX1 - ax) / (BX1 - KNEE[0])
    return KNEE[1] + (RIDGE - KNEE[1]) * (KNEE[0] - ax) / KNEE[0]


# ------------------------------------------------------------------------------------------------- muro poligonal
def poly_wall(mb, M, L, top, z0, holes, t, mat_out, mat_in, mat_rev, kinks=()):
    """Muro de espesor t en coordenadas locales del muro (u 0..L, v = z, cara exterior y = 0, interior y = t) con borde
    superior top(u) lineal entre quiebres `kinks`, desde v = z0, con vanos rectangulares `holes` [(u0, u1, v0, v1)].
    Se arma por franjas verticales entre todos los quiebres y bordes de vano (sin booleanos), con los vértices soldados."""
    us = sorted({0.0, round(L, 5)} | {round(k, 5) for k in kinks if 0 < k < L} | {round(h[i], 5) for h in holes for i in (0, 1)})
    cache = {}

    def V(u, v, y):
        k = (round(u, 5), round(v, 5), round(y, 5))
        if k not in cache:
            cache[k] = mb.bm.verts.new(M @ Vector((u, y, v)))
        return cache[k]

    def quad(a, b, c, d, mat):
        f = mb.face([a, b, c, d], mat)
        return f
    for ua, ub in zip(us[:-1], us[1:]):
        ta, tb = top(ua), top(ub)
        cut = sorted([(h[2], h[3]) for h in holes if h[0] <= ua + 1e-6 and h[1] >= ub - 1e-6])
        spans, cur = [], z0
        for (v0, v1) in cut:
            if v0 > cur + 1e-6:
                spans.append((cur, v0, False))
            cur = max(cur, v1)
        spans.append((cur, None, True))                      # el último tramo llega al borde superior
        for (va, vb, to_top) in spans:
            vba, vbb = (ta, tb) if to_top else (vb, vb)
            if min(vba, vbb) <= va + 1e-6:
                continue
            quad(V(ua, va, 0), V(ub, va, 0), V(ub, vbb, 0), V(ua, vba, 0), mat_out)          # cara exterior (-y)
            quad(V(ua, vba, t), V(ub, vbb, t), V(ub, va, t), V(ua, va, t), mat_in)           # cara interior (+y)
            quad(V(ua, vba, 0), V(ub, vbb, 0), V(ub, vbb, t), V(ua, vba, t), mat_out if to_top else mat_rev)   # canto superior
            if va > z0 + 1e-6:                                                              # dintel (cara inferior)
                quad(V(ua, va, t), V(ub, va, t), V(ub, va, 0), V(ua, va, 0), mat_rev)
            for (u, vh) in ((ua, vba), (ub, vbb)):                                          # extremos del muro
                if abs(u) < 1e-6:
                    quad(V(u, va, t), V(u, va, 0), V(u, vh, 0), V(u, vh, t), mat_out)        # normal -u
                elif abs(u - L) < 1e-6:
                    quad(V(u, va, 0), V(u, va, t), V(u, vh, t), V(u, vh, 0), mat_out)        # normal +u
        for h in holes:                                                                     # jambas de los vanos
            if abs(h[0] - ua) < 1e-6:                                                       # jamba izquierda: mira a +u
                quad(V(ua, h[2], t), V(ua, h[3], t), V(ua, h[3], 0), V(ua, h[2], 0), mat_rev)
            if abs(h[1] - ub) < 1e-6:                                                       # jamba derecha: mira a -u
                quad(V(ub, h[2], 0), V(ub, h[3], 0), V(ub, h[3], t), V(ub, h[2], t), mat_rev)


def _u_of(side, a0, a1):
    return {"front": lambda w: w - a0, "back": lambda w: a1 - w, "west": lambda w: a1 - w, "east": lambda w: w - a0}[side]


# ------------------------------------------------------------------------------------------------- granero: muros
BARN_OPS = {}


def barn_walls(shell, det, inter):
    """Base de block (aplanado de cemento por dentro) y muros de tabla roja con tapajuntas; vanos de puertas y ventanas."""
    sides = {"front": (BX0, BX1, BY0), "back": (BX0, BX1, BY1), "west": (BY0 + TB, BY1 - TB, BX0), "east": (BY0 + TB, BY1 - TB, BX1)}
    # vanos en coordenadas del mundo: (lado, w0, w1, z0, z1)
    doors = [("front", -DOOR_W / 2, DOOR_W / 2, 0.0, DOOR_H), ("back", -1.2, 1.2, 0.0, 2.6), ("west", -1.5, -0.5, 0.0, 2.1),
             ("east", 4.0, 5.0, 0.0, 2.1)]
    wins = [("west", -5.4, -4.5, 2.1, 3.0), ("west", 2.6, 3.5, 2.1, 3.0), ("east", -2.5, -1.6, 2.1, 3.0), ("east", 1.6, 2.5, 2.1, 3.0),
            ("front", -3.9, -3.1, 5.2, 6.0), ("front", 3.1, 3.9, 5.2, 6.0), ("front", *LOFT_DOOR[:2], *LOFT_DOOR[2:]),
            ("back", -0.8, 0.8, 5.2, 6.4)]
    ops = {k: [] for k in sides}
    for (sd, w0, w1, z0, z1) in doors + wins:
        a0, a1, _ = sides[sd]
        u = _u_of(sd, a0, a1)
        ua, ub = sorted((u(w0), u(w1)))
        ops[sd].append((ua, ub, z0, z1))
    BARN_OPS.update(ops)
    Ms = {}
    for sd, (a0, a1, face) in sides.items():
        L = a1 - a0
        M = ac.panel_matrix(sd, a0, a1, face, 0.0)
        Ms[sd] = M
        base_ops = [(o[0], o[1], o[2], min(o[3], H_BASE)) for o in ops[sd] if o[2] < H_BASE]
        wall_with_openings(shell, L, H_BASE, TB, base_ops, mat_out="block", mat_in="block", mat_reveal="block", m=M)
        # remate de la base: cama de mortero con gotero bajo la tabla
        shell.box((0.0, -0.025, H_BASE - 0.02), (L, TB, H_BASE), "concrete", m=M)
        up_ops = [(o[0], o[1], max(o[2], H_BASE), o[3]) for o in ops[sd] if o[3] > H_BASE]
        Mw = M @ _T(0, -0.02, 0)
        if sd in ("front", "back"):
            u = _u_of(sd, a0, a1)
            xs_k = [u(x) for x in (-KNEE[0], 0.0, KNEE[0])]
            topf = (lambda uu, sd=sd, a0=a0, a1=a1: gable_top(a0 + uu if sd == "front" else a1 - uu))
            poly_wall(shell, Mw, L, topf, H_BASE, up_ops, TW, "wood_red", "wood", "wood_red", kinks=xs_k)
        else:
            wall_with_openings(shell, L, H_EAVE - H_BASE, TW, [(o[0], o[1], o[2] - H_BASE, o[3] - H_BASE) for o in up_ops],
                               mat_out="wood_red", mat_in="wood", mat_reveal="wood_red", m=Mw @ _T(0, 0, H_BASE))
        battens(det, sd, L, Mw, up_ops, a0, a1)
    corner_trim(det)
    return Ms, ops


def battens(det, sd, L, Mw, holes, a0, a1, pitch=0.30, w=0.07, d=0.022):
    """Tapajuntas cada 30 cm sobre las juntas de la tabla, de la base al alero/hastial, cortados en los vanos (con chambrana)."""
    u = _u_of(sd, a0, a1)
    r = rng(hash(sd) % 1000)
    k = 0.15
    while k < L - 0.1:
        if sd in ("front", "back"):
            wx = a0 + k if sd == "front" else a1 - k
            ztop = gable_top(wx) - 0.04
        else:
            ztop = H_EAVE - 0.02
        segs, cur = [], H_BASE + 0.02
        for h in sorted(holes, key=lambda h: h[2]):
            if h[0] - 0.06 < k < h[1] + 0.06:
                if h[2] > cur:
                    segs.append((cur, h[2] - 0.06))
                cur = max(cur, h[3] + 0.06)
        if ztop > cur:
            segs.append((cur, ztop))
        for (z0, z1) in segs:
            if z1 - z0 < 0.08:
                continue
            jit = float(r.uniform(-0.004, 0.004))
            det.box((k - w / 2 + jit, -d, z0), (k + w / 2 + jit, 0.0, z1), "wood_red", bevel=0.004, m=Mw)
        k += pitch
    # chambranas blancas de vanos (10 cm) y cornisa de goteo sobre la base
    for h in holes:
        tw = 0.10
        det.box((h[0] - tw, -d - 0.012, h[2] - (tw if h[2] > H_BASE + 0.01 else 0)), (h[0], -0.0, h[3] + tw), "paint_white", bevel=0.005, m=Mw)
        det.box((h[1], -d - 0.012, h[2] - (tw if h[2] > H_BASE + 0.01 else 0)), (h[1] + tw, -0.0, h[3] + tw), "paint_white", bevel=0.005, m=Mw)
        det.box((h[0], -d - 0.012, h[3]), (h[1], -0.0, h[3] + tw), "paint_white", bevel=0.005, m=Mw)
        if h[2] > H_BASE + 0.01:
            det.box((h[0] - 0.03, -d - 0.05, h[2] - 0.035), (h[1] + 0.03, 0.0, h[2]), "paint_white", bevel=0.006, m=Mw)
    det.box((0.0, -0.06, H_BASE), (L, 0.0, H_BASE + 0.05), "paint_white", bevel=0.006, m=Mw @ _Rx(0))


def corner_trim(det):
    """Esquineros blancos (dos tablas de 12 cm en L) en las 4 esquinas, de la base al alero."""
    for (x, y, sx, sy) in ((BX0, BY0, -1, -1), (BX1, BY0, 1, -1), (BX0, BY1, -1, 1), (BX1, BY1, 1, 1)):
        xo, yo = x + sx * 0.042, y + sy * 0.042
        det.box((min(xo, xo - sx * 0.14), min(yo, yo - sy * 0.025), H_BASE), (max(xo, xo - sx * 0.14), max(yo, yo - sy * 0.025), H_EAVE),
                "paint_white", bevel=0.006)
        det.box((min(xo, xo - sx * 0.025), min(yo, yo - sy * 0.14), H_BASE), (max(xo, xo - sx * 0.025), max(yo, yo - sy * 0.14), H_EAVE),
                "paint_white", bevel=0.006)


# ------------------------------------------------------------------------------------------------- granero: techo
ROOF_OFF = 0.16                 # la lámina queda 16 cm sobre el perfil del muro (par + polín)


def roof_z(x):
    return gable_top(x) + ROOF_OFF


def _plane_frame(p0, p1):
    """Marco de un faldón: D = dirección de la pendiente (de p0 a p1, en XZ), Y = cumbrera, N = normal hacia arriba."""
    D = (Vector(p1) - Vector(p0)).normalized()
    Y = Vector((0, 1, 0))
    N = D.cross(Y)
    if N.z < 0:
        N = -N
    return D, Y, N


def corrugated_plane(mb, p0, p1, y0, y1, mat, pitch=0.076, amp=0.009, nseg=8, screws=True, screw_rows=0.6, r=None):
    """Faldón de lámina ondulada (una sola cara, material de doble cara): ondas a lo largo de la pendiente, cresta cada `pitch`
    a lo ancho; tornillos con rondana en las crestas sobre cada polín (cada `screw_rows` m de pendiente, cada 3 ondas)."""
    D, Y, N = _plane_frame(p0, p1)
    Ls = (Vector(p1) - Vector(p0)).length
    nw = int((y1 - y0) / pitch * nseg)
    ns = max(2, int(Ls / 1.2))
    rows = []
    for j in range(ns + 1):
        s = Ls * j / ns
        row = []
        for i in range(nw + 1):
            w = y0 + (y1 - y0) * i / nw
            h = amp * math.sin(2 * math.pi * (w - y0) / pitch)
            row.append(mb.bm.verts.new(Vector(p0) + D * s + Y * (w - Vector(p0).y) + N * h))
        rows.append(row)
    for j in range(ns):
        for i in range(nw):
            f = mb.face([rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]], mat)
            f.smooth = True
    if not screws:
        return
    s = 0.15
    while s < Ls - 0.05:
        w = y0 + pitch / 4 + pitch * 3 * 0.5
        while w < y1 - 0.05:
            c = Vector(p0) + D * s + Y * (w - Vector(p0).y) + N * amp
            mb.cyl(tuple(c), tuple(c + N * 0.004), 0.011, seg=8, mat="rubber", caps=True)
            mb.cyl(tuple(c + N * 0.004), tuple(c + N * 0.0095), 0.0075, seg=6, mat="steel", caps=True)
            w += pitch * 3
        s += screw_rows


def barn_roof(roof, det, inter):
    """Cubierta gambrel de lámina galvanizada, caballete, botaguas del quiebre, frontales blancos y pares/polines/tirantes."""
    y0, y1 = BY0 - OVH_G, BY1 + OVH_G
    r = rng(17)
    for s in (-1, 1):
        xe = s * (BX1 + OVH_E)
        ze = roof_z(s * BX1) - (KNEE[1] - H_EAVE) / (BX1 - KNEE[0]) * OVH_E
        lower = ((xe, y0, ze), (s * KNEE[0], y0, roof_z(s * KNEE[0])))
        upper = ((s * KNEE[0], y0, roof_z(s * KNEE[0]) - 0.004), (0.0, y0, roof_z(0.0)))
        corrugated_plane(roof, lower[0], lower[1], y0, y1, "roof_metal_light", r=r)
        corrugated_plane(roof, upper[0], upper[1], y0, y1, "roof_metal_light", r=r)
        # botaguas del quiebre: lámina doblada que tapa el traslape del faldón alto sobre el bajo
        kx, kz = s * KNEE[0], roof_z(s * KNEE[0])
        prof = [(kx + s * 0.22, kz - 1.47 * 0.22 + 0.015), (kx, kz + 0.02), (kx - s * 0.22, kz + 0.366 * 0.22 + 0.015)]
        for (xa, za), (xb, zb) in zip(prof[:-1], prof[1:]):
            q = [(xa, y0 - 0.02, za), (xb, y0 - 0.02, zb), (xb, y1 + 0.02, zb), (xa, y1 + 0.02, za)]
            det.poly(q if s > 0 else list(reversed(q)), "roof_metal_light")
        # fascia blanca del alero
        xi = xe - s * 0.03
        det.box((min(xe, xi), y0, ze - 0.20), (max(xe, xi), y1, ze), "paint_white", bevel=0.005)
    # caballete: lámina doblada redonda sobre la cumbrera
    zr = roof_z(0.0)
    cap = [(-0.24, zr - 0.366 * 0.24 + 0.012), (-0.06, zr + 0.012), (0.0, zr + 0.035), (0.06, zr + 0.012), (0.24, zr - 0.366 * 0.24 + 0.012)]
    for (xa, za), (xb, zb) in zip(cap[:-1], cap[1:]):
        det.poly([(xa, y0 - 0.03, za), (xb, y0 - 0.03, zb), (xb, y1 + 0.03, zb), (xa, y1 + 0.03, za)], "roof_metal_light")
    # frontales (tablas blancas sobre el canto de la lámina en los hastiales)
    for (yf, sg) in ((y0, -1), (y1, 1)):
        pts = [(x, roof_z(x)) for x in (-(BX1 + OVH_E), -BX1, -KNEE[0], 0.0, KNEE[0], BX1, BX1 + OVH_E)]
        pts[0] = (pts[0][0], roof_z(-BX1) - 1.47 * OVH_E)
        pts[-1] = (pts[-1][0], roof_z(BX1) - 1.47 * OVH_E)
        path = [(x, yf + sg * 0.015, z - 0.04) for (x, z) in pts]
        det.sweep([(-0.012, -0.11), (0.012, -0.11), (0.012, 0.03), (-0.012, 0.03)], path, mat="paint_white", normal=(0, 1, 0))
    # pares cada 1,0 m (lado bajo + lado alto), tirante en el quiebre, polines cada 0,6 m a todo lo largo
    yy = BY0 + 0.25
    while yy < BY1 - 0.2:
        for s in (-1, 1):
            a = Vector((s * (BX1 + OVH_E * 0.9), yy, roof_z(s * BX1) - 1.47 * OVH_E * 0.9))
            k = Vector((s * KNEE[0], yy, roof_z(s * KNEE[0])))
            top = Vector((0.0, yy, roof_z(0.0)))
            for (p, q) in ((a, k), (k, top)):
                _, _, N = _plane_frame(p, q)
                cl.rtube(inter, tuple(p - N * 0.115), tuple(q - N * 0.115), 0.045, 0.14, "wood", up=tuple(N), r=0.004)
            # cartabones de triplay a los dos lados del quiebre (unen par bajo, par alto y tirante), con clavos
            kp = k - Vector((0, 0, 0.2))
            for dy in (-0.0345, 0.0345 + 0.012):
                Mg = _T(kp.x, yy + dy, kp.z) @ _Rx(90)
                inter.plate([(s * 0.30, -0.42), (s * 0.30, 0.10), (-s * 0.42, 0.14), (-s * 0.42, -0.02)][::(1 if s > 0 else -1)],
                            0.012, "wood_grey", m=Mg)
        inter.box((-KNEE[0] + 0.05, yy - 0.022, KNEE[1] - 0.06), (KNEE[0] - 0.05, yy + 0.022, KNEE[1] + 0.08), "wood", bevel=0.004)
        yy += 1.0
    for s in (-1, 1):
        for (xa, xb) in (((BX1 + OVH_E * 0.9) * s, KNEE[0] * s), (KNEE[0] * s, 0.0)):
            n = max(2, int(abs(xb - xa) / 0.6))
            for i in range(n + 1):
                x = xa + (xb - xa) * i / n
                p = Vector((x, BY0 - OVH_G + 0.05, roof_z(x)))
                q = Vector((x, BY1 + OVH_G - 0.05, roof_z(x)))
                _, _, N = _plane_frame((xa, 0, roof_z(xa)), (xb, 0, roof_z(xb)))
                cl.rtube(inter, tuple(p - N * 0.03), tuple(q - N * 0.03), 0.09, 0.04, "wood", up=tuple(N), r=0.003)


# ------------------------------------------------------------------------------------------------- granero: estructura
FLOOR_B = 0.10                  # firme de concreto del granero
FRAMES = (-4.0, 0.0, 4.0)
XP_WALL, XP_AISLE = 5.72, 2.0
GIRDER = (3.02, 3.25)


def _brace(mb, p0, p1, w=0.09, h=0.09, mat="wood"):
    cl.rtube(mb, p0, p1, w, h, mat, up=(0, 1, 0) if abs(p1[1] - p0[1]) < 1e-6 else (1, 0, 0), r=0.004)


def _bolt_plate(mb, c, nrm, size=0.10):
    """Placa de acero con 2 pernos y tuercas (herraje de poste a viga)."""
    c = Vector(c)
    n = Vector(nrm).normalized()
    up = Vector((0, 0, 1)) if abs(n.z) < 0.9 else Vector((1, 0, 0))
    side = n.cross(up).normalized()
    up = side.cross(n).normalized()
    M = Matrix((side.to_4d(), up.to_4d(), n.to_4d(), (0, 0, 0, 1))).transposed()
    M.translation = c
    mb.box((-size / 2, -size, 0.0), (size / 2, size, 0.006), "metal_rust", bevel=0.002, m=M)
    for dv in (-size * 0.55, size * 0.55):
        p = M @ Vector((0, dv, 0.006))
        mb.cyl(tuple(p), tuple(p + n * 0.012), 0.012, seg=6, mat="metal_rust")
        mb.cyl(tuple(p + n * 0.012), tuple(p + n * 0.03), 0.007, seg=8, mat="metal_rust")


def barn_frame(inter):
    """Postes de 20 x 20 sobre dados de concreto con herraje, durmientes, vigas de amarre (cargan el tapanco), solera de muro,
    tornapuntas a 45° con pernos, largueros horizontales por dentro de la tabla y firme de concreto."""
    inter.box((BX0 + TB, BY0 + TB, 0.0), (BX1 - TB, BY1 - TB, FLOOR_B), "concrete")
    inter.box((-DOOR_W / 2, BY0, 0.0), (DOOR_W / 2, BY0 + TB, FLOOR_B), "concrete")                 # umbral del portón
    inter.box((-1.2, BY1 - TB, 0.0), (1.2, BY1, FLOOR_B), "concrete")
    posts = []
    for y in FRAMES:
        for x in (-XP_WALL, -XP_AISLE, XP_AISLE, XP_WALL):
            ztop = GIRDER[0] if abs(x) == XP_AISLE else H_EAVE - 0.22
            inter.box((x - 0.21, y - 0.21, FLOOR_B), (x + 0.21, y + 0.21, FLOOR_B + 0.06), "concrete", bevel=0.01)     # dado
            inter.box((x - 0.10, y - 0.10, FLOOR_B + 0.06), (x + 0.10, y + 0.10, ztop), "wood", bevel=0.008)
            for sgn in (-1, 1):                                                                       # estribo de acero
                inter.box((x - 0.105, y + sgn * 0.10, FLOOR_B + 0.06), (x + 0.105, y + sgn * 0.106, FLOOR_B + 0.30), "metal_rust",
                          bevel=0.0)
                for zb in (FLOOR_B + 0.13, FLOOR_B + 0.24):                                         # pernos del estribo
                    p = Vector((x, y + sgn * 0.106, zb))
                    inter.cyl(tuple(p), tuple(p + Vector((0, sgn * 0.012, 0))), 0.011, seg=6, mat="metal_rust")
            posts.append((x, y, ztop))
        # viga de amarre de lado a lado (carga los largueros del tapanco)
        inter.box((-XP_WALL - 0.11, y - 0.11, GIRDER[0]), (XP_WALL + 0.11, y + 0.11, GIRDER[1]), "wood", bevel=0.008)
        for x in (-XP_AISLE, XP_AISLE):                                                               # tornapuntas del pasillo
            for sx in (-1, 1):
                _brace(inter, (x + sx * 0.10, y, GIRDER[0] - 0.62), (x + sx * 0.72, y, GIRDER[0]))
            _bolt_plate(inter, (x, y - 0.104, GIRDER[0] - 0.05), (0, -1, 0))
        for x in (-XP_WALL, XP_WALL):
            _brace(inter, (x - math.copysign(0.10, x), y, GIRDER[0] - 0.62), (x - math.copysign(0.72, x), y, GIRDER[0]))
    for x in (-XP_WALL, XP_WALL):                                                                       # solera y tornapuntas
        inter.box((x - 0.11, BY0 + TB, H_EAVE - 0.22), (x + 0.11, BY1 - TB, H_EAVE - 0.02), "wood", bevel=0.008)
        for y in FRAMES:
            for sy in (-1, 1):
                _brace(inter, (x, y + sy * 0.10, H_EAVE - 0.84), (x, y + sy * 0.72, H_EAVE - 0.22))
        # largueros horizontales (2x6) por dentro de la tabla, donde se clavan las tablas
        face = (BX1 - 0.02 - TW) if x > 0 else (BX0 + 0.02 + TW)
        for z in (1.85, 2.95, 3.70):
            x0_, x1_ = sorted((face, face - math.copysign(0.05, x)))
            inter.box((x0_, BY0 + TB, z), (x1_, BY1 - TB, z + 0.14), "wood", bevel=0.004)
    for y in (BY0 + TB + 0.08, BY1 - TB - 0.08):                                                         # cabezales de los hastiales
        inter.box((-XP_WALL, y - 0.08, GIRDER[0]), (XP_WALL, y + 0.08, GIRDER[1]), "wood", bevel=0.008)
    loft(inter)


def loft(inter):
    """Tapanco al poniente: largueros 2x8 a cada 0,6 m sobre las vigas de amarre y piso de tablones con holgura."""
    z0 = GIRDER[1]
    zt = z0 + 0.20
    x = -XP_WALL + 0.05
    while x < -XP_AISLE + 0.06:
        inter.box((x - 0.025, BY0 + TB + 0.1, z0), (x + 0.025, BY1 - TB - 0.1, zt), "wood", bevel=0.003)
        x += 0.6
    r = rng(5)
    y = BY0 + TB + 0.12
    while y < BY1 - TB - 0.16:
        w = float(r.uniform(0.14, 0.20))
        sag = float(r.uniform(-0.003, 0.003))
        inter.box((-XP_WALL - 0.05, y, zt), (-XP_AISLE + 0.10 + float(r.uniform(-0.02, 0.02)), y + w - 0.006, zt + 0.028 + sag), "wood",
                  bevel=0.004)
        y += w
    # borde del tapanco: tabla de canto (guardapolvo) para que no caiga la paja
    inter.box((-XP_AISLE + 0.10, BY0 + TB + 0.12, zt), (-XP_AISLE + 0.14, BY1 - TB - 0.16, zt + 0.22), "wood", bevel=0.004)


# ------------------------------------------------------------------------------------------------- granero: puertas y ventanas
def board_leaf(mb, M, w, h, t=0.05, brace="X", trim=True, seed=0, board_mat="wood_red", trim_mat="paint_white"):
    """Hoja de tablas verticales con holgura de 3 mm, bastidor blanco perimetral, travesaño y cruz/Z de refuerzo (local:
    u 0..w, v 0..h, cara exterior y = 0, espesor hacia +y)."""
    r = rng(seed)
    bw = 0.145
    n = max(2, int(round(w / bw)))
    bw = w / n
    for i in range(n):
        u0 = i * bw + 0.0015
        mb.box((u0, 0.0, 0.0), (u0 + bw - 0.003, t * 0.5, h + float(r.uniform(-0.004, 0.0))), board_mat, bevel=0.004, m=M)
    if not trim:
        return
    tw, tt = 0.11, 0.028
    for (a, b) in (((0, -tt, 0), (tw, 0, h)), ((w - tw, -tt, 0), (w, 0, h)), ((tw, -tt, 0), (w - tw, 0, tw)),
                   ((tw, -tt, h - tw), (w - tw, 0, h)), ((tw, -tt, h / 2 - tw / 2), (w - tw, 0, h / 2 + tw / 2))):
        mb.box(a, b, trim_mat, bevel=0.005, m=M)
    halves = ((tw, tw, w - tw, h / 2 - tw / 2), (tw, h / 2 + tw / 2, w - tw, h - tw)) if brace == "X" else ((tw, tw, w - tw, h - tw),)
    for (ua, va, ub, vb) in halves:
        diag = [((ua, va), (ub, vb))] + ([((ua, vb), (ub, va))] if brace == "X" else [])
        for k, (p, q) in enumerate(diag):
            d = Vector((q[0] - p[0], 0, q[1] - p[1]))
            L = d.length
            ang = math.atan2(d.z, d.x)
            Mb = M @ _T(p[0], -tt, p[1]) @ Matrix.Rotation(-ang, 4, "Y")
            # la segunda diagonal va en dos tramos que topan contra la primera (corrida): sin caras coplanares en el cruce
            cut = (tw / 2.4) / max(math.sin(abs(2 * math.atan2(vb - va, ub - ua))), 0.3) + 0.004
            spans = [(0.04, L - 0.04)] if k == 0 else [(0.04, L / 2 - cut), (L / 2 + cut, L - 0.04)]
            for (s0, s1) in spans:
                mb.box((s0, 0.0, -tw / 2.4), (s1, tt, tw / 2.4), trim_mat, bevel=0.005, m=Mb)


def strap_hinge(mb, M, u, v, L=0.45, side=1):
    """Bisagra de cinta (forja) con 3 pijas, sobre la cara exterior (local de la hoja)."""
    mb.box((u, -0.006, v - 0.022), (u + side * L, 0.0, v + 0.022), "metal_rust", bevel=0.002, m=M) if side > 0 else \
        mb.box((u + side * L, -0.006, v - 0.022), (u, 0.0, v + 0.022), "metal_rust", bevel=0.002, m=M)
    for k in (0.08, 0.22, 0.38):
        p = M @ Vector((u + side * k * L / 0.45, -0.006, v))
        mb.cyl(tuple(p), tuple(p + (M.to_3x3() @ Vector((0, -0.005, 0)))), 0.008, seg=8, mat="metal_rust")


def barn_doors(det):
    """Portón corredizo de dos hojas sobre riel de acero (una abierta), puerta del tapanco con viga de polea, puerta trasera de
    dos hojas, puertas de hombre en los costados."""
    yf = BY0 - 0.02 - 0.03                       # paño de las tablas del hastial
    # riel con ménsulas y topes
    zr = DOOR_H + 0.25
    det.box((-4.7, yf - 0.16, zr), (4.7, yf - 0.08, zr + 0.09), "metal_rust", bevel=0.004)
    x = -4.5
    while x <= 4.6:
        det.box((x - 0.04, yf - 0.16, zr + 0.09), (x + 0.04, yf, zr + 0.14), "metal_rust", bevel=0.003)
        det.box((x - 0.04, yf - 0.012, zr - 0.05), (x + 0.04, yf, zr + 0.14), "metal_rust", bevel=0.002)
        x += 1.0
    for x in (-4.66, 4.62):
        det.box((x, yf - 0.20, zr - 0.04), (x + 0.04, yf - 0.06, zr + 0.13), "metal_rust", bevel=0.003)
    leaves = [(-DOOR_W / 2 - 2.2, 0), (0.0 - 0.02, 1)]       # izquierda abierta (corrida a la izquierda), derecha cerrada
    for (x0, k) in leaves:
        w = DOOR_W / 2 + 0.12
        M = _T(x0, yf - 0.14, FLOOR_B * 0.3) @ _Rz(0)
        board_leaf(det, M, w, DOOR_H + 0.05, seed=11 + k)
        for ut in (0.25, w - 0.25):                                                              # carros colgantes
            det.box((ut - 0.05, -0.012 - 0.01, DOOR_H - 0.12), (ut + 0.05, 0.0 - 0.01, zr + 0.06), "metal_rust", bevel=0.002, m=M)
            pc = M @ Vector((ut, -0.05, zr + 0.11))
            det.cyl(tuple(pc + Vector((0, -0.03, 0))), tuple(pc + Vector((0, 0.03, 0))), 0.045, seg=16, mat="metal_rust")
        det.box((w * 0.5 - 0.012, -0.08, 1.05), (w * 0.5 + 0.012, -0.03, 1.40), "metal_rust", bevel=0.004, m=M)       # jaladera
        for vv in (1.05, 1.40):
            det.box((w * 0.5 - 0.015, -0.05, vv - 0.015), (w * 0.5 + 0.015, -0.0, vv + 0.015), "metal_rust", bevel=0.002, m=M)
    det.box((-0.09, yf - 0.20, 0.0), (0.09, yf - 0.06, 0.05), "metal_rust", bevel=0.004)                  # guía de piso
    # puerta del tapanco (dos hojas, una entreabierta) y viga de polea
    lx0, lx1, lz0, lz1 = LOFT_DOOR
    w2 = (lx1 - lx0) / 2
    for (k, ang) in ((0, 0.0), (1, 70.0)):
        hx = lx0 if k == 0 else lx1
        side = 1 if k == 0 else -1
        M = _T(hx, yf - 0.06, lz0 + 0.02) @ _Rz(side * ang) @ _T(0 if k == 0 else -w2, 0, 0)
        board_leaf(det, M, w2 - 0.01, lz1 - lz0 - 0.04, brace="Z", seed=21 + k)
        for vv in (0.25, lz1 - lz0 - 0.30):
            strap_hinge(det, M, 0.0 if k == 0 else w2 - 0.01, vv, side=1 if k == 0 else -1)
    det.box((-0.10, BY0 + 0.7, 7.40), (0.10, BY0 - 1.35, 7.65), "wood", bevel=0.01)
    det.box((-0.105, BY0 - 1.10, 7.38), (0.105, BY0 - 1.30, 7.67), "metal_rust", bevel=0.003)             # zuncho de la punta
    # puerta trasera (dos hojas cerradas con tranca) y puertas de hombre
    yb = BY1 + 0.02 + 0.03
    for (k, x0) in ((0, -1.2), (1, 0.0)):
        M = _T(x0 + 1.2 if k == 0 else x0 + 1.2 + 1.2 - 1.2, yb + 0.05, FLOOR_B * 0.3) @ _Rz(180)
        board_leaf(det, M, 1.19, 2.55, brace="Z", seed=31 + k)
    det.box((-1.35, yb + 0.06, 1.30), (1.35, yb + 0.16, 1.42), "wood", bevel=0.008)                        # tranca
    for x in (-1.25, 1.25):
        det.box((x - 0.04, yb + 0.05, 1.27), (x + 0.04, yb + 0.17, 1.45), "metal_rust", bevel=0.003)
    for (sd, w0) in (("west", -1.5), ("east", 4.0)):
        if sd == "west":
            M = _T(BX0 - 0.05, w0 + 1.0, FLOOR_B * 0.3) @ _Rz(-90)
        else:
            M = _T(BX1 + 0.05, w0, FLOOR_B * 0.3) @ _Rz(90)
        board_leaf(det, M, 0.98, 2.05, brace="Z", trim=True, seed=41 if sd == "west" else 42)
        for vv in (0.3, 1.7):
            strap_hinge(det, M, 0.0, vv, side=1)


def barn_window(det, M, w, h, seed=0, open_shutters=True):
    """Ventana de granero: marco de madera, hoja de 4 vidrios con contravidrios, alféizar inclinado y postigos de tabla con
    bisagras de cinta abiertos contra el muro (local del vano: u 0..w, v 0..h, muro y 0..t)."""
    r = rng(seed)
    f = 0.06
    for (a, b) in (((0, 0.02, 0), (f, 0.08, h)), ((w - f, 0.02, 0), (w, 0.08, h)), ((f, 0.02, 0), (w - f, 0.08, f)), ((f, 0.02, h - f), (w - f, 0.08, h))):
        det.box(a, b, "wood", bevel=0.004, m=M)
    m = 0.025
    for (a, b) in (((f, 0.035, h / 2 - m / 2), (w - f, 0.065, h / 2 + m / 2)), ((w / 2 - m / 2, 0.035, f), (w / 2 + m / 2, 0.065, h - f))):
        det.box(a, b, "wood", bevel=0.003, m=M)
    for (u0, v0) in ((f, f), (w / 2 + m / 2, f), (f, h / 2 + m / 2), (w / 2 + m / 2, h / 2 + m / 2)):
        det.box((u0, 0.049, v0), (u0 + (w - 2 * f - m) / 2, 0.051, v0 + (h - 2 * f - m) / 2), "glass", bevel=0.0, m=M)
    det.box((-0.05, -0.07, -0.045), (w + 0.05, 0.02, 0.0), "wood", bevel=0.006, m=M @ _Rx(-6))
    if open_shutters:
        for (k, hx) in ((0, 0.0), (1, w)):
            side = -1 if k == 0 else 1
            ang = float(r.uniform(165, 178))
            # postigo abierto casi 180° contra el muro: el izquierdo gira sobre u = 0, el derecho sobre u = w
            Ms = M @ _T(hx, -0.035, 0.0) @ _Rz(side * ang) @ _T(-w / 2 if k == 1 else 0, 0, 0)
            board_leaf(det, Ms, w / 2, h, t=0.03, brace="Z", trim=False, seed=seed * 7 + k)


def barn_windows(det):
    for sd, lst in BARN_OPS.items():
        a0, a1, face = {"front": (BX0, BX1, BY0), "back": (BX0, BX1, BY1), "west": (BY0 + TB, BY1 - TB, BX0),
                        "east": (BY0 + TB, BY1 - TB, BX1)}[sd]
        M = ac.panel_matrix(sd, a0, a1, face, 0.0) @ _T(0, -0.02, 0)
        for (u0, u1, v0, v1) in lst:
            w, h = u1 - u0, v1 - v0
            if v0 < 0.01 or (sd == "front" and abs((u0 + u1) / 2 - (BX1 - BX0) / 2) < 0.1 and v0 > 4.0) or (sd == "back" and v0 > 4.0 and w > 1.4):
                continue                                                     # puertas y puerta del tapanco: aparte
            barn_window(det, M @ _T(u0, 0, v0), w, h, seed=int(u0 * 10 + v0), open_shutters=(sd != "front"))
    # ventila del hastial trasero: celosía de tablillas
    a0, a1 = BX0, BX1
    M = ac.panel_matrix("back", a0, a1, BY1, 0.0) @ _T(0, -0.02, 0)
    u0 = a1 - 0.8                                   # u = a1 - x: vano de x -0,8..0,8
    for i in range(9):
        v = 5.25 + i * 0.13
        Mv = M @ _T(u0, 0.0, v) @ _Rx(-35)
        det.box((0.0, 0.0, -0.05), (1.6, 0.012, 0.05), "wood", bevel=0.002, m=Mv)


# ------------------------------------------------------------------------------------------------- tejaban poniente
def lean_to(det, inter, roof):
    """Tejaban sobre postes de 15 x 15 en dados, viga de carga, solera atornillada al muro, pares cada 1,0 m, polines y lámina
    oxidada con tornillos; tornapuntas poste-viga."""
    zl, zb = 3.55, 2.72
    for y in (LY0, -2.0, 2.0, LY1):
        det.box((LX0 - 0.18, y - 0.18, 0.0), (LX0 + 0.18, y + 0.18, 0.12), "concrete", bevel=0.01)
        det.box((LX0 - 0.075, y - 0.075, 0.12), (LX0 + 0.075, y + 0.075, zb - 0.2), "wood", bevel=0.006)
        for sy in (-1, 1):
            if (y == LY0 and sy < 0) or (y == LY1 and sy > 0):
                continue
            _brace(det, (LX0, y + sy * 0.07, zb - 0.75), (LX0, y + sy * 0.6, zb - 0.2), w=0.07, h=0.07)
    det.box((LX0 - 0.06, LY0 - 0.3, zb - 0.2), (LX0 + 0.06, LY1 + 0.3, zb), "wood", bevel=0.006)              # viga
    det.box((BX0 - 0.02 - 0.06 - 0.06, LY0 - 0.3, zl - 0.22), (BX0 - 0.02 - 0.06, LY1 + 0.3, zl - 0.02), "wood", bevel=0.006)  # solera
    slope = (zl - zb) / (BX0 - 0.14 - LX0)
    zf = lambda x: zb + (x - LX0) * slope  # noqa: E731
    y = LY0 - 0.25
    while y <= LY1 + 0.3:
        cl.rtube(det, (LX0 - 0.35, y, zf(LX0 - 0.35) + 0.02), (BX0 - 0.14, y, zl), 0.045, 0.12, "wood", up=(0, 0, 1), r=0.003)
        y += 1.0
    x = LX0 - 0.3
    while x < BX0 - 0.2:
        det.box((x - 0.045, LY0 - 0.35, zf(x) + 0.08), (x + 0.045, LY1 + 0.35, zf(x) + 0.12), "wood", bevel=0.003)
        x += 0.8
    corrugated_plane(roof, (LX0 - 0.42, LY0 - 0.4, zf(LX0 - 0.42) + 0.125), (BX0 - 0.10, LY0 - 0.4, zl + 0.06), LY0 - 0.4, LY1 + 0.4,
                     "roof_metal", screw_rows=0.8)


# ------------------------------------------------------------------------------------------------- tienda
STORE_OPS = {}


def store(shell, det, inter, roof):
    """Muros de block aplanado (amarillo con zoclo azul, lookdev), losa con pretil y remate, piso de barro, lambrín azul y
    pintura crema por dentro, plafón blanco; pórtico de concreto con escalón y tejaban de lámina sobre postes de madera."""
    sides = {"front": (SX0, SX1, SY0), "back": (SX0, SX1, SY1), "west": (SY0 + TS, SY1 - TS, SX0), "east": (SY0 + TS, SY1 - TS, SX1)}
    ops = {"front": [("door", 10.5, 11.45, S_FFL, S_FFL + 2.1), ("win", 13.8, 15.0, 1.05, 2.15)],
           "east": [("win", -1.8, -0.8, 1.2, 2.2)],
           "west": [("win", -3.0, -2.0, 1.3, 2.1)],
           "back": [("door", 13.6, 14.5, S_FFL, S_FFL + 2.1)]}
    Ms = {}
    for sd, (a0, a1, face) in sides.items():
        L = a1 - a0
        u = _u_of(sd, a0, a1)
        lst = []
        for (kind, w0, w1, z0, z1) in ops[sd]:
            ua, ub = sorted((u(w0), u(w1)))
            lst.append((kind, ua, ub, z0, z1))
        STORE_OPS[sd] = lst
        M = ac.panel_matrix(sd, a0, a1, face, 0.0)
        Ms[sd] = M
        wall_with_openings(shell, L, S_ST, TS, [(o[1], o[2], o[3], o[4]) for o in lst], mat_out="plaster", mat_in="paint_cream",
                           mat_reveal="plaster", m=M)
        wall_with_openings(shell, L, S_PARA - S_ST, TS, [], mat_out="plaster", mat_in="plaster", mat_reveal="plaster", m=M @ _T(0, 0, S_ST))
        tr = 0.0 if sd in ("front", "back") else 0.03
        shell.box((tr - (0.03 if tr == 0 else 0), -0.03, S_PARA), (L - tr + (0.03 if tr == 0 else 0), TS + 0.03, S_PARA + 0.05), "concrete", m=M)
    # losa, plafón, piso
    xi0, xi1, yi0, yi1 = SX0 + TS, SX1 - TS, SY0 + TS, SY1 - TS
    inter.box((xi0, yi0, 0.0), (xi1, yi1, S_FFL - 0.012), "concrete")
    inter.box((xi0, yi0, S_FFL - 0.012), (xi1, yi1, S_FFL), "tile_clay")
    roof.box((xi0, yi0, S_SB), (xi1, yi1, S_ST), "concrete")
    inter.box((xi0, yi0, S_CEIL - 0.012), (xi1, yi1, S_CEIL - 0.002), "paint_white")
    # lambrín azul a 1,0 m con filete, cortado en las puertas
    for sd, (a0, a1, face) in sides.items():
        M = ac.panel_matrix(sd, a0, a1, face, 0.0)
        L = a1 - a0
        cuts = [(o[1], o[2]) for o in STORE_OPS[sd] if o[0] == "door"]
        segs, cur = [], (0.0 if sd in ("front", "back") else 0.0)
        lo, hi = (TS, L - TS) if sd in ("front", "back") else (0.0, L)
        cur = lo
        for (c0, c1) in sorted(cuts):
            if c0 > cur:
                segs.append((cur, c0))
            cur = max(cur, c1)
        if hi > cur:
            segs.append((cur, hi))
        for (a, b) in segs:
            inter.box((a, TS + 0.001, S_FFL), (b, TS + 0.004, S_FFL + 1.0), "paint_navy", m=M)
            inter.box((a, TS + 0.001, S_FFL + 1.0), (b, TS + 0.007, S_FFL + 1.03), "paint_navy", bevel=0.002, m=M)
            inter.box((a, TS + 0.001, S_FFL), (b, TS + 0.012, S_FFL + 0.08), "tile_clay", bevel=0.002, m=M)     # zoclo de barro
    # pórtico y escalón
    det.box((SX0 - 0.25, PORCH_Y, 0.0), (SX1 + 0.25, SY0, S_FFL), "concrete", bevel=0.012)
    det.box((10.2, PORCH_Y - 0.32, 0.0), (11.8, PORCH_Y, 0.075), "concrete", bevel=0.01)
    awning(det, roof)
    return Ms


def awning(det, roof):
    """Tejaban del pórtico: postes rollizos sobre dados, viga, solera en el muro, pares 2x4 cada 0,9 m y lámina galvanizada."""
    zl, zb = 2.98, 2.62
    ypost = PORCH_Y + 0.18
    r = rng(29)
    for x in (SX0 + 0.15, (SX0 + SX1) / 2, SX1 - 0.15):
        lean = float(r.uniform(-0.012, 0.012))
        det.box((x - 0.12, ypost - 0.12, S_FFL), (x + 0.12, ypost + 0.12, S_FFL + 0.10), "concrete", bevel=0.01)
        det.tube([(x, ypost, S_FFL + 0.08), (x + lean, ypost + lean * 0.5, zb - 0.16)], 0.075, seg=14, mat="wood", caps=True,
                 radii=[0.078, 0.07])
        det.box((x - 0.06, ypost - 0.012, zb - 0.30), (x + 0.06, ypost + 0.0, zb - 0.16), "metal_rust", bevel=0.002)
    det.box((SX0 - 0.15, ypost - 0.05, zb - 0.18), (SX1 + 0.15, ypost + 0.05, zb), "wood", bevel=0.006)
    det.box((SX0 - 0.15, SY0 - 0.08, zl - 0.18), (SX1 + 0.15, SY0, zl), "wood", bevel=0.006)
    slope = (zl - zb) / (SY0 - 0.08 - ypost)
    zf = lambda y: zb + (y - ypost) * slope  # noqa: E731
    x = SX0 - 0.1
    while x <= SX1 + 0.12:
        cl.rtube(det, (x, PORCH_Y - 0.12, zf(PORCH_Y - 0.12) + 0.02), (x, SY0 - 0.08, zl), 0.04, 0.09, "wood", up=(0, 0, 1), r=0.003)
        x += 0.9
    # la lámina corre con ondas a lo largo de la pendiente (en Y): faldón construido sobre X
    p0 = Vector((SX0 - 0.3, PORCH_Y - 0.3, zf(PORCH_Y - 0.3) + 0.085))
    p1 = Vector((SX0 - 0.3, SY0 - 0.02, zl + 0.05))
    _corr_x(roof, p0, p1, SX0 - 0.3, SX1 + 0.3, "roof_metal_light")


def _corr_x(mb, p0, p1, x0, x1, mat, pitch=0.076, amp=0.009, nseg=8):
    """Lámina ondulada con la pendiente en Y (de p0 a p1) y el ancho en X; tornillos cada 3 ondas en dos hileras."""
    D = (p1 - p0).normalized()
    X = Vector((1, 0, 0))
    N = X.cross(D)
    if N.z < 0:
        N = -N
    Ls = (p1 - p0).length
    nw = int((x1 - x0) / pitch * nseg)
    rows = []
    for j in range(3):
        s = Ls * j / 2
        rows.append([mb.bm.verts.new(p0 + D * s + X * ((x1 - x0) * i / nw) + N * (amp * math.sin(2 * math.pi * ((x1 - x0) * i / nw) / pitch)))
                     for i in range(nw + 1)])
    for j in range(2):
        for i in range(nw):
            f = mb.face([rows[j][i], rows[j + 1][i], rows[j + 1][i + 1], rows[j][i + 1]], mat)
            f.smooth = True
    for s in (0.25, Ls - 0.18):
        w = pitch / 4
        while w < x1 - x0 - 0.05:
            c = p0 + D * s + X * w + N * amp
            mb.cyl(tuple(c), tuple(c + N * 0.004), 0.011, seg=8, mat="rubber")
            mb.cyl(tuple(c + N * 0.004), tuple(c + N * 0.0095), 0.0075, seg=6, mat="steel")
            w += pitch * 3


def store_openings(det, furn):
    """Puerta de acero con reja de seguridad abierta, ventanilla de venta con barrotes, repisa de madera y campana, ventanas
    corredizas con reja, puerta trasera; letreros pintados (COMMUNITY STORE y la lista de lo que se vende)."""
    for sd, lst in STORE_OPS.items():
        a0, a1, face = {"front": (SX0, SX1, SY0), "back": (SX0, SX1, SY1), "west": (SY0 + TS, SY1 - TS, SX0),
                        "east": (SY0 + TS, SY1 - TS, SX1)}[sd]
        M = ac.panel_matrix(sd, a0, a1, face, 0.0)
        for i, (kind, ua, ub, z0, z1) in enumerate(lst):
            w, h = ub - ua, z1 - z0
            Mo = M @ _T(ua, 0, z0)
            if kind == "door":
                det.join(cl.door_steel(w, h, depth=TS, seed=3 + i, ang=(-62.0 if sd == "front" else 0.0), panic=False, mat="paint_green"), Mo)
                if sd == "front":
                    det.join(security_gate(w, h, ang=-158.0), Mo)
            else:
                det.join(cl.window_clean(w, h, depth=TS, seed=7 + i, open_frac=0.0 if sd == "front" else None), Mo)
                det.join(cl.window_grille(w, h, seed=8 + i, mat="paint_green") if sd != "front" else heavy_bars(w, h), Mo)
                if sd == "front":                                                   # repisa de venta con ménsulas y campana
                    det.box((-0.05, -0.36, -0.06), (w + 0.05, -0.0, -0.02), "wood", bevel=0.008, m=Mo)
                    for uu in (0.15, w - 0.15):
                        det.box((uu - 0.02, -0.30, -0.30), (uu + 0.02, -0.0, -0.06), "metal_rust", bevel=0.003, m=Mo)
                        det.tube([tuple(Mo @ Vector((uu, -0.28, -0.06))), tuple(Mo @ Vector((uu, -0.01, -0.28)))], 0.008, seg=6,
                                 mat="metal_rust")
                    pc = Mo @ Vector((w - 0.25, -0.2, -0.02))
                    det.cyl(tuple(pc), tuple(pc + Vector((0, 0, 0.012))), 0.045, seg=20, mat="steel")
                    det.cyl(tuple(pc + Vector((0, 0, 0.012))), tuple(pc + Vector((0, 0, 0.05))), 0.035, seg=20, mat="aluminium",
                            r1=0.012)
    signs(det)


def security_gate(w, h, ang=-160.0):
    """Reja de seguridad de una hoja (marco de PTR, barrotes cuadrados, travesaños, chapa), abierta contra el muro."""
    g = MB()
    M = _T(0, -0.035, 0) @ _Rz(ang)
    cl.rtube(g, (0.02, 0, 0.02), (0.02, 0, h - 0.02), 0.04, 0.025, "paint_green", up=(0, 1, 0), r=0.003)
    for (p, q) in (((0.02, 0, 0.02), (w - 0.04, 0, 0.02)), ((w - 0.04, 0, 0.02), (w - 0.04, 0, h - 0.02)),
                   ((0.02, 0, h - 0.02), (w - 0.04, 0, h - 0.02)), ((0.02, 0, h * 0.5), (w - 0.04, 0, h * 0.5))):
        cl.rtube(g, p, q, 0.04, 0.025, "paint_green", up=(0, 1, 0), r=0.003)
    u = 0.12
    while u < w - 0.1:
        g.box((u - 0.008, -0.008, 0.04), (u + 0.008, 0.008, h - 0.04), "paint_green", bevel=0.002)
        u += 0.11
    g.box((w - 0.12, -0.03, 1.0), (w - 0.04, 0.03, 1.15), "metal_rust", bevel=0.004)
    out = MB()
    out.join(g, M)
    for v in (0.3, h - 0.3):                                                     # bisagras de barril
        out.cyl((0.0, -0.035, v - 0.06), (0.0, -0.035, v + 0.06), 0.014, seg=12, mat="metal_rust")
    return out


def heavy_bars(w, h):
    """Barrotes de la ventanilla de venta: redondos de 3/4" soldados a marco de ángulo, con ventanilla de paso abajo."""
    mb = MB()
    t = 0.035
    for (a, b) in (((0, -t, 0), (0.035, 0, h)), ((w - 0.035, -t, 0), (w, 0, h)), ((0, -t, h - 0.035), (w, 0, h)),
                   ((0, -t, 0.30), (w, 0, 0.335)), ((0, -t, 0), (w, 0, 0.035))):
        mb.box(a, b, "paint_green", bevel=0.003)
    u = 0.10
    while u < w - 0.08:
        mb.cyl((u, -t / 2, 0.335), (u, -t / 2, h - 0.035), 0.0095, seg=10, mat="paint_green")
        u += 0.10
    return mb


def signs(det):
    """Letreros pintados con brocha (relieve de 1,5 mm de pintura): COMMUNITY STORE en el pretil, la lista al frente y al costado."""
    Mp = _T((SX0 + SX1) / 2, SY0 - 0.0015, S_ST + 0.12) @ _Rx(90)
    cl.text(det, "COMMUNITY STORE", 0.36, 0.0015, "sign_blue", M=Mp, align="CENTER", bold=True)
    for k, line in enumerate(("MEDICAL", "FOOD", "AMMO", "COLD BEER")):
        M = _T(11.70, SY0 - 0.0015, S_FFL + 2.05 - k * 0.27) @ _Rx(90)
        cl.text(det, "- " + line, 0.17, 0.0015, "sign_blue", M=M, align="LEFT", bold=True)
    Me = _T(SX1 + 0.0015, (SY0 + SY1) / 2, 2.55) @ _Rz(90) @ _Rx(90)
    cl.text(det, "MEDICAL - FOOD - AMMO - COLD BEER", 0.20, 0.0015, "sign_blue", M=Me, align="CENTER", bold=True)


def store_services(det, furn):
    """Medidor y tubo conduit al frente, tinaco sobre base de ángulo en la losa, condensadora y jaula de gas LP atrás,
    bajada de agua pluvial."""
    det.join(cl.remap(sv.meter_box(seed=4, open_door=False, detail="high"), {"metal_rust": "steel", "metal_paint": "steel"}),
             _T(SX0 + 0.45, SY0, 1.45) @ _Rz(180))
    det.join(cl.remap(sv.conduit([(SX0 + 0.45, SY0, 1.95), (SX0 + 0.45, SY0, S_PARA - 0.1), (SX0 + 0.45, SY0 + 0.25, S_PARA + 0.3)],
                                 seed=5, detail="high"), {"metal_rust": "steel"}))
    # tinaco en base de ángulo de 0,9 m
    tx, ty = SX1 - 1.4, SY1 - 1.6
    for (dx, dy) in ((-0.5, -0.5), (0.5, -0.5), (-0.5, 0.5), (0.5, 0.5)):
        det.box((tx + dx - 0.025, ty + dy - 0.025, S_ST), (tx + dx + 0.025, ty + dy + 0.025, S_ST + 0.9), "steel", bevel=0.002)
    for z in (S_ST + 0.30, S_ST + 0.88):
        for (a, b) in (((tx - 0.52, ty - 0.52), (tx + 0.52, ty - 0.48)), ((tx - 0.52, ty + 0.48), (tx + 0.52, ty + 0.52)),
                       ((tx - 0.52, ty - 0.52), (tx - 0.48, ty + 0.52)), ((tx + 0.48, ty - 0.52), (tx + 0.52, ty + 0.52))):
            det.box((a[0], a[1], z - 0.02), (b[0], b[1], z + 0.02), "steel", bevel=0.002)
    det.box((tx - 0.56, ty - 0.56, S_ST + 0.9), (tx + 0.56, ty + 0.56, S_ST + 0.93), "steel", bevel=0.003)
    det.join(sv.water_tank(seed=6, detail="high"), _T(tx, ty, S_ST + 0.93))
    det.join(cl.remap(sv.ac_unit("split_outdoor", seed=7, detail="mid"), {"metal_rust": "enamel", "metal_paint": "sign_white"}),
             _T(SX0 + 1.4, SY1 + 0.02, 1.0) @ _Rz(180))
    det.cyl((SX1 - 0.3, SY1 + 0.05, 0.25), (SX1 - 0.3, SY1 + 0.05, S_ST + 0.05), 0.05, seg=14, mat="plastic")      # bajada pluvial


# ------------------------------------------------------------------------------------------------- vestido (utilería)
def _mod(name):
    try:
        return __import__(f"kit.{name}", fromlist=[name])
    except ImportError:
        return None


def dress(furn, r):
    """Utilería AAA de kit/farm.py y kit/store.py (y del hospital: luminarias, extintor, minisplit, gas). Lo que se puede
    chocar deja su caja de colisión en PROXIES. Si un módulo aún no existe, se omite (pruebas de arquitectura)."""
    farm, st = _mod("farm"), _mod("store")

    def put(piece, x, y, z=0.0, facing="-y", solid=True, M=None):
        Mx = M if M is not None else _T(x, y, z) @ face_to(facing)
        if solid:
            _proxy(piece, Mx)
        furn.join(piece, Mx)

    zl = GIRDER[1] + 0.20 + 0.028                  # piso del tapanco
    # luminarias
    for y in FRAMES:
        LIGHTS.append([0.0, y, GIRDER[0] - 0.62])
    for y in (-5.6, -2.6):
        furn.join(cl.fluorescent(), _T(12.5, y, S_CEIL - 0.012) @ _Rz(90))
        LIGHTS.append([12.5, y, round(S_CEIL - 0.1, 3)])
    furn.join(cl.fluorescent(0.6, 0.3), _T(12.5, SY0 - 0.45, 2.86))
    LIGHTS.append([12.5, SY0 - 0.45, 2.78])
    put(cl.split_indoor(), 10.9, SY1 - TS, S_FFL + 2.35, "-y", solid=False)
    put(cl.extinguisher(), SX0 + TS, -7.2, S_FFL + 1.05, "+x", solid=False)
    put(cl.cylinder_rack(3, seed=int(r.integers(1e6)), medical=False), SX1 - 1.3, SY1 + 0.45, 0.0, "+y")
    if farm is not None:
        for y in FRAMES:
            put(farm.bare_bulb(0.55), 0.0, y, GIRDER[0], solid=False)
        put(farm.hoist(drop=2.4), 0.0, BY0 - 1.2, 7.40, solid=False)
        # tapanco: pacas estibadas
        put(farm.hay_stack(3, 8, 3, seed=1), -4.2, -5.0, zl)
        put(farm.hay_stack(3, 6, 2, seed=2), -4.2, 3.4, zl)
        put(farm.loose_hay(1.6, 1.0, seed=3), -3.0, 0.2, zl, solid=False)
        # bajo el tapanco: banco, gabinete, costales, tambos
        put(farm.workbench(2.0, seed=4), -XP_WALL + 0.45, 2.0, FLOOR_B, "+x")
        put(farm.metal_cabinet(seed=5), -XP_WALL + 0.30, 5.6, FLOOR_B, "+x")
        put(farm.sack_pile(6, seed=6), -4.4, -6.6, FLOOR_B)
        put(farm.drum(seed=7), -4.9, 6.9, FLOOR_B)
        put(farm.drum(seed=8), -4.2, 7.1, FLOOR_B)
        put(farm.rope_coil(seed=9), -XP_AISLE - 0.10, -3.80, 1.7, "-x", solid=False)
        lad = farm.ladder(3.6)
        put(lad, 0, 0, M=_T(-1.30, -2.0, FLOOR_B) @ _Ry(-13.0) @ face_to("-x"))
        put(farm.pitchfork(seed=10), 0, 0, M=_T(XP_AISLE + 0.16, 0.25, FLOOR_B) @ _Rx(-9) @ _Rz(20))
        put(farm.shovel(seed=11), 0, 0, M=_T(XP_AISLE + 0.20, -0.25, FLOOR_B) @ _Rx(-10) @ _Rz(-15))
        put(farm.wheelbarrow(seed=12), 0.7, -2.6, FLOOR_B, "+x")
        for (x, y) in ((-0.6, 2.2), (0.9, 5.5), (-1.2, -6.2)):
            put(farm.loose_hay(1.3, 0.9, seed=int(abs(x * 10 + y)) + 70), x, y, FLOOR_B, solid=False)
        # corrales vacíos al oriente: divisiones y frentes con puerta
        for y in FRAMES:
            put(farm.stall_partition(XP_WALL - XP_AISLE - 0.12, gate=False, seed=int(y + 20)), 0, 0,
                M=_T(XP_AISLE + 0.10, y, FLOOR_B))
        for (ya, yb) in ((-3.9, -0.1), (0.1, 3.9), (4.1, 7.6)):
            put(farm.stall_partition(yb - ya, gate=True, seed=int(ya + 40)), 0, 0, M=_T(XP_AISLE, ya, FLOOR_B) @ _Rz(90))
        for (x, y) in ((4.6, -2.0), (4.6, 2.0), (4.6, 5.9)):
            put(farm.bucket(seed=int(y * 3 + 50)), x, y + 0.9, FLOOR_B)
            put(farm.loose_hay(1.6, 1.2, seed=int(y + 60)), x - 0.6, y - 0.4, FLOOR_B, solid=False)
        put(farm.water_trough(1.2, seed=13), 4.6, 5.9, FLOOR_B, "-x")
        # afuera, frente: pacas, tarimas, bebedero, costales
        put(farm.hay_stack(2, 2, 2, seed=14), -3.6, -9.3, 0.0)
        put(farm.hay_bale(seed=15), -2.3, -9.6, 0.0, M=_T(-2.3, -9.7, 0.0) @ _Rz(17))
        put(farm.pallet(seed=16), 0, 0, M=_T(-5.0, BY0 - 0.30, 0.02) @ _Rx(-78))
        put(farm.pallet(seed=17), 0, 0, M=_T(-4.55, BY0 - 0.36, 0.02) @ _Rx(-76))
        put(farm.water_trough(1.8, seed=18), 3.7, -9.4, 0.0)
        put(farm.sack_pile(4, seed=19), 2.6, -8.9, 0.0)
        # tejaban: pacas, costales y corral vacío
        put(farm.hay_stack(3, 6, 3, seed=20), -8.1, -4.0, 0.0, "+x")
        put(farm.sack_pile(6, seed=21), -8.0, -0.4, 0.0, "+x")
        put(farm.pen_fence(4.3, seed=22), 0, 0, M=_T(-10.5, 1.0, 0.0))
        put(farm.pen_fence(4.3, seed=23), 0, 0, M=_T(-10.5, 6.1, 0.0))
        put(farm.pen_fence(5.1, seed=24), 0, 0, M=_T(-10.5, 1.0, 0.0) @ _Rz(90))
        put(farm.water_trough(1.2, seed=25), -9.6, 4.6, 0.0, "+x")
        put(farm.loose_hay(1.8, 1.4, seed=26), -8.0, 3.2, 0.0, solid=False)
        # alambrado al fondo (contexto de potrero, sin ganado)
        for k, x0 in enumerate((-12.0, -6.0, 0.0, 6.0)):
            put(farm.wire_fence(6.0, seed=30 + k), 0, 0, M=_T(x0, BY1 + 2.2, 0.0), solid=False)
        put(farm.drum(seed=34), SX1 - 0.3, SY1 + 0.6, 0.0)
    if st is not None:
        yi0, yi1 = SY0 + TS, SY1 - TS
        put(st.shop_counter(3.2, seed=40), 14.0, -4.4, S_FFL, "-x")
        put(st.ammo_cabinet(seed=41), SX1 - TS, -4.0, S_FFL, "-x")
        put(st.medical_shelf(seed=42), SX1 - TS, -6.55, S_FFL, "-x")
        put(st.wall_calendar(seed=43), SX1 - TS, -5.3, S_FFL + 1.55, "-x", solid=False)
        put(st.crate_stack(seed=44), 14.9, yi0 + 0.45, S_FFL, "-x")
        for k, (y, stock) in enumerate(((-6.85, "canned"), (-5.55, "dry"), (-4.25, "household"))):
            put(st.grocery_shelving(1.2, seed=45 + k, stock=stock), SX0 + TS, y, S_FFL, "+x")          # espalda al muro poniente
        for k, (x, stock) in enumerate(((10.45, "dry"), (11.75, "canned"))):
            put(st.grocery_shelving(1.2, seed=48 + k, stock=stock), x, yi1, S_FFL, "-y")               # espalda al muro del fondo
        put(st.beer_cooler(seed=50), 13.05, yi1 - 0.37, S_FFL, "-y")
        put(st.chalkboard(seed=51), 14.75, yi1, S_FFL + 1.25, "-y", solid=False)
        put(st.hand_scale(seed=52), 14.05, -3.6, S_FFL + 0.95, "-x", solid=False)
        put(st.cash_box(seed=53), 14.1, -5.2, S_FFL + 0.95, "-x", solid=False)
        put(cl.trash_bin(pedal=False), 12.9, -6.9, S_FFL)
        # pórtico
        put(st.chest_freezer(seed=54), 12.65, SY0 - 0.42, S_FFL, "-y")
        put(st.bottle_crate(seed=55), 13.75, SY0 - 0.30, S_FFL, "-y")
        put(st.bottle_crate(seed=56), 13.78, SY0 - 0.31, S_FFL + 0.29, "-y")
        put(st.bench(1.3, seed=57), SX0 + 0.75, SY0 - 0.35, S_FFL, "-y")
        put(st.open_sign(), 14.4, SY0 - 0.06, S_FFL + 1.95, "-y", solid=False)


# ------------------------------------------------------------------------------------------------- ensamble
def build_gra(bid="GRA_1_tienda", collection_root=None, dress_on=True, **kw):
    cfg = cfg_gra(bid)
    cid = cfg["id"]
    LIGHTS.clear()
    PROXIES.clear()
    BARN_OPS.clear()
    STORE_OPS.clear()
    root = collection_root or get_collection(cid)
    keys = ("Shell", "Details", "Interior", "Skirt", "Roof", "Damage", "Furniture")
    cols = {k: get_collection(f"{cid}_{k}", root) for k in keys}
    out = {k: [] for k in cols}
    shell, det, inter, roof, furn = MB(), MB(), MB(), MB(), MB()
    r = rng(cfg["seed"])
    barn_walls(shell, det, inter)
    barn_roof(roof, det, inter)
    barn_frame(inter)
    barn_doors(det)
    barn_windows(det)
    lean_to(det, inter, roof)
    store(shell, det, inter, roof)
    store_openings(det, furn)
    store_services(det, furn)
    if dress_on and kw.get("dress", True):
        dress(furn, r)
    for nm, mb in (("Shell", shell), ("Details", det), ("Interior", inter), ("Roof", roof), ("Furniture", furn)):
        if len(mb.bm.faces):
            out[nm].append(mb.finish(f"{cid}_{nm}", cols[nm], uv_size=2.0, merge=0))
    out["stats"] = dict(interior_dress=dict(bulb_pos=list(LIGHTS)), proxies=list(PROXIES))
    out["cfg"] = cfg
    return out
