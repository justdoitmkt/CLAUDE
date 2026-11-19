"""cladding.py — GRUPO G3 · REVESTIMIENTOS del kit modular BLACKISLE (ladrillo a soga, tablón y junquillo, tabla traslapada).

Todas las funciones públicas devuelven un `MB` con el MISMO sistema que `wall_with_openings`:
  u = 0..length en X, v = 0..height en Z, cara EXTERIOR en y = 0 (la fachada mira a -Y), el muro crece hacia +Y.
  openings = [(u0, u1, v0, v1)] vanos libres (puertas: v0 = 0). Las piezas de G1 (ventanas/puertas) se colocan en ese vano.

  brick_wall      ladrillo 0,24 x 0,06 x 0,12 a soga (junta 1 cm rehundida 8 mm sobre un núcleo de mortero), cara vista en y = 0;
                  núcleo de mortero y = 0,008..thickness (0,14 por defecto; cara interior 'plaster'); dinteles de piedra
                  ('concrete') de 3 hiladas y alféizares inclinados; ladrillos faltantes (agujero pasante), descascarados y caídos
                  al pie del muro (y < 0, z = 0); parches de revoque viejo (y -0,016..-0,004). ~20 triángulos por ladrillo.
  board_and_batten tablones verticales 0,22 (rendija 0,04) con cara exterior en y = 0 (y 0..0,022), junquillos 0,05 x 0,02 encima
                  (y -0,021..-0,001); bastidor de postes y largueros 0,05 x 0,10 detrás (y 0,024..0,124).
  clapboard       tablas traslapadas de perfil cuña (0,016 -> 0,006, 0,18 de ancho, 0,15 de exposición), testa vista en y ~ 0;
                  pies derechos cada 0,6 en y 0,026..0,126; esquineros y tapajuntas de vano 6 mm por delante de las tablas.
Todo son sólidos cerrados (0 aristas no-manifold); no hay láminas en este módulo.

Triángulos medidos (muro 6,5 x 2,8 con 2 ventanas y 1 puerta): brick_wall ~18,5 k (20 tris por ladrillo + núcleo, dinteles,
caídos y revoque) · board_and_batten ~12 k · clapboard ~6,6 k (incluyen bastidor, tapajuntas y clavos).
"""
import math

import bpy  # noqa: F401
import bmesh  # noqa: F401
from mathutils import Matrix, Vector

from kit.common import MB, rng
from kit.roofing import _N1, _R, _T, _about

PI = math.pi
BRICK_L, BRICK_H, BRICK_D, JOINT = 0.24, 0.06, 0.12, 0.01
COURSE, PITCH = BRICK_H + JOINT, BRICK_L + JOINT
REC = 0.008                                  # rehundido de la junta = cara del núcleo de mortero


# =====================================================================================================================
# 0) MADERA ASERRADA INTEMPERIZADA — base de todas las piezas de madera de las cabañas (pasada AAA, 2026-11-19)
#    Cantos redondeados de radio real (n = 4 segmentos por esquina: pasos de 22,5°, sombreado continuo con el corte de 30° de
#    MB.finish), vetas abiertas y fendas como muescas en V que nacen y mueren a lo largo de la pieza, arqueo, flecha, alabeo,
#    puntas rotas con astillas, clavos de cabeza abombada (sombreado suave). Medidas de escuadría de madera aserrada en bruto
#    (full-sawn): un "2x4" de antes de 1930 mide 2 x 4 pulgadas reales (51 x 102 mm).
# =====================================================================================================================
def _wsec(w, h, rc, n=4, grooves=(), y0=0.0):
    """Sección de esquinas redondeadas (antihoraria), x en ±w/2, y en y0..y0+h. grooves = [(cara, t, media_anchura, prof)]:
    cara 0 = derecha (+x), 1 = arriba (+y), 2 = izquierda, 3 = abajo; t = 0..1 a lo largo del tramo plano. Muesca en V hacia dentro."""
    rc = max(0.0004, min(rc, 0.45 * w, 0.45 * h))
    C = [((w / 2 - rc, y0 + rc), -PI / 2), ((w / 2 - rc, y0 + h - rc), 0.0), ((-w / 2 + rc, y0 + h - rc), PI / 2),
         ((-w / 2 + rc, y0 + rc), PI)]
    pts = []
    for i, ((cx, cy), a0) in enumerate(C):
        for k in range(n + 1):
            a = a0 + PI / 2 * k / n
            pts.append((cx + rc * math.cos(a), cy + rc * math.sin(a)))
        gs = sorted((g for g in grooves if g[0] == i), key=lambda g: g[1])
        if not gs:
            continue
        ax, ay = cx + rc * math.cos(a0 + PI / 2), cy + rc * math.sin(a0 + PI / 2)
        (cx2, cy2), a2 = C[(i + 1) % 4]
        bx, by = cx2 + rc * math.cos(a2), cy2 + rc * math.sin(a2)
        L = math.hypot(bx - ax, by - ay)
        if L < 1e-4:
            continue
        dx, dy = (bx - ax) / L, (by - ay) / L
        nx, ny = -dy, dx                                  # hacia dentro (polígono antihorario)
        last = 0.0
        for (_, t, hw, d) in gs:
            s = t * L
            if s - hw <= last + 0.0008 or s + hw >= L - 0.0008:
                continue
            for ds, dd in ((-hw, 0.0), (0.0, d), (hw, 0.0)):
                pts.append((ax + dx * (s + ds) + nx * dd, ay + dy * (s + ds) + ny * dd))
            last = s + hw
    return pts


def _frame(p0, p1, up):
    p0, p1 = Vector(p0), Vector(p1)
    T = p1 - p0
    L = T.length
    T = T / max(L, 1e-9)
    U = Vector(up)
    if abs(T.dot(U.normalized())) > 0.985:
        U = Vector((0, 1, 0)) if abs(T.y) < 0.9 else Vector((1, 0, 0))
    S = U.cross(T).normalized()
    U = T.cross(S).normalized()
    return p0, T, S, U, L


def _cap_loft(mb, rings, mat, caps=True):
    vs = [[mb.bm.verts.new(p) for p in rg] for rg in rings]
    k = len(rings[0])
    for i in range(len(vs) - 1):
        a, b = vs[i], vs[i + 1]
        for j in range(k):
            jj = (j + 1) % k
            mb.face([a[j], a[jj], b[jj], b[j]], mat)
    if caps:
        mb.face(list(reversed(vs[0])), mat)
        mb.face(vs[-1], mat)
    return vs


