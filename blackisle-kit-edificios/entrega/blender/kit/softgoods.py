"""kit/softgoods.py — textiles y acolchados con simulación de tela de Blender (regla R-AAA: lo blando se ve blando).

- pillow(): almohada inflada por presión (cloth + pressure) y asentada por gravedad sobre un plano: costura perimetral, esquinas
  en punta, arrugas radiales.
- mattress(): colchón de hule espuma forrado de vinilo: caja con esquinas redondeadas (subdivisión con aristas de apoyo),
  abombado superior, ribete (vivo) en el perímetro superior e inferior y cierre lateral; opcional quiebre de respaldo (Fowler).
- drape(): tela (sábana, cobija, cortina de camilla) dejada caer sobre colisionadores: la caída y los pliegues salen de la
  simulación, con espesor (solidify) para que sea un sólido cerrado.
- folded_blanket(): cobija doblada en tres con dobleces redondeados y pelusa (ruido) sobre la superficie.
Los resultados de simulación se guardan en cache_tela/ (npz) por parámetros: el modelo se reconstruye idéntico y rápido.
"""
import hashlib
import json
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector, noise

from kit.common import MB

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache_tela")
VERSION = 9


def _key(name, params):
    h = hashlib.sha1(json.dumps([name, VERSION, params], sort_keys=True).encode()).hexdigest()[:16]
    return os.path.join(CACHE, f"{name}_{h}.npz")


def _mesh_arrays(me):
    co = np.array([v.co[:] for v in me.vertices], np.float32)
    faces = [list(p.vertices) for p in me.polygons]
    flat = np.array([i for f in faces for i in f], np.int32)
    lens = np.array([len(f) for f in faces], np.int32)
    return co, flat, lens


def _to_mb(mb, co, flat, lens, mat, M=None):
    vs = [mb.bm.verts.new((M @ Vector(c)) if M is not None else Vector(c)) for c in co]
    mi = mb.mi(mat)
    k = 0
    for n in lens:
        idx = flat[k:k + n]
        k += n
        try:
            f = mb.bm.faces.new([vs[i] for i in idx])
            f.material_index = mi
            f.smooth = True
        except ValueError:
            pass


def _cached(name, params, fn):
    os.makedirs(CACHE, exist_ok=True)
    path = _key(name, params)
    if os.path.exists(path):
        d = np.load(path)
        return d["co"], d["flat"], d["lens"]
    co, flat, lens = fn()
    np.savez_compressed(path, co=co, flat=flat, lens=lens)
    return co, flat, lens


def _new_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _cleanup(objs):
    for o in objs:
        me = o.data
        bpy.data.objects.remove(o)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)


def _simulate(ob, frames):
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, frames
    for md in ob.modifiers:
        if md.type == "CLOTH":
            md.point_cache.frame_start, md.point_cache.frame_end = 1, frames
    for f in range(1, frames + 1):
        sc.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    out = _mesh_arrays(me)
    ev.to_mesh_clear()
    sc.frame_set(1)
    return out


def _collider_box(name, mn, mx, round_r=0.0, segs=2):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]), verts=bm.verts)
    bmesh.ops.translate(bm, vec=((mn[0] + mx[0]) / 2, (mn[1] + mx[1]) / 2, (mn[2] + mx[2]) / 2), verts=bm.verts)
    if round_r > 0:
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=round_r, segments=segs, affect="EDGES", profile=0.5)
    ob = _new_obj(name, bm)
    md = ob.modifiers.new("col", "COLLISION")
    ob.collision.thickness_outer = 0.004
    ob.collision.cloth_friction = 8.0
    del md
    return ob


def _collider_mesh(name, co, flat, lens):
    bm = bmesh.new()
    vs = [bm.verts.new(c) for c in co]
    k = 0
    for n in lens:
        try:
            bm.faces.new([vs[i] for i in flat[k:k + n]])
        except ValueError:
            pass
        k += n
    # normales hacia afuera: la colisión de tela usa el sentido de la cara (con normales invertidas la sábana
    # atravesaba la cara de arriba del colchón y quedaba dentro, apoyada en la de abajo)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    ob = _new_obj(name, bm)
    ob.modifiers.new("col", "COLLISION")
    ob.collision.thickness_outer = 0.004
    ob.collision.cloth_friction = 8.0
    return ob


# ------------------------------------------------------------------------------------------------------------- almohada
def _pillow_sim(w, d, puff, seed):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=(w, d, 0.02), verts=bm.verts)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=14, use_grid_fill=True)
    rr = np.random.default_rng(seed)
    for v in bm.verts:
        v.co.z += float(rr.normal(0, 0.0006))
        v.co.x *= 1.0 + 0.04 * (1 - (2 * v.co.y / d) ** 2) * float(rr.uniform(0.6, 1.0))
    bmesh.ops.translate(bm, vec=(0, 0, 0.06), verts=bm.verts)
    ob = _new_obj("_pillow", bm)
    md = ob.modifiers.new("cloth", "CLOTH")
    s = md.settings
    s.quality = 7
    s.mass = 0.25
    s.tension_stiffness = 18
    s.compression_stiffness = 18
    s.shear_stiffness = 6
    s.bending_stiffness = 0.35
    s.use_pressure = True
    s.uniform_pressure_force = puff
    s.effector_weights.gravity = 0.0
    ls = ob.modifiers.new("lap", "LAPLACIANSMOOTH")
    ls.lambda_factor = 0.6
    ls.iterations = 4
    ss = ob.modifiers.new("sub", "SUBSURF")
    ss.levels = 1
    ss.render_levels = 1
    out = _simulate(ob, 40)
    _cleanup([ob])
    co = out[0].copy()
    zc = (co[:, 2].max() + co[:, 2].min()) / 2
    co[:, 2] -= zc
    # asentada: la cara de abajo se aplasta contra el colchón; la de arriba conserva el bombeo con el hundido de la cabeza
    low = co[:, 2] < 0
    co[low, 2] *= 0.55
    rx = co[:, 0] / (w / 2)
    ry = (co[:, 1] + d * 0.06) / (d / 2)
    dent = 0.025 * np.exp(-(rx ** 2) / 0.18 - (ry ** 2) / 0.35)
    co[~low, 2] -= dent[~low] * np.clip(co[~low, 2] / max(co[:, 2].max(), 1e-3), 0, 1)
    co[:, 2] -= co[:, 2].min()
    return co, out[1], out[2]


