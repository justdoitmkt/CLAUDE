"""Per-mesh bakes for materials whose layers use different UVs / projections (run with bpy):
  * MM_DMAR_Overlay with masks on the second UV set (Caravan, Caravan_2, Pier, Wooden_Boat):
    tiled base + dirt/moss/rust overlays (UV0 x tiling) blended by masks (UV1) are evaluated per texel
    of a unique UV layout and the normals are re-expressed in that layout's MikkTSpace frame
  * MM_Vertex_Color_Blend (Diorama_Ground): world-projected layers blended by vertex color
  * MM_Water (Diorama_Water): static approximation of the translucent water
  * Power_Pole: masks on "UV1" but the mesh has a single UV set (UE then reuses UV0)
Writes build/mat/<material>/<mesh>/manifest.json (+ bake_uv.npy when a new UV layout is created)."""
import json, math, os, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bake_materials as BM
from bake_materials import (META, key, tex_meta, srgb_to_lin, raw, s_curve, blend_overlay, normalize,
                            write_basecolor, write_normal, write_orm, NORMAL_DX, blend_angle_corrected)
from ue_mat import load_mic, ROOT
from ue_mesh import load_static_mesh
import build_glb as BG

Image.MAX_IMAGE_PIXELS = None
RES = 4096
TILING = "/Game/Modular_Rural_Cabin/Textures/Tiling/"


# ------------------------------------------------------------------ mip-mapped sampler
class Tex:
    _cache = {}

    def __init__(self, game_path, kind):
        self.kind = kind
        a = raw(game_path).astype(np.float32) / 255.0
        if kind == "normal":
            a = a[..., :2] * 2 - 1
            if key(game_path).split("/")[-1] in NORMAL_DX:
                a[..., 1] *= -1
        else:
            if a.shape[2] == 1:
                a = np.repeat(a, 4, 2); a[..., 3] = 1
            if a.shape[2] == 3:
                a = np.concatenate([a, np.ones_like(a[..., :1])], 2)
            if tex_meta(game_path)["props"].get("SRGB", True):
                a[..., :3] = srgb_to_lin(a[..., :3])
        self.levels = [a]
        while self.levels[-1].shape[0] > 4:
            b = self.levels[-1]
            self.levels.append(0.25 * (b[0::2, 0::2] + b[1::2, 0::2] + b[0::2, 1::2] + b[1::2, 1::2]))
        self.size = a.shape[0]

    @classmethod
    def get(cls, game_path, kind="color"):
        k = (key(game_path), kind)
        if k not in cls._cache:
            cls._cache[k] = Tex(game_path, kind)
        return cls._cache[k]

    def sample(self, uv, footprint, tiling=1.0):
        """uv (N,2) in glTF convention; footprint = UV units per output texel (N,)."""
        lod = np.log2(np.maximum(footprint * self.size * tiling, 1.0))
        lv = np.clip(np.round(lod).astype(np.int64), 0, len(self.levels) - 1)
        out = np.empty((len(uv), self.levels[0].shape[2]), np.float32)
        for L in np.unique(lv):
            sel = lv == L
            a = self.levels[L]; n = a.shape[0]
            x = uv[sel, 0] * tiling * n - 0.5; y = uv[sel, 1] * tiling * n - 0.5
            x0 = np.floor(x).astype(np.int64); y0 = np.floor(y).astype(np.int64)
            fx = (x - x0).astype(np.float32)[:, None]; fy = (y - y0).astype(np.float32)[:, None]
            x0 %= n; y0 %= n; x1 = (x0 + 1) % n; y1 = (y0 + 1) % n
            out[sel] = (a[y0, x0] * (1 - fx) + a[y0, x1] * fx) * (1 - fy) + (a[y1, x0] * (1 - fx) + a[y1, x1] * fx) * fy
        if self.kind == "normal":
            z = np.sqrt(np.clip(1 - out[:, 0] ** 2 - out[:, 1] ** 2, 0, 1))
            return np.concatenate([out, z[:, None]], 1)
        return out