def lumber(mb, p0, p1, w, h, mat="wood_grey", up=(0, 0, 1), r=None, rc=0.004, n=4, step=0.5, center=True, grain=1.0,
           check=0.0, bow=0.0, sag=0.0, twist=0.0, cup=0.0, jag0=0.0, jag1=0.0, splinters=True, cut0=None, cut1=None,
           y_off=0.0):
    """Pieza de madera aserrada de p0 a p1: sección w (eje lateral S = up x T) por h (eje `up`), centrada en el eje (center) o con
    la cara inferior en el eje + y_off. Cantos de radio rc; grain 0..1 = vetas abiertas (0,5–1,6 mm) en las caras anchas que
    aparecen y se desvanecen; check 0..1 = fenda (grieta de secado) en una cara ancha, hasta ~25 % del grueso; bow/sag = flecha
    lateral / vertical (m) en el centro; twist = alabeo (rad) de punta a punta; cup = abarquillado (m) de la cara superior;
    jag0/jag1 = punta rota (m) con astillas; cut0/cut1 = (punto, normal) corte a inglete o a bisel del extremo."""
    if r is None:
        r = rng(int(abs(p0[0] * 7919 + p0[1] * 104729 + p0[2] * 1299709 + p1[0] * 31 + p1[2] * 17) * 1000) % 2147483647)
    P0, T, S, U, L = _frame(p0, p1, up)
    if L < 0.004:
        return None
    yb = -h / 2 if center else y_off
    # vetas y fenda: (cara, t, media anchura, prof, s0, s1)
    gro = []
    wide = [1, 3] if w >= h * 0.8 else [0, 2]
    if h >= w * 0.8 and w >= h * 0.8:
        wide = [0, 1, 2, 3]
    for f in wide:
        flen = (w if f in (1, 3) else h) - 2 * rc
        if flen < 0.03 or grain <= 0:
            continue
        for _ in range(int(r.integers(0, 1 + int(round(3 * grain * min(1.0, flen / 0.12)))))):
            s0 = r.uniform(-0.3, 0.6) * L
            gro.append((f, r.uniform(0.12, 0.88), r.uniform(0.0012, 0.003), r.uniform(0.0005, 0.0016) * grain, s0,
                        s0 + r.uniform(0.35, 1.0) * L))
    if check > 0 and L > 0.3:
        f = wide[int(r.integers(0, len(wide)))]
        s0 = r.uniform(0.0, 0.45) * L
        dep = min(w, h) * r.uniform(0.12, 0.25) * check
        gro.append((f, r.uniform(0.3, 0.7), r.uniform(0.0012, 0.0028) * (0.6 + check), dep, s0, min(L * 1.05, s0 + r.uniform(0.35, 0.8) * L)))
    need = bool(gro or bow or sag or twist)
    ns = max(2 if not need else 4, int(math.ceil(L / step)) + 1)
    rings = []
    for i in range(ns):
        f = i / (ns - 1)
        s = L * f
        g_here = []
        for (fc, t, hw, d, s0, s1) in gro:
            u = (s - s0) / max(s1 - s0, 1e-6)
            g_here.append((fc, t, hw, d * (math.sin(PI * min(max(u, 0.0), 1.0)) ** 0.6 if 0.0 < u < 1.0 else 0.0)))
        prof = _wsec(w, h, rc, n, g_here, yb)
        sn = math.sin(PI * f)
        tw = twist * (f - 0.5)
        ct, st = math.cos(tw), math.sin(tw)
        base = P0 + T * s + S * (bow * sn) + U * (sag * sn)
        rg = []
        for (x, y) in prof:
            if cup:
                y += cup * (1.0 - (2.0 * x / w) ** 2)
            yy = y - (yb + h / 2)
            xr, yr = x * ct - yy * st, x * st + yy * ct
            rg.append(base + S * xr + U * (yr + yb + h / 2))
        if i == 0 and cut0 is not None:
            q, nn = Vector(cut0[0]), Vector(cut0[1])
            rg = [p + T * ((q - p).dot(nn) / (T.dot(nn) if abs(T.dot(nn)) > 1e-6 else 1e-6)) for p in rg]
        if i == ns - 1 and cut1 is not None:
            q, nn = Vector(cut1[0]), Vector(cut1[1])
            rg = [p + T * ((q - p).dot(nn) / (T.dot(nn) if abs(T.dot(nn)) > 1e-6 else 1e-6)) for p in rg]
        j = jag0 if i == 0 else (jag1 if i == ns - 1 else 0.0)
        if j:
            sg = 1.0 if i == 0 else -1.0
            ph = r.uniform(0, 2 * PI)
            rg = [p + T * (sg * j * (0.5 + 0.5 * math.sin(ph + 5.0 * k / len(rg) * 2 * PI) * r.uniform(0.4, 1.0)))
                  for k, p in enumerate(rg)]
        rings.append(rg)
    _cap_loft(mb, rings, mat)
    for (jj, end) in ((jag0, 0), (jag1, 1)):
        if jj and splinters:
            sg = 1.0 if end == 0 else -1.0
            e0 = P0 + T * (0.0 if end == 0 else L)
            for _ in range(int(r.integers(1, 4))):
                x, y = r.uniform(-0.38, 0.38) * w, r.uniform(-0.35, 0.35) * h + yb + h / 2
                ln = r.uniform(0.6, 1.8) * jj + 0.015
                tw_ = r.uniform(0.002, 0.006)
                th_ = min(r.uniform(0.0015, 0.004), 0.3 * h)
                b = e0 + S * x + U * y + T * (sg * jj * 0.5)
                d = -T * sg
                tip = b + d * ln + S * r.uniform(-0.2, 0.2) * ln * 0.2 + U * r.uniform(-0.1, 0.1) * ln * 0.2
                bb = b - d * 0.01
                ring0 = [bb + S * (-tw_) + U * (-th_), bb + S * tw_ + U * (-th_), bb + S * tw_ * 0.6 + U * th_, bb + S * (-tw_ * 0.6) + U * th_]
                vs = [mb.bm.verts.new(p) for p in ring0]
                vt = mb.bm.verts.new(tip)
                for k in range(4):
                    mb.face([vs[k], vs[(k + 1) % 4], vt], mat)
                mb.face(list(reversed(vs)), mat)
    return rings


def lbox(mb, mn, mx, mat="wood_grey", r=None, axis=None, **kw):
    """lumber() con la huella de una caja alineada a ejes (mn, mx): la pieza corre a lo largo de `axis` (0/1/2; por omisión el
    lado mayor). Sustituye a mb.box() en tablas, vigas y postes."""
    d = [mx[i] - mn[i] for i in range(3)]
    ax = max(range(3), key=lambda i: d[i]) if axis is None else axis
    c = [(mn[i] + mx[i]) / 2 for i in range(3)]
    p0, p1 = list(c), list(c)
    p0[ax], p1[ax] = mn[ax], mx[ax]
    if ax == 0:
        return lumber(mb, p0, p1, d[1], d[2], mat, up=(0, 0, 1), r=r, **kw)
    if ax == 1:
        return lumber(mb, p0, p1, d[0], d[2], mat, up=(0, 0, 1), r=r, **kw)
    return lumber(mb, p0, p1, d[0], d[1], mat, up=(0, 1, 0), r=r, **kw)


def lbox_m(mb, mn, mx, mat, m, r=None, axis=None, **kw):
    """lbox() en el marco de la matriz m (piezas giradas: vierteaguas, repisas, tablas caídas)."""
    tmp = MB()
    lbox(tmp, mn, mx, mat, r=r, axis=axis, **kw)
    mb.join(tmp, m)
    tmp.bm.free()


def _lathe(mb, prof, seg, mat, M, caps=True):
    """Sólido de revolución sobre Z local (perfil [(r, z)]; r = 0 -> polo). caps=False: sin tapas (anillos, collarines)."""
    rings = []
    for (rr, z) in prof:
        if rr < 1e-7:
            rings.append([mb.bm.verts.new(M @ Vector((0.0, 0.0, z)))])
            continue
        rings.append([mb.bm.verts.new(M @ Vector((rr * math.cos(2 * PI * k / seg), rr * math.sin(2 * PI * k / seg), z)))
                      for k in range(seg)])
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        for k in range(seg):
            kk = (k + 1) % seg
            if len(A) == 1:
                mb.face([A[0], B[kk], B[k]], mat)
            elif len(B) == 1:
                mb.face([A[k], A[kk], B[0]], mat)
            else:
                mb.face([A[k], A[kk], B[kk], B[k]], mat)
    if caps and len(rings[0]) > 1:
        mb.face(list(reversed(rings[0])), mat)
    if caps and len(rings[-1]) > 1:
        mb.face(rings[-1], mat)
    return rings


def axis_m(p, axis):
    """Matriz con Z local = axis y origen en p."""
    a = Vector(axis).normalized()
    q = a.to_track_quat("Z", "Y")
    return Matrix.Translation(Vector(p)) @ q.to_matrix().to_4x4()


def nail(mb, p, axis, r=0.0045, h=0.0024, mat="metal_rust", seg=8, pop=0.0, bend=0.0):
    """Clavo de alambre: cabeza abombada (sombreado suave, seg 8 en Ø <= 10 mm) que sobresale h y entra 4 mm en la madera.
    pop > 0: clavo botado (la caña asoma pop m); bend: caña doblada (rad)."""
    a = Vector(axis).normalized()
    with mb.soft():
        if pop > 0:
            M = axis_m(Vector(p), a)
            sh = 0.0016 if r < 0.004 else 0.0021
            pts = [Vector((0, 0, -0.004)), Vector((0, 0, pop * 0.5)), Vector((math.sin(bend) * pop * 0.5, 0, pop * (0.5 + 0.5 * math.cos(bend))))]
            mb.tube([M @ q for q in pts], sh, seg=seg, mat=mat)
            hp = M @ pts[-1]
            ax2 = (M.to_3x3() @ Vector((math.sin(bend), 0, math.cos(bend)))).normalized()
            _lathe(mb, [(r, 0.0), (r, h * 0.45), (r * 0.55, h), (0.0, h * 1.05)], seg, mat, axis_m(hp, ax2))
        else:
            _lathe(mb, [(r, -0.004), (r, h * 0.45), (r * 0.55, h), (0.0, h * 1.05)], seg, mat, axis_m(Vector(p), a))


def bolt_head(mb, p, axis, d=0.012, mat="metal_rust", kind="carriage", seg=12):
    """Cabeza de tornillo sobre una cara (eje = normal de la cara): 'carriage' cabeza de hongo; 'nut' arandela + tuerca
    hexagonal con punta de espárrago. d = diámetro nominal."""
    M = axis_m(Vector(p), axis)
    with mb.soft():
        if kind == "carriage":
            _lathe(mb, [(d * 1.15, -0.003), (d * 1.15, d * 0.12), (d * 0.95, d * 0.38), (d * 0.55, d * 0.58), (0.0, d * 0.64)], seg, mat, M)
            return
        _lathe(mb, [(d * 0.55, -0.002), (d * 1.25, -0.002), (d * 1.25, d * 0.16), (d * 0.55, d * 0.16)], seg, mat, M)
    z = d * 0.16
    hx = []
    for k in range(6):
        a = PI / 6 + PI / 3 * k
        hx.append((d * 0.85 * math.cos(a), d * 0.85 * math.sin(a)))
    # tuerca hexagonal con los vértices achaflanados (aristas duras reales)
    bot = [mb.bm.verts.new(M @ Vector((x, y, z))) for x, y in hx]
    top = [mb.bm.verts.new(M @ Vector((x * 0.94, y * 0.94, z + d * 0.8))) for x, y in hx]
    mid = [mb.bm.verts.new(M @ Vector((x, y, z + d * 0.68))) for x, y in hx]
    for k in range(6):
        kk = (k + 1) % 6
        mb.face([bot[k], bot[kk], mid[kk], mid[k]], mat)
        mb.face([mid[k], mid[kk], top[kk], top[k]], mat)
    mb.face(list(reversed(bot)), mat)
    mb.face(top, mat)
    with mb.soft():
        _lathe(mb, [(d * 0.5, z + d * 0.75), (d * 0.5, z + d * 1.15), (d * 0.38, z + d * 1.28), (0.0, z + d * 1.3)], seg, mat, M)


