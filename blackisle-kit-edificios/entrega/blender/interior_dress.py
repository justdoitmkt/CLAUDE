"""interior_dress.py — vestido interior de los departamentos: escombro, basura, focos colgando, apagadores y algún mueble roto.

La revisión de aceptación (2026-10-28) vio los cuartos como cascarones limpios: con la estructura completa pero sin escombro ni
escala humana. El plan de ESTADO decía "sin mobiliario, con escombro y daño interior". Este módulo lo cumple sin conocer los
cuartos: lee la geometría ya construida con rayos (BVH de carcasa + interior + detalles) y solo coloca piezas donde:
  - hay piso a la cota del nivel (cara horizontal hacia arriba) y techo de losa a 2,2–3,6 m (fuera de escaleras y del colapso);
  - el punto está encerrado: 8 rayos horizontales a 0,5 m chocan antes de 7 m (fuera de logias, galerías y balcones);
  - queda lejos de los núcleos de escalera (rectángulos de cfg) y, para lo que va pegado al muro, hay muro macizo detrás
    (3 rayos paralelos a las alturas pedidas chocan casi a la misma distancia: no hay puerta ahí);
  - (2026-11-19) la huella REAL de cada pieza cabe en el cuarto: colchones, sillas volcadas y montones se prueban con rayos
    contra muros, puertas y escaleras antes de colocarlos (antes una silla volcada a 0,45 m de un muro lo atravesaba).
Nada de lo colocado pasa de 0,35 m salvo sillas y focos (no estorban el paso: cápsula de jugador r 0,25, escalón 0,35).

Segunda pasada AAA (R-AAA, 2026-11-19): las piezas son objetos con su construcción real, no cajas.
  - mattress(): colchón de resortes (individual 0,99 × 1,90 o matrimonial 1,35 × 1,90, 17–21 cm) con aristas redondeadas,
    costados abombados, cara acolchada (pespunte en rombo), hundido de uso, esquinas levantadas, vivos (ribetes) arriba y abajo,
    asas de cinta, ventilas de ojillo, manchas de uso y, a veces, la tela rasgada con el relleno, el fieltro y los resortes
    Bonnell a la vista; almohadas simuladas (kit.softgoods) hundidas en el colchón.
  - broken_chair(): silla de comedor de madera maciza (asiento de 3 tablas, faldones, patas ahusadas, travesaños torneados,
    postes traseros inclinados con copete y travesaño curvos, tornillos) rota: pata quebrada con astillas (y el pedazo tirado),
    copete partido, tabla del asiento suelta o travesaño zafado.
  - trash(): hojas tamaño carta curvadas, bolas de papel arrugado, latas de 355 ml (enteras, abolladas o aplastadas), botellas de
    cerveza de cuello largo (enteras o con el cuello roto y vidrios), bolsas de plástico arrugadas y cartón.
  - ceiling_bulb(): roseta de techo con tornillos, cordón dúplex trenzado, portalámparas de baquelita (Ø 39 × 54 mm) y foco A19
    (Ø 60 × 110 mm) con casquillo E26 roscado y filamento; a veces roto (vidrio en dientes) o sin foco.
  - wall_plate(): placa de apagador o contacto de 70 × 114 mm con cantos redondeados, mecanismo y tornillos 6-32 de cabeza oval
    ranurada a 60,3 mm; a veces colgando de un tornillo.
  - plaster_debris(): lajas de aplanado con cara pintada, canto de fractura irregular y combadas, trozos de concreto rugosos y
    montoncito de polvo.
Referencias (medidas): colchones MX 1,00/1,35 × 1,90 (homedepot.com.mx, mercadolibre); almohada estándar 51 × 66 cm
(sleepfoundation.org); lata 12 oz Ø 66,2 × 122,2 mm (spec American Canning / Illing); botella long neck 355 ml Ø 60,6 × 228,6 mm
(thecarycompany.com); foco A19 Ø 60 mm × 100–112 mm, base E26 (ANSI C79.1, waveformlighting.com); portalámparas de baquelita
Ø 39 × 54 mm (creative-cables.us); placa 1 gang 2,75 × 4,5 in, tornillos 6-32 a 2-3/8 in (kyleswitchplates.com); silla: asiento
45 cm de alto, 40–46 cm de fondo (ikea, woodbin.com).
"""
import math

import bmesh
import numpy as np
from mathutils import Matrix, Vector
from mathutils import noise as _mnoise
from mathutils.bvhtree import BVHTree

from kit.common import MB, rng

DIRS8 = [Vector((math.cos(a), math.sin(a), 0.0)) for a in (k * math.pi / 4 for k in range(8))]
PI = math.pi


def _T(x, y, z):
    return Matrix.Translation((x, y, z))


def _Rz(a):
    return Matrix.Rotation(a, 4, "Z")


def _Rx(a):
    return Matrix.Rotation(a, 4, "X")


def _Ry(a):
    return Matrix.Rotation(a, 4, "Y")


class Scene:
    def __init__(self, objs):
        self.bms, self.trees = [], []
        for o in objs:
            bm = bmesh.new()
            bm.from_mesh(o.data)
            bm.transform(o.matrix_world)
            self.bms.append(bm)
            self.trees.append(BVHTree.FromBMesh(bm))

    def hit(self, p, d, dist):
        best = None
        for t in self.trees:
            loc, nrm, idx, dd = t.ray_cast(p, d, dist)
            if idx is not None and (best is None or dd < best[2]):
                best = (loc, nrm, dd)
        return best

    def free(self):
        for bm in self.bms:
            bm.free()


def _in_rects(x, y, rects, pad):
    return any(x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad for (x0, x1, y0, y1) in rects)


def probe(sc, x, y, zl, stairs):
    """Devuelve dict del punto (piso, techo, distancias a muros) o None si no sirve."""
    if _in_rects(x, y, stairs, 0.45):
        return None
    h = sc.hit(Vector((x, y, zl + 1.2)), Vector((0, 0, -1)), 1.6)
    if h is None or h[1].z < 0.9 or abs(h[0].z - zl) > 0.12:
        return None
    zf = h[0].z
    up = sc.hit(Vector((x, y, zf + 0.05)), Vector((0, 0, 1)), 4.0)
    if up is None or up[1].z > -0.9 or not (2.2 <= up[0].z - zf <= 3.6):
        return None
    ds = []
    for d in DIRS8:
        hh = sc.hit(Vector((x, y, zf + 0.5)), d, 7.0)
        if hh is None:
            return None                        # abierto: logia, galería, balcón, colapso
        ds.append(hh[2])
    k = min(range(8), key=lambda i: ds[i])
    return dict(x=x, y=y, zf=zf, zc=up[0].z, d=ds[k], wall_dir=DIRS8[k], ds=ds)


def solid_wall(sc, p, n, d, half=0.5, zs=(0.5, 1.9)):
    """Muro macizo detrás de p (dirección n, distancia d): 3 rayos paralelos a las alturas zs chocan a ±6 cm de d."""
    t = Vector((-n.y, n.x, 0.0))
    for off in (-half, 0.0, half):
        for z in zs:
            q = Vector((p["x"], p["y"], p["zf"] + z)) + t * off
            hh = sc.hit(q, n, d + 0.4)
            if hh is None or abs(hh[2] - d) > 0.06:
                return False
    return True


def footprint_clear(sc, M, pts2d, z0, zs=(0.04, 0.2), pad=0.03):
    """True si el contorno local `pts2d` [(x, y)] (marco M de la pieza, z local = piso) no choca con nada entre su centro y
    cada punto a las alturas zs (más `pad`): ni muros, ni marcos de puerta, ni escaleras. Prueba de colocación."""
    c = Vector((sum(p[0] for p in pts2d) / len(pts2d), sum(p[1] for p in pts2d) / len(pts2d), 0.0))
    for z in zs:
        a = M @ Vector((c.x, c.y, z0 + z))
        for (x, y) in pts2d:
            b = M @ Vector((x, y, z0 + z))
            d = b - a
            L = d.length
            if L < 1e-6:
                continue
            hh = sc.hit(a, d / L, L + pad)
            if hh is not None:
                return False
    return True


