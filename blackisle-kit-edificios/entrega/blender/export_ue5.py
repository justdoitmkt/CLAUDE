"""export_ue5.py — kit de un modelo para Unreal Engine 5, a partir de <ID>_ue.blend (bake_apt.py --id <ID> --ue).

Uso: /root/blk-venv/bin/python export_ue5.py --id APT_A_5p [--blend ruta.blend] [--tex carpeta_texturas_ue] [--out carpeta_del_kit]
Escribe en <kit>/modelos/<ID>/:
  SM_<ID>_<Parte>.glb  un GLB por malla, las 5 con el mismo pivote (centro de la planta a nivel del suelo, z = 0): SM_<ID>_Estructura (carcasa,
                interior, techo), SM_<ID>_Detalle (vanos, servicios, barandales, daño), SM_<ID>_Escombro (escombro exterior
                suelto, sin terreno), SM_<ID>_Vidrio (todo el vidrio, translúcido en el motor) y SM_<ID>_Colision (carcasa +
                interior simplificados sin cambiar su forma, solo para colisión). Un solo canal UV, COLOR_0 = AO (x color de la
                tela), materiales solo con nombre (BLK_<tipo> comunes y <ID>_walls_main / <ID>_walls_rest): sin texturas dentro.
  texturas/     T_<ID>_walls_{main,rest}_{BC.jpg, N.png (DirectX: verde invertido), ORM.png (R AO, G rugosidad, B metal)}
  <ID>.json     ficha del modelo: mallas, triángulos, ranuras de material, medidas, focos para luces, comprobaciones.
La reimportación de los GLB en una escena limpia valida nombres, ranuras, UV, COLOR_0 y medidas.
export_ue5.py --ejes <ruta.glb> escribe SM_BLK_Ejes (marcador de ejes común a todo el kit).
"""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

ENT = os.path.abspath(os.path.join(HERE, ".."))
GROUPS = {   # malla del kit -> sufijos de los objetos de <ID>_ue.blend
    "Estructura": ("_WallsMain", "_WallsRest", "_Interior", "_Roof"),
    "Detalle": ("_Details",),
    "Escombro": ("_SkirtLoose",),
}
COLLISION_FROM = ("_WallsMain", "_WallsRest", "_Interior")


def log(*a):
    print("[ue5]", *a, flush=True)


def one_uv(o):
    """Deja un solo canal UV llamado 'UVMap' (atlas en los muros, caja de 2 m en el resto)."""
    me = o.data
    keep = me.uv_layers.get("atlas") or me.uv_layers.get("UVMap") or (me.uv_layers[0] if len(me.uv_layers) else None)
    if keep is None:
        me.uv_layers.new(name="UVMap")
        return
    for lay in [l.name for l in me.uv_layers if l.name != keep.name]:
        me.uv_layers.remove(me.uv_layers[lay])
    keep.name = "UVMap"


def ensure_ao(o):
    """COLOR_0 'AO' en todas las mallas (los muros con atlas no la tienen: blanco = sin oscurecer)."""
    me = o.data
    if "AO" not in me.color_attributes:
        ca = me.color_attributes.new("AO", "FLOAT_COLOR", "CORNER")
        ca.data.foreach_set("color", np.ones(len(ca.data) * 4, dtype=np.float32))
    me.color_attributes.active_color = me.color_attributes["AO"]
    me.attributes.default_color_name = "AO"


def copy_obj(o, name):
    c = o.copy()
    c.data = o.data.copy()
    c.name = name
    c.data.name = name
    bpy.context.scene.collection.objects.link(c)
    return c


def split_glass(o):
    """Saca de `o` las caras de BLK_glass a un objeto nuevo (o None)."""
    idx = [i for i, m in enumerate(o.data.materials) if m and m.name.split(".")[0] == "BLK_glass"]
    if not idx:
        return None
    g = copy_obj(o, o.name + "_glass")
    for ob, keep_glass in ((o, False), (g, True)):
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        kill = [f for f in bm.faces if (f.material_index in idx) != keep_glass]
        bmesh.ops.delete(bm, geom=kill, context="FACES")
        bm.to_mesh(ob.data)
        bm.free()
    return g


