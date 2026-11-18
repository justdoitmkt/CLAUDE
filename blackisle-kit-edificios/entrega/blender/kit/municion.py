"""kit/municion.py — municiones y su embalaje para MIL_1_almacen (racks de tarimas) y MIL_2_avanzada (tienda que vende munición):
latas metálicas de munición, cajas de cartón de cartuchos, cajas de madera, tarima GMA, tarima de proyectiles de 155 mm y
tarima de cajas flejada. Segunda pasada AAA (regla R-AAA de CLAUDE.md): construcción real de cada pieza (lámina con cantos
redondeados, emboss, empaque de hule, cierre de leva con su gancho de alambre, bisagra de tubos rolados, asa abatible; tablas
individuales con veta y cantos gastados, holguras de 1–2 mm, clavos, travesaños, bisagras, portacandados con grapa y sello,
asas de cuerda torcida de 3 cabos con sus nudos, flejes con sello engargolado; proyectiles con anillo protector de banda,
tapón de izaje, marco de madera con varillas roscadas y tuercas). Nada redondo facetado: cilindros visibles >= 24 lados,
tubos >= 14, alambres <= 6 mm de 12 lados con sombreado continuo (MB.soft), cartuchos de 24.

Mismas firmas, orígenes y huellas que las funciones homónimas de kit/armory.py (que sigue intacto): ammo_can, cardboard_ammo_box,
ammo_crate, pallet_gma, shell_pallet, crate_pallet. Lo que se repite cientos de veces (tarimas, cajas, proyectiles, textos) se
construye una vez por variante y se copia (caché del módulo): la misma semilla da siempre la misma pieza.

Convenciones: metros, Z arriba, origen al centro de la base (z = 0 apoyo), largo en X, frente (estarcidos, broches) hacia -Y.
Estarcidos con tipografía real de plantilla (kit.fonts: «stencil» Saira Stencil One, «stencil2» Allerta Stencil), en inglés e
inocuos (R4). Sin grafiti ni placas (MIL_1 / MIL_2): limpio, de poco uso, algún golpe en los cantos de la madera.
Materiales: wood_od, paint_od, paint_yellow, steel, galvanized, rubber, fabric (cuerda), canvas (cincho), cardboard, brass,
copper, polymer, cable (tinta / interior oscuro), sign_white.
Fuentes de medidas (consultadas 2026-11): ver el docstring de cada función.
"""
import math

import bpy  # noqa: F401  (bpy antes que mathutils / bmesh)
import bmesh
from mathutils import Matrix, Vector

from kit.armory import plan, side, xloft
from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rng, rr_profile
from kit.clinic_equipo import revolve, sweep_frame
from kit.clinic_servicios import _edge_levels, rr_pts, skin
from kit.clinic_servicios import slab as _slab
from kit.fonts import text_font

IN = 0.0254
SEG = 24          # cilindros visibles
SEG_B = 36        # cilindros grandes (proyectiles, latas vistas de cerca)
SEG_T = 16        # tubos, varillas, cuerdas
SEG_W = 12        # alambres <= 6 mm (dentro de mb.soft())
WOOD = "wood_od"
CRATE_DIMS = {"wood": (0.66, 0.36, 0.30), "long": (1.65, 0.42, 0.27), "small": (0.46, 0.30, 0.24)}

_CACHE = {}
_LOD = [0]          # nivel de detalle activo mientras se arma una pieza (0 = completo; 1 = racks: ver crate_pallet)


def _lo():
    return _LOD[0] >= 1


def _at_lod(lod, fn, *a, **k):
    """Arma fn(*a, **k) con el nivel de detalle `lod` activo (los ayudantes lo consultan con _lo())."""
    prev = _LOD[0]
    _LOD[0] = int(lod)
    try:
        return fn(*a, **k)
    finally:
        _LOD[0] = prev


# ======================================================================================================== utilidades
def _cached(key, fn):
    """Construye una sola vez la pieza `key` (un MB que NO se modifica después) y la devuelve en llamadas siguientes."""
    src = _CACHE.get(key)
    if src is None:
        src = fn()
        _CACHE[key] = src
    return src


def _fresh(src, M=None):
    mb = MB()
    mb.join(src, M)
    return mb


def _join_map(mb, src, fn):
    """Copia `src` en `mb` pasando cada vértice por fn(Vector) -> Vector (doblar textos sobre un cilindro)."""
    vm = {v: mb.bm.verts.new(fn(v.co)) for v in src.bm.verts}
    for f in src.bm.faces:
        nf = mb.bm.faces.new([vm[v] for v in f.verts])
        nf.material_index = mb.mi(src.mats[f.material_index])


def _basis(o, ex, ey, ez):
    """Matriz con ejes locales ex, ey, ez (columnas) y origen o."""
    M = Matrix.Identity(4)
    for i in range(3):
        M[i][0], M[i][1], M[i][2], M[i][3] = ex[i], ey[i], ez[i], o[i]
    return M


def _ss(u):
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def _perim(w, d, r, nc, xc=(), yc=()):
    """Contorno de rectángulo redondeado (antihorario, desde la esquina +x+y) con puntos extra en los lados rectos:
    xc = cortes en x sobre los lados ±Y, yc = cortes en y sobre los lados ±X. Devuelve [(x, y, nx, ny, lado)]."""
    out = []
    hw, hd = w / 2, d / 2
    r = max(min(r, hw - 1e-4, hd - 1e-4), 2e-4)
    xs = sorted(x for x in xc if -hw + r + 1e-5 < x < hw - r - 1e-5)
    ys = sorted(y for y in yc if -hd + r + 1e-5 < y < hd - r - 1e-5)

    def arc(cx, cy, a0):
        for k in range(nc + 1):
            a = a0 + PI / 2 * k / nc
            out.append((cx + r * math.cos(a), cy + r * math.sin(a), math.cos(a), math.sin(a), "c"))
    arc(hw - r, hd - r, 0.0)
    out += [(x, hd, 0.0, 1.0, "y+") for x in reversed(xs)]
    arc(-hw + r, hd - r, PI / 2)
    out += [(-hw, y, -1.0, 0.0, "x-") for y in reversed(ys)]
    arc(-hw + r, -hd + r, PI)
    out += [(x, -hd, 0.0, -1.0, "y-") for x in xs]
    arc(hw - r, -hd + r, 1.5 * PI)
    out += [(hw, y, 1.0, 0.0, "x+") for y in ys]
    return out


def _ring_band(mb, M, w, d, rc, sect, mat, nc=6):
    """Cordón cerrado que sigue un rectángulo redondeado w × d (radio rc) con la sección [(desplazamiento, z)] (lazo cerrado):
    empaques, bordes rolados, dobladillos."""
    loops = [[(x, y, z) for (x, y) in rr_pts(w + 2 * o, d + 2 * o, max(rc + o, 3e-4), nc)] for (o, z) in sect]
    return skin(mb, loops, mat, M, closed=True)


def _round_sect(cx, cz, rx, rz, n=12):
    return [(cx + rx * math.cos(2 * PI * k / n), cz + rz * math.sin(2 * PI * k / n)) for k in range(n)]


def stencil(mb, s, size, M, mat="paint_yellow", depth=0.00045, font="stencil", align="CENTER", spacing=1.0, sink=0.0003):
    """Estarcido de pintura con tipografía de plantilla real (kit.fonts), centrado en el origen de M (plano XY, +Z hacia
    afuera; la altura de mayúsculas queda centrada en y = 0). Sobresale `depth` y se hunde `sink` (más en madera, que no
    es plana)."""
    lo = _lo()
    key = ("txt", s, round(size, 5), round(depth, 6), mat, font, align, spacing, round(sink, 6), lo)

    def build():
        t = MB()
        res = (2 if size >= 0.025 else 1) if lo else (3 if size >= 0.025 else (2 if size >= 0.012 else 1))
        text_font(t, s, size, depth, mat, None, font=font, align=align, res=res, spacing=spacing, sink=sink)
        if lo:
            _drop_back(t, -sink * 0.5)
        return t
    mb.join(_cached(key, build), M @ _T(0, -size * 0.355, 0))


def stencil_cyl(mb, s, size, R, M, ang=-PI / 2, mat="paint_yellow", depth=0.0005, font="stencil", sink=0.0003):
    """Estarcido doblado sobre un cilindro de radio R (eje Z de M), centrado en el ángulo `ang` y en z = 0 local."""
    lo = _lo()
    key = ("txt", s, round(size, 5), round(depth, 6), mat, font, "CENTER", 1.0, lo, round(sink, 6))

    def build():
        t = MB()
        text_font(t, s, size, depth, mat, None, font=font, align="CENTER", res=2, sink=sink)
        if lo:
            _drop_back(t, -sink * 0.5)
        return t
    src = _cached(key, build)

    def fn(co):
        th = ang + co.x / R
        rr = R + co.z
        return M @ Vector((rr * math.cos(th), rr * math.sin(th), co.y - size * 0.355))
    _join_map(mb, src, fn)


def _drop_back(t, zlim):
    """Quita las caras traseras de las letras (hundidas en la superficie, nunca visibles): versión ligera."""
    t.bm.faces.ensure_lookup_table()
    dead = [f for f in t.bm.faces if max(v.co.z for v in f.verts) < zlim]
    if dead:
        bmesh.ops.delete(t.bm, geom=dead, context="FACES_ONLY")


def nail(mb, M, d=0.0062, mat="steel"):
    """Cabeza de clavo de caja (plana, apenas abombada) sobre z = 0 local, +Z hacia afuera; el vástago queda en la madera."""
    with mb.soft():
        if _lo():                                            # disco de 8 lados de sombreado continuo
            revolve(mb, [(d * 0.5, -0.0012), (d * 0.5, 0.0004), (0.0, 0.0010)], mat, seg=8, M=M, caps=False)
        else:
            revolve(mb, [(d * 0.5, -0.0016), (d * 0.5, 0.0004), (d * 0.40, 0.0009), (0.0, 0.0011)], mat, seg=10, M=M, caps=False)


def rivet(mb, M, d=0.007, mat="steel", seg=SEG_W):
    """Cabeza de remache / tornillo de gota sobre z = 0 local (hundida 0,4 mm), sombreado continuo (cabezas <= 8 mm)."""
    with mb.soft():
        if _lo():
            revolve(mb, [(d / 2, -0.0004), (d * 0.42, d * 0.17), (0.0, d * 0.3)], mat, seg=8, M=M, caps=False)
        else:
            revolve(mb, [(d / 2, -0.0004), (d / 2, 0.0002), (d * 0.42, d * 0.17), (d * 0.24, d * 0.27), (0.0, d * 0.3)], mat, seg=seg,
                    M=M, caps=False)


def wire(mb, pts, r, mat="steel", bend=0.006, nseg=4, caps=True, seg=None):
    """Alambre / varilla delgada por una polilínea con dobleces de radio real. r <= 3 mm: 12 lados de sombreado continuo."""
    lo = _lo()
    P = fillet(pts, bend, min(nseg, 2) if lo else nseg) if len(pts) > 2 else pts
    out = [P[0]]
    for p in P[1:]:
        if (Vector(p) - Vector(out[-1])).length > 1e-6:
            out.append(p)
    if lo:                                                   # alambres y varillas de 8 lados de sombreado continuo
        with mb.soft():
            mb.tube(out, r, seg=8, mat=mat, caps=caps)
    elif r <= 0.0031:
        with mb.soft():
            mb.tube(out, r, seg=seg or (8 if r < 0.0009 else SEG_W), mat=mat, caps=caps)
    else:
        mb.tube(out, r, seg=SEG_T if r < 0.006 else SEG, mat=mat, caps=caps)


def band(mb, path, w=0.019, t=0.0006, normal=(1, 0, 0), mat="steel", closed=True):
    """Fleje de acero (cinta de w × t con cantos rolados) a lo largo de un lazo plano; `normal` = normal del plano del lazo."""
    prof = [(t / 2, w / 2), (-t / 2, w / 2), (-t / 2, -w / 2), (t / 2, -w / 2)] if _lo() else rr_profile(t, w, t * 0.45, n=1)
    mb.sweep(prof, path, mat=mat, closed_profile=True, closed_path=closed, normal=normal)


def band_seal(mb, M, w=0.019, L=0.032, mat="galvanized"):
    """Sello engargolado de fleje (camisa de lámina doblada sobre los dos extremos) con dos pares de muescas de engargolado,
    centrado en el origen de M (largo en X, apoyado en z = 0). Versión ligera: sin sello."""
    if _lo():
        return
    h, wd = 0.0021, w + 0.0026
    st = []
    xs = [-L / 2, -L / 2 + 0.0015]
    for xn in (-L * 0.22, L * 0.22):
        xs += [xn - 0.004, xn - 0.0022, xn - 0.0012, xn + 0.0012, xn + 0.0022, xn + 0.004]
    xs += [L / 2 - 0.0015, L / 2]
    for x in xs:
        notch = any(abs(x - xn) < 0.0013 for xn in (-L * 0.22, L * 0.22))
        mid = any(0.0013 <= abs(x - xn) < 0.0023 for xn in (-L * 0.22, L * 0.22))
        end = abs(abs(x) - L / 2) < 1e-6
        ww = wd - (0.0034 if notch else (0.0016 if mid else 0.0)) - (0.0008 if end else 0.0)
        hh = h - (0.0006 if notch else 0.0) - (0.0006 if end else 0.0)
        st.append((x, ww, hh, hh / 2, (0.0008, 0.0008, 0.0004, 0.0004)))
    xloft(mb, st, mat, n=2, M=M)


def _resample(P, step):
    P = [Vector(p) for p in P]
    out = [P[0]]
    for a, b in zip(P[:-1], P[1:]):
        L = (b - a).length
        n = max(1, int(math.ceil(L / step)))
        for k in range(1, n + 1):
            out.append(a.lerp(b, k / n))
    return out


def _ptframes(P):
    """Marcos de transporte paralelo (T, N, B) a lo largo de una polilínea."""
    n = len(P)
    T = []
    for i in range(n):
        a = P[min(i + 1, n - 1)] - P[max(i - 1, 0)]
        T.append(a.normalized() if a.length > 1e-9 else Vector((0, 0, 1)))
    ref = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
    N = (ref - T[0] * ref.dot(T[0])).normalized()
    out = []
    for i in range(n):
        if i:
            N = (N - T[i] * N.dot(T[i]))
            N = N.normalized() if N.length > 1e-9 else out[-1][1]
        out.append((T[i], N, T[i].cross(N)))
    return out


