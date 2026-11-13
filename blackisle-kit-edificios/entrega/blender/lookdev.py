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
def _footprint_grid(bm, mw, cell=0.25, zmin=1.0):
    """Planta del edificio como rejilla 2D: celdas cubiertas por caras hacia arriba por encima de `zmin` (losas de piso, de
    azotea, de balcón). Devuelve inside(x, y) -> bool. Sin caras así (cabañas) devuelve siempre False."""
    from mathutils.geometry import intersect_point_tri_2d
    cells = set()
    for f in bm.faces:
        n = (mw.to_3x3() @ f.normal).normalized()
        if n.z < 0.9:
            continue
        pts = [(mw @ v.co) for v in f.verts]
        if sum(p.z for p in pts) / len(pts) < zmin:
            continue
        p2 = [Vector((p.x, p.y)) for p in pts]
        x0, x1 = min(p.x for p in p2), max(p.x for p in p2)
        y0, y1 = min(p.y for p in p2), max(p.y for p in p2)
        for i in range(int(math.floor(x0 / cell)), int(math.floor(x1 / cell)) + 1):
            for j in range(int(math.floor(y0 / cell)), int(math.floor(y1 / cell)) + 1):
                if (i, j) in cells:
                    continue
                q = Vector(((i + 0.5) * cell, (j + 0.5) * cell))
                if any(intersect_point_tri_2d(q, p2[0], p2[k], p2[k + 1]) for k in range(1, len(p2) - 1)):
                    cells.add((i, j))
    grown = set(cells)                                  # cierra rendijas de una celda (juntas, bordes de losa)
    for (i, j) in cells:
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                grown.add((i + di, j + dj))
    return lambda x, y: (int(math.floor(x / cell)), int(math.floor(y / cell))) in grown


def _inside_run(inside, c, d, step=0.2, cap=12.0):
    """Recorrido horizontal (m) del rayo dentro de la planta antes de salir. Rayos casi verticales: 0."""
    h = Vector((d.x, d.y))
    if h.length < 0.3:
        return 0.0
    h.normalize()
    s = 0.0
    while s < cap and inside(c.x + h.x * s, c.y + h.y * s):
        s += step
    return s


def _rects_inside(rects):
    return lambda x, y: any(x0 <= x <= x1 and y0 <= y <= y1 for (x0, x1, y0, y1) in rects)


