"""services.py — GRUPO G4 · SERVICIOS Y PROPS del kit modular BLACKISLE.

Todas las funciones públicas devuelven un `MB` (bmesh de kit.common) listo para `MB.join(pieza, matriz)`.

Convención de montaje (salvo que la función diga otra cosa):
  · Piezas de MURO (A/C, medidor, lámparas, buzones, gabinete, letrero, conduit, antena satelital): el origen está en la
    CARA EXTERIOR DEL MURO (plano y = 0) y el cuerpo sale hacia -Y (la fachada mira a -Y). Nada toca el plano y = 0:
    las placas de apoyo quedan a 1–2 mm (y <= -0,001); pernos, tacos, cables y tubos que "entran" al muro cruzan y = 0
    y terminan dentro del muro (y > 0), por eso no se ven por detrás si el muro es sólido.
  · Piezas de AZOTEA (antena yagi, tinaco): origen en la base, sobre la losa (z = 0), Z arriba.
  · Cables / tendedero / cortina: ver la docstring de cada función (coordenadas de los puntos de anclaje).

Láminas intencionales (aristas abiertas a propósito; en Three.js usar `side: DoubleSide`):
  · material 'fabric': prendas del tendedero y cortinas rotas (planos de una cara con pliegues). Es la ÚNICA lámina.
Todo lo demás son sólidos cerrados (0 aristas no-manifold): las chapas (carcasas, puertas, aspas, pantallas, tanque) se
construyen como superficie y se les da espesor con `bmesh.ops.solidify`; el vidrio roto son esquirlas con espesor.

Escala (brief §4.2): A/C de ventana 0,60 × 0,40 × 0,45 · split exterior 0,80 × 0,55 × 0,28 · medidor 0,36 × 0,50 × 0,17 ·
cable de acometida Ø 9 mm · conduit EMT 3/4" (Ø 23 mm) · tinaco 1100 L Ø 1,10 × 1,37 · ladrillo 0,24 × 0,06 × 0,12 (junta 1 cm).
Triángulos medidos (barrido de 8 semillas, tests/test_G4_servicios_dano.py imprime los de la vitrina):
  ac_unit window 17,9–18,0 k · split_outdoor 28,2–28,4 k · box_old 17,0–17,1 k · cable_bundle (3 anclajes) 12–26 k ·
  conduit 6,5–8,9 k · meter_box 9,9–10,8 k · light_fixture wall 3,4–3,6 k / bracket 2,9–3,0 k · tv_antenna 7,9–8,1 k ·
  satellite_dish 5,1 k · water_tank 16,5–16,7 k · mailboxes(n) 10–28 k · extinguisher_cabinet 4,9 k ·
  sign_torn 5–14 k (según w × h) · laundry_line 2,5–13 k (según largo) · curtain_torn 5–20 k (según w × h).
Todo cabe en 0 aristas no-manifold fuera de 'fabric' (verificado en 168 combinaciones semilla/tamaño), sin caras de área
0 ni vértices sueltos, y es determinista por semilla.
"""
import contextlib
import math

import bpy  # noqa: F401  (bmesh/mathutils solo existen después de importar bpy)
import bmesh
from mathutils import Matrix, Vector
from mathutils import noise as _mnoise
from mathutils.kdtree import KDTree

from kit.common import MB, rng

PI = math.pi
LAMINA_MATS = ("fabric",)


# =====================================================================================================================
# utilidades de transformación y ruido
# =====================================================================================================================
def _v(p):
    return Vector((float(p[0]), float(p[1]), float(p[2])))


def _T(x=0.0, y=0.0, z=0.0):
    if not isinstance(x, (int, float)):
        return Matrix.Translation(_v(x))
    return Matrix.Translation((x, y, z))


def _R(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, axis)


def _about(p, M):
    """M aplicada alrededor del punto p."""
    p = _v(p)
    return Matrix.Translation(p) @ M @ Matrix.Translation(-p)


def _frame(origin, z_axis, x_hint=(1.0, 0.0, 0.0)):
    """Matriz cuyo eje Z local apunta a `z_axis` (X local lo más parecido a `x_hint`)."""
    Z = _v(z_axis).normalized()
    X = _v(x_hint)
    X = X - Z * X.dot(Z)
    if X.length < 1e-6:
        X = Z.orthogonal()
    X.normalize()
    Y = Z.cross(X)
    M = Matrix((
        (X.x, Y.x, Z.x, 0.0),
        (X.y, Y.y, Z.y, 0.0),
        (X.z, Y.z, Z.z, 0.0),
        (0.0, 0.0, 0.0, 1.0)))
    return Matrix.Translation(_v(origin)) @ M


def _basis(origin, X, Y, Z):
    """Matriz con columnas arbitrarias (permite cizalla)."""
    X, Y, Z, o = _v(X), _v(Y), _v(Z), _v(origin)
    return Matrix((
        (X.x, Y.x, Z.x, o.x),
        (X.y, Y.y, Z.y, o.y),
        (X.z, Y.z, Z.z, o.z),
        (0.0, 0.0, 0.0, 1.0)))


def _merge(dst, src, m=None):
    """Une src en dst con la matriz m y libera src."""
    dst.join(src, m)
    src.bm.free()
    return dst


def _xform(mb, m):
    for v in mb.bm.verts:
        v.co = m @ v.co


def _smooth(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def _lerp(a, b, t):
    return a + (b - a) * t


class _Nz:
    """Ruido Perlin determinista (mathutils.noise) con desfase sacado de rng(seed). Devuelve ~[-1, 1]."""

    def __init__(self, r):
        self.o = Vector((float(r.uniform(-400, 400)), float(r.uniform(-400, 400)), float(r.uniform(-400, 400))))

    def __call__(self, p, freq=1.0, octaves=1):
        q = _v(p) * freq + self.o
        if octaves == 1:
            return _mnoise.noise(q)
        s, a, tot = 0.0, 1.0, 0.0
        for _ in range(octaves):
            s += a * _mnoise.noise(q)
            tot += a
            q = q * 2.03
            a *= 0.5
        return s / tot * 1.4


def _declump(mb, dist=0.00016):
    """Separa vértices de PIEZAS DISTINTAS (componentes conexas) que quedaron a menos de `dist`, para que el
    remove_doubles de MB.finish() (0,1 mm) no las suelde y cree aristas no-manifold. Mueve 0,3 mm (invisible)."""
    bm = mb.bm
    vs = list(bm.verts)
    if not vs:
        return 0
    bm.verts.index_update()
    parent = list(range(len(vs)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for e in bm.edges:
        a, b = find(e.verts[0].index), find(e.verts[1].index)
        if a != b:
            parent[a] = b
    comp = [find(i) for i in range(len(vs))]
    kd = KDTree(len(vs))
    for i, v in enumerate(vs):
        kd.insert(v.co, i)
    kd.balance()
    push = Vector((0.00014, -0.00017, 0.0002))  # |push| = 0,3 mm: > 0,16 + 0,1 mm y sin torcer hilos de 0,7 mm
    moved = 0
    done = set()
    for i, v in enumerate(vs):
        if i in done:
            continue
        for (_, j, _) in kd.find_range(v.co, dist):
            if j != i and comp[j] != comp[i] and j not in done:
                vs[j].co += push
                done.add(j)
                moved += 1
    return moved


# =====================================================================================================================
# NIVEL DE DETALLE (parámetro `detail` = 'high' | 'mid' | 'low' de todas las funciones públicas)
# =====================================================================================================================
DETAIL_LEVELS = ("high", "mid", "low")


class _LOD:
    level = "high"


@contextlib.contextmanager
def _detail(level):
    """Activa un nivel de detalle mientras se construye una pieza (cada función pública lo hace con su `detail`).
      · 'high': geometría de primer plano (< 3 m), idéntica a la versión aprobada.
      · 'mid' : 3–6 m. Sin biseles < 5 mm, tubos y cilindros con ~2/3 de los lados, polilíneas simplificadas
                (Douglas-Peucker, tolerancia 0,35 × radio), retículas de chapa a paso doble, tornillos simplificados.
      · 'low' : > 6 m / instancias repetidas. Sin biseles < 12 mm, tubos de 3–4 lados, tolerancia 1,2 × radio,
                retículas a paso ×5, sin tornillería chica ni puntas deshiladas.
    El nivel NO cambia el consumo de la semilla: con la misma semilla los 3 niveles tienen el mismo estado (puertas,
    roturas, flechas, piezas faltantes), así el constructor puede cambiar de LOD sin que la pieza 'salte'."""
    if level not in DETAIL_LEVELS:
        raise ValueError(f"detail debe ser uno de {DETAIL_LEVELS}, no {level!r}")
    prev = _LOD.level
    _LOD.level = level
    try:
        yield level
    finally:
        _LOD.level = prev


def _lv(high, mid, low):
    """Valor según el nivel de detalle activo."""
    lv = _LOD.level
    return high if lv == "high" else (mid if lv == "mid" else low)


def _sseg(seg, r=None):
    """Lados de tubos y cilindros según el nivel (high tal cual · mid × 0,67 · low × 0,45; mínimo 4, o 3 en hilos < 4 mm)."""
    lv = _LOD.level
    if lv == "high":
        return seg
    lo = 3 if (r is not None and r < 0.004) else 4
    return max(lo, int(round(seg * (0.67 if lv == "mid" else 0.45))))


def _dp(P, tol):
    """Douglas-Peucker sobre una polilínea abierta (lista de Vector): índices que se conservan (extremos siempre)."""
    n = len(P)
    if n <= 2 or tol <= 0:
        return list(range(n))
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        A, AB = P[a], P[b] - P[a]
        L2 = AB.length_squared
        dmax, imax = -1.0, -1
        for i in range(a + 1, b):
            AP = P[i] - A
            t = 0.0 if L2 < 1e-18 else max(0.0, min(1.0, AP.dot(AB) / L2))
            d = (AP - AB * t).length
            if d > dmax:
                dmax, imax = d, i
        if dmax > tol:
            keep[imax] = True
            stack.append((a, imax))
            stack.append((imax, b))
    return [i for i in range(n) if keep[i]]


def _simplify(P, r, closed=False):
    """Índices de la polilínea P que sobreviven al nivel activo (tolerancia de cuerda relativa al radio del tubo)."""
    tol = _lv(0.0, max(0.35 * r, 0.0006), max(1.2 * r, 0.002))
    n = len(P)
    if tol <= 0 or n <= 2:
        return list(range(n))
    if not closed:
        return _dp(P, tol)
    if n <= 6:
        return list(range(n))
    h = n // 2
    a = _dp(P[:h + 1], tol)
    b = _dp(P[h:] + [P[0]], tol)
    idx = sorted(set(a + [h + i for i in b[:-1]]))
    if len(idx) < 4:
        idx = sorted({int(round(k * n / 4)) % n for k in range(4)})
    return idx


def _box(mb, mn, mx, mat="concrete", bevel=0.0, seg=2, m=None):
    """MB.box con bisel según el nivel: mid quita biseles < 5 mm (el resto a 1 segmento), low quita los < 12 mm."""
    if bevel > 0 and _LOD.level != "high":
        if bevel < _lv(0.0, 0.005, 0.012):
            bevel = 0.0
        else:
            seg = 1
    return mb.box(mn, mx, mat, bevel=bevel, seg=seg, m=m)


def _cyl(mb, p0, p1, r, seg=8, mat="metal_rust", caps=True, r1=None):
    """MB.cyl con los lados según el nivel."""
    return mb.cyl(p0, p1, r, seg=_sseg(seg, r), mat=mat, caps=caps, r1=r1)


def _keep_idx(n, step):
    """Índices 0, step, 2·step, … y siempre el último."""
    idx = list(range(0, n, step))
    if idx[-1] != n - 1:
        idx.append(n - 1)
    return idx


def _sub_grid(grid, si, sj):
    """Submuestrea una rejilla grid[i][j] (columnas × filas) conservando bordes."""
    if si <= 1 and sj <= 1:
        return grid
    I, J = _keep_idx(len(grid), si), _keep_idx(len(grid[0]), sj)
    return [[grid[i][j] for j in J] for i in I]


def _sheet_lod(mb, grid, mat, skip=None, wrap=False, steps=((1, 1), (2, 2), (3, 3))):
    """_sheet con la rejilla submuestreada según el nivel (steps = pasos (columnas, filas) para high/mid/low).
    Una celda gruesa se salta si CUALQUIERA de las celdas finas que cubre se salta (desgarros y huecos no se cierran)."""
    si, sj = _lv(*steps)
    if (si <= 1 and sj <= 1) or wrap:
        return _sheet(mb, grid, mat, skip, wrap)
    I, J = _keep_idx(len(grid), si), _keep_idx(len(grid[0]), sj)
    g2 = [[grid[i][j] for j in J] for i in I]
    sk2 = None
    if skip is not None:
        def sk2(a, b):
            return any(skip(i, j) for i in range(I[a], I[a + 1]) for j in range(J[b], J[b + 1]))
    return _sheet(mb, g2, mat, sk2)


# =====================================================================================================================
# primitivas propias del grupo (todas cerradas salvo que se diga)
# =====================================================================================================================
def _tube(mb, pts, r, seg=6, mat="cable", caps=True, radii=None, closed=False, up=None, lod=True):
    """Tubo por una polilínea (transporte paralelo). closed=True: anillo cerrado (usar `up` = normal del plano).
    lod=True: en 'mid'/'low' reduce los lados (_sseg) y simplifica la polilínea (_simplify)."""
    P, RR = [], []
    for i, p in enumerate(pts):
        q = _v(p)
        if not P or (q - P[-1]).length > 2e-4:
            P.append(q)
            RR.append(radii[i] if radii is not None else r)
    if closed and len(P) > 2 and (P[0] - P[-1]).length < 2e-4:
        P.pop()
        RR.pop()
    if lod and _LOD.level != "high":
        seg = _sseg(seg, r)
        idx = _simplify(P, r, closed)
        P, RR = [P[i] for i in idx], [RR[i] for i in idx]
    n = len(P)
    if n < 2:
        return None
    T = []
    for i in range(n):
        if closed:
            a = P[(i + 1) % n] - P[(i - 1) % n]
        else:
            a = P[min(i + 1, n - 1)] - P[max(i - 1, 0)]
        T.append(a.normalized() if a.length > 1e-12 else Vector((0, 0, 1)))
    U = _v(up).normalized() if up is not None else None
    ref = U if U is not None else (Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0)))
    N = ref - T[0] * ref.dot(T[0])
    if N.length < 1e-6:
        N = T[0].orthogonal()
    N.normalize()
    rings = []
    cs = [(math.cos(2 * PI * k / seg), math.sin(2 * PI * k / seg)) for k in range(seg)]
    for i in range(n):
        if i > 0:
            if U is not None:
                Nn = U - T[i] * U.dot(T[i])
                N = Nn.normalized() if Nn.length > 1e-4 else (N - T[i] * N.dot(T[i])).normalized()
            else:
                N = (N - T[i] * N.dot(T[i])).normalized()
        B = T[i].cross(N)
        rr = RR[i]
        rings.append([mb.bm.verts.new(P[i] + (N * c + B * s) * rr) for c, s in cs])
    segs = n if closed else n - 1
    for i in range(segs):
        a, b = rings[i], rings[(i + 1) % n]
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([a[k], a[kk], b[kk], b[k]], mat)
    if caps and not closed:
        mb.face(list(reversed(rings[0])), mat)
        mb.face(rings[-1], mat)
    return rings


def _lathe(mb, prof, seg=32, mat="plastic", m=None, loop=False, deform=None, a0=0.0, caps=True, lod=True):
    """Sólido de revolución alrededor de Z local. prof = [(r, z), ...] de abajo hacia arriba por la cara exterior.
    r = 0 en un extremo -> polo (abanico de triángulos). loop=True: perfil cerrado (toro / anillo hueco).
    lod=True: en 'mid'/'low' usa 60 % / 38 % de los gajos (mínimo 6)."""
    if lod and _LOD.level != "high":
        seg = max(6, int(round(seg * _lv(1.0, 0.6, 0.38))))
    rings = []
    for (rr, zz) in prof:
        if rr < 1e-6 and not loop:
            p = Vector((0.0, 0.0, zz))
            if deform is not None:
                p = deform(p, 0.0, 0.0, zz)
            rings.append([mb.bm.verts.new(m @ p if m is not None else p)])
            continue
        ring = []
        for k in range(seg):
            a = a0 + 2 * PI * k / seg
            p = Vector((rr * math.cos(a), rr * math.sin(a), zz))
            if deform is not None:
                p = deform(p, a, rr, zz)
            ring.append(mb.bm.verts.new(m @ p if m is not None else p))
        rings.append(ring)
    nr = len(rings)
    segs = nr if loop else nr - 1
    for i in range(segs):
        A, B = rings[i], rings[(i + 1) % nr]
        if len(A) == 1 and len(B) == 1:
            continue
        for k in range(seg):
            kk = (k + 1) % seg
            if len(A) == 1:
                mb.face([A[0], B[kk], B[k]], mat)
            elif len(B) == 1:
                mb.face([A[k], A[kk], B[0]], mat)
            else:
                mb.face([A[k], A[kk], B[kk], B[k]], mat)
    if not loop and caps:
        if len(rings[0]) > 1:
            mb.face(list(reversed(rings[0])), mat)
        if len(rings[-1]) > 1:
            mb.face(rings[-1], mat)
    return rings


def _torus(mb, center, axis, R, r, n=24, seg=6, mat="metal_rust", arc=None, a0=0.0):
    """Anillo (toro) o arco de toro (arc en grados, con tapas) alrededor de `axis`."""
    M = _frame(center, axis)
    if arc is None:
        pts = [M @ Vector((R * math.cos(a0 + 2 * PI * i / n), R * math.sin(a0 + 2 * PI * i / n), 0)) for i in range(n)]
        return _tube(mb, pts, r, seg=seg, mat=mat, closed=True, up=M.to_3x3() @ Vector((0, 0, 1)))
    k = max(2, int(n * arc / 360.0) + 1)
    pts = [M @ Vector((R * math.cos(a0 + math.radians(arc) * i / (k - 1)), R * math.sin(a0 + math.radians(arc) * i / (k - 1)), 0))
           for i in range(k)]
    return _tube(mb, pts, r, seg=seg, mat=mat, up=M.to_3x3() @ Vector((0, 0, 1)))


def _axis_vals(a0, a1, r, rseg, step):
    i0, i1 = a0 + r, a1 - r
    n = max(1, int(math.ceil((i1 - i0) / step - 1e-9)))
    vals = [a0 + r * k / rseg for k in range(rseg)]
    vals += [i0 + (i1 - i0) * k / n for k in range(n + 1)]
    vals += [i1 + r * k / rseg for k in range(1, rseg + 1)]
    return vals


def _lattice(mn, mx, r=0.01, rseg=2, step=0.04, mat="metal_paint", skip=(), deform=None, matfn=None, steps=None, lod=True):
    """Caja de esquinas redondeadas hecha con una retícula de cuadriláteros (para poder abollarla).
    skip: caras abiertas ('-x', '+x', '-y', '+y', '-z', '+z'). deform(p, n) -> p. matfn(centro, normal) -> material|None.
    lod=True: en 'mid' / 'low' el paso de la retícula se multiplica × 2 / × 5 y el redondeo de esquinas es de 1 gajo
    (las manchas de óxido por cara y las abolladuras siguen, más gruesas).
    Devuelve un MB nuevo (superficie cerrada si skip está vacío)."""
    mn, mx = _v(mn), _v(mx)
    dims = mx - mn
    r = max(0.001, min(r, 0.45 * min(dims)))
    if r < 0.003:
        rseg = 1
    st = steps or (step, step, step)
    if lod and _LOD.level != "high":
        st = tuple(s_ * _lv(1.0, 2.0, 5.0) for s_ in st)
        rseg = 1
    ax = [_axis_vals(mn[a], mx[a], r, rseg, st[a]) for a in range(3)]
    lo = mn + Vector((r, r, r))
    hi = mx - Vector((r, r, r))
    mb = MB()
    bm = mb.bm
    cache = {}

    def V(i, j, k):
        key = (i, j, k)
        v = cache.get(key)
        if v is None:
            p = Vector((ax[0][i], ax[1][j], ax[2][k]))
            inner = Vector((min(max(p.x, lo.x), hi.x), min(max(p.y, lo.y), hi.y), min(max(p.z, lo.z), hi.z)))
            d = p - inner
            nrm = d.normalized() if d.length > 1e-12 else Vector((0, 0, 1))
            p = inner + nrm * r
            if deform is not None:
                p = deform(p, nrm)
            v = bm.verts.new(p)
            cache[key] = v
        return v

    n0, n1, n2 = len(ax[0]), len(ax[1]), len(ax[2])
    faces = []
    F = faces.append
    if "-x" not in skip:
        for j in range(n1 - 1):
            for k in range(n2 - 1):
                F(mb.face([V(0, j, k), V(0, j, k + 1), V(0, j + 1, k + 1), V(0, j + 1, k)], mat))
    if "+x" not in skip:
        i = n0 - 1
        for j in range(n1 - 1):
            for k in range(n2 - 1):
                F(mb.face([V(i, j, k), V(i, j + 1, k), V(i, j + 1, k + 1), V(i, j, k + 1)], mat))
    if "-y" not in skip:
        for i in range(n0 - 1):
            for k in range(n2 - 1):
                F(mb.face([V(i, 0, k), V(i + 1, 0, k), V(i + 1, 0, k + 1), V(i, 0, k + 1)], mat))
    if "+y" not in skip:
        j = n1 - 1
        for i in range(n0 - 1):
            for k in range(n2 - 1):
                F(mb.face([V(i, j, k), V(i, j, k + 1), V(i + 1, j, k + 1), V(i + 1, j, k)], mat))
    if "-z" not in skip:
        for i in range(n0 - 1):
            for j in range(n1 - 1):
                F(mb.face([V(i, j, 0), V(i, j + 1, 0), V(i + 1, j + 1, 0), V(i + 1, j, 0)], mat))
    if "+z" not in skip:
        k = n2 - 1
        for i in range(n0 - 1):
            for j in range(n1 - 1):
                F(mb.face([V(i, j, k), V(i + 1, j, k), V(i + 1, j + 1, k), V(i, j + 1, k)], mat))
    if matfn is not None:
        bm.normal_update()
        for f in faces:
            mm = matfn(f.calc_center_median(), f.normal)
            if mm:
                f.material_index = mb.mi(mm)
    return mb


def _solidify(mb, t):
    """Da espesor `t` hacia ATRÁS de la normal (las caras deben venir orientadas hacia fuera). Sólido cerrado."""
    mb.bm.normal_update()
    bmesh.ops.solidify(mb.bm, geom=list(mb.bm.faces), thickness=t)
    return mb


def _tray(mn, mx, open_face="-y", t=0.0015, **kw):
    """Bandeja / carcasa de chapa: caja redondeada con una (o varias) caras abiertas y espesor `t` hacia dentro."""
    skip = (open_face,) if isinstance(open_face, str) else tuple(open_face)
    mb = _lattice(mn, mx, skip=skip, **kw)
    return _solidify(mb, t)


def _sheet(mb, grid, mat, skip=None, wrap=False):
    """Cuadriláteros sobre una rejilla de puntos grid[i][j] (i = columnas, j = filas). wrap=True: la última columna es la
    primera (superficie cerrada en i, sin costura duplicada). Devuelve los vértices."""
    V = [[mb.bm.verts.new(_v(p)) for p in col] for col in (grid[:-1] if wrap else grid)]
    if wrap:
        V.append(V[0])
    for i in range(len(V) - 1):
        for j in range(len(V[0]) - 1):
            if skip is not None and skip(i, j):
                continue
            mb.face([V[i][j], V[i + 1][j], V[i + 1][j + 1], V[i][j + 1]], mat)
    # quita vértices sueltos de celdas saltadas
    loose = list({v for col in V for v in col if not v.link_faces})
    if loose:
        bmesh.ops.delete(mb.bm, geom=loose, context="VERTS")
    return V


def _solid_sheet(grid, t, mat, skip=None, wrap=False):
    """Rejilla de puntos -> chapa con espesor t (sólido cerrado). Devuelve un MB nuevo."""
    mb = MB()
    _sheet(mb, grid, mat, skip, wrap)
    mb.bm.normal_update()
    bmesh.ops.solidify(mb.bm, geom=list(mb.bm.faces), thickness=t)
    return mb


def _holed_panel(x0, z0, x1, z1, cx, cz, R, t, mat, n=48, rings=3, y=0.0):
    """Placa rectangular (plano XZ, cara frontal en y, espesor t hacia +y) con un agujero circular. Sólido cerrado."""
    corners = [(x1, z1), (x0, z1), (x0, z0), (x1, z0)]
    ca = sorted(math.atan2(c[1] - cz, c[0] - cx) % (2 * PI) for c in corners)
    step = 2 * PI / n
    angs = list(ca)
    for i in range(n):
        a = i * step
        if min(abs((a - c + PI) % (2 * PI) - PI) for c in ca) > 0.35 * step:
            angs.append(a)
    angs.sort()

    def ray(a):
        dx, dz = math.cos(a), math.sin(a)
        ts = []
        if dx > 1e-9:
            ts.append((x1 - cx) / dx)
        if dx < -1e-9:
            ts.append((x0 - cx) / dx)
        if dz > 1e-9:
            ts.append((z1 - cz) / dz)
        if dz < -1e-9:
            ts.append((z0 - cz) / dz)
        tt = min(ts)
        return cx + dx * tt, cz + dz * tt

    mb = MB()
    cols = []
    for a in angs:
        ox, oz = ray(a)
        ix, iz = cx + R * math.cos(a), cz + R * math.sin(a)
        col = []
        for k in range(rings + 1):
            s = (k / rings) ** 1.3
            col.append(mb.bm.verts.new((ix + (ox - ix) * s, y, iz + (oz - iz) * s)))
        cols.append(col)
    m = len(cols)
    for i in range(m):
        A, B = cols[i], cols[(i + 1) % m]
        for k in range(rings):
            mb.face([A[k], A[k + 1], B[k + 1], B[k]], mat)
    return _solidify(mb, t)


def _hood_louvers(mb, origin, U, V, W, cols, rows, su, sv, pu, pv, out=0.006, t=0.0012, mat="metal_paint", deform=None):
    """Lamas estampadas (capotas inclinadas) sobre un panel. origin = esquina superior izquierda de la primera lama,
    U/V en el plano del panel (V hacia arriba), W normal hacia fuera. Cada capota entra 0,8 mm en el panel."""
    tmp = MB()
    U, V, W = _v(U).normalized(), _v(V).normalized(), _v(W).normalized()
    Vs = V - W * (out / sv)
    for c in range(cols):
        for rr in range(rows):
            o = _v(origin) + U * (c * pu) - V * (rr * pv) - W * 0.0008
            M = _basis(o, U, Vs, W)
            _box(tmp, (0.0, -sv, 0.0), (su, 0.0, t), mat, m=M)
    if deform is not None:
        for v in tmp.bm.verts:
            v.co = deform(v.co, W)
    _merge(mb, tmp)


def _bolt(mb, p, n, r=0.006, h=0.005, mat="metal_rust", washer=True, seg=6):
    """Cabeza hexagonal + arandela, apoyadas en una superficie de normal n (se empotran 0,6 mm).
    mid: arandela de 8 lados · low: sin arandela y sin pernos chicos (r < 12 mm)."""
    lv = _LOD.level
    if lv == "low" and r < 0.012:
        return
    p, n = _v(p), _v(n).normalized()
    b = p - n * 0.0006
    if washer and lv != "low":
        mb.cyl(b, b + n * (0.0015 + 0.0006), r * 1.7, seg=_lv(12, 8, 6), mat=mat)
        b = b + n * 0.0016
    mb.cyl(b, b + n * h, r, seg=seg, mat=mat)


def _screw(mb, p, n, r=0.0042, h=0.0022, mat="metal_rust"):
    """Tornillo de cabeza redonda (domo bajo), empotrado 0,6 mm. mid: domo de 6 gajos · low: se omite."""
    lv = _LOD.level
    if lv == "low":
        return
    M = _frame(_v(p) - _v(n).normalized() * 0.0006, n)
    if lv == "mid":
        _lathe(mb, [(r, 0.0), (r * 0.8, h * 0.7), (0.0, h)], seg=6, mat=mat, m=M, lod=False)
        return
    _lathe(mb, [(r, 0.0), (r, h * 0.45), (r * 0.7, h * 0.85), (0.0, h)], seg=8, mat=mat, m=M)


def _rand_dents(r, mn, mx, n, faces=("+z", "-y", "+x", "-x"), R=(0.03, 0.09), depth=(0.003, 0.012), region=None):
    """Abolladuras: (centro sobre la cara, dirección hacia dentro, radio, profundidad). region = (mn, mx) opcional."""
    mn, mx = _v(mn), _v(mx)
    lo, hi = (mn, mx) if region is None else (_v(region[0]), _v(region[1]))
    out = []
    for _ in range(n):
        f = faces[int(r.integers(0, len(faces)))]
        ax = "xyz".index(f[1])
        c = Vector((r.uniform(lo.x, hi.x), r.uniform(lo.y, hi.y), r.uniform(lo.z, hi.z)))
        d = Vector((0, 0, 0))
        if f[0] == "+":
            c[ax] = mx[ax]
            d[ax] = -1.0
        else:
            c[ax] = mn[ax]
            d[ax] = 1.0
        out.append((c, d, r.uniform(*R), r.uniform(*depth)))
    return out


def _deformer(dents, nz=None, amp=0.0, freq=7.0):
    def f(p, nrm):
        q = p.copy()
        for (c, d, R, dep) in dents:
            dist = (p - c).length
            if dist < R:
                q += d * dep * 0.5 * (1 + math.cos(PI * dist / R))
        if nz is not None and amp > 0:
            q -= nrm * amp * nz(p, freq)
        return q
    return f


def _rust_fn(nz, z0, z1, thr=0.35, rust="metal_rust"):
    """Manchas de óxido por cara: más abajo y en caras que miran al suelo; bordes irregulares por ruido."""
    def f(c, n):
        h = (c.z - z0) / max(z1 - z0, 1e-6)
        v = nz(c, 9.0) * 0.55 + nz(c, 27.0) * 0.25 + (1.0 - h) ** 2 * 0.7 - 0.35
        if n.z < -0.5:
            v += 0.45
        return rust if v > thr else None
    return f


def _bezier(p0, p1, p2, p3, n):
    p0, p1, p2, p3 = _v(p0), _v(p1), _v(p2), _v(p3)
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append(p0 * u ** 3 + p1 * 3 * u * u * t + p2 * 3 * u * t * t + p3 * t ** 3)
    return out


def _spline(ctrl, step=0.04):
    """Catmull-Rom (centrípeta simple) por los puntos de control, muestreada cada ~step m."""
    P = [_v(p) for p in ctrl]
    if len(P) < 3:
        n = max(2, int((P[-1] - P[0]).length / step))
        return [P[0].lerp(P[-1], i / n) for i in range(n + 1)]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        n = max(2, int((p2 - p1).length / step))
        for k in range(n):
            t = k / n
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-2])
    return out