def join(objs, name):
    objs = [o for o in objs if o is not None and len(o.data.polygons)]
    if not objs:
        return None
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    if len(objs) > 1:
        bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    o.name = name
    o.data.name = name
    return o


def clean_slots(o):
    """Quita ranuras de material sin caras (las deja el join) para que el motor no cree ranuras vacías."""
    me = o.data
    used = np.zeros(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("material_index", used)
    keep = sorted(set(used.tolist()))
    mats = [me.materials[i] for i in keep]
    remap = np.zeros(max(len(me.materials), 1), dtype=np.int32)
    for new, old in enumerate(keep):
        remap[old] = new
    me.materials.clear()
    for m in mats:
        me.materials.append(m)
    me.polygons.foreach_set("material_index", remap[used])
    me.update()


def collision_mesh(src, name):
    """Copia de la carcasa + interior con las caras coplanares fundidas (misma forma, muchos menos triángulos) y triangulada."""
    o = join([copy_obj(s, s.name + "_col") for s in src], name)
    bm = bmesh.new()
    bm.from_mesh(o.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.001)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(1.0), use_dissolve_boundaries=False, verts=bm.verts, edges=bm.edges)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(o.data)
    bm.free()
    o.data.materials.clear()
    m = bpy.data.materials.get("BLK_colision") or bpy.data.materials.new("BLK_colision")
    m.diffuse_color = (1.0, 0.0, 1.0, 1.0)
    o.data.materials.append(m)
    for lay in [l.name for l in o.data.uv_layers]:
        o.data.uv_layers.remove(o.data.uv_layers[lay])
    for ca in [c.name for c in o.data.color_attributes]:
        o.data.color_attributes.remove(o.data.color_attributes[ca])
    return o


def tris(o):
    return sum(len(p.vertices) - 2 for p in o.data.polygons)


def export_textures(bid, src_dir, dst_dir):
    os.makedirs(dst_dir, exist_ok=True)
    out = {}
    for aid in ("walls_main", "walls_rest"):
        base = os.path.join(src_dir, f"{bid}_{aid}")
        bc = os.path.join(dst_dir, f"T_{bid}_{aid}_BC.jpg")
        Image.open(base + "_albedo.png").convert("RGB").save(bc, quality=95, subsampling=0)
        n = np.asarray(Image.open(base + "_normal.png").convert("RGB")).copy()
        n[..., 1] = 255 - n[..., 1]                           # OpenGL (Blender) -> DirectX (Unreal)
        Image.fromarray(n).save(os.path.join(dst_dir, f"T_{bid}_{aid}_N.png"), optimize=True)
        Image.open(base + "_orm.png").convert("RGB").save(os.path.join(dst_dir, f"T_{bid}_{aid}_ORM.png"), optimize=True)
        out[aid] = {k: f"T_{bid}_{aid}_{k}" for k in ("BC", "N", "ORM")}
    return out


