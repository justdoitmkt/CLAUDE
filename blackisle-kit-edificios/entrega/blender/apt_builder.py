"""apt_builder.py — constructor de edificios de departamentos BLACKISLE (estructura + interior completo).

Reglas del usuario (2026-10-09): entrada delantera (-Y) y trasera (+Y) en PB, CERO escaleras exteriores (núcleo interno),
interior completo (departamentos divididos en cuartos, corredores, escalera real).

Sistema: malla estructural de crujías; columnas continuas en toda la altura; vigas de borde con descuelgue bajo la losa;
losas con hueco de escalera; muros de relleno rehundidos 8 cm respecto a la cara de columna; divisiones interiores de 10 cm.
Las piezas del kit (ventanas, puertas, cortinas, escaleras, barandales, techo…) se acoplan en `dress_*`.
"""
import math
import os
import sys

import bpy  # noqa: F401  (debe importarse antes que mathutils)
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kit.common import MB, rng, wall_with_openings  # noqa: E402

COL = 0.35          # columna
COL_CORNER = 0.45   # columna de esquina
BEAM_W, BEAM_D = 0.25, 0.50
SLAB = 0.20
INFILL = 0.15       # muro de relleno (block + aplanado)
RECESS = 0.08       # rehundido del relleno respecto a la cara de columna
PART = 0.10         # división interior
GROUND = 0.15       # losa de desplante (z 0 → 0.15)


# ----------------------------------------------------------------------------------------------
# matrices de colocación
# ----------------------------------------------------------------------------------------------
def m_wall_x(x0, y_out, z0, inward=+1):
    """Muro a lo largo de +X empezando en x0. Cara exterior en y_out; el espesor crece hacia +Y si inward=+1 (fachada -Y),
    o hacia -Y si inward=-1 (fachada +Y, se recorre en -X para que la cara exterior mire afuera)."""
    if inward == +1:
        return Matrix(((1, 0, 0, x0), (0, 1, 0, y_out), (0, 0, 1, z0), (0, 0, 0, 1)))
    return Matrix(((-1, 0, 0, x0), (0, -1, 0, y_out), (0, 0, 1, z0), (0, 0, 0, 1)))


def m_wall_y(y0, x_out, z0, inward=+1):
    """Muro a lo largo de Y. inward=+1: cara exterior en x_out mirando a -X (fachada oeste), recorre +Y hacia… ver uso."""
    if inward == +1:   # fachada oeste: exterior hacia -X, espesor hacia +X, u recorre -Y→ para que la cara mire afuera usamos u = -Y
        return Matrix(((0, 1, 0, x_out), (-1, 0, 0, y0), (0, 0, 1, z0), (0, 0, 0, 1)))
    return Matrix(((0, -1, 0, x_out), (1, 0, 0, y0), (0, 0, 1, z0), (0, 0, 0, 1)))  # fachada este


def m_slab(x0, y0, z_top):
    """wall_with_openings como losa: u→X, v→Y, espesor hacia -Z. Cara 'exterior' = cara superior (piso)."""
    return Matrix(((1, 0, 0, x0), (0, 0, 1, y0), (0, -1, 0, z_top), (0, 0, 0, 1)))


# ----------------------------------------------------------------------------------------------
# configuración APT_A_5p
# ----------------------------------------------------------------------------------------------
def cfg_apt_a():
    xs = [-7.2, -3.6, 0.0, 3.6, 7.2]
    ys = [-5.4, -1.8, 1.8, 5.4]
    h = [3.4, 2.9, 2.9, 2.9, 2.9]           # PB + 4 pisos
    # núcleo interior: x 3.70 → cara interior de la fachada este (7.145); y ±1.475 (muros a ±1.55, t 0.15)
    stair = dict(x0=3.70, y0=-1.475, w=7.145 - 3.70, l=2.95, wall_y=1.55)
    # vanos de fachada por nivel y crujía (índice 0 = oeste/izquierda mirando la fachada)
    front = {0: ["window_high", "shutter", "lobby", "shutter"]}   # crujía oeste ciega con ventana alta: lienzo del grafiti
    front.update({k: ["window", "loggia", "loggia", "window"] for k in (1, 2, 3, 4)})
    back = {0: ["window_high", "door_service", "door_rear", "window_high"]}
    back.update({k: ["window_small", "window", "window", "window_small"] for k in (1, 2, 3, 4)})
    # 'back' se lista de oeste a este igual que 'front'
    west = {0: ["window_high", "solid", "window_high"]}
    west.update({k: ["window", "vent", "window"] for k in (1, 2, 3, 4)})
    east = {0: ["window_high", "vent", "window_high"]}       # PB cerrada por seguridad; la celosía arranca en el 1.er piso
    east.update({k: ["window", "breeze", "window"] for k in (1, 2, 3, 4)})
    return dict(id="APT_A_5p", xs=xs, ys=ys, h=h, stair=stair, front=front, back=back, west=west, east=east,
                loggia_depth=1.2, seed=11)


# ----------------------------------------------------------------------------------------------
# utilidades de nivel
# ----------------------------------------------------------------------------------------------
def level_z(cfg):
    """z de la cara superior de la losa de cada nivel (0 = PB) + la losa de azotea al final."""
    z = [GROUND]
    for hh in cfg["h"]:
        z.append(z[-1] + hh)
    return z


def col_size(i, j, cfg):
    corner = i in (0, len(cfg["xs"]) - 1) and j in (0, len(cfg["ys"]) - 1)
    return COL_CORNER if corner else COL


def bay_span(coords, k, sizes):
    """Tramo libre entre caras de columna para la crujía k."""
    return coords[k] + sizes[k] / 2, coords[k + 1] - sizes[k + 1] / 2


