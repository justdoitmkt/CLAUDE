"""kit/port.py — piezas portuarias detalladas (muelle MUE_1): primitivas de perfil (torneado, loft, ángulos estructurales,
pernos, eslabones, poleas) y piezas completas: bita de cabeza en T, llanta de defensa con dibujo y cadena, defensa de madera
con flejes, escalera marina, poste de luz octagonal con luminaria tipo cobra, grúa de pedestal con pluma de celosía, tambo,
contenedor de 20' con herrajes. Todas devuelven MB o escriben en el MB dado; medidas en metros, z arriba.
Nada de cajas sueltas: cada pieza lleva sus uniones (placas, pernos, soldaduras, bridas) y su desgaste geométrico."""
import math

from mathutils import Matrix, Vector

from kit.common import MB, rng

SQ = 0.7071067811865476


def _T(x, y, z):
    return Matrix.Translation((x, y, z))


def _R(axis, deg):
    return Matrix.Rotation(math.radians(deg), 4, axis)


# ======================================================================================================== primitivas
def frame_on(p0, p1, up=(0, 0, 1)):
    """Matriz con X a lo largo de p0→p1 y Z lo más cerca posible de `up`; origen en p0. Devuelve (M, largo)."""
    p0, p1 = Vector(p0), Vector(p1)
    X = (p1 - p0).normalized()
    U = Vector(up)
    if abs(X.dot(U)) > 0.99:
        U = Vector((0, 1, 0)) if abs(X.y) < 0.9 else Vector((1, 0, 0))
    Z = (U - X * X.dot(U)).normalized()
    Y = Z.cross(X)
    return Matrix(((X.x, Y.x, Z.x, p0.x), (X.y, Y.y, Z.y, p0.y), (X.z, Y.z, Z.z, p0.z), (0, 0, 0, 1))), (p1 - p0).length


def member(mb, p0, p1, rects, mat, up=(0, 0, 1)):
    """Barra prismática de p0 a p1; sección = unión de rectángulos [(y0, y1, z0, z1)] en el plano local YZ."""
    M, L = frame_on(p0, p1, up)
    for (y0, y1, z0, z1) in rects:
        mb.box((0.0, y0, z0), (L, y1, z1), mat, m=M)


def angle_bar(mb, p0, p1, leg=0.08, t=0.008, mat="metal_paint", up=(0, 0, 1), flip=False):
    """Ángulo L (alas iguales) de p0 a p1: el talón sobre el eje, alas hacia +Y y +Z locales (o -Y/+Z con flip)."""
    s = -1.0 if flip else 1.0
    y0, y1 = sorted((0.0, s * leg))
    ty0, ty1 = sorted((0.0, s * t))
    member(mb, p0, p1, [(y0, y1, 0.0, t), (ty0, ty1, t, leg)], mat, up)


def i_sec(h, b, tw=0.012, tf=0.016):
    return [(-tw / 2, tw / 2, -h / 2 + tf, h / 2 - tf), (-b / 2, b / 2, h / 2 - tf, h / 2), (-b / 2, b / 2, -h / 2, -h / 2 + tf)]


def z_sec(h=0.2, b=0.07, t=0.0025):
    """Larguero Z (alas opuestas)."""
    return [(-t / 2, t / 2, -h / 2, h / 2), (-t / 2, b, h / 2 - t, h / 2), (-b, t / 2, -h / 2, -h / 2 + t)]


def lathe(mb, prof, seg=16, mat="metal_paint", M=None, caps=True, phase=0.0):
    """Sólido de revolución alrededor de Z local. prof: [(r, z)] de abajo hacia arriba."""
    rings = []
    for (rr, z) in prof:
        ring = []
        for k in range(seg):
            a = 2 * math.pi * k / seg + phase
            p = Vector((rr * math.cos(a), rr * math.sin(a), z))
            ring.append(mb.bm.verts.new(M @ p if M is not None else p))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([rings[i][k], rings[i][kk], rings[i + 1][kk], rings[i + 1][k]], mat)
    if caps:
        if prof[0][0] > 1e-6:
            mb.face(list(reversed(rings[0])), mat)
        if prof[-1][0] > 1e-6:
            mb.face(rings[-1], mat)


def loft(mb, stations, seg=12, mat="metal_paint", M=None, ex=2.6):
    """Cuerpo a lo largo de X local por secciones superelípticas [(x, ancho, alto, z_centro)] (ex = 2 elipse, >2 más cuadrada)."""
    rings = []
    for (x, w, h, zc) in stations:
        ring = []
        for k in range(seg):
            a = 2 * math.pi * k / seg
            c, s = math.cos(a), math.sin(a)
            yy = (w / 2) * math.copysign(abs(c) ** (2 / ex), c)
            zz = zc + (h / 2) * math.copysign(abs(s) ** (2 / ex), s)
            p = Vector((x, yy, zz))
            ring.append(mb.bm.verts.new(M @ p if M is not None else p))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([rings[i][k], rings[i][kk], rings[i + 1][kk], rings[i + 1][k]], mat)
    mb.face(list(reversed(rings[0])), mat)
    mb.face(rings[-1], mat)


