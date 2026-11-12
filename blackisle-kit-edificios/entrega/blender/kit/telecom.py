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
from kit.clinic_equipo import text as _ce_text
from kit.clinic_servicios import hexnut, holed, lathe, louver_grille, rr_pts, rrframe, screw, skin, slab  # noqa: F401

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
KNUCKLE = (-0.075, 0.0, 0.075)   # muestras por nudo del picket (3: ~4 800 tris por par de pickets de 2,4 m)
RES = 3                          # resolución de curva del texto en relieve de los letreros
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
def label(mb, s, size, mat, M, depth=0.0012, align="CENTER", bold=False, res=2):
    """Texto en relieve sobre una superficie (M: XY local sobre la cara, +Z afuera): sobresale `depth` (>= 1 mm) y se hunde
    0,3 mm; sin la cara trasera de las letras (queda dentro de la placa y nunca se ve)."""
    return _ce_text(mb, s, size, depth + 0.0003, mat, M @ _T(0, 0, -0.0003), align=align, bold=bold, res=res, back=False)


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
    if seg <= 8:
        washer = False
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
    prof = [(rr * 0.92, zt - 0.001), (rr, zt + 0.001)]
    for k in range(2):                                # hilos visibles de rosca sobre la tuerca, punta con chaflán
        z = zt + proud * (0.35 + 0.3 * k)
        prof += [(rr, z - 0.0012), (rr * 0.88, z), (rr, z + 0.0012)]
    prof += [(rr, zt + proud - 0.0015), (rr * 0.82, zt + proud), (0.0, zt + proud)]
    lathe(mb, prof, seg=seg, mat=mat, M=M, caps=True)


def carriage_bolt(mb, M, d=0.0095, mat="galvanized", seg=12):
    """Cabeza de domo de perno de carruaje (z = 0 = superficie)."""
    lathe(mb, [(d * 1.05, -0.0003), (d * 1.05, d * 0.12), (d * 0.8, d * 0.42), (0.0, d * 0.58)], seg=seg, mat=mat, M=M)


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


def footing(mb, x, y, r_post, r_foot, crown=0.035, mat="concrete", seg=SEG, seed=None):
    """Corona de concreto del dado colado alrededor de un poste: domo allanado a cuchara que escurre el agua, borde irregular
    que muere en el piso (se entierra 5 cm)."""
    k = (seed if seed is not None else int(abs(x) * 1000 + abs(y) * 777)) % 997
    ph = [0.37 * k, 1.13 * k, 2.07 * k]
    rm = (lambda i, a, rr, z: rr * (1.0 + (0.045 * math.sin(2 * a + ph[0]) + 0.03 * math.sin(3 * a + ph[1]) + 0.02 * math.sin(5 * a + ph[2]))
                                     * (1.0 if i <= 2 else 0.0)))
    lathe(mb, [(r_foot * 1.02, -0.05), (r_foot, -0.002), (r_foot * 0.93, crown * 0.32), (r_foot * 0.78, crown * 0.66),
               (r_foot * 0.55, crown * 0.88), (r_post + 0.012, crown), (r_post + 0.0015, crown * 0.97)], seg=seg, mat=mat,
          M=_T(x, y, 0.0), caps=False, rmod=rm)


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
        for du in KNUCKLE:
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
    npts = turns * 6
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
            for i in range(8):
                t = i / 7
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
    pts = [Vector((-R - 0.0065, yf - 0.002, -0.0075)), Vector((-R - 0.009, yf - 0.0055, -0.004)), Vector((-R - 0.011, yf - 0.002, 0.0)),
           Vector((-R - 0.008, yf + 0.003, 0.001))]
    yc = yf + 0.004
    xc = math.sqrt(max(Rt ** 2 - yc ** 2, 1e-8))
    al = math.atan2(yc, -xc) + 2 * PI                  # ~ 200° (lado -X), recorre por +Y hasta ~ -20° (lado +X)
    ar = math.atan2(yc, xc)
    n = 14
    for i in range(n + 1):
        a = al - (al - ar) * i / n
        pts.append(Vector((Rt * math.cos(a), Rt * math.sin(a), 0.001 + 0.0012 * math.sin(PI * i / n))))
    pts += [Vector((R + 0.008, yf + 0.003, 0.001)), Vector((R + 0.011, yf - 0.002, 0.0)), Vector((R + 0.009, yf - 0.0055, -0.004)),
            Vector((R + 0.0065, yf - 0.002, -0.0075))]
    mb.tube([tuple(p) for p in _dedupe(pts)], rt, seg=6, mat="aluminium")
    return mb


def rail_tie(Rr, yf=None):
    """Amarre de aluminio al larguero superior: rodea el larguero (eje X local en el origen) por arriba y por detrás y
    engancha la tela por debajo. Local: larguero en el origen, tela en y = Y_FAB - Y_RAIL."""
    mb = MB()
    rt = 0.0019
    Rt = Rr + rt + 0.0004
    yf = (Y_FAB - Y_RAIL) if yf is None else yf
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


def tension_band(R, sd=1, yfab=None):
    """Abrazadera de tensión (fleje 3/4" × 12 ga) que abraza un poste de radio R (en el origen) y aprieta con perno de carruaje
    la barra de tensión en (sd·(R + 0.0155), Y_FAB): una oreja por delante y otra por detrás de la barra. sd = ±1: lado del
    poste hacia el que corre la tela."""
    mb = MB()
    t, w = 0.0027, 0.019
    Rb = R + t / 2 + 0.0003
    yfab = Y_FAB if yfab is None else yfab
    yfr = yfab - 0.0024 - t / 2 - 0.0002             # oreja delantera (lado público)
    yrr = yfab + 0.0024 + t / 2 + 0.0002             # oreja trasera (pegada al poste)
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
    pts = [(Rb + ear_len, g + t / 2, 0.0), (Rb * math.cos(a_s) + 0.003, g + t / 2, 0.0)]
    n = 14
    for i in range(n + 1):
        a = a_s + (2 * PI - 2 * a_s) * i / n
        pts.append((Rb * math.cos(a), Rb * math.sin(a), 0.0))
    pts += [(Rb * math.cos(a_s) + 0.003, -g - t / 2, 0.0), (Rb + ear_len, -g - t / 2, 0.0)]
    pts = [tuple(M @ Vector(p)) for p in _dedupe(pts)]
    sweep_frame(mb, [(-t / 2, -w / 2), (t / 2, -w / 2), (t / 2, w / 2), (-t / 2, w / 2)], pts, "galvanized", up=(0, 0, 1))
    xb = Rb + ear_len - 0.009
    carriage_bolt(mb, M @ _T(xb, g + t, 0) @ _Rx(-90), d=bolt_d)
    mb.cyl(M @ Vector((xb, g + t, 0)), M @ Vector((xb, -g - t - 0.01, 0)), bolt_d * 0.47, seg=8, mat="galvanized")
    hexnut(mb, M @ _T(xb, -g - t, 0) @ _Rx(90), s=bolt_d * 1.5, h=bolt_d * 0.85, mat="galvanized")


def sleeve(mb, M, r_in, r_out, L, mat="galvanized", ch=0.0015, seg=SEG, inner=True):
    """Manga / copa tubular (cantos con chaflán) de z = 0 a L sobre el eje Z local. inner=False omite la pared interior (el
    tubo que abraza la tapa)."""
    lathe(mb, [(r_in, 0.0), (r_out, ch), (r_out, L - ch), (r_in, L)], seg=seg, mat=mat, M=M, closed=inner, caps=False)


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
            ring(mb, Mc @ _T(0, 0, 0.0022), 0.0040, 0.0011, n=8, seg=6, a0=-0.25, a1=PI + 0.25)
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


def _terminal(mb, x, sd, R, z_b, z_top, zr, zt, lean=0.0, x_brace=None, R_brace=R_LINE, fabric=True, brace=True, rail=True,
              foot=0.2):
    """Poste terminal completo en x (la tela corre hacia sd·X): dado, tubo, domo, abrazaderas, copa del larguero, barra de
    tensión, brazo de púas con amarres, riostra + tirante con tensor al poste vecino en x_brace. Devuelve hilos (3 × Vector)."""
    footing(mb, x, 0.0, R, foot)
    pipe(mb, (x, 0, -0.05), (x + lean, 0, zt), R, caps=False)
    dome_cap(mb, x + lean, 0, zt, R)
    if rail:                                          # copa del larguero sostenida por abrazadera
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
        pa = Vector((x_brace - sd * (R_brace + 0.024), 0.0, zbr - 0.016))
        pb = Vector((x + sd * (R + 0.008), 0.014, z_b + 0.10))
        dv = (pb - pa).normalized()
        mid = pa.lerp(pb, 0.45)
        wire(mb, [pa, mid - dv * 0.08], 0.0048)
        wire(mb, [mid + dv * 0.08, pb], 0.0048)
        post_band(mb, x, 0.0, pb.z, R, (0.0, 1.0, 0), ear_len=0.012)   # el tirante remata en una abrazadera al pie del terminal
        ring(mb, frame_x(pa, pa + Vector((0, 1, 0)), up=(1, 0, 0)) @ _T(0, 0, 0), 0.008, 0.0042, n=12, seg=8)   # ojo al perno
        Mtb = frame_x(mid - dv * 0.085, mid + dv * 0.085, up=(0, 1, 0))
        for sy in (-1, 1):                            # tensor: cuerpo de dos barras forjadas y dos tuercas hexagonales
            mb.box((0.018, sy * 0.0068 - 0.0026, -0.0032), (0.152, sy * 0.0068 + 0.0026, 0.0032), "galvanized", bevel=0.0012, seg=1,
                   m=Mtb)
        for xx in (0.009, 0.161):
            lathe(mb, [(0.0045, -0.009), (0.0098, -0.0082), (0.0098, 0.0082), (0.0045, 0.009)], seg=6, mat="galvanized",
                  M=Mtb @ _T(xx, 0, 0) @ _Ry(90), closed=True, phase=PI / 6)
    # brazo de púas de terminal: abrazadera + brazo; amarre de cada hilo
    zab = zt - 0.035
    lathe(mb, [(R + 0.0006, zab - 0.032), (R + 0.0038, zab - 0.030), (R + 0.0038, zab + 0.030), (R + 0.0006, zab + 0.032)],
          seg=SEG, mat="galvanized", M=_T(x + lean, 0, 0), caps=False)
    sts = _arm(mb, (x + lean, -R - 0.003, zab + 0.004), -1, L=0.36, clips=False)
    for p in sts:                                     # vuelta del hilo alrededor del brazo + cola enrollada sobre el hilo
        dd = Vector((0.0, -math.cos(PI / 4), math.sin(PI / 4)))
        upv = Vector((0.0, math.sin(PI / 4), math.cos(PI / 4)))
        ring(mb, frame_x(p - upv * 0.0075, p - upv * 0.0075 + dd, up=(1, 0, 0)), 0.0105, 0.0013, n=12, seg=6)
        pts = [p + Vector((sd * (0.014 + 0.035 * t), 0.0029 * math.cos(6 * PI * t), 0.0029 * math.sin(6 * PI * t)))
               for t in [j / 12 for j in range(13)]]
        wire(mb, pts, 0.0012, seg=6)
    return sts


def _term_arm_strands(x, R, zt):
    """Posiciones de los 3 hilos en el brazo de un poste terminal / de puerta (mismo cálculo que _terminal/_arm)."""
    zab = zt - 0.035
    base = Vector((x, -R - 0.003, zab + 0.004))
    d = Vector((0.0, -math.cos(PI / 4), math.sin(PI / 4)))
    up = Vector((0.0, math.sin(PI / 4), math.cos(PI / 4)))
    return [base + d * s + up * 0.0048 for s in (0.36 - 0.23, 0.36 - 0.125, 0.36 - 0.02)]


def fence_levels(h=2.4):
    """Alturas compartidas por cerca y puerta: (z_b, n, z_top, zr, zp, zt)."""
    z_b = 0.05
    n = int(round(h / CL_D))
    z_top = z_b + n * CL_D
    zr = z_top - 0.006
    return z_b, n, z_top, zr, zr - R_RAIL - 0.012, zr + 0.05


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
    end_posts: True / False o (inicio, fin) con True = terminal, False = poste de línea (la tela sigue hasta x = 0 / L) y
    None = sin poste: el extremo remata en un poste de puerta 4" de `fence_gate` centrado en ese x (tela, larguero, tensor e
    hilos llegan a su barra de tensión, su copa y su brazo).
    fabric: "instance" (por omisión; tela, púas, amarres y abrazaderas como instancias TEL_*), "join" (todo en la malla) o
    "none" (solo postes y largueros)."""
    r = rng(seed)
    mb = TelMB()
    nb = max(1, int(math.ceil(L / 3.05 - 1e-6)))
    xs = [L * i / nb for i in range(nb + 1)]
    z_b, n, z_top, zr, zp, zt = fence_levels(h)
    ep = tuple(end_posts) if isinstance(end_posts, (tuple, list)) else (bool(end_posts), bool(end_posts))
    is_term = [(i == 0 and ep[0] is True) or (i == nb and ep[1] is True) for i in range(nb + 1)]
    is_none = [(i == 0 and ep[0] is None) or (i == nb and ep[1] is None) for i in range(nb + 1)]
    strand_pts = [[], [], []]
    leans = [float(r.uniform(-0.004, 0.004)) for _ in xs]
    for i, x in enumerate(xs):
        if is_none[i]:                                # el poste lo pone fence_gate: hilos a su brazo
            sts = _term_arm_strands(x, R_GATEPOST, zt)
        elif is_term[i]:
            sd = 1 if i == 0 else -1
            j = i + sd
            sts = _terminal(mb, x, sd, R_TERM, z_b, z_top, zr, zt, lean=leans[i] * 0.4, x_brace=xs[j],
                            R_brace=R_TERM if is_term[j] else R_LINE, fabric=fabric != "none",
                            brace=not (nb == 1 and i == nb and is_term[0]) and not is_none[j])
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
    def off(i, k):
        return (R_TERM + k) if is_term[i] else ((R_GATEPOST + k) if is_none[i] else 0.0)
    xa = xs[0] + off(0, 0.006)
    xb_ = xs[-1] - off(nb, 0.006)
    pipe(mb, (xa, Y_RAIL, zr), (xb_, Y_RAIL, zr), R_RAIL, caps=True)
    xc = xa + 6.4
    while xc < xb_ - 0.2:
        sleeve(mb, _T(xc - 0.05, Y_RAIL, zr) @ _Ry(90), R_RAIL - 0.0004, R_RAIL + 0.0026, 0.1)
        xc += 6.4
    z_tw = z_b + 0.5 * CL_D
    ta = xs[0] + off(0, R_TW)
    tb = xs[-1] - off(nb, R_TW)
    wire(mb, [(ta, Y_TW, z_tw), (tb, Y_TW, z_tw)], R_TW, caps=True)
    for i in (0, nb):                                 # el tensor da vuelta al poste terminal y se enrolla sobre sí mismo
        if is_term[i]:
            sd = 1 if i == 0 else -1
            x = xs[i]
            Rw = R_TERM + R_TW + 0.0003
            a_in = math.atan2(Y_TW, sd * math.sqrt(max(Rw ** 2 - Y_TW ** 2, 0)))
            pts = []
            for j in range(12):
                a = a_in - sd * 2 * PI * j / 11 * 0.97
                pts.append((x + Rw * math.cos(a), Rw * math.sin(a), z_tw + 0.011 * j / 11))
            for j in range(9):
                t = j / 8
                pts.append((x + sd * (Rw + 0.02 + 0.05 * t), Y_TW + 0.0052 * math.cos(6 * PI * t) * min(1, 3 * t),
                            z_tw + 0.011 * (1 - t) + 0.0052 * math.sin(6 * PI * t) * min(1, 3 * t)))
            wire(mb, pts, R_TW * 0.95, seg=8)
    if fabric != "none":
        fx0 = xs[0] + off(0, 0.0155)
        fx1 = xs[-1] - off(nb, 0.0155)
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


# ============================================================================================================ puerta
def chain_link():
    """Eslabón de cadena galvanizada de 6 mm (paso interior 28 mm, ancho interior 12 mm) a lo largo de X local."""
    mb = MB()
    rw, hl, hw = 0.003, 0.014, 0.006 + 0.003
    pts = []
    for k in range(8):
        a = -PI / 2 + PI * k / 7
        pts.append(Vector((hl - hw + hw * math.cos(a), hw * math.sin(a), 0.0)))
    for k in range(8):
        a = PI / 2 + PI * k / 7
        pts.append(Vector((-hl + hw + hw * math.cos(a), hw * math.sin(a), 0.0)))
    from kit.clinic_equipo import loop_tube
    loop_tube(mb, [tuple(p) for p in pts], rw, seg=SEG_T, mat="galvanized", normal=(0, 0, 1))
    return mb


def _chain(mb, pts, closed=False, M=None):
    """Cadena de eslabones instanciados (alternados 90°) a paso constante a lo largo de una polilínea."""
    P = [Vector(p) for p in pts] + ([Vector(pts[0])] if closed else [])
    acc = [0.0]
    for i in range(1, len(P)):
        acc.append(acc[-1] + (P[i] - P[i - 1]).length)
    pitch = 0.0255
    n = max(1, int(acc[-1] / pitch))

    def at(sv):
        i = next((k for k in range(1, len(acc)) if acc[k] >= sv), len(acc) - 1)
        t = (sv - acc[i - 1]) / max(acc[i] - acc[i - 1], 1e-9)
        return P[i - 1].lerp(P[i], t)

    for k in range(n):
        a_, b_ = at(k * pitch), at(min((k + 1) * pitch, acc[-1]))
        c = (a_ + b_) / 2
        d = (b_ - a_).normalized()
        F = frame_x(c, c + d, up=(0, 0, 1) if abs(d.z) < 0.9 else (1, 0, 0)) @ _Rx(90 * (k % 2))
        mb.add_inst("chain6", chain_link, (M @ F) if M is not None else F)


def padlock(mb, M):
    """Candado de acero laminado de 50 mm: cuerpo de 8 láminas con juntas, arco de 8 mm, bocallave abajo. Origen: centro del
    arco arriba (por donde cuelga); cuerpo hacia -Z, frente hacia -Y local."""
    w, d, hb = 0.050, 0.026, 0.040
    loops = []
    z = -0.018
    nl = 7
    loops.append([(x, y, z) for (x, y) in rr_pts(w - 0.0016, d - 0.0016, 0.0052, n=3)])
    for k in range(nl + 1):                          # láminas: cara recta + junta rehundida 0,6 mm entre lámina y lámina
        zz = z - 0.0008 - (hb - 0.0016) * k / nl
        ins = 0.0006 if 0 < k < nl else 0.0
        loops.append([(x, y, zz) for (x, y) in rr_pts(w - 2 * ins, d - 2 * ins, 0.006 - ins, n=3)])
    loops.append([(x, y, z - hb) for (x, y) in rr_pts(w - 0.0016, d - 0.0016, 0.0052, n=3)])
    skin(mb, loops, "steel", M)
    for sx in (-1, 1):                               # remaches de las esquinas
        for zz in (z - 0.006, z - hb + 0.006):
            lathe(mb, [(0.0026, 0.0), (0.0026, 0.0006), (0.0012, 0.0011), (0.0, 0.0012)], seg=10, mat="steel",
                  M=M @ _T(sx * 0.019, -d / 2, zz) @ _Rx(90))
    # arco (grillete) de 8 mm
    pts = [(-0.0145, 0, z - 0.004), (-0.0145, 0, -0.006)]
    for k in range(1, 10):
        a = PI - PI * k / 10
        pts.append((0.0145 * math.cos(a), 0, -0.006 + 0.0145 * math.sin(a)))
    pts += [(0.0145, 0, -0.006), (0.0145, 0, z - 0.004)]
    mb.tube([tuple(M @ Vector(p)) for p in pts], 0.004, seg=SEG_T, mat="steel")
    mb.box((-0.0012, -0.004, z - hb - 0.0006), (0.0012, 0.004, z - hb + 0.001), "cable", bevel=0.0, m=M)


def _truss(mb, pa, pb, r=0.0048):
    """Tirante de 3/8" con tensor de cuerpo abierto en su punto medio."""
    pa, pb = Vector(pa), Vector(pb)
    dv = (pb - pa).normalized()
    mid = pa.lerp(pb, 0.5)
    wire(mb, [pa, mid - dv * 0.08], r)
    wire(mb, [mid + dv * 0.08, pb], r)
    up = Vector((0, 1, 0)) if abs(dv.y) < 0.9 else Vector((1, 0, 0))
    Mtb = frame_x(mid - dv * 0.085, mid + dv * 0.085, up=tuple(up))
    for sy in (-1, 1):
        mb.box((0.018, sy * 0.0068 - 0.0026, -0.0032), (0.152, sy * 0.0068 + 0.0026, 0.0032), "galvanized", bevel=0.0012, seg=1, m=Mtb)
    for xx in (0.009, 0.161):
        lathe(mb, [(0.0045, -0.009), (0.0098, -0.0082), (0.0098, 0.0082), (0.0045, 0.009)], seg=6, mat="galvanized",
              M=Mtb @ _T(xx, 0, 0) @ _Ry(90), closed=True, phase=PI / 6)


