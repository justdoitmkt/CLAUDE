"""kit/port.py — piezas portuarias (muelle MUE_1) con construcción real (pasada AAA, R-AAA 2026-11-19).
Primitivas de perfil (torneado, loft, barridos de perfil con inglete, ángulos laminados, tuercas hexagonales con chaflán,
láminas corrugadas como sólido delgado, cabos torcidos, cordones de soldadura, grilletes) y piezas completas: bita de
cabeza en T, llanta de defensa hueca con dibujo, cadena de eslabones, defensa de madera dura con flejes, escalera marina,
poste de luz octagonal con luminaria tipo cobra, tambo de 200 L, grúa de pedestal con pluma de celosía, contenedor ISO
de 20' y barandal de tubo. Todas devuelven MB o escriben en el MB dado; medidas en metros, z arriba.
Las primitivas viejas (lathe, loft, member, angle_bar, gusset, bolt, frame_on) conservan su comportamiento: las usan
otros módulos del kit (clínica, granja, armería, antenas...)."""
import math

from mathutils import Matrix, Vector

from kit.common import MB, rng

SQ = 0.7071067811865476


def _T(x, y, z):
    return Matrix.Translation((x, y, z))


def _R(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, axis)


# ======================================================================================================== primitivas
def frame_on(p0, p1, up=(0, 0, 1)):
    """Matriz con X a lo largo de p0→p1 y Z lo más cerca posible de `up`; origen en p0. Devuelve (M, largo)."""
    p0, p1 = Vector(p0), Vector(p1)
    X = (p1 - p0).normalized()
    U = Vector(up)
    if abs(X.dot(U)) > 0.99:
        U = Vector((0, 1, 0)) if abs(X.y) < 0.9 else Vector((1, 0, 0))
    Z = (U - X * X.dot(U)).normalized()
    Y = Z.cross(X)
    return Matrix(((X.x, Y.x, Z.x, p0.x), (X.y, Y.y, Z.y, p0.y), (X.z, Y.z, Z.z, p0.z), (0, 0, 0, 1))), (p1 - p0).length


def member(mb, p0, p1, rects, mat, up=(0, 0, 1)):
    """Barra prismática de p0 a p1; sección = unión de rectángulos [(y0, y1, z0, z1)] en el plano local YZ."""
    M, L = frame_on(p0, p1, up)
    for (y0, y1, z0, z1) in rects:
        mb.box((0.0, y0, z0), (L, y1, z1), mat, m=M)


def angle_bar(mb, p0, p1, leg=0.08, t=0.008, mat="metal_paint", up=(0, 0, 1), flip=False):
    """Ángulo L (alas iguales) de p0 a p1: el talón sobre el eje, alas hacia +Y y +Z locales (o -Y/+Z con flip)."""
    s = -1.0 if flip else 1.0
    y0, y1 = sorted((0.0, s * leg))
    ty0, ty1 = sorted((0.0, s * t))
    member(mb, p0, p1, [(y0, y1, 0.0, t), (ty0, ty1, t, leg)], mat, up)


def i_sec(h, b, tw=0.012, tf=0.016):
    return [(-tw / 2, tw / 2, -h / 2 + tf, h / 2 - tf), (-b / 2, b / 2, h / 2 - tf, h / 2), (-b / 2, b / 2, -h / 2, -h / 2 + tf)]


def z_sec(h=0.2, b=0.07, t=0.0025):
    """Larguero Z (alas opuestas)."""
    return [(-t / 2, t / 2, -h / 2, h / 2), (-t / 2, b, h / 2 - t, h / 2), (-b, t / 2, -h / 2, -h / 2 + t)]


def lathe(mb, prof, seg=16, mat="metal_paint", M=None, caps=True, phase=0.0):
    """Sólido de revolución alrededor de Z local. prof: [(r, z)] de abajo hacia arriba."""
    rings = []
    for (rr, z) in prof:
        ring = []
        for k in range(seg):
            a = 2 * math.pi * k / seg + phase
            p = Vector((rr * math.cos(a), rr * math.sin(a), z))
            ring.append(mb.bm.verts.new(M @ p if M is not None else p))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([rings[i][k], rings[i][kk], rings[i + 1][kk], rings[i + 1][k]], mat)
    if caps:
        if prof[0][0] > 1e-6:
            mb.face(list(reversed(rings[0])), mat)
        if prof[-1][0] > 1e-6:
            mb.face(rings[-1], mat)


def loft(mb, stations, seg=12, mat="metal_paint", M=None, ex=2.6):
    """Cuerpo a lo largo de X local por secciones superelípticas [(x, ancho, alto, z_centro)] (ex = 2 elipse, >2 más cuadrada)."""
    rings = []
    for (x, w, h, zc) in stations:
        ring = []
        for k in range(seg):
            a = 2 * math.pi * k / seg
            c, s = math.cos(a), math.sin(a)
            yy = (w / 2) * math.copysign(abs(c) ** (2 / ex), c)
            zz = zc + (h / 2) * math.copysign(abs(s) ** (2 / ex), s)
            p = Vector((x, yy, zz))
            ring.append(mb.bm.verts.new(M @ p if M is not None else p))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([rings[i][k], rings[i][kk], rings[i + 1][kk], rings[i + 1][k]], mat)
    mb.face(list(reversed(rings[0])), mat)
    mb.face(rings[-1], mat)


def bolt(mb, M, d=0.024, stud=0.02, mat="metal_rust", fine=False):
    """Tuerca hexagonal con arandela y punta de espárrago sobre el plano z = 0 local (eje +Z). fine=True: tuerca con
    chaflán, arandela redonda de 24 lados y espárrago roscado (hexnut); el valor por omisión conserva la pieza vieja que
    usan otros módulos."""
    if fine:
        return nutbolt(mb, M, d=d, stud=stud, mat=mat)
    lathe(mb, [(d * 1.0, 0.0), (d * 1.0, 0.004)], seg=10, mat=mat, M=M)
    lathe(mb, [(d * 0.82, 0.004), (d * 0.82, 0.004 + d * 0.8)], seg=6, mat=mat, M=M, phase=math.pi / 6)
    lathe(mb, [(d * 0.45, 0.004 + d * 0.8), (d * 0.45, 0.004 + d * 0.8 + stud)], seg=6, mat=mat, M=M)


def bolt_ring(mb, M, R, n, d=0.024, mat="metal_rust", phase=0.0):
    for k in range(n):
        a = 2 * math.pi * k / n + phase
        bolt(mb, M @ _T(R * math.cos(a), R * math.sin(a), 0.0), d=d, mat=mat)


def plate_poly(mb, pts, t, mat, M):
    """Placa: polígono (x, y) extruido t en +Z local."""
    mb.plate(pts, t, mat, m=M)


def gusset(mb, M, a, b, t=0.012, mat="metal_paint", chamfer=0.03):
    """Cartela triangular en el plano XZ local (catetos a en X y b en Z), espesor t centrado en Y."""
    pts = [(0.0, 0.0), (a, 0.0), (a, chamfer), (chamfer, b), (0.0, b)]
    mb.plate(pts, t, mat, m=M @ _T(0, t / 2, 0) @ _R("X", 90))


# ======================================================================================================== ayudas AAA
class PMB(MB):
    """MB de las piezas portuarias: toda caja lleva bisel real por omisión (1–3 mm; bevel=0 explícito lo quita)."""

    def box(self, mn, mx, mat="concrete", bevel=None, seg=2, m=None):
        if bevel is None:
            d = min(abs(mx[0] - mn[0]), abs(mx[1] - mn[1]), abs(mx[2] - mn[2]))
            bevel = min(0.003, d * 0.24) if d > 0.0015 else 0.0
        return super().box(mn, mx, mat, bevel=bevel, seg=seg, m=m)


def fillet(pts, rad, nseg=8):
    """Polilínea 3D con las esquinas redondeadas (radio de doblez real)."""
    P = [Vector(p) for p in pts]
    if len(P) < 3:
        return [tuple(p) for p in P]
    out = [P[0]]
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        d0, d1 = (a - b).normalized(), (c - b).normalized()
        ang = d0.angle(d1)
        if ang > math.pi - 1e-3:
            out.append(b)
            continue
        t = rad / math.tan(ang / 2)
        t = min(t, (a - b).length * 0.49, (c - b).length * 0.49)
        p0, p1 = b + d0 * t, b + d1 * t
        for k in range(nseg + 1):
            u = k / nseg
            out.append(p0.lerp(b, u).lerp(b.lerp(p1, u), u))
    out.append(P[-1])
    return [tuple(p) for p in out]


def rr_profile(w, h, r, n=4, cx=0.0, cy=0.0):
    """Rectángulo w x h de esquinas de radio r (antihorario), centrado en (cx, cy)."""
    pts = []
    r = min(r, w / 2 - 1e-5, h / 2 - 1e-5)
    for (qx, qy, a0) in ((w / 2 - r, h / 2 - r, 0.0), (-w / 2 + r, h / 2 - r, math.pi / 2), (-w / 2 + r, -h / 2 + r, math.pi),
                         (w / 2 - r, -h / 2 + r, 1.5 * math.pi)):
        for k in range(n + 1):
            a = a0 + math.pi / 2 * k / n
            pts.append((cx + qx + r * math.cos(a), cy + qy + r * math.sin(a)))
    return pts


def round_poly(pts, r, n=3):
    """Polígono 2D cerrado con las esquinas redondeadas (radio r, n segmentos por esquina)."""
    P = [Vector((p[0], p[1], 0.0)) for p in pts]
    k = len(P)
    out = []
    for i in range(k):
        a, b, c = P[i - 1], P[i], P[(i + 1) % k]
        d0, d1 = (a - b), (c - b)
        if d0.length < 1e-9 or d1.length < 1e-9:
            out.append((b.x, b.y))
            continue
        d0.normalize()
        d1.normalize()
        ang = d0.angle(d1)
        if ang > math.pi - 1e-3 or r <= 0:
            out.append((b.x, b.y))
            continue
        t = min(r / math.tan(ang / 2), (a - b).length * 0.45, (c - b).length * 0.45)
        p0, p1 = b + d0 * t, b + d1 * t
        for j in range(n + 1):
            u = j / n
            q = p0.lerp(b, u).lerp(b.lerp(p1, u), u)
            out.append((q.x, q.y))
    return out


def _frames(P, up=None, closed=False):
    """Tangentes y normales (N = eje y del perfil) por vértice de la polilínea."""
    n = len(P)
    T = []
    for i in range(n):
        if closed:
            a = P[(i + 1) % n] - P[(i - 1) % n]
        else:
            a = P[min(i + 1, n - 1)] - P[max(i - 1, 0)]
        T.append(a.normalized() if a.length > 1e-12 else Vector((0, 0, 1)))
    N = []
    if up is not None:
        U = Vector(up)
        for t in T:
            v = U - t * t.dot(U)
            if v.length < 1e-6:
                v = Vector((1, 0, 0)) - t * t.x
            N.append(v.normalized())
    else:
        ref = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
        v = (ref - T[0] * ref.dot(T[0])).normalized()
        for t in T:
            v = (v - t * v.dot(t))
            v = v.normalized() if v.length > 1e-9 else (ref - t * ref.dot(t)).normalized()
            N.append(v)
    return T, N


def psweep(mb, prof, path, mat, up=None, caps=True, closed=False, scales=None, miter=True):
    """Barre un perfil 2D cerrado [(x, y)] a lo largo de una polilínea 3D (x = lateral, y = hacia `up` o la normal de
    transporte paralelo). scales: factor por estación. Juntas a inglete en los quiebres (sin estrangular el perfil)."""
    P = [Vector(p) for p in path]
    n = len(P)
    if n < 2:
        return []
    T, N = _frames(P, up, closed)
    rings = []
    for i in range(n):
        B = T[i].cross(N[i])
        s = scales[i] if scales is not None else 1.0
        k = None
        f = 1.0
        if miter and (closed or 0 < i < n - 1):
            t0 = (P[i] - P[(i - 1) % n]).normalized()
            t1 = (P[(i + 1) % n] - P[i]).normalized()
            c = max(min(t0.dot(t1), 1.0), -0.9)
            if c < 0.9999:
                k = (t1 - t0).normalized()
                f = 1.0 / max(math.cos(math.acos(c) / 2), 0.35)
        ring = []
        for (x, y) in prof:
            off = (B * x + N[i] * y) * s
            if k is not None:
                off = off + k * (off.dot(k) * (f - 1.0))
            ring.append(mb.bm.verts.new(P[i] + off))
        rings.append(ring)
    m = len(prof)
    segs = n if closed else n - 1
    for i in range(segs):
        A, Bq = rings[i], rings[(i + 1) % n]
        for j in range(m):
            jj = (j + 1) % m
            mb.face([A[j], A[jj], Bq[jj], Bq[j]], mat)
    if caps and not closed:
        mb.face(list(reversed(rings[0])), mat)
        mb.face(rings[-1], mat)
    return rings


def lathe_n(mb, prof, seg=48, mat="metal_paint", M=None, caps=True, phase=0.0, dr=None):
    """Sólido de revolución (eje Z local) con desplazamiento radial dr(ángulo, z) -> m (abolladuras, picaduras, costra)."""
    rings = []
    for (rr, z) in prof:
        ring = []
        for k in range(seg):
            a = 2 * math.pi * k / seg + phase
            r2 = rr + (dr(a, z) if (dr is not None and rr > 1e-6) else 0.0)
            p = Vector((r2 * math.cos(a), r2 * math.sin(a), z))
            ring.append(mb.bm.verts.new(M @ p if M is not None else p))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([rings[i][k], rings[i][kk], rings[i + 1][kk], rings[i + 1][k]], mat)
    if caps:
        if prof[0][0] > 1e-6:
            mb.face(list(reversed(rings[0])), mat)
        if prof[-1][0] > 1e-6:
            mb.face(rings[-1], mat)
    return rings


def hexnut(mb, M, af=0.046, h=None, mat="metal_rust", washer=True, stud=None):
    """Tuerca hexagonal (entre caras af) con chaflán de 30° en ambas caras, arandela de canto redondeado y punta de
    espárrago con hilos (eje +Z, apoyada en z = 0 local). stud = largo que asoma la punta (None: 0,45·af)."""
    h = h if h is not None else af * 0.8
    z0 = 0.0
    if washer:
        rw, tw = af * 0.95, max(af * 0.09, 0.0015)
        lathe_n(mb, [(af * 0.56, 0.0), (rw - tw * 0.4, 0.0), (rw, tw * 0.4), (rw, tw * 0.6), (rw - tw * 0.4, tw),
                     (af * 0.56, tw)], seg=24, mat=mat, M=M)
        z0 = tw
    ac = af / math.cos(math.radians(30))
    ch = h * 0.12

    def ring(z, rc, rf):
        vs = []
        for k in range(12):
            a = math.radians(30 * k)
            rr = rc if k % 2 == 0 else rf
            p = Vector((rr * math.cos(a), rr * math.sin(a), z))
            vs.append(mb.bm.verts.new(M @ p))
        return vs
    rf = af / 2
    rcc = rf * 1.035                       # esquina recortada por el chaflán (círculo apenas mayor que la cara)
    R = [ring(z0, rcc, rf * 0.97), ring(z0 + ch, ac / 2, rf), ring(z0 + h - ch, ac / 2, rf), ring(z0 + h, rcc, rf * 0.97)]
    for i in range(3):
        for k in range(12):
            kk = (k + 1) % 12
            mb.face([R[i][k], R[i][kk], R[i + 1][kk], R[i + 1][k]], mat)
    mb.face(list(reversed(R[0])), mat)
    # cara superior con el agujero roscado ocupado por el espárrago
    rs = af * 0.31
    if stud is None:
        stud = af * 0.45
    if stud > 0:
        top = [mb.bm.verts.new(M @ Vector((rs * 1.08 * math.cos(math.radians(30 * k)), rs * 1.08 * math.sin(math.radians(30 * k)),
                                            z0 + h))) for k in range(12)]
        for k in range(12):
            kk = (k + 1) % 12
            mb.face([R[3][k], R[3][kk], top[kk], top[k]], mat)
        mb.face(list(reversed(top)), mat)
        prof = [(rs, z0 + h - 0.002)]
        nth = max(2, int(stud / max(af * 0.075, 0.001)))
        for j in range(nth):
            z = z0 + h + stud * (j + 0.5) / (nth + 0.6)
            prof += [(rs * 0.9, z), (rs, z + stud / (nth + 0.6) * 0.5)]
        prof += [(rs * 0.94, z0 + h + stud - rs * 0.12), (rs * 0.7, z0 + h + stud), (0.0, z0 + h + stud)]
        with mb.soft():
            lathe_n(mb, prof, seg=14, mat=mat, M=M)
    else:
        mb.face(R[3], mat)


