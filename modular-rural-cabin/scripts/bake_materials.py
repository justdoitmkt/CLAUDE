"""Evaluate the kit's UE4 material instances into glTF metal/rough textures.

Every texture is evaluated exactly as the UE4.22 material graph does, texel by texel:
  * sRGB-flagged textures are linearised before the math (as the UE sampler does), base color is
    re-encoded to sRGB for glTF; DET = (R metallic, G roughness, B ambient occlusion) -> glTF ORM
  * normal maps: Z rebuilt from XY (BC5, as UE does), FlattenNormal "power", detail normal blended
    with BlendAngleCorrectedNormals (RNM), overlay layers lerped; written in OpenGL convention
  * outputs that would be identical to a source image are not re-encoded: the original PNG is used
Materials whose layers are sampled with different UVs/tilings (MM_DMAR_Overlay with second-UV masks,
MM_Vertex_Color_Blend, MM_Water) are baked per mesh by bake_special.py instead."""
import json, os, sys, hashlib, shutil
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ue_mat import load_mic, master_defaults, ROOT

Image.MAX_IMAGE_PIXELS = None
WORK = os.environ.get("KIT_WORK", "/home/user/work2")
META = json.load(open(f"{WORK}/tex_src/meta.json"))
OUT = f"{WORK}/build/mat"
DEFAULT_NORMAL = "/Game/Modular_Rural_Cabin/Textures/Utility/Default_Normal"
LUMA = np.array([0.3, 0.59, 0.11], np.float32)            # UE Desaturation default LuminanceFactors
DMAR_RES = 4096

# Normal maps authored in DirectX convention (checked per map, see README); all others are OpenGL.
NORMAL_DX = set(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "normal_dx.json"))))


# ---------------------------------------------------------------- texture access
def key(game_path):
    return game_path.split(".")[0]


def tex_meta(game_path):
    return META[key(game_path)]


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4).astype(np.float32)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(c, 1 / 2.4) - 0.055).astype(np.float32)


_cache = {}


def raw(game_path):
    """uint8 HxWx4 (or HxWx1) array of the source image."""
    k = key(game_path)
    if k not in _cache:
        im = Image.open(tex_meta(game_path)["file"])
        im = im.convert("RGBA") if im.mode != "L" else im
        a = np.asarray(im)
        _cache[k] = a if a.ndim == 3 else a[..., None]
        if len(_cache) > 24:
            _cache.pop(next(iter(_cache)))
    return _cache[k]


def resize(a, size):
    """Resize float HxWxC array to size x size (Lanczos per channel)."""
    if a.shape[0] == size and a.shape[1] == size:
        return a
    out = np.empty((size, size, a.shape[2]), np.float32)
    for c in range(a.shape[2]):
        out[..., c] = np.asarray(Image.fromarray(a[..., c].astype(np.float32), "F").resize((size, size), Image.LANCZOS))
    return out


def sample(a, res, tiling=1.0):
    """Sample float texture `a` on a res x res output grid covering UV [0,1]^2 * tiling (wrap, bilinear).
    The texture is pre-filtered to the output texel density first (no aliasing)."""
    if tiling == 1.0:
        return resize(a, res)
    dens = res / tiling                                   # source texels per tile at output density
    if dens < a.shape[0]:
        a = resize(a, max(8, int(round(dens))))
    n = a.shape[0]
    x = (np.arange(res, dtype=np.float64) + 0.5) / res * tiling * n - 0.5
    x0 = np.floor(x).astype(np.int64); f = (x - x0).astype(np.float32)
    i0, i1 = x0 % n, (x0 + 1) % n
    rows = a[i0] * (1 - f)[:, None, None] + a[i1] * f[:, None, None]
    return rows[:, i0] * (1 - f)[None, :, None] + rows[:, i1] * f[None, :, None]


def color(game_path, res, tiling=1.0):
    """Shader-space RGBA (sRGB textures linearised, alpha linear)."""
    a = raw(game_path).astype(np.float32) / 255.0
    if a.shape[2] == 1:
        a = np.repeat(a, 4, 2); a[..., 3] = 1
    if tex_meta(game_path)["props"].get("SRGB", True):
        a = np.concatenate([srgb_to_lin(a[..., :3]), a[..., 3:]], 2)
    return sample(a, res, tiling)


def normal(game_path, res, tiling=1.0):
    """Tangent-space normal in OpenGL convention, Z rebuilt from XY like UE's BC5 path."""
    a = raw(game_path)[..., :2].astype(np.float32) / 255.0 * 2 - 1
    if key(game_path).split("/")[-1] in NORMAL_DX:
        a[..., 1] *= -1
    a = sample(a, res, tiling)
    z = np.sqrt(np.clip(1 - a[..., 0] ** 2 - a[..., 1] ** 2, 0, 1))
    return np.concatenate([a, z[..., None]], 2)


