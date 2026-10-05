"""Extract StaticMesh LOD0 source geometry + material slots from an uncooked UE 4.22 package."""
from uasset import Package, read_bulk
from meshdesc import decode


def load_static_mesh(path):
    p = Package(path)
    e = [e for e in p.exports if p.export_class(e) == "StaticMesh"][0]
    props, r = p.export_props(e)
    r.p += 4 + 2 + 4 + 4 + 4 + 8          # HasGuid, StripFlags, bCooked, BodySetup, NavCollision, (8 bytes)
    r.guid()                              # LightingGuid
    r.array(r.i32)                        # Sockets
    lods = []
    for sm in props["SourceModels"]:
        if not r.bool32():
            lods.append(None); continue
        flags, count, raw = read_bulk(p, r)
        r.guid(); r.bool32()
        lods.append(decode(raw) if count else None)
    mats = []
    for m in props.get("StaticMaterials", []):
        ref = m["MaterialInterface"][1]
        mats.append(dict(slot=m.get("MaterialSlotName"), imported=m.get("ImportedMaterialSlotName"),
                         material=p.obj_path(ref) if ref else None))
    sim = {k: v for k, v in props.get("SectionInfoMap", {}).get("Map", [])}
    return dict(name=e["name"], props=props, lods=lods, materials=mats, section_info=sim, package=p)