def nutbolt(mb, M, d=0.024, stud=0.02, mat="metal_rust"):
    """Tuerca fina con el criterio de tamaño de bolt() (d = radio de la arandela vieja ≈ 0,7·entre caras)."""
    hexnut(mb, M, af=d * 1.42, mat=mat, stud=stud if stud > 0 else 0.0)


def bev_plate(mb, outline, t, mat, M=None, ch=0.002):
    """Placa: polígono 2D CONVEXO (antihorario) extruido t en +Z local con chaflán ch en los cantos de ambas caras."""
    k = len(outline)
    P = [Vector((x, y, 0.0)) for (x, y) in outline]

    def inset(d):
        out = []
        for i in range(k):
            a, b, c = P[i - 1], P[i], P[(i + 1) % k]
            e0 = (b - a).normalized()
            e1 = (c - b).normalized()
            n0 = Vector((-e0.y, e0.x, 0.0))
            n1 = Vector((-e1.y, e1.x, 0.0))
            bis = (n0 + n1)
            if bis.length < 1e-9:
                bis = n0
            bis.normalize()
            s = d / max(bis.dot(n0), 0.3)
            out.append(b + bis * s)
        return out
    ch = min(ch, t * 0.3)
    layers = [(inset(ch), 0.0), (P, ch), (P, t - ch), (inset(ch), t)] if ch > 0 else [(P, 0.0), (P, t)]
    rings = []
    for (pts, z) in layers:
        rings.append([mb.bm.verts.new((M @ Vector((p.x, p.y, z))) if M is not None else Vector((p.x, p.y, z))) for p in pts])
    for i in range(len(rings) - 1):
        for j in range(k):
            jj = (j + 1) % k
            mb.face([rings[i][j], rings[i][jj], rings[i + 1][jj], rings[i + 1][j]], mat)
    mb.face(list(reversed(rings[0])), mat)
    mb.face(rings[-1], mat)


def corr_pts(L, pitch=0.278, depth=0.036, outer=0.072, inner=0.070, phase=0.0, round_r=0.0):
    """Perfil trapezoidal [(u, d)] de 0..L: valle (cara interior) d = 0, cresta d = depth (ISO 1496: paso 278, peralte 36,
    cara exterior 72, interior 70, faldón 68 en planta)."""
    sl = (pitch - outer - inner) / 2
    keys = [(0.0, 0.0), (inner, 0.0), (inner + sl, depth), (inner + sl + outer, depth), (pitch, 0.0)]

    def d_at(u):
        f = (u + phase) % pitch
        for (a, da), (b, db) in zip(keys[:-1], keys[1:]):
            if a <= f <= b:
                return da + (db - da) * ((f - a) / (b - a) if b > a else 0.0)
        return 0.0
    us = {0.0, round(L, 6)}
    kk = math.floor(-phase / pitch) - 1
    while kk * pitch - phase < L + pitch:
        for (a, _) in keys:
            u = kk * pitch + a - phase
            if 0.0 < u < L:
                us.add(round(u, 6))
        kk += 1
    us = sorted(us)
    return [(u, d_at(u)) for u in us]


def csheet(mb, M, upts, v0, v1, mat, nrows=8, t=0.002, dent=None, vfn=None):
    """Lámina corrugada como sólido delgado: upts = [(u, peralte)] (peralte hacia -Y local = afuera), cota v0..v1 en Z
    local, nrows filas (para abolladuras). dent(u, v) -> desplazamiento hacia +Y (adentro) en m. vfn(u, v) -> v alterado
    (bordes inclinados). Caras: exterior, interior y los 4 cantos."""
    n = len(upts)
    rows = [v0 + (v1 - v0) * j / nrows for j in range(nrows + 1)]
    O, I = [], []
    for v in rows:
        ro, ri = [], []
        for (u, d) in upts:
            vv = vfn(u, v) if vfn is not None else v
            dd = dent(u, vv) if dent is not None else 0.0
            ro.append(mb.bm.verts.new(M @ Vector((u, -d + dd, vv))))
            ri.append(mb.bm.verts.new(M @ Vector((u, -d + dd + t, vv))))
        O.append(ro)
        I.append(ri)
    for j in range(nrows):
        for i in range(n - 1):
            mb.face([O[j][i], O[j][i + 1], O[j + 1][i + 1], O[j + 1][i]], mat)
            mb.face([I[j][i], I[j + 1][i], I[j + 1][i + 1], I[j][i + 1]], mat)
    for i in range(n - 1):
        mb.face([O[0][i], I[0][i], I[0][i + 1], O[0][i + 1]], mat)
        mb.face([O[-1][i], O[-1][i + 1], I[-1][i + 1], I[-1][i]], mat)
    for j in range(nrows):
        mb.face([O[j][0], O[j + 1][0], I[j + 1][0], I[j][0]], mat)
        mb.face([O[j][-1], I[j][-1], I[j + 1][-1], O[j + 1][-1]], mat)


def dents(r, n, u0, u1, v0, v1, amp=(0.01, 0.04), rad=(0.15, 0.5)):
    """Función de abolladuras gaussianas aleatorias sobre un panel (u, v) -> desplazamiento."""
    D = [(float(r.uniform(u0, u1)), float(r.uniform(v0, v1)), float(r.uniform(*amp)), float(r.uniform(*rad))) for _ in range(n)]

    def f(u, v):
        s = 0.0
        for (cu, cv, a, rr) in D:
            q = ((u - cu) ** 2 + (v - cv) ** 2) / (rr * rr)
            if q < 9.0:
                s += a * math.exp(-q)
        return s
    return f


def laid_rope(mb, pts, r=0.02, mat="cable", lay=None, strands=3, res=None, seg=16, fray=0.0, rr=None):
    """Cabo torcido de `strands` torones: polilínea suavizada (Catmull-Rom) y radio modulado en hélice (los surcos entre
    torones giran con el paso de cableado `lay`, ~3,3·Ø). Sombreado continuo. fray > 0: punta deshilachada (m)."""
    P = [Vector(p) for p in pts]
    if len(P) < 2:
        return
    lay = lay or 6.6 * r
    res = res or lay / 7.0
    # Catmull-Rom con remuestreo por longitud
    dense = []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, len(P) - 1)]
        L = (p2 - p1).length
        k = max(2, int(L / res))
        for j in range(k):
            t = j / k
            dense.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    dense.append(P[-1])
    T, N = _frames(dense)
    s = 0.0
    rings = []
    total = sum((dense[i + 1] - dense[i]).length for i in range(len(dense) - 1))
    for i, p in enumerate(dense):
        if i > 0:
            s += (p - dense[i - 1]).length
        B = T[i].cross(N[i])
        tw = 2 * math.pi * s / lay
        fr = 0.0
        if fray > 0 and total - s < fray:
            fr = (1.0 - (total - s) / fray)
        ring = []
        for k in range(seg):
            a = 2 * math.pi * k / seg
            m_ = 1.0 - 0.13 * (0.5 + 0.5 * math.cos(strands * (a - tw)))
            if fr > 0:
                m_ *= 1.0 + 0.9 * fr * (0.5 + 0.5 * math.cos(strands * (a - tw))) * (1.0 + 0.3 * math.sin(7 * a + 3 * s))
            rad = r * m_ * (rr(s) if rr else 1.0)
            ring.append(mb.bm.verts.new(p + (N[i] * math.cos(a) + B * math.sin(a)) * rad))
        rings.append(ring)
    with mb.soft():
        for i in range(len(rings) - 1):
            for k in range(seg):
                kk = (k + 1) % seg
                mb.face([rings[i][k], rings[i][kk], rings[i + 1][kk], rings[i + 1][k]], mat)
        c0 = mb.bm.verts.new(dense[0])
        c1 = mb.bm.verts.new(dense[-1])
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([c0, rings[0][kk], rings[0][k]], mat)
            mb.face([c1, rings[-1][k], rings[-1][kk]], mat)


def catenary(p0, p1, sag, n=16):
    """Puntos de una curva colgante (parábola) entre p0 y p1 con flecha `sag` al centro."""
    p0, p1 = Vector(p0), Vector(p1)
    return [tuple(p0.lerp(p1, i / n) - Vector((0, 0, sag * 4 * (i / n) * (1 - i / n)))) for i in range(n + 1)]


def weld(mb, pts, r=0.004, mat="metal_rust"):
    """Cordón de soldadura (filete) a lo largo de una polilínea: tubo de sombreado continuo con ondas leves."""
    with mb.soft():
        mb.tube(pts, r, seg=8, mat=mat, caps=True)


def shackle(mb, M, d=0.019, mat="metal_rust"):
    """Grillete de lira (arco + perno con cabeza y tuerca): arco en el plano XZ local, abierto hacia -Z, perno sobre el eje X
    a z = 0. d = diámetro del cuerpo."""
    W = d * 1.7          # luz interior
    Hh = d * 3.6         # largo interior
    pts = []
    for k in range(17):
        a = math.pi * k / 16
        pts.append(M @ Vector(((W / 2 + d / 2) * math.cos(a), 0.0, Hh - W / 2 + (W / 2 + d / 2) * math.sin(a))))
    pts = [M @ Vector((W / 2 + d / 2, 0, 0))] + pts + [M @ Vector((-(W / 2 + d / 2), 0, 0))]
    mb.tube(pts, d / 2, seg=16, mat=mat)
    for sx in (-1, 1):
        lathe_n(mb, [(0.0, -d * 0.5), (d * 0.55, -d * 0.5), (d * 0.62, -d * 0.35), (d * 0.62, d * 0.35), (d * 0.55, d * 0.5),
                     (0.0, d * 0.5)], seg=16, mat=mat, M=M @ _T(sx * (W / 2 + d / 2), 0, 0) @ _R("Y", 90))
    lathe_n(mb, [(0.0, -W / 2 - d * 1.4), (d * 0.42, -W / 2 - d * 1.4), (d * 0.42, W / 2 + d * 1.3), (d * 0.3, W / 2 + d * 1.45),
                 (0.0, W / 2 + d * 1.45)], seg=16, mat=mat, M=M @ _R("Y", 90))
    lathe_n(mb, [(0.0, 0.0), (d * 0.75, 0.0), (d * 0.75, d * 0.45), (d * 0.55, d * 0.55), (0.0, d * 0.55)], seg=16, mat=mat,
            M=M @ _T(-W / 2 - d * 1.4, 0, 0) @ _R("Y", -90))


_LINK_CACHE = {}


def _link_mb(d, seg=14, mat="metal_rust"):
    """Eslabón corto (DIN 766 aprox.): paso interior 3d, ancho interior 1,4d, alambre d; estadio en el plano XY local,
    eje largo en X, centrado en el origen. Se arma una vez por tamaño y se copia."""
    key = (round(d, 5), seg, mat)
    if key in _LINK_CACHE:
        return _LINK_CACHE[key]
    mb = MB()
    rc = 1.2 * d
    s = 1.6 * d
    pts = []
    na = 9
    for k in range(na + 1):                         # semicírculo derecho (de -y a +y)
        a = -math.pi / 2 + math.pi * k / na
        pts.append((s / 2 + rc * math.cos(a), rc * math.sin(a), 0.0))
    for k in range(na + 1):                         # semicírculo izquierdo
        a = math.pi / 2 + math.pi * k / na
        pts.append((-s / 2 + rc * math.cos(a), rc * math.sin(a), 0.0))
    prof = [(d / 2 * math.cos(2 * math.pi * k / seg), d / 2 * math.sin(2 * math.pi * k / seg)) for k in range(seg)]
    psweep(mb, prof, pts, mat, up=(0, 0, 1), closed=True, miter=True)
    _LINK_CACHE[key] = mb
    return mb


def chain(mb, pts, link=0.075, wire=0.009, mat="metal_rust", r=None):
    """Cadena de eslabones cortos entrelazados a lo largo de una polilínea: alambre Ø 2·wire, paso 3·Ø (el eslabón mide
    5·Ø x 3,4·Ø por fuera), cada eslabón girado 90° respecto al anterior, con giro leve al azar. `link` se conserva por
    compatibilidad (el tamaño sale del alambre)."""
    d = 2 * wire
    pitch = 3.0 * d
    L1 = _link_mb(d, mat=mat)
    P = [Vector(p) for p in pts]
    segs = [(P[i], P[i + 1]) for i in range(len(P) - 1) if (P[i + 1] - P[i]).length > 1e-6]
    total = sum((b_ - a_).length for (a_, b_) in segs)
    n = max(1, int(total / pitch))
    for k in range(n):
        s_ = (k + 0.5) * total / n
        for (a_, b_) in segs:
            Ls = (b_ - a_).length
            if s_ <= Ls + 1e-9:
                break
            s_ -= Ls
        dv = (b_ - a_).normalized()
        c = a_ + dv * s_
        M, _ = frame_on(c, c + dv, up=(0, 0, 1) if abs(dv.z) < 0.9 else (1, 0, 0))
        jit = float(r.uniform(-10, 10)) if r is not None else 0.0
        mb.join(L1, M @ _R("X", 90 * (k % 2) + jit))


def sheave(mb, M, R=0.25, w=0.08, mat="metal_paint"):
    """Polea (eje Y local): llanta con garganta para el cable, alma rebajada, maza y perno con tapa de retención."""
    Mr = M @ _R("X", 90)
    g = min(0.04, R * 0.18)
    prof = [(0.07, -w / 2 - 0.01), (0.075, -w * 0.18), (R - g - 0.025, -w * 0.18), (R - g - 0.02, -w / 2), (R - 0.004, -w / 2),
            (R, -w / 2 + 0.004), (R, -w / 2 + 0.012), (R - g * 0.55, -w * 0.22), (R - g, -w * 0.08), (R - g, w * 0.08),
            (R - g * 0.55, w * 0.22), (R, w / 2 - 0.012), (R, w / 2 - 0.004), (R - 0.004, w / 2), (R - g - 0.02, w / 2),
            (R - g - 0.025, w * 0.18), (0.075, w * 0.18), (0.07, w / 2 + 0.01)]
    lathe_n(mb, prof, seg=48, mat=mat, M=Mr, caps=False)
    lathe_n(mb, [(0.0, -w / 2 - 0.045), (0.045, -w / 2 - 0.045), (0.045, w / 2 + 0.045), (0.0, w / 2 + 0.045)], seg=24,
            mat="metal_rust", M=Mr)
    lathe_n(mb, [(0.044, -w / 2 - 0.01), (0.07, -w / 2 - 0.01), (0.07, w / 2 + 0.01), (0.044, w / 2 + 0.01)], seg=24, mat=mat,
            M=Mr, caps=False)


def rope(mb, pts, r=0.011, mat="cable"):
    """Cable de acero o cabo delgado: tubo de 14 lados con sombreado continuo."""
    with mb.soft():
        mb.tube(pts, r, seg=14, mat=mat)


