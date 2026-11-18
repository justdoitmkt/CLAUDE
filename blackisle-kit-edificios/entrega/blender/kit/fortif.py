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
Cilindros visibles >= 24 lados; tubos/cables >= 14 (el kit suaviza a 30°). Excepción documentada: los alambres de 4 mm de la
malla HESCO y la bobina de sus juntas van de 4 y 3 lados (presupuesto de 3,5 k tris por celda).
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
    res = bmesh.ops.triangulate(mb.bm, faces=[f], quad_method="BEAUTY", ngon_method="BEAUTY")
    for g in res["faces"]:
        g.smooth = smooth
    return res["faces"]


def bar4(mb, p0, p1, r, side, mat="galvanized", cap0=True, cap1=True):
    """Alambre recto de 4 lados (sección en rombo: un vértice hacia `side`, otro hacia dir × side). 8 tris + tapas."""
    p0, p1 = _v(p0), _v(p1)
    d = (p1 - p0).normalized()
    s = _v(side)
    s = (s - d * s.dot(d)).normalized()
    n = d.cross(s)
    offs = [s * r, n * r, -s * r, -n * r]
    A = [mb.bm.verts.new(p0 + o) for o in offs]
    B = [mb.bm.verts.new(p1 + o) for o in offs]
    for k in range(4):
        kk = (k + 1) % 4
        mb.face([A[k], A[kk], B[kk], B[k]], mat)
    if cap0:
        mb.face(list(reversed(A)), mat)
    if cap1:
        mb.face(B, mat)


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


def _smooth1d(a, k=1, it=1):
    a = np.asarray(a, float)
    for _ in range(it):
        b = a.copy()
        b[1:-1] = (a[:-2] + a[1:-1] + a[2:]) / 3.0
        a = b
    return a


# ============================================================================================================ HESCO
# HESCO / Concertainer MIL (fuentes: hesco.com vía tabla de dimensiones nominales MIL1 54"×42", MIL7 87"×84", MIL8 54"×48";
# malla soldada 75 × 75 mm (3") de alambre de 4 mm Alu-Zinc / Galfan, bisagras de espiral y pasadores de unión de 4 mm, liner
# de geotextil no tejido de polipropileno gris/arena). Celdas cuadradas: largo de celda = ancho del muro.
HESCO = {"MIL1": (1.37, 1.06), "MIL7": (2.21, 2.13), "MIL8": (1.37, 1.22)}
HW_R = 0.002          # radio del alambre de la malla (4 mm)
H_MESH = 0.0762       # paso nominal de la malla (3")
H_EDGE = 0.005        # alambre vertical de orilla: a 5 mm del eje de la bobina
H_COIL_R = 0.011      # radio de la línea central de la bobina de unión
H_LIN_D = 2 * HW_R + 0.0006   # el liner apoya detrás de la capa interior de alambres
H_LIN_T = 0.003       # espesor del geotextil
H_CORNER_R = 0.032    # radio de la esquina del liner (queda por fuera de la bobina)


def _hesco_panel_frame(O, U, N):
    """Matriz del panel: x local = u (a lo largo), y local = profundidad (+ hacia afuera, N), z = altura."""
    O, U, N = _v(O), _v(U), _v(N)
    return Matrix(((U.x, N.x, 0, O.x), (U.y, N.y, 0, O.y), (U.z, N.z, 1, O.z), (0, 0, 0, 1)))


def _hesco_mesh(mb, M, c, H, us, vs, vmin=None, h_ext=(-0.001, -0.001)):
    """Malla soldada de un panel (coordenadas de panel: u 0..c, profundidad y, altura z). Verticales en la capa exterior
    (+HW_R), horizontales en la interior (-HW_R), soldadas una sobre otra. vmin: solo la parte de arriba (divisiones).
    h_ext: cuánto rebasan (o no llegan, si es negativo) los horizontales a los verticales de orilla, en cada extremo: las
    puntas de los paneles vecinos quedan dentro de la bobina sin tocarse."""
    lay_v, lay_h = HW_R, -HW_R
    z0 = -0.02 if vmin is None else vmin
    X = M.to_3x3() @ Vector((1, 0, 0))
    Y = M.to_3x3() @ Vector((0, 1, 0))
    for u in us:
        bar4(mb, M @ Vector((u, lay_v, z0)), M @ Vector((u, lay_v, H + 0.006)), HW_R, X, cap0=vmin is not None)
    for v in vs:
        if vmin is not None and v < vmin + 0.01:
            continue
        bar4(mb, M @ Vector((us[0] - h_ext[0], lay_h, v)), M @ Vector((us[-1] + h_ext[1], lay_h, v)), HW_R, Y, cap0=False, cap1=False)


def _hesco_coil(mb, axis_xy, H, vs, quad, pitch, phase=0.19):
    """Bisagra de espiral (alambre de 4 mm, 3 lados, 4 puntos por vuelta girados 45°) + pasador de unión con gancho.
    quad = ángulo (rad) de la dirección 'hacia afuera' de la junta; la fase evita los alambres horizontales."""
    x, y = axis_xy
    z0 = vs[0] + phase * pitch
    turns = int((H - 0.01 - z0) / pitch)
    pts = []
    Rk = H_COIL_R / math.cos(PI / 4)
    for k in range(turns * 4 + 1):
        a = quad + PI / 4 + k * PI / 2
        pts.append((x + Rk * math.cos(a), y + Rk * math.sin(a), z0 + pitch * k / 4))
    mb.tube(pts, HW_R, seg=3, mat="galvanized", caps=True)
    # pasador: varilla de 6 mm con la punta doblada en gancho sobre la orilla superior
    hook = [(x, y, 0.02), (x, y, H + 0.035), (x + 0.025 * math.cos(quad), y + 0.025 * math.sin(quad), H + 0.05),
            (x + 0.045 * math.cos(quad), y + 0.045 * math.sin(quad), H + 0.02)]
    mb.tube(fillet(hook, 0.012, 2), 0.003, seg=4, mat="galvanized", caps=True)


def hesco_run(n=5, kind="MIL1", seed=0):
    """Línea de n celdas de muro HESCO MIL (MIL1 1,37 × 1,06; MIL7 2,21 × 2,13; MIL8 1,37 × 1,22 m) a lo largo de +X desde
    x = 0; cara exterior en -Y, muro centrado en y = 0 (ancho W). Construcción: malla soldada de 76,2 mm con alambres de 4 mm
    de geometría real (verticales por fuera, horizontales por dentro), bisagra de espiral + pasador con gancho en cada esquina,
    liner de geotextil de 3 mm con esquinas redondeadas por dentro de la bobina que asoma acolchado entre los alambres (el
    relleno lo empuja; el abombado crece hacia el centro de cada cara), liner flojo y ondulado arriba del relleno, y tapón de
    tierra compactada con corona en cada celda. Presupuesto: <= 3,5 k tris por celda MIL1, <= 6 k por celda MIL7."""
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
    # región acolchada (central) de cada cara: el borde queda plano y se triangula en abanico
    qa = (ncol - (12 if big else 8)) // 2
    qb = ncol - qa
    ja, jb = (4, nrow - 9) if big else (2, nrow - 4)
    L = n * c
    # paredes exteriores: frente (-Y), fondo (+Y) por celda; extremos en x = 0 y x = L
    walls = []
    for i in range(n):
        walls.append(("f", i, (i * c, -W / 2, 0), (1, 0, 0), (0, -1, 0)))
        walls.append(("b", i, ((i + 1) * c, W / 2, 0), (-1, 0, 0), (0, 1, 0)))
    walls.append(("e0", 0, (0, W / 2, 0), (0, -1, 0), (-1, 0, 0)))
    walls.append(("e1", n - 1, (L, -W / 2, 0), (0, 1, 0), (1, 0, 0)))
    fills = [float(H - 0.075 + r.uniform(-0.02, 0.012)) for _ in range(n)]
    # ---------------------------------------------------------------- malla de alambre
    for (tag, i, O, U, N) in walls:
        _hesco_mesh(mb, _hesco_panel_frame(O, U, N), c, H, us, vs, h_ext=(-0.003, -0.003) if tag[0] == "e" else (0.001, 0.001))
    us_d = [0.006 + (c - 0.012) * k / ncol for k in range(ncol + 1)]
    for i in range(1, n):                                  # divisiones: solo asoman arriba del relleno
        M = _hesco_panel_frame((i * c, -W / 2, 0), (0, 1, 0), (1, 0, 0))
        _hesco_mesh(mb, M, c, H, us_d, vs, vmin=min(fills[i - 1], fills[i]) - 0.03, h_ext=(0.0, 0.0))
    # ---------------------------------------------------------------- bobinas + pasadores (4 por celda de esquina, 2 por junta)
    for i in range(n + 1):
        x = i * c
        _hesco_coil(mb, (x, -W / 2), H, vs, -PI / 2 if 0 < i < n else (-3 * PI / 4 if i == 0 else -PI / 4), pitch)
        _hesco_coil(mb, (x, W / 2), H, vs, PI / 2 if 0 < i < n else (3 * PI / 4 if i == 0 else PI / 4), pitch)
    # ---------------------------------------------------------------- liner + relleno por celda
    for i in range(n):
        _hesco_cell_liner(mb, i, c, W, H, us, vs, fills[i], (qa, qb, ja, jb), r, ends=(i == 0, i == n - 1))
    return mb


