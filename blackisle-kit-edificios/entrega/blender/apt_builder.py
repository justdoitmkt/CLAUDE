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
SKIRT_TERRAIN = True  # False (kit UE5): sin arena ni hierba alrededor; el escombro exterior se conserva como pieza suelta


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
    east = {0: ["window_high", "window_high", "window_high"]}  # PB cerrada; ventana alta sobre el descanso; la celosía arranca en el 1.er piso
    east.update({k: ["window", "breeze", "window"] for k in (1, 2, 3, 4)})
    zl = [GROUND]
    for hh in h:
        zl.append(zl[-1] + hh)
    # mordidas con varilla expuesta en columnas y vigas exteriores (fachada oeste muy dañada, golpes al pie de las columnas
    # del frente, vigas sobre las logias y trasera); sides = (cara de x, cara de y) en columnas, (cara lateral, -1 abajo) en vigas
    spalls = {
        ("col", 0, 1): [dict(sides=(-1, -1), start=zl[2] + 0.55, length=1.0, depth=0.09, seed=1101),
                        dict(sides=(-1, 1), start=zl[3] + 1.1, length=0.8, depth=0.07, seed=1102)],
        ("col", 0, 2): [dict(sides=(-1, 1), start=zl[1] + 0.9, length=1.3, depth=0.09, seed=1103)],
        ("col", 1, 0): [dict(sides=(-1, -1), start=0.32, length=0.7, depth=0.06, seed=1104)],
        ("col", 3, 0): [dict(sides=(1, -1), start=0.45, length=0.55, depth=0.05, seed=1105)],
        ("beam", 2, "y", 0, 1): [dict(sides=(-1, -1), start=0.4, length=1.4, depth=0.08, seed=1106)],
        ("beam", 3, "y", 0, 0): [dict(sides=(-1, -1), start=1.0, length=1.0, depth=0.07, seed=1107)],
        ("beam", 4, "y", 0, 2): [dict(sides=(-1, -1), start=0.6, length=0.9, depth=0.06, seed=1108)],
        ("beam", 1, "x", 1, 0): [dict(sides=(-1, -1), start=0.8, length=1.2, depth=0.08, seed=1109)],
        ("beam", 3, "x", 2, 0): [dict(sides=(-1, -1), start=1.4, length=0.9, depth=0.07, seed=1110)],
        ("beam", 2, "x", 0, 3): [dict(sides=(1, -1), start=0.5, length=1.5, depth=0.08, seed=1111)],
    }
    return dict(id="APT_A_5p", xs=xs, ys=ys, h=h, stair=stair, front=front, back=back, west=west, east=east,
                loggia_depth=1.2, seed=11, spalls=spalls)


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
    if "corner_nodes" in cfg:                     # plantas en L: esquinas reales dadas por el constructor
        return COL_CORNER if (i, j) in cfg["corner_nodes"] else COL
    corner = i in (0, len(cfg["xs"]) - 1) and j in (0, len(cfg["ys"]) - 1)
    return COL_CORNER if corner else COL


def bay_span(coords, k, sizes):
    """Tramo libre entre caras de columna para la crujía k."""
    return coords[k] + sizes[k] / 2, coords[k + 1] - sizes[k + 1] / 2


# ----------------------------------------------------------------------------------------------
# estructura
# ----------------------------------------------------------------------------------------------
def _cell_on(cfg, i, j):
    cells = cfg.get("cells")
    return cells is None or (i, j) in cells


def _node_on(cfg, i, j):
    """Hay columna en el nodo (i, j) si toca alguna crujía activa (plantas en L: cfg['cells'])."""
    return any(_cell_on(cfg, a, b) for a in (i - 1, i) for b in (j - 1, j)
               if 0 <= a < len(cfg["xs"]) - 1 and 0 <= b < len(cfg["ys"]) - 1)


SLAB_BAND = 0.06       # canto de losa perimetral (barrido con goterón) que sustituye la orilla de la losa


def slab_band(mb, path, closed, z_top, t=SLAB, mat="concrete"):  # noqa: C901
    """Canto de losa: perfil de 6 cm (2 cm fuera de la cara del relleno) con aristas superior e inferior redondeadas
    (r 8 mm) y GOTERÓN de 10 × 10 mm a 1,2 cm de la orilla en la cara de abajo, barrido por la orilla (recorrido
    antihorario en planta: el perfil x crece hacia afuera). Cerrado o abierto (ramas de una planta en L)."""
    w = SLAB_BAND
    k = 0.0023
    prof = [(-w, 0.0), (-0.008, 0.0), (-k, -k), (0.0, -0.008), (0.0, -t + 0.008), (-k, -t + k), (-0.008, -t),
            (-0.0115, -t), (-0.0122, -t + 0.009), (-0.0135, -t + 0.0102), (-0.0205, -t + 0.0102), (-0.0218, -t + 0.009),
            (-0.0225, -t), (-w, -t)]
    pts = [Vector((p[0], p[1], z_top)) for p in path]
    mb.sweep(list(reversed(prof)), pts, mat=mat, closed_profile=True, closed_path=closed, normal=(0, 0, 1))


def frame_spalls(cfg):
    """Mordidas de arista con varilla expuesta INTEGRADAS en la estructura (R-AAA, 2026-11-19). Antes eran envolventes
    2 mm por fuera de la columna sana y la mordida quedaba tapada por la columna original. cfg['spalls'] =
    {('col', i, j): [mordida, ...], ('beam', k, eje, i, j): [...]} con mordida = dict(sides, start, length, depth, seed)
    (convención de kit.damage.spalled_box; start desde el inicio del elemento)."""
    return cfg.get("spalls", {})


def _spalled(spall_mb, mb, key, mn, mx, axis, bevel, seg, cfg):
    sp = frame_spalls(cfg).get(key)
    if not sp or spall_mb is None:
        mb.box(mn, mx, "concrete", bevel=bevel, seg=seg)
        return False
    from kit import damage as dm
    dm.spalled_box(spall_mb, mn, mx, [dict(d, axis=axis) for d in sp], mat="concrete", bevel=bevel, seg=seg, detail="high")
    return True


