"""texturas_hospital.py — repetibles procedurales del hospital (HOS_1_pueblo), sin costura por construcción (todo en un toro).

Uso: /root/blk-venv/bin/python tools/texturas_hospital.py
Escribe en entrega/texturas/:
  T5_terrazo.png        terrazo pulido gris claro (1,5 m por repetición): matriz de cemento con grano de mármol blanco, gris,
                        negro y crema de 2 a 14 mm, juntas de latón cada 0,75 m.
  T6_azulejo_blanco.png azulejo blanco de 15 x 15 cm (0,6 m por repetición) con boquilla gris de 3 mm y variación de esmalte.
  T7_plafon.png         plafón reticular de 61 x 61 cm (1,22 m por repetición): placa mineral con fisuras finas y perfil T blanco.
"""
import os

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.abspath(os.path.join(HERE, "..", "..", "texturas"))


def _wrap_noise(n, cells, r, octaves=4):
    """Ruido de valor periódico (n x n px, `cells` celdas en la octava base) en 0..1."""
    acc = np.zeros((n, n), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        c = cells * (2 ** o)
        g = r.random((c, c)).astype(np.float32)
        g = np.tile(g, (3, 3))
        img = Image.fromarray((g * 255).astype(np.uint8)).resize((n * 3, n * 3), Image.BICUBIC)
        a = np.asarray(img, np.float32)[n:2 * n, n:2 * n] / 255.0
        acc += a * amp
        tot += amp
        amp *= 0.5
    return acc / tot


def _stamp_disc(img, cx, cy, rad, col, n, r):
    """Grano irregular (polígono de 6-9 lados) pegado en el toro."""
    k = int(r.integers(6, 10))
    ang = np.sort(r.random(k) * 2 * np.pi)
    rr = rad * (0.65 + 0.45 * r.random(k))
    x0, x1 = int(cx - rad * 1.2) - 1, int(cx + rad * 1.2) + 2
    y0, y1 = int(cy - rad * 1.2) - 1, int(cy + rad * 1.2) + 2
    ys, xs = np.mgrid[y0:y1, x0:x1]
    dx, dy = xs - cx, ys - cy
    a = np.arctan2(dy, dx) % (2 * np.pi)
    rad_at = np.interp(a, np.r_[ang, ang[0] + 2 * np.pi], np.r_[rr, rr[0]])
    m = np.hypot(dx, dy) <= rad_at
    img[ys[m] % n, xs[m] % n] = col


def terrazo(n=2048, seed=11):
    r = np.random.default_rng(seed)
    px_m = n / 1.5
    base = np.array([0.66, 0.65, 0.62], np.float32)
    nz = _wrap_noise(n, 6, r)
    img = np.empty((n, n, 3), np.float32)
    img[:] = base
    img *= (0.94 + 0.12 * nz)[..., None]
    chips = [((0.93, 0.92, 0.89), 0.42), ((0.40, 0.40, 0.39), 0.22), ((0.12, 0.12, 0.12), 0.12), ((0.78, 0.70, 0.58), 0.14),
             ((0.55, 0.54, 0.52), 0.10)]
    cols = np.array([c for c, _ in chips], np.float32)
    w = np.array([p for _, p in chips])
    area = 0.0
    while area < 0.42 * n * n:
        d_mm = float(np.clip(r.lognormal(np.log(4.5), 0.55), 1.6, 16.0))
        rad = d_mm / 1000 * px_m / 2
        col = cols[r.choice(len(cols), p=w / w.sum())] * float(r.uniform(0.9, 1.06))
        _stamp_disc(img, r.random() * n, r.random() * n, rad, col, n, r)
        area += np.pi * rad * rad
    # juntas de latón cada 0,75 m (dos por repetición)
    jw = max(2, int(0.003 * px_m))
    for k in range(2):
        p = int(k * n / 2)
        img[:, (np.arange(p - jw // 2, p + jw // 2 + 1)) % n] = (0.55, 0.45, 0.25)
        img[(np.arange(p - jw // 2, p + jw // 2 + 1)) % n, :] = (0.55, 0.45, 0.25)
    out = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
    out.save(os.path.join(TEX, "T5_terrazo.png"), optimize=True)


def azulejo(n=1024, seed=12, tiles=4):
    r = np.random.default_rng(seed)
    s = n // tiles
    img = np.zeros((n, n, 3), np.float32)
    glaze = _wrap_noise(n, 8, r, 3)
    g = max(2, int(round(0.003 / (0.6 / n))))
    for i in range(tiles):
        for j in range(tiles):
            c = np.array([0.88, 0.88, 0.86]) * float(r.uniform(0.96, 1.02)) + r.normal(0, 0.006, 3)
            img[j * s:(j + 1) * s, i * s:(i + 1) * s] = c
    img *= (0.97 + 0.05 * glaze)[..., None]
    grout = np.array([0.52, 0.52, 0.50])
    for k in range(tiles):
        a = k * s
        idx = np.arange(a - g // 2, a + g - g // 2) % n
        img[:, idx] = grout
        img[idx, :] = grout
    # bisel del esmalte junto a la boquilla
    edge = np.zeros((n, n), np.float32)
    for k in range(tiles):
        a = k * s
        for d in range(1, 4):
            for idx in ((a + g - g // 2 + d - 1) % n, (a - g // 2 - d) % n):
                edge[:, idx] = np.maximum(edge[:, idx], 1 - d / 4)
                edge[idx, :] = np.maximum(edge[idx, :], 1 - d / 4)
    img *= (1 - 0.08 * edge)[..., None]
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(os.path.join(TEX, "T6_azulejo_blanco.png"), optimize=True)


def plafon(n=1024, seed=13, panels=2):
    r = np.random.default_rng(seed)
    s = n // panels
    img = np.ones((n, n, 3), np.float32) * np.array([0.86, 0.85, 0.82])
    nz = _wrap_noise(n, 10, r, 4)
    img *= (0.95 + 0.07 * nz)[..., None]
    # fisuras de la placa mineral: trazos cortos y oscuros
    for _ in range(9000):
        x, y = r.random() * n, r.random() * n
        L = r.uniform(2, 9)
        a = r.random() * np.pi
        for t in np.linspace(0, L, int(L * 2)):
            img[int(y + t * np.sin(a)) % n, int(x + t * np.cos(a)) % n] *= 0.82
    for _ in range(26000):
        img[int(r.random() * n), int(r.random() * n)] *= float(r.uniform(0.7, 0.9))
    # manchas de agua escasas
    st = _wrap_noise(n, 3, r, 3)
    img *= (1 - 0.10 * np.clip((st - 0.68) / 0.1, 0, 1))[..., None] * np.array([1.0, 0.98, 0.93])
    # perfil T (24 mm) con sombra de la placa rebajada
    g = max(3, int(round(0.024 / (1.22 / n))))
    for k in range(panels):
        a = k * s
        idx = np.arange(a - g // 2, a + g - g // 2) % n
        img[:, idx] = (0.90, 0.90, 0.89)
        img[idx, :] = (0.90, 0.90, 0.89)
        for d in range(1, 5):
            for j in ((a + g - g // 2 + d - 1) % n, (a - g // 2 - d) % n):
                img[:, j] *= 0.86 + 0.035 * d
                img[j, :] *= 0.86 + 0.035 * d
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.4)).save(
        os.path.join(TEX, "T7_plafon.png"), optimize=True)


def pintura_lisa(n=1024, seed=14):
    """Pintura vinílica sobre aplanado fino (2 m por repetición): piel de naranja del rodillo, variación de tono muy leve,
    sin manchas ni descascarado (hospital en uso)."""
    r = np.random.default_rng(seed)
    a = 0.5 + 0.5 * (_wrap_noise(n, 48, r, 3) - 0.5) * 0.9
    b = _wrap_noise(n, 4, r, 3)
    img = np.ones((n, n, 3), np.float32) * 0.93
    img *= (0.975 + 0.035 * a + 0.02 * (b - 0.5))[..., None]
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(os.path.join(TEX, "T8_pintura_lisa.png"), optimize=True)


def _aniso_noise(n, cx, cy, r, octaves=3):
    """Ruido periódico anisótropo: cx celdas en X, cy en Y (vetas largas si cx << cy)."""
    acc = np.zeros((n, n), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        gx, gy = cx * 2 ** o, cy * 2 ** o
        g = r.random((gy, gx)).astype(np.float32)
        g = np.tile(g, (3, 3))
        img = Image.fromarray((g * 255).astype(np.uint8)).resize((n * 3, n * 3), Image.BICUBIC)
        acc += np.asarray(img, np.float32)[n:2 * n, n:2 * n] / 255.0 * amp
        tot += amp
        amp *= 0.5
    return acc / tot


def madera_barniz(n=1024, seed=15):
    """Madera barnizada (0,8 m por repetición): vetas largas en X que ondulan suave, anillos de espaciado variable, hilos de
    poro finos, bandas de duramen más oscuras y brillo de barniz; limpia (hospital en uso)."""
    r = np.random.default_rng(seed)
    yy = np.linspace(0, 1, n, endpoint=False)[:, None] * np.ones((1, n))
    warp = _aniso_noise(n, 2, 5, r, 3)
    space = _aniso_noise(n, 1, 3, r, 2)
    phase = yy * 18 + 2.2 * warp + 1.5 * space
    rings = np.abs(np.sin(np.pi * phase)) ** 0.6
    pores = _aniso_noise(n, 3, 160, r, 2)
    bands = _aniso_noise(n, 1, 4, r, 2)
    t = 0.62 * (1 - rings) + 0.22 * (pores - 0.5) + 0.35 * (bands - 0.5) + 0.25
    c0 = np.array([0.30, 0.16, 0.07])
    c1 = np.array([0.60, 0.38, 0.19])
    img = c0 + (c1 - c0) * np.clip(t, 0, 1)[..., None]
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(os.path.join(TEX, "T9_madera_barniz.png"), optimize=True)


if __name__ == "__main__":
    terrazo()
    azulejo()
    plafon()
    pintura_lisa()
    madera_barniz()
    print("ok", TEX)
