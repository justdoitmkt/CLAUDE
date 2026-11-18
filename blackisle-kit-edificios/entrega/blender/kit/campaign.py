"""kit/campaign.py — equipo de campaña para MIL_1_almacen (bodega de armamento pesado en una nave de acero prefabricada de
30 × 18 m) y MIL_2_avanzada (puesto avanzado: tienda de campaña militar de armazón que funciona como expendio de munición y
armas). Época actual, ordenado, uso ligero (rozones, polvo y holguras; nada roto).

Regla R-AAA: cada pieza con su construcción real (tubos con radio de doblez, conectores y pernos, lámina doblada con canto
redondeado, soldaduras, malla de alambre real, lona subdividida con caída entre los miembros del armazón, costuras, ojillos,
cintas y cuerdas). Sin facetado: cilindros visibles de >= 24 lados, tubos delgados, cuerdas y cables de >= 14.

CONVENCIONES (todas las funciones devuelven un MB de kit.clinic; metros, Z arriba):
- Piezas de piso: origen en el piso (z = 0) al centro de la huella, frente (lado de uso / del cliente) hacia -Y.
- Piezas de muro (pegboard, extinguisher_station): espalda en el plano del muro y = 0, crecen hacia -Y; origen en el piso
  (pegboard: en el canto inferior del tablero) y centradas en X.
- Piezas de techo (high_bay_light): origen en el punto de cuelgue (gancho), cuelgan hacia -Z.
- string_lights(points, n) y hanging_sign: coordenadas absolutas de los puntos dados / origen en el punto de cuelgue.
- Funciones de ranuras: weapon_rack_slots, pallet_rack_slots y pegboard_hooks devuelven matrices / posiciones en el MISMO
  espacio local de su pieza (para colocar armas, tarimas y equipo de otros agentes).
Textos en inglés, genéricos; sin marcas, logotipos ni insignias reales (R4).

Materiales: steel, galvanized, aluminium, concrete, rubber, cable, plastic, glass, wood, wood_dark, paper, cardboard, enamel,
paint_yellow, sign_white, sign_red, sign_blue, sign_green, fabric y los nuevos de este modelo: canvas (lona OD, material de dos
caras), wood_od (madera pintada verde olivo), paint_od (acero pintado verde olivo), paint_tan, plywood, rack_orange (largueros),
rack_blue (postes de rack).

MEDIDAS (fuentes consultadas en la web, 2026-11-13):
- Tienda TEMPER 20 × 32 ft (DLA, ficha NSN 8340-01-196-6272): 6,10 × 9,75 m, cumbrera 10'6" (3,20 m), alero 6'9" (2,06 m);
  arcos a 8 ft (2,44 m) con 5 largueros (cumbrera, 2 aleros, 2 bases) idénticos (TM 10-8340-224-13); sin postes centrales.
- Rack selectivo: poste de 3" (76 mm) con perforación de gota, marco de 42" de fondo, largueros escalonados de 4" × 96" con
  escalón de 1-5/8", parrilla de alambre 46 × 42" con caída tipo cascada y 3 canales, malla 2,5 × 4" (Uline H-10518,
  Cisco-Eagle, Husky Rack, Ridg-U-Rak).
- Malla de seguridad: poste tubular de 2" cal. 14 con placa base, marco de ángulo 1-1/4", malla soldada cal. 10 de 2 × 1"
  a 2 × 2", altura 8'-2" con 2" libres al piso, bisagras de 4" y orejas para candado (WireCrafters 840, Cogan).
- Montacargas de contrapeso 2,5 t gas LP (Yale GC050VX): ancho 1,07 m, protector 2,13 m, mástil abajo 3,28 m (ritchiespecs).
- Anaquel sin tornillos 48 × 18 × 72" de 5 entrepaños, poste de ángulo ranurado (Hirsh / Global Industrial).
- Mesa plegable 72 × 30 × 29" con bastidor de acero (Lifetime 2924); silla plegable de acero: asiento 17", total 30-32",
  tubo de 7/8" (Global Industrial / Virco).
- Caja de munición M2A1: 11,75 × 6 × 7,5" exterior (Blackhawk / Lucky Gunner).
- Lámpara LED high-bay UFO 150 W: Ø 11-12,6", altura 4,6-8", cuelgue de gancho (Sunco, eLEDlights).
- Banco de trabajo 72 × 30" de acero, 34" de alto (Jamco / Butler Bros).
"""
import math

import bmesh
import bpy  # noqa: F401  (bpy antes que mathutils)
import numpy as np
from mathutils import Matrix, Vector, noise

from kit import port
from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rbox, rng, rr_profile, rtube  # noqa: F401
from kit.clinic_equipo import arc_solid, loft_rings, loop_tube, revolve, rtube_lo, sweep_frame, weld  # noqa: F401
from kit.clinic_equipo import extinguisher as _ce_extinguisher
from kit.clinic_equipo import text as etext
from kit.clinic_servicios import holed, rr_pts, rrframe, skin, slab  # noqa: F401

IN = 0.0254
SEG = 24          # lados de todo cilindro visible
SEG_T = 14        # lados de tubos delgados, cuerdas y cables (con el suavizado de 30° del kit no se facetan)


# ======================================================================================================== utilidades
def _f(x):
    return float(x)


def _jit(r, a):
    return _f(r.uniform(-a, a))


def _sstep(e0, e1, x):
    t = np.clip((np.asarray(x, float) - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _cosspace(a, b, n):
    """n + 1 muestras de a a b, densas en los extremos (para arrugas y pliegues que nacen en los apoyos)."""
    t = np.linspace(0.0, 1.0, n + 1)
    return a + (b - a) * (0.5 - 0.5 * np.cos(np.pi * t))


def _merge(base, forced, eps=0.0025):
    """Une muestras: las forzadas quedan exactas y se quitan las base a menos de eps de alguna forzada."""
    forced = sorted(set(round(_f(v), 7) for v in forced))
    out = [v for v in base if all(abs(v - q) > eps for q in forced)] + forced
    out = sorted(out)
    res = [out[0]]
    for v in out[1:]:
        if v - res[-1] > 1e-6:
            res.append(v)
    return np.array(res)


def _noise_arr(A, B, f, seed, C=None):
    """Ruido de Perlin (mathutils) evaluado en arreglos (misma forma)."""
    A = np.asarray(A, float)
    B = np.asarray(B, float)
    Cc = np.zeros_like(A) if C is None else np.asarray(C, float)
    out = np.array([noise.noise(Vector((a * f + seed * 7.31, b * f - seed * 3.7, c * f))) for a, b, c in
                    zip(A.ravel(), B.ravel(), Cc.ravel())])
    return out.reshape(A.shape)


def _ridges(U, V, specs):
    """Arrugas: crestas gaussianas que se adelgazan hacia las puntas. spec = (cu, cv, ángulo, largo, ancho, alto)."""
    D = np.zeros_like(U)
    for (cu, cv, ang, length, w, A) in specs:
        du, dv = U - cu, V - cv
        ca, sa = math.cos(ang), math.sin(ang)
        al, pe = du * ca + dv * sa, -du * sa + dv * ca
        env = np.clip(1 - (2 * al / length) ** 2, 0, 1)
        we = w * (0.45 + 0.55 * np.sqrt(env))
        D += A * np.exp(-(pe / np.maximum(we, 1e-4)) ** 2) * env ** 1.5
    return D


class _Grid:
    """Rejilla de vértices creada bajo demanda (sin vértices sueltos). P: (nu, nv, 3); mask[i, j]: celda (i, j) emitida."""

    def __init__(self, mb, P, mat, mask=None, smooth=True):
        self.mb, self.P, self.V = mb, P, {}
        nu, nv = P.shape[0], P.shape[1]
        mi = mb.mi(mat)
        for i in range(nu - 1):
            for j in range(nv - 1):
                if mask is not None and not mask[i, j]:
                    continue
                f = mb.bm.faces.new([self.v(i, j), self.v(i + 1, j), self.v(i + 1, j + 1), self.v(i, j + 1)])
                f.material_index = mi
                f.smooth = smooth

    def v(self, i, j):
        k = (i, j)
        if k not in self.V:
            self.V[k] = self.mb.bm.verts.new(Vector(self.P[i, j]))
        return self.V[k]


def _grid_normals(P):
    """Normales por vértice de una rejilla (nu, nv, 3) (sentido dP/du × dP/dv)."""
    N = np.cross(np.gradient(P, axis=0), np.gradient(P, axis=1))
    return N / np.maximum(np.linalg.norm(N, axis=-1, keepdims=True), 1e-12)


def _slab_grid(mb, P, N, t0, t1, mat):
    """Sólido delgado cerrado que sigue una superficie: rejilla P (nu, nv, 3) desplazada t0 y t1 por las normales N.
    Parches de refuerzo, mallas mosquiteras, solapas."""
    A = P + N * t0
    B = P + N * t1
    nu, nv = P.shape[0], P.shape[1]
    VA = [[mb.bm.verts.new(Vector(A[i, j])) for j in range(nv)] for i in range(nu)]
    VB = [[mb.bm.verts.new(Vector(B[i, j])) for j in range(nv)] for i in range(nu)]
    mi = mb.mi(mat)

    def F(q):
        f = mb.bm.faces.new(q)
        f.material_index = mi
        f.smooth = True
    for i in range(nu - 1):
        for j in range(nv - 1):
            F([VB[i][j], VB[i + 1][j], VB[i + 1][j + 1], VB[i][j + 1]])
            F([VA[i][j], VA[i][j + 1], VA[i + 1][j + 1], VA[i + 1][j]])
    for i in range(nu - 1):
        F([VA[i][0], VA[i + 1][0], VB[i + 1][0], VB[i][0]])
        F([VB[i][-1], VB[i + 1][-1], VA[i + 1][-1], VA[i][-1]])
    for j in range(nv - 1):
        F([VB[0][j], VB[0][j + 1], VA[0][j + 1], VA[0][j]])
        F([VA[-1][j], VA[-1][j + 1], VB[-1][j + 1], VB[-1][j]])


def _frame_z(p, z_axis, x_hint=(1, 0, 0)):
    """Matriz con origen p y eje Z local = z_axis (X local lo más cerca de x_hint)."""
    Z = Vector(z_axis).normalized()
    X = Vector(x_hint)
    X = (X - Z * X.dot(Z))
    if X.length < 1e-6:
        X = Vector((0, 1, 0)) - Z * Z.y
    X.normalize()
    Y = Z.cross(X)
    return Matrix(((X.x, Y.x, Z.x, p[0]), (X.y, Y.y, Z.y, p[1]), (X.z, Y.z, Z.z, p[2]), (0, 0, 0, 1)))


def _fillet2d(pts, radii, nseg):
    """Polilínea 2D con esquinas redondeadas por ARCOS reales (radio por esquina)."""
    P = [np.array(p, float) for p in pts]
    out = [P[0]]
    for i in range(1, len(P) - 1):
        r = radii[i - 1] if isinstance(radii, (list, tuple)) else radii
        a, b, c = P[i - 1], P[i], P[i + 1]
        d0 = (a - b) / np.linalg.norm(a - b)
        d1 = (c - b) / np.linalg.norm(c - b)
        th = math.acos(max(-1.0, min(1.0, float(d0 @ d1))))
        if r <= 0 or th > PI - 1e-4:
            out.append(b)
            continue
        t = r / math.tan(th / 2)
        bis = (d0 + d1) / np.linalg.norm(d0 + d1)
        ctr = b + bis * r / math.sin(th / 2)
        p0, p1 = b + d0 * t, b + d1 * t
        a0 = math.atan2(p0[1] - ctr[1], p0[0] - ctr[0])
        a1 = math.atan2(p1[1] - ctr[1], p1[0] - ctr[0])
        da = (a1 - a0 + PI) % (2 * PI) - PI
        for k in range(nseg + 1):
            ang = a0 + da * k / nseg
            out.append(ctr + r * np.array([math.cos(ang), math.sin(ang)]))
    out.append(P[-1])
    return np.array(out)


def _resample2d(P, step):
    S = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    n = max(2, int(math.ceil(S[-1] / step)) + 1)
    s = np.linspace(0, S[-1], n)
    return np.stack([np.interp(s, S, P[:, 0]), np.interp(s, S, P[:, 1])], -1)


def _arclen(P):
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])


