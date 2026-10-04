"""Build glTF-ready textures from the original maps.

Originals are reused byte-for-byte whenever glTF can take them as they are. New images
are only written when glTF requires it, always lossless (PNG):
  * metallic-roughness packed into one image (G = roughness, B = metallic)
  * roof base color + cut-out mask merged into RGBA
  * DirectX normal maps converted to OpenGL (green inverted)
Writes TEX_OUT/<material>/manifest.json describing what is available."""
import json, os, shutil, sys
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kit_config import MATERIALS, TEX_SRC, TEX_OUT

Image.MAX_IMAGE_PIXELS = None


def src(cfg, key):
    f = cfg.get(key)
    if not f:
        return None
    p = os.path.join(TEX_SRC, cfg["folder"], f)
    return p if os.path.isfile(p) else False      # False = configured but missing


def ext(p):
    return os.path.splitext(p)[1].lower()


def main():
    report = {}
    for fbx_name, cfg in MATERIALS.items():
        name = cfg["name"]
        out = os.path.join(TEX_OUT, name)
        os.makedirs(out, exist_ok=True)
        info = {"fbx_material": fbx_name, "missing": [], "notes": []}

        # ---- base color (+ alpha) ----
        b, o = src(cfg, "base"), src(cfg, "opacity")
        if b is False:
            info["missing"].append(cfg["base"])
        elif b:
            im = Image.open(b)
            has_alpha = im.mode in ("RGBA", "LA") and np.asarray(im.getchannel("A")).min() < 250
            if has_alpha:
                dst = os.path.join(out, f"{name}_basecolor{ext(b)}")
                shutil.copyfile(b, dst)
                info["basecolor"], info["alpha"] = dst, "embedded"
            elif o:
                rgb = im.convert("RGB")
                mask = Image.open(o).convert("L")
                if mask.size != rgb.size:
                    mask = mask.resize(rgb.size, Image.LANCZOS)
                rgba = rgb.copy(); rgba.putalpha(mask)
                dst = os.path.join(out, f"{name}_basecolor.png")
                rgba.save(dst, optimize=False, compress_level=9)
                info["basecolor"], info["alpha"] = dst, "opacity map"
            else:
                dst = os.path.join(out, f"{name}_basecolor{ext(b)}")
                shutil.copyfile(b, dst)
                info["basecolor"] = dst
            info["size"] = list(im.size)
        if o is False:
            info["missing"].append(cfg["opacity"])

        # ---- normal ----
        n = src(cfg, "normal")
        if n is False:
            info["missing"].append(cfg["normal"])
        elif n:
            if cfg.get("normal_dx"):
                a = np.asarray(Image.open(n).convert("RGB")).copy()
                a[..., 1] = 255 - a[..., 1]
                dst = os.path.join(out, f"{name}_normal.png")
                Image.fromarray(a).save(dst, compress_level=9)
                info["notes"].append("normal map converted DirectX -> OpenGL")
            else:
                dst = os.path.join(out, f"{name}_normal{ext(n)}")
                shutil.copyfile(n, dst)
            info["normal"] = dst

        # ---- metallic / roughness ----
        r, m = src(cfg, "rough"), src(cfg, "metal")
        if r is False:
            info["missing"].append(cfg["rough"])
        if m is False:
            info["missing"].append(cfg["metal"])
        if r and m:
            rough = Image.open(r).convert("L")
            metal = Image.open(m).convert("L")
            if metal.size != rough.size:
                metal = metal.resize(rough.size, Image.LANCZOS)
            ones = Image.new("L", rough.size, 255)
            dst = os.path.join(out, f"{name}_metallic_roughness.png")
            Image.merge("RGB", (ones, rough, metal)).save(dst, compress_level=9)
            info["metallic_roughness"], info["metallic"] = dst, True
        elif r:
            im = Image.open(r)
            if im.mode == "L":
                # grayscale: G already holds roughness; metallicFactor will be 0, so B is ignored
                dst = os.path.join(out, f"{name}_roughness{ext(r)}")
                shutil.copyfile(r, dst)
            else:
                g = im.convert("L")
                dst = os.path.join(out, f"{name}_roughness.png")
                Image.merge("RGB", (Image.new("L", g.size, 255), g, Image.new("L", g.size, 0))).save(dst, compress_level=9)
            info["metallic_roughness"], info["metallic"] = dst, False

        with open(os.path.join(out, "manifest.json"), "w") as fh:
            json.dump(info, fh, indent=1)
        report[name] = info
        flag = "  MISSING: " + ", ".join(info["missing"]) if info["missing"] else ""
        print(f"{name:14} ok{flag}")
    with open(os.path.join(TEX_OUT, "report.json"), "w") as fh:
        json.dump(report, fh, indent=1)


if __name__ == "__main__":
    main()
