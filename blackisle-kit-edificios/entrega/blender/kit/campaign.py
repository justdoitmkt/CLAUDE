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
    px, py = x + 0.055, y + 0.055 * sy                                  # estaca del lado de afuera
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
    Huella útil interior: a ras de piso entre placas base x ±(L/2 - 0,125), y ±(W/2 - 0,13) (9,50 × 5,84 m con las medidas
    por omisión); arriba de 0,1 m, entre caras internas de patas y arcos extremos x ±(L/2 - 0,067), y ±(W/2 - 0,072)."""
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
    r = min(r, 0.3 * min(x1 - x0, y1 - y0, z1 - z0))
    slab(mb, (M @ Mb) if M is not None else Mb, x1 - x0, y1 - y0, z1 - z0, rc=min(r, 0.25 * min(x1 - x0, y1 - y0)), re=r, mat=mat,
         nc=1, ne=1, re0=(r if bottom else 0.0))


def plywood_floor(L=9.5, W=5.8, seed=0):
    """Piso de tarima para la tienda de campaña: durmientes de 2×4" de canto (38 × 89 mm) a 16" (406 mm) a lo largo de X,
    hojas de triplay de 4 × 8 ft (1,22 × 2,44 m) × 19 mm en hiladas trabadas con juntas de 3 mm y alturas que varían
    medio milímetro, cantos matados, tornillos avellanados sobre cada durmiente a 0,4 m; perímetro con fascia de 1×6" y
    nariz de ángulo de aluminio de 25 × 25 mm. Cara superior a z = 0,108 m.
    Origen: centro, al piso; L en X, W en Y (con 9,5 × 5,8 cabe dentro de frame_tent sin tocar sus placas base)."""
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
    zl = RACK_ZC + 0.019
    xh = x0 + 0.02
    for k in range(3):                                                   # bisagra de nudillos al frente del poste izquierdo
        zk = zl - 0.03 + k * 0.02
        _lathe(mb, [(0.0045, 0.0), (0.0085, 0.0), (0.0085, 0.019), (0.0045, 0.019)], _T(xh, yl, zk), "paint_od", seg=SEG, closed=True)
    _cyl(mb, (xh, yl, zl - 0.034), (xh, yl, zl + 0.034), 0.0045, "steel", seg=SEG_T)
    for k in (0, 2):
        _board(mb, xh - 0.006, xh + 0.006, yl + 0.004, -0.0195, zl - 0.03 + k * 0.02, zl - 0.012 + k * 0.02, "paint_od", r=0.001)
    rtube(mb, (xh + 0.0085, yl, zl), (x1 - 0.004, yl, zl), 0.008, 0.025, "paint_od", r=0.002, up=(0, 0, 1))
    rtube(mb, (x0 + 0.04, 0.0, 0.985), (x1 - 0.04, 0.0, 0.985), 0.03, 0.03, "paint_od", r=0.003)          # travesaño superior
    rtube(mb, (x0 + 0.04, 0.012, 0.42), (x1 - 0.04, 0.012, 0.42), 0.016, 0.03, "paint_od", r=0.002)       # riel trasero
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
            for q in ((v[0], v[1], v[2]), (v[0], v[2], v[3])):          # 2 triángulos: isla de 2 caras (normal estable)
                f = mb.bm.faces.new(q)
                f.material_index = mi
    for (x, z) in ((-w / 2 + 0.03, 0.05), (-w / 2 + 0.03, h - 0.05), (w / 2 - 0.03, 0.05), (w / 2 - 0.03, h - 0.05), (0, 0.05),
                   (0, h - 0.05)):
        _lathe(mb, [(0.0045, 0.0), (0.004, 0.0015), (0.0, 0.0022)], _T(x, yf, z) @ _Rx(90), "steel", seg=12)
    for (i, j) in hooks:                                                 # ganchos de 4" con punta levantada
        x, z, zu = xs[i], zs[j], zs[j + 1]
        L = 0.1
        path = [(x, yb + 0.004, zu), (x, yf - 0.005, zu), (x, yf - 0.005, z), (x, yf - L, z + 0.003), (x, yf - L - 0.01, z + 0.018)]
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
        _tube(mb, fillet(leg, 0.05, 6), R, seg=SEG_T, mat="steel")
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
            rib = [(0.017 * ca, 0.017 * sa, -0.05), (0.036 * ca, 0.036 * sa, -0.1), (0.0, 0.0, -0.153),
                   (-0.036 * ca, -0.036 * sa, -0.1), (-0.017 * ca, -0.017 * sa, -0.05)]
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


# ======================================================================================================== rack selectivo
RK_COL = 0.0762              # poste de 3" × 3"
RK_T = 0.0019                # lámina cal. 14
RK_BH, RK_BW = 0.1016, 0.0445  # larguero escalonado de 4" × 1-3/4"
RK_PITCH = 0.0508            # gotas a cada 2"
RK_CT = 0.0048               # conector del larguero: ángulo de 3/16"
RK_BP = 0.0064               # placa base de 1/4"
RK_Z0 = 0.0889               # centro de la primera hilera de gotas (3-1/2" sobre el piso)
_NV_CACHE = {}


# ---------------------------------------------------------------- utilidades de la nave (rack, jaula, montacargas, banco)
def _nv_add(mb, V, F, mat, M=None, mirror_y=False, soft=False, mats=None):
    """Agrega una malla indexada (V: (n, 3); F: tuplas de índices) transformada por M (y espejada en Y si se pide)."""
    V = np.asarray(V, float)
    if mirror_y:
        V = V * np.array([1.0, -1.0, 1.0])
    if M is not None:
        A = np.array(M)
        V = V @ A[:3, :3].T + A[:3, 3]
    vs = [mb.bm.verts.new(p) for p in V.tolist()]
    mi = mb.mi(mat)
    mis = [mb.mi(m) for m in mats] if mats else None
    sl = mb._soft_layer() if soft else None
    for k, f in enumerate(F):
        face = mb.bm.faces.new([vs[i] for i in (f[::-1] if mirror_y else f)])
        face.material_index = mis[k] if mis else mi
        if soft:
            face[sl] = 1


def _miter_path(pts, d=0.001):
    """Lazo cerrado para MB.sweep con inglete exacto: agrega puntos a 1 mm de cada esquina (MB.sweep toma como tangente la
    cuerda entre vecinos; sin esto, en marcos no cuadrados el anillo de la esquina queda sesgado y las alas se corren)."""
    P = [Vector(p) for p in pts]
    n = len(P)
    out = []
    for i in range(n):
        a, b, c = P[i - 1], P[i], P[(i + 1) % n]
        out += [tuple(b + (a - b).normalized() * d), tuple(b), tuple(b + (c - b).normalized() * d)]
    return out


def _fillet_closed(pts, radii, nseg):
    """Polígono cerrado 2D con todas las esquinas redondeadas (arcos reales); radii escalar o por esquina."""
    P = [np.array(p, float) for p in pts]
    n = len(P)
    rad = radii if isinstance(radii, (list, tuple)) else [radii] * n
    m0 = (P[-1] + P[0]) / 2
    return _fillet2d([m0] + P + [m0], list(rad), nseg)[1:-1]


def _bead(mb, pts, r=0.0022, ripple=0.14, step=0.0022, taper=True, mat=None, closed=False):
    """Cordón de soldadura MIG: tubo de 12 lados (sombreado continuo) con ondas de "monedas apiladas" y extremos que se
    adelgazan (inicio y cráter)."""
    P = [Vector(p) for p in pts]
    Q = [P[0]]
    for i in range(1, len(P)):
        a, b = P[i - 1], P[i]
        L = (b - a).length
        n = max(1, int(math.ceil(L / step)))
        for k in range(1, n + 1):
            Q.append(a.lerp(b, k / n))
    if closed:                                                      # cierre con traslape, desfasado medio paso (sin anillos
        a, b = P[-1], P[0]                                          # coincidentes con el inicio)
        L = (b - a).length
        n = max(1, int(math.ceil(L / step)))
        for k in range(n):
            Q.append(a.lerp(b, (k + 0.5) / n))
        d = (P[1] - P[0])
        Q.append(P[0] + d * min(0.5, step * 1.5 / max(d.length, 1e-6)))
    N = len(Q)
    radii = []
    for i in range(N):
        f = 1.0 + ripple * (1.0 if i % 2 == 0 else -1.0)
        if taper:
            e = min(i, N - 1 - i)
            f *= (0.45 + 0.55 * min(1.0, e / 2.0))
        radii.append(r * f)
    with mb.soft():
        mb.tube([tuple(q) for q in Q], r, seg=12, mat=mat or "steel", caps=True, radii=radii)


def _nv_washer(mb, M, ro, ri, t, mat="galvanized", seg=SEG):
    """Rondana plana con cantos redondeados (z = 0 a t sobre el plano local)."""
    e = min(t * 0.3, 0.0005)
    _lathe(mb, [(ri, 0.0), (ro - e, 0.0), (ro, e), (ro, t - e), (ro - e, t), (ri + e, t), (ri, t - e)], M, mat, seg=seg, closed=True)


def _nv_nut(mb, M, s, h, mat="galvanized", hole=0.0):
    """Tuerca hexagonal (s entre caras) con chaflán de 30° arriba y abajo, apoyada en z = 0 local."""
    R = s / 2 / math.cos(PI / 6)
    prof = [(s * 0.46, 0.0), (R * 0.93, 0.0), (R, h * 0.12), (R, h * 0.88), (R * 0.93, h), (s * 0.46, h)]
    if hole:
        prof += [(hole, h), (hole, 0.0)]
        revolve(mb, prof, mat, seg=6, M=M, phase=PI / 6, closed=True)
    else:
        prof = [(0.0, 0.0)] + prof + [(0.0, h)]
        revolve(mb, prof, mat, seg=6, M=M, phase=PI / 6)
    mb.bm.faces.ensure_lookup_table()


def _nv_thread(mb, M, d, L, pitch, mat="galvanized", seg=SEG, dome=True):
    """Espárrago roscado de z = 0 a L (filetes como anillos en V, punta achaflanada)."""
    prof = [(0.0, 0.0), (d / 2 * 0.86, 0.0)]
    z = 0.0
    while z + pitch < L - pitch * 0.6:
        prof += [(d / 2, z + pitch * 0.5), (d / 2 * 0.86, z + pitch)]
        z += pitch
    prof += [(d / 2 * 0.95, L - pitch * 0.4), (d / 2 * 0.7, L), (0.0, L + (0.0006 if dome else 0.0))]
    _lathe(mb, prof, M, mat, seg=seg)


def _nv_anchor(mb, p, d=0.0127, proud=0.014, mat="galvanized", plate_mat=None):
    """Taquete de expansión (cuña) de 1/2" asomado sobre una placa: rondana, tuerca hexagonal y espárrago roscado."""
    M = Matrix.Translation(Vector(p))
    _nv_washer(mb, M, d * 1.06, d * 0.53, 0.0025, mat)
    _nv_nut(mb, M @ _T(0, 0, 0.0025), d * 1.5, d * 0.85, mat, hole=d * 0.5)
    _nv_thread(mb, M @ _T(0, 0, 0.002), d, proud + d * 0.85, 0.00195, mat)


def _nv_bolt_head(mb, M, d=0.0095, mat="galvanized", washer=True):
    """Cabeza hexagonal con rondana (eje +Z local, apoyada en z = 0; hundida 0,2 mm para asentar)."""
    M = M @ _T(0, 0, -0.0002)
    z = 0.0
    if washer:
        _nv_washer(mb, M, d * 1.05, d * 0.53, 0.0018, mat)
        z = 0.0018
    _nv_nut(mb, M @ _T(0, 0, z), d * 1.5, d * 0.65, mat)


def _rk_tear_pts():
    """Gota del poste (2D, centrada en su celda, ancha arriba): arco superior r = 8,2 mm con centro en +4 mm, flancos
    tangentes a un arco inferior r = 3,2 mm con centro en -10,5 mm (≈ 16 × 26 mm). 24 puntos antihorarios."""
    c1, r1, c2, r2 = 0.0040, 0.0082, -0.0105, 0.0032
    al = math.asin((r2 - r1) / (c1 - c2))
    P = []
    for k in range(7):
        a = (PI - al) + ((2 * PI + al) - (PI - al)) * k / 6
        P.append((r2 * math.cos(a), c2 + r2 * math.sin(a)))
    t2 = (r2 * math.cos(al), c2 + r2 * math.sin(al))
    t1 = (r1 * math.cos(al), c1 + r1 * math.sin(al))
    for k in (1, 2):
        P.append((t2[0] + (t1[0] - t2[0]) * k / 3, t2[1] + (t1[1] - t2[1]) * k / 3))
    for k in range(13):
        a = al + ((PI - al) - al) * k / 12
        P.append((r1 * math.cos(a), c1 + r1 * math.sin(a)))
    for k in (1, 2):
        P.append((-t1[0] + (-t2[0] + t1[0]) * k / 3, t1[1] + (t2[1] - t1[1]) * k / 3))
    return np.array(P)


def _zip_bridge(O, Hh, c):
    """Triangula el anillo entre un contorno exterior O (n_o puntos 2D) y un hueco Hh (n_h), ambos antihorarios alrededor
    de c. Devuelve triángulos [(('o', j), ('h', i), ...)] (cremallera por ángulo)."""
    ao = np.arctan2(O[:, 1] - c[1], O[:, 0] - c[0])
    ah = np.arctan2(Hh[:, 1] - c[1], Hh[:, 0] - c[0])
    a0 = ao[0]
    ao = (ao - a0) % (2 * PI)
    ah = (ah - a0 + PI) % (2 * PI) - PI
    i0 = int(np.argmin(np.abs(ah)))
    n_o, n_h = len(O), len(Hh)
    hi = [(i0 + i) % n_h for i in range(n_h)]
    ahs = np.array([ah[k] for k in hi])
    ahs = np.concatenate([[ahs[0]], ahs[0] + (ahs[1:] - ahs[0]) % (2 * PI)])
    aos = np.concatenate([ao, [2 * PI]])
    ahs = np.concatenate([ahs, [ahs[0] + 2 * PI]])
    tris = []
    i = j = 0
    while i < n_h or j < n_o:
        if j < n_o and (i >= n_h or aos[j + 1] <= ahs[i + 1]):
            tris.append((("o", j % n_o), ("o", (j + 1) % n_o), ("h", hi[i % n_h])))
            j += 1
        else:
            tris.append((("o", j % n_o), ("h", hi[(i + 1) % n_h]), ("h", hi[i % n_h])))
            i += 1
    return tris


def _rk_column_geo(H):
    """Poste rolado de 3" × 3" cal. 14 en C con labios (abre hacia +Y, el alma da a -Y = pasillo), radios de doblez reales
    y perforación REAL: dos hileras de gotas en el alma y una hilera de barrenos de 7/16" en cada costado (para pernos J y
    separadores), todo a paso de 2". Malla indexada (V, F) del poste delantero centrado en el origen; caché por altura."""
    key = ("col", round(H, 4))
    if key in _NV_CACHE:
        return _NV_CACHE[key]
    a, t = RK_COL / 2, RK_T
    ac, rb, lip, nb = a - t / 2, 0.0035, 0.0175, 4
    S, N = [], []

    def line(p0, p1, n, first):
        T = np.array(p1, float) - np.array(p0, float)
        T /= np.linalg.norm(T)
        for k in range(0 if first else 1, n + 1):
            S.append((p0[0] + (p1[0] - p0[0]) * k / n, p0[1] + (p1[1] - p0[1]) * k / n))
            N.append((T[1], -T[0]))

    def arc(c, a0, a1):
        for k in range(1, nb + 1):
            g = a0 + (a1 - a0) * k / nb
            S.append((c[0] + rb * math.cos(g), c[1] + rb * math.sin(g)))
            N.append((math.cos(g), math.sin(g)))
    cells = []
    line((-ac + lip, ac), (-ac + rb, ac), 2, True)
    arc((-ac + rb, ac - rb), PI / 2, PI)
    i0 = len(S) - 1
    line((-ac, ac - rb), (-ac, -ac + rb), 8, False)
    cells.append((i0 + 4, i0 + 8, "side"))
    arc((-ac + rb, -ac + rb), PI, 1.5 * PI)
    i0 = len(S) - 1
    line((-ac + rb, -ac), (ac - rb, -ac), 8, False)
    cells += [(i0, i0 + 4, "tear"), (i0 + 4, i0 + 8, "tear")]
    arc((ac - rb, -ac + rb), 1.5 * PI, 2 * PI)
    i0 = len(S) - 1
    line((ac, -ac + rb), (ac, ac - rb), 8, False)
    cells.append((i0, i0 + 4, "side"))
    arc((ac - rb, ac - rb), 0.0, PI / 2)
    line((ac - rb, ac), (ac - lip, ac), 2, False)
    S, N = np.array(S), np.array(N)
    ns = len(S)
    # estaciones en Z: tramo liso abajo, hileras de perforación (3 estaciones c/u) y tramo liso arriba
    p = RK_PITCH
    zc = [RK_Z0 + k * p for k in range(200) if RK_Z0 + k * p + p / 2 < H - 0.03]
    Z = [RK_BP]
    rows = []
    for zk in zc:
        k0 = len(Z) - 1 if abs(Z[-1] - (zk - p / 2)) < 1e-9 else len(Z)
        if k0 == len(Z):
            Z.append(zk - p / 2)
        Z += [zk, zk + p / 2]
        rows.append((k0, zk))
    Z.append(H)
    Z = np.array(Z)
    nz = len(Z)
    O3 = np.zeros((ns, nz, 3))
    I3 = np.zeros((ns, nz, 3))
    O3[:, :, :2] = (S + N * t / 2)[:, None, :]
    I3[:, :, :2] = (S - N * t / 2)[:, None, :]
    O3[:, :, 2] = Z[None, :]
    I3[:, :, 2] = Z[None, :]
    V = [O3.reshape(-1, 3), I3.reshape(-1, 3)]
    nv = [2 * ns * nz]

    def o(i, k):
        return i * nz + k

    def n_(i, k):
        return ns * nz + i * nz + k
    F = []
    covered = np.zeros((ns - 1, nz - 1), bool)
    tear = _rk_tear_pts()
    circ = np.array([(0.0055 * math.cos(2 * PI * k / 16 - PI / 2), 0.0055 * math.sin(2 * PI * k / 16 - PI / 2)) for k in range(16)])
    for (k0, zk) in rows:
        for (ia, ib, kind) in cells:
            covered[ia:ib, k0:k0 + 2] = True
            per = [(i, k0) for i in range(ia, ib + 1)] + [(ib, k0 + 1)] + [(i, k0 + 2) for i in range(ib, ia - 1, -1)] + [(ia, k0 + 1)]
            T = (S[ib] - S[ia]) / np.linalg.norm(S[ib] - S[ia])
            Nn = N[(ia + ib) // 2]
            sc = (S[ia] + S[ib]) / 2
            # perímetro en coordenadas de la celda (u a lo largo de T, z relativo al centro de la hilera)
            O2 = np.array([((S[i] - sc) @ T, Z[k] - zk) for (i, k) in per])
            hole = tear if kind == "tear" else circ
            nh = len(hole)
            base = nv[0]
            for side, sg in ((0, 1.0), (1, -1.0)):
                P3 = np.zeros((nh, 3))
                P3[:, :2] = sc + np.outer(hole[:, 0], T) + Nn * sg * t / 2
                P3[:, 2] = zk + hole[:, 1]
                V.append(P3)
            nv[0] += 2 * nh
            ho = lambda i: base + i          # noqa: E731
            hi = lambda i: base + nh + i     # noqa: E731
            for tri in _zip_bridge(O2, hole, (0.0, 0.0)):
                fo = tuple(o(*per[j]) if s == "o" else ho(j) for (s, j) in tri)
                fi = tuple(n_(*per[j]) if s == "o" else hi(j) for (s, j) in tri)
                F.append(fo)
                F.append(fi[::-1])
            for j in range(nh):
                jj = (j + 1) % nh
                F.append((ho(j), ho(jj), hi(jj), hi(j)))
    for i in range(ns - 1):
        for k in range(nz - 1):
            if covered[i, k]:
                continue
            F.append((o(i, k), o(i + 1, k), o(i + 1, k + 1), o(i, k + 1)))
            F.append((n_(i, k), n_(i, k + 1), n_(i + 1, k + 1), n_(i + 1, k)))
    for i in range(ns - 1):                                              # cortes de los extremos
        F.append((o(i, 0), n_(i, 0), n_(i + 1, 0), o(i + 1, 0)))
        F.append((o(i, nz - 1), o(i + 1, nz - 1), n_(i + 1, nz - 1), n_(i, nz - 1)))
    for k in range(nz - 1):                                              # cantos libres de los labios
        F.append((o(0, k), o(0, k + 1), n_(0, k + 1), n_(0, k)))
        F.append((o(ns - 1, k), n_(ns - 1, k), n_(ns - 1, k + 1), o(ns - 1, k + 1)))
    Vall = np.concatenate(V)
    used = np.zeros(len(Vall), bool)
    for f in F:
        used[list(f)] = True
    remap = -np.ones(len(Vall), int)
    remap[used] = np.arange(int(used.sum()))
    F = [tuple(int(remap[i]) for i in f) for f in F]
    res = (Vall[used], F, rows)
    _NV_CACHE[key] = res
    return res


def _rk_lprof(a, z0, z1, re=0.0012, n=2):
    """Lazos para extruir en Z un perfil 2D cerrado con los cantos superior e inferior redondeados (re)."""
    P = np.array(a, float)
    Nn = _normals2d(np.vstack([P[-1:], P, P[:1]]))[1:-1]
    area = 0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1])
    if area < 0:
        Nn = -Nn
    loops = []
    for j in range(n + 1):
        g = PI / 2 * j / n
        d = re * (1 - math.sin(g))
        loops.append([(x, y, z0 + re * (1 - math.cos(g))) for (x, y) in (P + Nn * d)])
    for j in range(n + 1):
        g = PI / 2 * j / n
        d = re * (1 - math.cos(g))
        loops.append([(x, y, z1 - re + re * math.sin(g)) for (x, y) in (P + Nn * d)])
    return loops