def split_exterior(obj, others=(), max_dist=60.0, n_dirs=5, max_inside=3.0, footprint=None):
    """Clasifica cada cara: exterior si al menos un rayo (normal + 4 inclinaciones de 35°) escapa sin chocar en max_dist y,
    antes de salir de la planta del edificio, recorre dentro de ella como mucho `max_inside` m. Lo segundo evita que la cara
    interior de un muro de fachada pase por exterior porque su rayo cruza una enfilada de puertas y sale por la fachada de
    enfrente (APT_D); logias, galerías, balcones y el rincón de la L quedan dentro de esos 3 m.
    `others`: objetos que también tapan (detalles, interior). footprint: [(x0, x1, y0, y1)] planta explícita de los recintos
    cerrados (muelle: la cubierta es una losa enorme y no sirve para deducir la planta de la nave).
    Devuelve (obj_ext, obj_int) — nuevos objetos con las caras separadas."""
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
    inside = _rects_inside(footprint) if footprint else _footprint_grid(bm, mw)
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
            if hit[0] is None and _inside_run(inside, c, d) <= max_inside:
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
    "aluminium": ((0.55, 0.56, 0.56), 0.45, 1.0), "glass": ((0.10, 0.125, 0.125), 0.08, 0.0), "fabric": ((0.55, 0.50, 0.42), 0.95, 0.0),
    "cable": ((0.03, 0.03, 0.03), 0.6, 0.0), "plastic": ((0.70, 0.69, 0.64), 0.55, 0.0), "metal_paint": ((0.24, 0.27, 0.24), 0.6, 0.3),
    "rubble": ((0.46, 0.44, 0.40), 0.95, 0.0), "sand": ((0.74, 0.68, 0.54), 0.97, 0.0), "vegetation": ((0.22, 0.28, 0.12), 0.8, 0.0),
    "mortar": ((0.58, 0.56, 0.52), 0.95, 0.0), "paper": ((0.70, 0.67, 0.58), 0.9, 0.0),
    # hospital (HOS_1)
    "plastic_blue": ((0.05, 0.17, 0.50), 0.45, 0.0), "linen": ((0.80, 0.80, 0.78), 0.9, 0.0),
    "sign_red": ((0.55, 0.04, 0.04), 0.5, 0.0), "sign_white": ((0.84, 0.84, 0.82), 0.45, 0.0),
    "sign_blue": ((0.02, 0.15, 0.52), 0.45, 0.0), "sign_green": ((0.02, 0.38, 0.11), 0.45, 0.0),
    "paint_yellow": ((0.72, 0.50, 0.04), 0.6, 0.0), "vinyl": ((0.07, 0.20, 0.19), 0.5, 0.0),
    "steel": ((0.60, 0.61, 0.62), 0.35, 1.0), "rubber": ((0.025, 0.025, 0.025), 0.8, 0.0),
    "wool_blue": ((0.10, 0.17, 0.33), 0.97, 0.0), "enamel": ((0.50, 0.53, 0.51), 0.42, 0.15),
    # granero con tienda (GRA_1): paja, costal, cartón y vidrio ámbar (botellas)
    "hay": ((0.60, 0.48, 0.24), 0.92, 0.0), "burlap": ((0.46, 0.37, 0.25), 0.95, 0.0),
    "cardboard": ((0.55, 0.42, 0.27), 0.85, 0.0), "amber": ((0.30, 0.13, 0.03), 0.12, 0.0),
    # sitio de telecom (COM_1): galvanizado por inmersión, cobre de tierras, grava triturada y radomo de fibra de vidrio
    "galvanized": ((0.56, 0.58, 0.59), 0.45, 1.0), "copper": ((0.72, 0.40, 0.25), 0.38, 1.0),
    "gravel": ((0.45, 0.45, 0.45), 0.95, 0.0), "radome": ((0.74, 0.75, 0.74), 0.55, 0.0),
    # base militar (MIL_1 / MIL_2): lona, costal, geotextil, red, madera y pinturas militares, armas
    "canvas": ((0.25, 0.27, 0.16), 0.92, 0.0), "sandbag": ((0.55, 0.48, 0.33), 0.9, 0.0),
    "geotextile": ((0.52, 0.44, 0.31), 0.95, 0.0), "net": ((0.45, 0.39, 0.27), 0.9, 0.0),
    "wood_od": ((0.20, 0.22, 0.13), 0.75, 0.0), "plywood": ((0.60, 0.48, 0.33), 0.8, 0.0),
    "paint_od": ((0.20, 0.22, 0.13), 0.55, 0.1), "paint_tan": ((0.56, 0.46, 0.30), 0.55, 0.1),
    "rack_orange": ((0.70, 0.19, 0.03), 0.45, 0.1), "rack_blue": ((0.03, 0.10, 0.38), 0.45, 0.1),
    "brass": ((0.62, 0.45, 0.16), 0.3, 1.0), "gunmetal": ((0.07, 0.075, 0.08), 0.45, 0.85),
    "polymer": ((0.10, 0.10, 0.095), 0.6, 0.0),
}
TEX_FOR = {  # material -> (textura, tamaño m)
    "concrete": ("T1_concrete.png", 3.0), "plaster": ("T2_old_plaster_paint.png", 2.4), "brick": ("S1_brick_red_worn.png", 2.0),
    "tile": ("T3_roof_tile.png", 2.0), "wood": ("T4_wood_weathered.png", 1.6), "wood_dark": ("W1_wood_dark_planks.png", 1.8),
    "wood_grey": ("W2_wood_grey_clapboard.png", 1.8), "metal_rust": ("M1_rust_metal.png", 1.2), "roof_metal": ("R1_roof_corrugated_rust.png", 2.0),
    "roof_metal_light": ("R1_roof_corrugated_rust.png", 2.0),
    # granero con tienda (GRA_1): tabla roja de granero y block de concreto
    "wood_red": ("T10_tabla_roja.png", 2.4), "block": ("T11_block.png", 2.4),
    # sitio de telecom (COM_1)
    "galvanized": ("T13_galvanizado.png", 1.0), "gravel": ("T14_grava.png", 1.2),
}
CLAD_WEAR_K = 0.55   # con wear < 1 la lámina pintada pierde menos pintura: umbral 0,56 + (1 - wear) * K


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
        if info.get("depth"):            # capa limitada a una franja de profundidad (varios muros que miran al mismo lado)
            dax, dlo, dhi = info["depth"]
            dc = sep_p.outputs[dax]
            inside = nb.math("MULTIPLY", nb.math("GREATER_THAN", dc, dlo), nb.math("LESS_THAN", dc, dhi))
            facing = nb.math("MULTIPLY", facing, inside)
        a = nb.math("MULTIPLY", t.outputs["Alpha"], facing)
        if col_acc is None:
            col_acc, a_acc = t.outputs["Color"], a
        else:
            col_acc = nb.mix(a, col_acc, t.outputs["Color"])
            a_acc = nb.math("MAXIMUM", a_acc, a)
    return col_acc, a_acc


