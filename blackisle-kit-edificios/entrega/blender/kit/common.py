"""common.py — base del kit modular BLACKISLE (Blender 5.2, bpy + bmesh, sin bpy.ops en geometría).

Convenciones (obligatorias para todo el kit):
- 1 unidad = 1 m · Z arriba · la fachada principal mira a -Y · origen de cada pieza en su base (z = 0) salvo que se diga otra cosa.
- Toda la geometría se construye con `MB` (bmesh). Cada cara lleva un nombre de material de `MATERIALS`.
- Biseles reales de 2 segmentos en aristas duras >= 2 cm (`box(..., bevel=...)`).
- Nada de booleanos para abrir vanos: `wall_with_openings` arma muros con huecos en una malla de cuadriláteros.
- Aleatoriedad SOLO vía `rng(seed)`: misma semilla, mismo resultado.
"""
import math

import bpy  # noqa: I001  (con el módulo bpy, bmesh y mathutils solo existen después de importar bpy)
import bmesh
import numpy as np
from mathutils import Matrix, Vector

# --- materiales de look-dev (nombres canónicos; el color es solo para la vista de arcilla/depuración) ---
MATERIALS = {
    "concrete": (0.50, 0.49, 0.46), "plaster": (0.62, 0.56, 0.45), "brick": (0.45, 0.22, 0.15),
    "mortar": (0.60, 0.58, 0.54), "tile": (0.55, 0.25, 0.15), "wood": (0.35, 0.25, 0.17),
    "wood_dark": (0.20, 0.13, 0.09), "wood_grey": (0.55, 0.53, 0.50), "metal_rust": (0.40, 0.20, 0.10),
    "metal_paint": (0.30, 0.33, 0.30), "aluminium": (0.65, 0.66, 0.66), "glass": (0.30, 0.38, 0.40),
    "fabric": (0.60, 0.55, 0.48), "cable": (0.05, 0.05, 0.05), "plastic": (0.80, 0.80, 0.76),
    "roof_metal": (0.45, 0.25, 0.15), "roof_metal_light": (0.70, 0.70, 0.68), "rubble": (0.48, 0.46, 0.42),
    "sand": (0.76, 0.70, 0.56), "vegetation": (0.25, 0.32, 0.15),
}


def rng(seed):
    return np.random.default_rng(seed)


def get_material(name):
    m = bpy.data.materials.get(name)
    if m is None:
        m = bpy.data.materials.new(name)
        c = MATERIALS.get(name, (0.5, 0.5, 0.5))
        m.diffuse_color = (*c, 1.0)
    return m


