"""texturas_telecom.py — repetibles procedurales del sitio de telecomunicaciones (COM_1_antena), sin costura por construcción (toro).

Uso: /root/blk-venv/bin/python tools/texturas_telecom.py
Escribe en entrega/texturas/:
  T13_galvanizado.png  acero galvanizado por inmersión en caliente (1,0 m por repetición): gris zinc mate con flor de zinc
                       (cristales de 4–15 mm con tono propio), manchas de enfriamiento, velo blanco de óxido de zinc en
                       zonas y escurrimientos verticales cortos del baño.
  T14_grava.png        grava triturada de 3/4" (19 mm) de las plataformas de telecom (1,2 m por repetición): piedras angulosas
                       gris azulado con algunas calizas claras y alguna rojiza, sombra de contacto entre piedras y polvo fino.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from texturas_hospital import _aniso_noise, _wrap_noise  # noqa: E402

TEX = os.path.abspath(os.path.join(HERE, "..", "..", "texturas"))


def _save(img, name, blur=0.0):
    out = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    if blur:
        out = out.filter(ImageFilter.GaussianBlur(blur))
    out.save(os.path.join(TEX, name), optimize=True)


def voronoi_wrap(n, cells, r, jitter=0.9, aniso=1.0):
    """Voronoi periódico (n x n px) con `cells` x `cells` puntos sacudidos: devuelve (F1, F2, id de celda) en px.
    aniso > 1 estira las celdas en Y (piedras alargadas al azar no; se usa 1)."""
    s = n / cells
    pts = (np.stack(np.meshgrid(np.arange(cells), np.arange(cells), indexing="xy"), -1) + 0.5 +
           (r.random((cells, cells, 2)) - 0.5) * jitter) * s           # (cy, cx, 2) en px (x, y)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    ci, cj = (yy // s).astype(int), (xx // s).astype(int)
    f1 = np.full((n, n), 1e9, np.float32)
    f2 = np.full((n, n), 1e9, np.float32)
    idc = np.zeros((n, n), np.int64)
    dxy = np.zeros((n, n, 2), np.float32)
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            i2, j2 = (ci + di) % cells, (cj + dj) % cells
            p = pts[i2, j2]
            px = p[..., 0] + np.where(cj + dj < 0, -n, np.where(cj + dj >= cells, n, 0))
            py = p[..., 1] + np.where(ci + di < 0, -n, np.where(ci + di >= cells, n, 0))
            d = np.sqrt((xx - px) ** 2 + ((yy - py) * aniso) ** 2)
            closer = d < f1
            f2 = np.where(closer, f1, np.minimum(f2, d))
            idc = np.where(closer, i2 * cells + j2, idc)
            dxy = np.where(closer[..., None], np.dstack([xx - px, yy - py]), dxy)
            f1 = np.where(closer, d, f1)
    voronoi_wrap.dxy = dxy                                         # vector piedra->px de la última llamada
    return f1, f2, idc


def galvanizado(n=1024, seed=31):
    r = np.random.default_rng(seed)
    base = np.array([0.56, 0.58, 0.59])
    # flor de zinc: cristales de ~8 mm (1 m / 1024 px -> ~8 px) con tono y "brillo" propio por cristal
    f1, f2, idc = voronoi_wrap(n, 120, r)
    tone = r.normal(0.0, 0.035, 120 * 120)[idc]
    edge = np.clip((f2 - f1) / 2.0, 0, 1)                        # línea fina entre cristales
    img = base[None, None, :] * (1.0 + tone)[..., None]
    img *= (0.975 + 0.025 * edge)[..., None]
    # cristales grandes en zonas (piezas gruesas enfriadas lento)
    g1, g2, gid = voronoi_wrap(n, 40, r)
    big = _wrap_noise(n, 3, r, 3)
    tone2 = r.normal(0.0, 0.03, 40 * 40)[gid]
    img *= (1.0 + tone2 * np.clip((big - 0.55) * 4, 0, 1))[..., None]
    # moteado de enfriamiento y manchas de pasivación
    mott = _wrap_noise(n, 9, r, 4)
    img *= (0.93 + 0.12 * (mott - 0.5))[..., None]
    # velo blanco de óxido de zinc (pátina) en zonas
    bloom = np.clip((_wrap_noise(n, 5, r, 4) - 0.60) * 3.0, 0, 1) * 0.55
    img = img * (1 - bloom[..., None] * 0.35) + np.array([0.80, 0.81, 0.80]) * bloom[..., None] * 0.35
    # escurrimientos verticales cortos del baño (más oscuros) y gotas
    drip = _aniso_noise(n, 60, 2, r, 2)
    img *= (1.0 - 0.06 * np.clip((drip - 0.62) * 5, 0, 1))[..., None]
    _save(img, "T13_galvanizado.png", 0.4)


def grava(n=2048, seed=32):
    r = np.random.default_rng(seed)
    # 1,2 m / 2048 px = 0,59 mm por px; piedra de 3/4" (~19 mm) -> ~32 px -> 64 celdas
    img = np.zeros((n, n, 3))
    # fondo: finos (arena de trituración) oscuros entre piedras
    fn = _wrap_noise(n, 40, r, 3)
    img[:] = (np.array([0.27, 0.265, 0.26]) * (0.8 + 0.4 * fn)[..., None])
    wob = _wrap_noise(n, 90, r, 2) - 0.5                          # contorno irregular de cada piedra
    light = np.array([-0.45, -0.55, 0.70])
    light /= np.linalg.norm(light)
    for layer, (cells, jit, keep, rmul) in enumerate(((64, 0.95, 1.0, 0.62), (88, 0.95, 0.30, 0.58))):
        f1, f2, idc = voronoi_wrap(n, cells, r, jitter=jit)
        dxy = voronoi_wrap.dxy
        k = cells * cells
        s = n / cells
        R = s * rmul * r.uniform(0.80, 1.20, k)[idc]                # radio de cada piedra
        el = r.uniform(0.75, 1.0, k)[idc]                           # algo alargadas, con giro propio
        ang = r.uniform(0, np.pi, k)[idc]
        u = dxy[..., 0] * np.cos(ang) + dxy[..., 1] * np.sin(ang)
        v = (-dxy[..., 0] * np.sin(ang) + dxy[..., 1] * np.cos(ang)) / el
        rr = np.sqrt(u * u + v * v) / (R * (1 + 0.35 * wob))
        # facetas de fractura: el radio se recorta por 5-7 planos por piedra (forma angulosa de triturado)
        edge_poly = np.clip((f2 - f1) / (0.45 * s), 0, 1)
        inside = (rr < 1.0) & (edge_poly > 0.08)
        if keep < 1.0:
            inside &= (r.random(k) < keep)[idc]
        h = np.sqrt(np.clip(1 - rr ** 2, 0, 1)) * np.clip(edge_poly * 3, 0, 1)
        nx, ny = dxy[..., 0] / (R + 1e-6) * 0.9, dxy[..., 1] / (R + 1e-6) * 0.9
        nz = np.maximum(h, 0.15)
        nl = np.sqrt(nx * nx + ny * ny + nz * nz)
        shade = np.clip((nx * light[0] + ny * light[1] + nz * light[2]) / nl, 0, 1)
        kind = r.random(k)
        col = np.array([0.56, 0.565, 0.57]) * r.uniform(0.70, 1.15, (k, 1)) + r.normal(0, 0.010, (k, 3))
        col[kind > 0.90] = (np.array([0.66, 0.64, 0.59]) * r.uniform(0.85, 1.05, (k, 1)))[kind > 0.90]
        col[kind > 0.98] = (np.array([0.52, 0.40, 0.32]) * r.uniform(0.85, 1.05, (k, 1)))[kind > 0.98]
        col[kind < 0.08] = (np.array([0.28, 0.29, 0.30]) * r.uniform(0.9, 1.1, (k, 1)))[kind < 0.08]
        facets = _wrap_noise(n, 150 + 40 * layer, r, 2)
        c = col[idc] * (0.45 + 0.75 * shade)[..., None] * (0.92 + 0.16 * (facets - 0.5))[..., None]
        # sombra de contacto en el borde de la piedra
        c *= (0.55 + 0.45 * np.clip((1 - rr) * 4, 0, 1))[..., None]
        if layer == 0:
            img = np.where(inside[..., None], c, img)
        else:                                                      # piedras sueltas encima: arrojan sombra al sureste
            sh = np.roll(np.roll(inside, 4, 0), 4, 1) & ~inside
            img[sh] *= 0.6
            img = np.where(inside[..., None], c, img)
    dust = _wrap_noise(n, 6, r, 4)
    img = img * (0.93 + 0.12 * (dust - 0.5))[..., None]
    _save(img, "T14_grava.png", 0.45)


if __name__ == "__main__":
    galvanizado()
    grava()
    print("ok", TEX)