def _fillet(pts, rad, nseg=6):
    """Polilínea con esquinas redondeadas (curvas de radio ~rad) — curvas de conduit, ganchos, varillas dobladas."""
    P = [_v(p) for p in pts]
    if len(P) < 3:
        return P
    out = [P[0]]
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        d0, d1 = b - a, c - b
        if d0.length < 1e-6 or d1.length < 1e-6:
            continue
        ang = d0.angle(d1)
        if ang < 1e-3:
            out.append(b)
            continue
        t = min(rad * math.tan(ang / 2), 0.45 * d0.length, 0.45 * d1.length)
        pin, pout = b - d0.normalized() * t, b + d1.normalized() * t
        for k in range(nseg + 1):
            s = k / nseg
            out.append(pin * (1 - s) ** 2 + b * 2 * (1 - s) * s + pout * s * s)
    out.append(P[-1])
    return out


def _angle_iron(mb, p0, p1, normal, a=0.04, t=0.004, mat="metal_rust", flip=False):
    """Ángulo de acero (L a × a × t, aristas con chaflán de 1,5 mm) de p0 a p1. El perfil se orienta con `normal`
    (perpendicular al recorrido): un ala sigue `normal`, la otra el lado (tangente × normal)."""
    c = 0.0015
    s = -1.0 if flip else 1.0
    prof = [(0.0, c), (c, 0.0), (a - c, 0.0), (a, c), (a, t - c * 0.5), (a - c * 0.5, t), (t + c, t), (t, t + c),
            (t, a - c * 0.5), (t - c * 0.5, a), (c, a), (0.0, a - c)]
    if _LOD.level != "high":  # sin chaflanes de 1,5 mm (invisibles a > 3 m)
        prof = [(0.0, 0.0), (a, 0.0), (a, t), (t, t), (t, a), (0.0, a)]
    prof = [(x * s, y) for x, y in prof]
    if flip:
        prof = list(reversed(prof))
    mb.sweep(prof, [p0, p1], mat=mat, normal=normal)


# =====================================================================================================================
# A/C
# =====================================================================================================================
def _coil(mb, x0, x1, z0, z1, y_face, pitch=0.008, depth=0.013, bend=None, mat_fin="aluminium", mat_core="metal_rust"):
    """Serpentín de condensador visto desde -Y: bloque de tubos + aletas verticales (bend(x, z) -> (dx, dy) = aletas
    aplastadas)."""
    _box(mb, (x0, y_face + depth - 0.001, z0), (x1, y_face + depth + 0.04, z1), mat_core)
    pitch *= _lv(1, 2, 3)  # mid / low: aletas a paso doble / triple con 3 / 2 estaciones
    nzs = _lv(6, 3, 2)
    nfin = int((x1 - x0) / pitch)
    zs = [z0 + 0.002 + (z1 - z0 - 0.004) * k / (nzs - 1) for k in range(nzs)]
    prof = [(-0.0005, 0.0), (0.0005, 0.0), (0.0005, depth), (-0.0005, depth)]
    for i in range(nfin):
        x = x0 + pitch * (i + 0.5)
        path = []
        for z in zs:
            dx, dy = bend(x, z) if bend is not None else (0.0, 0.0)
            path.append((x + dx, y_face + dy, z))
        mb.sweep(prof, path, mat=mat_fin, normal=(0, 1, 0))


def _wire_guard(mb, x0, x1, z0, z1, y, sx=0.025, sz=0.025, r=0.0017, deform=None, mat="metal_paint"):
    """Rejilla de alambre soldado (verticales en y, horizontales delante) con marco perimetral de alambre."""
    def D(p):
        p = _v(p)
        return deform(p, Vector((0, -1, 0))) if deform is not None else p

    nx = max(2, int((x1 - x0) / sx))
    nz_ = max(2, int((z1 - z0) / sz))
    zs = [z0 + (z1 - z0) * k / 8 for k in range(9)]
    xs = [x0 + (x1 - x0) * k / 12 for k in range(13)]
    for i in range(1, nx):
        x = x0 + (x1 - x0) * i / nx
        _tube(mb, [D((x, y, z)) for z in zs], r, seg=6, mat=mat)
    for k in range(1, nz_):
        z = z0 + (z1 - z0) * k / nz_
        _tube(mb, [D((x, y - 1.6 * r, z)) for x in xs], r, seg=6, mat=mat)
    rim = _fillet([(x0, y - 0.8 * r, z0), (x1, y - 0.8 * r, z0), (x1, y - 0.8 * r, z1), (x0, y - 0.8 * r, z1),
                   (x0, y - 0.8 * r, z0), (x1, y - 0.8 * r, z0)], 0.012, 3)
    rim = rim[1:-1]
    _tube(mb, [D(p) for p in rim], r * 1.5, seg=6, mat=mat, closed=True, up=(0, 1, 0))


def _wall_bracket(mb, x, y_out, z_top, drop, nz, rr, w=0.04, leg_top=None):
    """Ménsula de ángulo de acero: pierna en el muro, brazo horizontal (ala superior plana en z_top) y tornapunta."""
    yw = -0.0012
    lt = z_top + 0.02 if leg_top is None else leg_top
    # pierna vertical contra el muro (ala en el plano del muro a 1,2 mm)
    _angle_iron(mb, (x - w / 2 - 0.002, yw, z_top - drop), (x - w / 2 - 0.002, yw, lt), normal=(0, -1, 0), a=w)
    # brazo horizontal: ala superior bajo el equipo
    _angle_iron(mb, (x - w / 2, -0.0045, z_top), (x - w / 2, y_out, z_top), normal=(0, 0, -1), a=w)
    # tornapunta diagonal
    ya, za = -0.012, z_top - drop + 0.05
    yb, zb = y_out * 0.78, z_top - 0.012
    d = Vector((0, yb - ya, zb - za)).normalized()
    nn = Vector((1, 0, 0)).cross(d)
    _angle_iron(mb, (x - 0.0135, ya, za), (x - 0.0135, yb, zb), normal=nn, a=0.032, t=0.004)
    # anclas (tuerca + arandela) en la pierna, y tornillo en el brazo
    for zz in (z_top - drop + 0.035, z_top - 0.09):
        _bolt(mb, (x + rr.uniform(-0.004, 0.004), yw - 0.004, zz), (0, -1, 0), r=0.0065)
        _cyl(mb, (x, 0.03, zz), (x, -0.012, zz), 0.0045, seg=8, mat="metal_rust")


def _ac_window(r):
    W, H = 0.60, 0.40
    yo, yi = -0.31, 0.14
    x0, x1 = -W / 2, W / 2
    nz = _Nz(r)
    dents = _rand_dents(r, (x0, yo, 0), (x1, yi, H), int(r.integers(2, 5)), faces=("+z", "+x", "-x", "+z"),
                        region=((x0 + 0.05, yo + 0.10, 0.05), (x1 - 0.05, -0.04, H - 0.05)))
    deform = _deformer(dents, nz, amp=0.0009, freq=6.0)
    mb = _tray((x0, yo, 0.0), (x1, yi, H), "-y", t=0.0012, r=0.014, step=0.03, mat="metal_paint", deform=deform,
               matfn=_rust_fn(nz, 0.0, H, thr=0.42))
    # lamas laterales en la parte exterior
    for side in (-1, 1):
        x = x1 if side > 0 else x0
        U = Vector((0, 1, 0)) * side
        ys = yo + 0.035 if side > 0 else -0.045
        _hood_louvers(mb, (x, ys, H - 0.075), U, (0, 0, 1), (side, 0, 0), 2, 9, 0.105, 0.016, 0.125, 0.027,
                      out=0.005, deform=deform)
    # lamas en la tapa (parte trasera exterior)
    _hood_louvers(mb, (x0 + 0.06, yo + 0.105, H), (1, 0, 0), (0, 1, 0), (0, 0, 1), 4, 3, 0.10, 0.014, 0.125, 0.026,
                  out=0.004, deform=deform)
    # serpentín + rejilla trasera (con zona aplastada)
    cx, cz, cr = r.uniform(-0.15, 0.15), r.uniform(0.12, 0.3), r.uniform(0.05, 0.11)

    def bend(x, z):
        d = math.hypot(x - cx, z - cz)
        if d > cr:
            return 0.0, 0.0
        w = 0.5 * (1 + math.cos(PI * d / cr))
        return 0.006 * w * math.sin(x * 400), 0.008 * w

    _coil(mb, x0 + 0.004, x1 - 0.004, 0.006, H - 0.006, yo + 0.024, pitch=0.008, bend=bend)
    gdef = _deformer([(Vector((cx, yo + 0.01, cz)), Vector((0, 1, 0)), cr * 1.2, 0.009)])
    _wire_guard(mb, x0 + 0.009, x1 - 0.009, 0.01, H - 0.01, yo + 0.012, deform=gdef)
    # tornillos
    for x in (-0.2, 0.0, 0.2):
        p = deform(Vector((x + r.uniform(-0.01, 0.01), yo + 0.012, H)), Vector((0, 0, 1)))
        _screw(mb, p, (0, 0, 1))
    for side in (-1, 1):
        for z in (0.06, H - 0.06):
            x = x1 if side > 0 else x0
            p = deform(Vector((x, yo + 0.012, z)), Vector((side, 0, 0)))
            _screw(mb, p, (side, 0, 0))
    # marco de manguito contra el muro (cubre el hueco del muro)
    g, fo, fy0, fy1 = 0.003, 0.032, -0.008, -0.0025
    _box(mb, (x0 - fo, fy0, H + g), (x1 + fo, fy1, H + fo), "aluminium", bevel=0.002, seg=1)
    _box(mb, (x0 - fo, fy0, -fo), (x1 + fo, fy1, -g), "aluminium", bevel=0.002, seg=1)
    _box(mb, (x0 - fo, fy0, -g + 0.001), (x0 - g, fy1, H + g - 0.001), "aluminium", bevel=0.002, seg=1)
    _box(mb, (x1 + g, fy0, -g + 0.001), (x1 + fo, fy1, H + g - 0.001), "aluminium", bevel=0.002, seg=1)
    # ménsulas
    for x in (-0.19, 0.19):
        _wall_bracket(mb, x + r.uniform(-0.01, 0.01), yo + 0.01, -0.0015, 0.30, nz, r, leg_top=-0.006)
    # desagüe: niple + manguera colgando
    dx = 0.262
    _cyl(mb, (dx, yo + 0.045, 0.004), (dx, yo + 0.045, -0.03), 0.007, seg=10, mat="plastic")
    L = r.uniform(0.35, 0.7)
    hose = _spline([(dx, yo + 0.045, -0.02), (dx + 0.01, yo + 0.05, -0.12), (dx + 0.03, yo + 0.09, -0.30 * L / 0.5),
                    (dx + r.uniform(0.0, 0.06), yo + 0.16, -L)], 0.03)
    _tube(mb, hose, 0.009, seg=8, mat="plastic")
    return mb