def _rk_brace(mb, x, A, B, yc0, yc1):
    """Riostra de canal de 1-1/2" × 1" cal. 16 en el plano YZ del marco, de A=(y, z) a B=(y, z); extremos cortados en los
    planos y = yc0 y y = yc1 (dentro de la C del poste). El canal abre hacia -n (n = normal en el plano)."""
    A = Vector((x, A[0], A[1]))
    B = Vector((x, B[0], B[1]))
    d = (B - A).normalized()
    n = Vector((0.0, -d.z, d.y))
    if n.z < 0 or (abs(n.z) < 1e-6 and n.y < 0):
        n = -n
    X = Vector((1, 0, 0))
    w, h, t, r = 0.0381, 0.0254, 0.0016, 0.0025
    cl = _fillet2d([(-w / 2 + t / 2, -h / 2), (-w / 2 + t / 2, h / 2 - t / 2), (w / 2 - t / 2, h / 2 - t / 2), (w / 2 - t / 2, -h / 2)],
                   r, 3)
    Nn = _normals2d(cl)
    prof = [tuple(q) for q in (cl + Nn * t / 2)] + [tuple(q) for q in (cl - Nn * t / 2)[::-1]]
    rings = []
    for (yc, P0) in ((yc0, A), (yc1, B)):
        ring = []
        for (px, pn) in prof:
            q = P0 + X * px + n * pn
            lam = (yc - q.y) / d.y
            ring.append(q + d * lam)
        rings.append(ring)
    loft_rings(mb, rings, "rack_blue")
    return d, n


def _rk_frame(mb, x, yc, H, seed=0):
    """Bastidor soldado: postes delantero y trasero, placas base de 1/4" soldadas con dos anclas cada una, riostras
    horizontales y diagonales en zigzag soldadas dentro de la C con cordones visibles."""
    V, F, _ = _rk_column_geo(H)
    a = RK_COL / 2
    for front in (-1, 1):
        y = front * yc
        _nv_add(mb, V, F, "rack_blue", M=_T(x, y, 0.0), mirror_y=(front > 0))
        # placa base 6 × 4 × 1/4" con cordón alrededor del poste
        slab(mb, _T(x, y, 0.0), 0.1524, 0.1016, RK_BP, rc=0.006, re=0.0012, mat="rack_blue", nc=3, ne=2)
        ac = a + 0.0009
        path = []
        for (px, py) in ((-ac + 0.016, ac), (-ac, ac), (-ac, -ac), (ac, -ac), (ac, ac), (ac - 0.016, ac)):
            path.append((x + px, y + (py if front < 0 else -py), RK_BP + 0.0012))
        _bead(mb, fillet(path, 0.004, 3), r=0.0024, mat="rack_blue")
        for sx in (-1, 1):
            _nv_anchor(mb, (x + sx * 0.0575, y, RK_BP), proud=0.012)
    # riostras
    yl = yc - a                                       # plano de los labios (por dentro del marco)
    ycut = yc + a - 0.014                             # corte de la riostra: 12 mm antes del alma (dentro de la C)
    zs = [0.127] + [0.127 + (H - 0.203) * k / 5 for k in range(1, 6)]
    braces = [((-yc, zs[0]), (yc, zs[0])), ((-yc, zs[-1]), (yc, zs[-1]))]
    for k in range(len(zs) - 1):
        if k % 2 == 0:
            braces.append(((-yc, zs[k] + 0.03), (yc, zs[k + 1] - 0.03)))
        else:
            braces.append(((yc, zs[k] + 0.03), (-yc, zs[k + 1] - 0.03)))
    for (A, B) in braces:
        y0c, y1c = (-ycut, ycut) if A[0] < B[0] else (ycut, -ycut)
        d, n = _rk_brace(mb, x, A, B, y0c, y1c)
        # cordones en los dos costados donde la riostra cruza el plano de los labios
        for ysgn in (-1, 1):
            yw = ysgn * (yl - 0.0012)
            P0 = Vector((x, A[0], A[1]))
            pts = []
            for pn in (-0.0127, 0.0127):
                q = P0 + n * pn
                lam = (yw - q.y) / d.y
                pts.append(q + d * lam)
            for sx in (-1, 1):
                xb = x + sx * 0.0203
                _bead(mb, [(xb, p.y, p.z) for p in pts], r=0.0021, mat="rack_blue")
    del seed


def _rk_beam(mb, xa, xb, z, side, yo, label=None):
    """Larguero escalonado de 4" (perfil rolado cerrado con radios de 4 mm) de xa a xb; yo = cara exterior; side = -1
    frente (escalón hacia +Y), +1 atrás. Cordones de soldadura al conector en ambos extremos."""
    st, sd = 0.0159, 0.0413                                  # escalón de 5/8" × 1-5/8"
    zb = z - RK_BH
    P = [(0.0, 0.0), (RK_BW, 0.0), (RK_BW, RK_BH - sd), (RK_BW - st, RK_BH - sd), (RK_BW - st, RK_BH), (0.0, RK_BH)]
    pr = _fillet_closed(P, [0.004, 0.004, 0.003, 0.0016, 0.003, 0.004], 4)
    pp = [(yo - side * u, zb + v) for (u, v) in pr]
    skin(mb, [[(xa, py, pz) for (py, pz) in pp], [(xb, py, pz) for (py, pz) in pp]], "rack_orange")
    loop = np.array(pr)
    Nl = _normals2d(np.vstack([loop[-1:], loop, loop[:1]]))[1:-1]
    if 0.5 * np.sum(loop[:, 0] * np.roll(loop[:, 1], -1) - np.roll(loop[:, 0], -1) * loop[:, 1]) < 0:
        Nl = -Nl
    loop = loop + Nl * 0.0011
    for (xw, sx) in ((xa, 1), (xb, -1)):
        pts = [(xw + sx * 0.0016, yo - side * u, zb + v) for (u, v) in loop]
        _bead(mb, pts, r=0.0021, mat="rack_orange", closed=True, step=0.003)


def _rk_connector(mb, xc, sx, yface, side, ztop, seed=0):
    """Conector de 3 pernos: ángulo de 3/16" que abraza la esquina del poste (pata con remaches de gota sobre el alma y pata
    lateral donde va soldado el larguero), cantos redondeados, 3 cabezas de remache y seguro de resorte remachado."""
    a = RK_COL / 2
    t = RK_CT
    z0, z1 = ztop - 0.152, ztop + 0.012
    # perfil en planta (u = x relativo al poste por el lado del larguero, v = y hacia afuera del alma, + = pasillo)
    P = [(-0.002, 0.0), (a, 0.0), (a, -0.046), (a + t, -0.046), (a + t, t), (-0.002, t)]
    pr = _fillet_closed(P, [0.001, 0.0045, 0.0008, 0.0008, 0.0093, 0.001], 4)
    pts = [(xc + sx * u, yface + side * v) for (u, v) in pr]
    if (sx * side) > 0:
        pts = pts[::-1]
    skin(mb, _rk_lprof(pts, z0, z1, re=0.0012, n=2), "rack_orange")
    for k in range(3):                                       # cabezas de remache (domo) en la pata del alma
        zr = ztop - 0.025 - k * RK_PITCH
        Mr = _frame_z(Vector((xc + sx * 0.0168, yface + side * (t - 0.0003), zr)), Vector((0, side, 0)))
        _lathe(mb, [(0.0, 0.0), (0.0068, 0.0), (0.0066, 0.0012), (0.0055, 0.0026), (0.0032, 0.0034), (0.0, 0.0036)], Mr,
               "rack_orange", seg=SEG)
    # seguro de resorte: lengüeta de lámina remachada arriba de la pata del alma, con la uña doblada hacia la gota
    xs_ = xc + sx * 0.0168
    yb_ = yface + side * (t - 0.0002)
    Ml = _frame_z(Vector((xs_, yb_, ztop - 0.012)), Vector((0, side, 0)), (1, 0, 0))
    slab(mb, Ml @ _T(0, 0.0, 0.0), 0.011, 0.004, 0.0013, rc=0.0018, re=0.0004, mat="galvanized", nc=2, ne=1)
    tongue = [(xs_, yb_ + side * 0.0012, ztop - 0.016), (xs_, yb_ + side * 0.0012, ztop + 0.002), (xs_, yb_ + side * 0.0045, ztop + 0.009)]
    sweep_frame(mb, rr_profile(0.0105, 0.0013, 0.0005, n=1), fillet(tongue, 0.004, 3), "galvanized", up=(0, side, 0))
    _lathe(mb, [(0.0, 0.0), (0.0032, 0.0), (0.003, 0.0008), (0.0018, 0.0016), (0.0, 0.0018)],
           _frame_z(Vector((xs_, yb_ + side * 0.001, ztop - 0.012)), Vector((0, side, 0))), "galvanized", seg=SEG)
    del seed


def _wire_deck(mb, x0, x1, yfo, ybo, z, seed=0):
    """Parrilla de alambre tipo cascada de 46 × 42": alambres de frente a fondo (cal. 6, Ø 4,9 mm) a cada 2-1/2" que bajan
    1" por fuera de ambos largueros con radio de doblez, travesaños por debajo a cada 4" y 3 canales de apoyo (sombrero de
    cal. 14) que asientan en el escalón de los largueros. yfo / ybo = caras exteriores de los largueros delantero / trasero."""
    rL, rC = 0.00245, 0.0021
    zL = z + rL
    yfi, ybi = yfo + RK_BW, ybo - RK_BW
    nL = max(2, int(round((x1 - x0 - 0.02) / 0.0635)))
    with mb.soft():
        for i in range(nL + 1):
            x = x0 + 0.01 + (x1 - x0 - 0.02) * i / nL
            yA, yB = yfo - rL + 0.0003, ybo + rL - 0.0003
            path = [(x, yA, z - 0.026), (x, yA, zL), (x, yB, zL), (x, yB, z - 0.026)]
            mb.tube(fillet(path, 0.007, 5), rL, seg=12, mat="galvanized")
        zC = zL - rL - rC + 0.0007
        m = int((ybi - yfi - 0.03) / 0.1016)
        for j in range(m + 1):
            y = yfi + 0.015 + (ybi - yfi - 0.03) * j / m
            mb.tube([(x0 + 0.004, y, zC), (x1 - 0.004, y, zC)], rC, seg=12, mat="galvanized")
    zst = z - 0.0413
    ztop = zC - rC + 0.0004
    hh = ztop - zst
    t = 0.0019
    hat = [(-0.024, -t / 2), (-0.014, -t / 2), (-0.0115, -hh + t / 2), (0.0115, -hh + t / 2), (0.014, -t / 2), (0.024, -t / 2)]
    cl = _fillet2d(hat, 0.0025, 4)
    Nn = _normals2d(cl)
    prof = [tuple(q) for q in (cl - Nn * t / 2)] + [tuple(q) for q in (cl + Nn * t / 2)[::-1]]
    for xc in (x0 + 0.09, (x0 + x1) / 2, x1 - 0.09):
        sweep_frame(mb, [(-u, v) for (u, v) in prof], [(xc, yfi - 0.0145, ztop), (xc, ybi + 0.0145, ztop)], "galvanized",
                    up=(0, 0, 1))
    del seed


def _rk_guard(mb, x, yf, seed=0, scuff=False):
    """Protector de poste atornillado al piso, frente al poste del pasillo: placa de 1/4" doblada en U (nariz de 16 cm,
    18" de alto) con radios de doblez, canto superior redondeado, dos patas soldadas con ancla y, si scuff, rozones de
    montacargas (pintura raspada y marca de llanta)."""
    r = rng(seed)
    t = 0.0064
    yb = yf - 0.0075
    yn = yf - 0.044 + t / 2
    hw = 0.08
    cl = _fillet2d([(x - hw, yb), (x - hw, yn + 0.018), (x - hw + 0.03, yn), (x + hw - 0.03, yn), (x + hw, yn + 0.018), (x + hw, yb)],
                   0.014, 4)
    Nn = _normals2d(cl)
    prof = [tuple(q) for q in (cl + Nn * t / 2)] + [tuple(q) for q in (cl - Nn * t / 2)[::-1]]
    skin(mb, _rk_lprof(prof, 0.0, 0.457, re=0.0022, n=3), "paint_yellow")
    for sx in (-1, 1):
        xf = x + sx * (hw + t / 2)
        slab(mb, _T(xf + sx * 0.035, (yb + yn) / 2 + 0.002, 0.0), 0.07, 0.034, 0.0064, rc=0.006, re=0.0012, mat="paint_yellow", nc=3,
             ne=2)
        _bead(mb, [(xf + sx * 0.0018, yb - 0.002, 0.0074), (xf + sx * 0.0018, yn + 0.004, 0.0074)], r=0.0022, mat="paint_yellow")
        _nv_anchor(mb, (xf + sx * 0.042, (yb + yn) / 2 + 0.002, 0.0064), proud=0.012)
    if scuff:
        yfr = yn - t / 2
        for k in range(5):                                   # pintura raspada (acero) y marcas de llanta (hule)
            zc = 0.09 + float(r.uniform(0.0, 0.12))
            xc = x + float(r.uniform(-0.05, 0.05))
            ln = float(r.uniform(0.03, 0.08))
            ang = float(r.uniform(-12, 12))
            mat = "steel" if k < 3 else "rubber"
            Ms = _T(xc, yfr + 0.0002, zc) @ _Ry(ang) @ _Rx(90)
            slab(mb, Ms, ln, 0.004 + 0.004 * (k >= 3), 0.0006, rc=0.0018, re=0.0002, mat=mat, nc=2, ne=1)


def _rk_plaque(mb, x, yf, z, seed=0):
    """Placa de capacidad de carga de aluminio (9 × 6") atornillada al alma del poste por dos gotas."""
    w, h, t = 0.2286, 0.1524, 0.0016
    Mp = _T(x, yf + 0.0002, z) @ _Rx(90)
    slab(mb, Mp @ _T(0, 0, 0), w, h, t, rc=0.008, re=0.0005, mat="sign_white", nc=3, ne=1)
    slab(mb, Mp @ _T(0, h / 2 - 0.0185, t - 0.0002), w - 0.012, 0.031, 0.0005, rc=0.004, re=0.0002, mat="sign_red", nc=2, ne=1)
    from kit.fonts import text_font
    text_font(mb, "LOAD CAPACITY", 0.017, 0.0005, "sign_white", Mp @ _T(0, h / 2 - 0.0255, t + 0.0003), font="sign", bold=True, res=2)
    lines = [("MAX 4,500 LB PER LEVEL", 0.0118, True), ("MAX 13,500 LB PER BAY", 0.0118, True),
             ("UNIFORMLY DISTRIBUTED LOADS ONLY", 0.0072, False), ("DO NOT CLIMB  -  REPORT ALL DAMAGE", 0.0072, False)]
    zl = h / 2 - 0.058
    for (s, sz, b) in lines:
        text_font(mb, s, sz, 0.0004, "cable", Mp @ _T(0, zl, t), font="sign", bold=b, res=2)
        zl -= sz * 1.75
    for zz in (h / 2 - 0.041, -h / 2 + 0.01):                # tornillos a las gotas del poste (fuera del texto)
        _nv_bolt_head(mb, Mp @ _T(-0.0168, zz, t), d=0.0064)


def _rk_label(mb, x, y, z, text, seed=0):
    """Etiqueta de ubicación adherida al frente del larguero: placa de 100 × 38 mm con texto y código de barras."""
    from kit.fonts import text_font
    r = rng(seed)
    M = _T(x, y + 0.0001, z) @ _Rx(90)
    slab(mb, M, 0.1, 0.038, 0.0006, rc=0.002, re=0.0002, mat="sign_white", nc=2, ne=1)
    text_font(mb, text, 0.0125, 0.0003, "cable", M @ _T(-0.024, 0.004, 0.0005), font="sign", bold=True, res=2)
    xb = 0.006
    while xb < 0.044:
        wbar = float(r.choice([0.0005, 0.0008, 0.0012]))
        slab(mb, M @ _T(xb + wbar / 2, -0.004, 0.0005), wbar, 0.022, 0.0002, rc=0.0001, re=0.0, mat="cable", nc=1, ne=1, re0=0.0)
        xb += wbar + float(r.choice([0.0005, 0.0008, 0.001]))


def _rk_levels(levels):
    """Altura del borde superior de los largueros de cada nivel (primer nivel a 0,15 m sobre el piso, luego cada 1,55 m)."""
    return [0.15 + 1.55 * k for k in range(levels)]


def _rk_height(levels):
    return round((_rk_levels(levels)[-1] + 0.41) / 0.3048) * 0.3048          # postes en pies cerrados (3 niveles: 12 ft)


def pallet_rack_slots(bays=3, levels=3, depth=1.1, bay_w=2.7):
    """Matrices de carga del rack (espacio local de pallet_rack): 2 tarimas por claro y nivel. Convención de la tarima:
    origen al centro de su cara inferior, lado de 48" sobre su X local y 40" sobre Y. La matriz la gira 90° para que el
    lado de 48" corra de frente a fondo (Y) con el frente de 40" hacia el pasillo (-Y), apoyada sobre la parrilla
    (z = borde superior del larguero + 5 mm)."""
    out = []
    W = bays * bay_w
    for b in range(bays):
        xc = -W / 2 + (b + 0.5) * bay_w
        inner = bay_w - RK_COL
        for z in _rk_levels(levels):
            for s in (-1, 1):
                out.append(Matrix.Translation((xc + s * inner / 4, 0.0, z + 0.005)) @ _Rz(90))
    return out


