"""kit/clinic_oficina.py — mobiliario de oficina/servicio del hospital rural HOS_1 rehecho a calidad AAA (regla R-AAA).

Mismas firmas, origen, orientación y tamaño que las piezas de kit/clinic.py (piso en z = 0, frente hacia -Y; las piezas de
muro con el origen en la cara del muro y creciendo hacia -Y). Cada pieza se arma con su construcción real: lámina formada con
cantos redondeados (perfiles barridos con extremos redondeados), uniones, tornillos, holguras de 3-4 mm entre frentes, cantos
de PVC, ruedas, regatones; lo blando (cojines, toalla, papeles) con malla subdividida y deformada.

Piezas: desk, filing_cabinet, counter, folding_chair, office_chair, bedside_cabinet, notice_board, clock, potted_plant.
Materiales: solo los nombres existentes del kit (steel, aluminium, plastic, plastic_blue, sign_*, rubber, cable, glass, enamel,
vinyl, paper, linen, wood_varnish, wood_dark, paint_*, concrete, vegetation).
"""
import math

import bpy  # noqa: F401  (bpy antes que mathutils)
import numpy as np
from mathutils import Matrix, Vector

from kit import port
from kit.clinic import MB, _Rx, _Ry, _Rz, _T, fillet, rbox, rr_profile, rtube, zloft
from kit.common import rng

PI = math.pi

# matrices de reorientación para loft_x (el loft corre a lo largo de X local; perfil en (Y, Z) locales)
LZ = Matrix(((0, 1, 0, 0), (0, 0, 1, 0), (1, 0, 0, 0), (0, 0, 0, 1)))   # loft a lo largo de Z mundo; perfil en (X, Y) mundo
LY = Matrix(((0, 1, 0, 0), (1, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))   # loft a lo largo de Y mundo; perfil en (X, Z) mundo


# ======================================================================================================== utilidades 2D
def _dedupe(pts, eps=1e-7):
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > eps:
            out.append((float(p[0]), float(p[1])))
    while len(out) > 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) <= eps:
        out.pop()
    return out


def _area(pts):
    return 0.5 * sum(pts[i - 1][0] * pts[i][1] - pts[i][0] * pts[i - 1][1] for i in range(len(pts)))


def _ccw(pts):
    return pts if _area(pts) > 0 else pts[::-1]


def fillet2d(pts, r, n=4):
    """Polígono 2D cerrado con las esquinas redondeadas (arco circular real); r escalar o lista por vértice."""
    N = len(pts)
    rs = list(r) if isinstance(r, (list, tuple)) else [r] * N
    out = []
    for i in range(N):
        a, b, c = Vector((*pts[i - 1], 0)), Vector((*pts[i], 0)), Vector((*pts[(i + 1) % N], 0))
        if rs[i] <= 0:
            out.append((b.x, b.y))
            continue
        d0, d1 = (a - b), (c - b)
        if d0.length < 1e-9 or d1.length < 1e-9:
            out.append((b.x, b.y))
            continue
        d0.normalize()
        d1.normalize()
        ang = d0.angle(d1)
        if ang > PI - 1e-3 or ang < 1e-3:
            out.append((b.x, b.y))
            continue
        t = rs[i] / math.tan(ang / 2)
        t = min(t, (a - b).length * 0.49, (c - b).length * 0.49)
        rr = t * math.tan(ang / 2)
        bis = (d0 + d1).normalized()
        ctr = b + bis * (rr / math.sin(ang / 2))
        p0, p1 = b + d0 * t, b + d1 * t
        a0 = math.atan2(p0.y - ctr.y, p0.x - ctr.x)
        a1 = math.atan2(p1.y - ctr.y, p1.x - ctr.x)
        da = (a1 - a0 + PI) % (2 * PI) - PI
        for k in range(n + 1):
            aa = a0 + da * k / n
            out.append((ctr.x + rr * math.cos(aa), ctr.y + rr * math.sin(aa)))
    return _dedupe(out)


def offset_ring(pts, d):
    """Desplaza un polígono CCW `d` hacia fuera (d < 0: hacia dentro), con inglete en las esquinas."""
    n = len(pts)
    out = []
    for i in range(n):
        x0, y0 = pts[i - 1]
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        ax, ay = x1 - x0, y1 - y0
        bx, by = x2 - x1, y2 - y1
        la, lb = math.hypot(ax, ay) or 1e-9, math.hypot(bx, by) or 1e-9
        n0 = (ay / la, -ax / la)
        n1 = (by / lb, -bx / lb)
        nx, ny = n0[0] + n1[0], n0[1] + n1[1]
        ln = math.hypot(nx, ny)
        if ln < 1e-9:
            nx, ny = n0
        else:
            nx, ny = nx / ln, ny / ln
        c = max(nx * n0[0] + ny * n0[1], 0.35)
        out.append((x1 + nx * d / c, y1 + ny * d / c))
    return out


def rrect(cx, cy, w, h, r, n=3):
    return [(cx + x, cy + y) for (x, y) in rr_profile(w, h, r, n)]


def _text(mb, s, size, depth, mat, M=None, align="CENTER", res=3, spacing=1.0):
    """Texto 3D como kit.clinic.text pero con resolución de curva baja (letras pequeñas: 3 en vez de 12 → ~1/4 de triángulos).
    Plano XY local de cara a +Z, relieve de z = 0 a z = depth, línea base en y = 0. Devuelve el ancho."""
    cu = bpy.data.curves.new("_txt", "FONT")
    cu.body = s
    cu.size = size
    cu.extrude = depth / 2
    cu.align_x = align
    cu.space_character = spacing
    cu.resolution_u = res
    ob = bpy.data.objects.new("_txt", cu)
    bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    M2 = (M if M is not None else Matrix()) @ _T(0, 0, depth / 2)
    vs = [mb.bm.verts.new(M2 @ v.co) for v in me.vertices]
    xs = [v.co.x for v in me.vertices] or [0.0]
    mi = mb.mi(mat)
    for p in me.polygons:
        try:
            f = mb.bm.faces.new([vs[i] for i in p.vertices])
            f.material_index = mi
        except ValueError:
            pass
    ev.to_mesh_clear()
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    return max(xs) - min(xs)


def _ap(M, p):
    v = Vector(p)
    return (M @ v) if M is not None else v


# ======================================================================================================== sólidos
def loft_x(mb, prof, x0, x1, mat, re=0.0, ne=2, M=None):
    """Prisma de perfil `prof` [(y, z)] a lo largo de X local de x0 a x1; re > 0 redondea los dos extremos (el perfil se
    contrae re·(1-cos) en `ne` pasos): lámina formada, cubiertas con canto boleado, frentes con jaladera rehundida."""
    prof = _ccw(_dedupe(prof))
    st = []
    if re > 0:
        for k in range(ne + 1):
            th = (PI / 2) * (1 - k / ne)
            st.append((x0 + re * (1 - math.sin(th)), -re * (1 - math.cos(th))))
        for k in range(ne + 1):
            th = (PI / 2) * k / ne
            st.append((x1 - re * (1 - math.sin(th)), -re * (1 - math.cos(th))))
    else:
        st = [(x0, 0.0), (x1, 0.0)]
    rings = []
    for (x, o) in st:
        pts = offset_ring(prof, o) if abs(o) > 1e-9 else prof
        rings.append([mb.bm.verts.new(_ap(M, (x, u, v))) for (u, v) in pts])
    k = len(prof)
    for i in range(len(rings) - 1):
        A, B = rings[i], rings[i + 1]
        for j in range(k):
            jj = (j + 1) % k
            mb.face([A[j], A[jj], B[jj], B[j]], mat)
    mb.face(list(reversed(rings[0])), mat)
    mb.face(rings[-1], mat)


def ring_shell(mb, rings, mat, M=None, cap0=True, cap1=True):
    """Superficie por anillos (misma cantidad de puntos) unidos en orden; tapas en el primero y el último."""
    R = [[mb.bm.verts.new(_ap(M, p)) for p in ring] for ring in rings]
    k = len(R[0])
    for i in range(len(R) - 1):
        A, B = R[i], R[i + 1]
        for j in range(k):
            jj = (j + 1) % k
            mb.face([A[j], A[jj], B[jj], B[j]], mat)
    if cap0:
        mb.face(list(reversed(R[0])), mat)
    if cap1:
        mb.face(R[-1], mat)


def sheet_solid(mb, top, bot, mat, M=None):
    """Lámina delgada cerrada (papel, hoja de planta, toalla): rejillas superior e inferior (nu x nv) + cantos + tapas."""
    T = [[mb.bm.verts.new(_ap(M, p)) for p in row] for row in top]
    B = [[mb.bm.verts.new(_ap(M, p)) for p in row] for row in bot]
    nu, nv = len(T), len(T[0])
    for i in range(nu - 1):
        for j in range(nv - 1):
            mb.face([T[i][j], T[i + 1][j], T[i + 1][j + 1], T[i][j + 1]], mat)
            mb.face([B[i][j], B[i][j + 1], B[i + 1][j + 1], B[i + 1][j]], mat)
        mb.face([B[i][0], B[i + 1][0], T[i + 1][0], T[i][0]], mat)
        mb.face([T[i][-1], T[i + 1][-1], B[i + 1][-1], B[i][-1]], mat)
    mb.face(T[0][::-1] + B[0], mat)
    mb.face(T[-1] + B[-1][::-1], mat)


def lathe_closed(mb, prof, seg, mat, M=None, phase=0.0):
    """Sólido de revolución de perfil cerrado [(r, z)] que no toca el eje (aros, juntas, bisel de cerradura)."""
    R = []
    for k in range(seg):
        a = 2 * PI * k / seg + phase
        ca, sa = math.cos(a), math.sin(a)
        R.append([mb.bm.verts.new(_ap(M, (r_ * ca, r_ * sa, z))) for (r_, z) in prof])
    n = len(prof)
    for k in range(seg):
        A, B = R[k], R[(k + 1) % seg]
        for i in range(n):
            ii = (i + 1) % n
            mb.face([A[i], A[ii], B[ii], B[i]], mat)


def sub(mb, build, M):
    """Construye en un MB temporal y lo une con la matriz M (para primitivas sin parámetro de matriz: sweep, tube)."""
    t = MB()
    build(t)
    mb.join(t, M)


def edge_band(mb, outline, plane, pos, thick, mat, bulge=0.0017, over=0.0006, n=3):
    """Canto de PVC redondeado sobre el contorno de un tablero: outline 2D cerrado en el plano (plane = 'x': (y, z);
    'y': (x, z); 'z': (x, y)), tablero de pos a pos + thick sobre el eje normal."""
    o = _ccw(_dedupe(outline))
    sgn = -1.0 if plane == "y" else 1.0
    if plane == "x":
        path, nrm = [(pos, u, v) for (u, v) in o], (1, 0, 0)
    elif plane == "y":
        path, nrm = [(u, pos, v) for (u, v) in o], (0, 1, 0)
    else:
        path, nrm = [(u, v, pos) for (u, v) in o], (0, 0, 1)
    prof = [(-0.003 * sgn, 0.0012)]
    for k in range(n + 1):
        a = -PI / 2 + PI * k / n
        prof.append(((bulge * math.cos(a) * 0.9 + bulge * 0.1) * sgn, thick / 2 + (thick / 2 + over) * math.sin(a)))
    prof.append((-0.003 * sgn, thick - 0.0012))
    mb.sweep(prof, path, mat=mat, closed_path=True, normal=nrm)


def coil(mb, path, R=0.0045, pitch=0.0032, r=0.0011, mat="cable", seg=4, ppt=6):
    """Cordón en espiral (auricular de teléfono) a lo largo de una curva suave."""
    P = [Vector(p) for p in path]
    L = [0.0]
    for a, b in zip(P[:-1], P[1:]):
        L.append(L[-1] + (b - a).length)
    tot = L[-1]
    N = max(8, int(tot / pitch * ppt))

    def at(s):
        for i in range(len(L) - 1):
            if L[i + 1] >= s:
                t = (s - L[i]) / max(L[i + 1] - L[i], 1e-9)
                return P[i].lerp(P[i + 1], t)
        return P[-1]
    C = [at(tot * k / N) for k in range(N + 1)]
    T = []
    for k in range(N + 1):
        a = C[min(k + 1, N)] - C[max(k - 1, 0)]
        T.append(a.normalized() if a.length > 1e-9 else Vector((1, 0, 0)))
    ref = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
    Nn = (ref - T[0] * ref.dot(T[0])).normalized()
    pts = []
    for k in range(N + 1):
        if k:
            Nn = (Nn - T[k] * Nn.dot(T[k])).normalized()
        B = T[k].cross(Nn)
        ph = 2 * PI * (tot * k / N) / pitch
        pts.append(tuple(C[k] + (Nn * math.cos(ph) + B * math.sin(ph)) * R))
    mb.tube(pts, r, seg=seg, mat=mat)


def smooth_path(pts, n=6):
    """Curva Catmull-Rom por los puntos (cables, tallos)."""
    P = [Vector(p) for p in pts]
    out = []
    for i in range(len(P) - 1):
        p0, p1, p2, p3 = P[max(i - 1, 0)], P[i], P[i + 1], P[min(i + 2, len(P) - 1)]
        for k in range(n):
            t = k / n
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-1])
    return [tuple(p) for p in out]


def keycap(mb, M, w, d, hgt, mat="plastic", top_in=0.0019, ch=0.0016):
    """Tecla: tronco de pirámide (base w x d, alto hgt), base en z = 0 local. Sin cara inferior: la base va embebida en la
    carcasa y nunca se ve (presupuesto: 10 triángulos por tecla)."""
    del ch
    b = [mb.bm.verts.new(_ap(M, p)) for p in ((-w / 2, -d / 2, 0.0), (w / 2, -d / 2, 0.0), (w / 2, d / 2, 0.0), (-w / 2, d / 2, 0.0))]
    hw, hd = w / 2 - top_in, d / 2 - top_in
    t = [mb.bm.verts.new(_ap(M, p)) for p in ((-hw, -hd, hgt), (hw, -hd, hgt), (hw, hd, hgt), (-hw, hd, hgt))]
    for i in range(4):
        j = (i + 1) % 4
        mb.face([b[i], b[j], t[j], t[i]], mat)
    mb.face(t, mat)


def glide(mb, x, y, z=0.0, r=0.0125, mat="plastic"):
    """Regatón nivelador: zapata de nylon, tuerca hexagonal y espárrago."""
    port.lathe(mb, [(r, 0.0), (r + 0.001, 0.0018), (r * 0.62, 0.0058)], seg=8, mat=mat, M=_T(x, y, z))
    port.lathe(mb, [(0.0065, 0.0055), (0.0065, 0.0105)], seg=6, mat="steel", M=_T(x, y, z), phase=PI / 6)


def lock_cyl(mb, M, r=0.0085, mat="steel"):
    """Cilindro de cerradura con bisel, rotor y ranura de llave. Eje +Z local (sale del frente)."""
    port.lathe(mb, [(r, -0.001), (r + 0.0006, 0.0012), (r * 0.92, 0.0026), (r * 0.72, 0.003), (r * 0.7, 0.0018)], seg=12, mat=mat, M=M)
    port.lathe(mb, [(r * 0.62, 0.0012), (r * 0.62, 0.0026), (r * 0.55, 0.0031)], seg=10, mat=mat, M=M)
    mb.box((-0.0008, -r * 0.42, 0.0025), (0.0008, r * 0.42, 0.0043), "cable", bevel=0.0, m=M)