def _hesco_cell_liner(mb, i, c, W, H, us, vs, zf, quilt, r, ends=(False, False)):
    """Liner de una celda: lazo en planta (4 paredes rectas + 4 esquinas redondeadas) con su cara exterior completa, cara
    interior y canto superior solo arriba del relleno; acolchado entre alambres en las caras a la vista; tapón de relleno."""
    qa, qb, ja, jb = quilt
    x0 = i * c
    d0 = H_LIN_D
    t = H_LIN_T
    Rc = H_CORNER_R
    amp = float(r.uniform(0.8, 1.15))
    v0l = -0.02
    v1l = H - 0.016
    ph = float(r.uniform(0, 100))
    zin = zf - 0.03
    # paredes: (origen de la esquina inicial, dirección U, normal N hacia afuera, ¿cara expuesta?)
    exposed = {0: True, 1: ends[1], 2: True, 3: ends[0]}   # 0 frente, 1 lado +x, 2 fondo, 3 lado -x
    corners = [(x0, -W / 2), (x0 + c, -W / 2), (x0 + c, W / 2), (x0, W / 2)]
    dirs = [Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((-1, 0, 0)), Vector((0, -1, 0))]
    nors = [Vector((0, -1, 0)), Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((-1, 0, 0))]
    s0 = Rc + d0                                           # la parte recta empieza tras la esquina redondeada
    rows_full = [v0l] + [v for v in vs[:-1]] + [v1l]
    outer_cols = []                                        # por pared: lista de columnas (cada una lista de vértices de abajo arriba)
    inner_rows = []                                        # por pared: (verts superiores exteriores, interiores arriba, interiores abajo)

    def P(w, u, depth, z):
        C = Vector((corners[w][0], corners[w][1], 0.0))
        return C + dirs[w] * u + nors[w] * depth + Vector((0, 0, z))

    def top_wave(w, u):
        return 0.009 * noise.noise(Vector((u * 7.0 + w * 3.1, ph, 0.3))) - 0.003

    for w in range(4):
        ex = exposed[w]
        ucols = [s0] + [u for u in us[1:-1] if s0 + 0.01 < u < c - s0 - 0.01] + [c - s0]
        if not ex:
            ucols = [s0 + (c - 2 * s0) * k / 4 for k in range(5)]

        def V(u, z, w=w):
            zz, dd = z, -d0
            if z == v1l:                                   # orilla del liner floja: ondula y se ladea hacia adentro
                edge = min(1.0, min(u - s0, c - s0 - u) / 0.12)
                zz = z + top_wave(w, u) * edge
                dd = -d0 - 0.012 * edge * (0.45 + 0.55 * noise.noise(Vector((u * 4.0, ph, w))))
            return mb.bm.verts.new(P(w, u, dd, zz))
        if ex:
            ka = ucols.index(us[qa])
            kb = ucols.index(us[qb])
            qrows = vs[ja:jb + 1]
            # cuadro acolchado: rejilla en los cruces + un vértice central por abertura empujado por el relleno
            Q = [[V(u, z) for u in ucols[ka:kb + 1]] for z in qrows]
            for j in range(len(qrows) - 1):
                for k in range(kb - ka):
                    q = [Q[j][k], Q[j][k + 1], Q[j + 1][k + 1], Q[j + 1][k]]
                    uc = (ucols[ka + k] + ucols[ka + k + 1]) / 2
                    zc = (qrows[j] + qrows[j + 1]) / 2
                    eu = math.sin(PI * (uc - ucols[ka]) / (ucols[kb] - ucols[ka])) ** 0.6
                    ev = math.sin(PI * (zc - qrows[0]) / (qrows[-1] - qrows[0])) ** 0.6
                    e = min(1.0, eu * ev * amp * (0.85 + 0.3 * (0.5 + 0.5 * noise.noise(Vector((uc * 7.0, zc * 7.0, ph + w))))))
                    if zc > zf - 0.02:
                        e *= max(0.0, 1.0 - (zc - zf + 0.02) / 0.05)
                    cv = mb.bm.verts.new(P(w, uc, -d0 + e * (d0 + 0.0055), zc))
                    for a_, b_ in ((q[0], q[1]), (q[1], q[2]), (q[2], q[3]), (q[3], q[0])):
                        mb.face([a_, b_, cv], "geotextile").smooth = True
            # franja superior (de la orilla del acolchado a la orilla del liner) a todo lo ancho; bordes planos (abajo,
            # izquierda, derecha) triangulados entre cadenas: sin uniones en T ni triángulos degenerados
            band0 = [V(ucols[0], qrows[-1])] + Q[-1] + [V(ucols[-1], qrows[-1])]
            band1 = [V(u, v1l) for u in ucols]
            zip_chains(mb, band0, band1, "geotextile")
            BL, BR = V(ucols[0], v0l), V(ucols[-1], v0l)
            QBL, QBR = V(ucols[ka], v0l), V(ucols[kb], v0l)
            zip_chains(mb, [QBL, QBR], Q[0], "geotextile")
            zip_chains(mb, [BL, band0[0]], [QBL] + [Q[j][0] for j in range(len(qrows))], "geotextile")
            zip_chains(mb, [QBR] + [Q[j][-1] for j in range(len(qrows))], [BR, band0[-1]], "geotextile")
            G = [[BL, band0[0], band1[0]], [BR, band0[-1], band1[-1]]]
            outer_cols.append((G[0], G[1]))
            top_o = band1
        else:
            rows = [v0l, zin, v1l]
            G = [[V(u, z) for u in ucols] for z in rows]
            grid_faces(mb, G, "geotextile")
            outer_cols.append(([G[j][0] for j in range(3)], [G[j][-1] for j in range(3)]))
            top_o = G[-1]
        # cara interior arriba del relleno y canto superior
        ti = [mb.bm.verts.new(v.co - nors[w] * t) for v in top_o]
        bi = [mb.bm.verts.new(P(w, ucols[k], -d0 - t, zin)) for k in range(len(ucols))]
        grid_faces(mb, [top_o, ti], "geotextile", flip=True)
        grid_faces(mb, [bi, ti], "geotextile", flip=True)
        inner_rows.append((top_o, ti, bi))
    # esquinas redondeadas (columnas de 2 filas: piso y orilla) cosidas con zip a las columnas de las paredes
    for w in range(4):
        wn = (w + 1) % 4
        endcol = outer_cols[w][1]
        startcol = outer_cols[wn][0]
        C = Vector((corners[wn][0], corners[wn][1], 0.0))
        ctr = C - dirs[w] * s0 + dirs[wn] * s0             # centro del arco (dirs[wn] = hacia adentro de la pared w)
        cols = []
        for k in (1, 2):
            a = k / 3 * (PI / 2)
            pdir = (nors[w] * math.cos(a) + dirs[w] * math.sin(a))
            p = ctr + pdir * Rc
            cols.append([mb.bm.verts.new(Vector((p.x, p.y, v0l))), mb.bm.verts.new(Vector((p.x, p.y, v1l)))])
        zip_chains(mb, endcol, cols[0], "geotextile")
        grid_faces(mb, [[cols[0][0], cols[1][0]], [cols[0][1], cols[1][1]]], "geotextile")
        zip_chains(mb, cols[1], startcol, "geotextile")
        # interior y canto en la esquina (arriba del relleno)
        to_a, ti_a, bi_a = inner_rows[w]
        to_b, ti_b, bi_b = inner_rows[wn]
        ci_t, ci_b = [], []
        for k in (1, 2):
            a = k / 3 * (PI / 2)
            pdir = (nors[w] * math.cos(a) + dirs[w] * math.sin(a))
            p = ctr + pdir * (Rc - t)
            ci_t.append(mb.bm.verts.new(Vector((p.x, p.y, v1l))))
            ci_b.append(mb.bm.verts.new(Vector((p.x, p.y, zin))))
        ot = [to_a[-1], cols[0][1], cols[1][1], to_b[0]]
        it = [ti_a[-1]] + ci_t + [ti_b[0]]
        ib = [bi_a[-1]] + ci_b + [bi_b[0]]
        grid_faces(mb, [ot, it], "geotextile", flip=True)
        grid_faces(mb, [ib, it], "geotextile", flip=True)
    # tapón de relleno: domo de tierra compactada que muere dentro del espesor del liner + faldón + fondo (sólido cerrado)
    din = d0 + t * 0.5
    ring = []
    for w in range(4):
        nk = 6 if c > 1.5 else 4
        for k in range(nk):
            u = s0 + (c - 2 * s0) * k / nk
            ring.append(P(w, u, -din, 0.0))
        wn = (w + 1) % 4
        C = Vector((corners[wn][0], corners[wn][1], 0.0))
        ctr = C - dirs[w] * s0 + dirs[wn] * s0
        for k in (1, 2):
            a = k / 3 * (PI / 2)
            ring.append(ctr + (nors[w] * math.cos(a) + dirs[w] * math.sin(a)) * (Rc - t * 0.5))
    cx, cy = x0 + c / 2, 0.0
    mound = float(r.uniform(0.03, 0.05)) * (c / 1.06) ** 0.5
    loops = []
    for sc in (1.0, 0.88, 0.72, 0.54, 0.34, 0.15):
        L = []
        for p in ring:
            dx, dy = p.x - cx, p.y - cy
            rr_ = math.hypot(dx, dy) or 1.0
            rnd = (1 - sc) ** 0.7                          # curvas de nivel cada vez más redondas hacia la corona
            k_ = (1 - rnd) + rnd * (c * 0.47) / rr_
            x = cx + dx * sc * k_
            y = cy + dy * sc * k_
            z = zf + mound * (1 - sc ** 2) + 0.018 * noise.noise(Vector((x * 4, y * 4, ph))) * (1 - sc ** 4) \
                + 0.006 * noise.noise(Vector((x * 13, y * 13, ph + 3))) * (1 - sc ** 2)
            if sc == 1.0:
                z = zf + 0.004 * noise.noise(Vector((x * 6, y * 6, ph)))
            L.append((x, y, z))
        loops.append(L)
    loops.append([(cx, cy, zf + mound * 1.0 + 0.01 * noise.noise(Vector((cx * 5, 0.0, ph))))])
    skirt = [(p[0], p[1], zf - 0.06) for p in loops[0]]
    skin(mb, [skirt] + loops, "sand", cap0=True, cap1=False)


