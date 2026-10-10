"""roofing.py — GRUPO G3 · CUBIERTAS del kit modular BLACKISLE (estructura de madera, teja curva, lámina ondulada, tablones).

Todas las funciones públicas devuelven un `MB`. Sistema de coordenadas común a las 4 cubiertas:
  · planta w (X) x d (Y) centrada en el origen = cara EXTERIOR de los muros que reciben la cubierta;
  · z = 0 es la corona del muro / losa de azotea: la solera (0,14 x 0,10) apoya ahí;
  · la cumbrera corre en X (si kind='hip' y w < d todo se construye girado 90° para que la cumbrera vaya en Y);
  · 'gable': vertientes hacia -Y y +Y, hastiales en x = ±w/2 con vuelo de remate `rake` (por defecto = overhang, máx 0,45);
  · 'hip': 4 vertientes con la misma pendiente; limatesas desde las esquinas del alero hasta los extremos de la cumbrera.

Pila constructiva (perpendicular al faldón, medida desde el plano superior de los cabios, `roof_top()`):
  cabios 0,05 x 0,15 a `spacing` con caja de apoyo (pájaro) sobre la solera, cola expuesta con corte curvo, tabla de cumbrera 0,04;
  rastreles de teja 0,05 x 0,025 a +1 mm (n 0,001–0,026) · correas de lámina/tablón 0,075 x 0,05 (n 0,001–0,051);
  la teja apoya en n = 0,027 (TILE_N), la lámina y los tablones en n = 0,052 (SHEET_N). Nada se toca coplanarmente (>= 1 mm).

Láminas intencionales (aristas abiertas, `side: DoubleSide` en Three.js): SOLO 'roof_metal' y 'roof_metal_light'
(láminas onduladas, cumbrera doblada y tapajuntas de remate). Todo lo demás (madera, teja, mortero, tornillos) son sólidos
cerrados: 0 aristas no-manifold (verificado con `--sweep` del test: 152 mallas, 4 semillas x varias medidas/cubiertas).

Uso por el constructor (todo con las MISMAS w, d, pendiente y vuelo; colocar con MB.join(m, Matrix.Translation((cx, cy, z_corona)))):
  APT (teja):   sp = damage_spot('hip', w, d, 26, 0.6, seed, 0.7)
                roof_frame('hip', w, d, 26, 0.6, seed, damage=0.7, spot=sp)  +  barrel_tiles(w, d, 'hip', 26, 0.6, seed, hole=sp)
  CAB_1/CAB_2:  tr = damage_spot('gable', w, d, p, ov, seed, 0.6)
                roof_frame('gable', w, d, p, ov, seed, cover='sheet', damage=0.6, spot=tr) + corrugated_roof(w, d, p, ov, seed, torn=tr)
  CAB_3:        roof_frame('gable', w, d, p, ov, seed, cover='boards', tails=False) + board_roof_stepped(w, d, p, ov, seed)
  roof_top(...) da la cota del plano de cabios en (x, y) para cerrar hastiales; ridge_height(...) la de la cumbrera.

Triángulos medidos (vitrina del test):
  roof_frame 7–15 k (cabaña) · 26–33 k (APT hip 12 x 9 con daño)
  barrel_tiles (seg=6, incluye caballetes y mortero): gable 8 x 6 ~163 k · hip 7,2 x 10,8 ~265 k · hip 12 x 9 ~338 k (seg=4/5 para LOD: -25 %/-15 %)
  corrugated_roof 9 x 6 ~159 k · 7 x 6 ~120 k (row=0,18; subir row para LOD) · board_roof_stepped 8 x 6,5 ~51 k
"""
import math

import bpy  # noqa: F401  (bmesh/mathutils solo existen después de importar bpy)
import bmesh  # noqa: F401
from mathutils import Matrix, Vector

from kit.common import MB, rng

PI = math.pi
LAMINA_MATS = ("roof_metal", "roof_metal_light")

# --- medidas de la pila constructiva ---
PLATE_W, PLATE_H = 0.14, 0.10          # solera
RAFTER_W, RAFTER_D = 0.05, 0.15        # cabio (ancho x canto perpendicular al faldón)
RIDGE_T = 0.04                          # tabla de cumbrera
BAT_W, BAT_T = 0.05, 0.025             # rastrel de teja
PUR_W, PUR_T = 0.075, 0.05             # correa de lámina / tablón
TILE_N = BAT_T + 0.002                  # base de la teja sobre el plano de cabios
SHEET_N = PUR_T + 0.002                 # base de la lámina ondulada
BOARD_N = 0.001                         # los tablones apoyan directo sobre los cabios
BOARD_W, BOARD_T, BOARD_EXP = 0.22, 0.022, 0.16
# --- teja curva (canal y cobija son la MISMA pieza, troncocónica) ---
TILE_L = 0.45                           # largo
TILE_E = 0.30                           # paso de hilada (solape 1/3)
TILE_RN, TILE_RW = 0.074, 0.100         # radio interior en boca estrecha / ancha
TILE_T = 0.012                          # espesor
TILE_TH = math.radians(70.0)            # semiángulo del arco
TILE_S = 0.225                          # separación entre ejes de canales
TILE_V0 = -0.05                         # la 1.ª hilada vuela 5 cm sobre el alero
# elevación del borde bajo de cada tablón (apoya sobre el inferior, a la fracción f de su ancho): n_b = BOARD_N + (T + 2 mm) / f
_f = BOARD_EXP / BOARD_W
BOARD_LB = BOARD_N + (BOARD_T + 0.002) / _f


# =====================================================================================================================
# utilidades
# =====================================================================================================================
def _T(x=0.0, y=0.0, z=0.0):
    return Matrix.Translation((x, y, z))


def _R(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, axis)


def _about(p, M):
    return _T(p[0], p[1], p[2]) @ M @ _T(-p[0], -p[1], -p[2])


def _vec(p):
    return p if isinstance(p, Vector) else Vector((float(p[0]), float(p[1]), float(p[2])))


def _merge(dst, src, m=None):
    dst.join(src, m)
    src.bm.free()
    return dst