# ----------------------------------------------------------------------------------------------
# estructura
# ----------------------------------------------------------------------------------------------
def build_frame(cfg, mb):
    xs, ys = cfg["xs"], cfg["ys"]
    zl = level_z(cfg)
    r = rng(cfg["seed"])
    top = zl[-1]
    # columnas continuas desde el desplante hasta la losa de azotea (desplome leve aleatorio en la sección, no en el eje)
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            c = col_size(i, j, cfg) / 2
            mb.box((x - c, y - c, 0.0), (x + c, y + c, top - SLAB), "concrete", bevel=0.012, seg=2)
    # vigas en todas las líneas de la malla (descuelgue BEAM_D - SLAB bajo la losa)
    for k in range(1, len(zl)):
        zt = zl[k] - SLAB
        zb = zl[k] - BEAM_D
        for j, y in enumerate(ys):
            for i in range(len(xs) - 1):
                x0 = xs[i] + col_size(i, j, cfg) / 2
                x1 = xs[i + 1] - col_size(i + 1, j, cfg) / 2
                sag = float(r.uniform(0.0, 0.012))
                mb.box((x0, y - BEAM_W / 2, zb - sag), (x1, y + BEAM_W / 2, zt), "concrete", bevel=0.01, seg=1)
        for i, x in enumerate(xs):
            for j in range(len(ys) - 1):
                y0 = ys[j] + col_size(i, j, cfg) / 2
                y1 = ys[j + 1] - col_size(i, j + 1, cfg) / 2
                mb.box((x - BEAM_W / 2, y0, zb), (x + BEAM_W / 2, y1, zt), "concrete", bevel=0.01, seg=1)
    # losas: desplante + entrepisos + azotea; las de entrepiso llevan el hueco de escalera
    ex = BEAM_W / 2
    x0, x1 = xs[0] - ex, xs[-1] + ex
    y0, y1 = ys[0] - ex, ys[-1] + ex
    st = cfg["stair"]
    hole = (st["x0"] - x0, st["x0"] + st["w"] - x0, st["y0"] - y0, st["y0"] + st["l"] - y0)
    for k, zt in enumerate(zl):
        openings = [hole] if k > 0 else []                    # la escalera sigue hasta el casetón de azotea
        if k == 0:
            wall_with_openings(mb, x1 - x0, y1 - y0, GROUND, openings, mat_out="concrete", mat_in="concrete",
                               mat_reveal="concrete", m=m_slab(x0, y0, zt))
        else:
            wall_with_openings(mb, x1 - x0, y1 - y0, SLAB, openings, mat_out="concrete", mat_in="plaster",
                               mat_reveal="concrete", m=m_slab(x0, y0, zt))
    return mb


PENT_H = 2.7          # casetón de escalera sobre la losa de azotea


def build_penthouse(cfg, mb, details=None):
    """Casetón sobre el núcleo: prolonga las 4 columnas (3.6/7.2, ±1.8), vigas perimetrales, losa de techo con pretil,
    muros norte/sur ciegos, muro oeste con puerta metálica al ático y celosía al este (continúa la de la fachada)."""
    zl = level_z(cfg)
    z0, z1 = zl[-1], zl[-1] + PENT_H
    cx, cy = (3.6, 7.2), (-1.8, 1.8)
    for x in cx:
        for y in cy:
            c = COL / 2
            mb.box((x - c, y - c, z0 - SLAB), (x + c, y + c, z1 - SLAB), "concrete", bevel=0.012, seg=2)
    for y in cy:
        mb.box((cx[0] + COL / 2, y - BEAM_W / 2, z1 - 0.40), (cx[1] - COL / 2, y + BEAM_W / 2, z1 - SLAB), "concrete", bevel=0.01, seg=1)
    for x in cx:
        mb.box((x - BEAM_W / 2, cy[0] + COL / 2, z1 - 0.40), (x + BEAM_W / 2, cy[1] - COL / 2, z1 - SLAB), "concrete", bevel=0.01, seg=1)
    # losa de techo del casetón + pretil bajo
    x0, x1, y0, y1 = cx[0] - COL / 2 - 0.05, cx[1] + COL / 2 + 0.05, cy[0] - COL / 2 - 0.05, cy[1] + COL / 2 + 0.05
    mb.box((x0, y0, z1 - SLAB), (x1, y1, z1), "concrete", bevel=0.015, seg=2)
    for (a, b) in (((x0, y0), (x1, y0 + 0.12)), ((x0, y1 - 0.12), (x1, y1)), ((x0, y0 + 0.12), (x0 + 0.12, y1 - 0.12)), ((x1 - 0.12, y0 + 0.12), (x1, y1 - 0.12))):
        mb.box((a[0], a[1], z1), (b[0], b[1], z1 + 0.35), "concrete", bevel=0.01, seg=1)
    H = PENT_H - 0.40
    # muros norte y sur (ciegos)
    for sg, y in ((-1, cy[0]), (1, cy[1])):
        face = y + sg * (COL / 2 - RECESS)
        m = m_wall_x(cx[0] + COL / 2, face, z0, +1) if sg < 0 else m_wall_x(cx[1] - COL / 2, face, z0, -1)
        wall_with_openings(mb, (cx[1] - cx[0]) - COL, H, INFILL, [], mat_out="plaster", mat_in="plaster", mat_reveal="concrete", m=m)
    # muro oeste con puerta al ático (se viste en dress)
    L = (cy[1] - cy[0]) - COL
    mw = m_wall_y(cy[1] - COL / 2, cx[0] - (COL / 2 - RECESS), z0, +1)
    door = (round((L - 0.9) / 2, 4), round((L + 0.9) / 2, 4), 0.0, 2.05)
    wall_with_openings(mb, L, H, INFILL, [door], mat_out="plaster", mat_in="plaster", mat_reveal="concrete", m=mw)
    # muro este: jambas + vano de celosía (como la fachada)
    me = m_wall_y(cy[0] + COL / 2, cx[1] + (COL / 2 - RECESS), z0, -1)
    vents = [(round(L / 2 - 0.9, 4), round(L / 2 - 0.3, 4), 1.5, 2.0), (round(L / 2 + 0.3, 4), round(L / 2 + 0.9, 4), 1.5, 2.0)]
    wall_with_openings(mb, L, H, INFILL, vents, mat_out="plaster", mat_in="plaster", mat_reveal="concrete", m=me)
    return dict(door=(mw, door), vents=(me, vents), top_z=z1, rect=(x0, y0, x1, y1))


# ----------------------------------------------------------------------------------------------
# fachadas (muros de relleno con vanos)
# ----------------------------------------------------------------------------------------------
OPENING = {
    # tipo: (ancho, alto, antepecho) — None = muro ciego o tratamiento especial
    "window": (1.6, 1.3, 0.9), "window_small": (1.2, 1.0, 1.1), "window_high": (1.8, 0.8, 1.9),
    "vent": (0.6, 0.6, 1.6), "door_rear": (1.2, 2.3, 0.0), "door_service": (0.9, 2.1, 0.0),
    "shutter": (2.8, 2.8, 0.0), "lobby": (2.2, 2.4, 0.0), "loggia": (2.4, 2.1, 0.0),
}


