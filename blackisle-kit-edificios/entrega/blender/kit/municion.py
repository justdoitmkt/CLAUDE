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
from mathutils import Matrix, Vector

from kit.armory import plan, side, xloft
from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rng, rr_profile
from kit.clinic_equipo import revolve, sweep_frame
from kit.clinic_servicios import _edge_levels, rr_pts, skin
from kit.fonts import text_font

IN = 0.0254
SEG = 24          # cilindros visibles
SEG_B = 36        # cilindros grandes (proyectiles, latas vistas de cerca)
SEG_T = 16        # tubos, varillas, cuerdas
SEG_W = 12        # alambres <= 6 mm (dentro de mb.soft())
WOOD = "wood_od"
CRATE_DIMS = {"wood": (0.66, 0.36, 0.30), "long": (1.65, 0.42, 0.27), "small": (0.46, 0.30, 0.24)}

_CACHE = {}


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


def stencil(mb, s, size, M, mat="paint_yellow", depth=0.00045, font="stencil", align="CENTER", spacing=1.0):
    """Estarcido de pintura con tipografía de plantilla real (kit.fonts), centrado en el origen de M (plano XY, +Z hacia
    afuera; la altura de mayúsculas queda centrada en y = 0). Sobresale `depth` y se hunde 0,3 mm."""
    key = ("txt", s, round(size, 5), round(depth, 6), mat, font, align, spacing)

    def build():
        t = MB()
        text_font(t, s, size, depth, mat, None, font=font, align=align, res=3 if size >= 0.025 else 2, spacing=spacing)
        return t
    mb.join(_cached(key, build), M @ _T(0, -size * 0.355, 0))


def stencil_cyl(mb, s, size, R, M, ang=-PI / 2, mat="paint_yellow", depth=0.0005, font="stencil"):
    """Estarcido doblado sobre un cilindro de radio R (eje Z de M), centrado en el ángulo `ang` y en z = 0 local."""
    key = ("txt", s, round(size, 5), round(depth, 6), mat, font, "CENTER", 1.0)

    def build():
        t = MB()
        text_font(t, s, size, depth, mat, None, font=font, align="CENTER", res=2)
        return t
    src = _cached(key, build)

    def fn(co):
        th = ang + co.x / R
        rr = R + co.z
        return M @ Vector((rr * math.cos(th), rr * math.sin(th), co.y - size * 0.355))
    _join_map(mb, src, fn)


def nail(mb, M, d=0.0062, mat="steel"):
    """Cabeza de clavo de caja (plana, apenas abombada) sobre z = 0 local, +Z hacia afuera; el vástago queda en la madera."""
    with mb.soft():
        revolve(mb, [(d * 0.5, -0.0008), (d * 0.5, 0.0001), (d * 0.45, 0.00045), (d * 0.26, 0.0007), (0.0, 0.00075)], mat,
                seg=SEG_W, M=M, caps=False)


def rivet(mb, M, d=0.007, mat="steel", seg=16):
    """Cabeza de remache / tornillo de gota sobre z = 0 local (hundida 0,4 mm)."""
    revolve(mb, [(d / 2, -0.0004), (d / 2, 0.0002), (d * 0.42, d * 0.17), (d * 0.24, d * 0.27), (0.0, d * 0.3)], mat, seg=seg,
            M=M, caps=False)


def wire(mb, pts, r, mat="steel", bend=0.006, nseg=4, caps=True):
    """Alambre / varilla delgada por una polilínea con dobleces de radio real. r <= 3 mm: 12 lados de sombreado continuo."""
    P = fillet(pts, bend, nseg) if len(pts) > 2 else pts
    out = [P[0]]
    for p in P[1:]:
        if (Vector(p) - Vector(out[-1])).length > 1e-6:
            out.append(p)
    if r <= 0.0031:
        with mb.soft():
            mb.tube(out, r, seg=SEG_W, mat=mat, caps=caps)
    else:
        mb.tube(out, r, seg=SEG_T if r < 0.006 else SEG, mat=mat, caps=caps)


def band(mb, path, w=0.019, t=0.0006, normal=(1, 0, 0), mat="steel", closed=True):
    """Fleje de acero (cinta de w × t con cantos rolados) a lo largo de un lazo plano; `normal` = normal del plano del lazo."""
    prof = rr_profile(t, w, t * 0.45, n=1)
    mb.sweep(prof, path, mat=mat, closed_profile=True, closed_path=closed, normal=normal)


def band_seal(mb, M, w=0.019, L=0.032, mat="galvanized"):
    """Sello engargolado de fleje (camisa de lámina doblada sobre los dos extremos) con dos pares de muescas de engargolado,
    centrado en el origen de M (largo en X, apoyado en z = 0)."""
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