def rope(mb, pts, r=0.0062, pitch=0.030, seg=15, mat="fabric", caps=True, phase=0.0, smooth=True, per_turn=7):
    """Cuerda torcida de 3 cabos de diámetro 2r: sección = unión de 3 círculos (cabos de radio 0,56 r a 0,44 r del eje)
    que gira a paso `pitch`; los anillos giran con la torsión, así las aristas entre cabos siguen la hélice sin dientes."""
    P = [Vector(p) for p in pts]
    if _lo():                                                # 9 lados (3 por cabo) y un anillo cada media vuelta
        seg, per_turn = 9, 2
    if smooth and len(P) > 2:
        P = [Vector(p) for p in spline(P, 2 if _lo() else 3)]
    P = _resample(P, pitch / per_turn)
    F = _ptframes(P)
    acc = [0.0]
    for i in range(1, len(P)):
        acc.append(acc[-1] + (P[i] - P[i - 1]).length)
    rs, dd = 0.56, 0.44
    per = seg // 3
    rad = []
    for k in range(seg):
        dl = abs((k % per) - per / 2) * 2 * PI / seg
        sn = dd * math.sin(dl)
        rad.append(r * (dd * math.cos(dl) + math.sqrt(max(rs * rs - sn * sn, 0.0))))
    rings = []
    for i, p in enumerate(P):
        T, N, B = F[i]
        tw = 2 * PI * acc[i] / pitch + phase
        ring = []
        for k in range(seg):
            a = 2 * PI * k / seg + tw
            ring.append(mb.bm.verts.new(p + (N * math.cos(a) + B * math.sin(a)) * rad[k]))
        rings.append(ring)
    with mb.soft():                              # la fibra se ve continua; la silueta y el surco dan los cabos
        for i in range(len(rings) - 1):
            A, Bq = rings[i], rings[i + 1]
            for k in range(seg):
                kk = (k + 1) % seg
                mb.face([A[k], A[kk], Bq[kk], Bq[k]], mat)
    if caps:
        mb.face(list(reversed(rings[0])), mat)
        mb.face(rings[-1], mat)


def spline(pts, n=3):
    """Curva Catmull-Rom por los puntos (n subdivisiones por tramo)."""
    P = [Vector(p) for p in pts]
    out = []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, len(P) - 1)]
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1])
    return [tuple(p) for p in out]


def rope_knot(mb, M, s=0.0056, r=0.0062, mat="fabric", phase=0.0):
    """Nudo de tope (trébol apretado) de la cuerda, centrado en el origen de M; cabe en ~ 6,5 s × 6,5 s × 2 (s + r)."""
    pts = []
    n = 10 if _lo() else 22
    for k in range(n + 1):
        t = 2 * PI * k / n + 0.35
        pts.append(M @ Vector((s * (math.sin(t) + 2 * math.sin(2 * t)), s * (math.cos(t) - 2 * math.cos(2 * t)),
                               -s * 0.9 * math.sin(3 * t))))
    rope(mb, pts, r=r, pitch=0.030, seg=12, mat=mat, caps=True, phase=phase, smooth=False, per_turn=5)


# --------------------------------------------------------------------------------------------- madera: tablas, bloques
def wplank(mb, mn, mx, mat=WOOD, r=0.0028, rs=None, grain=0.00014, cup=0.0002, bow=0.0003, step=0.085, end=0.0011,
           wear=0.0016, kw=None, dings=None, hidden=False):
    """Tabla aserrada y cepillada: sección de cantos redondeados (4 segmentos por canto, nada facetado) con veta en
    geometría (crestas de 0,1–0,2 mm a lo largo), leve combado (cup) y arqueo (bow), cantos gastados con golpes al azar
    (anillos extra en cada golpe) y cabezas de corte de sierra con un chaflán de 1 mm, ligeramente fuera de escuadra.
    El eje largo es el mayor de la caja mn..mx; el ancho, el siguiente. hidden=True (fondos, patines: caras que casi no se
    ven): sin golpes, una sola cresta por cara y anillos cada 15 cm (los cantos siguen redondos)."""
    rs = rs if rs is not None else rng(0)
    lo = _lo()
    if hidden:
        step, kw, dings, cup, bow = max(step, 0.15), 1, [], 0.0, 0.0
    if lo:                                                   # ligera: cantos de 2 segmentos, sin veta ni golpes, 2 anillos
        kw, dings, cup, bow, grain, end, step = 0, [], 0.0, 0.0, 0.0, 0.0, 1e9
    ext = [mx[i] - mn[i] for i in range(3)]
    a = max(range(3), key=lambda i: ext[i])
    b, c = [i for i in range(3) if i != a]
    if ext[b] < ext[c]:
        b, c = c, b
    W, T, L = ext[b], ext[c], ext[a]
    bc, cc = (mn[b] + mx[b]) / 2, (mn[c] + mx[c]) / 2
    r = min(r, T * 0.38, W * 0.38)
    nw = kw if kw is not None else (3 if W > 0.05 else (1 if W > 0.025 else 0))
    nn = 1 if (T > 0.03 and not lo) else 0
    nk = 2 if lo else 4
    hw, ht = W / 2, T / 2
    prof = []                                   # (pb, pc, nb, nc, cara: 1 / -1 cara ancha, 0 canto; esquina, u)
    cs = [(hw - r, ht - r, 0.0), (-hw + r, ht - r, PI / 2), (-hw + r, -ht + r, PI), (hw - r, -ht + r, 1.5 * PI)]
    for ci, (cx, cy, a0) in enumerate(cs):
        for k in range(nk + 1):
            an = a0 + PI / 2 * k / nk
            prof.append((cx + r * math.cos(an), cy + r * math.sin(an), math.cos(an), math.sin(an), 0, ci if 0 < k < nk else -1, 0.0))
        if ci == 0:                             # cara +c (ancha) de +b a -b
            for j in range(nw):
                u = 1 - 2 * (j + 1) / (nw + 1)
                prof.append((u * (hw - r), ht, 0.0, 1.0, 1, -1, u))
        elif ci == 1:
            for j in range(nn):
                prof.append((-hw, 0.0, -1.0, 0.0, 0, -1, 0.0))
        elif ci == 2:
            for j in range(nw):
                u = -1 + 2 * (j + 1) / (nw + 1)
                prof.append((u * (hw - r), -ht, 0.0, -1.0, -1, -1, u))
        else:
            for j in range(nn):
                prof.append((hw, 0.0, 1.0, 0.0, 0, -1, 0.0))
    # golpes en los cantos: (esquina, posición, ancho, profundidad)
    if dings is None:
        dings = []
        for ci in range(4):
            for _ in range(int(rs.integers(0, 2))):
                dings.append((ci, float(rs.uniform(0.05, 0.95)) * L, float(rs.uniform(0.006, 0.03)), float(rs.uniform(0.4, 1.0)) * wear))
    g_ph = [float(rs.uniform(0, 2 * PI)) for _ in prof]
    g_fr = [float(rs.uniform(1.5, 7.0)) for _ in prof]
    cup_s = float(rs.uniform(-1, 1)) * cup
    bow_s = float(rs.uniform(-1, 1)) * bow
    sweep_s = float(rs.uniform(-1, 1)) * bow * 0.6
    # posiciones de anillos a lo largo
    e = min(end, L * 0.1)
    n_in = max(1, int(round((L - 2 * e) / step))) if step < 1.0 else 1
    S = {0.0, e, L - e, L}
    for k in range(1, n_in):
        S.add(e + (L - 2 * e) * k / n_in)
    for (_, p, wd, _) in dings:
        for q in (p - wd * 0.8, p, p + wd * 0.8):
            if e < q < L - e:
                S.add(q)
    S = sorted(S)
    S2 = [S[0]]
    for s_ in S[1:]:
        if s_ - S2[-1] > 0.0015:
            S2.append(s_)
    if S2[-1] != L:
        S2[-1] = L
    tb0 = (float(rs.uniform(-1, 1)) * 0.0006, float(rs.uniform(-1, 1)) * 0.0004)
    tb1 = (float(rs.uniform(-1, 1)) * 0.0006, float(rs.uniform(-1, 1)) * 0.0004)
    loops = []
    for si, s_ in enumerate(S2):
        endring = si in (0, len(S2) - 1)
        u = s_ / L
        dc = bow_s * math.sin(PI * u)
        db = sweep_s * math.sin(PI * u)
        ring = []
        for j, (pb, pc, nb, ncn, face, ci, uu) in enumerate(prof):
            ob = oc = 0.0
            if face:
                ob, oc = 0.0, face * grain * math.sin(g_fr[j] * u * 2 * PI + g_ph[j])
                oc += cup_s * (1 - uu * uu)
            elif ci >= 0:
                dg = 0.0
                for (dci, dp, dw, dd) in dings:
                    if dci == ci:
                        dg += dd * math.exp(-((s_ - dp) / (dw * 0.5)) ** 2)
                ob, oc = -nb * dg * 0.75, -ncn * dg * 0.75
            q = [0.0, 0.0, 0.0]
            pa = mn[a] + s_
            if endring:
                tbx = tb0 if si == 0 else tb1
                pa += tbx[0] * pb / max(hw, 1e-4) + tbx[1] * pc / max(ht, 1e-4)
                sc = e
                ob -= nb * sc
                oc -= ncn * sc
            q[a] = pa
            q[b] = bc + pb + ob + db
            q[c] = cc + pc + oc + dc
            ring.append(tuple(q))
        loops.append(ring)
    skin(mb, loops, mat)


def _fix_cuts(xs):
    return sorted({round(x, 6) for x in xs})


