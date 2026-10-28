"""Depuración de caras coplanares superpuestas (z-fighting) antes del horneado.

Si una cara F tiene delante (a menos de `tol`) otra cara G casi paralela y del mismo sentido, y G la cubre por completo
(todos los vértices de F proyectados caen dentro del polígono de G), F nunca aporta nada visible: lo que se ve es G, y en un
rasterizador las dos se pelean. Se borra F. Casos típicos: cabeza de muro bajo la losa de azotea, canto de losa contra la cara
interior del muro, tapa de un elemento metida en el plano de otro. Si G no cubre a F entera (solape parcial: la cabeza del muro
sobresale 3 cm del borde de la losa, cruces de juntas), F se hunde `push` (3 mm) dentro de su propio sólido: el escalón no se ve
y el rasterizador ya no duda (con near 0,05 m y 24 bits, la precisión de profundidad a 30 m ronda 1 mm).
El borrado nunca abre un hueco que se vea, porque G está en el mismo plano y del mismo lado.
"""
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def _inside(poly, p, eps):
    """Punto 2D dentro del polígono (cruce de rayo) o a menos de eps de un lado."""
    x, y = p
    n = len(poly)
    inside = False
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / L2))
        if (x - x1 - t * dx) ** 2 + (y - y1 - t * dy) ** 2 <= eps * eps:
            return True
    return inside


def _covers(g, f, eps):
    n = g.normal
    t = n.orthogonal().normalized()
    b = n.cross(t)
    poly = [(v.co.dot(t), v.co.dot(b)) for v in g.verts]
    return all(_inside(poly, (v.co.dot(t), v.co.dot(b)), eps) for v in f.verts)


def dedupe(objs, passes=5, **kw):
    """Repite la pasada hasta que no quede nada que borrar o hundir (hundir una cara puede dejarla contra otra)."""
    tot = [0, 0.0, 0]
    for _ in range(passes):
        k, a, s = dedupe_pass(objs, **kw)
        tot = [tot[0] + k, round(tot[1] + a, 3), tot[2] + s]
        if k + s == 0:
            break
    return tuple(tot)


def dedupe_pass(objs, tol=0.0012, eps=0.0015, min_area=1e-5, push=0.003, log=print):
    """Borra de `objs` (mallas en coordenadas de mundo = locales; los objetos del kit no llevan transformación) las caras cubiertas
    por completo por otra coplanar del mismo sentido y hunde las parcialmente cubiertas. Devuelve (borradas, área borrada, hundidas)."""
    bms, trees = [], []
    for o in objs:
        bm = bmesh.new()
        bm.from_mesh(o.data)
        bm.transform(o.matrix_world)
        bm.faces.ensure_lookup_table()
        bms.append(bm)
        trees.append(BVHTree.FromBMesh(bm))
    kill = [set() for _ in objs]
    sink = [set() for _ in objs]
    area_k = 0.0
    for k, bm in enumerate(bms):
        for f in bm.faces:
            a = f.calc_area()
            if a < min_area:
                continue
            n = f.normal
            c = f.calc_center_median()
            for j, tr in enumerate(trees):
                hit = None
                for start, dist in ((c + n * 0.0005, tol + 0.0005), (c - n * 0.00002, tol)):
                    loc, nrm, idx, dd = tr.ray_cast(start, -n, dist)
                    if idx is None or (j == k and idx == f.index) or idx in kill[j]:
                        continue
                    if bms[j].faces[idx].normal.dot(n) > 0.995:
                        hit = idx
                        break
                if hit is None:
                    continue
                g = bms[j].faces[hit]
                ga = g.calc_area()
                # se actúa sobre la menor del par (empate: decide el índice; nunca las dos), la encuentre quien la encuentre:
                # si el centro de la menor no cae sobre la mayor, solo el rayo de la mayor descubre el solape
                (sa, sk, sf), (bk, bf) = ((a, k, f), (j, g)) if (a, k, f.index) < (ga, j, hit) else ((ga, j, g), (k, f))
                if sf.index in kill[sk] or sf.index in sink[sk]:
                    break
                if _covers(bf, sf, eps):
                    kill[sk].add(sf.index)
                    area_k += sa
                else:
                    sink[sk].add(sf.index)
                break
    n_k = n_s = 0
    for o, bm, ks, ss in zip(objs, bms, kill, sink):
        ss = ss - ks
        if not ks and not ss:
            bm.free()
            continue
        # hundir: cada vértice se mueve por la suma de las normales DISTINTAS de sus caras hundidas (una esquina de dos caras
        # hundidas entra en las dos direcciones; dos caras coplanares que comparten vértice no lo mueven el doble)
        moves = {}
        for i in ss:
            f = bm.faces[i]
            key = tuple(round(x, 3) for x in f.normal)
            for v in f.verts:
                moves.setdefault(v.index, {})[key] = f.normal.copy()
        bm.verts.ensure_lookup_table()
        for vi, ns in moves.items():
            d = Vector()
            for nv in ns.values():
                d += nv
            bm.verts[vi].co -= d * push
        if ks:
            bmesh.ops.delete(bm, geom=[bm.faces[i] for i in ks], context="FACES")
        bm.transform(o.matrix_world.inverted())
        bm.to_mesh(o.data)
        bm.free()
        n_k += len(ks)
        n_s += len(ss)
        log("coplanares en", o.name, "borradas", len(ks), "hundidas", len(ss))
    return n_k, round(area_k, 3), n_s