# ---------------------------------------------------------------- UE material functions
def desaturate(c, fraction):
    if fraction == 0:
        return c
    l = (c * LUMA).sum(-1, keepdims=True)
    return c + (l - c) * fraction


def flatten_normal(n, flatness):
    """/Engine/.../FlattenNormal: lerp((0,0,1), Normal, Flatness)."""
    if flatness == 1:
        return n
    out = n * flatness
    out[..., 2] += 1 - flatness
    return out


def blend_angle_corrected(base, detail):
    """/Engine/.../BlendAngleCorrectedNormals (reoriented normal mapping)."""
    t = base.copy(); t[..., 2] += 1
    u = detail * np.array([-1, -1, 1], np.float32)
    return t * ((t * u).sum(-1, keepdims=True) / np.maximum(t[..., 2:3], 1e-6)) - u


def s_curve(x, exponent):
    """/Engine/.../SCurve: contrast curve around 0.5."""
    if exponent == 1:
        return x
    x = np.clip(x, 0, 1)
    lo = 0.5 * np.power(2 * x, exponent)
    hi = 1 - 0.5 * np.power(2 * (1 - x), exponent)
    return np.where(x < 0.5, lo, hi).astype(np.float32)


def blend_overlay(base, blend):
    """/Engine/.../Blend_Overlay (Base = first input)."""
    return np.where(base <= 0.5, 2 * base * blend, 1 - 2 * (1 - base) * (1 - blend)).astype(np.float32)


def hue_shift(c, turns):
    """/Engine/.../HueShift: rotate RGB about the grey axis (RotateAboutAxis, 1 = 360 deg)."""
    if turns == 0:
        return c
    k = np.full(3, 1 / np.sqrt(3), np.float32)
    th = 2 * np.pi * turns
    along = (c * k).sum(-1, keepdims=True) * k
    u = c - along
    v = np.cross(k, u)
    return along + u * np.cos(th) + v * np.sin(th)


def normalize(n):
    return n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-8)


# ---------------------------------------------------------------- outputs
def save_png(path, arr8, mode):
    Image.fromarray(arr8, mode).save(path, compress_level=6)


def write_basecolor(out_dir, lin_rgb, alpha=None):
    rgb = np.round(lin_to_srgb(lin_rgb) * 255).astype(np.uint8)
    if alpha is not None:
        a = np.round(np.clip(alpha, 0, 1) * 255).astype(np.uint8)
        save_png(f"{out_dir}/basecolor.png", np.concatenate([rgb, a[..., None]], 2), "RGBA")
    else:
        save_png(f"{out_dir}/basecolor.png", rgb, "RGB")
    return f"{out_dir}/basecolor.png"


def write_normal(out_dir, n):
    n = normalize(n)
    save_png(f"{out_dir}/normal.png", np.round((n * 0.5 + 0.5) * 255).astype(np.uint8), "RGB")
    return f"{out_dir}/normal.png"


def write_orm(out_dir, ao, rough, metal):
    arr = np.stack([np.clip(x, 0, 1) for x in (ao, rough, metal)], -1)
    save_png(f"{out_dir}/orm.png", np.round(arr * 255).astype(np.uint8), "RGB")
    return f"{out_dir}/orm.png"


def res_of(*paths):
    return max(tex_meta(p)["width"] for p in paths if p)


def is_flat(game_path):
    return not game_path or key(game_path) == DEFAULT_NORMAL