def build_frame(cfg, mb, spall_mb=None):
    """Opcionales (APT_B/C/D; APT_A no usa ninguno y su resultado no cambia):
    cells = {(i, j)} crujías activas (planta en L) · col_top = {(i, j): z} columnas truncadas (colapso) ·
    skip_beam(k, eje, i, j) -> bool · stair_levels = losas k con hueco de escalera · holes = {k: [(x0, x1, y0, y1)]} huecos
    extra en coordenadas absolutas · slab_rects = [(x0, x1, y0, y1)] losas por rectángulos (absolutas, antes del vuelo de viga).
    spall_mb: MB donde van las columnas y vigas con mordidas de cfg['spalls'] (grupo Damage); slab_band (por omisión True):
    canto de losa redondeado con goterón en las orillas con vuelo."""
    xs, ys = cfg["xs"], cfg["ys"]
    zl = level_z(cfg)
    r = rng(cfg["seed"])
    top = zl[-1]
    col_top = cfg.get("col_top", {})
    skip = cfg.get("skip_beam", lambda k, ax, i, j: False)
    # columnas continuas desde el desplante hasta la losa de azotea (desplome leve aleatorio en la sección, no en el eje)
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            if not _node_on(cfg, i, j):
                continue
            c = col_size(i, j, cfg) / 2
            _spalled(spall_mb, mb, ("col", i, j), (x - c, y - c, 0.0), (x + c, y + c, col_top.get((i, j), top - SLAB)), "z", 0.012, 2, cfg)
    # vigas en todas las líneas de la malla (descuelgue BEAM_D - SLAB bajo la losa)
    for k in range(1, len(zl)):
        zt = zl[k] - SLAB
        zb = zl[k] - BEAM_D
        for j, y in enumerate(ys):
            for i in range(len(xs) - 1):
                if not (_cell_on(cfg, i, j) or _cell_on(cfg, i, j - 1)) or skip(k, "x", i, j):
                    continue
                x0 = xs[i] + col_size(i, j, cfg) / 2
                x1 = xs[i + 1] - col_size(i + 1, j, cfg) / 2
                sag = float(r.uniform(0.0, 0.012))
                _spalled(spall_mb, mb, ("beam", k, "x", i, j), (x0, y - BEAM_W / 2, zb - sag), (x1, y + BEAM_W / 2, zt), "x", 0.01, 2, cfg)
        for i, x in enumerate(xs):
            for j in range(len(ys) - 1):
                if not (_cell_on(cfg, i, j) or _cell_on(cfg, i - 1, j)) or skip(k, "y", i, j):
                    continue
                y0 = ys[j] + col_size(i, j, cfg) / 2
                y1 = ys[j + 1] - col_size(i, j + 1, cfg) / 2
                _spalled(spall_mb, mb, ("beam", k, "y", i, j), (x - BEAM_W / 2, y0, zb), (x + BEAM_W / 2, y1, zt), "y", 0.01, 2, cfg)
    # losas: desplante + entrepisos + azotea; las de entrepiso llevan el hueco de escalera
    ex = BEAM_W / 2
    st = cfg["stair"]
    st_levels = cfg.get("stair_levels", range(1, len(zl)))      # APT_A: la escalera sigue hasta el casetón de azotea
    rects = cfg.get("slab_rects", [(xs[0], xs[-1], ys[0], ys[-1])])
    band = cfg.get("slab_band", True)
    for rect in rects:
        rx0, rx1, ry0, ry1 = rect[:4]
        e = rect[4] if len(rect) > 4 else (ex, ex, ex, ex)   # vuelo por lado (0 en la junta de dos losas de una planta en L)
        X0, X1 = rx0 - e[0], rx1 + e[1]
        Y0, Y1 = ry0 - e[2], ry1 + e[3]
        on = [band and v > 0 for v in e]                      # lados con canto (x0, x1, y0, y1)
        for k, zt in enumerate(zl):
            x0, x1, y0, y1 = X0, X1, Y0, Y1
            if k > 0 and any(on):
                # la losa se recorta SLAB_BAND en los lados con canto y el canto barrido (con goterón) la completa
                w = SLAB_BAND
                x0, x1 = X0 + (w if on[0] else 0.0), X1 - (w if on[1] else 0.0)
                y0, y1 = Y0 + (w if on[2] else 0.0), Y1 - (w if on[3] else 0.0)
                corners = [(X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)]
                side_on = [on[2], on[1], on[3], on[0]]            # recorrido antihorario: abajo, derecha, arriba, izquierda
                touch = [hh for hh in cfg.get("holes", {}).get(k, [])
                         if hh[0] < X0 + w or hh[1] > X1 - w or hh[2] < Y0 + w or hh[3] > Y1 - w]
                if touch:
                    # un hueco (colapso) llega a la orilla: canto por lado, a tope en las esquinas, cortado donde está el hueco
                    for sd in range(4):
                        if not side_on[sd]:
                            continue
                        A, B = Vector((*corners[sd], 0.0)), Vector((*corners[(sd + 1) % 4], 0.0))
                        dv = B - A
                        Ls = dv.length
                        dv /= Ls
                        nrm = Vector((dv.y, -dv.x, 0.0))          # hacia afuera
                        blocked = []
                        for (hx0, hx1, hy0, hy1) in touch:
                            ts = []
                            for q in ((hx0, hy0), (hx1, hy0), (hx1, hy1), (hx0, hy1)):
                                ts.append((Vector((q[0], q[1], 0.0)) - A).dot(dv))
                            ds = [(Vector((q[0], q[1], 0.0)) - A).dot(nrm) for q in ((hx0, hy0), (hx1, hy0), (hx1, hy1), (hx0, hy1))]
                            if min(ds) < 0.0 and max(ds) > -w:            # el hueco toca la franja del canto
                                blocked.append((min(ts), max(ts)))
                        t0 = 0.0
                        for (b0, b1) in sorted(blocked) + [(Ls - w, Ls + 1.0)]:
                            if b0 > t0 + 0.05:
                                slab_band(mb, [tuple(A + dv * t0)[:2], tuple(A + dv * min(b0, Ls - w))[:2]], False, zt)
                            t0 = max(t0, b1)
                elif all(side_on):
                    slab_band(mb, corners, True, zt)
                else:
                    k0 = next(q for q in range(4) if not side_on[q])
                    run = []
                    for q in range(1, 5):
                        sd = (k0 + q) % 4
                        if side_on[sd]:
                            if not run:
                                run = [corners[sd]]
                            run.append(corners[(sd + 1) % 4])
                        elif run:
                            slab_band(mb, run, False, zt)
                            run = []
                    if run:
                        slab_band(mb, run, False, zt)
            holes = []
            if k in st_levels:
                holes.append((st["x0"], st["x0"] + st["w"], st["y0"], st["y0"] + st["l"]))
            holes += cfg.get("holes", {}).get(k, [])
            openings = [(hx0 - x0, hx1 - x0, hy0 - y0, hy1 - y0) for (hx0, hx1, hy0, hy1) in holes
                        if hx0 < x1 and hx1 > x0 and hy0 < y1 and hy1 > y0]
            if k == 0:
                wall_with_openings(mb, x1 - x0, y1 - y0, GROUND, openings, mat_out="concrete", mat_in="concrete",
                                   mat_reveal="concrete", m=m_slab(x0, y0, zt))
            else:
                wall_with_openings(mb, x1 - x0, y1 - y0, SLAB, openings, mat_out="concrete", mat_in="plaster",
                                   mat_reveal="concrete", m=m_slab(x0, y0, zt))
    return mb


PENT_H = 2.7          # casetón de escalera sobre la losa de azotea


PENT_XW = 2.30        # cara exterior del muro oeste del casetón: deja un descanso de llegada x 2,45..3,70 como en los pisos


