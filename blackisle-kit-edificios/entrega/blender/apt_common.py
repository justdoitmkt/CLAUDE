"""apt_common.py — piezas compartidas por los constructores APT_B / APT_C / APT_D (APT_A conserva su código aprobado).

- panel(): muro de relleno entre las columnas de CUALQUIER línea de la malla (no solo el perímetro), con varios vanos
  posicionados por fracción del claro. Sirve para galerías (muro de los departamentos en la segunda línea), retornos y
  testeros, y para alas de un plan en L (cada ala con su propia malla).
- dress_panel(): viste los vanos de un panel con las piezas del kit según el tipo de vano.
- rail_along(): barandal entre dos puntos alineados a X o Y con el lado exterior indicado.
- stair_core(): escalera en U girada (tramos a lo largo de X o de Y) con la comprobación de huella.
"""
import math

import bpy  # noqa: F401
from mathutils import Matrix

import apt_builder as ab
from apt_builder import BEAM_D, COL, INFILL, RECESS, _T, bay_span, col_size, level_z, m_wall_x, m_wall_y
from kit.common import rng, wall_with_openings

OPENING = dict(ab.OPENING)
OPENING.update({
    # tipo: (ancho, alto, antepecho)
    "door_apt": (0.9, 2.1, 0.0), "hall_door": (1.2, 2.2, 0.0), "portico": (1.8, 2.4, 0.0),
    "window_narrow": (0.8, 1.6, 0.6), "window_wide": (2.0, 1.3, 0.9), "window_stair": (1.0, 0.6, 1.75),
    "door_balcony": (1.0, 2.1, 0.0), "gallery_end": None, "solid": None, "open": None,
})


