"""circulation.py — GRUPO G2 · CIRCULACIÓN Y BORDES del kit modular BLACKISLE (Blender 5.2, bmesh, sin bpy.ops).

Escaleras de concreto (U de ida y vuelta, tramo recto de concreto o de madera), barandales (balaustres de concreto
torneados, tubo metálico soldado, madera), pasamanos de escalera, losas de balcón en voladizo, canalones de media caña
y bajantes. TODAS las funciones públicas devuelven un `MB` (el constructor lo combina con `MB.join(otro, matriz)`).

Convenciones de este módulo (además de las de common.py):
- 1 = 1 m, Z arriba, fachada principal hacia -Y. Cada docstring indica el origen y los ejes de la pieza.
- Cada `MB` devuelto lleva `mb.meta` (dict) con medidas útiles para el constructor: huella, alturas, rutas de pasamanos,
  salidas de canalón, etc. (`MB` no usa __slots__, así que el atributo extra no rompe el contrato).
- Sólidos cerrados: cada pieza es una malla cerrada independiente. Las piezas que se tocan se interpenetran sin caras
  coplanares visibles o se separan >= 2 mm. No hay láminas abiertas: `mesh_health` debe dar 0 aristas no-manifold.
- Sombreado: `MB.finish` suaviza por ángulo (30°). Por eso los redondos visibles usan >= 14 lados (13+ queda suave), los
  balaustres torneados usan 12 lados con todas las bandas ligeramente cónicas (así su ángulo diedro queda < 30° y no se
  facetan), y las varillas finas (<= 16 mm) usan 6–8 lados (facetas invisibles a esa escala).
- Aleatoriedad solo vía `rng(seed)`: misma semilla, mismo resultado.
"""
import math

import bpy  # noqa: F401,I001  (bmesh y mathutils solo existen después de importar bpy)
import bmesh  # noqa: F401
import numpy as np
from mathutils import Euler, Matrix, Vector

from kit.common import MB, rng

ZV = Vector((0.0, 0.0, 1.0))


# =====================================================================================================================
# utilidades internas
# =====================================================================================================================
def _sub(rs):
    """Generador hijo determinista (cada sub-pieza consume su propio flujo y no altera a las demás)."""
    return rng(int(rs.integers(0, 2**31 - 1)))


def _v(p):
    return Vector((float(p[0]), float(p[1]), float(p[2])))


