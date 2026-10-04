"""Structural audit of the exported GLBs: textures (resolution, format, byte-identical
to the prepared/original file), materials, node hierarchy, geometry, placement."""
import glob, hashlib, io, json, os, struct, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kit_config import GLB_OUT, MATERIALS, TEX_OUT, TEX_SRC

Image.MAX_IMAGE_PIXELS = None
sha = lambda b: hashlib.sha256(b).hexdigest()

# hashes of every original and prepared texture, to prove what was embedded untouched
known = {}
for root, label in ((TEX_SRC, "original"), (TEX_OUT, "prepared")):
    for p in glob.glob(os.path.join(root, "*", "*")):
        if p.endswith((".png", ".jpg")):
            known.setdefault(sha(open(p, "rb").read()), (label, os.path.relpath(p, root)))

def read_glb(path):
    data = open(path, "rb").read()
    magic, ver, length = struct.unpack_from("<4sII", data, 0)
    assert magic == b"glTF" and ver == 2 and length == len(data)
    off, js, binc = 12, None, None
    while off < len(data):
        clen, ctype = struct.unpack_from("<II", data, off)
        chunk = data[off + 8: off + 8 + clen]
        if ctype == 0x4E4F534A: js = json.loads(chunk)
        elif ctype == 0x004E4942: binc = chunk
        off += 8 + clen
    return js, binc

def accessor(js, binc, idx):
    a = js["accessors"][idx]; bv = js["bufferViews"][a["bufferView"]]
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
    dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16}[a["componentType"]]
    start = bv.get("byteOffset", 0) + a.get("byteOffset", 0)
    return np.frombuffer(binc, dt, a["count"] * n, start).reshape(a["count"], n)

def world_mats(js):
    out = {}
    def trs(n):
        m = np.eye(4)
        if "matrix" in n: return np.array(n["matrix"]).reshape(4, 4).T
        t = n.get("translation", [0, 0, 0]); r = n.get("rotation", [0, 0, 0, 1]); s = n.get("scale", [1, 1, 1])
        x, y, z, w = r
        R = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
        m[:3, :3] = R * s; m[:3, 3] = t; return m
    def walk(i, parent):
        m = parent @ trs(js["nodes"][i]); out[i] = m
        for c in js["nodes"][i].get("children", []): walk(c, m)
    for i in js["scenes"][0]["nodes"]: walk(i, np.eye(4))
    return out

def main():
  for path in sorted(glob.glob(os.path.join(GLB_OUT, "*.glb"))):
    js, binc = read_glb(path)
    name = os.path.basename(path)
    W = world_mats(js)
    lo, hi, verts, tris, tangents = np.full(3, np.inf), np.full(3, -np.inf), 0, 0, True
    for ni, m in W.items():
        node = js["nodes"][ni]
        if "mesh" not in node: continue
        for prim in js["meshes"][node["mesh"]]["primitives"]:
            pos = accessor(js, binc, prim["attributes"]["POSITION"])
            w = pos @ m[:3, :3].T + m[:3, 3]
            lo, hi = np.minimum(lo, w.min(0)), np.maximum(hi, w.max(0))
            verts += len(pos); tris += js["accessors"][prim["indices"]]["count"] // 3
            tangents &= "TANGENT" in prim["attributes"]
    imgs = []
    for im in js["images"]:
        bv = js["bufferViews"][im["bufferView"]]
        b = binc[bv.get("byteOffset", 0): bv.get("byteOffset", 0) + bv["byteLength"]]
        pil = Image.open(io.BytesIO(b))
        src = known.get(sha(b), ("NEW", "-"))
        imgs.append(f'{im["name"]}: {pil.size[0]}x{pil.size[1]} {pil.mode} {im["mimeType"].split("/")[1]} [{src[0]}: {src[1]}]')
    mats = []
    for m in js["materials"]:
        pbr = m.get("pbrMetallicRoughness", {})
        mats.append(f'{m["name"]}: base={"tex" if "baseColorTexture" in pbr else "-"} '
                    f'MR={"tex" if "metallicRoughnessTexture" in pbr else "-"} metallicF={pbr.get("metallicFactor", 1)} '
                    f'normal={"tex" if "normalTexture" in m else "-"} alpha={m.get("alphaMode", "OPAQUE")}'
                    f'{"@" + str(m["alphaCutoff"]) if "alphaCutoff" in m else ""} doubleSided={m.get("doubleSided", False)}')
    nodes = [f'{n["name"]}{" t=" + str([round(v, 3) for v in n["translation"]]) if "translation" in n else ""}'
             f'{" children=" + str([js["nodes"][c]["name"] for c in n["children"]]) if "children" in n else ""}' for n in js["nodes"]]
    print(f"== {name}  {os.path.getsize(path)/1e6:.1f} MB  verts={verts} tris={tris} tangents={tangents}")
    print(f"   size (m, glTF X/Y-up/Z) = {np.round(hi - lo, 3).tolist()}   min Y = {lo[1]:.3f}   centre XZ = {np.round([(lo[0]+hi[0])/2, (lo[2]+hi[2])/2], 3).tolist()}")
    for x in nodes: print("   node  ", x)
    for x in mats: print("   mat   ", x)
    for x in imgs: print("   image ", x)


if __name__ == "__main__":
    main()