def coping(mb, path, z, closed=True, w=0.17, mat="concrete"):
    """Remate (albardilla) de concreto sobre un pretil de 12 cm: 17 × 5 cm con vuelo de 2,5 cm a cada lado, cantos
    redondeados, pendiente de 6 mm hacia adentro y gotero de 6 × 6 mm bajo cada vuelo; se asienta 2 mm en el pretil.
    path: eje del pretil en planta, antihorario (el lado + del perfil queda hacia afuera)."""
    h = w / 2
    prof = [(-0.060, -0.002), (-0.070, 0.0), (-0.070, 0.006), (-0.076, 0.006), (-0.076, 0.0), (-h + 0.002, 0.0), (-h, 0.004),
            (-h, 0.040), (-h + 0.004, 0.047), (-h + 0.011, 0.050), (h - 0.011, 0.056), (h - 0.004, 0.053), (h, 0.046), (h, 0.004),
            (h - 0.002, 0.0), (0.076, 0.0), (0.076, 0.006), (0.070, 0.006), (0.070, 0.0), (0.060, -0.002)]
    mb.sweep(list(reversed(prof)), [Vector((p[0], p[1], z)) for p in path], mat=mat, closed_profile=True, closed_path=closed,
             normal=(0, 0, 1))


def build_penthouse(cfg, mb, details=None):
    """Casetón sobre el núcleo: prolonga las 4 columnas (3.6/7.2, ±1.8), vigas perimetrales, losa de techo con pretil,
    muros norte/sur ciegos, muro este con ventilas. Se alarga al oeste hasta x = PENT_XW para que la escalera llegue a un
    descanso (auditoría: antes llegaba contra el muro); el muro oeste, con la puerta metálica al ático, va en ese extremo."""
    zl = level_z(cfg)
    z0, z1 = zl[-1], zl[-1] + PENT_H
    cx, cy = (3.6, 7.2), (-1.8, 1.8)
    xw = PENT_XW
    for x in cx:
        for y in cy:
            c = COL / 2
            mb.box((x - c, y - c, z0 - SLAB), (x + c, y + c, z1 - SLAB), "concrete", bevel=0.012, seg=2)
    for y in cy:
        mb.box((cx[0] + COL / 2, y - BEAM_W / 2, z1 - 0.40), (cx[1] - COL / 2, y + BEAM_W / 2, z1 - SLAB), "concrete", bevel=0.01, seg=1)
        mb.box((xw + INFILL, y - BEAM_W / 2, z1 - 0.40), (cx[0] - COL / 2, y + BEAM_W / 2, z1 - SLAB), "concrete", bevel=0.01, seg=1)
    for x in cx:
        mb.box((x - BEAM_W / 2, cy[0] + COL / 2, z1 - 0.40), (x + BEAM_W / 2, cy[1] - COL / 2, z1 - SLAB), "concrete", bevel=0.01, seg=1)
    # losa de techo del casetón + pretil bajo
    x0, x1, y0, y1 = xw - 0.05, cx[1] + COL / 2 + 0.05, cy[0] - COL / 2 - 0.05, cy[1] + COL / 2 + 0.05
    mb.box((x0, y0, z1 - SLAB), (x1, y1, z1), "concrete", bevel=0.015, seg=2)
    for (a, b) in (((x0, y0), (x1, y0 + 0.12)), ((x0, y1 - 0.12), (x1, y1)), ((x0, y0 + 0.12), (x0 + 0.12, y1 - 0.12)), ((x1 - 0.12, y0 + 0.12), (x1, y1 - 0.12))):
        mb.box((a[0], a[1], z1), (b[0], b[1], z1 + 0.35), "concrete", bevel=0.01, seg=1)
    coping(mb, [(x0 + 0.06, y0 + 0.06), (x1 - 0.06, y0 + 0.06), (x1 - 0.06, y1 - 0.06), (x0 + 0.06, y1 - 0.06)], z1 + 0.35)
    H = PENT_H - 0.40
    # muros norte y sur (ciegos), tramo entre columnas + prolongación hasta el muro oeste
    for sg, y in ((-1, cy[0]), (1, cy[1])):
        face = y + sg * (COL / 2 - RECESS)
        m = m_wall_x(cx[0] + COL / 2, face, z0, +1) if sg < 0 else m_wall_x(cx[1] - COL / 2, face, z0, -1)
        wall_with_openings(mb, (cx[1] - cx[0]) - COL, H, INFILL, [], mat_out="plaster", mat_in="plaster", mat_reveal="concrete", m=m)
        Le = (cx[0] - COL / 2) - (xw + INFILL)
        m = m_wall_x(xw + INFILL, face, z0, +1) if sg < 0 else m_wall_x(cx[0] - COL / 2, face, z0, -1)
        wall_with_openings(mb, Le, H + 0.2, INFILL, [], mat_out="plaster", mat_in="plaster", mat_reveal="concrete", m=m)
    # muro oeste con puerta al ático (se viste en dress)
    Lw = (cy[1] - cy[0]) + 2 * (COL / 2 - RECESS)
    mw = m_wall_y(cy[1] + (COL / 2 - RECESS), xw, z0, +1)
    door = (round((Lw - 0.9) / 2, 4), round((Lw + 0.9) / 2, 4), 0.0, 2.05)
    wall_with_openings(mb, Lw, H + 0.2, INFILL, [door], mat_out="plaster", mat_in="plaster", mat_reveal="concrete", m=mw)
    # muro este: jambas + vano de celosía (como la fachada)
    L = (cy[1] - cy[0]) - COL
    me = m_wall_y(cy[0] + COL / 2, cx[1] + (COL / 2 - RECESS), z0, -1)
    vents = [(round(L / 2 - 0.9, 4), round(L / 2 - 0.3, 4), 1.5, 2.0), (round(L / 2 + 0.3, 4), round(L / 2 + 0.9, 4), 1.5, 2.0)]
    wall_with_openings(mb, L, H, INFILL, vents, mat_out="plaster", mat_in="plaster", mat_reveal="concrete", m=me)
    return dict(door=(mw, door), vents=(me, vents), top_z=z1, rect=(x0, y0, x1, y1))


# ----------------------------------------------------------------------------------------------
# aplanado caído y grietas: el block a la vista (R-AAA, 2026-11-19 — antes los muros eran un plano liso)
# ----------------------------------------------------------------------------------------------
PLASTER_T = 0.015                       # aplanado de mortero (cemento-arena) de 1,5 cm
BLOCK_H, BLOCK_L, JOINT = 0.20, 0.40, 0.01   # block hueco 15/12 × 20 × 40 (NMX, homedepot.com.mx) con junta de 1 cm


def plan_patches(L, H, openings, r, n, size=(0.4, 1.3), margin=0.12, edge=0.07, crack=0.3):
    """Hasta n parches (tipo, u0, u1, v0, v1) en un muro L × H que no tocan los vanos (margen: alféizares, rejas) ni los
    bordes. tipo 'spall' = aplanado caído (se ve el block), 'crack' = grieta que atraviesa el aplanado."""
    out = []
    for _ in range(n * 8):
        if len(out) >= n:
            break
        kind = "crack" if r.random() < crack else "spall"
        if kind == "crack":
            w, h = float(r.uniform(0.22, 0.45)), float(r.uniform(0.5, 1.1))
        else:
            w, h = float(r.uniform(*size)), float(r.uniform(size[0] * 0.8, size[1] * 0.85))
        if w > L - 2 * edge or h > H - 2 * edge:
            continue
        u0 = float(r.uniform(edge, L - edge - w))
        v0 = float(r.uniform(edge, H - edge - h))
        rect = (u0, u0 + w, v0, v0 + h)
        others = list(openings) + [q[1:] for q in out]
        if any(not (rect[1] + margin < o[0] or rect[0] - margin > o[1] or rect[3] + margin < o[2] or rect[2] - margin > o[3])
               for o in others):
            continue
        out.append((kind,) + tuple(round(x, 4) for x in rect))
    return out