# ========================================================================================================== sacos
# Saco terrero de polipropileno tejido: vacío 14" × 26" (36 × 66 cm) según catálogos (webstaurantstore 14x26, sandbaggy.com:
# lleno ~ 12" × 18" × 3,5-4"); FM 5-103 / práctica de campo: lleno a 2/3-3/4, extremo amarrado doblado debajo, juntas
# cuatrapeadas, hiladas de soga y tizón alternadas en muros dobles. Lleno: ~ 0,48 × 0,30 × 0,11 m.
BAG_N = 14            # puntos por anillo (sección superelíptica)


def _bag_rings(r, ls=1.0, ws=1.0, hs=1.0, blunt=0.0, lod=0):
    """Anillos (lista de [Vector] locales) de un saco lleno: largo en X (costura cosida en -X, boca amarrada y doblada en +X),
    ancho en Y, base en z = 0. Devuelve (anillos, fracción de altura por vértice)."""
    a = 0.24 * ls * float(r.uniform(0.96, 1.04))
    b0 = 0.152 * ws * float(r.uniform(0.95, 1.05))
    c0 = 0.054 * hs * float(r.uniform(0.92, 1.06))
    e = float(r.uniform(2.2, 2.6))                         # costados redondos
    et = float(r.uniform(2.5, 2.9))                        # tapa algo aplanada por la carga
    eb = 3.2                                               # base aplanada sobre el apoyo
    bend = float(r.uniform(-0.012, 0.012))                 # saco ligeramente curvo en planta
    tilt = float(r.uniform(-0.15, 0.15))                   # el relleno se carga hacia un costado
    ph = float(r.uniform(0, 50))
    stations = []                                          # (x, b, c, gathers)

    def g(t):
        t = min(max(t, 0.0), 1.0)
        return math.sqrt(max(0.0, 1 - (1 - t) ** 2))
    stations.append((-a - 0.017, 0.86 * b0, 0.0022, 0.0))  # orilla de la costura (dobladillo cosido)
    stations.append((-a - 0.005, 0.93 * b0, 0.0034, 0.0))
    NR = BAG_N if lod == 0 else 10
    for s in ((0.0, 0.05, 0.14, 0.3, 0.5, 0.7, 0.86, 0.965) if lod == 0 else (0.0, 0.08, 0.25, 0.5, 0.75, 0.94)):
        x = -a + 2 * a * s
        te = 0.2 - 0.08 * blunt                            # en un muro los extremos se aprietan unos contra otros
        cs = c0 * max(g(s / te), 0.1) * g((1.0 - s) / (0.3 - 0.1 * blunt) + 0.18 + 0.2 * blunt)
        cs *= 1 + 0.05 * noise.noise(Vector((s * 4, ph, 0.0)))
        bs = b0 * (0.94 + 0.06 * math.sin(PI * s) ** 0.5) * (1 - 0.18 * max(0.0, (s - 0.8) / 0.2) ** 1.5)
        if s == 0.0:
            cs = 0.006
        stations.append((x, bs, cs, max(0.0, (s - 0.62) / 0.38)))
    rings, fr = [], []
    for (x, bs, cs, gth) in stations:
        ring = []
        zc = cs
        for k in range(NR):
            phi = 2 * PI * (k + 0.5) / NR
            cp, sp = math.cos(phi), math.sin(phi)
            y = bs * math.copysign(abs(cp) ** (2 / e), cp)
            z = cs * math.copysign(abs(sp) ** (2 / (et if sp > 0 else eb)), sp)
            if z > 0:                                      # carga: la tapa se aplana y se ladea
                z *= 1 + tilt * y / max(bs, 1e-4) * 0.5
            lump = 0.0035 * noise.noise(Vector((k * 0.55, x * 7.0, ph + 2.0))) * min(1.0, cs / max(c0, 1e-4)) \
                * min(1.0, max(0.0, (sp + 0.45) / 0.45))      # la base apoyada no se despega del suelo
            y += cp * lump                                 # terrones de arena y pliegues blandos de la tela
            z += sp * lump
            if gth > 0:                                    # frunces que convergen hacia la boca amarrada
                kk = 0.0045 * gth * (1 if k % 2 else -1) * (0.6 + 0.4 * noise.noise(Vector((k * 0.7, ph, x * 9))))
                nrm = Vector((0, cp, sp)).normalized()
                y += nrm.y * kk
                z += nrm.z * kk * 0.6
            xx = x + bend * (1 - (x / a) ** 2) * 0 + 0.002 * noise.noise(Vector((k * 0.9, x * 11, ph)))
            yy = y + bend * (1 - min(1.0, (x / a) ** 2))
            ring.append(Vector((xx, yy, zc + z)))
        rings.append(ring)
        fr.append([min(1.0, max(0.0, (p.z) / max(2 * cs, 1e-4))) for p in ring])
    # boca amarrada: el sobrante se junta y se dobla hacia abajo contra la cabeza del saco (pestaña de 2 capas)
    cl = stations[-1][2]
    path = [(a + 0.004, 0.0, 1.55 * cl + 0.006), (a + 0.026, 0.0, 1.05 * cl), (a + 0.034, 0.0, 0.45 * cl), (a + 0.03, 0.0, 0.012)]
    tans = [Vector((1, 0, -0.3)), Vector((0.55, 0, -1)), Vector((0.05, 0, -1)), Vector((-0.25, 0, -1))]
    widths = [0.5 * b0, 0.56 * b0, 0.5 * b0, 0.36 * b0]
    if lod:
        path, tans, widths = [path[0], path[2], path[3]], [tans[0], tans[2], tans[3]], [widths[0], widths[2], widths[3]]
    for (p, tg, wb) in zip(path, tans, widths):
        tg = tg.normalized()
        U = Vector((0, 1, 0))
        Vn = tg.cross(U).normalized()
        ring = []
        for k in range(NR):
            phi = 2 * PI * (k + 0.5) / NR
            cp, sp = math.cos(phi), math.sin(phi)
            y = wb * math.copysign(abs(cp) ** 0.8, cp)
            t = 0.0032 * math.copysign(abs(sp) ** 0.8, sp)
            ring.append(Vector(p) + U * (y + bend * 0.0) + Vn * t + Vector((0, 0, 0.0015 * (1 if k % 2 else -1))))
        rings.append(ring)
        fr.append([0.5] * NR)
    return rings, fr


def _bag_build(mb, rings, M=None, zfun=None, fr=None):
    """Malla del saco a partir de sus anillos; M coloca el saco, zfun(x, y, f) -> desplazamiento z por vértice (asiento)."""
    out = []
    for i, ring in enumerate(rings):
        row = []
        for k, p in enumerate(ring):
            q = (M @ p) if M is not None else p.copy()
            if zfun is not None:
                q.z += zfun(q.x, q.y, fr[i][k])
            row.append(q)
        out.append(row)
    V = [[mb.bm.verts.new(q) for q in row] for row in out]
    nr = len(V[0])
    for i in range(len(V) - 1):
        A, B = V[i], V[i + 1]
        for k in range(nr):
            kk = (k + 1) % nr
            mb.face([A[k], A[kk], B[kk], B[k]], "sandbag").smooth = True
    ngon(mb, list(reversed(V[0])), "sandbag")
    ngon(mb, V[-1], "sandbag")
    return out


