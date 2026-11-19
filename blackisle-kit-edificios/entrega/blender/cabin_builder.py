"""cabin_builder.py — cabañas de madera BLACKISLE (CAB_1_tablones, CAB_2_pilotes, CAB_3_ladrillo), con interior completo.

Sistema: planta w (X) x d (Y) centrada; fachada principal hacia -Y; cumbrera en X (hastiales en x = ±w/2).
Estructura: base (dados, pilotes con cruces de San Andrés o PB de ladrillo), plataforma de vigas + duela, muros de bastidor con el
revestimiento del kit (tablón y junquillo / tabla traslapada / ladrillo), entrepiso de vigas y duela con hueco de escalera,
escalera interior recta de madera, divisiones de tabla, hastiales de tabla cortados al faldón, cubierta del kit (estructura de
cabios con colas + lámina ondulada o tablones escalonados) y los elementos propios de cada concepto.

Pasada AAA (2026-11-19, regla R-AAA): toda la madera es madera aserrada con su construcción real (kit.cladding.lumber: cantos
redondeados, vetas y fendas, alabeo, puntas rotas con astilla, clavos y tornillos), nada de cajas:
  · CAB_1: dados de concreto prefabricado troncopiramidales con cuñas de madera bajo los durmientes; estufa de leña de hierro
    con patas, puerta con bisagras, tapa de hornilla y regulador; tubo de 6" (Ø152) en tramos engargolados con costura, llave
    de tiro, collarín de piso, tapajuntas de techo (bota + collar de tormenta) y sombrerete; tonel de duelas con aros; leñero
    de leña partida (sectores con corteza) sobre durmientes.
  · CAB_2: pilotes 8x8 aserrados (0,20) sobre dados de concreto con base de acero (placa, anclas y orejas atornilladas),
    vigas madre 8x10 apoyadas en el pilote con cachetes atornillados, tornapuntas, cruces de San Andrés de 2x6 una por cada
    cara del pilote con tornillos de carruaje; cisterna de lámina soldada con atiesadores de ángulo, registro atornillado,
    tubo de salida con brida y válvula de compuerta, sobre durmientes.
  · CAB_3: chimenea de ladrillo a soga con trabazón en las esquinas, corona de concreto con gotero, tubo de barro, tapajuntas
    de lámina contra el techo, dedal de barro en el cuarto; sillares de piedra con aristas gastadas.
  · Porches/veranda: dados, bases de acero, postes 6x6 con fendas, viga doble atornillada con tornapuntas, viga de amarre en la
    casa (ledger) con pijas, vigas de piso perpendiculares a la casa, duela de 5/4x6 con holgura y clavos, faldón de tablas.
  · Interiores: duela con juntas sobre las vigas y dos clavos por cruce, vigas con fendas, divisiones de tablones verticales
    sobre largueros (con muesca bajo las vigas del entrepiso), escalera de mano con largueros 2x3 y peldaños redondos.
Fuentes de medidas: ver ESTADO.md (pasada AAA de cabañas) y el reporte del agente.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402,F401
from mathutils import Matrix, Vector  # noqa: E402
from mathutils.bvhtree import BVHTree  # noqa: E402

import apt_common as ac  # noqa: E402
from kit import cladding as cl  # noqa: E402
from kit.cladding import _lathe, axis_m, bolt_head, knot, lbox, lbox_m, lumber, nail  # noqa: E402
from kit.common import MB, rng  # noqa: E402

T = lambda x=0.0, y=0.0, z=0.0: Matrix.Translation((x, y, z))  # noqa: E731
RZ = ac._rot_z
RX = lambda deg: Matrix.Rotation(math.radians(deg), 4, "X")  # noqa: E731
RY = lambda deg: Matrix.Rotation(math.radians(deg), 4, "Y")  # noqa: E731
PI = math.pi
WALL_T = {"board_and_batten": 0.125, "clapboard": 0.13, "brick": 0.14}
FLOOR_T = 0.0295                    # duela 1x6 en bruto (1 1/8"): su cara inferior apoya en las vigas (cara superior a z - 0,03)


def cfg_cab(bid):
    if bid == "CAB_1_tablones":
        return dict(id=bid, w=9.0, d=6.0, levels=2, floor_h=2.8, base="piers", z0=0.40, siding="board_and_batten", pitch=35.0,
                    ovh=0.5, roof="corrugated_rust", seed=5, porch=dict(side="west", depth=2.4), stove_pipe=True,
                    stair=dict(x=-3.9, along="+x", y_side="back"), split_x=1.2)
    if bid == "CAB_2_pilotes":
        return dict(id=bid, w=7.0, d=6.0, levels=1, floor_h=2.6, base="stilts", z0=2.0, siding="clapboard", pitch=28.0, ovh=0.45,
                    roof="corrugated_light", seed=9, veranda=1.2, ext_stair=True, cistern=True, torn=True, loft=True, split_x=0.0)
    if bid == "CAB_3_ladrillo":
        return dict(id=bid, w=8.0, d=6.5, levels=2, floor_h=2.8, base="slab", z0=0.45, siding="clapboard", ground="brick", pitch=30.0,
                    ovh=0.45, roof="boards", seed=14, porch=dict(side="front", depth=2.4, x0=-0.6, x1=3.4, stair_x=(1.3, 2.5)), chimney=True,
                    stair=dict(x=-3.6, along="+x", y_side="back"), split_x=0.4, gutter=True)
    raise KeyError(bid)


STOVE_XY = (-1.8, 1.1)                 # CAB_1: estufa de leña y su tubo
CHIMNEY = (2.6, 1.2, 0.6, 0.52)        # CAB_3: centro (x, y) y sección de la chimenea de ladrillo


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
    o = [x for _, x in ops]
    if kind == "board_and_batten":
        return cl.board_and_batten(L, H, seed=seed, openings=o, rot=rot)
    if kind == "clapboard":
        return cl.clapboard(L, H, seed=seed, openings=o, loose=0.08)
    return cl.brick_wall(L, H, seed=seed, openings=o, missing=0.03, detail="aaa", fallen=False)


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
            cur = r.random() < 0.35 and v0 < 1.5                          # ventana alta (sobre escalera): sin cortina
            det.join(op.window(k, w, h, t, seed=s, broken=float(r.uniform(0.5, 1.0)), curtain=cur), Mi)
        elif kind == "door":
            det.join(op.door("plank", w, h, t, seed=s, open_angle=max(60.0, float(r.uniform(10, 70)))), Mi)
        else:
            continue
        n += 1
    return n


def _rrect(sx, sy, rad, n=4):
    """Contorno de rectángulo sx x sy centrado, esquinas de radio rad (antihorario)."""
    rad = min(rad, sx / 2 - 1e-4, sy / 2 - 1e-4)
    pts = []
    for (cx, cy, a0) in ((sx / 2 - rad, -sy / 2 + rad, -PI / 2), (sx / 2 - rad, sy / 2 - rad, 0.0),
                         (-sx / 2 + rad, sy / 2 - rad, PI / 2), (-sx / 2 + rad, -sy / 2 + rad, PI)):
        for k in range(n + 1):
            a = a0 + PI / 2 * k / n
            pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    return pts


def _loft_rr(mb, cx, cy, prof, mat, rad=0.012, n=4, top=True, bottom=True, M=None):
    """Sólido de contornos redondeados apilados: prof = [(sx, sy, z)] de abajo hacia arriba (dados, coronas, cuerpos)."""
    rings = []
    for (sx, sy, z) in prof:
        rr = rad if isinstance(rad, (int, float)) else rad
        pts = [Vector((cx + x, cy + y, z)) for x, y in _rrect(sx, sy, rr, n)]
        rings.append([mb.bm.verts.new(M @ p if M is not None else p) for p in pts])
    k = len(rings[0])
    for i in range(len(rings) - 1):
        for j in range(k):
            jj = (j + 1) % k
            mb.face([rings[i][j], rings[i][jj], rings[i + 1][jj], rings[i + 1][j]], mat)
    if bottom:
        mb.face(list(reversed(rings[0])), mat)
    if top:
        mb.face(rings[-1], mat)
    return rings


def _pier_block(mb, x, y, z_top, s_bot=0.36, s_top=0.27, z_bot=-0.10, r=None):
    """Dado de concreto prefabricado troncopiramidal (como los 'pier blocks' de 12"–14"): base enterrada, aristas de 1 cm,
    corona achaflanada. z_top = cara superior."""
    h = z_top - z_bot
    prof = [(s_bot, s_bot, z_bot), (s_bot - 0.004, s_bot - 0.004, z_bot + 0.12 * h), (s_top + 0.012, s_top + 0.012, z_top - 0.012),
            (s_top, s_top, z_top)]
    _loft_rr(mb, x, y, prof, "concrete", rad=0.012, n=4)


def _shims(mb, x, y, z, r, n=2, span=0.16):
    """Cuñas de cedro (tejamanil) que calzan el durmiente sobre el dado: asoman por los dos lados."""
    for k in range(n):
        sg = 1 if k % 2 == 0 else -1
        L = r.uniform(0.17, 0.24)
        th = r.uniform(0.010, 0.015)
        out = [(-L / 2, 0.0), (L / 2, 0.0), (L / 2, 0.0015), (-L / 2, th)]
        if sg < 0:
            out = [(-L / 2, 0.0), (L / 2, 0.0), (L / 2, th), (-L / 2, 0.0015)]
        wd = r.uniform(0.04, 0.06)
        M = T(x + sg * r.uniform(0.0, 0.03), y + r.uniform(-0.06, 0.06) - wd / 2, z) @ RZ(r.uniform(-8, 8)) @ \
            Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
        mb.plate(out, wd, "wood", m=M)


def _post_base(mb, x, y, z, s, r, straps="x", h=0.13):
    """Base de poste de acero (placa 6 mm con 4 anclas y dos orejas atornilladas al poste). s = lado del poste."""
    P = s + 0.06
    out = _rrect(P, P, 0.008, 3)
    mb.plate([(x + a, y + b) for a, b in out], 0.006, "metal_rust", m=T(0, 0, z))
    for sx in (-1, 1):
        for sy in (-1, 1):
            bolt_head(mb, (x + sx * (P / 2 - 0.018), y + sy * (P / 2 - 0.018), z + 0.006), (0, 0, 1), d=0.012, kind="nut")
    for sg in (-1, 1):
        if straps == "x":
            mn, mx = (x + sg * s / 2 + (0.0 if sg > 0 else -0.006), y - 0.04, z + 0.006), (x + sg * s / 2 + (0.006 if sg > 0 else 0.0), y + 0.04, z + h)
        else:
            mn, mx = (x - 0.04, y + sg * s / 2 + (0.0 if sg > 0 else -0.006), z + 0.006), (x + 0.04, y + sg * s / 2 + (0.006 if sg > 0 else 0.0), z + h)
        mb.box(mn, mx, "metal_rust", bevel=0.0015, seg=2)
        for zz in (z + 0.045, z + h - 0.03):
            p = Vector(((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, zz))
            ax = Vector((sg, 0, 0)) if straps == "x" else Vector((0, sg, 0))
            bolt_head(mb, p + ax * 0.003, ax, d=0.012, kind="carriage" if sg > 0 else "nut")


def boards_floor(mb, x0, x1, y0, y1, z, r, holes=(), board=0.14, t=FLOOR_T, missing=0.05, mat="wood", nail_xs=None, nails=True):
    """Duela: tablas 1x6 en bruto (0,14 x 0,0295) a lo largo de X con holgura de secado de 3–6 mm, cantos redondeados, vetas,
    fendas, abarquillado (cantos arriba) y alabeo; juntas a tope desfasadas sobre las vigas (nail_xs = ejes de las vigas) y dos
    clavos por cruce (alguno botado). Las faltantes son tablas rotas con astillas (queda el hueco) o arrancadas.
    Respeta huecos (x0, x1, y0, y1). Cara superior en z."""
    nx = sorted(nail_xs) if nail_xs else []
    y = y0
    row = 0
    while y < y1 - 0.02:
        gap = r.uniform(0.003, 0.006)
        yb = min(y + board - gap, y1)
        if yb - y < 0.03:
            break
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
            if b - a < 0.05:
                continue
            xs = [a]
            xx = a + (0.9 if row % 2 else 1.7) + r.uniform(-0.15, 0.15)
            while xx < b - 0.4:
                if nx:                                           # la junta cae al centro de una viga
                    cand = [q for q in nx if xs[-1] + 0.4 < q < b - 0.4]
                    if cand:
                        xx = min(cand, key=lambda q: abs(q - xx))
                xs.append(xx)
                xx += 2.6 + r.uniform(-0.3, 0.3)
            xs.append(b)
            for p, q in zip(xs, xs[1:]):
                pieces = [(p, q, 0.0, 0.0)]
                if r.random() < missing:
                    if q - p > 1.0 and r.random() < 0.65:
                        g0 = r.uniform(p + 0.3, q - 0.7)
                        g1 = g0 + r.uniform(0.18, 0.45)
                        pieces = [(p, g0, 0.0, r.uniform(0.02, 0.05)), (g1, q, r.uniform(0.02, 0.05), 0.0)]
                    else:
                        continue
                for (pa, pb, j0, j1) in pieces:
                    if pb - pa < 0.06:
                        continue
                    wd = yb - y
                    yc = (y + yb) / 2
                    dz = r.uniform(-0.001, 0.0022)
                    cup = -r.uniform(0.0, 0.0018)
                    lumber(mb, (pa + 0.0015, yc, z - t / 2 + dz), (pb - 0.0015, yc, z - t / 2 + dz), wd, t, mat, up=(0, 0, 1), r=r,
                           rc=0.003, step=0.6, grain=1.0, check=0.6 if r.random() < 0.18 else 0.0, cup=cup,
                           twist=r.uniform(-0.008, 0.008), jag0=j0, jag1=j1)
                    if not nails:
                        continue
                    for xn in nx:
                        if pa + 0.035 < xn < pb - 0.035:
                            for sg in (-1, 1):
                                off = wd / 2 - 0.024
                                zz = z + dz + cup * (1.0 - (2 * off / wd) ** 2)
                                pop = r.uniform(0.002, 0.006) if r.random() < 0.03 else 0.0
                                nail(mb, (xn + r.uniform(-0.007, 0.007), yc + sg * off, zz), (0, 0, 1), r=0.0042, h=0.0018, seg=6,
                                     pop=pop)
        y += board
        row += 1


def joists(mb, x0, x1, y0, y1, z_top, step=0.45, h=0.20, b=0.05, skip=(), mat="wood", r=None, xs_out=None, boxes_out=None):
    """Vigas de entrepiso (2x8 en bruto, 0,05 x 0,20) a lo largo de Y cada `step`, con fendas y vetas; `skip` = huecos
    (x0, x1, y0, y1): las vigas se cortan contra un brochal doble en los cuatro bordes. xs_out: ejes x de las vigas (para
    clavar la duela encima); boxes_out: cajas (x0, x1, y0, y1, z_inf) de cada pieza (para recortar divisiones bajo ellas)."""
    r = r if r is not None else rng(int(abs(x0 * 1000 + y0 * 37 + z_top * 101)) % 100000)

    def piece(xa, xb, ya, yb_, along):
        if along == "y":
            xc = (xa + xb) / 2
            lumber(mb, (xc, ya, z_top - h / 2), (xc, yb_, z_top - h / 2), xb - xa, h, mat, up=(0, 0, 1), r=r, rc=0.004, step=0.6,
                   grain=0.8, check=0.8 if r.random() < 0.45 else 0.0)
        else:
            yc = (ya + yb_) / 2
            lumber(mb, (xa, yc, z_top - h / 2), (xb, yc, z_top - h / 2), yb_ - ya, h, mat, up=(0, 0, 1), r=r, rc=0.004, step=0.6,
                   grain=0.8, check=0.6 if r.random() < 0.3 else 0.0)
        if boxes_out is not None:
            boxes_out.append((xa, xb, ya, yb_, z_top - h))

    n = 0
    x = x0 + b / 2
    while x < x1:
        # en la franja de un hueco: las vigas a < 1,6 b del borde las sustituye la viga de borde (trimmer); las de dentro se
        # cortan contra los cabezales
        zone = [s_ for s_ in skip if s_[0] - 1.6 * b <= x <= s_[1] + 1.6 * b]
        if zone:
            hx0, hx1, hy0, hy1 = zone[0]
            if hx0 + b / 2 + 0.002 < x < hx1 - b / 2 - 0.002:
                if hy0 - b - y0 > 0.1:
                    piece(x - b / 2, x + b / 2, y0 + 0.001, hy0 - b - 0.001, "y")
                if y1 - hy1 - b > 0.1:
                    piece(x - b / 2, x + b / 2, hy1 + b + 0.001, y1 - 0.001, "y")
        else:
            piece(x - b / 2, x + b / 2, y0 + 0.001, y1 - 0.001, "y")
            if xs_out is not None:
                xs_out.append(x)
        x += step
        n += 1
    for (hx0, hx1, hy0, hy1) in skip:                      # vigas de borde (trimmers) a todo lo largo y cabezales entre ellas
        for xx in (hx0 - b, hx1):
            piece(xx, xx + b, y0 + 0.001, y1 - 0.001, "y")
            if xs_out is not None:
                xs_out.append(xx + b / 2)
        if hy0 - b > y0 + 0.01:
            piece(hx0 + 0.001, hx1 - 0.001, hy0 - b, hy0, "x")
        if hy1 + b < y1 - 0.01:
            piece(hx0 + 0.001, hx1 - 0.001, hy1, hy1 + b, "x")
    return n


def _gable_frame(cfg, side, z_crown):
    w, d = cfg["w"], cfg["d"]
    sx = -1 if side == "west" else 1
    x_out = sx * w / 2
    if side == "west":
        return T(x_out, d / 2, z_crown) @ RZ(-90), (lambda u: d / 2 - u), x_out
    return T(x_out, -d / 2, z_crown) @ RZ(90), (lambda u: -d / 2 + u), x_out


def gable(mb, cfg, side, z_crown, t, r, top_fn):
    """Hastial (toda la profundidad del techo) en el marco local del muro (u a lo largo, y hacia dentro, v desde la solera):
    tablón y junquillo con la punta de cada tabla cortada al sesgo del faldón, o tabla traslapada de perfil cuña cuyas puntas
    siguen la línea del faldón; bastidor de pies derechos cortados a la pendiente y travesaños detrás."""
    d = cfg["d"]
    Mg, yw, x_out = _gable_frame(cfg, side, z_crown)
    pitch = math.radians(cfg["pitch"])
    margin = 0.15 / math.cos(pitch) + 0.004                 # canto vertical del cabio de remate + 4 mm

    def vt(u):
        return top_fn(x_out, yw(u)) - margin
    ur = d / 2
    vr = vt(ur)
    s = (vr - vt(ur - 1.0))                                  # pendiente del corte (dv/du) en la mitad u < ur
    sub = MB()

    def cut_at(uc):
        sg = 1.0 if uc < ur else -1.0
        n = Vector((-sg * s, 0.0, 1.0)).normalized()
        return (Vector((uc, 0.0, vt(uc))), n)
    if cfg["siding"] == "board_and_batten":
        BT = 0.022
        u = 0.02
        cols = []
        while u < d - 0.06:
            wdt = min(0.22 + r.uniform(-0.025, 0.02), d - 0.004 - u)
            cols.append((u, u + wdt))
            u += wdt + 0.022 + r.uniform(-0.006, 0.006)
        for (a, b) in cols:
            uc = (a + b) / 2
            top = min(vt(a), vt(b)) if a < ur < b else vt(uc)
            if top < 0.12:
                continue
            broken = r.random() < 0.12
            cl._vboard(sub, uc, b - a, BT, 0.0, top - (r.uniform(0.05, 0.35) if broken else 0.0), r, jag1=0.03 if broken else 0.0,
                       mat="wood", cut1=None if (broken or a < ur < b) else cut_at(uc))
        for (c0, c1) in zip(cols[:-1], cols[1:]):
            um = (c0[1] + c1[0]) / 2
            top = vt(um)
            if top < 0.15 or r.random() < 0.15:
                continue
            lumber(sub, (um, -0.011, 0.0), (um, -0.011, top), 0.064, 0.020, "wood_dark", up=(0, 1, 0), r=r, rc=0.004, grain=0.8,
                   cut1=cut_at(um))
            for vv in (0.35, 1.0, 1.65):
                if vv < top - 0.1:
                    nail(sub, (um, -0.021, vv), (0, -1, 0), r=0.0046, h=0.0025)
        y_fr = (0.024, 0.124)
    else:
        ybb, ytb = cl._clap_y()
        ex, wb = cl.CLAP_EXP, cl.CLAP_W
        H = cfg["floor_h"]
        K = max(k for k in range(60) if 0.03 + ex * k < H - 0.04)
        last_top = min(0.03 + ex * K + wb, H - 0.003)
        v0g = (0.03 + ex * (K + 1)) - H
        if 0.03 + ex * (K + 1) > last_top - 0.012:
            v0g = (last_top - 0.015) - H

        def yb_(f):
            return ybb + (ytb - ybb) * f

        def th_(f):
            return cl.CLAP_TB + (cl.CLAP_TT - cl.CLAP_TB) * f
        k = 0
        while True:
            vk = v0g + ex * k
            if vt(ur) - (vk + 0.03) < 0.0:
                break
            f1 = 1.0
            if vk + wb > vr:
                f1 = max(0.25, (vr - vk) / wb)
            v0, v1 = vk, vk + wb * f1
            rb = 0.0035
            yf0 = yb_(0) - th_(0)
            arc = [(yf0 + rb * (1 - math.sin(PI / 2 * q / 4)), v0 + rb * (1 - math.cos(PI / 2 * q / 4))) for q in range(5)]
            prof = [(yb_(0), v0), (yb_(f1), v1), (yb_(f1) - th_(f1), v1)] + arc[::-1]

            def uL(vv):
                return max(0.002, ur - (vr - vv) / s)

            def uR(vv):
                return min(d - 0.002, ur + (vr - vv) / s)
            wmin = min(uR(vv) - uL(vv) for _, vv in prof)
            if wmin < 0.06:
                break
            loose = k > 0 and r.random() < 0.05
            ns = max(2, int(math.ceil((uR(v0) - uL(v0)) / 0.35)) + 1)
            rings = []
            for i in range(ns):
                fq = i / (ns - 1)
                kick = (0.03 * fq ** 2) if loose else r.uniform(0.0, 0.0015)
                rg = []
                for (yy, vv) in prof:
                    uu = uL(vv) + (uR(vv) - uL(vv)) * fq
                    rg.append(Vector((uu, yy - (kick if vv < v0 + 0.02 else 0.0), vv)))
                rings.append(rg)
            cl._cap_loft(sub, rings, "wood_grey")
            if not loose:
                for us in [0.3 + 0.6 * j for j in range(int(d / 0.6) + 1)]:
                    if uL(v0) + 0.05 < us < uR(v0) - 0.05 and r.random() > 0.15:
                        fv = 0.025 / wb
                        yface = yb_(fv) - th_(fv)
                        nail(sub, (us + r.uniform(-0.006, 0.006), yface, vk + 0.025), (0, -1, -0.11), r=0.0045, h=0.0024)
            k += 1
        y_fr = (cl.CLAP_YS, cl.CLAP_YS + 0.10)
    # bastidor del hastial: pies derechos cada 0,60 (cortados a la pendiente) y travesaños
    u = 0.3
    ym = (y_fr[0] + y_fr[1]) / 2
    while u < d - 0.3:
        top = vt(u) - 0.01
        if top > 0.15 and abs(u - ur) > 0.06:
            lumber(sub, (u, ym, 0.002), (u, ym, top), 0.05, y_fr[1] - y_fr[0], "wood", up=(0, 1, 0), r=r, rc=0.003, grain=0.5,
                   cut1=cut_at(u) if abs(u - ur) > 0.03 else None)
        u += 0.6
    for vv in (0.45, 1.05, 1.65):
        a, b = ur - (vr - vv - 0.08) / s, ur + (vr - vv - 0.08) / s
        if b - a > 0.6:
            yc = y_fr[0] + 0.025
            lumber(sub, (a, yc, vv), (b, yc, vv), 0.09, 0.048, "wood", up=(0, 1, 0), r=r, rc=0.003, grain=0.4)
    mb.join(sub, Mg)
    sub.bm.free()


def partition_wood(mb, p0, p1, z0, H, doors=(), t=0.05, out=None, r=None, ceil=()):
    """División de tablones verticales (1x6–1x8 en bruto, 0,13–0,20 x 0,022, holgura de 3–8 mm) clavados por la otra cara a
    soleras y travesaño de 2x4 de plano (0,089 x 0,027); vanos de puerta con pies derechos de jamba y cabezal. Espesor total t.
    ceil = [(x0, x1, y0, y1, z_inf)]: obstáculos de arriba (vigas y duela del entrepiso): cada tablón sube hasta el más bajo
    que cruza su ancho (muesca entre vigas), sin meterse en ellos."""
    r = r if r is not None else rng(int(abs(p0[0] * 977 + p0[1] * 313 + z0 * 71)) % 100000)
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

    def world_fp(ua, ub):
        if along_x:
            return (a0 + ua, a0 + ub, ya - t / 2, ya + t / 2)
        return (xa - t / 2, xa + t / 2, a0 + ua, a0 + ub)

    def top_at(ua, ub):
        x0_, x1_, y0_, y1_ = world_fp(ua, ub)
        tp = H
        for (cx0, cx1, cy0, cy1, cz) in ceil:
            if cx0 < x1_ - 0.001 and cx1 > x0_ + 0.001 and cy0 < y1_ - 0.001 and cy1 > y0_ + 0.001:
                tp = min(tp, cz - z0 - 0.003)
        return tp
    sub = MB()
    BT = 0.022
    u = 0.0
    tops = []
    while u < L - 0.03:
        bw = min(r.uniform(0.13, 0.20), L - u)
        if L - (u + bw) < 0.06:
            bw = L - u
        pcs = [(u, u + bw, 0.0, H)]
        for (o0, o1, v0, v1) in ops:
            pcs = [q for p in pcs for q in cl._rect_sub(p, (o0, o1, -1.0, v1 + 0.002), min_w=0.03)]
        for (pa, pb, pc, pd) in pcs:
            # tramos de tablón bajo las vigas: se parte el tablón en franjas si una viga cruza solo parte de su ancho
            top = min(pd, top_at(pa, pb))
            tops.append(top)
            if top - pc < 0.08:
                continue
            if r.random() < 0.05 and pc < 0.01:
                continue                                                  # tablón arrancado
            jag1 = 0.0
            tt = top - 0.002
            if r.random() < 0.06:
                tt = top - r.uniform(0.3, 0.9)
                jag1 = 0.03
            lumber(sub, ((pa + pb) / 2, BT / 2, pc + 0.003), ((pa + pb) / 2, BT / 2, tt), pb - pa - 0.002, BT, "wood_grey",
                   up=(0, 1, 0), r=r, rc=0.003, step=0.5, grain=1.0, check=0.5 if r.random() < 0.25 else 0.0,
                   bow=r.uniform(-0.002, 0.002), cup=r.uniform(0.0, 0.002), jag1=jag1)
            if pb - pa > 0.12 and r.random() < 0.5:
                kv = r.uniform(pc + 0.3, max(pc + 0.35, tt - 0.3))
                ku = (pa + pb) / 2 + r.uniform(-0.03, 0.03)
                knot(sub, (ku, 0.0005, kv), (0, -1, 0), (0, 0, 1), r.uniform(0.01, 0.02), r.uniform(0.007, 0.012))
        u += bw + r.uniform(0.003, 0.008)
    # soleras, travesaño y cabezales por la cara de atrás (y = BT .. t)
    Hm = min([H] + [top_at(0.0, L)])
    ym = (BT + 0.0005 + t) / 2
    dd = t - BT - 0.0005
    rails = [0.0445, 1.0, Hm - 0.0445] if Hm > 1.3 else [0.0445, Hm - 0.0445]
    for vv in rails:
        segs = [(0.0, L)]
        for (o0, o1, v0, v1) in ops:
            if vv - 0.045 < v1 + 0.09:
                nxt = []
                for a, b in segs:
                    if o1 + 0.05 <= a or o0 - 0.05 >= b:
                        nxt.append((a, b))
                    else:
                        if o0 - 0.05 > a:
                            nxt.append((a, o0 - 0.05))
                        if o1 + 0.05 < b:
                            nxt.append((o1 + 0.05, b))
                segs = nxt
        for a, b in segs:
            if b - a > 0.1:
                lumber(sub, (a + 0.002, ym, vv), (b - 0.002, ym, vv), 0.089, dd, "wood", up=(0, 1, 0), r=r, rc=0.003, grain=0.6)
                q = a + 0.08
                while q < b - 0.05:
                    for dv in (-0.025, 0.025):
                        nail(sub, (q, 0.0, vv + dv), (0, -1, 0), r=0.0042, h=0.0018, seg=6)
                    q += r.uniform(0.15, 0.2)
    for (o0, o1, v0, v1) in ops:                                       # pies derechos de jamba y cabezal
        for uu in (o0 - 0.046, o1 + 0.001):
            lumber(sub, (uu + 0.0225, ym, 0.003), (uu + 0.0225, ym, v1), 0.045, dd, "wood", up=(0, 1, 0), r=r, rc=0.003, grain=0.5)
        hv = v1 + 0.0445 + 0.001
        if hv + 0.045 < Hm:
            lumber(sub, (o0 - 0.05, ym, hv), (o1 + 0.05, ym, hv), 0.089, dd, "wood", up=(0, 1, 0), r=r, rc=0.003, grain=0.5)
    mb.join(sub, m)
    sub.bm.free()
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
    rw = rng(cfg["seed"] + 4242)                         # madera de estructura (no altera la serie de r de vanos y puertas)
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
                _pier_block(shell, x, y, z0 - 0.365, r=rw)
                _shims(shell, x, y, z0 - 0.365, rw)
        for y in (yf + 0.15, 0.0, d / 2 - 0.15):                                   # durmientes 6x5 bajo las vigas
            lbox(shell, (-w / 2, y - 0.08, z0 - 0.35), (w / 2, y + 0.08, z0 - 0.232), "wood_dark", r=rw, axis=0, rc=0.006,
                 check=1.0, grain=1.0, step=0.6)
    elif cfg["base"] == "stilts":
        _stilts(cfg, shell, rw, r)
    else:                                                                          # losa
        shell.box((-w / 2 - 0.05, yf - 0.05, -0.1), (w / 2 + 0.05, d / 2 + 0.05, z0), "concrete", bevel=0.015, seg=4)
    # ---------------- plataforma de PB (vigas + duela) ----------------
    jx0 = []
    if cfg["base"] != "slab":
        joists(shell, -w / 2 + t, w / 2 - t, yf + t, d / 2 - t, z0 - 0.03, mat="wood_dark", r=rw, xs_out=jx0)
    st = cfg.get("stair")
    sw, going = 0.85, 0.24
    hole = None
    if st and nl > 1:
        N = max(14, int(round(fh / 0.18)))
        run = (N - 1) * going
        y_st = d / 2 - t - sw - 0.02
        hole = (st["x"] + 0.6, st["x"] + run, y_st - 0.05, d / 2 - t)
    zb0 = z0 + (0.028 if cfg["base"] == "slab" else 0.0)                      # sobre la losa: sin caras coplanares
    holes0 = []
    if cfg.get("chimney"):
        chx, chy, chw, chd = CHIMNEY
        holes0.append((chx - chw / 2 - 0.004, chx + chw / 2 + 0.004, chy - chd / 2 - 0.004, chy + chd / 2 + 0.004))
    if cfg["base"] == "slab":                       # duela de 1" sobre la losa, clavada a rastreles ahogados en el firme
        jx0 = [x for x in [-w / 2 + t + 0.2 + 0.45 * k for k in range(40)] if x < w / 2 - t - 0.1]
    boards_floor(inter, -w / 2 + t - 0.02, w / 2 - t + 0.02, yf + t - 0.02, d / 2 - t + 0.02, zb0, rw, missing=0.03, holes=holes0,
                 nail_xs=jx0, t=0.027 if cfg["base"] == "slab" else FLOOR_T)
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
        if lv > 0:
            # cinta de entrepiso: tabla de 1x8 (0,18 x 0,03) clavada sobre la junta de niveles
            bm_ = "wood_dark" if bid == "CAB_1_tablones" else "wood_grey"
            for (a, b) in (((-w / 2 - 0.03, yf - 0.035), (w / 2 + 0.03, yf - 0.005)), ((-w / 2 - 0.03, d / 2 + 0.005), (w / 2 + 0.03, d / 2 + 0.035)),
                           ((-w / 2 - 0.035, yf), (-w / 2 - 0.005, d / 2)), ((w / 2 + 0.005, yf), (w / 2 + 0.035, d / 2))):
                ax_ = 0 if abs(b[0] - a[0]) > abs(b[1] - a[1]) else 1
                lbox(shell, (a[0], a[1], zl - 0.12), (b[0], b[1], zl + 0.06), bm_, r=rw, axis=ax_, rc=0.004, grain=1.0, check=0.5,
                     sag=-0.004)
                for k in range(int(abs(b[ax_] - a[ax_]) / 0.6)):
                    c = min(a[ax_], b[ax_]) + 0.3 + 0.6 * k
                    face = (a[1 - ax_] if (a[1 - ax_] < 0) else b[1 - ax_])
                    nrm = [0.0, 0.0, 0.0]
                    nrm[1 - ax_] = -1.0 if face < 0 else 1.0
                    for dz in (-0.07, 0.01):
                        p = [0.0, 0.0, zl + dz]
                        p[ax_] = c
                        p[1 - ax_] = face
                        nail(shell, p, nrm, r=0.0046, h=0.0024)
    # ---------------- esquineros (y sillares en la PB de ladrillo) ----------------
    trim_mat = "wood_dark" if bid == "CAB_1_tablones" else "wood_grey"
    for sx in (-1, 1):
        for (yc, sy) in ((yf, -1), (d / 2, 1)):
            xo = sx * w / 2
            for lv in range(nl):
                zl, zh = z0 + lv * fh, z0 + (lv + 1) * fh
                if lv == 0 and cfg.get("ground") == "brick":
                    k = 0
                    z = zl
                    while z < zh - 0.05:                                  # sillares alternos de 0,28 de alto (piedra labrada)
                        hq = min(0.28, zh - z)
                        lq = 0.42 if k % 2 == 0 else 0.26
                        _quoin(shell, (min(xo, xo + sx * 0.035), min(yc, yc - sy * lq), z + 0.005),
                               (max(xo, xo + sx * 0.035), max(yc, yc - sy * lq), z + hq - 0.005), rw)
                        lq2 = 0.26 if k % 2 == 0 else 0.42
                        _quoin(shell, (min(xo, xo - sx * lq2), min(yc, yc + sy * 0.035), z + 0.005),
                               (max(xo, xo - sx * lq2), max(yc, yc + sy * 0.035), z + hq - 0.005), rw)
                        z += 0.28
                        k += 1
                    continue
                # tabla en la cara del testero (cubre el canto del muro de frente/fondo) y tabla en la cara de frente/fondo
                lbox(shell, (min(xo, xo + sx * 0.026), min(yc + sy * 0.026, yc - sy * (t + 0.12)), zl),
                     (max(xo, xo + sx * 0.026), max(yc + sy * 0.026, yc - sy * (t + 0.12)), zh), trim_mat, r=rw, axis=2, rc=0.004,
                     grain=1.0, check=0.6, bow=rw.uniform(-0.002, 0.002))
                lbox(shell, (min(xo - sx * 0.001, xo - sx * 0.15), min(yc, yc + sy * 0.026), zl),
                     (max(xo - sx * 0.001, xo - sx * 0.15), max(yc, yc + sy * 0.026), zh), trim_mat, r=rw, axis=2, rc=0.004,
                     grain=1.0, check=0.6, bow=rw.uniform(-0.002, 0.002))
                for zz in [zl + 0.25 + 0.6 * k for k in range(int(fh / 0.6))]:
                    nail(shell, (xo + sx * 0.026, yc - sy * (t + 0.05) + sy * 0.0, zz), (sx, 0, 0), r=0.0046, h=0.0024)
                    nail(shell, (xo - sx * 0.075, yc + sy * 0.026, zz + 0.05), (0, sy, 0), r=0.0046, h=0.0024)
    # ---------------- entrepiso ----------------
    ceil0 = []                                     # vigas y duela del nivel superior (las divisiones de PB suben hasta ellas)
    if nl > 1:
        z1 = z0 + fh
        skip = [hole] if hole else []
        holes1 = [hole] if hole else []
        if cfg.get("chimney"):
            chx, chy, chw, chd = CHIMNEY
            ch_hole = (chx - chw / 2 - 0.05, chx + chw / 2 + 0.05, chy - chd / 2 - 0.05, chy + chd / 2 + 0.05)
            skip.append(ch_hole)
            holes1.append((chx - chw / 2 - 0.004, chx + chw / 2 + 0.004, chy - chd / 2 - 0.004, chy + chd / 2 + 0.004))
        if cfg.get("stove_pipe"):
            sx_, sy_ = STOVE_XY
            holes1.append((sx_ - 0.14, sx_ + 0.14, sy_ - 0.14, sy_ + 0.14))
        jx1 = []
        joists(inter, -w / 2 + t, w / 2 - t, yf + t, d / 2 - t, z1 - 0.03, skip=skip, r=rw, xs_out=jx1, boxes_out=ceil0)
        boards_floor(inter, -w / 2 + t, w / 2 - t, yf + t, d / 2 - t, z1, rw, holes=holes1, missing=0.06, nail_xs=jx1)
        ceil0.append((-w / 2 + t, w / 2 - t, yf + t, d / 2 - t, z1 - FLOOR_T))
    if cfg.get("loft"):                                                            # tapanco sobre la mitad trasera
        zl = z0 + fh
        jxl = []
        joists(inter, -w / 2 + t, w / 2 - t, 0.2, d / 2 - t, zl - 0.03, r=rw, xs_out=jxl, boxes_out=ceil0)
        boards_floor(inter, -w / 2 + t, w / 2 - t, 0.2, d / 2 - t, zl, rw, missing=0.08, nail_xs=jxl)
        ceil0.append((-w / 2 + t, w / 2 - t, 0.2, d / 2 - t, zl - FLOOR_T))
        det.join(circ.railing("wood", 2.40 - (-w / 2 + t + 0.1), h=0.9, seed=cfg["seed"] + 3, missing=0.15),   # libre sobre la escalera de mano
                 T(-w / 2 + t + 0.1, 0.25, zl))
    # ---------------- escalera interior ----------------
    if hole:
        # zancas recortadas bajo las huellas: las tres primeras se pisan desde el cuarto (caída lateral < 0,6 m);
        # el barandal del lado del cuarto arranca en la 4.ª huella
        s = circ.stair_straight(width=sw, rise_total=fh, seed=cfg["seed"] + 1, kind="wood", going=going, broken=0.08, rail=None,
                                stringers=False)
        N_, rr, gg = s.meta["N"], s.meta["riser"], s.meta["going"]
        ks = [4] + [k for k in sorted(set(list(range(1, N_, 4)) + [N_ - 1])) if k > 4]
        s.join(circ.stair_railing([((k - 1) * gg + 0.07, 0.045, k * rr) for k in ks], h=0.9, kind="wood", seed=cfg["seed"] + 2))
        inter.join(s, T(st["x"], d / 2 - t - sw - 0.02, z0))
        stats["stair_N"] = getattr(s, "meta", {}).get("N")
    if cfg.get("loft"):                                                            # escalera de mano al tapanco
        lad = _ladder(fh + 0.9, rw)
        y_pie = 0.2 - fh * math.tan(math.radians(14)) - 0.036            # los largueros apoyan en el canto del tapanco
        inter.join(lad, T(w / 2 - t - 0.6, y_pie, z0) @ Matrix.Rotation(math.radians(-14), 4, "X"))
    # ---------------- divisiones ----------------
    idoors = []
    for lv in range(nl):
        zl = z0 + lv * fh
        cl_ = ceil0 if lv == 0 else []
        Hp = fh - 0.005 if cl_ else fh - 0.05
        xs_ = cfg["split_x"]
        partition_wood(inter, (xs_, yf + t), (xs_, d / 2 - t), zl, Hp, doors=[(-0.6, 0.85)] if lv == 0 else [(-0.6, 0.85), (2.4, 0.85)],
                       out=idoors, r=rw, ceil=cl_)
        if lv == 0:
            partition_wood(inter, (xs_, 0.9), (w / 2 - t, 0.9), zl, Hp, doors=[(xs_ + 1.0, 0.8)], out=idoors, r=rw, ceil=cl_)
        elif hole:
            partition_wood(inter, (-w / 2 + t, hole[2] - 0.15), (xs_, hole[2] - 0.15), zl, Hp, doors=[(hole[1] + 0.6, 0.85)], out=idoors,
                           r=rw, ceil=cl_)
    n_id = 0
    for dd in idoors:
        if r.random() < 0.35:
            inter.join(op.door("plank", dd["w"], dd["h"], dd["t"], seed=int(r.integers(1e6)), open_angle=max(80.0, float(r.uniform(0, 90)))),
                       dd["m"] @ T(dd["u0"], 0, 0))
            n_id += 1
        else:                                                                     # vano sin hoja: forro de jambas y cabezal
            _door_lining(inter, dd, rw)
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
        spot = rf.damage_spot("gable", w, D, P_, O_, seed=seed, damage=0.4)
        spot = (w / 2 - 1.6, -0.95, 0.45)             # junto al hastial este, entre la faja del muro y la cumbrera
    # sin losa a la altura de la solera: ni pendolones ni escombro en z = 0; en CAB_2 tampoco tirantes (los ata el tapanco)
    fr = rf.roof_frame("gable", w, D, P_, O_, seed=seed, cover=cover, tails=cfg["roof"] != "boards", damage=0.4 if spot else 0.0, spot=spot,
                       ties=not cfg.get("loft"), kingposts=False, debris=False)
    if cfg["roof"] == "boards":
        cv = rf.board_roof_stepped(w, D, P_, O_, seed=seed, missing=0.04)
    else:
        cv = rf.corrugated_roof(w, D, P_, O_, seed=seed, light=cfg["roof"] == "corrugated_light", torn=spot, detail="mid")
    MR = T(0, yc, z_crown)
    if cfg.get("chimney"):
        chx, chy, chw, chd = CHIMNEY
        ac.cull_pred(cv, lambda c: abs(c.x - chx) < chw / 2 + 0.06 and abs(c.y - (chy - yc)) < chd / 2 + 0.06)
        ac.cull_pred(fr, lambda c: abs(c.x - chx) < chw / 2 + 0.05 and abs(c.y - (chy - yc)) < chd / 2 + 0.05 and c.z > 0.2)
    roof.join(fr, MR)
    roof.join(cv, MR)
    for side in ("west", "east"):
        gable(shell, cfg, side, z_crown, t, rw, top)
    # ---------------- detalles propios ----------------
    stats["openings"] = sum(dress_ops(det, p["m"], p["ops"], p["t"], r) for p in P)
    if cfg.get("porch"):
        stats["porch"] = build_porch(cfg, shell, det, roof, r)
    if cfg.get("veranda"):
        stats["veranda"] = build_veranda(cfg, shell, det, r, top, z_crown)
    if cfg.get("stove_pipe"):
        x, y = STOVE_XY
        ac.cull_pred(roof, lambda c: math.hypot(c.x - x, c.y - y) < 0.095 and c.z > z_crown)
        bvh = BVHTree.FromBMesh(roof.bm)
        sp = MB()
        wood_stove(sp, x, y, z0, rw)
        stove_pipe(sp, x, y, z0 + 0.86, z0 + fh, z_crown + top(x, y) + 1.25, bvh, rw)
        det.join(sp)
    if cfg.get("chimney"):
        chx, chy, chw, chd = CHIMNEY
        bvh = BVHTree.FromBMesh(roof.bm)
        ztop = z_crown + rf.ridge_height("gable", w, D, P_, O_) + 0.75
        ch = MB()
        brick_chimney(ch, chx, chy, chw, chd, z0, ztop, rw, bvh=bvh, thimble=("+y", z0 + 1.55))
        det.join(ch)
    if cfg.get("cistern"):
        det.join(cistern(rw), T(-0.3, 1.02, 0.0))
    if cfg.get("torn"):                                                          # trozos de cabio y correa caídos al piso
        rd = rng(cfg["seed"] + 77)
        for k in range(5):
            L = float(rd.uniform(0.5, 0.9))
            a = float(rd.uniform(-12, 12))
            px, py = float(rd.uniform(1.2, 1.9)), -1.45 + 0.28 * k                  # una franja por trozo, bajo el desgarro
            wd, ht = (0.05, 0.12) if k % 2 else (0.06, 0.04)
            pl = MB()
            lumber(pl, (-L / 2, 0.0, ht / 2), (L / 2, 0.0, ht / 2), wd, ht, "wood", up=(0, 0, 1), r=rd, rc=0.004, grain=1.0,
                   check=0.6, jag0=rd.uniform(0.02, 0.05), jag1=rd.uniform(0.02, 0.06))
            if k % 2:
                nail(pl, (-L / 2 + 0.06, 0.0, ht), (0, 0, 1), pop=0.03, bend=0.5)
            inter.join(pl, T(px, py, z0 - 0.003) @ RZ(a))                          # asentado en la duela (tope 1,994..2,004)
    back_steps = []
    if cfg["base"] == "slab" and z0 > 0.25:                                      # escalón de madera en las puertas traseras
        for kind, uc, dw, dh, sill in SPECS[bid].get(("back", 0), []):
            if kind != "door":
                continue
            xc = w / 2 - uc
            stb = circ.stair_straight(width=1.0, rise_total=z0, seed=cfg["seed"] + 25, kind="wood", going=0.28, broken=0.1)
            runb = (stb.meta["N"] - 1) * 0.28 if hasattr(stb, "meta") and "N" in stb.meta else 0.56
            det.join(stb, T(xc - 0.5, d / 2 + 0.05 + runb, 0.0) @ RZ(-90))
            back_steps.append((xc - 0.55, xc + 0.55, d / 2, d / 2 + 0.1 + runb))
    if cfg.get("gutter"):
        stats["gutters"] = build_gutters(cfg, roof, det, top, z_crown, yf, yc, D)
    if bid == "CAB_1_tablones":
        det.join(barrel(int(r.integers(1e6))), T(1.6, yf - 0.55, 0.0))
        det.join(woodpile(int(r.integers(1e6)), 2.4, 1.0), T(2.8, yf - 0.9, 0.0))
    # ---------------- base de arena y hierba ----------------
    acfg = dict(id=cid, xs=[-w / 2, w / 2], ys=[yf if not cfg.get("veranda") else -d / 2, d / 2], seed=cfg["seed"],
                footprint=[(-w / 2, w / 2, (yf if not cfg.get("veranda") else -d / 2), d / 2)])
    keep = [(-1.0, -d / 2 - 3.0, 1.0, -d / 2)]
    caps = [(a - 0.05, b + 0.05, c0 - 0.05, c1, 0.08) for (a, b, c0, c1) in back_steps]
    keep += [(a - 0.3, c0, b + 0.3, c1 + 1.0) for (a, b, c0, c1) in back_steps]
    for kind, uc, dw, dh, sill in SPECS[bid].get(("back", 0), []):               # puertas traseras: umbral sin hierba
        if kind == "door":
            keep.append((w / 2 - uc - dw / 2 - 0.35, d / 2, w / 2 - uc + dw / 2 + 0.35, d / 2 + 1.6))
    if cfg.get("cistern"):
        keep.append((-1.55, -0.03, 0.95, 2.07))
    if cfg["base"] == "stilts":                                                 # cruces de San Andrés de los pilotes
        keep += [(sx * (w / 2 - 0.24) - 0.4, -d / 2, sx * (w / 2 - 0.24) + 0.4, d / 2) for sx in (-1, 1)]
        keep += [(-w / 2, sy * (d / 2 - 0.24) - 0.4, w / 2, sy * (d / 2 - 0.24) + 0.4) for sy in (-1, 1)]
    sr = stats.get("porch", {}).get("stair_rect")
    if sr:                                                                       # la arena no tapa los escalones del porche
        caps.append((sr[0] - 0.05, sr[1] + 0.05, sr[2] - 0.05, sr[3] + 0.05, 0.03))
    if cfg.get("porch") and cfg["porch"]["side"] == "west":
        acfg["footprint"].append((-w / 2 - cfg["porch"]["depth"], -w / 2, yf + 0.3, d / 2 - 0.3))
        keep.append((-w / 2 - cfg["porch"]["depth"] - 1.2, 1.2, -w / 2 - cfg["porch"]["depth"], 2.7))
    if cfg.get("porch") and cfg["porch"]["side"] == "front":
        pc = cfg["porch"]
        acfg["footprint"].append((pc["x0"], pc["x1"], yf - pc["depth"], yf))
        sx0, sx1 = pc["stair_x"]
        keep.append((sx0 - 0.3, yf - pc["depth"] - 1.6, sx1 + 0.3, yf - pc["depth"]))
    if cfg.get("veranda"):                                                       # pie de la escalera exterior
        keep.append((-w / 2 - 0.2, -d / 2 - stats["veranda"]["stair_run"] - 1.0, -w / 2 + 1.5, -d / 2))
    if bid == "CAB_1_tablones":                                                  # tonel y leñero: sin hierba encima
        keep.append((1.2, yf - 1.0, 2.0, yf - 0.1))
        keep.append((2.6, yf - 1.35, 5.4, yf - 0.4))
    import apt_builder as ab
    if cfg["base"] == "stilts":
        acfg["footprint"] = [(-w / 2 + 0.12 + dx - 0.3, -w / 2 + 0.12 + dx + 0.3, y - 0.3, y + 0.3) for dx in (0, w / 3 - 0.12, 2 * w / 3 - 0.12, w - 0.24)
                             for y in (-d / 2 + 0.12, 0.0, d / 2 - 0.12)]
    stats["tufts"] = ab.build_skirt(acfg, sk, margin=3.0, keep_clear=keep, inset=0.05, fill_inside=True, tuft_clear=0.35, caps=caps,
                                     cap_inside=0.15)
    for nm, mb in (("Shell", shell), ("Details", det), ("Interior", inter), ("Roof", roof), ("Skirt", sk)):
        if len(mb.bm.faces):
            out[nm].append(mb.finish(f"{cid}_{nm}", cols[nm], uv_size=2.0, merge=0))
    out["stats"] = stats
    out["cfg"] = cfg
    out["placed"] = [dict(p, side=p["side"], level=p["level"]) for p in P]
    return out


# ----------------------------------------------------------------------------------------------
# piezas de construcción
# ----------------------------------------------------------------------------------------------
def _quoin(mb, mn, mx, r):
    """Sillar de piedra labrada en la esquina de ladrillo: aristas gastadas de 7 mm en 4 tramos (sombreado continuo) y una
    esquina despostillada de vez en cuando (cuña de 1–2 cm que falta)."""
    mb.box(mn, mx, "concrete", bevel=0.007, seg=4)


def _door_lining(mb, dd, r):
    """Forro de un vano de puerta interior sin hoja: jambas y cabezal de tabla de 1x6 (0,14 x 0,02) a todo el grueso de la
    división, clavados; uno de cada tres con la jamba rajada."""
    m, u0, w, h, t = dd["m"], dd["u0"], dd["w"], dd["h"], dd["t"]
    sub = MB()
    for uu in (u0 + 0.011, u0 + w - 0.011):
        lumber(sub, (uu, t / 2, 0.003), (uu, t / 2, h - 0.002), 0.02, t + 0.012, "wood_grey", up=(0, 1, 0), r=r, rc=0.003, grain=1.0,
               check=0.7 if r.random() < 0.33 else 0.0)
    lumber(sub, (u0 + 0.001, t / 2, h - 0.011), (u0 + w - 0.001, t / 2, h - 0.011), 0.02, t + 0.012, "wood_grey", up=(0, 1, 0),
           r=r, rc=0.003, grain=1.0)
    mb.join(sub, m)
    sub.bm.free()


def _ladder(Lr, r):
    """Escalera de mano de carpintero: largueros 2x3 de canto (0,045 x 0,07) y peldaños redondos de Ø35 (24 lados) metidos
    2 cm en los largueros cada 0,27 m (OSHA 1910.23: 25–36 cm); un peldaño roto. Origen al pie, sube en +Z."""
    lad = MB()
    for sx in (-0.22, 0.22):
        lumber(lad, (sx, 0.0, 0.0), (sx, 0.0, Lr), 0.045, 0.07, "wood", up=(0, 1, 0), r=r, rc=0.004, grain=1.0, check=0.6,
               bow=r.uniform(-0.004, 0.004))
    broken = int(r.integers(3, 8))
    for k in range(1, 11):
        z = k * 0.27 + 0.0175
        if k == broken:
            for sx, sg in ((-0.2225, 1), (0.2225, -1)):
                lad.cyl((sx, 0.0, z), (sx + sg * r.uniform(0.06, 0.12), 0.0, z - 0.01), 0.0175, seg=24, mat="wood")
            continue
        lad.cyl((-0.2425, 0.0, z), (0.2425, 0.0, z), 0.0175, seg=24, mat="wood")
        for sx in (-0.22, 0.22):
            nail(lad, (sx, -0.035, z), (0, -1, 0), r=0.0042, h=0.0018, seg=6)
    return lad


def _stilts(cfg, shell, rw, r):
    """Pilotes de CAB_2: dados de concreto 0,60 con corona achaflanada, base de acero, pilote 8x8 aserrado (0,20) con fendas,
    viga madre 8x10 (0,20 x 0,25) apoyada en el pilote con cachetes de 2x6 atornillados por ambos lados, tornapuntas de 4x4 en
    los pilotes interiores, cruces de San Andrés de 2x6 (una diagonal por cada cara) con tornillos de carruaje de 1/2"."""
    w, d = cfg["w"], cfg["d"]
    z0 = cfg["z0"]
    yf = cfg.get("front_y", -d / 2)
    t = WALL_T[cfg["siding"]]
    xs = [-w / 2 + 0.12, -w / 6, w / 6, w / 2 - 0.12]
    ys = [-d / 2 + 0.12, 0.0, d / 2 - 0.12]
    zg0, zg1 = z0 - 0.48, z0 - 0.23                                          # viga madre
    zb = 0.25                                                                  # corona del dado
    for x in xs:
        for y in ys:
            _loft_rr(shell, x, y, [(0.6, 0.6, -0.15), (0.6, 0.6, zb - 0.03), (0.55, 0.55, zb)], "concrete", rad=0.02, n=4)
            _post_base(shell, x, y, zb, 0.20, rw, straps="x", h=0.13)
            tilt = float(rw.uniform(-0.25, 0.25))
            pm = MB()
            lumber(pm, (0, 0, 0.0), (0, 0, zg0 - zb - 0.006 - 0.001), 0.2, 0.2, "wood_dark", up=(0, 1, 0), r=rw, rc=0.008, grain=1.0,
                   check=1.0, step=0.4)
            shell.join(pm, T(x, y, zb + 0.006) @ Matrix.Rotation(math.radians(tilt), 4, "X"))
            # cachetes (2x6 de 0,55) en las caras ±y: abrazan pilote y viga madre, 2 tornillos en cada uno
            for sg in (-1, 1):
                yy = y + sg * (0.1 + 0.019 + 0.0005)
                lumber(shell, (x, yy, zg0 - 0.28), (x, yy, zg0 + 0.27), 0.14, 0.038, "wood_grey", up=(0, 1, 0), r=rw, rc=0.004, grain=1.0,
                       check=0.5)
            for zz in (zg0 - 0.2, zg0 - 0.08, zg0 + 0.07, zg0 + 0.19):
                for dx in (-0.035, 0.035):
                    bolt_head(shell, (x + dx, y + 0.1385, zz), (0, 1, 0), d=0.013, kind="carriage")
                    bolt_head(shell, (x + dx, y - 0.1385, zz), (0, -1, 0), d=0.013, kind="nut")
        # tornapuntas 4x4 a 45° bajo la viga madre (solo pilotes interiores: en los de orilla van las cruces)
    for x in xs[1:-1]:
        for y in ys:
            for sg in (-1, 1):
                a = Vector((x + sg * 0.1, y, zg0 - 0.42))
                b = Vector((x + sg * 0.52, y, zg0))
                dvec = (b - a).normalized()
                lumber(shell, a - dvec * 0.03, b + dvec * 0.03, 0.09, 0.09, "wood_grey", up=(0, 1, 0), r=rw, rc=0.005, grain=1.0,
                       check=0.5, cut0=(a, (-sg, 0, 0)), cut1=(b, (0, 0, 1)))
                for p in (a + dvec * 0.11, b - dvec * 0.11):
                    bolt_head(shell, p + Vector((0, 0.045, 0)), (0, 1, 0), d=0.012, kind="carriage")
                    bolt_head(shell, p - Vector((0, 0.045, 0)), (0, -1, 0), d=0.012, kind="nut")
    for y in ys:                                                               # vigas madre (las viguetas apoyan en ellas)
        lbox(shell, (-w / 2, y - 0.1, zg0), (w / 2, y + 0.1, zg1), "wood_dark", r=rw, axis=0, rc=0.008, check=1.0, grain=1.0, step=0.6)
    for (a, b) in (((-w / 2, yf), (w / 2, yf + t)), ((-w / 2, d / 2 - t), (w / 2, d / 2)),       # vigas de borde bajo los muros
                   ((-w / 2, yf + t), (-w / 2 + t, d / 2 - t)), ((w / 2 - t, yf + t), (w / 2, d / 2 - t))):
        lbox(shell, (a[0], a[1], zg1 + 0.001), (b[0], b[1], z0 - 0.002), "wood_dark", r=rw, rc=0.006, check=0.7, grain=1.0)
    # cruces de San Andrés: en frente y fondo, una diagonal por la cara exterior y la otra por la interior del pilote
    zl_, zh_ = 0.5, 1.1
    for i in range(len(xs) - 1):
        for y in (ys[0], ys[-1]):
            out_s = -1 if y < 0 else 1
            for kd, (a, b) in enumerate((((xs[i], zl_), (xs[i + 1], zh_)), ((xs[i], zh_), (xs[i + 1], zl_)))):
                face = out_s if kd == 0 else -out_s
                yy = y + face * (0.1 + 0.02)
                p0, p1 = Vector((a[0], yy, a[1])), Vector((b[0], yy, b[1]))
                _brace(shell, p0, p1, Vector((0, face, 0)), rw)
    for j in range(len(ys) - 1):
        for x in (xs[0], xs[-1]):
            face = 1 if x < 0 else -1                                             # cara interior del pilote de orilla
            xx = x + face * (0.1 + 0.02)
            p0, p1 = Vector((xx, ys[j], zl_)), Vector((xx, ys[j + 1], zh_))
            _brace(shell, p0, p1, Vector((face, 0, 0)), rw)