def _ac_split(r):
    W, H, D = 0.80, 0.55, 0.28
    yb = -0.075
    yo = yb - D
    z0 = 0.05
    x0, x1 = -W / 2, W / 2
    z1 = z0 + H
    nz = _Nz(r)
    dents = _rand_dents(r, (x0, yo, z0), (x1, yb, z1), int(r.integers(2, 5)), faces=("+z", "-y", "+x", "-x"),
                        region=((x0 + 0.05, yo + 0.04, z0 + 0.05), (x1 - 0.05, yb - 0.04, z1 - 0.05)))
    deform = _deformer(dents, nz, amp=0.0008, freq=5.0)
    mb = _tray((x0, yo, z0), (x1, yb, z1), "-y", t=0.0015, r=0.012, step=0.03, mat="metal_paint", deform=deform,
               matfn=_rust_fn(nz, z0, z1, thr=0.45))
    # panel frontal con boca de ventilador
    cx, cz, R = 0.09, z0 + 0.285, 0.205
    inset = 0.0045
    py = yo + 0.0015
    front = _holed_panel(x0 + inset, z0 + inset, x1 - inset, z1 - inset, cx, cz, R, 0.0015, "metal_paint", n=_lv(56, 40, 24),
                         rings=_lv(3, 2, 1), y=py)
    fd = [dd for dd in dents if dd[1].y > 0.5]
    if fd:
        fdef = _deformer([(c + Vector((0, 0.0015, 0)), d, rr_, dep) for (c, d, rr_, dep) in fd])
        for v in front.bm.verts:
            v.co = fdef(v.co, Vector((0, -1, 0)))
    _merge(mb, front)
    # campana (aro de la boca)
    Mb = _frame((cx, py + 0.0015, cz), (0, 1, 0))
    _lathe(mb, [(R + 0.0005, -0.0004), (R + 0.0005, 0.07), (R - 0.0012, 0.07), (R - 0.0012, 0.004), (R - 0.008, -0.0004)],
           seg=56, mat="metal_paint", m=Mb, loop=True)
    # rejilla del ventilador: anillos concéntricos + radios
    gy = yo - 0.007
    Mg = _frame((cx, gy, cz), (0, -1, 0))
    nring = _lv(9, 7, 5)  # mid / low: menos anillos (mismo diámetro exterior) y menos puntos por anillo
    rings_r = [0.035 + (0.0215 * 8) * k / (nring - 1) for k in range(nring)]
    nsp = 12
    bent = r.uniform(0, 2 * PI)
    for k, rr_ in enumerate(rings_r):
        pts = []
        npt = _lv(64, max(16, int(2 * PI * rr_ / 0.035)), max(10, int(2 * PI * rr_ / 0.06)))
        for i in range(npt):
            a = 2 * PI * i / npt
            push = 0.006 * max(0.0, math.cos(a - bent)) ** 6 * (rr_ / 0.2)
            pts.append(Mg @ Vector((rr_ * math.cos(a), rr_ * math.sin(a), -push - 0.0018)))
        _tube(mb, pts, 0.0017, seg=6, mat="metal_paint", closed=True, up=(0, 1, 0))
    for i in range(nsp):
        a = 2 * PI * (i + 0.5) / nsp
        pts = [Mg @ Vector((rr_ * math.cos(a), rr_ * math.sin(a), 0.0)) for rr_ in (0.03, 0.1, 0.17, rings_r[-1] + 0.012)]
        _tube(mb, pts, 0.0019, seg=6, mat="metal_paint")
        if i % 3 == 0:  # orejas atornilladas al panel
            p = Mg @ Vector(((rings_r[-1] + 0.014) * math.cos(a), (rings_r[-1] + 0.014) * math.sin(a), 0.0))
            _cyl(mb, p + Vector((0, -0.001, 0)), Vector((p.x, py + 0.0004, p.z)), 0.006, seg=8, mat="metal_paint")
            _screw(mb, Vector((p.x, gy - 0.001, p.z)), (0, -1, 0), r=0.0045)
    _lathe(mb, [(0.0, 0.004), (0.028, 0.004), (0.034, 0.0), (0.034, -0.004), (0.0, -0.004)], seg=24, mat="plastic", m=Mg)
    # ventilador (3 aspas) + motor + soporte
    Mf = _frame((cx, yo + 0.055, cz), (0, -1, 0))
    _fan(mb, Mf, 0.19, 0.055, 3, r, broken=r.random() < 0.5)
    _cyl(mb, (cx, yo + 0.06, cz), (cx, yo + 0.13, cz), 0.06, seg=24, mat="metal_rust")
    for dz in (-1, 1):
        _box(mb, (cx - 0.012, yo + 0.13, cz + dz * 0.06 if dz > 0 else z0 + 0.006),
               (cx + 0.012, yo + 0.137, z1 - 0.006 if dz > 0 else cz - 0.06), "metal_rust", bevel=0.002, seg=1)
    _coil(mb, x0 + 0.01, x1 - 0.01, z0 + 0.008, z1 - 0.008, yb - 0.06, pitch=0.009)
    # lamas frontales izquierdas
    _hood_louvers(mb, (x0 + 0.035, py, z1 - 0.05), (1, 0, 0), (0, 0, 1), (0, -1, 0), 1, 15, 0.18, 0.016, 0.0, 0.029,
                  out=0.006, deform=None)
    # tapa de válvulas (lado derecho) + válvulas + tuberías
    vy0, vy1, vz0, vz1 = yo + 0.05, yo + 0.20, z0 + 0.04, z0 + 0.26
    cover = _tray((x1 - 0.002, vy0, vz0), (x1 + 0.03, vy1, vz1), "-x", t=0.0012, r=0.006, step=0.03, mat="metal_paint",
                  matfn=_rust_fn(nz, vz0, vz1, thr=0.2))
    _merge(mb, cover)
    for (yy, zz) in ((vy0 + 0.02, vz1 - 0.02), (vy1 - 0.02, vz1 - 0.02), (vy0 + 0.02, vz0 + 0.02), (vy1 - 0.02, vz0 + 0.02)):
        _screw(mb, (x1 + 0.03, yy, zz), (1, 0, 0), r=0.004)
    runs = []
    for k, (rp, ins) in enumerate(((0.0048, 0.0), (0.008, 0.016))):
        vz = z0 + 0.075 + 0.075 * k
        vy = yo + 0.235
        _box(mb, (x1 - 0.0032, vy - 0.02, vz - 0.022), (x1 + 0.035, vy + 0.02, vz + 0.022), "metal_rust", bevel=0.003, seg=1)
        _cyl(mb, (x1 + 0.034, vy, vz), (x1 + 0.06, vy, vz), rp + 0.007, seg=6, mat="metal_rust")
        top = r.uniform(0.75, 1.05) + 0.06 * k
        px, py_ = x1 + 0.11 + 0.035 * k, -0.035 - 0.03 * k
        path = _fillet([(x1 + 0.055, vy, vz), (px, vy, vz), (px, py_, vz + 0.02), (px, py_, top), (px, 0.03, top + 0.04)], 0.07, 6)
        path = _densify(path, 0.03)
        if ins > 0:
            radii = [ins * (1.0 + 0.12 * (math.sin(i * 1.7) > 0.6)) for i in range(len(path))]
            _tube(mb, path[2:], ins, seg=10, mat="cable", radii=radii[2:])
            _tube(mb, path[:3], rp, seg=8, mat="metal_rust")
        else:
            _tube(mb, path, rp, seg=8, mat="metal_rust")
        runs.append((px, py_, vz + 0.1, top - 0.08, ins if ins > 0 else rp))
    # cable eléctrico que sale de la tapa y acompaña a la tubería aislada, con cinchos de plástico
    px, py_, zb_, zt_, ri = runs[1]
    cx_ = px + 0.03
    cab = _fillet([(x1 + 0.015, vy1 - 0.03, vz0 + 0.01), (x1 + 0.015, vy1 - 0.03, vz0 - 0.05), (cx_, py_, vz0 - 0.03),
                   (cx_, py_, zt_ + 0.12), (cx_, 0.03, zt_ + 0.16)], 0.06, 5)
    _tube(mb, _densify(cab, 0.04), 0.006, seg=6, mat="cable")
    for t_ in (0.15, 0.45, 0.8):
        z = zb_ + (zt_ - zb_) * t_
        loop = [Vector((px + (ri + 0.0022) * math.cos(a), py_ + (ri + 0.0022) * math.sin(a), z))
                for a in [PI / 2 + PI * i / 10 for i in range(11)]]
        loop += [Vector((cx_ + 0.0082 * math.cos(a), py_ + 0.0082 * math.sin(a), z)) for a in [-PI / 2 + PI * i / 6 for i in range(7)]]
        _tube(mb, loop, 0.0015, seg=4, mat="plastic", closed=True, up=(0, 0, 1))
        _box(mb, (cx_ + 0.008, py_ - 0.003, z - 0.004), (cx_ + 0.016, py_ + 0.003, z + 0.004), "plastic", bevel=0.001, seg=1)
    # patas + amortiguadores + ménsulas
    for x in (-0.28, 0.28):
        _box(mb, (x - 0.025, yo + 0.01, 0.016), (x + 0.025, yb - 0.01, z0 + 0.004), "metal_paint", bevel=0.003, seg=1)
        for y in (yo + 0.05, yb - 0.05):
            _cyl(mb, (x, y, -0.0002), (x, y, 0.0165), 0.017, seg=12, mat="plastic")
            _cyl(mb, (x, y, 0.012), (x, y, z0 + 0.012), 0.005, seg=6, mat="metal_rust")
        _wall_bracket(mb, x + r.uniform(-0.006, 0.006), yo - 0.06, -0.0012, 0.42, nz, r)
    # manguera de desagüe
    dxx = -0.355
    _cyl(mb, (dxx, yo + 0.12, z0 + 0.004), (dxx, yo + 0.12, z0 - 0.04), 0.008, seg=10, mat="plastic")
    L = r.uniform(0.5, 0.9)
    _tube(mb, _spline([(dxx, yo + 0.12, z0 - 0.03), (dxx - 0.02, yo + 0.14, -0.12), (dxx - 0.05, yo + 0.2, -0.4 * L),
                       (dxx - 0.04, yo + 0.25, -L)], 0.03), 0.009, seg=8, mat="plastic")
    return mb


def _densify(pts, step):
    P = [_v(p) for p in pts]
    out = [P[0]]
    for a, b in zip(P[:-1], P[1:]):
        n = max(1, int((b - a).length / step))
        for k in range(1, n + 1):
            out.append(a.lerp(b, k / n))
    return out


def _fan(mb, M, R_tip, R_hub, nb, r, broken=False, mat="plastic"):
    """Hélice axial de nb aspas en forma de hoz (chapa de 2,5 mm), eje Z local de M. broken: una aspa partida."""
    bad = int(r.integers(0, nb)) if broken else -1
    th_base = r.uniform(0, 2 * PI)
    NC = 5
    nr, nc = _lv((9, 5), (6, 3), (3, 2))
    for b in range(nb):
        th0 = th_base + 2 * PI * b / nb
        tip = 1.0 if b != bad else r.uniform(0.45, 0.75)
        # recortes de la punta rota: se sortean siempre los NC + 1 valores (misma semilla en los 3 niveles)
        cuts = [r.uniform(0.3, 0.9) for _ in range(NC + 1)] if b == bad else None
        grid = []
        for c in range(nc + 1):
            cc = c / nc
            col = []
            for i in range(nr + 1):
                s = i / nr * tip
                rr_ = R_hub * 0.8 + s * (R_tip - R_hub * 0.8)
                chord = (0.075 + 0.06 * s) * (R_tip / 0.19)
                if s > 0.82:
                    chord *= math.sqrt(max(0.05, 1 - ((s - 0.82) / 0.18) ** 2))
                if b == bad and i == nr:
                    chord *= cuts[int(round(cc * NC))]
                phi = math.radians(34 - 16 * s)
                tang = (cc - 0.5) * chord * math.cos(phi)
                ax = (cc - 0.5) * chord * math.sin(phi) + 0.07 * chord * math.sin(PI * cc)
                th = th0 + 0.6 * s * s + tang / rr_
                col.append(M @ Vector((rr_ * math.cos(th), rr_ * math.sin(th), ax)))
            grid.append(col)
        blade = _solid_sheet(grid, 0.0025, mat)
        _merge(mb, blade)
    _lathe(mb, [(0.0, -0.035), (R_hub, -0.035), (R_hub, 0.0), (min(0.045, R_hub * 0.85), 0.02), (0.03, 0.032), (0.0, 0.035)],
           seg=24, mat=mat, m=M)


def _ac_box_old(r):
    W, H = 0.66, 0.44
    yo, yi = -0.36, 0.20
    x0, x1 = -W / 2, W / 2
    nz = _Nz(r)
    open_side = "+x" if r.random() < 0.5 else "-x"
    dents = _rand_dents(r, (x0, yo, 0), (x1, yi, H), int(r.integers(3, 6)), faces=("+z", "+z", "+x", "-x"),
                        R=(0.05, 0.12), depth=(0.006, 0.018),
                        region=((x0 + 0.05, yo + 0.04, 0.06), (x1 - 0.05, -0.05, H - 0.05)))
    deform = _deformer(dents, nz, amp=0.0014, freq=5.0)
    mb = _tray((x0, yo, 0.0), (x1, yi, H), ("-y", open_side), t=0.0016, r=0.018, step=0.03, mat="metal_paint",
               deform=deform, matfn=_rust_fn(nz, 0.0, H, thr=0.15))
    # rejilla trasera de lamas gruesas estampadas (algunas dobladas o faltantes)
    gx0, gx1, gz0, gz1 = x0 + 0.03, x1 - 0.03, 0.035, H - 0.035
    fy = yo + 0.004
    for (a, b, c, d) in ((gx0 - 0.02, gx1 + 0.02, gz1, gz1 + 0.02), (gx0 - 0.02, gx1 + 0.02, gz0 - 0.02, gz0),
                         (gx0 - 0.02, gx0, gz0 + 0.001, gz1 - 0.001), (gx1, gx1 + 0.02, gz0 + 0.001, gz1 - 0.001)):
        _box(mb, (a, fy - 0.008, c), (b, fy + 0.006, d), "metal_paint", bevel=0.003, seg=1)
    nsl = 11
    for k in range(nsl):
        z = gz0 + (gz1 - gz0) * (k + 0.5) / nsl
        roll = r.random()
        if roll < 0.12:
            continue  # lama arrancada
        ang = -38 if roll > 0.25 else r.uniform(-75, 5)
        sag = 0.0 if roll > 0.25 else r.uniform(0.005, 0.02)
        M = _T(0, fy, z - sag) @ _R("X", ang)
        _box(mb, (gx0 + 0.001, -0.016, -0.0009), (gx1 - 0.001, 0.016, 0.0009), "metal_paint", bevel=0.0006, seg=1, m=M)
    _coil(mb, x0 + 0.006, x1 - 0.006, 0.008, H - 0.008, yo + 0.04, pitch=0.009, mat_core="metal_rust")
    # interior visible por el panel lateral que falta: tabique, compresor, capacitor, tubería de cobre, motor y hélice
    side = 1 if open_side == "+x" else -1
    _box(mb, (x0 + 0.004, -0.03, 0.004), (x1 - 0.004, -0.018, H - 0.004), "metal_paint", bevel=0.002, seg=1)
    sx, sy = side * (W / 2 - 0.12), -0.155
    _lathe(mb, [(0.0, 0.0), (0.075, 0.0), (0.08, 0.02), (0.08, 0.16), (0.07, 0.2), (0.04, 0.218), (0.0, 0.222)], seg=28,
           mat="metal_rust", m=_T(sx, sy, 0.0035))
    for a in range(3):
        aa = 2 * PI * a / 3 + 0.4
        px, py_ = sx + 0.068 * math.cos(aa), sy + 0.068 * math.sin(aa)
        _cyl(mb, (px, py_, 0.0022), (px, py_, 0.03), 0.013, seg=10, mat="plastic")
    _cyl(mb, (sx - side * 0.02, -0.055, 0.03), (sx - side * 0.02, -0.055, 0.12), 0.021, seg=16, mat="aluminium")
    for k in range(3):
        tp = _fillet([(sx + 0.02 * (k - 1), sy, 0.21), (sx + 0.02 * (k - 1), sy, 0.29 + 0.03 * k),
                      (sx - side * 0.06, sy - 0.05 - 0.015 * k, 0.33 + 0.025 * k),
                      (sx - side * 0.20, yo + 0.07, 0.31 + 0.03 * k), (sx - side * 0.24, yo + 0.07, 0.12 + 0.05 * k)], 0.04, 5)
        _tube(mb, _densify(tp, 0.03), 0.0045 + 0.002 * (k == 0), seg=8, mat="metal_rust")
    mx_ = -side * 0.08
    _cyl(mb, (mx_, -0.10, 0.22), (mx_, -0.174, 0.22), 0.055, seg=24, mat="metal_rust")
    _box(mb, (mx_ - 0.012, -0.10, 0.0045), (mx_ + 0.012, -0.09, 0.16), "metal_rust", bevel=0.002, seg=1)
    _fan(mb, _frame((mx_, -0.205, 0.22), (0, -1, 0)), 0.15, 0.045, 4, r, broken=True, mat="metal_paint")
    # jaula antirrobo: ángulos de 30 mm, marco frontal, barrotes de 12 mm (uno cortado), orejas atornilladas al muro
    cg = 0.03
    X0, X1, Z0, Z1, YF = x0 - cg, x1 + cg, -0.03, H + cg, yo - 0.045
    _angle_iron(mb, (X0, -0.003, Z0), (X0, YF + 0.0012, Z0), (0, 0, 1), a=0.03, t=0.0035, flip=True)
    _angle_iron(mb, (X1, -0.003, Z0), (X1, YF + 0.0012, Z0), (0, 0, 1), a=0.03, t=0.0035, flip=False)
    _angle_iron(mb, (X0, -0.003, Z1), (X0, YF + 0.0012, Z1), (0, 0, -1), a=0.03, t=0.0035, flip=False)
    _angle_iron(mb, (X1, -0.003, Z1), (X1, YF + 0.0012, Z1), (0, 0, -1), a=0.03, t=0.0035, flip=True)
    _box(mb, (X0 + 0.0015, YF - 0.002, Z0 + 0.0015), (X1 - 0.0015, YF + 0.02, Z0 + 0.0255), "metal_rust", bevel=0.002, seg=1)
    _box(mb, (X0 + 0.0015, YF - 0.002, Z1 - 0.0255), (X1 - 0.0015, YF + 0.02, Z1 - 0.0015), "metal_rust", bevel=0.002, seg=1)
    for xa in (X0, X1 - 0.024):
        _box(mb, (xa + 0.002, YF, Z0 + 0.01), (xa + 0.022, YF + 0.018, Z1 - 0.01), "metal_rust", bevel=0.002, seg=1)
    for (xa, za) in ((X0, Z0), (X1, Z0), (X0, Z1), (X1, Z1)):
        _box(mb, (xa - 0.025, -0.006, za - 0.025), (xa + 0.025, -0.0015, za + 0.025), "metal_rust", bevel=0.002, seg=1)
        _bolt(mb, (xa, -0.006, za), (0, -1, 0), r=0.006)
    cut = int(r.integers(1, 7))
    nb = 8
    for i in range(1, nb):
        x = X0 + (X1 - X0) * i / nb
        yb_ = YF - 0.004
        if i == cut:
            _tube(mb, [(x, yb_, Z0 + 0.01), (x + 0.004, yb_ - 0.002, Z0 + 0.11)], 0.006, seg=8, mat="metal_rust")
            _tube(mb, _spline([(x, yb_, Z1 - 0.01), (x, yb_ - 0.006, Z1 - 0.12), (x - 0.025, yb_ - 0.07, Z1 - 0.21)], 0.02),
                  0.006, seg=8, mat="metal_rust")
            continue
        bow = r.uniform(-0.008, 0.003)
        _tube(mb, [(x, yb_, Z0 + 0.008), (x, yb_ + bow, (Z0 + Z1) / 2), (x, yb_, Z1 - 0.008)], 0.006, seg=8, mat="metal_rust")
    for xx in (X0 + 0.003, X1 - 0.003):
        for k in range(1, 5):
            y = YF * k / 5
            _tube(mb, [(xx, y, Z0 + 0.012), (xx, y, Z1 - 0.012)], 0.006, seg=8, mat="metal_rust")
    for k in range(1, 5):
        y = YF * k / 5
        _tube(mb, [(X0 + 0.012, y, Z1 - 0.002), (X1 - 0.012, y, Z1 - 0.002)], 0.006, seg=8, mat="metal_rust")
    # ménsulas bajo el equipo (el brazo entra en el marco frontal de la jaula)
    for x in (-0.22, 0.22):
        _wall_bracket(mb, x, YF + 0.012, -0.0015, 0.32, nz, r, leg_top=-0.006)
    return mb


def ac_unit(kind="window", seed=0, detail="high"):
    """Equipo de aire acondicionado envejecido. kind: 'window' (de ventana 0,60 × 0,40 × 0,45, sobresale 0,31),
    'split_outdoor' (condensadora 0,80 × 0,55 × 0,28 sobre ménsulas, a 7,5 cm del muro) o 'box_old' (equipo viejo de
    ventana 0,66 × 0,44 × 0,56 dentro de una jaula antirrobo, con un panel lateral arrancado).
    Origen: cara del muro (y = 0), centro del equipo en X, z = 0 = apoyo del cuerpo (las ménsulas cuelgan debajo).
    'window' y 'box_old' entran en el muro (y > 0) 0,14 / 0,20: el constructor abre un vano de 0,606 × 0,406 /
    0,666 × 0,446 o lo coloca dentro de una ventana. Carcasa de chapa biselada con abolladuras y manchas metal_rust."""
    with _detail(detail):
        r = rng(seed)
        if kind == "window":
            mb = _ac_window(r)
        elif kind == "split_outdoor":
            mb = _ac_split(r)
        elif kind == "box_old":
            mb = _ac_box_old(r)
        else:
            raise ValueError(f"ac_unit: kind desconocido {kind!r}")
        _declump(mb)
        return mb


# =====================================================================================================================
# cables, conduit
# =====================================================================================================================
def _paint_new(mb, n_before, fn):
    """Aplica fn(centro, normal) -> material|None a las caras creadas después de n_before (manchas de óxido, etc.)."""
    bm = mb.bm
    bm.faces.ensure_lookup_table()
    bm.normal_update()
    for i in range(n_before, len(bm.faces)):
        f = bm.faces[i]
        m = fn(f.calc_center_median(), f.normal)
        if m:
            f.material_index = mb.mi(m)


def _spool(mb, c, axis, mat="plastic"):
    """Aislador de carrete de porcelana (Ø 52 × 55 mm, garganta Ø 32, barreno Ø 18)."""
    M = _frame(_v(c) - _v(axis).normalized() * 0.0275, axis)
    prof = _lv([(0.009, 0.0), (0.024, 0.0), (0.026, 0.0025), (0.026, 0.011), (0.021, 0.016), (0.016, 0.0225), (0.016, 0.0325),
                (0.021, 0.039), (0.026, 0.044), (0.026, 0.0525), (0.024, 0.055), (0.009, 0.055)],
               [(0.009, 0.0), (0.026, 0.0), (0.026, 0.011), (0.016, 0.0225), (0.016, 0.0325), (0.026, 0.044), (0.026, 0.055),
                (0.009, 0.055)],
               [(0.009, 0.0), (0.026, 0.0), (0.016, 0.0225), (0.016, 0.0325), (0.026, 0.055), (0.009, 0.055)])
    _lathe(mb, prof, seg=16, mat=mat, m=M, loop=True)