# ------------------------------------------------------------------ rasteriser
def rasterize(uv_t, tris, res):
    """uv_t: per-corner target UV (C,2) glTF convention; tris: (T,3) corner indices.
    Returns texel index (M,), triangle id (M,), barycentrics (M,3)."""
    tri_id = np.full(res * res, -1, np.int64)
    bary = np.zeros((res * res, 3), np.float32)
    P = uv_t * res
    for t, (a, b, c) in enumerate(tris):
        pa, pb, pc = P[a], P[b], P[c]
        lo = np.floor(np.minimum(np.minimum(pa, pb), pc) - 0.5).astype(int)
        hi = np.ceil(np.maximum(np.maximum(pa, pb), pc) + 0.5).astype(int)
        lo = np.clip(lo, 0, res - 1); hi = np.clip(hi, 0, res)
        if hi[0] <= lo[0] or hi[1] <= lo[1]:
            continue
        xs, ys = np.meshgrid(np.arange(lo[0], hi[0]) + 0.5, np.arange(lo[1], hi[1]) + 0.5)
        x, y = xs.ravel(), ys.ravel()
        d = (pb[0] - pa[0]) * (pc[1] - pa[1]) - (pc[0] - pa[0]) * (pb[1] - pa[1])
        if abs(d) < 1e-12:
            continue
        w1 = ((x - pa[0]) * (pc[1] - pa[1]) - (pc[0] - pa[0]) * (y - pa[1])) / d
        w2 = ((pb[0] - pa[0]) * (y - pa[1]) - (x - pa[0]) * (pb[1] - pa[1])) / d
        w0 = 1 - w1 - w2
        eps = 1e-4
        inside = (w0 >= -eps) & (w1 >= -eps) & (w2 >= -eps)
        idx = (y[inside] - 0.5).astype(np.int64) * res + (x[inside] - 0.5).astype(np.int64)
        tri_id[idx] = t
        bary[idx] = np.stack([w0[inside], w1[inside], w2[inside]], 1)
    texels = np.nonzero(tri_id >= 0)[0]
    return texels, tri_id[texels], bary[texels]


def dilate(img, filled, iters=24):
    """Grow baked islands outward so mip-mapping/bilinear never reads empty texels."""
    img = img.copy(); filled = filled.copy()
    for _ in range(iters):
        acc = np.zeros_like(img); cnt = np.zeros(filled.shape, np.float32)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            f = np.roll(filled, (dy, dx), (0, 1)); v = np.roll(img, (dy, dx), (0, 1))
            acc += v * f[..., None]; cnt += f
        new = (~filled) & (cnt > 0)
        img[new] = acc[new] / cnt[new][:, None]
        filled |= new
        if filled.all():
            break
    # anything still empty gets the mean colour
    img[~filled] = img[filled].mean(0)
    return img


# ------------------------------------------------------------------ Blender frames
def blender_frames(a, uv_layers):
    """MikkTSpace frames per corner for each named UV layer (Blender space; same mesh as the builder)."""
    import bpy
    P = a["positions"] * BG.SCALE * np.array([1, -1, 1])
    N = a["normals"] * np.array([1, -1, 1])
    tris = a["tris"]; corner_vi = tris.reshape(-1); corner_v = a["vi_vert"][corner_vi]
    me = bpy.data.meshes.new("frames")
    me.vertices.add(len(P)); me.vertices.foreach_set("co", P.astype(np.float32).ravel())
    me.loops.add(len(corner_v)); me.loops.foreach_set("vertex_index", corner_v.astype(np.int32))
    me.polygons.add(len(tris)); me.polygons.foreach_set("loop_start", (np.arange(len(tris)) * 3).astype(np.int32))
    for name, uv in uv_layers.items():
        lay = me.uv_layers.new(name=name)
        lay.data.foreach_set("uv", np.stack([uv[:, 0], 1 - uv[:, 1]], 1).astype(np.float32).ravel())
    me.update(calc_edges=True)
    ln = N[corner_vi]; ln /= np.maximum(np.linalg.norm(ln, axis=1, keepdims=True), 1e-12)
    me.normals_split_custom_set(ln.astype(np.float32).tolist())
    out = {}
    for name in uv_layers:
        me.calc_tangents(uvmap=name)
        n = len(me.loops)
        T = np.empty(n * 3, np.float32); me.loops.foreach_get("tangent", T)
        Nn = np.empty(n * 3, np.float32); me.loops.foreach_get("normal", Nn)
        s = np.empty(n, np.float32); me.loops.foreach_get("bitangent_sign", s)
        T = T.reshape(n, 3); Nn = Nn.reshape(n, 3)
        out[name] = (T, s[:, None] * np.cross(Nn, T), Nn)
    me.free_tangents()
    bpy.data.meshes.remove(me)
    return out