def pillow(mb, M, seed=0, w=0.62, d=0.42, puff=2.2, mat="linen"):
    """Almohada simulada (≈ 0,62 × 0,42 × 0,13). Origen: centro de la base (z = 0 sobre lo que la sostiene)."""
    co, flat, lens = _cached("pillow", dict(w=w, d=d, puff=puff, seed=seed), lambda: _pillow_sim(w, d, puff, seed))
    _to_mb(mb, co, flat, lens, mat, M)


# -------------------------------------------------------------------------------------------------------------- colchón
def _rounded_slab(L, W, H, r, crown, seg_l=40, seg_w=22, seg_h=8, fowler=0.0, hinge=0.0):
    """Superficie cerrada de colchón: sección superelíptica (esquinas de radio r), abombado superior `crown`; si fowler > 0
    dobla la parte de la cabecera (y > hinge) hacia arriba con una transición suave."""
    rings = []
    # contorno de la sección (en X-Z), recorrido cerrado
    sec = []
    n_c = 6
    corners = [(W / 2 - r, H - r, 0.0), (-W / 2 + r, H - r, math.pi / 2), (-W / 2 + r, r, math.pi), (W / 2 - r, r, 1.5 * math.pi)]
    for (cx, cz, a0) in corners:
        for k in range(n_c + 1):
            a = a0 + (math.pi / 2) * k / n_c
            sec.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    for i in range(seg_l + 1):
        y = -L / 2 + L * i / seg_l
        ring = []
        for (x, z) in sec:
            cr = crown * (1 - (2 * x / W) ** 2) * (1 - (2 * y / L) ** 4) if z > H / 2 else 0.0
            zz = z + cr * (z / H)
            yy = y
            if fowler > 0 and y > hinge:
                t = min(1.0, (y - hinge) / 0.25)
                ang = math.radians(fowler) * (t * t * (3 - 2 * t))
                dy = y - hinge
                yy = hinge + dy * math.cos(ang) - zz * math.sin(ang) + 0.0
                zz = dy * math.sin(ang) + zz * math.cos(ang)
            ring.append((x, yy, zz))
        rings.append(ring)
    return rings


RE = 0.035          # radio de todas las aristas del colchón (hule espuma forrado)
CROWN = 0.012       # abombado de la cara superior


def _sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _crown(x, y, z, W, L, H, crown=CROWN):
    """Abombado del colchón; la ropa que lo cubre usa la misma función para seguirlo a distancia constante."""
    xc = np.clip(x, -W / 2, W / 2)
    yc = np.clip(y, -L / 2, L / 2)
    cr = crown * (1 - (2 * xc / W) ** 2) * (1 - (2 * yc / L) ** 4)
    return np.where(z > H / 2, cr * np.clip(z / H, 0.0, 1.2), 0.0)