def _weld_ring(mb, M, R, r=0.0024, n=SEG):
    """Cordón de soldadura alrededor de un tubo de radio R, en el plano z = 0 local."""
    ring(mb, M, R + r * 0.35, r, mat="galvanized", n=n, seg=5)


def _weld_mb(R):
    mb = MB()
    _weld_ring(mb, Matrix(), R)
    return mb


def _band_mb(R, ear_len=0.012):
    """Abrazadera de fleje (post_band) suelta: poste de radio R en el origen, orejas hacia +X (para instanciar)."""
    mb = MB()
    post_band(mb, 0.0, 0.0, 0.0, R, (1.0, 0.0, 0.0), ear_len=ear_len)
    return mb


def hinge_leaf_part():
    """Bisagra industrial de 180°, mitad de la hoja: collar partido al montante 1-7/8" (eje en x = 0,05) con dos pernos
    pasados, alma fundida y barril de 33 mm alrededor del perno (eje en el origen). z = 0 = centro de la bisagra."""
    mb = MB()
    R = R_GFRAME
    lathe(mb, [(R + 0.0010, -0.030), (R + 0.0058, -0.028), (R + 0.0058, 0.028), (R + 0.0010, 0.030)], seg=SEG, mat="galvanized",
          M=_T(0.05, 0, 0), caps=False)
    rbox(mb, (0.010, -0.0065, -0.024), (0.05 - R - 0.002, 0.0065, 0.024), "galvanized", r=0.003)
    sleeve(mb, _T(0, 0, -0.025), 0.0099, 0.0165, 0.05)
    for zz in (-0.016, 0.016):
        carriage_bolt(mb, _T(0.05, -R - 0.0058, zz) @ _Rx(90), d=0.008)
        hexnut(mb, _T(0.05, R + 0.0058, zz) @ _Rx(-90), s=0.013, h=0.007, mat="galvanized")
    return mb


def hinge_post_part():
    """Bisagra industrial de 180°, mitad del poste: abrazadera de fleje al poste de 4" (eje en x = -(R + 0,032)) y bloque
    fundido con perno macizo de 3/4" (eje en el origen) sobre el que gira el barril. z = 0 = centro de la bisagra."""
    mb = MB()
    xp = -(R_GATEPOST + 0.032)
    post_band(mb, xp, 0.0, -0.045, R_GATEPOST, (1.0, 0.0, 0.0), ear_len=0.032 - 0.0027 - 0.011)
    rbox(mb, (-0.014, -0.012, -0.06), (0.014, 0.012, -0.026), "galvanized", r=0.004)
    lathe(mb, [(0.0095, -0.03), (0.0095, 0.03), (0.0075, 0.034), (0.0, 0.035)], seg=SEG_T, mat="galvanized", caps=False)
    return mb


def ext_clip():
    """Grapa de fleje atornillada a la extensión de un montante 1-7/8" que sostiene un hilo de púas (lado -Y)."""
    mb = MB()
    R = R_GFRAME
    pts = [(-0.014, -0.004, 0.0), (-0.014, -R - 0.0102, 0.0), (0.014, -R - 0.0102, 0.0), (0.014, -0.004, 0.0)]
    sweep_frame(mb, [(-0.0012, -0.007), (0.0012, -0.007), (0.0012, 0.007), (-0.0012, 0.007)], fillet(pts, 0.006, 2), "galvanized",
                up=(0, 0, 1))
    carriage_bolt(mb, _T(0, -R - 0.0114, 0.0) @ _Rx(90), d=0.006)
    return mb


def _leaf(lf, dirx, L, z_lb, z_lt, n_fab, latch="rod"):
    """Hoja de puerta en coordenadas de hoja: eje del perno de bisagra en el origen, la hoja se extiende hacia dirx·X.
    Marco soldado de tubo 1-7/8" (dos montantes con extensión para púas, travesaños arriba / medio / abajo con cordones de
    soldadura), tirante con tensor, tela con barras de tensión y amarres, 3 hilos de púas y el herraje de cierre `latch`:
    'rod' = barra de caída 5/8" con dos guías, collar y manija; 'fork' = horquilla que abraza el montante de la otra hoja."""
    R = R_GFRAME
    yfl = -(R + CL_E + CL_R + 0.0008)
    xh, xf = dirx * 0.05, dirx * L
    z_ext = z_lt + 0.40
    for x in (xh, xf):
        pipe(lf, (x, 0, z_lb - R - 0.004), (x, 0, z_ext), R, caps=False)
        lathe(lf, [(R, z_lb - R - 0.006), (R * 0.6, z_lb - R - 0.008), (0.0, z_lb - R - 0.0085)], seg=SEG, mat="galvanized",
              M=_T(x, 0, 0), caps=False)
        lathe(lf, [(R + 0.0012, z_ext - 0.025), (R + 0.0015, z_ext + 0.003), (R * 0.78, z_ext + 0.013), (0.0, z_ext + 0.0165)],
              seg=SEG, mat="galvanized", M=_T(x, 0, 0), caps=False)
    zm = (z_lb + z_lt) / 2
    for z in (z_lb, zm, z_lt):
        a, b = xh + dirx * R * 0.97, xf - dirx * R * 0.97
        pipe(lf, (a, 0, z), (b, 0, z), R, caps=False)
        lf.add_inst("weldgf", lambda: _weld_mb(R_GFRAME), _T(a + dirx * 0.0015, 0, z) @ _Ry(90))
        lf.add_inst("weldgf", lambda: _weld_mb(R_GFRAME), _T(b - dirx * 0.0015, 0, z) @ _Ry(90))
    _truss(lf, (xh + dirx * (R + 0.03), 0.016, z_lt - 0.05), (xf - dirx * (R + 0.03), 0.016, z_lb + 0.05))
    for (x, z, dd) in ((xh, z_lt - 0.05, dirx), (xf, z_lb + 0.05, -dirx)):
        lf.add_inst("bandgf", lambda: _band_mb(R_GFRAME), _T(x, 0, z) @ _Rz(math.degrees(math.atan2(0.55, dd))))
    # tela con barras de tensión en ambos montantes
    xa, xb = xh + dirx * (R + 0.0155), xf - dirx * (R + 0.0155)
    zf0 = z_lb + 0.012
    zf1 = zf0 + n_fab * CL_D
    for x, sd, xu in ((xa, dirx, xh), (xb, -dirx, xf)):
        rbox(lf, (x - 0.0095, yfl - 0.0024, zf0 - 0.012), (x + 0.0095, yfl + 0.0024, zf1 - 0.004), "galvanized", r=0.0012)
        for k in range(5):
            zb_ = zf0 + 0.15 + (zf1 - zf0 - 0.3) * k / 4
            lf.add_inst(f"tbandg{'r' if sd > 0 else 'l'}", lambda sd=sd: tension_band(R_GFRAME, sd, yfab=yfl), _T(xu, 0, zb_))
    _add_fabric(lf, min(xa, xb), max(xa, xb), zf0, n_fab, M=_T(0, yfl, 0))
    x = min(xa, xb) + 0.25
    while x < max(xa, xb) - 0.15:
        for z in (z_lb, zm, z_lt):
            lf.add_inst("rtieg", lambda: rail_tie(R_GFRAME, yf=yfl), _T(x, 0, z))
        x += 0.5
    # púas: 3 hilos de montante a montante, en grapas de fleje atornilladas a las extensiones
    for zz in (z_lt + 0.12, z_lt + 0.23, z_lt + 0.34):
        ps = []
        for x in (xh, xf):
            ps.append(Vector((x, -R - 0.0068, zz)))
            lf.add_inst("extclip", ext_clip, _T(x, 0, zz))
        _add_barbed(lf, ps[0] + Vector((dirx * 0.016, 0, 0)), ps[1] - Vector((dirx * 0.016, 0, 0)))
    if latch == "rod":                                # barra de caída por dentro (+Y) del montante libre
        xr, yr = xf - dirx * 0.002, R + 0.0135
        zt_ = 1.30
        wire(lf, [(xr, yr, -0.13), (xr, yr, zt_), (xr - dirx * 0.17, yr, zt_)], 0.0079, seg=SEG_T, bend=0.03)
        for zg in (0.30, 1.05):                       # guías: fleje en U soldado al montante
            pts = [(xr - 0.017, R - 0.003, zg), (xr - 0.017, yr + 0.0115, zg), (xr + 0.017, yr + 0.0115, zg), (xr + 0.017, R - 0.003, zg)]
            sweep_frame(lf, [(-0.0025, -0.012), (0.0025, -0.012), (0.0025, 0.012), (-0.0025, 0.012)], fillet(pts, 0.008, 3),
                        "galvanized", up=(0, 0, 1))
        lathe(lf, [(0.0079, 1.10), (0.0125, 1.102), (0.0125, 1.118), (0.0079, 1.12)], seg=SEG_T, mat="galvanized",
              M=_T(xr, yr, 0), closed=True)        # collar de tope sobre la guía superior
    else:                                             # horquilla: collar + dos dientes que abrazan al otro montante + seguro
        zl = 1.05
        D = 2 * R + 0.05
        sleeve(lf, _T(xf, 0, zl - 0.035), R + 0.0012, R + 0.0055, 0.07)
        for sy in (-1, 1):
            y0 = sy * (R + 0.0085)
            rbox(lf, (min(xf, xf + dirx * (D + R + 0.02)), y0 - 0.0025, zl - 0.02),
                 (max(xf, xf + dirx * (D + R + 0.02)), y0 + 0.0025, zl + 0.02), "galvanized", r=0.0012)
        xk = xf + dirx * (D + R + 0.012)
        rbox(lf, (xk - 0.004, -R - 0.011, zl - 0.022), (xk + 0.004, R + 0.011, zl + 0.022), "galvanized", r=0.0015)
        holed(lf, _T(xk + dirx * 0.004, -R - 0.03, zl) @ _Ry(90 * dirx), (0, 0, 0.022, 0.016, 0.006), (0, 0, 0.007, 0.007, 0.006),
              0.004, re_o=0.0012, re_i=0.001, n=24, mat="galvanized", ne=1)
    return R, yfl


def fence_gate(w=4.0, h=2.4, open_deg=(0, 0), seed=0, fence_sides=(True, True), fabric="instance"):
    """Puerta doble abatible de malla ciclónica (origen: piso al centro del claro; claro libre `w` entre caras de los postes
    a lo largo de X; lado público -Y, abre hacia el recinto +Y). open_deg = (hoja izquierda, hoja derecha) en grados (0 =
    cerrada, + = abre hacia +Y; hasta 90).
    Postes de puerta de 4" OD con domo y dado, como terminales de la cerca vecina si fence_sides (barra de tensión, copa del
    larguero, brazo de púas a 45°: fence_run(..., end_posts=(..., None)) remata ahí). Por hoja: marco soldado de 1-7/8" con
    extensiones de púas, travesaño medio, tirante con tensor, tela 2" cal. 9 con barras de tensión, amarres, 3 hilos de púas,
    2 bisagras industriales de 180° (abrazadera al poste con perno macizo + abrazadera al montante con barril). Cierre: barra
    de caída en la hoja izquierda (con receptáculo de tubo en dado de concreto al centro), horquilla con seguro en la derecha
    y cadena de 6 mm con candado laminado (cerrada: abraza ambos montantes; abierta: cuelga de la hoja derecha)."""
    r = rng(seed)
    mb = TelMB()
    z_b, n, z_top, zr, zp, zt = fence_levels(h)
    Xl, Xr = -(w / 2 + R_GATEPOST), w / 2 + R_GATEPOST
    for X, sd, fs in ((Xl, -1, fence_sides[0]), (Xr, 1, fence_sides[1])):
        _terminal(mb, X, sd, R_GATEPOST, z_b, z_top, zr, zt, x_brace=None, fabric=fs and fabric != "none", rail=fs, foot=0.27)
    z_lb, z_lt = 0.11, zr
    n_fab = int((z_lt - z_lb - 0.012) / CL_D)
    L = w / 2 - 0.032 - 0.025 - R_GFRAME              # perno -> eje del montante libre
    zh = (0.28, z_lt - 0.22)
    for side, X, dirx, ang, latch in ((0, Xl, 1, open_deg[0], "rod"), (1, Xr, -1, open_deg[1], "fork")):
        xpin = X + dirx * (R_GATEPOST + 0.032)
        Mleaf = _T(xpin, 0, 0) @ _Rz(dirx * float(ang))
        lf = TelMB()
        _leaf(lf, dirx, L, z_lb, z_lt, n_fab, latch=latch)
        for z in zh:                                  # bisagras: mitad de la hoja (gira con ella) y mitad del poste
            lf.add_inst("hingeleaf", hinge_leaf_part, _T(0, 0, z) @ _Rz(0 if dirx > 0 else 180))
            mb.add_inst("hingepost", hinge_post_part, _T(xpin, 0, z) @ _Rz(0 if dirx > 0 else 180))
        mb.join(lf, Mleaf)
    # receptáculo de la barra de caída (tubo en dado de concreto) al centro, del lado de la hoja izquierda cerrada
    xr = Xl + R_GATEPOST + 0.032 + L - 0.002
    yr = R_GFRAME + 0.0135
    footing(mb, xr, yr, 0.016, 0.11, crown=0.02)
    lathe(mb, [(0.0115, -0.05), (0.0115, 0.026), (0.0135, 0.026), (0.0135, 0.02), (0.0155, 0.018), (0.0155, -0.03)], seg=SEG,
          mat="galvanized", M=_T(xr, yr, 0), caps=False)
    lathe(mb, [(0.0, -0.03), (0.0115, -0.03)], seg=SEG, mat="cable", M=_T(xr, yr, 0), caps=False)
    # cadena y candado
    xa_ = Xl + R_GATEPOST + 0.032 + L
    xb_ = Xr - R_GATEPOST - 0.032 - L
    zc = 1.17
    Rc = R_GFRAME + 0.0045
    if abs(open_deg[0]) < 1e-3 and abs(open_deg[1]) < 1e-3:
        pts = []
        for (cx, a0) in ((xb_, -PI / 2), (xa_, PI / 2)):
            for k in range(9):
                a = a0 + PI * k / 8
                pts.append((cx + Rc * math.cos(a), Rc * math.sin(a), zc - 0.006 * math.sin(a) ** 2))
        _chain(mb, pts, closed=True)
        pl = Vector(((xa_ + xb_) / 2, -Rc - 0.006, zc - 0.006))
        padlock(mb, _T(pl.x, pl.y - 0.004, pl.z + 0.004) @ _Rz(float(r.uniform(-12, 12))))
        _chain(mb, [(pl.x + 0.01, pl.y - 0.004, zc - 0.03), (pl.x + 0.02, pl.y - 0.02, zc - 0.18)])
    else:
        Mr = _T(Xr - R_GATEPOST - 0.032, 0, 0) @ _Rz(-float(open_deg[1]))
        cx = -L
        pts = [(cx + Rc * math.cos(a), Rc * math.sin(a), zc) for a in [PI / 2 + PI * k / 8 for k in range(9)]]
        pts += [(cx - 0.02, -Rc - 0.03, zc - 0.12), (cx - 0.035, -Rc - 0.035, zc - 0.33)]
        _chain(mb, pts, M=Mr)
        padlock(mb, Mr @ _T(cx - 0.035, -Rc - 0.035, zc - 0.33))
    if fabric == "join":
        mb.realize()
    return mb


