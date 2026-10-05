"""Replace zero-length TANGENT vectors (triangles with collapsed UVs, where MikkTSpace is undefined)
by any unit vector perpendicular to the normal, w=+1. Patched in place; nothing else in the GLB changes."""
import json, struct, sys
import numpy as np


def patch(path):
    data = bytearray(open(path, "rb").read())
    jlen = struct.unpack_from("<I", data, 12)[0]
    j = json.loads(data[20:20 + jlen])
    bin_off = 20 + jlen + 8
    fixed = 0
    for mesh in j["meshes"]:
        for prim in mesh["primitives"]:
            a = prim["attributes"]
            if "TANGENT" not in a:
                continue
            def view(acc_i, comps):
                acc = j["accessors"][acc_i]; bv = j["bufferViews"][acc["bufferView"]]
                assert acc["componentType"] == 5126 and bv.get("byteStride", comps * 4) == comps * 4
                off = bin_off + bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
                return off, acc["count"]
            toff, n = view(a["TANGENT"], 4); noff, _ = view(a["NORMAL"], 3)
            T = np.frombuffer(bytes(data[toff:toff + n * 16]), "<f4").reshape(n, 4).copy()
            N = np.frombuffer(bytes(data[noff:noff + n * 12]), "<f4").reshape(n, 3)
            bad = np.linalg.norm(T[:, :3], axis=1) < 1e-4
            if not bad.any():
                continue
            nb = N[bad]
            axis = np.where(np.abs(nb[:, :1]) < 0.9, np.array([[1.0, 0, 0]]), np.array([[0, 1.0, 0]]))
            t = np.cross(nb, axis); t /= np.linalg.norm(t, axis=1, keepdims=True)
            T[bad, :3] = t; T[bad, 3] = 1.0
            data[toff:toff + n * 16] = T.astype("<f4").tobytes()
            fixed += int(bad.sum())
    if fixed:
        open(path, "wb").write(bytes(data))
    return fixed


if __name__ == "__main__":
    for p in sys.argv[1:]:
        f = patch(p)
        if f:
            print(f"{p}: {f} tangents fixed")