# ---------------------------------------------------------------- masters
def bake_basic(mic, out_dir, info):
    P, S, T = mic["params"], mic["params"]["scalar"], mic["params"]["texture"]
    overlay = mic["master"].endswith("MM_Basic_Overlay") and P["switch"].get("Overlay?", False)
    bc, det, nrm = T["Basecolor"], T["DET"], T["Normal"]
    det_n = None if is_flat(T.get("Detail normal")) else T["Detail normal"]
    res = res_of(bc, det, nrm, *( [T["Overlay Basecolor"], T["Overlay DET"], T["Overlay Normal"]] if overlay else []))
    cp, de = S.get("Color Power", 1.0), S.get("Deaturation", 0.0)
    rp = S.get("Roughness Power", 1.0)
    np_, dnp, dt = S.get("Normal Power", 2.0), S.get("Detail Normal Power", 2.0), S.get("Detail Tiling", 1.0)

    C = color(bc, res)
    base = np.clip(desaturate(np.power(np.maximum(C[..., :3], 0), cp), de), 0, 1)
    D = color(det, res)
    metal, rough, ao = D[..., 0], np.power(np.maximum(D[..., 1], 1e-8), rp), D[..., 2]
    N = flatten_normal(normal(nrm, res), np_)
    if det_n:
        tiling = max(1, round(dt))                       # integer so the baked texture tiles seamlessly
        info["detail_normal"] = dict(texture=key(det_n).split("/")[-1], tiling_ue=dt, tiling_baked=tiling, power=dnp)
        N = blend_angle_corrected(N, flatten_normal(normal(det_n, res, tiling), dnp))
    if overlay:
        mask = s_curve(C[..., 3], S.get("Overlay Amount", 1.0))[..., None]
        tint = np.array(P["vector"].get("Overlay Color Tint", (0, 0, 0, 1))[:3], np.float32)
        OC, OD = color(T["Overlay Basecolor"], res), color(T["Overlay DET"], res)
        base = base + (blend_overlay(tint, OC[..., :3]) - base) * mask
        m = mask[..., 0]
        metal = metal + (OD[..., 0] - metal) * m
        rough = rough + (np.power(np.maximum(OD[..., 1], 1e-8), S.get("Overlay Roughness Power", 1.0)) - rough) * m
        N = normalize(N)
        N = N + (normal(T["Overlay Normal"], res) - N) * C[..., 3:4]
        info["overlay"] = dict(basecolor=key(T["Overlay Basecolor"]).split("/")[-1], amount=S.get("Overlay Amount"))

    # base color: keep the source PNG when the graph leaves it untouched
    if cp == 1 and de == 0 and not overlay:
        info["basecolor"] = tex_meta(bc)["file"]; info["basecolor_original"] = True
    else:
        info["basecolor"] = write_basecolor(out_dir, base); info["basecolor_original"] = False
    if np_ == 1 and not det_n and not overlay and key(nrm).split("/")[-1] not in NORMAL_DX:
        info["normal"] = tex_meta(nrm)["file"]; info["normal_original"] = True
    else:
        info["normal"] = write_normal(out_dir, N); info["normal_original"] = False
    info["orm"] = write_orm(out_dir, ao, rough, metal)
    info["occlusion"] = bool(ao.min() < 0.98)
    info["res"] = res


def bake_foliage(mic, out_dir, info):
    S, T = mic["params"]["scalar"], mic["params"]["texture"]
    bc, det, nrm = T["Basecolor"], T["DET"], T["Normal"]
    res = res_of(bc, det, nrm)
    cp, de, hs = S.get("Color Power", 1.0), S.get("Deaturation", 0.0), S.get("Hue Shift", 0.0)
    C = color(bc, res)
    if cp == 1 and de == 0 and hs == 0:
        info["basecolor"] = tex_meta(bc)["file"]; info["basecolor_original"] = True
    else:
        base = np.clip(hue_shift(desaturate(np.power(np.maximum(C[..., :3], 0), cp), de), hs), 0, 1)
        info["basecolor"] = write_basecolor(out_dir, base, C[..., 3]); info["basecolor_original"] = False
    D = color(det, res)
    rough = np.power(np.maximum(D[..., 1], 1e-8), S.get("Roughness Power", 1.0))
    info["orm"] = write_orm(out_dir, np.ones_like(rough), rough, np.zeros_like(rough))
    info["occlusion"] = False
    if key(nrm).split("/")[-1] in NORMAL_DX:
        info["normal"] = write_normal(out_dir, normal(nrm, res)); info["normal_original"] = False
    else:
        info["normal"] = tex_meta(nrm)["file"]; info["normal_original"] = True
    info["res"] = res
    info["alpha_mode"] = "MASK"


def bake_glass(mic, out_dir, info):
    T = mic["params"]["texture"]
    bc, det, nrm = T["Basecolor"], T["DET"], T["Normal"]
    res = res_of(bc, det, nrm)
    info["basecolor"] = tex_meta(bc)["file"]; info["basecolor_original"] = True
    D = color(det, res)
    info["orm"] = write_orm(out_dir, D[..., 2], D[..., 1], D[..., 0])
    info["occlusion"] = bool(D[..., 2].min() < 0.98)
    if key(nrm).split("/")[-1] in NORMAL_DX:
        info["normal"] = write_normal(out_dir, normal(nrm, res)); info["normal_original"] = False
    else:
        info["normal"] = tex_meta(nrm)["file"]; info["normal_original"] = True
    info["res"] = res
    info["alpha_mode"] = "BLEND"


