"""Read MaterialInstanceConstant parameters (with parent defaults) and Texture2D source data."""
import os, functools
from uasset import Package, read_bulk
WORK = os.environ.get("KIT_WORK", "/home/user/work2")
ROOT = f"{WORK}/src/Modular Rural Cabin"


def game_to_file(path):
    """/Game/Modular_Rural_Cabin/X/Y.Y -> file path"""
    pkg = path.split(".")[0]
    rel = pkg.replace("/Game/Modular_Rural_Cabin/", "")
    return os.path.join(ROOT, rel + ".uasset")


@functools.lru_cache(None)
def master_defaults(path):
    p = Package(game_to_file(path))
    out = dict(scalar={}, vector={}, texture={}, switch={}, props={})
    for e in p.exports:
        c = p.export_class(e)
        if c == "Material":
            props, _ = p.export_props(e)
            out["props"] = {k: v for k, v in props.items() if k in ("BlendMode", "TwoSided", "ShadingModel", "OpacityMaskClipValue")}
            continue
        if not c.startswith("MaterialExpression"): continue
        props, _ = p.export_props(e)
        name = props.get("ParameterName")
        if not name: continue
        if c == "MaterialExpressionScalarParameter": out["scalar"][name] = props.get("DefaultValue", 0.0)
        elif c == "MaterialExpressionVectorParameter": out["vector"][name] = props.get("DefaultValue", (0, 0, 0, 0))
        elif c.startswith("MaterialExpressionTextureSampleParameter"):
            t = props.get("Texture"); out["texture"][name] = p.obj_path(t[1]) if t and t[1] else None
        elif c == "MaterialExpressionStaticSwitchParameter": out["switch"][name] = bool(props.get("DefaultValue", False))
    return out


def load_mic(path):
    p = Package(path)
    e = [e for e in p.exports if p.export_class(e) in ("MaterialInstanceConstant", "Material")][0]
    if p.export_class(e) == "Material":
        d = master_defaults(p.obj_path(p.exports.index(e) + 1).replace("", "") if False else None) if False else None
    props, _ = p.export_props(e)
    parent = p.obj_path(props["Parent"][1])
    chain = [parent]
    # resolve parent chain (MIC of MIC)
    base_params = None
    if "/Materials/Masters/" in parent:
        d = master_defaults(parent)
        master = parent
        params = dict(scalar=dict(d["scalar"]), vector=dict(d["vector"]), texture=dict(d["texture"]), switch=dict(d["switch"]))
    else:
        sub = load_mic(game_to_file(parent))
        master = sub["master"]; params = {k: dict(v) for k, v in sub["params"].items()}; d = master_defaults(master)
    for t in props.get("ScalarParameterValues", []): params["scalar"][t["ParameterInfo"]["Name"]] = t["ParameterValue"]
    for t in props.get("VectorParameterValues", []): params["vector"][t["ParameterInfo"]["Name"]] = t["ParameterValue"]
    for t in props.get("TextureParameterValues", []):
        v = t["ParameterValue"]; params["texture"][t["ParameterInfo"]["Name"]] = p.obj_path(v[1]) if v and v[1] else None
    sp = props.get("StaticParameters") or {}
    for s in sp.get("StaticSwitchParameters", []):
        if s.get("bOverride", True):
            params["switch"][s["ParameterInfo"]["Name"]] = bool(s.get("Value", False))
    over = props.get("BasePropertyOverrides", {})
    return dict(name=e["name"], master=master, params=params, overrides=over, master_props=d["props"])