def bolt(mb, M, d=0.024, stud=0.02, mat="metal_rust"):
    """Tuerca hexagonal con arandela y punta de espárrago sobre el plano z = 0 local (eje +Z)."""
    lathe(mb, [(d * 1.0, 0.0), (d * 1.0, 0.004)], seg=10, mat=mat, M=M)
    lathe(mb, [(d * 0.82, 0.004), (d * 0.82, 0.004 + d * 0.8)], seg=6, mat=mat, M=M, phase=math.pi / 6)
    lathe(mb, [(d * 0.45, 0.004 + d * 0.8), (d * 0.45, 0.004 + d * 0.8 + stud)], seg=6, mat=mat, M=M)


def bolt_ring(mb, M, R, n, d=0.024, mat="metal_rust", phase=0.0):
    for k in range(n):
        a = 2 * math.pi * k / n + phase
        bolt(mb, M @ _T(R * math.cos(a), R * math.sin(a), 0.0), d=d, mat=mat)


def plate_poly(mb, pts, t, mat, M):
    """Placa: polígono (x, y) extruido t en +Z local."""
    mb.plate(pts, t, mat, m=M)


def gusset(mb, M, a, b, t=0.012, mat="metal_paint", chamfer=0.03):
    """Cartela triangular en el plano XZ local (catetos a en X y b en Z), espesor t centrado en Y."""
    pts = [(0.0, 0.0), (a, 0.0), (a, chamfer), (chamfer, b), (0.0, b)]
    mb.plate(pts, t, mat, m=M @ _T(0, t / 2, 0) @ _R("X", 90))


def chain(mb, pts, link=0.075, wire=0.009, mat="metal_rust", r=None):
    """Cadena de eslabones alternados a lo largo de una polilínea (cada eslabón: estadio barrido por un tubo de 4 lados)."""
    P = [Vector(p) for p in pts]
    pitch = link * 0.82
    k = 0
    for i in range(len(P) - 1):
        a, b = P[i], P[i + 1]
        L = (b - a).length
        n = max(int(L / pitch), 1)
        d = (b - a).normalized()
        for j in range(n):
            c = a + d * (pitch * (j + 0.5) * L / (n * pitch))
            M, _ = frame_on(c - d * link / 2, c + d * link / 2, up=(0, 0, 1) if abs(d.z) < 0.9 else (1, 0, 0))
            M = M @ _R("X", 90 * (k % 2) + (float(r.uniform(-12, 12)) if r is not None else 0.0))
            hw = link * 0.32
            path = []
            for q in range(7):     # medio estadio derecho
                ang = -math.pi / 2 + math.pi * q / 6
                path.append(M @ Vector((link - hw + hw * math.cos(ang), hw * math.sin(ang), 0)))
            for q in range(7):     # medio estadio izquierdo
                ang = math.pi / 2 + math.pi * q / 6
                path.append(M @ Vector((hw + hw * math.cos(ang), hw * math.sin(ang), 0)))
            path.append(path[0])
            mb.tube(path, wire, seg=4, mat=mat, caps=False)
            k += 1


def sheave(mb, M, R=0.25, w=0.08, mat="metal_paint"):
    """Polea con garganta (eje Y local)."""
    Mr = M @ _R("X", 90)
    prof = [(0.05, -w / 2), (R, -w / 2), (R, -w / 2 + 0.012), (R - 0.04, -0.008), (R - 0.04, 0.008), (R, w / 2 - 0.012),
            (R, w / 2), (0.05, w / 2)]
    lathe(mb, prof, seg=24, mat=mat, M=Mr)
    lathe(mb, [(0.045, -w / 2 - 0.03), (0.045, w / 2 + 0.03)], seg=12, mat="metal_rust", M=Mr)


def rope(mb, pts, r=0.011, mat="cable"):
    mb.tube(pts, r, seg=6, mat=mat)


def handrail(mb, p0, p1, h=1.1, post_step=1.5, mat="metal_paint", r=None, knee=True):
    """Barandal de tubo (pasamanos Ø48, rodillera Ø33, postes Ø48 con placa) recto de p0 a p1 sobre su piso."""
    p0, p1 = Vector(p0), Vector(p1)
    L = (p1 - p0).length
    n = max(int(math.ceil(L / post_step)), 1)
    up = Vector((0, 0, 1))
    for k in range(n + 1):
        c = p0.lerp(p1, k / n)
        lean = Vector((float(r.uniform(-0.01, 0.01)), float(r.uniform(-0.01, 0.01)), 0)) if r is not None else Vector()
        mb.tube([c, c + up * h + lean], 0.024, seg=8, mat=mat)
        mb.box((c.x - 0.07, c.y - 0.07, c.z), (c.x + 0.07, c.y + 0.07, c.z + 0.012), mat)
    mb.tube([p0 + up * h, p1 + up * h], 0.024, seg=8, mat=mat)
    if knee:
        mb.tube([p0 + up * h * 0.5, p1 + up * h * 0.5], 0.017, seg=6, mat=mat)