def handrail(mb, p0, p1, h=1.1, post_step=1.5, mat="metal_paint", r=None, knee=True):
    """Barandal de tubo recto de p0 a p1 sobre su piso: pasamanos Ø48 y rodillera Ø33 de 20 lados con tapones soldados,
    postes Ø48 que rematan bajo el pasamanos con cordón de soldadura, placa base de 140 x 140 x 12 biselada y 4 anclas."""
    p0, p1 = Vector(p0), Vector(p1)
    L = (p1 - p0).length
    n = max(int(math.ceil(L / post_step)), 1)
    up = Vector((0, 0, 1))
    dv = (p1 - p0).normalized() if L > 1e-6 else Vector((1, 0, 0))
    side = up.cross(dv).normalized() if abs(dv.z) < 0.99 else Vector((0, 1, 0))
    tops = []
    for k in range(n + 1):
        c = p0.lerp(p1, k / n)
        lean = Vector((float(r.uniform(-0.01, 0.01)), float(r.uniform(-0.01, 0.01)), 0)) if r is not None else Vector()
        top = c + up * (h - 0.022) + lean
        mb.tube([c + up * 0.012, top], 0.024, seg=20, mat=mat, caps=False)
        tops.append(top)
        Mp = Matrix.Translation(c) @ Matrix(((dv.x, side.x, 0, 0), (dv.y, side.y, 0, 0), (dv.z, side.z, 1, 0), (0, 0, 0, 1)))
        bev_plate(mb, [(-0.07, -0.07), (0.07, -0.07), (0.07, 0.07), (-0.07, 0.07)], 0.012, mat, M=Mp, ch=0.002)
        for (bx, by) in ((-0.05, -0.05), (0.05, -0.05), (0.05, 0.05), (-0.05, 0.05)):
            hexnut(mb, Mp @ _T(bx, by, 0.012), af=0.013, mat=mat, washer=False, stud=0.004)
        weld(mb, [c + up * 0.012 + Vector((0.025 * math.cos(a), 0.025 * math.sin(a), 0.0)) for a in
                  [2 * math.pi * q / 16 for q in range(17)]], r=0.004, mat=mat)
    a_, b_ = p0 + up * h, p1 + up * h
    mb.tube([a_ - dv * 0.03, b_ + dv * 0.03], 0.024, seg=20, mat=mat, caps=True)
    for (q, o) in ((a_ - dv * 0.03, -dv), (b_ + dv * 0.03, dv)):
        lathe_n(mb, [(0.0, 0.0), (0.024, 0.0), (0.021, 0.005), (0.012, 0.008), (0.0, 0.009)], seg=20, mat=mat,
                M=frame_on(q, q + o)[0] @ _R("Y", 90))
    if knee:
        mb.tube([p0 + up * h * 0.5, p1 + up * h * 0.5], 0.0165, seg=20, mat=mat)


# ======================================================================================================== piezas
def bollard(seed=0):
    """Bita de amarre de fundición dúctil de cabeza en T (10–15 t, ~0,57 m): base fundida de esquinas redondeadas con
    faldón inclinado sobre cama de mortero, 4 anclas M30 con arandela y tuerca, fuste torneado con cintura y filetes de
    fundición, cuernos con labio de retención, sombrero con ceja, línea de partición del molde, pintura saltada y golpes."""
    r = rng(seed)
    mb = PMB()
    # cama de mortero bajo la base (asoma 8 mm alrededor)
    _rr_loft(mb, [(-0.01, 0.80, 0.64, 0.07), (0.012, 0.79, 0.63, 0.065), (0.018, 0.776, 0.616, 0.058)], "concrete", corner_n=5)
    # brida fundida de esquinas redondeadas con canto achaflanado
    _rr_loft(mb, [(0.018, 0.76, 0.60, 0.05), (0.046, 0.76, 0.60, 0.05), (0.053, 0.746, 0.586, 0.043)], "metal_paint", corner_n=5)
    for (x, y) in ((-0.29, -0.21), (0.29, -0.21), (-0.29, 0.21), (0.29, 0.21)):
        hexnut(mb, _T(x, y, 0.053), af=0.046, mat="metal_rust", stud=0.026)
    # fuste torneado con filete en la base y cintura (dr: golpes de los cabos y fundición irregular)
    hits = [(float(r.uniform(0, 2 * math.pi)), float(r.uniform(0.15, 0.36)), float(r.uniform(0.002, 0.006))) for _ in range(5)]

    def dr(a, z):
        s = 0.0
        for (ha, hz, hd) in hits:
            da = math.atan2(math.sin(a - ha), math.cos(a - ha))
            q = (da / 0.25) ** 2 + ((z - hz) / 0.03) ** 2
            if q < 9:
                s -= hd * math.exp(-q)
        return s
    prof = [(0.27, 0.053), (0.262, 0.057), (0.245, 0.066), (0.222, 0.082), (0.2, 0.104), (0.182, 0.132), (0.169, 0.168),
            (0.16, 0.21), (0.155, 0.25), (0.153, 0.29), (0.154, 0.33), (0.158, 0.365), (0.166, 0.4)]

    def prof_r(z):
        for (ra, za), (rb, zb) in zip(prof[:-1], prof[1:]):
            if za <= z <= zb:
                return ra + (rb - ra) * (z - za) / (zb - za)
        return prof[-1][0]
    lathe_n(mb, prof, seg=56, mat="metal_paint", caps=False, dr=dr)
    # línea de partición del molde (aleta de 3 mm a ±X)
    for sg in (-1, 1):
        weld(mb, [(sg * (rr_ + 0.0005), 0.0, z) for (rr_, z) in prof[3:]], r=0.0022, mat="metal_paint")
    # cuernos de la T: cuerpo cónico con labio levantado en la punta
    for sg in (-1, 1):
        lathe_n(mb, [(0.0, 0.0), (0.098, 0.0), (0.096, 0.06), (0.092, 0.17), (0.094, 0.215), (0.104, 0.245), (0.112, 0.262),
                     (0.111, 0.278), (0.1, 0.292), (0.08, 0.303), (0.05, 0.309), (0.0, 0.311)], seg=40, mat="metal_paint",
                M=_T(0, 0, 0.47) @ _R("Y", 90 * sg))
    # sombrero con ceja y bombeo
    lathe_n(mb, [(0.166, 0.4), (0.172, 0.43), (0.18, 0.47), (0.188, 0.515), (0.196, 0.535), (0.198, 0.545), (0.192, 0.556),
                 (0.17, 0.563), (0.11, 0.569), (0.0, 0.571)], seg=56, mat="metal_paint", caps=True, dr=dr)
    # escamas de pintura levantadas y desconchones (placas finas de 0,6 mm sobre el fuste)
    for k in range(int(r.integers(5, 9))):
        a = float(r.uniform(0, 2 * math.pi))
        z = float(r.uniform(0.14, 0.39))
        rad = prof_r(z)
        w, hh = float(r.uniform(0.015, 0.03)), float(r.uniform(0.01, 0.022))
        M = _R("Z", math.degrees(a)) @ _T(rad + 0.0004, 0, z) @ _R("Y", 90) @ _R("Z", float(r.uniform(0, 180)))
        bev_plate(mb, [(-w / 2, -hh / 2), (w / 2, -hh / 2 + 0.003), (w / 2 - 0.004, hh / 2), (-w / 2 + 0.006, hh / 2)], 0.0006,
                  "metal_rust", M=M, ch=0.0)
    mb.meta = dict(top=0.571)
    return mb


def _rr_loft(mb, stations, mat, corner_n=4, M=None, caps=True):
    """Sólido por anillos de rectángulo redondeado [(z, ancho_x, fondo_y, radio)] de abajo hacia arriba."""
    rings = []
    for (z, w, d, rad) in stations:
        pr = rr_profile(w, d, rad, n=corner_n)
        rings.append([mb.bm.verts.new((M @ Vector((x, y, z))) if M is not None else Vector((x, y, z))) for (x, y) in pr])
    k = len(rings[0])
    for i in range(len(rings) - 1):
        for j in range(k):
            jj = (j + 1) % k
            mb.face([rings[i][j], rings[i][jj], rings[i + 1][jj], rings[i + 1][j]], mat)
    if caps:
        mb.face(list(reversed(rings[0])), mat)
        mb.face(rings[-1], mat)
    return rings


