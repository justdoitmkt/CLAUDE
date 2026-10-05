"""Minimal reader for uncooked UE 4.22 packages (.uasset/.umap): summary, names, imports, exports,
tagged properties, bulk data."""
import struct, zlib, uuid

class Reader:
    def __init__(self, data, pkg=None, pos=0):
        self.d = data; self.p = pos; self.pkg = pkg
    def read(self, n):
        b = self.d[self.p:self.p + n]
        if len(b) != n: raise EOFError(f"read {n} at {self.p}")
        self.p += n; return b
    def u8(self):  return self.read(1)[0]
    def i16(self): return struct.unpack("<h", self.read(2))[0]
    def u16(self): return struct.unpack("<H", self.read(2))[0]
    def i32(self): return struct.unpack("<i", self.read(4))[0]
    def u32(self): return struct.unpack("<I", self.read(4))[0]
    def i64(self): return struct.unpack("<q", self.read(8))[0]
    def u64(self): return struct.unpack("<Q", self.read(8))[0]
    def f32(self): return struct.unpack("<f", self.read(4))[0]
    def guid(self): return self.read(16).hex()
    def bool32(self): v = self.u32(); assert v in (0, 1), v; return bool(v)
    def fstring(self):
        n = self.i32()
        if n == 0: return ""
        if n > 0: return self.read(n)[:-1].decode("latin-1")
        return self.read(-n * 2)[:-2].decode("utf-16-le")
    def fname(self):
        i, num = self.i32(), self.i32()
        s = self.pkg.names[i]
        return s if num == 0 else f"{s}_{num - 1}"
    def array(self, fn):
        return [fn() for _ in range(self.i32())]


