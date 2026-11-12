"""kit/telecom.py — equipo del sitio celular COM_1_antena (2026, actual, no futurista): recinto de malla ciclónica con
alambre de púas, puente de cables (ice bridge), gabinetes exteriores, generador diésel con tanque de doble pared,
H-frame de acometida, poste de luz con cámara, equipamiento interior de la caseta prefabricada y letreros.

Convenciones (todas las funciones devuelven un MB):
- metros, Z arriba, origen en el contacto con el piso (z = 0) y centrado salvo que la función diga otra cosa;
- el frente mira a -Y; las piezas de muro tienen la espalda en el plano del muro y = 0 y crecen hacia -Y;
- las corridas lineales (cerca, puente de cables) van a lo largo de +X desde x = 0.
Materiales: galvanized, steel, aluminium, metal_rust, concrete, rubber, cable, plastic, plastic_blue, enamel, sign_*, paint_yellow,
glass, vinyl, paper, copper, gravel, radome.

INSTANCIAS (malla ciclónica, púas, amarres): la tela de alambre tejido real cuesta ~8 000 triángulos por par de pickets y el
alambre de púas ~5 600 por metro; no caben en una malla única por tramo. `fence_run` y `fence_gate` devuelven un `TelMB` cuyo
`instances` guarda {tipo: (constructor, [Matrix...])}. `TelMB.finish()` crea la malla propia del tramo y, como hijos, objetos
"linked duplicate" que comparten UNA malla por tipo (TEL_*), lista para instanciarse en UE5 (ISM/HISM) o para unirse al
exportar. `TelMB.transform()` y `TelMB.join()` arrastran las instancias; `realize()` (o fabric="join") las vuelve geometría
propia (para vistas previas) y entonces `finish()` suaviza a 65° para que los alambres de 6 lados no se vean facetados.
"""
import math

import bmesh
import bpy  # noqa: F401  (bpy antes que mathutils)
from mathutils import Matrix, Vector

from kit.clinic import MB, PI, _Rx, _Ry, _Rz, _T, fillet, rbox, rng, rr_profile, rtube  # noqa: F401
from kit.clinic_equipo import loft_rings, revolve, sweep_frame  # noqa: F401
from kit.clinic_servicios import hexnut, holed, label, lathe, louver_grille, rr_pts, rrframe, screw, skin, slab  # noqa: F401

IN = 0.0254
# --- medidas de la malla ciclónica (ASTM F1083 / F668; catálogos chainlinkfittings.com y hooverfence.com) ---
R_LINE = 2.375 * IN / 2          # poste de línea 2-3/8" OD
R_TERM = 2.875 * IN / 2          # poste terminal / esquina 2-7/8" OD
R_GATEPOST = 4.0 * IN / 2        # poste de puerta 4" OD
R_RAIL = 1.625 * IN / 2          # larguero superior 1-5/8" OD
R_GFRAME = 1.875 * IN / 2        # marco de hoja de puerta 1-7/8" OD (marco industrial "2 in")
CL_W = 2.0 * IN / math.sqrt(2)   # malla de 2": paso horizontal entre pickets = media diagonal del rombo (35,9 mm)
CL_D = CL_W                      # paso vertical entre nudos (rombo cuadrado)
CL_R = 0.148 * IN / 2            # alambre calibre 9 (3,76 mm)
CL_E = 0.0022                    # semiespesor de la hélice aplastada del picket
CL_B = 0.0026                    # cuánto sobresale cada vuelta del nudo más allá del eje del nudo
R_TW = 0.177 * IN / 2            # alambre tensor inferior calibre 7 (4,5 mm)
Y_FAB = -(R_LINE + 2 * R_TW + CL_E + CL_R + 0.0012)   # plano de la tela (lado público, -Y), por fuera del alambre tensor
Y_TW = -(R_LINE + R_TW + 0.0003)                        # alambre tensor inferior, pegado a la cara de los postes
Y_RAIL = Y_FAB + CL_E + CL_R + 0.0005 + R_RAIL          # larguero: su cara exterior a 0,5 mm de la tela
BARB_P = 5.0 * IN                # púas cada 5" (127 mm), alambre 12-1/2 ga de 2 hilos, púa de 4 puntas 14 ga
SEG = 24                         # lados de todo cilindro visible
SEG_T = 14                       # lados de tubos delgados / cables (> 12: con el suavizado de 30° del kit no se facetan)


# ====================================================================================================== infraestructura
class TelMB(MB):
    """MB con instancias. instances = {tipo: [constructor() -> MB, [Matrix, ...]]}."""

    def __init__(self):
        super().__init__()
        self.instances = {}
        self.smooth_default = 30.0

    def add_inst(self, kind, build, M):
        self.instances.setdefault(kind, [build, []])[1].append(M.copy())

    def transform(self, m):
        super().transform(m)
        for d in self.instances.values():
            d[1] = [m @ M for M in d[1]]

    def join(self, other, m=None):
        super().join(other, m)
        for kind, d in getattr(other, "instances", {}).items():
            for M in d[1]:
                self.add_inst(kind, d[0], (m @ M) if m is not None else M)
        if getattr(other, "smooth_default", 30.0) > self.smooth_default:
            self.smooth_default = other.smooth_default

    def realize(self):
        """Convierte las instancias en geometría propia (vista previa / cuando el tramo se une a otro MB sin instancias)."""
        for kind, (build, mats) in self.instances.items():
            src = _inst_mb(kind, build)
            for M in mats:
                MB.join(self, src, M)
        self.instances = {}
        self.smooth_default = 65.0
        return self

    def inst_tris(self):
        """Triángulos que suman las instancias si se realizan (para el reporte)."""
        tot = 0
        for kind, (build, mats) in self.instances.items():
            src = _inst_mb(kind, build)
            tot += len(mats) * sum(len(f.verts) - 2 for f in src.bm.faces)
        return tot

    def finish(self, name, collection=None, smooth_angle=None, merge=0.0001, uv_size=None):
        inst = self.instances
        ob = super().finish(name, collection, smooth_angle=smooth_angle or self.smooth_default, merge=merge, uv_size=uv_size)
        col = collection or bpy.context.scene.collection
        for kind, (build, mats) in inst.items():
            me = _inst_mesh(kind, build, uv_size)
            for i, M in enumerate(mats):
                o = bpy.data.objects.new(f"{name}_{kind}_{i:03d}", me)
                col.objects.link(o)
                o.parent = ob
                o.matrix_parent_inverse = Matrix()
                o.matrix_basis = M
        return ob