def knot(mb, p, nrm, along, rx, ry, mat="wood_dark", proud=0.0012):
    """Nudo de la madera: lente ovalada (rx a lo largo de la veta) que sobresale `proud` de la cara y se hunde 1,5 mm en ella."""
    n = Vector(nrm).normalized()
    a = Vector(along).normalized()
    b = n.cross(a).normalized()
    c = Vector(p)
    seg = 14
    with mb.soft():
        rings = []
        for (k, dep) in ((1.0, -0.0015), (0.8, proud * 0.75), (0.45, proud)):
            rings.append([mb.bm.verts.new(c + a * (rx * k * math.cos(2 * PI * i / seg)) + b * (ry * k * math.sin(2 * PI * i / seg)) + n * dep)
                          for i in range(seg)])
        top = mb.bm.verts.new(c + n * (proud * 1.05))
        for i in range(2):
            for j in range(seg):
                jj = (j + 1) % seg
                mb.face([rings[i][j], rings[i][jj], rings[i + 1][jj], rings[i + 1][j]], mat)
        for j in range(seg):
            mb.face([rings[2][j], rings[2][(j + 1) % seg], top], mat)
        mb.face(list(reversed(rings[0])), mat)


# =====================================================================================================================
# muro macizo con huecos rectangulares (núcleo) — malla soldada y cerrada, sin booleanos
# =====================================================================================================================
def _merge_iv(ivs):
    out = []
    for a, b in sorted(ivs):
        if out and a <= out[-1][1] + 1e-9:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _strip_wall(mb, L, H, y0, y1, holes, mat_f="mortar", mat_b="plaster", mat_r="mortar", u_min=0.0):
    """Muro u in [u_min, L], v in [0, H], y in [y0, y1] con huecos rectangulares (u0, u1, v0, v1) que lo atraviesan.
    Filas entre las líneas v de los huecos; cada línea comparte los vértices de las dos filas que separa -> cerrado y manifold."""
    hs = []
    for (a, b, c, d) in holes:
        a, b, c, d = max(a, u_min), min(b, L), max(c, 0.0), min(d, H)
        if b - a > 1e-3 and d - c > 1e-3:
            hs.append((a, b, c, d))

    def snapper(vals, fixed, tol=1.5e-3):
        reps = sorted(fixed)
        for x in sorted(vals):
            if all(abs(x - q) > tol for q in reps):
                reps.append(x)
                reps.sort()
        return lambda x: min(reps, key=lambda q: abs(q - x))
    su = snapper([h[0] for h in hs] + [h[1] for h in hs], [u_min, L])
    sv = snapper([h[2] for h in hs] + [h[3] for h in hs], [0.0, H])
    hs = [(su(a), su(b), sv(c), sv(d)) for (a, b, c, d) in hs]
    hs = [h for h in hs if h[1] - h[0] > 1e-6 and h[3] - h[2] > 1e-6]
    vl = sorted({0.0, H} | {h[2] for h in hs} | {h[3] for h in hs})
    R = len(vl) - 1
    rows = []
    for j in range(R):
        a, b = vl[j], vl[j + 1]
        rows.append(_merge_iv([(h[0], h[1]) for h in hs if h[2] <= a + 1e-7 and h[3] >= b - 1e-7]))

    def solid(j):
        out, cur = [], u_min
        for a, b in rows[j]:
            if a > cur + 1e-7:
                out.append((cur, a))
            cur = max(cur, b)
        if L > cur + 1e-7:
            out.append((cur, L))
        return out

    SO = [solid(j) for j in range(R)]
    Bk = [sorted({x for seg in SO[j] for x in seg}) for j in range(R)]
    E = []
    for i in range(R + 1):
        s = set()
        if i > 0:
            s |= set(Bk[i - 1])
        if i < R:
            s |= set(Bk[i])
        E.append(sorted(s))
    VF, VK = {}, {}

    def F(i, u):
        k = (i, round(u, 7))
        if k not in VF:
            VF[k] = mb.bm.verts.new((u, y0, vl[i]))
        return VF[k]

    def K(i, u):
        k = (i, round(u, 7))
        if k not in VK:
            VK[k] = mb.bm.verts.new((u, y1, vl[i]))
        return VK[k]

    def rng_e(i, a, b):
        return [u for u in E[i] if a - 1e-7 <= u <= b + 1e-7]

    def inter(ivs, a, b):
        return [(max(x, a), min(y, b)) for x, y in ivs if min(y, b) - max(x, a) > 1e-7]

    for j in range(R):
        for (a, b) in SO[j]:
            bot, top = rng_e(j, a, b), rng_e(j + 1, a, b)
            mb.face([F(j, u) for u in bot] + [F(j + 1, u) for u in reversed(top)], mat_f)
            mb.face([K(j, u) for u in reversed(bot)] + [K(j + 1, u) for u in top], mat_b)
            for u, sg in ((a, -1), (b, 1)):
                q = [F(j, u), F(j + 1, u), K(j + 1, u), K(j, u)]
                mb.face(q if sg > 0 else list(reversed(q)), mat_r)
            # techo / piso donde la fila vecina es hueco (o borde del muro)
            up = [(a, b)] if j == R - 1 else inter(rows[j + 1], a, b)
            for (c, d) in up:
                us = rng_e(j + 1, c, d)
                mb.face([F(j + 1, u) for u in us] + [K(j + 1, u) for u in reversed(us)], mat_r)
            dn = [(a, b)] if j == 0 else inter(rows[j - 1], a, b)
            for (c, d) in dn:
                us = rng_e(j, c, d)
                mb.face([K(j, u) for u in us] + [F(j, u) for u in reversed(us)], mat_r)
    return mb


# =====================================================================================================================
# bastidor de madera (pies derechos / postes y largueros) con vanos
# =====================================================================================================================
def _rect_sub(a, b, min_w=0.02):
    """Rectángulo a menos b (u0, u1, v0, v1) -> lista de rectángulos."""
    if b[0] >= a[1] or b[1] <= a[0] or b[2] >= a[3] or b[3] <= a[2]:
        return [a]
    out = []
    if b[0] > a[0]:
        out.append((a[0], b[0], a[2], a[3]))
    if b[1] < a[1]:
        out.append((b[1], a[1], a[2], a[3]))
    m0, m1 = max(a[0], b[0]), min(a[1], b[1])
    if b[2] > a[2]:
        out.append((m0, m1, a[2], b[2]))
    if b[3] < a[3]:
        out.append((m0, m1, b[3], a[3]))
    return [o for o in out if o[1] - o[0] >= min_w and o[3] - o[2] >= min_w]


def _cut(rc, z, vertical):
    """Resta la zona z al miembro rc sin dejar astillas que se toquen: un pie derecho solo se parte arriba/abajo y un
    larguero solo a izquierda/derecha."""
    if z[0] >= rc[1] or z[1] <= rc[0] or z[2] >= rc[3] or z[3] <= rc[2]:
        return [rc]
    if vertical:
        z = (min(z[0], rc[0]), max(z[1], rc[1]), z[2], z[3])
    else:
        z = (z[0], z[1], min(z[2], rc[2]), max(z[3], rc[3]))
    return _rect_sub(rc, z)


def _member(mb, rc, y0, y1, r, mat="wood", vertical=True, jag=False, grain=0.6, check=0.0):
    """Pieza del bastidor / tapajuntas: madera de cantos redondeados (3 mm) con vetas; recta (las holguras de 1 mm entre piezas
    del bastidor no admiten arqueos)."""
    u0, u1, v0, v1 = rc
    ym = (y0 + y1) / 2
    if vertical:
        um = (u0 + u1) / 2
        lumber(mb, (um, ym, v0), (um, ym, v1), u1 - u0, y1 - y0, mat, up=(0, 1, 0), r=r, rc=0.003, grain=grain, check=check)
    else:
        vm = (v0 + v1) / 2
        lumber(mb, (u0, ym, vm), (u1, ym, vm), v1 - v0, y1 - y0, mat, up=(0, 1, 0), r=r, rc=0.003, grain=grain, check=check)


