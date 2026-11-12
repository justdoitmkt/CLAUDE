"""interior_dress.py — vestido interior de los departamentos: escombro, basura, focos colgando, apagadores y algún mueble roto.

La revisión de aceptación (2026-10-28) vio los cuartos como cascarones limpios: con la estructura completa pero sin escombro ni
escala humana. El plan de ESTADO decía "sin mobiliario, con escombro y daño interior". Este módulo lo cumple sin conocer los
cuartos: lee la geometría ya construida con rayos (BVH de carcasa + interior + detalles) y solo coloca piezas donde:
  - hay piso a la cota del nivel (cara horizontal hacia arriba) y techo de losa a 2,2–3,6 m (fuera de escaleras y del colapso);
  - el punto está encerrado: 8 rayos horizontales a 0,5 m chocan antes de 7 m (fuera de logias, galerías y balcones);
  - queda lejos de los núcleos de escalera (rectángulos de cfg) y, para lo que va pegado al muro, hay muro macizo detrás
    (3 rayos paralelos a las alturas pedidas chocan casi a la misma distancia: no hay puerta ahí).
Nada de lo colocado pasa de 0,35 m salvo sillas y focos (no estorban el paso: cápsula de jugador r 0,25, escalón 0,35).
Presupuesto medido (2026-10-28): A 31 k · B 24 k · C 15 k · D 21 k triángulos, trozos de escombro en nivel 'low'.
"""
import math

import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from kit.common import MB, rng

DIRS8 = [Vector((math.cos(a), math.sin(a), 0.0)) for a in (k * math.pi / 4 for k in range(8))]


def _T(x, y, z):
    return Matrix.Translation((x, y, z))


def _Rz(a):
    return Matrix.Rotation(a, 4, "Z")


class Scene:
    def __init__(self, objs):
        self.bms, self.trees = [], []
        for o in objs:
            bm = bmesh.new()
            bm.from_mesh(o.data)
            bm.transform(o.matrix_world)
            self.bms.append(bm)
            self.trees.append(BVHTree.FromBMesh(bm))

    def hit(self, p, d, dist):
        best = None
        for t in self.trees:
            loc, nrm, idx, dd = t.ray_cast(p, d, dist)
            if idx is not None and (best is None or dd < best[2]):
                best = (loc, nrm, dd)
        return best

    def free(self):
        for bm in self.bms:
            bm.free()


def _in_rects(x, y, rects, pad):
    return any(x0 - pad <= x <= x1 + pad and y0 - pad <= y <= y1 + pad for (x0, x1, y0, y1) in rects)


def probe(sc, x, y, zl, stairs):
    """Devuelve dict del punto (piso, techo, distancias a muros) o None si no sirve."""
    if _in_rects(x, y, stairs, 0.45):
        return None
    h = sc.hit(Vector((x, y, zl + 1.2)), Vector((0, 0, -1)), 1.6)
    if h is None or h[1].z < 0.9 or abs(h[0].z - zl) > 0.12:
        return None
    zf = h[0].z
    up = sc.hit(Vector((x, y, zf + 0.05)), Vector((0, 0, 1)), 4.0)
    if up is None or up[1].z > -0.9 or not (2.2 <= up[0].z - zf <= 3.6):
        return None
    ds = []
    for d in DIRS8:
        hh = sc.hit(Vector((x, y, zf + 0.5)), d, 7.0)
        if hh is None:
            return None                        # abierto: logia, galería, balcón, colapso
        ds.append(hh[2])
    k = min(range(8), key=lambda i: ds[i])
    return dict(x=x, y=y, zf=zf, zc=up[0].z, d=ds[k], wall_dir=DIRS8[k], ds=ds)


def solid_wall(sc, p, n, d, half=0.5, zs=(0.5, 1.9)):
    """Muro macizo detrás de p (dirección n, distancia d): 3 rayos paralelos a las alturas zs chocan a ±6 cm de d."""
    t = Vector((-n.y, n.x, 0.0))
    for off in (-half, 0.0, half):
        for z in zs:
            q = Vector((p["x"], p["y"], p["zf"] + z)) + t * off
            hh = sc.hit(q, n, d + 0.4)
            if hh is None or abs(hh[2] - d) > 0.06:
                return False
    return True


