"""texture_tools.py - utilidades de textura para el edificio BLACKISLE (numpy + Pillow)."""
import json
import struct

import numpy as np
from PIL import Image, ImageFilter


def _blur(a, r):
    """Desenfoque gaussiano de un array float 2D en 0..1 (devuelve float32)."""
    im = Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8))
    return np.asarray(im.filter(ImageFilter.GaussianBlur(r)), dtype=np.float32) / 255.0


def _lum(path):
    return np.asarray(Image.open(path).convert("L"), dtype=np.float32) / 255.0


def make_seamless(src, dst, border=0.25):
    """Hace repetible una textura: cross-fade con la copia desplazada 50 %, primero en X y luego en Y.
    border (0..0.5) = ancho de la zona de mezcla respecto al tamaño de la imagen."""
    a = np.asarray(Image.open(src).convert("RGB"), dtype=np.float32)
    h, w, _ = a.shape

    def ramp(n):
        d = np.minimum(np.arange(n), n - 1 - np.arange(n)) / (border * n)  # 0 en el borde, 1 desde `border`
        t = np.clip(d, 0, 1)
        return t * t * (3 - 2 * t)

    mx = ramp(w)[None, :, None]
    a = a * mx + np.roll(a, w // 2, axis=1) * (1 - mx)
    my = ramp(h)[:, None, None]
    a = a * my + np.roll(a, h // 2, axis=0) * (1 - my)
    Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).save(dst, quality=95)


def make_normal(albedo, dst, strength=6.0, detail=1.2, lowcut=24.0):
    """Normal map (OpenGL, Y+) falsa a partir de la luminancia del albedo (alto-paso para quitar sombras horneadas)."""
    g = _lum(albedo)
    h = _blur(g, detail) - _blur(g, lowcut)
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) * strength
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) * strength
    n = np.dstack([-dx, dy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8)).save(dst)


def make_orm(albedo, dst, rough=0.85, rough_var=0.15, ao_strength=1.0, metal=0.0):
    """Mapa ORM de glTF: R = oclusión, G = rugosidad, B = metálico."""
    g = _lum(albedo)
    cav = g - _blur(g, 6)  # negativo en cavidades
    ao = np.clip(1.0 + ao_strength * np.minimum(cav, 0) * 3.0, 0.4, 1.0)
    r = np.clip(rough - rough_var * (g - g.mean()) * 2.0, 0.45, 1.0)
    orm = np.dstack([ao, r, np.full_like(g, metal)])
    Image.fromarray((orm * 255).astype(np.uint8)).save(dst)


def key_out(src, dst, key="green", lo=40.0, hi=110.0, margin=8):
    """Quita un fondo chroma plano: key="green" (0,255,0) o key="magenta" (255,0,255; para vegetación verde).
    Guarda PNG RGBA recortado al contenido, con despill del color de fondo."""
    if key not in ("green", "magenta"):
        raise ValueError("key debe ser 'green' o 'magenta'")
    a = np.asarray(Image.open(src).convert("RGB"), dtype=np.float32)
    kc = np.array([0, 255, 0] if key == "green" else [255, 0, 255], np.float32)
    alpha = np.clip((np.linalg.norm(a - kc, axis=2) - lo) / (hi - lo), 0, 1)
    rgb = a.copy()
    if key == "green":
        rgb[..., 1] = np.minimum(rgb[..., 1], np.maximum(rgb[..., 0], rgb[..., 2]))  # despill del verde
    else:
        spill = np.maximum(np.minimum(rgb[..., 0], rgb[..., 2]) - rgb[..., 1], 0)    # despill del magenta
        rgb[..., 0] -= spill
        rgb[..., 2] -= spill
    edge = (alpha < 0.98)[..., None]                       # el despill solo toca los píxeles de borde
    rgb = np.clip(np.where(edge, rgb, a), 0, 255)
    ys, xs = np.where(alpha > 0.05)
    if len(ys) == 0:
        raise ValueError("key_out: no queda contenido; revisa que el fondo sea plano y del color indicado")
    y0, y1 = max(ys.min() - margin, 0), min(ys.max() + margin, a.shape[0])
    x0, x1 = max(xs.min() - margin, 0), min(xs.max() + margin, a.shape[1])
    out = np.dstack([rgb, alpha * 255])[y0:y1, x0:x1].astype(np.uint8)
    Image.fromarray(out, "RGBA").save(dst)