# ======================================================================================================== piezas
def bollard(seed=0):
    """Bita de amarre de fundición (cabeza en T, ~0,55 m): placa base con chaflán y 4 anclas, cuerpo torneado con cintura,
    cabeza con cuernos y nervio; pintura negra perdida (material metal_paint con óxido en el horneado/motor)."""
    r = rng(seed)
    mb = MB()
    mb.plate([(-0.34, -0.3), (0.34, -0.3), (0.38, -0.26), (0.38, 0.26), (0.34, 0.3), (-0.34, 0.3), (-0.38, 0.26), (-0.38, -0.26)],
             0.05, "metal_paint")
    for (x, y) in ((-0.29, -0.21), (0.29, -0.21), (-0.29, 0.21), (0.29, 0.21)):
        bolt(mb, _T(x, y, 0.05), d=0.03)
    lathe(mb, [(0.25, 0.05), (0.235, 0.075), (0.2, 0.1), (0.165, 0.16), (0.15, 0.26), (0.15, 0.34), (0.16, 0.38),
               (0.165, 0.4)], seg=28, mat="metal_paint")
    # cabeza en T: barra horizontal con extremos redondeados, más el disco superior con borde
    for sg in (-1, 1):
        lathe(mb, [(0.085, 0.0), (0.09, 0.2), (0.095, 0.26), (0.085, 0.29), (0.05, 0.305), (0.0, 0.31)], seg=16,
              mat="metal_paint", M=_T(0, 0, 0.47) @ _R("Y", 90 * sg))
    lathe(mb, [(0.165, 0.4), (0.18, 0.47), (0.19, 0.53), (0.175, 0.56), (0.0, 0.57)], seg=28, mat="metal_paint")
    mb.meta = dict(top=0.57)
    del r
    return mb


def fender_tyre(seed=0, R=0.42, t=0.13, seg=56, sseg=16):
    """Llanta de defensa con dibujo de banda de rodadura (bloques alternados), ceja y costado; eje en Y local."""
    r = rng(seed)
    mb = MB()
    rings = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        ring = []
        for j in range(sseg):
            b = 2 * math.pi * j / sseg
            rr = R + t * math.cos(b)
            # banda de rodadura: bloques alternos en el tercio exterior
            if math.cos(b) > 0.45:                      # banda: ranuras transversales cada 4 segmentos, alternadas por lado
                rr -= 0.01 if (i + (2 if math.sin(b) > 0 else 0)) % 4 == 0 else 0.0
            ring.append(mb.bm.verts.new((rr * math.cos(a), t * 0.85 * math.sin(b), rr * math.sin(a))))
        rings.append(ring)
    for i in range(seg):
        for j in range(sseg):
            A, B = rings[i], rings[(i + 1) % seg]
            mb.face([A[j], A[(j + 1) % sseg], B[(j + 1) % sseg], B[j]], "cable")
    del r
    return mb


def timber_fender(height, seed=0):
    """Defensa vertical de madera dura 0,30 x 0,30 con aristas gastadas, flejes de acero y pernos pasantes."""
    r = rng(seed)
    mb = MB()
    w = 0.3
    mb.box((-w / 2, 0.0, 0.0), (w / 2, w, height), "wood_dark", bevel=0.025, seg=2)
    for z in (0.35, height * 0.5, height - 0.4):
        mb.box((-w / 2 - 0.006, -0.004, z), (w / 2 + 0.006, w + 0.006, z + 0.06), "metal_rust")
    for z in (0.5, height * 0.5 + 0.3, height - 0.6):
        bolt(mb, _T(0, w + 0.006, z) @ _R("X", -90), d=0.03)
    # desgaste: muesca en la cara de impacto
    mb.box((-w / 2 - 0.001, w - 0.05, height * 0.55), (w / 2 + 0.001, w + 0.001, height * 0.55 + 0.25), "wood_dark")
    del r
    return mb


def marine_ladder(z0, z1, seed=0, standoff=0.17):
    """Escalera marina embutida en el frente de atraque: largueros de solera 65x12, peldaños cuadrados de 25 mm a 0,30,
    ménsulas atornilladas al frente (en y = 0, la escalera queda en +Y), asideros curvos sobre la cubierta."""
    r = rng(seed)
    mb = MB()
    for dx in (-0.22, 0.22):
        mb.box((dx - 0.006, standoff - 0.032, z0), (dx + 0.006, standoff + 0.032, z1), "metal_rust")
        z = z0 + 0.4
        while z < z1 - 0.2:
            mb.box((dx - 0.006, 0.0, z - 0.03), (dx + 0.006, standoff - 0.03, z + 0.03), "metal_rust")
            mb.box((dx - 0.05, -0.0, z - 0.06), (dx + 0.05, 0.012, z + 0.06), "metal_rust")
            bolt(mb, _T(dx, 0.012, z) @ _R("X", -90), d=0.018)
            z += 1.5
        mb.tube([(dx, -0.3, z1), (dx, -0.3, z1 + 0.85), (dx, -0.15, z1 + 1.05), (dx, standoff, z1 + 0.85), (dx, standoff, z1 - 0.1)],
                0.021, seg=8, mat="metal_rust")
    z = z0 + 0.15
    while z < z1 - 0.15:
        if r.random() > 0.05:
            mb.box((-0.22, standoff - 0.0125, z - 0.0125), (0.22, standoff + 0.0125, z + 0.0125), "metal_rust")
        z += 0.30
    return mb