def facade_panels(cfg, side):
    """Genera la lista de paneles de relleno de una fachada: dict(level, bay, kind, m, length, height, openings, recess)."""
    xs, ys = cfg["xs"], cfg["ys"]
    zl = level_z(cfg)
    panels = []
    if side in ("front", "back"):
        coords = xs
        j = 0 if side == "front" else len(ys) - 1
        sizes = [col_size(i, j, cfg) for i in range(len(xs))]
        face = ys[j] + (-1 if side == "front" else 1) * (COL / 2 - RECESS)
    else:
        coords = ys
        i = 0 if side == "west" else len(xs) - 1
        sizes = [col_size(i, jj, cfg) for jj in range(len(ys))]
        face = xs[i] + (-1 if side == "west" else 1) * (COL / 2 - RECESS)
    for lv, kinds in cfg[side].items():
        z0 = zl[lv]
        hclear = cfg["h"][lv] - BEAM_D if lv > 0 else cfg["h"][lv] - BEAM_D + (0.0)
        for b, kind in enumerate(kinds):
            a0, a1 = bay_span(coords, b, sizes)
            L = a1 - a0
            recess = cfg["loggia_depth"] if kind in ("loggia", "lobby") else 0.0
            panels.append(dict(level=lv, bay=b, kind=kind, a0=a0, a1=a1, L=L, z0=z0, H=hclear, face=face, recess=recess))
    return panels


def build_facade(cfg, mb, side):
    """Muros de relleno + retornos de loggia/vestíbulo. Devuelve los paneles con la posición de cada vano para vestirlos después."""
    placed = []
    for p in facade_panels(cfg, side):
        kind = p["kind"]
        L, H = p["L"], p["H"]
        op = OPENING.get(kind)
        openings = []
        if kind == "breeze":  # cierre del núcleo: celosía de 2,4 m centrada entre jambas de concreto, de losa a viga
            w = min(2.4, L - 0.3)
            u0 = (L - w) / 2
            openings = [(round(u0, 4), round(u0 + w, 4), 0.0, round(H, 4))]
        elif op is not None:
            w, h, sill = op
            w = min(w, L - 0.3)
            h = min(h, H - sill - 0.1) if sill > 0 else min(h, H - 0.05)
            u0 = (L - w) / 2
            openings = [(round(u0, 4), round(u0 + w, 4), round(sill, 4), round(sill + h, 4))]
        d = p["recess"]
        if side == "front":
            m = m_wall_x(p["a0"], p["face"] + d, p["z0"], +1)
        elif side == "back":
            m = m_wall_x(p["a1"], p["face"] - d, p["z0"], -1)
        elif side == "west":
            m = m_wall_y(p["a1"], p["face"] + d, p["z0"], +1)
        else:
            m = m_wall_y(p["a0"], p["face"] - d, p["z0"], -1)
        wall_with_openings(mb, L, H, INFILL, openings, mat_out="plaster", mat_in="plaster", mat_reveal="concrete", m=m)
        if d > 0:  # retornos laterales de loggia / vestíbulo rehundido
            for a in (p["a0"], p["a1"] - INFILL):
                if side == "front":
                    mb.box((a, p["face"], p["z0"]), (a + INFILL, p["face"] + d, p["z0"] + H), "plaster", bevel=0.005, seg=1)
                elif side == "back":
                    mb.box((a, p["face"] - d, p["z0"]), (a + INFILL, p["face"], p["z0"] + H), "plaster", bevel=0.005, seg=1)
        placed.append(dict(p, opening=openings[0] if openings else None, m=m))
    return placed


# ----------------------------------------------------------------------------------------------
# interior: núcleo de escalera, corredor, departamentos
# ----------------------------------------------------------------------------------------------
def partition(mb, p0, p1, z0, H, doors=(), t=PART, mat="plaster", door_h=2.05, out=None, tag="room"):
    """División interior recta entre p0 y p1 (eje X o Y), centrada en la línea.
    doors = [(coordenada_centro_absoluta, ancho)] sobre el eje del muro (x si corre en X, y si corre en Y)."""
    (xa, ya), (xb, yb) = p0, p1
    along_x = abs(yb - ya) < 1e-6
    a0 = min(xa, xb) if along_x else min(ya, yb)
    L = abs(xb - xa) + abs(yb - ya)
    ops = []
    for c, w in doors:
        u0, u1 = max(c - w / 2 - a0, 0.05), min(c + w / 2 - a0, L - 0.05)
        if u1 - u0 > 0.3:
            ops.append((round(u0, 4), round(u1, 4), 0.0, min(door_h, H - 0.05)))
    if along_x:
        m = Matrix(((1, 0, 0, a0), (0, 1, 0, ya - t / 2), (0, 0, 1, z0), (0, 0, 0, 1)))
    else:
        m = Matrix(((0, -1, 0, xa + t / 2), (1, 0, 0, a0), (0, 0, 1, z0), (0, 0, 0, 1)))
    wall_with_openings(mb, L, H, t, ops, mat_out=mat, mat_in=mat, mat_reveal=mat, m=m)
    if out is not None:
        for (u0, u1, v0, v1) in ops:
            out.append(dict(m=m, u0=u0, w=u1 - u0, h=v1, t=t, tag=tag))


def inner_faces(cfg):
    xs, ys = cfg["xs"], cfg["ys"]
    k = COL / 2 - RECESS + INFILL     # de la línea de malla a la cara interior del relleno
    return xs[0] - (COL / 2 - RECESS) + INFILL, xs[-1] + (COL / 2 - RECESS) - INFILL, \
        ys[0] - (COL / 2 - RECESS) + INFILL, ys[-1] + (COL / 2 - RECESS) - INFILL


