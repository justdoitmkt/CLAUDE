"""openings.py — GRUPO G1 · VANOS del kit modular BLACKISLE (ventanas, puertas, cortina enrollable, celosía, reja).

Todas las funciones públicas devuelven un `MB` en coordenadas LOCALES DEL VANO:
  u = 0..w en X, v = 0..h en Z (v = 0 es el fondo del vano: repisa del muro en ventanas, piso terminado en puertas),
  el muro va de y = 0 (cara exterior, fachada hacia -Y) a y = depth (cara interior).
El constructor coloca la pieza con `MB.join(pieza, Matrix.Translation((u_vano, y_muro, z_vano)) @ rot)`.

Qué sale del prisma del vano (todo con lógica constructiva):
  · alféizar de concreto: nariz 4,5 cm hacia -Y y orejas de 6 cm a cada lado, bajo v = 0;
  · postigos, tablas clavadas, rejas montadas y caja de persiana: sobre la fachada (y < 0);
  · barra y cortina: cara interior (y > depth); hojas de puerta abiertas: giran hacia +Y (abren hacia adentro).
Ninguna pieza toca coplanarmente la cara del muro: se separan >= 1 mm o se empotran >= 1 mm.

Láminas intencionales (aristas abiertas, usar `side: DoubleSide` en Three.js):
  · 'fabric' — la tela de cortinas (planos ondulados de una cara). Es la ÚNICA lámina del grupo.
El vidrio ('glass') va en esquirlas (cuñas) de ~4 mm de espesor: prismas cerrados, nunca un vidrio entero.
Todo lo demás son sólidos cerrados (0 aristas no-manifold; verificado en barridos de tamaño/profundidad/semilla/ángulo).

Montaje y profundidades (y):
  ventana corrediza: marco de aluminio y 0,04–0,12 con 2 rieles; hojas en y 0,041–0,063 y 0,067–0,089.
  ventana abatible/postigo/tapiada: marco de madera y 0,04–0,128 con galce; hojas abren hacia AFUERA (-Y).
  postigos: bisagras de pernio en la fachada (u = -0,025 y w + 0,025), tablas tapiadas sobre la fachada (y < -0,004).
  puertas flush/metal/double_glazed abren hacia ADENTRO (+Y, open_angle <= 95°); plank abre hacia AFUERA (<= 92°).
  El ángulo se reduce solo si el herraje de la hoja tocaría la jamba o el muro (_swing_clear).
  door(..., parts=True) devuelve el marco y cada hoja por separado (posición cerrada + pivote + eje + ángulo) para animar.
  cortina enrollable, celosía y reja quedan dentro del vano (reja en y 0,006–0,036, compatible con ventana + alféizar).
  Hojas y herrajes montados sobre un marco descuadrado reciben el mismo descuadre (sin choques hoja–marco).

Vidrio roto: punto de impacto + grietas radiales + grieta concéntrica dentada (cuñas pegadas al junquillo, con la punta
hacia el impacto); nunca un vidrio entero. Cortinas: la tela se apoya contra la cara interior del muro, nunca la cruza.

Triángulos medidos (barrido de 864 combinaciones por tipo: 1,2–1,8 x 1,0–1,6 m, 12 semillas, con/sin cortina):
  window: sliding 1,4–3,7 k · casement 1,6–4,5 k · shutter 2,5–4,9 k · boarded 2,4–4,7 k (presupuesto 800–5000 cumplido)
  door: flush ~3,5 k · double_glazed 2,2–2,7 k · plank 2,3–2,6 k · metal ~3,6 k
  rolling_shutter 2,6 x 2,6: 6–10 k (según open_frac) · security_grille 1,2 x 1,2: ~1,9 k
  breeze_block_screen: ~230 tris por bloque 4sq con bisel (2,0 x 2,4 m ≈ 23 k); bevel=0 para lejanía.
"""
import math

import bpy  # noqa: F401  (bmesh/mathutils solo existen después de importar bpy)
import bmesh  # noqa: F401
from mathutils import Matrix, Vector

from kit.common import MB, rng

PI = math.pi
LAMINA_MATS = ("fabric",)


# =====================================================================================================================
# utilidades de transformación
# =====================================================================================================================
def _T(x=0.0, y=0.0, z=0.0):
    return Matrix.Translation((x, y, z))


def _R(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, axis)


def _about(p, M):
    """M aplicada alrededor del punto p."""
    return _T(p[0], p[1], p[2]) @ M @ _T(-p[0], -p[1], -p[2])


def _merge(dst, src, m=None):
    """Une src en dst con la matriz m y libera src."""
    dst.join(src, m)
    src.bm.free()
    return dst


def _bounds(mb):
    cs = [v.co for v in mb.bm.verts]
    mn = Vector((min(c.x for c in cs), min(c.y for c in cs), min(c.z for c in cs)))
    mx = Vector((max(c.x for c in cs), max(c.y for c in cs), max(c.z for c in cs)))
    return mn, mx


def _xform(mb, m):
    for v in mb.bm.verts:
        v.co = m @ v.co


def _uni(r, a, b):
    """r.uniform tolerante a rangos invertidos o vacíos (vanos muy chicos)."""
    return r.uniform(a, b) if b > a else 0.5 * (a + b)


def _declump(mb, dist=0.0003, push=0.0007):
    """Separa vértices de piezas distintas que quedaron a menos de `dist` (evita que el merge de finish() las suelde
    y cree aristas no-manifold)."""
    from mathutils import kdtree
    vs = list(mb.bm.verts)
    kd = kdtree.KDTree(len(vs))
    for i, v in enumerate(vs):
        kd.insert(v.co, i)
    kd.balance()
    moved = set()
    for i, v in enumerate(vs):
        if i in moved:
            continue
        for (_, j, d) in kd.find_range(v.co, dist):
            if j != i and j not in moved:
                vs[j].co.y += push
                moved.add(j)
    return len(moved)


def _smooth(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


# =====================================================================================================================
# ruido y abolladuras deterministas
# =====================================================================================================================
class _Noise:
    """Ruido suave 2D (suma de ondas planas con fase aleatoria). Rango aproximado [-1, 1]. `wl` = longitud de onda base (m)."""

    def __init__(self, r, wl=1.0, octaves=3, waves=3):
        self.c = []
        for o in range(octaves):
            k = 2 * PI / wl * (2.1 ** o)
            for _ in range(waves):
                a = r.uniform(0, 2 * PI)
                self.c.append((k * math.cos(a), k * math.sin(a), r.uniform(0, 2 * PI), 0.5 ** o))
        self.n = sum(c[3] for c in self.c) / 1.7

    def __call__(self, x, y):
        return sum(a * math.sin(kx * x + ky * y + ph) for kx, ky, ph, a in self.c) / self.n


def _dents(r, n, x0, x1, z0, z1, rad=(0.04, 0.15), depth=(0.004, 0.02)):
    """Campo de abolladuras gaussianas: f(x, z) -> profundidad (>= 0)."""
    ds = [(_uni(r, x0, x1), _uni(r, z0, z1), _uni(r, *rad), _uni(r, *depth)) for _ in range(n)]

    def f(x, z):
        return sum(d * math.exp(-((x - cx) ** 2 + (z - cz) ** 2) / (rr * rr)) for cx, cz, rr, d in ds)
    return f


# =====================================================================================================================
# primitivas propias (sobre MB; no tocan common.py)
# =====================================================================================================================
def _loft(mb, rings, mat, caps=True, closed=True, m=None):
    """Barrido general: une anillos de puntos 3D consecutivos con cuadriláteros; tapa los extremos (sólido cerrado)."""
    vr = [mb._verts(ring, m) for ring in rings]
    k = len(rings[0])
    kr = k if closed else k - 1
    for i in range(len(vr) - 1):
        a, b = vr[i], vr[i + 1]
        for j in range(kr):
            jj = (j + 1) % k
            mb.face([a[j], a[jj], b[jj], b[j]], mat)
    if closed and caps:
        mb.face(list(reversed(vr[0])), mat)
        mb.face(vr[-1], mat)
    return vr


def _cprof(a, b, c):
    """Rectángulo a x b centrado en el origen con chaflán c en las 4 esquinas (8 puntos CCW)."""
    a2, b2 = a / 2, b / 2
    c = min(c, 0.4 * min(a, b))
    return [(-a2 + c, -b2), (a2 - c, -b2), (a2, -b2 + c), (a2, b2 - c), (a2 - c, b2), (-a2 + c, b2), (-a2, b2 - c), (-a2, -b2 + c)]


def _rprof(x0, x1, y0, y1, c):
    """Rectángulo [x0,x1]x[y0,y1] con chaflán c (perfil de barrido)."""
    return [(x + (x0 + x1) / 2, y + (y0 + y1) / 2) for x, y in _cprof(x1 - x0, y1 - y0, c)]


def _side_ts(L, step, c, start=True, end=True):
    """Parámetros t a lo largo de un lado: puntos a distancia c de cada esquina (inglete simétrico en MB.sweep, que usa
    P[i+1]-P[i-1] como tangente) e intermedios cada `step` si step > 0."""
    if L <= 2.5 * c:
        return []
    n = max(1, int(round((L - 2 * c) / step))) if step > 0 else 1
    ts = [c / L + (1 - 2 * c / L) * k / n for k in range(1, n)]
    return ([c / L] if start else []) + ts + ([1 - c / L] if end else [])


def _rect_path(u0, v0, u1, v1, step=0.0, c=0.03):
    """Recorrido cerrado CCW (visto desde -Y) en el plano XZ (y = 0). Con el `normal` (0,1,0) de MB.sweep el perfil
    x > 0 apunta HACIA DENTRO del rectángulo y el perfil y es la profundidad absoluta en Y.
    Siempre lleva puntos a distancia c de cada esquina (inglete correcto aunque w != h); step > 0 añade intermedios."""
    cs = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    pts = []
    for i in range(4):
        a, b = cs[i], cs[(i + 1) % 4]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        pts.append((a[0], 0.0, a[1]))
        pts += [(a[0] + (b[0] - a[0]) * t, 0.0, a[1] + (b[1] - a[1]) * t) for t in _side_ts(L, step, c)]
    return pts


def _door_path(u0, u1, z0, z1, step=0.0, c=0.03, z_end=None):
    """Recorrido abierto de 3 lados (jamba der. hacia arriba, cabezal, jamba izq. hacia abajo): perfil x > 0 hacia dentro.
    z_end: cota donde termina la jamba izquierda (por defecto z0)."""
    cs = [(u1, z0), (u1, z1), (u0, z1), (u0, z0 if z_end is None else z_end)]
    pts = []
    for i in range(3):
        a, b = cs[i], cs[i + 1]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        pts.append((a[0], 0.0, a[1]))
        pts += [(a[0] + (b[0] - a[0]) * t, 0.0, a[1] + (b[1] - a[1]) * t) for t in _side_ts(L, step, c, start=i > 0, end=i < 2)]
    pts.append((cs[3][0], 0.0, cs[3][1]))
    return pts


def _plank(L, W, Tk, r, mat="wood_grey", step=0.15, bow=0.004, twist=1.2, cut=(0.0, 0.0), yfn=None, ch=0.003,
           rough=0.0006):
    """Tabla a lo largo de +X (0..L), ancho W en Z y grueso Tk en Y (ambos centrados). Alabeo, torsión, cortes en bisel
    (cut = desfase en X del canto superior respecto al inferior en cada extremo) y aristas achaflanadas."""
    mb = MB()
    n = max(2, int(math.ceil(L / step)))
    prof = [(x, y) for x, y in _rrect(W, Tk, ch * 1.4, 2)]   # aristas gastadas (radio ~4 mm), no un octágono
    tw = math.radians(r.uniform(-twist, twist))
    bw = r.uniform(-bow, bow)
    bz = r.uniform(-bow, bow) * 0.5
    rings = []
    for i in range(n + 1):
        s = i / n
        x = s * L
        a = tw * (s - 0.5)
        ca, sa = math.cos(a), math.sin(a)
        oy = bw * math.sin(PI * s) + (yfn(s) if yfn else 0.0)
        oz = bz * math.sin(PI * s)
        ring = []
        for pz, py in prof:
            xx = x
            if i == 0:
                xx += cut[0] * (pz / W + 0.5)
            elif i == n:
                xx += cut[1] * (pz / W + 0.5)
            else:
                xx += r.normal(0, rough)
            ring.append((xx, oy + pz * sa + py * ca + r.normal(0, rough), oz + pz * ca - py * sa + r.normal(0, rough)))
        rings.append(ring)
    _loft(mb, rings, mat)
    return mb


def _slab(W, H, Tk, nx=1, nz=1, c=0.003, mat="wood"):
    """Panel/hoja x 0..W, y 0..Tk (y = 0 cara exterior), z 0..H con chaflán c en TODAS las aristas.
    Malla densa en las caras (nx columnas, nz filas) para abollar. Devuelve (mb, anillos, nx); los índices 0..nx de cada
    anillo son la cara y = 0 y los índices nx+3..2nx+3 la cara y = Tk (x invertida)."""
    mb = MB()
    xs = [W * i / nx for i in range(nx + 1)]
    xs[0], xs[-1] = c, W - c
    sec = [(x, 0.0) for x in xs] + [(W, c), (W, Tk - c)] + [(x, Tk) for x in reversed(xs)] + [(0.0, Tk - c), (0.0, c)]
    zs = [0.0, c] + [c + (H - 2 * c) * k / nz for k in range(1, nz)] + [H - c, H]
    cx, cy = W / 2, Tk / 2
    fx, fy = 1 - 2 * c / W, 1 - 2 * c / Tk
    rings = []
    for k, z in enumerate(zs):
        if k in (0, len(zs) - 1):
            rings.append([(cx + (x - cx) * fx, cy + (y - cy) * fy, z) for x, y in sec])
        else:
            rings.append([(x, y, z) for x, y in sec])
    vr = _loft(mb, rings, mat)
    return mb, vr, nx


def _prism(mb, pts, t, mat, m=None):
    """Prisma cerrado a partir de un polígono 3D casi plano `pts` (en XZ) extruido +-t/2 en Y. Para esquirlas y placas."""
    a = mb._verts([(p[0], p[1] - t / 2, p[2]) for p in pts], m)
    b = mb._verts([(p[0], p[1] + t / 2, p[2]) for p in pts], m)
    k = len(pts)
    mb.face(list(reversed(a)), mat)
    mb.face(b, mat)
    for i in range(k):
        j = (i + 1) % k
        mb.face([a[i], a[j], b[j], b[i]], mat)


def _frame_on(p0, p1, up=(0.0, 0.0, 1.0)):
    """Matriz con Z local de p0 a p1 (X local = `up` proyectado). Devuelve (M, largo)."""
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L = d.length
    z = d / L if L > 1e-12 else Vector((0.0, 0.0, 1.0))
    u = Vector(up)
    if abs(u.dot(z)) > 0.95:
        u = Vector((1.0, 0.0, 0.0)) if abs(z.x) < 0.9 else Vector((0.0, 1.0, 0.0))
    x = (u - z * u.dot(z)).normalized()
    y = z.cross(x)
    return Matrix(((x.x, y.x, z.x, p0.x), (x.y, y.y, z.y, p0.y), (x.z, y.z, z.z, p0.z), (0.0, 0.0, 0.0, 1.0))), L


def _lathe(mb, prof, seg=24, mat="metal_rust", M=None, phase=0.0, caps=True):
    """Sólido de revolución alrededor del Z local: prof [(r, z)] de un extremo al otro; r = 0 en un extremo = polo (abanico
    de triángulos, sin caras degeneradas). Los extremos con r > 0 se tapan (caps) para cerrar el sólido."""
    rings = []
    for (rr, z) in prof:
        if rr < 1e-7:
            rings.append(mb._verts([(0.0, 0.0, z)], M))
        else:
            rings.append(mb._verts([(rr * math.cos(phase + 2 * PI * k / seg), rr * math.sin(phase + 2 * PI * k / seg), z)
                                    for k in range(seg)], M))
    for a, b in zip(rings[:-1], rings[1:]):
        if len(a) == 1 and len(b) == 1:
            continue
        for k in range(seg):
            kk = (k + 1) % seg
            if len(a) == 1:
                mb.face([a[0], b[kk], b[k]], mat)
            elif len(b) == 1:
                mb.face([a[k], a[kk], b[0]], mat)
            else:
                mb.face([a[k], a[kk], b[kk], b[k]], mat)
    if caps:
        if len(rings[0]) > 1:
            mb.face(list(reversed(rings[0])), mat)
        if len(rings[-1]) > 1:
            mb.face(rings[-1], mat)
    return rings


def _arc(cx, cy, r, a0, a1, n):
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / n), cy + r * math.sin(a0 + (a1 - a0) * k / n)) for k in range(n + 1)]


def _rrect(w, h, r, n=3, cx=0.0, cy=0.0):
    """Rectángulo w x h centrado en (cx, cy) con esquinas de radio r (CCW, 4(n+1) puntos)."""
    r = max(1e-5, min(r, 0.49 * min(w, h)))
    pts = []
    for (ox, oy, a0) in ((w / 2 - r, h / 2 - r, 0.0), (-w / 2 + r, h / 2 - r, PI / 2), (-w / 2 + r, -h / 2 + r, PI),
                         (w / 2 - r, -h / 2 + r, 1.5 * PI)):
        pts += _arc(cx + ox, cy + oy, r, a0, a0 + PI / 2, n)
    return pts


def _fillet2d(pts, rad, n=3, closed=True):
    """Polígono/polilínea 2D con cada esquina redondeada: rad = radio único o lista por vértice (0 = esquina viva).
    El radio se acota a 0,45 de los tramos vecinos (perfiles de 2–3 mm de pared sin auto-cruces)."""
    P = [Vector(p) for p in pts]
    k = len(P)
    rr = rad if isinstance(rad, (list, tuple)) else [rad] * k
    out = []
    for i in range(k):
        if (not closed and i in (0, k - 1)) or rr[i] <= 0:
            out.append((P[i].x, P[i].y))
            continue
        a, b, c = P[i - 1], P[i], P[(i + 1) % k]
        d0, d1 = (a - b), (c - b)
        l0, l1 = d0.length, d1.length
        if l0 < 1e-9 or l1 < 1e-9:
            out.append((b.x, b.y))
            continue
        d0, d1 = d0 / l0, d1 / l1
        ang = math.acos(max(-1.0, min(1.0, d0.dot(d1))))
        if ang > PI - 0.05:
            out.append((b.x, b.y))
            continue
        t = min(rr[i] / math.tan(ang / 2), 0.45 * l0, 0.45 * l1)
        p0, p1 = b + d0 * t, b + d1 * t
        for j in range(n + 1):
            u = j / n
            q = p0.lerp(b, u).lerp(b.lerp(p1, u), u)
            out.append((q.x, q.y))
    return out


def _rrprof(x0, x1, y0, y1, r, n=2):
    """Perfil de barrido [x0,x1]x[y0,y1] con esquinas redondeadas de radio r (canto de perfil extruido real)."""
    return _rrect(x1 - x0, y1 - y0, r, n, (x0 + x1) / 2, (y0 + y1) / 2)


def _sweep3(mb, prof, pts, mat, up=(0.0, 0.0, 1.0), scale=None, caps=True):
    """Barre `prof` [(px, py)] por una polilínea 3D cualquiera: py va en `up` proyectado (N), px en T x N.
    scale(s) -> factor del perfil (s = 0..1 por longitud): remates redondeados de manijas y jaladeras."""
    P = [Vector(p) for p in pts]
    n = len(P)
    acc = [0.0]
    for i in range(1, n):
        acc.append(acc[-1] + (P[i] - P[i - 1]).length)
    tot = acc[-1] or 1.0
    U = Vector(up)
    rings = []
    for i in range(n):
        T = (P[min(i + 1, n - 1)] - P[max(i - 1, 0)]).normalized()
        N = U - T * U.dot(T)
        N = N.normalized() if N.length > 1e-6 else Vector((1.0, 0.0, 0.0))
        B = T.cross(N)
        k = scale(acc[i] / tot) if scale else 1.0
        rings.append([mb.bm.verts.new(P[i] + B * (px * k) + N * (py * k)) for px, py in prof])
    m = len(prof)
    for i in range(n - 1):
        for j in range(m):
            jj = (j + 1) % m
            mb.face([rings[i][j], rings[i][jj], rings[i + 1][jj], rings[i + 1][j]], mat)
    if caps:
        mb.face(list(reversed(rings[0])), mat)
        mb.face(rings[-1], mat)
    return rings


def _rtube(mb, pts, rad, mat, seg=16, rbend=None, nb=6, caps=True, soft=False):
    """Tubo/varilla redonda por una polilínea con dobleces de radio real (rbend, por defecto 2,5 diámetros)."""
    P = [Vector(p) for p in pts]
    rb = rbend if rbend is not None else 5.0 * rad
    if len(P) > 2 and rb > 0:
        Q = [P[0]]
        for i in range(1, len(P) - 1):
            a, b, c = P[i - 1], P[i], P[i + 1]
            d0, d1 = (a - b).normalized(), (c - b).normalized()
            ang = d0.angle(d1) if d0.length and d1.length else PI
            if ang > PI - 0.02:
                Q.append(b)
                continue
            t = min(rb / math.tan(ang / 2), (a - b).length * 0.49, (c - b).length * 0.49)
            p0, p1 = b + d0 * t, b + d1 * t
            for k in range(nb + 1):
                u = k / nb
                Q.append(p0.lerp(b, u).lerp(b.lerp(p1, u), u))
        Q.append(P[-1])
        P = Q
    if soft:
        with mb.soft():
            mb.tube([tuple(p) for p in P], rad, seg=seg, mat=mat, caps=caps)
    else:
        mb.tube([tuple(p) for p in P], rad, seg=seg, mat=mat, caps=caps)