# ========================================================================================================= ice bridge
def anchor_base(mb, x, y, plate=0.30, t=0.019, pier_r=0.23, pier_h=0.15, R_post=0.0445, bolt_off=0.11, grout=0.025, seed=0):
    """Dado de concreto redondo con chaflán, lecho de grout, placa base cuadrada con 4 anclas (tuerca de nivelación abajo,
    arandela + tuerca + rosca arriba) y 4 cartelas soldadas al poste. Devuelve la z de la cara superior de la placa."""
    lathe(mb, [(pier_r + 0.004, -0.05), (pier_r, 0.0), (pier_r, pier_h - 0.015), (pier_r - 0.015, pier_h), (0.0, pier_h)], seg=SEG,
          mat="concrete", M=_T(x, y, 0), caps=False)
    zg = pier_h + grout
    hp = plate / 2 + 0.012                             # lecho de grout que asoma bajo la placa con talud
    mb.plate([(px, py) for (px, py) in rr_pts(plate + 0.03, plate + 0.03, 0.02, n=2)], grout * 0.4, "concrete", m=_T(x, y, pier_h))
    skin(mb, [[(px, py, pier_h + grout * 0.4) for (px, py) in rr_pts(plate + 0.03, plate + 0.03, 0.02, n=2)],
              [(px, py, zg) for (px, py) in rr_pts(plate + 0.004, plate + 0.004, 0.012, n=2)]], "concrete", M=_T(x, y, 0), cap0=False)
    mb.box((x - plate / 2, y - plate / 2, zg), (x + plate / 2, y + plate / 2, zg + t), "galvanized", bevel=0.003, seg=2)
    for sx in (-1, 1):
        for sy in (-1, 1):
            px, py = x + sx * bolt_off, y + sy * bolt_off
            stud(mb, _T(px, py, zg + t), d=0.019, proud=0.032, mat="galvanized", seg=10)
    for k in range(4):                                 # cartelas
        a = PI / 4 + PI / 2 * k
        M = _T(x, y, zg + t) @ _Rz(math.degrees(a))
        mb.plate([(R_post, 0.0), (R_post + 0.075, 0.0), (R_post + 0.075, 0.012), (R_post + 0.006, 0.11), (R_post, 0.11)], 0.008,
                 "galvanized", m=M @ _T(0, 0.004, 0) @ _Rx(90))
    return zg + t


def ice_bridge(L=5.5, h=2.6, w=0.51, n_posts=2, n_cables=16, seed=0):
    """Puente de cables (ice bridge / waveguide bridge) de x = 0 a x = L, centrado en y = 0; h = cara superior de los
    largueros (origen: piso). Tipo escalera galvanizado (catálogos CommScope WB-CY212 / Andrew: 24" × 12', postes de 3-1/2"):
    dos canales C de 3" con patines hacia afuera, peldaños de canal 38 × 19 cada 30 cm soldados, empalmes atornillados cada
    3,66 m, postes de 3-1/2" OD sobre placa base con anclas y cartelas en dado de concreto, brazo transversal de canal de 3"
    con abrazaderas. Cables: n_cables (todos negros salvo 2 de fibra amarillos) de ~25 mm y 12 mm acostados en una capa,
    amarrados con fleje inoxidable y hebilla cada ~0,9 m; en x = 0 suben hacia la torre (radio de curvatura 0,3 m, hasta
    h + 0,8) y en x = L siguen 0,3 m rectos hacia el puerto de entrada de la caseta."""
    r = rng(seed)
    mb = MB()
    ch_h, ch_w, ch_t = 0.0762, 0.0358, 0.0043          # C 3" × 4.1 lb/ft
    yw = w / 2 - ch_w                                    # cara exterior del alma
    z_c = h - ch_h / 2
    nsec = max(1, int(math.ceil(L / 3.66 - 1e-6)))
    cuts = [L * i / nsec for i in range(nsec + 1)]
    for sy in (-1, 1):
        for i in range(nsec):
            x0 = cuts[i] + (0.002 if i else 0.0)
            x1 = cuts[i + 1] - (0.002 if i < nsec - 1 else 0.0)
            chan(mb, (x0, sy * yw, z_c), (x1, sy * yw, z_c), ch_w, ch_h, ch_t, up=(0, 0, 1), open_dir=sy)
    # empalmes: placa de 300 × 60 × 6 dentro del canal, 4 pernos con tuerca
    for xc in cuts[1:-1]:
        for sy in (-1, 1):
            yp = sy * (yw + ch_t)
            mb.box((xc - 0.15, min(yp, yp + sy * 0.006), z_c - 0.03), (xc + 0.15, max(yp, yp + sy * 0.006), z_c + 0.03), "galvanized",
                   bevel=0.0015, seg=1)
            for dx in (-0.11, -0.05, 0.05, 0.11):
                bolt(mb, _T(xc + dx, yp + sy * 0.006, z_c) @ _Rx(-90 * sy), d=0.0095, mat="galvanized", seg=8)
    # peldaños: canal 38 × 19 boca abajo cada 30 cm
    yi = yw - ch_t
    nr = int(L / 0.3)
    rung_xs = [L * (k + 0.5) / nr for k in range(nr)]
    z_rung = h - ch_h + 0.0095 + 0.004
    for x in rung_xs:
        sweep_frame(mb, [(-0.019, 0.0), (0.019, 0.0), (0.019, -0.019), (0.0165, -0.019), (0.0165, -0.0025), (-0.0165, -0.0025),
                         (-0.0165, -0.019), (-0.019, -0.019)], [(x, -yi, z_rung + 0.0095), (x, yi, z_rung + 0.0095)], "galvanized",
                    up=(0, 0, 1))
    z_bed = z_rung + 0.0095
    # postes, placas base y brazos transversales
    if n_posts == 1:
        pxs = [L / 2]
    else:
        pxs = [0.45 + (L - 0.9) * k / (n_posts - 1) for k in range(n_posts)]
    Rp = 3.5 * IN / 2
    for k, px in enumerate(pxs):
        zb = anchor_base(mb, px, 0.0, R_post=Rp, seed=seed * 7 + k)
        z_arm = h - ch_h - 0.0762 / 2
        pipe(mb, (px, 0, zb - 0.002), (px, 0, z_arm - 0.0762 / 2 - 0.012), Rp, caps=False)
        mb.box((px - 0.075, -0.075, z_arm - 0.0762 / 2 - 0.012), (px + 0.075, 0.075, z_arm - 0.0762 / 2), "galvanized", bevel=0.002,
               seg=1)
        ring(mb, _T(px, 0, z_arm - 0.0762 / 2 - 0.0135), Rp + 0.001, 0.003, n=SEG, seg=4)
        ring(mb, _T(px, 0, zb + 0.0015), Rp + 0.001, 0.003, n=SEG, seg=4)
        aw = w / 2 + 0.12
        chan(mb, (px + ch_w / 2, -aw, z_arm), (px + ch_w / 2, aw, z_arm), ch_w, 0.0762, ch_t, up=(0, 0, 1), open_dir=-1)
        for yy in (-0.055, -0.025, 0.025, 0.055):          # pernos placa-brazo (cabeza abajo de la placa, tuerca dentro del canal)
            bolt(mb, _T(px - 0.004, yy, z_arm - 0.0381 - 0.012) @ _Rx(180), d=0.0127, mat="galvanized", seg=8)
            hexnut(mb, _T(px - 0.004, yy, z_arm - 0.0381 + ch_t), s=0.019, h=0.011, mat="galvanized")
        for sy in (-1, 1):                               # abrazaderas de ángulo que fijan cada larguero al brazo
            yc = sy * (yw + ch_w + 0.004)
            mb.box((px - 0.05, yc - 0.002, z_arm + 0.0381), (px + 0.05, yc + 0.002, z_arm + 0.0381 + 0.05), "galvanized", bevel=0.001,
                   seg=1)
            mb.box((px - 0.05, min(yc, yc + sy * 0.04), z_arm + 0.0381), (px + 0.05, max(yc, yc + sy * 0.04), z_arm + 0.0381 + 0.005),
                   "galvanized", bevel=0.001, seg=1)
            bolt(mb, _T(px, yc + sy * 0.002, z_arm + 0.0381 + 0.03) @ _Rx(-90 * sy), d=0.0095, mat="galvanized", seg=8)
            bolt(mb, _T(px, yc + sy * 0.025, z_arm + 0.0381 + 0.005), d=0.0095, mat="galvanized", seg=8)
    # cables: capa de negros (25 mm) + 2 amarillos de fibra (12 mm) encima
    nb_ = max(0, n_cables - 2)
    ny = min(2, n_cables)
    rb, ry = 0.0125, 0.006
    inner = 2 * (yi - 0.004)
    pitch = min(2 * rb + 0.003, inner / max(nb_, 1))
    y0 = -pitch * (nb_ - 1) / 2
    straps = [x for x in rung_xs[2::4]]
    cab = []
    for i in range(nb_):
        cab.append((y0 + pitch * i, z_bed + rb, rb, "cable"))
    for j in range(ny):
        yy = y0 + pitch * (0.5 + j * 1.0) + pitch * 2
        cab.append((yy, z_bed + 2 * rb + ry - 0.0015, ry, "paint_yellow"))
    z_rise = h + 0.8
    for i, (yc, zc, rc, mat) in enumerate(cab):
        yel = mat != "cable"                           # los de fibra van encima: suben por fuera con radio mayor
        xr = -0.22 - (0.06 if yel else 0.0)
        path = [(xr, yc, z_rise), (xr, yc, zc)]
        for xm in (L * 0.3, L * 0.62):
            path.append((xm + float(r.uniform(-0.2, 0.2)), yc + float(r.uniform(-0.0012, 0.0012)), zc))
        path.append((L + 0.3, yc, zc))
        wire(mb, path, rc, mat=mat, seg=13, bend=0.36 if yel else 0.32, nseg=6)
    # flejes inoxidables con hebilla que abrazan la capa de cables y el peldaño
    zt_layer = z_bed + 2 * rb
    for sx in straps:
        pts = [(sx, -yi + 0.006, z_rung - 0.004), (sx, -yi + 0.006, z_bed + 0.002)]
        top = []
        for i in range(nb_):
            yc = y0 + pitch * i
            top.append((sx, yc, z_bed + 2 * rb + 0.0008))
        top = sorted(top, key=lambda p: p[1])
        pts += top + [(sx, yi - 0.006, z_bed + 0.002), (sx, yi - 0.006, z_rung - 0.004)]
        sweep_frame(mb, [(-0.0006, -0.0064), (0.0006, -0.0064), (0.0006, 0.0064), (-0.0006, 0.0064)], _dedupe(pts), "steel",
                    up=(1, 0, 0))
        mb.box((sx - 0.009, yi - 0.012, z_bed + 0.004), (sx + 0.009, yi - 0.0045, z_bed + 0.02), "steel", bevel=0.0015, seg=1)
    return mb


# ================================================================================================== gabinete exterior
def _MF(x, y, z, face="front"):
    """Marco de una cara: XY local sobre la cara, +Z local hacia afuera. face: front (-Y), back (+Y), right (+X), left (-X)."""
    rot = {"front": _Rx(90), "back": _Rz(180) @ _Rx(90), "right": _Rz(90) @ _Rx(90), "left": _Rz(-90) @ _Rx(90)}[face]
    return _T(x, y, z) @ rot


def _louvers(mb, M, n, w, pitch=0.026, mat="sign_white"):
    """Rejilla de persianas troqueladas: n capuchas abombadas (sobresalen 6,5 mm) de ancho w con su ranura oscura debajo.
    M: centro de la rejilla sobre la cara (XY local, +Z afuera)."""
    for k in range(n):
        y = (k - (n - 1) / 2) * pitch
        slab(mb, M @ _T(0, y, -0.0005), w, 0.015, 0.007, rc=0.0065, re=0.0035, mat=mat, nc=2, ne=1, re0=0.0, cap0=False)
        mb.box((-w / 2 + 0.006, y - 0.0098, -0.0012), (w / 2 - 0.006, y - 0.0066, 0.0016), "cable", bevel=0.0, m=M)


def _cab_handle(mb, M):
    """Manija giratoria con cerradura de 3 puntos: escudo embutido, palanca abatida y cilindro de llave. M: cara de la puerta."""
    slab(mb, M @ _T(0, 0, -0.0005), 0.042, 0.17, 0.006, rc=0.008, re=0.002, mat="cable", nc=3, ne=1, re0=0.0, cap0=False)
    slab(mb, M @ _T(0, -0.012, 0.0055), 0.028, 0.13, 0.009, rc=0.008, re=0.003, mat="steel", nc=3, ne=2, re0=0.0, cap0=False)
    lathe(mb, [(0.0092, 0.0055), (0.0092, 0.008), (0.008, 0.0105), (0.0, 0.011)], seg=SEG, mat="steel", M=M @ _T(0, 0.062, 0),
          caps=False)
    mb.box((-0.0007, 0.057, 0.0095), (0.0007, 0.067, 0.0113), "cable", bevel=0.0, m=M)


def _pin_hinge(mb, M, h=0.08, r=0.0065):
    """Bisagra exterior de pasador: dos nudillos de 24 lados con hoja atornillada. M: eje vertical del pasador."""
    for z0, z1 in ((-h / 2, -0.002), (0.002, h / 2)):
        lathe(mb, [(r * 0.85, z0), (r, z0 + 0.0012), (r, z1 - 0.0012), (r * 0.85, z1)], seg=16, mat="steel", M=M, caps=True)
    lathe(mb, [(r * 0.55, h / 2), (r * 0.55, h / 2 + 0.003), (0.0, h / 2 + 0.0042)], seg=10, mat="steel", M=M, caps=False)
    mb.box((-0.0015, 0.0, -h / 2 + 0.004), (0.0015, 0.03, h / 2 - 0.004), "steel", bevel=0.0008, seg=1, m=M @ _Rz(-20))