def _ring_rect(u0, u1, v0, v1, n, start=None):
    """n puntos en el perímetro del rectángulo, antihorario (u, v), CON las 4 esquinas (si no, el anillo del aplanado
    corta la esquina y deja un agujerito), desde el punto más cercano a `start`."""
    sides = [((u0, v0), (u1, v0)), ((u1, v0), (u1, v1)), ((u1, v1), (u0, v1)), ((u0, v1), (u0, v0))]
    lens = [abs(u1 - u0), abs(v1 - v0), abs(u1 - u0), abs(v1 - v0)]
    per = sum(lens)
    cnt = [max(1, int(round(n * L / per))) for L in lens]
    cnt[0] += n - sum(cnt)
    pts = []
    for (a, b), c in zip(sides, cnt):
        for k in range(c):
            t = k / c
            pts.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    if start is not None:
        k0 = min(range(n), key=lambda i: (pts[i][0] - start[0]) ** 2 + (pts[i][1] - start[1]) ** 2)
        pts = pts[k0:] + pts[:k0]
    return pts


def _resample_closed(pts, n):
    P = [Vector((p[0], p[1], 0.0)) for p in pts]
    L = [(P[(i + 1) % len(P)] - P[i]).length for i in range(len(P))]
    tot = sum(L)
    out, i, acc = [], 0, 0.0
    for k in range(n):
        d = tot * k / n
        while acc + L[i] < d - 1e-12:
            acc += L[i]
            i += 1
        t = (d - acc) / max(L[i], 1e-12)
        q = P[i].lerp(P[(i + 1) % len(P)], t)
        out.append((q.x, q.y))
    return out


def patch_fill(mb, m, patch, t, r, filler="block", lip=PLASTER_T, mat_face="plaster", mat_back="plaster"):
    """Rellena el hueco `patch` (tipo, u0, u1, v0, v1) abierto en un muro (coordenadas del muro: u, v; cara exterior y = 0,
    interior y = t): aplanado roto alrededor (contorno irregular, canto de fractura con chaflán) y detrás, a 1,5 cm,
    hiladas de block 40 × 20 cuatrapeadas con junta de mortero rehundida 8 mm (filler='block'), o concreto rugoso con la
    malla de varilla del panel a la vista (filler='concrete', paneles de APT_D). Por dentro el muro conserva su aplanado.
    'crack': el aplanado cubre todo menos una grieta de 2–6 mm que deja ver el fondo."""
    kind, u0, u1, v0, v1 = patch
    tmp = MB()
    off = Vector((float(r.uniform(-300, 300)), float(r.uniform(-300, 300)), 0.0))
    from mathutils import noise as mn
    yb0, yb1 = lip + 0.001, t - PLASTER_T - 0.001
    if filler == "block":
        tmp.box((u0 + 0.001, yb0 + 0.008, v0 + 0.001), (u1 - 0.001, yb1 - 0.001, v1 - 0.001), "mortar", bevel=0.0)
        pitch_v, pitch_u = BLOCK_H + JOINT, BLOCK_L + JOINT
        for k in range(int(math.floor(v0 / pitch_v)) - 1, int(math.ceil(v1 / pitch_v)) + 1):
            va, vb = k * pitch_v + JOINT / 2, k * pitch_v + JOINT / 2 + BLOCK_H
            va, vb = max(va, v0 + 0.002), min(vb, v1 - 0.002)
            if vb - va < 0.015:
                continue
            shift = pitch_u / 2 if k % 2 else 0.0
            for j in range(int(math.floor((u0 - shift) / pitch_u)) - 1, int(math.ceil((u1 - shift) / pitch_u)) + 1):
                ua, ub = shift + j * pitch_u + JOINT / 2, shift + j * pitch_u + JOINT / 2 + BLOCK_L
                ua, ub = max(ua, u0 + 0.002), min(ub, u1 - 0.002)
                if ub - ua < 0.015:
                    continue
                yo = float(r.uniform(-0.0015, 0.0025))
                tmp.box((ua, yb0 + yo, va), (ub, yb1, vb), "block", bevel=0.004, seg=1)
    else:
        dep = 0.03                                         # el recubrimiento se cayó: queda el concreto y la malla
        tmp.box((u0 + 0.001, yb0 + dep, v0 + 0.001), (u1 - 0.001, yb1, v1 - 0.001), "concrete", bevel=0.0)
        bars = MB()
        from kit import damage as dm
        for uu in [u0 + 0.05 + 0.15 * i for i in range(int((u1 - u0 - 0.06) / 0.15) + 1)]:
            dm._rebar(bars, [Vector((uu, yb0 + dep - 0.004, v0 + 0.004)), Vector((uu, yb0 + dep - 0.004, v1 - 0.004))], 0.0048,
                      ribs=False, seg=12)
        for vv in [v0 + 0.06 + 0.15 * i for i in range(int((v1 - v0 - 0.07) / 0.15) + 1)]:
            dm._rebar(bars, [Vector((u0 + 0.004, yb0 + dep - 0.013, vv)), Vector((u1 - 0.004, yb0 + dep - 0.013, vv))], 0.0048,
                      ribs=False, seg=12)
        with tmp.soft():
            tmp.join(bars)
    # aplanado interior intacto; el aro de aplanado y esta placa llegan EXACTO al canto del hueco (con holgura se leía el
    # rectángulo del parche como una raya fina); la carcasa no se suelda (merge=0), así no hay aristas de 4 caras
    tmp.box((u0, t - PLASTER_T, v0), (u1, t, v1), mat_back, bevel=0.0)
    # aplanado roto: anillo entre el borde del hueco y el contorno de la fractura
    N = 64
    cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
    if kind == "spall":
        outer = _ring_rect(u0, u1, v0, v1, N)
        inner = []
        for (a, b) in outer:
            th = math.atan2(b - cv, a - cu)
            k = 0.70 + 0.16 * mn.noise(Vector((math.cos(th) * 1.6, math.sin(th) * 1.6, 0.0)) + off) \
                + 0.05 * mn.noise(Vector((math.cos(th) * 6.0, math.sin(th) * 6.0, 0.0)) + off)
            inner.append((cu + (a - cu) * k, cv + (b - cv) * k))
    else:
        # grieta: de una esquina a la opuesta con quiebres; ancho 2–6 mm que se adelgaza en las puntas
        flip = r.random() < 0.5
        A = Vector((u0 + 0.03, v0 + 0.03)) if not flip else Vector((u1 - 0.03, v0 + 0.03))
        B = Vector((u1 - 0.03, v1 - 0.03)) if not flip else Vector((u0 + 0.03, v1 - 0.03))
        npt = 14
        path = []
        for i in range(npt + 1):
            s = i / npt
            q = A.lerp(B, s)
            nrm = Vector((-(B - A).y, (B - A).x)).normalized()
            q = q + nrm * (0.035 * mn.noise(Vector((s * 4.0, 0.0, 0.0)) + off) + 0.01 * mn.noise(Vector((s * 13.0, 3.0, 0.0)) + off)) * math.sin(math.pi * s)
            path.append(q)
        left, right = [], []
        for i, q in enumerate(path):
            d = (path[min(i + 1, npt)] - path[max(i - 1, 0)]).normalized()
            nrm = Vector((-d.y, d.x))
            wdt = (0.0012 + 0.0022 * math.sin(math.pi * i / npt) * (0.7 + 0.3 * mn.noise(Vector((i * 0.7, 5.0, 0.0)) + off)))
            left.append(q + nrm * wdt)
            right.append(q - nrm * wdt)
        slit = [(p.x, p.y) for p in right] + [(p.x, p.y) for p in reversed(left)][1:-1]
        area = sum(slit[i][0] * slit[(i + 1) % len(slit)][1] - slit[(i + 1) % len(slit)][0] * slit[i][1] for i in range(len(slit)))
        if area < 0:
            slit = list(reversed(slit))
        inner = _resample_closed(slit, N)
        outer = _ring_rect(u0, u1, v0, v1, N, start=inner[0])
    # anillos: exterior al frente, fractura al frente (chaflán de 2–4 mm), fractura al fondo, exterior al fondo
    def V(u, y, v):
        return tmp.bm.verts.new((u, y, v))
    of = [V(a, 0.0, b) for (a, b) in outer]
    ob = [V(a, lip, b) for (a, b) in outer]
    inf, inb = [], []
    for (a, b), (oa, obb) in zip(inner, outer):
        dv = Vector((a - cu, b - cv))
        dn = dv.normalized() if dv.length > 1e-6 else Vector((0.0, 0.0))
        ch = float(r.uniform(0.002, 0.004)) if kind == "spall" else 0.0008
        inf.append(V(a + dn.x * ch, 0.0, b + dn.y * ch))
        jag = float(r.uniform(-0.003, 0.002)) if kind == "spall" else 0.0
        inb.append(V(a - dn.x * jag, lip, b - dn.y * jag))
    for i in range(N):
        j = (i + 1) % N
        tmp.face([of[i], of[j], inf[j], inf[i]], mat_face)
        tmp.face([inf[i], inf[j], inb[j], inb[i]], "mortar")
        tmp.face([inb[i], inb[j], ob[j], ob[i]], "mortar")
        tmp.face([ob[i], ob[j], of[j], of[i]], "mortar")
    mb.join(tmp, m)


