"""com_builder.py — COM_1_antena: sitio de telecomunicaciones celular actual (2026, no futurista) que da cobertura a una ciudad
costera chica: torre autosoportada de tres patas tubulares galvanizada de 42 m, caseta prefabricada de concreto con su centro
de equipos, gabinetes exteriores, generador con tanque, marco H de acometida y compound de grava con malla ciclónica.

Ejes de Blender, metros; frente hacia -Y (portón del compound y puerta de la caseta); pivote al centro del compound a nivel
del terreno (z = 0). Sin terreno: lo que se entrega es la plataforma construida (guarnición perimetral, cama de grava,
banquetas y losas) y lo que va encima.
  compound  x -8..8 · y -8..8 (eje de la malla), guarnición de concreto de 0,30 m bajo la malla, grava a z 0,10.
  caseta    x -6,4..-0,6 · y 2,35..5,65 (exterior; muros prefabricados de 0,10 m), firme de desplante a z 0,15, piso
            interior a z 0,30, losa de techo 3,00–3,20 con pendiente hacia atrás. Puerta en el muro del frente (-y), puerto de
            cables en el muro oriente (+x) a y 4,6 / z 2,6, donde llega el puente de cables desde la torre.
  torre     al nororiente del compound (ver TOWER); gabinetes en losa al sur de la torre; generador y tanque al sureste.
Proporciones de fuentes reales (R-AAA punto 7) anotadas en ESTADO.md.
Grafiti (regla R-GRAF): pocas piezas chicanas solo en la trasera de la caseta (graffiti_com.py).
"""
import math

import bpy  # noqa: F401
import numpy as np
from mathutils import Matrix, Vector

from kit import clinic as cl
from kit import clinic_equipo as ce
from kit import services as sv
from kit.common import MB, get_collection, rng, wall_with_openings

# ------------------------------------------------------------------------------------------------------------ compound
CX0, CX1, CY0, CY1 = -8.0, 8.0, -8.0, 8.0          # eje de la malla
CURB_W, CURB_TOP = 0.30, 0.18                       # guarnición bajo la malla
Z_GRAVEL = 0.10
Z_WALK = 0.12                                       # banquetas 2 cm sobre la grava
GATE_X0, GATE_X1 = -7.6, -3.6                       # vano del portón (ejes de los postes del portón)
# ------------------------------------------------------------------------------------------------------------ caseta
SH_X0, SH_X1, SH_Y0, SH_Y1 = -6.4, -0.6, 2.35, 5.65
SH_T = 0.10                                         # muro prefabricado
Z_PAD = 0.15                                        # firme de desplante
Z_FLOOR = 0.30                                      # piso interior
Z_CEIL = 3.00
ROOF_T0, ROOF_T1 = 0.20, 0.16                       # peralte de la losa al frente y atrás (pendiente hacia +y)
ROOF_OVH = 0.10
CH = 0.03                                           # chaflán de las esquinas de la caseta
DOOR_W, DOOR_H = 0.914, 2.134                       # puerta de 36" x 84" (claro libre)
DOOR_CX = -5.40
DX0, DX1 = DOOR_CX - DOOR_W / 2, DOOR_CX + DOOR_W / 2
FRAME = 0.05
PORT = (4.6, 2.6)                                   # (y, z) del puerto de cables en el muro oriente
IN_CX, IN_CY = (SH_X0 + SH_X1) / 2, (SH_Y0 + SH_Y1) / 2
IN_L, IN_W, IN_H = SH_X1 - SH_X0 - 2 * SH_T, SH_Y1 - SH_Y0 - 2 * SH_T, Z_CEIL - Z_FLOOR
# ------------------------------------------------------------------------------------------------------------ equipo
TOWER = dict(x=3.6, y=3.4, rot=0.0)                 # centroide de la torre y giro en z (se ajusta con tower.tower_mounts)
CAB_PAD = (1.4, 5.8, -2.0, -0.95)                   # losa de gabinetes (x0, x1, y0, y1)
GEN_PAD = (1.6, 7.0, -6.9, -4.4)                    # losa del generador y su tanque
WALKS = [   # banquetas (x0, x1, y0, y1): del portón a la caseta, ramal a los gabinetes y al generador
    (-6.05, -4.75, -7.85, 2.10),
    (-4.75, 5.80, -3.05, -2.05),
    (3.30, 4.30, -4.40, -3.05),
]
APRON = (GATE_X0 + 0.15, GATE_X1 - 0.15, CY0 - 0.60, CY0 + 0.15)    # losa del portón (pasa bajo la malla, sale 0,6 m)


def _T(x=0.0, y=0.0, z=0.0):
    return Matrix.Translation((x, y, z))


