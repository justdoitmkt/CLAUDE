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


def compose_overlay(pieces, size_px, px_per_m, keepout, out, seed=7, fade_from_m=None, fade_to_m=None, sun=0.12, buffs=()):
    """Como compose_panel pero SIN fondo: guarda la capa de grafiti RGBA (para montarla en el shader sobre cualquier superficie).
    pieces: [{"png", "x", "y", "w", "rot", "op"}] en metros desde la esquina inferior izquierda de la cara (mirando desde fuera).
    keepout: [(x0, y0, x1, y1)] m. fade_from_m/fade_to_m: desvanecimiento vertical del alfa (densidad decreciente sobre la PB).
    buffs: [(x0, y0, x1, y1, gris)] parches de pintura gris encima (borrados municipales), opacidad 0,9."""
    W, H = size_px
    canvas = np.zeros((H, W, 4), np.float32)
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
    for (bx0, by0, bx1, by1, g) in buffs:
        ys0, ys1 = int(H - by1 * px_per_m), int(H - by0 * px_per_m)
        xs0, xs1 = int(bx0 * px_per_m), int(bx1 * px_per_m)
        rng_ = np.random.default_rng(int(bx0 * 1000 + by0 * 10))
        h_, w_ = max(ys1 - ys0, 1), max(xs1 - xs0, 1)
        edge = _blur(rng_.random((h_, w_)).astype(np.float32), 6)            # borde irregular de rodillo
        m = np.clip((edge - 0.35) * 6, 0, 1)[..., None] * 0.9
        reg = canvas[max(ys0, 0):ys1, max(xs0, 0):xs1]
        m = m[:reg.shape[0], :reg.shape[1]]
        col = np.array([g, g * 0.98, g * 0.95], np.float32)
        a_old = reg[..., 3:4].copy()
        reg[..., :3] = np.where(a_old > 0, col * m + reg[..., :3] * (1 - m), col)
        reg[..., 3:4] = np.maximum(a_old, m)
    for (kx0, ky0, kx1, ky1) in keepout:
        canvas[max(int(H - ky1 * px_per_m), 0):max(int(H - ky0 * px_per_m), 0), max(int(kx0 * px_per_m), 0):max(int(kx1 * px_per_m), 0), 3] = 0
    if fade_from_m is not None and fade_to_m is not None:
        z = (H - np.arange(H)) / px_per_m
        f = np.clip((fade_to_m - z) / max(fade_to_m - fade_from_m, 1e-6), 0, 1)
        canvas[..., 3] *= f[:, None]
    pl = canvas[..., :3].mean(axis=2, keepdims=True)
    canvas[..., :3] = np.clip(canvas[..., :3] * (1 - sun) + pl * sun, 0, 1)    # pintura desteñida por el sol
    Image.fromarray((np.clip(canvas, 0, 1) * 255).astype(np.uint8), "RGBA").save(out)


# ------------------------------------------------------------------------------------------------
# grafiti denso por capas (receta del brief §D-3)
# ------------------------------------------------------------------------------------------------
def _recolor(arr, rgb):
    """Recolorea una pieza RGBA conservando su luminancia relativa (tags de distintos colores con la misma pieza)."""
    lum = arr[..., :3].mean(axis=2, keepdims=True)
    tint = np.array(rgb, np.float32)[None, None, :]
    out = arr.copy()
    out[..., :3] = np.clip(tint * (0.55 + 0.45 * lum) + (lum > 0.85) * 0.25, 0, 1)
    return out


def _load_piece(path, w_m, px_per_m, rot=0.0, rgb=None):
    im = Image.open(path).convert("RGBA")
    pw = max(int(w_m * px_per_m), 2)
    im = im.resize((pw, max(int(im.height * pw / im.width), 2)), Image.LANCZOS)
    if rot:
        im = im.rotate(rot, expand=True, resample=Image.BICUBIC)
    arr = np.asarray(im, np.float32) / 255.0
    if rgb is not None:
        arr = _recolor(arr, rgb)
    return arr


def _stamp(canvas, arr, cx, cy, op=1.0, overspray=0.0):
    H, W = canvas.shape[:2]
    h, w = arr.shape[:2]
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    sx0, sy0 = max(-x0, 0), max(-y0, 0)
    x0c, y0c = max(x0, 0), max(y0, 0)
    x1c, y1c = min(x0 + w, W), min(y0 + h, H)
    if x1c <= x0c or y1c <= y0c:
        return
    src = arr[sy0:sy0 + (y1c - y0c), sx0:sx0 + (x1c - x0c)].copy()
    if overspray > 0:   # halo de aerosol: alfa difuminado del color medio de la pieza
        a = src[..., 3]
        halo = _blur(a, max(2.0, w / 120.0)) * overspray
        col = (src[..., :3] * a[..., None]).sum(axis=(0, 1)) / max(a.sum(), 1e-6)
        src[..., :3] = np.where(a[..., None] > 0.05, src[..., :3], col[None, None, :])
        src[..., 3] = np.maximum(a, halo)
    dst = canvas[y0c:y1c, x0c:x1c]
    pa = src[..., 3:4] * op
    oa = pa + dst[..., 3:4] * (1 - pa)
    dst[..., :3] = (src[..., :3] * pa + dst[..., :3] * dst[..., 3:4] * (1 - pa)) / np.maximum(oa, 1e-6)
    dst[..., 3:4] = oa