def get_collection(name, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def _v(p):
    return Vector((float(p[0]), float(p[1]), float(p[2])))


class MB:
    """Constructor de mallas sobre bmesh con material por cara. Todas las primitivas aceptan `m` (Matrix 4x4) opcional."""

    def __init__(self):
        self.bm = bmesh.new()
        self.mats = []

    # ---------------- utilidades ----------------
    def mi(self, name):
        if name not in self.mats:
            self.mats.append(name)
        return self.mats.index(name)

    def _verts(self, pts, m=None):
        return [self.bm.verts.new((m @ _v(p)) if m is not None else _v(p)) for p in pts]

    def face(self, verts, mat):
        f = self.bm.faces.new(verts)
        f.material_index = self.mi(mat)
        return f

    def poly(self, pts, mat, m=None):
        return self.face(self._verts(pts, m), mat)

    # ---------------- primitivas ----------------
    def box(self, mn, mx, mat="concrete", bevel=0.0, seg=2, m=None):
        """Caja alineada a ejes (en el espacio de `m`). bevel > 0: bisel real en las 12 aristas."""
        x0, y0, z0 = mn
        x1, y1, z1 = mx
        p = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        v = self._verts(p, m)
        idx = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
        faces = [self.face([v[i] for i in q], mat) for q in idx]
        if bevel > 0:
            lim = 0.49 * min(abs(x1 - x0), abs(y1 - y0), abs(z1 - z0))
            edges = list({e for f in faces for e in f.edges})
            res = bmesh.ops.bevel(self.bm, geom=edges, offset=min(bevel, lim), segments=seg, profile=0.5,
                                  affect="EDGES", clamp_overlap=True)
            for f in res["faces"]:
                f.material_index = self.mi(mat)
        return faces

    def cyl(self, p0, p1, r, seg=8, mat="metal_rust", caps=True, r1=None):
        """Cilindro (o cono si r1) entre dos puntos."""
        p0, p1 = _v(p0), _v(p1)
        d = p1 - p0
        q = d.to_track_quat("Z", "Y")
        rot = q.to_matrix().to_4x4()
        r1 = r if r1 is None else r1
        ring0, ring1 = [], []
        for i in range(seg):
            a = 2 * math.pi * i / seg
            c = Vector((math.cos(a), math.sin(a), 0))
            ring0.append(self.bm.verts.new(p0 + rot @ (c * r)))
            ring1.append(self.bm.verts.new(p1 + rot @ (c * r1)))
        for i in range(seg):
            j = (i + 1) % seg
            self.face([ring0[i], ring0[j], ring1[j], ring1[i]], mat)
        if caps:
            self.face(list(reversed(ring0)), mat)
            self.face(ring1, mat)
        return ring0, ring1

    def tube(self, pts, r, seg=8, mat="cable", caps=True, radii=None):
        """Barre un círculo a lo largo de una polilínea (transporte paralelo; sin giros bruscos). Cables, varillas, tubos."""
        P = [_v(p) for p in pts]
        n = len(P)
        if n < 2:
            return
        T = []
        for i in range(n):
            a = P[min(i + 1, n - 1)] - P[max(i - 1, 0)]
            T.append(a.normalized() if a.length > 1e-9 else Vector((0, 0, 1)))
        ref = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
        N = (ref - T[0] * ref.dot(T[0])).normalized()
        rings = []
        for i in range(n):
            if i > 0:
                N = (N - T[i] * N.dot(T[i])).normalized()
            B = T[i].cross(N)
            rr = radii[i] if radii is not None else r
            rings.append([self.bm.verts.new(P[i] + (N * math.cos(2 * math.pi * k / seg) + B * math.sin(2 * math.pi * k / seg)) * rr)
                          for k in range(seg)])
        for i in range(n - 1):
            for k in range(seg):
                kk = (k + 1) % seg
                self.face([rings[i][k], rings[i][kk], rings[i + 1][kk], rings[i + 1][k]], mat)
        if caps:
            self.face(list(reversed(rings[0])), mat)
            self.face(rings[-1], mat)

    def sweep(self, profile, path, mat="aluminium", closed_profile=True, closed_path=False, normal=(0, 0, 1)):
        """Barre un perfil 2D (x, y) a lo largo de una polilínea 3D PLANA (o casi).
        `normal` = vector fijo perpendicular al plano del recorrido: el perfil x va en (tangente x normal) y el perfil y va en `normal`.
        Ej.: marco de ventana en el plano XZ -> normal=(0, 1, 0) (y del perfil = profundidad); canalón horizontal -> normal=(0, 0, 1)."""
        P = [_v(p) for p in path]
        n = len(P)
        N = _v(normal).normalized()
        rings = []
        for i in range(n):
            if closed_path:
                a, b = P[(i - 1) % n], P[(i + 1) % n]
            else:
                a, b = P[max(i - 1, 0)], P[min(i + 1, n - 1)]
            t = (b - a)
            t = (t - N * t.dot(N)).normalized()
            side = t.cross(N).normalized()
            s = 1.0
            if 0 < i < n - 1 or closed_path:
                t0 = (P[i] - a).normalized()
                t1 = (b - P[i]).normalized()
                c = max(min(t0.dot(t1), 1.0), -0.95)
                s = 1.0 / max(math.cos(math.acos(c) / 2), 0.3)
            rings.append([self.bm.verts.new(P[i] + side * (x * s) + N * y) for x, y in profile])
        k = len(profile)
        segs = n if closed_path else n - 1
        kk_range = k if closed_profile else k - 1
        for i in range(segs):
            r0, r1 = rings[i], rings[(i + 1) % n]
            for j in range(kk_range):
                jj = (j + 1) % k
                self.face([r0[j], r0[jj], r1[jj], r1[j]], mat)
        if closed_profile and not closed_path:
            self.face(list(reversed(rings[0])), mat)
            self.face(rings[-1], mat)

    def plate(self, outline, thickness, mat="concrete", m=None):
        """Polígono 2D (x, y) extruido en +z `thickness`. Losas, placas, letreros."""
        bot = self._verts([(x, y, 0) for x, y in outline], m)
        top = self._verts([(x, y, thickness) for x, y in outline], m)
        self.face(list(reversed(bot)), mat)
        self.face(top, mat)
        k = len(outline)
        for i in range(k):
            j = (i + 1) % k
            self.face([bot[i], bot[j], top[j], top[i]], mat)

    def join(self, other, m=None):
        """Copia la geometría de otro MB (con su material por cara) aplicando la matriz `m`."""
        vmap = {}
        for v in other.bm.verts:
            vmap[v] = self.bm.verts.new((m @ v.co) if m is not None else v.co)
        for f in other.bm.faces:
            nf = self.bm.faces.new([vmap[v] for v in f.verts])
            nf.material_index = self.mi(other.mats[f.material_index])
            nf.smooth = f.smooth

    def transform(self, m):
        bmesh.ops.transform(self.bm, matrix=m, verts=self.bm.verts)

    # ---------------- salida ----------------
    def finish(self, name, collection=None, smooth_angle=30.0, merge=0.0001, uv_size=None):
        """Crea el objeto: merge by distance, normales recalculadas hacia fuera, sombreado suave por ángulo, UV de caja opcional."""
        bm = self.bm
        if merge:
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=merge)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        if uv_size:
            box_uv_bm(bm, uv_size)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        for nm in self.mats:
            me.materials.append(get_material(nm))
        for p in me.polygons:
            p.use_smooth = True
        me.set_sharp_from_angle(angle=math.radians(smooth_angle))
        ob = bpy.data.objects.new(name, me)
        (collection or bpy.context.scene.collection).objects.link(ob)
        return ob