def light_pole(height=9.0, seed=0, broken=False, arm=1.6):
    """Poste de alumbrado: fuste octagonal cónico, placa base con cartelas y 4 anclas con doble tuerca, registro con tapa
    atornillada, brazo curvo y luminaria tipo cobra (carcasa, difusor de vidrio, bisagra)."""
    r = rng(seed)
    mb = MB()
    mb.plate([(-0.22, -0.22), (0.22, -0.22), (0.22, 0.22), (-0.22, 0.22)], 0.025, "metal_paint")
    for (x, y) in ((-0.17, -0.17), (0.17, -0.17), (-0.17, 0.17), (0.17, 0.17)):
        lathe(mb, [(0.012, -0.02), (0.012, 0.09)], seg=6, mat="metal_rust", M=_T(x, y, 0.0))
        bolt(mb, _T(x, y, 0.025), d=0.024, stud=0.0)
        bolt(mb, _T(x, y, 0.05), d=0.024, stud=0.03)
    for k in range(4):
        gusset(mb, _R("Z", 45 + 90 * k) @ _T(0.085, 0, 0.025), 0.1, 0.18, t=0.01)
    prof = [(0.13, 0.025), (0.13, 0.3), (0.118, 0.32)] + [(0.118 - 0.05 * (z / height), z) for z in (1.0, 3.0, 5.0, 7.0)] + \
           [(0.068, height - 0.05), (0.06, height)]
    lathe(mb, prof, seg=8, mat="metal_paint", phase=math.pi / 8)
    mb.box((-0.06, -0.125, 0.55), (0.06, -0.11, 0.95), "metal_paint")          # tapa del registro
    for z in (0.58, 0.92):
        bolt(mb, _T(0, -0.125, z) @ _R("X", 90), d=0.008, stud=0.0)
    # brazo curvo
    pts = []
    for k in range(9):
        t = k / 8
        pts.append((0.0, -arm * t, height - 0.35 + 0.55 * math.sin(t * math.pi / 2) - 0.12 * t * t))
    mb.tube(pts, 0.03, seg=10, mat="metal_paint")
    tb = 0.39
    zb = height - 0.35 + 0.55 * math.sin(tb * math.pi / 2) - 0.12 * tb * tb - 0.02
    mb.tube([(0, 0, height - 0.75), (0, -arm * tb * 0.45, height - 0.42), (0, -arm * tb, zb)], 0.016, seg=8, mat="metal_paint")
    head = Vector(pts[-1])
    Mh = _T(head.x, head.y, head.z) @ _R("Z", -90) @ _R("Y", 6)
    if not broken:
        loft(mb, [(-0.08, 0.075, 0.075, 0.0), (0.0, 0.16, 0.12, 0.01), (0.12, 0.3, 0.17, 0.02), (0.45, 0.4, 0.19, 0.02),
                  (0.75, 0.36, 0.15, 0.01), (0.88, 0.22, 0.09, -0.005)], seg=20, mat="metal_paint", M=Mh, ex=3.0)
        loft(mb, [(0.14, 0.24, 0.04, -0.065), (0.45, 0.34, 0.12, -0.085), (0.74, 0.28, 0.07, -0.06)], seg=16, mat="glass",
             M=Mh, ex=2.2)
        mb.box((0.02, -0.05, 0.1), (0.2, 0.05, 0.13), "metal_paint", m=Mh)          # fotocelda
    else:   # carcasa abierta colgando de la bisagra, difusor perdido, cables sueltos
        loft(mb, [(-0.05, 0.08, 0.08, 0.0), (0.05, 0.2, 0.12, 0.0), (0.3, 0.34, 0.16, 0.0), (0.6, 0.3, 0.13, 0.0),
                  (0.72, 0.16, 0.08, -0.01)], seg=16, mat="metal_paint", M=Mh @ _R("Y", 18))
        rope(mb, [Mh @ Vector((0.1, 0, -0.05)), Mh @ Vector((0.2, 0.05, -0.4)), Mh @ Vector((0.18, 0.08, -0.55))], r=0.006)
    del r
    return mb


def drum(seed=0):
    """Tambo de 200 L: cuerpo con dos aros de rodadura, chimbas rebordeadas, tapa con dos tapones (uno abierto), abolladura."""
    r = rng(seed)
    mb = MB()
    dent = float(r.uniform(0.0, 0.02))
    prof = [(0.0, 0.0), (0.285, 0.0), (0.293, 0.012), (0.286, 0.03), (0.286, 0.27), (0.297, 0.285), (0.286, 0.30),
            (0.286 - dent, 0.45), (0.286, 0.58), (0.297, 0.595), (0.286, 0.61), (0.286, 0.85), (0.293, 0.868), (0.285, 0.88),
            (0.27, 0.875), (0.0, 0.875)]
    lathe(mb, prof, seg=24, mat="metal_paint")
    for (x, y, rr) in ((0.17, 0.0, 0.03), (-0.12, 0.1, 0.018)):
        lathe(mb, [(rr, 0.875), (rr, 0.888), (rr * 0.7, 0.892), (0.0, 0.892)], seg=8, mat="metal_rust", M=_T(x, y, 0))
    return mb