def outdoor_cabinet(kind="power", seed=0):
    """Gabinete exterior de telecom (lámina doble con pintura en polvo blanca, IP55; catálogos BETE BT7575175 / EverExceed:
    750 × 750 × 1750 mm) sobre su zócalo galvanizado de 100 mm. Origen: piso al centro; puerta al frente (-Y).
    Puerta con junta perimetral, 3 bisagras de pasador, manija con cerradura de 3 puntos; techo-sombrero que vuela 30 mm con
    holgura de ventilación sobre separadores y tapones de las orejas de izaje; zócalo con tapa frontal atornillada, pestañas de
    anclaje con taquete y placa de prensaestopas atrás con 3 cables que bajan al piso; placa de datos y etiqueta de riesgo.
    kind: 'power' (planta de rectificadores: rejillas arriba y abajo en la puerta), 'battery' (baterías: más bajo, rejillas
    laterales), 'telecom' (equipos: aire acondicionado de puerta con carcasa, rejillas y dren de condensado)."""
    r = rng(seed)
    mb = MB()
    W = D = 0.75
    H = {"power": 1.75, "battery": 1.55, "telecom": 1.80}[kind]
    zp = 0.10
    z0, z1 = zp, zp + H
    # zócalo galvanizado: paredes de lámina doblada, tapa frontal atornillada, pestañas de anclaje
    pw = W - 0.02
    slab(mb, _T(0, 0, 0), pw, pw, zp, rc=0.004, re=0.002, mat="galvanized", nc=2, ne=1, re0=0.0, cap0=False)
    mb.box((-pw / 2 + 0.04, -pw / 2 - 0.0025, 0.012), (pw / 2 - 0.04, -pw / 2 + 0.0005, zp - 0.012), "galvanized", bevel=0.0012, seg=1)
    for sx in (-1, 1):
        screw(mb, _MF(sx * (pw / 2 - 0.06), -pw / 2 - 0.0025, zp / 2), r=0.004, mat="steel", seg=10)
        for sy in (-1, 1):
            mb.box((sx * pw / 2 - (0.0 if sx < 0 else 0.05) + (0.0 if sx > 0 else -0.05), sy * 0.2 - 0.03, 0.0),
                   (sx * pw / 2 + (0.05 if sx > 0 else 0.0), sy * 0.2 + 0.03, 0.004), "galvanized", bevel=0.0015, seg=1)
            hexnut(mb, _T(sx * (pw / 2 + 0.026), sy * 0.2, 0.004), s=0.017, h=0.01, mat="galvanized")
    # cuerpo
    slab(mb, _T(0, 0, z0), W, D, H, rc=0.01, re=0.004, mat="sign_white", nc=3, ne=2)
    # puerta (sobrepuesta, junta de 3 mm) con bisagras a la izquierda y manija a la derecha
    dw, dh, dt = W - 0.04, H - 0.07, 0.022
    yd = -D / 2
    Md = _T(0, yd, z0 + 0.035) @ _Rx(90)
    slab(mb, Md @ _T(0, dh / 2, -0.0005), dw, dh, dt, rc=0.008, re=0.004, mat="sign_white", nc=3, ne=2, re0=0.0, cap0=False)
    slab(mb, Md @ _T(0, dh / 2, -0.0008), dw + 0.006, dh + 0.006, 0.0035, rc=0.01, re=0.001, mat="rubber", nc=3, ne=1, re0=0.0,
         cap0=False)
    yf = yd - dt                                      # cara de la puerta
    for zz in (0.25, dh / 2, dh - 0.25):
        _pin_hinge(mb, _T(-dw / 2 - 0.004, yd - dt * 0.55, z0 + 0.035 + zz) @ _Rz(180))
    _cab_handle(mb, _MF(dw / 2 - 0.075, yf, z0 + 0.035 + dh * 0.5))
    # placa de datos (aluminio con remaches) y etiqueta de riesgo eléctrico (triángulo amarillo con rayo)
    Mp = _MF(-0.13, yf, z0 + 0.035 + dh * 0.62)
    mb.box((-0.06, -0.03, -0.0004), (0.06, 0.03, 0.0008), "aluminium", bevel=0.0004, seg=1, m=Mp)
    for (px, py) in ((-0.052, -0.022), (0.052, -0.022), (-0.052, 0.022), (0.052, 0.022)):
        lathe(mb, [(0.002, 0.0008), (0.0016, 0.0016), (0.0, 0.0019)], seg=8, mat="aluminium", M=Mp @ _T(px, py, 0), caps=False)
    for k in range(4):
        mb.box((-0.045, 0.012 - k * 0.011, 0.0008), (0.045 - 0.02 * (k % 2), 0.0155 - k * 0.011, 0.0013), "cable", bevel=0.0, m=Mp)
    Mw = _MF(0.0, yf, z0 + 0.035 + dh * 0.62)
    tri = [(0.0, 0.048), (-0.042, -0.024), (0.042, -0.024)]
    mb.plate(tri, 0.0009, "paint_yellow", m=Mw @ _T(0.06, 0, -0.0003))
    mb.plate([(0.0, 0.034), (-0.032, -0.017), (0.032, -0.017)], 0.0004, "cable", m=Mw @ _T(0.06, 0, 0.0006))
    mb.plate([(0.0, 0.028), (-0.025, -0.013), (0.025, -0.013)], 0.0004, "paint_yellow", m=Mw @ _T(0.06, 0, 0.001))
    mb.plate([(0.004, 0.018), (-0.006, 0.0), (0.0, 0.0), (-0.004, -0.012), (0.007, 0.003), (0.001, 0.003)], 0.0004, "cable",
             m=Mw @ _T(0.06, 0, 0.0014))
    zc = z0 + 0.035
    if kind == "power":
        _louvers(mb, _MF(-0.04, yf, zc + 0.30), 8, 0.44)
        _louvers(mb, _MF(-0.04, yf, zc + dh - 0.32), 8, 0.44)
    elif kind == "battery":
        _louvers(mb, _MF(-0.04, yf, zc + 0.22), 5, 0.44)
        for face, xf in (("right", W / 2), ("left", -W / 2)):
            _louvers(mb, _MF(xf, 0.0, z0 + 0.22, face), 5, 0.42)
            _louvers(mb, _MF(xf, 0.0, z1 - 0.20, face), 4, 0.42)
    else:                                             # aire acondicionado montado en puerta
        Ma = _MF(-0.03, yf, zc + dh * 0.5)
        slab(mb, Ma @ _T(0, -0.05, -0.0005), 0.50, 0.92, 0.095, rc=0.02, re=0.008, mat="sign_white", nc=3, ne=2, re0=0.0, cap0=False)
        Mac = Ma @ _T(0, 0, 0.0945)
        _louvers(mb, Mac @ _T(0, 0.25, 0), 7, 0.38)
        _louvers(mb, Mac @ _T(0, -0.30, 0), 7, 0.38)
        holed(mb, Mac @ _T(0, -0.01, -0.0005), (0, 0, 0.17, 0.05, 0.01), (0, 0, 0.15, 0.03, 0.008), 0.003, re_o=0.0012,
              re_i=0.001, n=24, mat="sign_white", ne=1)
        mb.box((-0.15, -0.04, -0.003), (0.15, 0.02, 0.0002), "cable", bevel=0.0, m=Mac)
        wire(mb, [(-0.03 + 0.2, yf - 0.06, zc + dh * 0.5 - 0.51), (0.17, yf - 0.06, zc - 0.05), (0.17, yf - 0.03, 0.02)], 0.006,
             mat="plastic", bend=0.04, seg=13)
    # techo-sombrero con holgura de ventilación, separadores y tapones de izaje
    zr = z1 + 0.018
    for sx in (-1, 1):
        for sy in (-1, 1):
            mb.box((sx * 0.3 - 0.02, sy * 0.3 - 0.02, z1 - 0.001), (sx * 0.3 + 0.02, sy * 0.3 + 0.02, zr + 0.001), "sign_white",
                   bevel=0.002, seg=1)
    ov = 0.03
    loops = [[(x, y, zr + 0.003) for (x, y) in rr_pts(W + 2 * ov - 0.018, D + 2 * ov - 0.018, 0.008, n=3)]]   # gotero inferior
    for (dl, z) in ((0.0, zr), (0.0, zr + 0.026), (0.004, zr + 0.03), (0.07, zr + 0.042), (0.12, zr + 0.045)):
        loops.append([(x, y, z) for (x, y) in rr_pts(W + 2 * ov - 2 * dl, D + 2 * ov - 2 * dl, max(0.012 - dl * 0.05, 0.004), n=3)])
    skin(mb, loops, "sign_white", cap0=True, cap1=True)
    for sx in (-1, 1):
        for sy in (-1, 1):                            # tapones de las orejas de izaje (las orejas se retiran al instalar)
            hexnut(mb, _T(sx * 0.27, sy * 0.27, zr + 0.0445), s=0.03, h=0.011, mat="steel")
    # placa de prensaestopas atrás del zócalo con 3 cables que bajan al piso
    Mg = _MF(0.0, pw / 2, zp / 2, "back")
    mb.box((-0.15, -0.035, -0.0005), (0.15, 0.035, 0.004), "galvanized", bevel=0.0012, seg=1, m=Mg)
    for k, (gx, rc) in enumerate(((-0.09, 0.011), (0.0, 0.014), (0.09, 0.009))):
        lathe(mb, [(rc + 0.009, 0.004), (rc + 0.009, 0.013), (rc + 0.006, 0.016), (rc + 0.006, 0.027), (rc + 0.0008, 0.035)],
              seg=SEG, mat="plastic", M=Mg @ _T(gx, 0.0, 0), caps=False)
        p0 = Mg @ Vector((gx, 0.0, 0.03))
        wire(mb, [tuple(p0), tuple(p0 + Vector((0, 0.07, 0))), (p0.x + float(r.uniform(-0.02, 0.02)), p0.y + 0.12, -0.03)],
             rc, mat="cable", bend=0.06, seg=13, nseg=4)
    return mb


# ============================================================================================ generador y tanque diésel
def _flush_handle(mb, M, mat="steel"):
    """Manija embutida de 'levantar y girar' con cerradura (puertas de casetas de generador). M: cara (XY, +Z afuera)."""
    slab(mb, M @ _T(0, 0, -0.0006), 0.07, 0.13, 0.004, rc=0.012, re=0.0015, mat="cable", nc=3, ne=1, re0=0.0, cap0=False)
    slab(mb, M @ _T(0, -0.008, 0.0034), 0.05, 0.09, 0.006, rc=0.01, re=0.0025, mat=mat, nc=3, ne=1, re0=0.0, cap0=False)
    lathe(mb, [(0.0085, 0.0034), (0.0085, 0.009), (0.007, 0.0115), (0.0, 0.012)], seg=SEG, mat=mat, M=M @ _T(0, 0.045, 0), caps=False)
    mb.box((-0.0007, 0.0405, 0.0105), (0.0007, 0.0495, 0.0123), "cable", bevel=0.0, m=M)


def _estop(mb, M):
    """Paro de emergencia: base amarilla con aro guarda y hongo rojo. M: cara (XY, +Z afuera)."""
    lathe(mb, [(0.0, 0.0), (0.03, 0.0), (0.03, 0.006), (0.027, 0.008), (0.0, 0.008)], seg=SEG, mat="paint_yellow", M=M)
    lathe(mb, [(0.012, 0.008), (0.012, 0.014), (0.02, 0.016), (0.021, 0.022), (0.017, 0.026), (0.0, 0.027)], seg=SEG, mat="sign_red",
          M=M, caps=False)


def generator(seed=0):
    """Generador diésel de 30 kVA en caseta insonorizada (catálogos Stephill SSDP30 2050 × 1000 × 1490, YorPower YXP30,
    Caterpillar 30–220 kVA: 1863–3511 L × 899–1325 W × 1348–1684 H). Origen: piso al centro; tablero de control en el extremo
    -X, radiador en +X, frente largo hacia -Y.
    Bastidor-base de canal negro con bolsas para montacargas, travesaños, anclas con tuerca, válvulas de drenado, conexiones
    de combustible (alimentación / retorno) y zapata de tierra con cable de cobre. Caseta de lámina gris con núcleo oscuro y
    paneles separados por juntas reales: 2 puertas por costado con bisagras de pasador y manijas embutidas con chapa, persianas
    de toma de aire, rejilla de descarga del radiador con marco y deflectores, puerta de control con mirilla de policarbonato,
    controlador con pantalla y teclas, paro de emergencia; techo con oreja de izaje central, brida y chimenea de escape de 3"
    con sombrerete abatible; placa en relieve '30 KVA' y 'STANDBY POWER'."""
    r = rng(seed)
    mb = MB()
    Lb, Wb, hb = 2.05, 1.00, 0.15                       # bastidor
    L, W = 2.0, 0.96                                     # caseta
    z0, z1 = hb, hb + 1.20
    # ---- bastidor: dos largueros C (patines hacia afuera), cabezales, bolsas de montacargas, anclas
    for sy in (-1, 1):                                   # largueros C con el alma al ras del canto y patines hacia adentro
        chan(mb, (-Lb / 2, sy * Wb / 2, hb / 2), (Lb / 2, sy * Wb / 2, hb / 2), 0.065, hb, 0.006, mat="cable", open_dir=sy)
    for sx in (-1, 1):                                   # cabezales C
        chan(mb, (sx * Lb / 2, -Wb / 2 + 0.006, hb / 2), (sx * Lb / 2, Wb / 2 - 0.006, hb / 2), 0.065, hb, 0.006, mat="cable",
             open_dir=-sx)
        for sy in (-1, 1):                               # pestaña de anclaje con ancla y tuerca
            ax, ay = sx * (Lb / 2 - 0.11), sy * (Wb / 2 + 0.03)
            mb.box((ax - 0.05, min(ay, sy * Wb / 2) - (0.022 if sy > 0 else 0.0), 0.0),
                   (ax + 0.05, max(ay, sy * Wb / 2) + (0.022 if sy < 0 else 0.0), 0.012), "cable", bevel=0.002, seg=1)
            bolt(mb, _T(ax, ay, 0.012), d=0.016, mat="galvanized", seg=10)
            lathe(mb, [(0.0075, 0.012 + 0.0115), (0.0075, 0.012 + 0.021), (0.006, 0.012 + 0.0235), (0.0, 0.012 + 0.0235)], seg=10,
                  mat="galvanized", M=_T(ax, ay, 0), caps=False)
    for xx in (-0.45, 0.45):                             # bolsas de montacargas (PTR que atraviesa el bastidor)
        for sy in (-1, 1):
            Mk = _MF(xx, sy * Wb / 2, 0.075, "front" if sy < 0 else "back")
            rrframe(mb, Mk, (0, 0, 0.24, 0.10, 0.01), (0, 0, 0.20, 0.064, 0.006), 0.006, re_o=0.002, re_i=0.0015, n=2, ne=1, mat="cable")
            mb.box((-0.1, -0.032, -0.012), (0.1, 0.032, -0.008), "rubber", bevel=0.0, m=Mk)
    # ---- caseta: núcleo oscuro + paneles con juntas
    rbox(mb, (-L / 2 + 0.006, -W / 2 + 0.006, z0), (L / 2 - 0.006, W / 2 - 0.006, z1 - 0.004), "cable", r=0.004)
    for sx in (-1, 1):                                   # postes de esquina
        for sy in (-1, 1):
            rtube(mb, (sx * (L / 2 - 0.025), sy * (W / 2 - 0.025), z0), (sx * (L / 2 - 0.025), sy * (W / 2 - 0.025), z1), 0.05, 0.05,
                  "enamel", up=(1, 0, 0), r=0.006)
    pt = 0.018                                           # espesor de panel
    zc_ = z0 + 0.02
    dh = z1 - z0 - 0.06
    doors = [(-0.47, 0.86), (0.47, 0.86)]
    for side, sy in (("front", -1), ("back", 1)):
        yfc = sy * W / 2
        for k, (xc, dw) in enumerate(doors):
            M = _MF(xc, yfc - sy * 0.0, zc_, side)
            slab(mb, M @ _T(0, dh / 2, -pt + 0.002), dw, dh, pt, rc=0.006, re=0.003, mat="enamel", nc=2, ne=1, re0=0.0, cap0=False)
            Mf = M @ _T(0, 0, 0.002)
            hx = -dw / 2 + 0.005 if (k == 0) == (sy < 0) else dw / 2 - 0.005
            for zz in (0.18, dh - 0.18):
                _pin_hinge(mb, Mf @ _T(hx, zz, 0.0) @ _Rx(-90) @ _Rz(90 if hx < 0 else -90), h=0.07, r=0.006)
            _flush_handle(mb, Mf @ _T(-hx * 0.86, dh * 0.5, 0))
            if (sy < 0 and k == 1) or (sy > 0 and k == 0):
                _louvers(mb, Mf @ _T(0.0, dh * 0.62, 0), 10, 0.5, pitch=0.03, mat="enamel")
    # extremo del radiador (+X): rejilla de descarga con marco y deflectores inclinados
    Mr = _MF(L / 2, 0.0, z0 + 0.6, "right")
    holed(mb, Mr @ _T(0, 0, -0.002), (0, -0.002, W / 2 - 0.05, 0.594, 0.01), (0, 0, 0.36, 0.44, 0.006), 0.016, re_o=0.004, re_i=0.003,
          n=40, mat="enamel", ne=2)
    for k in range(13):
        yy = -0.40 + 0.8 * k / 12
        mb.box((-0.36, -0.032, -0.0015), (0.36, 0.032, 0.0015), "enamel", bevel=0.0012, seg=1, m=Mr @ _T(0, yy, 0.002) @ _Rx(55))
    mb.box((-0.358, -0.43, -0.02), (0.358, 0.43, -0.012), "cable", bevel=0.0, m=Mr)
    # extremo de control (-X): puerta con mirilla, controlador, paro de emergencia, placas en relieve
    Mc = _MF(-L / 2, 0.0, zc_, "left")
    slab(mb, Mc @ _T(0, dh / 2, -pt + 0.002), W - 0.1, dh, pt, rc=0.006, re=0.003, mat="enamel", nc=2, ne=1, re0=0.0, cap0=False)
    Mcf = Mc @ _T(0, 0, 0.002)
    for zz in (0.18, dh - 0.18):
        _pin_hinge(mb, Mcf @ _T(-(W - 0.1) / 2 + 0.005, zz, 0.0) @ _Rx(-90) @ _Rz(90), h=0.07, r=0.006)
    _flush_handle(mb, Mcf @ _T((W - 0.1) / 2 - 0.07, dh * 0.5, 0))
    rrframe(mb, Mcf @ _T(0, dh * 0.66, -0.001), (0, 0, 0.42, 0.30, 0.03), (0, 0, 0.36, 0.24, 0.02), 0.008, re_o=0.003, re_i=0.002, n=4,
            mat="rubber")
    mb.box((-0.18, -0.12, 0.0018), (0.18, 0.12, 0.0026), "glass", bevel=0.0, m=Mcf @ _T(0, dh * 0.66, 0))
    Mi = Mcf @ _T(0, dh * 0.66, -0.03)                 # controlador detrás de la mirilla
    slab(mb, Mi @ _T(0, 0, -0.005), 0.24, 0.18, 0.012, rc=0.008, re=0.002, mat="cable", nc=2, ne=1, re0=0.0, cap0=False)
    mb.box((-0.06, 0.005, 0.005), (0.06, 0.07, 0.0075), "sign_green", bevel=0.0, m=Mi)
    for k in range(6):
        mb.box((-0.075 + k * 0.03, -0.06, 0.005), (-0.06 + k * 0.03, -0.042, 0.0085), "plastic" if k % 3 else "sign_green", bevel=0.001,
               seg=1, m=Mi)
    _estop(mb, Mcf @ _T(0.25, dh * 0.66, 0))
    Ml = Mcf @ _T(0, dh * 0.30, 0)
    mb.box((-0.17, -0.055, -0.0004), (0.17, 0.055, 0.0012), "aluminium", bevel=0.0005, seg=1, m=Ml)
    label(mb, "STANDBY POWER", 0.026, "cable", Ml @ _T(0, 0.01, 0.0012), depth=0.0012, bold=True, res=2)
    label(mb, "30 KVA  DIESEL", 0.02, "cable", Ml @ _T(0, -0.035, 0.0012), depth=0.0012, res=2)
    # techo: panel con ligera corona, oreja de izaje central, escape
    loops = []
    for (dl, z) in ((0.0, z1 - 0.004), (0.0, z1 + 0.012), (0.012, z1 + 0.02), (0.2, z1 + 0.03)):
        loops.append([(x, y, z) for (x, y) in rr_pts(L + 0.01 - 2 * dl, W + 0.01 - 2 * dl, 0.012, n=2)])
    skin(mb, loops, "enamel", cap0=True, cap1=True)
    holed(mb, _T(0, 0.006, z1 + 0.02) @ _Rx(90), (0, 0.06, 0.07, 0.07, (0.05, 0.05, 0.004, 0.004)), (0, 0.075, 0.025, 0.025, 0.025), 0.012,
          re_o=0.003, re_i=0.004, n=32, mat="enamel", ne=2)
    xe, ye = 0.55, 0.22
    lathe(mb, [(0.06, z1 + 0.025), (0.06, z1 + 0.04), (0.042, z1 + 0.042)], seg=SEG, mat="steel", M=_T(xe, ye, 0), caps=False)
    for k in range(6):
        a = 2 * PI * k / 6
        bolt(mb, _T(xe + 0.051 * math.cos(a), ye + 0.051 * math.sin(a), z1 + 0.04), d=0.008, seg=8, mat="steel")
    zt = z1 + 0.30
    pipe(mb, (xe, ye, z1 + 0.035), (xe, ye, zt), 0.0381, mat="steel", caps=False)
    lathe(mb, [(0.0345, zt - 0.002), (0.0345, z1 + 0.04), (0.0, z1 + 0.04)], seg=SEG, mat="cable", M=_T(xe, ye, 0), caps=False)
    Mcap = _T(xe + 0.04, ye, zt) @ _Ry(-14)               # sombrerete abatible con bisagra
    lathe(mb, [(0.0, 0.003), (0.046, 0.003), (0.046, -0.006), (0.043, -0.007), (0.043, 0.0), (0.0, 0.0)], seg=SEG, mat="steel",
          M=Mcap @ _T(-0.04, 0, 0), caps=False)
    mb.cyl(Mcap @ Vector((0.006, -0.012, 0.0)), Mcap @ Vector((0.006, 0.012, 0.0)), 0.003, seg=12, mat="steel")
    # conexiones de combustible, drenes y tierra en el bastidor (lado -X, costado -Y)
    for k, (xx, mat) in enumerate(((-0.75, "cable"), (-0.62, "cable"))):
        Mfit = _MF(xx, -Wb / 2, 0.08, "front")
        lathe(mb, [(0.012, 0.0), (0.012, 0.02), (0.0145, 0.022), (0.0145, 0.036), (0.01, 0.038)], seg=6, mat="steel", M=Mfit, phase=PI / 6,
              caps=False)
        p0 = Mfit @ Vector((0, 0, 0.038))
        wire(mb, [tuple(p0), tuple(p0 + Vector((0, -0.05, 0))), (p0.x - 0.1 - 0.05 * k, p0.y - 0.08, 0.012), (-Lb / 2 - 0.2, p0.y - 0.1 - 0.04 * k, 0.012)],
             0.0095, mat="rubber", bend=0.05, seg=13, nseg=5)
    for xx in (0.3, 0.75):                               # válvulas de drenado (aceite / refrigerante) con tapón
        Mv = _MF(xx, -Wb / 2, 0.05, "front")
        lathe(mb, [(0.009, 0.0), (0.009, 0.03), (0.011, 0.032), (0.011, 0.05), (0.008, 0.052), (0.0, 0.052)], seg=12, mat="steel", M=Mv,
              caps=False)
        mb.box((-0.03, -0.004, 0.022), (0.004, 0.004, 0.028), "sign_red", bevel=0.0015, seg=1, m=Mv)
    Mg = _MF(-0.95, -Wb / 2, 0.1, "front")               # zapata de tierra y conductor de cobre al piso
    mb.box((-0.012, -0.02, 0.0), (0.012, 0.02, 0.006), "copper", bevel=0.0015, seg=1, m=Mg)
    bolt(mb, Mg @ _T(0, 0.006, 0.006), d=0.008, seg=8, mat="steel")
    pg = Mg @ Vector((0, -0.018, 0.006))
    wire(mb, [tuple(pg), (pg.x, pg.y - 0.03, pg.z - 0.03), (pg.x - 0.05, pg.y - 0.08, 0.004), (pg.x - 0.3, pg.y - 0.15, 0.004)], 0.0045,
         mat="copper", bend=0.04, seg=13, nseg=4)
    return mb