# ------------------------------------------------------------------ evaluation
def footprint(uv_src, uv_t, tris, res):
    """UV-units (source) per output texel, per triangle."""
    a, b, c = (uv_src[tris[:, i]] for i in range(3))
    A, B, C = (uv_t[tris[:, i]] * res for i in range(3))
    ds = np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1]))
    dt = np.abs((B[:, 0] - A[:, 0]) * (C[:, 1] - A[:, 1]) - (C[:, 0] - A[:, 0]) * (B[:, 1] - A[:, 1]))
    return np.sqrt(ds / np.maximum(dt, 1e-12))


def eval_dmar(mic, uv0, fp0, uvm, fpm):
    P, S, T = mic["params"], mic["params"]["scalar"], mic["params"]["texture"]
    bt, ot = S.get("Base Texture Tiling", 1.0), S.get("Overlay Tiling", 1.0)
    M = Tex.get(T["DMAR"]).sample(uvm, fpm)
    dirt = s_curve(M[:, 0], S.get("Dirt Contrast", 1.0))
    moss = s_curve(M[:, 1], S.get("Moss Contrast", 1.0))
    nb = Tex.get(T["Normal"], "normal").sample(uv0, fp0, bt)
    r = M[:, 3] if P["switch"].get("Rust?", False) else np.zeros_like(dirt)
    rust = s_curve(np.clip(r + 2 * r * nb[:, 0], 0, 1), S.get("Rust Contrast", 1.0))
    tint = np.array(P["vector"].get("Overlay Tint", (0.401, 0.401, 0.401, 1))[:3], np.float32)
    C = Tex.get(T["Basecolor"]).sample(uv0, fp0, bt); D = Tex.get(T["DET"]).sample(uv0, fp0, bt)
    s = lambda n, k="color": Tex.get(TILING + n, k).sample(uv0, fp0, ot)
    RC, RD, RN = s("Rust_Generic_BaseColor"), s("Rust_Generic_DET"), s("Rust_Generic_Normal", "normal")
    MC, MD, MN = s("Moss_BaseColor"), s("Moss_DET"), s("Moss_Normal", "normal")
    DC, DD, DN = s("Dirt_Basecolor"), s("Dirt_DET"), s("Dirt_Normal", "normal")
    lerp = lambda x, y, t: x + (y - x) * (t[:, None] if x.ndim == 2 else t)
    base = lerp(lerp(lerp(blend_overlay(tint, C[:, :3]), RC[:, :3], rust), MC[:, :3], moss), DC[:, :3], dirt)
    metal = lerp(lerp(lerp(D[:, 0], RD[:, 0], rust), MD[:, 0], moss), DD[:, 0], dirt)
    rough = lerp(lerp(lerp(D[:, 1], RD[:, 1] * S.get("Rust Roughness", 1.0), rust),
                      MD[:, 1] * S.get("Moss Roughness", 1.0), moss), DD[:, 1] * S.get("Dirt Roughness", 1.0), dirt)
    N = lerp(lerp(lerp(nb, RN, rust), MN, moss), DN, dirt)
    ao = lerp(D[:, 2], DD[:, 2], dirt) * M[:, 2]
    return dict(base=np.clip(base, 0, 1), metal=metal, rough=rough, ao=ao, normal=normalize(N))


def eval_vertex_blend(mic, uv0, fp0, wpos, fpw, vcol):
    S, T = mic["params"]["scalar"], mic["params"]["texture"]
    wuv = wpos[:, :2] / 300.0                                  # WorldPosition.xy / 300
    sw = lambda p, k="color": Tex.get(p, k).sample(wuv, fpw)
    BC1, BC2, BC3 = sw(T["Basecolor 1"]), sw(T["Basecolor 2"]), sw(T["Basecolor 3"])
    N_sand, N_grass, N_rock = sw(TILING + "Sand_normal", "normal"), sw(TILING + "Grass_Normal", "normal"), sw(TILING + "Rocky_Ground_normal", "normal")
    D1, D2, D3 = (Tex.get(T[f"DET {i}"]).sample(uv0, fp0) for i in (1, 2, 3))   # DET sampled with UV0
    r, g, b, a = (vcol[:, i] for i in range(4))
    lerp = lambda x, y, t: x + (y - x) * (t[:, None] if x.ndim == 2 else t)
    base = lerp(lerp(lerp(BC2[:, :3], BC1[:, :3], b), BC2[:, :3], g), BC3[:, :3], r)
    base = lerp(base, base * S.get("Water Darkness", 0.5), a)
    r1, r2, r3 = S.get("Rougness 1", 1.0), S.get("Rougness 2", 1.0), S.get("Rougness 3", 1.0)
    rough = lerp(lerp(lerp(D2[:, 1] * r2, D1[:, 1] * r1, b), D2[:, 1] * r2, g), D3[:, 1] * r3, r)
    rough = lerp(rough, np.zeros_like(rough), a)
    water_n = normalize(np.array([[0.07345565, -0.02902924, 0.38541666]], np.float32))   # UE constant, Y flipped (GL)
    N = lerp(lerp(lerp(lerp(N_sand, N_rock, b), N_sand, g), N_grass, r), np.repeat(water_n, len(r), 0), a)
    return dict(base=np.clip(base, 0, 1), metal=np.zeros_like(rough), rough=rough, ao=np.ones_like(rough), normal=normalize(N))