def _framing(mb, L, H, y0, depth, openings, r, style="studs", spacing=0.6, mat="wood"):
    """Bastidor: soleras inferior y superior, pies derechos cada `spacing` ('studs') o postes + largueros ('girts'),
    y en cada vano: montantes, dintel de 0,15 y antepecho (ventanas). Piezas separadas 1 mm (sin caras coplanares)."""
    y1 = y0 + depth
    P = 0.05
    mem = []                    # (rect, vertical)
    cur = 0.0                    # solera inferior en tramos: no pasa por los vanos de puerta (umbral libre)
    for (u0, u1, v0, v1) in sorted(o for o in openings if o[2] <= 0.05):
        if u0 - 0.003 > cur:
            mem.append(((cur, u0 - 0.003, 0.0, P), False))
        cur = max(cur, u1 + 0.003)
    if cur < L:
        mem.append(((cur, L, 0.0, P), False))
    mem.append(((0.0, L, H - P, H), False))
    zones = []
    for (u0, u1, v0, v1) in openings:
        zones.append((u0 - 0.003, u1 + 0.003, v0 - P - 0.004 if v0 > 0.05 else -1.0, v1 + 0.154))
    vert = []
    if style == "studs":
        n = max(1, int(math.ceil((L - P) / spacing)))
        vert = [min(i * spacing, L - P) for i in range(n + 1)]
    else:
        n = max(1, int(math.ceil((L - P) / 1.8)))
        vert = [(L - P) * i / n for i in range(n + 1)]
    for (u0, u1, v0, v1) in openings:
        vert += [u0 - P - 0.004, u1 + 0.004]
    vert = sorted(vert)
    keep = []
    for x in vert:
        if any(abs(x - k) < P + 0.002 for k in keep):
            continue
        keep.append(x)
    for x in keep:
        pcs = [(x, x + P, P + 0.001, H - P - 0.001)]
        for z in zones:
            pcs = [q for p in pcs for q in _cut(p, z, True)]
        for p in pcs:
            mem.append((p, True))
    for (u0, u1, v0, v1) in openings:
        mem.append(((u0 - 0.002, u1 + 0.002, v1 + 0.003, min(v1 + 0.15, H - P - 0.002)), False))
        if v0 > 0.05:
            mem.append(((u0 - 0.002, u1 + 0.002, v0 - P - 0.003, v0 - 0.003), False))
    if style == "girts":
        nz = max(1, int(math.ceil((H - 2 * P) / 0.85)))
        for k in range(1, nz):
            v = P + (H - 2 * P) * k / nz
            gaps = sorted(keep)
            for a, b in zip(gaps[:-1], gaps[1:]):
                rc = (a + P + 0.001, b - 0.001, v - 0.05, v)
                pcs = [rc]
                for z in zones:
                    pcs = [q for p in pcs for q in _cut(p, (z[0] - 0.05, z[1] + 0.05, z[2], z[3]), False)]
                for p in pcs:
                    if p[1] - p[0] > 0.1:
                        mem.append((p, False))
    for rc, vt in mem:
        if rc[1] - rc[0] > 0.02 and rc[3] - rc[2] > 0.02:
            _member(mb, rc, y0, y1, r, mat, vertical=vt)
    return [x for x in keep], [rc for rc, vt in mem if not vt]


# =====================================================================================================================
# 1) LADRILLO A SOGA
# =====================================================================================================================
def _brick(mb, u0, u1, v0, v1, yf, yb, r, bev=0.004, chip=0, tilt=(0.0, 0.0), jag=0.0, mat="brick", mode="bevel"):
    """Ladrillo. mode 'bevel': 12 vértices / 10 quads (20 tris), cara vista con bisel de 1 segmento, costados hasta yb y
    cara trasera. 'box5': cara vista + 4 costados sin bisel (10 tris; la trasera queda enterrada en el núcleo).
    'front3': cara vista + tabla y sardinel (6 tris; los costados verticales de la llaga se dejan: de lejos manda la sombra de
    las hiladas). Los modos abiertos tienen sus bordes DENTRO del núcleo de mortero (yb > REC), así que se ven cerrados."""
    uc, vc = (u0 + u1) / 2, (v0 + v1) / 2

    def Y(u, v, y):
        return y + tilt[0] * (u - uc) + tilt[1] * (v - vc)
    if mode == "round":
        # 'round' (pasada AAA): aristas redondeadas de radio `bev` en 2 tramos (sombreado continuo) + costados hasta yb + trasera,
        # cara vista en abanico con un vértice central hundido/abombado ±0,8 mm (cara cocida irregular) y esquinas despostilladas.
        # 26 tris por ladrillo; sólido cerrado.
        b = max(0.0015, min(bev * 0.75, 0.25 * (u1 - u0), 0.25 * (v1 - v0)))
        L0 = [[u0 + b + r.uniform(-0.0006, 0.0006), v0 + b + r.uniform(-0.0004, 0.0004)],
              [u1 - b + r.uniform(-0.0006, 0.0006), v0 + b + r.uniform(-0.0004, 0.0004)],
              [u1 - b + r.uniform(-0.0006, 0.0006), v1 - b + r.uniform(-0.0004, 0.0004)],
              [u0 + b + r.uniform(-0.0006, 0.0006), v1 - b + r.uniform(-0.0004, 0.0004)]]
        d0 = [Y(u, v, yf) for u, v in L0]
        k1 = 0.2929 * b
        L1 = [[u0 + k1, v0 + k1], [u1 - k1, v0 + k1], [u1 - k1, v1 - k1], [u0 + k1, v1 - k1]]
        d1 = [Y(u, v, yf + k1) for u, v in L1]
        if chip:
            for _ in range(chip):
                k = int(r.integers(0, 4))
                du = r.uniform(0.01, 0.028) * (1 if k in (0, 3) else -1)
                dv = r.uniform(0.006, 0.016) * (1 if k in (0, 1) else -1)
                dd = r.uniform(0.003, 0.0065)          # el despostillado no pasa detrás de la cara del núcleo de mortero (8 mm)
                L0[k][0] += du
                L0[k][1] += dv
                d0[k] += dd
                L1[k][0] += du * 0.55
                L1[k][1] += dv * 0.55
                d1[k] += dd * 0.6
        if jag:
            d0 = [y + r.uniform(0.0, jag) for y in d0]
        outer = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        # cara vista: rejilla 3 x 2 bilineal sobre las 4 esquinas, con el arris y la cara irregulares (ladrillo de horno)
        NU, NV = 3, 2

        def bil(i, j):
            fu, fv = i / NU, j / NV
            a = [L0[0][0] + (L0[1][0] - L0[0][0]) * fu, L0[0][1] + (L0[1][1] - L0[0][1]) * fu, d0[0] + (d0[1] - d0[0]) * fu]
            c = [L0[3][0] + (L0[2][0] - L0[3][0]) * fu, L0[3][1] + (L0[2][1] - L0[3][1]) * fu, d0[3] + (d0[2] - d0[3]) * fu]
            return [a[k] + (c[k] - a[k]) * fv for k in range(3)]
        G = {}
        for i in range(NU + 1):
            for j in range(NV + 1):
                u, v, y = bil(i, j)
                corner = i in (0, NU) and j in (0, NV)
                edge = i in (0, NU) or j in (0, NV)
                if not corner:
                    if edge:
                        y += r.uniform(-0.0004, 0.0006)
                        if j in (0, NV):
                            v += r.uniform(-0.0007, 0.0007)
                        else:
                            u += r.uniform(-0.0007, 0.0007)
                    else:
                        y += r.uniform(-0.0009, 0.0009)
                G[i, j] = mb.bm.verts.new((u, y, v))
        for i in range(NU):
            for j in range(NV):
                mb.face([G[i, j], G[i + 1, j], G[i + 1, j + 1], G[i, j + 1]], mat)
        edges = [[G[i, 0] for i in range(NU + 1)], [G[NU, j] for j in range(NV + 1)],
                 [G[i, NV] for i in range(NU, -1, -1)], [G[0, j] for j in range(NV, -1, -1)]]
        M1 = [mb.bm.verts.new((u, y, v)) for (u, v), y in zip(L1, d1)]
        with mb.soft():
            O = [mb.bm.verts.new((u, Y(u, v, yf + b), v)) for u, v in outer]
            B = [mb.bm.verts.new((u, yb, v)) for u, v in outer]
            for i in range(4):
                j = (i + 1) % 4
                mb.face(list(reversed(edges[i])) + [M1[i], M1[j]], mat)
                mb.face([M1[j], M1[i], O[i], O[j]], mat)
                mb.face([O[j], O[i], B[i], B[j]], mat)
            mb.face(B, mat)
        return
    if mode != "bevel":
        fy = yf + (r.uniform(0.0, jag) if jag else 0.0)
        c = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
        Fv = [mb.bm.verts.new((u, Y(u, v, fy), v)) for u, v in c]
        Bv = [mb.bm.verts.new((u, yb, v)) for u, v in c]
        mb.face(Fv, mat)
        sides = (0, 1, 2, 3) if mode == "box5" else (0, 2)          # 0 = sardinel (abajo), 2 = tabla (arriba)
        for i in sides:
            j = (i + 1) % 4
            mb.face([Fv[j], Fv[i], Bv[i], Bv[j]], mat)
        return
    b = max(0.0015, min(bev, 0.3 * (u1 - u0), 0.3 * (v1 - v0)))
    front = [[u0 + b, v0 + b], [u1 - b, v0 + b], [u1 - b, v1 - b], [u0 + b, v1 - b]]
    fy = [Y(u, v, yf) for u, v in front]
    if chip:
        for _ in range(chip):
            k = int(r.integers(0, 4))
            du = r.uniform(0.01, 0.028) * (1 if k in (0, 3) else -1)
            dv = r.uniform(0.006, 0.016) * (1 if k in (0, 1) else -1)
            front[k][0] += du
            front[k][1] += dv
            fy[k] += r.uniform(0.004, 0.012)
    if jag:
        fy = [y + r.uniform(0.0, jag) for y in fy]
    outer = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    Fv = [mb.bm.verts.new((u, y, v)) for (u, v), y in zip(front, fy)]
    Ov = [mb.bm.verts.new((u, Y(u, v, yf + b), v)) for u, v in outer]
    Bv = [mb.bm.verts.new((u, yb, v)) for u, v in outer]
    mb.face(Fv, mat)
    for i in range(4):
        j = (i + 1) % 4
        mb.face([Fv[i], Fv[j], Ov[j], Ov[i]], mat)
        mb.face([Ov[i], Ov[j], Bv[j], Bv[i]], mat)
    mb.face(list(reversed(Bv)), mat)