def rope(mb, pts, r=0.0062, pitch=0.030, seg=18, mat="fabric", caps=True, phase=0.0, smooth=True):
    """Cuerda torcida de 3 cabos de diámetro 2r: sección = unión de 3 círculos (cabos de radio 0,56 r a 0,44 r del eje)
    que gira a paso `pitch`; los anillos giran con la torsión, así las aristas entre cabos siguen la hélice sin dientes."""
    P = [Vector(p) for p in pts]
    if smooth and len(P) > 2:
        P = [Vector(p) for p in spline(P, 3)]
    P = _resample(P, pitch / 7)
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


def rope_knot(mb, M, s=0.0046, r=0.0062, mat="fabric", phase=0.0):
    """Nudo de tope (trébol apretado) de la cuerda, centrado en el origen de M; cabe en ~ 6,5 s × 6,5 s × 2 (s + r)."""
    pts = []
    n = 30
    for k in range(n + 1):
        t = 2 * PI * k / n + 0.35
        pts.append(M @ Vector((s * (math.sin(t) + 2 * math.sin(2 * t)), s * (math.cos(t) - 2 * math.cos(2 * t)),
                               -s * 0.9 * math.sin(3 * t))))
    rope(mb, pts, r=r, pitch=0.030, seg=15, mat=mat, caps=True, phase=phase, smooth=False)


# --------------------------------------------------------------------------------------------- madera: tablas, bloques
def wplank(mb, mn, mx, mat=WOOD, r=0.0028, rs=None, grain=0.00014, cup=0.00028, bow=0.0004, step=0.055, end=0.0011,
           wear=0.0016, kw=None, dings=None):
    """Tabla aserrada y cepillada: sección de cantos redondeados (4 segmentos por canto, nada facetado) con veta en
    geometría (crestas de 0,1–0,2 mm a lo largo), leve combado (cup) y arqueo (bow), cantos gastados con golpes al azar
    (anillos extra en cada golpe) y cabezas de corte de sierra con un chaflán de 1 mm, ligeramente fuera de escuadra.
    El eje largo es el mayor de la caja mn..mx; el ancho, el siguiente."""
    rs = rs if rs is not None else rng(0)
    ext = [mx[i] - mn[i] for i in range(3)]
    a = max(range(3), key=lambda i: ext[i])
    b, c = [i for i in range(3) if i != a]
    if ext[b] < ext[c]:
        b, c = c, b
    W, T, L = ext[b], ext[c], ext[a]
    bc, cc = (mn[b] + mx[b]) / 2, (mn[c] + mx[c]) / 2
    r = min(r, T * 0.38, W * 0.38)
    nw = kw if kw is not None else (3 if W > 0.05 else (1 if W > 0.025 else 0))
    nn = 1 if T > 0.03 else 0
    hw, ht = W / 2, T / 2
    prof = []                                   # (pb, pc, nb, nc, cara: 1 / -1 cara ancha, 0 canto; esquina, u)
    cs = [(hw - r, ht - r, 0.0), (-hw + r, ht - r, PI / 2), (-hw + r, -ht + r, PI), (hw - r, -ht + r, 1.5 * PI)]
    for ci, (cx, cy, a0) in enumerate(cs):
        for k in range(5):
            an = a0 + PI / 2 * k / 4
            prof.append((cx + r * math.cos(an), cy + r * math.sin(an), math.cos(an), math.sin(an), 0, ci if 0 < k < 4 else -1, 0.0))
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
            for _ in range(int(rs.integers(0, 3))):
                dings.append((ci, float(rs.uniform(0.05, 0.95)) * L, float(rs.uniform(0.006, 0.03)), float(rs.uniform(0.4, 1.0)) * wear))
    g_ph = [float(rs.uniform(0, 2 * PI)) for _ in prof]
    g_fr = [float(rs.uniform(1.5, 7.0)) for _ in prof]
    cup_s = float(rs.uniform(-1, 1)) * cup
    bow_s = float(rs.uniform(-1, 1)) * bow
    sweep_s = float(rs.uniform(-1, 1)) * bow * 0.6
    # posiciones de anillos a lo largo
    e = min(end, L * 0.1)
    n_in = max(1, int(round((L - 2 * e) / step)))
    S = {0.0, e, L - e, L}
    for k in range(1, n_in):
        S.add(e + (L - 2 * e) * k / n_in)
    for (_, p, wd, _) in dings:
        for q in (p - wd, p - wd * 0.4, p, p + wd * 0.4, p + wd):
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
    cols = _fix_cuts([h[0] for h in holes])
    lv = _edge_levels(T, ch, ch, ne) if ch > 0 else [(0.0, 0.0), (0.0, T)]
    pts_lv = [_perim(L - 2 * dl, W - 2 * dl, max(rc - dl, 3e-4), nc, xc=cols) for (dl, z) in lv]
    loops = [[(p[0], p[1], z) for p in P] for P, (dl, z) in zip(pts_lv, lv)]
    V = skin(mb, loops, mat, M, cap0=False, cap1=False)
    hl = []
    for j in range(4):
        p = PI / 2 * j / 3
        hl.append((chh * (1 - math.sin(p)), chh * (1 - math.cos(p))))
    for j in range(4):
        p = PI / 2 * j / 3
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