def pallet_rack(bays=3, levels=3, depth=1.1, bay_w=2.7, seed=0):
    """Rack selectivo de tarimas tipo gota (VACÍO; cargas en pallet_rack_slots). Postes rolados de 3" × 3" cal. 14 con
    perforación REAL (gotas a cada 2" en el alma y barrenos laterales), bastidores soldados (riostras de canal en zigzag
    con cordones visibles), placas base de 1/4" con dos anclas de cuña (rondana, tuerca y espárrago roscado), largueros
    escalonados de 4" con conector de ángulo de 3 remaches soldado (cordón perimetral) y perno de seguridad J, parrillas de
    alambre en cascada (2 por claro y nivel) con canales asentados en el escalón, protectores amarillos atornillados al piso
    en los postes del pasillo (uno con rozones de montacargas), placa de capacidad en el poste de la cabecera y etiquetas
    de ubicación con código de barras en los largueros. Origen: piso al centro de la hilera; claros a lo largo de X,
    pasillo hacia -Y, fondo del marco = depth."""
    r = rng(seed)
    mb = MB()
    W = bays * bay_w
    H = _rk_height(levels)
    a = RK_COL / 2
    yc = depth / 2 - a
    lv = _rk_levels(levels)
    yfc = -yc - a                                                       # cara del alma de los postes del pasillo
    dent = int(r.integers(bays + 1))
    for f in range(bays + 1):
        x = -W / 2 + f * bay_w
        _rk_frame(mb, x, yc, H, seed=seed + f)
        _rk_guard(mb, x, yfc, seed=seed * 7 + f, scuff=(f == dent))
    _rk_plaque(mb, -W / 2, yfc, 1.32, seed=seed)
    row = "ABCDEFGH"[(seed // 10 * 2 + seed % 10) % 8]
    for b in range(bays):
        xl = -W / 2 + b * bay_w
        xr = xl + bay_w
        for li, z in enumerate(lv):
            for side in (-1, 1):
                yface = side * (yc + a)
                yo = yface + side * RK_CT
                xa, xb = xl + a + RK_CT, xr - a - RK_CT
                _rk_beam(mb, xa, xb, z, side, yo)
                _rk_connector(mb, xl, 1, yface, side, z, seed=seed)
                _rk_connector(mb, xr, -1, yface, side, z, seed=seed)
            _rk_label(mb, xl + 0.16, -(yc + a) - RK_CT, z - 0.05, f"{row}-{b + 1:02d}-{li + 1}", seed=seed * 31 + b * 3 + li)
            inner0, inner1 = xl + a + RK_CT + 0.008, xr - a - RK_CT - 0.008
            mid = (inner0 + inner1) / 2
            for (x0, x1) in ((inner0, mid - 0.006), (mid + 0.006, inner1)):
                _wire_deck(mb, x0, x1, -(yc + a) - RK_CT, (yc + a) + RK_CT, z, seed=seed)
    return mb

# ======================================================================================================== jaula de seguridad
CG_POST = 0.0508             # PTR de 2" × 2" cal. 11
CG_WIRE = 0.001715           # radio del alambre cal. 10 (Ø 3,43 mm)
CG_MESH = 0.0508             # malla soldada de 2 × 2"
CG_A, CG_AT = 0.0318, 0.0023  # ángulo rolado de 1-1/4" × 1-1/4" cal. 13
CG_Y0 = -0.0064              # cara frontal del ala del panel (el ala trasera queda al ras de la cara interior del poste)
CG_GAP = 0.0064              # holgura poste-panel (la ocupa la oreja de 1/4" soldada al poste)


def _cg_angle_prof():
    """Perfil del ángulo rolado del marco (px hacia el centro del panel, py hacia el interior de la jaula): talón con radio
    de doblez y cantos de las alas redondeados."""
    a, t = CG_A, CG_AT
    cl = _fillet2d([(a - t / 2, t / 2), (t / 2, t / 2), (t / 2, a - t / 2)], 0.0028, 4)
    Nn = _normals2d(cl)
    A = cl + Nn * t / 2
    B = cl - Nn * t / 2
    out = [tuple(q) for q in A]
    for k in range(1, 4):                                                 # canto redondo del ala vertical
        g = PI * k / 4
        c = cl[-1]
        T = (cl[-1] - cl[-2]) / np.linalg.norm(cl[-1] - cl[-2])
        out.append(tuple(c + Nn[-1] * t / 2 * math.cos(g) + T * t / 2 * math.sin(g)))
    out += [tuple(q) for q in B[::-1]]
    for k in range(1, 4):                                                 # canto redondo del ala en el plano
        g = PI * k / 4
        c = cl[0]
        T = (cl[0] - cl[1]) / np.linalg.norm(cl[0] - cl[1])
        out.append(tuple(c - Nn[0] * t / 2 * math.cos(g) + T * t / 2 * math.sin(g)))
    return out


def _cg_panel(mb, M, w, h, mesh=True, stiff=True, mat="steel"):
    """Panel de malla: marco de ángulo rolado de 1-1/4" con esquinas a inglete (ala en el plano al frente, ala de fondo hacia
    el interior), malla soldada de 2 × 2" de alambre redondo cal. 10 (verticales contra el ala, horizontales por detrás,
    traslapadas = punto de soldadura) y atiesador horizontal de canal de 1-1/2" × 3/4" soldado por dentro. Local: x de 0 a w,
    z de 0 a h, cara frontal del ala en y = CG_Y0 (frente hacia -Y)."""
    a, t = CG_A, CG_AT
    prof = [(px, py + CG_Y0) for (px, py) in _cg_angle_prof()]
    path = [(0, 0, 0), (w, 0, 0), (w, 0, h), (0, 0, h)]
    mb.sweep(prof, _miter_path([tuple(M @ Vector(p)) for p in path]), mat, closed_path=True, normal=tuple(M.to_3x3() @ Vector((0, 1, 0))))
    yv = CG_Y0 + t + CG_WIRE - 0.0002
    yh = yv + 2 * CG_WIRE - 0.0005
    if stiff:
        zs = h * 0.5
        ch = [(-0.019, 0.0), (0.019, 0.0), (0.019, 0.019), (0.0168, 0.019), (0.0168, 0.0022), (-0.0168, 0.0022), (-0.0168, 0.019),
              (-0.019, 0.019)]
        chf = _fillet_closed(ch, 0.0009, 2)
        y0 = yh + CG_WIRE - 0.0003
        sweep_frame(mb, [(u, v) for (u, v) in chf], [tuple(M @ Vector((t, y0, zs))), tuple(M @ Vector((w - t, y0, zs)))], mat,
                    up=tuple(M.to_3x3() @ Vector((0, 1, 0))))
        for xw in (t + 0.0012, w - t - 0.0012):
            _bead(mb, [tuple(M @ Vector((xw, y0 + 0.0015, zs - 0.017))), tuple(M @ Vector((xw, y0 + 0.0015, zs + 0.017)))], r=0.0018)
    if not mesh:
        return
    nx = max(1, int(round((w - 2 * a) / CG_MESH)))
    xs = [a + (w - 2 * a) * (i + 0.5) / nx for i in range(nx)]
    nz = max(1, int(round((h - 2 * a) / CG_MESH)))
    zs_ = [a + (h - 2 * a) * (j + 0.5) / nz for j in range(nz)]
    with mb.soft():
        for x in xs:
            mb.tube([tuple(M @ Vector((x, yv, 0.012))), tuple(M @ Vector((x, yv, h - 0.012)))], CG_WIRE, seg=12, mat="galvanized")
        for z in zs_:
            mb.tube([tuple(M @ Vector((0.012, yh, z))), tuple(M @ Vector((w - 0.012, yh, z)))], CG_WIRE, seg=12, mat="galvanized")


def _cg_post(mb, x, y, h, cap=True, seed=0):
    """Poste de PTR de 2" cal. 11 (radio de esquina real) sobre placa base de 5 × 5 × 1/4" soldada (cordón perimetral), dos
    anclas de cuña en diagonal y tapón de polietileno con domo."""
    rtube(mb, (x, y, RK_BP), (x, y, h), CG_POST, CG_POST, "steel", r=0.0045, up=(0, 1, 0))
    slab(mb, _T(x, y, 0.0), 0.127, 0.127, RK_BP, rc=0.008, re=0.0012, mat="steel", nc=3, ne=2)
    q = CG_POST / 2 + 0.001
    loop = [(x + px, y + py, RK_BP + 0.001) for (px, py) in rr_pts(2 * q, 2 * q, 0.0055, 3)]
    _bead(mb, loop, r=0.0021, closed=True, step=0.0026)
    for (dx, dy) in ((-0.044, -0.044), (0.044, 0.044)):
        _nv_anchor(mb, (x + dx, y + dy, RK_BP), proud=0.011)
    if cap:
        slab(mb, _T(x, y, h - 0.012), CG_POST + 0.003, CG_POST + 0.003, 0.016, rc=0.006, re=0.0035, mat="plastic", nc=3, ne=3,
             re0=0.0008)
    del seed


def _cg_clamp(mb, M, zc):
    """Unión panel-poste: oreja de placa de 1/4" soldada al costado del poste (cordones arriba y abajo) y tornillo hexagonal
    con rondana por el lado interior del ala del panel. M: marco local del panel (x = 0 en el canto del ala, junto al poste)."""
    slab(mb, M @ _T(-CG_GAP / 2 + 0.0001, 0.011, zc - 0.025), CG_GAP + 0.0004, 0.026, 0.05, rc=0.0012, re=0.0012, mat="steel", nc=1,
         ne=1)
    for (zz, sz) in ((zc - 0.025, -1), (zc + 0.025, 1)):
        _bead(mb, [tuple(M @ Vector((-CG_GAP + 0.0008, -0.0015, zz + sz * 0.0008))),
                   tuple(M @ Vector((-CG_GAP + 0.0008, 0.0235, zz + sz * 0.0008)))], r=0.0017)
    _nv_bolt_head(mb, M @ _T(CG_AT, 0.0125, zc) @ _Ry(90), d=0.0079)


def _cg_padlock(mb, M, seed=0):
    """Candado laminado de 51 mm: 7 láminas de acero con cantos redondeados, 4 remaches, cilindro de latón con bocallave al
    fondo y arco de acero de 3/8" con dobleces reales. M: origen en lo alto del eje del arco; cuelga hacia -Z, frente -Y."""
    R = 0.0168
    rs = 0.00475
    arc = [(R * math.cos(a), 0.0, -R + R * math.sin(a)) for a in np.linspace(0, PI, 15)]
    sh = [(R, 0.0, -0.052)] + arc + [(-R, 0.0, -0.052)]
    _tube(mb, [tuple(M @ Vector(p)) for p in sh], rs, seg=SEG, mat="steel")
    zt = -0.042
    for k in range(7):
        z1 = zt - k * 0.0071
        slab(mb, M @ _T(0, 0, z1 - 0.0071), 0.051, 0.026, 0.0071, rc=0.0065, re=0.0011, mat="steel", nc=3, ne=2)
    zb = zt - 7 * 0.0071
    _lathe(mb, [(0.0, 0.0), (0.0079, 0.0), (0.0079, 0.0008), (0.0072, 0.0012), (0.0, 0.0012)], M @ _T(0, 0, zb) @ _Rx(180), "brass",
           seg=SEG)
    slab(mb, M @ _T(0, 0, zb - 0.0013), 0.0016, 0.009, 0.0006, rc=0.0006, re=0.0002, mat="cable", nc=1, ne=1)
    for sx in (-1, 1):
        for z in (zt - 0.007, zb + 0.007):
            for sy in (-1, 1):
                _lathe(mb, [(0.0, 0.0), (0.0024, 0.0), (0.0018, 0.0008), (0.0, 0.0011)],
                       M @ _T(sx * 0.0195, sy * 0.013, z) @ _Rx(-90 * sy), "steel", seg=12)
    del seed


def security_cage(w=4.0, d=3.0, h=2.6, seed=0):
    """Jaula de malla de seguridad (partición tipo WireCrafters/Cogan): postes de PTR de 2" con placa base soldada y anclas,
    paneles de malla soldada de 2 × 2" cal. 10 (alambre redondo real) en marco de ángulo rolado de 1-1/4" con atiesador,
    2" libres al piso, orejas soldadas a los postes y tornillos por dentro; puerta abatible de 1,0 × 2,1 m con tres bisagras
    de barril soldadas, jaladera, portacandado de pasador con candado laminado, y panel de cabecera sobre la puerta. Huella
    de intento de saqueo (sutil): rayones brillantes de barreta en el poste y el marco junto al portacandado y la oreja del
    portacandado doblada hacia afuera. Origen: piso al centro; frente (puerta) hacia -Y; w en X, d en Y."""
    r = rng(seed)
    mb = MB()
    zp = 0.0508                                                          # 2" libres al piso
    hp = h - zp - 0.03
    off = CG_POST / 2 + CG_GAP
    dw, dh = 1.0, 2.1
    xd0 = -dw / 2 - 0.35                                                 # puerta un poco a la izquierda del centro
    xd1 = xd0 + dw

    def run(p0, p1, normal, door=None):
        """Tramo recto de postes y paneles entre p0 y p1."""
        p0, p1 = Vector((p0[0], p0[1], 0.0)), Vector((p1[0], p1[1], 0.0))
        L = (p1 - p0).length
        u = (p1 - p0).normalized()
        if door:
            a, b = door
            segs = [(0.0, a, "p"), (a, b, "door"), (b, L, "p")]
        else:
            segs = [(0.0, L, "p")]
        posts = set([0.0, L])
        out = []
        for (a, b, kind) in segs:
            if kind == "door":
                posts |= {a, b}
                out.append((a, b, kind))
                continue
            n = max(1, int(math.ceil((b - a) / 1.55)))
            for k in range(n):
                s0 = a + (b - a) * k / n
                s1 = a + (b - a) * (k + 1) / n
                posts |= {s0, s1}
                out.append((s0, s1, kind))
        for s in sorted(posts):
            if s > L - 1e-6:                                             # la esquina final la pone el tramo siguiente
                continue
            q = p0 + u * s
            _cg_post(mb, q.x, q.y, h)
        nrm = Vector(normal)
        Mrot = Matrix(((u.x, nrm.x, 0.0, 0.0), (u.y, nrm.y, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
        for (s0, s1, kind) in out:
            if kind == "door":
                continue
            q = p0 + u * (s0 + off)
            M = Matrix.Translation(q + Vector((0, 0, zp))) @ Mrot
            pw = s1 - s0 - 2 * off
            _cg_panel(mb, M, pw, hp)
            Mr = M @ _T(pw, 0, 0) @ Matrix.Scale(-1, 4, Vector((1, 0, 0)))
            for zz in (0.25, hp * 0.5 + 0.08, hp - 0.25):
                _cg_clamp(mb, M, zz)
                _cg_clamp(mb, Mr, zz)
        return Mrot, u, nrm

    x0, x1, y0, y1 = -w / 2, w / 2, -d / 2, d / 2
    door_s = (xd0 - x0, xd1 - x0)
    Mf, uf, nf = run((x0, y0), (x1, y0), (0, 1, 0), door=door_s)
    run((x1, y0), (x1, y1), (-1, 0, 0))
    run((x1, y1), (x0, y1), (0, -1, 0))
    run((x0, y1), (x0, y0), (1, 0, 0))
    # panel de cabecera sobre la puerta
    xa, xb = xd0 + off, xd1 - off
    zh0 = dh + 0.03
    Mh = Matrix.Translation((xa, y0, zh0)) @ Mf
    _cg_panel(mb, Mh, xb - xa, hp + zp - zh0, stiff=False)
    Mhr = Mh @ _T(xb - xa, 0, 0) @ Matrix.Scale(-1, 4, Vector((1, 0, 0)))
    for zz in (0.08, hp + zp - zh0 - 0.08):
        _cg_clamp(mb, Mh, zz)
        _cg_clamp(mb, Mhr, zz)
    # hoja de la puerta (cerrada): mismo marco de ángulo y malla; bisagras a la izquierda, portacandado a la derecha
    g = 0.012
    xa, xb = xd0 + CG_POST / 2 + g, xd1 - CG_POST / 2 - g
    za, zb = zp, dh
    Md = Matrix.Translation((xa, y0, za)) @ Mf
    dwid, dhei = xb - xa, zb - za
    _cg_panel(mb, Md, dwid, dhei, stiff=True)
    yfr = y0 + CG_Y0                                                     # plano frontal de postes/hoja (cara del ala)
    for zz in (0.22, dhei / 2, dhei - 0.22):                              # bisagras de barril soldadas (3/4", 2 nudillos)
        p = Vector((xd0 + CG_POST / 2 + g / 2, yfr - 0.0125, za + zz))
        for (z0, z1) in ((-0.05, -0.0015), (0.0015, 0.05)):
            _lathe(mb, [(0.0, z0), (0.0085, z0), (0.0095, z0 + 0.0012), (0.0095, z1 - 0.0012), (0.0085, z1), (0.0, z1)],
                   _T(p.x, p.y, p.z), "steel", seg=SEG)
        _lathe(mb, [(0.0, 0.05), (0.0058, 0.05), (0.0058, 0.0525), (0.0045, 0.0545), (0.0, 0.0552)], _T(p.x, p.y, p.z), "steel", seg=SEG)
        _lathe(mb, [(0.0, -0.0525), (0.0042, -0.0525), (0.0042, -0.05), (0.0, -0.05)], _T(p.x, p.y, p.z), "steel", seg=SEG)
        yp_ = y0 - CG_POST / 2
        for (sx, z0, z1, yl_) in ((-1, -0.048, -0.004, yp_ - 0.0025), (1, 0.004, 0.048, yfr - 0.0025)):   # hojas soldadas
            xe = p.x + sx * 0.03
            slab(mb, _T((p.x + xe) / 2, yl_, p.z + z0), 0.03, 0.005, z1 - z0, rc=0.0015, re=0.0012, mat="steel", nc=1, ne=1)
            _bead(mb, [(xe + sx * 0.0006, yl_ - 0.0012, p.z + z0 + 0.003), (xe + sx * 0.0006, yl_ - 0.0012, p.z + z1 - 0.003)],
                  r=0.0016)
    # jaladera de redondo de 3/4" con placas soldadas
    hx = xb - 0.016
    zl = za + 1.05
    hp_ = [(hx, yfr, zl - 0.06), (hx, yfr - 0.05, zl - 0.06), (hx, yfr - 0.05, zl - 0.24), (hx, yfr, zl - 0.24)]
    _tube(mb, fillet(hp_, 0.018, 6), 0.0095, seg=SEG, mat="steel")
    for zz in (zl - 0.06, zl - 0.24):
        _bead(mb, [(hx + 0.0105 * math.cos(a_), yfr - 0.0008, zz + 0.0105 * math.sin(a_)) for a_ in np.linspace(0, 2 * PI, 25)[:-1]],
              r=0.0016, closed=True)
    # portacandado: separador y base remachada en el larguero de la hoja, barril, oreja ranurada (doblada por la barreta)
    # que asienta sobre la cara del poste, grapa de redondo soldada al poste y candado laminado colgando de la grapa
    xpost = xd1
    yp = y0 - CG_POST / 2                                                 # cara frontal del poste
    ph = xb - 0.004
    slab(mb, _T(xb - 0.017, yfr, zl - 0.035) @ _Rx(90) @ _T(0, 0.035, 0), 0.026, 0.07, 0.0145, rc=0.002, re=0.0012, mat="steel",
         nc=2, ne=1)
    yb0 = yfr - 0.0145
    slab(mb, _T(ph - 0.03, yb0, zl) @ _Rx(90), 0.06, 0.07, 0.004, rc=0.006, re=0.0012, mat="steel", nc=3, ne=2)
    for sx in (-1, 1):                                                    # remaches de la base
        for sz in (-1, 1):
            _lathe(mb, [(0.0, 0.0), (0.0042, 0.0), (0.0036, 0.0012), (0.002, 0.0021), (0.0, 0.0024)],
                   _T(ph - 0.03 + sx * 0.02, yb0 - 0.0039, zl + sz * 0.025) @ _Rx(90), "steel", seg=SEG)
    xbar = ph - 0.006
    _cyl(mb, (xbar, yp - 0.002, zl - 0.03), (xbar, yp - 0.002, zl + 0.03), 0.0062, "steel", seg=SEG, caps=False)
    for zz in (zl - 0.03, zl + 0.03):
        _lathe(mb, [(0.0, 0.0), (0.0062, 0.0), (0.0055, 0.0012), (0.0, 0.0016)], _T(xbar, yp - 0.002, zz) @ (_Rx(180) if zz < zl else Matrix()),
               "steel", seg=SEG)
    bend = 7.0 + float(r.uniform(-2, 2))                                  # oreja doblada hacia afuera (saqueo)
    Le = xpost + 0.022 - xbar
    Mh2 = _T(xbar, yp - 0.002, zl) @ _Rz(-bend)
    holed(mb, Mh2 @ _T(Le / 2, 0.0023, 0.0) @ _Rx(90), (0.0, 0.0, Le / 2, 0.019, 0.006),
          (xpost - xbar - Le / 2, 0.0, 0.0175, 0.0058, 0.0055), 0.0035, re_o=0.001, re_i=0.0008, n=56, mat="steel", ne=2)
    st = [(xpost - 0.012, yp + 0.001, zl), (xpost - 0.012, yp - 0.028, zl), (xpost + 0.012, yp - 0.028, zl), (xpost + 0.012, yp + 0.001, zl)]
    _tube(mb, fillet(st, 0.007, 5), 0.0048, seg=SEG, mat="steel")                         # grapa de redondo de 3/8"
    for xs_ in (xpost - 0.012, xpost + 0.012):
        _bead(mb, [(xs_ + 0.0062 * math.cos(a_), yp - 0.0005, zl + 0.0062 * math.sin(a_)) for a_ in np.linspace(0, 2 * PI, 21)[:-1]],
              r=0.0015, closed=True)
    _cg_padlock(mb, _T(xpost, yp - 0.028, zl + 0.0048 + 0.00475 - 0.0004) @ _Rz(90), seed=seed)
    for k in range(6):                                                    # rayones de barreta (acero brillante)
        a = float(r.uniform(-40, 40))
        on_post = k % 2 == 0
        cx = (xpost - 0.006 + float(r.uniform(-0.01, 0.01))) if on_post else (xb - 0.016 + float(r.uniform(-0.005, 0.005)))
        cz = zl + (1 if k % 4 < 2 else -1) * float(r.uniform(0.045, 0.11))
        ln = float(r.uniform(0.012, 0.03)) if on_post else float(r.uniform(0.01, 0.02))
        yy = (yp + 0.0002) if on_post else (yfr + 0.0002)
        Ms = _T(cx, yy, cz) @ _Ry(90 + a * 0.6) @ _Rx(90)
        slab(mb, Ms, ln, 0.0012, 0.0006, rc=0.0005, re=0.0002, mat="galvanized", nc=1, ne=1)
    return mb

# ======================================================================================================== montacargas
FL_YF, FL_YR = -0.55, 0.76         # ejes delantero (tracción) y trasero (dirección): distancia entre ejes 1,31 m
FL_RF, FL_WF = 0.2667, 0.178       # llanta de tracción 21 × 7 × 15
FL_RR, FL_WR = 0.2032, 0.152       # llanta de dirección 16 × 6 × 10-1/2
FL_YM = -0.89                      # eje de los rieles del mástil


def _off2(P, d):
    """Desplaza un polígono cerrado 2D hacia DENTRO d (por normales de vértice)."""
    P = np.asarray(P, float)
    Nn = _normals2d(np.vstack([P[-1:], P, P[:1]]))[1:-1]
    if 0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1]) < 0:
        Nn = -Nn
    return P + Nn * d


def _fl_xloft(mb, P, half, re, mat, n=4, x0=0.0, rmin=None):
    """Sólido de perfil lateral P [(y, z)] (cerrado) extruido a lo ancho en X (x0 ± half) con TODAS las aristas laterales
    redondeadas (radio re, n segmentos): lámina embutida, fundición, cofres."""
    P = np.asarray(P, float)
    loops = []
    for side in (-1, 1):
        rng_ = range(n + 1) if side < 0 else range(n, -1, -1)
        for j in rng_:
            ph = PI / 2 * j / n
            x = x0 + side * (half - re + re * math.cos(ph))
            Q = _off2(P, re - re * math.sin(ph))
            loops.append([(x, y, z) for (y, z) in Q])
    skin(mb, loops, mat)


def _rloft(mb, M, st, mat, n=3, cap0=True, cap1=True):
    """Sólido por estaciones de rectángulos redondeados [(z, ancho, fondo, cy, radio)] en Z local."""
    loops = [[(x, cy + y, z) for (x, y) in rr_pts(wd, dp, rc, n)] for (z, wd, dp, cy, rc) in st]
    return skin(mb, loops, mat, M, cap0=cap0, cap1=cap1)


def _fl_wheel(mb, M, R, w, rim_r, n_lugs=8):
    """Rueda de llanta sólida prensada (cushion) con dibujo de tracción: tacos alternados desde cada hombro (ranuras reales
    en V), hombros redondeados, banda de acero prensada visible, disco con birlos y tuercas, y tapón del cubo (eje Z local =
    eje de la rueda; cara exterior hacia +Z)."""
    from kit.clinic_servicios import lathe as slathe
    nl = 22 if R > 0.25 else 18
    seg = nl * 6
    pitch = 2 * PI / nl

    def rmod(i, a, rr, z):
        if rr < R - 0.0005:
            return rr
        ph = (a / pitch) % 1.0
        if z < -0.004 and ph < 0.30:
            return rr - 0.009 * (1.0 if z < -w / 2 + 0.03 else 0.7)
        if z > 0.004 and 0.5 <= ph < 0.80:
            return rr - 0.009 * (1.0 if z > w / 2 - 0.03 else 0.7)
        return rr
    prof = [(rim_r + 0.004, -w / 2), (R - 0.016, -w / 2), (R - 0.006, -w / 2 + 0.004), (R - 0.0012, -w / 2 + 0.011), (R, -w / 2 + 0.02),
            (R, -w / 4), (R, -0.006), (R, 0.0), (R, 0.006), (R, w / 4), (R, w / 2 - 0.02), (R - 0.0012, w / 2 - 0.011),
            (R - 0.006, w / 2 - 0.004), (R - 0.016, w / 2), (rim_r + 0.004, w / 2)]
    slathe(mb, prof, seg=seg, mat="rubber", M=M, rmod=rmod, caps=False)
    # banda de acero prensada (asoma 4 mm en ambos costados) y disco
    _lathe(mb, [(rim_r - 0.012, -w / 2 - 0.004), (rim_r + 0.006, -w / 2 - 0.004), (rim_r + 0.0075, -w / 2 - 0.0025),
                (rim_r + 0.0075, w / 2 + 0.0025), (rim_r + 0.006, w / 2 + 0.004), (rim_r - 0.012, w / 2 + 0.004)], M, "steel", seg=72,
           closed=True)
    zc = w / 2 - 0.02
    disc = [(rim_r - 0.012, w / 2 + 0.004), (rim_r - 0.02, zc + 0.006), (rim_r * 0.62, zc - 0.004), (rim_r * 0.52, zc - 0.004),
            (rim_r * 0.44, zc + 0.002), (rim_r * 0.3, zc + 0.002), (rim_r * 0.3, zc + 0.012), (rim_r * 0.24, zc + 0.022),
            (0.0, zc + 0.024)]
    _lathe(mb, disc, M, "steel", seg=48)
    pcd = rim_r * 0.37
    for k in range(n_lugs):
        a = 2 * PI * (k + 0.5) / n_lugs
        Ml = M @ _T(pcd * math.cos(a), pcd * math.sin(a), zc + 0.0015)
        _nv_nut(mb, Ml, 0.022, 0.016, "steel")
        _nv_thread(mb, Ml @ _T(0, 0, 0.014), 0.014, 0.012, 0.0016, "steel")
    for k in range(6):                                                    # barrenos de aligeramiento del disco
        a = 2 * PI * k / 6
        _lathe(mb, [(0.0, 0.0), (0.016, 0.0), (0.014, 0.0012), (0.0, 0.0012)],
               M @ _T(rim_r * 0.57 * math.cos(a), rim_r * 0.57 * math.sin(a), zc - 0.0035), "cable", seg=SEG)


def _leaf_chain(mb, p0, p1, side, pitch=0.015875):
    """Cadena de hojas BL534 (paso 5/8", entrelazado 2 × 3): placas en estadio de 2 mm alternadas por paso y pernos
    remachados con cabeza abombada. p0 -> p1 recta; side = eje de los pernos."""
    p0, p1 = Vector(p0), Vector(p1)
    L = (p1 - p0).length
    u = (p1 - p0).normalized()
    sd = Vector(side).normalized()
    n = int(L / pitch)
    w = sd.cross(u).normalized()
    Mbase = Matrix(((u.x, w.x, sd.x, 0), (u.y, w.y, sd.y, 0), (u.z, w.z, sd.z, 0), (0, 0, 0, 1)))
    tp = 0.0021
    for k in range(n):
        c = p0 + u * (pitch * (k + 0.5))
        offs = (-2, 0, 2) if k % 2 == 0 else (-1, 1)
        for o in offs:
            M = Matrix.Translation(c + sd * (o * tp - tp / 2)) @ Mbase
            slab(mb, M, pitch + 0.0135, 0.0135, tp - 0.0001, rc=0.0067, re=0.0004, mat="steel", nc=3, ne=1)
    for k in range(n + 1):
        c = p0 + u * (pitch * k)
        for sg in (-1, 1):
            Mp = _frame_z(c + sd * sg * 2.5 * tp, sd * sg)
            _lathe(mb, [(0.0, -0.0003), (0.0033, -0.0003), (0.0031, 0.0004), (0.0022, 0.0011), (0.0, 0.0013)], Mp, "steel", seg=12)


def _fl_cyl(mb, a, b, rb, rr, stroke_frac=0.55, mat="gunmetal", seg=SEG):
    """Cilindro hidráulico de a (base, ojo) a b (vástago): tubo con tapas torneadas, glándula, vástago cromado, ojos con
    rótula y perno con chaveta."""
    a, b = Vector(a), Vector(b)
    u = (b - a).normalized()
    L = (b - a).length
    Lb = L * stroke_frac
    M = _frame_z(a, u)
    _lathe(mb, [(0.0, 0.03), (rb * 0.92, 0.03), (rb, 0.036), (rb, Lb - 0.03), (rb * 1.06, Lb - 0.026), (rb * 1.06, Lb - 0.004),
                (rr * 1.25, Lb), (rr * 1.25, Lb + 0.006), (rr, Lb + 0.008)], M, mat, seg=seg)
    _lathe(mb, [(rr, Lb), (rr, L - 0.03), (0.0, L - 0.03)], M, "steel", seg=seg)
    for (p, d) in ((a, u), (b, -u)):                                       # ojos con perno
        Me = _frame_z(p, d)
        _lathe(mb, [(0.0, 0.0), (rr * 0.9, 0.0), (rr * 0.9, 0.032), (0.0, 0.034)], Me, mat if p is a else "steel", seg=seg)
        ax = Vector((1, 0, 0))
        _cyl(mb, tuple(p - ax * 0.026), tuple(p + ax * 0.026), 0.024, mat if p is a else "steel", seg=seg)
        _cyl(mb, tuple(p - ax * 0.045), tuple(p + ax * 0.045), 0.0095, "steel", seg=SEG)
        for sg in (-1, 1):
            _nv_washer(mb, _frame_z(p + ax * sg * 0.045, ax * sg), 0.015, 0.0095, 0.002, "steel")
    return M, Lb


def _fl_hose(mb, pts, r=0.0095, bend=0.05):
    """Manguera hidráulica (16 lados) con casquillos prensados y conexiones hexagonales en ambos extremos."""
    P = fillet(pts, bend, 8)
    _tube(mb, P, r, seg=16, mat="rubber")
    for (p, q) in ((P[0], P[1]), (P[-1], P[-2])):
        p, q = Vector(p), Vector(q)
        d = (q - p).normalized()
        M = _frame_z(p, d)
        _lathe(mb, [(0.0, -0.012), (r * 1.25, -0.012), (r * 1.3, 0.0), (r * 1.3, 0.04), (r * 1.08, 0.046)], M, "steel", seg=SEG)
        for k in range(3):
            _lathe(mb, [(r * 1.3, 0.008 + k * 0.011), (r * 1.36, 0.011 + k * 0.011), (r * 1.3, 0.014 + k * 0.011)], M, "steel", seg=SEG)
        _nv_nut(mb, M @ _T(0, 0, -0.03), r * 2.4, 0.018, "steel", hole=r * 0.6)


def _fl_light(mb, M, w=0.11, h=0.08, d=0.06, mat="cable"):
    """Faro de trabajo LED rectangular: cuerpo con aletas, bisel, mica y soporte en U con perilla (frente +Z local)."""
    slab(mb, M @ _T(0, 0, -d), w, h, d, rc=0.012, re=0.006, mat=mat, nc=3, ne=2)
    for k in range(5):
        x = -w / 2 + 0.014 + (w - 0.028) * k / 4
        slab(mb, M @ _T(x, 0, -d - 0.012), 0.004, h * 0.86, 0.0125, rc=0.0015, re=0.0012, mat=mat, nc=1, ne=1)
    rrframe(mb, M, (0, 0, w, h, 0.012), (0, 0, w - 0.014, h - 0.014, 0.006), 0.004, re_o=0.002, re_i=0.0015, mat=mat)
    slab(mb, M @ _T(0, 0, -0.001), w - 0.012, h - 0.012, 0.0035, rc=0.0055, re=0.0012, mat="glass", nc=3, ne=1)
    for k in range(3):
        _lathe(mb, [(0.0, 0.0), (0.011, 0.0), (0.009, 0.004), (0.0, 0.005)], M @ _T(-w / 3 + k * w / 3, 0.0, -0.0035), "aluminium", seg=SEG)


def forklift(seed=0):
    """Montacargas de contrapeso a gas LP de 5 000 lb (llantas sólidas), proporciones de un Yale GC050VX: ancho 1,07 m,
    protector a 2,13 m, entre ejes 1,31 m, largo a la cara de la horquilla 2,24 m. Construcción real: chasis soldado,
    contrapeso fundido de perfil redondeado con cajas de rueda, cofre del motor con rejillas, tablero con pantalla, columna
    con fuelle, volante de 3 rayos con perilla, 3 palancas hidráulicas con fuelles, pedales de hule, piso con tapete,
    escalones antiderrapantes, salpicaderas; protector superior de PTR doblado con rejilla soldada, agarradera, faros,
    torreta y espejo; tanque de gas LP de 33 lb con collar, válvula, manómetro, manguera y cuna abatible con cinchos;
    mástil de 2 etapas (canales exteriores, rieles interiores en I, travesaños, rodillos, 2 cilindros de levante, poleas y
    cadenas de hojas reales), carro ITA clase II con respaldo de carga y horquillas de gancho con talón doblado y punta
    cónica, 2 cilindros de inclinación, mangueras hidráulicas de 16 lados, llantas con dibujo y rines con birlos, placa de
    capacidad. Origen: piso al centro del chasis; horquillas hacia -Y."""
    r = rng(seed)
    mb = MB()
    from kit.fonts import text_font
    yfa, yra, Rf, wf, Rr, wr = FL_YF, FL_YR, FL_RF, FL_WF, FL_RR, FL_WR
    Wt = 1.07
    # ---------------- ruedas, eje de tracción y eje de dirección
    xf = Wt / 2 - wf / 2
    xr = 0.40
    for sx in (-1, 1):
        _fl_wheel(mb, _T(sx * xf, yfa, Rf) @ _Ry(90 * sx), Rf, wf, 0.1905, n_lugs=10)
        _fl_wheel(mb, _T(sx * xr, yra, Rr) @ _Ry(90 * sx), Rr, wr, 0.1334, n_lugs=6)
        _lathe(mb, [(0.0, 0.0), (0.13, 0.0), (0.13, 0.02), (0.095, 0.03), (0.095, 0.06), (0.0, 0.06)],
               _T(sx * (xf - wf / 2 - 0.0), yfa, Rf) @ _Ry(-90 * sx), "gunmetal", seg=SEG)                  # cubo planetario
        _lathe(mb, [(0.0, 0.0), (0.06, 0.0), (0.06, 0.07), (0.045, 0.085), (0.0, 0.085)],
               _T(sx * (xr - wr / 2), yra, Rr) @ _Ry(-90 * sx), "gunmetal", seg=SEG)                         # muñón
    _cyl(mb, (-0.36, yfa, Rf), (0.36, yfa, Rf), 0.085, "gunmetal", seg=SEG)                                 # carcasa del eje
    _lathe(mb, [(0.0, -0.13), (0.11, -0.12), (0.15, -0.06), (0.15, 0.04), (0.12, 0.1), (0.0, 0.12)], _T(0.0, yfa + 0.02, Rf) @ _Rx(90),
           "gunmetal", seg=SEG)                                                                              # diferencial
    rtube(mb, (-0.33, yra, Rr), (0.33, yra, Rr), 0.12, 0.1, "gunmetal", r=0.012, up=(0, 0, 1))              # eje de dirección
    for sx in (-1, 1):
        _cyl(mb, (sx * 0.1, yra - 0.08, Rr + 0.02), (sx * 0.3, yra - 0.07, Rr + 0.02), 0.012, "steel", seg=SEG)  # barras de liga
    # ---------------- chasis (acero negro), carrocería (amarillo)
    _fl_xloft(mb, [(-0.72, 0.18), (-0.62, 0.12), (0.47, 0.12), (0.47, 0.53), (-0.66, 0.53), (-0.72, 0.45)], 0.30, 0.012, "gunmetal", n=3)
    _fl_xloft(mb, [(-0.27, 0.22), (0.425, 0.22), (0.425, 0.535), (-0.05, 0.535), (-0.05, 0.345), (-0.27, 0.345)], 0.52, 0.03,
              "paint_yellow", n=4)                                                                           # costados y escalones
    _fl_xloft(mb, [(-0.37, 0.34), (-0.05, 0.34), (-0.05, 0.545), (-0.37, 0.545)], 0.345, 0.008, "gunmetal", n=2)  # caja del piso
    cowl = [(-0.62, 0.53), (-0.36, 0.53), (-0.36, 0.90), (-0.39, 0.985), (-0.47, 1.03), (-0.58, 1.015), (-0.64, 0.86), (-0.645, 0.56)]
    _fl_xloft(mb, cowl, 0.34, 0.035, "paint_yellow", n=4)
    hood = [(-0.055, 0.535), (0.415, 0.535), (0.415, 0.975), (0.33, 0.988), (0.0, 0.982), (-0.045, 0.962), (-0.062, 0.91)]
    _fl_xloft(mb, hood, 0.505, 0.04, "paint_yellow", n=4)
    ac = math.asin((0.13 - Rr) / 0.25)
    arch = [(yra + 0.25 * math.cos(a), Rr + 0.25 * math.sin(a)) for a in np.linspace(ac, PI - ac, 17)]
    cw = [(1.215, 0.30), (1.215, 0.43), (1.207, 0.462), (1.192, 0.478), (1.186, 0.50), (1.186, 0.80), (1.172, 0.93), (1.13, 1.02),
          (1.05, 1.06), (0.80, 1.07), (0.56, 1.05), (0.425, 0.995), (0.42, 0.95), (0.42, 0.15), (0.43, 0.13)] + arch[::-1] + \
        [(1.04, 0.13), (1.15, 0.145), (1.2, 0.2), (1.212, 0.25)]
    _fl_xloft(mb, cw, 0.52, 0.045, "paint_yellow", n=5)                                                     # contrapeso fundido
    # salpicaderas de lámina sobre las llantas de tracción (canto enrollado)
    for sx in (-1, 1):
        fp = [(sx * xf, yfa + 0.305 * math.cos(a), Rf + 0.305 * math.sin(a)) for a in np.linspace(math.radians(14), math.radians(166), 25)]
        sweep_frame(mb, rr_profile(0.006, wf + 0.01, 0.0029, n=3), fp, "paint_yellow", up=(1, 0, 0))
        _tube(mb, [(p[0] + sx * (wf / 2 + 0.005), p[1], p[2]) for p in fp], 0.0055, seg=SEG_T + 2, mat="paint_yellow")
    # piso: placa antiderrapante y tapete de hule con costillas
    slab(mb, _T(0, -0.205, 0.545), 0.66, 0.29, 0.006, rc=0.01, re=0.002, mat="steel", nc=2, ne=1)
    slab(mb, _T(0, -0.205, 0.551), 0.6, 0.26, 0.008, rc=0.02, re=0.003, mat="rubber", nc=3, ne=2)
    for k in range(9):
        y = -0.32 + k * 0.028
        slab(mb, _T(0, y, 0.5585), 0.56, 0.008, 0.004, rc=0.003, re=0.0018, mat="rubber", nc=2, ne=1, re0=0.0)
    # escalones: placa con bordes doblados y botones antiderrapantes perforados
    for sx in (-1, 1):
        xs0 = sx * 0.435
        slab(mb, _T(xs0, -0.16, 0.345), 0.17, 0.215, 0.005, rc=0.008, re=0.002, mat="steel", nc=2, ne=1)
        for i in range(5):
            for j in range(7):
                if (i + j) % 2:
                    continue
                p = (xs0 - 0.064 + i * 0.032, -0.25 + j * 0.03, 0.35)
                _lathe(mb, [(0.0034, 0.0), (0.0075, 0.0), (0.0062, 0.0022), (0.0034, 0.0026)], _T(*p), "steel", seg=16, closed=True)
                _lathe(mb, [(0.0, 0.0002), (0.0035, 0.0002), (0.0, 0.0003)], _T(*p), "cable", seg=16)
    # rejillas del cofre (persianas reales) y chapa
    for sx in (-1, 1):
        Mg = _T(sx * 0.5048, 0.18, 0.75) @ _Rz(90 * sx) @ _Rx(90)
        rrframe(mb, Mg, (0, 0, 0.3, 0.16, 0.012), (0, 0, 0.27, 0.13, 0.006), 0.008, re_o=0.002, re_i=0.0015, mat="cable")
        slab(mb, Mg, 0.272, 0.132, 0.0015, rc=0.006, re=0.0005, mat="cable", nc=2, ne=1)
        for k in range(8):
            z = -0.055 + k * 0.0157
            sweep_frame(mb, [(-0.0011, -0.0065), (0.0011, -0.0065), (0.0011, 0.0065), (-0.0011, 0.0065)],
                        [tuple(Mg @ Vector((-0.1355, z, 0.0062))), tuple(Mg @ Vector((0.1355, z, 0.0062)))], "cable",
                        up=tuple(Mg.to_3x3() @ Vector((0, 0.5, -0.866))))
    slab(mb, _T(0, -0.0645, 0.92) @ _Rx(90), 0.12, 0.03, 0.006, rc=0.01, re=0.003, mat="cable", nc=3, ne=2)      # jaladera del cofre
    # contrapeso: calaveras, enganche, ojos de izaje, alarma de reversa
    for sx in (-1, 1):
        Ml = _T(sx * 0.4, 1.181, 0.86) @ _Rx(-90)
        _lathe(mb, [(0.0, -0.004), (0.048, -0.004), (0.05, 0.0), (0.05, 0.012), (0.045, 0.016), (0.0, 0.016)], Ml, "cable", seg=SEG)
        _lathe(mb, [(0.0, 0.0), (0.042, 0.0), (0.042, 0.004), (0.036, 0.011), (0.0, 0.013)], Ml @ _T(0, 0, 0.016), "sign_red", seg=SEG)
        _lathe(mb, [(0.0, -0.004), (0.035, -0.004), (0.035, 0.008), (0.0, 0.008)], _T(sx * 0.38, 1.0, 1.06), "cable", seg=SEG)   # ojo
    slab(mb, _T(0, 1.212, 0.33) @ _Rx(-90) @ _T(0, 0, -0.004), 0.16, 0.1, 0.05, rc=0.02, re=0.01, mat="paint_yellow", nc=3, ne=2)
    _lathe(mb, [(0.0, 0.0), (0.016, 0.0), (0.016, 0.16), (0.013, 0.165), (0.0, 0.165)], _T(0, 1.237, 0.265), "steel", seg=SEG)
    _lathe(mb, [(0.0, 0.0), (0.026, 0.0), (0.026, 0.012), (0.02, 0.018), (0.0, 0.02)], _T(0, 1.237, 0.43), "steel", seg=SEG)
    with mb.soft():                                                       # cadenita del perno
        loop_tube(mb, [(0.026 + 0.01 * math.cos(a), 1.237, 0.44 + 0.006 * math.sin(a)) for a in np.linspace(0, 2 * PI, 17)[:-1]], 0.0015,
                  seg=12, mat="steel", normal=(0, 1, 0))
    slab(mb, _T(0.25, 1.10, 1.035), 0.09, 0.06, 0.05, rc=0.01, re=0.006, mat="cable", nc=3, ne=2)          # alarma de reversa
    for k in range(5):
        slab(mb, _T(0.25, 1.1296, 1.047 + k * 0.007) @ _Rx(-90), 0.07, 0.003, 0.0012, rc=0.0012, re=0.0004, mat="steel", nc=1, ne=1)
    # ---------------- tablero, columna, volante, palancas, pedales
    Md = _T(0, -0.54, 1.012) @ _Rx(-25)
    slab(mb, Md, 0.24, 0.11, 0.045, rc=0.015, re=0.008, mat="cable", nc=3, ne=2)                         # caja de la pantalla
    slab(mb, Md @ _T(0, 0.012, 0.0445), 0.15, 0.065, 0.003, rc=0.006, re=0.001, mat="glass", nc=2, ne=1)
    for k in range(4):
        _lathe(mb, [(0.0, 0.0), (0.006, 0.0), (0.0055, 0.003), (0.0, 0.0035)], Md @ _T(-0.075 + k * 0.05, -0.037, 0.0445), "plastic", seg=SEG)
    _lathe(mb, [(0.0, 0.0), (0.011, 0.0), (0.011, 0.006), (0.006, 0.01), (0.0, 0.01)], _T(0.12, -0.39, 0.95) @ _Rx(-80), "steel", seg=SEG)
    pc = Vector((0.0, -0.44, 1.0))
    pw = Vector((0.0, -0.27, 1.21))
    ax = (pw - pc).normalized()
    Mc = _frame_z(pc, ax)
    bell = [(0.06, 0.0)]
    for k in range(8):
        bell += [(0.058 - k * 0.003, 0.012 + k * 0.022), (0.046 - k * 0.003, 0.023 + k * 0.022)]
    _lathe(mb, bell + [(0.034, 0.2)], Mc, "rubber", seg=SEG)                                                  # fuelle
    _lathe(mb, [(0.034, 0.2), (0.038, 0.21), (0.038, 0.24), (0.03, 0.26)], Mc, "cable", seg=SEG)
    _cyl(mb, tuple(pc + ax * 0.25), tuple(pw - ax * 0.03), 0.022, "cable", seg=SEG)
    Mw = _frame_z(pw, ax)
    rim = [(0.165 + 0.0155 * math.cos(a), 0.0155 * math.sin(a)) for a in np.linspace(0, 2 * PI, 17)[:-1]]
    grips = lambda a: 1.0 - 0.006 * max(0.0, math.cos(36 * a)) ** 6                                       # noqa: E731
    revolve(mb, rim, "rubber", seg=96, M=Mw, closed=True, rmod=grips)
    _lathe(mb, [(0.0, -0.035), (0.05, -0.035), (0.055, -0.01), (0.052, 0.012), (0.04, 0.026), (0.0, 0.03)], Mw, "cable", seg=SEG)
    for k in range(3):
        a = PI / 2 + 2 * PI * k / 3
        p0 = Mw @ Vector((0.045 * math.cos(a), 0.045 * math.sin(a), -0.004))
        p1 = Mw @ Vector((0.158 * math.cos(a), 0.158 * math.sin(a), 0.0))
        sweep_frame(mb, rr_profile(0.012, 0.03, 0.0055, n=3), [tuple(p0), tuple(p0.lerp(p1, 0.5) + ax * -0.006), tuple(p1)], "cable",
                    up=tuple(ax), scale=lambda t_: (1.0, 1.0 - 0.3 * t_))
    pk = Mw @ Vector((0.165 * math.cos(-0.5), 0.165 * math.sin(-0.5), 0.0))
    _lathe(mb, [(0.0, 0.0), (0.012, 0.0), (0.012, 0.012), (0.018, 0.02), (0.019, 0.045), (0.015, 0.058), (0.0, 0.06)],
           _frame_z(pk, ax), "plastic", seg=SEG)
    # palanca de dirección (columna izquierda)
    _tube(mb, fillet([tuple(pc + ax * 0.24 + Vector((-0.03, 0, 0))), tuple(pc + ax * 0.24 + Vector((-0.12, 0.02, 0.01))),
                      tuple(pc + ax * 0.24 + Vector((-0.15, 0.05, 0.02)))], 0.02, 4), 0.006, seg=SEG_T + 2, mat="cable")
    for k in range(3):                                                    # palancas hidráulicas con fuelle y perilla
        x = 0.17 + k * 0.042
        b0 = Vector((x, -0.40, 0.965))
        _lathe(mb, [(0.0, 0.0), (0.018, 0.0), (0.016, 0.01), (0.019, 0.016), (0.014, 0.026), (0.016, 0.031), (0.009, 0.042),
                    (0.0, 0.043)], _T(*b0), "rubber", seg=SEG)
        p1 = b0 + Vector((0.0, 0.07, 0.2 - k * 0.01))
        _cyl(mb, tuple(b0), tuple(p1), 0.006, "steel", seg=SEG_T + 2)
        _lathe(mb, [(0.0, -0.004), (0.011, 0.0), (0.016, 0.018), (0.017, 0.032), (0.012, 0.044), (0.0, 0.046)],
               _frame_z(p1, p1 - b0), "cable", seg=SEG)
    for (x, ang, w_) in ((-0.13, 32, 0.14), (0.02, 32, 0.09), (0.15, 36, 0.08)):        # pedales: frenado, avance lento, acelerador
        Mp = _T(x, -0.33, 0.62) @ _Rx(ang)
        slab(mb, Mp, w_, 0.11, 0.012, rc=0.012, re=0.004, mat="steel", nc=2, ne=1)
        slab(mb, Mp @ _T(0, 0, 0.012), w_ - 0.01, 0.1, 0.006, rc=0.01, re=0.0025, mat="rubber", nc=2, ne=1)
        for k in range(5):
            slab(mb, Mp @ _T(0, -0.04 + k * 0.02, 0.0175), w_ - 0.02, 0.005, 0.0025, rc=0.002, re=0.001, mat="rubber", nc=1, ne=1, re0=0.0)
        _cyl(mb, tuple(Mp @ Vector((0, 0.04, -0.002))), (x, -0.36, 0.565), 0.009, "steel", seg=SEG)
    # placa de capacidad (aluminio remachado, cara al operador)
    Mpl = _T(-0.16, -0.3598, 0.82) @ _Rx(-90) @ _Rz(180)
    slab(mb, Mpl, 0.15, 0.1, 0.0012, rc=0.004, re=0.0003, mat="aluminium", nc=2, ne=1)
    zz = 0.034
    for (s_, sz, b) in (("CAPACITY", 0.011, True), ("5000 LB  @  24 IN LOAD CENTER", 0.0058, True), ("MAX FORK HEIGHT 130 IN", 0.0058, False),
                        ("TRUCK WEIGHT 8650 LB   LPG", 0.0058, False), ("OPERATOR MUST BE TRAINED", 0.0052, False)):
        text_font(mb, s_, sz, 0.0003, "cable", Mpl @ _T(0, zz, 0.0012), font="sign", bold=b, res=2)
        zz -= sz * 1.9
    for sx in (-1, 1):
        for sz_ in (-1, 1):
            _lathe(mb, [(0.0, 0.0), (0.0025, 0.0), (0.0018, 0.0009), (0.0, 0.0012)], Mpl @ _T(sx * 0.066, sz_ * 0.041, 0.0011), "steel", seg=12)
    # ---------------- asiento de suspensión
    from kit.clinic import cushion
    slab(mb, _T(0, 0.14, 0.98), 0.4, 0.38, 0.05, rc=0.02, re=0.008, mat="cable", nc=3, ne=2)                 # base de suspensión
    cushion(mb, _T(0, 0.12, 1.03), 0.48, 0.46, 0.085, mat="rubber", r=0.03, crown=0.012, piping=False, seg=(28, 24))
    Mb = _T(0, 0.37, 1.07) @ _Rx(-14)
    Mbk = Mb @ _Rx(90) @ _T(0, 0.23, 0)
    cushion(mb, Mbk, 0.47, 0.46, 0.08, mat="rubber", r=0.03, crown=0.012, piping=False, seg=(28, 24))
    with mb.soft():
        for (Mx, w_, d_, h_) in ((_T(0, 0.12, 1.03), 0.48, 0.46, 0.085), (Mbk, 0.47, 0.46, 0.08)):
            pts = [(x, y, h_ - 0.012) for (x, y) in rr_pts(w_ - 0.004, d_ - 0.004, 0.03, 5)]
            pts.append(pts[0])
            mb.tube([tuple(Mx @ Vector(p)) for p in pts], 0.0032, seg=12, mat="rubber")
            pts = [(x, y, h_ * 0.42) for (x, y) in rr_pts(w_ + 0.001, d_ + 0.001, 0.03, 5)]
            pts.append(pts[0])
            mb.tube([tuple(Mx @ Vector(p)) for p in pts], 0.0024, seg=12, mat="rubber")
    for sx in (-1, 1):                                                    # topes de cadera
        Mh = Mb @ _T(sx * 0.255, -0.07, 0.03) @ _Rz(sx * 8)
        slab(mb, Mh @ _Ry(-sx * 10), 0.05, 0.2, 0.17, rc=0.022, re=0.02, mat="rubber", nc=3, ne=3)
    slab(mb, Mb @ _T(0, -0.035, 0.445), 0.3, 0.07, 0.04, rc=0.015, re=0.015, mat="rubber", nc=3, ne=2)        # cabecera
    belt = [(-0.25, 0.3, 1.06), (-0.22, 0.07, 1.125), (-0.05, -0.02, 1.13), (0.12, -0.03, 1.125), (0.24, 0.16, 1.07)]
    with mb.soft():
        sweep_frame(mb, rr_profile(0.0025, 0.048, 0.001, n=1), fillet(belt, 0.06, 6), "paint_yellow", up=(0, 0, 1))
    slab(mb, _T(0.2, 0.06, 1.1) @ _Rz(40), 0.07, 0.035, 0.024, rc=0.008, re=0.006, mat="cable", nc=3, ne=2)    # hebilla
    _lathe(mb, [(0.0, 0.0), (0.03, 0.0), (0.03, 0.07), (0.0, 0.07)], _T(-0.26, 0.32, 1.02) @ _Ry(90) @ _T(0, 0, -0.035), "cable", seg=SEG)
    # ---------------- protector superior: dos tubos doblados de 60 × 50, travesaños, rejilla soldada
    zg = 2.095
    for sx in (-1, 1):
        x = sx * 0.47
        path = [(x, -0.40, 0.556), (x, -0.50, 1.45), (x, -0.50, zg), (x, 0.625, zg), (x, 0.625, 1.06)]
        sweep_frame(mb, rr_profile(0.06, 0.05, 0.007, n=4), fillet(path, 0.13, 10), "gunmetal", up=(1, 0, 0))
        _board(mb, x - 0.045, x + 0.045, -0.455, -0.345, 0.50, 0.551, "gunmetal", r=0.004)
        for (yb_, zb_) in ((-0.40, 0.55), (0.625, 1.052)):
            slab(mb, _T(x, yb_, zb_), 0.09, 0.11, 0.012, rc=0.008, re=0.002, mat="gunmetal", nc=2, ne=1)
            for (dx, dy) in ((-0.03, -0.042), (0.03, -0.042), (-0.03, 0.042), (0.03, 0.042)):
                _nv_bolt_head(mb, _T(x + dx, yb_ + dy, zb_ + 0.012), d=0.011, mat="steel")
            q = [(x + px, yb_ + py, zb_ + 0.0135) for (px, py) in rr_pts(0.052, 0.062, 0.008, 3)]
            _bead(mb, q, r=0.0025, closed=True, mat="gunmetal", step=0.003)
    for y in (-0.50, 0.625):
        rtube(mb, (-0.47, y, zg), (0.47, y, zg), 0.06, 0.05, "gunmetal", r=0.007, up=(0, 0, 1))
    for k in range(6):
        x = -0.35 + 0.14 * k
        rtube(mb, (x, -0.47, zg + 0.0), (x, 0.595, zg), 0.008, 0.045, "gunmetal", r=0.002, up=(0, 0, 1))
    for y in (-0.12, 0.25):
        rtube(mb, (-0.445, y, zg + 0.001), (0.445, y, zg + 0.001), 0.008, 0.043, "gunmetal", r=0.002, up=(0, 0, 1))
    # agarradera con forro de hule, espejo, faros, torreta
    gp = [(-0.445, -0.47, 1.0), (-0.41, -0.47, 1.0), (-0.41, -0.48, 1.42), (-0.445, -0.48, 1.42)]
    _tube(mb, fillet(gp, 0.025, 6), 0.0125, seg=SEG, mat="steel")
    _lathe(mb, [(0.0145, 0.0), (0.0165, 0.01), (0.0165, 0.35), (0.0145, 0.36)], _frame_z(Vector((-0.41, -0.4703, 1.03)), Vector((0, -0.01, 0.42))),
           "rubber", seg=SEG, closed=False)
    _tube(mb, fillet([(-0.495, -0.505, 1.62), (-0.56, -0.53, 1.66), (-0.6, -0.54, 1.7)], 0.03, 5), 0.009, seg=SEG_T + 2, mat="cable")
    Mm = _T(-0.62, -0.545, 1.72) @ _Rz(20) @ _Rx(90)
    slab(mb, Mm, 0.16, 0.11, 0.025, rc=0.03, re=0.01, mat="cable", nc=4, ne=2)
    slab(mb, Mm @ _T(0, 0, -0.002), 0.145, 0.095, 0.004, rc=0.024, re=0.0015, mat="glass", nc=4, ne=1)
    for sx in (-1, 1):
        _fl_light(mb, _T(sx * 0.47, -0.585, 1.98) @ _Rx(90) @ _Rx(-8))
    _fl_light(mb, _T(0.42, 0.66, 1.95) @ _Rx(-90) @ _Rz(180), w=0.09, h=0.07)
    _lathe(mb, [(0.0, 0.0), (0.06, 0.0), (0.06, 0.012), (0.052, 0.02), (0.05, 0.03)], _T(0.30, 0.625, zg + 0.025), "cable", seg=SEG)
    _lathe(mb, [(0.05, 0.03), (0.048, 0.1), (0.04, 0.125), (0.022, 0.138), (0.0, 0.141)], _T(0.30, 0.625, zg + 0.025), "plastic", seg=SEG)
    # ---------------- tanque de gas LP de 33 lb (Ø 12-1/4" × 27-1/2"), collar, válvulas y cuna abatible
    yt, zt = 0.885, 1.255
    Mt = _T(0, yt, zt) @ _Ry(90)
    Rt, hs = 0.1555, 0.272
    tank = []
    for k in range(10):
        t_ = PI / 2 * k / 9
        tank.append((Rt * math.sin(t_), -hs - 0.078 * math.cos(t_)))
    for k in range(9, -1, -1):
        t_ = PI / 2 * k / 9
        tank.append((Rt * math.sin(t_), hs + 0.078 * math.cos(t_)))
    _lathe(mb, tank, Mt, "aluminium", seg=48)
    _lathe(mb, [(0.112, -0.33), (0.118, -0.33), (0.118, -0.39), (0.112, -0.392)], Mt, "aluminium", seg=48, closed=True)  # aro de pie
    for (z0, z1, a0, a1) in ((0.31, 0.37, 0.0, 2 * PI), (0.37, 0.43, 0.25, PI - 0.25), (0.37, 0.43, PI + 0.6, 2 * PI - 0.6)):
        arc_solid(mb, 0.106, 0.11, z0, z1, a0, a1, 40 if a1 - a0 > 4 else 18, "aluminium", M=Mt)                # collar con asas
    _lathe(mb, [(0.0, 0.33), (0.022, 0.33), (0.022, 0.355), (0.016, 0.36), (0.016, 0.38), (0.0, 0.38)], Mt, "brass", seg=SEG)
    Mv = Mt @ _T(0, 0, 0.37)
    _lathe(mb, [(0.0, 0.0), (0.009, 0.0), (0.009, 0.03), (0.0, 0.03)], Mv, "steel", seg=SEG)
    revolve(mb, [(0.032 + 0.005 * math.cos(a), 0.034 + 0.005 * math.sin(a)) for a in np.linspace(0, 2 * PI, 13)[:-1]], "sign_red",
            seg=48, M=Mv, closed=True)                                                                       # volante de la válvula
    for k in range(4):
        a = 2 * PI * k / 4
        _cyl(mb, tuple(Mv @ Vector((0.008 * math.cos(a), 0.008 * math.sin(a), 0.034))), tuple(Mv @ Vector((0.031 * math.cos(a), 0.031 * math.sin(a), 0.034))),
             0.0035, "sign_red", seg=16)
    _lathe(mb, [(0.0, 0.0), (0.0095, 0.0), (0.0095, 0.012), (0.0, 0.014)], Mt @ _T(0.05, 0.03, 0.335) @ _Ry(30), "brass", seg=SEG)  # alivio
    Mg_ = Mt @ _T(-0.055, -0.02, 0.33) @ _Ry(-25)
    _lathe(mb, [(0.0, 0.0), (0.02, 0.0), (0.02, 0.012), (0.017, 0.014), (0.0, 0.014)], Mg_, "cable", seg=SEG)       # medidor
    _lathe(mb, [(0.0, 0.0), (0.017, 0.0), (0.0, 0.002)], Mg_ @ _T(0, 0, 0.012), "glass", seg=SEG)
    pv = Mt @ Vector((0.0, 0.025, 0.395))
    _fl_hose(mb, [tuple(pv), tuple(pv + Vector((0.05, -0.02, 0.0))), (0.42, 0.66, 1.06), (0.40, 0.42, 1.0)], r=0.008, bend=0.05)
    for sx in (-0.2, 0.2):                                                # cinchos con hebilla de palanca y cuna
        loop_ = [(sx, yt + 0.1585 * math.cos(a), zt + 0.1585 * math.sin(a)) for a in np.linspace(0, 2 * PI, 49)[:-1]]
        sweep_frame(mb, rr_profile(0.0025, 0.03, 0.001, n=1), loop_ + [loop_[0], loop_[1]], "steel", up=(1, 0, 0))
        slab(mb, _T(sx, yt + 0.162, zt + 0.02) @ _Ry(90) @ _Rx(90), 0.05, 0.034, 0.012, rc=0.006, re=0.003, mat="steel", nc=2, ne=1)
        saddle = [(sx, yt + 0.17 * math.cos(a), zt + 0.17 * math.sin(a)) for a in np.linspace(-PI * 0.82, -PI * 0.18, 13)]
        sweep_frame(mb, rr_profile(0.008, 0.05, 0.003, n=2), saddle, "steel", up=(1, 0, 0))
        _board(mb, sx - 0.025, sx + 0.025, yt - 0.14, yt + 0.14, 1.06, 1.104, "steel", r=0.004)
    rtube(mb, (-0.27, yt - 0.1, 1.085), (0.27, yt - 0.1, 1.085), 0.04, 0.03, "steel", r=0.005)
    _cyl(mb, (-0.29, yt + 0.13, 1.09), (0.29, yt + 0.13, 1.09), 0.014, "steel")                             # perno de abatimiento
    # ---------------- mástil de 2 etapas
    ym = FL_YM
    zo0, zo1 = 0.08, 2.02
    zi0, zi1 = 0.10, 2.03
    t = 0.014
    outer = [(0.405, -0.0625), (0.405, 0.0625), (0.345, 0.0625), (0.345, 0.0625 - t), (0.405 - t, 0.0625 - t), (0.405 - t, -0.0625 + t),
             (0.345, -0.0625 + t), (0.345, -0.0625)]
    inner = [(0.367, -0.045), (0.367, 0.045), (0.285, 0.045), (0.285, 0.045 - 0.012), (0.367 - 0.013, 0.045 - 0.012),
             (0.367 - 0.013, -0.045 + 0.012), (0.285, -0.045 + 0.012), (0.285, -0.045)]
    for sx in (-1, 1):
        for (prof, z0, z1) in ((outer, zo0, zo1), (inner, zi0, zi1)):
            pr = _fillet_closed(prof, [0.004, 0.004, 0.0015, 0.0015, 0.005, 0.005, 0.0015, 0.0015], 3)
            pts = [(sx * u, ym + v) for (u, v) in pr]
            if sx < 0:
                pts = pts[::-1]
            skin(mb, _rk_lprof(pts, z0, z1, re=0.002, n=2), "gunmetal")
        # rodillos: tapas de flecha atornilladas en lo alto del exterior y al pie del interior
        for (xw, zr) in ((0.405, zo1 - 0.09), (0.405, zo0 + 0.32)):
            Mr = _frame_z(Vector((sx * xw, ym, zr)), Vector((sx, 0, 0)))
            _lathe(mb, [(0.0, -0.001), (0.03, -0.001), (0.03, 0.008), (0.026, 0.012), (0.0, 0.012)], Mr, "steel", seg=SEG)
            for k in range(3):
                a = 2 * PI * k / 3 + 0.3
                _nv_bolt_head(mb, Mr @ _T(0.02 * math.cos(a), 0.02 * math.sin(a), 0.012), d=0.006, mat="steel", washer=False)
        # soporte del pivote del mástil al eje y oreja del cilindro de inclinación
        slab(mb, _T(sx * 0.336, (ym + 0.058 + yfa) / 2, Rf - 0.03) @ _Ry(90) @ _T(0, 0, -0.012), 0.16, yfa - ym - 0.058, 0.024, rc=0.04,
             re=0.004, mat="gunmetal", nc=3, ne=2)
        _lathe(mb, [(0.0, -0.02), (0.105, -0.02), (0.11, -0.015), (0.11, 0.015), (0.105, 0.02), (0.0, 0.02)], _T(sx * 0.336, yfa, Rf) @ _Ry(90),
               "gunmetal", seg=SEG)
        slab(mb, _T(sx * 0.40, ym + 0.0625 + 0.025, 0.95) @ _Ry(90) @ _T(0, 0, -0.025), 0.1, 0.05, 0.05, rc=0.012, re=0.004,
             mat="gunmetal", nc=2, ne=2)
    # travesaños del exterior (atrás) y cabezal del interior
    _board(mb, -0.35, 0.35, ym + 0.06, ym + 0.17, 0.10, 0.2, "gunmetal", r=0.006)
    _board(mb, -0.40, 0.40, ym + 0.06, ym + 0.078, zo1 - 0.1, zo1, "gunmetal", r=0.004)
    _board(mb, -0.367, 0.367, ym - 0.02, ym + 0.17, zi1, zi1 + 0.055, "gunmetal", r=0.006)
    for sx in (-1, 1):
        # cilindros de levante (atrás de los rieles) con vástago al cabezal
        xc = sx * 0.25
        _lathe(mb, [(0.0, 0.2), (0.036, 0.2), (0.04, 0.21), (0.04, 1.62), (0.043, 1.63), (0.043, 1.66), (0.028, 1.67), (0.025, 1.675)],
               _T(xc, ym + 0.12, 0.0), "gunmetal", seg=SEG)
        _cyl(mb, (xc, ym + 0.12, 1.67), (xc, ym + 0.12, zi1 + 0.002), 0.025, "steel", seg=SEG)
        _fl_hose(mb, [(xc, ym + 0.165, 0.24), (xc, ym + 0.25, 0.24), (sx * 0.12, -0.66, 0.40), (sx * 0.08, -0.64, 0.62)], r=0.0095)
        # polea de cadena sobre el cabezal y cadena de hojas
        xs_ = sx * 0.17
        Mp = _T(xs_, ym + 0.005, zi1 + 0.09) @ _Ry(90)
        _lathe(mb, [(0.012, -0.022), (0.06, -0.022), (0.062, -0.016), (0.052, -0.008), (0.052, 0.008), (0.062, 0.016), (0.06, 0.022),
                    (0.012, 0.022)], Mp, "steel", seg=48, closed=True)
        for sy in (-1, 1):
            slab(mb, _T(xs_ + sy * 0.03, ym + 0.005, zi1 + 0.055) @ _Ry(90) @ _T(-0.035, 0, -0.005), 0.07, 0.12, 0.01, rc=0.02, re=0.002,
                 mat="gunmetal", nc=3, ne=1)
        _cyl(mb, (xs_ - 0.04, ym + 0.005, zi1 + 0.09), (xs_ + 0.04, ym + 0.005, zi1 + 0.09), 0.012, "steel")
        _leaf_chain(mb, (xs_, ym - 0.05, zi1 + 0.09), (xs_, ym - 0.05, 0.70), (1, 0, 0))
        _leaf_chain(mb, (xs_, ym + 0.06, zi1 + 0.09), (xs_, ym + 0.06, zo1 - 0.06), (1, 0, 0))
        _nv_thread(mb, _T(xs_, ym - 0.05, 0.62), 0.016, 0.08, 0.002, "steel")                               # perno de anclaje
        _nv_nut(mb, _T(xs_, ym - 0.05, 0.655), 0.024, 0.014, "steel", hole=0.008)
        _nv_nut(mb, _T(xs_, ym - 0.05, 0.672), 0.024, 0.01, "steel", hole=0.008)
        # cilindros de inclinación
        _fl_cyl(mb, (sx * 0.40, -0.52, 0.645), (sx * 0.40, ym + 0.0625 + 0.025, 0.95), 0.036, 0.0225, stroke_frac=0.55)
        slab(mb, _T(sx * 0.40, -0.52, 0.575), 0.075, 0.07, 0.03, rc=0.01, re=0.004, mat="gunmetal", nc=2, ne=1)
        for sg in (-1, 1):
            slab(mb, _T(sx * 0.40 + sg * 0.033, -0.52, 0.6) @ _Ry(90) @ _T(-0.045, 0, -0.005), 0.09, 0.06, 0.01, rc=0.025, re=0.002,
                 mat="gunmetal", nc=3, ne=1)
        _fl_hose(mb, [(sx * 0.40, -0.56, 0.68), (sx * 0.37, -0.61, 0.66), (sx * 0.25, -0.645, 0.70)], r=0.0085, bend=0.04)
    # ---------------- carro ITA clase II, respaldo de carga y horquillas de gancho
    yb1 = ym - 0.0705
    yb0 = yb1 - 0.025
    xs_n = [-0.52 + 0.0508 * k for k in range(21)]
    top = [(-0.52, 0.48)]
    for xn in xs_n[1:-1]:
        top += [(xn - 0.007, 0.48), (xn - 0.005, 0.47), (xn + 0.005, 0.47), (xn + 0.007, 0.48)]
    top += [(0.52, 0.48)]
    ub = [(-0.52, 0.38), (0.52, 0.38)] + top[::-1]
    for (P2, z0, z1) in ((ub, None, None), ([(-0.52, 0.075), (0.52, 0.075), (0.52, 0.14), (-0.52, 0.14)], None, None)):
        loops = _rk_lprof([(x, z) for (x, z) in P2], yb0, yb1, re=0.0025, n=2)
        skin(mb, [[(p[0], p[2], p[1]) for p in L] for L in loops], "gunmetal")
    for sx in (-1, 1):
        _board(mb, sx * 0.262 - 0.008, sx * 0.262 + 0.008, yb1 - 0.004, ym + 0.02, 0.07, 0.86, "gunmetal", r=0.004)
        for zr in (0.25, 0.78):
            Mr = _frame_z(Vector((sx * 0.27, ym, zr)), Vector((sx, 0, 0)))
            _lathe(mb, [(0.0, 0.0), (0.012, 0.0), (0.012, 0.016), (0.0, 0.016)], Mr, "steel", seg=SEG)
            _lathe(mb, [(0.012, 0.016), (0.031, 0.017), (0.032, 0.02), (0.032, 0.046), (0.031, 0.049), (0.012, 0.05)], Mr, "steel", seg=SEG)
        _board(mb, sx * 0.17 - 0.03, sx * 0.17 + 0.03, yb1 - 0.002, ym - 0.045, 0.48, 0.62, "gunmetal", r=0.004)    # orejas de cadena
    # respaldo de carga
    yr_ = (yb0 + yb1) / 2
    for sx in (-1, 1):
        rtube(mb, (sx * 0.5, yr_, 0.48), (sx * 0.5, yr_, 1.27), 0.04, 0.025, "gunmetal", r=0.004, up=(0, 1, 0))
    rtube(mb, (-0.52, yr_, 1.27), (0.52, yr_, 1.27), 0.025, 0.04, "gunmetal", r=0.004, up=(0, 0, 1))
    rtube(mb, (-0.48, yr_, 0.87), (0.48, yr_, 0.87), 0.025, 0.03, "gunmetal", r=0.004, up=(0, 0, 1))
    for k in range(8):
        x = -0.42 + 0.12 * k
        rtube(mb, (x, yr_, 0.48), (x, yr_, 1.25), 0.012, 0.04, "gunmetal", r=0.003, up=(0, 1, 0))
        for zw in (0.484, 1.252):
            _bead(mb, [(x - 0.007, yr_ - 0.021, zw), (x + 0.007, yr_ - 0.021, zw)], r=0.0022, mat="gunmetal")
    # horquillas: caña, talón doblado, cuchilla con punta cónica y biselada, ganchos y seguro de posición
    for sx in (-1, 1):
        x = sx * 0.36
        yf0 = yb0 - 0.0005                                               # cara trasera de la caña
        T0, Tt = 0.045, 0.014
        L_ = 1.067
        ycs = yf0 - T0 / 2
        yt_ = yf0 - T0 - L_
        P = [(ycs, 0.50), (ycs, T0 / 2), (ycs - 0.12, T0 / 2), (ycs - 0.5, T0 / 2)]
        P += [(yt_ + d, T0 / 2) for d in (0.3, 0.24, 0.18, 0.13, 0.09, 0.06, 0.04, 0.025, 0.014, 0.008, 0.005, 0.0025, 0.001, 0.0)]
        path = fillet([(x, y_, z_) for (y_, z_) in P], 0.04, 10)
        acc = _arclen(np.array([p[1:] for p in path]))
        tot = acc[-1]

        def sc(s_, tot=tot):
            d = (1.0 - s_) * tot                                         # distancia a la punta
            th = 1.0 if d > 0.3 else (Tt / T0 + (1 - Tt / T0) * (d / 0.3) ** 1.2)
            wd = 1.0 if d > 0.06 else (0.62 + 0.38 * math.sqrt(max(0.0, d / 0.06)))
            if d < 0.006:
                k_ = math.sqrt(max(0.0, 1 - ((0.006 - d) / 0.006) ** 2))
                th *= max(0.35, k_)
                wd *= max(0.6, k_)
            return (th, wd)
        # el perfil se desplaza para que la cara superior de la cuchilla quede plana al adelgazar
        path2 = []
        for p, s_ in zip(path, acc / tot):
            th = sc(s_)[0]
            dz = (1 - th) * T0 / 2 if p[2] < 0.05 else 0.0
            path2.append((p[0], p[1], p[2] + dz))
        sweep_frame(mb, rr_profile(T0, 0.1, 0.0045, n=3), path2, "gunmetal", up=(1, 0, 0), scale=sc)
        # gancho superior sobre la barra (con hueco del pasador) y gancho inferior bajo la barra baja
        _board(mb, x - 0.05, x + 0.05, yf0 - 0.001, yb1 + 0.0065, 0.4805, 0.52, "gunmetal", r=0.004)
        _board(mb, x - 0.05, x + 0.05, yb1 + 0.0003, yb1 + 0.0065, 0.44, 0.52, "gunmetal", r=0.002)
        _board(mb, x - 0.05, x + 0.05, yf0 - 0.001, yb1 + 0.0065, 0.045, 0.0745, "gunmetal", r=0.004)
        _board(mb, x - 0.05, x + 0.05, yb1 + 0.0003, yb1 + 0.0065, 0.045, 0.11, "gunmetal", r=0.002)
        for zb in (0.482, 0.073):
            _bead(mb, [(x - 0.048, yf0 - 0.0015, zb + (0.0015 if zb > 0.3 else -0.0015)), (x + 0.048, yf0 - 0.0015, zb + (0.0015 if zb > 0.3 else -0.0015))],
                  r=0.0028, mat="gunmetal")
        _lathe(mb, [(0.0, 0.0), (0.0085, 0.0), (0.0085, 0.05), (0.0, 0.05)], _T(x, (yf0 + yb1) / 2, 0.47), "steel", seg=SEG)   # pasador
        lever = [(x - 0.03, (yf0 + yb1) / 2, 0.528), (x - 0.03, (yf0 + yb1) / 2, 0.55), (x + 0.03, (yf0 + yb1) / 2, 0.55),
                 (x + 0.03, (yf0 + yb1) / 2, 0.528)]
        _tube(mb, fillet(lever, 0.01, 5), 0.0045, seg=SEG_T + 2, mat="steel")
        _lathe(mb, [(0.0, 0.0), (0.012, 0.0), (0.012, 0.006), (0.0, 0.006)], _T(x, (yf0 + yb1) / 2, 0.52), "steel", seg=SEG)
    # placa de capacidad del carro (estarcido)
    text_font(mb, "5000 LB", 0.035, 0.0006, "sign_white", _T(0, yb0 + 0.0002, 0.405) @ _Rx(90), font="stencil", res=2)
    del r
    return mb

# ======================================================================================================== banco de trabajo


def _serrated(mb, M, w, h, pitch=0.0021, depth=0.0011, mat="steel"):
    """Cara estriada en rombo de una mordaza (dientes piramidales cruzados reales) en el plano XY local (de -w/2..w/2 por
    -h/2..h/2), dientes hacia +Z; cerrada por detrás (z = -0.002) para formar el inserto."""
    nu = max(4, int(round(w / pitch)) * 2)
    nv = max(4, int(round(h / pitch)) * 2)
    U = np.linspace(-w / 2, w / 2, nu + 1)
    Vv = np.linspace(-h / 2, h / 2, nv + 1)
    A, B = np.meshgrid(U, Vv, indexing="ij")
    tu = np.abs(((A + w / 2) / pitch) % 1.0 - 0.5) * 2
    tv = np.abs(((B + h / 2) / pitch) % 1.0 - 0.5) * 2
    Z = depth * np.minimum(1 - tu, 1 - tv)
    Z[0, :] = Z[-1, :] = 0.0
    Z[:, 0] = Z[:, -1] = 0.0
    P = np.stack([A, B, Z], -1)
    V = P.reshape(-1, 3)
    F = []
    for i in range(nu):
        for j in range(nv):
            a, b, c, d = i * (nv + 1) + j, (i + 1) * (nv + 1) + j, (i + 1) * (nv + 1) + j + 1, i * (nv + 1) + j + 1
            F.append((a, b, c, d))
    _nv_add(mb, V, F, mat, M=M)
    slab(mb, M @ _T(0, 0, -0.004), w, h, 0.004, rc=0.0006, re=0.0003, mat=mat, nc=1, ne=1, cap1=False)


def _vise(mb, M, seed=0):
    """Tornillo de banco de mecánico de 4" (mordazas de 100 mm, abre 4-1/2", garganta 3-7/16"): base giratoria con 3 orejas
    atornilladas a la cubierta y dos palancas de freno, tornamesa estriada, cuerpo fijo fundido con yunque, mordaza móvil con
    su viga de deslizamiento, insertos con estrías cruzadas reales sujetos con tornillos Allen, husillo con collarín y
    maneral con topes de bola. Origen: centro de la base sobre la cubierta, frente -Y."""
    r = rng(seed)
    _lathe(mb, [(0.0, 0.0), (0.074, 0.0), (0.076, 0.004), (0.076, 0.016), (0.07, 0.022), (0.062, 0.026), (0.0, 0.026)], M, "paint_od", seg=48)
    for k in range(3):                                                    # orejas con tornillo
        a = PI / 2 + 2 * PI * k / 3 + PI / 3
        p = Vector((0.083 * math.cos(a), 0.083 * math.sin(a), 0.0))
        Ml = M @ _T(*p) @ _Rz(math.degrees(a))
        slab(mb, Ml @ _T(-0.01, 0, 0), 0.04, 0.034, 0.014, rc=0.012, re=0.003, mat="paint_od", nc=3, ne=2)
        _nv_bolt_head(mb, M @ _T(*p) @ _T(0, 0, 0.014), d=0.0127, mat="steel")
    for sx in (-1, 1):                                                    # palancas de freno de la base
        p0 = M @ Vector((sx * 0.06, -0.05, 0.014))
        p1 = M @ Vector((sx * 0.1, -0.085, 0.02))
        _cyl(mb, tuple(p0), tuple(p1), 0.0045, "steel", seg=SEG)
        _lathe(mb, [(0.0, -0.006), (0.006, -0.005), (0.0075, 0.0), (0.006, 0.005), (0.0, 0.006)], _frame_z(p1, p1 - p0), "steel", seg=SEG)
    serr = lambda i, a, rr, z: rr * (1.0 - 0.012 * (0.5 + 0.5 * math.cos(60 * a)))    # noqa: E731
    from kit.clinic_servicios import lathe as slathe
    slathe(mb, [(0.0, 0.026), (0.064, 0.026), (0.064, 0.038), (0.058, 0.044), (0.0, 0.044)], seg=120, mat="paint_od", M=M,
           rmod=lambda i, a, rr, z: serr(i, a, rr, z) if 1 <= i <= 2 else rr)
    # cuerpo fijo (atrás) con yunque y garganta
    _rloft(mb, M @ _T(0, 0.035, 0.044), [(0.0, 0.11, 0.13, 0.0, 0.03), (0.04, 0.1, 0.12, 0.0, 0.028), (0.09, 0.085, 0.11, -0.005, 0.022),
                                         (0.13, 0.12, 0.09, -0.02, 0.012), (0.156, 0.124, 0.09, -0.02, 0.008)], "paint_od", n=4)
    _rloft(mb, M @ _T(0, 0.105, 0.17), [(0.0, 0.06, 0.07, 0.0, 0.01), (0.03, 0.065, 0.08, 0.0, 0.006)], "paint_od", n=3)
    slab(mb, M @ _T(0, 0.105, 0.2), 0.062, 0.076, 0.012, rc=0.008, re=0.003, mat="steel", nc=3, ne=2)          # yunque pulido
    # viga de deslizamiento y mordaza móvil (adelante): abierta 30 mm
    rtube(mb, tuple(M @ Vector((0, -0.125, 0.115))), tuple(M @ Vector((0, 0.05, 0.115))), 0.05, 0.042, "paint_od", r=0.006)
    _rloft(mb, M @ _T(0, -0.098, 0.09), [(0.0, 0.08, 0.06, 0.0, 0.016), (0.06, 0.1, 0.055, 0.003, 0.012), (0.11, 0.124, 0.052, 0.003, 0.008)],
           "paint_od", n=4)
    yj_f, yj_m = -0.0255, -0.0555                                          # caras de los insertos (fija y móvil)
    for (yy, sg) in ((yj_f, -1), (yj_m, 1)):
        Mi = M @ _T(0, yy, 0.183) @ _Rx(-90 * sg)
        _serrated(mb, Mi, 0.1, 0.032, mat="steel")
        for sx in (-1, 1):
            _lathe(mb, [(0.0, -0.0005), (0.004, -0.0005), (0.004, 0.0002), (0.0, 0.0002)], Mi @ _T(sx * 0.035, 0, 0.0004), "cable", seg=SEG)
    slab(mb, M @ _T(0, -0.0105, 0.167), 0.1, 0.03, 0.032, rc=0.004, re=0.002, mat="paint_od", nc=2, ne=1)   # asiento del inserto fijo
    slab(mb, M @ _T(0, -0.0705, 0.167), 0.1, 0.03, 0.032, rc=0.004, re=0.002, mat="paint_od", nc=2, ne=1)
    # husillo, collarín, buje y maneral
    yh = -0.165
    _lathe(mb, [(0.0, 0.0), (0.026, 0.0), (0.028, 0.004), (0.028, 0.022), (0.022, 0.028), (0.0, 0.03)],
           M @ _T(0, -0.12, 0.115) @ _Rx(90), "paint_od", seg=SEG)
    _cyl(mb, tuple(M @ Vector((0, -0.15, 0.115))), tuple(M @ Vector((0, yh + 0.012, 0.115))), 0.011, "steel", seg=SEG)
    _lathe(mb, [(0.0, -0.016), (0.017, -0.016), (0.02, -0.011), (0.02, 0.011), (0.017, 0.016), (0.0, 0.016)],
           M @ _T(0, yh, 0.115) @ _Rx(90), "steel", seg=SEG)
    ang = math.radians(float(r.uniform(-50, 50)))
    hd = M.to_3x3() @ Vector((math.cos(ang), 0, math.sin(ang)))
    hx = M @ Vector((0, yh, 0.115))
    off = float(r.uniform(-0.06, 0.06))
    _cyl(mb, tuple(hx - hd * (0.1 - off)), tuple(hx + hd * (0.1 + off)), 0.0063, "steel", seg=SEG)
    for s_ in (-(0.1 - off), 0.1 + off):
        sg = 1 if s_ > 0 else -1
        _lathe(mb, [(0.0, -0.011), (0.008, -0.0085), (0.0115, 0.0), (0.008, 0.0085), (0.0, 0.011)], _frame_z(hx + hd * (s_ + sg * 0.009), hd),
               "steel", seg=SEG)


def _wrench(mb, M, L=0.2, seed=0):
    """Llave combinada acostada (boca abierta a 15° en +X, estría de 12 puntas en -X), caña en I con cantos redondeados."""
    s = L / 0.24
    w0, t0 = 0.016 * s, 0.0055 * s
    sweep_frame(mb, rr_profile(w0, t0, t0 * 0.35, n=3), [tuple(M @ Vector((x, 0, t0 / 2 + 0.0003))) for x in (-L / 2 + 0.022 * s, L / 2 - 0.028 * s)],
                "steel", up=tuple(M.to_3x3() @ Vector((0, 0, 1))), scale=lambda t_: (1.0 - 0.18 * math.sin(PI * t_), 1.0 - 0.15 * math.sin(PI * t_)))
    # estría: anillo con 12 puntas por dentro
    Ro, Ri = 0.0155 * s, 0.0098 * s
    ring = [(Ri, 0.0003), (Ro - 0.0015, 0.0003), (Ro, 0.0018), (Ro, t0 * 1.2 - 0.0012), (Ro - 0.0015, t0 * 1.2), (Ri, t0 * 1.2)]
    pts12 = lambda a: 1.0 + 0.1 * (0.5 + 0.5 * math.cos(12 * a))                           # noqa: E731
    revolve(mb, ring, "steel", seg=48, M=M @ _T(-L / 2 + 0.006 * s, 0, 0), closed=True)
    revolve(mb, [(Ri * 1.1, 0.0004), (Ri * 1.1, t0 * 1.2 - 0.0001)], "cable", seg=48, M=M @ _T(-L / 2 + 0.006 * s, 0, 0), rmod=pts12,
            caps=False)
    # boca abierta: mordaza en C (perfil redondeado barrido por un arco de 230°) girada 15° respecto a la caña
    Mo = M @ _T(L / 2 - 0.012 * s, 0, 0) @ _Rz(15)
    Rj, wj = 0.0136 * s, 0.0076 * s
    arc = [tuple(Mo @ Vector((Rj * math.cos(a), Rj * math.sin(a), t0 * 0.56))) for a in np.linspace(math.radians(62), math.radians(298), 33)]
    sweep_frame(mb, rr_profile(wj, t0 * 1.05, t0 * 0.3, n=3), arc, "steel", up=tuple(M.to_3x3() @ Vector((0, 0, 1))),
                scale=lambda t_: (1.0 - 0.25 * max(0.0, abs(2 * t_ - 1) - 0.8) / 0.2, 1.0))


def _hammer(mb, M, seed=0):
    """Martillo de uña de 16 oz acostado (mango sobre X, cabeza en Y local, z = 0 en la cubierta): mango de madera ovalado con
    cuello y remate, cabeza forjada con cara redonda biselada, cuello, ojo con cachetes y uña partida curva."""
    st = []
    for (x, a, b) in ((0.0, 0.012, 0.0165), (0.008, 0.0135, 0.0185), (0.03, 0.0128, 0.0172), (0.15, 0.0118, 0.016), (0.24, 0.0094, 0.0132),
                      (0.29, 0.0108, 0.0155), (0.312, 0.0108, 0.0155)):
        st.append([(x, b * math.cos(2 * PI * k / 24), a * math.sin(2 * PI * k / 24) + 0.0165) for k in range(24)])
    skin(mb, [[tuple(M @ Vector(p)) for p in L] for L in st], "wood")
    Mh = M @ _T(0.30, 0, 0.0165)
    _lathe(mb, [(0.0, -0.078), (0.0135, -0.078), (0.0152, -0.075), (0.0152, -0.064), (0.0118, -0.052), (0.0105, -0.034), (0.0118, -0.02)],
           Mh @ _Rx(90), "steel", seg=SEG)                                 # cara, cuello
    _rloft(mb, Mh @ _Rx(-90) @ _T(0, 0, -0.022), [(0.0, 0.03, 0.025, 0.0, 0.006), (0.044, 0.032, 0.026, 0.0, 0.006)], "steel", n=3)
    for sgn in (-1, 1):                                                   # uña partida y curva hacia el mango
        path = [(0.30, 0.02, sgn * 0.0052), (0.299, 0.048, sgn * 0.006), (0.29, 0.074, sgn * 0.0068), (0.274, 0.092, sgn * 0.0074)]
        sweep_frame(mb, rr_profile(0.0084, 0.02, 0.0025, n=3), [tuple(M @ Vector((p[0], p[1], p[2] + 0.0165))) for p in path], "steel",
                    up=tuple(M.to_3x3() @ Vector((1, 0, 0))), scale=lambda t_: (1.0 - 0.5 * t_, 1.0 - 0.6 * t_))


def _screwdriver(mb, M, seed=0):
    """Desarmador de cruz acostado: mango de acetato con estrías, virola, vástago y punta (eje X local, z = 0 en la cubierta)."""
    Ms = M @ _T(0, 0, 0.016) @ _Ry(90)
    from kit.clinic_servicios import lathe as slathe
    fl = lambda i, a, rr, z: rr * (1.0 - 0.07 * max(0.0, math.cos(6 * a)) ** 2) if 2 <= i <= 4 else rr   # noqa: E731
    slathe(mb, [(0.0, -0.11), (0.012, -0.109), (0.015, -0.1), (0.016, -0.09), (0.0155, -0.03), (0.0135, -0.015), (0.0085, -0.008),
                (0.007, 0.0), (0.0, 0.0)], seg=48, mat="plastic", M=Ms, rmod=fl)
    _lathe(mb, [(0.0035, 0.0), (0.0035, 0.1), (0.003, 0.108), (0.0012, 0.116), (0.0, 0.117)], Ms, "steel", seg=SEG)


def _tape(mb, M):
    """Flexómetro de 5 m: carcasa redondeada de dos tapas con costura, tope de cinta y gancho, clip de cinturón."""
    slab(mb, M, 0.068, 0.068, 0.034, rc=0.02, re=0.008, mat="sign_red", nc=4, ne=3)
    _bead(mb, [tuple(M @ Vector((x, y, 0.017))) for (x, y) in rr_pts(0.0685, 0.0685, 0.02, 4)], r=0.0009, ripple=0.0, closed=True,
          mat="cable", taper=False)
    slab(mb, M @ _T(-0.036, -0.005, 0.004), 0.008, 0.026, 0.006, rc=0.002, re=0.001, mat="steel", nc=2, ne=1)
    slab(mb, M @ _T(-0.04, -0.005, 0.0), 0.0012, 0.03, 0.012, rc=0.0005, re=0.0004, mat="steel", nc=1, ne=1)
    slab(mb, M @ _T(0.01, 0.0, 0.034), 0.03, 0.05, 0.0015, rc=0.005, re=0.0005, mat="steel", nc=2, ne=1)


def workbench(seed=0):
    """Banco de trabajo industrial 72 × 30" (1,83 × 0,76 m) a 34": cubierta de maple laminado de 1-3/4" (tiras encoladas con
    juntas y cantos redondeados), bastidor de ángulo de 2" × 3/16" soldado a inglete con cordones visibles, patas de ángulo
    con placa de pie y niveladores roscados con zapata, entrepaño inferior de lámina con cejas sobre largueros de ángulo,
    cajonera colgante atornillada con 2 cajones sobre correderas telescópicas de balines (el de arriba entreabierto con
    llaves de dado), jaladeras troqueladas y portaetiquetas; tornillo de banco de 4" atornillado, martillo, dos llaves
    combinadas, desarmador y flexómetro sobre la cubierta; caja de herramientas de lámina con bisagra de piano, broches y
    asa en el entrepaño. Origen: piso al centro; frente -Y."""
    r = rng(seed)
    mb = MB()
    L, D, H = 1.83, 0.76, 0.864
    tb = 0.0445
    zt = H - tb
    # ---- cubierta de maple: 17 tiras encoladas
    n = 17
    wst = D / n
    for k in range(n):
        y0 = -D / 2 + k * wst
        rr_ = 0.004 if k in (0, n - 1) else 0.0012
        _board(mb, -L / 2, L / 2, y0, y0 + wst, zt, H, "wood", r=rr_)
    # ---- bastidor de ángulo de 2" × 3/16" (perímetro bajo la cubierta) con esquinas a inglete
    a, t = 0.0508, 0.0048
    Lf, Df = L - 0.04, D - 0.04
    cl = _fillet2d([(a - t / 2, t / 2), (t / 2, t / 2), (t / 2, a - t / 2)], 0.004, 3)      # (hacia dentro, hacia abajo)
    Nn = _normals2d(cl)
    prof = [tuple(q) for q in (cl + Nn * t / 2)] + [tuple(q) for q in (cl - Nn * t / 2)[::-1]]
    rect = [(-Lf / 2, -Df / 2, zt), (Lf / 2, -Df / 2, zt), (Lf / 2, Df / 2, zt), (-Lf / 2, Df / 2, zt)]
    mb.sweep([(-px, -py) for (px, py) in prof], _miter_path(rect), "paint_od", closed_path=True, normal=(0, 0, 1))
    # ---- patas de ángulo, placas de pie, niveladores
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * Lf / 2, sy * Df / 2
            lp = [(x - sx * u, y - sy * v) for (u, v) in _fillet2d([(0.0508, 0.0024), (0.0024, 0.0024), (0.0024, 0.0508)], 0.004, 3)]
            ln = np.array(lp)
            Nl = _normals2d(ln)
            pr2 = [tuple(q) for q in (ln + Nl * t / 2)] + [tuple(q) for q in (ln - Nl * t / 2)[::-1]]
            skin(mb, _rk_lprof(pr2, 0.032, zt - 0.0005, re=0.0008, n=1), "paint_od")
            slab(mb, _T(x - sx * 0.035, y - sy * 0.035, 0.0254), 0.076, 0.076, 0.0064, rc=0.006, re=0.0015, mat="paint_od", nc=3, ne=2)
            _bead(mb, [(x - sx * 0.002, y - sy * 0.002, 0.034)] + [(x - sx * 0.002, y - sy * 0.05, 0.034)], r=0.0022, mat="paint_od")
            _bead(mb, [(x - sx * 0.002, y - sy * 0.002, 0.034)] + [(x - sx * 0.05, y - sy * 0.002, 0.034)], r=0.0022, mat="paint_od")
            _bead(mb, [(x - sx * 0.002, y - sy * 0.002, zt - 0.006), (x - sx * 0.002, y - sy * 0.002, zt - 0.05)], r=0.0024, mat="paint_od")
            pf = (x - sx * 0.035, y - sy * 0.035)
            _nv_nut(mb, _T(pf[0], pf[1], 0.0318), 0.019, 0.011, "steel", hole=0.006)
            _nv_thread(mb, _T(pf[0], pf[1], 0.008), 0.0127, 0.045, 0.0019, "steel")
            _lathe(mb, [(0.0, 0.0), (0.026, 0.0), (0.027, 0.003), (0.027, 0.008), (0.022, 0.011), (0.012, 0.012), (0.0, 0.012)],
                   _T(pf[0], pf[1], 0.0), "rubber", seg=SEG)
            _lathe(mb, [(0.0, 0.0), (0.021, 0.0), (0.021, 0.004), (0.0, 0.005)], _T(pf[0], pf[1], 0.0115), "steel", seg=SEG)
    # ---- largueros del entrepaño y entrepaño de lámina con cejas
    zs = 0.16
    for sy in (-1, 1):
        y = sy * Df / 2
        lp = [(px, -py) for (px, py) in prof]
        P = [(-Lf / 2 + 0.003, y, zs), (Lf / 2 - 0.003, y, zs)]
        sweep_frame(mb, [(sy * px, py) for (px, py) in lp], P, "paint_od", up=(0, 0, 1))
    for sx in (-1, 1):
        sweep_frame(mb, [(-sx * px, -py) for (px, py) in prof][::-1], [(sx * Lf / 2, -Df / 2 + 0.003, zs), (sx * Lf / 2, Df / 2 - 0.003, zs)],
                    "paint_od", up=(0, 0, 1))
    slab(mb, _T(0, 0, zs), Lf - 0.012, Df - 0.012, 0.0019, rc=0.004, re=0.0008, mat="paint_od", nc=2, ne=1)
    for sy in (-1, 1):
        _board(mb, -Lf / 2 + 0.006, Lf / 2 - 0.006, sy * (Df / 2 - 0.0075) - 0.00095, sy * (Df / 2 - 0.0075) + 0.00095, zs - 0.03, zs + 0.0015,
               "paint_od", r=0.0006)
    # ---- cajonera colgante (derecha): lámina cal. 18, tornillos al bastidor, 2 cajones
    cx, cw, cd, ch = L / 2 - 0.34, 0.5, 0.62, 0.29
    z1 = zt - 0.0005
    z0 = z1 - ch
    for sx in (-1, 1):
        _board(mb, cx + sx * cw / 2 - (0.0012 if sx > 0 else 0.0), cx + sx * cw / 2 + (0.0 if sx > 0 else 0.0012), -cd / 2, cd / 2, z0, z1, "paint_od",
               r=0.0005)
        for zb in (z0 + 0.03, z1 - 0.03):
            _nv_bolt_head(mb, _T(cx + sx * (cw / 2 + 0.0012), -0.2, zb) @ _Ry(90 * sx), d=0.0064, mat="steel")
    _board(mb, cx - cw / 2, cx + cw / 2, -cd / 2, cd / 2, z0, z0 + 0.0012, "paint_od", r=0.0005)
    _board(mb, cx - cw / 2, cx + cw / 2, cd / 2 - 0.0012, cd / 2, z0, z1, "paint_od", r=0.0005)
    _board(mb, cx - cw / 2, cx + cw / 2, -cd / 2, -cd / 2 + 0.018, z1 - 0.012, z1, "paint_od", r=0.0008)
    hd = (ch - 0.016) / 2
    for k in range(2):
        za = z0 + 0.004 + k * (hd + 0.004)
        zb = za + hd
        opn = 0.16 if k == 1 else 0.0
        yf = -cd / 2 - opn
        Md = _T(cx, yf, za)
        # frente formado con ceja superior troquelada (jaladera de canal) y portaetiquetas
        slab(mb, Md @ _T(0, -0.009, 0.0), cw - 0.006, 0.018, hd - 0.025, rc=0.002, re=0.0012, mat="paint_od", nc=2, ne=1)
        hp = _fillet2d([(0.0, hd - 0.025), (-0.02, hd - 0.025), (-0.02, hd - 0.001), (0.002, hd - 0.001)], 0.004, 3)
        Nh = _normals2d(hp)
        hprof = [tuple(q) for q in (hp + Nh * 0.0006)] + [tuple(q) for q in (hp - Nh * 0.0006)[::-1]]
        sweep_frame(mb, [(-u, v) for (u, v) in hprof], [tuple(Md @ Vector((-cw / 2 + 0.003, 0, 0))), tuple(Md @ Vector((cw / 2 - 0.003, 0, 0)))],
                    "paint_od", up=(0, 0, 1))
        slab(mb, Md @ _T(0, -0.0182, 0.035) @ _Rx(90), 0.08, 0.035, 0.0012, rc=0.003, re=0.0004, mat="aluminium", nc=2, ne=1)
        slab(mb, Md @ _T(0, -0.0192, 0.035) @ _Rx(90), 0.066, 0.024, 0.0004, rc=0.001, re=0.0001, mat="paper", nc=1, ne=1)
        # caja del cajón (lados, fondo, trasera) y correderas de 3 miembros
        dd = cd - 0.03
        for sx in (-1, 1):
            xs_ = cx + sx * (cw / 2 - 0.016)
            _board(mb, xs_ - 0.0006, xs_ + 0.0006, yf, yf + dd, za + 0.01, zb - 0.03, "paint_od", r=0.0004)
            for (dxs, y_a, y_b, hz) in ((0.0045, -cd / 2, cd / 2 - 0.01, 0.034), (0.009, -cd / 2 - opn * 0.5, cd / 2 - 0.01 - opn * 0.5, 0.028),
                                         (0.0125, yf, yf + dd - 0.02, 0.022)):
                xr = cx + sx * (cw / 2 - 0.0012 - dxs + 0.0026)
                chn = [(-0.0018, -hz / 2), (0.0018, -hz / 2), (0.0018, -hz / 2 + 0.0008), (-0.001, -hz / 2 + 0.0008), (-0.001, hz / 2 - 0.0008),
                       (0.0018, hz / 2 - 0.0008), (0.0018, hz / 2), (-0.0018, hz / 2)]
                sweep_frame(mb, [(sx * u, v) for (u, v) in chn][::(1 if sx > 0 else -1)], [(xr, y_a, za + 0.03), (xr, y_b, za + 0.03)],
                            "galvanized", up=(0, 0, 1))
        _board(mb, cx - cw / 2 + 0.016, cx + cw / 2 - 0.016, yf, yf + dd, za + 0.008, za + 0.0092, "paint_od", r=0.0004)
        _board(mb, cx - cw / 2 + 0.016, cx + cw / 2 - 0.016, yf + dd - 0.0012, yf + dd, za + 0.008, zb - 0.03, "paint_od", r=0.0004)
        if opn > 0:                                                       # llaves de dado en el cajón abierto
            for j in range(9):
                d_ = 0.012 + j * 0.0016
                p = (cx - 0.16 + j * 0.035, yf + 0.06, za + 0.0092)
                _lathe(mb, [(d_ * 0.55, 0.0), (d_, 0.0), (d_, 0.028), (d_ * 0.92, 0.031), (d_ * 0.62, 0.031), (d_ * 0.62, 0.012)],
                       _T(*p), "steel", seg=SEG, closed=True)
                _lathe(mb, [(0.0, 0.0105), (d_ * 0.62, 0.0105), (0.0, 0.011)], _T(*p), "cable", seg=6)
    # ---- tornillo de banco y herramientas sobre la cubierta
    _vise(mb, _T(-L / 2 + 0.2, -D / 2 + 0.16, H), seed=seed)
    _hammer(mb, _T(-0.3, 0.06, H) @ _Rz(-20 + _jit(r, 8)), seed=seed)
    _wrench(mb, _T(0.05, -0.12, H) @ _Rz(12 + _jit(r, 10)), L=0.24)
    _wrench(mb, _T(0.12, -0.2, H) @ _Rz(-8 + _jit(r, 10)), L=0.19)
    _screwdriver(mb, _T(0.38, 0.05, H) @ _Rz(75 + _jit(r, 10)), seed=seed)
    _tape(mb, _T(0.28, -0.22, H) @ _Rz(_jit(r, 30)))
    # ---- caja de herramientas de lámina en el entrepaño
    Mtb = _T(-0.38, 0.02, zs + 0.0019) @ _Rz(_jit(r, 4))
    slab(mb, Mtb, 0.52, 0.22, 0.155, rc=0.012, re=0.004, mat="sign_red", nc=3, ne=2)
    for k in range(2):                                                    # nervios del cuerpo
        slab(mb, Mtb @ _T(0, 0, 0.03 + k * 0.08) @ _T(0, 0, 0), 0.524, 0.224, 0.006, rc=0.013, re=0.0025, mat="sign_red", nc=3, ne=2)
    Ml = Mtb @ _T(0, 0, 0.157)
    loops = []
    for (z_, inset) in ((0.0, 0.0), (0.045, 0.0), (0.06, 0.012), (0.07, 0.03)):
        loops.append([(x, y, z_) for (x, y) in rr_pts(0.524 - inset * 0.3, 0.224 - inset * 2, 0.013, 3)])
    skin(mb, loops, "sign_red", M=Ml)
    _cyl(mb, tuple(Mtb @ Vector((-0.25, 0.113, 0.157))), tuple(Mtb @ Vector((0.25, 0.113, 0.157))), 0.0035, "steel", seg=SEG)   # bisagra
    for sx in (-1, 1):                                                    # broches
        Mc = Mtb @ _T(sx * 0.2, -0.1115, 0.13) @ _Rx(90)
        slab(mb, Mc, 0.03, 0.04, 0.003, rc=0.004, re=0.001, mat="steel", nc=2, ne=1)
        slab(mb, Mc @ _T(0, 0.03, 0.002), 0.024, 0.03, 0.0025, rc=0.004, re=0.001, mat="steel", nc=2, ne=1)
    hp = [(-0.11, 0.0, 0.227), (-0.11, 0.0, 0.262), (0.11, 0.0, 0.262), (0.11, 0.0, 0.227)]
    _tube(mb, [tuple(Mtb @ Vector(p)) for p in fillet(hp, 0.015, 6)], 0.0075, seg=SEG, mat="cable")
    for sx in (-1, 1):
        slab(mb, Mtb @ _T(sx * 0.11, 0, 0.222), 0.03, 0.02, 0.008, rc=0.006, re=0.002, mat="steel", nc=2, ne=1)
    return mb

# ======================================================================================================== lámpara high-bay


def _fin(mb, M, prof, t, mat="aluminium", re=0.0006):
    """Aleta de disipador: perfil 2D cerrado (en el plano XZ local) con espesor t en Y local y cantos redondeados."""
    loops = _rk_lprof([tuple(p) for p in prof], -t / 2, t / 2, re=re, n=2)
    skin(mb, [[(x, z, y) for (x, y, z) in L] for L in loops], mat, M=M)


def high_bay_light():
    """Lámpara LED industrial tipo UFO de 150-200 W (Ø 300 mm × 135 mm): disipador de aluminio fundido con 48 aletas radiales
    reales de canto redondeado sobre disco base biselado, caja del driver integrada arriba con nervios y prensaestopa,
    armella forjada roscada con tuerca, cadena de cuelgue con gancho S y cable de seguridad, cordón de alimentación SJOW
    con caída natural, bisel inferior atornillado y mica de policarbonato con matriz de lentes TIR. Origen: punto de cuelgue
    (interior de la armella); cuelga hacia -Z."""
    mb = MB()
    R = 0.15
    # armella forjada y espárrago con tuerca
    revolve(mb, [(0.016 + 0.0042 * math.cos(a), 0.0042 * math.sin(a)) for a in np.linspace(0, 2 * PI, 17)[:-1]], "steel", seg=36,
            M=_T(0, 0, -0.0118) @ _Rx(90), closed=True)
    _lathe(mb, [(0.0, -0.028), (0.006, -0.029), (0.0075, -0.036), (0.0075, -0.045), (0.0065, -0.046), (0.0, -0.046)], Matrix(), "steel", seg=SEG)
    _nv_thread(mb, _T(0, 0, -0.072), 0.0095, 0.03, 0.0016, "steel")
    _nv_nut(mb, _T(0, 0, -0.064), 0.016, 0.008, "steel", hole=0.004)
    zt = -0.064                                                           # tapa de la caja del driver
    # caja del driver con nervios
    from kit.clinic_servicios import lathe as slathe
    rib = lambda i, a, rr, z: rr * (1.0 + 0.05 * max(0.0, math.cos(12 * a)) ** 8) if 1 <= i <= 3 else rr   # noqa: E731
    slathe(mb, [(0.0, zt), (0.052, zt), (0.058, zt - 0.004), (0.06, zt - 0.012), (0.06, zt - 0.05), (0.064, zt - 0.054), (0.0, zt - 0.054)],
           seg=96, mat="aluminium", M=Matrix(), rmod=rib)
    zb = zt - 0.054                                                       # cara superior del disco base
    _lathe(mb, [(0.0, zb), (R - 0.004, zb - 0.006), (R, zb - 0.01), (R, zb - 0.022), (R - 0.004, zb - 0.026), (0.0, zb - 0.026)], Matrix(),
           "aluminium", seg=96)
    for k in range(48):                                                   # aletas radiales
        a = 2 * PI * (k + 0.5) / 48
        r0 = 0.068 if k % 2 == 0 else 0.095
        prof = _fillet_closed([(r0, zb - 0.004), (R - 0.006, zb - 0.012), (R - 0.006, zb + 0.008), (r0 + 0.012, zb + 0.048), (r0, zb + 0.048)],
                              [0.001, 0.002, 0.003, 0.006, 0.001], 3)
        _fin(mb, _Rz(math.degrees(a)), prof, 0.0019)
    # bisel inferior con tornillos y mica con lentes TIR
    zl = zb - 0.026
    _lathe(mb, [(0.128, zl + 0.0005), (R - 0.004, zl + 0.0005), (R - 0.003, zl - 0.006), (R - 0.008, zl - 0.009), (0.128, zl - 0.009),
                (0.125, zl - 0.006)], Matrix(), "aluminium", seg=96, closed=True)
    for k in range(8):
        a = 2 * PI * k / 8
        _lathe(mb, [(0.0, 0.0), (0.0035, 0.0), (0.003, -0.0015), (0.0, -0.002)], _T(0.139 * math.cos(a), 0.139 * math.sin(a), zl - 0.009),
               "steel", seg=16)
    _lathe(mb, [(0.0, zl - 0.004), (0.127, zl - 0.004), (0.127, zl - 0.007), (0.0, zl - 0.0075)], Matrix(), "glass", seg=96)
    k = 0
    for ring_r, nn in ((0.0, 1), (0.024, 8), (0.048, 15), (0.072, 22), (0.096, 29), (0.117, 36)):
        for j in range(nn):
            a = 2 * PI * j / nn + 0.2 * k
            p = (ring_r * math.cos(a), ring_r * math.sin(a), zl - 0.007)
            _lathe(mb, [(0.0, 0.0), (0.0085, 0.0), (0.0078, -0.0022), (0.0055, -0.0038), (0.0, -0.0045)], _T(*p), "glass", seg=16)
        k += 1
    # prensaestopa y cordón de alimentación que sube junto a la cadena
    pg = Vector((0.06, 0.0, zt - 0.03))
    _lathe(mb, [(0.0, -0.001), (0.009, -0.001), (0.009, 0.008), (0.0105, 0.009), (0.0105, 0.016), (0.0075, 0.02), (0.006, 0.026)],
           _frame_z(pg, Vector((1, 0, 0))), "plastic", seg=SEG)
    cab = [(0.085, 0.0, zt - 0.03), (0.11, 0.0, zt - 0.025), (0.125, 0.006, zt + 0.02), (0.08, 0.012, 0.06), (0.03, 0.012, 0.13),
           (0.018, 0.012, 0.205)]
    _tube(mb, fillet(cab, 0.04, 8), 0.0046, seg=16, mat="cable")
    # cadena de cuelgue con gancho S y cable de seguridad
    links = []
    zc = -0.002
    k = 0
    while zc < 0.17:
        links.append((zc, k))
        zc += 0.026
        k += 1
    with mb.soft():
        for (zc, k) in links:
            M = _T(0, 0, zc + 0.016) @ (_Rz(90) if k % 2 else Matrix())
            pts = []
            for q in range(8):
                g = -PI / 2 + PI * q / 7
                pts.append((0.0, 0.0055 * math.cos(g) * 1.0, 0.0105 + 0.0055 * math.sin(g)))
            for q in range(8):
                g = PI / 2 + PI * q / 7
                pts.append((0.0, 0.0055 * math.cos(g), -0.0105 + 0.0055 * math.sin(g)))
            loop_tube(mb, [tuple(M @ Vector(p)) for p in pts], 0.0022, seg=12, mat="galvanized", normal=tuple(M.to_3x3() @ Vector((1, 0, 0))))
        zs = links[-1][0] + 0.032
        sh = [(0.0, 0.0, zs - 0.012), (0.009, 0.0, zs - 0.004), (0.0, 0.0, zs + 0.006), (-0.009, 0.0, zs + 0.016), (0.0, 0.0, zs + 0.026),
              (0.007, 0.0, zs + 0.02)]
        mb.tube(fillet(sh, 0.006, 5), 0.0026, seg=12, mat="galvanized")
        cbl = [(-0.012, 0.004, -0.024), (-0.016, 0.006, 0.02), (-0.012, 0.006, 0.12), (-0.006, 0.004, 0.2)]
        mb.tube(fillet(cbl, 0.03, 6), 0.0012, seg=12, mat="galvanized")
    return mb


# ======================================================================================================== estación de extintor


def _wrap_text(mb, s, size, depth, mat, R, zc, M, font="sign", bold=False, ang0=-PI / 2):
    """Texto 3D envuelto sobre un cilindro de radio R (eje Z local de M), centrado en el ángulo ang0 y a la altura zc."""
    from kit.fonts import text_font
    tmp = MB()
    text_font(tmp, s, size, depth, mat, Matrix(), font=font, bold=bold, res=2)
    for v in tmp.bm.verts:
        x, y, z = v.co
        a = ang0 + x / R
        rr = R + z
        v.co = Vector((rr * math.cos(a), rr * math.sin(a), zc + y))
    mb.join(tmp, M)


def _extinguisher10(mb, M, seed=0):
    """Extintor de polvo ABC de 10 lb (Ø 5" × 20"): cilindro de acero con base y domo, etiqueta envolvente con texto e
    instrucciones, collarín moleteado, válvula forjada con manija de transporte y palanca de disparo de lámina en canal,
    pasador con argolla y precinto, manómetro con bisel y mica, salida hexagonal, manguera de 16 lados con casquillos y
    boquilla sujeta por fleje con clip. M: origen en el eje del cilindro al nivel de su base; frente -Y."""
    r = rng(seed)
    R = 0.0635
    body = [(0.0, 0.004), (0.054, 0.004), (0.057, 0.0), (0.0605, 0.0012), (0.0625, 0.006), (R, 0.014), (R, 0.355), (0.0622, 0.37),
            (0.058, 0.385), (0.05, 0.398), (0.04, 0.407), (0.029, 0.413), (0.0205, 0.416), (0.0195, 0.418), (0.0195, 0.43)]
    _lathe(mb, body, M, "sign_red", seg=48)
    # etiqueta envolvente (1 mm) con texto
    arc_solid(mb, R - 0.0004, R + 0.0008, 0.12, 0.33, -PI / 2 - math.radians(75), -PI / 2 + math.radians(75), 30, "sign_white", M=M)
    _wrap_text(mb, "FIRE", 0.03, 0.0008, "sign_red", R + 0.0006, 0.285, M, bold=True)
    _wrap_text(mb, "EXTINGUISHER", 0.0105, 0.0006, "cable", R + 0.0006, 0.265, M, bold=True)
    _wrap_text(mb, "ABC  10 LB", 0.0125, 0.0006, "sign_red", R + 0.0006, 0.243, M, bold=True)
    for k, s_ in enumerate(("1. PULL PIN", "2. AIM AT BASE OF FIRE", "3. SQUEEZE LEVER", "4. SWEEP SIDE TO SIDE")):
        _wrap_text(mb, s_, 0.0062, 0.0005, "cable", R + 0.0006, 0.215 - k * 0.012, M)
    for k in range(3):
        arc_solid(mb, R + 0.0006, R + 0.0012, 0.142 + k * 0.007, 0.1445 + k * 0.007, -PI / 2 - math.radians(50), -PI / 2 + math.radians(48 - 9 * k),
                  14, "cable", M=M)
    # fleje porta-boquilla
    _lathe(mb, [(R - 0.0005, 0.085), (R + 0.0012, 0.085), (R + 0.0014, 0.0865), (R + 0.0014, 0.0985), (R + 0.0012, 0.1), (R - 0.0005, 0.1)],
           M, "steel", seg=48, closed=True)
    # collarín moleteado y válvula
    zt = 0.43
    from kit.clinic_servicios import lathe as slathe
    knurl = lambda i, a, rr, z: rr * (1.0 - 0.035 * (0.5 + 0.5 * math.cos(30 * a))) if 1 <= i <= 2 else rr   # noqa: E731
    slathe(mb, [(0.0, zt - 0.012), (0.0255, zt - 0.012), (0.0255, zt), (0.023, zt + 0.002), (0.0, zt + 0.002)], seg=120, mat="steel",
           M=M, rmod=knurl)
    Mv = M @ _T(0, 0, zt + 0.002)
    _rloft(mb, Mv, [(0.0, 0.034, 0.042, 0.004, 0.01), (0.03, 0.03, 0.04, 0.004, 0.009), (0.042, 0.026, 0.034, 0.002, 0.007)], "steel", n=3)
    ch = _fillet_closed([(-0.012, -0.004), (0.012, -0.004), (0.012, 0.004), (0.0098, 0.004), (0.0098, -0.0018), (-0.0098, -0.0018),
                         (-0.0098, 0.004), (-0.012, 0.004)], [0.002, 0.002, 0.0006, 0.0004, 0.0004, 0.0006, 0.002, 0.002], 2)
    sweep_frame(mb, ch, [tuple(Mv @ Vector(p)) for p in fillet([(0, 0.015, 0.012), (0, 0.06, 0.008), (0, 0.105, -0.004)], 0.03, 5)], "steel",
                up=tuple(M.to_3x3() @ Vector((0, 0, 1))))                   # manija de transporte (hacia el muro)
    _lathe(mb, [(0.0, 0.0), (0.012, 0.0), (0.0125, 0.004), (0.0, 0.0045)], Mv @ _T(0, 0.105, -0.004) @ _Rx(-90), "plastic", seg=SEG)
    sweep_frame(mb, [(x, -y) for (x, y) in ch], [tuple(Mv @ Vector(p)) for p in fillet([(0, -0.012, 0.045), (0, 0.04, 0.052), (0, 0.108, 0.07)],
                                                                                          0.04, 5)], "steel", up=tuple(M.to_3x3() @ Vector((0, 0, 1))))
    for sx in (-1, 1):                                                    # orejas y perno de pivote
        slab(mb, Mv @ _T(sx * 0.0125, -0.014, 0.034) @ _Ry(90), 0.022, 0.02, 0.003, rc=0.006, re=0.0008, mat="steel", nc=2, ne=1)
    _cyl(mb, tuple(Mv @ Vector((-0.016, -0.012, 0.045))), tuple(Mv @ Vector((0.016, -0.012, 0.045))), 0.0022, "steel", seg=SEG)
    # pasador con argolla y precinto
    zp = 0.03
    _cyl(mb, tuple(Mv @ Vector((-0.021, 0.022, zp))), tuple(Mv @ Vector((0.017, 0.022, zp))), 0.0017, "steel", seg=SEG_T + 2)
    with mb.soft():
        loop_tube(mb, [tuple(Mv @ Vector((-0.033 + 0.012 * math.cos(a), 0.022, zp + 0.012 * math.sin(a)))) for a in np.linspace(0, 2 * PI, 25)[:-1]],
                  0.0013, seg=12, mat="steel", normal=tuple(M.to_3x3() @ Vector((0, 1, 0))))
        seal = [(-0.042, 0.022, zp + 0.008), (-0.038, 0.03, zp + 0.024), (-0.02, 0.04, zp + 0.03), (0.0, 0.042, zp + 0.024), (0.006, 0.036, zp + 0.012)]
        mb.tube([tuple(Mv @ Vector(p)) for p in fillet(seal, 0.007, 5)], 0.0009, seg=12, mat="paint_yellow")
    slab(mb, Mv @ _T(-0.04, 0.034, zp + 0.03), 0.009, 0.006, 0.006, rc=0.002, re=0.001, mat="paint_yellow", nc=2, ne=1)
    # manómetro al frente
    Mg = Mv @ _T(0, -0.0135, 0.024) @ _Rx(90)
    _cyl(mb, tuple(Mg @ Vector((0, 0, -0.002))), tuple(Mg @ Vector((0, 0, 0.012))), 0.004, "brass", seg=SEG)
    _lathe(mb, [(0.0, 0.012), (0.0145, 0.012), (0.0155, 0.014), (0.0155, 0.022), (0.0165, 0.023), (0.0165, 0.025), (0.014, 0.0255)], Mg, "steel",
           seg=SEG)
    _lathe(mb, [(0.0, 0.0225), (0.0138, 0.0225), (0.0, 0.0227)], Mg, "sign_white", seg=SEG)
    arc_solid(mb, 0.008, 0.012, 0.0226, 0.0229, math.radians(60), math.radians(120), 8, "sign_green", M=Mg)
    needle = math.radians(float(r.uniform(-8, 6)))
    slab(mb, Mg @ _T(0, 0, 0.0229) @ _Rz(math.degrees(needle) + 90), 0.0105, 0.0008, 0.0004, rc=0.0003, re=0.0001, mat="cable", nc=1, ne=1)
    _lathe(mb, [(0.0, 0.0255), (0.014, 0.0255), (0.012, 0.0262), (0.0, 0.0265)], Mg, "glass", seg=SEG)
    # salida, manguera y boquilla
    Mo = Mv @ _T(0.016, 0.0, 0.018) @ _Ry(90)
    _nv_nut(mb, Mo, 0.016, 0.009, "steel", hole=0.004)
    _lathe(mb, [(0.0, 0.009), (0.008, 0.009), (0.008, 0.026), (0.0085, 0.028), (0.0085, 0.032), (0.0072, 0.034)], Mo, "steel", seg=SEG)
    p0 = Mo @ Vector((0, 0, 0.033))
    loc = M.inverted() @ p0
    hp = [tuple(loc), (loc.x + 0.03, loc.y - 0.004, loc.z - 0.01), (0.074, -0.012, 0.36), (0.075, -0.02, 0.2), (0.07, -0.036, 0.13)]
    P = fillet(hp, 0.05, 8)
    _tube(mb, [tuple(M @ Vector(p)) for p in P], 0.0075, seg=16, mat="rubber")
    pe, pd = Vector(P[-1]), (Vector(P[-1]) - Vector(P[-2])).normalized()
    Mn = M @ Matrix.Translation(pe) @ pd.to_track_quat("Z", "Y").to_matrix().to_4x4()
    _lathe(mb, [(0.0, -0.004), (0.0092, -0.004), (0.0092, 0.012), (0.0085, 0.014), (0.0075, 0.016), (0.0075, 0.05), (0.0062, 0.068),
                (0.004, 0.07), (0.0035, 0.066), (0.0, 0.066)], Mn, "cable", seg=SEG)
    for k in range(2):
        _lathe(mb, [(0.0075, 0.002 + k * 0.006), (0.0086, 0.004 + k * 0.006), (0.0075, 0.006 + k * 0.006)], M @ Matrix.Translation(Vector(P[0])) @
               (Vector(P[1]) - Vector(P[0])).normalized().to_track_quat("Z", "Y").to_matrix().to_4x4(), "steel", seg=SEG)
    ang = math.atan2(-0.036, 0.07)
    cpos = Vector((R * math.cos(ang), R * math.sin(ang), 0.092))
    nrm = Vector((math.cos(ang), math.sin(ang), 0))
    Mk = M @ Matrix.Translation(cpos) @ nrm.to_track_quat("Z", "Y").to_matrix().to_4x4()
    clip = [(-0.0065, 0.0, 0.0), (-0.0065, 0.0, 0.004), (-0.009, 0.0, 0.0105), (-0.0065, 0.0, 0.0175), (0.0, 0.0, 0.0195), (0.0065, 0.0, 0.0175),
            (0.009, 0.0, 0.0105), (0.0075, 0.0, 0.006)]
    sweep_frame(mb, rr_profile(0.0012, 0.012, 0.0005, n=2), [tuple(Mk @ Vector(p)) for p in fillet(clip, 0.003, 3)], "steel",
                up=tuple(Mk.to_3x3() @ Vector((0, 1, 0))))
    return zt


def extinguisher_station(seed=0):
    """Punto de fuego en muro: tablero de lámina blanca de 600 × 1300 con franja roja perimetral, cabezal rojo "FIRE POINT"
    (Overpass bold) y placa de instrucciones, fijado con 4 pijas con taquete; gancho de lámina troquelada atornillado y
    extintor ABC de 10 lb (kit propio: válvula, manómetro, pasador con precinto, manguera de 16 lados, boquilla) con
    etiqueta de inspección colgando del cuello por un cordón. Origen: cara del muro al piso, centrado; crece hacia -Y."""
    from kit.fonts import text_font
    r = rng(seed)
    mb = MB()
    t = 0.004
    W_, z0, z1 = 0.6, 0.85, 2.15
    slab(mb, _T(0, -t / 2, z0) @ _Rx(0), W_, t, z1 - z0, rc=0.004, re=0.0015, mat="sign_white", nc=2, ne=1)
    for (xa, xb, za, zb) in ((-W_ / 2 + 0.012, W_ / 2 - 0.012, z0 + 0.012, z0 + 0.04), (-W_ / 2 + 0.012, -W_ / 2 + 0.04, z0 + 0.04, z1 - 0.2),
                             (W_ / 2 - 0.04, W_ / 2 - 0.012, z0 + 0.04, z1 - 0.2)):
        _board(mb, xa, xb, -t - 0.0006, -t + 0.0003, za, zb, "sign_red", r=0.0003)
    _board(mb, -W_ / 2 + 0.012, W_ / 2 - 0.012, -t - 0.0006, -t + 0.0003, z1 - 0.2, z1 - 0.012, "sign_red", r=0.0003)
    text_font(mb, "FIRE POINT", 0.072, 0.0008, "sign_white", _T(0, -t - 0.0006, z1 - 0.135) @ _Rx(90), font="sign", bold=True, res=3)
    Mi = _T(0, -t - 0.0006, z1 - 0.37) @ _Rx(90)
    slab(mb, Mi, 0.36, 0.2, 0.0012, rc=0.008, re=0.0004, mat="sign_red", nc=3, ne=1)
    slab(mb, Mi @ _T(0, 0, 0.0012), 0.344, 0.184, 0.0005, rc=0.006, re=0.0002, mat="sign_white", nc=3, ne=1)
    zz = 0.06
    for (s_, sz, b) in (("IN CASE OF FIRE", 0.022, True), ("PULL  -  AIM  -  SQUEEZE  -  SWEEP", 0.0125, True),
                        ("RAISE THE ALARM  -  CALL FOR HELP", 0.0105, False), ("KEEP THIS AREA CLEAR", 0.0105, False)):
        text_font(mb, s_, sz, 0.0005, "sign_red" if b else "cable", Mi @ _T(0, zz, 0.0017), font="sign", bold=b, res=2)
        zz -= sz * 1.9 + 0.006
    for x in (-W_ / 2 + 0.026, W_ / 2 - 0.026):                          # pijas con taquete
        for z in (z0 + 0.026, z1 - 0.026):
            Ms = _T(x, -t + 0.0002, z) @ _Rx(90)
            _lathe(mb, [(0.0, 0.0), (0.0062, 0.0), (0.006, 0.0008), (0.0045, 0.0021), (0.0, 0.0025)], Ms, "steel", seg=SEG)
            for ang in (0, 90):
                slab(mb, Ms @ _T(0, 0, 0.0016) @ _Rz(ang + 20), 0.0068, 0.0011, 0.0012, rc=0.0002, re=0.0001, mat="cable", nc=1, ne=1)
    # gancho de lámina troquelada atornillado al tablero
    zb = 1.0
    yc = -0.115
    Mx = _T(0, yc, zb)
    zh = zb + 0.4345
    plate = _fillet_closed([(-0.02, -0.11), (0.02, -0.11), (0.02, 0.11), (-0.02, 0.11)], 0.012, 3)
    skin(mb, _rk_lprof([tuple(p) for p in plate], 0.0, 0.003, re=0.0008, n=1), "steel", M=_T(0, -t + 0.0002, zh - 0.04) @ _Rx(90))
    for zs_ in (zh - 0.12, zh + 0.04):
        _nv_bolt_head(mb, _T(0, -t - 0.0028, zs_) @ _Rx(90), d=0.0055, mat="steel", washer=False)
    hook = [(0, -t - 0.002, zh - 0.004), (0, -t - 0.02, zh - 0.004), (0, -t - 0.034, zh - 0.0), (0, -t - 0.038, zh + 0.014)]
    sweep_frame(mb, rr_profile(0.003, 0.028, 0.0012, n=2), fillet(hook, 0.008, 5), "steel", up=(1, 0, 0))
    for sx in (-1, 1):
        slab(mb, _T(sx * 0.0135, -t - 0.017, zh - 0.016) @ _Ry(90), 0.022, 0.03, 0.003, rc=0.005, re=0.0008, mat="steel", nc=2, ne=1)
    # extintor colgado: la manija de transporte descansa en el gancho
    zt = _extinguisher10(mb, Mx, seed=seed)
    # etiqueta de inspección: cordón al cuello y tarjeta colgando de lado
    ztn = zb + 0.416
    phi = math.radians(40 + _jit(r, 6))
    with mb.soft():
        loop_tube(mb, [(0.021 * math.cos(a), yc + 0.021 * math.sin(a), ztn) for a in np.linspace(0, 2 * PI, 25)[:-1]], 0.0008, seg=12, mat="cable",
                  normal=(0, 0, 1))
        dome = [(0.021, ztn), (0.032, ztn - 0.005), (0.045, ztn - 0.014), (0.056, ztn - 0.026), (0.063, ztn - 0.042), (0.065, ztn - 0.07)]
        mb.tube([(r_ * math.sin(phi), yc - r_ * math.cos(phi), z_) for (r_, z_) in dome], 0.0008, seg=12, mat="cable")
    Mt = _T(0.0655 * math.sin(phi), yc - 0.0655 * math.cos(phi), ztn - 0.07) @ _Rz(math.degrees(phi)) @ _Rx(90)
    slab(mb, Mt @ _T(0, -0.05, -0.0003), 0.05, 0.09, 0.0006, rc=0.006, re=0.0002, mat="paper", nc=2, ne=1)
    _lathe(mb, [(0.0025, 0.0), (0.005, 0.0), (0.005, 0.0011), (0.0025, 0.0011)], Mt @ _T(0, -0.012, -0.0003), "brass", seg=16, closed=True)
    text_font(mb, "INSPECTED", 0.0062, 0.0002, "cable", Mt @ _T(0, -0.03, 0.0003), font="sign", bold=True, res=2)
    for k in range(4):
        slab(mb, Mt @ _T(0, -0.045 - k * 0.009, 0.0003), 0.036, 0.0008, 0.0002, rc=0.0002, re=0.0, mat="cable", nc=1, ne=1, re0=0.0)
    del zt
    return mb
