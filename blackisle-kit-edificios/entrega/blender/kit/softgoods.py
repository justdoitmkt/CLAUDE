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
VERSION = 6


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
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=22, use_grid_fill=True)
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


def mattress(mb, M, L=1.9, W=0.86, H=0.13, seed=0, mat="vinyl", piping="vinyl", fowler=0.0, hinge=0.15):
    """Colchón de hospital: hule espuma forrado de vinilo, esquinas redondeadas, abombado, vivos perimetrales y cierre."""
    rings = _rounded_slab(L, W, H, 0.035, 0.012, fowler=fowler, hinge=hinge)
    nr = len(rings[0])
    vs = [[mb.bm.verts.new(M @ Vector(p)) for p in ring] for ring in rings]
    for i in range(len(vs) - 1):
        for k in range(nr):
            f = mb.face([vs[i][k], vs[i][(k + 1) % nr], vs[i + 1][(k + 1) % nr], vs[i + 1][k]], mat)
            f.smooth = True
    for ring, rev in ((vs[0], False), (vs[-1], True)):
        c = sum((v.co for v in ring), Vector()) / nr
        cv = mb.bm.verts.new(c)
        for k in range(nr):
            a, b = ring[k], ring[(k + 1) % nr]
            f = mb.face([cv, b, a] if not rev else [cv, a, b], mat)
            f.smooth = True
    # vivos (ribetes) en las aristas superior e inferior: tubo de 4 mm siguiendo el contorno, remuestreado cada 2 cm para que
    # siga el quiebre del respaldo
    def bent(x, y, z):
        if fowler > 0 and y > hinge:
            t = min(1.0, (y - hinge) / 0.25)
            ang = math.radians(fowler) * (t * t * (3 - 2 * t))
            dy = y - hinge
            return Vector((x, hinge + dy * math.cos(ang) - z * math.sin(ang), dy * math.sin(ang) + z * math.cos(ang)))
        return Vector((x, y, z))

    corners = ((W / 2 - 0.035, -L / 2 + 0.035, -math.pi / 2), (W / 2 - 0.035, L / 2 - 0.035, 0.0), (-W / 2 + 0.035, L / 2 - 0.035, math.pi / 2),
               (-W / 2 + 0.035, -L / 2 + 0.035, math.pi))
    outline = []
    for (cx, cy, a0) in corners:
        for k in range(9):
            a = a0 + (math.pi / 2) * k / 8
            outline.append(Vector((cx + 0.036 * math.cos(a), cy + 0.036 * math.sin(a), 0.0)))
    outline.append(outline[0])
    dense = [outline[0]]
    for p0, p1 in zip(outline[:-1], outline[1:]):
        n = max(1, int((p1 - p0).length / 0.02))
        for k in range(1, n + 1):
            dense.append(p0.lerp(p1, k / n))
    for zf in (H - 0.004, 0.004):
        mb.tube([tuple(M @ bent(p.x, p.y, zf)) for p in dense], 0.004, seg=6, mat=piping)
    # cierre lateral (cremallera): dientes a media altura en un costado, siguiendo el quiebre
    n = 120
    for k in range(n):
        y0 = -L / 2 + 0.15 + k * (L - 0.3) / n
        y1 = y0 + (L - 0.3) / n * 0.7
        c0, c1 = bent(W / 2, y0, H / 2), bent(W / 2, y1, H / 2)
        mb.box(M @ (c0 + Vector((-0.002, 0, -0.004))), M @ (Vector((c1.x + 0.002, c1.y, c0.z + 0.004))), "steel")
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
def folded_blanket(mb, M, w=0.86, d=0.42, layers=3, t=0.012, seed=0, mat="wool_blue"):
    """Cobija doblada en `layers` pliegues: capas con dobleces redondeados alternos (S), bordes con caída y ruido de pelusa."""
    rr = np.random.default_rng(seed)
    nx, ny = 34, 14
    H = layers * t * 1.6
    rows = []
    # recorrido en S en el plano Y-Z: capa k va de un extremo al otro; el doblez es una semicircunferencia de radio = paso/2
    step = H / layers
    path = []
    for k in range(layers):
        y0, y1 = (-d / 2, d / 2) if k % 2 == 0 else (d / 2, -d / 2)
        zc = step * (k + 0.5)
        for j in range(ny + 1):
            path.append((y0 + (y1 - y0) * j / ny, zc))
        if k < layers - 1:
            cy = y1
            for j in range(1, 8):
                a = math.pi * j / 8
                sgn = 1 if k % 2 == 0 else -1
                path.append((cy + sgn * step / 2 * math.sin(a), zc + step / 2 * (1 - math.cos(a))))
    for i in range(nx + 1):
        x = -w / 2 + w * i / nx
        ring = []
        for (y, z) in path:
            sag = 0.004 * math.sin(math.pi * i / nx)
            fz = 0.0025 * noise.noise(Vector((x * 9 + seed, y * 9, z * 9)))
            ring.append((x * (1 - 0.01 * (z / H)), y, z - sag + fz))
        rows.append(ring)
    n = len(path)
    top = [[mb.bm.verts.new(M @ Vector(p)) for p in ring] for ring in rows]
    bot = [[mb.bm.verts.new(M @ Vector((p[0], p[1], p[2] - t))) for p in ring] for ring in rows]
    for i in range(nx):
        for j in range(n - 1):
            for (A, B, flip) in ((top, top, False), (bot, bot, True)):
                q = [A[i][j], A[i + 1][j], B[i + 1][j + 1], B[i][j + 1]]
                f = mb.face(list(reversed(q)) if flip else q, mat)
                f.smooth = True
    for i in (0, nx):
        for j in range(n - 1):
            q = [top[i][j], top[i][j + 1], bot[i][j + 1], bot[i][j]]
            f = mb.face(q if i == 0 else list(reversed(q)), mat)
            f.smooth = True
    for j in (0, n - 1):
        for i in range(nx):
            q = [top[i][j], bot[i][j], bot[i + 1][j], top[i + 1][j]]
            f = mb.face(q if j == 0 else list(reversed(q)), mat)
            f.smooth = True
    del rr


# -------------------------------------------------------------------------------------------------------------- cortinas
def _curtain_sim(hang_w, fabric_w, drop, seed):
    """Cortina fruncida: pliegues de paso y fondo variables (no un acanalado), algunos pliegues que se cruzan en diagonal hacia
    el pie, dobladillo con peso (filas inferiores más pesadas) y fijación solo en los colgantes."""
    nx = max(16, int(fabric_w / 0.02))
    nz = max(12, int(drop / 0.03))
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
    so = ob.modifiers.new("solid", "SOLIDIFY")
    so.thickness = 0.002
    out = _simulate(ob, 50)
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