_INST_CACHE = {}


def _inst_mb(kind, build):
    if kind not in _INST_CACHE:
        _INST_CACHE[kind] = build()
    return _INST_CACHE[kind]


def _inst_mesh(kind, build, uv_size=None):
    """Malla compartida TEL_<tipo> (una por tipo): alambres de 6 lados con normales 100 % suaves (ángulo 89°)."""
    nm = f"TEL_{kind}"
    me = bpy.data.meshes.get(nm)
    if me is not None:
        return me
    src = _inst_mb(kind, build)
    tmp = MB()
    MB.join(tmp, src)
    ob = tmp.finish(nm + "_tmp", smooth_angle=89.0, merge=0, uv_size=uv_size or 1.0)
    me = ob.data
    me.name = nm
    bpy.data.objects.remove(ob)
    return me


# ======================================================================================================== primitivas
def pipe(mb, p0, p1, r, mat="galvanized", seg=SEG, caps=True):
    """Tubo redondo (cilindro visible de >= 24 lados)."""
    return mb.cyl(p0, p1, r, seg=seg, mat=mat, caps=caps)


def wire(mb, pts, r, mat="galvanized", seg=SEG_T, bend=None, nseg=6, caps=True):
    """Alambre / cable por una polilínea; bend = radio de doblez real."""
    P = fillet(pts, bend, nseg) if (bend and len(pts) > 2) else pts
    P = _dedupe(P)
    mb.tube(P, r, seg=seg, mat=mat, caps=caps)
    return P


def _dedupe(pts, eps=1e-6):
    out = [Vector(pts[0])]
    for p in pts[1:]:
        if (Vector(p) - out[-1]).length > eps:
            out.append(Vector(p))
    return [tuple(p) for p in out]


def ring(mb, M, R, r, mat="galvanized", n=24, seg=8, a0=0.0, a1=2 * PI):
    """Toro (o arco de toro a0..a1) de radio R y alambre r en el plano XY local."""
    full = abs(a1 - a0 - 2 * PI) < 1e-6
    cnt = n if full else n + 1
    rings = []
    for i in range(cnt):
        a = a0 + (a1 - a0) * i / n
        c = Vector((R * math.cos(a), R * math.sin(a), 0.0))
        rad = Vector((math.cos(a), math.sin(a), 0.0))
        rings.append([mb.bm.verts.new(M @ (c + rad * (r * math.cos(2 * PI * k / seg)) + Vector((0, 0, r * math.sin(2 * PI * k / seg)))))
                      for k in range(seg)])
    nn = cnt if full else cnt - 1
    for i in range(nn):
        A, B = rings[i], rings[(i + 1) % cnt]
        for k in range(seg):
            kk = (k + 1) % seg
            mb.face([A[k], B[k], B[kk], A[kk]], mat)
    if not full:
        mb.face(list(rings[0]), mat)
        mb.face(list(reversed(rings[-1])), mat)


def bolt(mb, M, d=0.012, L=0.03, mat="steel", washer=True, seg=12):
    """Perno hexagonal visto desde la cabeza (z = 0 = superficie de apoyo, eje +Z hacia afuera)."""
    z = 0.0
    if washer:
        lathe(mb, [(d * 0.55, -0.0003), (d * 1.05, -0.0003), (d * 1.05, d * 0.12), (d * 0.55, d * 0.14)], seg=seg, mat=mat, M=M)
        z = d * 0.12
    hexnut(mb, M @ _T(0, 0, z), s=d * 1.5, h=d * 0.62, mat=mat)


def stud(mb, M, d=0.012, proud=0.02, mat="steel", seg=12):
    """Tuerca hexagonal + arandela + espárrago roscado que sobresale `proud` (sobre z = 0 local, eje +Z)."""
    bolt(mb, M, d, mat=mat, seg=seg)
    zt = d * 0.12 + d * 0.62
    rr = d / 2
    prof = [(rr * 0.92, zt - 0.001)]
    pitch = d * 0.15
    k = 0
    z = zt
    while z < zt + proud - pitch:
        prof += [(rr, z + pitch * 0.25), (rr * 0.86, z + pitch * 0.75)]
        z += pitch
        k += 1
    prof += [(rr * 0.85, zt + proud), (0.0, zt + proud)]
    lathe(mb, prof, seg=seg, mat=mat, M=M, caps=True)


def carriage_bolt(mb, M, d=0.0095, mat="galvanized"):
    """Cabeza de domo de perno de carruaje (z = 0 = superficie)."""
    lathe(mb, [(d * 1.05, -0.0003), (d * 1.05, d * 0.12), (d * 0.85, d * 0.4), (d * 0.45, d * 0.55), (0.0, d * 0.58)], seg=16, mat=mat,
          M=M)


