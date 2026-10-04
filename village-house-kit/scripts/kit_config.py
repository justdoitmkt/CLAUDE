"""Shared configuration: FBX material -> texture set, and FBX objects -> exported models."""
import os

WORK = os.environ.get("KIT_WORK", "/home/user/work")
SRC_FBX = os.path.join(WORK, "src", "village house kit.fbx")
TEX_SRC = os.path.join(WORK, "textures")          # textures as downloaded from Drive
TEX_OUT = os.path.join(WORK, "build", "tex")      # glTF-ready textures
GLB_OUT = os.environ.get("KIT_GLB_OUT",
                         os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "glb"))

# FBX material name -> clean name + texture files (relative to TEX_SRC/<folder>).
# normal_dx: map authored in DirectX convention (green down); glTF needs OpenGL, so green is inverted.
#            Determined per map (see README): curl/integrability test, groove profiles and lit renders.
# opacity:   cut-out mask for thatch roofs (used only if the base color has no alpha of its own).
MATERIALS = {
    "house 1":       dict(name="house_1", folder="house 1", base="house 1_BaseColor.jpg", normal="house 1_Normal.jpg", rough="house 1_Roughness.jpg"),
    "roof 1":        dict(name="roof_1", folder="house 1", base="roof 1_BaseColor.png", normal="roof 1_Normal.png", rough="roof 1_Roughness.png", opacity="roof 1_opacity.jpg"),
    "house 2":       dict(name="house_2", folder="house 2", base="house 2_BaseColor.jpg", normal="house 2_Normal.jpg", rough="house 2_Roughness.jpg"),
    "house 3":       dict(name="house_3", folder="house 3", base="house 3_BaseColor.jpg", normal="house 3_Normal.jpg", rough="house 3_Roughness.jpg"),
    "roof 3":        dict(name="roof_3", folder="house 3", base="roof 3_BaseColor.png", normal="roof 3_Normal.png", rough="roof 3_Roughness.png", opacity="roof 3_opacity.jpg"),
    "house 4":       dict(name="house_4", folder="house 4", base="house 4_BaseColor.jpg", normal="house 4_Normal.jpg", rough="house 4_Roughness.jpg"),
    "roof 4":        dict(name="roof_4", folder="house 4", base="roof 4_BaseColor.jpg", normal="roof 4_Normal.jpg", rough="roof 4_Roughness.jpg"),
    "house 5":       dict(name="house_5", folder="house 5", base="house 5_BaseColor.jpg", normal="house 5_Normal.jpg", rough="house 5_Roughness.jpg", metal="house 5_Metallic.jpg"),
    "roof 5":        dict(name="roof_5", folder="house 5", base="roof 5_BaseColor.png", normal="roof 5_Normal.jpg", rough="roof 5_Roughness.jpg", opacity="roof 5_opacity.jpg"),
    "gate mat":      dict(name="gate", folder="gate", base="gate_BaseColor.jpg", normal="gate_Normal.jpg", rough="gate_Roughness.jpg", metal="gate_Metallic.jpg"),
    "Material.002":  dict(name="fortification", folder="fortification", base="fortification_BaseColor.jpg", normal="fortification_Normal.jpg", rough="fortification_Roughness.jpg"),
    "Material.001":  dict(name="stilt", folder="stilt", base="stilt_BaseColor.jpg", normal="stilt_Normal.jpg", rough="stilt_Roughness.jpg"),
    "structure mat": dict(name="structure", folder="structure", base="structure_BaseColor.jpg", normal="structure_Normal.jpg", rough="structure_Roughness.jpg"),
    "well mat":      dict(name="well", folder="well", base="DefaultMaterial_BaseColor.jpg", normal="DefaultMaterial_Normal.jpg", rough="DefaultMaterial_Roughness.jpg", metal="DefaultMaterial_Metallic.jpg"),
    "cart mat":      dict(name="cart", folder="cart", base="cart_BaseColor.jpg", normal="cart_Normal.jpg", rough="cart_Roughness.jpg", metal="cart_Metallic.jpg"),
    "barrel mat":    dict(name="barrel", folder="barrel", base="barrel_BaseColor.png", normal="barrel_Normal.png", rough="barrel_Roughness.png", metal="barrel_Metallic.png", normal_dx=True),
    "crate mat":     dict(name="crate", folder="crate", base="crate_BaseColor.png", normal="crate_Normal.png", rough="crate_Roughness.png"),
    "bag":           dict(name="bag", folder="bag", base="bag_BaseColor.png", normal="bag_Normal.png", rough="bag_Roughness.png", normal_dx=True),
    "bucket 2":      dict(name="bucket", folder="bucket 2", base="DefaultMaterial_BaseColor.png", normal="DefaultMaterial_Normal.png", rough="DefaultMaterial_Roughness.png", metal="DefaultMaterial_Metallic.png", normal_dx=True),
    "table mat":     dict(name="table", folder="table", base="table_BaseColor.png", normal="table_Normal.png", rough="table_Roughness.png", metal="table_Metallic.png", normal_dx=True),
    "trunk mat":     dict(name="trunk", folder="trunk", base="trunk_BaseColor.png", normal="trunk_Normal.png", rough="trunk_Roughness.png"),
    "Material":      dict(name="trunk_2", folder="trunk 2", base="trunk 2_BaseColor.jpg", normal="trunk 2_Normal.jpg", rough="trunk 2_Roughness.jpg"),
    "Material.003":  dict(name="axe", folder="axe", base="axe_BaseColor.jpg", normal="axe_Normal.jpg", rough="axe_Roughness.jpg", metal="axe_Metallic.jpg"),
    "ladders mat":   dict(name="ladder", folder="ladders", base="ladders_BaseColor.png", normal="ladders_Normal.png", rough="ladders_Roughness.png", normal_dx=True),
    "fence mat":     dict(name="fence", folder="fence", base="fence mat_BaseColor.jpg", normal="fence mat_Normal.jpg", rough="fence mat_Roughness.jpg"),
}