# ================================================================================================================ utilidades
def _sst(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _nzv(p, off, freq=1.0):
    return _mnoise.noise(Vector((p[0] * freq + off[0], p[1] * freq + off[1], p[2] * freq + off[2])))


def _noise_arr(P, freq, off):
    """Perlin de mathutils sobre un arreglo (N, 3) -> (N,)."""
    o = Vector(off)
    return np.array([_mnoise.noise(Vector((float(p[0]) * freq, float(p[1]) * freq, float(p[2]) * freq)) + o) for p in P])


def _off(r):
    return (float(r.uniform(-300, 300)), float(r.uniform(-300, 300)), float(r.uniform(-300, 300)))


def _lathe(mb, prof, mats, seg=24, M=None, rmod=None, closed=False):
    """Sólido de revolución sobre Z local (kit.clinic_equipo.revolve: polos sin caras degeneradas, material por tramo)."""
    from kit.clinic_equipo import revolve
    revolve(mb, prof, mats, seg=seg, M=M, caps=True, rmod=rmod, closed=closed)


def _rr(w, h, r, n=3):
    from kit.clinic import rr_profile
    return rr_profile(w, h, min(r, 0.49 * w, 0.49 * h), n=n)


def _loft_path(mb, path, prof_fn, mat, up=(0, 0, 1), cap0=True, cap1=True, closed=False):
    """Barre perfiles 2D variables a lo largo de una polilínea: prof_fn(s, i) -> [(x lateral, y en `up`)], s = 0..1 por longitud.
    closed=True: lazo cerrado (une el último anillo con el primero, sin tapas). Devuelve los anillos de vértices."""
    P = [Vector(p) for p in path]
    n = len(P)
    if closed:
        cap0 = cap1 = False
    acc = [0.0]
    for i in range(1, n):
        acc.append(acc[-1] + (P[i] - P[i - 1]).length)
    tot = acc[-1] or 1.0
    U0 = Vector(up)
    rings = []
    for i in range(n):
        if closed:
            T = (P[(i + 1) % n] - P[(i - 1) % n]).normalized()
        else:
            T = (P[min(i + 1, n - 1)] - P[max(i - 1, 0)]).normalized()
        U = U0 - T * U0.dot(T)
        if U.length < 1e-6:
            U = T.orthogonal()
        U.normalize()
        X = T.cross(U)
        rings.append([mb.bm.verts.new(P[i] + X * a + U * b) for (a, b) in prof_fn(acc[i] / tot, i)])
    k = len(rings[0])
    for i in range(n if closed else n - 1):
        A, B = rings[i], rings[(i + 1) % n]
        for j in range(k):
            jj = (j + 1) % k
            mb.face([A[j], B[j], B[jj], A[jj]], mat)
    if cap0:
        mb.face(list(rings[0]), mat)
    if cap1:
        mb.face(list(reversed(rings[-1])), mat)
    return rings


# ================================================================================================================ colchón
def _mattress_deform(P, N, L, W, H, prm):
    """Desplaza los puntos P (N×3, z 0..H) del colchón con normales N de la caja redondeada: abombado de costados, corona y
    acolchado (pespunte en rombo) arriba, hundido de uso, arrugas, esquinas levantadas. Devuelve P nuevo."""
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    nz = N[:, 2]
    nh = np.hypot(N[:, 0], N[:, 1])
    wt = _sst((nz - 0.15) / 0.7)                         # cara de arriba (y la mitad superior del redondeo)
    t = np.clip(z / H, 0.0, 1.0)
    out = P.copy()
    # costados abombados (relleno que empuja la tela) — máximo a media altura
    bul = prm["bulge"] * np.sin(PI * t) * nh
    out[:, 0] += N[:, 0] / np.maximum(nh, 1e-6) * bul
    out[:, 1] += N[:, 1] / np.maximum(nh, 1e-6) * bul
    # corona
    xn, yn = np.clip(2 * x / L, -1, 1), np.clip(2 * y / W, -1, 1)
    dz = prm["crown"] * (1 - xn ** 4) * (1 - yn ** 4)
    # acolchado: rombos de 11 cm con pespunte hundido, dentro de una orilla lisa de 7 cm
    b = 0.075
    mq = _sst((L / 2 - b - np.abs(x)) / 0.03) * _sst((W / 2 - b - np.abs(y)) / 0.03)
    S = 0.11
    s1, s2 = (x + y) / math.sqrt(2), (x - y) / math.sqrt(2)
    d1 = np.abs(s1 / S - np.round(s1 / S)) * 2      # 0 en la línea de pespunte, 1 a media celda
    d2 = np.abs(s2 / S - np.round(s2 / S)) * 2
    q = np.minimum(d1, d2)
    dz += mq * (0.0065 * (1 - (1 - q) ** 3) - 0.0042)
    # hundido de uso (cadera y hombros de quien durmió ahí)
    for (cx, cy, sx, sy, dep) in prm["dents"]:
        dz -= dep * np.exp(-((x - cx) / sx) ** 2 - ((y - cy) / sy) ** 2)
    dz += 0.0022 * prm["wr"]                             # arrugas de la tela
    out[:, 2] += dz * wt
    # deformación general: esquinas levantadas (el colchón viejo se arquea) y alabeo
    out[:, 2] += prm["curl"] * (np.abs(xn) ** 2.2) * (np.abs(yn) ** 1.6) + prm["twist"] * xn * yn
    return out


def _mattress_normals(P, L, W, H, re):
    inner = np.array([L / 2 - re, W / 2 - re, H / 2 - re])
    c = P - np.array([0.0, 0.0, H / 2])
    q = np.clip(c, -inner, inner)
    d = c - q
    ln = np.linalg.norm(d, axis=1)
    return d / np.maximum(ln, 1e-9)[:, None]


def mattress(mb, r, pillows=True):
    """Colchón tirado contra el muro (origen: centro del lado pegado al muro; +y hacia el cuarto).
    Huella: x ∈ ±0,96, y ∈ [0,03, 0,03 + W + 0,04] (W 0,99 o 1,35), alto ≤ 0,23 m (con almohadas ≤ 0,32)."""
    from kit import softgoods as sg
    wide = r.random() < 0.45
    W = (1.35 if wide else 0.99) + float(r.uniform(-0.01, 0.01))
    L = 1.90 + float(r.uniform(-0.01, 0.01))
    H = float(r.uniform(0.16, 0.20))
    re = 0.045
    yaw = float(r.uniform(-0.035, 0.035))
    off = _off(r)
    nd = 2 if wide else 1
    dents = []
    for k in range(nd):
        cy = (k - (nd - 1) / 2) * W * 0.45 + float(r.uniform(-0.06, 0.06))
        cx = float(r.uniform(-0.2, 0.15)) * L
        dents.append((cx, cy, float(r.uniform(0.38, 0.5)), float(r.uniform(0.17, 0.24)), float(r.uniform(0.025, 0.045))))
        dents.append((cx + 0.45 * np.sign(cx + 1e-3), cy, 0.22, 0.17, float(r.uniform(0.008, 0.016))))
    prm = dict(bulge=float(r.uniform(0.008, 0.015)), crown=0.010, dents=dents, curl=float(r.uniform(0.012, 0.03)),
               twist=float(r.uniform(-0.01, 0.01)))
    co, flat, lens = sg._rbox_arrays(L, W, H, re=re, step=0.027, n_round=4)
    N = _mattress_normals(co, L, W, H, re)
    prm["wr"] = _noise_arr(co, 7.0, off) + 0.5 * _noise_arr(co, 19.0, off)
    P = _mattress_deform(co, N, L, W, H, prm)
    zmin = float(P[:, 2].min())
    lift = -zmin
    P[:, 2] += lift
    body = MB()
    vs = [body.bm.verts.new(Vector(p)) for p in P]
    k = 0
    mi = body.mi("fabric")
    for n in lens:
        f = body.bm.faces.new([vs[i] for i in flat[k:k + n]])
        f.material_index = mi
        k += n
    body.bm.normal_update()

    def surf(pts, nrm, push=0.0):
        """Puntos de la superficie sin deformar -> deformados (+ empuje a lo largo de la normal)."""
        pts = np.asarray(pts, dtype=np.float64)
        nrm = np.asarray(nrm, dtype=np.float64)
        prm["wr"] = _noise_arr(pts, 7.0, off) + 0.5 * _noise_arr(pts, 19.0, off)
        q = _mattress_deform(pts, nrm, L, W, H, prm)
        q[:, 2] += lift
        return q + nrm * push

    # rasgadura: la tela y el relleno se abren y se ven el fieltro y los resortes Bonnell
    tear = None
    if r.random() < 0.4:
        tx = float(r.uniform(-0.45, 0.45)) * L
        ty = float(r.uniform(-0.15, 0.15)) * W
        ra, rb = float(r.uniform(0.12, 0.22)), float(r.uniform(0.08, 0.14))
        ang = float(r.uniform(0, PI))
        toff = _off(r)
        tear = (tx, ty, ra, rb, ang, toff)

        def inside(x, y, shrink=0.0):
            dx, dy = x - tx, y - ty
            u = (dx * math.cos(ang) + dy * math.sin(ang)) / max(ra - shrink, 0.01)
            v = (-dx * math.sin(ang) + dy * math.cos(ang)) / max(rb - shrink, 0.01)
            th = math.atan2(v, u)
            rr_ = 1.0 + 0.2 * _mnoise.noise(Vector((math.cos(th) * 1.5, math.sin(th) * 1.5, 0.0)) + Vector(toff))
            return u * u + v * v < rr_ * rr_
        bm = body.bm
        kill = set(f for f in bm.faces if f.normal.z > 0.8 and inside(f.calc_center_median().x, f.calc_center_median().y))
        # solo si el borde del corte es UN lazo simple (si no, el colchón queda entero)
        bedges = [e for f in kill for e in f.edges if sum(1 for g in e.link_faces if g in kill) == 1]
        deg = {}
        for e in bedges:
            for v in e.verts:
                deg[v] = deg.get(v, 0) + 1
        simple = len(kill) >= 10 and bedges and all(d == 2 for d in deg.values())
        if simple:
            seen_v, stack = set(), [bedges[0].verts[0]]
            badj = {}
            for e in bedges:
                a_, b_ = e.verts
                badj.setdefault(a_, []).append(b_)
                badj.setdefault(b_, []).append(a_)
            while stack:
                v = stack.pop()
                if v in seen_v:
                    continue
                seen_v.add(v)
                stack += badj[v]
            simple = len(seen_v) == len(deg)
        if simple:
            bmesh.ops.delete(bm, geom=list(kill), context="FACES_ONLY")
            loose = [e for e in bm.edges if not e.link_faces]
            bmesh.ops.delete(bm, geom=loose, context="EDGES")
            lv = [v for v in bm.verts if not v.link_faces]
            bmesh.ops.delete(bm, geom=lv, context="VERTS")
            bnd = [e for e in bm.edges if len(e.link_faces) == 1]
            # ordena el borde en un lazo
            adj = {}
            for e in bnd:
                a, b = e.verts
                adj.setdefault(a, []).append(b)
                adj.setdefault(b, []).append(a)
            loops = []
            seen = set()
            for v0 in adj:
                if v0 in seen:
                    continue
                lp = [v0]
                seen.add(v0)
                prev, cur = None, v0
                while True:
                    nxt = [w for w in adj[cur] if w is not prev and w not in seen]
                    if not nxt:
                        break
                    prev, cur = cur, nxt[0]
                    lp.append(cur)
                    seen.add(cur)
                loops.append(lp)
            lp = max(loops, key=len)
            if len(lp) >= 6 and all(len(adj[v]) == 2 for v in lp):
                # orientación del lazo: que la cara del borde (fleco) quede con la cara vecina
                e0 = bm.edges.get((lp[0], lp[1]))
                f0 = e0.link_faces[0]
                fv = list(f0.verts)
                i0 = fv.index(lp[0])
                forward = fv[(i0 + 1) % len(fv)] is lp[1]
                if forward:
                    lp = list(reversed(lp))
                # el borde escalonado de la retícula se lleva a la curva irregular del corte (sin dientes de sierra)
                for v in lp:
                    dx, dy = v.co.x - tx, v.co.y - ty
                    u = (dx * math.cos(ang) + dy * math.sin(ang)) / ra
                    w_ = (-dx * math.sin(ang) + dy * math.cos(ang)) / rb
                    th = math.atan2(w_, u)
                    rr_ = 1.0 + 0.2 * _mnoise.noise(Vector((math.cos(th) * 1.5, math.sin(th) * 1.5, 0.0)) + Vector(toff))
                    eu, ew = rr_ * ra * math.cos(th), rr_ * rb * math.sin(th)
                    v.co.x = tx + eu * math.cos(ang) - ew * math.sin(ang)
                    v.co.y = ty + eu * math.sin(ang) + ew * math.cos(ang)
                ctr = sum((v.co for v in lp), Vector()) / len(lp)
                fr = rng(int(abs(toff[0]) * 1000) % 100000)
                z_floor = 0.035 + lift
                rings = [lp]
                r1, r2, r3 = [], [], []
                for v in lp:
                    dd = Vector((ctr.x - v.co.x, ctr.y - v.co.y, 0.0))
                    dn = dd.normalized() if dd.length > 1e-6 else Vector((0, 0, 0))
                    fringe = float(fr.uniform(0.003, 0.014))
                    r1.append(bm.verts.new(v.co + dn * fringe + Vector((0, 0, -0.004 - fringe * 0.4))))
                    r2.append(bm.verts.new(Vector((v.co.x + dn.x * 0.004, v.co.y + dn.y * 0.004, v.co.z - 0.032 - float(fr.uniform(0, 0.008))))))
                    r3.append(bm.verts.new(Vector((v.co.x + dn.x * 0.006, v.co.y + dn.y * 0.006, z_floor))))
                rings += [r1, r2, r3]
                mats = ["fabric", "linen", "burlap"]
                nloop = len(lp)
                for ri in range(3):
                    A, B = rings[ri], rings[ri + 1]
                    for j in range(nloop):
                        jj = (j + 1) % nloop
                        body.face([A[j], A[jj], B[jj], B[j]], mats[ri])
                body.face(list(r3), "burlap")
                # resortes Bonnell (reloj de arena, 4,5 vueltas, alambre Ø 2,2 mm) en una retícula de 9 cm
                sp = 0.09
                ztop = float(min(v.co.z for v in lp)) - 0.04
                coils = MB()
                with coils.soft():
                    for ix in range(-4, 5):
                        for iy in range(-4, 5):
                            cx, cy = tx + ix * sp, ty + iy * sp
                            if not inside(cx, cy, shrink=0.05):
                                continue
                            pts = []
                            nt, npt = 4.5, 18
                            for kk in range(int(nt * npt) + 1):
                                s = kk / (nt * npt)
                                a = 2 * PI * nt * s
                                rc = 0.036 - 0.011 * math.sin(PI * s)
                                zz = z_floor + 0.004 + (ztop - z_floor - 0.008) * (0.06 + 0.88 * s if 0.06 < s < 0.94 else (s if s <= 0.06 else s))
                                pts.append((cx + rc * math.cos(a), cy + rc * math.sin(a), zz))
                            coils.tube(pts, 0.0011, seg=8, mat="metal_rust")
                body.join(coils)
    # vivos (ribetes) sobre la costura a 45° de las aristas superior e inferior
    a, b = L / 2 - re, W / 2 - re
    c45 = math.cos(PI / 4)
    outline = []
    for (cx, cy, a0) in ((a, -b, -PI / 2), (a, b, 0.0), (-a, b, PI / 2), (-a, -b, PI)):
        for kk in range(7):
            ang = a0 + (PI / 2) * kk / 6
            outline.append((cx, cy, math.cos(ang), math.sin(ang)))
    dense = []
    for i in range(len(outline)):
        p0, p1 = outline[i], outline[(i + 1) % len(outline)]
        Lseg = math.hypot((p1[0] + re * p1[2]) - (p0[0] + re * p0[2]), (p1[1] + re * p1[3]) - (p0[1] + re * p0[3]))
        nn = max(1, int(Lseg / 0.035))
        for kk in range(nn):
            t = kk / nn
            cx, cy = p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t
            dx, dy = p0[2] + (p1[2] - p0[2]) * t, p0[3] + (p1[3] - p0[3]) * t
            dl = math.hypot(dx, dy)
            dense.append((cx, cy, dx / dl, dy / dl))
    for sz in (1, -1):
        zc = H / 2 + sz * (H / 2 - re)
        pts = [(cx + re * c45 * dx, cy + re * c45 * dy, zc + sz * re * c45) for (cx, cy, dx, dy) in dense]
        nrm = [(c45 * dx, c45 * dy, sz * c45) for (cx, cy, dx, dy) in dense]
        q = surf(pts, nrm, push=0.0015)
        ring = [(0.0042 * math.cos(2 * PI * j / 10), 0.0042 * math.sin(2 * PI * j / 10)) for j in range(10)]
        with body.soft():
            _loft_path(body, [tuple(p) for p in q], lambda s, i: ring, "fabric", up=(0, 0, 1), closed=True)
    # asas de cinta en el costado del cuarto y ventilas de ojillo
    for xc in (-0.42, 0.42):
        path = []
        for kk in range(13):
            s = kk / 12
            path.append((xc + 0.075 * (2 * s - 1), W / 2, H * 0.52 - 0.012 * math.sin(PI * s)))
        nrm = [(0.0, 1.0, 0.0)] * len(path)
        q = surf(path, nrm)
        q = [Vector(p) + Vector((0, 0.003 + 0.017 * math.sin(PI * kk / 12) ** 0.7, 0)) for kk, p in enumerate(q)]
        q[0] -= Vector((0, 0.004, 0))
        q[-1] -= Vector((0, 0.004, 0))
        _loft_path(body, q, lambda s, i: _rr(0.032, 0.0026, 0.0012, n=2), "fabric", up=(0, 1, 0))
    for xc in (-0.62, 0.62):
        q = surf([(xc, W / 2, H * 0.5)], [(0.0, 1.0, 0.0)])[0]
        _lathe(body, [(0.0040, -0.003), (0.0085, -0.003), (0.0095, 0.0008), (0.0085, 0.0022), (0.0047, 0.0022), (0.0040, 0.0005)],
               "aluminium", seg=16, M=_T(*q) @ _Rx(-PI / 2), closed=True)
    # manchas de uso: calcas que siguen la cara de arriba (1,4 mm de relieve)
    body.bm.normal_update()
    tree = BVHTree.FromBMesh(body.bm)
    for _ in range(int(r.integers(1, 4))):
        cx = float(r.uniform(-0.38, 0.38)) * L
        cy = float(r.uniform(-0.32, 0.32)) * W
        R0 = float(r.uniform(0.07, 0.22))
        so = _off(r)
        na, nr = 28, 5
        ring_pts = []
        ok = True
        for ir in range(1, nr + 1):
            ring = []
            for ia in range(na):
                th = 2 * PI * ia / na
                rr_ = R0 * (ir / nr) * (0.72 + 0.28 * _mnoise.noise(Vector((math.cos(th) * 1.5, math.sin(th) * 1.5, ir * 0.1)) + Vector(so)))
                x, y = cx + rr_ * math.cos(th), cy + rr_ * math.sin(th) * 0.8
                h = tree.ray_cast(Vector((x, y, H + 0.3)), Vector((0, 0, -1)), 1.0)
                if h[0] is None or h[1].z < 0.6:
                    ok = False
                    break
                ring.append(h[0] + h[1] * (0.0017 - 0.0013 * ir / nr))     # borde que muere en la tela: sin escalón
            if not ok:
                break
            ring_pts.append(ring)
        if not ok:
            continue
        h = tree.ray_cast(Vector((cx, cy, H + 0.3)), Vector((0, 0, -1)), 1.0)
        if h[0] is None:
            continue
        mat = "cardboard"
        for sgn, dz in ((1, 0.0), (-1, -0.0008)):        # cara de arriba y de abajo: calca cerrada de 0,8 mm
            c = body.bm.verts.new(h[0] + h[1] * (0.0017 + dz))
            R = [[body.bm.verts.new(p + Vector((0, 0, dz))) for p in ring] for ring in ring_pts]
            for ia in range(na):
                q = [c, R[0][ia], R[0][(ia + 1) % na]]
                body.face(q if sgn > 0 else list(reversed(q)), mat)
            for ir in range(nr - 1):
                for ia in range(na):
                    ib = (ia + 1) % na
                    q = [R[ir][ia], R[ir + 1][ia], R[ir + 1][ib], R[ir][ib]]
                    body.face(q if sgn > 0 else list(reversed(q)), mat)
            if sgn > 0:
                top_rim = R[-1]
            else:
                for ia in range(na):
                    ib = (ia + 1) % na
                    body.face([top_rim[ia], R[-1][ia], R[-1][ib], top_rim[ib]], mat)
    # almohadas (kit.softgoods, simulación en caché) hundidas 1 cm en el colchón, en la cabecera
    if pillows and r.random() < 0.6:
        head = 1 if r.random() < 0.5 else -1
        npl = 2 if (wide and r.random() < 0.65) else 1
        for k in range(npl):
            py = (k - (npl - 1) / 2) * 0.62 + float(r.uniform(-0.04, 0.04))
            px = head * (L / 2 - 0.30) + float(r.uniform(-0.05, 0.03)) * head
            yaw_p = PI / 2 + float(r.uniform(-0.2, 0.2))
            zs = []
            for dx in (-0.15, 0.0, 0.15):
                for dy in (-0.22, 0.0, 0.22):
                    h = tree.ray_cast(Vector((px + dx, py + dy, H + 0.3)), Vector((0, 0, -1)), 1.0)
                    if h[0] is not None:
                        zs.append(h[0].z)
            if not zs:
                continue
            zp = float(np.median(zs)) - 0.011
            sg.pillow(body, _T(px, py, zp) @ _Rz(yaw_p) @ Matrix.Diagonal((1.06, 1.12, 1.0, 1.0)), seed=int(r.integers(0, 4)),
                      mat="linen" if r.random() < 0.5 else "fabric")
    # al muro: el origen es el centro del lado del muro; el giro nunca mete una esquina en él
    y0 = 0.045 + abs(math.sin(yaw)) * L / 2
    mb.join(body, _Rz(yaw) @ _T(0.0, y0 + W / 2, 0.0))
    return dict(L=L, W=W, y0=y0, yaw=yaw)


# ================================================================================================================ silla
def _splinter_cap(mb, ring, T, rr, mat, long_n=2, depth=0.012, long_len=(0.03, 0.06)):
    """Fractura astillada al final de un madero: anillo medio con entrantes y salientes a lo largo de la veta (T) y
    2–3 astillas largas y delgadas; cierra en un vértice central. `ring` = vértices del extremo (sentido del loft)."""
    n = len(ring)
    ctr = sum((v.co for v in ring), Vector()) / n
    longs = set(int(i) for i in rr.choice(n, size=min(long_n, n), replace=False))
    mid = []
    for i, v in enumerate(ring):
        a = v.co.lerp(ctr, float(rr.uniform(0.35, 0.6)))
        f = float(rr.uniform(0.0, depth))
        if i in longs:
            f = float(rr.uniform(*long_len))
            a = v.co.lerp(ctr, 0.2)
        mid.append(mb.bm.verts.new(a + T * f + (v.co - ctr) * float(rr.uniform(-0.08, 0.05))))
    c = mb.bm.verts.new(ctr + T * float(rr.uniform(0.002, depth * 1.4)))
    for i in range(n):
        j = (i + 1) % n
        mb.face([ring[i], ring[j], mid[j], mid[i]], mat)
        mb.face([mid[i], mid[j], c], mat)


def _lumber(mb, path, w, h, rad, mat, taper=None, up=(0, 0, 1), split0=None, split1=None, n_corner=3):
    """Madero de sección rectangular con aristas redondeadas (radio `rad`) barrido por `path`; taper(s) -> factor de sección.
    split0 / split1 = rng: extremo inicial / final quebrado con astillas (si no, tapa plana con su redondeo)."""
    prof = _rr(w, h, rad, n=n_corner)

    def pf(s, i):
        k = taper(s) if taper else 1.0
        return [(a * k, b * k) for (a, b) in prof]
    rings = _loft_path(mb, path, pf, mat, up=up, cap0=split0 is None, cap1=split1 is None)
    P = [Vector(p) for p in path]
    if split0 is not None:
        _splinter_cap(mb, list(reversed(rings[0])), (P[0] - P[1]).normalized(), split0, mat)
    if split1 is not None:
        _splinter_cap(mb, list(rings[-1]), (P[-1] - P[-2]).normalized(), split1, mat)
    return rings


def _rplate(mb, outline, z0, t, mat, bevel=0.004, M=None):
    """Tabla: contorno 2D extruido de z0 a z0 + t con TODAS sus aristas redondeadas (bisel de 2 segmentos)."""
    tmp = MB()
    tmp.plate(outline, t, mat, m=_T(0, 0, z0))
    res = bmesh.ops.bevel(tmp.bm, geom=list(tmp.bm.edges), offset=bevel, segments=2, profile=0.5, affect="EDGES",
                          clamp_overlap=True)
    for f in res["faces"]:
        f.material_index = tmp.mi(mat)
    mb.join(tmp, M)


def _dowel(mb, p0, p1, d, mat, seg=16):
    mb.cyl(p0, p1, d / 2, seg=seg, mat=mat)


def broken_chair(mb, r):
    """Silla de madera rota (origen: centro en el piso). Construcción real: asiento de 3 tablas (22 mm) con escotes para los
    postes, 4 faldones de 65 × 20 mm, patas delanteras ahusadas de 36 → 28 mm, postes traseros de 36 × 42 mm que se inclinan
    10° arriba del asiento, copete y travesaño curvos, travesaños torneados Ø 20 mm en H y 4 tornillos en el asiento.
    Daño: pata quebrada con astillas (el pedazo queda tirado junto), copete partido, tabla suelta, travesaño zafado; casi
    siempre volcada de lado. Medidas: asiento a 45 cm, 42 × 40 cm, respaldo a 88 cm."""
    mat = "wood" if r.random() < 0.6 else "wood_dark"
    tmp = MB()
    loose = []                                   # piezas sueltas (se ponen en el piso después de volcarla)
    SW, SD, SH, ST = 0.42, 0.40, 0.45, 0.022
    zs = SH - ST                                 # cara de abajo del asiento
    fx, fy = SW / 2 - 0.038, -(SD / 2 - 0.038)   # eje de las patas delanteras
    rx, ry = SW / 2 - 0.038, SD / 2 - 0.045      # eje de los postes traseros a la altura del asiento
    rake = 0.10 / 0.43                           # desplome del poste sobre el asiento
    broken_leg = int(r.integers(0, 4)) if r.random() < 0.55 else -1
    hb = float(r.uniform(0.07, 0.3))
    # patas delanteras (ahusadas)
    for i, sx in enumerate((-1, 1)):
        x = sx * fx
        if broken_leg == i:
            _lumber(tmp, [(x, fy, hb), (x, fy, zs)], 0.036, 0.036, 0.004, mat, taper=lambda s: 0.80 + 0.2 * (hb + s * (zs - hb)) / zs,
                    split0=rng(int(r.integers(1e6))))
            piece = MB()
            _lumber(piece, [(0, 0, 0), (0, 0, hb + 0.01)], 0.036, 0.036, 0.004, mat, taper=lambda s: 0.78 + 0.2 * s * hb / zs,
                    split1=rng(int(r.integers(1e6))))
            loose.append(piece)
        else:
            _lumber(tmp, [(x, fy, 0.0), (x, fy, zs)], 0.036, 0.036, 0.004, mat, taper=lambda s: 0.78 + 0.22 * s)
    # postes traseros: pata + respaldo de una pieza, con el quiebre suave a la altura del asiento
    from kit.clinic import fillet
    for i, sx in enumerate((-1, 1)):
        x = sx * rx
        top = (x, ry + 0.43 * rake * 1.0 + 0.0, 0.88)
        path = [(x, ry + 0.012, 0.0), (x, ry, zs), top]
        path = fillet(path, 0.25, nseg=6)
        if broken_leg == 2 + i:
            k = next(j for j, p in enumerate(path) if p[2] > hb)
            path = [(x, ry + 0.012 * (1 - hb / zs), hb)] + path[k:]
            _lumber(tmp, path, 0.036, 0.042, 0.004, mat, taper=lambda s: 1.0 - 0.15 * s, split0=rng(int(r.integers(1e6))))
            piece = MB()
            _lumber(piece, [(0, 0, 0), (0, 0, hb + 0.01)], 0.036, 0.042, 0.004, mat, split1=rng(int(r.integers(1e6))))
            loose.append(piece)
        else:
            _lumber(tmp, path, 0.036, 0.042, 0.004, mat, taper=lambda s: 1.0 - 0.15 * s)

    def post_y(z):
        return ry + max(0.0, z - zs) * rake

    # faldones (debajo del asiento, a 6 mm de la cara de las patas)
    ah, at = 0.065, 0.02
    for sy, yy in ((-1, fy), (1, ry)):
        tmp.box((-fx + 0.018, yy - at / 2, zs - ah), (fx - 0.018, yy + at / 2, zs - 0.001), mat, bevel=0.003, seg=2)
    for sx in (-1, 1):
        x = sx * (fx + 0.018 - 0.006 - at / 2)
        tmp.box((x - at / 2, fy + 0.018, zs - ah), (x + at / 2, ry - 0.021, zs - 0.001), mat, bevel=0.003, seg=2)
    # travesaños torneados en H (Ø 20 mm, espigas metidas 12 mm en las patas)
    out_rail = int(r.integers(0, 2)) if r.random() < 0.25 else -1
    zst = 0.15
    for i, sx in enumerate((-1, 1)):
        x = sx * fx
        p0, p1 = Vector((x, fy + 0.006, zst)), Vector((x, ry + 0.012 * (1 - zst / zs) - 0.006, zst))
        if i == out_rail:                        # zafado: gira sobre la espiga trasera hasta el piso
            d = p0 - p1
            ang = math.asin(min(0.95, (zst - 0.012) / d.length))
            q = p1 + Vector((d.x, d.y * math.cos(ang), -d.length * math.sin(ang)))
            _dowel(tmp, p1, q, 0.020, mat)
        else:
            _dowel(tmp, p0, p1, 0.020, mat)
    _dowel(tmp, (-fx + 0.006, (fy + ry) / 2, zst + 0.018), (fx - 0.006, (fy + ry) / 2, zst + 0.018), 0.018, mat)
    # asiento: 3 tablas; las laterales llevan escote para los postes
    gap = 0.0015
    bw = (SW + 0.02) / 3
    xa = -(SW + 0.02) / 2
    y_front, y_back = -(SD / 2 + 0.015), SD / 2 + 0.006
    y_notch = ry - 0.021 - 0.003
    loose_board = int(r.integers(0, 3)) if r.random() < 0.2 else -1
    for b in range(3):
        x0, x1 = xa + b * bw + gap / 2, xa + (b + 1) * bw - gap / 2
        if b == 1:
            out = [(x0, y_front), (x1, y_front), (x1, y_back), (x0, y_back)]
        elif b == 0:
            xn = -rx + 0.018 + 0.003
            out = [(x0, y_front), (x1, y_front), (x1, y_back), (xn, y_back), (xn, y_notch), (x0, y_notch)]
        else:
            xn = rx - 0.018 - 0.003
            out = [(x0, y_front), (x1, y_front), (x1, y_notch), (xn, y_notch), (xn, y_back), (x0, y_back)]
        if b == loose_board:
            piece = MB()
            cx = (x0 + x1) / 2
            _rplate(piece, [(x - cx, y) for (x, y) in out], 0.0, ST, mat, bevel=0.003)
            loose.append(piece)
            continue
        _rplate(tmp, out, zs, ST, mat, bevel=0.003)
    # tornillos del asiento a los faldones (cabeza plana avellanada, ras + 0,6 mm)
    for (x, y) in ((-0.13, fy), (0.13, fy), (-0.13, ry), (0.13, ry)):
        _lathe(tmp, [(0.0, SH - 0.001), (0.0042, SH - 0.001), (0.0042, SH + 0.0004), (0.0, SH + 0.0006)], "metal_rust", seg=12,
               M=_T(x, y, 0.0))
    # respaldo: copete (alto 65 mm) y travesaño (45 mm) curvos en planta, con espigas en los postes
    back_broken = r.random() < 0.35

    def rail(zc, hh, broken=False):
        yc = post_y(zc)
        n = 9
        pts = [(-rx + 0.004 + (2 * rx - 0.008) * k / (n - 1), yc + 0.026 * (1 - ((2 * k / (n - 1)) - 1) ** 2), zc) for k in range(n)]
        if not broken:
            _lumber(tmp, pts, 0.022, hh, 0.005, mat, up=(0, 0, 1))
            return
        cut = int(r.integers(3, 6))
        left, right = pts[:cut + 1], pts[cut:]
        _lumber(tmp, left, 0.022, hh, 0.005, mat, split1=rng(int(r.integers(1e6))))
        # la otra mitad cuelga de su espiga (gira hacia abajo sobre el poste)
        piv = Vector(right[-1])
        ang = -float(r.uniform(0.5, 1.1))
        Mr = _T(*piv) @ Matrix.Rotation(ang, 4, Vector((0, 1, 0))) @ _T(*(-piv))
        rr2 = [tuple(Mr @ Vector(p)) for p in right]
        _lumber(tmp, rr2, 0.022, hh, 0.005, mat, split0=rng(int(r.integers(1e6))))
    rail(0.845, 0.065, broken=back_broken)
    rail(0.64, 0.045)
    # volcada de lado (o de frente si le falta una pata delantera)
    toppled = r.random() < (0.8 if broken_leg >= 0 else 0.4)
    if toppled:                                  # gira sobre su centro (no sobre el origen) y se re-centra
        side = 1 if r.random() < 0.5 else -1
        tmp.transform(_T(0, 0, 0.3) @ Matrix.Rotation(side * PI / 2, 4, "Y") @ _Rx(float(r.uniform(-0.12, 0.12))) @ _T(0, 0, -0.3))
    vs = tmp.bm.verts
    bx0, bx1 = min(v.co.x for v in vs), max(v.co.x for v in vs)
    by0, by1 = min(v.co.y for v in vs), max(v.co.y for v in vs)
    tmp.transform(_T(-(bx0 + bx1) / 2, -(by0 + by1) / 2, -min(v.co.z for v in vs)))
    hx, hy = (bx1 - bx0) / 2, (by1 - by0) / 2
    # piezas sueltas: tiradas junto a la silla, fuera de su huella, apoyadas en el piso
    for k, piece in enumerate(loose):
        xs = [v.co.x for v in piece.bm.verts]
        zp = [v.co.z for v in piece.bm.verts]
        if max(zp) - min(zp) > max(xs) - min(xs):          # pata: se acuesta
            piece.transform(_Ry(PI / 2))
        pv = piece.bm.verts
        piece.transform(_T(-(min(v.co.x for v in pv) + max(v.co.x for v in pv)) / 2,
                           -(min(v.co.y for v in pv) + max(v.co.y for v in pv)) / 2, -min(v.co.z for v in pv)))
        rz = float(r.uniform(0, 2 * PI))
        piece.transform(_Rz(rz))
        ex = max(abs(v.co.x) for v in pv)
        ey = max(abs(v.co.y) for v in pv)
        sd = int(r.integers(0, 4))
        t = float(r.uniform(-0.6, 0.6))
        px, py = [(hx + ex + 0.04, t * hy), (-(hx + ex + 0.04), t * hy), (t * hx, hy + ey + 0.04), (t * hx, -(hy + ey + 0.04))][sd]
        tmp.join(piece, _T(px, py, 0.0))
    mb.join(tmp, _Rz(float(r.uniform(0, 2 * PI))))


# ================================================================================================================ basura
_CAN = [(0.0, 0.0095), (0.012, 0.0086), (0.020, 0.0062), (0.0242, 0.0022), (0.0252, 0.0002), (0.0268, 0.0004), (0.0298, 0.0038),
        (0.0322, 0.0088), (0.0331, 0.0140), (0.0331, 0.0600), (0.0331, 0.1040), (0.0319, 0.1082), (0.0296, 0.1128),
        (0.0276, 0.1172), (0.0272, 0.1196), (0.0278, 0.1206), (0.0282, 0.1216), (0.0277, 0.1222), (0.0263, 0.1216),
        (0.0257, 0.1188), (0.0238, 0.1183), (0.0, 0.1190)]


def _can(mb, M, r, state="intact"):
    """Lata de 355 ml (Ø 66,2 × 122,2 mm): fondo de domo con anillo de apoyo, cuello reducido, tapa con ceja y fondo hundido,
    anillo abridor remachado y boca abierta. state: 'intact' | 'dented' | 'crushed' (aplastada a lo largo con pliegues de
    acordeón). Origen en el centro del fondo, eje +Z."""
    tmp = MB()
    _lathe(tmp, _CAN, "aluminium", seg=24)
    nz = _off(r)
    if state != "intact":
        dents = [(float(r.uniform(0, 2 * PI)), float(r.uniform(0.025, 0.095)), float(r.uniform(0.012, 0.03)), float(r.uniform(0.003, 0.009)))
                 for _ in range(int(r.integers(1, 4)))]
        crush = float(r.uniform(0.35, 0.6)) if state == "crushed" else 1.0
        kf = int(r.integers(5, 8))
        for v in tmp.bm.verts:
            x, y, z = v.co
            rad = math.hypot(x, y)
            if rad < 0.02 or not (0.012 < z < 0.106):
                if state == "crushed" and z >= 0.106:
                    v.co.z = z - (0.094 * (1 - crush))
                continue
            a = math.atan2(y, x)
            push = 0.0
            for (da, dzc, dr, dep) in dents:
                dd = math.hypot(((a - da + PI) % (2 * PI) - PI) * 0.0331, z - dzc)
                push += dep * math.exp(-(dd / dr) ** 2)
            if state == "crushed":
                t = (z - 0.012) / 0.094
                zn = 0.012 + t * 0.094 * crush
                fold = math.sin(t * PI * kf + 1.3 * math.sin(a * 3 + nz[0]))
                push -= 0.006 * (1 - crush) * 2.2 * fold * math.sin(PI * t)
                v.co.z = zn
            k = (rad - push) / rad
            v.co.x, v.co.y = x * k, y * k
    # anillo abridor (remachado al centro) y boca abierta
    tab = [(-0.0045, -0.003), (0.0045, -0.003), (0.0065, 0.004), (0.0060, 0.0125), (0.0, 0.0165), (-0.0060, 0.0125), (-0.0065, 0.004)]
    zt = max(v.co.z for v in tmp.bm.verts if math.hypot(v.co.x, v.co.y) < 0.022)
    _rplate(tmp, tab, zt + 0.0002, 0.0007, "aluminium", bevel=0.0003, M=_Rz(float(r.uniform(-0.3, 0.3))))
    _lathe(tmp, [(0.0, zt), (0.0018, zt), (0.0016, zt + 0.0013), (0.0, zt + 0.0014)], "aluminium", seg=10)
    mouth = [(-0.0065, -0.0165), (0.0065, -0.0165), (0.0072, -0.0105), (0.0, -0.0065), (-0.0072, -0.0105)]
    _rplate(tmp, mouth, zt + 0.0001, 0.0006, "cable", bevel=0.0002)
    mb.join(tmp, M)


_BOTTLE = [(0.0, 0.0060), (0.0150, 0.0046), (0.0255, 0.0012), (0.0290, 0.0000), (0.0303, 0.0030), (0.0303, 0.0600),
           (0.0303, 0.1150), (0.0292, 0.1290), (0.0255, 0.1440), (0.0200, 0.1580), (0.0155, 0.1710), (0.0136, 0.1850),
           (0.0129, 0.2000), (0.0128, 0.2110), (0.0136, 0.2135), (0.0146, 0.2165), (0.0146, 0.2228), (0.0136, 0.2272),
           (0.0112, 0.2286), (0.0094, 0.2280), (0.0090, 0.2240), (0.0, 0.2230)]


def _bottle(mb, M, r, broken=False, mat="amber"):
    """Botella de cerveza de cuello largo de 355 ml (Ø 60,6 × 228,6 mm, vidrio de 3 mm): fondo con picadura, hombro,
    cuello y corona; broken: cuello quebrado en dientes. Origen en el centro del fondo, eje +Z. Devuelve la altura."""
    tmp = MB()
    if not broken:
        _lathe(tmp, _BOTTLE, mat, seg=24)
        mb.join(tmp, M)
        return 0.2286
    zb = float(r.uniform(0.125, 0.175))
    outer = [p for p in _BOTTLE[:-6] if p[1] < zb]
    ro = next(p[0] for p in _BOTTLE if p[1] >= zb)
    prof = outer + [(ro, zb), (ro - 0.003, zb), (ro - 0.003, zb - 0.004)]
    prof = [p for p in prof if p[0] > 0] + [(0.0, 0.009)]
    prof = [(0.0, 0.006)] + prof[1:]
    # perfil cerrado de vidrio: exterior hasta la fractura, canto de 3 mm y pared interior hasta el fondo
    inner = [(max(rr_ - 0.003, 0.004), z) for (rr_, z) in reversed(outer[2:]) if z > 0.012]
    prof = outer + [(ro, zb), (ro - 0.003, zb)] + inner + [(0.0, 0.0095)]
    _lathe(tmp, prof, mat, seg=24)
    # dientes de la fractura: los vértices del canto suben o bajan
    off = _off(r)
    for v in tmp.bm.verts:
        if v.co.z > zb - 0.0005:
            a = math.atan2(v.co.y, v.co.x)
            v.co.z += 0.012 * (_mnoise.noise(Vector((math.cos(a) * 1.3, math.sin(a) * 1.3, 0.0)) + Vector(off)) + 0.25 * math.sin(5 * a + off[0]))
    mb.join(tmp, M)
    return zb


def _shard(mb, M, r, mat):
    """Vidrio roto: casco de cilindro (r 30 mm) de 3 mm con contorno irregular, apoyado en el piso."""
    n = int(r.integers(5, 8))
    pts = [(float(r.uniform(0.012, 0.03)) * math.cos(2 * PI * i / n + float(r.uniform(-0.3, 0.3))),
            float(r.uniform(0.01, 0.025)) * math.sin(2 * PI * i / n)) for i in range(n)]
    tmp = MB()
    tmp.plate(pts, 0.003, mat)
    for v in tmp.bm.verts:
        v.co.z += 0.004 * (v.co.x / 0.03) ** 2
    mb.join(tmp, M)


def _sheet(mb, M, r, w=0.216, h=0.279, t=0.0005):
    """Hoja tamaño carta (216 × 279 mm) curvada, con una esquina doblada y arrugas: dos caras de papel y canto cerrado."""
    nx, ny = 9, 12
    curl = float(r.uniform(-1.6, 1.6))
    off = _off(r)
    corner = (int(r.integers(0, 2)), int(r.integers(0, 2))) if r.random() < 0.5 else None
    P = {}
    for i in range(nx + 1):
        for j in range(ny + 1):
            x, y = (i / nx - 0.5) * w, (j / ny - 0.5) * h
            z = curl * 0.5 * (x * x) + 0.002 * _mnoise.noise(Vector((x * 18 + off[0], y * 18 + off[1], 0.0)))
            if corner is not None:
                cx, cy = (w / 2) * (2 * corner[0] - 1), (h / 2) * (2 * corner[1] - 1)
                dd = (abs(x - cx) + abs(y - cy)) / 0.09
                if dd < 1:
                    z += 0.025 * (1 - dd)
            P[(i, j)] = Vector((x, y, z))
    zmin = min(p.z for p in P.values())
    for k in P:
        P[k].z -= zmin - 0.0004
    tmp = MB()
    top = {k: tmp.bm.verts.new(p + Vector((0, 0, t))) for k, p in P.items()}
    bot = {k: tmp.bm.verts.new(p) for k, p in P.items()}
    for i in range(nx):
        for j in range(ny):
            tmp.face([top[(i, j)], top[(i + 1, j)], top[(i + 1, j + 1)], top[(i, j + 1)]], "paper")
            tmp.face([bot[(i, j)], bot[(i, j + 1)], bot[(i + 1, j + 1)], bot[(i + 1, j)]], "paper")
    ring = [(i, 0) for i in range(nx)] + [(nx, j) for j in range(ny)] + [(i, ny) for i in range(nx, 0, -1)] + [(0, j) for j in range(ny, 0, -1)]
    for a, b in zip(ring, ring[1:] + ring[:1]):
        tmp.face([bot[a], bot[b], top[b], top[a]], "paper")
    mb.join(tmp, M)


def _crumple(mb, M, r, size, mat="paper", squash=0.8, N=5, amp=0.28):
    """Papel arrugado: esfera-cubo con pliegues duros (ruido de valor absoluto), base aplastada contra el piso."""
    from kit.damage import _cube_sphere
    dirs, quads = _cube_sphere(N)
    off = _off(r)
    tmp = MB()
    vs = []
    for d in dirs:
        k = 1.0 - amp * abs(_mnoise.noise(d * 2.2 + Vector(off))) - amp * 0.5 * abs(_mnoise.noise(d * 5.0 + Vector(off) * 1.3))
        p = Vector((d.x * size, d.y * size * 0.9, d.z * size * squash)) * k
        vs.append(tmp.bm.verts.new(p))
    for q in quads:
        tmp.face([vs[i] for i in q], mat)
    zmin = min(v.co.z for v in vs)
    for v in vs:
        if v.co.z < zmin + size * 0.25:
            v.co.z = zmin + (v.co.z - zmin) * 0.4
    tmp.transform(_T(0, 0, -min(v.co.z for v in vs)))
    mb.join(tmp, M)


def _bag(mb, M, r):
    """Bolsa de plástico de súper arrugada en el piso (~30 × 20 × 6 cm) con las dos asas de tira aplastadas: pliegues
    duros (ruido de valor absoluto en 3 octavas) — el polietileno se quiebra en aristas, no se ve como una piedra lisa."""
    from kit.damage import _cube_sphere
    dirs, quads = _cube_sphere(10)
    off = Vector(_off(r))
    tmp = MB()
    vs = []
    for d in dirs:
        wr = (0.16 * abs(_mnoise.noise(d * 3.1 + off)) + 0.10 * abs(_mnoise.noise(d * 7.3 + off * 1.1))
              + 0.06 * abs(_mnoise.noise(d * 15.0 + off * 1.3)))
        p = Vector((d.x * 0.15, d.y * 0.10, d.z * 0.035)) * (1.0 - wr)
        p.z += 0.012 * _mnoise.noise(Vector((d.x * 2.0, d.y * 2.0, 0.0)) + off)
        vs.append(tmp.bm.verts.new(p))
    mat = "plastic" if r.random() < 0.6 else "plastic_blue"
    for q in quads:
        tmp.face([vs[i] for i in q], mat)
    zmin = min(v.co.z for v in vs)
    for v in vs:
        if v.co.z < zmin + 0.015:
            v.co.z = zmin + (v.co.z - zmin) * 0.3
    tmp.transform(_T(0, 0, -min(v.co.z for v in vs)))
    for s in (-1, 1):                            # asas: tiras de 25 mm sobre el piso
        path = [(0.13 + 0.09 * math.sin(PI * k / 10), s * 0.03 + s * 0.035 * math.sin(PI * k / 10) - 0.03 * (k / 10 - 0.5),
                 0.004 + 0.012 * (1 - abs(k / 5 - 1))) for k in range(11)]
        with tmp.soft():
            _loft_path(tmp, path, lambda u, i: _rr(0.022, 0.0012, 0.0005, n=1), mat, up=(0, 0, 1))
    mb.join(tmp, M)


def _cardboard(mb, M, r):
    """Pedazo de caja de cartón corrugado (4 mm) con un doblez a 20–40° y el canto rasgado."""
    w, h = float(r.uniform(0.22, 0.4)), float(r.uniform(0.18, 0.3))
    ang = math.radians(float(r.uniform(20, 40)))
    tmp = MB()
    n = 7
    tear = [(w * (0.5 + 0.5 * k / n), h + float(r.uniform(-0.03, 0.0))) for k in range(n + 1)]
    out1 = [(0.0, 0.0), (w / 2, 0.0), (w / 2, h)] + [(w * 0.5 * (1 - k / n), h + float(r.uniform(-0.025, 0.0))) for k in range(1, n + 1)]
    _rplate(tmp, [(x - w / 2, y) for (x, y) in out1], 0.0, 0.004, "cardboard", bevel=0.0012)
    flap = MB()
    out2 = [(0.0, 0.0), (w / 2, 0.0)] + [(w / 2 - x + 0.0, y) for (x, y) in reversed(tear)][:-1] + [(0.0, h)]
    out2 = [(0.0, 0.0), (w / 2, 0.0), (w / 2, h * 0.9)] + [(w * 0.5 * (1 - k / n), h * 0.9 + float(r.uniform(-0.02, 0.0))) for k in range(1, n + 1)]
    _rplate(flap, out2, 0.0, 0.004, "cardboard", bevel=0.0012)
    tmp.join(flap, _Ry(-ang))
    zmin = min(v.co.z for v in tmp.bm.verts)
    tmp.transform(_T(0, -h / 2, -zmin))
    mb.join(tmp, M)


def trash(mb, r, n_papers=10, n_bottles=3, fits=None):
    """Montón de basura en el piso (origen al centro, radio ~0,7 m): hojas, bolas de papel, latas, botellas (enteras o rotas,
    con vidrios), bolsas de plástico y cartón. fits(x, y, rad) -> bool opcional: descarta lo que no cabe en el cuarto."""
    used = []

    def spot(rad, tries=8):
        for _ in range(tries):
            a = r.uniform(0, 6.3)
            d = r.uniform(0.0, 0.7)
            x, y = d * math.cos(a), d * math.sin(a)
            if all((x - u[0]) ** 2 + (y - u[1]) ** 2 >= (rad + u[2]) ** 2 for u in used) and (fits is None or fits(x, y, rad)):
                used.append((x, y, rad))
                return x, y
        return None
    for _ in range(int(n_papers)):
        if r.random() < 0.55:
            q = spot(0.19)
            if q:
                _sheet(mb, _T(q[0], q[1], 0.0) @ _Rz(r.uniform(0, 6.3)), r)
        else:
            s = float(r.uniform(0.03, 0.045))
            q = spot(s + 0.01)
            if q:
                _crumple(mb, _T(q[0], q[1], 0.0) @ _Rz(r.uniform(0, 6.3)), r, s)
    for _ in range(int(n_bottles)):
        roll = r.random()
        if roll < 0.45:
            st = "intact" if r.random() < 0.3 else ("dented" if r.random() < 0.5 else "crushed")
            q = spot(0.07)
            if q is None:
                continue
            tmp = MB()
            _can(tmp, Matrix(), r, st)
            if st == "crushed" or r.random() < 0.75:     # acostada
                tmp.transform(_Ry(PI / 2))
                tmp.transform(_T(-0.06, 0, -min(v.co.z for v in tmp.bm.verts)))
            mb.join(tmp, _T(q[0], q[1], 0.0) @ _Rz(r.uniform(0, 6.3)))
        elif roll < 0.85:
            broken = r.random() < 0.45
            mat = "amber" if r.random() < 0.7 else "glass"
            q = spot(0.13)
            if q is None:
                continue
            tmp = MB()
            hgt = _bottle(tmp, Matrix(), r, broken, mat)
            if r.random() < 0.8:
                tmp.transform(_Ry(PI / 2))
                tmp.transform(_T(-hgt / 2, 0, -min(v.co.z for v in tmp.bm.verts)))
            rz = r.uniform(0, 6.3)
            mb.join(tmp, _T(q[0], q[1], 0.0) @ _Rz(rz))
            if broken:
                for _k in range(int(r.integers(3, 6))):
                    a, d = r.uniform(0, 6.3), r.uniform(0.08, 0.2)
                    sx, sy = q[0] + d * math.cos(a), q[1] + d * math.sin(a)
                    if fits is None or fits(sx, sy, 0.03):
                        _shard(mb, _T(sx, sy, 0.0) @ _Rz(r.uniform(0, 6.3)), r, mat)
        else:
            q = spot(0.17)
            if q:
                _bag(mb, _T(q[0], q[1], 0.0) @ _Rz(r.uniform(0, 6.3)), r)
    if r.random() < 0.3:
        q = spot(0.24)
        if q:
            _cardboard(mb, _T(q[0], q[1], 0.0) @ _Rz(r.uniform(0, 6.3)), r)
    if r.random() < 0.25:
        q = spot(0.17)
        if q:
            _bag(mb, _T(q[0], q[1], 0.0) @ _Rz(r.uniform(0, 6.3)), r)


# ================================================================================================================ foco
_A19 = [(0.0, 0.0), (0.0090, 0.0010), (0.0140, 0.0016), (0.0150, 0.0040), (0.0145, 0.0060)]   # contacto y aislante (abajo->arriba invertido)


def ceiling_bulb(mb, r, drop):
    """Foco desnudo colgando de su cordón (origen: punto del techo; cuelga hacia -Z).
    Roseta de techo Ø 76 mm con 2 tornillos, cordón dúplex trenzado (2 conductores Ø 3,2 mm, paso 28 mm), portalámparas de
    baquelita Ø 39 × 54 mm con anillo, foco A19 (Ø 60, 110 mm con casquillo E26 roscado, vástago y filamento); a veces el
    vidrio está roto en dientes o falta el foco (se ve la rosca del portalámparas)."""
    # roseta: base con ceja, cuerpo y prensacable; 2 tornillos
    _lathe(mb, [(0.0, 0.0), (0.038, 0.0), (0.038, -0.004), (0.0365, -0.0065), (0.031, -0.010), (0.024, -0.020), (0.016, -0.024),
                (0.0085, -0.025), (0.0075, -0.034), (0.0058, -0.036), (0.0, -0.036)], "plastic", seg=32)
    for a in (0.0, PI):
        x, y = 0.027 * math.cos(a), 0.027 * math.sin(a)
        _lathe(mb, [(0.0, -0.0128), (0.0034, -0.0128), (0.0034, -0.0124), (0.0026, -0.0135), (0.0, -0.0139)], "steel", seg=12,
               M=_T(x, y, 0.0) @ Matrix.Rotation(0.32 if a == 0 else -0.32, 4, Vector((-math.sin(a), math.cos(a), 0))))
    # cordón dúplex trenzado: dos conductores enrollados uno en otro, con una leve curva
    sway = Vector((float(r.uniform(-0.03, 0.03)), float(r.uniform(-0.03, 0.03)), 0.0))
    z0, z1 = -0.034, -drop - 0.006
    n = max(20, int((z0 - z1) / 0.009))
    ph = float(r.uniform(0, 2 * PI))
    with mb.soft():
        for k in (0, 1):
            pts = []
            for i in range(n + 1):
                t = i / n
                c = Vector((0, 0, z0 + (z1 - z0) * t)) + sway * math.sin(PI * t) * 0.6
                a = ph + k * PI + 2 * PI * (z0 - c.z) / 0.028
                pts.append(c + Vector((math.cos(a), math.sin(a), 0.0)) * 0.0016)
            mb.tube(pts, 0.0016, seg=12, mat="cable")
    # portalámparas de baquelita: tapa con buje, cuerpo, anillo roscado y boca del casquillo
    z = -drop
    holder = "polymer" if r.random() < 0.6 else "plastic"
    _lathe(mb, [(0.0, z), (0.0045, z), (0.0050, z - 0.006), (0.0115, z - 0.008), (0.0175, z - 0.012), (0.0195, z - 0.018),
                (0.0195, z - 0.036), (0.0188, z - 0.038), (0.0205, z - 0.039), (0.0275, z - 0.040), (0.0280, z - 0.044),
                (0.0270, z - 0.046), (0.0185, z - 0.047), (0.0175, z - 0.054), (0.0140, z - 0.054), (0.0140, z - 0.050),
                (0.0, z - 0.050)], holder, seg=32)
    roll = r.random()
    zb = z - 0.050                                    # boca del portalámparas: el casquillo entra 22 mm
    if roll < 0.12:                                   # sin foco: se ve la rosca del casquillo y el contacto central
        _lathe(mb, [(0.0, zb - 0.0001), (0.0132, zb - 0.0001), (0.0132, zb - 0.0004), (0.0, zb - 0.0004)], "brass", seg=24,
               rmod=lambda a: 1.0)
        return
    # casquillo E26 roscado (Ø 26,5 mm) visible bajo el portalámparas + aislante negro + contacto
    zs = zb - 0.0005
    thread = []
    for i in range(9):
        thread.append((0.0130 if i % 2 == 0 else 0.0120, zs - 0.0022 * i))
    _lathe(mb, [(0.0, zs + 0.004), (0.0128, zs + 0.004)] + thread + [(0.0118, zs - 0.0185), (0.0110, zs - 0.0195)], "aluminium", seg=24)
    zg = zs - 0.0195
    broken = roll < 0.32
    glass = [(0.0110, zg), (0.0125, zg - 0.006), (0.0150, zg - 0.016), (0.0200, zg - 0.026), (0.0255, zg - 0.036), (0.0290, zg - 0.048),
             (0.0300, zg - 0.060), (0.0292, zg - 0.071), (0.0262, zg - 0.081), (0.0205, zg - 0.0885), (0.0120, zg - 0.0925),
             (0.0, zg - 0.0935)]
    if not broken:
        _lathe(mb, [(0.0, zg + 0.0004)] + glass, "glass", seg=32)
    else:                                             # vidrio roto: queda un cuello con dientes y el vástago con el filamento
        tmp = MB()
        zc = zg - float(r.uniform(0.012, 0.03))
        outer = [p for p in glass if p[1] > zc]
        ro = next(p[0] for p in glass if p[1] <= zc)
        inner = [(max(p[0] - 0.0007, 0.004), p[1]) for p in reversed(outer)]
        _lathe(tmp, [(0.0, zg + 0.0004)] + outer + [(ro, zc), (ro - 0.0007, zc)] + inner + [(0.0, zg - 0.0003)], "glass", seg=32)
        off = _off(r)
        for v in tmp.bm.verts:
            if v.co.z < zc + 0.0006 and math.hypot(v.co.x, v.co.y) > 0.005:
                a = math.atan2(v.co.y, v.co.x)
                v.co.z -= 0.006 * (0.5 + 0.5 * _mnoise.noise(Vector((math.cos(a) * 2, math.sin(a) * 2, 0)) + Vector(off)))
        mb.join(tmp)
    # vástago, alambres de soporte y filamento en espiral (tungsteno)
    _lathe(mb, [(0.0, zg), (0.0050, zg), (0.0042, zg - 0.016), (0.0025, zg - 0.024), (0.0, zg - 0.025)], "glass", seg=12)
    zf = zg - 0.048
    with mb.soft():
        for s in (-1, 1):
            mb.tube([(s * 0.0018, 0.0, zg - 0.022), (s * 0.0045, 0.0, zg - 0.036), (s * 0.0060, 0.0, zf)], 0.00035, seg=6, mat="steel")
        coil = [(-0.006 + 0.012 * k / 60, 0.0009 * math.sin(k * 1.9), zf - 0.0009 * math.cos(k * 1.9) - 0.0015 * math.sin(PI * k / 60))
                for k in range(61)]
        mb.tube(coil, 0.0002, seg=6, mat="steel")


# ================================================================================================================ placa
def _plate_ring(w, h, rad, n=3):
    return [Vector((x, 0.0, y)) for (x, y) in _rr(w, h, rad, n=n)]


def wall_plate(mb, kind, r=None):
    """Apagador o contacto (origen: cara del muro, +y hacia el cuarto). Placa de 1 salida de 70 × 114 × 6 mm con cantos
    redondeados y cara abombada, ventana del mecanismo, palanca (apagador) o dos tomas con ranuras y tierra (contacto),
    tornillos 6-32 de cabeza oval ranurada a 60,3 mm (apagador) o uno al centro (contacto). r (opcional): placa vieja que
    cuelga de un tornillo."""
    W, H = 0.070, 0.114
    tmp = MB()
    # placa: anillos exterior→interior (canto redondeado de 3 mm, cara abombada 1 mm) alrededor de la ventana
    if kind == "switch":
        hw, hh, hr = 0.0056, 0.0119, 0.0012                 # ventana de 11 × 24 mm
    else:
        hw, hh, hr = 0.0175, 0.048, 0.006                   # ventana del contacto doble (2 tomas en una cara)
    rings = []
    for (sw, sh, sr, y) in ((W, H, 0.004, 0.0), (W - 0.0004, H - 0.0004, 0.0038, 0.0032), (W - 0.0035, H - 0.0035, 0.0028, 0.0055),
                            (W - 0.010, H - 0.010, 0.004, 0.0062), (2 * hw + 0.004, 2 * hh + 0.004, hr + 0.002, 0.0058),
                            (2 * hw, 2 * hh, hr, 0.0052), (2 * hw, 2 * hh, hr, 0.0012)):
        rings.append([tmp.bm.verts.new(p + Vector((0, y, 0))) for p in _plate_ring(sw, sh, sr)])
    k = len(rings[0])
    for i in range(len(rings) - 1):
        for j in range(k):
            jj = (j + 1) % k
            tmp.face([rings[i][j], rings[i][jj], rings[i + 1][jj], rings[i + 1][j]], "plastic")
    back = [tmp.bm.verts.new(p + Vector((0, 0.0012, 0))) for p in _plate_ring(W - 0.003, H - 0.003, 0.003)]
    for j in range(k):                                     # cara trasera (cerca del muro) del aro de la placa
        jj = (j + 1) % k
        tmp.face([rings[-1][j], rings[-1][jj], back[jj], back[j]], "plastic")
        tmp.face([back[j], back[jj], rings[0][jj], rings[0][j]], "plastic")
    hang = r is not None and kind == "switch" and r.random() < 0.15
    dev = MB()                                             # mecanismo (fijo en la chalupa aunque la placa cuelgue)
    if kind == "switch":
        dev.box((-hw + 0.0003, 0.0003, -hh + 0.0003), (hw - 0.0003, 0.0040, hh - 0.0003), "plastic", bevel=0.0006, seg=1)
        up = 1 if (r is None or r.random() < 0.5) else -1
        lever = [Vector((0, 0.0040, 0)), Vector((0, 0.0090, up * 0.0018)), Vector((0, 0.0140, up * 0.0042))]
        _loft_path(dev, lever, lambda s, i: _rr(0.0070 - 0.0012 * s, 0.0050 - 0.0008 * s, 0.0015, n=2), "plastic", up=(0, 0, 1))
        screws = [(0.0, 0.0302), (0.0, -0.0302)]
    else:
        dev.box((-hw + 0.0003, 0.0003, -hh + 0.0003), (hw - 0.0003, 0.0058, hh - 0.0003), "plastic", bevel=0.0008, seg=1)
        for zc in (0.0195, -0.0195):                       # dos tomas: cara ovalada con ranuras y orificio de tierra
            face = MB()
            _rplate(face, [(0.0165 * math.cos(a), 0.0135 * math.sin(a)) for a in (2 * PI * i / 24 for i in range(24))],
                    0.0, 0.0012, "plastic", bevel=0.0004)
            dev.join(face, _T(0, 0.0058, zc) @ _Rx(-PI / 2))
            for x, ln in ((-0.0064, 0.0079), (0.0064, 0.0063)):
                dev.box((x - 0.0009, 0.0068, zc + 0.002 - ln / 2), (x + 0.0009, 0.0075, zc + 0.002 + ln / 2), "cable", bevel=0.0)
            _lathe(dev, [(0.0, 0.0), (0.0025, 0.0), (0.0025, 0.0007), (0.0, 0.0007)], "cable", seg=12,
                   M=_T(0, 0.0068, zc - 0.0075) @ _Rx(-PI / 2))
        screws = [(0.0, 0.0)]
    # tornillos 6-32 de cabeza oval ranurada (Ø 7 mm); la placa que cuelga perdió el de abajo
    for (x, z) in screws:
        if hang and z < 0:
            continue
        y = 0.0057 if kind == "switch" else 0.0071
        M = _T(x, y, z) @ _Rx(-PI / 2) @ _Rz(float(r.uniform(0, PI)) if r is not None else 0.6)
        _lathe(tmp, [(0.0, -0.0004), (0.0035, -0.0004), (0.0035, 0.0003), (0.0028, 0.0012), (0.0016, 0.0017), (0.0, 0.0019)], "steel",
               seg=16, M=M)
        tmp.box((-0.0029, -0.00035, 0.0011), (0.0029, 0.00035, 0.0021), "cable", bevel=0.0, m=M)
    if hang:                                               # gira en su tornillo de arriba (flojo), por fuera de la palanca
        ang = float(r.uniform(0.25, 0.6)) * (1 if r.random() < 0.5 else -1)
        tmp.transform(_T(0, 0.0, 0.0302) @ Matrix.Rotation(ang, 4, "Y") @ _T(0, 0.0, -0.0302))
        tmp.transform(_T(0, 0.0146, 0))                   # apoyada en la punta de la palanca
    mb.join(dev)
    mb.join(tmp)


# ================================================================================================================ escombro
def plaster_debris(mb, r, n_chunks=7, spread=0.55, fits=None):
    """Aplanado caído al pie del muro: lajas de mortero de 10–20 mm combadas, con cara pintada (plaster), cara de atrás de
    mortero y canto de fractura irregular; trozos de concreto rugosos y un montoncito de polvo y arenilla."""
    from kit import damage as dm
    for _ in range(int(n_chunks)):
        a = r.uniform(0, 2 * math.pi)
        rad = r.uniform(0.05, spread)
        cx, cy = rad * math.cos(a), rad * math.sin(a) * 0.6
        if fits is not None and not fits(cx, cy, 0.18):
            continue
        if r.random() < 0.75:
            _plaster_flake(mb, r, _T(cx, cy, 0.0) @ _Rz(r.uniform(0, 6.3)))
        else:
            mb.join(dm.chunk(size=float(r.uniform(0.05, 0.14)), seed=int(r.integers(1e6)), detail="high"),
                    _T(cx, cy, 0.0) @ _Rz(r.uniform(0, 6.3)))
    # polvo y arenilla: loma baja (máx. 12 mm) que muere en el piso
    s = spread * 0.9
    off = _off(r)
    na, nr = 24, 5
    lim = []                                      # la loma se encoge donde hay un muro o un paso cerca
    for ia in range(na):
        th = 2 * PI * ia / na
        k = 1.0
        if fits is not None:
            for k in (1.0, 0.75, 0.5, 0.3):
                if fits(s * k * math.cos(th), 0.6 * s * k * math.sin(th), 0.02):
                    break
        lim.append(k)
    c = mb.bm.verts.new((0.0, 0.0, 0.012))
    R = []
    for ir in range(1, nr + 1):
        ring = []
        for ia in range(na):
            th = 2 * PI * ia / na
            k = ir / nr
            rr_ = s * k * (0.75 + 0.25 * _mnoise.noise(Vector((math.cos(th) * 1.4, math.sin(th) * 1.4, 0.0)) + Vector(off))) * lim[ia]
            z = 0.012 * (1 - k ** 1.5) + 0.003 * _mnoise.noise(Vector((math.cos(th) * 4, math.sin(th) * 4, k * 3)) + Vector(off))
            ring.append(mb.bm.verts.new((rr_ * math.cos(th), 0.6 * rr_ * math.sin(th), max(z, 0.0) if ir < nr else -0.002)))
        R.append(ring)
    with mb.soft():
        for ia in range(na):
            mb.face([c, R[0][ia], R[0][(ia + 1) % na]], "rubble")
        for ir in range(nr - 1):
            for ia in range(na):
                ib = (ia + 1) % na
                mb.face([R[ir][ia], R[ir + 1][ia], R[ir + 1][ib], R[ir][ib]], "rubble")
        mb.face(list(reversed(R[-1])), "rubble")


def _plaster_flake(mb, r, M):
    """Laja de aplanado: contorno irregular de 8–12 lados, espesor 10–20 mm, combada (se curvó al secarse y caer), cara
    de arriba pintada, canto de fractura con dientes. Apoyada en el piso por su punto más bajo."""
    k = int(r.integers(8, 13))
    s = float(r.uniform(0.06, 0.2))
    t = float(r.uniform(0.010, 0.020))
    pts = []
    for i in range(k):
        a = 2 * PI * (i + float(r.uniform(-0.3, 0.3))) / k
        pts.append((s * float(r.uniform(0.55, 1.0)) * math.cos(a), s * float(r.uniform(0.45, 0.85)) * math.sin(a)))
    bend = float(r.uniform(-0.6, 0.6))
    tmp = MB()
    bot = [tmp.bm.verts.new((x, y, 0.0)) for (x, y) in pts]
    mid = [tmp.bm.verts.new((x * 1.0, y * 1.0, t * float(r.uniform(0.35, 0.65)))) for (x, y) in pts]
    top = [tmp.bm.verts.new((x * float(r.uniform(0.9, 0.98)), y * float(r.uniform(0.9, 0.98)), t)) for (x, y) in pts]
    for i in range(k):
        mid[i].co.x += float(r.uniform(-0.004, 0.004))
        mid[i].co.y += float(r.uniform(-0.004, 0.004))
    tmp.face(list(reversed(bot)), "mortar")
    tmp.face(top, "plaster")
    for i in range(k):
        j = (i + 1) % k
        tmp.face([bot[i], bot[j], mid[j], mid[i]], "mortar")
        tmp.face([mid[i], mid[j], top[j], top[i]], "mortar")
    bmesh.ops.triangulate(tmp.bm, faces=[f for f in tmp.bm.faces if len(f.verts) > 4])
    for v in tmp.bm.verts:
        v.co.z += bend * (v.co.x ** 2 + 0.5 * v.co.y ** 2)
    tilt = _Rx(float(r.uniform(-0.12, 0.12))) @ _Ry(float(r.uniform(-0.12, 0.12)))
    tmp.transform(tilt)
    tmp.transform(_T(0, 0, -min(v.co.z for v in tmp.bm.verts)))
    mb.join(tmp, M)


def _frame(p, n):
    """Matriz con +y hacia el cuarto (contraria al muro n) y origen en el pie del muro bajo p."""
    inward = -n
    xax = Vector((inward.y, -inward.x, 0.0))
    o = Vector((p["x"], p["y"], p["zf"])) + n * (p["d"] - 0.002)
    return Matrix(((xax.x, inward.x, 0, o.x), (xax.y, inward.y, 0, o.y), (0, 0, 1, o.z), (0, 0, 0, 1)))


def _in_zones(zones, x, y, z, rad):
    return any(z0 - 0.3 <= z <= z1 and x + rad > x0 and x - rad < x1 and y + rad > y0 and y - rad < y1
               for (x0, x1, y0, y1, z0, z1) in zones)


def _fits_fn(sc, M, zs=(0.05, 0.25), zones=()):
    """fits(x, y, rad) para piezas de un montón con marco M: nada entre el centro del montón y el punto, ni entre el punto
    y su contorno (4 direcciones, radio rad), y fuera de las zonas de paso de puertas (cfg['door_zones'])."""
    def fits(x, y, rad):
        for z in zs:
            a = M @ Vector((0.0, 0.0, z))
            b = M @ Vector((x, y, z))
            dv = b - a
            if dv.length > 1e-4 and sc.hit(a, dv.normalized(), dv.length) is not None:
                return False
            for d in DIRS8[::2]:
                if sc.hit(b, d, rad + 0.02) is not None:
                    return False
        c = M @ Vector((x, y, 0.0))
        return not _in_zones(zones, c.x, c.y, c.z, rad)
    return fits


def _outline8(mb):
    """Contorno de 8 puntos (extremos en 8 direcciones) de la planta de un MB, para probar su huella con rayos."""
    pts = [(v.co.x, v.co.y) for v in mb.bm.verts]
    out = []
    for k in range(8):
        a = k * PI / 4
        c, s_ = math.cos(a), math.sin(a)
        out.append(max(pts, key=lambda q: q[0] * c + q[1] * s_))
    return out


# ------------------------------------------------------------------------------------------------ colocación
def dress(objs, cfg, levels, stairs, bounds, seed, density=1.0, step=0.5, log=print):
    """objs: objetos ya construidos (carcasa, interior, detalles). levels: cotas de piso a vestir. stairs: [(x0, x1, y0, y1)].
    bounds: (x0, x1, y0, y1) de la planta. Devuelve (MB, estadísticas)."""
    sc = Scene(objs)
    r = rng(seed)
    mb = MB()
    st = {}
    x0, x1, y0, y1 = bounds
    for lv, zl in enumerate(levels):
        pts = []
        nx, ny = int((x1 - x0) / step), int((y1 - y0) / step)
        for i in range(nx + 1):
            for j in range(ny + 1):
                x = x0 + i * step + r.uniform(-0.12, 0.12)
                y = y0 + j * step + r.uniform(-0.12, 0.12)
                p = probe(sc, x, y, zl, stairs)
                if p:
                    pts.append(p)
        r.shuffle(pts)
        used = []

        zones = cfg.get("door_zones", [])

        def free(p, rad):
            return all((p["x"] - q[0]) ** 2 + (p["y"] - q[1]) ** 2 >= (rad + q[2]) ** 2 for q in used)

        def clear(p, rad):                       # fuera de las zonas de paso de puertas y cortinas
            return not _in_zones(zones, p["x"], p["y"], p["zf"], rad)

        # focos: centro de cuarto (lejos de los muros), uno cada ~3 m
        bulbs = []
        for p in sorted(pts, key=lambda q: -min(q["ds"])):
            if min(p["ds"]) < 1.1:
                break
            if all((p["x"] - b[0]) ** 2 + (p["y"] - b[1]) ** 2 > 3.0 ** 2 for b in bulbs) and r.random() < 0.85 * density:
                bulbs.append((p["x"], p["y"]))
                drop = r.uniform(0.25, 0.55)
                tmp = MB()
                ceiling_bulb(tmp, r, drop)
                mb.join(tmp, _T(p["x"], p["y"], p["zc"]))
                st["bulb"] = st.get("bulb", 0) + 1
                # centro del vidrio del foco (para poner una luz puntual en el motor), en metros, ejes de Blender
                st.setdefault("bulb_pos", []).append([round(p["x"], 3), round(p["y"], 3), round(p["zc"] - drop - 0.117, 3)])

        # una pasada por tipo, cada una con su espaciado (entre piezas del mismo tipo) y su probabilidad
        def place(kind, ok, prob, gap, rad, put):
            mine = []
            for p in pts:
                if r.random() >= prob * density or not ok(p) or not free(p, rad) or not clear(p, rad * 0.6):
                    continue
                if any((p["x"] - q[0]) ** 2 + (p["y"] - q[1]) ** 2 < gap * gap for q in mine):
                    continue
                if put(p) is False:                      # no cupo (prueba de huella): no cuenta ni ocupa
                    st[kind + "_rechazado"] = st.get(kind + "_rechazado", 0) + 1
                    continue
                mine.append((p["x"], p["y"]))
                used.append((p["x"], p["y"], rad))
                st[kind] = st.get(kind, 0) + 1

        def wall_ok(zs, half, dmax=0.75):
            return lambda p: 0.12 <= p["d"] <= dmax and solid_wall(sc, p, p["wall_dir"], p["d"], half=half, zs=zs)

        def put_debris(p):
            M = _frame(p, p["wall_dir"]) @ _T(0, 0.3, 0)
            tmp = MB()
            plaster_debris(tmp, r, n_chunks=r.integers(4, 9), fits=_fits_fn(sc, M, zs=(0.04,), zones=zones))
            mb.join(tmp, M)

        def put_mattress(p):
            tmp = MB()
            info = mattress(tmp, r)
            M = _frame(p, p["wall_dir"])
            L, W, ym, yaw = info["L"], info["W"], info["y0"], info["yaw"]
            box = [(x, y) for x in (-L / 2 - 0.02, 0.0, L / 2 + 0.02) for y in (ym, ym + W / 2, ym + W + 0.02)]
            box = [(x * math.cos(yaw) - y * math.sin(yaw), x * math.sin(yaw) + y * math.cos(yaw)) for (x, y) in box]
            if not footprint_clear(sc, M @ _T(0, 0.02, 0), box, 0.0, zs=(0.06, 0.2)):
                return False
            if any(_in_zones(zones, *(M @ Vector((x, y, 0.0)))[:3], 0.05) for (x, y) in box):
                return False
            mb.join(tmp, M)

        def put_trash(p):
            M = _T(p["x"], p["y"], p["zf"])
            tmp = MB()
            trash(tmp, r, n_papers=r.integers(4, 9), n_bottles=r.integers(1, 4), fits=_fits_fn(sc, M, zs=(0.04, 0.12), zones=zones))
            mb.join(tmp, M)

        def put_chair(p):
            M = _T(p["x"], p["y"], p["zf"])
            tmp = MB()
            broken_chair(tmp, r)
            ol = _outline8(tmp)
            if not footprint_clear(sc, M, ol, 0.0, zs=(0.05, 0.3, 0.6)):
                return False
            if any(_in_zones(zones, *(M @ Vector((x, y, 0.0)))[:3], 0.05) for (x, y) in ol):
                return False
            mb.join(tmp, M)

        def put_plate(p):
            kind = "switch" if r.random() < 0.5 else "socket"
            tmp = MB()
            wall_plate(tmp, kind, r)
            mb.join(tmp, _frame(p, p["wall_dir"]) @ _T(0, -0.0025, 1.1 if kind == "switch" else 0.3))   # 0,5 mm en el muro

        # escombro: muro sin puerta detrás (rayo a 0,3 m; bajo una ventana sí puede haber escombro)
        place("plaster_debris", wall_ok((0.3,), 0.35), 0.3, 2.3, 0.55, put_debris)
        place("mattress", wall_ok((0.3,), 0.95), 0.15, 6.0, 1.05, put_mattress)
        place("chair", lambda p: p["d"] >= 0.45, 0.12, 4.5, 0.5, put_chair)
        place("trash", lambda p: p["d"] >= 0.3, 0.35, 2.0, 0.7, put_trash)
        place("plate", wall_ok((0.5, 1.9), 0.15), 0.5, 2.8, 0.2, put_plate)
        log(f"[vestido] nivel {lv}: {len(pts)} puntos útiles")
    sc.free()
    return mb, st
