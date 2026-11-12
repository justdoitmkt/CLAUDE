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


def straw(mb, p, d, L, r, rr, mat="hay", droop=0.25, segs=2, flat=0.55, curl=0.35, floor=0.0):
    """Popote suelto: prisma de 3 lados aplanado que se adelgaza a punta, doblado por la gravedad y con curvatura al azar.
    p = raíz (debe quedar 3-5 mm dentro de la superficie de la que sale)."""
    d = Vector(d).normalized()
    pts = [Vector(p)]
    side = Vector((float(rr.uniform(-1, 1)), float(rr.uniform(-1, 1)), float(rr.uniform(-1, 1)))) * curl
    for k in range(segs):
        d = (d + side * (1.0 / segs) + Vector((0, 0, -droop / segs))).normalized()
        q = pts[-1] + d * (L / segs)
        if floor is not None:
            q.z = max(q.z, floor + r * 1.1)                       # se apoya en el piso, no lo atraviesa
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
        T = [0.0, 0.025, 0.06, 0.11, 0.18, 0.26, 0.35, 0.44, 0.53, 0.62, 0.7, 0.77, 0.83, 0.88, 0.92, 0.96, 1.0]
        A = [(0.0, 0.24), (0.06, 0.245), (0.2, 0.252), (0.5, 0.255), (0.7, 0.25), (0.86, 0.248), (1.0, 0.255)]
        Bb = [(0.0, 0.012), (0.025, 0.06), (0.07, 0.098), (0.18, 0.118), (0.5, 0.122), (0.7, 0.11), (0.83, 0.07), (0.92, 0.03),
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
    # puntada: por cada cara (±Y), una línea en zigzag a media altura del dobladillo, interpolada sobre la banda
    xs_ = [v.x for v in top]
    span = (max(xs_) - min(xs_)) * 0.42
    for sgn in (-1, 1):
        S = sorted((v for v in L1 if (v.y - c.y) * sgn > 0), key=lambda v: v.x)
        pts = []
        n = 26
        for k in range(n + 1):
            x = c.x - span + 2 * span * k / n
            j = max(1, min(len(S) - 1, next((q for q in range(len(S)) if S[q].x >= x), len(S) - 1)))
            a_, b_ = S[j - 1], S[j]
            u = min(max((x - a_.x) / max(b_.x - a_.x, 1e-9), 0.0), 1.0)
            q = a_.lerp(b_, u)
            pts.append(q + up * (0.0025 if k % 2 else -0.0025) + Vector((0, sgn * 0.0012, 0)))
        mb.tube([tuple(p_) for p_ in _dedupe([tuple(q) for q in pts], 1e-4)], 0.0011, seg=3, mat=thread)
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
        ys = [v.co.y for v in bm.verts]
        y0, y1 = min(ys), max(ys)
        for v in bm.verts:
            v.co.z -= zmin
            # las puntas vacías (orejas y dobladillo) caen hacia el apoyo
            for (ye, sg) in ((y1, 1), (y0, -1)):
                u = (v.co.y - (ye - sg * 0.12)) * sg / 0.12
                if u > 0:
                    v.co.z -= (v.co.z - 0.012) * 0.75 * min(u, 1.0) ** 1.6
                    v.co.y -= sg * 0.02 * min(u, 1.0) ** 2
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
            own = BVHTree.FromBMesh(s_.bm)
            lifts = []
            for v in s_.bm.verts:                               # se amolda a lo de abajo: cada columna sube lo que la apoya
                sup = placed.ray_cast(Vector((v.co.x, v.co.y, zhi + 0.5)), Vector((0, 0, -1)), 3.0)[0]
                bot = own.ray_cast(Vector((v.co.x, v.co.y, zlo - 0.05)), Vector((0, 0, 1)), 3.0)[0]
                lifts.append(max(0.0, sup.z + 0.002 - bot.z) if (sup is not None and bot is not None) else 0.0)
            for v, lf in zip(s_.bm.verts, lifts):
                v.co.z += lf
            mb.join(s_)
            left -= 1
        placed = BVHTree.FromBMesh(mb.bm)
        layer += 1
        z += 0.13
    return mb


# ======================================================================================================== carretilla
def _tray_loop(z, wx, lf, lb, cy, n=48, p=4.2):
    """Lazo de la batea: superelipse en planta (medio ancho wx en X; frente lf hacia -Y, atrás lb hacia +Y)."""
    out = []
    for k in range(n):
        th = 2 * PI * (k + 0.5) / n
        c, s_ = math.cos(th), math.sin(th)
        x = wx * math.copysign(abs(c) ** (2 / p), c)
        y = cy + (lb if s_ > 0 else lf) * math.copysign(abs(s_) ** (2 / p), s_)
        out.append(Vector((x, y, z)))
    return out


def _tire_tread(mb, M, R, rt, n=48, m=12, mat="rubber"):
    """Llanta neumática: toro de radio R y sección rt aplanada en la banda, con tacos alternados (dibujo de chevrón)."""
    rings = []
    for i in range(n):
        a = 2 * PI * i / n
        ring = []
        for j in range(m):
            b = 2 * PI * j / m
            cb, sb = math.cos(b), math.sin(b)
            rr = rt
            w = 1.0 + 0.12 * max(cb, 0.0) ** 2                     # banda más ancha y plana
            if cb > 0.5 and ((i + (1 if sb > 0 else 0)) % 2 == 0):
                rr *= 1.06                                       # tacos alternados a cada lado del centro
            p = Vector(((R + rr * cb * 0.92) * math.cos(a), (R + rr * cb * 0.92) * math.sin(a), rr * sb * w))
            ring.append(mb.bm.verts.new(M @ p))
        rings.append(ring)
    for i in range(n):
        A, B = rings[i], rings[(i + 1) % n]
        for j in range(m):
            mb.face([A[j], A[(j + 1) % m], B[(j + 1) % m], B[j]], mat)


def wheelbarrow(seed=0):
    """Carretilla de obra/rancho (≈ 1,50 × 0,68 × 0,62; rueda al frente, -Y): batea de lámina de acero pintada (rojo, con el fondo
    interior pelado a óxido por el uso) de paredes inclinadas — el frente más tendido para vaciar —, con labio rolado y dos
    abolladuras; dos largueros de tubo Ø 32 con dobleces reales que forman la horquilla; travesaños de PTR bajo la batea con 4
    pernos de coche; patas de tubo con pie y riostra, travesaño entre patas; tirantes de solera del frente de la batea al eje;
    rueda neumática de 16" (llanta con tacos, rin de lámina estampado, maza con baleros, eje con tuercas y válvula); puños de
    hule con estrías. ≤ 8 000 triángulos."""
    r = rng(seed)
    mb = MB()
    paint = ["sign_red", "sign_red", "paint_green", "paint_yellow"][int(r.integers(0, 4))]
    zb = 0.312
    cy = 0.04
    t = 0.0022
    dents = [(Vector((float(r.uniform(-0.3, 0.3)), float(r.uniform(-0.4, 0.3)), float(r.uniform(0.4, 0.58)))), float(r.uniform(0.04, 0.07)),
              float(r.uniform(0.006, 0.012))) for _ in range(2)]

    def dims(z):
        u = (z - zb) / (0.615 - zb)
        return 0.21 + 0.13 * u, 0.15 + 0.38 * u, 0.22 + 0.22 * u
    rf = 0.045
    prof = []                                                    # (z, encogimiento en planta)
    for k in range(4):                                           # chaflán redondo del fondo
        a = PI / 2 * k / 3
        prof.append((zb + rf * (1 - math.cos(a)), rf * (1 - math.sin(a))))
    for z in (0.40, 0.48, 0.555, 0.605):
        prof.append((z, 0.0))
    outer = []
    for (z, sh) in prof:
        wx, lf, lb = dims(max(z, zb + rf))
        outer.append(_tray_loop(z, wx - sh, lf - sh, lb - sh, cy))
    # labio rolado: cordón alrededor del borde
    zt = 0.612
    wx, lf, lb = dims(zt)
    rim = []
    for ang in (-60, 0, 60, 120, 180, 240):
        a = math.radians(ang)
        dn = 0.0075 + 0.0085 * math.cos(a)
        rim.append(_tray_loop(zt + 0.004 + 0.0085 * math.sin(a), wx + dn - 0.002, lf + dn - 0.002, lb + dn - 0.002, cy))
    inner = []
    for (z, sh) in reversed(prof):
        wx, lf, lb = dims(max(z, zb + rf))
        inner.append(_tray_loop(z + t, wx - sh - t * 1.4, lf - sh - t * 1.4, lb - sh - t * 1.4, cy))
    loops = outer + rim + inner
    for L_ in loops:                                             # abolladuras y labio un poco vencido
        for v in L_:
            for (c, rad, dep) in dents:
                d2 = (v - c).length_squared
                if d2 < (rad * 2.5) ** 2:
                    pl = Vector((v.x, v.y - cy, 0.0))
                    pl = pl.normalized() if pl.length > 1e-6 else Vector((1, 0, 0))
                    v -= pl * dep * math.exp(-d2 / (rad * rad))
            if v.z > 0.58:
                v.z -= 0.006 * max(0.0, math.cos(math.atan2(v.y - cy, v.x) - 0.7)) ** 6
    V = [[mb.bm.verts.new(p) for p in L_] for L_ in loops]
    nL = len(V)
    n = len(V[0])
    n_out = len(outer)
    for i in range(nL - 1):
        for k in range(n):
            m = paint
            if i >= n_out + len(rim) - 1 + 2:                    # fondo interior gastado por la carga
                m = "metal_rust"
            mb.face([V[i][k], V[i][(k + 1) % n], V[i + 1][(k + 1) % n], V[i + 1][k]], m)
    mb.face(list(reversed(V[0])), paint)
    mb.face(V[-1], "metal_rust")
    # ---- largueros (horquilla) y travesaños
    rt = 0.016
    for sx in (-1, 1):
        P = [(sx * 0.285, 0.88, 0.52), (sx * 0.27, 0.62, 0.40), (sx * 0.252, 0.36, 0.276), (sx * 0.228, 0.12, 0.268),
             (sx * 0.195, -0.16, 0.268), (sx * 0.13, -0.40, 0.236), (sx * 0.084, -0.53, 0.205), (sx * 0.084, -0.57, 0.2)]
        mb.tube(_dedupe(fillet(P, 0.14, 3), 1e-4), rt, seg=8, mat="steel", caps=True)
        # oreja aplanada del larguero que abraza el eje
        bplate(mb, [(-0.035, -0.022), (0.03, -0.024), (0.045, 0.0), (0.03, 0.024), (-0.035, 0.022)], 0.005, "steel",
               M=_T(sx * (0.084 - 0.0025 * sx) - (0.0025 if sx > 0 else -0.0025) * 0 + (-0.0025 if sx > 0 else -0.0025), -0.585, 0.2)
               @ _Ry(90) @ _Rz(90), e=0.001)
        # puño de hule con estrías
        d = (Vector(P[0]) - Vector(P[1])).normalized()
        Mg = Matrix.Translation(Vector(P[0]) - d * 0.13) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4()
        gp = [(0.0185, 0.0), (0.0195, 0.004)]
        for k in range(6):
            gp += [(0.0195, 0.014 + k * 0.018), (0.0178, 0.02 + k * 0.018)]
        gp += [(0.0205, 0.125), (0.021, 0.134), (0.015, 0.142), (0.0, 0.143)]
        lathe(mb, gp, seg=12, mat="rubber", M=Mg, caps=False)
        # pata: tubo del larguero al piso con pie aplanado, riostra al larguero
        top = Vector((sx * 0.262, 0.47, 0.335))
        foot = Vector((sx * 0.29, 0.42, 0.022))
        mb.tube(_dedupe(fillet([tuple(top + Vector((0, 0, 0.004))), tuple(foot + Vector((0, 0.0, 0.03))), tuple(foot), tuple(foot + Vector((0, -0.07, 0)))],
                               0.03, 4), 1e-4), 0.0125, seg=8, mat="steel")
        lathe(mb, [(0.0, -0.022), (0.016, -0.022), (0.018, -0.012), (0.016, 0.0), (0.013, 0.012), (0.0, 0.013)], seg=8, mat="rubber",
              M=_T(foot.x, foot.y - 0.04, 0.022) @ _Rx(90))
        mid = foot.lerp(top, 0.45)
        mb.tube([tuple(mid), (sx * 0.226, 0.13, 0.262)], 0.009, seg=6, mat="steel")
        port.bolt(mb, _T(top.x + sx * 0.016, top.y, top.z) @ _Ry(90 * sx), d=0.008, stud=0.006, mat="steel")
        # tirante de solera del labio delantero al eje
        sweep_frame(mb, [(-0.012, -0.0022), (0.012, -0.0022), (0.012, 0.0022), (-0.012, 0.0022)],
                    fillet([(sx * 0.12, -0.49, 0.585), (sx * 0.112, -0.52, 0.45), (sx * 0.095, -0.575, 0.215)], 0.04, 4), "steel",
                    up=(1, 0, 0))
    mb.tube([(-0.29, 0.425, 0.09), (0.29, 0.425, 0.09)], 0.008, seg=6, mat="steel")
    for y in (-0.07, 0.21):
        xa = 0.21 if y < 0 else 0.245
        port.member(mb, (-xa - 0.04, y, zb - 0.0125), (xa + 0.04, y, zb - 0.0125), [(-0.0125, 0.0125, -0.0125, 0.0125)], "steel")
        for xb in (-0.12, 0.12):
            lathe(mb, [(0.0095, 0.0), (0.0085, 0.003), (0.004, 0.0048), (0.0, 0.005)], seg=8, mat="steel",
                  M=_T(xb, y, zb + t - 0.0003))                    # cabeza de coche dentro de la batea
            hexnut(mb, _T(xb, y, zb - 0.025) @ _Rx(180), s=0.013, h=0.007, mat="steel")
            lathe(mb, [(0.004, -0.004), (0.004, 0.0)], seg=6, mat="steel", M=_T(xb, y, zb - 0.032), caps=True)
    # ---- rueda neumática de 16"
    Mw = _T(0, -0.585, 0.1985) @ _Ry(90)
    _tire_tread(mb, Mw, 0.152, 0.047, n=54, m=12)
    rim_p = [(0.112, -0.034), (0.118, -0.04), (0.122, -0.036), (0.118, -0.028), (0.112, -0.02), (0.106, -0.008), (0.106, 0.008),
             (0.112, 0.02), (0.118, 0.028), (0.122, 0.036), (0.118, 0.04), (0.112, 0.034)]
    revolve(mb, rim_p, "steel", seg=26, M=Mw, caps=False)
    revolve(mb, [(0.112, 0.034), (0.09, 0.01), (0.05, 0.004), (0.035, 0.018), (0.035, -0.018), (0.05, -0.004), (0.09, -0.01),
                 (0.112, -0.034)], "steel", seg=26, M=Mw, closed=True)
    revolve(mb, [(0.0, -0.05), (0.02, -0.05), (0.022, -0.045), (0.022, 0.045), (0.02, 0.05), (0.0, 0.05)], "steel", seg=12, M=Mw)
    mb.cyl(Mw @ Vector((0, 0, -0.105)), Mw @ Vector((0, 0, 0.105)), 0.0065, seg=8, mat="steel")
    for sz in (-1, 1):
        hexnut(mb, Mw @ _T(0, 0, sz * 0.092) @ (_Rx(180) if sz < 0 else Matrix()), s=0.016, h=0.008, mat="steel")
    lathe(mb, [(0.0035, 0.0), (0.0035, 0.025), (0.004, 0.027), (0.0, 0.03)], seg=6, mat="rubber",
          M=Mw @ _Rz(40) @ _T(0.104, 0, 0.0) @ _Ry(90))
    return mb


# ======================================================================================================== herramientas de mano
def _handle(mb, z0, z1, r0, r1, rr, mat="wood", seg=14, knob=False):
    """Mango de madera torneado a lo largo de Z: ligera conicidad, ovalado por el uso (rmod), remate redondeado arriba."""
    ph = float(rr.uniform(0, 2 * PI))
    prof = []
    n = 6
    for k in range(n + 1):
        u = k / n
        prof.append((r0 + (r1 - r0) * u, z0 + (z1 - z0 - 0.012) * u))
    prof += [(r1 * 0.85, z1 - 0.004), (r1 * 0.45, z1), (0.0, z1 + 0.001)]
    if knob:
        prof = prof[:-3] + [(r1 * 1.15, z1 - 0.03), (r1 * 1.3, z1 - 0.012), (r1 * 0.9, z1), (0.0, z1 + 0.002)]
    revolve(mb, prof, mat, seg=seg, rmod=lambda a: 1.0 + 0.035 * math.cos(2 * a + ph) + 0.012 * math.cos(3 * a))


def _ferrule(mb, z0, z1, r0, r1, mat="metal_rust", seg=14, rivet=True):
    """Casquillo (virola) de lámina: cono con borde rolado arriba y remache pasante."""
    revolve(mb, [(r0 * 0.6, z0 - 0.01), (r0, z0), (r1, z1 - 0.006), (r1 + 0.0012, z1 - 0.003), (r1 + 0.0008, z1), (r1 - 0.001, z1 + 0.001)],
            mat, seg=seg, caps=False)
    if rivet:
        zr = z0 + (z1 - z0) * 0.62
        rr_ = r0 + (r1 - r0) * 0.62
        for s_ in (-1, 1):
            lathe(mb, [(0.0042, -0.0005), (0.0038, 0.0012), (0.002, 0.0022), (0.0, 0.0025)], seg=8, mat=mat,
                  M=_T(s_ * rr_, 0, zr) @ _Ry(90 * s_))


def pitchfork(seed=0):
    """Bieldo (horquilla de heno) de 3 dientes: dientes de acero redondo forjado que se afinan a punta y se curvan hacia el
    frente (-Y), los de afuera doblados en arco que se forjan en el puente; cuello, virola cónica con remaches y mango de
    fresno de 1,2 m ovalado por el uso con remate redondo. Origen: punta de los dientes en z = 0, herramienta vertical a lo
    largo de +Z (se recarga en el muro al colocarla). ≤ 1 500 triángulos."""
    r = rng(seed)
    mb = MB()
    metal = "metal_rust" if r.uniform() < 0.6 else "steel"
    dy = lambda z: -0.018 * math.sin(PI * min(z / 0.32, 1.0) * 0.85)  # noqa: E731  (comba hacia el frente)
    spread = float(r.uniform(-0.004, 0.004))
    for sx in (-1, 0, 1):
        if sx == 0:
            P = [(0.0, dy(z), z) for z in (0.0, 0.04, 0.09, 0.15, 0.21, 0.27, 0.33)]
        else:
            xt = sx * (0.088 + spread)
            P = _dedupe(fillet([(xt, dy(0.0), 0.0), (xt * 0.985, dy(0.12), 0.12), (xt * 0.95, dy(0.235), 0.235),
                                (sx * 0.004, dy(0.322), 0.322)], 0.07, 7), 1e-4)
        P = [Vector(p) for p in P]
        acc = [0.0]
        for i in range(1, len(P)):
            acc.append(acc[-1] + (P[i] - P[i - 1]).length)
        radii = [0.0007 + 0.0040 * min(a_ / 0.16, 1.0) ** 0.75 for a_ in acc]
        mb.tube([tuple(p) for p in P], 0.0045, seg=6, mat=metal, radii=radii, caps=True)
    # cuello forjado: abraza la unión de los tres dientes y sube adelgazándose hasta la virola
    revolve(mb, [(0.0, 0.296), (0.011, 0.303), (0.0145, 0.318), (0.012, 0.334), (0.0088, 0.352), (0.0095, 0.372), (0.0125, 0.386),
                 (0.0, 0.387)], metal, seg=12, M=_T(0, dy(0.33), 0) @ Matrix.Scale(1.0, 4) , caps=False,
            rmod=lambda a_: 1.0 + 0.25 * math.cos(a_) ** 2)
    _ferrule(mb, 0.385, 0.50, 0.0125, 0.0165, mat=metal, seg=14)
    _handle(mb, 0.495, 1.66, 0.0158, 0.0145, r, mat=["wood", "wood_grey", "wood_varnish"][int(r.integers(0, 3))])
    return mb


def shovel(seed=0):
    """Pala de punta redonda: hoja de lámina de 2 mm combada (cóncava al frente -Y) con punta redondeada, pisaderas dobladas
    hacia el frente en los hombros, lomo estampado al dorso que sube al cubo, cubo cónico con remaches y mango de madera de
    1,1 m. El filo de la punta brilla (gastado de cavar), el resto oxidado. Origen: punta de la hoja en z = 0, herramienta
    vertical a lo largo de +Z. ≤ 1 500 triángulos."""
    r = rng(seed)
    mb = MB()
    Lb, hw0, t = 0.30, 0.118, 0.002
    nu, nv = 10, 11

    def hw(v):
        return hw0 * (1 - (1 - min(v / 0.62, 1.0)) ** 2.2) ** 0.55

    def surf(u, v, side):
        z = Lb * v
        x = u * max(hw(v), 0.004)
        y = -0.026 * u * u - 0.012 * math.sin(PI * v * 0.9) + 0.006 * (1 - v)
        y += side * t / 2
        return Vector((x, y, z))
    us = [-1 + 2 * k / nu for k in range(nu + 1)]
    vs = [((k / nv) ** 0.85) for k in range(nv + 1)]
    F = [[mb.bm.verts.new(surf(u, v, -1)) for u in us] for v in vs]
    B = [[mb.bm.verts.new(surf(u, v, 1)) for u in us] for v in vs]
    for j in range(nv):
        for i in range(nu):
            m = "steel" if vs[j] < 0.28 else "metal_rust"
            mb.face([F[j][i], F[j + 1][i], F[j + 1][i + 1], F[j][i + 1]], m)
            mb.face([B[j][i], B[j][i + 1], B[j + 1][i + 1], B[j + 1][i]], "metal_rust")
    for j in range(nv):                                          # cantos laterales
        for i in (0, nu):
            a, b_ = (F[j][i], F[j + 1][i]), (B[j][i], B[j + 1][i])
            q = [a[0], b_[0], b_[1], a[1]]
            mb.face(q if i == 0 else list(reversed(q)), "steel" if vs[j] < 0.3 else "metal_rust")
    for i in range(nu):                                          # canto superior (hombros)
        mb.face([F[nv][i], F[nv][i + 1], B[nv][i + 1], B[nv][i]], "metal_rust")
    for i in range(nu):                                          # filo de la punta (fila v = 0 colapsa a la punta)
        mb.face([F[0][i + 1], B[0][i + 1], B[0][i], F[0][i]], "steel")
    # pisaderas: pestañas dobladas hacia el frente (-Y) en los hombros, de canto redondeado
    for sx in (-1, 1):
        xa, xb = sorted((sx * 0.03, sx * (hw0 - 0.003)))
        pts = [surf(x / hw0, 1.0, -1) + Vector((0, 0.0008, -0.0011)) for x in (xa, (xa + xb) / 2, xb)]
        sweep_frame(mb, [(0.0, -0.0011), (0.012, -0.0011), (0.0165, -0.0004), (0.0165, 0.0004), (0.012, 0.0011), (0.0, 0.0011)],
                    [tuple(p) for p in pts], "metal_rust", up=(0, 0, 1))
    # lomo estampado al dorso y cubo
    sp = [surf(0, v, 1) for v in (0.3, 0.55, 0.8, 0.97)]
    mb.tube([tuple(p + Vector((0, 0.0012, 0))) for p in sp], 0.006, seg=6, mat="metal_rust",
            radii=[0.0025, 0.0055, 0.0085, 0.011])
    top = surf(0, 1.0, 1)
    revolve(mb, [(0.012, top.z - 0.035), (0.0165, top.z), (0.0175, top.z + 0.05), (0.0172, top.z + 0.11), (0.0185, top.z + 0.115),
                 (0.0172, top.z + 0.118)], "metal_rust", seg=14, M=_T(0, top.y + 0.004, 0), caps=False)
    for s_ in (-1, 1):
        lathe(mb, [(0.0042, -0.0005), (0.0038, 0.0012), (0.002, 0.0022), (0.0, 0.0025)], seg=8, mat="metal_rust",
              M=_T(0, top.y + 0.004 + s_ * 0.0172, top.z + 0.07) @ _Rx(-90 * s_))
    _handle(mb, top.z + 0.112, top.z + 1.22, 0.0158, 0.0148, r, mat=["wood", "wood_grey", "wood_varnish"][int(r.integers(0, 3))])
    mb.transform(_T(0, -(top.y + 0.004), 0))                     # el mango queda sobre el eje Z
    return mb


# ======================================================================================================== bebedero, cubeta, tambo
def _stadium(L, W, n, amp=0.0, pitch=0.1, off=0.0):
    """Puntos (x, y, nx, ny) de un óvalo de extremos semicirculares (largo L en X, ancho W en Y) desplazado `off` hacia afuera,
    con corrugado senoidal de amplitud `amp` (n debe ser múltiplo de 4 por costilla)."""
    R = W / 2
    a = L / 2 - R
    per = 4 * a + 2 * PI * R
    out = []
    for k in range(n):
        s_ = per * k / n
        if s_ < 2 * a:
            x, y, nx, ny = -a + s_, -R, 0.0, -1.0
        elif s_ < 2 * a + PI * R:
            th = -PI / 2 + (s_ - 2 * a) / R
            x, y, nx, ny = a + R * math.cos(th), R * math.sin(th), math.cos(th), math.sin(th)
        elif s_ < 4 * a + PI * R:
            x, y, nx, ny = a - (s_ - 2 * a - PI * R), R, 0.0, 1.0
        else:
            th = PI / 2 + (s_ - 4 * a - PI * R) / R
            x, y, nx, ny = -a + R * math.cos(th), R * math.sin(th), math.cos(th), math.sin(th)
        d = off + amp * math.sin(2 * PI * k / 4)
        out.append((x + nx * d, y + ny * d, nx, ny))
    return out


def water_trough(L=1.8, seed=0):
    """Bebedero ovalado de lámina galvanizada (L × 0,60 × 0,60): pared corrugada vertical (costillas senoidales por dentro y
    por fuera), chimba inferior engargolada, cordón rolado en el borde, piso interior con sedimento, espejo de agua a 0,46 m
    que muere dentro del espesor de la pared, tapón de desagüe roscado con brida y cabeza cuadrada en un extremo, abolladura
    en el borde. ≤ 5 000 triángulos."""
    r = rng(seed)
    mb = MB()
    W = 0.60
    per = 2 * (L - W) + PI * W
    ribs = max(8, int(round(per / 0.105)))
    n = ribs * 4
    amp, t = 0.0055, 0.0012
    dent_k = int(r.integers(0, n))
    dent_d = float(r.uniform(0.008, 0.016))

    def loop(z, off, corr):
        pts = _stadium(L, W, n, amp if corr else 0.0, off=off)
        ring = []
        for k, (x, y, nx, ny) in enumerate(pts):
            dk = min(abs(k - dent_k), n - abs(k - dent_k))
            dd = dent_d * math.exp(-(dk / 5.0) ** 2) * max(0.0, (z - 0.35) / 0.25)
            ring.append(Vector((x - nx * dd, y - ny * dd, z)))
        return ring
    zt = 0.556
    loops = [loop(0.0, 0.006, False), loop(0.026, 0.0075, False), loop(0.034, 0.0, False), loop(0.06, 0.0, True), loop(0.53, 0.0, True),
             loop(zt, 0.0, False)]
    for ang in (-40, 40, 110, 180):
        a = math.radians(ang)
        loops.append(loop(zt + 0.009 + 0.0105 * math.sin(a), 0.0045 + 0.0105 * math.cos(a) - 0.006, False))
    loops += [loop(zt, -t, False), loop(0.53, -t, True), loop(0.06, -t, True), loop(0.042, -t, False)]
    V = [[mb.bm.verts.new(p) for p in L_] for L_ in loops]
    for i in range(len(V) - 1):
        for k in range(n):
            mb.face([V[i][k], V[i][(k + 1) % n], V[i + 1][(k + 1) % n], V[i + 1][k]], "roof_metal_light")
    mb.face(V[-1], "metal_rust")                                   # piso interior con sedimento
    zw = 0.46 + float(r.uniform(-0.03, 0.02))                      # espejo de agua (muere dentro de la pared)
    mb.poly([(p.x, p.y, zw) for p in loop(zw, -t / 2, True)], "glass")
    # tapón de desagüe en el extremo +X, sobre una cresta
    x0 = L / 2 + amp
    M = _T(x0, 0.0, 0.085) @ _Ry(90)
    revolve(mb, [(0.0, -0.004), (0.03, -0.004), (0.031, 0.0), (0.029, 0.003), (0.019, 0.004), (0.0, 0.004)], "roof_metal_light", seg=16,
            M=M)
    revolve(mb, [(0.0, 0.003), (0.017, 0.003), (0.017, 0.016), (0.0155, 0.018), (0.0, 0.018)], "steel", seg=6, M=M, phase=PI / 6)
    port.member(mb, M @ Vector((0, 0, 0.017)), M @ Vector((0, 0, 0.03)), [(-0.0065, 0.0065, -0.0065, 0.0065)], "steel")
    return mb


def bucket(seed=0):
    """Cubeta galvanizada de 12 L (Ø 0,30 arriba, 0,27 de alto): pared cónica con dos costillas estampadas, chimba inferior
    rolada con el fondo remetido, cordón de alambre en el labio, orejas remachadas, asa de alambre Ø 5 con ganchos en las
    orejas y agarradera de madera; asa abatida a un lado; abolladura. ≤ 1 500 triángulos."""
    r = rng(seed)
    mb = MB()
    H = 0.268
    rb, rt_ = 0.1195, 0.150
    rw = lambda z: rb + (rt_ - rb) * (z - 0.016) / (H - 0.016)  # noqa: E731
    prof = [(0.0, 0.011), (0.108, 0.011), (0.113, 0.004), (0.118, 0.0), (0.1215, 0.006), (rw(0.016), 0.016)]
    for zr in (0.075, 0.19):
        prof += [(rw(zr - 0.006), zr - 0.006), (rw(zr) + 0.0028, zr), (rw(zr + 0.006), zr + 0.006)]
    prof += [(rw(H - 0.008), H - 0.008), (rt_ + 0.0045, H - 0.004), (rt_ + 0.0045, H + 0.0015), (rt_ + 0.001, H + 0.004),
             (rt_ - 0.0035, H + 0.001), (rw(H - 0.012) - 0.0009, H - 0.012), (rw(0.1) - 0.0009, 0.1), (rb - 0.0009, 0.02),
             (0.115, 0.014), (0.0, 0.014)]
    dent_a = float(r.uniform(0, 2 * PI))
    rings = revolve(mb, prof, "roof_metal_light", seg=24)
    for ring, (rr_, z) in zip(rings, prof):
        if len(ring) == 1:
            continue
        for v in ring:
            a = math.atan2(v.co.y, v.co.x)
            da = math.atan2(math.sin(a - dent_a), math.cos(a - dent_a))
            k = math.exp(-(da / 0.35) ** 2) * math.exp(-((z - 0.13) / 0.06) ** 2) * 0.008
            v.co.x -= math.cos(a) * k
            v.co.y -= math.sin(a) * k
    # orejas remachadas y asa
    ang = float(r.uniform(55, 80)) * (1 if r.uniform() < 0.5 else -1)
    for sx in (-1, 1):
        zc = H - 0.03
        rr_ = rw(zc) + 0.0002
        slope = math.degrees(math.atan2(rt_ - rb, H - 0.016))
        Me = _T(sx * rr_, 0, zc) @ _Rz(90 if sx > 0 else -90) @ _Rx(90) @ _Rx(-slope)
        bplate(mb, [(-0.017, -0.02), (0.017, -0.02), (0.014, 0.012), (0.0, 0.02), (-0.014, 0.012)], 0.0015, "roof_metal_light", M=Me,
               e=0.0005)
        for dx in (-0.009, 0.009):
            lathe(mb, [(0.0028, 0.0), (0.0024, 0.0012), (0.0, 0.0018)], seg=6, mat="roof_metal_light", M=Me @ _T(dx, -0.011, 0.0013),
                  caps=False)
    zb = H - 0.022
    Mb = _T(0, 0, zb) @ _Rx(ang)
    Rb = rt_ + 0.011
    pts = [Mb @ Vector((-Rb * math.cos(PI * k / 16), 0.0, Rb * math.sin(PI * k / 16) * 0.95)) for k in range(17)]
    xin = rw(zb) + 0.0035
    path = [(-xin, 0.0, zb)] + [tuple(p) for p in pts] + [(xin, 0.0, zb)]
    mb.tube(_dedupe(path, 1e-4), 0.0025, seg=5, mat="steel")
    for sx in (-1, 1):                                             # remate del asa en la oreja
        lathe(mb, [(0.0045, 0.0), (0.0042, 0.0018), (0.0022, 0.003), (0.0, 0.0033)], seg=8, mat="steel",
              M=_T(sx * (xin + 0.0005), 0, zb) @ _Ry(90 * sx), caps=False)
    top = Mb @ Vector((0, 0, (rt_ + 0.011) * 0.95))
    Mg = _T(*top) @ _Rx(ang) @ _Ry(90)
    lathe(mb, [(0.0, -0.05), (0.0075, -0.05), (0.0095, -0.042), (0.0095, 0.042), (0.0075, 0.05), (0.0, 0.05)], seg=10, mat="wood_dark",
          M=Mg)
    return mb


def drum(seed=0):
    """Tambo de 200 L (Ø 0,58 × 0,88): cuerpo de lámina con dos aros de rodadura y dos costillas suaves, chimbas engargoladas
    arriba y abajo, tapas remetidas con nervadura, tapones roscados de 2" y 3/4" (uno con cabeza hexagonal y sello, el otro con
    tapa de rosca estriada), abolladuras en el cuerpo y en un borde. Pintura (azul/rojo/verde) u óxido según la semilla.
    ≤ 3 000 triángulos."""
    r = rng(seed)
    mb = MB()
    paint = ["metal_rust", "metal_rust", "plastic_blue", "sign_red", "paint_green"][int(r.integers(0, 5))]
    R = 0.286
    prof = [(0.0, 0.017), (0.2, 0.017), (0.205, 0.014), (0.268, 0.014), (0.276, 0.01), (0.281, 0.0), (0.29, 0.001), (0.2945, 0.01),
            (0.291, 0.022), (R, 0.03), (R, 0.11), (R + 0.002, 0.135), (R, 0.16), (R, 0.255), (R + 0.005, 0.275), (R + 0.011, 0.29),
            (R + 0.005, 0.305), (R, 0.325), (R, 0.4), (R, 0.47), (R, 0.55), (R + 0.005, 0.57), (R + 0.011, 0.585), (R + 0.005, 0.6),
            (R, 0.62), (R, 0.715), (R + 0.002, 0.74), (R, 0.765), (R, 0.85), (0.291, 0.858), (0.2945, 0.87), (0.29, 0.879), (0.281, 0.88),
            (0.276, 0.87), (0.268, 0.866), (0.205, 0.866), (0.2, 0.863), (0.0, 0.863)]
    mats = [("metal_rust" if (z0 < 0.03 or z0 > 0.85 or z1 > 0.855) else paint) for (_, z0), (_, z1) in zip(prof[:-1], prof[1:])]
    rings = revolve(mb, prof, mats, seg=36)
    dents = [(float(r.uniform(0, 2 * PI)), float(r.uniform(0.15, 0.7)), float(r.uniform(0.012, 0.028)), float(r.uniform(0.25, 0.45)))
             for _ in range(int(r.integers(1, 3)))]
    rim_a = float(r.uniform(0, 2 * PI))
    for ring, (rr_, z) in zip(rings, prof):
        if len(ring) == 1:
            continue
        for v in ring:
            a = math.atan2(v.co.y, v.co.x)
            k = 0.0
            for (da_, dz, dep, wa) in dents:
                da = math.atan2(math.sin(a - da_), math.cos(a - da_))
                k += dep * math.exp(-(da / wa) ** 2) * math.exp(-((z - dz) / 0.09) ** 2)
            if z > 0.84:                                           # borde golpeado
                da = math.atan2(math.sin(a - rim_a), math.cos(a - rim_a))
                k += 0.01 * math.exp(-(da / 0.18) ** 2)
                v.co.z -= 0.008 * math.exp(-(da / 0.18) ** 2)
            v.co.x -= math.cos(a) * k
            v.co.y -= math.sin(a) * k
    zl = 0.863
    for (x, y, rr_, hexa) in ((0.17, 0.0, 0.031, True), (-0.13, 0.11, 0.019, False)):
        lathe(mb, [(rr_ + 0.009, zl - 0.0004), (rr_ + 0.007, zl + 0.004), (rr_ + 0.001, zl + 0.006), (rr_, zl + 0.004)], seg=14,
              mat=paint if paint != "metal_rust" else "steel", M=_T(x, y, 0), caps=False)
        if hexa:
            revolve(mb, [(0.0, zl + 0.003), (rr_ * 0.95, zl + 0.003), (rr_ * 0.95, zl + 0.008), (rr_ * 0.7, zl + 0.009), (rr_ * 0.7, zl + 0.02),
                         (rr_ * 0.6, zl + 0.022), (0.0, zl + 0.022)], "steel", seg=6, M=_T(x, y, 0), phase=PI / 6)
        else:
            revolve(mb, [(0.0, zl + 0.003), (rr_, zl + 0.003), (rr_, zl + 0.013), (rr_ * 0.85, zl + 0.016), (0.0, zl + 0.016)], "plastic",
                    seg=16, M=_T(x, y, 0), rmod=lambda a: 1.0 - 0.06 * (0.5 + 0.5 * math.cos(12 * a)) ** 3)
    return mb


# ======================================================================================================== banco de trabajo
def _vise(mb, M, rr, open_=0.03, paint="plastic_blue"):
    """Tornillo de banco de 5": base giratoria con 3 orejas atornilladas, cuerpo fundido redondeado con yunque atrás, quijada
    fija y móvil con placas de acero estriadas, barra guía, husillo roscado con barra en T de remates esféricos.
    Local: apoyado en z = 0 (cubierta del banco), quijadas hacia -Y, la quijada fija en y = 0."""
    revolve(mb, [(0.0, 0.0), (0.075, 0.0), (0.077, 0.006), (0.074, 0.012), (0.06, 0.016), (0.0, 0.016)], paint, seg=20, M=M @ _T(0, 0.07, 0))
    for k in range(3):
        a = PI / 2 + 2 * PI * k / 3 + PI / 3
        c = Vector((math.cos(a) * 0.08, 0.07 + math.sin(a) * 0.08, 0.0))
        slab(mb, M @ _T(c.x, c.y, 0) @ _Rz(math.degrees(a)), 0.045, 0.03, 0.01, rc=0.013, re=0.003, mat=paint, nc=3, ne=1)
        hexnut(mb, M @ _T(c.x, c.y, 0.01), s=0.016, h=0.009, mat="steel")
    revolve(mb, [(0.0, 0.016), (0.05, 0.016), (0.052, 0.022), (0.048, 0.03), (0.0, 0.03)], paint, seg=20, M=M @ _T(0, 0.07, 0))
    slab(mb, M @ _T(0, 0.075, 0.028), 0.115, 0.2, 0.068, rc=0.02, re=0.012, mat=paint, nc=3, ne=3)          # cuerpo
    slab(mb, M @ _T(0, 0.135, 0.094), 0.07, 0.07, 0.018, rc=0.008, re=0.004, mat="steel", nc=2, ne=2)        # yunque
    slab(mb, M @ _T(0, -0.012, 0.028), 0.135, 0.05, 0.14, rc=0.012, re=0.008, mat=paint, nc=3, ne=2)        # quijada fija
    yo = -0.037 - 0.003
    ym = yo - open_
    for (yy, sgn) in ((yo + 0.0015, 1), (ym - 0.0015, -1)):                                            # placas estriadas
        slab(mb, M @ _T(0, yy - 0.003 * sgn, 0.12), 0.13, 0.006, 0.046, rc=0.001, re=0.0008, mat="steel", nc=1, ne=1)
        for k in range(9):
            x = -0.058 + k * 0.0145
            mb.box((x - 0.0012, yy - 0.0065 * sgn - 0.0006, 0.122), (x + 0.0012, yy - 0.0065 * sgn + 0.0006, 0.164), "steel", bevel=0.0,
                   m=M)
    slab(mb, M @ _T(0, ym - 0.0065 - 0.025, 0.07), 0.135, 0.05, 0.098, rc=0.012, re=0.008, mat=paint, nc=3, ne=2)   # quijada móvil
    slab(mb, M @ _T(0, ym - 0.04, 0.03), 0.06, 0.07, 0.042, rc=0.008, re=0.006, mat=paint, nc=2, ne=2)
    port.member(mb, M @ Vector((0, ym - 0.06, 0.062)), M @ Vector((0, 0.17, 0.062)), [(-0.022, 0.022, -0.016, 0.016)], "steel")
    zs = 0.088
    prof = [(0.0, 0.0)]
    for k in range(14):
        prof += [(0.0105, 0.004 + k * 0.006), (0.0085, 0.007 + k * 0.006)]
    prof += [(0.0105, 0.09), (0.0, 0.09)]
    revolve(mb, prof, "steel", seg=8, M=M @ _T(0, ym - 0.055, zs) @ _Rx(90))
    revolve(mb, [(0.0, 0.0), (0.018, 0.0), (0.02, 0.008), (0.018, 0.03), (0.0, 0.03)], "steel", seg=12, M=M @ _T(0, ym - 0.05, zs) @ _Rx(90))
    hx = float(rr.uniform(-0.09, 0.09))
    mb.cyl(M @ Vector((hx - 0.1, ym - 0.068, zs)), M @ Vector((hx + 0.1, ym - 0.068, zs)), 0.0055, seg=8, mat="steel")
    for s_ in (-1, 1):
        revolve(mb, [(0.0, -0.011), (0.008, -0.009), (0.0115, 0.0), (0.008, 0.009), (0.0, 0.011)], "steel", seg=10,
                M=M @ _T(hx + s_ * 0.105, ym - 0.068, zs) @ _Ry(90))


def _hammer(mb, M, rr):
    """Martillo de uña acostado: mango de madera ovalado, cabeza con cara torneada, ojo con cuña y uña curva partida."""
    revolve(mb, [(0.0, 0.0), (0.012, 0.0), (0.0135, 0.02), (0.0125, 0.12), (0.011, 0.22), (0.0105, 0.285), (0.008, 0.3), (0.0, 0.3)],
            "wood_varnish", seg=10, M=M @ _T(0, 0, 0.0125) @ _Ry(90), rmod=lambda a: 1.0 - 0.18 * math.sin(a) ** 2)
    Mh = M @ _T(0.3, 0, 0.0125)
    revolve(mb, [(0.0, -0.05), (0.0125, -0.05), (0.0145, -0.046), (0.0145, -0.03), (0.0115, -0.02), (0.0115, 0.0)], "steel", seg=12,
            M=Mh @ _Rx(90), caps=False)
    slab(mb, Mh @ _T(0, 0.01, -0.012) @ _Rz(0), 0.03, 0.04, 0.024, rc=0.006, re=0.003, mat="steel", nc=2, ne=1)
    for s_ in (-1, 1):
        prof = [(-0.004, -0.0055), (0.004, -0.0055), (0.004, 0.0055), (-0.004, 0.0055)]
        pts = [Mh @ Vector((s_ * 0.0045, 0.028, 0.0)), Mh @ Vector((s_ * 0.006, 0.05, -0.004)), Mh @ Vector((s_ * 0.008, 0.068, -0.012)),
               Mh @ Vector((s_ * 0.0095, 0.08, -0.024))]
        sweep_frame(mb, prof, [tuple(p) for p in pts], "steel", up=tuple(M.to_3x3() @ Vector((0, 0, 1))),
                    scale=lambda t: (1.0 - 0.35 * t, 1.0 - 0.55 * t))
    mb.box((0.29, -0.003, 0.0125 + 0.0105), (0.31, 0.003, 0.0125 + 0.0115), "steel", bevel=0.0, m=M)


def _wrench(mb, M, L=0.2):
    """Llave combinada: caña de sección ovalada, boca abierta a 15° y estría de 12 puntas."""
    sweep_frame(mb, [(-0.009, -0.0035), (0.009, -0.0035), (0.01, 0.0), (0.009, 0.0035), (-0.009, 0.0035), (-0.01, 0.0)],
                [tuple(M @ Vector((x, 0, 0.0045))) for x in (0.02, L / 2, L - 0.02)], "steel", up=tuple(M.to_3x3() @ Vector((0, 0, 1))),
                scale=lambda t: (1.0 + 0.25 * abs(2 * t - 1), 1.0))
    Mo = M @ _T(L, 0, 0.0) @ _Rz(15)
    R_, hs = 0.019, 0.0065
    a0 = math.degrees(math.asin(0.0109 / R_))
    o = [(R_ * math.cos(math.radians(a)), R_ * math.sin(math.radians(a))) for a in np.linspace(a0, 360 - a0, 15)]
    xt = o[-1][0]
    o += [(xt, -hs), (0.0, -hs), (-hs * 0.7071, -hs * 0.7071), (-hs, 0.0), (-hs * 0.7071, hs * 0.7071), (0.0, hs), (xt, hs)]
    bplate(mb, o, 0.006, "steel", M=Mo @ _T(0.0, 0, 0.0015), e=0.0008)
    Mb = M @ _T(0.0, 0, 0.0)
    revolve(mb, [(0.0075, 0.0015), (0.0135, 0.0015), (0.0145, 0.0045), (0.0135, 0.0085), (0.0075, 0.0085), (0.0072, 0.005)], "steel",
            seg=12, M=Mb, closed=True)


def _saw(mb, M, rr):
    """Serrucho: hoja de acero de 2 mm con dientes triscados en el canto, lomo recto, puño cerrado de madera (aro en D) con
    tres tornillos de latón."""
    Lb = 0.5
    pts = [(0.0, 0.0)]
    n = 60
    for k in range(n):
        x = Lb * (k + 0.6) / n
        pts += [(x, 0.0042 if k % 2 else 0.0036), (Lb * (k + 1) / n, 0.0)]
    pts = [(x, y) for (x, y) in pts]
    outline = pts + [(Lb, 0.072), (0.0, 0.118)]
    bplate(mb, [(x, y) for (x, y) in outline], 0.0012, "steel", M=M @ _T(0, 0, 0.0109), e=0.0)
    Mh = M @ _T(-0.0, 0.07, 0.0115)
    loop = [(-0.115, -0.065), (-0.135, -0.04), (-0.14, 0.0), (-0.13, 0.035), (-0.1, 0.055), (-0.04, 0.06), (0.012, 0.045), (0.02, 0.0),
            (0.015, -0.045), (-0.01, -0.068), (-0.06, -0.072)]
    loop_tube(mb, [Mh @ Vector((x, y, 0.0)) for (x, y, _z) in fillet([(x, y, 0) for (x, y) in loop] + [(loop[0][0], loop[0][1], 0)], 0.02, 2)[:-1]],
              0.0115, seg=6, mat="wood", normal=tuple(M.to_3x3() @ Vector((0, 0, 1))))
    for (x, y) in ((0.006, -0.02), (0.006, 0.025), (-0.03, 0.045)):
        lathe(mb, [(0.0055, 0.0), (0.005, 0.0016), (0.0, 0.002)], seg=8, mat="paint_yellow", M=Mh @ _T(x, y, 0.0115 - 0.0007), caps=False)
    del rr


def _pliers(mb, M, rr):
    """Pinzas de electricista: dos brazos que se cruzan en el perno, quijadas estriadas, mangos con forro de plástico."""
    a = math.radians(float(rr.uniform(4, 10)))
    for s_ in (-1, 1):
        z = 0.0042 if s_ > 0 else 0.0115
        pts = [(-0.065, s_ * 0.0015, z), (-0.03, s_ * 0.002, z), (0.0, 0.0, z), (0.04, -s_ * 0.012, z), (0.1, -s_ * 0.02, z), (0.13, -s_ * 0.019, z)]
        R = Matrix.Rotation(-s_ * a, 4, "Z")
        P = [tuple(M @ R @ Vector(p)) for p in fillet(pts, 0.03, 3)]
        sweep_frame(mb, [(-0.006, -0.0035), (0.006, -0.0035), (0.0065, 0.0), (0.006, 0.0035), (-0.006, 0.0035), (-0.0065, 0.0)], P[:6],
                    "steel", up=tuple(M.to_3x3() @ Vector((0, 0, 1))), scale=lambda t: (0.55 + 0.45 * t, 1.0))
        g = [tuple(M @ R @ Vector(p)) for p in [(0.035, -s_ * 0.011, z), (0.08, -s_ * 0.017, z), (0.128, -s_ * 0.019, z)]]
        mb.tube(g, 0.0062, seg=7, mat="sign_red" if s_ > 0 else "sign_red")
    revolve(mb, [(0.0, 0.0), (0.0065, 0.0), (0.0065, 0.0162), (0.0045, 0.0168), (0.0, 0.017)], "steel", seg=10, M=M)


def _screwdriver(mb, M, rr, L=0.22, flat=True):
    """Desarmador: mango con estrías y tapa, virola, vástago redondo y punta plana o de cruz. Acostado sobre su costado."""
    rh = 0.0145
    Ma = M @ _T(0, 0, rh) @ _Ry(90)
    revolve(mb, [(0.0, 0.0), (0.011, 0.0), (rh, 0.01), (rh, 0.07), (0.012, 0.09), (0.008, 0.1), (0.0, 0.1)],
            ["plastic_blue", "sign_red", "paint_yellow"][int(rr.integers(0, 3))], seg=12, M=Ma,
            rmod=lambda a: 1.0 - 0.07 * (0.5 + 0.5 * math.cos(6 * a)) ** 4)
    revolve(mb, [(0.0035, 0.1), (0.0035, L - 0.012), (0.0028, L - 0.006), (0.0, L)], "steel", seg=6, M=Ma)
    if flat:
        mb.box((-0.0045, -0.0008, L - 0.012), (0.0045, 0.0008, L + 0.002), "steel", bevel=0.0004, m=Ma)


def workbench(w=2.0, seed=0):
    """Banco de trabajo pesado: cubierta de 3 tablones de 5 cm con juntas, cantos golpeados y marcas, 4 patas de 4×4, faldones
    de 2×6 con pernos de coche, travesaños bajos y repisa de tablas; tornillo de banco de 5" atornillado al frente; encima
    martillo de uña, llave combinada, serrucho, pinzas, dos desarmadores, aceitera de bomba, lata de café con clavos (y unos
    regados) y un trapo rojo colgando del canto. Frente -Y. ≤ 15 000 triángulos."""
    r = rng(seed)
    mb = MB()
    D, H, tt = 0.72, 0.9, 0.05
    xl = w / 2 - 0.13
    # ---- cubierta
    pw = (D - 0.008) / 3
    for k in range(3):
        y = -D / 2 + pw * (k + 0.5) + 0.004 * k
        dents = [(float(r.uniform(-w / 2, w / 2)), float(r.uniform(0.004, 0.012))) for _ in range(4)]

        def deform(x, py, pz, k=k, dents=dents):
            if k == 0 and py < -pw * 0.3 and pz > 0:              # canto frontal golpeado
                for (dx, dd) in dents:
                    pz -= dd * math.exp(-((x - (dx + w / 2)) / 0.04) ** 2)
            return py, pz
        board(mb, (-w / 2 - float(r.uniform(0, 0.01)), y, H - tt / 2), (w / 2 + float(r.uniform(0, 0.01)), y, H - tt / 2), pw, tt,
              ["wood", "wood_grey", "wood"][k], r, r=0.005, seg=10, warp=float(r.uniform(-0.002, 0.002)), rough=0.0012, deform=deform)
    # ---- patas, faldones, travesaños, repisa
    for sx in (-1, 1):
        for sy in (-1, 1):
            board(mb, (sx * xl, sy * 0.27, 0.0), (sx * xl, sy * 0.27, H - tt - 0.001), 0.09, 0.09, "wood", r, r=0.006, up=(0, 1, 0),
                  seg=3, rough=0.0015)
    for sy in (-1, 1):
        y = sy * (0.27 + 0.045 + 0.019)
        board(mb, (-w / 2 + 0.07, y, H - tt - 0.07), (w / 2 - 0.07, y, H - tt - 0.07), 0.038, 0.14, "wood", r, r=0.004, seg=4, rough=0.001)
        for sx in (-1, 1):
            for dz in (-0.035, 0.035):
                lathe(mb, [(0.011, -0.0003), (0.0105, 0.002), (0.008, 0.0045), (0.004, 0.006), (0.0, 0.0063)], seg=8, mat="metal_rust",
                      M=_T(sx * xl, y + sy * 0.019, H - tt - 0.07 + dz) @ _Rx(-90 * sy), caps=False)
    for sx in (-1, 1):
        x = sx * (xl + 0.045 + 0.019)
        board(mb, (x, -0.27 - 0.045, H - tt - 0.07), (x, 0.27 + 0.045, H - tt - 0.07), 0.038, 0.14, "wood", r, r=0.004, up=(0, 0, 1),
              seg=2, rough=0.001)
        for sy in (-1, 1):
            for dz in (-0.035, 0.035):
                lathe(mb, [(0.011, -0.0003), (0.0105, 0.002), (0.008, 0.0045), (0.004, 0.006), (0.0, 0.0063)], seg=8, mat="metal_rust",
                      M=_T(x + sx * 0.019, sy * 0.27, H - tt - 0.07 + dz) @ _Ry(90 * sx), caps=False)
        board(mb, (sx * xl, -0.228, 0.215), (sx * xl, 0.228, 0.215), 0.06, 0.089, "wood", r, r=0.004, seg=2, rough=0.001)
    for k, y in enumerate((-0.15, 0.0, 0.15)):
        board(mb, (-xl - 0.03, y, 0.2725), (xl + 0.03, y, 0.2725), 0.14, 0.025, ["wood_grey", "wood", "wood_grey"][k], r, r=0.003,
              seg=4, warp=float(r.uniform(-0.004, 0.0)), rough=0.001)
        for sx in (-1, 1):
            for dy in (-0.04, 0.04):
                nail(mb, _T(sx * xl + float(r.uniform(-0.01, 0.01)), y + dy, 0.285), r=0.0045, seg=5, mat="metal_rust")
    # ---- tornillo de banco al frente izquierdo
    _vise(mb, _T(-w / 2 + 0.32, -D / 2 + 0.02, H), r, open_=float(r.uniform(0.015, 0.05)),
          paint=["plastic_blue", "paint_green", "paint_green"][int(r.integers(0, 3))])
    # ---- herramientas sobre la cubierta
    _hammer(mb, _T(-0.12, -0.16, H) @ _Rz(float(r.uniform(-25, 5))) @ _Rx(-90) @ _T(0, -0.0125, 0) @ _Rx(90), r)
    _wrench(mb, _T(0.18, -0.24, H) @ _Rz(float(r.uniform(10, 50))), )
    _saw(mb, _T(0.15, -0.02, H) @ _Rz(float(r.uniform(-12, 12)) + 180) @ _Ry(1.3), r)
    _pliers(mb, _T(-0.38, 0.12, H) @ _Rz(float(r.uniform(0, 360))), r)
    _screwdriver(mb, _T(0.5, -0.2, H) @ _Rz(float(r.uniform(70, 110))), r)
    _screwdriver(mb, _T(0.56, -0.16, H) @ _Rz(float(r.uniform(60, 100))), r, L=0.18)
    # aceitera de bomba
    Mo = _T(-0.6 + w * 0.0, 0.2, H)
    revolve(mb, [(0.0, 0.0), (0.046, 0.0), (0.05, 0.004), (0.05, 0.05), (0.045, 0.062), (0.03, 0.072), (0.016, 0.076), (0.0, 0.076)],
            "paint_yellow", seg=18, M=Mo)
    revolve(mb, [(0.0, 0.074), (0.016, 0.074), (0.016, 0.082), (0.012, 0.086), (0.0, 0.086)], "steel", seg=10, M=Mo)
    mb.tube([tuple(Mo @ Vector(p)) for p in [(0.0, 0.0, 0.084), (0.04, 0.0, 0.12), (0.12, 0.0, 0.2), (0.17, 0.0, 0.245)]], 0.006, seg=6,
            mat="steel", radii=[0.006, 0.005, 0.0035, 0.002])
    mb.tube([tuple(Mo @ Vector(p)) for p in [(-0.01, 0.0, 0.08), (-0.03, 0.0, 0.1), (-0.06, 0.0, 0.105)]], 0.003, seg=5, mat="steel")
    revolve(mb, [(0.0, 0.0), (0.009, 0.0), (0.009, 0.006), (0.0, 0.007)], "steel", seg=8, M=Mo @ _T(-0.062, 0, 0.102) @ _Ry(-80))
    # lata de café con clavos
    Mc = _T(0.72 * w / 2, 0.18, H)
    cr, ch = 0.052, 0.125
    cprof = [(0.0, 0.004), (cr - 0.004, 0.004), (cr - 0.002, 0.0), (cr + 0.0015, 0.002), (cr + 0.0015, 0.009)]
    for zr in (0.035, 0.06, 0.085):
        cprof += [(cr, zr - 0.004), (cr + 0.0015, zr), (cr, zr + 0.004)]
    cprof += [(cr + 0.0015, ch - 0.006), (cr + 0.003, ch - 0.002), (cr + 0.0018, ch + 0.001), (cr - 0.0012, ch - 0.001), (cr - 0.0012, 0.01),
              (0.0, 0.01)]
    revolve(mb, cprof, ["steel"] * 5 + ["sign_white"] * 9 + ["steel"] * 6, seg=20, M=Mc)
    zn = ch - 0.03
    revolve(mb, [(0.0, zn + 0.008), (cr * 0.5, zn + 0.004), (cr - 0.0013, zn - 0.004), (cr - 0.0013, zn - 0.006)], "metal_rust", seg=16, M=Mc,
            caps=False, rmod=lambda a: 1.0)
    for k in range(34):
        a = float(r.uniform(0, 2 * PI))
        rad = math.sqrt(float(r.uniform(0, 1))) * (cr - 0.008)
        base = Mc @ Vector((rad * math.cos(a), rad * math.sin(a), zn - 0.01))
        d = Vector((float(r.uniform(-0.6, 0.6)), float(r.uniform(-0.6, 0.6)), 1.0)).normalized()
        if k % 3 == 0:
            d = Vector((d.x * 2.2, d.y * 2.2, 0.25)).normalized()
        Ln = float(r.uniform(0.035, 0.065))
        tip = base + d * Ln
        mb.cyl(base, tip, 0.0013, seg=4, mat="steel", caps=False)
        q = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
        revolve(mb, [(0.0, 0.0), (0.0038, 0.0), (0.0035, 0.0012), (0.0, 0.0014)], "steel", seg=6, M=Matrix.Translation(tip) @ q)
    for k in range(5):                                           # clavos regados en la cubierta
        p0 = Mc @ Vector((float(r.uniform(-0.14, 0.14)), float(r.uniform(-0.16, -0.07)), 0.0014))
        d = Vector((math.cos(k * 1.7 + 0.3), math.sin(k * 1.7 + 0.3), 0.0))
        mb.cyl(p0, p0 + d * 0.06, 0.0013, seg=4, mat="steel", caps=False)
        revolve(mb, [(0.0, 0.0), (0.0038, 0.0), (0.0035, 0.0012), (0.0, 0.0014)], "steel", seg=6,
                M=Matrix.Translation(p0 + d * 0.06 + Vector((0, 0, 0.0024))) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4() @ _T(0, 0, -0.0))
    # trapo rojo: sobre la cubierta y colgando del canto frontal, con pliegues
    _rag(mb, Vector((0.45, -D / 2, H)), r)
    return mb


def _rag(mb, edge, rr, size=(0.36, 0.44), n=(16, 22), t=0.0025, mat="sign_red"):
    """Trapo de algodón: hoja de espesor real (dos caras y canto) arrugada sobre la cubierta, que dobla sobre el canto del banco
    y cuelga por el frente con pliegues que se abren hacia abajo, puntas que caen más y dobladillo disparejo."""
    sx_, sy_ = size
    nx, ny = n
    sd = float(rr.uniform(0, 50))
    R = 0.0065                                                   # radio del canto del banco al que abraza
    hang = sy_ * 0.5
    pts = np.zeros((ny + 1, nx + 1, 3))
    for j in range(ny + 1):
        v = j / ny                                               # 0 = punta colgante, 1 = punta sobre la cubierta
        for i in range(nx + 1):
            u = i / nx
            x = (u - 0.5) * sx_
            s_ = (v - 0.5) * sy_ * 2 * (0.5 if v >= 0.5 else 1.0)  # longitud de arco desde el canto (+ hacia atrás)
            if s_ >= 0:
                k = s_ / (sy_ * 0.5)
                cr = 0.016 * max(0.0, noise.noise(Vector((u * 3.5 + sd, v * 3.5, 2.0)))) + \
                    0.01 * (1 - abs(math.sin(PI * (u * 2.2 + 0.7 * v) + sd))) ** 3
                y = edge.y + R + s_ * (1 - 0.25 * k) + 0.006 * noise.noise(Vector((u * 3, v * 3 + sd, 1.0)))
                z = edge.z + t / 2 + 0.0004 + cr * min(k * 3, 1.0)
                x *= 1 - 0.18 * k * (0.5 + 0.5 * math.sin(4 * u + sd))
            else:
                a = min(-s_ / R, PI / 2)
                if -s_ <= R * PI / 2:
                    y = edge.y + R - (R + t / 2 + 0.0016) * math.sin(a)
                    z = edge.z - R + (R + t / 2 + 0.0016) * math.cos(a)
                else:
                    drop = (-s_ - R * PI / 2) * (1 + 0.35 * (2 * u - 1) ** 2) + 0.02 * noise.noise(Vector((u * 5 + sd, 0.5, 3.0))) * (1 - v * 2)
                    g = min(drop / hang, 1.0) ** 0.8
                    pleat = 0.011 * (0.5 + 0.5 * math.sin(2 * PI * u * 2.6 + sd + 1.5 * g)) + \
                        0.005 * (0.5 + 0.5 * math.sin(2 * PI * u * 5.3 + 2 * sd))
                    y = edge.y - t / 2 - 0.0016 - pleat * g - 0.012 * g * g
                    z = edge.z - R - drop
                    x *= 1 - 0.08 * g
            pts[j, i] = (x + edge.x, y, z)
    N = _grid_normals_np(pts)
    top = pts + N * t / 2
    bot = pts - N * t / 2
    from kit.softgoods import _grid_to_mb
    _grid_to_mb(mb, Matrix(), top, mat)
    _grid_to_mb(mb, Matrix(), bot[:, ::-1], mat)
    ring = [(j, 0) for j in range(ny + 1)] + [(ny, i) for i in range(1, nx + 1)] + [(j, nx) for j in range(ny - 1, -1, -1)] + \
           [(0, i) for i in range(nx - 1, 0, -1)]
    for k in range(len(ring)):
        a_, b_ = ring[k], ring[(k + 1) % len(ring)]
        mb.poly([tuple(top[a_]), tuple(top[b_]), tuple(bot[b_]), tuple(bot[a_])], mat)


def _grid_normals_np(P):
    N = np.cross(np.gradient(P, axis=1), np.gradient(P, axis=0))
    return N / np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-12)