def fender_tyre(seed=0, R=0.42, t=0.13, seg=120, sseg=16):
    """Llanta de camión de desecho como defensa (11R22.5: Ø ext. ~1,10 m, sección 0,28 m, ceja de 22,5"): corte real de la
    llanta (banda plana con hombros, costados abombados, cejas y forro interior: es HUECA y se ve por dentro), banda con
    3 ranuras circunferenciales en zigzag y tacos de hombro, desgaste por roce contra el muro. Eje en Y local."""
    r = rng(seed)
    mb = MB()
    Ro, Rb = R + t, R - t                       # radio exterior de la banda y de la ceja
    hw = 0.14                                   # medio ancho de sección
    # perfil exterior de ceja a ceja (r, y) pasando por la banda (cada 1 cm en la banda); luego el forro de regreso
    side_up = [(Rb, 0.098), (Rb + 0.012, 0.112), (Rb + 0.03, 0.118), (Rb + 0.06, 0.128), (Rb + 0.1, 0.137), (Rb + 0.14, 0.14),
               (Rb + 0.18, 0.137), (Ro - 0.045, 0.128), (Ro - 0.02, 0.118), (Ro - 0.006, 0.104)]
    tread = [(Ro, 0.095 - 0.01 * k) for k in range(20)]
    outer = side_up + tread + [(rr, -y) for (rr, y) in reversed(side_up)]
    inner = [(Rb + 0.004, -0.082), (Rb + 0.03, -0.1), (Rb + 0.1, -0.118), (Rb + 0.17, -0.117), (Ro - 0.04, -0.1),
             (Ro - 0.018, -0.07), (Ro - 0.016, 0.0), (Ro - 0.018, 0.07), (Ro - 0.04, 0.1), (Rb + 0.17, 0.117), (Rb + 0.1, 0.118),
             (Rb + 0.03, 0.1), (Rb + 0.004, 0.082)]
    prof = outer + inner
    t0 = len(side_up)
    tread_idx = set(range(t0, t0 + len(tread)))
    wear_a = float(r.uniform(-0.6, 0.6))
    rings = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        ca, sa = math.cos(a), math.sin(a)
        ring = []
        for j, (rr, y) in enumerate(prof):
            if j in tread_idx:
                # 3 ranuras circunferenciales en zigzag (14 mm de ancho, 13 de hondo) y tacos de hombro cada 4 pasos
                zz = 0.008 * (1 if (i // 3) % 2 == 0 else -1)
                g = 0.0
                for yc in (-0.045, 0.0, 0.045):
                    if abs(y - (yc + zz)) < 0.0075:
                        g = 0.013
                if abs(y) > 0.068 and (i // 4) % 2 == 0 and abs(y) < 0.094:
                    g = max(g, 0.011 if abs(y) < 0.085 else 0.006)
                rr = rr - g
                rr -= 0.006 * max(0.0, math.cos(a - math.pi / 2 - wear_a)) ** 4          # banda gastada en un sector
            # costado que roza contra el muro (-Y): aplanado leve
            if y < -0.11:
                rr = rr - 0.004 * max(0.0, math.cos(a - wear_a))
            ring.append(mb.bm.verts.new((rr * ca, y, rr * sa)))
        rings.append(ring)
    n = len(prof)
    for i in range(seg):
        A, B = rings[i], rings[(i + 1) % seg]
        for j in range(n):
            jj = (j + 1) % n
            mb.face([A[j], A[jj], B[jj], B[j]], "rubber")
    return mb


def _barnacles(mb, r, pts_normals, size=(0.006, 0.014), mat="rubble"):
    """Percebes: conos bajos con cráter (8 lados, sombreado continuo) sobre puntos [(p, n)]."""
    with mb.soft():
        for (p, n) in pts_normals:
            s = float(r.uniform(*size))
            M, _ = frame_on(Vector(p), Vector(p) + Vector(n))
            M = M @ _R("Y", 90) @ _R("Z", float(r.uniform(0, 360)))
            lathe_n(mb, [(0.0, -0.002), (s, -0.002), (s * 0.95, s * 0.25), (s * 0.62, s * 0.62), (s * 0.4, s * 0.72), (s * 0.3, s * 0.5),
                         (0.0, s * 0.45)], seg=8, mat=mat, M=M)


def _timber_ring(w, d, rad, ns=6, nc=3):
    """Anillo de sección de madera (rectángulo w x d con esquinas gastadas de radio rad): [(x, y, nx, ny, cara, frac)]."""
    out = []
    cs = [(w / 2 - rad, d / 2 - rad, 0.0), (-w / 2 + rad, d / 2 - rad, 0.5 * math.pi), (-w / 2 + rad, -d / 2 + rad, math.pi),
          (w / 2 - rad, -d / 2 + rad, 1.5 * math.pi)]
    for ci, (cx, cy, a0) in enumerate(cs):
        for k in range(nc + 1):
            a = a0 + 0.5 * math.pi * k / nc
            out.append((cx + rad * math.cos(a), cy + rad * math.sin(a), math.cos(a), math.sin(a), -1, 0.0))
        nx_, ny_ = cs[(ci + 1) % 4][0], cs[(ci + 1) % 4][1]
        a1 = a0 + 0.5 * math.pi
        sx, sy = cx + rad * math.cos(a1), cy + rad * math.sin(a1)
        ex, ey = nx_ + rad * math.cos(a1), ny_ + rad * math.sin(a1)
        for k in range(1, ns):
            f = k / ns
            out.append((sx + (ex - sx) * f, sy + (ey - sy) * f, math.cos(a1), math.sin(a1), (ci + 1) % 4, f))
    return out


def timber_fender(height, seed=0, wl=None):
    """Defensa vertical de madera dura 0,30 x 0,30 (pilote de defensa): aristas gastadas de radio variable, grietas de
    secado a lo largo de la fibra, golpe de atraque en la cara de impacto, cabeza con grietas radiales, flejes de acero
    60 x 8 alrededor con pernos pasantes, placas de arandela y tuercas; con wl (cota local del agua) lleva percebes en la
    franja de mareas. Origen: centro de la cara trasera en la base; la cara de impacto mira a +Y."""
    r = rng(seed)
    mb = PMB()
    w = 0.3
    rads = [float(r.uniform(0.012, 0.03)) for _ in range(4)]
    rad = sum(rads) / 4
    ring = _timber_ring(w, w, rad)
    nr = len(ring)
    # grietas: (cara, frac, z0, z1, prof)
    checks = []
    for _ in range(int(r.integers(3, 6))):
        z0 = float(r.uniform(0.3, height - 1.2))
        checks.append((int(r.integers(0, 4)), int(r.integers(1, 6)) / 6.0, z0, z0 + float(r.uniform(0.6, 2.0)),
                       float(r.uniform(0.006, 0.014))))
    zn = height * 0.55
    zs = sorted({round(z, 4) for z in [0.0, height] + [height * k / int(height / 0.1) for k in range(1, int(height / 0.1))] +
                 [zn + 0.02 * k for k in range(-4, 18)]})
    rings = []
    for z in zs:
        rr_ = []
        for (x, y, nx, ny, face, frac) in ring:
            dd = float(r.uniform(-0.0012, 0.0012))
            for (cf, cfrac, c0, c1, cd) in checks:
                if face == cf and c0 <= z <= c1:
                    t = min(z - c0, c1 - z) / 0.25
                    if abs(frac - cfrac) < 1e-6:
                        dd -= cd * min(1.0, t)
            if ny > 0.7 and zn - 0.05 <= z <= zn + 0.35:          # golpe de atraque: hundido astillado en la cara +Y
                tt = math.sin(math.pi * (z - zn + 0.05) / 0.4)
                dd -= 0.028 * tt * (0.75 + 0.25 * math.cos(9 * x + 3.0)) + float(r.uniform(0, 0.004))
            ytop = y + w / 2
            rr_.append(mb.bm.verts.new((x + nx * dd, ytop + ny * dd, z)))
        rings.append(rr_)
    for i in range(len(rings) - 1):
        for j in range(nr):
            jj = (j + 1) % nr
            mb.face([rings[i][j], rings[i][jj], rings[i + 1][jj], rings[i + 1][j]], "wood_dark")
    mb.face(list(reversed(rings[0])), "wood_dark")
    # cabeza: chaflán de intemperie y grietas radiales (fan con vértices hundidos)
    topz = height
    inner = [mb.bm.verts.new((v.co.x * 0.88, (v.co.y - w / 2) * 0.88 + w / 2, topz + 0.012)) for v in rings[-1]]
    for j in range(nr):
        jj = (j + 1) % nr
        mb.face([rings[-1][j], rings[-1][jj], inner[jj], inner[j]], "wood_dark")
    c = mb.bm.verts.new((0.0, w / 2, topz + 0.018))
    crack = {int(r.integers(0, nr)), int(r.integers(0, nr)), int(r.integers(0, nr))}
    mids = []
    for j in range(nr):
        v = inner[j].co
        m = mb.bm.verts.new(((v.x + 0.0) * 0.5, (v.y + w / 2) * 0.5, topz + (0.004 if j in crack else 0.016)))
        mids.append(m)
    for j in range(nr):
        jj = (j + 1) % nr
        mb.face([inner[j], inner[jj], mids[jj], mids[j]], "wood_dark")
        mb.face([mids[j], mids[jj], c], "wood_dark")
    # flejes 60 x 8 alrededor y pernos pasantes con placa de arandela
    zf = [0.35, height * 0.5, height - 0.4]
    if wl is not None:
        zf = [max(wl + 0.6, 0.35), height * 0.5 + 0.6, height - 0.4]
    path = [(x * (w + 0.01) / w, (y) * (w + 0.01) / w + w / 2, 0.0) for (x, y) in rr_profile(w + 0.0, w + 0.0, rad + 0.004, n=4)]
    prof = rr_profile(0.008, 0.06, 0.0025, n=2)
    for z in zf:
        psweep(mb, prof, [(p[0], p[1], z) for p in path], "metal_rust", up=(0, 0, 1), closed=True)
        bev_plate(mb, [(-0.045, -0.045), (0.045, -0.045), (0.045, 0.045), (-0.045, 0.045)], 0.01, "metal_rust",
                  M=_T(0, w + 0.009, z) @ _R("X", -90), ch=0.0015)
        hexnut(mb, _T(0, w + 0.019, z) @ _R("X", -90), af=0.036, mat="metal_rust", stud=0.022)
    # percebes en la franja de mareas
    if wl is not None:
        pts = []
        for _ in range(140):
            z = float(r.uniform(max(0.05, wl - 1.6), wl + 0.25))
            face = int(r.integers(0, 4))
            u = float(r.uniform(-w / 2 + 0.03, w / 2 - 0.03))
            if face == 0:
                pts.append(((w / 2, u + w / 2, z), (1, 0, 0)))
            elif face == 1:
                pts.append(((u, w, z), (0, 1, 0)))
            elif face == 2:
                pts.append(((-w / 2, u + w / 2, z), (-1, 0, 0)))
            else:
                continue
        _barnacles(mb, r, pts, size=(0.006, 0.016))
    return mb


def marine_ladder(z0, z1, seed=0, standoff=0.17, brackets=None, wl=None):
    """Escalera marina de acero galvanizado (hoy oxidada) en el frente de atraque: largueros de solera 65 x 12 biselada,
    peldaños redondos Ø25 a 0,30 m soldados a través del larguero (uno doblado, alguno perdido), ménsulas de solera con
    placa de anclaje y 2 anclas al muro (en y = 0; la escalera queda en +Y), asideros de tubo Ø42 doblado con radio real
    que salen 0,95 m sobre la cubierta con placa base atornillada. brackets: cotas de las ménsulas; wl: cota del agua
    (percebes bajo ella)."""
    r = rng(seed)
    mb = PMB()
    xs = (-0.22, 0.22)
    for dx in xs:
        mb.box((dx - 0.006, standoff - 0.0325, z0), (dx + 0.006, standoff + 0.0325, z1 - 0.02), "metal_rust", bevel=0.002)
    bz = brackets if brackets is not None else [z0 + 0.4 + 1.5 * k for k in range(int((z1 - 0.2 - z0 - 0.4) / 1.5) + 1)]
    for z in bz:
        for dx in xs:
            # solera horizontal del muro al larguero, soldada al costado exterior del larguero
            sx = 1 if dx > 0 else -1
            mb.box((dx + sx * 0.006 - (0.012 if sx < 0 else 0.0), 0.012, z - 0.025), (dx + sx * 0.006 + (0.012 if sx > 0 else 0.0),
                   standoff + 0.025, z + 0.025), "metal_rust", bevel=0.0015)
            bev_plate(mb, [(-0.05, -0.065), (0.05, -0.065), (0.05, 0.065), (-0.05, 0.065)], 0.012, "metal_rust",
                      M=_T(dx + sx * 0.012, 0.0, z) @ _R("X", -90), ch=0.002)
            for zz in (-0.04, 0.04):
                hexnut(mb, _T(dx + sx * 0.012, 0.012, z + zz) @ _R("X", -90), af=0.024, mat="metal_rust", stud=0.012)
            weld(mb, [(dx + sx * 0.006, standoff - 0.02, z + 0.026), (dx + sx * 0.006, standoff + 0.024, z + 0.026)], r=0.003)
    # peldaños
    z = z0 + 0.15
    k = 0
    bent = int(r.integers(3, 8))
    while z < z1 - 0.15:
        if r.random() > 0.05:
            if k == bent:
                pts = [(-0.226 + 0.452 * q / 10, standoff - 0.035 * math.sin(math.pi * q / 10), z - 0.03 * math.sin(math.pi * q / 10))
                       for q in range(11)]
                mb.tube(pts, 0.0125, seg=20, mat="metal_rust")
            else:
                mb.tube([(-0.228, standoff, z), (0.228, standoff, z)], 0.0125, seg=20, mat="metal_rust")
            for dx in xs:
                for sx in (-1, 1):
                    weld(mb, [(dx + sx * 0.0065, standoff + 0.0135 * math.cos(a), z + 0.0135 * math.sin(a)) for a in
                              [2 * math.pi * q / 12 for q in range(13)]], r=0.0025)
        z += 0.30
        k += 1
    # asideros sobre la cubierta
    for dx in xs:
        pts = fillet([(dx, -0.35, z1 + 0.012), (dx, -0.35, z1 + 0.95), (dx, standoff, z1 + 0.95), (dx, standoff, z1 - 0.06)], 0.14, 8)
        mb.tube(pts, 0.021, seg=20, mat="metal_rust")
        bev_plate(mb, [(-0.06, -0.06), (0.06, -0.06), (0.06, 0.06), (-0.06, 0.06)], 0.012, "metal_rust", M=_T(dx, -0.35, z1), ch=0.002)
        for (bx, by) in ((-0.042, -0.042), (0.042, -0.042), (0.042, 0.042), (-0.042, 0.042)):
            hexnut(mb, _T(dx + bx, -0.35 + by, z1 + 0.012), af=0.019, mat="metal_rust", stud=0.008)
    if wl is not None:
        pts = []
        z = z0 + 0.1
        while z < wl + 0.2:
            for dx in xs:
                for sx in (-1, 1):
                    if r.random() < 0.55:
                        pts.append(((dx + sx * 0.006, standoff + float(r.uniform(-0.025, 0.025)), z + float(r.uniform(-0.05, 0.05))),
                                    (sx, 0, 0)))
            z += 0.07
        _barnacles(mb, r, pts, size=(0.005, 0.011))
    return mb


def _oct_ring(R, n_c=3, fr=0.18, phase=math.pi / 8):
    """Octágono de radio de esquina R con las esquinas redondeadas (n_c vértices por esquina): [(x, y)]."""
    pts = []
    for k in range(8):
        a = phase + 2 * math.pi * k / 8
        c = Vector((R * math.cos(a), R * math.sin(a), 0))
        p_prev = Vector((R * math.cos(a - math.pi / 4), R * math.sin(a - math.pi / 4), 0))
        p_next = Vector((R * math.cos(a + math.pi / 4), R * math.sin(a + math.pi / 4), 0))
        p0 = c.lerp(p_prev, fr * 0.5)
        p1 = c.lerp(p_next, fr * 0.5)
        for j in range(n_c):
            u = j / (n_c - 1)
            q = p0.lerp(c, u).lerp(c.lerp(p1, u), u)
            pts.append((q.x, q.y))
    return pts


def light_pole(height=9.0, seed=0, broken=False, arm=1.6):
    """Poste de alumbrado de acero (9 m): fuste octagonal cónico de esquinas redondeadas, placa base biselada sobre dado de
    mortero con 4 anclas de doble tuerca y 4 cartelas soldadas, registro de mano con marco y tapa atornillada, zapata de
    tierra, tapa superior, brazo de tubo Ø60 curvado con su abrazadera y tirante, luminaria tipo cobra (carcasa, puerta del
    difusor con bisagra y broche, difusor de vidrio, fotocelda de giro). broken: puerta colgando sin difusor y cables
    sueltos."""
    r = rng(seed)
    mb = PMB()
    _rr_loft(mb, [(-0.01, 0.5, 0.5, 0.04), (0.015, 0.5, 0.5, 0.04), (0.025, 0.47, 0.47, 0.03)], "concrete", corner_n=4)
    bev_plate(mb, [(-0.22, -0.2), (-0.2, -0.22), (0.2, -0.22), (0.22, -0.2), (0.22, 0.2), (0.2, 0.22), (-0.2, 0.22), (-0.22, 0.2)],
              0.025, "metal_paint", M=_T(0, 0, 0.025), ch=0.003)
    for (x, y) in ((-0.17, -0.17), (0.17, -0.17), (-0.17, 0.17), (0.17, 0.17)):
        with mb.soft():
            lathe_n(mb, [(0.0, -0.02), (0.011, -0.02), (0.011, 0.083), (0.0, 0.083)], seg=14, mat="metal_rust", M=_T(x, y, 0.0))
        hexnut(mb, _T(x, y, 0.025) @ _R("X", 180), af=0.036, mat="metal_rust", washer=True, stud=0.0)
        hexnut(mb, _T(x, y, 0.05), af=0.036, mat="metal_rust", washer=True, stud=0.0)
        hexnut(mb, _T(x, y, 0.0825), af=0.036, mat="metal_rust", washer=False, stud=0.014)
    for k in range(4):
        Mg = _R("Z", 45 + 90 * k) @ _T(0.095, 0, 0.05)
        pts = [(0.0, 0.0), (0.11, 0.0), (0.11, 0.025), (0.02, 0.2), (0.0, 0.2)]
        bev_plate(mb, pts, 0.01, "metal_paint", M=Mg @ _T(0, 0.005, 0) @ _R("X", 90), ch=0.0015)
    # fuste octagonal cónico
    R0, R1 = 0.135, 0.07
    zs = [0.05, 0.3, 1.0, 3.0, 5.0, 7.0, height - 0.06]
    rings = []
    for z in zs:
        Rz = R0 - (R0 - R1) * max(0.0, z - 0.3) / (height - 0.3)
        rings.append([mb.bm.verts.new((x, y, z)) for (x, y) in _oct_ring(Rz)])
    nr = len(rings[0])
    for i in range(len(rings) - 1):
        for j in range(nr):
            jj = (j + 1) % nr
            mb.face([rings[i][j], rings[i][jj], rings[i + 1][jj], rings[i + 1][j]], "metal_paint")
    weld(mb, [(x * 1.03, y * 1.03, 0.054) for (x, y) in _oct_ring(R0)] + [(_oct_ring(R0)[0][0] * 1.03, _oct_ring(R0)[0][1] * 1.03, 0.054)],
         r=0.005, mat="metal_paint")
    lathe_n(mb, [(R1 * 1.05, height - 0.06), (R1 * 1.05, height - 0.02), (R1 * 0.9, height + 0.01), (R1 * 0.5, height + 0.025),
                 (0.0, height + 0.03)], seg=24, mat="metal_paint")
    # registro de mano (cara -Y): marco soldado y tapa con 2 tornillos
    Rh = R0 - (R0 - R1) * 0.45 / (height - 0.3)
    yf = -Rh * math.cos(math.pi / 8)
    psweep(mb, rr_profile(0.012, 0.01, 0.003, n=2), [(x, yf - 0.004, z) for (x, z) in rr_profile(0.1, 0.36, 0.03, n=4, cy=0.75)],
           "metal_paint", up=(0, -1, 0), closed=True)
    mb.box((-0.05, yf - 0.0165, 0.58), (0.05, yf - 0.0095, 0.92), "metal_paint", bevel=0.003)
    for z in (0.61, 0.89):
        hexnut(mb, _T(0, yf - 0.0165, z) @ _R("X", 90), af=0.012, mat="metal_rust", washer=False, stud=0.0)
    lathe_n(mb, [(0.0, -0.004), (0.012, -0.004), (0.012, 0.02), (0.009, 0.024), (0.0, 0.025)], seg=16, mat="copper",
            M=_T(0.0, yf, 0.36) @ _R("X", 90))
    # brazo curvo y abrazadera
    pts = []
    zt = height - 0.35
    for k in range(17):
        t = k / 16
        pts.append(Vector((0.0, -arm * t, zt + 0.55 * math.sin(t * math.pi / 2) - 0.12 * t * t)))
    mb.tube([Vector((0, 0.02, zt))] + pts[1:], 0.03, seg=24, mat="metal_paint")
    Rarm = R0 - (R0 - R1) * (zt - 0.3) / (height - 0.3)
    lathe_n(mb, [(0.029, 0.0), (0.042, 0.0), (0.046, 0.01), (0.046, 0.05), (0.04, 0.06), (0.029, 0.06)], seg=24, mat="metal_paint",
            M=_T(0, -Rarm * 0.92, zt) @ _R("X", 90), caps=False)
    tb = 0.39
    zb = zt + 0.55 * math.sin(tb * math.pi / 2) - 0.12 * tb * tb - 0.02
    mb.tube(fillet([(0, -R1 * 0.95, height - 0.75), (0, -arm * tb * 0.45, height - 0.42), (0, -arm * tb, zb)], 0.2, 6), 0.016, seg=16,
            mat="metal_paint")
    head = pts[-1]
    Mh = _T(head.x, head.y, head.z) @ _R("Z", -90) @ _R("Y", 6)
    # adaptador (slip-fitter) con 2 tornillos
    lathe_n(mb, [(0.0, -0.02), (0.042, -0.02), (0.046, 0.0), (0.046, 0.12), (0.04, 0.13), (0.0, 0.13)], seg=24, mat="metal_paint",
            M=Mh @ _T(-0.12, 0, 0) @ _R("Y", 90))
    for xx in (-0.08, -0.03):
        hexnut(mb, Mh @ _T(xx, 0.0, 0.046), af=0.013, mat="metal_rust", washer=False, stud=0.006)
    if not broken:
        st = [(0.0, 0.1, 0.07, 0.0), (0.04, 0.17, 0.11, 0.008), (0.12, 0.27, 0.15, 0.016), (0.25, 0.36, 0.18, 0.02),
              (0.45, 0.4, 0.19, 0.02), (0.62, 0.38, 0.17, 0.016), (0.75, 0.33, 0.14, 0.01), (0.84, 0.25, 0.1, 0.0),
              (0.885, 0.16, 0.07, -0.006), (0.9, 0.08, 0.04, -0.008)]
        loft(mb, st, seg=32, mat="metal_paint", M=Mh, ex=3.0)
        # puerta del difusor (marco) y difusor de vidrio
        loft(mb, [(0.1, 0.25, 0.04, -0.045), (0.14, 0.32, 0.05, -0.05), (0.45, 0.39, 0.05, -0.055), (0.74, 0.33, 0.05, -0.05),
                  (0.8, 0.27, 0.04, -0.045)], seg=32, mat="metal_paint", M=Mh, ex=3.4)
        loft(mb, [(0.16, 0.22, 0.03, -0.07), (0.2, 0.28, 0.1, -0.09), (0.45, 0.33, 0.14, -0.1), (0.68, 0.27, 0.1, -0.09),
                  (0.74, 0.2, 0.03, -0.07)], seg=32, mat="glass", M=Mh, ex=2.2)
        lathe_n(mb, [(0.0, 0.0), (0.038, 0.0), (0.038, 0.05), (0.034, 0.06), (0.02, 0.07), (0.0, 0.072)], seg=24, mat="plastic",
                M=Mh @ _T(0.3, 0.0, 0.105))
        mb.box((0.86, -0.025, -0.075), (0.9, 0.025, -0.045), "metal_paint", bevel=0.004, m=Mh)          # broche
        mb.tube([Mh @ Vector((0.06, -0.08, -0.05)), Mh @ Vector((0.06, 0.08, -0.05))], 0.008, seg=14, mat="metal_paint")   # bisagra
    else:   # carcasa abierta, puerta colgando de la bisagra, difusor perdido, cables sueltos
        loft(mb, [(-0.02, 0.1, 0.07, 0.0), (0.05, 0.2, 0.12, 0.0), (0.3, 0.34, 0.16, 0.0), (0.6, 0.3, 0.13, 0.0),
                  (0.72, 0.16, 0.08, -0.01)], seg=32, mat="metal_paint", M=Mh @ _R("Y", 18), ex=3.0)
        Md = Mh @ _T(0.06, 0, -0.05) @ _R("Y", 72)
        loft(mb, [(0.0, 0.25, 0.03, 0.0), (0.04, 0.32, 0.04, -0.005), (0.35, 0.39, 0.04, -0.01), (0.64, 0.33, 0.04, -0.005),
                  (0.7, 0.27, 0.03, 0.0)], seg=32, mat="metal_paint", M=Md, ex=3.4)
        for k in range(3):
            rope(mb, [Mh @ Vector((0.1 + 0.03 * k, -0.02 + 0.02 * k, -0.05)), Mh @ Vector((0.2, 0.05 * k, -0.4)),
                      Mh @ Vector((0.17 + 0.02 * k, 0.08, -0.55 - 0.05 * k))], r=0.004, mat="cable")
    del r
    return mb


def drum(seed=0):
    """Tambo de acero de 200 L (Ø 572 mm, alto 880 mm): cuerpo con dos aros de rodadura y chimbas rebordeadas, tapa
    abombada con tapón de 2" y de 3/4" con sus bridas, costura vertical soldada, abolladuras y golpes en la chimba."""
    r = rng(seed)
    mb = PMB()
    dents_ = [(float(r.uniform(0, 2 * math.pi)), float(r.uniform(0.1, 0.8)), float(r.uniform(0.004, 0.025)),
               float(r.uniform(0.25, 0.6)), float(r.uniform(0.05, 0.15))) for _ in range(int(r.integers(1, 4)))]

    def dr(a, z):
        s = 0.0
        for (da_, dz, amp, wa, wz) in dents_:
            dd = math.atan2(math.sin(a - da_), math.cos(a - da_))
            q = (dd / wa) ** 2 + ((z - dz) / wz) ** 2
            if q < 9:
                s -= amp * math.exp(-q)
        return s
    prof = [(0.0, 0.0), (0.255, 0.0), (0.27, 0.004), (0.284, 0.006), (0.292, 0.012), (0.294, 0.02), (0.29, 0.027),
            (0.286, 0.034), (0.286, 0.26), (0.29, 0.272), (0.296, 0.285), (0.29, 0.298), (0.286, 0.31), (0.286, 0.57),
            (0.29, 0.582), (0.296, 0.595), (0.29, 0.608), (0.286, 0.62), (0.286, 0.846), (0.29, 0.853), (0.294, 0.86),
            (0.292, 0.868), (0.284, 0.874), (0.276, 0.872), (0.272, 0.866), (0.262, 0.868), (0.2, 0.872), (0.1, 0.875),
            (0.0, 0.876)]
    lathe_n(mb, prof, seg=64, mat="metal_paint", caps=False, dr=dr)
    weld(mb, [(0.287, 0.0, z) for z in (0.036, 0.26)] , r=0.0018, mat="metal_paint")
    weld(mb, [(0.287, 0.0, z) for z in (0.31, 0.57)], r=0.0018, mat="metal_paint")
    weld(mb, [(0.287, 0.0, z) for z in (0.62, 0.845)], r=0.0018, mat="metal_paint")
    for (x, y, rr, hex_) in ((0.17, 0.0, 0.032, True), (-0.13, 0.11, 0.017, False)):
        lathe_n(mb, [(rr * 1.45, 0.874), (rr * 1.45, 0.879), (rr * 1.25, 0.884), (rr * 1.05, 0.884), (rr * 1.05, 0.878)], seg=24,
                mat="metal_paint", M=_T(x, y, 0), caps=False)
        lathe_n(mb, [(rr * 1.05, 0.876), (rr, 0.889), (rr * 0.98, 0.892), (rr * 0.5, 0.892), (rr * 0.48, 0.886), (0.0, 0.886)],
                seg=24, mat="metal_rust", M=_T(x, y, 0), caps=False)
        if hex_:
            mb.box((x - rr * 0.42, y - rr * 0.12, 0.886), (x + rr * 0.42, y + rr * 0.12, 0.893), "metal_rust", bevel=0.001)
    return mb


# ------------------------------------------------------------------------------------------------ contenedor
def _casting(mb, M, holes, mat="metal_rust", size=(0.178, 0.162, 0.118)):
    """Cantonera ISO 1161 (178 x 162 x 118) en la esquina local (0..sx, 0..sy, 0..sz) con aberturas ovaladas reales
    (bocas con túnel y fondo) en las caras indicadas: holes = {'x0','x1','y0','y1','z0','z1'} (x0 = cara en x = 0, etc.)."""
    sx, sy, sz = size
    ne = 5                                     # vértices intermedios por arista (para que las caras con boca casen)
    C = {}
    for i in (0, 1):
        for j in (0, 1):
            for k in (0, 1):
                C[(i, j, k)] = mb.bm.verts.new(M @ Vector((i * sx, j * sy, k * sz)))
    E = {}

    def edge(a, b):
        key = (a, b) if a < b else (b, a)
        if key not in E:
            pa, pb = C[key[0]].co, C[key[1]].co
            E[key] = [mb.bm.verts.new(pa.lerp(pb, (q + 1) / (ne + 1))) for q in range(ne)]
        vs = E[key]
        return vs if key == (a, b) else list(reversed(vs))

    def loop(cs):
        out = []
        for q in range(4):
            a, b = cs[q], cs[(q + 1) % 4]
            out.append(C[a])
            out += edge(a, b)
        return out
    # caras con sus 4 esquinas en orden antihorario visto desde afuera
    faces = {
        "x0": [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)], "x1": [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)],
        "y0": [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)], "y1": [(0, 1, 0), (0, 1, 1), (1, 1, 1), (1, 1, 0)],
        "z0": [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)], "z1": [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
    }
    nrm = {"x0": (-1, 0, 0), "x1": (1, 0, 0), "y0": (0, -1, 0), "y1": (0, 1, 0), "z0": (0, 0, -1), "z1": (0, 0, 1)}
    for nm, cs in faces.items():
        lp = loop(cs)
        if nm not in holes:
            mb.face(lp, mat)
            continue
        ctr = sum((v.co for v in lp), Vector()) / len(lp)
        n = (M.to_3x3() @ Vector(nrm[nm])).normalized()
        # semiejes de la boca: ovalada de 124 x 63 en techo/piso, 78 x 51 en costados y testas
        ax = [Vector(M.to_3x3() @ Vector(v)).normalized() for v in ((1, 0, 0), (0, 1, 0), (0, 0, 1)) if abs(Vector(v).dot(Vector(nrm[nm]))) < 0.5]
        if nm in ("z0", "z1"):
            a_len, b_len = 0.062, 0.032
        else:
            a_len, b_len = 0.039, 0.026
        A, B = ax[0], ax[1]
        if nm in ("x0", "x1"):
            A, B = ax[0], ax[1]          # y (ancho) y z (alto)
        ring_o, ring_i = [], []
        for v in lp:
            d = v.co - ctr
            ang = math.atan2(d.dot(B), d.dot(A))
            c, s = math.cos(ang), math.sin(ang)
            ex = 3.2
            xx = a_len * math.copysign(abs(c) ** (2 / ex), c)
            yy = b_len * math.copysign(abs(s) ** (2 / ex), s)
            p = ctr + A * xx + B * yy
            ring_o.append(mb.bm.verts.new(p - n * 0.002))
            ring_i.append(mb.bm.verts.new(p - n * 0.03 + (A * xx + B * yy) * -0.08))
        k = len(lp)
        for q in range(k):
            qq = (q + 1) % k
            mb.face([lp[q], lp[qq], ring_o[qq], ring_o[q]], mat)
            mb.face([ring_o[q], ring_o[qq], ring_i[qq], ring_i[q]], mat)
        mb.face(list(ring_i), mat)