def _bond_pieces(p, q, off):
    """Ladrillos (a, b) del aparejo a soga que caen en [p, q]; extremos enrasados y sin piezas < 7 cm."""
    k0 = int(math.floor((p - off) / PITCH)) - 1
    out = []
    k = k0
    while True:
        s = off + k * PITCH
        if s > q:
            break
        a, b = max(s, p), min(s + BRICK_L, q)
        if b - a > 1e-4:
            out.append([a, b])
        k += 1
    if not out:
        return []
    out[0][0] = p
    out[-1][1] = q
    # piezas cortas -> se reparten con la vecina
    i = 0
    while i < len(out):
        a, b = out[i]
        if b - a < 0.07 and len(out) > 1:
            j = i + 1 if i + 1 < len(out) else i - 1
            lo, hi = min(out[i][0], out[j][0]), max(out[i][1], out[j][1])
            mid = (lo + hi) / 2
            pair = [[lo, mid - JOINT / 2], [mid + JOINT / 2, hi]]
            if hi - lo < 0.15:
                pair = [[lo, hi]]
            out[min(i, j):max(i, j) + 1] = pair
            i = 0 if len(pair) == 1 else i
            if len(pair) == 1 and len(out) == 1:
                break
            continue
        i += 1
    return [tuple(x) for x in out]


BRICK_LOD = {
    # modo del ladrillo corriente / de jamba, puntos del contorno de los parches de revoque, bisel de los caídos
    "high": dict(brick="bevel", jamb="bevel", plaster_pts=22, fallen_bev=0.006),
    "mid": dict(brick="box5", jamb="box5", plaster_pts=14, fallen_bev=0.0),
    "low": dict(brick="front3", jamb="box5", plaster_pts=10, fallen_bev=0.0),
    # pasada AAA (2026-11-19): aristas redondeadas en 2 tramos, cara irregular, despostillados; ~26 tris por ladrillo
    "aaa": dict(brick="round", jamb="round", plaster_pts=24, fallen_bev=0.006),
}


def _patch(mb, pts, t, mat, m, r):
    """Parche de revoque viejo: canto roto en dos escalones (la capa de acabado se desprende antes que el emparche), no una
    placa de canto vivo. pts en el plano (x, y) de la placa; espesor t hacia +z local."""
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)

    def ins(p, d):
        dx, dy = cx - p[0], cy - p[1]
        L = math.hypot(dx, dy)
        k = min(d, 0.45 * L) / max(L, 1e-9)
        return (p[0] + dx * k, p[1] + dy * k)
    rings = [[(x, y, 0.0) for x, y in pts]]
    d1 = [r.uniform(0.002, 0.006) for _ in pts]
    rings.append([(*ins(p, d), t * 0.55) for p, d in zip(pts, d1)])
    rings.append([(*ins(p, d + r.uniform(0.002, 0.012)), t) for p, d in zip(pts, d1)])
    vs = [[mb.bm.verts.new(m @ Vector(p)) for p in rg] for rg in rings]
    k = len(pts)
    for i in range(2):
        for j in range(k):
            jj = (j + 1) % k
            mb.face([vs[i][j], vs[i][jj], vs[i + 1][jj], vs[i + 1][j]], mat)
    mb.face(list(reversed(vs[0])), mat)
    mb.face(vs[2], mat)