def _brace(mb, p0, p1, nrm, r):
    """Diagonal de 2x6 (0,14 x 0,04) de p0 a p1 (centros de pilote) prolongada 8 cm, con la cara ancha contra el pilote
    (normal nrm hacia afuera) y un tornillo de carruaje en cada pilote (tuerca y arandela del otro lado)."""
    dvec = (p1 - p0).normalized()
    a, b = p0 - dvec * 0.08, p1 + dvec * 0.08
    lumber(mb, a, b, 0.14, 0.04, "wood_grey", up=tuple(nrm), r=r, rc=0.004, grain=1.0, check=0.6 if r.random() < 0.4 else 0.0,
           jag0=0.0, jag1=0.0)
    for p in (p0, p1):
        bolt_head(mb, p + nrm * 0.02, nrm, d=0.013, kind="carriage")
        nail(mb, p + nrm * 0.02 + dvec * 0.05 + Vector((0, 0, 0.03)), nrm, r=0.0046, h=0.0024)


def wood_stove(mb, x, y, z, r):
    """Estufa de leña de caja (hierro colado, ~0,56 x 0,44 x 0,86 con patas): cuerpo de aristas redondeadas, placa superior
    con hornilla y tapa de levantar, puerta al frente (-Y) con marco, bisagras de pernio y manija de resorte, regulador de
    tiro giratorio, bandeja de cenizas, patas torneadas y collarín del tubo."""
    zb = z + 0.17
    mb.box((x - 0.28, y - 0.22, zb), (x + 0.28, y + 0.22, zb + 0.5), "metal_rust", bevel=0.012, seg=4)
    mb.box((x - 0.30, y - 0.24, zb + 0.5), (x + 0.30, y + 0.24, zb + 0.528), "metal_rust", bevel=0.006, seg=4)        # placa superior
    mb.box((x - 0.29, y - 0.23, zb - 0.02), (x + 0.29, y + 0.23, zb + 0.004), "metal_rust", bevel=0.006, seg=4)       # zócalo
    for k in range(5):                                                           # costillas de fundición en los costados
        for sg in (-1, 1):
            zz = zb + 0.08 + 0.085 * k
            mb.box((x + sg * 0.28 - 0.006, y - 0.17, zz), (x + sg * 0.28 + 0.006, y + 0.17, zz + 0.014), "metal_rust", bevel=0.004, seg=3)
    # hornilla con tapa (de levantar, con la ranura) y su aro
    _lathe(mb, [(0.105, zb + 0.527), (0.105, zb + 0.534), (0.098, zb + 0.538), (0.0, zb + 0.538)], 32, "metal_rust", T(x - 0.08, y, 0))
    mb.box((x - 0.08 - 0.03, y - 0.008, zb + 0.537), (x - 0.08 + 0.03, y + 0.008, zb + 0.546), "metal_rust", bevel=0.002, seg=2)
    # puerta
    yd = y - 0.22
    mb.box((x - 0.2, yd - 0.012, zb + 0.08), (x + 0.2, yd + 0.004, zb + 0.4), "metal_rust", bevel=0.005, seg=3)        # marco
    mb.box((x - 0.17, yd - 0.028, zb + 0.1), (x + 0.17, yd - 0.010, zb + 0.38), "metal_rust", bevel=0.006, seg=3)      # hoja
    for zz in (zb + 0.14, zb + 0.34):                                                                                   # bisagras
        mb.cyl((x - 0.185, yd - 0.024, zz - 0.025), (x - 0.185, yd - 0.024, zz + 0.025), 0.011, seg=16, mat="metal_rust")
        mb.box((x - 0.185, yd - 0.026, zz - 0.012), (x - 0.12, yd - 0.016, zz + 0.012), "metal_rust", bevel=0.002, seg=2)
    # manija de resorte (espiral de alambre) y pestillo
    hp = [Vector((x + 0.13 + 0.008 * math.cos(a), yd - 0.035 - 0.05 * a / (12 * PI), zb + 0.24 + 0.008 * math.sin(a)))
          for a in [k * PI / 6 for k in range(73)]]
    with mb.soft():
        mb.tube([Vector((x + 0.13, yd - 0.02, zb + 0.24))] + hp, 0.0022, seg=8, mat="metal_rust")
    mb.cyl((x + 0.13, yd - 0.032, zb + 0.24), (x + 0.13, yd - 0.012, zb + 0.24), 0.006, seg=16, mat="metal_rust")
    # regulador de tiro (disco con ventanas) bajo la puerta y bandeja de cenizas
    _lathe(mb, [(0.0, -0.004), (0.045, -0.004), (0.045, 0.004), (0.035, 0.008), (0.0, 0.009)], 24, "metal_rust",
           axis_m(Vector((x, yd - 0.012, zb + 0.045)), (0, -1, 0)))
    mb.box((x - 0.2, yd - 0.09, zb - 0.012), (x + 0.2, yd + 0.002, zb + 0.0), "metal_rust", bevel=0.003, seg=3)
    # patas torneadas
    for lx in (-0.24, 0.24):
        for ly in (-0.18, 0.18):
            _lathe(mb, [(0.0, z), (0.034, z), (0.036, z + 0.012), (0.022, z + 0.03), (0.018, z + 0.08), (0.026, z + 0.13),
                        (0.03, zb - 0.02), (0.0, zb - 0.02)], 20, "metal_rust", T(x + lx, y + ly, 0))
    # collarín del tubo
    _lathe(mb, [(0.06, zb + 0.52), (0.083, zb + 0.528), (0.083, zb + 0.545), (0.0795, zb + 0.55), (0.0795, z + 0.86),
                (0.07, z + 0.86)], 32, "metal_rust", T(x, y, 0))


