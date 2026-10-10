"""damage.py — GRUPO G4 · DAÑO del kit modular BLACKISLE (varillas expuestas, escombro, trozos y mordidas de arista).

Todas las funciones públicas devuelven un `MB` (o lo escriben en uno, `spalled_box`). Todo es sólido cerrado
(0 aristas no-manifold): no hay láminas en este módulo. Triángulos solo donde la forma lo exige (cascos convexos de
escombro); el resto son cuadriláteros.

Medidas: varilla #3 Ø 3/8" (r = 4,8 mm) y #4 Ø 1/2" (r = 6,4 mm) de 8 lados con corrugado real (anillos cada 12 mm);
estribo #2 Ø 1/4" (r = 3,2 mm) con ganchos a 135°; recubrimiento 35 mm al eje de la varilla longitudinal.

USO DE `spall_edge` EN LAS ESQUINAS (sin booleanos)
---------------------------------------------------
`spall_edge(L, D)` es GEOMETRÍA DE REEMPLAZO del prisma de esquina de una arista. En coordenadas locales:
  · la arista corre por +X de x = 0 a x = L;
  · la cara "frontal" del anfitrión es el plano y = 0 (mira a -Y) y la cara "superior" es z = 0 (mira a +Z);
  · la pieza ocupa x ∈ [0,001, L-0,001], y ∈ [0, D-0,001], z ∈ [-(D-0,001), 0]: queda AL RAS en y = 0 y z = 0 y
    separada 1 mm de las caras internas del hueco que deja el anfitrión (y = D, z = -D, x = 0, x = L).
  · En sus extremos el perfil es el chaflán redondo intacto de la arista (`edge_bevel`, mismo perfil que
    `MB.box(bevel=b, seg=2)`), así empalma con la arista sana del anfitrión.
El constructor tiene que DEJAR VACÍO ese prisma de esquina en el anfitrión. La forma fácil es `spalled_box(...)`, que
arma la caja anfitriona (losa, viga o columna) como un sólido soldado con las muescas de esquina (extracción de celdas
sobre una retícula, sin caras internas) + biseles solo en las aristas exteriores reales, y coloca las mordidas:
    spalled_box(mb, (0, 0, 2.9), (3.6, 0.35, 3.1), [dict(axis="x", sides=(-1, -1), start=0.8, length=1.1, depth=0.12)])
      -> losa con la arista inferior-frontal mordida entre x = 0,8 y 1,9 (varillas de la losa expuestas).
    start se mide desde mn[axis] (inicio de la caja), length a lo largo del eje, depth = lado del prisma de esquina.
    axis: dirección de la arista ('x' | 'y' | 'z'); sides: signos (-1 = cara mínima, +1 = cara máxima) de los otros dos
    ejes en orden (x -> (y, z), y -> (x, z), z -> (x, y)). Columnas: axis='z', sides=(±1, ±1) = cualquiera de sus 4 esquinas.
Para colocar `spall_edge` a mano en otra orientación usa `spall_matrix(...)` (misma convención) y construye tú el hueco.

NIVEL DE DETALLE: todas las funciones públicas aceptan detail='high' (por defecto) | 'mid' | 'low' (ver services._detail;
la semilla se consume igual en los 3 niveles). Triángulos medidos (barrido de 8 semillas × 3 niveles; high / mid / low):
  rebar_nest (n 4–11, largo 0,4–0,9) ....... 19–40 k     / 3,2–3,8 k / 1,2–1,4 k   (n 8, 0,6 m: 28,5 / 3,3 / 1,25 k)
  rubble_pile (r 0,6–2,0, n 30–100) ........ 16–115 k    / 4,6–30 k  / 2,7–9,3 k   (r 1, n 60: 50 / 13,3 / 5,6 k)
  chunk (0,1–0,7 m) ........................ 0,3–3,6 k   / 0,1–1,5 k / 80–140
  spall_edge (0,5–1,9 m) ................... 3,0–13,9 k  / 0,6–2,5 k / 0,3–1,1 k
  spalled_box (losa 2–3,4 m, 2 mordidas) ... 18,7–27 k   / 5,6–8,0 k / 2,4–3,3 k  · columna 2,6 m: 19,9 / 6,0 / 2,5 k
Control de costo adicional: rebar_nest(n, seg, ribs) y rubble_pile(n, gravel).
"""
import math

import bpy  # noqa: F401  (bmesh/mathutils solo existen después de importar bpy)
import bmesh
from mathutils import Matrix, Vector

from kit.common import MB, rng
from kit.services import (PI, _LOD, _R, _T, _Nz, _box, _declump, _detail, _fillet, _lattice, _lv, _merge, _simplify, _smooth,
                          _tube, _v)


# =====================================================================================================================
# utilidades
# =====================================================================================================================
def _hull(mb, pts, mat="rubble", m=None, detail=0, nz=None, amp=0.0, freq=20.0, flat=None, matfn=None, weld=0.0):
    """Casco convexo (bmesh.ops.convex_hull) de `pts`. detail = cortes de subdivisión de cada arista para poder rugosear
    la superficie de fractura con ruido (amp, freq); `flat(p) -> True` marca vértices de caras originales (moldeadas)
    que no se rugosean. matfn(centro, normal) -> material por cara. weld > 0: suelda antes los puntos a menos de `weld`
    (evita astillas de área ~0 cuando los puntos vienen muestreados sobre planos). Sólido cerrado."""
    tmp = bmesh.new()
    vs = [tmp.verts.new(_v(p)) for p in pts]
    if weld > 0:
        bmesh.ops.remove_doubles(tmp, verts=vs, dist=weld)
        vs = list(tmp.verts)
    bmesh.ops.convex_hull(tmp, input=vs, use_existing_faces=False)
    junk = [v for v in tmp.verts if not v.link_faces]
    if junk:
        bmesh.ops.delete(tmp, geom=junk, context="VERTS")
    # une triángulos casi coplanares (caras de fractura planas, menos triángulos delgados)
    bmesh.ops.dissolve_limit(tmp, angle_limit=math.radians(2.0), verts=list(tmp.verts), edges=list(tmp.edges))
    if weld > 0:
        bmesh.ops.dissolve_degenerate(tmp, dist=weld, edges=list(tmp.edges))
    bmesh.ops.triangulate(tmp, faces=[f for f in tmp.faces if len(f.verts) > 4])
    _fix_slivers(tmp)
    junk = [v for v in tmp.verts if not v.link_faces]
    if junk:
        bmesh.ops.delete(tmp, geom=junk, context="VERTS")
    if detail > 0:
        tmp.normal_update()
        orig = list(tmp.verts)
        ctr = sum((v.co for v in orig), Vector((0, 0, 0))) / max(len(orig), 1)
        origs = set(orig)
        bmesh.ops.subdivide_edges(tmp, edges=list(tmp.edges), cuts=detail, use_grid_fill=True)
        tmp.normal_update()
        if nz is not None and amp > 0:
            for v in tmp.verts:
                if v in origs:
                    continue
                if flat is not None and flat(v.co):
                    continue
                k = nz(v.co, freq) + 0.45 * nz(v.co, freq * 2.7)
                v.co -= v.normal * amp * k
    tmp.normal_update()
    out = MB()
    out.bm.free()
    out.bm = tmp
    for f in tmp.faces:
        f.material_index = out.mi(mat)
    if matfn is not None:
        for f in tmp.faces:
            mm = matfn(f.calc_center_median(), f.normal)
            if mm:
                f.material_index = out.mi(mm)
    _merge(mb, out, m)


