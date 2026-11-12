"""importar_blackisle.py — importa el kit BLACKISLE (7 edificios) en Unreal Engine 5 desde el editor (Python).

Requisitos: UE 5.1 o posterior, plugin "Python Editor Script Plugin" activo e importador glTF (Interchange, activo por defecto
en 5.1+). Todo lo que hace este script está descrito en manifiesto.json: si alguna llamada falla en tu versión del motor,
el manifiesto es la especificación y el script es una forma de cumplirla (ver LEEME_UE5.md).

Uso (consola Python del editor: Output Log -> "Python"):
    import sys; sys.path.append(r"RUTA/A/kit_ue5")          # la carpeta que contiene este archivo
    import importar_blackisle as ib
    ib.importar_todo()                                      # texturas + materiales + mallas de los 11 modelos (unos minutos)
    ib.verificar()                                          # medidas, ranuras de material y ejes, modelo por modelo
    ib.colocar("APT_A_5p", unreal.Vector(0, 0, 0), yaw=0)   # pone un edificio (5 actores enganchados al de Estructura)
    ib.reemplazar("Edificio_Placeholder_01", "APT_A_5p")    # lo pone donde está un actor existente y oculta ese actor
    ib.focos(actor_estructura)                              # (opcional) luces puntuales en los focos colgantes del interior
Contenido en /Game/BlackIsle: Texturas/Comun, Texturas/<ID>, Materiales/Maestros, Materiales/Instancias, Modelos/<ID>.
"""
import json
import os

import unreal

KIT = os.path.dirname(os.path.abspath(__file__))
ROOT = "/Game/BlackIsle"
MAN = json.load(open(os.path.join(KIT, "manifiesto.json"), encoding="utf-8"))

AT = unreal.AssetToolsHelpers.get_asset_tools()
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
_tex = {}          # nombre -> Texture2D
_mi = {}           # nombre de ranura del manifiesto -> MaterialInstanceConstant
_ejes = None       # conversión de ejes Blender -> Unreal (se mide con SM_BLK_Ejes)


def log(*a):
    unreal.log("[BLACKISLE] " + " ".join(str(x) for x in a))


def warn(*a):
    unreal.log_warning("[BLACKISLE] " + " ".join(str(x) for x in a))


# ----------------------------------------------------------------------------------------------------------- importación
def _import(files, dest):
    tasks = []
    for f in files:
        t = unreal.AssetImportTask()
        t.set_editor_property("filename", f)
        t.set_editor_property("destination_path", dest)
        t.set_editor_property("automated", True)
        t.set_editor_property("replace_existing", True)
        t.set_editor_property("save", True)
        tasks.append(t)
    AT.import_asset_tasks(tasks)
    out = []
    for t in tasks:
        paths = list(t.get_editor_property("imported_object_paths") or [])
        if not paths:
            warn("no se importó", t.get_editor_property("filename"))
        out.append(paths)
    return out


def _texture(path_png, dest, kind):
    """kind: BC (color sRGB), N (normal DirectX), ORM / MASK (lineal)."""
    name = os.path.splitext(os.path.basename(path_png))[0]
    asset = f"{dest}/{name}"
    if EAL.does_asset_exist(asset):
        tex = EAL.load_asset(asset)
    else:
        _import([path_png], dest)
        tex = EAL.load_asset(asset)
    if tex is None:
        raise RuntimeError(f"textura no importada: {path_png}")
    if kind == "N":
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
        tex.set_editor_property("srgb", False)
        tex.set_editor_property("flip_green_channel", False)          # el kit ya viene en convención DirectX
    elif kind in ("ORM", "MASK"):
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
        tex.set_editor_property("srgb", False)
    EAL.save_loaded_asset(tex)
    _tex[name] = tex
    return tex


def presentes():
    """Modelos del manifiesto cuya carpeta está en el disco (se pueden descomprimir solo algunos ZIP de modelo)."""
    out = [b for b in MAN["modelos"] if os.path.isdir(os.path.join(KIT, "modelos", b))]
    falta = [b for b in MAN["modelos"] if b not in out]
    if falta:
        warn("modelos sin carpeta (no se importan):", falta)
    return out


