"""lookdev.py — look-dev por capas (brief §4.6) y horneado a atlas únicos (§4.7) para el kit BLACKISLE.

Flujo por edificio:
  1. split_exterior(obj): separa caras exteriores (las que "ven" el cielo o el horizonte) de las interiores con rayos BVH.
  2. build_materials(cfg): materiales de look-dev procedurales en espacio de OBJETO (no dependen de UV) con las capas L0–L9:
     concreto en dos escalas, pintura vieja descascarada (K1), suciedad por oclusión, chorreados (K2), eflorescencia (K3),
     óxido (K6), musgo/algas en base y cara norte (K4), arena en horizontales y base, desgaste de aristas (Bevel) y el grafiti de PB
     proyectado por cara desde las capas RGBA de `texturas/graffiti`.
  3. unwrap(objs, name): UV únicas (Smart UV Project) en un canal 'atlas'.
  4. bake_atlas(objs, name, size): hornea color, rugosidad, normal (tangente) y AO con Cycles.
  5. final_material(...): Principled con imágenes horneadas (glTF): color sRGB, normal Non-Color, ORM (R=AO, G=rugosidad, B=metal).
"""
import math
import os

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
ENT = os.path.abspath(os.path.join(HERE, ".."))
TEX = os.path.join(ENT, "texturas")


# ------------------------------------------------------------------------------------------------
# 1. exterior / interior
# ------------------------------------------------------------------------------------------------
def split_exterior(obj, others=(), max_dist=60.0, n_dirs=5):
    """Clasifica cada cara: exterior si al menos un rayo (normal + 4 inclinaciones de 35°) escapa sin chocar en max_dist.
    `others`: objetos que también tapan (detalles, interior). Devuelve (obj_ext, obj_int) — nuevos objetos con las caras separadas."""
    dg = bpy.context.evaluated_depsgraph_get()
    occl = [obj] + [o for o in others if o.type == "MESH"]
    bms = []
    for o in occl:
        b = bmesh.new()
        b.from_object(o, dg)
        b.transform(o.matrix_world)
        bms.append(b)
    big = bmesh.new()
    for b in bms:
        big.from_mesh(_bm_to_mesh(b))
        b.free()
    tree = BVHTree.FromBMesh(big)
    big.free()
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    mw = obj.matrix_world
    ext = []
    for f in bm.faces:
        c = mw @ f.calc_center_median()
        n = (mw.to_3x3() @ f.normal).normalized()
        t = n.orthogonal().normalized()
        b2 = n.cross(t)
        dirs = [n]
        for k in range(n_dirs - 1):
            a = 2 * math.pi * k / (n_dirs - 1)
            dirs.append((n * math.cos(math.radians(35)) + (t * math.cos(a) + b2 * math.sin(a)) * math.sin(math.radians(35))).normalized())
        free = False
        for d in dirs:
            hit = tree.ray_cast(c + n * 0.004, d, max_dist)
            if hit[0] is None:
                free = True
                break
        ext.append(free)
    me_ext, me_int = _split_mesh(bm, ext)
    bm.free()
    for me in (me_ext, me_int):                     # mismos slots en el mismo orden: los índices por cara siguen valiendo
        for m in obj.data.materials:
            me.materials.append(m)
    oe = bpy.data.objects.new(obj.name + "_Ext", me_ext)
    oi = bpy.data.objects.new(obj.name + "_Int", me_int)
    for o in (oe, oi):
        o.matrix_world = obj.matrix_world
        for col in obj.users_collection:
            col.objects.link(o)
    return oe, oi


def _bm_to_mesh(b):
    me = bpy.data.meshes.new("_tmp")
    b.to_mesh(me)
    return me


def _split_mesh(bm, mask):
    """Copia las caras con mask=True a un mesh y el resto a otro (conserva materiales y UV)."""
    out = []
    for want in (True, False):
        b = bm.copy()
        kill = [f for f, m in zip(b.faces, mask) if m != want]
        bmesh.ops.delete(b, geom=kill, context="FACES")
        me = bpy.data.meshes.new("_split")
        b.to_mesh(me)
        b.free()
        out.append(me)
    return out