def main():
    argv = sys.argv
    bid = argv[argv.index("--id") + 1]
    blend = argv[argv.index("--blend") + 1] if "--blend" in argv else os.path.join(HERE, f"{bid}_ue.blend")
    kit = argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(ENT, "..", "kit_ue5")
    kit = os.path.abspath(kit)
    mdir = os.path.join(kit, "modelos", bid)
    os.makedirs(mdir, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=blend)
    objs = {o.name: o for o in bpy.data.objects if o.type == "MESH" and o.name.startswith(bid)}
    by_suffix = lambda suf: objs.get(bid + suf)  # noqa: E731
    for o in objs.values():
        one_uv(o)
        ensure_ao(o)
    # la colisión se arma antes de sacar el vidrio (no se usa: es solo forma) y de unir
    extra = []
    if bid.startswith("MUE_"):              # muelle: grúa, postes y bitas son Detalle; su colisión va como formas simples
        import mue_builder
        extra.append(mue_builder.collision_proxies().finish(f"{bid}_colx", bpy.context.scene.collection, merge=0))
    col = collision_mesh([by_suffix(s) for s in COLLISION_FROM if by_suffix(s)] + extra, f"SM_{bid}_Colision")
    for o in extra:
        bpy.data.objects.remove(o)
    glass = [g for g in (split_glass(o) for o in list(objs.values())) if g]
    parts = {}
    for gname, sufs in GROUPS.items():
        parts[gname] = join([by_suffix(s) for s in sufs], f"SM_{bid}_{gname}")
    parts["Vidrio"] = join(glass, f"SM_{bid}_Vidrio")
    parts["Colision"] = col
    parts = {k: v for k, v in parts.items() if v is not None}
    for o in parts.values():
        clean_slots(o)
        if "AO" in o.data.color_attributes:
            o.data.color_attributes.active_color = o.data.color_attributes["AO"]
    # exportación: un GLB por malla (el importador del motor no puede combinarlas por error), solo nombres de material
    info = dict(id=bid, mallas={})
    for k, o in parts.items():
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        f = os.path.join(mdir, f"{o.name}.glb")
        export_glb(f)
        info["mallas"][k] = dict(nombre=o.name, archivo=f"modelos/{bid}/{o.name}.glb", triangulos=tris(o),
                                 ranuras=[m.name for m in o.data.materials], mib=round(os.path.getsize(f) / 2**20, 2))
    tex = argv[argv.index("--tex") + 1] if "--tex" in argv else os.path.join(ENT, "texturas_ue", bid)
    info["texturas"] = export_textures(bid, tex, os.path.join(mdir, "texturas"))
    fj = os.path.join(tex, "focos.json")
    info["focos_m_blender"] = json.load(open(fj))["focos"] if os.path.exists(fj) else []
    # validación: reimportar los GLB en una escena vacía
    bpy.ops.wm.read_factory_settings(use_empty=True)
    for d in info["mallas"].values():
        bpy.ops.import_scene.gltf(filepath=os.path.join(kit, d["archivo"]))
    imp = {o.name: o for o in bpy.data.objects if o.type == "MESH"}
    mins, maxs = np.full(3, np.inf), np.full(3, -np.inf)           # edificio (sin el escombro suelto)
    smin, smax = np.full(3, np.inf), np.full(3, -np.inf)           # solo la malla de Estructura
    emin, emax = np.full(3, np.inf), np.full(3, -np.inf)           # escombro exterior
    checks = {}
    for k, d in info["mallas"].items():
        o = imp.get(d["nombre"])
        checks[f"{k}_presente"] = o is not None
        if o is None:
            continue
        me = o.data
        checks[f"{k}_ranuras"] = [m.name.split(".")[0] for m in me.materials] == d["ranuras"]   # .001: mismo nombre en otro GLB
        checks[f"{k}_un_uv"] = len(me.uv_layers) == (0 if k == "Colision" else 1)
        checks[f"{k}_color0"] = (len(me.color_attributes) >= 1) if k != "Colision" else True
        co = np.array([o.matrix_world @ v.co for v in me.vertices])
        if k == "Escombro":
            emin, emax = np.minimum(emin, co.min(0)), np.maximum(emax, co.max(0))
        elif k != "Colision":
            mins, maxs = np.minimum(mins, co.min(0)), np.maximum(maxs, co.max(0))
        if k == "Estructura":
            smin, smax = np.minimum(smin, co.min(0)), np.maximum(smax, co.max(0))
    r3 = lambda a: [round(float(x), 3) for x in a]  # noqa: E731
    dims = (maxs - mins).tolist()
    info["medidas_m"] = dict(x=round(dims[0], 3), y=round(dims[1], 3), z=round(dims[2], 3), min=r3(mins), max=r3(maxs),
                             escombro_min=r3(emin) if np.isfinite(emin).all() else None,
                             escombro_max=r3(emax) if np.isfinite(emax).all() else None,
                             nota="ejes de Blender (z arriba, metros); fachada principal hacia -y; pivote = centro de la planta "
                                  "a nivel del suelo. Sin terreno: el edificio apoya en z = 0.")
    sd = (smax - smin).tolist()
    info["medidas_estructura_m"] = dict(x=round(sd[0], 3), y=round(sd[1], 3), z=round(sd[2], 3), min=r3(smin), max=r3(smax))
    if bid.startswith("MUE_"):
        import mue_builder as mu
        info["medidas_m"]["nota"] = ("ejes de Blender (z arriba, metros). Pivote (0, 0, 0) = eje de la rampa en la orilla de la "
                                     "cubierta, a nivel de la arena; la rampa baja hacia -y hasta el pie (y = %.0f, z = 0) y "
                                     "el muelle entra al mar hacia +y. Sin terreno ni agua: la arena va a z = 0, el mar a z = "
                                     "%.1f, la cubierta queda a z = +%.1f y los pilotes bajan a z = %.1f (bajo el agua y el "
                                     "lecho)." % (mu.RAMP_Y0, mu.SEA_Z, mu.DECK_Z, mu.PILE_BOT))
        info["niveles_m"] = dict(arena=0.0, mar=mu.SEA_Z, cubierta=mu.DECK_Z, punta_pilotes=mu.PILE_BOT, pie_rampa_y=mu.RAMP_Y0)
        # la rampa entierra su cimiento 0,8 m en la arena y los pilotes llegan a -7 m
        checks["base_en_suelo"] = (mu.PILE_BOT - 0.1 <= float(mins[2]) <= mu.PILE_BOT + 0.1 and
                                   -0.85 <= float(smin[2]) <= -0.75)
    else:
        # apoya en z = 0; las zapatas de los pilotes y los dados de las cabañas se entierran hasta 0,15 m (bajo el piso del mapa)
        checks["base_en_suelo"] = -0.2 <= float(mins[2]) <= 0.06
    info["comprobaciones"] = checks
    info["ok"] = all(checks.values())
    info["mib_total"] = round(sum(d["mib"] for d in info["mallas"].values()), 2)
    json.dump(info, open(os.path.join(mdir, f"{bid}.json"), "w"), indent=1, ensure_ascii=False)
    log(bid, "OK" if info["ok"] else "REVISAR", {k: v["triangulos"] for k, v in info["mallas"].items()},
        {k: info["medidas_m"][k] for k in ("x", "y", "z")}, info["mib_total"], "MiB", [k for k, v in checks.items() if not v])