# ======================================================================================================== escalera, polipasto, cuerda, foco
def ladder(h=3.2, seed=0):
    """Escalera de mano de madera: largueros de 38 × 89 aserrados (cantos matados, aristas irregulares, ligera comba), que
    cierran un poco hacia arriba; peldaños redondos Ø 32 a cada 30 cm que atraviesan los largueros con espiga y cuña a la vista
    por fuera, desgastados arriba por el uso; dos tensores de varilla con rondana y tuerca bajo los peldaños 2 y n-1; pies
    cortados al sesgo. Vertical (se inclina al colocarla). ≤ 2 000 triángulos."""
    r = rng(seed)
    mb = MB()
    wb, wt = 0.44, 0.36
    rt, rd = 0.038, 0.089
    xs = lambda z: (wb + (wt - wb) * z / h) / 2  # noqa: E731  (medio ancho interior)
    for sx in (-1, 1):
        board(mb, (sx * (xs(0) + rt / 2), 0.0, 0.0), (sx * (xs(h) + rt / 2), 0.0, h), rt, rd, ["wood", "wood_grey"][int(r.integers(0, 2))], r,
              r=0.005, up=(0, 1, 0), seg=6, warp=float(r.uniform(-0.006, 0.006)), rough=0.0015, square=8.0)
    n = int((h - 0.15) / 0.3)
    for k in range(1, n + 1):
        z = 0.3 * k
        if z > h - 0.12:
            break
        xi = xs(z)
        xo = xi + rt + 0.004
        prof = [(0.0, -xo), (0.0135, -xo), (0.0135, -xi + 0.002), (0.016, -xi - 0.008), (0.016, xi + 0.008), (0.0135, xi - 0.002),
                (0.0135, xo), (0.0, xo)]
        revolve(mb, prof, "wood_dark" if k % 4 == 0 else "wood", seg=8, M=_T(0, 0, z) @ _Ry(90),
                rmod=lambda a: 1.0 - 0.09 * max(0.0, math.cos(a)) ** 6)            # huella gastada arriba
        for sx in (-1, 1):                                          # cuña clavada en la espiga, asoma 1,5 mm
            xa_, xb_ = sorted((sx * (xo - 0.006), sx * (xo + 0.0015)))
            mb.box((xa_, -0.0105, -0.0016), (xb_, 0.0105, 0.0016), "wood_dark", bevel=0.0,
                   m=_T(0, 0, z) @ _Rx(float(r.uniform(-12, 12))))
        if k in (2, n - 1):
            zr = z - 0.03
            xr = xs(zr) + rt
            mb.cyl((-xr - 0.012, 0, zr), (xr + 0.012, 0, zr), 0.0045, seg=6, mat="metal_rust")
            for sx in (-1, 1):
                lathe(mb, [(0.016, 0.0), (0.016, 0.002)], seg=10, mat="metal_rust", M=_T(sx * xr, 0, zr) @ _Ry(90 * sx))
                hexnut(mb, _T(sx * (xr + 0.002), 0, zr) @ _Ry(90 * sx), s=0.012, h=0.007, mat="metal_rust")
    return mb


