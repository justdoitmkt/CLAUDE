"""kit/fortif.py — fortificación y equipo de sitio militar CONTEMPORÁNEO (MIL_1_almacen, MIL_2_avanzada): limpio, mantenido,
apenas intemperizado. Regla R-AAA: construcción real (mallas soldadas con alambres de verdad, bobinas, liner, sacos blandos que
se asientan unos sobre otros, concertina con cuchillas reales, torres con perfiles, uniones y tornillería).

Convenciones (todas las funciones devuelven un MB de kit.clinic, que bisela box() por omisión):
- metros, Z arriba, origen en el piso (z = 0);
- piezas lineales (hesco_run, t_wall, jersey_barrier, sandbag_wall, concertina*, drop_arm_barrier) corren a lo largo de +X
  desde x = 0; el lado exterior / frente mira a -Y; el espesor queda centrado en y = 0 salvo que la función diga otra cosa;
- piezas sueltas (sandbag, guard_tower, light_tower, floodlight_tripod, camo_net, tactical_generator, jerry_can): centradas
  en planta en el origen, frente hacia -Y.
Materiales: steel, galvanized, aluminium, concrete, rubber, cable, plastic, paint_yellow, sign_white, sign_red, glass,
metal_rust (muy poco), sandbag (polipropileno tejido), geotextile (liner HESCO), canvas, net (red de camuflaje, DOS CARAS),
paint_od (acero verde olivo), paint_tan (acero arena), sand (relleno).
Cilindros visibles >= 24 lados; tubos/cuerdas >= 14 (el kit suaviza a 30°); alambres y cordeles de <= 6 mm (malla y bobinas
HESCO, alma y fleje de la concertina, cordel de la red, amarres, cordón de los sacos, cordones de soldadura) de 12 lados con
sombreado continuo (MB.soft / _np_faces(soft=True)). Lo que se repite mucho se arma en bloque con numpy (_np_faces, _tubes_np).
Medidas verificadas contra fuentes reales: ver el bloque de cada función y ESTADO.md.
"""
import math

import bmesh
import bpy  # noqa: F401  (bpy antes que mathutils)
import numpy as np
from mathutils import Matrix, Vector, noise

from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rbox, rng, rr_profile, rtube  # noqa: F401
from kit.clinic_equipo import angle_l, loft_rings, sweep_frame  # noqa: F401
from kit.clinic_servicios import hexnut, label, lathe, rr_pts, skin, slab  # noqa: F401

SEG = 24          # lados de todo cilindro visible
SEG_T = 14        # lados de tubos delgados / cables / cuerdas
IN = 0.0254


# ====================================================================================================== utilidades
def _v(p):
    return Vector((float(p[0]), float(p[1]), float(p[2])))


def zip_chains(mb, P, Q, mat, flip=False):
    """Triangula la franja entre dos cadenas de vértices bmesh P y Q (mismo sentido, número de vértices distinto) avanzando
    por longitud de arco normalizada: sin uniones en T ni triángulos degenerados."""
    def params(C):
        acc = [0.0]
        for i in range(1, len(C)):
            acc.append(acc[-1] + (C[i].co - C[i - 1].co).length)
        t = acc[-1] or 1.0
        return [a / t for a in acc]
    tp, tq = params(P), params(Q)
    i = j = 0
    while i < len(P) - 1 or j < len(Q) - 1:
        adv_p = j >= len(Q) - 1 or (i < len(P) - 1 and tp[i + 1] <= tq[j + 1])
        if adv_p:
            tri = [P[i], P[i + 1], Q[j]]
            i += 1
        else:
            tri = [P[i], Q[j + 1], Q[j]]
            j += 1
        mb.face(list(reversed(tri)) if flip else tri, mat)


def grid_faces(mb, G, mat, flip=False, smooth=True):
    """Cuadriláteros de una rejilla G[fila][columna] de vértices bmesh."""
    for j in range(len(G) - 1):
        for i in range(len(G[0]) - 1):
            q = [G[j][i], G[j][i + 1], G[j + 1][i + 1], G[j + 1][i]]
            f = mb.face(list(reversed(q)) if flip else q, mat)
            f.smooth = smooth


def ngon(mb, verts, mat, smooth=True):
    """Cara plana de n lados triangulada al momento (BEAUTY): bordes planos con vértices colineales sin uniones en T."""
    f = mb.face(verts, mat)
    f.normal_update()                                      # sin normal, la proyección del polyfill sale mal (cóncavos)
    res = bmesh.ops.triangulate(mb.bm, faces=[f], quad_method="BEAUTY", ngon_method="BEAUTY")
    for g in res["faces"]:
        g.smooth = smooth
    return res["faces"]


def tube_path(mb, pts, r, seg=SEG_T, mat="cable", bend=None, nseg=6, caps=True, radii=None):
    """Tubo / cable por polilínea con dobleces de radio real `bend`."""
    P = fillet(pts, bend, nseg) if (bend and len(pts) > 2) else [tuple(p) for p in pts]
    out = [P[0]]
    for p in P[1:]:
        if (_v(p) - _v(out[-1])).length > 1e-6:
            out.append(p)
    mb.tube(out, r, seg=seg, mat=mat, caps=caps, radii=radii)
    return out


def catenary(p0, p1, sag, n=12):
    """Puntos de un cable colgado entre p0 y p1 con flecha `sag` al centro (parábola)."""
    p0, p1 = _v(p0), _v(p1)
    return [tuple(p0.lerp(p1, k / n) - Vector((0, 0, 4 * sag * (k / n) * (1 - k / n)))) for k in range(n + 1)]


# ===================================================================================================== mallas en bloque
def _np_faces(mb, V, F, mat, soft=False, smooth=True):
    """Crea en bloque los vértices V (N × 3) y las caras F (listas de índices en V) con un material; soft = sombreado
    continuo (ver MB.soft). Devuelve la lista de BMVerts."""
    bm = mb.bm
    vs = [bm.verts.new(p) for p in np.asarray(V, float).reshape(-1, 3).tolist()]
    mi = mb.mi(mat)
    sl = mb._soft_layer() if soft else None
    for q in F:
        f = bm.faces.new([vs[i] for i in q])
        f.material_index = mi
        f.smooth = smooth
        if soft:
            f[sl] = 1
    return vs


def _grid_quads(nr, nc, closed=False, off=0):
    """Índices de cuadriláteros de una rejilla nr × nc (filas × columnas), cerrada en columnas si closed."""
    idx = np.arange(nr * nc).reshape(nr, nc) + off
    if closed:
        idx = np.concatenate([idx, idx[:, :1]], 1)
    return np.stack([idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]], -1).reshape(-1, 4)


