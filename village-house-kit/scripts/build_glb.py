"""Split 'village house kit.fbx' into one GLB per model, with PBR textures embedded.

Run with the `bpy` module (Blender 5.0) after prepare_textures.py:
    python build_glb.py [--allow-incomplete] [--only house_2,gate]

Per model:
  * rotation/scale applied to the mesh data; doors stay child nodes with their hinge pivot
  * model centred on X/Y and placed on the kit ground plane (Z=0 in Blender, Y=0 in glTF);
    a prop that rests on another prop in the kit (min Z > 0.1 m) is dropped to the ground
  * materials rebuilt from the texture manifest: base color (+ alpha mask for thatch),
    OpenGL normal map, metallic-roughness; tangents exported (MikkTSpace, as baked)
A model whose textures are incomplete is skipped unless --allow-incomplete is given."""
import argparse, json, os, sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kit_config import GLB_OUT, GROUPS, MATERIALS, SRC_FBX, TEX_OUT

GROUND_TOLERANCE = 0.1   # metres


def world_bbox(objs):
    """Exact world-space bounds from the vertices (bound_box corners are loose once rotated)."""
    lo = Vector((float("inf"),) * 3)
    hi = Vector((float("-inf"),) * 3)
    for o in objs:
        n = len(o.data.vertices)
        co = np.empty(n * 3)
        o.data.vertices.foreach_get("co", co)
        m = np.array(o.matrix_world)
        w = co.reshape(n, 3) @ m[:3, :3].T + m[:3, 3]
        lo = Vector(np.minimum(lo, w.min(0)))
        hi = Vector(np.maximum(hi, w.max(0)))
    return lo, hi


def load_image(path, colorspace, name):
    img = bpy.data.images.load(path, check_existing=False)
    img.name = name
    img.colorspace_settings.name = colorspace
    return img