def hoist(drop=2.0, seed=0):
    """Polipasto de una garrucha colgado de la viga: placa con 4 pijas y armella forjada; motón de dos cachetes de lámina
    con separadores remachados, garrucha con garganta, perno con tuercas, gancho giratorio arriba y gaza abajo; cuerda de
    3 cabos que abraza la garrucha y baja `drop` m con gancho de carga en gaza empalmada (lado de carga) y remate con
    falcaceado (lado de tiro). Origen: cara inferior de la viga; cuelga hacia -Z. ≤ 3 000 triángulos."""
    r = rng(seed)
    mb = MB()
    # placa y armella
    slab(mb, _T(0, 0, -0.008), 0.11, 0.09, 0.008, rc=0.008, re=0.002, mat="metal_rust", nc=2, ne=1)
    for (x, y) in ((-0.04, -0.03), (0.04, -0.03), (-0.04, 0.03), (0.04, 0.03)):
        hexnut(mb, _T(x, y, -0.008) @ _Rx(180), s=0.013, h=0.007, mat="metal_rust")
    revolve(mb, [(0.0, -0.008), (0.016, -0.008), (0.012, -0.014), (0.009, -0.03), (0.0, -0.031)], "metal_rust", seg=10)
    eye_c = Vector((0, 0, -0.052))
    loop_tube(mb, [eye_c + Vector((0.021 * math.cos(2 * PI * k / 14), 0.0, 0.021 * math.sin(2 * PI * k / 14))) for k in range(14)],
              0.0065, seg=6, mat="metal_rust", normal=(0, 1, 0))
    # gancho giratorio del motón enganchado en la armella
    hk = [(0.0, 0.0, -0.064), (0.014, 0.0, -0.062), (0.022, 0.0, -0.05), (0.02, 0.0, -0.036), (0.008, 0.0, -0.028), (-0.008, 0.0, -0.03),
          (-0.02, 0.0, -0.042), (-0.026, 0.0, -0.066), (-0.02, 0.0, -0.09), (0.0, 0.0, -0.1)]
    hk = [(x, y + 0.0, z - 0.011) for (x, y, z) in hk]
    hk = [(x, y, z) for (x, y, z) in hk]
    mb.tube(_dedupe(fillet(hk, 0.008, 2), 1e-4), 0.006, seg=6, mat="steel",
            radii=None)
    zb = -0.11
    revolve(mb, [(0.0, zb - 0.002), (0.012, zb - 0.002), (0.012, zb + 0.004), (0.009, zb + 0.008), (0.0, zb + 0.008)], "steel", seg=10)
    revolve(mb, [(0.0, zb - 0.03), (0.018, zb - 0.03), (0.02, zb - 0.024), (0.02, zb - 0.008), (0.016, zb - 0.002), (0.0, zb - 0.002)], "steel", seg=12)
    # motón: cachetes, garrucha, perno, separadores, gaza inferior
    Rs = 0.06
    zc = zb - 0.03 - Rs - 0.012
    outline = []
    for k in range(20):
        a = 2 * PI * k / 20
        rx = Rs + 0.016
        rz = Rs + 0.02 + (0.012 if math.sin(a) > 0 else 0.004) * abs(math.sin(a))
        outline.append((rx * math.cos(a), rz * math.sin(a)))
    for sy in (-1, 1):
        bplate(mb, outline, 0.005, "paint_yellow", M=_T(0, sy * 0.021 + (0.005 if sy < 0 else 0.0) * 0 - (0.0 if sy > 0 else 0.005) + 0.0, zc)
               @ _Rx(-90) @ _T(0, 0, 0) if sy > 0 else _T(0, -0.021, zc) @ _Rx(-90) @ _T(0, 0, -0.005), e=0.0015)
    revolve(mb, [(0.012, -0.016), (Rs, -0.016), (Rs + 0.002, -0.013), (Rs - 0.006, -0.006), (Rs - 0.01, 0.0), (Rs - 0.006, 0.006),
                 (Rs + 0.002, 0.013), (Rs, 0.016), (0.012, 0.016)], "steel", seg=18, M=_T(0, 0, zc) @ _Rx(90), caps=False)
    revolve(mb, [(0.0, -0.016), (0.012, -0.016), (0.012, 0.016), (0.0, 0.016)], "steel", seg=10, M=_T(0, 0, zc) @ _Rx(90))
    mb.cyl((0, -0.034, zc), (0, 0.034, zc), 0.0075, seg=8, mat="steel")
    for sy in (-1, 1):
        hexnut(mb, _T(0, sy * 0.026, zc) @ _Rx(-90 * sy), s=0.019, h=0.009, mat="steel")
    for (x, z) in ((0.0, zc + Rs + 0.014), (0.0, zc - Rs - 0.012)):
        mb.cyl((x, -0.026, z), (x, 0.026, z), 0.0055, seg=8, mat="steel")
        for sy in (-1, 1):
            lathe(mb, [(0.0085, 0.0), (0.0075, 0.002), (0.0, 0.003)], seg=8, mat="steel", M=_T(x, sy * 0.026, z) @ _Rx(-90 * sy), caps=False)
    # cuerda: abraza la garrucha y baja en dos ramales
    rr_ = 0.0085
    Rg = Rs - 0.01 + rr_
    wrap = [(Rg * math.cos(a), 0.0, zc + Rg * math.sin(a)) for a in np.linspace(0, PI, 13)]
    sway = [float(r.uniform(-0.01, 0.01)) for _ in range(4)]
    zl = -drop
    left = [(-Rg, 0.0, zc - 0.08)] + [(-Rg - 0.004 + sway[0] * u, sway[1] * u, zc + (zl + 0.16 - zc) * u) for u in (0.33, 0.66, 1.0)]
    zr_ = -drop + 0.28 + float(r.uniform(-0.05, 0.05))
    right = [(Rg + 0.004 + sway[2] * u, sway[3] * u, zc + (zr_ - zc) * u) for u in (1.0, 0.66, 0.33)] + [(Rg, 0.0, zc - 0.08)]
    path = right + [(Rg, 0.0, zc)] + wrap[1:-1] + [(-Rg, 0.0, zc)] + left
    pts = []
    for (a_, b_) in zip(path[:-1], path[1:]):
        A, B = Vector(a_), Vector(b_)
        n = max(1, int((B - A).length / (0.018 if (A - Vector((0, 0, zc))).length < 0.12 else 0.2)))
        for k in range(n):
            pts.append(A.lerp(B, k / n))
    pts.append(Vector(path[-1]))
    _rope_fixed(mb, pts, rr_, "burlap")
    # remate falcaceado del lado de tiro y gaza con gancho del lado de carga
    end = Vector(right[0])
    lathe(mb, [(rr_ * 1.12, -0.03), (rr_ * 1.12, 0.0)], seg=6, mat="cable", M=_T(end.x, end.y, end.z + 0.004), caps=False)
    lo = Vector(left[-1])
    eye = [lo + Vector((0.02 * math.sin(2 * PI * k / 12), 0.0, -0.045 + 0.045 * math.cos(2 * PI * k / 12))) for k in range(12)]
    loop_tube(mb, eye, rr_ * 0.9, seg=5, mat="burlap", normal=(0, 1, 0))
    lathe(mb, [(0.0, -0.002), (rr_ * 1.25, 0.0), (rr_ * 1.35, 0.04), (rr_ * 1.1, 0.09), (rr_, 0.1)], seg=6, mat="burlap",
          M=_T(lo.x, lo.y, lo.z - 0.002), caps=False)
    hz = lo.z - 0.09
    loop_tube(mb, [Vector((lo.x + 0.016 * math.cos(2 * PI * k / 10), lo.y + 0.016 * math.sin(2 * PI * k / 10), hz)) for k in range(10)],
              0.005, seg=5, mat="steel", normal=(0, 0, 1))
    gh = [(0.0, 0.0, hz - 0.012), (0.0, 0.0, hz - 0.05), (0.004, 0.0, hz - 0.085), (0.028, 0.0, hz - 0.1), (0.045, 0.0, hz - 0.085),
          (0.047, 0.0, hz - 0.06), (0.04, 0.0, hz - 0.048)]
    mb.tube([(x + lo.x, y + lo.y, z) for (x, y, z) in fillet(gh, 0.015, 3)], 0.007, seg=6, mat="steel",
            radii=None)
    return mb