def sandbag(seed=0):
    """Saco terrero lleno suelto (~0,48 × 0,30 × 0,11 m + costura y pestaña): polipropileno tejido relleno a 3/4, sección
    superelíptica aplastada por la carga (tapa plana, costados redondos), extremos de almohada, dobladillo cosido de 1,7 cm en
    -X, boca amarrada con frunces que convergen y pestaña doblada hacia abajo en +X. Origen: centro de la base, largo en X."""
    r = rng(seed)
    mb = MB()
    rings, fr = _bag_rings(r)
    _bag_build(mb, rings)
    return mb


class _HField:
    """Campo de alturas (máximo de las tapas de los sacos ya puestos) para asentar cada hilada sobre la anterior."""

    def __init__(self, x0, x1, y0, y1, h=0.01):
        self.x0, self.y0, self.h = x0, y0, h
        self.nx = int(math.ceil((x1 - x0) / h)) + 1
        self.ny = int(math.ceil((y1 - y0) / h)) + 1
        self.H = np.zeros((self.ny, self.nx))

    def raster(self, tris):
        """tris: lista de (p0, p1, p2) Vector; levanta H con la tapa de cada triángulo que mira hacia arriba."""
        H, h = self.H, self.h
        for (a, b, c) in tris:
            n = (b - a).cross(c - a)
            if n.z <= 1e-12:
                continue
            xs = (a.x, b.x, c.x)
            ys = (a.y, b.y, c.y)
            i0 = max(0, int((min(xs) - self.x0) / h))
            i1 = min(self.nx - 1, int((max(xs) - self.x0) / h) + 1)
            j0 = max(0, int((min(ys) - self.y0) / h))
            j1 = min(self.ny - 1, int((max(ys) - self.y0) / h) + 1)
            if i1 < i0 or j1 < j0:
                continue
            X, Y = np.meshgrid(self.x0 + h * np.arange(i0, i1 + 1), self.y0 + h * np.arange(j0, j1 + 1))
            det = (b.y - c.y) * (a.x - c.x) + (c.x - b.x) * (a.y - c.y)
            if abs(det) < 1e-14:
                continue
            l1 = ((b.y - c.y) * (X - c.x) + (c.x - b.x) * (Y - c.y)) / det
            l2 = ((c.y - a.y) * (X - c.x) + (a.x - c.x) * (Y - c.y)) / det
            l3 = 1 - l1 - l2
            m = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
            Z = l1 * a.z + l2 * b.z + l3 * c.z
            sub = H[j0:j1 + 1, i0:i1 + 1]
            H[j0:j1 + 1, i0:i1 + 1] = np.where(m, np.maximum(sub, Z), sub)

    def filtered(self, rmax=4, sigma=6):
        """(S1, S2): máximo local (radio rmax celdas) + holgura, y su versión desenfocada (gaussiana sigma celdas)."""
        H = self.H
        S1 = H.copy()
        for dj in range(-rmax, rmax + 1):
            for di in range(-rmax, rmax + 1):
                if di * di + dj * dj <= rmax * rmax:
                    S1 = np.maximum(S1, np.roll(np.roll(H, dj, 0), di, 1))
        def blur(A, sg):
            k = np.exp(-0.5 * (np.arange(-3 * sg, 3 * sg + 1) / sg) ** 2)
            k /= k.sum()
            B = np.apply_along_axis(lambda v: np.convolve(np.pad(v, 3 * sg, mode="edge"), k, "valid"), 1, A)
            return np.apply_along_axis(lambda v: np.convolve(np.pad(v, 3 * sg, mode="edge"), k, "valid"), 0, B)
        S1 = np.maximum(blur(S1, 2), H)
        return S1, blur(S1, sigma)

    def sample(self, A, x, y):
        fx = min(max((x - self.x0) / self.h, 0.0), self.nx - 1.001)
        fy = min(max((y - self.y0) / self.h, 0.0), self.ny - 1.001)
        i, j = int(fx), int(fy)
        tx, ty = fx - i, fy - j
        return (A[j, i] * (1 - tx) * (1 - ty) + A[j, i + 1] * tx * (1 - ty) + A[j + 1, i] * (1 - tx) * ty
                + A[j + 1, i + 1] * tx * ty)


def _bag_stack(courses, seed, bounds, hs_course=None, lod=0):
    """Apila hiladas de sacos: courses = [[(x, y, ángulo°, escala_largo, escala_ancho), ...], ...] de abajo hacia arriba.
    Cada saco se asienta sobre los de la hilada anterior (campo de alturas: la base sigue los lomos y se hunde en las
    juntas, la tapa sigue un promedio suave) sin interpenetrarse; cada saco es distinto (semilla propia)."""
    r = rng(seed)
    mb = MB()
    hf = _HField(*bounds)
    for ci, course in enumerate(courses):
        S1, S2 = hf.filtered()
        S1 = S1 + (0.003 if ci else 0.0)
        S2 = S2 + (0.003 if ci else 0.0)
        new_tris = []
        nc = len(courses)
        for (x, y, ang, ls, ws) in course:
            rb = rng(int(r.integers(1 << 30)))
            hs = 1.0 - 0.06 * (nc - 1 - ci) / max(nc - 1, 1)     # las hiladas de abajo cargan más: más aplastadas
            rings, fr = _bag_rings(rb, ls, ws, hs, blunt=1.0, lod=lod)
            M = _T(x, y, 0.0) @ _Rz(ang + float(rb.uniform(-2.5, 2.5)))

            def zf(px, py, f, S1=S1, S2=S2):
                s1 = hf.sample(S1, px, py)
                s2 = hf.sample(S2, px, py)
                w_ = f ** 0.7
                top = s2 + 0.3 * (s1 - s2)
                return s1 * (1 - w_) + max(top, s1 - 0.018) * w_
            pts = _bag_build(mb, rings, M, zf, fr)
            n_r = len(pts)
            nk = len(pts[0])
            for i in range(n_r - 1):
                for k in range(nk):
                    kk = (k + 1) % nk
                    new_tris.append((pts[i][k], pts[i][kk], pts[i + 1][kk]))
                    new_tris.append((pts[i][k], pts[i + 1][kk], pts[i + 1][k]))
        hf.raster(new_tris)
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
                row.append((p * (i + 0.5), 0.0, 90.0 + (180.0 if (i + k) % 2 else 0.0), 1.2, 0.97 * p / 0.315))
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
                    row.append(((u0 + u1) / 2, y, flip, ls, 0.9 if thickness == "double" else 1.0))
        courses.append(row)
    return _bag_stack(courses, seed, (-0.4, L + 0.4, -0.5, 0.5))


def sandbag_ring(radius=1.1, rows=3, seed=0, opening_deg=50.0):
    """Anillo de sacos (puesto de tirador / protección de un equipo): sacos a soga tangentes a un círculo de `radius` m
    (eje del muro), hiladas cuatrapeadas, con una entrada de `opening_deg` grados hacia -Y. Origen: centro, en el piso."""
    courses = []
    pitch = 0.515
    for k in range(rows):
        arc0 = -PI / 2 + math.radians(opening_deg) / 2
        arc = 2 * PI - math.radians(opening_deg)
        n = max(3, int(round(arc * radius / pitch)))
        da = arc / n
        row = []
        off = 0.5 * (k % 2)
        idx = [i + off for i in range(n)] if not off else [i + off for i in range(n - 1)]
        for t in idx:
            a = arc0 + da * (t + 0.5)
            row.append((radius * math.cos(a), radius * math.sin(a), math.degrees(a) + 90.0, 1.0, 1.0))
        if off:                                            # medios sacos en las cabezas de la entrada
            for t in (0.25, n - 0.25):
                a = arc0 + da * t
                row.append((radius * math.cos(a), radius * math.sin(a), math.degrees(a) + 90.0, 0.5, 1.0))
        courses.append(row)
    R = radius + 0.5
    return _bag_stack(courses, seed, (-R, R, -R, R))


# ================================================================================================ barreras de concreto
def _offset_loop(pts, d):
    """Desplaza un lazo 2D antihorario (y, z) hacia adentro `d` (inglete): chaflán de los extremos de una pieza colada."""
    n = len(pts)
    out = []
    for i in range(n):
        p0, p1, p2 = Vector((*pts[i - 1], 0)), Vector((*pts[i], 0)), Vector((*pts[(i + 1) % n], 0))
        e0 = (p1 - p0).normalized()
        e1 = (p2 - p1).normalized()
        n0 = Vector((-e0.y, e0.x, 0))
        n1 = Vector((-e1.y, e1.x, 0))
        m = (n0 + n1)
        m = m.normalized() if m.length > 1e-6 else n0
        c = max(m.dot(n0), 0.35)
        q = p1 + m * (d / c)
        out.append((q.x, q.y))
    return out