def export_glb(path):
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_apply=False, export_yup=True,
                              export_materials="VIEWPORT", export_image_format="NONE", export_vertex_color="ACTIVE",
                              export_all_vertex_colors=False, export_tangents=False, export_normals=True,
                              export_cameras=False, export_lights=False, export_extras=False)


def axes_marker(path):
    """SM_BLK_Ejes: caja de 1,0 x 0,5 x 0,25 m en el octante positivo de Blender (x, y, z). Importada en el motor, su caja
    envolvente dice a qué eje (y signo) fue a parar cada eje de Blender, sin suponer la conversión del importador."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    me = bpy.data.meshes.new("SM_BLK_Ejes")
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x, v.co.y, v.co.z = (v.co.x + 0.5) * 1.0, (v.co.y + 0.5) * 0.5, (v.co.z + 0.5) * 0.25
    bm.to_mesh(me)
    bm.free()
    m = bpy.data.materials.new("BLK_colision")
    me.materials.append(m)
    o = bpy.data.objects.new("SM_BLK_Ejes", me)
    bpy.context.scene.collection.objects.link(o)
    o.select_set(True)
    export_glb(path)


if __name__ == "__main__":
    if "--ejes" in sys.argv:
        axes_marker(sys.argv[sys.argv.index("--ejes") + 1])
    else:
        main()