def brick_wall(length, height, seed=0, openings=(), missing=0.02, thickness=0.14, plaster=0.12, lintel_courses=3,
               fallen=True, detail="high", keep_ends=0.0):
    """Muro de ladrillo individual a soga sobre núcleo de mortero (ver cabecera). openings como wall_with_openings.
    detail = 'aaa' | 'high' | 'mid' | 'low' (BRICK_LOD); la disposición (aparejo, faltantes, descascarados, caídos, revoque) es la
    misma en los tres niveles. Ladrillo de 20 / 10 / 6 tris (bisel / caja sin trasera / cara + tabla + sardinel; los de
    jamba, que se ven en el derrame, son caja sin trasera en mid y low). Medido con test_G3 (--budget) en un muro de
    6,5 x 2,8 con 2 ventanas y 1 puerta (13,6 m² de ladrillo, 57 ladrillos/m²), núcleo, dinteles, caídos y revoque incluidos:
      high ~18,8 k tris (~1380 tris/m²) · mid ~10,6 k (~780/m²) · low ~7,3 k (~535/m²)."""
    if detail not in BRICK_LOD:
        raise ValueError("detail debe ser 'aaa', 'high', 'mid' o 'low'")
    lod = BRICK_LOD[detail]
    r = rng(seed + 2024)
    mb = MB()
    L, H = float(length), float(height)
    ops = [tuple(float(x) for x in o) for o in openings]
    obst = []                  # (u0, u1, v0, v1, kind)
    holes = []
    for (u0, u1, v0, v1) in ops:
        obst.append((u0, u1, v0, v1, "open"))
        holes.append((u0 - 0.006, u1 + 0.006, max(0.0, v0 - 0.006) if v0 > 0.05 else -0.01, v1 + 0.006))
        lh = lintel_courses * COURSE
        if v1 < H - 0.05:
            obst.append((u0 - 0.12 - JOINT, u1 + 0.12 + JOINT, v1, min(v1 + lh + JOINT / 2, H + 0.1), "stone"))
        if v0 > 0.05:
            obst.append((u0 - 0.06 - JOINT, u1 + 0.06 + JOINT, v0 - 0.075 - JOINT / 2, v0, "stone"))
    noise = _N1(r, wl=1.7)
    nz2 = _N1(r, wl=0.9)
    wav = _N1(r, wl=2.6)
    bricks_tris = 0
    fallen_list = []
    nc = int(H / COURSE) + 1
    cov = r.uniform(0, PITCH)
    for c in range(nc):
        cv0 = c * COURSE + JOINT / 2
        cv1 = min(cv0 + BRICK_H, H - 0.003)
        if cv1 - cv0 < 0.02:
            break
        off = cov + (PITCH / 2 if c % 2 else 0.0)
        # tramos elementales en u y su rango v permitido
        edges = {0.0, L}
        rel = [o for o in obst if o[2] < cv1 and o[3] > cv0]
        for o in rel:
            edges |= {min(max(o[0], 0.0), L), min(max(o[1], 0.0), L)}
        edges = sorted(edges)
        runs = []
        for a, b in zip(edges[:-1], edges[1:]):
            if b - a < 1e-6:
                continue
            m = (a + b) / 2
            lo, hi, blocked = cv0, cv1, False
            for o in rel:
                if not (o[0] < m < o[1]):
                    continue
                g = JOINT if o[4] == "stone" else 0.0
                if o[2] <= cv0 + 0.02 and o[3] >= cv1 - 0.02:
                    blocked = True
                    break
                if o[2] > cv0:
                    hi = min(hi, o[2] - g)
                if o[3] < cv1:
                    lo = max(lo, o[3] + g)
            if blocked or hi - lo < 0.025:
                continue
            key = (round(lo, 5), round(hi, 5))
            if runs and runs[-1][2] == key and abs(runs[-1][1] - a) < 1e-6:
                runs[-1][1] = b
            else:
                runs.append([a, b, key])
        open_edges = {round(o[0], 6) for o in obst if o[4] == "open"} | {round(o[1], 6) for o in obst if o[4] == "open"}
        # tramos contiguos de distinta altura (junto a un dintel o alféizar): llaga de 1 cm entre ellos
        for q in range(len(runs) - 1):
            if abs(runs[q][1] - runs[q + 1][0]) < 1e-6:
                runs[q][1] -= JOINT / 2
                runs[q + 1][0] += JOINT / 2
        for a, b, (lo, hi) in runs:
            for (pa, pb) in _bond_pieces(a, b, off):
                jamb = (round(pa, 6) in open_edges and pa > 0.001) or (round(pb, 6) in open_edges and pb < L - 0.001)
                ua, ub = pa + r.uniform(-0.002, 0.002) * (pa > a), pb + r.uniform(-0.002, 0.002) * (pb < b)
                cw = 0.0028 * wav((pa + pb) * 0.35 + c * 0.11)        # hiladas levemente onduladas (asiento)
                va = lo + (cw if lo == cv0 else 0.0) + r.uniform(-0.0012, 0.0012)
                vb = hi + (cw if hi == cv1 else 0.0) + r.uniform(-0.0012, 0.0012)
                px, py = (ua + ub) / 2, (va + vb) / 2
                yf = r.uniform(-0.0015, 0.0012)
                tilt = (r.uniform(-0.006, 0.006), r.uniform(-0.01, 0.01))
                bev, chip, jag = 0.004, 0, 0.0
                pm = missing * max(0.0, 1.0 + 1.8 * noise(px * 0.9 + py * 1.4)) * (1.6 if va < 0.5 else 1.0)
                roll = r.uniform()
                if not jamb and ub - ua > 0.1 and roll < pm:
                    holes.append((ua - 0.004, ub + 0.004, va - 0.004, vb + 0.004))
                    if r.uniform() < 0.35:
                        # descascarado: queda el ladrillo roto metido 2–5 cm
                        _brick(mb, ua + 0.003, ub - 0.003, va + 0.002, vb - 0.002, r.uniform(0.02, 0.045), thickness - 0.012, r,
                               bev=0.008, jag=0.012)
                    elif fallen and r.uniform() < 0.6:
                        fallen_list.append((ub - ua, vb - va))
                    continue
                damp = max(0.0, 0.55 - va) / 0.55
                if roll < pm + 0.2 * (0.6 + 0.4 * nz2(px * 2.0 + py)) + 0.45 * damp:
                    yf += r.uniform(0.002, 0.006)          # cara erosionada: bisel mayor y hundida
                    bev = r.uniform(0.006, 0.011)
                if r.uniform() < 0.06:
                    chip = 1 + int(r.uniform() < 0.25)
                yb = BRICK_D - 0.002 if jamb else 0.02
                _brick(mb, ua, ub, va, vb, yf, yb, r, bev=bev, chip=chip, tilt=tilt, mode=lod["jamb"] if jamb else lod["brick"])
                bricks_tris += 20

    # ---- núcleo de mortero con los vanos y los agujeros de ladrillos faltantes ----
    _strip_wall(mb, L - 0.004, H, REC, thickness, holes, u_min=0.004)

    # ---- dinteles y alféizares de piedra (en 'aaa' aristas redondeadas en 4 tramos: piedra labrada gastada) ----
    lod_seg = 4 if detail == "aaa" else 1
    for (u0, u1, v0, v1) in ops:
        if v1 < H - 0.05:
            top = min(v1 + lintel_courses * COURSE, H)
            a, b = u0 - 0.12, u1 + 0.12
            if r.uniform() < 0.35 and u1 - u0 > 0.6:
                # dintel rajado: dos piezas con la grieta y un leve asiento
                cut = r.uniform(u0 + 0.25 * (u1 - u0), u1 - 0.25 * (u1 - u0))
                for (x0, x1, sg) in ((a, cut - 0.002, 1), (cut + 0.002, b, -1)):
                    m = _about(((x0 + x1) / 2, 0, v1), _R("Y", sg * r.uniform(0.3, 0.9)))
                    mb.box((x0, -0.012, v1 + 0.002), (x1, thickness - 0.02, top - 0.002), "concrete", bevel=0.008, seg=lod_seg, m=m)
            else:
                m = _about(((a + b) / 2, 0, v1), _R("Y", r.uniform(-0.4, 0.4)))
                mb.box((a, -0.012, v1), (b, thickness - 0.02, top - 0.002), "concrete", bevel=0.009, seg=lod_seg, m=m)
        if v0 > 0.05:
            a, b = u0 - 0.06, u1 + 0.06
            m = _about(((a + b) / 2, 0.06, v0 - 0.004), _R("X", r.uniform(5.0, 8.0)) @ _R("Y", r.uniform(-0.5, 0.5)))
            mb.box((a, -0.045, v0 - 0.075), (b, 0.07, v0 - 0.004), "concrete", bevel=0.008, seg=lod_seg, m=m)

    # ---- ladrillos caídos al pie del muro ----
    for idf, (lw, lh) in enumerate(fallen_list[:12]):
        x = r.uniform(0.2, L - 0.2)
        a = r.uniform(0, 360)
        half = r.uniform() < 0.4
        ln = BRICK_L * (r.uniform(0.4, 0.6) if half else 1.0)
        lay = r.uniform() < 0.7
        dims = (ln, BRICK_D, BRICK_H) if lay else (ln, BRICK_H, BRICK_D)
        m = _T(x, -r.uniform(0.08, 0.7), 0.0013 * (idf % 5)) @ _R("Z", a) @ _R("X", r.uniform(-4, 4))
        if detail == "aaa":
            # ladrillo suelto de aristas gastadas (radio 6 mm en 4 tramos: sombreado continuo)
            mb.box((-dims[0] / 2, -dims[1] / 2, 0.001), (dims[0] / 2, dims[1] / 2, dims[2] + 0.001), "brick", bevel=0.006, seg=4, m=m)
        else:
            mb.box((-dims[0] / 2, -dims[1] / 2, 0.001), (dims[0] / 2, dims[1] / 2, dims[2] + 0.001), "brick",
                   bevel=lod["fallen_bev"], seg=1, m=m)

    # ---- restos de revoque ----
    if plaster > 0:
        area, target, tries = 0.0, plaster * L * H, 0
        stone = [o for o in obst]
        while area < target and tries < 40:
            tries += 1
            ru, rv = r.uniform(0.25, 0.9), r.uniform(0.2, 0.6)
            pu, pv = r.uniform(ru * 0.6, L - ru * 0.6), r.uniform(rv * 0.6, H - rv * 0.6)
            if any(pu + ru > o[0] - 0.03 and pu - ru < o[1] + 0.03 and pv + rv > o[2] - 0.03 and pv - rv < o[3] + 0.03
                   for o in stone):
                continue
            if keep_ends and (pu - ru * 1.3 < keep_ends or pu + ru * 1.3 > L - keep_ends):
                continue                                                  # sin revoque bajo los sillares de esquina
            nn = _N1(r, wl=1.0, n=4)
            pts = []
            jit = [r.uniform(-0.06, 0.06) for _ in range(22)]
            npp = lod["plaster_pts"]
            for i in range(npp):
                a = 2 * PI * i / npp
                k = 1.0 + 0.32 * nn(a * 2.0) + jit[int(i * 22 / npp)]
                pts.append((min(max(pu + ru * k * math.cos(a), 0.01), L - 0.01), min(max(pv + rv * k * math.sin(a), 0.01), H - 0.01)))
            t = r.uniform(0.008, 0.013)
            m = Matrix(((1, 0, 0, 0), (0, 0, -1, 0.002 if detail == "aaa" else -0.004), (0, 1, 0, 0), (0, 0, 0, 1)))
            if detail == "aaa":                                           # el parche asienta 2 mm dentro de la cara del ladrillo
                _patch(mb, pts, t, "plaster", m, r)
            else:
                mb.plate(pts, t, "plaster", m=m)
            area += PI * ru * rv
    return mb


# =====================================================================================================================
# utilidades de revestimiento de madera
# =====================================================================================================================
def _segments(ua, ub, v0, v1, obst, gap=0.002, min_h=0.03):
    """Tramos elementales en [ua, ub] con su rango v permitido dentro de [v0, v1] evitando los rectángulos obst."""
    edges = {ua, ub}
    rel = [o for o in obst if o[2] < v1 and o[3] > v0 and o[1] > ua and o[0] < ub]
    for o in rel:
        edges |= {min(max(o[0] - gap, ua), ub), min(max(o[1] + gap, ua), ub)}
    edges = sorted(edges)
    out = []
    for a, b in zip(edges[:-1], edges[1:]):
        if b - a < 1e-5:
            continue
        m = (a + b) / 2
        lo, hi, bl = v0, v1, False
        for o in rel:
            if not (o[0] - gap < m < o[1] + gap):
                continue
            if o[2] <= v0 + min_h and o[3] >= v1 - min_h:
                bl = True
                break
            if (o[2] + o[3]) / 2 > (v0 + v1) / 2:
                hi = min(hi, o[2] - gap)
            else:
                lo = max(lo, o[3] + gap)
        if bl or hi - lo < min_h:
            continue
        if out and abs(out[-1][1] - a) < 1e-6 and abs(out[-1][2] - lo) < 1e-6 and abs(out[-1][3] - hi) < 1e-6:
            out[-1][1] = b
        else:
            out.append([a, b, lo, hi])
    return [tuple(o) for o in out]