def stove_pipe(mb, x, y, z_a, z_floor, z_top, bvh, r):
    """Tubo de estufa de 6" (Ø152) en tramos de 0,61 m (24") engargolados: costura longitudinal saliente, extremo
    corrugado que entra en el tramo de abajo, 3 pijas por unión, llave de tiro con manija de resorte; collarín y placa de
    piso en el entrepiso; en el techo, bota de lámina con base sobre las crestas (plano ajustado con rayos), collar de
    tormenta y sombrerete chino con 3 patas."""
    R = 0.0762
    z = z_a
    k = 0
    while z < z_top - 0.02:
        z2 = min(z + 0.61, z_top)
        mb.cyl((x, y, z), (x, y, z2), R, seg=32, mat="metal_rust", caps=False)
        if z2 < z_top - 0.01:                                                   # boca engargolada del tramo
            _lathe(mb, [(R - 0.002, z2 - 0.035), (R + 0.0012, z2 - 0.03), (R + 0.0012, z2 + 0.0), (R - 0.002, z2 + 0.004)], 32,
                   "metal_rust", T(x, y, 0), caps=False)
        mb.box((x - 0.003, y + R - 0.002, z + 0.01), (x + 0.003, y + R + 0.0025, z2 - 0.01), "metal_rust", bevel=0.001, seg=2)  # costura
        if z2 < z_top - 0.01:
            for a in (0.4, 2.5, 4.6):
                p = Vector((x + (R + 0.0012) * math.cos(a), y + (R + 0.0012) * math.sin(a), z2 - 0.015))
                nail(mb, p, (math.cos(a), math.sin(a), 0), r=0.0042, h=0.002, mat="metal_rust", seg=8)
        z = z2
        k += 1
    # llave de tiro a 0,30 sobre el collarín
    zd = z_a + 0.3
    with mb.soft():
        mb.cyl((x - R - 0.06, y, zd), (x + R + 0.01, y, zd), 0.0032, seg=12, mat="metal_rust")
        hp = [Vector((x - R - 0.06 - 0.05 * k / 60, y + 0.009 * math.cos(k * PI / 5), zd + 0.009 * math.sin(k * PI / 5))) for k in range(61)]
        mb.tube(hp, 0.0022, seg=8, mat="metal_rust")
    # collarín y placas de techo-piso en el entrepiso (arriba y abajo de la duela)
    for (zz, sg) in ((z_floor + 0.0005, 1), ):
        pl = [(x + a, y + b) for a, b in _rrect(0.34, 0.34, 0.01, 3)]
        mb.plate(pl, 0.003, "metal_rust", m=T(0, 0, zz))
        if sg > 0:
            _lathe(mb, [(R + 0.002, zz + 0.003), (R + 0.025, zz + 0.003), (R + 0.004, zz + 0.04), (R + 0.002, zz + 0.04),
                        (R + 0.002, zz + 0.003)], 32, "metal_rust", T(x, y, 0), caps=False)
        for (a, b) in ((-0.14, -0.14), (0.14, -0.14), (0.14, 0.14), (-0.14, 0.14)):
            nail(mb, (x + a, y + b, zz + (0.003 if sg > 0 else 0.0)), (0, 0, sg), r=0.0042, h=0.002, seg=6)
    # techo: bota con base sobre las crestas de la lámina
    pts = []
    for (dx, dy) in ((-0.3, -0.3), (0.3, -0.3), (0.3, 0.3), (-0.3, 0.3), (0.0, -0.32), (0.0, 0.32), (-0.32, 0.0), (0.32, 0.0)):
        hit = bvh.ray_cast(Vector((x + dx, y + dy, z_top + 3.0)), Vector((0, 0, -1)), 10.0)
        if hit[0] is not None:
            pts.append(hit[0])
    if len(pts) >= 4:
        import numpy as np
        A = np.array([[1.0, p.x - x, p.y - y] for p in pts])
        bz = np.array([p.z for p in pts])
        c0, cx_, cy_ = np.linalg.lstsq(A, bz, rcond=None)[0]
        res = max(p.z - (c0 + cx_ * (p.x - x) + cy_ * (p.y - y)) for p in pts)
        c0 += max(res, 0.0) + 0.002
        nrm = Vector((-cx_, -cy_, 1.0)).normalized()
        ux = Vector((1.0, 0.0, cx_)).normalized()
        uy = nrm.cross(ux)
        M = Matrix(((ux.x, uy.x, nrm.x, x), (ux.y, uy.y, nrm.y, y), (ux.z, uy.z, nrm.z, c0), (0, 0, 0, 1)))
        mb.plate(_rrect(0.56, 0.62, 0.015, 3), 0.0015, "metal_rust", m=M)

        def pz(px, py):
            return c0 + cx_ * (px - x) + cy_ * (py - y)
        # bota: el pie sigue el plano de la placa, la boca es horizontal y abraza el tubo
        zc = max(pz(x + 0.15 * math.cos(a), y + 0.15 * math.sin(a)) for a in [2 * PI * k / 32 for k in range(32)])
        rings = []
        for (rr, mode, dz) in ((0.15, "p", -0.004), (0.148, "p", 0.03), (R + 0.006, "h", 0.13), (R + 0.0015, "h", 0.135)):
            rg = []
            for k in range(32):
                a = 2 * PI * k / 32
                px, py = x + rr * math.cos(a), y + rr * math.sin(a)
                rg.append(Vector((px, py, (pz(px, py) if mode == "p" else zc) + dz)))
            rings.append(rg)
        cl._cap_loft(mb, rings, "metal_rust", caps=False)
        _lathe(mb, [(R + 0.001, zc + 0.17), (R + 0.045, zc + 0.155), (R + 0.045, zc + 0.162), (R + 0.001, zc + 0.185),
                    (R + 0.001, zc + 0.17)], 32, "metal_rust", T(x, y, 0), caps=False)                # collar de tormenta
        for k in range(10):
            a = 2 * PI * k / 10
            nail(mb, M @ Vector((0.25 * math.cos(a), 0.28 * math.sin(a), 0.0015)), nrm, r=0.0042, h=0.002, seg=6)
    # sombrerete chino con 3 patas
    zt = z_top
    _lathe(mb, [(0.0, zt + 0.16), (0.17, zt + 0.085), (0.175, zt + 0.078), (0.168, zt + 0.076), (0.0, zt + 0.15)], 32, "metal_rust", T(x, y, 0))
    for k in range(3):
        a = 2 * PI * k / 3 + 0.3
        p0 = Vector((x + (R + 0.002) * math.cos(a), y + (R + 0.002) * math.sin(a), zt - 0.06))
        p1 = Vector((x + 0.12 * math.cos(a), y + 0.12 * math.sin(a), zt + 0.1))
        lbox_m(mb, (0.0, -0.009, -0.0008), ((p1 - p0).length, 0.009, 0.0008), "metal_rust",
               T(*p0) @ (Vector((1, 0, 0)).rotation_difference((p1 - p0).normalized())).to_matrix().to_4x4(), r=r, axis=0, rc=0.0006,
               grain=0.0)