def _hits(rect, keepout, pad=0.05):
    x0, y0, x1, y1 = rect
    return any(not (x1 < k[0] - pad or x0 > k[2] + pad or y1 < k[1] - pad or y0 > k[3] + pad) for k in keepout)


def compose_graffiti_dense(width_m, height_m, px_per_m, keepout, out, *, seed, hero=(), tags=(), icons=(), drips=(),
                           pb_top_m, coverage=0.85, peel_mask=None, n_tags=110, n_buffs=4, jpg_base=None, jpg_out=None):
    """Capa de grafiti RGBA densa por capas para una cara de PB.
    hero: [{"png", "w", "x"?, "y"?, "rot"?}] piezas grandes (throw-ups + lettering chicano). Si no traen x/y, se colocan solas
          por muestreo con rechazo SIN cruzar ninguna zona keepout (legibles enteras).
    tags/icons/drips: listas de PNG para la capa de fondo, los tags chicos encima, íconos y goteos.
    Capas: tags de fondo (densidad decreciente con la altura) → héroes → tags chicos → íconos → goteos → borrados grises
    irregulares → algunos tags encima de los borrados → desgaste (peel_mask) → desvanecimiento sobre la PB → keepout."""
    r = np.random.default_rng(seed)
    W, H = int(width_m * px_per_m), int(height_m * px_per_m)
    cv = np.zeros((H, W, 4), np.float32)
    PAL = [(0.03, 0.03, 0.04), (0.03, 0.03, 0.04), (0.08, 0.20, 0.62), (0.65, 0.07, 0.07), (0.92, 0.92, 0.90), (0.85, 0.62, 0.10)]
    to_px = lambda x, y: (x * px_per_m, H - y * px_per_m)

    def zpick(hi):
        return float(min(r.gamma(2.0, 0.55), hi))        # densidad alta abajo, decreciente hacia arriba

    # 1) capa de fondo: tags repetidos, recoloreados, translúcidos
    for _ in range(int(n_tags * coverage)):
        p = tags[int(r.integers(len(tags)))]
        w = float(r.uniform(0.45, 1.25))
        arr = _load_piece(p, w, px_per_m, rot=float(r.uniform(-14, 14)), rgb=PAL[int(r.integers(len(PAL)))])
        x = float(r.uniform(0, width_m)); y = zpick(pb_top_m + 0.4)
        _stamp(cv, arr, *to_px(x, y), op=float(r.uniform(0.35, 0.85)), overspray=0.25)
    # 2) héroes enteros fuera de los vanos y SIN encimarse entre sí (en el orden dado: el primero es el protagonista)
    taken = []
    for hp in hero:
        arr = _load_piece(hp["png"], hp["w"], px_per_m, rot=hp.get("rot", float(r.uniform(-5, 5))))
        hm, wm = arr.shape[0] / px_per_m, arr.shape[1] / px_per_m
        if "x" in hp:
            x, y = hp["x"], hp["y"]
        else:
            for _ in range(400):
                x = float(r.uniform(wm / 2 + 0.05, width_m - wm / 2 - 0.05)); y = float(r.uniform(hm / 2 + 0.08, max(pb_top_m - hm / 2 - 0.15, hm / 2 + 0.1)))
                rect = (x - wm / 2, y - hm / 2, x + wm / 2, y + hm / 2)
                if not _hits(rect, keepout) and not _hits(rect, taken, pad=0.12):
                    break
            else:
                continue
        taken.append((x - wm / 2, y - hm / 2, x + wm / 2, y + hm / 2))
        _stamp(cv, arr, *to_px(x, y), op=float(r.uniform(0.88, 1.0)), overspray=0.35)
    # 3) tags chicos encima + íconos + goteos
    for _ in range(int(n_tags * 0.25)):
        p = tags[int(r.integers(len(tags)))]
        arr = _load_piece(p, float(r.uniform(0.35, 0.8)), px_per_m, rot=float(r.uniform(-12, 12)), rgb=PAL[int(r.integers(4))])
        _stamp(cv, arr, *to_px(float(r.uniform(0, width_m)), zpick(pb_top_m)), op=float(r.uniform(0.6, 0.95)), overspray=0.2)
    for p in [icons[i] for i in r.permutation(len(icons))]:          # cada ícono una sola vez por cara
        arr = _load_piece(p, float(r.uniform(0.5, 1.0)), px_per_m, rot=float(r.uniform(-8, 8)))
        hm, wm = arr.shape[0] / px_per_m, arr.shape[1] / px_per_m
        for _ in range(60):
            x, y = float(r.uniform(0.3, width_m - 0.3)), float(r.uniform(0.6, pb_top_m - 0.4))
            if not _hits((x - wm / 2, y - hm / 2, x + wm / 2, y + hm / 2), taken + list(keepout), pad=0.05):
                _stamp(cv, arr, *to_px(x, y), op=0.9, overspray=0.3)
                break
    for _ in range(int(width_m * 0.8)):
        p = drips[int(r.integers(len(drips)))]
        arr = _load_piece(p, float(r.uniform(0.25, 0.6)), px_per_m, rgb=PAL[int(r.integers(4))] if r.random() < 0.5 else None)
        _stamp(cv, arr, *to_px(float(r.uniform(0, width_m)), float(r.uniform(0.3, 1.8))), op=float(r.uniform(0.5, 0.9)))
    # 4) borrados grises irregulares (rodillo), y unos tags encima
    for _ in range(n_buffs):
        bw, bh = float(r.uniform(0.9, 2.0)), float(r.uniform(0.6, 1.3))
        for _ in range(80):                                          # los borrados no tapan a los héroes
            bx, by = float(r.uniform(0, width_m - bw)), float(r.uniform(0.15, pb_top_m - bh))
            if not _hits((bx, by, bx + bw, by + bh), taken, pad=0.05):
                break
        else:
            continue
        ys0, ys1 = int(H - (by + bh) * px_per_m), int(H - by * px_per_m)
        xs0, xs1 = int(bx * px_per_m), int((bx + bw) * px_per_m)
        hh, ww = ys1 - ys0, xs1 - xs0
        yy, xx = np.mgrid[0:hh, 0:ww]
        d = np.minimum.reduce([xx / ww, 1 - xx / ww, yy / hh, 1 - yy / hh])
        n = _blur(r.random((hh, ww)).astype(np.float32), 9) - 0.5
        strokes = _blur(np.repeat(r.random((1, ww)), hh, axis=0).astype(np.float32), 3)       # pasadas verticales de rodillo
        m = np.clip((d + n * 0.5 - 0.04) * 14, 0, 1) * np.clip(0.75 + strokes * 0.3, 0, 1)
        g = float(r.uniform(0.42, 0.62)); col = np.array([g, g * 0.985, g * 0.95], np.float32)
        reg = cv[ys0:ys1, xs0:xs1]
        a_old = reg[..., 3:4].copy(); mm = m[..., None]
        reg[..., :3] = np.where(a_old > 0, col * mm + reg[..., :3] * (1 - mm), col)
        reg[..., 3:4] = np.maximum(a_old, mm * 0.92)
        for _ in range(int(r.integers(1, 3))):
            p = tags[int(r.integers(len(tags)))]
            arr = _load_piece(p, float(r.uniform(0.4, 0.8)), px_per_m, rot=float(r.uniform(-10, 10)), rgb=PAL[int(r.integers(4))])
            _stamp(cv, arr, *to_px(bx + bw * float(r.uniform(0.2, 0.8)), by + bh * float(r.uniform(0.3, 0.7))), op=0.9)
    # 5) desgaste: pintura descascarada y lavada por la lluvia
    if peel_mask is not None:
        pm = Image.open(peel_mask).convert("L")
        tile = int(1.6 * px_per_m)
        pm = np.asarray(pm.resize((tile, tile), Image.LANCZOS), np.float32) / 255.0
        reps = (H // tile + 1, W // tile + 1)
        pm = np.tile(pm, reps)[:H, :W]
        rain = _blur(np.repeat(r.random((1, W)), H, axis=0).astype(np.float32), 2.0)
        cv[..., 3] *= np.clip(1.0 - 0.55 * pm - 0.25 * (rain > 0.8), 0.0, 1.0)
    # 6) desvanecimiento sobre la PB + keepout + sol
    z = (H - np.arange(H)) / px_per_m
    cv[..., 3] *= np.clip((height_m - z) / max(height_m - (pb_top_m - 0.2), 1e-6), 0, 1)[:, None]
    for (kx0, ky0, kx1, ky1) in keepout:
        cv[max(int(H - ky1 * px_per_m), 0):max(int(H - ky0 * px_per_m), 0), max(int(kx0 * px_per_m), 0):max(int(kx1 * px_per_m), 0), 3] = 0
    pl = cv[..., :3].mean(axis=2, keepdims=True)
    cv[..., :3] = np.clip(cv[..., :3] * 0.88 + pl * 0.12, 0, 1)
    Image.fromarray((np.clip(cv, 0, 1) * 255).astype(np.uint8), "RGBA").save(out)
    if jpg_base and jpg_out:
        base = Image.open(jpg_base).convert("RGB")
        tw = int(3.0 * px_per_m); base = base.resize((tw, tw), Image.LANCZOS)
        bg = Image.new("RGB", (W, H))
        for ty in range(0, H, tw):
            for tx in range(0, W, tw):
                bg.paste(base, (tx, ty))
        b = np.asarray(bg, np.float32) / 255.0
        lum = b.mean(axis=2)
        hp = _blur(lum, 1.0) - _blur(lum, 8.0)
        a = cv[..., 3:4]
        paint = cv[..., :3] * np.clip(1.0 + hp * 2.5, 0.7, 1.3)[..., None]
        Image.fromarray((np.clip(b * (1 - a) + paint * a, 0, 1) * 255).astype(np.uint8)).save(jpg_out, quality=92)