def _frayed(mb, p, t, rr, n=3, r=0.0011, L=0.04, mat="aluminium"):
    """Punta deshilachada: n alambres que se abren y rizan desde el extremo de un cable cortado."""
    p, t = _v(p), _v(t).normalized()
    a = t.orthogonal().normalized()
    b = t.cross(a)
    for i in range(n):
        ang = 2 * PI * i / n + rr.uniform(-0.4, 0.4)
        sp = a * math.cos(ang) + b * math.sin(ang)
        ln = L * rr.uniform(0.6, 1.2)
        curl = rr.uniform(0.2, 0.8)
        if _LOD.level == "low":  # invisible a > 6 m (la semilla se consume igual)
            continue
        pts = [p - t * 0.006 + sp * 0.0015]
        for k in range(1, 6):
            s = k / 5
            pts.append(p + t * ln * s + sp * (0.0015 + 0.012 * s * s) + b.cross(sp) * curl * 0.01 * s ** 3)
        _tube(mb, pts, r, seg=4, mat=mat, up=b)  # marco fijo: sin anillos torcidos en hilos tan finos


def cable_bundle(points, n=4, sag=0.25, seed=0, r=0.0045, mount=(0.0, -1.0, 0.0), loose=True, detail="high"):
    """Acometida aérea: haz de n cables (Ø 9 mm) en catenaria entre puntos de anclaje, con bastidor de aisladores de
    carrete en cada anclaje, abrazaderas y cinchos cerca de los bastidores, puentes colgantes en anclajes intermedios,
    bucles de goteo hacia una mufa de PVC en los extremos y (loose=True) cables sueltos colgando con puntas deshiladas.
    points: anclajes en coordenadas del constructor, SOBRE la cara del muro/poste (centro del bastidor).
    mount: dirección hacia fuera del muro en los anclajes (por defecto -Y). sag: flecha del haz a media luz (m); cada
    cable cuelga entre 0 y 50 % más que el haz (distinta flecha)."""
    with _detail(detail):
        rr = rng(seed)
        mb = MB()
        P = [_v(p) for p in points]
        if len(P) < 2:
            raise ValueError("cable_bundle: hacen falta >= 2 puntos")
        up = Vector((0, 0, 1))
        out = _v(mount).normalized()
        Yl, Zl = -out, up
        Xl = Yl.cross(Zl).normalized()
        nA = len(P)
        h = (n - 1) * 0.10
        zs = [h / 2 - k * 0.10 for k in range(n)]
        spools = []
        for i, A in enumerate(P):
            Ma = _basis(A, Xl, Yl, Zl)
            _box(mb, (-0.0225, -0.0065, -h / 2 - 0.075), (0.0225, -0.0015, h / 2 + 0.075), "metal_rust", bevel=0.0015, seg=1, m=Ma)
            for zb in (h / 2 + 0.05, -h / 2 - 0.05):
                _bolt(mb, Ma @ Vector((0, -0.0065, zb)), out, r=0.0065)
            row = []
            for k, z in enumerate(zs):
                for dz in (-0.031, 0.031):
                    _box(mb, (-0.02, -0.092, z + dz - 0.002), (0.02, -0.0055, z + dz + 0.002), "metal_rust", bevel=0.001, seg=1, m=Ma)
                _cyl(mb, Ma @ Vector((0, -0.065, z - 0.037)), Ma @ Vector((0, -0.065, z + 0.04)), 0.0055, seg=8, mat="metal_rust")
                _cyl(mb, Ma @ Vector((0, -0.065, z + 0.0325)), Ma @ Vector((0, -0.065, z + 0.039)), 0.0095, seg=6, mat="metal_rust")
                c = Ma @ Vector((0, -0.065, z))
                _spool(mb, c, Zl)
                row.append(c)
            spools.append(row)
        # mufas (entrada al muro) en los extremos
        heads = {}
        for i in (0, nA - 1):
            Ma = _basis(P[i], Xl, Yl, Zl)
            sgn = -1.0 if i == 0 else 1.0
            if nA > 1:
                dd = (P[1] - P[0]) if i == 0 else (P[-2] - P[-1])
                sgn = -1.0 if dd.dot(Xl) > 0 else 1.0
            hx, hz = sgn * 0.16, -h / 2 - 0.10
            pts = _fillet([(hx, 0.03, hz + 0.09), (hx, -0.06, hz + 0.09), (hx, -0.06, hz)], 0.04, 6)
            _tube(mb, [Ma @ p for p in pts], 0.021, seg=14, mat="plastic")
            heads[i] = (Ma @ Vector((hx, -0.06, hz + 0.03)), Ma @ Vector((hx, -0.06, hz - 0.04)))

        def hdir(a, b):
            d = b - a
            d = d - up * d.dot(up)
            if d.length < 1e-6:
                d = Xl.copy()
            return d.normalized()

        def wrap(S, d, zo):
            e2 = up.cross(d).normalized()
            rho = 0.0215
            c = S + up * zo
            pts = [c - e2 * rho + d * 0.05]
            pts += [c + (d * math.cos(ph) + e2 * math.sin(ph)) * rho for ph in [1.5 * PI - PI * i / 8 for i in range(9)]]
            pts.append(c + e2 * rho + d * 0.05)
            return pts  # lado de la cola -> lado del vano

        rb = 0.0 if n == 1 else r * 1.18 / math.sin(PI / n)
        nsp = nA - 1
        brk = None
        if loose and n >= 2:
            brk = (int(rr.integers(0, nsp)), int(rr.integers(0, n)), rr.uniform(0.3, 0.65))
        span_data = []
        for s in range(nsp):
            A, B = P[s] + out * 0.065, P[s + 1] + out * 0.065
            L = (B - A).length
            sg = sag * rr.uniform(0.85, 1.15)
            chord = (B - A).normalized()
            Nn = up - chord * up.dot(chord)
            Nn = Nn.normalized() if Nn.length > 1e-4 else Xl.copy()
            Bb = chord.cross(Nn)
            f = min(0.55 / max(L, 0.1), 0.25)
            extras = [rr.uniform(0.0, 0.5) * sg for _ in range(n)]
            span_data.append(dict(A=A, B=B, L=L, sag=sg, Nn=Nn, Bb=Bb, f=f, extras=extras, phase=rr.uniform(0, 2 * PI),
                                  twist=rr.choice([-1, 1]) * 2 * PI / rr.uniform(0.7, 1.4)))

        def Cpt(sd, t):
            return sd["A"].lerp(sd["B"], t) - up * sd["sag"] * 4 * t * (1 - t)

        def strand_span(sd, k):
            L, f = sd["L"], sd["f"]
            nseg = max(12, int(L * (1 - 2 * f) / 0.05))
            pts = []
            for i in range(nseg + 1):
                u = i / nseg
                t = f + (1 - 2 * f) * u
                ang = 2 * PI * k / n + sd["phase"] + sd["twist"] * u * L
                pts.append(Cpt(sd, t) + (sd["Nn"] * math.cos(ang) + sd["Bb"] * math.sin(ang)) * rb
                           - up * sd["extras"][k] * 4 * u * (1 - u))
            return pts

        def link(p0, d0, p1, d1, n_=8):
            L = (p1 - p0).length
            return _bezier(p0, p0 + d0 * L * 0.4, p1 - d1 * L * 0.4, p1, n_)[1:-1]

        def tan_at(sd, t):
            return (Cpt(sd, min(t + 0.01, 1)) - Cpt(sd, max(t - 0.01, 0))).normalized()

        pieces = []  # (puntos, extremo_inicial_libre, extremo_final_libre)
        for k in range(n):
            zo_in, zo_out = 0.005, -0.005
            # cola inicial: mufa -> bucle de goteo -> carrete
            d0 = hdir(P[0], P[1])
            w0 = wrap(spools[0][k], d0, zo_out)
            hin, hmouth = heads[0]
            lb = hmouth.lerp(w0[0], 0.5) - up * (0.22 + 0.025 * k) + out * 0.02 * k
            path = _spline([hin, hmouth, lb, w0[0] + d0 * 0.06 - up * 0.08], 0.03)[:-1] + w0
            free0 = False
            for s in range(nsp):
                sd = span_data[s]
                sp = strand_span(sd, k)
                dA = hdir(P[s], P[s + 1])
                path += link(path[-1], dA, sp[0], tan_at(sd, sd["f"]))
                dB = hdir(P[s + 1], P[s])
                wB = list(reversed(wrap(spools[s + 1][k], dB, zo_in)))
                if brk is not None and brk[0] == s and brk[1] == k:
                    ib = int(len(sp) * brk[2])
                    pb = sp[ib]
                    hang = rr.uniform(0.7, 1.5)
                    drift = sd["Nn"].cross(up).normalized() * rr.uniform(-0.15, 0.15)
                    tail = _spline([pb, pb + (sp[ib] - sp[ib - 1]).normalized() * 0.08 - up * 0.1, pb - up * hang * 0.6 + drift * 0.6,
                                    pb - up * hang + drift], 0.04)
                    path += sp[:ib] + tail[1:]
                    pieces.append((path, free0, True))
                    # el otro trozo cuelga desde la abrazadera del lado B
                    cb = sp[-1]
                    hang2 = rr.uniform(0.5, 1.1)
                    h2 = _spline([cb - up * hang2 + drift * 0.4, cb - up * hang2 * 0.5 + drift * 0.2, cb - up * 0.04, cb], 0.04)
                    path = h2[:-1] + sp[-3:] + link(sp[-1], tan_at(sd, 1 - sd["f"]), wB[0], -dB) + wB
                    free0 = True
                else:
                    path += sp + link(sp[-1], tan_at(sd, 1 - sd["f"]), wB[0], -dB) + wB
                if s + 1 < nsp:  # puente colgante en el anclaje intermedio
                    dN = hdir(P[s + 1], P[s + 2])
                    wN = wrap(spools[s + 1][k], dN, zo_out)
                    S = spools[s + 1][k]
                    drop = 0.12 + 0.035 * k + rr.uniform(0, 0.03)
                    Tb, Ta = path[-1], wN[0]
                    nj = 14
                    for j in range(1, nj):
                        t = j / nj
                        sn = math.sin(PI * t)
                        path.append(Tb.lerp(Ta, t) - up * drop * sn ** 0.8 + out * (0.03 + 0.01 * k) * sn
                                    + (dB * (1 - t) + dN * t) * 0.06 * sn)
                    path += wN
            # cola final
            hin, hmouth = heads[nA - 1]
            lb = hmouth.lerp(path[-1], 0.5) - up * (0.22 + 0.025 * k) + out * 0.02 * k
            dL = hdir(P[-1], P[-2])
            path += _spline([path[-1], path[-1] + dL * 0.06 - up * 0.08, lb, hmouth, hin], 0.03)[1:]
            pieces.append((path, free0, False))
        for (pts, f0, f1) in pieces:
            _tube(mb, pts, r, seg=6, mat="cable")
            if f0:
                _frayed(mb, pts[0], pts[0] - pts[1], rr)
            if f1:
                _frayed(mb, pts[-1], pts[-1] - pts[-2], rr)
        # abrazaderas (2 bandas + oreja con tornillo) junto a cada bastidor, y cinchos de plástico
        for sd in span_data:
            for t in (sd["f"], 1 - sd["f"]):
                c, tg = Cpt(sd, t), tan_at(sd, t)
                for o in (-0.012, 0.012):
                    _torus(mb, c + tg * o, tg, rb + r + 0.0028, 0.0022, n=16, seg=4, mat="metal_rust")
                side = tg.cross(up).normalized()
                Mt = _frame(c + side * (rb + r + 0.012), tg, side)
                _box(mb, (-0.011, -0.004, -0.018), (0.011, 0.004, 0.018), "metal_rust", bevel=0.0015, seg=1, m=Mt)
                _cyl(mb, c + side * (rb + r + 0.004) - tg * 0.0, c + side * (rb + r + 0.022), 0.0035, seg=6, mat="metal_rust")
            for u in (0.035, 0.965):
                t = sd["f"] + (1 - 2 * sd["f"]) * u
                tg = tan_at(sd, t)
                sp = []
                for k in range(n):
                    ang = 2 * PI * k / n + sd["phase"] + sd["twist"] * u * sd["L"]
                    sp.append(Cpt(sd, t) + (sd["Nn"] * math.cos(ang) + sd["Bb"] * math.sin(ang)) * rb
                              - up * sd["extras"][k] * 4 * u * (1 - u))
                c = sum(sp, Vector((0, 0, 0))) / n
                rad = max((p_ - c).length for p_ in sp) + r + 0.0016
                _torus(mb, c, tg, rad, 0.0014, n=14, seg=4, mat="plastic")
        # cable abandonado colgando del último bastidor
        if loose:
            S = spools[-1][-1]
            top = S - up * 0.036 + out * 0.004
            hang = rr.uniform(1.0, 2.2)
            sw = Xl * rr.uniform(-0.3, 0.3)
            pts = _spline([top + Xl * 0.02, top - up * 0.05 + out * 0.04, top - up * hang * 0.5 + out * 0.12 + sw * 0.5,
                           top - up * hang + out * 0.06 + sw], 0.04)
            _tube(mb, pts, r * 0.9, seg=6, mat="cable")
            _frayed(mb, pts[-1], pts[-1] - pts[-2], rr)
            _torus(mb, top + Xl * 0.004, Xl, 0.007, 0.0016, n=10, seg=4, mat="aluminium")
        _declump(mb)
        return mb


def _along(path, s):
    """Punto y tangente a distancia s sobre una polilínea."""
    acc = 0.0
    for a, b in zip(path[:-1], path[1:]):
        L = (b - a).length
        if acc + L >= s and L > 1e-9:
            t = (s - acc) / L
            return a.lerp(b, t), (b - a).normalized()
        acc += L
    return path[-1], (path[-1] - path[-2]).normalized()


def _plen(path):
    return sum((b - a).length for a, b in zip(path[:-1], path[1:]))


def _junction_box(mb, c, nz, rr, size=0.10, depth=0.055, cover="on", wires=False):
    """Caja de registro 4×4" de chapa (bandeja abierta al frente) con tapa atornillada, colgando o arrancada."""
    hs = size / 2
    x0, z0, x1, z1 = c.x - hs, c.z - hs, c.x + hs, c.z + hs
    yb, yf = c.y - 0.0015, c.y - 0.0015 - depth
    n0 = len(mb.bm.faces)
    box = _tray((x0, yf, z0), (x1, yb, z1), "-y", t=0.0014, r=0.005, step=0.025, mat="metal_paint",
                matfn=_rust_fn(nz, z0, z1, thr=0.25))
    _merge(mb, box)
    for (xx, zz) in ((c.x - hs + 0.012, c.z + hs - 0.012), (c.x + hs - 0.012, c.z - hs + 0.012)):
        _cyl(mb, (xx, yf + 0.03, zz), (xx, yf + 0.0005, zz), 0.0045, seg=8, mat="metal_rust")  # orejas con rosca
    for (xx, zz) in ((c.x, c.z + hs), (c.x - hs, c.z), (c.x + hs, c.z), (c.x, c.z - hs)):
        if rr.random() < 0.5:  # tapones de knock-out
            d = Vector((xx - c.x, 0, zz - c.z)).normalized()
            _cyl(mb, Vector((xx, yf + depth * 0.5, zz)) - d * 0.0005, Vector((xx, yf + depth * 0.5, zz)) + d * 0.0012, 0.011,
                   seg=12, mat="metal_paint")
    if cover == "on":
        M = _T(c.x, yf - 0.0011, c.z) @ _R("Y", rr.uniform(-2, 2))
        _box(mb, (-hs - 0.004, -0.0012, -hs - 0.004), (hs + 0.004, 0.0012, hs + 0.004), "metal_paint", bevel=0.0009, seg=1, m=M)
        for (xx, zz) in ((-hs + 0.012, hs - 0.012), (hs - 0.012, -hs + 0.012)):
            _screw(mb, M @ Vector((xx, -0.0012, zz)), (0, -1, 0), r=0.0045)
    elif cover == "hanging":
        piv = Vector((c.x - hs + 0.012, yf - 0.004, c.z + hs - 0.012))
        M = _T(piv) @ _R("Y", rr.uniform(120, 160)) @ _R("Z", rr.uniform(-12, 12))
        _box(mb, (-0.012 - 0.004, -0.0024, -0.012 - 0.004), (size - 0.012 + 0.004, 0.0, size - 0.012 + 0.004), "metal_rust",
               bevel=0.0009, seg=1, m=M @ _T(0, 0, -(size - 0.024)))
        _screw(mb, piv + Vector((0, -0.0024, 0)), (0, -1, 0), r=0.0045)
    if wires:
        for i in range(int(rr.integers(3, 6))):
            o = Vector((rr.uniform(-0.03, 0.03), 0, rr.uniform(-0.03, 0.02)))
            hang = rr.uniform(0.15, 0.6)
            p0 = Vector((c.x, yb - 0.004, c.z)) + o
            pts = _spline([p0, p0 + Vector((0, -0.05, 0.02)), p0 + Vector((rr.uniform(-0.05, 0.05), -0.09, -0.06)),
                           p0 + Vector((rr.uniform(-0.12, 0.12), -0.1 + rr.uniform(-0.03, 0.03), -hang))], 0.02)
            _tube(mb, pts, 0.0018, seg=6, mat="cable")
            _frayed(mb, pts[-1], pts[-1] - pts[-2], rr, n=2, r=0.0007, L=0.015, mat="metal_rust")
    return n0


