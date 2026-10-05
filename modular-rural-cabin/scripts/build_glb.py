"""Build one GLB per StaticMesh of the 'Modular Rural Cabin' UE4.22 project (+ Blueprint assemblies).

Run with the `bpy` module (Blender 5.0) after bake_materials.py / bake_special.py:
    python build_glb.py [--only Wall_4m,Door_01] [--no-assemblies]

Per mesh:
  * LOD0 source geometry (MeshDescription) exactly as imported in UE: positions, the artist's
    normals (UE build keeps imported normals), every triangle, UVs, material slots via SectionInfoMap
  * UE (cm, left-handed, Z up) -> glTF (m, right-handed, Y up): mirror Y in Blender + winding flip;
    the UE pivot is kept, so modular pieces still snap on their grid
  * materials from the baked manifests: base color, ORM (occlusion/roughness/metallic), OpenGL normal,
    MikkTSpace tangents exported (UE builds this kit's tangents with MikkTSpace too)
  * TEXCOORD_0 = UVs the textures use; TEXCOORD_1 = UE lightmap UV when the mesh has one"""
import argparse, glob, json, math, os, sys

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_mesh import load_static_mesh
from ue_mat import ROOT
from uasset import Package

WORK = os.environ.get("KIT_WORK", "/home/user/work2")
MAT_DIR = f"{WORK}/build/mat"
OUT = os.environ.get("KIT_GLB_OUT", f"{WORK}/glb")
SCALE = 0.01


# ------------------------------------------------------------------ geometry
def mesh_arrays(sm):
    """Flatten LOD0 MeshDescription into numpy arrays (UE space)."""
    md = sm["lods"][0]
    pos_attr = md["vertex_attrs"][1]["Position"]["arrays"][0]
    vi = md["vi_attrs"][1]
    v_ids = md["vertices"]
    vmap = np.full(int(v_ids.max()) + 1, -1, np.int64); vmap[v_ids] = np.arange(len(v_ids))
    positions = pos_attr[v_ids].astype(np.float64)

    vi_ids = md["vi_ids"]
    vimap = np.full(int(vi_ids.max()) + 1, -1, np.int64); vimap[vi_ids] = np.arange(len(vi_ids))
    vi_vert = vmap[md["vi_vertex"]]
    normals = vi["Normal"]["arrays"][0][vi_ids].astype(np.float64)
    uvs = [a[vi_ids].astype(np.float64) for a in vi["TextureCoordinate"]["arrays"]]
    colors = vi["Color"]["arrays"][0][vi_ids].astype(np.float64) if "Color" in vi else None

    group_ids = list(md["group_ids"])
    tris, tri_group = [], []
    for poly, g in zip(md["polys"], md["poly_group"]):
        c = [int(vimap[x]) for x in poly]
        for k in range(1, len(c) - 1):                       # all polygons are triangles in this kit
            tris.append((c[0], c[k], c[k + 1])); tri_group.append(group_ids.index(g))
    tris = np.array(tris, np.int64); tri_group = np.array(tri_group, np.int64)
    # UE build (bRemoveDegenerates): drop triangles with two corners at the same position
    p = positions[vi_vert[tris]]
    same = lambda a, b: (np.abs(p[:, a] - p[:, b]) <= 0.00002).all(1)    # THRESH_POINTS_ARE_SAME (cm)
    keep = ~(same(0, 1) | same(1, 2) | same(0, 2))
    return dict(positions=positions, vi_vert=vi_vert, normals=normals, uvs=uvs, colors=colors,
                tris=tris[keep], tri_section=tri_group[keep], degenerate=int((~keep).sum()), source_triangles=len(tris),
                group_names=md["group_attrs"][1]["ImportedMaterialSlotName"]["arrays"][0])


def section_material(sm, section):
    info = sm["section_info"].get(section)
    return info["MaterialIndex"] if info else section


def material_manifest(mic, mesh_name):
    p = f"{MAT_DIR}/{mic}/{mesh_name}/manifest.json"            # per-mesh bake (special materials)
    if os.path.exists(p):
        return json.load(open(p))
    return json.load(open(f"{MAT_DIR}/{mic}/manifest.json"))


UV_INDEX = {"UV0": 0, "UV1": 1, "UV2": 2}


