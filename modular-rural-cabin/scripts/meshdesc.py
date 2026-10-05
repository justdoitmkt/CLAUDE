"""Decode a UE 4.22 FMeshDescription (FEditorObjectVersion 30, FReleaseObjectVersion 20)."""
import struct
import numpy as np
from uasset import Reader

TYPES = {0: ("f", 4), 1: ("f", 3), 2: ("f", 2), 3: ("f", 1), 4: ("i", 1), 5: ("?", 1), 6: ("name", 1)}


def _bitarray(r):
    n = r.i32()
    words = np.frombuffer(r.read(((n + 31) // 32) * 4), dtype="<u4")
    bits = np.unpackbits(words.view(np.uint8), bitorder="little")[:n]
    return np.nonzero(bits)[0]


def _attr_array(r, typ):
    kind, comps = TYPES[typ]
    if kind == "name":
        return [r.fstring() for _ in range(r.i32())]
    esize = r.i32(); n = r.i32()
    raw = r.read(esize * n)
    if kind == "?":
        return np.frombuffer(raw, dtype=np.uint8).astype(bool)
    a = np.frombuffer(raw, dtype="<f4" if kind == "f" else "<i4")
    return a.reshape(n, comps) if comps > 1 else a


def _default(r, typ):
    kind, comps = TYPES[typ]
    if kind == "name": return r.fstring()
    if kind == "?": return r.bool32()
    if kind == "i": return r.i32()
    return tuple(r.f32() for _ in range(comps))


def _attr_set(r):
    num = r.i32(); out = {}
    for _ in range(r.i32()):
        name = r.fstring().strip()
        typ = r.u32()
        n_el = r.i32()
        arrays = [_attr_array(r, typ) for _ in range(r.i32())]
        default = _default(r, typ)
        flags = r.u32()
        out[name] = dict(type=typ, num=n_el, arrays=arrays, default=default, flags=flags)
    return num, out


def decode(data):
    r = Reader(data)
    md = {}
    md["vertices"] = _bitarray(r)
    ids = _bitarray(r); md["vi_ids"] = ids
    md["vi_vertex"] = np.array([r.i32() for _ in ids], dtype=np.int64)
    ids = _bitarray(r); md["edge_ids"] = ids
    md["edges"] = np.array([(r.i32(), r.i32()) for _ in ids], dtype=np.int64).reshape(-1, 2)
    ids = _bitarray(r); md["poly_ids"] = ids
    polys, groups = [], []
    for _ in ids:
        polys.append([r.i32() for _ in range(r.i32())]); groups.append(r.i32())
    md["polys"] = polys; md["poly_group"] = np.array(groups, dtype=np.int64)
    md["group_ids"] = _bitarray(r)
    for key in ("vertex_attrs", "vi_attrs", "edge_attrs", "poly_attrs", "group_attrs"):
        md[key] = _attr_set(r)
    md["trailing"] = len(data) - r.p
    return md