def _screw(mb, p, axis, d=0.0065, mat="metal_rust", kind="pan", m=None, up=(0.0, 0.0, 1.0)):
    """Cabeza de tornillo/clavo sobre una superficie (p en la superficie, `axis` hacia fuera), 16 lados con sombreado continuo:
    'pan' (gota con cruz hundida), 'flat' (avellanado al ras con cruz), 'dome' (perno de coche / remache)."""
    a = Vector(axis).normalized()
    p = Vector(p)
    M, _ = _frame_on(p, p + a, up)
    if m is not None:
        M = m @ M
    h = d * (0.36 if kind == "pan" else (0.55 if kind == "dome" else 0.12))
    if kind == "pan":
        prof = [(0.0, -0.0006), (d / 2, -0.0006), (d / 2, h * 0.3), (d * 0.43, h * 0.78), (d * 0.26, h), (d * 0.13, h * 0.96),
                (0.0, h * 0.62)]
    elif kind == "dome":
        prof = [(0.0, -0.0006), (d / 2, -0.0006), (d / 2, h * 0.12), (d * 0.46, h * 0.45), (d * 0.36, h * 0.75), (d * 0.2, h * 0.95),
                (0.0, h)]
    else:
        prof = [(0.0, -0.0008), (d / 2, -0.0008), (d / 2, h), (d * 0.2, h), (0.0, h * 0.2 - 0.0002)]
    with mb.soft():
        _lathe(mb, prof, seg=16, mat=mat, M=M)


def _nail(mb, x, y, z, r, d=-1, mat="metal_rust", head=0.0045, m=None):
    """Cabeza de clavo sobre una cara que mira a d*Y (empotrada 0,8 mm, cúpula de 1,6 mm), ligeramente ladeada; a veces
    el clavo quedó medio sacado y doblado (cabeza levantada con caña visible)."""
    tilt = Vector((r.normal(0, 0.08), 0, r.normal(0, 0.08)))
    ax = (Vector((0, d, 0)) + tilt).normalized()
    p = Vector((x, y, z))
    pulled = r.random() < 0.12
    lift = r.uniform(0.004, 0.012) if pulled else 0.0
    M, _ = _frame_on(p - ax * 0.0008, p + ax, (0, 0, 1))
    if m is not None:
        M = m @ M
    hd = 2 * head * r.uniform(0.85, 1.1)
    with mb.soft():
        if pulled:   # caña de 2,8 mm visible
            _lathe(mb, [(0.0014, 0.0), (0.0014, lift + 0.0004)], seg=10, mat=mat, M=M)
        _lathe(mb, [(0.0, lift), (hd / 2, lift), (hd / 2, lift + 0.0007), (hd * 0.36, lift + 0.0015), (0.0, lift + 0.0018)],
               seg=14, mat=mat, M=M)


def _bolt(mb, p, axis, r=0.007, ln=0.006, mat="metal_rust", seg=6, m=None):
    """Perno de cabeza hexagonal con chaflán y arandela: p en la superficie, `axis` hacia fuera. r = medio entrecaras."""
    a = Vector(axis).normalized()
    p = Vector(p)
    M, _ = _frame_on(p - a * 0.0008, p + a, (0, 0, 1) if abs(a.z) < 0.9 else (1, 0, 0))
    if m is not None:
        M = m @ M
    ce = r / math.cos(PI / 6)
    tw = min(0.0016, 0.25 * ln)
    with mb.soft():
        _lathe(mb, [(0.0, 0.0), (r * 1.45, 0.0), (r * 1.45, tw * 0.7), (r * 1.38, tw), (0.0, tw)], seg=20, mat=mat, M=M)
    hh = max(0.002, ln - tw)
    _lathe(mb, [(0.0, tw - 0.0003), (ce, tw - 0.0003), (ce, tw + hh * 0.78), (r * 0.92, tw + hh), (0.0, tw + hh)], seg=6, mat=mat,
           M=M, phase=PI / 6)


def _rack(mb, w, h, r, deg=0.25, sag=0.004):
    """Desplome/descuadre de un marco: giro leve en su plano alrededor del centro + flecha del cabezal."""
    a = math.radians(r.uniform(-deg, deg))
    s = r.uniform(0.3, 1.0) * sag
    ca, sa = math.cos(a), math.sin(a)
    cx, cz = w / 2, h / 2
    for v in mb.bm.verts:
        x, z = v.co.x - cx, v.co.z - cz
        x, z = x * ca - z * sa, x * sa + z * ca
        t = min(max((v.co.x) / max(w, 1e-6), 0.0), 1.0)
        dz = -s * math.sin(PI * t) * _smooth((v.co.z - h * 0.55) / (h * 0.45))
        v.co.x, v.co.z = x + cx, z + cz + dz
    return _about((cx, 0.0, cz), _R("Y", -math.degrees(a)))   # el mismo giro, para montar hojas sobre el marco descuadrado


# =====================================================================================================================
# vidrio roto (esquirlas) — prismas cerrados de 4 mm
# =====================================================================================================================
def _glass(mb, u0, v0, u1, v1, y, r, broken=0.7, t=0.004, embed=0.006, m=None):
    """Vidrio roto con lógica de fractura en un claro de vidriado (u0..u1, v0..v1) a profundidad y.
    Un punto de impacto (descentrado, más bien bajo) con 8–15 grietas radiales irregulares y una grieta concéntrica
    dentada: quedan CUÑAS pegadas al junquillo por su canto exterior (metido `embed`), con la punta hacia el impacto;
    algunas cuñas se cayeron completas. Cada esquirla es un prisma cerrado de ~4 mm separado de sus vecinas por grietas
    de 1,5–4 mm medidas en perpendicular a la grieta (en proyección nunca se solapan, aunque se ladeen).
    broken 0..1 = fracción perdida (0,1 -> agujero chico alrededor del impacto y grietas; 0,95 -> solo dientes)."""
    W, H = u1 - u0, v1 - v0
    if W < 0.04 or H < 0.04:
        return 0
    b = min(max(broken, 0.0), 0.97)
    iu = u0 + W * r.uniform(0.22, 0.78)
    iv = v0 + H * r.uniform(0.18, 0.7)
    E = embed

    def reach(a, e, ou=0.0, ov=0.0):
        """Distancia desde (impacto + (ou, ov)) al borde del claro (agrandado e) en la dirección a."""
        c, s = math.cos(a), math.sin(a)
        ts = []
        if c > 1e-9:
            ts.append((u1 + e - iu - ou) / c)
        elif c < -1e-9:
            ts.append((u0 - e - iu - ou) / c)
        if s > 1e-9:
            ts.append((v1 + e - iv - ov) / s)
        elif s < -1e-9:
            ts.append((v0 - e - iv - ov) / s)
        return min(ts)

    big = max(W, H)   # nº de grietas radiales según el tamaño del claro (claros chicos de ventana con junquillos: 5–8)
    k = int(r.integers(5, 9)) if big < 0.45 else int(r.integers(8, 12)) + (2 if big > 0.8 else 0)
    ph = r.uniform(0, 2 * PI)
    angs = sorted(ph + 2 * PI * (i + r.uniform(-0.32, 0.32)) / k for i in range(k))
    corners = [(math.atan2(cv - iv, cu - iu), (cu, cv)) for cu, cv in ((u1 + E, v1 + E), (u0 - E, v1 + E), (u0 - E, v0 - E),
                                                                         (u1 + E, v0 - E))]
    miss = 0.1 + 0.3 * b
    n = 0
    for i in range(k):
        a0 = angs[i]
        a1 = angs[(i + 1) % k] + (2 * PI if i == k - 1 else 0.0)
        span = a1 - a0
        if r.random() < miss or span < 0.12:
            continue
        gap = r.uniform(0.0015, 0.004)
        kw = min(0.97, (1.0 - b) * r.uniform(0.35, 1.6) + 0.04)
        rin_min = max(0.045, gap / (0.1 * span))
        nm = 1 + int(r.integers(0, 2 if big < 0.45 else 3))
        ia = [a0] + sorted(r.uniform(a0 + 0.12 * span, a1 - 0.12 * span, nm).tolist()) + [a1]
        inner, vis = [], 0.0
        for j, a in enumerate(ia):
            Rt = reach(a, 0.0)
            kk = kw * (r.uniform(0.5, 1.4) if 0 < j < len(ia) - 1 else r.uniform(0.7, 1.15))
            L = min(max(kk * Rt, 0.004), Rt - rin_min)   # largo visible desde el borde del claro
            if L < 0.004:
                L = 0.004
            rin = min(Rt - L, reach(a, E) - 0.006)
            vis = max(vis, Rt - rin)
            inner.append((a, rin))
        if vis < 0.012:   # la cuña quedaría escondida en el junquillo: se cayó
            continue
        # cada canto de grieta es la recta de la grieta corrida gap/2 hacia dentro de la cuña; corta al borde agrandado
        n0 = (-math.sin(a0) * gap / 2, math.cos(a0) * gap / 2)
        n1 = (math.sin(a1) * gap / 2, -math.cos(a1) * gap / 2)
        Re0, Re1 = reach(a0, E, *n0), reach(a1, E, *n1)
        B0 = (iu + n0[0] + Re0 * math.cos(a0), iv + n0[1] + Re0 * math.sin(a0))
        B1 = (iu + n1[0] + Re1 * math.cos(a1), iv + n1[1] + Re1 * math.sin(a1))
        g0, g1 = math.atan2(B0[1] - iv, B0[0] - iu), math.atan2(B1[1] - iv, B1[0] - iu)
        g1 = g0 + (g1 - g0) % (2 * PI)
        cs = sorted((g0 + (ca - g0) % (2 * PI), cp) for ca, cp in corners)   # esquinas del claro dentro de la cuña
        cin = [cp for ca, cp in cs if g0 + 1e-6 < ca < g1 - 1e-6]
        pts2 = [B0] + cin + [B1]
        for j in range(len(inner) - 1, -1, -1):
            a, rin = inner[j]
            off = n1 if j == len(inner) - 1 else (n0 if j == 0 else (0.0, 0.0))
            pts2.append((iu + rin * math.cos(a) + off[0], iv + rin * math.sin(a) + off[1]))
        # ladeo rígido alrededor de la cuerda del canto exterior (la esquirla se vence hacia un lado); acotado a 5 mm
        pa, pb = pts2[0], pts2[len(cin) + 1]
        cu_, cv_ = pb[0] - pa[0], pb[1] - pa[1]
        cl = math.hypot(cu_, cv_) or 1.0
        nu, nv = -cv_ / cl, cu_ / cl
        if (iu - pa[0]) * nu + (iv - pa[1]) * nv < 0:
            nu, nv = -nu, -nv
        dmax = max(1e-6, max((p[0] - pa[0]) * nu + (p[1] - pa[1]) * nv for p in pts2))
        tl = r.uniform(-1, 1) * (0.0012 if cin else min(0.005, dmax * math.sin(math.radians(3.0))))
        pts = [(p[0], y + tl * ((p[0] - pa[0]) * nu + (p[1] - pa[1]) * nv) / dmax, p[1]) for p in pts2]
        _prism(mb, pts, t * r.uniform(0.8, 1.1), "glass", m)
        n += 1
    return n


def _loose_glass(mb, x0, x1, y0, y1, z, count, r, m=None):
    """Esquirlas caídas sobre una superficie horizontal a cota z (prismas de 3 mm apoyados, ligeramente ladeados).
    Nunca se enciman: cada una busca un lugar libre (si no lo halla, se omite) -> sin caras coplanares entre esquirlas."""
    placed = []
    for _ in range(count):
        for _try in range(8):
            sz = min(r.uniform(0.015, 0.06), 0.5 * (y1 - y0), 0.5 * (x1 - x0))   # nunca sale de la superficie
            cx, cy = r.uniform(x0 + sz, x1 - sz), r.uniform(y0 + sz, y1 - sz)
            if all(math.hypot(cx - px, cy - py) > sz + ps + 0.004 for px, py, ps in placed):
                break
        else:
            continue
        placed.append((cx, cy, sz))
        a0 = r.uniform(0, 2 * PI)
        pts = []
        for k in range(3):
            a = a0 + k * 2 * PI / 3 + r.uniform(-0.45, 0.45)
            rr = sz * r.uniform(0.45, 1.0)
            pts.append((cx + rr * math.cos(a), 0.0, -(cy + rr * math.sin(a))))
        mm = _T(0, 0, z + 0.0016 + 0.0006 * r.random()) @ _R("X", 90)   # planas, apoyadas (0,1–0,7 mm de holgura)
        _prism(mb, pts, 0.003, "glass", (m @ mm) if m is not None else mm)


# =====================================================================================================================
# cortina rasgada (lámina 'fabric') + barra
# =====================================================================================================================
def _curtain_panel(mb, u0, u1, ztop_fn, zbot, yc, r, amp=0.022, wl=0.19, droop=0.0, droop_end=1, rip=True, holes=1,
                   ring_sp=0.1):
    """Paño de tela colgando (lámina de una cara, malla de ~3 x 6 cm con sombreado continuo) con pliegues que nacen en el
    cabezal fruncido (festón entre argollas), dobladillo rasgado, desgarro vertical, agujeros y, opcionalmente, un extremo
    descolgado (droop) donde se soltaron los ganchos. Devuelve las argollas que aún sostienen la tela [(u, y, z)]."""
    W = u1 - u0
    nx = max(10, int(W / (wl / 6.0)))
    nzr = max(8, int((ztop_fn(u0) - zbot) / 0.06))
    ph = r.uniform(0, 2 * PI)
    sway = _Noise(r, wl=0.8, octaves=2, waves=2)
    # dobladillo rasgado: paseo aleatorio + jirones
    hem, z = [], 0.0
    for i in range(nx + 1):
        z = 0.82 * z + r.normal(0, 0.02)
        hem.append(zbot + z + (r.uniform(-0.25, -0.08) if r.random() < 0.04 else 0.0))
    krip = int(r.integers(2, nx - 2)) if (rip and nx > 6) else -1
    rip_top = r.uniform(0.35, 0.8)
    hole_c = [(_uni(r, u0 + 0.1 * W, u1 - 0.1 * W), _uni(r, zbot + 0.2, ztop_fn(u0) - 0.25), r.uniform(0.04, 0.09))
              for _ in range(holes)]

    def dro(s):
        return _smooth((s if droop_end > 0 else 1 - s) * 3.0 - 2.0) if droop > 0 else 0.0

    def pos(i, j, side):
        s = i / nx
        u = u0 + W * s
        zt = ztop_fn(u) - 0.011 * abs(math.sin(PI * (u - u0) / ring_sp))   # festón entre argollas
        zt -= droop * dro(s)
        t = j / nzr
        zz = zt + (hem[i] - zt) * t
        # el pliegue nace casi plano en el cabezal (la tela pasa por las argollas) y se abre hacia abajo
        a = amp * (0.25 + 0.55 * min(1.0, t * 4.0) + 0.45 * t) * (1.0 + 0.35 * sway(u * 1.3, zz))
        a *= 1.0 + 0.8 * dro(s)
        yy = yc + a * math.sin(2 * PI * (u - u0) / wl + ph + 0.5 * sway(u, zz * 0.7)) + 0.012 * sway(zz, u) * t
        uu = u + 0.006 * sway(zz * 2, u) * t
        if side and j / nzr > 1.0 - rip_top:
            sep = (j / nzr - (1.0 - rip_top)) / rip_top
            uu += side * 0.035 * sep * sep
            yy += side * 0.01 * sep
        return (uu, yy, zz)

    V, V2 = {}, {}
    for i in range(nx + 1):
        for j in range(nzr + 1):
            V[(i, j)] = mb._verts([pos(i, j, -1 if i == krip else 0)])[0]
            if i == krip and j / nzr > 1.0 - rip_top - 1e-6:
                V2[(i, j)] = mb._verts([pos(i, j, 1)])[0] if j / nzr > 1.0 - rip_top + 1e-6 else V[(i, j)]
    with mb.soft():
        for i in range(nx):
            for j in range(nzr):
                uc = u0 + W * (i + 0.5) / nx
                zc = ztop_fn(uc) + (hem[i] - ztop_fn(uc)) * (j + 0.5) / nzr
                if any((uc - hu) ** 2 + (zc - hz) ** 2 < hr * hr for hu, hz, hr in hole_c):
                    continue
                a = V[(i, j)] if i != krip else V2.get((i, j), V[(i, j)])
                d = V[(i, j + 1)] if i != krip else V2.get((i, j + 1), V[(i, j + 1)])
                mb.face([a, V[(i + 1, j)], V[(i + 1, j + 1)], d], "fabric")
    loose = [v for v in list(V.values()) + list(V2.values()) if v.is_valid and not v.link_faces]
    bmesh.ops.delete(mb.bm, geom=list(set(loose)), context="VERTS")
    rings = []
    k = 0
    while u0 + k * ring_sp <= u1 + 1e-6:
        u = u0 + k * ring_sp
        s = (u - u0) / W
        if dro(s) < 0.05:
            p = pos(min(nx, round(s * nx)), 0, 0)
            rings.append((u, p[1], ztop_fn(u)))
        k += 1
    return rings


def _curtains(dst, w, h, depth, r, tear=0.6):
    """Barra de cortina Ø19 (24 lados) con remates torneados y soportes de pared atornillados (uno arrancado a veces), argollas
    de Ø32 con su ganchito y 1–2 paños rasgados del lado interior (y > depth).
    La tela nunca atraviesa la cara interior del muro: donde cae por fuera del vano (debajo del antepecho o pasada la
    jamba) se apoya contra el muro a 4 mm; dentro del vano puede meterse en el derrame."""
    mb = MB()
    zr = h + r.uniform(0.07, 0.12)
    yr = depth + 0.065
    ua, ub = -r.uniform(0.12, 0.2), w + r.uniform(0.12, 0.2)
    fall = r.uniform(0.08, 0.22) if r.random() < 0.25 else 0.0   # un soporte arrancado: la barra cuelga de un lado
    sag = r.uniform(0.002, 0.01)
    rr = 0.0095

    def rodz(u):
        s = (u - ua) / (ub - ua)
        return zr - sag * math.sin(PI * s) - fall * s * s

    pts = [(ua + (ub - ua) * k / 12, yr, rodz(ua + (ub - ua) * k / 12)) for k in range(13)]
    mb.tube(pts, rr, seg=24, mat="metal_paint")
    for p, sg in ((pts[0], -1), (pts[-1], 1)):   # remates: collarín y bola torneada
        d = Vector(pts[1]) - Vector(pts[0]) if sg < 0 else Vector(pts[-1]) - Vector(pts[-2])
        M, _ = _frame_on(Vector(p), Vector(p) + d.normalized() * sg, (0, 0, 1))
        _lathe(mb, [(0.0, -0.004), (0.0115, -0.004), (0.0125, 0.0), (0.0125, 0.006), (0.0105, 0.009), (0.0075, 0.011),
                    (0.0105, 0.014), (0.0158, 0.021), (0.0165, 0.029), (0.014, 0.038), (0.008, 0.044), (0.0, 0.0455)],
               seg=24, mat="metal_paint", M=M)
    for k, ub_ in enumerate((ua + 0.09, ub - 0.09)):
        if fall > 0 and k == 1:
            # soporte arrancado: queda la roseta torcida con un taquete salido y los agujeros
            _plate_bev(mb, _rrect(0.04, 0.08, 0.008, 3, ub_, zr - 0.01), depth - 0.002, 0.006, "metal_paint", face=1,
                       bev=0.0015, m=_about((ub_, depth, zr - 0.01), _R("Y", r.uniform(-12, 12))))
            _lathe(mb, [(0.0, 0.0), (0.004, 0.0), (0.004, 0.022), (0.0032, 0.025), (0.0, 0.025)], seg=12, mat="plastic",
                   M=_mat_xy((ub_ + 0.03, depth + 0.004, zr - 0.06), (1, 0, 0), (0, 0, -1)))
            continue
        z0 = rodz(ub_)
        _plate_bev(mb, _rrect(0.04, 0.08, 0.008, 3, ub_, z0 - 0.01), depth - 0.002, 0.007, "metal_paint", face=1, bev=0.002)
        for zz in (z0 - 0.038, z0 + 0.018):
            _screw(mb, (ub_, depth + 0.005, zz), (0, 1, 0), d=0.0065, mat="metal_paint", kind="pan")
        # brazo: varilla doblada que sale del muro y abraza la barra por abajo (copa)
        _rtube(mb, [(ub_, depth + 0.004, z0 - 0.014), (ub_, yr - 0.004, z0 - 0.014), (ub_, yr + 0.0, z0 - 0.0135)], 0.0045,
               "metal_paint", seg=16, rbend=0.0)
        _lathe(mb, [(0.0, -0.002), (0.0135, -0.002), (0.0135, 0.004), (0.0118, 0.006), (0.0, 0.006)], seg=24, mat="metal_paint",
               M=_T(ub_, yr, z0 - 0.0135))
    zb = r.uniform(-0.08, 0.15)
    yc = yr - 0.002
    mode = r.random()
    zt = lambda u: rodz(u) - 0.024   # noqa: E731  (el cabezal cuelga de las argollas)
    rings = []
    if mode < 0.45:      # dos paños, uno recogido a un lado
        cut = w * r.uniform(0.25, 0.4)
        rings += _curtain_panel(mb, ua + 0.03, ua + 0.03 + cut, zt, zb, yc, r, amp=0.035, wl=0.12, rip=r.random() < tear,
                                holes=0, ring_sp=0.06)
        rings += _curtain_panel(mb, ua + cut + 0.12, ub - 0.03, zt, zb, yc, r, amp=0.022,
                                droop=r.uniform(0.15, 0.45) if r.random() < tear else 0.0, droop_end=1, rip=r.random() < tear,
                                holes=int(r.random() < tear) + 1)
    elif mode < 0.8:     # un solo paño corrido, rasgado
        rings += _curtain_panel(mb, ua + 0.03, ub - 0.03, zt, zb, yc, r, amp=0.026,
                                droop=r.uniform(0.2, 0.5) if r.random() < tear else 0.0,
                                droop_end=-1 if r.random() < 0.5 else 1, rip=True, holes=1 + int(r.random() < tear))
    else:                # dos paños recogidos a los lados, jirones
        rings += _curtain_panel(mb, ua + 0.03, ua + 0.03 + w * 0.3, zt, zb + 0.2, yc, r, amp=0.035, wl=0.12, rip=False, holes=0,
                                ring_sp=0.06)
        rings += _curtain_panel(mb, ub - 0.03 - w * 0.3, ub - 0.03, zt, zb, yc, r, amp=0.035, wl=0.12, rip=True, holes=1,
                                ring_sp=0.06)
    # argollas de Ø32 (alambre de 2,5 mm) colgadas de la barra, con ganchito hasta el cabezal de la tela
    with mb.soft():
        for (u, y_, z_) in rings:
            if not (ua + 0.05 < u < ub - 0.05) or (fall > 0 and abs(u - (ub - 0.09)) < 0.03) or abs(u - (ua + 0.09)) < 0.03 \
                    or abs(u - (ub - 0.09)) < 0.03:
                continue
            zc = rodz(u) - 0.006
            Rg, rg = 0.016, 0.00125
            tor = []   # toro de 14 x 8
            for a in range(14):
                t = 2 * PI * a / 14
                ctr = Vector((u, yr + Rg * math.cos(t), zc + Rg * math.sin(t)))
                nrm = Vector((0.0, math.cos(t), math.sin(t)))
                tor.append(mb._verts([tuple(ctr + nrm * (rg * math.cos(2 * PI * b / 8)) + Vector((rg * math.sin(2 * PI * b / 8),
                                                                                                   0, 0))) for b in range(8)]))
            for a in range(14):
                A, B = tor[a], tor[(a + 1) % 14]
                for b in range(8):
                    bb = (b + 1) % 8
                    mb.face([A[b], A[bb], B[bb], B[b]], "metal_paint")
            mb.tube([(u, yr, zc - Rg + 0.0005), (u, (yr + y_) / 2, zc - Rg - 0.004), (u, y_, z_ + 0.004)], 0.0011, seg=8,
                    mat="metal_paint")
    fab = mb.mi("fabric")
    for v in mb.bm.verts:
        if not v.link_faces or v.link_faces[0].material_index != fab:
            continue
        x, z = v.co.x, v.co.z
        d = min(x, w - x, z, h - z)            # > 0 dentro del vano (distancia al borde más cercano)
        ymin = depth + 0.004 - 0.1 * max(d, 0.0)   # pendiente suave: ninguna arista recorta la esquina del muro
        if v.co.y < ymin:
            v.co.y = ymin
    _merge(dst, mb)