# ---------------- muros con vanos (sin booleanos) ----------------
def wall_with_openings(mb, length, height, thickness, openings=(), mat_out="concrete", mat_in="plaster", mat_reveal="concrete",
                       m=None, reveal=True):
    """Muro en coordenadas locales: u = 0..length (eje X), v = 0..height (eje Z), cara exterior en y = 0, interior en y = thickness.
    openings: [(u0, u1, v0, v1)] rectángulos que atraviesan el muro (puertas: v0 = 0).
    Malla de cuadriláteros soldada (grid por las líneas de los vanos) + jambas/dintel/alféizar. `m` coloca el muro en el mundo."""
    us = sorted({0.0, float(length)} | {float(o[i]) for o in openings for i in (0, 1)})
    vs = sorted({0.0, float(height)} | {float(o[i]) for o in openings for i in (2, 3)})

    def hole(cu, cv):
        return any(o[0] <= cu <= o[1] and o[2] <= cv <= o[3] for o in openings)

    vf, vb = {}, {}

    def V(store, i, j, y):
        if (i, j) not in store:
            p = Vector((us[i], y, vs[j]))
            store[(i, j)] = mb.bm.verts.new((m @ p) if m is not None else p)
        return store[(i, j)]

    for i in range(len(us) - 1):
        for j in range(len(vs) - 1):
            cu, cv = (us[i] + us[i + 1]) / 2, (vs[j] + vs[j + 1]) / 2
            if hole(cu, cv):
                continue
            mb.face([V(vf, i, j, 0), V(vf, i + 1, j, 0), V(vf, i + 1, j + 1, 0), V(vf, i, j + 1, 0)], mat_out)
            mb.face([V(vb, i, j, thickness), V(vb, i, j + 1, thickness), V(vb, i + 1, j + 1, thickness), V(vb, i + 1, j, thickness)], mat_in)
    # bordes exteriores del muro (cierran el sólido)
    nu, nv = len(us) - 1, len(vs) - 1
    for i in range(nu):
        for j, jn in ((0, 0), (nv, nv)):
            cu = (us[i] + us[i + 1]) / 2
            cv = vs[j] + (1e-4 if j == 0 else -1e-4)
            if hole(cu, cv):
                continue
            a, b = (i, j), (i + 1, j)
            f = [V(vf, *a, 0), V(vf, *b, 0), V(vb, *b, thickness), V(vb, *a, thickness)]
            mb.face(f if j == 0 else list(reversed(f)), mat_reveal)
    for j in range(nv):
        for i in (0, nu):
            cv = (vs[j] + vs[j + 1]) / 2
            cu = us[i] + (1e-4 if i == 0 else -1e-4)
            if hole(cu, cv):
                continue
            a, b = (i, j), (i, j + 1)
            f = [V(vf, *a, 0), V(vf, *b, 0), V(vb, *b, thickness), V(vb, *a, thickness)]
            mb.face(f if i != 0 else list(reversed(f)), mat_reveal)
    # jambas, dintel y alféizar (las caras internas de cada vano), segmentadas por la rejilla para soldar
    if reveal:
        for (u0, u1, v0, v1) in openings:
            i0, i1 = us.index(float(u0)), us.index(float(u1))
            j0, j1 = vs.index(float(v0)), vs.index(float(v1))
            for i in range(i0, i1):  # alféizar (abajo) y dintel (arriba)
                if j0 > 0:
                    mb.face([V(vf, i, j0, 0), V(vb, i, j0, thickness), V(vb, i + 1, j0, thickness), V(vf, i + 1, j0, 0)], mat_reveal)
                if j1 < nv:
                    mb.face([V(vf, i + 1, j1, 0), V(vb, i + 1, j1, thickness), V(vb, i, j1, thickness), V(vf, i, j1, 0)], mat_reveal)
            for j in range(j0, j1):  # jambas
                if i0 > 0:
                    mb.face([V(vf, i0, j + 1, 0), V(vb, i0, j + 1, thickness), V(vb, i0, j, thickness), V(vf, i0, j, 0)], mat_reveal)
                if i1 < nu:
                    mb.face([V(vf, i1, j, 0), V(vb, i1, j, thickness), V(vb, i1, j + 1, thickness), V(vf, i1, j + 1, 0)], mat_reveal)
    return mb


