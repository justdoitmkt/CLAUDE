"""kit/farm.py — utilería de una granja EN USO (GRA_1_tienda: granero rojo y tienda comunitaria en la llanura costera seca).

Pacas, paja suelta, costales, tarima, carretilla, herramientas, bebedero, cubeta, banco de trabajo, escalera, polipasto, rollo
de cuerda, foco colgante, gabinete metálico, divisiones de corral, cercas y tambo. Regla R-AAA: nada de cajas; cada pieza
lleva su construcción real (tablas con cantos matados y aristas irregulares, uniones clavadas/atornilladas/amarradas, lámina
rolada, soldaduras, costuras), lo blando es blando (paja con fleco de popotes, costales abombados que se asientan, trapos).

Convención: cada función devuelve un MB en metros, origen en el piso al centro de la pieza, frente hacia -Y, Z arriba, salvo:
- pitchfork/shovel: origen en el pie de la herramienta (puntas/hoja), herramienta vertical a lo largo de +Z;
- hoist/bare_bulb: origen en la viga/plafón, cuelgan hacia -Z;
- rope_coil: origen en la estaca, muro en y = 0, el rollo hacia -Y;
- stall_partition/pen_fence/wire_fence: corren a lo largo de +X desde x = 0, centradas en y = 0.
Materiales: wood, wood_dark, wood_grey, wood_varnish, steel, aluminium, metal_rust, roof_metal_light, rubber, cable, plastic,
plastic_blue, concrete, paint_green, paint_yellow, sign_red, sign_white, paper, glass, vegetation, hay, burlap, cardboard, amber.
Aleatoriedad solo vía rng(seed).
"""
import math

import bmesh
import bpy  # noqa: F401  (bpy antes que mathutils)
import numpy as np
from mathutils import Matrix, Vector, noise
from mathutils.bvhtree import BVHTree

from kit import port
from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rng, rr_profile
from kit.clinic_equipo import loft_rings, loop_tube, revolve, sweep_frame
from kit.clinic_servicios import _dedupe, hexnut, label, lathe, resample, rr_pts, skin, slab


# ======================================================================================================== primitivas
def _V(p):
    return Vector((float(p[0]), float(p[1]), float(p[2])))


def _perp(d):
    d = Vector(d).normalized()
    a = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
    n1 = (a - d * a.dot(d)).normalized()
    return n1, d.cross(n1)


def board(mb, p0, p1, w, t, mat, rr, r=0.004, up=(0, 0, 1), seg=3, n=1, rough=0.0012, warp=0.0, twist=0.0, square=2.5,
          deform=None, caps=(True, True)):
    """Tabla / viga aserrada de p0 a p1: sección w (lateral) × t (en `up`) con cantos matados de radio r, comba `warp` (m, hacia
    `up`), torcedura `twist` (grados a lo largo), aristas irregulares (`rough` m por vértice), testas con chaflán y corte fuera
    de escuadra (±`square` grados). deform(x, py, pz) -> (py, pz) para mordidas/desgaste. rr = Generator."""
    M, L = port.frame_on(p0, p1, up)
    prof = rr_profile(w, t, r, n)
    e = min(r * 0.8, L * 0.1)
    xs = [0.0, e] + [L * k / seg for k in range(1, seg)] + [L - e, L]
    xs = sorted(set(round(x, 6) for x in xs))
    cut0 = math.tan(math.radians(float(rr.uniform(-square, square))))
    cut1 = math.tan(math.radians(float(rr.uniform(-square, square))))
    sy = max(w / 2 - e * 0.85, w * 0.2) / (w / 2)
    sz = max(t / 2 - e * 0.85, t * 0.2) / (t / 2)
    rings = []
    for i, x in enumerate(xs):
        end = i == 0 or i == len(xs) - 1
        u = x / L if L > 0 else 0.0
        ring = []
        tw = math.radians(twist) * (u - 0.5)
        ct, st = math.cos(tw), math.sin(tw)
        for (py, pz) in prof:
            if end:
                py, pz = py * sy, pz * sz
            py += float(rr.uniform(-rough, rough))
            pz += float(rr.uniform(-rough, rough))
            if deform is not None:
                py, pz = deform(x, py, pz)
            py, pz = py * ct - pz * st, py * st + pz * ct
            pz += warp * math.sin(PI * u)
            xx = x + (py * cut0 if i <= 1 else (py * cut1 if i >= len(xs) - 2 else 0.0))
            ring.append(Vector((xx, py, pz)))
        rings.append(ring)
    loft_rings(mb, rings, mat, M=M, cap0=caps[0], cap1=caps[1])
    return M, L


def log_post(mb, p0, p1, r0, r1, mat, rr, seg=10, rings=6, crook=0.015, top=True, checks=1, cap_bottom=True, rough=0.06):
    """Poste rollizo de p0 (abajo) a p1 (arriba): radio r0 -> r1 con irregularidad por vértice, eje chueco, grietas de secado
    (columnas hundidas) y cabeza intemperizada (canto redondeado y copete abombado)."""
    p0, p1 = _V(p0), _V(p1)
    d = (p1 - p0)
    L = d.length
    d.normalize()
    n1, n2 = _perp(d)
    ph = [float(rr.uniform(0, 2 * PI)) for _ in range(4)]
    ck = [int(rr.integers(0, seg)) for _ in range(checks)]
    loops = []
    zs = [L * k / (rings - 1) for k in range(rings)]
    if top:
        zs[-1] = L - 0.012
    for i, z in enumerate(zs):
        u = z / L
        off = crook * (math.sin(PI * u + ph[0]) * n1 + 0.7 * math.sin(2 * PI * u + ph[1]) * n2) * math.sin(PI * u)
        rad = r0 + (r1 - r0) * u
        c = p0 + d * z + off
        ring = []
        for k in range(seg):
            a = 2 * PI * k / seg + 0.15 * math.sin(i + ph[2])
            f = 1.0 + float(rr.uniform(-rough, rough)) + 0.05 * math.sin(3 * a + ph[3])
            if k in ck and 0 < i < rings - 1:
                f -= 0.09
            ring.append(c + (n1 * math.cos(a) + n2 * math.sin(a)) * rad * f)
        loops.append(ring)
    if top:
        c = p0 + d * L + crook * 0.0 * n1
        last = loops[-1]
        cc = sum(last, Vector()) / len(last)
        loops.append([cc + (v - cc) * 0.82 + d * 0.011 for v in last])
        loops.append([cc + d * (0.014 + float(rr.uniform(-0.003, 0.004))) + n1 * float(rr.uniform(-0.01, 0.01))])
    skin(mb, loops, mat, cap0=cap_bottom, cap1=True)
    return loops