def brick_chimney(mb, cx, cy, wx, wy, z_bot, z_top, r, bvh=None, thimble=None):
    """Chimenea de ladrillo a soga (24 x 12 x 6 con junta de 1 cm rehundida) con trabazón en las esquinas: en cada hilada dos
    caras corren de esquina a esquina y las otras dos entre ellas (se alternan), ladrillos de aristas gastadas y cara irregular
    (kit.cladding._brick 'round'), núcleo de mortero detrás de las juntas; corona de concreto con gotero y lavadero, tubo de
    barro que asoma 10 cm, dos ladrillos sueltos en la corona, faltantes en las últimas hiladas; tapajuntas de lámina contra el
    techo (rayos sobre la cubierta) y dedal de barro para el tubo de la estufa (thimble = (cara, z))."""
    from kit.cladding import BRICK_D, BRICK_H, COURSE, JOINT, REC, _bond_pieces, _brick
    crown = 0.09
    zc = z_top - crown
    nc = int((zc - z_bot) / COURSE)
    zc = z_bot + nc * COURSE
    faces = {"-y": (wx, T(cx - wx / 2, cy - wy / 2, z_bot)), "+x": (wy, T(cx + wx / 2, cy - wy / 2, z_bot) @ RZ(90)),
             "+y": (wx, T(cx + wx / 2, cy + wy / 2, z_bot) @ RZ(180)), "-x": (wy, T(cx - wx / 2, cy + wy / 2, z_bot) @ RZ(-90))}
    subs = {k: MB() for k in faces}
    th_u = None
    if thimble:
        th_face, th_z = thimble
        th_u = (faces[th_face][0] / 2, th_z - z_bot)
    for c in range(nc):
        v0 = c * COURSE + JOINT / 2
        v1 = v0 + BRICK_H
        full = ("-y", "+y") if c % 2 == 0 else ("+x", "-x")
        off = r.uniform(0, 0.25)
        for k, (L, _) in faces.items():
            if k in full:
                p, q = 0.0, L
            else:
                p, q = BRICK_D + JOINT, L - BRICK_D - JOINT
            for (a, b) in _bond_pieces(p, q, off + (0.125 if c % 2 else 0.0)):
                if th_u and k == th_face and abs((a + b) / 2 - th_u[0]) < 0.17 and abs((v0 + v1) / 2 - th_u[1]) < 0.15:
                    continue                                                      # hueco del dedal
                top_courses = c >= nc - 3
                if top_courses and r.random() < 0.06 and k not in full and c < nc - 1:
                    continue                                                      # ladrillo faltante arriba
                ero = top_courses or r.random() < 0.15
                yf = r.uniform(-0.0015, 0.001) + (r.uniform(0.002, 0.005) if ero else 0.0)
                tilt = (r.uniform(-0.006, 0.006), r.uniform(-0.01, 0.01))
                chip = 1 + int(r.uniform() < 0.25) if r.uniform() < 0.08 else 0
                _brick(subs[k], a + r.uniform(-0.0015, 0.0015) * (a > 0.001), b + r.uniform(-0.0015, 0.0015) * (b < L - 0.001),
                       v0 + r.uniform(-0.001, 0.001), v1 + r.uniform(-0.001, 0.001), yf, BRICK_D - 0.004, r,
                       bev=r.uniform(0.006, 0.011) if ero else 0.004, chip=chip, tilt=tilt, mode="round")
    for k, (L, M) in faces.items():
        mb.join(subs[k], M)
        subs[k].bm.free()
    # núcleo de mortero detrás de las juntas
    mb.box((cx - wx / 2 + REC, cy - wy / 2 + REC, z_bot), (cx + wx / 2 - REC, cy + wy / 2 - REC, zc + 0.002), "mortar")
    # corona de concreto (gotero de 5 cm, lavadero hacia afuera) y tubo de barro
    _loft_rr(mb, cx, cy, [(wx + 0.1, wy + 0.1, zc + 0.002), (wx + 0.1, wy + 0.1, zc + 0.05), (wx + 0.08, wy + 0.08, zc + 0.058),
                          (0.30, 0.30, zc + crown - 0.004), (0.29, 0.29, zc + crown)], "concrete", rad=0.012, n=4)
    for (a, b, c_, d_) in ((-0.1, 0.1, -0.1, -0.082), (-0.1, 0.1, 0.082, 0.1), (-0.1, -0.082, -0.082, 0.082), (0.082, 0.1, -0.082, 0.082)):
        mb.box((cx + a, cy + c_, zc + crown - 0.06), (cx + b, cy + d_, zc + crown + 0.10), "tile_clay", bevel=0.003, seg=3)
    for k in range(2):                                                          # ladrillos sueltos en la corona
        m = T(cx + r.uniform(-0.2, 0.2), cy - wy / 2 + 0.02 + 0.1 * k, zc + crown - 0.01) @ RZ(r.uniform(-30, 30)) @ RY(r.uniform(-6, 6))
        mb.box((-0.12, -0.06, 0.0), (0.12, 0.06, 0.06), "brick", bevel=0.006, seg=4, m=m)
    # dedal de barro (tubo Ø0,20 que asoma 2 cm) con su anillo de lámina
    if thimble:
        L, M = faces[th_face]
        Mt = M @ T(th_u[0], 0.0, th_u[1]) @ RX(90)
        _lathe(mb, [(0.085, -0.10), (0.1, -0.10), (0.1, 0.02), (0.085, 0.02), (0.085, -0.09)], 32, "tile_clay", Mt)
        _lathe(mb, [(0.1, 0.012), (0.13, 0.012), (0.13, 0.016), (0.1, 0.016), (0.1, 0.012)], 32, "metal_rust", Mt, caps=False)
        mb.box((-0.17, 0.004, -0.15), (0.17, 0.12, 0.15), "mortar", m=M @ T(th_u[0], 0.0, th_u[1]))   # relleno del hueco
    # tapajuntas contra el techo: base sobre la cubierta + vuelta de 12 cm contra el ladrillo
    if bvh is not None:
        for (fx, fy, along) in ((0, -1, "x"), (0, 1, "x"), (-1, 0, "y"), (1, 0, "y")):
            L = wx if along == "x" else wy
            for s in [i / 6 for i in range(7)]:
                pass
            px = cx + fx * (wx / 2 + 0.08)
            py = cy + fy * (wy / 2 + 0.08)
            samples = []
            for s in (-0.5, -0.25, 0.0, 0.25, 0.5):
                qx = px + (s * (L + 0.24) if along == "x" else 0.0)
                qy = py + (s * (L + 0.24) if along == "y" else 0.0)
                hit = bvh.ray_cast(Vector((qx, qy, z_top + 2.0)), Vector((0, 0, -1)), 10.0)
                if hit[0] is not None:
                    samples.append(hit[0])
            if len(samples) < 2:
                continue
            for i in range(len(samples) - 1):
                a, b = samples[i], samples[i + 1]
                za, zb_ = a.z + 0.004, b.z + 0.004
                if along == "x":
                    p0 = Vector((a.x, cy + fy * (wy / 2 + 0.003), za))
                    p1 = Vector((b.x, cy + fy * (wy / 2 + 0.003), zb_))
                    off = Vector((0, fy * 0.075, 0))
                else:
                    p0 = Vector((cx + fx * (wx / 2 + 0.003), a.y, za))
                    p1 = Vector((cx + fx * (wx / 2 + 0.003), b.y, zb_))
                    off = Vector((fx * 0.075, 0, 0))
                lumber(mb, p0 + off, p1 + off, 0.15, 0.0015, "metal_rust", up=(0, 0, 1), r=r, rc=0.0006, grain=0.0, center=True)
                up_n = Vector((fx, fy, 0))
                lumber(mb, p0 + Vector((0, 0, 0.06)) + up_n * 0.0008, p1 + Vector((0, 0, 0.06)) + up_n * 0.0008, 0.12, 0.0015,
                       "metal_rust", up=tuple(up_n), r=r, rc=0.0006, grain=0.0)
                for p in (p0 + Vector((0, 0, 0.1)), ):
                    nail(mb, p + up_n * 0.0016, up_n, r=0.0042, h=0.002, seg=6)


