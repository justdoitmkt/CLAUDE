"""Extract Texture2D source images (lossless) from uncooked UE 4.22 packages."""
import io, os, glob, json, hashlib
import numpy as np
from PIL import Image
from uasset import Package, read_bulk
WORK = os.environ.get("KIT_WORK", "/home/user/work2")
ROOT = f"{WORK}/src/Modular Rural Cabin"
OUT = f"{WORK}/tex_src"


def load_texture(path):
    p = Package(path)
    e = [e for e in p.exports if p.export_class(e) == "Texture2D"][0]
    props, r = p.export_props(e)
    r.i32()                      # HasGuid
    r.u8(); r.u8()               # StripFlags
    flags, count, raw = read_bulk(p, r)
    src = props["Source"]
    info = dict(name=e["name"], props={k: v for k, v in props.items() if k not in ("AssetImportData", "Source", "LightingGuid")},
                width=src["SizeX"], height=src["SizeY"], format=src["Format"], png=src.get("bPNGCompressed", False),
                mips=src.get("NumMips"), slices=src.get("NumSlices"))
    if info["png"]:
        # UE compresses the BGRA8 source rows straight into the PNG: decoded "RGB" is really BGR
        im = Image.open(io.BytesIO(raw))
        if src["Format"] == "TSF_BGRA8":
            a = np.asarray(im.convert("RGBA"))[:, :, [2, 1, 0, 3]]
            im = Image.fromarray(np.ascontiguousarray(a), "RGBA")
            if a[:, :, 3].min() == 255:
                im = im.convert("RGB")                       # alpha unused: keep a lean RGB PNG
        b = io.BytesIO(); im.save(b, "PNG", compress_level=6); info["bytes"] = b.getvalue()
    else:
        w, h = src["SizeX"], src["SizeY"]
        fmt = src["Format"]
        if fmt == "TSF_BGRA8":
            a = np.frombuffer(raw[:w * h * 4], np.uint8).reshape(h, w, 4)[:, :, [2, 1, 0, 3]]
            im = Image.fromarray(a, "RGBA")
        elif fmt == "TSF_G8":
            im = Image.fromarray(np.frombuffer(raw[:w * h], np.uint8).reshape(h, w), "L")
        else:
            raise NotImplementedError(fmt)
        b = io.BytesIO(); im.save(b, "PNG"); info["bytes"] = b.getvalue()
    return info


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    meta = {}
    for f in sorted(glob.glob(ROOT + "/Textures/**/*.uasset", recursive=True)):
        t = load_texture(f)
        rel = os.path.relpath(f, ROOT)[:-7]
        out = os.path.join(OUT, rel + ".png")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(t["bytes"])
        im = Image.open(out)
        t["mode"] = im.mode; t["size"] = im.size
        t["sha256"] = hashlib.sha256(t["bytes"]).hexdigest()
        t["file"] = out
        del t["bytes"]
        meta["/Game/Modular_Rural_Cabin/" + rel] = t
    json.dump(meta, open(OUT + "/meta.json", "w"), indent=1, default=str)
    print(len(meta))