def _rope_fixed(mb, pts, r, mat, seg=6, dphi=0.7, depth=0.16):
    """Cuerda de 3 cabos sobre puntos ya muestreados: la sección de 3 lóbulos gira un ángulo fijo por anillo (sin aliasing
    donde el muestreo es ralo: ahí el torcido se alarga)."""
    P = [Vector(p) for p in pts]
    n = len(P)
    T = [(P[min(i + 1, n - 1)] - P[max(i - 1, 0)]).normalized() for i in range(n)]
    ref = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
    N = (ref - T[0] * ref.dot(T[0])).normalized()
    rings = []
    for i in range(n):
        if i:
            N = (N - T[i] * N.dot(T[i])).normalized()
        B = T[i].cross(N)
        ph = dphi * i
        rings.append([P[i] + (N * math.cos(2 * PI * k / seg) + B * math.sin(2 * PI * k / seg)) *
                      r * (1 - depth * (0.5 - 0.5 * math.cos(3 * (2 * PI * k / seg - ph)))) for k in range(seg)])
    loft_rings(mb, rings, mat)


def rope_coil(seed=0):
    """Rollo de cuerda colgado de una estaca de madera en el muro: 7 vueltas en gota que caen por su peso, apretadas en el
    cuello por 3 vueltas del chicote y con la punta colgando. Origen: estaca en la cara del muro (y = 0), el rollo hacia -Y.
    ≤ 2 000 triángulos."""
    r = rng(seed)
    mb = MB()
    revolve(mb, [(0.0, 0.0), (0.017, 0.0), (0.016, 0.06), (0.015, 0.1), (0.016, 0.115), (0.013, 0.13), (0.0, 0.132)], "wood_dark", seg=10,
            M=_T(0, 0.0, 0.0) @ _Rx(90 - 8))
    rr_ = 0.0078
    nl = 5
    peg_dir = (_Rx(90 - 8).to_3x3() @ Vector((0, 0, 1)))
    ys = []
    zneck = -0.085
    path = []
    for i in range(nl):                                          # una sola cuerda: cada vuelta sigue en la siguiente
        yp = 0.03 + i * 2.05 * rr_
        top = peg_dir * yp / abs(peg_dir.y) + Vector((0, 0, 0.0155 + rr_))
        ys.append(top.y)
        Wd = float(r.uniform(0.12, 0.155))
        Hd = float(r.uniform(0.46, 0.53))
        sk = float(r.uniform(-0.025, 0.025))
        yaw = float(r.uniform(-0.12, 0.12))

        def wfun(u):
            if u < 0.18:
                return 0.024 + 0.004 * math.cos(PI * u / 0.18)
            if u < 0.78:
                return 0.024 + (Wd - 0.024) * _sstep_f(0.18, 0.62, u)
            return Wd * math.sqrt(max(0.0, 1 - ((u - 0.78) / 0.22) ** 2)) * 0.97 + 0.03 * (1 - (u - 0.78) / 0.22)
        us = [0.04, 0.1, 0.17, 0.25, 0.35, 0.47, 0.6, 0.72, 0.83, 0.92, 0.975]
        right = []
        for u in us:
            z = top.z - Hd * u
            if u < 0.1:                                            # pasa por encima de la estaca
                z = top.z - 0.02 * (1 - math.cos(PI / 2 * u / 0.1)) - 0.004
            right.append((wfun(u), z, u))
        dy = 2.05 * rr_ * abs(1 / peg_dir.y) * peg_dir.y           # avance a lo largo de la estaca en una vuelta
        loop = [Vector((0.0, top.y, top.z + 0.003))]
        for (w_, z, u) in right:
            loop.append(Vector((w_ + sk * u * u, top.y + yaw * w_ * u + dy * 0.25 * u, z)))
        loop.append(Vector((sk, top.y + dy * 0.5, top.z - Hd)))
        for (w_, z, u) in reversed(right):
            loop.append(Vector((-w_ + sk * u * u, top.y - yaw * w_ * u + dy * (1 - 0.25 * u) * 0.0 + dy * (0.75 + 0.25 * (1 - u)) * 0.0
                                + dy * (1.0 - 0.5 * u), z)))
        path += loop
    path.append(path[-1] + Vector((0.0, 0.0, -0.05)))
    # amarre: el chicote baja por el frente, da tres vueltas al cuello del rollo y cuelga
    ymid = (ys[0] + ys[-1]) / 2
    ry = (ys[0] - ys[-1]) / 2 + 2.3 * rr_
    rx = 0.024 + 2.3 * rr_
    for k in range(1, 28):
        a = 2 * PI * k / 9 - PI / 2
        path.append(Vector((rx * math.cos(a), ymid + ry * math.sin(a), zneck - 0.035 - 0.017 * k / 9)))
    path += [path[-1] + Vector((0.012, -0.006, -0.05)), path[-1] + Vector((0.02, -0.008, -0.13)), path[-1] + Vector((0.026, -0.01, -0.24))]
    pts = path[-1:]
    _rope_fixed(mb, _dedupe([tuple(p) for p in path], 1e-4), rr_, "burlap", seg=6, dphi=0.9)
    lathe(mb, [(rr_ * 1.1, 0.0), (rr_ * 1.1, 0.025)], seg=5, mat="cable", M=_T(*pts[-1]) @ _T(0, 0, 0.0), caps=False)
    for k in range(3):
        straw(mb, pts[-1] + Vector((0, 0, 0.004)), (float(r.uniform(-0.4, 0.4)), float(r.uniform(-0.4, 0.4)), -1.0),
              float(r.uniform(0.02, 0.035)), 0.0022, r, mat="burlap", droop=0.3, segs=1, floor=None)
    return mb