class Package:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as fh:
            self.data = fh.read()
        r = Reader(self.data, self)
        s = self.summary = {}
        assert r.u32() == 0x9E2A83C1
        s["legacy"] = r.i32(); assert s["legacy"] == -7, s["legacy"]
        r.i32()                                   # LegacyUE3Version
        s["ue4"] = r.i32(); s["licensee"] = r.i32()
        self.custom = {}
        for _ in range(r.i32()):
            g = r.guid(); v = r.i32(); self.custom[g] = v
        s["total_header"] = r.i32(); s["folder"] = r.fstring(); s["flags"] = r.u32()
        s["name_count"], s["name_off"] = r.i32(), r.i32()
        if s["ue4"] >= 516 and not s["flags"] & 0x80000000:
            s["localization_id"] = r.fstring()
        s["gatherable_count"], s["gatherable_off"] = r.i32(), r.i32()
        s["export_count"], s["export_off"] = r.i32(), r.i32()
        s["import_count"], s["import_off"] = r.i32(), r.i32()
        s["depends_off"] = r.i32()
        s["soft_count"], s["soft_off"] = r.i32(), r.i32()
        s["searchable_off"] = r.i32(); s["thumb_off"] = r.i32()
        s["guid"] = r.guid()
        s["generations"] = r.array(lambda: (r.i32(), r.i32()))
        s["saved_by"] = (r.u16(), r.u16(), r.u16(), r.u32(), r.fstring())
        s["compat"] = (r.u16(), r.u16(), r.u16(), r.u32(), r.fstring())
        s["compression"] = r.u32(); assert r.i32() == 0       # compressed chunks
        s["source"] = r.u32()
        r.array(r.fstring)                         # AdditionalPackagesToCook
        s["asset_registry_off"] = r.i32()
        s["bulk_start"] = r.i64()
        s["world_tile_off"] = r.i32()
        r.array(r.i32)                             # ChunkIDs
        s["preload_count"], s["preload_off"] = r.i32(), r.i32()

        r.p = s["name_off"]; self.names = []
        for _ in range(s["name_count"]):
            self.names.append(r.fstring()); r.u16(); r.u16()

        r.p = s["import_off"]; self.imports = []
        for _ in range(s["import_count"]):
            self.imports.append(dict(class_package=r.fname(), class_name=r.fname(),
                                     outer=r.i32(), name=r.fname()))
        r.p = s["export_off"]; self.exports = []
        for _ in range(s["export_count"]):
            e = dict(class_index=r.i32(), super_index=r.i32(), template_index=r.i32(),
                     outer=r.i32(), name=r.fname(), flags=r.u32(),
                     size=r.i64(), offset=r.i64(), forced=r.bool32(), not_client=r.bool32(),
                     not_server=r.bool32(), pkg_guid=r.guid(), pkg_flags=r.u32(),
                     not_always_loaded_editor=r.bool32(), is_asset=r.bool32())
            r.read(20)                             # preload dependency indices
            self.exports.append(e)

    # ---- object references ----
    def obj_name(self, idx):
        if idx == 0: return None
        if idx < 0: return self.imports[-idx - 1]["name"]
        return self.exports[idx - 1]["name"]
    def obj_path(self, idx):
        parts = []
        while idx:
            if idx < 0:
                imp = self.imports[-idx - 1]; parts.append(imp["name"]); idx = imp["outer"]
            else:
                exp = self.exports[idx - 1]; parts.append(exp["name"]); idx = exp["outer"]
        return ".".join(reversed(parts))
    def obj_class(self, idx):
        if idx < 0: return self.imports[-idx - 1]["class_name"]
        if idx > 0: return self.obj_name(self.exports[idx - 1]["class_index"])
    def export_class(self, e):
        return self.obj_name(e["class_index"])

    def reader(self, e):
        return Reader(self.data, self, e["offset"])

    # ---- tagged properties ----
    def read_props(self, r, end=None):
        props = {}
        while True:
            name = r.fname()
            if name == "None": break
            typ = r.fname(); size = r.i32(); idx = r.i32()
            tag = dict(type=typ)
            if typ == "StructProperty": tag["struct"] = r.fname(); r.guid()
            elif typ == "BoolProperty": tag["bool"] = r.u8()
            elif typ in ("ByteProperty", "EnumProperty"): tag["enum"] = r.fname()
            elif typ in ("ArrayProperty", "SetProperty"): tag["inner"] = r.fname()
            elif typ == "MapProperty": tag["inner"] = r.fname(); tag["value"] = r.fname()
            if r.u8(): r.guid()
            start = r.p
            try:
                val = self.read_value(r, tag, size)
            except Exception as ex:
                val = ("<err>", repr(ex))
            r.p = start + size
            key = name if idx == 0 else f"{name}[{idx}]"
            props[key] = val
        return props

    def read_value(self, r, tag, size):
        t = tag["type"]
        if t == "BoolProperty": return bool(tag["bool"]) if "bool" in tag else bool(r.u8())
        if t == "IntProperty": return r.i32()
        if t == "UInt32Property": return r.u32()
        if t == "Int64Property": return r.i64()
        if t == "FloatProperty": return r.f32()
        if t == "NameProperty": return r.fname()
        if t == "StrProperty": return r.fstring()
        if t in ("ObjectProperty", "ClassProperty", "WeakObjectProperty", "LazyObjectProperty"):
            return ("obj", r.i32())
        if t == "SoftObjectProperty": return ("soft", r.fname(), r.fstring())
        if t in ("ByteProperty", "EnumProperty"):
            if size == 1: return r.u8()
            return r.fname()
        if t == "TextProperty": return ("text", r.read(size).hex())
        if t == "StructProperty": return self.read_struct(r, tag["struct"], size)
        if t == "ArrayProperty":
            n = r.i32(); inner = tag["inner"]
            if inner == "StructProperty":
                itag = dict(); iname = r.fname(); itype = r.fname(); isize = r.i32(); r.i32()
                sname = r.fname(); r.guid()
                if r.u8(): r.guid()
                return [self.read_struct(r, sname, isize // max(n, 1)) for _ in range(n)]
            if inner == "BoolProperty": return [bool(r.u8()) for _ in range(n)]
            if inner == "ByteProperty":
                if n and (size - 4) == n: return list(r.read(n))
                return [r.fname() for _ in range(n)]
            return [self.read_value(r, dict(type=inner), 0) for _ in range(n)]
        if t == "MapProperty":
            r.i32()                                  # keys to remove
            n = r.i32(); out = []
            for _ in range(n):
                k = self.read_value(r, dict(type=tag["inner"], struct="?"), 0) if tag["inner"] != "StructProperty" else ("rawkey",)
                v = self.read_value(r, dict(type=tag["value"], struct="?"), 0) if tag["value"] != "StructProperty" else self.read_props(r)
                out.append((k, v))
            return out
        return ("raw", t, r.read(size).hex()[:64])

    NATIVE = {
        "Vector": lambda r: (r.f32(), r.f32(), r.f32()),
        "Vector2D": lambda r: (r.f32(), r.f32()),
        "Vector4": lambda r: (r.f32(), r.f32(), r.f32(), r.f32()),
        "Rotator": lambda r: (r.f32(), r.f32(), r.f32()),
        "Quat": lambda r: (r.f32(), r.f32(), r.f32(), r.f32()),
        "LinearColor": lambda r: (r.f32(), r.f32(), r.f32(), r.f32()),
        "Color": lambda r: tuple(r.read(4)),          # B G R A
        "IntPoint": lambda r: (r.i32(), r.i32()),
        "Guid": lambda r: r.guid(),
        "Box": lambda r: ((r.f32(), r.f32(), r.f32()), (r.f32(), r.f32(), r.f32()), r.u8()),
        "Box2D": lambda r: ((r.f32(), r.f32()), (r.f32(), r.f32()), r.u8()),
        "SoftObjectPath": lambda r: (r.fname(), r.fstring()),
        "SoftClassPath": lambda r: (r.fname(), r.fstring()),
        "PerPlatformFloat": lambda r: (r.bool32(), r.f32()),
        "PerPlatformInt": lambda r: (r.bool32(), r.i32()),
    }

    def read_struct(self, r, sname, size):
        fn = self.NATIVE.get(sname)
        if fn: return fn(r)
        if sname in ("ExpressionInput", "ColorMaterialInput", "ScalarMaterialInput", "VectorMaterialInput",
                     "Vector2MaterialInput", "MaterialAttributesInput"):
            return self.read_expression_input(r, sname)
        return self.read_props(r)

    def read_expression_input(self, r, sname):
        d = dict(expr=r.i32(), output=r.i32(), input_name=r.fname(), mask=r.i32(),
                 mr=r.i32(), mg=r.i32(), mb=r.i32(), ma=r.i32())
        if sname == "ColorMaterialInput": d["use_const"] = r.bool32(); d["const"] = tuple(r.read(4))
        elif sname == "ScalarMaterialInput": d["use_const"] = r.bool32(); d["const"] = r.f32()
        elif sname == "VectorMaterialInput": d["use_const"] = r.bool32(); d["const"] = (r.f32(), r.f32(), r.f32())
        elif sname == "Vector2MaterialInput": d["use_const"] = r.bool32(); d["const"] = (r.f32(), r.f32())
        return d

    def export_props(self, e):
        r = self.reader(e)
        props = self.read_props(r)
        return props, r


def read_bulk(pkg, r):
    """FByteBulkData (UE4.22). Returns bytes (decompressed)."""
    flags = r.u32()
    count = r.i64() if flags & 0x2000 else r.i32()
    size_on_disk = r.i64() if flags & 0x2000 else r.i32()
    offset = r.i64()
    if flags & 0x0001:                                     # payload at end of file
        if not flags & 0x10000:                            # BULKDATA_NoOffsetFixUp
            offset += pkg.summary["bulk_start"]
        raw = pkg.data[offset:offset + size_on_disk]
    elif flags & 0x0800 or count == 0 or flags & 0x0020:  # separate file / unused / unused
        raw = pkg.data[r.p:r.p + size_on_disk]; r.p += size_on_disk
    else:
        raw = pkg.data[r.p:r.p + size_on_disk]; r.p += size_on_disk
    if flags & 0x0002:                                     # BULKDATA_SerializeCompressedZLIB
        raw = decompress_chunked(raw)
    return flags, count, raw


def decompress_chunked(raw):
    r = Reader(raw)
    tag = r.u64(); assert tag & 0xFFFFFFFF == 0x9E2A83C1, hex(tag)
    chunk = r.i64(); comp_total = r.i64(); uncomp_total = r.i64()
    n = (uncomp_total + chunk - 1) // chunk
    sizes = [(r.i64(), r.i64()) for _ in range(n)]
    out = bytearray()
    for cs, us in sizes:
        out += zlib.decompress(r.read(cs))
    assert len(out) == uncomp_total
    return bytes(out)