def _prof_extrude(mb, stations, mat="concrete"):
    """Sólido colado por estaciones a lo largo de X: cada estación = (x, cadena derecha [(y, z)] de abajo arriba, cadena
    izquierda de abajo arriba), mismas cuentas en todas. Tapas por zip entre las dos cadenas (sección horizontalmente
    convexa: T invertida, perfil New Jersey): sin n-gonos cóncavos ni triángulos degenerados."""
    rings = []
    for (x, R, Lf) in stations:
        loop = [(x, y, z) for (y, z) in R] + [(x, y, z) for (y, z) in reversed(Lf)]
        rings.append([mb.bm.verts.new(Vector(p)) for p in loop])
    k = len(rings[0])
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        for j in range(k):
            jj = (j + 1) % k
            mb.face([A[j], B[j], B[jj], A[jj]], mat)
    nR = len(stations[0][1])
    for idx, flip in ((0, False), (-1, True)):
        ring = rings[idx]
        R = ring[:nR]
        Lf = list(reversed(ring[nR:]))
        zip_chains(mb, R, Lf, mat, flip=flip)
    return rings


def _chip_set(r, zs, n, lo, hi):
    """Alturas de despostilladuras pequeñas (n) sobre una arista vertical, entre lo y hi."""
    return sorted(float(z) for z in r.uniform(lo, hi, n)) if n else []


def t_wall(seed=0):
    """Muro T (T-wall / tipo Alaska) de concreto precolado: 3,66 m (12 ft) de alto, segmento de 1,52 m (5 ft) a lo largo de +X
    desde x = 0, base en T invertida de 1,37 m (4,5 ft) de fondo centrada en y = 0 (frente en -Y). Alma ahusada 0,30 -> 0,20 m,
    acartelamiento de la base a 22°, chaflanes de 15-20 mm en todas las aristas, juntas de cimbra (ranuras horizontales de
    3 mm), dos asas de izaje de varilla de 7/8" en la corona y algunas despostilladuras chicas en las aristas de los extremos.
    Fuentes: globalsecurity.org (2007: "T barrier ... 12 feet high ... four and a half feet wide ... ~10,000 lb"); peso del
    modelo ~2,0 m³ × 2400 kg/m³ = 4,8 t (10 600 lb)."""
    r = rng(seed)
    mb = MB()
    L, H = 1.52, 3.66
    hb, hy = 0.685, 0.20
    ch = 0.018
    grooves = [1.22 + float(r.uniform(-0.01, 0.01)), 2.44 + float(r.uniform(-0.01, 0.01))]
    chips = _chip_set(r, None, 3, 0.7, 3.4)
    zs = [0.52]
    for z in [0.9, 1.5, 2.0, 2.9, 3.3] + chips:
        zs.append(z)
    for g in grooves:
        zs += [g - 0.005, g, g + 0.005]
    zs = sorted(set(round(z, 4) for z in zs))

    def stem_y(z):
        return 0.15 - 0.05 * (z - 0.5) / (H - 0.5)

    def right_chain(chip=None):
        R = [(hb - ch * 0.6, 0.0), (hb, ch * 0.6), (hb, hy - ch), (hb - ch, hy + ch * 0.45)]
        R += [(0.17, 0.417), (stem_y(0.47) + 0.004, 0.462)]
        for z in zs:
            y = stem_y(z)
            if any(abs(z - g) < 1e-4 for g in grooves):
                y -= 0.003
            if chip and z in chip:
                y -= chip[z]
            R.append((y, z))
        R += [(stem_y(H) , H - ch), (stem_y(H) - ch, H)]
        return R
    # despostilladuras: (lado, estación extremo, {z: profundidad}) -> en las 4 aristas verticales de los extremos
    chipmap = {}
    for z in chips:
        key = (int(r.integers(2)), int(r.integers(2)))
        chipmap.setdefault(key, {})[round(z, 4)] = float(r.uniform(0.006, 0.014))
    stations = []
    for (x, end) in ((0.0, 0), (ch, 0), (L - ch, 1), (L, 1)):
        R = right_chain(chipmap.get((0, end)))
        Lf = [(-y, z) for (y, z) in right_chain(chipmap.get((1, end)))]
        if x in (0.0, L):                                  # chaflán del extremo: perfil desplazado hacia adentro
            loop = R + list(reversed(Lf))
            off = _offset_loop(loop, ch)
            off = [(y, max(z, 0.0)) for (y, z) in off]
            n = len(R)
            R, Lf = off[:n], list(reversed(off[n:]))
            R[0] = (R[0][0], 0.0)
            Lf[0] = (Lf[0][0], 0.0)
        stations.append((x, R, Lf))
    _prof_extrude(mb, stations)
    # asas de izaje: varilla corrugada de 7/8" doblada en U, ahogada en la corona
    for xc in (0.38, L - 0.38):
        xc += float(r.uniform(-0.01, 0.01))
        path = [(xc - 0.065, 0.0, H - 0.06), (xc - 0.065, 0.0, H + 0.075), (xc + 0.065, 0.0, H + 0.075), (xc + 0.065, 0.0, H - 0.06)]
        tube_path(mb, path, 0.0111, seg=SEG_T, mat="steel", bend=0.05, nseg=5, caps=False)
    return mb


def jersey_barrier(L=3.0, seed=0):
    """Barrera tipo New Jersey de concreto precolado (temporal, de conexión pin-and-loop): 0,81 m (32") de alto, base 0,61 m
    (24"), corona 0,15 m (6"): 76 mm verticales, talud de 55° hasta 0,33 m y cara de 84° hasta la corona (FHWA/DOT). Largo L a
    lo largo de +X desde x = 0, centrada en y = 0. Dos ranuras de izaje pasantes en la base a 0,9 m de cada extremo (WisDOT:
    "two lifting slots ... 3'-0" from each end"), chaflanes de 15 mm, lazos de varilla de 3/4" que salen de los extremos (dos
    por extremo, alturas alternadas para encajar con la vecina) y pasador de 25 mm × 0,7 m con cabeza en el extremo +X."""
    r = rng(seed)
    mb = MB()
    ch = 0.015
    zs = 0.10                                              # alto de la ranura de izaje

    def chain(slot=False):
        R = [(0.305 - ch * 0.5, 0.0), (0.305, ch * 0.5), (0.305, 0.076), (0.127, 0.33), (0.075 + ch * 0.9, 0.81 - ch * 0.4),
             (0.075 - ch * 0.4, 0.81)]
        if slot:
            yz = lambda z: 0.305 - (z - 0.076) / math.tan(math.radians(55))  # noqa: E731
            R[0] = (yz(zs) - 0.0005, zs)
            R[1] = (yz(zs + 0.004), zs + 0.004)
            R[2] = (yz(zs + 0.008), zs + 0.008)
        return R
    xs = []
    for xc in (0.9, L - 0.9):
        xs += [(xc - 0.16, False), (xc - 0.15, True), (xc + 0.15, True), (xc + 0.16, False)]
    stations = []
    for (x, slot) in [(0.0, False), (ch, False)] + xs + [(L - ch, False), (L, False)]:
        R = chain(slot)
        Lf = [(-y, z) for (y, z) in chain(slot)]
        if x in (0.0, L):
            loop = R + list(reversed(Lf))
            off = _offset_loop(loop, ch)
            n = len(R)
            R, Lf = off[:n], list(reversed(off[n:]))
            R[0] = (R[0][0], 0.0)
            Lf[0] = (Lf[0][0], 0.0)
        stations.append((x, R, Lf))
    # despostilladuras chicas en la corona de los extremos
    for k in (1, -2):
        x, R, Lf = stations[k]
        if r.uniform() < 0.7:
            R[-2] = (R[-2][0] - float(r.uniform(0.004, 0.009)), R[-2][1] - float(r.uniform(0.004, 0.01)))
    _prof_extrude(mb, stations)
    # pin-and-loop: lazos de varilla en U que salen 9 cm de cada cara de extremo
    for (xe, sgn, zl) in ((0.0, -1, (0.22, 0.56)), (L, 1, (0.30, 0.64))):
        for z in zl:
            w = 0.05
            path = [(xe - sgn * 0.04, -w, z), (xe + sgn * 0.09, -w, z), (xe + sgn * 0.09, w, z), (xe - sgn * 0.04, w, z)]
            tube_path(mb, path, 0.0095, seg=SEG_T, mat="steel", bend=0.035, nseg=3, caps=False)
    # pasador (en el extremo +X, pasa por los lazos de este lado): barra de 25 mm con cabeza doblada
    xp = L + 0.055
    lathe(mb, [(0.0, 0.05), (0.0125, 0.05), (0.0125, 0.74), (0.02, 0.745), (0.02, 0.765), (0.0, 0.77)], seg=SEG, mat="steel",
          M=_T(xp, 0.0, 0.0))
    return mb