def bare_bulb(drop=0.6, seed=0):
    """Foco desnudo colgante: roseta de porcelana atornillada al plafón, cordón de tela con nudo de electricista, socket de
    porcelana sin apagador con tornillos de terminal, foco A19 de vidrio con base roscada de aluminio, contacto y filamento
    (ámbar) en sus soportes. Origen: plafón; cuelga hacia -Z. ≤ 800 triángulos."""
    r = rng(seed)
    mb = MB()
    revolve(mb, [(0.0, -0.022), (0.012, -0.022), (0.03, -0.016), (0.036, -0.006), (0.036, 0.0), (0.0, 0.0)], "plastic", seg=10)
    for s_ in (-1, 1):
        lathe(mb, [(0.004, -0.0003), (0.0035, 0.0014), (0.0, 0.0018)], seg=6, mat="steel", M=_T(s_ * 0.024, 0, -0.0112) @ _Ry(180 + s_ * 50),
              caps=False)
    zs = -drop
    sw = float(r.uniform(-0.01, 0.01))
    cord = [(0.0, 0.0, -0.02), (0.0, 0.0, -0.08), (sw * 0.5, 0.0, (zs + 0.06) * 0.6), (sw, 0.0, zs + 0.09), (sw, 0.0, zs + 0.06)]
    mb.tube(cord, 0.0032, seg=5, mat="cable")
    revolve(mb, [(0.0, -0.012), (0.0055, -0.009), (0.0065, 0.0), (0.0055, 0.008), (0.0, 0.011)], "cable", seg=6, M=_T(sw, 0, zs + 0.068))
    Ms = _T(sw, 0, zs)
    revolve(mb, [(0.0, 0.062), (0.008, 0.062), (0.016, 0.058), (0.019, 0.05), (0.021, 0.035), (0.023, 0.03), (0.023, 0.006),
                 (0.0215, 0.0), (0.0175, 0.0)], "plastic", seg=10, M=Ms, caps=False)
    for s_ in (-1, 1):
        lathe(mb, [(0.0035, -0.0003), (0.0032, 0.0012), (0.0, 0.0016)], seg=6, mat="steel", M=Ms @ _T(s_ * 0.0222, 0, 0.022) @ _Ry(90 * s_),
              caps=False)
    revolve(mb, [(0.0175, 0.0), (0.0175, -0.002), (0.0132, -0.004), (0.0139, -0.008), (0.0132, -0.012), (0.0139, -0.016), (0.0128, -0.021),
                 (0.009, -0.024), (0.0, -0.026)], "aluminium", seg=10, M=Ms, caps=False)
    revolve(mb, [(0.0128, -0.021), (0.015, -0.028), (0.025, -0.045), (0.03, -0.07), (0.029, -0.09), (0.024, -0.104), (0.014, -0.112),
                 (0.0, -0.114)], "glass", seg=12, M=Ms, caps=False)
    for s_ in (-1, 1):
        mb.cyl(Ms @ Vector((s_ * 0.002, 0, -0.03)), Ms @ Vector((s_ * 0.007, 0, -0.068)), 0.0006, seg=3, mat="steel", caps=False)
    mb.tube([tuple(Ms @ Vector(p)) for p in [(-0.007, 0, -0.068), (-0.003, 0, -0.072), (0.003, 0, -0.072), (0.007, 0, -0.068)]], 0.0009,
            seg=3, mat="amber")
    return mb