def bake_dmar_uv0(mic, out_dir, info, res=DMAR_RES):
    """MM_DMAR_Overlay when masks and base share UV0 inside [0,1] (no second UV map)."""
    P, S, T = mic["params"], mic["params"]["scalar"], mic["params"]["texture"]
    bt, ot = S.get("Base Texture Tiling", 1.0), S.get("Overlay Tiling", 1.0)
    tex = lambda n: f"/Game/Modular_Rural_Cabin/Textures/Tiling/{n}"
    M = color(T["DMAR"], res)
    dirt = s_curve(M[..., 0], S.get("Dirt Contrast", 1.0))
    moss = s_curve(M[..., 1], S.get("Moss Contrast", 1.0))
    rust_in = M[..., 3] if P["switch"].get("Rust?", False) else np.zeros_like(dirt)
    nb = normal(T["Normal"], res, bt)
    rust_in = rust_in + 2 * rust_in * nb[..., 0]           # lerp(r, 3r, Normal.R), Normal.R in [-1, 1]
    rust = s_curve(np.clip(rust_in, 0, 1), S.get("Rust Contrast", 1.0))
    tint = np.array(P["vector"].get("Overlay Tint", (0.401, 0.401, 0.401, 1))[:3], np.float32)

    C, D = color(T["Basecolor"], res, bt), color(T["DET"], res, bt)
    RC, RD, RN = color(tex("Rust_Generic_BaseColor"), res, ot), color(tex("Rust_Generic_DET"), res, ot), normal(tex("Rust_Generic_Normal"), res, ot)
    MC, MD, MN = color(tex("Moss_BaseColor"), res, ot), color(tex("Moss_DET"), res, ot), normal(tex("Moss_Normal"), res, ot)
    DC, DD, DN = color(tex("Dirt_Basecolor"), res, ot), color(tex("Dirt_DET"), res, ot), normal(tex("Dirt_Normal"), res, ot)
    lerp = lambda a, b, t: a + (b - a) * (t[..., None] if a.ndim == 3 else t)

    base = lerp(lerp(lerp(blend_overlay(tint, C[..., :3]), RC[..., :3], rust), MC[..., :3], moss), DC[..., :3], dirt)
    metal = lerp(lerp(lerp(D[..., 0], RD[..., 0], rust), MD[..., 0], moss), DD[..., 0], dirt)
    rough = lerp(lerp(lerp(D[..., 1], RD[..., 1] * S.get("Rust Roughness", 1.0), rust),
                      MD[..., 1] * S.get("Moss Roughness", 1.0), moss), DD[..., 1] * S.get("Dirt Roughness", 1.0), dirt)
    N = lerp(lerp(lerp(nb, RN, rust), MN, moss), DN, dirt)
    ao = lerp(D[..., 2], DD[..., 2], dirt) * M[..., 2]
    info["basecolor"] = write_basecolor(out_dir, np.clip(base, 0, 1)); info["basecolor_original"] = False
    info["normal"] = write_normal(out_dir, N); info["normal_original"] = False
    info["orm"] = write_orm(out_dir, ao, rough, metal)
    info["occlusion"] = True
    info["res"] = res
    info["tiling"] = dict(base=bt, overlay=ot)


def bake(mic_name):
    mic = load_mic(f"{ROOT}/Materials/Instances/{mic_name}.uasset")
    master = mic["master"].split(".")[-1]
    out_dir = f"{OUT}/{mic_name}"
    os.makedirs(out_dir, exist_ok=True)
    info = dict(name=mic_name, master=master, alpha_mode="OPAQUE", double_sided=False, cutoff=0.3333,
                uv="UV0")
    md = master_defaults(mic["master"])["props"]
    info["double_sided"] = bool(md.get("TwoSided", False))
    if master in ("MM_Basic", "MM_Basic_Overlay"):
        bake_basic(mic, out_dir, info)
    elif master == "MM_Foliage":
        bake_foliage(mic, out_dir, info)
    elif master == "MM_Glass":
        bake_glass(mic, out_dir, info)
    elif master == "MM_DMAR_Overlay" and not mic["params"]["switch"].get("Second UV map?", False):
        bake_dmar_uv0(mic, out_dir, info)
    else:
        info["special"] = True                           # baked per mesh by bake_special.py
    with open(f"{out_dir}/manifest.json", "w") as fh:
        json.dump(info, fh, indent=1)
    return info


if __name__ == "__main__":
    names = sys.argv[1:]
    for n in names:
        i = bake(n)
        print(f"{n:24} {i['master']:20} res={i.get('res')} bc_orig={i.get('basecolor_original')} n_orig={i.get('normal_original')} special={i.get('special', False)}")