def _door_leaf(mb, M, lw, lh, r, sg, mat, open_ang=0.0):
    """Hoja de puerta de contenedor: marco perimetral de perfil cerrado, lámina de 2 mm con 4 corrugaciones horizontales,
    burlete, 4 bisagras, 2 barras de cierre Ø34 con guías, levas, manijas y retenes, placa de datos (hoja izquierda).
    Local: bisagra en y = 0, la hoja crece hacia sg·Y, cara exterior hacia +X, z = 0 al pie de la hoja."""
    d = PMB()
    y0, y1 = (0.0, lw) if sg > 0 else (-lw, 0.0)
    # marco: largueros verticales y travesaños (perfil cerrado 0,05 x 0,09 de esquinas redondeadas)
    for yy in (y0 + 0.03, y1 - 0.03):
        psweep(d, rr_profile(0.05, 0.06, 0.006), [(0.03, yy, 0.0), (0.03, yy, lh)], mat, up=(1, 0, 0))
    for zz in (0.05, lh - 0.05):
        psweep(d, rr_profile(0.09, 0.06, 0.008), [(0.03, y0 + 0.055, zz), (0.03, y1 - 0.055, zz)], mat, up=(1, 0, 0))
    # lámina con corrugaciones horizontales (perfil a lo largo de z)
    up = corr_pts(lh - 0.2, pitch=(lh - 0.2) / 4.0, depth=0.03, outer=0.24, inner=0.22, phase=0.0)
    # u corre en z; la lámina se arma en el plano YZ con peralte hacia +X
    rows = 6
    ya, yb = y0 + 0.055, y1 - 0.055
    vs_o, vs_i = [], []
    for jj in range(rows + 1):
        yy = ya + (yb - ya) * jj / rows
        ro, ri = [], []
        for (u, dd) in up:
            z = 0.1 + u
            ro.append(d.bm.verts.new((0.03 + 0.012 + dd, yy, z)))
            ri.append(d.bm.verts.new((0.03 + 0.010 + dd, yy, z)))
        vs_o.append(ro)
        vs_i.append(ri)
    for jj in range(rows):
        for i in range(len(up) - 1):
            d.face([vs_o[jj][i], vs_o[jj + 1][i], vs_o[jj + 1][i + 1], vs_o[jj][i + 1]], mat)
            d.face([vs_i[jj][i], vs_i[jj][i + 1], vs_i[jj + 1][i + 1], vs_i[jj + 1][i]], mat)
    # burlete (labio vertical de hule en el canto de cierre)
    ye = y1 if sg > 0 else y0
    psweep(d, rr_profile(0.04, 0.012, 0.004), [(0.012, ye + sg * 0.004, 0.02), (0.012, ye + sg * 0.004, lh - 0.02)], "rubber",
           up=(1, 0, 0))
    # bisagras: hoja soldada + nudillo con perno
    for zz in (0.2, 0.85, 1.5, lh - 0.18):
        d.box((0.055, min(0.0, sg * 0.16), zz), (0.075, max(0.0, sg * 0.16), zz + 0.075), "metal_rust", bevel=0.004)
        lathe_n(d, [(0.0, zz - 0.012), (0.019, zz - 0.012), (0.021, zz - 0.006), (0.021, zz + 0.081), (0.019, zz + 0.087), (0.0, zz + 0.087)],
                seg=24, mat="metal_rust", M=_T(0.065, 0.0, 0.0))
        lathe_n(d, [(0.0, zz + 0.087), (0.011, zz + 0.087), (0.011, zz + 0.1), (0.0, zz + 0.103)], seg=16, mat="metal_rust",
                M=_T(0.065, 0.0, 0.0))
    # barras de cierre (2 por hoja) con guías, levas, manija y retén
    for f in (0.36, 0.8):
        yy = sg * lw * f
        bar = 0.017
        xb = 0.098
        d.tube([(xb, yy, -0.045), (xb, yy, lh + 0.045)], bar, seg=24, mat="metal_rust")
        for zz in (0.32, 0.95, 1.6, lh - 0.32):                         # guías: fleje doblado en U soldado a la lámina
            pts = fillet([(0.045, yy - 0.04, zz), (xb + bar + 0.006, yy - 0.04, zz), (xb + bar + 0.006, yy + 0.04, zz),
                          (0.045, yy + 0.04, zz)], 0.02, 5)
            psweep(d, rr_profile(0.006, 0.04, 0.002, n=2), pts, "metal_rust", up=(0, 0, 1))
        for (zc, s_) in ((-0.02, -1), (lh + 0.02, 1)):                   # levas
            d.box((xb - 0.012, yy - 0.03, zc - 0.02), (xb + 0.028, yy + 0.035, zc + 0.02), "metal_rust", bevel=0.005)
        hz = 1.05
        lathe_n(d, [(0.0, -0.035), (0.026, -0.035), (0.028, -0.025), (0.028, 0.025), (0.026, 0.035), (0.0, 0.035)], seg=24,
                mat="metal_rust", M=_T(xb, yy, hz))
        ang = float(r.uniform(-4, 4)) if open_ang == 0 else float(r.uniform(-4, 35))
        hp = [(xb + 0.03, yy, hz), (xb + 0.06, yy, hz)]
        a = math.radians(ang)
        tip = (xb + 0.06, yy - sg * 0.3 * math.cos(a), hz - 0.3 * math.sin(a))
        psweep(d, rr_profile(0.014, 0.03, 0.005), fillet([hp[0], hp[1], tip], 0.03, 5), "metal_rust", up=(0, 0, 1))
        yr = yy - sg * 0.26
        d.box((0.07, yr - 0.02, hz - 0.035), (0.125, yr + 0.02, hz - 0.018), "metal_rust", bevel=0.004)      # retén de la manija
    if sg < 0:                                                           # placa de datos remachada en la hoja izquierda
        d.box((0.044, y0 + 0.2, 1.35), (0.05, y0 + 0.5, 1.55), "aluminium", bevel=0.002)
        for (py, pz) in ((0.21, 1.36), (0.49, 1.36), (0.21, 1.54), (0.49, 1.54)):
            lathe_n(d, [(0.0, 0.0), (0.004, 0.0), (0.0035, 0.002), (0.0, 0.0025)], seg=10, mat="aluminium",
                    M=_T(0.05, y0 + py, pz) @ _R("Y", 90))
    mb.join(d, M @ _R("Z", open_ang))