def eval_water(mic, wpos, fpw):
    S = mic["params"]["scalar"]
    t = S.get("Tiling", 5.0)
    wuv = wpos[:, :2] / 300.0 * t
    n1 = Tex.get(TILING + "Water_normal", "normal").sample(wuv, fpw * t)
    n2 = Tex.get(TILING + "Water_2_normal", "normal").sample(wuv, fpw * t)
    return normalize(blend_angle_corrected(n1, n2))


# ------------------------------------------------------------------ driver
def mesh_data(name):
    path = [os.path.join(dp, f) for dp, _, fs in os.walk(ROOT + "/Meshes") for f in fs
            if f == name + ".uasset" and "Blueprints" not in dp][0]
    sm = load_static_mesh(path)
    return sm, BG.mesh_arrays(sm)


def tri_material(sm, a):
    return np.array([BG.section_material(sm, s) for s in a["tri_section"]])


def pack_uv(a, src_uv, margin=0.004):
    """New non-overlapping layout: the mesh's lightmap islands re-packed to fill the square."""
    import bpy
    tris = a["tris"]; corner_vi = tris.reshape(-1)
    P = a["positions"] * BG.SCALE * np.array([1, -1, 1]); corner_v = a["vi_vert"][corner_vi]
    me = bpy.data.meshes.new("pack")
    me.vertices.add(len(P)); me.vertices.foreach_set("co", P.astype(np.float32).ravel())
    me.loops.add(len(corner_v)); me.loops.foreach_set("vertex_index", corner_v.astype(np.int32))
    me.polygons.add(len(tris)); me.polygons.foreach_set("loop_start", (np.arange(len(tris)) * 3).astype(np.int32))
    lay = me.uv_layers.new(name="UV")
    uv = src_uv[corner_vi]
    lay.data.foreach_set("uv", np.stack([uv[:, 0], 1 - uv[:, 1]], 1).astype(np.float32).ravel())
    me.update()
    ob = bpy.data.objects.new("pack", me); bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.select_all(action="SELECT")
    bpy.ops.uv.pack_islands(rotate=True, margin=margin, shape_method="CONCAVE")
    bpy.ops.object.mode_set(mode="OBJECT")
    out = np.empty(len(corner_vi) * 2, np.float32); me.uv_layers["UV"].data.foreach_get("uv", out)
    out = out.reshape(-1, 2); out[:, 1] = 1 - out[:, 1]
    bpy.data.objects.remove(ob); bpy.data.meshes.remove(me)
    return out.astype(np.float64)                               # per corner (builder order)


def coverage(uv_t, tris):
    A = uv_t[tris[:, 0]]; B = uv_t[tris[:, 1]]; C = uv_t[tris[:, 2]]
    return float(np.abs((B[:, 0] - A[:, 0]) * (C[:, 1] - A[:, 1]) - (C[:, 0] - A[:, 0]) * (B[:, 1] - A[:, 1])).sum() / 2)