def conduit(points, seed=0, r=0.0117, standoff=0.003, box_corners=None, detail="high"):
    """Tubería conduit EMT 3/4" (Ø 23 mm) sobre el muro, con curvas de radio 0,12, coples cada 3,05 m, abrazaderas de
    2 orejas cada ~1,2 m (una falta y el tubo se despega), cajas de registro 4×4" en los extremos (la final abierta con
    cables saliendo) y, al azar, cajas en las esquinas en vez de curva.
    points: polilínea SOBRE la cara del muro (plano y = 0 local; se usan x, z). El tubo corre a y = -(r + standoff)."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        mb = MB()
        yc = -(r + standoff)
        P = [Vector((float(p[0]), yc + float(p[1]) if len(p) > 2 else yc, float(p[2]) if len(p) > 2 else float(p[1])))
             for p in points]
        nP = len(P)
        if box_corners is None:
            box_corners = [i for i in range(1, nP - 1) if rr.random() < 0.35]
        boxes = [0] + list(box_corners) + [nP - 1]
        runs = []
        for a, b in zip(boxes[:-1], boxes[1:]):
            seg_ = P[a:b + 1]
            da = (seg_[1] - seg_[0]).normalized()
            db = (seg_[-1] - seg_[-2]).normalized()
            seg_ = [seg_[0] + da * 0.044] + seg_[1:-1] + [seg_[-1] - db * 0.044]
            runs.append(seg_)
        end_cover = ["on", "hanging", "off"][int(rr.integers(0, 3))]
        for bi, idx in enumerate(boxes):
            last = bi == len(boxes) - 1
            cov = end_cover if last else ("on" if rr.random() < 0.8 else "hanging")
            _junction_box(mb, Vector((P[idx].x, -0.0, P[idx].z)), nz, rr, cover=cov, wires=last and cov != "on")
        missing_done = False
        for run in runs:
            path = _fillet(run, 0.12, 8)
            path = _densify(path, 0.2)
            L = _plen(path)
            # posiciones de abrazaderas
            straps = [0.22]
            while straps[-1] + 1.2 < L - 0.22:
                straps.append(straps[-1] + rr.uniform(1.0, 1.35))
            if L > 0.6:
                straps.append(L - 0.22)
            miss = -1
            if not missing_done and len(straps) >= 3:
                miss = int(rr.integers(1, len(straps) - 1))
                missing_done = True
            # deformación: arqueo leve y despegue donde falta la abrazadera
            acc = [0.0]
            for a, b in zip(path[:-1], path[1:]):
                acc.append(acc[-1] + (b - a).length)
            newp = []
            for p, s in zip(path, acc):
                q = p.copy()
                w = math.sin(PI * min(max(s / max(L, 1e-6), 0), 1))
                q.y -= 0.003 * w * (0.5 + 0.5 * nz(q, 0.7))
                q.x += 0.002 * nz(q + Vector((3, 0, 0)), 1.3) * w
                q.z += 0.002 * nz(q + Vector((0, 0, 7)), 1.3) * w
                if miss >= 0:
                    dist = abs(s - straps[miss])
                    if dist < 0.9:
                        q.y -= 0.022 * 0.5 * (1 + math.cos(PI * dist / 0.9))
                newp.append(q)
            path = newp
            n0 = len(mb.bm.faces)
            _tube(mb, path, r, seg=10, mat="metal_paint")
            _paint_new(mb, n0, lambda c, n: "metal_rust" if nz(c, 2.5) + 0.3 * nz(c, 9.0) > 0.38 else None)
            # coples
            s = rr.uniform(0.6, 2.4)
            while s < L - 0.1:
                p, t = _along(path, s)
                _cyl(mb, p - t * 0.022, p + t * 0.022, r + 0.0022, seg=12, mat="metal_paint")
                side = t.cross(Vector((0, 1, 0))).normalized() if abs(t.y) < 0.9 else Vector((1, 0, 0))
                for o in (-0.011, 0.011):
                    q = p + t * o
                    _cyl(mb, q - Vector((0, 1, 0)) * 0.0, q - Vector((0, 1, 0)) * (r + 0.006), 0.0028, seg=6, mat="metal_rust")
                s += 3.05
            # abrazaderas de 2 orejas
            for i, s in enumerate(straps):
                p, t = _along(path, s)
                t = Vector((t.x, 0.0, t.z)).normalized()
                w = t.cross(Vector((0, 1, 0))).normalized()
                if i == miss:
                    _screw(mb, Vector((p.x, 0.0, p.z)) + w * 0.03 + Vector((0, -0.006, 0)), (0, -1, 0), r=0.0045)
                    continue
                R_ = r + 0.0009
                c = Vector((p.x, p.y, p.z))
                yw = -0.0016
                na = _lv(12, 6, 4)
                arc = [c + (w * math.cos(ph) + Vector((0, -1, 0)) * math.sin(ph)) * R_ for ph in [PI * k / na for k in range(na + 1)]]
                path_s = ([Vector((c.x, yw, c.z)) - w * (R_ + 0.026), Vector((c.x, yw, c.z)) - w * (R_ + 0.003)]
                          + list(reversed(arc)) + [Vector((c.x, yw, c.z)) + w * (R_ + 0.003), Vector((c.x, yw, c.z)) + w * (R_ + 0.026)])
                mb.sweep([(0.0, -0.009), (0.0015, -0.009), (0.0015, 0.009), (0.0, 0.009)], path_s, mat="metal_rust", normal=t)
                for sg in (-1, 1):
                    _screw(mb, Vector((c.x, yw - 0.0015, c.z)) + w * sg * (R_ + 0.016), (0, -1, 0), r=0.0042)
        _declump(mb)
        return mb


# =====================================================================================================================
# medidor, lámparas, antenas
# =====================================================================================================================
def _shards_ring(mb, M, R, rr, n=7, t=0.003, h=(0.01, 0.04), mat="glass"):
    """Esquirlas de vidrio (prismas triangulares de espesor t) que quedan pegadas al borde de un hueco circular de radio R
    (plano XY local de M, normal +Z)."""
    for i in range(n):
        a = rr.uniform(0, 2 * PI)
        w = rr.uniform(0.15, 0.45)
        hh = rr.uniform(*h)
        pts2 = [(R * math.cos(a - w / 2), R * math.sin(a - w / 2)), (R * math.cos(a + w / 2), R * math.sin(a + w / 2)),
                ((R - hh) * math.cos(a + rr.uniform(-w / 3, w / 3)), (R - hh) * math.sin(a + rr.uniform(-w / 3, w / 3)))]
        # cada esquirla queda ladeada en su ranura (giro alrededor de su borde pegado): nunca coplanar con sus vecinas
        _shard_plate(mb, [(x * 1.02, y * 1.02) for x, y in pts2], t, mat, M, rr, i)


def _shard_plate(mb, pts2, t, mat, M, rr, i):
    """Esquirla de vidrio (prisma de espesor t) en el plano XY local de M, girada 3–9° alrededor de su borde de apoyo
    (pts2[0] -> pts2[1]) y desplazada 0,45 mm × (i mod 7 − 3) en su normal: las que se traslapan no son coplanares."""
    a, b = Vector((pts2[0][0], pts2[0][1], 0.0)), Vector((pts2[1][0], pts2[1][1], 0.0))
    ax = (b - a).normalized() if (b - a).length > 1e-9 else Vector((1, 0, 0))
    ang = math.radians(rr.uniform(3.0, 9.0)) * (1 if i % 2 == 0 else -1)
    tilt = _about((a + b) / 2, Matrix.Rotation(ang, 4, ax))
    mb.plate(pts2, t, mat, m=M @ _T(0, 0, -t / 2 + 0.00045 * (i % 7 - 3)) @ tilt)


def _hinge(mb, p, h=0.05, r=0.0055, mat="metal_rust"):
    p = _v(p)
    _cyl(mb, p - Vector((0, 0, h / 2)), p + Vector((0, 0, h / 2)), r, seg=10, mat=mat)
    _cyl(mb, p + Vector((0, 0, h / 2 - 0.001)), p + Vector((0, 0, h / 2 + 0.004)), r * 0.6, seg=8, mat=mat)


def _padlock(mb, p, rr, open_=True):
    """Candado colgando (cuerpo con bisel + arco abierto) de un punto p (centro del arco)."""
    p = _v(p)
    rot = _R("Z", rr.uniform(-25, 25)) @ _R("X", rr.uniform(-12, 12))
    M = _T(p) @ rot
    arc = [M @ Vector((0.012 * math.cos(a), 0, -0.02 + 0.016 * math.sin(a) + (0.012 if open_ and a < PI / 2 else 0.0)))
           for a in [PI * i / 12 for i in range(13)]]
    _tube(mb, [M @ Vector((0.012, 0, -0.035))] + arc[1:] + [M @ Vector((-0.012, 0, -0.035))], 0.0032, seg=6, mat="aluminium")
    _box(mb, (-0.021, -0.008, -0.07), (0.021, 0.008, -0.03), "metal_rust", bevel=0.004, seg=2, m=M)
    _cyl(mb, M @ Vector((0, -0.0085, -0.058)), M @ Vector((0, -0.0075, -0.058)), 0.004, seg=10, mat="aluminium")


def meter_box(seed=0, open_door=True, detail="high"):
    """Gabinete de medidor de chapa (0,36 × 0,50 × 0,17) con puerta de ventanilla redonda (vidrio roto) abierta o
    entreabierta, base de medidor (con medidor o con las mordazas vacías), interruptor, tubo conduit que baja del muro
    y un enredo de cables colgando por abajo. Origen: cara del muro, centro del gabinete en X, z = 0 = fondo del gabinete."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        mb = MB()
        W, H, D = 0.36, 0.50, 0.17
        x0, x1, yb, yf = -W / 2, W / 2, -0.0015, -0.0015 - D
        dents = _rand_dents(rr, (x0, yf, 0), (x1, yb, H), int(rr.integers(1, 4)), faces=("+x", "-x", "+z"),
                            region=((x0 + 0.04, yf + 0.04, 0.05), (x1 - 0.04, yb - 0.04, H - 0.05)), R=(0.03, 0.07), depth=(0.002, 0.006))
        deform = _deformer(dents, nz, amp=0.0006, freq=6.0)
        body = _tray((x0, yf, 0.0), (x1, yb, H), "-y", t=0.0015, r=0.008, step=0.03, mat="metal_paint", deform=deform,
                     matfn=_rust_fn(nz, 0.0, H, thr=0.3))
        _merge(mb, body)
        # ceja enrollada del marco
        rim = _fillet([(x0 + 0.0008, yf + 0.0012, 0.0008), (x1 - 0.0008, yf + 0.0012, 0.0008), (x1 - 0.0008, yf + 0.0012, H - 0.0008),
                       (x0 + 0.0008, yf + 0.0012, H - 0.0008), (x0 + 0.0008, yf + 0.0012, 0.0008), (x1 - 0.0008, yf + 0.0012, 0.0008)], 0.008, 3)[1:-1]
        _tube(mb, rim, 0.0024, seg=6, mat="metal_paint", closed=True, up=(0, 1, 0))
        # tablero de fondo + base de medidor + interruptor
        _box(mb, (x0 + 0.025, yb - 0.016, 0.03), (x1 - 0.025, yb - 0.004, H - 0.03), "wood_dark", bevel=0.002, seg=1)
        sy = yb - 0.016
        _box(mb, (-0.085, sy - 0.035, 0.20), (0.085, sy + 0.002, 0.44), "metal_paint", bevel=0.006, seg=2)
        Mm = _frame((0, sy - 0.035, 0.32), (0, -1, 0))
        _lathe(mb, [(0.0, 0.0), (0.082, 0.0), (0.084, 0.004), (0.084, 0.012), (0.078, 0.016), (0.0, 0.016)], seg=40, mat="metal_paint",
               m=Mm @ _T(0, 0, -0.0005))
        meter = rr.random() < 0.55
        if meter:
            _lathe(mb, [(0.0, 0.0), (0.07, 0.0), (0.072, 0.03), (0.07, 0.034), (0.0, 0.034)], seg=36, mat="plastic", m=Mm @ _T(0, 0, 0.0155))
            _box(mb, (-0.045, -0.02, 0.0), (0.045, 0.02, 0.012), "aluminium", bevel=0.002, seg=1, m=Mm @ _T(0, 0.01, 0.049))
            dome = MB()
            prof = [(0.071, 0.0), (0.072, 0.06), (0.068, 0.085), (0.055, 0.1), (0.03, 0.108), (0.0, 0.11)]
            _lathe(dome, prof, seg=36, mat="glass", caps=False, m=Mm @ _T(0, 0, 0.033))
            cut = rr.uniform(0.0, 2 * PI)
            rm = [f for f in dome.bm.faces if f.calc_center_median().z > 0.30 and
                  math.cos(math.atan2(f.calc_center_median().x, -(f.calc_center_median().z - 0.32)) - cut) > 0.3]
            bmesh.ops.delete(dome.bm, geom=rm, context="FACES")
            _solidify(dome, 0.0025)
            _merge(mb, dome)
        else:
            for (xx, zz) in ((-0.035, 0.36), (0.035, 0.36), (-0.035, 0.28), (0.035, 0.28)):
                _box(mb, (xx - 0.004, sy - 0.07, zz - 0.012), (xx + 0.004, sy - 0.03, zz + 0.012), "aluminium", bevel=0.0012, seg=1)
                _box(mb, (xx - 0.0045 + 0.0035 * (1 if xx > 0 else -1), sy - 0.072, zz - 0.010), (xx + 0.0045 + 0.0035 * (1 if xx > 0 else -1), sy - 0.06, zz + 0.010),
                       "aluminium", bevel=0.001, seg=1)
        _box(mb, (-0.05, sy - 0.07, 0.07), (0.05, sy + 0.002, 0.17), "plastic", bevel=0.005, seg=2)
        lev = rr.uniform(-30, 30)
        _box(mb, (-0.008, -0.03, -0.006), (0.008, 0.0, 0.006), "plastic", bevel=0.002, seg=1, m=_T(0, sy - 0.069, 0.12) @ _R("X", lev))
        # conduit que baja del muro al techo del gabinete + cables internos
        cpath = _fillet([(0.05, 0.03, H + 0.32), (0.05, -0.06, H + 0.32), (0.05, -0.06, H - 0.01)], 0.1, 8)
        _tube(mb, cpath, 0.0117, seg=10, mat="metal_paint")
        _cyl(mb, (0.05, -0.06, H + 0.004), (0.05, -0.06, H + 0.03), 0.016, seg=12, mat="metal_rust")
        for i in range(3):
            o = (i - 1) * 0.012
            p0 = Vector((0.05 + o, -0.06, H + 0.01))
            top_to_meter = _spline([p0, p0 + Vector((0, 0, -0.05)), Vector((0.06 + o, sy - 0.03, 0.47)), Vector((0.02 + o, sy - 0.05, 0.43))], 0.02)
            _tube(mb, top_to_meter, 0.0045, seg=6, mat="cable")
            b0 = Vector((o * 2, sy - 0.04, 0.205))
            _tube(mb, _spline([b0, b0 + Vector((0, -0.01, -0.02)), Vector((o * 2, sy - 0.06, 0.16))], 0.02), 0.0035, seg=6, mat="cable")
        # cables que salen por abajo y cuelgan enredados
        for i in range(int(rr.integers(4, 8))):
            p0 = Vector((rr.uniform(-0.08, 0.08), rr.uniform(yf + 0.03, yb - 0.04), 0.075))
            hang = rr.uniform(0.25, 1.1)
            sw = Vector((rr.uniform(-0.25, 0.25), rr.uniform(-0.15, 0.05), 0))
            pts = _spline([Vector((p0.x * 0.6, sy - 0.06, 0.08)), p0 + Vector((0, 0, -0.06)), p0 + Vector((0, 0, -0.12)),
                           p0 + sw * 0.4 + Vector((0, 0, -hang * 0.5)), p0 + sw * 0.7 + Vector((rr.uniform(-0.1, 0.1), 0, -hang * 0.8)),
                           p0 + sw + Vector((0, 0, -hang))], 0.025)
            rad = rr.choice([0.0025, 0.0035, 0.0045])
            _tube(mb, pts, rad, seg=6, mat="cable")
            if rr.random() < 0.6:
                _frayed(mb, pts[-1], pts[-1] - pts[-2], rr, n=2, r=0.0008, L=0.02, mat="metal_rust")
        for xx in (-0.06, 0.0, 0.06):  # pasacables en el fondo
            _cyl(mb, (xx, (yf + yb) / 2, -0.004), (xx, (yf + yb) / 2, 0.006), 0.012, seg=12, mat="plastic")
        # puerta con ventanilla redonda (vidrio roto), bisagras a la izquierda, porta-candado a la derecha
        ang = rr.uniform(100, 155) if open_door else rr.uniform(3, 12)
        droop = rr.uniform(0.5, 4.0)
        piv = Vector((x0 - 0.004, yf - 0.006, 0.0))
        Md = _T(piv) @ _R("Z", -ang) @ _R("Y", -droop)
        dw, dh = W + 0.008, H + 0.008
        door = _holed_panel(0.004, -0.004, 0.004 + dw, -0.004 + dh, 0.004 + dw / 2, 0.33, 0.058, 0.0015, "metal_paint",
                            n=_lv(40, 28, 16), rings=_lv(3, 2, 1), y=-0.0015)
        _merge(mb, door, Md)
        # marco de la puerta: 0,5 mm dentro del canto del panel (sin biseles en mid/low quedaba coplanar con el canto)
        for (a, b, c, d) in ((0.0045, 0.0035 + dw, -0.0035, 0.006), (0.0045, 0.0035 + dw, dh - 0.014, dh - 0.0045),
                             (0.0045, 0.014, 0.0065, dh - 0.0145), (dw - 0.006, dw + 0.0035, 0.0065, dh - 0.0145)):
            _box(mb, (a, -0.0005, c), (b, 0.011, d), "metal_paint", bevel=0.0006, seg=1, m=Md)
        Mw = Md @ _T(0.004 + dw / 2, -0.0019, 0.33) @ _R("X", 90)
        _tube(mb, [Mw @ Vector((0.0625 * math.cos(a), 0.0625 * math.sin(a), 0.0)) for a in [2 * PI * i / 28 for i in range(28)]], 0.003,
              seg=6, mat="plastic", closed=True, up=Mw.to_3x3() @ Vector((0, 0, 1)))
        _shards_ring(mb, Mw @ _T(0, 0, 0.004), 0.058, rr, n=int(rr.integers(3, 7)))
        _box(mb, (dw - 0.02, -0.012, 0.22), (dw + 0.002, -0.0005, 0.25), "metal_rust", bevel=0.0015, seg=1, m=Md)  # aldaba
        for zh in (0.07, H - 0.07):
            _hinge(mb, piv + Vector((0, 0, zh)))
            _box(mb, (x0 - 0.002, yf - 0.004, zh - 0.02), (x0 + 0.02, yf + 0.0015, zh + 0.02), "metal_rust", bevel=0.001, seg=1)
        # armella + candado abierto en el gabinete
        st = Vector((x1 + 0.006, yf + 0.02, 0.235))
        _box(mb, (x1 - 0.002, yf + 0.008, 0.215), (x1 + 0.004, yf + 0.032, 0.255), "metal_rust", bevel=0.0012, seg=1)
        _tube(mb, _fillet([(x1 + 0.002, yf + 0.012, 0.235), (x1 + 0.022, yf + 0.012, 0.235), (x1 + 0.022, yf + 0.028, 0.235),
                           (x1 + 0.002, yf + 0.028, 0.235)], 0.006, 4), 0.0028, seg=6, mat="metal_rust")
        if rr.random() < 0.7:
            _padlock(mb, st + Vector((0.016, 0.0, -0.002)), rr)
        _declump(mb)
        return mb