def _Rz(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Z")


def _Rx(deg):
    return Matrix.Rotation(math.radians(deg), 4, "X")


def _Ry(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Y")


def face_to(d):
    """Giro en Z para que el frente local (-Y) de una pieza mire hacia d ('-y', '+x', '+y', '-x')."""
    return _Rz({"-y": 0, "+x": 90, "+y": 180, "-x": -90}[d])


def cfg_com(bid="COM_1_antena"):
    fp = [(SH_X0, SH_X1, SH_Y0, SH_Y1)]
    return dict(id=bid, seed=113, xs=[CX0, CX1], ys=[CY0, CY1], h=[0.0], band_top=2.4,
                graffiti_bounds=(SH_X0 - 0.2, SH_X1 + 0.2, SH_Y0 - 0.2, SH_Y1 + 0.2), graffiti_px_per_m=150.0,
                exterior_footprint=fp,
                lookdev=dict(base_z=Z_PAD, graffiti_mats=("concrete",), paint_tint=(0.90, 0.90, 0.88), wear=0.06,
                             band=None, paint_sat=0.15))


# ------------------------------------------------------------------------------------------------------------ registros
LIGHTS = []        # luminarias para el motor (interior de la caseta, arbotante, reflectores)
PROXIES = []       # cajas de colisión de lo que va en Detalle/Mobiliario


def _proxy_box(mn, mx):
    PROXIES.append([[round(c, 3) for c in mn], [round(c, 3) for c in mx]])


def _proxy(piece, M, pad=0.0):
    pts = [M @ v.co for v in piece.bm.verts]
    if not pts:
        return
    mn = [min(p[i] for p in pts) - pad for i in range(3)]
    mx = [max(p[i] for p in pts) + pad for i in range(3)]
    _proxy_box(mn, mx)


def _noise2(r, n):
    """Ruido de valor suave en una rejilla n x n (0..1), para la ondulación de la grava."""
    g = r.random((n // 8 + 3, n // 8 + 3))
    from PIL import Image
    img = Image.fromarray((g * 255).astype(np.uint8)).resize((n, n), Image.BICUBIC)
    return np.asarray(img, np.float64) / 255.0


# ------------------------------------------------------------------------------------------------------------ caseta
def shelter_shell(shell, roof):
    """Caseta prefabricada: cuatro muros de concreto de 10 cm con las esquinas en chaflán, losa de piso integrada (z 0,15–0,30)
    y losa de techo con vuelo de 10 cm, aristas boleadas y pendiente hacia atrás. Vano de la puerta y del puerto de cables."""
    zb, zt = Z_PAD, Z_CEIL + 0.01                   # el muro entra 1 cm en la losa de techo (sin caras coplanares)
    H = zt - zb
    Lx = SH_X1 - SH_X0 - 2 * CH
    Ly = SH_Y1 - SH_Y0 - 2 * CH
    ro = (DX0 - FRAME - 0.004, DX1 + FRAME + 0.004, Z_FLOOR, Z_FLOOR + DOOR_H + FRAME + 0.004)   # vano bruto de la puerta
    front = [(ro[0] - (SH_X0 + CH), ro[1] - (SH_X0 + CH), ro[2] - zb, ro[3] - zb)]
    wall_with_openings(shell, Lx, H, SH_T, front, "concrete", "paint_white", "concrete", m=_T(SH_X0 + CH, SH_Y0, zb))
    wall_with_openings(shell, Lx, H, SH_T, [], "concrete", "paint_white", "concrete", m=_T(SH_X1 - CH, SH_Y1, zb) @ _Rz(180))
    py, pz = PORT
    east = [(py - 0.20 - (SH_Y0 + CH), py + 0.20 - (SH_Y0 + CH), pz - 0.10 - zb, pz + 0.10 - zb)]
    wall_with_openings(shell, Ly, H, SH_T, east, "concrete", "paint_white", "concrete", m=_T(SH_X1, SH_Y0 + CH, zb) @ _Rz(90))
    wall_with_openings(shell, Ly, H, SH_T, [], "concrete", "paint_white", "concrete", m=_T(SH_X0, SH_Y1 - CH, zb) @ _Rz(-90))
    for (cx, cy, sx, sy) in ((SH_X0, SH_Y0, 1, 1), (SH_X1, SH_Y0, -1, 1), (SH_X1, SH_Y1, -1, -1), (SH_X0, SH_Y1, 1, -1)):
        a = (cx + sx * CH, cy, 0)
        b = (cx, cy + sy * CH, 0)
        q = [(a[0], a[1], zb), (b[0], b[1], zb), (b[0], b[1], zt), (a[0], a[1], zt)]
        if sx * sy < 0:
            q = list(reversed(q))
        shell.poly(q, "concrete")
    # losa de piso (canto bajo los muros; la cara superior es el piso de la caseta)
    shell.box((SH_X0 + SH_T - 0.002, SH_Y0 + SH_T - 0.002, zb), (SH_X1 - SH_T + 0.002, SH_Y1 - SH_T + 0.002, Z_FLOOR),
              "concrete", bevel=0.0)
    # losa de techo: aristas boleadas de 2 cm, pendiente de 4 cm hacia atrás
    x0, x1, y0, y1 = SH_X0 - ROOF_OVH, SH_X1 + ROOF_OVH, SH_Y0 - ROOF_OVH, SH_Y1 + ROOF_OVH
    tmp = MB()
    tmp.box((x0, y0, Z_CEIL), (x1, y1, Z_CEIL + ROOF_T0), "concrete", bevel=0.02, seg=3)
    for v in tmp.bm.verts:
        if v.co.z > Z_CEIL + ROOF_T0 * 0.5:
            v.co.z -= (ROOF_T0 - ROOF_T1) * (v.co.y - y0) / (y1 - y0)
    # gotero: ranura de 12 mm bajo el vuelo a 4 cm del canto (la losa se arma con un listón bajo el canto)
    roof.join(tmp)
    for (a, b, c, d) in ((x0 + 0.035, x1 - 0.035, y0 + 0.035, y0 + 0.047), (x0 + 0.035, x1 - 0.035, y1 - 0.047, y1 - 0.035),
                         (x0 + 0.035, x0 + 0.047, y0 + 0.047, y1 - 0.047), (x1 - 0.047, x1 - 0.035, y0 + 0.047, y1 - 0.047)):
        roof.box((a, c, Z_CEIL - 0.010), (b, d, Z_CEIL + 0.002), "rubber", bevel=0.0)   # tapajuntas oscuro del gotero


def roof_z(y):
    """Cota de la cara superior de la losa de techo en y."""
    y0, y1 = SH_Y0 - ROOF_OVH, SH_Y1 + ROOF_OVH
    return Z_CEIL + ROOF_T0 - (ROOF_T0 - ROOF_T1) * (y - y0) / (y1 - y0)


def roof_details(det):
    """Insertos de izaje con tapón, dos antenas GPS de sincronía en mástil corto y la membrana de juntas del perímetro."""
    for (x, y) in ((SH_X0 + 0.6, SH_Y0 + 0.5), (SH_X1 - 0.6, SH_Y0 + 0.5), (SH_X0 + 0.6, SH_Y1 - 0.5), (SH_X1 - 0.6, SH_Y1 - 0.5)):
        z = roof_z(y)
        det.cyl((x, y, z - 0.02), (x, y, z + 0.004), 0.055, seg=32, mat="concrete")          # anillo de mortero del inserto
        det.cyl((x, y, z - 0.02), (x, y, z + 0.009), 0.034, seg=32, mat="plastic")           # tapón del inserto
        det.cyl((x, y, z + 0.009), (x, y, z + 0.013), 0.012, seg=24, mat="plastic")
    for k, x in enumerate((SH_X1 - 0.35, SH_X1 - 0.75)):
        y = SH_Y1 - 0.25
        z = roof_z(y)
        # base de lastre (bloque de hule reciclado) con mástil
        cl.rbox(det, (x - 0.14, y - 0.14, z), (x + 0.14, y + 0.14, z + 0.06), "rubber", r=0.012)
        det.cyl((x, y, z + 0.06), (x, y, z + 0.075), 0.045, seg=32, mat="galvanized")
        det.cyl((x, y, z + 0.075), (x, y, z + 0.42), 0.0167, seg=24, mat="galvanized")
        det.cyl((x, y, z + 0.42), (x, y, z + 0.44), 0.020, seg=24, mat="galvanized")
        # antena GPS tipo hongo: base y domo de radomo
        ce.lathe(det, [(0.0, 0.0), (0.046, 0.0), (0.050, 0.010), (0.052, 0.030), (0.046, 0.052), (0.032, 0.066),
                       (0.016, 0.073), (0.0, 0.075)], seg=32, mat="radome", M=_T(x, y, z + 0.44))
        # cable que baja por el muro trasero, da vuelta a la esquina y entra por una bota del puerto (muro oriente)
        zc = Z_CEIL - 0.14 - 0.05 * k
        yc = SH_Y1 + 0.012 + 0.012 * k
        xc = SH_X1 + 0.012 + 0.012 * k
        ye = SH_Y1 + ROOF_OVH
        ze = roof_z(ye)
        pts = cl.fillet([(x, y + 0.03, z + 0.43), (x, y + 0.06, z + 0.12), (x, y + 0.14, roof_z(y + 0.14) + 0.006),
                         (x, ye - 0.03, ze + 0.006), (x, ye + 0.008, ze - 0.03), (x, ye + 0.008, Z_CEIL - 0.07),
                         (x, yc, Z_CEIL - 0.09), (x, yc, zc), (SH_X1 - 0.03, yc, zc), (xc, yc, zc), (xc, SH_Y1 - 0.03, zc),
                         (xc, PORT[0] + 0.30, zc), (xc + 0.03, PORT[0] + 0.195 - 0.13 * k, PORT[1] + 0.20),
                         (SH_X1 + 0.08, PORT[0] + 0.195 - 0.13 * k, PORT[1] + 0.085), (SH_X1 + 0.05, PORT[0] + 0.195 - 0.13 * k, PORT[1] + 0.085)],
                        0.035, 6)
        det.tube(pts, 0.0045, seg=12, mat="cable")
        cl.rtube(det, ((x + SH_X1) / 2 - 0.012, yc, zc), ((x + SH_X1) / 2 + 0.012, yc, zc), 0.014, 0.016, "plastic",
                 up=(0, 0, 1), r=0.002)                               # grapas al muro
        cl.rtube(det, (xc, (SH_Y1 + PORT[0]) / 2 + 0.15 - 0.012, zc), (xc, (SH_Y1 + PORT[0]) / 2 + 0.15 + 0.012, zc), 0.014, 0.016,
                 "plastic", up=(0, 0, 1), r=0.002)


def door(det, ang=72.0):
    """Puerta exterior de lámina aislada de 36 x 84" en marco de lámina con tope, abatible hacia afuera (bisagras de balero con
    pasador fijo del lado de la calle), manija de palanca y cerrojo, placa de patada, cierrapuertas de brazo paralelo por
    dentro, burlete, umbral de aluminio y gotero sobre el marco."""
    y0 = SH_Y0
    zf = Z_FLOOR
    # marco: jambas y cabezal (tubo de lámina 50 x 112 mm) con el tope de 16 mm
    for (xa, xb) in ((DX0 - FRAME, DX0), (DX1, DX1 + FRAME)):
        cl.rbox(det, (xa, y0 - 0.006, zf), (xa + (xb - xa), y0 + SH_T + 0.006, zf + DOOR_H), "enamel", r=0.003)
    cl.rbox(det, (DX0 - FRAME, y0 - 0.006, zf + DOOR_H), (DX1 + FRAME, y0 + SH_T + 0.006, zf + DOOR_H + FRAME), "enamel", r=0.003)
    for (xa, xb) in ((DX0, DX0 + 0.016), (DX1 - 0.016, DX1)):
        cl.rbox(det, (xa, y0 + 0.052, zf), (xb, y0 + 0.068, zf + DOOR_H), "enamel", r=0.002)
    cl.rbox(det, (DX0, y0 + 0.052, zf + DOOR_H - 0.016), (DX1, y0 + 0.068, zf + DOOR_H), "enamel", r=0.002)
    # burlete sobre el tope (lado exterior)
    for (xa, xb) in ((DX0 + 0.016, DX0 + 0.024), (DX1 - 0.024, DX1 - 0.016)):
        det.box((xa, y0 + 0.046, zf + 0.01), (xb, y0 + 0.052, zf + DOOR_H - 0.016), "rubber", bevel=0.002)
    det.box((DX0 + 0.024, y0 + 0.046, zf + DOOR_H - 0.024), (DX1 - 0.024, y0 + 0.052, zf + DOOR_H - 0.016), "rubber", bevel=0.002)
    # sello entre marco y vano (cordón de sellador)
    for x in (DX0 - FRAME - 0.002, DX1 + FRAME + 0.002):
        det.cyl((x, y0 - 0.002, zf), (x, y0 - 0.002, zf + DOOR_H + FRAME + 0.002), 0.004, seg=12, mat="rubber")
    det.cyl((DX0 - FRAME - 0.002, y0 - 0.002, zf + DOOR_H + FRAME + 0.002), (DX1 + FRAME + 0.002, y0 - 0.002, zf + DOOR_H + FRAME + 0.002),
            0.004, seg=12, mat="rubber")
    # umbral de aluminio con estrías
    cl.rbox(det, (DX0, y0 - 0.035, zf), (DX1, y0 + SH_T, zf + 0.010), "aluminium", r=0.003)
    for k in range(6):
        y = y0 - 0.025 + k * 0.018
        det.box((DX0 + 0.01, y, zf + 0.010), (DX1 - 0.01, y + 0.004, zf + 0.012), "aluminium", bevel=0.0008)
    # gotero sobre la puerta
    gz = zf + DOOR_H + FRAME + 0.05
    # (sweep sobre +X con normal +Z: la x del perfil va hacia -Y, afuera del muro)
    det.sweep([(0.0, 0.0), (0.0, 0.025), (0.065, 0.006), (0.072, -0.012), (0.066, -0.014), (0.060, 0.000), (0.006, 0.016),
               (0.006, 0.0)], [(DX0 - 0.13, y0, gz), (DX1 + 0.13, y0, gz)], mat="aluminium", normal=(0, 0, 1))
    for x in (DX0 - 0.13, DX1 + 0.13):                              # tapas de los extremos del gotero
        det.box((x - 0.0015 if x < DOOR_CX else x, y0 - 0.068, gz - 0.012), (x if x < DOOR_CX else x + 0.0015, y0, gz + 0.022),
                "aluminium", bevel=0.0)
    # hoja
    M = _T(DX0 + 0.002, y0 + 0.002, zf + 0.006) @ _Rz(-ang)
    leaf = cl.MB()
    W, H, T = 0.905, DOOR_H - 0.010, 0.045
    cl.rbox(leaf, (0.004, 0.0, 0.0), (W, T, H), "enamel", r=0.004)
    # junta de las caras (lámina de 18 ga en bandeja): canal fino en el canto
    leaf.box((0.004 - 0.0006, T * 0.5 - 0.001, 0.02), (0.0046, T * 0.5 + 0.001, H - 0.02), "rubber", bevel=0.0)
    # placa de patada de acero inoxidable (exterior: cara y = 0)
    leaf.box((0.03, -0.0018, 0.010), (W - 0.03, -0.0002, 0.26), "steel", bevel=0.0007)
    for x in (0.05, W / 2, W - 0.05):
        for z in (0.03, 0.24):
            ce.screw(leaf, _T(x, -0.0018, z) @ _Rx(90), d=0.006, mat="steel")
    # bisagras (3) con nudillo del lado exterior
    for z in (0.20, 1.06, H - 0.30):
        leaf.cyl((0.0, -0.004, z), (0.0, -0.004, z + 0.114), 0.0095, seg=24, mat="steel")
        leaf.cyl((0.0, -0.004, z + 0.114), (0.0, -0.004, z + 0.120), 0.0060, seg=24, mat="steel")
        leaf.cyl((0.0, -0.004, z - 0.006), (0.0, -0.004, z), 0.0060, seg=24, mat="steel")
        for k in range(1, 5):
            leaf.cyl((0.0, -0.004, z + k * 0.0228 - 0.0006), (0.0, -0.004, z + k * 0.0228 + 0.0006), 0.0098, seg=24, mat="steel")
        leaf.box((0.004, -0.0028, z + 0.004), (0.050, -0.0004, z + 0.110), "steel", bevel=0.0008)
    # herrajes de la cara exterior (y < 0) e interior (y > T): roseta, palanca, cerrojo
    lx = W - 0.068
    for (side, yy) in ((-1, 0.0), (1, T)):
        R = _T(lx, yy, 1.02) @ _Rx(90 if side < 0 else -90)
        ce.lathe(leaf, [(0.0, 0.0), (0.034, 0.0), (0.036, 0.003), (0.034, 0.008), (0.018, 0.012), (0.016, 0.022), (0.0, 0.022)],
                 seg=32, mat="steel", M=R)
        path = cl.fillet([(lx, yy + side * 0.020, 1.02), (lx, yy + side * 0.058, 1.02), (lx - 0.125, yy + side * 0.060, 1.02),
                          (lx - 0.128, yy + side * 0.045, 1.02)], 0.018, 8)
        leaf.tube(path, 0.0085, seg=16, mat="steel")
        Rd = _T(lx, yy, 1.18) @ _Rx(90 if side < 0 else -90)
        ce.lathe(leaf, [(0.0, 0.0), (0.030, 0.0), (0.031, 0.004), (0.022, 0.010), (0.018, 0.016), (0.0, 0.016)], seg=32,
                 mat="steel", M=Rd)
        if side < 0:
            leaf.box((lx - 0.0015, yy - 0.0175, 1.18 - 0.007), (lx + 0.0015, yy - 0.0160, 1.18 + 0.007), "rubber", bevel=0.0)
        else:
            leaf.box((lx - 0.004, yy + 0.016, 1.18 - 0.018), (lx + 0.004, yy + 0.030, 1.18 + 0.018), "steel", bevel=0.002)
    # cierrapuertas por dentro (cara y = T, arriba): cuerpo, tapas, brazo paralelo a la zapata del marco
    cz = H - 0.12
    cl.rbox(leaf, (0.10, T, cz - 0.03), (0.40, T + 0.055, cz + 0.035), "aluminium", r=0.012)
    for x in (0.10, 0.40):
        leaf.cyl((x - 0.003 if x < 0.2 else x, T + 0.0275, cz + 0.002), (x + 0.003 if x < 0.2 else x + 0.006, T + 0.0275, cz + 0.002),
                 0.026, seg=24, mat="plastic")
    leaf.cyl((0.16, T + 0.055, cz), (0.16, T + 0.070, cz), 0.012, seg=24, mat="steel")
    det.join(leaf, M)
    arm_a = M @ Vector((0.16, T + 0.064, cz))
    arm_c = Vector((DX0 + 0.30, y0 + SH_T + 0.03, zf + DOOR_H - 0.03))
    arm_b = arm_a.lerp(arm_c, 0.55) + Vector((0.0, 0.10, 0.0))
    for (p, q) in ((arm_a, arm_b), (arm_b, arm_c)):
        cl.rtube(det, tuple(p), tuple(q), 0.016, 0.006, "steel", r=0.002)
    cl.rbox(det, (arm_c.x - 0.05, y0 + SH_T + 0.006, arm_c.z - 0.012), (arm_c.x + 0.05, y0 + SH_T + 0.03, arm_c.z + 0.02),
            "aluminium", r=0.004)
    return M


def wall_services(det, r):
    """Lo que va colgado de la caseta por fuera: condensadoras de los minisplits en ménsula con su tubería forrada, arbotante LED
    sobre la puerta, estrobo de alarma, caja de conexión del generador, barra de tierras exterior y el puerto de entrada de
    cables con su capucha."""
    y0 = SH_Y0
    for k, x in enumerate((-3.75, -2.20)):
        ac_ = cl.remap(sv.ac_unit("split_outdoor", seed=int(r.integers(1e6)), detail="high"),
                       {"metal_rust": "enamel", "metal_paint": "sign_white"})
        det.join(ac_, _T(x, y0, 0.78))
        _proxy_box((x - 0.42, y0 - 0.38, 0.55), (x + 0.42, y0, 1.36))
        # tubería forrada (canaleta de PVC 80 x 60 con codos) de la condensadora al muro, arriba
        pts = [(x + 0.30, y0 - 0.12, 1.18), (x + 0.30, y0 - 0.12, 1.40), (x + 0.30, y0 - 0.04, 1.52), (x + 0.30, y0 - 0.04, 2.55),
               (x + 0.30, y0, 2.62)]
        P = cl.fillet(pts, 0.06, 6)
        for a, b in zip(P[:-1], P[1:]):
            cl.rtube(det, a, b, 0.080, 0.060, "plastic", up=(1, 0, 0), r=0.006)
        det.cyl((x + 0.30, y0 - 0.001, 2.62), (x + 0.30, y0 - 0.025, 2.62), 0.055, seg=32, mat="plastic")   # tapa pasamuro
        # desagüe del condensado
        det.tube(cl.fillet([(x - 0.25, y0 - 0.18, 0.80), (x - 0.25, y0 - 0.18, 0.60), (x - 0.25, y0 - 0.26, Z_PAD + 0.12),
                            (x - 0.25, y0 - 0.34, Z_PAD + 0.12)], 0.04, 6), 0.008, seg=12, mat="plastic")
    # arbotante LED sobre la puerta (carcasa de aluminio fundido con aletas, difusor)
    wz = Z_FLOOR + DOOR_H + 0.32
    wp = cl.MB()
    cl.zloft(wp, [(0.000, 0.26, 0.14, 0.02), (0.012, 0.26, 0.14, 0.02), (0.020, 0.25, 0.13, 0.02), (0.120, 0.22, 0.10, 0.02),
                  (0.140, 0.20, 0.09, 0.02)], seg=24, mat="aluminium")
    wp.transform(_Rx(90))
    for k in range(7):
        x = -0.09 + k * 0.03
        wp.box((x - 0.002, -0.13, 0.04), (x + 0.002, -0.02, 0.07), "aluminium", bevel=0.0008)
    wp.box((-0.10, -0.13, -0.065), (0.10, -0.03, -0.055), "plastic", bevel=0.003)
    det.join(wp, _T(DOOR_CX, y0, wz))
    LIGHTS.append([DOOR_CX, y0 - 0.12, round(wz - 0.08, 3)])
    # estrobo de alarma
    det.cyl((SH_X1 - 0.45, y0, 2.70), (SH_X1 - 0.45, y0 - 0.04, 2.70), 0.055, seg=32, mat="plastic")
    ce.lathe(det, [(0.0, 0.0), (0.045, 0.0), (0.046, 0.02), (0.035, 0.05), (0.0, 0.056)], seg=32, mat="sign_red",
             M=_T(SH_X1 - 0.45, y0 - 0.04, 2.70) @ _Rx(90))
    # caja de conexión del generador (muro poniente): gabinete NEMA 3R con tapa abisagrada y tubo conduit al piso
    gx = SH_X0
    gy = 3.30
    cab = cl.MB()
    cl.rbox(cab, (-0.30, -0.22, 0.0), (0.30, 0.0, 0.70), "enamel", r=0.008)
    cl.rbox(cab, (-0.29, -0.235, 0.02), (0.29, -0.218, 0.68), "enamel", r=0.004)
    for z in (0.12, 0.58):
        cab.cyl((0.292, -0.226, z - 0.04), (0.292, -0.226, z + 0.04), 0.007, seg=16, mat="steel")
    cl.rbox(cab, (-0.27, -0.25, 0.32), (-0.23, -0.235, 0.40), "steel", r=0.003)
    cab.cyl((-0.25, -0.255, 0.36), (-0.25, -0.265, 0.36), 0.008, seg=16, mat="steel")
    cab.box((-0.22, -0.2362, 0.48), (0.10, -0.2352, 0.62), "sign_white", bevel=0.0)
    cl.text(cab, "GENERATOR CONNECTION", 0.018, 0.0006, "cable", M=_T(-0.06, -0.2362, 0.575) @ _Rx(90))
    cl.text(cab, "DANGER 240V", 0.016, 0.0006, "sign_red", M=_T(-0.06, -0.2362, 0.52) @ _Rx(90))
    det.join(cab, _T(gx, gy, 1.00) @ _Rz(-90))
    for dx in (-0.12, 0.12):                       # conduit del fondo de la caja al firme (plano del muro: x local = gy - y)
        det.join(cl.remap(sv.conduit([(dx, 0.0, 1.00), (dx, 0.0, Z_PAD - 0.03)], seed=int(r.integers(1e6)), detail="high"),
                          {"metal_rust": "galvanized", "metal_paint": "galvanized"}), _T(gx, gy, 0.0) @ _Rz(-90))
    # barra de tierras exterior bajo el puerto (cobre con aisladores) y sus bajantes al anillo de tierras
    py, pz = PORT
    gb = cl.MB()
    gb.box((-0.25, -0.035, -0.025), (0.25, -0.029, 0.025), "copper", bevel=0.0015)
    for x in (-0.22, 0.22):
        gb.cyl((x, 0.0, 0.0), (x, -0.029, 0.0), 0.012, seg=24, mat="plastic")
        gb.box((x - 0.012, -0.002, -0.03), (x + 0.012, 0.0, 0.03), "steel", bevel=0.0006)
    for k in range(10):
        x = -0.18 + k * 0.04
        for z in (-0.009, 0.009):
            ce.hexnut(gb, _T(x, -0.035, z) @ _Rx(90), d=0.006, mat="steel")
    det.join(gb, _T(SH_X1, py, 1.25) @ _Rz(90))
    for k, dy in enumerate((-0.16, -0.08, 0.0, 0.08, 0.16)):
        pts = cl.fillet([(SH_X1 + 0.045, py + dy, 1.24), (SH_X1 + 0.06, py + dy, 1.05), (SH_X1 + 0.06, py + dy * 0.4, Z_PAD + 0.30),
                         (SH_X1 + 0.22, py + dy * 0.2, Z_PAD + 0.05), (SH_X1 + 0.30, py + dy * 0.2, Z_PAD - 0.04)], 0.05, 6)
        det.tube(pts, 0.0055, seg=12, mat="sign_green" if k % 2 == 0 else "copper")
    # puerto de entrada de cables (12 botas de hule de 4") con capucha
    port = cl.MB()
    cl.rbox(port, (-0.28, -0.012, -0.16), (0.28, 0.0, 0.16), "galvanized", r=0.004)
    for i in range(4):
        for j in range(3):
            u, v = -0.195 + i * 0.13, -0.085 + j * 0.085
            port.cyl((u, -0.012, v), (u, -0.022, v), 0.040, seg=32, mat="galvanized")
            ce.lathe(port, [(0.0, 0.0), (0.036, 0.0), (0.036, 0.020), (0.030, 0.030), (0.030, 0.052), (0.026, 0.060),
                            (0.0, 0.060)], seg=24, mat="rubber", M=_T(u, -0.022, v) @ _Rx(90))
            port.cyl((u, -0.040, v), (u, -0.050, v), 0.0325, seg=24, mat="steel")    # abrazadera
    for (u, v) in ((-0.26, -0.14), (0.26, -0.14), (-0.26, 0.14), (0.26, 0.14)):
        ce.hexnut(port, _T(u, -0.012, v) @ _Rx(90), d=0.008, mat="steel")
    # capucha de lámina doblada
    rain_hood(port, 0.0, 0.40, 0.68, 0.19, 0.17, screen=False)
    det.join(port, _T(SH_X1, py, pz) @ _Rz(90))


def rain_hood(mb, x, z, w, h, d, screen=True, mat="galvanized", t=0.0012):
    """Capucha de lámina contra lluvia en el plano local del muro (y = 0, afuera = -y), centrada en x, con su ceja superior a z:
    frente vertical, tapa inclinada que vuelve al muro, costados trapezoidales, ceja de fijación con pijas y, abajo, malla
    contra aves (o abierta si screen=False)."""
    x0, x1 = x - w / 2, x + w / 2
    zt, zb = z, z - h
    rise = min(0.06, h * 0.3)
    # costados (trapecio: atrás llega más alto)
    for xx, sg in ((x0, 1), (x1, -1)):
        q = [(xx, 0.0, zb), (xx, -d, zb), (xx, -d, zt - rise), (xx, 0.0, zt)]
        for k, off in enumerate((0.0, sg * t)):
            pts = [(p[0] + off, p[1], p[2]) for p in q]
            mb.poly(pts if (sg > 0) == (k == 1) else list(reversed(pts)), mat)
        for a, b in zip(q, q[1:] + q[:1]):
            mb.poly([a, b, (b[0] + sg * t, b[1], b[2]), (a[0] + sg * t, a[1], a[2])], mat)
    # frente y tapa (lámina con dobleces boleados)
    path = cl.fillet([(x0, -0.002, zt + 0.004), (x0, -d, zt - rise), (x0, -d, zb), (x0, -d + 0.02, zb - 0.004)], 0.012, 4)
    prof = [(p[1], p[2]) for p in path]
    for i in range(len(prof) - 1):
        (y_a, z_a), (y_b, z_b) = prof[i], prof[i + 1]
        n_y, n_z = -(z_b - z_a), (y_b - y_a)
        L = math.hypot(n_y, n_z) or 1.0
        n_y, n_z = n_y / L * t, n_z / L * t
        mb.poly([(x0, y_a, z_a), (x1, y_a, z_a), (x1, y_b, z_b), (x0, y_b, z_b)], mat)
        mb.poly([(x0, y_b + n_y, z_b + n_z), (x1, y_b + n_y, z_b + n_z), (x1, y_a + n_y, z_a + n_z), (x0, y_a + n_y, z_a + n_z)], mat)
    # nervaduras de rigidez del frente y dobladillo inferior
    for zz in (zb + (zt - zb) * 0.38, zb + (zt - zb) * 0.68):
        cl.rtube(mb, (x0 + 0.004, -d - 0.0005, zz), (x1 - 0.004, -d - 0.0005, zz), 0.010, 0.005, mat, up=(0, -1, 0), r=0.002)
    mb.cyl((x0, -d + 0.002, zb + 0.003), (x1, -d + 0.002, zb + 0.003), 0.004, seg=12, mat=mat)
    for xx in (x0, x1):                                    # remaches de los costados
        for k in range(3):
            zz = zb + 0.03 + k * (h - rise - 0.06) / 2
            mb.cyl((xx, -d + 0.015, zz), (xx + (-0.002 if xx == x0 else 0.002), -d + 0.015, zz), 0.0035, seg=12, mat="steel")
    # ceja de fijación al muro con pijas
    mb.box((x0 - 0.025, -0.002, zt - 0.005), (x1 + 0.025, 0.0, zt + 0.035), mat, bevel=0.0005)
    for k in range(5):
        ce.screw(mb, _T(x0 - 0.01 + (w + 0.02) * k / 4, -0.002, zt + 0.018) @ _Rx(90), d=0.008, mat="steel")
    if screen:                                            # malla de alambre abajo (12 mm), en retícula real de alambres
        for k in range(int(w / 0.012) + 1):
            xx = x0 + 0.004 + k * (w - 0.008) / int(w / 0.012)
            mb.box((xx - 0.0006, -d + 0.004, zb + 0.004), (xx + 0.0006, -0.004, zb + 0.0052), "steel", bevel=0.0)
        for k in range(int(d / 0.012) + 1):
            yy = -d + 0.004 + k * (d - 0.008) / int(d / 0.012)
            mb.box((x0 + 0.002, yy - 0.0006, zb + 0.0052), (x1 - 0.002, yy + 0.0006, zb + 0.0064), "steel", bevel=0.0)


def wall_vents(det):
    """Toma de aire de emergencia (muro poniente, baja) y extractor con persiana de gravedad (muro oriente, alta): rejilla de
    lamas con su capucha contra lluvia, como las casetas prefabricadas de telecom."""
    from kit import clinic_servicios as cs
    for (xw, y, z, rot, w, h) in ((SH_X0, 4.85, 1.35, -90, 0.62, 0.62), (SH_X1, 3.25, 2.45, 90, 0.46, 0.46)):
        W = _T(xw, y, 0.0) @ _Rz(rot)
        g = cl.MB()
        cs.louver_grille(g, _T(0, -0.001, z) @ _Rx(90), w, h, int(h / 0.05), mat="galvanized", back_mat="cable", t=0.008,
                         frame=0.025, depth=0.006)
        rain_hood(g, 0.0, z + h / 2 + 0.06, w + 0.12, h + 0.10, 0.22)
        det.join(g, W)


def anchor_clips(det):
    """Clips de anclaje de la caseta al firme (ángulo galvanizado de 100 x 100 x 10 mm, 150 mm de largo, taquete expansivo al
    firme y perno al inserto del muro): dos por esquina."""
    clip = cl.MB()
    clip.box((-0.075, -0.100, 0.0), (0.075, 0.0, 0.010), "galvanized", bevel=0.002)
    clip.box((-0.075, -0.010, 0.0), (0.075, 0.0, 0.100), "galvanized", bevel=0.002)
    for sx in (-1, 1):                                    # cartabones
        clip.poly([(sx * 0.07, -0.010, 0.010), (sx * 0.07, -0.090, 0.010), (sx * 0.07, -0.010, 0.090)], "galvanized")
        clip.poly([(sx * 0.064, -0.010, 0.090), (sx * 0.064, -0.090, 0.010), (sx * 0.064, -0.010, 0.010)], "galvanized")
        clip.poly([(sx * 0.064, -0.090, 0.010), (sx * 0.064, -0.010, 0.090), (sx * 0.07, -0.010, 0.090), (sx * 0.07, -0.090, 0.010)],
                  "galvanized")
    ce.hexnut(clip, _T(0.0, -0.060, 0.010), d=0.016, mat="galvanized")
    clip.cyl((0.0, -0.060, 0.010), (0.0, -0.060, 0.045), 0.008, seg=16, mat="galvanized")
    ce.hexnut(clip, _T(0.0, -0.010, 0.060) @ _Rx(90), d=0.016, mat="galvanized")
    for (cx, cy, rot) in ((SH_X0 + 0.35, SH_Y0, 0), (SH_X1 - 0.35, SH_Y0, 0), (SH_X1 - 0.35, SH_Y1, 180), (SH_X0 + 0.35, SH_Y1, 180),
                          (SH_X0, SH_Y0 + 0.35, -90), (SH_X0, SH_Y1 - 0.35, -90), (SH_X1, SH_Y0 + 0.35, 90), (SH_X1, SH_Y1 - 0.35, 90)):
        det.join(clip, _T(cx, cy, Z_PAD) @ _Rz(rot))


def foundation(det):
    """Firme de desplante de la caseta (sobresale 25 cm) con su chaflán y el cordón de sellador entre caseta y firme."""
    cl.rbox(det, (SH_X0 - 0.25, SH_Y0 - 0.25, Z_GRAVEL - 0.08), (SH_X1 + 0.25, SH_Y1 + 0.25, Z_PAD), "concrete", r=0.015)
    pts = [(SH_X0 + CH, SH_Y0 - 0.004), (DX0 - FRAME - 0.004, SH_Y0 - 0.004)], [(DX1 + FRAME + 0.004, SH_Y0 - 0.004),
                                                                              (SH_X1 - CH, SH_Y0 - 0.004)]
    for run in pts:
        det.cyl((run[0][0], run[0][1], Z_PAD + 0.004), (run[1][0], run[1][1], Z_PAD + 0.004), 0.008, seg=12, mat="rubber")
    for (a, b) in (((SH_X1 + 0.004, SH_Y0 + CH), (SH_X1 + 0.004, SH_Y1 - CH)), ((SH_X1 - CH, SH_Y1 + 0.004), (SH_X0 + CH, SH_Y1 + 0.004)),
                   ((SH_X0 - 0.004, SH_Y1 - CH), (SH_X0 - 0.004, SH_Y0 + CH))):
        det.cyl((a[0], a[1], Z_PAD + 0.004), (b[0], b[1], Z_PAD + 0.004), 0.008, seg=12, mat="rubber")
    # escalón prefabricado frente a la puerta (del firme al piso interior: 15 cm)
    cl.rbox(det, (DX0 - 0.20, SH_Y0 - 0.42, Z_PAD - 0.01), (DX1 + 0.20, SH_Y0 - 0.006, Z_PAD + 0.075), "concrete", r=0.012)


# ------------------------------------------------------------------------------------------------------------ plataforma
def _rect_in(x, y, rects, pad=0.0):
    return any(a + pad <= x <= b - pad and c + pad <= y <= d - pad for (a, b, c, d) in rects)


def compound(det, r):
    """Guarnición perimetral en tramos con junta, cama de grava ondulada (con la grava amontonada contra guarniciones y losas),
    banquetas en losas con junta fría, losas de equipo, losa del portón y piedras sueltas de la grava."""
    # guarnición bajo la malla (tramos de 3 m con junta de 8 mm); se interrumpe en el portón
    def curb_run(a, b, axis, c):
        n = max(1, int(round(abs(b - a) / 3.0)))
        step = (b - a) / n
        for k in range(n):
            u0, u1 = a + k * step + 0.004, a + (k + 1) * step - 0.004
            if axis == "x":
                cl.rbox(det, (u0, c - CURB_W / 2, -0.05), (u1, c + CURB_W / 2, CURB_TOP), "concrete", r=0.012)
            else:
                cl.rbox(det, (c - CURB_W / 2, u0, -0.05), (c + CURB_W / 2, u1, CURB_TOP), "concrete", r=0.012)
    h = CURB_W / 2
    curb_run(CX0 - h, GATE_X0 - 0.10, "x", CY0)
    curb_run(GATE_X1 + 0.10, CX1 + h, "x", CY0)
    curb_run(CX0 - h, CX1 + h, "x", CY1)
    curb_run(CY0 + h, CY1 - h, "y", CX0)
    curb_run(CY0 + h, CY1 - h, "y", CX1)
    # losas (banquetas en paños de 1,5 m con junta, losas de equipo y del portón)
    slabs = []

    def slab(x0, x1, y0, y1, top, panel=1.5):
        L = max(x1 - x0, y1 - y0)
        along_x = (x1 - x0) >= (y1 - y0)
        n = max(1, int(round(L / panel)))
        for k in range(n):
            if along_x:
                a, b = x0 + (x1 - x0) * k / n, x0 + (x1 - x0) * (k + 1) / n
                cl.rbox(det, (a + 0.003, y0, Z_GRAVEL - 0.10), (b - 0.003, y1, top), "concrete", r=0.010)
            else:
                a, b = y0 + (y1 - y0) * k / n, y0 + (y1 - y0) * (k + 1) / n
                cl.rbox(det, (x0, a + 0.003, Z_GRAVEL - 0.10), (x1, b - 0.003, top), "concrete", r=0.010)
        slabs.append((x0, x1, y0, y1))
    for w in WALKS:
        slab(*w, Z_WALK)
    slab(*CAB_PAD, Z_WALK + 0.06, panel=6.0)
    slab(*GEN_PAD, Z_WALK + 0.08, panel=6.0)
    slab(*APRON, Z_WALK + 0.01, panel=2.0)
    slabs.append((SH_X0 - 0.25, SH_X1 + 0.25, SH_Y0 - 0.25, SH_Y1 + 0.25))
    # cama de grava: rejilla de 10 cm con ondulación de ±1,2 cm, más alta contra guarniciones y losas (la grava se amontona)
    g0, g1 = CX0 + h - 0.012, CX1 - h + 0.012
    n = int(round((g1 - g0) / 0.10))
    xs = np.linspace(g0, g1, n + 1)
    nz = _noise2(r, n + 1)
    fine = r.random((n + 1, n + 1)) * 0.004
    Z = Z_GRAVEL + (nz - 0.5) * 0.024 + fine
    bm = det.bm
    verts = {}
    occ = lambda x, y: _rect_in(x, y, slabs, pad=0.03)   # noqa: E731
    keep = np.zeros((n, n), bool)
    for i in range(n):
        for j in range(n):
            cx, cy = (xs[i] + xs[i + 1]) / 2, (xs[j] + xs[j + 1]) / 2
            keep[i, j] = not (occ(xs[i], xs[j]) and occ(xs[i + 1], xs[j]) and occ(xs[i], xs[j + 1]) and occ(xs[i + 1], xs[j + 1]))
            keep[i, j] &= not (occ(cx, cy) and False)

    def V(i, j):
        if (i, j) not in verts:
            x, y = xs[i], xs[j]
            z = Z[i, j]
            # junto a una losa o guarnición la grava sube hasta 1,5 cm
            d = min(abs(x - g0), abs(x - g1), abs(y - g0), abs(y - g1))
            for (a, b, c, e) in slabs:
                dx = max(a - x, 0, x - b)
                dy = max(c - y, 0, y - e)
                d = min(d, math.hypot(dx, dy))
            z += 0.015 * max(0.0, 1 - d / 0.25)
            verts[(i, j)] = bm.verts.new((x, y, z))
        return verts[(i, j)]
    mi = det.mi("gravel")
    for i in range(n):
        for j in range(n):
            if keep[i, j]:
                f = bm.faces.new([V(i, j), V(i + 1, j), V(i + 1, j + 1), V(i, j + 1)])
                f.material_index = mi
    # piedras sueltas (las más grandes de la grava) junto a losas y guarniciones y alguna en las banquetas
    stone = cl.MB()
    ce.lathe(stone, [(0.0, 0.0), (0.5, 0.05), (0.62, 0.35), (0.45, 0.75), (0.0, 0.85)], seg=7, mat="gravel")
    placed = 0
    tries = 0
    while placed < 900 and tries < 20000:
        tries += 1
        x, y = r.uniform(g0, g1), r.uniform(g0, g1)
        d = min(abs(x - g0), abs(x - g1), abs(y - g0), abs(y - g1))
        for (a, b, c, e) in slabs:
            d = min(d, math.hypot(max(a - x, 0, x - b), max(c - y, 0, y - e)))
        if _rect_in(x, y, slabs, pad=-0.01):
            if r.random() > 0.01:
                continue
            z = Z_WALK
        elif d > 0.35 and r.random() > 0.15:
            continue
        else:
            z = Z_GRAVEL
        s = r.uniform(0.012, 0.028)
        M = _T(x, y, z - s * 0.25) @ _Rz(r.uniform(0, 360)) @ _Rx(r.uniform(-25, 25)) @ \
            Matrix.Diagonal((s * r.uniform(0.8, 1.3), s * r.uniform(0.7, 1.1), s * r.uniform(0.6, 0.9), 1.0))
        det.join(stone, M)
        placed += 1
    # registros de prueba del anillo de tierras (tapas redondas de PVC al ras de la grava)
    for (x, y) in ((-7.3, 7.3), (7.3, 7.3), (7.3, -7.3), (-0.25, 6.2)):
        det.cyl((x, y, Z_GRAVEL - 0.02), (x, y, Z_GRAVEL + 0.022), 0.13, seg=40, mat="plastic")
        det.cyl((x, y, Z_GRAVEL + 0.022), (x, y, Z_GRAVEL + 0.030), 0.115, seg=40, mat="sign_green")
        cl.text(det, "GROUND", 0.035, 0.002, "sign_white", M=_T(x, y, Z_GRAVEL + 0.030))
        for a in range(2):
            xx = x + 0.075 * math.cos(math.pi * a)
            det.cyl((xx, y, Z_GRAVEL + 0.030), (xx, y, Z_GRAVEL + 0.034), 0.008, seg=16, mat="steel")
    # bolardos de tubo relleno de concreto, pintados de amarillo, con tapa de domo (protegen generador y tanque)
    for (x, y) in ((GEN_PAD[0] + 0.15, GEN_PAD[2] - 0.30), (GEN_PAD[0] + 2.5, GEN_PAD[2] - 0.30), (GEN_PAD[1] - 0.15, GEN_PAD[2] - 0.30),
                   (GEN_PAD[0] - 0.30, GEN_PAD[2] + 0.4), (GEN_PAD[0] - 0.30, GEN_PAD[3] - 0.4)):
        bollard(det, x, y, Z_GRAVEL)
        _proxy_box((x - 0.06, y - 0.06, 0.0), (x + 0.06, y + 0.06, Z_GRAVEL + 1.07))


def bollard(det, x, y, z):
    """Bolardo de tubo de acero de 4" (114 mm) cédula 40 relleno de concreto, 1,07 m sobre el piso, con domo de concreto y anillo
    de grava apisonada."""
    det.cyl((x, y, z - 0.03), (x, y, z + 1.00), 0.0572, seg=32, mat="paint_yellow")
    ce.lathe(det, [(0.0, 0.0), (0.0572, 0.0), (0.0572, 0.004), (0.052, 0.012), (0.046, 0.04), (0.032, 0.062), (0.016, 0.070),
                   (0.0, 0.072)], seg=32, mat="concrete", M=_T(x, y, z + 1.00))
    for zz in (0.30, 0.36):                                       # franjas reflejantes
        det.cyl((x, y, z + zz), (x, y, z + zz + 0.05), 0.0578, seg=32, mat="sign_white")


# ------------------------------------------------------------------------------------------------------------ vestido
def _mod(name):
    try:
        return __import__(f"kit.{name}", fromlist=[name])
    except ImportError:
        return None


def dress(det, furn, r):
    """Equipo de los agentes (kit/tower.py, kit/antennas.py, kit/telecom.py). Si un módulo aún no existe, se omite."""
    pass


# ------------------------------------------------------------------------------------------------- ensamble
def build_com(bid="COM_1_antena", collection_root=None, dress_on=True, **kw):
    cfg = cfg_com(bid)
    cid = cfg["id"]
    LIGHTS.clear()
    PROXIES.clear()
    root = collection_root or get_collection(cid)
    keys = ("Shell", "Details", "Interior", "Skirt", "Roof", "Damage", "Furniture")
    cols = {k: get_collection(f"{cid}_{k}", root) for k in keys}
    out = {k: [] for k in cols}
    shell, det, inter, roof, furn = MB(), MB(), MB(), MB(), MB()
    r = rng(cfg["seed"])
    shelter_shell(shell, roof)
    roof_details(det)
    door(det)
    wall_services(det, r)
    wall_vents(det)
    anchor_clips(det)
    foundation(det)
    compound(det, r)
    if dress_on and kw.get("dress", True):
        dress(det, furn, r)
    for nm, mb in (("Shell", shell), ("Details", det), ("Interior", inter), ("Roof", roof), ("Furniture", furn)):
        if len(mb.bm.faces):
            out[nm].append(mb.finish(f"{cid}_{nm}", cols[nm], uv_size=2.0, merge=0))
    out["stats"] = dict(interior_dress=dict(bulb_pos=list(LIGHTS)), proxies=list(PROXIES))
    out["cfg"] = cfg
    return out