# ======================================================================================================== gabinete metálico
def _door_panel(mb, x0, x1, z0, z1, y, depth, rr, mat="paint_green", nx=6, nz=14, dents=(), rust_z=0.0, re=0.006):
    """Hoja de puerta de lámina: cara frontal en rejilla (para abolladuras) con canto doblado redondeado de radio `re` que
    regresa `depth` hacia +Y. dents: [(x, z, radio, profundidad)]. Las caras bajo rust_z llevan óxido (pintura caída)."""
    xs = [x0 + re + (x1 - x0 - 2 * re) * i / nx for i in range(nx + 1)]
    zs = [z0 + re + (z1 - z0 - 2 * re) * j / nz for j in range(nz + 1)]

    def dy(x, z):
        d = 0.0
        for (dx, dz, rad, dep) in dents:
            d += dep * math.exp(-((x - dx) ** 2 + (z - dz) ** 2) / (rad * rad))
        return d
    F = [[mb.bm.verts.new((x, y + dy(x, z) + float(rr.uniform(-0.0003, 0.0003)), z)) for x in xs] for z in zs]
    for j in range(nz):
        for i in range(nx):
            m = "metal_rust" if zs[j] < rust_z and (i + j) % 3 else mat
            mb.face([F[j][i], F[j][i + 1], F[j + 1][i + 1], F[j + 1][i]], m)
    ring = [F[0][i] for i in range(nx + 1)] + [F[j][nx] for j in range(1, nz + 1)] + [F[nz][i] for i in range(nx - 1, -1, -1)] + \
           [F[j][0] for j in range(nz - 1, 0, -1)]
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    loops = [ring]
    for (k, (a, b_)) in enumerate(((0.55, 0.15), (0.95, 0.6), (1.0, 1.0))):
        L_ = []
        for v in ring:
            ox = (1 if v.co.x > cx else -1) * (re * a if abs(v.co.x - cx) > (x1 - x0) / 2 - re * 1.5 else 0.0)
            oz = (1 if v.co.z > cz else -1) * (re * a if abs(v.co.z - cz) > (z1 - z0) / 2 - re * 1.5 else 0.0)
            L_.append(mb.bm.verts.new((v.co.x + ox, y + re * b_ if k < 2 else y + depth, v.co.z + oz)))
        loops.append(L_)
    n = len(ring)
    for A, B in zip(loops[:-1], loops[1:]):
        for k in range(n):
            mb.face([A[k], B[k], B[(k + 1) % n], A[(k + 1) % n]], mat)