def _ss(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


class _N1:
    """Ruido 1D suave y determinista (nudos aleatorios con interpolación smoothstep)."""

    def __init__(self, rs, x0, x1, step, amp):
        self.x0, self.step = x0 - step, step
        n = max(3, int(math.ceil((x1 - x0) / step)) + 3)
        self.v = rs.uniform(-amp, amp, n)

    def __call__(self, x):
        f = (x - self.x0) / self.step
        i = min(max(int(math.floor(f)), 0), len(self.v) - 2)
        t = _ss(f - i)
        return float(self.v[i] * (1.0 - t) + self.v[i + 1] * t)


def _frame(Z, side=None):
    """Base ortonormal (X, Y, Z) con Z dado. X = `side` proyectado (por defecto horizontal: Zmundo x Z)."""
    Z = Z.normalized()
    if side is None:
        side = ZV.cross(Z)
        if side.length < 1e-6:
            side = Vector((1.0, 0.0, 0.0))
    X = side - Z * side.dot(Z)
    if X.length < 1e-6:
        X = Vector((1.0, 0.0, 0.0)) - Z * Z.x
    X.normalize()
    return X, Z.cross(X), Z


def _mat(X, Y, Z, o):
    return Matrix(((X.x, Y.x, Z.x, o.x), (X.y, Y.y, Z.y, o.y), (X.z, Y.z, Z.z, o.z), (0.0, 0.0, 0.0, 1.0)))


def _beam(mb, a, b, sx, sy, mat, bevel=0.003, seg=1, side=None):
    """Prisma rectangular (sx a lo ancho, sy a lo alto) entre los puntos a y b, con bisel real."""
    a, b = _v(a), _v(b)
    d = b - a
    X, Y, Z = _frame(d, side)
    mb.box((-sx / 2, -sy / 2, 0.0), (sx / 2, sy / 2, d.length), mat, bevel=bevel, seg=seg, m=_mat(X, Y, Z, a))


def _loft(mb, sections, mat, cap_faces=None, caps=True):
    """Une secciones (lazos cerrados con el mismo número de puntos) con cuadriláteros y tapa los extremos.
    cap_faces: polígonos (índices del perfil) en que se descompone cada tapa; None = un solo n-gono."""
    rings = [[mb.bm.verts.new(p) for p in s] for s in sections]
    K = len(rings[0])
    for a, b in zip(rings, rings[1:]):
        for k in range(K):
            kk = (k + 1) % K
            mb.face([a[k], a[kk], b[kk], b[k]], mat)
    if caps:
        polys = cap_faces or [list(range(K))]
        for ring, rev in ((rings[0], True), (rings[-1], False)):
            for idx in polys:
                vs = [ring[i] for i in idx]
                mb.face(vs[::-1] if rev else vs, mat)
    return rings


def _fan_cap(mb, ring, center, mat, rev):
    c = mb.bm.verts.new(center)
    n = len(ring)
    for k in range(n):
        f = [ring[k], ring[(k + 1) % n], c]
        mb.face(f[::-1] if rev else f, mat)


def _sweep(mb, profile, pts, ups, mat, caps=True, end_jag=(0.0, 0.0), rs=None, fan=False):
    """Barre un perfil 2D cerrado (x -> lado = T x U, y -> U) por una polilínea 3D con vectores `up` por punto.
    `profile` puede ser una lista o un callable(i) -> lista (perfil distinto por anillo: despostillados, abolladuras).
    Ingletes correctos en los quiebres. end_jag: dientes (m) en los extremos (rotura), con tapa en abanico."""
    pts = [_v(p) for p in pts]
    n = len(pts)
    rings = []
    for i in range(n):
        if i == 0:
            T = (pts[1] - pts[0]).normalized()
        elif i == n - 1:
            T = (pts[-1] - pts[-2]).normalized()
        else:
            t0 = (pts[i] - pts[i - 1]).normalized()
            t1 = (pts[i + 1] - pts[i]).normalized()
            T = t0 + t1
            T = T.normalized() if T.length > 1e-6 else t1
        up = _v(ups[i])
        U = up - T * up.dot(T)
        U.normalize()
        S = T.cross(U)
        mit = None
        if 0 < i < n - 1:
            c = max(min(t0.dot(t1), 1.0), -0.9)
            half = math.acos(c) / 2
            if half > 1e-4:
                mit = ((t1 - t0).normalized(), 1.0 / max(math.cos(half), 0.4))
        prof = profile(i) if callable(profile) else profile
        ring = []
        for (x, y) in prof:
            o = S * x + U * y
            if mit is not None:
                o = o + mit[0] * (o.dot(mit[0]) * (mit[1] - 1.0))
            if i == 0 and end_jag[0] > 0:
                o = o + T * float(rs.uniform(0.0, end_jag[0]))
            if i == n - 1 and end_jag[1] > 0:
                o = o - T * float(rs.uniform(0.0, end_jag[1]))
            ring.append(mb.bm.verts.new(pts[i] + o))
        rings.append(ring)
    K = len(rings[0])
    for a, b in zip(rings, rings[1:]):
        for j in range(K):
            jj = (j + 1) % K
            mb.face([a[j], a[jj], b[jj], b[j]], mat)
    if caps:
        for idx, rev, sgn in ((0, True, 1.0), (n - 1, False, -1.0)):
            ring = rings[idx]
            if (end_jag[0] > 0 and idx == 0) or (end_jag[1] > 0 and idx == n - 1) or fan:
                cen = sum((v.co for v in ring), Vector()) / len(ring)
                tdir = (pts[1] - pts[0]).normalized() if idx == 0 else (pts[-1] - pts[-2]).normalized()
                jj = end_jag[0] if idx == 0 else end_jag[1]
                cen = cen + tdir * (sgn * 0.5 * jj)
                _fan_cap(mb, ring, cen, mat, rev)
            else:
                mb.face(ring[::-1] if rev else ring, mat)
    return rings


def _ptube(mb, pts, ro, ri=None, seg=16, mat="plastic", jag0=None, jag1=None, caps=True):
    """Tubo por transporte paralelo. ri: tubo hueco (pared visible en los extremos). jag0/jag1: dientes por vértice (m)
    en el extremo inicial/final, hacia dentro del tubo (bordes rotos). Ingletes en los quiebres."""
    P = [_v(p) for p in pts]
    n = len(P)
    T = []
    for i in range(n):
        if i == 0:
            t = P[1] - P[0]
        elif i == n - 1:
            t = P[-1] - P[-2]
        else:
            t = (P[i] - P[i - 1]).normalized() + (P[i + 1] - P[i]).normalized()
        T.append(t.normalized())
    ref = ZV if abs(T[0].z) < 0.9 else Vector((1.0, 0.0, 0.0))
    N = (ref - T[0] * ref.dot(T[0])).normalized()
    outer, inner = [], []
    for i in range(n):
        if i > 0:
            N = (N - T[i] * N.dot(T[i])).normalized()
        B = T[i].cross(N)
        bd, sc = None, 1.0
        if 0 < i < n - 1:
            a0 = (P[i] - P[i - 1]).normalized()
            a1 = (P[i + 1] - P[i]).normalized()
            c = max(min(a0.dot(a1), 1.0), -0.9)
            sc = 1.0 / max(math.cos(math.acos(c) / 2), 0.5)
            if sc > 1.0001:
                bd = (a1 - a0).normalized()
        ro_i, ri_i = [], []
        for k in range(seg):
            ang = 2 * math.pi * k / seg
            dv = N * math.cos(ang) + B * math.sin(ang)
            if bd is not None:
                dv = dv + bd * (dv.dot(bd) * (sc - 1.0))
            off = Vector()
            if i == 0 and jag0 is not None:
                off = T[i] * float(jag0[k])
            if i == n - 1 and jag1 is not None:
                off = -T[i] * float(jag1[k])
            ro_i.append(mb.bm.verts.new(P[i] + dv * ro + off))
            if ri is not None:
                ri_i.append(mb.bm.verts.new(P[i] + dv * ri + off))
        outer.append(ro_i)
        inner.append(ri_i)
    for i in range(n - 1):
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([outer[i][k], outer[i][kk], outer[i + 1][kk], outer[i + 1][k]], mat)
            if ri is not None:
                mb.face([inner[i][kk], inner[i][k], inner[i + 1][k], inner[i + 1][kk]], mat)
    if ri is not None:
        for i, rev in ((0, True), (n - 1, False)):
            for k in range(seg):
                kk = (k + 1) % seg
                f = [outer[i][k], outer[i][kk], inner[i][kk], inner[i][k]]
                mb.face(f[::-1] if rev else f, mat)
    elif caps:
        mb.face(list(reversed(outer[0])), mat)
        mb.face(outer[-1], mat)


def _torus(mb, c, axis, R, r, seg=8, segr=4, mat="metal_rust"):
    """Toro cerrado (cordón de soldadura, anillos)."""
    c = _v(c)
    X, Y, Z = _frame(_v(axis))
    rings = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        d = X * math.cos(a) + Y * math.sin(a)
        ctr = c + d * R
        rings.append([mb.bm.verts.new(ctr + d * (r * math.cos(2 * math.pi * j / segr)) + Z * (r * math.sin(2 * math.pi * j / segr)))
                      for j in range(segr)])
    for i in range(seg):
        ii = (i + 1) % seg
        for j in range(segr):
            jj = (j + 1) % segr
            mb.face([rings[i][j], rings[ii][j], rings[ii][jj], rings[i][jj]], mat)


def _revolve(mb, prof, m, seg=12, mat="concrete", jag_top=None, jag_bot=None, rs=None):
    """Sólido de revolución cerrado. prof: [(r, z)] de abajo arriba (en el espacio de `m`, eje Z local).
    jag_top/jag_bot: amplitud (m) de rotura en la tapa superior/inferior (anillo dentado + tapa en abanico)."""
    rings = []
    last = len(prof) - 1
    for i, (r, z) in enumerate(prof):
        ring = []
        for k in range(seg):
            a = 2 * math.pi * k / seg
            zz = z
            if i == last and jag_top:  # el dentado nunca baja del anillo anterior (sin autointersección)
                zz = max(zz - float(rs.uniform(0.0, jag_top)), prof[last - 1][1] + 0.004 if last > 0 else zz)
            if i == 0 and jag_bot:
                zz = min(zz + float(rs.uniform(0.0, jag_bot)), prof[1][1] - 0.004 if last > 0 else zz)
            ring.append(mb.bm.verts.new(m @ Vector((r * math.cos(a), r * math.sin(a), zz))))
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([a[k], a[kk], b[kk], b[k]], mat)
    for idx, rev, jag in ((0, True, jag_bot), (last, False, jag_top)):
        ring = rings[idx]
        if jag:  # fractura convexa (pico irregular), no en copa
            cz = prof[idx][1] + (-0.08 * jag if idx == last else 0.08 * jag)
            cx, cy = rs.normal(0, prof[idx][0] * 0.25), rs.normal(0, prof[idx][0] * 0.25)
            _fan_cap(mb, ring, m @ Vector((cx, cy, cz)), mat, rev)
        else:
            mb.face(ring[::-1] if rev else ring, mat)


def _chunk(mb, center, size, rs, mat="rubble", flat=1.0):
    """Trozo de escombro: caja biselada deformada y girada al azar (los triángulos aquí los exige la forma)."""
    c = MB()
    s = np.array([rs.uniform(0.7, 1.3), rs.uniform(0.55, 1.05), rs.uniform(0.3, 0.6) * flat]) * size
    c.box(tuple(-s / 2), tuple(s / 2), mat, bevel=float(min(s)) * 0.2, seg=1)
    # cada esquina (octante) se desplaza en bloque: forma irregular sin plegar las caras del bisel
    oct_off = {(a, b, d): Vector(rs.normal(0.0, 0.07, 3)) * float(min(s)) for a in (0, 1) for b in (0, 1) for d in (0, 1)}
    for v in c.bm.verts:
        v.co += oct_off[(int(v.co.x > 0), int(v.co.y > 0), int(v.co.z > 0))]
    rot = Euler((rs.normal(0, 0.2), rs.normal(0, 0.2), rs.uniform(0, 2 * math.pi))).to_matrix().to_4x4()
    mb.join(c, Matrix.Translation(_v(center)) @ rot)
    c.bm.free()


def _inset2d(P, d):
    """Desplaza un polígono 2D cerrado hacia dentro una distancia d (inglete por vértice)."""
    n = len(P)
    A = sum(P[i][0] * P[(i + 1) % n][1] - P[(i + 1) % n][0] * P[i][1] for i in range(n))
    sg = 1.0 if A > 0 else -1.0
    out = []
    for i in range(n):
        x0, y0 = P[i - 1]
        x1, y1 = P[i]
        x2, y2 = P[(i + 1) % n]
        e0 = (x1 - x0, y1 - y0)
        e1 = (x2 - x1, y2 - y1)
        l0 = math.hypot(*e0) or 1e-9
        l1 = math.hypot(*e1) or 1e-9
        n0 = (-e0[1] / l0 * sg, e0[0] / l0 * sg)
        n1 = (-e1[1] / l1 * sg, e1[0] / l1 * sg)
        mx, my = n0[0] + n1[0], n0[1] + n1[1]
        lm = math.hypot(mx, my)
        if lm < 1e-6:
            mx, my, c = n0[0], n0[1], 1.0
        else:
            mx, my = mx / lm, my / lm
            c = max(mx * n0[0] + my * n0[1], 0.4)
        out.append((x1 + mx * d / c, y1 + my * d / c))
    return out


def _round_inset(v, a, b, bev):
    """Retranqueo de la sección en v para un bisel redondeado de radio `bev` en los extremos a y b."""
    d = min(v - a, b - v)
    if bev <= 0 or d >= bev:
        return 0.0
    return bev - math.sqrt(max(bev * bev - (bev - d) ** 2, 0.0))


def _stations(a, b, step, extra=(), bev=0.0, tol=0.004):
    """Estaciones de un loft entre a y b: extremos + bisel redondeado (2 seg) + uniformes + extras (despostillados)."""
    prot = sorted({a, b} | ({a + 0.293 * bev, a + bev, b - bev, b - 0.293 * bev} if bev > 0 else set()))
    n = max(1, int(round((b - a) / step)))
    cand = [a + (b - a) * i / n for i in range(1, n)] + [x for x in extra if a + bev + tol < x < b - bev - tol]
    out = list(prot)
    for x in sorted(cand):
        if all(abs(x - y) > tol for y in out):
            out.append(x)
    return sorted(out)


class _Chip:
    """Despostillado de un canto: muesca con paredes casi verticales y fondo irregular (dientes por estación)."""

    def __init__(self, rs, key, c, hw, du, dz):
        self.key, self.c, self.hw, self.du, self.dz = key, c, hw, du, dz
        self.j1 = _N1(rs, c - hw, c + hw, max(hw / 2.5, 0.01), 0.25)
        self.j2 = _N1(rs, c - hw, c + hw, max(hw / 3.0, 0.01), 0.35)

    def f(self, x):
        d = abs(x - self.c) / self.hw
        if d >= 1.0:
            return 0.0
        return _ss((1.0 - d) / 0.2) * (0.85 + 0.6 * self.j1(x))

    def bounds(self):
        return [self.c + k * self.hw for k in (-1.0, -0.8, -0.45, 0.0, 0.45, 0.8, 1.0)]


class _Path:
    """Polilínea parametrizada por distancia HORIZONTAL acumulada (barandales, canalones)."""

    def __init__(self, pts):
        self.P = [_v(p) for p in pts]
        self.cum = [0.0]
        for a, b in zip(self.P, self.P[1:]):
            self.cum.append(self.cum[-1] + max(math.hypot(b.x - a.x, b.y - a.y), 1e-6))
        self.L = self.cum[-1]

    def seg(self, s):
        for i in range(len(self.P) - 1):
            if s <= self.cum[i + 1] + 1e-9:
                return i
        return len(self.P) - 2

    def at(self, s):
        i = self.seg(s)
        a, b = self.P[i], self.P[i + 1]
        return a.lerp(b, (s - self.cum[i]) / (self.cum[i + 1] - self.cum[i]))

    def tang(self, s):
        i = self.seg(s)
        return (self.P[i + 1] - self.P[i]).normalized()

    def hdir(self, s):
        t = self.tang(s)
        return Vector((t.x, t.y, 0.0)).normalized()

    def side(self, s):
        """Horizontal, a la derecha del sentido de avance (para un recorrido en +X: -Y = hacia fuera de la fachada)."""
        h = self.hdir(s)
        return Vector((h.y, -h.x, 0.0))

    def slope(self, s):
        i = self.seg(s)
        a, b = self.P[i], self.P[i + 1]
        return (b.z - a.z) / (self.cum[i + 1] - self.cum[i])

    def stations(self, s0, s1, step, extra=(), clear=0.0):
        """Estaciones entre s0 y s1 (incluye los vértices interiores). clear > 0: descarta las estaciones a menos de
        `clear` de un vértice interior (salvo el propio vértice): en un barrido con inglete, una sección demasiado
        cercana al quiebre cruzaría el plano de inglete (autointersección)."""
        verts = [c for c in self.cum if s0 + 1e-4 < c < s1 - 1e-4]
        ss = [s0] + verts + [s1]
        out = []
        for a, b in zip(ss, ss[1:]):
            m = max(1, int(math.ceil((b - a) / step - 1e-9)))
            out += [a + (b - a) * j / m for j in range(m)]
        out.append(s1)
        out += [x for x in extra if s0 < x < s1]
        if clear > 0:
            out = [x for x in out if x in (s0, s1) or all(abs(x - c) < 1e-6 or abs(x - c) >= clear for c in verts)]
        out.sort()
        res = [out[0]]
        for x in out[1:]:
            if x - res[-1] > 0.003:
                res.append(x)
        if res[-1] != s1:
            res[-1] = s1
        return res


def _fillet(pts, R, nseg=4):
    """Redondea los quiebres de una polilínea con arcos (Bézier cuadrática) de radio ~R (tubos doblados, codos)."""
    P = [_v(p) for p in pts]
    if len(P) < 3:
        return P
    out = [P[0]]
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        l0, l1 = (b - a).length, (c - b).length
        d0, d1 = (b - a) / l0, (c - b) / l1
        dl = math.acos(max(min(d0.dot(d1), 1.0), -1.0))
        if dl < math.radians(2.0):
            out.append(b)
            continue
        t = min(R * math.tan(dl / 2), 0.45 * l0, 0.45 * l1)
        p0, p2 = b - d0 * t, b + d1 * t
        for j in range(nseg + 1):
            u = j / nseg
            out.append(p0 * (1 - u) ** 2 + b * (2 * u * (1 - u)) + p2 * (u * u))
    out.append(P[-1])
    return out


def _bays(path, ends, post_max):
    """Estaciones de postes: extremos (retranqueados), vértices interiores y los intermedios necesarios."""
    s = [ends[0]] + path.cum[1:-1] + [path.L - ends[1]]
    out = [s[0]]
    for a, b in zip(s, s[1:]):
        m = max(1, int(math.ceil((b - a) / post_max - 1e-9)))
        out += [a + (b - a) * j / m for j in range(1, m + 1)]
    return out


def _spaced(a, b, sp, c):
    L = b - a - 2 * c
    if L < 0:
        return []
    m = int(math.floor(L / sp + 1e-9)) + 1
    off = a + c + (L - (m - 1) * sp) / 2
    return [off + i * sp for i in range(m)]


# =====================================================================================================================
# ESCALERAS
# =====================================================================================================================
def stair_riser_count(rise, lo=0.16, hi=0.18, prefer_even=True):
    """Número de contrahuellas N para un desnivel `rise` con rise/N en [lo, hi].
    Prefiere N par (tramos iguales en la U) y, entre los válidos, la contrahuella más cercana a 0,17. -> (N, contrahuella)."""
    cands = [n for n in range(1, 80) if lo - 1e-9 <= rise / n <= hi + 1e-9]
    if not cands:
        n = max(1, int(round(rise / 0.17)))
        return n, rise / n
    pool = [n for n in cands if n % 2 == 0] if prefer_even else []
    n = min(pool or cands, key=lambda k: (abs(rise / k - 0.17), k))
    return n, rise / n


def stair_u_footprint(width=1.2, floor_h=2.9, landing_depth=1.3, gap=0.15, going=0.28, core_length=None):
    """Medidas de `stair_u` sin construir geometría (para que el constructor deje el hueco en las losas).
    Devuelve dict: N, riser, n1, n2 (contrahuellas por tramo), W (ancho en Y), L (largo en X), landing_x, landing_z, landing_depth."""
    N, r = stair_riser_count(floor_h)
    n1 = (N + 1) // 2
    n2 = N - n1
    uL = 0.003 + (n1 - 1) * going
    ld = landing_depth if core_length is None else max(landing_depth, core_length - uL)
    return dict(N=N, riser=r, n1=n1, n2=n2, going=going, W=2 * width + gap, L=uL + ld, landing_x=uL,
                landing_z=n1 * r, landing_depth=ld)


def _flight(mb, M, n, r, g, v0, v1, rs, *, bottom="floor", top="landing", u_end=None, z_clip=-0.19, t_w=0.15,
            nb=0.018, bev=0.012, open_vs=(), wall_v=None, broken=0.1, wear=0.009, walk_v=None, foot_back=0.10,
            top_depth=0.30, top_thick=0.20, mat="concrete", spalls=()):
    """Tramo monolítico de concreto como loft a lo ancho (v). Perfil (u, z) local: contrahuella k en u=(k-1)g, huella k
    a z=k·r, losa inclinada (cara inferior) paralela a la línea de narices con espesor t_w y marcas reales de tablas de
    encofrado (escalones de 1,5–3 mm entre tablas).
    bottom: 'floor' (arranca del canto de una losa: cara frontal vertical en u=0), 'landing' (pie embebido en un
            descanso cuya cara superior está en z=0) o 'solid' (macizo apoyado en el suelo).
    top:    'landing' (la última contrahuella la forma el canto del descanso; el tramo penetra en él hasta u_end),
            'slab' (la última contrahuella la forma el canto de la losa del piso: la última huella llega a u_end) o
            'free' (incluye la última contrahuella y una meseta de top_depth).
    Desgaste: huellas gastadas en la línea de paso (walk_v), narices despostilladas (más en los bordes libres open_vs),
    grietas transversales, variación de ±3–5 mm entre peldaños, desconchados de la arista inferior (spalls) y arena
    acumulada en los rincones del lado del muro (wall_v).
    M: matriz local->mundo con u=x, v=y, z=z. Devuelve info (narices, despostillados, función de la losa inferior)."""
    kc = t_w / math.cos(math.atan2(r, g))

    def zs(u):
        return u * r / g - kc

    n_draw = n - 1 if top in ("landing", "slab") else n
    solid = bottom == "solid"
    P, I, sb = [], {}, {}
    TOP = ("A", "B", "C", "D", "E", "F", "G", "X1", "X2", "X3")

    def add(u, z, role, k=0):
        I[(role, k)] = len(P)
        P.append((u, z, role, k))

    # variación constructiva entre peldaños (encofrado a mano)
    du_k = {k: (0.0 if k == 1 else float(rs.normal(0.0, 0.004))) for k in range(1, n_draw + 2)}
    dz_k = {k: (0.0 if k in (0, n_draw) else float(rs.normal(0.0, 0.0025))) for k in range(0, n_draw + 1)}
    cracks = {}
    for k in range(1, n_draw + (0 if top == "free" else 0)):
        if rs.random() < min(0.5, broken * 1.8):
            a_ = rs.uniform(v0, v0 + 0.5 * (v1 - v0))
            b_ = rs.uniform(a_ + 0.3 * (v1 - v0), v1 + 0.2)
            cracks[k] = (rs.uniform(0.19, 0.245), a_, b_, rs.uniform(0.003, 0.007), _N1(rs, v0, v1, 0.12, 0.012))

    if bottom == "landing":
        add(-foot_back, max(z_clip, zs(-foot_back)), "Q0")
        add(-foot_back, -0.02, "Q1")
    for k in range(1, n_draw + 1):
        uk = (k - 1) * g + du_k[k]
        z0, z1 = (k - 1) * r + dz_k[k - 1], k * r + dz_k[k]
        if k == 1 and bottom != "floor":
            z0 = -0.02
        add(uk, z0, "A", k)
        add(uk, z0 + 0.5 * (z1 - nb - z0), "B", k)
        add(uk, z1 - nb, "C", k)
        add(uk + 0.293 * nb, z1 - 0.293 * nb, "D", k)
        add(uk + nb, z1, "E", k)
        add(uk + 0.085, z1, "F", k)
        add(uk + 0.55 * g, z1, "G", k)
        if k in cracks:
            uc = (k - 1) * g + cracks[k][0]
            add(uc - 0.0016, z1, "X1", k)
            add(uc, z1, "X2", k)
            add(uc + 0.0016, z1, "X3", k)
    zt = n_draw * r
    ue = (n - 1) * g + top_depth if top == "free" else u_end
    add(ue, zt, "T1")
    ulim = ue
    if solid:
        add(ue, -0.02, "T2")
    elif top in ("free", "slab"):  # meseta / llegada alargada: fondo horizontal (sin canto en filo de navaja)
        zb = zt - top_thick
        uk_ = (zb + kc) * g / r
        if uk_ < ue - 0.03:
            add(ue, zb, "T2")
            add(uk_, zb, "K")
            ulim = uk_
        else:
            add(ue, zs(ue), "T2")
    else:
        add(ue, zs(ue), "T2")
    # tablas de encofrado (anchos 9–15 cm) con desfase alterno entre tablas
    joints, u = [], -foot_back - 0.05
    while u < ulim + 0.2:
        u += rs.uniform(0.09, 0.15)
        joints.append(u)
    boff = [((-1) ** j) * rs.uniform(0.0015, 0.0035) for j in range(len(joints) + 1)]

    def board_off(u):
        j = int(np.searchsorted(joints, u))
        return boff[j]

    for k in range(n_draw, 0, -1):
        uk = (k - 1) * g + du_k[k]
        cend = ulim if k == n_draw else k * g + du_k[k + 1]
        sb[k] = []
        if not solid:
            for j in range(len(joints) - 1, -1, -1):
                uj = joints[j]
                if uk + 0.012 < uj < cend - (0.05 if k == n_draw else 0.012):  # nada junto a la esquina aguda final
                    sb[k].append(len(P))
                    P.append((uj + 0.002, zs(uj + 0.002) + boff[j + 1], "SB", k))
                    sb[k].append(len(P))
                    P.append((uj, zs(uj) + boff[j], "SB", k))
        if not (solid and k == 1):
            add(uk, -0.02 if solid else zs(uk) + board_off(uk), "S", k)
    if bottom == "landing" and zs(-foot_back) < z_clip:
        add((z_clip + kc) * g / r, z_clip, "UC")

    # tapas laterales descompuestas en columnas (un polígono por peldaño) en lugar de un n-gono dentado
    cols = []
    if bottom == "landing":
        cols.append([I["Q0", 0], I["Q1", 0], I["A", 1], I["S", 1]] + ([I["UC", 0]] if ("UC", 0) in I else []))
    for k in range(1, n_draw + 1):
        top_i = [i for i, p in enumerate(P) if p[3] == k and p[2] in TOP]
        if k < n_draw:
            top_i.append(I["A", k + 1])
            bot = [I["S", k + 1]]
        else:
            top_i += [I["T1", 0], I["T2", 0]] + ([I["K", 0]] if ("K", 0) in I else [])
            bot = []
        bot += sb[k]
        if ("S", k) in I:
            bot.append(I["S", k])
        cols.append(top_i + bot)

    # imperfección: nivel de cada huella y plomo de cada contrahuella varían suavemente a lo ancho
    tn = {k: _N1(rs, v0, v1, 0.3, 0.0022) for k in range(0, n_draw + 1)}
    rn = {k: _N1(rs, v0, v1, 0.3, 0.002) for k in range(1, n_draw + 1)}
    chips = []
    for k in range(1, n_draw + 1):
        base_p = 0.1 if broken > 0 else 0.0  # edificio abandonado: aun con poco daño hay narices mordidas
        if rs.random() < base_p + broken * 0.9:
            hw = rs.uniform(0.04, 0.13)
            chips.append(_Chip(rs, k, rs.uniform(v0 + hw, v1 - hw), hw, rs.uniform(0.02, 0.05), rs.uniform(0.02, 0.05)))
        for ov in open_vs:
            if rs.random() < 1.3 * base_p + broken * 1.6:
                hw = rs.uniform(0.05, 0.12)
                big = rs.random() < broken * 1.5
                vc = ov + hw * rs.uniform(0.1, 0.5) * (1 if abs(ov - v0) < abs(ov - v1) else -1)
                chips.append(_Chip(rs, k, vc, hw, rs.uniform(0.03, 0.11 if big else 0.06), rs.uniform(0.03, 0.085 if big else 0.055)))
    for c in chips:
        c.j3 = _N1(rs, c.c - c.hw, c.c + c.hw, max(c.hw / 7.0, 0.006), 0.35)
    spj = [_N1(rs, -1.0, 6.0, 0.06, 0.3) for _ in spalls]

    def prof(v):
        Q = [[p[0], p[1]] for p in P]
        wl = 0.0
        if walk_v is not None:
            wl = wear * math.exp(-((v - walk_v) / (0.32 * (v1 - v0))) ** 2)
        for i, (u, z, ro, k) in enumerate(P):
            if ro == "A":
                Q[i][0] += rn[k](v)
                if k > 1:
                    Q[i][1] += tn[k - 1](v)
            elif ro == "B":
                Q[i][0] += rn[k](v)
            elif ro in ("C", "D", "E", "F", "G", "X1", "X2", "X3"):
                Q[i][1] += tn[k](v)
                if ro == "C":
                    Q[i][0] += rn[k](v)
                    Q[i][1] -= 0.3 * wl
                elif ro == "D":
                    Q[i][0] += 0.5 * rn[k](v) + 0.5 * wl
                    Q[i][1] -= 0.5 * wl
                elif ro == "E":
                    Q[i][0] += 0.6 * wl
                    Q[i][1] -= 0.4 * wl
                elif ro == "F":
                    Q[i][1] -= 0.7 * wl
                elif ro == "G":
                    Q[i][1] -= wl
                else:  # grieta: surco en V que serpentea y se cierra en sus extremos
                    _, a_, b_, dep, wob = cracks[k]
                    e = _ss((v - a_) / 0.06) * _ss((b_ - v) / 0.06)
                    Q[i][0] += wob(v)
                    if ro == "X2":
                        Q[i][1] -= dep * e
                        Q[i][0] += 0.0008 * e
            elif ro == "T1":
                Q[i][1] += tn[n_draw](v)
            elif ro in ("S", "SB", "K", "T2"):
                for sp, jj in zip(spalls, spj):
                    ev = 1.0 - _ss((abs(v - sp["ov"]) - 0.8 * sp["wv"]) / (0.2 * sp["wv"]))
                    eu = _ss((u - sp["ua"]) / 0.05) * _ss((sp["ub"] - u) / 0.05)
                    if ev > 0 and eu > 0:
                        Q[i][1] += sp["depth"] * ev * eu * (0.8 + jj(u + 3.1 * v))
        for k in range(1, n_draw + 1):
            best, fb = None, 0.0
            for c in chips:
                if c.key == k:
                    f = c.f(v)
                    if f > fb:
                        best, fb = c, f
            if best is None:
                continue
            du = best.du * (1.0 + best.j2(v))
            dz = best.dz * (1.0 - 0.6 * best.j2(v))
            j3 = best.j3(v)
            uk = Q[I["C", k]][0]
            zk = Q[I["E", k]][1]
            tg = {"C": (uk + (0.1 + 0.3 * j3) * du, zk - dz * (1.0 + 0.4 * best.j1(v))),
                  "D": (uk + (0.6 + 0.9 * j3) * du, zk - (0.62 - 0.9 * j3) * dz),
                  "E": (uk + du * (1.0 - 0.5 * j3), zk - (0.1 + 0.3 * abs(j3)) * dz)}
            iF, iB = I["F", k], I["B", k]
            if tg["E"][0] + 0.015 > Q[iF][0]:
                tg["F"] = (tg["E"][0] + 0.015, zk - 0.04 * dz)
            if tg["C"][1] - 0.012 < Q[iB][1]:
                tg["B"] = (Q[iB][0], tg["C"][1] - 0.012)
            for ro, (tu, tz) in tg.items():
                j = I[ro, k]
                Q[j][0] += (tu - Q[j][0]) * fb
                Q[j][1] += (tz - Q[j][1]) * fb
        d = _round_inset(v, v0, v1, bev)
        return _inset2d(Q, d) if d > 0 else Q

    extra = [c.c + c.hw * t for c in chips for t in (-1.0, -0.8, -0.3, 0.3, 0.8, 1.0)]
    for sp in spalls:
        extra += [sp["ov"] + s * sp["wv"] * k for k in (0.8, 1.0) for s in (-1, 1)]
    secs = []
    for v in _stations(v0, v1, 0.15, extra, bev=bev, tol=0.006):
        secs.append([M @ Vector((q[0], v, q[1])) for q in prof(v)])
    _loft(mb, secs, mat, cap_faces=cols)
    # arena y polvo acumulados en el rincón huella-contrahuella del lado del muro
    if wall_v is not None:
        sgn = 1.0 if abs(wall_v - v0) < abs(wall_v - v1) else -1.0
        for k in range(1, n_draw):
            if rs.random() < 0.55:
                uc = k * g + du_k[k + 1]
                zf = k * r + dz_k[k]
                _sand_wedge(mb, M, uc, zf, wall_v, wall_v + sgn * rs.uniform(0.15, 0.45), rs, wd=rs.uniform(0.04, 0.09),
                            hd=rs.uniform(0.015, 0.035))
    return dict(zs=zs, kc=kc, chips=[(c.key, c.c, c.du, c.dz) for c in chips], n_draw=n_draw, u_soffit=(
                (-foot_back if bottom == "landing" else 0.0), ulim),
                nosings=[((k - 1) * g + du_k[k], k * r + dz_k[k]) for k in range(1, n_draw + 1)])


def _sand_wedge(mb, M, uc, zf, va, vb, rs, wd=0.06, hd=0.025, dirn=-1.0, lens=False, mat="sand", bk=None):
    """Cuña de arena/polvo apoyada en una cara vertical (u=uc) sobre un piso (z=zf), a lo largo de v de va a vb.
    Gruesa junto a va y se hunde en el piso hacia vb (lens=True: gruesa al centro y hundida en ambos extremos).
    dirn: hacia dónde se extiende sobre el piso (-1 = -u). El borde trasero entra 3 mm en la cara vertical."""
    nn = _N1(rs, min(va, vb), max(va, vb), 0.05, 0.22)
    n = max(5, int(abs(vb - va) / 0.035) + 1)
    bk_, zb0 = float(rs.uniform(0.002, 0.007)), float(rs.uniform(0.004, 0.009))  # empotramiento trasero e inferior
    bk = bk_ if bk is None else bk
    secs = []
    for i in range(n):
        t = i / (n - 1)
        v = va + (vb - va) * t
        e = math.sin(math.pi * t) ** 0.6 if lens else (1.0 - t) ** 0.6
        e = max(e, 0.25) * (1.0 + nn(v))
        w_, h_ = wd * e, hd * e
        if i == n - 1 or (lens and i == 0):
            h_ = -0.002  # el extremo se hunde en el piso (sin corte vertical)
        pr = [(uc + dirn * w_, zf - zb0), (uc - dirn * bk, zf - zb0), (uc - dirn * bk, zf + h_),
              (uc + dirn * w_ * 0.35, zf + h_ * 0.55), (uc + dirn * w_ * 0.75, zf + h_ * 0.15 - 0.0015)]
        secs.append([M @ Vector((p[0], v, p[1])) for p in pr])
    _loft(mb, secs, mat)


def _landing(mb, M, L, v0, v1, lt, rs, *, push_from=None, push=0.03, nb=0.018, bev=0.012, broken=0.1, chip_vmax=None,
             mat="concrete"):
    """Descanso: loft a lo ancho (v) de un perfil (u, z) con u in [0, L] (u=0 borde frontal) y z in [-lt, 0].
    Para v > push_from el canto frontal se adelanta `push` (queda dentro del pie del tramo que arranca ahí: sin caras
    coplanares y sin ranura en la base de su primera contrahuella)."""
    b = 0.02
    P, I = [], {}

    def add(u, z, ro):
        I[ro] = len(P)
        P.append((u, z, ro))

    add(0.0, -lt + b, "FB0")
    add(0.293 * b, -lt + 0.293 * b, "FB1")
    add(b, -lt, "FB2")
    nbd = max(1, int(round((L - 2 * b) / 0.13)))
    for j in range(1, nbd):
        P.append((b + (L - 2 * b) * j / nbd, -lt + (0.0015 if j % 2 else -0.001), "BD"))
    add(L - b, -lt, "BB0")
    add(L - 0.293 * b, -lt + 0.293 * b, "BB1")
    add(L, -lt + b, "BB2")
    add(L, -b, "BT0")
    add(L - 0.293 * b, -0.293 * b, "BT1")
    add(L - b, 0.0, "BT2")
    # grietas de retracción paralelas al canto (surco en V que serpentea y se cierra en los extremos)
    lcr = []
    for ci in range(int(rs.poisson(0.5 + broken * 3.0))):
        uc = float(rs.uniform(0.22, L - 0.2))
        if abs(uc - 0.55 * L) < 0.02 or any(abs(uc - q[0]) < 0.06 for q in lcr):
            continue
        a_ = float(rs.uniform(v0, v0 + 0.55 * (v1 - v0)))
        lcr.append((uc, a_, float(rs.uniform(a_ + 0.3 * (v1 - v0), v1 + 0.3)), float(rs.uniform(0.003, 0.007)),
                    _N1(rs, v0, v1, 0.12, 0.014), ci))
    tops = [(0.55 * L, "G")] + [(q[0] + d, f"X{k}_{q[5]}") for q in lcr for k, d in ((1, 0.0016), (2, 0.0), (3, -0.0016))]
    for u_, ro_ in sorted(tops, reverse=True):
        add(u_, 0.0, ro_)
    lcr = {q[5]: q for q in lcr}
    add(0.085, 0.0, "F")
    add(nb, 0.0, "E")
    add(0.293 * nb, -0.293 * nb, "D")
    add(0.0, -nb, "C")
    add(0.0, -0.5 * lt, "B")
    vmax = chip_vmax if chip_vmax is not None else v1
    chips = []
    nch = rs.poisson(broken * 4.0 * max(vmax - v0, 0.1))
    for _ in range(nch):
        hw = rs.uniform(0.04, 0.12)
        chips.append(_Chip(rs, 0, rs.uniform(v0 + hw, max(vmax - hw * 0.5, v0 + hw + 0.01)), hw, rs.uniform(0.02, 0.05),
                           rs.uniform(0.02, 0.05)))
    tnz = _N1(rs, v0, v1, 0.4, 0.0015)

    def prof(v):
        Q = [[p[0], p[1]] for p in P]
        pushed = push_from is not None and v > push_from + 0.001
        for i, (u, z, ro) in enumerate(P):
            if ro in ("G", "F", "E", "D", "BT2") or ro[0] == "X":
                Q[i][1] += tnz(v)
            if ro[0] == "X":
                _, a_, b_, dep, wob, _ = lcr[int(ro.split("_")[1])]
                e = _ss((v - a_) / 0.06) * _ss((b_ - v) / 0.06)
                Q[i][0] += wob(v)
                if ro[1] == "2":
                    Q[i][1] -= dep * e
                    Q[i][0] += 0.0008 * e
            if pushed and u <= 0.09:
                Q[i][0] -= push
        if not pushed:
            best, fb = None, 0.0
            for c in chips:
                f = c.f(v)
                if f > fb:
                    best, fb = c, f
            if best is not None:
                du = best.du * (1.0 + best.j2(v))
                dz = best.dz * (1.0 - 0.6 * best.j2(v))
                tg = {"C": (0.1 * du, -dz), "D": (0.6 * du, -0.62 * dz), "E": (du, -0.1 * dz)}
                if du + 0.015 > 0.085:
                    tg["F"] = (du + 0.015, -0.04 * dz)
                for ro, (tu, tz) in tg.items():
                    j = I[ro]
                    Q[j][0] += (tu - Q[j][0]) * fb
                    Q[j][1] += (tz - Q[j][1]) * fb
        d = _round_inset(v, v0, v1, bev)
        return _inset2d(Q, d) if d > 0 else Q

    extra = [x for c in chips for x in c.bounds()]
    for (_, a_, b_, _, _, _) in lcr.values():  # estaciones para que la grieta serpentee y se cierre suave
        extra += [a_, a_ + 0.03, a_ + 0.06, b_ - 0.06, b_ - 0.03, b_] + list(np.arange(a_ + 0.1, b_ - 0.06, 0.09))
    if push_from is not None:
        extra += [push_from - 0.002, push_from + 0.006]
    secs = [[M @ Vector((q[0], v, q[1])) for q in prof(v)] for v in _stations(v0, v1, 0.3, extra, bev=bev, tol=0.003)]
    _loft(mb, secs, mat)


def _rebar_run(mb, pts, rs, r=0.005, bulge=0.004):
    """Varilla corrugada aproximada: tubo de 6 lados con leve ondulación (corrosión, pandeo)."""
    P = [_v(p) for p in pts]
    out = [P[0]]
    for a, b in zip(P, P[1:]):
        m = max(1, int((b - a).length / 0.06))
        for j in range(1, m + 1):
            q = a.lerp(b, j / m)
            if j < m:
                q = q + Vector(rs.normal(0.0, bulge * 0.35, 3))
            out.append(q)
    _ptube(mb, out, r, None, seg=6, mat="metal_rust")


def stair_u(width=1.2, floor_h=2.9, landing_depth=1.3, gap=0.15, seed=0, broken=0.1, *, going=0.28, waist=0.15,
            core_length=None, rail=None, rail_h=0.95, debris=True):
    """Escalera de concreto en U (ida y vuelta) para UN entrepiso, dentro de un núcleo. Devuelve MB.

    ORIGEN: esquina inferior izquierda del núcleo = (0, 0, 0): x=0 es el canto del hueco por donde se entra/sale, y=0 el
    muro lateral del tramo 1, z=0 el nivel de piso terminado de abajo.
    HUELLA (hueco que el constructor deja en la losa de arriba, en z=floor_h):
        X in [0, L]  con  L = 0,003 + (n1-1)·going + landing_depth      (2,24 + 0,003 + 1,30 = 3,543 m con los valores por defecto)
        Y in [0, W]  con  W = 2·width + gap                            (2,55 m por defecto)
    Usa `stair_u_footprint(...)` para obtener L, W, N, contrahuella, etc. sin construir geometría.
    - N contrahuellas con floor_h/N en [0,16; 0,18] (prefiere N par: 2,9 m -> 18 x 0,161; 3,4 m -> 20 x 0,170). Huella 0,28.
    - Tramo 1 en Y in [0, width] sube hacia +X desde x=0 (z=0) hasta el descanso (x >= landing_x, z = n1·r).
      Tramo 2 en Y in [width+gap, W] vuelve hacia -X y llega a z=floor_h en x≈0, junto al canto del hueco.
    - La última contrahuella del tramo 2 la forma el CANTO DE LA LOSA de arriba (hueco en x=0); el pie del tramo 1 baja
      hasta la cara inferior de esa losa (x in [0,003; 0,3], z hasta -0,18): con losa de 0,20 queda oculto o empotrado.
    - Empotramientos: tramos 2 cm dentro de los muros laterales (y<0, y>W) y descanso 3 cm dentro de los muros (y, x=L).
    - APILADO: coloca una por piso con Matrix.Translation((x0, y0, z_piso)); los módulos no se solapan (el pie del tramo 1
      está del lado y<width y la llegada del tramo 2 del lado y>width+gap). En PB el pie queda bajo el firme.
    - core_length: alarga el descanso para que todas las plantas compartan el mismo L (p. ej. PB de 3,4 m y pisos de 2,9).
    - broken: probabilidad de despostillados en narices (más en el canto libre del ojo), losa inferior desconchada con
      varillas expuestas (si broken >= 0,2) y escombro suelto en huellas/descanso. Con broken > 0 siempre hay un mínimo de
      narices mordidas (~10 % por peldaño), grietas en el descanso y gravilla barrida contra el muro: un módulo no se ve
      nunca como maqueta limpia. Coste orientativo: ~18-20k triángulos con broken 0,1-0,15; ~30-35k con broken 0,4 y
      barandal de tubo; ~40-46k con balaustrada de concreto (cada despostillado añade estaciones a lo ancho del tramo).
    - rail: None | 'tube_metal' | 'wood' | 'baluster_concrete' -> pasamanos en el borde del ojo (stair_railing). Con
      'baluster_concrete' el giro del descanso lleva un único pilar de arranque ancho con remate.
    meta: N, riser, n1, n2, L, W, landing_z, landing_x, rail_path (polilínea de base del pasamanos del ojo)."""
    rs = rng(seed)
    fp = stair_u_footprint(width, floor_h, landing_depth, gap, going=going, core_length=core_length)
    N, r, n1, n2 = fp["N"], fp["riser"], fp["n1"], fp["n2"]
    g, eps, emb, embl = going, 0.003, 0.02, 0.03
    W, L, uL, zl = fp["W"], fp["L"], fp["landing_x"], fp["landing_z"]
    ld = L - uL
    kc = waist / math.cos(math.atan2(r, g))
    lt = max(0.20, kc + 0.03)
    mb = MB()

    def spalls_for(ov, nn, sgn):
        out = []
        span = (nn - 1) * g
        for _ in range(3):
            if rs.random() > min(0.9, broken * 2.5) or len(out) >= 1 + int(broken > 0.3):
                continue
            ua = rs.uniform(0.3, max(0.35, span - 0.6))
            big = broken >= 0.2 and rs.random() < 0.8
            sp_ = dict(ov=ov, wv=rs.uniform(0.05, 0.10), ua=ua, ub=ua + rs.uniform(0.25, 0.7 if big else 0.4),
                       depth=rs.uniform(0.03, 0.045) if big else rs.uniform(0.012, 0.022), sgn=sgn)
            if any(sp_["ua"] < q["ub"] + 0.3 and q["ua"] < sp_["ub"] + 0.3 for q in out):
                continue  # dos desconchados solapados duplicarían las varillas expuestas
            out.append(sp_)
        return out

    # --- tramo 1 (sube hacia +X)
    M1 = Matrix.Translation((eps, 0.0, 0.0))
    ue1 = (zl - lt + 0.012 + kc) * g / r
    ue1 = min(max(ue1, (n1 - 1) * g + 0.06) + 0.005, (n1 - 1) * g + ld - 0.08)
    sp1 = spalls_for(width, n1, -1)
    f1 = _flight(mb, M1, n1, r, g, -emb, width, _sub(rs), bottom="floor", top="landing", u_end=ue1, t_w=waist,
                 open_vs=(width,), wall_v=-emb, broken=broken, walk_v=width - 0.35, spalls=sp1)
    # --- tramo 2 (espejo en X: u' crece hacia -X)
    M2 = Matrix(((-1.0, 0.0, 0.0, uL), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, zl), (0.0, 0.0, 0.0, 1.0)))
    sp2 = spalls_for(width + gap, n2 + 1, 1)
    f2 = _flight(mb, M2, n2, r, g, width + gap, W + emb, _sub(rs), bottom="landing", top="slab", u_end=uL - eps,
                 z_clip=-lt + 0.012, t_w=waist, open_vs=(width + gap,), wall_v=W + emb, broken=broken,
                 walk_v=width + gap + 0.35, spalls=sp2)
    # --- descanso
    ML = Matrix.Translation((uL, 0.0, zl))
    rl = _sub(rs)
    _landing(mb, ML, ld + embl, -embl, W + embl, lt, rl, push_from=width + gap + 0.01, broken=broken,
             chip_vmax=width + gap)
    # arena contra el muro del fondo y en los rincones del descanso
    for iw in range(int(rl.integers(1, 4))):
        a = rl.uniform(0.0, W - 0.5)
        _sand_wedge(mb, Matrix(), uL + ld, zl, a, a + rl.uniform(0.3, 0.9), rl, wd=rl.uniform(0.06, 0.14),
                    hd=rl.uniform(0.02, 0.045), lens=True, bk=0.002 + 0.0015 * iw)
    for yw, sg_ in ((0.0, 1.0), (W, -1.0)):
        if rl.random() < 0.7:
            Mr = Matrix(((0.0, 1.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
            _sand_wedge(mb, Mr, yw, zl, uL + ld, uL + ld - rl.uniform(0.25, 0.7), rl, wd=rl.uniform(0.05, 0.1),
                        hd=rl.uniform(0.015, 0.035), dirn=sg_)

    # --- varillas expuestas donde se desconchó la losa inferior
    rr = _sub(rs)
    for sps, f, Mx in ((sp1, f1, M1), (sp2, f2, M2)):
        for sp in sps:
            if sp["depth"] < 0.028:
                continue
            zsf = f["zs"]
            cover = min(0.026, sp["depth"] * 0.7)
            # las varillas quedan DENTRO del tramo: no asoman por el extremo del tramo ni bajo la losa de llegada
            u_lo, u_hi = f["u_soffit"][0] + 0.06, f["u_soffit"][1] - 0.06
            ra, rb_ = max(sp["ua"] - 0.12, u_lo), min(sp["ub"] + 0.12, u_hi)
            if rb_ - ra < 0.15:
                continue
            for dv in (0.035, 0.11):
                v = sp["ov"] + sp["sgn"] * dv
                us = np.linspace(ra, rb_, 6)
                _rebar_run(mb, [Mx @ Vector((u, v, zsf(u) + cover)) for u in us], rr)
            for u in np.arange(max(sp["ua"] + 0.05, u_lo), min(sp["ub"] - 0.02, u_hi), 0.2):
                a = Mx @ Vector((u, sp["ov"] + sp["sgn"] * 0.012, zsf(u) + cover + 0.011))
                b = Mx @ Vector((u, sp["ov"] + sp["sgn"] * 0.2, zsf(u) + cover + 0.011))
                _rebar_run(mb, [a, b], rr, r=0.004)

    # --- escombro suelto (trozos desprendidos de los despostillados)
    if debris:
        rd = _sub(rs)
        lo_v, hi_v = (0.0, width + gap), (width, W)
        for f, Mx in ((f1, M1), (f2, M2)):
            for (k, vc, du, dz) in f["chips"]:
                for _ in range(int(rd.integers(1, 4))):
                    kk = max(1, k - int(rd.integers(0, 2)))
                    s = rd.uniform(0.02, 0.05) * (0.6 + 6 * du)
                    vv = min(max(vc + rd.normal(0, 0.06), lo_v[Mx is M2] + 0.04), hi_v[Mx is M2] - 0.04)
                    p = Mx @ Vector(((kk - 1) * g + rd.uniform(0.1, 0.25), vv, kk * r + 0.12 * s))
                    _chunk(mb, p, s, rd)
        for _ in range(int(rd.integers(2, 6))):
            s = rd.uniform(0.02, 0.06)
            y = rd.choice([rd.uniform(0.02, 0.15), rd.uniform(W - 0.15, W - 0.02)])
            _chunk(mb, (uL + rd.uniform(ld * 0.4, ld - 0.08), y, zl + 0.12 * s), s, rd)
        # gravilla y esquirlas sueltas (también con poco daño): el paso las barre contra el muro y los rincones
        for f, Mx, wv, sg in ((f1, M1, 0.0, 1.0), (f2, M2, W, -1.0)):
            for _ in range(int(rd.poisson(6 + 16 * broken))):
                k = int(rd.integers(1, f["n_draw"] + 1))
                vv = wv + sg * (rd.uniform(0.02, 0.28) if rd.random() < 0.7 else rd.uniform(0.28, width - 0.12))
                s = rd.uniform(0.008, 0.026)
                _chunk(mb, Mx @ Vector(((k - 1) * g + rd.uniform(0.1, 0.25), vv, k * r + 0.08 * s)), s, rd, flat=0.7)
        for _ in range(int(rd.poisson(8 + 12 * broken))):
            s = rd.uniform(0.008, 0.03)
            y = rd.uniform(0.03, W - 0.03) if rd.random() < 0.4 else rd.choice([rd.uniform(0.02, 0.2), rd.uniform(W - 0.2, W - 0.02)])
            _chunk(mb, (uL + rd.uniform(0.12, ld - 0.04), y, zl + 0.08 * s), s, rd, flat=0.7)

    # --- pasamanos del ojo (opcional)
    ya, yb = width - 0.055, width + gap + 0.055
    # vértices sobre huellas (cada <= 4 peldaños) para que todos los postes apoyen en una huella
    ks1 = sorted(set(list(range(1, n1, 4)) + [n1 - 1]))
    ks2 = sorted(set(list(range(1, n2, 4)) + [n2 - 1]))
    path = [(eps + (k - 1) * g + 0.07, ya, k * r) for k in ks1] + [(uL + 0.07, ya, zl), (uL + 0.07, yb, zl)] + \
           [(uL - (k - 1) * g - 0.07, yb, zl + k * r) for k in ks2]
    if rail:
        mb.join(stair_railing(path, h=rail_h, kind=rail, seed=int(rs.integers(1 << 30))))
    mb.meta = dict(fp, kind="stair_u", footprint=(L, W), floor_h=floor_h, rail_path=path, landing_thickness=lt)
    return mb


def stair_straight(width=1.2, rise_total=1.0, seed=0, *, kind="concrete", stringers=None, going=None, broken=0.1,
                   top_depth=0.30, solid=None, rail=None, rail_side="both"):
    """Tramo recto (PB, accesos, cabañas). Sube hacia +X; ancho en Y in [0, width]; origen (0,0,0) = pie de la primera
    contrahuella en el borde y=0, a nivel de suelo.
    kind='concrete': monolítico. Si rise_total <= 1,25 (o solid=True) es macizo sobre el terreno; si no, losa inclinada
        con cara inferior. Incluye la última contrahuella y una meseta de `top_depth` (llega a x = (N-1)·going + top_depth).
        stringers=True añade zancas laterales de concreto (cantos 0,12 que sobresalen 0,12 sobre la línea de narices).
    kind='wood': contrahuellas abiertas, huellas de tabla de 0,035, clavos, dado de concreto al pie y poste intermedio si
        rise_total > 1,6. stringers=None/True: zancas cerradas de tablón 0,05x0,28 a cada lado con huellas embutidas sobre
        listones; stringers=False: zancas recortadas en diente de sierra bajo las huellas (2 o 3) y huellas que vuelan.
        La última contrahuella la forma el canto de la terraza en x = (N-1)·going (ahí terminan las zancas).
    broken: peldaños despostillados (concreto) / tablas faltantes, rotas o hundidas (madera).
    rail: None | 'tube_metal' | 'wood' | 'baluster_concrete'; rail_side: 'left' (y=0), 'right' (y=width) o 'both'.
    meta: N, riser, going, top_x, top_z, rail_paths."""
    rs = rng(seed)
    mb = MB()
    if kind == "wood":
        info = _stair_wood(mb, width, rise_total, rs, going or 0.26, broken, stringers is not False)
    else:
        g = going or 0.28
        N, r = stair_riser_count(rise_total, prefer_even=False)
        solid = rise_total <= 1.25 if solid is None else solid
        ov = (0.0, width)
        f = _flight(mb, Matrix(), N, r, g, 0.0, width, _sub(rs), bottom="solid" if solid else "floor", top="free",
                    top_depth=top_depth, open_vs=() if stringers else ov, broken=broken, walk_v=width * 0.5)
        ue = (N - 1) * g + top_depth
        if stringers:
            zs = f["zs"]
            kc = f["kc"]
            zb_top = N * r - 0.20
            uk_ = (zb_top + kc) * g / r
            if solid:
                bot = [(0.0, -0.05), (ue, -0.05)]
            elif uk_ < ue - 0.03:
                bot = [(0.0, zs(0.0) - 0.08), (uk_, zb_top - 0.08), (ue, zb_top - 0.08)]
            else:
                bot = [(0.0, zs(0.0) - 0.08), (ue, zs(ue) - 0.08)]
            prof = bot + [(ue, N * r + 0.12), ((N - 1) * g, N * r + 0.12), (0.0, r + 0.12)]
            for va, vb in ((-0.12, 0.012), (width - 0.012, width + 0.12)):
                secs = []
                for v in _stations(va, vb, 0.2, bev=0.015):
                    d = _round_inset(v, va, vb, 0.015)
                    q2 = _inset2d(prof, d) if d > 0 else prof
                    secs.append([Vector((q[0], v, q[1])) for q in q2])
                _loft(mb, secs, "concrete")
        info = dict(N=N, riser=r, going=g, top_x=ue, top_z=rise_total,
                    rail_paths={key: [((k - 1) * g + 0.07, y, k * r) for k in sorted(set(list(range(1, N + 1, 4)) + [N]))] +
                                [(ue - 0.05, y, N * r)] for key, y in (("left", 0.06), ("right", width - 0.06))})
        if stringers:
            for key, y in (("left", -0.054), ("right", width + 0.054)):
                info["rail_paths"][key] = [(0.06, y, 2 * r + 0.12 - 0.06 * r / g), ((N - 1) * g, y, N * r + 0.12),
                                           (ue - 0.06, y, N * r + 0.12)]
    if rail:
        sides = ("left", "right") if rail_side == "both" else (rail_side,)
        for sd in sides:
            mb.join(stair_railing(info["rail_paths"][sd], h=0.9, kind=rail, seed=int(rs.integers(1 << 30))))
    mb.meta = dict(info, kind="stair_straight", material=kind, width=width, rise_total=rise_total)
    return mb


def _stair_wood(mb, width, rise, rs, g, broken, stringers):
    """Escalera de madera. stringers=True: zancas cerradas (tablón 5x28 a cada lado, huellas embutidas sobre listones).
    stringers=False: zancas recortadas en diente de sierra bajo las huellas (retranqueadas 6 cm) y huellas que vuelan."""
    N, r = stair_riser_count(rise, 0.16, 0.19, prefer_even=False)
    st_t, st_d = 0.05, 0.28
    cs = math.cos(math.atan2(r, g))
    u_top = (N - 1) * g - 0.003
    dvv = st_d / cs
    tz = 0.035
    WD = "wood_grey"
    rr = _sub(rs)

    def z_top(u):
        return r + 0.05 + u * r / g

    def z_bot(u):
        return z_top(u) - dvv

    u0 = -0.05
    if stringers:
        uf = (dvv - r - 0.05) * g / r
        prof = ([(u0, 0.0), (uf, 0.0)] if uf > u0 + 0.01 else [(u0, z_bot(u0))]) + \
            [(u_top, z_bot(u_top)), (u_top, z_top(u_top)), (u0, z_top(u0))]
        cols = None
        sv = [(0.0, st_t), (width - st_t, width)]
    else:  # zanca recortada: diente de sierra (un polígono por peldaño en las tapas)
        dcut = 0.20 / cs

        def z_bl(u):
            return u * r / g - tz - dcut

        uf = max((tz + dcut) * g / r, 0.0)
        top_c = [(0.0, 0.0)]
        for k in range(1, N):
            top_c += [((k - 1) * g, k * r - tz), (min(k * g, u_top), k * r - tz)]
        bot_u = sorted(set([k * g for k in range(1, N - 1)] + [u_top]), reverse=True)
        prof = list(top_c)
        idx_bot = {}
        for u in bot_u:
            idx_bot[u] = len(prof)
            prof.append((u, max(z_bl(u), 0.0)))
            nxt = max([x for x in bot_u if x < u] + [0.0])
            if nxt < uf < u:
                idx_bot[("f", u)] = len(prof)
                prof.append((uf, 0.0))
        cols = []
        for k in range(1, N):
            ia, ib = 1 + 2 * (k - 1), 2 + 2 * (k - 1)
            right = u_top if k == N - 1 else k * g
            poly = ([0] if k == 1 else [idx_bot[(k - 1) * g], ib - 2]) + [ia, ib, idx_bot[right]]
            if ("f", right) in idx_bot:
                poly.append(idx_bot[("f", right)])
            cols.append(poly)
        sv = [(0.06, 0.105), (width - 0.105, width - 0.06)]
        if width > 1.1:
            sv.insert(1, (width / 2 - 0.0225, width / 2 + 0.0225))
    # zancas (tablón con leve alabeo)
    for va, vb in sv:
        tw = rr.normal(0, 0.004)
        secs = []
        for v in _stations(va, vb, 0.05, bev=0.006, tol=0.002):
            d = _round_inset(v, va, vb, 0.006)
            q2 = _inset2d(prof, d) if d > 0 else prof
            secs.append([Vector((q[0], v + tw * (q[0] / max(u_top, 0.1)), q[1])) for q in q2])
        _loft(mb, secs, WD, cap_faces=cols)
        if stringers:  # clavos en la cara exterior (2 por peldaño)
            vo = va if va == 0.0 else vb
            sgn = -1.0 if va == 0.0 else 1.0
            for k in range(1, N):
                for du in (0.06, 0.19):
                    p = Vector(((k - 1) * g + du, vo, k * r - 0.018))
                    mb.cyl(p - Vector((0, sgn * 0.002, 0)), p + Vector((0, sgn * 0.0015, 0)), 0.0038, seg=6, mat="metal_rust")
    # huellas
    for k in range(1, N):
        ua, ub = (k - 1) * g - 0.02, min((k - 1) * g + g + 0.01, u_top - 0.004)
        zt = k * r
        if stringers:
            for va in (st_t - 0.004, width - st_t - 0.036):  # listones (debajo de cada extremo de huella)
                mb.box(((k - 1) * g + 0.01, va, zt - tz - 0.04), ((k - 1) * g + g - 0.03, va + 0.04, zt - tz + 0.002), WD,
                       bevel=0.004, seg=1)
        roll = rr.random()
        if roll < broken * 0.6:
            continue  # tabla faltante (quedan los listones o el diente desnudo)
        va, vb = (st_t - 0.012, width - st_t + 0.012) if stringers else (0.0, width)
        sag = rr.uniform(0.002, 0.008) + (rr.uniform(0.02, 0.05) if roll < broken * 1.1 else 0.0)
        split = roll < broken * 1.1
        tw = rr.normal(0, 0.004)
        c = 0.005
        sh_ = rr.normal(0, 0.007)
        ua, ub = ua + sh_, min(ub + sh_, u_top - 0.004)
        zt = zt + rr.normal(0, 0.0025) + (0.0 if stringers else 0.003)
        # cara inferior 2-5 mm por debajo del apoyo (listón o diente de la zanca): se empotra, nunca queda coplanar
        z_sup = k * r - tz + (0.002 if stringers else 0.0)
        tzk = zt - z_sup + rr.uniform(0.002, 0.005)
        tprof = [(ua + 0.012, zt), (ua + 0.002, zt - 0.006), (ua, zt - 0.012), (ua, zt - tzk + c), (ua + c, zt - tzk),
                 (ub - c, zt - tzk), (ub, zt - tzk + c), (ub, zt - c), (ub - c, zt)]
        if split:  # tabla partida a lo ancho: dos mitades hundidas en V
            vm = rr.uniform(va + 0.35 * (vb - va), va + 0.65 * (vb - va))
            for (a_, b_) in ((va, vm - 0.006), (vm + 0.006, vb)):
                secs = []
                for v in _stations(a_, b_, 0.15, bev=0.004, tol=0.002):
                    d = _round_inset(v, a_, b_, 0.004)
                    t = (v - a_) / (b_ - a_) if a_ == va else (b_ - v) / (b_ - a_)
                    dzv = -sag * t * 1.4
                    q2 = _inset2d(tprof, d) if d > 0 else tprof
                    secs.append([Vector((q[0], v, q[1] + dzv + tw * (q[0] - ua))) for q in q2])
                _loft(mb, secs, WD)
        else:
            secs = []
            for v in _stations(va, vb, 0.15, bev=0.004, tol=0.002):
                d = _round_inset(v, va, vb, 0.004)
                dzv = -sag * math.sin(math.pi * (v - va) / (vb - va)) * (1.0 if stringers else 0.4)
                q2 = _inset2d(tprof, d) if d > 0 else tprof
                secs.append([Vector((q[0], v, q[1] + dzv + tw * (q[0] - ua))) for q in q2])
            _loft(mb, secs, WD)
            if not stringers:  # clavos en la cara de la huella sobre cada zanca
                for (sa, sb) in sv:
                    for du in (0.07, 0.19):
                        p = Vector(((k - 1) * g + du + sh_, (sa + sb) / 2 + rr.normal(0, 0.004), zt))
                        mb.cyl(p - ZV * 0.003, p + ZV * 0.0012, 0.0038, seg=6, mat="metal_rust")
    # dado de concreto al pie
    if uf > u0 + 0.01:
        mb.box((u0 - 0.10, -0.07, -0.12), (uf + 0.12, width + 0.07, 0.04), "concrete", bevel=0.015, seg=2)
    # poste y travesaño intermedios
    if rise > 1.6:
        um = 0.5 * u_top
        zb = z_bot(um) if stringers else um * r / g - tz - 0.2 / cs
        mb.box((um - 0.08, -0.06, zb - 0.16), (um + 0.08, width + 0.06, zb + 0.015), WD, bevel=0.006, seg=1)
        for sa, sb in sv:
            vc = (sa + sb) / 2
            mb.box((um - 0.045, vc - 0.045, -0.05), (um + 0.045, vc + 0.045, zb - 0.155), WD, bevel=0.006, seg=1)
            mb.box((um - 0.13, vc - 0.13, -0.15), (um + 0.13, vc + 0.13, -0.03), "concrete", bevel=0.015, seg=2)
    if stringers:
        yl, yr = 0.025, width - 0.025
        rp = {"left": [(u0 + 0.06, yl, z_top(u0 + 0.06)), (u_top - 0.06, yl, z_top(u_top - 0.06))],
              "right": [(u0 + 0.06, yr, z_top(u0 + 0.06)), (u_top - 0.06, yr, z_top(u_top - 0.06))]}
    else:
        ks = sorted(set(list(range(1, N, 4)) + [N - 1]))
        rp = {key: [((k - 1) * g + 0.07, y, k * r) for k in ks] for key, y in (("left", 0.045), ("right", width - 0.045))}
    return dict(N=N, riser=r, going=g, top_x=u_top + 0.003, top_z=rise, rail_paths=rp)


# =====================================================================================================================
# BARANDALES
# =====================================================================================================================
def _rail_tube(mb, path, h, rs, missing, *, ends=(0.025, 0.025), post_max=1.4, sp=0.11):
    """Barandal de tubo: postes de tubo cuadrado 40x40 con placa y pernos, pasamanos Ø42, travesaño inferior Ø24,
    barrotes Ø14 cada 0,11 con cordones de soldadura; faltantes con muñones, algunos rotos y doblados."""
    rt, rb, rbar, hb = 0.021, 0.012, 0.007, 0.10
    MR = "metal_rust"
    sposts = _bays(path, ends, post_max)
    st = path.stations(sposts[0] - 0.04, sposts[-1] + 0.04, 0.12)
    _ptube(mb, _fillet([path.at(s) + Vector((0, 0, h - rt)) for s in st], 0.07), rt, None, seg=14, mat=MR)
    st = path.stations(sposts[0], sposts[-1], 0.15)
    _ptube(mb, _fillet([path.at(s) + Vector((0, 0, hb)) for s in st], 0.05), rb, None, seg=10, mat=MR)
    for s in sposts:
        base = path.at(s)
        hd = path.hdir(s)
        m = Matrix.Translation(base) @ Matrix.Rotation(math.atan2(hd.y, hd.x), 4, "Z")
        mb.box((-0.02, -0.02, 0.004), (0.02, 0.02, h - rt), MR, bevel=0.004, seg=1, m=m)
        mb.box((-0.05, -0.05, -0.002), (0.05, 0.05, 0.006), MR, bevel=0.002, seg=1, m=m)
        for sx, sy in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            mb.cyl(m @ Vector((0.035 * sx, 0.035 * sy, 0.004)), m @ Vector((0.035 * sx, 0.035 * sy, 0.0115)), 0.0065, seg=6, mat=MR)
        _torus(mb, base + Vector((0, 0, hb)), ZV, 0.029, 0.003, seg=8, segr=4)  # soldadura poste-travesaño
    for a, b in zip(sposts, sposts[1:]):
        for s in _spaced(a, b, sp, 0.06):
            base = path.at(s)
            sl = path.slope(s)
            cs = 1.0 / math.sqrt(1.0 + sl * sl)
            zb_c, zt_c = base.z + hb, base.z + h - rt
            plo = Vector((base.x, base.y, zb_c))
            phi = Vector((base.x, base.y, zt_c))
            wlo = Vector((base.x, base.y, zb_c + rb / cs - 0.0012))
            whi = Vector((base.x, base.y, zt_c - rt / cs + 0.0012))
            roll = rs.random()
            if roll < missing:  # barrote arrancado: quedan muñones soldados arriba y abajo
                mb.cyl(phi, phi - ZV * (rt / cs + rs.uniform(0.008, 0.05)), rbar, seg=8, mat=MR)
                _torus(mb, whi, ZV, rbar + 0.0022, 0.0028, seg=6, segr=3)
                mb.cyl(plo, plo + ZV * (rb / cs + rs.uniform(0.004, 0.03)), rbar, seg=8, mat=MR)
                _torus(mb, wlo, ZV, rbar + 0.0022, 0.0028, seg=6, segr=3)
            elif roll < missing * 1.4:  # barrote podrido abajo, doblado hacia fuera, colgando del pasamanos
                zc = zb_c + (zt_c - zb_c) * rs.uniform(0.25, 0.6)
                sd = path.side(s) * rs.uniform(0.03, 0.09) + path.hdir(s) * rs.normal(0, 0.02)
                pts = [phi, phi - ZV * ((zt_c - zc) * 0.45), Vector((base.x, base.y, zc)) + sd]
                _ptube(mb, _fillet(pts, 0.1), rbar, None, seg=8, mat=MR)
                _torus(mb, whi, ZV, rbar + 0.0022, 0.0028, seg=6, segr=3)
                mb.cyl(plo, plo + ZV * (rb / cs + rs.uniform(0.004, 0.02)), rbar, seg=8, mat=MR)
            else:
                mb.cyl(plo, phi, rbar, seg=8, mat=MR)
                _torus(mb, wlo, ZV, rbar + 0.0022, 0.0028, seg=6, segr=3)
                _torus(mb, whi, ZV, rbar + 0.0022, 0.0028, seg=6, segr=3)
    return sposts


def _lean_bend(mb, length, h, rs, bend, lean=0.01):
    """Desplome realista: inclinación fuera de plomo variable a lo largo (±0,5–1°) y, si bend > 0, un tramo empujado
    hacia -Y (bend = desplazamiento en m en lo alto) que se hunde y arrastra un poste con la placa desprendida."""
    l0 = rs.normal(0.0, lean * 0.6)
    ln = _N1(rs, 0.0, length, 0.9, lean * 0.6)
    xb = rs.uniform(0.3, 0.7) * length
    hw = min(0.5 * length, rs.uniform(0.7, 1.2))
    for v in mb.bm.verts:
        x, z = v.co.x, max(v.co.z, 0.0)
        dy = -math.tan(l0 + ln(x)) * z
        dz = 0.0
        if bend:
            bmp = _ss(1.0 - abs(x - xb) / hw)
            q = min(z / h, 1.1)
            dy += -bend * bmp * (0.1 + 0.9 * q ** 1.3)
            dz += -0.28 * bend * bmp * q ** 1.5
        v.co.y += dy
        v.co.z += dz


# --- balaustre torneado: (t, r) con t en [0,1] a lo alto del fuste; todas las bandas son cónicas (suavizado limpio)
_BAL = [(0.0, 0.046), (0.035, 0.050), (0.07, 0.046), (0.095, 0.036), (0.12, 0.034), (0.17, 0.042), (0.25, 0.052),
        (0.34, 0.056), (0.44, 0.052), (0.54, 0.042), (0.63, 0.031), (0.70, 0.026), (0.745, 0.028), (0.77, 0.036),
        (0.80, 0.040), (0.83, 0.037), (0.86, 0.031), (0.92, 0.034), (0.97, 0.040), (1.0, 0.043)]


def _baluster(mb, base, z0, z1, ang, rs, part=None, rod=False):
    """Balaustre de concreto: dado inferior + fuste torneado (12 lados) + dado superior, entre z0 y z1 (absolutos).
    part=None completo; ('low', t) muñón inferior roto en t; ('high', t) muñón colgante superior roto en t."""
    dh = 0.045
    m0 = Matrix.Translation((base.x, base.y, 0.0)) @ Matrix.Rotation(ang, 4, "Z")
    H = z1 - z0 - 2 * dh + 0.008
    zt0 = z0 + dh - 0.004
    if part is None or part[0] == "low":
        mb.box((-0.055, -0.055, z0), (0.055, 0.055, z0 + dh), "concrete", bevel=0.006, seg=1, m=m0)
    if part is None or part[0] == "high":
        mb.box((-0.052, -0.052, z1 - dh), (0.052, 0.052, z1), "concrete", bevel=0.006, seg=1, m=m0)
    rot = Matrix.Translation((base.x, base.y, zt0)) @ Matrix.Rotation(ang + rs.uniform(0, 0.5), 4, "Z")
    if part is None:
        prof = [(r, t * H) for t, r in _BAL]
        _revolve(mb, prof, rot, seg=12)
        return
    kind, tb = part
    rint = float(np.interp(tb, [p[0] for p in _BAL], [p[1] for p in _BAL]))
    if kind == "low":
        prof = [(r, t * H) for t, r in _BAL if t < tb - 0.02] + [(rint, tb * H)]
        _revolve(mb, prof, rot, seg=12, jag_top=0.035, rs=rs)
        if rod:
            _rebar_run(mb, [rot @ Vector((0.004, 0.0, 0.0)), rot @ Vector((0.004, 0.0, tb * H)),
                            rot @ Vector((rs.normal(0, 0.03), rs.normal(0, 0.03), tb * H + rs.uniform(0.05, 0.2)))], rs, r=0.004)
    else:
        prof = [(rint, tb * H)] + [(r, t * H) for t, r in _BAL if t > tb + 0.02]
        _revolve(mb, prof, rot, seg=12, jag_bot=0.035, rs=rs)


def _concrete_sweep(mb, path, s0, s1, prof, rs, *, dz=0.0, step=0.08, corners=(), rate=0.0, end_jag=(0.0, 0.0),
                    mat="concrete", dmax=0.03):
    """Barre un perfil de concreto por el camino con despostillados reales en las esquinas `corners`:
    [(índices del perfil, (dx, dy) dirección hacia dentro)]. rate = despostillados por metro y por esquina."""
    chips = []
    for idxs, dvec in corners:
        for _ in range(rs.poisson(rate * (s1 - s0))):
            hw = rs.uniform(0.03, 0.10)
            chips.append((idxs, dvec, _Chip(rs, 0, rs.uniform(s0 + hw, max(s1 - hw, s0 + hw + 0.01)), hw, rs.uniform(0.008, dmax), 0.0)))
    extra = [x for c in chips for x in c[2].bounds()]
    ss = path.stations(s0, s1, step, extra)
    jag = [float(rs.uniform(0.75, 1.25)) for _ in ss]

    def ring(i):
        Q = [list(p) for p in prof]
        s = ss[i]
        for idxs, dvec, c in chips:
            f = c.f(s)
            if f <= 0:
                continue
            d = c.du * f * jag[i]
            for j in idxs:
                Q[j][0] += dvec[0] * d
                Q[j][1] += dvec[1] * d
        return Q

    pts = [path.at(s) + Vector((0, 0, dz)) for s in ss]
    _sweep(mb, ring, pts, [ZV] * len(pts), mat, end_jag=end_jag, rs=rs)


def _chipped_post(mb, base, z0, z1, w, hdir, rs, n_chips=1, bev=0.012, mat="concrete"):
    """Pilastra de concreto (bisel redondeado de 2 segmentos) con desconchados reales en sus aristas verticales.
    w: lado (cuadrada) o (largo según hdir, ancho)."""
    wx, wy = (w, w) if isinstance(w, (int, float)) else w
    cs = [(1, -1), (1, 1), (-1, 1), (-1, -1)]
    prof, groups = [], []
    for i, (sx, sy) in enumerate(cs):
        nx_, ny_ = cs[(i + 1) % 4]
        c = Vector((sx * wx / 2, sy * wy / 2, 0.0))
        din = Vector(((sx - cs[i - 1][0]) / 2, (sy - cs[i - 1][1]) / 2, 0.0)).normalized()
        dout = Vector(((nx_ - sx) / 2, (ny_ - sy) / 2, 0.0)).normalized()
        p1, p2, p3 = c - din * bev, c + (dout - din) * (0.293 * bev), c + dout * bev
        # bucles de apoyo a 1,5 cm del bisel: un despostillado en la esquina no tuerce las normales de toda la cara
        # (sin ellos, cada anillo afectado deja una banda de sombreado de lado a lado de la pilastra)
        s0_, s1_ = c - din * (bev + 0.015), c + dout * (bev + 0.015)
        groups.append(([len(prof) + 1, len(prof) + 2, len(prof) + 3], (-sx * 0.7071, -sy * 0.7071)))
        prof += [(s0_.x, s0_.y), (p1.x, p1.y), (p2.x, p2.y), (p3.x, p3.y), (s1_.x, s1_.y)]
    chips = []
    for _ in range(n_chips):
        hw = rs.uniform(0.03, 0.12)
        chips.append((groups[int(rs.integers(0, 4))], _Chip(rs, 0, rs.uniform(z0 + 0.1, z1 - 0.06), hw, rs.uniform(0.012, 0.035), 0.0)))
    zz = sorted(set([z0, z1] + list(np.linspace(z0, z1, max(2, int((z1 - z0) / 0.2)) + 1)) +
                    [x for _, c in chips for x in c.bounds() if z0 + 0.01 < x < z1 - 0.01]))
    jag = [float(rs.uniform(0.7, 1.3)) for _ in zz]

    def ring(i):
        Q = [list(q) for q in prof]
        for (idxs, dv), c in chips:
            f = c.f(zz[i])
            if f > 0:
                for j in idxs:
                    Q[j][0] += dv[0] * c.du * f * jag[i]
                    Q[j][1] += dv[1] * c.du * f * jag[i]
        return Q

    pts = [Vector((base.x, base.y, z)) for z in zz]
    side = Vector((hdir.y, -hdir.x, 0.0))
    _sweep(mb, ring, pts, [side] * len(pts), mat)


def _splinter_stick(mb, plo, ztop, w, side, rs, mat="wood_grey"):
    """Balaustre de madera partido: listón de sección achaflanada con la punta astillada en diagonal."""
    c = w * 0.12
    q = [(-w / 2 + c, -w / 2), (w / 2 - c, -w / 2), (w / 2, -w / 2 + c), (w / 2, w / 2 - c), (w / 2 - c, w / 2),
         (-w / 2 + c, w / 2), (-w / 2, w / 2 - c), (-w / 2, -w / 2 + c)]
    X, Y, Z = _frame(ZV, side)
    zs_ = [plo.z, (plo.z + ztop) / 2, ztop]
    a, b = rs.normal(0, 1.2), rs.normal(0, 1.2)
    rings = []
    for k, z in enumerate(zs_):
        ring = []
        for x, y in q:
            dz = 0.0
            if k == 2:
                dz = -abs(a * (x + w / 2) + b * (y + w / 2)) - float(rs.uniform(0.0, 0.012))
            ring.append(mb.bm.verts.new(Vector((plo.x, plo.y, z + dz)) + X * x + Y * y))
        rings.append(ring)
    for r0, r1 in zip(rings, rings[1:]):
        for j in range(8):
            jj = (j + 1) % 8
            mb.face([r0[j], r0[jj], r1[jj], r1[j]], mat)
    mb.face(rings[0][::-1], mat)
    top = rings[-1]
    cen = sum((v.co for v in top), Vector()) / 8 + ZV * 0.006
    _fan_cap(mb, top, cen, mat, False)


def _rail_concrete(mb, path, h, rs, missing, bend, stair=False):
    """Balaustrada de concreto: zócalo continuo, pilastras 0,19, balaustres torneados cada 0,16 y pasamanos moldurado
    0,20 x 0,11 con gotero. Despostillados en cantos; balaustres faltantes con muñones (y varilla); bend > 0: tramo de
    pasamanos roto con varillas dobladas hacia abajo `bend` m y escombro sobre el zócalo.
    Quiebres del recorrido (cambio de pendiente o giro en planta): pilar de arranque de 0,25 que sobresale 5 cm sobre el
    pasamanos, con remate; zócalo y pasamanos se cortan dentro de él (nada de ingletes moldurados que se autointersequen).
    Quiebres separados menos de 0,40 (p. ej. el ojo de una escalera en U) comparten un único pilar ancho."""
    pw, rail_h, ptop, nw = 0.19, 0.11, 0.12, 0.25
    sposts = _bays(path, (pw / 2, pw / 2), 1.8 if stair else 2.2)
    s0, s1 = sposts[0] - pw / 2, sposts[-1] + pw / 2
    # en escalera el zócalo baja como zanca y tapa el diente de los peldaños (0,19: queda por encima de la cara inferior
    # del tramo y dentro de un descanso de 0,20, sin asomar por debajo)
    zb_ = -0.19 if stair else -0.012
    # --- quiebres agrupados en pilares de arranque
    groups = []
    for i in range(1, len(path.P) - 1):
        t0 = (path.P[i] - path.P[i - 1]).normalized()
        t1 = (path.P[i + 1] - path.P[i]).normalized()
        if t0.dot(t1) < math.cos(math.radians(1.5)):
            if groups and path.cum[i] - path.cum[groups[-1][-1]] < nw + 0.15:
                groups[-1].append(i)
            else:
                groups.append([i])
    newels = []
    for g_ in groups:
        pts = [path.P[i] for i in g_]
        segs = [(path.P[i + 1] - path.P[i]) for i in g_[:-1]]
        hd = max(segs, key=lambda d: d.x * d.x + d.y * d.y) if segs else (path.P[g_[0]] - path.P[g_[0] - 1])
        hd = Vector((hd.x, hd.y, 0.0)).normalized()
        sd = Vector((hd.y, -hd.x, 0.0))
        us = [p.dot(hd) for p in pts]
        vs = [p.dot(sd) for p in pts]
        lu, lv = max(us) - min(us) + nw, max(vs) - min(vs) + nw
        ctr = hd * ((max(us) + min(us)) / 2) + sd * ((max(vs) + min(vs)) / 2)
        zlo, zhi = min(p.z for p in pts), max(p.z for p in pts)

        def inside(p, ctr=ctr, hd=hd, sd=sd, lu=lu, lv=lv):
            q = p - ctr
            return abs(q.dot(hd)) < lu / 2 - 0.005 and abs(q.dot(sd)) < lv / 2 - 0.005
        a, b = path.cum[g_[0]], path.cum[g_[-1]]
        lo, hi = a, b
        while lo > s0 and inside(path.at(lo - 0.01)):
            lo -= 0.01
        while hi < s1 and inside(path.at(hi + 0.01)):
            hi += 0.01
        newels.append(dict(a=a, b=b, lo=lo - 0.01, hi=hi + 0.01, ctr=Vector((ctr.x, ctr.y, 0.0)), hd=hd, lu=lu, lv=lv,
                           z0=zlo + zb_ - 0.008, z1=zhi + h + 0.05))
    sposts = [s for s in sposts if not any(n["lo"] - pw / 2 - 0.02 < s < n["hi"] + pw / 2 + 0.02 for n in newels)]
    # tramos continuos de zócalo y pasamanos (entre pilares de arranque)
    spans, a_ = [], s0
    for n in newels:
        spans.append((a_, n["a"]))
        a_ = n["b"]
    spans.append((a_, s1))
    pl = [(-0.085, zb_), (0.085, zb_), (0.085, ptop - 0.012), (0.0815, ptop - 0.0035), (0.073, ptop),
          (-0.073, ptop), (-0.0815, ptop - 0.0035), (-0.085, ptop - 0.012)]
    rp = _sub(rs)

    def narrow(prof, k):  # tramos alternos 1,2 % más estrechos: dos tramos que entran en un mismo pilar no comparten caras
        f = 1.0 - 0.012 * (k % 2)
        return [(x * f, y) for x, y in prof]
    for k, (a_, b_) in enumerate(spans):
        if b_ - a_ > 0.02:
            _concrete_sweep(mb, path, a_ + (0.004 if k == 0 else 0.003), b_ - (0.004 if k == len(spans) - 1 else 0.003),
                            narrow(pl, k), rp, corners=[((2, 3, 4), (-1, -1)), ((5, 6, 7), (1, -1))], rate=0.8)
    rl = [(-0.072, 0.0), (0.072, 0.0), (0.078, 0.006), (0.078, 0.030), (0.096, 0.036), (0.1, 0.042), (0.1, 0.085),
          (0.096, 0.097), (0.085, 0.105), (0.06, 0.11), (-0.06, 0.11), (-0.085, 0.105), (-0.096, 0.097), (-0.1, 0.085),
          (-0.1, 0.042), (-0.096, 0.036), (-0.078, 0.030), (-0.078, 0.006)]
    rcorn = [((6, 7, 8, 9), (-1, -1)), ((10, 11, 12, 13), (1, -1)), ((4, 5), (-1, 0.4)), ((14, 15), (1, 0.4))]
    brk = None
    rr = _sub(rs)
    if bend > 0 and len(sposts) >= 2:
        j = int(rr.integers(0, len(sposts) - 1))
        a, b = sposts[j] + pw / 2, sposts[j + 1] - pw / 2
        gl = min(rr.uniform(0.3, 0.6), (b - a) * 0.6)
        c = rr.uniform(a + gl / 2 + 0.05, max(b - gl / 2 - 0.05, a + gl / 2 + 0.06))
        brk = (c - gl / 2, c + gl / 2)
    zr = h - rail_h
    rspans = [(s0 - 0.012 if k == 0 else a_ + 0.003, s1 + 0.012 if k == len(spans) - 1 else b_ - 0.003)
              for k, (a_, b_) in enumerate(spans)]
    for k, (a_, b_) in enumerate(rspans):
        if b_ - a_ <= 0.02:
            continue
        rlk = narrow(rl, k)
        if brk is not None and a_ < brk[0] and brk[1] < b_:
            _concrete_sweep(mb, path, a_, brk[0], rlk, rr, dz=zr, corners=rcorn, rate=0.6, dmax=0.022, end_jag=(0.0, 0.05))
            _concrete_sweep(mb, path, brk[1], b_, rlk, rr, dz=zr, corners=rcorn, rate=0.6, dmax=0.022, end_jag=(0.05, 0.0))
        else:
            _concrete_sweep(mb, path, a_, b_, rlk, rr, dz=zr, corners=rcorn, rate=0.6, dmax=0.022)
    if brk is not None:
        for sb_, sgn in ((brk[0], 1.0), (brk[1], -1.0)):
            for (x, y) in ((0.05, 0.025), (-0.05, 0.025), (0.05, 0.08), (-0.05, 0.08)):
                ext = rr.uniform(0.06, min(0.24, (brk[1] - brk[0]) * 0.55))
                pts = []
                for t in np.linspace(-0.18, ext, 7):
                    s = sb_ + sgn * t
                    p = path.at(s) + path.side(s) * x + Vector((0, 0, zr + y))
                    if t > 0:
                        p = p - ZV * (bend * (t / ext) ** 2) + path.side(s) * (0.3 * bend * (t / ext) ** 2 * rr.normal(0, 1))
                    pts.append(p)
                _rebar_run(mb, pts, rr, r=0.005)
    for s in sposts:
        base = path.at(s)
        top = h - rail_h + 0.05
        if stair:
            top = h - rail_h + 0.05 - abs(path.slope(s)) * pw / 2
        _chipped_post(mb, base, base.z - 0.01, base.z + top, pw, path.hdir(s), rr, n_chips=int(rr.poisson(1.5)))
    for n in newels:  # pilar de arranque con remate (losa de 5 cm con bisel y goterón)
        _chipped_post(mb, n["ctr"], n["z0"], n["z1"], (n["lu"], n["lv"]), n["hd"], rr, n_chips=1 + int(rr.poisson(1.5)),
                      bev=0.015)
        m = Matrix.Translation((n["ctr"].x, n["ctr"].y, n["z1"])) @ Matrix.Rotation(math.atan2(n["hd"].y, n["hd"].x), 4, "Z")
        cu, cv = n["lu"] / 2 + 0.03, n["lv"] / 2 + 0.03
        mb.box((-cu, -cv, -0.006), (cu, cv, 0.045), "concrete", bevel=0.012, seg=2, m=m)
        mb.box((-cu + 0.05, -cv + 0.05, 0.04), (cu - 0.05, cv - 0.05, 0.07), "concrete", bevel=0.012, seg=2, m=m)
    # balaustres en los vanos libres entre apoyos (pilastras y pilares de arranque)
    sup = sorted([(s - pw / 2, s + pw / 2) for s in sposts] + [(n["lo"], n["hi"]) for n in newels])
    for (_, a), (b, _) in zip(sup, sup[1:]):
        for s in _spaced(a, b, 0.16, 0.08):
            base = path.at(s)
            sl = path.slope(s)
            z0 = base.z + ptop * math.sqrt(1 + sl * sl) - 0.008 - abs(sl) * 0.055
            z1 = base.z + h - rail_h + 0.008 + abs(sl) * 0.055
            ang = math.atan2(path.hdir(s).y, path.hdir(s).x)
            under_gap = brk is not None and brk[0] - 0.05 < s < brk[1] + 0.05
            roll = rr.random()
            if under_gap or roll < missing:
                if rr.random() < 0.75 or under_gap:
                    _baluster(mb, base, z0, z1, ang, rr, part=("low", rr.uniform(0.12, 0.4)), rod=rr.random() < 0.6)
                if not under_gap and rr.random() < 0.7:
                    _baluster(mb, base, z0, z1, ang, rr, part=("high", rr.uniform(0.66, 0.9)))
                if under_gap:
                    for _ in range(int(rr.integers(1, 4))):
                        sz = rr.uniform(0.03, 0.07)
                        p = path.at(s + rr.normal(0, 0.06)) + path.side(s) * rr.normal(0, 0.03)
                        _chunk(mb, p + Vector((0, 0, ptop + 0.15 * sz)), sz, rr)
            else:
                _baluster(mb, base, z0, z1, ang, rr)
    return sorted(sposts + [0.5 * (n["a"] + n["b"]) for n in newels])


def _rail_wood(mb, path, h, rs, missing, bend, stair=False):
    """Barandal de madera: postes 9x9, tapa 14x3,2 continua, travesaños 4,5x9 y 4,5x7, balaustres 3,5x3,5 cada 0,115,
    clavos. Tablas alabeadas, faltantes y rotas; bend > 0: un vano con la tapa partida y el travesaño caído."""
    pw, cw, ct, rw, trh, brz, brh = 0.09, 0.14, 0.032, 0.045, 0.09, 0.05, 0.07
    WD = "wood_grey"
    rr = _sub(rs)
    sposts = _bays(path, (pw / 2, pw / 2), 1.5)
    z_post0 = -0.06 if stair else -0.012
    brk = None
    if bend > 0 and len(sposts) >= 2:
        j = int(rr.integers(0, len(sposts) - 1))
        sa, sb = sposts[j], sposts[j + 1]
        brk = (j, sa, sb, sa + (sb - sa) * rr.uniform(0.35, 0.65))
    for s in sposts:
        base = path.at(s)
        hd = path.hdir(s)
        rot = Euler((rr.normal(0, 0.01), rr.normal(0, 0.01), math.atan2(hd.y, hd.x) + rr.normal(0, 0.03))).to_matrix().to_4x4()
        mb.box((-pw / 2, -pw / 2, z_post0), (pw / 2, pw / 2, h - ct + 0.006), WD, bevel=0.007, seg=1,
               m=Matrix.Translation(base) @ rot)
    # tapa (con alabeo y torsión suaves); en el vano roto se parte y cuelga
    cprof = [(-cw / 2 + 0.006, 0.0), (cw / 2 - 0.006, 0.0), (cw / 2, 0.006), (cw / 2, ct - 0.006), (cw / 2 - 0.006, ct),
             (-cw / 2 + 0.006, ct), (-cw / 2, ct - 0.006), (-cw / 2, 0.006)]
    cs0, cs1 = sposts[0] - pw / 2 - 0.03, sposts[-1] + pw / 2 + 0.03
    warp = _N1(rr, cs0, cs1, 0.7, 0.003)
    twist = _N1(rr, cs0, cs1, 0.9, 0.03)

    def cap_piece(a, b, dzf):
        ss = path.stations(a, b, 0.25, extra=[x for x in ((brk[1], brk[2]) if brk else ())])
        pts = [path.at(s) + Vector((0, 0, h - ct + warp(s) + dzf(s))) for s in ss]

        def pr(i):
            tw = twist(ss[i])
            return [(x * math.cos(tw) - (y - ct / 2) * math.sin(tw), (y - ct / 2) * math.cos(tw) + x * math.sin(tw) + ct / 2)
                    for x, y in cprof]
        _sweep(mb, pr, pts, [ZV] * len(pts), WD, end_jag=(0.0, 0.0), rs=rr)

    if brk is None:
        cap_piece(cs0, cs1, lambda s: 0.0)
    else:
        _, sa, sb, sbk = brk
        d1, d2 = bend * rr.uniform(0.8, 1.2), bend * rr.uniform(0.5, 1.0)
        cap_piece(cs0, sbk - 0.006, lambda s: -max(0.0, s - sa) / (sbk - sa) * d1)
        cap_piece(sbk + 0.006, cs1, lambda s: -max(0.0, sb - s) / (sb - sbk) * d2)
    rprof_t = [(-rw / 2, 0.0), (rw / 2, 0.0), (rw / 2, trh), (-rw / 2, trh)]
    rprof_b = [(-rw / 2, 0.0), (rw / 2, 0.0), (rw / 2, brh), (-rw / 2, brh)]
    for jb, (a, b) in enumerate(zip(sposts, sposts[1:])):
        ra, rb_ = a + pw / 2 - 0.012, b - pw / 2 + 0.012
        drop = 0.0
        if brk is not None and jb == brk[0]:
            drop = min(bend * 1.6, h * 0.55)
        for prof_, z0, dd in ((rprof_t, h - ct - trh + 0.004, drop), (rprof_b, brz, 0.0)):
            ss = path.stations(ra, rb_, 0.3)
            sg = rr.uniform(0.0, 0.006)
            pts = [path.at(s) + Vector((0, 0, z0 - sg * math.sin(math.pi * (s - ra) / (rb_ - ra)) - dd * (s - ra) / (rb_ - ra)))
                   for s in ss]
            _sweep(mb, [(x, y) for x, y in prof_], pts, [ZV] * len(pts), WD)
        for s in _spaced(a + pw / 2, b - pw / 2, 0.115, 0.07):
            base = path.at(s)
            sd, hd = path.side(s), path.hdir(s)
            zlo = base.z + brz + brh * 0.5
            zhi = base.z + h - ct - trh * 0.5 + 0.004 - drop * (s - ra) / (rb_ - ra)
            if zhi - zlo < 0.3:
                continue
            roll = rr.random()
            plo = Vector((base.x, base.y, zlo))
            phi = Vector((base.x, base.y, zhi)) + sd * rr.normal(0, 0.006) + hd * rr.normal(0, 0.006)
            if drop > 0:
                phi = phi + sd * rr.uniform(0.0, 0.05)
            if roll < missing:  # falta: queda un clavo doblado
                for zz in (zlo, zhi):
                    p = Vector((base.x, base.y, zz)) + sd * (rw / 2)
                    mb.cyl(p - sd * 0.005, p + sd * 0.02 + ZV * rr.normal(0, 0.01), 0.0015, seg=4, mat="metal_rust")
                continue
            side = sd * math.cos(rr.normal(0, 0.05)) + hd * math.sin(rr.normal(0, 0.05))
            if roll < missing * 1.5:  # roto: punta astillada a media altura
                ztop = zlo + (zhi - zlo) * rr.uniform(0.35, 0.7)
                _splinter_stick(mb, plo, ztop, 0.035, side, rr)
            else:
                _beam(mb, plo, phi, 0.035, 0.035, WD, bevel=0.003, side=side)
            for zz, ok in ((zlo, True), (zhi, roll >= missing * 1.5)):
                if not ok:
                    continue
                p = Vector((base.x, base.y, zz)) + sd * (rw / 2)
                mb.cyl(p - sd * 0.002, p + sd * 0.0015, 0.0035, seg=6, mat="metal_rust")
    return sposts


def railing(kind="tube_metal", length=3.0, h=1.0, seed=0, bend=0.0, missing=0.1):
    """Barandal recto a lo largo de X de 0 a `length`, base en z=0, eje en y=0 (el lado exterior es -Y). Devuelve MB.
    kind:
      'baluster_concrete' — zócalo + pilastras + balaustres torneados de 12 lados + pasamanos moldurado con gotero.
            bend > 0: tramo de pasamanos ROTO con varillas expuestas dobladas hacia abajo `bend` m.
      'tube_metal' — postes 40x40 con placa y pernos, pasamanos Ø42, travesaño Ø24, barrotes Ø14 cada 0,11 soldados.
            Desplome fuera de plomo ±0,5–1°; bend > 0: un tramo empujado hacia -Y `bend` m en lo alto (y hundido).
      'wood' — postes 9x9, tapa, travesaños, balaustres 3,5x3,5 clavados. bend > 0: vano con tapa partida y travesaño caído.
    missing: fracción de barrotes/balaustres faltantes (quedan muñones, clavos o muñones con varilla).
    meta: posts (x de cada poste), kind, length, h."""
    rs = rng(seed)
    path = _Path([(0.0, 0.0, 0.0), (float(length), 0.0, 0.0)])
    mb = MB()
    if kind == "tube_metal":
        posts = _rail_tube(mb, path, h, _sub(rs), missing)
        _lean_bend(mb, length, h, _sub(rs), bend, lean=0.012)
    elif kind == "wood":
        posts = _rail_wood(mb, path, h, _sub(rs), missing, bend)
        _lean_bend(mb, length, h, _sub(rs), 0.0, lean=0.008)
    elif kind == "baluster_concrete":
        posts = _rail_concrete(mb, path, h, _sub(rs), missing, bend)
    else:
        raise ValueError(f"railing: kind desconocido {kind!r}")
    mb.meta = dict(kind=kind, length=length, h=h, posts=posts)
    return mb


def stair_railing(points, h=0.9, kind="tube_metal", seed=0, *, missing=0.06):
    """Pasamanos que sigue una polilínea de base inclinada (sobre las narices / huellas de una escalera). Devuelve MB.
    points: [(x, y, z)] base de la baranda; el pasamanos va `h` m por encima en vertical. Postes en cada vértice
    (+ intermedios si un tramo supera 1,3–1,8 m: pon un vértice sobre cada huella donde quieras un poste, porque los
    intermedios se reparten en horizontal y pueden caer entre narices); barrotes/balaustres verticales repartidos en
    horizontal. El lado exterior es la derecha del sentido de avance. kind: 'tube_metal' | 'wood' | 'baluster_concrete'
    (en escalera el zócalo de concreto baja 0,19 como zanca para tapar el diente de los peldaños; en cada cambio de
    pendiente o giro va un pilar de arranque con remate y los quiebres a menos de 0,40 comparten uno solo)."""
    rs = rng(seed)
    path = _Path(points)
    mb = MB()
    if kind == "tube_metal":
        posts = _rail_tube(mb, path, h, rs, missing, ends=(0.0, 0.0), post_max=1.3)
    elif kind == "wood":
        posts = _rail_wood(mb, path, h, rs, missing, 0.0, stair=True)
    elif kind == "baluster_concrete":
        posts = _rail_concrete(mb, path, h, rs, missing, 0.0, stair=True)
    else:
        raise ValueError(f"stair_railing: kind desconocido {kind!r}")
    mb.meta = dict(kind=kind, h=h, posts=posts, points=[tuple(p) for p in points])
    return mb


# =====================================================================================================================
# LOSA DE BALCÓN
# =====================================================================================================================
def balcony_slab(w=1.8, d=1.2, t=0.15, seed=0, spalled=0.3, *, embed=0.06, drip=True, rebar=True):
    """Losa de balcón en voladizo. Devuelve MB.
    ORIGEN: x in [0, w] a lo largo de la fachada; la cara del muro está en y=0 y la losa vuela hacia -Y hasta y=-d;
    base z=0, cara superior z≈t (pendiente de 1,5 % hacia el borde y flecha de voladizo de 5–12 mm en la punta).
    Se empotra `embed` m dentro del muro (y in [0, embed]) para no dejar junta.
    - Gotero real en la cara inferior: ranura 14x12 mm a 3 cm de los tres bordes libres (en U).
    - Cantos biselados 15 mm; `spalled` (0..1) controla cuántos desconchados hay: muescas reales en el canto (en planta y
      en altura) con el gotero perdido en la zona rota y varillas oxidadas asomando (superiores en voladizo, con gancho
      o dobladas, y una de reparto expuesta).
    meta: w, d, t, top_z, spalls."""
    rs = rng(seed)
    b, g0, gw, gd = 0.015, 0.03, 0.014, 0.012
    sp = []
    edges = [("F", w), ("L", d), ("R", d)]
    ltot = w + 2 * d
    nsp = int(rs.poisson(spalled * ltot / 0.55))
    for _ in range(nsp):
        x = rs.uniform(0, ltot)
        e = "F" if x < w else ("L" if x < w + d else "R")
        elen = dict(edges)[e]
        hw = rs.uniform(0.06, 0.24)
        c = rs.uniform(min(hw * 0.6, elen / 2), max(elen - hw * 0.6 - (0.1 if e != "F" else 0.0), elen / 2))
        D = rs.uniform(0.025, 0.085)
        drop = D * rs.uniform(0.45, 1.0) + 0.008
        rise = D * rs.uniform(0.15, 0.6)
        k = min(1.0, (t - 0.035) / (drop + rise))
        sp.append(dict(e=e, c=c, hw=hw, D=D, drop=drop * k, rise=rise * k, j=_N1(rs, c - hw, c + hw, max(hw / 4.0, 0.015), 0.35)))

    def edge_lines(L, extra):
        base = [0.0, 0.006, b, g0, g0 + 0.002, g0 + gw - 0.002, g0 + gw, 0.07, 0.11]
        lines = set(base) | {L - x for x in base}
        n = max(1, int(round((L - 0.22) / 0.12)))
        lines |= {0.11 + (L - 0.22) * i / n for i in range(n + 1)}
        lines |= {x for x in extra if 0 < x < L}
        out = []
        for x in sorted(lines):
            if not out or x - out[-1] > 0.0015:
                out.append(x)
        return out

    def sp_lines(e):
        res = []
        for s in sp:
            if s["e"] == e:
                res += [s["c"] + k * s["hw"] for k in np.linspace(-1.0, 1.0, 13)]
        return res

    xs = edge_lines(w, sp_lines("F"))
    # filas en y: distancia al borde frontal sF (0 = borde), hasta el muro (y=0) y el empotramiento
    sfl = edge_lines(d, [d - v for v in sp_lines("L") + sp_lines("R")])
    sfl = [s for s in sfl if s < d - 0.02] + [d - 0.012, d, d + embed]
    # grieta de flexión del voladizo sobre el apoyo (paralela al muro, en la mitad más cercana a él): surco en V que
    # serpentea; se coloca a medio camino entre dos filas de la malla para no cruzarlas
    rcr = _sub(rs)
    crack = None
    cand = [(a_ + b_) / 2 for a_, b_ in zip(sfl, sfl[1:]) if 0.25 <= (a_ + b_) / 2 <= d - 0.1 and b_ - a_ > 0.03]
    if cand and rcr.random() < 0.85:
        sc = cand[int(rcr.integers(len(cand) // 2, len(cand)))]
        crack = dict(s=sc, a=rcr.uniform(-0.3, 0.35 * w), b=rcr.uniform(0.65 * w, w + 0.3), dep=rcr.uniform(0.006, 0.01),
                     wob=_N1(rcr, -0.5, w + 0.5, 0.1, 0.008))
        sfl = sorted(sfl + [sc - 0.0025, sc, sc + 0.0025])
        xs = sorted(set(xs) | {x for x in (crack["a"] + 0.04, crack["a"] + 0.09, crack["b"] - 0.09, crack["b"] - 0.04)
                               if all(abs(x - q) > 0.012 for q in xs) and 0.03 < x < w - 0.03})
    groove_in = {g0 + 0.002, g0 + gw - 0.002}

    def is_groove(v):
        return any(abs(v - q) < 1e-6 for q in groove_in)

    def spall_D(e, pos):
        D, drop, rise = 0.0, 0.0, 0.0
        for s in sp:
            if s["e"] != e:
                continue
            q = abs(pos - s["c"]) / s["hw"]
            if q >= 1:
                continue
            f = _ss((1 - q) / 0.25) * (0.75 + s["j"](pos))
            if s["D"] * f > D:
                D, drop, rise = s["D"] * f, s["drop"] * f, s["rise"] * f
        return D, drop, rise

    sag = rs.uniform(0.005, 0.012)
    tnoise = _N1(rs, -1.0, w + 1.0, 0.3, 0.0015)
    S_ZONE = 0.15
    nx, ny = len(xs), len(sfl)
    top, bot = {}, {}
    rrn = _sub(rs)
    rough = _N1(rrn, -2.0, w + d + 40.0, 0.018, 0.005)
    for j, sF in enumerate(sfl):
        for i, x in enumerate(xs):
            y = -d + sF
            sL, sR = x, w - x
            free = y < -0.004
            zt, zb = t, 0.0
            k = max(0.0, -y / d)
            zt -= 0.015 * d * k + sag * k * k
            zb -= sag * k * k
            zt += tnoise(x + 0.37 * y)
            bev_row = (j == 0) or (free and (i == 0 or i == nx - 1))
            if bev_row:
                zt -= b
                zb += b
            if drip and free and y < -0.03:
                if is_groove(sF) and g0 <= sL and g0 <= sR:
                    zb += gd
                elif (is_groove(sL) or is_groove(sR)) and sF >= g0:
                    zb += gd
            nx_, ny_ = x, y
            # desconchados: remapeo hacia dentro + caída del canto superior + levantamiento del inferior
            Df, drf, rif = spall_D("F", x)
            if Df > 0 and sF < S_ZONE:
                sF2 = Df + sF * (S_ZONE - Df) / S_ZONE
                ny_ = -d + sF2
                q = max(0.0, 1.0 - sF / 0.075) ** 0.8
                zt -= drf * q
                zb += rif * q
                if drip and Df > 0.6 * g0 and is_groove(sF):
                    zb -= gd
                if sF < 0.075:  # rugosidad de la fractura (ruido suave: las filas no se cruzan)
                    zt += rough(x + 2.0 * sF) * q
                    zb += rough(x - 3.0 * sF + 5.0) * 0.7 * q
                    ny_ += rough(x + 11.0) * 0.6 * q
            if free:
                for e, se in (("L", sL), ("R", sR)):
                    De, dre, rie = spall_D(e, d - sF)
                    if De > 0 and se < S_ZONE:
                        se2 = De + se * (S_ZONE - De) / S_ZONE
                        nx_ = se2 if e == "L" else w - se2
                        q = max(0.0, 1.0 - se / 0.075) ** 0.8
                        zt -= dre * q
                        zb += rie * q
                        if drip and De > 0.6 * g0 and is_groove(se) and sF >= g0:
                            zb -= gd
                        if se < 0.075:
                            zt += rough(sF + 2.0 * se + 20.0) * q
                            zb += rough(sF - 3.0 * se + 27.0) * 0.7 * q
                            nx_ += rough(sF + 31.0) * 0.6 * q * (1.0 if e == "L" else -1.0)
            if crack is not None and abs(sF - crack["s"]) < 0.003:
                ny_ += crack["wob"](x)
                if abs(sF - crack["s"]) < 1e-6:
                    zt -= crack["dep"] * _ss((x - crack["a"]) / 0.08) * _ss((crack["b"] - x) / 0.08)
            if j == 0 and (i == 0 or i == nx - 1):  # esquinas verticales achaflanadas
                nx_ += 0.006 if i == 0 else -0.006
                ny_ += 0.006
            if zt - zb < 0.03:  # muesca honda sobre la fila del bisel o el gotero: las caras no se cruzan
                zm = 0.5 * (zt + zb)
                zt, zb = zm + 0.015, zm - 0.015
            top[i, j] = Vector((nx_, ny_, zt))
            bot[i, j] = Vector((nx_, ny_, zb))
    mb = MB()
    vt = {k: mb.bm.verts.new(v) for k, v in top.items()}
    vb = {k: mb.bm.verts.new(v) for k, v in bot.items()}
    for j in range(ny - 1):
        for i in range(nx - 1):
            mb.face([vt[i, j], vt[i + 1, j], vt[i + 1, j + 1], vt[i, j + 1]], "concrete")
            mb.face([vb[i, j], vb[i, j + 1], vb[i + 1, j + 1], vb[i + 1, j]], "concrete")
    for i in range(nx - 1):
        for j, rev in ((0, False), (ny - 1, True)):
            f = [vt[i, j], vb[i, j], vb[i + 1, j], vt[i + 1, j]]
            mb.face(f[::-1] if rev else f, "concrete")
    for j in range(ny - 1):
        for i, rev in ((0, True), (nx - 1, False)):
            f = [vt[i, j], vb[i, j], vb[i, j + 1], vt[i, j + 1]]
            mb.face(f[::-1] if rev else f, "concrete")
    # varillas asomando en los desconchados
    if rebar:
        rr = _sub(rs)
        for s in sp:
            if s["D"] < 0.035:
                continue
            ztb = t - 0.015 * d - sag - 0.03
            if s["e"] == "F":
                for xb in np.arange(s["c"] - s["hw"] * 0.7, s["c"] + s["hw"] * 0.7, 0.15):
                    Dl = spall_D("F", xb)[0]
                    if Dl < 0.03:
                        continue
                    y_in, y_out = -d + Dl + 0.25, -d + Dl - rr.uniform(0.0, 0.07)
                    tip = Vector((xb, y_out - 0.01, ztb - rr.uniform(0.02, 0.09)))
                    pts = [Vector((xb, y_in, ztb)), Vector((xb, -d + Dl + 0.02, ztb)), Vector((xb, y_out, ztb - 0.004)), tip]
                    _rebar_run(mb, _fillet(pts, 0.02), rr, r=0.005)
                if s["D"] > 0.045:
                    yb_ = -d + 0.04
                    _rebar_run(mb, [Vector((s["c"] - s["hw"] * 0.8, yb_, 0.028)), Vector((s["c"] + s["hw"] * 0.8, yb_, 0.028))],
                               rr, r=0.004, bulge=0.006)
            else:
                xe = 0.0 if s["e"] == "L" else w
                sgn = 1.0 if s["e"] == "L" else -1.0
                for sfb in np.arange(d - s["c"] - s["hw"] * 0.7, d - s["c"] + s["hw"] * 0.7, 0.15):
                    Dl = spall_D(s["e"], d - sfb)[0]
                    if Dl < 0.03 or sfb < 0.05:
                        continue
                    yy = -d + sfb
                    x_in = xe + sgn * (Dl + 0.25)
                    x_out = xe + sgn * (Dl - rr.uniform(0.0, 0.06))
                    pts = [Vector((x_in, yy, ztb + 0.012)), Vector((xe + sgn * (Dl + 0.02), yy, ztb + 0.012)),
                           Vector((x_out, yy, ztb + 0.006)), Vector((x_out - sgn * 0.01, yy, ztb - rr.uniform(0.02, 0.07)))]
                    _rebar_run(mb, _fillet(pts, 0.02), rr, r=0.005)
    # arena y polvo en la junta con el muro, y escombro suelto sobre la losa
    rdb = _sub(rs)
    Mw = Matrix(((0.0, 1.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
    for _ in range(int(rdb.integers(1, 3))):
        a_ = rdb.uniform(0.03, w * 0.6)
        b_ = min(a_ + rdb.uniform(0.35, 1.1), w - 0.03)
        if b_ - a_ > 0.2:
            _sand_wedge(mb, Mw, 0.0, t, a_, b_, rdb, wd=rdb.uniform(0.05, 0.12), hd=rdb.uniform(0.012, 0.03), dirn=-1.0,
                        lens=True)
    for _ in range(int(rdb.poisson(3 + 6 * spalled))):
        sz = rdb.uniform(0.01, 0.045)
        yy = -rdb.uniform(0.05, d - 0.12)
        kk = -yy / d
        _chunk(mb, (rdb.uniform(0.08, w - 0.08), yy, t - 0.015 * d * kk - sag * kk * kk + 0.08 * sz), sz, rdb, flat=0.7)
    mb.meta = dict(kind="balcony_slab", w=w, d=d, t=t, top_z=t, embed=embed,
                   crack=None if crack is None else (round(float(crack["s"] - d), 3), round(float(crack["a"]), 3),
                                                     round(float(crack["b"]), 3)),
                   spalls=[(s["e"], round(float(s["c"]), 3), round(float(s["D"]), 3)) for s in sp])
    return mb


# =====================================================================================================================
# CANALÓN Y BAJANTE
# =====================================================================================================================
def gutter(path, seed=0, *, radius=0.06, hanger_step=0.8, fault="auto", dirt=True, outlets=(), section_len=3.0,
           mat="metal_paint"):
    """Canalón de media caña (Ø0,12, chapa de 2,5 mm con bocel enrollado en el borde frontal) barrido por `path`. Devuelve MB.
    path: [(x, y, z)] eje del canalón a la altura del borde superior (centro de la media caña). La fascia queda a la
    IZQUIERDA del sentido de avance (recorrido en +X -> fascia en +Y), con su cara a meta['fascia_offset'] = R + 0,0265
    (0,0865 m) del eje: las pestañas de los ganchos quedan 1 mm por delante (sin caras coplanares con la fascia).
    Quiebres del recorrido (esquinas de alero a 90° o en ángulo): inglete real + pieza de esquina con dos bocas.
    Ganchos de fleje cada `hanger_step` (0,8 m) abrazando el canalón y atornillados a la fascia; uniones (manguitos)
    cada `section_len`; tapas en los extremos; tierra y matas de pasto en el fondo (dirt).
    fault: 'fallen' (una sección se soltó y cuelga girada desde su unión), 'bent' (un tramo vencido y volcado hacia
    fuera, con sus ganchos estirados), 'none' o 'auto' (según la semilla).
    outlets: distancias a lo largo del recorrido donde va una boquilla de bajante. meta['outlets'] = puntos (mundo) del
    extremo inferior de cada boquilla, en el mismo orden (úsalos como `top` de `downpipe`). Una sección con boquilla
    nunca es la que se cae."""
    rs = rng(seed)
    R, th = radius, 0.0025
    pth = _Path(path)
    L = pth.L
    na = 14
    outer = [(R * math.cos(math.pi + math.pi * i / na), R * math.sin(math.pi + math.pi * i / na)) for i in range(na + 1)]
    inner = [((R - th) * math.cos(math.pi + math.pi * i / na), (R - th) * math.sin(math.pi + math.pi * i / na))
             for i in range(na, -1, -1)]
    base_prof = outer + inner
    angs = [math.pi + math.pi * i / na for i in range(na + 1)] + [math.pi + math.pi * i / na for i in range(na, -1, -1)]
    # quiebres del recorrido (esquinas de alero): inglete + pieza de esquina con dos manguitos
    corner_i = []
    for i in range(1, len(pth.P) - 1):
        t0 = (pth.P[i] - pth.P[i - 1]).normalized()
        t1 = (pth.P[i + 1] - pth.P[i]).normalized()
        if t0.dot(t1) < math.cos(math.radians(1.0)):
            corner_i.append(i)
    corners = [pth.cum[i] for i in corner_i]

    def off_corner(x, clr):
        for c in corners:
            if abs(x - c) < clr:
                return c + clr if c + clr < L - 0.4 else c - clr
        return x

    joints = sorted({round(off_corner(section_len * k, 0.3), 6) for k in range(1, int(L / section_len) + 1)
                     if section_len * k < L - 0.4})
    joints = [j for j in joints if 0.4 < j < L - 0.4]
    if fault == "auto":
        fault = ("fallen", "bent")[int(rs.integers(0, 2))]
    if fault == "fallen" and not joints:
        joints = [off_corner(L * rs.uniform(0.4, 0.6), 0.3)]
    bounds = [0.0] + joints + [L]
    secs = list(zip(bounds, bounds[1:]))
    fallen, bent = None, None
    if fault == "fallen":
        def can_fall(k):  # ni la sección con boquilla ni una que doble una esquina (giraría contra el muro)
            a_, b_ = secs[k]
            return not any(a_ < so < b_ for so in outlets) and not any(a_ < c < b_ for c in corners)
        fallen = len(secs) - 1 if rs.random() < 0.6 else 0
        if not can_fall(fallen):
            fallen = 0 if fallen == len(secs) - 1 else len(secs) - 1
            if not can_fall(fallen):
                fallen, fault = None, "bent"
    if fault == "bent":
        i = int(rs.integers(0, len(secs)))
        a, b = secs[i]
        span = min(b - a - 0.2, rs.uniform(1.0, 2.0))
        c = rs.uniform(a + 0.1 + span / 2, max(b - 0.1 - span / 2, a + 0.1 + span / 2 + 1e-3))
        bent = (c - span / 2, c + span / 2, rs.uniform(0.07, 0.15), rs.uniform(0.2, 0.45))
    dents = [(rs.uniform(0, L), rs.uniform(math.pi * 1.15, math.pi * 1.85), rs.uniform(0.005, 0.014), rs.uniform(0.06, 0.13))
             for _ in range(int(rs.poisson(L / 1.1)))]
    # ganchos: cada hanger_step; ~12 % perdidos (queda la pestaña); el canalón cuelga entre los que quedan
    hangers = []
    sh = hanger_step / 2
    while sh < L - 0.08:
        if sh >= 0.08 and not any(abs(sh - j) < 0.08 for j in joints):
            hangers.append((off_corner(sh, 0.24), rs.random() < 0.12))
        sh += hanger_step
    hangers = sorted((s, lost) for s, lost in hangers if 0.08 <= s <= L - 0.08 and not any(abs(s - j) < 0.08 for j in joints))
    held = [h for h, lost in hangers if not lost]
    spans = [(a, b, rs.uniform(0.002, 0.006) * ((b - a) / hanger_step) ** 2) for a, b in zip(held, held[1:])]

    def frame(s, deformed=True):
        """(P, T, U, S) en la estación s. En un quiebre del recorrido T es la bisectriz y S se alarga 1/cos(θ/2): las
        secciones de esquina quedan en el plano de inglete (sin pinzamiento ni autointersección)."""
        P = pth.at(s)
        T = pth.tang(s)
        msc = 1.0
        for ci in corner_i:
            if abs(s - pth.cum[ci]) < 1e-5:
                t0 = (pth.P[ci] - pth.P[ci - 1]).normalized()
                t1 = (pth.P[ci + 1] - pth.P[ci]).normalized()
                T = (t0 + t1).normalized()
                msc = 1.0 / max(math.cos(math.acos(max(min(t0.dot(t1), 1.0), -0.9)) / 2), 0.4)
                break
        U = ZV - T * ZV.dot(T)
        U.normalize()
        if deformed:
            for a, b, sg in spans:
                if a < s < b:
                    P = P - ZV * (sg * math.sin(math.pi * (s - a) / (b - a)))
                    break
        if deformed and bent is not None and bent[0] < s < bent[1]:
            q = math.sin(math.pi * (s - bent[0]) / (bent[1] - bent[0]))
            P = P - ZV * (bent[2] * q)
            U = Matrix.Rotation(-bent[3] * q, 3, T) @ U
        return P, T, U, T.cross(U) * msc

    def prof_at(s):
        Q = [list(p) for p in base_prof]
        for (sd, ad, dep, sz) in dents:
            e = 1.0 - abs(s - sd) / sz
            if e <= 0:
                continue
            for k, a in enumerate(angs):
                ea = 1.0 - abs(a - ad) / 0.5
                if ea > 0:
                    f = _ss(e) * _ss(ea) * dep
                    Q[k][0] -= math.cos(a) * f
                    Q[k][1] -= math.sin(a) * f
        return Q

    mb = MB()
    meta_out = []
    for si, (a, b) in enumerate(secs):
        sa, sb_ = a + (0.002 if si > 0 else 0.0), b - (0.002 if si < len(secs) - 1 else 0.0)
        extra = []
        if bent is not None:
            extra = list(np.linspace(bent[0], bent[1], 9))
        # cada abolladura con 5 estaciones (centro, mitades y bordes): chapa de 2,5 mm sin cuadriláteros alabeados
        dex = [d[0] + k * d[3] for d in dents for k in (-1.0, -0.5, 0.0, 0.5, 1.0)]
        ss = pth.stations(sa, sb_, 0.15, extra=extra + dex, clear=0.075)
        part = MB()
        frs = [frame(s) for s in ss]
        rings = []
        for k, s in enumerate(ss):
            P, T, U, S = frs[k]
            rings.append([P + S * x + U * y for x, y in prof_at(s)])
        _loft(part, rings, mat)
        # bocel del borde frontal
        _ptube(part, [fr[0] + fr[3] * (R + 0.0035) + fr[2] * 0.0035 for fr in frs], 0.0045, None, seg=8, mat=mat)
        # tapas de extremo
        for s_end, sgn, is_end in ((sa, 1.0, si == 0), (sb_, -1.0, si == len(secs) - 1)):
            if not is_end:
                continue
            P, T, U, S = frame(s_end)
            ro = R + 0.002
            ol = [(ro * math.cos(math.pi + math.pi * i / 12), ro * math.sin(math.pi + math.pi * i / 12)) for i in range(13)]
            ol += [(ro, 0.004), (-ro, 0.004)]
            t0, t1 = (-0.0015, 0.004) if sgn > 0 else (-0.004, 0.0015)  # la boca del canalón queda 1,5 mm dentro
            _loft(part, [[P + S * x + U * y + T * t0 for x, y in ol], [P + S * x + U * y + T * t1 for x, y in ol]], mat)
        # boquillas
        for oi, so in enumerate(outlets):
            if sa + 0.08 < so < sb_ - 0.08 and si != fallen:
                P, T, U, S = frame(so)
                _ptube(part, [P - U * (R - 0.01), P - U * (R + 0.09)], 0.042, 0.038, seg=16, mat=mat)
                _ptube(part, [P - U * (R - 0.004), P - U * (R + 0.018)], 0.049, 0.039, seg=16, mat=mat)
                meta_out.append((oi, P - U * (R + 0.09)))
        # tierra y pasto
        if dirt and si != fallen:
            rd = _sub(rs)
            for _ in range(int(rd.poisson((sb_ - sa) / 1.6))):
                l = rd.uniform(0.3, 1.2)
                c0 = rd.uniform(sa + 0.05, max(sb_ - 0.05 - l, sa + 0.06))
                c1 = min(c0 + l, sb_ - 0.03)
                for c in corners:  # los extremos de la tierra no caen junto al inglete
                    if abs(c0 - c) < 0.06:
                        c0 = c + 0.06
                    if abs(c1 - c) < 0.06:
                        c1 = c - 0.06
                if c1 - c0 < 0.1:
                    continue
                fill0 = rd.uniform(0.012, 0.028)
                dss = pth.stations(c0, c1, 0.08, clear=0.045)
                Rd = R - th - 0.0015
                dirt_rings = []
                for s in dss:
                    e = _ss((s - c0) / 0.12) * _ss((c1 - s) / 0.12)
                    fill = 0.003 + fill0 * e + rd.normal(0, 0.0015) * e
                    yf = -Rd + fill
                    al = math.acos(max(min(-yf / Rd, 1.0), -1.0))
                    P, T, U, S = frame(s)
                    pts2 = [(Rd * math.cos(-math.pi / 2 - al + 2 * al * i / 8), Rd * math.sin(-math.pi / 2 - al + 2 * al * i / 8))
                            for i in range(9)]
                    pts2 += [(0.0, yf + rd.uniform(0.0, 0.004) * e)]
                    dirt_rings.append([P + S * x + U * y for x, y in pts2])
                _loft(part, dirt_rings, "sand")
                for _ in range(int(rd.integers(0, 3))):
                    s = rd.uniform(c0 + 0.1, max(c1 - 0.1, c0 + 0.11))
                    P, T, U, S = frame(s)
                    base = P + U * (-Rd + fill0 * 0.8)
                    for _b in range(int(rd.integers(5, 10))):
                        ang = rd.uniform(0, 2 * math.pi)
                        lean = Vector((math.cos(ang), math.sin(ang), 0.0)) * rd.uniform(0.05, 0.4)
                        hgt = rd.uniform(0.06, 0.2)
                        p0 = base + (S * rd.normal(0, 0.01) + T * rd.normal(0, 0.015))
                        p1 = p0 + (U + lean * 0.5) * hgt * 0.5
                        p2 = p1 + (U + lean * 1.6).normalized() * hgt * 0.55
                        bw = rd.uniform(0.002, 0.004)
                        Xb = (U.cross(lean.normalized() if lean.length > 1e-6 else S)).normalized() * bw
                        tri0 = [part.bm.verts.new(p0 + Xb), part.bm.verts.new(p0 - Xb), part.bm.verts.new(p0 + lean.normalized() * bw * 0.6)]
                        tri1 = [part.bm.verts.new(p1 + Xb * 0.6), part.bm.verts.new(p1 - Xb * 0.6),
                                part.bm.verts.new(p1 + lean.normalized() * bw * 0.4)]
                        tip = part.bm.verts.new(p2)
                        part.face(tri0[::-1], "vegetation")
                        for q in range(3):
                            qq = (q + 1) % 3
                            part.face([tri0[q], tri0[qq], tri1[qq], tri1[q]], "vegetation")
                            part.face([tri1[q], tri1[qq], tip], "vegetation")
        if si == fallen:  # sección suelta: gira desde su unión y cae, con torsión
            piv_s = sa if si > 0 else sb_
            P0, T0, U0, S0 = frame(piv_s, deformed=False)
            free_s = sb_ if si > 0 else sa
            ang = rs.uniform(0.35, 0.65)
            rot = Matrix.Rotation(ang, 4, S0)
            Pf = pth.at(free_s)
            if (rot @ (Pf - P0)).z > 0:
                rot = Matrix.Rotation(-ang, 4, S0)
            tw = Matrix.Rotation(rs.uniform(0.25, 0.6), 4, T0)
            Mf = Matrix.Translation(P0) @ rot @ tw @ Matrix.Translation(-P0)
            mb.join(part, Mf)
        else:
            mb.join(part)
        part.bm.free()
    # manguitos de unión y piezas de esquina (inglete con un manguito en cada brazo)
    Ro, Ri = R + 0.003, R - 0.001
    do, di = math.asin(0.004 / Ro), math.asin(0.004 / Ri)
    sl = [(Ro * math.cos(math.pi - do + (math.pi + 2 * do) * i / na), Ro * math.sin(math.pi - do + (math.pi + 2 * do) * i / na))
          for i in range(na + 1)]
    sl += [(Ri * math.cos(math.pi - di + (math.pi + 2 * di) * i / na), Ri * math.sin(math.pi - di + (math.pi + 2 * di) * i / na))
           for i in range(na, -1, -1)]
    sleeves = [(sj - 0.05, sj, sj + 0.05) for sj in joints]
    for c in corners:
        # dos bocas de la pieza de esquina y su cuerpo sobre el inglete (separados 5 mm: se leen como rebordes)
        sleeves += [(c - 0.17, c - 0.12, c - 0.07), (c + 0.07, c + 0.12, c + 0.17)]
        sleeves.append(tuple(pth.stations(c - 0.065, c + 0.065, 0.2)))
    for sts in sleeves:
        rings = []
        for s in sts:
            P, T, U, S = frame(s)
            rings.append([P + S * x + U * y for x, y in sl])
        _loft(mb, rings, mat)
    # ganchos de fleje
    Rh = R + 0.0035
    sp2 = [(R - 0.002, 0.0115), (R + 0.0095, 0.0115), (R + 0.0095, -0.004)]
    for i in range(13):
        a = -0.15 - (math.pi - 0.3) * i / 12
        sp2.append((Rh * math.cos(a), Rh * math.sin(a)))
    sp2 += [(-Rh, 0.004), (-Rh, 0.03), (-(R + 0.024), 0.05), (-(R + 0.024), 0.10)]
    n_tab = 2
    strap = [(-0.0015, -0.011), (0.0015, -0.011), (0.0015, 0.011), (-0.0015, 0.011)]
    fall_rng = secs[fallen] if fallen is not None else None
    rh = _sub(rs)
    for s, lost in hangers:
        P0, T0, U0, S0 = frame(s, deformed=False)
        P1, T1, U1, S1 = frame(s, deformed=True)
        broken_h = lost or (fall_rng is not None and fall_rng[0] < s < fall_rng[1])
        if broken_h or (bent is not None and bent[0] < s < bent[1] and rh.random() < 0.35):
            pts = [P0 + S0 * x + U0 * y for x, y in sp2[-n_tab - 1:]]  # queda solo la pestaña en la fascia
            pts[0] = pts[0] + U0 * 0.012
        else:
            pts = [P1 + S1 * x + U1 * y for x, y in sp2[:-n_tab]] + [P0 + S0 * x + U0 * y for x, y in sp2[-n_tab:]]
        _sweep(mb, strap, pts, [T0] * len(pts), "metal_rust")
        hp = P0 + S0 * (-(R + 0.024) + 0.001) + U0 * 0.08
        mb.cyl(hp, hp + S0 * 0.004, 0.0055, seg=8, mat="metal_rust")
    mb.meta = dict(kind="gutter", fault=fault, length=L, outlets=[tuple(p) for _, p in sorted(meta_out, key=lambda q: q[0])],
                   fascia_offset=R + 0.0265, corners=[tuple(pth.P[i]) for i in corner_i])
    return mb


def downpipe(top, bottom, wall_offset=0.06, seed=0, *, radius=0.05, mat="plastic", fault="auto", clamp_step=1.6):
    """Bajante Ø0,10 (pared 4 mm, hueca) del punto `top` (p. ej. meta['outlets'] de `gutter`) al punto `bottom` (eje de la
    bajante a nivel de suelo). El MURO está detrás de la bajante, en y = bottom.y + wall_offset (fachada hacia -Y). Para
    otra fachada, construye en este marco local y gira el MB con `MB.join(mb, matriz)` (top/bottom en coordenadas locales).
    - La bajante arranca 4 cm POR ENCIMA de `top` y recibe la boquilla del canalón (Ø ext. 0,084 dentro del Ø int. 0,092),
      con un casquillo en la boca: no hay unión a tope ni caras coplanares con la boquilla.
    - Si `top` no está sobre el eje, cuello de cisne con dos codos (curvas reales con casquillos) hasta pegarse al muro;
      si el desfase es pequeño (<= 3 cm) el primer tramo se inclina y recupera el eje en 0,6 m.
    - Casquillos de unión cada ~2,5 m, abrazaderas cada `clamp_step` con oreja, perno, ménsula y placa atornillada al muro.
    - Zapata de salida al pie (codo hacia fuera, boca abierta a 6 cm del suelo).
    - fault: 'missing' (falta un tramo: bordes rotos dentados y una abrazadera vacía), 'broken' (tramo partido que cuelga
      girado desde su casquillo superior), 'shoe' (zapata arrancada tirada en el suelo y tubo roto al pie), 'none' o
      'auto' (missing/broken si la bajante es larga; si es corta, 'shoe').
    meta: wall_y, path (polilínea del eje), fault."""
    rs = rng(seed)
    Tp, Bp = _v(top), _v(bottom)
    Tq = Tp + ZV * 0.04  # boca de la bajante: la boquilla entra 4 cm
    R, Ri = radius, radius - 0.004
    y_wall = Bp.y + wall_offset
    up_pts = [Tq]
    dxy = Vector((Tp.x - Bp.x, Tp.y - Bp.y, 0.0))
    straight = dxy.length <= 0.03
    if not straight:
        p1 = Tq - ZV * 0.11
        # el desvío baja a 45° (o más suave si es corto: al menos 0,30 m de altura) para que el radio de los codos nunca
        # quede por debajo del radio del tubo (un desvío de 3 cm a 45° daba un codo que se cruzaba consigo mismo)
        p2 = Vector((Bp.x, Bp.y, p1.z - max(dxy.length, 0.3)))
        up_pts = [Tq, p1, p2]
    z_v_top = up_pts[-1].z
    z_shoe = Bp.z + 0.28
    if z_v_top - z_shoe < 0.3:
        z_shoe = z_v_top - 0.3
    shoe_end = Vector((Bp.x, Bp.y - 0.11, Bp.z + 0.06))
    full = up_pts + [Vector((Bp.x, Bp.y, z_shoe)), shoe_end]
    MR = "metal_rust"
    mb = MB()
    vtop, vbot = z_v_top - 0.12, z_shoe + 0.15
    if fault == "auto":
        fault = ("missing", "broken")[int(rs.integers(0, 2))] if vtop - vbot > 1.6 else "shoe"
    gap = None
    if fault in ("missing", "broken") and vtop - vbot > 1.2:
        ln = rs.uniform(0.45, min(1.1, (vtop - vbot) * 0.45))
        z2 = rs.uniform(vbot + ln + 0.3, vtop - 0.3)
        gap = (z2 - ln, z2)
    elif fault != "none":
        fault = "shoe"
    wob = _N1(rs, Bp.z, Tq.z, 1.1, 0.007)
    # hacia el muro (Y) el desplome se limita para que el tubo no toque la placa de las abrazaderas
    wy_amp = max(0.0, min(0.004, y_wall - 0.006 - (Bp.y + R)))

    def wy(z):
        return wob(z + 7.0) * (wy_amp / 0.007)

    def axis(z):
        """Eje de la bajante a la altura z (desplome suave; en una bajante recta con desfase pequeño, el primer tramo
        se inclina desde el centro de la boquilla y recupera el eje en 0,6 m)."""
        k = max(0.0, 1.0 - (Tq.z - z) / 0.6) if straight else 0.0
        return Vector((Bp.x + wob(z) * (1.0 - k) + dxy.x * k, Bp.y + wy(z) * (1.0 - k) + dxy.y * k, z))

    def vrun(z_hi, z_lo, step=0.5):
        n = max(1, int(math.ceil((z_hi - z_lo) / step)))
        zs_ = list(np.linspace(z_hi, z_lo, n + 1))
        if straight and z_hi > Tq.z - 0.6 and n > 1:  # más puntos en el tramo inclinado
            zs_ = sorted(set(zs_) | {z for z in (Tq.z - 0.2, Tq.z - 0.4, Tq.z - 0.6) if z_lo < z < z_hi}, reverse=True)
        return [axis(z) for z in zs_]

    def jag(amp):
        return list(rs.uniform(0.0, amp, 16))

    # tramo superior (codos + vertical hasta el hueco o hasta la zapata)
    upper = _fillet(up_pts + [Vector((Bp.x, Bp.y, z_v_top - 0.25))], 0.08, nseg=5) if len(up_pts) > 1 else [Tq]
    z_lo1 = gap[1] if gap else z_shoe
    run1 = upper[:-1] + vrun(upper[-1].z if len(up_pts) > 1 else Tq.z, z_lo1)
    if gap is None and fault == "shoe":  # zapata arrancada: el tubo termina roto y la zapata yace en el suelo
        z_cut = z_shoe + rs.uniform(0.06, 0.3)
        run1 = [q for q in run1 if q.z > z_cut + 0.03] + [axis(z_cut)]  # nada por debajo del corte (sin pliegues)
        _ptube(mb, run1, R, Ri, seg=16, mat=mat, jag1=jag(0.035))
        piece = MB()
        _ptube(piece, _fillet([Vector((-0.16, 0.0, R)), Vector((0.0, 0.0, R)), Vector((0.1, 0.1, R))], 0.09, nseg=5), R, Ri,
               seg=16, mat=mat, jag0=jag(0.03))
        mb.join(piece, Matrix.Translation((Bp.x + rs.uniform(0.15, 0.35), Bp.y - rs.uniform(0.2, 0.45), Bp.z - 0.004)) @
                Matrix.Rotation(rs.uniform(0, 2 * math.pi), 4, "Z"))
        piece.bm.free()
    elif gap is None:  # solo se redondea el pie (el cuello de cisne ya viene redondeado: no se redondea dos veces)
        run1 = run1[:-2] + _fillet([run1[-2], Vector((Bp.x, Bp.y, z_shoe)), shoe_end], 0.09, nseg=5)
        _ptube(mb, run1, R, Ri, seg=16, mat=mat)
    else:
        _ptube(mb, run1, R, Ri, seg=16, mat=mat, jag1=jag(0.03))
        if fault == "broken":  # el tramo partido cuelga del casquillo de arriba, girado hacia fuera
            pv = Vector((Bp.x, Bp.y, gap[1]))
            piece = MB()
            seg_pts = [pv - ZV * 0.012, pv - ZV * ((gap[1] - gap[0]) * 0.5), pv - ZV * (gap[1] - gap[0] + 0.25)]
            _ptube(piece, seg_pts, R, Ri, seg=16, mat=mat, jag0=jag(0.02), jag1=jag(0.035))
            ang = rs.uniform(0.12, 0.26)
            rot = Matrix.Rotation(-ang, 4, "X") @ Matrix.Rotation(rs.normal(0, 0.08), 4, "Y")
            mb.join(piece, Matrix.Translation(pv) @ rot @ Matrix.Translation(-pv))
            piece.bm.free()
        lower = vrun(gap[0], z_shoe + 0.0)[:-1] + [Vector((Bp.x, Bp.y, z_shoe)), shoe_end]
        _ptube(mb, _fillet(lower, 0.09, nseg=5), R, Ri, seg=16, mat=mat, jag0=jag(0.03))
    # casquillos: en codos y cada ~2,5 m
    # casquillo de la boca (sobresale 4 mm del canto del tubo: sin caras coplanares) y del codo inferior
    sockets = [(axis(Tq.z) + ZV * 0.004, axis(Tq.z - 0.065))] if straight else [(Tq + ZV * 0.004, Tq - ZV * 0.065)]
    if len(up_pts) > 1:
        sockets += [(up_pts[2] + (up_pts[1] - up_pts[2]).normalized() * 0.09,
                     up_pts[2] + (up_pts[1] - up_pts[2]).normalized() * 0.16)]
    z = z_v_top - 0.35
    while z > z_shoe + 0.4:
        if not (gap and gap[0] - 0.1 < z < gap[1] + 0.05):
            sockets.append((axis(z + 0.04), axis(z - 0.04)))
        z -= rs.uniform(2.2, 2.8)
    if gap:
        sockets.append((Vector((Bp.x, Bp.y, gap[1] + 0.13)), Vector((Bp.x, Bp.y, gap[1] + 0.055))))
    if fault != "shoe":
        sockets.append((Vector((Bp.x, Bp.y, z_shoe + 0.11)), Vector((Bp.x, Bp.y, z_shoe + 0.04))))
    for a, b in sockets:
        _ptube(mb, [a, b], R + 0.0055, R - 0.0015, seg=16, mat=mat)
    # abrazaderas
    z = z_v_top - 0.3
    while z > z_shoe + 0.25:
        if any((a.z + 0.05 > z > b.z - 0.05) for a, b in sockets):
            z -= 0.12
            continue
        in_gap = gap is not None and gap[0] - 0.05 < z < gap[1] + 0.03
        cx, cy = axis(z).x, axis(z).y
        c = Vector((cx, cy, z))
        # orejas: del anillo hasta DENTRO de la placa del muro (la atraviesan: sin caras coplanares con ella)
        e1 = min(cy + R + 0.016, y_wall - 0.0015)
        if not (in_gap and fault == "broken"):
            _ptube(mb, [c + ZV * 0.014, c - ZV * 0.014], R + 0.0045, R - 0.0015, seg=16, mat=MR)
            for sx in (-1, 1):
                mb.box((cx + sx * 0.004 - 0.003, cy + R - 0.002, z - 0.012), (cx + sx * 0.004 + 0.003, e1, z + 0.012),
                       MR, bevel=0.0012, seg=1)
            yb_ = min(cy + R + 0.008, e1 - 0.004)
            mb.cyl((cx - 0.012, yb_, z), (cx + 0.012, yb_, z), 0.0035, seg=6, mat=MR)
        # anillo arrancado (tramo partido): quedan la placa y, si hay holgura, la ménsula
        y0 = cy + R + 0.012
        if y_wall - 0.0015 - (cy + R + 0.016) > 0.003:  # muro lejano: ménsula entre las orejas y la placa
            mb.box((cx - 0.006, y0, z - 0.009), (cx + 0.006, y_wall + 0.01, z + 0.009), MR, bevel=0.0015, seg=1)
        mb.box((cx - 0.025, y_wall - 0.005, z - 0.032), (cx + 0.025, y_wall + 0.003, z + 0.032), MR, bevel=0.0015, seg=1)
        for dz in (-0.021, 0.021):
            mb.cyl((cx, y_wall - 0.0045, z + dz), (cx, y_wall - 0.0085, z + dz), 0.0055, seg=6, mat=MR)
        z -= clamp_step
    mb.meta = dict(kind="downpipe", wall_y=y_wall, path=[tuple(p) for p in full], fault=fault, gap=gap)
    return mb