def copy_materials(src, dst):
    for m in src.data.materials:
        dst.data.materials.append(m)


# ------------------------------------------------------------------------------------------------
# 2. materiales de look-dev
# ------------------------------------------------------------------------------------------------
def _img(path, colorspace="sRGB"):
    name = os.path.basename(path)
    im = bpy.data.images.get(name) or bpy.data.images.load(path, check_existing=True)
    im.colorspace_settings.name = colorspace
    return im


class NB:
    """Ayudante mínimo para armar árboles de nodos."""

    def __init__(self, mat):
        mat.use_nodes = True
        self.nt = mat.node_tree
        self.nt.nodes.clear()
        self.x = 0

    def n(self, kind, **props):
        node = self.nt.nodes.new(kind)
        node.location = (self.x, 0)
        self.x += 220
        for k, v in props.items():
            if k.startswith("in_"):
                key = k[3:]
                node.inputs[int(key) if key.isdigit() else key.replace("_", " ")].default_value = v
            else:
                setattr(node, k, v)
        return node

    def link(self, a, b):
        self.nt.links.new(a, b)

    def math(self, op, a, b=None, clamp=False):
        m = self.n("ShaderNodeMath", operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                m.inputs[i].default_value = v
            else:
                self.link(v, m.inputs[i])
        return m.outputs[0]

    def mix(self, fac, a, b, blend="MIX"):
        m = self.n("ShaderNodeMix", data_type="RGBA", blend_type=blend, clamp_result=True)
        for sock, v in ((m.inputs[0], fac), (m.inputs[6], a), (m.inputs[7], b)):
            if isinstance(v, (int, float)):
                sock.default_value = v
            elif isinstance(v, tuple):
                sock.default_value = v
            else:
                self.link(v, sock)
        return m.outputs[2]

    def tex(self, path, size_m, coord, colorspace="sRGB", rot_z=0.0, offset=(0, 0, 0), blend=0.25):
        mp = self.n("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (1 / size_m, 1 / size_m, 1 / size_m)
        mp.inputs["Rotation"].default_value = (0, 0, rot_z)
        mp.inputs["Location"].default_value = offset
        self.link(coord, mp.inputs["Vector"])
        t = self.n("ShaderNodeTexImage", projection="BOX", projection_blend=blend, extension="REPEAT")
        t.image = _img(path, colorspace)
        self.link(mp.outputs[0], t.inputs[0])
        return t


BASE_COLORS = {   # color de material simple (los no-concreto) + rugosidad + metal
    "aluminium": ((0.55, 0.56, 0.56), 0.45, 1.0), "glass": ((0.25, 0.30, 0.30), 0.08, 0.0), "fabric": ((0.55, 0.50, 0.42), 0.95, 0.0),
    "cable": ((0.03, 0.03, 0.03), 0.6, 0.0), "plastic": ((0.70, 0.69, 0.64), 0.55, 0.0), "metal_paint": ((0.24, 0.27, 0.24), 0.6, 0.3),
    "rubble": ((0.46, 0.44, 0.40), 0.95, 0.0), "sand": ((0.74, 0.68, 0.54), 0.97, 0.0), "vegetation": ((0.22, 0.28, 0.12), 0.8, 0.0),
    "mortar": ((0.58, 0.56, 0.52), 0.95, 0.0),
}
TEX_FOR = {  # material -> (textura, tamaño m)
    "concrete": ("T1_concrete.png", 3.0), "plaster": ("T2_old_plaster_paint.png", 2.4), "brick": ("S1_brick_red_worn.png", 2.0),
    "tile": ("T3_roof_tile.png", 2.0), "wood": ("T4_wood_weathered.png", 1.6), "wood_dark": ("W1_wood_dark_planks.png", 1.8),
    "wood_grey": ("W2_wood_grey_clapboard.png", 1.8), "metal_rust": ("M1_rust_metal.png", 1.2), "roof_metal": ("R1_roof_corrugated_rust.png", 2.0),
    "roof_metal_light": ("R1_roof_corrugated_rust.png", 2.0),
}


def _graffiti_layer(nb, coord_obj, gmap, band_top):
    """Devuelve (color, alfa) del grafiti de PB proyectado en planta por cara (front/back/west/east) según la normal."""
    geo = nb.n("ShaderNodeNewGeometry")
    sep_n = nb.n("ShaderNodeSeparateXYZ")
    nb.link(geo.outputs["Normal"], sep_n.inputs[0])
    sep_p = nb.n("ShaderNodeSeparateXYZ")
    nb.link(coord_obj, sep_p.inputs[0])
    col_acc, a_acc = None, None
    for side, info in gmap.items():
        W, Hb = info["width_m"], info["height_m"]
        u_from = info["u_from"]       # ("x"|"y", origen, signo)
        axis, origin, sign = u_from
        u = nb.math("MULTIPLY", nb.math("SUBTRACT", sep_p.outputs[0 if axis == "x" else 1], origin), sign)
        u01 = nb.math("DIVIDE", u, W)
        v01 = nb.math("DIVIDE", sep_p.outputs[2], Hb)
        cmb = nb.n("ShaderNodeCombineXYZ")
        nb.link(u01, cmb.inputs[0])
        nb.link(v01, cmb.inputs[1])
        t = nb.n("ShaderNodeTexImage", extension="CLIP", interpolation="Cubic")
        t.image = _img(info["png"], "sRGB")
        t.image.alpha_mode = "STRAIGHT"
        nb.link(cmb.outputs[0], t.inputs[0])
        # selección por orientación de la cara
        nidx, nsgn = info["normal"]
        facing = nb.math("GREATER_THAN", nb.math("MULTIPLY", sep_n.outputs[nidx], nsgn), 0.6)
        a = nb.math("MULTIPLY", t.outputs["Alpha"], facing)
        if col_acc is None:
            col_acc, a_acc = t.outputs["Color"], a
        else:
            col_acc = nb.mix(a, col_acc, t.outputs["Color"])
            a_acc = nb.math("MAXIMUM", a_acc, a)
    return col_acc, a_acc


def lookdev_material(name, seed=0, gmap=None, band_top=4.25, paint_tint=(0.97, 0.92, 0.82)):
    """Material de look-dev para `name` (nombre canónico del kit). Concreto/aplanado llevan todas las capas; el resto, capas reducidas."""
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nb = NB(mat)
    out = nb.n("ShaderNodeOutputMaterial")
    bsdf = nb.n("ShaderNodeBsdfPrincipled")
    nb.link(bsdf.outputs[0], out.inputs[0])
    tc = nb.n("ShaderNodeTexCoord")
    co = tc.outputs["Object"]
    geo = nb.n("ShaderNodeNewGeometry")
    sep_n = nb.n("ShaderNodeSeparateXYZ")
    nb.link(geo.outputs["Normal"], sep_n.inputs[0])
    sep_p = nb.n("ShaderNodeSeparateXYZ")
    nb.link(co, sep_p.inputs[0])
    off = (seed * 0.37 % 1.0, seed * 0.61 % 1.0, 0)

    if name in TEX_FOR:
        fn, size = TEX_FOR[name]
        t1 = nb.tex(os.path.join(TEX, fn), size, co, offset=off)
        t2 = nb.tex(os.path.join(TEX, fn), size * 2.43, co, rot_z=0.6, offset=(off[1], off[0], 0))
        big = nb.n("ShaderNodeTexNoise", in_Scale=0.18, in_Detail=3.0)
        nb.link(co, big.inputs["Vector"])
        mask = nb.n("ShaderNodeMapRange", in_From_Min=0.42, in_From_Max=0.58, in_To_Min=0.0, in_To_Max=1.0, interpolation_type="SMOOTHSTEP")
        nb.link(big.outputs["Fac"], mask.inputs[0])
        base = nb.mix(mask.outputs[0], t1.outputs[0], t2.outputs[0])     # dos escalas mezcladas por ruido grande: sin repetición a 15 m
        rough_base, metal = 0.86, 0.0
        if name in ("metal_rust", "roof_metal", "roof_metal_light"):
            rough_base, metal = 0.7, 0.25
            if name == "roof_metal_light":
                base = nb.mix(0.55, base, (0.72, 0.72, 0.70, 1.0))
    else:
        c, rough_base, metal = BASE_COLORS.get(name, ((0.5, 0.5, 0.5), 0.8, 0.0))
        nz = nb.n("ShaderNodeTexNoise", in_Scale=6.0, in_Detail=6.0)
        nb.link(co, nz.inputs["Vector"])
        base = nb.mix(nb.math("MULTIPLY", nz.outputs["Fac"], 0.35), (*c, 1.0), (c[0] * 0.6, c[1] * 0.6, c[2] * 0.6, 1.0))
        t1 = None

    k = lambda fn, s, rot=0.0: nb.tex(os.path.join(TEX, fn), s, co, "Non-Color", rot_z=rot, offset=off).outputs[0]
    color = base
    if name == "plaster":
        # L1: pintura vieja (crema/ocre apagado) que se descascara mostrando el concreto (L0); dos escalas de K1 contra repetición
        conc = nb.tex(os.path.join(TEX, "T1_concrete.png"), 3.0, co, offset=off).outputs[0]
        hsv = nb.n("ShaderNodeHueSaturation", in_Saturation=0.5, in_Value=1.08)
        nb.link(color, hsv.inputs["Color"])
        tinted = nb.mix(0.6, hsv.outputs[0], (*paint_tint, 1.0), "MULTIPLY")
        k1a = k("K1_peel.png", 3.2, 0.3)
        k1b = k("K1_peel.png", 7.9, 1.9)
        nz3 = nb.n("ShaderNodeTexNoise", in_Scale=0.35, in_Detail=2.0)
        nb.link(co, nz3.inputs["Vector"])
        peel_v = nb.math("ADD", nb.math("MULTIPLY", k1a, 0.6), nb.math("MULTIPLY", k1b, 0.4))
        peel_v = nb.math("ADD", peel_v, nb.math("MULTIPLY", nb.math("SUBTRACT", nz3.outputs["Fac"], 0.5), 0.5))
        peel = nb.math("GREATER_THAN", peel_v, 0.48)
        color = nb.mix(peel, tinted, conc)
    if name in ("concrete", "plaster", "brick", "tile", "wood", "wood_dark", "wood_grey"):
        # L2: suciedad por cavidades (AO)
        ao = nb.n("ShaderNodeAmbientOcclusion", samples=8, only_local=True, in_Distance=0.6)
        dirt = nb.math("SUBTRACT", 1.0, ao.outputs["AO"], clamp=True)
        color = nb.mix(nb.math("MULTIPLY", dirt, 0.75), color, (0.12, 0.11, 0.09, 1.0), "MULTIPLY")
        vertical = nb.math("LESS_THAN", nb.math("ABSOLUTE", sep_n.outputs[2]), 0.5)
        # L3: chorreados de lluvia en verticales
        streak = nb.math("MULTIPLY", k("K2_rain_streaks.png", 3.6), vertical)
        color = nb.mix(nb.math("MULTIPLY", streak, 0.8), color, (0.18, 0.17, 0.15, 1.0), "MULTIPLY")
        # L4: eflorescencia (más abajo)
        low = nb.math("SUBTRACT", 1.0, nb.math("DIVIDE", sep_p.outputs[2], 6.0), clamp=True)
        eff = nb.math("MULTIPLY", nb.math("MULTIPLY", k("K3_efflorescence.png", 2.3, 1.1), low), 0.55)
        color = nb.mix(eff, color, (0.86, 0.85, 0.80, 1.0))
        # L5: óxido sangrando (manchas grandes, escasas)
        rustm = nb.math("MULTIPLY", nb.math("GREATER_THAN", k("K6_rust_bleed.png", 4.1, 2.0), 0.6), 0.5)
        color = nb.mix(nb.math("MULTIPLY", rustm, vertical), color, (0.36, 0.17, 0.07, 1.0), "MULTIPLY")
        # L6: musgo/algas en la base (z < 1,4) y en la cara norte (+Y)
        base_z = nb.math("SUBTRACT", 1.0, nb.math("DIVIDE", sep_p.outputs[2], 1.4), clamp=True)
        north = nb.math("MULTIPLY", nb.math("GREATER_THAN", sep_n.outputs[1], 0.5), 0.45)
        moss = nb.math("MULTIPLY", k("K4_moss.png", 1.9, 0.7), nb.math("MAXIMUM", base_z, north))
        color = nb.mix(nb.math("MULTIPLY", moss, 0.85), color, (0.20, 0.25, 0.11, 1.0))
        # L7: arena y polvo en horizontales hacia arriba y en la base
        up = nb.math("GREATER_THAN", sep_n.outputs[2], 0.7)
        ground = nb.math("SUBTRACT", 1.0, nb.math("DIVIDE", sep_p.outputs[2], 0.35), clamp=True)
        nz2 = nb.n("ShaderNodeTexNoise", in_Scale=1.5, in_Detail=4.0)
        nb.link(co, nz2.inputs["Vector"])
        sand = nb.math("MULTIPLY", nb.math("MAXIMUM", nb.math("MULTIPLY", up, 0.6), ground), nz2.outputs["Fac"])
        color = nb.mix(nb.math("MULTIPLY", sand, 1.2), color, (0.72, 0.65, 0.50, 1.0))
        # L8: desgaste de aristas (diferencia entre normal biselada y geométrica)
        bev = nb.n("ShaderNodeBevel", samples=8, in_Radius=0.025)
        dot = nb.n("ShaderNodeVectorMath", operation="DOT_PRODUCT")
        nb.link(bev.outputs[0], dot.inputs[0])
        nb.link(geo.outputs["Normal"], dot.inputs[1])
        edge = nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, dot.outputs["Value"]), 18.0, clamp=True)
        color = nb.mix(nb.math("MULTIPLY", edge, 0.5), color, (0.70, 0.68, 0.63, 1.0))
        nb.link(bev.outputs[0], bsdf.inputs["Normal"])
    if gmap and name in ("concrete", "plaster"):
        # L9: grafiti de PB (capa RGBA por cara) con el relieve del soporte atravesando la pintura
        gcol, ga = _graffiti_layer(nb, co, gmap, band_top)
        color = nb.mix(nb.math("MULTIPLY", ga, 0.95), color, gcol)
    nb.link(color, bsdf.inputs["Base Color"])
    rough = nb.n("ShaderNodeMapRange", in_From_Min=0.0, in_From_Max=1.0, in_To_Min=rough_base - 0.12, in_To_Max=min(rough_base + 0.1, 1.0))
    if t1 is not None:
        bw = nb.n("ShaderNodeRGBToBW")
        nb.link(t1.outputs[0], bw.inputs[0])
        nb.link(bw.outputs[0], rough.inputs[0])
        bump = nb.n("ShaderNodeBump", in_Strength=0.35, in_Distance=0.01)
        nb.link(bw.outputs[0], bump.inputs["Height"])
        if not bsdf.inputs["Normal"].is_linked:
            nb.link(bump.outputs[0], bsdf.inputs["Normal"])
    nb.link(rough.outputs[0], bsdf.inputs["Roughness"])
    bsdf.inputs["Metallic"].default_value = metal
    if name in ("glass",):
        bsdf.inputs["Transmission Weight"].default_value = 0.0      # vidrio sucio opaco-ish: las esquirlas no necesitan transmisión
    return mat