def _wall_patches(cfg, side, key, L, H, openings, density):
    """Parches de una pared (semilla estable por pared): número según la densidad de la fachada."""
    import zlib
    r = rng(cfg["seed"] * 1000 + zlib.crc32(repr(key).encode()) % 100000)
    n = int(density) + (1 if r.random() < density - int(density) else 0)
    return plan_patches(L, H, openings, r, n) if n > 0 else [], r


PATCH_DENSITY = {"front": 0.8, "back": 0.9, "west": 2.0, "east": 0.8}


def panel_patched(cfg, mb, side, line, bay, lv, kinds, H=None, d=0.0, z0=None, mat="plaster", collect=None, tag=""):
    """apt_common.panel con aplanado caído y grietas (block a la vista) en el muro: mismo dict de panel (ops y matriz),
    los parches NO van en 'ops' (no son vanos que se vistan ni cuentan para el grafiti)."""
    import apt_common as ac
    coords, sizes, face = ac.line_geom(cfg, side, line)
    a0, a1 = bay_span(coords, bay, sizes)
    L = a1 - a0
    zl = level_z(cfg)
    z0 = zl[lv] if z0 is None else z0
    H = cfg["h"][lv] - BEAM_D if H is None else H
    ops = ac.layout_openings(kinds, L, H)
    m = ac.panel_matrix(side, a0, a1, face, z0, d)
    no = any(k in ("shutter", "portico", "lobby", "lobby_door") for k, _ in ops)
    dens = 0.0 if no else cfg.get("patch_density", PATCH_DENSITY).get(side, 0.0)
    patches, pr = _wall_patches(cfg, side, (line, bay, lv), L, H, [o for _, o in ops], dens)
    wall_with_openings(mb, L, H, INFILL, [o for _, o in ops] + [q[1:] for q in patches], mat_out=mat, mat_in="plaster",
                       mat_reveal="concrete", m=m)
    for q in patches:
        patch_fill(mb, m, q, INFILL, pr)
    p = dict(side=side, line=line, bay=bay, level=lv, a0=a0, a1=a1, L=L, z0=z0, H=H, face=face, recess=d, m=m, ops=ops, tag=tag,
             patches=patches)
    if collect is not None:
        collect.append(p)
    return p


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
        dens = cfg.get("patch_density", PATCH_DENSITY).get(side, 0.0) if kind not in ("breeze", "shutter", "lobby") else 0.0
        patches, pr = _wall_patches(cfg, side, (p["level"], p["bay"]), L, H, openings, dens)
        wall_with_openings(mb, L, H, INFILL, openings + [q[1:] for q in patches], mat_out="plaster", mat_in="plaster",
                           mat_reveal="concrete", m=m)
        for q in patches:
            patch_fill(mb, m, q, INFILL, pr)
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
            partition(mb, (-3.6, yo), (-3.6, yc), z0, H, doors=[(sg * 3.8, 0.8), (sg * 1.2, 0.8)], out=out)
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
                details.join(op.door("double_glazed", w, h, INFILL, seed=seed, open_angle=max(58.0, float(r.uniform(15, 70)))), M)
            elif kind == "lobby":
                details.join(op.door("double_glazed", w, h, INFILL, seed=seed, open_angle=max(58.0, float(r.uniform(15, 70)))), M)
            elif kind in ("door_rear", "door_service"):
                details.join(op.door("metal", w, h, INFILL, seed=seed, open_angle=max(75.0, float(r.uniform(0, 80)))), M)
            elif kind == "shutter":
                details.join(op.rolling_shutter(w, h, seed=seed, dent=float(r.uniform(0.4, 0.9)),
                                                open_frac=float(r.choice([0.0, 0.0, 0.35]))), M)
            elif kind == "breeze":
                details.join(op.breeze_block_screen(w, h, seed=seed, pattern="cross", y0=0.025,
                                                    missing=float(r.uniform(0.04, 0.12))), M)
            n += 1
            # barandal de loggia sobre el canto de la losa
            if kind == "loggia" and side == "front":
                y_axis = cfg["ys"][0] - BEAM_W / 2 + 0.07
                details.join(circ.railing("tube_metal", p["L"], h=1.0, seed=seed + 7, bend=float(r.choice([0.0, 0.0, 0.12])),
                                          missing=float(r.uniform(0.05, 0.2))), _T(p["a0"], y_axis, p["z0"]))
    return n


DOOR_KINDS = ("door", "lobby", "portico", "loggia", "shutter", "hall")