def _rot_z(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Z")


def line_geom(cfg, side, line):
    """Coordenadas de la línea `line` de la malla para una cara que mira hacia `side`: (coords del claro, tamaños de columna,
    coordenada de la cara exterior del relleno)."""
    xs, ys = cfg["xs"], cfg["ys"]
    if side in ("front", "back"):
        sizes = [col_size(i, line, cfg) for i in range(len(xs))]
        face = ys[line] + (-1 if side == "front" else 1) * (COL / 2 - RECESS)
        return xs, sizes, face
    sizes = [col_size(line, j, cfg) for j in range(len(ys))]
    face = xs[line] + (-1 if side == "west" else 1) * (COL / 2 - RECESS)
    return ys, sizes, face


def panel_matrix(side, a0, a1, face, z0, d=0.0):
    """Matriz local del muro (u a lo largo del claro, mirando desde afuera de izquierda a derecha; v = z; y = espesor hacia adentro)."""
    if side == "front":
        return m_wall_x(a0, face + d, z0, +1)
    if side == "back":
        return m_wall_x(a1, face - d, z0, -1)
    if side == "west":
        return m_wall_y(a1, face + d, z0, +1)
    return m_wall_y(a0, face - d, z0, -1)


def layout_openings(kinds, L, H):
    """kinds = [(tipo, fracción del claro)] -> [(tipo, (u0, u1, v0, v1))] sin traslapes (separación mínima 0,25)."""
    out = []
    last = 0.0
    for kind, frac in kinds:
        op = OPENING.get(kind)
        if op is None:
            continue
        w, h, sill = op
        w = min(w, L - 0.3)
        h = min(h, H - sill - 0.1) if sill > 0 else min(h, H - 0.05)
        u0 = min(max(frac * L - w / 2, max(0.15, last + 0.25 if out else 0.15)), L - 0.15 - w)
        if out and u0 < last + 0.12:                      # no cabe junto al anterior: se omite (avisa)
            print(f"[panel] AVISO: vano {kind} omitido (claro {L:.2f} m)", flush=True)
            continue
        out.append((kind, (round(u0, 4), round(u0 + w, 4), round(sill, 4), round(sill + h, 4))))
        last = u0 + w
    return out


def panel(cfg, mb, side, line, bay, lv, kinds, H=None, d=0.0, z0=None, mat="plaster", collect=None, tag=""):
    """Muro de relleno de la crujía `bay` sobre la línea `line` (índice de malla) en el nivel `lv`, con la cara exterior
    hacia `side`. kinds: [(tipo, fracción)]; H: alto libre (por defecto, de losa a fondo de viga); d: rehundido."""
    coords, sizes, face = line_geom(cfg, side, line)
    a0, a1 = bay_span(coords, bay, sizes)
    L = a1 - a0
    zl = level_z(cfg)
    z0 = zl[lv] if z0 is None else z0
    H = cfg["h"][lv] - BEAM_D if H is None else H
    ops = layout_openings(kinds, L, H)
    m = panel_matrix(side, a0, a1, face, z0, d)
    wall_with_openings(mb, L, H, INFILL, [o for _, o in ops], mat_out=mat, mat_in="plaster", mat_reveal="concrete", m=m)
    p = dict(side=side, line=line, bay=bay, level=lv, a0=a0, a1=a1, L=L, z0=z0, H=H, face=face, recess=d, m=m, ops=ops, tag=tag)
    if collect is not None:
        collect.append(p)
    return p


def dress_panel(p, details, interior, r, primary=False, depth=INFILL):
    """Coloca ventanas, puertas, cortinas metálicas, rejas y celosías en los vanos del panel. Devuelve el número de piezas."""
    from kit import openings as op
    n = 0
    for kind, (u0, u1, v0, v1) in p["ops"]:
        w, h = u1 - u0, v1 - v0
        M = p["m"] @ _T(u0, 0, v0)
        seed = int(r.integers(0, 10**6))
        if kind in ("window", "window_small", "window_wide"):
            roll = r.random()
            k = "boarded" if roll < 0.18 else ("casement" if kind == "window_small" and roll < 0.45 else "sliding")
            details.join(op.window(k, w, h, depth, seed=seed, broken=float(r.uniform(0.55, 1.0)), curtain=primary or r.random() < 0.4), M)
            if k != "boarded" and r.random() < 0.15:
                details.join(op.security_grille(w, h, seed=seed + 1), M)
        elif kind == "window_narrow":
            k = "boarded" if r.random() < 0.6 else "shutter"
            details.join(op.window(k, w, h, depth, seed=seed, broken=float(r.uniform(0.6, 1.0)), curtain=False), M)
        elif kind in ("vent", "window_stair"):
            details.join(op.window("casement", w, h, depth, seed=seed, broken=1.0, curtain=False), M)
        elif kind == "window_high":
            details.join(op.window("sliding", w, h, depth, seed=seed, broken=float(r.uniform(0.6, 1.0)), curtain=False), M)
            if r.random() < 0.6:
                details.join(op.security_grille(w, h, seed=seed + 1), M)
        elif kind == "loggia":
            details.join(op.window("sliding", w, h, depth, seed=seed, broken=float(r.uniform(0.5, 1.0)), curtain=True, sill=False), M)
        elif kind in ("lobby", "portico", "lobby_door"):
            details.join(op.door("double_glazed", w, h, depth, seed=seed, open_angle=float(r.uniform(15, 70))), M)
        elif kind in ("door_rear", "door_service", "hall_door"):
            details.join(op.door("metal", w, h, depth, seed=seed, open_angle=float(r.uniform(0, 80))), M)
        elif kind in ("door_apt", "door_balcony"):
            if r.random() < 0.7:          # muchas hojas arrancadas: queda el vano
                details.join(op.door("flush", w, h, depth, seed=seed, open_angle=float(r.uniform(0, 95))), M)
        elif kind == "shutter":
            details.join(op.rolling_shutter(w, h, seed=seed, dent=float(r.uniform(0.4, 0.9)),
                                            open_frac=float(r.choice([0.0, 0.0, 0.35]))), M)
        elif kind == "breeze":
            details.join(op.breeze_block_screen(w, h, seed=seed, pattern="cross", bevel=0.0, y0=0.025,
                                                missing=float(r.uniform(0.04, 0.12))), M)
        else:
            continue
        n += 1
    return n


def rail_along(details, kind, p0, p1, z, outside, seed, h=1.0, bend=0.0, missing=0.1):
    """Barandal recto de p0 a p1 (alineados a X o a Y) a la cota z. outside: '-y' | '+y' | '-x' | '+x' (lado exterior)."""
    from kit import circulation as circ
    (x0, y0), (x1, y1) = p0, p1
    if abs(y1 - y0) < 1e-6:
        L = abs(x1 - x0)
        if outside == "-y":
            M = _T(min(x0, x1), y0, z)
        else:
            M = _T(max(x0, x1), y0, z) @ _rot_z(180)
    else:
        L = abs(y1 - y0)
        if outside == "+x":
            M = _T(x0, min(y0, y1), z) @ _rot_z(90)
        else:
            M = _T(x0, max(y0, y1), z) @ _rot_z(-90)
    details.join(circ.railing(kind, L, h=h, seed=seed, bend=bend, missing=missing), M)
    return L


def stair_kw(cfg, lv, width, landing, gap=0.10, going=0.28, top=False):
    fh = cfg["h"][lv]
    return dict(width=width, floor_h=fh, landing_depth=landing, gap=gap, seed=cfg["seed"] * 10 + lv, broken=0.05,
                rail="tube_metal", debris=(lv == 0 or top), going=going)


def stair_core(cfg, interior, origin, axis, width, landing, levels, gap=0.10, going=0.28, limit=None):
    """Escalera en U de cada nivel de `levels` (de lv a lv+1). axis: '+x' (tramos a lo largo de +X, el ancho crece hacia +Y,
    como APT_A) o '+y' (tramos hacia +Y, el ancho crece hacia -X). origin = esquina de arranque (x, y) en planta.
    limit = (largo, ancho) disponibles: se verifica la huella."""
    from kit import circulation as circ
    zl = level_z(cfg)
    R = Matrix() if axis == "+x" else _rot_z(90)
    fps = []
    for lv in levels:
        kw = stair_kw(cfg, lv, width, landing, gap, going, top=(lv == levels[-1]))
        fp = circ.stair_u_footprint(width=width, floor_h=kw["floor_h"], landing_depth=landing, gap=gap, going=going)
        if limit is not None:
            assert fp["L"] <= limit[0] + 0.003 and fp["W"] <= limit[1] + 0.003, (lv, fp, limit)
        interior.join(circ.stair_u(**kw), _T(origin[0], origin[1], zl[lv]) @ R)
        fps.append(fp)
    return fps


def counter(n, key, k=1):
    n[key] = n.get(key, 0) + k


def cull_pred(mb, fn):
    """Quita las caras de un MB cuyo centro cumple fn(Vector) (limahoyas, chimeneas, volúmenes ocultos)."""
    import bmesh
    kill = [f for f in mb.bm.faces if fn(f.calc_center_median())]
    bmesh.ops.delete(mb.bm, geom=kill, context="FACES")
    return len(kill)


def downpipe_on(det, top, side, wall, seed, offset=0.06):
    """Bajante desde `top` (salida del canalón, mundo) hasta el suelo, pegada al muro de la fachada `side` cuya cara está en
    la coordenada `wall` (y para front/back, x para west/east). Se construye en el marco local de downpipe (muro hacia +Y)."""
    from kit import circulation as circ
    from mathutils import Vector
    R = {"front": Matrix(), "back": _rot_z(180), "west": _rot_z(-90), "east": _rot_z(90)}[side]
    Ri = R.inverted()
    tl = Ri @ Vector(top)
    wp = Vector((top[0], wall, 0.0)) if side in ("front", "back") else Vector((wall, top[1], 0.0))
    wl = Ri @ wp
    det.join(circ.downpipe(tl, Vector((tl.x, wl.y - offset, 0.05)), wall_offset=offset, seed=seed), R)
