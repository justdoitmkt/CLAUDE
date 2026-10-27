"""export_validate.py — fase G: exporta el GLB de un modelo horneado y lo valida.

Uso: /root/blk-venv/bin/python export_validate.py --id APT_A_5p [--blend ruta.blend]
Exporta solo las mallas cuyo nombre empieza por el ID (sin maniquí, cámara, sol ni piso de render), transformaciones aplicadas,
+Y arriba, sin cámaras/luces/Draco, texturas embebidas en JPEG 90. Valida: triángulos del GLB (glb_tris), tamaño, dimensiones,
origen en la base, escala y una reimportación en escena limpia (materiales, UV, memoria de texturas). Escribe export/<ID>_validacion.json.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import texture_tools as tt  # noqa: E402

ENT = os.path.abspath(os.path.join(HERE, ".."))


def main():
    argv = sys.argv
    bid = argv[argv.index("--id") + 1]
    blend = argv[argv.index("--blend") + 1] if "--blend" in argv else os.path.join(HERE, f"{bid}.blend")
    out_dir = os.path.join(ENT, "export")
    os.makedirs(out_dir, exist_ok=True)
    glb = os.path.join(out_dir, f"{bid}.glb")
    bpy.ops.wm.open_mainfile(filepath=blend)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH" and o.name.startswith(bid) and not o.name.startswith("_")]
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.gltf(filepath=glb, export_format="GLB", use_selection=True, export_apply=True, export_yup=True,
                              export_image_format="JPEG", export_image_quality=90, export_cameras=False, export_lights=False,
                              export_draco_mesh_compression_enable=False, export_tangents=False, export_materials="EXPORT",
                              export_extras=False)
    size_mb = os.path.getsize(glb) / 2**20
    tris = tt.glb_tris(glb)
    # reimportación en escena limpia
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb)
    imp = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    pts = [o.matrix_world @ Vector(c) for o in imp for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    mats = {m.name for o in imp for m in o.data.materials if m}
    no_uv = [o.name for o in imp if not o.data.uv_layers]
    mem = 0.0
    for im in bpy.data.images:
        if im.size[0] and im.size[1]:
            mem += im.size[0] * im.size[1] * 4 * 1.33 / 2**20
    rep = dict(
        id=bid, glb=os.path.relpath(glb, ENT), size_mb=round(size_mb, 2), tris_glb=tris, objects=len(imp), materials=sorted(mats),
        n_materials=len(mats), images=len([i for i in bpy.data.images if i.size[0]]), texture_mem_mb=round(mem, 1),
        bbox_min=[round(v, 3) for v in mn], bbox_max=[round(v, 3) for v in mx], dims_m=[round(v, 3) for v in (mx - mn)],
        base_z=round(mn.z, 3), center_xy=[round((mn.x + mx.x) / 2, 3), round((mn.y + mx.y) / 2, 3)], meshes_without_uv=no_uv,
        checks=dict(tris_ge_100k=tris >= 100_000, size_le_100mb=size_mb <= 100, base_on_ground=abs(mn.z) < 0.15,
                    materials_le_14=len(mats) <= 14, all_have_uv=not no_uv),
    )
    json.dump(rep, open(os.path.join(out_dir, f"{bid}_validacion.json"), "w"), indent=1, ensure_ascii=False)
    print(json.dumps(rep, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