def importar_texturas():
    d = os.path.join(KIT, "comun", "texturas")
    for f in sorted(os.listdir(d)):
        if f.endswith(".png"):
            kind = "N" if f.endswith("_N.png") else ("ORM" if f.endswith("_ORM.png") else ("MASK" if "suciedad" in f else "BC"))
            _texture(os.path.join(d, f), f"{ROOT}/Texturas/Comun", kind)
    for bid in presentes():
        d = os.path.join(KIT, "modelos", bid, "texturas")
        for f in sorted(os.listdir(d)):
            kind = "N" if "_N." in f else ("ORM" if "_ORM." in f else "BC")
            _texture(os.path.join(d, f), f"{ROOT}/Texturas/{bid}", kind)
    log("texturas:", len(_tex))


# ----------------------------------------------------------------------------------------------------------- materiales
def _new_material(name):
    folder = f"{ROOT}/Materiales/Maestros"
    path = f"{folder}/{name}"
    if EAL.does_asset_exist(path):
        return EAL.load_asset(path), False
    return AT.create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew()), True


def _e(m, cls, x, y):
    return MEL.create_material_expression(m, cls, x, y)


def _scalar(m, name, val, x, y):
    e = _e(m, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", float(val))
    return e


def _vector(m, name, rgb, x, y):
    e = _e(m, unreal.MaterialExpressionVectorParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", unreal.LinearColor(rgb[0], rgb[1], rgb[2], 1.0))
    return e


def _texp(m, name, tex, sampler, x, y, uv=None):
    e = _e(m, unreal.MaterialExpressionTextureSampleParameter2D, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("texture", tex)
    e.set_editor_property("sampler_type", sampler)
    if uv is not None:
        MEL.connect_material_expressions(uv, "", e, "UVs")
    return e


def _mul(m, a, b, x, y, ao="", bo=""):
    e = _e(m, unreal.MaterialExpressionMultiply, x, y)
    MEL.connect_material_expressions(a, ao, e, "A")
    MEL.connect_material_expressions(b, bo, e, "B")
    return e


def _lerp1(m, b, alpha, x, y, bo=""):
    """lerp(1, b, alpha)"""
    e = _e(m, unreal.MaterialExpressionLinearInterpolate, x, y)
    e.set_editor_property("const_a", 1.0)
    MEL.connect_material_expressions(b, bo, e, "B")
    MEL.connect_material_expressions(alpha, "", e, "Alpha")
    return e


def _usage(m):
    for u in ("MATUSAGE_NANITE", "MATUSAGE_STATIC_LIGHTING"):
        try:
            MEL.set_material_usage(m, getattr(unreal.MaterialUsage, u))
        except Exception:  # noqa: BLE001 — según versión
            pass


def maestros():
    """Cuatro materiales maestros con parámetros (los nombres de parámetro son los del manifiesto)."""
    P = unreal.MaterialProperty
    S = unreal.MaterialSamplerType
    t_bc = _tex["T_BLK_concrete_BC"]
    t_n = _tex["T_BLK_concrete_N"]
    t_orm = _tex["T_BLK_concrete_ORM"]
    out = {}
    # --- M_BLK_Atlas: muros exteriores horneados (color, normal y ORM únicos del modelo)
    m, new = _new_material("M_BLK_Atlas")
    if new:
        bc = _texp(m, "BC", t_bc, S.SAMPLERTYPE_COLOR, -700, -200)
        n = _texp(m, "N", t_n, S.SAMPLERTYPE_NORMAL, -700, 100)
        orm = _texp(m, "ORM", t_orm, S.SAMPLERTYPE_MASKS, -700, 400)
        aof = _scalar(m, "AOFuerza", 1.0, -700, 700)
        MEL.connect_material_property(bc, "RGB", P.MP_BASE_COLOR)
        MEL.connect_material_property(n, "RGB", P.MP_NORMAL)
        MEL.connect_material_property(_lerp1(m, orm, aof, -300, 400, bo="R"), "", P.MP_AMBIENT_OCCLUSION)
        MEL.connect_material_property(orm, "G", P.MP_ROUGHNESS)
        MEL.connect_material_property(orm, "B", P.MP_METALLIC)
        _usage(m)
        MEL.recompile_material(m)
    out["M_BLK_Atlas"] = m
    # --- M_BLK_Repetible: textura a escala real (UV0 = caja de 2 m) x tinte x color por vértice (AO) + variación grande
    m, new = _new_material("M_BLK_Repetible")
    if new:
        tc = _e(m, unreal.MaterialExpressionTextureCoordinate, -1500, 0)
        uvs = _mul(m, tc, _scalar(m, "UVEscala", 1.0, -1500, 150), -1300, 0)
        macro_uv = _mul(m, uvs, _scalar(m, "MacroEscala", 0.21, -1300, 150), -1100, 300)
        bc = _texp(m, "BC", t_bc, S.SAMPLERTYPE_COLOR, -1000, -300, uv=uvs)
        bcm = _texp(m, "BC", t_bc, S.SAMPLERTYPE_COLOR, -900, 300, uv=macro_uv)
        lum_w = _e(m, unreal.MaterialExpressionConstant3Vector, -900, 550)
        lum_w.set_editor_property("constant", unreal.LinearColor(0.2126, 0.7152, 0.0722, 1.0))
        dot = _e(m, unreal.MaterialExpressionDotProduct, -700, 400)
        MEL.connect_material_expressions(bcm, "RGB", dot, "A")
        MEL.connect_material_expressions(lum_w, "", dot, "B")
        div = _e(m, unreal.MaterialExpressionDivide, -550, 400)
        MEL.connect_material_expressions(dot, "", div, "A")
        MEL.connect_material_expressions(_scalar(m, "LumaMedia", 0.25, -700, 550), "", div, "B")
        macro = _lerp1(m, div, _scalar(m, "MacroFuerza", 0.3, -550, 550), -400, 400)
        vc = _e(m, unreal.MaterialExpressionVertexColor, -700, -500)
        vcmix = _lerp1(m, vc, _scalar(m, "PesoVC", 0.75, -700, -350), -500, -450)
        col = _mul(m, _mul(m, bc, _vector(m, "Tinte", (1, 1, 1), -800, -150), -600, -250, ao="RGB"), vcmix, -400, -300)
        col = _mul(m, col, macro, -250, -200)
        MEL.connect_material_property(col, "", P.MP_BASE_COLOR)
        n = _texp(m, "N", t_n, S.SAMPLERTYPE_NORMAL, -1000, 700, uv=uvs)
        flat = _e(m, unreal.MaterialExpressionConstant3Vector, -800, 900)
        flat.set_editor_property("constant", unreal.LinearColor(0, 0, 1, 1))
        nl = _e(m, unreal.MaterialExpressionLinearInterpolate, -500, 750)
        MEL.connect_material_expressions(flat, "", nl, "A")
        MEL.connect_material_expressions(n, "RGB", nl, "B")
        MEL.connect_material_expressions(_scalar(m, "NormalFuerza", 1.0, -800, 1000), "", nl, "Alpha")
        MEL.connect_material_property(nl, "", P.MP_NORMAL)
        orm = _texp(m, "ORM", t_orm, S.SAMPLERTYPE_MASKS, -1000, 1100, uv=uvs)
        MEL.connect_material_property(_lerp1(m, orm, _scalar(m, "AOFuerza", 1.0, -800, 1300), -500, 1150, bo="R"), "",
                                      P.MP_AMBIENT_OCCLUSION)
        MEL.connect_material_property(orm, "G", P.MP_ROUGHNESS)
        MEL.connect_material_property(orm, "B", P.MP_METALLIC)
        _usage(m)
        MEL.recompile_material(m)
    out["M_BLK_Repetible"] = m
    # --- M_BLK_Color: color liso x color por vértice (AO; en la tela, el color de cada pieza)
    m, new = _new_material("M_BLK_Color")
    if new:
        vc = _e(m, unreal.MaterialExpressionVertexColor, -700, 0)
        vcmix = _lerp1(m, vc, _scalar(m, "PesoVC", 0.75, -700, 150), -500, 50)
        MEL.connect_material_property(_mul(m, _vector(m, "Color", (0.5, 0.5, 0.5), -700, -200), vcmix, -300, -100), "",
                                      P.MP_BASE_COLOR)
        MEL.connect_material_property(_scalar(m, "Rugosidad", 0.8, -500, 300), "", P.MP_ROUGHNESS)
        MEL.connect_material_property(_scalar(m, "Metal", 0.0, -500, 400), "", P.MP_METALLIC)
        _usage(m)
        MEL.recompile_material(m)
    out["M_BLK_Color"] = m
    # --- M_BLK_Vidrio: translúcido con iluminación por píxel; la suciedad sube opacidad y rugosidad
    m, new = _new_material("M_BLK_Vidrio")
    if new:
        m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
        try:
            m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
        except Exception:  # noqa: BLE001
            warn("no se pudo fijar Surface ForwardShading en M_BLK_Vidrio: ponlo a mano (Details > Translucency)")
        tc = _e(m, unreal.MaterialExpressionTextureCoordinate, -1100, 300)
        uvs = _mul(m, tc, _scalar(m, "EscalaSuciedad", 1.6, -1100, 450), -900, 300)
        g = _texp(m, "Suciedad", _tex["T_BLK_vidrio_suciedad"], S.SAMPLERTYPE_MASKS, -700, 300, uv=uvs)
        gs = _mul(m, g, _scalar(m, "FuerzaSuciedad", 1.0, -700, 500), -500, 350, ao="R")
        sat = _e(m, unreal.MaterialExpressionSaturate, -350, 350)
        MEL.connect_material_expressions(gs, "", sat, "")
        op = _e(m, unreal.MaterialExpressionLinearInterpolate, -150, 300)
        MEL.connect_material_expressions(_scalar(m, "OpacidadLimpia", 0.16, -350, 150), "", op, "A")
        MEL.connect_material_expressions(_scalar(m, "OpacidadSucia", 0.55, -350, 220), "", op, "B")
        MEL.connect_material_expressions(sat, "", op, "Alpha")
        rg = _e(m, unreal.MaterialExpressionLinearInterpolate, -150, 500)
        MEL.connect_material_expressions(_scalar(m, "RugosidadLimpia", 0.03, -350, 500), "", rg, "A")
        MEL.connect_material_expressions(_scalar(m, "RugosidadSucia", 0.38, -350, 570), "", rg, "B")
        MEL.connect_material_expressions(sat, "", rg, "Alpha")
        MEL.connect_material_property(_vector(m, "Color", (0.035, 0.042, 0.042), -350, -100), "", P.MP_BASE_COLOR)
        MEL.connect_material_property(op, "", P.MP_OPACITY)
        MEL.connect_material_property(rg, "", P.MP_ROUGHNESS)
        MEL.connect_material_property(_scalar(m, "Especular", 0.5, -350, 700), "", P.MP_SPECULAR)
        MEL.recompile_material(m)
    out["M_BLK_Vidrio"] = m
    return out


def _mi_set(name, parent, spec):
    folder = f"{ROOT}/Materiales/Instancias"
    path = f"{folder}/MI_{name}"
    mi = EAL.load_asset(path) if EAL.does_asset_exist(path) else \
        AT.create_asset(f"MI_{name}", folder, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    MEL.set_material_instance_parent(mi, parent)
    for k, v in spec.items():
        if k in ("maestro", "nota", "dos_caras", "texturas"):
            continue
        if isinstance(v, list):
            MEL.set_material_instance_vector_parameter_value(mi, k, unreal.LinearColor(v[0], v[1], v[2], 1.0))
        elif isinstance(v, (int, float)):
            MEL.set_material_instance_scalar_parameter_value(mi, k, float(v))
    for k, tname in spec.get("texturas", {}).items():
        MEL.set_material_instance_texture_parameter_value(mi, k, _tex[tname])
    if spec.get("dos_caras"):
        ov = mi.get_editor_property("base_property_overrides")
        ov.set_editor_property("override_two_sided", True)
        ov.set_editor_property("two_sided", True)
        mi.set_editor_property("base_property_overrides", ov)
    MEL.update_material_instance(mi)
    EAL.save_loaded_asset(mi)
    _mi[name] = mi
    return mi


def materiales():
    M = maestros()
    for name, spec in MAN["materiales"].items():
        _mi_set(name, M[spec["maestro"]], spec)
    for bid in presentes():
        for name, spec in MAN["modelos"][bid]["materiales_atlas"].items():
            _mi_set(name, M[spec["maestro"]], spec)
    log("instancias de material:", len(_mi))


# ----------------------------------------------------------------------------------------------------------- mallas
def _slot_material(slot):
    s = str(slot)
    if s in _mi:
        return _mi[s]
    best = max((k for k in _mi if k in s), key=len, default=None)       # el importador puede añadir prefijos o sufijos
    return _mi.get(best)


def _nanite(sm, on):
    try:
        sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
        ns = sm.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", on)
        sub.set_nanite_settings(sm, ns, apply_changes=True)
    except Exception:  # noqa: BLE001
        ns = sm.get_editor_property("nanite_settings")
        ns.set_editor_property("enabled", on)
        sm.set_editor_property("nanite_settings", ns)


def _collision(sm, mode):
    bs = sm.get_editor_property("body_setup")
    if bs is None:
        return
    if mode == "compleja":
        bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    else:
        bs.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX)
        try:
            unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem).remove_collisions(sm)
        except Exception:  # noqa: BLE001
            pass


def _limpiar_importados(folder, keep):
    """Borra los materiales y texturas que el importador glTF crea por su cuenta (se usan las instancias del kit)."""
    for p in EAL.list_assets(folder, recursive=True, include_folder=False):
        if p.split(".")[0] in keep:
            continue
        a = EAL.load_asset(p)
        if isinstance(a, (unreal.MaterialInterface, unreal.Texture)):
            EAL.delete_asset(p)


def importar_modelo(bid):
    d = MAN["modelos"][bid]
    folder = f"{ROOT}/Modelos/{bid}"
    meshes = {}
    for parte, info in d["mallas"].items():
        paths = _import([os.path.join(KIT, info["archivo"])], folder)[0]
        sm = next((EAL.load_asset(p) for p in paths if isinstance(EAL.load_asset(p), unreal.StaticMesh)), None)
        if sm is None:
            warn(bid, parte, "sin StaticMesh tras importar", paths)
            continue
        mats = sm.get_editor_property("static_materials")
        for i, st in enumerate(mats):
            slot = st.get_editor_property("material_slot_name")
            if parte == "Colision":                                  # invisible: material del motor
                sm.set_material(i, unreal.load_asset("/Engine/EngineMaterials/WorldGridMaterial"))
                continue
            mi = _slot_material(slot)
            if mi is None:
                warn(bid, parte, "ranura sin material del kit:", slot)
                continue
            sm.set_material(i, mi)
        cfg = MAN["partes"][parte]
        _nanite(sm, bool(cfg.get("nanite")))
        _collision(sm, "compleja" if cfg["colision"].startswith("compleja") else "ninguna")
        EAL.save_loaded_asset(sm)
        meshes[parte] = sm
    _limpiar_importados(folder, {sm.get_path_name().split(".")[0] for sm in meshes.values()})
    log(bid, "mallas:", list(meshes))
    return meshes


def importar_todo(modelos=None):
    importar_texturas()
    materiales()
    for bid in (modelos or presentes()):
        importar_modelo(bid)
    ejes()
    log("listo. Siguiente: ib.verificar()")


# ----------------------------------------------------------------------------------------------------------- ejes y verificación
def ejes():
    """Mide a dónde fue cada eje de Blender importando SM_BLK_Ejes (caja de 1,0 x 0,5 x 0,25 m en +x, +y, +z)."""
    global _ejes
    folder = f"{ROOT}/Comun"
    paths = _import([os.path.join(KIT, "comun", "geometria", "SM_BLK_Ejes.glb")], folder)[0]
    sm = next((EAL.load_asset(p) for p in paths if isinstance(EAL.load_asset(p), unreal.StaticMesh)), None)
    b = sm.get_bounding_box()
    mn, mx = (b.min.x, b.min.y, b.min.z), (b.max.x, b.max.y, b.max.z)
    ext = [mx[i] - mn[i] for i in range(3)]
    res = {}
    for baxis, length in (("x", 100.0), ("y", 50.0), ("z", 25.0)):
        i = min(range(3), key=lambda k: abs(ext[k] - length))
        sign = 1 if abs(mn[i]) < abs(mx[i]) else -1
        res[baxis] = (i, sign)
    _ejes = res
    _limpiar_importados(folder, {sm.get_path_name().split(".")[0]})
    log("ejes Blender -> Unreal:", {k: ("+" if s > 0 else "-") + "XYZ"[i] for k, (i, s) in res.items()},
        "(escala x100 si la caja mide", [round(e) for e in ext], "cm)")
    return res


def blender_a_ue(p):
    """Punto de Blender (m, relativo al pivote del edificio) -> vector local de Unreal (cm)."""
    if _ejes is None:
        ejes()
    v = [0.0, 0.0, 0.0]
    for k, comp in zip("xyz", p):
        i, s = _ejes[k]
        v[i] += s * comp * 100.0
    return unreal.Vector(v[0], v[1], v[2])


def frente(bid=None):
    """Dirección (local, Unreal) hacia la que mira la fachada principal: -y de Blender."""
    v = blender_a_ue((0.0, -1.0, 0.0))
    return v


def verificar():
    ok_all = True
    for bid in presentes():
        d = MAN["modelos"][bid]
        sm = EAL.load_asset(f"{ROOT}/Modelos/{bid}/{d['mallas']['Estructura']['nombre']}")
        if sm is None:
            warn(bid, "falta la malla de Estructura"); ok_all = False
            continue
        b = sm.get_bounding_box()
        ext = [b.max.x - b.min.x, b.max.y - b.min.y, b.max.z - b.min.z]
        me = d.get("medidas_estructura_m")       # fichas nuevas: medidas exactas de la malla de Estructura
        mm = me or d["medidas_m"]
        exp = blender_a_ue((mm["x"], mm["y"], mm["z"]))
        expv = [abs(exp.x), abs(exp.y), abs(exp.z)]
        # sin medidas_estructura_m se compara contra el modelo completo: la Estructura no lleva los detalles que sobresalen
        lo = 0.98 if me else 0.80
        okm = all(lo * e <= g <= 1.02 * e for g, e in zip(ext, expv))
        sin = [str(st.get_editor_property("material_slot_name")) for i, st in enumerate(sm.get_editor_property("static_materials"))
               if st.get_editor_property("material_interface") is None or
               not st.get_editor_property("material_interface").get_name().startswith("MI_")]
        log(bid, "medidas cm", [round(x) for x in ext], "esperadas ~", [round(x) for x in expv], "OK" if okm else "REVISAR",
            "| ranuras sin MI del kit:", sin or "ninguna", "| fachada principal hacia", frente(bid))
        ok_all &= okm and not sin
    log("verificación:", "OK" if ok_all else "REVISAR (ver arriba)")
    return ok_all


# ----------------------------------------------------------------------------------------------------------- colocación
def colocar(bid, ubicacion=None, yaw=0.0, con_escombro=True, etiqueta=None):
    """Pone el edificio: actor BLK_<ID>_Estructura (raíz) + Detalle, Mobiliario (si lo trae), Vidrio, Escombro y Colision
    enganchados a él."""
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    loc = ubicacion or unreal.Vector(0, 0, 0)
    rot = unreal.Rotator(roll=0.0, pitch=0.0, yaw=float(yaw))
    d = MAN["modelos"][bid]
    root = None
    actors = {}
    for parte, info in d["mallas"].items():
        if parte == "Escombro" and not con_escombro:
            continue
        sm = EAL.load_asset(f"{ROOT}/Modelos/{bid}/{info['nombre']}")
        if sm is None:
            warn(bid, parte, "no importado")
            continue
        a = sub.spawn_actor_from_object(sm, loc, rot)
        a.set_actor_label(f"{etiqueta or 'BLK_' + bid}_{parte}")
        c = a.static_mesh_component
        cfg = MAN["partes"][parte]
        if cfg["colision"].startswith("compleja"):
            c.set_collision_profile_name("BlockAll")
        else:
            c.set_collision_profile_name("NoCollision")
        if parte == "Vidrio":
            c.set_editor_property("cast_shadow", False)
        if parte == "Colision":
            c.set_editor_property("visible", False)
            a.set_actor_hidden_in_game(True)
        actors[parte] = a
        if parte == "Estructura":
            root = a
    for parte, a in actors.items():
        if a is not root and root is not None:
            a.attach_to_actor(root, "", unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD,
                              unreal.AttachmentRule.KEEP_WORLD, False)
    log(bid, "colocado en", loc, "yaw", yaw, "| raíz:", root.get_actor_label() if root else None)
    return root


def reemplazar(etiqueta_existente, bid, yaw_extra=0.0, borrar=False, con_escombro=True):
    """Pone <bid> en la posición y giro (yaw) de un actor existente del nivel y oculta (o borra) ese actor."""
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    viejo = next((a for a in sub.get_all_level_actors() if a.get_actor_label() == etiqueta_existente), None)
    if viejo is None:
        warn("no hay un actor con la etiqueta", etiqueta_existente)
        return None
    loc = viejo.get_actor_location()
    yaw = viejo.get_actor_rotation().yaw + yaw_extra
    root = colocar(bid, loc, yaw, con_escombro=con_escombro, etiqueta=f"BLK_{bid}_{etiqueta_existente}")
    if borrar:
        sub.destroy_actor(viejo)
    else:
        viejo.set_is_temporarily_hidden_in_editor(True)
        viejo.set_actor_hidden_in_game(True)
        viejo.set_actor_enable_collision(False)
    return root


def focos(raiz, lumenes=800.0, temperatura=2700.0, radio_cm=650.0, sombras=False):
    """Luz puntual en cada foco del modelo (departamentos: focos colgantes, 60 W ~ 800 lm, 2700 K; hospital: luminarias
    fluorescentes; usa lumenes=2000, temperatura=4000)."""
    label = raiz.get_actor_label()
    bid = next((b for b in MAN["modelos"] if f"_{b}_" in label + "_" or label.startswith(f"BLK_{b}")), None)
    pts = MAN["modelos"][bid].get("focos_m_blender", []) if bid else []
    sub = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    tr = raiz.get_actor_transform()
    n = 0
    for p in pts:
        w = tr.transform_location(blender_a_ue(p))
        L = sub.spawn_actor_from_class(unreal.PointLight, w, unreal.Rotator())
        lc = L.point_light_component
        try:
            lc.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
        except Exception:  # noqa: BLE001
            pass
        lc.set_editor_property("intensity", lumenes)
        lc.set_editor_property("use_temperature", True)
        lc.set_editor_property("temperature", temperatura)
        lc.set_editor_property("attenuation_radius", radio_cm)
        lc.set_editor_property("source_radius", 3.0)
        lc.set_editor_property("cast_shadows", sombras)
        L.set_actor_label(f"{label}_Foco_{n:02d}")
        L.attach_to_actor(raiz, "", unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD,
                          unreal.AttachmentRule.KEEP_WORLD, False)
        n += 1
    log(label, "focos:", n)
    return n