def bplate(mb, outline, t, mat, M=None, e=0.0015):
    """Placa: polígono 2D (x, y) extruido t en +z con cantos matados `e` (4 lazos: el exterior de cada cara inset `e`)."""
    P = [Vector((x, y, 0.0)) for (x, y) in outline]
    n = len(P)
    area = sum(P[i].x * P[(i + 1) % n].y - P[(i + 1) % n].x * P[i].y for i in range(n))
    sgn = 1.0 if area > 0 else -1.0

    def inset(dl):
        out = []
        for i in range(n):
            a, b, c = P[i - 1], P[i], P[(i + 1) % n]
            t0 = (b - a).normalized()
            t1 = (c - b).normalized()
            n0 = Vector((t0.y, -t0.x, 0)) * sgn
            n1 = Vector((t1.y, -t1.x, 0)) * sgn
            bis = (n0 + n1)
            if bis.length < 1e-6:
                bis = n0
            bis.normalize()
            k = max(bis.dot(n0), 0.35)
            out.append(b - bis * (dl / k))
        return out
    e = min(e, t * 0.45)
    if e > 0:
        rings = [[p + Vector((0, 0, z)) for p in ring] for (ring, z) in ((inset(e), 0.0), (P, e), (P, t - e), (inset(e), t))]
    else:
        rings = [[p + Vector((0, 0, z)) for p in P] for z in (0.0, t)]
    loft_rings(mb, rings, mat, M=M, cap0=True, cap1=True)


def nail(mb, M, r=0.0045, mat="steel", seg=6):
    """Cabeza de clavo (ligeramente abombada) apoyada en z = 0 local, hundida 0,4 mm en la madera (sin tapa oculta)."""
    lathe(mb, [(r, -0.0004), (r * 0.8, 0.0009), (0.0, 0.0013)], seg=seg, mat=mat, M=M, caps=False)


def cbolt(mb, M, r=0.011, mat="steel", nut=False):
    """Perno de coche (cabeza de hongo) o tuerca cuadrada con espárrago, apoyado en z = 0 local."""
    if nut:
        lathe(mb, [(r * 1.1, -0.0003), (r * 1.1, 0.0015)], seg=10, mat=mat, M=M)
        lathe(mb, [(r * 0.95, 0.0015), (r * 0.95, 0.0015 + r * 0.8), (r * 0.8, 0.0015 + r * 0.9)], seg=4, mat=mat, M=M, phase=PI / 4)
        lathe(mb, [(r * 0.45, 0.0015 + r * 0.9), (r * 0.45, 0.0015 + r * 1.5), (r * 0.3, 0.0015 + r * 1.6), (0.0, 0.0015 + r * 1.6)],
              seg=6, mat=mat, M=M)
    else:
        lathe(mb, [(r, -0.0003), (r * 0.97, r * 0.2), (r * 0.75, r * 0.45), (r * 0.35, r * 0.58), (0.0, r * 0.6)], seg=10, mat=mat, M=M)


def rope_tube(mb, pts, r, mat="burlap", seg=6, step=None, lay=None, depth=0.16, caps=True, strands=3):
    """Cuerda torcida de 3 cabos: tubo por la polilínea con la sección de 3 lóbulos girando a lo largo (paso `lay`)."""
    step = step or r * 2.2
    lay = lay or r * 18
    P = [Vector(p) for p in resample(_dedupe([tuple(p) for p in pts], 1e-5), step)]
    n = len(P)
    if n < 2:
        return
    T = []
    for i in range(n):
        a = P[min(i + 1, n - 1)] - P[max(i - 1, 0)]
        T.append(a.normalized() if a.length > 1e-9 else Vector((0, 0, 1)))
    ref = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
    N = (ref - T[0] * ref.dot(T[0])).normalized()
    rings = []
    s = 0.0
    for i in range(n):
        if i > 0:
            s += (P[i] - P[i - 1]).length
            N = (N - T[i] * N.dot(T[i])).normalized()
        B = T[i].cross(N)
        ph = 2 * PI * s / lay
        ring = []
        for k in range(seg):
            a = 2 * PI * k / seg
            rr_ = r * (1.0 - depth * (0.5 - 0.5 * math.cos(strands * (a - ph))))
            ring.append(P[i] + (N * math.cos(a) + B * math.sin(a)) * rr_)
        rings.append(ring)
    loft_rings(mb, rings, mat, cap0=caps, cap1=caps)


def straw(mb, p, d, L, r, rr, mat="hay", droop=0.25, segs=2, flat=0.55, curl=0.35):
    """Popote suelto: prisma de 3 lados aplanado que se adelgaza a punta, doblado por la gravedad y con curvatura al azar.
    p = raíz (debe quedar 3-5 mm dentro de la superficie de la que sale)."""
    d = Vector(d).normalized()
    pts = [Vector(p)]
    side = Vector((float(rr.uniform(-1, 1)), float(rr.uniform(-1, 1)), float(rr.uniform(-1, 1)))) * curl
    for k in range(segs):
        d = (d + side * (1.0 / segs) + Vector((0, 0, -droop / segs))).normalized()
        q = pts[-1] + d * (L / segs)
        q.z = max(q.z, r * 1.1)                                   # se apoya en el piso, no lo atraviesa
        pts.append(q)
    n1, n2 = _perp(pts[1] - pts[0])
    tw = float(rr.uniform(0, 2 * PI))
    loops = []
    for i, c in enumerate(pts[:-1]):
        f = 1.0 - 0.35 * i / segs
        loops.append([c + (n1 * math.cos(tw + 2 * PI * k / 3) + n2 * math.sin(tw + 2 * PI * k / 3) * flat) * r * f for k in range(3)])
    loops.append([pts[-1]])
    skin(mb, loops, mat, cap0=True, cap1=False)
    return pts


# ======================================================================================================== paja
BALE = (0.90, 0.46, 0.36)
TWINE_Y = 0.115