def graffiti_map(prefix, faces_info, x0, x1, y0, y1):
    """Arma el dict de capas de grafiti para lookdev_material a partir del JSON de compose (G_<ID>_mapa.json)."""
    rel = {"front": (("x", x0, 1.0), (1, -1.0)), "back": (("x", x1, -1.0), (1, 1.0)),
           "west": (("y", y1, -1.0), (0, -1.0)), "east": (("y", y0, 1.0), (0, 1.0))}
    gm = {}
    for side, info in faces_info.items():
        u_from, normal = rel[side]
        gm[side] = dict(width_m=info["width_m"], height_m=info["height_m"], u_from=u_from, normal=normal,
                        png=os.path.join(TEX, "graffiti", f"{prefix}_{side}.png"))
    return gm


# ------------------------------------------------------------------------------------------------
# 3–4. UV y horneado
# ------------------------------------------------------------------------------------------------
def unwrap(obj, uv_name="atlas", angle=66.0, margin=0.004, make_active=True):
    me = obj.data
    if uv_name not in me.uv_layers:
        me.uv_layers.new(name=uv_name)
    me.uv_layers.active = me.uv_layers[uv_name]
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin, area_weight=0.0, correct_aspect=True,
                             scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    if make_active:
        me.uv_layers[uv_name].active_render = True