# ------------------------------------------------------------------------------------------------ piezas
def plaster_debris(mb, r, n_chunks=7, spread=0.55):
    """Aplanado caído al pie del muro: lajas planas (plaster) y trozos (concreto), polvo como laja muy delgada."""
    from kit import damage as dm
    for _ in range(int(n_chunks)):
        a = r.uniform(0, 2 * math.pi)
        rad = r.uniform(0.05, spread)
        cx, cy = rad * math.cos(a), rad * math.sin(a) * 0.6
        if r.random() < 0.75:                   # laja de aplanado (polígono irregular de 5–7 lados, 1–1,8 cm)
            k = int(r.integers(5, 8))
            s = r.uniform(0.06, 0.22)
            pts = [(s * r.uniform(0.6, 1.0) * math.cos(2 * math.pi * i / k), s * r.uniform(0.5, 0.9) * math.sin(2 * math.pi * i / k))
                   for i in range(k)]
            tilt = Matrix.Rotation(r.uniform(-0.25, 0.25), 4, "X") @ Matrix.Rotation(r.uniform(-0.25, 0.25), 4, "Y")
            mb.plate(pts, r.uniform(0.010, 0.018), "plaster", m=_T(cx, cy, 0.004) @ _Rz(r.uniform(0, 6.3)) @ tilt)
        else:
            mb.join(dm.chunk(size=float(r.uniform(0.05, 0.14)), seed=int(r.integers(1e6)), detail="low"),
                    _T(cx, cy, 0.0) @ _Rz(r.uniform(0, 6.3)))
    # polvo / arenilla: laja muy delgada y ancha bajo el montón
    k = 9
    s = spread * 0.9
    pts = [(s * r.uniform(0.7, 1.0) * math.cos(2 * math.pi * i / k), 0.6 * s * r.uniform(0.7, 1.0) * math.sin(2 * math.pi * i / k))
           for i in range(k)]
    mb.plate(pts, 0.004, "rubble", m=_T(0, 0, 0.001))


def trash(mb, r, n_papers=10, n_bottles=3):
    for _ in range(int(n_papers)):                 # hojas: cajas de 2 mm (cerradas: la AO por vértice no se va a negro)
        a = r.uniform(0, 6.3)
        rad = r.uniform(0.0, 0.7)
        w, h = r.uniform(0.15, 0.24), r.uniform(0.2, 0.32)
        M = _T(rad * math.cos(a), rad * math.sin(a), 0.002 + r.uniform(0, 0.01)) @ _Rz(r.uniform(0, 6.3)) @ \
            Matrix.Rotation(r.uniform(-0.12, 0.12), 4, "X")
        mb.box((-w / 2, -h / 2, 0), (w / 2, h / 2, 0.002), "paper", m=M)
    for _ in range(int(n_bottles)):                # botellas y latas tiradas
        a = r.uniform(0, 6.3)
        rad = r.uniform(0.1, 0.6)
        x, y = rad * math.cos(a), rad * math.sin(a)
        ang = r.uniform(0, 6.3)
        d = Vector((math.cos(ang), math.sin(ang), 0.0))
        if r.random() < 0.6:
            L, rr = r.uniform(0.22, 0.3), 0.035
            p0 = Vector((x, y, rr))
            mb.cyl(p0, p0 + d * L * 0.7, rr, seg=8, mat="glass")
            mb.cyl(p0 + d * L * 0.7, p0 + d * L, rr, seg=8, mat="glass", r1=0.013)
        else:
            L, rr = 0.12, 0.033
            p0 = Vector((x, y, rr))
            mb.cyl(p0, p0 + d * L, rr, seg=8, mat="aluminium")


def mattress(mb, r):
    """Colchón tirado contra el muro (origen: centro del lado pegado al muro; +y hacia el cuarto)."""
    W, L, T = r.uniform(0.85, 1.35), r.uniform(1.85, 1.95), r.uniform(0.12, 0.17)
    mb.box((-L / 2, 0.02, 0), (L / 2, 0.02 + W, T), "fabric", bevel=0.035, seg=2,
           m=Matrix.Rotation(r.uniform(-0.04, 0.04), 4, "Z"))