# =====================================================================================================================
# alféizar de concreto con gotero + relleno perimetral de mortero
# =====================================================================================================================
def _sill(mb, w, r, chip=0.6):
    """Alféizar de concreto colado: nariz exterior (sobresale 4,6 cm de la fachada, orejas de 6 cm, pendiente de 25 %,
    canto boleado de 8 mm y goterón de 7 x 9 mm a 1,3 cm del frente) + pieza interior dentro del vano (empotrada en la repisa
    del muro). Desportilladuras en la arista frontal."""
    x0, x1 = -0.06 + r.uniform(-0.012, 0.004), w + 0.06 + r.uniform(-0.004, 0.012)
    base = [(-0.0015, 0.032), (-0.046, 0.0205), (-0.046, -0.040), (-0.0335, -0.040), (-0.0335, -0.031), (-0.0265, -0.031),
            (-0.0265, -0.040), (-0.0015, -0.040)]
    prof = _fillet2d(base, [0.0, 0.008, 0.005, 0.0012, 0.0015, 0.0015, 0.0012, 0.0], n=3)
    n = max(6, int((x1 - x0) / 0.08))
    xs = [x0, x0 + 0.004, x0 + 0.008] + [x0 + 0.008 + (x1 - x0 - 0.016) * k / n for k in range(1, n)] + \
        [x1 - 0.008, x1 - 0.004, x1]
    chips = [(r.uniform(x0, x1), r.uniform(0.03, 0.1), r.uniform(0.006, 0.02)) for _ in range(int(1 + 5 * chip))]
    nose = Vector((-0.046, 0.0205))
    rings = []
    for k, x in enumerate(xs):
        endk = 0 if k in (0, len(xs) - 1) else (1 if k in (1, len(xs) - 2) else 2)
        e = sum(cd * max(0.0, 1 - abs(x - cx) / cw) for cx, cw, cd in chips)
        ring = []
        for j, (py, pz) in enumerate(prof):
            yy, zz = py, pz
            wn = max(0.0, 1.0 - (Vector((py, pz)) - nose).length / 0.022)   # la desportilladura muerde la nariz
            yy += e * 0.9 * wn
            zz -= e * 0.7 * wn
            if endk < 2:   # remate de la oreja redondeado (dos anillos que encogen hacia la fachada)
                f = (0.86, 0.95)[endk]
                yy, zz = -0.024 + (yy + 0.024) * f, -0.004 + (zz + 0.004) * (0.9 + 0.05 * endk)
            elif 0 < j < len(prof) - 1:
                yy += r.normal(0, 0.0005)
                zz += r.normal(0, 0.0005)
            ring.append((x, yy, zz))
        rings.append(ring)
    _loft(mb, rings, "concrete")
    zt = 0.029 + r.uniform(-0.002, 0.002)
    mb.box((0.004, -0.006, -0.006), (w - 0.004, 0.036, zt), "concrete", bevel=0.005, seg=2)   # metida bajo la nariz
    return zt


def _packing(mb, w, h, g, y0=0.058, y1=0.1):
    """Relleno de mortero entre marco y jambas (queda 1,2 mm separado del muro y metido 3 mm en el marco)."""
    prof = [(-g + 0.0012, y0), (0.003, y0), (0.003, y1), (-g + 0.0012, y1)]
    mb.sweep(prof, _rect_path(g, g, w - g, h - g, c=0.02), mat="mortar", normal=(0, 1, 0), closed_path=True)


# =====================================================================================================================
# VENTANAS
# =====================================================================================================================
# perfil de marco de aluminio corredizo (x hacia dentro del vano, y profundidad): dos rieles de 4x10 mm
_AL_FRAME = _fillet2d([(0.0, 0.040), (0.031, 0.040), (0.031, 0.050), (0.041, 0.050), (0.041, 0.054), (0.031, 0.054),
                       (0.031, 0.076), (0.041, 0.076), (0.041, 0.080), (0.031, 0.080), (0.031, 0.120), (0.0, 0.120)],
                      [0.0, 0.0018, 0.0006, 0.0009, 0.0009, 0.0006, 0.0006, 0.0009, 0.0009, 0.0006, 0.0018, 0.0], n=2)
# perfil de marco de madera con galce exterior (la hoja abatible asienta en y 0,042–0,072 contra el tope)
_WD_FRAME = _fillet2d([(0.0, 0.040), (0.035, 0.040), (0.035, 0.0745), (0.055, 0.0755), (0.055, 0.128), (0.0, 0.128)],
                      [0.0, 0.004, 0.0012, 0.003, 0.004, 0.0], n=3)
_G = 0.008   # holgura perimetral marco–jamba (rellena de mortero)


def _al_sash(sw, sh, r, broken, mid=True, latch=False):
    """Hoja corrediza de aluminio en coordenadas locales: x 0..sw, z 0..sh, y centrado (+-11 mm)."""
    s = MB()
    s.sweep(_rrprof(0.0, 0.032, -0.011, 0.011, 0.0015), _rect_path(0, 0, sw, sh, c=0.042), mat="aluminium", normal=(0, 1, 0),
            closed_path=True)
    # traslape: pestaña de 3 x 7 mm a todo lo alto del larguero de encuentro (engancha con la de la otra hoja)
    if latch:
        s.box((0.0, -0.0135, 0.03), (0.007, -0.0108, sh - 0.03), "aluminium", bevel=0.0009, seg=2)
    else:
        s.box((sw - 0.007, 0.0108, 0.03), (sw, 0.0135, sh - 0.03), "aluminium", bevel=0.0009, seg=2)
    lites = []
    if mid and sh > 0.95:
        zm = sh * r.uniform(0.42, 0.52)
        s.box((0.028, -0.009, zm - 0.014), (sw - 0.028, 0.009, zm + 0.014), "aluminium", bevel=0.0015, seg=2)
        lites = [(0.032, 0.032, sw - 0.032, zm - 0.014), (0.032, zm + 0.014, sw - 0.032, sh - 0.032)]
    else:
        lites = [(0.032, 0.032, sw - 0.032, sh - 0.032)]
    for (a, b, c, d) in lites:
        _glass(s, a, b, c, d, 0.0, r, min(0.97, max(0.05, broken + r.uniform(-0.2, 0.2))), embed=0.008)
        _glazing(s, a, b, c, d, -0.011, 0.011, 0.0, tg=0.004, bead=False, gw=0.0045)   # vinil cuña a ambos lados
    # tramo de vinil desprendido colgando de una esquina del claro
    if r.random() < 0.5:
        a, b, c, d = lites[int(r.integers(0, len(lites)))]
        x = a + 0.004
        pts = [(x, -0.004, d - 0.01)]
        for k in range(1, 9):
            pts.append((x + 0.009 * math.sin(k * 0.7) + 0.0075 * k, -0.004 - 0.0045 * k, d - 0.01 - 0.034 * k))
        s.tube(pts, 0.0022, seg=10, mat="rubber")
    _warp(s, sw, sh, r, amp=0.002)
    if latch:   # cerrojo de media luna en el larguero de traslape, cara interior: base de 18 x 70 y leva con palanca
        zl = sh * 0.5
        _plate_bev(s, _rrect(0.018, 0.07, 0.004, 3, 0.017, zl), 0.0108, 0.004, "metal_paint", face=1, bev=0.001)
        _lathe(s, [(0.0, 0.0), (0.0075, 0.0), (0.0075, 0.0035), (0.006, 0.005), (0.0, 0.0052)], seg=24, mat="metal_paint",
               M=_mat_xy((0.017, 0.0148, zl + 0.01), (1, 0, 0), (0, 0, -1)))
        arc = [(0.017 + 0.0105 * math.cos(a_), 0.0185, zl + 0.01 + 0.0105 * math.sin(a_)) for a_ in
               [math.radians(-100 + 25 * k) for k in range(7)]]
        _sweep3(s, _rrect(0.004, 0.006, 0.0015, 2), arc + [(arc[-1][0] - 0.012, 0.019, arc[-1][2] + 0.016)], "metal_paint",
                up=(0, 1, 0))
        for zz in (zl - 0.027, zl + 0.027):
            _screw(s, (0.017, 0.0148, zz), (0, 1, 0), d=0.0045, mat="metal_paint", kind="pan")
    return s


def _win_sliding(mb, w, h, depth, r, broken):
    g = _G
    fr = MB()
    fr.sweep(_AL_FRAME, _rect_path(g, g, w - g, h - g, step=0.35, c=0.052), mat="aluminium", normal=(0, 1, 0), closed_path=True)
    cu0, cu1, cv0, cv1 = g + 0.031, w - g - 0.031, g + 0.031, h - g - 0.031
    top = cv1 - 0.004
    if h >= 1.45:   # montante fijo con travesaño
        vt = cv1 - r.uniform(0.3, 0.38)
        fr.box((cu0 - 0.003, 0.043, vt - 0.02), (cu1 + 0.003, 0.117, vt + 0.02), "aluminium", bevel=0.003, seg=1)
        _glass(fr, cu0, vt + 0.02, cu1, cv1, 0.065, r, min(0.97, broken + 0.1), embed=0.006)   # entre los dos rieles
        top = vt - 0.023
    Rk = _rack(fr, w, h, r, deg=0.2, sag=0.004)   # las hojas que siguen en sus rieles se montan con el mismo descuadre
    _merge(mb, fr)
    _packing(mb, w, h, g)
    zb = g + 0.036
    sh = top - zb
    sw = (cu1 - cu0) / 2 + 0.02
    mode = r.random()
    lean_ok = depth >= 0.17
    # hoja exterior (riel delantero, y = 0,052): corrida y descuadrada
    dx = r.uniform(0.0, 0.75) * max(0.0, cu1 - cu0 - sw - 0.006)
    if mode < 0.33 or (mode >= 0.66 and not lean_ok):
        # A: ambas en su riel, desalineadas; la interior también corrida
        _merge(mb, _al_sash(sw, sh, r, broken), Rk @ _T(cu0 + 0.003 + dx, 0.052, zb) @ _about((sw, 0, 0), _R("Y", r.uniform(-0.6, 0.3))))
        dx2 = -r.uniform(0.0, 0.5) * sw
        _merge(mb, _al_sash(sw, sh, r, broken, latch=True), Rk @ _T(cu1 - 0.003 - sw + dx2, 0.078, zb) @ _R("Y", r.uniform(-0.25, 0.25)))
    elif mode < 0.66:
        # B: la interior fuera de su riel, recargada del lado de adentro contra la jamba
        _merge(mb, _al_sash(sw, sh, r, broken), Rk @ _T(cu0 + 0.003 + dx, 0.052, zb) @ _about((sw, 0, 0), _R("Y", r.uniform(-0.5, 0.2))))
        yb = depth - 0.03
        a = math.degrees(math.asin(min(0.2, max(0.0, (yb - 0.133) / sh))))
        # apoyada sobre su esquina inferior derecha (giro en su plano sobre ese punto: nunca entra al piso ni a la jamba)
        _merge(mb, _al_sash(sw, sh, r, broken), _T(0.012, yb, 0.003) @ _R("X", a) @ _about((sw, 0, 0), _R("Y", r.uniform(0.0, 0.5))))
    else:
        # C: la interior desapareció (solo quedan sus carretillas); la exterior se salió del riel por un extremo
        ang = r.uniform(0.6, 1.0)
        _merge(mb, _al_sash(sw, sh, r, broken), Rk @ _T(cu0 + 0.003 + dx, 0.052, zb) @ _about((sw, 0, 0), _R("Y", ang)))
        for k in range(2):   # carretilla: caja de nailon con rueda de Ø16 asomada sobre el riel
            x = cu1 - 0.06 - k * (sw - 0.12)
            mb.box((x - 0.02, 0.069, g + 0.047), (x + 0.02, 0.087, g + 0.06), "plastic", bevel=0.0015, seg=2)
            _lathe(mb, [(0.0, -0.0035), (0.0065, -0.0035), (0.008, -0.002), (0.008, 0.002), (0.0065, 0.0035), (0.0, 0.0035)],
                   seg=24, mat="plastic", M=_T(x, 0.078, g + 0.050) @ _R("X", 90))


def _wd_sash(sw, sh, r, broken, cols=None, rows=None, mat="wood"):
    """Hoja abatible de madera: bastidor 48x30 mm, peinazo inferior 75 mm, travesaños (junquillos) que dividen vidrios.
    Local: x 0..sw (x = 0 lado de bisagras), y +-15 mm, z 0..sh."""
    s = MB()
    # larguero/cabezal de 48 x 30: cuarto bocel (ovolo) de 7 mm en la arista interior del lado de adentro, cantos boleados
    s.sweep(_fillet2d([(0.0, -0.015), (0.048, -0.015), (0.048, 0.015), (0.0, 0.015)], [0.003, 0.0015, 0.007, 0.003], n=4),
            _rect_path(0, 0, sw, sh, c=0.058), mat=mat, normal=(0, 1, 0), closed_path=True)
    zb = 0.075
    s.box((0.044, -0.013, 0.044), (sw - 0.044, 0.013, zb), mat, bevel=0.003, seg=2)
    # botaguas (vierteaguas) en la cara exterior del peinazo: nariz inclinada con goterón de 3 x 4 mm
    dp = _fillet2d([(-0.0145, 0.0685), (-0.031, 0.0535), (-0.031, 0.0445), (-0.0255, 0.0445), (-0.0255, 0.0405),
                    (-0.0225, 0.0405), (-0.0225, 0.0445), (-0.0145, 0.0445)], [0.0, 0.003, 0.002, 0.0006, 0.0006, 0.0006, 0.0006,
                                                                                0.0], n=3)
    _sweep3(s, [(-yy, zz) for yy, zz in dp], [(0.03, 0.0, 0.0), (sw - 0.03, 0.0, 0.0)], mat, up=(0, 0, 1))
    cols = cols or (2 if sw > 0.42 else 1)
    rows = rows or max(1, int(round((sh - 0.12) / 0.42)))
    x0, x1, z0, z1 = 0.048, sw - 0.048, zb, sh - 0.048
    xs = [x0 + (x1 - x0) * k / cols for k in range(cols + 1)]
    zs = [z0 + (z1 - z0) * k / rows for k in range(rows + 1)]
    for x in xs[1:-1]:   # junquillos moldurados (ovolo de 5 mm a ambos lados del lado interior)
        _sweep3(s, _fillet2d([(-0.011, -0.012), (0.011, -0.012), (0.011, 0.012), (-0.011, 0.012)],
                             [0.002, 0.002, 0.005, 0.005], n=3), [(x, 0.0, z0 - 0.004), (x, 0.0, z1 + 0.004)], mat, up=(0, 1, 0))
    for z in zs[1:-1]:   # el travesaño horizontal sobresale 0,5 mm del vertical en cada cara (sin caras coplanares)
        _sweep3(s, _fillet2d([(-0.011, -0.0125), (0.011, -0.0125), (0.011, 0.0125), (-0.011, 0.0125)],
                             [0.002, 0.002, 0.005, 0.005], n=3), [(x0 - 0.004, 0.0, z), (x1 + 0.004, 0.0, z)], mat, up=(0, 1, 0))
    for i in range(cols):
        for j in range(rows):
            a = xs[i] + (0.011 if i > 0 else 0.0)
            c = xs[i + 1] - (0.011 if i < cols - 1 else 0.0)
            b = zs[j] + (0.011 if j > 0 else 0.0)
            d = zs[j + 1] - (0.011 if j < rows - 1 else 0.0)
            bb = 0.97 if r.random() < broken * 0.5 else min(0.97, max(0.08, broken + r.uniform(-0.35, 0.25)))
            _glass(s, a, b, c, d, 0.0, r, bb, embed=0.007)
            # masilla en bisel del lado exterior (la que sostiene el vidrio), agrietada: le faltan tramos
            path = _rect_path(a, b, c, d, c=0.015)
            s.sweep([(-0.001, -0.0024), (0.0075, -0.0024), (-0.001, -0.0118)], path, mat=mat, normal=(0, 1, 0), closed_path=True)
    return s   # el alabeo (_warp) lo aplica quien la usa, DESPUÉS de montar herrajes (así se mueven con la hoja)


def _warp(mb, w, h, r, amp=0.003, side=0):
    """Alabeo de una hoja vieja: torsión (esquina fuera de plano) + ondulación suave (madera hinchada, aluminio vencido).
    side=-1: hoja cerrada contra su tope (que queda en +Y): todo el alabeo va hacia -Y — asienta en el tope por tres
    puntos y la cuarta esquina se despega, nunca lo atraviesa."""
    nz = _Noise(r, wl=0.9, octaves=2, waves=2)
    tw = r.uniform(-1, 1) * amp * 1.5
    for v in mb.bm.verts:
        x, z = v.co.x / max(w, 1e-6), v.co.z / max(h, 1e-6)
        # la torsión es bilineal (exacta sobre las caras largas de barrotes y travesaños); la ondulación es mínima para no
        # comerse las holguras de 2–3 mm entre piezas que se cruzan
        if side < 0:
            v.co.y -= abs(tw) * 2 * min(max(x, 0.0), 1.0) * min(max(z if tw > 0 else 1 - z, 0.0), 1.0) + amp * 0.08 * (1 + nz(v.co.x, v.co.z))
        else:
            v.co.y += tw * (x - 0.5) * (z - 0.5) * 4 + amp * 0.15 * nz(v.co.x, v.co.z)
        v.co.x += amp * 0.15 * nz(v.co.z + 3.1, v.co.x)