def bake(obj, img_name, bake_type, size, out_dir, samples=32, margin=16, colorspace="sRGB", uv_name="atlas", **kw):
    """Hornea `bake_type` del objeto a una imagen nueva size² guardada en out_dir/img_name.png."""
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    img = bpy.data.images.new(img_name, size, size, alpha=False, float_buffer=False)
    img.colorspace_settings.name = colorspace
    obj.data.uv_layers.active = obj.data.uv_layers[uv_name]
    nodes_added = []
    for m in obj.data.materials:
        nt = m.node_tree
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = img
        nt.nodes.active = n
        nodes_added.append((nt, n))
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    sc.render.bake.margin = margin
    sc.render.bake.use_clear = True
    bpy.ops.object.bake(type=bake_type, margin=margin, use_clear=True, **kw)
    img.filepath_raw = os.path.join(out_dir, img_name + ".png")
    img.file_format = "PNG"
    img.save()
    for nt, n in nodes_added:
        nt.nodes.remove(n)
    return img


def pack_orm(ao_img, rough_img, metal_value, out_path):
    import numpy as np
    w, h = ao_img.size
    ao = np.array(ao_img.pixels[:], dtype=np.float32).reshape(h, w, 4)[..., 0]
    ro = np.array(rough_img.pixels[:], dtype=np.float32).reshape(h, w, 4)[..., 0]
    orm = np.dstack([ao, ro, np.full_like(ao, metal_value), np.ones_like(ao)])
    img = bpy.data.images.new(os.path.basename(out_path).split(".")[0], w, h, alpha=False)
    img.colorspace_settings.name = "Non-Color"
    img.pixels[:] = orm.ravel()
    img.filepath_raw = out_path
    img.file_format = "PNG"
    img.save()
    return img