def build_interior_apt_a(cfg, mb, out=None):
    """Plantas de APT_A (todas las escaleras dentro).
    PB: vestíbulo pasante x 0.3..3.3 entre la entrada delantera (vestíbulo rehundido) y la trasera; el descanso de PB se abre al núcleo
        (x 3.70→fachada este, y ±1.475); local oeste (2 crujías) + bodega con WC atrás; local este al frente + cuarto atrás.
    Pisos 1–4: corredor y ±0.75 desde la fachada oeste hasta x 2.4; vestíbulo de escalera x 2.4..3.70, y ±1.55;
        4 departamentos: A1/A3 al oeste (estancia con loggia, recámara, cocina, baño), A2/A4 al este (estancia con loggia, recámara
        en la esquina, cocina-acceso y baño)."""
    zl = level_z(cfg)
    st = cfg["stair"]
    xin0, xin1, yin0, yin1 = inner_faces(cfg)
    wy = st["wall_y"]
    d_lobby = cfg["loggia_depth"]
    y_lobby_in = cfg["ys"][0] - (COL / 2 - RECESS) + d_lobby + INFILL   # cara interior del muro del vestíbulo rehundido
    for lv in range(len(cfg["h"])):
        z0 = zl[lv]
        H = cfg["h"][lv] - SLAB
        # muros norte y sur del núcleo (el lado oeste queda abierto al descanso; el este es la celosía)
        for sg in (-1, 1):
            partition(mb, (3.625, sg * wy), (xin1, sg * wy), z0, H, t=0.15)
        if lv == 0:
            partition(mb, (0.25, y_lobby_in), (0.25, yin1), z0, H, doors=[(-3.0, 0.9), (3.0, 0.9)], out=out)
            partition(mb, (3.35, y_lobby_in), (3.35, -wy), z0, H, doors=[(-3.0, 0.9)], out=out)
            partition(mb, (3.35, wy), (3.35, yin1), z0, H, doors=[(3.2, 0.9)], out=out)
            partition(mb, (xin0, 0.6), (0.2, 0.6), z0, H, doors=[(-3.6, 1.4)], out=out)          # local oeste | bodega
            partition(mb, (xin0, 3.0), (-5.0, 3.0), z0, H, doors=[(-6.0, 0.8)], out=out)          # WC de la bodega
            partition(mb, (-5.0, 3.0), (-5.0, yin1), z0, H)
            continue
        cw, xh = 0.75, 2.4
        for sg in (-1, 1):
            yc, yo = sg * cw, (yin0 if sg < 0 else yin1)
            # corredor (muro hacia los deptos) con puertas de acceso a A1/A3 (x -1.0) y A2/A4 (x 1.8)
            partition(mb, (xin0, yc), (xh, yc), z0, H, doors=[(-1.0, 0.9), (1.8, 0.9)], out=out, tag="entry")
            partition(mb, (xh, yc), (xh, sg * wy), z0, H)                                   # quiebre corredor → vestíbulo
            partition(mb, (xh, sg * wy), (3.625, sg * wy), z0, H, t=0.15)                  # vestíbulo de escalera
            partition(mb, (0.0, yo), (0.0, yc), z0, H)                                       # medianera A1|A2
            # A1/A3: estancia x -3.6..0 · recámara x xin0..-3.6 (lado fachada) · cocina x -5.4..-3.6 y baño x xin0..-5.4 (lado corredor)
            partition(mb, (-3.6, yo), (-3.6, yc), z0, H, doors=[(sg * 3.8, 0.8), (sg * 1.6, 0.8)], out=out)
            partition(mb, (xin0, sg * 2.4), (-3.6, sg * 2.4), z0, H)
            partition(mb, (-5.4, sg * 2.4), (-5.4, yc), z0, H, doors=[(sg * 1.6, 0.7)], out=out)
            # A2/A4: estancia x 0..3.6 · recámara de esquina x 3.6..xin1 · cocina-acceso x 1.2..2.4 y baño x 0..1.2 (lado corredor)
            partition(mb, (3.6, yo), (3.6, sg * wy), z0, H, doors=[(sg * 3.0, 0.8)], out=out)
            partition(mb, (0.0, sg * 2.6), (2.4, sg * 2.6), z0, H, doors=[(1.8, 1.2)], out=out)
            partition(mb, (1.2, sg * 2.6), (1.2, yc), z0, H, doors=[(sg * 1.7, 0.7)], out=out)
    return mb


# ----------------------------------------------------------------------------------------------
# vestido con el kit (G1 vanos + G2 circulación)
# ----------------------------------------------------------------------------------------------
def _T(x, y, z):
    return Matrix.Translation((x, y, z))