def bake_mesh(mesh_name, mic_names, target, res=RES):
    """target: 'UV1' / 'UV2' / 'UV0' / 'PACK:<k>' (re-packed islands of UV set k)."""
    sm, a = mesh_data(mesh_name)
    tm = tri_material(sm, a)
    slots = [m["material"].split(".")[-1] for m in sm["materials"]]
    slot_ids = lambda m: [i for i, x in enumerate(slots) if x == m]
    sel_tris = np.isin(tm, [i for m in mic_names for i in slot_ids(m)])
    tris_all = a["tris"]
    corner_vi = tris_all.reshape(-1)
    uv0 = a["uvs"][0][corner_vi]
    n_uv = len(a["uvs"])
    uv_corner = lambda k: a["uvs"][min(k, n_uv - 1)][corner_vi]
    if target.startswith("PACK"):
        uv_t = pack_uv(a, a["uvs"][int(target.split(":")[1])])
    else:
        uv_t = uv_corner(int(target[2:]))
    ctris = np.arange(len(corner_vi)).reshape(-1, 3)              # corner indices per triangle
    T = ctris[sel_tris]
    print(f"{mesh_name}: {len(T)} tris, target {target}, coverage {coverage(uv_t, T):.2f}")
    texels, tid, bary = rasterize(uv_t, T, res)
    tri = T[tid]
    interp = lambda arr: (arr[tri] * bary[..., None]).sum(1)
    fp0_tri = footprint(uv0, uv_t, T, res)
    results = {}
    for mic_name in mic_names:
        mic = load_mic(f"{ROOT}/Materials/Instances/{mic_name}.uasset")
        msel = np.isin(tm[sel_tris][tid], slot_ids(mic_name))
        if not msel.any():
            continue
        t_ = tri[msel]; b_ = bary[msel]
        ip = lambda arr: (arr[t_] * b_[..., None]).sum(1)
        u0 = ip(uv0); f0 = fp0_tri[tid[msel]]
        master = mic["master"].split(".")[-1]
        if master == "MM_DMAR_Overlay":
            k = 1 if mic["params"]["switch"].get("Second UV map?", False) else 0
            uvm = uv_corner(k)
            r = eval_dmar(mic, u0, f0, ip(uvm), footprint(uvm, uv_t, T, res)[tid[msel]])
        elif master == "MM_Vertex_Color_Blend":
            vcol = a.get("colors")
            wpos = a["positions"][a["vi_vert"][corner_vi]]
            fpw = footprint(wpos[:, :2] / 300.0, uv_t, T, res)[tid[msel]]
            r = eval_vertex_blend(mic, u0, f0, ip(wpos), fpw, ip(vcol))
        results[mic_name] = (texels[msel], r, t_, b_)
    # tangent-space frame change UV0 -> target layout
    if target != "UV0":
        fr = blender_frames(a, {"src": uv0, "tgt": uv_t})
        Ts, Bs, Ns = fr["src"]; Tt, Bt, Nt = fr["tgt"]
        for mic_name, (tx, r, t_, b_) in results.items():
            ip = lambda arr: (arr[t_] * b_[..., None]).sum(1)
            n = r["normal"]
            w = n[:, :1] * ip(Ts) + n[:, 1:2] * ip(Bs) + n[:, 2:3] * ip(Ns)
            r["normal"] = normalize(np.stack([(w * ip(Tt)).sum(1), (w * ip(Bt)).sum(1), (w * ip(Nt)).sum(1)], 1))
    # assemble shared images for all materials of this mesh
    base = np.zeros((res * res, 3), np.float32); orm = np.zeros((res * res, 3), np.float32)
    nrm = np.zeros((res * res, 3), np.float32); filled = np.zeros(res * res, bool)
    for mic_name, (tx, r, _, _) in results.items():
        base[tx] = r["base"]; orm[tx] = np.stack([r["ao"], r["rough"], r["metal"]], 1); nrm[tx] = r["normal"]; filled[tx] = True
    shape = (res, res)
    out_dir = f"{BM.OUT}/{mic_names[0]}/{mesh_name}"
    os.makedirs(out_dir, exist_ok=True)
    f2 = filled.reshape(shape)
    base_i = dilate(base.reshape(shape + (3,)), f2)
    orm_i = dilate(orm.reshape(shape + (3,)), f2)
    nrm_i = dilate(nrm.reshape(shape + (3,)), f2)
    files = dict(basecolor=write_basecolor(out_dir, base_i), orm=write_orm(out_dir, orm_i[..., 0], orm_i[..., 1], orm_i[..., 2]),
                 normal=write_normal(out_dir, nrm_i))
    if target.startswith("PACK"):
        np.save(f"{out_dir}/bake_uv.npy", uv_t)
    for mic_name in mic_names:
        d = f"{BM.OUT}/{mic_name}/{mesh_name}"; os.makedirs(d, exist_ok=True)
        man = dict(name=mic_name, mesh_suffix=f"@{mesh_name}", master=load_mic(f"{ROOT}/Materials/Instances/{mic_name}.uasset")["master"].split(".")[-1],
                   alpha_mode="OPAQUE", double_sided=False, cutoff=0.3333, res=res, occlusion=True,
                   basecolor_original=False, normal_original=False,
                   uv=("BAKE" if target.startswith("PACK") else target), bake_uv=(f"{out_dir}/bake_uv.npy" if target.startswith("PACK") else None),
                   coverage=coverage(uv_t, T), **files)
        json.dump(man, open(f"{d}/manifest.json", "w"), indent=1)
    print(f"   -> {out_dir}")