def door_zones(cfg, panels=(), doors=(), depth=0.9, pad=0.15):
    """Zonas de paso (cajas x0, x1, y0, y1, z0, z1 en mundo) delante y detrás de cada puerta, cortina y vano de paso:
    ahí no se pone escombro, basura ni muebles (auditoría de coherencia 2026-11-19: escombro tapando puertas).
    panels: paneles de fachada (dicts con m y ops / opening+kind); doors: puertas de tabiques (dicts con m, u0, w, t)."""
    out = []

    def box(m, u0, u1, t):
        cs = [m @ Vector((u, y, v)) for u in (u0 - pad, u1 + pad) for y in (-depth, t + depth) for v in (0.0, 2.0)]
        out.append((min(c.x for c in cs), max(c.x for c in cs), min(c.y for c in cs), max(c.y for c in cs),
                    min(c.z for c in cs), max(c.z for c in cs)))
    for p in panels:
        ops = p.get("ops") or ([(p["kind"], p["opening"])] if p.get("opening") else [])
        for kind, o in ops:
            if any(k in kind for k in DOOR_KINDS):
                box(p["m"], o[0], o[1], INFILL)
    for d in doors:
        box(d["m"], d["u0"], d["u0"] + d["w"], d["t"])
    return out


def door_caps(cfg):
    """Topes de la arena acumulada (build_skirt caps) en los pasos de las puertas de PB: la deriva de 30 cm tapaba los
    umbrales (auditoría 2026-11-19). Solo aplica al terreno de revisión; el kit UE5 no lleva terreno."""
    return [(x0, x1, y0, y1, 0.02) for (x0, x1, y0, y1, z0, z1) in cfg.get("door_zones", []) if z0 < 0.6]


def clear_of(zones, x, y, z, rad):
    """True si un círculo (x, y, rad) a la cota z no toca ninguna zona de paso."""
    return not any(z0 - 0.3 <= z <= z1 and x + rad > x0 and x - rad < x1 and y + rad > y0 and y - rad < y1
                   for (x0, x1, y0, y1, z0, z1) in zones)


def nudge(zones, x, y, z, rad, tries=8, step=0.3):
    """Mueve un montón hasta que no tape un paso (espiral de 30 cm); None si no hay lugar."""
    if clear_of(zones, x, y, z, rad):
        return x, y
    for k in range(1, tries + 1):
        for a in range(8):
            xx, yy = x + k * step * math.cos(a * math.pi / 4), y + k * step * math.sin(a * math.pi / 4)
            if clear_of(zones, xx, yy, z, rad):
                return xx, yy
    return None


def door_frame_remnant(w, h, t, seed=0, mat=None):
    """Lo que queda de un marco de puerta interior cuya hoja se arrancó (R-AAA: el vano no queda como un corte limpio en el
    muro): forro de jambas y cabezal de pino de 19 mm del espesor del muro, chambrana de 70 × 15 mm con canto redondeado en
    las dos caras (a veces arrancada en un tramo, con la punta astillada), tope de 12 × 35 mm, las 2 o 3 bisagras rotas
    (media hoja con nudillo) y el contra del pestillo. Local del vano: u 0..w, v 0..h, muro y 0..t."""
    from kit.clinic_equipo import revolve
    r = rng(seed)
    mat = mat or ("wood" if r.random() < 0.55 else "wood_dark")
    mb = MB()
    jt = 0.019
    # forro (jambas y cabezal): tablas del espesor del muro
    e = 0.0006                                   # holgura con el canto del vano (sin caras coincidentes)
    mb.box((e, e, 0.0), (jt + e, t - e, h - e), mat, bevel=0.002, seg=1)
    mb.box((w - jt - e, e, 0.0), (w - e, t - e, h - e), mat, bevel=0.002, seg=1)
    mb.box((jt + e + 0.0005, e, h - jt - e), (w - jt - e - 0.0005, t - e, h - e), mat, bevel=0.002, seg=1)
    # tope (donde cerraba la hoja), a 4 cm de la cara interior
    for (a, b) in (((jt, t - 0.075), (jt + 0.012, t - 0.04)), ((w - jt - 0.012, t - 0.075), (w - jt, t - 0.04))):
        mb.box((a[0], a[1], 0.0), (b[0], b[1], h - jt), mat, bevel=0.0015, seg=1)
    mb.box((jt + 0.0125, t - 0.075, h - jt - 0.012), (w - jt - 0.0125, t - 0.04, h - jt - 0.0005), mat, bevel=0.0015, seg=1)
    # chambranas en las dos caras: jambas + cabezal a inglete (perfil 70 × 15 con canto redondeado de 5 mm)
    cw, ct = 0.07, 0.015
    for face, sg in ((0.0, -1), (t, 1)):
        yb, ye = sorted((face, face + sg * ct))
        for side in (0, 1):
            if r.random() < 0.18:                 # tramo arrancado: queda un pedazo de abajo con la punta rota
                hh = float(r.uniform(0.25, 1.2))
                x0 = -cw + 0.004 if side == 0 else w - 0.004
                mb.box((x0, yb, 0.0), (x0 + cw, ye, hh), mat, bevel=0.004, seg=2)
                for k in range(5):                # astillas de la rotura
                    xx = x0 + cw * (k + 0.5) / 5
                    ln = float(r.uniform(0.01, 0.06))
                    mb.box((xx - 0.006, yb + 0.002, hh - 0.002), (xx + 0.006, ye - 0.002, hh + ln), mat, bevel=0.002, seg=1)
                continue
            x0 = -cw + 0.004 if side == 0 else w - 0.004
            mb.box((x0, yb, 0.0), (x0 + cw, ye, h + cw - 0.004), mat, bevel=0.004, seg=2)
        if r.random() < 0.85:                     # cabezal a tope entre las jambas (sin traslape coplanar)
            mb.box((0.0045, yb, h - 0.004), (w - 0.0045, ye, h + cw - 0.004), mat, bevel=0.004, seg=2)
    # bisagras rotas (media hoja de 89 mm atornillada al forro con su nudillo) y contra del pestillo
    hx = jt if r.random() < 0.5 else w - jt
    sgn = 1 if hx == jt else -1
    for zc in ((0.25, h - 0.28) if r.random() < 0.5 else (0.25, h / 2, h - 0.28)):
        mb.box((hx, t - 0.04 - 0.0, zc - 0.045), (hx + sgn * 0.0025, t - 0.004, zc + 0.045), "steel", bevel=0.0006, seg=1)
        revolve(mb, [(0.0, -0.045), (0.0065, -0.045), (0.0065, 0.045), (0.0, 0.045)], "steel", seg=16, M=_T(hx + sgn * 0.004, t - 0.002, zc))
    lx = w - jt if hx == jt else jt
    mb.box((lx - 0.0015, t - 0.065, 0.98), (lx + 0.0015, t - 0.04, 1.08), "brass", bevel=0.0005, seg=1)
    return mb


def dress_interior_doors(cfg, doors, interior):
    from kit import openings as op
    r = rng(cfg["seed"] + 202)
    n = 0
    for d in doors:
        keep = 0.45 if d["tag"] == "entry" else 0.06         # saqueo: casi todas las hojas interiores arrancadas (queda el vano)
        if r.random() > keep:
            if d["tag"] != "open":                           # el marco se queda (los vanos de paso abiertos no llevan)
                interior.join(door_frame_remnant(d["w"], d["h"], d["t"], seed=int(cfg["seed"] * 997 + n * 13 + int(d["u0"] * 1000))),
                              d["m"] @ _T(d["u0"], 0, 0))
            continue
        M = d["m"] @ _T(d["u0"], 0, 0)
        interior.join(op.door("flush", d["w"], d["h"], d["t"], seed=int(r.integers(0, 10**6)), open_angle=max(80.0, float(r.uniform(0, 95)))), M)   # nunca casi cerrada: se debe poder pasar
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
    # en la losa de azotea el hueco del primer tramo queda abierto: barandal de remate (exterior = +X, el lado del hueco)
    interior.join(circ.railing("tube_metal", 1.4, h=1.0, seed=cfg["seed"] + 9, missing=0.1), _T(st["x0"] + 0.03, st["y0"], zl[-1]) @ ROT_Z90)