def compose_panel(base_tile, pieces, size_px, px_per_m, keepout, out, tile_m=3.0, seed=7, opacity=0.92):
    """Pinta lettering/grafiti RGBA sobre concreto repetible y guarda el albedo del panel.
    pieces : [{"png": ruta RGBA, "x": m, "y": m, "w": m, "rot": grados, "op": 0..1}]
             (x, y = centro de la pieza en metros desde la esquina inferior izquierda de la cara)
    keepout: [(x0, y0, x1, y1)] en metros donde NO se pinta (puerta, ventanas)."""
    W, H = size_px
    rng = np.random.default_rng(seed)
    tile = Image.open(base_tile).convert("RGB")
    tw = max(int(tile_m * px_per_m), 8)
    tile = tile.resize((tw, tw), Image.LANCZOS)
    base = Image.new("RGB", (W, H))
    for ty in range(0, H, tw):
        for tx in range(0, W, tw):
            t = tile
            if rng.random() < 0.5:
                t = t.transpose(Image.FLIP_LEFT_RIGHT)
            if rng.random() < 0.5:
                t = t.transpose(Image.FLIP_TOP_BOTTOM)
            base.paste(t, (tx, ty))
    base = np.asarray(base, np.float32) / 255.0

    canvas = np.zeros((H, W, 4), np.float32)  # RGB recto + alfa
    for p in pieces:
        im = Image.open(p["png"]).convert("RGBA")
        pw = max(int(p["w"] * px_per_m), 2)
        im = im.resize((pw, max(int(im.height * pw / im.width), 2)), Image.LANCZOS)
        if p.get("rot"):
            im = im.rotate(p["rot"], expand=True, resample=Image.BICUBIC)
        arr = np.asarray(im, np.float32) / 255.0
        cx, cy = int(p["x"] * px_per_m), int(H - p["y"] * px_per_m)
        x0, y0 = cx - arr.shape[1] // 2, cy - arr.shape[0] // 2
        sx0, sy0 = max(-x0, 0), max(-y0, 0)
        x0c, y0c = max(x0, 0), max(y0, 0)
        x1c, y1c = min(x0 + arr.shape[1], W), min(y0 + arr.shape[0], H)
        if x1c <= x0c or y1c <= y0c:
            continue
        src = arr[sy0:sy0 + (y1c - y0c), sx0:sx0 + (x1c - x0c)]
        dst = canvas[y0c:y1c, x0c:x1c]
        pa = src[..., 3:4] * p.get("op", 1.0)
        oa = pa + dst[..., 3:4] * (1 - pa)
        dst[..., :3] = (src[..., :3] * pa + dst[..., :3] * dst[..., 3:4] * (1 - pa)) / np.maximum(oa, 1e-6)
        dst[..., 3:4] = oa

    for (kx0, ky0, kx1, ky1) in keepout:
        canvas[int(H - ky1 * px_per_m):int(H - ky0 * px_per_m), int(kx0 * px_per_m):int(kx1 * px_per_m), 3] = 0

    lum = base.mean(axis=2)
    hp = _blur(lum, 1.0) - _blur(lum, 8.0)  # relieve del concreto que debe "atravesar" la pintura
    paint = canvas[..., :3] * np.clip(1.0 + hp * 2.5, 0.7, 1.3)[..., None]
    pl = paint.mean(axis=2, keepdims=True)
    paint = np.clip(paint * 0.88 + pl * 0.12, 0, 1)  # pintura algo desteñida por el sol
    a = (canvas[..., 3:4] * opacity)
    res = base * (1 - a) + paint * a
    Image.fromarray((np.clip(res, 0, 1) * 255).astype(np.uint8)).save(out, quality=95)


def glb_tris(path):
    """Triángulos reales de un .glb (cuenta cada nodo que usa la malla)."""
    with open(path, "rb") as f:
        f.read(12)
        length, _ = struct.unpack("<II", f.read(8))
        j = json.loads(f.read(length))
    uses = {}
    for n in j.get("nodes", []):
        if "mesh" in n:
            uses[n["mesh"]] = uses.get(n["mesh"], 0) + 1
    total = 0
    for i, m in enumerate(j.get("meshes", [])):
        for p in m["primitives"]:
            if p.get("mode", 4) == 4:
                cnt = j["accessors"][p["indices"]]["count"] if "indices" in p else j["accessors"][p["attributes"]["POSITION"]]["count"]
                total += (cnt // 3) * uses.get(i, 0)
    return total


def despill_all(path):
    """Despill de verde en TODOS los píxeles de un PNG RGBA ya recortado (G <= max(R, B)).
    Para arte que por diseño no lleva verde y que el modelo tiñó de verde en brillos o halos."""
    a = np.asarray(Image.open(path).convert("RGBA")).copy()
    a[..., 1] = np.minimum(a[..., 1], np.maximum(a[..., 0], a[..., 2]))
    Image.fromarray(a, "RGBA").save(path)


def split_sheet(src_rgba, dst_prefix, min_gap=12, min_size=40, margin=8):
    """Separa una hoja RGBA (piezas en cuadrícula con huecos vacíos) en piezas sueltas.
    Corta primero por filas vacías y luego por columnas vacías dentro de cada fila (proyección del alfa).
    Devuelve la lista de rutas guardadas: <dst_prefix>_01.png, _02.png… en orden de lectura."""
    a = np.asarray(Image.open(src_rgba).convert("RGBA"))
    occ = a[..., 3] > 20

    def bands(profile):
        out, start, gap = [], None, 0
        for i, v in enumerate(profile):
            if v:
                if start is None:
                    start = i
                gap = 0
            elif start is not None:
                gap += 1
                if gap >= min_gap:
                    out.append((start, i - gap + 1))
                    start, gap = None, 0
        if start is not None:
            out.append((start, len(profile)))
        return [(s, e) for s, e in out if e - s >= min_size]

    paths = []
    for (y0, y1) in bands(occ.any(axis=1)):
        for (x0, x1) in bands(occ[y0:y1].any(axis=0)):
            sub = occ[y0:y1, x0:x1]
            ys = np.where(sub.any(axis=1))[0]
            yy0, yy1 = max(y0 + ys.min() - margin, 0), min(y0 + ys.max() + 1 + margin, a.shape[0])
            xx0, xx1 = max(x0 - margin, 0), min(x1 + margin, a.shape[1])
            p = f"{dst_prefix}_{len(paths) + 1:02d}.png"
            Image.fromarray(a[yy0:yy1, xx0:xx1], "RGBA").save(p)
            paths.append(p)
    return paths