# ============================================================================================================ concertina
# Alambre de navajas en espiral con grapas (concertina): diámetro 730 mm típico (24"-28"), navaja BTO-22 (largo 22 mm, ancho
# 15 mm, paso 34-40 mm, fleje de 0,5 mm sobre alambre de alta resistencia de 2,5 mm), 3 a 5 grapas por vuelta que unen cada
# espira con la vecina; ~56 espiras por rollo de 10-15 m estirado (rapidtech.co.ke 730 mm, firstfence.co.uk, citadel
# razor-wire spec). FM 5-102: concertina triple estándar (dos rollos abajo + uno arriba, piquetes largos 1,65 m).
CON_P = 0.036         # paso entre navajas a lo largo del fleje
CON_SP = 0.22         # separación entre espiras estiradas
CON_CLIPS = 3.5       # grapas por vuelta (media: alternan con la espira anterior y la siguiente)


def _coil(mb, L, d, seed, ctr=(0.0, None), squash=0.94, ground=True, clip_out=None):
    """Una espira continua de fleje de navajas a lo largo de +X (0..L), eje en (y, z) = ctr. Devuelve los puntos de grapa."""
    r = rng(seed)
    R = d / 2 - 0.008
    yc, zc = ctr[0], ((R * squash - 0.02) if ctr[1] is None else ctr[1])
    nt = max(2, int(round(L / CON_SP)))
    p = (L - CON_SP * 0.5) / nt
    ph = float(r.uniform(0, 100))
    A = 0.47 * p
    ns = 72
    th = np.linspace(0.0, 2 * PI * nt, ns * nt + 1)
    # forma de cada espira: círculo apenas aplastado (gravedad), radio con ruido de baja frecuencia (fleje que no es perfecto)
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
    # estaciones del fleje: angosta en cada paso, punta de navaja desfasada 0,32 / 0,68 (dientes encontrados)
    st = []
    k = 0
    s = 0.004
    while s < tot - 0.004:
        st.append((s, 0))
        t_ = s + CON_P * (0.32 if k % 2 == 0 else 0.68)
        if t_ < tot - 0.004:
            st.append((t_, 1))
        s += CON_P
        k += 1
    S = np.array([a for a, _ in st])
    Px = np.interp(S, acc, P[:, 0])
    Py = np.interp(S, acc, P[:, 1])
    Pz = np.interp(S, acc, P[:, 2])
    Q = np.stack([Px, Py, Pz], 1)
    T = np.gradient(Q, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    rings = []
    for i, (sv, tip) in enumerate(st):
        t = Vector(T[i])
        c = Vector(Q[i])
        rad = Vector((0.0, c.y - yc, c.z - zc))
        rad = (rad - t * rad.dot(t))
        rad = rad.normalized() if rad.length > 1e-6 else Vector((0, 0, 1))
        bn = t.cross(rad)
        tw = 2 * PI * sv / 1.1 + 0.9 * noise.noise(Vector((sv * 0.7, ph, 5.0)))
        U = rad * math.cos(tw) + bn * math.sin(tw)          # el fleje se tuerce a lo largo del rollo
        Vn = t.cross(U)
        w = 0.0076 if tip else 0.0019
        tk = 0.0006 if tip else 0.0013
        rings.append([c + U * w, c + Vn * tk, c - U * w, c - Vn * tk])
    V = [[mb.bm.verts.new(q) for q in ring] for ring in rings]
    for i in range(len(V) - 1):
        for j in range(4):
            jj = (j + 1) % 4
            mb.face([V[i][j], V[i][jj], V[i + 1][jj], V[i + 1][j]], "galvanized")
    mb.face(list(reversed(V[0])), "galvanized")
    mb.face(V[-1], "galvanized")
    # grapas: fleje de acero de 12 mm doblado sobre las dos espiras donde se tocan
    m = 0
    clips = []
    while True:
        t0 = 2 * PI * m / CON_CLIPS
        if t0 + 2 * PI > th[-1] - 1e-6:
            break
        pa = np.array([np.interp(t0, th, P[:, j]) for j in range(3)])
        pb = np.array([np.interp(t0 + 2 * PI, th, P[:, j]) for j in range(3)])
        a_, b_ = Vector(pa), Vector(pb)
        if b_.x < a_.x:
            a_, b_ = b_, a_
        radial = Vector((0.0, a_.y - yc, a_.z - zc)).normalized()
        Mc = _frame(a_, b_, radial)
        gap = (b_ - a_).length
        mb.box((-0.004, -0.006, -0.0022), (gap + 0.004, 0.006, 0.0022), "steel", bevel=0.0, m=Mc)
        clips.append(a_.lerp(b_, 0.5))
        m += 1
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
    """Rollo de concertina de navajas estirado en el piso a lo largo de +X (0..L), eje en y = 0, base en z = 0. Fleje de
    navajas BTO-22 de geometría real (sección en rombo con el alma de 2,5 mm al centro, dientes de 7,6 mm que se encuentran
    por pares cada 36 mm, fleje que se tuerce), espiras de diámetro d separadas 0,22 m con 3,5 grapas por vuelta que alternan
    con la espira anterior y la siguiente (el patrón de rombos cruzados de la concertina), espiras de abajo aplanadas en el
    piso. ~5,5 k tris por metro."""
    mb = MB()
    _coil(mb, L, d, seed)
    return mb


def _u_picket(mb, x, y, h, rot=0.0, mat="paint_od"):
    """Piquete en U de acero (perfil de 75 × 35 × 3 mm, con alas dobladas) hincado; asoma h m. Ojos en la cara para amarres."""
    t = 0.003
    prof = [(-0.0375, 0.0), (-0.0375, 0.012), (-0.03, 0.035), (0.03, 0.035), (0.0375, 0.012), (0.0375, 0.0),
            (0.0375 - t, 0.0), (0.0375 - t, 0.011), (0.03 - t * 0.6, 0.035 - t), (-0.03 + t * 0.6, 0.035 - t),
            (-0.0375 + t, 0.011), (-0.0375 + t, 0.0)]
    M = _T(x, y, 0.0) @ _Rz(rot)
    rings = [[M @ Vector((px, py - 0.017, z)) for (px, py) in prof] for z in (-0.15, h)]
    loft_rings(mb, rings, mat)


def concertina_triple(L=10.0, d=0.75, seed=0):
    """Concertina triple estándar (FM 5-102): dos rollos lado a lado en el piso y un tercero encima en la junta, a lo largo de
    +X (0..L), centrada en y = 0; piquetes de U de acero de 1,65 m metidos en los rollos de abajo cada ~4,5 m (y a 0,3 m de
    cada extremo), y amarres de alambre que sujetan los rollos a los piquetes."""
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
            for z in (0.4, 1.5):                           # amarres: dos vueltas de alambre suave alrededor del piquete
                for k in range(2):
                    pts = [(x + 0.045 * math.cos(a) * 1.0, y + 0.03 * math.sin(a), z + 0.006 * k + 0.002 * a)
                           for a in np.linspace(0, 2 * PI, 13)[:-1]]
                    pts.append(pts[0])
                    mb.tube([(p[0], p[1], p[2]) for p in pts], 0.0012, seg=SEG_T, mat="steel", caps=True)
    return mb


def concertina_fence_top(L=10.0, d=0.6, seed=0, with_fence=False):
    """Un rollo de concertina montado sobre una malla ciclónica de 2,4 m (kit.telecom.fence_run, brazos a 45° hacia -Y):
    coordenadas del tramo de cerca (x a lo largo, y = 0 eje de los postes, z = piso). El rollo descansa sobre los 3 hilos de
    púas de los brazos, centrado sobre el hilo medio, y se amarra a los hilos con grapas cada ~0,45 m.
    with_fence=True agrega el tramo de cerca 'lite' (solo para revisar)."""
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
    _coil(mb, L, d, seed, ctr=(c.y, c.z), ground=False, squash=0.97)
    # grapas de amarre del rollo a los hilos de púas
    x = 0.25
    k = 0
    while x < L - 0.2:
        p = strands[k % 3]
        mb.box((-0.006, -0.002, -0.0035), (0.006, 0.002, 0.012), "steel", bevel=0.0, m=_T(x, p.y, p.z) @ _Rx(-45))
        x += 0.45
        k += 1
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
                    row.append((x, y, ang + (180.0 if (i + k) % 2 else 0.0), (b_ - a_) / 0.515, 1.0))
        courses.append(row)
    return courses


def guard_tower(seed=0):
    """Torre de vigilancia de acero de 4 patas: plataforma a 5,0 m, patas de PTR 100 × 100 con talud (2,6 m entre ejes abajo,
    2,2 m arriba) sobre dados de concreto con placa base, cartabones y 4 anclas; travesaños de ángulo 75 × 6 y contravientos
    en X de solera 60 × 8 con placas de conexión atornilladas; piso de rejilla electrosoldada (soleras 30 × 3 a 33 mm) sobre
    marco de PTR; barandal de tubo de 48 mm con rodapié; muro de sacos terreros de 6 hiladas sobre el piso (hueco de acceso
    al fondo); techo a un agua de lámina acanalada sobre postes de 60 × 60, largueros y tornillos con arandela; escalera
    marina en el fondo (+Y) con jaula de seguridad (aros a partir de 2,4 m, OSHA 1910.28/ANSI A14.3: peldaños a 0,30 m, ancho
    libre 0,42 m). Origen: centro del pie de la torre; frente (lado vigilado) hacia -Y."""
    r = rng(seed)
    mb = MB()
    zd = 5.0
    zf = zd - 0.15
    b0, b1 = 1.3, 1.1
    zb = 0.27

    def half(z):
        return b0 + (b1 - b0) * (z - zb) / (zf - zb)
    st = "galvanized"
    # ---- dados, placas base, anclas, cartabones y patas
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0, y0 = sx * b0, sy * b0
            slab(mb, _T(x0, y0, -0.08), 0.6, 0.6, 0.33, rc=0.03, re=0.02, mat="concrete", nc=3, ne=2)
            mb.box((x0 - 0.16, y0 - 0.16, 0.25), (x0 + 0.16, y0 + 0.16, zb), st, bevel=0.003, seg=1)
            for ax in (-1, 1):
                for ay in (-1, 1):
                    Ma = _T(x0 + ax * 0.115, y0 + ay * 0.115, zb)
                    hexnut(mb, Ma, s=0.032, h=0.02, mat=st)
                    lathe(mb, [(0.0, 0.0), (0.0095, 0.0), (0.0095, 0.045), (0.007, 0.05), (0.0, 0.05)], seg=SEG_T, mat=st, M=Ma)
            top = Vector((sx * b1, sy * b1, zf))
            bot = Vector((x0, y0, zb))
            rtube(mb, bot, top, 0.1, 0.1, st, up=(1, 0, 0), r=0.006)
            for (gx, gy) in ((1, 0), (0, 1)):              # cartabones
                Mg = _T(x0, y0, zb) @ (_Rx(90) if gx else _Rz(90) @ _Rx(90))
                mb.plate([(-0.15, 0.0), (0.15, 0.0), (0.05, 0.16), (-0.05, 0.16)], 0.01, st, m=Mg @ _T(0, 0, -0.005))
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
                mb.box((0.0, -0.03, -0.004), (ln, 0.03, 0.004), st, bevel=0.0015, seg=1, m=Mf)
                for (pp, ll) in ((pa + o, 0.03), (pb + o, ln - 0.03)):
                    Mg = Mf @ _T(ll, 0, 0.004)
                    mb.box((-0.07, -0.06, -0.012), (0.07, 0.06, -0.004), st, bevel=0.002, seg=1, m=Mf @ _T(ll, 0, 0))
                    hexnut(mb, Mg, s=0.024, h=0.014, mat=st)
            # perno de cruce de las diagonales
            zc = (z0 + z1) / 2
            hc = half(zc)
            pc = Vector(((a_[0] + b_[0]) / 2 * hc, (a_[1] + b_[1]) / 2 * hc, zc)) + out0 * 0.083
            hexnut(mb, face_M(pc, out0), s=0.024, h=0.014, mat=st)
    # ---- marco del piso, rejilla, rodapié y barandal
    H2 = 1.32
    for (p0, p1) in (((-H2, -H2), (H2, -H2)), ((-H2, H2), (H2, H2)), ((-H2, -H2), (-H2, H2)), ((H2, -H2), (H2, H2)),
                     ((-H2, -0.45), (H2, -0.45)), ((-H2, 0.45), (H2, 0.45))):
        rtube(mb, (p0[0], p0[1], zd - 0.105), (p1[0], p1[1], zd - 0.105), 0.075, 0.15, st, up=(0, 0, 1), r=0.005)
    ny = int((2 * H2 - 0.08) / 0.033)
    for k in range(ny + 1):
        y = -H2 + 0.04 + k * 0.033
        mb.box((-H2 + 0.04, y - 0.0015, zd - 0.03), (H2 - 0.04, y + 0.0015, zd), st, bevel=0.0)
    for k in range(int((2 * H2 - 0.08) / 0.1) + 1):
        x = -H2 + 0.04 + k * 0.1
        mb.box((x - 0.003, -H2 + 0.04, zd - 0.006), (x + 0.003, H2 - 0.04, zd - 0.0005), st, bevel=0.0)
    for (p0, p1) in (((-H2, -H2), (H2, -H2)), ((H2, -H2), (H2, H2)), ((H2, H2), (0.4, H2)), ((-0.4, H2), (-H2, H2)),
                     ((-H2, H2), (-H2, -H2))):
        a_, b_ = Vector((*p0, 0)), Vector((*p1, 0))
        d = (b_ - a_).normalized()
        nrm = Vector((d.y, -d.x, 0))
        Mt = _frame(Vector((a_.x, a_.y, zd)) - nrm * 0.0, Vector((b_.x, b_.y, zd)), Vector((0, 0, 1)))
        mb.box((0.0, -0.003, 0.0), ((b_ - a_).length, 0.003, 0.1), st, bevel=0.0015, seg=1, m=Mt @ _T(0, 0, 0))
        mb.cyl((a_.x, a_.y, zd + 1.07), (b_.x, b_.y, zd + 1.07), 0.024, seg=SEG, mat=st)
        mb.cyl((a_.x, a_.y, zd + 0.55), (b_.x, b_.y, zd + 0.55), 0.021, seg=SEG, mat=st)
    for (x, y) in ((-H2, -H2), (H2, -H2), (H2, H2), (-H2, H2), (0.0, -H2), (H2, 0.0), (-H2, 0.0), (0.4, H2), (-0.4, H2)):
        lathe(mb, [(0.0, zd), (0.024, zd), (0.024, zd + 1.07), (0.0, zd + 1.095)], seg=SEG, mat=st, M=_T(x, y, 0))
    # ---- muro de sacos sobre el piso (hueco de acceso al fondo)
    bags = _bag_stack(_ring_courses(1.08, 6, opening=("b", 0.42)), seed, (-1.6, 1.6, -1.6, 1.6), lod=0)
    mb.join(bags, _T(0, 0, zd))
    # ---- techo a un agua: postes, marco, largueros, lámina acanalada y tornillos
    zr_f, zr_b = zd + 2.25, zd + 2.05
    zr = lambda y: zr_f + (zr_b - zr_f) * (y + 1.22) / 2.44  # noqa: E731
    for (x, y) in ((-1.22, -1.22), (1.22, -1.22), (1.22, 1.22), (-1.22, 1.22)):
        rtube(mb, (x, y, zd), (x, y, zr(y) - 0.06), 0.06, 0.06, st, up=(1, 0, 0), r=0.004)
    for x in (-1.22, 1.22):
        rtube(mb, (x, -1.3, zr(-1.3) - 0.03), (x, 1.3, zr(1.3) - 0.03), 0.05, 0.06, st, up=(0, 0, 1), r=0.004)
    for y in (-1.22, -0.4, 0.4, 1.22):
        rtube(mb, (-1.35, y, zr(y) + 0.0), (1.35, y, zr(y) + 0.0), 0.05, 0.05, st, up=(0, 0, 1), r=0.004)
    # lámina acanalada (onda de 76 mm, 18 mm de peralte), canales a lo largo de la pendiente (Y)
    Wr, pitch, A = 2.95, 0.0762, 0.009
    nw = int(Wr / pitch)
    xs = [-nw * pitch / 2 + pitch * k / 8 for k in range(nw * 8 + 1)]
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
        for k in range(1, nw, 4):
            x = -nw * pitch / 2 + pitch * k + pitch / 2
            p = sheet_pt(x, y, 0.0)
            Ms = _T(p.x, p.y, p.z) @ _Rx(math.degrees(slope))
            hexnut(mb, Ms @ _T(0, 0, -0.001), s=0.008, h=0.007, mat=st)   # tornillo autotaladrante de cabeza hexagonal
    # ---- escalera marina con jaula (fondo, +Y)
    yl = 1.5
    ztop = zd + 1.1
    for sx in (-1, 1):
        mb.box((sx * 0.235 - 0.006, yl - 0.03, 0.0), (sx * 0.235 + 0.006, yl + 0.03, ztop), st, bevel=0.002, seg=1)
        lathe(mb, [(0.0, -0.002), (0.07, -0.002), (0.07, 0.01), (0.0, 0.01)], seg=SEG, mat="concrete", M=_T(sx * 0.235, yl, 0.0))
    z = 0.3
    while z < zd + 0.05:
        mb.cyl((-0.229, yl, z), (0.229, yl, z), 0.011, seg=16, mat=st, caps=False)
        z += 0.3
    for z in (1.75, 3.3, zf - 0.08):                       # ménsulas de la escalera a la cara del fondo
        h = half(z)
        for sx in (-1, 1):
            mb.box((sx * 0.235 - 0.03, h + 0.05, z - 0.004), (sx * 0.235 + 0.03, yl - 0.03, z + 0.004), st, bevel=0.002, seg=1)
    hoops = [2.4 + 0.9 * k for k in range(4)]
    hoops.append(ztop - 0.05)
    Rc = 0.36
    cy = yl + 0.05
    for z in hoops:
        path = [(-0.24, yl, z), (-Rc, cy, z)] + [(Rc * math.cos(a), cy + Rc * math.sin(a), z) for a in np.linspace(PI, 0, 15)][1:-1] + \
               [(Rc, cy, z), (0.24, yl, z)]
        sweep_frame(mb, [(-0.003, -0.025), (0.003, -0.025), (0.003, 0.025), (-0.003, 0.025)], path, st, up=(0, 0, 1))
    for a in np.linspace(PI * 0.88, PI * 0.12, 5):
        p = Vector((Rc * math.cos(a), cy + Rc * math.sin(a), 0))
        nrm = Vector((math.cos(a), math.sin(a), 0))
        Mv = _frame(Vector((p.x, p.y, hoops[0] - 0.03)) + nrm * 0.006, Vector((p.x, p.y, hoops[-1] + 0.03)) + nrm * 0.006, nrm)
        mb.box((0.0, -0.02, -0.003), (hoops[-1] - hoops[0] + 0.06, 0.02, 0.003), st, bevel=0.0012, seg=1, m=Mv)
    del r
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
# La guarnición (garnish) es una lámina cortada con huecos y solapas: aquí es geometría (material "net" de DOS CARAS);
# rejilla de 7,2 cm recortada por isolíneas (marching triangles) de un ruido de 3 octavas.
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
    """Toldo de red de camuflaje de w (X) × l (Y) m centrado en el origen: guarnición cortada con huecos orgánicos y orillas
    deshilachadas (geometría real, material 'net' de dos caras), colgada sobre postes seccionales de aluminio Ø 38 mm con
    separador (disco abovedado) en los postes interiores de ~3,4 m y postes de orilla de 2,3 m en esquinas y medios lados; la
    red forma picos en los separadores y cuelga entre apoyos; las orillas libres hacen catenaria; relinga perimetral, vientos
    con estacas de acero. poles=False: solo la red con su relinga (la misma forma, para colgarla sobre otra pieza)."""
    r = rng(seed)
    mb = MB()
    ph = float(r.uniform(0, 100))
    # ---- apoyos
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
    supports = [(x, y, z + 0.06, 0.34) for (x, y), z in zip(inner, zi)]
    ties = [(x, y, z + 0.03) for (x, y), z in zip(edge_p, ze)]
    xs, ys, Z = _drape(w, l, supports, ties)
    # ---- red: rejilla de 6,5 cm recortada por un campo de ruido (huecos de la guarnición) con contornos interpolados
    a = 0.072
    nx = int(round(w / a))
    ny = int(round(l / a))
    gx = np.linspace(-w / 2, w / 2, nx + 1)
    gy = np.linspace(-l / 2, l / 2, ny + 1)
    GX, GY = np.meshgrid(gx, gy)

    def field(x, y):
        f = np.array([0.6 * noise.noise(Vector((float(u) * 2.2, float(v) * 2.2, ph))) + noise.noise(Vector((float(u) * 6.0, float(v) * 6.0,
                      ph + 7.0))) + 0.45 * noise.noise(Vector((float(u) * 14.0, float(v) * 14.0, ph + 13.0)))
                      for u, v in zip(np.ravel(x), np.ravel(y))]).reshape(np.shape(x))
        f = f + 0.12
        border = np.minimum(np.minimum(x + w / 2, w / 2 - x), np.minimum(y + l / 2, l / 2 - y))
        f = f + np.clip((0.16 - border) / 0.06, 0, 3)          # orilla continua donde corre la relinga
        for (px, py, _, _) in supports:
            f = f + 2.5 * np.clip(1 - np.hypot(x - px, y - py) / 0.45, 0, 1)
        return f
    F = field(GX, GY)

    def zat(x, y):
        z = _bilerp(xs, ys, Z, x, y)
        wr = 0.035 * noise.noise(Vector((x * 0.9, y * 0.9, ph + 3))) + 0.016 * noise.noise(Vector((x * 3.5, y * 3.5, ph + 5))) \
            + 0.008 * noise.noise(Vector((x * 9.0, y * 9.0, ph + 6)))
        near = min([math.hypot(x - px, y - py) for (px, py, _, _) in supports] + [9.0])
        if near < 0.5:
            wr = abs(wr) * (near / 0.5)
        return float(z) + wr
    vid = {}

    def V(i, j):
        if (i, j) not in vid:
            x, y = gx[i], gy[j]
            vid[(i, j)] = mb.bm.verts.new(Vector((x, y, zat(x, y))))
        return vid[(i, j)]
    eid = {}

    def E(p, q):
        key = (min(p, q), max(p, q))
        if key not in eid:
            (i0, j0), (i1, j1) = key
            f0, f1 = F[j0, i0], F[j1, i1]
            t = min(max(f0 / (f0 - f1), 0.04), 0.96)          # nunca encima de un vértice: sin caras de área cero
            x = gx[i0] + (gx[i1] - gx[i0]) * t
            y = gy[j0] + (gy[j1] - gy[j0]) * t
            # deshilachado: el corte no es limpio; la solapa se levanta o cae un poco
            jx = 0.009 * noise.noise(Vector((x * 40, y * 40, ph + 9)))
            jy = 0.009 * noise.noise(Vector((x * 40, y * 40, ph + 11)))
            dz = 0.024 * noise.noise(Vector((x * 9, y * 9, ph + 17)))
            eid[key] = mb.bm.verts.new(Vector((x + jx, y + jy, zat(x, y) + dz)))
        return eid[key]

    def tri(ids):
        vals = [F[j, i] for (i, j) in ids]
        if all(v >= 0 for v in vals):
            mb.face([V(*p) for p in ids], "net").smooth = True
            return
        if all(v < 0 for v in vals):
            return
        poly = []
        for k in range(3):
            p, q = ids[k], ids[(k + 1) % 3]
            fp, fq = vals[k], vals[(k + 1) % 3]
            if fp >= 0:
                poly.append(V(*p))
            if (fp >= 0) != (fq >= 0):
                poly.append(E(p, q))
        for k in range(1, len(poly) - 1):
            try:
                mb.face([poly[0], poly[k], poly[k + 1]], "net").smooth = True
            except ValueError:
                pass
    for j in range(ny):
        for i in range(nx):
            A_, B_, C_, D_ = (i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1)
            if (i + j) % 2:
                tri((A_, B_, C_))
                tri((A_, C_, D_))
            else:
                tri((A_, B_, D_))
                tri((B_, C_, D_))
    # ---- relinga perimetral (cuerda de 12 mm cosida a la orilla)
    per = []
    for i in range(0, nx + 1, 4):
        per.append((i, 0))
    for j in range(0, ny + 1, 4):
        per.append((nx, j))
    for i in range(nx, -1, -4):
        per.append((i, ny))
    for j in range(ny, -1, -4):
        per.append((0, j))
    pts = []
    for (i, j) in per:
        p = Vector((gx[i], gy[j], zat(gx[i], gy[j]) - 0.007))
        if not pts or (p - Vector(pts[-1])).length > 1e-4:
            pts.append(tuple(p))
    pts.append(pts[0])
    pts.append(pts[1])
    mb.tube(pts, 0.006, seg=SEG_T, mat="canvas", caps=False)
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
                  seg=32, mat="plastic", M=Ms, rmod=lambda i, a_, rr, z: rr * (1 + 0.02 * math.cos(8 * a_)) if i in (3, 4) else rr)
            for k in range(8):
                ang = math.radians(22.5 + 45 * k)
                mb.box((0.04, -0.004, 0.0), (0.22, 0.004, 0.028), "plastic", bevel=0.002, seg=1,
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
            tube_path(mb, catenary((x, y, z + 0.06), (g.x, g.y, 0.07), 0.03, n=8), 0.005, seg=SEG_T, mat="canvas", caps=True)
    # amarres intermedios de la orilla a estacas
    for (x0, y0, x1, y1) in ((-w / 2, -l / 2, w / 2, -l / 2), (-w / 2, l / 2, w / 2, l / 2), (-w / 2, -l / 2, -w / 2, l / 2),
                             (w / 2, -l / 2, w / 2, l / 2)):
        for t in (0.25, 0.75):
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            zz = float(_bilerp(xs, ys, Z, np.array(x), np.array(y)))
            d = Vector((math.copysign(1, x) if abs(x0 - x1) < 1e-6 else 0.0, math.copysign(1, y) if abs(y0 - y1) < 1e-6 else 0.0, 0))
            g = Vector((x, y, 0)) + d * 1.1
            stakes.append(g)
            tube_path(mb, catenary((x, y, zz - 0.01), (g.x, g.y, 0.07), 0.02, n=7), 0.0045, seg=SEG_T, mat="canvas", caps=True)
    for g in stakes:                                       # estaca de varilla con gancho, hincada
        tube_path(mb, [(g.x, g.y, -0.12), (g.x, g.y, 0.08), (g.x + 0.03, g.y, 0.1), (g.x + 0.05, g.y, 0.07)], 0.006, seg=SEG_T,
                  mat="steel", bend=0.015, nseg=2, caps=True)
    return mb