def _bale_outline(hy, hz, rc, cinch, bulge, bul_cut, bul_fold, rr, jit):
    """Contorno (y, z) de un tajo de paca, centrado: base plana, esquinas redondeadas, vértices de amarre (cinchados) en
    y = ±TWINE_Y arriba, cara superior abombada entre hilos, lado de corte (-Y) casi plano y lado doblado (+Y) abombado.
    17 vértices, antihorario."""
    P = []
    tw = TWINE_Y
    for (cy, cz, a0) in ((hy - rc, -hz + rc, -PI / 2), (hy - rc, hz - rc, 0.0)):
        for k in range(3):
            a = a0 + PI / 4 * k
            P.append((cy + rc * math.cos(a), cz + rc * math.sin(a)))
        if a0 < 0:
            P.append((hy + bul_fold, 0.0))
    for y in (tw, 0.0, -tw):
        P.append((y, hz - cinch if y else hz + bulge))
    for (cy, cz, a0) in ((-hy + rc, hz - rc, PI / 2), (-hy + rc, -hz + rc, PI)):
        for k in range(3):
            a = a0 + PI / 4 * k
            P.append((cy + rc * math.cos(a), cz + rc * math.sin(a)))
        if a0 < PI * 0.75:
            P.append((-hy - bul_cut, 0.0))
    return [(y + float(rr.uniform(-jit, jit)), z + float(rr.uniform(-jit, jit))) for (y, z) in P]