def fuel_tank(seed=0):
    """Tanque diésel horizontal de doble pared UL 142 de ~550 gal (Ø 1,12 × 1,85 m de virola; catálogos tankretailer /
    Modweldco: 48" × 72"), sobre dos silletas soldadas con placa base anclada. Origen: piso al centro; eje del tanque en X.
    Cabezas toriesféricas con cordón de soldadura, costura longitudinal, orejas de izaje, accesorios arriba: boca de llenado
    con tapa con candado, venteo normal con hongo, venteo de emergencia, indicador de nivel de carátula, puerto del monitor
    intersticial, alimentación y retorno con válvulas; zapata de tierra; placas 'DIESEL' y 'NO SMOKING' en relieve."""
    r = rng(seed)
    mb = MB()
    R, Ls = 0.56, 1.85
    zc = 0.18 + R
    # virola + cabezas (perfil de revolución alrededor de X)
    head = [(0.0, 0.13), (0.42, 0.112), (0.51, 0.08), (0.548, 0.042), (R, 0.0)]     # cabeza toriesférica (corona + nudillo)
    prof = [(rr, -Ls / 2 - hz) for (rr, hz) in head] + [(R, Ls / 2 - 0.0)] + [(rr, Ls / 2 + hz) for (rr, hz) in reversed(head[:-1])]
    lathe(mb, prof, seg=48, mat="enamel", M=_T(0, 0, zc) @ _Ry(90), caps=False)
    for x in (-Ls / 2, Ls / 2):                          # cordones de soldadura cabeza-virola
        ring(mb, _T(x, 0, zc) @ _Ry(90), R + 0.0008, 0.0035, mat="enamel", n=48, seg=3)
    mb.box((-Ls / 2, -0.004, zc - R - 0.0015), (Ls / 2, 0.004, zc - R + 0.002), "enamel", bevel=0.0015, seg=1)   # costura inferior
    # silletas: cuna curva + alma + placa base + cartelas + anclas
    for xs_ in (-0.58, 0.58):
        arc = []
        for k in range(13):
            a = -PI / 2 - math.radians(60) + math.radians(120) * k / 12
            arc.append((xs_, (R + 0.005) * math.cos(a), zc + (R + 0.005) * math.sin(a)))
        sweep_frame(mb, [(-0.006, -0.08), (0.006, -0.08), (0.006, 0.08), (-0.006, 0.08)], arc, "cable", up=(1, 0, 0))
        ys = (R + 0.005) * math.cos(-PI / 2 - math.radians(60))
        web = [(-abs(ys) - 0.04, 0.0)]
        for k in range(13):
            a = -PI / 2 - math.radians(60) + math.radians(120) * k / 12
            web.append(((R + 0.01) * math.cos(a), zc + (R + 0.01) * math.sin(a)))
        web += [(abs(ys) + 0.04, 0.0)]
        web = [(-abs(ys) - 0.04, 0.012)] + [(y, max(z, 0.012)) for (y, z) in web[1:-1]] + [(abs(ys) + 0.04, 0.012)]
        mb.plate([(y, z) for (y, z) in reversed(web)], 0.012, "cable", m=_T(xs_ + 0.006, 0, 0) @ _Rz(90) @ _Rx(90))
        mb.box((xs_ - 0.09, -abs(ys) - 0.07, 0.0), (xs_ + 0.09, abs(ys) + 0.07, 0.012), "cable", bevel=0.003, seg=1)
        for sy in (-1, 1):
            for dx in (-0.05, 0.05):
                bolt(mb, _T(xs_ + dx, sy * (abs(ys) + 0.035), 0.012), d=0.016, mat="galvanized", seg=8)
    # orejas de izaje
    for x in (-0.75, 0.75):
        holed(mb, _T(x - 0.006, 0, zc + R - 0.01) @ _Ry(90) @ _Rz(90), (0, 0.04, 0.04, 0.045, (0.03, 0.03, 0.002, 0.002)),
              (0, 0.05, 0.015, 0.015, 0.015), 0.012, re_o=0.002, re_i=0.003, n=16, mat="enamel", ne=1)
    zt = zc + R
    # boca de llenado con tapa con candado
    lathe(mb, [(0.05, zt - 0.02), (0.05, zt + 0.06), (0.055, zt + 0.062), (0.055, zt + 0.075)], seg=SEG, mat="steel",
          M=_T(-0.45, 0, 0), caps=False)
    lathe(mb, [(0.058, zt + 0.075), (0.058, zt + 0.1), (0.05, zt + 0.108), (0.0, zt + 0.11)], seg=SEG, mat="steel", M=_T(-0.45, 0, 0),
          caps=True)
    # venteo normal (tubo 2" con hongo)
    lathe(mb, [(0.03, zt - 0.02), (0.03, zt + 0.45), (0.036, zt + 0.452), (0.036, zt + 0.47)], seg=SEG, mat="steel", M=_T(0.2, 0.22, 0),
          caps=False)
    lathe(mb, [(0.03, zt + 0.47), (0.085, zt + 0.48), (0.088, zt + 0.49), (0.07, zt + 0.53), (0.0, zt + 0.545)], seg=SEG, mat="steel",
          M=_T(0.2, 0.22, 0), caps=True)
    # venteo de emergencia (tapa de presión)
    lathe(mb, [(0.085, zt - 0.02), (0.085, zt + 0.04), (0.11, zt + 0.042), (0.11, zt + 0.06), (0.095, zt + 0.1), (0.04, zt + 0.12),
               (0.0, zt + 0.122)], seg=SEG, mat="steel", M=_T(0.55, -0.1, 0), caps=False)
    # indicador de nivel de carátula
    from kit.clinic_equipo import gauge
    lathe(mb, [(0.03, zt - 0.02), (0.03, zt + 0.08), (0.06, zt + 0.08), (0.06, zt + 0.085)], seg=SEG, mat="steel", M=_T(-0.1, -0.15, 0),
          caps=False)
    gauge(mb, _T(-0.1, -0.15, zt + 0.12) @ _Rx(80), r=0.05, depth=0.03, needle=float(r.uniform(-30, 30)))
    mb.cyl((-0.1, -0.15, zt + 0.085), (-0.1, -0.15 - 0.005, zt + 0.12), 0.012, seg=12, mat="steel")
    # monitor intersticial
    lathe(mb, [(0.02, zt - 0.02), (0.02, zt + 0.05), (0.026, zt + 0.052), (0.026, zt + 0.07), (0.0, zt + 0.072)], seg=SEG,
          mat="sign_red", M=_T(0.75, 0.12, 0), caps=False)
    # alimentación y retorno con válvulas de bola
    for k, xx in enumerate((-0.2, -0.05)):
        lathe(mb, [(0.016, zt - 0.02), (0.016, zt + 0.05), (0.022, zt + 0.052), (0.022, zt + 0.1), (0.016, zt + 0.102), (0.016, zt + 0.14)],
              seg=12, mat="steel", M=_T(xx, 0.3, 0), caps=False)
        mb.box((xx - 0.004, 0.3, zt + 0.07), (xx + 0.004, 0.3 + 0.1, zt + 0.08), "sign_red", bevel=0.002, seg=1)
        wire(mb, [(xx, 0.3, zt + 0.14), (xx, 0.3, zt + 0.2), (xx, R + 0.2, zt + 0.1), (xx, R + 0.22, 0.012), (xx - 0.3, R + 0.4, 0.012)],
             0.0095, mat="rubber", bend=0.08, seg=13, nseg=3)
    # placas en relieve
    for xx, txt, sz in ((-0.2, "DIESEL", 0.06),):
        a0 = -PI / 2
        Mp = _T(xx, -R * math.cos(math.radians(20)), zc + R * math.sin(math.radians(20))) @ _Rx(90 - 20)
        mb.box((-0.22, -0.045, -0.002), (0.22, 0.045, 0.0012), "sign_white" if txt == "DIESEL" else "sign_red", bevel=0.0008, seg=1, m=Mp)
        label(mb, txt, sz, "sign_red" if txt == "DIESEL" else "sign_white", Mp @ _T(0, -sz * 0.36, 0.0012), depth=0.0012, bold=True,
              res=2)
    # zapata de tierra en la silleta
    mb.box((0.58 + 0.012, -0.05, 0.05), (0.58 + 0.02, -0.02, 0.08), "copper", bevel=0.0015, seg=1)
    wire(mb, [(0.6, -0.035, 0.06), (0.65, -0.035, 0.04), (0.7, -0.08, 0.004), (0.9, -0.15, 0.004)], 0.0045, mat="copper", bend=0.03, seg=13,
         nseg=4)
    return mb


# ================================================================================================ H-frame de acometida
def _ubolt(mb, x, z, R_post, y_back, y_front, r=0.005):
    """Abrazadera de tubo para unistrut (fleje de 1" × 12 ga): rodea el poste por detrás, sus orejas entran a la boca del canal
    y aprietan con tornillo y tuerca de resorte; tuercas visibles al frente."""
    Rb = R_post + 0.0018
    pts = [(x - Rb - 0.012, y_front + 0.004, z), (x - Rb, y_front + 0.004, z), (x - Rb, 0.0, z)]
    for k in range(1, 9):
        a = PI - PI * k / 9
        pts.append((x + Rb * math.cos(a), Rb * math.sin(a), z))
    pts += [(x + Rb, 0.0, z), (x + Rb, y_front + 0.004, z), (x + Rb + 0.012, y_front + 0.004, z)]
    sweep_frame(mb, [(-0.0014, -0.0125), (0.0014, -0.0125), (0.0014, 0.0125), (-0.0014, 0.0125)], _dedupe(pts), "galvanized",
                up=(0, 0, 1))
    for sx in (-1, 1):
        hexnut(mb, _T(x + sx * (Rb + 0.007), y_front, z) @ _Rx(90), s=0.0143, h=0.008, mat="galvanized")


def _conduit_strap(mb, x, z, Rc, yc, yf):
    """Abrazadera de dos orejas para conduit, atornillada al unistrut (cara frontal yf), conduit con eje en (x, yc)."""
    Rb = Rc + 0.0015
    pts = [(x - Rb - 0.016, yf - 0.0015, z), (x - Rb, yf - 0.0015, z), (x - Rb, yc, z)]
    for k in range(1, 12):
        a = PI + PI * k / 12
        pts.append((x + Rb * math.cos(a), yc + Rb * math.sin(a), z))
    pts += [(x + Rb, yc, z), (x + Rb, yf - 0.0015, z), (x + Rb + 0.016, yf - 0.0015, z)]
    sweep_frame(mb, [(-0.0015, -0.011), (0.0015, -0.011), (0.0015, 0.011), (-0.0015, 0.011)], _dedupe(pts), "galvanized",
                up=(0, 0, 1))
    for sx in (-1, 1):
        hexnut(mb, _T(x + sx * (Rb + 0.009), yf - 0.003, z) @ _Rx(90), s=0.0143, h=0.007, mat="galvanized")