def _fix_slivers(bm, area=1e-8):
    """Astillas de área ~0 (vértice colineal sobre el borde de un n-gono al triangular): se gira su arista más larga."""
    for _ in range(4):
        bad = [f for f in bm.faces if len(f.verts) == 3 and f.calc_area() < area]
        if not bad:
            return
        for f in bad:
            if not f.is_valid:
                continue
            e = max(f.edges, key=lambda e_: e_.calc_length())
            if len(e.link_faces) == 2:
                bmesh.utils.edge_rotate(e, True)


def _rebar_path(rr, p0, d0, L, bend_dir, kind="bent", step=0.006):
    """Polilínea de una varilla: tramo recto, dobladura concentrada (radio R, ángulo θ) y tramo final casi recto.
    kind: 'bent' (θ 25–100°, R 6–20 cm), 'hook' (θ 140–175°, R 4–8 cm), 'kink' (quiebre seco 50–110°),
    'straight' (recta con desplome leve)."""
    p = _v(p0)
    d = _v(d0).normalized()
    b = _v(bend_dir)
    b = (b - d * b.dot(d))
    b = b.normalized() if b.length > 1e-6 else d.orthogonal().normalized()
    if kind == "bent":
        s1, th, R = rr.uniform(0.04, 0.25) * L / 0.6, math.radians(rr.uniform(25, 100)), rr.uniform(0.06, 0.2)
    elif kind == "hook":
        s1, th, R = rr.uniform(0.1, 0.35) * L / 0.6, math.radians(rr.uniform(140, 175)), rr.uniform(0.04, 0.08)
    elif kind == "kink":
        s1, th, R = rr.uniform(0.05, 0.3) * L / 0.6, math.radians(rr.uniform(50, 110)), 0.012
    else:
        s1, th, R = L, 0.0, 1.0
    s1 = min(s1, 0.8 * L)
    arc = th * R
    side = b.cross(d).normalized()
    wob, wob_a = rr.uniform(0, 2 * PI), rr.uniform(0.01, 0.04)
    sag = rr.uniform(-0.25, 0.25)
    n = max(4, int(L / step))
    pts = [p.copy()]
    for i in range(1, n + 1):
        s = L * i / n
        if s <= s1:
            ang = 0.0
        elif s <= s1 + arc:
            ang = th * (s - s1) / max(arc, 1e-6)
        else:
            ang = th + sag * (s - s1 - arc) * 0.6
        dirv = d * math.cos(ang) + b * math.sin(ang)
        dirv = (dirv + side * wob_a * math.sin(s * 7 + wob)).normalized()
        p = p + dirv * (L / n)
        pts.append(p.copy())
    return pts


def _rebar(mb, pts, r, ribs=None, seg=None, mat="metal_rust"):
    """Varilla corrugada: anillos de corrugado (r × 1,16) cada ~12 mm (2 muestras por paso de 6 mm).
    ribs / seg = None -> según el nivel: high corrugada de 8 lados · mid lisa de 5 lados · low lisa de 4 lados; las lisas
    se simplifican (Douglas-Peucker): los tramos rectos quedan en 1 segmento y solo la dobladura conserva estaciones."""
    if ribs is None:
        ribs = _lv(True, False, False)
    if seg is None:
        seg = _lv(8, 5, 4)
    if ribs:
        radii = [r * (1.16 if (i % 2 == 1) else 1.0) for i in range(len(pts))]
        _tube(mb, pts, r, seg=seg, mat=mat, radii=radii, lod=False)
    else:
        P = [_v(p) for p in pts]
        if _LOD.level != "high":
            P = [P[i] for i in _simplify(P, r)]
        _tube(mb, P, r, seg=seg, mat=mat, lod=False)


def _resample(pts, step):
    P = [_v(p) for p in pts]
    out = [P[0]]
    acc = 0.0
    for a, b in zip(P[:-1], P[1:]):
        L = (b - a).length
        if L < 1e-9:
            continue
        t = step - acc
        while t <= L:
            out.append(a.lerp(b, t / L))
            t += step
        acc = L - (t - step)
    if (out[-1] - P[-1]).length > step * 0.3:
        out.append(P[-1])
    return out


def _stirrup(mb, cx, cy, z, hw, hd, rr, r=0.0032, tilt=(0.0, 0.0), open_=0.0, mat="metal_rust"):
    """Estribo rectangular #2 con esquinas dobladas (radio 2 cm) y ganchos a 135° en una esquina. open_ > 0 abre un lado."""
    corners = [(cx - hw, cy - hd), (cx + hw, cy - hd), (cx + hw, cy + hd), (cx - hw, cy + hd)]
    start = int(rr.integers(0, 4))
    c = corners[start:] + corners[:start]
    c0 = Vector((c[0][0], c[0][1], z))
    hk_in = (Vector((cx, cy, z)) - c0).normalized()
    q25 = c0 + (Vector((c[1][0], c[1][1], z)) - c0) * 0.25
    # ganchos a 135° incluidos ANTES del redondeo: también sus dobleces quedan curvos (antes eran quiebres secos)
    path = ([c0 + hk_in * 0.07 + Vector((0, 0, -0.003))] + [Vector((cc[0], cc[1], z)) for cc in c] + [c0, q25]
            + [q25 + hk_in * 0.06 + Vector((0, 0, 0.003))])
    path = _fillet(path, 0.02, 4)
    if open_ > 0:
        k = len(path) // 2
        for i in range(k, len(path)):
            path[i] = path[i] + (path[i] - Vector((cx, cy, z))).normalized() * open_ * (i - k) / max(1, len(path) - k)
    M = _T(cx, cy, z) @ _R("X", tilt[0]) @ _R("Y", tilt[1]) @ _T(-cx, -cy, -z)
    _tube(mb, [M @ p for p in _resample(path, 0.01)], r, seg=8, mat=mat)


def _chunk_pts(rr, sx, sy, sz, kind):
    """Puntos para el casco de un trozo: 'block' = sobre la superficie de una caja con jitter (caras de fractura grandes,
    esquinas cortadas), 'slab' = contornos irregulares en z = ±sz/2 + capas intermedias (pedazo de losa con caras
    moldeadas planas y canto de fractura facetado)."""
    pts = []
    if kind == "slab":
        nv = int(rr.integers(7, 12))
        a0 = rr.uniform(0, 2 * PI)
        base = [(a0 + 2 * PI * (i + rr.uniform(-0.35, 0.35)) / nv, rr.uniform(0.55, 1.0)) for i in range(nv)]
        for zf in (-0.5, -0.17, 0.17, 0.5):
            for (a, rad) in base:
                if abs(zf) < 0.5:
                    rad *= rr.uniform(0.9, 1.06)
                    a += rr.uniform(-0.12, 0.12)
                else:
                    rad *= rr.uniform(0.94, 1.0)
                pts.append((sx / 2 * rad * math.cos(a), sy / 2 * rad * math.sin(a), zf * sz))
        return pts
    n = int(rr.integers(11, 17))
    for _ in range(n):
        p = Vector((rr.uniform(-1, 1), rr.uniform(-1, 1), rr.uniform(-1, 1)))
        ax = max(range(3), key=lambda i: abs(p[i]))
        p[ax] = math.copysign(rr.uniform(0.7, 1.0), p[ax])
        pts.append((p.x * sx / 2, p.y * sy / 2, p.z * sz / 2))
    return pts


_CSPHERE = {}