def container(seed=0, open_doors=False, mat="container"):
    """Contenedor ISO 668 1CC de 20' (6 058 x 2 438 x 2 591). Local: x 0..L, y 0..W, z 0..H; puertas en x = L.
    Construcción ISO 1496-1: 8 cantoneras ISO 1161 con bocas reales, postes de esquina de lámina prensada, largueros
    inferiores en C con bolsas para montacargas (360 x 115 a 2 050 entre centros) y túnel, largueros superiores de tubo
    60 x 60, costados de lámina trapezoidal (paso 278, peralte 36), frente corrugado, techo corrugado transversal con
    abolladuras, piso de triplay sobre travesaños, cabezal y umbral de puertas con retenes de leva, 2 hojas con 4 bisagras,
    2 barras de cierre Ø34 cada una, manijas, burletes y placa de datos."""
    r = rng(seed)
    mb = PMB()
    L, W, H = 6.058, 2.438, 2.591
    m = mat
    cx, cy, cz = 0.178, 0.162, 0.118
    zr = 0.0125                                  # los largueros inferiores quedan 12,5 mm sobre el plano de las cantoneras
    # --- cantoneras
    for (i, j) in ((0, 0), (1, 0), (0, 1), (1, 1)):
        for k in (0, 1):
            x0 = 0.0 if i == 0 else L - cx
            y0 = 0.0 if j == 0 else W - cy
            z0 = 0.0 if k == 0 else H - cz
            holes = {("x0" if i == 0 else "x1"), ("y0" if j == 0 else "y1"), ("z0" if k == 0 else "z1")}
            _casting(mb, _T(x0, y0, z0), holes)
    # --- postes de esquina (lámina prensada 6 mm: los del frente en L con pestaña; los de puerta, sección cerrada)
    #     psweep vertical con up = +Y: el eje x del perfil corre hacia -X del mundo (por eso el signo de ox)
    for (i, j) in ((0, 0), (1, 0), (0, 1), (1, 1)):
        sx = 1 if i == 0 else -1
        sy = 1 if j == 0 else -1
        X, Y = (0.0 if i == 0 else L), (0.0 if j == 0 else W)
        if i == 1:
            offs = [(sx * 0.055 + px, sy * 0.065 + py) for (px, py) in rr_profile(0.11, 0.13, 0.008)]
        else:
            base = [(0.0, 0.0), (0.13, 0.0), (0.13, 0.03), (0.115, 0.03), (0.112, 0.008), (0.008, 0.008), (0.008, 0.112),
                    (0.03, 0.115), (0.03, 0.13), (0.0, 0.13)]
            offs = round_poly([(sx * px, sy * py) for (px, py) in base], 0.003, 2)
        psweep(mb, [(-ox, oy) for (ox, oy) in offs], [(X, Y, cz), (X, Y, H - cz)], m, up=(0, 1, 0), miter=False)
    # --- largueros inferiores (C 158 con alas de 48 hacia adentro) con bolsas para montacargas
    pockets = [(L / 2 - 1.025 - 0.18, L / 2 - 1.025 + 0.18), (L / 2 + 1.025 - 0.18, L / 2 + 1.025 + 0.18)]
    hp = 0.115
    for (Y, sy) in ((0.0, 1), (W, -1)):
        segs = [(cx, pockets[0][0]), (pockets[0][1], pockets[1][0]), (pockets[1][1], L - cx)]
        c_prof = [(0.0, 0.0), (0.0, 0.158), (0.048, 0.158), (0.048, 0.152), (0.0045, 0.152), (0.0045, 0.006), (0.03, 0.006),
                  (0.03, 0.0)]
        cp = round_poly([(-sy * px, zr + pz) for (px, pz) in c_prof], 0.003, 2)
        for (a, b) in segs:
            psweep(mb, [(y, z) for (y, z) in cp], [(a, Y, 0.0), (b, Y, 0.0)], m, up=(0, 0, 1), miter=False)
        for (a, b) in pockets:
            # tramo del larguero sobre la bolsa + marco de refuerzo + túnel de la bolsa
            cp2 = round_poly([(-sy * px, zr + pz) for (px, pz) in ((0.0, hp + 0.004), (0.0, 0.158), (0.048, 0.158), (0.048, 0.152),
                                                                  (0.0045, 0.152), (0.0045, hp + 0.004))], 0.002, 2)
            psweep(mb, cp2, [(a, Y, 0.0), (b, Y, 0.0)], m, up=(0, 0, 1), miter=False)
            yi0, yi1 = (Y, Y + sy * 0.006)
            mb.box((a - 0.012, min(yi0, yi1) - 0.002, zr), (a, max(yi0, yi1) + 0.002, zr + hp + 0.01), m)
            mb.box((b, min(yi0, yi1) - 0.002, zr), (b + 0.012, max(yi0, yi1) + 0.002, zr + hp + 0.01), m)
            if sy > 0:
                for (xa, xb_) in ((a, a + 0.006), (b - 0.006, b)):
                    mb.box((xa, 0.006, zr), (xb_, W - 0.006, zr + hp), m, bevel=0.001)
                mb.box((a, 0.006, zr), (b, W - 0.006, zr + 0.006), m, bevel=0.001)
                mb.box((a, 0.006, zr + hp - 0.006), (b, W - 0.006, zr + hp), m, bevel=0.001)
    # --- largueros superiores (tubo 60 x 60 x 3)
    for (Y, sy) in ((0.0, 1), (W, -1)):
        psweep(mb, rr_profile(0.06, 0.06, 0.006), [(cx, Y + sy * 0.03, H - 0.03), (L - cx, Y + sy * 0.03, H - 0.03)], m, up=(0, 0, 1))
    # --- testa frontal (x = 0): larguero inferior, cabezal superior y muro corrugado vertical
    mb.box((0.0, cy, zr), (0.16, W - cy, zr + 0.158), m, bevel=0.004)
    psweep(mb, rr_profile(0.1, 0.11, 0.008), [(0.05, cy, H - 0.055), (0.05, W - cy, H - 0.055)], m, up=(0, 0, 1))
    upf = corr_pts(W - 0.26, pitch=0.278, depth=0.045, outer=0.07, inner=0.07, phase=0.02)
    Mf = Matrix(((0, 1, 0, 0.05), (-1, 0, 0, W - 0.13), (0, 0, 1, 0.0), (0, 0, 0, 1)))
    dfront = dents(r, int(r.integers(1, 4)), 0.2, W - 0.4, 0.4, 2.2, amp=(0.01, 0.035), rad=(0.15, 0.4))
    csheet(mb, Mf, upf, zr + 0.158, H - 0.11, m, nrows=10, t=0.002, dent=dfront)
    # --- costados: lámina trapezoidal de 278 mm
    for (Y, sgn) in ((0.0, 1), (W, -1)):
        ups = corr_pts(L - 0.24, pitch=0.278, depth=0.036, phase=0.03)
        if sgn > 0:
            Ms = Matrix(((1, 0, 0, 0.12), (0, 1, 0, Y + 0.04), (0, 0, 1, 0.0), (0, 0, 0, 1)))
        else:
            Ms = Matrix(((-1, 0, 0, L - 0.12), (0, -1, 0, Y - 0.04), (0, 0, 1, 0.0), (0, 0, 0, 1)))
        dside = dents(r, int(r.integers(2, 6)), 0.3, L - 0.6, 0.4, 2.3, amp=(0.008, 0.04), rad=(0.15, 0.55))
        csheet(mb, Ms, ups, zr + 0.152, H - 0.058, m, nrows=12, t=0.002, dent=dside)
    # --- techo corrugado transversal (peralte 20, paso 209) con abolladuras hacia abajo
    upr = corr_pts(L - 0.21, pitch=0.209, depth=0.02, outer=0.06, inner=0.06, phase=0.0)
    Mr = Matrix(((1, 0, 0, 0.09), (0, 0, 1, 0.0), (0, -1, 0, H - 0.025), (0, 0, 0, 1)))      # u -> x, v -> y, peralte -> +z
    droof = dents(r, int(r.integers(2, 6)), 0.3, L - 0.6, 0.3, W - 0.3, amp=(0.01, 0.045), rad=(0.2, 0.6))
    csheet(mb, Mr, upr, 0.055, W - 0.055, m, nrows=8, t=0.002, dent=droof)
    # --- piso de triplay 28 mm sobre travesaños en C
    mb.box((0.16, 0.05, zr + 0.13), (L - 0.13, W - 0.05, zr + 0.158), "plywood", bevel=0.002)
    x = 0.3
    while x < L - 0.2:
        if not any(a - 0.03 < x < b + 0.03 for (a, b) in pockets):
            mb.box((x - 0.022, 0.05, zr + 0.01), (x + 0.022, W - 0.05, zr + 0.13), m, bevel=0.002)
        x += 0.3
    # --- extremo de puertas (x = L): umbral, cabezal y retenes de leva
    mb.box((L - 0.13, cy, zr), (L, W - cy, zr + 0.158), m, bevel=0.004)
    psweep(mb, rr_profile(0.13, 0.15, 0.01), [(L - 0.065, cy, H - 0.09), (L - 0.065, W - cy, H - 0.09)], m, up=(0, 0, 1))
    lw = (W - 2 * 0.13) / 2 - 0.004
    lh = H - 0.17 - 0.165
    for (yy, sg) in ((0.13, 1), (W - 0.13, -1)):
        for f in (0.36, 0.8):
            yb = yy + sg * lw * f
            for zc in (0.15, 0.17 + lh + 0.02):
                mb.box((L, yb - 0.04, zc - 0.03), (L + 0.072, yb + 0.045, zc + 0.03), "metal_rust", bevel=0.006)
        for zz in (0.2, 0.85, 1.5, lh - 0.18):               # orejas de bisagra en el poste
            mb.box((L - 0.005, yy - sg * 0.03 - 0.02, 0.17 + zz - 0.012), (L + 0.075, yy - sg * 0.03 + 0.02, 0.17 + zz),
                   "metal_rust", bevel=0.004)
            mb.box((L - 0.005, yy - sg * 0.03 - 0.02, 0.17 + zz + 0.087), (L + 0.075, yy - sg * 0.03 + 0.02, 0.17 + zz + 0.099),
                   "metal_rust", bevel=0.004)
    # --- hojas
    for (yy, sg) in ((0.13, 1), (W - 0.13, -1)):
        ang = (float(r.uniform(70, 120)) if open_doors else 0.0) * (-sg)
        _door_leaf(mb, _T(L - 0.01, yy, 0.17), lw, lh, r, sg, m, open_ang=ang)
    return mb


# ------------------------------------------------------------------------------------------------ grúa de pedestal
def angle_sweep(mb, p0, p1, leg=0.08, t=0.008, mat="metal_paint", up=(0, 0, 1), flip=False):
    """Ángulo L laminado (alas iguales, filete de raíz y puntas redondeadas) de p0 a p1, con la misma colocación que
    angle_bar: talón sobre el eje, alas hacia +Y y +Z del marco de frame_on (o -Y/+Z con flip)."""
    s = 1.0 if flip else -1.0                   # psweep: x del perfil = -Y del marco de frame_on
    rr = t * 0.6
    pts = [(0.0, 0.0), (s * leg, 0.0), (s * leg, t), (s * (t + rr), t), (s * t, t + rr), (s * t, leg), (0.0, leg)]
    pts = round_poly(pts, t * 0.35, 2)
    if s > 0:
        pts = list(reversed(pts))
    psweep(mb, pts, [p0, p1], mat, up=up, miter=False)


def _hook(mb, M, scale=1.0, mat="metal_rust"):
    """Gancho forjado de un ramal (DIN 15401 aprox.): caña roscada con tuerca, garganta y punta de sección trapezoidal que
    adelgaza, pestillo de seguridad. Plano XZ local, la caña sube por +Z desde el origen."""
    S = scale
    path = [(0.0, 0.0, 0.0), (0.0, 0.0, -0.06 * S), (0.0, 0.0, -0.12 * S)]
    for k in range(1, 17):
        a = math.radians(180 + 240 * k / 16)
        path.append((0.09 * S + 0.09 * S * math.cos(a), 0.0, -0.2 * S + 0.09 * S * math.sin(a)))
    n = len(path)
    sc = []
    for i in range(n):
        f = i / (n - 1)
        sc.append(0.62 if f < 0.12 else (0.62 + 0.38 * math.sin(math.pi * min(1.0, (f - 0.12) / 0.5)) if f < 0.62 else
                                          max(0.32, 1.0 - 1.25 * (f - 0.62))))
    prof = round_poly([(-0.028 * S, -0.022 * S), (0.032 * S, -0.016 * S), (0.032 * S, 0.016 * S), (-0.028 * S, 0.022 * S)], 0.012 * S, 3)
    psweep(mb, prof, [M @ Vector(p) for p in path], mat, up=tuple(M.to_3x3() @ Vector((0, 1, 0))), scales=sc)
    lathe_n(mb, [(0.0, 0.0), (0.024 * S, 0.0), (0.024 * S, 0.09 * S), (0.021 * S, 0.095 * S), (0.0, 0.095 * S)], seg=24, mat=mat, M=M)
    hexnut(mb, M @ _T(0, 0, 0.095 * S), af=0.06 * S, mat=mat, washer=True, stud=0.02 * S)
    tip = M @ Vector(path[-1])
    p0 = M @ Vector((0.03 * S, 0.0, -0.07 * S))
    Ml, Ll = frame_on(p0, tip, up=tuple(M.to_3x3() @ Vector((0, 1, 0))))
    bev_plate(mb, [(0.0, -0.012 * S), (Ll * 0.92, -0.012 * S), (Ll * 0.92, 0.012 * S), (0.0, 0.012 * S)], 0.003 * S, mat,
              M=Ml @ _T(0, 0, -0.0015 * S), ch=0.0008)