def meter_hframe(seed=0):
    """H-frame de acometida eléctrica del sitio (origen: piso al centro; equipos al frente -Y). Dos postes galvanizados 2-7/8"
    OD en dados de concreto con tapones, tres canales unistrut 1-5/8" con abrazaderas de tubo, base de medidor ringless 200 A
    (catálogos Square D / Eaton: 14 × 11 × 4-3/8") con medidor digital de domo, interruptor de seguridad NEMA 3R con palanca
    lateral y portacandado, niple con contratuercas entre ambos, tubos conduit rígidos de 2" con coples y abrazaderas que bajan
    al piso, varilla de tierra con conector y conductor de cobre, etiquetas de advertencia en relieve."""
    r = rng(seed)
    mb = MB()
    Rp = R_TERM
    xp = 0.45
    ztop = 2.0
    for sx in (-1, 1):
        footing(mb, sx * xp, 0.0, Rp, 0.17, seed=seed * 3 + sx)
        pipe(mb, (sx * xp, 0, -0.05), (sx * xp, 0, ztop), Rp, caps=False)
        lathe(mb, [(Rp + 0.0022, ztop - 0.03), (Rp + 0.0022, ztop + 0.004), (Rp * 0.85, ztop + 0.016), (0.0, ztop + 0.02)], seg=SEG,
              mat="galvanized", M=_T(sx * xp, 0, 0), caps=False)
    ys = -Rp - 0.0018 - 0.0032                           # cara trasera de los canales (pegados al frente de los postes)
    zs = (0.5, 1.4)                                      # canal bajo: abrazaderas de conduit; canal alto: medidor y switch
    for z in zs:
        strut(mb, (-xp - 0.12, ys - 0.0413, z), (xp + 0.12, ys - 0.0413, z), up=(0, 1, 0))
        for sx in (-1, 1):
            _ubolt(mb, sx * xp, z, Rp, ys, ys - 0.0413)
    yf = ys - 0.0413                                     # cara frontal de los canales
    # base de medidor (lado izquierdo)
    xm, zm = -0.24, 1.42
    Mm = _MF(xm, yf, zm)
    slab(mb, Mm @ _T(0, 0, 0.0), 0.28, 0.36, 0.11, rc=0.012, re=0.004, mat="galvanized", nc=3, ne=1, re0=0.0, cap0=False)
    slab(mb, Mm @ _T(0, 0.005, 0.11), 0.27, 0.34, 0.006, rc=0.012, re=0.002, mat="galvanized", nc=3, ne=1, re0=0.0, cap0=False)
    slab(mb, Mm @ _T(0, 0.17, 0.0), 0.30, 0.04, 0.125, rc=0.006, re=0.003, mat="galvanized", nc=2, ne=1, re0=0.0, cap0=False)
    lathe(mb, [(0.088, 0.115), (0.094, 0.118), (0.094, 0.126), (0.086, 0.128)], seg=SEG, mat="galvanized", M=Mm @ _T(0, 0.03, 0),
          caps=False)
    Mt = Mm @ _T(0, 0.03, 0.126)                         # medidor digital: base, anillo, domo de vidrio, display
    lathe(mb, [(0.0, 0.0), (0.087, 0.0), (0.087, 0.03), (0.075, 0.034)], seg=SEG, mat="plastic", M=Mt, caps=False)
    lathe(mb, [(0.075, 0.034), (0.075, 0.105), (0.068, 0.125), (0.045, 0.136), (0.0, 0.139)], seg=SEG, mat="glass", M=Mt, caps=False)
    mb.box((-0.035, 0.005, 0.08), (0.035, 0.03, 0.084), "cable", bevel=0.0, m=Mt)
    mb.box((-0.04, -0.035, 0.07), (0.04, -0.01, 0.074), "sign_white", bevel=0.0, m=Mt)
    for k in range(2):                                   # tornillos del sello
        screw(mb, Mm @ _T(-0.1 + 0.2 * k, -0.15, 0.116), r=0.004, mat="steel", seg=8)
    # interruptor de seguridad (lado derecho)
    xd, zd = 0.22, 1.30
    Md = _MF(xd, yf, zd)
    slab(mb, Md @ _T(0, 0, 0.0), 0.30, 0.48, 0.16, rc=0.01, re=0.004, mat="galvanized", nc=3, ne=1, re0=0.0, cap0=False)
    slab(mb, Md @ _T(0, -0.006, 0.16), 0.288, 0.455, 0.008, rc=0.01, re=0.003, mat="galvanized", nc=3, ne=1, re0=0.0, cap0=False)
    slab(mb, Md @ _T(0, 0.235, 0.0), 0.33, 0.035, 0.18, rc=0.006, re=0.003, mat="galvanized", nc=2, ne=1, re0=0.0, cap0=False)
    for zz in (-0.15, 0.15):                             # bisagras de la tapa
        lathe(mb, [(0.006, -0.03), (0.006, 0.03)], seg=16, mat="galvanized", M=Md @ _T(-0.148, zz, 0.164) @ _Rx(90), caps=True)
    Mh = _T(xd + 0.15, yf - 0.08, zd + 0.06)             # palanca lateral de operación con portacandado
    lathe(mb, [(0.0, 0.0), (0.03, 0.0), (0.03, 0.012), (0.0, 0.015)], seg=SEG, mat="cable", M=Mh @ _Ry(90))
    rtube(mb, (xd + 0.165, yf - 0.08, zd + 0.06), (xd + 0.165, yf - 0.16, zd + 0.17), 0.016, 0.03, "cable", up=(1, 0, 0), r=0.004)
    rtube(mb, (xd + 0.165, yf - 0.16, zd + 0.17), (xd + 0.165, yf - 0.165, zd + 0.24), 0.024, 0.034, "sign_red", up=(1, 0, 0), r=0.008)
    holed(mb, _T(xd + 0.151, yf - 0.03, zd + 0.15) @ _Ry(90), (0, 0, 0.02, 0.012, 0.004), (0, 0, 0.006, 0.006, 0.006), 0.004, re_o=0.001,
          re_i=0.001, n=12, mat="galvanized", ne=1)
    # etiquetas en relieve
    for (M_, txt, sz, bg, fg) in ((Md @ _T(0, 0.10, 0.168), "WARNING", 0.024, "paint_yellow", "cable"),
                                  (Mm @ _T(0, -0.13, 0.117), "METER", 0.016, "sign_white", "cable")):
        w_ = len(txt) * sz * 0.72 + 0.02
        mb.box((-w_ / 2, -sz * 0.9, -0.0004), (w_ / 2, sz * 0.9, 0.0008), bg, bevel=0.0004, seg=1, m=M_)
        label(mb, txt, sz, fg, M_ @ _T(0, -sz * 0.36, 0.0008), depth=0.001, bold=True, res=2)
    # niple entre medidor y switch, conduits rígidos de 2" al piso con coples y abrazaderas
    Rc = 2.375 * IN / 2
    yc = yf - 0.06
    pipe(mb, (xm + 0.14, yc, zm - 0.06), (xd - 0.15, yc, zm - 0.06), 1.315 * IN / 2, mat="galvanized", caps=False)
    for xx in (xm + 0.14, xd - 0.15):
        lathe(mb, [(0.0185, -0.004), (0.026, -0.004), (0.026, 0.004), (0.0185, 0.004)], seg=6, mat="galvanized",
              M=_T(xx + (0.006 if xx < 0 else -0.006), yc, zm - 0.06) @ _Ry(90), phase=PI / 6, caps=True)
    for (xx, z_) in ((xm, zm - 0.18), (xd, zd - 0.24)):
        pipe(mb, (xx, yc, z_), (xx, yc, -0.05), Rc, caps=False)
        lathe(mb, [(Rc + 0.0005, z_ - 0.02), (Rc + 0.004, z_ - 0.018), (Rc + 0.004, z_), (Rc * 0.75, z_ + 0.004)], seg=SEG,
              mat="galvanized", M=_T(xx, yc, 0), caps=False)
        zc_ = 0.55
        lathe(mb, [(Rc + 0.0005, zc_ - 0.035), (Rc + 0.004, zc_ - 0.033), (Rc + 0.004, zc_ + 0.033), (Rc + 0.0005, zc_ + 0.035)], seg=SEG,
              mat="galvanized", M=_T(xx, yc, 0), caps=False)
        _conduit_strap(mb, xx, zs[0], Rc, yc, yf)
    # varilla de tierra con conector y conductor de cobre desde el switch
    gx, gy = 0.62, -0.25
    lathe(mb, [(0.008, -0.05), (0.008, 0.06), (0.006, 0.065), (0.0, 0.066)], seg=16, mat="copper", M=_T(gx, gy, 0), caps=False)
    lathe(mb, [(0.0075, 0.02), (0.014, 0.022), (0.014, 0.05), (0.0075, 0.052)], seg=16, mat="copper", M=_T(gx, gy, 0), caps=True)
    wire(mb, [(xd + 0.1, yf - 0.02, zd - 0.24), (xd + 0.1, yf - 0.03, 0.35), (gx - 0.02, gy + 0.02, 0.12), (gx - 0.0, gy, 0.037)],
         0.0042, mat="copper", bend=0.08, seg=13, nseg=4)
    return mb


# ============================================================================================================ poste de luz
def led_flood(mb, M):
    """Reflector LED de 150 W (~0,36 × 0,30 × 0,07 m, catálogos RAB / Stanpro): carcasa de aluminio inyectado con aletas
    disipadoras, marco y cristal templado, yugo con perillas y prensaestopa. M: centro de la carcasa, cristal hacia -Z local."""
    w, d, t = 0.34, 0.28, 0.05
    slab(mb, M @ _T(0, 0, -t / 2), w, d, t, rc=0.02, re=0.008, mat="aluminium", nc=3, ne=2)
    rrframe(mb, M @ _T(0, 0, -t / 2 - 0.006) @ _Rx(180) @ _T(0, 0, -0.006), (0, 0, w - 0.01, d - 0.01, 0.018), (0, 0, w - 0.05, d - 0.05, 0.008),
            0.006, re_o=0.003, re_i=0.002, n=3, ne=1, mat="aluminium")
    mb.box((-(w - 0.05) / 2, -(d - 0.05) / 2, -t / 2 - 0.004), ((w - 0.05) / 2, (d - 0.05) / 2, -t / 2 - 0.002), "glass", bevel=0.0, m=M)
    for k in range(9):                                   # aletas disipadoras
        x = -0.14 + 0.28 * k / 8
        mb.box((x - 0.0018, -d / 2 + 0.025, t / 2 - 0.002), (x + 0.0018, d / 2 - 0.025, t / 2 + 0.03), "aluminium", bevel=0.0012, seg=1,
               m=M)
    for sx in (-1, 1):                                   # yugo
        mb.box((sx * (w / 2 + 0.006) - 0.003, -0.02, -0.01), (sx * (w / 2 + 0.006) + 0.003, 0.02, 0.09), "aluminium", bevel=0.0015,
               seg=1, m=M)
        lathe(mb, [(0.0, 0.0), (0.016, 0.0), (0.016, 0.012), (0.012, 0.016), (0.0, 0.016)], seg=16, mat="cable",
              M=M @ _T(sx * (w / 2 + 0.009), 0, 0.0) @ _Ry(90 * sx))
    mb.box((-(w / 2 + 0.009), -0.02, 0.087), ((w / 2 + 0.009), 0.02, 0.095), "aluminium", bevel=0.002, seg=1, m=M)


def cctv_bullet(mb, A, d):
    """Cámara bala IP: cuerpo de 24 lados con visera curva, cristal frontal y anillo de LEDs IR, colgada de una rótula en el
    punto A (extremo del brazo); d = dirección de vista (unitaria, con inclinación hacia abajo)."""
    A, d = Vector(A), Vector(d).normalized()
    lathe(mb, [(0.0, -0.012), (0.014, -0.012), (0.018, 0.0), (0.014, 0.012), (0.0, 0.014)], seg=16, mat="sign_white", M=_T(*A))
    C = A + Vector((0, 0, -0.058))
    pipe(mb, A - Vector((0, 0, 0.006)), C + Vector((0, 0, 0.03)), 0.009, mat="sign_white", caps=False)
    Fc = frame_x(C - d * 0.09, C + d * 0.13, up=(0, 0, 1)) @ _Ry(90)
    revolve(mb, [(0.0, 0.0), (0.03, 0.0), (0.038, 0.012), (0.038, 0.205), (0.035, 0.215), (0.033, 0.215), (0.033, 0.212), (0.0, 0.212)],
            ["sign_white"] * 6 + ["cable"], seg=SEG, M=Fc)
    lathe(mb, [(0.0, 0.212), (0.012, 0.212), (0.012, 0.215), (0.0, 0.2155)], seg=16, mat="glass", M=Fc, caps=False)
    for k in range(6):
        a = 2 * PI * k / 6
        lathe(mb, [(0.0, 0.212), (0.004, 0.212), (0.004, 0.2135), (0.0, 0.214)], seg=8, mat="sign_red",
              M=Fc @ _T(0.022 * math.cos(a), 0.022 * math.sin(a), 0.0), caps=False)
    arc = [(-0.046 * math.cos(t), 0.046 * math.sin(t)) for t in [math.radians(-70 + 140 * k / 10) for k in range(11)]]
    prof = arc + [(x * 0.95, y * 0.95) for (x, y) in reversed(arc)]
    loft_rings(mb, [[Vector((x, y, zz)) for (x, y) in prof] for zz in (-0.005, 0.24)], "sign_white", M=Fc)
    mb.box((-0.0442, -0.006, 0.02), (-0.0372, 0.006, 0.2), "sign_white", bevel=0.001, seg=1, m=Fc)   # riel que sujeta la visera


def light_pole(h=6.0, seed=0, cctv=True):
    """Poste de alumbrado del recinto (origen: piso al centro). Poste redondo de acero galvanizado cónico (Ø 140 -> 90 mm,
    catálogos de postes de 20 ft / 6 m) sobre placa base con 4 anclas en dado de concreto con grout, registro de mano con tapa
    atornillada, tapón superior y espiga 2-3/8" con brazo y reflector LED de 150 W orientado hacia el recinto (+Y) y abajo 35°;
    con cctv, cámara bala IP en brazo a 4,2 m apuntando hacia la puerta (-Y) con caja de conexiones, flejes y cable que entra
    al poste por un pasacables."""
    mb = MB()
    zb = anchor_base(mb, 0.0, 0.0, plate=0.28, t=0.022, pier_r=0.24, pier_h=0.2, R_post=0.07, bolt_off=0.1, seed=seed)
    R0, R1 = 0.07, 0.045
    lathe(mb, [(R0, zb - 0.002), (R1, h), (R1 * 0.95, h + 0.006), (0.032, h + 0.01), (0.0302, h + 0.012)], seg=SEG, mat="galvanized",
          caps=False)
    ring(mb, _T(0, 0, zb + 0.004), R0 + 0.001, 0.004, n=SEG, seg=4)
    # registro de mano
    zh = zb + 0.45
    Rh = R0 - (R0 - R1) * (zh - zb) / (h - zb)
    Mh = _T(0, -Rh, zh) @ _Rx(90)
    slab(mb, Mh @ _T(0, 0, -0.004), 0.07, 0.16, 0.008, rc=0.02, re=0.003, mat="galvanized", nc=3, ne=1, re0=0.0, cap0=False)
    for zz in (-0.06, 0.06):
        screw(mb, Mh @ _T(0, zz, 0.004), r=0.004, mat="steel", seg=10)
    # espiga, brazo y reflector
    pipe(mb, (0, 0, h + 0.01), (0, 0, h + 0.11), 0.0302, caps=True)
    pipe(mb, (0, 0, h + 0.085), (0, 0.32, h + 0.085), 0.0302, caps=True)
    lathe(mb, [(0.0302, -0.03), (0.04, -0.028), (0.04, 0.028), (0.0302, 0.03)], seg=SEG, mat="galvanized", M=_T(0, 0, h + 0.085),
          caps=False)
    K = Vector((0.0, 0.32, h + 0.085))                   # nudillo del slipfitter en la punta del brazo
    lathe(mb, [(0.0302, -0.035), (0.036, -0.033), (0.036, 0.02), (0.03, 0.026), (0.0, 0.027)], seg=SEG, mat="aluminium",
          M=_T(*K) @ _Rx(-90) @ _T(0, 0, -0.01))
    Rf = _Rx(45)
    led_flood(mb, _T(*(K - Rf.to_3x3() @ Vector((0, 0, 0.091)))) @ Rf)
    wire(mb, [(0.03, 0.30, h + 0.075), (0.06, 0.33, h + 0.03), (0.15, 0.36, h + 0.0)], 0.0045, mat="cable", bend=0.02, seg=13, nseg=3)
    if cctv:
        zc = 4.2
        Rc_ = R0 - (R0 - R1) * (zc - zb) / (h - zb)
        for dz in (-0.06, 0.06):                         # flejes inoxidables
            ring(mb, _T(0, 0, zc + dz), Rc_ + 0.0012, 0.0012, n=SEG, seg=4, mat="steel")
        Mj = _T(0, -Rc_, zc) @ _Rx(90)                  # caja de conexiones redonda contra el poste y brazo
        lathe(mb, [(0.0, 0.0), (0.075, 0.0), (0.075, 0.045), (0.07, 0.05), (0.0, 0.05)], seg=SEG, mat="sign_white", M=Mj)
        pipe(mb, Mj @ Vector((0, 0.0, 0.05)), Mj @ Vector((0, 0.0, 0.16)), 0.016, mat="sign_white", caps=True)
        A = Mj @ Vector((0, -0.014, 0.17))
        a15 = math.radians(18)
        cctv_bullet(mb, A, (0.25, -math.cos(a15), -math.sin(a15)))
        wire(mb, [(0.05, -Rc_ - 0.01, zc - 0.04), (0.06, -Rc_ - 0.008, zc - 0.25), (0.02, -Rc_ - 0.004, zc - 0.32),
                  (0.0, -Rc_ + 0.002, zc - 0.33)], 0.003, mat="cable", bend=0.03, seg=13, nseg=3)
    return mb


# ================================================================================================================ letreros
def _zip_tie(mb, x, z, t):
    """Cincho de nylon negro que pasa por dos barrenos de la placa y abraza un alambre de la malla detrás (y > 0)."""
    pts = [(x - 0.007, -t - 0.0007, z), (x - 0.007, 0.004, z), (x - 0.004, 0.0115, z), (x + 0.004, 0.0115, z), (x + 0.007, 0.004, z),
           (x + 0.007, -t - 0.0007, z), (x + 0.0, -t - 0.0011, z)]
    sweep_frame(mb, [(-0.0006, -0.0023), (0.0006, -0.0023), (0.0006, 0.0023), (-0.0006, 0.0023)], pts, "cable", up=(0, 0, 1),
                caps=True)
    mb.box((x - 0.0105, -t - 0.0045, z - 0.003), (x - 0.0045, -t - 0.0005, z + 0.003), "cable", bevel=0.0)
    mb.box((x - 0.0175, -t - 0.0034, z - 0.0022), (x - 0.0105, -t - 0.0022, z + 0.0022), "cable", bevel=0.0, seg=1)


def _sign_base(w, h, face, mount="zip", t=0.0016, rc=0.012):
    """Placa de aluminio de 1,6 mm con cantos redondeados y cara impresa (capa de 0,3 mm); origen: espalda en y = 0, centro
    inferior; la cara mira a -Y. mount: 'zip' (2 cinchos a la malla en las esquinas superiores) o 'rivet' (4 remaches)."""
    mb = MB()
    slab(mb, _MF(0, 0, 0) @ _T(0, h / 2, 0), w, h, t, rc=rc, re=0.0006, mat="aluminium", nc=2, ne=1)
    slab(mb, _MF(0, -t + 0.0001, 0) @ _T(0, h / 2, 0), w - 0.004, h - 0.004, 0.0004, rc=rc - 0.002, re=0.0001, mat=face, nc=2, ne=1,
         re0=0.0, cap0=False)
    corners = [(sx * (w / 2 - 0.016), z) for sx in (-1, 1) for z in (0.016, h - 0.016)]
    if mount == "zip":
        for (x, z) in corners:
            if z > h / 2:
                _zip_tie(mb, x, z, t)
    else:
        for (x, z) in corners:
            lathe(mb, [(0.0043, -0.0002), (0.0043, 0.0005), (0.0032, 0.0013), (0.0, 0.0017)], seg=10, mat="aluminium",
                  M=_MF(x, -t - 0.0003, z), caps=False)
    return mb


