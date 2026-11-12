"""kit_ue5_comun.py — parte común del kit UE5: texturas PBR de los materiales repetibles, máscara de suciedad del vidrio,
marcador de ejes y manifiesto (kit_ue5/manifiesto.json) a partir de las fichas de cada modelo (kit_ue5/modelos/<ID>/<ID>.json).

Uso: /root/blk-venv/bin/python tools/kit_ue5_comun.py [--out carpeta_del_kit] [--solo-manifiesto]
Texturas: kit_ue5/comun/texturas/T_BLK_<material>_{BC.png, N.png (DirectX), ORM.png (R AO, G rugosidad, B metal)}.
Los valores de color, tinte, rugosidad, metal y escala salen de las mismas tablas que usa el GLB web (bake_apt.TILE_TEX y
lookdev.BASE_COLORS): el tono es el mismo; en el motor se añaden normal, rugosidad por píxel y vidrio translúcido.
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BL = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, BL)
sys.path.insert(0, os.path.join(BL, "..", "scripts"))
import numpy as np  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402

import bake_apt as ba  # noqa: E402
import lookdev as ld  # noqa: E402
import texture_tools as tt  # noqa: E402

ENT = os.path.abspath(os.path.join(BL, ".."))
IDS = ["APT_A_5p", "APT_B_4p", "APT_C_3p", "APT_D_4p", "CAB_1_tablones", "CAB_2_pilotes", "CAB_3_ladrillo", "MUE_1_carga",
       "HOS_1_pueblo"]
# relieve por material para el normal derivado del albedo (madera y ladrillo marcados; aplanado y metal suaves)
NORMAL_STRENGTH = {"concrete": 4.0, "plaster": 3.0, "wood": 6.0, "wood_dark": 6.0, "wood_grey": 6.0, "brick": 7.0, "tile": 5.0,
                   "metal_rust": 3.5, "metal_paint": 3.0, "roof_metal": 3.5, "roof_metal_light": 3.0,
                   "terrazzo": 1.2, "tile_white": 2.5, "ceiling_tile": 2.0, "paint_mint": 0.6, "paint_green": 0.6, "paint_white": 0.6,
                   "wood_varnish": 3.0}
COLOR_ONLY = ["aluminium", "fabric", "cable", "plastic", "sand", "vegetation", "mortar", "paper",
              "plastic_blue", "linen", "sign_red", "sign_white", "sign_blue", "sign_green", "paint_yellow", "vinyl", "steel", "rubber", "wool_blue", "enamel"]
FRONT = {   # rasgo que identifica la fachada principal (-y de Blender) para orientar cada modelo en el mapa
    "APT_A_5p": "pórtico de concreto con la entrada de PB entre cortinas metálicas, logias con barandal",
    "APT_B_4p": "galerías de acceso con balaustrada y el pórtico con marquesina",
    "APT_C_3p": "hastial del ala sur con la cortina metálica de PB y 'Mi Vida Loca'",
    "APT_D_4p": "balcones colgados y las dos puertas de PB con marquesina",
    "CAB_1_tablones": "puerta delantera; el porche de un agua queda a un costado (oeste)",
    "CAB_2_pilotes": "veranda con la escalera exterior",
    "CAB_3_ladrillo": "porche delantero con escalones",
    "MUE_1_carga": "la rampa ancha que sube desde la playa (pivote en su eje, en la orilla de la cubierta); el atraque mira al mar (+y)",
    "HOS_1_pueblo": "pórtico de 4 columnas con COMMUNITY HOSPITAL en el pretil; la cochera de ambulancias queda al oriente (+x)",
}


def lin2srgb(c):
    c = np.clip(np.asarray(c, dtype=np.float64), 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


def luma_mean(path):
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    return float((lin @ np.array([0.2126, 0.7152, 0.0722])).mean())


def tile_textures(tdir):
    out = {}
    for name, (fn, size, rough, metal, tint) in ba.TILE_TEX.items():
        src = os.path.join(ld.TEX, fn)
        bc = os.path.join(tdir, f"T_BLK_{name}_BC.png")
        Image.open(src).convert("RGB").save(bc, optimize=True)
        n = os.path.join(tdir, f"T_BLK_{name}_N.png")
        tt.make_normal(src, n, strength=NORMAL_STRENGTH.get(name, 4.0))
        a = np.asarray(Image.open(n).convert("RGB")).copy()
        a[..., 1] = 255 - a[..., 1]                                # OpenGL -> DirectX
        Image.fromarray(a).save(n, optimize=True)
        tt.make_orm(src, os.path.join(tdir, f"T_BLK_{name}_ORM.png"), rough=rough, rough_var=0.15, metal=metal)
        out[name] = dict(textura_fuente=fn, tamano_m=size, rugosidad=rough, metal=metal, tinte_lineal=list(tint),
                         luma_media=round(luma_mean(src), 4))
    return out


def glass_grime(tdir):
    """Máscara de suciedad del vidrio (repetible): chorreados verticales (K2) + polvo en manchas grandes (K1 desenfocado)."""
    k2 = np.asarray(Image.open(os.path.join(ld.TEX, "K2_rain_streaks.png")).convert("L"), dtype=np.float32) / 255.0
    k1 = Image.open(os.path.join(ld.TEX, "K1_peel.png")).convert("L").resize(k2.shape[::-1])
    k1 = np.asarray(k1.filter(ImageFilter.GaussianBlur(18)), dtype=np.float32) / 255.0
    g = np.clip(0.65 * k2 + 0.55 * (k1 - k1.mean()) + 0.25, 0, 1)
    Image.fromarray((g * 255).astype(np.uint8)).save(os.path.join(tdir, "T_BLK_vidrio_suciedad.png"), optimize=True)


def materials(tiles):
    m = {}
    for name, t in tiles.items():
        m[f"BLK_{name}"] = dict(maestro="M_BLK_Repetible", texturas=dict(BC=f"T_BLK_{name}_BC", N=f"T_BLK_{name}_N",
                                                                          ORM=f"T_BLK_{name}_ORM"),
                                UVEscala=round(2.0 / t["tamano_m"], 5), Tinte=t["tinte_lineal"], LumaMedia=t["luma_media"],
                                PesoVC=0.75, AOFuerza=1.0, NormalFuerza=1.0, MacroFuerza=0.3,
                                dos_caras=name in ba.DOUBLE_SIDED,
                                nota=f"{t['textura_fuente']} a {t['tamano_m']} m por repetición; rugosidad {t['rugosidad']}, "
                                     f"metal {t['metal']} (en el ORM)")
    for name in COLOR_ONLY:
        c, rough, metal = ld.BASE_COLORS[name]
        m[f"BLK_{name}"] = dict(maestro="M_BLK_Color", Color=list(c), Rugosidad=rough, Metal=metal,
                                PesoVC=1.0 if name == "fabric" else 0.75, dos_caras=name in ba.DOUBLE_SIDED,
                                nota=("COLOR_0 lleva el color desteñido de cada pieza (ropa, cortinas, colchones) x AO; "
                                      "Color queda casi blanco") if name == "fabric" else "")
        if name == "fabric":
            m[f"BLK_{name}"]["Color"] = [0.9, 0.9, 0.9]
    m["BLK_glass"] = dict(maestro="M_BLK_Vidrio", Color=[0.035, 0.042, 0.042], OpacidadLimpia=0.16, OpacidadSucia=0.55,
                          RugosidadLimpia=0.03, RugosidadSucia=0.38, Especular=0.5, EscalaSuciedad=1.6, FuerzaSuciedad=1.0,
                          texturas=dict(Suciedad="T_BLK_vidrio_suciedad"), dos_caras=False,
                          nota="vidrio de 4 mm como prismas cerrados (cada esquirla tiene cara delantera y trasera): una cara. "
                               "Translúcido con iluminación por píxel (Surface ForwardShading); malla sin Nanite.")
    return m


def manifest(kit, tiles):
    models = {}
    for bid in IDS:
        f = os.path.join(kit, "modelos", bid, f"{bid}.json")
        if not os.path.exists(f):
            continue
        d = json.load(open(f))
        d["fachada_principal"] = dict(eje_blender="-y", rasgo=FRONT[bid])
        d["materiales_atlas"] = {f"{bid}_{aid}": dict(maestro="M_BLK_Atlas", texturas=tex, AOFuerza=1.0)
                                 for aid, tex in d["texturas"].items()}
        models[bid] = d
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ENT, capture_output=True, text=True).stdout.strip()
    man = dict(
        kit="BLACKISLE · edificios y cabañas para Unreal Engine 5", version_repo=sha,
        unidades="Los GLB están en metros (glTF): el importador de Unreal los pasa a centímetros (x100).",
        ejes=("Blender: z arriba, fachada principal hacia -y. La conversión de ejes la hace el importador glTF; "
              "comun/geometria/SM_BLK_Ejes.glb (caja de 1,0 x 0,5 x 0,25 m en +x, +y, +z de Blender) dice a dónde fue cada eje."),
        partes=dict(
            Estructura=dict(nanite=True, colision="ninguna", nota="carcasa, interior (muros, losas, escaleras, puertas, vestido) y techo"),
            Detalle=dict(nanite=True, colision="ninguna", nota="vanos, barandales, servicios, cables, daño"),
            Escombro=dict(nanite=False, colision="compleja como simple",
                          nota="escombro exterior suelto (sin terreno): se puede mover o borrar sin afectar al edificio"),
            Vidrio=dict(nanite=False, colision="ninguna", sombra=False, nota="todo el vidrio; material translúcido"),
            Colision=dict(nanite=False, colision="compleja como simple", visible=False,
                          nota="carcasa + interior con caras coplanares fundidas: misma forma, pocos triángulos; invisible"),
        ),
        materiales=materials(tiles),
        modelos=models,
    )
    json.dump(man, open(os.path.join(kit, "manifiesto.json"), "w"), indent=1, ensure_ascii=False)
    return man


def main():
    argv = sys.argv
    kit = os.path.abspath(argv[argv.index("--out") + 1] if "--out" in argv else os.path.join(ENT, "..", "kit_ue5"))
    tdir = os.path.join(kit, "comun", "texturas")
    os.makedirs(tdir, exist_ok=True)
    os.makedirs(os.path.join(kit, "comun", "geometria"), exist_ok=True)
    if "--solo-manifiesto" in argv:
        tiles = json.load(open(os.path.join(tdir, "repetibles.json")))
    else:
        tiles = tile_textures(tdir)
        glass_grime(tdir)
        json.dump(tiles, open(os.path.join(tdir, "repetibles.json"), "w"), indent=1, ensure_ascii=False)
        subprocess.run([sys.executable, os.path.join(BL, "export_ue5.py"), "--ejes",
                        os.path.join(kit, "comun", "geometria", "SM_BLK_Ejes.glb")], check=True, capture_output=True)
    man = manifest(kit, tiles)
    print("[comun] materiales", len(man["materiales"]), "modelos", list(man["modelos"]))


if __name__ == "__main__":
    main()
