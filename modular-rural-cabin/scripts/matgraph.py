import os
import sys
from uasset import Package
WORK = os.environ.get("KIT_WORK", "/home/user/work2")
ROOT = f"{WORK}/src/Modular Rural Cabin"
SKIP = {"MaterialExpressionEditorX", "MaterialExpressionEditorY", "MaterialExpressionGuid", "Material", "bCollapsed",
        "Desc", "SortPriority", "Group", "bRealtimePreview", "bNeedToUpdatePreview", "bShowOutputNameOnPin",
        "bHidePreviewWindow", "bShowOutputs", "Outputs", "bIsParameterExpression", "ExpressionGUID", "bCommentBubbleVisible",
        "SamplerSource", "ConstA", "ConstB"}

def dump(path):
    p = Package(path)
    nodes = {}
    for i, e in enumerate(p.exports):
        c = p.export_class(e)
        if c.startswith("MaterialExpression") or c == "Material":
            props, _ = p.export_props(e)
            nodes[i + 1] = (c, e["name"], props)
    def ref(v):
        if isinstance(v, dict) and "expr" in v:
            if not v["expr"]: return None
            n = nodes.get(v["expr"])
            s = f"{n[1]}" if n else f"#{v['expr']}"
            if v["output"]: s += f".out{v['output']}"
            if v["mask"]: s += "." + "".join(ch for ch, m in zip("RGBA", (v["mr"], v["mg"], v["mb"], v["ma"])) if m)
            return s
        if isinstance(v, tuple) and v and v[0] == "obj": return p.obj_path(v[1]) if v[1] else None
        if isinstance(v, list): return [ref(x) for x in v]
        if isinstance(v, dict): return {k: ref(x) for k, x in v.items() if k not in SKIP}
        return v
    for idx, (c, name, props) in nodes.items():
        if c == "Material":
            print("== MATERIAL", name)
            for k, v in props.items():
                if k in ("Expressions", "EditorComments", "ExpressionCollection", "CachedExpressionData", "ReferencedTextureGuids", "ThumbnailInfo", "StateId", "LightingGuid", "ParameterGroupData", "TextureStreamingData", "EditorX", "EditorY"): continue
                print("  ", k, "=", ref(v))
    for idx, (c, name, props) in nodes.items():
        if c == "Material": continue
        if c == "MaterialExpressionComment": continue
        print(name, {k: ref(v) for k, v in props.items() if k not in SKIP})

if __name__ == "__main__":
    dump(f"{ROOT}/Materials/Masters/{sys.argv[1]}.uasset")