def dress_penthouse(cfg, pent, details):
    from kit import openings as op
    mw, d = pent["door"]
    details.join(op.door("metal", d[1] - d[0], d[3] - d[2], INFILL, seed=cfg["seed"] + 77, open_angle=82), mw @ _T(d[0], 0, d[2]))
    me, vents = pent["vents"]
    for i, v in enumerate(vents):
        details.join(op.window("casement", v[1] - v[0], v[3] - v[2], INFILL, seed=cfg["seed"] + 79 + i, broken=1.0, curtain=False),
                     me @ _T(v[0], 0, v[2]))


# ----------------------------------------------------------------------------------------------
# base y entorno inmediato: arena acumulada + hierba seca
# ----------------------------------------------------------------------------------------------
def build_skirt(cfg, mb, margin=3.0, cell=0.25, keep_clear=(), inset=0.15, fill_inside=False, tuft_clear=0.05, caps=(),
                cap_inside=None):
    """Terreno de arena alrededor de la planta: deriva contra los muros (hasta ~0,32 m sobre el desplante, tapando el zócalo),
    ondulación de dunas y borde que muere en z=0. Hierba seca en matas de hojas finas (láminas 'vegetation', DoubleSide),
    más densas junto a los muros y en esquinas. keep_clear: rectángulos (x0, y0, x1, y1) libres de hierba (accesos).
    fill_inside: conserva la arena bajo la planta a z = -0,05 (pisos elevados con duela suelta: no se ve el vacío).
    tuft_clear: distancia mínima de las matas a la planta (las hojas se inclinan hasta ~0,33 m).
    caps: [(x0, x1, y0, y1, zmax)] la arena no sube de zmax ahí (bajo escalones). cap_inside: tope de la arena dentro de la
    planta (bajo pisos elevados y decks). El parche abarca la unión de la planta (porches incluidos) + margin."""
    if not SKIRT_TERRAIN:
        return 0
    import numpy as np
    r = rng(cfg["seed"] + 303)
    xs, ys = cfg["xs"], cfg["ys"]
    fx0, fx1 = xs[0] - COL_CORNER / 2, xs[-1] + COL_CORNER / 2
    fy0, fy1 = ys[0] - COL_CORNER / 2, ys[-1] + COL_CORNER / 2
    for (rx0, rx1, ry0, ry1) in cfg.get("footprint", []):  # porches y alas fuera de la malla: el parche los abarca
        fx0, fx1, fy0, fy1 = min(fx0, rx0), max(fx1, rx1), min(fy0, ry0), max(fy1, ry1)
    X0, X1, Y0, Y1 = fx0 - margin, fx1 + margin, fy0 - margin, fy1 + margin
    nx, ny = int((X1 - X0) / cell) + 1, int((Y1 - Y0) / cell) + 1
    gx = np.linspace(X0, X1, nx)
    gy = np.linspace(Y0, Y1, ny)
    GX, GY = np.meshgrid(gx, gy, indexing="ij")
    rects = cfg.get("footprint", [(fx0, fx1, fy0, fy1)])  # plantas en L: unión de rectángulos
    d = np.full(GX.shape, np.inf)
    inside = np.zeros(GX.shape, dtype=bool)
    for (rx0, rx1, ry0, ry1) in rects:
        dx = np.maximum(np.maximum(rx0 - GX, GX - rx1), 0)
        dy = np.maximum(np.maximum(ry0 - GY, GY - ry1), 0)
        d = np.minimum(d, np.hypot(dx, dy))                # distancia a la planta (0 dentro)
        inside |= (GX > rx0 + inset) & (GX < rx1 - inset) & (GY > ry0 + inset) & (GY < ry1 - inset)
    ph = r.uniform(0, 6.28, 4)
    dune = (0.06 * np.sin(GX * 0.9 + ph[0]) * np.cos(GY * 0.7 + ph[1]) + 0.04 * np.sin(GX * 2.3 + GY * 1.7 + ph[2])
            + 0.025 * np.sin(GX * 5.1 - GY * 4.3 + ph[3]))
    drift = 0.32 * np.exp(-d / 0.9) * (0.7 + 0.3 * np.sin(GX * 1.3 + GY * 0.8 + ph[0]))
    edge = np.clip((margin - d) / 1.2, 0, 1)               # muere en z=0 en el borde del parche
    Z = np.where(inside, -0.05, (drift + dune + 0.03) * edge)
    if cap_inside is not None:
        Z = np.where(d <= 0, np.minimum(Z, cap_inside), Z)
    for (cx0, cx1, cy0, cy1, zmax) in caps:
        Z = np.where((GX >= cx0) & (GX <= cx1) & (GY >= cy0) & (GY <= cy1), np.minimum(Z, zmax), Z)
    # malla en rejilla; se omiten las celdas totalmente dentro de la planta (bajo el edificio)
    vid = {}
    def V(i, j):
        if (i, j) not in vid:
            vid[(i, j)] = mb.bm.verts.new((float(GX[i, j]), float(GY[i, j]), float(Z[i, j])))
        return vid[(i, j)]
    for i in range(nx - 1):
        for j in range(ny - 1):
            if not fill_inside and inside[i, j] and inside[i + 1, j] and inside[i, j + 1] and inside[i + 1, j + 1]:
                continue
            mb.face([V(i, j), V(i + 1, j), V(i + 1, j + 1), V(i, j + 1)], "sand")
    # hierba seca
    def zat(x, y):
        i = int(round((x - X0) / cell)); j = int(round((y - Y0) / cell))
        return float(Z[min(max(i, 0), nx - 1), min(max(j, 0), ny - 1)])
    n_tufts = 0
    for _ in range(4000):
        x, y = float(r.uniform(X0 + 0.3, X1 - 0.3)), float(r.uniform(Y0 + 0.3, Y1 - 0.3))
        dd = min(math.hypot(max(rx0 - x, x - rx1, 0), max(ry0 - y, y - ry1, 0)) for (rx0, rx1, ry0, ry1) in rects)
        if dd <= tuft_clear or any(k[0] <= x <= k[2] and k[1] <= y <= k[3] for k in keep_clear):
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
    k_frame = cull_components(frame, [vol], mode="center") + cull_faces(frame, [vol])
    k_tiles = cull_faces(tiles, [vol])
    roof.join(frame, _T(0, 0, z0))
    roof.join(tiles, _T(0, 0, z0))
    # canalones solo en los aleros delantero y trasero (los de las limatesas laterales se perdieron) + 4 bajantes
    ex, ey = W / 2 + ROOF_OVH, D / 2 + ROOF_OVH
    ze = rf.roof_top("hip", W, D, ROOF_PITCH, ROOF_OVH, x=0.0, y=-ey + 0.01)
    off = 0.0865
    gx, gy = ex - 0.15, ey + off
    xo = 6.6
    tops = []
    for side, path, outs in (("front", [(-gx, -gy, ze - 0.06), (gx, -gy, ze - 0.06)], [gx - xo, gx + xo]),
                             ("back", [(gx, gy, ze - 0.06), (-gx, gy, ze - 0.06)], [gx - xo, gx + xo])):
        g = circ.gutter([Vector(p) for p in path], seed=seed + (1 if side == "front" else 2), outlets=outs, dirt=False,
                        hanger_step=1.0, fault="fallen" if side == "back" else "none")
        roof.join(g, _T(0, 0, z0))
        if hasattr(g, "meta") and "outlets" in g.meta:
            tops += [Vector(t) + Vector((0, 0, z0)) for t in g.meta["outlets"]]
    yf = cfg["ys"][0] - (COL / 2 - RECESS)          # cara del relleno de fachada
    for i, t in enumerate(tops):
        if t.y < 0:
            details.join(circ.downpipe(t, Vector((t.x, yf - 0.06, 0.05)), wall_offset=0.06, seed=seed + 10 + i))
        else:
            R = _rot_z(180)
            tl = R.inverted() @ t
            details.join(circ.downpipe(tl, Vector((tl.x, yf - 0.06, 0.05)), wall_offset=0.06, seed=seed + 10 + i), R)
    return dict(spot=spot, culled_frame=k_frame, culled_tiles=k_tiles, downpipes=len(tops))