def light_fixture(kind="wall", seed=0, detail="high"):
    """Luminaria exterior rota. kind='wall': arbotante tipo tortuga (base fundida Ø 0,24, rejilla de 4 arcos, globo de
    vidrio partido, socket con el bulbo roto). kind='bracket': brazo de cuello de ganso con pantalla de lámina abollada
    colgando chueca y cable suelto. Origen: cara del muro, centro de la placa de anclaje (z = 0 = centro de la placa)."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        mb = MB()
        if kind == "wall":
            M = _frame((0, -0.0015, 0), (0, -1, 0))
            _lathe(mb, [(0.0, 0.0), (0.115, 0.0), (0.119, 0.004), (0.119, 0.028), (0.112, 0.042), (0.098, 0.05), (0.0, 0.05)], seg=40,
                   mat="metal_paint", m=M)
            _torus(mb, M @ Vector((0, 0, 0.05)), M.to_3x3() @ Vector((0, 0, 1)), 0.096, 0.0065, n=40, seg=8, mat="metal_paint")
            for a in range(4):  # tornillos de anclaje
                aa = PI / 4 + a * PI / 2
                _screw(mb, M @ Vector((0.085 * math.cos(aa), 0.085 * math.sin(aa), 0.046)), M.to_3x3() @ Vector((0, 0, 1)), r=0.005)
            # globo partido
            brk = [rr.uniform(0.25, 0.75) for _ in range(9)]
            grid = []
            nt, nph = _lv((36, 10), (24, 6), (16, 4))
            for i in range(nt + 1):
                th = 2 * PI * i / nt
                col = []
                for j in range(nph + 1):
                    ph = (PI / 2) * j / nph
                    col.append(M @ Vector((0.088 * math.cos(ph) * math.cos(th), 0.088 * math.cos(ph) * math.sin(th), 0.052 + 0.07 * math.sin(ph))))
                grid.append(col)

            def keep(i, j):
                k = (i * 9) // nt
                lim = brk[k] + (brk[(k + 1) % 9] - brk[k]) * ((i * 9 / nt) - k)
                return j / nph > lim + 0.06 * math.sin(i * 2.7)

            glob = _solid_sheet(grid, 0.003, "glass", skip=keep, wrap=True)
            _merge(mb, glob)
            # rejilla: 4 arcos + tapa central (uno doblado)
            bent = int(rr.integers(0, 4))
            for a in range(4):
                th = PI / 4 + a * PI / 2
                pts = []
                for j in range(13):
                    ph = (PI / 2) * j / 12
                    rad = 0.098
                    p = Vector((rad * math.cos(ph) * math.cos(th), rad * math.cos(ph) * math.sin(th), 0.05 + 0.081 * math.sin(ph)))
                    if a == bent:
                        p += Vector((math.cos(th), math.sin(th), 0.0)) * 0.03 * math.sin(ph) ** 3 + Vector((0, 0, -0.02)) * math.sin(ph) ** 4
                    pts.append(M @ p)
                _tube(mb, pts, 0.0035, seg=6, mat="metal_paint")
            _lathe(mb, [(0.0, 0.124), (0.02, 0.124), (0.022, 0.13), (0.0, 0.134)], seg=16, mat="metal_paint", m=M)
            # socket + base del foco roto + filamento
            _lathe(mb, [(0.0, 0.049), (0.022, 0.049), (0.022, 0.075), (0.016, 0.082), (0.0, 0.082)], seg=20, mat="plastic", m=M)
            _lathe(mb, [(0.0, 0.08), (0.0135, 0.08), (0.0135, 0.088), (0.0125, 0.091), (0.0135, 0.094), (0.0125, 0.097), (0.0135, 0.1),
                        (0.0, 0.1)], seg=16, mat="aluminium", m=M)
            _shards_ring(mb, M @ _T(0, 0, 0.1) @ _R("X", 90) @ _R("X", -90), 0.0135, rr, n=4, t=0.0012, h=(0.004, 0.012))
            for sx in (-1, 1):
                _tube(mb, [M @ Vector((0.003 * sx, 0, 0.098)), M @ Vector((0.004 * sx, 0.001, 0.115)), M @ Vector((0.0 + 0.002 * sx, 0.004, 0.126))],
                      0.0007, seg=4, mat="aluminium")
            # cable de alimentación saliendo por abajo, cortado
            pts = _spline([(0.0, 0.02, -0.06), (0.0, -0.02, -0.07), (0.01, -0.05, -0.10), (0.03, -0.06, -0.25)], 0.02)
            _tube(mb, pts, 0.0035, seg=6, mat="cable")
            _frayed(mb, pts[-1], pts[-1] - pts[-2], rr, n=2, r=0.0008, L=0.015, mat="metal_rust")
        elif kind == "bracket":
            M = _frame((0, -0.0015, 0), (0, -1, 0))
            _lathe(mb, [(0.0, 0.0), (0.06, 0.0), (0.062, 0.003), (0.062, 0.01), (0.05, 0.016), (0.02, 0.018), (0.0, 0.018)], seg=32,
                   mat="metal_rust", m=M)
            for a in range(3):
                aa = PI / 2 + a * 2 * PI / 3
                _screw(mb, M @ Vector((0.045 * math.cos(aa), 0.045 * math.sin(aa), 0.012)), M.to_3x3() @ Vector((0, 0, 1)), r=0.005)
            reach = rr.uniform(0.38, 0.5)
            arm = _spline([(0, -0.01, 0.0), (0, -0.08, 0.01), (0, -0.2, 0.09), (0, -reach + 0.06, 0.15), (0, -reach, 0.11),
                           (0, -reach - 0.01, 0.06)], 0.02)
            arm = [p + Vector((0.004 * nz(p, 8), 0, 0.003 * nz(p + Vector((0, 0, 4)), 8))) for p in arm]
            _tube(mb, arm, 0.011, seg=10, mat="metal_rust")
            neck = arm[-1]
            _cyl(mb, neck + Vector((0, 0, 0.012)), neck - Vector((0, 0, 0.02)), 0.016, seg=12, mat="metal_rust")
            tilt = rr.uniform(18, 45)
            Ms = _T(neck - Vector((0, 0, 0.02))) @ _R("X", tilt) @ _R("Y", rr.uniform(-12, 12)) @ _R("X", 180)
            sh = MB()
            dents = [(Vector((rr.uniform(-0.1, 0.1), rr.uniform(-0.1, 0.1), 0.05)), Vector((0, 0, 1)), rr.uniform(0.03, 0.07),
                      rr.uniform(0.006, 0.015)) for _ in range(2)]

            def dfm(p, a, rad, z):
                q = p.copy()
                for (c, d, R_, dep) in dents:
                    dist = (Vector((p.x, p.y, 0)) - Vector((c.x, c.y, 0))).length
                    if dist < R_:
                        q.z += dep * 0.5 * (1 + math.cos(PI * dist / R_))
                q.z += 0.003 * nz(p, 12)
                return q

            _lathe(sh, [(0.016, 0.0), (0.03, 0.006), (0.07, 0.03), (0.12, 0.065), (0.155, 0.09), (0.17, 0.1)], seg=40, mat="metal_rust",
                   caps=False, deform=dfm)
            _solidify(sh, 0.0012)
            _merge(mb, sh, Ms)
            rim = [Ms @ dfm(Vector((0.171 * math.cos(a), 0.171 * math.sin(a), 0.1)), a, 0.171, 0.1) for a in [2 * PI * i / 40 for i in range(40)]]
            _tube(mb, rim, 0.003, seg=6, mat="metal_rust", closed=True, up=Ms.to_3x3() @ Vector((0, 0, 1)))
            _lathe(mb, [(0.0, -0.005), (0.02, -0.005), (0.02, 0.04), (0.015, 0.048), (0.0, 0.048)], seg=16, mat="plastic", m=Ms)
            _lathe(mb, [(0.0, 0.046), (0.0135, 0.046), (0.0135, 0.068), (0.0, 0.068)], seg=16, mat="aluminium", m=Ms)
            _shards_ring(mb, Ms @ _T(0, 0, 0.068), 0.0135, rr, n=3, t=0.0012, h=(0.005, 0.012))
            w0 = neck + Vector((0, 0.01, -0.01))
            pts = _spline([w0, w0 + Vector((0.02, -0.02, -0.06)), w0 + Vector((0.05, -0.04, -0.2)), w0 + Vector((0.06, -0.02, -0.38))], 0.02)
            _tube(mb, pts, 0.003, seg=6, mat="cable")
            _frayed(mb, pts[-1], pts[-1] - pts[-2], rr, n=2, r=0.0008, L=0.015, mat="metal_rust")
        else:
            raise ValueError(f"light_fixture: kind desconocido {kind!r}")
        _declump(mb)
        return mb


def tv_antenna(seed=0, detail="high"):
    """Antena yagi de TV en azotea: trípode de ángulo con zapatas atornilladas, mástil Ø 32 inclinado, 3 vientos (uno
    flojo), botalón cuadrado de 1,4 m con reflector, dipolo plegado con caja de bornes y 8 directores (doblados, uno
    falta), coaxial encintado bajando por el mástil. Origen: base del mástil sobre la losa (z = 0)."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        mb = MB()
        lean = _R("Y", rr.uniform(-5, 5)) @ _R("X", rr.uniform(-4, 4))
        Hm = rr.uniform(2.2, 2.6)
        top = lean @ Vector((0, 0, Hm))
        mast = [lean @ Vector((0, 0, 0.012 + Hm * k / 10)) for k in range(11)]
        _tube(mb, mast, 0.016, seg=12, mat="metal_paint")
        _cyl(mb, top - Vector((0, 0, 0.002)), top + Vector((0, 0, 0.012)), 0.017, seg=12, mat="plastic")
        # trípode
        hc = lean @ Vector((0, 0, 0.9))
        _cyl(mb, hc - Vector((0, 0, 0.04)), hc + Vector((0, 0, 0.04)), 0.024, seg=12, mat="metal_rust")
        a0 = rr.uniform(0, 2 * PI)
        for i in range(3):
            a = a0 + 2 * PI * i / 3
            foot = Vector((0.6 * math.cos(a), 0.6 * math.sin(a), 0.0))
            leg_top = hc + Vector((0.026 * math.cos(a), 0.026 * math.sin(a), -0.02))
            d = (leg_top - foot).normalized()
            nn = d.cross(Vector((-math.sin(a), math.cos(a), 0))).normalized()
            _angle_iron(mb, foot + Vector((0, 0, 0.012)) + d * 0.01, leg_top, nn, a=0.03, t=0.0035)
            Mf = _T(foot) @ _R("Z", math.degrees(a))
            _box(mb, (-0.05, -0.05, 0.0015), (0.05, 0.05, 0.007), "metal_rust", bevel=0.002, seg=1, m=Mf)
            for (bx, by) in ((-0.032, -0.032), (0.032, 0.032), (-0.032, 0.032), (0.032, -0.032)):
                _bolt(mb, Mf @ Vector((bx, by, 0.007)), (0, 0, 1), r=0.006)
            _box(mb, (-0.012, -0.03, 0.006), (0.012, 0.03, 0.05), "metal_rust", bevel=0.002, seg=1, m=Mf @ _T(0.02, 0, 0))
        # vientos
        gr = lean @ Vector((0, 0, Hm * 0.72))
        _torus(mb, gr, lean.to_3x3() @ Vector((0, 0, 1)), 0.022, 0.004, n=16, seg=6, mat="metal_rust")
        loose_i = int(rr.integers(0, 3))
        for i in range(3):
            a = a0 + PI / 3 + 2 * PI * i / 3
            anc = Vector((1.7 * math.cos(a), 1.7 * math.sin(a), 0.02))
            st = gr + Vector((0.024 * math.cos(a), 0.024 * math.sin(a), 0))
            sg = 0.05 if i != loose_i else rr.uniform(0.6, 1.0)
            pts = []
            for k in range(31):
                t = k / 30
                p = st.lerp(anc, t) - Vector((0, 0, sg * 4 * t * (1 - t)))
                if i == loose_i:
                    p.z = max(p.z, 0.004 + 0.0015)
                pts.append(p)
            _tube(mb, pts, 0.0016, seg=4, mat="metal_rust")
            _box(mb, (-0.02, -0.02, 0.0015), (0.02, 0.02, 0.01), "metal_rust", bevel=0.002, seg=1, m=_T(anc.x, anc.y, 0))
            _torus(mb, anc + Vector((0, 0, 0.018)), Vector((-math.sin(a), math.cos(a), 0)), 0.012, 0.003, n=12, seg=4, mat="metal_rust")
        # botalón con abrazadera
        yaw = rr.uniform(0, 360)
        Mb_ = _T(top + lean.to_3x3() @ Vector((0, 0, -0.08))) @ _R("Z", yaw)
        droop = rr.uniform(0.02, 0.07)
        boom = [Vector((-0.45 + 1.4 * k / 10, 0, -droop * max(0, (k - 4) / 6) ** 2)) for k in range(11)]
        mb.sweep([(-0.0095, -0.01), (-0.0075, -0.012), (0.0075, -0.012), (0.0095, -0.01), (0.0095, 0.01), (0.0075, 0.012),
                  (-0.0075, 0.012), (-0.0095, 0.01)], [Mb_ @ p for p in boom], mat="aluminium", normal=Mb_.to_3x3() @ Vector((0, 1, 0)))
        _box(mb, (-0.04, 0.014, -0.035), (0.04, 0.02, 0.035), "metal_rust", bevel=0.002, seg=1, m=Mb_)
        for zz in (-0.022, 0.022):
            _tube(mb, [Mb_ @ p for p in _fillet([(-0.016, 0.035, zz), (-0.016, -0.014, zz), (0.016, -0.014, zz), (0.016, 0.035, zz)], 0.012, 4)],
                  0.003, seg=6, mat="metal_rust")
        for zz in (-0.022, 0.022):
            for xx in (-0.016, 0.016):
                _cyl(mb, Mb_ @ Vector((xx, 0.022, zz)), Mb_ @ Vector((xx, 0.03, zz)), 0.0055, seg=6, mat="metal_rust")

        def boom_at(x):
            k = (x + 0.45) / 1.4 * 10
            return Vector((x, 0, -droop * max(0, (k - 4) / 6) ** 2))

        def element(x, half, r_=0.0045, broken=False, mat="aluminium"):
            c = boom_at(x)
            sk = rr.uniform(-6, 6)
            Me = Mb_ @ _T(c) @ _R("Z", sk)
            for sgn in (-1, 1):
                hh = half * (rr.uniform(0.35, 0.7) if (broken and sgn > 0) else 1.0)
                dro = rr.uniform(0.0, 0.08) if rr.random() < 0.45 else rr.uniform(0.0, 0.012)
                kink = rr.uniform(0.3, 0.8)
                pts = []
                for k in range(8):
                    t = k / 7
                    z = -dro * max(0.0, (t - kink) / (1 - kink)) ** 1.5 if t > kink else 0.0
                    pts.append(Me @ Vector((0.0, sgn * (0.004 + hh * t), z - 0.004 * t)))
                _tube(mb, pts, r_, seg=6, mat=mat)
            _box(mb, (-0.012, -0.016, -0.014), (0.012, 0.016, 0.005), "plastic", bevel=0.002, seg=1, m=Me)

        element(-0.42, 0.52, r_=0.005)
        element(-0.36, 0.5, r_=0.005)
        # dipolo plegado + caja de bornes
        xd = -0.25
        cd = boom_at(xd)
        Md = Mb_ @ _T(cd + Vector((0, 0, 0.022)))
        loop = _fillet([(0, -0.33, 0), (0, 0.33, 0), (0.0, 0.33, 0.045), (0, -0.33, 0.045), (0, -0.33, 0), (0, 0.33, 0)], 0.02, 5)[1:-1]
        loop = [p for p in loop if not (abs(p.y) < 0.03 and p.z < 0.01)]
        _tube(mb, [Md @ (p + Vector((0, 0, -0.03))) for p in loop], 0.0048, seg=6, mat="aluminium", closed=False)
        _box(mb, (-0.03, -0.035, -0.045), (0.03, 0.035, -0.012), "plastic", bevel=0.004, seg=2, m=Md)
        miss = int(rr.integers(1, 7))
        for i in range(8):
            x = -0.1 + 1.0 * i / 7
            half = 0.27 - 0.07 * i / 7
            if i == miss:
                _box(mb, (-0.012, -0.016, -0.014), (0.012, 0.016, 0.005), "plastic", bevel=0.002, seg=1, m=Mb_ @ _T(boom_at(x)))
                continue
            element(x, half, broken=(rr.random() < 0.15))
        # coaxial: caja -> botalón -> mástil -> losa
        c0 = Md @ Vector((0.0, 0.0, -0.046))
        pb = [Mb_ @ (boom_at(x) + Vector((0, 0.0, -0.016))) for x in (-0.22, -0.15, -0.06)]
        down = [top + lean.to_3x3() @ Vector((0.022 * math.cos(z * 6), 0.022 * math.sin(z * 6), -0.12 - z)) for z in [0.1 * k for k in range(int(Hm / 0.1) - 2)]]
        end_ = [Vector(down[-1]) + Vector((0.05, 0.02, -0.12)), Vector((0.25, 0.06, 0.008)), Vector((1.2, 0.3, 0.008))]
        cpts = _spline([c0, c0 + Vector((0, 0, -0.03))] + pb + [top + lean.to_3x3() @ Vector((0.03, 0, -0.1))] + down[::3] + end_, 0.03)
        _tube(mb, cpts, 0.0035, seg=6, mat="cable")
        for k in range(2, len(down), 4):
            _torus(mb, down[k] - (down[k] - (top + lean.to_3x3() @ Vector((0, 0, -0.12 - 0.1 * k)))) * 0.45,
                   lean.to_3x3() @ Vector((0, 0, 1)), 0.022, 0.0025, n=14, seg=4, mat="cable")
        _declump(mb)
        return mb


def satellite_dish(seed=0, detail="high"):
    """Antena parabólica offset (0,62 × 0,56) en ménsula de muro: placa con 4 taquetes, brazo, mástil Ø 42, soporte de
    elevación con ranuras, plato abollado y vencido hacia abajo, brazo del LNB doblado y coaxial con bucle de goteo
    entrando al muro. Origen: cara del muro, centro de la placa de anclaje (z = 0 = centro de la placa)."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        mb = MB()
        # ménsula de muro
        _box(mb, (-0.07, -0.0075, -0.11), (0.07, -0.0015, 0.11), "metal_rust", bevel=0.003, seg=1)
        for (bx, bz) in ((-0.045, -0.08), (0.045, -0.08), (-0.045, 0.08), (0.045, 0.08)):
            _bolt(mb, (bx, -0.0075, bz), (0, -1, 0), r=0.0065)
        mb.sweep([(-0.02, -0.02), (0.02, -0.02), (0.02, 0.02), (-0.02, 0.02)], [(0, -0.006, 0.0), (0, -0.303, 0.0)], mat="metal_rust",
                 normal=(0, 0, 1))
        _angle_iron(mb, (0.0, -0.007, -0.10), (0.0, -0.25, -0.02), Vector((1, 0, 0)).cross(Vector((0, -0.24, 0.08)).normalized()), a=0.03)
        mx, my = 0.0, -0.33
        _cyl(mb, (mx, my, -0.12), (mx, my, 0.40), 0.021, seg=16, mat="metal_paint")
        _cyl(mb, (mx, my, 0.395), (mx, my, 0.405), 0.022, seg=16, mat="plastic")
        for zz in (-0.035, 0.035):
            _tube(mb, _fillet([(mx - 0.024, my + 0.06, zz), (mx - 0.024, my - 0.024, zz), (mx + 0.024, my - 0.024, zz), (mx + 0.024, my + 0.06, zz)],
                              0.02, 5), 0.0045, seg=6, mat="metal_rust")
        _box(mb, (mx - 0.035, my + 0.022, -0.05), (mx + 0.035, my + 0.03, 0.05), "metal_rust", bevel=0.002, seg=1)
        # plato
        az = rr.uniform(-25, 25)
        el = rr.uniform(-20, -5)  # vencido hacia abajo
        Mmount = _T(mx, my, 0.30) @ _R("Z", az)
        _cyl(mb, Mmount @ Vector((0, 0, -0.07)), Mmount @ Vector((0, 0, 0.07)), 0.027, seg=16, mat="metal_rust")
        _box(mb, (-0.006, -0.10, -0.05), (0.006, -0.02, 0.06), "metal_rust", bevel=0.002, seg=1, m=Mmount @ _T(-0.045, 0, 0))
        _box(mb, (-0.006, -0.10, -0.05), (0.006, -0.02, 0.06), "metal_rust", bevel=0.002, seg=1, m=Mmount @ _T(0.045, 0, 0))
        _bolt(mb, Mmount @ Vector((0.051, -0.07, 0.03)), Mmount.to_3x3() @ Vector((1, 0, 0)), r=0.006)
        _bolt(mb, Mmount @ Vector((-0.051, -0.07, 0.03)), Mmount.to_3x3() @ Vector((-1, 0, 0)), r=0.006)
        # marco local del plato: eje de la paraboloide = -Y (mira hacia fuera), u = X, v = Z
        Mdish = Mmount @ _T(0, -0.105, -0.02) @ _R("X", el)
        f = 0.36
        a_, b_ = 0.31, 0.28
        v0 = 0.30
        dents = [(rr.uniform(-0.6, 0.6), rr.uniform(-0.6, 0.6), rr.uniform(0.12, 0.3), rr.uniform(0.006, 0.02)) for _ in range(2)]
        warp_a = rr.uniform(0, 2 * PI)

        def dish_pt(rho, ph):
            u, v = a_ * rho * math.cos(ph), v0 + b_ * rho * math.sin(ph)
            w = (u * u + v * v) / (4 * f) - (v0 * v0) / (4 * f)
            for (du, dv, R_, dep) in dents:
                d = math.hypot(rho * math.cos(ph) - du, rho * math.sin(ph) - dv)
                if d < R_ * 3:
                    w += dep * 0.5 * (1 + math.cos(PI * min(d / (R_ * 3), 1)))
            w += 0.03 * max(0.0, math.cos(ph - warp_a)) ** 8 * rho ** 4
            return Vector((u, -w, v - v0))

        nrho, nph = _lv((10, 48), (6, 32), (4, 20))
        sh = MB()
        rings = [[sh.bm.verts.new(Mdish @ dish_pt(0.0, 0.0))]]
        for i in range(1, nrho + 1):
            rho = i / nrho
            rings.append([sh.bm.verts.new(Mdish @ dish_pt(rho, 2 * PI * k / nph)) for k in range(nph)])
        for k in range(nph):
            kk = (k + 1) % nph
            sh.face([rings[0][0], rings[1][k], rings[1][kk]], "metal_paint")
        for i in range(1, nrho):
            for k in range(nph):
                kk = (k + 1) % nph
                sh.face([rings[i][k], rings[i + 1][k], rings[i + 1][kk], rings[i][kk]], "metal_paint")
        sh.bm.normal_update()
        # normal hacia el frente (cara cóncava hacia -Y local): solidify hacia atrás
        nrm_avg = sum((f_.normal for f_ in sh.bm.faces), Vector((0, 0, 0)))
        front = Mdish.to_3x3() @ Vector((0, -1, 0))
        if nrm_avg.dot(front) < 0:
            bmesh.ops.reverse_faces(sh.bm, faces=list(sh.bm.faces))
        _solidify(sh, 0.0016)
        _merge(mb, sh)
        rim = [Mdish @ dish_pt(1.0, 2 * PI * k / nph) for k in range(nph)]
        _tube(mb, rim, 0.004, seg=6, mat="metal_paint", closed=True, up=front)
        # placa trasera del plato (sigue la pendiente de la paraboloide en el centro)
        tv = Vector((0.0, -2 * v0 / (4 * f), 1.0)).normalized()
        nb_ = Vector((1, 0, 0)).cross(tv) * -1.0
        Mp = Mdish @ _frame((0, 0, 0), nb_, (1, 0, 0))
        _box(mb, (-0.055, -0.055, 0.0018), (0.055, 0.055, 0.009), "metal_rust", bevel=0.003, seg=1, m=Mp)
        for (bx, by) in ((-0.035, -0.035), (0.035, 0.035), (-0.035, 0.035), (0.035, -0.035)):
            _screw(mb, Mp @ Vector((bx, by, -0.0005)), Mp.to_3x3() @ Vector((0, 0, -1)), r=0.005)
        # brazo del LNB (doblado) desde el borde inferior hasta el foco
        p_low = Mdish @ dish_pt(1.0, -PI / 2)
        focus = Mdish @ Vector((0.0, -f + (v0 * v0) / (4 * f), -v0))
        bendv = Mdish.to_3x3() @ Vector((rr.uniform(-0.05, 0.05), 0.0, rr.uniform(-0.08, -0.02)))
        arm = [p_low.lerp(focus, t) + bendv * math.sin(PI * t * 0.5) ** 2 for t in [k / 10 for k in range(11)]]
        arm = [p_low + (Mdish.to_3x3() @ Vector((0, -0.002, -0.01)))] + arm[1:]
        mb.sweep([(-0.012, -0.0095), (0.012, -0.0095), (0.012, 0.0095), (-0.012, 0.0095)], arm, mat="metal_paint",
                 normal=Mdish.to_3x3() @ Vector((1, 0, 0)))
        tip = arm[-1]
        lnb_dir = (Mdish @ Vector((0, 0, 0)) - tip).normalized()
        lnb_dir = (lnb_dir + Vector((rr.uniform(-0.3, 0.3), rr.uniform(-0.3, 0.3), -0.5))).normalized()
        Ml = _frame(tip, lnb_dir)
        _torus(mb, tip, lnb_dir, 0.03, 0.004, n=20, seg=6, mat="metal_paint")
        _lathe(mb, [(0.0, -0.09), (0.021, -0.09), (0.024, -0.06), (0.024, 0.0), (0.03, 0.01), (0.034, 0.04), (0.0, 0.04)], seg=20,
               mat="plastic", m=Ml)
        _box(mb, (-0.02, -0.018, -0.14), (0.02, 0.018, -0.085), "plastic", bevel=0.004, seg=2, m=Ml)
        # coaxial: LNB -> brazo -> mástil -> bucle -> muro
        c0 = Ml @ Vector((0, 0.0, -0.14))
        under = Mdish.to_3x3() @ Vector((0, 0.0, -0.016))
        # sale del conector del LNB, da la vuelta por debajo de la punta del brazo (sin pasar por dentro del LNB) y sigue el brazo
        cpts = [c0, c0 + (Ml.to_3x3() @ Vector((0, 0, -0.05))), tip + under * 4.0] + [p + under for p in arm[7::-3]]
        cpts += [Vector((mx + 0.03, my, 0.15)), Vector((mx + 0.03, my, -0.05)), Vector((mx + 0.05, my + 0.08, -0.25)),
                 Vector((mx + 0.08, -0.05, -0.32)), Vector((mx + 0.1, -0.02, -0.15)), Vector((mx + 0.1, 0.02, -0.12))]
        _tube(mb, _spline(cpts, 0.03), 0.0035, seg=6, mat="cable")
        _declump(mb)
        return mb


# =====================================================================================================================
# tinaco, buzones, gabinete de extintor, letrero
# =====================================================================================================================
def _brick_wall(mb, x0, x1, yc, courses, rr, nz, z0=0.0, missing=0.03, BL=0.24, BW=0.12, BH=0.06, J=0.01):
    """Murete de tabique a soga (0,24 × 0,12 × 0,06, junta 1 cm) con juntas de mortero rehundidas 6 mm, ladrillos
    ligeramente desalineados, alguno partido o faltante. Devuelve la altura superior."""
    joints = _LOD.level == "high"
    if not joints:  # mid / low: núcleo de mortero rehundido 6 mm (se ve en todas las juntas) en vez de una caja por junta
        top = z0 + J + courses * (BH + J) - J
        _box(mb, (x0 + 0.004, yc - BW / 2 + 0.006, z0 + 0.001), (x1 - 0.004, yc + BW / 2 - 0.006, top - 0.002), "mortar")
    for c in range(courses):
        zb = z0 + J + c * (BH + J)
        off = 0.0 if c % 2 == 0 else (BL + J) / 2
        x = x0 - off
        # junta de asiento (debajo de la hilada)
        if joints:
            _box(mb, (x0 + 0.004, yc - BW / 2 + 0.006, zb - J + 0.001), (x1 - 0.004, yc + BW / 2 - 0.006, zb - 0.001), "mortar")
        while x < x1 - 0.02:
            a, b = max(x, x0), min(x + BL, x1)
            if b - a > 0.03:
                if rr.random() > missing:
                    broken = rr.random() < 0.06
                    bb = a + (b - a) * rr.uniform(0.45, 0.8) if broken else b
                    M = _about(((a + bb) / 2, yc, zb + BH / 2), _R("Z", rr.uniform(-0.6, 0.6)) @ _R("X", rr.uniform(-0.5, 0.5)))
                    M = _T(rr.uniform(-0.0015, 0.0015), rr.uniform(-0.002, 0.002), 0) @ M
                    _box(mb, (a, yc - BW / 2, zb), (bb, yc + BW / 2, zb + BH), "brick", bevel=0.004, seg=1, m=M)
                if joints and b < x1 - 0.005:  # junta vertical
                    _box(mb, (b + 0.001, yc - BW / 2 + 0.006, zb + 0.001), (b + J - 0.001, yc + BW / 2 - 0.006, zb + BH - 0.001), "mortar")
            x += BL + J
    return z0 + J + courses * (BH + J) - J


def water_tank(seed=0, detail="high"):
    """Tinaco de polietileno de 1100 L (Ø 1,10 × 1,40) con nervaduras, cuello y tapa (puesta, corrida o tirada), sobre
    losa de concreto de 1,32 × 1,16 apoyada en 3 muretes de tabique de 6 hiladas; salida con válvula, jarro de aire y
    alimentación de PVC. Origen: centro de la base sobre la losa de azotea (z = 0)."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        mb = MB()
        top = 0.0
        for yc in (-0.46, 0.0, 0.46):
            top = _brick_wall(mb, -0.6, 0.6, yc, 6, rr, nz)
        zs = top + 0.0015
        slab = _lattice((-0.66, -0.58, zs), (0.66, 0.58, zs + 0.08), r=0.012, step=0.08, mat="concrete",
                        deform=_deformer([], nz, amp=0.003, freq=4.0))
        _merge(mb, slab)
        zt = zs + 0.08 + 0.001
        # tanque
        prof = [(0.0, 0.0), (0.50, 0.0), (0.53, 0.012), (0.545, 0.04), (0.55, 0.085)]
        z = 0.11
        while z < 1.08:
            prof += _lv([(0.55, z), (0.556, z + 0.012), (0.563, z + 0.028), (0.563, z + 0.046), (0.556, z + 0.062), (0.55, z + 0.074)],
                        [(0.55, z), (0.5615, z + 0.02), (0.5615, z + 0.054), (0.55, z + 0.074)],
                        [(0.55, z), (0.562, z + 0.037), (0.55, z + 0.074)])
            z += 0.17
        prof += [(0.55, 1.17), (0.535, 1.235), (0.49, 1.29), (0.41, 1.33), (0.31, 1.356), (0.245, 1.366), (0.245, 1.40), (0.236, 1.407),
                 (0.218, 1.40), (0.218, 1.12), (0.0, 1.12)]
        dent_a, dent_z = rr.uniform(0, 2 * PI), rr.uniform(0.3, 0.9)
        bul = rr.uniform(0.004, 0.012)

        def tdef(p, a, rad, zz):
            if rad < 0.3 or zz > 1.37:
                return p
            k = 1.0 + (0.006 * nz(Vector((math.cos(a) * 2, math.sin(a) * 2, zz * 3))) + bul * math.sin(PI * min(zz / 1.2, 1.0))) * (rad / 0.55)
            d = math.hypot((a - dent_a + PI) % (2 * PI) - PI, (zz - dent_z) * 2.0)
            if d < 0.35:
                k -= 0.035 * 0.5 * (1 + math.cos(PI * d / 0.35))
            return Vector((p.x * k, p.y * k, p.z))

        Mt = _T(0, 0, zt)
        _lathe(mb, prof, seg=56, mat="plastic", m=Mt, deform=tdef)
        # tapa
        lid = [(0.0, 0.0), (0.262, 0.0), (0.262, 0.035), (0.255, 0.045), (0.21, 0.052), (0.0, 0.056)]
        state = rr.choice(["on", "ajar", "off"])
        if state == "on":
            Ml = _T(0, 0, zt + 1.371) @ _R("Z", rr.uniform(0, 90))
        elif state == "ajar":
            Ml = _T(rr.uniform(0.12, 0.2), rr.uniform(-0.05, 0.05), zt + 1.395) @ _R("Y", rr.uniform(8, 14)) @ _R("Z", rr.uniform(0, 90))
        else:
            a = rr.uniform(0, 2 * PI)
            Ml = _T(0.95 * math.cos(a), 0.95 * math.sin(a), 0.0015) @ _R("X", 180) @ _T(0, 0, -0.056)
        _lathe(mb, lid, seg=40, mat="plastic", m=Ml)
        for k in range(16):  # nervios de agarre de la tapa
            a = 2 * PI * k / 16
            _box(mb, (0.258, -0.006, 0.006), (0.268, 0.006, 0.03), "plastic", bevel=0.002, seg=1, m=Ml @ _R("Z", math.degrees(a)))
        # salida: niple + válvula + tee + jarro de aire + bajada
        ao = rr.uniform(0, 2 * PI)
        d = Vector((math.cos(ao), math.sin(ao), 0))
        s_ = Vector((-d.y, d.x, 0))
        zo = zt + 0.13
        p0 = d * 0.53 + Vector((0, 0, zo))
        _cyl(mb, p0 - d * 0.02, p0 + d * 0.05, 0.034, seg=16, mat="plastic")
        _cyl(mb, p0 + d * 0.05, p0 + d * 0.2, 0.021, seg=12, mat="plastic")
        vc = p0 + d * 0.13
        _bolt(mb, vc + Vector((0, 0, 0.018)), (0, 0, 1), r=0.016, h=0.02, washer=False, seg=8)
        _box(mb, (-0.012, -0.004, 0.0), (0.09, 0.004, 0.006), "metal_rust", bevel=0.002, seg=1,
               m=_T(vc + Vector((0, 0, 0.04))) @ _R("Z", math.degrees(ao) + rr.uniform(-70, 70)))
        tee = p0 + d * 0.22
        _cyl(mb, tee - d * 0.025, tee + d * 0.025, 0.028, seg=12, mat="plastic")
        jar = _fillet([tee, tee + Vector((0, 0, 1.75)), tee + Vector((0, 0, 1.75)) + d * 0.1, tee + Vector((0, 0, 1.6)) + d * 0.1], 0.06, 6)
        _tube(mb, _densify(jar, 0.1), 0.021, seg=12, mat="plastic")
        low = _fillet([tee, tee - Vector((0, 0, zo - 0.05)), tee - Vector((0, 0, zo - 0.05)) + d * 0.6 + s_ * 0.2], 0.07, 6)
        _tube(mb, _densify(low, 0.1), 0.021, seg=12, mat="plastic")
        # alimentación por arriba (sube por fuera del tanque)
        ai = ao + rr.uniform(0.9, 1.6)
        di = Vector((math.cos(ai), math.sin(ai), 0))
        pin = di * 0.535 + Vector((0, 0, zt + 1.22))
        _cyl(mb, pin - di * 0.02, pin + di * 0.05, 0.026, seg=12, mat="plastic")
        feed = _fillet([pin + di * 0.05, pin + di * 0.12, pin + di * 0.12 - Vector((0, 0, 1.22 + zt - 0.04)),
                        pin + di * 0.9 - Vector((0, 0, 1.22 + zt - 0.04))], 0.06, 6)
        _tube(mb, _densify(feed, 0.1), 0.0135, seg=10, mat="plastic")
        _declump(mb)
        return mb