CLAD_PAINT = {   # lámina pintada sobre óxido (muelle): color de la pintura vieja
    "cladding": (0.60, 0.62, 0.60),     # nave: gris verdoso deslavado
    "container": (0.24, 0.36, 0.40),    # contenedores: azul petróleo deslavado
    "cladding_tan": (0.56, 0.45, 0.29), # almacén militar (MIL_1): lámina R color arena, en uso
}


def lookdev_material(name, seed=0, gmap=None, band_top=4.25, paint_tint=(0.88, 0.88, 0.86), under="concrete", dust_h=0.35,
                     base_z=0.0, graffiti_mats=("concrete", "plaster"), wear=1.0, band=None, paint_sat=0.15):
    """Material de look-dev para `name` (nombre canónico del kit). Concreto/aplanado llevan todas las capas; el resto, capas reducidas.
    base_z: cota del piso del modelo (musgo, polvo y salpicaduras se miden desde ahí; 0 en edificios, la cubierta en el muelle).
    graffiti_mats: materiales que reciben la capa de grafiti.
    wear: 1 = abandono (departamentos, cabañas, muelle); < 1 = edificio en uso: menos descascarado, chorreado, eflorescencia,
    óxido y musgo (hospital 0,35). band: (altura sobre base_z, color lineal) del zoclo pintado del aplanado.
    paint_sat: saturación que conserva la pintura del aplanado (0,15 = casi gris; el hospital usa 1 para su crema)."""
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
    if name in CLAD_PAINT:
        # L1 (lámina): pintura vieja sobre óxido; se cae por zonas, en bordes y cavidades (AO) y en la franja baja (salpicadura)
        rust = nb.tex(os.path.join(TEX, "M1_rust_metal.png"), 1.2, co, offset=off)
        t1 = rust
        rough_base, metal = 0.62, 0.12
        pc = CLAD_PAINT[name]
        nzp = nb.n("ShaderNodeTexNoise", in_Scale=0.6, in_Detail=4.0)
        nb.link(co, nzp.inputs["Vector"])
        paint = nb.mix(nb.math("MULTIPLY", nzp.outputs["Fac"], 0.5), (*pc, 1.0), (pc[0] * 0.78, pc[1] * 0.78, pc[2] * 0.76, 1.0))
        k1a = k("K1_peel.png", 2.1, 0.4)
        k1b = k("K1_peel.png", 5.3, 1.3)
        zone = nb.n("ShaderNodeTexNoise", in_Scale=0.09, in_Detail=2.0)
        nb.link(co, zone.inputs["Vector"])
        pv = nb.math("ADD", nb.math("MULTIPLY", k1a, 0.6), nb.math("MULTIPLY", k1b, 0.4))
        pv = nb.math("ADD", pv, nb.math("MULTIPLY", nb.math("SUBTRACT", zone.outputs["Fac"], 0.5), 0.8))
        lowp = nb.math("SUBTRACT", 1.0, nb.math("DIVIDE", nb.math("SUBTRACT", sep_p.outputs[2], base_z), 1.8), clamp=True)
        pv = nb.math("ADD", pv, nb.math("MULTIPLY", lowp, 0.22))
        aop = nb.n("ShaderNodeAmbientOcclusion", samples=8, only_local=True, in_Distance=0.4)
        pv = nb.math("ADD", pv, nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, aop.outputs["AO"], clamp=True), 0.35))
        color = nb.mix(nb.math("GREATER_THAN", pv, 0.56 + (1.0 - wear) * CLAD_WEAR_K), paint, rust.outputs[0])
    if name == "plaster":
        # L1: pintura vieja (crema/ocre apagado) que se descascara mostrando el concreto (L0); dos escalas de K1 contra repetición
        # under: lo que asoma bajo la pintura ('concrete' = losa/columna colada; 'brick' = relleno de tabique, APT_B/APT_C)
        conc = nb.tex(os.path.join(TEX, "T1_concrete.png"), 3.0, co, offset=off).outputs[0]
        # pintura vieja casi gris (brief: concreto gris gastado). 0,15: con 0,28 el ocre de T2 dejaba manchas canela parejas en todas
        # las caras y en Three.js los muros derivaban a marrón grisáceo (revisiones de aceptación de A y D)
        hsv = nb.n("ShaderNodeHueSaturation", in_Saturation=paint_sat, in_Value=1.05)
        nb.link(color, hsv.inputs["Color"])
        tinted = nb.mix(0.6, hsv.outputs[0], (*paint_tint, 1.0), "MULTIPLY")
        if wear < 1.0:                     # pintura mantenida: el tinte manda sobre la mancha del aplanado viejo
            tinted = nb.mix(0.55 + 0.25 * (1.0 - wear), tinted, (*paint_tint, 1.0))
        if band is not None:
            bh, bc = band
            nzb = nb.n("ShaderNodeTexNoise", in_Scale=40.0, in_Detail=2.0)
            nb.link(co, nzb.inputs["Vector"])
            zb = nb.math("ADD", nb.math("SUBTRACT", sep_p.outputs[2], base_z), nb.math("MULTIPLY", nb.math("SUBTRACT", nzb.outputs["Fac"], 0.5), 0.006))
            inband = nb.math("LESS_THAN", zb, bh)
            bcol = nb.mix(nb.math("MULTIPLY", nzb.outputs["Fac"], 0.3), (*bc, 1.0), (bc[0] * 0.8, bc[1] * 0.8, bc[2] * 0.8, 1.0))
            tinted = nb.mix(inband, tinted, bcol)
        k1a = k("K1_peel.png", 3.2, 0.3)
        k1b = k("K1_peel.png", 7.9, 1.9)
        nz3 = nb.n("ShaderNodeTexNoise", in_Scale=0.35, in_Detail=2.0)
        nb.link(co, nz3.inputs["Vector"])
        peel_v = nb.math("ADD", nb.math("MULTIPLY", k1a, 0.6), nb.math("MULTIPLY", k1b, 0.4))
        peel_v = nb.math("ADD", peel_v, nb.math("MULTIPLY", nb.math("SUBTRACT", nz3.outputs["Fac"], 0.5), 0.5))
        # por zonas, no parejo: manchas grandes de humedad (ruido a ~14 m), más en el zócalo y junto a esquinas y juntas (AO);
        # umbral 0,52 (antes 0,48): menos descascarado a media placa
        zone = nb.n("ShaderNodeTexNoise", in_Scale=0.07, in_Detail=2.0)
        nb.link(co, zone.inputs["Vector"])
        peel_v = nb.math("ADD", peel_v, nb.math("MULTIPLY", nb.math("SUBTRACT", zone.outputs["Fac"], 0.5), 0.7))
        plinth = nb.math("SUBTRACT", 1.0, nb.math("DIVIDE", sep_p.outputs[2], 1.6), clamp=True)
        peel_v = nb.math("ADD", peel_v, nb.math("MULTIPLY", plinth, 0.12))
        ao_p = nb.n("ShaderNodeAmbientOcclusion", samples=8, only_local=True, in_Distance=0.5)
        peel_v = nb.math("ADD", peel_v, nb.math("MULTIPLY", nb.math("SUBTRACT", 1.0, ao_p.outputs["AO"], clamp=True), 0.35))
        # wear 1 (abandono) -> umbral 0,52 sin cambios; edificio en uso (hospital, wear 0,08) -> ~1,16: solo despostilladuras
        # sueltas en esquinas y zoclo (con 0,32 el hospital seguía con medio zoclo descascarado: revisión de la vista de calle)
        peel = nb.math("GREATER_THAN", peel_v, 0.52 + (1.0 - wear) * 0.70)
        if under == "brick":
            # bajo la pintura queda el repellado gris; el tabique solo asoma donde se cayó también el repellado: parches grandes y
            # escasos, más en PB que arriba (conceptos de B y C: muros grises, ladrillo en PB, esquinas y bajo el alero)
            brick = nb.tex(os.path.join(TEX, "S1_brick_red_worn.png"), 2.0, co, offset=off).outputs[0]
            nzb = nb.n("ShaderNodeTexNoise", in_Scale=0.22, in_Detail=3.0, in_Roughness=0.55)
            nb.link(co, nzb.inputs["Vector"])
            hz = nb.math("DIVIDE", nb.math("SUBTRACT", sep_p.outputs[2], 2.8), 2.5, clamp=True)
            thr = nb.math("ADD", 0.57, nb.math("MULTIPLY", hz, 0.11))
            bfield = nb.math("ADD", nzb.outputs["Fac"], nb.math("MULTIPLY", nb.math("SUBTRACT", peel_v, 0.52), 0.35))
            bmask = nb.math("MULTIPLY", nb.math("GREATER_THAN", bfield, thr), peel)
            conc = nb.mix(bmask, conc, brick)
        color = nb.mix(peel, tinted, conc)
    if name in ("concrete", "plaster", "brick", "tile", "wood", "wood_dark", "wood_grey", "wood_red", "block") + tuple(CLAD_PAINT):
        zr = nb.math("SUBTRACT", sep_p.outputs[2], base_z)                 # altura sobre el piso del modelo
        # L2: suciedad por cavidades (AO)
        ao = nb.n("ShaderNodeAmbientOcclusion", samples=8, only_local=True, in_Distance=0.6)
        dirt = nb.math("SUBTRACT", 1.0, ao.outputs["AO"], clamp=True)
        color = nb.mix(nb.math("MULTIPLY", dirt, 0.75 * (0.5 + 0.5 * wear)), color, (0.12, 0.115, 0.105, 1.0), "MULTIPLY")
        vertical = nb.math("LESS_THAN", nb.math("ABSOLUTE", sep_n.outputs[2]), 0.5)
        # L3: chorreados de lluvia en verticales
        streak = nb.math("MULTIPLY", k("K2_rain_streaks.png", 3.6), vertical)
        color = nb.mix(nb.math("MULTIPLY", streak, 0.8 * (0.35 + 0.65 * wear)), color, (0.17, 0.168, 0.16, 1.0), "MULTIPLY")
        # L4: eflorescencia (más abajo)
        low = nb.math("SUBTRACT", 1.0, nb.math("DIVIDE", zr, 6.0), clamp=True)
        eff = nb.math("MULTIPLY", nb.math("MULTIPLY", k("K3_efflorescence.png", 2.3, 1.1), low), 0.55 * wear)
        color = nb.mix(eff, color, (0.86, 0.85, 0.80, 1.0))
        # L5: óxido sangrando (manchas grandes, escasas)
        # (umbral 0,72 y tono pardo apagado: con 0,6 y naranja saturado los muros se leían marrón camuflaje en Three.js)
        rustm = nb.math("MULTIPLY", nb.math("GREATER_THAN", k("K6_rust_bleed.png", 4.1, 2.0), 0.72), 0.4 * wear)
        color = nb.mix(nb.math("MULTIPLY", rustm, vertical), color, (0.42, 0.31, 0.22, 1.0), "MULTIPLY")
        # L6: musgo/algas en la base (z < 1,4) y en la cara norte (+Y)
        base_zz = nb.math("SUBTRACT", 1.0, nb.math("DIVIDE", zr, 1.4), clamp=True)
        north = nb.math("MULTIPLY", nb.math("GREATER_THAN", sep_n.outputs[1], 0.5), 0.45)
        moss = nb.math("MULTIPLY", k("K4_moss.png", 1.9, 0.7), nb.math("MAXIMUM", base_zz, north))
        color = nb.mix(nb.math("MULTIPLY", moss, 0.85 * wear), color, (0.20, 0.25, 0.11, 1.0))
        # L7: arena y polvo en horizontales hacia arriba y en la base
        up = nb.math("GREATER_THAN", sep_n.outputs[2], 0.7)
        ground = nb.math("SUBTRACT", 1.0, nb.math("DIVIDE", zr, dust_h), clamp=True)   # 0,35 m con duna; 0,12 sin
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
    if gmap and name in graffiti_mats:
        # L9: grafiti de PB (capa RGBA por cara) con el relieve del soporte atravesando la pintura
        gcol, ga = _graffiti_layer(nb, co, gmap, band_top)
        # alfa x1,3 (tope 1): el desgaste del panel ya rompe la pintura; con 0,95 las piezas se perdían a 15 m en Three.js
        color = nb.mix(nb.math("MINIMUM", nb.math("MULTIPLY", ga, 1.3), 1.0), color, gcol)
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
    for key, info in faces_info.items():
        side = info.get("side", key)            # varias capas por lado: clave libre + 'side' + 'depth' [eje, mín, máx]
        u_from, normal = rel[side]
        gm[key] = dict(width_m=info["width_m"], height_m=info["height_m"], u_from=u_from, normal=normal, depth=info.get("depth"),
                       png=os.path.join(TEX, "graffiti", f"{prefix}_{key}.png"))
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