def cistern(r):
    """Cisterna de lámina soldada (1,80 x 1,40 x 1,60, CAB_2) semienterrada: cuerpo de aristas redondeadas, atiesadores de
    ángulo de 2" verticales y un cinturón a media altura, registro circular de 0,50 con tapa atornillada, respiradero de cuello
    de ganso, tubo de salida de 2" con brida y válvula de compuerta (volante de 4 rayos), sobre dos durmientes. Origen al centro
    de la base (x -0,90..0,90, y -0,70..0,70; la vieja ocupaba x -1,2..0,6, y 0,32..1,72 colocada en (-0,3, 1,02))."""
    mb = MB()
    W, D_, H = 1.8, 1.4, 1.6
    z0 = -0.05
    mb.box((-W / 2, -D_ / 2, z0), (W / 2, D_ / 2, z0 + H), "metal_rust", bevel=0.02, seg=4)
    # atiesadores: ángulos 50x50x5 verticales en las caras largas y cinturón a media altura
    for sy in (-1, 1):
        for k in range(5):
            x = -W / 2 + 0.18 + 0.36 * k
            y = sy * D_ / 2
            mb.box((x - 0.025, y - (0.05 if sy < 0 else 0.0), z0 + 0.04), (x + 0.025, y + (0.0 if sy < 0 else 0.05), z0 + H - 0.04),
                   "metal_rust", bevel=0.002, seg=2)
            mb.box((x - 0.0025, y - (0.003 if sy < 0 else 0.0), z0 + 0.04), (x + 0.0025, y + (0.0 if sy < 0 else 0.003), z0 + H - 0.04),
                   "metal_rust", bevel=0.0, seg=1)
    for sx in (-1, 1):
        for k in range(3):
            y = -D_ / 2 + 0.25 + 0.45 * k
            x = sx * W / 2
            mb.box((x - (0.05 if sx < 0 else 0.0), y - 0.025, z0 + 0.04), (x + (0.0 if sx < 0 else 0.05), y + 0.025, z0 + H - 0.04),
                   "metal_rust", bevel=0.002, seg=2)
    zm = z0 + H / 2
    for (a, b) in (((-W / 2 - 0.006, -D_ / 2 - 0.056), (W / 2 + 0.006, -D_ / 2 - 0.05)), ((-W / 2 - 0.006, D_ / 2 + 0.05), (W / 2 + 0.006, D_ / 2 + 0.056)),
                   ((-W / 2 - 0.056, -D_ / 2 - 0.05), (-W / 2 - 0.05, D_ / 2 + 0.05)), ((W / 2 + 0.05, -D_ / 2 - 0.05), (W / 2 + 0.056, D_ / 2 + 0.05))):
        mb.box((a[0], a[1], zm - 0.03), (b[0], b[1], zm + 0.03), "metal_rust", bevel=0.002, seg=2)
    # registro con tapa atornillada
    zt = z0 + H
    _lathe(mb, [(0.23, zt - 0.01), (0.25, zt - 0.01), (0.25, zt + 0.06), (0.23, zt + 0.06)], 40, "metal_rust", T(0.35, 0.0, 0))
    _lathe(mb, [(0.0, zt + 0.06), (0.29, zt + 0.06), (0.29, zt + 0.075), (0.27, zt + 0.08), (0.0, zt + 0.085)], 40, "metal_rust",
           T(0.35, 0.0, 0) @ RY(1.2))
    for k in range(12):
        a = 2 * PI * k / 12
        bolt_head(mb, (0.35 + 0.265 * math.cos(a), 0.265 * math.sin(a), zt + 0.078), (0, 0, 1), d=0.012, kind="nut")
    mb.box((0.35 - 0.012, -0.12, zt + 0.08), (0.35 + 0.012, 0.12, zt + 0.1), "metal_rust", bevel=0.004, seg=3)          # asa
    # respiradero de cuello de ganso (Ø2")
    pts = [Vector((-0.5, 0.2, zt - 0.01)), Vector((-0.5, 0.2, zt + 0.06))] + \
        [Vector((-0.5 + 0.07 - 0.07 * math.cos(a), 0.2, zt + 0.06 + 0.07 * math.sin(a))) for a in [PI * k / 12 for k in range(1, 13)]] + \
        [Vector((-0.5 + 0.14, 0.2, zt + 0.0))]
    mb.tube(pts, 0.03, seg=24, mat="metal_rust")
    # salida de 2" con brida y válvula de compuerta
    ya = -D_ / 2
    zo = z0 + 0.32
    xo = -0.3
    mb.cyl((xo, ya + 0.01, zo), (xo, ya - 0.12, zo), 0.03, seg=24, mat="metal_rust")
    for yy in (ya - 0.12, ya - 0.135):
        _lathe(mb, [(0.03, 0.0), (0.075, 0.0), (0.075, 0.015), (0.03, 0.015)], 32, "metal_rust", axis_m(Vector((xo, yy, zo)), (0, -1, 0)))
    for k in range(4):
        a = 2 * PI * k / 4 + PI / 4
        bolt_head(mb, (xo + 0.055 * math.cos(a), ya - 0.15, zo + 0.055 * math.sin(a)), (0, -1, 0), d=0.01, kind="nut")
    mb.box((xo - 0.06, ya - 0.33, zo - 0.06), (xo + 0.06, ya - 0.15, zo + 0.06), "metal_rust", bevel=0.012, seg=4)      # cuerpo
    mb.box((xo - 0.035, ya - 0.28, zo + 0.06), (xo + 0.035, ya - 0.2, zo + 0.17), "metal_rust", bevel=0.008, seg=4)     # bonete
    mb.cyl((xo, ya - 0.24, zo + 0.17), (xo, ya - 0.24, zo + 0.26), 0.008, seg=16, mat="metal_rust")
    _lathe(mb, [(0.012, -0.008), (0.012, 0.008), (0.0, 0.009)], 16, "metal_rust", T(xo, ya - 0.24, zo + 0.26))
    with mb.soft():
        rim = [Vector((xo + 0.075 * math.cos(2 * PI * k / 40), ya - 0.24 + 0.075 * math.sin(2 * PI * k / 40), zo + 0.255)) for k in range(41)]
        mb.tube(rim, 0.006, seg=12, mat="metal_rust")
    for k in range(4):
        a = 2 * PI * k / 4
        mb.cyl((xo, ya - 0.24, zo + 0.255), (xo + 0.073 * math.cos(a), ya - 0.24 + 0.073 * math.sin(a), zo + 0.255), 0.004, seg=12,
               mat="metal_rust")
    mb.cyl((xo, ya - 0.33, zo), (xo, ya - 0.5, zo - 0.02), 0.03, seg=24, mat="metal_rust")
    return mb