def mailboxes(n=8, seed=0, detail="high"):
    """Batería de n buzones de chapa (celda 0,27 × 0,135 × 0,26) con marco, divisiones, puertas con ranura, tarjetero y
    chapa: unas cerradas, otras abiertas, colgando de una bisagra o arrancadas (quedan los muñones de bisagra), papeles
    viejos dentro. Origen: cara del muro, centro inferior del gabinete."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        mb = MB()
        cols = 2 if n <= 8 else (3 if n <= 15 else 4)
        rows = int(math.ceil(n / cols))
        cw, ch, D = 0.27, 0.135, 0.26
        fr = 0.012
        W, H = cols * cw + 2 * fr, rows * ch + 2 * fr
        x0, x1, yb, yf = -W / 2, W / 2, -0.0015, -0.0015 - D
        dents = _rand_dents(rr, (x0, yf, 0), (x1, yb, H), 2, faces=("+x", "-x", "+z"),
                            region=((x0 + 0.04, yf + 0.04, 0.04), (x1 - 0.04, yb - 0.04, H - 0.04)), depth=(0.002, 0.006))
        body = _tray((x0, yf, 0.0), (x1, yb, H), "-y", t=0.0015, r=0.006, step=0.035, mat="metal_paint",
                     deform=_deformer(dents, nz, amp=0.0005), matfn=_rust_fn(nz, 0.0, H, thr=0.32))
        _merge(mb, body)
        xi0, xi1 = x0 + fr, x1 - fr
        for rI in range(1, rows):
            z = fr + rI * ch
            _box(mb, (x0 + 0.002, yb - 0.004, z - 0.00075), (x1 - 0.002, yf + 0.004, z + 0.00075), "metal_paint")
            _box(mb, (x0 + 0.0005, yf - 0.002, z - 0.006), (x1 - 0.0005, yf + 0.009, z + 0.006), "metal_paint", bevel=0.0015, seg=1)
        for cI in range(1, cols):
            x = xi0 + cI * cw
            _box(mb, (x - 0.00075, yb - 0.0046, 0.002), (x + 0.00075, yf + 0.0046, H - 0.002), "metal_paint")
            _box(mb, (x - 0.006, yf - 0.0025, 0.0005), (x + 0.006, yf + 0.0095, H - 0.0005), "metal_paint", bevel=0.0015, seg=1)
        for (a, b, c, d) in ((x0 - 0.002, x1 + 0.002, -0.002, fr), (x0 - 0.002, x1 + 0.002, H - fr, H + 0.002)):
            _box(mb, (a, yf - 0.003, c), (b, yf + 0.012, d), "metal_paint", bevel=0.002, seg=1)
        for (a, b) in ((x0 - 0.002, x0 + fr), (x1 - fr, x1 + 0.002)):
            _box(mb, (a + 0.0005, yf - 0.0028, fr + 0.0005), (b - 0.0005, yf + 0.0118, H - fr - 0.0005), "metal_paint", bevel=0.002, seg=1)
        # puertas
        dw, dh = cw - 0.016, ch - 0.016
        col_ang = {}
        for i in range(rows * cols):
            rI, cI = divmod(i, cols)
            rI = rows - 1 - rI
            cx0 = xi0 + cI * cw + 0.008
            cz0 = fr + rI * ch + 0.008
            if i >= n:  # tapa ciega
                _box(mb, (cx0, yf - 0.004, cz0), (cx0 + dw, yf - 0.0015, cz0 + dh), "metal_paint", bevel=0.001, seg=1)
                continue
            roll = rr.random()
            state = "closed" if roll < 0.35 else ("open" if roll < 0.65 else ("hanging" if roll < 0.82 else "torn"))
            piv = Vector((cx0 - 0.002, yf - 0.006, cz0))
            for zh in (0.02, dh - 0.02):
                if state == "torn":
                    _cyl(mb, piv + Vector((0, 0, zh - 0.008)), piv + Vector((0, 0, zh + 0.006)), 0.0035, seg=8, mat="metal_rust")
                else:
                    _cyl(mb, piv + Vector((0, 0, zh - 0.012)), piv + Vector((0, 0, zh + 0.012)), 0.0035, seg=8, mat="metal_rust")
            if state == "torn":
                col_ang[cI] = None
                if rr.random() < 0.5:  # papel dentro
                    _box(mb, (-0.08, -0.06, 0.0), (0.08, 0.06, 0.0025), "plastic", m=_T(cx0 + dw / 2, yf + 0.12, cz0 - 0.006 + 0.004)
                           @ _R("Z", rr.uniform(-20, 20)) @ _R("Y", rr.uniform(-6, 6)))
                continue
            ang = {"closed": rr.uniform(0, 4), "open": rr.uniform(50, 125), "hanging": rr.uniform(15, 60)}[state]
            prev = col_ang.get(cI)
            if state != "closed" and prev is not None and abs(ang - prev) < 16:  # que no choque con la puerta de arriba
                ang = prev + 18 if prev + 18 <= 125 else prev - 18
            col_ang[cI] = ang if state != "closed" else None
            Md = _T(piv) @ _R("Z", -ang)
            if state == "hanging":
                # bisagra inferior rota: cuelga de la superior y el canto libre se cae; se corre hacia fuera para no cruzar
                # la línea de bisagras
                th = math.radians(rr.uniform(10, 26))
                shift = max(0.0, (dh - 0.02) * math.sin(th) - 0.002 * math.cos(th)) + 0.002
                Md = Md @ _T(shift, 0, 0) @ _about((0, 0, dh - 0.02), Matrix.Rotation(th, 4, "Y")) @ _R("X", rr.uniform(-6, 6))
            door = _tray((0.002, -0.0012, 0.0), (0.002 + dw, 0.0055, dh), "+y", t=0.0012, r=0.003, step=0.04, mat="aluminium")
            _merge(mb, door, Md)
            _box(mb, (0.03, -0.0028, dh - 0.045), (dw - 0.03, -0.0008, dh - 0.038), "aluminium", bevel=0.0006, seg=1, m=Md)
            _box(mb, (0.03, -0.0028, dh - 0.028), (dw - 0.03, -0.0008, dh - 0.021), "aluminium", bevel=0.0006, seg=1, m=Md)
            _box(mb, (0.035, -0.0022, 0.02), (0.11, -0.0008, 0.05), "plastic", bevel=0.0005, seg=1, m=Md)
            _cyl(mb, Md @ Vector((dw - 0.025, -0.0008, dh / 2 - 0.01)), Md @ Vector((dw - 0.025, -0.0065, dh / 2 - 0.01)), 0.008, seg=14,
                   mat="aluminium")
            _box(mb, (-0.001, -0.0075, -0.0045), (0.001, -0.0055, 0.0045), "metal_rust", m=Md @ _T(dw - 0.025, 0, dh / 2 - 0.01))
            if state != "closed" and rr.random() < 0.6:
                _box(mb, (-0.09, -0.07, 0.0), (0.09, 0.07, 0.003), "plastic", m=_T(cx0 + dw / 2, yf + 0.13, cz0 - 0.006 + 0.004)
                       @ _R("Z", rr.uniform(-25, 25)) @ _R("X", rr.uniform(-4, 4)))
        for (xx, zz) in ((x0 + 0.03, H - 0.03), (x1 - 0.03, H - 0.03), (x0 + 0.03, 0.03), (x1 - 0.03, 0.03)):
            _screw(mb, (xx, yb - 0.0015, zz), (0, -1, 0), r=0.005)
        _declump(mb)
        return mb


def extinguisher_cabinet(seed=0, detail="high"):
    """Gabinete de extintor de sobreponer (0,30 × 0,64 × 0,20), VACÍO: gancho doblado al fondo, puerta de marco con el
    vidrio roto (esquirlas en el marco) abierta o colgando, letrero de lámina arriba colgando de un tornillo.
    Origen: cara del muro, centro inferior del gabinete."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        mb = MB()
        W, H, D = 0.30, 0.64, 0.20
        x0, x1, yb, yf = -W / 2, W / 2, -0.0015, -0.0015 - D
        body = _tray((x0, yf, 0.0), (x1, yb, H), "-y", t=0.0015, r=0.007, step=0.035, mat="metal_paint",
                     deform=_deformer(_rand_dents(rr, (x0, yf, 0), (x1, yb, H), 2, faces=("+x", "-x", "+z"),
                                                  region=((x0 + 0.04, yf + 0.04, 0.06), (x1 - 0.04, yb - 0.04, H - 0.06))), nz, amp=0.0005),
                     matfn=_rust_fn(nz, 0.0, H, thr=0.3))
        _merge(mb, body)
        rim = _fillet([(x0 + 0.0008, yf + 0.0012, 0.0008), (x1 - 0.0008, yf + 0.0012, 0.0008), (x1 - 0.0008, yf + 0.0012, H - 0.0008),
                       (x0 + 0.0008, yf + 0.0012, H - 0.0008), (x0 + 0.0008, yf + 0.0012, 0.0008), (x1 - 0.0008, yf + 0.0012, 0.0008)], 0.007, 3)[1:-1]
        _tube(mb, rim, 0.0024, seg=6, mat="metal_paint", closed=True, up=(0, 1, 0))
        # gancho de solera doblado
        hk = _fillet([(0.0, yb - 0.0016, 0.40), (0.0, yb - 0.0016, 0.47), (0.0, yb - 0.06, 0.47), (0.0, yb - 0.075, 0.5)], 0.012, 4)
        hk = [p + Vector((0.0, 0.0, 0.0)) for p in hk]
        hk[-1] = hk[-1] + Vector((rr.uniform(-0.03, 0.03), 0, -0.02))
        mb.sweep([(-0.015, 0.0), (0.015, 0.0), (0.015, 0.003), (-0.015, 0.003)], hk, mat="metal_rust", normal=(1, 0, 0))
        _screw(mb, (0.0, yb - 0.0046, 0.43), (0, -1, 0), r=0.005)
        # puerta: marco tubular + vidrio roto
        st = rr.choice(["open", "hanging", "ajar"])
        piv = Vector((x0 - 0.004, yf - 0.006, 0.0))
        if st == "open":
            Md = _T(piv) @ _R("Z", -rr.uniform(95, 160))
        elif st == "ajar":
            Md = _T(piv) @ _R("Z", -rr.uniform(10, 35))
        else:
            Md = _T(piv) @ _R("Z", -rr.uniform(40, 90)) @ _about((0, 0, H - 0.08), _R("Y", -rr.uniform(8, 20)))
        dw, dh, fw = W + 0.008, H + 0.008, 0.028
        for (a, b, c, d) in ((0.004, 0.004 + dw, -0.004, -0.004 + fw), (0.004, 0.004 + dw, dh - 0.004 - fw, dh - 0.004),
                             (0.0045, 0.0035 + fw, fw - 0.0035, dh - fw - 0.0045), (dw + 0.0045 - fw, dw + 0.0035, fw - 0.0035, dh - fw - 0.0045)):
            side = (b - a) < fw
            _box(mb, (a, -0.0155 if side else -0.016, c), (b, -0.0005 if side else 0.0, d), "metal_paint", bevel=0.003, seg=1, m=Md)
        gi = [(0.004 + fw - 0.006, -0.004 + fw - 0.006), (dw + 0.004 - fw + 0.006, -0.004 + fw - 0.006),
              (dw + 0.004 - fw + 0.006, dh - 0.004 - fw + 0.006), (0.004 + fw - 0.006, dh - 0.004 - fw + 0.006)]
        Mg = Md @ _T(0, -0.0085, 0) @ _R("X", 90)
        for e in range(4):
            a, b = Vector(gi[e] + (0,)), Vector(gi[(e + 1) % 4] + (0,))
            nsh = int(rr.integers(1, 4))
            for k in range(nsh):
                t0 = rr.uniform(0.0, 0.7)
                t1 = min(1.0, t0 + rr.uniform(0.15, 0.4))
                pa, pb = a.lerp(b, t0), a.lerp(b, t1)
                inward = Vector(((dw / 2 + 0.004) - (pa.x + pb.x) / 2, (dh / 2 - 0.004) - (pa.y + pb.y) / 2, 0)).normalized()
                tip = pa.lerp(pb, rr.uniform(0.2, 0.8)) + inward * rr.uniform(0.03, 0.12)
                _shard_plate(mb, [(pa.x, pa.y), (pb.x, pb.y), (tip.x, tip.y)], 0.003, "glass", Mg, rr, e * 3 + k)
        _cyl(mb, Md @ Vector((dw - 0.01, -0.016, dh / 2)), Md @ Vector((dw - 0.01, -0.03, dh / 2)), 0.007, seg=10, mat="aluminium")
        for zh in (0.08, H - 0.08):
            _hinge(mb, piv + Vector((0, 0, zh)), h=0.06)
        # letrero de lámina arriba, colgando de un tornillo
        sp = Vector((-0.11, -0.004, H + 0.1))
        Ms = _T(sp) @ _R("Y", rr.uniform(8, 35))
        _box(mb, (0.0, -0.0012, -0.08), (0.24, 0.0, 0.0), "metal_paint", bevel=0.0008, seg=1, m=Ms @ _T(-0.012, 0, 0.012))
        _screw(mb, sp + Vector((0, -0.0012, 0)), (0, -1, 0), r=0.005)
        _cyl(mb, (0.11, 0.02, H + 0.1), (0.11, -0.006, H + 0.1), 0.0025, seg=6, mat="metal_rust")
        _declump(mb)
        return mb


def _torn_panel(x0, x1, zt, frac_lo, frac_hi, rr, jag=0.04, from_top=True, nu=None, nv=10):
    """Rejilla de un fragmento de lámina rasgada: columnas de x0 a x1 desde el borde fijo zt hasta una línea de rotura
    dentada (fracciones de la altura total). Devuelve una lista de columnas (cada una lista de (x, z))."""
    nu = nu or max(6, int((x1 - x0) / 0.03))
    walk = rr.uniform(frac_lo, frac_hi)
    cols = []
    for i in range(nu + 1):
        x = x0 + (x1 - x0) * i / nu
        walk = min(max(walk + rr.uniform(-jag, jag), frac_lo * 0.5), frac_hi * 1.2)
        tear = walk + (rr.uniform(0.3, 1.0) * jag * 2.2 if rr.random() < 0.3 else rr.uniform(0.0, jag * 0.4))
        edge = (i == 0 or i == nu)
        tear = tear * (rr.uniform(0.6, 1.0) if edge else 1.0)
        cols.append([(x, zt + (-1 if from_top else 1) * tear * j / nv) for j in range(nv + 1)])
    return cols


