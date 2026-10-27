"""builders.py — registro de constructores por ID de modelo (lo usan bake_apt, export y los renders de revisión)."""


def build(bid, **kw):
    if bid == "APT_A_5p":
        import apt_builder
        return apt_builder.build_apt_a(**kw)
    if bid == "APT_B_4p":
        import apt_b
        return apt_b.build_apt_b(**kw)
    raise KeyError(f"sin constructor para {bid}")


KEYS = ("Shell", "Details", "Interior", "Skirt", "Roof", "Damage")