def barrel(seed):
    """Tonel de duelas (barrica de 200 L: alto 0,88, Ø cabeza 0,53, Ø barriga 0,64): 26 duelas abombadas con holgura y una
    corrida, chanfle (croze) en las bocas, tapa de 3 tablas con una faltante, 6 aros de fleje oxidado (3 cm x 2 mm) que
    siguen la barriga; uno de los aros caído y flojo."""
    r = rng(seed)
    mb = MB()
    Hh = 0.88
    Rh, Rb = 0.265, 0.32
    ns = 26
    t = 0.022

    def rad(z):
        u = (z / Hh) * 2 - 1
        return Rh + (Rb - Rh) * (1 - u * u)
    zs = [Hh * k / 10 for k in range(11)]
    gap = 0.0025
    for i in range(ns):
        a0 = 2 * PI * i / ns + gap / Rb
        a1 = 2 * PI * (i + 1) / ns - gap / Rb
        dz = r.uniform(-0.004, 0.004) + (0.025 if i == 7 else 0.0)
        rings = []
        for z in zs:
            Ro = rad(z)
            zz = z + dz
            ring = []
            for q in range(4):
                a = a0 + (a1 - a0) * q / 3
                ring.append(Vector((Ro * math.cos(a), Ro * math.sin(a), zz)))
            for q in range(3, -1, -1):
                a = a0 + (a1 - a0) * q / 3
                ring.append(Vector(((Ro - t) * math.cos(a), (Ro - t) * math.sin(a), zz)))
            rings.append(ring)
        cl._cap_loft(mb, rings, "wood_dark")
    for zc in (Hh - 0.035,):                                                 # tapa de 3 tablas (falta una)
        Rt = rad(zc) - t + 0.006
        for k, (y0, y1) in enumerate(((-Rt, -Rt / 3 - 0.002), (-Rt / 3 + 0.002, Rt / 3 - 0.002), (Rt / 3 + 0.002, Rt))):
            if k == 2:
                continue
            pts = []
            for q in range(17):
                yy = y0 + (y1 - y0) * q / 16
                pts.append((math.sqrt(max(Rt * Rt - yy * yy, 0.0)), yy))
            for q in range(16, -1, -1):
                yy = y0 + (y1 - y0) * q / 16
                pts.append((-math.sqrt(max(Rt * Rt - yy * yy, 0.0)), yy))
            mb.plate(pts, 0.022, "wood_dark", m=T(0, 0, zc - 0.011 + r.uniform(-0.003, 0.0)))
    Rb0 = rad(0.035) - t + 0.006
    mb.cyl((0, 0, 0.024), (0, 0, 0.046), Rb0, seg=40, mat="wood_dark")                # fondo
    for (z, drop) in ((0.03, 0.0), (0.16, 0.0), (0.33, 0.0), (0.55, 0.0), (0.72, 0.0), (0.85, 0.0)):
        if z == 0.72:
            continue
        rings = []
        for zz in (z - 0.015, z + 0.015):
            Ro = rad(zz) + 0.0015
            rings.append([Vector((Ro * math.cos(2 * PI * k / 64), Ro * math.sin(2 * PI * k / 64), zz)) for k in range(64)])
        rings.append([p * ((rad(z + 0.015) - 0.0005) / (rad(z + 0.015) + 0.0015)) for p in rings[-1]])
        rings[-1] = [Vector((p.x, p.y, z + 0.015)) for p in rings[-1]]
        r2 = [Vector((p.x * (rad(z - 0.015) - 0.0005) / (rad(z - 0.015) + 0.0015), p.y * (rad(z - 0.015) - 0.0005) / (rad(z - 0.015) + 0.0015), z - 0.015))
              for p in rings[0]]
        rings.append(r2)
        rings.append(rings[0])
        cl._cap_loft(mb, rings, "metal_rust", caps=False)
        for k in range(3):
            a = 2 * PI * k / 3 + z
            nail(mb, (rad(z) * math.cos(a) + 0.002 * math.cos(a), rad(z) * math.sin(a) + 0.002 * math.sin(a), z), (math.cos(a), math.sin(a), 0),
                 r=0.004, h=0.0018, seg=6)
    # aro caído en la arena junto al tonel
    m = T(0.72, -0.25, 0.012) @ RX(4)
    rings = []
    for (rr, zz) in ((Rb + 0.01, -0.015), (Rb + 0.01, 0.015), (Rb + 0.008, 0.015), (Rb + 0.008, -0.015)):
        rings.append([m @ Vector((rr * math.cos(2 * PI * k / 64), rr * math.sin(2 * PI * k / 64) * 0.98, zz * 0.1 + 0.0)) for k in range(64)])
    for i in range(4):
        A, B = rings[i], rings[(i + 1) % 4]
        vA = [mb.bm.verts.new(p) for p in A]
        vB = [mb.bm.verts.new(p) for p in B]
        for k in range(64):
            kk = (k + 1) % 64
            mb.face([vA[k], vA[kk], vB[kk], vB[k]], "metal_rust")
    return mb


