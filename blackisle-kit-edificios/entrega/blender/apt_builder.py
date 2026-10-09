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
    east = {0: ["window_high", "breeze", "window_high"]}
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
        openings = [hole] if 0 < k < len(zl) - 1 else []
        if k == 0:
            wall_with_openings(mb, x1 - x0, y1 - y0, GROUND, openings, mat_out="concrete", mat_in="concrete",
                               mat_reveal="concrete", m=m_slab(x0, y0, zt))
        else:
            wall_with_openings(mb, x1 - x0, y1 - y0, SLAB, openings, mat_out="concrete", mat_in="plaster",
                               mat_reveal="concrete", m=m_slab(x0, y0, zt))
    return mb


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
        if kind == "breeze":  # la celosía va en dress (es el cierre del núcleo de escalera)
            placed.append(dict(p, opening=None))
            continue
        L, H = p["L"], p["H"]
        op = OPENING.get(kind)
        openings = []
        if op is not None:
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
def partition(mb, p0, p1, z0, H, doors=(), t=PART, mat="plaster", door_h=2.05):
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


def inner_faces(cfg):
    xs, ys = cfg["xs"], cfg["ys"]
    k = COL / 2 - RECESS + INFILL     # de la línea de malla a la cara interior del relleno
    return xs[0] - (COL / 2 - RECESS) + INFILL, xs[-1] + (COL / 2 - RECESS) - INFILL, \
        ys[0] - (COL / 2 - RECESS) + INFILL, ys[-1] + (COL / 2 - RECESS) - INFILL


def build_interior_apt_a(cfg, mb):
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
            partition(mb, (0.25, y_lobby_in), (0.25, yin1), z0, H, doors=[(-3.0, 0.9), (3.0, 0.9)])
            partition(mb, (3.35, y_lobby_in), (3.35, -wy), z0, H, doors=[(-3.0, 0.9)])
            partition(mb, (3.35, wy), (3.35, yin1), z0, H, doors=[(3.2, 0.9)])
            partition(mb, (xin0, 0.6), (0.2, 0.6), z0, H, doors=[(-3.6, 1.4)])          # local oeste | bodega
            partition(mb, (xin0, 3.0), (-5.0, 3.0), z0, H, doors=[(-6.0, 0.8)])          # WC de la bodega
            partition(mb, (-5.0, 3.0), (-5.0, yin1), z0, H)
            continue
        cw, xh = 0.75, 2.4
        for sg in (-1, 1):
            yc, yo = sg * cw, (yin0 if sg < 0 else yin1)
            # corredor (muro hacia los deptos) con puertas de acceso a A1/A3 (x -1.0) y A2/A4 (x 1.8)
            partition(mb, (xin0, yc), (xh, yc), z0, H, doors=[(-1.0, 0.9), (1.8, 0.9)])
            partition(mb, (xh, yc), (xh, sg * wy), z0, H)                                   # quiebre corredor → vestíbulo
            partition(mb, (xh, sg * wy), (3.625, sg * wy), z0, H, t=0.15)                  # vestíbulo de escalera
            partition(mb, (0.0, yo), (0.0, yc), z0, H)                                       # medianera A1|A2
            # A1/A3: estancia x -3.6..0 · recámara x xin0..-3.6 (lado fachada) · cocina x -5.4..-3.6 y baño x xin0..-5.4 (lado corredor)
            partition(mb, (-3.6, yo), (-3.6, yc), z0, H, doors=[(sg * 3.8, 0.8), (sg * 1.6, 0.8)])
            partition(mb, (xin0, sg * 2.4), (-3.6, sg * 2.4), z0, H)
            partition(mb, (-5.4, sg * 2.4), (-5.4, yc), z0, H, doors=[(sg * 1.6, 0.7)])
            # A2/A4: estancia x 0..3.6 · recámara de esquina x 3.6..xin1 · cocina-acceso x 1.2..2.4 y baño x 0..1.2 (lado corredor)
            partition(mb, (3.6, yo), (3.6, sg * wy), z0, H, doors=[(sg * 3.0, 0.8)])
            partition(mb, (0.0, sg * 2.6), (2.4, sg * 2.6), z0, H, doors=[(1.8, 1.2)])
            partition(mb, (1.2, sg * 2.6), (1.2, yc), z0, H, doors=[(sg * 1.7, 0.7)])
    return mb


# ----------------------------------------------------------------------------------------------
# ensamblado
# ----------------------------------------------------------------------------------------------
def build_structure(cfg, collection=None):
    """Estructura + fachadas + interior. Devuelve (objetos, paneles colocados)."""
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
