"""Audit: triangles per GLB vs UE source (minus UE-removed degenerates); every embedded image must be
byte-identical to a source texture (tex_src) or to a baked texture (build/mat)."""
import glob, hashlib, json, os, struct, sys
WORK = os.environ.get("KIT_WORK", "/home/user/work2")


def glb_json(path):
    d = open(path, "rb").read()
    jl = struct.unpack_from("<I", d, 12)[0]
    j = json.loads(d[20:20 + jl])
    return j, d, 20 + jl + 8


def main():
    known = {}
    for f in glob.glob(f"{WORK}/tex_src/**/*.png", recursive=True) + glob.glob(f"{WORK}/build/mat/**/*.png", recursive=True):
        known[hashlib.sha256(open(f, "rb").read()).hexdigest()] = f
    rep = json.load(open(f"{WORK}/build_report.json"))
    bad = 0; n_img = 0; orig = 0; tris_ok = 0
    out = {}
    for path in sorted(glob.glob(f"{WORK}/glb/**/*.glb", recursive=True)):
        rel = os.path.relpath(path, f"{WORK}/glb")
        j, d, b0 = glb_json(path)
        tris = 0
        for node in j["nodes"]:
            if "mesh" in node:
                for p in j["meshes"][node["mesh"]]["primitives"]:
                    tris += j["accessors"][p["indices"]]["count"] // 3
        imgs = []
        for im in j.get("images", []):
            bv = j["bufferViews"][im["bufferView"]]
            blob = d[b0 + bv.get("byteOffset", 0): b0 + bv.get("byteOffset", 0) + bv["byteLength"]]
            h = hashlib.sha256(blob).hexdigest()
            src = known.get(h)
            n_img += 1
            if src is None:
                bad += 1; print("UNKNOWN IMAGE", rel, im.get("name"))
            elif "/tex_src/" in src:
                orig += 1
            imgs.append(os.path.relpath(src, WORK) if src else None)
        key = os.path.splitext(os.path.basename(rel))[0]
        r = rep.get(key) if rel.split("/")[0] not in ("Assemblies", "Cabins") else None
        if r and "triangles" in r:
            ok = tris == r["triangles"] and r["triangles"] + r["degenerate_removed"] == r["source_triangles"]
            tris_ok += ok
            if not ok:
                print("TRIS MISMATCH", rel, tris, r["triangles"], r["source_triangles"])
        out[rel] = dict(triangles=tris, images=imgs, bytes=os.path.getsize(path),
                        materials=[m.get("name") for m in j.get("materials", [])],
                        alpha=[m.get("alphaMode", "OPAQUE") for m in j.get("materials", [])])
    json.dump(out, open(f"{WORK}/build/audit.json", "w"), indent=1)
    print(f"GLBs {len(out)}  single-mesh triangle checks OK {tris_ok}  images {n_img} (source PNG byte-identical {orig}, baked {n_img - orig - bad}, unknown {bad})")


if __name__ == "__main__":
    main()