# ---------------- UV ----------------
def box_uv_bm(bm, size=2.0, offset=(0.0, 0.0)):
    """Proyección de caja en espacio del objeto, sin espejo (texto legible), `size` m por unidad UV."""
    uv = bm.loops.layers.uv.verify()
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        s = 1 if n[ax] > 0 else -1
        for lp in f.loops:
            c = lp.vert.co
            if ax == 0:
                u, v = (c.y if s > 0 else -c.y), c.z
            elif ax == 1:
                u, v = (-c.x if s > 0 else c.x), c.z
            else:
                u, v = c.x, c.y
            lp[uv].uv = (u / size + offset[0], v / size + offset[1])


# ---------------- medición ----------------
def tri_count(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    tot = 0
    for o in objs:
        if o.type != "MESH":
            continue
        eo = o.evaluated_get(dg)
        me = eo.to_mesh()
        tot += sum(len(p.vertices) - 2 for p in me.polygons)
        eo.to_mesh_clear()
    return tot


def mesh_health(obj):
    """Cuenta aristas no-manifold, caras de área ~0 y vértices sueltos."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    zero = sum(1 for f in bm.faces if f.calc_area() < 1e-8)
    loose = sum(1 for v in bm.verts if not v.link_edges)
    bm.free()
    return {"non_manifold_edges": nm, "zero_area_faces": zero, "loose_verts": loose}


# ---------------- vista de arcilla ----------------
def clay_render(objs, out_path, res=(960, 540), samples=24, azim=35.0, elev=18.0, fov=40.0, margin=1.15, target=None, dist=None,
                ground=True, sun_azim=50.0, sun_elev=35.0):
    """Render de arcilla en Cycles CPU: material gris uniforme, cielo tenue + sol con sombras, piso opcional.
    Encuadra automáticamente los `objs` (azim 0 = vista desde -Y, la fachada principal)."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    try:
        sc.cycles.use_denoising = True
    except Exception:
        pass
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    try:
        sc.view_settings.view_transform = "AgX"
        sc.view_settings.look = "AgX - Medium High Contrast"
        sc.view_settings.exposure = -0.5
    except Exception:
        pass
    clay = bpy.data.materials.get("_clay") or bpy.data.materials.new("_clay")
    clay.diffuse_color = (0.42, 0.42, 0.42, 1)
    sc.view_layers[0].material_override = clay
    if sc.world is None:
        sc.world = bpy.data.worlds.new("W")
    w = sc.world
    w.use_nodes = True
    bg = next((n for n in w.node_tree.nodes if n.type == "BACKGROUND"), None)
    if bg is None:
        bg = w.node_tree.nodes.new("ShaderNodeBackground")
        out = next((n for n in w.node_tree.nodes if n.type == "OUTPUT_WORLD"), None) or w.node_tree.nodes.new("ShaderNodeOutputWorld")
        w.node_tree.links.new(bg.outputs[0], out.inputs[0])
    bg.inputs[0].default_value = (0.55, 0.62, 0.72, 1.0)
    bg.inputs[1].default_value = 0.28
    sun = bpy.data.objects.get("_sun")
    if sun is None:
        sun = bpy.data.objects.new("_sun", bpy.data.lights.new("_sun", "SUN"))
        sc.collection.objects.link(sun)
    sun.data.energy = 3.2
    sun.data.angle = math.radians(1.5)
    sun.rotation_euler = (math.radians(90 - sun_elev), 0, math.radians(sun_azim))  # luz viniendo desde -Y (lado de la fachada)
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    gnd = bpy.data.objects.get("_ground")
    if ground:
        if gnd is None:
            gm = bpy.data.meshes.new("_ground")
            gm.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
            gnd = bpy.data.objects.new("_ground", gm)
            sc.collection.objects.link(gnd)
        size = max((mx - mn).length * 3, 20.0)
        gnd.scale = (size, size, 1)
        gnd.location = ((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z - 0.001)
        gnd.hide_render = False
    elif gnd is not None:
        gnd.hide_render = True
    ctr = target if target is not None else (mn + mx) / 2
    rad = (mx - mn).length / 2 * margin
    cam = bpy.data.objects.get("_cam")
    if cam is None:
        cam = bpy.data.objects.new("_cam", bpy.data.cameras.new("_cam"))
        sc.collection.objects.link(cam)
    cam.data.angle = math.radians(fov)
    dd = dist if dist is not None else rad / math.sin(math.radians(fov) / 2)
    a, e = math.radians(azim), math.radians(elev)
    # azim 0 = mirando desde -Y (fachada principal)
    cam.location = ctr + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * dd
    cam.rotation_euler = (ctr - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_end = dd * 4
    sc.camera = cam
    sc.render.filepath = out_path
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    sc.view_layers[0].material_override = None
    return out_path


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    return sc