def _cube_sphere(N):
    """Esfera-cubo (retícula N × N de cuadriláteros por cara, malla cerrada y soldada): (direcciones unitarias, quads)."""
    if N in _CSPHERE:
        return _CSPHERE[N]
    idx, pts, quads = {}, [], []

    def V(i, j, k):
        key = (i, j, k)
        if key not in idx:
            x, y, z = 2 * i / N - 1, 2 * j / N - 1, 2 * k / N - 1
            s = Vector((x * math.sqrt(max(0.0, 1 - y * y / 2 - z * z / 2 + y * y * z * z / 3)),
                        y * math.sqrt(max(0.0, 1 - z * z / 2 - x * x / 2 + z * z * x * x / 3)),
                        z * math.sqrt(max(0.0, 1 - x * x / 2 - y * y / 2 + x * x * y * y / 3))))
            idx[key] = len(pts)
            pts.append(s.normalized())
        return idx[key]

    for a in range(N):
        for b in range(N):
            quads.append((V(0, a, b), V(0, a, b + 1), V(0, a + 1, b + 1), V(0, a + 1, b)))
            quads.append((V(N, a, b), V(N, a + 1, b), V(N, a + 1, b + 1), V(N, a, b + 1)))
            quads.append((V(a, 0, b), V(a + 1, 0, b), V(a + 1, 0, b + 1), V(a, 0, b + 1)))
            quads.append((V(a, N, b), V(a, N, b + 1), V(a + 1, N, b + 1), V(a + 1, N, b)))
            quads.append((V(a, b, 0), V(a, b + 1, 0), V(a + 1, b + 1, 0), V(a + 1, b, 0)))
            quads.append((V(a, b, N), V(a + 1, b, N), V(a + 1, b + 1, N), V(a, b + 1, N)))
    _CSPHERE[N] = (pts, quads)
    return _CSPHERE[N]


def _frac_planes(rr, sx, sy, sz, kind):
    """Planos (n, d, moldeado) de un fragmento: 'block' = caja con caras ladeadas, 0–2 caras de cimbra intactas y 3–6
    esquinas/aristas arrancadas; 'slab' = caras superior e inferior de cimbra (planas) + canto de fractura facetado."""
    P = []
    if kind == "slab":
        P.append((Vector((0, 0, 1)), sz / 2, True))
        P.append((Vector((0, 0, -1)), sz / 2, True))
        nv = int(rr.integers(6, 11))
        a0 = rr.uniform(0, 2 * PI)
        for i in range(nv):
            a = a0 + 2 * PI * (i + rr.uniform(-0.3, 0.3)) / nv
            tl = math.radians(rr.uniform(-28, 28))
            rad = 1.0 / math.sqrt((math.cos(a) / (sx / 2)) ** 2 + (math.sin(a) / (sy / 2)) ** 2) * rr.uniform(0.62, 1.0)
            n = Vector((math.cos(a) * math.cos(tl), math.sin(a) * math.cos(tl), math.sin(tl)))
            P.append((n, rad * math.cos(tl), False))
        return P
    half = (sx / 2, sy / 2, sz / 2)
    molded = set(int(i) for i in rr.choice(6, size=int(rr.integers(0, 3)), replace=False))
    for k in range(6):
        ax, sg = k // 2, (1 if k % 2 else -1)
        n = Vector((0.0, 0.0, 0.0))
        n[ax] = sg
        if k in molded:
            P.append((n, half[ax] * rr.uniform(0.9, 1.0), True))
            continue
        n = (n + Vector((rr.uniform(-1, 1), rr.uniform(-1, 1), rr.uniform(-1, 1))) * 0.3).normalized()
        P.append((n, half[ax] * rr.uniform(0.72, 1.0) * abs(n[ax]), False))
    for _ in range(int(rr.integers(3, 7))):
        sg = Vector((rr.choice([-1, 1]), rr.choice([-1, 1]), rr.choice([-1, 1])))
        if rr.random() < 0.4:  # arista arrancada en vez de esquina
            sg[int(rr.integers(0, 3))] = 0.0
        c = Vector((sg.x * half[0], sg.y * half[1], sg.z * half[2]))
        n = (Vector((sg.x / half[0], sg.y / half[1], sg.z / half[2])) + Vector((rr.uniform(-1, 1), rr.uniform(-1, 1),
                                                                                rr.uniform(-1, 1))) * 1.5).normalized()
        if n.dot(c) <= 1e-4:
            continue
        P.append((n, n.dot(c) * rr.uniform(0.55, 0.85), False))
    return P


def _frac_chunk(rr, size, kind, res=1.0, nzoff=None, nz=None):
    """Fragmento de fractura (MB local, centro en el origen): intersección de semiespacios (planos de fractura) muestreada
    con una esfera-cubo de cuadriláteros (rayos desde el centro: superficie estrellada, cerrada y soldada) + 1–2 cuencas
    concoideas cóncavas (esferas que muerden la superficie) + rugosidad de 3 octavas en las caras de fractura (las caras
    de cimbra quedan planas, material 'concrete'). Las aristas del poliedro caen entre vértices: quedan romas y rotas."""
    sx, sy, sz = size
    big = max(sx, sy, sz)
    planes = _frac_planes(rr, sx, sy, sz, kind)
    N = int(min(14, max(3, round((big / 0.032 + 2) * res * _lv(1.0, 0.5, 1.0)))))
    dirs, quads = _cube_sphere(N)
    sc = Vector((sx, sy, sz)) / big

    def ray(u):
        t, pid = 1e9, -1
        for i, (n, d, _) in enumerate(planes):
            c = n.dot(u)
            if c > 1e-6 and d / c < t:
                t, pid = d / c, i
        return t, pid

    scoops = []
    for _ in range(int(rr.integers(1, 3)) if big > 0.1 else 0):
        u = Vector((rr.uniform(-1, 1), rr.uniform(-1, 1), rr.uniform(-0.6, 0.6)))
        u = Vector((u.x * sc.x, u.y * sc.y, u.z * sc.z)).normalized()
        T, pid = ray(u)
        if planes[pid][2]:
            continue
        R = big * rr.uniform(0.28, 0.5)
        dep = min(T * 0.45, R * rr.uniform(0.25, 0.5))
        scoops.append((u * (T + R - dep), R))
    off = nzoff if nzoff is not None else Vector((rr.uniform(-50, 50), rr.uniform(-50, 50), rr.uniform(-50, 50)))
    if _LOD.level == "low":
        # 'low': el poliedro limpio de los planos de fractura (casco convexo de puntos sobre los planos, caras coplanares
        # fundidas): misma silueta y mismas caras de cimbra, sin rugosidad ni cuencas. ~20–60 triángulos.
        pts = [u * ray(u)[0] for u in (Vector((s_.x * sc.x, s_.y * sc.y, s_.z * sc.z)).normalized() for s_ in _cube_sphere(5)[0])]
        molded = [(n_, d_) for (n_, d_, mo_) in planes if mo_]

        def matfn(c, nn):
            return "concrete" if any(nn.dot(n_) > 0.995 and abs(c.dot(n_) - d_) < 0.01 * big for (n_, d_) in molded) else None
        tmp = MB()
        _hull(tmp, pts, "rubble", matfn=matfn, weld=0.012 * big)
        ext = max(max(v.co[a] for v in tmp.bm.verts) - min(v.co[a] for v in tmp.bm.verts) for a in range(3))
        if ext > big * 1.03:
            tmp.transform(Matrix.Diagonal((big / ext, big / ext, big / ext, 1.0)))
        return tmp
    amp = 0.03 * big + 0.0015
    f1 = 2.4 / big
    tmp = MB()
    vs, molded = [], []
    for s in dirs:
        u = Vector((s.x * sc.x, s.y * sc.y, s.z * sc.z)).normalized()
        t, pid = ray(u)
        mo = planes[pid][2]
        for (C, R) in scoops:
            b = u.dot(C)
            disc = b * b - (C.length_squared - R * R)
            if b > 0 and disc > 0:
                ti = b - math.sqrt(disc)
                if 0 < ti < t:
                    t, mo = ti, False
        vs.append(tmp.bm.verts.new(u * t))
        molded.append(mo)
    for q in quads:
        f = tmp.face([vs[i] for i in q], "concrete" if all(molded[i] for i in q) else "rubble")
    tmp.bm.normal_update()
    nrm = [v.normal.copy() for v in vs]
    for v, n, mo in zip(vs, nrm, molded):
        if mo:
            continue
        p = v.co + off
        k = nz(p, f1) + 0.5 * nz(p, f1 * 2.3) + 0.3 * abs(nz(p, f1 * 5.1))
        v.co -= n * amp * k
    # los planos ladeados agrandan la caja: reescala para que la dimensión mayor sea `big`
    ext = max(max(v.co[a] for v in vs) - min(v.co[a] for v in vs) for a in range(3))
    if ext > big * 1.03:
        tmp.transform(Matrix.Diagonal((big / ext, big / ext, big / ext, 1.0)))
    return tmp