def broken_chair(mb, r):
    """Silla de madera rota: a veces sin respaldo o con una pata menos; casi siempre volcada de lado."""
    tmp = MB()
    s, hs, hb = 0.42, 0.45, 0.45
    leg = 0.035
    legs = [(-s / 2, -s / 2), (s / 2, -s / 2), (s / 2, s / 2), (-s / 2, s / 2)]
    miss = int(r.integers(0, 6))
    for i, (x, y) in enumerate(legs):
        if i == miss:
            continue
        tmp.box((x - leg / 2, y - leg / 2, 0), (x + leg / 2, y + leg / 2, hs), "wood")
    tmp.box((-s / 2 - 0.01, -s / 2 - 0.01, hs), (s / 2 + 0.01, s / 2 + 0.01, hs + 0.025), "wood")
    if r.random() < 0.7:
        for x in (-s / 2, s / 2):
            tmp.box((x - leg / 2, s / 2 - leg, hs), (x + leg / 2, s / 2, hs + hb), "wood")
        tmp.box((-s / 2, s / 2 - leg, hs + hb - 0.09), (s / 2, s / 2, hs + hb), "wood")
    if r.random() < 0.6:          # volcada: de lado sobre el piso
        tmp.transform(_T(0, 0, s / 2 + 0.012) @ Matrix.Rotation(math.pi / 2, 4, "Y") @ _T(0, 0, -s / 2 - 0.012))
        zmin = min(v.co.z for v in tmp.bm.verts)
        tmp.transform(_T(0, 0, -zmin))
    mb.join(tmp, _Rz(r.uniform(0, 6.3)))


def ceiling_bulb(mb, r, drop):
    """Foco desnudo en su cable (origen: punto del techo)."""
    mb.cyl((0, 0, 0), (0, 0, -0.03), 0.045, seg=10, mat="plastic")                 # roseta
    mb.tube([(0, 0, -0.03), (r.uniform(-0.01, 0.01), r.uniform(-0.01, 0.01), -drop)], 0.004, seg=4, mat="cable")
    z = -drop
    mb.cyl((0, 0, z), (0, 0, z - 0.06), 0.017, seg=8, mat="plastic")                # portalámparas
    if r.random() < 0.8:                                                             # bombilla (a veces rota: falta)
        mb.cyl((0, 0, z - 0.06), (0, 0, z - 0.09), 0.014, seg=8, mat="glass", r1=0.03)
        mb.cyl((0, 0, z - 0.09), (0, 0, z - 0.13), 0.03, seg=8, mat="glass", r1=0.008)


def wall_plate(mb, kind):
    """Apagador o contacto (origen: muro, +y hacia el cuarto)."""
    w, h = (0.075, 0.115) if kind == "switch" else (0.075, 0.075)
    mb.box((-w / 2, 0.0, -h / 2), (w / 2, 0.012, h / 2), "plastic")
    mb.box((-0.012, 0.012, -0.018), (0.012, 0.02, 0.018), "plastic")


def _frame(p, n):
    """Matriz con +y hacia el cuarto (contraria al muro n) y origen en el pie del muro bajo p."""
    inward = -n
    xax = Vector((inward.y, -inward.x, 0.0))
    o = Vector((p["x"], p["y"], p["zf"])) + n * (p["d"] - 0.002)
    return Matrix(((xax.x, inward.x, 0, o.x), (xax.y, inward.y, 0, o.y), (0, 0, 1, o.z), (0, 0, 0, 1)))