def _rbox_arrays(W, L, H, re=RE, step=0.05, n_round=5):
    """Caja de W x L x H (z de 0 a H) con las 12 aristas y las 8 esquinas redondeadas de radio `re`: cubo subdividido cuyos
    vértices se proyectan sobre la caja interior desplazada `re` (rejilla con muestreo angular uniforme en los redondeos)."""
    inner = np.array([W / 2 - re, L / 2 - re, H / 2 - re])

    def samples(a):
        n = max(1, int(round(2 * a / step)))
        band = a + re * np.tan(np.linspace(0, np.pi / 4, n_round + 1))[1:]
        return np.concatenate([-band[::-1], np.linspace(-a, a, n + 1), band])
    S = [samples(a) for a in inner]
    E = inner + re
    bm = bmesh.new()
    vmap = {}

    def vert(p):
        k = tuple(np.round(p, 7))
        v = vmap.get(k)
        if v is None:
            q = np.clip(p, -inner, inner)
            d = p - q
            pos = q + re * d / np.linalg.norm(d)
            v = vmap[k] = bm.verts.new((float(pos[0]), float(pos[1]), float(pos[2] + H / 2)))
        return v
    for ax in range(3):
        i1, i2 = [k for k in range(3) if k != ax]
        for sgn in (-1, 1):
            g1, g2 = S[i1], S[i2]
            grid = []
            for x1 in g1:
                row = []
                for x2 in g2:
                    p = np.zeros(3)
                    p[ax], p[i1], p[i2] = sgn * E[ax], x1, x2
                    row.append(vert(p))
                grid.append(row)
            for i in range(len(g1) - 1):
                for j in range(len(g2) - 1):
                    bm.faces.new([grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.verts.index_update()
    co = np.array([v.co[:] for v in bm.verts], np.float64)
    flat = np.array([v.index for f in bm.faces for v in f.verts], np.int32)
    lens = np.array([len(f.verts) for f in bm.faces], np.int32)
    bm.free()
    return co, flat, lens


def mattress(mb, M, L=1.9, W=0.86, H=0.13, seed=0, mat="vinyl", piping="vinyl", fowler=0.0, hinge=0.15, covered=False):
    """Colchón de hospital: hule espuma forrado de vinilo con las 12 aristas redondeadas (r 35 mm, también en planta), abombado,
    vivos (ribetes) sobre la línea de costura a 45° de las aristas superior e inferior y cierre lateral; quiebre Fowler opcional.
    covered=True (cama tendida: la sábana remetida lo tapa entero): solo el cuerpo, a baja resolución, sin vivos ni cierre."""
    co, flat, lens = _rbox_arrays(W, L, H, step=0.12 if covered else 0.05, n_round=3 if covered else 5)
    co[:, 2] += _crown(co[:, 0], co[:, 1], co[:, 2], W, L, H)
    co = bend_fowler(co, fowler, hinge)
    _to_mb(mb, co, flat, lens, mat, M)
    if covered:
        return
    # vivos: tubo de 4 mm sobre la costura (a 45° del redondeo), remuestreado cada 2 cm para seguir el quiebre del respaldo
    a, b = W / 2 - RE, L / 2 - RE
    rp = (RE + 0.0015) * math.cos(math.pi / 4)
    outline = []
    for (cx, cy, a0) in ((a, -b, -math.pi / 2), (a, b, 0.0), (-a, b, math.pi / 2), (-a, -b, math.pi)):
        for k in range(9):
            ang = a0 + (math.pi / 2) * k / 8
            outline.append(Vector((cx + rp * math.cos(ang), cy + rp * math.sin(ang), 0.0)))
    outline.append(outline[0])
    dense = [outline[0]]
    for p0, p1 in zip(outline[:-1], outline[1:]):
        n = max(1, int((p1 - p0).length / 0.02))
        for k in range(1, n + 1):
            dense.append(p0.lerp(p1, k / n))
    for zf in (H - RE + rp, RE - rp):
        pts = np.array([(p.x, p.y, zf) for p in dense])
        pts[:, 2] += _crown(pts[:, 0], pts[:, 1], pts[:, 2], W, L, H)
        pts = bend_fowler(pts, fowler, hinge)
        mb.tube([tuple(M @ Vector(p)) for p in pts], 0.004, seg=6, mat=piping)
    # cierre lateral (cremallera): dientes a media altura en un costado, siguiendo el quiebre
    n = 120
    for k in range(n):
        y0 = -L / 2 + 0.15 + k * (L - 0.3) / n
        y1 = y0 + (L - 0.3) / n * 0.7
        c0, c1 = bend_fowler(np.array([[W / 2, y0, H / 2], [W / 2, y1, H / 2]]), fowler, hinge)
        mb.box(M @ Vector((c0[0] - 0.002, c0[1], c0[2] - 0.004)), M @ Vector((c1[0] + 0.002, c1[1], c0[2] + 0.004)), "steel", bevel=0.0)
    del seed


def mattress_collider_arrays(L, W, H, fowler=0.0, hinge=0.15):
    mbt = MB()
    mattress(mbt, Matrix(), L, W, H, fowler=fowler, hinge=hinge)
    bm = mbt.bm
    co = np.array([v.co[:] for v in bm.verts], np.float32)
    idx = {v: i for i, v in enumerate(bm.verts)}
    faces = [[idx[v] for v in f.verts] for f in bm.faces]
    return co, np.array([i for f in faces for i in f], np.int32), np.array([len(f) for f in faces], np.int32)


# ---------------------------------------------------------------------------------------------------------- telas caídas
def _drape_sim(size, res, z0, colliders, seed, stiff, frames, thickness, pin_edge=None, pre_fold=None):
    sx, sy = size
    zmax = max((float(np.max(c[0][:, 2])) for c in colliders if isinstance(c, tuple)), default=0.0)
    z0 = max(z0, zmax + 0.03)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=res[0], y_segments=res[1], size=0.5)
    bmesh.ops.scale(bm, vec=(sx, sy, 1.0), verts=bm.verts)
    rr = np.random.default_rng(seed)
    for v in bm.verts:
        v.co.z = z0 + float(rr.normal(0, 0.002)) + 0.01 * noise.noise(Vector((v.co.x * 3 + seed, v.co.y * 3, 0)))
    if pre_fold:
        yf = pre_fold
        for v in bm.verts:
            if v.co.y < yf:                       # dobla la tela sobre sí misma (cobija con el embozo vuelto)
                v.co.y = 2 * yf - v.co.y
                v.co.z += 0.012
    ob = _new_obj("_drape", bm)
    if pin_edge is not None:
        vg = ob.vertex_groups.new(name="pin")
        ids = [v.index for v in ob.data.vertices if pin_edge(v.co)]
        vg.add(ids, 1.0, "REPLACE")
    md = ob.modifiers.new("cloth", "CLOTH")
    s = md.settings
    s.quality = 8
    s.mass = 0.3
    s.tension_stiffness = stiff
    s.compression_stiffness = stiff
    s.shear_stiffness = stiff * 0.3
    s.bending_stiffness = 0.05 if stiff < 20 else 0.4
    s.air_damping = 1.0
    if pin_edge is not None:
        s.vertex_group_mass = "pin"
    md.collision_settings.collision_quality = 4
    md.collision_settings.distance_min = 0.004
    md.collision_settings.use_self_collision = True
    md.collision_settings.self_distance_min = 0.003
    cols = [_collider_mesh(f"_c{i}", *c) if isinstance(c, tuple) else c for i, c in enumerate(colliders)]
    sm = ob.modifiers.new("smooth", "CORRECTIVE_SMOOTH")
    sm.iterations = 1
    so = ob.modifiers.new("solid", "SOLIDIFY")
    so.thickness = thickness
    so.offset = 1.0
    out = _simulate(ob, frames)
    _cleanup([ob] + cols)
    co, flat, lens = out
    k, worst = 0, 0.0
    rest = max(sx / res[0], sy / res[1])
    for n in lens:                                    # una tela que atraviesa su colisionador deja caras de varios metros
        idx = flat[k:k + n]
        k += n
        pts = co[idx]
        worst = max(worst, float(np.max(np.linalg.norm(pts - np.roll(pts, 1, axis=0), axis=1))))
    if worst > rest * 6 + thickness * 4:
        raise RuntimeError(f"tela inestable: arista de {worst:.3f} m (reposo {rest:.3f})")
    if zmax > 0 and pin_edge is None:
        inside = float(np.mean(co[:, 2] < zmax - 0.05))
        if inside > 0.5:
            raise RuntimeError(f"tela atravesó el colisionador: {inside:.0%} de los vértices bajo su cara superior")
    return out


def bend_fowler(co, fowler, hinge):
    """Dobla hacia arriba la parte y > hinge con la misma curva que el colchón (sábana ajustable que sigue al respaldo)."""
    if fowler <= 0:
        return co
    co = co.copy()
    y, z = co[:, 1].astype(np.float64), co[:, 2].astype(np.float64)
    t = np.clip((y - hinge) / 0.25, 0, 1)
    ang = math.radians(fowler) * (t * t * (3 - 2 * t))
    dy = y - hinge
    sel = y > hinge
    co[sel, 1] = (hinge + dy * np.cos(ang) - z * np.sin(ang))[sel]
    co[sel, 2] = (dy * np.sin(ang) + z * np.cos(ang))[sel]
    return co


# ------------------------------------------------------------------------------------------------- tendido de cama a la medida
def _perlin(X, Y, s):
    return np.array([noise.noise(Vector((float(x), float(y), s))) for x, y in zip(X.ravel(), Y.ravel())]).reshape(X.shape)


def _wrap(u, v, off, W, L, H, re=RE, tuck=0.05, bump=0.0, bump_w=0.3):
    """Coloca el punto (u, v) de una tela plana tendida sobre el colchón a `off` de su forro: plano arriba, luego rodea la
    arista (radio re + off), baja por el costado, rodea la arista inferior y se remete `tuck` bajo el colchón. En las esquinas
    la distancia al rectángulo interior es radial (esquina redondeada como la del colchón). `bump` levanta la tela sobre el vivo
    a 45° de cada arista."""
    a, b = W / 2 - re, L / 2 - re
    qx, qy = np.clip(u, -a, a), np.clip(v, -b, b)
    dx, dy = u - qx, v - qy
    t = np.hypot(dx, dy)
    tn = np.maximum(t, 1e-12)
    nx, ny = dx / tn, dy / tn
    R = re + off
    zc = H - re
    t1 = 0.5 * np.pi * R
    t2 = t1 + (H - 2 * re)
    t3 = t2 + 0.5 * np.pi * R
    th = np.clip(t / R, 0, np.pi / 2)
    Rb = R + bump * np.exp(-((th - np.pi / 4) / bump_w) ** 2)
    rho, z = Rb * np.sin(th), zc + Rb * np.cos(th)
    side = t > t1
    rho = np.where(side, R, rho)
    z = np.where(side, zc - (t - t1), z)
    th2 = np.clip((t - t2) / R, 0, np.pi / 2)
    Rb2 = R + bump * np.exp(-((th2 - np.pi / 4) / bump_w) ** 2)
    low = t > t2
    rho = np.where(low, Rb2 * np.cos(th2), rho)
    z = np.where(low, re - Rb2 * np.sin(th2), z)
    under = t > t3
    rho = np.where(under, -(t - t3), rho)
    z = np.where(under, re - R, z)
    x, y = qx + nx * rho, qy + ny * rho
    z = z + _crown(x, y, z, W, L, H)
    del tuck
    return np.stack([x, y, z], -1)


def _band(R, H, re=RE, tuck=0.05, n_side=3, n_low=4):
    """Valores de distancia t (desde el borde del rectángulo interior) para muestrear la vuelta de la tela: arista (8),
    costado (n_side), arista inferior (n_low, bajo el colchón casi no se ve) y remetido (1)."""
    t1 = 0.5 * np.pi * R
    t2 = t1 + (H - 2 * re)
    t3 = t2 + 0.5 * np.pi * R
    return np.concatenate([np.linspace(0, t1, 9)[1:], np.linspace(t1, t2, n_side + 1)[1:], np.linspace(t2, t3, n_low + 1)[1:],
                           [t3 + tuck]])


def _axis(inner, R, H, step, lo_end=True, hi_end=True, lo=None, hi=None, n_side=3, n_low=4):
    band = _band(R, H, n_side=n_side, n_low=n_low)
    lo_ = -inner if lo is None else lo
    hi_ = inner if hi is None else hi
    parts = [-inner - band[::-1]] if lo_end else []
    parts.append(np.linspace(lo_, hi_, max(2, int(round((hi_ - lo_) / step))) + 1))
    if hi_end:
        parts.append(inner + band)
    return np.concatenate(parts)


def _grid_normals(P):
    N = np.cross(np.gradient(P, axis=1), np.gradient(P, axis=0))
    return N / np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-12)