def _trims(mb, ops, y0, y1, r, mat="wood_grey", H=99.0):
    """Tapajuntas de vano (jambas 0,09, cabezal 0,12 con vierteaguas, delantal y repisa en ventanas). Devuelve sus rectángulos."""
    rects = []
    for (u0, u1, v0, v1) in ops:
        win = v0 > 0.05
        vb = v0 - 0.002 if win else 0.0
        top = min(v1 + 0.12, H - 0.004)
        parts = [((u0 - 0.09, u0 - 0.002, vb, v1), True), ((u1 + 0.002, u1 + 0.09, vb, v1), True),
                 ((u0 - 0.09, u1 + 0.09, v1 + 0.001, top), False)]
        if win:
            parts.append(((u0 - 0.06, u1 + 0.06, v0 - 0.11, v0 - 0.04), False))
        for (a, b, c, d), vert in parts:
            if d - c < 0.03:
                continue
            _member(mb, (a, b, c, d), y0 + r.uniform(-0.002, 0.0), y1, r, mat, vertical=vert)
            rects.append((a, b, c, d))
        # vierteaguas sobre el cabezal y repisa de la ventana (sobresalen): tabla de cantos redondeados con su caída
        if top + 0.03 < H:
            lbox_m(mb, (u0 - 0.11, y0 - 0.03, top + 0.001), (u1 + 0.11, y1, top + 0.026), mat,
                   _about(((u0 + u1) / 2, y1, top), _R("X", -r.uniform(4, 9))), r=r, axis=0, rc=0.004, grain=0.8,
                   sag=-r.uniform(0.0, 0.004))
            rects.append((u0 - 0.11, u1 + 0.11, top, top + 0.035))
        if win:
            # repisa por delante del revestimiento (antes se metía 4 cm en tablas y montantes)
            lbox_m(mb, (u0 - 0.08, y0 - 0.045, v0 - 0.039), (u1 + 0.08, y1 - 0.002, v0 - 0.003), mat,
                   _about(((u0 + u1) / 2, y1 - 0.002, v0 - 0.003), _R("X", r.uniform(2, 6))), r=r, axis=0, rc=0.005,
                   grain=1.0, check=0.5 if r.uniform() < 0.4 else 0.0)
            rects.append((u0 - 0.08, u1 + 0.08, v0 - 0.045, v0))
    return rects


def _vboard(mb, uc, w, t, v0, v1, r, jag0=0.0, jag1=0.0, mat="wood", step=0.45, knots=True, cut1=None):
    """Tablón vertical (cara vista en y = 0, espesor hacia +y) de cantos redondeados (4 mm) con vetas abiertas que nacen y
    mueren, fenda de secado en uno de cada tres, leve abarquillado hacia dentro, arqueo lateral, alabeo, puntas astilladas y
    nudos (lentes de madera oscura en la zona libre de junquillos). cut1 = (punto, normal): corte del extremo alto (hastial)."""
    bow, cup = r.uniform(-0.003, 0.003), r.uniform(0.0, 0.003)
    lumber(mb, (uc, t / 2, v0), (uc, t / 2, v1), w, t, mat, up=(0, 1, 0), r=r, rc=0.004, step=step, grain=1.0,
           check=0.6 if r.uniform() < 0.33 else 0.0, bow=bow, twist=r.uniform(-0.004, 0.004), cup=cup, jag0=jag0, jag1=jag1,
           cut1=cut1)
    if knots and w > 0.12 and v1 - v0 > 0.5:
        for _ in range(int(r.integers(0, 3))):
            ku = r.uniform(-w / 2 + 0.035, w / 2 - 0.035)
            kv = r.uniform(v0 + 0.15, v1 - 0.15)
            rx = r.uniform(0.010, 0.024)
            knot(mb, (uc + ku + bow * math.sin(PI * (kv - v0) / (v1 - v0)), cup * (1.0 - (2 * ku / w) ** 2), kv), (0, -1, 0),
                 (0, 0, 1), rx, rx * r.uniform(0.55, 0.85))


# =====================================================================================================================
# 2) TABLÓN Y JUNQUILLO
# =====================================================================================================================
def board_and_batten(length, height, seed=0, openings=(), rot=0.1, board=0.22, gap=0.022, frame=True, batten=0.064):
    """Tablones verticales (0,22 = 1x10 en bruto, rendija 0,022 ± 8 mm: la tabla vieja se encoge) con junquillos 1x3
    (0,064 x 0,020) que traslapan ~2 cm cada tablón (ver cabecera para cotas). rot 0..1: tablones podridos por abajo (más
    cortos, punta astillada), rotos con tramo faltante, faltantes; junquillos faltantes, cortos o colgando de un clavo.
    Bastidor de postes y largueros detrás (frame=True)."""
    r = rng(seed + 8080)
    mb = MB()
    L, H = float(length), float(height)
    ops = [tuple(float(x) for x in o) for o in openings]
    BT = 0.022
    girts_v = []
    if frame:
        _, hm = _framing(mb, L, H, BT + 0.002, 0.10, ops, r, style="girts")      # el alabeo de la tabla llega a +0,8 mm
        girts_v = sorted({round((h[2] + h[3]) / 2, 3) for h in hm})
    trims = _trims(mb, ops, -0.0245, -0.0015, r, H=H)
    rotn = _N1(r, wl=1.6)
    # ---- tablones ----
    cols, u = [], 0.004
    while u < L - 0.06:
        wdt = min(board + r.uniform(-0.025, 0.02), L - 0.004 - u)
        cols.append((u, u + wdt))
        u += wdt + gap + r.uniform(-0.008, 0.008)
    for (bu0, bu1) in cols:
        pcs = [(bu0, bu1, 0.015, H - 0.004)]
        for (u0, u1, v0, v1) in ops:
            pcs = [q for p in pcs for q in _rect_sub(p, (u0, u1, v0 - 0.001, v1 + 0.001), min_w=0.035)]
        for (a, b, c, d) in pcs:
            a, b = a + (0.0015 if a > bu0 + 1e-6 else 0.0), b - (0.0015 if b < bu1 - 1e-6 else 0.0)
            uc = (a + b) / 2
            sev = rot * (1.0 + 1.2 * rotn(uc * 1.3))
            if r.uniform() < 0.22 * sev:
                continue                                            # faltante
            segs = [(c, d, 0.0, 0.0)]
            if c < 0.05 and r.uniform() < 0.9 * sev:
                segs = [(c + r.uniform(0.08, 0.55), d, 0.035, 0.0)]  # pie podrido
            if d - c > 1.2 and r.uniform() < 0.35 * sev:
                g0 = r.uniform(c + 0.4, d - 0.8)
                g1 = g0 + r.uniform(0.12, 0.5)
                lo = segs[0]
                segs = [(lo[0], g0, lo[2], 0.03), (g1, lo[1], 0.03, 0.0)]
                if r.uniform() < 0.3:
                    segs = segs[1:]
            for (sa, sb, j0, j1) in segs:
                if sb - sa < 0.08:
                    continue
                _vboard(mb, uc, b - a, BT, sa, sb, r, jag0=j0, jag1=j1)
                # clavos en cada larguero (no bajo los tapajuntas)
                for gv in girts_v:
                    if sa + 0.04 < gv < sb - 0.04:
                        pu, pv = uc + r.uniform(-0.01, 0.01), gv + r.uniform(-0.01, 0.01)
                        if any(t[0] - 0.01 < pu < t[1] + 0.01 and t[2] - 0.01 < pv < t[3] + 0.01 for t in trims):
                            continue
                        pop = r.uniform(0.004, 0.012) if r.uniform() < 0.06 else 0.0
                        nail(mb, (pu, 0.0, pv), (0, -1, 0), r=0.0048, h=0.0026, pop=pop, bend=r.uniform(0.0, 0.6) if pop else 0.0)
    # ---- junquillos ----
    hb = batten / 2
    for (c0, c1) in zip(cols[:-1], cols[1:]):
        um = (c0[1] + c1[0]) / 2
        rc = (um - hb, um + hb, 0.03, H - 0.01)
        pcs = [rc]
        for t in trims:
            pcs = [q for p in pcs for q in _rect_sub(p, (t[0] - 0.003, t[1] + 0.003, t[2] - 0.003, t[3] + 0.003))]
        for (u0, u1, v0, v1) in ops:
            pcs = [q for p in pcs for q in _rect_sub(p, (u0, u1, v0, v1))]
        for (a, b, c, d) in pcs:
            if b - a < batten - 0.005 or d - c < 0.1:
                continue
            sev = rot * (1.0 + 1.2 * rotn(um * 1.3 + 5.0))
            x = r.uniform()
            if x < 0.3 * sev:
                continue
            if x < 0.45 * sev:
                c = c + r.uniform(0.1, 0.6) * (d - c)                # corto
            yo = -0.021 - (r.uniform(0.0, 0.004) if r.uniform() < 0.3 else 0.0)
            M = None
            if 0.45 * sev < x < 0.6 * sev and d - c > 0.6:
                # colgando del clavo superior: gira en el plano y se despega
                ang = math.degrees(math.atan2(min(0.12, gap + 0.08), d - c)) * r.choice((-1, 1))
                M = _about((um, -0.021, d - 0.05), _R("Y", ang) @ _R("X", -r.uniform(1.0, 3.0)))
            tmp = MB()
            lumber(tmp, (um, yo + 0.010, c), (um, yo + 0.010, d), batten, 0.020, "wood_dark", up=(0, 1, 0), r=r, rc=0.004,
                   step=0.5, grain=0.8, check=0.5 if r.uniform() < 0.25 else 0.0, bow=r.uniform(-0.0015, 0.0015),
                   jag0=0.02 if c > 0.05 else 0.0)
            if M is not None:
                M = _T(0, -0.002, 0) @ M
                # el clavo del que cuelga: cabeza sobre el junquillo y caña que lo atraviesa hasta el tablón
                with tmp.soft():
                    tmp.tube([(um, yo - 0.003, d - 0.05), (um, 0.006, d - 0.05)], 0.0016, seg=8, mat="metal_rust")
                nail(tmp, (um, yo - 0.0005, d - 0.05), (0, -1, 0), r=0.0046, h=0.0025)
            mb.join(tmp, M)
            tmp.bm.free()
            for gv in girts_v:
                if c + 0.04 < gv < d - 0.04 and M is None:
                    nail(mb, (um + r.uniform(-0.004, 0.004), yo, gv), (0, -1, 0), r=0.0046, h=0.0025)
    return mb