def woodpile(seed, L, H):
    """Leñero: leña partida de 0,40–0,50 (sectores de rollo de Ø 0,14–0,24 con corteza, algunos rollos chicos enteros) en
    hiladas sobre dos durmientes, con estacas en las puntas; testas con el corte de motosierra (cara plana levemente sesgada)."""
    r = rng(seed)
    mb = MB()
    depth = 0.46
    for y in (-0.16, 0.16):                                                   # durmientes
        lumber(mb, (-0.05, y, 0.045), (L + 0.05, y, 0.045), 0.09, 0.09, "wood_dark", up=(0, 0, 1), r=r, rc=0.006, check=1.0)
    for x in (-0.02, L + 0.02):                                               # estacas
        for y in (-0.12, 0.12):
            lumber(mb, (x, y, -0.15), (x + r.uniform(-0.02, 0.02), y, H + 0.12), 0.05, 0.05, "wood", up=(1, 0, 0), r=r, rc=0.006, jag1=0.02)
    z = 0.09
    row = 0
    while z < H - 0.06:
        x = 0.03 + (0.04 if row % 2 else 0.0)
        hmax = 0.0
        while x < L - 0.1:
            R0 = r.uniform(0.07, 0.12)
            kind = r.random()
            if kind < 0.2:
                a0, a1 = 0.0, 2 * PI                                        # rollo entero chico
                R0 *= 0.65
            elif kind < 0.6:
                a0 = r.uniform(0, 2 * PI)
                a1 = a0 + PI * r.uniform(0.45, 0.6)                           # cuarto
            else:
                a0 = r.uniform(0, 2 * PI)
                a1 = a0 + PI * r.uniform(0.9, 1.05)                           # mitad
            prof = []
            full = a1 - a0 >= 2 * PI - 1e-6
            nseg = 14 if not full else 18
            for k in range(nseg + 1 if not full else nseg):
                a = a0 + (a1 - a0) * k / nseg
                rr = R0 * (1.0 + 0.04 * math.sin(5 * a + R0 * 30))
                prof.append((rr * math.cos(a), rr * math.sin(a)))
            if not full:
                prof.append((0.0, 0.0))
            cxs = [p[0] for p in prof]
            czs = [p[1] for p in prof]
            mx_, mn_ = max(cxs), min(cxs)
            zx, zn = max(czs), min(czs)
            wpc = mx_ - mn_
            if x + wpc > L - 0.03:
                break
            ln = r.uniform(0.40, 0.50)
            rings = []
            for q, yy in enumerate((-ln / 2, -ln / 6, ln / 6, ln / 2)):
                sk = r.uniform(-0.012, 0.012) if q in (0, 3) else 0.0
                rings.append([Vector((x - mn_ + px + sk * 0.3, yy + sk * pz * 3.0, z - zn + pz)) for px, pz in prof])
            cl._cap_loft(mb, rings, "wood")
            hmax = max(hmax, zx - zn)
            x += wpc + r.uniform(0.004, 0.015)
        z += max(0.09, hmax * 0.82)
        row += 1
    return mb