# Exported model -> FBX objects. The first object is the root; the rest become child nodes
# (doors keep their own pivot at the hinge so they can be animated).
GROUPS = {
    "house_1":       [("house 1", "house_1"), ("door 1.001", "house_1_door")],
    "house_2":       [("house 2", "house_2"), ("door 2.001", "house_2_door")],
    "house_3":       [("house 3", "house_3"), ("door 3", "house_3_door")],
    "house_4":       [("house 4", "house_4"), ("door 4", "house_4_door")],
    "house_5":       [("house 5", "house_5"), ("door 5 a", "house_5_door"), ("door 5 b", "house_5_loft_door")],
    "gate":          [("gate", "gate"), ("door 1", "gate_door_right"), ("door 2", "gate_door_left")],
    "wooden_wall_1": [("wooden wall ", "wooden_wall_1")],
    "wooden_wall_2": [("wooden wall .001", "wooden_wall_2")],
    "fortification": [("fortification", "fortification")],
    "stilt":         [("stilt", "stilt")],
    "structure":     [("structure", "structure")],
    "well":          [("well", "well")],
    "cart":          [("cart", "cart")],
    "barrel":        [("barrel", "barrel")],
    "crate":         [("crate", "crate")],
    "bag_1":         [("bag", "bag_1")],
    "bag_2":         [("bag 2", "bag_2")],
    "bucket":        [("bucket 2", "bucket")],
    "table":         [("table", "table")],
    "trunk":         [("trunk", "trunk")],
    "trunk_2":       [("trunk 2", "trunk_2")],
    "axe":           [("axe", "axe")],
    "ladder_1":      [("ladder", "ladder_1")],
    "ladder_2":      [("ladder 2", "ladder_2")],
    "fence_1":       [("fence 1", "fence_1")],
    "fence_2":       [("fence 2", "fence_2")],
}