# =====================================================================================================================
# 3) TABLA TRASLAPADA (perfil cuña)
# =====================================================================================================================
CLAP_W, CLAP_EXP, CLAP_TB, CLAP_TT = 0.18, 0.15, 0.016, 0.006
CLAP_YS = 0.026                          # cara de los pies derechos


def _clap_y():
    f = CLAP_EXP / CLAP_W
    ytb = CLAP_YS - 0.001
    ybb = ytb - (CLAP_TT - CLAP_TB) - (CLAP_TB + 0.001) / f
    return ybb, ytb


def clapboard(length, height, seed=0, openings=(), corners=(True, True), loose=0.07, frame=True):
    """Tablas horizontales traslapadas de perfil cuña (exposición 0,15) sobre pies derechos, con esquineros, tapajuntas de vano,
    tabla de arranque, juntas a tope desfasadas y clavos. Envejecido: tablas sueltas (el canto bajo se despega y cuelga),
    corridas, rotas (falta media tabla) y faltantes (asoma el bastidor)."""
    r = rng(seed + 6060)
    mb = MB()
    L, H = float(length), float(height)
    ops = [tuple(float(x) for x in o) for o in openings]
    ybb, ytb = _clap_y()
    studs = []
    if frame:
        studs, _ = _framing(mb, L, H, CLAP_YS, 0.10, ops, r, style="studs")
    obst = list(_trims(mb, ops, CLAP_YS - 0.034, CLAP_YS - 0.001, r, H=H))
    obst += [(u0, u1, v0, v1) for (u0, u1, v0, v1) in ops]
    ua, ub = 0.0, L
    for k, on in enumerate(corners):
        if not on:
            continue
        a, b = (0.0, 0.10) if k == 0 else (L - 0.10, L)
        _member(mb, (a, b, 0.0, H), CLAP_YS - 0.033, CLAP_YS - 0.001, r, "wood_grey", vertical=True)
        if k == 0:
            ua = 0.102
        else:
            ub = L - 0.102
    # tabla de arranque (cortada en las puertas y tapajuntas: antes cruzaba el umbral)
    for (a, b, lo, hi) in _segments(ua, ub, 0.03, 0.07, obst, gap=0.002, min_h=0.03):
        if b - a > 0.08:
            _member(mb, (a, b, 0.03, 0.07), ybb + 0.001, ytb - 0.0015, r, "wood_grey", vertical=False)
    lz = _N1(r, wl=2.0)

    fk = (CLAP_EXP - 0.012) / CLAP_W               # línea donde apoya el canto de la tabla de arriba

    def ring(u, vk, f0, f1, kick=0.0, drop=0.0, bend=False):
        def yb(f):
            return ybb + (ytb - ybb) * f

        def th(f):
            return CLAP_TB + (CLAP_TT - CLAP_TB) * f
        v0, v1 = vk + CLAP_W * f0 - drop, vk + CLAP_W * f1
        kick = kick + r.uniform(0.0, 0.0018)          # canto bajo irregular (tabla vieja, alabeada)
        v0 -= r.uniform(0.0, 0.002)
        rb = min(0.0035, 0.3 * (v1 - v0), 0.3 * th(f0))
        yf0 = yb(f0) - th(f0) - kick
        # canto vivo de la testa redondeado (radio 3,5 mm, 4 segmentos: es la línea de sombra que se ve de la fachada)
        arc = [(yf0 + rb * (1 - math.sin(PI / 2 * k / 4)), v0 + rb * (1 - math.cos(PI / 2 * k / 4))) for k in range(5)]
        if bend:
            # tabla suelta: se despega por debajo de la línea fk y conserva la parte que tapa la tabla de arriba, así no se
            # mete en ella (antes giraba entera alrededor del canto alto)
            fm = min(max(fk, f0 + 0.05), f1 - 0.02)
            vm_ = vk + CLAP_W * fm
            pts = [(yb(f0) - kick, v0), (yb(fm), vm_), (yb(f1), v1), (yb(f1) - th(f1), v1), (yb(fm) - th(fm), vm_)] + \
                arc[::-1]
        else:
            pts = [(yb(f0) - kick, v0), (yb(f1), v1), (yb(f1) - th(f1), v1)] + arc[::-1]
        return [Vector((u, y, v)) for y, v in pts]

    k, vk = 0, 0.03
    while vk < H - 0.04:
        segs = _segments(ua, ub, vk, min(vk + CLAP_W, H - 0.003), obst, gap=0.002, min_h=0.03)
        # juntas a tope desfasadas
        for (a, b, lo, hi) in segs:
            cuts = [a]
            while cuts[-1] + 4.2 < b:
                cuts.append(cuts[-1] + r.uniform(1.8, 4.2))
            cuts.append(b)
            for (pa, pb) in zip(cuts[:-1], cuts[1:]):
                pa2, pb2 = pa + (0.0015 if pa > ua + 1e-6 else 0.0), pb - (0.0015 if pb < ub - 1e-6 else 0.0)
                f0, f1 = (lo - vk) / CLAP_W, (hi - vk) / CLAP_W
                um = (pa2 + pb2) / 2
                x = r.uniform()
                sev = 1.0 + 1.3 * lz(um * 0.9 + vk * 1.7)
                if k > 0 and x < loose * 0.35 * sev:
                    continue                                                    # faltante
                kick0 = kick1 = 0.0
                drop = 0.0
                j0 = j1 = 0.0
                if k > 0 and x < loose * 0.8 * sev:
                    # suelta: un extremo se despega y cae
                    if r.uniform() < 0.5:
                        kick1, drop = r.uniform(0.015, 0.05), r.uniform(0.0, 0.012)
                    else:
                        kick0, drop = r.uniform(0.015, 0.05), r.uniform(0.0, 0.012)
                elif x < loose * 1.2 * sev and f1 > 0.6:
                    f1 = max(f0 + 0.3, r.uniform(0.45, 0.6))                    # rota: falta la mitad alta
                elif x < loose * 1.6 * sev and pb2 - pa2 > 0.6:
                    if r.uniform() < 0.5:
                        pb2 -= r.uniform(0.1, 0.35)
                        j1 = 0.02
                    else:
                        pa2 += r.uniform(0.1, 0.35)
                        j0 = 0.02
                if pb2 - pa2 < 0.08:
                    continue
                n = max(2, int(math.ceil((pb2 - pa2) / 0.35)) + 1)
                rings = []
                for i in range(n):
                    t = i / (n - 1)
                    kk = kick0 * (1 - t) ** 2 + kick1 * t ** 2
                    dd = drop * ((1 - t) ** 2 if kick0 else t ** 2)
                    rg = ring(pa2 + (pb2 - pa2) * t, vk, f0, f1, kick=kk, drop=dd, bend=bool(kick0 or kick1))
                    if (i == 0 and j0) or (i == n - 1 and j1):
                        jj = j0 if i == 0 else j1
                        sg = 1 if i == 0 else -1
                        rg = [p + Vector((sg * r.uniform(0, jj), 0, 0)) for p in rg]
                    rings.append(rg)
                _cap_loft(mb, rings, "wood_grey")
                # clavos sobre cada pie derecho, cerca del canto bajo
                if not (kick0 or kick1):
                    for sx in studs:
                        us = sx + 0.025
                        if pa2 + 0.03 < us < pb2 - 0.03 and r.uniform() > 0.12 and f0 < 0.1:
                            fv = 0.025 / CLAP_W
                            yface = ybb + (ytb - ybb) * fv - (CLAP_TB + (CLAP_TT - CLAP_TB) * fv)
                            pop = r.uniform(0.003, 0.009) if r.uniform() < 0.05 else 0.0
                            nail(mb, (us + r.uniform(-0.008, 0.008), yface, vk + 0.025), (0, -1, -0.11), r=0.0045, h=0.0024,
                                 pop=pop, bend=r.uniform(0.0, 0.5) if pop else 0.0)
        k += 1
        vk += CLAP_EXP
    return mb