def signs():
    """Letreros del sitio (dict nombre -> MB), placas de aluminio con cara impresa y texto en relieve de 1,2 mm (inglés, sin
    marcas). Origen de cada uno: espalda en y = 0 (malla, poste o muro), centro inferior; la cara mira a -Y.
    - 'AUTHORIZED PERSONNEL ONLY' 300 × 200, blanco con marco rojo, 2 cinchos (malla);
    - 'DANGER HIGH VOLTAGE' 254 × 178 (formato ANSI: banda negra con óvalo rojo 'DANGER'), 4 remaches;
    - 'RF EXPOSURE: DO NOT CLIMB' 254 × 178, amarillo con triángulo genérico de advertencia, 2 cinchos;
    - 'NO TRESPASSING' 300 × 150, blanco con letras rojas, 2 cinchos;
    - 'SITE ID 2047' 200 × 100, aluminio con letras negras, 4 remaches."""
    out = {}
    t = 0.0016
    yf = -t - 0.0004                                   # cara impresa

    def txt(mb, s, size, mat, x, z, bold=True):
        label(mb, s, size, mat, _MF(x, yf, z), depth=0.0012, bold=bold, res=RES)

    # AUTHORIZED PERSONNEL ONLY
    mb = _sign_base(0.30, 0.20, "sign_red")
    slab(mb, _MF(0, yf + 0.0001, 0.0) @ _T(0, 0.10, 0), 0.272, 0.172, 0.0003, rc=0.006, re=0.0001, mat="sign_white", nc=2, ne=1, re0=0.0,
         cap0=False)
    for k, s_ in enumerate(("AUTHORIZED", "PERSONNEL", "ONLY")):
        txt(mb, s_, 0.034, "cable", 0.0, 0.135 - k * 0.048)
    out["AUTHORIZED PERSONNEL ONLY"] = mb
    # DANGER HIGH VOLTAGE (encabezado tipo ANSI genérico)
    mb = _sign_base(0.254, 0.178, "sign_white", mount="rivet")
    mb.box((-0.119, yf - 0.0002, 0.112), (0.119, yf + 0.0001, 0.17), "cable", bevel=0.0, m=None)
    mb.plate(rr_pts(0.17, 0.042, 0.02, n=4), 0.0003, "sign_red", m=_MF(0, yf - 0.0002, 0.141) @ _T(0, 0, 0.0))
    txt(mb, "DANGER", 0.03, "sign_white", 0.0, 0.1295)
    txt(mb, "HIGH", 0.034, "cable", 0.0, 0.066)
    txt(mb, "VOLTAGE", 0.034, "cable", 0.0, 0.02)
    out["DANGER HIGH VOLTAGE"] = mb
    # RF EXPOSURE: DO NOT CLIMB
    mb = _sign_base(0.254, 0.178, "paint_yellow")
    tri = [(0.0, 0.05), (-0.044, -0.026), (0.044, -0.026)]
    mb.plate(tri, 0.0003, "cable", m=_MF(-0.075, yf - 0.0001, 0.11))
    mb.plate([(0.0, 0.034), (-0.031, -0.0175), (0.031, -0.0175)], 0.0003, "paint_yellow", m=_MF(-0.075, yf - 0.0003, 0.11))
    mb.box((-0.075 - 0.0035, yf - 0.0012, 0.104), (-0.075 + 0.0035, yf - 0.0003, 0.132), "cable", bevel=0.0)
    mb.box((-0.075 - 0.0035, yf - 0.0012, 0.094), (-0.075 + 0.0035, yf - 0.0003, 0.1005), "cable", bevel=0.0)
    txt(mb, "RF", 0.04, "cable", 0.05, 0.115)
    txt(mb, "EXPOSURE", 0.028, "cable", 0.0, 0.058)
    txt(mb, "DO NOT CLIMB", 0.024, "cable", 0.0, 0.018)
    out["RF EXPOSURE: DO NOT CLIMB"] = mb
    # NO TRESPASSING
    mb = _sign_base(0.30, 0.15, "sign_white")
    txt(mb, "NO", 0.05, "sign_red", 0.0, 0.08)
    txt(mb, "TRESPASSING", 0.033, "sign_red", 0.0, 0.03)
    out["NO TRESPASSING"] = mb
    # SITE ID 2047
    mb = _sign_base(0.20, 0.10, "aluminium", mount="rivet", rc=0.008)
    txt(mb, "SITE ID", 0.022, "cable", 0.0, 0.058)
    txt(mb, "2047", 0.032, "cable", 0.0, 0.02)
    out["SITE ID 2047"] = mb
    return out


def sign(name="SITE ID 2047"):
    """Un letrero de signs() por nombre (para revisión con tests/render_pieza.py)."""
    return signs()[name]


# ======================================================================================================= interior de caseta
U = 0.04445                                            # 1U de rack de 19"
W19 = 0.4826                                           # ancho de panel de 19"


def _cells(mb, x0, z0, cols, rows, cw, ch, gap=0.0016, depth=0.0034, mat="cable", wall="cable", inner="rubber"):
    """Arreglo de puertos rehundidos en la cara y = 0 (mira a -Y) a partir de la esquina (x0, z0): fondo oscuro casi al ras y
    marco + divisiones que sobresalen `depth` (las celdas quedan hundidas). Puertos RJ45, LC/SC, SFP."""
    W_ = cols * cw + (cols + 1) * gap
    H_ = rows * ch + (rows + 1) * gap
    mb.box((x0, -0.0003, z0), (x0 + W_, 0.002, z0 + H_), inner, bevel=0.0)
    for i in range(cols + 1):
        x = x0 + i * (cw + gap)
        mb.box((x, -depth, z0), (x + gap, 0.0, z0 + H_), wall, bevel=0.0)
    for j in range(rows + 1):
        z = z0 + j * (ch + gap)
        mb.box((x0, -depth, z), (x0 + W_, 0.0, z + gap), wall, bevel=0.0)
    return W_, H_


def _leds(mb, xs, z, mats, r=0.0012):
    for x, m in zip(xs, mats):
        mb.box((x - r, -0.0009, z - r), (x + r, 0.0002, z + r), m, bevel=0.0)


def _chassis(mb, nU, mat="cable", d=0.42, ears=True, ear_mat=None):
    """Chasis de equipo de rack de 19" (frente en y = 0 mirando a -Y, z de 0 a nU) con orejas atornilladas a los rieles."""
    h = nU * U - 0.0008
    mb.box((-0.2165, 0.0, 0.0004), (0.2165, d, h + 0.0004), mat, bevel=0.0015, seg=1)
    if ears:
        for sx in (-1, 1):
            mb.box((sx * 0.2165 - (0.0 if sx > 0 else 0.0225) + (0.0 if sx < 0 else 0.0), -0.0025, 0.0004),
                   (sx * 0.2165 + (0.0225 if sx > 0 else 0.0), 0.0, h + 0.0004), ear_mat or mat, bevel=0.0008, seg=1)
            for k in range(nU):
                zz = k * U + U / 2
                lathe(mb, [(0.0035, 0.0), (0.0035, 0.001), (0.0018, 0.0022), (0.0, 0.0025)], seg=8, mat="steel",
                      M=_T(sx * 0.2325, -0.0025, zz) @ _Rx(90))
    return h


def eq_switch(n=24, mat="cable"):
    """Switch / patch de 1U con n puertos RJ45 en dos filas y LEDs."""
    mb = MB()
    _chassis(mb, 1, mat)
    cols = n // 2
    _cells(mb, -0.17, 0.006, cols, 2, 0.0115, 0.0125, wall="aluminium" if mat == "cable" else "cable")
    _leds(mb, [0.15, 0.158, 0.166, 0.174], 0.03, ["sign_green", "sign_green", "paint_yellow", "sign_green"])
    _cells(mb, 0.13, 0.006, 2, 1, 0.0135, 0.0095, wall="aluminium")      # 2 SFP
    return mb, 1


def eq_patch(n=24):
    """Panel de parcheo de 1U (24 puertos) con tira de etiquetas."""
    mb = MB()
    _chassis(mb, 1, "cable", d=0.08)
    _cells(mb, -0.19, 0.012, n, 1, 0.0118, 0.0135, gap=0.0018, wall="cable", inner="rubber")
    mb.box((-0.19, -0.0012, 0.0045), (0.19, 0.0, 0.0105), "sign_white", bevel=0.0)
    return mb, 1


def eq_odf():
    """Charola de distribución de fibra (ODF) de 1U con 24 adaptadores LC dúplex azules y jumpers amarillos."""
    mb = MB()
    _chassis(mb, 1, "cable", d=0.3)
    for k in range(12):
        x = -0.17 + k * 0.026
        mb.box((x, -0.008, 0.007), (x + 0.02, 0.0, 0.037), "plastic_blue", bevel=0.0008, seg=1)
        mb.box((x + 0.003, -0.0085, 0.012), (x + 0.0085, -0.006, 0.032), "cable", bevel=0.0)
        mb.box((x + 0.0115, -0.0085, 0.012), (x + 0.017, -0.006, 0.032), "cable", bevel=0.0)
    return mb, 1


def eq_bbu():
    """Unidad de banda base (BBU) de 2U: 6 tarjetas con jaladeras, puertos SFP y LEDs, módulo de ventiladores con rejilla."""
    mb = MB()
    _chassis(mb, 2, "aluminium", ear_mat="aluminium")
    for k in range(6):
        col, row = k % 3, k // 3
        x0 = -0.205 + col * 0.12
        z0 = 0.004 + row * 0.042
        mb.box((x0, -0.0025, z0), (x0 + 0.117, 0.0, z0 + 0.040), "aluminium", bevel=0.0006, seg=1)
        for sx in (0, 1):                           # jaladeras con tornillo cautivo
            xx = x0 + 0.004 + sx * 0.104
            mb.box((xx, -0.012, z0 + 0.006), (xx + 0.009, -0.0025, z0 + 0.034), "cable", bevel=0.0015, seg=1)
        _cells(mb, x0 + 0.02, z0 + 0.012, 3, 1, 0.0135, 0.0095, gap=0.0015, depth=0.003, wall="aluminium")
        _leds(mb, [x0 + 0.08, x0 + 0.087, x0 + 0.094], z0 + 0.03, ["sign_green", "sign_green", "sign_red" if k == 4 else "sign_green"])
    mb.box((0.155, -0.003, 0.004), (0.215, 0.0, 0.085), "aluminium", bevel=0.0008, seg=1)
    for k in range(9):
        z = 0.012 + k * 0.0082
        mb.box((0.161, -0.0042, z), (0.209, -0.003, z + 0.0035), "cable", bevel=0.0)
    return mb, 2


def eq_router():
    """Router / IDU de microondas de 1U con 8 SFP, consola y LEDs."""
    mb = MB()
    _chassis(mb, 1, "cable")
    _cells(mb, -0.12, 0.008, 8, 1, 0.0135, 0.0095, gap=0.0016, wall="aluminium")
    _cells(mb, 0.05, 0.007, 2, 1, 0.0115, 0.0125, wall="aluminium")
    _leds(mb, [-0.17, -0.162, -0.154, 0.12, 0.128], 0.026, ["sign_green", "sign_green", "paint_yellow", "sign_blue", "sign_green"])
    mb.box((0.15, -0.002, 0.012), (0.2, 0.0, 0.032), "aluminium", bevel=0.0005, seg=1)
    return mb, 1


def eq_server():
    """Servidor de 1U con 8 bahías de disco con jaladeras y panel de control."""
    mb = MB()
    _chassis(mb, 1, "cable", d=0.6)
    for k in range(8):
        x = -0.205 + k * 0.042
        mb.box((x, -0.003, 0.004), (x + 0.04, 0.0, 0.04), "aluminium", bevel=0.0006, seg=1)
        mb.box((x + 0.004, -0.0055, 0.008), (x + 0.03, -0.003, 0.014), "cable", bevel=0.0)
        _leds(mb, [x + 0.035], 0.034, ["sign_green"])
    mb.box((0.15, -0.0025, 0.006), (0.205, 0.0, 0.038), "aluminium", bevel=0.0006, seg=1)
    _leds(mb, [0.16, 0.168], 0.03, ["sign_blue", "sign_green"])
    return mb, 1


def eq_blank(nU=1):
    """Tapa ciega de nU con dobleces."""
    mb = MB()
    h = nU * U - 0.0008
    mb.box((-0.2405, -0.0022, 0.0004), (0.2405, 0.0, h + 0.0004), "cable", bevel=0.0008, seg=1)
    mb.box((-0.2165, 0.0, 0.0024), (0.2165, 0.012, h - 0.0016), "cable", bevel=0.0, seg=1)
    return mb, nU


def eq_cm(nU=1):
    """Organizador horizontal de cables de nU con 8 dedos."""
    mb = MB()
    h = nU * U - 0.0008
    mb.box((-0.2405, 0.0, 0.0004), (0.2405, 0.003, h + 0.0004), "cable", bevel=0.0008, seg=1)
    for k in range(9):
        x = -0.2 + k * 0.05
        mb.box((x - 0.004, -0.06, 0.006), (x + 0.004, 0.0, h - 0.004), "cable", bevel=0.0018, seg=1)
    return mb, nU


def eq_rectifier():
    """Repisa de rectificadores de 2U: 4 módulos de 48 V con rejilla, jaladera y LEDs + controlador con display y teclas."""
    mb = MB()
    _chassis(mb, 2, "sign_white", ear_mat="aluminium")
    for k in range(4):
        x0 = -0.21 + k * 0.083
        mb.box((x0, -0.003, 0.003), (x0 + 0.081, 0.0, 0.085), "aluminium", bevel=0.0006, seg=1)
        for j in range(6):
            z = 0.02 + j * 0.0095
            mb.box((x0 + 0.01, -0.0042, z), (x0 + 0.071, -0.003, z + 0.004), "cable", bevel=0.0)
        mb.box((x0 + 0.025, -0.016, 0.006), (x0 + 0.056, -0.003, 0.014), "cable", bevel=0.002, seg=1)
        _leds(mb, [x0 + 0.06, x0 + 0.068, x0 + 0.076], 0.078, ["sign_green", "sign_green", "paint_yellow"])
    mb.box((0.124, -0.003, 0.003), (0.214, 0.0, 0.085), "sign_white", bevel=0.0006, seg=1)
    mb.box((0.132, -0.0045, 0.045), (0.206, -0.003, 0.077), "glass", bevel=0.0)
    mb.box((0.137, -0.0052, 0.05), (0.2, -0.0045, 0.072), "sign_blue", bevel=0.0)
    for k in range(4):
        mb.box((0.135 + k * 0.019, -0.008, 0.016), (0.148 + k * 0.019, -0.003, 0.03), "plastic", bevel=0.0015, seg=1)
    return mb, 2


def eq_dcdist():
    """Distribución de CD de 2U: 12 interruptores termomagnéticos con palanca y tira de etiquetas."""
    mb = MB()
    _chassis(mb, 2, "sign_white", ear_mat="aluminium")
    mb.box((-0.2, -0.002, 0.012), (0.2, 0.0, 0.074), "cable", bevel=0.0)
    for k in range(12):
        x = -0.195 + k * 0.0328
        mb.box((x, -0.022, 0.016), (x + 0.03, -0.002, 0.07), "sign_white", bevel=0.0015, seg=1)
        mb.box((x + 0.011, -0.03, 0.04 + (0.0 if k % 5 else -0.012)), (x + 0.019, -0.022, 0.054 + (0.0 if k % 5 else -0.012)),
               "cable", bevel=0.0012, seg=1)
    mb.box((-0.2, -0.0015, 0.076), (0.2, 0.0, 0.084), "sign_white", bevel=0.0)
    return mb, 2


def eq_battery():
    """Módulo de batería de litio 48 V 100 Ah de 3U: jaladeras, display de estado, interruptor, bornes con tapas roja y negra,
    puertos de comunicación, rejilla."""
    mb = MB()
    _chassis(mb, 3, "cable", d=0.48)
    for sx in (-1, 1):
        rtube(mb, (sx * 0.19, -0.03, 0.02), (sx * 0.19, -0.03, 0.115), 0.012, 0.012, "aluminium", up=(1, 0, 0), r=0.003)
        for zz in (0.02, 0.115):
            mb.box((sx * 0.19 - 0.008, -0.03, zz - 0.006), (sx * 0.19 + 0.008, 0.0, zz + 0.006), "aluminium", bevel=0.002, seg=1)
    mb.box((-0.15, -0.0025, 0.07), (-0.07, 0.0, 0.11), "cable", bevel=0.0005, seg=1)
    mb.box((-0.145, -0.0035, 0.077), (-0.075, -0.0025, 0.103), "sign_blue", bevel=0.0)
    mb.box((-0.04, -0.018, 0.075), (0.0, -0.002, 0.11), "plastic", bevel=0.0025, seg=1)
    mb.box((-0.026, -0.026, 0.083), (-0.014, -0.018, 0.103), "sign_red", bevel=0.0015, seg=1)
    for k, m in enumerate(("sign_red", "cable")):
        mb.box((0.03 + k * 0.05, -0.022, 0.02), (0.07 + k * 0.05, -0.002, 0.055), m, bevel=0.003, seg=1)
    _cells(mb, 0.03, 0.075, 2, 1, 0.0115, 0.0125, wall="aluminium")
    _leds(mb, [-0.15 + k * 0.012 for k in range(5)], 0.05, ["sign_green"] * 4 + ["paint_yellow"])
    for k in range(5):
        mb.box((-0.15, -0.0012, 0.018 + k * 0.006), (-0.07, 0.0, 0.021 + k * 0.006), "rubber", bevel=0.0)
    return mb, 3