def _tube_rings(P, r, seg=12, N0=None):
    """Anillos (K × seg × 3) de un tubo circular por la polilínea P (K × 3) con marco de transporte paralelo. r escalar o (K,)."""
    P = np.asarray(P, float)
    K = len(P)
    T = np.gradient(P, axis=0) if K > 2 else np.repeat((P[1:] - P[:1]), K, 0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    ref = np.array([0.0, 0.0, 1.0]) if abs(T[0][2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    N = (ref - T[0] * ref.dot(T[0])) if N0 is None else np.asarray(N0, float)
    N = N / np.linalg.norm(N)
    an = 2 * PI * np.arange(seg) / seg
    ca, sa = np.cos(an), np.sin(an)
    rr = np.broadcast_to(np.asarray(r, float), (K,))
    out = np.empty((K, seg, 3))
    for i in range(K):
        N = N - T[i] * N.dot(T[i])
        N /= np.linalg.norm(N)
        B = np.cross(T[i], N)
        out[i] = P[i] + rr[i] * (np.outer(ca, N) + np.outer(sa, B))
    return out


def _tubes_np(mb, paths, r, seg=12, mat="galvanized", soft=True, caps=True):
    """Varios tubos circulares de una vez (alambres, varillas, cordones): paths = lista de polilíneas (K × 3)."""
    V, F = [], []
    off = 0
    for P in paths:
        R = _tube_rings(P, r, seg)
        K = len(R)
        V.append(R.reshape(-1, 3))
        F.extend(_grid_quads(K, seg, closed=True, off=off).tolist())
        if caps:
            F.append(list(range(off + seg - 1, off - 1, -1)))
            F.append(list(range(off + (K - 1) * seg, off + K * seg)))
        off += K * seg
    if V:
        _np_faces(mb, np.concatenate(V, 0), F, mat, soft=soft)


# ============================================================================================================ HESCO
# HESCO / Concertainer MIL (hesco.com, tabla de dimensiones nominales: MIL1 54" × 42" (1,37 × 1,06 m), MIL7 87" × 84"
# (2,21 × 2,13 m), MIL8 54" × 48"; malla electrosoldada de 76,2 mm (3") de alambre de 4-5 mm galvanizado Galfan; esquinas
# unidas con bisagra de espiral y pasador; liner de geotextil no tejido de PP de 250-350 g/m², beige o verde). Celdas
# cuadradas: largo de celda = ancho del muro. Lleno, el relleno empuja el geotextil por cada cuadro de la malla (acolchado de
# ~1 cm) y toda la cara se panzea entre las bobinas (2-4 cm, más en MIL7).
HESCO = {"MIL1": (1.37, 1.06), "MIL7": (2.21, 2.13), "MIL8": (1.37, 1.22)}
HW_R = 0.002          # radio del alambre de la malla (4 mm)
H_MESH = 0.0762       # paso nominal de la malla (3")
H_EDGE = 0.005        # alambre vertical de orilla: a 5 mm del eje de la bobina
H_COIL_R = 0.011      # radio de la línea central de la bobina de unión
H_LIN_D = 2 * HW_R + 0.0006   # el liner apoya detrás de la capa interior de alambres
H_LIN_T = 0.003       # espesor del geotextil
H_CORNER_R = 0.032    # radio de la esquina del liner (queda por fuera de la bobina)


class _HescoBelly:
    """Panza de una cara expuesta: desplazamiento hacia afuera B(u, z) nulo en las bobinas (u = 0, c) y en el piso, máximo
    a ~45 % de la altura; con una ondulación suave para que ninguna cara sea igual a otra."""

    def __init__(self, r, c, H, amp):
        self.c, self.H = c, H
        self.amp = amp * float(r.uniform(0.75, 1.25))
        self.k = (float(r.uniform(0, 6)), float(r.uniform(0, 6)), float(r.uniform(-0.15, 0.15)))

    def __call__(self, u, z):
        u = np.asarray(u, float)
        z = np.asarray(z, float)
        su = np.clip(np.sin(PI * np.clip(u / self.c, 0, 1)), 0, 1) ** 0.85
        zz = np.clip(z / self.H, 0, 1.05)
        sv = np.sin(PI * np.clip(zz, 0, 1) ** 0.78 * 0.9)
        w = 1 + 0.12 * np.sin(2 * PI * u / self.c * 1.3 + self.k[0]) * np.sin(PI * zz * 1.7 + self.k[1])
        return self.amp * su * sv * w * (1 + self.k[2] * (u / self.c - 0.5))


def _hesco_panel_frame(O, U, N):
    """Matriz del panel: x local = u (a lo largo), y local = profundidad (+ hacia afuera, N), z = altura."""
    O, U, N = _v(O), _v(U), _v(N)
    return Matrix(((U.x, N.x, 0, O.x), (U.y, N.y, 0, O.y), (U.z, N.z, 1, O.z), (0, 0, 0, 1)))


def _hesco_mesh(mb, M, c, H, us, vs, r, belly=None, vmin=None, h_ext=(-0.001, -0.001)):
    """Malla electrosoldada de un panel (u 0..c, profundidad y, altura z): verticales en la capa exterior (+HW_R),
    horizontales en la interior (-HW_R), alambres de 4 mm de 12 lados con sombreado continuo que siguen la panza de la cara
    (belly) con una ondulación de ±0,6 mm, y un punto de soldadura (botón aplastado) en cada cruce. vmin: solo la parte de
    arriba (divisiones interiores). h_ext: cuánto rebasan los horizontales a los verticales de orilla en cada extremo."""
    Mn = np.array(M)
    R3, t3 = Mn[:3, :3], Mn[:3, 3]
    z0 = -0.02 if vmin is None else vmin
    zt = H                                                  # las verticales mueren a ras del horizontal de arriba
    B = belly if belly is not None else (lambda u, z: np.zeros(np.broadcast(np.asarray(u), np.asarray(z)).shape))
    nzs = max(4, int(round((zt - z0) / 0.17)))
    paths = []
    for u in us:
        zz = np.linspace(z0, zt, nzs + 1)
        wob = 0.0004 * np.sin(zz * float(r.uniform(5, 9)) + float(r.uniform(0, 6)))
        P = np.stack([np.full_like(zz, u), HW_R + B(u, zz) + wob, zz], 1)
        paths.append(P @ R3.T + t3)
    vrows = [v for v in vs if vmin is None or v >= vmin + 0.01]
    nus = max(4, int(round(c / 0.15)))
    for v in vrows:
        uu = np.linspace(us[0] - h_ext[0], us[-1] + h_ext[1], nus + 1)
        wob = 0.0004 * np.sin(uu * float(r.uniform(5, 9)) + float(r.uniform(0, 6)))
        P = np.stack([uu, -HW_R + B(uu, v) + wob, np.full_like(uu, v)], 1)
        paths.append(P @ R3.T + t3)
    _tubes_np(mb, paths, HW_R, seg=12, mat="galvanized", soft=True, caps=True)
    # soldaduras: botón elíptico (3,4 mm en el plano de la malla, 1,7 mm de grueso) en el plano de contacto de las capas
    UU, ZZ = np.meshgrid(np.asarray(us, float), np.asarray(vrows, float))
    UU, ZZ = UU.ravel(), ZZ.ravel()
    D = B(UU, ZZ)
    na = 6
    an = 2 * PI * (np.arange(na) + 0.5) / na
    V, F = [], []
    for k in range(len(UU)):
        ctr = np.array([UU[k], D[k], ZZ[k]])
        ring = ctr + np.stack([0.0034 * np.cos(an), np.zeros(na), 0.0034 * np.sin(an)], 1)
        poles = ctr + np.array([[0.0, 0.0017, 0.0], [0.0, -0.0017, 0.0]])
        o = k * (na + 2)
        V.append(np.concatenate([ring, poles], 0))
        for j in range(na):
            jj = (j + 1) % na
            F.append([o + j, o + jj, o + na])
            F.append([o + jj, o + j, o + na + 1])
    _np_faces(mb, np.concatenate(V, 0) @ R3.T + t3, F, "galvanized", soft=True)


def _hesco_coil(mb, axis_xy, H, vs, quad, pitch, phase=0.19):
    """Bisagra de espiral (alambre de 4 mm, 12 lados, 10 puntos por vuelta) que abraza los verticales de orilla de los dos
    paneles + pasador de unión de 6 mm con gancho doblado sobre la orilla de arriba. quad = ángulo (rad) de la dirección
    'hacia afuera' de la junta; la fase evita los alambres horizontales."""
    x, y = axis_xy
    z0 = vs[0] + phase * pitch
    turns = int((H - 0.01 - z0) / pitch)
    k = np.arange(turns * 10 + 1)
    a = quad + PI / 4 + k * 2 * PI / 10
    pts = np.stack([x + H_COIL_R * np.cos(a), y + H_COIL_R * np.sin(a), z0 + pitch * k / 10], 1)
    hook = [(x, y, 0.02), (x, y, H + 0.035), (x + 0.025 * math.cos(quad), y + 0.025 * math.sin(quad), H + 0.05),
            (x + 0.045 * math.cos(quad), y + 0.045 * math.sin(quad), H + 0.02)]
    _tubes_np(mb, [pts], HW_R, seg=12, soft=True)
    _tubes_np(mb, [np.array(fillet(hook, 0.012, 4))], 0.003, seg=12, soft=True)


def hesco_run(n=5, kind="MIL1", seed=0):
    """Línea de n celdas de muro HESCO MIL (MIL1 1,37 × 1,06; MIL7 2,21 × 2,13; MIL8 1,37 × 1,22 m) a lo largo de +X desde
    x = 0; cara exterior en -Y, muro centrado en y = 0 (ancho W). Construcción: malla electrosoldada de 76,2 mm con alambres
    de 4 mm de 12 lados (verticales por fuera, horizontales por dentro) y un punto de soldadura en cada cruce; bisagra de
    espiral + pasador con gancho en cada esquina; liner de geotextil de 3 mm con esquinas redondeadas dentro de la bobina,
    acolchado entre alambres (el relleno lo empuja 8-14 mm por cada cuadro), panza de toda la cara entre bobinas (2-3 cm en
    MIL1, 3-4,5 cm en MIL7) que la malla sigue, orilla de arriba doblada hacia afuera sobre el alambre superior en las caras
    expuestas y hacia adentro en las divisiones, y tapa de tierra irregular con terrones y piedras. Toda la línea con un
    ligero desplome (< 0,5°) que varía de celda en celda."""
    H, W = HESCO[kind]
    r = rng(seed)
    mb = MB()
    c = W
    ncol = max(2, int(round((c - 2 * H_EDGE) / H_MESH)))
    nrow = max(2, int(round((H - 0.025) / H_MESH)))
    us = [H_EDGE + (c - 2 * H_EDGE) * k / ncol for k in range(ncol + 1)]
    vs = [0.025 + (H - 0.025) * j / nrow for j in range(nrow + 1)]
    pitch = vs[1] - vs[0]
    big = kind == "MIL7"
    L = n * c
    fills = [float(H - 0.075 + r.uniform(-0.02, 0.012)) for _ in range(n)]
    bamp = 0.038 if big else 0.024
    # paredes exteriores: frente (-Y), fondo (+Y) por celda; extremos en x = 0 y x = L. Cada una con su panza.
    walls = []
    bellies = {}
    for i in range(n):
        bellies[("f", i)] = _HescoBelly(r, c, H, bamp)
        bellies[("b", i)] = _HescoBelly(r, c, H, bamp)
        walls.append((("f", i), (i * c, -W / 2, 0), (1, 0, 0), (0, -1, 0)))
        walls.append((("b", i), ((i + 1) * c, W / 2, 0), (-1, 0, 0), (0, 1, 0)))
    bellies[("e0", 0)] = _HescoBelly(r, c, H, bamp * 0.9)
    bellies[("e1", n - 1)] = _HescoBelly(r, c, H, bamp * 0.9)
    walls.append((("e0", 0), (0, W / 2, 0), (0, -1, 0), (-1, 0, 0)))
    walls.append((("e1", n - 1), (L, -W / 2, 0), (0, 1, 0), (1, 0, 0)))
    # ---------------------------------------------------------------- malla de alambre
    for (key, O, U, N) in walls:
        _hesco_mesh(mb, _hesco_panel_frame(O, U, N), c, H, us, vs, r, belly=bellies[key],
                    h_ext=(-0.003, -0.003) if key[0][0] == "e" else (0.001, 0.001))
    us_d = [0.006 + (c - 0.012) * k / ncol for k in range(ncol + 1)]
    for i in range(1, n):                                  # divisiones: solo asoman arriba del relleno
        M = _hesco_panel_frame((i * c, -W / 2, 0), (0, 1, 0), (1, 0, 0))
        _hesco_mesh(mb, M, c, H, us_d, vs, r, vmin=min(fills[i - 1], fills[i]) - 0.03, h_ext=(0.0, 0.0))
    # ---------------------------------------------------------------- bobinas + pasadores (4 por celda de esquina, 2 por junta)
    for i in range(n + 1):
        x = i * c
        _hesco_coil(mb, (x, -W / 2), H, vs, -PI / 2 if 0 < i < n else (-3 * PI / 4 if i == 0 else -PI / 4), pitch)
        _hesco_coil(mb, (x, W / 2), H, vs, PI / 2 if 0 < i < n else (3 * PI / 4 if i == 0 else PI / 4), pitch)
    # ---------------------------------------------------------------- liner + relleno por celda
    for i in range(n):
        bl = [bellies[("f", i)], None, bellies[("b", i)], None]
        if i == n - 1:
            bl[1] = bellies[("e1", n - 1)]
        if i == 0:
            bl[3] = bellies[("e0", 0)]
        _hesco_cell_liner(mb, i, c, W, H, us, vs, fills[i], bl, r, big)
        _hesco_fill(mb, i, c, W, H, fills[i], r)
    # ---------------------------------------------------------------- desplome: la línea se ladea apenas, distinto en cada celda
    lean = [float(r.uniform(-0.006, 0.006)) for _ in range(n + 1)]
    xs = np.array([i * c for i in range(n + 1)])
    for v in mb.bm.verts:
        co = v.co
        lz = float(np.interp(co.x, xs, lean))
        co.y += lz * max(co.z, 0.0)
        co.x += 0.25 * lz * max(co.z, 0.0)
    return mb


def _hesco_cell_liner(mb, i, c, W, H, us, vs, zf, bellies, r, big=False):
    """Liner de una celda como una sola hoja de 3 mm: lazo en planta (4 paredes + 4 esquinas redondeadas) × perfil vertical.
    Perfil de cada columna (línea media de la tela): sube pegado a la malla (acolchado entre alambres + panza de la cara),
    se dobla en la orilla de arriba (hacia afuera sobre el alambre superior en las caras expuestas, hacia adentro en las
    divisiones y las esquinas) y cuelga 2-4,5 cm con la orilla ondulada; la cara interior baja hasta perderse en el
    relleno. Malla densa (4 × 4 por cuadro en las caras expuestas), sombreado continuo."""
    x0 = i * c
    d0, t = H_LIN_D, H_LIN_T
    Rc = H_CORNER_R
    s0 = Rc + d0
    corners = [(x0, -W / 2), (x0 + c, -W / 2), (x0 + c, W / 2), (x0, W / 2)]
    dirs = [np.array((1.0, 0, 0)), np.array((0, 1.0, 0)), np.array((-1.0, 0, 0)), np.array((0, -1.0, 0))]
    nors = [np.array((0, -1.0, 0)), np.array((1.0, 0, 0)), np.array((0, 1.0, 0)), np.array((-1.0, 0, 0))]
    sub = 3 if big else 4
    pu = us[1] - us[0]
    pv = vs[1] - vs[0]
    ph = float(r.uniform(0, 100))
    # ---- columnas del lazo: (punto base en planta, normal hacia afuera, pared, u, signo del doblez, acolchado?)
    cols = []
    for w in range(4):
        ex = bellies[w] is not None
        if ex:
            uc = [us[0] + pu * k / sub for k in range(len(us) * sub)]
            uc = [u for u in uc if s0 + 0.006 < u < c - s0 - 0.006]
            uc = [s0] + uc + [c - s0]
        else:
            uc = [s0 + (c - 2 * s0) * k / 6 for k in range(7)]
        C = np.array((corners[w][0], corners[w][1], 0.0))
        for u in uc:
            e = min(u - s0, c - s0 - u)
            if ex:                                         # la orilla floja no es pareja: tramos doblados afuera, parados, adentro
                fold = 0.55 + 0.9 * noise.noise(Vector((float(C[0] + dirs[w][0] * u) * 2.6, float(C[1] + dirs[w][1] * u) * 2.6, ph)))
                sg = min(max(fold, -0.7), 1.0)
                sg = min(sg, -0.6 + 1.6 * e / 0.09)
            else:
                sg = -1.0
            cols.append((C + dirs[w] * u, nors[w], w, u, sg, ex))
        # esquina redondeada hacia la pared siguiente (3 columnas intermedias)
        wn = (w + 1) % 4
        Cn = np.array((corners[wn][0], corners[wn][1], 0.0))
        ctr = Cn - dirs[w] * s0 + dirs[wn] * s0
        for k in (1, 2, 3):
            a = k / 4 * (PI / 2)
            nd = nors[w] * math.cos(a) + dirs[w] * math.sin(a)
            cols.append((ctr + nd * (Rc + d0), nd, -1, 0.0, -0.8, False))
    nc = len(cols)
    # ---- filas de la parte recta del perfil: densas (sub por cuadro) bajo el relleno, ralas arriba
    zc_top = H + 0.0078                                    # centro del doblez (libra el alambre de arriba)
    rows = [-0.02]
    for j in range(len(vs) - 1):
        for k in range(sub):
            z = vs[j] + pv * k / sub
            if z < zf - 0.01:
                rows.append(z)
    zq = rows[-1]
    nadd = max(2, int(math.ceil((zc_top - zq) / 0.022)))
    rows += [zq + (zc_top - zq) * k / nadd for k in range(1, nadd + 1)]
    rows = np.array(rows)
    nz = len(rows)
    zin = zf - 0.03
    # presión del relleno: plena abajo, nula en el nivel del relleno
    press = np.clip((zf - 0.012 - rows) / 0.12, 0, 1) ** 0.8 * (0.75 + 0.25 * np.clip(rows / 0.08, 0, 1))
    na, nfl = 7, 4                                         # puntos del doblez y del faldón colgante
    Rm = 0.0055 + t / 2                                    # radio medio del doblez
    # amplitud del acolchado por cuadro (8-14 mm, al azar) y del abombado de cada columna
    nap = len(us) + 2
    A_ap = r.uniform(0.0085, 0.0135, (len(vs) + 2, nap))
    mids = []                                              # por columna: (puntos (m × 2) en (d, z), normales, índice zin)
    for (P0, nrm, w, u, sg, ex) in cols:
        bel = bellies[w] if (w >= 0 and bellies[w] is not None) else None
        Bz = bel(u, rows) if bel is not None else np.zeros(nz)
        D = np.zeros(nz)
        if ex:
            fu = (u - us[0]) / pu
            iu = int(np.clip(math.floor(fu), 0, nap - 1))
            Su = abs(math.sin(PI * (fu - math.floor(fu)))) ** 0.85
            fz = (rows - vs[0]) / pv
            iz = np.clip(np.floor(fz).astype(int), 0, len(vs))
            Sv = np.abs(np.sin(PI * (fz - np.floor(fz)))) ** 0.85 * (rows > vs[0] - 0.0005)
            Sv = np.where(rows < vs[0], np.abs(np.sin(PI * (rows - vs[0]) / pv * 0.5)) ** 0.85, Sv)
            Aap = A_ap[iz, iu]
            g = 2 * HW_R - 0.0004
            D = Sv * (g + (Aap - g) * Su) * press
        # orilla de arriba: largo del faldón ondulado; columnas de esquina y de división, cortito
        if ex:
            Lf = 0.024 + 0.014 * (0.5 + 0.5 * noise.noise(Vector((float(P0[0]) * 6, float(P0[1]) * 6, ph)))) + 0.006 * math.sin(u * 37 + ph)
        else:
            Lf = 0.016 + 0.006 * (0.5 + 0.5 * noise.noise(Vector((float(P0[0]) * 6, float(P0[1]) * 6, ph + 4))))
        Lf *= min(1.0, 0.35 + 0.65 * abs(sg))
        dm = -d0 - t / 2
        Pz = [(dm + D[k] + Bz[k], rows[k]) for k in range(nz)]
        # doblez: arco de radio Rm hacia el lado sg (afuera > 0), barrido |sg|·180°
        side = 1.0 if sg >= 0 else -1.0
        sweep = abs(sg) * PI
        dtop = dm + Bz[-1]
        cx = dtop + side * Rm
        for k in range(1, na + 1):
            th = PI / 2 + side * PI / 2 - side * sweep * k / na   # ángulo desde el centro del arco
            Pz.append((cx + Rm * math.cos(th), zc_top + Rm * math.sin(th)))
        th_end = PI / 2 + side * PI / 2 - side * sweep
        tdir = np.array((math.sin(th_end), -math.cos(th_end))) * side
        if np.linalg.norm(tdir) < 1e-6:
            tdir = np.array((0.0, 1.0))
        pe = np.array(Pz[-1])
        for k in range(1, nfl + 1):
            s_ = Lf * k / nfl
            flare = 0.12 * s_ * side * (1 if sweep > PI * 0.7 else 0)
            wv = 0.0022 * math.sin(u * 23 + ph + k) * k / nfl
            q = pe + tdir * s_ + np.array((flare + wv * side, 0.0))
            Pz.append((float(q[0]), float(q[1])))
        Pz = np.array(Pz)
        tg = np.gradient(Pz, axis=0)
        tg /= np.maximum(np.linalg.norm(tg, axis=1, keepdims=True), 1e-12)
        nn = np.stack([tg[:, 1], -tg[:, 0]], 1)            # normal hacia +d en la parte que sube
        mids.append((P0, nrm, Pz, nn))
    # ---- vértices: cara A (hacia la malla) de abajo hasta la punta del faldón, luego cara B (hacia el relleno) de la punta
    # de regreso hasta zin
    m = len(mids[0][2])
    kin = int(np.searchsorted(rows, zin))
    nb = m - kin
    NR = m + nb
    V = np.zeros((NR, nc, 3))
    for j, (P0, nrm, Pz, nn) in enumerate(mids):
        A = Pz + nn * (t / 2)
        Bf = (Pz - nn * (t / 2))[kin:][::-1]
        prof = np.concatenate([A, Bf], 0)
        V[:, j, :] = P0[None, :] + nrm[None, :] * prof[:, 0:1] + np.array((0, 0, 1.0))[None, :] * prof[:, 1:2]
    F = _grid_quads(NR, nc, closed=True)
    _np_faces(mb, V.reshape(-1, 3), F.tolist(), "geotextile", soft=True)


def _hesco_fill(mb, i, c, W, H, zf, r):
    """Tapa de relleno de una celda: rejilla en planta de ~3 cm recortada al contorno interior del liner (cuadro de esquinas
    redondeadas), tierra compactada con corona baja e irregular (ruido en tres escalas + hondonadas de las paladas) que muere
    bajo la cara interior del liner, faldón que baja dentro de la tela; terrones (arena) y piedras (concreto) sueltos."""
    x0 = i * c
    din = H_LIN_D + H_LIN_T * 0.6
    hx = c / 2 - din
    hy = W / 2 - din
    rc = H_CORNER_R - H_LIN_T * 0.6
    ph = float(r.uniform(0, 100))
    cx, cy = x0 + c / 2, 0.0
    n_ = max(12, int(round(2 * hx / 0.03)))
    a = np.linspace(-1.0, 1.0, n_ + 1)
    A_, B_ = np.meshgrid(a, a)
    X = cx + A_ * hx
    Y = cy + B_ * hy
    # esquinas: los puntos que caen fuera del arco se proyectan sobre él
    qx, qy = np.abs(X - cx) - (hx - rc), np.abs(Y - cy) - (hy - rc)
    out = (qx > 0) & (qy > 0)
    d = np.hypot(qx, qy)
    k = np.where(out & (d > rc), rc / np.maximum(d, 1e-9), 1.0)
    X = np.where(out, cx + np.sign(X - cx) * (hx - rc + qx * k), X)
    Y = np.where(out, cy + np.sign(Y - cy) * (hy - rc + qy * k), Y)
    mound = float(r.uniform(0.03, 0.05)) * (c / 1.06) ** 0.5
    f1, f2, f3 = _sfield(r, 6, 4.0, 8.0), _sfield(r, 9, 18.0, 34.0), _sfield(r, 12, 55.0, 95.0)
    digs = [(cx + float(r.uniform(-0.3, 0.3)) * c, cy + float(r.uniform(-0.3, 0.3)) * W, float(r.uniform(0.06, 0.13)),
             float(r.uniform(0.006, 0.016))) for _ in range(int(r.integers(2, 5)))]

    def hgt(x, y):
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        ea = np.clip(1 - np.abs(x - cx) / hx, 0, 1)
        eb = np.clip(1 - np.abs(y - cy) / hy, 0, 1)
        e = np.minimum(ea, eb)                             # 0 en la orilla, 1 al centro
        edge = np.clip(e / 0.06, 0, 1) ** 0.6              # junto a la tela el relleno queda al nivel de llenado
        P = np.stack([x, y, np.full(np.shape(x), ph)], -1)
        z = (zf + mound * (1 - (1 - ea) ** 2) * (1 - (1 - eb) ** 2) + (0.014 * f1(P) + 0.0065 * f2(P)) * edge
             + 0.0028 * f3(P) * edge)
        for (gx, gy, gr, gd) in digs:
            z = z - gd * np.exp(-((x - gx) ** 2 + (y - gy) ** 2) / (gr * gr)) * edge
        return z
    Z = hgt(X, Y)
    nr = n_ + 1
    V = np.stack([X, Y, Z], -1).reshape(-1, 3)
    F = _grid_quads(nr, nr).tolist()
    # faldón: el contorno de la rejilla baja 6 cm dentro de la tela y se cierra abajo
    idx = np.arange(nr * nr).reshape(nr, nr)
    bnd = list(idx[0, :]) + list(idx[1:, -1]) + list(idx[-1, -2::-1]) + list(idx[-2:0:-1, 0])
    o = len(V)
    sk = V[bnd].copy()
    sk[:, 2] = zf - 0.06
    V = np.concatenate([V, sk], 0)
    nb = len(bnd)
    for j in range(nb):
        jj = (j + 1) % nb
        F.append([bnd[j], o + j, o + jj, bnd[jj]])
    F.append(list(range(o + nb - 1, o - 1, -1)))
    _np_faces(mb, V, F, "sand", soft=True)
    # terrones y piedras sobre la tapa (poliedros irregulares, medio hundidos)
    nst = int(r.integers(34, 48)) if c < 1.5 else int(r.integers(80, 110))
    ico = _rock_proto()
    for k in range(nst):
        px = cx + float(r.uniform(-0.88, 0.88)) * hx
        py = cy + float(r.uniform(-0.88, 0.88)) * hy
        pz = float(hgt(np.array([px]), np.array([py]))[0])
        stone = r.uniform() < 0.4
        size = float(r.uniform(0.008, 0.016) if r.uniform() < 0.6 else r.uniform(0.016, 0.04))
        if not stone:
            size *= 1.3
        S = np.array([size, size * float(r.uniform(0.6, 1.0)), size * float(r.uniform(0.35, 0.6) if not stone else r.uniform(0.5, 0.8))])
        Vr = ico[0] * S * (1 + 0.22 * r.uniform(-1, 1, (len(ico[0]), 1)))
        a_ = float(r.uniform(0, 2 * PI))
        Rz = np.array([[math.cos(a_), -math.sin(a_), 0], [math.sin(a_), math.cos(a_), 0], [0, 0, 1]])
        Vr = Vr @ Rz.T + np.array([px, py, pz + S[2] * 0.25])
        _np_faces(mb, Vr, ico[1], "concrete" if stone else "sand", soft=not stone)   # piedra angulosa; terrón redondo


_ROCK = None


def _rock_proto():
    """Icosaedro subdividido una vez (42 vértices, 80 caras) de radio 1: base de terrones y piedras."""
    global _ROCK
    if _ROCK is None:
        t_ = (1 + 5 ** 0.5) / 2
        V = [(-1, t_, 0), (1, t_, 0), (-1, -t_, 0), (1, -t_, 0), (0, -1, t_), (0, 1, t_), (0, -1, -t_), (0, 1, -t_),
             (t_, 0, -1), (t_, 0, 1), (-t_, 0, -1), (-t_, 0, 1)]
        F = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
             (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7),
             (9, 8, 1)]
        V = [np.array(v, float) / np.linalg.norm(v) for v in V]
        mid = {}

        def mp(a, b):
            k = (min(a, b), max(a, b))
            if k not in mid:
                p = V[a] + V[b]
                V.append(p / np.linalg.norm(p))
                mid[k] = len(V) - 1
            return mid[k]
        F2 = []
        for (a, b, c_) in F:
            ab, bc, ca = mp(a, b), mp(b, c_), mp(c_, a)
            F2 += [(a, ab, ca), (b, bc, ab), (c_, ca, bc), (ab, bc, ca)]
        _ROCK = (np.array(V), F2)
    return _ROCK


# ========================================================================================================== sacos
# Saco terrero de polipropileno tejido 14" × 26" (vacío 0,356 × 0,660 m; tubo tejido de ~0,71 m de contorno, fondo con
# dobladillo cosido, boca con cordón de amarre). Catálogos: webstaurantstore 14x26 (850-1450 denier, "hemmed top and
# double-stitched bottom", cordón pre-atado), sandbaggy.com (lleno: ~12" × 18" × 3,5-4"), NDSU AE-626 (colocado: ~4" de
# alto), práctica militar (FM 5-103 / Manitoba 1081: llenar 2/3-3/4, la boca se dobla debajo, hiladas cuatrapeadas de soga y
# tizón). Lleno a ~3/4 y asentado: ~0,48 × 0,30 × 0,11 m + dobladillo + cuello amarrado con la cola doblada debajo.
# La sección conserva el contorno de la tela (0,71 m): donde el saco se aplana hacia la costura se ensancha solo (las
# "orejas" de las esquinas del fondo), y hacia la boca el sobrante de tela se vuelve frunces que convergen al cuello.
BAG_P0 = 0.71         # contorno del tubo tejido (2 × 0,356 m)
BAG_NT = 38           # puntos por anillo (re-muestreados por longitud de arco; la base apoyada lleva menos)
BAG_NS = 36           # estaciones del cuerpo (más densas en los extremos)


def _sfield(r, n, kmin, kmax):
    """Campo suave pseudoaleatorio en 3D (suma de n senos de dirección y frecuencia al azar); f(P[..., 3]) ~ [-1, 1]."""
    K = r.normal(size=(n, 3))
    K /= np.linalg.norm(K, axis=1, keepdims=True)
    K *= r.uniform(kmin, kmax, (n, 1))
    ph = r.uniform(0.0, 2 * PI, n)
    a = 1.0 / math.sqrt(n * 0.5)
    return lambda P: np.sin(P @ K.T + ph).sum(-1) * a


def _sstep(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _bag_sections(b, c, zc, e_t, e_b, nt=BAG_NT, nd=192, wb=1.0):
    """Anillos de sección (estaciones × nt × (y, z)) re-muestreados por longitud de arco, empezando abajo al centro y
    girando hacia +y. Sección: superelipse por cuadrante (exponente e_t arriba, e_b abajo). wb < 1: la base (oculta,
    apoyada) recibe menos puntos que la tapa y los costados. Devuelve (anillos, contorno, ángulo de cada punto)."""
    t = np.linspace(-PI / 2, 1.5 * PI, nd, endpoint=False)
    ct, st = np.cos(t), np.sin(t)
    E = np.where(st[None, :] > 0, e_t[:, None], e_b[:, None])
    y = b[:, None] * np.sign(ct) * np.abs(ct) ** (2.0 / E)
    z = zc[:, None] + c[:, None] * np.sign(st) * np.abs(st) ** (2.0 / E)
    yy = np.concatenate([y, y[:, :1]], 1)
    zz = np.concatenate([z, z[:, :1]], 1)
    tt = np.concatenate([t, t[:1] + 2 * PI])
    sl = np.hypot(np.diff(yy, axis=1), np.diff(zz, axis=1))
    per = sl.sum(1)
    tm = (t + PI / nd)
    wgt = wb + (1 - wb) * np.clip((np.sin(tm) + 0.75) / 0.4, 0, 1)
    acc = np.concatenate([np.zeros((len(b), 1)), np.cumsum(sl * wgt[None, :], 1)], 1)
    out = np.zeros((len(b), nt, 2))
    ang = np.zeros((len(b), nt))
    for i in range(len(b)):
        q = acc[i, -1] * np.arange(nt) / nt
        out[i, :, 0] = np.interp(q, acc[i], yy[i])
        out[i, :, 1] = np.interp(q, acc[i], zz[i])
        ang[i] = np.interp(q, acc[i], tt)
    return out, per, ang


def _ring_normals(R):
    """Normales 2D (hacia afuera) de anillos cerrados R[..., nt, 2] (y, z) recorridos en sentido antihorario."""
    d = np.roll(R, -1, axis=-2) - np.roll(R, 1, axis=-2)
    n = np.stack([d[..., 1], -d[..., 0]], -1)
    return n / np.maximum(np.linalg.norm(n, axis=-1, keepdims=True), 1e-9)


def _bag_rings(r, ls=1.0, ws=1.0, hs=1.0, blunt=0.0, lod=0):
    """Geometría local de un saco lleno (largo en X: costura en -X, boca amarrada en +X; ancho en Y; base en z = 0).
    Devuelve dict: R (anillos × nt × 3, un solo tubo continuo: punta del dobladillo -> costura -> cuerpo -> cuello -> cola),
    nf (anillos del dobladillo), cord (eje del cordón de amarre), c0 (media altura), nt."""
    nt = BAG_NT if lod == 0 else 30
    ns = BAG_NS if lod == 0 else 28
    a = 0.236 * ls * float(r.uniform(0.975, 1.025))
    c0 = 0.055 * hs * float(r.uniform(0.94, 1.05))
    P0 = BAG_P0 * ws * float(r.uniform(0.985, 1.015))
    cs, rn = 0.0024, 0.0145 * float(r.uniform(0.9, 1.1))   # media altura en la costura; radio del cuello amarrado
    te = 0.15 - 0.05 * blunt                               # largo (fracción) del remate redondo de la costura
    sg = 0.68 + 0.1 * blunt + float(r.uniform(-0.03, 0.03))  # inicio del cuello (fracción)
    z_seam = 0.02 + 0.006 * blunt + float(r.uniform(-0.003, 0.003))
    z_neck = 0.036 + float(r.uniform(-0.004, 0.006))
    e_body_t = float(r.uniform(2.2, 2.5))                  # tapa abombada, algo aplanada por la carga
    e_body_b = 3.6                                         # base aplanada sobre el apoyo
    bend = float(r.uniform(-0.012, 0.012))                 # saco apenas curvo en planta
    tilt = float(r.uniform(-0.12, 0.12))                   # el relleno cargado hacia un costado
    # ---- estaciones del cuerpo (coseno + lineal: densas en los dos remates)
    u = np.linspace(0.0, 1.0, ns)
    s = 0.62 * (0.5 - 0.5 * np.cos(PI * u)) + 0.38 * u
    x = -a + 2 * a * s
    g0 = np.sqrt(np.clip(1 - (1 - np.clip(s / te, 0, 1)) ** 2, 0, 1))
    q = np.clip((s - sg) / (1 - sg), 0.0, 1.0)
    shoulder = (1 - q ** 2) ** 0.75
    c = np.maximum(cs, c0 * g0 * shoulder + rn * (1 - shoulder) * (s > sg))
    c[0] = cs
    ph1, ph2 = float(r.uniform(0, 6)), float(r.uniform(0, 6))
    c *= 1 + (0.045 * np.sin(PI * s * 2.0 + ph1) + 0.025 * np.sin(PI * s * 5.0 + ph2)) * g0
    # contorno: constante (tela tensa) hasta el cuello; ahí la tela sobrante se vuelve frunces
    Ps = np.where(s > sg, 2 * PI * rn + (P0 - 2 * PI * rn) * np.clip((c - rn) / (c0 - rn), 0, 1) ** 0.85, P0)
    Ps = Ps * (1 + 0.012 * np.sin(PI * s * 3.0 + ph2) * g0)
    e_t = 1.12 + (e_body_t - 1.12) * g0 ** 1.4
    e_b = 1.12 + (e_body_b - 1.12) * g0 ** 1.4
    e_t = e_t + (2.0 - e_t) * q ** 0.8
    e_b = e_b + (2.0 - e_b) * q ** 0.8
    zc = c + (z_seam - cs) * (1 - g0) ** 2 + (z_neck - rn) * q ** 1.6
    # ancho que conserva el contorno: dos medidas y una corrección
    b1 = np.full(ns, 0.10)
    b2 = np.full(ns, 0.20)
    _, p1, _ = _bag_sections(b1, c, zc, e_t, e_b, 4, 96)
    _, p2, _ = _bag_sections(b2, c, zc, e_t, e_b, 4, 96)
    b = b1 + (b2 - b1) * (Ps - p1) / (p2 - p1)
    _, p3, _ = _bag_sections(b, c, zc, e_t, e_b, 4, 96)
    b = np.maximum(b * Ps / p3, rn * 0.9)
    S2, _, TH = _bag_sections(b, c, zc, e_t, e_b, nt, 192, 0.42)
    Y, Z = S2[..., 0].copy(), S2[..., 1].copy()
    w = np.arange(nt) / nt                                 # parámetro del contorno (0 = abajo al centro)
    arc = (TH[-1] + PI / 2) / (2 * PI)                     # fracción angular de cada punto (cuello y cola)
    # carga: la tapa se ladea un poco hacia un costado
    top = np.clip((Z - zc[:, None]) / np.maximum(c[:, None], 1e-4), 0, 1)
    Z = Z + tilt * top * c[:, None] * Y / np.maximum(b[:, None], 1e-4) * 0.5
    Nn = _ring_normals(np.stack([Y, Z], -1))
    X = np.repeat(x[:, None], nt, 1)
    P = np.stack([X, Y, Z], -1)
    disp = np.zeros((ns, nt))
    # coordenada sobre la tela: (x, u) con u = longitud de arco del contorno (m), para arrugas que siguen la superficie
    Uc = np.concatenate([np.zeros((ns, 1)), np.cumsum(np.hypot(np.diff(Y, axis=1), np.diff(Z, axis=1)), 1)], 1)
    Uc = Uc - Uc[:, [nt // 2]]
    vis = np.clip((Nn[..., 1] + 0.6) / 0.45, 0, 1)         # tapa y costados (la base apoyada queda lisa)
    body = vis * np.clip(g0, 0.15, 1)[:, None]
    # terrones de arena: ondulación ancha (relleno desparejo) + bultos medianos
    lump1 = _sfield(r, 6, 9.0, 16.0)
    lump2 = _sfield(r, 9, 32.0, 60.0)
    disp += (0.0032 * lump1(P) + 0.0013 * lump2(P)) * body
    # pliegues de tela floja: crestas angostas en el plano de la tela, más hacia los remates y las esquinas
    ncr = int(r.integers(5, 9))
    for kc in range(ncr):
        x0 = float(r.uniform(-0.95, 0.85)) * a
        if r.uniform() < 0.5:                              # remates: arrugas cortas casi a lo largo, hacia la costura o el cuello
            x0 = float(r.choice([-1.0, 1.0])) * float(r.uniform(0.55, 0.92)) * a
        u0 = float(r.uniform(-0.3, 0.3))
        ang = math.radians(float(r.uniform(-50, 50)) + (90 if r.uniform() < 0.25 else 0))
        L_ = float(r.uniform(0.05, 0.16))
        wd = float(r.uniform(0.009, 0.016))
        A_ = float(r.uniform(0.0014, 0.003)) * (1 if r.uniform() < 0.7 else -1)
        dx, du = math.cos(ang), math.sin(ang)
        rx, ru = X - x0, Uc - u0
        tt = np.clip(rx * dx + ru * du, -L_ / 2, L_ / 2)
        d = np.hypot(rx - tt * dx, ru - tt * du)
        prof = np.clip(1 - d / wd, 0, 1) ** 1.6 * np.clip(np.cos(PI * tt / L_), 0, 1) ** 0.6
        disp += A_ * prof * vis
    # orejas de la costura: arrugas que salen de cada esquina del fondo hacia el lomo (tela que se tensa al llenarse)
    for sgn_u in (-1.0, 1.0):
        ue = sgn_u * P0 / 4 * 0.98
        for kc in range(int(r.integers(2, 4))):
            ang = math.radians(float(r.uniform(15, 55))) * -sgn_u
            L_ = float(r.uniform(0.04, 0.09))
            wd = float(r.uniform(0.008, 0.013))
            A_ = float(r.uniform(0.0015, 0.0028))
            dx, du = math.cos(ang), math.sin(ang)
            rx, ru = X - (-a + 0.004), Uc - ue
            tt = np.clip(rx * dx + ru * du, 0.0, L_)
            d = np.hypot(rx - tt * dx, ru - tt * du)
            disp += A_ * np.clip(1 - d / wd, 0, 1) ** 1.6 * (1 - tt / L_) ** 0.8 * (s > 0)[:, None]
    # frunces del cuello: crestas agudas (cúspide afuera) que convergen al amarre; la tela sobrante (P0 - contorno) se
    # reparte en n pliegues; sus colas siguen como arrugas sobre el lomo del saco
    npl = int(r.integers(8, 11))
    phj = float(r.uniform(0, 2 * PI))
    jit = 0.035 * np.sin(2 * PI * 2 * w + phj) + 0.02 * np.sin(2 * PI * 3 * w + 1.7 * phj)
    pleat = 1 - 2 * np.abs(np.sin(PI * npl * (w + jit))) ** 0.7
    pa = (0.7 + 0.6 * np.abs(np.sin(PI * npl * 0.5 * (w + jit) + phj)))  # pliegues desiguales
    excess = np.clip(P0 - Ps, 0, None) / (2 * npl)
    hp = np.minimum(np.minimum(0.45 * excess + 0.0022 * _sstep(sg - 0.26, sg, s), 0.42 * c), 0.0085)
    hp *= 1 - _sstep(0.975, 1.0, s)
    disp += hp[:, None] * (pleat * pa)[None, :] * (0.7 + 0.3 * vis)
    # frunce de la costura: ondas cortas perpendiculares al dobladillo
    pk = np.sin(2 * PI * 13 * w + float(r.uniform(0, 6)) + 0.8 * np.sin(2 * PI * 3 * w))
    disp += 0.0018 * pk[None, :] * np.clip(1 - s / 0.085, 0, 1)[:, None] * (s > 0)[:, None]
    P[..., 1] += Nn[..., 0] * disp
    P[..., 2] += Nn[..., 1] * disp
    P[..., 2] = np.maximum(P[..., 2], 0.0)                 # la base apoyada no se hunde
    # dobladillo cosido (2 capas + doblez): sale 15 mm de la costura, cae hacia el piso; ranura de las puntadas a 6 mm
    R0 = P[0].copy()
    flap = []
    wav = float(r.uniform(0, 6))
    for (dd, k_) in ((0.0035, 1.0), (0.0058, 0.62), (0.0078, 1.0), (0.0122, 0.95), (0.0148, 0.55)):
        F = R0.copy()
        F[:, 0] -= dd * (1 + 0.12 * np.sin(F[:, 1] * 31 + wav)) + 0.0012 * np.sin(F[:, 1] * 57 + 2 * wav)
        F[:, 1] *= 1.0 - 0.012 * dd / 0.015
        F[:, 2] = z_seam + (R0[:, 2] - z_seam) * (0.0016 / cs) * k_ - dd * (0.45 + 0.35 * blunt) \
            - 0.0025 * dd / 0.015 * np.sin(F[:, 1] * 23 + wav)
        F[:, 2] = np.maximum(F[:, 2], 0.0009)
        flap.append(F)
    flap = flap[::-1]
    # cuello amarrado: tubo corto de tela fruncida (radio rn) y la cola que se dobla hacia abajo y hacia atrás
    xn = x[-1]
    th = -PI / 2 + 2 * PI * arc
    neck = []
    for dx_ in (0.004, 0.009):
        rr = rn * (1 + 0.1 * pleat)
        neck.append(np.stack([np.full(nt, xn + dx_), rr * np.cos(th), z_neck + rr * np.sin(th)], -1))
    tl = float(r.uniform(0.85, 1.15)) * (0.75 if blunt > 0.5 else 1.0)
    fr = 0.7 if blunt > 0.5 else 1.0                       # en un muro la cola va más pegada a la cabeza
    path = np.array([(xn + 0.012, 0.0, z_neck), (xn + 0.022 * fr + 0.002, 0.0, z_neck - 0.004),
                     (xn + 0.03 * fr, 0.0, z_neck - 0.015), (xn + 0.028 * fr, 0.0, 0.4 * z_neck + 0.006),
                     (xn + 0.014 * fr, 0.0, 0.0084), (xn - 0.016 * tl, 0.0, 0.0058), (xn - 0.058 * tl, 0.0, 0.005)])
    wid = np.array([1.05, 1.35, 1.8, 2.3, 2.8, 3.05, 3.05]) * rn
    thk = np.array([0.95, 0.75, 0.5, 0.36, 0.3, 0.26, 0.22]) * rn
    tail = []
    Tg = np.gradient(path, axis=0)
    Tg /= np.linalg.norm(Tg, axis=1, keepdims=True)
    for i in range(len(path)):
        Ny = np.array([0.0, 1.0, 0.0])
        Bz = np.cross(Tg[i], Ny)
        Bz /= np.linalg.norm(Bz)
        pl = 1 + 0.22 * pleat * (1 - i / len(path) * 0.5)
        sec = (np.outer(np.cos(th) * wid[i] * pl, Ny) + np.outer(np.sin(th) * thk[i] * (1 + 0.5 * (pleat + 1) * 0.5), Bz))
        tail.append(path[i] + sec)
    R = np.concatenate([np.array(flap), P, np.array(neck), np.array(tail)], 0)
    R[..., 1] += bend * (1 - np.clip(R[..., 0] / a, -1, 1) ** 2)   # planta un poco curva
    nf = len(flap)
    # cordón de amarre (PP de 3 mm): 1,3 vueltas en hélice sobre el cuello y dos puntas cortas que cuelgan
    rc = rn * 1.1 + 0.0017
    ang = np.linspace(0.0, 2 * PI * 1.3, 19) + float(r.uniform(0, 2 * PI))
    cx_ = xn + 0.0035 + 0.0045 * np.linspace(0, 1, 19)
    cord = [np.stack([cx_, rc * np.cos(ang), z_neck + rc * np.sin(ang)], -1)]
    for k_, sgn in ((0, -1), (-1, 1)):
        p0 = cord[0][k_]
        d0 = np.array([0.0, math.cos(ang[k_]) * 0.5, -1.0])
        d0 /= np.linalg.norm(d0)
        e = [p0 + np.array([sgn * 0.002 * j, 0.0, 0.0]) + d0 * 0.009 * j + np.array([0, 0, 0.0004 * j * j]) for j in range(1, 4)]
        cord.append(np.array([p0] + e) if k_ == -1 else np.array(e[::-1] + [p0]))
    cord = np.concatenate([cord[1][:-1], cord[0], cord[2][1:]], 0)
    cord[..., 1] += bend * (1 - np.clip(cord[..., 0] / a, -1, 1) ** 2)
    cord[:, 2] = np.maximum(cord[:, 2], 0.0016)
    return dict(R=R, nf=nf, cord=cord, c0=c0, nt=nt)


def _bag_build(mb, rings, M=None, zfun=None, fr=None):
    """Malla del saco: un solo tubo de anillos (tapas en abanico en la punta del dobladillo y en la orilla de la cola) +
    cordón de amarre (12 lados, sombreado continuo). M coloca el saco; zfun(X, Y, f) -> desplazamiento z vectorizado
    (asiento sobre la hilada de abajo; f = fracción de altura del vértice). Devuelve los vértices puestos (N × 3)."""
    R = rings["R"]
    nr, nt = R.shape[0], R.shape[1]
    caps = np.array([R[0].mean(0), R[-1].mean(0)])
    cord = rings["cord"]
    # cordón como tubo de 12 lados (transporte paralelo)
    seg = 12
    T = np.gradient(cord, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    Nv = np.cross(T[0], [0.0, 0.0, 1.0] if abs(T[0][2]) < 0.9 else [1.0, 0.0, 0.0])
    Nv /= np.linalg.norm(Nv)
    ring_c = []
    an = 2 * PI * np.arange(seg) / seg
    for i in range(len(cord)):
        Nv = Nv - T[i] * Nv.dot(T[i])
        Nv /= np.linalg.norm(Nv)
        Bv = np.cross(T[i], Nv)
        ring_c.append(cord[i] + 0.0015 * (np.outer(np.cos(an), Nv) + np.outer(np.sin(an), Bv)))
    C = np.array(ring_c)
    allp = np.concatenate([R.reshape(-1, 3), caps, C.reshape(-1, 3), cord[[0, -1]]], 0)
    loc_z = allp[:, 2].copy()
    if M is not None:
        Mn = np.array(M)
        allp = allp @ Mn[:3, :3].T + Mn[:3, 3]
    if zfun is not None:
        f = np.clip(loc_z / (2 * rings["c0"]), 0.0, 1.0)
        allp[:, 2] += zfun(allp[:, 0], allp[:, 1], f)
    bm = mb.bm
    V = [bm.verts.new(p) for p in allp.tolist()]
    mi = mb.mi("sandbag")
    sl = mb._soft_layer()
    nf = rings["nf"]

    def q(i, k):
        return V[i * nt + k]
    for i in range(nr - 1):
        hard = i < nf                                      # dobladillo y costura: aristas reales
        for k in range(nt):
            kk = (k + 1) % nt
            f_ = bm.faces.new((q(i, k), q(i, kk), q(i + 1, kk), q(i + 1, k)))
            f_.material_index = mi
            f_.smooth = True
            if not hard:
                f_[sl] = 1
    c0v, c1v = V[nr * nt], V[nr * nt + 1]
    for k in range(nt):
        kk = (k + 1) % nt
        for (cv, i, sft) in ((c0v, 0, 0), (c1v, nr - 1, 1)):
            f_ = bm.faces.new((cv, q(i, kk), q(i, k)) if i == 0 else (cv, q(i, k), q(i, kk)))
            f_.material_index = mi
            f_.smooth = True
            f_[sl] = sft
    o = nr * nt + 2
    ncs = len(cord)
    for i in range(ncs - 1):
        for k in range(seg):
            kk = (k + 1) % seg
            f_ = bm.faces.new((V[o + i * seg + k], V[o + i * seg + kk], V[o + (i + 1) * seg + kk], V[o + (i + 1) * seg + k]))
            f_.material_index = mi
            f_.smooth = True
            f_[sl] = 1
    e0, e1 = V[o + ncs * seg], V[o + ncs * seg + 1]
    for k in range(seg):
        kk = (k + 1) % seg
        for (cv, i, rev) in ((e0, 0, True), (e1, ncs - 1, False)):
            tri = (cv, V[o + i * seg + kk], V[o + i * seg + k])
            f_ = bm.faces.new(tri if rev else tri[::-1])
            f_.material_index = mi
            f_.smooth = True
            f_[sl] = 1
    return allp


def sandbag(seed=0):
    """Saco terrero suelto, lleno a ~3/4 (~0,48 × 0,30 × 0,11 m + dobladillo y cola): polipropileno tejido como un solo
    tubo de tela de contorno constante (0,71 m), tapa aplastada por la carga y costados redondos, remate de almohada hacia
    la costura con las orejas de las esquinas, dobladillo cosido de 15 mm con la ranura de las puntadas y el frunce de la
    costura, terrones y pliegues de tela floja, boca con frunces agudos que convergen al cuello, cordón de amarre de 3 mm
    con sus puntas y la cola doblada hacia abajo y metida bajo la cabeza. Origen: centro de la base, largo en X (costura en
    -X). ~3,5 k tris."""
    r = rng(seed)
    mb = MB()
    _bag_build(mb, _bag_rings(r))
    return mb


class _HField:
    """Campo de alturas (máximo de las tapas de los sacos ya puestos) para asentar cada hilada sobre la anterior."""

    def __init__(self, x0, x1, y0, y1, h=0.01):
        self.x0, self.y0, self.h = x0, y0, h
        self.nx = int(math.ceil((x1 - x0) / h)) + 1
        self.ny = int(math.ceil((y1 - y0) / h)) + 1
        self.H = np.zeros((self.ny, self.nx))

    def splat(self, P):
        """Levanta H con los vértices P (N × 3) de los sacos de la hilada (malla densa: paso <= 2 cm)."""
        ix = np.clip(np.floor((P[:, 0] - self.x0) / self.h + 0.5).astype(int), 0, self.nx - 1)
        iy = np.clip(np.floor((P[:, 1] - self.y0) / self.h + 0.5).astype(int), 0, self.ny - 1)
        np.maximum.at(self.H, (iy, ix), P[:, 2])

    def filtered(self, rmax=2, sigma=6):
        """(S1, S2): máximo local (radio rmax celdas, cubre los huecos entre vértices) desenfocado y nunca debajo de H; y su
        versión muy desenfocada (gaussiana sigma celdas) para la tapa."""
        H = self.H
        S1 = H.copy()
        M1 = H.copy()                                      # máximo 3 × 3: cubre las caras entre vértices vecinos
        for dj in range(-rmax, rmax + 1):
            for di in range(-rmax, rmax + 1):
                if di * di + dj * dj <= rmax * rmax:
                    S1 = np.maximum(S1, np.roll(np.roll(H, dj, 0), di, 1))
                if abs(di) <= 1 and abs(dj) <= 1:
                    M1 = np.maximum(M1, np.roll(np.roll(H, dj, 0), di, 1))

        def blur(A, sg):
            k = np.exp(-0.5 * (np.arange(-3 * sg, 3 * sg + 1) / sg) ** 2)
            k /= k.sum()
            B = np.apply_along_axis(lambda v: np.convolve(np.pad(v, 3 * sg, mode="edge"), k, "valid"), 1, A)
            return np.apply_along_axis(lambda v: np.convolve(np.pad(v, 3 * sg, mode="edge"), k, "valid"), 0, B)
        S1 = np.maximum(blur(S1, 2), M1)
        return S1, blur(S1, sigma)

    def sample(self, A, x, y):
        fx = np.clip((np.asarray(x) - self.x0) / self.h, 0.0, self.nx - 1.001)
        fy = np.clip((np.asarray(y) - self.y0) / self.h, 0.0, self.ny - 1.001)
        i, j = fx.astype(int), fy.astype(int)
        tx, ty = fx - i, fy - j
        return (A[j, i] * (1 - tx) * (1 - ty) + A[j, i + 1] * tx * (1 - ty) + A[j + 1, i] * (1 - tx) * ty
                + A[j + 1, i + 1] * tx * ty)


def _bend_ring_xy(R, Rb):
    """Curva un saco en planta para seguir un muro circular de radio Rb (eje del muro en y = 0, centro hacia +y): la cara
    interior queda más corta que la exterior, como cuando el saco se asienta en el anillo."""
    x, y = R[..., 0], R[..., 1]
    rho = Rb - y
    phi = x / Rb
    R = R.copy()
    R[..., 0] = rho * np.sin(phi)
    R[..., 1] = Rb - rho * np.cos(phi)
    return R


def _bag_stack(courses, seed, bounds, hs_course=None, lod=0):
    """Apila hiladas de sacos: courses = [[(x, y, ángulo°, escala_largo, escala_ancho[, radio_de_curva]), ...], ...] de abajo
    hacia arriba. Cada saco se asienta sobre los de la hilada anterior (campo de alturas: la base sigue los lomos y se hunde
    en las juntas, la tapa sigue un promedio suave) sin interpenetrarse; cada saco es distinto (semilla propia)."""
    r = rng(seed)
    mb = MB()
    hf = _HField(*bounds)
    nc = len(courses)
    for ci, course in enumerate(courses):
        S1, S2 = hf.filtered()
        if ci:                                             # 1,2 mm de holgura: apoyado a la vista, sin caras coplanares
            S1 = S1 + 0.0012
            S2 = S2 + 0.0012
        placed = []
        for item in course:
            x, y, ang, ls, ws = item[:5]
            rb = rng(int(r.integers(1 << 30)))
            hs = 1.0 - 0.07 * (nc - 1 - ci) / max(nc - 1, 1)     # las hiladas de abajo cargan más: más aplastadas
            rings = _bag_rings(rb, ls, ws, hs, blunt=1.0, lod=lod)
            if len(item) > 5 and item[5]:
                rings["R"] = _bend_ring_xy(rings["R"], item[5])
                rings["cord"] = _bend_ring_xy(rings["cord"], item[5])
            M = _T(x, y, 0.0) @ _Rz(ang + float(rb.uniform(-2.0, 2.0)))

            def zf(px, py, f, S1=S1, S2=S2):
                # el saco puentea las juntas (la arena no fluye hasta el fondo del canal entre dos lomos): la base sigue
                # el apoyo pero no se hunde más de 3 cm bajo el plano medio; la tapa sigue sobre todo ese plano
                s1 = hf.sample(S1, px, py)
                s2 = hf.sample(S2, px, py)
                lo = f < 0.25
                if lo.sum() > 8:
                    A_ = np.stack([px[lo], py[lo], np.ones(lo.sum())], 1)
                    cf = np.linalg.lstsq(A_, np.maximum(s1[lo], np.percentile(s1[lo], 35)), rcond=None)[0]
                    pl = cf[0] * px + cf[1] * py + cf[2]
                    pl = np.maximum(pl, np.percentile(s1[lo], 60) - 0.012)
                else:
                    pl = s2
                bot = np.maximum(s1, pl - 0.03)
                top = np.maximum(pl + 0.3 * (s2 - pl), bot - 0.016)
                w_ = f ** 0.7
                return bot * (1 - w_) + top * w_
            placed.append(_bag_build(mb, rings, M, zf))
        for P in placed:
            hf.splat(P)
    return mb


def sandbag_wall(L=3.0, rows=4, seed=0, thickness="single"):
    """Muro de sacos terreros de L m a lo largo de +X desde x = 0, centrado en y = 0, `rows` hiladas cuatrapeadas (junta a
    medio saco; medios sacos en los extremos para rematar a plomo). single: todas a soga (espesor ~0,30 m); double: hiladas de
    soga doble (dos filas) alternadas con hiladas de tizón (sacos atravesados, ~0,55 m), como indica FM 5-103."""
    r = rng(seed)
    pitch = 0.515
    courses = []
    for k in range(rows):
        row = []
        if thickness == "double" and k % 2 == 1:           # hilada de tizón: sacos atravesados
            n = max(1, int(round(L / 0.315)))
            p = L / n
            for i in range(n):
                row.append((p * (i + 0.5), 0.0, 90.0 + (180.0 if (i + k) % 2 else 0.0), 1.15, 0.97 * p / 0.315))
        else:
            ys = (-0.14, 0.14) if thickness == "double" else (0.0,)
            off = (k // (2 if thickness == "double" else 1)) % 2
            n = max(1, int(round(L / pitch)))
            p = L / n
            for y in ys:
                segs = [(p * i, p * (i + 1)) for i in range(n)]
                if off:
                    segs = [(0.0, p / 2)] + [(p * (i + 0.5), p * (i + 1.5)) for i in range(n - 1)] + [(L - p / 2, L)]
                for (u0, u1) in segs:
                    ls = (u1 - u0) / pitch
                    flip = 180.0 if r.uniform() < 0.5 else 0.0
                    row.append(((u0 + u1) / 2, y + float(r.uniform(-0.012, 0.012)), flip, ls * 0.985,
                                0.9 if thickness == "double" else 1.0))
        courses.append(row)
    return _bag_stack(courses, seed, (-0.4, L + 0.4, -0.5, 0.5))


def sandbag_ring(radius=1.1, rows=3, seed=0, opening_deg=50.0):
    """Anillo de sacos (puesto de tirador / protección de un equipo): sacos a soga tangentes a un círculo de `radius` m
    (eje del muro), curvados en planta para seguirlo (la cara interior más corta), hiladas cuatrapeadas, con una entrada de
    `opening_deg` grados hacia -Y. Origen: centro, en el piso."""
    courses = []
    pitch = 0.515
    rf = rng(seed + 77)
    for k in range(rows):
        arc0 = -PI / 2 + math.radians(opening_deg) / 2
        arc = 2 * PI - math.radians(opening_deg)
        n = max(3, int(round(arc * radius / pitch)))
        da = arc / n
        ls = da * radius / pitch * 0.985
        row = []
        off = 0.5 * (k % 2)
        idx = [i + off for i in range(n)] if not off else [i + off for i in range(n - 1)]
        for t in idx:
            a = arc0 + da * (t + 0.5)
            fl = rf.uniform() < 0.5                        # boca hacia uno u otro lado (el saco se curva igual)
            row.append((radius * math.cos(a), radius * math.sin(a), math.degrees(a) + (270.0 if fl else 90.0), ls, 1.0,
                        -radius if fl else radius))
        if off:                                            # medios sacos en las cabezas de la entrada
            for t in (0.25, n - 0.25):
                a = arc0 + da * t
                row.append((radius * math.cos(a), radius * math.sin(a), math.degrees(a) + 90.0, 0.5 * ls, 1.0, radius))
        courses.append(row)
    R = radius + 0.5
    return _bag_stack(courses, seed, (-R, R, -R, R))


# ================================================================================================ barreras de concreto
def _rpoly(corners, radii, spacing, nseg=4):
    """Polígono 2D cerrado (y, z) con esquinas de radio real y lados densificados. corners: vértices antihorarios; radii[k]
    (0 = sin redondeo); spacing[k] = paso máximo del lado k -> k+1 (None = sin puntos intermedios). Devuelve (pts N × 2,
    tags) con tag = ('c', k, t) para puntos del arco de la esquina k (t de 0 a 1) o ('e', k, i) para puntos del lado k."""
    C = [np.array(p, float) for p in corners]
    n = len(C)
    arcs = []
    for k in range(n):
        p, a, b = C[k], C[k - 1], C[(k + 1) % n]
        d0 = (a - p) / np.linalg.norm(a - p)
        d1 = (b - p) / np.linalg.norm(b - p)
        th = math.acos(max(-1.0, min(1.0, float(d0 @ d1))))
        rr = radii[k]
        if rr <= 0 or th > PI - 1e-3:
            arcs.append([p])
            continue
        t = rr / math.tan(th / 2)
        t = min(t, 0.45 * np.linalg.norm(a - p), 0.45 * np.linalg.norm(b - p))
        rr = t * math.tan(th / 2)
        bis = (d0 + d1) / np.linalg.norm(d0 + d1)
        ctr = p + bis * (rr / math.sin(th / 2))
        pa, pb = p + d0 * t, p + d1 * t
        a0 = math.atan2(pa[1] - ctr[1], pa[0] - ctr[0])
        a1 = math.atan2(pb[1] - ctr[1], pb[0] - ctr[0])
        da = (a1 - a0 + PI) % (2 * PI) - PI
        arcs.append([ctr + rr * np.array((math.cos(a0 + da * j / nseg), math.sin(a0 + da * j / nseg))) for j in range(nseg + 1)])
    pts, tags = [], []
    for k in range(n):
        A = arcs[k]
        for j, q in enumerate(A):
            pts.append(q)
            tags.append(("c", k, j / max(len(A) - 1, 1)))
        B0, B1 = A[-1], arcs[(k + 1) % n][0]
        sp = spacing[k]
        if sp:
            m = max(1, int(math.ceil(np.linalg.norm(B1 - B0) / sp)))
            for i in range(1, m):
                pts.append(B0 + (B1 - B0) * i / m)
                tags.append(("e", k, i))
    return np.array(pts), tags


def _loop_normals2(P, reach=0.0):
    """Normales hacia afuera de un lazo 2D antihorario. reach > 0: cada normal sale de los puntos que quedan a esa
    distancia (por longitud de arco) antes y después, así los detalles diminutos (rebabas) no la tuercen."""
    if reach <= 0:
        d = np.roll(P, -1, 0) - np.roll(P, 1, 0)
    else:
        n_ = len(P)
        seg = np.linalg.norm(np.roll(P, -1, 0) - P, axis=1)
        acc = np.concatenate([[0.0], np.cumsum(seg)])
        tot = acc[-1]
        a = acc[:-1]
        fx = np.concatenate([P[:, 0], P[:1, 0]])
        fy = np.concatenate([P[:, 1], P[:1, 1]])
        pa = (a - reach) % tot
        pb = (a + reach) % tot
        A = np.stack([np.interp(pa, acc, fx), np.interp(pa, acc, fy)], 1)
        B = np.stack([np.interp(pb, acc, fx), np.interp(pb, acc, fy)], 1)
        d = B - A
        del n_
    n = np.stack([d[:, 1], -d[:, 0]], 1)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def _cast_piece(mb, prof, tags, xs, L, r_end, mat="concrete", chips=(), end_chips=(), notches=(), recesses=(),
                wave=0.0009, seed=0):
    """Pieza de concreto colado extruida a lo largo de X (0..L) con el perfil redondeado `prof` (antihorario en (y, z)):
    - cantos verticales de los extremos redondeados (radio r_end: el perfil se encoge en 4 estaciones de arco);
    - despostilladuras: chips = [(índice_de_esquina, x, ancho, hondo)] en cantos longitudinales; end_chips = [(extremo 0|1,
      z, alto, hondo, lado ±1)] en los cantos verticales de los extremos;
    - muescas por debajo (ranuras de izaje / drenaje): notches = [(x0, x1, alto)];
    - huecos: recesses = [(x, índice de punto del perfil, radio, hondo, radio_fondo)] (conos de tirante, cajas de izaje):
      el nodo (estación, punto) debe existir; se arma el hueco con su pared cónica y su fondo;
    - ondulación de cimbra de ±wave en las caras (nada queda perfectamente plano). Tapas de los extremos trianguladas."""
    r = rng(seed)
    N2 = _loop_normals2(prof, reach=0.012)
    npf = len(prof)
    # estaciones: arco de los extremos + interiores
    ends = [(r_end * (1 - math.cos(f)), r_end * (1 - math.sin(f))) for f in np.linspace(0, PI / 2, 4)]
    st = [(x, d, 0) for (x, d) in ends] + [(L - x, d, 1) for (x, d) in ends]
    st += [(x, 0.0, -1) for x in xs if r_end + 0.004 < x < L - r_end - 0.004]
    st.sort(key=lambda s: s[0])
    X = np.array([s[0] for s in st])
    ph = float(r.uniform(0, 50))
    V = np.zeros((len(st), npf, 3))
    zmax = prof[:, 1].max()
    for i, (x, d, side) in enumerate(st):
        P = prof.copy()
        dd = np.full(npf, d)
        for (e, zc, hz, dep, sd) in end_chips:             # despostilladura en el canto vertical de un extremo
            if side == e:
                sel = (np.sign(prof[:, 0]) == sd) | (sd == 0)
                dd = dd + dep * np.exp(-((prof[:, 1] - zc) / hz) ** 2) * sel * (d / max(r_end, 1e-6))
        P = P - N2 * dd[:, None]
        for (k, xc, w, dep) in chips:                       # despostilladura en un canto longitudinal
            g = math.exp(-((x - xc) / w) ** 2)
            if g < 0.02:
                continue
            for j, tg in enumerate(tags):
                if tg[0] == "c" and tg[1] == k:
                    P[j] = P[j] - N2[j] * dep * g * (0.35 + 0.65 * math.sin(PI * tg[2]))
        for (x0, x1, hz) in notches:                        # muesca abierta abajo: los puntos bajos suben al techo
            if x0 - 1e-6 <= x <= x1 + 1e-6:
                low = np.where(prof[:, 1] < hz)[0]
                for sgn in (1, -1):
                    ids = [j for j in low if np.sign(prof[j, 0]) == sgn or (prof[j, 0] == 0 and sgn == 1)]
                    if not ids:
                        continue
                    # ancho del perfil a la altura hz (interpolado sobre el lado)
                    side_pts = prof[np.sign(prof[:, 0]) == sgn]
                    yw = float(np.interp(hz, *zip(*sorted((p[1], abs(p[0])) for p in side_pts))))
                    ids.sort(key=lambda j: prof[j, 1] + 1e-3 * (-abs(prof[j, 0])))
                    m = len(ids)
                    for q, j in enumerate(ids):
                        P[j] = (sgn * (yw - 0.004 - 0.05 * (1 - (q + 1) / m)), hz + 0.0015 * (q + 1) / m)
        wv = wave * np.sin(x * 7.3 + prof[:, 1] * 5.1 + ph) * np.sin(x * 2.9 - prof[:, 1] * 3.7 + 2 * ph)
        wv = wv * (prof[:, 1] > 0.01)
        P = P + N2 * wv[:, None]
        V[i, :, 0] = x
        V[i, :, 1] = P[:, 0]
        V[i, :, 2] = P[:, 1]
    V[..., 2] = np.maximum(V[..., 2], 0.0)
    bm = mb.bm
    VV = [[bm.verts.new(p) for p in row] for row in V.tolist()]
    mi = mb.mi(mat)
    skip = set()
    rec_specs = []
    for (xr, j, rad, dep, rad2) in recesses:
        i = int(np.argmin(np.abs(X - xr)))
        rec_specs.append((i, j, rad, dep, rad2))
        for (a_, b_) in ((i - 1, j - 1), (i, j - 1), (i - 1, j), (i, j)):
            skip.add((a_, b_ % npf))
    for i in range(len(st) - 1):
        for j in range(npf):
            if (i, j) in skip:
                continue
            jj = (j + 1) % npf
            f = bm.faces.new((VV[i][j], VV[i + 1][j], VV[i + 1][jj], VV[i][jj]))
            f.material_index = mi
            f.smooth = True
    for row, rev in ((VV[0], True), (VV[-1], False)):
        ngon(mb, list(reversed(row)) if rev else list(row), mat)
    # huecos (cono de tirante / caja de izaje)
    out = []
    for (i, j, rad, dep, rad2) in rec_specs:
        c = VV[i][j].co.copy()
        ex = Vector((1, 0, 0))
        ey = (VV[i][(j + 1) % npf].co - VV[i][j - 1].co).normalized()
        nrm = ex.cross(ey).normalized()
        if nrm.dot(Vector((0.0, N2[j][0], N2[j][1]))) < 0:
            nrm = -nrm
        bnd = [VV[i - 1][j - 1], VV[i][j - 1], VV[i + 1][j - 1], VV[i + 1][j], VV[i + 1][(j + 1) % npf],
               VV[i][(j + 1) % npf], VV[i - 1][(j + 1) % npf], VV[i - 1][j]]
        ns_ = 16
        ang = [math.radians(225 + 22.5 * m) for m in range(ns_)]
        circ = [bm.verts.new(c + (ex * math.cos(a) + ey * math.sin(a)) * rad) for a in ang]
        for q in range(4):
            ch = [bnd[2 * q], bnd[2 * q + 1], bnd[(2 * q + 2) % 8]]
            arc = [circ[(4 * q + m) % ns_] for m in range(5)]
            zip_chains(mb, ch, arc, mat)
        rings = [circ]
        for (fd, fr) in ((0.003, rad * 0.97), (dep, rad2)):
            rings.append([bm.verts.new(c - nrm * fd + (ex * math.cos(a) + ey * math.sin(a)) * fr) for a in ang])
        for A_, B_ in zip(rings[:-1], rings[1:]):
            for m in range(ns_):
                mm = (m + 1) % ns_
                f = bm.faces.new((A_[m], A_[mm], B_[mm], B_[m]))
                f.material_index = mi
                f.smooth = True
        cb = bm.verts.new(c - nrm * dep)
        for m in range(ns_):
            f = bm.faces.new((rings[-1][m], rings[-1][(m + 1) % ns_], cb))
            f.material_index = mi
            f.smooth = True
        bm.verts.remove(VV[i][j])
        out.append((c, nrm, ex, ey))
    return out


def t_wall(seed=0):
    """Muro T (T-wall / tipo Alaska) de concreto precolado: 3,66 m (12 ft) de alto, segmento de 1,52 m (5 ft) a lo largo de +X
    desde x = 0, base en T invertida de 1,37 m (4,5 ft) de fondo centrada en y = 0 (frente en -Y). Alma ahusada 0,31 -> 0,20 m,
    acartelamiento de la base a 22° con transición curva (R 70 mm) al alma; cantos redondeados de colado (R 12-18 mm) y cantos
    verticales de los extremos (R 9 mm); dos rebabas de junta de cimbra (1,5 mm) a lo ancho de cada cara del alma; seis conos
    de tirante de cimbra resanados por cara (Ø 32 mm); dos cajas de izaje en la corona con su asa de varilla de 7/8" en U
    ahogada; ondulación de cimbra de ±0,9 mm; despostilladuras chicas en cantos y extremos (pieza limpia, en servicio).
    Fuentes: globalsecurity.org (2007: "T barrier ... 12 feet high ... four and a half feet wide ... ~10,000 lb"); 48barriers.com
    (T-wall: módulos autoportantes de concreto precolado); peso del modelo ~2,0 m³ × 2400 kg/m³ = 4,8 t."""
    r = rng(seed)
    mb = MB()
    L, H = 1.52, 3.66
    hb, hy = 0.685, 0.20
    yC, zC = 0.155, 0.42                                   # arranque del alma (fin del acartelamiento)
    yD = 0.10                                              # paño del alma en la corona
    stem = lambda z: yC + (yD - yC) * (z - zC) / (H - zC)  # noqa: E731
    flash = [1.22 + float(r.uniform(-0.01, 0.01)), 2.44 + float(r.uniform(-0.01, 0.01))]
    # lado derecho (y > 0) de abajo hacia arriba, con las rebabas de cimbra como esquinas sin redondeo
    right = [(hb, 0.0, 0.012, None), (hb, hy, 0.018, 0.13), (yC, zC, 0.07, 0.1)]
    for zf in flash:
        right += [(stem(zf - 0.003), zf - 0.003, 0.0, None), (stem(zf - 0.0015) + 0.0015, zf - 0.0015, 0.0, None),
                  (stem(zf + 0.0015) + 0.0015, zf + 0.0015, 0.0, None), (stem(zf + 0.003), zf + 0.003, 0.0, 0.1)]
    right += [(yD, H, 0.016, 0.045)]
    left = [(-y, z, rr, None) for (y, z, rr, sp) in reversed(right)]
    # espaciado del lado izquierdo: el del tramo simétrico
    sps = [sp for (_, _, _, sp) in right]
    for k in range(len(left) - 1):
        left[k] = (left[k][0], left[k][1], left[k][2], sps[len(right) - 2 - k])
    corners = right + [(0.0, H, 0.0, 0.045)] + left
    prof, tags = _rpoly([(y, z) for (y, z, _, _) in corners], [c[2] for c in corners], [c[3] for c in corners], nseg=4)
    # nodos para huecos: puntos del perfil sobre el alma a ~1,0 / 2,0 / 3,0 m y el centro de la corona
    def node(y_sign, z):
        cand = [j for j in range(len(prof)) if np.sign(prof[j, 0]) == y_sign and tags[j][0] == "e"]
        return min(cand, key=lambda j: abs(prof[j, 1] - z))
    j_top = int(np.argmin(np.abs(prof[:, 0]) + np.abs(prof[:, 1] - H)))
    xs_tie = (0.43 + float(r.uniform(-0.02, 0.02)), L - 0.43 + float(r.uniform(-0.02, 0.02)))
    xs_lift = (0.38, L - 0.38)
    spec = list(xs_tie) + list(xs_lift)
    xs = [x for x in np.arange(0.06, L - 0.05, 0.1) if min(abs(x - s_) for s_ in spec) > 0.06]
    xs += spec + [s_ + d for s_ in spec for d in (-0.085, 0.085)]
    xs = sorted(xs)
    xs = [x for i_, x in enumerate(xs) if i_ == 0 or x - xs[i_ - 1] > 0.02]
    recs = []
    for ysg in (1, -1):
        for zt in (1.0, 2.0, 3.0):
            j = node(ysg, zt + float(r.uniform(-0.05, 0.05)))
            for xt in xs_tie:
                recs.append((xt, j, 0.016, 0.022, 0.009))
    for xl in xs_lift:
        recs.append((xl, j_top, 0.034, 0.05, 0.03))
    # despostilladuras chicas: cantos de la base y de la corona; cantos verticales de los extremos
    ci = [k for k, c in enumerate(corners) if c[2] > 0.01]
    chips = []
    for _ in range(int(r.integers(2, 5))):
        x_ = float(r.uniform(0.15, L - 0.15))
        if min(abs(x_ - xl) for xl in xs_lift + xs_tie) < 0.16:
            continue
        chips.append((int(r.choice(ci)), x_, float(r.uniform(0.012, 0.03)), float(r.uniform(0.004, 0.009))))
    end_chips = [(int(r.integers(2)), float(r.uniform(0.6, 3.4)), float(r.uniform(0.02, 0.05)), float(r.uniform(0.004, 0.01)),
                  int(r.choice([-1, 1]))) for _ in range(int(r.integers(1, 4)))]
    for (k, xc, w, dep) in chips:                          # estaciones extra donde hay despostilladura
        xs += [xc - w, xc, xc + w]
    xs = sorted(xs)
    out = _cast_piece(mb, prof, tags, xs, L, 0.009, chips=chips, end_chips=end_chips, recesses=recs, seed=seed)
    # asas de izaje: varilla de 7/8" en U ahogada en el fondo de cada caja de la corona
    for (c, nrm, ex, ey) in out:
        if c.z < H - 0.01:
            continue
        zb = c.z - 0.05
        path = [(c.x - 0.019, c.y, zb), (c.x - 0.019, c.y, H + 0.06), (c.x + 0.019, c.y, H + 0.06), (c.x + 0.019, c.y, zb)]
        P = np.array(fillet(path, 0.018, 6))
        _tubes_np(mb, [P], 0.0111, seg=16, mat="steel", soft=False, caps=True)
    return mb


def jersey_barrier(L=3.0, seed=0):
    """Barrera tipo New Jersey de concreto precolado (temporal, de conexión pin-and-loop): 0,81 m (32") de alto, base 0,61 m
    (24"), corona 0,15 m (6"): 76 mm verticales, talud de 55° hasta 0,33 m y cara de 84° hasta la corona (FHWA/DOT), quiebre
    del talud redondeado (R 0,1 m). Largo L a lo largo de +X desde x = 0, centrada en y = 0. Dos ranuras de izaje / drenaje
    pasantes en la base de 0,30 × 0,10 m a 0,9 m de cada extremo (WisDOT: "two lifting slots ... 3'-0" from each end"),
    cantos redondeados de colado (R 10-20 mm), rebaba de junta de cimbra en el quiebre del talud, dos insertos de izaje en
    la corona, despostilladuras chicas; lazos de varilla de 3/4" que salen de los extremos (dos por extremo, alturas
    alternadas para encajar con la vecina) y pasador de 25 mm × 0,7 m con cabeza en el extremo +X."""
    r = rng(seed)
    mb = MB()
    zb = 0.33                                              # quiebre del talud
    yb = 0.305 - (zb - 0.076) / math.tan(math.radians(55))
    right = [(0.305, 0.0, 0.01, None), (0.305, 0.076, 0.02, 0.08), (yb, zb - 0.0025, 0.0, None),
             (yb + 0.0016, zb, 0.0, None), (yb - 0.0003, zb + 0.0025, 0.0, 0.08), (0.075, 0.81, 0.018, 0.03)]
    # el quiebre del talud lleva radio grande: se redondea la esquina sin la rebaba (que queda como un hilo de 1,6 mm)
    left = [(-y, z, rr, None) for (y, z, rr, sp) in reversed(right)]
    sps = [sp for (_, _, _, sp) in right]
    for k in range(len(left) - 1):
        left[k] = (left[k][0], left[k][1], left[k][2], sps[len(right) - 2 - k])
    corners = right + [(0.0, 0.81, 0.0, 0.03)] + left
    prof, tags = _rpoly([(y, z) for (y, z, _, _) in corners], [c[2] for c in corners], [c[3] for c in corners], nseg=4)
    j_top = int(np.argmin(np.abs(prof[:, 0]) + np.abs(prof[:, 1] - 0.81)))
    xs_lift = (0.75, L - 0.75)
    notch = []
    for xc in (0.9, L - 0.9):
        notch.append((xc - 0.15, xc + 0.15, 0.10))
    xs = list(np.arange(0.05, L - 0.04, 0.12))
    for (a_, b_, _) in notch:
        xs = [x for x in xs if not (a_ - 0.03 < x < b_ + 0.03)]
        xs += [a_ - 0.012, a_, a_ + 0.1, b_ - 0.1, b_, b_ + 0.012]
    for xl in xs_lift:
        xs = [x for x in xs if abs(x - xl) > 0.05]
        xs += [xl - 0.09, xl, xl + 0.09]
    ci = [k for k, c in enumerate(corners) if c[2] > 0.01]
    chips = []
    for _ in range(int(r.integers(1, 4))):
        x_ = float(r.uniform(0.2, L - 0.2))
        if min([abs(x_ - xl) for xl in xs_lift] + [abs(x_ - (a_ + b_) / 2) for (a_, b_, _) in notch]) < 0.25:
            continue
        chips.append((int(r.choice(ci)), x_, float(r.uniform(0.012, 0.03)), float(r.uniform(0.004, 0.009))))
        xs += [x_ - 0.02, x_, x_ + 0.02]
    end_chips = [(int(r.integers(2)), float(r.uniform(0.15, 0.7)), float(r.uniform(0.02, 0.04)), float(r.uniform(0.004, 0.009)),
                  int(r.choice([-1, 1]))) for _ in range(int(r.integers(1, 3)))]
    xs = sorted(xs)
    recs = [(xl, j_top, 0.022, 0.03, 0.016) for xl in xs_lift]
    out = _cast_piece(mb, prof, tags, xs, L, 0.008, chips=chips, end_chips=end_chips, notches=notch, recesses=recs, seed=seed)
    # insertos de izaje: anillo de acero ahogado en el fondo de cada hueco de la corona
    for (c, nrm, ex, ey) in out:
        Mi = _T(c.x, c.y, c.z - 0.03)
        lathe(mb, [(0.0, 0.0), (0.012, 0.0), (0.012, 0.012), (0.0065, 0.012), (0.0065, 0.004), (0.0, 0.004)], seg=SEG,
              mat="steel", M=Mi)
    # pin-and-loop: lazos de varilla en U que salen 9 cm de cada cara de extremo
    for (xe, sgn, zl) in ((0.0, -1, (0.22, 0.56)), (L, 1, (0.30, 0.64))):
        for z in zl:
            w = 0.05
            path = [(xe - sgn * 0.04, -w, z), (xe + sgn * 0.09, -w, z), (xe + sgn * 0.09, w, z), (xe - sgn * 0.04, w, z)]
            tube_path(mb, path, 0.0095, seg=16, mat="steel", bend=0.035, nseg=6, caps=True)
    # pasador (en el extremo +X, pasa por los lazos de este lado): barra de 25 mm con cabeza recalcada y punta achaflanada
    xp = L + 0.09 - 0.0095 - 0.0125 + 0.0002                # apoyado contra el fondo de los lazos, la punta en el piso
    lathe(mb, [(0.0, 0.0), (0.009, 0.0), (0.0125, 0.004), (0.0125, 0.69), (0.021, 0.695), (0.022, 0.702), (0.022, 0.715),
               (0.018, 0.72), (0.0, 0.721)], seg=SEG, mat="steel", M=_T(xp, 0.0, 0.0))
    return mb


# ============================================================================================================ concertina
# Alambre de navajas en espiral con grapas (concertina), navaja BTO-22: fleje de acero de 0,5 mm engargolado sobre un alma de
# alambre de alta resistencia de 2,5 mm; cada racimo de navajas mide 22 mm de largo × 15 mm de ancho (cuatro puntas, dos
# pares encontrados) cada 34 mm (fichas de fabricante: globalsources BTO-22 0,5 / 2,5 / 22 / 15 / 34 mm; otras dan 16 mm de
# ancho y 35 mm de paso). Rollo de 600-730 mm de diámetro, ~56 espiras estiradas a 10-15 m, 3 a 5 grapas por vuelta que
# unen cada espira con la vecina (rapidtech.co.ke 730 mm, firstfence.co.uk). FM 5-102: concertina triple estándar.
CON_P = 0.034         # paso entre racimos de navajas a lo largo del fleje
CON_SP = 0.22         # separación entre espiras estiradas
CON_CLIPS = 3.5       # grapas por vuelta (media: alternan con la espira anterior y la siguiente)
CON_RS = 0.00175      # radio exterior del fleje engargolado (alma 2,5 mm + 2 × 0,5 mm de fleje)
CON_RC = 0.00125      # radio del alma


def _barb_cluster_proto():
    """Racimo de navajas BTO-22 en coordenadas locales (t a lo largo del fleje, u a lo ancho, v espesor): cuatro puntas
    triangulares de lámina de 0,5 mm (dos pares encontrados: una hacia atrás y otra hacia adelante de cada lado), con su
    base metida en el engargolado. Devuelve (vértices K × 3, caras)."""
    V, F = [], []
    for su in (1.0, -1.0):
        for sd in (-1.0, 1.0):
            tri = [(sd * 0.0016, su * 0.0010), (sd * 0.0078, su * 0.0010), (sd * 0.011, su * 0.0075)]
            o = len(V)
            for v in (-0.00025, 0.00025):
                for (t, u) in tri:
                    V.append((t, u, v))
            F += [[o, o + 1, o + 2], [o + 5, o + 4, o + 3]]
            for k in range(3):
                kk = (k + 1) % 3
                F.append([o + k, o + 3 + k, o + 3 + kk, o + kk])
    return np.array(V), F


def _clip_band(a, b, tang, w=0.012, t=0.0006):
    """Grapa: fleje de acero de 12 mm × 0,6 mm cerrado en estadio alrededor de dos fajas que se cruzan (centros a y b).
    Devuelve (V, F) de un sólido cerrado (cara exterior, interior y dos cantos)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    ax = np.asarray(tang, float)
    e1 = b - a
    e1 = e1 - ax * e1.dot(ax)
    gap = np.linalg.norm(e1)
    e1 = e1 / max(gap, 1e-9) if gap > 1e-6 else np.cross(ax, [0.0, 0.0, 1.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(ax, e1)
    mid = (a + b) / 2
    hl = max(gap / 2, 0.0005)
    ang = np.concatenate([np.linspace(-PI / 2, PI / 2, 8), np.linspace(PI / 2, 1.5 * PI, 8)])
    sgn = np.concatenate([np.ones(8), -np.ones(8)])
    rings = []
    for R_ in (CON_RS + 0.0002 + t, CON_RS + 0.0002):
        for x in (-w / 2, w / 2):
            pinch = 1.0
            P = (mid[None, :] + ax[None, :] * x + e1[None, :] * (sgn * hl + R_ * np.cos(ang))[:, None]
                 + e2[None, :] * (R_ * np.sin(ang) * pinch)[:, None])
            rings.append(P)
    V = np.concatenate(rings, 0)
    n = 16
    F = []
    for (A_, B_) in ((0, 1), (3, 2), (2, 0), (1, 3)):      # exterior, interior, canto -x, canto +x
        for j in range(n):
            jj = (j + 1) % n
            F.append([A_ * n + j, A_ * n + jj, B_ * n + jj, B_ * n + j])
    return V, F


def _coil(mb, L, d, seed, ctr=(0.0, None), squash=0.94, ground=True, clip_out=None):
    """Una espira continua de navaja BTO-22 a lo largo de +X (0..L), eje en (y, z) = ctr: fleje engargolado (tubo de 3,5 mm,
    12 lados, sombreado continuo) que se tuerce a lo largo del rollo, racimos de 4 navajas de lámina de 0,5 mm cada 34 mm,
    alma de 2,5 mm que asoma en las puntas, y grapas de fleje cerrado en estadio donde cada espira toca a la vecina (patrón
    de rombos de la concertina). Devuelve los puntos del eje de la espira."""
    r = rng(seed)
    R = d / 2 - 0.008
    yc, zc = ctr[0], ((R * squash - 0.02) if ctr[1] is None else ctr[1])
    nt = max(2, int(round(L / CON_SP)))
    p = (L - CON_SP * 0.5) / nt
    ph = float(r.uniform(0, 100))
    A = 0.47 * p
    ns = 72
    th = np.linspace(0.0, 2 * PI * nt, ns * nt + 1)
    rr = R * (1 + 0.025 * np.array([noise.noise(Vector((t * 0.35, ph, 0.0))) for t in th]))
    x = p * th / (2 * PI) + A * np.cos(CON_CLIPS * th) + p * 0.25 + 0.006 * np.array([noise.noise(Vector((t * 0.8, ph, 2.0))) for t in th])
    y = yc + rr * np.cos(th) * (2 - squash)
    z = zc + rr * np.sin(th) * squash
    if ground:                                             # las espiras de abajo se apoyan y se aplanan en el piso
        zmin, wf = 0.009, 0.04
        z = np.where(z < zmin + wf, zmin + wf * np.exp((z - zmin - wf) / wf), z)
    P = np.stack([x, y, z], 1)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    acc = np.concatenate([[0.0], np.cumsum(seg)])
    tot = acc[-1]

    def frame(S):
        Q = np.stack([np.interp(S, acc, P[:, k]) for k in range(3)], 1)
        Th = np.interp(S, acc, th)
        dP = np.stack([np.interp(S + 0.002, acc, P[:, k]) - np.interp(S - 0.002, acc, P[:, k]) for k in range(3)], 1)
        T = dP / np.linalg.norm(dP, axis=1, keepdims=True)
        rad = np.stack([np.zeros(len(S)), Q[:, 1] - yc, Q[:, 2] - zc], 1)
        rad = rad - T * (rad * T).sum(1, keepdims=True)
        rad /= np.maximum(np.linalg.norm(rad, axis=1, keepdims=True), 1e-9)
        bn = np.cross(T, rad)
        tw = 2 * PI * S / 1.1 + 0.9 * np.array([noise.noise(Vector((float(s_) * 0.7, ph, 5.0))) for s_ in S])
        U = rad * np.cos(tw)[:, None] + bn * np.sin(tw)[:, None]   # ancho del fleje: se tuerce a lo largo del rollo
        Vn = np.cross(T, U)
        return Q, T, U, Vn, Th
    # ---- fleje engargolado: tubo de 12 lados con anillos cada ~25 mm (4,7° de curva a 0,3 m de radio)
    S = np.arange(0.006, tot - 0.006, CON_P * 0.72)
    Q, T, U, Vn, _ = frame(S)
    an = 2 * PI * np.arange(12) / 12
    ring = Q[:, None, :] + CON_RS * (np.cos(an)[None, :, None] * U[:, None, :] + np.sin(an)[None, :, None] * Vn[:, None, :])
    K = len(S)
    F = _grid_quads(K, 12, closed=True).tolist()
    F.append(list(range(11, -1, -1)))
    F.append(list(range((K - 1) * 12, K * 12)))
    _np_faces(mb, ring.reshape(-1, 3), F, "galvanized", soft=True)
    # ---- alma de 2,5 mm: asoma 12 mm en cada punta del rollo (corte de cizalla)
    paths = []
    for (s0, s1) in ((0.006, -0.006), (tot - 0.006, tot + 0.006)):
        e = Q[0] if s1 < s0 else Q[-1]
        tt = T[0] if s1 < s0 else T[-1]
        sg = -1.0 if s1 < s0 else 1.0
        paths.append(np.array([e - sg * tt * 0.004, e + sg * tt * 0.006, e + sg * tt * 0.012]))
    _tubes_np(mb, paths, CON_RC, seg=12, soft=True)
    # ---- racimos de navajas (lámina de 0,5 mm, cantos vivos)
    Sc = np.arange(0.006 + CON_P / 2, tot - 0.02, CON_P)
    Qc, Tc, Uc, Vc, _ = frame(Sc)
    pv, pf = _barb_cluster_proto()
    nv = len(pv)
    jit = r.normal(0.0, 0.06, len(Sc))                     # navajas apenas fuera del plano (dobladas al manejar el rollo)
    Vall, Fall = [], []
    for k in range(len(Sc)):
        u_ = Uc[k] * math.cos(jit[k]) + Vc[k] * math.sin(jit[k])
        v_ = np.cross(Tc[k], u_)
        Vall.append(Qc[k] + np.outer(pv[:, 0], Tc[k]) + np.outer(pv[:, 1], u_) + np.outer(pv[:, 2], v_))
        Fall.extend((np.array(f) + k * nv).tolist() for f in pf)
    if Vall:
        _np_faces(mb, np.concatenate(Vall, 0), Fall, "galvanized", soft=False)
    # ---- grapas donde cada espira toca a la siguiente
    m = 0
    clips = []
    Vg, Fg = [], []
    while True:
        t0 = 2 * PI * m / CON_CLIPS
        if t0 + 2 * PI > th[-1] - 1e-6:
            break
        pa = np.array([np.interp(t0, th, P[:, j]) for j in range(3)])
        pb = np.array([np.interp(t0 + 2 * PI, th, P[:, j]) for j in range(3)])
        ta = np.array([np.interp(t0 + 0.01, th, P[:, j]) - np.interp(t0 - 0.01, th, P[:, j]) for j in range(3)])
        tb = np.array([np.interp(t0 + 2 * PI + 0.01, th, P[:, j]) - np.interp(t0 + 2 * PI - 0.01, th, P[:, j]) for j in range(3)])
        tg = ta / np.linalg.norm(ta) + tb / np.linalg.norm(tb)
        tg /= max(np.linalg.norm(tg), 1e-9)
        Vb, Fb = _clip_band(pa, pb, tg)
        Fg.extend((np.array(f) + sum(len(v) for v in Vg)).tolist() for f in Fb)
        Vg.append(Vb)
        clips.append(Vector(((pa + pb) / 2).tolist()))
        m += 1
    if Vg:
        _np_faces(mb, np.concatenate(Vg, 0), Fg, "steel", soft=False)
    if clip_out is not None:
        clip_out.extend(clips)
    return P


def _frame(p0, p1, up):
    p0, p1 = Vector(p0), Vector(p1)
    X = (p1 - p0).normalized()
    U = Vector(up)
    if abs(X.dot(U)) > 0.99:
        U = Vector((0, 0, 1)) if abs(X.z) < 0.9 else Vector((1, 0, 0))
    Z = (U - X * X.dot(U)).normalized()
    Y = Z.cross(X)
    return Matrix(((X.x, Y.x, Z.x, p0.x), (X.y, Y.y, Z.y, p0.y), (X.z, Y.z, Z.z, p0.z), (0, 0, 0, 1)))


def concertina(L=10.0, d=0.75, seed=0):
    """Rollo de concertina de navajas BTO-22 estirado en el piso a lo largo de +X (0..L), eje en y = 0, base en z = 0: fleje
    engargolado de 3,5 mm sobre alma de 2,5 mm, racimos de cuatro navajas de lámina (22 × 15 mm, cada 34 mm) en pares
    encontrados, fleje que se tuerce, espiras de diámetro d separadas 0,22 m con 3,5 grapas por vuelta que alternan con la
    espira anterior y la siguiente (el patrón de rombos de la concertina), espiras de abajo aplanadas en el piso.
    ~20 k tris por metro."""
    mb = MB()
    _coil(mb, L, d, seed)
    return mb


def _u_picket(mb, x, y, h, rot=0.0, mat="paint_od"):
    """Piquete en U de acero (perfil de 75 × 35 × 3 mm con alas dobladas y radios de doblez reales) hincado; asoma h m."""
    t = 0.003
    prof = [(-0.0375, 0.0), (-0.0375, 0.012), (-0.03, 0.035), (0.03, 0.035), (0.0375, 0.012), (0.0375, 0.0),
            (0.0375 - t, 0.0), (0.0375 - t, 0.011), (0.03 - t * 0.6, 0.035 - t), (-0.03 + t * 0.6, 0.035 - t),
            (-0.0375 + t, 0.011), (-0.0375 + t, 0.0)]
    radii = [0.0006, 0.0045, 0.0045, 0.0045, 0.0045, 0.0006, 0.0006, 0.0015, 0.0015, 0.0015, 0.0015, 0.0006]
    pp, _ = _rpoly(prof, radii, [None] * len(prof), nseg=3)
    M = _T(x, y, 0.0) @ _Rz(rot)
    rings = [[M @ Vector((float(px), float(py) - 0.017, z)) for (px, py) in pp] for z in (-0.15, h - 0.004, h)]
    rings[-1] = [M @ Vector((float(px) * 0.985, float(py) * 0.985 - 0.017 + 0.0003, h)) for (px, py) in pp]
    loft_rings(mb, rings, mat)


def _tie_wire(mb, c, axis, rad, turns=2.0, r=0.0008, n=16):
    """Amarre de alambre recocido (1,6 mm, 12 lados, sombreado continuo): hélice de `turns` vueltas alrededor de `axis`."""
    c, axis = np.asarray(c, float), np.asarray(axis, float)
    axis /= np.linalg.norm(axis)
    e1 = np.cross(axis, [0.0, 0.0, 1.0] if abs(axis[2]) < 0.9 else [1.0, 0.0, 0.0])
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(axis, e1)
    a = np.linspace(0.0, 2 * PI * turns, int(n * turns) + 1)
    P = c + np.outer(np.cos(a) * rad, e1) + np.outer(np.sin(a) * rad, e2) + np.outer((a / (2 * PI) - turns / 2) * 0.0024, axis)
    _tubes_np(mb, [P], r, seg=12, mat="steel", soft=True)


def concertina_triple(L=10.0, d=0.75, seed=0):
    """Concertina triple estándar (FM 5-102): dos rollos lado a lado en el piso y un tercero encima en la junta, a lo largo de
    +X (0..L), centrada en y = 0; piquetes de U de acero de 1,65 m metidos en los rollos de abajo cada ~4,5 m (y a 0,3 m de
    cada extremo), y amarres de alambre recocido que sujetan los rollos a los piquetes."""
    r = rng(seed)
    mb = MB()
    R = d / 2
    yb = R * 0.98
    Rc = R - 0.008
    zt = Rc * 0.94 - 0.02 + 0.9 * math.sqrt(max(4 * Rc * Rc - yb * yb, 0.0))
    for k, (yy, zz) in enumerate(((-yb, None), (yb, None), (0.0, zt))):
        _coil(mb, L, d, seed * 3 + k, ctr=(yy, zz), ground=zz is None, squash=0.94 if zz is None else 0.97)
    npk = max(2, int(round(L / 4.5)) + 1)
    for side in (-1, 1):
        for i in range(npk):
            x = 0.3 + (L - 0.6) * i / (npk - 1) + float(r.uniform(-0.1, 0.1))
            y = side * yb * 0.55 + float(r.uniform(-0.03, 0.03))
            _u_picket(mb, x, y, 1.65, rot=float(r.uniform(-8, 8)) + (0 if side < 0 else 180))
            for z in (0.4, 1.5):                           # amarres: dos vueltas de alambre alrededor del piquete
                _tie_wire(mb, (x, y - side * 0.017, z), (0.0, 0.0, 1.0), 0.045, turns=2.0, n=40)
    return mb


def concertina_fence_top(L=10.0, d=0.6, seed=0, with_fence=False):
    """Un rollo de concertina montado sobre una malla ciclónica de 2,4 m (kit.telecom.fence_run, brazos a 45° hacia -Y):
    coordenadas del tramo de cerca (x a lo largo, y = 0 eje de los postes, z = piso). El rollo descansa sobre los 3 hilos de
    púas de los brazos, centrado sobre el hilo medio, y se amarra a los hilos cada ~0,45 m con dos vueltas de alambre
    recocido que abrazan el hilo y el fleje. with_fence=True agrega el tramo de cerca 'lite' (solo para revisar)."""
    from kit import telecom as tel
    mb = MB()
    z_b, n, z_top, zr, zp, zt = tel.fence_levels(2.4)
    zr_arm = zp + 0.010 + tel.R_RAIL + 0.002
    base = Vector((0.0, tel.Y_RAIL - tel.R_RAIL - 0.003, zr_arm + 0.003))
    dv = Vector((0.0, -math.cos(PI / 4), math.sin(PI / 4)))
    up = Vector((0.0, math.sin(PI / 4), math.cos(PI / 4)))
    strands = [base + dv * s + up * 0.0048 for s in (0.115, 0.22, 0.325)]
    R = d / 2
    c = strands[1] + up * (R + 0.004)
    P = _coil(mb, L, d, seed, ctr=(c.y, c.z), ground=False, squash=0.97)
    # amarres: en cada hilo, donde la espira pasa más cerca, dos vueltas que abrazan hilo + fleje
    for k, sp in enumerate(strands):
        x = 0.25 + 0.15 * k
        while x < L - 0.2:
            sel = np.abs(P[:, 0] - x) < 0.12
            if sel.any():
                Pc = P[sel]
                dd = np.hypot(Pc[:, 1] - sp.y, Pc[:, 2] - sp.z)
                iq = int(np.flatnonzero(sel)[int(np.argmin(dd))])
                q = P[iq]
                mid = (np.array((q[0], sp.y, sp.z)) + q) / 2
                gap = float(np.min(dd))
                if gap < 0.014 and 0 < iq < len(P) - 1:
                    tq = P[iq + 1] - P[iq - 1]
                    tq /= np.linalg.norm(tq)
                    ax = np.array((1.0, 0.0, 0.0)) + tq * (1.0 if tq[0] >= 0 else -1.0)
                    _tie_wire(mb, mid, ax, gap / 2 + 0.0042, turns=2.0, n=28)
            x += 0.45 * 2
    if with_fence:
        mb.join(tel.fence_run(L=L, fabric="lite"))
    return mb


# ================================================================================================== utilidades de equipo
def face_M(o, n, up=(0, 0, 1)):
    """Matriz de una cara: origen o, +Z local = normal n (hacia afuera), +Y local lo más cerca de `up`."""
    Z = _v(n).normalized()
    U = _v(up)
    if abs(U.dot(Z)) > 0.99:
        U = Vector((0, 1, 0)) if abs(Z.y) < 0.9 else Vector((1, 0, 0))
    Y = (U - Z * U.dot(Z)).normalized()
    X = Y.cross(Z)
    o = _v(o)
    return Matrix(((X.x, Y.x, Z.x, o.x), (X.y, Y.y, Z.y, o.y), (X.z, Y.z, Z.z, o.z), (0, 0, 0, 1)))


def torus(mb, M, R, r, mat="steel", n=24, seg=12, a0=0.0, a1=2 * PI):
    """Toro (o arco) en el plano XY local: argollas, asas, ojos de izaje."""
    full = abs(a1 - a0 - 2 * PI) < 1e-6
    cnt = n if full else n + 1
    rings = []
    for i in range(cnt):
        a = a0 + (a1 - a0) * i / n
        c = Vector((R * math.cos(a), R * math.sin(a), 0.0))
        rd = Vector((math.cos(a), math.sin(a), 0.0))
        rings.append([mb.bm.verts.new(M @ (c + rd * (r * math.cos(2 * PI * k / seg)) + Vector((0, 0, r * math.sin(2 * PI * k / seg)))))
                      for k in range(seg)])
    for i in range(cnt if full else cnt - 1):
        A, B = rings[i], rings[(i + 1) % cnt]
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([A[k], B[k], B[kk], A[kk]], mat)
    if not full:
        mb.face(list(reversed(rings[0])), mat)
        mb.face(rings[-1], mat)


def hollow_rect(mb, M, w, h, t, L, mat="steel", r=0.004):
    """Tubo rectangular HUECO (boca visible: bolsas de montacargas) a lo largo de X local, de 0 a L, sección w (Y) × h (Z)."""
    po = rr_profile(w, h, r, n=2)
    pi_ = rr_profile(w - 2 * t, h - 2 * t, max(r - t, 0.0008), n=2)
    O = [[mb.bm.verts.new(M @ Vector((x, a, b))) for (a, b) in po] for x in (0.0, L)]
    I_ = [[mb.bm.verts.new(M @ Vector((x, a, b))) for (a, b) in pi_] for x in (0.0, L)]
    k = len(po)
    for j in range(k):
        jj = (j + 1) % k
        mb.face([O[0][j], O[0][jj], O[1][jj], O[1][j]], mat)
        mb.face([I_[0][jj], I_[0][j], I_[1][j], I_[1][jj]], mat)
        mb.face([O[0][jj], O[0][j], I_[0][j], I_[0][jj]], mat)
        mb.face([O[1][j], O[1][jj], I_[1][jj], I_[1][j]], mat)


def dring_latch(mb, M, s=1.0, mat="steel"):
    """Cerrojo embutido de 1/4 de vuelta: copa embutida + manija en T abatida dentro de la copa. M: cara (+Z afuera)."""
    lathe(mb, [(0.0, -0.006 * s), (0.017 * s, -0.006 * s), (0.02 * s, 0.0005), (0.024 * s, 0.0015 * s), (0.026 * s, 0.0)], seg=SEG,
          mat=mat, M=M, caps=False)
    mb.box((-0.0035 * s, -0.016 * s, -0.004 * s), (0.0035 * s, 0.016 * s, 0.0035 * s), mat, bevel=0.0012 * s, seg=1, m=M)


# ============================================================================================================ bidón
def jerry_can(seed=0, color="od"):
    """Bidón de 20 L tipo OTAN ("jerry can"): 470 × 345 × 165 mm (armysurplusworld / Wavian: 18-1/2" × 13-1/2" × 6-1/2"), dos
    mitades de lámina estampada soldadas con cordón perimetral, X estampada en ambas caras (cuatro paneles realzados con
    esquinas redondas), aristas redondeadas, tres asas de tubo en la tapa (para uno o dos cargadores) y boquilla con tapa de
    leva y palanca. Pintura verde olivo (od) o arena (tan). Origen: centro de la base; caras anchas hacia ±Y."""
    r = rng(seed)
    mat = "paint_od" if color == "od" else "paint_tan"
    mb = MB()
    W, D, Hb = 0.345, 0.165, 0.435
    z0 = 0.003
    re = 0.016
    rc = (0.03, 0.03, 0.036, 0.036)

    def outline(dl, y):
        return [(x, y, z0 + Hb / 2 + z) for (x, z) in rr_pts(W - 2 * dl, Hb - 2 * dl, tuple(max(c - dl, 0.002) for c in rc), n=4)]
    loops = []
    for j in range(4):                                     # canto delantero redondeado
        a = PI / 2 * j / 3
        loops.append(outline(re * (1 - math.sin(a)), -D / 2 + re * (1 - math.cos(a))))
    for (y, dl) in ((-0.0075, 0.0), (-0.0035, -0.0018), (0.0, -0.0028), (0.0035, -0.0018), (0.0075, 0.0)):
        loops.append(outline(dl, y))                       # cordón de soldadura entre las dos mitades
    for j in range(3, -1, -1):
        a = PI / 2 * j / 3
        loops.append(outline(re * (1 - math.sin(a)), D / 2 - re * (1 - math.cos(a))))
    V = skin(mb, loops, mat, cap0=False, cap1=False)
    ngon(mb, list(reversed(V[0])), mat)
    ngon(mb, V[-1], mat)
    # X estampada: cuatro paneles triangulares realzados 3 mm con esquinas redondas
    x0, x1 = -W / 2 + 0.036, W / 2 - 0.036
    zb, zt = z0 + 0.042, z0 + Hb - 0.046
    C = Vector(((x0 + x1) / 2, (zb + zt) / 2))
    corners = [Vector((x0, zt)), Vector((x1, zt)), Vector((x1, zb)), Vector((x0, zb))]
    for side in (-1, 1):
        yf = side * D / 2
        for k in range(4):
            tri = [corners[k], corners[(k + 1) % 4], C]
            rings = []
            for (inset, yy) in ((0.0075, yf - side * 0.0008), (0.0118, yf + side * 0.003)):
                pts = []
                cen = (tri[0] + tri[1] + tri[2]) / 3
                for i in range(3):
                    p0, p1, p2 = tri[i - 1], tri[i], tri[(i + 1) % 3]
                    e0 = (p1 - p0).normalized()
                    e1 = (p2 - p1).normalized()
                    n0 = Vector((-e0.y, e0.x))
                    n1 = Vector((-e1.y, e1.x))
                    if (cen - p1).dot(n0) < 0:
                        n0, n1 = -n0, -n1
                    rcn = 0.008
                    m = (n0 + n1).normalized()
                    half = math.acos(max(-1.0, min(1.0, n0.dot(n1)))) / 2
                    q = p1 + m * ((inset + rcn) / math.cos(half))
                    a0 = math.atan2(-n0.y, -n0.x)
                    a1 = math.atan2(-n1.y, -n1.x)
                    da = (a1 - a0 + PI) % (2 * PI) - PI
                    for t in range(3):
                        aa = a0 + da * t / 2
                        pts.append(Vector((q.x + rcn * math.cos(aa), yy, q.y + rcn * math.sin(aa))))
                rings.append(pts)
            # orientar igual que la cara
            R0 = [mb.bm.verts.new(p) for p in rings[0]]
            R1 = [mb.bm.verts.new(p) for p in rings[1]]
            nn = len(R0)
            for i in range(nn):
                ii = (i + 1) % nn
                mb.face([R0[i], R0[ii], R1[ii], R1[i]], mat)
            ngon(mb, R1, mat)
    # asas: tres tubos de 19 mm en la tapa, de la cara delantera a la trasera
    for xh in (-0.118, -0.042, 0.034):
        path = [(xh, -0.052, z0 + Hb - 0.008), (xh, -0.048, z0 + Hb + 0.024), (xh, 0.048, z0 + Hb + 0.024), (xh, 0.052, z0 + Hb - 0.008)]
        tube_path(mb, path, 0.0095, seg=SEG_T, mat=mat, bend=0.016, nseg=3, caps=False)
    # boquilla con tapa de leva y palanca de cierre
    Ms = _T(0.118, 0.0, z0 + Hb - 0.024) @ _Ry(18)
    lathe(mb, [(0.0225, -0.004), (0.0225, 0.022), (0.0255, 0.024), (0.0255, 0.027)], seg=SEG, mat=mat, M=Ms, caps=False)
    lathe(mb, [(0.0285, 0.026), (0.0298, 0.03), (0.0298, 0.043), (0.026, 0.049), (0.012, 0.0515), (0.0, 0.0515)], seg=SEG, mat=mat,
          M=Ms)
    # bisagra de la tapa (lado +X) y palanca que corre sobre la tapa hacia las asas
    mb.cyl(Ms @ Vector((0.034, -0.012, 0.036)), Ms @ Vector((0.034, 0.012, 0.036)), 0.0042, seg=SEG_T, mat="steel")
    rbox(mb, (-0.07, -0.007, 0.050), (0.03, 0.007, 0.056), mat, r=0.002, m=Ms)
    rbox(mb, (-0.078, -0.009, 0.042), (-0.066, 0.009, 0.056), mat, r=0.002, m=Ms)
    # pasador de seguridad con cadenita a la asa
    mb.cyl(Ms @ Vector((-0.072, -0.013, 0.047)), Ms @ Vector((-0.072, 0.013, 0.047)), 0.0018, seg=SEG_T, mat="steel")
    return mb


# ======================================================================================================= generador táctico
def tactical_generator(seed=0, color="od"):
    """Grupo electrógeno táctico de 10 kW sobre patín (tipo AMMPS MEP-1040: 55 × 32 × 35,8 in = 1,40 × 0,81 × 0,91 m, ficha
    Cummins / MARCORSYSCOM). Largo en X, frente de servicio -Y. Patín de canal con bolsas de montacargas huecas y argollas de
    amarre; gabinete de lámina de esquinas redondeadas con puertas de acceso a ambos lados (holgura de 3 mm, bisagra de piano y
    cerrojos de D), rejilla de toma de aire en el extremo -X, tablero de control bajo visera en +X (instrumentos, interruptores,
    contactos), salida de escape con tapa contra lluvia, tapón de combustible, 4 ojos de izaje, borne de tierra, receptáculo
    de arranque auxiliar y placa de datos."""
    r = rng(seed)
    mat = "paint_od" if color == "od" else "paint_tan"
    mb = MB()
    Lx, Wy, Hz = 1.40, 0.81, 0.915
    zs = 0.11
    # ---- patín: dos largueros de canal + bolsas de montacargas huecas + argollas
    for sy in (-1, 1):
        rtube(mb, (-Lx / 2, sy * 0.355, zs / 2), (Lx / 2, sy * 0.355, zs / 2), 0.07, zs, mat, up=(0, 0, 1), r=0.004)
    for xp in (-0.36, 0.36):
        hollow_rect(mb, _T(xp, -Wy / 2, 0.045) @ _Rz(90), 0.21, 0.075, 0.005, Wy, mat=mat)
    for sx in (-1, 1):
        for sy in (-1, 1):
            Mx = _T(sx * (Lx / 2 - 0.08), sy * (0.355 + 0.036), 0.06) @ _Rx(-sy * 90)
            lathe(mb, [(0.0, 0.0), (0.018, 0.0), (0.018, 0.012), (0.0, 0.012)], seg=SEG, mat=mat, M=Mx)
            torus(mb, Mx @ _T(0, 0.0, 0.02) @ _Ry(90), 0.022, 0.0055, mat="steel", n=10, seg=SEG_T, a0=-PI * 0.3, a1=PI * 1.3)
    # ---- gabinete
    slab(mb, _T(0, 0, zs), Lx, Wy, Hz - zs, rc=0.035, re=0.022, mat=mat, nc=4, ne=3)
    # puertas laterales (2 por lado): paneles de 3 mm con holgura, bisagra de piano arriba, 2 cerrojos de D
    for sy in (-1, 1):
        yf = sy * Wy / 2
        for xc in (-0.33, 0.33):
            Mf = face_M((xc, yf, 0.0), (0, sy, 0))
            w, h = 0.6, 0.56
            zc = zs + 0.07 + h / 2
            slab(mb, Mf @ _T(0, zc, -0.001), w, h, 0.004, rc=0.012, re=0.0015, mat=mat, nc=3, ne=1, re0=0.0, cap0=False)
            mb.cyl(Mf @ Vector((-w / 2 + 0.01, zc + h / 2 + 0.006, 0.006)), Mf @ Vector((w / 2 - 0.01, zc + h / 2 + 0.006, 0.006)),
                   0.0055, seg=SEG_T, mat=mat)
            dring_latch(mb, Mf @ _T(0.0, zc - h / 2 + 0.06, 0.003), s=1.0)
            if xc < 0:                                     # persiana de ventilación en la puerta de la toma
                for k in range(7):
                    zz = zc - 0.15 + k * 0.045
                    mb.box((-0.2, -0.012, -0.004), (0.2, 0.012, 0.004), mat, bevel=0.0018, seg=1, m=Mf @ _T(0, zz, 0.006) @ _Rx(-30))
    # ---- rejilla de aire de enfriamiento (extremo -X)
    from kit.clinic_servicios import louver_grille
    louver_grille(mb, face_M((-Lx / 2 - 0.0005, 0.0, zs + 0.43), (-1, 0, 0)), 0.6, 0.5, 11, mat=mat, back_mat="cable", t=0.008,
                  frame=0.03, slat_ang=40.0, depth=0.03, nr=32)
    # ---- tablero de control (extremo +X): marco, visera, instrumentos, interruptores, contactos
    Mp = face_M((Lx / 2, 0.0, 0.0), (1, 0, 0))
    zp = zs + 0.47
    mb.box((-0.3, zp - 0.2, -0.04), (0.3, zp + 0.2, 0.002), "cable", bevel=0.003, m=Mp)
    mb.box((-0.31, zp + 0.2, 0.0), (0.31, zp + 0.215, 0.13), mat, bevel=0.003, m=Mp)        # visera
    for sx in (-1, 1):
        mb.box((sx * 0.31 - 0.006, zp - 0.05, 0.0), (sx * 0.31 + 0.006, zp + 0.215, 0.13), mat, bevel=0.002, m=Mp)
    for k, xg in enumerate((-0.2, -0.08, 0.04)):           # instrumentos de carátula redonda con bisel y cristal
        Mg = Mp @ _T(xg, zp + 0.08, 0.002)
        lathe(mb, [(0.0, 0.0), (0.04, 0.0), (0.042, 0.008), (0.036, 0.012), (0.034, 0.006), (0.0, 0.006)], seg=SEG, mat="steel",
              M=Mg)
        lathe(mb, [(0.034, 0.0055), (0.0, 0.0075)], seg=SEG, mat="glass", M=Mg)
    for xg in (0.16, 0.22):                                # botones de hongo (paro de emergencia / arranque)
        lathe(mb, [(0.0, 0.0), (0.012, 0.0), (0.012, 0.012), (0.019, 0.014), (0.019, 0.022), (0.012, 0.026), (0.0, 0.027)], seg=SEG,
              mat="sign_red", M=Mp @ _T(xg, zp + 0.08, 0.0))
    for k in range(5):                                     # interruptores de palanca con guarda
        Ms = Mp @ _T(-0.2 + k * 0.08, zp - 0.04, 0.002)
        lathe(mb, [(0.0, 0.0), (0.011, 0.0), (0.011, 0.006), (0.0, 0.006)], seg=SEG_T, mat="steel", M=Ms)
        mb.cyl(Ms @ Vector((0, 0, 0.006)), Ms @ Vector((0, 0.012, 0.024)), 0.003, seg=SEG_T, mat="steel")
    for k in range(3):                                     # contactos con tapa abatible
        Mc = Mp @ _T(-0.18 + k * 0.17, zp - 0.13, 0.002)
        mb.box((-0.035, -0.035, 0.0), (0.035, 0.035, 0.012), "cable", bevel=0.003, seg=1, m=Mc)
        mb.box((-0.03, -0.03, 0.012), (0.03, 0.03, 0.018), "rubber", bevel=0.003, seg=1, m=Mc)
    label(mb, "MAIN", 0.018, "sign_white", Mp @ _T(0.19, zp + 0.125, 0.002), depth=0.0012)
    # ---- techo: escape con tapa contra lluvia, tapón de combustible, ojos de izaje
    lathe(mb, [(0.0, -0.01), (0.038, -0.01), (0.038, 0.11), (0.034, 0.11), (0.034, 0.0)], seg=SEG, mat="steel",
          M=_T(-0.42, 0.18, Hz), caps=False)
    lathe(mb, [(0.05, -0.002), (0.052, 0.006), (0.044, 0.008), (0.044, 0.0)], seg=SEG, mat=mat, M=_T(-0.42, 0.18, Hz), caps=False)
    Mrc = _T(-0.42, 0.18 - 0.04, Hz + 0.112) @ _Rx(14)
    lathe(mb, [(0.0, 0.0), (0.043, 0.0), (0.043, 0.004), (0.0, 0.006)], seg=SEG, mat="steel", M=Mrc @ _T(0, 0.04, 0))
    mb.cyl(Mrc @ Vector((-0.02, 0.0, 0.002)), Mrc @ Vector((0.02, 0.0, 0.002)), 0.004, seg=SEG_T, mat="steel")
    Mf = _T(0.42, -0.2, Hz)
    lathe(mb, [(0.0, -0.005), (0.045, -0.005), (0.045, 0.01), (0.041, 0.012), (0.041, 0.003), (0.0, 0.003)], seg=SEG, mat=mat, M=Mf)
    lathe(mb, [(0.0, 0.003), (0.036, 0.003), (0.036, 0.022), (0.03, 0.03), (0.0, 0.031)], seg=SEG, mat="steel", M=Mf,
          rmod=lambda i, a, rr, z: rr * (1 - 0.06 * max(0.0, math.cos(8 * a)) ** 4) if i in (1, 2) else rr)
    for sx in (-1, 1):
        for sy in (-1, 1):
            Me = _T(sx * (Lx / 2 - 0.09), sy * (Wy / 2 - 0.09), Hz)
            mb.box((-0.035, -0.012, -0.002), (0.035, 0.012, 0.008), "steel", bevel=0.003, m=Me @ _Rz(45 * sx * sy))
            torus(mb, Me @ _T(0, 0, 0.036) @ _Rz(45 * sx * sy) @ _Rx(90), 0.026, 0.0065, mat="steel", n=12, seg=SEG_T, a0=-PI * 0.1,
                  a1=PI * 1.1)
    # ---- frente (-Y): placa de datos, borne de tierra, receptáculo de arranque auxiliar
    Mn = face_M((0.0, -Wy / 2 - 0.002, 0.0), (0, -1, 0))
    mb.box((-0.11, zs + 0.66, -0.002), (0.11, zs + 0.74, 0.0015), "sign_white", bevel=0.001, m=Mn @ _T(0.33, 0, 0))
    label(mb, "GENERATOR SET 10 KW", 0.013, "cable", Mn @ _T(0.33, zs + 0.693, 0.0015), depth=0.0008, res=2)
    Mg = face_M((0.62, -Wy / 2, zs + 0.12), (0, -1, 0))
    lathe(mb, [(0.0, 0.0), (0.008, 0.0), (0.008, 0.045), (0.0, 0.047)], seg=SEG_T, mat="steel", M=Mg)
    hexnut(mb, Mg @ _T(0, 0, 0.02), s=0.019, h=0.01, mat="steel")
    Ma = face_M((-0.62, -Wy / 2, zs + 0.2), (0, -1, 0))
    lathe(mb, [(0.0, 0.0), (0.04, 0.0), (0.04, 0.012), (0.028, 0.014), (0.028, 0.05), (0.032, 0.052), (0.032, 0.06), (0.0, 0.062)],
          seg=SEG, mat="cable", M=Ma)
    del r
    return mb


# ================================================================================================== pluma de acceso
def drop_arm_barrier(L=5.0, seed=0):
    """Pluma (barrera de brazo) manual con contrapeso: poste pivote de PTR 150 × 150 de 1,0 m con placa base y anclas en
    x = 0, pluma de aluminio Ø 90 mm de L m hacia +X con franjas rojo/blanco de 0,5 m (banda reflejante), contrapeso de placas
    atornilladas en el brazo corto (-X), horquilla de descanso Ø 89 mm en el extremo con candado, y letrero STOP colgado.
    Medidas: ELKA (plumas manuales hasta 7,5 m, contrapeso, apoyo obligatorio > 4 m, pluma blanca con franjas rojas),
    Workyard (poste de 1000 mm), Broxap (manual hasta 6 m). Frente -Y; pluma bajada (horizontal) a 0,95 m."""
    r = rng(seed)
    mb = MB()
    zp = 0.98
    # ---- poste pivote
    mb.box((-0.2, -0.2, 0.0), (0.2, 0.2, 0.02), "paint_yellow", bevel=0.004)
    for sx in (-1, 1):
        for sy in (-1, 1):
            Mb = _T(sx * 0.15, sy * 0.15, 0.02)
            hexnut(mb, Mb, s=0.024, h=0.016, mat="galvanized")
            lathe(mb, [(0.0, 0.0), (0.008, 0.0), (0.008, 0.032), (0.006, 0.035), (0.0, 0.035)], seg=SEG_T, mat="galvanized", M=Mb)
    rtube(mb, (0, 0, 0.02), (0, 0, zp - 0.05), 0.15, 0.15, "paint_yellow", up=(1, 0, 0), r=0.008)
    mb.box((-0.085, -0.085, zp - 0.055), (0.085, 0.085, zp - 0.045), "paint_yellow", bevel=0.002)
    for sy in (-1, 1):                                     # horquilla del pivote: dos placas de 10 mm
        mb.box((-0.11, sy * 0.06 - 0.005, zp - 0.05), (0.11, sy * 0.06 + 0.005, zp + 0.12), "paint_yellow", bevel=0.003)
    lathe(mb, [(0.0, -0.08), (0.016, -0.08), (0.016, 0.08), (0.0, 0.08)], seg=SEG, mat="steel", M=_T(0, 0, zp + 0.035) @ _Rx(90))
    for sy in (-1, 1):
        hexnut(mb, _T(0, sy * 0.066, zp + 0.035) @ _Rx(-90 * sy), s=0.036, h=0.02, mat="steel")
    # ---- pluma con franjas (segmentos de material distinto, sin calcas)
    Rb = 0.045
    xs = [0.12] + [0.5 * k for k in range(1, int(L / 0.5) + 1) if 0.5 * k < L - 0.03] + [L - 0.02]
    for i in range(len(xs) - 1):
        m = "sign_red" if i % 2 == 0 else "sign_white"
        mb.cyl((xs[i], 0, zp + 0.035), (xs[i + 1], 0, zp + 0.035), Rb, seg=SEG, mat=m, caps=False)
    lathe(mb, [(Rb, 0.0), (Rb + 0.002, 0.004), (Rb + 0.002, 0.03), (0.035, 0.036), (0.0, 0.037)], seg=SEG, mat="rubber",
          M=_T(L - 0.02, 0, zp + 0.035) @ _Ry(90))
    # abrazadera de la pluma en el pivote y brazo corto del contrapeso
    rtube(mb, (-0.75, 0, zp + 0.035), (0.2, 0, zp + 0.035), 0.1, 0.11, "paint_yellow", up=(0, 0, 1), r=0.008)
    mb.cyl((0.12, 0, zp + 0.035), (0.2, 0, zp + 0.035), Rb + 0.002, seg=SEG, mat="sign_red", caps=False)
    for k in range(4):                                     # placas de contrapeso de 20 kg atornilladas
        x0 = -0.72 + k * 0.052
        mb.box((x0, -0.13, zp - 0.12), (x0 + 0.048, 0.13, zp + 0.19), "steel", bevel=0.004)
    for sy in (-1, 1):
        mb.cyl((-0.735, sy * 0.08, zp + 0.13), (-0.5, sy * 0.08, zp + 0.13), 0.009, seg=SEG_T, mat="galvanized")
        hexnut(mb, _T(-0.735, sy * 0.08, zp + 0.13) @ _Ry(-90), s=0.027, h=0.016, mat="galvanized")
    # ---- horquilla de descanso con candado
    xr = L - 0.25
    mb.box((xr - 0.13, -0.13, 0.0), (xr + 0.13, 0.13, 0.016), "paint_yellow", bevel=0.003)
    lathe(mb, [(0.0, 0.016), (0.0445, 0.016), (0.0445, zp - 0.1), (0.0, zp - 0.1)], seg=SEG, mat="paint_yellow", M=_T(xr, 0, 0))
    for sy in (-1, 1):
        mb.box((xr - 0.04, sy * (Rb + 0.012) - 0.005, zp - 0.1), (xr + 0.04, sy * (Rb + 0.012) + 0.005, zp + 0.06), "paint_yellow",
               bevel=0.002)
    mb.box((xr - 0.04, -Rb - 0.017, zp - 0.105), (xr + 0.04, Rb + 0.017, zp - 0.1 + 0.012), "paint_yellow", bevel=0.002)
    lathe(mb, [(0.0, 0.0), (0.045, 0.0), (0.045, 0.006), (0.0, 0.006)], seg=SEG, mat="rubber", M=_T(xr, 0, zp - 0.088))
    # candado (cuerpo + arco) en la oreja
    Ml = _T(xr, -Rb - 0.03, zp + 0.02)
    mb.box((-0.02, -0.008, -0.055), (0.02, 0.008, -0.02), "steel", bevel=0.003, m=Ml)
    torus(mb, Ml @ _T(0, 0, -0.02) @ _Rx(90), 0.013, 0.0035, mat="steel", n=10, seg=SEG_T, a0=0.0, a1=PI)
    # ---- letrero STOP colgado del centro de la pluma
    xs_ = L * 0.55
    Ms = _T(xs_, -Rb - 0.003, zp - 0.06)
    oct_ = [(0.17 * math.cos(PI / 8 + k * PI / 4), 0.17 * math.sin(PI / 8 + k * PI / 4)) for k in range(8)]
    rings = [[Ms @ Vector((x, -t, z)) for (x, z) in oct_] for t in (0.0, 0.003)]
    loft_rings(mb, rings, "sign_red")
    label(mb, "STOP", 0.085, "sign_white", Ms @ _T(0, -0.003, -0.03) @ _Rx(90), depth=0.0012, res=2)
    for sx in (-1, 1):
        torus(mb, _T(xs_ + sx * 0.07, 0, zp + 0.035) @ _Ry(90), Rb + 0.004, 0.003, mat="galvanized", n=24, seg=SEG_T)
        mb.cyl((xs_ + sx * 0.07, -Rb - 0.002, zp + 0.03), (xs_ + sx * 0.07, -Rb - 0.002, zp + 0.11 - 0.06), 0.003, seg=SEG_T,
               mat="galvanized")
    del r
    return mb


# =========================================================================================================== trípode
def floodlight_tripod(seed=0):
    """Trípode de trabajo con dos reflectores LED: poste telescópico de aluminio (Ø 35 / 28 mm, con perilla de apriete), tres
    patas de Ø 22 mm abiertas con regatones de hule y brazos tensores a un collarín deslizable, barra en T con dos reflectores
    (carcasa de aluminio fundido con aletas de disipación, cristal, horquilla con perillas) a ~1,9 m, caja de conexiones y cable
    que baja por el poste, sale al piso y queda enrollado con su clavija. Origen: centro de las patas."""
    r = rng(seed)
    mb = MB()
    zc, zt = 0.62, 1.86
    # poste: tramo inferior Ø 35, superior Ø 28, abrazadera con perilla
    lathe(mb, [(0.0, 0.42), (0.0175, 0.42), (0.0175, 1.25), (0.019, 1.255), (0.019, 1.3), (0.0145, 1.305), (0.0, 1.305)], seg=SEG,
          mat="aluminium")
    lathe(mb, [(0.014, 1.3), (0.014, zt - 0.02), (0.0, zt - 0.02)], seg=SEG, mat="aluminium", caps=False)
    mb.cyl((0.019, 0, 1.278), (0.05, 0, 1.278), 0.004, seg=SEG_T, mat="steel")
    lathe(mb, [(0.0, 0.0), (0.013, 0.0), (0.013, 0.012), (0.0, 0.017)], seg=SEG, mat="plastic", M=_T(0.05, 0, 1.278) @ _Ry(90))
    # cabeza de patas y collarín
    lathe(mb, [(0.0, 0.40), (0.03, 0.40), (0.032, 0.43), (0.03, 0.47), (0.0, 0.47)], seg=SEG, mat="plastic")
    lathe(mb, [(0.0185, zc - 0.25), (0.03, zc - 0.25), (0.03, zc - 0.21), (0.0185, zc - 0.21)], seg=SEG, mat="plastic", caps=True)
    for k in range(3):
        a = math.radians(90 + 120 * k + float(r.uniform(-4, 4)))
        top = Vector((0.03 * math.cos(a), 0.03 * math.sin(a), 0.45))
        foot = Vector((0.62 * math.cos(a), 0.62 * math.sin(a), 0.018))
        mb.cyl(top, foot, 0.011, seg=SEG, mat="aluminium", caps=True)
        lathe(mb, [(0.0, 0.0), (0.016, 0.0), (0.016, 0.03), (0.012, 0.035), (0.0, 0.035)], seg=SEG, mat="rubber",
              M=_frame(foot, foot + (foot - top).normalized(), (0, 0, 1)) @ _Ry(-90) @ _T(0, 0, -0.005))
        mid = top.lerp(foot, 0.45)
        c0 = Vector((0.03 * math.cos(a), 0.03 * math.sin(a), zc - 0.23))
        rtube(mb, c0, mid, 0.012, 0.004, "steel", up=(-math.sin(a), math.cos(a), 0), r=0.0015)
    # barra en T y reflectores
    mb.cyl((-0.33, 0, zt), (0.33, 0, zt), 0.014, seg=SEG, mat="steel")
    lathe(mb, [(0.0, -0.035), (0.02, -0.035), (0.02, 0.025), (0.0, 0.025)], seg=SEG, mat="steel", M=_T(0, 0, zt - 0.01))
    for sx in (-1, 1):
        x = sx * 0.22
        ang = sx * 12.0
        Mh = _T(x, 0, zt + 0.03) @ _Rz(ang) @ _Rx(-18)
        for sy in (-1, 1):                                 # horquilla
            mb.box((sy * 0.165 - 0.004, -0.012, -0.03), (sy * 0.165 + 0.004, 0.012, 0.13), "steel", bevel=0.002, seg=1, m=Mh)
            lathe(mb, [(0.0, 0.0), (0.017, 0.0), (0.017, 0.014), (0.0, 0.019)], seg=SEG, mat="plastic",
                  M=Mh @ _T(sy * 0.17, 0, 0.1) @ _Ry(90 * sy))
        mb.box((-0.17, -0.012, -0.034), (0.17, 0.012, -0.026), "steel", bevel=0.002, seg=1, m=Mh)
        Mb = Mh @ _T(0, 0, 0.1)
        slab(mb, Mb @ _Rx(90) @ _T(0, 0, -0.03), 0.30, 0.22, 0.06, rc=0.02, re=0.008, mat="aluminium", nc=3, ne=2)
        mb.box((-0.135, -0.034, -0.095), (0.135, -0.029, 0.095), "glass", bevel=0.002, m=Mb)
        for k in range(9):                                 # aletas de disipación en la espalda
            xx = -0.12 + k * 0.03
            mb.box((xx - 0.0025, 0.03, -0.09), (xx + 0.0025, 0.055, 0.09), "aluminium", bevel=0.0, m=Mb)
    # caja de conexiones y cable
    rbox(mb, (-0.05, 0.014, zt - 0.2), (0.05, 0.075, zt - 0.08), "plastic", r=0.006)
    pts = [(0.0, 0.076, zt - 0.2), (0.0, 0.03, zt - 0.3), (0.0, 0.024, 1.0), (0.01, 0.025, 0.55), (0.12, 0.08, 0.12),
           (0.3, 0.2, 0.012), (0.75, 0.35, 0.012)]
    P = fillet(pts, 0.08, 3)
    tube_path(mb, P, 0.0045, seg=SEG_T, mat="cable", caps=True)
    # rollo de cable en el piso + clavija
    cx, cy = 0.95, 0.42
    coil = []
    for k in range(22):
        a = 2 * PI * k / 14 + PI
        rr_ = 0.16 + 0.012 * k / 14
        coil.append((cx + rr_ * math.cos(a), cy + rr_ * math.sin(a), 0.0046 + 0.0042 * min(1.0, k / 14)))
    tube_path(mb, [(0.75, 0.35, 0.012)] + coil[1:], 0.0045, seg=SEG_T, mat="cable", caps=True)
    end = Vector(coil[-1])
    rbox(mb, (end.x - 0.02, end.y - 0.07, 0.0), (end.x + 0.02, end.y - 0.005, 0.03), "plastic", r=0.006)
    return mb


# ========================================================================================================== torre de guardia
def _plate_bev(mb, outline, t, M, mat="galvanized", b=0.0015, rc=0.004):
    """Placa de acero de espesor t con contorno 2D `outline` (antihorario, plano XY local, z de 0 a t): esquinas de planta
    redondeadas (rc) y cantos rotos (b) arriba y abajo: nada de arista perfecta."""
    pp, _ = _rpoly(outline, [rc] * len(outline), [None] * len(outline), nseg=3)
    N2 = _loop_normals2(pp)
    loops = []
    for (inset, z) in ((b, 0.0), (0.0, b), (0.0, t - b), (b, t)):
        Q = pp - N2 * inset
        loops.append([(float(q[0]), float(q[1]), z) for q in Q])
    skin(mb, loops, mat, M, cap0=True, cap1=True)


def _weld(mb, pts, r=0.0035, mat="galvanized", closed=False):
    """Cordón de soldadura de filete: tubo de 12 lados con ondas de avance (rizos cada ~4 mm) siguiendo la junta."""
    P = np.asarray(pts, float)
    if closed:
        P = np.concatenate([P, P[:1]], 0)
    acc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    n = max(3, int(acc[-1] / 0.006))
    s = np.linspace(0, acc[-1], n + 1)
    Q = np.stack([np.interp(s, acc, P[:, k]) for k in range(3)], 1)
    rad = r * (1 + 0.12 * np.abs(np.sin(PI * s / 0.006)))
    R = _tube_rings(Q, rad, seg=12)
    K = len(Q)
    F = _grid_quads(K, 12, closed=True).tolist()
    F.append(list(range(11, -1, -1)))
    F.append(list(range((K - 1) * 12, K * 12)))
    _np_faces(mb, R.reshape(-1, 3), F, mat, soft=True)


def _bolt(mb, M, d=0.016, stub=0.012, mat="galvanized"):
    """Tornillo visto del lado de la tuerca: rondana plana, tuerca hexagonal con chaflán y punta de la rosca con chaflán.
    M: origen en la cara de apoyo, +Z hacia afuera."""
    lathe(mb, [(d * 0.55, 0.0), (d * 1.05, 0.0), (d * 1.08, 0.0012), (d * 1.05, d * 0.18), (d * 0.55, d * 0.18)], seg=24, mat=mat,
          M=M, caps=True)
    hexnut(mb, M @ _T(0, 0, d * 0.18), s=d * 1.5, h=d * 0.85, mat=mat)
    z0 = d * 0.18 + d * 0.85
    lathe(mb, [(0.0, z0 - 0.002), (d * 0.48, z0 - 0.002), (d * 0.48, z0 + stub * 0.7), (d * 0.38, z0 + stub), (0.0, z0 + stub)],
          seg=16, mat=mat, M=M)


def _ring_courses(half, rows, opening=None, pitch=0.5):
    """Hiladas de sacos en un cuadro (eje del muro a `half` del centro): las esquinas se traslapan alternando qué lados pasan
    de largo en cada hilada; opening = (lado, medio_ancho) deja un hueco (lado: 'b' = +Y)."""
    courses = []
    for k in range(rows):
        row = []
        through_y = (k % 2 == 0)                           # hiladas pares: lados frente/fondo de esquina a esquina
        sides = [("f", (0, -half), (1, 0)), ("b", (0, half), (1, 0)), ("l", (-half, 0), (0, 1)), ("r", (half, 0), (0, 1))]
        for (nm, c, d) in sides:
            is_y = nm in ("f", "b")
            full = (is_y == through_y)
            ext = half + (0.155 if full else -0.155)
            segs = [(-ext, ext)]
            if opening and nm == opening[0]:
                segs = [(-ext, -opening[1]), (opening[1], ext)]
            for (u0, u1) in segs:
                ln = u1 - u0
                if ln < 0.2:
                    continue
                n = max(1, int(round(ln / pitch)))
                p = ln / n
                off = 0.5 * p if (k // 2) % 2 and n > 1 else 0.0
                cuts = [u0] + [u0 + off + p * i for i in range(1, n)] + [u1] if off else [u0 + p * i for i in range(n + 1)]
                for i in range(len(cuts) - 1):
                    a_, b_ = cuts[i], cuts[i + 1]
                    if b_ - a_ < 0.15:
                        continue
                    um = (a_ + b_) / 2
                    x = c[0] + d[0] * um
                    y = c[1] + d[1] * um
                    ang = 0.0 if d[0] else 90.0
                    row.append((x, y, ang + (180.0 if (i + k) % 2 else 0.0), (b_ - a_) / 0.515 * 0.985, 1.0))
        courses.append(row)
    return courses


def guard_tower(seed=0):
    """Torre de vigilancia de acero galvanizado de 4 patas: plataforma a 5,0 m, patas de PTR 100 × 100 × 6 con talud (2,6 m
    entre ejes abajo, 2,2 m arriba) sobre dados de concreto con placa base de 320 × 320 × 20 (cantos rotos), cartabones de
    10 mm soldados (cordones de filete con rizos), 4 anclas de 3/4" con rondana y tuerca; travesaños de ángulo 75 × 6 y
    contravientos en X de solera 60 × 8 con placas de conexión y tornillos de 5/8" (rondana, tuerca, punta de rosca); piso de
    rejilla electrosoldada (soleras 30 × 3 a 33 mm, varilla transversal Ø 6 a 100 mm, marco de solera) sobre marco de PTR;
    barandal de tubo de 48 mm continuo con curvas de radio real (R 120 mm) en las esquinas, pasamanos a 1,07 m, intermedio a
    0,55 m y rodapié de 100 mm (OSHA 1910.29); muro de sacos terreros de 6 hiladas sobre el piso (hueco de acceso al fondo);
    techo a un agua de lámina acanalada sobre postes de 60 × 60 con placa base atornillada, largueros y pijas con rondana de
    neopreno; escalera marina en el fondo (+Y) con jaula (aros a partir de 2,4 m; OSHA 1910.28/ANSI A14.3: peldaños a 0,30 m,
    ancho libre 0,42 m). Origen: centro del pie de la torre; frente (lado vigilado) hacia -Y."""
    r = rng(seed)
    mb = MB()
    zd = 5.0
    zf = zd - 0.15
    b0, b1 = 1.3, 1.1
    zb = 0.27

    def half(z):
        return b0 + (b1 - b0) * (z - zb) / (zf - zb)
    st = "galvanized"
    tl = math.atan2(b0 - b1, zf - zb)                     # talud de las patas
    # ---- dados, placas base, anclas, cartabones, soldaduras y patas
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0, y0 = sx * b0, sy * b0
            slab(mb, _T(x0, y0, -0.08), 0.6, 0.6, 0.33, rc=0.03, re=0.02, mat="concrete", nc=4, ne=3)
            _plate_bev(mb, [(-0.16, -0.16), (0.16, -0.16), (0.16, 0.16), (-0.16, 0.16)], 0.02, _T(x0, y0, 0.25), st, b=0.002, rc=0.012)
            for ax in (-1, 1):
                for ay in (-1, 1):
                    Ma = _T(x0 + ax * 0.115, y0 + ay * 0.115, zb)
                    _bolt(mb, Ma, d=0.019, stub=0.022)
            top = Vector((sx * b1, sy * b1, zf))
            bot = Vector((x0, y0, zb))
            rtube(mb, bot, top, 0.1, 0.1, st, up=(1, 0, 0), r=0.008)
            # cordón perimetral de la pata sobre la placa base
            loop = [(x0 + 0.054 * math.cos(a), y0 + 0.054 * math.sin(a), zb + 0.003) for a in np.linspace(0, 2 * PI, 33)[:-1]]
            loop = [(x0 + max(-0.054, min(0.054, (p[0] - x0) * 1.42)), y0 + max(-0.054, min(0.054, (p[1] - y0) * 1.42)), p[2])
                    for p in loop]
            _weld(mb, loop, r=0.0035, closed=True)
            for (gx, gy) in ((1, 0), (0, 1)):              # cartabones de 10 mm a cada cara, soldados a pata y placa
                for sg in (-1, 1):
                    if gx:
                        M = _T(x0 + sg * 0.05, y0, zb) @ _Rz(0 if sg > 0 else 180) @ _Rx(90)
                        outward = sg * sx > 0
                    else:
                        M = _T(x0, y0 + sg * 0.05, zb) @ _Rz(90 if sg > 0 else -90) @ _Rx(90)
                        outward = sg * sy > 0
                    sh = 0.0437 * 0.17 * (1 if outward else -1)   # la cara de la pata se inclina con el talud
                    _plate_bev(mb, [(-0.004, 0.0), (0.1, 0.0), (0.1, 0.02), (-sh, 0.17), (-sh - 0.004, 0.17)], 0.01,
                               M @ _T(0, 0, -0.005), st, b=0.0012, rc=0.003)
                    for side in (-1, 1):                   # cordones de filete a pie y a la pata
                        q0 = M @ Vector((0.0, 0.002, side * 0.0075))
                        q1 = M @ Vector((0.095, 0.002, side * 0.0075))
                        q2 = M @ Vector((-sh, 0.16, side * 0.0075))
                        _weld(mb, [q0, q1], r=0.003)
                        _weld(mb, [q0, q2], r=0.003)
    # ---- travesaños (ángulo 75 × 6) y contravientos en X (solera 60 × 8) por cara y entrepiso
    levels = [zb + 0.1, 1.75, 3.3, zf - 0.08]
    faces = [((-1, -1), (1, -1)), ((1, -1), (1, 1)), ((1, 1), (-1, 1)), ((-1, 1), (-1, -1))]
    for (a_, b_) in faces:
        for li, z in enumerate(levels[1:-1], 1):
            h = half(z)
            pa = Vector((a_[0] * h, a_[1] * h, z))
            pb = Vector((b_[0] * h, b_[1] * h, z))
            out = Vector(((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2, 0)).normalized() * 0.055
            d = (pb - pa).normalized()
            p0, p1 = pa + d * 0.05 + out, pb - d * 0.05 + out
            T_ = (p1 - p0).normalized()
            B = T_.cross(Vector((0, 0, 1)))
            angle_l(mb, p0, p1, 0.075, 0.006, up=(0, 0, 1), s=1 if B.dot(-out) > 0 else -1, mat=st)
            for pp in (p0, p1):                            # soldadura del ángulo a la pata
                _weld(mb, [pp - Vector((0, 0, 0.0)) + d * 0.0, pp + Vector((0, 0, 0.074))], r=0.003)
        for li in range(len(levels) - 1):
            z0, z1 = levels[li], levels[li + 1]
            h0, h1 = half(z0), half(z1)
            out0 = Vector(((a_[0] + b_[0]) / 2, (a_[1] + b_[1]) / 2, 0)).normalized()
            for k, (pa_, pb_) in enumerate((((a_, z0, h0), (b_, z1, h1)), ((b_, z0, h0), (a_, z1, h1)))):
                (ca, za, ha), (cb, zb_, hb) = pa_, pb_
                pa = Vector((ca[0] * ha, ca[1] * ha, za + 0.06))
                pb = Vector((cb[0] * hb, cb[1] * hb, zb_ - 0.06))
                dd = (pb - pa).normalized()
                pa, pb = pa + dd * 0.08, pb - dd * 0.08
                o = out0 * (0.066 + 0.009 * k)
                Mf = _frame(pa + o, pb + o, out0)
                ln = (pb - pa).length
                rbox(mb, (0.0, -0.03, -0.004), (ln, 0.03, 0.004), st, r=0.0015, m=Mf)
                tp = 0.066 + 0.009 * k - 0.05 - 0.004          # placa de conexión: del paño de la pata a la solera
                for ll in (0.03, ln - 0.03):
                    _plate_bev(mb, [(-0.07, -0.06), (0.07, -0.06), (0.07, 0.06), (-0.07, 0.06)], tp,
                               Mf @ _T(ll, 0, -0.004 - tp), st, b=0.0012, rc=0.008)
                    _bolt(mb, Mf @ _T(ll, 0, 0.004), d=0.016, stub=0.008)
            # perno de cruce de las diagonales
            zc = (z0 + z1) / 2
            hc = half(zc)
            pc = Vector(((a_[0] + b_[0]) / 2 * hc, (a_[1] + b_[1]) / 2 * hc, zc)) + out0 * 0.083
            _bolt(mb, face_M(pc, out0), d=0.016, stub=0.008)
    # ---- marco del piso, rejilla electrosoldada, rodapié y barandal
    H2 = 1.32
    for (p0, p1) in (((-H2, -H2), (H2, -H2)), ((-H2, H2), (H2, H2)), ((-H2, -H2), (-H2, H2)), ((H2, -H2), (H2, H2)),
                     ((-H2, -0.45), (H2, -0.45)), ((-H2, 0.45), (H2, 0.45))):
        rtube(mb, (p0[0], p0[1], zd - 0.105), (p1[0], p1[1], zd - 0.105), 0.075, 0.15, st, up=(0, 0, 1), r=0.006)
    gx0, gx1 = -H2 + 0.035, H2 - 0.035
    ny = int((gx1 - gx0 - 0.01) / 0.033)
    for k in range(ny + 1):                                # soleras portantes de 30 × 3
        y = gx0 + 0.006 + k * (gx1 - gx0 - 0.012) / ny
        mb.box((gx0 + 0.004, y - 0.0015, zd - 0.03), (gx1 - 0.004, y + 0.0015, zd), st, bevel=0.0005, seg=1)
    rods = []
    for k in range(int((gx1 - gx0) / 0.1) + 1):            # varilla transversal Ø 6 hundida a ras en las soleras
        x = gx0 + 0.03 + k * 0.1
        if x > gx1 - 0.02:
            break
        rods.append(np.array([(x, gx0 + 0.004, zd - 0.0032), (x, gx1 - 0.004, zd - 0.0032)]))
    _tubes_np(mb, rods, 0.003, seg=12, mat=st, soft=True)
    for (p0, p1) in (((gx0, gx0), (gx1, gx0)), ((gx1, gx0), (gx1, gx1)), ((gx1, gx1), (gx0, gx1)), ((gx0, gx1), (gx0, gx0))):
        Mt = _frame(Vector((p0[0], p0[1], zd - 0.03)), Vector((p1[0], p1[1], zd - 0.03)), Vector((0, 0, 1)))
        Lb = (Vector(p1) - Vector(p0)).length
        rbox(mb, (-0.002, -0.0015, 0.0), (Lb + 0.002, 0.0015, 0.03), st, r=0.0006, m=Mt @ _T(0, 0, 0))   # solera de marco
    # rodapié de 100 mm (lámina de 6 mm) por dentro de los postes
    for (p0, p1) in (((-H2, -H2), (H2, -H2)), ((H2, -H2), (H2, H2)), ((H2, H2), (0.4, H2)), ((-0.4, H2), (-H2, H2)),
                     ((-H2, H2), (-H2, -H2))):
        a_, b_ = Vector((*p0, 0)), Vector((*p1, 0))
        Mt = _frame(Vector((a_.x, a_.y, zd)), Vector((b_.x, b_.y, zd)), Vector((0, 0, 1)))
        rbox(mb, (0.0, -0.003, 0.0), ((b_ - a_).length, 0.003, 0.1), st, r=0.0015, m=Mt)
    # barandal: pasamanos e intermedio continuos con curvas de R 120 mm; postes de 48 mm; hueco de acceso al fondo
    Hr = H2 - 0.03
    rail = [(0.4, Hr, 0.0), (Hr, Hr, 0.0), (Hr, -Hr, 0.0), (-Hr, -Hr, 0.0), (-Hr, Hr, 0.0), (-0.4, Hr, 0.0)]
    for zr_, rr_ in ((1.07, 0.024), (0.55, 0.021)):
        P = [(x, y, zd + zr_) for (x, y, _) in rail]
        tube_path(mb, P, rr_, seg=SEG, mat=st, bend=0.12, nseg=8, caps=True)
    cpost = Hr - 0.12 * (1 - 1 / math.sqrt(2))            # postes de esquina en el centro de la curva
    posts = [(-cpost, -cpost), (cpost, -cpost), (cpost, cpost), (-cpost, cpost), (0.0, -Hr), (Hr, 0.0), (-Hr, 0.0),
             (0.4, Hr), (-0.4, Hr)]
    for (x, y) in posts:
        lathe(mb, [(0.0, zd), (0.024, zd), (0.024, zd + 1.07), (0.017, zd + 1.083), (0.0, zd + 1.088)], seg=SEG, mat=st,
              M=_T(x, y, 0), caps=False)
        ring = [(x + 0.0265 * math.cos(a), y + 0.0265 * math.sin(a), zd + 0.002) for a in np.linspace(0, 2 * PI, 25)[:-1]]
        _weld(mb, ring, r=0.003, closed=True)              # pie del poste soldado al marco
    # ---- muro de sacos sobre el piso (hueco de acceso al fondo)
    bags = _bag_stack(_ring_courses(1.08, 6, opening=("b", 0.42)), seed, (-1.6, 1.6, -1.6, 1.6), lod=1)   # a 5 m de altura
    mb.join(bags, _T(0, 0, zd))
    # ---- techo a un agua: postes con placa base atornillada, marco, largueros, lámina acanalada y pijas con rondana
    zr_f, zr_b = zd + 2.25, zd + 2.05
    zr = lambda y: zr_f + (zr_b - zr_f) * (y + 1.22) / 2.44  # noqa: E731
    for (x, y) in ((-1.22, -1.22), (1.22, -1.22), (1.22, 1.22), (-1.22, 1.22)):
        rtube(mb, (x, y, zd + 0.012), (x, y, zr(y) - 0.06), 0.06, 0.06, st, up=(1, 0, 0), r=0.004)
        _plate_bev(mb, [(-0.06, -0.06), (0.06, -0.06), (0.06, 0.06), (-0.06, 0.06)], 0.012, _T(x, y, zd), st, b=0.0012, rc=0.008)
        for (dx, dy) in ((-0.042, -0.042), (0.042, 0.042)):
            _bolt(mb, _T(x + dx, y + dy, zd + 0.012), d=0.012, stub=0.004)
    for x in (-1.22, 1.22):
        rtube(mb, (x, -1.3, zr(-1.3) - 0.03), (x, 1.3, zr(1.3) - 0.03), 0.05, 0.06, st, up=(0, 0, 1), r=0.004)
    for y in (-1.22, -0.4, 0.4, 1.22):
        rtube(mb, (-1.35, y, zr(y) + 0.0), (1.35, y, zr(y) + 0.0), 0.05, 0.05, st, up=(0, 0, 1), r=0.004)
    Wr, pitch, A = 2.95, 0.0762, 0.009
    nw = int(Wr / pitch)
    xs = [-nw * pitch / 2 + pitch * k / 10 for k in range(nw * 10 + 1)]
    t = 0.0015
    slope = math.atan2(zr_b - zr_f, 2.44)

    def sheet_pt(x, y, off):
        zc = zr(y) + 0.025 + A + A * math.sin(2 * PI * x / pitch - PI / 2)
        return Vector((x, y, zc + off))
    rows = []
    for (y, off) in ((-1.5, 0.0), (1.48, 0.0), (1.48, -t), (-1.5, -t)):
        rows.append([mb.bm.verts.new(sheet_pt(x, y, off)) for x in xs])
    for i in range(4):
        A_, B_ = rows[i], rows[(i + 1) % 4]
        for k in range(len(xs) - 1):
            mb.face([A_[k], A_[k + 1], B_[k + 1], B_[k]], st).smooth = True
    mb.face([rows[0][0], rows[3][0], rows[2][0], rows[1][0]], st)
    mb.face([rows[0][-1], rows[1][-1], rows[2][-1], rows[3][-1]], st)
    for y in (-1.22, -0.4, 0.4, 1.22):
        for k in range(1, nw, 3):
            x = -nw * pitch / 2 + pitch * k
            p = sheet_pt(x, y, 0.0)
            Ms = _T(p.x, p.y, p.z) @ _Rx(math.degrees(slope))
            lathe(mb, [(0.0, -0.0005), (0.0085, -0.0005), (0.0085, 0.002), (0.006, 0.003), (0.0, 0.003)], seg=24, mat="rubber",
                  M=Ms)                                    # rondana de neopreno
            lathe(mb, [(0.0065, 0.003), (0.0075, 0.0036), (0.0075, 0.0045), (0.0, 0.0045)], seg=24, mat=st, M=Ms)
            hexnut(mb, Ms @ _T(0, 0, 0.0045), s=0.008, h=0.0055, mat=st)   # pija autotaladrante de cabeza hexagonal
    # ---- escalera marina con jaula (fondo, +Y)
    yl = 1.5
    ztop = zd + 1.1
    for sx in (-1, 1):
        rbox(mb, (sx * 0.235 - 0.006, yl - 0.03, 0.0), (sx * 0.235 + 0.006, yl + 0.03, ztop), st, r=0.0018)
        lathe(mb, [(0.0, -0.002), (0.07, -0.002), (0.07, 0.01), (0.0, 0.01)], seg=SEG, mat="concrete", M=_T(sx * 0.235, yl, 0.0))
    z = 0.3
    while z < zd + 0.05:
        lathe(mb, [(0.011, -0.229), (0.011, 0.229)], seg=SEG, mat=st, M=_T(0.0, yl, z) @ _Ry(90), caps=True)
        for sx in (-1, 1):                                 # soldadura del peldaño al larguero
            ring = [(sx * 0.2285, yl + 0.0125 * math.cos(a), z + 0.0125 * math.sin(a)) for a in np.linspace(0, 2 * PI, 17)[:-1]]
            _weld(mb, ring, r=0.0022, closed=True)
        z += 0.3
    for z in (1.75, 3.3, zf - 0.08):                       # ménsulas de la escalera a la cara del fondo
        h = half(z)
        for sx in (-1, 1):
            rbox(mb, (sx * 0.235 - 0.03, h + 0.05, z - 0.004), (sx * 0.235 + 0.03, yl - 0.03, z + 0.004), st, r=0.0015)
            _bolt(mb, _T(sx * 0.235, yl - 0.05, z + 0.004), d=0.012, stub=0.005)
    hoops = [2.4 + 0.9 * k for k in range(4)]
    hoops.append(ztop - 0.05)
    Rc = 0.36
    cy = yl + 0.05
    for z in hoops:
        path = [(-0.24, yl, z), (-Rc, cy, z)] + [(Rc * math.cos(a), cy + Rc * math.sin(a), z) for a in np.linspace(PI, 0, 25)][1:-1] + \
               [(Rc, cy, z), (0.24, yl, z)]
        sweep_frame(mb, [(-0.003, -0.025), (-0.0022, -0.0255), (0.0022, -0.0255), (0.003, -0.025), (0.003, 0.025), (0.0022, 0.0255),
                         (-0.0022, 0.0255), (-0.003, 0.025)], path, st, up=(0, 0, 1))
    for a in np.linspace(PI * 0.88, PI * 0.12, 5):
        p = Vector((Rc * math.cos(a), cy + Rc * math.sin(a), 0))
        nrm = Vector((math.cos(a), math.sin(a), 0))
        Mv = _frame(Vector((p.x, p.y, hoops[0] - 0.03)) + nrm * 0.006, Vector((p.x, p.y, hoops[-1] + 0.03)) + nrm * 0.006, nrm)
        rbox(mb, (0.0, -0.02, -0.003), (hoops[-1] - hoops[0] + 0.06, 0.02, 0.003), st, r=0.0012, m=Mv)
    del r, tl
    return mb


# ============================================================================================================ torre de luz
def _wheel(mb, M, R=0.31, w=0.165, mat_rim="paint_tan"):
    """Rueda de remolque: llanta con dibujo (costados abombados, hombros, ranuras) + rin de acero con 5 birlos. Eje = Z local."""
    hw = w / 2
    prof = [(R * 0.62, -hw * 0.82), (R * 0.8, -hw), (R * 0.93, -hw * 0.97), (R - 0.01, -hw * 0.82), (R, -hw * 0.6), (R, hw * 0.6),
            (R - 0.01, hw * 0.82), (R * 0.93, hw * 0.97), (R * 0.8, hw), (R * 0.62, hw * 0.82)]
    lathe(mb, prof, seg=36, mat="rubber", M=M, caps=False,
          rmod=lambda i, a, rr, z: rr - (0.006 if (i in (4, 5) and math.cos(18 * a) > 0.55) else 0.0))
    lathe(mb, [(R * 0.62, -hw * 0.82), (R * 0.6, -hw * 0.6), (R * 0.6, hw * 0.55), (R * 0.62, hw * 0.82)], seg=36, mat=mat_rim, M=M,
          caps=False)
    lathe(mb, [(R * 0.6, hw * 0.55), (R * 0.45, hw * 0.5), (R * 0.3, hw * 0.62), (0.07, hw * 0.66), (0.045, hw * 0.72), (0.0, hw * 0.74)],
          seg=SEG, mat=mat_rim, M=M)
    for k in range(5):
        a = 2 * PI * k / 5
        hexnut(mb, M @ _T(0.075 * math.cos(a), 0.075 * math.sin(a), hw * 0.66 - 0.002), s=0.019, h=0.012, mat="steel")


def _led_head(mb, M, w=0.42, h=0.3, d=0.075, tilt=0.0):
    """Reflector LED de torre: carcasa de aluminio con aletas, cristal templado, horquilla (fija) y cuerpo inclinado `tilt`°
    sobre el eje de las perillas. M: centro del reflector; mira hacia -Y local; la horquilla sube a h/2 + 0,085."""
    Mb = M @ _Rx(tilt)
    slab(mb, Mb @ _Rx(90) @ _T(0, 0, -d / 2), w, h, d, rc=0.025, re=0.01, mat="aluminium", nc=3, ne=2)
    mb.box((-w / 2 + 0.02, -d / 2 - 0.004, -h / 2 + 0.02), (w / 2 - 0.02, -d / 2 + 0.001, h / 2 - 0.02), "glass", bevel=0.002,
           seg=1, m=Mb)
    for k in range(9):
        x = -w / 2 + 0.04 + k * (w - 0.08) / 8
        mb.box((x - 0.003, d / 2 - 0.002, -h / 2 + 0.03), (x + 0.003, d / 2 + 0.03, h / 2 - 0.03), "aluminium", bevel=0.0, m=Mb)
    for sx in (-1, 1):
        mb.box((sx * (w / 2 + 0.012) - 0.005, -0.02, -0.02), (sx * (w / 2 + 0.012) + 0.005, 0.02, h / 2 + 0.08), "steel", bevel=0.002,
               seg=1, m=M)
        lathe(mb, [(0.0, 0.0), (0.022, 0.0), (0.022, 0.012), (0.0, 0.016)], seg=SEG, mat="plastic", M=M @ _T(sx * (w / 2 + 0.017), 0, 0)
              @ _Ry(90 * sx))
    mb.box((-w / 2 - 0.017, -0.02, h / 2 + 0.07), (w / 2 + 0.017, 0.02, h / 2 + 0.085), "steel", bevel=0.002, seg=1, m=M)


def light_tower(seed=0):
    """Torre de iluminación sobre remolque (tipo 4 × LED, mástil de 9 m: MOSA TF 4x240 LED, 3920 × 1410 × 2240 mm cerrada,
    9000 mm de altura máxima, 790 kg): remolque de un eje con lanza en A y argolla (lunette) militar, gato de apoyo con
    manivela, salpicaderas, 4 estabilizadores telescópicos con gato de tornillo y zapata, gabinete del generador (puertas,
    rejillas, ojo de izaje, tapón de combustible, escape), mástil telescópico de 4 tramos (izado) con malacate y cable, y barra
    con 4 reflectores LED a ~9 m. Largo en X (lanza hacia -X), panel de control hacia -Y. Origen: centro del eje en el piso."""
    r = rng(seed)
    mb = MB()
    paint = "paint_tan"
    zc = 0.47                                              # altura del chasís
    # ---- chasís, lanza en A, argolla y gato de apoyo
    for sy in (-1, 1):
        rtube(mb, (-1.05, sy * 0.48, zc), (1.25, sy * 0.48, zc), 0.06, 0.1, paint, up=(0, 0, 1), r=0.005)
        rtube(mb, (-1.05, sy * 0.48, zc), (-2.05, 0.0, zc), 0.06, 0.08, paint, up=(0, 0, 1), r=0.005)
    for x in (-1.0, -0.2, 0.5, 1.2):
        rtube(mb, (x, -0.45, zc), (x, 0.45, zc), 0.05, 0.08, paint, up=(0, 0, 1), r=0.004)
    rtube(mb, (-2.25, 0, zc), (-1.85, 0, zc), 0.07, 0.07, paint, up=(0, 0, 1), r=0.005)
    torus(mb, _T(-2.34, 0, zc) @ _Rx(90), 0.048, 0.018, mat="steel", n=24, seg=SEG_T)
    lathe(mb, [(0.0, zc - 0.32), (0.03, zc - 0.32), (0.03, zc + 0.25), (0.0, zc + 0.25)], seg=SEG, mat=paint, M=_T(-1.7, 0.09, 0))
    lathe(mb, [(0.024, zc - 0.43), (0.024, zc - 0.32)], seg=SEG, mat="steel", M=_T(-1.7, 0.09, 0), caps=False)
    lathe(mb, [(0.0, 0.0), (0.09, 0.0), (0.09, 0.012), (0.03, 0.03), (0.0, 0.03)], seg=SEG, mat="steel", M=_T(-1.7, 0.09, zc - 0.47))
    tube_path(mb, [(-1.7, 0.09, zc + 0.26), (-1.7, 0.09, zc + 0.3), (-1.58, 0.09, zc + 0.3), (-1.58, 0.09, zc + 0.37)], 0.007,
              seg=SEG_T, mat="steel", bend=0.02, nseg=3)
    lathe(mb, [(0.0, 0.0), (0.012, 0.0), (0.012, 0.06), (0.0, 0.065)], seg=SEG, mat="plastic", M=_T(-1.58, 0.09, zc + 0.36))
    rtube(mb, (-1.75, 0.03, zc - 0.02), (-1.75, 0.13, zc - 0.02), 0.06, 0.06, paint, up=(0, 0, 1), r=0.004)
    # ---- eje, ruedas y salpicaderas
    mb.cyl((0, -0.62, 0.31), (0, 0.62, 0.31), 0.03, seg=SEG, mat="steel")
    for sy in (-1, 1):
        _wheel(mb, _T(0, sy * 0.7, 0.31) @ _Rx(-90 * sy))
        path = [(0.36 * math.cos(a), sy * 0.7, 0.31 + 0.36 * math.sin(a)) for a in np.linspace(PI * 0.95, PI * 0.05, 14)]
        sweep_frame(mb, [(-0.11, -0.0015), (0.11, -0.0015), (0.11, 0.0015), (-0.11, 0.0015)], path, paint, up=(0, sy, 0))
    # ---- estabilizadores telescópicos con gato de tornillo
    for (x, sy) in ((-0.95, -1), (-0.95, 1), (1.15, -1), (1.15, 1)):
        rtube(mb, (x, sy * 0.4, zc - 0.08), (x, sy * 0.86, zc - 0.08), 0.08, 0.08, paint, up=(0, 0, 1), r=0.005)
        rtube(mb, (x, sy * 0.8, zc - 0.08), (x, sy * 1.02, zc - 0.08), 0.065, 0.065, "steel", up=(0, 0, 1), r=0.004)
        Mj = _T(x, sy * 0.99, 0.0)
        lathe(mb, [(0.0, 0.08), (0.035, 0.08), (0.035, zc + 0.12), (0.0, zc + 0.12)], seg=SEG, mat=paint, M=Mj)
        lathe(mb, [(0.0, 0.03), (0.018, 0.03), (0.018, 0.09), (0.0, 0.09)], seg=SEG, mat="steel", M=Mj)
        lathe(mb, [(0.0, 0.0), (0.11, 0.0), (0.11, 0.012), (0.04, 0.03), (0.0, 0.035)], seg=SEG, mat="steel", M=Mj)
        tube_path(mb, [(x, sy * 0.99, zc + 0.12), (x, sy * 0.99, zc + 0.16), (x + 0.11, sy * 0.99, zc + 0.16),
                       (x + 0.11, sy * 0.99, zc + 0.22)], 0.007, seg=SEG_T, mat="steel", bend=0.02, nseg=3)
    # ---- gabinete del generador
    zb = zc + 0.05
    Lh, Wh, Hh = 2.0, 1.2, 1.3
    xh = 0.1
    slab(mb, _T(xh, 0, zb), Lh, Wh, Hh, rc=0.04, re=0.03, mat=paint, nc=4, ne=3)
    for sy in (-1, 1):
        for xd in (-0.45, 0.45):
            Mf = face_M((xh + xd, sy * Wh / 2, 0), (0, sy, 0))
            wd, hd = 0.82, 1.0
            zd_ = zb + 0.12 + hd / 2
            slab(mb, Mf @ _T(0, zd_, -0.001), wd, hd, 0.004, rc=0.015, re=0.0015, mat=paint, nc=3, ne=1, re0=0.0, cap0=False)
            mb.cyl(Mf @ Vector((-wd / 2 - 0.004, zd_ - hd / 2 + 0.05, 0.006)), Mf @ Vector((-wd / 2 - 0.004, zd_ + hd / 2 - 0.05, 0.006)),
                   0.006, seg=SEG_T, mat=paint)
            dring_latch(mb, Mf @ _T(wd / 2 - 0.06, zd_, 0.003))
            if xd > 0:
                for k in range(8):
                    zz = zd_ + 0.12 + k * 0.035
                    mb.box((-0.3, -0.01, -0.003), (0.3, 0.01, 0.003), paint, bevel=0.0015, seg=1, m=Mf @ _T(0, zz, 0.006) @ _Rx(-30))
    Mp = face_M((xh - Lh / 2 - 0.001, 0, 0), (-1, 0, 0))
    mb.box((-0.35, zb + 0.45, -0.03), (0.35, zb + 1.05, 0.004), "cable", bevel=0.003, seg=1, m=Mp)
    for k in range(3):
        lathe(mb, [(0.0, 0.0), (0.03, 0.0), (0.032, 0.008), (0.028, 0.011), (0.0, 0.009)], seg=SEG, mat="steel",
              M=Mp @ _T(-0.2 + 0.2 * k, zb + 0.9, 0.004))
    for k in range(4):
        lathe(mb, [(0.0, 0.0), (0.011, 0.0), (0.011, 0.015), (0.0, 0.016)], seg=SEG, mat="sign_red" if k == 0 else "plastic",
              M=Mp @ _T(-0.24 + 0.16 * k, zb + 0.62, 0.004))
    label(mb, "LIGHT TOWER", 0.03, "sign_white", Mp @ _T(0, zb + 0.99 - 0.02, 0.004), depth=0.001, res=2)
    lathe(mb, [(0.0, zb + Hh), (0.045, zb + Hh), (0.045, zb + Hh + 0.015), (0.03, zb + Hh + 0.03), (0.0, zb + Hh + 0.032)], seg=SEG,
          mat="steel", M=_T(xh - 0.6, -0.35, 0))
    lathe(mb, [(0.0, zb + Hh - 0.01), (0.035, zb + Hh - 0.01), (0.035, zb + Hh + 0.12), (0.031, zb + Hh + 0.12), (0.031, zb + Hh)],
          seg=SEG, mat="steel", M=_T(xh - 0.75, 0.3, 0), caps=False)
    torus(mb, _T(xh - 0.2, 0, zb + Hh + 0.04) @ _Rx(90), 0.04, 0.012, mat="steel", n=16, seg=SEG_T, a0=0.0, a1=PI)
    mb.box((xh - 0.26, -0.03, zb + Hh - 0.005), (xh - 0.14, 0.03, zb + Hh + 0.04), "steel", bevel=0.004, seg=1)
    # ---- mástil telescópico izado (4 tramos) con pivote, malacate y cable
    xm, ym = xh + Lh / 2 + 0.11, 0.0
    mb.box((xm - 0.16, -0.14, zb + 0.1), (xm - 0.1, 0.14, zb + 0.75), paint, bevel=0.004)
    for sy in (-1, 1):
        mb.box((xm - 0.1, sy * 0.1 - 0.006, zb + 0.55), (xm + 0.02, sy * 0.1 + 0.006, zb + 0.8), "steel", bevel=0.003)
    mb.cyl((xm - 0.04, -0.12, zb + 0.72), (xm - 0.04, 0.12, zb + 0.72), 0.02, seg=SEG, mat="steel")
    secs = [(0.16, zb + 0.15, zb + 2.55), (0.135, zb + 2.35, zb + 4.75), (0.11, zb + 4.55, zb + 6.85), (0.085, zb + 6.65, 8.75)]
    for (wm, z0, z1) in secs:
        rtube(mb, (xm, ym, z0), (xm, ym, z1), wm, wm, "galvanized", up=(1, 0, 0), r=0.01)
        rtube(mb, (xm, ym, z1 - 0.12), (xm, ym, z1), wm + 0.014, wm + 0.014, "galvanized", up=(1, 0, 0), r=0.012)
    Mw = _T(xm + 0.09, -0.11, zb + 1.1)
    lathe(mb, [(0.0, -0.05), (0.06, -0.05), (0.06, -0.04), (0.035, -0.035), (0.035, 0.035), (0.06, 0.04), (0.06, 0.05), (0.0, 0.05)],
          seg=SEG, mat="steel", M=Mw @ _Rx(90))
    tube_path(mb, [(xm + 0.09, -0.16, zb + 1.1), (xm + 0.09, -0.21, zb + 1.1), (xm + 0.2, -0.21, zb + 1.1), (xm + 0.2, -0.27, zb + 1.1)],
              0.008, seg=SEG_T, mat="steel", bend=0.02, nseg=3)
    mb.cyl((xm + 0.09, -0.11, zb + 1.13), (xm + 0.09, -0.11, 8.7), 0.004, seg=SEG_T, mat="steel")
    # cable de potencia en espiral alrededor del mástil
    pts = []
    for k in range(0, 161):
        t = k / 160
        z = zb + 0.9 + (8.6 - zb - 0.9) * t
        a = t * 2 * PI * 9
        rr_ = 0.11 + 0.01 * math.sin(t * 40)
        pts.append((xm + rr_ * math.cos(a), ym + rr_ * math.sin(a), z))
    mb.tube(pts, 0.009, seg=SEG_T, mat="cable")
    # ---- barra de reflectores (4 LED) en la punta
    zt = 8.75
    lathe(mb, [(0.0, zt), (0.05, zt), (0.05, zt + 0.66), (0.0, zt + 0.66)], seg=SEG, mat="steel", M=_T(xm, ym, 0))
    for zbar in (zt + 0.15, zt + 0.62):                    # dos barras horizontales; los reflectores cuelgan de su horquilla
        rtube(mb, (xm - 0.78, ym - 0.055, zbar), (xm + 0.78, ym - 0.055, zbar), 0.05, 0.05, "steel", up=(0, 0, 1), r=0.004)
        for sx in (-1, 1):
            xx = xm + sx * 0.52
            _led_head(mb, _T(xx, ym - 0.055, zbar - 0.025 - 0.15 - 0.0775) @ _Rz(sx * 8), tilt=-14 if zbar > zt + 0.3 else -24)
    rbox(mb, (xm + 0.05, -0.08, zt - 0.25), (xm + 0.13, 0.08, zt - 0.02), "plastic", r=0.008)
    del r
    return mb


# ======================================================================================================== red de camuflaje
# ULCANS (Ultra Lightweight Camouflage Net System): módulo hexagonal ~32,2 × 27,9 ft (673 ft²) + rómbico 27,9 × 16,1 ft,
# postes seccionales de aluminio, separadores ("spreaders"), estacas y bolsa (armynavyoutdoors.com, Darley; TM 5-1080-250-12&P).
# La guarnición (garnish) es una lámina cortada con incisiones en U y en V cuyas solapas cuelgan o se rizan: geometría real
# (material "net" de DOS CARAS) sobre una red de soporte de cordel en rombos (~12 cm, cordel de 3 mm: medida estimada de
# fotos de redes LCSS/ULCANS; MIL-C-53004 / MIL-C-52765 no se pudieron consultar en línea).
def _drape(w, l, supports, ties, k_in=0.13, k_edge=0.1, h=0.2, iters=2500):
    """Campo de alturas de la red sobre una rejilla gruesa: membrana con peso (Poisson) fijada en los separadores (discos) y en
    los amarres de orilla; las orillas libres cuelgan como cadena entre amarres. Devuelve (xs, ys, Z)."""
    xs = np.linspace(-w / 2, w / 2, int(round(w / h)) + 1)
    ys = np.linspace(-l / 2, l / 2, int(round(l / h)) + 1)
    X, Y = np.meshgrid(xs, ys)
    Z = np.full(X.shape, 2.0)
    fixed = np.zeros(X.shape, bool)
    val = np.zeros(X.shape)
    for (px, py, ztop, rad) in supports:
        d = np.hypot(X - px, Y - py)
        m = d <= max(rad, h * 0.75)
        fixed |= m
        val = np.where(m, ztop + 0.04 * np.clip(1 - (d / max(rad, 1e-3)) ** 2, 0, 1), val)
    for (px, py, zz) in ties:
        i = int(np.argmin(np.abs(xs - px)))
        j = int(np.argmin(np.abs(ys - py)))
        fixed[j, i] = True
        val[j, i] = zz
    Z = np.where(fixed, val, Z)
    edge = np.zeros(X.shape, bool)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    for _ in range(iters):
        P = np.pad(Z, 1, mode="edge")
        avg = (P[:-2, 1:-1] + P[2:, 1:-1] + P[1:-1, :-2] + P[1:-1, 2:]) / 4.0
        Zn = avg - k_in * h * h / 4.0
        # orillas: cadena a lo largo de la orilla (más tensa por la relinga)
        Ze = Z.copy()
        Ze[0, 1:-1] = (Z[0, :-2] + Z[0, 2:]) / 2 - k_edge * h * h / 2
        Ze[-1, 1:-1] = (Z[-1, :-2] + Z[-1, 2:]) / 2 - k_edge * h * h / 2
        Ze[1:-1, 0] = (Z[:-2, 0] + Z[2:, 0]) / 2 - k_edge * h * h / 2
        Ze[1:-1, -1] = (Z[:-2, -1] + Z[2:, -1]) / 2 - k_edge * h * h / 2
        Zn = np.where(edge, 0.7 * Ze + 0.3 * Zn, Zn)
        Z = np.where(fixed, val, Zn)
    return xs, ys, Z


def _bilerp(xs, ys, Z, x, y):
    fx = (x - xs[0]) / (xs[1] - xs[0])
    fy = (y - ys[0]) / (ys[1] - ys[0])
    i = np.clip(np.floor(fx).astype(int), 0, len(xs) - 2)
    j = np.clip(np.floor(fy).astype(int), 0, len(ys) - 2)
    tx, ty = fx - i, fy - j
    return (Z[j, i] * (1 - tx) * (1 - ty) + Z[j, i + 1] * tx * (1 - ty) + Z[j + 1, i] * (1 - tx) * ty + Z[j + 1, i + 1] * tx * ty)


def camo_net(w=8.0, l=10.0, seed=0, poles=True):
    """Toldo de red de camuflaje de w (X) × l (Y) m centrado en el origen, como el sistema LCSS / ULCANS:
    - red de soporte de cordel de poliéster de 3 mm en rombos de 12 cm, con un nudo en cada cruce (12 lados, sombreado
      continuo), que sigue la caída de la red;
    - guarnición (garnish) de tela cortada: lámina de dos caras apoyada sobre la red, con incisiones en U y en V; cada
      lóbulo cortado cuelga por su bisagra a través de un rombo de la red (cae 55-85°, con curvatura y giro), y deja en la
      tela el hueco de su forma (geometría real, material 'net' de dos caras);
    - relinga perimetral de 10 mm con amarres de cordel cada 0,3 m;
    - postes seccionales de aluminio Ø 38 mm con separador (sombrilla de 0,48 m con nervios) en los interiores de ~3,4 m y
      postes de orilla de 2,3 m; la red forma picos en los separadores y cae por gravedad entre apoyos (membrana con peso);
      vientos de cuerda con estacas de varilla.
    poles=False: solo la red, la guarnición y la relinga (la misma forma, para colgarla sobre otra pieza)."""
    r = rng(seed)
    mb = MB()
    ph = float(r.uniform(0, 100))
    # ---- apoyos y caída
    nxp = max(1, int(round(w / 4.5)))
    nyp = max(1, int(round(l / 4.5)))
    inner = [(-w / 2 + w * (i + 0.5) / nxp, -l / 2 + l * (j + 0.5) / nyp) for i in range(nxp) for j in range(nyp)]
    inner = [(x + float(r.uniform(-0.15, 0.15)), y + float(r.uniform(-0.15, 0.15))) for (x, y) in inner]
    zi = [3.35 + float(r.uniform(-0.12, 0.12)) for _ in inner]
    edge_p = []
    for sx in (-1, 0, 1):
        for sy in (-1, 0, 1):
            if sx == 0 and sy == 0:
                continue
            edge_p.append((sx * w / 2, sy * l / 2))
    ze = [2.25 + float(r.uniform(-0.08, 0.08)) for _ in edge_p]
    supports = [(x, y, z + 0.045, 0.34) for (x, y), z in zip(inner, zi)]   # la red apoya en el domo del separador
    ties = [(x, y, z + 0.03) for (x, y), z in zip(edge_p, ze)]
    xs, ys, Z = _drape(w, l, supports, ties)
    wf1, wf2, wf3 = _sfield(r, 6, 0.6, 1.2), _sfield(r, 8, 2.5, 4.5), _sfield(r, 10, 7.0, 11.0)
    sup = np.array([(px, py) for (px, py, _, _) in supports]) if supports else np.zeros((0, 2))

    def zat(x, y):
        x = np.asarray(x, float)
        y = np.asarray(y, float)
        z = _bilerp(xs, ys, Z, x, y)
        P = np.stack([x, y, np.full(x.shape, ph)], -1)
        wr = 0.03 * wf1(P) + 0.014 * wf2(P) + 0.006 * wf3(P)
        if len(sup):
            near = np.min(np.hypot(x[..., None] - sup[:, 0], y[..., None] - sup[:, 1]), -1)
            wr = np.where(near < 0.5, np.abs(wr) * (near / 0.5), wr)
        return z + wr

    def nrm_at(x, y, e=0.02):
        zx = (zat(x + e, y) - zat(x - e, y)) / (2 * e)
        zy = (zat(x, y + e) - zat(x, y - e)) / (2 * e)
        n = np.stack([-zx, -zy, np.ones(np.shape(zx))], -1)
        return n / np.linalg.norm(n, axis=-1, keepdims=True)
    # ---- red de soporte: rombos de 12 cm (cordel de 3 mm), nudo en cada cruce, 7,5 mm bajo la tela
    s_ = 0.12
    rt2 = math.sqrt(2.0)
    hw_, hl_ = w / 2 - 0.02, l / 2 - 0.02
    umax = (hw_ + hl_) / rt2
    ks = np.arange(-int(umax / s_), int(umax / s_) + 1)
    paths = []
    for fam in (1, -1):
        for k in ks:
            c0 = k * s_                                     # u (o v) constante
            # puntos de la línea: x = (c0 + t)/√2, y = fam·(c0 - t)/√2 con t múltiplo de s_
            tt = np.arange(-int(umax / s_) - 1, int(umax / s_) + 2) * s_
            x = (c0 + tt) / rt2
            y = fam * (c0 - tt) / rt2
            ok = (np.abs(x) <= hw_) & (np.abs(y) <= hl_)
            if ok.sum() < 2:
                continue
            idx = np.flatnonzero(ok)
            x, y = x[idx[0]:idx[-1] + 1], y[idx[0]:idx[-1] + 1]
            paths.append(np.stack([x, y, zat(x, y) - 0.0075], 1))
    _tubes_np(mb, paths, 0.0015, seg=12, mat="fabric", soft=True)
    # nudos: botón de cordel en cada cruce
    kx = []
    for P in paths[:len(paths) // 2]:
        kx.append(P)
    Kn = np.concatenate(kx, 0) if kx else np.zeros((0, 3))
    na = 6
    an = 2 * PI * (np.arange(na) + 0.5) / na
    Vk, Fk = [], []
    for k, p in enumerate(Kn):
        o = k * (na + 2)
        rot = float(r.uniform(0, PI))
        ring = p + np.stack([0.0042 * np.cos(an + rot), 0.0042 * np.sin(an + rot), np.zeros(na)], 1)
        Vk.append(np.concatenate([ring, p + np.array([[0.0, 0.0, 0.0028], [0.0, 0.0, -0.0028]])], 0))
        for j in range(na):
            jj = (j + 1) % na
            Fk += [[o + j, o + jj, o + na], [o + jj, o + j, o + na + 1]]
    if Vk:
        _np_faces(mb, np.concatenate(Vk, 0), Fk, "fabric", soft=True)
    # ---- lóbulos de la guarnición. (a) en ~85 % de los rombos: el corte cuelga a través del rombo de la red; (b) cortes
    # chicos entre ellos cuya solapa, tiesa, se levanta o se riza hacia arriba (nunca atraviesan el cordel de abajo)
    lobes = []
    for i_ in range(-int(umax / s_) - 1, int(umax / s_) + 1):
        for j_ in range(-int(umax / s_) - 1, int(umax / s_) + 1):
            u, v = (i_ + 0.5) * s_, (j_ + 0.5) * s_
            cx, cy = (u + v) / rt2, (u - v) / rt2
            if abs(cx) > w / 2 - 0.2 or abs(cy) > l / 2 - 0.2:
                continue
            if len(sup) and np.min(np.hypot(sup[:, 0] - cx, sup[:, 1] - cy)) < 0.42:
                continue
            if r.uniform() > 0.85:
                continue
            ang = float(r.uniform(0, 2 * PI))
            ln = float(r.uniform(0.075, 0.125))
            wd = float(r.uniform(0.045, 0.072))
            kind = 0 if r.uniform() < 0.55 else 1          # 0: corte en U (punta redonda), 1: corte en V (punta aguda)
            d = np.array((math.cos(ang), math.sin(ang)))
            hx, hy = cx - d[0] * 0.03, cy - d[1] * 0.03
            lobes.append((hx, hy, d, ln, wd, kind, float(r.uniform(0.85, 1.4)), float(r.uniform(-0.5, 0.5))))
    nb_ = int(len(lobes) * 0.6)
    tries = 0
    pts_b = []
    while len(pts_b) < nb_ and tries < nb_ * 6:
        tries += 1
        cx, cy = float(r.uniform(-w / 2 + 0.2, w / 2 - 0.2)), float(r.uniform(-l / 2 + 0.2, l / 2 - 0.2))
        if len(sup) and np.min(np.hypot(sup[:, 0] - cx, sup[:, 1] - cy)) < 0.42:
            continue
        uu, vv = (cx + cy) / rt2 / s_, (cx - cy) / rt2 / s_
        if abs(uu - round(uu)) > 0.3 and abs(vv - round(vv)) > 0.3:   # lejos de los cordeles: ese hueco es de un lóbulo (a)
            continue
        pts_b.append((cx, cy))
    for (cx, cy) in pts_b:
        ang = float(r.uniform(0, 2 * PI))
        d = np.array((math.cos(ang), math.sin(ang)))
        ln = float(r.uniform(0.04, 0.07))
        wd = float(r.uniform(0.028, 0.045))
        lobes.append((cx - d[0] * ln / 2, cy - d[1] * ln / 2, d, ln, wd, int(r.uniform() < 0.5), -float(r.uniform(0.08, 0.3)),
                      float(r.uniform(-0.6, 0.6))))

    def hwf(t, wd, kind):
        t = np.clip(t, 0.0, 1.0)
        return wd / 2 * (np.sqrt(np.clip(1 - t ** 2.5, 0, 1)) if kind == 0 else (1 - t) ** 0.9)
    # ---- lámina de la guarnición: rejilla de 2 cm recortada por los huecos de los lóbulos (contornos interpolados)
    a = 0.02
    nx = int(round(w / a))
    ny = int(round(l / a))
    gx = np.linspace(-w / 2, w / 2, nx + 1)
    gy = np.linspace(-l / 2, l / 2, ny + 1)
    GX, GY = np.meshgrid(gx, gy)
    F = np.full(GX.shape, 1.0)
    for (hx, hy, d, ln, wd, kind, _, _) in lobes:
        i0 = max(0, int((hx - 0.13 + w / 2) / a))
        i1 = min(nx, int((hx + 0.13 + w / 2) / a) + 1)
        j0 = max(0, int((hy - 0.13 + l / 2) / a))
        j1 = min(ny, int((hy + 0.13 + l / 2) / a) + 1)
        X_, Y_ = GX[j0:j1 + 1, i0:i1 + 1] - hx, GY[j0:j1 + 1, i0:i1 + 1] - hy
        ap = X_ * d[0] + Y_ * d[1]
        bp = -X_ * d[1] + Y_ * d[0]
        sdf = np.maximum(np.maximum(np.abs(bp) - hwf(ap / ln, wd, kind), -ap), ap - ln)
        F[j0:j1 + 1, i0:i1 + 1] = np.minimum(F[j0:j1 + 1, i0:i1 + 1], sdf / 0.01)
    border = np.minimum(np.minimum(GX + w / 2, w / 2 - GX), np.minimum(GY + l / 2, l / 2 - GY))
    F = np.maximum(F, (0.1 - border) / 0.02)               # orilla continua donde corre la relinga
    for (px, py, _, _) in supports:
        F = np.maximum(F, 2.0 * (1 - np.hypot(GX - px, GY - py) / 0.4))
    Zg = zat(GX, GY)
    vid = {}
    bm = mb.bm
    nn = nx + 1

    def V(k):
        if k not in vid:
            j, i = divmod(k, nn)
            vid[k] = bm.verts.new((gx[i], gy[j], Zg[j, i]))
        return vid[k]
    eid = {}
    Ff = F.ravel()

    def E(p, q):
        key = (min(p, q), max(p, q))
        if key not in eid:
            k0, k1 = key
            f0, f1 = Ff[k0], Ff[k1]
            t = min(max(f0 / (f0 - f1), 0.04), 0.96)
            j0, i0 = divmod(k0, nn)
            j1, i1 = divmod(k1, nn)
            x = gx[i0] + (gx[i1] - gx[i0]) * t
            y = gy[j0] + (gy[j1] - gy[j0]) * t
            jx = 0.0025 * math.sin(x * 211 + y * 97 + ph)       # el corte no es limpio: hilos sueltos
            zz = Zg[j0, i0] + (Zg[j1, i1] - Zg[j0, i0]) * t
            eid[key] = bm.verts.new((x + jx, y - jx, zz + 0.0015 * math.sin(x * 157 - y * 61)))
        return eid[key]
    mi = mb.mi("net")
    sl = mb._soft_layer()
    idx = np.arange((ny + 1) * nn).reshape(ny + 1, nn)
    A_, B_, C_, D_ = idx[:-1, :-1], idx[:-1, 1:], idx[1:, 1:], idx[1:, :-1]
    alt = ((np.arange(nx)[None, :] + np.arange(ny)[:, None]) % 2).astype(bool)
    T1 = np.where(alt[..., None], np.stack([A_, B_, C_], -1), np.stack([A_, B_, D_], -1)).reshape(-1, 3)
    T2 = np.where(alt[..., None], np.stack([A_, C_, D_], -1), np.stack([B_, C_, D_], -1)).reshape(-1, 3)
    TT = np.concatenate([T1, T2], 0)
    ins = Ff[TT] >= 0
    for tri in TT[ins.all(1)].tolist():
        f_ = bm.faces.new([V(k) for k in tri])
        f_.material_index = mi
        f_.smooth = True
        f_[sl] = 1
    for tri in TT[ins.any(1) & ~ins.all(1)].tolist():
        vals = [Ff[k] for k in tri]
        poly = []
        for k in range(3):
            p, q = tri[k], tri[(k + 1) % 3]
            if vals[k] >= 0:
                poly.append(V(p))
            if (vals[k] >= 0) != (vals[(k + 1) % 3] >= 0):
                poly.append(E(p, q))
        for k in range(1, len(poly) - 1):
            try:
                f_ = bm.faces.new([poly[0], poly[k], poly[k + 1]])
            except ValueError:
                continue
            f_.material_index = mi
            f_.smooth = True
            f_[sl] = 1
    # ---- lóbulos: lámina con bisagra en la tela, cae por el rombo de la red con curvatura y giro
    nla, nlb = 6, 4
    Vl, Fl = [], []
    for li, (hx, hy, d, ln, wd, kind, phi0, twist) in enumerate(lobes):
        h = np.array((hx, hy, float(zat(np.array([hx]), np.array([hy]))[0]) + (0.0018 if phi0 > 0 else 0.0)))
        nz = nrm_at(np.array([hx]), np.array([hy]))[0]
        dd = np.array((d[0], d[1], 0.0))
        dd = dd - nz * dd.dot(nz)
        dd /= np.linalg.norm(dd)
        sd = np.cross(nz, dd)
        aa = np.concatenate([[-0.008], np.linspace(0.0, ln, nla - 1)])
        phi = phi0 * np.clip(aa / 0.014, 0, 1) ** 0.8 + (0.25 if phi0 > 0 else -0.15) * (np.clip(aa, 0, None) / ln) ** 1.5
        phi = np.where(aa < 0, 0.0, phi)
        stepv = np.stack([np.cos(phi)[:, None] * dd + 0 * nz, -np.sin(phi)[:, None] * nz], 0).sum(0)
        da = np.diff(aa, prepend=0.0)
        spine = h + np.cumsum(stepv * da[:, None], 0)
        psi = twist * np.clip(aa / ln, 0, 1)
        nf = np.cos(phi)[:, None] * nz + np.sin(phi)[:, None] * dd
        side = np.cos(psi)[:, None] * sd + np.sin(psi)[:, None] * nf
        hw = np.maximum(hwf(np.clip(aa, 0, None) / ln, wd, kind), 0.0015)
        bb = np.linspace(-1.0, 1.0, nlb)
        cup = 0.004 * (1 - bb ** 2)                        # la tela se acopa un poco
        P = spine[:, None, :] + side[:, None, :] * (hw[:, None] * bb[None, :])[..., None] + nf[:, None, :] * cup[None, :, None]
        o = li * nla * nlb
        Vl.append(P.reshape(-1, 3))
        Fl.extend((_grid_quads(nla, nlb) + o).tolist())
    if Vl:
        _np_faces(mb, np.concatenate(Vl, 0), Fl, "net", soft=True)
    # ---- relinga perimetral (cuerda de 10 mm) con amarres de cordel cada 0,3 m
    per = []
    for (x0, y0, x1, y1) in ((-w / 2, -l / 2, w / 2, -l / 2), (w / 2, -l / 2, w / 2, l / 2), (w / 2, l / 2, -w / 2, l / 2),
                             (-w / 2, l / 2, -w / 2, -l / 2)):
        n_ = max(2, int(math.hypot(x1 - x0, y1 - y0) / 0.1))
        for k in range(n_):
            per.append((x0 + (x1 - x0) * k / n_, y0 + (y1 - y0) * k / n_))
    per = np.array(per)
    # esquinas un poco redondeadas (la cuerda no dobla a 90° vivos)
    per = (np.roll(per, 1, 0) + 2 * per + np.roll(per, -1, 0)) / 4
    Pr = np.concatenate([per, (zat(per[:, 0], per[:, 1]) - 0.001)[:, None]], 1)
    Pr = np.concatenate([Pr, Pr[:2]], 0)
    _tubes_np(mb, [Pr], 0.005, seg=16, mat="canvas", soft=False, caps=False)
    acc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(Pr[:-2], axis=0), axis=1))])
    lash = []
    for s0 in np.arange(0.15, acc[-1], 0.3):
        i = int(np.searchsorted(acc, s0))
        i = min(max(i, 1), len(Pr) - 4)
        c = Pr[i]
        tg = Pr[i + 1] - Pr[i - 1]
        tg /= np.linalg.norm(tg)
        e1 = np.array((-tg[1], tg[0], 0.0))
        e2 = np.cross(tg, e1)
        a_ = np.linspace(0, 2 * PI * 1.5, 25)
        lash.append(c + np.outer(np.cos(a_), e1) * 0.0072 + np.outer(np.sin(a_), e2) * 0.0072 + np.outer(a_ / (2 * PI) * 0.0035, tg))
    _tubes_np(mb, lash, 0.001, seg=12, mat="fabric", soft=True)
    if not poles:
        return mb
    # ---- postes seccionales con separador (interiores) y postes de orilla con vientos y estacas
    def pole(x, y, ztop, spreader):
        lathe(mb, [(0.06, 0.0), (0.06, 0.008), (0.025, 0.02), (0.0, 0.022)], seg=SEG, mat="steel", M=_T(x, y, 0))
        z = 0.02
        while z < ztop - 0.05:
            z1 = min(z + 1.07, ztop)
            lathe(mb, [(0.019, z), (0.019, z1)], seg=SEG, mat="aluminium", M=_T(x, y, 0), caps=False)
            if z1 < ztop - 0.01:
                lathe(mb, [(0.0185, z1 - 0.04), (0.0215, z1 - 0.035), (0.0215, z1 + 0.035), (0.0185, z1 + 0.04)], seg=SEG,
                      mat="aluminium", M=_T(x, y, 0), caps=False)
            z = z1
        lathe(mb, [(0.019, ztop), (0.012, ztop + 0.006), (0.006, ztop + 0.01), (0.006, ztop + 0.075), (0.0, ztop + 0.08)], seg=SEG,
              mat="steel", M=_T(x, y, 0))
        if spreader:                                   # separador: domo de plástico de 0,48 m con nervios y cubo
            Ms = _T(x, y, ztop + 0.012)
            lathe(mb, [(0.0, 0.0), (0.03, 0.0), (0.06, 0.02), (0.24, 0.035), (0.245, 0.042), (0.06, 0.05), (0.03, 0.06), (0.0, 0.062)],
                  seg=40, mat="plastic", M=Ms, rmod=lambda i, a_, rr, z: rr * (1 + 0.02 * math.cos(8 * a_)) if i in (3, 4) else rr)
            for k in range(8):
                ang = math.radians(22.5 + 45 * k)
                mb.box((0.04, -0.004, 0.0), (0.22, 0.004, 0.028), "plastic", bevel=0.002, seg=2,
                       m=Ms @ _Rz(math.degrees(ang)) @ _T(0, 0, 0.004))
    for (x, y), z in zip(inner, zi):
        pole(x, y, z, True)
    stakes = []
    for (x, y), z in zip(edge_p, ze):
        pole(x, y, z, False)
        out = Vector((math.copysign(1, x) if abs(x) > 1e-3 else 0.0, math.copysign(1, y) if abs(y) > 1e-3 else 0.0, 0.0))
        dirs = [out.normalized()] if (out.x == 0 or out.y == 0) else [Vector((out.x, 0.0, 0)), Vector((0.0, out.y, 0))]
        for d in dirs:
            g = Vector((x, y, 0)) + d * 1.6 + Vector((d.y, -d.x, 0)) * float(r.uniform(-0.2, 0.2))
            stakes.append(g)
            tube_path(mb, catenary((x, y, z + 0.06), (g.x, g.y, 0.07), 0.03, n=16), 0.005, seg=16, mat="canvas", caps=True)
    # amarres intermedios de la orilla a estacas
    for (x0, y0, x1, y1) in ((-w / 2, -l / 2, w / 2, -l / 2), (-w / 2, l / 2, w / 2, l / 2), (-w / 2, -l / 2, -w / 2, l / 2),
                             (w / 2, -l / 2, w / 2, l / 2)):
        for t in (0.25, 0.75):
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            zz = float(zat(np.array([x]), np.array([y]))[0])
            d = Vector((math.copysign(1, x) if abs(x0 - x1) < 1e-6 else 0.0, math.copysign(1, y) if abs(y0 - y1) < 1e-6 else 0.0, 0))
            g = Vector((x, y, 0)) + d * 1.1
            stakes.append(g)
            tube_path(mb, catenary((x, y, zz - 0.01), (g.x, g.y, 0.07), 0.02, n=14), 0.0045, seg=16, mat="canvas", caps=True)
    for g in stakes:                                       # estaca de varilla con gancho, hincada
        tube_path(mb, [(g.x, g.y, -0.12), (g.x, g.y, 0.08), (g.x + 0.03, g.y, 0.1), (g.x + 0.05, g.y, 0.07)], 0.006, seg=16,
                  mat="steel", bend=0.015, nseg=5, caps=True)
    return mb