def bake_water(mesh_name="Diorama_Water", mic_name="Water_Lake", res=1024):
    sm, a = mesh_data(mesh_name)
    mic = load_mic(f"{ROOT}/Materials/Instances/{mic_name}.uasset")
    corner_vi = a["tris"].reshape(-1); uv0 = a["uvs"][0][corner_vi]
    ctris = np.arange(len(corner_vi)).reshape(-1, 3)
    tm = tri_material(sm, a)
    slots = [m["material"].split(".")[-1] for m in sm["materials"]]
    T = ctris[np.isin(tm, [i for i, x in enumerate(slots) if x == mic_name])]
    texels, tid, bary = rasterize(uv0, T, res)
    tri = T[tid]
    wpos = a["positions"][a["vi_vert"][corner_vi]]
    fpw = footprint(wpos[:, :2] / 300.0, uv0, T, res)[tid]
    n = eval_water(mic, (wpos[tri] * bary[..., None]).sum(1), fpw)
    img = np.zeros((res * res, 3), np.float32); img[texels] = n
    filled = np.zeros(res * res, bool); filled[texels] = True
    out_dir = f"{BM.OUT}/{mic_name}/{mesh_name}"; os.makedirs(out_dir, exist_ok=True)
    nfile = write_normal(out_dir, dilate(img.reshape(res, res, 3), filled.reshape(res, res)))
    S = mic["params"]["scalar"]
    man = dict(name=mic_name, mesh_suffix=f"@{mesh_name}", master="MM_Water", alpha_mode="BLEND", double_sided=False,
               basecolor=None, basecolor_factor=[0.0, 0.0, 0.0], alpha_factor=float(S.get("Opacity Fresnel Base", 0.5)),
               metallic_factor=0.3, roughness_factor=0.0, emissive_factor=[0.039063, 0.039324, 0.046875],
               orm=None, occlusion=False, normal=nfile, normal_original=False, uv="UV0", res=res,
               note="static approximation of the UE water (fresnel/refraction/depth fade/panning are runtime effects)")
    json.dump(man, open(f"{out_dir}/manifest.json", "w"), indent=1)
    # the water side wall uses the same parent material
    print(f"{mesh_name}: water normal baked -> {out_dir}")


def bake_power_pole():
    """Second-UV masks on a single-UV mesh: UE feeds UV0 to TexCoord[1]; plain UV0 bake."""
    mic = load_mic(f"{ROOT}/Materials/Instances/Power_Pole.uasset")
    out_dir = f"{BM.OUT}/Power_Pole"
    info = dict(name="Power_Pole", master="MM_DMAR_Overlay", alpha_mode="OPAQUE", double_sided=False, cutoff=0.3333, uv="UV0",
                note="Second UV map? = true but Power_Pole_1 has one UV set: UE reuses UV0")
    BM.bake_dmar_uv0(mic, out_dir, info)
    json.dump(info, open(f"{out_dir}/manifest.json", "w"), indent=1)
    print("Power_Pole: UV0 bake")


if __name__ == "__main__":
    jobs = sys.argv[1:] or ["power_pole", "caravan", "pier", "boat", "ground", "water"]
    for j in jobs:
        if j == "power_pole": bake_power_pole()
        elif j == "caravan": bake_mesh("Caravan", ["Caravan", "Caravan_2"], "UV1")
        elif j == "pier": bake_mesh("Pier", ["Pier"], "UV1")
        elif j == "boat": bake_mesh("Wooden_Boat", ["Wooden_Boat"], "UV2")
        elif j == "ground": bake_mesh("Diorama_Ground", ["Diorama_Ground"], "UV0")
        elif j == "water": bake_water()