def _barrel(mb, x, y, zc, ln, rad, n=5, mat="metal_rust", tips=True, m=None):
    """Nudillos de bisagra de libro (n canutos de 24 lados con chaflán de 0,5 mm y junta de 0,6 mm entre ellos) sobre su
    pasador, con botones de remate arriba y abajo. Eje vertical en (x, y), centrado en zc."""
    M = _T(x, y, zc - ln / 2)
    if m is not None:
        M = m @ M
    g = 0.0006
    kl = (ln - (n - 1) * g) / n
    c = min(0.0005, rad * 0.12)
    _lathe(mb, [(0.0, -0.0006), (rad * 0.42, -0.0006), (rad * 0.42, ln + 0.0006), (0.0, ln + 0.0006)], seg=16, mat=mat, M=M)
    for k in range(n):
        z0 = k * (kl + g)
        _lathe(mb, [(rad * 0.4, z0), (rad - c, z0), (rad, z0 + c), (rad, z0 + kl - c), (rad - c, z0 + kl), (rad * 0.4, z0 + kl)],
               seg=24, mat=mat, M=M)
    if tips:   # botón de remate (pasador con cabeza) arriba, punta abajo
        _lathe(mb, [(0.0, ln - 0.0004), (rad * 0.98, ln - 0.0004), (rad * 0.98, ln + 0.0012), (rad * 0.8, ln + 0.0028),
                    (rad * 0.45, ln + 0.0036), (0.0, ln + 0.0038)], seg=24, mat=mat, M=M)
        _lathe(mb, [(0.0, 0.0004), (rad * 0.98, 0.0004), (rad * 0.98, -0.0012), (rad * 0.8, -0.0028), (rad * 0.45, -0.0036),
                    (0.0, -0.0038)], seg=24, mat=mat, M=M)


def _leafplate(mb, M, L, W, t, mat="metal_rust", screws=3, sd=0.0065, rc=0.003):
    """Hoja de bisagra / placa de herraje: placa de L (Z local) x W (X local) x t (Y local, de 0 a t) con esquinas de radio rc y
    canto redondeado, con `screws` tornillos avellanados en su cara y = t. M la coloca (origen: centro del borde x = 0)."""
    prof = _rrect(W, L, rc, 3, W / 2, 0.0)
    a = mb._verts([(px, 0.0, pz) for px, pz in prof], M)
    b = mb._verts([(px, t, pz) for px, pz in prof], M)
    mb.face(a, mat)
    mb.face(list(reversed(b)), mat)
    k = len(prof)
    for i in range(k):
        j = (i + 1) % k
        mb.face([a[i], b[i], b[j], a[j]], mat)
    for s in range(screws):
        zz = -L / 2 + L * (s + 0.5) / screws
        xx = W * (0.62 if s % 2 else 0.5)
        p = M @ Vector((xx, t, zz))
        ax = (M.to_3x3() @ Vector((0, 1, 0))).normalized()
        _screw(mb, p, ax, d=min(sd, 0.8 * W), mat=mat, kind="flat")


def _inset(pts, d):
    """Polígono 2D CCW desplazado d hacia dentro (por bisectriz; para contornos convexos o casi)."""
    n = len(pts)
    out = []
    for i in range(n):
        a, b, c = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[(i + 1) % n])
        e0, e1 = (b - a), (c - b)
        if e0.length < 1e-9 or e1.length < 1e-9:
            out.append(tuple(b))
            continue
        n0 = Vector((-e0.y, e0.x)).normalized()
        n1 = Vector((-e1.y, e1.x)).normalized()
        nb = n0 + n1
        nb = nb.normalized() if nb.length > 1e-6 else n0
        k = d / max(0.35, nb.dot(n0))
        out.append(tuple(b + nb * k))
    return out


def _plate_bev(mb, pts, y0, t, mat, face=-1, bev=0.0008, m=None):
    """Placa (pletina, chapa) de contorno `pts` [(x, z)] CCW visto desde -Y, de y0 a y0 + face*t, con el canto de la cara vista
    (la del lado `face`) redondeado/achaflanado `bev`; la cara de apoyo queda plana. Sólido cerrado."""
    inner = _inset(pts, bev)
    yA = y0
    yB = y0 + face * (t - bev)
    yC = y0 + face * t
    A = mb._verts([(x, yA, z) for x, z in pts], m)
    B = mb._verts([(x, yB, z) for x, z in pts], m)
    C = mb._verts([(x, yC, z) for x, z in inner], m)
    k = len(pts)
    mb.face(list(reversed(A)), mat)
    mb.face(C, mat)
    for R0, R1 in ((A, B), (B, C)):
        for i in range(k):
            j = (i + 1) % k
            mb.face([R0[i], R0[j], R1[j], R1[i]], mat)


def _lever(mb, x, y, z, d, r, mat="metal_paint", m=None, droop=0.0):
    """Manija de palanca con retorno hacia la hoja sobre roseta (local de la hoja; la palanca apunta a -X).
    Roseta Ø52 x 9 mm de canto redondo (32 lados), cuello Ø18 con collarín, palanca de 17 x 11 mm de sección redondeada,
    curva de retorno de 1,5 cm hacia la hoja y punta redonda. d = signo de la cara (-1 exterior, +1 interior)."""
    mm = m if m is not None else Matrix.Identity(4)
    up = Vector((0.0, d, 0.0))
    M, _ = _frame_on(Vector((x, y - d * 0.001, z)), Vector((x, y - d * 0.001, z)) + up, (0, 0, 1))
    M = mm @ M
    _lathe(mb, [(0.0, 0.0), (0.026, 0.0), (0.026, 0.0035), (0.0252, 0.0062), (0.0232, 0.0083), (0.019, 0.0096), (0.0105, 0.01),
                (0.0, 0.0101)], seg=32, mat=mat, M=M)
    _lathe(mb, [(0.0, 0.009), (0.0098, 0.009), (0.0098, 0.03), (0.0108, 0.034), (0.0108, 0.04), (0.0094, 0.043), (0.0094, 0.058),
                (0.006, 0.0605), (0.0, 0.061)], seg=24, mat=mat, M=M)
    dz = -0.12 * math.sin(math.radians(droop))
    yy = lambda k: y + d * k   # noqa: E731
    pts = [(x + 0.004, yy(0.052), z), (x - 0.008, yy(0.0525), z + dz * 0.04), (x - 0.025, yy(0.053), z + dz * 0.18),
           (x - 0.05, yy(0.052), z + dz * 0.4), (x - 0.075, yy(0.049), z + dz * 0.62), (x - 0.098, yy(0.044), z + dz * 0.82),
           (x - 0.112, yy(0.037), z + dz * 0.93), (x - 0.119, yy(0.03), z + dz), (x - 0.1215, yy(0.0262), z + dz),
           (x - 0.123, yy(0.0236), z + dz)]
    pts = [mm @ Vector(p) for p in pts]

    def sc(s):
        return 1.0 if s < 0.9 else max(0.3, math.sqrt(max(0.0, 1 - ((s - 0.9) / 0.1) ** 2)))
    _sweep3(mb, _rrect(0.011, 0.017, 0.0045, 3), pts, mat, up=mm.to_3x3() @ Vector((0, 0, 1)), scale=sc)


def _cylinder_rose(mb, p, axis, R=0.011, h=0.009, mat="metal_paint", turn=False, m=None):
    """Escudo de cilindro de cerradura (o de mirilla): roseta torneada de 28 lados con bombín y ranura de llave; turn=True
    lleva botón de giro (cara interior) en vez de bocallave."""
    a = Vector(axis).normalized()
    p = Vector(p)
    M, _ = _frame_on(p - a * 0.001, p + a, (0, 0, 1))
    if m is not None:
        M = m @ M
    _lathe(mb, [(0.0, 0.0), (R, 0.0), (R, h * 0.35), (R * 0.93, h * 0.7), (R * 0.78, h), (R * 0.55, h * 1.02), (0.0, h * 1.02)],
           seg=28, mat=mat, M=M)
    if turn:
        mb.box((-0.0035, -R * 0.75, h), (0.0035, R * 0.75, h + 0.011), mat, bevel=0.0015, seg=2, m=M)
    else:
        mb.box((-0.0007, -R * 0.38, h * 0.95), (0.0007, R * 0.18, h * 1.08), "metal_rust", m=M)


def _hinge(mb, x, y, z, r, ln=0.07, rad=0.0065):
    """Bisagra de pernio de ventana: canutos con pasador y botones."""
    _barrel(mb, x, y, z, ln, rad, n=5 if ln > 0.06 else 3)


def _win_wood_frame(mb, w, h, r, transom=True):
    """Marco de madera con galce, opcional montante con vidrio. Devuelve (cota superior libre para las hojas, matriz del
    descuadre del marco para montar las hojas con él)."""
    g = _G
    fr = MB()
    fr.sweep(_WD_FRAME, _rect_path(g, g, w - g, h - g, step=0.6, c=0.066), mat="wood", normal=(0, 1, 0), closed_path=True)
    top = h - g - 0.035
    if transom and h >= 1.45:
        vt = h - g - r.uniform(0.33, 0.4)
        fr.box((g + 0.03, 0.041, vt - 0.03), (w - g - 0.03, 0.127, vt + 0.03), "wood", bevel=0.004, seg=2)
        _glass(fr, g + 0.055, vt + 0.03, w - g - 0.055, h - g - 0.055, 0.1, r, 0.6, embed=0.02)
        top = vt - 0.03
    Rk = _rack(fr, w, h, r, deg=0.3, sag=0.004)
    _merge(mb, fr)
    _packing(mb, w, h, g, 0.06, 0.1)
    return top, Rk


def _win_casement(mb, w, h, depth, r, broken, allow_open=True, lites=(None, None), transom=True):
    g = _G
    top, Rk = _win_wood_frame(mb, w, h, r, transom=transom)
    hw = MB()   # hojas y herrajes: se montan con el mismo descuadre del marco
    zb = g + 0.037
    sh = top - 0.004 - zb
    W_r = w - 2 * (g + 0.037)
    two = W_r > 0.75
    sw = W_r / 2 - 0.002 if two else W_r - 0.002
    mir = Matrix.Diagonal((-1, 1, 1, 1))
    for k in range(2 if two else 1):
        if r.random() < 0.12 and k == 1:   # hoja perdida: quedan las bisagras
            for zz in (zb + 0.15, zb + sh - 0.15):
                _hinge(hw, w - g - 0.037, 0.040, zz, r)
            continue
        th = 0.0
        if allow_open:
            th = r.uniform(15, 105) if (k == 0 and r.random() < 0.75) else (r.uniform(2, 12) if r.random() < 0.5 else 0.0)
        sag = r.uniform(0.3, 1.2) if th > 10 else 0.0
        s = _wd_sash(sw, sh, r, broken, cols=lites[0], rows=lites[1])
        for zz in (0.15, sh - 0.15):   # nudillo 7 cm; las hojas de la bisagra 6,4 cm (sin tapas coplanares)
            _hinge(s, 0.0, -0.016, zz, r)
            _leafplate(s, _mat_xy((0.004, -0.0148, zz), (1, 0, 0), (0, -1, 0)), 0.064, 0.026, 0.0017, screws=2, sd=0.0052)
        if k == 1:   # manija de falleba en el larguero de cierre (cara interior): escudo boleado y palanca curva
            zf = sh * 0.48
            _plate_bev(s, _rrect(0.018, 0.08, 0.005, 3, sw - 0.025, zf), 0.0145, 0.0045, "metal_paint", face=1, bev=0.0012)
            _lathe(s, [(0.0, 0.0), (0.0068, 0.0), (0.0068, 0.004), (0.0058, 0.012), (0.0062, 0.016), (0.0, 0.0175)], seg=24,
                   mat="metal_paint", M=_mat_xy((sw - 0.025, 0.0185, zf), (1, 0, 0), (0, 0, -1)))
            pts = [(sw - 0.025, 0.031, zf), (sw - 0.03, 0.034, zf - 0.02), (sw - 0.032, 0.036, zf - 0.045),
                   (sw - 0.03, 0.037, zf - 0.065), (sw - 0.0285, 0.037, zf - 0.07)]
            _sweep3(s, _rrect(0.0065, 0.009, 0.0028, 2), pts, "metal_paint", up=(1, 0, 0),
                    scale=lambda t_: 1.0 if t_ < 0.85 else max(0.35, 1 - (t_ - 0.85) / 0.15 * 0.65))
            for zz in (zf - 0.03, zf + 0.03):
                _screw(s, (sw - 0.025, 0.019, zz), (0, 1, 0), d=0.0045, mat="metal_paint", kind="pan")
        _warp(s, sw, sh, r, amp=0.003, side=-1 if th < 3 else 0)
        sagm = _R("Y", sag)   # la hoja vencida: el extremo libre cae
        if k == 0:   # gira sobre el eje del nudillo (y = 0,041); abre hacia afuera (-Y)
            M = _T(g + 0.037, 0.041, zb) @ _R("Z", -th) @ _T(0, 0.016, 0) @ sagm
        else:
            M = _T(w - g - 0.037, 0.041, zb) @ _R("Z", th) @ mir @ _T(0, 0.016, 0) @ sagm
        _merge(hw, s, M)
        # hoja de la bisagra en el marco (fija)
        hx = g + 0.037 if k == 0 else w - g - 0.037
        for zz in (zb + 0.15, zb + sh - 0.15):
            sx = 1 if k == 0 else -1
            _leafplate(hw, _mat_xy((hx, 0.0402, zz), (-sx, 0, 0), (0, -1, 0)), 0.064, 0.026, 0.0017, screws=2, sd=0.0052)
    _merge(mb, hw, Rk)


def _shutter_panel(W, H, r, style):
    """Postigo exterior. Local: x 0..W (x = 0 eje de bisagras), y +-15 mm (-Y = cara exterior al cerrar), z 0..H.
    style 'louvre' (bastidor + tablillas a 45°, algunas faltantes/rotas) o 'board' (tablas + barrotes en Z)."""
    s = MB()
    Tk = 0.03
    if style == "louvre":
        mat, st = "wood", 0.055
        s.box((0, -Tk / 2, 0), (st, Tk / 2, H), mat, bevel=0.004, seg=2)
        s.box((W - st, -Tk / 2, 0), (W, Tk / 2, H), mat, bevel=0.004, seg=2)
        rails = [(0.003, 0.10), (H - 0.07, H - 0.003)]
        if H > 1.0:
            zm = H * r.uniform(0.45, 0.55)
            rails.append((zm - 0.035, zm + 0.035))
        rails.sort()
        for z0, z1 in rails:
            s.box((st - 0.004, -Tk / 2 + 0.002, z0), (W - st + 0.004, Tk / 2 - 0.002, z1), mat, bevel=0.004, seg=2)
        L = W - 2 * st + 0.008
        for (za, zb_), (zc, _) in zip(rails[:-1], rails[1:]):
            z = zb_ + 0.022
            while z < zc - 0.018:
                q = r.random()
                if q < 0.12:
                    pass
                elif q < 0.2:   # tablilla rota colgando de un lado
                    ln = L * r.uniform(0.3, 0.6)
                    Mb = _T(st - 0.004, 0, z) @ _R("Y", r.uniform(8, 25)) @ _R("X", r.uniform(55, 80))
                    s.box((0, -0.018, -0.0035), (ln, 0.018, 0.0035), mat, bevel=0.0028, seg=2, m=Mb)
                    # punta astillada del lado roto
                    _prism(s, [(ln - 0.002, 0.0, -0.0075), (ln + r.uniform(0.02, 0.05), 0.0, r.uniform(-0.006, 0.006)),
                               (ln - 0.002, 0.0, 0.0075)], 0.0055, mat, m=Mb @ _R("X", -90))
                else:   # tablilla de 36 x 7 de cantos redondos, metida en las cajas de los largueros
                    s.box((-L / 2, -0.018, -0.0035), (L / 2, 0.018, 0.0035), mat, bevel=0.0028, seg=2,
                          m=_T(W / 2, 0, z) @ _R("X", 45 + r.uniform(-6, 6)) @ _R("Y", r.uniform(-0.6, 0.6)))
                z += 0.042
    else:
        mat = "wood_grey"
        nb = max(2, int(round(W / 0.19)))
        bw = (W - (nb - 1) * 0.004) / nb
        for i in range(nb):
            x = i * (bw + 0.004) + bw / 2
            Hb = H - r.uniform(0.0, 0.035)
            p = _plank(Hb, bw - r.uniform(0, 0.008), 0.016, r, mat, cut=(r.uniform(-0.01, 0.01), r.uniform(-0.03, 0.03)),
                       bow=0.002, twist=0.6, step=0.45)
            _merge(s, p, _T(x, -0.007, r.uniform(0.0, 0.015)) @ _R("Y", -90))
        for zc in (0.12, H - 0.12):
            p = _plank(W - 0.03, 0.09, 0.015, r, mat, bow=0.001, twist=0.3, step=0.3)
            _merge(s, p, _T(0.015, 0.0075, zc))
        dz = (H - 0.24 - 0.09)
        ang = math.degrees(math.atan2(dz, W - 0.12))
        ln = math.hypot(dz, W - 0.12) + 0.04
        p = _plank(ln, 0.085, 0.0148, r, mat, bow=0.001, twist=0.3, cut=(0.05, -0.05), step=0.35)
        _merge(s, p, _T(0.04, 0.0076, 0.12 + 0.045) @ _R("Y", -ang))
    # bisagras de cola de golondrina (cara interior +Y) con nudillo en el eje
    for zc in (0.12, H - 0.12):
        # pletina forjada de 32 mm que se adelgaza hasta un remate redondo, sobre la cara interior (+Y), con su ojo
        pts = [(-0.004, zc - 0.016), (0.22, zc - 0.016), (0.29, zc - 0.009)] + \
            [(0.30 + 0.011 * math.cos(a_), zc + 0.011 * math.sin(a_)) for a_ in [-PI / 2 + PI * k / 6 for k in range(1, 6)]] + \
            [(0.29, zc + 0.009), (0.22, zc + 0.016), (-0.004, zc + 0.016)]
        _plate_bev(s, pts, 0.0147, 0.0042, "metal_rust", face=1, bev=0.001)
        _lathe(s, [(0.0042, -0.028), (0.0088, -0.028), (0.0095, -0.0273), (0.0095, 0.0273), (0.0088, 0.028), (0.0042, 0.028)],
               seg=24, mat="metal_rust", M=_T(0.0, 0.0, zc))
        for xb in (0.08, 0.25):
            _screw(s, (xb, 0.0187, zc), (0, 1, 0), d=0.011, kind="dome")
    return s


def _win_shutter(mb, w, h, depth, r, broken):
    _win_casement(mb, w, h, depth, r, broken, allow_open=False, lites=(1, 2), transom=False)
    style = "louvre" if r.random() < 0.5 else "board"
    zb = 0.045
    H = h + 0.02 - zb
    W = w / 2 + 0.025 - 0.003
    crooked = int(r.integers(0, 2))
    mir = Matrix.Diagonal((-1, 1, 1, 1))
    for k in range(2):
        s = _shutter_panel(W, H, r, style)
        ax = -0.025 if k == 0 else w + 0.025
        if k == crooked:   # se reventó la bisagra superior: cuelga de la inferior, torcido y separado del muro
            th = r.uniform(18, 55)
            loc = _about((0, 0, 0.12), _R("X", r.uniform(3, 7)) @ _R("Y", r.uniform(5, 12)))
        else:
            th = r.uniform(148, 170)
            loc = Matrix.Identity(4)
        M = _T(ax, -0.02, zb) @ _R("Z", -th if k == 0 else th) @ (mir if k == 1 else Matrix.Identity(4)) @ loc
        _xform(s, M)
        mn, mx = _bounds(s)
        if mx.y > -0.002:
            _xform(s, _T(0, -(mx.y + 0.002), 0))
        _merge(mb, s)
        for zc in (zb + 0.12, zb + H - 0.12):   # pernios (goznes) empotrados en la fachada con su remiendo de mortero
            _lathe(mb, [(0.0, -0.034), (0.0055, -0.034), (0.0055, 0.027), (0.0042, 0.0292), (0.0022, 0.0302), (0.0, 0.0304)],
                   seg=16, mat="metal_rust", M=_T(ax, -0.02, zc))
            mb.box((ax - 0.008, -0.026, zc - 0.041), (ax + 0.008, 0.012, zc - 0.03), "metal_rust", bevel=0.002, seg=2)
            pm = [(ax + 0.022 * math.cos(2 * PI * k / 12) * r.uniform(0.75, 1.15),
                   zc - 0.035 + 0.019 * math.sin(2 * PI * k / 12) * r.uniform(0.75, 1.15)) for k in range(12)]
            _plate_bev(mb, pm, 0.0015, 0.0045, "mortar", face=-1, bev=0.0018)