def frame_x(p0, p1, up=(0, 0, 1)):
    """Matriz con X a lo largo de p0->p1 y Z hacia `up`."""
    p0, p1 = Vector(p0), Vector(p1)
    X = (p1 - p0).normalized()
    U = Vector(up)
    if abs(X.dot(U)) > 0.99:
        U = Vector((0, 1, 0)) if abs(X.y) < 0.9 else Vector((1, 0, 0))
    Z = (U - X * X.dot(U)).normalized()
    Y = Z.cross(X)
    return Matrix(((X.x, Y.x, Z.x, p0.x), (X.y, Y.y, Z.y, p0.y), (X.z, Y.z, Z.z, p0.z), (0, 0, 0, 1)))


def chan(mb, p0, p1, w, h, t, mat="galvanized", up=(0, 0, 1), open_dir=1, r=0.002):
    """Perfil C (canal) de p0 a p1: alma de alto h en `up`, patines de ancho w; open_dir = ±1 hacia donde abren los patines."""
    s = open_dir
    prof = [(0.0, -h / 2), (s * w, -h / 2), (s * w, -h / 2 + t), (s * (t + r), -h / 2 + t), (s * t, -h / 2 + t + r),
            (s * t, h / 2 - t - r), (s * (t + r), h / 2 - t), (s * w, h / 2 - t), (s * w, h / 2), (0.0, h / 2)]
    if s < 0:
        prof = list(reversed(prof))
    sweep_frame(mb, prof, [p0, p1], mat, up=up)


def strut(mb, p0, p1, mat="galvanized", up=(0, 0, 1), depth=1.625 * IN, w=1.625 * IN, t=0.0025):
    """Canal unistrut 1-5/8" (P1000): perfil C con labios doblados hacia adentro; la boca mira a -up."""
    lip = 0.0095
    hw = w / 2
    prof = [(-hw, depth), (hw, depth), (hw, 0.0), (hw - lip, 0.0), (hw - lip, t * 1.2), (hw - t, t * 1.2), (hw - t, depth - t),
            (-hw + t, depth - t), (-hw + t, t * 1.2), (-hw + lip, t * 1.2), (-hw + lip, 0.0), (-hw, 0.0)]
    prof = [(x, y - depth) for (x, y) in prof]           # el lomo (cerrado) queda en y = 0 = `up`
    sweep_frame(mb, prof, [p0, p1], mat, up=up)


def footing(mb, x, y, r_post, r_foot, crown=0.035, mat="concrete", seg=SEG):
    """Corona de concreto del dado colado alrededor de un poste (domo que escurre el agua; se entierra 5 cm)."""
    lathe(mb, [(r_foot, -0.05), (r_foot, 0.004), (r_foot * 0.9, crown * 0.55), (r_foot * 0.65, crown * 0.9),
               (r_post + 0.006, crown), (r_post + 0.0015, crown * 0.98)], seg=seg, mat=mat, M=_T(x, y, 0.0), caps=False)


def dome_cap(mb, x, y, z, r, mat="galvanized"):
    """Tapón de domo de lámina embutida para poste terminal (asienta en el tope del tubo a z)."""
    rr = r + 0.0022
    lathe(mb, [(r - 0.0005, z - 0.045), (rr, z - 0.044), (rr + 0.0008, z - 0.040), (rr, z - 0.036), (rr, z + 0.004),
               (rr * 0.93, z + 0.016), (rr * 0.72, z + 0.026), (rr * 0.38, z + 0.032), (0.0, z + 0.0335)], seg=SEG, mat=mat,
          M=_T(x, y, 0.0), caps=False)


# ============================================================================================ malla ciclónica (instancias)
def _picket_pts(u0, u1, n_top=None, n_bot=0):
    """Línea central de un picket (hélice aplastada de alambre cal. 9) entre los parámetros u0..u1 (u = altura / CL_D).
    Las piernas son rectas; en cada nudo (u entero) el alambre da la vuelta alrededor del picket vecino: sobresale CL_B y cruza
    de un lado al otro de la tela (y = +e -> -e), de modo que el vecino (mismo picket desplazado CL_W, CL_D) se entrelaza."""
    tau = 0.1
    A = (CL_W / 2 + CL_B) / (1 - tau)
    s = 2 * A

    def P(u):
        k = round(u)
        du = u - k
        sg = 1.0 if (k % 2) else -1.0
        q = s * (du * du + tau * tau) / (2 * tau) if abs(du) < tau else s * abs(du)
        x = CL_W / 2 + sg * (A - q)
        kk = 6.0
        y = CL_E * math.tanh(kk * math.sin(PI * u)) / math.tanh(kk)
        return Vector((x, y, CL_D * u))

    us = []
    k0, k1 = math.floor(u0), math.ceil(u1)
    for k in range(k0, k1 + 1):
        for du in (-0.1, -0.04, 0.0, 0.04, 0.1):
            u = k + du
            if u0 - 1e-9 <= u <= u1 + 1e-9:
                us.append(u)
    us = sorted(set(round(u, 6) for u in us))
    return [P(u) for u in us], P