def _normals2d(P):
    T = np.gradient(P, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    return np.stack([-T[:, 1], T[:, 0]], -1)


def _tube(mb, pts, r, seg=SEG_T, mat="steel", caps=True, radii=None):
    """Tubo / cuerda por una polilínea (transporte paralelo), caras suaves."""
    n0 = len(mb.bm.faces)
    mb.tube([tuple(p) for p in pts], r, seg=seg, mat=mat, caps=caps, radii=radii)
    mb.bm.faces.ensure_lookup_table()
    for f in mb.bm.faces[n0:]:
        f.smooth = True


def _catenary(p0, p1, sag, n=8):
    p0, p1 = Vector(p0), Vector(p1)
    return [tuple(p0.lerp(p1, k / n) - Vector((0, 0, sag * 4 * (k / n) * (1 - k / n)))) for k in range(n + 1)]


def _cyl(mb, p0, p1, r, mat="steel", seg=SEG, caps=True, r1=None):
    n0 = len(mb.bm.faces)
    mb.cyl(p0, p1, r, seg=seg, mat=mat, caps=caps, r1=r1)
    mb.bm.faces.ensure_lookup_table()
    for f in mb.bm.faces[n0:]:
        f.smooth = True


def _lathe(mb, prof, M, mat="steel", seg=SEG, closed=False):
    """Torneado alrededor de Z local con caras suaves (aristas duras las marca el ángulo de 30° del kit)."""
    n0 = len(mb.bm.faces)
    revolve(mb, prof, mat, seg=seg, M=M, closed=closed)
    mb.bm.faces.ensure_lookup_table()
    for f in mb.bm.faces[n0:]:
        f.smooth = True


def _strap(mb, path, w=0.025, t=0.002, up=(1, 0, 0), mat="fabric"):
    """Cinta plana de reata (w ancho en `up`, t espesor) barrida por una trayectoria plana perpendicular a `up`."""
    sweep_frame(mb, rr_profile(t, w, min(t * 0.45, 0.0009), n=1), path, mat, up=up)


def _ring(mb, M, R, r, seg=16, sseg=SEG_T, mat="steel"):
    """Aro de alambre (argolla, D, eslabón redondo) en el plano XY local."""
    loop_tube(mb, [tuple(M @ Vector((R * math.cos(a), R * math.sin(a), 0))) for a in [2 * PI * k / seg for k in range(seg)]],
              r, seg=sseg, mat=mat, normal=tuple(M.to_3x3() @ Vector((0, 0, 1))))


def _grommet(mb, M, ro=0.0115, ri=0.0058, mat="steel"):
    """Ojillo metálico: anillo con ceja abombada que sobresale 1,8 mm de la cara (z local = normal de la lona) y su boca
    oscura (lona y cuerda vistas por el agujero)."""
    _lathe(mb, [(ri, -0.0004), (ro, -0.0004), (ro - 0.0012, 0.0014), (ri + 0.0015, 0.0018), (ri, 0.0008)], M, mat, seg=14, closed=True)
    _lathe(mb, [(0.0, -0.0003), (ri + 0.0002, 0.0), (0.0, 0.0003)], M, "cable", seg=14)


def _circ_tangent(c, rho, G, ccw=True):
    """Ángulo del punto de una circunferencia (centro c, radio rho, en 2D) desde el que sale la tangente hacia G
    recorriéndola en sentido antihorario."""
    g = (G[0] - c[0], G[1] - c[1])
    D = math.hypot(*g)
    phi = math.atan2(g[1], g[0])
    return phi - math.acos(min(rho / D, 1.0))


def _sling_path(pc, zc, rho, A, G, n=14):
    """Trayectoria 2D (p = distancia hacia afuera del muro, z) de una cinta que baja por dentro de un rollo de lona
    (entre el muro y el rollo), le da la vuelta por abajo, sube por fuera, pasa por encima y llega al punto G."""
    pts = [A, (pc - rho, zc + 0.02), (pc - rho, zc)]
    th_d = _circ_tangent((pc, zc), rho, G) % (2 * PI)
    a0, a1 = PI, 2 * PI + th_d
    nn = max(6, int(n * (a1 - a0) / (2 * PI)))
    for k in range(1, nn + 1):
        a = a0 + (a1 - a0) * k / nn
        pts.append((pc + rho * math.cos(a), zc + rho * math.sin(a)))
    pts.append(G)
    return pts


def _canvas_roll(mb, M, L, R, seed=0, zfun=None, seg=SEG, nst=None, mat="canvas", step=0.0025, end_dish=0.012):
    """Rollo de lona (pared o solapa enrollada): eje X local de 0 a L, centro en (y, z) = (0, zfun(x)). Sección en espiral
    (la orilla libre de la última vuelta deja un escalón de `step` a lo largo del rollo), bultos irregulares del enrollado
    flojo, extremos hundidos en cono con la espiral de las capas a la vista."""
    r = rng(seed)
    nst = nst or max(4, int(L / 0.12)) + 1
    xs = np.linspace(0.0, L, nst)
    ph = [_f(v) for v in r.uniform(0, 2 * PI, 4)]
    zfun = zfun or (lambda x: 0.0)
    a_edge = _f(r.uniform(-2.4, -1.6))                       # la orilla libre queda abajo-afuera
    rings = []
    for x in xs:
        ring = []
        for k in range(seg):
            a = a_edge + 2 * PI * k / seg
            lump = 1.0 + 0.045 * math.sin(2 * a + ph[0] + x * 3.1) + 0.03 * math.sin(3 * a + ph[1] - x * 5.3) \
                + 0.025 * math.sin(x * 9.0 + ph[2])
            rr = R * lump + step * (k / seg - 0.5)
            ring.append(Vector((x, rr * math.cos(a), zfun(x) + rr * math.sin(a))))
        rings.append(ring)
    V = [[mb.bm.verts.new(M @ p) for p in ring] for ring in rings]
    mi = mb.mi(mat)
    for i in range(nst - 1):
        for k in range(seg):
            f = mb.bm.faces.new([V[i][k], V[i + 1][k], V[i + 1][(k + 1) % seg], V[i][(k + 1) % seg]])
            f.material_index = mi
            f.smooth = True
    for (i, sx) in ((0, -1), (nst - 1, 1)):                  # extremos en cono hundido + espiral de capas
        x = xs[i]
        cz = zfun(x)
        cv = mb.bm.verts.new(M @ Vector((x - sx * end_dish, 0.0, cz)))
        for k in range(seg):
            q = [V[i][k], V[i][(k + 1) % seg], cv]
            f = mb.bm.faces.new(q if sx < 0 else q[::-1])
            f.material_index = mi
            f.smooth = True
        sp = []
        nt = 2.2
        npt = int(nt * 10)
        for k in range(npt + 1):
            u = k / npt
            a = a_edge + 2 * PI * nt * u
            rr = R * (0.22 + 0.7 * u)
            dish = end_dish * (1 - rr / R) - 0.0004
            sp.append((x - sx * dish, rr * math.cos(a), cz + rr * math.sin(a)))
        _tube(mb, [tuple(M @ Vector(p)) for p in sp], 0.0016, seg=5, mat=mat)
    return xs


# ======================================================================================================== tienda de campaña
R_A = 0.0222                 # tubo de arco: Ø 44,5 mm de aluminio (estimado; TEMPER usa tubo de aluminio de ~1,75")
R_P = 0.0190                 # larguero (purlin): Ø 38 mm
EAVE, RIDGE = 2.06, 3.20     # alero 6'9" y cumbrera 10'6" (DLA)


def _tent_geo(L, W):
    """Geometría base: perfil del armazón (eje del tubo), perfil de la lona y posiciones de los arcos."""
    g = {}
    hw = W / 2 - 0.05                                        # eje de las patas
    o = R_A + 0.006                                          # la lona descansa en los conectores (6 mm sobre el tubo)
    g["hw"], g["o"] = hw, o
    zr = RIDGE - o
    ze = EAVE - 0.02
    for _ in range(3):
        pf = _fillet2d([(-hw, 0.0), (-hw, ze), (0.0, zr), (hw, ze), (hw, 0.0)], [0.24, 0.5, 0.24], 24)
        zr += RIDGE - o - pf[:, 1].max()
        alpha = math.atan2(zr - ze, hw)
        ze = EAVE - o * (1 - math.sin(alpha)) / math.cos(alpha)
    pf = _resample2d(pf, 0.01)
    g["pf"] = pf
    g["alpha"] = alpha
    Nf = _normals2d(pf)
    g["Nf"] = Nf
    Sf = _arclen(pf)
    g["Sf"] = Sf
    i_ks = int(np.argmax(pf[:, 0] > -hw + 1e-5))            # arranque de la rodilla (el tubo deja la vertical)
    slope = np.diff(pf[:, 1]) / np.maximum(np.diff(pf[:, 0]), 1e-9)
    ta = math.tan(alpha)
    i_ke = i_ks + int(np.argmax(np.abs(slope[i_ks:] - ta) < 2e-3))          # fin de la rodilla (empieza el par recto)
    i_rs = i_ke + int(np.argmax(np.abs(slope[i_ke:] - ta) > 2e-3))          # arranque del arco de cumbrera
    i_r = int(np.argmax(pf[:, 1]))
    g["i_ks"], g["i_ke"], g["i_rs"], g["i_r"] = i_ks, i_ke, i_rs, i_r
    g["z_ks"] = pf[i_ks, 1]
    i_e = (i_ks + i_ke) // 2                                 # larguero de alero: a media rodilla
    g["i_e"] = i_e
    g["f_e"] = Sf[i_e]                                       # s del armazón: larguero de alero y cumbrera
    g["f_r"] = Sf[i_r]
    # arcos
    xa = L / 2 - 0.045
    g["xs"] = list(np.linspace(-xa, xa, 5))
    # perfil de la lona del techo: dobladillo -> faldón (valance) -> rodilla -> cumbrera -> ... (de -Y a +Y)
    off = pf + Nf * o
    z_ks = g["z_ks"]
    yv = hw + o
    val = np.array([(-(yv + 0.022), z_ks - 0.170), (-(yv + 0.034), z_ks - 0.180), (-(yv + 0.034), z_ks - 0.120),
                    (-(yv + 0.031), z_ks - 0.060), (-(yv + 0.020), z_ks - 0.025), (-(yv + 0.006), z_ks - 0.006)])
    mid = off[i_ks:len(off) - i_ks]
    C = np.concatenate([val, mid, val[::-1] * np.array([-1.0, 1.0])])
    S = _arclen(C)
    g["C"], g["S"], g["N"] = C, S, _normals2d(C)
    ns = len(val)

    def sc(i):                                               # índice del armazón -> s de la lona
        return S[ns + (i - i_ks)]
    g["s_hem"] = S[1]
    g["s_vb"] = S[1]                                          # orilla inferior del faldón
    g["s_ks"] = sc(i_ks)
    g["s_e0"] = sc(i_e)
    g["s_ke"] = sc(i_ke)
    g["s_rs"] = sc(i_rs)
    g["s_r"] = sc(i_r)
    g["s_tot"] = S[-1]
    g["s_e1"] = S[-1] - g["s_e0"]
    g["z_vb"] = z_ks - 0.18
    g["Yw"] = hw + R_A + 0.020                               # plano de las paredes laterales
    g["z_wt"] = z_ks - 0.06                                  # remate superior de la pared lateral (tras el faldón)
    g["Xe"] = L / 2 - 0.003                                  # plano de los testeros
    g["Ye"] = hw + R_A + 0.002                               # orilla lateral del testero (tras el faldón)
    # contorno superior del testero: lona a 12 mm por dentro de la del techo
    g["top"] = pf + Nf * (o - 0.012)
    return g


def _roof_eval(g, X, Ss, D):
    """Punto de la lona del techo para (x, s) con desplazamiento D por la normal (positivo = hacia afuera)."""
    C, S, N = g["C"], g["S"], g["N"]
    cy = np.interp(Ss, S, C[:, 0])
    cz = np.interp(Ss, S, C[:, 1])
    ny = np.interp(Ss, S, N[:, 0])
    nz = np.interp(Ss, S, N[:, 1])
    nn = np.maximum(np.hypot(ny, nz), 1e-9)
    ny, nz = ny / nn, nz / nn
    return np.stack([np.broadcast_to(X, cy.shape) if np.ndim(X) else np.full_like(cy, X), cy + ny * D, cz + nz * D], -1)


def _roof_disp(g, X, Ss, seed, prm):
    """Caída de la lona entre arcos y largueros + traslape de secciones en cada arco + costuras paralelas a la cumbrera +
    arrugas de tensión que nacen en las esquinas de cada paño + ruido de baja frecuencia."""
    xs = g["xs"]
    D = np.zeros(np.broadcast(X, Ss).shape)
    Xb = np.broadcast_to(X, D.shape)
    Sb = np.broadcast_to(Ss, D.shape)
    # caída (seno en ambos sentidos; cresta marcada sobre cada miembro)
    for k in range(4):
        x0, x1 = xs[k], xs[k + 1]
        fx = np.clip((Xb - x0) / (x1 - x0), 0, 1)
        bx = np.sin(np.pi * fx) * ((Xb > x0) & (Xb < x1))
        for (s0, s1, side) in ((g["s_e0"], g["s_r"], 0), (g["s_r"], g["s_e1"], 1)):
            fs = np.clip((Sb - s0) / (s1 - s0), 0, 1)
            bs = np.sin(np.pi * fs) ** 0.9 * ((Sb > s0) & (Sb < s1))
            D -= prm["sag"][k][side] * bx * bs
    # faldón: cuelga flojo con ondas verticales suaves; festón entre amarres en la orilla
    val = (Sb < g["s_ks"]) | (Sb > g["s_tot"] - g["s_ks"])
    sv = np.minimum(Sb, g["s_tot"] - Sb)
    fv = 1 - _sstep(g["s_vb"], g["s_ks"], sv)
    wave = 0.004 * np.sin(Xb * 2 * PI / 0.47 + seed) + 0.0025 * np.sin(Xb * 2 * PI / 0.29 + 1.7 * seed)
    D += np.where(val, wave * fv, 0.0)
    # traslape de la cubierta de cada sección sobre los arcos interiores (lona de 2,5 mm encima, orilla viva)
    for xk in xs[1:-1]:
        up = _sstep(xk - 0.005, xk + 0.006, Xb) * (1 - _sstep(xk + 0.045, xk + 0.0485, Xb))
        D += 0.0025 * up
    # costuras dobles (felled seams) paralelas a la cumbrera
    for sc in prm["seams"]:
        D += 0.0016 * np.exp(-((Sb - sc) / 0.0045) ** 2)
    # arrugas de tensión
    D += _ridges(Xb, Sb, prm["wr"])
    # ruido (lona pesada: ondulación ancha y leve)
    D += 0.0035 * _noise_arr(Xb, Sb, 0.9, seed) + 0.0012 * _noise_arr(Xb, Sb, 3.2, seed + 3)
    return D


def _wall_disp(X, Z, x_legs, z0, z1, seed, ends, amp=1.0):
    """Pared colgante: abombado leve entre patas, pliegues verticales por gravedad abajo, ruido; cero en los apoyos."""
    D = np.zeros(np.broadcast(X, Z).shape)
    Xb = np.broadcast_to(X, D.shape)
    Zb = np.broadcast_to(Z, D.shape)
    B = np.zeros_like(D)
    for k in range(len(x_legs) - 1):
        a, b = x_legs[k], x_legs[k + 1]
        fx = np.clip((Xb - a) / (b - a), 0, 1)
        B += np.sin(np.pi * fx) * ((Xb > a) & (Xb < b))
    fz = np.clip((Zb - z0) / (z1 - z0), 0, 1)
    D += 0.011 * amp * B * np.sin(np.pi * fz) ** 0.7
    r = rng(seed)
    low = (1 - fz) ** 1.4
    for _ in range(6):
        lam = _f(r.uniform(0.22, 0.6))
        D += _f(r.uniform(0.004, 0.008)) * amp * np.sin(Xb * 2 * PI / lam + _f(r.uniform(0, 6.3)) + 2.0 * Zb) * low * np.sqrt(B)
    wr = []
    for xk in x_legs:
        for sx in (-1, 1):
            for _ in range(2):
                ln = _f(r.uniform(0.35, 0.8))
                a = -PI / 2 + sx * _f(r.uniform(0.45, 0.9))
                c0 = (xk + sx * 0.06 + math.cos(a) * ln / 2, z1 - 0.04 + math.sin(a) * ln / 2)
                wr.append((c0[0], c0[1], a, ln, _f(r.uniform(0.025, 0.04)), _f(r.uniform(0.003, 0.0065))))
    D += _ridges(Xb, Zb, wr) * amp
    D += (0.0025 * _noise_arr(Xb, Zb, 1.6, seed) + 0.0012 * _noise_arr(Xb, Zb, 4.0, seed + 1)) * amp * np.sqrt(B)
    D *= _sstep(ends[0], ends[0] + 0.12, Xb) * (1 - _sstep(ends[1] - 0.12, ends[1], Xb))
    return D


def _tent_roof(mb, g, L, seed, tie_x):
    """Cubierta del techo (de faldón a faldón) con campanas en los extremos."""
    r = rng(seed + 11)
    xs = g["xs"]
    # --- muestras en x: densas en los arcos, filas del traslape y de la campana
    xb = []
    for k in range(4):
        xb += list(0.45 * _cosspace(xs[k], xs[k + 1], 15) + 0.55 * np.linspace(xs[k], xs[k + 1], 16))
    hood = [(-L / 2 - 0.0235, -0.032), (-L / 2 - 0.0215, -0.005), (-L / 2 - 0.012, 0.0)]
    forced = [xs[0] - 0.03, L / 2 - 0.045 + 0.03] + list(xs)
    for xk in xs[1:-1]:
        forced += [xk - 0.005, xk + 0.006, xk + 0.045, xk + 0.0485]
    xv = _merge(xb, forced, 0.006)
    xv = np.concatenate([[h[0] for h in hood], xv, [-h[0] for h in hood[::-1]]])
    hood_d = np.concatenate([[h[1] for h in hood], np.full(len(xv) - 6, np.nan), [h[1] for h in hood[::-1]]])
    # --- muestras en s
    S = g["S"]
    st = g["s_tot"]
    half = list(S[:7]) + list(np.linspace(g["s_ks"], g["s_ke"], 7)[1:])
    half += list(_cosspace(g["s_ke"], g["s_rs"], 20)[1:]) + list(np.linspace(g["s_rs"], g["s_r"], 4)[1:])
    sv = np.array(half + [st - v for v in half[::-1][1:]])
    span = g["s_rs"] - g["s_ke"]
    seams = []
    for fr in (0.34, 0.68):
        sc = g["s_ke"] + span * fr
        seams += [sc, st - sc]
    sv = _merge(list(sv), [v for sc in seams for v in (sc - 0.006, sc, sc + 0.006)] + [g["s_e0"], g["s_e1"], g["s_r"]], 0.008)
    X, Ss = np.meshgrid(xv, sv, indexing="ij")
    # --- arrugas de tensión desde las esquinas de cada paño
    wr = []
    for k in range(4):
        for (s0, s1) in ((g["s_e0"], g["s_r"]), (g["s_r"], g["s_e1"])):
            xm, sm = (xs[k] + xs[k + 1]) / 2, (s0 + s1) / 2
            for (xc, sc) in ((xs[k], s0), (xs[k + 1], s0), (xs[k], s1), (xs[k + 1], s1)):
                base = math.atan2(sm - sc, xm - xc)
                for j in range(int(r.integers(2, 4))):
                    a = base + _jit(r, 0.45)
                    ln = _f(r.uniform(0.4, 1.1))
                    c0 = (xc + math.cos(a) * (ln / 2 + 0.04), sc + math.sin(a) * (ln / 2 + 0.04))
                    wr.append((c0[0], c0[1], a, ln, _f(r.uniform(0.05, 0.1)), _f(r.uniform(0.006, 0.013))))
            # pliegue de cizalla largo y suave a lo largo de una diagonal del paño
            if r.uniform() < 0.7:
                sgn = 1 if r.uniform() < 0.5 else -1
                a = math.atan2((s1 - s0) * sgn, xs[k + 1] - xs[k]) + _jit(r, 0.15)
                wr.append((xm + _jit(r, 0.2), sm + _jit(r, 0.2), a, _f(r.uniform(1.4, 2.2)), _f(r.uniform(0.09, 0.15)),
                           _f(r.uniform(0.006, 0.012))))
    prm = {"sag": [[_f(r.uniform(0.045, 0.068)) for _ in range(2)] for _ in range(4)], "seams": seams, "wr": wr}
    D = _roof_disp(g, X, Ss, seed, prm)
    hd = np.broadcast_to(hood_d[:, None], D.shape)
    D = np.where(np.isnan(hd), D, hd + 0.4 * D)
    # festón del dobladillo del faldón entre amarres
    sv_ = np.minimum(Ss, st - Ss)
    fest = np.zeros_like(D)
    for k in range(len(tie_x) - 1):
        a, b = tie_x[k], tie_x[k + 1]
        fest += np.sin(np.pi * np.clip((X - a) / (b - a), 0, 1)) * ((X > a) & (X < b))
    P = _roof_eval(g, X, Ss, D)
    P[..., 2] -= 0.012 * fest * (1 - _sstep(g["s_vb"], g["s_ks"] - 0.05, sv_))
    _Grid(mb, P, "canvas")
    g["roof_prm"] = prm
    return P, xv, sv


def _roof_point(g, x, s, seed, d_extra=0.0):
    """Punto y normal de la cubierta (misma función que la malla) para colocar parches, ojillos y amarres."""
    prm = g["roof_prm"]
    X = np.array([[x - 0.004, x, x + 0.004]] * 3)
    Ss = np.array([[s - 0.004] * 3, [s] * 3, [s + 0.004] * 3])
    D = _roof_disp(g, X, Ss, seed, prm) + d_extra
    P = _roof_eval(g, X, Ss, D)
    n = np.cross(P[2, 1] - P[0, 1], P[1, 2] - P[1, 0])
    n /= np.linalg.norm(n)
    c = Vector(P[1, 1])
    out = Vector(n)
    ref = Vector((0, 0, 1.2))
    if out.dot(c - Vector((c.x, 0, 1.2)) if abs(c.y) > 0.5 else c - ref) < 0:
        out = -out
    return c, out


def _side_wall(mb, g, L, side, seed, windows=()):
    """Pared lateral cerrada (side = -1 frente, +1 fondo): cuelga del larguero de alero, remates doblados hacia dentro arriba
    y abajo, festón entre amarres arriba, pliegues por gravedad abajo, ventanas con solapa (enrollada o cerrada)."""
    Yw = g["Yw"]
    z0, z1 = 0.012, g["z_wt"]
    xe = L / 2 + 0.006
    xs = g["xs"]
    xb = []
    legs = [-xe] + xs[1:-1] + [xe]
    for k in range(len(legs) - 1):
        xb += list(_cosspace(legs[k], legs[k + 1], 18))
    forced = [-xe, xe] + list(xs)
    zf = [z0, z1]
    for (xa, xb_, za, zb, kind) in windows:
        forced += [xa - 0.003, xa, xb_, xb_ + 0.003] if kind == "closed" else [xa, xb_]
        zf += [za - 0.003, za, zb] if kind == "closed" else [za, zb]
    xv = _merge(xb, forced, 0.008)
    zv = _merge(list(np.linspace(z0, z1, 17)), zf, 0.02)
    X, Z = np.meshgrid(xv, zv, indexing="ij")
    D = _wall_disp(X, Z, xs, z0, z1, seed, (-xe, xe))
    for (xa, xb_, za, zb, kind) in windows:
        if kind == "closed":                                  # solapa exterior cerrada: 5 mm encima, orilla viva abajo y lados
            ins = _sstep(xa - 0.003, xa, X) * (1 - _sstep(xb_, xb_ + 0.003, X)) * _sstep(za - 0.003, za, Z) * (1 - _sstep(zb, zb + 0.06, Z))
            D = D + 0.005 * ins - 0.004 * ins * np.sin(np.pi * np.clip((X - xa) / (xb_ - xa), 0, 1)) * np.sin(np.pi * np.clip((Z - za) / (zb - za), 0, 1))
    # festón del remate superior entre amarres (cada ~0,3 m)
    fest = np.abs(np.sin(np.pi * (X + L / 2) / (L / 32)))
    Zs = Z - 0.007 * fest * np.exp(-(z1 - Z) / 0.09)
    P = np.stack([X, side * (Yw + D), Zs], -1)
    # remates doblados hacia dentro (arriba y abajo): filas extra
    top = P[:, -1:, :].copy()
    top[..., 1] -= side * 0.015
    top[..., 2] += 0.006
    lift = sum(np.exp(-((xv - xk) / 0.1) ** 2) for xk in xs)
    P[:, 0, 2] = 0.004 + 0.008 * lift
    bot = P[:, :1, :].copy()
    bot[..., 1] -= side * 0.015
    bot[..., 2] = 0.0015 + 0.008 * lift[:, None]
    P = np.concatenate([bot, P, top], axis=1)
    mask = np.ones((P.shape[0] - 1, P.shape[1] - 1), bool)
    for (xa, xb_, za, zb, kind) in windows:
        if kind == "open":
            ia, ib = int(np.argmin(np.abs(xv - xa))), int(np.argmin(np.abs(xv - xb_)))
            ja, jb = int(np.argmin(np.abs(zv - za))) + 1, int(np.argmin(np.abs(zv - zb))) + 1
            mask[ia:ib, ja:jb] = False
    _Grid(mb, P, "canvas", mask)
    return P, xv, zv


def _wall_pt(g, L, side, x, z, seed):
    D = _wall_disp(np.array([x]), np.array([z]), g["xs"], 0.012, g["z_wt"], seed, (-L / 2 - 0.006, L / 2 + 0.006))[0]
    return Vector((x, side * (g["Yw"] + D), z)), Vector((0, side, 0))


def _end_top(g, y):
    """Altura del contorno superior del testero (12 mm bajo la lona del techo)."""
    T = g["top"]
    up = T[g["i_ks"]:g["i_r"] + 1]
    yy = abs(_f(y))
    if yy >= -up[0, 0]:
        return _f(up[0, 1])
    return _f(np.interp(-yy, up[:, 0], up[:, 1]))


def _end_wall(mb, g, L, end, seed, door_open):
    """Testero (end = -1 en -X, +1 en +X): lona plana tensada al arco extremo, remates doblados hacia dentro, puerta de
    1,5 × 1,98 m al centro: abierta (hueco con ribete) o cerrada (cierre al centro tapado por una solapa de tormenta)."""
    Ye = g["Ye"]
    Xe = end * g["Xe"]
    dw, dh = 0.75, 1.98
    yb = list(np.linspace(-Ye, Ye, 37))
    forced = [-Ye, Ye, -dw, dw]
    if not door_open:
        forced += [-0.021, -0.017, 0.026, 0.029]
    yv = _merge(yb, forced, 0.02 if door_open else 0.012)
    nv_lo, nv_hi = 15, 9
    rows = []
    for y in yv:
        h = _end_top(g, y)
        zd = min(dh, h - 0.15)
        col = list(np.linspace(0.012, zd, nv_lo + 1)) + list(np.linspace(zd, h, nv_hi + 1)[1:])
        rows.append(col)
    Z = np.array(rows)
    Y = np.broadcast_to(np.array(yv)[:, None], Z.shape)
    # desplazamiento hacia afuera (±X): abombado leve, pliegues abajo, cero en el contorno
    H = Z[:, -1:]
    fy = np.clip((Y + Ye) / (2 * Ye), 0, 1)
    fz = np.clip(Z / H, 0, 1)
    D = 0.006 * np.sin(np.pi * fy) * np.sin(np.pi * fz) ** 0.8
    r = rng(seed + 31)
    low = (1 - fz) ** 1.8 * np.sin(np.pi * fy) ** 0.5
    for _ in range(4):
        D += _f(r.uniform(0.0015, 0.003)) * np.sin(Y * 2 * PI / _f(r.uniform(0.3, 0.6)) + _f(r.uniform(0, 6.3))) * low
    D += 0.0012 * _noise_arr(Y, Z, 1.7, seed + 5) * np.sin(np.pi * fy) * np.sin(np.pi * fz)
    near = (np.abs(Y) < dw + 0.08) & (Z > dh - 0.25) & (Z < dh + 0.25)          # cabecera de la puerta: tensa
    D = np.where(near, D * 0.25, D)
    if not door_open:                                         # solapa de tormenta sobre el cierre (4 mm encima, orilla viva)
        fl = _sstep(-0.021, -0.017, Y) * (1 - _sstep(0.026, 0.029, Y)) * (1 - _sstep(dh - 0.02, dh + 0.04, Z))
        D = D + 0.004 * fl
    P = np.stack([np.full_like(Y, Xe) + end * D, Y, Z], -1)
    # remates doblados hacia dentro (arriba, abajo y lados)
    top = P[:, -1:, :].copy()
    top[..., 0] -= end * 0.015
    lift = np.exp(-((np.abs(np.array(yv)) - g["hw"]) / 0.12) ** 2)
    P[:, 0, 2] = 0.004 + 0.008 * lift
    bot = P[:, :1, :].copy()
    bot[..., 0] -= end * 0.015
    bot[..., 2] = 0.0015 + 0.008 * lift[:, None]
    P = np.concatenate([bot, P, top], axis=1)
    lft = P[:1].copy()
    lft[..., 0] -= end * 0.015
    rgt = P[-1:].copy()
    rgt[..., 0] -= end * 0.015
    P = np.concatenate([lft, P, rgt], axis=0)
    mask = np.ones((P.shape[0] - 1, P.shape[1] - 1), bool)
    for (i, j) in ((0, 0), (0, -1), (-1, 0), (-1, -1)):
        mask[i, j] = False
    if door_open:
        ia = int(np.argmin(np.abs(np.array(yv) + dw))) + 1
        ib = int(np.argmin(np.abs(np.array(yv) - dw))) + 1
        mask[ia:ib, 0:nv_lo + 1] = False
    _Grid(mb, P, "canvas", mask)
    return P, yv, Z


def _end_pt(g, end, y, z, seed):
    """Punto aproximado del testero (sin pliegues) para colocar accesorios cerca de la cabecera de la puerta."""
    return Vector((end * g["Xe"], y, z)), Vector((end, 0, 0))


def _arch(mb, g, x, seed):
    """Arco de aluminio: patas, rodillas y cumbrera con radio de doblez, coples de unión de sección con perno."""
    pf = g["pf"]
    Sf = g["Sf"]
    s_ks, s_ke, s_rs, sr = Sf[g["i_ks"]], Sf[g["i_ke"]], Sf[g["i_rs"]], Sf[g["i_r"]]
    key = [0.0, s_ks] + list(np.linspace(s_ks, s_ke, 9)[1:]) + [s_rs] + list(np.linspace(s_rs, sr, 6)[1:])
    key = key + [2 * sr - v for v in key[::-1][1:]]
    yy = np.interp(key, Sf, pf[:, 0])
    zz = np.interp(key, Sf, pf[:, 1])
    pts = [(x, _f(a), _f(b)) for a, b in zip(yy, zz)]
    pts[0] = (x, pts[0][1], 0.03)
    pts[-1] = (x, pts[-1][1], 0.03)
    _tube(mb, pts, R_A, seg=SEG, mat="aluminium")
    # coples de sección de las patas con perno de seguro
    for s in (1.25, 2 * sr - 1.25):
        p = Vector((x, _f(np.interp(s, Sf, pf[:, 0])), _f(np.interp(s, Sf, pf[:, 1]))))
        M = _frame_z(p, Vector((0, 0, 1)), (1, 0, 0))
        _lathe(mb, [(R_A - 0.001, -0.07), (R_A + 0.003, -0.067), (R_A + 0.003, 0.067), (R_A - 0.001, 0.07)], M, "aluminium",
               closed=True)
        sy = 1 if p.y > 0 else -1
        _cyl(mb, (x, p.y - sy * (R_A + 0.006), p.z + 0.035), (x, p.y + sy * (R_A + 0.01), p.z + 0.035), 0.0035, "steel", seg=12)


def _fitting(mb, g, x, s, sockets, purlin_r=R_P):
    """Conector de larguero de aluminio fundido sobre el arco: collar abrazando el tubo y cuello(s) a lo largo de X en los
    que entra el larguero, con perno de seguro."""
    pf, Sf = g["pf"], g["Sf"]
    p = Vector((x, _f(np.interp(s, Sf, pf[:, 0])), _f(np.interp(s, Sf, pf[:, 1]))))
    p2 = Vector((x, _f(np.interp(s + 0.01, Sf, pf[:, 0])), _f(np.interp(s + 0.01, Sf, pf[:, 1]))))
    t = (p2 - p).normalized()
    M = _frame_z(p, t, (1, 0, 0))
    _lathe(mb, [(R_A - 0.001, -0.055), (R_A + 0.0035, -0.05), (R_A + 0.0035, 0.05), (R_A - 0.001, 0.055)], M, "aluminium",
           closed=True)
    rs = purlin_r + 0.0032
    n = Vector(_normal_at(g, s))
    for sx in sockets:
        Ms = Matrix.Translation(p) @ (_Ry(90) if sx > 0 else _Ry(-90))
        _lathe(mb, [(rs, R_A * 0.6), (rs, 0.06), (rs - 0.0022, 0.064), (0.0, 0.064)], Ms, "aluminium")
        pc = p + Vector((sx * 0.045, 0, 0))
        if sx == sockets[0]:
            _cyl(mb, tuple(pc - n * (rs + 0.006)), tuple(pc + n * (rs + 0.004)), 0.0028, "steel", seg=12)


def _normal_at(g, s):
    Nf, Sf = g["Nf"], g["Sf"]
    return (0.0, _f(np.interp(s, Sf, Nf[:, 0])), _f(np.interp(s, Sf, Nf[:, 1])))


def _baseplate(mb, g, x, y, r):
    """Placa base de acero galvanizado: placa de 6 mm con esquinas redondeadas, casquillo en T soldado donde entran la pata
    y los largueros de base, perno, y una estaca de varilla hincada por la perforación."""
    slab(mb, _T(x, y, 0.0), 0.16, 0.16, 0.006, rc=0.018, re=0.002, mat="galvanized", nc=2, ne=1)
    _lathe(mb, [(R_A + 0.0042, 0.0045), (R_A + 0.004, 0.095), (R_A + 0.0025, 0.1), (R_A - 0.0008, 0.1), (R_A - 0.0008, 0.096)],
           _T(x, y, 0.0), "galvanized")
    sy = 1 if y > 0 else -1
    _cyl(mb, (x, y - sy * (R_A + 0.008), 0.08), (x, y + sy * (R_A + 0.012), 0.08), 0.0032, "steel", seg=12)
    px, py = x + 0.055, y - 0.055 * sy
    _cyl(mb, (px, py, -0.04), (px, py, 0.026), 0.0055, "steel", seg=SEG_T, caps=False)
    _lathe(mb, [(0.0055, 0.026), (0.011, 0.026), (0.011, 0.031), (0.009, 0.0335), (0.0, 0.034)], _T(px, py, 0), "steel", seg=SEG_T + 2)


def _stake(mb, base, lean, r=0.0065, h=0.17):
    """Estaca de varilla con gancho (J) hincada inclinada; devuelve el punto donde abraza la cuerda (bajo el gancho) y su eje."""
    b = Vector(base)
    out = Vector(lean).normalized()
    ax = (Vector((0, 0, 1)) - out * 0.32).normalized()
    p0 = b - ax * 0.06
    p1 = b + ax * h
    hook = [p0, p1, p1 + out * 0.03 + ax * 0.012, p1 + out * 0.05 - ax * 0.016]
    _tube(mb, fillet([tuple(p) for p in hook], 0.012, 3), r, seg=SEG_T, mat="steel")
    return b + ax * (h - 0.04), ax


def _guy(mb, pa, stake_base, lean, seed):
    """Viento (cuerda de 3/8") de un punto del armazón a su estaca: tensor deslizante de aluminio a 0,35 m de la estaca,
    gaza que abraza la estaca bajo el gancho y chicote con nudo."""
    r = rng(seed)
    pr, ax = _stake(mb, stake_base, lean)
    pa = Vector(pa)
    d = (pr - pa)
    L = d.length
    u = d.normalized()
    ps = pr - u * 0.36
    rr = 0.0048
    _tube(mb, _catenary(pa, ps - u * 0.04, 0.006 * L, n=6), rr, seg=SEG_T, mat="fabric")
    side = u.cross(Vector((0, 0, 1))).normalized()
    Mt = Matrix.Translation(ps) @ port.frame_on((0, 0, 0), tuple(u), up=tuple(u.cross(side)))[0]
    slab(mb, Mt @ _T(0.0, 0, -0.0035), 0.085, 0.026, 0.007, rc=0.008, re=0.0018, mat="aluminium", nc=2, ne=1)
    # gaza: dos ramales que salen del tensor y rodean la estaca bajo el gancho
    ring = [pr + side * (math.cos(PI * k / 4) * 0.0118) + u * (math.sin(PI * k / 4) * 0.0118) for k in range(5)]
    loop = [ps - u * 0.04 + side * 0.006, ps + u * 0.06 + side * 0.009] + ring + [ps + u * 0.06 - side * 0.009, ps - u * 0.04 - side * 0.006]
    _tube(mb, [tuple(p) for p in loop], rr * 0.95, seg=SEG_T, mat="fabric", caps=False)
    _lathe(mb, [(0.0, -0.012), (rr * 2.2, -0.009), (rr * 2.4, 0.0), (rr * 2.0, 0.009), (0.0, 0.012)],
           _frame_z(ps - u * 0.045, u), "fabric", seg=SEG_T)
    tail = [ps - u * 0.05 - side * 0.006, ps - u * 0.07 - side * 0.01 - Vector((0, 0, 0.03 + _jit(r, 0.01)))]
    _tube(mb, tail, rr * 0.9, seg=SEG_T, mat="fabric")


def _tieout(mb, g, x, side, seed):
    """Refuerzo cosido en la rodilla con gaza de reata para el viento; devuelve el punto de amarre de la cuerda."""
    s = g["s_e0"] + 0.03 if side < 0 else g["s_e1"] - 0.03
    P, N = [], []
    for sx in np.linspace(x - 0.05, x + 0.05, 4):
        rowp, rown = [], []
        for ss in np.linspace(s - 0.06, s + 0.06, 4):
            c, n = _roof_point(g, sx, ss, seed)
            rowp.append(tuple(c))
            rown.append(tuple(n))
        P.append(rowp)
        N.append(rown)
    _slab_grid(mb, np.array(P), np.array(N), -0.0012, 0.0024, "canvas")
    c, n = _roof_point(g, x, s, seed)
    down = Vector((0, side * 0.55, -0.83)).normalized()
    a = c + n * 0.0045
    tip = a + down * 0.06 + n * 0.012
    loop = [a - down * 0.035, a, tip, tip + down * 0.012 + Vector((0, side * 0.004, 0)), tip + down * 0.004 + Vector((0, side * 0.012, 0))]
    _strap(mb, [tuple(p) for p in loop[:3]], w=0.025, t=0.0022, up=(1, 0, 0))
    _lathe(mb, [(0.0, -0.012), (0.011, -0.009), (0.013, 0.0), (0.011, 0.009), (0.0, 0.012)], _frame_z(tip + down * 0.008, down),
           "fabric", seg=SEG_T)
    return tip + down * 0.018


def frame_tent(L=9.75, W=6.1, seed=0, open_front=True, rolled_sides=("front",)):
    """Tienda militar de armazón tipo TEMPER 20 × 32 ft (6,1 × 9,75 m) armada como expendio del puesto avanzado.

    Ejes: origen en el piso al centro; largo L en X, ancho W en Y; FRENTE = pared lateral larga en -Y (la del mostrador),
    FONDO = pared lateral en +Y; testeros (puertas) en -X y +X. Cumbrera 3,20 m, alero 2,06 m.
    - Armazón de aluminio sin postes centrales: 5 arcos (Ø 44,5 mm) a 2,42 m con patas, rodillas y cumbrera de radio real,
      coples de sección con perno; 5 líneas de largueros (cumbrera, 2 aleros, 2 bases, Ø 38 mm) en conectores fundidos con
      perno de seguro y argolla; placas base galvanizadas con casquillo soldado y dos estacas hincadas.
    - Cubierta de lona OD de una sola capa (material canvas de dos caras): caída real entre arcos y largueros, cresta sobre
      cada miembro, traslape de 45 mm de la cubierta de cada sección sobre los arcos, costuras dobles paralelas a la cumbrera,
      arrugas de tensión que nacen en las esquinas de cada paño, faldón con festón entre amarres y dobladillo, campanas en los
      extremos sobre los testeros.
    - rolled_sides: paredes laterales ("front" y/o "back") enrolladas hasta el alero y atadas con cintas que abrazan el rollo
      por debajo y suben al ojillo del faldón; las no enrolladas cuelgan cerradas con ventanas: una con la solapa enrollada y
      la malla mosquitera a la vista, otra con la solapa de tormenta cerrada y su jalador.
    - open_front: la puerta del testero -X (entrada) abierta, con sus dos hojas enrolladas y atadas sobre el vano; la del
      testero +X va cerrada con el cierre tapado por la solapa de tormenta (si es False, ambas cerradas).
    - 12 vientos de cuerda de 3/8" con tensor deslizante, gaza y nudo, a estacas de gancho inclinadas.
    Piso interior: la tienda no trae piso (va sobre el terreno o sobre plywood_floor, cuya cara superior queda a 0,108 m).
    Huella útil interior (entre las caras internas de patas y largueros de base): x ±(L/2 - 0,07), y ±(W/2 - 0,075)."""
    r = rng(seed)
    mb = MB()
    g = _tent_geo(L, W)
    xs = g["xs"]
    hw = g["hw"]
    # ---------------- lona
    tie_x = sorted(set([-L / 2 - 0.0235] + [xk + d for xk in xs for d in (0.0,)] + [(xs[k] + xs[k + 1]) / 2 for k in range(4)] + [L / 2 + 0.0235]))
    _tent_roof(mb, g, L, seed, tie_x)
    win_x = [(xs[1] + xs[2]) / 2, (xs[2] + xs[3]) / 2]
    for side, name in ((-1, "front"), (1, "back")):
        if name in rolled_sides:
            _rolled_wall(mb, g, L, side, seed + (3 if side > 0 else 0), tie_x)
        else:
            wins = [(win_x[0] - 0.45, win_x[0] + 0.45, 1.05, 1.62, "open"), (win_x[1] - 0.45, win_x[1] + 0.45, 1.05, 1.62, "closed")]
            _side_wall(mb, g, L, side, seed + (5 if side > 0 else 9), wins)
            _window_details(mb, g, L, side, seed, wins)
    for end in (-1, 1):
        dopen = bool(open_front) and end < 0
        _end_wall(mb, g, L, end, seed + (13 if end > 0 else 17), dopen)
        _door_details(mb, g, L, end, seed + 21 + 2 * end, dopen)
    # ---------------- armazón
    Sf = g["Sf"]
    s_e_f, s_r = g["f_e"], g["f_r"]
    s_e_b = 2 * s_r - s_e_f
    for k, x in enumerate(xs):
        _arch(mb, g, x, seed + k)
        socks = (-1, 1) if 0 < k < 4 else ((1,) if k == 0 else (-1,))
        for s in (s_e_f, s_r, s_e_b):
            _fitting(mb, g, x, s, socks)
        for sy in (-1, 1):
            _baseplate(mb, g, x, sy * hw, r)
    del Sf
    pf, Sfa = g["pf"], g["Sf"]
    for s in (s_e_f, s_r, s_e_b):
        y = _f(np.interp(s, Sfa, pf[:, 0]))
        z = _f(np.interp(s, Sfa, pf[:, 1]))
        for k in range(4):
            _cyl(mb, (xs[k] + 0.058, y, z), (xs[k + 1] - 0.058, y, z), R_P, "aluminium", seg=SEG)
    for sy in (-1, 1):
        for k in range(4):
            _cyl(mb, (xs[k] + R_A + 0.0015, sy * hw, 0.06), (xs[k + 1] - R_A - 0.0015, sy * hw, 0.06), R_P, "aluminium", seg=SEG)
    # ---------------- vientos
    for k, x in enumerate(xs):
        for sy in (-1, 1):
            pa = _tieout(mb, g, x + (0.0225 if 0 < k < 4 else 0.0), sy, seed)
            lean = Vector((0.25 * (-1 if k == 0 else 1 if k == 4 else 0), sy, 0)).normalized()
            base = Vector((x + lean.x * 1.45, sy * (W / 2 + 1.35), 0.0))
            _guy(mb, pa, base, lean, seed + k * 3 + (sy > 0))
    for end in (-1, 1):
        c, n = _roof_point(g, end * (L / 2 + 0.004), g["s_r"], seed)
        pa = Vector((end * (L / 2 + 0.03), 0.0, RIDGE - 0.035))
        _strap(mb, [(end * (L / 2 + 0.006), 0.0, RIDGE + 0.002), (end * (L / 2 + 0.024), 0.0, RIDGE - 0.004), tuple(pa)], w=0.025,
               up=(0, 1, 0))
        _lathe(mb, [(0.0, -0.012), (0.011, -0.009), (0.013, 0.0), (0.011, 0.009), (0.0, 0.012)],
               _frame_z(pa + Vector((end * 0.008, 0, -0.004)), Vector((end, 0, -0.5))), "fabric", seg=SEG_T)
        _guy(mb, pa + Vector((end * 0.026, 0, -0.012)), Vector((end * (L / 2 + 2.6), 0.0, 0.0)), Vector((end, 0, 0)), seed + 40 + end)
    return mb


def _rolled_wall(mb, g, L, side, seed, tie_x):
    """Pared lateral enrollada hasta el alero: tira de lona que baja del remate superior al rollo, rollo con caída entre
    cintas y cintas que lo abrazan por debajo y suben al ojillo del dobladillo del faldón."""
    Yw = g["Yw"]
    R = 0.058
    pc = R + 0.007
    zc0 = g["z_vb"] - R - 0.014
    ties = [x for x in tie_x if abs(x) < L / 2 - 0.1]
    ties = [-L / 2 + 0.12] + ties + [L / 2 - 0.12]

    def zfun(x):
        for k in range(len(ties) - 1):
            a, b = ties[k], ties[k + 1]
            if a <= x <= b:
                return zc0 - 0.013 * math.sin(PI * (x - a) / (b - a))
        return zc0
    x0, x1 = -L / 2 + 0.012, L / 2 - 0.012
    M = _T(x0, side * (Yw + pc), 0.0)
    if side > 0:
        M = _T(x1, side * (Yw + pc), 0.0) @ _Rz(180)
        zf = lambda xx: zfun(x1 - xx)  # noqa: E731
    else:
        zf = lambda xx: zfun(xx + x0)  # noqa: E731
    _canvas_roll(mb, M, x1 - x0, R, seed=seed, zfun=zf, seg=SEG, nst=int((x1 - x0) / 0.24) + 1)
    # tira de lona del remate superior al rollo (remate doblado hacia dentro arriba)
    xv = np.linspace(x0, x1, int((x1 - x0) / 0.2) + 1)
    rows = []
    for x in xv:
        zc = zfun(x)
        zt = g["z_wt"]
        rows.append([(x, side * (Yw - 0.015), zt + 0.006), (x, side * Yw, zt), (x, side * (Yw + 0.0015), (zt + zc) / 2),
                     (x, side * (Yw + 0.004), zc + 0.012), (x, side * (Yw + pc - R * 0.97), zc - 0.006)])
    _Grid(mb, np.array(rows), "canvas")
    # cintas
    zg = g["z_vb"] + 0.032
    for x in ties[1:-1]:
        zc = zfun(x)
        rho = R + 0.0016
        path2 = _sling_path(pc, zc, rho, (pc - rho, g["z_wt"] - 0.03), (0.0335, zg))
        _strap(mb, [(x, side * (Yw + p), z) for (p, z) in path2], w=0.025, t=0.0018, up=(1, 0, 0))
        c, n = Vector((x, side * (Yw + 0.0335 - 0.0035), zg)), Vector((0, side, 0))
        _grommet(mb, _frame_z(c, n), ro=0.0105, ri=0.0052)


def _window_details(mb, g, L, side, seed, wins):
    """Ventanas de la pared lateral: ribete perimetral; abierta = malla mosquitera + solapa enrollada atada arriba;
    cerrada = jalador del cierre en la esquina."""
    Yw = g["Yw"]
    for (xa, xb, za, zb, kind) in wins:
        if kind == "open":
            # malla mosquitera (sólido delgado que sigue la pared, 4 mm adentro)
            xv = np.linspace(xa - 0.01, xb + 0.01, 10)
            zv = np.linspace(za - 0.01, zb + 0.01, 6)
            P = np.array([[tuple(_wall_pt(g, L, side, x, z, seed + (5 if side > 0 else 9))[0]) for z in zv] for x in xv])
            N = np.zeros_like(P)
            N[..., 1] = side
            _slab_grid(mb, P, N, -0.0055, -0.0045, "fabric")
            # ribete del vano (cinta que envuelve la orilla)
            path = [(xa, za), (xb, za), (xb, zb), (xa, zb), (xa, za)]
            pts = []
            for k in range(4):
                (x0, z0), (x1, z1) = path[k], path[k + 1]
                for t in np.linspace(0, 1, 8)[:-1]:
                    x, z = x0 + (x1 - x0) * t, z0 + (z1 - z0) * t
                    pts.append(tuple(_wall_pt(g, L, side, x, z, seed + (5 if side > 0 else 9))[0]))
            loop_tube_flat(mb, pts, side)
            # solapa enrollada sobre la ventana, atada con dos cintas
            R = 0.032
            pc = R + 0.006
            zc = zb + 0.035
            M = _T(xa - 0.02, side * (Yw + pc), 0.0)
            _canvas_roll(mb, M, xb - xa + 0.04, R, seed=seed + 7, zfun=lambda xx: zc - 0.006 * math.sin(PI * xx / (xb - xa + 0.04)),
                         seg=SEG, nst=10)
            for x in (xa + 0.12, xb - 0.12):
                rho = R + 0.0016
                p2 = _sling_path(pc, zc, rho, (pc - rho, zc + 0.16), (0.0045, zc + 0.16))
                _strap(mb, [(x, side * (Yw + p), z) for (p, z) in p2], w=0.02, t=0.0018, up=(1, 0, 0))
        else:
            c = Vector((xb - 0.02, side * (g["Yw"] + 0.0045), za - 0.002))
            _zip_pull(mb, c, Vector((0, side, 0)))


def loop_tube_flat(mb, pts, side):
    """Ribete de cinta (25 × 4 mm) que envuelve la orilla de un vano en una pared lateral (lazo cerrado)."""
    P = [Vector(p) for p in pts]
    n = len(P)
    nrm = Vector((0, side, 0))
    prof = rr_profile(0.026, 0.004, 0.0015, n=2)
    rings = []
    for i in range(n):
        T = (P[(i + 1) % n] - P[i - 1]).normalized()
        B = T.cross(nrm).normalized()
        rings.append([P[i] + B * a + nrm * b for (a, b) in prof])
    V = [[mb.bm.verts.new(p) for p in ring] for ring in rings]
    mi = mb.mi("fabric")
    k = len(prof)
    for i in range(n):
        A, B_ = V[i], V[(i + 1) % n]
        for j in range(k):
            f = mb.bm.faces.new([A[j], A[(j + 1) % k], B_[(j + 1) % k], B_[j]])
            f.material_index = mi
            f.smooth = True


def _zip_pull(mb, c, n):
    """Corredera de cierre con jalador de lámina y cordón (se asoma bajo la solapa)."""
    M = _frame_z(c, n, (0, 0, 1))
    slab(mb, M @ _T(0, 0, -0.002), 0.012, 0.02, 0.006, rc=0.003, re=0.0015, mat="steel", nc=2, ne=1)
    tab = M @ _T(0, -0.02, 0.004) @ _Rx(18)
    slab(mb, tab, 0.008, 0.028, 0.0018, rc=0.0035, re=0.0006, mat="steel", nc=2, ne=1)
    p0 = tab @ Vector((0, -0.012, 0.001))
    _tube(mb, [tuple(p0), tuple(p0 + (M.to_3x3() @ Vector((0.004, -0.03, 0.006)))),
               tuple(p0 + (M.to_3x3() @ Vector((-0.002, -0.055, 0.012))))], 0.0018, seg=8, mat="cable")


def _door_details(mb, g, L, end, seed, door_open):
    """Puerta del testero: abierta = ribete del vano + dos hojas enrolladas sobre la cabecera con cintas; cerrada = ribete
    del contorno, corredera y jalador asomando bajo la solapa de tormenta."""
    Xe = end * g["Xe"]
    dw, dh = 0.75, 1.98
    if door_open:
        # ribete en U (lados y cabecera)
        pts = [(Xe, -dw, 0.012), (Xe, -dw, dh), (Xe, dw, dh), (Xe, dw, 0.012)]
        prof = rr_profile(0.004, 0.03, 0.0015, n=2)
        sweep_frame(mb, prof, fillet(pts, 0.03, 4), "fabric", up=(1, 0, 0))
        R = 0.052
        pc = R + 0.008
        zc = dh + 0.02
        for (y0, y1, sd) in ((-dw - 0.03, -0.012, 0), (0.012, dw + 0.03, 1)):
            M = _T(Xe + end * pc, y0, 0.0) @ _Rz(90)
            _canvas_roll(mb, M, y1 - y0, R, seed=seed + sd, zfun=lambda xx, a=y1 - y0: zc - 0.008 * math.sin(PI * xx / a),
                         seg=SEG, nst=10)
            for y in (y0 + 0.13, y1 - 0.13):
                rho = R + 0.0016
                p2 = _sling_path(pc, zc, rho, (pc - rho, zc + 0.2), (0.0045, zc + 0.2))
                pth = [(Xe + end * p, y, z) for (p, z) in p2]
                _strap(mb, pth, w=0.025, t=0.0018, up=(0, 1, 0))
                _grommet(mb, _frame_z(Vector((Xe + end * 0.0015, y, zc + 0.215)), Vector((end, 0, 0))), ro=0.0105, ri=0.0052)
    else:
        pts = [(Xe + end * 0.0012, -dw, 0.012), (Xe + end * 0.0012, -dw, dh), (Xe + end * 0.0012, dw, dh), (Xe + end * 0.0012, dw, 0.012)]
        prof = rr_profile(0.0025, 0.03, 0.001, n=2)
        sweep_frame(mb, prof, fillet(pts, 0.03, 4), "fabric", up=(1, 0, 0))
        _zip_pull(mb, Vector((Xe + end * 0.0025, 0.004, 0.16)), Vector((end, 0, 0)))


def _board(mb, x0, x1, y0, y1, z0, z1, mat, r=0.002, M=None, bottom=True):
    """Tabla de cantos redondeados (r) dada por su caja; bottom=False: sin bisel abajo (cara oculta)."""
    Mb = _T((x0 + x1) / 2, (y0 + y1) / 2, z0)
    slab(mb, (M @ Mb) if M is not None else Mb, x1 - x0, y1 - y0, z1 - z0, rc=min(r, 0.25 * min(x1 - x0, y1 - y0)), re=r, mat=mat,
         nc=1, ne=1, re0=(r if bottom else 0.0))


def plywood_floor(L=9.6, W=5.9, seed=0):
    """Piso de tarima para la tienda de campaña: durmientes de 2×4" de canto (38 × 89 mm) a 16" (406 mm) a lo largo de X,
    hojas de triplay de 4 × 8 ft (1,22 × 2,44 m) × 19 mm en hiladas trabadas con juntas de 3 mm y alturas que varían
    medio milímetro, cantos matados, tornillos avellanados sobre cada durmiente a 0,4 m; perímetro con fascia de 1×6" y
    nariz de ángulo de aluminio de 25 × 25 mm. Cara superior a z = 0,108 m.
    Origen: centro, al piso; L en X, W en Y (cabe entre las patas de frame_tent con L = 9,6 y W = 5,9)."""
    r = rng(seed)
    mb = MB()
    t, hs, fa = 0.019, 0.089, 0.019
    zt = hs + t
    x0, x1 = -L / 2 + fa, L / 2 - fa
    y0, y1 = -W / 2 + fa, W / 2 - fa
    ny = int(math.ceil((y1 - y0 - 0.038) / 0.406)) + 1
    ys = np.linspace(y0 + 0.019, y1 - 0.019, ny)
    for y in ys:
        mb.box((x0, y - 0.019, 0.0), (x1, y + 0.019, hs), "wood", bevel=0.0)
    pw, pl, gap = 1.2192, 2.4384, 0.003
    yb = [y0]
    while yb[-1] + pw < y1 - 0.05:
        yb.append(yb[-1] + pw)
    yb.append(y1)
    xcuts = set()
    for j in range(len(yb) - 1):
        off = pl if j % 2 == 0 else pl / 2
        xb = [x0]
        x = x0 + off
        while x < x1 - 0.05:
            xb.append(x)
            x += pl
        xb.append(x1)
        for i in range(len(xb) - 1):
            dz = -_f(r.uniform(0.0, 0.0007))
            _board(mb, xb[i] + gap / 2, xb[i + 1] - gap / 2, yb[j] + gap / 2, yb[j + 1] - gap / 2, hs + dz, zt + dz, "plywood",
                   r=0.0015, bottom=False)
            for xc in xb[1:-1]:
                xcuts.add(round(xc, 4))
            # tornillos avellanados sobre los durmientes que caen en esta hoja
            for y in ys:
                if not (yb[j] + 0.025 < y < yb[j + 1] - 0.025):
                    continue
                xx = xb[i] + 0.05
                while xx < xb[i + 1] - 0.04:
                    _lathe(mb, [(0.0046, -0.0003), (0.0, 0.00035)], _T(xx + _jit(r, 0.004), y, zt + dz), "steel", seg=6)
                    xx += 0.6
    # fascia perimetral (1×6") y nariz de ángulo de aluminio sobre la orilla
    _board(mb, -L / 2, L / 2, -W / 2, -W / 2 + fa, 0.0, zt, "wood", r=0.003)
    _board(mb, -L / 2, L / 2, W / 2 - fa, W / 2, 0.0, zt, "wood", r=0.003)
    _board(mb, -L / 2, -L / 2 + fa, -W / 2 + fa + 0.0005, W / 2 - fa - 0.0005, 0.0, zt, "wood", r=0.003)
    _board(mb, L / 2 - fa, L / 2, -W / 2 + fa + 0.0005, W / 2 - fa - 0.0005, 0.0, zt, "wood", r=0.003)
    prof = [(-0.025, 0.0002), (0.0, 0.0002), (0.0, -0.025), (0.002, -0.025), (0.002, 0.0008), (0.0012, 0.0022), (-0.025, 0.0022)]
    path = [(-L / 2, -W / 2, zt), (L / 2, -W / 2, zt), (L / 2, W / 2, zt), (-L / 2, W / 2, zt)]
    mb.sweep(prof, path, "aluminium", closed_path=True)
    for x in np.linspace(-L / 2 + 0.3, L / 2 - 0.3, 9):         # pijas de la nariz
        for (y, s) in ((-W / 2 - 0.002, -1), (W / 2 + 0.002, 1)):
            _lathe(mb, [(0.0045, -0.0003), (0.0, 0.0009)], _T(x, y, zt - 0.012) @ _Rx(-90 * s), "steel", seg=8)
    return mb


# ======================================================================================================== mostrador de cajas


def _od_crate(mb, M, w=0.8, d=0.55, h=0.42, seed=0, ends=(True, True), lid_battens=False, stencil=None, bands=True,
              handles=(True, True)):
    """Caja de madera militar pintada OD (origen: centro de la base, frente -Y): patines, costados de dos tablas con junta,
    testeros con marco de listones (los ocultos sin listones), tapa de dos tablas, flejes de acero con sello, asas de
    lámina abatibles y rótulo en esténcil."""
    r = rng(seed)
    hs = 0.025
    tb = 0.018
    xi = w / 2 - 0.022
    z0 = hs
    for sy in (-1, 1):                                                   # patines
        _board(mb, -w / 2 + 0.01, w / 2 - 0.01, sy * (d / 2 - 0.06) - 0.025, sy * (d / 2 - 0.06) + 0.025, 0.0, hs + 0.0005, "wood_od",
               r=0.003, M=M, bottom=False)
    hb = (h - tb - z0) / 2
    for sy in (-1, 1):                                                   # costados: dos tablas con junta de 4 mm
        ya, yb_ = sorted((sy * d / 2, sy * (d / 2 - tb)))
        for k in range(2):
            za = z0 + k * hb + (0.002 if k else 0.0)
            zb = z0 + (k + 1) * hb - (0.0 if k else 0.002)
            _board(mb, -xi, xi, ya, yb_, za + _jit(r, 0.0008), zb, "wood_od", r=0.0025, M=M)
    for sx in (-1, 1):                                                   # testeros
        xa, xb_ = sorted((sx * (xi - tb), sx * xi))
        _board(mb, xa, xb_, -d / 2 + tb + 0.0005, d / 2 - tb - 0.0005, z0, h - tb, "wood_od", r=0.002, M=M)
        if ends[0 if sx < 0 else 1]:
            xa, xb_ = sorted((sx * xi, sx * w / 2))
            _board(mb, xa, xb_, -d / 2, d / 2, z0, z0 + 0.07, "wood_od", r=0.003, M=M)
            _board(mb, xa, xb_, -d / 2, d / 2, h - 0.07, h, "wood_od", r=0.003, M=M)
            for sy in (-1, 1):
                ya, yb_ = sorted((sy * d / 2, sy * (d / 2 - 0.07)))
                _board(mb, xa, xb_, ya, yb_, z0 + 0.0705, h - 0.0705, "wood_od", r=0.003, M=M)
            if handles[0 if sx < 0 else 1]:                              # asa de lámina abatible (colgando)
                zc = (z0 + h) / 2 + 0.03
                for sy in (-1, 1):
                    _board(mb, -0.016, 0.016, sy * 0.075 - 0.02, sy * 0.075 + 0.02, 0.0, 0.003, "paint_od", r=0.001,
                           M=M @ _T(sx * xi, 0, zc) @ _Ry(90 * sx))
                hp = [(sx * (xi + 0.009), -0.075, zc + 0.004), (sx * (xi + 0.011), -0.072, zc - 0.05), (sx * (xi + 0.011), 0.072, zc - 0.05),
                      (sx * (xi + 0.009), 0.075, zc + 0.004)]
                sweep_frame(mb, rr_profile(0.004, 0.016, 0.0015, n=1), [tuple(M @ Vector(p)) for p in fillet(hp, 0.012, 2)],
                            "paint_od", up=tuple(M.to_3x3() @ Vector((sx, 0, 0))))
    for k in range(2):                                                   # tapa
        ya = -d / 2 + k * d / 2 + (0.002 if k else 0.0)
        yb_ = -d / 2 + (k + 1) * d / 2 - (0.0 if k else 0.002)
        _board(mb, -xi, xi, ya, yb_, h - tb, h - 0.0004 * k, "wood_od", r=0.0025, M=M)
    if lid_battens:
        for sx in (-1, 1):
            _board(mb, sx * (xi - 0.06) - 0.035, sx * (xi - 0.06) + 0.035, -d / 2, d / 2, h - 0.001, h + 0.02, "wood_od", r=0.003, M=M)
    if bands:                                                            # flejes: suben por el frente, pasan sobre la tapa, bajan atrás
        for xb in (-w / 4, w / 4):
            e = 0.0009
            zt = h + (0.02 if lid_battens and abs(abs(xb) - (xi - 0.06)) < 0.04 else 0.0)
            pth = [(xb, -d / 2 - e, z0 + 0.004), (xb, -d / 2 - e, zt - 0.004), (xb, -d / 2 + 0.004, zt + e), (xb, d / 2 - 0.004, zt + e),
                   (xb, d / 2 + e, zt - 0.004), (xb, d / 2 + e, z0 + 0.004)]
            sweep_frame(mb, [(-0.008, -0.0004), (0.008, -0.0004), (0.008, 0.0004), (-0.008, 0.0004)],
                        [tuple(M @ Vector(p)) for p in fillet(pth, 0.004, 1)], "steel", up=tuple(M.to_3x3() @ Vector((1, 0, 0))))
            _board(mb, xb - 0.012, xb + 0.012, d / 2 + e, d / 2 + e + 0.0025, z0 + 0.09, z0 + 0.12, "steel", r=0.0008, M=M)
    if stencil:
        etext(mb, stencil, 0.055, 0.0006, "sign_white", M @ _T(0, -d / 2 + 0.0002, z0 + hb + 0.02) @ _Rx(90) @ _T(0, 0, 0.0),
              res=1, back=False, bold=True)
        if lid_battens:
            etext(mb, "LOT 7-%02d" % (seed % 90 + 10), 0.022, 0.0006, "sign_white",
                  M @ _T(0, -d / 2 + 0.0002, z0 + 0.035) @ _Rx(90), res=1, back=False)


def _clipboard(mb, M, seed=0):
    """Tabla con clip de lámina y resorte, tres hojas de papel con la esquina levantada y una pluma (origen: centro de la
    base, sobre la mesa)."""
    r = rng(seed)
    _board(mb, -0.115, 0.115, -0.16, 0.16, 0.0, 0.003, "wood_dark", r=0.0012, M=M)
    for k in range(3):                                                   # hojas
        ang = _jit(r, 1.5)
        nu, nv = 5, 7
        P = np.zeros((nu, nv, 3))
        for i in range(nu):
            for j in range(nv):
                x = -0.105 + 0.21 * i / (nu - 1)
                y = -0.14 + 0.28 * j / (nv - 1)
                lift = 0.006 * max(0.0, (-y - 0.06) / 0.08) ** 2 * (0.5 + 0.5 * (x + 0.105) / 0.21) * (k == 2)
                P[i, j] = (x, y, 0.003 + 0.00035 * k + 0.0001 + lift)
        Mr = M @ _Rz(ang)
        PP = np.array([[tuple(Mr @ Vector(P[i, j])) for j in range(nv)] for i in range(nu)])
        N = np.zeros_like(PP)
        N[..., :] = tuple(M.to_3x3() @ Vector((0, 0, 1)))
        _slab_grid(mb, PP, N, 0.0, 0.0002, "paper")
        for j in range(5):                                                # renglones escritos a mano (tinta en relieve fino)
            if k == 2:
                yl = 0.09 - j * 0.035
                ln = _f(r.uniform(0.07, 0.16))
                _board(mb, -0.09, -0.09 + ln, yl, yl + 0.0012, 0.0041, 0.00425, "cable", r=0.0002, M=Mr)
    # clip: base remachada, palanca abombada y resorte
    _board(mb, -0.05, 0.05, 0.12, 0.155, 0.003, 0.0045, "aluminium", r=0.001, M=M)
    sweep_frame(mb, rr_profile(0.08, 0.0012, 0.0005, n=1), [tuple(M @ Vector(p)) for p in
                                                            [(0, 0.15, 0.006), (0, 0.13, 0.0095), (0, 0.11, 0.0072), (0, 0.098, 0.0044)]],
                "aluminium", up=tuple(M.to_3x3() @ Vector((0, 0, 1))))
    _cyl(mb, tuple(M @ Vector((-0.03, 0.142, 0.009))), tuple(M @ Vector((0.03, 0.142, 0.009))), 0.0042, "steel", seg=16)
    for sx in (-1, 1):
        _lathe(mb, [(0.0, 0.0), (0.003, 0.0), (0.0025, 0.0012), (0.0, 0.0015)], M @ _T(sx * 0.04, 0.138, 0.0045), "aluminium", seg=10)
    # pluma
    pm = M @ _T(0.07, -0.02, 0.0084) @ _Rz(68) @ _Ry(90)
    _lathe(mb, [(0.0, -0.07), (0.0015, -0.068), (0.004, -0.055), (0.0042, 0.06), (0.0038, 0.065), (0.0, 0.067)], pm, "plastic", seg=14)
    _board(mb, -0.0012, 0.0012, 0.0038, 0.0058, 0.02, 0.058, "steel", r=0.0005, M=pm @ _Rz(0))


def _tape_roll(mb, M, seed=0):
    """Rollo de cinta de tela (duct tape) acostado: rollo con cantos suaves, núcleo de cartón y la punta despegada."""
    R0, R1, Wt = 0.0385, 0.056, 0.048
    _lathe(mb, [(R0 + 0.0043, 0.0005), (R1 - 0.002, 0.0005), (R1, 0.002), (R1, Wt - 0.002), (R1 - 0.002, Wt - 0.0005),
                (R0 + 0.0043, Wt - 0.0005)], M, "plastic", seg=SEG, closed=True)
    _lathe(mb, [(R0, 0.0), (R0 + 0.0042, 0.0), (R0 + 0.0042, Wt), (R0, Wt)], M, "cardboard", seg=SEG, closed=True)
    a0 = 0.6
    pts = []
    for k in range(6):
        a = a0 + 0.12 * k
        rr = R1 + 0.0004 + 0.0025 * k ** 1.5 / 6
        pts.append((rr * math.cos(a), rr * math.sin(a)))
    P = np.array([[(x, y, z) for z in (0.001, Wt - 0.001)] for (x, y) in pts])
    PP = np.array([[tuple(M @ Vector(p)) for p in row] for row in P])
    N = np.zeros_like(PP)
    for i in range(len(pts)):
        n = Vector((pts[i][0], pts[i][1], 0)).normalized()
        N[i, :] = tuple(M.to_3x3() @ n)
    _slab_grid(mb, PP, N, -0.0002, 0.0002, "plastic")


def crate_counter(L=2.4, seed=0):
    """Mostrador de venta armado con cajas de madera militares pintadas OD (2 hiladas de 3 cajas de 0,80 × 0,55 × 0,42 m)
    con cubierta de triplay de 3/4" que vuela 10 cm hacia el cliente, apoyada en los listones de la tapa de las cajas de
    arriba. Encima: caja de dinero de lámina, tabla con clip y hojas, pluma y rollo de cinta.
    Origen: piso al centro; L en X, cliente en -Y. Cubierta a z = 0,909 m (alto total ~0,93 m con los objetos)."""
    r = rng(seed)
    mb = MB()
    n = max(1, int(round(L / 0.8)))
    w = L / n
    d, h = 0.55, 0.42
    for lay in range(2):
        for i in range(n):
            x = -L / 2 + w * (i + 0.5) + _jit(r, 0.006)
            M = _T(x, _jit(r, 0.008), lay * (h + 0.0005)) @ _Rz(_jit(r, 0.6))
            ends = (i == 0, i == n - 1)
            _od_crate(mb, M, w - 0.006, d, h, seed=seed + 7 * lay + i, ends=ends, lid_battens=(lay == 1),
                      stencil=("AMMO" if (i + lay) % 2 == 0 else "SUPPLY"), handles=ends)
    zt = 2 * h + 0.0005 + 0.02 + 0.019
    _board(mb, -L / 2 - 0.05, L / 2 + 0.05, -d / 2 - 0.1, d / 2 + 0.03, zt - 0.019, zt, "plywood", r=0.0025)
    from kit import store
    mb.join(store.cash_box(seed=seed), _T(L / 2 - 0.32, 0.02, zt) @ _Rz(8 + _jit(r, 6)))
    _clipboard(mb, _T(-0.05, -0.12, zt) @ _Rz(-6 + _jit(r, 5)), seed=seed)
    _tape_roll(mb, _T(-L / 2 + 0.25, 0.05, zt) @ _Rx(0), seed=seed)
    return mb


# ======================================================================================================== anaquel


def _ammo_can(mb, M, seed=0):
    """Caja de munición de acero tipo M2A1 (11,75 × 6 × 7,5"): cuerpo de lámina con cantos redondeados y nervio, tapa con
    faldón, empaque, asa abatible acostada, palanca de cierre en un extremo y bisagra de pasador en el otro.
    Origen: centro de la base; largo en X."""
    L, W, H = 0.298, 0.152, 0.19
    hb = H - 0.036
    slab(mb, M, L - 0.004, W - 0.004, hb, rc=0.008, re=0.0, mat="paint_od", nc=2, ne=1, re0=0.0, cap0=False, cap1=False)
    slab(mb, M @ _T(0, 0, hb - 0.004), L, W, 0.036 + 0.004, rc=0.009, re=0.006, mat="paint_od", nc=2, ne=1, re0=0.0, cap0=False)
    # asa acostada sobre la tapa
    hp = [(-0.06, 0.02, H + 0.0015), (-0.06, -0.035, H + 0.0035), (0.06, -0.035, H + 0.0035), (0.06, 0.02, H + 0.0015)]
    sweep_frame(mb, rr_profile(0.018, 0.003, 0.0012, n=1), [tuple(M @ Vector(p)) for p in fillet(hp, 0.012, 1)], "paint_od",
                up=tuple(M.to_3x3() @ Vector((0, 0, 1))))
    # palanca de cierre (extremo +X) y bisagra (extremo -X)
    _board(mb, 0.0, 0.004, -0.03, 0.03, hb - 0.075, hb + 0.03, "paint_od", r=0.0015, M=M @ _T(L / 2 - 0.001, 0, 0) @ _Ry(-7))
    _cyl(mb, tuple(M @ Vector((L / 2 + 0.004, -0.03, hb + 0.022))), tuple(M @ Vector((L / 2 + 0.004, 0.03, hb + 0.022))), 0.004,
         "paint_od", seg=12)
    _cyl(mb, tuple(M @ Vector((-L / 2 - 0.003, -0.055, hb + 0.006))), tuple(M @ Vector((-L / 2 - 0.003, 0.055, hb + 0.006))), 0.0042,
         "paint_od", seg=12)


def shelving(w=1.2, seed=0, stock="mixed"):
    """Anaquel de acero sin tornillos 48 × 18 × 72" (1,2 × 0,45 × 1,83 m, 5 entrepaños; postes de ángulo ranurado, largueros
    remachados, entrepaños de lámina con canal) cargado: stock = "cans" (cajas de munición de acero OD tipo M2A1),
    "boxes" (cajas de cartón cerradas con cinta y rótulos) o "mixed" (alternado). Uso ligero: huecos donde ya se vendió.
    Origen: piso, centrado en X; espalda contra el muro en y = 0, frente hacia -Y (pieza de muro)."""
    from kit import store
    r = rng(seed)
    mb = MB()
    d, h = 0.45, 1.83
    lv = store.snap_levels(h, 5, z_first=0.12)
    store.shelving_frame(mb, w, d, h, lv)
    kinds = {"cans": ["cans"] * 5, "boxes": ["boxes"] * 5, "mixed": ["boxes", "cans", "cans", "boxes", "boxes"]}[stock]
    words = ("KEEP DRY", "THIS SIDE UP", "FRAGILE", "HANDLE WITH CARE")
    for li, z in enumerate(lv):
        zs = z - 0.0006
        gapz = (lv[li + 1] - z - 0.05) if li + 1 < len(lv) else 0.42
        kind = kinds[li]
        xl = -w / 2 + 0.03
        xr = w / 2 - 0.03
        if kind == "cans":
            x = xl + 0.004
            while x + 0.152 <= xr:
                if r.uniform() < 0.86:
                    M = _T(x + 0.076 + _jit(r, 0.003), -d / 2 + _jit(r, 0.012), zs) @ _Rz(90 + _jit(r, 2.5))
                    _ammo_can(mb, M, seed=int(r.integers(0, 999)))
                x += 0.152 + 0.006
        else:
            x = xl + 0.005
            while x < xr - 0.15:
                bw = _f(r.uniform(0.22, 0.4))
                bw = min(bw, xr - x)
                if bw < 0.15:
                    break
                bd = _f(r.uniform(0.28, 0.4))
                bh = min(_f(r.uniform(0.18, 0.3)), gapz)
                if r.uniform() < 0.88:
                    st = (words[int(r.integers(0, 4))], 0.022) if r.uniform() < 0.5 else None
                    c = store.carton(bw - 0.008, bd, bh, seed=int(r.integers(0, 999)), crush=_f(r.uniform(0, 0.002)), stamp=st)
                    mb.join(c, _T(x + bw / 2, -0.035 - bd / 2 + _jit(r, 0.01), zs) @ _Rz(_jit(r, 2.0)))
                    if bh < gapz * 0.45 and r.uniform() < 0.5:                 # una caja chica encima
                        bh2 = min(_f(r.uniform(0.12, 0.2)), gapz - bh - 0.01)
                        if bh2 > 0.08:
                            c2 = store.carton(bw * 0.7, bd * 0.8, bh2, seed=int(r.integers(0, 999)))
                            mb.join(c2, _T(x + bw / 2 + _jit(r, 0.02), -0.035 - bd / 2, zs + bh + 0.0028) @ _Rz(_jit(r, 6)))
                x += bw + _f(r.uniform(0.006, 0.02))
    return mb


# ======================================================================================================== armero vertical
RACK_PITCH = 0.115           # paso entre ranuras del armero
RACK_TILT = 6.0              # inclinación hacia atrás de los cañones (grados)
RACK_ZC = 0.80               # altura del peine de cañones
RACK_BORE = 0.07             # eje del cañón a ~70 mm sobre la línea inferior de la culata (supuesto para el peine)


def weapon_rack_slots(n=8):
    """Matrices de colocación de las armas largas del armero (espacio local de weapon_rack(n)). Convención del arma: origen en
    la parte trasera inferior de la culata (talón inferior de la cantonera), cañón a lo largo de +X, lomo (+Z) arriba.
    En el armero el arma queda de pie sobre la cantonera en la charola: cañón hacia arriba inclinado RACK_TILT° hacia atrás
    (+Y), lomo hacia +Y (el muro) y cargador/empuñadura hacia el frente (-Y); la culata ocupa ~16 cm hacia atrás desde el
    origen y el cañón descansa en la muesca del peine (z = 0,80)."""
    th = math.radians(RACK_TILT)
    c, s = math.cos(th), math.sin(th)
    R = Matrix(((0, 1, 0, 0), (s, 0, c, 0), (c, 0, -s, 0), (0, 0, 0, 1)))
    out = []
    for i in range(n):
        x = (i - (n - 1) / 2) * RACK_PITCH
        out.append(Matrix.Translation((x, -0.085, 0.072)) @ R)
    return out


def weapon_rack(n=8, seed=0):
    """Armero vertical de acero para n armas largas (VACÍO; ver weapon_rack_slots): charola de culatas de lámina doblada con
    separadores y tapete de hule, patas de ángulo con regatones, postes de PTR de 40 × 40, peine de cañones de placa con
    muescas forradas de hule, barra de seguridad abisagrada que cierra sobre las muescas con portacandado y candado.
    Pintado verde olivo. Origen: piso al centro; frente -Y."""
    r = rng(seed)
    mb = MB()
    Wr = n * RACK_PITCH + 0.09
    x0, x1 = -Wr / 2, Wr / 2
    yf, yb = -0.12, 0.09
    zt = 0.06
    # patas de ángulo (front-back) con regatones
    for sx in (-1, 1):
        x = sx * (Wr / 2 - 0.02)
        rtube(mb, (x, -0.26, 0.022), (x, 0.22, 0.022), 0.04, 0.04, "paint_od", r=0.004)
        for y in (-0.25, 0.21):
            _lathe(mb, [(0.0, 0.0), (0.021, 0.0), (0.021, 0.004), (0.018, 0.006), (0.0, 0.006)], _T(x, y, -0.0), "rubber", seg=SEG)
    # charola: fondo y bordes de lámina doblada
    prof = [(yf, zt + 0.045), (yf, zt), (yb, zt), (yb, zt + 0.06), (yb - 0.002, zt + 0.06), (yb - 0.002, zt + 0.002),
            (yf + 0.002, zt + 0.002), (yf + 0.002, zt + 0.045)]
    from kit.store import lofts
    lofts(mb, [(x0, prof), (x1, prof)], "paint_od")
    _board(mb, x0, x0 + 0.003, yf, yb, zt - 0.02, zt + 0.06, "paint_od", r=0.001)
    _board(mb, x1 - 0.003, x1, yf, yb, zt - 0.02, zt + 0.06, "paint_od", r=0.001)
    rbox(mb, (x0 + 0.003, yf, zt - 0.02), (x1 - 0.003, yb, zt), "paint_od", r=0.003)
    _board(mb, x0 + 0.004, x1 - 0.004, yf + 0.003, yb - 0.003, zt + 0.0015, zt + 0.012, "rubber", r=0.003)
    for i in range(n + 1):                                               # separadores
        x = x0 + 0.045 + (i - 0.5) * RACK_PITCH
        if i in (0, n):
            x = x0 + 0.02 if i == 0 else x1 - 0.02
        _board(mb, x - 0.0015, x + 0.0015, yf + 0.004, yb - 0.004, zt + 0.011, zt + 0.055, "paint_od", r=0.001)
    # postes
    for sx in (-1, 1):
        x = sx * (Wr / 2 - 0.02)
        rtube(mb, (x, 0.0, 0.042), (x, 0.0, 1.0), 0.04, 0.04, "paint_od", r=0.004, up=(0, 1, 0))
        _board(mb, x - 0.022, x + 0.022, -0.022, 0.022, 1.0, 1.003, "paint_od", r=0.001)
    # peine de cañones: placa con muescas
    th = math.radians(RACK_TILT)
    tt = (RACK_ZC - 0.072 + RACK_BORE * math.sin(th)) / math.cos(th)
    yc = -0.085 + RACK_BORE * math.cos(th) + tt * math.sin(th)        # eje del cañón a la altura del peine
    rn, yfr = 0.026, yc - 0.075
    pts = []
    for i in range(n):
        xc = (i - (n - 1) / 2) * RACK_PITCH
        pts.append((xc - 0.031, yfr))
        for k in range(9):
            a = PI - PI * k / 8
            pts.append((xc + rn * math.cos(a), yc + rn * math.sin(a)))
        pts.append((xc + 0.031, yfr))
    outline = [(x0 + 0.04, yfr)] + pts + [(x1 - 0.04, yfr), (x1 - 0.04, yc + 0.07), (x0 + 0.04, yc + 0.07)]
    mb.plate(outline, 0.006, "paint_od", m=_T(0, 0, RACK_ZC - 0.003))
    for i in range(n):                                                   # forro de hule de cada muesca
        xc = (i - (n - 1) / 2) * RACK_PITCH
        up_ = [(xc - rn, yfr + 0.012, RACK_ZC), (xc - rn, yc, RACK_ZC)] + \
            [(xc + rn * math.cos(PI - PI * k / 6), yc + rn * math.sin(PI - PI * k / 6), RACK_ZC) for k in range(1, 6)] + \
            [(xc + rn, yc, RACK_ZC), (xc + rn, yfr + 0.012, RACK_ZC)]
        sweep_frame(mb, rr_profile(0.003, 0.014, 0.0012, n=1), up_, "rubber", up=(0, 0, 1))
    for sx in (-1, 1):                                                   # ménsulas del peine a los postes
        x = sx * (Wr / 2 - 0.02)
        _board(mb, x - 0.02, x + 0.02, -0.02, yc + 0.07, RACK_ZC - 0.009, RACK_ZC - 0.003, "paint_od", r=0.001)
    # barra de seguridad abisagrada (cerrada) frente a las bocas de las muescas
    yl = min(yfr - 0.008, -0.031)
    zl = RACK_ZC + 0.012
    xh = x0 + 0.02
    for k in range(3):                                                   # bisagra de nudillos al frente del poste izquierdo
        zk = zl - 0.03 + k * 0.02
        _lathe(mb, [(0.0045, 0.0), (0.0085, 0.0), (0.0085, 0.019), (0.0045, 0.019)], _T(xh, yl, zk), "paint_od", seg=SEG, closed=True)
    _cyl(mb, (xh, yl, zl - 0.034), (xh, yl, zl + 0.034), 0.0045, "steel", seg=SEG_T)
    for k in (0, 2):
        _board(mb, xh - 0.006, xh + 0.006, yl + 0.004, -0.0195, zl - 0.03 + k * 0.02, zl - 0.012 + k * 0.02, "paint_od", r=0.001)
    rtube(mb, (xh + 0.0085, yl, zl), (x1 - 0.004, yl, zl), 0.008, 0.04, "paint_od", r=0.002, up=(0, 0, 1))
    # portacandado: grapa en U soldada al frente del poste derecho que atraviesa la barra, y candado
    xs_ = x1 - 0.025
    st = [(xs_ - 0.012, -0.0205, zl), (xs_ - 0.012, yl - 0.016, zl), (xs_ + 0.012, yl - 0.016, zl), (xs_ + 0.012, -0.0205, zl)]
    _tube(mb, fillet(st, 0.006, 3), 0.004, seg=SEG_T, mat="steel")
    _padlock(mb, _T(xs_ + 0.009, yl - 0.0105, zl), seed=seed)
    del r
    return mb


def _padlock(mb, M, seed=0, scratched=False):
    """Candado de cuerpo laminado (40 mm) con arco de acero; M: origen en el punto donde el arco atraviesa el ojo, cuelga
    hacia -Z, cara al frente -Y."""
    sw = 0.022
    shackle = [(-sw / 2, 0, -0.022), (-sw / 2, 0, 0.006), (0.0, 0, 0.016), (sw / 2, 0, 0.006), (sw / 2, 0, -0.022)]
    _tube(mb, [tuple(M @ Vector(p)) for p in fillet(shackle, 0.009, 4)], 0.0036, seg=SEG_T, mat="steel")
    for k in range(5):                                                   # cuerpo de láminas remachadas
        z0 = -0.022 - k * 0.0072
        slab(mb, M @ _T(0, 0, z0 - 0.0068), 0.04, 0.024, 0.0068, rc=0.0035, re=0.0012, mat="steel", nc=2, ne=1)
    _lathe(mb, [(0.0, 0.0), (0.0062, 0.0), (0.0062, 0.0012), (0.0, 0.0012)], M @ _T(0, 0.0, -0.058) @ _Rx(180), "steel", seg=16)
    for sx in (-1, 1):
        for z in (-0.026, -0.054):
            _lathe(mb, [(0.0, 0.0), (0.0022, 0.0), (0.0, 0.0008)], M @ _T(sx * 0.016, -0.012, z) @ _Rx(90), "steel", seg=8)


# ======================================================================================================== tablero perforado
PEG = 0.0254


def _peg_grid(w, h):
    nx = int(w / PEG) - 1
    nz = int(h / PEG) - 1
    xs = [(i - (nx - 1) / 2) * PEG for i in range(nx)]
    zs = [(j + 1) * PEG + (h - (nz + 1) * PEG) / 2 for j in range(nz)]
    hooks = []
    for fz in (0.74, 0.36):
        for fx in (0.27, 0.73):
            hooks.append((int(round(fx * (nx - 1))), int(round(fz * (nz - 1)))))
    return xs, zs, hooks


def pegboard_hooks(w=1.2, h=1.0):
    """Puntos de cuelgue de los ganchos del tablero (espacio local de pegboard(w, h)): Matrix con la traslación sobre la
    varilla, a 2 cm de la punta, donde descansa la gaza / el gancho del objeto (ejes del mundo: el objeto cuelga hacia -Z con
    su frente a -Y). 4 ganchos de 4" en 2 filas × 2 columnas (dos chalecos o cuatro fundas)."""
    xs, zs, hooks = _peg_grid(w, h)
    yf = -0.025
    return [Matrix.Translation((xs[i], yf - 0.08, zs[j] + 0.0024 + 0.003)) for (i, j) in hooks]


def pegboard(w=1.2, h=1.0, seed=0):
    """Tablero perforado de 1/4" (6 mm) de fibra con agujeros de 1/4" a 1" (25,4 mm) entre centros, sobre bastidor de
    listones de 1×2" separado 19 mm del muro, pijas con rondana, y 4 ganchos de alambre de 4" con punta levantada (en
    pegboard_hooks). Los agujeros son pastillas oscuras 0,5 mm al frente de la cara (no huecos reales: ~1 750 agujeros).
    Origen: plano del muro (y = 0), centro del canto inferior del tablero; crece hacia -Y y +Z."""
    r = rng(seed)
    mb = MB()
    t = 0.006
    yb = -0.019
    yf = yb - t
    _board(mb, -w / 2, w / 2, yf, yb, 0.0, h, "plywood", r=0.0012)
    for x in (-w / 2 + 0.03, 0.0, w / 2 - 0.03):                         # listones
        _board(mb, x - 0.019, x + 0.019, yb, -0.0005, 0.02, h - 0.02, "wood", r=0.002)
    xs, zs, hooks = _peg_grid(w, h)
    used = set()
    for (i, j) in hooks:
        used |= {(i, j), (i, j + 1)}
    s = 0.0032
    mi = mb.mi("cable")
    for i, x in enumerate(xs):
        for j, z in enumerate(zs):
            if (i, j) in used or i in (0, len(xs) - 1) or j in (0, len(zs) - 1):
                continue
            v = [mb.bm.verts.new((x + a, yf - 0.0005, z + b)) for (a, b) in ((-s, -s), (s, -s), (s, s), (-s, s))]
            f = mb.bm.faces.new(v)
            f.material_index = mi
    for (x, z) in ((-w / 2 + 0.03, 0.05), (-w / 2 + 0.03, h - 0.05), (w / 2 - 0.03, 0.05), (w / 2 - 0.03, h - 0.05), (0, 0.05),
                   (0, h - 0.05)):
        _lathe(mb, [(0.0045, 0.0), (0.004, 0.0015), (0.0, 0.0022)], _T(x, yf, z) @ _Rx(90), "steel", seg=14)
    for (i, j) in hooks:                                                 # ganchos de 4" con punta levantada
        x, z, zu = xs[i], zs[j], zs[j + 1]
        L = 0.1
        path = [(x, yb + 0.004, zu - 0.008), (x, yb + 0.004, zu), (x, yf - 0.004, zu), (x, yf - 0.006, z + 0.006),
                (x, yf - L, z + 0.003), (x, yf - L - 0.01, z + 0.018)]
        _tube(mb, fillet(path, 0.005, 2), 0.0024, seg=SEG_T, mat="steel")
    del r
    return mb


# ======================================================================================================== mesa y silla plegables


def folding_table(L=1.83, seed=0):
    """Mesa plegable de 6 ft (1,83 × 0,76 × 0,74 m): cubierta de polietileno soplado de 5 cm con cantos redondeados y
    faldón, bastidor perimetral de tubo rectangular, dos juegos de patas de tubo de 1" con travesaño, tirantes plegables
    con anillo de seguro, tapones de pie. Origen: piso al centro; L en X."""
    mb = MB()
    D, H = 0.76, 0.737
    t = 0.045
    slab(mb, _T(0, 0, H - t), L, D, t, rc=0.035, re=0.012, mat="plastic", nc=4, ne=2, re0=0.006)
    for sy in (-1, 1):                                                   # largueros del bastidor
        rtube(mb, (-L / 2 + 0.06, sy * (D / 2 - 0.05), H - t - 0.0125), (L / 2 - 0.06, sy * (D / 2 - 0.05), H - t - 0.0125), 0.025,
              0.025, "steel", r=0.003)
    for sx in (-1, 1):
        rtube(mb, (sx * (L / 2 - 0.06), -D / 2 + 0.05, H - t - 0.0125), (sx * (L / 2 - 0.06), D / 2 - 0.05, H - t - 0.0125), 0.025,
              0.025, "steel", r=0.003, up=(0, 0, 1))
        xl = sx * (L / 2 - 0.11)
        R = 0.0127
        zb = 0.025
        leg = [(xl, -D / 2 + 0.085, zb), (xl, -D / 2 + 0.085, H - t - 0.03), (xl, D / 2 - 0.085, H - t - 0.03), (xl, D / 2 - 0.085, zb)]
        _tube(mb, fillet(leg, 0.05, 6), R, seg=SEG_T + 2, mat="steel")
        _cyl(mb, (xl, -D / 2 + 0.085, 0.12), (xl, D / 2 - 0.085, 0.12), 0.0095, "steel", seg=SEG)
        for sy in (-1, 1):
            _lathe(mb, [(0.0, 0.0), (0.0165, 0.0), (0.015, 0.028), (0.0, 0.028)], _T(xl, sy * (D / 2 - 0.085), 0.0), "plastic", seg=18)
        # pivote de la pata en el bastidor
        for sy in (-1, 1):
            _cyl(mb, (xl, sy * (D / 2 - 0.085) - 0.016 * sy, H - t - 0.03), (xl, sy * (D / 2 - 0.05) + 0.01 * sy, H - t - 0.03), 0.004,
                 "steel", seg=12)
        # tirante plegable: del travesaño a la cubierta, con anillo de seguro
        p0 = Vector((xl, 0.0, 0.12))
        p2 = Vector((sx * (L / 2 - 0.42), 0.0, H - t - 0.01))
        pm = p0.lerp(p2, 0.5)
        u = (p2 - p0).normalized()
        for (a, b) in ((p0, pm - u * 0.002), (pm + u * 0.002, p2)):
            for sy in (-1, 1):
                rtube_lo(mb, tuple(a + Vector((0, sy * 0.0105, 0))), tuple(b + Vector((0, sy * 0.0105, 0))), 0.004, 0.016, "steel",
                         r=0.0015, up=(0, 1, 0))
        _lathe(mb, [(0.0145, -0.018), (0.0165, -0.018), (0.0165, 0.018), (0.0145, 0.018)], _frame_z(pm, p2 - p0), "steel", seg=SEG,
               closed=True)
        _board(mb, p2.x - 0.03, p2.x + 0.03, -0.025, 0.025, H - t - 0.006, H - t, "steel", r=0.001)
    return mb


def folding_chair(seed=0):
    """Silla plegable de acero: patas delanteras y respaldo de un solo tubo de 7/8" doblado, patas traseras en U, asiento
    de lámina embutida con canto redondeado, respaldo curvo de lámina, travesaños, remaches de pivote y tapones.
    Asiento a 0,44 m, alto total 0,80 m. Pintura OD. Origen: piso al centro; frente -Y."""
    mb = MB()
    R = 0.011
    hs = 0.44
    wf = 0.40
    yfa, ytop = -0.23, 0.17
    for sx in (-1, 1):                                                   # marco delantero/respaldo (dos lados del mismo tubo en U)
        x = sx * wf / 2
        pth = [(x, yfa, 0.02), (x, 0.09, hs + 0.09), (x, ytop, 0.78)]
        _tube(mb, fillet(pth, 0.15, 6), R, seg=SEG_T + 2, mat="paint_od")
    top = [(-wf / 2, ytop, 0.78), (-wf / 2 + 0.002, ytop + 0.006, 0.80), (wf / 2 - 0.002, ytop + 0.006, 0.80), (wf / 2, ytop, 0.78)]
    _tube(mb, fillet(top, 0.03, 5), R, seg=SEG_T + 2, mat="paint_od")
    wr = 0.36
    for sx in (-1, 1):                                                   # patas traseras
        x = sx * wr / 2
        _tube(mb, [(x, 0.2, 0.02), (x, -0.04, hs - 0.03)], R * 0.95, seg=SEG_T + 2, mat="paint_od")
    _tube(mb, [(-wr / 2, 0.16, 0.09), (wr / 2, 0.16, 0.09)], R * 0.8, seg=SEG_T + 2, mat="paint_od")
    _tube(mb, [(-wf / 2, -0.205, 0.06), (wf / 2, -0.205, 0.06)], R * 0.8, seg=SEG_T + 2, mat="paint_od")
    for sx in (-1, 1):                                                   # pivotes y tapones
        x = sx * wf / 2
        _cyl(mb, (x - sx * 0.04, -0.04, hs - 0.03), (x + sx * 0.012, -0.04, hs - 0.03), 0.004, "steel", seg=12)
        for (y, xx) in ((yfa, x), (0.2, sx * wr / 2)):
            _lathe(mb, [(0.0, 0.0), (0.0135, 0.0), (0.0135, 0.03), (0.0, 0.03)], _T(xx, y, 0.0), "rubber", seg=SEG)
    # asiento de lámina embutida
    slab(mb, _T(0, -0.04, hs - 0.012), 0.39, 0.38, 0.022, rc=(0.05, 0.05, 0.05, 0.05), re=0.008, mat="paint_od", nc=4, ne=2,
         re0=0.003)
    for sx in (-1, 1):
        _board(mb, sx * (wf / 2) - 0.012 if sx > 0 else -wf / 2, sx * wf / 2 if sx > 0 else -wf / 2 + 0.012, -0.2, 0.12,
               hs - 0.02, hs - 0.012, "paint_od", r=0.001)
    # respaldo curvo
    from kit.clinic import shell_strip
    shell_strip(mb, [(0.115, 0.58), (0.135, 0.65), (0.155, 0.72)], wf - 0.02, 0.006, "paint_od", m=_T(0, 0.0, 0.0), smooth_n=3,
                edge_seg=3)
    return mb


# ======================================================================================================== series de focos


def string_lights(points=((-3.0, 0.0, 2.6), (0.0, 0.0, 2.75), (3.0, 0.0, 2.6)), n=6, seed=0):
    """Serie de focos de intemperie: cable de uso rudo con catenaria entre los puntos dados (coordenadas absolutas), n
    portalámparas de hule moldeado colgando de derivaciones cortas, foco de vidrio tipo A19 y canastilla de alambre
    (4 costillas y aro). El cable rodea cada punto de amarre con una gaza y cincho."""
    r = rng(seed)
    mb = MB()
    P = [Vector(p) for p in points]
    path = []
    for k in range(len(P) - 1):
        a, b = P[k], P[k + 1]
        Ls = (b - a).length
        seg = _catenary(a, b, 0.03 + 0.012 * Ls, n=max(5, int(Ls / 0.4)))
        path += seg if k == 0 else seg[1:]
    _tube(mb, path, 0.0045, seg=SEG_T, mat="cable")
    for p in P:                                                          # cinchos de amarre
        _lathe(mb, [(0.0058, -0.004), (0.0068, -0.004), (0.0068, 0.004), (0.0058, 0.004)], _frame_z(p, Vector((1, 0, 0.0))), "plastic",
               seg=14, closed=True)
    Q = [Vector(p) for p in path]
    acc = [0.0]
    for i in range(1, len(Q)):
        acc.append(acc[-1] + (Q[i] - Q[i - 1]).length)
    for k in range(n):
        sv = acc[-1] * (k + 0.5) / n
        i = next(j for j in range(1, len(acc)) if acc[j] >= sv)
        t = (sv - acc[i - 1]) / max(acc[i] - acc[i - 1], 1e-9)
        c = Q[i - 1].lerp(Q[i], t)
        drop = 0.06 + _jit(r, 0.01)
        top = c - Vector((0, 0, 0.004))
        _lathe(mb, [(0.0, 0.007), (0.0072, 0.003), (0.0072, -0.012)], Matrix.Translation(top), "cable", seg=14)
        _tube(mb, [tuple(top - Vector((0, 0, 0.012))), tuple(top - Vector((0, 0, drop)))], 0.0028, seg=SEG_T, mat="cable", caps=False)
        zs = top.z - drop
        Ms = _T(top.x, top.y, zs) @ _Rx(_jit(r, 4)) @ _Ry(_jit(r, 4))
        _lathe(mb, [(0.0, 0.0), (0.0145, -0.004), (0.0165, -0.05), (0.0, -0.056)], Ms, "cable", seg=16)
        _lathe(mb, [(0.012, -0.055), (0.024, -0.08), (0.03, -0.106), (0.024, -0.132), (0.0, -0.143)], Ms, "glass", seg=16)
        for q in range(2):                                               # canastilla: dos alambres cruzados en U
            a = PI / 4 + q * PI / 2
            ca, sa = math.cos(a), math.sin(a)
            rib = [(0.017 * ca, 0.017 * sa, -0.05), (0.036 * ca, 0.036 * sa, -0.092), (0.034 * ca, 0.034 * sa, -0.135),
                   (0.0, 0.0, -0.152), (-0.034 * ca, -0.034 * sa, -0.135), (-0.036 * ca, -0.036 * sa, -0.092),
                   (-0.017 * ca, -0.017 * sa, -0.05)]
            _tube(mb, [tuple(Ms @ Vector(p)) for p in rib], 0.0011, seg=6, mat="steel")
    return mb


# ======================================================================================================== letrero colgante


def hanging_sign(text="SUPPLY", w=0.9, seed=0):
    """Letrero de tabla pintado a mano: tabla de pino de 22 mm con cantos gastados y vetas (estaciones irregulares), letras
    de pintura OD en relieve de 0,5 mm (cada letra con su giro, tamaño y altura un poco distintos, como a pincel), dos
    armellas en el canto superior y cuerda de 3/8" que sube a dos puntos de amarre.
    Origen: punto medio entre los dos amarres (z = 0, p. ej. el larguero); la tabla cuelga 0,30 m abajo, cara a -Y."""
    from kit.store import plank_x
    r = rng(seed)
    mb = MB()
    hgt = 0.22
    zb = -0.30 - hgt
    M = _T(0, 0, zb) @ _Rx(90) @ _T(0, 0, -0.011)
    plank_x(mb, -w / 2, w / 2, 0.0, hgt, 0.0, 0.022, "wood", rf=0.004, rb=0.004, nst=14,
            wear=lambda x, y: 0.0006 * math.sin(x * 23 + seed) * math.sin(y * 31), M=M)
    # letras a pincel
    size = hgt * 0.6
    n = len(text)
    adv = min(size * 0.78, (w - 0.1) / max(n, 1))
    for i, ch in enumerate(text):
        if ch == " ":
            continue
        x = (i - (n - 1) / 2) * adv + _jit(r, 0.004)
        Ml = _T(x, -0.0104, zb + hgt * 0.24 + _jit(r, 0.006)) @ _Rx(90) @ _Rz(_jit(r, 3.5))
        etext(mb, ch, size * (1 + _jit(r, 0.05)), 0.0013, "paint_od", Ml, res=2, back=False, bold=True)
    # armellas y cuerda
    for sx in (-1, 1):
        x = sx * (w / 2 - 0.08)
        ze = zb + hgt
        _cyl(mb, (x, 0.0, ze - 0.012), (x, 0.0, ze + 0.008), 0.0022, "steel", seg=10)
        _ring(mb, _T(x, 0.0, ze + 0.018) @ _Rx(90), 0.0095, 0.0022, seg=14, sseg=10)
        rope = [(x, 0.0, ze + 0.024), (x + sx * 0.004, 0.0, ze + 0.06), (x + sx * 0.002, 0.0, -0.03), (x, 0.0, 0.0)]
        _tube(mb, rope, 0.0045, seg=SEG_T, mat="fabric")
        loop = [(x - 0.007, 0.0, ze + 0.03), (x - 0.012, 0.0, ze + 0.016), (x, 0.003, ze + 0.008), (x + 0.012, 0.0, ze + 0.016),
                (x + 0.007, 0.0, ze + 0.03)]
        _tube(mb, loop, 0.0042, seg=SEG_T, mat="fabric")
        _lathe(mb, [(0.0, -0.012), (0.0095, -0.009), (0.011, 0.0), (0.0095, 0.009), (0.0, 0.012)], _T(x, 0.0, ze + 0.045), "fabric",
               seg=SEG_T)
    return mb