# ------------------------------------------------------------------------------------------------ grúa de pedestal
def pedestal_crane(seed=0, yaw=-25.0, luff=38.0, boom_len=15.0, hook_z=-0.3):
    """Grúa de pedestal de muelle (origen: centro de la base sobre la cubierta, z = 0).
    Pedestal tubular Ø1,4 con brida y 24 pernos, cartelas, escalera con jaula; corona de giro con dientes; plataforma
    giratoria con barandal; casa de máquinas de lámina nervada con persianas y puerta; cabina con marcos y vidrios;
    caballete en A; pluma de celosía de ángulos (cordones y diagonales) con talón articulado y cabeza con poleas;
    cables de pluma y de izaje con su gancho; contrapeso."""
    r = rng(seed)
    mb = MB()
    # --- base y pedestal
    lathe(mb, [(1.3, 0.0), (1.3, 0.35), (1.2, 0.45), (0.0, 0.45)], seg=24, mat="concrete")
    lathe(mb, [(0.95, 0.45), (0.95, 0.52), (0.0, 0.52)], seg=32, mat="metal_paint")
    bolt_ring(mb, _T(0, 0, 0.52), 0.85, 24, d=0.03)
    lathe(mb, [(0.7, 0.52), (0.7, 4.3), (0.0, 4.3)], seg=28, mat="metal_paint", caps=False)
    for k in range(8):
        gusset(mb, _R("Z", 22.5 + 45 * k) @ _T(0.7, 0, 0.52), 0.22, 0.5, t=0.016)
    lathe(mb, [(0.88, 4.3), (0.88, 4.38), (0.6, 4.38)], seg=32, mat="metal_paint")
    bolt_ring(mb, _T(0, 0, 4.38), 0.8, 24, d=0.026)
    # corona de giro con dientes
    lathe(mb, [(0.84, 4.38), (0.84, 4.58), (0.6, 4.58)], seg=32, mat="metal_rust")
    for k in range(48):
        a = 2 * math.pi * k / 48
        M = _T(0.86 * math.cos(a), 0.86 * math.sin(a), 4.4) @ _R("Z", math.degrees(a))
        mb.box((-0.025, -0.02, 0.0), (0.025, 0.02, 0.16), "metal_rust", m=M)
    # escalera con jaula por el pedestal
    for dx in (-0.2, 0.2):
        mb.box((dx - 0.006, -0.95, 0.45), (dx + 0.006, -0.89, 5.6), "metal_paint")
    z = 0.75
    while z < 5.5:
        mb.box((-0.2, -0.925, z - 0.01), (0.2, -0.915, z + 0.01), "metal_paint")
        z += 0.3
    for z in range(3, 6):
        pts = [(0.28 * math.cos(math.radians(a)) * 1.0 + 0.0, -0.92 - 0.28 * math.sin(math.radians(a)) - 0.25, z * 1.0)
               for a in range(-10, 191, 20)]
        mb.tube(pts, 0.012, seg=5, mat="metal_paint")
    for a in (20, 90, 160):
        x, y = 0.53 * math.cos(math.radians(a)) * 0.0 + 0.28 * math.cos(math.radians(a)), -1.17 - 0.28 * math.sin(math.radians(a))
        mb.box((x - 0.02, y - 0.003, 2.9), (x + 0.02, y + 0.003, 5.6), "metal_paint")
    # --- parte giratoria
    R = _T(0, 0, 4.58) @ _R("Z", yaw)
    up = MB()
    up.plate([(-1.4, -2.6), (1.4, -2.6), (1.4, 2.4), (-1.4, 2.4)], 0.025, "metal_rust")     # plataforma estriada
    for (a, b) in [((-1.4, -2.6), (1.4, -2.6)), ((1.4, -2.6), (1.4, 2.4)), ((-1.4, 2.4), (-1.4, -2.6))]:
        handrail(up, (a[0], a[1], 0.025), (b[0], b[1], 0.025), h=1.05, post_step=1.3, r=r)
    # casa de máquinas (lámina nervada, persianas, puerta)
    hx0, hx1, hy0, hy1, hz = -1.15, 1.15, 0.2, 2.2, 1.9
    up.box((hx0, hy0, 0.025), (hx1, hy1, 0.06), "metal_paint")
    for (x0, x1, y0, y1) in ((hx0, hx1, hy0, hy0 + 0.03), (hx0, hx1, hy1 - 0.03, hy1), (hx0, hx0 + 0.03, hy0, hy1),
                             (hx1 - 0.03, hx1, hy0, hy1)):
        up.box((x0, y0, 0.06), (x1, y1, hz), "metal_paint")
    k = 0.0
    while hx0 + k < hx1 - 0.05:
        x = hx0 + 0.1 + k
        for (y, s) in ((hy0, -1), (hy1, 1)):
            up.box((x - 0.012, y + (s * 0.03 if s > 0 else -0.03), 0.1), (x + 0.012, y + (s * 0.0), hz - 0.05), "metal_paint")
        k += 0.2
    for i in range(6):     # persianas en el costado
        zz = 0.9 + i * 0.12
        up.box((hx1, 0.9, zz), (hx1 + 0.06, 1.7, zz + 0.012), "metal_paint", m=_T(hx1, 0, zz) @ _R("Y", 30) @ _T(-hx1, 0, -zz))
    up.box((hx0 - 0.01, 0.6, 0.06), (hx0 + 0.005, 1.4, 1.7), "metal_rust")         # puerta
    up.plate([(hx0 - 0.08, hy0 - 0.08), (hx1 + 0.08, hy0 - 0.08), (hx1 + 0.08, hy1 + 0.08), (hx0 - 0.08, hy1 + 0.08)], 0.05,
             "metal_paint", m=_T(0, 0, hz))
    up.box((-1.3, hy1, 0.06), (1.3, hy1 + 0.75, 1.2), "concrete", bevel=0.03)     # contrapeso
    # cabina del operador (marcos y vidrios)
    cx0, cx1, cy0, cy1, cz0, cz1 = 0.35, 1.35, -2.4, -0.6, 0.06, 2.1
    up.box((cx0, cy0, cz0), (cx1, cy1, 0.95), "metal_paint")
    for (x, y) in ((cx0, cy0), (cx1 - 0.05, cy0), (cx0, cy1 - 0.05), (cx1 - 0.05, cy1 - 0.05)):
        up.box((x, y, 0.95), (x + 0.05, y + 0.05, cz1), "metal_paint")
    up.box((cx0, cy0, cz1), (cx1, cy1, cz1 + 0.08), "metal_paint")
    up.box((cx0 - 0.05, cy0 - 0.1, cz1 + 0.08), (cx1 + 0.05, cy1 + 0.05, cz1 + 0.12), "metal_paint")
    up.box((cx0 + 0.05, cy0 + 0.005, 1.0), (cx1 - 0.05, cy0 + 0.015, cz1 - 0.05), "glass")
    up.box((cx1 - 0.015, cy0 + 0.05, 1.0), (cx1 - 0.005, cy1 - 0.05, cz1 - 0.05), "glass")
    up.box((cx0 + 0.45, cy0 - 0.02, 1.0), (cx0 + 0.47, cy0, cz1 - 0.05), "metal_paint")      # montante
    up.tube([(cx0 + 0.25, cy0 - 0.02, 1.9), (cx0 + 0.42, cy0 - 0.02, 1.45)], 0.006, seg=4, mat="cable")      # limpiador
    # caballete en A y pie de la pluma
    for sg in (-1, 1):
        up.tube([(sg * 0.85, 0.5, 1.95), (sg * 0.2, -0.3, 4.6)], 0.07, seg=10, mat="metal_paint")
        up.tube([(sg * 0.85, -1.0, 0.06), (sg * 0.2, -0.3, 4.6)], 0.06, seg=10, mat="metal_paint")
    up.tube([(-0.3, -0.3, 4.6), (0.3, -0.3, 4.6)], 0.06, seg=10, mat="metal_paint")
    sheave(up, _T(0, -0.3, 4.72), R=0.22)
    for sg in (-1, 1):     # talón de la pluma: orejas y perno
        up.plate([(-0.12, 0.0), (0.12, 0.0), (0.08, 0.35), (-0.08, 0.35)], 0.03, "metal_paint",
                 m=_T(sg * 0.4, -1.2, 0.06) @ _R("X", 90) @ _T(0, 0, -0.015) @ _R("Z", 0))
    up.tube([(-0.5, -1.2, 0.3), (0.5, -1.2, 0.3)], 0.045, seg=12, mat="metal_rust")
    # --- pluma de celosía (cordones de ángulo, diagonales en las 4 caras)
    el = math.radians(luff)
    d = Vector((0.0, -math.cos(el), math.sin(el)))
    base = Vector((0.0, -1.2, 0.3))
    hw = 0.38
    n = 16

    def chord_pt(ix, iz, t):
        taper = 1.0 - 0.55 * max(0.0, t - 0.75) / 0.25 - 0.45 * max(0.0, 0.08 - t) / 0.08
        return base + d * (boom_len * t) + Vector((ix * hw * taper, 0, 0)) + Vector((0, math.sin(el), math.cos(el))) * (iz * hw * taper)
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    for (ix, iz) in corners:
        for i in range(n):
            p0, p1 = chord_pt(ix, iz, i / n), chord_pt(ix, iz, (i + 1) / n)
            angle_bar(up, p0, p1, leg=0.09, t=0.009, mat="metal_paint", up=(0, math.sin(el), math.cos(el)), flip=ix > 0)
    for f in range(4):
        a, b = corners[f], corners[(f + 1) % 4]
        for i in range(n):
            t0, t1 = i / n, (i + 1) / n
            pa = chord_pt(*a, t0) if i % 2 == 0 else chord_pt(*b, t0)
            pb = chord_pt(*b, t1) if i % 2 == 0 else chord_pt(*a, t1)
            up.tube([pa, pb], 0.022, seg=5, mat="metal_paint")
    # cabeza de la pluma
    tip = base + d * boom_len
    Mbm, _ = frame_on(base, tip, up=(0, math.sin(el), math.cos(el)))
    head = [(-0.9, -0.2), (-0.15, -0.34), (0.22, -0.3), (0.38, -0.12), (0.38, 0.12), (0.22, 0.32), (-0.15, 0.3), (-0.9, 0.2)]
    for sg in (-1, 1):
        up.plate(head, 0.02, "metal_paint", m=Mbm @ _T(boom_len, sg * 0.17 - 0.01, 0) @ _R("X", -90) @ _T(0, 0, -0.01 * sg))
    for (dx, dz) in ((-0.7, 0.0), (0.22, 0.0)):
        up.tube([Mbm @ Vector((boom_len + dx, -0.2, dz)), Mbm @ Vector((boom_len + dx, 0.2, dz))], 0.035, seg=10,
                mat="metal_rust")
    Mt = _T(tip.x, tip.y, tip.z)
    sheave(up, Mt @ _R("Z", 90), R=0.3, w=0.1)
    # cables: pluma (4 ramales del caballete a la cabeza) e izaje (al gancho)
    for dx in (-0.06, -0.02, 0.02, 0.06):
        rope(up, [(dx, -0.3, 4.72), (tip.x + dx, tip.y + 0.05, tip.z + 0.25)], r=0.01)
    hook_top = Vector((tip.x, tip.y - 0.3, hook_z + 1.2 - 4.58))
    rope(up, [(0.0, 0.5, 1.2), (0.0, -0.3, 4.5), (tip.x, tip.y - 0.25, tip.z + 0.2)], r=0.011)
    for dx in (-0.05, 0.05):
        rope(up, [(tip.x + dx, tip.y - 0.3, tip.z), (hook_top.x + dx, hook_top.y, hook_top.z + 0.45)], r=0.011)
    # motón y gancho
    Mb = _T(hook_top.x, hook_top.y, hook_top.z)
    for sg in (-1, 1):
        up.plate([(-0.18, 0.0), (0.18, 0.0), (0.14, 0.42), (-0.14, 0.42)], 0.02, "metal_paint",
                 m=Mb @ _T(0, sg * 0.07, 0) @ _R("X", 90) @ _T(0, 0, -0.01))
    sheave(up, Mb @ _T(0, 0, 0.25), R=0.13, w=0.08)
    lathe(up, [(0.05, -0.25), (0.05, 0.0)], seg=10, mat="metal_rust", M=Mb)
    hook = []
    for k in range(13):
        a = math.radians(-90 + 300 * k / 12)
        hook.append(Mb @ Vector((0.13 * math.cos(a) * 1.0, 0.0, -0.4 + 0.13 * math.sin(a))))
    up.tube([Mb @ Vector((0, 0, -0.25))] + hook, 0.032, seg=10, mat="metal_rust",
            radii=[0.045] + [0.045 - 0.025 * k / 12 for k in range(13)])
    mb.join(up, R)
    mb.meta = dict(tip=R @ tip, top=R @ Vector((0, 0, tip.z)))
    return mb