def _win_boarded(mb, w, h, depth, r, broken):
    _win_casement(mb, w, h, depth, r, max(broken, 0.8), allow_open=False, lites=(1, 2), transom=False)
    T1 = 0.022
    y1, y2 = -0.004 - T1 / 2, -0.006 - 1.5 * T1
    boards = []   # (ancho, matriz, [(x_local, y_cara)]) para clavos

    def horiz(zc, bw, tilt, ext=None):
        el, er = ext or (r.uniform(0.07, 0.2), r.uniform(0.07, 0.2))
        L = w + el + er
        p = _plank(L, bw, T1, r, "wood_grey", cut=(r.uniform(-0.03, 0.03), r.uniform(-0.03, 0.03)), bow=0.003, twist=0.5,
                   step=0.2)
        M = _T(-el, y1, zc) @ _R("Y", tilt)
        _merge(mb, p, M)
        boards.append((bw, M, [(x, -T1 / 2) for x in (el * r.uniform(0.3, 0.6), L - er * r.uniform(0.3, 0.6))]))
        return el, L

    bw_t, bw_b = r.uniform(0.13, 0.2), r.uniform(0.13, 0.2)
    zt = h + r.uniform(-0.03, 0.05)
    tb = r.uniform(0.0, 0.8)
    zbot = 0.045 + bw_b / 2 + (w + 0.4) * math.sin(math.radians(tb)) + r.uniform(0.0, 0.04)
    broken_top = r.random() < 0.4
    if broken_top:   # la tabla superior se partió: el trozo derecho cuelga de su último clavo
        el, er = r.uniform(0.07, 0.2), r.uniform(0.07, 0.2)
        L = w + el + er
        L1 = el + w * r.uniform(0.3, 0.55)
        p = _plank(L1, bw_t, T1, r, "wood_grey", cut=(r.uniform(-0.02, 0.02), r.uniform(0.03, 0.06)), bow=0.002, twist=0.4)
        M = _T(-el, y1, zt)
        _merge(mb, p, M)
        boards.append((bw_t, M, [(0.03, -T1 / 2), (el - 0.035, -T1 / 2)]))
        L2 = L - L1 - 0.012
        p = _plank(L2, bw_t, T1, r, "wood_grey", cut=(r.uniform(-0.06, -0.03), r.uniform(-0.02, 0.02)), bow=0.002, twist=0.4)
        piv = (L2 - er * 0.5, 0, 0)
        M = _T(-el + L1 + 0.012, y1, zt) @ _about(piv, _R("Y", -r.uniform(10, 24)))
        _merge(mb, p, M)
        boards.append((bw_t, M, [(L2 - er * 0.5, -T1 / 2)]))
    else:
        horiz(zt, bw_t, r.uniform(-1.5, 1.5))
        if r.random() < 0.5:
            horiz(h * r.uniform(0.42, 0.58), r.uniform(0.12, 0.18), r.uniform(-2.5, 2.5))
    horiz(zbot, bw_b, tb)
    # cruz: A apoyada en las horizontales (capa 2); B encima de A (capa 3) y se dobla hasta apoyar sus extremos
    a0 = (r.uniform(-0.02, 0.1), zbot + r.uniform(-0.02, 0.02))
    a1 = (w - r.uniform(-0.02, 0.1), zt + r.uniform(-0.02, 0.02))
    b0 = (w - r.uniform(-0.02, 0.1), zbot + r.uniform(-0.02, 0.02))
    b1 = (r.uniform(-0.02, 0.1), zt + r.uniform(-0.02, 0.02))
    da = (a1[0] - a0[0], a1[1] - a0[1])
    db = (b1[0] - b0[0], b1[1] - b0[1])
    den = db[0] * da[1] - db[1] * da[0]
    sb = ((a0[0] - b0[0]) * da[1] - (a0[1] - b0[1]) * da[0]) / den if abs(den) > 1e-6 else 0.5
    la = math.hypot(*da)
    uax, uaz = da[0] / la, da[1] / la
    for (p0, d, cross) in ((a0, da, None), (b0, db, sb)):
        ln = math.hypot(*d)
        ux, uz = d[0] / ln, d[1] / ln
        L = ln + 0.12
        bwd = r.uniform(0.11, 0.16)
        yfn = None
        nails = [(0.05, -T1 / 2), (L - 0.05, -T1 / 2)]
        if cross is not None:
            sc = (cross * ln + 0.06) / L
            half = (0.085 / max(0.3, abs(ux * uaz - uz * uax)) + 0.03) / L
            yfn = (lambda s, sc=sc, half=half: -(T1 + 0.001) * _smooth(1.0 - (abs(s - sc) - half) / 0.22))
            nails.append((sc * L, -T1 / 2 - T1 - 0.001))
        p = _plank(L, bwd, T1, r, "wood_grey", cut=(r.uniform(-0.04, 0.04), r.uniform(-0.04, 0.04)), bow=0.002, twist=0.4,
                   yfn=yfn, step=0.1 if yfn else 0.2)
        M = _T(p0[0] - ux * 0.06, y2, p0[1] - uz * 0.06) @ _R("Y", -math.degrees(math.atan2(uz, ux)))
        _merge(mb, p, M)
        boards.append((bwd, M, nails))
    # clavos (cabezas) en cada apoyo
    for (bw, M, nails) in boards:
        for x, yf in nails:
            for dz in (-0.28, 0.27):
                _nail(mb, x + r.uniform(-0.008, 0.008), yf, dz * bw + r.uniform(-0.006, 0.006), r, m=M)


def window(kind, w, h, depth=0.20, seed=0, broken=0.7, curtain=True, sill=True):
    """Ventana completa para un vano w x h (local: u = 0..w en X, v = 0..h en Z, muro y = 0..depth).
    kind: 'sliding' (aluminio corredizo), 'casement' (madera abatible), 'shutter' (abatible + postigos), 'boarded' (tapiada).
    broken 0..1: vidrio perdido. curtain: cortina rasgada del lado interior. sill: alféizar de concreto con gotero."""
    if kind not in ("sliding", "casement", "shutter", "boarded"):
        raise ValueError(f"window kind desconocido: {kind}")
    r = rng(seed)
    mb = MB()
    zs = _sill(mb, w, r) if sill else 0.0
    {"sliding": _win_sliding, "casement": _win_casement, "shutter": _win_shutter, "boarded": _win_boarded}[kind](
        mb, w, h, depth, r, broken)
    if broken > 0.2 and kind != "boarded":
        if sill:   # sobre la parte plana del alféizar (dentro del vano, delante del marco)
            _loose_glass(mb, 0.06, w - 0.06, 0.003, 0.037, zs, int(2 + 6 * broken), r)
        else:
            _loose_glass(mb, 0.05, w - 0.05, 0.004, 0.034, 0.0, int(2 + 5 * broken), r)
    if curtain:
        _curtains(mb, w, h, depth, r, tear=0.4 + 0.5 * broken)
    return mb


# =====================================================================================================================
# PUERTAS
# =====================================================================================================================
def _door_frame(mb, w, h, prof, mat, r, g=0.006, c=None):
    """Marco de 3 lados (jambas empotradas 1 cm bajo el piso terminado), descuadrado levemente."""
    c = c or (max(p[0] for p in prof) + 0.012)
    sub = MB()
    sub.sweep(prof, _door_path(g, w - g, -0.01, h - g, step=0.45, c=c), mat=mat, normal=(0, 1, 0))
    Rk = _rack(sub, w, h, r, deg=0.12, sag=0.004)
    _merge(mb, sub)
    return Rk   # para montar el herraje del marco (pernios, cerradero) con el mismo descuadre


def _swing_clear(leaf, Mfn, angle, boxes, margin=0.0015, pin=None):
    """Mayor ángulo (de `angle` hacia 0, resolución 0,5°) con el que ningún vértice de la hoja entra en las cajas
    prohibidas (jambas, muro) — una hoja real se detiene donde su herraje toca la jamba o el muro. Se ignora el herraje
    que gira en el propio eje (a < 2 cm del perno: nudillos, ojos de bisagra)."""
    if not boxes:
        return angle

    def inside(p):
        return any(x0 - margin < p.x < x1 + margin and y0 - margin < p.y < y1 + margin and z0 < p.z < z1
                   for (x0, x1, y0, y1, z0, z1) in boxes)

    M0 = Mfn(0.0)
    # los vértices que ya tocan con la hoja cerrada (pernios embutidos, canto hinchado) son contacto de diseño: se ignoran
    vs = [v.co.copy() for v in leaf.bm.verts if not inside(M0 @ v.co)
          and (pin is None or math.hypot(v.co.x - pin[0], v.co.y - pin[1]) > 0.02)]
    def ok(a):
        M = Mfn(a)
        return not any(inside(M @ co) for co in vs)

    if ok(angle):
        return angle
    lo, hi = 0.0, abs(angle)          # el choque crece con el giro: búsqueda binaria a 0,5°
    sgn = 1.0 if angle >= 0 else -1.0
    while hi - lo > 0.5:
        mid = 0.5 * (lo + hi)
        if ok(sgn * mid):
            lo = mid
        else:
            hi = mid
    return sgn * lo


def _jamb_boxes(w, h, depth, g, jx, yj0, yj1):
    """Cajas prohibidas para una hoja que abre hacia adentro: cuerpo de ambas jambas (x hasta jx desde el marco, y yj0..yj1)
    y el muro a cada lado del vano (y 0..depth)."""
    return [(g - 0.003, g + jx, yj0, yj1, -1.0, h + 1.0), (w - g - jx, w - g + 0.003, yj0, yj1, -1.0, h + 1.0),
            (-1.0, 0.0005, 0.0, depth, -1.0, h + 1.0), (w - 0.0005, w + 1.0, 0.0, depth, -1.0, h + 1.0)]


_PARTS = None   # cuando door(..., parts=True) recolecta las hojas por separado


def _leaf_place(mb, leaf, u_hinge, y_face, z0, pin, angle, mirror=False, boxes=None):
    """Coloca una hoja (local x 0..W desde la bisagra, y 0..T con y = 0 cara exterior) girándola `angle` grados sobre su
    perno `pin` (local). angle > 0 abre hacia +Y. mirror: hoja con bisagra a la derecha.
    boxes: cajas prohibidas (ver _swing_clear); el ángulo se reduce hasta que la hoja no las toque. Devuelve la matriz."""
    B = _T(u_hinge, y_face, z0)
    if mirror:
        B = B @ Matrix.Diagonal((-1, 1, 1, 1))

    def Mfn(a):
        return B @ _about((pin[0], pin[1], 0.0), _R("Z", a))

    angle = _swing_clear(leaf, Mfn, angle, boxes, pin=pin)
    M = Mfn(angle)
    if _PARTS is not None:   # hoja aparte: geometría en posición CERRADA + eje de giro (mundo) + ángulo aplicado
        piv = B @ Vector((pin[0], pin[1], 0.0))
        sgn = -1.0 if mirror else 1.0
        closed = MB()
        closed.join(leaf, Mfn(0.0))
        _PARTS.append({"mb": closed, "pivot": (piv.x, piv.y, piv.z), "axis": (0.0, 0.0, sgn), "angle": float(angle)})
        leaf.bm.free()
        return M
    _merge(mb, leaf, M)
    return M


def _butt_hinges(mb, x, y, zs, r, ln=0.09, rad=0.0068):
    """Bisagras de libro (canutos con pasador y botones) con el eje en (x, y) a las alturas zs."""
    for z in zs:
        _barrel(mb, x, y, z, ln, rad, n=5)


def _mat_xy(o, X, Y):
    """Matriz con origen o y ejes X, Y dados (Z = X x Y)."""
    X, Y = Vector(X), Vector(Y)
    Z = X.cross(Y)
    return Matrix(((X.x, Y.x, Z.x, o[0]), (X.y, Y.y, Z.y, o[1]), (X.z, Y.z, Z.z, o[2]), (0.0, 0.0, 0.0, 1.0)))


def _door_flush(mb, w, h, depth, r, ang):
    """Puerta de departamento: marco de madera con tope, moldura exterior, hoja de tambor con chapa, mirilla y número,
    forzada (canto astillado a la altura de la chapa, chapa de piel desprendida y abolladuras)."""
    g = 0.006
    y0, ys, y1 = 0.001, 0.031, depth - 0.012
    # marco (jamba de 42 x 136 mm con tope rebajado de 15 mm): aristas boleadas de 2–3 mm, como una jamba cepillada
    prof = _fillet2d([(0.0, y0), (0.042, y0), (0.042, ys), (0.027, ys + 0.0015), (0.027, y1), (0.0, y1)],
                     [0.0, 0.003, 0.002, 0.0015, 0.003, 0.0], n=3)
    Rk = _door_frame(mb, w, h, prof, "wood", r, g)
    # moldura exterior (chambrana colonial de 88 x 19 mm): canto interior boleado con media caña, campo, gola y contramarco
    cas = [(-0.072, -0.0012), (0.016, -0.0012), (0.016, -0.0085), (0.0156, -0.0096), (0.0146, -0.0103), (0.0132, -0.0106),
           (0.0088, -0.0108), (0.0079, -0.0101), (0.0068, -0.0099), (0.0058, -0.0104), (0.0048, -0.0112), (-0.0385, -0.0128),
           (-0.0415, -0.0132), (-0.0448, -0.0141), (-0.0478, -0.0155), (-0.0505, -0.0170), (-0.0532, -0.0180),
           (-0.0565, -0.0187), (-0.0655, -0.0190), (-0.0688, -0.0187), (-0.0708, -0.0177), (-0.0718, -0.0161),
           (-0.072, -0.0140)]
    sub = MB()
    if r.random() < 0.5:   # tramo de chambrana arrancado en la jamba izquierda
        cut = r.uniform(0.6, 1.4)
        sub.sweep(cas, _door_path(0.0, w, -0.005, h, step=0.5, c=0.085, z_end=cut), mat="wood", normal=(0, 1, 0))
        if r.random() < 0.6:
            sub.sweep(cas, [(0.0, 0.0, cut - r.uniform(0.25, 0.55)), (0.0, 0.0, -0.005)], mat="wood", normal=(0, 1, 0))
    else:
        sub.sweep(cas, _door_path(0.0, w, -0.005, h, step=0.5, c=0.085), mat="wood", normal=(0, 1, 0))
    _rack(sub, w, h, r, deg=0.1, sag=0.0)
    _merge(mb, sub)
    # umbral de mármol/concreto
    mb.box((0.003, -0.012, -0.012), (w - 0.003, y1, 0.012), "concrete", bevel=0.004, seg=1)   # pasa bajo las jambas
    # hoja
    T = 0.04
    xl0 = g + 0.027 + 0.003
    Wl, Hl = w - 2 * xl0, h - g - 0.027 - 0.003 - 0.016
    leaf, rings, nx = _slab(Wl, Hl, T, nx=12, nz=26, c=0.003, mat="wood")   # malla de ~7 cm: las abolladuras se leen
    dent0 = _dents(r, int(r.integers(4, 9)), 0.1, Wl - 0.28, 0.1, 1.5, rad=(0.05, 0.13), depth=(0.003, 0.009))
    scuff = _dents(r, int(r.integers(2, 5)), 0.1, Wl - 0.15, 0.05, 0.42, rad=(0.03, 0.06), depth=(0.002, 0.007))   # patadas

    def dent(x, z):
        return dent0(x, z) + scuff(x, z)
    kick = (Wl - r.uniform(0.15, 0.3), r.uniform(0.35, 0.6), r.uniform(0.08, 0.13), r.uniform(0.01, 0.02))
    warp = r.uniform(0.003, 0.012)
    wsgn = 1 if r.random() < 0.5 else -1
    zl = 0.98
    for ring in rings:
        # desplazamientos por anillo (no por vértice): las caras del canto no se pliegan sobre sí mismas
        rot_dx, rot_dz, cut_dx = r.normal(0, 0.0015), r.uniform(-0.002, 0.0), r.uniform(0.008, 0.026)
        for j, v in enumerate(ring):
            x, z = v.co.x, v.co.z
            if j <= nx:   # cara exterior (abolladuras acotadas: la piel nunca alcanza a la cara interior)
                d = dent(x, z) + kick[3] * math.exp(-((x - kick[0]) ** 2 + (z - kick[1]) ** 2) / kick[2] ** 2)
                v.co.y += min(d, T - 0.012)
            # alabeo: la hoja asienta en el tope por las bisagras y una esquina; la otra esquina del canto de la chapa se
            # despega hacia adentro (+Y) — nunca atraviesa el tope
            v.co.y += warp * (x / Wl) * (0.5 + 0.5 * wsgn * (2 * z / Hl - 1))
            if z < 0.06:   # canto inferior hinchado/podrido
                v.co.x += rot_dx + r.normal(0, 0.0003)
                v.co.z += rot_dz * (1 - z / 0.06)   # nunca baja hasta el umbral (tope a z = 0,012)
            if x > Wl - 0.012 and abs(z - zl) < 0.16:   # canto astillado (barreta)
                k = 1 - abs(z - zl) / 0.16
                v.co.x -= k * cut_dx
                v.co.y += r.normal(0, 0.0012)
    # piel de triplay desprendida, enroscándose hacia afuera desde abajo
    if r.random() < 0.75:
        Wk, Hk = r.uniform(0.25, 0.45), r.uniform(0.35, 0.7)
        sk, srings, snx = _slab(Wk, Hk, 0.003, nx=6, nz=12, c=0.0008, mat="wood")
        curl = r.uniform(0.09, 0.17)
        for ring in srings[1:-1]:   # bordes rasgados: cada costado del jirón se desplaza en bloque por anillo
            exl, exr = r.normal(0, 0.012), r.normal(0, 0.012)
            for j in (0, 2 * snx + 3, 2 * snx + 4, 2 * snx + 5):
                ring[j].co.x += exl
            for j in (snx, snx + 1, snx + 2, snx + 3):
                ring[j].co.x += exr
        for v in sk.bm.verts:
            t = 1 - v.co.z / Hk
            v.co.y -= curl * t * t + 0.004 * math.sin(v.co.x * 25) * t
            v.co.z += curl * 0.45 * t * t * t
        _merge(leaf, sk, _T(r.uniform(0.03, 0.12), -0.0035, r.uniform(0.0, 0.08)))
    # chapa, manijas, cerrojo, mirilla, número
    xh = Wl - 0.065
    for d, yy in ((-1, 0.0), (1, T)):
        # placa larga (escudo) de 48 x 220 mm de canto boleado con tornillos, manija de palanca y cilindro
        pl = _rrect(0.048, 0.22, 0.006, 3, xh, zl)
        _plate_bev(leaf, pl, yy - d * 0.001, 0.0045, "metal_paint", face=d, bev=0.0012)
        _lever(leaf, xh, yy + d * 0.0035, zl + 0.04, d, r, droop=r.uniform(0, 35) if d < 0 else 0.0)
        _cylinder_rose(leaf, (xh, yy + d * 0.0035, zl - 0.06), (0, d, 0), R=0.011, h=0.008, turn=False)
        for zz in (zl + 0.095, zl - 0.095):
            _screw(leaf, (xh, yy + d * 0.0035, zz), (0, d, 0), d=0.0062, mat="metal_paint", kind="pan")
        # cerrojo de seguridad: roseta con bocallave por fuera, botón de giro por dentro
        _cylinder_rose(leaf, (xh, yy - d * 0.001, 1.28), (0, d, 0), R=0.0215, h=0.012, turn=d > 0)
    # mirilla (Ø14 mm con lente) y placa de número atornillada
    Mv = _mat_xy((Wl / 2, 0.0015, 1.55), (1, 0, 0), (0, 0, 1))   # Z local = -Y (hacia afuera)
    _lathe(leaf, [(0.0, 0.0), (0.0108, 0.0), (0.0108, 0.0028), (0.0098, 0.004), (0.0074, 0.0046), (0.0074, 0.0078),
                  (0.0064, 0.0082), (0.0062, 0.0072), (0.0, 0.0072)], seg=24, mat="metal_paint", M=Mv)
    _lathe(leaf, [(0.0, 0.0071), (0.0063, 0.0071), (0.0063, 0.0077), (0.0, 0.0079)], seg=24, mat="glass", M=Mv)
    _plate_bev(leaf, _rrect(0.09, 0.06, 0.006, 3, Wl / 2, 1.71), 0.0008, 0.0048, "metal_paint", face=-1, bev=0.001)
    for sx in (-0.036, 0.036):
        _screw(leaf, (Wl / 2 + sx, -0.004, 1.71), (0, -1, 0), d=0.0055, mat="metal_paint", kind="dome")
    # bisagras de libro de 3 1/2" (89 mm): hojas embutidas en el canto con 3 tornillos avellanados
    zs = (0.22, Hl / 2 + 0.1, Hl - 0.22)
    for z in zs:
        _leafplate(leaf, _mat_xy((0.0013, T - 0.002, z), (0, -1, 0), (-1, 0, 0)), 0.089, 0.028, 0.0025)
    pin = (-0.001, T + 0.004)
    _leaf_place(mb, leaf, xl0, ys + 0.002, 0.016, pin, ang, boxes=_jamb_boxes(w, h, depth, g, 0.027, ys + 0.001, y1))
    _butt_hinges(mb, xl0 - 0.001, ys + 0.002 + T + 0.004, [z + 0.016 for z in zs], r)
    fh = MB()   # herraje y daños de la jamba: con el descuadre del marco
    for z in zs:
        _leafplate(fh, _mat_xy((g + 0.026, ys + 0.002 + T, z + 0.016), (0, -1, 0), (1, 0, 0)), 0.089, 0.03, 0.0025)
    # cerradero arrancado (zafado, colgando de un tornillo) y astillas en la jamba de la chapa
    xj = w - g - 0.027
    if r.random() < 0.4:
        Ms = _mat_xy((xj + 0.002, ys + 0.004, zl + 0.016), (0, 1, 0), (-1, 0, 0))
        _leafplate(fh, Ms @ _about((0.004, 0.0, 0.055), _R("Y", r.uniform(-14, -6)) @ _R("Z", r.uniform(4, 9))), 0.14, 0.026,
                   0.0018, screws=1, rc=0.004)
    for _ in range(int(r.integers(4, 8))):
        zc = zl + 0.016 + r.uniform(-0.12, 0.12)
        ln = r.uniform(0.04, 0.12)
        yb = r.uniform(ys + 0.006, ys + 0.04)
        tip = (xj - r.uniform(0.006, 0.025), yb + r.uniform(-0.01, 0.01), zc + r.choice([-1, 1]) * ln)
        _prism(fh, [(xj + 0.003, yb, zc - 0.006), (xj + 0.003, yb, zc + 0.006), tip], 0.004, "wood")
    _merge(mb, fh, Rk)