# ------------------------------------------------------------------------------------------------ colocación
def dress(objs, cfg, levels, stairs, bounds, seed, density=1.0, step=0.5, log=print):
    """objs: objetos ya construidos (carcasa, interior, detalles). levels: cotas de piso a vestir. stairs: [(x0, x1, y0, y1)].
    bounds: (x0, x1, y0, y1) de la planta. Devuelve (MB, estadísticas)."""
    sc = Scene(objs)
    r = rng(seed)
    mb = MB()
    st = {}
    x0, x1, y0, y1 = bounds
    for lv, zl in enumerate(levels):
        pts = []
        nx, ny = int((x1 - x0) / step), int((y1 - y0) / step)
        for i in range(nx + 1):
            for j in range(ny + 1):
                x = x0 + i * step + r.uniform(-0.12, 0.12)
                y = y0 + j * step + r.uniform(-0.12, 0.12)
                p = probe(sc, x, y, zl, stairs)
                if p:
                    pts.append(p)
        r.shuffle(pts)
        used = []

        def free(p, rad):
            return all((p["x"] - q[0]) ** 2 + (p["y"] - q[1]) ** 2 >= (rad + q[2]) ** 2 for q in used)

        # focos: centro de cuarto (lejos de los muros), uno cada ~3 m
        bulbs = []
        for p in sorted(pts, key=lambda q: -min(q["ds"])):
            if min(p["ds"]) < 1.1:
                break
            if all((p["x"] - b[0]) ** 2 + (p["y"] - b[1]) ** 2 > 3.0 ** 2 for b in bulbs) and r.random() < 0.85 * density:
                bulbs.append((p["x"], p["y"]))
                tmp = MB()
                ceiling_bulb(tmp, r, r.uniform(0.25, 0.55))
                mb.join(tmp, _T(p["x"], p["y"], p["zc"]))
                st["bulb"] = st.get("bulb", 0) + 1

        # una pasada por tipo, cada una con su espaciado (entre piezas del mismo tipo) y su probabilidad
        def place(kind, ok, prob, gap, rad, put):
            mine = []
            for p in pts:
                if r.random() >= prob * density or not ok(p) or not free(p, rad):
                    continue
                if any((p["x"] - q[0]) ** 2 + (p["y"] - q[1]) ** 2 < gap * gap for q in mine):
                    continue
                put(p)
                mine.append((p["x"], p["y"]))
                used.append((p["x"], p["y"], rad))
                st[kind] = st.get(kind, 0) + 1

        def wall_ok(zs, half, dmax=0.75):
            return lambda p: 0.12 <= p["d"] <= dmax and solid_wall(sc, p, p["wall_dir"], p["d"], half=half, zs=zs)

        def put_debris(p):
            tmp = MB()
            plaster_debris(tmp, r, n_chunks=r.integers(4, 9))
            mb.join(tmp, _frame(p, p["wall_dir"]) @ _T(0, 0.3, 0))

        def put_mattress(p):
            tmp = MB()
            mattress(tmp, r)
            mb.join(tmp, _frame(p, p["wall_dir"]))

        def put_trash(p):
            tmp = MB()
            trash(tmp, r, n_papers=r.integers(4, 9), n_bottles=r.integers(0, 3))
            mb.join(tmp, _T(p["x"], p["y"], p["zf"]))

        def put_chair(p):
            tmp = MB()
            broken_chair(tmp, r)
            mb.join(tmp, _T(p["x"], p["y"], p["zf"]))

        def put_plate(p):
            kind = "switch" if r.random() < 0.5 else "socket"
            tmp = MB()
            wall_plate(tmp, kind)
            mb.join(tmp, _frame(p, p["wall_dir"]) @ _T(0, 0, 1.1 if kind == "switch" else 0.3))

        # escombro: muro sin puerta detrás (rayo a 0,3 m; bajo una ventana sí puede haber escombro)
        place("plaster_debris", wall_ok((0.3,), 0.35), 0.3, 2.3, 0.55, put_debris)
        place("mattress", wall_ok((0.3,), 0.95), 0.15, 6.0, 1.05, put_mattress)
        place("chair", lambda p: p["d"] >= 0.45, 0.12, 4.5, 0.5, put_chair)
        place("trash", lambda p: p["d"] >= 0.3, 0.35, 2.0, 0.7, put_trash)
        place("plate", wall_ok((0.5, 1.9), 0.15), 0.5, 2.8, 0.2, put_plate)
        log(f"[vestido] nivel {lv}: {len(pts)} puntos útiles")
    sc.free()
    return mb, st