def dpull(mb, M, cc=0.096, proj=0.028, r=0.0048, mat="steel"):
    """Jaladera de alambre en D: postes con roseta y barra; plano local XY, sale hacia -Y desde y = 0, a lo largo de X."""
    path = fillet([(-cc / 2, 0.0015, 0.0), (-cc / 2, -proj, 0.0), (cc / 2, -proj, 0.0), (cc / 2, 0.0015, 0.0)], 0.012, 3)
    mb.tube([tuple(M @ Vector(p)) for p in path], r, seg=8, mat=mat)
    for x in (-cc / 2, cc / 2):
        port.lathe(mb, [(r * 1.9, 0.0), (r * 1.9, -0.0015), (r * 1.4, -0.003)], seg=8, mat=mat, M=M @ _T(x, 0.0, 0.0) @ _Rx(-90))


def small_caster(mb, M, d=0.05, brake=False, swivel=0.0, mat_tire="rubber"):
    """Rodaja de 50 mm: placa con 4 tornillos, balero, horquilla de lámina, rueda con banda y maza; freno opcional.
    Origen en el piso bajo la espiga; la placa queda arriba a d + 0.025."""
    rr = d / 2
    Mz = M @ _Rz(swivel)
    zt = d + 0.022
    mb.box((-0.03, -0.03, zt), (0.03, 0.03, zt + 0.004), "steel", bevel=0.0015, seg=1, m=Mz)
    port.lathe(mb, [(0.019, zt - 0.009), (0.021, zt - 0.005), (0.019, zt)], seg=10, mat="steel", M=Mz)
    off = rr * 0.5
    for s in (-1, 1):
        prof = [(-0.016, zt - 0.009), (0.016, zt - 0.009), (off + 0.012, rr + 0.006), (off + 0.008, rr - 0.008),
                (off - 0.008, rr - 0.008), (-0.012, zt - 0.02)]
        perm = Matrix(((0, 0, 1, 0), (1, 0, 0, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
        mb.plate(fillet2d(prof, 0.004, 1), 0.0025, "steel", m=Mz @ _T(s * 0.0145 - (0.0025 if s > 0 else 0), 0, 0) @ perm)
    Mw = Mz @ _T(0, off, rr) @ _Ry(90)
    port.lathe(mb, [(rr * 0.62, -0.0115), (rr - 0.002, -0.0105), (rr, -0.004), (rr, 0.004), (rr - 0.002, 0.0105), (rr * 0.62, 0.0115)],
               seg=14, mat=mat_tire, M=Mw)
    port.lathe(mb, [(0.0075, -0.0135), (0.0085, -0.0115), (0.0085, 0.0115), (0.0075, 0.0135)], seg=8, mat="steel", M=Mw)
    if brake:
        mb.box((-0.011, -0.04, zt - 0.014), (0.011, -0.012, zt - 0.006), "sign_red", bevel=0.003, seg=1, m=Mz)


# ======================================================================================================== accesorios de escritorio
def paper_sheet(mb, M, w, l, t=0.0007, curl=0.0, lift=0.0, wave=0.0, seed=0, nu=5, nv=6, mat="paper", curl_dir=1):
    """Hoja suelta (sólido delgado) acostada en z = 0 local: borde y+ (curl_dir=1) o y- enrollado `curl`, una esquina
    levantada `lift` y ondulación suave `wave`."""
    r = rng(seed)
    ph = [float(v) for v in r.uniform(0, 2 * PI, 3)]
    cx = float(r.choice([0, 1]))
    top, bot = [], []
    for i in range(nu):
        u = i / (nu - 1)
        x = -w / 2 + w * u
        rt, rb = [], []
        for j in range(nv):
            v = j / (nv - 1)
            y = -l / 2 + l * v
            vv = v if curl_dir > 0 else 1 - v
            dz = curl * max(0.0, (vv - 0.68) / 0.32) ** 2
            uu = u if cx else 1 - u
            dz += lift * (max(0.0, (uu - 0.6) / 0.4) * max(0.0, (0.4 - vv) / 0.4)) ** 1.3
            dz += wave * (0.5 + 0.5 * math.sin(3.1 * u + ph[0]) * math.sin(2.3 * v + ph[1]))
            rb.append((x, y, dz))
            rt.append((x, y, dz + t))
        top.append(rt)
        bot.append(rb)
    sheet_solid(mb, top, bot, mat, M)


def _keyboard(mb, M):
    """Teclado de membrana de 104 teclas: carcasa en cuña con cantos redondeados, teclas individuales inclinadas con la
    carcasa, bloque numérico, navegación y LEDs. Origen: centro de la base sobre la mesa. Devuelve el punto de salida del cable."""
    W, D = 0.458, 0.152
    y0, y1 = -D / 2, D / 2
    zf, zb = 0.016, 0.029
    prof = fillet2d([(y0, 0.0), (y1, 0.0), (y1, zb), (y0, zf)], [0.0015, 0.003, 0.006, 0.006], 2)
    loft_x(mb, prof, -W / 2, W / 2, "plastic", re=0.007, ne=1, M=M)
    sl = math.atan2(zb - zf, D)

    def ztop(y):
        return zf + (zb - zf) * (y - y0) / D
    u = 0.019
    x0 = -W / 2 + 0.0095
    rows = {
        0: [1.25, 1.25, 1.25, 6.25, 1.25, 1.25, 1.25, 1.25],
        1: [2.25] + [1] * 10 + [2.75],
        2: [1.75] + [1] * 11 + [2.25],
        3: [1.5] + [1] * 12 + [1.5],
        4: [1] * 13 + [2],
        5: [1, -1, 1, 1, 1, 1, -0.5, 1, 1, 1, 1, -0.5, 1, 1, 1, 1],
    }
    nav = {5: [1, 1, 1], 4: [1, 1, 1], 3: [1, 1, 1], 1: [-1, 1], 0: [1, 1, 1]}
    pad = {4: [1, 1, 1, 1], 3: [1, 1, 1], 2: [1, 1, 1], 1: [1, 1, 1], 0: [2, 1]}

    def yrow(i):
        return y0 + 0.0105 + u / 2 + i * u + (0.45 * u if i == 5 else 0.0)

    def put(xl, row, widths, tall=None):
        x = xl
        for wu in widths:
            if wu < 0:
                x += -wu * u
                continue
            cx, cy = x + wu * u / 2, yrow(row)
            dd = u - 0.0036
            if tall:
                cy -= u / 2
                dd += u
            keycap(mb, M @ _T(cx, cy, ztop(cy) - 0.0025) @ _Rx(math.degrees(sl)), wu * u - 0.0036, dd, 0.0105, "plastic")
            x += wu * u
    for row, ws in rows.items():
        put(x0, row, ws)
    for row, ws in nav.items():
        put(x0 + 15.5 * u, row, ws)
    for row, ws in pad.items():
        put(x0 + 19.0 * u, row, ws)
    put(x0 + 22.0 * u, 3, [1], tall=True)        # + del bloque numérico (2 filas)
    put(x0 + 22.0 * u, 1, [1], tall=True)        # Intro del bloque numérico
    for k in range(3):                            # LEDs
        x = x0 + 19.6 * u + k * 0.017
        y = y1 - 0.0085
        port.lathe(mb, [(0.0018, -0.001), (0.0018, 0.0006), (0.0012, 0.0013)], seg=6, mat="sign_green",
                   M=M @ _T(x, y, ztop(y)) @ _Rx(math.degrees(sl)))
    return M @ Vector((-0.06, y1 + 0.001, 0.016))


def _mouse(mb, M):
    """Ratón óptico: cuerpo de anillos con joroba hacia atrás, ranura de botones, rueda de hule. Devuelve el punto del cable."""
    st = [(0.0, 0.056, 0.104, 0.0), (0.008, 0.062, 0.111, 0.001), (0.019, 0.058, 0.102, 0.005),
          (0.028, 0.048, 0.084, 0.010), (0.033, 0.036, 0.062, 0.013), (0.0355, 0.020, 0.036, 0.015)]
    zloft(mb, st, seg=16, mat="plastic", M=M, ex=2.3)

    def ztop(y):
        return 0.0355 * max(0.0, 1 - ((y - 0.012) / 0.058) ** 2) ** 0.5
    pts = [(0.0, y, ztop(y) + 0.0004) for y in np.linspace(-0.05, -0.004, 4)]
    mb.tube([tuple(M @ Vector(p)) for p in pts], 0.0009, seg=4, mat="cable")
    port.lathe(mb, [(0.0085, -0.0032), (0.0095, -0.0015), (0.0095, 0.0015), (0.0085, 0.0032)], seg=10,
               mat="rubber", M=M @ _T(0.0, -0.026, ztop(-0.026) - 0.006) @ _Ry(90))
    return M @ Vector((0.0, -0.05, 0.008))


def _monitor(mb, M):
    """Monitor LCD de 21,5" sencillo: base ovalada, cuello inclinado, bisagra, bisel con pantalla rehundida, cuerpo, carcasa
    trasera abombada con rejilla de ventilación, placa VESA, botones y LED. Origen: centro de la base sobre la mesa."""
    zloft(mb, [(0.0, 0.214, 0.164, 0.0), (0.003, 0.222, 0.172, 0.0), (0.009, 0.219, 0.169, 0.001), (0.013, 0.200, 0.150, 0.006),
               (0.016, 0.130, 0.090, 0.014), (0.017, 0.100, 0.062, 0.016)], seg=20, mat="cable", M=M, ex=3.2)
    zloft(mb, [(0.012, 0.076, 0.036, 0.024), (0.03, 0.068, 0.033, 0.028), (0.17, 0.060, 0.030, 0.042), (0.206, 0.060, 0.030, 0.045),
               (0.214, 0.050, 0.022, 0.045)], seg=12, mat="cable", M=M, ex=3.5)
    mb.box((-0.012, 0.059, 0.09), (0.012, 0.064, 0.13), "cable", bevel=0.002, seg=1, m=M)       # pasacables del cuello
    port.lathe(mb, [(0.015, -0.034), (0.0165, -0.031), (0.0165, 0.031), (0.015, 0.034)], seg=12,
               mat="cable", M=M @ _T(0, 0.046, 0.20) @ _Ry(90))
    W, H, bw = 0.51, 0.31, 0.016
    Mp = M @ _T(0, 0.046, 0.20) @ _Rx(-6) @ _T(0, -0.09, 0.07)
    a, b = (W - bw) / 2, (H - bw) / 2
    path = [(x, 0.0, z) for (x, z) in fillet2d([(-a, -b), (a, -b), (a, b), (-a, b)], 0.006, 2)]
    prof = [(-bw / 2, 0.012), (-bw / 2, 0.0035), (-bw / 2 + 0.0035, 0.0), (bw / 2 - 0.0035, 0.0), (bw / 2, 0.0028), (bw / 2, 0.012)]
    sub(mb, lambda t: t.sweep(prof, path, mat="cable", closed_path=True, normal=(0, 1, 0)), Mp)
    mb.box((-(W / 2 - bw + 0.004), 0.0028, -(H / 2 - bw + 0.004)), (W / 2 - bw + 0.004, 0.009, H / 2 - bw + 0.004), m=Mp, mat=
           "glass", bevel=0.0)
    mb.box((-W / 2 + 0.0015, 0.012, -H / 2 + 0.0015), (W / 2 - 0.0015, 0.026, H / 2 - 0.0015), "cable", bevel=0.005, seg=2, m=Mp)
    swap = Matrix(((0, 1, 0, 0), (1, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
    port.loft(mb, [(0.025, W - 0.05, H - 0.10, -0.02), (0.04, W - 0.11, H - 0.13, -0.03), (0.056, 0.33, 0.16, -0.04),
                   (0.064, 0.28, 0.13, -0.04)], seg=20, mat="cable", M=Mp @ swap, ex=3.6)
    for k in range(17):                                                                           # rejilla de ventilación
        x = -0.152 + k * 0.019
        mb.box((x - 0.0028, 0.0255, 0.112), (x + 0.0028, 0.0285, 0.142), "cable", bevel=0.0, m=Mp)
    mb.box((-0.055, 0.062, -0.105), (0.055, 0.075, -0.035), "cable", bevel=0.003, seg=1, m=Mp)   # placa VESA
    for (x, z) in ((-0.04, -0.09), (0.04, -0.09), (-0.04, -0.05), (0.04, -0.05)):
        port.lathe(mb, [(0.004, 0.0), (0.0035, 0.002)], seg=6, mat="steel", M=Mp @ _T(x, 0.075, z) @ _Rx(-90))
    for k in range(4):                                                                            # botones y LED
        x = W / 2 - 0.03 - k * 0.017
        port.lathe(mb, [(0.0032, -0.0006), (0.0032, 0.0008), (0.0024, 0.0014)], seg=6,
                   mat=("sign_blue" if k == 0 else "cable"), M=Mp @ _T(x, 0.0, -H / 2 + bw * 0.45) @ _Rx(90))
    return Mp


def _phone(mb, M, seed=0):
    """Teléfono de escritorio: base en cuña, teclado de 12 teclas + funciones, pantalla, horquilla, auricular sobre sus
    soportes y cordón en espiral hasta el costado. Origen: centro de la base sobre la mesa."""
    yF, yB, zF, zB = -0.105, 0.105, 0.032, 0.07
    prof = fillet2d([(yF, 0.0), (yB, 0.0), (yB, zB), (yB - 0.03, zB + 0.004), (yF, zF)], [0.002, 0.006, 0.01, 0.02, 0.01], 3)
    loft_x(mb, prof, -0.1, 0.1, "plastic", re=0.01, ne=2, M=M)
    ya, za, yb_, zb_ = yF + 0.012, zF + 0.0035, yB - 0.03, zB + 0.004
    sl = math.atan2(zb_ - za, yb_ - ya)

    def zt(y):
        return za + (zb_ - za) * (y - ya) / (yb_ - ya)
    for i in range(4):                                                                            # teclado 3 x 4
        for j in range(3):
            x, y = 0.012 + j * 0.022, -0.075 + i * 0.019
            keycap(mb, M @ _T(x, y, zt(y) - 0.0015) @ _Rx(math.degrees(sl)), 0.016, 0.013, 0.0055, "plastic")
    for i in range(5):                                                                            # teclas de función
        y = -0.08 + i * 0.016
        keycap(mb, M @ _T(0.084, y, zt(y) - 0.0015) @ _Rx(math.degrees(sl)), 0.014, 0.010, 0.0045, "cable")
    y = 0.045
    mb.box((-0.002, -0.022, -0.002), (0.096, 0.022, 0.0016), "cable", bevel=0.0015, seg=1, m=M @ _T(0, y, zt(y)) @ _Rx(math.degrees(sl)))
    mb.box((0.006, -0.015, 0.001), (0.088, 0.015, 0.0032), "glass", bevel=0.0, m=M @ _T(0, y, zt(y)) @ _Rx(math.degrees(sl)))
    # horquilla: dos soportes y botones de colgado
    for y in (-0.072, 0.072):
        mb.box((-0.088, y - 0.012, -0.002), (-0.032, y + 0.012, 0.007), "plastic", bevel=0.003, seg=1,
               m=M @ _T(0, 0, zt(y)) @ _Rx(math.degrees(sl)))
        port.lathe(mb, [(0.004, 0.0), (0.004, 0.004)], seg=6, mat="cable",
                   M=M @ _T(-0.06, y + (0.016 if y > 0 else -0.016), zt(y) + 0.004))
    # auricular (sobre los soportes, inclinado con la base)
    st = [(-0.105, 0.040, 0.014, -0.006), (-0.099, 0.050, 0.028, -0.002), (-0.082, 0.052, 0.032, 0.0), (-0.060, 0.036, 0.025, 0.006),
          (0.052, 0.034, 0.024, 0.006), (0.074, 0.048, 0.030, 0.0), (0.095, 0.052, 0.030, -0.002), (0.105, 0.044, 0.014, -0.006)]
    swap = Matrix(((0, 1, 0, 0), (1, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
    Mh = M @ _T(-0.06, 0.0, zt(0.0) + 0.022) @ _Rx(math.degrees(sl))
    port.loft(mb, st, seg=12, mat="plastic", M=Mh @ swap, ex=2.5)
    # cordón en espiral desde el micrófono hasta el costado izquierdo de la base
    p0 = Mh @ Vector((0.0, -0.104, -0.002))
    pts = [tuple(p0), tuple(M @ Vector((-0.075, -0.118, 0.02))), tuple(M @ Vector((-0.112, -0.112, 0.0055))),
           tuple(M @ Vector((-0.135, -0.06, 0.0055))), tuple(M @ Vector((-0.125, -0.012, 0.0075))), tuple(M @ Vector((-0.1, -0.005, 0.012)))]
    coil(mb, smooth_path(pts, 6), R=0.0042, pitch=0.0058, r=0.0013, seg=3, ppt=5)
    port.lathe(mb, [(0.0035, 0.0), (0.0035, 0.008)], seg=6, mat="cable", M=M @ _T(-0.1, -0.005, 0.012) @ _Ry(90))
    del seed
    return M @ Vector((0.05, yB, 0.012))


def _pen_cup(mb, M, seed=0):
    """Portalápices con 3-4 plumas (capuchón con clip) y un lápiz hexagonal con punta y goma."""
    r = rng(seed)
    port.lathe(mb, [(0.034, 0.0), (0.0355, 0.003), (0.0355, 0.098), (0.0336, 0.1006), (0.0315, 0.098), (0.0315, 0.007)], seg=14,
               mat="plastic_blue", M=M)
    n = int(r.integers(3, 5))
    for k in range(n + 1):
        a = 2 * PI * k / (n + 1) + float(r.uniform(-0.3, 0.3))
        t = float(r.uniform(7, 15))
        Mb = M @ _T(-0.012 * math.cos(a), -0.012 * math.sin(a), 0.007) @ _Rz(math.degrees(a) - 90) @ _Rx(-t)
        if k < n:
            body = ("plastic", "sign_blue", "sign_red", "cable", "plastic_blue")[int(r.integers(0, 5))]
            if k >= 2:                                   # presupuesto: 2 plumas + lápiz (la punta queda dentro del vaso)
                continue
            port.lathe(mb, [(0.0034, 0.017), (0.004, 0.02), (0.004, 0.118)], seg=6, mat=body, M=Mb)
            port.lathe(mb, [(0.0044, 0.1175), (0.0044, 0.139), (0.0036, 0.1425), (0.0, 0.1435)], seg=6,
                       mat=("cable" if body != "cable" else "sign_blue"), M=Mb)
            mb.box((-0.0012, 0.0040, 0.104), (0.0012, 0.0056, 0.139), "steel", bevel=0.0, m=Mb)
        else:
            port.lathe(mb, [(0.0011, 0.0031), (0.0036, 0.016)], seg=6, mat="wood_varnish", M=Mb)          # madera afilada
            port.lathe(mb, [(0.0036, 0.0162), (0.0036, 0.1505)], seg=6, mat="paint_yellow", M=Mb)          # cuerpo hexagonal
            port.lathe(mb, [(0.0036, 0.15), (0.0039, 0.1505), (0.0039, 0.161), (0.0036, 0.1615)], seg=8, mat="aluminium", M=Mb)
            port.lathe(mb, [(0.0035, 0.1612), (0.0035, 0.168), (0.0028, 0.171), (0.0, 0.1715)], seg=8, mat="sign_red", M=Mb)


def _binder(mb, M, bw, dd, hh, mat, label):
    """Carpeta de palanca parada: tapas de cartón forrado, lomo curvo, anillo para el dedo, portaetiqueta con texto y el
    bloque de hojas visible por detrás. Lomo hacia -Y local; base en z = 0."""
    ct = 0.0025
    yc, ry = -dd / 2 + 0.0065, 0.0065
    outer = [(bw / 2 * math.cos(a), yc + ry * math.sin(a)) for a in np.linspace(PI, 2 * PI, 7)]
    inner = [((bw / 2 - ct) * math.cos(a), yc + (ry - ct) * math.sin(a)) for a in np.linspace(2 * PI, PI, 7)]
    poly = [(-bw / 2, dd / 2)] + outer + [(bw / 2, dd / 2), (bw / 2 - ct, dd / 2)] + inner + [(-bw / 2 + ct, dd / 2)]
    loft_x(mb, poly, 0.0, hh, mat, re=0.0, M=M @ LZ)          # cartón forrado: cantos de corte rectos arriba y abajo
    mb.box((-bw / 2 + ct + 0.0015, -dd / 2 + 0.02, 0.005), (bw / 2 - ct - 0.0015, dd / 2 - 0.004, hh - 0.007), m=M, mat=
           "paper", bevel=0.0)
    zh = hh * 0.22
    Mr = M @ _T(0, -dd / 2, zh) @ _Rx(90)
    lathe_closed(mb, [(0.0103, -0.0015), (0.0138, -0.0015), (0.0132, 0.0019), (0.0106, 0.0017)], 12, "steel", Mr)
    port.lathe(mb, [(0.0106, -0.0012), (0.0106, 0.0009)], seg=12, mat="cable", M=Mr)
    lw = bw / 2 - 0.007
    mb.box((-lw, -dd / 2 - 0.0016, hh - 0.125), (lw, -dd / 2 + 0.0008, hh - 0.022), "paper", bevel=0.0, m=M)
    for z in (hh - 0.125, hh - 0.022):
        mb.cyl(M @ Vector((-lw - 0.001, -dd / 2 - 0.0016, z)), M @ Vector((lw + 0.001, -dd / 2 - 0.0016, z)), 0.0017, seg=6, mat="glass")
    sz = min(0.0105, 2.0 * lw / max(len(label), 1) * 1.1)
    _text(mb, label, sz, 0.0016, "cable", M @ _T(0, -dd / 2 - 0.0014, hh - 0.055) @ _Rx(90), res=2)


def _bookend(mb, M):
    """Sujetalibros de lámina doblada: base bajo las carpetas y respaldo con esquinas redondeadas."""
    mb.box((0.0, -0.065, 0.0), (0.13, 0.065, 0.0015), "steel", bevel=0.0, m=M)
    prof = fillet2d([(-0.065, 0.0005), (0.065, 0.0005), (0.065, 0.15), (0.035, 0.175), (-0.065, 0.175)], [0.0, 0.0, 0.012, 0.02, 0.012], 3)
    loft_x(mb, prof, -0.0016, 0.0, "steel", re=0.0, M=M)
    loft_x(mb, [(-0.06, 0.0011), (0.06, 0.0011), (0.0, 0.01)], -0.0008, 0.004, "steel", re=0.0, M=M)


def _paper_stack(mb, M, seed, n_loose=2, folder=False):
    """Pila de hojas: bloque de papel con cantos suaves, hojas sueltas giradas encima (la de arriba con el borde levantado)
    y, opcional, un fólder manila doblado."""
    r = rng(seed)
    w, l = 0.216, 0.279
    hb = float(r.uniform(0.003, 0.009))
    mb.box((-w / 2, -l / 2, 0.0), (w / 2, l / 2, hb), "paper", bevel=0.0008, seg=1, m=M)
    z = hb + 0.0006
    for k in range(n_loose):
        last = k == n_loose - 1
        Mk = M @ _T(float(r.uniform(-0.008, 0.008)), float(r.uniform(-0.01, 0.01)), z) @ _Rz(float(r.uniform(-6, 6)))
        free_top = last and not folder
        paper_sheet(mb, Mk, w, l, curl=(float(r.uniform(0.006, 0.014)) if free_top else 0.0), lift=(0.006 if free_top else 0.0),
                    wave=0.0012 if free_top else 0.0, seed=int(r.integers(1e6)), nu=(4 if free_top else 2), nv=(5 if free_top else 2))
        z += 0.0014 + (0.0016 if last else 0.0)
    if folder:
        Mf = M @ _T(0.004, 0.006, z + 0.0008) @ _Rz(float(r.uniform(-4, 4)))
        paper_sheet(mb, Mf, 0.235, 0.30, t=0.0009, curl=0.0, wave=0.0, seed=int(r.integers(1e6)), mat="paint_yellow", nu=2, nv=2)
        paper_sheet(mb, Mf @ _T(-0.002, 0.003, 0.0016), 0.226, 0.28, t=0.0007, wave=0.0, seed=int(r.integers(1e6)), nu=2, nv=2)
        Mt = Mf @ _T(-0.1175, 0, 0.0042) @ _Ry(-2.5) @ _T(0.1175, 0, 0)
        paper_sheet(mb, Mt, 0.235, 0.30, t=0.0009, curl=0.009, lift=0.01, wave=0.0015, seed=int(r.integers(1e6)), mat="paint_yellow",
                    curl_dir=-1, nu=4, nv=5)
        mb.tube([tuple(Mf @ Vector((-0.1175, y, 0.0022))) for y in (-0.15, 0.15)], 0.0021, seg=5, mat="paint_yellow")


# ======================================================================================================== escritorio
def _drawer_prof(yf, z0, z1, T=0.02, top=True):
    """Sección de frente de cajón de lámina con jaladera rehundida corrida (bolsa bajo una ceja) arriba o abajo."""
    L, P, H = 0.008, 0.0145, 0.03
    pts = [(yf, 0.0), (yf + T, 0.0), (yf + T, 1.0), (yf, 1.0), (yf, 1.0 - L), (yf + P, 1.0 - L - 0.003), (yf + P, 1.0 - H),
           (yf, 1.0 - H - 0.006)]
    rad = [0.003, 0.002, 0.002, 0.003, 0.0015, 0.003, 0.004, 0.003]
    if top:
        pts = [(y, z0 if z == 0.0 else (z1 if z == 1.0 else z1 - (1.0 - z))) for (y, z) in pts]
    else:
        pts = [(y, z1 if z == 0.0 else (z0 if z == 1.0 else z0 + (1.0 - z))) for (y, z) in pts]
    return fillet2d(pts, rad, 2)


def _steel_drawer(mb, xa, xb, yf, z0, z1, top=True, lock=False):
    loft_x(mb, _drawer_prof(yf, z0, z1, 0.02, top), xa, xb, "enamel", re=0.0035, ne=1)
    if lock:
        lock_cyl(mb, _T(xb - 0.045, yf, z1 - 0.058) @ _Rx(90))


def desk(w=1.4, d=0.7, seed=0, monitor=True, papers=True):
    """Escritorio metálico secretarial (pedestal de 3 cajones a la derecha; doble pedestal desde 1,7 m): cubierta laminada
    de 28 mm con moldura T de vinil, costado de lámina formada de 30 mm, faldón con nervaduras, pedestal con zoclo
    rehundido, cajones con holgura de 3 mm y jaladera rehundida, cerradura, cajón central de lápices, regatones niveladores.
    Encima: monitor LCD con cables, teclado de 104 teclas, ratón con cable sobre tapete, teléfono con cordón en espiral,
    portalápices, carpetas de palanca con sujetalibros y papeles con el borde levantado."""
    r = rng(seed)
    mb = MB()
    h = 0.75
    tt = 0.028
    zt0 = h - tt
    yf, yb = -d / 2 + 0.04, d / 2 - 0.03
    # --- cubierta: tablero laminado + moldura T perimetral
    out = rrect(0.0, 0.0, w - 0.005, d - 0.005, 0.014, 3)
    mb.plate(out, tt, "wood_varnish", m=_T(0, 0, zt0))
    hh = tt / 2 + 0.0012
    tprof = [(-0.004, -hh + 0.003), (-0.0005, -hh), (0.0017, -hh * 0.62), (0.0025, 0.0), (0.0017, hh * 0.62), (-0.0005, hh),
             (-0.004, hh - 0.003)]
    mb.sweep(tprof, [(x, y, zt0 + tt / 2) for (x, y) in out], mat="cable", closed_path=True, normal=(0, 0, 1))
    # --- pedestales y costado
    pw = 0.40 if w >= 1.2 else 0.36
    double = w >= 1.7
    xR1 = w / 2 - 0.012
    xR0 = xR1 - pw

    def pedestal(x0, x1, lock=True):
        for (a_, b_) in ((x0, x0 + 0.02), (x1 - 0.02, x1)):
            loft_x(mb, fillet2d([(a_, yf), (b_, yf), (b_, yb), (a_, yb)], [0.006, 0.006, 0.003, 0.003], 2), 0.012, zt0, "enamel", re=0.003,
                   ne=1, M=LZ)
            for yy in (yf + 0.03, yb - 0.03):
                glide(mb, (a_ + b_) / 2, yy)
        mb.box((x0 + 0.02, yb - 0.012, 0.03), (x1 - 0.02, yb - 0.002, zt0), "enamel", bevel=0.002, seg=1)          # respaldo
        mb.box((x0 + 0.02, yf + 0.03, 0.012), (x1 - 0.02, yf + 0.045, 0.078), "enamel", bevel=0.002, seg=1)       # zoclo
        mb.box((x0 + 0.02, yf + 0.03, 0.0785), (x1 - 0.02, yb - 0.012, 0.086), "enamel", bevel=0.0)               # fondo (oculto)
        mb.box((x0 + 0.02, yf, zt0 - 0.026), (x1 - 0.02, yf + 0.022, zt0), "enamel", bevel=0.003, seg=2)           # travesaño
        ztop = zt0 - 0.029
        zbot = 0.088
        unit = (ztop - zbot - 0.008) / 4
        zs = [(zbot, zbot + 2 * unit), (zbot + 2 * unit + 0.004, zbot + 3 * unit + 0.004), (zbot + 3 * unit + 0.008, ztop)]
        for k, (z0, z1) in enumerate(zs):
            _steel_drawer(mb, x0 + 0.023, x1 - 0.023, yf, z0, z1, top=True, lock=(lock and k == 2))
            if k:
                mb.box((x0 + 0.02, yf + 0.021, z0 - 0.009), (x1 - 0.02, yf + 0.04, z0 + 0.005), "enamel", bevel=0.0)
    pedestal(xR0, xR1)
    if double:
        xL0 = -w / 2 + 0.012
        xL1 = xL0 + pw
        pedestal(xL0, xL1, lock=False)
        xk0 = xL1
    else:
        xL0 = -w / 2 + 0.012
        loft_x(mb, fillet2d([(xL0 + 0.0035, yf), (xL0 + 0.03, yf), (xL0 + 0.03, yb), (xL0 + 0.0035, yb)], [0.01, 0.012, 0.006, 0.004], 3),
               0.012, zt0, "enamel", re=0.004, ne=1, M=LZ)
        # marco perimetral embutido de la cara exterior (lámina formada): tablero central rehundido 4 mm
        o = [(yf, 0.012), (yb, 0.012), (yb, zt0), (yf, zt0)]
        fprof = fillet2d([(0.0, 0.0005), (0.0, 0.0045), (0.032, 0.0045), (0.038, 0.0005)], [0.0, 0.0025, 0.004, 0.0], 2)
        mb.sweep(fprof, [(xL0 + 0.0045, u, v) for (u, v) in _ccw(o)], mat="enamel", closed_path=True, normal=(-1, 0, 0))
        for yy in (yf + 0.035, yb - 0.035):
            glide(mb, xL0 + 0.015, yy)
        xk0 = xL0 + 0.03
    xk1 = xR0
    # --- faldón (modesty panel) con dos nervaduras repujadas, riel frontal y cajón central
    ym0, ym1 = yb - 0.032, yb - 0.016
    zb0, zb1 = 0.26, zt0
    pts = [(ym1, zb0), (ym1, zb1), (ym0, zb1)]
    for zc in sorted([zb0 + (zb1 - zb0) * f for f in (0.35, 0.7)], reverse=True):
        pts += [(ym0, zc + 0.009), (ym0 - 0.0035, zc + 0.004), (ym0 - 0.004, zc), (ym0 - 0.0035, zc - 0.004), (ym0, zc - 0.009)]
    pts += [(ym0, zb0 + 0.012), (ym0 - 0.012, zb0 + 0.004), (ym0 - 0.012, zb0)]
    loft_x(mb, fillet2d(pts, 0.0025, 2), xk0, xk1, "enamel", re=0.0)
    mb.box((xk0, yf + 0.005, zt0 - 0.035), (xk1, yf + 0.024, zt0), "enamel", bevel=0.003, seg=2)
    kw = xk1 - xk0
    if kw > 0.5:
        cw = min(0.56, kw - 0.14)
        cx = (xk0 + xk1) / 2
        z1c = zt0 - 0.038
        z0c = z1c - 0.056
        loft_x(mb, _drawer_prof(yf + 0.004, z0c, z1c, 0.018, top=False), cx - cw / 2, cx + cw / 2, "enamel", re=0.003, ne=1)
        for s in (-1, 1):
            xs = cx + s * (cw / 2 + 0.006)
            mb.box((xs - 0.0015, yf + 0.024, z0c - 0.006), (xs + 0.0015, yb - 0.06, zt0), "enamel", bevel=0.0)
        mb.box((cx - cw / 2 - 0.0075, yf + 0.024, z0c - 0.008), (cx + cw / 2 + 0.0075, yb - 0.06, z0c - 0.005), "enamel", bevel=0.0)
    # --- objetos sobre la cubierta
    occ = []

    def free(x0, y0, x1, y1):
        if x0 < -w / 2 + 0.01 or x1 > w / 2 - 0.01 or y0 < -d / 2 + 0.01 or y1 > d / 2 - 0.01:
            return False
        return all(x1 < a or x0 > c or y1 < b or y0 > e for (a, b, c, e) in occ)
    kx = (xk0 + xk1) / 2
    kx = min(max(kx, -w / 2 + 0.25), w / 2 - 0.25 - 0.24)
    ky = -d / 2 + 0.135
    if monitor:
        Mk = _T(kx, ky, h) @ _Rz(float(r.uniform(-3, 3)))
        kc = _keyboard(mb, Mk)
        occ.append((kx - 0.24, ky - 0.085, kx + 0.24, ky + 0.085))
        mx, my = kx + 0.355, ky + 0.005
        mb.plate(rrect(0, 0, 0.22, 0.18, 0.016, 3), 0.003, "rubber", m=_T(mx, my, h))
        mc = _mouse(mb, _T(mx + float(r.uniform(-0.02, 0.02)), my + float(r.uniform(-0.02, 0.01)), h + 0.003) @ _Rz(float(r.uniform(-12, 8))))
        occ.append((mx - 0.115, my - 0.095, mx + 0.115, my + 0.095))
        xm = kx + float(r.uniform(-0.04, 0.04))
        ym = max(d / 2 - 0.2, -d / 2 + 0.31)
        Mm = _T(xm, ym, h) @ _Rz(float(r.uniform(-5, 5)))
        Mp = _monitor(mb, Mm)
        occ.append((xm - 0.26, ym - 0.1, xm + 0.26, ym + 0.1))
        # cables: video y corriente del monitor por detrás de la mesa; teclado y ratón hacia atrás
        for k, dx in enumerate((-0.03, 0.035)):
            p0 = Mp @ Vector((dx, 0.05, -0.135))
            zc_ = h + 0.0035 + k * 0.0045
            pts = [tuple(p0), tuple(Mp @ Vector((dx, 0.07, -0.16))), (xm + dx * 1.5, ym + 0.1, zc_), (xm + 0.06 + dx, d / 2 - 0.004, zc_),
                   (xm + 0.062 + dx, d / 2 + 0.0055, zc_ - 0.01), (xm + 0.07 + dx, d / 2 + 0.006, h - 0.3)]
            mb.tube(fillet(pts, 0.03, 2), 0.0032 if k else 0.0028, seg=5, mat="cable")
            mb.box(p0 + Vector((-0.009, -0.004, -0.006)), p0 + Vector((0.009, 0.012, 0.006)), "cable", bevel=0.002, seg=1)
        pts = [tuple(kc), (kc.x - 0.01, kc.y + 0.04, h + 0.0026), (xm - 0.1, ym - 0.02, h + 0.0026), (xm - 0.13, ym + 0.09, h + 0.0026),
               (xm - 0.12, d / 2 - 0.004, h + 0.0026), (xm - 0.119, d / 2 + 0.0042, h - 0.008), (xm - 0.115, d / 2 + 0.0045, h - 0.25)]
        mb.tube(fillet(pts, 0.03, 2), 0.0022, seg=4, mat="cable")
        pts = [tuple(mc), (mc.x + 0.01, mc.y - 0.03, h + 0.0052), (mx + 0.06, my - 0.06, h + 0.0052), (mx + 0.1, my + 0.07, h + 0.0052),
               (mx + 0.09, my + 0.13, h + 0.0022), (xm + 0.2, ym + 0.06, h + 0.0022), (xm + 0.16, d / 2 - 0.004, h + 0.0022),
               (xm + 0.159, d / 2 + 0.0038, h - 0.008), (xm + 0.155, d / 2 + 0.004, h - 0.22)]
        mb.tube(fillet(pts, 0.03, 2), 0.0018, seg=4, mat="cable")
    # teléfono en la esquina trasera izquierda
    px, py = -w / 2 + 0.17, d / 2 - 0.14
    Mph = _T(px, py, h) @ _Rz(float(r.uniform(8, 22)))
    pc = _phone(mb, Mph, seed=int(r.integers(1e6)))
    occ.append((px - 0.17, py - 0.15, px + 0.12, py + 0.12))
    mb.tube(fillet([tuple(pc), (pc.x + 0.02, pc.y + 0.02, h + 0.0025), (pc.x + 0.04, d / 2 - 0.004, h + 0.0025),
                    (pc.x + 0.041, d / 2 + 0.0038, h - 0.008), (pc.x + 0.045, d / 2 + 0.004, h - 0.18)], 0.03, 2), 0.0018, seg=4, mat="cable")
    # carpetas de palanca con sujetalibros sobre el pedestal derecho
    if papers:
        nb = int(r.integers(3, 6))
        xb = w / 2 - 0.035
        yc = d / 2 - 0.16
        mats = ("plastic_blue", "sign_red", "sign_green", "sign_blue", "plastic", "paint_yellow")
        labels = ("LOG", "STOCK", "ADMIN", "2025", "2026", "MISC", "FORMS", "STAFF")
        bws = []
        for k in range(nb):
            bw = float(r.choice([0.055, 0.075, 0.08]))
            if xb - bw < xR0 - 0.02:
                break
            hb = float(r.uniform(0.30, 0.315))
            yaw = float(r.uniform(-0.4, 0.4))
            mat_, lab_ = mats[int(r.integers(0, len(mats)))], labels[int(r.integers(0, len(labels)))]
            bws.append(bw)
            _binder(mb, _T(xb - bw / 2, yc, h + 0.0016) @ _Rz(yaw), bw - 0.004, 0.285, hb, mat_, lab_)
            xb -= bw
        _bookend(mb, _T(xb - 0.0045, yc, h))
        occ.append((xb - 0.01, yc - 0.15, w / 2, yc + 0.15))
        cpx, cpy = w / 2 - 0.07, yc - 0.205
        if free(cpx - 0.04, cpy - 0.04, cpx + 0.04, cpy + 0.04):
            _pen_cup(mb, _T(cpx, cpy, h), seed=int(r.integers(1e6)))
            occ.append((cpx - 0.04, cpy - 0.04, cpx + 0.04, cpy + 0.04))
        nst = int(r.integers(2, 4))
        for k in range(nst):
            for _ in range(60):
                ang = float(r.uniform(-9, 9))
                hx, hy = 0.122, 0.152
                x = float(r.uniform(-w / 2 + hx + 0.012, w / 2 - hx - 0.012))
                y = float(r.uniform(-d / 2 + hy + 0.012, d / 2 - hy - 0.012))
                if free(x - hx, y - hy, x + hx, y + hy):
                    _paper_stack(mb, _T(x, y, h + 0.0012) @ _Rz(ang), int(r.integers(1e6)), n_loose=int(r.integers(1, 4)),
                                 folder=(k == 0 and r.random() < 0.7))
                    occ.append((x - hx, y - hy, x + hx, y + hy))
                    break
    return mb


# ======================================================================================================== archivero
def filing_cabinet(seed=0, n=4):
    """Archivero vertical de lámina de n cajones (0,47 x 0,62): costados formados con pestaña de retorno al frente, tapa
    sobrepuesta de cantos redondeados, travesaños entre cajones, zoclo rehundido, frentes de cajón con holgura de 4 mm,
    jaladera de puente con escudos y gatillo, portaetiqueta con tarjeta rotulada y labios, cerradura en el travesaño superior."""
    r = rng(seed)
    mb = MB()
    lab0 = int(r.integers(0, 8))
    W2, yF, yB = 0.235, -0.30, 0.31
    H = 0.33 * n + 0.04
    zt = H - 0.014
    for s in (-1, 1):                                                        # costados con retorno
        xo, xi, xr = s * W2, s * (W2 - 0.006), s * (W2 - 0.024)
        pts = [(xo, yB), (xo, yF), (xr, yF), (xr, yF + 0.006), (xi, yF + 0.006), (xi, yB)]
        loft_x(mb, fillet2d(pts, [0.002, 0.007, 0.0015, 0.001, 0.002, 0.002], 2), 0.0, zt, "enamel", re=0.0, M=LZ)
    mb.box((-W2 - 0.002, yF - 0.012, zt), (W2 + 0.002, yB, H), "enamel", bevel=0.006, seg=3)                 # tapa
    mb.box((-W2 + 0.006, yB - 0.008, 0.0), (W2 - 0.006, yB, zt), "enamel", bevel=0.0)                       # respaldo (contra el muro)
    mb.box((-W2 + 0.024, yF + 0.016, 0.0), (W2 - 0.024, yF + 0.03, 0.04), "enamel", bevel=0.003, seg=1)     # zoclo rehundido
    mb.box((-W2 + 0.006, yF + 0.016, 0.04), (W2 - 0.006, yB - 0.008, 0.048), "enamel", bevel=0.0)           # fondo (oculto)
    p = (zt - 0.026 - 0.048) / n
    zs = [0.048 + k * p for k in range(n + 1)]
    mb.box((-W2 + 0.024, yF, zt - 0.026), (W2 - 0.024, yF + 0.02, zt), "enamel", bevel=0.002, seg=1)        # travesaño superior
    for z in zs[:-1]:                                                         # travesaños: solo se ven por la holgura de 8 mm
        mb.box((-W2 + 0.024, yF + 0.002, z - 0.006), (W2 - 0.024, yF + 0.02, z + 0.006), "enamel", bevel=0.0)
    lock_cyl(mb, _T(0.17, yF, zt - 0.013) @ _Rx(90))
    labels = ("A - D", "E - H", "I - L", "M - P", "Q - T", "U - Z", "MISC", "OLD")
    for k in range(n):
        z0, z1 = zs[k] + 0.004, zs[k + 1] - 0.004
        yfd = yF - 0.003
        mb.box((-W2 + 0.028, yfd, z0), (W2 - 0.028, yfd + 0.02, z1), "enamel", bevel=0.005, seg=2)
        zh = z0 + (z1 - z0) * 0.56
        path = fillet([(-0.062, yfd + 0.0015, zh), (-0.062, yfd - 0.024, zh), (0.062, yfd - 0.024, zh), (0.062, yfd + 0.0015, zh)], 0.013, 4)
        mb.sweep(rr_profile(0.011, 0.02, 0.0045, 2), path, mat="steel", normal=(0, 0, 1))
        for x in (-0.062, 0.062):                                            # escudos de la jaladera
            mb.box((x - 0.011, yfd - 0.003, zh - 0.017), (x + 0.011, yfd + 0.001, zh + 0.017), "steel", bevel=0.0012, seg=1)
            port.lathe(mb, [(0.0028, 0.0), (0.0027, 0.0008), (0.0016, 0.0015)], seg=6, mat="steel",
                       M=_T(x + (0.006 if x > 0 else -0.006), yfd - 0.003, zh + 0.011) @ _Rx(90))
        mb.box((-0.03, yfd - 0.013, zh - 0.0125), (0.03, yfd - 0.0005, zh - 0.0075), "steel", bevel=0.0015, seg=1)   # gatillo
        zl = zh + 0.052                                                       # portaetiqueta
        mb.box((-0.046, yfd - 0.0016, zl - 0.021), (0.046, yfd + 0.0005, zl + 0.021), "steel", bevel=0.0007, seg=1)
        mb.box((-0.039, yfd - 0.0031, zl - 0.0145), (0.039, yfd - 0.0012, zl + 0.0145), "paper", bevel=0.0)
        for zz in (zl - 0.016, zl + 0.016):
            mb.cyl((-0.043, yfd - 0.0026, zz), (0.043, yfd - 0.0026, zz), 0.0016, seg=6, mat="steel")
        for xx in (-0.043, 0.043):
            mb.cyl((xx, yfd - 0.0026, zl - 0.0175), (xx, yfd - 0.0026, zl + 0.0175), 0.0016, seg=6, mat="steel")
        _text(mb, labels[(k + lab0) % len(labels)], 0.011, 0.0016, "cable", _T(0, yfd - 0.0029, zl - 0.0045) @ _Rx(90), res=2)
    return mb


# ======================================================================================================== mostrador
def _reception(mb, w, d, h, r, top, front):
    y0c = -d / 2 + 0.02
    tc = 0.018
    yk = y0c + 0.045
    yR = y0c + 0.25
    yE = d / 2 - 0.012
    zW0, zW1 = 0.72, 0.75
    zT0 = h - 0.032
    xi = w / 2 - 0.025
    # frente: tableros laminados en dos franjas con reveles de aluminio
    nP = max(2, int(round(w / 0.8)))
    pw = (w - (nP - 1) * 0.008) / nP
    for (za, zb) in ((0.105, 0.795), (0.805, zT0 - 0.002)):
        for i in range(nP):
            xa = -w / 2 + i * (pw + 0.008)
            rbox(mb, (xa, y0c, za), (xa + pw, y0c + tc, zb), front, r=0.003)
    for i in range(1, nP):
        xg = -w / 2 + i * (pw + 0.008) - 0.004
        rbox(mb, (xg - 0.0042, y0c + 0.008, 0.105), (xg + 0.0042, y0c + tc + 0.002, zT0 - 0.002), "aluminium", r=0.001)
    rbox(mb, (-w / 2 + 0.002, y0c + 0.008, 0.7955), (w / 2 - 0.002, y0c + tc + 0.002, 0.8045), "aluminium", r=0.001)
    rbox(mb, (-xi, y0c + tc, 0.106), (xi, y0c + 0.036, zT0), front, r=0.002)                         # respaldo del frente
    rbox(mb, (-xi, yk, 0.0), (xi, yk + 0.018, 0.0995), front, r=0.002)                                # zoclo rehundido
    rbox(mb, (-xi, y0c + tc, 0.10), (xi, yk + 0.018, 0.118), front, r=0.002)                          # fondo
    loft_x(mb, fillet2d([(yk - 0.008, 0.0), (yk + 0.001, 0.0), (yk + 0.001, 0.098), (yk - 0.0035, 0.098), (yk - 0.0035, 0.014),
                         (yk - 0.008, 0.004)], [0.0, 0.0, 0.0, 0.0015, 0.006, 0.002], 3), -xi, xi, "rubber", re=0.0)
    zb = 0.32                                                                                         # defensa de vinil (camillas, sillas)
    loft_x(mb, fillet2d([(y0c + 0.003, zb - 0.022), (y0c + 0.003, zb + 0.022), (y0c - 0.007, zb + 0.017), (y0c - 0.0125, zb),
                         (y0c - 0.007, zb - 0.017)], [0.0, 0.0, 0.006, 0.008, 0.006], 4), -w / 2 + 0.006, w / 2 - 0.006, "vinyl", re=0.008,
           ne=3)
    for i in range(int(w / 0.6) + 1):                                                                 # tornillos de la defensa
        x = -w / 2 + 0.08 + i * (w - 0.16) / int(w / 0.6)
        port.lathe(mb, [(0.0, 0.0), (0.0035, 0.0), (0.0033, 0.0008), (0.002, 0.0015), (0.0, 0.0016)], seg=8, mat="steel",
                   M=_T(x, y0c - 0.0123, zb) @ _Rx(90))
    # costados en L (alto al frente, bajo en el lado de trabajo) con canto de PVC
    gab = [(yk, 0.002), (yE, 0.002), (yE, zW1), (yR, zW1), (yR, zT0), (y0c + tc, zT0), (y0c + tc, 0.105), (yk, 0.105)]
    gab_f = fillet2d(gab, [0.002, 0.003, 0.012, 0.02, 0.004, 0.002, 0.002, 0.002], 4)
    for s in (-1, 1):
        xa = xi if s > 0 else -w / 2
        loft_x(mb, gab_f, xa, xa + 0.025, front, re=0.0)
        edge_band(mb, gab_f, "x", xa, 0.025, "plastic")
    if w > 2.0:                                                                                       # costado intermedio
        mid = fillet2d([(y0c + 0.036, 0.002), (yE, 0.002), (yE, zW0), (y0c + 0.036, zW0)], [0.0, 0.003, 0.01, 0.0], 3)
        loft_x(mb, mid, -0.0125, 0.0125, front, re=0.0)
        edge_band(mb, mid, "x", -0.0125, 0.025, "plastic")
    # cubierta de atención con canto boleado al frente
    tp = fillet2d([(-d / 2 - 0.045, zT0), (yR + 0.012, zT0), (yR + 0.012, h), (-d / 2 - 0.045, h)], [0.0158, 0.004, 0.004, 0.0158], 6)
    loft_x(mb, tp, -w / 2 - 0.02, w / 2 + 0.02, top, re=0.008, ne=3)
    rbox(mb, (-xi, yR - 0.018, zW1), (xi, yR, zT0), front, r=0.002)                                   # peto interior
    # superficie de trabajo del lado del personal (canto boleado) con pasacables
    ws = fillet2d([(y0c + 0.036, zW0), (d / 2, zW0), (d / 2, zW1), (y0c + 0.036, zW1)], [0.0, 0.0148, 0.0148, 0.0], 5)
    loft_x(mb, ws, -xi, xi, top, re=0.0)
    gx, gy = xi - 0.32, (yR + d / 2) / 2 + 0.03
    port.lathe(mb, [(0.0255, -0.004), (0.0335, -0.004), (0.0335, 0.0004), (0.034, 0.0012), (0.0325, 0.0022), (0.029, 0.0024),
                    (0.0262, 0.0016), (0.0255, 0.0)], seg=28, mat="plastic", M=_T(gx, gy, zW1))
    port.lathe(mb, [(0.0, -0.002), (0.025, -0.002), (0.025, 0.0015), (0.0235, 0.0019), (0.0, 0.0019)], seg=24, mat="cable",
               M=_T(gx, gy, zW1))
    # objetos del lado del personal: teléfono (cordón al pasacables), formatos y portalápices
    px, py = gx - 0.25, gy + 0.005
    Mph = _T(px, py, zW1) @ _Rz(180 + float(r.uniform(10, 25)))
    pc = _phone(mb, Mph, seed=int(r.integers(1e6)))
    mb.tube(smooth_path([tuple(pc), (pc.x + 0.03, pc.y + 0.005, zW1 + 0.0025), (gx - 0.03, gy - 0.03, zW1 + 0.0025),
                         (gx, gy - 0.02, zW1 + 0.0028), (gx, gy - 0.015, zW1 - 0.05)], 5), 0.0018, seg=5, mat="cable")
    sx = -xi + 0.28 + float(r.uniform(0, 0.25))
    _paper_stack(mb, _T(sx, (yR + d / 2) / 2 + 0.005, zW1 + 0.0012) @ _Rz(float(r.uniform(-8, 8)) + 90), int(r.integers(1e6)),
                 n_loose=2, folder=False)
    _pen_cup(mb, _T(sx + 0.24, yR + 0.06, zW1), seed=int(r.integers(1e6)))


def _base_run(mb, w, d, h, r, top, front):
    tk = 0.04
    zc = h - tk
    yd = -d / 2
    yc0 = yd + 0.019
    yE = d / 2 - 0.004
    xi = w / 2 - 0.018
    yk = yc0 + 0.05
    gab = fillet2d([(yk, 0.002), (yE, 0.002), (yE, zc), (yc0, zc), (yc0, 0.10), (yk, 0.10)], [0.002, 0.002, 0.002, 0.002, 0.002, 0.002], 2)
    for s in (-1, 1):
        xa = xi if s > 0 else -w / 2
        loft_x(mb, gab, xa, xa + 0.018, front, re=0.0)
        edge_band(mb, gab, "x", xa, 0.018, "plastic")
    rbox(mb, (-xi, yE - 0.012, 0.1005), (xi, yE, zc), front, r=0.002)                                 # respaldo
    rbox(mb, (-xi, yc0 + 0.01, 0.10), (xi, yE - 0.012, 0.118), front, r=0.002)                         # fondo
    rbox(mb, (-xi, yk, 0.0), (xi, yk + 0.018, 0.0995), front, r=0.002)                                # zoclo
    loft_x(mb, fillet2d([(yk - 0.008, 0.0), (yk + 0.001, 0.0), (yk + 0.001, 0.098), (yk - 0.0035, 0.098), (yk - 0.0035, 0.014),
                         (yk - 0.008, 0.004)], [0.0, 0.0, 0.0, 0.0015, 0.006, 0.002], 3), -xi, xi, "rubber", re=0.0)
    nm = max(2, int(round(w / 0.6)))
    mw = w / nm
    stack = int(r.integers(0, nm))
    g = 0.0015
    for i in range(nm):
        xa, xb = -w / 2 + i * mw + g, -w / 2 + (i + 1) * mw - g
        if 0 < i:
            rbox(mb, (xa - g - 0.009, yc0, 0.118), (xa - g + 0.009, yE - 0.012, zc), front, r=0.002)   # divisiones
        if i == stack:
            zz = [0.103, 0.103 + (zc - 0.106) * 0.4, 0.103 + (zc - 0.106) * 0.7, zc - 0.003]
            parts = [(zz[k] + (g if k else 0.0), zz[k + 1] - g, "drawer") for k in range(3)]
        else:
            parts = [(0.103, zc - 0.148, "door"), (zc - 0.145, zc - 0.003, "drawer")]
        for (za, zb, kind) in parts:
            rbox(mb, (xa, yd, za), (xb, yd + 0.019, zb), front, r=0.0025)
            if kind == "drawer":
                dpull(mb, _T((xa + xb) / 2, yd, min(zb - 0.045, (za + zb) / 2)), cc=0.128, proj=0.03)
            else:
                hinge_left = (i % 2 == 0)
                xp = xb - 0.04 if hinge_left else xa + 0.04
                dpull(mb, _T(xp, yd, zb - 0.1) @ _Ry(90), cc=0.128, proj=0.03)
    # cubierta
    yf, yb = -d / 2 - 0.022, d / 2
    if top == "steel":
        tp = [(yf, zc), (yb, zc), (yb, h + 0.022), (yb - 0.006, h + 0.022), (yb - 0.016, h - 0.004), (yf + 0.022, h - 0.004),
              (yf + 0.012, h + 0.002), (yf + 0.004, h + 0.002), (yf, h - 0.004)]
        loft_x(mb, fillet2d(tp, [0.002, 0.002, 0.003, 0.003, 0.012, 0.006, 0.004, 0.004, 0.006], 4), -w / 2 - 0.012, w / 2 + 0.012,
               "steel", re=0.004, ne=2)
    else:
        tp = [(yf, zc), (yb, zc), (yb, h + 0.02), (yb - 0.012, h + 0.02), (yb - 0.012, h), (yf, h)]
        loft_x(mb, fillet2d(tp, [0.019, 0.002, 0.004, 0.004, 0.006, 0.019], 5), -w / 2 - 0.012, w / 2 + 0.012, top, re=0.004, ne=2)


def counter(w=2.4, d=0.6, h=1.05, seed=0, top="wood_varnish", front="plastic"):
    """Mostrador. Alto (h ≥ 1): estación de recepción/enfermería: frente de tableros laminados en dos franjas con reveles de
    aluminio, zoclo rehundido con rodapié de hule, costados en L con canto de PVC, cubierta de atención con canto boleado
    volada al frente, peto interior, superficie de trabajo a 0,75 con canto boleado y pasacables, costado intermedio en
    tramos largos; teléfono, formatos y portalápices del lado del personal. Bajo (h < 1, cocina/farmacia): bajo-cubierta de
    módulos con cajón y puerta (o cajonera), jaladeras de alambre, divisiones visibles por las holguras, zoclo con rodapié y
    cubierta de acero inoxidable con nariz y ceja antiderrame al frente y zócalo sanitario atrás."""
    r = rng(seed)
    mb = MB()
    if h < 1.0:
        _base_run(mb, w, d, h, r, top, front)
    else:
        _reception(mb, w, d, h, r, top, front)
    return mb


# ======================================================================================================== sillas
def pan_shell(mb, outline, mat, M=None, dish=0.0, t=0.0016, lip=0.014, deform=None, inner=(0.45, 0.9)):
    """Bandeja de lámina embutida (asiento/respaldo de silla plegable): cara superior a z = 0 en el borde y hundida `dish` al
    centro, borde enrollado hacia abajo en una ceja de alto `lip` y cara inferior a `t`; sólido cerrado.
    outline: contorno en planta (x, y) con radios ≥ 2 cm. deform(x, y, z) -> (x, y, z) opcional (curvatura)."""
    o = _ccw(_dedupe(outline))
    cx = sum(p[0] for p in o) / len(o)
    cy = sum(p[1] for p in o) / len(o)

    base = offset_ring(o, -0.02)

    def sc(s, z):
        return [(cx + (x - cx) * s, cy + (y - cy) * s, z) for (x, y) in base]

    def off(dd, z):
        return [(x, y, z) for (x, y) in offset_ring(o, dd)]
    rings = [sc(s, -dish * (1 - s * s)) for s in inner]
    rings += [off(-0.014, -dish * 0.02), off(-0.005, 0.0), off(-0.0012, -0.0012), off(0.0004, -0.0048), off(0.0, -lip + 0.002),
              off(-0.0016, -lip), off(-0.0032, -lip + 0.0012), off(-0.0034, -0.006), off(-0.012, -t - 0.001)]
    rings += [sc(s, -dish * (1 - s * s) - t) for s in reversed(inner)]
    if deform is not None:
        rings = [[deform(*p) for p in ring] for ring in rings]
    ring_shell(mb, rings, mat, M)


def _boot(mb, x, y0, slope, r=0.0135, h=0.04, mat="rubber"):
    """Regatón de hule de pata inclinada: anillos horizontales que siguen la pata (base plana sobre el piso)."""
    k = math.sqrt(1 + slope * slope)
    st = []
    for (z, f) in ((0.0, 0.93), (0.0025, 1.0), (h - 0.006, 1.0), (h, 0.9)):
        st.append((z, 2 * r * f, 2 * r * f * k, y0 + slope * z))
    zloft(mb, st, seg=10, mat=mat, M=_T(x, 0, 0), ex=2.0)


def folding_chair(seed=0):
    """Silla plegable de lámina: bastidor de tubo de 22 mm doblado (postes delanteros con quiebre a la altura del asiento),
    patas traseras de 19 mm cruzadas en tijera con perno de pivote, arandela separadora y tuerca, travesaños soldados con
    cordón, asiento de lámina embutida con borde enrollado sobre ménsulas remachadas, respaldo curvo de lámina con cejas
    enrolladas remachado a los postes, regatones de hule y tapones en los postes."""
    del seed                                  # mismo modelo en toda la cocina: sin variación aleatoria
    mb = MB()
    fr = "enamel"
    xf, xr = 0.196, 0.172
    F, K, Tp = (-0.212, 0.012), (0.03, 0.445), (0.152, 0.858)
    R0, R1 = (0.198, 0.012), (-0.11, 0.432)
    sf = (K[0] - F[0]) / (K[1] - F[1])
    sr = (R1[0] - R0[0]) / (R1[1] - R0[1])
    for s in (-1, 1):
        mb.tube(fillet([(s * xf, F[0], F[1]), (s * xf, K[0], K[1]), (s * xf, Tp[0], Tp[1])], 0.12, 5), 0.011, seg=10, mat=fr)
        mb.tube([(s * xr, R0[0], R0[1]), (s * xr, R1[0], R1[1])], 0.0095, seg=10, mat=fr)
        _boot(mb, s * xf, F[0] - sf * F[1], sf)
        _boot(mb, s * xr, R0[0] - sr * R0[1], sr, r=0.012)
        d_ = Vector((0, Tp[0] - K[0], Tp[1] - K[1])).normalized()                     # tapón del poste
        port.lathe(mb, [(0.0115, 0.0), (0.0118, 0.006), (0.0105, 0.011), (0.006, 0.0138)], seg=10, mat="rubber", M=_T(s * xf, Tp[0] - d_.y * 0.004, Tp[1] - d_.z * 0.004) @ _Rx(-math.degrees(math.atan2(d_.y, d_.z))))
    # pivote de tijera: cruce de las rectas de pata delantera y trasera
    tz = (R0[0] - F[0] + sf * F[1] - sr * R0[1]) / (sf - sr)
    py = F[0] + sf * (tz - F[1])
    for s in (-1, 1):
        port.lathe(mb, [(0.0068, 0.0), (0.0064, 0.0018), (0.004, 0.0034), (0.0015, 0.0038)], seg=8, mat="steel",
                   M=_T(s * (xf + 0.0105), py, tz) @ _Ry(90 * s))
        port.lathe(mb, [(0.0075, 0.0), (0.0075, 0.0035)], seg=8, mat="steel", M=_T(s * (xr + 0.0092), py, tz) @ _Ry(90 * s))
        port.bolt(mb, _T(s * (xr - 0.0092), py, tz) @ _Ry(-90 * s), d=0.0055, stud=0.002, mat="steel")
    # travesaños con cordón de soldadura
    zs = 0.11
    ys = F[0] + sf * (zs - F[1])
    mb.tube([(-xf, ys, zs), (xf, ys, zs)], 0.0085, seg=8, mat=fr)
    zr = 0.085
    yr = R0[0] + sr * (zr - R0[1])
    mb.tube([(-xr, yr, zr), (xr, yr, zr)], 0.0078, seg=8, mat=fr)
    for (x, y, z, rr_) in ((xf - 0.0095, ys, zs, 0.0085), (-xf + 0.0095, ys, zs, 0.0085), (xr - 0.0082, yr, zr, 0.0078),
                           (-xr + 0.0082, yr, zr, 0.0078)):
        lathe_closed(mb, [(rr_ - 0.0005, -0.0028), (rr_ + 0.002, -0.0006), (rr_ + 0.0008, 0.0024), (rr_ - 0.0005, 0.0026)], 8, fr,
                     _T(x, y, z) @ _Ry(90 if x > 0 else -90))
    # asiento de lámina embutida
    zt = 0.456
    seat = fillet2d([(-0.2, -0.19), (0.2, -0.19), (0.166, 0.172), (-0.166, 0.172)], [0.05, 0.05, 0.035, 0.035], 6)
    pan_shell(mb, seat, "paint_green", M=_T(0, 0, zt), dish=0.007, lip=0.016)
    for s in (-1, 1):                                                                  # ménsulas y remaches
        mb.box((s * 0.158 - 0.012, -0.135, zt - 0.031), (s * 0.158 + 0.012, -0.085, zt - 0.0045), "steel", bevel=0.0015, seg=1)
        port.lathe(mb, [(0.0055, 0.0), (0.005, 0.0016), (0.003, 0.0029)], seg=6, mat="steel",
                   M=_T(s * (xr + 0.0095), R1[0] + 0.004, R1[1] - 0.004) @ _Ry(90 * s))
        mb.box((s * 0.181 - 0.0016, 0.012, zt - 0.03), (s * 0.181 + 0.0016, 0.07, zt - 0.006), "steel", bevel=0.0007, seg=1)
        port.lathe(mb, [(0.0055, 0.0), (0.005, 0.0016), (0.003, 0.0029)], seg=6, mat="steel",
                   M=_T(s * (xf + 0.0105), 0.042, zt - 0.018) @ _Ry(90 * s))
    # respaldo curvo
    zc = 0.758
    tpost = (zc - K[1]) / (Tp[1] - K[1])
    yp = K[0] + (Tp[0] - K[0]) * tpost
    ang = math.degrees(math.atan2(Tp[0] - K[0], Tp[1] - K[1]))
    Mb = _T(0, yp - 0.0125, zc) @ _Rx(-ang)
    # respaldo de lámina prensada: sección con cejas enrolladas hacia atrás arriba y abajo, cantos laterales redondos y
    # curvatura cóncava hacia el usuario (centro 16 mm más atrás que los extremos)
    prof = [(0.011, -0.074), (0.0045, -0.0835), (-0.0015, -0.081), (-0.0005, -0.062), (0.0015, -0.03), (0.002, 0.0), (0.0015, 0.03),
            (-0.0005, 0.062), (-0.0015, 0.081), (0.0045, 0.0835), (0.011, 0.075)]
    tmp = MB()
    from kit.clinic import shell_strip
    shell_strip(tmp, prof, 0.405, 0.0016, "paint_green", smooth_n=2, edge_seg=3)
    for v in tmp.bm.verts:
        v.co.y += 0.016 * (1 - min(1.0, (v.co.x / 0.2025) ** 2))
    mb.join(tmp, Mb)
    Mb = Mb @ Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
    for s in (-1, 1):
        for zz in (-0.045, 0.045):
            port.lathe(mb, [(0.0052, -0.001), (0.0048, 0.0008), (0.003, 0.0019)], seg=6, mat="steel", M=Mb @ _T(s * xf, zz, -0.0001))
    return mb


def _sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _soft_block(mb, M, W, L, H, re, mat, deform, step=0.03, n_round=4, drop=()):
    """Bloque acolchado: caja redondeada subdividida (aristas y esquinas de radio re) deformada por deform(x, y, z) en
    arreglos numpy (abombado, hundido, cascada, curvatura). z de 0 a H, centrado en x, y.
    drop: caras planas que nunca se ven [(eje, signo)] (p. ej. (2, -1) = fondo apoyado en la concha): se omiten."""
    from kit import softgoods as sg
    co, flat, lens = sg._rbox_arrays(W, L, H, re=re, step=step, n_round=n_round)
    if drop:
        ctr = np.array([0.0, 0.0, H / 2])
        E = np.array([W / 2, L / 2, H / 2])
        rel = co - ctr
        starts = np.concatenate([[0], np.cumsum(lens)[:-1]])
        keep = np.ones(len(lens), bool)
        for (ax, sgn) in drop:
            onf = rel[:, ax] * sgn > E[ax] - 1e-6
            keep &= ~np.minimum.reduceat(onf[flat].astype(np.int8), starts).astype(bool)
        idx = np.repeat(keep, lens)
        flat, lens = flat[idx], lens[keep]
    x, y, z = deform(co[:, 0].copy(), co[:, 1].copy(), co[:, 2].copy())
    co = np.stack([x, y, z], -1)
    sg._to_mb(mb, co, flat, lens, mat, M)


def _welt_loop(W, L, re, z, n=4, dens=0.035):
    """Contorno del vivo (a 45° del redondeo superior) remuestreado cada `dens` m: [(x, y)]."""
    a, b = W / 2 - re, L / 2 - re
    rp = (re + 0.0012) * math.cos(PI / 4)
    pts = []
    for (cx, cy, a0) in ((a, -b, -PI / 2), (a, b, 0.0), (-a, b, PI / 2), (-a, -b, PI)):
        for k in range(n + 1):
            ang = a0 + (PI / 2) * k / n
            pts.append((cx + rp * math.cos(ang), cy + rp * math.sin(ang)))
    pts.append(pts[0])
    dense = [pts[0]]
    for p0, p1 in zip(pts[:-1], pts[1:]):
        m = max(1, int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / dens))
        for k in range(1, m + 1):
            dense.append((p0[0] + (p1[0] - p0[0]) * k / m, p0[1] + (p1[1] - p0[1]) * k / m))
    return dense


def _twin_caster(mb, M):
    """Rodaja doble de silla de oficina (Ø 50): capuchón, espiga, dos ruedas con maza. Origen en el piso bajo la espiga."""
    zloft(mb, [(0.02, 0.014, 0.052, 0.012), (0.038, 0.016, 0.058, 0.008), (0.05, 0.014, 0.046, 0.002), (0.057, 0.01, 0.022, -0.004)],
          seg=10, mat="cable", M=M, ex=2.6)
    for s in (-1, 1):                                    # la espiga queda dentro de la cuenca de la base: no se modela
        Mw = M @ _T(s * 0.0155, 0.014, 0.025) @ _Ry(90)
        port.lathe(mb, [(0.0075, -0.0082 * s), (0.021, -0.0082 * s), (0.025, -0.003 * s), (0.025, 0.003 * s), (0.021, 0.0082 * s),
                        (0.0085, 0.0084 * s), (0.0075, 0.0096 * s)], seg=12, mat="cable", M=Mw, caps=True)


def office_chair(seed=0):
    """Silla secretarial: base de 5 brazos de nylon con nervio y cuencas de rodaja, rodajas dobles, pistón de gas cromado con
    funda telescópica lisa, mecanismo con cono, perilla de tensión estriada y palanca de altura, concha de asiento, cojín de
    asiento subdividido (abombado, hundido de uso, frente en cascada, vivo perimetral), respaldo con curva lumbar, vivo
    perimetral y costura horizontal en concha plástica, solera de respaldo doblada con placa y perilla de altura,
    descansabrazos en T de solera con almohadilla."""
    r = rng(seed)
    mb = MB()
    ph = float(r.uniform(0, 72))
    for k in range(5):                                                                 # base de 5 brazos
        Ma = _Rz(72 * k + ph)
        port.loft(mb, [(0.035, 0.064, 0.052, 0.088), (0.12, 0.052, 0.046, 0.083), (0.22, 0.044, 0.036, 0.074),
                       (0.285, 0.041, 0.033, 0.07), (0.302, 0.036, 0.026, 0.07)], seg=12, mat="cable", M=Ma, ex=3.2)
        port.loft(mb, [(0.05, 0.012, 0.016, 0.112), (0.25, 0.01, 0.01, 0.089), (0.27, 0.006, 0.004, 0.0855)], seg=6, mat="cable",
                  M=Ma, ex=2.4)
        port.lathe(mb, [(0.0165, 0.05), (0.0175, 0.054), (0.0175, 0.066)], seg=10, mat="cable", M=Ma @ _T(0.288, 0, 0))
        _twin_caster(mb, Ma @ _T(0.288, 0, 0) @ _Rz(float(r.uniform(0, 360))))
    port.lathe(mb, [(0.046, 0.058), (0.052, 0.068), (0.052, 0.104), (0.044, 0.116), (0.034, 0.12)], seg=16, mat="cable")
    port.lathe(mb, [(0.0315, 0.118), (0.0315, 0.205), (0.0292, 0.209), (0.0288, 0.272), (0.0265, 0.276), (0.0262, 0.298)], seg=16,
               mat="cable")
    port.lathe(mb, [(0.0142, 0.296), (0.0142, 0.39)], seg=12, mat="steel")
    # mecanismo
    zs = 0.43
    port.lathe(mb, [(0.02, 0.37), (0.03, 0.398), (0.03, 0.404)], seg=12, mat="cable")
    mb.box((-0.095, -0.135, 0.398), (0.095, 0.115, zs), "cable", bevel=0.006, seg=2)
    mb.box((-0.12, -0.15, zs - 0.004), (0.12, 0.14, zs + 0.002), "cable", bevel=0.002, seg=1)
    Mk = _T(0, -0.135, 0.405) @ _Rx(90)
    port.lathe(mb, [(0.024, 0.0), (0.03, 0.006), (0.031, 0.012), (0.03, 0.03), (0.024, 0.036)], seg=12, mat="cable", M=Mk)
    for k in range(12):                                                                # estrías de la perilla de tensión
        Mr = Mk @ _Rz(30 * k + 15) @ _T(0.0308, 0, 0)
        mb.box((-0.0018, -0.0022, 0.008), (0.0018, 0.0022, 0.029), "cable", bevel=0.0, m=Mr)
    mb.tube(fillet([(0.09, -0.06, 0.41), (0.15, -0.075, 0.405), (0.2, -0.1, 0.39)], 0.03, 3), 0.0045, seg=6, mat="steel")
    port.loft(mb, [(0.0, 0.018, 0.008, 0.0), (0.012, 0.024, 0.012, 0.0), (0.055, 0.026, 0.012, 0.0), (0.065, 0.016, 0.008, 0.0)],
              seg=8, mat="cable", M=_T(0.195, -0.098, 0.391) @ _Rz(-27) @ _Ry(12), ex=2.6)
    # concha y cojín de asiento
    mb.box((-0.236, -0.226, zs), (0.236, 0.222, zs + 0.024), "cable", bevel=0.009, seg=2)
    Ws, Ls, Hs, rs = 0.47, 0.45, 0.075, 0.028

    def seat_def(x, y, z):
        ft = _sstep(Hs * 0.35, Hs, z)
        z = z + 0.011 * (1 - (2 * x / Ws) ** 2) * (1 - (2 * y / Ls) ** 4) * ft
        z = z - 0.012 * np.exp(-((x / 0.14) ** 2 + ((y - 0.035) / 0.15) ** 2)) * ft
        z = z - 0.016 * _sstep(-Ls / 2 + 0.11, -Ls / 2, y) * ft
        z = z + 0.004 * _sstep(0.11, 0.2, np.abs(x)) * ft
        return x, y, z
    Mseat = _T(0, -0.002, zs + 0.016)
    _soft_block(mb, Mseat, Ws, Ls, Hs, rs, "vinyl", seat_def, step=0.05, n_round=3, drop=((2, -1),))
    loop = np.array([(x, y, Hs - rs + (rs + 0.0012) * math.sin(PI / 4)) for (x, y) in _welt_loop(Ws, Ls, rs, 0)])
    X, Y, Z = seat_def(loop[:, 0], loop[:, 1], loop[:, 2])
    mb.tube([tuple(Mseat @ Vector(p)) for p in zip(X, Y, Z)], 0.0034, seg=5, mat="vinyl")
    # respaldo: cojín con curva lumbar sobre concha plástica
    Wb, Lb, Hb, rb_ = 0.44, 0.066, 0.485, 0.026

    def bend(x, z):
        return -0.016 * np.exp(-((z - 0.15) / 0.1) ** 2) - 0.028 * (2 * x / Wb) ** 2 + 0.02 * (z / Hb) ** 2

    def back_def(x, y, z):
        ff = _sstep(-Lb * 0.1, -Lb * 0.5, y)
        y = y - 0.007 * (1 - (2 * x / Wb) ** 2) * (1 - (2 * z / Hb - 1) ** 4) * ff
        return x, y + bend(x, z), z
    Mback = _T(0, 0.236, 0.565) @ _Rx(-6)
    _soft_block(mb, Mback, Wb, Lb, Hb, rb_, "vinyl", back_def, step=0.05, n_round=3, drop=((1, 1),))
    _soft_block(mb, Mback @ _T(0, 0, -0.006), Wb + 0.014, 0.03, Hb + 0.012, 0.012, "cable",
                lambda x, y, z: (x, y + Lb / 2 + 0.002 + bend(x, z + 0.006), z), step=0.06, n_round=3, drop=((1, -1),))
    pts = []                                                                           # vivo perimetral del frente
    for (x, z) in _welt_loop(Wb, Hb, rb_, 0):
        X, Y, Z = back_def(np.array([x]), np.array([-Lb / 2 + rb_ - (rb_ + 0.0012) * math.sin(PI / 4)]), np.array([z + Hb / 2]))
        pts.append((float(X[0]), float(Y[0]), float(Z[0])))
    mb.tube([tuple(Mback @ Vector(p)) for p in pts], 0.0032, seg=5, mat="vinyl")
    xs = np.linspace(-Wb / 2 + rb_ * 0.6, Wb / 2 - rb_ * 0.6, 13)                    # costura horizontal con vivo
    X, Y, Z = back_def(xs, np.full_like(xs, -Lb / 2), np.full_like(xs, 0.30))
    mb.tube([tuple(Mback @ Vector((float(a), float(b) + 0.0008, float(c)))) for a, b, c in zip(X, Y, Z)], 0.0028, seg=5, mat="vinyl")
    # solera del respaldo, placa de unión y perilla de altura
    pa = Mback @ Vector((0, Lb / 2 + 0.036 + float(bend(0.0, 0.10)), 0.10))
    pb = Mback @ Vector((0, Lb / 2 + 0.036 + float(bend(0.0, 0.25)), 0.25))
    path = fillet([(0, 0.08, zs - 0.012), (0, pa.y - 0.02, zs - 0.012), (0, pa.y, pa.z - 0.04), (0, pa.y, pa.z), (0, pb.y, pb.z)], 0.05, 4)
    mb.sweep(rr_profile(0.065, 0.009, 0.0035, 2), path, mat="cable", normal=(1, 0, 0))
    mb.box((-0.055, -0.007, 0.0), (0.055, 0.004, 0.13), "cable", bevel=0.003, seg=1,
           m=Mback @ _T(0, Lb / 2 + 0.031 + float(bend(0.0, 0.2)), 0.13))
    for (x, z) in ((-0.04, 0.15), (0.04, 0.15), (-0.04, 0.24), (0.04, 0.24)):
        port.lathe(mb, [(0.0045, 0.0), (0.004, 0.0015)], seg=6, mat="steel",
                   M=Mback @ _T(x, Lb / 2 + 0.035 + float(bend(0.0, z)), z) @ _Rx(-90))
    port.lathe(mb, [(0.016, 0.0), (0.019, 0.004), (0.019, 0.016), (0.015, 0.02)], seg=12, mat="cable",
               M=_T(0, pa.y + 0.004, pa.z - 0.02) @ _Rx(-90))
    # descansabrazos en T
    for s in (-1, 1):
        path = fillet([(s * 0.12, -0.02, zs - 0.006), (s * 0.255, -0.02, zs - 0.006), (s * 0.262, -0.02, 0.63)], 0.05, 5)
        mb.sweep(rr_profile(0.012, 0.055, 0.004, 2), path, mat="cable", normal=(0, 1, 0))
        for yy in (-0.035, -0.005):
            port.lathe(mb, [(0.006, 0.0), (0.0055, 0.002)], seg=6, mat="steel", M=_T(s * 0.15, yy, zs - 0.012) @ _Rx(180))
        mb.box((s * 0.262 - 0.03, -0.12, 0.628), (s * 0.262 + 0.03, 0.07, 0.638), "cable", bevel=0.003, seg=1)
        mb.box((s * 0.262 - 0.035, -0.155, 0.637), (s * 0.262 + 0.035, 0.095, 0.663), "rubber", bevel=0.011, seg=3)
    return mb


# ======================================================================================================== buró hospitalario
def _towel(mb, xb, zb, rbar, seed):
    """Toalla doblada colgada de la barra (sólido delgado subdividido): paño interior y exterior con caída, vuelta sobre la
    barra y ondas que crecen hacia el dobladillo."""
    r = rng(seed)
    tt = 0.004
    rw = rbar + 0.0006 + tt / 2
    path = []
    for k in range(4):                                                      # paño interior (de abajo hacia la barra)
        f = k / 3
        path.append((xb - rw - 0.012 * (1 - f) ** 1.5, zb - 0.19 * (1 - f)))
    for k in range(1, 6):                                                   # vuelta sobre la barra
        a = PI - PI * k / 6
        path.append((xb + rw * math.cos(a), zb + rw * math.sin(a)))
    for k in range(6):                                                      # paño exterior
        f = k / 5
        path.append((xb + rw + 0.009 * f ** 1.5, zb - 0.235 * f))
    n = len(path)
    hw = 0.112
    nv = 13
    ph = float(r.uniform(0, 6.28))
    top, bot = [], []
    for i in range(n):
        x, z = path[i]
        a = path[max(i - 1, 0)]
        b = path[min(i + 1, n - 1)]
        tx, tz = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(tx, tz) or 1.0
        nx, nz = tz / ln, -tx / ln
        hang = max(0.0, zb - z - 0.02) / 0.2
        rt, rb = [], []
        for j in range(nv):
            v = -hw + 2 * hw * j / (nv - 1)
            fold = math.sin(v / 0.034 * PI + ph) + 0.45 * math.sin(v / 0.019 * PI + 2.1 * ph)
            wav = 0.0045 * hang ** 0.8 * fold * (1 if x > xb else -0.5)
            sag = 0.005 * hang * ((v / hw) ** 2) * (1 if x > xb else -1)
            vv = v * (1 + 0.025 * hang)
            px, pz = x + wav + sag, z + 0.003 * hang * (v / hw) ** 2
            rt.append((px + nx * tt / 2, vv, pz + nz * tt / 2))
            rb.append((px - nx * tt / 2, vv, pz - nz * tt / 2))
        top.append(rt)
        bot.append(rb)
    sheet_solid(mb, top, bot, "linen")


def bedside_cabinet(seed=0):
    """Buró de hospital de tablero laminado: costados, fondo, entrepaños y respaldo de 18 mm; frentes sobrepuestos con canto
    de PVC de color y holgura de 3 mm: cajón con jaladera, nicho abierto y puerta con bisagras de libro y jaladera vertical;
    cubierta moldeada de canto redondo con ceja perimetral en tres lados; bastidor de PTR con 4 rodajas de 50 mm (2 con
    freno); toallero de tubo con rosetas y toalla colgada; jarra con tapa y asa y vaso."""
    has_jug = rng(seed).random() < 0.8
    r = rng(seed + 7919)
    mb = MB()
    lam, edge = "plastic", "plastic_blue"
    zc0, zc1 = 0.096, 0.78
    xo, yfc, ybk = 0.21, -0.19, 0.205
    # bastidor y rodajas
    for (x0, y0, x1, y1) in ((-0.19, -0.1825, 0.19, -0.1575), (-0.19, 0.1575, 0.19, 0.1825), (-0.2025, -0.17, -0.1775, 0.17),
                             (0.1775, -0.17, 0.2025, 0.17)):                 # bastidor de PTR 25 x 20 (queda bajo el casco)
        mb.box((x0, y0, 0.076), (x1, y1, 0.096), "steel", bevel=0.003, seg=1)
    for (x, y) in ((-0.17, -0.155), (0.17, -0.155), (-0.17, 0.155), (0.17, 0.155)):
        small_caster(mb, _T(x, y, 0.0), d=0.05, brake=(y < 0), swivel=float(r.uniform(-40, 40)) + (180 if y > 0 else 0))
    # casco de tablero
    for s in (-1, 1):
        mb.box((s * xo - (0.018 if s > 0 else 0), yfc, zc0) if s > 0 else (-xo, yfc, zc0),
               (xo, ybk, zc1) if s > 0 else (-xo + 0.018, ybk, zc1), lam, bevel=0.002, seg=2)
    mb.box((-xo + 0.018, yfc, zc0), (xo - 0.018, ybk - 0.01, zc0 + 0.018), lam, bevel=0.0)                 # fondo (tras la puerta)
    mb.box((-xo + 0.018, ybk - 0.01, zc0 + 0.018), (xo - 0.018, ybk, zc1 - 0.018), lam, bevel=0.001, seg=1)  # respaldo
    mb.box((-xo + 0.018, yfc, zc1 - 0.018), (xo - 0.018, ybk, zc1), lam, bevel=0.0)                         # techo (bajo la cubierta)
    for z in (0.452, 0.622):
        mb.box((-xo + 0.018, yfc + 0.002, z), (xo - 0.018, ybk - 0.01, z + 0.018), lam, bevel=0.0015, seg=1)
        mb.box((-xo + 0.018, yfc - 0.0012, z + 0.0005), (xo - 0.018, yfc + 0.004, z + 0.0175), edge, bevel=0.0006, seg=1)
    # frentes con canto de PVC
    yF = yfc - 0.001
    for (za, zb) in ((0.643, 0.777), (0.10, 0.449)):
        mb.box((-xo + 0.002, yF - 0.018, za), (xo - 0.002, yF, zb), lam, bevel=0.0)          # el canto de PVC cubre las aristas
        edge_band(mb, [(-xo + 0.002, za), (xo - 0.002, za), (xo - 0.002, zb), (-xo + 0.002, zb)], "y", yF - 0.018, 0.018, edge,
                  bulge=0.0022, over=0.0005, n=3)
    dpull(mb, _T(0, yF - 0.018, 0.712), cc=0.128, proj=0.028, r=0.0045)
    dpull(mb, _T(xo - 0.045, yF - 0.018, 0.36) @ _Ry(90), cc=0.096, proj=0.028, r=0.0045)
    for zh in (0.15, 0.40):                                                  # bisagras de libro
        for (z0, z1) in ((zh - 0.025, zh - 0.0005), (zh + 0.0005, zh + 0.025)):
            port.lathe(mb, [(0.0042, z0), (0.0045, z0 + 0.001), (0.0045, z1 - 0.001), (0.0042, z1)], seg=8,
                       mat="steel", M=_T(-xo - 0.0005, yF - 0.009, 0.0))
        mb.box((-xo - 0.0005 - 0.0012, yF - 0.004, zh - 0.024), (-xo + 0.0004, yF + 0.012, zh + 0.024), "steel", bevel=0.0004, seg=1)
    # cubierta moldeada con ceja
    zt0, zt1 = 0.78, 0.80
    tp = fillet2d([(-0.226, zt0), (0.226, zt0), (0.226, zt1), (-0.226, zt1)], [0.006, 0.006, 0.008, 0.009], 3)
    loft_x(mb, tp, -0.236, 0.236, "sign_white", re=0.012, ne=2)
    rim = fillet([(-0.222, -0.17, zt1 - 0.012), (-0.222, -0.13, zt1 - 0.001), (-0.222, 0.212, zt1 - 0.001), (0.222, 0.212, zt1 - 0.001),
                  (0.222, -0.13, zt1 - 0.001), (0.222, -0.17, zt1 - 0.012)], 0.03, 4)
    mb.sweep([(x, y + 0.0) for (x, y) in rr_profile(0.012, 0.024, 0.0055, 2)], [(x, y, z + 0.011) for (x, y, z) in rim], mat="sign_white",
             normal=(0, 0, 1))
    # toallero y toalla
    xb, zb = xo + 0.028, 0.70
    mb.tube(fillet([(xo + 0.001, -0.13, zb), (xb, -0.13, zb), (xb, 0.13, zb), (xo + 0.001, 0.13, zb)], 0.02, 4), 0.0065, seg=8, mat="steel")
    for y in (-0.13, 0.13):
        port.lathe(mb, [(0.012, 0.0), (0.012, 0.003), (0.008, 0.007)], seg=10, mat="steel", M=_T(xo, y, zb) @ _Ry(90))
    if r.random() < 0.65:
        _towel(mb, xb, zb, 0.0065, int(r.integers(1e6)))
    # jarra y vaso
    if has_jug:
        Mj = _T(0.1, 0.05, zt1) @ _Rz(float(r.uniform(-30, 30)))
        port.lathe(mb, [(0.04, 0.0), (0.0445, 0.004), (0.047, 0.03), (0.046, 0.15), (0.041, 0.188), (0.038, 0.196)], seg=16, mat="plastic",
                   M=Mj)
        port.lathe(mb, [(0.0405, 0.195), (0.041, 0.201), (0.031, 0.211), (0.012, 0.215), (0.011, 0.224), (0.004, 0.23)], seg=14,
                   mat="plastic_blue", M=Mj)
        mb.tube([tuple(Mj @ Vector(p)) for p in fillet([(0.04, 0.0, 0.165), (0.072, 0.0, 0.158), (0.07, 0.0, 0.06), (0.042, 0.0, 0.05)],
                                                      0.02, 3)], 0.0065, seg=8, mat="plastic")
        port.loft(mb, [(0.03, 0.03, 0.01, 0.19), (0.05, 0.026, 0.008, 0.193), (0.058, 0.02, 0.006, 0.196)], seg=8, mat="plastic",
                  M=Mj @ _Rz(180), ex=2.2)
        Mg = _T(-0.08, 0.02, zt1)
        port.lathe(mb, [(0.029, 0.0), (0.0335, 0.092), (0.0326, 0.0935), (0.0316, 0.092), (0.0275, 0.004)], seg=16, mat="glass", M=Mg)
    return mb


# ======================================================================================================== piezas de muro
_WALL = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))   # local (x, y, z) de hoja -> muro (x, -z, y)


def _pin(mb, x, y, z, mat):
    """Chincheta de mapa: aguja, base y cabeza torneada; eje -Y desde la superficie y."""
    port.lathe(mb, [(0.0, -0.005), (0.0006, -0.005), (0.0006, 0.0007), (0.0042, 0.0007), (0.0046, 0.002), (0.003, 0.004), (0.003, 0.0076),
                    (0.0041, 0.0092), (0.004, 0.0116), (0.0024, 0.0126), (0.0, 0.0128)], seg=10, mat=mat, M=_T(x, y, z) @ _Rx(90))


def notice_board(w=0.9, h=0.6, seed=0, posters=()):
    """Tablero de corcho en marco de aluminio extruido con esquineros de plástico (origen: cara del muro, centro inferior;
    sale hacia -Y): hojas, tarjetas y avisos como sólidos delgados despegados del corcho con el borde inferior enrollado,
    clavados con chinchetas; encabezados en relieve. posters: textos de carteles de salud (opcional)."""
    r = rng(seed)
    mb = MB()
    yc = -0.016
    rbox(mb, (-w / 2 + 0.004, -0.0045, 0.004), (w / 2 - 0.004, -0.0018, h - 0.004), "wood_dark", r=0.0008)
    rbox(mb, (-w / 2 + 0.006, yc, 0.006), (w / 2 - 0.006, -0.0045, h - 0.006), "wood_varnish", r=0.0015)
    a, b = w / 2 - 0.011, 0.011
    path = [(x, -0.024, z) for (x, z) in [(-a, b), (a, b), (a, h - b), (-a, h - b)]]
    prof = fillet2d([(-0.011, 0.024), (-0.011, 0.0035), (-0.0085, 0.0), (0.0085, 0.0), (0.011, 0.002), (0.011, 0.0085), (0.004, 0.0085),
                     (0.004, 0.024)], [0.0, 0.002, 0.003, 0.003, 0.0015, 0.0008, 0.0008, 0.0], 3)
    mb.sweep(prof, path, mat="aluminium", closed_path=True, normal=(0, 1, 0))
    L = [(0.0, 0.0), (0.043, 0.0), (0.043, 0.027), (0.027, 0.027), (0.027, 0.043), (0.0, 0.043)]
    Lf = fillet2d(L, [0.013, 0.004, 0.004, 0.003, 0.004, 0.004], 4)
    for (sx, sz, z0) in ((1, 1, 0.0), (-1, 1, 0.0), (1, -1, h), (-1, -1, h)):
        x0 = -w / 2 - 0.001 if sx > 0 else w / 2 + 0.001
        prof_c = [(x0 + sx * u, z0 - (0.001 if sz > 0 else -0.001) + sz * v) for (u, v) in Lf]
        loft_x(mb, prof_c, -0.0268, -0.0032, "plastic", re=0.0016, ne=2, M=LY)
    # hojas clavadas
    sizes = [(0.216, 0.279), (0.279, 0.216), (0.148, 0.21), (0.127, 0.076), (0.21, 0.148), (0.216, 0.279), (0.10, 0.15)]
    heads = ["NOTICE", "SCHEDULE", "STAFF MEETING", "HAND HYGIENE", "SHIFTS", "THANK YOU", "VACCINES", "REMINDER"]
    x_in, z_in = w / 2 - 0.035, 0.035
    n = int(r.integers(4, 8)) if w < 1.0 else int(r.integers(6, 10))
    placed = []                                              # (cx, cz, w, h, ang, poster, layer)
    for k in range(n + len(posters)):
        poster = k >= n
        pw_, ph_ = (0.28, 0.38) if poster else sizes[int(r.integers(0, len(sizes)))]
        if pw_ > 2 * x_in - 0.02 or ph_ > h - 2 * z_in - 0.02:
            continue
        for _ in range(30):
            cx = float(r.uniform(-x_in + pw_ / 2, x_in - pw_ / 2))
            cz = float(r.uniform(z_in + ph_ / 2, h - z_in - ph_ / 2))
            over = sum(1 for q in placed if abs(q[0] - cx) < (pw_ + q[2]) / 2 - 0.03 and abs(q[1] - cz) < (ph_ + q[3]) / 2 - 0.03)
            if over <= (1 if not poster else 0):
                break
        ang = float(r.uniform(-3.5, 3.5)) if not poster else float(r.uniform(-1, 1))
        layer = 1 + max([q[6] for q in placed if abs(q[0] - cx) < (pw_ + q[2]) / 2 + 0.02 and abs(q[1] - cz) < (ph_ + q[3]) / 2 + 0.02] + [0])
        placed.append((cx, cz, pw_, ph_, ang, poster, layer, k))
    nhead = 0
    for (cx, cz, pw_, ph_, ang, poster, layer, k) in placed:
        covered = any(q[6] > layer and abs(q[0] - cx) < (pw_ + q[2]) / 2 + 0.02 and abs(q[1] - cz) < (ph_ + q[3]) / 2 + 0.02 for q in placed)
        printed = (not covered) and (poster or (pw_ >= 0.14 and nhead < 3 and r.random() < 0.85))
        t = 0.0013 if printed else 0.0007                         # avisos impresos: hoja enmicada (más gruesa)
        yb = yc - 0.0004 - 0.0026 * (layer - 1) - 0.0012
        Mp = _T(cx, yb, cz) @ _Ry(ang) @ _WALL
        paper_sheet(mb, Mp, pw_, ph_, t=t, curl=(0.0 if covered else float(r.uniform(0.003, 0.009))),
                    wave=(0.0 if (covered or printed) else 0.0008),
                    seed=int(r.integers(1e6)), nu=5, nv=7, mat=("sign_white" if poster else ("paper" if r.random() < 0.7 else "paint_yellow")),
                    curl_dir=-1)
        top = _T(cx, yb, cz) @ _Ry(ang)
        pins = [(0.0, ph_ / 2 - 0.014)] if (pw_ < 0.2 or r.random() < 0.5) else [(-pw_ / 2 + 0.018, ph_ / 2 - 0.014),
                                                                                 (pw_ / 2 - 0.018, ph_ / 2 - 0.014)]
        for (px, pz) in pins:
            v = top @ Vector((px, -t, pz))
            hit = any(q[6] > layer and abs(q[0] - v.x) < q[2] / 2 + 0.006 and abs(q[1] - v.z) < q[3] / 2 + 0.006 for q in placed)
            if not hit:
                _pin(mb, v.x, v.y, v.z, ("sign_red", "sign_blue", "sign_green", "paint_yellow", "sign_white")[int(r.integers(0, 5))])
        if covered:
            continue
        if poster:
            s_ = posters[k - n]
            sz = min(0.028, (pw_ - 0.04) / max(len(s_), 1) * 1.5)
            _text(mb, s_, sz, 0.0015, "sign_blue", top @ _T(0, -t, ph_ / 2 - 0.06) @ _Rx(90), res=3)
            mb.box((-pw_ * 0.36, -t - 0.0015, -ph_ * 0.32), (pw_ * 0.36, -t, ph_ * 0.2), "plastic_blue", bevel=0.0005, seg=1, m=top)
        elif printed:
            s_ = heads[int(r.integers(0, len(heads)))]
            sz = min(0.017, (pw_ - 0.03) / max(len(s_), 1) * 1.45)
            _text(mb, s_, sz, 0.0014, "sign_blue" if nhead % 2 == 0 else "cable", top @ _T(0, -t, ph_ / 2 - 0.042) @ _Rx(90),
                  res=2)
            nhead += 1
            for q in range(int((ph_ - 0.09) / 0.022)):                      # renglones impresos (relieve de tinta)
                zq = ph_ / 2 - 0.07 - q * 0.022
                if zq < -ph_ / 2 + 0.36 * ph_:
                    break
                lw = (pw_ - 0.05) * (0.55 + 0.45 * float(r.random()))
                mb.box((-pw_ / 2 + 0.025, -t - 0.0013, zq - 0.0015), (-pw_ / 2 + 0.025 + lw, -t, zq + 0.0015), m=top, mat=
                       "cable", bevel=0.0)
    return mb


def clock(seed=0):
    """Reloj de pared Ø 0,31 (origen: cara del muro, centro; sale hacia -Y): caja de plástico con aro redondeado y tapa
    trasera, carátula, 60 marcas de minuto y 12 de hora en relieve, números arábigos en relieve, manecillas de hora y minuto
    perfiladas, segundero rojo con contrapeso, tapón central y cristal abombado."""
    r = rng(seed)
    mb = MB()
    M = _Rx(90)
    # caja: la tapa trasera (contra el muro) y el piso interior (bajo la carátula) se cierran con n-ágonos
    port.lathe(mb, [(0.142, 0.0), (0.15, 0.003), (0.1545, 0.01), (0.1555, 0.03), (0.1535, 0.0395), (0.148, 0.0445),
                    (0.1415, 0.0452), (0.1375, 0.0425), (0.1355, 0.031), (0.1345, 0.02)], seg=40, mat="plastic", M=M)
    port.lathe(mb, [(0.1355, 0.0195), (0.1355, 0.027)], seg=32, mat="sign_white", M=M)
    zf = 0.027
    for k in range(60):                                                  # marcas sin cara de apoyo (embebida en la carátula)
        hour = k % 5 == 0
        Mt = M @ _Rz(-6 * k) @ _T(0, 0, zf)
        rr0, rr1, hw = (0.112, 0.128, 0.0022) if hour else (0.122, 0.128, 0.0007)
        v = [mb.bm.verts.new(Mt @ Vector(p)) for p in ((-hw, rr0, -0.0004), (hw, rr0, -0.0004), (hw, rr1, -0.0004), (-hw, rr1, -0.0004),
                                                        (-hw, rr0, 0.0014), (hw, rr0, 0.0014), (hw, rr1, 0.0014), (-hw, rr1, 0.0014))]
        for q in ((4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            mb.face([v[i] for i in q], "cable")
    for k in range(1, 13):
        a = math.radians(90 - 30 * k)
        x, y = 0.094 * math.cos(a), 0.094 * math.sin(a)
        _text(mb, str(k), 0.019, 0.0017, "cable", M @ _T(x, y - 0.0068, zf - 0.0003), res=2)
    _text(mb, "QUARTZ", 0.0065, 0.0016, "cable", M @ _T(0, -0.05, zf - 0.0002), res=1)
    hh = float(r.uniform(0, 12))
    mm = float(r.uniform(0, 60))
    ss = float(r.uniform(0, 60))

    def hand(L, tail, wb, wt, z, mat, ang):
        pts = [(-wb * 0.6, -tail), (wb * 0.6, -tail), (wb / 2, 0.0), (wt / 2, L * 0.86), (0.0, L), (-wt / 2, L * 0.86), (-wb / 2, 0.0)]
        mb.plate(pts, 0.0009, mat, m=M @ _Rz(-ang) @ _T(0, 0, z))
    hand(0.068, 0.016, 0.0085, 0.0045, zf + 0.004, "cable", (hh + mm / 60) * 30)
    hand(0.108, 0.02, 0.0065, 0.003, zf + 0.0062, "cable", (mm + ss / 60) * 6)
    Ms = M @ _Rz(-ss * 6) @ _T(0, 0, zf + 0.0085)
    mb.plate([(-0.0007, -0.028), (0.0007, -0.028), (0.0006, 0.118), (-0.0006, 0.118)], 0.0006, "sign_red", m=Ms)
    port.lathe(mb, [(0.0042, 0.0), (0.0042, 0.0006)], seg=10, mat="sign_red", M=Ms @ _T(0, -0.024, 0))
    port.lathe(mb, [(0.0055, zf), (0.0055, zf + 0.0085), (0.0035, zf + 0.0105), (0.0028, zf + 0.0112), (0.0, zf + 0.0118)], seg=10,
               mat="sign_red", M=M)
    port.lathe(mb, [(0.0068, zf + 0.0048), (0.0068, zf + 0.0062)], seg=12, mat="cable", M=M)
    # cristal abombado: casquete de 1,5 mm asentado bajo el aro (perfil cerrado: cara interior, canto y cara exterior)
    outer = [(0.139 * (1 - k / 5), 0.0405 + 0.0072 * (1 - (1 - k / 5) ** 2)) for k in range(6)]
    inner = [(rr_, z - 0.0015) for (rr_, z) in outer]
    port.lathe(mb, inner[::-1] + outer, seg=28, mat="glass", M=M, caps=False)
    return mb


# ======================================================================================================== planta en maceta
def _leaf(mb, base, az, el0, droop, L, W, t0=0.0016, fold=0.22, twist=0.0, nu=11, nv=7, mat="vegetation", shape=0.8, tip=0.004):
    """Hoja lanceolada con grosor: lámina doblada en V a lo largo de la nervadura (arriba surco, abajo costilla saliente),
    arqueada (elevación que cae `droop` grados hacia la punta), afilada en punta y con cuña en la base."""
    P = Vector(base)
    pts = [P.copy()]
    ds = L / (nu - 1)
    for i in range(nu - 1):
        u = (i + 0.5) / (nu - 1)
        e = math.radians(el0 - droop * u ** 1.4)
        d = Vector((math.cos(e) * math.cos(az), math.cos(e) * math.sin(az), math.sin(e)))
        P = P + d * ds
        pts.append(P.copy())
    top, bot = [], []
    for i in range(nu):
        u = i / (nu - 1)
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, nu - 1)]
        T = (b - a).normalized()
        S = T.cross(Vector((0, 0, 1)))
        if S.length < 1e-6:
            S = Vector((1, 0, 0))
        S.normalize()
        tw = math.radians(twist * u)
        Nn = S.cross(T).normalized()
        S, Nn = S * math.cos(tw) + Nn * math.sin(tw), Nn * math.cos(tw) - S * math.sin(tw)
        wu = W / 2 * max(math.sin(PI * min(u, 0.999) ** shape), 0.0) ** 0.9 * (1 - 0.35 * u ** 2)
        wu = max(wu, 0.0035 if u < 0.05 else tip * 0.5)
        rt, rb = [], []
        for j in range(nv):
            v = -1 + 2 * j / (nv - 1)
            wave = 0.0025 * v * v * math.sin(u * 17.0 + v * 2.0) * math.sin(PI * u)
            off = S * (v * wu) + Nn * (fold * wu * abs(v) - 0.25 * fold * wu * v * v + wave)
            th = t0 * (0.45 + 0.55 * (1 - abs(v)))
            rib = 0.0022 * (1 - u) ** 0.7 * max(0.0, 1 - abs(v) * 3.2)
            c = pts[i] + off
            rt.append(tuple(c + Nn * (th / 2)))
            rb.append(tuple(c - Nn * (th / 2 + rib)))
        top.append(rt)
        bot.append(rb)
    sheet_solid(mb, top, bot, mat)
    return pts


def potted_plant(seed=0, h=0.9):
    """Cuna de Moisés (Spathiphyllum) en maceta de cerámica vidriada: maceta con pie, cuerpo cónico y borde enrollado, plato
    de plástico con ceja, tierra con montículo y piedritas, pecíolos que salen de la tierra y hojas lanceoladas con grosor,
    nervadura, doblez en V y arco por su peso; una o dos espatas blancas con espádice."""
    r = rng(seed)
    mb = MB()
    sc = 0.76 * h / 0.9
    # plato, maceta y tierra: los fondos (sobre el piso, dentro del plato y bajo la tierra) se cierran con n-ágonos, sin abanico
    port.lathe(mb, [(0.172, 0.0), (0.184, 0.004), (0.193, 0.021), (0.196, 0.026), (0.1915, 0.0275), (0.186, 0.014), (0.177, 0.0065)],
               seg=24, mat="plastic")
    port.lathe(mb, [(0.114, 0.0065), (0.123, 0.012), (0.121, 0.024), (0.126, 0.03), (0.168, 0.288), (0.172, 0.297), (0.186, 0.302),
                    (0.192, 0.312), (0.192, 0.333), (0.187, 0.342), (0.178, 0.345), (0.17, 0.343), (0.166, 0.335), (0.162, 0.30)], seg=36,
               mat="enamel")
    port.lathe(mb, [(0.1645, 0.302), (0.1645, 0.309), (0.14, 0.313), (0.09, 0.318), (0.04, 0.322), (0.0, 0.323)], seg=24, mat="wood_dark")
    for k in range(int(r.integers(10, 16))):                                    # piedritas (se dibujan 6)
        a = float(r.uniform(0, 2 * PI))
        rr_ = float(r.uniform(0.03, 0.15))
        s_ = float(r.uniform(0.005, 0.011))
        z = 0.322 - 0.012 * (rr_ / 0.165) ** 2
        rz, ry = float(r.uniform(0, 60)), float(r.uniform(-20, 20))
        if k >= 6:
            continue
        port.lathe(mb, [(0.0, -s_ * 0.5), (s_ * 0.8, -s_ * 0.3), (s_ * 0.85, s_ * 0.3), (0.0, s_ * 0.5)], seg=5, mat="concrete",
                   M=_T(rr_ * math.cos(a), rr_ * math.sin(a), z) @ _Rz(rz) @ _Ry(ry))
    nl = int(r.integers(13, 18))
    for k in range(nl):
        az = 2 * PI * k / nl + float(r.uniform(-0.25, 0.25))
        rb = float(r.uniform(0.0, 0.04))
        b0 = Vector((rb * math.cos(az), rb * math.sin(az), 0.312))
        inner = k % 3 == 0
        Ls = (float(r.uniform(0.17, 0.26)) if not inner else float(r.uniform(0.26, 0.34))) * sc
        es = math.radians(float(r.uniform(50, 66)) if not inner else float(r.uniform(70, 82)))
        d = Vector((math.cos(es) * math.cos(az), math.cos(es) * math.sin(az), math.sin(es)))
        p1 = b0 + d * Ls + Vector((0, 0, -0.03 * Ls))
        mid = b0 + d * (Ls * 0.5) + Vector((0, 0, 0.012))
        stem = smooth_path([tuple(b0 - Vector((0, 0, 0.015))), tuple(mid), tuple(p1)], 2)
        mb.tube(stem, 0.0032, seg=4, mat="vegetation", radii=[0.0042 - 0.0016 * i / (len(stem) - 1) for i in range(len(stem))])
        el0 = math.degrees(es) - float(r.uniform(12, 28))
        _leaf(mb, p1 - d * 0.004, az + float(r.uniform(-0.15, 0.15)), el0, float(r.uniform(65, 100)) if not inner else float(r.uniform(45, 70)),
              float(r.uniform(0.27, 0.34)) * sc, float(r.uniform(0.085, 0.11)) * sc, fold=0.3, twist=float(r.uniform(-25, 25)), nu=8, nv=5)
    for k in range(int(r.integers(1, 3))):                                      # espatas
        az = float(r.uniform(0, 2 * PI))
        b0 = Vector((0.02 * math.cos(az), 0.02 * math.sin(az), 0.312))
        top_ = b0 + Vector((0.08 * math.cos(az), 0.08 * math.sin(az), 0.52 * sc))
        mb.tube(smooth_path([tuple(b0 - Vector((0, 0, 0.015))), tuple(b0 + Vector((0, 0, 0.25 * sc))), tuple(top_)], 3), 0.0028, seg=5,
                mat="vegetation")
        _leaf(mb, top_ - Vector((0, 0, 0.005)), az + 0.3, 82, 40, 0.11 * sc, 0.06 * sc, t0=0.0012, fold=0.75, nu=6, nv=5, mat="sign_white",
              shape=0.6, twist=20)
        sp = top_ + Vector((0.01 * math.cos(az + 0.3 + PI), 0.01 * math.sin(az + 0.3 + PI), 0.0))
        port.lathe(mb, [(0.0, 0.0), (0.0058, 0.008), (0.0055, 0.035), (0.0, 0.05)], seg=6, mat="paint_yellow",
                   M=_T(sp.x, sp.y, sp.z) @ _Rz(math.degrees(az)) @ _Ry(-12))
    return mb