def _louver(mb, x, z, w, y, mat):
    """Persiana estampada en la lámina: capucha que sale 6 mm con la boca hacia abajo (oscura)."""
    rings = []
    for (u, s_) in ((-0.5, 0.06), (-0.44, 0.8), (-0.3, 1.0), (0.3, 1.0), (0.44, 0.8), (0.5, 0.06)):
        prof = [(0.0004, -0.0005), (-0.0062, 0.0005), (-0.0052, 0.007), (0.0004, 0.0125)]
        rings.append([Vector((x + u * w, y + py * s_, z + pz * (0.4 + 0.6 * s_))) for (py, pz) in prof])
    R = [[mb.bm.verts.new(p) for p in ring] for ring in rings]
    for i in range(len(R) - 1):
        for j in range(4):
            jj = (j + 1) % 4
            mb.face([R[i][j], R[i][jj], R[i + 1][jj], R[i + 1][j]], "cable" if j == 0 else mat)
    mb.face(list(reversed(R[0])), mat)
    mb.face(R[-1], mat)


def metal_cabinet(seed=0):
    """Gabinete viejo de lámina de dos puertas (0,91 × 0,46 × 1,83): cuerpo con cantos doblados redondeados, zoclo remetido,
    tapa con ceja; dos hojas con holgura de 3 mm, abolladas (rejilla deformada), con óxido abajo donde se cayó la pintura,
    dos grupos de 5 persianas estampadas por hoja, 3 bisagras de barril por hoja, manija de palanca cromada con portacandado
    y candado, etiqueta de papel 'TOOLS' (1,5 mm despegada) y una hoja ligeramente vencida. ≤ 4 000 triángulos."""
    r = rng(seed)
    mb = MB()
    W, D, H = 0.91, 0.46, 1.83
    paint = ["paint_green", "paint_green", "plastic_blue", "sign_white"][int(r.integers(0, 4))]
    slab(mb, _T(0, 0.012, 0.06), W - 0.004, D - 0.024, H - 0.06 - 0.012, rc=0.006, re=0.005, mat=paint, nc=2, ne=2)     # cuerpo
    slab(mb, _T(0, 0.02, 0.0), W - 0.05, D - 0.06, 0.062, rc=0.004, re=0.002, mat="cable", nc=1, ne=1)                 # zoclo
    slab(mb, _T(0, 0.006, H - 0.014), W + 0.006, D - 0.006, 0.014, rc=0.008, re=0.005, mat=paint, nc=2, ne=2)           # tapa
    yd = -D / 2 - 0.0005
    gap = 0.0015
    for sx in (-1, 1):
        x0, x1 = sorted((sx * gap, sx * (W / 2 - 0.004)))
        sag = 0.003 if sx > 0 else 0.0
        dents = [(float(r.uniform(x0 + 0.08, x1 - 0.08)), float(r.uniform(0.3, 1.4)), float(r.uniform(0.05, 0.11)),
                  float(r.uniform(0.006, 0.014))) for _ in range(int(r.integers(2, 4)))]
        _door_panel(mb, x0, x1, 0.075 - sag, H - 0.02 - sag, yd - 0.018, 0.018, r, mat=paint, dents=dents, rust_z=0.24)
        for zc in (H - 0.32, 0.38):
            for k in range(5):
                _louver(mb, (x0 + x1) / 2, zc + k * 0.03 - sag, 0.2, yd - 0.018 - 0.0002, paint)
        xh = x0 + 0.02 if sx < 0 else x1 - 0.02
        xh = sx * (W / 2 - 0.004)
        for zc in (0.2, H / 2, H - 0.22):
            mb.cyl((xh + sx * 0.005, yd - 0.006, zc - 0.035 - sag), (xh + sx * 0.005, yd - 0.006, zc + 0.035 - sag), 0.0055, seg=8, mat="steel")
            lathe(mb, [(0.0, 0.0), (0.0055, 0.0), (0.004, 0.003), (0.0, 0.0035)], seg=8, mat="steel",
                  M=_T(xh + sx * 0.005, yd - 0.006, zc + 0.035 - sag))
    # manija de palanca con portacandado (hoja derecha) y candado
    xm, zm = 0.045, 1.0
    slab(mb, _T(xm, yd - 0.018, zm - 0.06) @ _Rx(90), 0.03, 0.12, 0.004, rc=0.008, re=0.0015, mat="steel", nc=2, ne=1)
    revolve(mb, [(0.0, 0.0), (0.009, 0.0), (0.009, 0.012), (0.007, 0.016), (0.0, 0.016)], "steel", seg=10,
            M=_T(xm, yd - 0.022, zm) @ _Rx(90))
    sweep_frame(mb, [(-0.006, -0.004), (0.006, -0.004), (0.007, 0.0), (0.006, 0.004), (-0.006, 0.004), (-0.007, 0.0)],
                fillet([(xm, yd - 0.034, zm), (xm, yd - 0.04, zm), (xm, yd - 0.04, zm - 0.1), (xm + 0.008, yd - 0.034, zm - 0.12)], 0.01, 3),
                "steel", up=(0, -1, 0))
    slab(mb, _T(xm, yd - 0.018, zm + 0.065) @ _Rx(90), 0.022, 0.04, 0.004, rc=0.004, re=0.0012, mat="steel", nc=2, ne=1)
    zl = zm + 0.075
    loop_tube(mb, [Vector((xm + 0.009 * math.cos(2 * PI * k / 10), yd - 0.034, zl + 0.012 * math.sin(2 * PI * k / 10) + 0.006))
                   for k in range(10)], 0.0028, seg=5, mat="steel", normal=(0, 1, 0))
    slab(mb, _T(xm, yd - 0.034, zl - 0.04) @ _Rz(float(r.uniform(-8, 8))), 0.04, 0.016, 0.036, rc=0.004, re=0.003, mat="paint_yellow",
         nc=2, ne=2)
    # etiqueta de papel sobre la hoja izquierda (despegada 1,5 mm)
    Ml = _T(-0.2, yd - 0.018 - 0.0015 - 0.0008, 1.3) @ _Rx(90) @ _Rz(float(r.uniform(-3, 3)))
    bplate(mb, [(-0.07, -0.025), (0.07, -0.025), (0.07, 0.025), (-0.07, 0.025)], 0.0008, "paper", M=Ml @ _T(0, 0, -0.0008), e=0.0002)
    label(mb, "TOOLS", 0.026, "cable", Ml @ _T(0, -0.012, 0.0), depth=0.0012, res=2, bold=True)
    return mb


# ======================================================================================================== corrales y cercas
def _strap_hinge(mb, M, L=0.32, w=0.04, mat="metal_rust", rr=None):
    """Bisagra de cola larga: solera que se adelgaza hacia la punta con 3 pernos de coche, nudillo enrollado sobre el perno
    (pivote en el origen local, la cola sale hacia +X sobre el plano z = 0)."""
    sweep_frame(mb, [(-0.5, -0.003), (0.5, -0.003), (0.5, 0.003), (-0.5, 0.003)],
                [tuple(M @ Vector((x, 0.0, 0.003))) for x in (0.012, L * 0.5, L)], mat, up=tuple(M.to_3x3() @ Vector((0, 0, 1))),
                scale=lambda t: (w * (1 - 0.45 * t), 1.0))
    revolve(mb, [(0.0, -w / 2), (0.011, -w / 2), (0.011, w / 2), (0.0, w / 2)], mat, seg=10, M=M @ _T(0, 0, 0.011) @ _Rx(90))
    for x in (0.05, L * 0.55, L - 0.03):
        cbolt(mb, M @ _T(x, 0, 0.006), r=0.008, mat=mat)