def build_mesh_object(sm, name):
    a = mesh_arrays(sm)
    P = a["positions"] * SCALE * np.array([1, -1, 1])           # Blender: right-handed, Z up
    N = a["normals"] * np.array([1, -1, 1])
    tris = a["tris"]                                            # UE CW (left-handed) == CCW once mirrored
    corner_vi = tris.reshape(-1)
    corner_v = a["vi_vert"][corner_vi]

    # material slots in StaticMaterials order
    slots = [m["material"].split(".")[-1] for m in sm["materials"]]
    tri_mat = np.array([section_material(sm, s) for s in a["tri_section"]], np.int64)
    manifests = {i: material_manifest(s, sm["name"]) for i, s in enumerate(slots) if i in set(tri_mat.tolist())}

    me = bpy.data.meshes.new(name)
    me.vertices.add(len(P)); me.vertices.foreach_set("co", P.astype(np.float32).ravel())
    me.loops.add(len(corner_v)); me.loops.foreach_set("vertex_index", corner_v.astype(np.int32))
    me.polygons.add(len(tris))
    me.polygons.foreach_set("loop_start", (np.arange(len(tris)) * 3).astype(np.int32))
    me.polygons.foreach_set("material_index", tri_mat.astype(np.int32))

    # TEXCOORD_0: per face the UV set its material's textures use; TEXCOORD_1: lightmap UV
    n_uv = len(a["uvs"])
    tex_uv = np.empty((len(corner_vi), 2))
    for i, man in manifests.items():
        sel = np.repeat(tri_mat == i, 3)
        if man.get("uv") == "BAKE":                              # re-packed layout made by bake_special.py
            tex_uv[sel] = np.load(man["bake_uv"])[sel]
            continue
        k = min(UV_INDEX[man.get("uv", "UV0")], n_uv - 1)        # UE reuses the last UV set if missing
        tex_uv[sel] = a["uvs"][k][corner_vi[sel]]
    layers = [("UVMap", tex_uv)]
    lm = sm["props"].get("LightMapCoordinateIndex", 0)
    if 0 < lm < n_uv:
        layers.append(("Lightmap", a["uvs"][lm][corner_vi]))
    for lname, uv in layers:
        lay = me.uv_layers.new(name=lname)
        flipped = np.stack([uv[:, 0], 1 - uv[:, 1]], 1)            # glTF/UE V down -> Blender V up
        lay.data.foreach_set("uv", flipped.astype(np.float32).ravel())
    me.uv_layers.active_index = 0
    me.update(calc_edges=True)
    if len(me.polygons) != len(tris):
        raise RuntimeError(f"{name}: face count mismatch")
    loop_n = N[corner_vi]
    loop_n /= np.maximum(np.linalg.norm(loop_n, axis=1, keepdims=True), 1e-12)
    me.normals_split_custom_set(loop_n.astype(np.float32).tolist())

    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    for s in slots:
        ob.data.materials.append(get_material(s, manifests, slots))
    stats = dict(triangles=len(tris), source_triangles=a["source_triangles"], degenerate_removed=a["degenerate"],
                 vertices=len(P), uv_sets=n_uv, materials=slots,
                 winding=winding_check(P, corner_v, corner_vi, N))
    return ob, stats


def winding_check(P, corner_v, corner_vi, N):
    """Fraction of (non-degenerate) triangles whose geometric normal agrees with the imported normals."""
    v = corner_v.reshape(-1, 3)
    g = np.cross(P[v[:, 1]] - P[v[:, 0]], P[v[:, 2]] - P[v[:, 0]])
    n = N[corner_vi].reshape(-1, 3, 3).sum(1)
    ok = np.linalg.norm(g, axis=1) > 1e-12
    return float(((g * n).sum(1)[ok] > 0).mean())


# ------------------------------------------------------------------ materials
_mats = {}


def occlusion_group():
    g = bpy.data.node_groups.get("glTF Material Output")
    if g is None:
        g = bpy.data.node_groups.new("glTF Material Output", "ShaderNodeTree")
        g.interface.new_socket("Occlusion", in_out="INPUT", socket_type="NodeSocketFloat")
    return g


def load_image(path, colorspace):
    img = bpy.data.images.load(path, check_existing=True)
    img.colorspace_settings.name = colorspace
    return img