ROT_Z90 = Matrix(((0, -1, 0, 0), (1, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))


def dress_openings(cfg, placed, details, interior):
    """Ventanas, puertas, cortinas metálicas, celosía, rejas y barandales de loggia sobre los paneles de fachada."""
    from kit import circulation as circ
    from kit import openings as op
    r = rng(cfg["seed"] + 101)
    n = 0
    for side, panels in placed.items():
        primary = side == "front"
        for p in panels:
            o = p.get("opening")
            if o is None:
                continue
            u0, u1, v0, v1 = o
            w, h = u1 - u0, v1 - v0
            M = p["m"] @ _T(u0, 0, v0)
            seed = int(r.integers(0, 10**6))
            kind = p["kind"]
            if kind in ("window", "window_small"):
                roll = r.random()
                if roll < 0.18:
                    k = "boarded"
                elif kind == "window_small" and roll < 0.45:
                    k = "casement"
                else:
                    k = "sliding"
                curtain = primary or r.random() < 0.4
                details.join(op.window(k, w, h, INFILL, seed=seed, broken=float(r.uniform(0.55, 1.0)), curtain=curtain), M)
            elif kind == "vent":
                details.join(op.window("casement", w, h, INFILL, seed=seed, broken=1.0, curtain=False), M)
            elif kind == "window_high":
                details.join(op.window("sliding", w, h, INFILL, seed=seed, broken=float(r.uniform(0.6, 1.0)), curtain=False), M)
                if r.random() < 0.6:
                    details.join(op.security_grille(w, h, seed=seed + 1), M)
            elif kind == "loggia":
                details.join(op.window("sliding", w, h, INFILL, seed=seed, broken=float(r.uniform(0.5, 1.0)), curtain=True,
                                       sill=False), M)
            elif kind == "lobby":
                details.join(op.door("double_glazed", w, h, INFILL, seed=seed, open_angle=float(r.uniform(15, 70))), M)
            elif kind in ("door_rear", "door_service"):
                details.join(op.door("metal", w, h, INFILL, seed=seed, open_angle=float(r.uniform(0, 80))), M)
            elif kind == "shutter":
                details.join(op.rolling_shutter(w, h, seed=seed, dent=float(r.uniform(0.4, 0.9)),
                                                open_frac=float(r.choice([0.0, 0.0, 0.35]))), M)
            elif kind == "breeze":
                details.join(op.breeze_block_screen(w, h, seed=seed, pattern="cross", bevel=0.0, y0=0.025,
                                                    missing=float(r.uniform(0.04, 0.12))), M)
            n += 1
            # barandal de loggia sobre el canto de la losa
            if kind == "loggia" and side == "front":
                y_axis = cfg["ys"][0] - BEAM_W / 2 + 0.07
                details.join(circ.railing("tube_metal", p["L"], h=1.0, seed=seed + 7, bend=float(r.choice([0.0, 0.0, 0.12])),
                                          missing=float(r.uniform(0.05, 0.2))), _T(p["a0"], y_axis, p["z0"]))
    return n


def dress_interior_doors(cfg, doors, interior):
    from kit import openings as op
    r = rng(cfg["seed"] + 202)
    n = 0
    for d in doors:
        keep = 0.55 if d["tag"] == "entry" else 0.12         # saqueo: casi todas las hojas interiores arrancadas (queda el vano)
        if r.random() > keep:
            continue
        M = d["m"] @ _T(d["u0"], 0, 0)
        interior.join(op.door("flush", d["w"], d["h"], d["t"], seed=int(r.integers(0, 10**6)), open_angle=float(r.uniform(0, 95))), M)
        n += 1
    return n


def dress_stairs(cfg, interior):
    """Escalera en U por entrepiso, de PB hasta el casetón de azotea (PB con huella 0,25 para compartir el núcleo de 3,443 m)."""
    from kit import circulation as circ
    st = cfg["stair"]
    zl = level_z(cfg)
    for lv in range(len(cfg["h"])):
        fh = cfg["h"][lv]
        kw = dict(width=1.4, floor_h=fh, landing_depth=1.2, gap=0.15, seed=cfg["seed"] * 10 + lv, broken=0.05,
                  rail="tube_metal", debris=(lv in (0, len(cfg["h"]) - 1)))
        if fh > 3.0:
            kw.update(going=0.25, landing_depth=1.19)
        fp = circ.stair_u_footprint(**{k: kw[k] for k in ("width", "floor_h", "landing_depth", "gap")}, going=kw.get("going", 0.28))
        assert fp["L"] <= st["w"] + 0.003 and fp["W"] <= st["l"] + 0.003, fp
        interior.join(circ.stair_u(**kw), _T(st["x0"], st["y0"], zl[lv]))


def dress_penthouse(cfg, pent, details):
    from kit import openings as op
    mw, d = pent["door"]
    details.join(op.door("metal", d[1] - d[0], d[3] - d[2], INFILL, seed=cfg["seed"] + 77, open_angle=35), mw @ _T(d[0], 0, d[2]))
    me, vents = pent["vents"]
    for i, v in enumerate(vents):
        details.join(op.window("casement", v[1] - v[0], v[3] - v[2], INFILL, seed=cfg["seed"] + 79 + i, broken=1.0, curtain=False),
                     me @ _T(v[0], 0, v[2]))


# ----------------------------------------------------------------------------------------------
# base y entorno inmediato: arena acumulada + hierba seca
# ----------------------------------------------------------------------------------------------
def build_skirt(cfg, mb, margin=3.0, cell=0.25, keep_clear=()):
    """Terreno de arena alrededor de la planta: deriva contra los muros (hasta ~0,32 m sobre el desplante, tapando el zócalo),
    ondulación de dunas y borde que muere en z=0. Hierba seca en matas de hojas finas (láminas 'vegetation', DoubleSide),
    más densas junto a los muros y en esquinas. keep_clear: rectángulos (x0, y0, x1, y1) libres de hierba (accesos)."""
    import numpy as np
    r = rng(cfg["seed"] + 303)
    xs, ys = cfg["xs"], cfg["ys"]
    fx0, fx1 = xs[0] - COL_CORNER / 2, xs[-1] + COL_CORNER / 2
    fy0, fy1 = ys[0] - COL_CORNER / 2, ys[-1] + COL_CORNER / 2
    X0, X1, Y0, Y1 = fx0 - margin, fx1 + margin, fy0 - margin, fy1 + margin
    nx, ny = int((X1 - X0) / cell) + 1, int((Y1 - Y0) / cell) + 1
    gx = np.linspace(X0, X1, nx)
    gy = np.linspace(Y0, Y1, ny)
    GX, GY = np.meshgrid(gx, gy, indexing="ij")
    dx = np.maximum(np.maximum(fx0 - GX, GX - fx1), 0)
    dy = np.maximum(np.maximum(fy0 - GY, GY - fy1), 0)
    d = np.hypot(dx, dy)                                   # distancia a la planta (0 dentro)
    inside = (GX > fx0) & (GX < fx1) & (GY > fy0) & (GY < fy1)
    ph = r.uniform(0, 6.28, 4)
    dune = (0.06 * np.sin(GX * 0.9 + ph[0]) * np.cos(GY * 0.7 + ph[1]) + 0.04 * np.sin(GX * 2.3 + GY * 1.7 + ph[2])
            + 0.025 * np.sin(GX * 5.1 - GY * 4.3 + ph[3]))
    drift = 0.32 * np.exp(-d / 0.9) * (0.7 + 0.3 * np.sin(GX * 1.3 + GY * 0.8 + ph[0]))
    edge = np.clip((margin - d) / 1.2, 0, 1)               # muere en z=0 en el borde del parche
    Z = np.where(inside, -0.05, (drift + dune + 0.03) * edge)
    # malla en rejilla; se omiten las celdas totalmente dentro de la planta (bajo el edificio)
    vid = {}
    def V(i, j):
        if (i, j) not in vid:
            vid[(i, j)] = mb.bm.verts.new((float(GX[i, j]), float(GY[i, j]), float(Z[i, j])))
        return vid[(i, j)]
    for i in range(nx - 1):
        for j in range(ny - 1):
            if inside[i, j] and inside[i + 1, j] and inside[i, j + 1] and inside[i + 1, j + 1]:
                continue
            mb.face([V(i, j), V(i + 1, j), V(i + 1, j + 1), V(i, j + 1)], "sand")
    # hierba seca
    def zat(x, y):
        i = int(round((x - X0) / cell)); j = int(round((y - Y0) / cell))
        return float(Z[min(max(i, 0), nx - 1), min(max(j, 0), ny - 1)])
    n_tufts = 0
    for _ in range(4000):
        x, y = float(r.uniform(X0 + 0.3, X1 - 0.3)), float(r.uniform(Y0 + 0.3, Y1 - 0.3))
        ddx = max(fx0 - x, x - fx1, 0); ddy = max(fy0 - y, y - fy1, 0)
        dd = math.hypot(ddx, ddy)
        if dd <= 0.05 or any(k[0] <= x <= k[2] and k[1] <= y <= k[3] for k in keep_clear):
            continue
        if r.random() > 0.85 * math.exp(-dd / 1.1) + 0.06:
            continue
        z0 = zat(x, y) - 0.02
        for _b in range(int(r.integers(7, 15))):
            a = float(r.uniform(0, 6.283)); lean = float(r.uniform(0.15, 0.6)); h = float(r.uniform(0.18, 0.55))
            w = float(r.uniform(0.006, 0.012))
            px, py = x + float(r.normal(0, 0.04)), y + float(r.normal(0, 0.04))
            ca, sa = math.cos(a), math.sin(a)
            side = (-sa * w, ca * w)
            mid = (px + ca * lean * h * 0.35, py + sa * lean * h * 0.35, z0 + h * 0.55)
            tip = (px + ca * lean * h, py + sa * lean * h, z0 + h * (0.9 - 0.25 * lean))
            v = [mb.bm.verts.new(p) for p in ((px - side[0], py - side[1], z0), (px + side[0], py + side[1], z0),
                                               (mid[0] + side[0] * 0.6, mid[1] + side[1] * 0.6, mid[2]),
                                               (mid[0] - side[0] * 0.6, mid[1] - side[1] * 0.6, mid[2]), tip)]
            mb.face([v[0], v[1], v[2], v[3]], "vegetation")
            mb.face([v[3], v[2], v[4]], "vegetation")
        n_tufts += 1
        if n_tufts >= 320:
            break
    return n_tufts


# ----------------------------------------------------------------------------------------------
# techo (G3), servicios y daño (G4)
# ----------------------------------------------------------------------------------------------
ROOF_PITCH, ROOF_OVH = 26.0, 0.6


def _rot_z(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Z")


def cull_faces(mb, boxes):
    """Quita las caras cuyo centro cae dentro de alguna caja (x0, y0, z0, x1, y1, z1). Para mallas soldadas (teja)."""
    import bmesh
    kill = [f for f in mb.bm.faces if any(b[0] <= c.x <= b[3] and b[1] <= c.y <= b[4] and b[2] <= c.z <= b[5]
                                          for c in (f.calc_center_median(),) for b in boxes)]
    bmesh.ops.delete(mb.bm, geom=kill, context="FACES")
    return len(kill)


def cull_components(mb, boxes, mode="center"):
    """Quita de un MB las piezas sueltas (componentes conexas) cuyo centro ('center') o caja ('touch') cae dentro de alguna caja
    (x0, y0, z0, x1, y1, z1). Sirve para vaciar el volumen del casetón dentro del techo sin booleanos."""
    import bmesh
    bm = mb.bm
    bm.faces.ensure_lookup_table()
    seen = set()
    kill = []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, comp = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop()
            comp.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index)
                        stack.append(h)
        vs = {v for g in comp for v in g.verts}
        mn = Vector((min(v.co.x for v in vs), min(v.co.y for v in vs), min(v.co.z for v in vs)))
        mx = Vector((max(v.co.x for v in vs), max(v.co.y for v in vs), max(v.co.z for v in vs)))
        c = (mn + mx) / 2
        for b in boxes:
            if mode == "center":
                hit = b[0] <= c.x <= b[3] and b[1] <= c.y <= b[4] and b[2] <= c.z <= b[5]
            else:
                hit = not (mx.x < b[0] or mn.x > b[3] or mx.y < b[1] or mn.y > b[4] or mx.z < b[2] or mn.z > b[5])
            if hit:
                kill.extend(comp)
                break
    bmesh.ops.delete(bm, geom=list(set(kill)), context="FACES")
    return len(kill)


def dress_roof(cfg, pent, roof, details, detail="low"):
    from kit import circulation as circ
    from kit import roofing as rf
    xs, ys = cfg["xs"], cfg["ys"]
    W = xs[-1] - xs[0] + COL_CORNER
    D = ys[-1] - ys[0] + COL_CORNER
    z0 = level_z(cfg)[-1]
    seed = cfg["seed"] + 404
    spot = rf.damage_spot("hip", W, D, ROOF_PITCH, ROOF_OVH, seed=seed, damage=0.55)
    frame = rf.roof_frame("hip", W, D, ROOF_PITCH, ROOF_OVH, seed=seed, cover="tile", damage=0.55, spot=spot)
    tiles = rf.barrel_tiles(W, D, "hip", ROOF_PITCH, ROOF_OVH, seed=seed, missing=0.04, hole=spot, detail=detail)
    x0, y0, x1, y1 = pent["rect"]
    vol = (x0 + 0.02, y0 + 0.02, -1.0, x1 - 0.02, y1 - 0.02, PENT_H + 0.5)      # en coordenadas del techo (z relativo)
    k_frame = cull_components(frame, [vol], mode="touch")
    k_tiles = cull_faces(tiles, [vol])
    roof.join(frame, _T(0, 0, z0))
    roof.join(tiles, _T(0, 0, z0))
    # canalón perimetral (recorrido antihorario: fascia a la izquierda) + 4 bajantes junto a las columnas de esquina
    ex, ey = W / 2 + ROOF_OVH, D / 2 + ROOF_OVH
    ze = rf.roof_top("hip", W, D, ROOF_PITCH, ROOF_OVH, x=ex - 0.01, y=0.0)
    off = 0.0865
    gx, gy = ex + off, ey + off
    path = [(-gx, -gy, ze - 0.06), (gx, -gy, ze - 0.06), (gx, gy, ze - 0.06), (-gx, gy, ze - 0.06), (-gx, -gy + 0.001, ze - 0.06)]
    Lf, Le = 2 * gx, 2 * gy
    xo = 6.6
    outlets = [gx - xo, Lf - (gx - xo), Lf + Le + (gx - xo), 2 * Lf + Le - (gx - xo)]
    g = circ.gutter([Vector(p) for p in path], seed=seed + 1, outlets=outlets)
    roof.join(g, _T(0, 0, z0))
    tops = [Vector(t) + Vector((0, 0, z0)) for t in g.meta["outlets"]] if hasattr(g, "meta") and "outlets" in g.meta else []
    yf = ys[0] - (COL / 2 - RECESS)          # cara del relleno de fachada
    for i, t in enumerate(tops):
        front = t.y < 0
        if front:
            dp = circ.downpipe(t, Vector((t.x, yf - 0.06, 0.05)), wall_offset=0.06, seed=seed + 10 + i)
            details.join(dp)
        else:
            R = _rot_z(180)
            tl = R.inverted() @ t
            dp = circ.downpipe(tl, Vector((tl.x, yf - 0.06, 0.05)), wall_offset=0.06, seed=seed + 10 + i)
            details.join(dp, R)
    return dict(spot=spot, culled_frame=k_frame, culled_tiles=k_tiles, downpipes=len(tops))
def _panel(placed, side, level, bay):
    for p in placed[side]:
        if p["level"] == level and p["bay"] == bay:
            return p
    raise KeyError((side, level, bay))


def dress_services(cfg, placed, pent, details, interior, detail_far="low", detail_near="mid"):
    """Elementos secundarios con lógica constructiva (>= 30 distintos en el modelo completo)."""
    from kit import services as sv
    r = rng(cfg["seed"] + 505)
    zl = level_z(cfg)
    n = {}
    def add(key, mb, M, target=details):
        target.join(mb, M)
        n[key] = n.get(key, 0) + 1
    # A/C: condensadoras bajo ventanas (trasera y oeste: lejanas; frente: una cercana) y equipos viejos en PB
    for side, lv, bay, kind, det in (("back", 1, 1, "split_outdoor", detail_far), ("back", 2, 2, "split_outdoor", detail_far),
                                      ("back", 3, 1, "split_outdoor", detail_far), ("back", 4, 2, "box_old", detail_far),
                                      ("west", 2, 0, "split_outdoor", detail_far), ("west", 3, 2, "box_old", detail_far),
                                      ("front", 2, 0, "split_outdoor", detail_near)):
        p = _panel(placed, side, lv, bay)
        o = p["opening"]
        add("ac_" + kind, sv.ac_unit(kind, seed=int(r.integers(1e6)), detail=det), p["m"] @ _T((o[0] + o[1]) / 2, 0, 0.32))
    # acometida aérea por la banda de viga de PB (frente) + medidores y conduit junto al vestíbulo
    yb = cfg["ys"][0] - BEAM_W / 2 - 0.005
    zc = zl[1] - 0.30
    add("cable_bundle", sv.cable_bundle([(-7.0, yb, zc), (-3.6, yb, zc + 0.04), (-0.1, yb, zc)], n=4, sag=0.22, seed=int(r.integers(1e6)),
                                        detail=detail_near), Matrix())
    p = _panel(placed, "front", 0, 0)
    for i, u in enumerate((p["L"] - 0.55, p["L"] - 0.12)):
        add("meter_box", sv.meter_box(seed=int(r.integers(1e6)), open_door=bool(i), detail=detail_near), p["m"] @ _T(u - 0.2, 0, 1.25))
    add("conduit", sv.conduit([(p["L"] - 0.75, 0, 1.78), (p["L"] - 0.75, 0, p["H"] - 0.05)], seed=int(r.integers(1e6)),
                              detail=detail_near), p["m"])
    # letreros arrancados sobre los locales
    for bay in (1, 3):
        p = _panel(placed, "front", 0, bay)
        add("sign_torn", sv.sign_torn(w=min(2.6, p["L"] - 0.3), h=0.42, seed=int(r.integers(1e6)), detail=detail_near),
            p["m"] @ _T(p["L"] / 2, -0.03, p["H"] + 0.04))
    # arbotantes rotos en columnas del frente y puerta trasera
    for x in (-3.6, 3.6):
        add("light_fixture", sv.light_fixture("bracket", seed=int(r.integers(1e6)), detail=detail_near),
            _T(x, cfg["ys"][0] - COL / 2, zl[1] - 0.75))
    p = _panel(placed, "back", 0, 2)
    o = p["opening"]
    add("light_fixture", sv.light_fixture("wall", seed=int(r.integers(1e6)), detail=detail_near), p["m"] @ _T((o[0] + o[1]) / 2, 0, o[3] + 0.35))
    # buzones en el vestíbulo (muro x = 0,25, cara este) y extintores vacíos en los vestíbulos de escalera
    add("mailboxes", sv.mailboxes(n=12, seed=int(r.integers(1e6)), detail=detail_near), _T(0.30 + 0.001, -1.2, zl[0] + 1.05) @ _rot_z(90), interior)
    for lv in (1, 3):
        add("extinguisher_cabinet", sv.extinguisher_cabinet(seed=int(r.integers(1e6)), detail=detail_near),
            _T(3.05, -cfg["stair"]["wall_y"] + 0.075 + 0.001, zl[lv] + 1.05) @ _rot_z(180), interior)
    # tendederos en 4 loggias
    for (lv, bay) in ((1, 1), (2, 2), (3, 1), (4, 2)):
        p = _panel(placed, "front", lv, bay)
        add("laundry_line", sv.laundry_line(length=p["L"] - 2 * INFILL - 0.02, seed=int(r.integers(1e6)), detail=detail_near),
            _T(p["a0"] + INFILL + 0.01, p["face"] + 0.55, p["z0"] + 1.95))
    # azotea del casetón: 2 tinacos, antena; parabólica en el muro sur del casetón
    zt = pent["top_z"]
    for x in (4.45, 6.25):
        add("water_tank", sv.water_tank(seed=int(r.integers(1e6)), detail=detail_far), _T(x, 0.25, zt))
    add("tv_antenna", sv.tv_antenna(seed=int(r.integers(1e6)), detail=detail_far), _T(5.35, -1.45, zt))
    add("satellite_dish", sv.satellite_dish(seed=int(r.integers(1e6)), detail=detail_far), _T(4.7, -1.8 - (COL / 2 - RECESS), zl[-1] + 1.7))
    return n


def dress_damage(cfg, shell, details, interior, skirt, detail="low"):
    """Daño concentrado en la fachada oeste (la 'muy dañada') + varillas de espera + escombro y trozos."""
    from kit import damage as dm
    r = rng(cfg["seed"] + 606)
    zl = level_z(cfg)
    n = {}
    def add(key, mb, M, target):
        target.join(mb, M)
        n[key] = n.get(key, 0) + 1
    # columnas de la fachada oeste con esquinas mordidas (piezas adicionales: se colocan como envolvente de la columna original,
    # 1 mm por fuera, para no tocar la estructura base)
    x = cfg["xs"][0]
    for j, y in enumerate(cfg["ys"][1:3], start=1):
        c = COL / 2 + 0.002
        z0 = zl[int(r.integers(1, 4))] + 0.3
        mbx = MB()
        dm.spalled_box(mbx, (x - c, y - c, z0), (x + c, y + c, z0 + 1.6),
                       [dict(axis="z", sides=(-1, int(r.choice([-1, 1]))), start=0.25, length=1.0, depth=0.09, seed=int(r.integers(1e6)))],
                       detail=detail)
        add("spalled_column", mbx, Matrix(), shell)
    # varillas de espera: castillos en las 4 esquinas de la azotea del casetón + ruinas de una ampliación demolida atrás
    for (xx, yy) in ((3.6, -1.8), (7.2, -1.8), (3.6, 1.8), (7.2, 1.8)):
        add("rebar_nest", dm.rebar_nest(seed=int(r.integers(1e6)), n=int(r.integers(4, 8)), length=0.7, stump=(0.25, 0.25, 0.25), detail=detail),
            _T(xx, yy, zl[-1] + PENT_H + 0.35), details)
    for (xx, yy) in ((-6.0, 8.6), (-2.4, 8.6), (1.2, 8.6), (-6.0, 11.0), (-2.4, 11.0), (1.2, 11.0)):
        add("rebar_nest", dm.rebar_nest(seed=int(r.integers(1e6)), n=int(r.integers(5, 9)), length=float(r.uniform(0.6, 1.1)),
                                        stump=(0.35, 0.35, float(r.uniform(0.3, 0.9))), detail=detail), _T(xx, yy, 0.0), skirt)
    # escombro: al pie de la fachada oeste, en el local oeste (PB), en el corredor del 2.º piso y entre las ruinas
    for (xx, yy, zz, rad, tgt) in ((-9.0, -1.5, 0.0, 1.3, skirt), (-4.2, -3.0, zl[0], 0.9, interior), (-5.2, 0.0, zl[2], 0.6, interior),
                                   (-1.0, 9.8, 0.0, 1.1, skirt)):
        add("rubble_pile", dm.rubble_pile(radius=rad, seed=int(r.integers(1e6)), n=int(rad * 40), detail=detail), _T(xx, yy, zz), tgt)
    # trozos sueltos al pie de los muros
    for _ in range(18):
        xx, yy = float(r.uniform(-9.5, -7.5)), float(r.uniform(-5.5, 5.5))
        add("chunk", dm.chunk(size=float(r.uniform(0.12, 0.45)), seed=int(r.integers(1e6)), detail=detail),
            _T(xx, yy, 0.0) @ _rot_z(float(r.uniform(0, 360))), skirt)
    return n
# ----------------------------------------------------------------------------------------------
# ensamblado
# ----------------------------------------------------------------------------------------------
def build_apt_a(collection_root=None, dress=True, roof_detail="low"):
    """APT_A_5p completo hasta donde llega el kit aprobado. Devuelve dict colección -> [objetos]."""
    from kit.common import get_collection
    cfg = cfg_apt_a()
    cid = cfg["id"]
    root = collection_root or get_collection(cid)
    cols = {k: get_collection(f"{cid}_{k}", root) for k in ("Shell", "Details", "Interior", "Skirt", "Roof")}
    out = {k: [] for k in cols}
    shell = MB()
    build_frame(cfg, shell)
    placed = {}
    for side in ("front", "back", "west", "east"):
        placed[side] = build_facade(cfg, shell, side)
    pent = build_penthouse(cfg, shell)
    out["Shell"].append(shell.finish(f"{cid}_Shell", cols["Shell"], uv_size=3.0, merge=0))
    out["pent"] = pent
    inter = MB()
    doors = []
    build_interior_apt_a(cfg, inter, out=doors)
    if dress:
        det = MB()
        stats = dict(openings=dress_openings(cfg, placed, det, inter))
        stats["interior_doors"] = dress_interior_doors(cfg, doors, inter)
        dress_stairs(cfg, inter)
        dress_penthouse(cfg, pent, det)
        roof = MB()
        stats["roof"] = dress_roof(cfg, pent, roof, det, detail=roof_detail)
        out["Roof"].append(roof.finish(f"{cid}_Roof", cols["Roof"], uv_size=2.0, merge=0))
        stats["services"] = dress_services(cfg, placed, pent, det, inter)
        out["Details"].append(det.finish(f"{cid}_Details", cols["Details"], uv_size=2.0, merge=0))
        out["stats"] = stats
    out["Interior"].append(inter.finish(f"{cid}_Interior", cols["Interior"], uv_size=3.0, merge=0))
    sk = MB()
    lobby = (0.2, cfg["ys"][0] - 3.2, 3.4, cfg["ys"][0])          # accesos limpios de hierba
    rear = (1.0, cfg["ys"][-1], 2.6, cfg["ys"][-1] + 3.0)
    out["stats_skirt"] = build_skirt(cfg, sk, margin=3.0, keep_clear=(lobby, rear))
    if dress:
        dmg_shell, dmg_det, dmg_int = MB(), MB(), MB()
        out["stats_damage"] = dress_damage(cfg, dmg_shell, dmg_det, dmg_int, sk)
        cols["Damage"] = get_collection(f"{cid}_Damage", root)
        out["Damage"] = []
        for nm, mbd in (("Damage_Shell", dmg_shell), ("Damage_Details", dmg_det), ("Damage_Interior", dmg_int)):
            if len(mbd.bm.faces):
                out["Damage"].append(mbd.finish(f"{cid}_{nm}", cols["Damage"], uv_size=2.0, merge=0))
    out["Skirt"].append(sk.finish(f"{cid}_Skirt", cols["Skirt"], uv_size=2.0, merge=0))
    out["cfg"] = cfg
    out["placed"] = placed
    return out


def build_structure(cfg, collection=None):
    """(compatibilidad) Estructura + fachadas + interior sin vestir."""
    objs = []
    mb = MB()
    build_frame(cfg, mb)
    objs.append(mb.finish(f"{cfg['id']}_Frame", collection, uv_size=3.0, merge=0))
    placed = {}
    for side in ("front", "back", "west", "east"):
        mb = MB()
        placed[side] = build_facade(cfg, mb, side)
        objs.append(mb.finish(f"{cfg['id']}_Facade_{side}", collection, uv_size=3.0, merge=0))
    mb = MB()
    build_interior_apt_a(cfg, mb)
    objs.append(mb.finish(f"{cfg['id']}_Interior", collection, uv_size=3.0, merge=0))
    return objs, placed