def _panel(placed, side, level, bay):
    for p in placed[side]:
        if p["level"] == level and p["bay"] == bay:
            return p
    raise KeyError((side, level, bay))


def ac_base(mb, o, kind, default=0.32):
    """Cota (sobre el piso del panel) del equipo de A/C bajo una ventana: su parte de arriba queda 6 cm bajo la nariz del
    alféizar (auditoría 2026-11-19: el condensador de services ya mide ~0,8 m y atravesaba el alféizar). Los de ventana
    ('box_old', 'window') van en su hueco: se respeta `default`."""
    if kind in ("box_old", "window") or o[2] <= 0.05:
        return default
    ztop = max(v.co.z for v in mb.bm.verts)
    return max(0.02, min(default, o[2] - 0.04 - 0.06 - ztop))


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
        u = sv.ac_unit(kind, seed=int(r.integers(1e6)), detail=det)
        add("ac_" + kind, u, p["m"] @ _T((o[0] + o[1]) / 2, 0, ac_base(u, o, kind)))
    # acometida aérea por la banda de viga de PB (frente) + medidores y conduit junto al vestíbulo
    yb = cfg["ys"][0] - COL / 2 - 0.012            # cara de columna: pasa por delante de los letreros, no a través
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
        sw = min(2.6 if bay == 1 else 2.2, p["L"] - 0.3)         # el de la crujía este libra la bajante (x 6,6)
        add("sign_torn", sv.sign_torn(w=sw, h=0.42, seed=int(r.integers(1e6)), detail=detail_near),
            p["m"] @ _T(p["L"] / 2 - (0.12 if bay == 3 else 0.0), -0.03, p["H"] + 0.04))
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
    # parabólica en el muro este del casetón, bajo las ventilas (en el muro sur quedaba dentro del techo de teja)
    add("satellite_dish", sv.satellite_dish(seed=int(r.integers(1e6)), detail=detail_far),
        _T(7.2 + (COL / 2 - RECESS), 1.15, zl[-1] + 1.15) @ _rot_z(90))
    return n


def dress_damage(cfg, shell, details, interior, skirt, detail="high"):
    """Daño concentrado en la fachada oeste (la 'muy dañada') + varillas de espera + escombro y trozos (R-AAA: detalle 'high',
    varilla corrugada real, trozos con caras de fractura rugosas, blocks y lajas en el escombro)."""
    from kit import damage as dm
    r = rng(cfg["seed"] + 606)
    zl = level_z(cfg)
    n = {}
    def add(key, mb, M, target):
        target.join(mb, M)
        n[key] = n.get(key, 0) + 1
    # (las columnas y vigas con mordidas se arman en build_frame, integradas: ver cfg['spalls'])
    # varillas de espera: castillos en las 4 esquinas de la azotea del casetón + ruinas de una ampliación demolida atrás
    # (sobre las columnas del casetón, desde la losa: antes se apoyaban en la corona del pretil y flotaban sobre la losa)
    for (xx, yy) in ((3.6, -1.75), (7.15, -1.75), (3.6, 1.75), (7.15, 1.75)):
        add("rebar_nest", dm.rebar_nest(seed=int(r.integers(1e6)), n=int(r.integers(4, 8)), length=0.7, stump=(0.25, 0.25, 0.45), detail=detail),
            _T(xx, yy, zl[-1] + PENT_H), details)
    for (xx, yy) in ((-6.0, 8.6), (-2.4, 8.6), (1.2, 8.6), (-6.0, 11.0), (-2.4, 11.0), (1.2, 11.0)):
        add("rebar_nest", dm.rebar_nest(seed=int(r.integers(1e6)), n=int(r.integers(5, 9)), length=float(r.uniform(0.6, 1.1)),
                                        stump=(0.35, 0.35, float(r.uniform(0.3, 0.9))), detail=detail), _T(xx, yy, 0.0), skirt)
    # escombro: al pie de la fachada oeste, en el local oeste (PB), en el corredor del 2.º piso y entre las ruinas
    zones = cfg.get("door_zones", [])
    for (xx, yy, zz, rad, tgt) in ((-9.0, -1.5, 0.0, 1.3, skirt), (-4.2, -3.0, zl[0], 0.9, interior), (-5.2, 0.0, zl[2], 0.6, interior),
                                   (-1.0, 9.8, 0.0, 1.1, skirt)):
        sd = int(r.integers(1e6))
        q = nudge(zones, xx, yy, zz, rad * 0.85)
        if q is not None:
            add("rubble_pile", dm.rubble_pile(radius=rad, seed=sd, n=int(rad * 40), detail=detail), _T(q[0], q[1], zz), tgt)
    # trozos sueltos al pie de los muros
    for _ in range(18):
        xx, yy = float(r.uniform(-9.5, -7.5)), float(r.uniform(-5.5, 5.5))
        size, sd, rz = float(r.uniform(0.12, 0.45)), int(r.integers(1e6)), float(r.uniform(0, 360))
        if clear_of(zones, xx, yy, 0.0, size / 2):
            add("chunk", dm.chunk(size=size, seed=sd, detail=detail), _T(xx, yy, 0.0) @ _rot_z(rz), skirt)
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
    dmg_shell = MB()
    build_frame(cfg, shell, spall_mb=dmg_shell if dress else None)
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
    cfg["door_zones"] = door_zones(cfg, [p for L in placed.values() for p in L], doors)
    out["stats_skirt"] = build_skirt(cfg, sk, margin=3.0, keep_clear=(lobby, rear), caps=door_caps(cfg))
    if dress:
        dmg_det, dmg_int = MB(), MB()
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