def _grid_to_mb(mb, M, P, mat):
    nv, nu, _ = P.shape
    vs = [[mb.bm.verts.new(M @ Vector(P[j, i])) for i in range(nu)] for j in range(nv)]
    mi = mb.mi(mat)
    for j in range(nv - 1):
        for i in range(nu - 1):
            f = mb.bm.faces.new([vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]])
            f.material_index = mi
            f.smooth = True


def _ridges(U, V, specs):
    """Arrugas: crestas gaussianas que se adelgazan hacia las puntas. spec = (cx, cy, ángulo, largo, ancho, alto)."""
    D = np.zeros_like(U)
    for (cx, cy, ang, length, w, A) in specs:
        dx, dy = U - cx, V - cy
        ca, sa = math.cos(ang), math.sin(ang)
        al, pe = dx * ca + dy * sa, -dx * sa + dy * ca
        env = np.clip(1 - (2 * al / length) ** 2, 0, 1)
        we = w * (0.45 + 0.55 * np.sqrt(env))
        D += A * np.exp(-(pe / np.maximum(we, 1e-4)) ** 2) * env ** 1.5
    return D


def _gathers(U, V, a, b, t_lo, t_hi, k, A, seed, corners="all"):
    """Frunces de esquina: la tela que sobra al rodear la esquina redondeada se junta en `k` pliegues verticales que crecen
    hacia abajo (donde la tela se remete o la jala el resorte)."""
    dx, dy = np.abs(U) - a, np.abs(V) - b
    m = (dx > 0) & (dy > 0)
    if corners == "foot":
        m &= V < 0
    t = np.hypot(np.maximum(dx, 0), np.maximum(dy, 0))
    phi = np.arctan2(np.maximum(dy, 0), np.maximum(dx, 0))
    ph = (np.sign(U) * 1.7 + np.sign(V) * 2.9 + seed) % (2 * np.pi)
    phi_w = phi + 0.06 * np.sin(3 * phi + ph)
    env = np.sqrt(np.clip(np.sin(2 * phi), 0, 1)) * _sstep(t_lo, t_hi, t)
    D = A * env * (0.5 + 0.5 * np.sin(4 * k * phi_w + ph)) ** 1.5
    return np.where(m, D, 0.0)


