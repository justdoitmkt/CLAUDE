"""apt_b.py — APT_B_4p: bloque de galería de acceso (PB + 3 pisos), concepto aprobado hero 8ac1d4d9 / trasera 1c3e07c8.

Malla 4 x 3 crujías: xs = -7,2 … 7,2 (3,6) · ys = -5,7 | -4,2 | 0 | 4,2 (la primera crujía, 1,5 m, es la GALERÍA).
- Galería en voladizo aparente sobre columnas de borde (y = -5,7) en los pisos 1–3, con balaustrada de concreto; el muro de
  los departamentos va en la segunda línea (y = -4,2). La crujía oeste se cierra hasta la línea de galería (testero ciego
  con ventanas angostas, como en el concepto) y su departamento se entra por el retorno lateral desde la galería.
- PB cerrada hasta la línea de galería: pórtico de acceso con marquesina (crujía 2), locales, bodega con WC.
- Núcleo de escalera INTERIOR en la mitad trasera de la crujía 2 (tramos a lo largo de +Y, ancho 1,0); pasillo de servicio
  al oeste del núcleo hasta la puerta trasera de PB. Sin casetón: la escalera termina en el piso 3 (barandal de remate).
- 3 departamentos pasantes por piso (crujías 0, 1 y 3) con estancia al frente, baño + cocina al centro y recámara atrás.
- Colapso en la esquina superior SO (concepto): columnas de galería truncadas en el piso 3, vigas y losa de azotea perdidas
  sobre la galería de las crujías 0–1, muros rotos, techo arrancado en esa esquina, varillas, escombro en galería y suelo.
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
from apt_builder import (BEAM_W, COL, COL_CORNER, GROUND, INFILL, RECESS, SLAB, _T, level_z,  # noqa: E402
                         partition)
from kit.common import MB, rng  # noqa: E402

STAIR_W, STAIR_LANDING = 1.0, 1.3
STAIR_Y0 = 0.53                               # el descanso de media planta llega a 2 mm del muro trasero
COLLAPSE = (-7.75, -1.6, -6.1, -4.35)        # planta (x0, x1, y0, y1) sin losa de azotea


def cfg_apt_b():
    xs = [-7.2, -3.6, 0.0, 3.6, 7.2]
    ys = [-5.7, -4.2, 0.0, 4.2]
    h = [3.2, 2.9, 2.9, 2.9]
    zl = [GROUND]
    for hh in h:
        zl.append(zl[-1] + hh)
    # núcleo: arranque en la esquina SE de la mitad trasera de la crujía 2 (cara de columna x 3,425; y 0,30)
    sw = 2 * STAIR_W + 0.10
    stair = dict(x0=3.425 - sw, y0=STAIR_Y0, w=sw, l=3.543, origin=(3.425, STAIR_Y0))

    def skip_beam(k, ax, i, j):
        if k != len(h):
            return False
        return (ax == "x" and j == 0 and i in (0, 1)) or (ax == "y" and j == 0 and i in (0, 1))

    return dict(id="APT_B_4p", xs=xs, ys=ys, h=h, stair=stair, seed=23, loggia_depth=0.0, lookdev=dict(under="brick"),
                stair_levels={1, 2, 3}, holes={len(h): [COLLAPSE]}, skip_beam=skip_beam,
                col_top={(0, 0): zl[3] + 1.25, (1, 0): zl[3] + 1.9})


# ----------------------------------------------------------------------------------------------
# fachadas
# ----------------------------------------------------------------------------------------------
def build_facades(cfg, shell):
    """Todos los muros de relleno exteriores. Devuelve la lista de paneles (para vestir y para el grafiti)."""
    P = []
    pan = lambda *a, **k: ac.panel(cfg, shell, *a, collect=P, **k)
    top = len(cfg["h"]) - 1
    # FRENTE ---------------------------------------------------------------------------------
    for b, kinds in enumerate(([("door_service", 0.3)], [("window_high", 0.5)], [("portico", 0.5)], [("shutter", 0.5)])):
        pan("front", 0, b, 0, kinds, tag="pb")
    for lv in range(1, top + 1):
        if lv == top:                                   # testero colapsado: queda un pretil roto de ~1 m
            pan("front", 0, 0, lv, [], H=1.05, tag="broken")
        else:
            pan("front", 0, 0, lv, [("window_narrow", 0.5)])
        pan("front", 1, 1, lv, [("door_apt", 0.22), ("window", 0.68)], tag="gallery")
        pan("front", 1, 2, lv, [("hall_door", 0.3), ("window_small", 0.8)], tag="gallery")
        pan("front", 1, 3, lv, [("window", 0.32), ("door_apt", 0.78)], tag="gallery")
        pan("east", 1, 0, lv, [("door_apt", 0.5)], tag="gallery_return")   # retorno: entrada del depto oeste
    # TRASERA (fracciones medidas desde el ESTE: así se ve desde afuera) -----------------------
    for b, kinds in enumerate(([("window_small", 0.35)], [("window_small", 0.5)], [("door_service_n", 0.84)], [("window_high", 0.5)])):
        pan("back", 3, b, 0, kinds, tag="pb")
    for lv in range(1, top + 1):
        pan("back", 3, 0, lv, [("window", 0.5)])
        pan("back", 3, 1, lv, [("window", 0.4)])
        pan("back", 3, 2, lv, [("window_stair", 0.3), ("window_narrow", 0.86)])
        pan("back", 3, 3, lv, [("window", 0.6)])
    # OESTE (u de norte a sur) -----------------------------------------------------------------
    pan("west", 0, 0, 0, [], tag="pb")
    pan("west", 0, 1, 0, [("window_high", 0.5)], tag="pb")
    pan("west", 0, 2, 0, [("window_high", 0.75)], tag="pb")
    for lv in range(1, top + 1):
        if lv == top:
            pan("west", 0, 0, lv, [], H=0.8, tag="broken")
        else:
            pan("west", 0, 0, lv, [("window_narrow", 0.5)])
        pan("west", 0, 1, lv, [("window", 0.66)])
        pan("west", 0, 2, lv, [("window_small", 0.27)])
    # ESTE (u de sur a norte); la crujía de galería queda abierta en los pisos -----------------
    pan("east", 4, 0, 0, [], tag="pb")
    pan("east", 4, 1, 0, [("window_high", 0.5)], tag="pb")
    pan("east", 4, 2, 0, [("vent", 0.3), ("window_small", 0.72)], tag="pb")
    for lv in range(1, top + 1):
        pan("east", 4, 1, lv, [("window", 0.5)])
        pan("east", 4, 2, lv, [("window_small", 0.72)])
    return P


def build_portico(cfg, shell, P):
    """Marquesina de concreto sobre el acceso de PB (2 postes, losa con pretil bajo y gotero) y escalón de llegada."""
    p = next(q for q in P if q["side"] == "front" and q["level"] == 0 and q["bay"] == 2)
    _, (u0, u1, v0, v1) = p["ops"][0]
    x0, x1 = p["a0"] + u0 - 0.45, p["a0"] + u1 + 0.45
    yf = p["face"]
    yo = yf - 1.15
    z0 = GROUND + v1 + 0.25
    shell.box((x0, yo, z0), (x1, yf, z0 + 0.14), "concrete", bevel=0.012, seg=2)
    for (a, b) in (((x0, yo), (x1, yo + 0.08)), ((x0, yo + 0.08), (x0 + 0.08, yf)), ((x1 - 0.08, yo + 0.08), (x1, yf))):
        shell.box((a[0], a[1], z0 + 0.14), (b[0], b[1], z0 + 0.32), "concrete", bevel=0.008, seg=1)
    for x in (x0 + 0.12, x1 - 0.12):
        shell.box((x - 0.09, yo + 0.04, GROUND), (x + 0.09, yo + 0.22, z0), "concrete", bevel=0.01, seg=1)
    shell.box((x0 - 0.1, yo - 0.25, 0.0), (x1 + 0.1, yf, GROUND), "concrete", bevel=0.01, seg=1)
    return dict(x0=x0, x1=x1, yo=yo, z=z0)


# ----------------------------------------------------------------------------------------------
# interior
# ----------------------------------------------------------------------------------------------
def build_interior(cfg, mb, out):
    zl = level_z(cfg)
    xin0, xin1, yin0, yin1 = ab.inner_faces(cfg)
    st = cfg["stair"]
    xs_part = st["x0"] - 0.075                      # muro entre núcleo y pasillo de servicio (cara a 2,5 cm del tramo)
    for lv in range(len(cfg["h"])):
        z0 = zl[lv]
        H = cfg["h"][lv] - SLAB
        partition(mb, (xs_part, st["y0"]), (xs_part, yin1), z0, H)                     # núcleo | pasillo de servicio
        if lv == 0:
            partition(mb, (0.0, yin0), (0.0, yin1), z0, H, t=0.15)                    # locales oeste | vestíbulo
            partition(mb, (3.6, yin0), (3.6, yin1), z0, H, t=0.15, doors=[(-3.0, 0.9)], out=out)   # vestíbulo | local este
            partition(mb, (xin0, -0.8), (-0.075, -0.8), z0, H, doors=[(-3.0, 1.0)], out=out)
            partition(mb, (-3.6, -0.8), (-3.6, yin1), z0, H, doors=[(1.6, 0.9)], out=out)
            partition(mb, (xin0, 2.6), (-5.6, 2.6), z0, H, doors=[(-6.4, 0.7)], out=out)
            partition(mb, (-5.6, 2.6), (-5.6, yin1), z0, H)
            partition(mb, (3.675, 0.0), (xin1, 0.0), z0, H, doors=[(5.4, 0.9)], out=out)
            continue
        yf = cfg["ys"][1] - (COL / 2 - RECESS) + INFILL                               # cara interior del muro de galería
        for x in (0.0, 3.6):
            partition(mb, (x, yf), (x, yin1), z0, H, t=0.15)                          # muros del núcleo / medianeras
        partition(mb, (-3.6, yf - 0.05), (-3.6, yin1), z0, H)                          # medianera deptos oeste | centro
        partition(mb, (0.075, st["y0"] - 0.05), (xs_part + 0.05, st["y0"] - 0.05), z0, H, doors=[(0.65, 0.8)], out=out)
        # depto centro (crujía 1)
        partition(mb, (-3.55, -0.4), (-0.075, -0.4), z0, H, doors=[(-1.0, 0.8)], out=out, tag="entry")
        partition(mb, (-2.0, -0.4), (-2.0, 1.6), z0, H, doors=[(0.6, 0.7)], out=out)
        partition(mb, (-3.55, 1.6), (-0.075, 1.6), z0, H, doors=[(-1.0, 0.8)], out=out)
        # depto este (crujía 3)
        partition(mb, (3.675, -0.4), (xin1, -0.4), z0, H, doors=[(4.6, 0.8)], out=out, tag="entry")
        partition(mb, (5.6, -0.4), (5.6, 1.6), z0, H, doors=[(0.6, 0.7)], out=out)
        partition(mb, (3.675, 1.6), (xin1, 1.6), z0, H, doors=[(4.6, 0.8)], out=out)
        # depto oeste (crujía 0, llega a la línea de galería)
        partition(mb, (xin0, -1.6), (-3.65, -1.6), z0, H, doors=[(-4.4, 0.8)], out=out, tag="entry")
        partition(mb, (-5.6, -1.6), (-5.6, 0.8), z0, H, doors=[(-0.4, 0.7)], out=out)
        partition(mb, (xin0, 0.8), (-3.65, 0.8), z0, H, doors=[(-4.4, 0.8)], out=out)
    return mb


# ----------------------------------------------------------------------------------------------
# vestido
# ----------------------------------------------------------------------------------------------
def dress(cfg, P, det, inter, doors, portico):
    from kit import circulation as circ
    r = rng(cfg["seed"] + 101)
    zl = level_z(cfg)
    xs, ys = cfg["xs"], cfg["ys"]
    stats = dict(openings=sum(ac.dress_panel(p, det, inter, r, primary=p["side"] == "front") for p in P))
    stats["interior_doors"] = ab.dress_interior_doors(cfg, doors, inter)
    st = cfg["stair"]
    fps = ac.stair_core(cfg, inter, st["origin"], "+y", STAIR_W, STAIR_LANDING, levels=list(range(len(cfg["h"]) - 1)),
                        limit=(4.075 - st["y0"], st["w"]))
    stats["stair_L"] = round(fps[0]["L"], 3)
    # barandal de remate del hueco en el último piso (el tramo de subida queda abierto)
    top = len(cfg["h"]) - 1
    ac.rail_along(inter, "tube_metal", (st["origin"][0] - STAIR_W, st["y0"]), (st["origin"][0], st["y0"]), zl[top], "+y",
                  seed=cfg["seed"] + 5, missing=0.15)
    # balaustrada de galería (pisos 1–3), testero este abierto
    ya = ys[0] - BEAM_W / 2 + 0.10
    n_rail = 0
    bal_seg, circ.BAL_SEG = circ.BAL_SEG, 8          # fuste de 8 lados: la galería se ve a > 8 m
    for lv in range(1, top + 1):
        for b in (1, 2, 3):
            a0 = xs[b] + ab.col_size(b, 0, cfg) / 2
            a1 = xs[b + 1] - ab.col_size(b + 1, 0, cfg) / 2
            if lv == top and b == 1:              # tramo bajo el colapso: queda la mitad este, rota
                a0 = -1.55
            bend = 0.18 if (lv == top and b == 1) or r.random() < 0.15 else 0.0
            ac.rail_along(det, "baluster_concrete", (a0, ya), (a1, ya), zl[lv], "-y", seed=int(r.integers(1e6)), bend=bend,
                          missing=float(r.uniform(0.04, 0.16)))
            n_rail += 1
        xe = xs[-1] + BEAM_W / 2 - 0.10
        ac.rail_along(det, "baluster_concrete", (xe, ys[0] + COL_CORNER / 2), (xe, ys[1] - COL / 2), zl[lv], "+x",
                      seed=int(r.integers(1e6)), missing=0.08)
        n_rail += 1
    circ.BAL_SEG = bal_seg
    stats["rails"] = n_rail
    return stats


def dress_roof(cfg, roof, det):
    """Techo a cuatro aguas sobre toda la planta (incluida la galería) con la esquina SO arrancada."""
    from kit import circulation as circ
    from kit import roofing as rf
    xs, ys = cfg["xs"], cfg["ys"]
    W = xs[-1] - xs[0] + COL_CORNER
    D = ys[-1] - ys[0] + COL_CORNER
    yc = (ys[0] + ys[-1]) / 2
    z0 = level_z(cfg)[-1]
    seed = cfg["seed"] + 404
    P, O = ab.ROOF_PITCH, ab.ROOF_OVH
    spot = (-4.9, -3.95 , 1.5)                             # sobre el colapso (coordenadas del techo)
    frame = rf.roof_frame("hip", W, D, P, O, seed=seed, cover="tile", damage=0.7, spot=spot)
    tiles = rf.barrel_tiles(W, D, "hip", P, O, seed=seed, missing=0.05, hole=spot, detail="low")
    x0, x1, y0, y1 = COLLAPSE
    gone = (x0 - 1.5, y0 - 1.5 - yc, -2.0, x1 - 0.5, y1 + 0.35 - yc, 6.0)   # esquina arrancada (sin muros que la carguen)
    k_frame = ab.cull_components(frame, [gone], mode="center")
    k_tiles = ab.cull_faces(tiles, [gone])
    M = _T(0, yc, z0)
    roof.join(frame, M)
    roof.join(tiles, M)
    # canalones: trasero completo; frontal solo al este del colapso; bajantes por las columnas de galería y la trasera
    ex, ey = W / 2 + O, D / 2 + O
    ze = rf.roof_top("hip", W, D, P, O, x=0.0, y=-ey + 0.01)
    gx, gy = ex - 0.15, ey + 0.0865
    tops = []
    for side, path, outs in (("front", [(-0.6, -gy, ze - 0.06), (gx, -gy, ze - 0.06)], [4.2, 7.8]),
                             ("back", [(gx, gy, ze - 0.06), (-gx, gy, ze - 0.06)], [gx - 3.6, gx + 3.6])):
        g = circ.gutter([Vector(p) for p in path], seed=seed + (1 if side == "front" else 2), outlets=outs, dirt=False,
                        hanger_step=1.0, fault="none" if side == "front" else "sag")
        roof.join(g, M)
        if hasattr(g, "meta") and "outlets" in g.meta:
            tops += [Vector(t) + Vector((0, yc, z0)) for t in g.meta["outlets"]]
    n = 0
    yf = ys[0] - COL_CORNER / 2                           # cara frontal de las columnas de galería (la de esquina es la más saliente)
    yb = ys[-1] + COL / 2                                 # cara exterior de las columnas traseras
    for i, t in enumerate(tops):
        if t.y < 0:
            det.join(circ.downpipe(t, Vector((t.x, yf - 0.06, 0.05)), wall_offset=0.06, seed=seed + 10 + i))
        else:
            R = ac._rot_z(180)
            tl = R.inverted() @ t
            det.join(circ.downpipe(tl, Vector((tl.x, -yb - 0.06, 0.05)), wall_offset=0.06, seed=seed + 10 + i), R)
        n += 1
    return dict(culled_frame=k_frame, culled_tiles=k_tiles, downpipes=n)


def _p(P, side, lv, bay, line=None):
    for q in P:
        if q["side"] == side and q["level"] == lv and q["bay"] == bay and (line is None or q["line"] == line):
            return q
    raise KeyError((side, lv, bay, line))


def dress_services(cfg, P, det, inter, far="low", near="mid"):
    from kit import services as sv
    r = rng(cfg["seed"] + 505)
    zl = level_z(cfg)
    xs, ys = cfg["xs"], cfg["ys"]
    n = {}

    def add(key, mb, M, target=det):
        target.join(mb, M)
        ac.counter(n, key)

    def at_op(p, k=0):
        _, o = p["ops"][k]
        return o
    for side, lv, bay, kind, d in (("back", 1, 0, "split_outdoor", far), ("back", 2, 3, "box_old", far), ("back", 3, 1, "split_outdoor", far),
                                   ("back", 1, 3, "split_outdoor", far), ("west", 2, 1, "split_outdoor", far),
                                   ("east", 1, 1, "box_old", far)):
        p = _p(P, side, lv, bay)
        o = at_op(p)
        add("ac_" + kind, sv.ac_unit(kind, seed=int(r.integers(1e6)), detail=d), p["m"] @ _T((o[0] + o[1]) / 2, 0, 0.32))
    # galería: condensadoras junto a las puertas, tendederos entre columnas, arbotantes en columnas
    for lv, bay in ((1, 3), (2, 1)):
        p = _p(P, "front", lv, bay, line=1)
        o = at_op(p, 0 if bay == 3 else 1)
        add("ac_split_outdoor", sv.ac_unit("split_outdoor", seed=int(r.integers(1e6)), detail=near), p["m"] @ _T((o[0] + o[1]) / 2, 0, 0.30))
    yl = ys[0] + 0.10                                     # dentro del canto de la columna: las armellas entran en ella
    for lv, bay in ((1, 1), (2, 3), (3, 3)):
        a0 = xs[bay] + COL / 2
        L = (xs[bay + 1] - ab.col_size(bay + 1, 0, cfg) / 2) - a0
        add("laundry_line", sv.laundry_line(length=L, seed=int(r.integers(1e6)), detail=near), _T(a0, yl, zl[lv] + 1.95))
    for lv, x in ((1, 0.0), (2, 3.6), (3, 0.0)):
        add("light_fixture", sv.light_fixture("bracket", seed=int(r.integers(1e6)), detail=near),
            _T(x, ys[0] + COL / 2, zl[lv] + 2.0) @ ac._rot_z(180))
    # acometida por la viga de PB del frente, medidores y conduit junto al pórtico, letrero sobre la cortina del local
    yb = ys[0] - BEAM_W / 2 - 0.005
    zc = zl[1] - 0.30
    add("cable_bundle", sv.cable_bundle([(-7.0, yb, zc), (-3.6, yb, zc + 0.05), (0.2, yb, zc)], n=4, sag=0.2, seed=int(r.integers(1e6)),
                                        detail=near), Matrix())
    p = _p(P, "front", 0, 1)
    for i, u in enumerate((p["L"] - 0.55, p["L"] - 0.12)):
        add("meter_box", sv.meter_box(seed=int(r.integers(1e6)), open_door=bool(i), detail=near), p["m"] @ _T(u - 0.2, 0, 1.25))
    add("conduit", sv.conduit([(p["L"] - 0.75, 0, 1.78), (p["L"] - 0.75, 0, p["H"] - 0.05)], seed=int(r.integers(1e6)), detail=near), p["m"])
    p = _p(P, "front", 0, 3)
    add("sign_torn", sv.sign_torn(w=min(2.6, p["L"] - 0.3), h=0.42, seed=int(r.integers(1e6)), detail=near),
        p["m"] @ _T(p["L"] / 2, -0.03, p["H"] + 0.04))
    p = _p(P, "back", 0, 2)
    o = at_op(p)
    add("light_fixture", sv.light_fixture("wall", seed=int(r.integers(1e6)), detail=near), p["m"] @ _T((o[0] + o[1]) / 2, 0, o[3] + 0.35))
    # vestíbulo de PB: buzones en el muro oeste (x = 0, cara este); extintores en los vestíbulos de piso
    add("mailboxes", sv.mailboxes(n=9, seed=int(r.integers(1e6)), detail=near), _T(0.075 + 0.001, -3.0, zl[0] + 1.05) @ ac._rot_z(90), inter)
    for lv in (1, 2):
        add("extinguisher_cabinet", sv.extinguisher_cabinet(seed=int(r.integers(1e6)), detail=near),
            _T(3.6 - 0.075 - 0.001, -2.2, zl[lv] + 1.05) @ ac._rot_z(-90), inter)
    # antena sobre la cumbrera y parabólica en una columna de galería
    from kit import roofing as rf
    W = xs[-1] - xs[0] + COL_CORNER
    D = ys[-1] - ys[0] + COL_CORNER
    zr = rf.roof_top("hip", W, D, ab.ROOF_PITCH, ab.ROOF_OVH, x=3.0, y=0.0)
    add("tv_antenna", sv.tv_antenna(seed=int(r.integers(1e6)), detail=far), _T(3.0, (ys[0] + ys[-1]) / 2, level_z(cfg)[-1] + zr + 0.05))
    add("satellite_dish", sv.satellite_dish(seed=int(r.integers(1e6)), detail=far), _T(3.6, ys[0] - COL / 2, zl[3] + 1.9) @ ac._rot_z(0))
    return n


def dress_damage(cfg, shell, det, inter, skirt, detail="low"):
    from kit import damage as dm
    r = rng(cfg["seed"] + 606)
    zl = level_z(cfg)
    xs, ys = cfg["xs"], cfg["ys"]
    n = {}

    def add(key, mb, M, target):
        target.join(mb, M)
        ac.counter(n, key)
    # muñones de las columnas truncadas con varilla expuesta
    for (i, j), z in cfg["col_top"].items():
        s = ab.col_size(i, j, cfg)
        add("rebar_nest", dm.rebar_nest(seed=int(r.integers(1e6)), n=8, length=0.75, stump=(s, s, 0.18), detail=detail),
            _T(xs[i], ys[j], z), det)
    # varillas que asoman del canto roto de la losa de azotea (sobre la galería) y del muro roto
    zt = zl[-1] - SLAB
    for x in (-6.3, -4.6, -2.7):
        add("rebar_nest", dm.rebar_nest(seed=int(r.integers(1e6)), n=5, length=0.55, stump=(0.25, 0.2, 0.12), detail=detail),
            _T(x, COLLAPSE[3] + 0.12, zt) @ ac._rot_z(float(r.uniform(-20, 20))), det)
    # columnas de galería con aristas mordidas
    for (i, lv) in ((2, 1), (3, 2), (4, 1)):
        c = ab.col_size(i, 0, cfg) / 2 + 0.002
        z0 = zl[lv] + 0.25
        mbx = MB()
        dm.spalled_box(mbx, (xs[i] - c, ys[0] - c, z0), (xs[i] + c, ys[0] + c, z0 + 1.5),
                       [dict(axis="z", sides=(-1, int(r.choice([-1, 1]))), start=0.2, length=0.9, depth=0.08, seed=int(r.integers(1e6)))],
                       detail=detail)
        add("spalled_column", mbx, Matrix(), shell)
    # escombro: galería del piso 3 bajo el colapso, cuarto expuesto, pie de la esquina SO, local de PB
    for (x, y, z, rad, tgt) in ((-2.7, -4.95, zl[3], 0.7, det), (-5.4, -4.9, zl[3], 0.9, inter), (-8.7, -6.9, 0.0, 1.5, skirt),
                                (-5.6, -7.6, 0.0, 0.9, skirt), (-4.0, -3.0, zl[0], 0.8, inter)):
        add("rubble_pile", dm.rubble_pile(radius=rad, seed=int(r.integers(1e6)), n=int(rad * 38), detail=detail), _T(x, y, z), tgt)
    for _ in range(22):
        x, y = float(r.uniform(-10.0, -3.0)), float(r.uniform(-8.6, -6.2))
        add("chunk", dm.chunk(size=float(r.uniform(0.12, 0.5)), seed=int(r.integers(1e6)), detail=detail),
            _T(x, y, 0.0) @ ac._rot_z(float(r.uniform(0, 360))), skirt)
    for _ in range(6):                                  # trozos sobre el pretil roto del testero
        x = float(r.uniform(-7.0, -3.8))
        add("chunk", dm.chunk(size=float(r.uniform(0.15, 0.3)), seed=int(r.integers(1e6)), detail=detail),
            _T(x, ys[0] - 0.05, zl[3] + 1.05) @ ac._rot_z(float(r.uniform(0, 360))), det)
    return n


# ----------------------------------------------------------------------------------------------
# ensamblado
# ----------------------------------------------------------------------------------------------
def build_apt_b(collection_root=None, dress_all=True):
    from kit.common import get_collection
    cfg = cfg_apt_b()
    cid = cfg["id"]
    root = collection_root or get_collection(cid)
    cols = {k: get_collection(f"{cid}_{k}", root) for k in ("Shell", "Details", "Interior", "Skirt", "Roof", "Damage")}
    out = {k: [] for k in cols}
    shell = MB()
    ab.build_frame(cfg, shell)
    P = build_facades(cfg, shell)
    portico = build_portico(cfg, shell, P)
    inter = MB()
    doors = []
    build_interior(cfg, inter, doors)
    out["placed"] = P
    stats = {}
    det = MB()
    sk = MB()
    dmg_shell, dmg_det, dmg_int = MB(), MB(), MB()
    if dress_all:
        stats = dress(cfg, P, det, inter, doors, portico)
        roof = MB()
        stats["roof"] = dress_roof(cfg, roof, det)
        out["Roof"].append(roof.finish(f"{cid}_Roof", cols["Roof"], uv_size=2.0, merge=0))
        stats["services"] = dress_services(cfg, P, det, inter)
    out["Shell"].append(shell.finish(f"{cid}_Shell", cols["Shell"], uv_size=3.0, merge=0))
    xs, ys = cfg["xs"], cfg["ys"]
    lobby = (portico["x0"] - 0.3, portico["yo"] - 2.5, portico["x1"] + 0.3, ys[0])
    rear = (0.0, ys[-1], 1.6, ys[-1] + 3.0)
    out["stats_skirt"] = ab.build_skirt(cfg, sk, margin=3.0, keep_clear=(lobby, rear))
    if dress_all:
        stats["damage"] = dress_damage(cfg, dmg_shell, dmg_det, dmg_int, sk)
        out["Details"].append(det.finish(f"{cid}_Details", cols["Details"], uv_size=2.0, merge=0))
        for nm, mbd in (("Damage_Shell", dmg_shell), ("Damage_Details", dmg_det), ("Damage_Interior", dmg_int)):
            if len(mbd.bm.faces):
                out["Damage"].append(mbd.finish(f"{cid}_{nm}", cols["Damage"], uv_size=2.0, merge=0))
    out["Interior"].append(inter.finish(f"{cid}_Interior", cols["Interior"], uv_size=3.0, merge=0))
    out["Skirt"].append(sk.finish(f"{cid}_Skirt", cols["Skirt"], uv_size=2.0, merge=0))
    out["stats"] = stats
    out["cfg"] = cfg
    return out
