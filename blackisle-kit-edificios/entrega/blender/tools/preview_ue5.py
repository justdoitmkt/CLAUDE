"""preview_ue5.py — vista previa del kit UE5 en Cycles usando SOLO los archivos del kit (GLB por parte, texturas y
manifiesto.json), con los materiales armados según la especificación del manifiesto (la misma que sigue el script de Unreal):
repetibles con tinte, color por vértice, variación grande, normal (DirectX -> se invierte el verde para Blender) y ORM;
vidrio con transmisión real y suciedad; atlas de muros con su normal y ORM. Suelo gris liso (el kit no trae terreno).

Uso: /root/blk-venv/bin/python tools/preview_ue5.py --id APT_A_5p [--kit ruta] [--out carpeta] [--samples 64]
Escribe <out>/<ID>_ue5_exterior.png y <ID>_ue5_interior.png (toma 1 del recorrido, con dos bombillas).
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

ENT = os.path.abspath(os.path.join(HERE, "..", ".."))
PREFIX = {"APT_A_5p": "A", "APT_B_4p": "B", "APT_C_3p": "C", "APT_D_4p": "D", "CAB_1_tablones": "CAB_1",
          "CAB_2_pilotes": "CAB_2", "CAB_3_ladrillo": "CAB_3", "MUE_1_carga": "MUE_1",
          "HOS_1_pueblo": "HOS_1"}


EXTRA_VIEWS = {   # (nombre, cámara, objetivo, lente mm) en ejes de Blender
    "MUE_1_carga": [("playa", (-12.0, -38.0, 2.6), (3.0, 8.0, 4.0), 26), ("mar", (38.0, 90.0, 3.0), (10.0, 30.0, 3.0), 32),
                    ("atraque", (30.0, 64.0, 1.2), (20.0, 51.0, 1.8), 28)],
    "HOS_1_pueblo": [("calle", (-16.0, -34.0, 1.7), (2.0, -4.0, 2.6), 26), ("urgencias", (26.0, -24.0, 1.7), (15.0, -8.0, 2.2), 28),
                     ("trasera", (12.0, 30.0, 2.0), (2.0, 10.0, 1.6), 26), ("pasillo", (-12.6, -2.9, 1.6), (6.0, -2.9, 1.5), 18),
                     ("encamados", (-5.6, 5.0, 1.6), (-11.0, 9.0, 0.8), 18)],
}


class NT:
    def __init__(self, mat):
        mat.use_nodes = True
        self.t = mat.node_tree
        self.t.nodes.clear()

    def n(self, kind, **kw):
        node = self.t.nodes.new(kind)
        for k, v in kw.items():
            if k.startswith("i_"):
                node.inputs[k[2:].replace("_", " ")].default_value = v
            else:
                setattr(node, k, v)
        return node

    def l(self, a, b):
        self.t.links.new(a, b)


def img(path, non_color=False):
    im = bpy.data.images.load(path, check_existing=True)
    if non_color:
        im.colorspace_settings.name = "Non-Color"
    return im


def tex(nt, path, uv, non_color=False):
    t = nt.n("ShaderNodeTexImage")
    t.image = img(path, non_color)
    nt.l(uv, t.inputs[0])
    return t


def normal_dx(nt, t):
    """Mapa DirectX del kit -> espacio tangente de Blender (OpenGL): verde invertido."""
    sep = nt.n("ShaderNodeSeparateColor")
    nt.l(t.outputs[0], sep.inputs[0])
    inv = nt.n("ShaderNodeMath", operation="SUBTRACT", i_Value=1.0)
    inv.inputs[0].default_value = 1.0
    nt.l(sep.outputs[1], inv.inputs[1])
    comb = nt.n("ShaderNodeCombineColor")
    nt.l(sep.outputs[0], comb.inputs[0])
    nt.l(inv.outputs[0], comb.inputs[1])
    nt.l(sep.outputs[2], comb.inputs[2])
    nm = nt.n("ShaderNodeNormalMap")
    nt.l(comb.outputs[0], nm.inputs["Color"])
    return nm


def lerp1(nt, b_socket, alpha):
    """lerp(1, b, alpha) en color."""
    mx = nt.n("ShaderNodeMix", data_type="RGBA", blend_type="MIX")
    mx.inputs[0].default_value = alpha
    mx.inputs[6].default_value = (1, 1, 1, 1)
    nt.l(b_socket, mx.inputs[7])
    return mx.outputs[2]


def build_material(name, spec, tdir_c, tdir_m):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    nt = NT(mat)
    out = nt.n("ShaderNodeOutputMaterial")
    b = nt.n("ShaderNodeBsdfPrincipled")
    nt.l(b.outputs[0], out.inputs[0])
    kind = spec["maestro"]
    uvn = nt.n("ShaderNodeUVMap", uv_map="UVMap")
    vc = nt.n("ShaderNodeVertexColor", layer_name="Color")
    if kind == "M_BLK_Atlas":
        T = spec["texturas"]
        bc = tex(nt, os.path.join(tdir_m, T["BC"] + ".jpg"), uvn.outputs[0])
        nm = normal_dx(nt, tex(nt, os.path.join(tdir_m, T["N"] + ".png"), uvn.outputs[0], True))
        orm = nt.n("ShaderNodeSeparateColor")
        nt.l(tex(nt, os.path.join(tdir_m, T["ORM"] + ".png"), uvn.outputs[0], True).outputs[0], orm.inputs[0])
        nt.l(bc.outputs[0], b.inputs["Base Color"])
        nt.l(nm.outputs[0], b.inputs["Normal"])
        nt.l(orm.outputs[1], b.inputs["Roughness"])
        nt.l(orm.outputs[2], b.inputs["Metallic"])
    elif kind == "M_BLK_Repetible":
        T = spec["texturas"]
        sc = nt.n("ShaderNodeVectorMath", operation="SCALE", i_Scale=spec["UVEscala"])
        nt.l(uvn.outputs[0], sc.inputs[0])
        bc = tex(nt, os.path.join(tdir_c, T["BC"] + ".png"), sc.outputs[0])
        sc2 = nt.n("ShaderNodeVectorMath", operation="SCALE", i_Scale=spec["UVEscala"] * 0.21)
        nt.l(uvn.outputs[0], sc2.inputs[0])
        bcm = tex(nt, os.path.join(tdir_c, T["BC"] + ".png"), sc2.outputs[0])
        lum = nt.n("ShaderNodeRGBToBW")
        nt.l(bcm.outputs[0], lum.inputs[0])
        div = nt.n("ShaderNodeMath", operation="DIVIDE")
        nt.l(lum.outputs[0], div.inputs[0])
        div.inputs[1].default_value = spec["LumaMedia"]
        macro = nt.n("ShaderNodeMix", data_type="FLOAT")
        macro.inputs[0].default_value = spec["MacroFuerza"]
        macro.inputs[2].default_value = 1.0
        nt.l(div.outputs[0], macro.inputs[3])
        tint = nt.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
        tint.inputs[0].default_value = 1.0
        nt.l(bc.outputs[0], tint.inputs[6])
        tint.inputs[7].default_value = (*spec["Tinte"], 1)
        c1 = nt.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
        c1.inputs[0].default_value = 1.0
        nt.l(tint.outputs[2], c1.inputs[6])
        nt.l(lerp1(nt, vc.outputs[0], spec["PesoVC"]), c1.inputs[7])
        c2 = nt.n("ShaderNodeVectorMath", operation="SCALE")
        nt.l(c1.outputs[2], c2.inputs[0])
        nt.l(macro.outputs[0], c2.inputs["Scale"])
        nt.l(c2.outputs[0], b.inputs["Base Color"])
        nm = normal_dx(nt, tex(nt, os.path.join(tdir_c, T["N"] + ".png"), sc.outputs[0], True))
        nt.l(nm.outputs[0], b.inputs["Normal"])
        orm = nt.n("ShaderNodeSeparateColor")
        nt.l(tex(nt, os.path.join(tdir_c, T["ORM"] + ".png"), sc.outputs[0], True).outputs[0], orm.inputs[0])
        nt.l(orm.outputs[1], b.inputs["Roughness"])
        nt.l(orm.outputs[2], b.inputs["Metallic"])
    elif kind == "M_BLK_Color":
        c = nt.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
        c.inputs[0].default_value = 1.0
        c.inputs[6].default_value = (*spec["Color"], 1)
        nt.l(lerp1(nt, vc.outputs[0], spec["PesoVC"]), c.inputs[7])
        nt.l(c.outputs[2], b.inputs["Base Color"])
        b.inputs["Roughness"].default_value = spec["Rugosidad"]
        b.inputs["Metallic"].default_value = spec["Metal"]
    elif kind == "M_BLK_Vidrio":
        sc = nt.n("ShaderNodeVectorMath", operation="SCALE", i_Scale=spec["EscalaSuciedad"])
        nt.l(uvn.outputs[0], sc.inputs[0])
        g = tex(nt, os.path.join(tdir_c, spec["texturas"]["Suciedad"] + ".png"), sc.outputs[0], True)
        r = nt.n("ShaderNodeMapRange", i_To_Min=spec["RugosidadLimpia"], i_To_Max=spec["RugosidadSucia"])
        nt.l(g.outputs[0], r.inputs[0])
        nt.l(r.outputs[0], b.inputs["Roughness"])
        tr = nt.n("ShaderNodeMapRange", i_To_Min=1.0 - spec["OpacidadLimpia"], i_To_Max=1.0 - spec["OpacidadSucia"])
        nt.l(g.outputs[0], tr.inputs[0])
        nt.l(tr.outputs[0], b.inputs["Transmission Weight"])
        b.inputs["Base Color"].default_value = (0.82, 0.88, 0.86, 1)          # tinte de la transmisión (vidrio común verdoso)
        b.inputs["IOR"].default_value = 1.52
    mat.use_backface_culling = not spec.get("dos_caras", False)
    return mat


def main():
    argv = sys.argv
    bid = argv[argv.index("--id") + 1]
    kit = os.path.abspath(argv[argv.index("--kit") + 1] if "--kit" in argv else os.path.join(ENT, "..", "kit_ue5"))
    out = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(ENT, "render_qa", "ue5")
    samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 64
    solo = set(argv[argv.index("--solo") + 1].split(",")) if "--solo" in argv else None     # p. ej. --solo playa,mar
    os.makedirs(out, exist_ok=True)
    man = json.load(open(os.path.join(kit, "manifiesto.json")))
    d = man["modelos"][bid]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    for parte, info in d["mallas"].items():
        if parte == "Colision":
            continue
        bpy.ops.import_scene.gltf(filepath=os.path.join(kit, info["archivo"]))
    specs = dict(man["materiales"])
    specs.update(d["materiales_atlas"])
    tdir_c = os.path.join(kit, "comun", "texturas")
    tdir_m = os.path.join(kit, "modelos", bid, "texturas")
    built = {}
    for o in [o for o in bpy.data.objects if o.type == "MESH"]:
        me = o.data
        if len(me.color_attributes):
            me.color_attributes[0].name = "Color"
        for i, m in enumerate(me.materials):
            key = m.name.split(".")[0]
            if key not in specs:
                continue
            if key not in built:
                built[key] = build_material(f"PV_{key}", specs[key], tdir_c, tdir_m)
            me.materials[i] = built[key]
    # suelo, cielo y sol
    gm = bpy.data.materials.new("suelo")
    gm.use_nodes = True
    gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.32, 0.31, 0.29, 1)
    gm.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.95
    if bid.startswith("MUE_"):
        # muelle: playa (z 0) que baja bajo la cubierta hasta el lecho y mar a su nivel (el kit no trae ni una ni otro)
        lv = d.get("niveles_m", {})
        sea = float(lv.get("mar", -0.5))
        gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.46, 0.40, 0.31, 1)
        me = bpy.data.meshes.new("playa")
        me.from_pydata([(-220, -160, 0.0), (220, -160, 0.0), (220, -1.0, 0.0), (-220, -1.0, 0.0), (220, 30, -4.0),
                        (-220, 30, -4.0), (220, 260, -8.0), (-220, 260, -8.0)], [], [(0, 1, 2, 3), (3, 2, 4, 5), (5, 4, 6, 7)])
        g = bpy.data.objects.new("playa", me)
        sc.collection.objects.link(g)
        g.data.materials.append(gm)
        wm = bpy.data.materials.new("mar")
        wm.use_nodes = True
        pb = wm.node_tree.nodes["Principled BSDF"]
        pb.inputs["Base Color"].default_value = (0.02, 0.06, 0.07, 1)
        pb.inputs["Roughness"].default_value = 0.06
        pb.inputs["Transmission Weight"].default_value = 0.6
        pb.inputs["IOR"].default_value = 1.33
        me = bpy.data.meshes.new("mar")
        me.from_pydata([(-220, -6.0, sea), (220, -6.0, sea), (220, 260, sea), (-220, 260, sea)], [], [(0, 1, 2, 3)])
        wo = bpy.data.objects.new("mar", me)
        sc.collection.objects.link(wo)
        wo.data.materials.append(wm)
    else:
        bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, -0.001))
        g = bpy.context.active_object
        g.data.materials.append(gm)
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.52, 0.64, 0.82, 1)     # cielo de día
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
    sun = bpy.data.lights.new("sol", "SUN")
    sun.energy = 3.2
    sun.angle = math.radians(1.0)
    sun.color = (1.0, 0.96, 0.9)
    so = bpy.data.objects.new("sol", sun)
    so.rotation_euler = (math.radians(50), 0, math.radians(215))
    sc.collection.objects.link(so)
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    try:
        sc.cycles.use_denoising = True
    except Exception:  # noqa: BLE001
        pass
    sc.view_settings.view_transform = "AgX" if "AgX" in [v.identifier for v in sc.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
    sc.render.resolution_x, sc.render.resolution_y = 1600, 900
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    mm = d["medidas_m"]
    ctr = Vector([(a + b) / 2 for a, b in zip(mm["min"], mm["max"])])
    R = Vector((mm["x"], mm["y"], mm["z"])).length / 2

    def look(c, tgt, lens=35):
        cam.location = c
        cam.rotation_euler = (Vector(tgt) - Vector(c)).to_track_quat("-Z", "Y").to_euler()
        cam.data.lens = lens

    az, el = math.radians(-35), math.radians(12)
    dist = R / math.sin(math.radians(22)) * 0.95
    look(ctr + Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el))) * dist, ctr)
    sc.render.filepath = os.path.join(out, f"{bid}_ue5_exterior.png")
    if solo is None or "exterior" in solo:
        bpy.ops.render.render(write_still=True)
        print("[preview] exterior", sc.render.filepath, flush=True)
    if bid.startswith("HOS_"):                  # hospital en uso: luminarias encendidas (focos de la ficha)
        for i, p in enumerate(d.get("focos_m_blender", [])):
            Lf = bpy.data.lights.new(f"foco{i}", "AREA")
            Lf.energy = 30.0
            Lf.size = 1.1
            Lf.color = (1.0, 0.97, 0.92)
            lf = bpy.data.objects.new(f"foco{i}", Lf)
            lf.location = (p[0], p[1], p[2] - 0.01)
            sc.collection.objects.link(lf)
    for (nm, c, t, lens) in EXTRA_VIEWS.get(bid, ()):
        if solo is not None and nm not in solo:
            continue
        look(Vector(c), t, lens=lens)
        sc.render.filepath = os.path.join(out, f"{bid}_ue5_{nm}.png")
        bpy.ops.render.render(write_still=True)
        print("[preview]", nm, sc.render.filepath, flush=True)
    shots = json.load(open(os.path.join(ENT, "visor", "recorrido", f"shots_{PREFIX[bid]}.json")))
    s = next((x for x in shots if x.get("lampA")), shots[0])
    for k in ("lampA", "lampB"):
        if s.get(k):
            L = bpy.data.lights.new(k, "POINT")
            L.energy = 60.0
            L.shadow_soft_size = 0.03
            L.color = (1.0, 0.85, 0.65)
            lo = bpy.data.objects.new(k, L)
            lo.location = s[k]
            sc.collection.objects.link(lo)
    if solo is not None and "interior" not in solo:
        return
    look(Vector(s["cam"]), s["tgt"], lens=18)
    sc.render.filepath = os.path.join(out, f"{bid}_ue5_interior.png")
    bpy.ops.render.render(write_still=True)
    print("[preview] interior", sc.render.filepath, flush=True)


if __name__ == "__main__":
    main()