def _ss(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


class _N1:
    """Ruido 1D suave determinista (suma de senos), rango ~[-1, 1]."""

    def __init__(self, r, wl=1.0, n=3):
        self.w = [(2 * PI / (wl * (0.55 ** -k if k else 1.0)) * (1.0 + 0.3 * r.uniform(-1, 1)), r.uniform(0, 2 * PI), 0.6 ** k)
                  for k in range(n)]
        self.s = sum(a for _, _, a in self.w)

    def __call__(self, t):
        return sum(a * math.sin(f * t + ph) for f, ph, a in self.w) / self.s


def _ring(B, S, U, y0, y1, w, c):
    """Sección rectangular achaflanada (8 vértices): x en ±w/2 sobre S, y de y0 a y1 sobre U."""
    hw = w / 2
    c = min(c, 0.3 * w, 0.3 * abs(y1 - y0))
    if c <= 1e-5:
        pts = [(-hw, y0), (hw, y0), (hw, y1), (-hw, y1)]
    else:
        pts = [(-hw, y0 + c), (-hw + c, y0), (hw - c, y0), (hw, y0 + c), (hw, y1 - c), (hw - c, y1), (-hw + c, y1), (-hw, y1 - c)]
    return [B + S * x + U * y for x, y in pts]


def _loft(mb, rings, mat, caps=True, closed=True):
    vs = [[mb.bm.verts.new(p) for p in r] for r in rings]
    k = len(rings[0])
    for i in range(len(vs) - 1):
        a, b = vs[i], vs[i + 1]
        for j in range(k if closed else k - 1):
            jj = (j + 1) % k
            mb.face([a[j], a[jj], b[jj], b[j]], mat)
    if caps:
        mb.face(list(reversed(vs[0])), mat)
        mb.face(vs[-1], mat)
    return vs


def _plane_hit(p, d, q, n):
    """Proyecta p a lo largo de d sobre el plano (q, n)."""
    den = d.dot(n)
    if abs(den) < 1e-9:
        return p
    return p + d * ((q - p).dot(n) / den)


def _beam(mb, pts, up, w, y0, y1, mat, c=0.004, cut0=None, cut1=None, jag0=0.0, jag1=0.0, r=None):
    """Pieza de madera achaflanada a lo largo de una polilínea de puntos base.
    up: Vector (o lista por estación) = dirección del canto; y0/y1 escalares o listas (canto variable: pájaro, corte de cola).
    Con up = Z las secciones son verticales (cortes a plomo). cut0/cut1 = (punto, normal): proyecta la sección extrema sobre
    ese plano (corte de mejilla, inglete). jag0/jag1: astillado aleatorio de los extremos (rotura)."""
    pts = [_vec(p) for p in pts]
    n = len(pts)
    rings = []
    for i in range(n):
        T = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        U = up[i] if isinstance(up, (list, tuple)) else up
        S = U.cross(T).normalized()
        a = y0[i] if isinstance(y0, (list, tuple)) else y0
        b = y1[i] if isinstance(y1, (list, tuple)) else y1
        rg = _ring(pts[i], S, U, a, b, w, c)
        if i == 0 and cut0 is not None:
            rg = [_plane_hit(p, T, _vec(cut0[0]), _vec(cut0[1])) for p in rg]
        if i == n - 1 and cut1 is not None:
            rg = [_plane_hit(p, T, _vec(cut1[0]), _vec(cut1[1])) for p in rg]
        if r is not None and ((i == 0 and jag0) or (i == n - 1 and jag1)):
            j = jag0 if i == 0 else jag1
            sgn = -1 if i == 0 else 1
            # astillas: los vértices del extremo avanzan/retroceden distinto; la cara de corte queda irregular
            rg = [p + T * (sgn * j * r.uniform(-1.0, 1.0)) + S * r.uniform(-0.15, 0.15) * j * 0.3 for p in rg]
        rings.append(rg)
    return _loft(mb, rings, mat)


def _box(mb, mn, mx, mat, bevel=0.004, seg=1, m=None):
    mb.box(mn, mx, mat, bevel=bevel, seg=seg, m=m)


def _nail(mb, p, axis, r=0.0055, h=0.004, mat="metal_rust", seg=6):
    """Cabeza de clavo / tornillo: disco corto que sobresale de la superficie p a lo largo de axis (sin tocarla)."""
    p, a = _vec(p), _vec(axis).normalized()
    mb.cyl(p + a * 0.0008, p + a * (0.0008 + h), r, seg=seg, mat=mat, r1=r * 0.8)


# =====================================================================================================================
# geometría común del techo (planos, vertientes, marcos locales)
# =====================================================================================================================
class _Roof:
    """Planos de cubierta en coordenadas de construcción (cumbrera en X). `top(x, y, n)` = cota del plano de cabios + n."""

    def __init__(self, kind, w, d, pitch_deg, overhang, rake=None):
        if kind not in ("hip", "gable"):
            raise ValueError("kind debe ser 'hip' o 'gable'")
        self.kind = kind
        self.swap = kind == "hip" and w < d
        if self.swap:
            w, d = d, w
        self.w, self.d = float(w), float(d)
        self.hw, self.hd = self.w / 2, self.d / 2
        self.p = math.radians(pitch_deg)
        self.tp, self.cp, self.sp = math.tan(self.p), math.cos(self.p), math.sin(self.p)
        self.ov = float(overhang)
        self.ovr = (min(self.ov, 0.45) if rake is None else float(rake)) if kind == "gable" else self.ov
        self.Dv = RAFTER_D / self.cp
        self.zb0 = PLATE_H + 0.001 - PLATE_W * self.tp      # canto inferior del cabio en la cara exterior del muro
        self.zt0 = self.zb0 + self.Dv                       # plano superior de cabios en la cara exterior del muro
        self.run = self.hd + self.ov                        # proyección horizontal alero -> cumbrera
        self.vlen = self.run / self.cp                      # largo del faldón (alero -> cumbrera)
        self.ridge_half = (self.hw - self.hd) if kind == "hip" else (self.hw + self.ovr)
        self.z_ridge = self.zt0 + self.hd * self.tp
        self.slopes = ["front", "back"] + (["right", "left"] if kind == "hip" else [])

    # ---- cotas ----
    def plane(self, s, x, y):
        if s == "front":
            return self.zt0 + (self.hd + y) * self.tp
        if s == "back":
            return self.zt0 + (self.hd - y) * self.tp
        if s == "right":
            return self.zt0 + (self.hw - x) * self.tp
        return self.zt0 + (self.hw + x) * self.tp

    def top(self, x, y, n=0.0):
        return min(self.plane(s, x, y) for s in self.slopes) + n / self.cp

    def owner(self, x, y):
        return min(self.slopes, key=lambda s: self.plane(s, x, y))

    # ---- marco local de cada vertiente: (O, U, V, N); u a lo largo del alero, v subiendo, n normal hacia afuera ----
    def frame(self, s):
        cp, sp, ov = self.cp, self.sp, self.ov
        z_e = self.zt0 - ov * self.tp
        if s == "front":
            return Vector((0, -(self.hd + ov), z_e)), Vector((1, 0, 0)), Vector((0, cp, sp)), Vector((0, -sp, cp))
        if s == "back":
            return Vector((0, self.hd + ov, z_e)), Vector((-1, 0, 0)), Vector((0, -cp, sp)), Vector((0, sp, cp))
        if s == "right":
            return Vector((self.hw + ov, 0, z_e)), Vector((0, 1, 0)), Vector((-cp, 0, sp)), Vector((sp, 0, cp))
        return Vector((-(self.hw + ov), 0, z_e)), Vector((0, -1, 0)), Vector((cp, 0, sp)), Vector((-sp, 0, cp))

    def matrix(self, s):
        O, U, V, N = self.frame(s)
        m = Matrix.Identity(4)
        for i in range(3):
            m[i][0], m[i][1], m[i][2], m[i][3] = U[i], V[i], N[i], O[i]
        return m

    def to_world(self, s, u, v, n=0.0):
        O, U, V, N = self.frame(s)
        return O + U * u + V * v + N * n

    def u_limits(self, s, v):
        """Límites en u de la vertiente a la altura v (trapecio / triángulo de limatesas o rectángulo con remates)."""
        if self.kind == "gable":
            e = self.hw + self.ovr
            return -e, e
        h = (self.hw if s in ("front", "back") else self.hd) + self.ov - v * self.cp
        return -h, h

    def to_plan(self, s, u, v):
        p = self.to_world(s, u, v)
        return p.x, p.y

    def finalize(self, mb):
        if self.swap:
            mb.transform(_R("Z", 90.0))
        return mb


def roof_top(kind, w, d, pitch_deg, overhang=0.6, x=0.0, y=0.0, n=0.0):
    """Cota z del plano superior de cabios (+ n perpendicular) en el punto de planta (x, y) — para que el constructor
    cierre hastiales, encaje chimeneas o coloque canalones. (Coordenadas finales, ya giradas si hip con w < d.)"""
    R = _Roof(kind, w, d, pitch_deg, overhang)
    if R.swap:
        x, y = y, -x
    return R.top(x, y, n)


def ridge_height(kind, w, d, pitch_deg, overhang=0.6):
    """Cota de la cumbrera sobre el plano de cabios (sin teja)."""
    return _Roof(kind, w, d, pitch_deg, overhang).z_ridge


def damage_spot(kind, w, d, pitch_deg, overhang=0.6, seed=0, damage=0.6):
    """Hueco de daño reproducible (x, y, r) en planta: lo usan roof_frame(damage=...) y se pasa como hole=... a barrel_tiles
    o torn=... a corrugated_roof para que el agujero de la cubierta coincida con los cabios rotos."""
    R = _Roof(kind, w, d, pitch_deg, overhang)
    r = rng(seed * 7919 + 101)
    rad = 0.55 + 1.25 * max(0.0, min(1.0, damage))
    ext = (R.hw - R.hd) if kind == "hip" else R.hw
    x = r.uniform(-0.55, 0.55) * max(ext - rad * 0.5, 0.2)
    y = -R.hd * r.uniform(0.38, 0.62)
    if R.swap:
        x, y = -y, x
    return (float(x), float(y), float(rad))


def _plan_local(R, x, y):
    """Coordenadas finales -> coordenadas de construcción (deshace el giro de hip con w < d)."""
    return (y, -x) if R.swap else (x, y)


# =====================================================================================================================
# trazado compartido de hiladas / correas (roof_frame y las cubiertas deben coincidir)
# =====================================================================================================================
def _tile_courses(vlen):
    """v del borde inferior de cada hilada de teja (la última se ajusta para llegar a 3 cm de la cumbrera)."""
    vs, v = [], TILE_V0
    while v + TILE_L <= vlen - 0.03 + 1e-9:
        vs.append(v)
        v += TILE_E
    top = vlen - 0.03 - TILE_L
    if not vs or top - vs[-1] > 0.06:
        vs.append(max(top, TILE_V0))
    return vs


def _batten_vs(vlen):
    return [v + TILE_L - 0.035 for v in _tile_courses(vlen)]


def _purlin_vs(vlen, step=0.85):
    """Correas de lámina/tablón: una en el alero, intermedias <= step, una a 10 cm de la cumbrera."""
    a, b = 0.10, vlen - 0.10
    n = max(1, int(math.ceil((b - a) / step)))
    return [a + (b - a) * i / n for i in range(n + 1)]


# =====================================================================================================================
# cabios
# =====================================================================================================================
def _rafter_fns(R, h_e, a0, a1, tails, r, deep=0.0):
    """Funciones (zb, zt, estaciones) de un cabio que corre desde a0 (interior) hasta a1 (punta de la cola).
    h_e = semiancho de la planta en esa dirección (cara exterior del muro en a = h_e)."""
    tp, Dv = R.tp, R.Dv + deep
    seat0, seat1 = h_e - PLATE_W, h_e
    sag = r.uniform(0.0, 0.014) * min(1.0, max(0.0, (seat0 - a0)) / 3.0)
    droop = r.uniform(0.0, 0.012)
    span = max(seat0 - a0, 1e-3)
    tail0 = a1 - 0.13
    deco = tails and (a1 - seat1) > 0.2

    def dz(a):
        if a < seat0:
            return -sag * math.sin(PI * max(0.0, a - a0) / span)
        if a > seat1:
            return -droop * ((a - seat1) / max(a1 - seat1, 1e-3)) ** 2
        return 0.0

    def zt(a):
        return R.zt0 + (h_e - a) * tp + dz(a)

    def zb(a):
        z = R.zt0 + (h_e - a) * tp - Dv + dz(a)
        if seat0 - 1e-6 <= a <= seat1 + 1e-6:
            z = max(z, PLATE_H + 0.001)
        if deco and a > tail0:
            t = (a - tail0) / (a1 - tail0)
            z += (R.Dv * 0.52) * t ** 1.7
        return z

    st = set()
    lo = min(seat0, a1)
    if lo > a0:
        n = max(1, int(math.ceil((lo - a0) / 0.45)))
        st.update(a0 + (lo - a0) * i / n for i in range(n + 1))
    st.add(a0)
    for a in (seat0, seat1, seat1 + 0.012):
        if a0 < a < a1:
            st.add(a)
    if a1 > seat1 + 0.012:
        b = tail0 if deco else a1
        n = max(1, int(math.ceil((b - (seat1 + 0.012)) / 0.3)))
        st.update(seat1 + 0.012 + (b - seat1 - 0.012) * i / n for i in range(n + 1))
        if deco:
            st.update(tail0 + (a1 - tail0) * t for t in (0.25, 0.5, 0.75, 1.0))
    st.add(a1)
    return zb, zt, _dedupe(sorted(a for a in st if a0 - 1e-9 <= a <= a1 + 1e-9))


def _dedupe(A, tol=1e-3):
    out = []
    for a in A:
        if not out or a - out[-1] > tol:
            out.append(a)
        elif a == A[-1]:
            out[-1] = a
    return out


def _rafter(mb, R, axis, coord, sgn, a0, a1, r, tails, cut0=None, pieces=None, deep=0.0, w=RAFTER_W, mat="wood",
            straight=False):
    """Cabio a plomo. axis 'y': corre en Y en x = coord, lado sgn; axis 'x': corre en X en y = coord (faldones de testero).
    pieces: [(a_lo, a_hi, jag_lo, jag_hi, M)] para cabios rotos/faltantes (M = matriz aplicada a la pieza o None).
    El arqueo lateral se anula en el apoyo y en la cola (frisos y solera a 1,5 mm); straight=True lo anula entero (cabios con
    tirante y nudillo clavados al costado)."""
    h_e = R.hd if axis == "y" else R.hw
    zb, zt, st = _rafter_fns(R, h_e, a0, a1, tails, r, deep)
    bow = _N1(r, wl=3.0)
    bamp = r.uniform(0.002, 0.007) * (0.0 if straight else 1.0)
    seat0 = h_e - PLATE_W

    def P(a):
        o = coord + bamp * bow(a) * math.sin(PI * min(max((a - a0) / max(seat0 - a0, 1e-3), 0.0), 1.0))
        return Vector((o, sgn * a, 0.0)) if axis == "y" else Vector((sgn * a, o, 0.0))

    if pieces is None:
        pieces = [(a0, a1, 0.0, 0.0, None)]
    for (lo, hi, j0, j1, M) in pieces:
        A = _dedupe(sorted({lo, hi} | {a for a in st if lo + 1e-3 < a < hi - 1e-3}))
        if cut0 is not None and lo == a0:
            A = [A[0]] + [a for a in A[1:] if a >= a0 + 0.045]
        if len(A) < 2 or hi - lo < 0.04:
            continue
        tmp = MB()
        _beam(tmp, [P(a) for a in A], Vector((0, 0, 1)), w, [zb(a) for a in A], [zt(a) for a in A], mat, c=0.005,
              cut0=cut0 if lo == a0 else None, jag0=j0, jag1=j1, r=r)
        _merge(mb, tmp, M)


def _tail_end(a_tail, j, tails):
    """Punta del cabio: con colas, a_tail + j; sin colas (fascia en a_tail + 1 mm) queda 2–6 mm por dentro de la fascia."""
    return a_tail + j if tails else a_tail - 0.002 - 0.3 * abs(j)


def _blocking(mb, occ, lo, hi, at, z0, z1, gap=0.0015, t=0.04):
    """Frisos (tablas de espesor t) entre los miembros occ = [(centro, semiancho)] a lo largo de la solera, de lo a hi.
    at(u) -> punto base (centro del espesor) en la cota 0; z0..z1 = cotas de la tabla."""
    cuts = sorted((c - hw_ - gap, c + hw_ + gap) for c, hw_ in occ)
    cur = lo
    spans = []
    for a, b in cuts:
        if a > cur:
            spans.append((cur, a))
        cur = max(cur, b)
    if hi > cur:
        spans.append((cur, hi))
    for a, b in spans:
        if b - a < 0.08 or z1 - z0 < 0.04:
            continue
        _beam(mb, [Vector(at(a)), Vector(at(b))], Vector((0, 0, 1)), t, z0, z1, "wood_dark", c=0.004)


def _hip_side_plane(R, sx, sy, jack_pt, off=0.026):
    """Plano lateral de la limatesa (cuadrante sx, sy) del lado donde está jack_pt: para el corte de mejilla de los cabios cortos."""
    q0 = Vector((sx * (R.hw - R.hd), 0.0, 0.0))
    d = Vector((sx, sy, 0.0)).normalized()
    nh = Vector((sy, -sx, 0.0)).normalized()
    if (Vector((jack_pt[0], jack_pt[1], 0.0)) - q0).dot(nh) < 0:
        nh = -nh
    return (q0 + nh * off, nh), d


# =====================================================================================================================
# 1) ESTRUCTURA DE MADERA
# =====================================================================================================================
def roof_frame(kind, w, d, pitch_deg, overhang=0.6, seed=0, spacing=0.6, tails=True, damage=0.0, cover="tile", spot=None,
               rake=None, ties=True, blocking=True):
    """Estructura de cubierta de madera (ver cabecera del módulo para medidas y cotas).
    cover: 'tile' (rastreles para teja curva a paso de hilada), 'sheet' (correas para lámina ondulada) o 'boards'
    (sin rastreles: los tablones de board_roof_stepped se clavan directo a los cabios).
    damage 0..1: abre un hueco en una vertiente (spot = (x, y, r) en planta; por defecto damage_spot(...)): rastreles
    cortados y colgando, cabios partidos (la pieza superior cuelga de la cumbrera) o faltantes, y escombro de madera en z = 0.
    blocking: frisos (tablas de 0,04 entre cabios sobre la solera, en la cara exterior de los muros de alero) que cierran el
    desván por el alero: desde abajo solo se ve el vuelo, nunca el intradós de las tejas interiores (lo aprovechan los niveles
    'mid'/'low' de barrel_tiles)."""
    R = _Roof(kind, w, d, pitch_deg, overhang, rake)
    r = rng(seed)
    mb = MB()
    Z = Vector((0, 0, 1))
    hw, hd, ov, tp = R.hw, R.hd, R.ov, R.tp
    xr = R.ridge_half
    if damage > 0 and spot is None:
        spot = damage_spot(kind, w, d, pitch_deg, overhang, seed, damage)
    sp = None
    if damage > 0 and spot is not None:
        sx_, sy_ = _plan_local(R, spot[0], spot[1])
        sp = (sx_, sy_, float(spot[2]))

    # ---------------- soleras ----------------
    for sg in (-1, 1):
        yc = sg * (hd - PLATE_W / 2)
        xs = [-hw + 0.004, -hw / 3, hw / 3, hw - 0.004]
        _beam(mb, [(x, yc + r.uniform(-0.003, 0.003), 0.0) for x in xs], Z, PLATE_W, 0.0, PLATE_H, "wood_dark", c=0.006)
        if kind == "hip":
            xc = sg * (hw - PLATE_W / 2)
            ys = [-hd + PLATE_W + 0.002, 0.0, hd - PLATE_W - 0.002]
            _beam(mb, [(xc + r.uniform(-0.003, 0.003), y, 0.0) for y in ys], Z, PLATE_W, 0.0, PLATE_H, "wood_dark", c=0.006)

    # ---------------- cumbrera ----------------
    zr_top = R.zt0 + (hd - RIDGE_T / 2) * tp - 0.002
    rb_end = xr - (0.02 if kind == "hip" else 0.0)
    nrs = max(2, int(math.ceil(2 * rb_end / 0.8)) + 1)
    rpts = [(-rb_end + 2 * rb_end * i / (nrs - 1), 0.25 * r.uniform(-0.002, 0.002), 0.0) for i in range(nrs)]
    rsag = [-r.uniform(0.0, 0.01) * math.sin(PI * i / (nrs - 1)) for i in range(nrs)]
    ridge_bot = zr_top - (R.Dv + 0.07)
    _beam(mb, rpts, Z, RIDGE_T, [ridge_bot + s for s in rsag], [zr_top + s for s in rsag], "wood", c=0.005)

    # ---------------- cabios de los faldones largos ----------------
    a_ridge = RIDGE_T / 2 + 0.0017            # 1,2 mm libres contra la tabla de cumbrera (que oscila ±0,5 mm)
    a_tail = hd + ov
    raf_x = []
    if kind == "gable":
        n = max(2, int(round((w - RAFTER_W) / spacing)) + 1)
        raf_x = [(-hw + RAFTER_W / 2) + (w - RAFTER_W) * i / (n - 1) for i in range(n)]
        if R.ovr > 0.12:
            raf_x = [-(hw + R.ovr - RAFTER_W / 2)] + raf_x + [hw + R.ovr - RAFTER_W / 2]
    else:
        k = int((hw + ov - 0.08) / spacing)
        raf_x = [i * spacing for i in range(-k, k + 1)]
    raf_x = [x + r.uniform(-0.008, 0.008) if abs(abs(x) - hw) > 0.05 else x for x in raf_x]
    commons = [x for x in raf_x if abs(x) < xr - 0.05 and abs(abs(x) - hw) > 0.06 and abs(x) < hw]
    tie_x = {x: (1 if (i // 2) % 2 == 0 else -1) for i, x in enumerate(commons) if i % 2 == 0} if ties else {}

    def damaged_pieces(axis_c, sgn, a0, a1, M_axis):
        """Piezas de un cabio en Y afectado por el hueco (None = intacto)."""
        if sp is None or (sp[1] < 0) != (sgn < 0):
            return None
        dx = abs(axis_c - sp[0])
        if dx >= sp[2]:
            return None
        hc = math.sqrt(sp[2] ** 2 - dx ** 2)
        ac = abs(sp[1])
        lo, hi = max(ac - hc, a0 + 0.3), min(ac + hc, hd - PLATE_W - 0.15)
        if hi - lo < 0.25:
            return None
        if dx < 0.5 * sp[2] and r.uniform() < 0.55:
            # faltante: solo quedan el muñón de cumbrera y la cola
            return [(a0, lo + r.uniform(0, 0.1), 0.0, 0.05, None), (hi - r.uniform(0, 0.1), a1, 0.06, 0.0, None)]
        ab = r.uniform(lo + 0.1 * (hi - lo), hi - 0.1 * (hi - lo))
        drop = 0.12 + 0.45 * damage * r.uniform(0.6, 1.0)
        ang = math.degrees(math.atan2(drop, max(ab - a0, 0.3)))
        piv = Vector((axis_c, sgn * a0, R.zt0 + (hd - a0) * tp - R.Dv * 0.5))
        Mup = _about(piv, _R(M_axis, -sgn * ang))
        return [(a0, ab, 0.0, 0.07, Mup), (ab + 0.012, a1, 0.05, 0.0, None)]

    for x in raf_x:
        for sgn in (-1, 1):
            if kind == "hip" and abs(x) > xr - 0.03:
                # cabio corto (jack) hasta la limatesa
                sx = 1 if x > 0 else -1
                yh = abs(x) - (hw - hd) + 0.037
                if a_tail - yh < 0.25:
                    continue
                plane, _ = _hip_side_plane(R, sx, sgn, (x, sgn * a_tail))
                _rafter(mb, R, "y", x, sgn, yh, _tail_end(a_tail, r.uniform(-0.012, 0.012), tails), r, tails, cut0=plane,
                        pieces=damaged_pieces(x, sgn, yh, a_tail, "X"))
            else:
                at = _tail_end(a_tail, r.uniform(-0.015, 0.012), tails)
                pcs = damaged_pieces(x, sgn, a_ridge, at, "X")
                if pcs is None and tails and r.uniform() < 0.08:
                    # cola podrida/partida
                    pcs = [(a_ridge, at - r.uniform(0.08, 0.25), 0.0, 0.04, None)]
                _rafter(mb, R, "y", x, sgn, a_ridge, at, r, tails, pieces=pcs, straight=x in tie_x)

    # ---------------- limatesas y cabios de testero ----------------
    if kind == "hip":
        for sx in (-1, 1):
            for sy in (-1, 1):
                t0, t1 = 0.012, hd + ov + (0.035 if tails else -0.03)
                n = max(3, int(math.ceil((t1 - t0) / 0.45)) + 1)
                ts = [t0 + (t1 - t0) * i / (n - 1) for i in range(n)]
                # pájaro de la limatesa sobre la esquina de soleras
                for tt in (hd - PLATE_W, hd):
                    ts.append(tt)
                ts = sorted(set(ts))
                drop = 0.025 * tp / math.sqrt(2) + 0.002
                pts, zb_, zt_ = [], [], []
                sag = r.uniform(0, 0.008)
                for t in ts:
                    pts.append(Vector((sx * (xr + t), sy * t, 0.0)))
                    z = R.zt0 + (hd - t) * tp - drop - sag * math.sin(PI * min(t / hd, 1.0))
                    zt_.append(z)
                    zbb = z - (R.Dv + 0.05)
                    if hd - PLATE_W - 1e-6 <= t <= hd + 1e-6:
                        zbb = max(zbb, PLATE_H + 0.001)
                    if t > hd + ov - 0.1:
                        zbb += (t - (hd + ov - 0.1)) / 0.135 * R.Dv * 0.45
                    zb_.append(zbb)
                _beam(mb, pts, Z, 0.05, zb_, zt_, "wood", c=0.005, cut0=((0.0, sy * 0.001, 0.0), (0.0, sy, 0.0)))
            # cabios de testero (corren en X) a ambos lados del eje, cortados contra las limatesas
            k = int((hd + ov - 0.1) / spacing)
            for j in range(-k, k):
                yj = (j + 0.5) * spacing + r.uniform(-0.008, 0.008)
                sy = 1 if yj > 0 else -1
                xh = abs(yj) + (hw - hd) + 0.037
                a_t = _tail_end(hw + ov, r.uniform(-0.012, 0.012), tails)
                if a_t - xh < 0.25:
                    continue
                plane, _ = _hip_side_plane(R, sx, sy, (sx * a_t, yj))
                _rafter(mb, R, "x", yj, sx, xh, a_t, r, tails, cut0=plane)

    # ---------------- rastreles / correas ----------------
    cov_top = {"tile": BAT_T + 0.012, "sheet": PUR_T - 0.002, "boards": -0.003}[cover]
    for s in R.slopes:
        O, U, V, N = R.frame(s)
        vlist = _batten_vs(R.vlen) if cover == "tile" else (_purlin_vs(R.vlen) if cover == "sheet" else [])
        bw, bt = (BAT_W, BAT_T) if cover == "tile" else (PUR_W, PUR_T)
        mat = "wood" if cover == "tile" else "wood_grey"
        for vb in vlist:
            u0, u1 = R.u_limits(s, vb + bw / 2)
            u0, u1 = u0 + (0.03 if kind == "hip" else 0.0), u1 - (0.03 if kind == "hip" else 0.0)
            if u1 - u0 < 0.15:
                continue
            spans = [(u0, u1)]
            hole_u = None
            if sp is not None:
                px, py = R.to_plan(s, 0.0, vb)
                if s in ("front", "back") and abs(py - sp[1]) < sp[2] * 1.05:
                    hc = math.sqrt(max(sp[2] ** 2 - (py - sp[1]) ** 2, 0.0)) * r.uniform(0.45, 0.72)
                    cu = sp[0] if s == "front" else -sp[0]
                    if hc > 0.05:
                        hole_u = (cu - hc, cu + hc)
            # tramos de 3–4,8 m con juntas a tope
            cuts = [u0]
            while cuts[-1] + 4.8 < u1:
                cuts.append(cuts[-1] + r.uniform(3.0, 4.8))
            cuts.append(u1)
            for a, b in zip(cuts[:-1], cuts[1:]):
                segs = [(a, b, 0.0, 0.0)]
                if hole_u is not None and hole_u[0] < b and hole_u[1] > a:
                    segs = []
                    if hole_u[0] - a > 0.12:
                        segs.append((a, hole_u[0], 0.0, 1.0))
                    if b - hole_u[1] > 0.12:
                        segs.append((hole_u[1], b, -1.0, 0.0))
                for (sa, sb, brk0, brk1) in segs:
                    sa2, sb2 = sa + (0.0015 if sa > u0 else 0.0), sb - (0.0015 if sb < u1 else 0.0)
                    nseg = max(2, int(math.ceil((sb2 - sa2) / 0.6)) + 1)
                    us = [sa2 + (sb2 - sa2) * i / (nseg - 1) for i in range(nseg)]
                    droop = r.uniform(0.02, 0.09) * damage if (brk0 or brk1) and r.uniform() < 0.6 else 0.0
                    pts = []
                    for i, u in enumerate(us):
                        dn = r.uniform(0.0, 0.0015)
                        if droop:
                            t = (u - sa2) / (sb2 - sa2) if brk1 else (sb2 - u) / (sb2 - sa2)
                            dn -= droop * max(0.0, (t - 0.55) / 0.45) ** 2 * 1.0
                        pts.append(O + U * u + V * (vb + r.uniform(-0.003, 0.003)) + N * (0.001 + dn))
                    _beam(mb, pts, N, bw, 0.0, bt, mat, c=0.003, jag0=0.03 if brk0 else 0.0, jag1=0.03 if brk1 else 0.0, r=r)
        # tabla de alero / calza de arranque (sobre las colas)
        u0, u1 = R.u_limits(s, 0.07)
        if kind == "hip":
            u0, u1 = u0 + 0.09, u1 - 0.09
        if cover == "tile":
            tb = BAT_T + 0.010
            pts = [O + U * (u0 + (u1 - u0) * i / 6) + V * 0.07 + N * 0.001 for i in range(7)]
            _beam(mb, pts, N, 0.14, 0.0, tb, "wood_grey", c=0.004)

    # ---------------- fascia (sin colas) y tapajuntas de remate ----------------
    if not tails:
        ze = R.zt0 - ov * tp
        for sg in (-1, 1):
            y0 = sg * (hd + ov + 0.0135)
            xe = (hw + ov + 0.026) if kind == "hip" else (hw + R.ovr + 0.026)
            _beam(mb, [(-xe, y0, 0), (0, y0 + sg * abs(r.uniform(-0.003, 0.003)), 0), (xe, y0, 0)], Z, 0.025,
                  ze - 0.20, ze + cov_top / R.cp, "wood_grey", c=0.004)
            if kind == "hip":
                x0 = sg * (hw + ov + 0.0135)
                ye = hd + ov - 0.001
                _beam(mb, [(x0, -ye, 0), (x0 + sg * abs(r.uniform(-0.003, 0.003)), 0, 0), (x0, ye, 0)], Z, 0.025,
                      ze - 0.20, ze + cov_top / R.cp, "wood_grey", c=0.004)
    if kind == "gable":
        for sx in (-1, 1):
            xb = sx * (hw + R.ovr + 0.0145)
            for sy in (-1, 1):
                ys = [sy * a for a in (0.0, R.run * 0.33, R.run * 0.66, R.run + 0.02)]
                btop = {"tile": BAT_T + 0.018, "sheet": PUR_T - 0.002, "boards": -0.003}[cover]
                zt_ = [R.zt0 + (hd - abs(y)) * tp + btop / R.cp for y in ys]
                zb_ = [z - 0.24 for z in zt_]
                _beam(mb, [(xb + sx * abs(r.uniform(-0.003, 0.003)), y, 0) for y in ys], Z, 0.025, zb_, zt_, "wood_grey", c=0.004,
                      cut0=((0, sy * 0.001, 0), (0, sy, 0)))

    # ---------------- tirantes, nudillos, pendolones y correas de apoyo ----------------
    if ties:
        for i, x in enumerate(commons):
            if i % 2:
                continue
            side = 1 if (i // 2) % 2 == 0 else -1
            xt = x + side * (RAFTER_W / 2 + 0.025 + 0.001)
            yy = hd - 0.004
            z0 = PLATE_H + 0.001
            # tirante sobre las soleras, extremos cortados por el faldón
            _beam(mb, [(xt, -yy - 0.2, 0), (xt, 0, 0), (xt, yy + 0.2, 0)], Z, 0.05, z0, z0 + 0.15, "wood", c=0.004,
                  cut0=((0, -hd, R.zt0 - 0.015), Vector((0, -R.sp, R.cp))), cut1=((0, hd, R.zt0 - 0.015), Vector((0, R.sp, R.cp))))
            # nudillo a 2/3 de la altura
            zc = PLATE_H + (R.z_ridge - PLATE_H) * 0.62
            ac = hd - (zc + 0.12 - R.zt0 + 0.02) / tp
            if ac > 0.4:
                _beam(mb, [(xt, -ac - 0.3, 0), (xt, ac + 0.3, 0)], Z, 0.05, zc, zc + 0.12, "wood", c=0.004,
                      cut0=((0, -hd, R.zt0 - 0.012), Vector((0, -R.sp, R.cp))), cut1=((0, hd, R.zt0 - 0.012), Vector((0, R.sp, R.cp))))
            # pendolón bajo la cumbrera en luces grandes
            if d > 5.0 and i % 4 == 0:
                xp = x - side * 0.08
                _box(mb, (xp - 0.05, -0.05, 0.001), (xp + 0.05, 0.05, ridge_bot - 0.012), "wood", bevel=0.006)

    # ---------------- frisos entre cabios en los muros de alero ----------------
    if blocking:
        zt_w = R.zt0 + 0.005 * tp - 0.002
        tie_occ = [(x + sd * (RAFTER_W / 2 + 0.026), 0.025) for x, sd in tie_x.items()]
        for sg in (-1, 1):
            occ = [(x, RAFTER_W / 2) for x in raf_x if abs(x) <= hw] + tie_occ
            lim = (hw - PLATE_W - 0.05) if kind == "hip" else hw - 0.002
            _blocking(mb, occ, -lim, lim, lambda u, sg=sg: (u, sg * (hd - 0.025), 0.0), PLATE_H + 0.001, zt_w)
            if kind == "hip":
                k = int((hd + ov - 0.1) / spacing)
                occ = [((j + 0.5) * spacing, RAFTER_W / 2 + 0.008) for j in range(-k, k)]
                lim = hd - PLATE_W - 0.05
                _blocking(mb, occ, -lim, lim, lambda u, sg=sg: (sg * (hw - 0.025), u, 0.0), PLATE_H + 0.001, zt_w)

    # ---------------- escombro de madera bajo el hueco ----------------
    if sp is not None:
        for idb in range(int(2 + 4 * damage)):
            L = r.uniform(0.3, 1.4)
            a = r.uniform(0, 2 * PI)
            cx = min(max(sp[0] + r.uniform(-0.6, 0.6) * sp[2], -hw + 0.5), hw - 0.5)
            cy = min(max(sp[1] + r.uniform(-0.6, 0.6) * sp[2], -hd + 0.5), hd - 0.5)
            zb0 = 0.001 + 0.0013 * idb                     # cada trozo a otra cota y algo inclinado: nunca coplanares
            p0 = Vector((cx - math.cos(a) * L / 2, cy - math.sin(a) * L / 2, zb0))
            p1 = Vector((cx + math.cos(a) * L / 2, cy + math.sin(a) * L / 2, zb0 + 0.006 + 0.004 * (idb % 3)))
            big = r.uniform() < 0.35
            wd, ht = (RAFTER_W, RAFTER_D) if big else (BAT_W, BAT_T)
            if big:
                p1.z += r.uniform(0.0, 0.25)
            _beam(mb, [p0, p1], Z, wd if not big else ht, 0.0, ht if not big else wd, "wood", c=0.003,
                  jag0=0.04, jag1=0.04, r=r)
    return R.finalize(mb)


# =====================================================================================================================
# 2) TEJA CURVA (canal + cobija)
# =====================================================================================================================
TILE_GAP = 0.003
LB = 1.5 * (TILE_T + TILE_GAP)          # el borde bajo del canal apoya DENTRO del canal inferior (anidado sin intersección)
CAP_L, CAP_RN, CAP_RW, CAP_T, CAP_TH, CAP_STEP = 0.42, 0.105, 0.135, 0.014, math.radians(66.0), 0.32

# Niveles de detalle de barrel_tiles(detail=...). La disposición (qué teja falta, cuál se corre o se rompe, el hueco, los
# caballetes y los cortes del cordón) es IDÉNTICA en los tres niveles con la misma semilla: se puede cambiar de nivel sin saltos.
#   cob / can / cap : segmentos del arco de cobija / canal / caballete (con 5 el diedro es de 28°: sombreado suave con el
#                     ángulo de 30° de MB.finish; con 4 el arco se ve facetado). El canal de 'low' usa 3 tramos desiguales
#                     (faceta central de ±25°, la única parte del canal que dejan ver las cobijas).
#   open            : forma de las piezas NO expuestas (las expuestas siempre son sólidos cerrados, ver barrel_tiles).
#   boq / bead / tube: puntos del arco de las boquillas del alero, (puntos del perfil, paso de estaciones x 0,14 m) del cordón de
#                     mortero de los caballetes y segmentos del remate de limatesas.
TILE_LOD = {
    "high": dict(cob=6, can=6, cap=7, open=None, cap_mode="closed", boq=9, bead=(6, 1), tube=12, eave_extra=0),
    "mid": dict(cob=5, can=5, cap=6, open="sides", cap_mode="sides", boq=7, bead=(6, 2), tube=10, eave_extra=1),
    "low": dict(cob=5, can=3, cap=5, open="lip", cap_mode="lip", boq=4, bead=(4, 3), tube=8, eave_extra=0),
}
_CAN_LOW = tuple(math.radians(a) for a in (-70.0, -25.0, 25.0, 70.0))
_CAN_HALF = math.radians(25.0)          # semiancho angular de la franja del canal-prisma
_FULL = frozenset(("sides", "hid", "cap"))
_MODES = {"closed": _FULL, "sides": frozenset(("sides",)), "lip": frozenset()}


def _tile_piece(mb, M, seg, r, convex, wide_bottom, x0=0.0, x1=TILE_L, jag0=0.0, jag1=0.0, rn=TILE_RN, rw=TILE_RW,
                t=TILE_T, th=TILE_TH, L=TILE_L, mat="tile", mode="closed", angles=None, lip_c=False):
    """Teja troncocónica en local: X = largo (0..L, x = 0 es la boca de ABAJO), arco en YZ con centro en el eje X.
    x0/x1 recortan (pieza rota); jag0/jag1 astillan esos extremos con `r` (rng propio de la pieza). El cono es recto, así que
    bastan dos anillos (un anillo intermedio no añade forma, solo triángulos).
    mode: 'closed' sólido cerrado · 'sides' cara vista + labio de la boca baja + cantos laterales (sin cara oculta ni testa
    alta) · 'lip' cara vista + labio · 'prism' (solo canal) franja central cerrada de 8 tris (fondo plano de ±25° a la
    profundidad del intradós y quilla en el trasdós: queda DENTRO del volumen del canal real, así que conserva sus holguras)
    · o un conjunto con los grupos que se añaden a cara vista + labio: {'sides', 'hid' (cara oculta), 'cap' (testa alta)}.
    lip_c (solo con 'lip'): labio solo en los tramos centrales (|ángulo| < 45°).
    La cara vista es el trasdós de la cobija (convex) y el intradós del canal. Los modos abiertos se orientan bien con el
    recálculo de normales de MB.finish (el vértice más alejado del centro siempre pertenece a una cara con la normal hacia
    fuera); lo verifica el test con rayos."""
    def ri(x):
        f = x / L
        return rn + (rw - rn) * ((1.0 - f) if wide_bottom else f)

    def jag(pts, j, sg):
        return [p + Vector((sg * r.uniform(0.0, j), 0, 0)) for p in pts] if j else pts

    F = mb.face
    if mode == "prism":
        rings = []
        for x, j, sg in ((x0, jag0, 1.0), (x1, jag1, -1.0)):
            rr = ri(x)
            uc = rr * math.sin(_CAN_HALF)
            pts = jag([Vector((x, -uc, -rr)), Vector((x, uc, -rr)), Vector((x, 0.0, -(rr + t)))], j, sg)
            rings.append([mb.bm.verts.new(M @ p) for p in pts])
        a, b = rings
        F([a[0], a[1], b[1], b[0]], mat)
        F([a[1], a[2], b[2], b[1]], mat)
        F([a[2], a[0], b[0], b[2]], mat)
        F([a[2], a[1], a[0]], mat)
        F([b[0], b[1], b[2]], mat)
        return
    A = list(angles) if angles is not None else [-th + 2 * th * i / seg for i in range(seg + 1)]
    n = len(A) - 1
    s = 1.0 if convex else -1.0

    def arc(x, rad):
        return [Vector((x, rad * math.sin(a), s * rad * math.cos(a))) for a in A]
    o0, i0 = arc(x0, ri(x0) + t), arc(x0, ri(x0))
    o1, i1 = arc(x1, ri(x1) + t), arc(x1, ri(x1))
    if jag0:
        d0 = [r.uniform(0.0, jag0) for _ in range(2 * (n + 1))]
        o0 = [p + Vector((d0[k], 0, 0)) for k, p in enumerate(o0)]
        i0 = [p + Vector((d0[n + 1 + k], 0, 0)) for k, p in enumerate(i0)]
    if jag1:
        d1 = [r.uniform(0.0, jag1) for _ in range(2 * (n + 1))]
        o1 = [p - Vector((d1[k], 0, 0)) for k, p in enumerate(o1)]
        i1 = [p - Vector((d1[n + 1 + k], 0, 0)) for k, p in enumerate(i1)]
    V0, H0, V1, H1 = (o0, i0, o1, i1) if convex else (i0, o0, i1, o1)

    def mk(pts):
        return [mb.bm.verts.new(M @ p) for p in pts]
    g = _MODES[mode] if isinstance(mode, str) else mode
    v0, v1 = mk(V0), mk(V1)
    for i in range(n):
        F([v0[i], v0[i + 1], v1[i + 1], v1[i]], mat)          # cara vista
    if not g and lip_c:
        # solo el labio central (|ángulo| < 45°): los costados de la boca se ven de canto y casi no cuentan
        keep = [i for i in range(n) if abs(A[i] + A[i + 1]) / 2 < math.radians(45.0)]
        h0 = {i: mb.bm.verts.new(M @ H0[i]) for i in sorted({q for i in keep for q in (i, i + 1)})}
        for i in keep:
            F([v0[i + 1], v0[i], h0[i], h0[i + 1]], mat)
        return
    h0 = mk(H0)
    for i in range(n):
        F([v0[i + 1], v0[i], h0[i], h0[i + 1]], mat)          # labio (testa de la boca baja)
    if not g:
        return
    if "hid" in g or "cap" in g:
        h1 = mk(H1)
    else:
        h1 = {0: mb.bm.verts.new(M @ H1[0]), n: mb.bm.verts.new(M @ H1[n])}
    for i in range(n):
        if "hid" in g:
            F([h0[i], h0[i + 1], h1[i + 1], h1[i]], mat)      # cara oculta
        if "cap" in g:
            F([v1[i], v1[i + 1], h1[i + 1], h1[i]], mat)      # testa alta
    if "sides" in g:
        for i in (0, n):
            F([v0[i], v1[i], h1[i], h0[i]], mat)              # cantos laterales


def _frame_m(X, Y, Z, O):
    m = Matrix.Identity(4)
    for i in range(3):
        m[i][0], m[i][1], m[i][2], m[i][3] = X[i], Y[i], Z[i], O[i]
    return m


def _tile_m(u, vb, nb, nt, L=TILE_L):
    """Local de teja -> local de vertiente (u, v, n): eje del arco de (u, vb, nb) a (u, vb + L, nt)."""
    X = Vector((0.0, L, nt - nb)).normalized()
    Y = Vector((-1.0, 0.0, 0.0))
    return _frame_m(X, Y, X.cross(Y), Vector((u, vb, nb)))


def _canal_sec(v_rel):
    """Secciones de canal (centro n, ri, ro) que cubren v_rel (relativo a la base de la hilada) — hiladas k-1, k, k+1."""
    out = []
    for off in (-TILE_E, 0.0, TILE_E):
        x = v_rel - off
        if -1e-9 <= x <= TILE_L + 1e-9:
            ri = TILE_RN + (TILE_RW - TILE_RN) * x / TILE_L
            out.append((LB * (1.0 - x / TILE_L) + ri + TILE_T, ri, ri + TILE_T))
    return out


def _cobija_lifts():
    """Altura del eje de la cobija (relativa a TILE_N) en su boca ancha (abajo) y estrecha (arriba), resuelta numéricamente para
    que no toque los canales vecinos (a ±S/2) ni la cobija inferior. Estado estacionario: igual para todas las hiladas."""
    th, S, g = TILE_TH, TILE_S, TILE_GAP
    D = TILE_RW - TILE_RN
    angs = [-th + 2 * th * i / 16 for i in range(17)]
    xs = [TILE_L * i / 12 for i in range(13)]
    nb = nt = 0.0

    def ri_cob(x):
        return TILE_RW - D * x / TILE_L

    for _ in range(6):
        req = []
        for x in xs:
            ri = ri_cob(x)
            ro = ri + TILE_T
            q = -1.0
            for (cn, rci, rco) in _canal_sec(x):
                for cu in (S / 2, -S / 2):
                    # puntos de la cobija contra la cara superior del canal
                    for rr in (ri, ro):
                        for a in angs:
                            du = rr * math.sin(a) - cu
                            if abs(du) <= rci * math.sin(th):
                                top = cn - math.sqrt(max(rci ** 2 - du ** 2, 0.0))
                            elif abs(du) <= rco * math.sin(th):
                                f = (abs(du) - rci * math.sin(th)) / ((rco - rci) * math.sin(th))
                                top = cn - (rci + f * (rco - rci)) * math.cos(th)
                            else:
                                continue
                            q = max(q, top + g - rr * math.cos(a))
                    # cantos del canal contra la cara interior de la cobija
                    for rr in (rci, rco):
                        for sg in (-1, 1):
                            uq = cu + sg * rr * math.sin(th)
                            nq = cn - rr * math.cos(th)
                            if abs(uq) <= ri * math.sin(th):
                                q = max(q, nq + g - math.sqrt(ri ** 2 - uq ** 2))
                            elif abs(uq) <= ro * math.sin(th):
                                q = max(q, nq + g - ri * math.cos(th))
            # sobre el plano de rastreles
            q = max(q, g - ri * math.cos(th))
            # cobija inferior (su boca estrecha queda bajo la ancha de esta)
            xl = x + TILE_E
            if xl <= TILE_L:
                nl = nb + (nt - nb) * xl / TILE_L
                rol = ri_cob(xl) + TILE_T
                for a in angs:
                    uq, nq = rol * math.sin(a), nl + rol * math.cos(a)
                    if abs(uq) < ri * math.sin(th):
                        q = max(q, nq + g - math.sqrt(ri ** 2 - uq ** 2))
            req.append(q)
        nb2 = max(q for x, q in zip(xs, req) if x <= TILE_L / 2)
        nt2 = max(q for x, q in zip(xs, req) if x >= TILE_L / 2)
        lift = max(q - (nb2 + (nt2 - nb2) * x / TILE_L) for x, q in zip(xs, req))
        nb, nt = nb2 + max(lift, 0.0), nt2 + max(lift, 0.0)
    return nb, nt


_COB = None


def _cob():
    global _COB
    if _COB is None:
        _COB = _cobija_lifts()
    return _COB


def _tile_env():
    """Altura máxima de la capa de teja sobre TILE_N (perpendicular)."""
    nb, nt = _cob()
    can = max(LB + TILE_RN + TILE_T - TILE_RN * math.cos(TILE_TH), TILE_RW + TILE_T - TILE_RW * math.cos(TILE_TH))
    cob = max(nb + TILE_RW + TILE_T, nt + TILE_RN + TILE_T)
    return max(can, cob) + 0.012


def _cap_run(mb, R, P0, P1, b, normals, r, seg, h_layer, gap=0.004, beads=True, plug0=False, plug1=False, skip=None,
             bead_sides=(-1, 1), bead_depth=0.1, skirt=None, mode="closed", bead=(6, 1)):
    """Caballetes de P0 a P1 (boca ancha hacia P0, solape ~1/4) sobre la línea de cumbrera/limatesa, con cordones de mortero.
    b = 'arriba' del caballete; normals = normales de los dos planos; h_layer = altura de la capa de teja sobre el plano de cabios.
    skirt = (lado, z_piso): en ese lado el cordón es un faldón de mortero enrasado que baja del canto del caballete hasta z_piso
    (remate de hastial sobre la tabla de remate). mode = modo de _tile_piece de los caballetes (por dentro los tapa el lecho);
    bead = (puntos del perfil 6|4, paso de estaciones en múltiplos de 0,14 m). Los cortes del cordón no dependen del nivel."""
    P0, P1 = _vec(P0), _vec(P1)
    X = (P1 - P0).normalized()
    Z = (b - X * b.dot(X)).normalized()
    Y = Z.cross(X)
    Ltot = (P1 - P0).length

    def env(du):
        n = max(normals, key=lambda nn: nn.dot(Y) * (1 if du >= 0 else -1))
        return -du * n.dot(Y) / n.dot(Z) + h_layer / n.dot(Z)

    H = -1.0
    for rr in (CAP_RN, CAP_RW):
        for t_ in (0.0, CAP_T):
            rad = rr + t_
            for i in range(25):
                a = -CAP_TH + 2 * CAP_TH * i / 24
                du = rad * math.sin(a)
                H = max(H, env(du) + gap - rad * math.cos(a))
        for i in range(31):
            du = -rr * math.sin(CAP_TH) + 2 * rr * math.sin(CAP_TH) * i / 30
            H = max(H, env(du) + gap - math.sqrt(max(rr ** 2 - du ** 2, 0.0)))
    n_caps = max(1, int(math.ceil((Ltot - CAP_L) / CAP_STEP)) + 1)
    step = (Ltot - CAP_L) / max(n_caps - 1, 1) if n_caps > 1 else 0.0
    base = _frame_m(X, Y, Z, P0 + Z * H)
    for i in range(n_caps):
        x = i * step
        rot = (r.uniform(-1.2, 1.2), r.uniform(-0.25, 0.25))
        if skip is not None and skip(P0 + X * (x + CAP_L / 2)):
            continue
        M = base @ _T(x, 0, 0) @ _about((CAP_L / 2, 0, 0), _R("X", rot[0]) @ _R("Z", rot[1]))
        last = i == n_caps - 1
        _tile_piece(mb, M, seg, r, True, True, rn=CAP_RN, rw=CAP_RW, t=CAP_T, th=CAP_TH, L=CAP_L,
                    mode="closed" if (last and not plug1) else mode)
    # tapón de mortero en las bocas de los extremos
    for flag, x, rr in ((plug0, 0.012, CAP_RW), (plug1, Ltot - 0.012 - 0.035, CAP_RN)):
        if not flag:
            continue
        rr2 = rr - 0.003
        pts = [(rr2 * math.sin(a), rr2 * math.cos(a)) for a in [-CAP_TH + 2 * CAP_TH * i / 8 for i in range(9)]]
        low = min(env(p[0]) for p in pts) - 0.04
        pts = [pts[0], *pts, pts[-1]]
        pts[0] = (pts[0][0], low)
        pts[-1] = (pts[-1][0], low)
        outline = list(reversed(pts))
        m = base @ _T(x, 0, 0) @ _frame_m(Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((1, 0, 0)), Vector((0, 0, 0)))
        mb.plate(outline, 0.035, "mortar", m=m)
    if not beads:
        return H
    # cordones de mortero a ambos lados (con tramos desprendidos). Los cortes salen de un rng propio sobre la rejilla fija de
    # 0,14 m, así que son los mismos en todos los niveles; el nivel solo submuestrea las estaciones de cada tramo.
    nz = _N1(r, wl=0.7)
    rb = rng(int(r.integers(0, 2 ** 31)))
    npts, stride = bead
    for sg in bead_sides:
        n_st = max(2, int(Ltot / 0.14))
        runs, cur = [], []
        for i in range(n_st + 1):
            x = Ltot * i / n_st
            if rb.uniform() < 0.02 and len(cur) >= 3:
                runs.append(cur)
                cur = []
                continue
            cur.append(x)
        if cur:
            runs.append(cur)
        for run in runs:
            if len(run) < 3:
                continue
            if stride > 1:
                run = [x for ii, x in enumerate(run) if ii % stride == 0 or ii == len(run) - 1]
                if len(run) < 2:
                    continue
            rings = []
            for ii, x in enumerate(run):
                rr = (CAP_RW + CAP_RN) / 2
                yr = sg * (rr + CAP_T * 0.5) * math.sin(CAP_TH)
                zr = H + rr * math.cos(CAP_TH)
                k = 1.0 + 0.45 * nz(x + sg * 3.1)
                ye = yr + sg * 0.045 * k
                yb_ = yr + sg * 0.028 * k
                end = ii in (0, len(run) - 1)
                if skirt is not None and sg == skirt[0]:
                    zf = skirt[1]
                    prof = [(yr - sg * 0.03, zr + 0.004), (yr + sg * (0.004 + 0.004 * k), zr + 0.002),
                            (yr + sg * (0.008 + 0.006 * k), (zr + zf) / 2), (yr + sg * (0.004 + 0.004 * k), zf),
                            (yr - sg * 0.04, zf)]
                    if npts < 6:
                        prof = [prof[0], prof[2], prof[3], prof[4]]
                    if end:
                        cy, cz = yr - sg * 0.01, (zr + zf) / 2
                        prof = [(cy + (py - cy) * 0.7, cz + (pz - cz) * 0.7) for py, pz in prof]
                    o = P0 + X * x
                    rings.append([o + Y * py + Z * pz for (py, pz) in prof])
                    continue
                # el lecho baja hasta el fondo de los canales (sin huecos bajo el caballete)
                prof = [(yr - sg * 0.022, zr + 0.004), (yr + sg * 0.006, zr + 0.003), (yb_, (zr + env(yb_)) / 2 + 0.008 * k),
                        (ye, env(ye) - 0.01 + 0.007 * k), (ye + sg * 0.004, env(ye) - bead_depth),
                        (yr - sg * 0.03, env(yr) - bead_depth)]
                if npts < 6:
                    prof = [prof[0], prof[3], prof[4], prof[5]]
                if end:
                    # extremos del tramo redondeados (se encogen hacia el canto del caballete)
                    cy, cz = yr + sg * 0.01, zr - 0.02
                    prof = [(cy + (py - cy) * 0.35, cz + (pz - cz) * 0.35) for py, pz in prof]
                o = P0 + X * x
                rings.append([o + Y * py + Z * pz for (py, pz) in prof])
            _loft(mb, rings, "mortar")
    return H


def barrel_tiles(w, d, kind, pitch_deg, overhang, seed=0, missing=0.04, hole=None, rake=None, seg=6, detail="high"):
    """Teja curva de barro (canal + cobija alternadas, 0,45 m, solape 1/3) sobre roof_frame(kind, w, d, pitch_deg, overhang,
    cover='tile') con las mismas medidas. Canales con la boca estrecha abajo anidados en el canal inferior; cobijas resueltas
    numéricamente sobre los canales (sin intersecciones nominales). Recorte en limatesas por centro de pieza, caballetes con cordón
    de mortero en cumbrera y limatesas, boquillas de mortero en el alero, jitter por pieza, tejas faltantes, cobijas corridas
    (resbaladas 15–21 cm, salen de debajo de la superior y montan sobre la inferior sin intersecarla) y rotas.
    hole = (x, y, r) en planta: hueco que deja ver la estructura (usa damage_spot(...) para que coincida con roof_frame).

    detail = 'high' | 'mid' | 'low' (TILE_LOD). Misma disposición en los tres niveles. 'high' = todas las piezas son sólidos
    cerrados con `seg` segmentos (seg solo se usa en 'high'). En 'mid' y 'low' son sólidos cerrados SOLO las piezas EXPUESTAS:
    hiladas cuyo intradós se ve desde abajo en el vuelo del alero (y una más en 'mid'), líneas sobre el vuelo de remate del
    hastial, piezas junto al hueco, corridas o rotas, y toda pieza con una vecina (3 x 3 en su vertiente) faltante, corrida o
    rota. Las demás pierden primero las caras que nunca se ven: la cara inferior tapada por la hilada y los canales vecinos y la
    testa alta tapada por la hilada de arriba.
      'mid': cobija y canal = cara vista + labio + cantos (24 tris) · caballetes abiertos por dentro (los tapa el lecho).
      'low': cobija = trasdós de 5 tramos + labio (20 tris) · canal = franja central cerrada de 8 tris (el resto del canal lo
             tapan siempre las cobijas) · boquillas, cordón y remates simplificados.
    Las piezas abiertas solo se ven por su cara vista (orientada hacia fuera): no necesitan DoubleSide. Medido con
    test_G3 (--budget) en un hip de 16 x 12,5 m en planta con alero (14,8 x 11,3 + vuelo 0,6, 26°, 222,5 m² de faldón,
    ~6200 tejas):
      high ~331 k tris (~1490 tris/m²) · mid ~188 k (~845/m²) · low ~108 k (~485/m²)   [antes de este control: 524 k]."""
    if detail not in TILE_LOD:
        raise ValueError("detail debe ser 'high', 'mid' o 'low'")
    lod = dict(TILE_LOD[detail])
    if detail == "high":
        lod.update(cob=seg, can=seg, cap=seg + 1)
    R = _Roof(kind, w, d, pitch_deg, overhang, rake)
    r = rng(seed + 4242)
    mb = MB()
    nb_c, nt_c = _cob()
    h_env = _tile_env()
    courses = _tile_courses(R.vlen)
    hl = None
    if hole is not None:
        hx, hy = _plan_local(R, hole[0], hole[1])
        hl = (hx, hy, float(hole[2]))
    hn = _N1(r, wl=1.3)
    fu = _N1(r, wl=2.3)          # deriva suave de las líneas (todas juntas: no rompe el anidado)
    fn = _N1(r, wl=1.7)          # abultamiento suave de la capa
    clump = _N1(r, wl=1.1)
    D_T = TILE_RW - TILE_RN

    def in_hole(x, y, extra=0.0):
        if hl is None:
            return False
        dx, dy = x - hl[0], y - hl[1]
        a = math.atan2(dy, dx)
        rad = hl[2] * (1.0 + 0.2 * hn(a * 1.7)) + extra
        return dx * dx + dy * dy < rad * rad

    # ---- pasada 1: disposición (todas las decisiones aleatorias; no depende del nivel de detalle) ----
    frags, pieces, grid = [], [], {}
    for s in R.slopes:
        ulo, uhi = R.u_limits(s, 0.0)
        imax = int(abs(uhi) / (TILE_S / 2)) + 2
        for j in range(-imax, imax + 1):
            u_line = j * TILE_S / 2
            is_canal = (j % 2 == 0)
            line_off = r.uniform(-0.002, 0.002)
            for k, vb in enumerate(courses):
                vm = vb + TILE_L / 2
                u0, u1 = R.u_limits(s, vm)
                if kind == "gable":
                    if not (u0 + 0.112 <= u_line <= u1 - 0.112):
                        continue
                elif not (u0 + 0.03 <= u_line <= u1 - 0.03):
                    continue
                du_f = 0.010 * fu(u_line * 0.37 + vm * 0.9 + (0 if s in ("front", "back") else 7.0))
                u = u_line + du_f + line_off + r.uniform(-0.0015, 0.0015)
                px, py = R.to_plan(s, u, vm)
                if in_hole(px, py):
                    grid[(s, j, k)] = 1
                    if r.uniform() < 0.25:
                        frags.append((s, u, vm, is_canal))
                    continue
                near = in_hole(px, py, 0.45)
                pm = missing * (0.7 if is_canal else 1.35) * max(0.0, 1.0 + 1.6 * clump(px * 0.8 + py * 1.3))
                if near:
                    pm += 0.25
                if k == len(courses) - 1 and kind == "hip" and s in ("right", "left"):
                    pm *= 0.5
                if r.uniform() < pm:
                    grid[(s, j, k)] = 1
                    if r.uniform() < 0.3:
                        frags.append((s, u, vm, is_canal))
                    continue
                lift = 0.006 * max(0.0, fn(px * 0.6 + py * 0.9)) + r.uniform(0.0, 0.0015)
                roll, yaw, dv = r.uniform(-2.5, 2.5), r.uniform(-0.3, 0.3), r.uniform(-0.004, 0.004)
                x0, jag0, slid, lb, lt = 0.0, 0.0, 0.0, 0.0, 0.0
                if near and r.uniform() < 0.5 or r.uniform() < 0.012:
                    a_dv, a_lift, a_roll, a_yaw = r.uniform(0.03, 0.09), r.uniform(0.012, 0.025), r.uniform(-7, 7), r.uniform(-3.5, 3.5)
                    if not is_canal and k > 0:
                        # cobija corrida: resbala 15–21 cm (sale de debajo de la superior) y monta sobre la inferior; se levanta
                        # lo que pierde de holgura al resbalar + el giro en planta (limitado a ±1,2°) para no intersecarla
                        slid = 0.15 + (a_dv - 0.03)
                        dv -= slid
                        roll += a_roll
                        yaw = max(-1.2, min(1.2, yaw + 0.3 * a_yaw))
                        lt = 0.004 + D_T * slid / TILE_L
                        lb = lt + 3.0 * 0.225 * math.sin(math.radians(abs(yaw))) + 0.3 * a_lift
                elif near and r.uniform() < 0.4 or r.uniform() < 0.025:
                    x0, jag0 = r.uniform(0.05, 0.16), 0.03         # rota: falta el borde visto
                jseed = int(r.integers(0, 2 ** 31)) if jag0 else 0
                boq = k == 0 and not is_canal and r.uniform() < 0.8 and x0 == 0.0
                grid[(s, j, k)] = 2 if (slid or x0) else 0
                pieces.append((s, j, k, u, vb, dv, lift, lb, lt, roll, yaw, x0, jag0, jseed, is_canal, near, boq))

    # ---- pasada 2: geometría según el nivel ----
    v_eave = R.ov / R.cp + 0.02 + lod["eave_extra"] * TILE_E
    rake_u = R.hw - 0.05
    extra_lift = {}                  # elevación de la cobija corrida para la superior de la misma línea si también se corrió
    def bad(j_, k_):
        return grid.get((s, j_, k_), 0) != 0

    mid = detail == "mid"
    for (s, j, k, u, vb, dv, lift, lb, lt, roll, yaw, x0, jag0, jseed, is_canal, near, boq) in pieces:
        Ms = R.matrix(s)
        if detail == "high" or near or x0 or lb:
            mode = _FULL
        else:
            # caras que deja ver cada situación (ver docstring); en 'low' solo las que se ven desde las vistas típicas
            under = vb + TILE_L - TILE_E < v_eave or (kind == "gable" and abs(u) > rake_u)
            g = set(_MODES[lod["open"]])
            if is_canal:
                if under or (mid and bad(j, k - 1)):
                    g.add("hid")
                if mid and bad(j, k + 1):
                    g.add("cap")
                if bad(j - 1, k) or bad(j + 1, k):
                    g.add("sides")          # sin la cobija de al lado se ve el canal entero
            else:
                if under or bad(j, k - 1) or (mid and (bad(j - 1, k) or bad(j + 1, k))):
                    g.add("hid")
                if bad(j, k + 1):
                    g.add("cap")
            mode = "prism" if (is_canal and detail == "low" and not g) else frozenset(g)
        if is_canal:
            nb, nt = TILE_N + LB + TILE_RN + TILE_T + lift, TILE_N + TILE_RW + TILE_T + lift
        else:
            base = extra_lift.get((s, j, k - 1), 0.0) if lb else 0.0
            if base:
                base += 0.004
            nb, nt = TILE_N + nb_c + lift + lb + base, TILE_N + nt_c + lift + lt + base
            if lb:
                extra_lift[(s, j, k)] = lb + base
        M = Ms @ _tile_m(u, vb + dv, nb, nt) @ _about((TILE_L / 2, 0, 0), _R("X", roll) @ _R("Z", yaw))
        _tile_piece(mb, M, lod["can"] if is_canal else lod["cob"], rng(jseed) if jag0 else None, not is_canal, not is_canal,
                    x0=x0, jag0=jag0, mode=mode, angles=_CAN_LOW if (is_canal and detail == "low") else None,
                    lip_c=detail == "low")
        if boq:
            # boquilla de mortero en la boca de la cobija del alero
            rr = TILE_RW - 0.004
            nq = lod["boq"] - 1
            pts = [(rr * math.sin(a), rr * math.cos(a)) for a in [-TILE_TH + 2 * TILE_TH * i / nq for i in range(nq + 1)]]
            low = rr * math.cos(TILE_TH) - 0.05
            pts = [(pts[0][0], low)] + pts + [(pts[-1][0], low)]
            m = M @ _T(0.012, 0, 0) @ _frame_m(Vector((0, 1, 0)), Vector((0, 0, 1)), Vector((1, 0, 0)), Vector((0, 0, 0)))
            mb.plate(list(reversed(pts)), 0.03, "mortar", m=m)

    # ---- caballetes ----
    ns = {s: R.frame(s)[3] for s in R.slopes}
    h_layer = TILE_N + h_env
    bd = 0.85 * h_env
    Z = Vector((0, 0, 1))
    cap_kw = dict(mode=lod["cap_mode"], bead=lod["bead"])

    def skip(p):
        return in_hole(p.x, p.y, 0.1)

    if kind == "gable":
        e = R.hw + R.ovr + 0.03
        _cap_run(mb, R, (-e, 0, R.z_ridge), (e, 0, R.z_ridge), Z, [ns["front"], ns["back"]], r, lod["cap"], h_layer,
                 plug0=True, plug1=True, skip=skip, bead_depth=bd, **cap_kw)
        # remate de hastial: caballetes recibidos con mortero sobre la última línea y el rastrel hasta la tabla de remate
        for s in ("front", "back"):
            Nn = ns[s]
            for sx in (-1, 1):
                ue = sx * (R.hw + R.ovr - 0.075)
                P0 = R.to_world(s, ue, TILE_V0 + 0.01)
                P1 = R.to_world(s, ue, R.vlen - 0.16)
                _cap_run(mb, R, P0, P1, Nn, [Nn, Nn], r, lod["cap"], h_layer, plug0=True, skip=skip, bead_depth=bd,
                         skirt=(-1 if ue > 0 else 1, BAT_T + 0.016), **cap_kw)
    else:
        xr = R.ridge_half
        if xr > 0.05:
            _cap_run(mb, R, (-xr - 0.05, 0, R.z_ridge), (xr + 0.05, 0, R.z_ridge), Z, [ns["front"], ns["back"]], r,
                     lod["cap"], h_layer, skip=skip, bead_depth=bd, **cap_kw)
        z_e = R.zt0 - R.ov * R.tp
        for sx in (-1, 1):
            for sy in (-1, 1):
                c = Vector((sx * (R.hw + R.ov), sy * (R.hd + R.ov), z_e))
                top = Vector((sx * xr, 0.0, R.z_ridge))
                c = c + (top - c).normalized() * 0.02
                n1 = ns["front"] if sy < 0 else ns["back"]
                n2 = ns["right"] if sx > 0 else ns["left"]
                Hh = _cap_run(mb, R, c, top + (top - c).normalized() * 0.04, (n1 + n2).normalized(), [n1, n2], r,
                              lod["cap"], h_layer, plug0=True, skip=skip, bead_depth=bd, **cap_kw)
            # remate de mortero donde se juntan limatesas y cumbrera
            p = Vector((sx * (xr + 0.02), 0.0, R.z_ridge + (Hh or 0.1) + 0.02))
            rad = [0.02, 0.075, 0.11, 0.125, 0.115, 0.08, 0.025]
            pts = [p + Vector((sx * (i - 3) * 0.05, r.uniform(-0.008, 0.008), r.uniform(-0.006, 0.006) - 0.012 * abs(i - 3)))
                   for i in range(7)]
            mb.tube(pts, 0.1, seg=lod["tube"], mat="mortar", radii=[q * r.uniform(0.92, 1.08) for q in rad])

    # ---- fragmentos: sobre las crestas de las cobijas bajo el hueco y caídos dentro (z = 0) ----
    crown = TILE_N + max(nb_c + TILE_RW, nt_c + TILE_RN) + TILE_T
    for (s, u, vm, is_canal) in frags[:14]:
        Ms = R.matrix(s)
        L = r.uniform(0.09, 0.22)
        if hl is not None and r.uniform() < 0.5:
            # caído al piso bajo el hueco (apoya en las puntas del arco a 2 mm del piso)
            a = r.uniform(0, 2 * PI)
            px = hl[0] + r.uniform(-0.7, 0.7) * hl[2]
            py = hl[1] + r.uniform(-0.7, 0.7) * hl[2]
            px = min(max(px, -R.hw + 0.4), R.hw - 0.4)
            py = min(max(py, -R.hd + 0.4), R.hd - 0.4)
            rr = TILE_RN + r.uniform(0, 0.02)
            zc = 0.002 - rr * math.cos(TILE_TH)
            M = _T(px, py, zc) @ _R("Z", math.degrees(a)) @ _T(-L / 2, 0, 0)
            _tile_piece(mb, M, lod["cob"], rng(int(r.integers(0, 2 ** 31))), True, False, x0=0.0, x1=L, jag0=0.02, jag1=0.02,
                        rn=rr, rw=rr)
        else:
            vf = vm - r.uniform(0.5, 1.2)
            if vf < 0.3:
                continue
            # trozo boca abajo tendido sobre la cresta de la cobija más cercana: la punta más baja del arco (tras el giro)
            # queda 3 mm sobre la cresta
            du, yw, tl, _ = r.uniform(-0.1, 0.1), r.uniform(-60, 60), r.uniform(-15, 15), r.uniform()
            uc = (2 * round(((u + du) / (TILE_S / 2) - 1) / 2) + 1) * TILE_S / 2
            ra = TILE_RN + 0.01
            phi = tl * 0.25
            M = Ms @ _T(uc, vf, crown + 0.003 - ra * math.cos(TILE_TH + math.radians(abs(phi)))) @ \
                _R("Z", yw) @ _R("X", phi) @ _T(-L / 2, 0, 0)
            _tile_piece(mb, M, lod["cob"], rng(int(r.integers(0, 2 ** 31))), True, False, x0=0.0, x1=L, jag0=0.02, jag1=0.02,
                        rn=ra, rw=ra)
    return R.finalize(mb)


# =====================================================================================================================
# 3) LÁMINA ONDULADA
# =====================================================================================================================
CORR_P, CORR_A = 0.076, 0.018           # paso y altura de onda
CORR_WAVES = 13                         # 13 ondas = 0,988 de ancho total; ancho útil 12 ondas = 0,912 (~0,9)
CORR_SEG = 8                            # segmentos por onda
CORR_LAP_E = 0.15                       # solape de testa


def _lamina(mb, P, mat, keep=None):
    """Malla de cuadriláteros de una cara (lámina) a partir de una rejilla de puntos P[j][i]. keep(i, j) filtra celdas.
    Solo crea los vértices usados (sin vértices sueltos)."""
    rows, cols = len(P), len(P[0])
    V = {}

    def gv(i, j):
        if (i, j) not in V:
            V[(i, j)] = mb.bm.verts.new(P[j][i])
        return V[(i, j)]
    for j in range(rows - 1):
        for i in range(cols - 1):
            if keep is not None and not keep(i, j):
                continue
            mb.face([gv(i, j), gv(i + 1, j), gv(i + 1, j + 1), gv(i, j + 1)], mat)


def _screw(mb, p, N, r, tilt=0.0, mat="metal_rust"):
    """Tornillo autorroscante con arandela de neopreno sobre una cresta (p en la superficie, N normal)."""
    N = _vec(N).normalized()
    if tilt:
        ax = N.orthogonal().normalized()
        N = (Matrix.Rotation(math.radians(tilt), 3, ax) @ N).normalized()
    p = _vec(p)
    mb.cyl(p + N * 0.0006, p + N * 0.0031, 0.0105, seg=8, mat="cable")
    mb.cyl(p + N * 0.0033, p + N * 0.0085, 0.0056, seg=6, mat=mat)


def corrugated_roof(w, d, pitch_deg, overhang, seed=0, light=False, torn=None, rake=None, row=0.18, lifted=True):
    """Cubierta a dos aguas de lámina ondulada sobre roof_frame('gable', w, d, pitch_deg, overhang, cover='sheet').
    Láminas de 13 ondas (0,9 útil) con solape lateral de 1 onda y de testa de 0,15, onda sinusoidal de 8 segmentos, flecha entre
    correas, abolladuras, tornillos con arandela en crestas sobre cada correa, cumbrera de lámina doblada con dobladillo,
    tapajuntas de remate en L, una lámina con la esquina levantada/doblada y `torn` = sección arrancada con borde rizado
    (torn=True usa damage_spot('gable', ...); o (x, y, r) en planta). Láminas = superficies de una cara (LAMINA_MATS)."""
    R = _Roof("gable", w, d, pitch_deg, overhang, rake)
    r = rng(seed + 31337)
    mat = "roof_metal_light" if light else "roof_metal"
    mb = MB()
    ue = R.hw + R.ovr + 0.04
    v0, v1 = -0.07, R.vlen - 0.025
    purl = _purlin_vs(R.vlen)
    if torn is True:
        torn = damage_spot("gable", w, d, pitch_deg, overhang, seed, 0.6)
    tl = None
    if torn:
        tx, ty = _plan_local(R, torn[0], torn[1])
        tl = (tx, ty, float(torn[2]))
    tn = _N1(r, wl=0.9, n=4)
    curl_n = _N1(r, wl=1.4)
    sag_n = _N1(r, wl=3.0)
    eave_n = _N1(r, wl=2.2)

    def torn_rad(a):
        # más largo a lo largo de la onda (el desgarro sigue las crestas), borde irregular sin picos regulares
        el = 1.0 / math.sqrt((math.cos(a) / 0.85) ** 2 + (math.sin(a) / 1.25) ** 2)
        return tl[2] * el * (1.0 + 0.16 * tn(a * 2.3) + 0.035 * tn(a * 9.7 + 4.0))

    # filas de láminas (testa) y columnas
    total = v1 - v0
    nrow = max(1, int(math.ceil((total - CORR_LAP_E) / (3.66 - CORR_LAP_E))))
    Ls = (total + (nrow - 1) * CORR_LAP_E) / nrow
    rows_v = [(v0 + j * (Ls - CORR_LAP_E), v0 + j * (Ls - CORR_LAP_E) + Ls) for j in range(nrow)]
    cover = CORR_P * (CORR_WAVES - 1)
    ncol = int(math.ceil((2 * ue - CORR_P) / cover))
    cols_u = []
    for i in range(ncol):
        ua = -ue + i * cover
        cols_u.append((ua, min(ua + CORR_P * CORR_WAVES, ue)))

    def wave(u):
        return CORR_A * 0.5 * (1.0 - math.cos(2 * PI * (u + ue) / CORR_P))

    oil = _N1(r, wl=0.8)

    def sag(u, v):
        if v <= purl[0] or v >= purl[-1]:
            return 0.0
        for a, b in zip(purl[:-1], purl[1:]):
            if a <= v <= b:
                f = math.sin(PI * (v - a) / (b - a))
                # flecha + ondulación de chapa vieja (cero sobre las correas: nunca atraviesa el apoyo)
                return -(0.004 + 0.003 * sag_n(u * 0.5)) * f + 0.004 * oil(u * 1.3 + v * 0.7) * f * f
        return 0.0

    def eave_curl(u, v):
        return -0.012 * (0.6 + 0.4 * eave_n(u)) * max(0.0, (v0 + 0.14 - v) / 0.14) ** 2

    lift_pick = None
    if lifted:
        cand = [(s, i) for s in ("front", "back") for i in range(1, ncol - 1)]
        lift_pick = cand[int(r.integers(0, len(cand)))]
        la, lb_, lphi = r.uniform(0.6, 0.95), r.uniform(0.9, 1.6), math.radians(r.uniform(40, 68))

    for s in R.slopes:
        Ms = R.matrix(s)
        Nw = R.frame(s)[3]
        sgn_plan = -1 if s == "front" else 1
        for j, (va, vb) in enumerate(rows_v):
            for i, (ua, ub) in enumerate(cols_u):
                # ---- rejilla en coordenadas de vertiente ----
                nu = max(2, int(round((ub - ua) / (CORR_P / CORR_SEG))))
                us = [ua + (ub - ua) * k / nu for k in range(nu + 1)]
                nv = max(2, int(math.ceil((vb - va) / row)))
                vs = sorted({va + (vb - va) * k / nv for k in range(nv + 1)} |
                            {p for p in purl if va + 0.02 < p < vb - 0.02})
                dents = []
                for _ in range(int(r.integers(0, 3))):
                    dents.append((r.uniform(ua + 0.2, max(ua + 0.21, ub - 0.2)), r.uniform(va + 0.3, max(va + 0.31, vb - 0.3)),
                                  r.uniform(0.08, 0.22), r.uniform(0.006, 0.02)))
                dents = [dd for dd in dents if all(abs(dd[1] - p) > dd[2] + 0.05 for p in purl)]
                peel = lift_pick == (s, i) and j == 0
                P, inside = [], []
                for v in vs:
                    rowp, rowi = [], []
                    for u in us:
                        n = SHEET_N + wave(u) + sag(u, v) + eave_curl(u, v)
                        if i > 0:
                            n += 0.003 * _ss(1.0 - (u - ua - CORR_P - 0.01) / 0.06)
                        if j > 0:
                            n += 0.006 * _ss(1.0 - (v - va - CORR_LAP_E - 0.02) / 0.08)
                        for (du, dv, rr, dp) in dents:
                            q = ((u - du) ** 2 + (v - dv) ** 2) / (rr * rr)
                            if q < 4.0:
                                n -= dp * math.exp(-q * 1.6)
                        uu, vv = u, v
                        ins = False
                        if tl is not None:
                            px, py = R.to_plan(s, u, v)
                            dx, dy = px - tl[0], py - tl[1]
                            dd = math.hypot(dx, dy)
                            a = math.atan2(dy, dx)
                            rad = torn_rad(a)
                            if dd < rad:
                                ins = True
                            elif dd < rad + 0.16:
                                t = 1.0 - (dd - rad) / 0.16
                                n += (0.015 + 0.06 * max(0.0, curl_n(a * 3.0))) * t * t
                        if peel:
                            # esquina inferior izquierda levantada: doblez alrededor de la línea (ua + la, va) – (ua, va + lb_)
                            A = Vector((ua + la, va))
                            B = Vector((ua, va + lb_))
                            e = (B - A).normalized()
                            perp = Vector((-e.y, e.x))
                            if perp.dot(Vector((ua, va)) - A) < 0:
                                perp = -perp
                            q = Vector((u, v)) - A
                            dpl = q.dot(perp)
                            if dpl > 0:
                                bz = 0.14
                                rho = bz / lphi
                                if dpl <= bz:
                                    along, up = rho * math.sin(dpl / rho), rho * (1 - math.cos(dpl / rho))
                                else:
                                    along = rho * math.sin(lphi) + (dpl - bz) * math.cos(lphi)
                                    up = rho * (1 - math.cos(lphi)) + (dpl - bz) * math.sin(lphi)
                                base2 = A + e * q.dot(e) + perp * along
                                uu, vv = base2.x, base2.y
                                n += up
                        rowp.append(Ms @ Vector((uu, vv, n)))
                        rowi.append(ins)
                    P.append(rowp)
                    inside.append(rowi)
                # celdas dentro del hueco fuera; vértices interiores de celdas que quedan -> al borde (radial)
                if tl is not None:
                    for jj in range(len(vs)):
                        for ii in range(len(us)):
                            if not inside[jj][ii]:
                                continue
                            p = P[jj][ii]
                            dx, dy = p.x - tl[0], p.y - tl[1]
                            a = math.atan2(dy, dx)
                            rad = torn_rad(a) + 0.002
                            dd = max(math.hypot(dx, dy), 1e-6)
                            sx_, sy_ = dx / dd * (rad - dd), dy / dd * (rad - dd)
                            # se desplaza en planta sobre el faldón y recibe el rizo máximo del borde arrancado
                            curl = 0.015 + 0.06 * max(0.0, curl_n(a * 3.0))
                            P[jj][ii] = p + Vector((sx_, sy_, -sgn_plan * R.tp * sy_)) + Nw * curl

                def keep(ii, jj, inside=inside):
                    return not (inside[jj][ii] and inside[jj][ii + 1] and inside[jj + 1][ii] and inside[jj + 1][ii + 1]) and \
                        sum((inside[jj][ii], inside[jj][ii + 1], inside[jj + 1][ii], inside[jj + 1][ii + 1])) < 3
                _lamina(mb, P, mat, keep if tl is not None else None)

                # ---- tornillos en crestas sobre correas ----
                m0 = int(math.ceil((ua + ue - CORR_P / 2) / CORR_P))
                crests = []
                m = m0
                while True:
                    uc = -ue + CORR_P / 2 + m * CORR_P
                    if uc > ub - 0.01:
                        break
                    if uc > ua + 0.01:
                        crests.append((m, uc))
                    m += 1
                for p in purl:
                    if not (va + 0.03 < p < vb - 0.03):
                        continue
                    if j < nrow - 1 and p > vb - CORR_LAP_E - 0.02:
                        continue                      # lo tapa la lámina superior (se atornilla en ella)
                    for k, (m, uc) in enumerate(crests):
                        last = k == len(crests) - 1 and i < ncol - 1
                        if last or not (k == 0 or (m % 3 == 0)):
                            continue
                        if peel:
                            continue
                        if r.uniform() < 0.07:
                            continue
                        n = SHEET_N + wave(uc) + sag(uc, p)
                        if i > 0:
                            n += 0.003 * _ss(1.0 - (uc - ua - CORR_P - 0.01) / 0.06)
                        if j > 0:
                            n += 0.006 * _ss(1.0 - (p - va - CORR_LAP_E - 0.02) / 0.08)
                        if tl is not None:
                            px, py = R.to_plan(s, uc, p)
                            if math.hypot(px - tl[0], py - tl[1]) < tl[2] * 1.35 + 0.2:
                                continue
                        loose = r.uniform() < 0.05
                        q = Ms @ Vector((uc, p, n + (0.004 if loose else 0.0)))
                        _screw(mb, q, (Ms.to_3x3() @ Vector((0, 0, 1))), r, tilt=r.uniform(8, 25) if loose else r.uniform(0, 3))

    # ---- cumbrera de lámina doblada ----
    n0 = SHEET_N + CORR_A + 0.015
    ridge_piece, ridge_lap = 1.8, 0.12
    xs0, xs1 = -ue - 0.03, ue + 0.03
    npc = max(1, int(math.ceil((xs1 - xs0 - ridge_lap) / (ridge_piece - ridge_lap))))
    Lp = (xs1 - xs0 + (npc - 1) * ridge_lap) / npc
    wing = [(0.205, -0.016), (0.20, 0.0), (0.12, 0.0015), (0.05, 0.004), (0.0, 0.0055)]
    for pc in range(npc):
        xa = xs0 + pc * (Lp - ridge_lap)
        xb = xa + Lp
        lift = 0.003 * (pc % 2)
        nx = max(2, int(math.ceil((xb - xa) / 0.15)))
        P = []
        for kx in range(nx + 1):
            x = xa + (xb - xa) * kx / nx
            wob = r.uniform(-0.0015, 0.0015)
            prof = []
            for sgn in (-1, 1):
                sname = "front" if sgn < 0 else "back"
                pts = [R.to_world(sname, -x if sname == "back" else x, R.vlen - dv, n0 + dn + lift + wob) for dv, dn in wing]
                if sgn > 0:
                    pts = list(reversed(pts))
                    # lomo redondeado entre las dos alas
                    ya, yb, za = prof[-1].y, pts[0].y, max(prof[-1].z, pts[0].z)
                    for t in (0.25, 0.5, 0.75):
                        prof.append(Vector((x, ya + (yb - ya) * t, za + 0.012 * math.sin(PI * t))))
                prof.extend(pts)
            P.append(prof)
        # P[kx][k] -> rejilla (filas = estaciones x)
        _lamina(mb, P, mat)
        for kx in range(1, int((xb - xa) / 0.3)):
            x = xa + kx * 0.3
            if r.uniform() < 0.1:
                continue
            for sname in ("front", "back"):
                uu = -x if sname == "back" else x
                q = R.to_world(sname, uu, R.vlen - 0.11, n0 + 0.0015 + lift)
                _screw(mb, q, R.frame(sname)[3], r, tilt=r.uniform(0, 4))

    # ---- tapajuntas de remate (L) en los hastiales ----
    nf = SHEET_N + CORR_A + 0.012
    for sname in ("front", "back"):
        for sx in (-1, 1):
            uside = sx if sname == "front" else -sx
            prof = [(ue - 0.12, nf - 0.004), (ue - 0.115, nf), (ue + 0.006, nf), (ue + 0.012, nf - 0.01), (ue + 0.012, nf - 0.14)]
            nvs = max(2, int(math.ceil((R.vlen - v0) / 0.4)))
            P = []
            for kv in range(nvs + 1):
                v = v0 + (R.vlen - 0.21 - v0) * kv / nvs
                wob = r.uniform(-0.002, 0.002)
                P.append([R.to_world(sname, uside * uu, v, nn + wob) for uu, nn in prof])
            _lamina(mb, P, mat)
            for kv in range(1, nvs):
                v = v0 + (R.vlen - 0.21 - v0) * kv / nvs
                _screw(mb, R.to_world(sname, uside * (ue - 0.06), v, nf), R.frame(sname)[3], r, tilt=r.uniform(0, 4))
    return R.finalize(mb)


# =====================================================================================================================
# 4) TABLONES GRISES TRASLAPADOS EN HILADAS ESCALONADAS
# =====================================================================================================================
def _board_courses(vlen, v_start=-0.08):
    vs, v = [], v_start
    while v + BOARD_W <= vlen - 0.004:
        vs.append(v)
        v += BOARD_EXP
    top = vlen - 0.004 - BOARD_W
    if top - vs[-1] > 0.03:
        vs.append(top)
    return vs


def _board(mb, R, s, u0, u1, vb, nb, nt, r, mat="wood_grey", lift_end=0.0, dv=0.0, yaw=0.0, width=BOARD_W, voff=0.0,
           jag0=0.0, jag1=0.0):
    """Tablón inclinado en la vertiente s: borde bajo en (vb, nb), borde alto en (vb + BOARD_W, nt), de u0 a u1.
    Sección con vetas abiertas en la cara vista, canto bajo alabeado (se levanta, nunca baja: no toca la hilada inferior),
    punta levantada (lift_end) y testas astilladas (jag0/jag1)."""
    O, U, V, N = R.frame(s)
    D = (V * BOARD_W + N * (nt - nb)).normalized()
    Nb = U.cross(D).normalized()
    T, c = BOARD_T, 0.0035
    exp = min(BOARD_EXP, width)
    grooves = []
    for _ in range(int(r.integers(0, 3)) if width > 0.12 else 0):
        g = r.uniform(0.02, exp - 0.02)
        if all(abs(g - q[0]) > 0.025 for q in grooves):
            grooves.append((g, r.uniform(0.003, 0.006), r.uniform(0.0015, 0.0035)))
    top = sorted({round(x, 6) for x in [c, width - c, exp * 0.5, min(exp + 0.01, width - 0.01)] +
                  [g[0] + k for g in grooves for k in (-g[1], 0.0, g[1])]})

    def depth(w):
        for g in grooves:
            if abs(w - round(g[0], 6)) < 1e-6:
                return g[2]
        return 0.0
    # perfil (w a lo ancho desde el canto bajo, h en el espesor): cara inferior, canto alto, cara vista (con vetas), canto bajo
    prof = [(c, 0.0), (width - c, 0.0), (width, c), (width, T - c)] + [(w, T - depth(w)) for w in reversed(top)] + [(0.0, T - c),
                                                                                                                    (0.0, c)]
    nst = max(2, int(math.ceil((u1 - u0) / 0.45)) + 1)
    tw = r.uniform(0.0, 0.006)                    # alabeo del canto bajo
    tw_ph = r.uniform(0, PI)
    rings = []
    for i in range(nst):
        t = i / (nst - 1)
        u = u0 + (u1 - u0) * t
        lift = r.uniform(0.0, 0.0015) + lift_end * max(0.0, (t - 0.5) / 0.5) ** 2
        twist = tw * abs(math.sin(PI * t + tw_ph))
        vv = vb + dv + voff + yaw * (t - 0.5) * (u1 - u0)
        nn = nb + (nt - nb) * voff / BOARD_W
        B = O + U * u + V * vv + N * (nn + lift)
        rg = [B + D * w + Nb * (h + twist * max(0.0, 1.0 - w / (0.6 * BOARD_W))) for w, h in prof]
        j = jag0 if i == 0 else (jag1 if i == nst - 1 else 0.0)
        if j:
            sg = 1.0 if i == 0 else -1.0
            rg = [p + U * (sg * r.uniform(0.0, j)) for p in rg]
        rings.append(rg)
    _loft(mb, rings, mat)
    return D, Nb


def board_roof_stepped(w, d, pitch_deg, overhang, seed=0, rake=None, missing=0.03, nails=True):
    """Cubierta a dos aguas de tablones grises (0,22 x 0,022, exposición 0,16) traslapados en hiladas escalonadas, clavados
    directo a los cabios de roof_frame('gable', w, d, pitch_deg, overhang, cover='boards', tails=False).
    Alero escalonado: hilada de arranque doble que vuela por escalones y fascia doble escalonada; remates de hastial con las
    testas de las hiladas alternando vuelo corto/largo y canecillos bajo las largas. Cumbrera de dos tablas a caballete.
    Envejecido: tablones sueltos/corridos con una punta levantada, rajados, faltantes; juntas a tope desfasadas; clavos."""
    R = _Roof("gable", w, d, pitch_deg, overhang, rake)
    r = rng(seed + 5150)
    mb = MB()
    ue = R.hw + R.ovr + 0.006
    courses = _board_courses(R.vlen)
    nraf = max(2, int(round((R.w - RAFTER_W) / 0.6)) + 1)
    raf_u = [(-R.hw + RAFTER_W / 2) + (R.w - RAFTER_W) * i / (nraf - 1) for i in range(nraf)]
    if R.ovr > 0.12:
        raf_u += [-(R.hw + R.ovr - RAFTER_W / 2), R.hw + R.ovr - RAFTER_W / 2]
    for s in R.slopes:
        O, U, V, N = R.frame(s)
        # hilada de arranque (bajo la primera): vuela 3 cm menos -> escalón en el alero
        for (a, b) in ((-ue - 0.03, -ue / 3), (-ue / 3, ue / 2), (ue / 2, ue + 0.03)):
            _board(mb, R, s, a + 0.002, b - 0.002, courses[0] + 0.05, BOARD_N + 0.0, BOARD_N, r, width=BOARD_W - 0.05,
                   voff=0.0)
        prev = None
        params = []
        for k, vb in enumerate(courses):
            if k == 0:
                nb = nt = BOARD_N + BOARD_T + 0.002          # la 1.ª hilada apoya plana sobre la de arranque
            else:
                pv, pnb, pnt = prev
                f = min(max((vb - pv) / BOARD_W, 0.0), 1.0)
                nb, nt = pnb + (pnt - pnb) * f + BOARD_T + 0.002, BOARD_N
            prev = (vb, nb, nt)
            params.append(prev)
            ext0 = (0.10 if k % 2 == 0 else 0.035) + r.uniform(-0.015, 0.012)
            ext1 = (0.10 if k % 2 == 0 else 0.035) + r.uniform(-0.015, 0.012)
            ua, ub = -ue - ext0, ue + ext1
            rj0 = 0.03 if r.uniform() < 0.3 else 0.0         # testas del remate podridas / astilladas
            rj1 = 0.03 if r.uniform() < 0.3 else 0.0
            # juntas a tope desfasadas
            cuts = [ua]
            first = r.uniform(0.6, 2.4)
            while cuts[-1] + (first if len(cuts) == 1 else 3.6) < ub - 0.5:
                cuts.append(cuts[-1] + (first if len(cuts) == 1 else r.uniform(1.6, 3.6)))
            cuts.append(ub)
            for a, b in zip(cuts[:-1], cuts[1:]):
                a2, b2 = a + (0.002 if a > ua else 0.0), b - (0.002 if b < ub else 0.0)
                roll = r.uniform()
                if 0 < k < len(courses) - 1 and roll < missing:
                    continue
                if 0 < k < len(courses) - 2 and roll < missing + 0.035:
                    # suelto y corrido: baja 4–8 cm, punta levantada, girado
                    dv = -r.uniform(0.065, 0.09)
                    pv, pnb, pnt = params[k - 1]
                    f = min(max((vb + dv - pv) / BOARD_W, 0.0), 1.0)
                    nbs = pnb + (pnt - pnb) * f + BOARD_T + 0.003
                    _board(mb, R, s, a2, b2, vb, nbs, nt, r, lift_end=r.uniform(0.015, 0.04), dv=dv, yaw=r.uniform(-0.006, 0.006))
                    continue
                if roll < missing + 0.07:
                    # rajado a lo largo de la veta: dos tiras separadas
                    sp_ = r.uniform(0.07, 0.15)
                    _board(mb, R, s, a2, b2, vb, nb, nt, r, width=sp_ - 0.003, voff=0.0)
                    _board(mb, R, s, a2 + r.uniform(0, 0.01), b2, vb, nb, nt, r, width=BOARD_W - sp_ - 0.004, voff=sp_ + 0.004)
                else:
                    _board(mb, R, s, a2, b2, vb, nb, nt, r, dv=r.uniform(-0.012, 0.008), yaw=r.uniform(-0.002, 0.002),
                           jag0=rj0 if a == ua else 0.0, jag1=rj1 if b == ub else 0.0)
                # clavos en la parte vista sobre cada cabio
                if nails:
                    Dd = (V * BOARD_W + N * (nt - nb)).normalized()
                    Nb = U.cross(Dd).normalized()
                    for ru in raf_u:
                        uu = ru if s == "front" else -ru
                        if not (a2 + 0.05 < uu < b2 - 0.05) or r.uniform() < 0.15:
                            continue
                        f = 0.045 / BOARD_W
                        p = O + U * (uu + r.uniform(-0.01, 0.01)) + V * (vb + 0.045) + N * (nb + (nt - nb) * f) + Nb * BOARD_T
                        _nail(mb, p, Nb, r=0.0045, h=0.003)
            # canecillo bajo las testas largas del remate
            if k % 2 == 0 and 0 < k < len(courses) - 1:
                for sx in (-1, 1):
                    uu = sx * (R.hw + R.ovr + 0.03)
                    u_lo, u_hi = (uu, uu + sx * 0.06) if sx > 0 else (uu + sx * 0.06, uu)
                    nbot = nb + (nt - nb) * 0.35 - 0.002
                    m = R.matrix(s)
                    mb.box((u_lo, vb + 0.03, nbot - 0.10), (u_hi, vb + 0.11, nbot), "wood_grey", bevel=0.006, seg=1, m=m)
        # fascia escalonada (segunda tabla por delante de la fascia de roof_frame)
        ze = R.zt0 - R.ov * R.tp
        sg = -1 if s == "front" else 1
        y0 = sg * (R.hd + R.ov + 0.038)
        xe = R.hw + R.ovr + 0.05
        _beam(mb, [(-xe, y0, 0), (0, y0 + r.uniform(-0.002, 0.002), 0), (xe, y0, 0)], Vector((0, 0, 1)), 0.022,
              ze - 0.105, ze - 0.008, "wood_grey", c=0.004)
    # ---- cumbrera: dos tablas a caballete ----
    vlen = R.vlen

    def surf(v):  # cara superior más alta de las hiladas que cubren v
        h = 0.0
        for (pv, pnb, pnt) in params:
            f = (v - pv) / BOARD_W
            if 0.0 <= f <= 1.0:
                h = max(h, pnb + (pnt - pnb) * f + BOARD_T)
        return h

    nb0 = max(surf(vlen - 0.17 + 0.01 * i) for i in range(18)) + 0.003
    for s, vend in (("front", vlen + 0.032), ("back", None)):
        O, U, V, N = R.frame(s)
        if vend is None:
            Of, Uf, Vf, Nf = R.frame("front")
            A = Of + Vf * vlen + Nf * (nb0 - 0.0015)
            vend = vlen
            while (O + V * vend + N * (nb0 + 0.026) - A).dot(Nf) > -0.001 and vend > vlen - 0.08:
                vend -= 0.001
        va = vlen - 0.17
        nx = max(2, int(math.ceil(2 * ue / 0.6)) + 1)
        pts = [O + U * (-ue - 0.03 + (2 * ue + 0.06) * i / (nx - 1)) + V * ((va + vend) / 2) + N * (nb0 + r.uniform(0, 0.002))
               for i in range(nx)]
        _beam(mb, pts, N, vend - va, 0.0, 0.025, "wood_grey", c=0.004)
    return R.finalize(mb)