def holed_slab(mb, M, L, W, T, holes=(), ch=0.0025, rc=0.004, nc=4, mat=WOOD, n=24, chh=None, ne=4):
    """Bloque / tablero L (X) × W (Y) × T (Z de 0 a T) con barrenos pasantes verticales [(cx, cy, a, b, e)] (superelipse de
    semiejes a, b y exponente e: 2 = círculo, 4–6 = ranura). Cantos exteriores redondeados ch (ne segmentos), bordes de
    barreno con chaflán redondo chh. Caras superior / inferior partidas en n-gonos por columnas de barrenos (malla soldada y
    cerrada, sin booleanos). n múltiplo de 4."""
    chh = ch if chh is None else chh
    if _lo():
        ne, nc = min(ne, 1), min(nc, 1)
    cols = _fix_cuts([h[0] for h in holes])
    lv = _edge_levels(T, ch, ch, ne) if ch > 0 else [(0.0, 0.0), (0.0, T)]
    pts_lv = [_perim(L - 2 * dl, W - 2 * dl, max(rc - dl, 3e-4), nc, xc=cols) for (dl, z) in lv]
    loops = [[(p[0], p[1], z) for p in P] for P, (dl, z) in zip(pts_lv, lv)]
    V = skin(mb, loops, mat, M, cap0=False, cap1=False)
    hl = []
    nh = 1 if _lo() else 3
    for j in range(nh + 1):
        p = PI / 2 * j / nh
        hl.append((chh * (1 - math.sin(p)), chh * (1 - math.cos(p))))
    for j in range(nh + 1):
        p = PI / 2 * j / nh
        hl.append((chh * (1 - math.cos(p)), T - chh + chh * math.sin(p)))
    unit = [(math.cos(2 * PI * k / n), math.sin(2 * PI * k / n)) for k in range(n)]
    H = []
    for (cx, cy, ha, hb, he) in holes:
        sl = [(math.copysign(abs(c) ** (2 / he), c), math.copysign(abs(s) ** (2 / he), s)) for (c, s) in unit]
        lp = [[(cx + (ha + f) * u, cy + (hb + f) * v, z) for (u, v) in sl] for (f, z) in hl]
        Vh = skin(mb, lp, mat, M, cap0=False, cap1=False)
        H.append((round(cx, 6), cy, Vh[0], Vh[-1]))

    def faces(ring, P, hidx):
        N = len(ring)
        if not cols:
            mb.face(ring if hidx else list(reversed(ring)), mat)
            return
        ib, it = {}, {}
        for i, p in enumerate(P):
            for cx in cols:
                if abs(p[0] - cx) < 1e-6:
                    (it if p[4] == "y+" else ib)[cx] = i

        def fwd(i, j):
            out, k = [], i
            while True:
                out.append(ring[k])
                if k == j:
                    break
                k = (k + 1) % N
            return out

        def up(cx):               # columna cx de -y a +y: mitades izquierdas de los barrenos (270° -> 180° -> 90°)
            out = []
            for (hx, cy, h0, h1) in sorted([h for h in H if h[0] == cx], key=lambda h: h[1]):
                hr = h1 if hidx else h0
                out += [hr[k] for k in range(3 * n // 4, n // 4 - 1, -1)]
            return out

        def down(cx):             # columna cx de +y a -y: mitades derechas (90° -> 0° -> 270°)
            out = []
            for (hx, cy, h0, h1) in sorted([h for h in H if h[0] == cx], key=lambda h: -h[1]):
                hr = h1 if hidx else h0
                out += [hr[k % n] for k in range(n // 4, -n // 4 - 1, -1)]
            return out
        bnd = [None] + cols + [None]
        for xa, xb in zip(bnd[:-1], bnd[1:]):
            if xa is None:
                poly = fwd(it[xb], ib[xb]) + up(xb)
            elif xb is None:
                poly = fwd(ib[xa], it[xa]) + down(xa)
            else:
                poly = fwd(ib[xa], ib[xb]) + up(xb) + fwd(it[xb], it[xa]) + down(xa)
            mb.face(poly if hidx else list(reversed(poly)), mat)
    faces(V[-1], pts_lv[-1], True)
    faces(V[0], pts_lv[0], False)


# ======================================================================================================== cartuchos
CAL = {   # (radio del culote / pestaña, largo de vaina, largo total, paso del eslabón) — .50 BMG y 7,62 × 51 (cinta)
    "50": dict(rim=0.0102, base=0.01015, sh=0.00905, neck=0.0071, bul=0.0065, case=0.0993, sh_z=0.0745, nk_z=0.0820,
               oal=0.1380, rim_t=0.0021, groove=0.0085, pitch=0.0250),
    "762": dict(rim=0.00597, base=0.00598, sh=0.00576, neck=0.00439, bul=0.00391, case=0.0512, sh_z=0.0396, nk_z=0.0436,
                oal=0.0711, rim_t=0.00127, groove=0.00502, pitch=0.0135),
}


def cartridge(mb, M, cal="50", seg=SEG, lite=False):
    """Cartucho metálico real (perfil de .50 BMG o 7,62 × 51) a lo largo de Z local, culote en z = 0: pestaña, ranura del
    extractor, vaina cónica, hombro, cuello y proyectil con camisa de cobre, ojiva tangente y punta redondeada.
    Fuente: en.wikipedia.org/wiki/.50_BMG (vaina 99,3 mm, total 138 mm, pestaña 20,4 mm, cuello 14,2 mm, bala 13 mm)."""
    c = CAL[cal]
    rt, g = c["rim_t"], c["groove"]
    prof = [(0.0, 0.0), (c["rim"] * 0.93, 0.0), (c["rim"], rt * 0.25), (c["rim"], rt * 0.8), (c["rim"] * 0.97, rt),
            (g, rt * 1.35), (g, rt * 2.0), (c["base"] * 0.985, rt * 2.6), (c["base"], rt * 2.9)]
    if lite:
        prof = [(0.0, 0.0), (c["rim"], rt * 0.3), (c["rim"], rt), (g, rt * 1.6), (c["base"], rt * 2.9)]
    zs, zn, L = c["sh_z"], c["nk_z"], c["case"]
    prof += [(c["sh"] + (c["base"] - c["sh"]) * 0.5, zs * 0.55), (c["sh"], zs), (c["sh"] * 0.97, zs + (zn - zs) * 0.35),
             (c["neck"] * 1.04, zn - (zn - zs) * 0.2), (c["neck"], zn), (c["neck"], L - 0.0004), (c["neck"] * 0.97, L),
             (c["bul"] * 0.96, L)]
    revolve(mb, prof, "brass", seg=seg, M=M, caps=False)
    rb = c["bul"]
    z0, z1 = L - 0.002, c["oal"]
    lo = (z1 - z0)
    bp = [(rb * 1.002, z0), (rb, z0 + lo * 0.25)]
    nb = 4 if lite else 7
    for k in range(1, nb + 1):                      # ojiva tangente
        u = k / (nb + 1)
        bp.append((rb * math.sqrt(max(1 - u ** 1.6, 0.0)) * 0.98 + rb * 0.06 * (1 - u), z0 + lo * (0.25 + 0.72 * u)))
    bp += [(rb * 0.08, z1 - lo * 0.006), (0.0, z1)]
    revolve(mb, bp, "copper", seg=seg, M=M, caps=True)


def _case_r(cal, z):
    """Radio de la vaina (perfil de cartridge) a la altura z: cuerpo cónico entre el culote y el hombro."""
    c = CAL[cal]
    z1, z2 = c["rim_t"] * 2.9, c["sh_z"] * 0.55
    rm = c["sh"] + (c["base"] - c["sh"]) * 0.5
    if z <= z1:
        return c["base"]
    if z <= z2:
        return c["base"] + (rm - c["base"]) * (z - z1) / (z2 - z1)
    return rm + (c["sh"] - rm) * min((z - z2) / (c["sh_z"] - z2), 1.0)


def _link_loop(mb, M, r, z0, w, a0, a1, t=0.0007, seg=16, mat="steel"):
    """Abrazadera en C de eslabón de cinta (lámina t × w) alrededor del eje Z de M, de a0 a a1 (rad), con cabezas cerradas."""
    rings = revolve(mb, [(r, z0), (r + t, z0 + 0.0003), (r + t, z0 + w - 0.0003), (r, z0 + w)], mat, seg=seg, M=M, a0=a0,
                    a1=a1, closed=True)
    mb.face([rings[k][0] for k in range(4)], mat)
    mb.face([rings[k][-1] for k in reversed(range(4))], mat)


def belt_layer(mb, M, n, cal="50", links=True, lite=False, seg=SEG):
    """Capa de cinta eslabonada: n cartuchos acostados a lo largo de +Y local (culote en y = 0), separados el paso del
    eslabón a lo largo de +X local; eslabones de lámina (abrazadera propia al centro de la vaina y dos abrazaderas del
    eslabón vecino) con su puente por abajo."""
    c = CAL[cal]
    p = c["pitch"]
    rr = c["base"] * 0.97 - 0.0006                           # abrazadera apretada sobre la vaina
    for i in range(n):
        Mi = M @ _T(p * i, 0, 0) @ _Rx(-90)                  # z local del cartucho = +Y; y local = -Z (abajo)
        cartridge(mb, Mi, cal, seg=seg, lite=lite)
        if not links:
            continue
        a0, a1 = PI / 2 + 0.75, PI / 2 + 2 * PI - 0.75       # abertura hacia abajo
        L = c["sh_z"]
        for (zz, ww, da) in ((L * 0.40, L * 0.20, 0.0), (L * 0.10, L * 0.13, 0.2), (L * 0.74, L * 0.13, 0.2)):
            rl = max(_case_r(cal, zz), _case_r(cal, zz + ww)) - 0.0003
            _link_loop(mb, Mi, rl, zz, ww, a0 + da, a1 - da, t=0.0013)
        if i < n - 1:                                        # puente bajo los cartuchos
            mb.box((p * 0.15, L * 0.12, -rr - 0.0012), (p * 0.85, L * 0.86, -rr + 0.0012), "steel", bevel=0.0003, seg=1,
                   m=M @ _T(p * i, 0, 0))


# ======================================================================================================== lata de munición
def _can_dims(size):
    # M2A1 (.50) 11,75 × 6 × 7,5 in; M19A1 (.30 / 7,62) ~ 10,9 × 3,9 × 7 in (exteriores, con tapa y cierre)
    return (0.2985, 0.1524, 0.1905) if size == "large" else (0.2770, 0.0990, 0.1780)


def _can_body(mb, Lb, Wb, rc, zl0, zb, open_, t=0.001, nc=6):
    """Cuerpo de lámina de la lata: costura reforzada (cordón) en el canto inferior, fondo hundido, costados largos con panel
    embutido (hundido 1,2 mm, transición de 7 mm), boca con borde redondo; abierta: pared con espesor y piso interior."""
    px = Lb / 2 - 0.028
    pz0, pz1 = 0.026, zl0 - 0.016
    tr, dE = 0.007, 0.0012
    xs = set()
    for sg in (-1, 1):
        for f in (0.0, 0.33, 0.67, 1.0):
            xs.add(round(sg * (px - tr * f), 6))
        xs.add(round(sg * (px + 0.008), 6))
    ni = max(2, int(round(2 * (px - tr) / 0.045)))
    for k in range(1, ni):
        xs.add(round(-(px - tr) + 2 * (px - tr) * k / ni, 6))
    P = _perim(Lb, Wb, rc, nc, xc=sorted(xs), yc=(-Wb * 0.2, Wb * 0.2))

    def dep(x, z):
        return dE * _ss((px - abs(x)) / tr) * _ss((z - pz0) / tr) * _ss((pz1 - z) / tr)

    def loop(z, off, emb=True):
        out = []
        for (x, y, nx, ny, sd) in P:
            o = off - (dep(x, z) if (emb and sd in ("y+", "y-")) else 0.0)
            out.append((x + nx * o, y + ny * o, z))
        return out
    zw = {0.0095, pz0 - 0.006, pz1 + 0.006}
    for f in (0.0, 0.33, 0.67, 1.0):
        zw |= {pz0 + tr * f, pz1 - tr * f}
    nz = max(1, int(round((pz1 - pz0 - 2 * tr) / 0.04)))
    for k in range(1, nz):
        zw.add(pz0 + tr + (pz1 - pz0 - 2 * tr) * k / nz)
    zw = sorted(zw)
    bead = [(0.0005, 0.0003), (0.0016, 0.0011), (0.0040, 0.0013), (0.0056, 0.0008), (0.0068, 0.0002), (0.0078, 0.0)]
    loops = [loop(0.0025, -0.0062, False), loop(0.0006, -0.0048, False), loop(0.0, -0.0026, False), loop(0.0, -0.0012, False)]
    loops += [loop(z, o, False) for (z, o) in bead]
    loops += [loop(z, 0.0) for z in zw]
    loops += [loop(zb - 0.0016, 0.0, False), loop(zb - 0.0005, -0.0002, False)]
    if open_:
        loops += [loop(zb, -t * 0.5, False), loop(zb - 0.0005, -t + 0.0002, False), loop(zb - 0.0016, -t, False)]
        loops += [loop(z, -t) for z in reversed(zw)]
        loops += [loop(0.0080, -t, False), loop(0.0058, -t - 0.0007, False), loop(0.0050, -t - 0.0022, False)]
    else:
        loops += [loop(zb, -0.0015, False)]
    skin(mb, loops, "paint_od")
    return P, dep


def _can_lid(lid, L, W, H, zl0, rcl, t=0.001, nc=6, inner=True):
    """Tapa embutida: faldón con dobladillo rolado, canto superior de radio 6 mm, panel realzado de 2,5 mm (radio de esquina
    12 mm) y cara interior con su radio; devuelve la altura de la cara interior."""
    pan_in, pan_h, pan_r, re = 0.024, 0.0025, 0.012, 0.006
    zt = H - pan_h
    zi = zt - 0.0035                                    # cara interior del techo de la tapa

    def LP(off, z, rr=None):
        rr = max(rcl + off, 0.003) if rr is None else rr
        return [(x, y, z) for (x, y) in rr_pts(L + 2 * off, W + 2 * off, rr, nc)]
    loops = []
    if inner:
        loops += [LP(-t - 0.0045, zi, rcl - 0.004), LP(-t - 0.0015, zi - 0.0008), LP(-t - 0.0004, zi - 0.0026), LP(-t, zi - 0.0045)]
        loops += [LP(-t, zl0 + 0.0022)]
    loops += [LP(-t * 0.6, zl0 + 0.0006), LP(-0.0002, zl0 - 0.0001), LP(0.0005, zl0 + 0.0008), LP(0.0006, zl0 + 0.0021),
              LP(0.0, zl0 + 0.0034)]
    for j in range(5):                                   # canto superior redondo (4 tramos de 22,5°)
        p = PI / 2 * j / 4
        loops.append(LP(-re * (1 - math.cos(p)), zt - re + re * math.sin(p)))
    loops += [LP(-pan_in, zt, pan_r + 0.002), LP(-pan_in - 0.0011, zt + 0.0004, pan_r + 0.0012),
              LP(-pan_in - 0.0022, zt + pan_h * 0.5, pan_r + 0.0006), LP(-pan_in - 0.0033, H - 0.0004, pan_r),
              LP(-pan_in - 0.0045, H, pan_r - 0.0008)]
    skin(lid, loops, "paint_od", cap0=inner, cap1=True)
    return zi


def _can_handle(mb, x0, y0, z0, hx, big):
    """Asa abatible de fleje estampado (12 × 2,6 mm, cantos rolados) en U, plegada sobre la tapa, con los extremos enrollados
    sobre la barra de dos lazos rectangulares de alambre de 4 mm soldados a la tapa (eje de giro a lo largo de X)."""
    bz = z0 + 0.0045
    for sx in (-1, 1):
        x = x0 + sx * hx
        wire(mb, [(x - 0.0095, y0, z0 - 0.0006), (x - 0.0095, y0, bz), (x + 0.0095, y0, bz), (x + 0.0095, y0, z0 - 0.0006)],
             0.002, "paint_od", bend=0.0022, nseg=4)
    rr = 0.002 + 0.0013 + 0.0003
    zl = bz + rr
    gy = 0.030 if big else 0.026
    path = fillet([(x0 - hx, y0 + 0.0002, zl), (x0 - hx, y0 + gy, zl), (x0 + hx, y0 + gy, zl), (x0 + hx, y0 + 0.0002, zl)], 0.011, 6)
    prof = rr_profile(0.012, 0.0026, 0.0012, n=4)
    sweep_frame(mb, prof, path, "paint_od", up=(0, 0, 1))
    for sx in (-1, 1):                                   # ojos enrollados (270°) sobre la barra
        x = x0 + sx * hx
        pts = [(x, y0 + rr * math.cos(a), bz + rr * math.sin(a)) for a in [PI / 2 + (PI * 1.45) * k / 12 for k in range(13)]]
        pts = [(x, y0 + 0.0004, zl)] + pts
        sweep_frame(mb, rr_profile(0.0026, 0.012, 0.0012, n=4), pts, "paint_od", up=(1, 0, 0))


def ammo_can(size="large", seed=0, open=False):
    """Lata metálica de munición clase M2A1 («large», .50: 298 × 152 × 191 mm) o M19A1 («small», 7,62: 277 × 99 × 178 mm),
    genérica. Cuerpo de lámina de 1 mm con esquinas de radio 10 mm, costura reforzada en el canto inferior y fondo hundido,
    costados largos con panel embutido; tapa embutida que abraza el cuerpo (faldón con dobladillo rolado, panel realzado),
    empaque de hule en su canal (visible abierta); bisagra de dos tubos rolados en el cuerpo y nudillo central de la tapa con
    pasador de cabezas remachadas (extremo -X); cierre de leva (extremo +X): palanca de fleje de muelle pivotada en dos
    orejas soldadas al cuerpo, con gancho que abraza el lazo de alambre de la tapa; asa de fleje en U plegada sobre dos lazos
    de alambre; estarcidos amarillos con tipografía de plantilla. open=True: tapa a 105° sobre la bisagra, palanca soltada,
    cuerpo con espesor y una cinta eslabonada (.50 en la grande, 7,62 en la chica) en dos capas.
    Origen: centro de la base (z = 0 apoyo); largo en X (bisagra en -X, palanca en +X), costado con estarcido hacia -Y.
    Fuentes: alloutdoor.com/?p=475777 (construcción: cuerpo de lámina embutida soldada, empaque integral, cierre de palanca,
    bisagra de pasadores, asa en lazos de alambre rectangulares); bulkammo.com/m19a1-30-cal-m2a1-50-cal-ammo-cans-green-
    brand-new-2 y skycraftsurplus.com/products/metal-ammo-can-m19a1-30-cal.html (medidas exteriores); ima-usa.com/products/
    original-u-s-wwii-model-m2-browning-50-cal-ammunition-can (tubos rolados de bisagra en el cuerpo, pasadores en la tapa,
    lazo de alambre en la tapa enganchado por la palanca)."""
    key = ("can", size, bool(open), int(seed) % 3)
    return _fresh(_cached(key, lambda: _ammo_can(size, int(seed) % 3, bool(open))))


def _ammo_can(size, seed, open_):
    r = rng(seed + 11)
    mb = MB()
    L, W, H = _can_dims(size)
    big = size == "large"
    lid_h = 0.044 if big else 0.040
    Lb, Wb = L - 0.008, W - 0.006
    rc, rcl = 0.010, 0.014
    zl0 = H - lid_h
    zb = H - 0.0025 - 0.0035 - 0.0045                 # boca del cuerpo: entra al empaque de la tapa
    _can_body(mb, Lb, Wb, rc, zl0, zb, open_)
    lid = MB()
    zi = _can_lid(lid, L, W, H, zl0, rcl)
    if open_:                                          # empaque de hule en el canal de la tapa + pared interior del canal
        sect = [(0.003 * math.cos(a) * 1.05, zi - 0.0026 + 0.0026 * math.sin(a)) for a in [2 * PI * k / 12 for k in range(12)]]
        _ring_band(lid, Matrix(), Lb, Wb, rc, sect, "rubber", nc=6)
        _ring_band(lid, Matrix(), Lb, Wb, rc, [(-0.0036, zi + 0.0004), (-0.0044, zi + 0.0004), (-0.0044, zi - 0.0068),
                                               (-0.0036, zi - 0.0072)], "paint_od", nc=6)
    # ---- asa abatible sobre la tapa
    _can_handle(lid, 0.0, -0.016 if big else -0.013, H, 0.068 if big else 0.060, big)
    # ---- bisagra (extremo -X): dos tubos rolados del cuerpo, nudillo central de la tapa, pasador
    yk, wk = (0.034, 0.022) if big else (0.025, 0.018)
    xh, zh = -L / 2 - 0.0016, zl0 - 0.0058
    Mend = _basis((-Lb / 2, 0, 0), (0, 0, 1), (0, 1, 0), (-1, 0, 0))     # plano del extremo -X del cuerpo (u = z, v = y)
    tabs = [(zh - 0.030, -yk - wk / 2), (zh - 0.030, yk + wk / 2), (zh, yk + wk / 2), (zh, yk - wk / 2), (zh - 0.006, yk - wk / 2 - 0.004),
            (zh - 0.006, -yk + wk / 2 + 0.004), (zh, -yk + wk / 2), (zh, -yk - wk / 2)]
    plan(mb, tabs, [0.004, 0.004, 0.0, 0.0, 0.002, 0.002, 0.0, 0.0], 0.0019, "paint_od", z0=-0.0003, re=0.0006, n=3, ne=1, M=Mend)
    for sy in (-1, 1):
        revolve(mb, [(0.0027, -wk / 2), (0.0038, -wk / 2), (0.0042, -wk / 2 + 0.0005), (0.0042, wk / 2 - 0.0005), (0.0038, wk / 2),
                     (0.0027, wk / 2)], "paint_od", seg=SEG, M=_T(xh, sy * yk, zh) @ _Rx(90), closed=True)
    wl = 2 * (yk - wk / 2) - 0.0026
    Mle = _basis((-L / 2, 0, 0), (0, 0, 1), (0, 1, 0), (-1, 0, 0))
    plan(lid, [(zh, -wl / 2), (zl0 + 0.016, -wl / 2 + 0.002), (zl0 + 0.016, wl / 2 - 0.002), (zh, wl / 2)],
         [0.0, 0.003, 0.003, 0.0], 0.0019, "paint_od", z0=-0.0003, re=0.0006, n=3, ne=1, M=Mle)
    revolve(lid, [(0.0026, -wl / 2), (0.0038, -wl / 2), (0.0042, -wl / 2 + 0.0005), (0.0042, wl / 2 - 0.0005), (0.0038, wl / 2),
                  (0.0026, wl / 2)], "paint_od", seg=SEG, M=_T(xh, 0, zh) @ _Rx(90), closed=True)
    hl = yk + wk / 2 + 0.0012
    with mb.soft():
        revolve(mb, [(0.0, -hl - 0.0009), (0.0022, -hl - 0.0008), (0.0034, -hl - 0.0002), (0.0034, -hl), (0.0028, -hl),
                     (0.0028, hl), (0.0034, hl), (0.0034, hl + 0.0002), (0.0022, hl + 0.0008), (0.0, hl + 0.0009)], "steel",
                seg=SEG_W, M=_T(xh, 0, zh) @ _Rx(-90))
    # ---- cierre (extremo +X): lazo de alambre en la tapa, orejas y pasador en el cuerpo, palanca de leva
    zw = zl0 + 0.0085
    wire(lid, [(L / 2 - 0.0006, -0.0135, zw), (L / 2 + 0.0060, -0.0135, zw), (L / 2 + 0.0060, 0.0135, zw), (L / 2 - 0.0006, 0.0135, zw)],
         0.0021, "paint_od", bend=0.003, nseg=4)
    xc = L / 2 + 0.0060
    rr = 0.0021 + 0.0011 + 0.0002
    xo = xc + rr
    xp, zp = xo - 0.0035, zl0 - 0.012
    lw = 0.034 if big else 0.030
    Mbe = _basis((Lb / 2, 0, 0), (0, 0, 1), (0, -1, 0), (1, 0, 0))
    plan(mb, [(zp - 0.016, -lw / 2 - 0.004), (zp + 0.009, -lw / 2 - 0.004), (zp + 0.009, lw / 2 + 0.004), (zp - 0.016, lw / 2 + 0.004)],
         0.004, 0.0019, "paint_od", z0=-0.0003, re=0.0006, n=3, ne=1, M=Mbe)
    for sy in (-1, 1):
        side(mb, [(Lb / 2, zp - 0.013), (xp + 0.0005, zp - 0.0058), (xp + 0.0058, zp), (xp, zp + 0.0058), (Lb / 2, zp + 0.007)],
             [0.0, 0.004, 0.0035, 0.004, 0.0], 0.0018, "paint_od", y0=sy * (lw / 2 + 0.0019), re=0.0005, n=3, ne=1)
    with mb.soft():
        hp = lw / 2 + 0.0034
        revolve(mb, [(0.0, -hp - 0.0008), (0.0026, -hp - 0.0006), (0.0031, -hp), (0.0025, -hp), (0.0025, hp), (0.0031, hp),
                     (0.0026, hp + 0.0006), (0.0, hp + 0.0008)], "steel", seg=SEG_W, M=_T(xp, 0, zp) @ _Rx(-90))
    lev = MB()
    arc = [(xc + rr * math.cos(a), 0.0, zw + rr * math.sin(a)) for a in [PI * 0.92 * k / 10 for k in range(11)]]
    tail = [(xo + 0.0045 - 0.0045 * (k / 6) ** 1.5 * 0.35, 0.0, zp - 0.054 + 0.006 * k / 6) for k in range(6)]
    path = fillet([(xo + 0.003, 0.0, zp - 0.048), (xo + 0.0005, 0.0, zp - 0.042), (xo, 0.0, zp - 0.02), (xo, 0.0, zw)], 0.006, 4)
    path = tail + path[1:-1] + arc
    acc = [0.0]
    for a_, b_ in zip(path[:-1], path[1:]):
        acc.append(acc[-1] + (Vector(b_) - Vector(a_)).length)
    tot = acc[-1]
    e0 = 0.0055 / tot

    def sc(s):                                         # extremo de la cola redondeado en planta (radio ~ 5 mm)
        return (1.0, 0.72 + 0.28 * math.sqrt(max(1 - ((e0 - s) / e0) ** 2, 0.0))) if s < e0 else (1.0, 1.0)
    sweep_frame(lev, rr_profile(0.0022, lw, 0.001, n=4), path, "paint_od", up=(0, 1, 0), scale=sc)
    revolve(lev, [(0.0023, -lw / 2 + 0.001), (0.0038, -lw / 2 + 0.001), (0.0042, -lw / 2 + 0.0015), (0.0042, lw / 2 - 0.0015),
                  (0.0038, lw / 2 - 0.001), (0.0023, lw / 2 - 0.001)], "paint_od", seg=SEG, M=_T(xp, 0, zp) @ _Rx(90), closed=True)
    side(lev, [(xp, zp - 0.003), (xo - 0.0004, zp - 0.012), (xo - 0.0004, zp + 0.004), (xp, zp + 0.003)], [0.0, 0.0, 0.0, 0.0],
         lw - 0.004, "paint_od", re=0.0005, n=2, ne=1)
    if open_:
        lev.transform(_T(xp, 0, zp) @ _Ry(-15) @ _T(-xp, 0, -zp))
    mb.join(lev)
    if open_:
        lid.transform(_T(xh, 0, zh) @ _Ry(-105) @ _T(-xh, 0, -zh))
    mb.join(lid)
    # ---- estarcidos (costado -Y, dentro del panel embutido)
    yf = -Wb / 2 + 0.0012
    zc = (0.026 + zl0 - 0.016) / 2
    Mf = _T(0, yf, 0) @ _Rx(90)
    stencil(mb, "AMMO", 0.032 if big else 0.026, Mf @ _T(0, zc + 0.020, 0), "paint_yellow")
    stencil(mb, "CAL .50 LINKED" if big else "7.62MM LINKED", 0.0105 if big else 0.0085, Mf @ _T(0, zc - 0.006, 0), "paint_yellow",
            font="stencil2")
    lot = ("LOT 27-05", "LOT 22-09", "LOT 31-02")[int(r.integers(0, 3))]
    stencil(mb, lot, 0.0105 if big else 0.0085, Mf @ _T(0, zc - 0.024, 0), "paint_yellow", font="stencil2")
    if open_:                                          # cinta eslabonada en capas, de culote a -Y
        cal = "50" if big else "762"
        c = CAL[cal]
        n = int((Lb - 0.004 - 2 * c["rim"]) / c["pitch"]) + 1
        x0 = -(n - 1) * c["pitch"] / 2
        y0 = -c["oal"] / 2 - 0.0005
        zc1 = zb - 0.020 - c["base"]
        belt_layer(mb, _T(x0, y0, zc1), n, cal)
        zc2 = zc1 - 2 * c["base"] + 0.0004
        belt_layer(mb, _T(x0, y0 + 0.0015, zc2), n, cal, links=False, lite=True, seg=16)
        # separador de cartón bajo la cinta (asienta en el piso)
        _slab(mb, _T(0, 0, 0.0047), Lb - 0.0050, Wb - 0.0050, zc2 - c["base"] + 0.0004 - 0.0047, rc=0.008, re=0.0015, mat="cardboard",
              nc=3, ne=2)
    return mb


# ======================================================================================================== caja de cartón
def cardboard_ammo_box(seed=0):
    """Caja plegadiza de cartón de 20 cartuchos de fusil (~ 112 × 72 × 45 mm, «reverse tuck end»): tubo de cartulina de
    0,6 mm con dobleces redondos (radio 1,2 mm), paneles levemente abombados, extremos cerrados con su solapa de meter
    (doblez redondo arriba en un extremo y abajo en el otro, holgura de 0,4 mm alrededor) y las aletas de polvo detrás,
    tira de sello de papel con espesor sobre un extremo, impresión en tinta oscura. Origen: centro de la base; largo en X.
    Fuente de proporción: cajas de 20 cartuchos de 5,56 mm (~ 4,4 × 2,8 × 1,8 in; listados de ar15discounts.com y
    planooutdoors.com)."""
    key = ("cbox", int(seed) % 4)
    return _fresh(_cached(key, lambda: _cbox(int(seed) % 4)))


def _cbox(seed):
    r = rng(seed + 5)
    mb = MB()
    L = 0.112 * (1.0 + float(r.uniform(-0.015, 0.015)))
    W, H, t, rk = 0.072, 0.045, 0.0006, 0.0012
    b = float(r.uniform(0.00035, 0.00055))
    nyp, nzp = 5, 3
    prof = []                                             # (y, z, ny, nz, u del panel o None)
    cs = [(W / 2 - rk, H - rk, 0.0), (-W / 2 + rk, H - rk, PI / 2), (-W / 2 + rk, rk, PI), (W / 2 - rk, rk, 1.5 * PI)]
    for ci, (cy, cz, a0) in enumerate(cs):
        for k in range(5):
            an = a0 + PI / 2 * k / 4
            prof.append((cy + rk * math.cos(an), cz + rk * math.sin(an), math.cos(an), math.sin(an), None))
        n_ = nyp if ci in (0, 2) else nzp
        for j in range(n_):
            u = 1 - 2 * (j + 1) / (n_ + 1)
            if ci == 0:
                prof.append((u * (W / 2 - rk), H, 0.0, 1.0, u))
            elif ci == 1:
                prof.append((-W / 2, H / 2 + u * (H / 2 - rk), -1.0, 0.0, u))
            elif ci == 2:
                prof.append((-u * (W / 2 - rk), 0.0, 0.0, -1.0, u))
            else:
                prof.append((W / 2, H / 2 - u * (H / 2 - rk), 1.0, 0.0, u))
    xs = [-L / 2, -L / 2 + 0.0015] + [-L / 2 + 0.0015 + (L - 0.003) * k / 7 for k in range(1, 7)] + [L / 2 - 0.0015, L / 2]

    def ring(x, off):
        v = 2 * x / L
        out = []
        for (y, z, ny, nz, u) in prof:
            o = off + (b * (1 - u * u) * (1 - v * v) if u is not None else 0.0)
            if nz < -0.5:
                o = off                                   # el fondo apoya plano
            out.append((x, y + ny * o, z + nz * o))
        return out
    loops = [ring(x, 0.0) for x in xs] + [ring(x, -t) for x in reversed(xs)]
    skin(mb, loops, "cardboard", closed=True)
    # extremos: solapa de meter (doblez arriba en +X, abajo en -X), aletas de polvo detrás
    gap = 0.0004
    fw, fh = W - 2 * t - 2 * gap, H - 2 * t - 2 * gap
    for sx in (-1, 1):
        x0 = sx * (L / 2 - 0.0005)
        Mf = _T(x0, 0, H / 2) @ _Ry(90 * sx)              # +Z local hacia afuera del extremo
        _slab(mb, Mf @ _T(0, 0, -t), fh, fw, t, rc=0.0008, re=t * 0.45, re0=t * 0.45, mat="cardboard", nc=3, ne=1)
        _slab(mb, Mf @ _T(0, 0, -0.0045), H - 2 * t + 0.0003, W - 2 * t + 0.0003, t, rc=0.0008, re=0.0, re0=0.0, mat="cardboard",
              nc=2, ne=1)
        zf = H - t - gap if sx > 0 else t + gap           # doblez redondo de la solapa contra el panel (arriba / abajo)
        with mb.soft():
            revolve(mb, [(0.0, -fw / 2), (0.00085, -fw / 2 + 0.0003), (0.00085, fw / 2 - 0.0003), (0.0, fw / 2)], "cardboard",
                    seg=SEG_W, M=_T(x0 - sx * 0.0004, 0, zf - (0.0002 if sx > 0 else -0.0002)) @ _Rx(90))
    # tira de sello de papel (0,25 mm) que cruza el extremo +X de la tapa al fondo
    sw, ot = 0.016, 0.00035
    path = [(L / 2 - 0.022, 0.0, H + b * 0.2 + ot)] + \
        [(L / 2 + ot - 0.0012 + (0.0012 + ot) * math.cos(a), 0.0, H - 0.0012 + (0.0012 + ot) * math.sin(a))
         for a in [PI / 2 - PI / 2 * k / 4 for k in range(5)]] + \
        [(L / 2 + ot - 0.0012 + (0.0012 + ot) * math.cos(a), 0.0, 0.0012 + (0.0012 + ot) * math.sin(a))
         for a in [-PI / 2 * k / 4 for k in range(5)]] + [(L / 2 - 0.018, 0.0, -ot)]
    sweep_frame(mb, rr_profile(0.00042, sw, 0.00018, n=1), path, "sign_white", up=(0, 1, 0))
    # impresión (tinta oscura) en la tapa y el frente
    zt = H + b * 0.75
    stencil(mb, "20 CARTRIDGES", 0.0072, _T(-0.004, 0.009, zt), "cable", depth=0.0008, font="sign", sink=0.0005)
    stencil(mb, "5.56MM BALL", 0.0066, _T(-0.004, -0.004, zt), "cable", depth=0.0008, font="sign", sink=0.0005)
    stencil(mb, ("LOT 22-09", "LOT 27-05", "LOT 31-02", "LOT 26-11")[seed % 4], 0.0048, _T(-0.004, -0.015, zt), "cable",
            depth=0.0006, font="stencil2", sink=0.0005)
    stencil(mb, "20 CTG", 0.009, _T(0.0, -W / 2 - 0.00022, H / 2) @ _Rx(90), "cable", depth=0.0006, font="sign")
    return mb


# ======================================================================================================== cajas de madera
def _knuckle(mb, M, a, b, ro=0.0042, ri=0.0013, mat="steel"):
    """Nudillo de bisagra (lámina enrollada, Ø <= 9 mm: 16 lados) a lo largo del eje Z de M, de z = a a z = b."""
    if _lo():
        with mb.soft():
            revolve(mb, [(ri, a), (ro, a), (ro, b), (ri, b)], mat, seg=8, M=M, closed=True)
        return
    revolve(mb, [(ri, a), (ro - 0.0005, a), (ro, a + 0.0005), (ro, b - 0.0005), (ro - 0.0005, b), (ri, b)], mat, seg=16, M=M, closed=True)


def _pin(mb, M, a, b, r=0.0016, rh=0.0027):
    """Pasador con cabezas remachadas (abombadas) a lo largo del eje Z de M (la versión ligera lo omite: lo tapan los nudillos)."""
    if _lo():
        return
    with mb.soft():
        revolve(mb, [(0.0, a - 0.0016), (rh * 0.7, a - 0.0014), (rh, a - 0.0005), (rh, a), (r, a), (r, b), (rh, b), (rh, b + 0.0005),
                     (rh * 0.7, b + 0.0014), (0.0, b + 0.0016)], "steel", seg=SEG_W, M=M)


def _crate_hinge(body, lid, x, D, zt, tb):
    """Bisagra de fleje en la espalda (+Y): hoja del cuerpo sobre la tabla trasera, hoja de la tapa en L (canto trasero y
    cara superior), tres nudillos alternados, pasador remachado y remaches de cabeza de gota."""
    ya, za = D / 2 + 0.0042, zt
    Mb = _basis((x, D / 2, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0))
    lo = _lo()
    plan(body, [(-0.0157, za - 0.0012), (-0.0157, za - 0.074), (-0.009, za - 0.094), (0.009, za - 0.094), (0.0157, za - 0.074),
                (0.0157, za - 0.0012)], [0.0, 0.004, 0.007, 0.007, 0.004, 0.0], 0.002, "steel", z0=-0.0004, re=0.0 if lo else 0.0007,
         n=1 if lo else 3, ne=1, M=Mb)
    for z in (za - 0.022, za - 0.050, za - 0.078):
        rivet(body, Mb @ _T(0, z, 0.0016))
    for (a, b) in (((-0.0150, 0.0150),) if lo else ((-0.016, -0.0056), (0.0056, 0.016))):
        _knuckle(body, _T(x, ya, za) @ _Ry(90), a, b)
    yl = D / 2 + 0.0004
    path = fillet([(x, yl, za + 0.0035), (x, yl, zt + tb + 0.0004), (x, D / 2 - 0.090, zt + tb + 0.0004)], 0.003, 4)
    path = [(x, yl, za + 0.0005)] + path
    acc = [0.0]
    for a_, b_ in zip(path[:-1], path[1:]):
        acc.append(acc[-1] + (Vector(b_) - Vector(a_)).length)
    tot = acc[-1]
    e0 = 0.012 / tot

    def sc(s):
        return (1.0, 0.55 + 0.45 * math.sqrt(max(1 - ((s - (1 - e0)) / e0) ** 2, 0.0))) if s > 1 - e0 else (1.0, 1.0)
    if lo:
        path = [(x, yl, za + 0.0005)] + fillet([(x, yl, za + 0.0035), (x, yl, zt + tb + 0.0004), (x, D / 2 - 0.090, zt + tb + 0.0004)],
                                              0.003, 2)
        sweep_frame(lid, [(0.001, 0.0157), (-0.001, 0.0157), (-0.001, -0.0157), (0.001, -0.0157)], path, "steel", up=(1, 0, 0))
    else:
        pts = []
        for a_, b_ in zip(path[:-1], path[1:]):                 # remuestreo para que el extremo redondo tenga anillos
            n = max(1, int(math.ceil((Vector(b_) - Vector(a_)).length / 0.006)))
            pts += [tuple(Vector(a_).lerp(Vector(b_), k / n)) for k in range(n)]
        pts.append(path[-1])
        sweep_frame(lid, rr_profile(0.002, 0.0314, 0.0008, n=2), pts, "steel", up=(1, 0, 0), scale=sc)
    if not lo:
        _knuckle(lid, _T(x, ya, za) @ _Ry(90), -0.0048, 0.0048)
    for y in (D / 2 - 0.022, D / 2 - 0.047, D / 2 - 0.072):
        rivet(lid, _T(x, y, zt + tb + 0.0018))
    _pin(body, _T(x, ya, za) @ _Ry(90), -0.0157, 0.0157)


def _crate_hasp(body, lid, x, D, zt, tb, seal=True, seed=0):
    """Portacandado al frente (-Y): placa con nudillos en el canto de la tapa, hebilla ranurada que cuelga sobre la grapa
    (lazo de varilla de 6 mm en su placa remachada al cuerpo) y sello de alambre con su plomo."""
    r = rng(seed)
    lo = _lo()
    seal = seal and not lo
    pn, pre = (1, 0.0) if lo else (3, 0.0007)
    yk, zk = -D / 2 - 0.0045, zt + 0.0015
    Mf = _basis((x, -D / 2, 0), (1, 0, 0), (0, 0, 1), (0, -1, 0))                 # cara frontal: u = x, v = z, +Z = -Y
    plan(lid, [(-0.017, zk), (-0.017, zt + tb - 0.003), (0.017, zt + tb - 0.003), (0.017, zk)], [0.0, 0.003, 0.003, 0.0], 0.002,
         "steel", z0=-0.0004, re=pre, n=pn, ne=1, M=Mf)
    for u in (-0.010, 0.010):
        rivet(lid, Mf @ _T(u, zt + tb * 0.62, 0.0016), d=0.006)
    for (a, b) in (((-0.0155, 0.0155),) if lo else ((-0.017, -0.0062), (0.0062, 0.017))):
        _knuckle(lid, _T(x, yk, zk) @ _Ry(90), a, b, ro=0.0036)
    hl = 0.074
    zc = zk - 0.0036 - hl / 2 + 0.002
    zs = zc - 0.016                                           # centro de la ranura
    hasp = MB()
    holed_slab(hasp, _basis((x, -D / 2 - 0.0022, zc), (1, 0, 0), (0, 0, 1), (0, -1, 0)), 0.030, hl, 0.002,
               holes=[(0.0, zs - zc, 0.0046, 0.0118, 5.0)], ch=0.0 if lo else 0.0007, rc=0.005, nc=3, mat="steel", n=8 if lo else 24,
               chh=0.0005, ne=1)
    if not lo:
        _knuckle(hasp, _T(x, yk, zk) @ _Ry(90), -0.0058, 0.0058, ro=0.0036)
    _pin(hasp, _T(x, yk, zk) @ _Ry(90), -0.0166, 0.0166, r=0.0015, rh=0.0024)
    lid.join(hasp)
    # grapa del cuerpo
    plan(body, [(-0.014, zs - 0.024), (0.014, zs - 0.024), (0.014, zs + 0.020), (-0.014, zs + 0.020)], 0.004, 0.0019, "steel",
         z0=-0.0004, re=0.0 if lo else 0.0006, n=pn, ne=1, M=Mf)
    for v in (zs - 0.018, zs + 0.014):
        rivet(body, Mf @ _T(0, v, 0.0015), d=0.006)
    ys = -D / 2 - 0.0145
    wire(body, [(x, -D / 2 - 0.0008, zs - 0.0066), (x, ys, zs - 0.0066), (x, ys, zs + 0.0066), (x, -D / 2 - 0.0008, zs + 0.0066)],
         0.0029, "steel", bend=0.0035, nseg=4)
    if seal:                                                  # sello: lazo de alambre por la grapa y plomo colgando
        ry, rl = ys, 0.0034                               # lazo apretado alrededor de la barra de la grapa
        lp = [(x + rl * math.cos(a), ry + rl * math.sin(a), zs + 0.0002) for a in [2 * PI * k / 14 for k in range(14)]]
        lp = lp + [lp[0]]
        wire(body, lp, 0.0006, "steel", bend=0.0, caps=False)
        sw = float(r.uniform(-0.004, 0.004))
        wire(body, [(x - rl, ry, zs + 0.0002), (x - 0.003 + sw * 0.3, ry - 0.0012, zs - 0.012), (x + sw, ry - 0.0016, zs - 0.0245)],
             0.0006, "steel", bend=0.004)
        wire(body, [(x + rl, ry, zs + 0.0002), (x + 0.003 + sw * 0.3, ry - 0.0010, zs - 0.012), (x + sw, ry - 0.0016, zs - 0.0245)],
             0.0006, "steel", bend=0.004)
        revolve(body, [(0.0, -0.0013), (0.0045, -0.0013), (0.0056, -0.0006), (0.0056, 0.0006), (0.0045, 0.0013), (0.0, 0.0013)],
                "aluminium", seg=16, M=_T(x + sw, ry - 0.0016, zs - 0.0296) @ _Rx(90))


def _crate_band(mb, x, D, zb, ztop, seed=0, w=0.016, t=0.0007):
    """Fleje de acero que ciñe la caja en el plano YZ (bajo el fondo, frente, tapa y espalda), con su sello engargolado sobre
    la tapa y dos grapas de alambre clavadas a horcajadas en frente y espalda."""
    r = rng(seed)
    o = 0.0004 + t / 2
    rf = 0.004
    if _lo():                                                # sin grapas ni sello: el fleje se hunde medio espesor en la madera
        t, o, rf = 0.001, 0.0, 0.0028                        # y dobla con el radio del canto de la tabla
    yo, za, zb_ = D / 2 + o, zb - o, ztop + o
    path = fillet([(x, -yo, za), (x, yo, za), (x, yo, zb_), (x, -yo, zb_)], rf, 2 if _lo() else 4)
    band(mb, path, w=w, t=t, normal=(1, 0, 0))
    ys = float(r.uniform(-D * 0.25, D * 0.25))
    band_seal(mb, _T(x, ys, zb_ + t / 2 - 0.0002) @ _Rz(90), w=w)
    for sy in (() if _lo() else (-1, 1)):                  # grapas de alambre de 2,2 mm: fuera en la versión ligera
        zz = zb + (ztop - zb) * float(r.uniform(0.35, 0.65))
        yy = sy * (yo + t / 2 + 0.0011)
        wire(mb, [(x - w / 2 - 0.0025, sy * (D / 2 - 0.004), zz), (x - w / 2 - 0.0025, yy, zz), (x + w / 2 + 0.0025, yy, zz),
                  (x + w / 2 + 0.0025, sy * (D / 2 - 0.004), zz)], 0.0011, "galvanized", bend=0.0018, nseg=3)


def _rope_end(mb, L, D, H, zc, rs):
    """Extremo +X con asa de cuerda: travesaño macizo de 34 × 72 mm con dos barrenos verticales, cuerda torcida de 12,4 mm
    que sube por los barrenos con un nudo de tope encima de cada uno y cuelga en U bajo el travesaño."""
    dep, hc = 0.034, 0.072
    Dc = D + 2 * 0.019 - 0.004
    xm = L / 2 + dep / 2
    z0c = zc - hc / 2
    lo = _lo()
    holed_slab(mb, _T(xm, 0, z0c) @ _Rz(90), Dc, dep, hc, holes=[(-0.05, 0.0, 0.0060, 0.0060, 2), (0.05, 0.0, 0.0060, 0.0060, 2)],
               ch=0.003, rc=0.004, nc=3, mat=WOOD, n=8 if lo else 16, chh=0.0022)
    for y in ((-Dc / 2 + 0.03, Dc / 2 - 0.03) if lo else (-Dc / 2 + 0.03, 0.0, Dc / 2 - 0.03)):
        nail(mb, _T(L / 2 + dep, y, zc + float(rs.uniform(-0.012, 0.012))) @ _Ry(90))
    xr = xm + 0.0008
    zt_ = z0c + hc
    sag = float(rs.uniform(0.046, 0.056))
    lp = [(xr, -0.05, z0c + 0.012), (xr, -0.05, z0c - 0.006), (xr + 0.0015, -0.046, z0c - 0.026),
          (xr + 0.003, -0.030, z0c - sag + 0.006), (xr + 0.0035, 0.0, z0c - sag), (xr + 0.003, 0.030, z0c - sag + 0.006),
          (xr + 0.0015, 0.046, z0c - 0.026), (xr, 0.05, z0c - 0.006), (xr, 0.05, z0c + 0.012)]
    rope(mb, lp, r=0.0062, pitch=0.030, seg=12, per_turn=6, phase=float(rs.uniform(0, 6.28)), caps=True)
    for sy in (-1, 1):
        rope_knot(mb, _T(xr, sy * 0.05, zt_ + 0.0085) @ _Rz(float(rs.uniform(0, 360))), phase=float(rs.uniform(0, 6)))
        a = float(rs.uniform(-0.6, 0.6))
        if lo:
            continue
        rope(mb, [(xr, sy * 0.05, zt_ + 0.012), (xr + 0.004 * math.cos(a), sy * (0.05 + 0.012), zt_ + 0.011),
                  (xr + 0.008 * math.cos(a), sy * (0.05 + 0.026), zt_ + 0.0075)], r=0.0058, pitch=0.030, seg=12, caps=True)


def _bail_end(mb, L, D, H, zc, tb, rs):
    """Extremo +X con asa abatible: travesaño de tabla y asa de varilla de 10 mm en U colgando de dos ojos de lámina
    remachados (orejas) al travesaño."""
    tc = tb
    Dc = D + 2 * tb - 0.004
    wplank(mb, (L / 2 - 0.0005, -Dc / 2, zc - 0.045), (L / 2 + tc, Dc / 2, zc + 0.045), rs=rs)
    xf = L / 2 + tc
    lo = _lo()
    for y in (-Dc / 2 + 0.025, Dc / 2 - 0.025):
        for z in ((zc,) if lo else (zc - 0.025, zc + 0.025)):
            nail(mb, _T(xf, y, z) @ _Ry(90))
    hw = 0.056
    ze = zc + 0.016
    xa = xf + 0.0095
    Me = _basis((xf, 0, 0), (0, 0, 1), (0, 1, 0), (1, 0, 0))
    for sy in (-1, 1):
        y = sy * hw
        plan(mb, [(ze - 0.032, y - 0.013), (ze + 0.008, y - 0.013), (ze + 0.008, y + 0.013), (ze - 0.032, y + 0.013)], 0.005, 0.0025,
             "steel", z0=-0.0004, re=0.0 if lo else 0.0008, n=1 if lo else 3, ne=1, M=Me)
        rivet(mb, Me @ _T(ze - 0.022, y, 0.002), d=0.0075)
        if lo:
            with mb.soft():
                revolve(mb, [(0.0075 + 0.0026 * math.cos(a), 0.0026 * math.sin(a) * 1.6) for a in [2 * PI * k / 6 for k in range(6)]],
                        "steel", seg=10, M=_T(xa, y, ze) @ _Rx(90), closed=True)
        else:
            revolve(mb, [(0.0075 + 0.0026 * math.cos(a), 0.0026 * math.sin(a) * 1.6) for a in [2 * PI * k / 10 for k in range(10)]],
                    "steel", seg=SEG, M=_T(xa, y, ze) @ _Rx(90), closed=True)
        side(mb, [(xf + 0.0010, ze - 0.012), (xa - 0.004, ze - 0.010), (xa - 0.004, ze - 0.004), (xf + 0.0010, ze - 0.002)],
             [0.0, 0.002, 0.002, 0.0], 0.006, "steel", y0=y, re=0.0 if lo else 0.0006, n=1 if lo else 2, ne=1)
    a = math.radians(float(rs.uniform(5, 11)))
    dz, dx = 0.062 * math.cos(a), 0.062 * math.sin(a)
    pth = [(xa, -hw + 0.013, ze), (xa, -hw - 0.009, ze), (xa + dx, -hw - 0.009, ze - dz), (xa + dx, hw + 0.009, ze - dz),
           (xa, hw + 0.009, ze), (xa, hw - 0.013, ze)]
    wire(mb, pth, 0.005, "steel", bend=0.011, nseg=6)


def _crate(L, D, H, kind, seed=0, open=False, stencils=True, contents=True, bands=None):
    """Caja de munición de madera (ver ammo_crate); respeta el nivel de detalle activo (_at_lod)."""
    rs = rng(seed * 7 + 3)
    lo = _lo()
    body, lid = MB(), MB()
    tb = 0.016 if kind == "small" else 0.019
    z0 = 0.022
    zt = H - 2 * tb
    g = 0.0015
    nb = 2 if (zt - z0) < 0.26 else 3
    bh = ((zt - z0) - (nb - 1) * g) / nb
    if kind == "wood":
        xh, xb, nbat = (-0.10, 0.10), 0.165, 2
    elif kind == "long":
        xh, xb, nbat = (-0.52, 0.52), 0.36, 3
    else:
        xh, xb, nbat = (-0.06, 0.06), 0.115, 2
    xhasp = xh if kind != "small" else (0.0,)
    # ---- costados largos (frente -Y y espalda +Y), extremos, fondo, patines
    for sy in (-1, 1):
        y0, y1 = (-D / 2, -D / 2 + tb) if sy < 0 else (D / 2 - tb, D / 2)
        for k in range(nb):
            za = z0 + k * (bh + g)
            wplank(body, (-L / 2, y0, za), (L / 2, y1, za + bh), rs=rs)
    for sx in (-1, 1):
        x0, x1 = (-L / 2, -L / 2 + tb) if sx < 0 else (L / 2 - tb, L / 2)
        for k in range(nb):
            za = z0 + k * (bh + g)
            wplank(body, (x0, -D / 2 + tb + 0.0004, za), (x1, D / 2 - tb - 0.0004, za + bh), rs=rs)
    nbt = 3 if D - 2 * tb > 0.25 else 2
    bw = (D - 2 * tb - 0.001 - (nbt - 1) * g) / nbt
    for k in range(nbt):
        ya = -D / 2 + tb + 0.0005 + k * (bw + g)
        wplank(body, (-L / 2 + tb + 0.0004, ya, z0), (L / 2 - tb - 0.0004, ya + bw, z0 + tb), rs=rs, hidden=not open)
    nr = 3 if L > 1.0 else 2
    for i in range(nr):
        x = -L / 2 + 0.07 + (L - 0.14) * i / (nr - 1) - 0.035
        wplank(body, (x, -D / 2 + 0.002, 0.0), (x + 0.07, D / 2 - 0.002, z0 + 0.0010), rs=rs, hidden=True)
    # ---- postes de esquina sobre los costados largos, con clavos
    for sx in (-1, 1):
        for sy in (-1, 1):
            xa, xb_ = sorted((sx * (L / 2 - 0.058), sx * L / 2))
            ya, yb = sorted((sy * (D / 2 - 0.0012), sy * (D / 2 + tb)))
            wplank(body, (xa, ya, z0 + 0.002), (xb_, yb, zt - 0.001), rs=rs)
            for z in ((z0 + 0.03, zt - 0.03) if lo else (z0 + 0.03, (z0 + zt) / 2, zt - 0.03)):
                nail(body, _T((xa + xb_) / 2 + float(rs.uniform(-0.004, 0.004)), sy * (D / 2 + tb), z) @ _Rx(-90 * sy))
    # ---- extremos: travesaño con asa (se arma el extremo +X y se gira 180° para el -X)
    zc = z0 + (zt - z0) * 0.58
    for sx in (1, -1):
        end = MB()
        if kind == "wood":
            _rope_end(end, L, D, H, zc, rs)
        else:
            _bail_end(end, L, D, H, zc, tb, rs)
        body.join(end, Matrix() if sx > 0 else _Rz(180))
    # ---- tapa: tablas a lo largo de X y listones transversales clavados
    nl = 3
    lw = (D - (nl - 1) * g) / nl
    for k in range(nl):
        ya = -D / 2 + k * (lw + g)
        wplank(lid, (-L / 2, ya, zt), (L / 2, ya + lw, zt + tb), rs=rs)
    for i in range(nbat):
        x = -L / 2 + 0.035 + (L - 0.07 - 0.06) * i / (nbat - 1)
        wplank(lid, (x, -D / 2 + 0.001, zt + tb - 0.0006), (x + 0.06, D / 2 - 0.001, H), rs=rs)
        for k in range(nl):
            yy = -D / 2 + k * (lw + g) + lw / 2
            for dx in ((0.030,) if lo else (0.018, 0.042)):
                nail(lid, _T(x + dx + float(rs.uniform(-0.003, 0.003)), yy + float(rs.uniform(-0.015, 0.015)), H))
    # ---- herrajes: bisagras atrás, portacandados al frente
    for x in xh:
        _crate_hinge(body, lid, x, D, zt, tb)
    for i, x in enumerate(xhasp):
        _crate_hasp(body, lid, x, D, zt, tb, seal=not open, seed=seed * 5 + i)
    if open:
        ya, za = D / 2 + 0.0042, zt
        lid.transform(_T(0, ya, za) @ _Rx(-102) @ _T(0, -ya, -za))
    body.join(lid)
    bands = (not open) if bands is None else bands
    if bands:
        for i, x in enumerate((-xb, xb)):
            _crate_band(body, x, D, z0, zt + tb, seed=seed * 3 + i)
    # ---- estarcidos (frente)
    if stencils:
        yf = -D / 2 - 0.0002
        Mf = _T(0, yf, 0) @ _Rx(90)
        h = 0.07 if kind == "long" else (0.055 if kind == "wood" else 0.045)
        lot = ("LOT 275", "LOT 229", "LOT 312", "LOT 926")[seed % 4]
        wt = ("WT 62 LB", "WT 58 LB", "WT 64 LB", "WT 60 LB")[seed % 4]
        if kind == "small":
            zl = z0 + bh / 2
            stencil(body, "AMMO", h, Mf @ _T(0, zl + 0.012, 0), depth=0.0007, sink=0.0009)
            stencil(body, lot, 0.013, Mf @ _T(0, zl - 0.026, 0), depth=0.0007, sink=0.0009, font="stencil2")
        else:
            zu, zl = z0 + bh * 1.5 + g, z0 + bh / 2
            stencil(body, "AMMO", h, Mf @ _T(0, zu, 0), depth=0.0007, sink=0.0009)
            stencil(body, lot, 0.016, Mf @ _T(0, zl + (0.0 if lo else 0.013), 0), depth=0.0007, sink=0.0009,
                    font="stencil" if lo else "stencil2")
            if not lo:
                stencil(body, wt, 0.016, Mf @ _T(0, zl - 0.013, 0), depth=0.0007, sink=0.0009, font="stencil2")
    if open and contents:
        zf = z0 + tb
        if kind == "long":                                   # cunas con fieltro para dos tubos (eje a z = 0,1285, y = ±0,085)
            zc_, R = 0.1285, 0.0525
            yw = D / 2 - tb - 0.002
            for x in (-0.30, 0.30):
                P = [(-yw, zf - 0.0005), (yw, zf - 0.0005), (yw, zc_ + 0.010)]
                P += [(0.085 + R * math.cos(-PI * k / 16), zc_ + R * math.sin(-PI * k / 16)) for k in range(17)]
                P += [(-0.085 + R * math.cos(-PI * k / 16), zc_ + R * math.sin(-PI * k / 16)) for k in range(17)]
                P += [(-yw, zc_ + 0.010)]
                Rr = [0.0, 0.0, 0.006] + [0.0] * 34 + [0.006]
                side(body, P, Rr, 0.05, WOOD, re=0.0025, n=3, ne=3, M=_T(x, 0, 0) @ _Rz(90))
                for yc in (-0.085, 0.085):
                    arc = [(x, yc + (R - 0.001) * math.cos(-PI * k / 16), zc_ + (R - 0.001) * math.sin(-PI * k / 16)) for k in range(1, 16)]
                    sweep_frame(body, rr_profile(0.0021, 0.046, 0.0009, n=2), arc, "fabric", up=(1, 0, 0))
        else:                                                # cajas de cartón de cartuchos
            nx_, ny_ = (3, 2) if kind == "wood" else (2, 2)
            for i in range(nx_):
                for j in range(ny_):
                    x = (i - (nx_ - 1) / 2) * 0.125
                    y = (j - (ny_ - 1) / 2) * 0.085
                    body.join(_cached(("cbox", (i + j + seed) % 4), lambda: _cbox((i + j + seed) % 4)),
                              _T(x, y, zf - 0.0004) @ _Rz(float(rs.uniform(-2.5, 2.5))))
    return body


def ammo_crate(kind="wood", seed=0, open=False, lod=0):
    """Caja de munición de madera pintada verde olivo (genérica). kind: «wood» 0,66 × 0,36 × 0,30 m (asas de cuerda),
    «long» 1,65 × 0,42 × 0,27 m (cohetes / armas, asas abatibles de varilla), «small» 0,46 × 0,30 × 0,24 m (asas
    abatibles). Construcción real: tablas individuales de 19 mm (16 mm en «small») con veta, cantos redondeados y gastados,
    juntas de 1,5 mm; postes de esquina clavados sobre los costados, extremos con travesaño de asa (macizo con barrenos y
    cuerda torcida de 3 cabos con nudos de tope, o tabla con asa de varilla en orejas remachadas), fondo de tablas sobre
    patines; tapa de 3 tablas con listones transversales clavados; 2 bisagras de fleje con nudillos y pasador remachado atrás;
    portacandados con hebilla ranurada, grapa y sello de alambre con plomo al frente; 2 flejes de acero con sello engargolado
    y grapas; estarcidos amarillos con tipografía de plantilla (AMMO, lote, peso). open=True: tapa a 102° sobre las
    bisagras, flejes y sellos retirados, con su contenido (cajas de cartón; cunas con fieltro para dos tubos en «long»).
    Origen: centro de la base (z = 0 bajo los patines); largo en X, frente (estarcidos, portacandados) hacia -Y.
    Fuentes: everyspec.com/MIL-SPECS/MIL-SPECS-MIL-S/MIL-S-23389B_14382 (familia de cajas de munición de madera);
    varusteleka.com (caja de 40 mm: asas de cuerda en travesaños, bisagras y broches de fleje); fleje de 5/8–3/4 in ×
    0,020–0,023 in con sello de 1–1,25 in (catálogos de fleje de acero para embalaje).
    lod=1 (racks del almacén, vistos a >= 1 m): misma silueta (tablas con holgura, postes, travesaños, asas, bisagras,
    broches, flejes) con cantos de 2 segmentos, sin veta ni golpes, cuerda de 9 lados, herrajes y clavos de 8 lados de
    sombreado continuo, sin sellos ni pasadores y solo AMMO + LOT: ~ 5–6 k triángulos."""
    L, D, H = CRATE_DIMS.get(kind, CRATE_DIMS["wood"])
    kind = kind if kind in CRATE_DIMS else "wood"
    lod = 1 if lod else 0
    key = ("crate", kind, int(seed) % 4, bool(open), lod)
    return _fresh(_cached(key, lambda: _at_lod(lod, _crate, L, D, H, kind, seed=int(seed) % 4, open=bool(open))))


# ======================================================================================================== tarimas
def pallet_gma(mb, M=None, mat=WOOD, seed=0, lod=0):
    """Tarima de largueros GMA de 48 × 40 in (1219 × 1016 × 135 mm) unida a `mb` (con la matriz M); devuelve la altura de
    la cubierta (0,135). 3 largueros de 38 × 100 mm a lo largo de X con dos muescas de 229 × 38 mm (entrada parcial a 4 vías,
    esquinas de radio 12 mm), 7 tablas superiores de 19 mm (las de orilla de 140 mm, las interiores de 89 mm) y 5 inferiores
    de 16 mm, todas con cantos redondeados y gastados, veta, holguras y anchos ligeramente desiguales; dos clavos de caña
    anillada por cruce de tabla y larguero (72 cabezas). Origen: centro en el piso.
    Fuentes: interlakemecalux.com/blog/gma-pallet ; racklify.com/encyclopedia/the-anatomy-of-the-gma-style-wooden-pallet
    (7 tablas arriba, 5 abajo, 3 largueros con muesca); nelsoncompany.com/pallet-spec-sheet (48 × 40 × 4,75 in).
    lod=1: tablas de cantos de 2 segmentos sin veta, largueros con canto de 1 segmento y clavos de 8 lados (~ 3 k)."""
    lod = 1 if lod else 0
    src = _cached(("gma", mat, int(seed) % 4, lod), lambda: _at_lod(lod, _gma, mat, int(seed) % 4))
    mb.join(src, M)
    return 0.135


def _gma(mat, seed):
    rs = rng(seed * 13 + 1)
    sub = MB()
    Lx, Ly = 1.219, 1.016
    tb, tt, hs = 0.016, 0.019, 0.100
    yst = (-Ly / 2 + 0.019, 0.0, Ly / 2 - 0.019)

    def j(a):
        return float(rs.uniform(-a, a))
    bx = []
    for k in range(5):                                       # tablas inferiores (cara vista hacia abajo)
        w = (0.14 if k in (0, 4) else 0.089) + j(0.003)
        x = (-Lx / 2 + w / 2) if k == 0 else ((Lx / 2 - w / 2) if k == 4 else -0.150 + 0.150 * (k - 1) + j(0.003))
        dy = j(0.003)
        wplank(sub, (x - w / 2, -Ly / 2 + dy, 0.0), (x + w / 2, Ly / 2 + dy, tb), mat, rs=rs, wear=0.0025)
        bx.append((x, w))
    for y in yst:                                            # largueros con muescas
        P = [(-Lx / 2, tb - 0.0005), (-0.43, tb - 0.0005), (-0.43, tb + 0.038), (-0.20, tb + 0.038), (-0.20, tb - 0.0005),
             (0.20, tb - 0.0005), (0.20, tb + 0.038), (0.43, tb + 0.038), (0.43, tb - 0.0005), (Lx / 2, tb - 0.0005),
             (Lx / 2, tb + hs + 0.0005), (-Lx / 2, tb + hs + 0.0005)]
        R = [0.0, 0.0, 0.012, 0.012, 0.0, 0.0, 0.012, 0.012, 0.0, 0.0, 0.0, 0.0]
        side(sub, P, R, 0.038, mat, y0=y, re=0.003, n=2 if _lo() else 4, ne=1 if _lo() else 4)
    xs = [-Lx / 2 + 0.07] + [-0.385 + 0.1925 * k for k in range(5)] + [Lx / 2 - 0.07]
    tx = []
    for k, x in enumerate(xs):                               # cubierta superior
        w = (0.14 if k in (0, 6) else 0.089) + j(0.003)
        x = x + (j(0.004) if 0 < k < 6 else (-0.07 + w / 2 if k == 0 else 0.07 - w / 2))
        dy = j(0.003)
        wplank(sub, (x - w / 2, -Ly / 2 + dy, tb + hs), (x + w / 2, Ly / 2 + dy, tb + hs + tt), mat, rs=rs, wear=0.0025)
        tx.append((x, w))
    for (x, w) in tx:                                        # clavos: dos por cruce
        for y in yst:
            for dx in (-w * 0.27, w * 0.27):
                nail(sub, _T(x + dx + j(0.004), y + j(0.006), tb + hs + tt) @ _Rz(j(180)))
    for (x, w) in bx:
        for y in yst:
            for dx in (-w * 0.27, w * 0.27):
                nail(sub, _T(x + dx + j(0.004), y + j(0.006), 0.0) @ _Rx(180))
    return sub


def threaded_rod(mb, M, r, z0, z1, pitch=0.0025, depth=0.0009, seg=SEG, thread=((None, None),)):
    """Varilla roscada a lo largo de Z de M: rosca helicoidal en V (paso `pitch`) en los tramos `thread` [(a, b)] y caña lisa
    entre ellos (la rosca solo se ve junto a las tuercas). Versión ligera: caña lisa de 12 lados de sombreado continuo."""
    if _lo():
        with mb.soft():
            revolve(mb, [(0.0, z0 - 0.0002), (r - 0.0004, z0), (r - 0.0004, z1), (0.0, z1 + 0.0002)], "steel", seg=12, M=M)
        return
    zs = []
    spans = [(z0 if a is None else a, z1 if b is None else b) for (a, b) in thread]
    edges = sorted({z0, z1} | {v for sp in spans for v in sp})
    for a, b in zip(edges[:-1], edges[1:]):
        th = any(sa - 1e-6 <= a and b <= sb + 1e-6 for (sa, sb) in spans)
        n = max(1, int(round((b - a) / (pitch / 4)))) if th else 1
        for k in range(n):
            zs.append((a + (b - a) * k / n, th))
    zs.append((z1, True))
    loops = [[(0.0, 0.0, z0 - 0.0002)]]
    for (z, th) in zs:
        ring = []
        for k in range(seg):
            a = 2 * PI * k / seg
            f = ((z - pitch * k / seg) / pitch) % 1.0
            rr = r - (depth * abs(2 * f - 1) if th else depth * 0.5)
            ring.append((rr * math.cos(a), rr * math.sin(a), z))
        loops.append(ring)
    loops.append([(0.0, 0.0, z1 + 0.0002)])
    skin(mb, loops, "steel", M)


def hex_nut(mb, M, s=0.024, h=0.014, washer=True, seg=24):
    """Tuerca hexagonal con chaflán cónico de 30° en ambas caras (la arista del hexágono se corta en círculo), sobre su
    rondana plana de cantos redondeados; apoyada en z = 0 local, eje +Z. Versión ligera: 6 caras reales con chaflán plano y
    rondana de 12 lados."""
    if _lo():
        z = 0.0
        if washer:
            with mb.soft():
                revolve(mb, [(s * 0.36, 0.0), (s * 0.72, 0.0), (s * 0.72, 0.003), (s * 0.36, 0.003)], "steel", seg=12, M=M, closed=True)
            z = 0.003
        rc = s / 2 / math.cos(PI / 6)
        lv = [(z, rc * 0.9), (z + 0.0015, rc), (z + h - 0.0015, rc), (z + h, rc * 0.9)]
        skin(mb, [[(rr * math.cos(PI / 3 * k), rr * math.sin(PI / 3 * k), zz) for k in range(6)] for (zz, rr) in lv], "steel", M)
        return z + h
    z = 0.0
    if washer:
        ro, ri, t = s * 0.72, s * 0.36, 0.003
        revolve(mb, [(ri, 0.0), (ro - 0.0006, 0.0), (ro, 0.0006), (ro, t - 0.0006), (ro - 0.0006, t), (ri, t)], "steel", seg=32, M=M,
                closed=True)
        z = t
    lv = [(z, 0.0), (z + 0.0008, 0.0008), (z + 0.0016, 0.0016), (z + 0.0026, 0.0026), (z + h - 0.0026, 0.0026), (z + h - 0.0016, 0.0016),
          (z + h - 0.0008, 0.0008), (z + h, 0.0)]
    loops = []
    for (zz, d) in lv:
        ring = []
        for k in range(seg):
            a = 2 * PI * k / seg
            rh = (s / 2) / math.cos(((a + PI / 6) % (PI / 3)) - PI / 6)
            rr = min(rh, s / 2 * 0.95 + d * math.tan(PI / 3))
            ring.append((rr * math.cos(a), rr * math.sin(a), zz))
        loops.append(ring)
    skin(mb, loops, "steel", M)
    return z + h


M107 = dict(R=0.07735, Rb=0.0790, z_og=0.344, Lo=0.300, z_nose=0.590, rn=0.0265, L=0.681)


def _og_r(z):
    """Radio de la ojiva tangente (proyectil clase 155 mm) a la altura z sobre el culote."""
    R, Lo = M107["R"], M107["Lo"]
    rho = (R * R + Lo * Lo) / (2 * R)
    x = M107["z_og"] + Lo - z                                # distancia a la punta teórica
    return math.sqrt(max(rho * rho - (Lo - x) ** 2, 0.0)) + R - rho


def _projectile(seed=0):
    """Proyectil de artillería clase 155 mm (genérico, proporciones del M107: cuerpo de 154,7 mm, banda de 158 mm, 605 mm
    sin espoleta, 681 mm con tapón de izaje) de pie sobre z = 0: culote con chaflán, cola de bote, banda de conducción
    cubierta por su anillo protector de polímero, cuerpo, ojiva tangente truncada en el pozo de espoleta, tapón de izaje
    roscado con collarín y argolla forjada; estarcidos amarillos doblados sobre el cuerpo."""
    mb = MB()
    lo = _lo()
    R = M107["R"]
    if lo:                                                   # 24 lados, menos anillos de perfil
        prof = [(0.0, 0.0), (0.0600, 0.0), (0.0656, 0.0040), (0.0745, 0.0350), (R, 0.0470), (R, M107["z_og"])]
        nog = 7
    else:
        prof = [(0.0, 0.0), (0.0520, 0.0), (0.0636, 0.0010), (0.0656, 0.0040), (0.0700, 0.0190), (0.0745, 0.0350), (R - 0.0003, 0.0430),
                (R, 0.0470), (R, 0.0710), (R, 0.1140), (R, 0.2000), (R, M107["z_og"])]
        nog = 14
    sg = SEG if lo else SEG_B
    for k in range(1, nog + 1):
        z = M107["z_og"] + (M107["z_nose"] - M107["z_og"]) * k / nog
        prof.append((_og_r(z), z))
    rn = prof[-1][0]
    zn = M107["z_nose"]
    prof += [(rn - 0.0006, zn + 0.0010), (0.0256, zn + 0.0016)]
    revolve(mb, prof, "paint_od", seg=sg, M=None, caps=True)
    # anillo protector de la banda de conducción (polímero), sobre la banda de cobre
    sect = []
    gz0, gz1, gr0, gr1, rr_ = 0.0745, 0.1115, R - 0.0006, M107["Rb"] + 0.0038, 0.0024
    for (cx, cz, a0) in ((gr1 - rr_, gz1 - rr_, 0.0), (gr0 + rr_ * 0.4, gz1 - rr_, PI / 2), (gr0 + rr_ * 0.4, gz0 + rr_, PI),
                         (gr1 - rr_, gz0 + rr_, 1.5 * PI)):
        for k in range(2 if lo else 4):
            a = a0 + PI / 2 * k / (1 if lo else 3)
            rx = rr_ if a0 in (0.0, 1.5 * PI) else rr_ * 0.4
            sect.append((cx + rx * math.cos(a), cz + rr_ * math.sin(a)))
    revolve(mb, sect, "polymer", seg=sg, closed=True)
    # tapón de izaje: cuerpo roscado en el pozo, collarín, cuello y argolla
    zp = zn + 0.0016
    if lo:
        revolve(mb, [(0.0250, zp - 0.004), (0.0290, zp + 0.0030), (0.0290, zp + 0.0130), (0.0170, zp + 0.0162), (0.0102, zp + 0.0240),
                     (0.0094, M107["L"] - 0.0465)], "steel", seg=16, caps=False)
        rw, Rr = 0.0062, 0.0185
        with mb.soft():
            revolve(mb, [(Rr + rw * math.cos(2 * PI * k / 6), rw * math.sin(2 * PI * k / 6)) for k in range(6)], "steel", seg=12,
                    M=_T(0, 0, M107["L"] - rw - Rr) @ _Rx(90), closed=True)
        stencil_cyl(mb, "155MM HE", 0.017, R - 0.0004, _T(0, 0, 0.215), ang=-PI / 2, depth=0.0012, sink=0.0012)   # cuerpo de 24 caras
        return mb
    revolve(mb, [(0.0250, zp - 0.004), (0.0262, zp + 0.0005), (0.0286, zp + 0.0030), (0.0290, zp + 0.0045), (0.0290, zp + 0.0130),
                 (0.0278, zp + 0.0150), (0.0170, zp + 0.0162), (0.0128, zp + 0.0190), (0.0102, zp + 0.0240), (0.0098, zp + 0.0330),
                 (0.0094, M107["L"] - 0.0465)], "steel", seg=SEG, caps=False)
    rw, Rr = 0.0062, 0.0185
    zc = M107["L"] - rw - Rr
    revolve(mb, [(Rr + rw * math.cos(2 * PI * k / 12), rw * math.sin(2 * PI * k / 12)) for k in range(12)], "steel", seg=SEG,
            M=_T(0, 0, zc) @ _Rx(90), closed=True)
    # estarcidos amarillos (doblados sobre el cuerpo)
    stencil_cyl(mb, "155MM HE", 0.017, R, _T(0, 0, 0.215), ang=-PI / 2)
    lot = ("LOT 31-02", "LOT 27-05", "LOT 22-09")[seed % 3]
    stencil_cyl(mb, lot, 0.012, R, _T(0, 0, 0.188), ang=-PI / 2, font="stencil2")
    return mb


def shell_pallet(seed=0, lod=0):
    """Tarima de 8 proyectiles de artillería clase 155 mm (2 × 4, de pie con su tapón de izaje) como se embarcan:
    689 × 346 × ~ 800 mm. Base: 2 patines de 4 × 4 in (75 × 89 mm), 5 tablas de cubierta y tablero de cunas de 36 mm con 8 barrenos que
    abrazan la cola de bote; marco superior de 32 mm con 8 barrenos que asientan en la ojiva (donde su radio es ~ 55 mm);
    4 varillas roscadas de 16 mm en las esquinas con rondana y tuerca hexagonal arriba y abajo (rosca helicoidal visible junto
    a las tuercas); 2 flejes horizontales que ciñen los cuerpos y 1 longitudinal sobre el marco y bajo la cubierta, con sellos
    engargolados; proyectiles con anillo protector de banda, cuerpo pintado verde olivo y estarcidos amarillos.
    Origen: centro en el piso; largo en X. Huella nueva 689 × 346 mm (antes 765 × 360: se ajustó a la tarima real).
    Fuentes: en.wikipedia.org/wiki/M107_projectile (154,71 mm de cuerpo, banda de 157,98 mm, 605 mm sin espoleta, tapón de
    izaje de argolla); vdoc.pub «Family of 155 mm M107 HE projectile» (681,2 mm con tapón de izaje); listado de partes NSN de
    la tarima del M107 (8 proyectiles por tarima de madera, 27,13 × 13,63 × 32,00 in, 797 lb); MIL-DTL-70951 (tarima de
    proyectiles de 155 mm, mismo envolvente que la de madera).
    lod=1 (racks): proyectiles de 24 lados con menos anillos de perfil, varillas lisas, tuercas hexagonales de 6 caras,
    flejes sin sello, tablas ligeras y una sola línea de estarcido (~ 22 k)."""
    lod = 1 if lod else 0
    key = ("shellpal", int(seed) % 4, lod)
    return _fresh(_cached(key, lambda: _at_lod(lod, _shell_pallet, int(seed) % 4)))


def _shell_pallet(seed):
    rs = rng(seed * 17 + 5)
    mb = MB()
    Lx, Ly = 0.689, 0.346
    px, py = 0.170, 0.172
    W = WOOD
    hs, td, tbd = 0.089, 0.019, 0.036
    for y in (-0.095, 0.095):                                  # patines de 4 × 4 in (las varillas bajan por fuera)
        wplank(mb, (-Lx / 2 + 0.002, y - 0.0375, 0.0), (Lx / 2 - 0.002, y + 0.0375, hs + 0.0005), W, rs=rs, kw=1)
    nd = 5
    dw = (Lx - (nd - 1) * 0.012) / nd
    for k in range(nd):                                        # cubierta
        x = -Lx / 2 + k * (dw + 0.012)
        wplank(mb, (x, -Ly / 2, hs), (x + dw, Ly / 2, hs + td), W, rs=rs)
    zb = hs + td
    cols = [(-1.5 + i) * px for i in range(4)]
    rows = [-py / 2, py / 2]
    lo = _lo()
    nh = SEG if lo else SEG_B
    holed_slab(mb, _T(0, 0, zb - 0.0004), Lx, Ly, tbd, holes=[(x, y, 0.0766, 0.0766, 2) for x in cols for y in rows], ch=0.003,
               rc=0.006, nc=3, mat=W, n=nh, chh=0.003, ne=3)
    src = [_cached(("proj", k, lo), lambda k=k: _projectile(k)) for k in range(3)]
    for i, x in enumerate(cols):
        for j, y in enumerate(rows):
            mb.join(src[(i + 2 * j + seed) % 3], _T(x, y, zb - 0.0012) @ _Rz(float(rs.uniform(-60, 60)) + (180 if j else 0) - 0.0))
    # marco superior asentado en las ojivas
    zfc = zb + 0.509
    tf = 0.032
    zf = zfc - tf / 2
    holed_slab(mb, _T(0, 0, zf), Lx, Ly, tf, holes=[(x, y, 0.0556, 0.0556, 2) for x in cols for y in rows], ch=0.003, rc=0.006, nc=3,
               mat=W, n=nh, chh=0.0045, ne=3)
    ztop = zf + tf
    # varillas roscadas con rondana y tuerca arriba (sobre el marco) y abajo (bajo la cubierta)
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (Lx / 2 - 0.0205), sy * (Ly / 2 - 0.021)
            zt_nut = hex_nut(mb, _T(x, y, ztop - 0.0003), s=0.024, h=0.014)
            hex_nut(mb, _T(x, y, hs + 0.0008) @ _Rx(180), s=0.024, h=0.014)
            z_lo = hs - 0.017 - 0.010
            z_hi = ztop + zt_nut + 0.012
            threaded_rod(mb, _T(x, y, 0), 0.008, z_lo, z_hi, thread=((z_lo, hs + 0.002), (ztop - 0.002, z_hi)))
    # flejes horizontales que ciñen los cuerpos
    R = M107["R"]
    t, w = 0.0008, 0.019
    o = 0.0005 if lo else 0.0001                               # fleje tenso de 0,8 mm: medio espesor hundido en lo que ciñe
    wx, wy = 2 * (cols[-1] + R + o), 2 * (rows[-1] + R + o)
    for k, zh in enumerate((zb + 0.170, zb + 0.300)):
        loop = [(x, y, zh) for (x, y) in rr_pts(wx, wy, R + o, 8 if lo else 16)]
        band(mb, loop, w=w, t=t, normal=(0, 0, 1))
        xs_ = float(rs.uniform(-0.05, 0.05)) + (-px / 2 if k else px / 2)
        band_seal(mb, _T(xs_, -wy / 2 - t / 2 + 0.0001, zh) @ _Rx(90), w=w)
    # fleje longitudinal sobre el marco, por los extremos y bajo la cubierta (entre patines)
    xe = Lx / 2 + o
    zu = hs - 0.0009                                           # bajo las tablas de cubierta (que no son planas): 0,5 mm libre
    path = fillet([(-xe, 0.0, zu), (xe, 0.0, zu), (xe, 0.0, ztop + o), (-xe, 0.0, ztop + o)], 0.004, 2 if lo else 4)
    band(mb, path, w=w, t=t, normal=(0, 1, 0))
    band_seal(mb, _T(float(rs.uniform(-0.12, 0.12)), 0.0, ztop + o + t / 2 - 0.0002), w=w)
    # estarcidos del tablero de cunas (frente -Y)
    Mf = _T(0, -Ly / 2 - 0.0002, zb + tbd / 2) @ _Rx(90)
    stencil(mb, "155MM HE  8 EA", 0.018, Mf @ _T(-0.14, 0, 0), depth=0.0007, sink=0.0009)
    if not lo:
        stencil(mb, ("LOT 2705", "LOT 2209", "LOT 3102", "LOT 2611")[seed % 4], 0.018, Mf @ _T(0.19, 0, 0), depth=0.0007, sink=0.0009)
    return mb


def crate_pallet(n=6, kind="wood", seed=0, straps=None, lod=0):
    """Cajas de munición de madera (ammo_crate «wood» o «small») estibadas en una tarima GMA de 48 × 40 in y amarradas:
    flejes de acero de 3/4 in con sello engargolado (straps="steel") o cinchos de matraca de 2 in con su matraca (carrete
    con vueltas de cincho, placas, palanca con mango de hule; straps="ratchet"; por omisión según la semilla), con
    esquineros de cartón doblado en las aristas superiores. n cajas (capas de 3 «wood» giradas 90° o de 6 «small»). Los
    flejes pasan bajo la cubierta superior (entre largueros), suben por el canto de la tarima y abrazan la carga.
    Origen: centro de la tarima en el piso; largo de la tarima (48 in) en X.
    Fuentes: interlakemecalux.com/blog/gma-pallet (48 × 40 in); fleje de acero de 3/4 × 0,023 in con sello de 1 1/4 in y
    cincho de matraca de 2 in (catálogos de embalaje).
    lod=1 (racks del almacén): tarima, cajas y amarres en su versión ligera, misma silueta (~ 37 k con 6 cajas, ~ 21 k con 3)."""
    lod = 1 if lod else 0
    return _at_lod(lod, _crate_pallet, n, kind, seed, straps, lod)


def _crate_pallet(n, kind, seed, straps, lod):
    r = rng(seed)
    mb = MB()
    zp = pallet_gma(mb, seed=seed, lod=lod)
    kind = kind if kind in ("wood", "small") else "wood"
    L, D, H = CRATE_DIMS[kind]
    tb = 0.016 if kind == "small" else 0.019
    if kind == "wood":
        slots = [(-0.41, 0.0, 90.0), (0.0, 0.0, 90.0), (0.41, 0.0, 90.0)]
        ys, xe = 0.205, 0.41 + D / 2                           # entre el fleje propio de la caja y el listón de la tapa
    else:
        slots = [(sx * 0.29, (j - 1) * 0.335, 0.0) for sx in (-1, 1) for j in range(3)]
        ys, xe = 0.205, 0.29 + L / 2 + 0.034
    per = len(slots)
    nl = max(1, -(-n // per))
    k = 0
    for layer in range(nl):
        for (x, y, rz) in slots:
            if k >= n:
                break
            sd = int(r.integers(0, 4))
            src = _cached(("crate", kind, sd, False, lod), lambda sd=sd: _at_lod(lod, _crate, L, D, H, kind, seed=sd))
            mb.join(src, _T(x, y, zp + layer * H) @ _Rz(rz + (180.0 if r.random() < 0.5 else 0.0)))
            k += 1
    full_top = n >= per * nl
    ztop = zp + (nl if full_top else max(nl - 1, 1)) * H
    kind_s = straps or ("steel" if seed % 2 == 0 else "ratchet")
    if kind_s == "steel":
        w, t, mat = 0.019, 0.0008, "steel"
    else:
        w, t, mat = 0.025, 0.0018, "canvas"
    zu = zp - 0.019 - 0.0011 - t / 2
    ztt = ztop - (tb if kind == "wood" else 0.0)              # sobre las tablas de la tapa (junto a los listones)
    xp = 0.6095 + t / 2 + 0.0009
    xc = xe + 0.0031 + t / 2                                   # cara de la carga + esquinero (el fleje lo aprieta)
    zt_ = ztt + 0.0031 + t / 2
    for yy in (-ys, ys):
        path = fillet([(-xp, yy, zu), (xp, yy, zu), (xp, yy, zp + 0.003), (xc, yy, zp + 0.045), (xc, yy, zt_), (-xc, yy, zt_),
                       (-xc, yy, zp + 0.045), (-xp, yy, zp + 0.003)], 0.008, 2 if lod else 4)
        band(mb, path, w=w, t=t, normal=(0, 1, 0), mat=mat)
        for sx in (-1, 1):                                     # esquineros de cartón doblado (L de 50 mm, 3,5 mm)
            x0 = sx * (xe - 0.0003)
            Q = [(0.0035, 0.0032), (0.0035, -0.05), (0.0, -0.05), (0.0, -0.0003), (-0.05, -0.0003), (-0.05, 0.0032)]
            Q = [(x0 + sx * qx, ztt + qz) for (qx, qz) in Q]
            side(mb, Q, [0.0035, 0.0006, 0.0006, 0.0005, 0.0006, 0.0006], 0.05, "cardboard", y0=yy, re=0.0 if lod else 0.0008,
                 n=1 if lod else 3, ne=1)
        if kind_s == "steel":
            band_seal(mb, _T(float(r.uniform(-0.25, 0.25)), yy, zt_ + t / 2 - 0.0002), w=w)
        else:
            _ratchet(mb, xc + t / 2, yy, zp + min(0.26, (ztt - zp) * 0.55), w)
    return mb


def _ratchet(mb, x0, y, zr, w=0.05):
    """Matraca de cincho de 2 in apoyada en la cara +X: base de dos placas laterales con dientes, carrete ranurado con tres
    vueltas de cincho, palanca de placas con mango de hule y pasadores."""
    if _lo():
        _ratchet_lo(mb, x0, y, zr, w)
        return
    for sy in (-1, 1):
        side(mb, [(x0, zr - 0.062), (x0 + 0.012, zr - 0.062), (x0 + 0.030, zr - 0.022), (x0 + 0.030, zr + 0.040), (x0 + 0.012, zr + 0.058),
                  (x0, zr + 0.058)], [0.0, 0.006, 0.008, 0.008, 0.006, 0.0], 0.003, "steel", y0=y + sy * (w / 2 + 0.0045), re=0.0007,
             n=3, ne=1)
        revolve(mb, [(0.0, -0.0025), (0.0185, -0.0025), (0.0195, -0.0015), (0.0195, 0.0015), (0.0185, 0.0025), (0.0, 0.0025)],
                "steel", seg=SEG, M=_T(x0 + 0.016, y + sy * (w / 2 + 0.0085), zr) @ _Rx(90),
                rmod=lambda a: 1.0 - 0.07 * (0.5 + 0.5 * math.cos(12 * a)) ** 4)
    revolve(mb, [(0.0, -w / 2 - 0.0115), (0.0055, -w / 2 - 0.0115), (0.0055, w / 2 + 0.0115), (0.0, w / 2 + 0.0115)], "steel", seg=SEG,
            M=_T(x0 + 0.016, y, zr) @ _Rx(90))
    for k, rr in enumerate((0.0062, 0.0079, 0.0096)):          # vueltas de cincho sobre el carrete (una sobre otra)
        revolve(mb, [(rr - 0.0009, -w / 2 + 0.0004), (rr + 0.0009, -w / 2 + 0.0004), (rr + 0.0009, w / 2 - 0.0004),
                     (rr - 0.0009, w / 2 - 0.0004)], "canvas", seg=SEG, M=_T(x0 + 0.016, y, zr) @ _Rx(90), closed=True)
    for sy in (-1, 1):                                         # palanca
        side(mb, [(x0 + 0.026, zr - 0.108), (x0 + 0.034, zr - 0.108), (x0 + 0.040, zr + 0.010), (x0 + 0.024, zr + 0.013),
                  (x0 + 0.0095, zr + 0.005), (x0 + 0.011, zr - 0.010)],
             [0.004, 0.004, 0.005, 0.004, 0.005, 0.004], 0.0025, "steel", y0=y + sy * (w / 2 + 0.0015), re=0.0006, n=3, ne=1)
    _slab(mb, _T(x0 + 0.034, y, zr - 0.098) @ _Ry(90), 0.034, w + 0.012, 0.010, rc=0.004, re=0.003, mat="rubber", nc=3, ne=3)
    revolve(mb, [(0.0, -w / 2 - 0.004), (0.003, -w / 2 - 0.004), (0.003, w / 2 + 0.004), (0.0, w / 2 + 0.004)], "steel", seg=16,
            M=_T(x0 + 0.031, y, zr - 0.086) @ _Rx(90))
    revolve(mb, [(0.0, -w / 2 - 0.0060), (0.0026, -w / 2 - 0.0060), (0.0026, w / 2 + 0.0060), (0.0, w / 2 + 0.0060)], "steel", seg=16,
            M=_T(x0 + 0.0021, y, zr - 0.052) @ _Rx(90))             # travesaño de la base: el cincho pasa debajo


def _ratchet_lo(mb, x0, y, zr, w):
    """Matraca ligera (racks): placas sin redondeo, carrete y vuelta de cincho de 12 lados, palanca, mango y travesaño."""
    for sy in (-1, 1):
        side(mb, [(x0, zr - 0.062), (x0 + 0.012, zr - 0.062), (x0 + 0.030, zr - 0.022), (x0 + 0.030, zr + 0.040), (x0 + 0.012, zr + 0.058),
                  (x0, zr + 0.058)], [0.0, 0.006, 0.008, 0.008, 0.006, 0.0], 0.003, "steel", y0=y + sy * (w / 2 + 0.0045), re=0.0, n=1)
        side(mb, [(x0 + 0.026, zr - 0.108), (x0 + 0.034, zr - 0.108), (x0 + 0.040, zr + 0.010), (x0 + 0.024, zr + 0.013),
                  (x0 + 0.0095, zr + 0.005), (x0 + 0.011, zr - 0.010)], [0.004, 0.004, 0.005, 0.004, 0.005, 0.004], 0.0025, "steel",
             y0=y + sy * (w / 2 + 0.0015), re=0.0, n=1)
    with mb.soft():
        revolve(mb, [(0.0, -w / 2 - 0.0115), (0.0055, -w / 2 - 0.0115), (0.0055, w / 2 + 0.0115), (0.0, w / 2 + 0.0115)], "steel", seg=12,
                M=_T(x0 + 0.016, y, zr) @ _Rx(90))
        revolve(mb, [(0.0052, -w / 2 + 0.0004), (0.0098, -w / 2 + 0.0004), (0.0098, w / 2 - 0.0004), (0.0052, w / 2 - 0.0004)], "canvas",
                seg=12, M=_T(x0 + 0.016, y, zr) @ _Rx(90), closed=True)
        revolve(mb, [(0.0, -w / 2 - 0.0052), (0.0026, -w / 2 - 0.0052), (0.0026, w / 2 + 0.0052), (0.0, w / 2 + 0.0052)], "steel", seg=8,
                M=_T(x0 + 0.0021, y, zr - 0.052) @ _Rx(90))
    _slab(mb, _T(x0 + 0.034, y, zr - 0.098) @ _Ry(90), 0.034, w + 0.012, 0.010, rc=0.004, re=0.003, mat="rubber", nc=1, ne=1)