def build_porch(cfg, shell, det, roof, r):
    """Porche de madera: dados de concreto con base de acero, postes 6x6 (0,14) con fendas, viga doble de 2x8 atornillada sobre
    los postes con tornapuntas de 4x4, viga de amarre (ledger) a la casa con pijas, vigas de piso 2x6 perpendiculares a la casa
    cada 0,60 sobre una viga de borde, duela de 5/4x6 paralela a la casa con holgura y clavos (con muesca en los postes),
    faldón de tablas verticales, barandal entre postes y escalones de madera; cubierta de un agua (media cubierta del kit)."""
    from kit import circulation as circ
    from kit import roofing as rf
    rw = rng(cfg["seed"] + 9191)
    w, d = cfg["w"], cfg["d"]
    yf = cfg.get("front_y", -d / 2)
    pc = cfg["porch"]
    dep = pc["depth"]
    z0 = cfg["z0"]
    west = pc["side"] == "west"
    if west:
        x0, x1, y0, y1 = -w / 2 - dep, -w / 2, yf + 0.3, d / 2 - 0.3
    else:
        x0, x1, y0, y1 = pc["x0"], pc["x1"], yf - dep, yf
    zdeck = z0 + (0.012 if cfg["base"] == "slab" else 0.0)   # al nivel del piso (sobre el canto de la losa, sin z-fighting)
    zb = cfg["z0"] + cfg["floor_h"] - 0.35 if cfg["levels"] > 1 else cfg["z0"] + cfg["floor_h"] - 0.2
    pitch = 9.0 if cfg["levels"] > 1 else 18.0
    posts = []
    if west:
        for y in (y0 + 0.1, (y0 + y1) / 2, y1 - 0.1):
            posts.append((x0 + 0.1, y))
    else:
        sx0, sx1 = pc["stair_x"]                    # el poste intermedio queda junto al escalón, no frente a él
        for x in (x0 + 0.1, sx0 - 0.08, x1 - 0.1):
            posts.append((x, y0 + 0.1))
    zpost = max(zb - (dep - 0.1) * math.tan(math.radians(pitch)), zdeck + 2.15)
    zj_top = zdeck - FLOOR_T - 0.0005
    hj = 0.15
    # ---- dados, bases y postes ----
    for (x, y) in posts:
        _pier_block(shell, x, y, 0.12, s_bot=0.32, s_top=0.26, z_bot=-0.12)
        _post_base(shell, x, y, 0.12, 0.14, rw, straps="y" if west else "x", h=0.12)
        lumber(shell, (x, y, 0.126), (x, y, zpost - 0.001), 0.14, 0.14, "wood_grey", up=(0, 1, 0), r=rw, rc=0.007, grain=1.0,
               check=1.0, step=0.4, bow=rw.uniform(-0.004, 0.004))
    # ---- viga doble sobre los postes + tornapuntas ----
    if west:
        for k, xx in enumerate((x0 + 0.1 - 0.0355, x0 + 0.1 + 0.0355)):
            lbox(shell, (xx - 0.0345, y0, zpost), (xx + 0.0345, y1, zpost + 0.16), "wood_grey", r=rw, axis=1, rc=0.005, check=0.8,
                 grain=1.0)
        for (x, y) in posts:
            for zz in (zpost + 0.05, zpost + 0.11):
                bolt_head(shell, (x0 + 0.1 - 0.07, y, zz), (-1, 0, 0), d=0.013, kind="carriage")
                bolt_head(shell, (x0 + 0.1 + 0.07, y, zz), (1, 0, 0), d=0.013, kind="nut")
            for sg in (-1, 1):
                if not (y0 + 0.6 < y + sg * 0.55 < y1 - 0.05):
                    continue
                a = Vector((x0 + 0.1, y + sg * 0.07, zpost - 0.45))
                b = Vector((x0 + 0.1, y + sg * 0.52, zpost))
                dv = (b - a).normalized()
                lumber(shell, a - dv * 0.02, b + dv * 0.02, 0.09, 0.09, "wood_grey", up=(1, 0, 0), r=rw, rc=0.005, grain=1.0,
                       cut0=(a, (0, -sg, 0)), cut1=(b, (0, 0, 1)), check=0.5)
                for p in (a + dv * 0.11, b - dv * 0.11):
                    bolt_head(shell, p + Vector((-0.045, 0, 0)), (-1, 0, 0), d=0.012, kind="carriage")
    else:
        for xx in (y0 + 0.1 - 0.0355, y0 + 0.1 + 0.0355):
            lbox(shell, (x0, xx - 0.0345, zpost), (x1, xx + 0.0345, zpost + 0.16), "wood_grey", r=rw, axis=0, rc=0.005, check=0.8,
                 grain=1.0)
        for (x, y) in posts:
            for zz in (zpost + 0.05, zpost + 0.11):
                bolt_head(shell, (x, y0 + 0.1 - 0.07, zz), (0, -1, 0), d=0.013, kind="carriage")
                bolt_head(shell, (x, y0 + 0.1 + 0.07, zz), (0, 1, 0), d=0.013, kind="nut")
            for sg in (-1, 1):
                if not (x0 + 0.05 < x + sg * 0.55 < x1 - 0.05):
                    continue
                a = Vector((x + sg * 0.07, y0 + 0.1, zpost - 0.45))
                b = Vector((x + sg * 0.52, y0 + 0.1, zpost))
                dv = (b - a).normalized()
                lumber(shell, a - dv * 0.02, b + dv * 0.02, 0.09, 0.09, "wood_grey", up=(0, 1, 0), r=rw, rc=0.005, grain=1.0,
                       cut0=(a, (-sg, 0, 0)), cut1=(b, (0, 0, 1)), check=0.5)
                for p in (a + dv * 0.11, b - dv * 0.11):
                    bolt_head(shell, p + Vector((0, -0.045, 0)), (0, -1, 0), d=0.012, kind="carriage")
    # ---- estructura del piso: ledger, viga de borde (por dentro de los postes) y vigas perpendiculares a la casa ----
    jpos = []
    holes = [(px - 0.072, px + 0.072, py - 0.072, py + 0.072) for (px, py) in posts]
    if west:
        lbox(shell, (x1 - 0.062, y0, zj_top - hj), (x1 - 0.024, y1, zj_top), "wood_grey", r=rw, axis=1, rc=0.004, check=0.6)   # ledger
        lbox(shell, (x0 + 0.171, y0, zj_top - hj), (x0 + 0.209, y1, zj_top), "wood_grey", r=rw, axis=1, rc=0.004, check=0.6)   # borde
        for k in range(int((y1 - y0) / 0.6) + 1):
            yy = min(y0 + 0.03 + 0.6 * k, y1 - 0.03)
            jpos.append(yy)
            lumber(shell, (x0 + 0.21, yy, zj_top - hj / 2), (x1 - 0.063, yy, zj_top - hj / 2), 0.038, hj, "wood_grey", up=(0, 0, 1),
                   r=rw, rc=0.004, check=0.5 if rw.random() < 0.4 else 0.0)
            bolt_head(shell, (x1 - 0.062, yy + 0.3, zj_top - hj / 2), (1, 0, 0), d=0.012, kind="nut") if yy + 0.3 < y1 else None
        tmp = MB()                                         # duela paralela a la casa (a lo largo de Y): se arma girada 90°
        lh = [(hy0, hy1, -hx1, -hx0) for (hx0, hx1, hy0, hy1) in holes]
        ys_j = min(jpos, key=lambda q: abs(q - (y1 - 1.4)))                     # junta sobre una viga
        boards_floor(tmp, y0, ys_j, -(x1 - 0.02), -(x0 + 0.02), zdeck, rw, holes=lh, missing=0.08, mat="wood_grey", nail_xs=jpos)
        boards_floor(tmp, ys_j, y1, -(x1 - 0.02), -(x0 + 0.02), zdeck, rw, holes=lh, missing=0.0, mat="wood_grey", nail_xs=jpos)
        shell.join(tmp, RZ(90))
        tmp.bm.free()
    else:
        lbox(shell, (x0, y1 - 0.062, zj_top - hj), (x1, y1 - 0.024, zj_top), "wood_grey", r=rw, axis=0, rc=0.004, check=0.6)
        lbox(shell, (x0, y0 + 0.171, zj_top - hj), (x1, y0 + 0.209, zj_top), "wood_grey", r=rw, axis=0, rc=0.004, check=0.6)
        for k in range(int((x1 - x0) / 0.6) + 1):
            xx = min(x0 + 0.03 + 0.6 * k, x1 - 0.03)
            jpos.append(xx)
            lumber(shell, (xx, y0 + 0.21, zj_top - hj / 2), (xx, y1 - 0.063, zj_top - hj / 2), 0.038, hj, "wood_grey", up=(0, 0, 1),
                   r=rw, rc=0.004, check=0.5 if rw.random() < 0.4 else 0.0)
        boards_floor(shell, x0 + 0.02, x1 - 0.02, y0, y0 + 0.42, zdeck, rw, missing=0.0, mat="wood_grey", holes=holes, nail_xs=jpos)
        boards_floor(shell, x0 + 0.02, x1 - 0.02, y0 + 0.42, y1, zdeck, rw, missing=0.08, mat="wood_grey", holes=holes, nail_xs=jpos)
    # ---- faldón de tablas verticales bajo el borde (sin tapar la escalera) ----
    if west:
        sk_y0, sk_y1 = y1 - 1.25 - 0.05, y1 - 0.25 + 0.05
        yy = y0 + 0.01
        while yy < y1 - 0.12:
            wb = rw.uniform(0.13, 0.19)
            if not (yy + wb > sk_y0 and yy < sk_y1) and rw.random() > 0.12:
                lumber(shell, (x0 + 0.02 - 0.011, yy + wb / 2, -0.02), (x0 + 0.02 - 0.011, yy + wb / 2, zj_top - 0.02 - rw.uniform(0, 0.03)),
                       wb - 0.004, 0.022, "wood_grey", up=(1, 0, 0), r=rw, rc=0.003, grain=1.0, check=0.4, jag1=0.02 if rw.random() < 0.2 else 0.0)
            yy += wb + rw.uniform(0.01, 0.03)
    else:
        sx0, sx1 = pc["stair_x"]
        xx = x0 + 0.01
        while xx < x1 - 0.12:
            wb = rw.uniform(0.13, 0.19)
            if not (xx + wb > sx0 - 0.05 and xx < sx1 + 0.05) and rw.random() > 0.12:
                lumber(shell, (xx + wb / 2, y0 + 0.02 - 0.011, -0.02), (xx + wb / 2, y0 + 0.02 - 0.011, zj_top - 0.02 - rw.uniform(0, 0.03)),
                       wb - 0.004, 0.022, "wood_grey", up=(0, 1, 0), r=rw, rc=0.003, grain=1.0, check=0.4, jag1=0.02 if rw.random() < 0.2 else 0.0)
            xx += wb + rw.uniform(0.01, 0.03)
    # ---- barandal entre postes y escalones ----
    if west:
        xr = x0 + 0.1
        segs = [(y0 + 0.1 + 0.07, (y0 + y1) / 2 - 0.07), ((y0 + y1) / 2 + 0.07, y1 - 1.4)]
        for i, (a, b) in enumerate(segs):
            if b - a > 0.3:
                ac.rail_along(det, "wood", (xr, a), (xr, b), zdeck, "-x", seed=cfg["seed"] + 21 + i, bend=0.2 if i == 0 else 0.0, missing=0.2)
        st = circ.stair_straight(width=1.0, rise_total=zdeck, seed=cfg["seed"] + 24, kind="wood", going=0.28, broken=0.15)
        run = (st.meta["N"] - 1) * 0.28 if hasattr(st, "meta") and "N" in st.meta else 0.56
        det.join(st, T(x0 - run, y1 - 1.25, 0.0))                # escalones a la arena en el claro del barandal
        stair_rect = (x0 - run, x0, y1 - 1.25, y1 - 0.25)
    else:
        yr = y0 + 0.1
        det.join(circ.railing("wood", (sx0 - 0.15) - (x0 + 0.17), h=0.9, seed=cfg["seed"] + 21, missing=0.15), T(x0 + 0.17, yr, zdeck))
        det.join(circ.railing("wood", (x1 - 0.17) - (sx1 + 0.05), h=0.9, seed=cfg["seed"] + 22, missing=0.1, bend=0.2),
                 T(sx1 + 0.05, yr, zdeck))
        st = circ.stair_straight(width=sx1 - sx0, rise_total=zdeck, seed=cfg["seed"] + 23, kind="wood", going=0.28, broken=0.15)
        run = (st.meta["N"] - 1) * 0.28 if hasattr(st, "meta") and "N" in st.meta else 0.56
        det.join(st, T(sx1, y0 - run, 0.0) @ RZ(90))           # centrado en la puerta
        stair_rect = (sx0, sx1, y0 - run, y0)
    # cubierta de un agua: media cubierta a dos aguas del kit (cumbrera contra el muro) + su estructura
    if west:
        Lr, depth = (y1 - y0) + 0.4, dep
        frame = rf.roof_frame("gable", Lr, 2 * depth, pitch, 0.35, seed=cfg["seed"] + 30, cover="sheet", tails=True, ties=False, blocking=False)
        sheet = rf.corrugated_roof(Lr, 2 * depth, pitch, 0.35, seed=cfg["seed"] + 30, detail="low")
        for mb in (frame, sheet):
            ac.cull_pred(mb, lambda c: c.y > 0.0)
        M = T(-w / 2 - 0.045, (y0 + y1) / 2, zpost + 0.16) @ RZ(-90)          # separada de cinta y esquineros
    else:
        Lr, depth = (x1 - x0) + 0.4, dep
        frame = rf.roof_frame("gable", Lr, 2 * depth, pitch, 0.35, seed=cfg["seed"] + 30, cover="boards", tails=False, ties=False, blocking=False)
        sheet = rf.board_roof_stepped(Lr, 2 * depth, pitch, 0.35, seed=cfg["seed"] + 30)
        for mb in (frame, sheet):
            ac.cull_pred(mb, lambda c: c.y > 0.0)
        M = T((x0 + x1) / 2, yf - 0.045, zpost + 0.16)                        # separada de cinta, esquineros y sillares
    roof.join(frame, M)
    roof.join(sheet, M)
    return dict(posts=len(posts), stair_rect=stair_rect)


def build_veranda(cfg, shell, det, r, top, z_crown):
    """Veranda bajo el faldón delantero (CAB_2): duela 5/4x6 sobre vigas, postes 5x5 (0,12) con fendas y base de ángulo
    atornillada, barandal entre postes, escalera exterior a la arena y faja de tablas traslapadas bajo el faldón."""
    from kit import circulation as circ
    rw = rng(cfg["seed"] + 5151)
    w, d = cfg["w"], cfg["d"]
    yf = cfg["front_y"]
    z0 = cfg["z0"]
    y0 = -d / 2
    jx = []
    joists(shell, -w / 2 + 0.05, w / 2 - 0.05, y0 + 0.02, yf, z0 - 0.03, step=0.5, h=0.20, r=rw, xs_out=jx)
    xs = [-w / 2 + 0.08, -w / 6, w / 6, w / 2 - 0.08]
    boards_floor(shell, -w / 2, w / 2, y0, yf, z0, rw, missing=0.0, mat="wood_grey", nail_xs=jx)   # sin claros en el paso
    for x in xs:
        lumber(shell, (x, y0 + 0.08, z0 + 0.001), (x, y0 + 0.08, z_crown + 0.02), 0.12, 0.12, "wood_grey", up=(0, 1, 0), r=rw, rc=0.006,
               grain=1.0, check=1.0, step=0.4, bow=rw.uniform(-0.003, 0.003))
        for sg in (-1, 1):                                                     # ángulos de fijación al piso
            yy = y0 + 0.08 + sg * 0.06
            lbox(shell, (x - 0.035, min(yy, yy + sg * 0.005), z0), (x + 0.035, max(yy, yy + sg * 0.005), z0 + 0.09), "metal_rust",
                 r=rw, axis=2, rc=0.001, grain=0.0)
            bolt_head(shell, (x, yy + sg * 0.005, z0 + 0.055), (0, sg, 0), d=0.011, kind="carriage" if sg < 0 else "nut")
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
    # el muro delantero (retranqueado) sube hasta los cabios: faja de tablas traslapadas que cierra el triángulo bajo el faldón
    zt = top(0.0, yf) - 0.18
    if zt > 0.05:
        v = 0.0
        while v < zt - 0.02:
            hb = min(0.15, zt - v)
            lumber(shell, (-w / 2 + 0.002, yf + 0.011, z_crown + v + hb / 2), (w / 2 - 0.002, yf + 0.011, z_crown + v + hb / 2), hb + 0.03 if v + hb < zt else hb,
                   0.02, "wood_grey", up=(0, -1, 0), r=rw, rc=0.003, grain=1.0, check=0.4)
            for xx in [-w / 2 + 0.3 + 0.6 * k for k in range(int(w / 0.6))]:
                nail(shell, (xx, yf + 0.0005, z_crown + v + 0.03), (0, -1, 0), r=0.0045, h=0.0024)
            v += 0.15
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
        ac.downpipe_on(det, Vector(tpt) + Vector((0, 0, z_crown)), "front", yf - 0.04, seed=cfg["seed"] + 60)   # fuera de sillares y cinta
        n += 1
    return n


# vanos por muro y nivel: (tipo, u_centro, ancho, alto, antepecho) — u medida mirando el muro desde afuera
SPECS = {
    "CAB_1_tablones": {
        ("front", 0): [("win", 3.4, 0.8, 1.1, 0.9), ("door", 4.9, 0.95, 2.15, 0.0), ("win", 7.6, 0.6, 0.9, 1.0)],   # puerta libre de la partición
        ("front", 1): [("win", 1.6, 0.6, 0.9, 1.0), ("win", 3.4, 0.8, 1.1, 0.9), ("win", 7.0, 0.8, 1.1, 0.9)],
        ("back", 0): [("win", 2.0, 0.8, 1.1, 0.9), ("door", 4.0, 0.9, 2.15, 0.0)],                              # al este de la escalera
        ("back", 1): [("win", 2.5, 0.8, 1.1, 0.9), ("win", 6.5, 0.8, 1.1, 0.9)],
        ("west", 0): [("door", 2.9, 0.9, 2.15, 0.0), ("win", 4.5, 0.7, 1.0, 1.0)],
        ("west", 1): [("win", 2.9, 0.7, 1.0, 1.0)],
        ("east", 0): [("win", 2.9, 0.8, 1.1, 0.9)],
        ("east", 1): [("win", 2.9, 0.8, 1.1, 0.9)],
    },
    "CAB_2_pilotes": {
        ("front", 0): [("win", 1.2, 0.8, 1.1, 0.9), ("door", 2.6, 0.9, 2.12, 0.0), ("door", 4.4, 0.9, 2.12, 0.0), ("win", 5.8, 0.8, 1.1, 0.9)],
        ("back", 0): [("win", 1.8, 0.8, 1.1, 0.9), ("win", 2.95, 0.7, 1.0, 1.0), ("win", 5.4, 0.8, 1.1, 0.9)],  # sin puerta: atrás no hay escalera
        ("west", 0): [("win", 2.4, 0.8, 1.1, 0.9)],
        ("east", 0): [("win", 1.4, 0.8, 1.1, 0.9), ("win", 3.4, 0.8, 1.1, 0.9)],
    },
    "CAB_3_ladrillo": {
        ("front", 0): [("win", 1.2, 0.8, 1.3, 0.85), ("win", 3.8, 0.8, 1.3, 0.85), ("door", 5.9, 0.95, 2.15, 0.0), ("win", 7.2, 0.7, 1.2, 0.9)],
        ("front", 1): [("win", 1.0, 0.75, 1.2, 0.85), ("win", 2.8, 0.75, 1.2, 0.85), ("win", 5.2, 0.75, 1.2, 0.85), ("win", 7.0, 0.75, 1.2, 0.85)],
        ("back", 0): [("win", 1.6, 0.8, 1.2, 0.9), ("door", 4.0, 0.9, 2.15, 0.0), ("win", 6.4, 0.8, 0.6, 1.75)],   # alta: sobre la escalera
        ("back", 1): [("win", 2.0, 0.75, 1.2, 0.85), ("win", 6.0, 0.75, 1.2, 0.85)],
        ("west", 0): [("win", 3.2, 0.8, 1.2, 0.9)],
        ("west", 1): [("win", 2.0, 0.7, 1.1, 0.9), ("win", 4.4, 0.7, 1.1, 0.9)],
        ("east", 0): [("win", 2.0, 0.8, 1.2, 0.9)],
        ("east", 1): [("win", 3.2, 0.75, 1.2, 0.85)],
    },
}