def pedestal_crane(seed=0, yaw=-25.0, luff=38.0, boom_len=15.0, hook_z=-0.3):
    """Grúa de pedestal de muelle (origen: centro de la base sobre la cubierta, z = 0).
    Fija: dado de concreto con chaflán, brida base con 24 anclas, pedestal tubular Ø1,4 con costuras soldadas, 8 cartelas,
    puerta de registro abatible al pie (la escalera va DENTRO del pedestal y sale por una escotilla de la plataforma),
    brida superior con 36 pernos y corona dentada del rodamiento de giro.
    Giratoria: plataforma con canal perimetral, vigas y escotilla; piñón y motorreductor de giro; casa de máquinas de lámina
    corrugada con postes de ángulo, persianas y puerta entreabierta; contrapeso de concreto con marco y orejas; cabina con
    marcos, empaques, vidrios (algunos rotos), visera, puerta, asiento y consola; caballete en A de tubo Ø140 con orejas y
    pernos; pluma de celosía (cordones de ángulo laminado, celosía de tubo Ø42) con talón articulado y cabeza de placas y
    poleas; aparejo de la pluma (4 ramales), cable de izaje de 2 ramales, motón y gancho forjado con pestillo; barandal."""
    r = rng(seed)
    mb = PMB()
    # --- dado y brida base
    lathe_n(mb, [(1.3, 0.0), (1.3, 0.42), (1.285, 0.443), (1.26, 0.45), (0.0, 0.45)], seg=72, mat="concrete")
    lathe_n(mb, [(0.95, 0.45), (0.95, 0.512), (0.942, 0.52), (0.0, 0.52)], seg=72, mat="metal_paint")
    for k in range(24):
        a = 2 * math.pi * (k + 0.5) / 24
        hexnut(mb, _T(0.85 * math.cos(a), 0.85 * math.sin(a), 0.52), af=0.046, mat="metal_rust", stud=0.03)
    # --- pedestal con costuras
    lathe_n(mb, [(0.7, 0.52), (0.7, 4.30)], seg=72, mat="metal_paint", caps=False)
    for z in (0.528, 2.4, 4.292):
        weld(mb, [(0.704 * math.cos(2 * math.pi * q / 48), 0.704 * math.sin(2 * math.pi * q / 48), z) for q in range(49)], r=0.006,
             mat="metal_paint")
    weld(mb, [(0.704 * math.cos(math.radians(150)), 0.704 * math.sin(math.radians(150)), z) for z in (0.55, 4.27)], r=0.005,
         mat="metal_paint")
    for k in range(8):
        Mg = _R("Z", 22.5 + 45 * k) @ _T(0.7, 0.008, 0.52) @ _R("X", 90)
        bev_plate(mb, [(-0.02, 0.0), (0.22, 0.0), (0.22, 0.04), (0.0, 0.52), (-0.02, 0.52)], 0.016, "metal_paint", M=Mg, ch=0.002)
    # puerta de registro al pie (cara -Y): marco ovalado sobre el cilindro, hoja curva, 2 bisagras, 4 trinquetes
    def cyl_pt(x, z, rad):
        return Vector((x, -math.sqrt(max(rad * rad - x * x, 0.0)), z))
    oval = [(0.29 * math.cos(2 * math.pi * k / 40), 1.25 + 0.44 * math.sin(2 * math.pi * k / 40)) for k in range(40)]
    psweep(mb, rr_profile(0.04, 0.03, 0.006, n=2), [cyl_pt(x, z, 0.712) for (x, z) in oval], "metal_paint", up=(0, -1, 0), closed=True)
    rings = []
    for f in (0.0, 0.5, 0.92):
        rings.append([(x * f, 1.25 + (z - 1.25) * f) for (x, z) in oval])
    vo = [[mb.bm.verts.new(cyl_pt(x, z, 0.738)) for (x, z) in rg] for rg in rings[1:]]
    c = mb.bm.verts.new(cyl_pt(0.0, 1.25, 0.738))
    vi = [mb.bm.verts.new(cyl_pt(x, z, 0.722)) for (x, z) in rings[2]]
    for k in range(40):
        kk = (k + 1) % 40
        mb.face([c, vo[0][k], vo[0][kk]], "metal_paint")
        mb.face([vo[0][k], vo[1][k], vo[1][kk], vo[0][kk]], "metal_paint")
        mb.face([vo[1][k], vi[k], vi[kk], vo[1][kk]], "metal_paint")
    ci = mb.bm.verts.new(cyl_pt(0.0, 1.25, 0.722))
    for k in range(40):
        mb.face([ci, vi[(k + 1) % 40], vi[k]], "metal_paint")
    for z in (1.0, 1.5):
        p = cyl_pt(-0.3, z, 0.74)
        lathe_n(mb, [(0.0, -0.05), (0.022, -0.05), (0.022, 0.05), (0.0, 0.05)], seg=20, mat="metal_rust", M=_T(p.x, p.y, z))
        mb.box((p.x, p.y - 0.012, z - 0.03), (p.x + 0.12, p.y + 0.004, z + 0.03), "metal_rust", bevel=0.004)
    for (x, z) in ((0.25, 1.05), (0.25, 1.45), (0.0, 1.66), (0.0, 0.84)):
        p = cyl_pt(x, z, 0.74)
        Mh, _ = frame_on(p, p + Vector((0, -1, 0)))
        lathe_n(mb, [(0.0, 0.0), (0.018, 0.0), (0.018, 0.03), (0.0, 0.03)], seg=16, mat="metal_rust", M=Mh @ _R("Y", 90))
        mb.box(tuple(p + Vector((-0.06, -0.05, -0.012))), tuple(p + Vector((0.06, -0.03, 0.012))), "metal_rust", bevel=0.005)
    # --- brida superior (pernos colgando por debajo) y rodamiento de giro con corona dentada
    lathe_n(mb, [(0.7, 4.28), (0.9, 4.30), (0.9, 4.375), (0.894, 4.38), (0.0, 4.38)], seg=72, mat="metal_paint")
    for k in range(36):
        a = 2 * math.pi * (k + 0.5) / 36
        hexnut(mb, _T(0.8 * math.cos(a), 0.8 * math.sin(a), 4.30) @ _R("X", 180), af=0.036, mat="metal_rust", stud=0.025)
    nt = 80
    Ri, Ro, Rt = 0.66, 0.86, 0.905
    gear = []
    for k in range(nt):
        for (da, rr_) in ((0.0, Ro), (0.18, Ro), (0.32, Rt), (0.68, Rt), (0.82, Ro)):
            a = 2 * math.pi * (k + da) / nt
            gear.append((rr_ * math.cos(a), rr_ * math.sin(a)))
    zb_, zt_ = 4.38, 4.50
    ob = [mb.bm.verts.new((x, y, zb_)) for (x, y) in gear]
    ot = [mb.bm.verts.new((x, y, zt_)) for (x, y) in gear]
    ib = [mb.bm.verts.new((Ri * math.cos(2 * math.pi * k / 72), Ri * math.sin(2 * math.pi * k / 72), zb_)) for k in range(72)]
    it = [mb.bm.verts.new((v.co.x, v.co.y, zt_)) for v in ib]
    ng = len(gear)
    for k in range(ng):
        kk = (k + 1) % ng
        mb.face([ob[k], ob[kk], ot[kk], ot[k]], "metal_rust")
    for k in range(72):
        kk = (k + 1) % 72
        mb.face([ib[k], it[k], it[kk], ib[kk]], "metal_rust")
    # caras superior e inferior del anillo: n-gon con hueco = puente entre el contorno dentado y el círculo
    for (OO, II, up_) in ((ot, it, True), (ob, ib, False)):
        for k in range(ng):
            kk = (k + 1) % ng
            j = int(round(k * 72 / ng)) % 72
            jj = int(round(kk * 72 / ng)) % 72
            q = [OO[k], OO[kk], II[jj], II[j]] if j != jj else [OO[k], OO[kk], II[j]]
            mb.face(q if up_ else list(reversed(q)), "metal_rust")
    # --- parte giratoria
    R = _T(0, 0, 4.58) @ _R("Z", yaw)
    up = PMB()
    lathe_n(up, [(0.52, -0.08), (0.655, -0.08), (0.655, -0.005), (0.52, -0.005), (0.52, -0.08)], seg=72, mat="metal_paint",
            caps=False)
    px0, px1, py0, py1 = -1.6, 1.6, -2.7, 3.1
    up.box((px0, py0, 0.0), (px1, py1, 0.02), "metal_rust", bevel=0.004)
    path = [(px0 + 0.04, py0 + 0.04, -0.075), (px1 - 0.04, py0 + 0.04, -0.075), (px1 - 0.04, py1 - 0.04, -0.075),
            (px0 + 0.04, py1 - 0.04, -0.075)]
    psweep(up, rr_profile(0.08, 0.15, 0.008), path, "metal_paint", up=(0, 0, 1), closed=True)
    for x in (-0.55, 0.55):
        psweep(up, [(-0.07, -0.2), (0.07, -0.2), (0.07, -0.186), (0.006, -0.186), (0.006, -0.014), (0.07, -0.014), (0.07, 0.0),
                    (-0.07, 0.0), (-0.07, -0.014), (-0.006, -0.014), (-0.006, -0.186), (-0.07, -0.186)],
               [(x, py0 + 0.1, 0.0), (x, py1 - 0.1, 0.0)], "metal_paint", up=(0, 0, 1), miter=False)
    # escotilla de la escalera interior
    up.box((-0.3, -0.62, 0.02), (0.3, -0.02, 0.035), "metal_rust", bevel=0.004)
    for x in (-0.2, 0.2):
        lathe_n(up, [(0.0, -0.04), (0.012, -0.04), (0.012, 0.04), (0.0, 0.04)], seg=16, mat="metal_rust",
                M=_T(x, -0.01, 0.04) @ _R("Y", 90))
    up.tube(fillet([(-0.08, -0.55, 0.035), (-0.08, -0.55, 0.07), (0.08, -0.55, 0.07), (0.08, -0.55, 0.035)], 0.02, 4), 0.008, seg=14,
            mat="metal_rust")
    # piñón y motorreductor de giro
    ang = math.radians(200)
    gx, gy = 0.99 * math.cos(ang), 0.99 * math.sin(ang)
    teeth = []
    for k in range(14):
        for (da, rr_) in ((0.0, 0.07), (0.2, 0.07), (0.35, 0.088), (0.65, 0.088), (0.8, 0.07)):
            a = 2 * math.pi * (k + da) / 14
            teeth.append((rr_ * math.cos(a), rr_ * math.sin(a)))
    pin = PMB()
    psweep(pin, teeth, [(0, 0, -0.2), (0, 0, -0.08)], "metal_rust", up=(1, 0, 0), miter=False)
    up.join(pin, _T(gx, gy, 0.0))
    lathe_n(up, [(0.0, 0.02), (0.17, 0.02), (0.17, 0.2), (0.15, 0.22), (0.12, 0.22), (0.12, 0.62), (0.1, 0.65), (0.0, 0.66)], seg=40,
            mat="metal_paint", M=_T(gx, gy, 0.0))
    for k in range(12):
        a = 2 * math.pi * k / 12
        up.box((gx + 0.118 * math.cos(a) - 0.004, gy + 0.118 * math.sin(a) - 0.004, 0.26), (gx + 0.132 * math.cos(a) + 0.004,
               gy + 0.132 * math.sin(a) + 0.004, 0.58), "metal_paint", bevel=0.002)
    # --- casa de máquinas
    hx0, hx1, hy0, hy1, hz = -1.2, 1.2, 0.3, 2.3, 2.0
    for (x, y, sx, sy) in ((hx0, hy0, 1, 1), (hx1, hy0, -1, 1), (hx1, hy1, -1, -1), (hx0, hy1, 1, -1)):
        offs = round_poly([(0.0, 0.0), (sx * 0.06, 0.0), (sx * 0.06, sy * 0.006), (sx * 0.006, sy * 0.006), (sx * 0.006, sy * 0.06),
                           (0.0, sy * 0.06)], 0.002, 2)
        psweep(up, [(-ox, oy) for (ox, oy) in offs], [(x, y, 0.02), (x, y, hz)], "metal_paint", up=(0, 1, 0), miter=False)
    up_c = corr_pts(1.0, pitch=0.2, depth=0.025, outer=0.06, inner=0.06)

    def wall(u0, u1, z0, z1, side):
        """Paño de lámina corrugada vertical en una cara de la casa (u a lo largo de la cara, de izquierda a derecha vista
        de afuera)."""
        L_ = u1 - u0
        pts = corr_pts(L_, pitch=0.2, depth=0.025, outer=0.06, inner=0.06, phase=u0 % 0.2)
        if side == "front":       # y = hy0, afuera -Y
            M_ = Matrix(((1, 0, 0, hx0 + u0), (0, 1, 0, hy0 + 0.03), (0, 0, 1, 0), (0, 0, 0, 1)))
        elif side == "back":      # y = hy1, afuera +Y
            M_ = Matrix(((-1, 0, 0, hx1 - u0), (0, -1, 0, hy1 - 0.03), (0, 0, 1, 0), (0, 0, 0, 1)))
        elif side == "west":      # x = hx0, afuera -X
            M_ = Matrix(((0, 1, 0, hx0 + 0.03), (-1, 0, 0, hy1 - u0), (0, 0, 1, 0), (0, 0, 0, 1)))
        else:                     # x = hx1, afuera +X
            M_ = Matrix(((0, -1, 0, hx1 - 0.03), (1, 0, 0, hy0 + u0), (0, 0, 1, 0), (0, 0, 0, 1)))
        csheet(up, M_, pts, z0, z1, "metal_paint", nrows=4, t=0.0015,
               dent=dents(r, 1, 0.0, L_, z0, z1, amp=(0.0, 0.012), rad=(0.1, 0.3)))
    del up_c
    W_ = hx1 - hx0
    D_ = hy1 - hy0
    wall(0.02, W_ - 0.02, 0.04, hz - 0.02, "front")
    wall(0.02, W_ - 0.02, 0.04, hz - 0.02, "back")
    # oeste: puerta (u 0.7..1.5 desde y1)
    wall(0.02, 0.7, 0.04, hz - 0.02, "west")
    wall(1.5, D_ - 0.02, 0.04, hz - 0.02, "west")
    wall(0.7, 1.5, 1.95, hz - 0.02, "west")
    # este: persianas (u 0.6..1.4 desde y0, z 0.9..1.6)
    wall(0.02, 0.6, 0.04, hz - 0.02, "east")
    wall(1.4, D_ - 0.02, 0.04, hz - 0.02, "east")
    wall(0.6, 1.4, 0.04, 0.9, "east")
    wall(0.6, 1.4, 1.6, hz - 0.02, "east")
    for z in (0.04, hz - 0.03):
        psweep(up, rr_profile(0.05, 0.03, 0.004), [(hx0, hy0, z), (hx1, hy0, z), (hx1, hy1, z), (hx0, hy1, z)], "metal_paint",
               up=(0, 0, 1), closed=True)
    # persianas: marco y 6 aletas a 35°
    yl0, yl1 = hy0 + 0.6, hy0 + 1.4
    psweep(up, rr_profile(0.05, 0.04, 0.004), [(hx1, yl0, 0.9), (hx1, yl1, 0.9), (hx1, yl1, 1.6), (hx1, yl0, 1.6)], "metal_paint",
           up=(1, 0, 0), closed=True)
    for i in range(6):
        zz = 0.95 + i * 0.11
        if i == 3 and r.random() < 0.8:
            continue                                  # una aleta perdida
        Ml = _T(hx1, 0, zz) @ _R("Y", -35)
        up.box((-0.045, yl0 + 0.03, -0.005), (0.045, yl1 - 0.03, 0.005), "metal_paint", bevel=0.002, m=Ml)
    # puerta oeste entreabierta
    yd0, yd1 = hy1 - 1.5, hy1 - 0.7
    psweep(up, rr_profile(0.05, 0.05, 0.004), [(hx0, yd0, 0.03), (hx0, yd0, 1.95), (hx0, yd1, 1.95), (hx0, yd1, 0.03)], "metal_paint",
           up=(-1, 0, 0))
    leaf = PMB()
    leaf.box((-0.035, 0.0, 0.05), (0.0, 0.76, 1.9), "metal_paint", bevel=0.006)
    for z in (0.5, 1.4):
        leaf.box((-0.05, 0.05, z - 0.03), (-0.035, 0.71, z + 0.03), "metal_paint", bevel=0.004)
    for z in (0.25, 1.65):
        lathe_n(leaf, [(0.0, -0.06), (0.016, -0.06), (0.016, 0.06), (0.0, 0.06)], seg=16, mat="metal_rust", M=_T(-0.02, 0.0, z))
    leaf.tube(fillet([(-0.035, 0.66, 1.0), (-0.09, 0.66, 1.0), (-0.09, 0.56, 1.0), (-0.035, 0.56, 1.0)], 0.02, 4), 0.01, seg=14,
              mat="metal_rust")
    up.join(leaf, _T(hx0 - 0.03, yd0 + 0.02, 0.0) @ _R("Z", 28))
    # techo con caída y gotero
    _rr_loft(up, [(hz, W_ + 0.14, D_ + 0.14, 0.02), (hz + 0.03, W_ + 0.14, D_ + 0.14, 0.02), (hz + 0.045, W_ + 0.1, D_ + 0.1, 0.03)],
             "metal_paint", corner_n=3, M=_T(0, (hy0 + hy1) / 2, 0))
    # --- contrapeso
    up.box((-1.3, 2.4, 0.02), (1.3, 3.05, 1.2), "concrete", bevel=0.025, seg=3)
    for (x, y) in ((-1.3, 2.4), (1.3, 2.4), (1.3, 3.05), (-1.3, 3.05)):
        sx = 1 if x < 0 else -1
        sy = 1 if y < 2.7 else -1
        offs = [(0.0, 0.0), (sx * 0.07, 0.0), (sx * 0.07, sy * 0.007), (sx * 0.007, sy * 0.007), (sx * 0.007, sy * 0.07), (0.0, sy * 0.07)]
        offs = [(ox - sx * 0.007, oy - sy * 0.007) for (ox, oy) in offs]
        psweep(up, [(-ox, oy) for (ox, oy) in round_poly(offs, 0.002, 2)], [(x, y, 0.02), (x, y, 1.2)], "metal_paint", up=(0, 1, 0),
               miter=False)
    for x in (-0.8, 0.8):
        bev_plate(up, [(-0.08, 0.0), (0.08, 0.0), (0.05, 0.12), (-0.05, 0.12)], 0.025, "metal_paint",
                  M=_T(x, 2.725 + 0.0125, 1.2) @ _R("X", 90), ch=0.003)
    # --- cabina del operador
    cx0, cx1, cy0, cy1, cz1 = 0.58, 1.5, -2.6, -0.82, 2.12
    up.box((cx0, cy0, 0.02), (cx1, cy1, 0.95), "metal_paint", bevel=0.02, seg=3)
    for (x, y) in ((cx0 + 0.03, cy0 + 0.03), (cx1 - 0.03, cy0 + 0.03), (cx0 + 0.03, cy1 - 0.03), (cx1 - 0.03, cy1 - 0.03)):
        psweep(up, rr_profile(0.06, 0.06, 0.012), [(x, y, 0.95), (x, y, cz1)], "metal_paint", up=(0, 1, 0))
    _rr_loft(up, [(cz1, cx1 - cx0 + 0.02, cy1 - cy0 + 0.02, 0.04), (cz1 + 0.08, cx1 - cx0 + 0.02, cy1 - cy0 + 0.02, 0.04),
                  (cz1 + 0.12, cx1 - cx0 - 0.04, cy1 - cy0 - 0.04, 0.06)], "metal_paint", corner_n=4,
             M=_T((cx0 + cx1) / 2, (cy0 + cy1) / 2, 0))
    up.box((cx0 - 0.02, cy0 - 0.2, cz1 + 0.04), (cx1 + 0.02, cy0 + 0.02, cz1 + 0.06), "metal_paint", bevel=0.008)   # visera
    # vidrios con empaque: frente (y = cy0), costado este (x = cx1), costado oeste (x = cx0, parte delantera)
    panes = [("y", cy0, cx0 + 0.06, cx1 - 0.06), ("x", cx1, cy0 + 0.06, cy1 - 0.06), ("x", cx0, cy0 + 0.06, cy0 + 0.9)]
    for (ax, c, a0, a1) in panes:
        z0, z1 = 1.0, cz1 - 0.06
        if ax == "y":
            corners = [(a0, c, z0), (a1, c, z0), (a1, c, z1), (a0, c, z1)]
            nrm = (0, -1, 0)
        else:
            corners = [(c, a0, z0), (c, a1, z0), (c, a1, z1), (c, a0, z1)]
            nrm = (1, 0, 0) if c > 0.9 else (-1, 0, 0)
        psweep(up, rr_profile(0.03, 0.03, 0.008), corners, "rubber", up=nrm, closed=True)
        broken_ = r.random() < 0.45
        if not broken_:
            if ax == "y":
                up.box((a0 + 0.01, c - 0.004, z0 + 0.01), (a1 - 0.01, c + 0.004, z1 - 0.01), "glass", bevel=0.0)
            else:
                up.box((c - 0.004, a0 + 0.01, z0 + 0.01), (c + 0.004, a1 - 0.01, z1 - 0.01), "glass", bevel=0.0)
        else:                                          # vidrio estrellado: quedan esquirlas en el empaque
            for (fa, fz, ga, gz) in ((0.0, 0.0, 0.35, 0.0), (1.0, 0.0, 1.0, 0.4), (0.0, 1.0, 0.0, 0.55), (1.0, 1.0, 0.6, 1.0)):
                A_ = (a0 + 0.01 + (a1 - a0 - 0.02) * fa, z0 + 0.01 + (z1 - z0 - 0.02) * fz)
                B_ = (a0 + 0.01 + (a1 - a0 - 0.02) * ga, z0 + 0.01 + (z1 - z0 - 0.02) * gz)
                C_ = (a0 + 0.01 + (a1 - a0 - 0.02) * (fa if ga != fa else (0.5 + 0.2 * (fa - 0.5))),
                      z0 + 0.01 + (z1 - z0 - 0.02) * (gz if gz != fz else (0.5 + 0.3 * (fz - 0.5))))
                tri = [A_, B_, C_]
                area = (B_[0] - A_[0]) * (C_[1] - A_[1]) - (C_[0] - A_[0]) * (B_[1] - A_[1])
                if area < 0:
                    tri = [A_, C_, B_]
                if ax == "y":
                    Mx = Matrix(((1, 0, 0, 0), (0, 0, 1, c - 0.002), (0, 1, 0, 0), (0, 0, 0, 1)))
                else:
                    Mx = Matrix(((0, 0, 1, c - 0.002), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
                tmp = MB()
                tmp.plate(tri, 0.004, "glass")
                up.join(tmp, Mx)
    up.tube(fillet([(cx0 + 0.3, cy0 - 0.02, 1.85), (cx0 + 0.42, cy0 - 0.02, 1.35)], 0.01, 2), 0.004, seg=12, mat="rubber")
    lathe_n(up, [(0.0, 0.0), (0.015, 0.0), (0.015, 0.03), (0.0, 0.035)], seg=16, mat="metal_paint",
            M=_T(cx0 + 0.42, cy0 - 0.005, 1.35) @ _R("X", 90))
    # puerta trasera de la cabina (cara y = cy1) con ventanilla
    up.box((cx0 + 0.12, cy1, 0.04), (cx0 + 0.8, cy1 + 0.035, 1.95), "metal_paint", bevel=0.006)
    psweep(up, rr_profile(0.025, 0.025, 0.006), [(cx0 + 0.22, cy1 + 0.04, 1.2), (cx0 + 0.7, cy1 + 0.04, 1.2),
                                                 (cx0 + 0.7, cy1 + 0.04, 1.8), (cx0 + 0.22, cy1 + 0.04, 1.8)], "rubber", up=(0, 1, 0),
           closed=True)
    up.box((cx0 + 0.23, cy1 + 0.03, 1.21), (cx0 + 0.69, cy1 + 0.038, 1.79), "glass", bevel=0.0)
    up.tube(fillet([(cx0 + 0.72, cy1 + 0.035, 1.0), (cx0 + 0.72, cy1 + 0.09, 1.0), (cx0 + 0.6, cy1 + 0.09, 1.0)], 0.02, 4), 0.01,
            seg=14, mat="metal_rust")
    # asiento y consola
    up.box((cx0 + 0.25, cy0 + 0.7, 0.45), (cx0 + 0.75, cy0 + 1.2, 0.55), "vinyl", bevel=0.03, seg=3)
    up.box((cx0 + 0.27, cy0 + 1.12, 0.55), (cx0 + 0.73, cy0 + 1.2, 1.15), "vinyl", bevel=0.03, seg=3)
    lathe_n(up, [(0.0, 0.0), (0.05, 0.0), (0.05, 0.45), (0.0, 0.45)], seg=20, mat="metal_paint", M=_T(cx0 + 0.5, cy0 + 0.95, 0.0))
    up.box((cx0 + 0.15, cy0 + 0.25, 0.6), (cx1 - 0.08, cy0 + 0.5, 0.95), "metal_paint", bevel=0.02, seg=3)
    for x in (cx0 + 0.3, cx1 - 0.3):
        lathe_n(up, [(0.0, 0.0), (0.012, 0.0), (0.01, 0.15), (0.02, 0.17), (0.022, 0.21), (0.0, 0.23)], seg=16, mat="plastic",
                M=_T(x, cy0 + 0.38, 0.95))
    # --- caballete en A
    apex = 4.6
    feet = []
    for sg in (-1, 1):
        fa = Vector((sg * 0.5, -0.45, 0.02))
        fb = Vector((sg * 0.9, 1.0, hz + 0.045))
        top = Vector((sg * 0.22, -0.2, apex))
        for f in (fa, fb):
            up.tube([f + (top - f).normalized() * 0.1, top], 0.07, seg=24, mat="metal_paint")
            feet.append((f, top))
    for (f, top) in feet:
        dv = (top - f).normalized()
        sx = 1 if f.x > 0 else -1
        for dx in (-0.06, 0.06):
            bev_plate(up, [(-0.09, 0.0), (0.09, 0.0), (0.06, 0.16), (-0.06, 0.16)], 0.02, "metal_paint",
                      M=_T(f.x + dx, f.y, f.z) @ _R("Z", 90) @ _T(0, 0.01, 0) @ _R("X", 90), ch=0.003)
        lathe_n(up, [(0.0, -0.1), (0.03, -0.1), (0.03, 0.1), (0.0, 0.1)], seg=20, mat="metal_rust",
                M=_T(f.x, f.y, f.z + 0.1) @ _R("Y", 90))
        lathe_n(up, [(0.0, 0.0), (0.075, 0.0), (0.075, 0.03), (0.0, 0.03)], seg=24, mat="metal_paint",
                M=frame_on(f + dv * 0.1, f + dv)[0] @ _R("Y", 90))
        del sx
    up.tube([(-0.32, -0.2, apex), (0.32, -0.2, apex)], 0.07, seg=24, mat="metal_paint")
    for sx in (-1, 1):
        lathe_n(up, [(0.0, 0.0), (0.085, 0.0), (0.085, 0.015), (0.0, 0.015)], seg=24, mat="metal_paint",
                M=_T(sx * 0.32, -0.2, apex) @ _R("Y", 90 * sx))
    for sx in (-1, 1):
        bev_plate(up, [(-0.14, -0.05), (0.14, -0.05), (0.1, 0.3), (-0.1, 0.3)], 0.02, "metal_paint",
                  M=_T(sx * 0.07, -0.2, apex) @ _R("Z", 90) @ _T(0, 0.01, 0) @ _R("X", 90), ch=0.003)
    sheave(up, _T(0, -0.2, apex + 0.17) @ _R("Z", 90), R=0.2, w=0.07)
    # --- talón de la pluma
    base = Vector((0.0, -1.3, 0.35))
    for sx in (-1, 1):
        for dx in (-0.03, 0.03):
            bev_plate(up, [(-0.16, 0.0), (0.16, 0.0), (0.09, 0.4), (-0.09, 0.4)], 0.02, "metal_paint",
                      M=_T(sx * 0.33 + dx, -1.3, 0.02) @ _R("Z", 90) @ _T(0, 0.01, 0) @ _R("X", 90), ch=0.003)
    lathe_n(up, [(0.0, -0.45), (0.045, -0.45), (0.045, 0.45), (0.0, 0.45)], seg=24, mat="metal_rust", M=_T(0, -1.3, 0.35) @ _R("Y", 90))
    for sx in (-1, 1):
        hexnut(up, _T(sx * 0.45, -1.3, 0.35) @ _R("Y", 90 * sx), af=0.075, mat="metal_rust", stud=0.03)
    # --- pluma de celosía
    el = math.radians(luff)
    d = Vector((0.0, -math.cos(el), math.sin(el)))
    nz = Vector((0, math.sin(el), math.cos(el)))
    hw = 0.38
    n = 16

    def chord_pt(ix, iz, t):
        taper = 1.0 - 0.55 * max(0.0, t - 0.75) / 0.25 - 0.21 * max(0.0, 0.08 - t) / 0.08
        return base + d * (boom_len * t) + Vector((ix * hw * taper, 0, 0)) + nz * (iz * hw * taper)
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    for (ix, iz) in corners:
        pts = [chord_pt(ix, iz, i / n) for i in range(n + 1)]
        for i in range(n):
            angle_sweep(up, pts[i], pts[i + 1], leg=0.09, t=0.009, mat="metal_paint", up=tuple(nz * (-iz)), flip=ix * iz < 0)
    for f in range(4):
        a, b = corners[f], corners[(f + 1) % 4]
        for i in range(n):
            t0, t1 = i / n, (i + 1) / n
            pa = chord_pt(*a, t0) if i % 2 == 0 else chord_pt(*b, t0)
            pb = chord_pt(*b, t1) if i % 2 == 0 else chord_pt(*a, t1)
            ctr = (chord_pt(*a, t0) + chord_pt(*b, t0) + chord_pt(*a, t1) + chord_pt(*b, t1)) / 4
            pa = pa + (ctr - pa).normalized() * 0.05
            pb = pb + (ctr - pb).normalized() * 0.05
            up.tube([pa, pb], 0.021, seg=14, mat="metal_paint")
            # cartelas de nudo en las uniones con el cordón
            fn_ = d.cross(chord_pt(*b, t0) - chord_pt(*a, t0)).normalized()
            for (pp, tt) in ((pa, t0), (pb, t1)):
                Mg_, _ = frame_on(pp, ctr, up=tuple(fn_))
                up.box((-0.02, -0.004, -0.04), (0.06, 0.004, 0.04), "metal_paint", bevel=0.002, m=Mg_)
    # cabeza de la pluma
    tip = base + d * boom_len
    Mbm, _ = frame_on(base, tip, up=tuple(nz))
    head = [(-0.9, -0.2), (-0.15, -0.34), (0.22, -0.3), (0.38, -0.12), (0.38, 0.12), (0.22, 0.32), (-0.15, 0.3), (-0.9, 0.2)]
    for sg in (-1, 1):
        bev_plate(up, round_poly(head, 0.04, 3), 0.02, "metal_paint",
                  M=Mbm @ _T(boom_len, 0.17 if sg > 0 else -0.19, 0) @ _R("X", -90), ch=0.004)
    for (dx, dz) in ((-0.7, 0.0), (0.22, 0.0)):
        p0 = Mbm @ Vector((boom_len + dx, -0.21, dz))
        p1 = Mbm @ Vector((boom_len + dx, 0.21, dz))
        up.tube([p0, p1], 0.035, seg=24, mat="metal_rust")
        for q in (p0, p1):
            hexnut(up, frame_on(q, q + (q - (p0 + p1) / 2).normalized())[0] @ _R("Y", 90), af=0.055, mat="metal_rust", stud=0.0)
    Mt = _T(tip.x, tip.y, tip.z)
    sheave(up, Mt @ _R("Z", 90), R=0.3, w=0.1)
    tipb = Mbm @ Vector((boom_len - 0.7, 0.0, 0.0))
    sheave(up, _T(tipb.x, tipb.y, tipb.z) @ _R("Z", 90), R=0.16, w=0.07)
    # aparejo de la pluma (4 ramales) y cable de izaje
    for dx in (-0.045, -0.015, 0.015, 0.045):
        rope(up, [(dx, -0.2, apex + 0.17), (tipb.x + dx, tipb.y, tipb.z + 0.16)], r=0.009)
    hook_top = Vector((tip.x, tip.y - 0.3, hook_z + 1.2 - 4.58))
    rope(up, fillet([(0.0, 0.8, hz + 0.045), (0.0, -0.05, apex - 0.02), (tip.x, tip.y + 0.05, tip.z + 0.3)], 0.15, 4), r=0.011)
    for dx in (-0.045, 0.045):
        rope(up, [(tip.x + dx, tip.y - 0.3, tip.z), (hook_top.x + dx, hook_top.y, hook_top.z + 0.42)], r=0.011)
    # motón y gancho
    Mb = _T(hook_top.x, hook_top.y, hook_top.z)
    for sg in (-1, 1):
        bev_plate(up, round_poly([(-0.17, 0.0), (0.17, 0.0), (0.17, 0.3), (0.12, 0.44), (-0.12, 0.44), (-0.17, 0.3)], 0.05, 4), 0.02,
                  "metal_paint", M=Mb @ _T(0, sg * 0.06 + (0.01 if sg < 0 else -0.01), 0) @ _R("X", 90) @ _T(0, 0, -0.01), ch=0.003)
    sheave(up, Mb @ _T(0, 0, 0.25), R=0.13, w=0.08)
    for (x, z) in ((-0.12, 0.06), (0.12, 0.06), (0.0, 0.4)):
        up.tube([Mb @ Vector((x, -0.085, z)), Mb @ Vector((x, 0.085, z))], 0.016, seg=16, mat="metal_rust")
    lathe_n(up, [(0.0, -0.06), (0.06, -0.06), (0.065, -0.04), (0.065, 0.0), (0.0, 0.0)], seg=24, mat="metal_rust", M=Mb)
    _hook(up, Mb @ _T(0, 0, -0.06), scale=1.2)
    # barandal de la plataforma
    handrail(up, (px0 + 0.05, py0 + 0.05, 0.02), (px0 + 0.05, 2.35, 0.02), h=1.05, post_step=1.3, r=r)
    handrail(up, (px1 - 0.05, -0.7, 0.02), (px1 - 0.05, 2.35, 0.02), h=1.05, post_step=1.3, r=r)
    handrail(up, (px0 + 0.05, py0 + 0.05, 0.02), (-0.55, py0 + 0.05, 0.02), h=1.05, post_step=1.3, r=r)
    mb.join(up, R)
    mb.meta = dict(tip=R @ tip, top=R @ Vector((0, 0, tip.z)))
    return mb