def get_material(slot, manifests, slots):
    idx = slots.index(slot)
    man = manifests.get(idx)
    if man is None:                                              # slot unused by any triangle
        man = json.load(open(f"{MAT_DIR}/{slot}/manifest.json"))
    mkey = man["name"] + man.get("mesh_suffix", "")
    if mkey in _mats:
        return _mats[mkey]
    mat = bpy.data.materials.new(mkey)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (700, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (350, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Metallic"].default_value = man.get("metallic_factor", 0.0)
    bsdf.inputs["Roughness"].default_value = man.get("roughness_factor", 0.5)

    if man.get("basecolor"):
        tex = nt.nodes.new("ShaderNodeTexImage"); tex.location = (-500, 350)
        tex.image = load_image(man["basecolor"], "sRGB")
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if man["alpha_mode"] == "MASK":
            lt = nt.nodes.new("ShaderNodeMath"); lt.operation = "LESS_THAN"; lt.location = (-150, 200)
            lt.inputs[1].default_value = man.get("cutoff", 0.3333)
            sub = nt.nodes.new("ShaderNodeMath"); sub.operation = "SUBTRACT"; sub.location = (50, 200)
            sub.inputs[0].default_value = 1.0
            nt.links.new(tex.outputs["Alpha"], lt.inputs[0]); nt.links.new(lt.outputs[0], sub.inputs[1])
            nt.links.new(sub.outputs[0], bsdf.inputs["Alpha"])
        elif man["alpha_mode"] == "BLEND":
            nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
        if man["alpha_mode"] != "OPAQUE":
            tex.image.alpha_mode = "STRAIGHT"
    else:
        bsdf.inputs["Base Color"].default_value = tuple(man.get("basecolor_factor", (0.8, 0.8, 0.8))) + (1.0,)
        if man["alpha_mode"] == "BLEND":
            bsdf.inputs["Alpha"].default_value = man.get("alpha_factor", 0.5)
    if man.get("metallic_factor") is not None and not man.get("orm"):
        bsdf.inputs["Metallic"].default_value = man["metallic_factor"]
    if man.get("roughness_factor") is not None and not man.get("orm"):
        bsdf.inputs["Roughness"].default_value = man["roughness_factor"]

    if man.get("orm"):
        tex = nt.nodes.new("ShaderNodeTexImage"); tex.location = (-500, 0)
        tex.image = load_image(man["orm"], "Non-Color")
        sep = nt.nodes.new("ShaderNodeSeparateColor"); sep.location = (-200, 0)
        nt.links.new(tex.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
        if man.get("occlusion"):
            grp = nt.nodes.new("ShaderNodeGroup"); grp.node_tree = occlusion_group(); grp.location = (350, -400)
            nt.links.new(sep.outputs["Red"], grp.inputs["Occlusion"])

    if man.get("normal"):
        tex = nt.nodes.new("ShaderNodeTexImage"); tex.location = (-500, -350)
        tex.image = load_image(man["normal"], "Non-Color")
        nm = nt.nodes.new("ShaderNodeNormalMap"); nm.location = (-200, -350)
        nt.links.new(tex.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])

    if man.get("emissive_factor"):
        bsdf.inputs["Emission Color"].default_value = tuple(man["emissive_factor"]) + (1.0,)
        bsdf.inputs["Emission Strength"].default_value = 1.0
    if man["alpha_mode"] == "BLEND":
        mat.surface_render_method = "BLENDED"
    mat.use_backface_culling = not man.get("double_sided", False)
    _mats[mkey] = mat
    return mat


# ------------------------------------------------------------------ Blueprint assemblies
def ue_rotator_matrix(rot):
    """UE FRotator (pitch, yaw, roll in degrees) -> 3x3 rotation matrix acting on UE column vectors."""
    if rot is None:
        return np.eye(3)
    p, y, r = (math.radians(v) for v in rot)
    sp, cp, sy, cy, sr, cr = math.sin(p), math.cos(p), math.sin(y), math.cos(y), math.sin(r), math.cos(r)
    x_axis = (cp * cy, cp * sy, sp)
    y_axis = (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp)
    z_axis = (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)
    return np.array([x_axis, y_axis, z_axis]).T


def ue_to_blender_matrix(loc, rot, scale):
    """UE relative transform (cm, left-handed) -> Blender 4x4 (m, right-handed)."""
    m = np.diag([1.0, -1.0, 1.0])
    R = m @ ue_rotator_matrix(rot) @ m
    S = np.diag(scale if scale else (1.0, 1.0, 1.0))
    T = np.eye(4)
    T[:3, :3] = R @ S
    T[:3, 3] = m @ np.array(loc if loc else (0.0, 0.0, 0.0)) * SCALE
    return Matrix(T.tolist())


def ue4x4_to_blender(M):
    """UE 4x4 (cm, left-handed, column vectors) -> Blender Matrix (m, right-handed)."""
    m = np.diag([1.0, -1.0, 1.0])
    T = np.eye(4)
    T[:3, :3] = m @ M[:3, :3] @ m
    T[:3, 3] = m @ M[:3, 3] * SCALE
    return Matrix(T.tolist())


def blueprint_components(path):
    """[(component name, mesh name, 4x4 matrix relative to the BP root, parent component)]"""
    p = Package(path)
    templates, nodes = {}, {}
    for i, e in enumerate(p.exports):
        c = p.export_class(e)
        if e["name"].endswith("_GEN_VARIABLE"):
            props, _ = p.export_props(e)
            templates[i + 1] = (c, e["name"][:-len("_GEN_VARIABLE")], props)
        elif c == "SCS_Node":
            props, _ = p.export_props(e)
            nodes[i + 1] = props
    children = {}
    for nid, props in nodes.items():
        for ch in props.get("ChildNodes", []):
            children[ch[1]] = nid
    out = []

    def world(nid):
        props = nodes[nid]
        cls, cname, tp = templates[props["ComponentTemplate"][1]]
        m = ue_to_blender_matrix(tp.get("RelativeLocation"), tp.get("RelativeRotation"), tp.get("RelativeScale3D"))
        parent = children.get(nid)
        return (world(parent) @ m) if parent else m
    for nid, props in nodes.items():
        cls, cname, tp = templates[props["ComponentTemplate"][1]]
        sm = tp.get("StaticMesh")
        if cls != "StaticMeshComponent" or not sm or not sm[1]:
            continue
        mats = [p.obj_path(m[1]).split(".")[-1] if m and m[1] else None for m in tp.get("OverrideMaterials", [])]
        out.append((cname, p.obj_path(sm[1]).split(".")[-1], world(nid), mats))
    return out


def apply_overrides(o, sm, overrides):
    """Per-instance material overrides (UE OverrideMaterials) as object-linked material slots."""
    slots = [m["material"].split(".")[-1] for m in sm["materials"]]
    for i, mic in enumerate(overrides or []):
        if mic and i < len(o.material_slots) and mic != slots[i]:
            o.material_slots[i].link = "OBJECT"
            o.material_slots[i].material = get_material(mic, {}, [mic])


# ------------------------------------------------------------------ export
def export(objs, path):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(
        filepath=path, export_format="GLB", use_selection=True,
        export_apply=True, export_yup=True,
        export_texcoords=True, export_normals=True, export_tangents=True,
        export_materials="EXPORT", export_image_format="AUTO",
        export_vertex_color="NONE",
        export_cameras=False, export_lights=False, export_extras=False,
        export_animations=False, export_skins=False, export_morph=False,
    )


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--no-assemblies", action="store_true")
    ap.add_argument("--no-cabins", action="store_true")
    args = ap.parse_args(argv)
    only = set(filter(None, args.only.split(",")))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    files = sorted(f for f in glob.glob(ROOT + "/Meshes/**/*.uasset", recursive=True) if "/Blueprints/" not in f)
    meshes, report = {}, {}
    for f in files:
        sm = load_static_mesh(f)
        meshes[sm["name"]] = (sm, os.path.relpath(os.path.dirname(f), ROOT + "/Meshes"))

    bps = sorted(glob.glob(ROOT + "/Meshes/**/Blueprints/*.uasset", recursive=True))
    assemblies = {}
    if not args.no_assemblies:
        for f in bps:
            comps = blueprint_components(f)
            if len(comps) > 1:
                assemblies[os.path.basename(f)[:-7]] = comps
    level_cabins = {}
    if not args.no_cabins:
        from level_assemblies import cabins
        for lv, prefix in (("Modular_Cabins_Showcase", "Cabin"), ("Rural_Cabins", "Cabin_Rural")):
            found = cabins(f"{ROOT}/Maps/{lv}.umap")
            for n, (label, cab) in enumerate(sorted(found.items(), key=lambda kv: (round(kv[1]["root_world"][0, 3] / 100), kv[0])), 1):
                cab["source"] = f"{lv}.umap / {label}"
                level_cabins[f"{prefix}_{n:02d}"] = cab
    needed = set(meshes) if not only else (set(only) | {m for a, c in assemblies.items() if a in only for _, m, _, _ in c}
                                           | {m for a, c in level_cabins.items() if a in only for _, m, _, _ in c["parts"]})

    built = {}
    for name in sorted(needed & set(meshes)):
        sm, folder = meshes[name]
        ob, stats = build_mesh_object(sm, name)
        built[name] = ob
        stats["folder"] = folder
        report[name] = stats

    for name, ob in built.items():
        if only and name not in only:
            continue
        folder = report[name]["folder"]
        os.makedirs(f"{OUT}/{folder}", exist_ok=True)
        path = f"{OUT}/{folder}/{name}.glb"
        export([ob], path)
        report[name]["file"] = os.path.relpath(path, OUT)
        report[name]["bytes"] = os.path.getsize(path)
        print(f"OK   {folder:8} {name:28} {report[name]['bytes'] / 1e6:6.1f} MB {report[name]['triangles']:6d} tris  winding={report[name]['winding']:.3f}")

    for aname, comps in assemblies.items():
        if only and aname not in only:
            continue
        objs = []
        root = None
        for cname, mname, mtx, overrides in comps:
            src = built[mname]
            o = bpy.data.objects.new(cname, src.data)
            bpy.context.scene.collection.objects.link(o)
            apply_overrides(o, meshes[mname][0], overrides)
            o.matrix_world = mtx
            objs.append(o)
        # the piece without offset is the root; the rest become its children (doors, lids, shutters)
        root = min(objs, key=lambda o: o.matrix_world.translation.length)
        for o in objs:
            if o is not root:
                w = o.matrix_world.copy()
                o.parent = root
                o.matrix_parent_inverse = root.matrix_world.inverted()
                o.matrix_world = w
        objs.remove(root); objs.insert(0, root)
        os.makedirs(f"{OUT}/Assemblies", exist_ok=True)
        path = f"{OUT}/Assemblies/{aname}.glb"
        export(objs, path)
        report["Assemblies/" + aname] = dict(file=os.path.relpath(path, OUT), bytes=os.path.getsize(path),
                                             parts=[(c, m) for c, m, _, _ in comps])
        print(f"OK   Assembly {aname:28} {os.path.getsize(path) / 1e6:6.1f} MB  parts={[m for _, m, _, _ in comps]}")
        for o in objs:
            bpy.data.objects.remove(o)

    for cname, cab in level_cabins.items():
        if only and cname not in only:
            continue
        inv_root = np.linalg.inv(cab["root_world"])
        root = bpy.data.objects.new(cname, None)
        bpy.context.scene.collection.objects.link(root)
        objs = [root]
        for pname, mname, overrides, world in cab["parts"]:
            if mname not in built:
                continue
            src = built[mname]
            o = bpy.data.objects.new(pname, src.data)
            bpy.context.scene.collection.objects.link(o)
            apply_overrides(o, meshes[mname][0], overrides)
            o.matrix_world = ue4x4_to_blender(inv_root @ world)
            o.parent = root
            objs.append(o)
        os.makedirs(f"{OUT}/Cabins", exist_ok=True)
        path = f"{OUT}/Cabins/{cname}.glb"
        export(objs, path)
        report["Cabins/" + cname] = dict(file=os.path.relpath(path, OUT), bytes=os.path.getsize(path), source=cab["source"],
                                         parts=len(objs) - 1, meshes=sorted({m for _, m, _, _ in cab["parts"]}))
        print(f"OK   Cabin {cname:16} {os.path.getsize(path) / 1e6:6.1f} MB  parts={len(objs) - 1}  ({cab['source']})")
        for o in objs:
            bpy.data.objects.remove(o)

    name = "build_report.json" if not only else "build_report_partial.json"
    with open(f"{OUT}/../{name}", "w") as fh:
        json.dump(report, fh, indent=1)


if __name__ == "__main__":
    main()
