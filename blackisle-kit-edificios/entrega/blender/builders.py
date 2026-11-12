"""builders.py — registro de constructores por ID de modelo (lo usan bake_apt, export y los renders de revisión)."""


def build(bid, **kw):
    if bid.startswith("APT_"):
        res = _build_apt(bid, **kw)
        if kw.get("dress_all", True) and kw.get("dress", True):
            _dress_interior(res)
        return res
    if bid.startswith("CAB_"):
        import cabin_builder
        kw.pop("dress_all", None)
        return cabin_builder.build_cabin(bid, **kw)
    raise KeyError(f"sin constructor para {bid}")


KEYS = ("Shell", "Details", "Interior", "Skirt", "Roof", "Damage")


def _build_apt(bid, **kw):
    if bid == "APT_A_5p":
        import apt_builder
        if "dress_all" in kw:
            kw["dress"] = kw.pop("dress_all")
        return apt_builder.build_apt_a(**kw)
    if bid == "APT_B_4p":
        import apt_b
        return apt_b.build_apt_b(**kw)
    if bid == "APT_C_3p":
        import apt_c
        return apt_c.build_apt_c(**kw)
    if bid == "APT_D_4p":
        import apt_d
        return apt_d.build_apt_d(**kw)
    raise KeyError(bid)


def _dress_interior(res):
    """Escombro, basura, focos, apagadores y algún mueble roto en los cuartos (interior_dress.py), como objeto aparte del
    grupo Interior. Solo se colocan piezas donde los rayos encuentran un cuarto cerrado con piso y techo."""
    import interior_dress as idr
    from apt_builder import level_z
    from kit.common import get_collection
    cfg = res["cfg"]
    cid = cfg["id"]
    st = cfg.get("stairs") or [cfg["stair"]]
    stairs = [(s["x0"], s["x0"] + s["w"], s["y0"], s["y0"] + s["l"]) for s in st]
    xs, ys = cfg["xs"], cfg["ys"]
    objs = [o for k in ("Shell", "Interior", "Details", "Damage") for o in res.get(k, [])]
    mb, stats = idr.dress(objs, cfg, level_z(cfg)[:-1], stairs, (xs[0], xs[-1], ys[0], ys[-1]), cfg["seed"] + 777)
    if len(mb.bm.faces):
        res["Interior"].append(mb.finish(f"{cid}_InteriorDress", get_collection(f"{cid}_Interior"), uv_size=3.0, merge=0))
    res.setdefault("stats", {})["interior_dress"] = stats