# ------------------------------------------------------------------------------------------------ contenedor
def container(seed=0, open_doors=False, mat="container"):
    """Contenedor ISO de 20' (6,058 x 2,438 x 2,591). Local: x 0..L, y 0..W, z 0..H. Costados de lámina trapezoidal (sólidos
    delgados), esquineros, largueros con bolsas para montacargas, cantoneras de fundición con ojales, techo abollado, frente
    corrugado y dos puertas con 4 barras de cierre (guías, levas, manijas), 8 bisagras y burletes."""
    import mue_builder as mbld
    r = rng(seed)
    mb = MB()
    L, W, H = 6.058, 2.438, 2.591
    m = mat
    # esquineros (perfil en C) y cantoneras con ojales
    for (x, y, sx, sy) in ((0, 0, 1, 1), (L, 0, -1, 1), (0, W, 1, -1), (L, W, -1, -1)):
        x0, x1 = sorted((x, x + sx * 0.13))
        y0, y1 = sorted((y, y + sy * 0.13))
        mb.box((x0, y0, 0.118), (x1, y1, H - 0.118), m)
        for z0 in (0.0, H - 0.118):
            cx0, cx1 = sorted((x, x + sx * 0.178))
            cy0, cy1 = sorted((y, y + sy * 0.162))
            mb.box((cx0, cy0, z0), (cx1, cy1, z0 + 0.118), "metal_rust")
            # ojales de la cantonera (cara lateral y de testa)
            fy = cy0 - 0.003 if sy > 0 else cy1
            mb.box((cx0 + 0.05, fy, z0 + 0.035), (cx1 - 0.05, fy + 0.003, z0 + 0.083), "cable")
    # largueros inferiores y superiores (laterales y de testa) con bolsas de montacargas
    for y, sy in ((0.0, 1), (W, -1)):
        y0, y1 = sorted((y, y + sy * 0.16))
        mb.box((0.178, y0, 0.0), (L - 0.178, y1, 0.16), m)
        mb.box((0.178, y0, H - 0.1), (L - 0.178, y1, H), m)
        for xc in (L / 2 - 1.03, L / 2 + 1.03):
            fy = y0 - 0.004 if sy > 0 else y1
            mb.box((xc - 0.18, fy, 0.0), (xc + 0.18, fy + 0.004, 0.12), "cable")
    for x, sx in ((0.0, 1), (L, -1)):
        x0, x1 = sorted((x, x + sx * 0.16))
        mb.box((x0, 0.162, 0.0), (x1, W - 0.162, 0.16), m)
        mb.box((x0, 0.162, H - 0.12), (x1, W - 0.162, H), m)
    mb.box((0.16, 0.16, 0.1), (L - 0.16, W - 0.16, 0.16), "wood_dark")
    # techo abollado (rejilla con ruido)
    nx, ny = 12, 5
    vs = {}
    for i in range(nx + 1):
        for j in range(ny + 1):
            x = 0.16 + (L - 0.32) * i / nx
            y = 0.16 + (W - 0.32) * j / ny
            dz = 0.0 if i in (0, nx) or j in (0, ny) else float(r.uniform(-0.03, 0.005))
            vs[(i, j)] = mb.bm.verts.new((x, y, H - 0.04 + dz))
    for i in range(nx):
        for j in range(ny):
            mb.face([vs[(i, j)], vs[(i + 1, j)], vs[(i + 1, j + 1)], vs[(i, j + 1)]], m)
    bv = [mb.bm.verts.new((v.co.x, v.co.y, H - 0.06)) for v in [vs[(0, 0)], vs[(nx, 0)], vs[(nx, ny)], vs[(0, ny)]]]
    mb.face(list(reversed(bv)), m)
    # costados y frente de lámina trapezoidal (pasos de 0,2; el kit usa el mismo perfil que la nave)
    Ms = Matrix(((1, 0, 0, 0.178), (0, 1, 0, 0.045), (0, 0, 1, 0.16), (0, 0, 0, 1)))
    mbld.sheet(mb, 0.0, L - 0.356, lambda u: 0.0, lambda u: H - 0.26, m, Ms)
    Mn = Matrix(((-1, 0, 0, L - 0.178), (0, -1, 0, W - 0.045), (0, 0, 1, 0.16), (0, 0, 0, 1)))
    mbld.sheet(mb, 0.0, L - 0.356, lambda u: 0.0, lambda u: H - 0.26, m, Mn)
    Mf = Matrix(((0, 1, 0, 0.045), (-1, 0, 0, W - 0.162), (0, 0, 1, 0.16), (0, 0, 0, 1)))
    mbld.sheet(mb, 0.0, W - 0.324, lambda u: 0.0, lambda u: H - 0.28, m, Mf)
    # puertas (extremo x = L)
    leaf = (W - 0.324) / 2
    for sg in (1, -1):
        hinge_y = 0.162 if sg > 0 else W - 0.162
        ang = (float(r.uniform(70, 120)) if open_doors else 0.0) * (-sg)
        Md = _T(L - 0.03, hinge_y, 0.16) @ _R("Z", ang)
        d = MB()
        y0, y1 = (0.0, leaf) if sg > 0 else (-leaf, 0.0)
        d.box((0.0, y0, 0.0), (0.04, y1, H - 0.28), m)
        # nervaduras horizontales de la hoja
        for k in range(1, 5):
            zz = (H - 0.28) * k / 5
            d.box((0.04, y0 + 0.05, zz - 0.035), (0.055, y1 - 0.05, zz + 0.035), m)
        # bisagras
        for zz in (0.2, 0.9, 1.6, 2.15):
            lathe(d, [(0.02, zz), (0.02, zz + 0.1)], seg=8, mat="metal_rust", M=_T(0.03, 0.0, 0.0))
            d.box((0.03, min(0.0, sg * 0.12), zz + 0.02), (0.05, max(0.0, sg * 0.12), zz + 0.08), "metal_rust")
        # barras de cierre con guías, levas y manijas
        for f in (0.28, 0.72):
            yy = (y0 + y1) / 2 + (f - 0.5) * leaf * 0.9
            d.tube([(0.075, yy, 0.02), (0.075, yy, H - 0.3)], 0.016, seg=8, mat="metal_rust")
            for zz in (0.12, 0.85, 1.55, H - 0.42):
                d.box((0.04, yy - 0.04, zz), (0.09, yy + 0.04, zz + 0.04), "metal_rust")
            d.box((0.06, yy - 0.025, -0.02), (0.1, yy + 0.025, 0.04), "metal_rust")
            d.box((0.06, yy - 0.025, H - 0.32), (0.1, yy + 0.025, H - 0.27), "metal_rust")
            ang_h = float(r.uniform(-5, 40))
            d.tube([(0.075, yy, 1.05), (0.15, yy + 0.02, 1.05), (0.18, yy + 0.32 * math.cos(math.radians(ang_h)), 1.05 +
                    0.05 * math.sin(math.radians(ang_h)))], 0.012, seg=6, mat="metal_rust")
        mb.join(d, Md)
    mb.box((L - 0.06, 0.162, H - 0.12), (L, W - 0.162, H - 0.1), m)
    return mb