def _picket(mb, u0, u1, top_twist, M):
    """Un picket entre u0 (abajo, nudo de orilla anudado) y u1 (arriba, orilla torcida con puntas)."""
    pts, P = _picket_pts(u0 - 0.1, u1)
    if top_twist:                                         # orilla superior torcida: 1,5 vueltas con su vecino y punta cortada
        k = round(u1)
        sg = 1.0 if (k % 2) else -1.0
        xk = CL_W / 2 + sg * CL_W / 2
        zt = CL_D * u1
        rt = CL_R * 1.08
        a0 = 0.0 if sg > 0 else PI
        for i in range(1, 13):
            t = i / 12
            a = a0 + 3 * PI * t
            pts.append(Vector((xk + rt * math.cos(a), rt * math.sin(a), zt + 0.003 + 0.024 * t)))
    mb.tube([tuple(M @ p) for p in pts], CL_R, seg=6, mat="galvanized")


def chainlink_pair(n):
    """Par de pickets (unidad de repetición, ancho 2 × 35,9 mm) de n nudos de alto; origen: nudo inferior izquierdo."""
    mb = MB()
    _picket(mb, 0.0, float(n), True, Matrix())
    _picket(mb, -1.0, float(n - 1), True, _T(CL_W, 0.0, CL_D))
    return mb


def chainlink_panel(n, pairs):
    mb = MB()
    src = chainlink_pair(n)
    for i in range(pairs):
        mb.join(src, _T(2 * CL_W * i, 0, 0))
    return mb


def _add_fabric(mb, x0, x1, z0, n, M=None, fabric="instance"):
    """Tela ciclónica de x0 a x1 (plano y = 0 local), nudos inferiores en z0, n nudos de alto. M coloca la tela."""
    M = M if M is not None else Matrix()
    pairs = max(1, int(round((x1 - x0) / (2 * CL_W))))
    x = (x0 + x1) / 2 - pairs * CL_W
    big = 8
    nb, rest = divmod(pairs, big)
    for _ in range(nb):
        mb.add_inst(f"cl8_n{n}", lambda n=n: chainlink_panel(n, big), M @ _T(x, 0, z0))
        x += 2 * CL_W * big
    for _ in range(rest):
        mb.add_inst(f"cl1_n{n}", lambda n=n: chainlink_pair(n), M @ _T(x, 0, z0))
        x += 2 * CL_W
    return (x0 + x1) / 2 - pairs * CL_W, x


def barbed_module(nb=8):
    """Alambre de púas: 2 hilos 12-1/2 ga torcidos (2 vueltas por púa) y púas de 4 puntas 14 ga cada 127 mm, a lo largo de +X
    de 0 a nb × 127 mm (eje del cordón en y = z = 0)."""
    mb = MB()
    L = nb * BARB_P
    rl = 0.00127
    rh = rl * 1.02
    turns = nb * 2
    npts = turns * 8
    for ph in (0.0, PI):
        pts = []
        for i in range(npts + 1):
            t = i / npts
            a = ph + 2 * PI * turns * t
            pts.append((L * t, rh * math.cos(a), rh * math.sin(a)))
        mb.tube(pts, rl, seg=6, mat="galvanized")
    rb = 0.001
    for k in range(nb):
        xc = (k + 0.5) * BARB_P
        for j, ph in enumerate((0.0, PI / 2)):
            Rw = rh + rl + rb * 1.1
            pts = []
            # punta 1 (sale tangente y se corta en bisel), 1,5 vueltas de amarre, punta 2
            a_s = ph
            out1 = Vector((xc - 0.002 + j * 0.0045, Rw * math.cos(a_s), Rw * math.sin(a_s)))
            tang = Vector((0.0, -math.sin(a_s), math.cos(a_s)))
            radial = Vector((0.0, math.cos(a_s), math.sin(a_s)))
            pts.append(out1 - tang * 0.011 + radial * 0.006 + Vector((-0.002, 0, 0)))
            for i in range(11):
                t = i / 10
                a = a_s + 3 * PI * t
                pts.append(Vector((xc - 0.002 + j * 0.0045 + 0.004 * t, Rw * math.cos(a), Rw * math.sin(a))))
            a_e = a_s + 3 * PI
            tang = Vector((0.0, -math.sin(a_e), math.cos(a_e)))
            radial = Vector((0.0, math.cos(a_e), math.sin(a_e)))
            pts.append(pts[-1] + tang * 0.011 + radial * 0.006 + Vector((0.002, 0, 0)))
            mb.tube([tuple(p) for p in pts], rb, seg=6, mat="galvanized")
    return mb