def build_material(mat, info):
    """Rebuild `mat` as a clean Principled BSDF graph the glTF exporter maps 1:1."""
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (600, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (250, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["Roughness"].default_value = 0.5
    name = mat.name

    if info.get("basecolor"):
        tex = nt.nodes.new("ShaderNodeTexImage"); tex.location = (-450, 300)
        tex.image = load_image(info["basecolor"], "sRGB", f"{name}_basecolor")
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if info.get("alpha"):
            # Round -> glTF alphaMode MASK (cutoff 0.5): crisp thatch edges, no sorting issues
            rnd = nt.nodes.new("ShaderNodeMath"); rnd.operation = "ROUND"; rnd.location = (0, 150)
            nt.links.new(tex.outputs["Alpha"], rnd.inputs[0])
            nt.links.new(rnd.outputs[0], bsdf.inputs["Alpha"])
            tex.image.alpha_mode = "STRAIGHT"
    else:
        bsdf.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1.0)

    if info.get("metallic_roughness"):
        tex = nt.nodes.new("ShaderNodeTexImage"); tex.location = (-450, 0)
        tex.image = load_image(info["metallic_roughness"], "Non-Color", f"{name}_metallic_roughness")
        sep = nt.nodes.new("ShaderNodeSeparateColor"); sep.location = (-150, 0)
        nt.links.new(tex.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        if info.get("metallic"):
            nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])

    if info.get("normal"):
        tex = nt.nodes.new("ShaderNodeTexImage"); tex.location = (-450, -300)
        tex.image = load_image(info["normal"], "Non-Color", f"{name}_normal")
        nm = nt.nodes.new("ShaderNodeNormalMap"); nm.location = (-150, -300)
        nt.links.new(tex.outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])

    mat.use_backface_culling = False     # doubleSided: thin planks/thatch must render from both sides


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-incomplete", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args(argv)
    only = set(filter(None, args.only.split(",")))

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=SRC_FBX)
    scene = bpy.context.scene
    meshes = [o for o in scene.objects if o.type == "MESH"]

    # --- apply rotation + scale (locations kept: they are the pivots, e.g. door hinges) ---
    before = {o.name: world_bbox([o]) for o in meshes}
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    for o in meshes:
        a, b = before[o.name], world_bbox([o])
        assert (a[0] - b[0]).length < 1e-4 and (a[1] - b[1]).length < 1e-4, f"transform_apply moved {o.name}"

    # MikkTSpace tangents (needed to match the baked normal maps) cannot be computed on n-gons:
    # triangulate only faces with 5+ corners, applied at export time, keeping custom normals.
    for o in meshes:
        if any(len(p.vertices) > 4 for p in o.data.polygons):
            mod = o.modifiers.new("triangulate_ngons", "TRIANGULATE")
            mod.min_vertices = 5
            if hasattr(mod, "keep_custom_normals"):
                mod.keep_custom_normals = True

    # --- materials ---
    status = {}
    for fbx_name, cfg in MATERIALS.items():
        mat = bpy.data.materials.get(fbx_name)
        if mat is None:
            raise SystemExit(f"material not found in FBX: {fbx_name}")
        with open(os.path.join(TEX_OUT, cfg["name"], "manifest.json")) as fh:
            info = json.load(fh)
        mat.name = cfg["name"]
        build_material(mat, info)
        status[cfg["name"]] = info

    os.makedirs(GLB_OUT, exist_ok=True)
    results = {}
    for model, members in GROUPS.items():
        if only and model not in only:
            continue
        objs = [bpy.data.objects[src] for src, _ in members]
        mats = sorted({s.material.name for o in objs for s in o.material_slots if s.material})
        missing = sorted({f for m in mats for f in status[m]["missing"]})
        lo, hi = world_bbox(objs)
        ground = lo.z if lo.z > GROUND_TOLERANCE else 0.0
        pivot = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, ground))
        if missing and not args.allow_incomplete:
            print(f"SKIP {model}: missing textures {missing}")
            results[model] = {"skipped": True, "missing": missing, "materials": mats,
                              "kit_position_m": [round(v, 3) for v in pivot]}
            continue

        root, children = objs[0], objs[1:]

        # move the root origin to the pivot without moving geometry, then bring the model to 0,0,0
        root.data.transform(Matrix.Translation(root.location - pivot))
        root.location = pivot
        for c in children:
            world = c.location.copy()
            c.parent = root
            c.matrix_parent_inverse = Matrix.Identity(4)
            c.location = world - pivot
        root.location = (0.0, 0.0, 0.0)
        for (src, new), o in zip(members, objs):
            o.name = new
            o.data.name = new

        bpy.ops.object.select_all(action="DESELECT")
        for o in objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = root
        path = os.path.join(GLB_OUT, f"{model}.glb")
        bpy.ops.export_scene.gltf(
            filepath=path, export_format="GLB", use_selection=True,
            export_apply=True, export_yup=True,
            export_texcoords=True, export_normals=True, export_tangents=True,
            export_materials="EXPORT", export_image_format="AUTO",
            export_cameras=False, export_lights=False, export_extras=False,
            export_animations=False, export_skins=False, export_morph=False,
        )
        lo2, hi2 = world_bbox(objs)
        results[model] = {
            "file": os.path.basename(path),
            "bytes": os.path.getsize(path),
            "nodes": [o.name for o in objs],
            "materials": mats,
            "vertices": sum(len(o.data.vertices) for o in objs),
            "triangles": sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs),
            "size_m": [round(v, 3) for v in (hi2 - lo2)],     # Blender X, Y, Z(up)
            "kit_position_m": [round(v, 3) for v in pivot],
            "missing": missing,
        }
        print(f"OK   {model:14} {results[model]['bytes'] / 1e6:7.1f} MB  {results[model]['triangles']:6d} tris  {mats}")

    with open(os.path.join(GLB_OUT, "..", "build_report.json"), "w") as fh:
        json.dump(results, fh, indent=1)


if __name__ == "__main__":
    main()
