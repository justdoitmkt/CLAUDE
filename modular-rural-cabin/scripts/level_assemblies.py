"""Read a UE4.22 level (.umap) and rebuild its actor attachment trees.

For every StaticMeshComponent: mesh, material overrides and world transform, merging the level's
per-instance deltas with the Blueprint component templates (archetypes). Actors attached to each other
form trees; each tree of modular pieces is one assembled cabin."""
import glob, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uasset import Package
from ue_mat import ROOT

TRANSFORM_KEYS = ("RelativeLocation", "RelativeRotation", "RelativeScale3D")


def ue_matrix(loc, rot, scale):
    """UE relative transform -> 4x4 acting on UE column vectors (cm)."""
    import build_glb as BG
    M = np.eye(4)
    M[:3, :3] = BG.ue_rotator_matrix(rot) @ np.diag(scale if scale else (1.0, 1.0, 1.0))
    M[:3, 3] = loc if loc else (0.0, 0.0, 0.0)
    return M


_bp_cache = {}


def bp_templates(class_name):
    """Component templates of a Blueprint class ('Wall_4m_C') -> {component name: props}."""
    if class_name in _bp_cache:
        return _bp_cache[class_name]
    name = class_name[:-2]
    files = [f for f in glob.glob(ROOT + "/**/Blueprints/*.uasset", recursive=True) if os.path.basename(f) == name + ".uasset"]
    out = {}
    if files:
        p = Package(files[0])
        for e in p.exports:
            if e["name"].endswith("_GEN_VARIABLE"):
                props, _ = p.export_props(e)
                sm = props.get("StaticMesh")
                props["_mesh"] = p.obj_path(sm[1]).split(".")[-1] if sm and sm[1] else None
                props["_materials"] = [p.obj_path(m[1]).split(".")[-1] if m and m[1] else None for m in props.get("OverrideMaterials", [])]
                out[e["name"][:-len("_GEN_VARIABLE")]] = props
    _bp_cache[class_name] = out
    return out


def read_level(path):
    p = Package(path)
    comps = {}
    for i, e in enumerate(p.exports):
        cls = p.export_class(e)
        if cls not in ("SceneComponent", "StaticMeshComponent"):
            continue
        outer = e["outer"]
        if outer <= 0:
            continue
        actor = p.exports[outer - 1]
        acls = p.export_class(actor)
        if not (acls.endswith("_C") or acls == "StaticMeshActor"):
            continue
        props, _ = p.export_props(e)
        tmpl = bp_templates(acls).get(e["name"], {}) if acls.endswith("_C") else {}
        merged = {k: props.get(k, tmpl.get(k)) for k in TRANSFORM_KEYS}
        sm = props.get("StaticMesh")
        mesh = (p.obj_path(sm[1]).split(".")[-1] if sm and sm[1] else None) if "StaticMesh" in props else tmpl.get("_mesh")
        if "OverrideMaterials" in props:
            mats = [p.obj_path(m[1]).split(".")[-1] if m and m[1] else None for m in props["OverrideMaterials"]]
        else:
            mats = tmpl.get("_materials", [])
        ap = props.get("AttachParent")
        comps[i + 1] = dict(name=e["name"], cls=cls, actor=outer, actor_label=None, actor_class=acls,
                            local=ue_matrix(*(merged[k] for k in TRANSFORM_KEYS)), parent=ap[1] if ap and ap[1] > 0 else None,
                            mesh=mesh if cls == "StaticMeshComponent" else None, materials=mats,
                            hidden=bool(props.get("bHiddenInGame", False) or props.get("bVisible") is False))
    actors = {}
    for i, e in enumerate(p.exports):
        if i + 1 in {c["actor"] for c in comps.values()}:
            props, _ = p.export_props(e)
            actors[i + 1] = dict(name=e["name"], label=props.get("ActorLabel", e["name"]), cls=p.export_class(e),
                                 root=props.get("RootComponent", (None, None))[1], folder=props.get("FolderPath"))
    for c in comps.values():
        c["actor_label"] = actors[c["actor"]]["label"]

    def world(cid, depth=0):
        c = comps[cid]
        if c["parent"] in comps and depth < 64:
            return world(c["parent"], depth + 1) @ c["local"]
        return c["local"]

    def top(cid, depth=0):
        c = comps[cid]
        return top(c["parent"], depth + 1) if c["parent"] in comps and depth < 64 else c["actor"]

    for cid, c in comps.items():
        c["world"] = world(cid)
        c["tree"] = top(cid)
    return comps, actors


def cabins(path, min_pieces=8):
    """Trees with modular cabin pieces -> {label: dict(root_world, parts=[(name, mesh, materials, world)])}"""
    comps, actors = read_level(path)
    trees = {}
    for cid, c in comps.items():
        if c["mesh"] and not c["hidden"]:
            trees.setdefault(c["tree"], []).append(c)
    out = {}
    for tid, parts in trees.items():
        modular = [c for c in parts if c["actor_class"].endswith("_C")]
        if len(parts) < min_pieces or not modular:
            continue
        root_actor = actors[tid]
        root_world = comps[root_actor["root"]]["world"] if root_actor["root"] in comps else np.eye(4)
        out[root_actor["label"]] = dict(root_world=root_world, parts=[(f"{c['actor_label']}.{c['name']}", c["mesh"], c["materials"], c["world"]) for c in parts])
    return out


if __name__ == "__main__":
    lv = sys.argv[1] if len(sys.argv) > 1 else ROOT + "/Maps/Modular_Cabins_Showcase.umap"
    cb = cabins(lv)
    for k, v in cb.items():
        meshes = sorted({m for _, m, _, _ in v["parts"]})
        print(f"{k:32} parts={len(v['parts']):4} distinct meshes={len(meshes)}  root at {np.round(v['root_world'][:3, 3] / 100, 2)}")