def hay_bale(seed=0):
    """Paca chica de 0,90 × 0,46 × 0,36 (eje largo X): cuerpo de 'tajos' (flakes) de 6-10 cm separados por juntas suaves de
    3-6 mm, cada tajo con su contorno irregular; cara superior abombada entre los hilos, lado de corte (-Y) casi plano con
    puntas de popote cortadas, lado doblado (+Y) abombado; cinchada por dos hilos (henequén o rafia) tensos que puentean las
    juntas, con nudo del anudador y cabos; testas abombadas e irregulares con popotes cortados, fleco de popotes sueltos que
    se doblan por su peso y algunos tirados al piso. Asentada: base plana en z = 0. ≤ 2 500 triángulos."""
    r = rng(seed)
    L, W, H = BALE
    hz0 = H / 2
    # ---- tajos
    xs = [-L / 2]
    while xs[-1] < L / 2 - 0.13:
        xs.append(xs[-1] + float(r.uniform(0.064, 0.10)))
    xs.append(L / 2)
    nfl = len(xs) - 1
    outl = []
    for i in range(nfl):
        hy = W / 2 + float(r.uniform(-0.005, 0.005))
        hz = hz0 + float(r.uniform(-0.004, 0.006))
        outl.append(dict(o=_bale_outline(hy, hz, float(r.uniform(0.03, 0.042)), float(r.uniform(0.004, 0.008)),
                                         float(r.uniform(0.003, 0.010)), float(r.uniform(0.0, 0.004)), float(r.uniform(0.005, 0.014)),
                                         r, 0.004),
                         dy=float(r.uniform(-0.004, 0.004)), dz=float(r.uniform(-0.002, 0.003))))
    tilt = [(float(r.uniform(-0.03, 0.03)), float(r.uniform(-0.03, 0.03))) for _ in xs]

    wav = [(float(r.uniform(0.0015, 0.005)), float(r.uniform(0, 2 * PI)), float(r.uniform(9, 16))) for _ in xs]

    def ring_at(x, o, dy, dz, scale, tl, xj=0.0, wv=None):
        out = []
        for (y, z) in o:
            yy, zz = y * scale[0] + dy, z * scale[1] + dz
            xw = wv[0] * math.sin(wv[2] * (yy + zz) + wv[1]) if wv else 0.0     # juntas onduladas, no planos perfectos
            out.append(Vector((x + tl[0] * yy + tl[1] * zz + xw + (float(r.uniform(-xj, xj)) if xj else 0.0), yy, zz + hz0)))
        return out
    loops = []
    e = 0.016
    for i in range(nfl):
        F = outl[i]
        xa, xb = xs[i], xs[i + 1]
        if i == 0:
            loops.append([Vector((xa - float(r.uniform(0.014, 0.024)), F["dy"] + float(r.uniform(-0.03, 0.03)),
                                  hz0 + F["dz"] + float(r.uniform(-0.03, 0.03))))])
            loops.append(ring_at(xa - 0.004, F["o"], F["dy"], F["dz"], (0.9, 0.9), tilt[0], xj=0.006))
        else:
            G = outl[i - 1]
            avg = [((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2) for a_, b_ in zip(F["o"], G["o"])]
            dd = float(r.uniform(0.003, 0.006))
            sc = (1 - dd / (W / 2), 1 - dd * 0.8 / hz0)
            loops.append(ring_at(xa, avg, (F["dy"] + G["dy"]) / 2, (F["dz"] + G["dz"]) / 2, sc, tilt[i], wv=wav[i]))
        jit = [(float(r.uniform(-0.0025, 0.0025)), float(r.uniform(-0.0025, 0.0025))) for _ in F["o"]]
        o2 = [(y + j[0], z + j[1]) for (y, z), j in zip(F["o"], jit)]
        loops.append(ring_at(xa + e, F["o"], F["dy"], F["dz"], (1, 1), tilt[i], wv=wav[i]))
        loops.append(ring_at(xb - e, o2, F["dy"], F["dz"], (1, 1), tilt[i + 1], wv=wav[i + 1]))
        if i == nfl - 1:
            loops.append(ring_at(xb + 0.004, F["o"], F["dy"], F["dz"], (0.9, 0.9), tilt[-1], xj=0.006))
            loops.append([Vector((xb + float(r.uniform(0.014, 0.024)), F["dy"] + float(r.uniform(-0.03, 0.03)),
                                  hz0 + F["dz"] + float(r.uniform(-0.03, 0.03))))])
    for L_ in loops:                                              # asentada: la base se aplana contra el piso
        for v in L_:
            if v.z < 0.012:
                v.z = max(0.0, v.z * 0.35)
    body = MB()
    skin(body, loops, "hay")
    bm = body.bm
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    faces = [(f.calc_center_median(), f.normal.copy(), f.calc_area()) for f in bm.faces]
    mb = MB()
    mb.join(body)
    # ---- hilos: proyectados sobre la superficie real (rayos desde un rectángulo redondeado exterior), tensos entre crestas
    tree = BVHTree.FromBMesh(bm)
    tmat = ["burlap", "burlap", "plastic_blue", "sign_red"][int(r.integers(0, 4))]
    rt = 0.0028
    A, B, Rc = L / 2 + 0.05, H / 2 + 0.05, 0.08
    outer = [Vector((x, 0.0, z + hz0)) for (x, z) in rr_pts(2 * A, 2 * B, Rc, n=3)]
    outer = [Vector(p) for p in resample([tuple(p) for p in outer + [outer[0]]], 0.075)][:-1]
    for sgn in (-1, 1):
        y = sgn * TWINE_Y + float(r.uniform(-0.005, 0.005))
        pts = []
        for q in outer:
            q = Vector((q.x, y, q.z))
            qi = Vector((min(max(q.x, -A + Rc), A - Rc), y, min(max(q.z, hz0 - B + Rc), hz0 + B - Rc)))
            hit, nrm, _, _ = tree.ray_cast(q, (qi - q).normalized(), 0.5)
            if hit is None:
                continue
            p_ = hit + nrm * (rt - 0.0012)
            p_.y = y
            p_.z = max(p_.z, rt)
            pts.append(p_)
        loop_tube(mb, pts, rt, seg=3, mat=tmat, normal=(0, 1, 0))
        kp = min((p_ for p_ in pts if p_.z > H * 0.8), key=lambda p_: abs(p_.x - (0.3 * sgn)))
        lathe(mb, [(0.0, -0.002), (0.0045, 0.0), (0.0065, 0.003), (0.0045, 0.007), (0.0, 0.008)], seg=5, mat=tmat,
              M=_T(kp.x, kp.y, kp.z - 0.001) @ _Rx(float(r.uniform(-20, 20))))
        for k in range(2):                                        # cabos cortados del nudo
            straw(mb, (kp.x, kp.y, kp.z + 0.003), (float(r.uniform(-1, 1)), float(r.uniform(-0.4, 0.4)), 0.3), 0.03, 0.0018, r,
                  mat=tmat, droop=0.6, segs=1)
    # ---- popotes: puntas cortadas (testas y lado de corte -Y), fleco largo que cuelga de juntas y aristas
    areas = np.array([a_ * (1.0 + 12.0 * (1.0 - max(abs(n_.x), abs(n_.y), abs(n_.z)))) for (_, n_, a_) in faces])   # más en aristas
    cdf = np.cumsum(areas) / areas.sum()
    n_long = n_stub = tries = 0
    while (n_long < 52 or n_stub < 34) and tries < 4000:
        tries += 1
        c, nrm, _ = faces[int(np.searchsorted(cdf, r.uniform()))]
        if nrm.z < -0.5 or c.z < 0.02:
            continue
        cut = abs(nrm.x) > 0.6 or nrm.y < -0.7
        if cut and n_stub < 34:
            d = (nrm + Vector((float(r.uniform(-0.45, 0.45)), float(r.uniform(-0.45, 0.45)), float(r.uniform(-0.35, 0.5))))).normalized()
            straw(mb, c - nrm * 0.004, d, float(r.uniform(0.016, 0.045)), 0.0017, r, droop=0.05, segs=1)
            n_stub += 1
            continue
        if cut or n_long >= 52:
            continue
        t1 = Vector((1, 0, 0)) if abs(nrm.x) < 0.7 else Vector((0, 0, 1))
        t1 = (t1 - nrm * t1.dot(nrm)).normalized()
        if r.uniform() < 0.5:
            t1 = -t1
        d = (t1 * float(r.uniform(0.6, 1.0)) + nrm * float(r.uniform(0.12, 0.5))
             + nrm.cross(t1) * float(r.uniform(-0.5, 0.5))).normalized()
        straw(mb, c - nrm * 0.004, d, float(r.uniform(0.06, 0.17)), 0.002, r, droop=0.6 if c.z < 0.09 else 0.3, segs=2)
        n_long += 1
    for k in range(8):                                            # popotes que salen de la junta inferior y descansan en el piso
        x = float(r.uniform(-L / 2 + 0.05, L / 2 - 0.05))
        sy = 1 if r.uniform() < 0.5 else -1
        ang = float(r.uniform(-0.9, 0.9))
        d = Vector((math.sin(ang), sy * math.cos(ang), 0.0))
        p0 = Vector((x, sy * (W / 2 - 0.025), 0.012))
        Ls = float(r.uniform(0.07, 0.16))
        pts = [p0, p0 + d * Ls * 0.45 + Vector((0, 0, -0.0085)), p0 + d * Ls + Vector((0, 0, -0.0095))]
        n1, n2 = _perp(d)
        lp = [[c + (n1 * math.cos(2 * PI * q / 3) + n2 * math.sin(2 * PI * q / 3) * 0.55) * 0.002 for q in range(3)] for c in pts[:-1]]
        skin(mb, lp + [[pts[-1]]], "hay", cap0=True, cap1=False)
    return mb


def _bale_M(x, y, z, yaw, rot90=False, side=False, tilt=(0.0, 0.0)):
    """Matriz de una paca: posición del centro de su base, giro en planta; rot90 = eje largo en Y; side = de canto
    (girada 90° sobre su eje largo: 0,46 de alto)."""
    M = _T(x, y, z) @ _Rz(yaw + (90.0 if rot90 else 0.0)) @ _Rx(tilt[0]) @ _Ry(tilt[1])
    if side:
        M = M @ _T(0, 0, BALE[1] / 2) @ _Rx(90) @ _T(0, 0, -BALE[2] / 2)
    return M


def hay_stack(nx=3, ny=2, nz=3, seed=0):
    """Estiba de pacas: capas trabadas (si ny es par, las capas impares van giradas 90° — dos anchos = un largo —; si no, a
    tizón corrido con media paca de desfase), cada paca con su holgura, giro y asentamiento (se hunde 5-8 mm en la de abajo),
    capa superior incompleta (se está usando) con una paca jalada a medias, y pacas sueltas al pie: una tirada en el piso y
    otra de canto. Origen: piso al centro de la huella de la estiba."""
    r = rng(seed)
    L, W, H = BALE
    pool = [hay_bale(seed=seed * 11 + k) for k in range(6)]
    mb = MB()
    WX, DY = nx * L, ny * W
    used = 0
    slots = []
    for k in range(nz):
        z = k * (H - 0.007)
        rot = (k % 2 == 1) and (ny % 2 == 0)
        if rot:
            cx, cy = int(round(WX / W)), ny // 2
            for i in range(cx):
                for j in range(cy):
                    slots.append((k, -WX / 2 + WX * (i + 0.5) / cx, -DY / 2 + L * (j + 0.5), z, True))
        elif k % 2 == 1:
            for i in range(nx - 1):
                for j in range(ny):
                    slots.append((k, -WX / 2 + L * (i + 1), -DY / 2 + W * (j + 0.5), z, False))
        else:
            for i in range(nx):
                for j in range(ny):
                    slots.append((k, -WX / 2 + L * (i + 0.5), -DY / 2 + W * (j + 0.5), z, False))
    top = [s_ for s_ in slots if s_[0] == nz - 1]
    gone = set()
    if nz > 1 and len(top) > 2:
        n_gone = int(r.integers(1, max(2, len(top) // 2)))
        for idx in r.choice(len(top), n_gone, replace=False):
            gone.add(top[int(idx)][1:3])
    pulled = None
    rest_top = [s_ for s_ in top if s_[1:3] not in gone]
    if nz > 1 and rest_top:
        pulled = rest_top[int(r.integers(0, len(rest_top)))][1:3]
    for (k, x, y, z, rot) in slots:
        if (x, y) in gone and k == nz - 1:
            continue
        jx, jy = float(r.uniform(-0.014, 0.014)), float(r.uniform(-0.012, 0.012))
        yaw = float(r.uniform(-2.0, 2.0))
        if k == nz - 1 and (x, y) == pulled:                      # paca jalada hacia el frente a medias
            jy -= float(r.uniform(0.12, 0.22)) if not rot else 0.0
            jx += float(r.uniform(0.12, 0.2)) if rot else 0.0
            yaw += float(r.uniform(-9, 9))
        tl = (float(r.uniform(-1.0, 1.0)), float(r.uniform(-0.8, 0.8))) if k else (0.0, 0.0)
        mb.join(pool[used % len(pool)], _bale_M(x + jx, y + jy, z - (0.004 if k else 0.0), yaw, rot90=rot, tilt=tl))
        used += 1
    # pacas sueltas al pie: una en el piso frente a la estiba, otra de canto al costado
    y0 = -DY / 2 - W / 2 - float(r.uniform(0.25, 0.45))
    mb.join(pool[used % 6], _bale_M(float(r.uniform(-0.3, 0.3)) * WX / 2, y0, 0.0, float(r.uniform(-35, 35))))
    used += 1
    tmp = MB()
    tmp.join(pool[used % 6], _bale_M(WX / 2 + H / 2 + float(r.uniform(0.2, 0.35)), float(r.uniform(-0.2, 0.2)) * DY, 0.0,
                                     90 + float(r.uniform(-12, 12)), side=True))
    for v in tmp.bm.verts:                                        # de canto: los popotes del lado de abajo se doblan contra el piso
        if v.co.z < 0.0018:
            v.co.z = 0.0018
    mb.join(tmp)
    return mb


def loose_hay(w=1.2, d=0.8, h=0.15, seed=0):
    """Paja suelta en el piso: montículo bajo de contorno irregular (ruido) con grumos, que muere en el piso con un borde
    hundido; encima, cientos de popotes acostados en todas direcciones que siguen la superficie (algunos arqueados) y otros
    regados por fuera del contorno. ≤ 4 000 triángulos."""
    r = rng(seed)
    sd = seed * 3.17 + 0.71
    mb = MB()
    na, nr = 30, 7
    lumps = [(float(r.uniform(-0.6, 0.6)), float(r.uniform(-0.6, 0.6)), float(r.uniform(0.12, 0.3)), float(r.uniform(0.15, 0.4)))
             for _ in range(5)]

    def Rr(a):
        c, s_ = math.cos(a), math.sin(a)
        return 1.0 + 0.2 * noise.noise(Vector((c * 1.3 + sd, s_ * 1.3, 0.5))) + 0.08 * noise.noise(Vector((c * 3 + sd, s_ * 3, 2.5)))

    def hgt(x, y):
        a = math.atan2(y / (d / 2), x / (w / 2))
        rho = math.hypot(x / (w / 2), y / (d / 2)) / Rr(a)
        if rho >= 1.0:
            return -0.004
        base = (1 - rho * rho) ** 1.9
        lu = sum(A * math.exp(-((x / (w / 2) - lx) ** 2 + (y / (d / 2) - ly) ** 2) / (rad * rad)) for (lx, ly, rad, A) in lumps)
        nz = 0.3 * noise.noise(Vector((x * 6 + sd, y * 6, 1.0))) + 0.18 * noise.noise(Vector((x * 16 + sd, y * 16, 3.0)))
        return h * base * (0.8 + lu + nz) - 0.004 * rho ** 8
    loops = [[Vector((0.0, 0.0, hgt(0.0, 0.0)))]]
    for j in range(1, nr + 1):
        rho = 1.0 - (1.0 - j / nr) ** 1.35
        ring = []
        for i in range(na):
            a = 2 * PI * i / na
            R_ = Rr(a) * (0.999 if j == nr else 1.0)
            x, y = w / 2 * rho * R_ * math.cos(a), d / 2 * rho * R_ * math.sin(a)
            ring.append(Vector((x, y, max(hgt(x, y), -0.004) if j < nr else -0.004)))
        loops.append(ring)
    skin(mb, loops, "hay", cap0=False, cap1=True)
    # popotes acostados sobre el montículo
    n = 200
    for k in range(n):
        out = k >= n - 30
        if out:
            a = float(r.uniform(0, 2 * PI))
            rho = float(r.uniform(1.0, 1.35))
        else:
            a = float(r.uniform(0, 2 * PI))
            rho = math.sqrt(float(r.uniform(0.0, 1.0))) * 0.95
        x0 = w / 2 * rho * Rr(a) * math.cos(a)
        y0 = d / 2 * rho * Rr(a) * math.sin(a)
        ang = float(r.uniform(0, 2 * PI))
        Ls = float(r.uniform(0.07, 0.24))
        bend = float(r.uniform(-0.5, 0.5))
        arch = float(r.uniform(0.0, 0.012)) if r.uniform() < 0.35 else 0.0
        rise = float(r.uniform(0.15, 0.6)) if (not out and r.uniform() < 0.16) else 0.0      # algunos se paran (pelusa del montón)
        pts = []
        for q in range(4):
            t = q / 3
            aa = ang + bend * t
            x = x0 + math.cos(aa) * Ls * (t - 0.5) * (1 - 0.4 * rise)
            y = y0 + math.sin(aa) * Ls * (t - 0.5) * (1 - 0.4 * rise)
            z = max(hgt(x, y), 0.0) + 0.0016 + arch * math.sin(PI * t) - (0.003 if q in (0, 3) and not out else 0.0)
            if rise:
                z = max(hgt(x0, y0), 0.0) - 0.004 + Ls * rise * t * (1.0 - 0.3 * t)
            pts.append(Vector((x, y, max(z, 0.0018))))
        dvec = (pts[-1] - pts[0]).normalized()
        n1, n2 = _perp(dvec)
        tw = float(r.uniform(0, 2 * PI))
        rr_ = float(r.uniform(0.0016, 0.0024))
        lp = []
        for i_, c in enumerate(pts[:-1]):
            f = 1.0 - 0.25 * i_ / 3
            lp.append([c + (n1 * math.cos(tw + 2 * PI * q / 3) + n2 * math.sin(tw + 2 * PI * q / 3) * 0.55) * rr_ * f for q in range(3)])
        skin(mb, lp + [[pts[-1]]], "hay", cap0=True, cap1=False)
    return mb


# ======================================================================================================== costales y tarima
def _sack_rings(r, lying, N=32):
    """Malla del costal (anillos horizontales de superelipse de -a..a en X y -b..b en Y, base en z = 0): devuelve los anillos
    (listas de Vector), las alturas t y la altura de la costura superior. De pie: base plana y 'panza' baja por el peso; acostado:
    las dos puntas cosidas (orejas) y el cuerpo aplastado."""
    Hs = 0.70
    if lying:
        T = [0.0, 0.03, 0.08, 0.15, 0.24, 0.34, 0.44, 0.54, 0.64, 0.72, 0.79, 0.85, 0.9, 0.94, 0.97, 1.0]
        A = [(0.0, 0.245), (0.06, 0.25), (0.2, 0.258), (0.5, 0.262), (0.7, 0.255), (0.86, 0.252), (1.0, 0.255)]
        Bb = [(0.0, 0.012), (0.03, 0.04), (0.08, 0.072), (0.18, 0.092), (0.5, 0.098), (0.72, 0.088), (0.85, 0.05), (0.95, 0.018),
              (1.0, 0.008)]
        Pp = [(0.0, 1.5), (0.1, 2.0), (0.2, 2.4), (0.75, 2.4), (0.9, 1.9), (1.0, 1.5)]
    else:
        T = [0.0, 0.01, 0.03, 0.06, 0.1, 0.15, 0.21, 0.27, 0.33, 0.39, 0.45, 0.51, 0.57, 0.63, 0.68, 0.73, 0.78, 0.83, 0.87, 0.91,
             0.945, 0.975, 1.0]
        A = [(0.0, 0.226), (0.01, 0.236), (0.04, 0.244), (0.17, 0.248), (0.35, 0.238), (0.55, 0.222), (0.7, 0.21), (0.82, 0.222),
             (0.93, 0.243), (1.0, 0.252)]
        Bb = [(0.0, 0.1), (0.01, 0.124), (0.04, 0.142), (0.15, 0.152), (0.35, 0.14), (0.55, 0.124), (0.7, 0.1), (0.82, 0.058),
              (0.93, 0.024), (1.0, 0.008)]
        Pp = [(0.0, 1.9), (0.06, 2.4), (0.65, 2.3), (0.86, 1.8), (1.0, 1.45)]

    def itp(tab, t):
        for (t0, v0), (t1, v1) in zip(tab[:-1], tab[1:]):
            if t <= t1:
                u = (t - t0) / max(t1 - t0, 1e-9)
                u = u * u * (3 - 2 * u)
                return v0 + (v1 - v0) * u
        return tab[-1][1]
    sd = float(r.uniform(0, 100))
    lean = (float(r.uniform(-0.035, 0.035)), float(r.uniform(-0.02, 0.02)))
    tilt = float(r.uniform(-0.03, 0.03))
    ph = [float(r.uniform(0, 2 * PI)) for _ in range(4)]
    rings = []
    for i, t in enumerate(T):
        a, b, p = itp(A, t), itp(Bb, t), itp(Pp, t)
        z = t * Hs
        ring = []
        for k in range(N):
            th = 2 * PI * k / N
            c, s_ = math.cos(th), math.sin(th)
            x = a * math.copysign(abs(c) ** (2 / p), c)
            y = b * math.copysign(abs(s_) ** (2 / p), s_)
            nx, ny = x / max(a, 1e-6), y / max(b, 1e-6)
            nl = math.hypot(nx, ny) or 1.0
            nx, ny = nx / nl, ny / nl
            # bultos del grano, pliegues que bajan de las orejas, arrugas de asentamiento abajo, trama (estrías de 0,6 mm)
            body = 0.011 * noise.noise(Vector((x * 4 + sd, y * 4, z * 3.5))) + 0.004 * noise.noise(Vector((x * 11 + sd, y * 11, z * 9)))
            fold = 0.0
            if t > 0.55:                                        # pliegues de tensión que bajan en diagonal desde las orejas
                g = _sstep_f(0.55, 0.85, t) * (1 - _sstep_f(0.95, 1.0, t))
                cr = (1 - abs(math.sin(2.5 * th + ph[0] + 7 * t))) ** 3
                cr2 = (1 - abs(math.sin(4.5 * th + ph[1] - 6 * t))) ** 3
                fold = g * (-0.012 * cr + 0.008 * cr2)
            if t < 0.32:                                        # arrugas de asentamiento: la tela se junta abajo
                fold += (1 - _sstep_f(0.04, 0.32, t)) * (0.005 * (1 - abs(math.sin(38 * z + 2 * th + ph[2]))) ** 2
                                                          - 0.003 * (1 - abs(math.sin(23 * z - 3 * th + ph[3]))) ** 3)
            weave = 0.0005 * (1 if i % 2 else -1) * (0.0 if t in (0.0, 1.0) else 1.0)
            dn = body + fold + weave
            if t in (0.0, 1.0):
                dn *= 0.3
            x += nx * dn
            y += ny * dn * (b / max(a, 1e-6) * 2 if b < 0.03 else 1.0)
            u = t * t
            ring.append(Vector((x + lean[0] * u, y + lean[1] * u, z + (tilt * x / 0.25 if t > 0.85 else 0.0) * _sstep_f(0.85, 1.0, t))))
        rings.append(ring)
    return rings, T, Hs


def _sstep_f(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _hem(mb, top, r, up, mat="burlap", h=0.026, thread="plastic"):
    """Dobladillo cosido del extremo del costal: banda plana doblada sobre el anillo `top` (lente), canto rolado, puntada de
    cadeneta en zigzag por las dos caras, hilos deshilachados en el canto y cabo colgando de una oreja."""
    N = len(top)
    c = sum(top, Vector()) / N
    up = Vector(up).normalized()
    hem_r = [[c + (v - c) * Vector((1.0, 0.55, 1.0)) + up * dz if False else v for v in top]]
    L1 = [c + (v - c) * 0.985 + up * (h * 0.5) for v in top]
    L2 = [c + (v - c) * 0.97 + up * h for v in top]
    for L_ in (L1, L2):                                         # banda: más delgada que el último anillo
        for v in L_:
            d = v - c
            side = d - up * d.dot(up)
            ax = Vector((1, 0, 0)) - up * up.x
            ax = ax.normalized() if ax.length > 1e-6 else Vector((0, 1, 0))
            across = side - ax * side.dot(ax)
            v -= across * 0.35
    cap = [c + up * (h + 0.004)]
    skin(mb, [top, L1, L2, cap], mat, cap0=False, cap1=False)
    del hem_r
    # puntada: por cada cara, una línea en zigzag a media altura del dobladillo
    xs_ = [v.x for v in top]
    ax = Vector((1, 0, 0))
    span = (max(xs_) - min(xs_)) * 0.42
    for sgn in (-1, 1):
        pts = []
        n = 26
        for k in range(n + 1):
            x = -span + 2 * span * k / n
            best = min(L1, key=lambda v: abs(v.x - c.x - x) + (0 if (v - c).dot(Vector((0, sgn, 0)) if abs(up.z) > 0.5 else up.cross(ax) * sgn) > 0 else 9))
            pts.append(best + up * (0.0025 if k % 2 else -0.0025))
        pts2 = []
        for p_ in pts:
            dv = p_ - c
            off = dv - up * dv.dot(up) - ax * (p_.x - c.x)
            off = off.normalized() if off.length > 1e-6 else Vector((0, sgn, 0))
            pts2.append(p_ + off * 0.0012)
        mb.tube([tuple(p_) for p_ in _dedupe([tuple(q) for q in pts2], 1e-4)], 0.0011, seg=3, mat=thread)
    for k in range(9):                                          # hilos deshilachados en el canto
        v = L2[int(r.integers(0, N))]
        d = (v - c)
        d = (d - up * d.dot(up)).normalized() if (d - up * d.dot(up)).length > 1e-6 else Vector((1, 0, 0))
        straw(mb, v - up * 0.003, (up * 0.8 + d * float(r.uniform(-0.3, 0.6))), float(r.uniform(0.012, 0.03)), 0.0008, r, mat=mat,
              droop=0.4, segs=1)
    ear = max(top, key=lambda v: v.x - c.x)
    straw(mb, ear + up * 0.012, (0.4, float(r.uniform(-0.3, 0.3)), -0.6), float(r.uniform(0.06, 0.1)), 0.0012, r, mat=thread,
          droop=1.0, segs=2)


def feed_sack(seed=0, lying=False):
    """Costal de alimento de yute/rafia (~0,45 × 0,25 × 0,70) lleno de grano: cuerpo blando subdividido que se asienta (panza
    baja, ligera inclinación, bultos del grano), hombros con pliegues que bajan de las orejas, costura superior con dobladillo
    y puntada de cadeneta, hilos deshilachados, cabo colgando, trama insinuada por estrías finas, franjas impresas (regiones de
    material, sin calcomanías) y etiqueta de papel cosida. lying=True: acostado, aplastado por su peso, ~0,70 a lo largo de Y.
    ≤ 3 000 triángulos."""
    r = rng(seed)
    mb = MB()
    rings, T, Hs = _sack_rings(r, lying)
    N = len(rings[0])
    stripe = ["sign_red", "paint_green", "plastic_blue"][int(r.integers(0, 3))]
    mats = []
    for i in range(len(rings) - 1):
        tm = (T[i] + T[i + 1]) / 2
        mats.append("burlap")
    V = [[mb.bm.verts.new(v) for v in ring] for ring in rings]
    for i in range(len(V) - 1):
        tm = (T[i] + T[i + 1]) / 2
        for k in range(N):
            th = 2 * PI * (k + 0.5) / N
            m = "burlap"
            front = math.sin(th) < -0.55
            if 0.3 < tm < 0.6 and front and abs(math.cos(th)) < 0.55:
                m = "paper"                                     # cartel impreso al frente
            elif (0.22 < tm < 0.26 or 0.64 < tm < 0.68) and math.sin(th) < 0:
                m = stripe                                      # franjas tejidas de color
            mb.face([V[i][k], V[i][(k + 1) % N], V[i + 1][(k + 1) % N], V[i + 1][k]], m)
    if lying:
        bot = rings[0]
        _hem(mb, list(reversed(bot)), r, (0, 0, -1))
    else:
        c0 = mb.bm.verts.new(sum(rings[0], Vector()) / N)
        for k in range(N):
            mb.face([c0, V[0][(k + 1) % N], V[0][k]], "burlap")
    _hem(mb, rings[-1], r, (0, 0, 1))
    # etiqueta de cartoncillo atrapada en la costura frontal: cuelga apoyada en el hombro, 2 mm separada de la tela
    if not lying or r.uniform() < 0.7:
        tree = BVHTree.FromBMesh(mb.bm)
        x0 = float(r.uniform(-0.1, 0.1))
        zt = Hs - 0.004
        zb = zt - 0.05

        def front_y(x, z):
            hit = tree.ray_cast(Vector((x, -1.0, z)), Vector((0, 1, 0)), 2.0)[0]
            return hit.y if hit is not None else -0.01
        yt, yb = front_y(x0, zt), front_y(x0, zb)
        for xx in (x0 - 0.035, x0 + 0.035):
            yb = min(yb, front_y(xx, zb))
        ang = math.degrees(math.atan2(yt - yb, zt - zb))
        tag = MB()
        bplate(tag, [(-0.035, -0.05), (0.035, -0.05), (0.035, 0.0), (-0.035, 0.0)], 0.0008, "paper", e=0.0002)
        label(tag, "FEED", 0.012, "sign_red", _T(0, -0.032, 0.0008), depth=0.0012, res=2, bold=True)
        mb.join(tag, _T(x0, min(yt, yb + (zt - zb) * math.tan(math.radians(ang))) - 0.0022, zt) @ _Rx(-ang)
                @ _Rz(float(r.uniform(-6, 6))) @ _Rx(90))
    if lying:
        mb.transform(_T(0, 0, 0) @ _Rx(-90))                      # eje largo a lo largo de -Y... base al frente
        bm = mb.bm
        zs = [v.co.z for v in bm.verts]
        ys = [v.co.y for v in bm.verts]
        zc = (min(zs) + max(zs)) / 2
        yc = (min(ys) + max(ys)) / 2
        for v in bm.verts:
            v.co.y -= yc
            v.co.z -= zc
            v.co.z *= 0.82                                     # se aplasta por su peso
        zmin = min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.z -= zmin
            if v.co.z < 0.03:                                  # panza contra el piso: parche de apoyo plano y ensanchado
                k_ = (0.03 - v.co.z) / 0.03
                v.co.z = 0.03 - (0.03 - v.co.z) * (1 - 0.85 * k_)
                v.co.x *= 1 + 0.03 * k_
        zmin = min(v.co.z for v in bm.verts)
        for v in bm.verts:
            v.co.z -= zmin
    return mb


def pallet(seed=0):
    """Tarima de madera de largueros (1,20 × 1,00 × 0,12): 3 largueros de 38 × 89 con muescas para montacargas de 4 entradas,
    7 tablas de cubierta superior (las de orilla más anchas) y 3 inferiores de 16 mm con cantos matados, clavadas (2 clavos
    por cruce), aristas irregulares, tablas combadas/torcidas, una astillada en la esquina y otra de reposición más oscura.
    ≤ 2 000 triángulos."""
    r = rng(seed)
    mb = MB()
    LX, LY = 1.20, 1.00
    tb, hs = 0.016, 0.089
    zs0, zs1 = tb, tb + hs
    ys = (-LY / 2 + 0.019 + 0.005, 0.0, LY / 2 - 0.019 - 0.005)
    out = [(-0.6, zs0), (-0.42, zs0), (-0.405, zs0 + 0.026), (-0.382, zs0 + 0.036), (-0.218, zs0 + 0.036), (-0.195, zs0 + 0.026),
           (-0.18, zs0), (0.18, zs0), (0.195, zs0 + 0.026), (0.218, zs0 + 0.036), (0.382, zs0 + 0.036), (0.405, zs0 + 0.026),
           (0.42, zs0), (0.6, zs0), (0.6, zs1), (-0.6, zs1)]
    for y in ys:
        o2 = [(x + float(r.uniform(-0.0015, 0.0015)), z + (float(r.uniform(-0.001, 0.001)) if 0 < z - zs0 < hs else 0.0)) for (x, z) in out]
        bplate(mb, o2, 0.038, ["wood", "wood_grey"][int(r.integers(0, 2))], M=_T(0, y + 0.019, 0) @ _Rx(90), e=0.003)
    top = [(-0.53, 0.14)] + [(-0.53 + 0.07 + 0.078 * 1 + 0.045 + k * 0.1685, 0.09) for k in range(5)] + [(0.53, 0.14)]
    dark = int(r.integers(0, 7))
    chip = int(r.integers(0, 7))
    for k, (x, w) in enumerate(top):
        x += float(r.uniform(-0.006, 0.006))
        mat = "wood_dark" if k == dark else ["wood", "wood", "wood_grey"][int(r.integers(0, 3))]

        def chipf(xx, py, pz, k=k):
            if k == chip and xx < 0.06 and py > 0 and pz > 0:   # esquina astillada
                return py - 0.012 * (1 - xx / 0.06), pz - 0.006 * (1 - xx / 0.06)
            return py, pz
        board(mb, (x, -LY / 2 - float(r.uniform(0, 0.006)), zs1 + tb / 2), (x, LY / 2 + float(r.uniform(0, 0.006)), zs1 + tb / 2), w, tb,
              mat, r, r=0.003, seg=2, warp=float(r.uniform(-0.003, 0.002)), twist=float(r.uniform(-1.5, 1.5)), rough=0.0008,
              deform=chipf)
        for y in ys:
            for dx in (-w * 0.28, w * 0.28):
                nail(mb, _T(x + dx + float(r.uniform(-0.006, 0.006)), y + float(r.uniform(-0.006, 0.006)), zs1 + tb) @ _Rz(float(r.uniform(0, 90))),
                     r=0.0042, seg=4, mat="metal_rust" if r.uniform() < 0.5 else "steel")
    for x in (-0.53, 0.0, 0.53):
        x += float(r.uniform(-0.004, 0.004))
        board(mb, (x, -LY / 2, tb / 2), (x, LY / 2, tb / 2), 0.14, tb, ["wood", "wood_grey"][int(r.integers(0, 2))], r, r=0.003, seg=2,
              warp=float(r.uniform(-0.002, 0.002)), twist=float(r.uniform(-1, 1)), rough=0.0008)
        for y in ys:
            for dx in (-0.04, 0.04):
                nail(mb, _T(x + dx, y + float(r.uniform(-0.006, 0.006)), 0.0) @ _Rx(180), r=0.0042, seg=4, mat="metal_rust")
    return mb


def sack_pile(n=6, seed=0):
    """Costales acostados estibados sobre una tarima: capas trabadas (3 a lo largo de Y, luego 2 cruzados a lo largo de X...),
    cada costal con su giro y desplazamiento; los de arriba se amoldan a los de abajo (cada vértice de la mitad inferior que
    quedaría dentro de lo ya estibado se apoya sobre esa superficie: la tela se acomoda en los valles), y la estiba se va
    cerrando hacia arriba. Incluye la tarima."""
    r = rng(seed)
    mb = MB()
    mb.join(pallet(seed=seed + 3))
    zdeck = 0.121
    placed = BVHTree.FromBMesh(mb.bm)
    patA = [(-0.4, 0.0, 0.0), (0.0, 0.0, 0.0), (0.4, 0.0, 0.0)]
    patB = [(0.0, -0.24, 90.0), (0.0, 0.24, 90.0)]
    layer = 0
    left = n
    z = zdeck
    while left > 0:
        pat = patA if layer % 2 == 0 else patB
        if left < len(pat):
            idx = sorted(r.choice(len(pat), left, replace=False))
            pat = [pat[int(i)] for i in idx]
            if len(pat) == 1:
                pat = [(float(r.uniform(-0.1, 0.1)), float(r.uniform(-0.1, 0.1)), pat[0][2])]
        for (x, y, yaw) in pat:
            s_ = feed_sack(seed=seed * 31 + layer * 7 + int(x * 10 + y * 10) + 50, lying=True)
            M = _T(x + float(r.uniform(-0.025, 0.025)), y + float(r.uniform(-0.025, 0.025)), z - 0.035 * (layer > 0)) @ \
                _Rz(yaw + float(r.uniform(-6, 6)) + (180.0 if r.uniform() < 0.5 else 0.0))
            s_.transform(M)
            zs = [v.co.z for v in s_.bm.verts]
            zlo, zhi = min(zs), max(zs)
            for v in s_.bm.verts:                               # se amolda a lo de abajo
                if v.co.z > zlo + (zhi - zlo) * 0.55:
                    continue
                hit = placed.ray_cast(Vector((v.co.x, v.co.y, zhi + 0.5)), Vector((0, 0, -1)), 2.0)[0]
                if hit is not None and v.co.z < hit.z + 0.0015:
                    lift = hit.z + 0.0015 - v.co.z
                    v.co.z += lift
            mb.join(s_)
            left -= 1
        placed = BVHTree.FromBMesh(mb.bm)
        layer += 1
        z += 0.13
    return mb