def _glazing(mb, a, b, c, d, y0, y1, yg, tg=0.005, bead=True, gasket=(-1, 1), mat="aluminium", gw=0.0055):
    """Vidriado de un claro (a..c en x, b..d en z) de un bastidor de y0..y1 con el vidrio en yg: junquillo de presión con cara
    inclinada del lado +Y (si bead) y empaque de hule (cuña) a ambos lados del vidrio, aunque el vidrio ya no esté."""
    path = _rect_path(a, b, c, d, c=0.02)
    if bead:
        yb = yg + tg / 2 + 0.0032
        bp = _fillet2d([(-0.001, yb), (0.0115, yb), (0.0115, yb + 0.002), (0.0045, y1 - 0.0016), (-0.001, y1 - 0.0016)],
                       [0.0, 0.0006, 0.0008, 0.0012, 0.0], n=2)
        mb.sweep(bp, path, mat=mat, normal=(0, 1, 0), closed_path=True)
    for sd in gasket:
        yc = yg + sd * (tg / 2 + 0.0013)
        mb.sweep(_rrect(gw, 0.0024, 0.0011, 2, 0.0005 + gw / 2, yc), path, mat="rubber", normal=(0, 1, 0), closed_path=True)


def _door_glazed(mb, w, h, depth, r, ang):
    """Puertas dobles de vestíbulo: marco de aluminio con tope, montante si h > 2,3, dos hojas de bastidor ancho (perfil
    tubular de 62 x 45 con cantos de radio 1,8 mm) con zoclo, travesaño-empujador, junquillos y empaques de hule, jaladera
    tubular Ø25 sobre postes torneados, barra de empuje Ø28, cerrojo de piso, bisagras de libro, vidrio roto en esquirlas
    y vidrio en el piso."""
    g = 0.006
    y0, y1 = 0.05, min(depth - 0.01, 0.15)
    prof = _fillet2d([(0.0, y0), (0.058, y0), (0.058, y0 + 0.012), (0.045, y0 + 0.013), (0.045, y1), (0.0, y1)],
                     [0.0, 0.0015, 0.001, 0.0008, 0.0015, 0.0], n=2)
    _door_frame(mb, w, h, prof, "aluminium", r, g)
    top = h - g - 0.045
    if h > 2.3:
        vt = h - g - r.uniform(0.38, 0.5)
        tp = _rrprof(-0.03, 0.03, y0 + 0.001, y1 - 0.001, 0.0018)
        mb.sweep([(z, y) for z, y in tp], [(g + 0.04, 0.0, vt), (w - g - 0.04, 0.0, vt)], mat="aluminium", normal=(0, 1, 0))
        _glass(mb, g + 0.045, vt + 0.03, w - g - 0.045, top, (y0 + y1) / 2, r, 0.75, embed=0.012)
        _glazing(mb, g + 0.045, vt + 0.03, w - g - 0.045, top, y0, y1, (y0 + y1) / 2)
        top = vt - 0.03
    # umbral de aluminio con rampas y estrías antiderrapantes (pasa bajo las jambas)
    ya, yb_ = y0 - 0.03, y1 + 0.01
    ribs = []
    nr = 9
    for k in range(nr):
        x0_ = ya + 0.012 + (yb_ - ya - 0.024) * k / nr
        x1_ = ya + 0.012 + (yb_ - ya - 0.024) * (k + 0.55) / nr
        ribs += [(x0_, 0.0075), (x0_ + 0.0006, 0.009), (x1_ - 0.0006, 0.009), (x1_, 0.0075)]
    tprof = [(ya, -0.008), (yb_, -0.008), (yb_, -0.0045), (yb_ - 0.012, 0.0075)] + list(reversed(ribs)) + [(ya + 0.012, 0.0075),
                                                                                                      (ya, -0.0045)]
    _sweep3(mb, [(-yy, zz) for yy, zz in tprof], [(0.003, 0.0, 0.0), (w - 0.003, 0.0, 0.0)], "aluminium", up=(0, 0, 1))
    T = 0.045
    xin0, xin1 = g + 0.045 + 0.003, w - g - 0.045 - 0.003
    Wl = (xin1 - xin0) / 2 - 0.003
    Hl = top - 0.003 - 0.014
    yf = y0 + 0.014
    angs = (ang, min(85.0, ang * r.uniform(0.2, 1.6)) if r.random() < 0.6 else 0.0)   # tope antes del muro a escuadra
    for k in range(2):
        lf = MB()
        lf.sweep(_rrprof(0.0, 0.062, 0.0, T, 0.0018), _rect_path(0, 0, Wl, Hl, c=0.075), mat="aluminium", normal=(0, 1, 0),
                 closed_path=True)
        lf.box((0.058, 0.002, 0.058), (Wl - 0.058, T - 0.002, 0.2), "aluminium", bevel=0.003, seg=2)
        zm = r.uniform(0.95, 1.05)
        lf.box((0.058, 0.004, zm - 0.04), (Wl - 0.058, T - 0.004, zm + 0.04), "aluminium", bevel=0.003, seg=2)
        for (gb, gt) in ((0.2, zm - 0.04), (zm + 0.04, Hl - 0.062)):
            _glass(lf, 0.062, gb, Wl - 0.062, gt, T / 2, r, min(0.97, r.uniform(0.5, 1.0)), embed=0.01)
            _glazing(lf, 0.062, gb, Wl - 0.062, gt, 0.0, T, T / 2)
        # jaladera exterior vertical Ø25 x 600 sobre dos postes torneados, junto al larguero de cierre
        xp = Wl - 0.035
        for zz in (0.9, 1.3):
            _lathe(lf, [(0.0, -0.001), (0.0165, -0.001), (0.0165, 0.0025), (0.0125, 0.0055), (0.0098, 0.009), (0.0098, 0.046),
                        (0.0, 0.046)], seg=24, mat="aluminium", M=_mat_xy((xp, 0.0, zz), (1, 0, 0), (0, 0, 1)))
        _lathe(lf, [(0.0, 0.0), (0.0062, 0.0006), (0.0104, 0.003), (0.0125, 0.0075), (0.0125, 0.5925), (0.0104, 0.597),
                    (0.0062, 0.5994), (0.0, 0.6)], seg=24, mat="aluminium", M=_T(xp, -0.0565, 0.8))
        # barra de empuje interior Ø28 sobre postes
        for xx in (0.1, Wl - 0.1):
            _lathe(lf, [(0.0, -0.001), (0.018, -0.001), (0.018, 0.0025), (0.0135, 0.006), (0.011, 0.01), (0.011, 0.04),
                        (0.0, 0.04)], seg=24, mat="aluminium", M=_mat_xy((xx, T, zm), (1, 0, 0), (0, 0, -1)))
        _lathe(lf, [(0.0, 0.0), (0.007, 0.0007), (0.0118, 0.0035), (0.014, 0.0085), (0.014, Wl - 0.13 - 0.0085),
                    (0.0118, Wl - 0.13 - 0.0035), (0.007, Wl - 0.1307), (0.0, Wl - 0.13)], seg=24, mat="aluminium",
               M=_T(0.065, T + 0.052, zm) @ _R("Y", 90))
        # cerrojo de piso (pasador) en el larguero de cierre, cara interior
        lf.box((Wl - 0.03, T - 0.004, 0.06), (Wl - 0.012, T + 0.012, 0.13), "metal_paint", bevel=0.002, seg=2)
        _lathe(lf, [(0.0, 0.0), (0.0045, 0.0), (0.0045, 0.08), (0.003, 0.0815), (0.0, 0.082)], seg=16, mat="metal_rust",
               M=_T(Wl - 0.021, T + 0.016, 0.025))
        for zz in (0.07, 0.12):
            _screw(lf, (Wl - 0.021, T + 0.012, zz), (0, 1, 0), d=0.005, mat="metal_paint", kind="pan")
        # abolladura del zoclo
        dn = _dents(r, 2, 0.1, Wl - 0.1, 0.06, 0.2, rad=(0.05, 0.1), depth=(0.003, 0.008))
        for v in lf.bm.verts:
            if v.co.y < 0.004 and v.co.z < 0.2:
                v.co.y += dn(v.co.x, v.co.z)
        # hoja vencida: gira en su plano sobre la bisagra inferior; el canto libre baja hasta casi rozar el umbral
        # (holgura 5 mm -> máx. 4 mm) y arriba se abre una rendija contra la jamba de bisagras
        sag = r.uniform(0.5, 1.0) * math.degrees(math.asin(min(1.0, 0.004 / Wl))) if (k == 1 and r.random() < 0.6) else 0.0
        if sag:
            _xform(lf, _R("Y", sag))
        hinge = xin0 if k == 0 else xin1
        _leaf_place(mb, lf, hinge, yf, 0.014, (0.002, T + 0.003), angs[k], mirror=(k == 1),
                    boxes=_jamb_boxes(w, h, depth, g, 0.045, y0 + 0.012, y1))   # la barra de empuje tope con la jamba
        hx = hinge + (0.002 if k == 0 else -0.002)
        _butt_hinges(mb, hx, yf + T + 0.003, (0.264, 0.014 + Hl * 0.55, 0.014 + Hl - 0.2), r, ln=0.1, rad=0.0072)
        sx = 1 if k == 0 else -1
        for zz in (0.264, 0.014 + Hl * 0.55, 0.014 + Hl - 0.2):   # hoja de la bisagra en el marco
            _leafplate(mb, _mat_xy((hinge - sx * 0.0035, yf + T + 0.003, zz), (0, -1, 0), (sx, 0, 0)), 0.1, 0.03, 0.0025)
    _loose_glass(mb, 0.1, w - 0.1, -0.7, -0.05, 0.0, int(r.integers(8, 15)), r)
    _loose_glass(mb, 0.1, w - 0.1, depth + 0.05, depth + 0.7, 0.0, int(r.integers(6, 12)), r)


def _strap(mb, x0, x1, z, y, r, w0=0.042, t=0.005, face=-1, bolts=4):
    """Bisagra de cola larga forjada (pletina ahusada de 5 mm con remate de lanza redondeado y canto suavizado) sobre una cara
    en y (face = -1: cara hacia -Y), con pernos de coche de cabeza de cúpula y tuerca del otro lado oculta."""
    L = x1 - x0
    n = 6
    pts = [(x0, z - w0 / 2)]
    for k in range(1, n + 1):   # costado inferior ahusándose
        s = k / n
        pts.append((x0 + (L - 0.05) * s, z - (w0 / 2 - (w0 / 2 - w0 * 0.2) * s ** 1.4)))
    tip = _arc(x1 - 0.05 + 0.0, z, w0 * 0.2, -PI / 2, PI / 2, 4)
    pts += [(x1 - 0.05 + (px - (x1 - 0.05)) * 2.6 + 0.0, pz) for px, pz in tip[1:-1]]
    pts.append((x1 - 0.05, z + w0 * 0.2))
    for k in range(n - 1, -1, -1):
        s = k / n
        pts.append((x0 + (L - 0.05) * s, z + (w0 / 2 - (w0 / 2 - w0 * 0.2) * s ** 1.4)))
    _plate_bev(mb, pts, y + face * 0.0006 * -1, t, "metal_rust", face=face, bev=0.0012)
    for k in range(bolts):
        xb = x0 + 0.05 + (x1 - x0 - 0.12) * k / max(1, bolts - 1)
        _screw(mb, (xb, y + face * (t - 0.0006), z), (0, face, 0), d=0.0125 - 0.0015 * (k / max(1, bolts - 1)), kind="dome")


def _padlock(mb, x, y, z, r, d=-1):
    """Candado de 40 mm: cuerpo de 44 x 18 x 45 mm con aristas redondeadas (radio 4 mm), arco de Ø7 mm
    (16 lados, doblez de radio real) y bocallave abajo. Arco en z, cuerpo debajo; d = hacia dónde mira el frente."""
    mb.box((x - 0.022, y - 0.009, z - 0.075), (x + 0.022, y + 0.009, z - 0.03), "metal_paint", bevel=0.004, seg=3)
    pts = [(x - 0.0115, y, z - 0.034), (x - 0.0115, y, z + 0.006)] + \
        [(x + 0.0115 * math.cos(PI - PI * k / 8), y, z + 0.006 + 0.0115 * math.sin(PI * k / 8)) for k in range(1, 8)] + \
        [(x + 0.0115, y, z + 0.006), (x + 0.0115, y, z - 0.034)]
    _rtube(mb, pts, 0.0035, "metal_rust", seg=16, rbend=0.0)
    mb.box((x - 0.001, y - 0.004, z - 0.0758), (x + 0.001, y + 0.004, z - 0.0748), "metal_rust")


def _door_plank(mb, w, h, depth, r, ang):
    """Puerta de cabaña: tablones verticales con barrotes y riostras en Z por dentro, bisagras de cola con pernios,
    aldaba con armella y candado, umbral de madera gastado. Abre hacia AFUERA (-Y)."""
    g = 0.006
    y0 = 0.002
    ys = y0 + 0.054
    y1 = max(ys + 0.02, depth - 0.008)
    prof = _fillet2d([(0.0, y0), (0.05, y0), (0.05, ys), (0.072, ys), (0.072, y1), (0.0, y1)],
                     [0.0, 0.004, 0.0015, 0.003, 0.004, 0.0], n=3)   # aristas gastadas de 3–4 mm
    _door_frame(mb, w, h, prof, "wood_grey", r, g)
    th = _plank(w - 0.006, depth + 0.025, 0.035, r, "wood_grey", step=0.12, bow=0.0, twist=0.0,
                yfn=lambda s: -0.006 * math.sin(PI * s) ** 2)
    _merge(mb, th, _T(0.003, (depth - 0.035) / 2, 0.0095) @ _R("X", 90))   # pasa bajo las jambas; fondo a -8 mm
    xl0 = g + 0.05 + 0.003
    Wl, Hl, z0 = w - 2 * xl0, h - g - 0.05 - 0.003 - 0.031, 0.031
    leaf = MB()
    n = max(3, int(round(Wl / 0.15)))
    ws = r.uniform(0.8, 1.2, n)
    gaps = r.uniform(0.003, 0.008, n - 1)
    ws = ws / ws.sum() * (Wl - gaps.sum())
    rot = int(r.integers(0, n))
    split = int(r.integers(0, n)) if r.random() < 0.6 else -1
    xs = []
    x = 0.0
    for i in range(n):
        cut0 = r.uniform(-0.012, 0.012)
        lo = abs(cut0) + r.uniform(0.001, 0.008)        # el corte sesgado nunca baja al umbral
        hi = Hl - 0.011 - r.uniform(0.0, 0.015)          # ni sube al cabezal (corte superior hasta +1 cm)
        if i == rot:   # tablón podrido abajo: más corto y con corte irregular
            cut0 = r.uniform(0.03, 0.06) * r.choice([-1, 1])
            lo = max(r.uniform(0.06, 0.16), abs(cut0) + 0.002)
        if i == split and ws[i] > 0.1:   # tablón rajado a lo largo: dos piezas con grieta en cuña
            wa = ws[i] * r.uniform(0.35, 0.6)
            for (xc, wd, lo_) in ((x + wa / 2, wa - 0.002, lo), (x + wa + (ws[i] - wa) / 2 + 0.0015, ws[i] - wa - 0.004,
                                                                   lo + r.uniform(0.0, 0.04))):
                c0 = r.uniform(-0.02, 0.02)
                lo_ = max(lo_, abs(c0) + 0.001)
                p = _plank(hi - lo_, wd, 0.025, r, "wood_grey", step=0.22, bow=0.003, twist=0.8,
                           cut=(c0, r.uniform(-0.01, 0.01)))
                _merge(leaf, p, _T(xc, 0.0125, lo_) @ _R("Y", -90))
        else:
            p = _plank(hi - lo, ws[i] - 0.002, 0.025, r, "wood_grey", step=0.22, bow=0.003, twist=0.8,
                       cut=(cut0, r.uniform(-0.01, 0.01)))
            _merge(leaf, p, _T(x + ws[i] / 2, 0.0125, lo) @ _R("Y", -90))
        xs.append((x + ws[i] / 2, lo))
        x += ws[i] + (gaps[i] if i < n - 1 else 0)
    bat = [0.16, Hl - 0.16] + ([Hl * 0.52] if Hl > 1.6 else [])
    bat.sort()
    for zc in bat:
        p = _plank(Wl - 0.04, 0.12, 0.025, r, "wood_grey", step=0.3, bow=0.002, twist=0.5)
        _merge(leaf, p, _T(0.02, 0.0365, zc))
    for za, zb in zip(bat[:-1], bat[1:]):
        ax, az, bx, bz = 0.07, za + 0.06, Wl - 0.07, zb - 0.06
        ln = math.hypot(bx - ax, bz - az)
        an = math.degrees(math.atan2(bz - az, bx - ax))
        p = _plank(ln, 0.1, 0.024, r, "wood_grey", step=0.35, bow=0.001, twist=0.4, cut=(0.05, -0.05))
        _merge(leaf, p, _T(ax, 0.0366, az) @ _R("Y", -an))
    for (xc, lo) in xs:   # clavos que atraviesan tablón y barrote
        for zc in bat:
            if zc > lo + 0.03:
                _nail(leaf, xc + r.uniform(-0.02, 0.02), 0.0, zc + r.uniform(-0.03, 0.03), r)
    for zc in (bat[0], bat[-1]):
        _strap(leaf, 0.0, min(0.48, Wl * 0.7), zc, 0.0, r)   # arranca en el nudillo (no se mete en la jamba)
        # ojo enrollado de la pletina alrededor del pernio (Ø19, 24 lados) y su cuello hasta la pletina
        _lathe(leaf, [(0.0062, 0.0), (0.0089, 0.0), (0.0095, 0.0006), (0.0095, 0.0574), (0.0089, 0.058), (0.0062, 0.058)],
               seg=24, mat="metal_rust", M=_T(-0.004, -0.012, zc - 0.029))
    # aldaba en la hoja (cerrada) o arrancada colgando del candado (abierta)
    zc = Hl * 0.5 + r.uniform(-0.05, 0.08)
    xs_ = w - g - 0.025
    closed = ang <= 3
    if closed:   # aldaba de 185 mm con ojo de bisagra, extremo redondo y ranura de la armella
        hp = _rrect(0.185, 0.036, 0.008, 3, Wl - 0.0375, zc)
        _plate_bev(leaf, hp, -0.0006, 0.0045, "metal_rust", face=-1, bev=0.0009)
        _lathe(leaf, [(0.0, 0.0), (0.0055, 0.0), (0.006, 0.0005), (0.006, 0.0435), (0.0055, 0.044), (0.0, 0.044)], seg=24,
               mat="metal_rust", M=_T(Wl - 0.135, -0.0045, zc - 0.022))
        for xx in (Wl - 0.105, Wl - 0.07):
            _screw(leaf, (xx, -0.0051, zc), (0, -1, 0), d=0.0075, kind="dome")
    else:
        for k in range(3):
            _bolt(leaf, (Wl - 0.12 + 0.02 * k, 0.0, zc + r.uniform(-0.012, 0.012)), (0.1 * r.normal(), -1, 0.15 * r.normal()),
                  r=0.0035, ln=0.012)
    M = _leaf_place(mb, leaf, xl0, y0 + 0.002, z0, (-0.004, -0.012), -ang, boxes=_jamb_boxes(w, h, depth, g, 0.05, y0 - 0.001, y1))
    for zz in (bat[0], bat[-1]):   # pernios (gozne) en la cara del marco: pasador Ø11,6 con punta redonda sobre placa atornillada
        px, py, pz = xl0 - 0.004, y0 + 0.002 - 0.012, z0 + zz
        _lathe(mb, [(0.0, -0.034), (0.0058, -0.034), (0.0058, 0.029), (0.0045, 0.0315), (0.0024, 0.0325), (0.0, 0.033)],
               seg=16, mat="metal_rust", M=_T(px, py, pz))
        _lathe(mb, [(0.0, -0.047), (0.0105, -0.047), (0.0105, -0.0365), (0.0085, -0.0345), (0.0, -0.0345)], seg=24,
               mat="metal_rust", M=_T(px, py, pz))   # collarín de apoyo bajo el ojo
        mb.box((px - 0.002, py - 0.004, pz - 0.046), (px + 0.03, y0 + 0.001, pz - 0.036), "metal_rust", bevel=0.0015, seg=2)
        _plate_bev(mb, _rrect(0.034, 0.075, 0.006, 3, px + 0.03, pz - 0.041), y0 + 0.0006, 0.0045, "metal_rust", face=-1,
                   bev=0.001)
        for zq in (pz - 0.066, pz - 0.016):
            _screw(mb, (px + 0.03, y0 - 0.0039, zq), (0, -1, 0), d=0.008, kind="pan")
    # armella en el marco (placa con 2 tornillos y grapa en U de Ø8,4) + candado
    zw = z0 + zc
    _plate_bev(mb, _rrect(0.036, 0.1, 0.007, 3, xs_, zw), y0 + 0.0006, 0.0031, "metal_rust", face=-1, bev=0.0008)
    for zq in (zw - 0.036, zw + 0.036):
        _screw(mb, (xs_, y0 - 0.0025, zq), (0, -1, 0), d=0.0075, kind="pan")
    _rtube(mb, [(xs_ - 0.012, y0 - 0.001, zw), (xs_ - 0.012, y0 - 0.026, zw), (xs_ + 0.012, y0 - 0.026, zw),
                (xs_ + 0.012, y0 - 0.001, zw)], 0.0042, "metal_rust", seg=16, rbend=0.008)
    _padlock(mb, xs_, y0 - 0.02, zw + 0.004, r)
    if not closed:
        sub = MB()   # aldaba arrancada colgando del candado (con los tornillos todavía en sus agujeros)
        _plate_bev(sub, _rrect(0.036, 0.185, 0.008, 3, xs_, zw - 0.1), -0.0008, 0.0045, "metal_rust", face=-1, bev=0.0009)
        _lathe(sub, [(0.0, 0.0), (0.0055, 0.0), (0.006, 0.0005), (0.006, 0.0435), (0.0055, 0.044), (0.0, 0.044)], seg=24,
               mat="metal_rust", M=_T(xs_ - 0.022, -0.005, zw - 0.195) @ _R("Y", 90))
        for zq in (zw - 0.16, zw - 0.125):
            _screw(sub, (xs_, -0.0053, zq), (0, -1, 0), d=0.0075, kind="dome")
        _merge(mb, sub, _about((xs_, -0.003, zw - 0.012), _R("Y", r.uniform(-12, 12)) @ _R("X", r.uniform(-8, -2))))