# ------------------------------------------------------------------------------------------------
# 5. material final (glTF)
# ------------------------------------------------------------------------------------------------
def final_material(name, albedo, normal, orm, uv_name="atlas"):
    mat = bpy.data.materials.new(name)
    nb = NB(mat)
    out = nb.n("ShaderNodeOutputMaterial")
    bsdf = nb.n("ShaderNodeBsdfPrincipled")
    nb.link(bsdf.outputs[0], out.inputs[0])
    uv = nb.n("ShaderNodeUVMap", uv_map=uv_name)
    ta = nb.n("ShaderNodeTexImage")
    ta.image = albedo
    nb.link(uv.outputs[0], ta.inputs[0])
    nb.link(ta.outputs[0], bsdf.inputs["Base Color"])
    tn = nb.n("ShaderNodeTexImage")
    tn.image = normal
    tn.image.colorspace_settings.name = "Non-Color"
    nb.link(uv.outputs[0], tn.inputs[0])
    nm = nb.n("ShaderNodeNormalMap", uv_map=uv_name)
    nb.link(tn.outputs[0], nm.inputs["Color"])
    nb.link(nm.outputs[0], bsdf.inputs["Normal"])
    to = nb.n("ShaderNodeTexImage")
    to.image = orm
    to.image.colorspace_settings.name = "Non-Color"
    nb.link(uv.outputs[0], to.inputs[0])
    sp = nb.n("ShaderNodeSeparateColor")
    nb.link(to.outputs[0], sp.inputs[0])
    nb.link(sp.outputs[1], bsdf.inputs["Roughness"])
    nb.link(sp.outputs[2], bsdf.inputs["Metallic"])
    # oclusión (R) para el exportador glTF: grupo "glTF Material Output"
    grp = bpy.data.node_groups.get("glTF Material Output")
    if grp is None:
        grp = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        grp.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    gn = nb.n("ShaderNodeGroup")
    gn.node_tree = grp
    nb.link(sp.outputs[0], gn.inputs["Occlusion"])
    return mat