def _concrete_chunk(mb, M, size, rr, nz, kind=None, dres=None, rebar=None, res=1.0):
    """Trozo de concreto (fragmento de fractura rugoso, ver `_frac_chunk`) con transformación M. size = (sx, sy, sz).
    dres (opcional) ajusta la resolución de la esfera-cubo. El nivel de detalle activo lo aplica `_frac_chunk`.
    Devuelve kind."""
    sx, sy, sz = size
    kind = kind or ("slab" if rr.random() < 0.35 else "block")
    if kind == "slab":
        sz = min(max(0.07, min(sz, 0.35 * min(sx, sy))), 0.2)
    big = max(sx, sy, sz)
    if dres is not None:
        res = res * (0.6 + 0.3 * dres)
    _merge(mb, _frac_chunk(rr, (sx, sy, sz), kind, res=res, nz=nz), M)
    if rebar or (rebar is None and kind == "slab" and big > 0.25 and rr.random() < 0.7):
        for k in range(int(rr.integers(1, 3))):
            a = rr.uniform(0, 2 * PI)
            p0 = Vector((math.cos(a) * sx * 0.2, math.sin(a) * sy * 0.2, rr.uniform(-0.3, 0.3) * sz))
            d0 = Vector((math.cos(a), math.sin(a), 0.0))
            pts = _rebar_path(rr, p0, d0, big * 0.5 + rr.uniform(0.1, 0.35), Vector((0, 0, rr.choice([-1, 1]))),
                              kind=rr.choice(["bent", "kink", "straight"]), step=0.006)
            _rebar(mb, [M @ p for p in pts], 0.0048)
    return kind