def bed_linens(mb, M, L=1.9, W=0.86, H=0.13, seed=0, blanket=True, fowler=0.0, hinge=0.15):
    """Tendido de cama de hospital hecho a la medida del colchón (no simulado: cada capa sigue el forro a distancia fija y se
    remete bajo el colchón, como se tiende en un hospital):
    - sábana bajera remetida en los 4 lados: frunces en las esquinas, arrugas de tensión que salen de las esquinas de la
      cabecera, pliegues de planchado (uno a lo largo y uno a lo ancho) y ondulación suave; levanta sobre los vivos.
    - cobija (si `blanket`): de la mitad del colchón al pie, remetida al pie y a los costados con esquina de hospital (pliegue
      diagonal en el costado con el escalón de la solapa), pliegues anchos y blandos, dobladillo de 7 mm en el borde superior.
    - sábana superior: entra bajo la cobija, sale 8-12 cm y se dobla de regreso sobre ella (embozo) con un doblez redondeado,
      ondas que cruzan el doblez y dobladillo en el borde libre.
    Sin cobija: cobija doblada en tres al pie.  Todo se dobla con el quiebre Fowler igual que el colchón."""
    rr = np.random.default_rng(seed + 101)
    a, b = W / 2 - RE, L / 2 - RE
    OFF_S, OFF_A, OFF_K = 0.003, 0.0045, 0.012
    sd = float(seed) * 7.31

    def bend(P):
        sh = P.shape
        return bend_fowler(P.reshape(-1, 3), fowler, hinge).reshape(sh)

    def hem(P, N, inset, r, mat, row=-1):
        c = bend(P[row] - N[row] * inset)
        mb.tube([tuple(M @ Vector(p)) for p in c], r, seg=8, mat=mat)

    y1 = float(rr.uniform(0.0, 0.14))
    e, cw = float(rr.uniform(0.08, 0.12)), float(rr.uniform(0.20, 0.26))
    yf = y1 + e
    # ---- 1) sábana bajera
    R = RE + OFF_S
    if blanket:                       # bajo la cobija y el embozo la sábana no se ve: malla gruesa ahí, fina de la cabecera al embozo
        bs = _band(R, H, n_side=6, n_low=2)
        vs = np.concatenate([-b - _band(R, H, n_side=2, n_low=1)[::-1], np.linspace(-b, y1 - 0.08, max(2, int((y1 - 0.08 + b) / 0.05)) + 1),
                             np.linspace(y1 - 0.08, b, max(2, int((b - y1 + 0.08) / 0.016)) + 1)[1:], b + bs])
    else:
        vs = _axis(b, R, H, 0.016, n_side=6, n_low=2)
    U, V = np.meshgrid(_axis(a, R, H, 0.016, n_side=6, n_low=2), vs)
    P = _wrap(U, V, OFF_S, W, L, H, bump=0.0045, bump_w=0.25)
    D = 0.0013 * _perlin(U * 4, V * 4, sd) + 0.0005 * _perlin(U * 12, V * 12, sd + 3)
    vis = _sstep(yf + 0.02, yf + 0.09, V) if blanket else np.ones_like(V)
    pil = _sstep(0.30, 0.36, np.abs(U)) + _sstep(0.22, 0.28, np.abs(V - 0.68))
    pil = np.clip(pil, 0, 1)                                             # bajo la almohada no hay arrugas que la atraviesen
    specs = [(float(rr.uniform(-0.02, 0.02)), 0.0, math.pi / 2, 2.2, 0.016, 0.0009),       # pliegue de planchado a lo largo
             (0.0, float(rr.uniform(0.40, 0.50)), 0.0, 1.0, 0.016, 0.0008)]                # y a lo ancho
    for sx in (-1, 1):                                                  # tensión desde las esquinas de la cabecera
        for _ in range(2):
            ang = math.radians(float(rr.uniform(20, 55)))
            ln = float(rr.uniform(0.16, 0.30))
            cx = sx * (a - ln * 0.35 * math.cos(ang))
            cy = b - ln * 0.35 * math.sin(ang) - float(rr.uniform(0.0, 0.08))
            specs.append((cx, cy, math.pi - ang if sx > 0 else ang, ln, float(rr.uniform(0.018, 0.026)), float(rr.uniform(0.003, 0.0045))))
    lo_y = (yf + 0.08) if blanket else (-b + 0.05)
    for _ in range(7):                                                  # arrugas sueltas donde se sentó o se acomodó alguien
        specs.append((float(rr.uniform(-0.33, 0.33)), float(rr.uniform(lo_y, 0.42)), float(rr.uniform(0, math.pi)),
                      float(rr.uniform(0.12, 0.34)), float(rr.uniform(0.018, 0.03)), float(rr.uniform(0.0025, 0.0042))))
    D += _ridges(U, V, specs) * vis * pil
    D += _gathers(U, V, a, b, 0.25 * 0.5 * np.pi * R, 0.5 * np.pi * R + H - 2 * RE, 4, 0.0065, sd)
    Pd = P + _grid_normals(P) * D[..., None]
    _grid_to_mb(mb, M, bend(Pd), "linen")
    if not blanket:
        yb, xb, rz = -0.62, float(rr.uniform(-0.03, 0.03)), math.radians(float(rr.uniform(-4, 4)))

        def base(x, y):                                     # apoyo: el abombado del colchón bajo la cobija
            gx = xb + x * math.cos(rz) - y * math.sin(rz)
            gy = yb + x * math.sin(rz) + y * math.cos(rz)
            return _crown(gx, gy, np.full_like(gx, H), W, L, H) - 0.0015
        folded_blanket(mb, M @ Matrix.Translation((xb, yb, H + OFF_S)) @ Matrix.Rotation(rz, 4, "Z"), w=0.74, d=0.36, layers=3,
                       seed=seed, mat="wool_blue", base=base)
        return
    # ---- 2) cobija
    R = RE + OFF_K
    vs = np.concatenate([-b - _band(R, H, n_side=8)[::-1], np.linspace(-b, -b + 0.30, 28),
                         np.linspace(-b + 0.30, y1, max(2, int(round((y1 + b - 0.30) / 0.022))) + 1)[1:]])
    U, V = np.meshgrid(_axis(a, R, H, 0.022, n_side=8), vs)          # malla fina en costados y pie: pliegue de esquina
    P = _wrap(U, V, OFF_K, W, L, H, bump=0.0015, bump_w=0.45)
    fade = _sstep(yf - cw - 0.01, yf - cw - 0.12, V)                    # nada bajo el embozo que lo atraviese
    D = (0.0034 * _perlin(U * 3.0, V * 3.0, sd + 11) + 0.0011 * _perlin(U * 9, V * 9, sd + 12)) * (0.2 + 0.8 * fade)
    specs = []
    for _ in range(6):                                                  # pliegues anchos de la lana
        specs.append((float(rr.uniform(-0.32, 0.32)), float(rr.uniform(-0.78, y1 - 0.25)), math.pi / 2 + float(rr.uniform(-0.6, 0.6)),
                      float(rr.uniform(0.30, 0.75)), float(rr.uniform(0.03, 0.05)), float(rr.uniform(0.005, 0.009))))
    D += _ridges(U, V, specs) * fade
    D += _gathers(U, V, a, b, 0.4 * np.pi * R, 0.5 * np.pi * R + H - 2 * RE, 3, 0.006, sd + 5, corners="foot")
    # esquina de hospital: pliegue diagonal en el costado, del canto superior (≈ 24 cm del pie) a la esquina inferior del pie,
    # con el escalón de la solapa doblada encima
    t1 = 0.5 * np.pi * R
    t2 = t1 + H - 2 * RE
    dxs = np.abs(U) - a
    p0, p1 = np.array([t1, -b + 0.24]), np.array([t2 + 0.01, -b])
    dvec = (p1 - p0) / np.linalg.norm(p1 - p0)
    rel_x, rel_y = dxs - p0[0], V - p0[1]
    al = rel_x * dvec[0] + rel_y * dvec[1]
    pe = -rel_x * dvec[1] + rel_y * dvec[0]
    span = np.linalg.norm(p1 - p0)
    win = _sstep(0.45 * t1, 0.85 * t1, dxs) * _sstep(-0.03, 0.01, al) * _sstep(span + 0.03, span - 0.01, al)
    crease = 0.005 * np.exp(-(pe / 0.011) ** 2) + 0.0035 * _sstep(0.005, -0.009, pe) * _sstep(-0.16, -0.10, pe)
    D += crease * win
    Pd = P + _grid_normals(P) * D[..., None]
    Nd = _grid_normals(Pd)
    _grid_to_mb(mb, M, bend(Pd), "wool_blue")
    hem(Pd, Nd, 0.0035, 0.0035, "wool_blue")
    # ---- 3) sábana superior con embozo: capa A bajo la cobija -> doblez -> capa B de regreso sobre la cobija
    rho = 0.0032
    ys_a = np.arange(y1 - 0.06, yf, 0.015)
    al_f = np.linspace(-np.pi / 2, np.pi / 2, 9)[1:-1]
    ys_b = np.linspace(yf, yf - cw, max(3, int(cw / 0.015)) + 1)
    ys = np.concatenate([ys_a, yf + rho * np.cos(al_f), ys_b])
    offb = (OFF_A + 0.0035) + (2 * rho - 0.0035) * np.exp(-(yf - ys_b) / 0.03)
    offb = offb + (0.0155 - offb) * _sstep(y1 + 0.025, y1 - 0.005, ys_b)
    offs = np.concatenate([np.full(len(ys_a), OFF_A), OFF_A + rho + rho * np.sin(al_f), offb])
    sgn = np.concatenate([np.ones(len(ys_a) + len(al_f) // 2), -np.ones(len(al_f) - len(al_f) // 2 + len(ys_b))])
    us = _axis(a, RE + 0.01, H, 0.018)
    U, Ys = np.meshgrid(us, ys)
    OFF = np.broadcast_to(offs[:, None], U.shape)
    P = _wrap(U, Ys, OFF, W, L, H, bump=0.002, bump_w=0.4)
    N = _grid_normals(P) * sgn[:, None, None]
    specs = [(float(rr.uniform(-0.34, 0.34)), yf - 0.02, math.pi / 2 + float(rr.uniform(-0.25, 0.25)), float(rr.uniform(0.08, 0.16)),
              0.016, float(rr.uniform(0.0008, 0.0016))) for _ in range(5)]
    D = 0.0004 * _perlin(U * 6, Ys * 6, sd + 21) + _ridges(U, Ys, specs)
    D = np.maximum(D, -0.0006)
    Pd = P + N * D[..., None]
    _grid_to_mb(mb, M, bend(Pd), "linen")
    Nd = _grid_normals(Pd) * sgn[:, None, None]
    hem(Pd, Nd, 0.0012, 0.0018, "linen")


def drape(mb, M, name, size, res, z0, colliders_fn, mat, seed=0, stiff=12.0, frames=60, thickness=0.003, pin=None, pre_fold=None,
          params=None, post=None):
    """Tela simulada: rectángulo `size` (x, y) a la altura z0 que cae sobre los colisionadores de `colliders_fn()`.
    pin: ('y+', margen) fija el borde (cortina colgada de su riel). params: claves extra para el caché."""
    p = dict(size=list(size), res=list(res), z0=z0, seed=seed, stiff=stiff, frames=frames, t=thickness, pin=pin, pf=pre_fold,
             extra=params or {})

    def run():
        pe = None
        if pin is not None:
            side, m = pin
            hy = size[1] / 2
            pe = (lambda c: c.y > hy - m) if side == "y+" else (lambda c: c.z > z0 - m)
        return _drape_sim(size, res, z0, colliders_fn(), seed, stiff, frames, thickness, pin_edge=pe, pre_fold=pre_fold)
    co, flat, lens = _cached(name, p, run)
    if post is not None:
        co = post(co)
    _to_mb(mb, co, flat, lens, mat, M)


# -------------------------------------------------------------------------------------------------------------- cobija
def folded_blanket(mb, M, w=0.86, d=0.42, layers=3, t=0.012, seed=0, mat="wool_blue", base=None):
    """Cobija de lana doblada en `layers` capas: bulto blando con aristas redondeadas (no placas), lomos de los dobleces
    redondos en los dos extremos alternados, canales entre capas en los costados abiertos, capas corridas unas sobre otras,
    lomo superior abombado, pelusa (ruido fino) y caída que copia el abombado de lo que tiene abajo.
    base(x, y) -> desplazamiento z del apoyo en coordenadas locales (p. ej. el abombado del colchón)."""
    rr = np.random.default_rng(seed + 7)
    h = layers * t * 1.45
    re = min(h * 0.45, 0.022)
    co, flat, lens = _rbox_arrays(w, d, h, re=re, step=0.02, n_round=4)
    x, y, z = co[:, 0].copy(), co[:, 1].copy(), co[:, 2].copy()
    sd = float(seed) * 3.7 + 0.5
    zl = np.clip(z / h, 0, 1) * layers                      # coordenada de capa (0..layers)
    # capas corridas: cada capa se desplaza unos mm en x/y; se interpola suave entre capas
    sh = rr.uniform(-0.008, 0.008, (layers + 1, 2))
    k0 = np.clip(np.floor(zl).astype(int), 0, layers - 1)
    fr = zl - k0
    fr = fr * fr * (3 - 2 * fr)
    x += sh[k0, 0] * (1 - fr) + sh[k0 + 1, 0] * fr
    y += sh[k0, 1] * (1 - fr) + sh[k0 + 1, 1] * fr
    # canales entre capas en los costados abiertos (|x| cerca del canto) y lomos de los dobleces en los extremos y
    side = _sstep(w / 2 - re - 0.01, w / 2 - 0.002, np.abs(x))
    endy = _sstep(d / 2 - re - 0.01, d / 2 - 0.002, np.abs(y))
    groove = np.zeros_like(z)
    for k in range(1, layers):
        groove += np.exp(-((zl - k) / 0.16) ** 2)
    # en un extremo el doblez abre las capas 1-2 y en el otro las 2-3: el canal del extremo cerrado es más leve
    fold_end = np.where(y > 0, 1.0, -1.0)
    end_g = np.zeros_like(z)
    for k in range(1, layers):
        closed = (k % 2 == 1) == (fold_end > 0)
        end_g += np.exp(-((zl - k) / 0.18) ** 2) * np.where(closed, 0.35, 1.0)
    inward = 0.0035 * groove * side + 0.003 * end_g * endy
    nx = np.sign(x) * side
    ny = np.sign(y) * endy
    nn = np.maximum(np.hypot(nx, ny), 1e-9)
    x -= inward * nx / nn * (nn > 1e-6)
    y -= inward * ny / nn * (nn > 1e-6)
    # lomo superior abombado y pelusa
    top = _sstep(h * 0.6, h, z)
    z += top * (0.006 * (1 - (2 * x / w) ** 2) * (1 - (2 * y / d) ** 4))
    X, Y, Z = x * 6, y * 6, z * 6
    z += 0.0018 * np.array([noise.noise(Vector((a_ + sd, b_, c_))) for a_, b_, c_ in zip(X, Y, Z)]) * top
    fz = np.array([noise.noise(Vector((a_ * 4 + sd, b_ * 4, c_ * 4))) for a_, b_, c_ in zip(X, Y, Z)])
    x += 0.0007 * fz
    y += 0.0007 * fz
    if base is not None:
        z += base(x, y)
    co = np.stack([x, y, z], -1)
    _to_mb(mb, co, flat, lens, mat, M)


# -------------------------------------------------------------------------------------------------------------- cortinas
def _curtain_sim(hang_w, fabric_w, drop, seed):
    """Cortina fruncida: pliegues de paso y fondo variables (no un acanalado), algunos pliegues que se cruzan en diagonal hacia
    el pie, dobladillo con peso (filas inferiores más pesadas) y fijación solo en los colgantes."""
    nx = max(16, int(fabric_w / 0.03))
    nz = max(12, int(drop / 0.05))
    rr = np.random.default_rng(seed)
    c = fabric_w / hang_w
    # fase acumulada con periodos aleatorios
    periods = rr.uniform(0.08, 0.15, 400)
    amps = rr.uniform(0.55, 1.25, 400)
    def pleat(xh):
        k, x0 = 0, 0.0
        while k < 399 and x0 + periods[k] < xh:
            x0 += periods[k]
            k += 1
        t = (xh - x0) / periods[k]
        base = periods[k] / math.pi * math.sqrt(max(c * c - 1.0, 0.0)) * 0.55
        return amps[k] * base * math.sin(2 * math.pi * t)
    bm = bmesh.new()
    rows = []
    drift = rr.uniform(-0.04, 0.04)
    for j in range(nz + 1):
        fz = j / nz
        z = -drop * fz
        row = []
        for i in range(nx + 1):
            xh = i / nx * hang_w
            x = xh + drift * fz * fz * math.sin(math.pi * i / nx)
            y = pleat(xh + 0.03 * math.sin(fz * 3.0 + i * 0.05) * fz) * (1.0 - 0.2 * fz) + float(rr.normal(0, 0.0006))
            row.append(bm.verts.new((x, y, z)))
        rows.append(row)
    for j in range(nz):
        for i in range(nx):
            bm.faces.new([rows[j][i], rows[j][i + 1], rows[j + 1][i + 1], rows[j + 1][i]])
    ob = _new_obj("_curtain", bm)
    vg = ob.vertex_groups.new(name="pin")
    step = max(1, int(round(0.1 / (hang_w / nx))))
    vg.add([v.index for v in ob.data.vertices if v.co.z > -0.001 and int(round(v.co.x / (hang_w / nx))) % step == 0], 1.0, "REPLACE")
    md = ob.modifiers.new("cloth", "CLOTH")
    st = md.settings
    st.quality = 7
    st.mass = 0.25
    st.tension_stiffness = 10
    st.compression_stiffness = 6
    st.shear_stiffness = 3
    st.bending_stiffness = 0.05
    st.air_damping = 2.0
    st.vertex_group_mass = "pin"
    out = _simulate(ob, 50)                  # una sola hoja: la tela es material de doble cara (linen en DOUBLE_SIDED)
    _cleanup([ob])
    co = out[0].copy()
    # dobladillo: los 4 cm de abajo, doble tela (ligeramente más gruesos hacia afuera)
    zmin = co[:, 2].min()
    hem = co[:, 2] < zmin + 0.04
    co[hem, 1] *= 1.04
    return co, out[1], out[2]


def curtain(mb, M, hang_w, drop, seed=0, gathered=1.8, mat="linen"):
    """Cortina colgada de su riel con caída simulada: tela de ancho hang_w × gathered fruncida en hang_w, plisado natural,
    dobladillo abajo. Origen: extremo izquierdo del riel (z = 0 = colgantes); cuelga hacia -Z a lo largo de +X."""
    hw = round(hang_w * 10) / 10
    co, flat, lens = _cached("curtain", dict(w=hw, f=round(hw * gathered, 2), d=round(drop, 2), s=seed),
                             lambda: _curtain_sim(hw, hw * gathered, drop, seed))
    co = co.copy()
    co[:, 0] *= hang_w / hw
    _to_mb(mb, co, flat, lens, mat, M)