def _door_metal(mb, w, h, depth, r, ang):
    """Puerta de servicio: marco de lámina con tope, hoja de tambor de acero abollada (pliegue, esquina inferior
    forzada hacia afuera), rejilla de ventilación, letrero atornillado, manijas, cierrapuertas con brazo roto."""
    g = 0.006
    y0, ys, y1 = 0.01, 0.03, depth - 0.01
    # marco de lámina doblada (cara de 2" = 52 mm, tope de 5/8" = 16 mm): dobleces de radio 1,5–2 mm
    prof = _fillet2d([(0.0, y0), (0.052, y0), (0.052, ys), (0.036, ys + 0.0015), (0.036, y1), (0.0, y1)],
                     [0.0, 0.002, 0.0015, 0.0012, 0.002, 0.0], n=3)
    Rk = _door_frame(mb, w, h, prof, "metal_paint", r, g)
    # umbral de lámina con rampas boleadas (pasa bajo las jambas)
    ya, yb_ = y0 - 0.02, y1
    tprof = _fillet2d([(ya, -0.006), (yb_, -0.006), (yb_, 0.001), (yb_ - 0.016, 0.006), (ya + 0.016, 0.006), (ya, 0.001)],
                      [0.0, 0.0, 0.002, 0.004, 0.004, 0.002], n=3)
    _sweep3(mb, [(-yy, zz) for yy, zz in tprof], [(0.003, 0.0, 0.0), (w - 0.003, 0.0, 0.0)], "metal_rust", up=(0, 0, 1))
    T = 0.045
    xl0 = g + 0.036 + 0.003
    Wl, Hl, z0 = w - 2 * xl0, h - g - 0.036 - 0.003 - 0.012, 0.012
    leaf, rings, nx = _slab(Wl, Hl, T, nx=14, nz=28, c=0.004, mat="metal_paint")
    vent = (Wl / 2 - 0.21, Wl / 2 + 0.21, 0.2, 0.5)
    sign = (Wl / 2 - 0.12, Wl / 2 + 0.12, 1.42, 1.58)
    dn = _dents(r, int(r.integers(7, 13)), 0.06, Wl - 0.06, 0.1, Hl - 0.2, rad=(0.05, 0.2), depth=(0.005, 0.026))
    c0 = (r.uniform(0.1, 0.4), r.uniform(0.6, 1.0))
    c1 = (c0[0] + r.uniform(0.3, 0.5), c0[1] + r.uniform(-0.25, 0.25))
    # esquina inferior libre forzada con barreta: hacia afuera si la hoja está abierta; cerrada, hundida hacia adentro
    # (hacia afuera atravesaría el tope del marco)
    pry = r.uniform(0.04, 0.08) * (1.0 if ang > 12 else -0.6)
    warp = r.uniform(0.003, 0.012)
    wsgn = 1 if r.random() < 0.5 else -1

    def mask(x, z):
        m = 1.0
        for (a, b, c, d) in (vent, sign, (Wl - 0.13, Wl, 0.82, 1.18)):
            dx = max(a - x, 0.0, x - b)
            dz = max(c - z, 0.0, z - d)
            m = min(m, _smooth(math.hypot(dx, dz) / 0.06))
        return m

    dn_in = _dents(r, int(r.integers(3, 7)), 0.08, Wl - 0.08, 0.15, Hl - 0.15, rad=(0.06, 0.2), depth=(0.002, 0.009))

    def ext_d(x, z):
        vx, vz = c1[0] - c0[0], c1[1] - c0[1]
        t = max(0.0, min(1.0, ((x - c0[0]) * vx + (z - c0[1]) * vz) / (vx * vx + vz * vz)))
        dl = math.hypot(x - c0[0] - t * vx, z - c0[1] - t * vz)
        return min((dn(x, z) + 0.02 * math.exp(-(dl / 0.035) ** 2)) * mask(x, z), T - 0.012)   # piel hueca: tope

    for ring in rings:
        for j, v in enumerate(ring):
            x, z = v.co.x, v.co.z
            if j <= nx:
                v.co.y += ext_d(x, z)
            elif nx + 3 <= j <= 2 * nx + 3 and 0.03 < x < Wl - 0.03:   # golpes también por dentro (la piel interior se hunde)
                sh_m = _smooth(math.hypot(max(0.12 - x, 0.0, x - 0.23), max(Hl - 0.1 - z, 0.0, z - Hl + 0.01)) / 0.06)
                v.co.y -= min(dn_in(x, z) * mask(x, z) * sh_m, max(0.0, T - 0.012 - ext_d(x, z)))   # sin tocar herrajes
            v.co.y -= pry * _smooth((x - 0.62 * Wl) / (0.38 * Wl)) * _smooth((0.38 - z) / 0.38)
            v.co.y += warp * (x / Wl) * (0.5 + 0.5 * wsgn * (2 * z / Hl - 1))
    # rejilla de ventilación sobrepuesta
    a, b, c, d = vent
    # marco de la rejilla: ángulo de lámina con esquinas redondeadas, atornillado
    fr = _rrect(b - a, d - c, 0.006, 3, (a + b) / 2, (c + d) / 2)
    fi = _rrect(b - a - 0.036, d - c - 0.036, 0.003, 3, (a + b) / 2, (c + d) / 2)
    A = leaf._verts([(x, 0.0006, z) for x, z in fr])
    B = leaf._verts([(x, -0.0105, z) for x, z in _inset(fr, 0.0012)])
    C = leaf._verts([(x, -0.0105, z) for x, z in _inset(fi, -0.0012)])
    D = leaf._verts([(x, 0.0006, z) for x, z in fi])
    for R0, R1 in ((A, B), (B, C), (C, D), (D, A)):
        for i in range(len(fr)):
            j = (i + 1) % len(fr)
            leaf.face([R0[i], R0[j], R1[j], R1[i]], "metal_paint")
    for (xb, zb) in ((a + 0.009, c + 0.009), (b - 0.009, c + 0.009), (a + 0.009, d - 0.009), (b - 0.009, d - 0.009)):
        _screw(leaf, (xb, -0.0105, zb), (0, -1, 0), d=0.0058, mat="metal_paint", kind="pan")
    # aletas en V invertida (lámina de 1,2 mm con cantos redondos), una arrancada
    k, z = 0, c + 0.035
    blade = [(py, pz) for py, pz in _rrect(0.034, 0.0013, 0.00055, 2)]
    while z < d - 0.03:
        if not (k == 2 and r.random() < 0.6):
            ang_b = -40 + r.uniform(-6, 6)
            ca, sa = math.cos(math.radians(ang_b)), math.sin(math.radians(ang_b))
            prof_b = [(-(py * ca - pz * sa) - 0.006, py * sa + pz * ca) for py, pz in blade]
            _sweep3(leaf, prof_b, [(a + 0.017, 0.0, z), (b - 0.017, 0.0, z)], "metal_paint", up=(0, 0, 1))
        z += 0.034
        k += 1
    # letrero atornillado: placa de 240 x 160 con esquinas redondas y 4 tornillos de cabeza de gota
    a, b, c, d = sign
    _plate_bev(leaf, _rrect(b - a, d - c, 0.01, 3, (a + b) / 2, (c + d) / 2), 0.0006, 0.0031, "metal_paint", face=-1,
               bev=0.0008)
    for (xb, zb) in ((a + 0.012, c + 0.012), (b - 0.012, c + 0.012), (a + 0.012, d - 0.012), (b - 0.012, d - 0.012)):
        _screw(leaf, (xb, -0.0025, zb), (0, -1, 0), d=0.007, mat="metal_paint", kind="pan")
    # manijas, escudos y cilindro
    xh, zl = Wl - 0.065, 1.0
    for dd, yy in ((-1, 0.0), (1, T)):
        _lever(leaf, xh, yy, zl, dd, r, droop=r.uniform(0, 40) if dd < 0 else r.uniform(0, 10))
        _cylinder_rose(leaf, (xh, yy - dd * 0.001, zl - 0.075), (0, dd, 0), R=0.0145, h=0.011, turn=dd > 0)
    # zapata del brazo del cierrapuertas (cara interior, arriba): el cuerpo va en el muro sobre el vano (ver abajo)
    leaf.box((0.15, T - 0.001, Hl - 0.075), (0.2, T + 0.011, Hl - 0.035), "metal_paint", bevel=0.003, seg=2)
    _lathe(leaf, [(0.0, 0.0), (0.0062, 0.0), (0.0062, 0.0065), (0.0045, 0.008), (0.0, 0.0082)], seg=24, mat="metal_rust",
           M=_mat_xy((0.175, T + 0.011, Hl - 0.055), (1, 0, 0), (0, 0, -1)))
    for xb in (0.16, 0.19):
        _screw(leaf, (xb, T + 0.011, Hl - 0.067), (0, 1, 0), d=0.0055, mat="metal_paint", kind="pan")
    # bisagras de 4 1/2" (114 mm) de acero: hojas embutidas en el canto
    zs = (0.22, Hl / 2, Hl - 0.22)
    for z in zs:
        _leafplate(leaf, _mat_xy((0.0013, T - 0.002, z), (0, -1, 0), (-1, 0, 0)), 0.114, 0.028, 0.003, screws=4)
    _leaf_place(mb, leaf, xl0, ys + 0.002, z0, (-0.001, T + 0.005), ang, boxes=_jamb_boxes(w, h, depth, g, 0.036, ys + 0.001, y1))
    _butt_hinges(mb, xl0 - 0.001, ys + 0.002 + T + 0.005, [z + z0 for z in zs], r, ln=0.114, rad=0.0075)
    fh = MB()
    for z in zs:
        _leafplate(fh, _mat_xy((g + 0.035, ys + 0.002 + T + 0.002, z + z0), (0, -1, 0), (1, 0, 0)), 0.114, 0.03, 0.003, screws=4)
    _leafplate(fh, _mat_xy((w - g - 0.0345, ys + 0.004, z0 + zl), (0, 1, 0), (-1, 0, 0)), 0.12, 0.026, 0.003, screws=2, rc=0.004)
    _merge(mb, fh, Rk)
    # cierrapuertas atornillado al muro sobre el vano (cara interior, lado de bisagras): cuerpo, tapas, piñón y el brazo
    # principal partido colgando junto a la jamba (fuera del barrido de la hoja); el antebrazo se perdió
    yb0 = depth + 0.0012
    zc0 = h + 0.035
    # cuerpo de aluminio fundido 280 x 50 x 62 con cantos de radio 9 mm, tapas torneadas de las válvulas y tornillos
    body = _rrect(0.05, 0.062, 0.009, 4, yb0 + 0.025, zc0 + 0.031)
    _sweep3(mb, [(-yy, zz) for yy, zz in body], [(-0.04, 0.0, 0.0), (0.24, 0.0, 0.0)], "metal_paint", up=(0, 0, 1))
    for xe, sg in ((-0.04, -1), (0.24, 1)):
        _lathe(mb, [(0.0, -0.002), (0.0225, -0.002), (0.0225, 0.004), (0.0205, 0.0062), (0.012, 0.007), (0.0, 0.007)], seg=28,
               mat="metal_paint", M=_mat_xy((xe, yb0 + 0.025, zc0 + 0.031), (0, sg, 0), (0, 0, 1)))
    for (xb, zb) in ((-0.02, zc0 + 0.012), (0.22, zc0 + 0.05)):
        _screw(mb, (xb, yb0 + 0.05, zb), (0, 1, 0), d=0.0085, mat="metal_paint", kind="pan")
    px, py = 0.012, yb0 + 0.03
    _lathe(mb, [(0.0, -0.016), (0.0072, -0.016), (0.0072, 0.001), (0.0, 0.001)], seg=24, mat="metal_rust", M=_T(px, py, zc0))
    _lathe(mb, [(0.0, -0.0175), (0.0055, -0.0175), (0.0055, -0.016), (0.0, -0.016)], seg=6, mat="metal_rust", M=_T(px, py, zc0),
           phase=PI / 6)
    arm = MB()   # brazo principal de 22 x 8 con ojos redondos en ambos extremos, partido en el ojo inferior
    arm.box((-0.011, -0.004, -0.198), (0.011, 0.004, -0.012), "metal_paint", bevel=0.0025, seg=2)
    for zz in (0.0, -0.198):
        _lathe(arm, [(0.0, -0.004), (0.011, -0.004), (0.011, 0.004), (0.0, 0.004)], seg=24, mat="metal_paint",
               M=_mat_xy((0.0, 0.0, zz), (1, 0, 0), (0, 0, 1)))
    _lathe(arm, [(0.0, -0.0062), (0.0045, -0.0062), (0.0045, 0.0062), (0.0, 0.0062)], seg=16, mat="metal_rust",
           M=_mat_xy((0.0, 0.0, -0.198), (1, 0, 0), (0, 0, 1)))
    _merge(mb, arm, _T(px, py, zc0 - 0.012) @ _R("Y", r.uniform(4, 12)) @ _R("X", r.uniform(2, 8)))   # cuelga hacia el muro


def door(kind, w, h, depth=0.20, seed=0, open_angle=25, parts=False):
    """Puerta completa para un vano w x h (local: u = 0..w en X, v = 0..h en Z, muro y = 0..depth, v = 0 piso terminado).
    kind: 'flush' (depto, madera), 'double_glazed' (vestíbulo de aluminio), 'plank' (cabaña), 'metal' (servicio).
    La hoja es una pieza SEPARADA girada open_angle grados sobre sus bisagras en u = 0 (hacia +Y, adentro; la de tablones
    abre hacia afuera, -Y). En double_glazed la segunda hoja gira sobre u = w con su propio ángulo.
    El ángulo se reduce solo si el herraje de la hoja chocaría con la jamba o el muro (p. ej. la barra de empuje de
    double_glazed tope hacia ~60°): la hoja se detiene donde se detendría una real.
    parts=False -> MB (todo junto). parts=True -> {'frame': MB, 'leaves': [{'mb': MB de la hoja en posición CERRADA,
    'pivot': (x, y, z), 'axis': (0, 0, ±1), 'angle': grados aplicados}]} para animar la hoja en Three.js (rotar 'mb'
    alrededor de 'pivot' sobre 'axis' por 'angle' reproduce exactamente la puerta del MB combinado)."""
    global _PARTS
    if kind not in ("flush", "double_glazed", "plank", "metal"):
        raise ValueError(f"door kind desconocido: {kind}")
    r = rng(seed)
    mb = MB()
    ang = max(0.0, min(float(open_angle), 92.0 if kind == "plank" else 95.0))
    _PARTS = [] if parts else None
    try:
        {"flush": _door_flush, "double_glazed": _door_glazed, "plank": _door_plank, "metal": _door_metal}[kind](
            mb, w, h, depth, r, ang)
        leaves = _PARTS
    finally:
        _PARTS = None
    if parts:
        return {"frame": mb, "leaves": leaves}
    return mb