# =====================================================================================================================
# varillas expuestas
# =====================================================================================================================
def rebar_nest(seed=0, n=8, length=0.6, stump=(0.35, 0.35, 0.35), r=None, detail="high", seg=None, ribs=None):
    """Muñón de columna de concreto roto (0,35 × 0,35, fractura irregular con esquinas desprendidas) del que salen
    n varillas corrugadas de 8 lados (Ø 3/8"–1/2") dobladas en curva, en gancho o con quiebre seco, estribos (uno en su
    lugar, otro zafado y abierto) y pedazos de concreto aún pegados. Origen: centro de la base del muñón (z = 0).
    detail: high / mid / low = 28,5 / 3,3 / 1,25 k con n = 8, length = 0,6 (≈ 2,9 k / 0,3 k / 0,1 k por varilla).
    mid / low: varillas lisas de 5 / 4 lados simplificadas (el corrugado no se lee a > 3 m), muñón a paso × 2 / × 5.
    Control fino: n (varillas), seg (lados de varilla), ribs (forzar o quitar el corrugado)."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        mb = MB()
        W, Dp, H = stump
        hw, hd = W / 2, Dp / 2

        band = min(0.16, 0.45 * H)
        H0 = H - band
        # desconches en las aristas verticales (esquina, z, radio, profundidad) y núcleo más alto que el recubrimiento
        chips = [(int(rr.integers(0, 4)), rr.uniform(0.06, max(0.07, H0 - 0.08)), rr.uniform(0.03, 0.07), rr.uniform(0.008, 0.022))
                 for _ in range(int(rr.integers(2, 5)))]
        corners = [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]

        def top_h(x, y):
            e = max(abs(x) / hw, abs(y) / hd)
            p3 = Vector((x, y, 0))
            h = (H + 0.04 * nz(p3, 6.0) + 0.016 * nz(p3 + Vector((0, 0, 3)), 19.0) + 0.006 * nz(p3 + Vector((0, 0, 7)), 47.0)
                 - 0.07 * _smooth((e - 0.5) / 0.5) * (0.7 + 0.6 * (0.5 + 0.5 * nz(p3 + Vector((0, 0, 11)), 9.0))))
            return max(h, H0 + 0.035)

        def push_at(x, y):  # cuánto se ha caído el recubrimiento en el borde superior (2–4,5 cm)
            return 0.02 + 0.025 * (0.5 + 0.5 * nz(Vector((x, y, 5)), 7.0))

        def hdir(p):
            cx = min(max(p.x, -hw + 0.07), hw - 0.07)
            cy = min(max(p.y, -hd + 0.07), hd - 0.07)
            d = Vector((p.x - cx, p.y - cy, 0.0))
            return d.normalized() if d.length > 1e-9 else Vector((0, 0, 0))

        def deform(p, nrm):
            q = p.copy()
            top = nrm.z > 0.7
            if top or p.z > H0:
                # banda de fractura: sube hasta la línea de rotura y el recubrimiento se cae (sin aleros: la cara superior
                # recibe el mismo empuje hacia dentro que el último anillo del costado)
                e = max(abs(p.x) / hw, abs(p.y) / hd)
                t = 1.0 if top else (p.z - H0) / band
                w = _smooth((e - 0.6) / 0.4) if top else 1.0
                ht = top_h(p.x, p.y)
                q.z = ht if top else H0 + t * (ht - H0)
                d = hdir(p)
                q -= d * push_at(p.x, p.y) * (t ** 1.6) * w
                q += Vector((nrm.x, nrm.y, 0)) * (-0.006 * abs(nz(p, 23.0)) * t)
            else:
                q -= nrm * (0.0012 * nz(p, 7.0) + 0.0012 * abs(nz(p, 31.0)))
                for (ci, zc, R, dep) in chips:
                    cx, cy = corners[ci]
                    dd = math.sqrt((p.x - cx) ** 2 + (p.y - cy) ** 2 + ((p.z - zc) * 0.7) ** 2)
                    if dd < R:
                        q -= hdir(p) * dep * (1 - dd / R) ** 1.5 * (0.7 + 0.3 * nz(p, 40.0))
            return q

        body = _lattice((-hw, -hd, 0.0), (hw, hd, H), r=0.012, step=0.016, mat="concrete", deform=deform,
                        matfn=lambda c, nn: "rubble" if c.z > H0 + 0.02 else None)
        _merge(mb, body)
        # varillas: esquinas + intermedias
        cov = 0.045
        perim = []
        cx_, cy_ = hw - cov, hd - cov
        ring = [(-cx_, -cy_), (cx_, -cy_), (cx_, cy_), (-cx_, cy_)]
        if n <= 4:
            perim = ring[:n]
        else:
            perim = list(ring)
            extra = n - 4
            mids = [((ring[i][0] + ring[(i + 1) % 4][0]) / 2, (ring[i][1] + ring[(i + 1) % 4][1]) / 2) for i in range(4)]
            k = 0
            while len(perim) < n:
                perim.append(mids[k % 4] if k < 4 else (mids[k % 4][0] * rr.uniform(0.4, 0.8), mids[k % 4][1] * rr.uniform(0.4, 0.8)))
                k += 1
        kinds = ["bent", "bent", "bent", "hook", "kink", "straight"]
        tips = []
        for i, (bx, by) in enumerate(perim):
            rb = r or (0.0064 if (i < 4) else 0.0048)
            out = Vector((bx, by, 0.0))
            out = out.normalized() if out.length > 1e-6 else Vector((1, 0, 0))
            bend = (out * rr.uniform(0.4, 1.0) + Vector((rr.uniform(-1, 1), rr.uniform(-1, 1), 0)) * 0.6).normalized()
            L = length * rr.uniform(0.55, 1.15)
            kind = kinds[int(rr.integers(0, len(kinds)))]
            if rr.random() < 0.12:
                L *= rr.uniform(0.2, 0.4)  # varilla cortada
            z0 = H - 0.14
            straight_in = [Vector((bx, by, z0)), Vector((bx, by, top_h(bx, by) - 0.01))]
            lean = Vector((rr.uniform(-0.03, 0.03), rr.uniform(-0.03, 0.03), 1.0)).normalized()
            pts = _rebar_path(rr, straight_in[-1], lean, L, bend, kind=kind)
            pts = _resample(straight_in, 0.006)[:-1] + pts
            _rebar(mb, pts, rb, ribs=ribs, seg=seg)
            tips.append(pts)
        # estribos: uno en su lugar justo sobre la fractura, otro zafado e inclinado
        ex = cx_ + 0.0064 + 0.0035
        ey = cy_ + 0.0064 + 0.0035
        zf = H + 0.06
        _stirrup(mb, 0.0, 0.0, H - 0.07, ex, ey, rr)
        _stirrup(mb, 0.0, 0.0, zf, ex + 0.004, ey + 0.004, rr, tilt=(rr.uniform(-6, 6), rr.uniform(-6, 6)), open_=0.0)
        _stirrup(mb, rr.uniform(-0.02, 0.02), rr.uniform(-0.02, 0.02), zf + rr.uniform(0.08, 0.16), ex + 0.01, ey + 0.01, rr,
                 tilt=(rr.uniform(-25, 25), rr.uniform(-25, 25)), open_=rr.uniform(0.03, 0.08))
        # pedazos de concreto aún pegados a 1–2 varillas
        for _ in range(int(rr.integers(1, 3))):
            pts = tips[int(rr.integers(0, len(tips)))]
            p = pts[min(len(pts) - 1, int(len(pts) * rr.uniform(0.25, 0.45)))]
            s = rr.uniform(0.04, 0.07)
            _concrete_chunk(mb, _T(p) @ _R("Z", rr.uniform(0, 360)) @ _R("X", rr.uniform(0, 360)), (s, s * 0.8, s * 0.6), rr, nz,
                            kind="block", dres=1, rebar=False)
        _declump(mb)
        return mb


# =====================================================================================================================
# escombro
# =====================================================================================================================
def _brick(mb, M, rr, broken=False):
    """Ladrillo 0,24 × 0,12 × 0,06 con bisel de 4 mm; broken: medio ladrillo con el extremo roto (casco)."""
    if not broken:
        _box(mb, (-0.12, -0.06, -0.03), (0.12, 0.06, 0.03), "brick", bevel=0.004, seg=1, m=M)
        return
    Lb = rr.uniform(0.08, 0.17)
    pts = []
    for sx in (-1,):
        for sy in (-1, 1):
            for sz in (-1, 1):
                for e in ((0.004, 0, 0), (0, 0.004, 0), (0, 0, 0.004)):
                    pts.append((-0.12 + e[0], sy * (0.06 - e[1]), sz * (0.03 - e[2])))
    for _ in range(10):
        pts.append((-0.12 + Lb + rr.uniform(-0.035, 0.035), rr.uniform(-0.06, 0.06), rr.uniform(-0.03, 0.03)))
    for sy in (-1, 1):
        for sz in (-1, 1):
            pts.append((-0.12 + Lb * rr.uniform(0.5, 0.9), sy * 0.06, sz * 0.03))
    _hull(mb, pts, "brick", m=M)


def rubble_pile(radius=1.0, seed=0, n=60, detail="high", gravel=2.5):
    """Montón de escombro: base de cascajo/arena con perfil de talud irregular y n trozos de concreto (cascos convexos
    rugosos, losas con varilla) APILADOS con un campo de alturas (cada pieza descansa sobre las anteriores), ladrillos
    enteros y rotos, grava y varillas dobladas asomando.
    Origen: centro del montón sobre el piso (la base se entierra 2 cm, z = -0,02).
    detail: high / mid / low = 50 / 13,3 / 5,6 k con radius = 1, n = 60 y 93 / 24 / 8,4 k con radius = 1,6, n = 90.
    mid: trozos con la mitad de resolución y 1 de cada 2 piedras de grava; low: cada trozo es el poliedro limpio de sus
    planos de fractura (20–60 triángulos) y 1 de cada 4 piedras. Control fino: n (trozos) y gravel (piedras por trozo)."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        mb = MB()
        R = float(radius)
        Hm = 0.26 * R * rr.uniform(0.85, 1.15)  # base de finos; los trozos apilados hacen el resto del talud
        rad_n = [rr.uniform(0.85, 1.15) for _ in range(7)]

        def Rth(a):
            k = (a % (2 * PI)) / (2 * PI) * 7
            i = int(k)
            t = _smooth(k - i)
            return R * (rad_n[i % 7] * (1 - t) + rad_n[(i + 1) % 7] * t)

        pk = Vector((rr.uniform(-0.2, 0.2) * R, rr.uniform(-0.2, 0.2) * R, 0))
        bumps = [(rr.uniform(-0.55, 0.55) * R, rr.uniform(-0.55, 0.55) * R, rr.uniform(0.15, 0.35) * R, rr.uniform(0.06, 0.16) * R)
                 for _ in range(int(rr.integers(2, 5)))]

        def hgt(x, y):
            a = math.atan2(y - pk.y * 0.0, x - pk.x * 0.0)
            rr_ = math.hypot(x, y) / Rth(a)
            off = math.hypot(x - pk.x, y - pk.y) / max(R, 1e-6)
            base = Hm * max(0.0, 1.0 - min(rr_, 1.0) ** 1.6) ** 1.4 * (1.0 - 0.35 * off)
            edge = min(1.0, (1 - min(rr_, 1.0)) * 4)
            bmp = sum(h * math.exp(-((x - bx) ** 2 + (y - by) ** 2) / (w * w)) for (bx, by, w, h) in bumps)
            return base + edge * (bmp + 0.045 * R * nz(Vector((x, y, 0)), 3.0 / R) + 0.015 * nz(Vector((x, y, 5)), 9.0)
                                  + 0.012 * nz(Vector((x, y, 9)), 23.0))

        nr, ns = _lv((14, 56), (9, 36), (6, 22))
        center = mb.bm.verts.new((0.0, 0.0, hgt(0.0, 0.0)))
        rings = []
        ts = [(i / nr) ** 0.85 for i in range(1, nr)] + [0.985, 1.0, 1.035]
        for i, t in enumerate(ts):
            ring = []
            for k in range(ns):
                a = 2 * PI * k / ns
                Ra = Rth(a)
                x, y = Ra * t * math.cos(a), Ra * t * math.sin(a)
                if t > 1.02:
                    z = -0.025
                else:
                    z = hgt(x, y) - 0.016 * _smooth((t - 0.8) / 0.2) + 0.006 * nz(Vector((x, y, 3)), 13.0)
                ring.append(mb.bm.verts.new((x, y, z)))
            rings.append(ring)
        nr = len(rings)
        for k in range(ns):
            mb.face([center, rings[0][k], rings[0][(k + 1) % ns]], "rubble")
        for i in range(nr - 1):
            for k in range(ns):
                kk = (k + 1) % ns
                f = mb.face([rings[i][k], rings[i + 1][k], rings[i + 1][kk], rings[i][kk]], "rubble")
                if nz(f.calc_center_median(), 2.5) > 0.25:
                    f.material_index = mb.mi("sand")
        mb.face(list(reversed(rings[-1])), "rubble")
        # campo de alturas (5 cm) para APILAR: cada trozo se apoya sobre lo ya colocado (los grandes primero)
        cell = 0.05
        org = -1.15 * R
        G = int(2.3 * R / cell) + 2
        hf = [[max(hgt(org + i * cell, org + j * cell), 0.0) if math.hypot(org + i * cell, org + j * cell) < Rth(
            math.atan2(org + j * cell, org + i * cell)) else 0.0 for j in range(G)] for i in range(G)]

        def cells(x, y, rad):
            i0, i1 = max(0, int((x - rad - org) / cell)), min(G - 1, int((x + rad - org) / cell) + 1)
            j0, j1 = max(0, int((y - rad - org) / cell)), min(G - 1, int((y + rad - org) / cell) + 1)
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    d = math.hypot(org + i * cell - x, org + j * cell - y)
                    if d <= rad:
                        yield i, j, d

        def hf_at(x, y, rad):
            vals = [hf[i][j] for (i, j, _) in cells(x, y, rad)]
            return max(vals) if vals else 0.0

        smax = min(0.55, 0.42 * R)
        smin = 0.05
        sizes = sorted([smin * (smax / smin) ** (rr.random() ** 1.3) for _ in range(n)], reverse=True)
        for s in sizes:
            a = rr.uniform(0, 2 * PI)
            d = Rth(a) * 0.85 * (rr.random() ** 0.7) * (0.7 if s > 0.3 else 1.0)
            x, y = d * math.cos(a), d * math.sin(a)
            roll = rr.random()
            yaw = rr.uniform(0, 360)
            tilt = (rr.uniform(-28, 28), rr.uniform(-28, 28))
            rot = _R("Z", yaw) @ _R("X", tilt[0]) @ _R("Y", tilt[1])
            if roll < 0.2 and s < 0.25:
                base = hf_at(x, y, 0.08)
                _brick(mb, _T(x, y, base + 0.02) @ rot, rr, broken=rr.random() < 0.5)
                for (i, j, dd) in cells(x, y, 0.1):
                    hf[i][j] = max(hf[i][j], base + 0.05 * (1 - dd / 0.1))
                continue
            sx, sy, sz = s, s * rr.uniform(0.55, 1.0), s * rr.uniform(0.35, 0.8)
            fr = 0.42 * max(sx, sy)
            base = hf_at(x, y, fr * 0.6)
            zc = base + sz * rr.uniform(0.05, 0.35)
            kind = _concrete_chunk(mb, _T(x, y, zc) @ rot, (sx, sy, sz), rr, nz)
            top = zc + (min(sz, 0.2) if kind == "slab" else sz) * 0.4
            for (i, j, dd) in cells(x, y, fr):
                hf[i][j] = max(hf[i][j], top - (top - base) * (dd / fr) ** 2 * 0.8)
        # grava y cascajo fino sobre la superficie
        gstep = _lv(1, 2, 4)  # mid / low: se construye 1 de cada 2 / 4 piedras (la semilla se consume igual)
        for gi in range(int(n * gravel)):
            a = rr.uniform(0, 2 * PI)
            d = Rth(a) * 1.2 * math.sqrt(rr.random())
            x, y = d * math.cos(a), d * math.sin(a)
            g = rr.uniform(0.012, 0.04) * (0.6 if d > Rth(a) else 1.0)
            c = Vector((x, y, max(hgt(x, y), hf_at(x, y, 0.03) - 0.02, 0.0) + g * 0.15))
            gp = [c + Vector((rr.uniform(-1, 1), rr.uniform(-1, 1), rr.uniform(-0.6, 0.6))).normalized() * g * rr.uniform(0.5, 1.0)
                  for _ in range(8)]
            gm = "rubble" if rr.random() < 0.75 else "brick"
            if gi % gstep == 0:
                _hull(mb, gp, gm)
        # varillas sueltas asomando
        for _ in range(max(2, n // 15)):
            a = rr.uniform(0, 2 * PI)
            d = Rth(a) * rr.uniform(0.1, 0.7)
            x, y = d * math.cos(a), d * math.sin(a)
            p0 = Vector((x, y, hf_at(x, y, 0.05) - 0.12))
            dirv = Vector((rr.uniform(-0.6, 0.6), rr.uniform(-0.6, 0.6), 1.0)).normalized()
            pts = _rebar_path(rr, p0, dirv, rr.uniform(0.3, 0.9), Vector((math.cos(a), math.sin(a), 0)),
                              kind=rr.choice(["bent", "kink", "hook", "straight"]))
            _rebar(mb, pts, rr.choice([0.0048, 0.0064]))
        _declump(mb)
        return mb


def chunk(size=0.3, seed=0, kind=None, detail="high"):
    """Trozo suelto e irregular de concreto (casco convexo rugoso). size: escalar (dimensión mayor) o (sx, sy, sz).
    kind: 'block' (pedazo macizo de esquinas cortadas), 'slab' (pedazo de losa con caras moldeadas planas y, si es
    grande, varilla asomando) o None (al azar). Origen: centro en planta, z = 0 en su punto más bajo (se apoya en el piso;
    para escombro colgante o desconches usar la matriz que convenga).
    detail: high / mid / low = 2,4 / 0,8 / 0,09 k para 0,45 m (low = poliedro limpio de los planos de fractura)."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        if isinstance(size, (int, float)):
            s = float(size)
            size = (s, s * rr.uniform(0.6, 0.95), s * rr.uniform(0.4, 0.75))
        tmp = MB()
        _concrete_chunk(tmp, Matrix.Identity(4), tuple(size), rr, nz, kind=kind)
        zmin = min(v.co.z for v in tmp.bm.verts)
        tmp.transform(_T(0, 0, -zmin))
        _declump(tmp)
        return tmp


# =====================================================================================================================
# mordidas de arista
# =====================================================================================================================
def _bite_k():
    return _lv(12, 8, 5)


class _Bite:
    """Perfil de una mordida a lo largo de una arista canónica (arista en +X, x = 0..L; d1 = distancia hacia dentro desde
    la cara 1 (y = 0), d2 = distancia hacia dentro desde la cara 2 (z = 0)). Fuera de la mordida el perfil es el chaflán
    redondo de radio b (mismo perfil que MB.box(bevel=b, seg=2)), así empalma con la arista sana."""

    K = 12  # estaciones del perfil en 'high' (mid 8, low 5: ver _bite_k)

    def __init__(self, L, D, b, rr, nz):
        self.K = _bite_k()
        self.L, self.D, self.b, self.nz = L, D, min(b, 0.3 * D), nz
        self.Dp = D - 0.001
        self.BY, self.BZ = self.Dp * rr.uniform(0.8, 0.98), self.Dp * rr.uniform(0.8, 0.98)
        self.xa = L * rr.uniform(0.04, 0.2)
        self.xb = L * rr.uniform(0.8, 0.96)
        self.ramp = max(0.03, min(0.15, (self.xb - self.xa) * 0.25))

    def env(self, x):
        if x <= self.xa or x >= self.xb:
            return 0.0
        w = _smooth((x - self.xa) / self.ramp) * _smooth((self.xb - x) / self.ramp)
        return w * (0.72 + 0.28 * (0.5 + 0.5 * self.nz(Vector((x, 0, 0)), 6.0)))

    def curve(self, x, guard=0.004):
        """[(d1, d2)] desde la cara 2 (d2 = 0) hasta la cara 1 (d1 = 0), con un punto guarda sobre cada cara."""
        b, Dp, nz = self.b, self.Dp, self.nz
        w = self.env(x)
        by = b + (self.BY - b) * w * (1 + 0.3 * nz(Vector((x, 1, 0)), 14.0) + 0.12 * nz(Vector((x, 1, 5)), 45.0))
        bz = b + (self.BZ - b) * w * (1 + 0.3 * nz(Vector((x, 2, 0)), 14.0) + 0.12 * nz(Vector((x, 2, 5)), 45.0))
        by, bz = min(by, Dp - 0.012), min(bz, Dp - 0.012)
        out = [(by + guard, 0.0)]
        K = self.K
        for k in range(K + 1):
            sp = k / K
            be = math.radians(90 + 90 * sp)
            pb = Vector((b + b * math.cos(be), b - b * math.sin(be)))
            g = PI / 2 * sp
            # superelipse: paredes de rotura empinadas junto a las caras y fondo plano a la altura de la varilla
            ps = Vector((by * math.cos(g) ** 0.55, bz * math.sin(g) ** 0.55))
            q = pb.lerp(ps, w)
            inward = (Vector((Dp, Dp)) - q).normalized()
            rough = 0.018 * nz(Vector((x, sp * 0.6, 0)), 15.0) + 0.009 * nz(Vector((x, sp, 7)), 34.0)
            rough = math.copysign(abs(rough) ** 0.8 * 0.05 ** 0.2, rough)  # crestas más marcadas
            q = q + inward * rough * w * math.sin(PI * sp)
            out.append((min(max(q.x, 0.0), Dp - 0.006), min(max(q.y, 0.0), Dp - 0.006)))
        out.append((0.0, bz + guard))
        return out

    def details(self, mb, rr, cover=0.035, bar_r=0.0064, stirrup_every=0.18, aggregate=True, x_ext=(0.004, None)):
        """Varilla longitudinal corrugada, esquinas de estribo y agregado grueso, en coordenadas canónicas
        (y = d1, z = -d2)."""
        L, Dp, nz = self.L, self.Dp, self.nz
        cover = min(cover, 0.42 * self.D)
        xe0 = x_ext[0]
        xe1 = L - 0.004 if x_ext[1] is None else x_ext[1]
        bar = []
        x = xe0
        while x <= xe1 + 1e-9:
            push = 0.004 * self.env(x)
            bar.append(Vector((x, cover - push * 0.7, -cover + push * 0.7)))
            x += 0.006
        _rebar(mb, bar, bar_r)
        rs = 0.0032
        c2 = cover - bar_r - rs - 0.0005
        xs = stirrup_every * rr.uniform(0.3, 0.8)
        while xs < L - 0.04:
            pull = 0.006 * self.env(xs) * rr.uniform(0.3, 1.0)
            path = _fillet([(xs, c2 - pull, -(Dp - 0.006)), (xs, c2 - pull, -c2 + pull), (xs, Dp - 0.006, -c2 + pull)], 0.016, 6)
            _tube(mb, _resample(path, 0.01), rs, seg=8, mat="metal_rust")
            xs += stirrup_every * rr.uniform(0.85, 1.15)
        if aggregate:
            astep = _lv(1, 2, 4)  # mid / low: 1 de cada 2 / 4 piedras de agregado (la semilla se consume igual)
            for ai in range(int((self.xb - self.xa) * 24)):
                x = rr.uniform(self.xa + self.ramp * 0.5, self.xb - self.ramp * 0.5)
                if self.env(x) < 0.35:
                    continue
                c = self.curve(x)
                k12 = int(rr.integers(3, 12))  # sorteo con el rango de 'high' (K = 12) y se lleva al K del nivel
                d1, d2 = c[max(1, min(self.K, int(round(k12 * self.K / 12))))]
                inward = (Vector((Dp, Dp)) - Vector((d1, d2))).normalized()
                rad = rr.uniform(0.006, 0.016)
                ctr = Vector((x, d1 + inward.x * rad * 0.45, -(d2 + inward.y * rad * 0.45)))
                pts = [ctr + Vector((rr.uniform(-1, 1), rr.uniform(-1, 1), rr.uniform(-1, 1))).normalized() * rad * rr.uniform(0.6, 1.0)
                       for _ in range(9)]
                if ai % astep == 0:
                    _hull(mb, pts, "rubble")


def spall_edge(length, depth, seed=0, edge_bevel=0.015, cover=0.035, bar_r=0.0064, stirrup_every=0.18, aggregate=True,
               detail="high"):
    """Pieza de reemplazo de una arista desconchada ("mordida"): prisma de esquina con perfil irregular de fractura,
    varilla longitudinal corrugada expuesta (recubrimiento `cover` al eje) y esquinas de estribo cada `stirrup_every`.
    Coordenadas y uso: ver la docstring del módulo (arista en +X, caras del anfitrión y = 0 y z = 0, la pieza llena
    y ∈ [0, depth), z ∈ (-depth, 0]). Queda una junta de 1 mm con el anfitrión (se lee como grieta). Para un empalme
    soldado sin junta usar `spalled_box`, que integra la mordida en el sólido del anfitrión.
    detail: high / mid / low = 8,4 / 1,7 / 0,7 k para 1,2 × 0,12 (estaciones cada 1,5 / 3 / 6 cm, perfil de 12 / 8 / 5
    puntos, varilla lisa en mid / low, 1 de cada 2 / 4 piedras de agregado)."""
    with _detail(detail):
        rr = rng(seed)
        nz = _Nz(rr)
        mb = MB()
        L, D = float(length), float(depth)
        bite = _Bite(L, D, edge_bevel, rr, nz)
        Dp = bite.Dp
        nst = max(8, int(L / _lv(0.015, 0.03, 0.06)))
        rings = []
        x0, x1 = 0.001, L - 0.001
        for i in range(nst + 1):
            x = x0 + (x1 - x0) * i / nst
            prof = [(Dp, 0.0)] + bite.curve(x) + [(0.0, Dp), (Dp, Dp)]
            rings.append([mb.bm.verts.new((x, d1, -d2)) for (d1, d2) in prof])
        m = len(rings[0])
        K = bite.K
        for i in range(nst):
            A, B = rings[i], rings[i + 1]
            for k in range(m):
                kk = (k + 1) % m
                f = mb.face([A[k], A[kk], B[kk], B[k]], "concrete")
                if 2 <= k <= K + 1 and bite.env(A[k].co.x) > 0.05:
                    f.material_index = mb.mi("rubble")
        mb.face(list(reversed(rings[0])), "concrete")
        mb.face(rings[-1], "concrete")
        bite.details(mb, rr, cover=cover, bar_r=bar_r, stirrup_every=stirrup_every, aggregate=aggregate)
        _declump(mb)
        return mb


_AX = {"x": (0, (1, 2)), "y": (1, (0, 2)), "z": (2, (0, 1))}


def spall_matrix(mn, mx, axis, sides, start):
    """Matriz que lleva `spall_edge` (arista en +X, caras y = 0 / z = 0) a la arista de la caja (mn, mx) indicada.
    axis: 'x' | 'y' | 'z'; sides = signos de los otros dos ejes (ver docstring del módulo); start: inicio de la mordida
    medido DESDE mn[axis] a lo largo del eje."""
    ai, (e1, e2) = _AX[axis]
    s1, s2 = sides
    E = [Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))]
    X = E[ai]
    Y = E[e1] * (-s1)
    Z = E[e2] * s2
    o = Vector((0.0, 0.0, 0.0))
    o[ai] = mn[ai] + start
    o[e1] = mn[e1] if s1 < 0 else mx[e1]
    o[e2] = mn[e2] if s2 < 0 else mx[e2]
    return Matrix(((X.x, Y.x, Z.x, o.x), (X.y, Y.y, Z.y, o.y), (X.z, Y.z, Z.z, o.z), (0, 0, 0, 1)))


def spalled_box(mb, mn, mx, spalls, mat="concrete", bevel=0.015, seg=2, detail="high"):
    """Caja anfitriona (losa, viga, columna) CON mordidas de arista, como UN SOLO sólido soldado, sin booleanos ni
    juntas. Escribe en `mb` y lo devuelve.
    spalls: lista de dict(axis, sides, start, length, depth[, seed]) — ver docstring del módulo. Todas las mordidas van
    sobre aristas paralelas al MISMO eje; en una misma esquina no deben traslaparse.
    Construcción: barrido (loft) a lo largo del eje de una sección = rectángulo con sus 4 esquinas, cada una con el
    chaflán redondo de radio `bevel` o con el perfil de mordida donde la hay; estaciones cada 1,5 cm dentro de las
    mordidas; los extremos de la caja llevan su propio redondeo (3 estaciones) y tapa. Varillas, estribos y agregado
    expuestos se agregan con la misma convención que `spall_edge`.
    detail: high / mid / low = 29 / 8,3 / 3,4 k para una losa de 3,6 m con 2 mordidas y 23,6 / 6,9 / 2,9 k para una
    columna de 2,6 m con 2 mordidas (mismos recortes que spall_edge)."""
    with _detail(detail):
        mn, mx = _v(mn), _v(mx)
        if not spalls:
            _box(mb, tuple(mn), tuple(mx), mat, bevel=bevel, seg=seg)
            return mb
        axis = spalls[0]["axis"]
        ai, (e1, e2) = _AX[axis]
        b = min(bevel, 0.3 * min(mx[q] - mn[q] for q in range(3)))
        corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]  # recorrido antihorario en (e1, e2)
        bites = {c: [] for c in corners}
        ext = {e1: mx[e1] - mn[e1], e2: mx[e2] - mn[e2]}
        depths = []
        for i, sp in enumerate(spalls):
            assert sp["axis"] == axis, "spalled_box: todas las mordidas deben ir sobre aristas del mismo eje"
            dep = min(float(sp["depth"]), 0.9 * min(ext.values()))
            # dos mordidas en esquinas vecinas (comparten cara) que se traslapan a lo largo del eje: que no se crucen
            s0, s1_ = float(sp["start"]), float(sp["start"]) + float(sp["length"])
            for j, o in enumerate(spalls):
                if j == i or not (float(o["start"]) < s1_ and s0 < float(o["start"]) + float(o["length"])):
                    continue
                a, c = tuple(sp["sides"]), tuple(o["sides"])
                for q, ax_ in ((0, e1), (1, e2)):  # comparten la cara normal a e2 (limita a lo largo de e1) o la normal a e1
                    if a[1 - q] == c[1 - q] and a[q] != c[q]:
                        lim = ext[ax_] - 0.03
                        tot = dep + float(o["depth"])
                        if tot > lim:
                            dep = dep * lim / tot
            depths.append(dep)
        for sp, dep in zip(spalls, depths):
            rr = rng(sp.get("seed", 0))
            nz = _Nz(rr)
            bt = _Bite(float(sp["length"]), dep, b, rr, nz)
            bites[tuple(sp["sides"])].append((mn[ai] + float(sp["start"]), bt, rr))
        a0, a1 = mn[ai], mx[ai]
        e = 0.7 * b
        st = {a0, a0 + 0.293 * e, a0 + e, a1 - e, a1 - 0.293 * e, a1}
        for c in corners:
            for (s0, bt, _) in bites[c]:
                n = max(8, int(bt.L / _lv(0.015, 0.03, 0.06)))
                st |= {min(max(s0 + bt.L * i / n, a0 + e + 0.002), a1 - e - 0.002) for i in range(n + 1)}
        st = sorted(st)
        K = _bite_k()
        flat_bevel = [(b + b * math.cos(math.radians(90 + 90 * k / K)), b - b * math.sin(math.radians(90 + 90 * k / K)))
                      for k in range(K + 1)]
        flat_bevel = [(flat_bevel[0][0] + 0.004, 0.0)] + flat_bevel + [(0.0, flat_bevel[-1][1] + 0.004)]
        host = MB()
        rings, ring_bite = [], []
        for x in st:
            inset = 0.0
            if x < a0 + e - 1e-9:
                th = math.acos(max(-1.0, min(1.0, 1 - (x - a0) / e))) if e > 0 else PI / 2
                inset = e * (1 - math.sin(th))
            elif x > a1 - e + 1e-9:
                th = math.acos(max(-1.0, min(1.0, 1 - (a1 - x) / e))) if e > 0 else PI / 2
                inset = e * (1 - math.sin(th))
            ring, flags = [], []
            for (s1, s2) in corners:
                curve, bitten = flat_bevel, False
                for (s0, bt, _) in bites[(s1, s2)]:
                    if s0 < x < s0 + bt.L:
                        curve, bitten = bt.curve(x - s0), bt.env(x - s0) > 0.05
                        break
                uc = mn[e1] if s1 < 0 else mx[e1]
                vc = mn[e2] if s2 < 0 else mx[e2]
                pts = curve if s1 != s2 else list(reversed(curve))
                for (d1, d2) in pts:
                    co = Vector((0.0, 0.0, 0.0))
                    co[ai] = x
                    co[e1] = uc - s1 * (d1 + inset)
                    co[e2] = vc - s2 * (d2 + inset)
                    ring.append(host.bm.verts.new(co))
                    flags.append(bitten)
            rings.append(ring)
            ring_bite.append(flags)
        m = len(rings[0])
        nper = K + 3
        for i in range(len(rings) - 1):
            A, B = rings[i], rings[i + 1]
            for k in range(m):
                kk = (k + 1) % m
                f = host.face([A[k], A[kk], B[kk], B[k]], mat)
                j = k % nper
                if ring_bite[i][k] and ring_bite[i + 1][k] and 1 <= j <= nper - 2:
                    f.material_index = host.mi("rubble")
        host.face(list(reversed(rings[0])), mat)
        host.face(rings[-1], mat)
        _merge(mb, host)
        for c in corners:
            for (s0, bt, rr) in bites[c]:
                det = MB()
                bt.details(det, rr)
                _merge(mb, det, spall_matrix(mn, mx, axis, c, s0 - mn[ai]))
        return mb