def stall_partition(L=3.0, h=1.4, gate=True, seed=0):
    """Costado de corral de establo: postes aserrados de 15 × 15 con cabeza achaflanada, tablones de 2×8 (5 cm) con holgura
    entre ellos atornillados a los postes con pernos de coche, el de arriba mordisqueado por los animales; con gate=True una
    puerta de 1,1 m de tablones con bastidor en Z, dos bisagras de cola larga sobre pernos (pivotes) en el poste y pasador de
    cerrojo con su armella en el poste de cierre, holguras de 1,5 cm. Corre a lo largo de +X de 0 a L, centrada en y = 0.
    ≤ 5 000 triángulos."""
    r = rng(seed)
    mb = MB()
    ps = 0.15
    hp = h + 0.12
    gw = 1.1 if gate else 0.0
    posts = [0.0, L] + ([L - gw - 0.015 * 2 - ps] if gate else []) + ([L / 2] if (not gate and L > 2.4) else [])
    if gate and L - gw - ps > 2.6:
        posts.append((L - gw - ps - 0.04) / 2)
    posts = sorted(posts)
    for x in posts:
        xc = min(max(x, ps / 2), L - ps / 2)
        board(mb, (xc, 0.0, 0.0), (xc, 0.0, hp), ps, ps, "wood_grey", r, r=0.008, up=(0, 1, 0), seg=4, rough=0.003, square=0.0,
              caps=(True, False))
        # cabeza achaflanada (escurre el agua)
        loft_rings(mb, [[Vector((xc + dx, dy_, hp + (0.0 if k == 0 else 0.03 * (1 if dy_ < 0 else 0.0) + 0.0)))
                         for (dx, dy_) in rr_pts(ps - (0.0 if k == 0 else 0.016), ps - (0.0 if k == 0 else 0.016), 0.008, 1)]
                        for k in range(2)], "wood_grey", cap0=False, cap1=True)
    xa = ps                                                         # tramo fijo: del primer poste al poste de bisagras
    xb = (posts[-2] - ps / 2 + 0.003) if gate else L - ps / 2
    bh, bt, bg = 0.2, 0.05, 0.065
    nb = max(2, int((h - 0.1) / (bh + bg)))
    yb = ps / 2 + bt / 2 + 0.001
    zs = [h - bh / 2 - k * (bh + bg) for k in range(nb)]
    for k, z in enumerate(zs):
        def chew(x, py, pz, k=k):
            if k == 0 and pz > 0:                                    # mordidas de los animales en el canto superior
                bite = 0.012 * max(0.0, math.sin(23 * x) * math.sin(7.3 * x + 1.0)) + 0.006 * max(0.0, math.sin(41 * x + 2))
                return py, pz - bite * (1.0 if py < 0 else 0.6)
            return py, pz
        board(mb, (-0.0, yb, z), (xb, yb, z), bt, bh, ["wood", "wood_grey", "wood"][k % 3], r, r=0.005, up=(0, 0, 1), seg=10 if k == 0 else 4,
              warp=float(r.uniform(-0.006, 0.006)), rough=0.002, deform=chew)
        for x in posts:
            if x > xb:
                continue
            xc = min(max(x, ps / 2), L - ps / 2)
            for dz in (-0.05, 0.05):
                cbolt(mb, _T(xc + float(r.uniform(-0.02, 0.02)), yb + bt / 2, z + dz) @ _Rx(-90), r=0.011, mat="metal_rust")
                cbolt(mb, _T(xc, -ps / 2, z + dz) @ _Rx(90), r=0.011, mat="metal_rust", nut=True)
    if not gate:
        return mb
    # puerta: tablones + bastidor en Z, colgada del poste de bisagras
    xh = posts[-2] + ps / 2 + 0.015
    xe = L - ps - 0.015
    gz0, gz1 = 0.08, h - 0.02
    ng = 4
    gb = (gz1 - gz0 - (ng - 1) * 0.07) / ng
    yg = yb
    for k in range(ng):
        z = gz0 + gb / 2 + k * (gb + 0.07)
        board(mb, (xh, yg, z), (xe, yg, z), bt, gb, ["wood_grey", "wood"][k % 2], r, r=0.005, up=(0, 0, 1), seg=3, rough=0.002)
    yz = yg + bt / 2 + 0.019
    zb_, zt_ = gz0 + gb * 0.5, gz1 - gb * 0.5
    for z in (zb_, zt_):
        board(mb, (xh + 0.02, yz, z), (xe - 0.02, yz, z), 0.038, 0.12, "wood", r, r=0.004, up=(0, 0, 1), seg=2, rough=0.0015)
    board(mb, (xh + 0.08, yz, zb_ + 0.05), (xe - 0.08, yz, zt_ - 0.05), 0.038, 0.11, "wood", r, r=0.004, up=(0, 0, 1), seg=2, rough=0.0015)
    for z in (zb_, zt_):
        for x in (xh + 0.06, (xh + xe) / 2, xe - 0.06):
            nail(mb, _T(x, yz + 0.019, z + float(r.uniform(-0.03, 0.03))) @ _Rx(-90), r=0.0055, seg=5, mat="metal_rust")
    # bisagras de cola larga por la cara del corral (-Y) y pivotes en el poste
    yfront = yg - bt / 2
    xp = posts[-2] + ps / 2 + 0.006
    for z in (zb_, zt_):
        _strap_hinge(mb, _T(xp, yfront, z) @ _Rx(90) @ _Rz(0), L=0.42, rr=r)
        port.member(mb, (xp - 0.06, yfront + 0.004 - 0.011 * 0, z - 0.03), (xp - 0.002, yfront + 0.004, z - 0.03),
                    [(-0.01, 0.01, -0.012, 0.012)], "metal_rust")
        mb.cyl((xp, yfront - 0.011, z - 0.05), (xp, yfront - 0.011, z + 0.03), 0.006, seg=8, mat="metal_rust")
    # cerrojo de pasador en el lado de cierre
    zl_ = gz0 + gb * 2.5 + 0.07 * 2
    xl0 = xe - 0.16
    slab(mb, _T(xl0 + 0.06, yfront, zl_) @ _Rx(90), 0.12, 0.05, 0.004, rc=0.004, re=0.0012, mat="metal_rust", nc=1, ne=1)
    revolve(mb, [(0.0, 0.0), (0.008, 0.0), (0.008, 0.2), (0.006, 0.204), (0.0, 0.205)], "steel", seg=8,
            M=_T(xl0, yfront - 0.012, zl_) @ _Ry(90))
    mb.tube([(xl0 + 0.05, yfront - 0.012, zl_), (xl0 + 0.05, yfront - 0.03, zl_), (xl0 + 0.05, yfront - 0.03, zl_ + 0.04)], 0.005, seg=6,
            mat="steel")
    for dx in (0.01, 0.1):
        loop_tube(mb, [Vector((xl0 + dx + 0.012 * math.cos(2 * PI * k / 8) * 0, yfront - 0.012 + 0.012 * math.cos(2 * PI * k / 8),
                               zl_ + 0.012 * math.sin(2 * PI * k / 8))) for k in range(8)], 0.003, seg=4, mat="metal_rust", normal=(1, 0, 0))
    xs_ = L - ps
    slab(mb, _T(xs_ - 0.001, yfront - 0.0, zl_) @ _Ry(-90) @ _Rz(90), 0.05, 0.004, 0.06, rc=0.002, re=0.001, mat="metal_rust", nc=1, ne=1)
    return mb


def split_rail(mb, p0, p1, w, t, rr, mat="wood_grey", seg=7, face=(0, -1, 0)):
    """Morillo partido (rajado de un tronco): sección de cuña con cara rajada plana hacia `face` y lomo de corteza; aristas y
    caras irregulares, torcido y combado."""
    M, L = port.frame_on(p0, p1, face)
    prof = [(-w / 2, 0.0), (w / 2, 0.0), (w * 0.44, t * 0.42), (w * 0.24, t * 0.84), (0.0, t), (-w * 0.26, t * 0.82), (-w * 0.45, t * 0.4)]
    rings = []
    tw = float(rr.uniform(-0.25, 0.25))
    bow = float(rr.uniform(-0.03, 0.03))
    for k in range(seg + 1):
        u = k / seg
        x = L * u
        a = tw * u
        c, s_ = math.cos(a), math.sin(a)
        ring = []
        for (py, pz) in prof:
            py += float(rr.uniform(-0.007, 0.007))
            pz += float(rr.uniform(-0.006, 0.006)) if pz > 0 else 0.0
            pz -= t / 2
            yy, zz = py * c - pz * s_, py * s_ + pz * c
            zz += t / 2
            ring.append(Vector((x + (float(rr.uniform(-0.01, 0.01)) if k in (0, seg) else 0.0), yy + bow * math.sin(PI * u), -zz)))
        rings.append(ring)
    loft_rings(mb, rings, mat, M=M)
    return M, L


def pen_fence(L=4.0, h=1.3, seed=0):
    """Cerca de corral a la intemperie: postes rollizos chuecos de mezquite (Ø 12-15 cm, cabeza gastada, grietas) a cada ~2 m,
    tres morillos partidos por tramo clavados al frente de los postes, empalmados en los postes intermedios uno junto a otro;
    algunos amarres de alambre galvanizado (3 vueltas) además de los clavos. Corre a lo largo de +X. ≤ 4 000 triángulos."""
    r = rng(seed)
    mb = MB()
    nb = max(1, int(round(L / 2.0)))
    xs = [L * k / nb for k in range(nb + 1)]
    rp = []
    pm = MB()
    for x in xs:
        r0 = float(r.uniform(0.065, 0.078))
        rp.append(r0)
        log_post(pm, (x, 0.0, -0.06), (x + float(r.uniform(-0.03, 0.03)), float(r.uniform(-0.02, 0.02)), h + float(r.uniform(0.05, 0.16))),
                 r0, r0 * 0.88, "wood_grey", r, seg=10, rings=7, crook=0.022, checks=2)
    tree = BVHTree.FromBMesh(pm.bm)
    mb.join(pm)

    def front(x, z, extra=0.0):
        hit = tree.ray_cast(Vector((x, -1.0, z)), Vector((0, 1, 0)), 2.0)[0]
        return (hit.y if hit is not None else -0.07) - extra
    zr = [h - 0.12, h * 0.6, h * 0.22]
    for b in range(nb):
        for k, z in enumerate(zr):
            x0 = xs[b] - (0.0 if b == 0 else -0.0) - 0.08 * (b == 0)
            x1 = xs[b + 1] + (0.08 if b == nb - 1 else 0.06)
            x0 = xs[b] - (0.08 if b == 0 else 0.06)
            dz = float(r.uniform(-0.03, 0.03))
            dz1 = dz + float(r.uniform(-0.04, 0.04))
            tk = float(r.uniform(0.05, 0.065))
            stack = 0.055 if (b % 2 == 1) else 0.0                 # en los postes intermedios un morillo va sobre el otro
            ya = front(xs[b], z + dz) + 0.007 - (stack if b > 0 else 0.0)
            yb_ = front(xs[b + 1], z + dz1) + 0.007 - (stack if b < nb - 1 else 0.0) * 0.0
            if b % 2 == 1:
                yb_ -= stack if b + 1 < nb else 0.0
            split_rail(mb, (x0, ya, z + dz), (x1, yb_, z + dz1), float(r.uniform(0.11, 0.14)), tk, r,
                       mat=["wood_grey", "wood", "wood_grey"][k], face=(0, 1, 0))
            for xp, yp, zp in ((xs[b], ya, z + dz), (xs[b + 1], yb_, z + dz1)):
                for dzn in (-0.025, 0.02):
                    nail(mb, _T(xp + float(r.uniform(-0.02, 0.02)), yp - tk + 0.004, zp + dzn) @ _Rx(90), r=0.006, seg=5, mat="metal_rust")
    # amarres de alambre: 3 vueltas alrededor del poste y el morillo
    for (xi, k) in ((0, 1), (nb, 0), (min(1, nb), 2)):
        x = xs[xi]
        z = zr[k]
        R = rp[xi] + 0.06
        pts = []
        for q in range(25):
            a = 2 * PI * q / 8
            pts.append((x + R * 0.55 * math.cos(a), -0.04 + R * 0.8 * math.sin(a), z - 0.035 + 0.011 * q / 8))
        mb.tube(pts, 0.0018, seg=4, mat="aluminium")
    return mb


def wire_fence(L=6.0, seed=0):
    """Cerca de alambre de púas: postes de rama chueca (mezquite) a cada ~2 m (≤ 2,5 m), enterrados, con grietas; 4 hilos de
    alambre de púas con catenaria entre postes, grapas en cada poste y púas de 4 puntas (dos alambres cruzados) a cada ~30 cm.
    Corre a lo largo de +X. ≤ 3 000 triángulos."""
    r = rng(seed)
    mb = MB()
    nb = max(1, int(math.ceil(L / 2.5)))
    xs = [L * k / nb for k in range(nb + 1)]
    tops = []
    pm = MB()
    for x in xs:
        r0 = float(r.uniform(0.055, 0.07))
        h = float(r.uniform(1.18, 1.35))
        lean = (float(r.uniform(-0.05, 0.05)), float(r.uniform(-0.04, 0.04)))
        log_post(pm, (x, 0.0, -0.08), (x + lean[0], lean[1], h), r0, r0 * 0.7, "wood_grey", r, seg=9, rings=7, crook=0.03, checks=1,
                 rough=0.1)
        tops.append((x, lean, r0, h))
    tree = BVHTree.FromBMesh(pm.bm)
    mb.join(pm)

    def front(x, z):
        hit = tree.ray_cast(Vector((x, -1.0, z)), Vector((0, 1, 0)), 2.0)
        return (hit[0].y, hit[0].x) if hit[0] is not None else (-0.06, x)
    zst = [0.32, 0.56, 0.8, 1.04]
    for z in zst:
        pts = []
        for b in range(nb):
            xa, la, ra, ha = tops[b]
            xb, lb, rb, hb = tops[b + 1]
            sag = float(r.uniform(0.015, 0.04))
            n = 8
            for q in range(n + (1 if b == nb - 1 else 0)):
                u = q / n
                fa, fb = front(xa + la[0] * z / ha, z), front(xb + lb[0] * z / hb, z)
                pa = Vector((fa[1], fa[0] - 0.0022, z))
                pb = Vector((fb[1], fb[0] - 0.0022, z))
                p = pa.lerp(pb, u)
                p.z -= sag * 4 * u * (1 - u)
                pts.append(p)
        mb.tube([tuple(p) for p in pts], 0.0021, seg=4, mat="metal_rust")
        # grapas en cada poste
        for (x, lean, r0, h) in tops:
            fy, fx = front(x + lean[0] * z / h, z)
            c = Vector((fx, fy + 0.002, z))
            mb.tube([tuple(c + Vector((-0.008, 0.004, 0.0))), tuple(c + Vector((-0.006, -0.004, 0.0))), tuple(c + Vector((0.006, -0.004, 0.0))),
                     tuple(c + Vector((0.008, 0.004, 0.0)))], 0.0014, seg=3, mat="steel")
        # púas
        total = 0.0
        for i in range(len(pts) - 1):
            seglen = (pts[i + 1] - pts[i]).length
            k0 = int(total / 0.3)
            total += seglen
            for kb in range(k0 + 1, int(total / 0.3) + 1):
                u = (kb * 0.3 - (total - seglen)) / seglen
                c = pts[i].lerp(pts[i + 1], u)
                d = (pts[i + 1] - pts[i]).normalized()
                n1, n2 = _perp(d)
                for q in range(2):
                    a = float(r.uniform(0, PI)) + q * PI / 2
                    sp = (n1 * math.cos(a) + n2 * math.sin(a) + d * float(r.uniform(-0.3, 0.3))).normalized()
                    cq = c + d * (0.0028 * q)                    # los dos alambres de la púa van enrollados uno junto al otro
                    ring = [cq + (d * math.cos(2 * PI * j / 3) + sp.cross(d) * math.sin(2 * PI * j / 3)) * 0.0016 for j in range(3)]
                    skin(mb, [[cq - sp * 0.013], ring, [cq + sp * 0.013]], "metal_rust")
    return mb