def sign_torn(w=2.4, h=0.6, seed=0, detail="high"):
    """Letrero luminoso de comercio (caja de lámina de 0,14 de fondo con marco de aluminio) con la cara de acrílico
    arrancada: quedan jirones colgando enroscados del marco superior y un pedazo en la esquina inferior; tubos
    fluorescentes rotos, caídos o faltantes con sus sockets, balastro y cable entrando desde el muro.
    Origen: cara del muro, centro inferior del letrero; ocupa x = -w/2..w/2, z = 0..h."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        mb = MB()
        D = 0.14
        x0, x1, yb, yf = -w / 2, w / 2, -0.0015, -0.0015 - D
        pan = _tray((x0, yf, 0.0), (x1, yb, h), "-y", t=0.0015, r=0.01, step=0.06, mat="metal_paint",
                    deform=_deformer([], nz, amp=0.0008), matfn=_rust_fn(nz, 0.0, h, thr=0.28))
        _merge(mb, pan)
        fw, fd = 0.045, 0.035
        fy0, fy1 = yf - 0.012, yf + fd - 0.012
        _box(mb, (x0 - 0.004, fy0, h - fw + 0.004), (x1 + 0.004, fy1, h + 0.004), "aluminium", bevel=0.004, seg=2)
        sag = rr.uniform(0.0, 0.02)
        Mbot = _about((x1, 0, 0), _R("Y", -math.degrees(math.atan2(sag, w))))
        _box(mb, (x0 - 0.004, fy0, -0.004), (x1 + 0.004, fy1, fw - 0.004), "aluminium", bevel=0.004, seg=2, m=Mbot)
        _box(mb, (x0 - 0.004 + 0.0005, fy0 + 0.0005, fw - 0.003), (x0 + fw - 0.004, fy1 - 0.0005, h - fw + 0.003), "aluminium", bevel=0.004, seg=2)
        _box(mb, (x1 - fw + 0.004, fy0 + 0.0005, fw - 0.003), (x1 + 0.004 - 0.0005, fy1 - 0.0005, h - fw + 0.003), "aluminium", bevel=0.004, seg=2)
        # tubos fluorescentes
        nt = max(2, int(h / 0.2))
        for k in range(nt):
            z = h * (k + 0.5) / nt
            yt = yb - 0.06
            _box(mb, (x0 + 0.05, yb - 0.03, z - 0.02), (x1 - 0.05, yb - 0.0045, z + 0.02), "metal_paint", bevel=0.003, seg=1)
            xa, xb = x0 + 0.08, x1 - 0.08
            for xs in (xa - 0.02, xb + 0.02):
                _box(mb, (xs - 0.012, yt - 0.018, z - 0.022), (xs + 0.012, yb - 0.025, z + 0.022), "plastic", bevel=0.003, seg=1)
            st = rr.choice(["ok", "broken", "missing", "fallen"], p=[0.25, 0.35, 0.2, 0.2])
            if st == "ok":
                _cyl(mb, (xa - 0.01, yt, z), (xb + 0.01, yt, z), 0.013, seg=12, mat="glass")
            elif st == "broken":
                cut = rr.uniform(0.25, 0.75)
                xm = xa + (xb - xa) * cut
                _cyl(mb, (xa - 0.01, yt, z), (xm - 0.02, yt, z), 0.013, seg=12, mat="glass")
                _cyl(mb, (xm + 0.03, yt, z), (xb + 0.01, yt, z), 0.013, seg=12, mat="glass")
                _shards_ring(mb, _frame((xm - 0.02, yt, z), (1, 0, 0)), 0.0125, rr, n=4, t=0.0015, h=(0.004, 0.012))
            elif st == "fallen":
                _cyl(mb, (xa - 0.01, yt, z), (xa + (xb - xa) * 0.9, yt - 0.05, max(0.06, z - 0.35)), 0.013, seg=12, mat="glass")
        _box(mb, (-0.12, yb - 0.05, h / 2 - 0.03), (0.12, yb - 0.0045, h / 2 + 0.03), "metal_rust", bevel=0.004, seg=1)
        ci = _spline([(x0 + 0.2, 0.02, -0.15), (x0 + 0.2, -0.05, -0.12), (x0 + 0.22, yb - 0.05, -0.02), (x0 + 0.24, yb - 0.04, 0.03)], 0.02)
        _tube(mb, ci, 0.005, seg=6, mat="cable")
        _cyl(mb, (x0 + 0.24, yb - 0.04, -0.004), (x0 + 0.24, yb - 0.04, 0.008), 0.012, seg=10, mat="plastic")
        # jirones de la cara de acrílico (3 mm)
        yface = yf + 0.004
        xa = rr.uniform(x0 + 0.05, x0 + w * 0.3)
        xb = min(x1 - 0.05, xa + rr.uniform(0.3, 0.55) * w)
        cols = _torn_panel(xa, xb, h - 0.02, 0.25 * h, 0.6 * h, rr, jag=0.05 * h / 0.6)
        peel = rr.uniform(0.6, 1.6)
        grid = []
        for col in cols:
            g = []
            for (x, z) in col:
                dz = (h - 0.02) - z
                g.append((x, yface - peel * dz * dz - 0.15 * dz * max(0.0, nz(Vector((x, 0, z)), 3.0)), z + 0.3 * peel * dz * dz * 0.3))
            grid.append(g)
        _merge(mb, _solid_sheet(_sub_grid(grid, _lv(1, 2, 3), _lv(1, 2, 3)), 0.003, "plastic"))
        xc = x1 - rr.uniform(0.2, 0.5) * w * 0.5
        cols = _torn_panel(xc, x1 - 0.02, 0.02, 0.1 * h, 0.35 * h, rr, jag=0.04 * h / 0.6, from_top=False)
        grid = [[(x, yface - 0.01 * max(0.0, nz(Vector((x, 0, z)), 5.0)) - 0.0005, z) for (x, z) in col] for col in cols]
        _merge(mb, _solid_sheet(_sub_grid(grid, _lv(1, 2, 3), _lv(1, 2, 3)), 0.003, "plastic"))
        _declump(mb)
        return mb


# =====================================================================================================================
# tendedero y cortina (telas = láminas intencionales 'fabric')
# =====================================================================================================================
def _clothespin(mb, x, z, rr, mat=None):
    """Pinza de ropa (2 patas + resorte) apretando el alambre en (x, 0, z)."""
    mat = mat or ("wood" if rr.random() < 0.6 else "plastic")
    tilt = rr.uniform(-8, 8)
    M = _T(x, 0.0, z) @ _R("Y", tilt)
    for sy in (-1, 1):
        _box(mb, (-0.0045, -0.0032, -0.046), (0.0045, 0.0032, 0.026), mat, bevel=0.0012, seg=1,
               m=M @ _T(0, sy * 0.0052, 0) @ _R("X", sy * 3.0))
    _torus(mb, M @ Vector((0, 0, 0.004)), M.to_3x3() @ Vector((1, 0, 0)), 0.0062, 0.0011, n=10, seg=4, mat="metal_rust")


def _garment_grid(kind, xa, xb, ztop, rr, nz, fallen=False):
    """Rejilla (columnas de puntos) de una prenda colgada del alambre entre las pinzas xa..xb (ztop(x) = altura del
    alambre). Silueta por máscara de celdas + caída: pliegues verticales de 2 frecuencias que crecen hacia abajo,
    comba entre pinzas, vaivén alrededor del alambre y giro leve. fallen: cuelga de una sola pinza (gira sobre ella).
    Devuelve (grid, skip) para _sheet."""
    span = xb - xa
    folded = kind in ("towel", "sheet")
    if kind == "towel":
        H, back = rr.uniform(0.5, 0.7), rr.uniform(0.55, 0.85)
    elif kind == "sheet":
        H, back = rr.uniform(0.8, 1.0), rr.uniform(0.6, 0.9)
    elif kind == "shirt":
        H = rr.uniform(0.5, 0.58)
    elif kind == "pants":
        H = rr.uniform(0.85, 0.98)
    else:
        H = rr.uniform(0.24, 0.4)
    sleeve = rr.uniform(0.17, 0.24)
    nu = max(12, int(span / 0.017))
    if kind == "shirt":
        tot = H + sleeve
    elif folded:
        tot = H * (1 + back) + 0.03
    else:
        tot = H
    nv = max(10, int(tot / 0.03))
    waves = [(rr.uniform(0.11, 0.2), rr.uniform(0, 2 * PI), rr.uniform(-6, 6)), (rr.uniform(0.06, 0.09), rr.uniform(0, 2 * PI), rr.uniform(-10, 10))]
    sway = math.radians(rr.uniform(3, 20))
    twist = math.radians(rr.uniform(-12, 12))
    sag_b = 0.0 if folded else rr.uniform(0.015, 0.045)
    xc = (xa + xb) / 2
    fray = [max(0.0, rr.uniform(-0.1, 0.32)) for _ in range(nu + 1)]  # borde inferior desgarrado (trapo)
    holes = set()
    grid = []
    for i in range(nu + 1):
        u = i / nu
        col = []
        for j in range(nv + 1):
            s = tot * j / nv  # distancia de tela desde el borde superior (o desde el borde trasero si va doblada)
            if folded:
                bl = H * back
                if s < bl:              # mitad trasera (y > 0), sube hacia el alambre
                    d, side = bl - s, 1.0
                elif s < bl + 0.03:     # doblez sobre el alambre
                    a_ = (s - bl) / 0.03 * PI
                    d, side = -0.006 * math.sin(a_), math.cos(a_)
                else:
                    d, side = s - bl - 0.03, -1.0
                d = max(d, 0.0) if abs(side) == 1.0 else d
                y0 = 0.0062 * side
                z0 = 0.005 - max(d, 0.0)
                depth = max(d, 0.0)
            else:
                depth = s * (1.0 - fray[i] * (j / nv) ** 2) if kind == "rag" else s
                y0, z0 = -0.0065, 0.012 - depth
            x = xa + span * u
            if kind == "pants":
                leg = -1 if u < 0.5 else 1
                x += leg * 0.03 * max(0.0, depth / H - 0.32)
                x = xc + (x - xc) * (1.0 - 0.12 * depth / H)
            ztp = ztop(min(max(x, xa), xb))
            z0 -= sag_b * math.sin(PI * u) * (1.0 - 0.5 * min(depth / 0.25, 1.0))
            amp = min(depth / 0.3, 1.0)
            fold = 0.0
            for k, (lam, ph, tw) in enumerate(waves):
                A = (0.003 + 0.016 * amp) if k == 0 else (0.0015 + 0.005 * amp)
                fold += A * math.sin(2 * PI * x / lam + ph + math.radians(tw) * depth * 10)
            fold += 0.008 * amp * nz(Vector((x * 1.0, depth, 0.0)), 5.0)
            fold += 0.014 * math.sin(PI * u) * math.exp(-depth / 0.12) * (0 if folded else 1)
            y = y0 + fold
            # vaivén alrededor del alambre y giro leve alrededor de la vertical
            y -= math.sin(sway) * depth
            z = ztp + z0 + (1 - math.cos(sway)) * depth * 0.5
            dx = x - xc
            x = xc + dx * math.cos(twist * amp) - y * math.sin(twist * amp) * 0.3
            y = y + dx * math.sin(twist * amp)
            col.append(Vector((x, y, z)))
        grid.append(col)
    if fallen:  # cuelga de la pinza izquierda: gira la prenda alrededor de ella
        piv = Vector((xa, 0.0, ztop(xa)))
        th = rr.uniform(38, 62)
        grid = [[piv + _R("Y", th * (1.0 - 0.55 * j / nv)).to_3x3() @ (p - piv) for j, p in enumerate(col)] for col in grid]

    def skip(i, j):
        if (i, j) in holes:
            return True
        if kind == "shirt":
            sv = H / (H + sleeve)
            if j / nv > sv and 0.24 * nu < i < 0.76 * nu - 1:
                return True
        if kind == "pants" and j / nv > 0.32 and nu // 2 - 1 <= i <= nu // 2:
            return True
        return False

    return [[(p.x, p.y, p.z) for p in col] for col in grid], skip


def laundry_line(length=3.0, seed=0, detail="high"):
    """Tendedero: alambre galvanizado Ø 3 mm entre dos armellas, con catenaria y quiebres bajo el peso de cada prenda
    (funicular), prendas de tela con pliegues mecidas por el viento (toallas y sábanas dobladas sobre el alambre,
    camisas, pantalones, trapos rotos; una colgando de una sola pinza) y pinzas sueltas.
    Origen: armella izquierda; el alambre va de x = 0 a x = length a z = 0 (antes de la flecha). Las armellas se
    atornillan en superficies verticales: plano x = 0 (mirando a +X) y plano x = length (mirando a -X).
    Las telas son LÁMINAS (material 'fabric', una cara): usar DoubleSide."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        mb = MB()
        L = float(length)
        for (x, sg) in ((0.0, 1.0), (L, -1.0)):
            _cyl(mb, (x - sg * 0.0006, 0, 0), (x + sg * 0.0025, 0, 0), 0.013, seg=12, mat="metal_rust")
            _cyl(mb, (x - sg * 0.05, 0, 0), (x + sg * 0.034, 0, 0), 0.0042, seg=8, mat="metal_rust")
            _torus(mb, (x + sg * 0.048, 0, 0), (0, 1, 0), 0.013, 0.0042, n=16, seg=6, mat="metal_rust")
        # prendas
        kinds = ["towel", "shirt", "pants", "rag", "towel", "shirt", "sheet", "rag"]
        items = []
        x = 0.15 + rr.uniform(0.0, 0.2)
        while x < L - 0.35:
            k = kinds[int(rr.integers(0, len(kinds)))]
            wdt = {"towel": rr.uniform(0.45, 0.65), "shirt": rr.uniform(0.42, 0.5), "pants": rr.uniform(0.36, 0.42),
                   "rag": rr.uniform(0.22, 0.34), "sheet": rr.uniform(0.8, 1.1)}[k]
            if x + wdt > L - 0.12:
                break
            if rr.random() < 0.15:
                items.append(("pin", x, x))
                x += rr.uniform(0.1, 0.25)
                continue
            items.append((k, x, x + wdt))
            x += wdt + rr.uniform(0.04, 0.22)
        fallen_i = int(rr.integers(0, len(items))) if items and rr.random() < 0.7 else -1
        if 0 <= fallen_i < len(items) and items[fallen_i][0] in ("pin", "towel", "sheet"):
            fallen_i = -1
        s0 = 0.02 + 0.02 * L
        loads = []
        for idx, (k, a, b) in enumerate(items):
            wgt = {"pin": 0.002, "towel": 0.03, "shirt": 0.018, "pants": 0.03, "rag": 0.01, "sheet": 0.05}[k]
            pins = [a] if (k == "pin" or idx == fallen_i) else [a, b]
            for p in pins:
                loads.append((p, wgt / len(pins) / max(p * (L - p) / L, 0.05)))

        def wz(xx):
            z = -s0 * 4 * (xx / L) * (1 - xx / L)
            for (a, w) in loads:
                z -= w * (xx * (L - a) / L if xx < a else a * (L - xx) / L)
            return z

        xs = sorted(set([0.061, L - 0.061] + [0.061 + (L - 0.122) * k / int(L / 0.03) for k in range(int(L / 0.03) + 1)]
                        + [p for (p, _) in loads]))
        wire = [Vector((xx, 0.0, wz(xx))) for xx in xs]
        wire = [Vector((0.048 + 0.013 * math.cos(a), 0, 0.013 * math.sin(a))) for a in (PI * 0.9, PI * 0.6, PI * 0.3)] + wire + \
               [Vector((L - 0.048 + 0.013 * math.cos(a), 0, 0.013 * math.sin(a))) for a in (PI * 0.7, PI * 0.4, PI * 0.1)]
        _tube(mb, wire, 0.0015, seg=6, mat="metal_rust")
        for (x, sg) in ((0.0, 1.0), (L, -1.0)):  # cola torcida del amarre
            _tube(mb, [Vector((x + sg * 0.062, 0.0028, wz(x + sg * 0.062) + 0.0)), Vector((x + sg * 0.11, 0.0028, wz(x + sg * 0.11)))],
                  0.0013, seg=4, mat="metal_rust")
        for idx, (k, a, b) in enumerate(items):
            if k == "pin":
                _clothespin(mb, a, wz(a), rr)
                continue
            fallen = idx == fallen_i
            grid, skip = _garment_grid(k, a, b, wz, rr, nz, fallen=fallen)
            _sheet_lod(mb, grid, "fabric", skip, steps=((1, 1), (2, 2), (3, 3)))
            _clothespin(mb, a + 0.01, wz(a + 0.01), rr)
            if not fallen:
                _clothespin(mb, b - 0.01, wz(b - 0.01), rr)
                if b - a > 0.6:
                    _clothespin(mb, (a + b) / 2, wz((a + b) / 2), rr)
        _declump(mb)
        return mb


def curtain_torn(w=1.4, h=1.5, seed=0, detail="high"):
    """Cortina rasgada colgando de una barra con argollas: 2 lienzos con pliegues, tiras desgarradas (con tela faltante)
    que se mecen, agujeros, bastilla deshilachada y, al azar, un lienzo medio desprendido de la barra (o la barra vencida).
    Coordenadas del vano: u = 0..w en X, v = 0..h en Z; la tela cuelga en el plano y ≈ 0 y las ménsulas de la barra van
    a un muro en y = +0,07 (cara interior). La tela es LÁMINA ('fabric', una cara): usar DoubleSide."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        mb = MB()
        zr = h + 0.07
        drop = rr.uniform(0.12, 0.3) if rr.random() < 0.3 else 0.0

        def rod_z(x):
            t = (x + 0.12) / (w + 0.24)
            return zr - 0.008 * math.sin(PI * t) - drop * t

        rod = [Vector((-0.12 + (w + 0.24) * k / 16, 0.0, rod_z(-0.12 + (w + 0.24) * k / 16))) for k in range(17)]
        _tube(mb, rod, 0.0125, seg=12, mat="metal_paint")
        for (x, sg) in ((-0.12, -1), (w + 0.12, 1)):
            _lathe(mb, [(0.0, 0.0), (0.016, 0.006), (0.02, 0.022), (0.014, 0.036), (0.0, 0.04)], seg=14, mat="metal_paint",
                   m=_frame((x - sg * 0.002, 0, rod_z(x)), (sg, 0, 0)))
        for (x, broken) in ((-0.06, False), (w + 0.06, drop > 0)):
            zz = zr if broken else rod_z(x)
            _box(mb, (x - 0.016, 0.0655, zz - 0.035), (x + 0.016, 0.0685, zz + 0.035), "metal_paint", bevel=0.001, seg=1)
            for dz in (-0.022, 0.022):
                _screw(mb, (x, 0.0655, zz + dz), (0, -1, 0), r=0.004)
            if broken:
                _cyl(mb, (x, 0.066, zz), (x, 0.045, zz - 0.004), 0.005, seg=8, mat="metal_paint")
            else:
                _cyl(mb, (x, 0.066, zz), (x, 0.006, zz), 0.005, seg=8, mat="metal_paint")
                _torus(mb, (x, 0.0, zz), (1, 0, 0), 0.0155, 0.0025, n=12, seg=4, mat="metal_paint", arc=200, a0=math.radians(170))
        # lienzos
        split = w * rr.uniform(0.3, 0.55)
        panels = [(0.0, split, rr.uniform(1.6, 2.2), False), (split + rr.uniform(0.0, 0.1), w, rr.uniform(1.2, 1.6), rr.random() < 0.45)]
        for (pa, pb, gather, detached) in panels:
            span = pb - pa
            nring = max(3, int(span / 0.1))
            rings_x = [pa + span * k / (nring - 1) for k in range(nring)]
            n_off = int(rr.integers(2, max(3, nring // 2))) if detached else 0
            for k, rx in enumerate(rings_x):
                if k >= nring - n_off:
                    continue
                _torus(mb, (rx, 0.0, rod_z(rx)), (1, 0, 0), 0.021, 0.0032, n=16, seg=4, mat="metal_paint")
            nu = max(10, int(span * gather / 0.025))
            nv = max(16, int(h / 0.035))
            period = max(3, int(nu / (nring - 1)))
            amp = 0.25 * (span * gather / nu * period) * math.sqrt(max(gather ** 2 - 1, 0.0)) / PI
            tears = sorted({int(rr.integers(2, nu - 2)) for _ in range(int(rr.integers(2, 5)))})
            tear_v = {t: rr.uniform(0.25, 0.7) for t in tears}
            strip_of = []
            sidx = 0
            for i in range(nu + 1):
                if sidx < len(tears) and i > tears[sidx]:
                    sidx += 1
                strip_of.append(sidx)
            strip_sw = [rr.uniform(-28, 12) for _ in range(len(tears) + 1)]
            ph2 = rr.uniform(0, 2 * PI)
            holes = set()
            hem = [int(rr.integers(0, 4)) for _ in range(nu)]
            ztop0 = rod_z(pa) - 0.035
            grid = []
            for i in range(nu + 1):
                u = i / nu
                col = []
                for j in range(nv + 1):
                    v = j / nv  # 0 = abajo, 1 = arriba
                    xr = pa + span * u
                    spread = 1.0 + 0.12 * (1 - v)
                    x = pa + span * (u - 0.5) * spread + span * 0.5
                    ztp = rod_z(min(max(xr, -0.1), w + 0.1)) - 0.035 - 0.012 * abs(math.sin(PI * u * (nring - 1)))
                    if detached:
                        k_last = (nring - n_off - 1) / (nring - 1)
                        if u > k_last:
                            ztp -= (u - k_last) / (1 - k_last + 1e-6) * rr.uniform(0.0, 0.0) + 0.45 * (u - k_last) / (1 - k_last + 1e-6)
                    hgt = ztp - 0.01
                    z = ztp - hgt * (1 - v)
                    a_ = amp * (0.55 + 0.45 * v) * (0.7 + 0.5 * (0.5 + 0.5 * nz(Vector((x * 0.7, 0.0, 0.0)), 3.0)))
                    y = a_ * math.sin(2 * PI * i / period + 0.3 * math.sin(v * 3) + 0.8 * nz(Vector((x, 1.0, z)), 1.5))
                    y += 0.35 * a_ * math.sin(2 * PI * i / (period * 2.7) + ph2) + 0.03 * (1 - v) * nz(Vector((x, 0, z)), 2.0)
                    st = strip_of[i]
                    tv = tear_v.get(tears[min(st, len(tears) - 1)], 0.5) if tears else 0.5
                    if v < tv:
                        ang = math.radians(strip_sw[st]) * (tv - v) / tv
                        y += math.sin(ang) * (tv - v) * hgt
                        z += (1 - math.cos(ang)) * (tv - v) * hgt
                    col.append((x, y, z))
                grid.append(col)

            def skip(i, j, tears=tears, tear_v=tear_v, holes=holes, hem=hem, nv=nv):
                if i in tear_v and j / nv < tear_v[i]:
                    return True
                if (i, j) in holes:
                    return True
                return j < hem[i]

            _sheet_lod(mb, grid, "fabric", skip, steps=((1, 1), (2, 2), (4, 3)))
        _declump(mb)
        return mb