def _rack(mb, M, w=0.6, d=0.8, h=2.0, items=(), jumpers=0, seed=0):
    """Gabinete de 19" 42U (w × d × h; catálogos Lehmann / Danbit 600 × 600-1000 × 2000) negro, sin puerta frontal: zócalo
    con rejilla, 4 postes de perfil redondeado, marcos superior e inferior, laterales y espalda de lámina, techo con pasacables
    de cepillo atrás, rieles de 19" con perforación implícita y el equipo `items` (constructores eq_* de abajo hacia arriba;
    None = 1U libre). jumpers: n de jumpers de fibra amarillos en lazo al frente. Local: centro de la huella, frente -Y."""
    from kit.clinic_equipo import rtube_lo
    r = rng(seed)
    P = lambda x, y, z: M @ Vector((x, y, z))           # noqa: E731
    mb.box((-w / 2 + 0.01, -d / 2 + 0.03, 0.0), (w / 2 - 0.01, d / 2 - 0.01, 0.1), "cable", bevel=0.002, seg=1, m=M)
    mb.box((-w / 2 + 0.05, -d / 2 + 0.028, 0.025), (w / 2 - 0.05, -d / 2 + 0.03, 0.075), "rubber", bevel=0.0, m=M)
    for k in range(10):                                  # rejilla del zócalo
        xx = -w / 2 + 0.06 + k * (w - 0.12) / 9
        mb.box((xx - 0.004, -d / 2 + 0.024, 0.028), (xx + 0.004, -d / 2 + 0.03, 0.072), "cable", bevel=0.0, m=M)
    pw = 0.04
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (w / 2 - pw / 2 - 0.002), sy * (d / 2 - pw / 2)
            rtube_lo(mb, P(x, y, 0.1), P(x, y, h - 0.03), pw, pw, "cable", up=tuple(M.to_3x3() @ Vector((1, 0, 0))), r=0.005)
    for z in (0.1 + 0.02, h - 0.05):
        for sy in (-1, 1):
            rtube_lo(mb, P(-w / 2 + 0.042, sy * (d / 2 - 0.02), z), P(w / 2 - 0.042, sy * (d / 2 - 0.02), z), 0.04, 0.03, "cable",
                     up=tuple(M.to_3x3() @ Vector((0, 0, 1))), r=0.004)
        for sx in (-1, 1):
            rtube_lo(mb, P(sx * (w / 2 - 0.022), -d / 2 + 0.042, z), P(sx * (w / 2 - 0.022), d / 2 - 0.042, z), 0.04, 0.03, "cable",
                     up=tuple(M.to_3x3() @ Vector((0, 0, 1))), r=0.004)
    for sx in (-1, 1):                                   # laterales de lámina con canto redondo
        slab(mb, M @ _T(sx * (w / 2 - 0.0005), 0.0, 0.1) @ _Ry(90 * sx) @ _Rz(0), 0.0, 0.0, 0.0) if False else None
        mb.box((sx * w / 2 - (0.0012 if sx > 0 else 0.0), -d / 2 + 0.004, 0.1), (sx * w / 2 + (0.0 if sx > 0 else 0.0012), d / 2 - 0.004,
               h - 0.022), "cable", bevel=0.0006, seg=1, m=M)
    mb.box((-w / 2 + 0.004, d / 2 - 0.0012, 0.1), (w / 2 - 0.004, d / 2, h - 0.022), "cable", bevel=0.0006, seg=1, m=M)
    mb.box((-w / 2, -d / 2, h - 0.022), (w / 2, d / 2, h), "cable", bevel=0.004, seg=2, m=M)
    mb.box((-0.18, d / 2 - 0.2, h), (0.18, d / 2 - 0.06, h + 0.006), "rubber", bevel=0.0015, seg=1, m=M)   # pasacables de cepillo
    yr = -d / 2 + 0.06                                   # rieles de 19"
    for sx in (-1, 1):
        x0 = sx * 0.2325
        mb.box((x0 - 0.008, yr, 0.1), (x0 + 0.008, yr + 0.002, 0.1 + 42 * U + 0.01), "aluminium", bevel=0.0004, seg=1, m=M)
        mb.box((sx * 0.2405 - 0.001, yr, 0.1), (sx * 0.2405 + 0.001, yr + 0.022, 0.1 + 42 * U + 0.01), "aluminium", bevel=0.0, m=M)
    u = 0
    placed = []
    for it in items:
        if it is None:
            u += 1
            continue
        src, nU = it
        placed.append((u, nU, src))
        mb.join(src, M @ _T(0, yr, 0.1 + u * U))
        u += nU
    if jumpers:                                          # jumpers de fibra en lazo desde la ODF a las tarjetas
        odf = [p for p in placed if p[2] is items[-1][0]] if False else None
        z_hi = 0.1 + (u - 1.5) * U
        z_lo = 0.1 + 6 * U
        for k in range(jumpers):
            xa = -0.16 + 0.31 * k / max(jumpers - 1, 1)
            xb = -0.18 + 0.36 * ((k * 5) % jumpers) / max(jumpers - 1, 1)
            za = z_hi - (k % 2) * 0.012
            zb = z_lo + (k % 3) * 0.04
            sag = 0.05 + 0.03 * float(r.random())
            pts = [P(xa, yr - 0.008, za), P(xa, yr - 0.04, za - 0.02), P(xa * 0.7 + 0.21, yr - 0.07 - 0.01 * (k % 3), (za + zb) / 2 + 0.05),
                   P(0.215, yr - 0.055, (za + zb) / 2 - sag), P(xb, yr - 0.045, zb + 0.03), P(xb, yr - 0.012, zb)]
            wire(mb, pts, 0.0015, mat="paint_yellow", seg=13, bend=0.03, nseg=3)
    return yr


def _offset_route(route, o):
    """Desplaza lateralmente (izquierda del avance = +) una ruta en planta [(x, y)] con ingletes en las esquinas."""
    P = [Vector((x, y, 0)) for (x, y) in route]
    out = []
    n = len(P)
    for i in range(n):
        if i == 0:
            t = (P[1] - P[0]).normalized()
            nrm = Vector((-t.y, t.x, 0))
            out.append(P[0] + nrm * o)
        elif i == n - 1:
            t = (P[-1] - P[-2]).normalized()
            nrm = Vector((-t.y, t.x, 0))
            out.append(P[-1] + nrm * o)
        else:
            t0 = (P[i] - P[i - 1]).normalized()
            t1 = (P[i + 1] - P[i]).normalized()
            n0, n1 = Vector((-t0.y, t0.x, 0)), Vector((-t1.y, t1.x, 0))
            b = (n0 + n1)
            b = b / max(b.length, 1e-6)
            out.append(P[i] + b * (o / max(b.dot(n0), 0.3)))
    return [(p.x, p.y) for p in out]


def _ladder_tray(mb, p0, p1, z, w=0.3, rung_phase=0.0, mat="galvanized"):
    """Charola tipo escalera (300 mm interior) de p0 a p1 en planta a la altura z (cama de peldaños): largueros de canal de
    75 mm y peldaños de 25 × 12 cada 30 cm."""
    from kit.clinic_equipo import rtube_lo
    p0, p1 = Vector((p0[0], p0[1], z)), Vector((p1[0], p1[1], z))
    t = (p1 - p0).normalized()
    nrm = Vector((-t.y, t.x, 0))
    L = (p1 - p0).length
    for s in (-1, 1):
        a = p0 + nrm * s * (w / 2 + 0.01)
        b = p1 + nrm * s * (w / 2 + 0.01)
        chan(mb, tuple(a + Vector((0, 0, 0.025))), tuple(b + Vector((0, 0, 0.025))), 0.02, 0.075, 0.002, mat=mat, up=(0, 0, 1),
             open_dir=s if (t.x > 0.5 or t.y < -0.5) else -s)
    k = 0
    while True:
        sv = rung_phase + 0.3 * k
        if sv > L - 0.05:
            break
        if sv > 0.05:
            c = p0 + t * sv
            rtube_lo(mb, tuple(c - nrm * (w / 2) - Vector((0, 0, 0.006))), tuple(c + nrm * (w / 2) - Vector((0, 0, 0.006))), 0.025, 0.012, mat,
                     up=(0, 0, 1), r=0.002)
        k += 1


def _trapeze(mb, c, along, z_under, H, w=0.3):
    """Soporte trapecio: unistrut bajo la charola colgado de 2 varillas roscadas de 3/8" al plafón, con tuercas y rondanas."""
    c = Vector(c)
    t = Vector(along).normalized()
    nrm = Vector((-t.y, t.x, 0))
    a = c + nrm * (w / 2 + 0.07)
    b = c - nrm * (w / 2 + 0.07)
    strut(mb, (a.x, a.y, z_under), (b.x, b.y, z_under), up=(0, 0, 1))
    for p in (c + nrm * (w / 2 + 0.04), c - nrm * (w / 2 + 0.04)):
        mb.cyl((p.x, p.y, z_under - 0.06), (p.x, p.y, H), 0.0048, seg=13, mat="galvanized", caps=True)
        hexnut(mb, _T(p.x, p.y, z_under), s=0.0143, h=0.008, mat="galvanized")
        hexnut(mb, _T(p.x, p.y, z_under - 0.0413) @ _Rx(180), s=0.0143, h=0.008, mat="galvanized")
        lathe(mb, [(0.0048, H - 0.03), (0.011, H - 0.025), (0.011, H)], seg=16, mat="galvanized", caps=False, M=_T(p.x, p.y, 0))


def _entry_port(mb, x_wall, yc, zc, ncol=4, nrow=2, used=8):
    """Puerto de entrada de cables (placa de 4" × ncol × nrow) en el muro x = x_wall (cara interior, sobresale hacia -X):
    marco atornillado, botas de hule con abrazadera inoxidable en cada cable y tapones en los puertos libres.
    Devuelve las salidas [(punto, radio)] de las botas usadas."""
    pitch = 0.12
    Wp, Hp = ncol * pitch + 0.06, nrow * pitch + 0.06
    M = _T(x_wall, yc, zc) @ _Rz(90) @ _Rx(90)          # XY local sobre el muro, +Z hacia -X (adentro)
    slab(mb, M @ _T(0, 0, -0.0005), Wp, Hp, 0.012, rc=0.012, re=0.003, mat="galvanized", nc=3, ne=1, re0=0.0, cap0=False)
    for sx in (-1, 1):
        for sy in (-1, 1):
            bolt(mb, M @ _T(sx * (Wp / 2 - 0.018), sy * (Hp / 2 - 0.018), 0.012), d=0.01, mat="galvanized", seg=8)
    outs = []
    k = 0
    for j in range(nrow):
        for i in range(ncol):
            x = (i - (ncol - 1) / 2) * pitch
            y = ((nrow - 1) / 2 - j) * pitch
            Mb = M @ _T(x, y, 0.012)
            if k < used:                                 # bota: brida, cuerpo cónico escalonado y cuello sobre el cable
                lathe(mb, [(0.0, 0.0), (0.05, 0.0), (0.05, 0.012), (0.042, 0.016), (0.03, 0.06), (0.026, 0.07), (0.016, 0.085),
                           (0.0135, 0.11)], seg=SEG, mat="rubber", M=Mb, caps=False)
                ring(mb, Mb @ _T(0, 0, 0.1), 0.0148, 0.0018, mat="steel", n=SEG, seg=4)
                mb.box((0.012, -0.004, 0.096), (0.024, 0.004, 0.104), "steel", bevel=0.001, seg=1, m=Mb)
                outs.append((Mb @ Vector((0, 0, 0.11)), 0.0115))
            else:
                lathe(mb, [(0.0, 0.0), (0.05, 0.0), (0.05, 0.012), (0.04, 0.02), (0.0, 0.024)], seg=SEG, mat="rubber", M=Mb, caps=False)
            k += 1
    return outs


def _ground_bar(mb, x_wall, yc, zc, n=8, wire_ends=None):
    """Barra de tierra de cobre 600 × 100 × 6,4 mm sobre aisladores y ménsulas en el muro x = x_wall (sobresale a -X), con
    zapatas de dos barrenos y conductores verdes. wire_ends: puntos a donde llegan los conductores."""
    M = _T(x_wall, yc, zc) @ _Rz(90) @ _Rx(90)
    for sx in (-1, 1):
        mb.box((sx * 0.33 - 0.015, -0.03, 0.0), (sx * 0.33 + 0.015, 0.03, 0.006), "steel", bevel=0.0015, seg=1, m=M)
        lathe(mb, [(0.018, 0.006), (0.018, 0.012), (0.015, 0.016), (0.015, 0.03), (0.018, 0.034), (0.018, 0.045)], seg=SEG,
              mat="plastic", M=M @ _T(sx * 0.3, 0, 0))
    mb.box((-0.3, -0.05, 0.045), (0.3, 0.05, 0.0514), "copper", bevel=0.0015, seg=1, m=M)
    ends = []
    for k in range(n):
        x = -0.26 + 0.52 * k / (n - 1)
        Ml = M @ _T(x, 0.0, 0.0514)
        mb.box((-0.009, -0.03, 0.0), (0.009, 0.035, 0.004), "copper", bevel=0.001, seg=1, m=Ml)
        for zz in (-0.012, 0.012):
            hexnut(mb, Ml @ _T(0, zz, 0.004), s=0.011, h=0.006, mat="steel")
        lathe(mb, [(0.0065, 0.035), (0.008, 0.042), (0.008, 0.06), (0.0055, 0.064)], seg=16, mat="copper", M=Ml @ _Rx(-90) @ _T(0, -0.002, 0))
        ends.append(Ml @ Vector((0, 0.064, 0.002)))
    return ends


def _alarm_panel(mb, M):
    """Panel de alarmas / control de acceso de acero inoxidable con display LCD, teclado de 12 teclas y LEDs. M: muro (XY
    local sobre el muro, +Z hacia afuera), origen centro inferior."""
    slab(mb, M @ _T(0, 0.22, 0), 0.34, 0.44, 0.1, rc=0.006, re=0.003, mat="steel", nc=2, ne=1, re0=0.0, cap0=False)
    slab(mb, M @ _T(0, 0.22, 0.1), 0.33, 0.43, 0.004, rc=0.006, re=0.0015, mat="steel", nc=2, ne=1, re0=0.0, cap0=False)
    Mf = M @ _T(0, 0, 0.104)
    mb.box((-0.11, 0.3, -0.0005), (0.03, 0.37, 0.002), "cable", bevel=0.0006, seg=1, m=Mf)
    mb.box((-0.104, 0.306, 0.002), (0.024, 0.364, 0.0026), "sign_green", bevel=0.0, m=Mf)
    for i in range(3):
        for j in range(4):
            mb.box((-0.1 + i * 0.033, 0.13 + j * 0.035, -0.0005), (-0.075 + i * 0.033, 0.155 + j * 0.035, 0.005), "plastic", bevel=0.0015,
                   seg=1, m=Mf)
    for k, m in enumerate(("sign_green", "sign_red", "paint_yellow", "sign_green")):
        mb.box((0.07, 0.35 - k * 0.025, -0.0005), (0.08, 0.36 - k * 0.025, 0.003), m, bevel=0.0, m=Mf)
    for sx in (-1, 1):
        for sy in (0.03, 0.41):
            screw(mb, Mf @ _T(sx * 0.15, sy, 0), r=0.004, mat="steel", seg=8)
    label(mb, "ALARM", 0.018, "cable", Mf @ _T(0.11, 0.05, 0.0), depth=0.001, res=2)


def _led_panel(mb, x, y, H, L=1.2, W=0.3):
    """Luminaria LED de sobreponer 1200 × 300 × 40: marco de aluminio redondeado, difusor opal y caja de driver."""
    slab(mb, _T(x, y, H - 0.04), L, W, 0.04, rc=0.012, re=0.004, mat="aluminium", nc=3, ne=1, re0=0.004)
    mb.box((x - L / 2 + 0.02, y - W / 2 + 0.02, H - 0.0415), (x + L / 2 - 0.02, y + W / 2 - 0.02, H - 0.039), "sign_white", bevel=0.0)


def _desk(mb, M, seed=0):
    """Escritorio abatible de muro (tablero 800 × 450 laminado con canto, 2 ménsulas plegables con brazo diagonal) con laptop
    abierta. M: muro (origen al piso, XY con X a lo largo del muro, +Y hacia afuera del muro)."""
    zt = 0.74
    rbox(mb, (-0.4, 0.0, zt), (0.4, 0.45, zt + 0.028), "plastic", r=0.004, m=M)
    for sx in (-1, 1):
        x = sx * 0.33
        rbox(mb, (x - 0.02, 0.0, zt - 0.32), (x + 0.02, 0.006, zt + 0.02), "steel", r=0.002, m=M)     # riel de muro
        rbox(mb, (x - 0.012, 0.006, zt - 0.025), (x + 0.012, 0.4, zt), "steel", r=0.002, m=M)        # brazo horizontal
        from kit.clinic_equipo import rtube_lo
        rtube_lo(mb, M @ Vector((x, 0.008, zt - 0.3)), M @ Vector((x, 0.3, zt - 0.03)), 0.016, 0.016, "steel",
                 up=tuple(M.to_3x3() @ Vector((1, 0, 0))), r=0.003)
    # laptop: base con teclado y pantalla abierta 110°
    Ml = M @ _T(0.05, 0.24, zt + 0.028) @ _Rz(-8)
    slab(mb, Ml, 0.33, 0.23, 0.016, rc=0.01, re=0.003, mat="cable", nc=3, ne=1)
    mb.box((-0.14, -0.045, 0.016), (0.14, 0.075, 0.0172), "rubber", bevel=0.0, m=Ml)
    for i in range(12):
        for j in range(4):
            mb.box((-0.135 + i * 0.0228, -0.04 + j * 0.028, 0.0168), (-0.117 + i * 0.0228, -0.022 + j * 0.028, 0.0185), "cable",
                   bevel=0.0, m=Ml)
    mb.box((-0.05, -0.1, 0.016), (0.05, -0.06, 0.0168), "rubber", bevel=0.0, m=Ml)
    Ms = Ml @ _T(0, 0.115, 0.016) @ _Rx(110 - 90)
    slab(mb, Ms @ _T(0, -0.003, 0.0) @ _Rx(90) @ _T(0, 0.11, 0), 0.33, 0.22, 0.006, rc=0.01, re=0.002, mat="cable", nc=3, ne=1)
    mb.box((-0.15, 0.0, 0.012), (0.15, 0.0005, 0.205), "sign_blue", bevel=0.0, m=Ms @ _T(0, -0.0095, 0))
    wire(mb, [tuple(Ml @ Vector((0.165, 0.0, 0.008))), tuple(Ml @ Vector((0.21, -0.02, -0.01))), tuple(M @ Vector((0.38, 0.1, zt))),
              tuple(M @ Vector((0.4, 0.06, zt - 0.2))), tuple(M @ Vector((0.38, 0.02, zt - 0.35)))], 0.002, mat="cable", seg=13,
         bend=0.04, nseg=3)