# =====================================================================================================================
# CORTINA METÁLICA ENROLLABLE
# =====================================================================================================================
def _slat_profile(p=0.08, bulge=0.010, t=0.0008):
    """Duela curva de lámina (cal. 22, 0,8 mm) en (z, y), contorno cerrado: cara abombada 10 mm hacia -Y y rizo superior
    (hembra) de Ø8,4 donde entra la cola de la duela de arriba (que arranca dentro del rizo). Paso p."""
    C = [(-0.0046, 0.0036), (-0.0016, 0.0012)]
    nf = 8
    for k in range(nf + 1):
        u = k / nf
        C.append((0.0015 + (p - 0.0085 - 0.0015) * u, -bulge * math.sin(PI * u) ** 0.85))
    zc, yc, R = p - 0.0062, 0.0042, 0.0042
    for k in range(1, 10):
        th = -PI / 2 + (PI / 2 + math.radians(205)) * k / 9
        C.append((zc + R * math.cos(th), yc + R * math.sin(th)))
    P = [Vector(c) for c in C]
    L, Rr = [], []
    for i in range(len(P)):
        d = (P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized()
        n = Vector((-d.y, d.x))
        L.append(tuple(P[i] + n * t / 2))
        Rr.append(tuple(P[i] - n * t / 2))
    return L + list(reversed(Rr))


def _shutter_guide(mb, x, side, z0, z1, r):
    """Guía de cortina: canal en U de lámina de 3,2 mm (ángulos de 1 1/2" x 1/8" unidos) con dobleces de radio real, la boca
    abocinada arriba, y taquetes con perno a la jamba. side 0 = jamba izquierda (canal abre hacia +X)."""
    U = [(0.003, 0.035), (0.063, 0.035), (0.063, 0.0382), (0.0062, 0.0382), (0.0062, 0.0818), (0.063, 0.0818), (0.063, 0.085),
         (0.003, 0.085)]
    U = _fillet2d(U, [0.004, 0.0012, 0.0012, 0.0016, 0.0016, 0.0012, 0.0012, 0.004], n=3)
    prof = [(-u if side == 0 else u, y) for u, y in U]
    if side == 0:
        prof = list(reversed(prof))
    mb.sweep(prof, [(x, 0.0, z0), (x, 0.0, z1)], mat="metal_paint", normal=(0, 1, 0))
    sg = 1 if side == 0 else -1
    for zz in [0.25 + (z1 - 0.4) * k / 3 for k in range(4)]:
        _bolt(mb, (x + sg * 0.0062, 0.06, zz), (sg, 0, 0), r=0.0065, ln=0.0055)


def rolling_shutter(w, h, seed=0, dent=0.5, open_frac=0.0):
    """Cortina metálica enrollable montada DENTRO del vano (local u 0..w, v 0..h, plano de lamas en y = 0,06):
    guías en U de lámina de 3,2 mm contra las jambas, caja de enrollado (0,32 m superiores) con faldón de lámina abollable
    de borde enrollado, tapas laterales con chumacera y el rollo de duelas visible por la ranura; duelas curvas de 8 cm
    (lámina de 0,8 mm, cara abombada 10 mm y rizo de engrane), barra inferior de doble ángulo con hule, chapa central con
    pasadores a las guías, jaladeras de varilla y porta-candados.
    dent 0..1: abolladuras (ruido + golpes) y lamas torcidas; open_frac 0..1 sube la cortina."""
    r = rng(seed)
    mb = MB()
    p = 0.08
    yc = 0.06
    hb = 0.32
    zbox = h - hb
    for side in (0, 1):
        _shutter_guide(mb, 0.0 if side == 0 else w, side, -0.005, zbox + 0.03, r)
    # caja: faldón frontal (lámina abollable con el borde inferior enrollado), tapa inferior con ranura, tapa superior y laterales
    fb, frings, fnx = _slab(w - 0.008, hb - 0.006, 0.0012, nx=max(6, int(w / 0.12)), nz=6, c=0.0004, mat="metal_paint")
    fd = _dents(r, int(3 + 5 * dent), 0.1, w - 0.1, 0.0, hb, rad=(0.05, 0.16), depth=(0.003, 0.018 * dent + 0.003))
    for v in fb.bm.verts:
        v.co.y += fd(v.co.x, v.co.z)
    _merge(mb, fb, _T(0.004, 0.009, zbox))
    _lathe(mb, [(0.0, 0.0), (0.0042, 0.0), (0.0042, w - 0.012), (0.0, w - 0.012)], seg=16, mat="metal_paint",
           M=_T(0.006, 0.0118, zbox + 0.003) @ _R("Y", 90))
    mb.box((0.004, 0.012, zbox), (w - 0.004, 0.038, zbox + 0.004), "metal_paint", bevel=0.0012, seg=2)
    mb.box((0.004, 0.084, zbox), (w - 0.004, 0.19, zbox + 0.004), "metal_paint", bevel=0.0012, seg=2)
    mb.box((0.004, 0.011, h - 0.007), (w - 0.004, 0.19, h - 0.003), "metal_paint", bevel=0.0012, seg=2)
    zax = h - hb / 2 - 0.01
    for xa, sg in ((0.004, 1), (w - 0.008, -1)):
        mb.box((xa, 0.0115, zbox + 0.0045), (xa + 0.004, 0.19, h - 0.0075), "metal_paint", bevel=0.0012, seg=2)
        xs_ = xa + (0.004 if sg > 0 else 0.0)
        _lathe(mb, [(0.0, -0.0005), (0.034, -0.0005), (0.034, 0.008), (0.031, 0.011), (0.022, 0.012), (0.0, 0.012)], seg=32,
               mat="metal_paint", M=_mat_xy((xs_, 0.1, zax), (0, 0, 1), (0, sg, 0)) @ _R("X", 0))
        for k in range(4):
            a_ = PI / 4 + PI / 2 * k
            _bolt(mb, (xs_, 0.1 + 0.026 * math.cos(a_), zax + 0.026 * math.sin(a_)), (sg, 0, 0), r=0.005, ln=0.005)
    # rollo de duelas: cilindro acanalado (una costura por duela) sobre el eje del tambor
    roll = 0.05 + 0.035 * max(0.0, min(1.0, open_frac))   # rollo de lamas: cabe en la caja (y 0,011–0,19)
    nr = 72
    nseam = max(12, int(2 * PI * roll / p))
    rp = [(roll * (1.0 - 0.06 * max(0.0, math.cos(PI * nseam * k / nr)) ** 8) * math.cos(2 * PI * k / nr),
           roll * (1.0 - 0.06 * max(0.0, math.cos(PI * nseam * k / nr)) ** 8) * math.sin(2 * PI * k / nr)) for k in range(nr)]
    with mb.soft():
        _sweep3(mb, list(reversed(rp)), [(0.02, 0.1, zax), (w - 0.02, 0.1, zax)], "metal_paint", up=(0, 0, 1))
    _lathe(mb, [(0.0, 0.0), (0.024, 0.0), (0.024, w - 0.016), (0.0, w - 0.016)], seg=24, mat="metal_rust",
           M=_T(0.008, 0.1, zax) @ _R("Y", 90))
    # cortina
    hc = zbox + 0.01
    zb0 = max(0.0, min(0.95, open_frac)) * (hc - 0.3)
    cur = MB()
    bar_h = 0.06
    n = max(1, int((hc - zb0 - bar_h) / p))
    prof = _slat_profile(p)
    ns = max(4, int(round(w / max(0.15, w / 30.0))))
    xs = [0.03 + (w - 0.06) * k / ns for k in range(ns + 1)]
    path = [(x, 0.0, 0.0) for x in xs]
    popped = int(r.integers(0, max(1, n // 3))) if r.random() < 0.35 + 0.5 * dent else -1
    for k in range(n):
        s = MB()
        with s.soft():
            s.sweep(prof, path, mat="metal_paint", normal=(0, 1, 0))
        z = zb0 + bar_h + k * p
        th = 0.0
        if k == popped:                          # lama zafada de su engrane: gira sobre su gancho hacia afuera
            th = -r.uniform(18, 32)
        elif r.random() < 0.15 * dent + 0.02:    # lama torcida
            th = r.uniform(-12, 12) * dent
        if th:
            for v in s.bm.verts:   # el giro se anula dentro de las guías (la lama sigue presa en sus extremos)
                a = math.radians(th) * _smooth(min(v.co.x - 0.03, w - 0.03 - v.co.x) / 0.35)
                yy, zz = v.co.y, v.co.z - p
                v.co.y, v.co.z = yy * math.cos(a) - zz * math.sin(a), yy * math.sin(a) + zz * math.cos(a) + p
        _merge(cur, s, _T(0, yc, z) @ _about((w / 2, 0, p / 2), _R("Y", r.uniform(-0.2, 0.2))))
    # barra inferior: doble ángulo de 1 1/2" con hule de bulbo; chapa central con pasadores; jaladeras; porta-candados
    bp = _fillet2d([(0.0, -0.014), (0.055, -0.014), (0.055, 0.016), (0.008, 0.016), (0.008, 0.012), (0.0, 0.006)],
                   [0.0015, 0.002, 0.002, 0.0012, 0.0012, 0.0015], n=2)
    nb0 = len(cur.bm.verts)
    cur.sweep(bp, [(x, 0.0, 0.0) for x in xs], mat="metal_paint", normal=(0, 1, 0))
    cur.bm.verts.ensure_lookup_table()
    for v in list(cur.bm.verts)[nb0:]:
        v.co.y += yc
        v.co.z += zb0 + 0.004
    with cur.soft():
        cur.sweep(_rrect(0.016, 0.009, 0.004, 3), [(x, 0.0, 0.0) for x in (0.035, w - 0.035)], mat="rubber", normal=(0, 1, 0))
    cur.bm.verts.ensure_lookup_table()
    nb1 = len(cur.bm.verts)
    for v in list(cur.bm.verts)[nb1 - 2 * 4 * 4:]:
        v.co.y += yc
        v.co.z += zb0 + 0.0025
    xc = w / 2
    cur.box((xc - 0.045, yc - 0.03, zb0 + 0.008), (xc + 0.045, yc - 0.0135, zb0 + 0.06), "metal_paint", bevel=0.004, seg=2)
    _cylinder_rose(cur, (xc, yc - 0.03, zb0 + 0.034), (0, -1, 0), R=0.0125, h=0.008, mat="metal_paint")
    for sx in (-1, 1):   # pasadores hacia las guías (varilla de 1/2" con su guía doblada) y jaladeras de varilla
        x0_, x1_ = xc + sx * 0.045, xc + sx * (w / 2 - 0.02)
        _lathe(cur, [(0.0, 0.0), (0.0062, 0.0), (0.0062, abs(x1_ - x0_) - 0.002), (0.0045, abs(x1_ - x0_)), (0.0, abs(x1_ - x0_))],
               seg=16, mat="metal_rust", M=_T(x0_, yc - 0.022, zb0 + 0.03) @ _R("Y", 90 * sx))
        for xg in (xc + sx * 0.25, xc + sx * (w / 2 - 0.25)):
            cur.box((xg - 0.014, yc - 0.031, zb0 + 0.021), (xg + 0.014, yc - 0.0135, zb0 + 0.039), "metal_rust", bevel=0.0025,
                    seg=2)
        xh = xc + sx * w * 0.3
        _rtube(cur, [(xh - 0.05, yc - 0.012, zb0 + 0.032), (xh - 0.05, yc - 0.05, zb0 + 0.032), (xh + 0.05, yc - 0.05, zb0 + 0.032),
                     (xh + 0.05, yc - 0.012, zb0 + 0.032)], 0.0065, "metal_rust", seg=16, rbend=0.016)
        # porta-candado junto a la guía: oreja con ojo en la barra (el candado lo cortaron)
        xq = xc + sx * (w / 2 - 0.12)
        _plate_bev(cur, _rrect(0.04, 0.05, 0.008, 3, xq, zb0 + 0.03), yc - 0.0135, 0.005, "metal_rust", face=-1, bev=0.0012)
        _lathe(cur, [(0.009, -0.0025), (0.015, -0.0025), (0.016, -0.0015), (0.016, 0.0015), (0.015, 0.0025), (0.009, 0.0025),
                     (0.009, -0.0025)], seg=24, mat="metal_rust", M=_T(xq, yc - 0.034, zb0 + 0.012), caps=False)
    # abolladuras, panza y esquina inferior forzada
    nz_ = _Noise(r, wl=0.7, octaves=3, waves=3)
    dn = _dents(r, int(4 + 12 * dent), 0.15, w - 0.15, zb0 + 0.05, hc - 0.1, rad=(0.07, 0.3), depth=(0.003, 0.04 * dent + 0.006))
    kicks = [(_uni(r, 0.3, w - 0.3), zb0 + r.uniform(0.2, 1.3), r.uniform(0.14, 0.32), r.uniform(0.025, 0.06) * dent)
             for _ in range(int(1 + 3 * dent))]
    belly = r.uniform(-0.03, 0.03) * dent
    pxc = r.uniform(0.3, 0.7) * w
    pry = r.uniform(0.05, 0.13) * dent if r.random() < 0.75 else 0.0
    for v in cur.bm.verts:
        x, z = v.co.x, v.co.z
        ex = _smooth(min(x - 0.03, w - 0.03 - x) / 0.25)   # en las guías la cortina queda recta
        d = dn(x, z) + 0.005 * dent * nz_(x, z) + belly * math.sin(PI * min(max(x / w, 0), 1))
        for kx, kz, kr, kd in kicks:   # patada: cono con pliegue (lamas pandeadas)
            q = math.hypot((x - kx) / kr, (z - kz) / (kr * 0.55))
            d += kd * max(0.0, 1.0 - q) ** 1.5
        d -= pry * math.exp(-((x - pxc) / 0.5) ** 2) * _smooth((zb0 + 0.55 - z) / 0.55)
        v.co.y += d * ex
    _declump(cur)
    _merge(mb, cur)
    return mb


# =====================================================================================================================
# CELOSÍA DE BLOQUES (pieza firma de APT_A)
# =====================================================================================================================
_BB_PATTERNS = {
    "4sq": ([0.0, 0.025, 0.09, 0.11, 0.175, 0.2], {(1, 1), (1, 3), (3, 1), (3, 3)}),
    "cross": ([0.0, 0.022, 0.074, 0.126, 0.178, 0.2], {(2, 1), (2, 2), (2, 3), (1, 2), (3, 2)}),
    "nine": ([0.0, 0.02, 0.065, 0.0775, 0.1225, 0.135, 0.18, 0.2], {(i, j) for i in (1, 3, 5) for j in (1, 3, 5)}),
}


def _bb_block(dst, pattern, D, M, r, broken=0, jit=0.0012, bevel=0.004):
    """Bloque de celosía 0,20 x 0,20 x D con calado REAL: malla por celdas (sólido/hueco), soldada y cerrada.
    broken > 0 arranca una esquina (celdas de borde) con contorno dentado. Se evitan pellizcos diagonales (manifold)."""
    xs, holes = _BB_PATTERNS[pattern]
    n = len(xs) - 1
    gone = set()
    if broken:
        ci, cj = r.choice([0, n - 1]), r.choice([0, n - 1])
        rad = r.uniform(1.0, 2.6)
        gone = {(i, j) for i in range(n) for j in range(n) if math.hypot(i - ci, j - cj) < rad and (i, j) not in holes}

    def solid(i, j):
        return 0 <= i < n and 0 <= j < n and (i, j) not in holes and (i, j) not in gone

    changed = True
    while changed:   # quitar pellizcos diagonales
        changed = False
        for i in range(1, n):
            for j in range(1, n):
                a, b, c, d = solid(i - 1, j - 1), solid(i, j - 1), solid(i - 1, j), solid(i, j)
                if (a and d and not b and not c) or (b and c and not a and not d):
                    gone.add((i - 1, j - 1) if a else (i, j - 1))
                    changed = True
    rough = set()
    for (i, j) in gone:
        rough |= {(i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1)}
    V = {}
    mb = MB()
    M_final, M = M, None

    def vert(i, j, s):
        key = (i, j, s)
        if key not in V:
            x, z = xs[i], xs[j]
            y = 0.0 if s == 0 else D
            jx, jz, jy = r.normal(0, jit), r.normal(0, jit), r.normal(0, jit * 0.6)
            if (i, j) in rough and 0 < i < n and 0 < j < n or ((i, j) in rough and (i in (0, n)) != (j in (0, n))):
                jx, jz = r.normal(0, 0.006), r.normal(0, 0.006)
                jy += r.uniform(0.0, 0.01) * (1 if s == 0 else -1)
            V[key] = mb._verts([(x + jx, y + jy, z + jz)], M)[0]
        return V[key]

    for i in range(n):
        for j in range(n):
            if not solid(i, j):
                continue
            mb.face([vert(i, j, 0), vert(i + 1, j, 0), vert(i + 1, j + 1, 0), vert(i, j + 1, 0)], "concrete")
            mb.face([vert(i, j, 1), vert(i, j + 1, 1), vert(i + 1, j + 1, 1), vert(i + 1, j, 1)], "concrete")
            if not solid(i - 1, j):
                mb.face([vert(i, j, 0), vert(i, j + 1, 0), vert(i, j + 1, 1), vert(i, j, 1)], "concrete")
            if not solid(i + 1, j):
                mb.face([vert(i + 1, j, 0), vert(i + 1, j, 1), vert(i + 1, j + 1, 1), vert(i + 1, j + 1, 0)], "concrete")
            if not solid(i, j - 1):
                mb.face([vert(i, j, 0), vert(i, j, 1), vert(i + 1, j, 1), vert(i + 1, j, 0)], "concrete")
            if not solid(i, j + 1):
                mb.face([vert(i, j + 1, 0), vert(i + 1, j + 1, 0), vert(i + 1, j + 1, 1), vert(i, j + 1, 1)], "concrete")
    if bevel > 0:   # chaflán real en el contorno exterior (frente, dorso y aristas de esquina); lo roto queda vivo
        B = xs[-1]
        e_ = 0.004

        def onrim(v):
            return (v.co.x < e_ or v.co.x > B - e_ or v.co.z < e_ or v.co.z > B - e_)

        edges = []
        for ed in mb.bm.edges:
            a, b = ed.verts
            if not (onrim(a) and onrim(b)):
                continue
            ka = (abs(a.co.x) < e_ or abs(a.co.x - B) < e_, abs(a.co.z) < e_ or abs(a.co.z - B) < e_)
            if abs(a.co.y - b.co.y) < 0.02 or (ka[0] and ka[1]):
                edges.append(ed)
        if edges:
            res = bmesh.ops.bevel(mb.bm, geom=edges, offset=bevel, segments=1, profile=0.5, affect="EDGES", clamp_overlap=True)
            for f in res["faces"]:
                f.material_index = mb.mi("concrete")
    _merge(dst, mb, M_final)


def breeze_block_screen(w, h, seed=0, missing=0.05, pattern=None, y0=0.0, bevel=0.004):
    """Celosía de bloques de concreto 0,20 x 0,20 x 0,10 con calado real en cada bloque, junta de mortero de 1 cm
    rehundida 8 mm, bloques rotos y faltantes. Local: u 0..w, v 0..h, bloques en y = y0..y0+0,10 (cara exterior en y0).
    pattern: '4sq' (4 cuadros, por defecto), 'cross' (cruz), 'nine' (9 cuadros) o None = '4sq'.
    bevel: chaflán del contorno de cada bloque (0,004 m; 0 = aristas vivas y ~35 % menos triángulos para lejanía).
    Costo por bloque con bisel: 4sq ~230 tris, cross ~215, nine ~390 (sin bisel: 160 / 140 / 290)."""
    r = rng(seed)
    pattern = pattern or "4sq"
    mb = MB()
    B, J, D = 0.2, 0.01, 0.1
    P = B + J
    nx = max(1, int((w - J) // P))
    nz = max(1, int((h - J) // P))
    mx = (w - (nx * P - J)) / 2
    mz = J
    for j in range(nz):
        for i in range(nx):
            if r.random() < missing:
                continue
            x0, z0 = mx + i * P, mz + j * P
            M = _T(x0 + r.normal(0, 0.0012), y0 + r.normal(0, 0.0015), z0 + r.normal(0, 0.0008)) @ \
                _about((B / 2, 0, B / 2), _R("Y", r.normal(0, 0.35)))
            _bb_block(mb, pattern, D, M, r, broken=int(r.random() < 1.5 * missing + 0.04), bevel=bevel)
    # mortero: tendeles corridos, llagas por hilada y rellenos perimetrales (rehundido 8 mm, metido 1 mm en los bloques)
    ya, yb = y0 + 0.008, y0 + D - 0.008
    top = mz + nz * P - J
    for j in range(nz + 1):
        za = mz + j * P - J - 0.001 if j > 0 else -0.004
        zb_ = mz + j * P + 0.001 if j < nz else min(h - 0.003, top + J + 0.001)
        if j == nz and h - 0.003 - top > J:
            zb_ = h - 0.003
        mb.box((0.003, ya + r.uniform(0, 0.003), za), (w - 0.003, yb, zb_), "mortar")
        if j == nz:
            break
    for j in range(nz):
        z0, z1 = mz + j * P + 0.0012, mz + j * P + B - 0.0012
        for i in range(nx + 1):
            xa = mx + i * P - J - 0.001 if i > 0 else 0.003
            xb = mx + i * P + 0.001 if i < nx else w - 0.003
            mb.box((xa, ya + r.uniform(0, 0.004), z0), (xb, yb, z1), "mortar")
    return mb


# =====================================================================================================================
# REJA DE SEGURIDAD
# =====================================================================================================================
def security_grille(w, h, seed=0, bottom=0.05, y0=0.006):
    """Reja de ventana dentro del vano (local u 0..w, v 0..h, plano y = y0..y0+0,03): marco de ángulo 30x30x4, barras
    redondas Ø14 cada ~12 cm, dos soleras horizontales, anclas empotradas en las jambas. Oxidada; una pareja de barras
    abierta a la fuerza y, a veces, una barra cortada. bottom = holgura inferior (deja libre el alféizar)."""
    r = rng(seed)
    mb = MB()
    g = 0.006
    L = [(0.0, y0), (0.03, y0), (0.03, y0 + 0.004), (0.004, y0 + 0.004), (0.004, y0 + 0.03), (0.0, y0 + 0.03)]
    fr = MB()
    fr.sweep(L, _rect_path(g, bottom, w - g, h - g, step=0.4, c=0.04), mat="metal_rust", normal=(0, 1, 0), closed_path=True)
    Rk = _rack(fr, w, h, r, deg=0.25, sag=0.002)
    _merge(mb, fr)
    for z in (bottom + 0.15, (bottom + h) / 2, h - 0.15):   # anclas a las jambas
        for x0, x1 in ((-0.03, g + 0.002), (w - g - 0.002, w + 0.03)):
            mb.box((x0, y0 + 0.012, z - 0.02), (x1, y0 + 0.017, z + 0.02), "metal_rust")
    framed, mb = mb, MB()   # soleras, barras y soldaduras: se montan con el mismo descuadre del marco
    zb, zt = bottom + 0.002, h - g - 0.002
    hs = [bottom + (h - bottom) * 0.33, bottom + (h - bottom) * 0.67]
    for z in hs:
        mb.box((g + 0.002, y0 + 0.008, z - 0.016), (w - g - 0.002, y0 + 0.013, z + 0.016), "metal_rust")
    nb = max(2, int(round((w - 2 * g) / 0.12)) - 1)
    xs = [g + (w - 2 * g) * (k + 1) / (nb + 1) for k in range(nb)]
    yb = y0 + 0.02
    pair = int(r.integers(0, nb - 1)) if nb > 1 else -1
    cutb = int(r.integers(0, nb)) if r.random() < 0.5 else -1
    zmid = _uni(r, hs[0] + 0.1, hs[1] - 0.1)
    for k, x in enumerate(xs):
        if k == cutb and k not in (pair, pair + 1):   # barra cortada con segueta: quedan muñones
            mb.cyl((x, yb, zb), (x, yb, zb + r.uniform(0.04, 0.09)), 0.007, seg=8, mat="metal_rust")
            mb.cyl((x, yb, zt - r.uniform(0.04, 0.12)), (x, yb, zt), 0.007, seg=8, mat="metal_rust")
            continue
        if k in (pair, pair + 1):   # pareja de barras separadas y empujadas hacia afuera entre las soleras
            sx = -1 if k == pair else 1
            spread = r.uniform(0.03, 0.06)
            out = r.uniform(0.01, 0.05)
            a_, b_ = hs[0] + 0.018, hs[1] - 0.018      # las soleras sujetan la barra: la curva vive entre ellas
            sm = (zmid - a_) / (b_ - a_)
            zs_ = [zb, a_ - 0.03] + [a_ + (b_ - a_) * i / 14 for i in range(15)] + [b_ + 0.03, zt]
            pts = []
            for z in zs_:
                s_ = (z - a_) / (b_ - a_)
                if 0.0 < s_ < 1.0:   # campana asimétrica con pico en zmid y tangente nula en las soleras (sin quiebres)
                    q = 0.5 * s_ / sm if s_ < sm else 0.5 + 0.5 * (s_ - sm) / (1 - sm)
                    f = math.sin(PI * q) ** 2
                else:
                    f = 0.0
                pts.append((x + sx * spread * f, yb - out * f, z))
            mb.tube(pts, 0.007, seg=8, mat="metal_rust")
        else:   # barra con leve flecha (nada perfectamente recto)
            wob, woy = r.normal(0, 0.0015), r.normal(0, 0.0012)
            pts = [(x + wob * math.sin(PI * t / 4), yb + woy * math.sin(PI * t / 4), zb + (zt - zb) * t / 4) for t in range(5)]
            mb.tube(pts, 0.007, seg=8, mat="metal_rust")
        # cordones de soldadura donde la barra toca las soleras y el ángulo del marco (gotas achatadas, irregulares)
        if not (k == cutb and k not in (pair, pair + 1)):
            for zw in (hs[0], hs[1]):   # un cordón por cruce, del lado que tocó al soldador
                zz = zw + (1 if r.random() < 0.6 else -1) * 0.0175
                mb.cyl((x - 0.0105, yb - 0.0045, zz), (x + 0.0105, yb - 0.0045, zz), 0.0032 * r.uniform(0.8, 1.2), seg=5,
                       mat="metal_rust", r1=0.0026)
            for zz in (bottom + 0.0055, h - g - 0.0055):
                mb.cyl((x - 0.0095, yb + 0.0005, zz), (x + 0.0095, yb + 0.0005, zz), 0.0035 * r.uniform(0.8, 1.2), seg=4,
                       mat="metal_rust", r1=0.0028)
    _merge(framed, mb, Rk)
    return framed