def _add_barbed(mb, p0, p1):
    """Cordón de púas recto de p0 a p1 con módulos de 8 púas (+ 4) escalados < 13 % para ajustar el largo."""
    p0, p1 = Vector(p0), Vector(p1)
    Ls = (p1 - p0).length
    half = 4 * BARB_P
    units = max(1, int(round(Ls / half)))
    sc = Ls / (units * half)
    F = frame_x(p0, p1)
    x = 0.0
    for _ in range(units // 2):
        mb.add_inst("barb8", lambda: barbed_module(8), F @ _T(x, 0, 0) @ Matrix.Diagonal((sc, 1, 1, 1)))
        x += 2 * half * sc
    if units % 2:
        mb.add_inst("barb4", lambda: barbed_module(4), F @ _T(x, 0, 0) @ Matrix.Diagonal((sc, 1, 1, 1)))


def post_tie(R):
    """Amarre de aluminio 9 ga a poste de radio R: engancha un alambre de la tela, rodea el poste por detrás (+Y) y regresa
    con la cola torcida. Local: poste en el origen (eje Z), tela en y = Y_FAB."""
    mb = MB()
    rt = 0.0019
    Rt = R + rt + 0.0004
    yf = Y_FAB
    pts = [Vector((-R - 0.010, yf - 0.006, -0.004)), Vector((-R - 0.012, yf - 0.002, 0.0)), Vector((-R - 0.008, yf + 0.003, 0.001))]
    yc = yf + 0.004
    xc = math.sqrt(max(Rt ** 2 - yc ** 2, 1e-8))
    al = math.atan2(yc, -xc) + 2 * PI                  # ~ 200° (lado -X), recorre por +Y hasta ~ -20° (lado +X)
    ar = math.atan2(yc, xc)
    n = 14
    for i in range(n + 1):
        a = al - (al - ar) * i / n
        pts.append(Vector((Rt * math.cos(a), Rt * math.sin(a), 0.001 + 0.0012 * math.sin(PI * i / n))))
    pts += [Vector((R + 0.008, yf + 0.003, 0.001)), Vector((R + 0.012, yf - 0.002, 0.0)), Vector((R + 0.010, yf - 0.006, -0.004)),
            Vector((R + 0.006, yf - 0.004, -0.009)), Vector((R + 0.004, yf + 0.001, -0.013))]
    mb.tube([tuple(p) for p in _dedupe(pts)], rt, seg=6, mat="aluminium")
    return mb


def rail_tie(Rr):
    """Amarre de aluminio al larguero superior: rodea el larguero (eje X local en el origen) por arriba y por detrás y
    engancha la tela por debajo. Local: larguero en el origen, tela en y = Y_FAB - Y_RAIL."""
    mb = MB()
    rt = 0.0019
    Rt = Rr + rt + 0.0004
    yf = Y_FAB - Y_RAIL
    pts = [Vector((-0.006, yf - 0.005, -Rr - 0.020)), Vector((-0.004, yf + 0.0005, -Rr - 0.015))]
    n = 16
    a0 = math.radians(-120)
    for i in range(n + 1):
        a = a0 - math.radians(300) * i / n            # vuelta por -Y, arriba, +Y y abajo
        pts.append(Vector((-0.003 + 0.006 * i / n, Rt * math.cos(a), Rt * math.sin(a))))
    pts += [Vector((0.004, yf + 0.0005, -Rr - 0.015)), Vector((0.006, yf - 0.005, -Rr - 0.021)),
            Vector((0.003, yf - 0.002, -Rr - 0.027))]
    mb.tube([tuple(p) for p in _dedupe(pts)], rt, seg=6, mat="aluminium")
    return mb


def hog_ring():
    """Anillo de cerdo (hog ring) 11 ga que une el nudo inferior de la tela con el alambre tensor. Local: alambre tensor en el
    origen a lo largo de X; la tela queda en y = Y_FAB - Y_TW."""
    mb = MB()
    yf = Y_FAB - Y_TW
    c = Vector((0.0, yf / 2, 0.0))
    Rr = abs(yf) / 2 + 0.003
    pts = []
    for i in range(13):
        a = math.radians(-150 + 300 * i / 12)
        pts.append(c + Vector((0.0, Rr * math.cos(a), Rr * math.sin(a) * 0.9)))
    mb.tube([tuple(p) for p in pts], 0.0015, seg=6, mat="galvanized")
    return mb


def tension_band(R, sd=1):
    """Abrazadera de tensión (fleje 3/4" × 12 ga) que abraza un poste de radio R (en el origen) y aprieta con perno de carruaje
    la barra de tensión en (sd·(R + 0.0155), Y_FAB): una oreja por delante y otra por detrás de la barra. sd = ±1: lado del
    poste hacia el que corre la tela."""
    mb = MB()
    t, w = 0.0027, 0.019
    Rb = R + t / 2 + 0.0003
    yfr = Y_FAB - 0.0024 - t / 2 - 0.0002            # oreja delantera (lado público)
    yrr = Y_FAB + 0.0024 + t / 2 + 0.0002            # oreja trasera (pegada al poste)
    xe = R + 0.0155 + 0.0095 + 0.012                  # punta de las orejas
    xr0 = math.sqrt(max(Rb ** 2 - yrr ** 2, 0.0)) if abs(yrr) < Rb else 0.004
    pts = [(xe, yfr, 0.0), (0.004, yfr, 0.0)]
    n = 22
    a1 = -2.5 * PI + math.atan2(yrr, xr0 + 0.002) + 2 * PI
    for i in range(n + 1):
        a = -PI / 2 - (-PI / 2 - a1) * i / n
        pts.append((Rb * math.cos(a), Rb * math.sin(a), 0.0))
    pts += [(xr0 + 0.004, yrr, 0.0), (xe, yrr, 0.0)]
    pts = [(sd * x, y, z) for (x, y, z) in _dedupe(fillet(pts, 0.003, 3))]
    if sd < 0:
        pts = list(reversed(pts))
    sweep_frame(mb, [(-t / 2, -w / 2), (t / 2, -w / 2), (t / 2, w / 2), (-t / 2, w / 2)], pts, "galvanized", up=(0, 0, 1))
    xb = sd * (xe - 0.0065)
    carriage_bolt(mb, _T(xb, yfr - t / 2, 0) @ _Rx(90), d=0.0095)
    mb.cyl((xb, yfr - t / 2, 0), (xb, yrr + t / 2 + 0.012, 0), 0.0045, seg=12, mat="galvanized", caps=True)
    hexnut(mb, _T(xb, yrr + t / 2, 0) @ _Rx(-90), s=0.0143, h=0.0085, mat="galvanized")
    return mb


def post_band(mb, x, y, z, R, ear_dir, ear_len=0.03, w=0.019, t=0.0027, bolt_d=0.0095):
    """Abrazadera de fleje (brace band / rail end band) alrededor de un poste vertical en (x, y), con dos orejas paralelas
    que salen en la dirección `ear_dir` (en planta) y un perno de carruaje entre ellas."""
    ang = math.atan2(ear_dir[1], ear_dir[0])
    M = _T(x, y, z) @ _Rz(math.degrees(ang))
    Rb = R + t / 2 + 0.0003
    g = 0.006
    a_s = math.asin(min(0.95, (g + t / 2) / Rb))
    pts = [(Rb + ear_len, g + t / 2, 0.0), (Rb * math.cos(a_s) + 0.002, g + t / 2, 0.0)]
    n = 22
    for i in range(n + 1):
        a = a_s + (2 * PI - 2 * a_s) * i / n
        pts.append((Rb * math.cos(a), Rb * math.sin(a), 0.0))
    pts += [(Rb * math.cos(a_s) + 0.002, -g - t / 2, 0.0), (Rb + ear_len, -g - t / 2, 0.0)]
    pts = [tuple(M @ Vector(p)) for p in _dedupe(fillet(pts, 0.003, 3))]
    sweep_frame(mb, [(-t / 2, -w / 2), (t / 2, -w / 2), (t / 2, w / 2), (-t / 2, w / 2)], pts, "galvanized", up=(0, 0, 1))
    xb = Rb + ear_len - 0.009
    carriage_bolt(mb, M @ _T(xb, g + t, 0) @ _Rx(-90), d=bolt_d)
    mb.cyl(M @ Vector((xb, g + t, 0)), M @ Vector((xb, -g - t - 0.01, 0)), bolt_d * 0.47, seg=12, mat="galvanized")
    hexnut(mb, M @ _T(xb, -g - t, 0) @ _Rx(90), s=bolt_d * 1.5, h=bolt_d * 0.85, mat="galvanized")


def sleeve(mb, M, r_in, r_out, L, mat="galvanized", ch=0.0015, seg=SEG):
    """Manga / copa tubular cerrada (pared real) de z = 0 a L sobre el eje Z local."""
    lathe(mb, [(r_in, 0.0), (r_out - ch, 0.0), (r_out, ch), (r_out, L - ch), (r_out - ch, L), (r_in, L)], seg=seg, mat=mat, M=M,
          closed=True)


ARM_PROF = [(-0.016, 0.0), (-0.016, -0.012), (-0.0135, -0.012), (-0.0135, -0.0025), (0.0135, -0.0025), (0.0135, -0.012),
            (0.016, -0.012), (0.016, 0.0)]


def _arm(mb, base, out=-1, L=0.345, clips=True):
    """Brazo de púas de lámina prensada (canal 32 × 12 mm) a 45° hacia `out`·Y desde `base`, con remate redondeado y 3 grapas.
    Devuelve las posiciones de los 3 hilos."""
    base = Vector(base)
    d = Vector((0.0, out * math.cos(PI / 4), math.sin(PI / 4)))
    up = Vector((0.0, -out * math.sin(PI / 4), math.cos(PI / 4)))
    tip = base + d * L
    sweep_frame(mb, ARM_PROF, [tuple(base), tuple(tip)], "galvanized", up=tuple(up))
    lathe(mb, [(0.0, -0.012), (0.016, -0.012), (0.016, 0.0), (0.0, 0.0)], seg=SEG, mat="galvanized",
          M=frame_x(tip, tip + Vector((1, 0, 0)), up=tuple(up)) @ _Ry(0))
    strands = []
    for s in (L - 0.23, L - 0.125, L - 0.02):
        p = base + d * s
        c = p + up * 0.0013 + up * 0.0013
        strands.append(c + up * 0.0022)
        if clips:                                     # grapa en J que abraza el hilo sobre la muesca
            Mc = frame_x(c, c + d, up=tuple(up))
            ring(mb, Mc @ _T(0, 0, 0.0022), 0.0040, 0.0011, n=10, seg=6, a0=-0.25, a1=PI + 0.25)
    return strands


def _barb_arm_line(mb, x, zp, R, out=-1):
    """Brazo de púas para poste de línea: copa sobre el tope del poste, ojo por donde pasa el larguero y brazo a 45°."""
    rr = R + 0.0028
    lathe(mb, [(R + 0.0006, zp - 0.050), (rr, zp - 0.049), (rr + 0.0012, zp - 0.044), (rr, zp - 0.038), (rr, zp + 0.002),
               (rr * 0.8, zp + 0.008), (rr * 0.4, zp + 0.010), (0.0, zp + 0.0105)], seg=SEG, mat="galvanized", M=_T(x, 0, 0), caps=False)
    zr = zp + 0.010 + R_RAIL + 0.002
    sleeve(mb, _T(x - 0.017, Y_RAIL, zr) @ _Ry(90), R_RAIL + 0.0012, R_RAIL + 0.0050, 0.034)
    rbox(mb, (x - 0.012, Y_RAIL + R_RAIL * 0.3, zp - 0.004), (x + 0.012, R * 0.5, zp + 0.013), "galvanized", r=0.003)
    base = (x, Y_RAIL - R_RAIL - 0.003, zr + 0.003)
    return _arm(mb, base, out)


def _terminal(mb, x, sd, R, z_b, z_top, zr, zt, lean=0.0, x_brace=None, R_brace=R_LINE, fabric=True, brace=True):
    """Poste terminal completo en x (la tela corre hacia sd·X): dado, tubo, domo, abrazaderas, copa del larguero, barra de
    tensión, brazo de púas con amarres, riostra + tirante con tensor al poste vecino en x_brace. Devuelve hilos (3 × Vector)."""
    footing(mb, x, 0.0, R, 0.2)
    pipe(mb, (x, 0, -0.05), (x + lean, 0, zt), R, caps=False)
    dome_cap(mb, x + lean, 0, zt, R)
    # copa del larguero sostenida por abrazadera
    xe = x + sd * (R + 0.006)
    sleeve(mb, _T(xe, Y_RAIL, zr) @ _Ry(90 * sd), R_RAIL + 0.0016, R_RAIL + 0.0042, 0.05)
    lathe(mb, [(0.0, -0.004), (R_RAIL + 0.0042, -0.004), (R_RAIL + 0.0042, 0.0), (0.0, 0.0)], seg=SEG, mat="galvanized",
          M=_T(xe, Y_RAIL, zr) @ _Ry(90 * sd))
    post_band(mb, x, 0.0, zr, R, (sd * 0.6, Y_RAIL / 0.05 * 0.8, 0), ear_len=0.012)
    if fabric:
        xb = x + sd * (R + 0.0155)
        rbox(mb, (xb - 0.0095, Y_FAB - 0.0024, z_b - 0.012), (xb + 0.0095, Y_FAB + 0.0024, z_top - 0.006), "galvanized", r=0.0012)
        for k in range(7):
            zb_ = z_b + 0.16 + (z_top - z_b - 0.4) * k / 6
            mb.add_inst(f"tband{int(R * 1e4)}{'r' if sd > 0 else 'l'}", lambda R=R, sd=sd: tension_band(R, sd), _T(x, 0, zb_))
    if brace and x_brace is not None:                 # riostra horizontal + tirante de 3/8" con tensor
        zbr = (z_b + zr) / 2
        pipe(mb, (x + sd * (R + 0.008), 0.0, zbr), (x_brace - sd * (R_brace + 0.008), 0.0, zbr), R_RAIL)
        for xx, RR, dd in ((x, R, sd), (x_brace, R_brace, -sd)):
            sleeve(mb, _T(xx + dd * (RR + 0.004), 0, zbr) @ _Ry(90 * dd), R_RAIL + 0.0016, R_RAIL + 0.0042, 0.04)
            post_band(mb, xx, 0.0, zbr, RR, (dd, 0.35, 0), ear_len=0.01)
        pa = Vector((x_brace - sd * (R_brace + 0.008), 0.014, zbr - 0.03))
        pb = Vector((x + sd * (R + 0.008), 0.014, z_b + 0.10))
        dv = (pb - pa).normalized()
        mid = pa.lerp(pb, 0.45)
        wire(mb, [pa, mid - dv * 0.08], 0.0048)
        wire(mb, [mid + dv * 0.08, pb], 0.0048)
        for pp, RR, xx in ((pa, R_brace, x_brace), (pb, R, x)):     # orejas del tirante abrazadas al poste
            post_band(mb, xx, 0.0, pp.z, RR, (0.0, 1.0, 0), ear_len=0.012)
        Mtb = frame_x(mid - dv * 0.085, mid + dv * 0.085, up=(0, 1, 0))
        for sy in (-1, 1):                            # tensor: cuerpo de dos barras forjadas y dos tuercas hexagonales
            rbox(mb, (0.018, sy * 0.0068 - 0.0026, -0.0032), (0.152, sy * 0.0068 + 0.0026, 0.0032), "galvanized", r=0.0012, m=Mtb)
        for xx in (0.009, 0.161):
            lathe(mb, [(0.0045, -0.009), (0.0098, -0.009), (0.0098, 0.009), (0.0045, 0.009)], seg=6, mat="galvanized",
                  M=Mtb @ _T(xx, 0, 0) @ _Ry(90), closed=True, phase=PI / 6)
            lathe(mb, [(0.0095, -0.009), (0.0095, 0.009), (0.007, 0.009), (0.007, -0.009)], seg=12, mat="galvanized",
                  M=Mtb @ _T(xx + (0.004 if xx < 0.1 else -0.004), 0, 0) @ _Ry(90), closed=True)
    # brazo de púas de terminal: abrazadera + brazo; amarre de cada hilo
    zab = zt - 0.035
    lathe(mb, [(R + 0.0006, zab - 0.032), (R + 0.0038, zab - 0.030), (R + 0.0038, zab + 0.030), (R + 0.0006, zab + 0.032)],
          seg=SEG, mat="galvanized", M=_T(x + lean, 0, 0), caps=False)
    sts = _arm(mb, (x + lean, -R - 0.003, zab + 0.004), -1, L=0.36, clips=False)
    for p in sts:                                     # vuelta del hilo alrededor del brazo + cola enrollada sobre el hilo
        dd = Vector((0.0, -math.cos(PI / 4), math.sin(PI / 4)))
        upv = Vector((0.0, math.sin(PI / 4), math.cos(PI / 4)))
        ring(mb, frame_x(p - upv * 0.0075, p - upv * 0.0075 + dd, up=(1, 0, 0)), 0.0105, 0.0013, n=16, seg=6)
        pts = [p + Vector((sd * (0.014 + 0.05 * t), 0.0029 * math.cos(9 * PI * t), 0.0029 * math.sin(9 * PI * t)))
               for t in [j / 26 for j in range(27)]]
        wire(mb, pts, 0.0012, seg=6)
    return sts


def fence_run(L=3.05, h=2.4, seed=0, end_posts=True, fabric="instance"):
    """Tramo de malla ciclónica de seguridad a lo largo de +X de x = 0 a x = L (origen: piso, eje de los postes en y = 0).
    Lado público / exterior = -Y: la tela va por la cara -Y de los postes y los brazos de púas se inclinan 45° hacia -Y; el
    recinto queda en +Y (armar el perímetro en sentido antihorario visto desde arriba).
    Construcción (ASTM F1083/F668, catálogos de herrajes): postes de línea 2-3/8" OD a <= 3,05 m y terminales 2-7/8" OD con
    tapón de domo, coronas de concreto de los dados; larguero superior 1-5/8" que pasa por los ojos de los brazos (copla
    cada 6,4 m); tela de 2" calibre 9 de `h` m (nudo abajo, orilla torcida con puntas arriba) a 5 cm del piso; alambre tensor
    inferior cal. 7; barras de tensión con abrazaderas en los terminales; riostra horizontal 1-5/8" y tirante de 3/8" con
    tensor al primer poste de línea; amarres de aluminio a postes (~35 cm) y larguero (60 cm), anillos de cerdo al tensor;
    brazos de 45° con 3 hilos de púas.
    end_posts=False: sin terminales (los postes en x = 0 y L son de línea; la tela llega hasta x = 0 y x = L).
    fabric: "instance" (por omisión; tela, púas, amarres y abrazaderas como instancias TEL_*), "join" (todo en la malla) o
    "none" (solo postes y largueros)."""
    r = rng(seed)
    mb = TelMB()
    nb = max(1, int(math.ceil(L / 3.05 - 1e-6)))
    xs = [L * i / nb for i in range(nb + 1)]
    z_b = 0.05
    n = int(round(h / CL_D))
    z_top = z_b + n * CL_D
    zr = z_top - 0.006
    zp = zr - R_RAIL - 0.012
    zt = zr + 0.05
    is_term = [end_posts and i in (0, nb) for i in range(nb + 1)]
    strand_pts = [[], [], []]
    leans = [float(r.uniform(-0.004, 0.004)) for _ in xs]
    for i, x in enumerate(xs):
        if is_term[i]:
            sd = 1 if i == 0 else -1
            j = i + sd
            sts = _terminal(mb, x, sd, R_TERM, z_b, z_top, zr, zt, lean=leans[i] * 0.4, x_brace=xs[j],
                            R_brace=R_TERM if is_term[j] else R_LINE, fabric=fabric != "none", brace=not (nb == 1 and i == nb))
        else:
            footing(mb, x, 0.0, R_LINE, 0.15)
            pipe(mb, (x, 0, -0.05), (x + leans[i], 0, zp), R_LINE, caps=False)
            sts = _barb_arm_line(mb, x + leans[i], zp, R_LINE)
            if fabric != "none":
                for k in range(7):
                    zz = z_b + 0.12 + (z_top - z_b - 0.3) * k / 6
                    mb.add_inst(f"ptie{int(R_LINE * 1e4)}", lambda: post_tie(R_LINE),
                                _T(x + leans[i] * zz / zp, 0, zz) @ _Rz(float(r.uniform(-3, 3))))
        for k in range(3):
            strand_pts[k].append(sts[k])
    xa = xs[0] + (R_TERM + 0.006 if is_term[0] else 0.0)
    xb_ = xs[-1] - (R_TERM + 0.006 if is_term[-1] else 0.0)
    pipe(mb, (xa, Y_RAIL, zr), (xb_, Y_RAIL, zr), R_RAIL, caps=True)
    xc = xa + 6.4
    while xc < xb_ - 0.2:
        sleeve(mb, _T(xc - 0.05, Y_RAIL, zr) @ _Ry(90), R_RAIL - 0.0004, R_RAIL + 0.0026, 0.1)
        xc += 6.4
    z_tw = z_b + 0.5 * CL_D
    ta = xs[0] + (R_TERM + R_TW if is_term[0] else 0.0)
    tb = xs[-1] - (R_TERM + R_TW if is_term[-1] else 0.0)
    wire(mb, [(ta, Y_TW, z_tw), (tb, Y_TW, z_tw)], R_TW, caps=not end_posts)
    for i in (0, nb):                                 # el tensor da vuelta al poste terminal y se enrolla sobre sí mismo
        if is_term[i]:
            sd = 1 if i == 0 else -1
            x = xs[i]
            Rw = R_TERM + R_TW + 0.0003
            a_in = math.atan2(Y_TW, sd * math.sqrt(max(Rw ** 2 - Y_TW ** 2, 0)))
            pts = []
            for j in range(19):
                a = a_in - sd * 2 * PI * j / 18 * 0.97
                pts.append((x + Rw * math.cos(a), Rw * math.sin(a), z_tw + 0.011 * j / 18))
            for j in range(16):
                t = j / 15
                pts.append((x + sd * (Rw + 0.02 + 0.05 * t), Y_TW + 0.0052 * math.cos(6 * PI * t) * min(1, 3 * t),
                            z_tw + 0.011 * (1 - t) + 0.0052 * math.sin(6 * PI * t) * min(1, 3 * t)))
            wire(mb, pts, R_TW * 0.95, seg=10)
    if fabric != "none":
        fx0 = xs[0] + (R_TERM + 0.0155 if is_term[0] else 0.0)
        fx1 = xs[-1] - (R_TERM + 0.0155 if is_term[-1] else 0.0)
        _add_fabric(mb, fx0, fx1, z_b, n, M=_T(0, Y_FAB, 0))
        x = xa + 0.3
        while x < xb_ - 0.1:
            mb.add_inst("rtie", lambda: rail_tie(R_RAIL), _T(x, Y_RAIL, zr))
            mb.add_inst("hog", hog_ring, _T(x + 0.15, Y_TW, z_tw))
            x += 0.6
        for k in range(3):
            _add_barbed(mb, strand_pts[k][0], strand_pts[k][-1])
    if fabric == "join":
        mb.realize()
    return mb
