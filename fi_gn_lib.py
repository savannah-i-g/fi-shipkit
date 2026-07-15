#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# fi_gn_lib.py -- shared FI_ShipKit builder layer (Blender 5.0):
# typed socket lookup, the G graph builder, gcall, _prim, materials and
# the wear-shader system. Imported by build_kit.py and build_warkit.py.
# LESSONS BAKED IN: RandomValue ID must be pinned in constant contexts;
# GN Mesh Cone spans [0, depth] from its base; write Python bools to bool
# modifier sockets.

import bpy
import math
import os

TAU = math.tau

def in_sock(node, name, stype=None):
    for s in node.inputs:
        if s.name == name and (stype is None or s.type == stype):
            return s
    raise KeyError(f"{node.bl_idname}: no input '{name}' type={stype}")


def out_sock(node, name, stype=None):
    for s in node.outputs:
        if s.name == name and (stype is None or s.type == stype):
            return s
    raise KeyError(f"{node.bl_idname}: no output '{name}' type={stype}")


class G:
    """Tiny node-graph builder with auto x-layout."""

    def __init__(self, name):
        self.ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
        self.x = 0
        self.gin = self.n("NodeGroupInput")
        self.gout = None  # created by finish()

    def sock_in(self, name, stype, default=None, minv=None, maxv=None):
        s = self.ng.interface.new_socket(name, in_out="INPUT",
                                         socket_type=stype)
        if default is not None:
            s.default_value = default
        if minv is not None:
            s.min_value = minv
        if maxv is not None:
            s.max_value = maxv
        return s

    def sock_out(self, name, stype):
        return self.ng.interface.new_socket(name, in_out="OUTPUT",
                                            socket_type=stype)

    def n(self, idname, **props):
        node = self.ng.nodes.new(idname)
        self.x += 190
        node.location = (self.x, 0)
        for k, v in props.items():
            setattr(node, k, v)
        return node

    def l(self, a, b):
        self.ng.links.new(a, b)

    def math(self, op, a, b=None):
        node = self.n("ShaderNodeMath", operation=op)
        if hasattr(a, "is_linked"):
            self.l(a, node.inputs[0])
        else:
            node.inputs[0].default_value = a
        if b is not None:
            if hasattr(b, "is_linked"):
                self.l(b, node.inputs[1])
            else:
                node.inputs[1].default_value = b
        return node.outputs[0]

    def rand_float(self, mn, mx, idf, seed):
        node = self.n("FunctionNodeRandomValue", data_type="FLOAT")
        for val, nm in ((mn, "Min"), (mx, "Max")):
            s = in_sock(node, nm, "VALUE")
            if hasattr(val, "is_linked"):
                self.l(val, s)
            else:
                s.default_value = val
        if idf is not None:
            self.l(idf, in_sock(node, "ID"))
        else:
            # Blender 4.0: an UNCONNECTED ID in a constant (non-field)
            # context evaluates to garbage (negative values). Always pin it.
            zero = self.n("FunctionNodeInputInt")
            zero.integer = 0
            self.l(zero.outputs[0], in_sock(node, "ID"))
        if hasattr(seed, "is_linked"):
            self.l(seed, in_sock(node, "Seed"))
        else:
            in_sock(node, "Seed").default_value = seed
        return out_sock(node, "Value", "VALUE")

    def finish(self, geo_out, mark=True):
        self.gout = self.n("NodeGroupOutput")
        self.l(geo_out, self.gout.inputs[0])
        if mark:
            self.ng.asset_mark()
        return self.ng


def group_in(g, idx_or_name):
    return g.gin.outputs[idx_or_name]


def gcall(g, sub, wires=None, values=None):
    """Drop a sub-group node into graph g; wire/set inputs by name."""
    node = g.n("GeometryNodeGroup")
    node.node_tree = sub
    for name, src in (wires or {}).items():
        g.l(src, in_sock(node, name))
    for name, val in (values or {}).items():
        in_sock(node, name).default_value = val
    return node


def boss(g, mesh, sel, offset, frame, individual=False):
    """Watertight raise/sink primitive (the FI_FleetKit chamfer language):
    ExtrudeMesh(FACES) + ScaleElements frame shrink on the Top. offset > 0
    raises along face normals, < 0 sinks. individual=False extrudes a
    contiguous REGION as one island (single chamfer rim — plateaus, drive
    slots); True does per-face work (panel mosaics, vernier ports).
    Multiplicative top shrink can never self-cross; borders never move, so
    divider T-junctions stay sealed. Returns (geometry, top, side)."""
    ex = g.n("GeometryNodeExtrudeMesh", mode="FACES")
    g.l(mesh, ex.inputs[0])
    g.l(sel, in_sock(ex, "Selection"))
    if hasattr(offset, "is_linked"):
        g.l(offset, in_sock(ex, "Offset Scale"))
    else:
        in_sock(ex, "Offset Scale").default_value = offset
    in_sock(ex, "Individual").default_value = bool(individual)
    sh = g.n("GeometryNodeScaleElements", domain="FACE")
    g.l(out_sock(ex, "Mesh"), sh.inputs[0])
    g.l(out_sock(ex, "Top"), in_sock(sh, "Selection"))
    if hasattr(frame, "is_linked"):
        g.l(frame, in_sock(sh, "Scale"))
    else:
        in_sock(sh, "Scale").default_value = frame
    return (out_sock(sh, "Geometry"), out_sock(ex, "Top"),
            out_sock(ex, "Side"))


def _prim(g, kind, dims, rot=None, trans=None, material=None, verts=None,
          smooth=True):
    """One primitive -> transform -> material. dims/trans entries may be
    sockets or floats. kind: 'cube'(dims=x,y,z) 'cyl'(r,depth)
    'cone'(rtop,rbot,depth) 'sphere'(r)."""
    def wire(sock, v):
        if hasattr(v, "is_linked"):
            g.l(v, sock)
        else:
            sock.default_value = v
    def wire_verts(sock, v, dflt):
        if v is None:
            sock.default_value = dflt
        elif hasattr(v, "is_linked"):
            g.l(v, sock)
        else:
            sock.default_value = v
    if kind == "cube":
        n = g.n("GeometryNodeMeshCube")
        cv = g.n("ShaderNodeCombineXYZ")
        for i in range(3):
            wire(cv.inputs[i], dims[i])
        g.l(cv.outputs[0], in_sock(n, "Size"))
        geo = out_sock(n, "Mesh")
    elif kind == "cyl":
        n = g.n("GeometryNodeMeshCylinder")
        wire_verts(in_sock(n, "Vertices"), verts, 10)
        wire(in_sock(n, "Radius", "VALUE"), dims[0])
        wire(in_sock(n, "Depth", "VALUE"), dims[1])
        if smooth:
            sm = g.n("GeometryNodeSetShadeSmooth")
            g.l(out_sock(n, "Mesh"), sm.inputs[0])
            g.l(out_sock(n, "Side"), in_sock(sm, "Selection"))
            in_sock(sm, "Shade Smooth").default_value = True
            geo = out_sock(sm, "Mesh")
        else:
            geo = out_sock(n, "Mesh")
    elif kind == "cone":
        n = g.n("GeometryNodeMeshCone")
        wire_verts(in_sock(n, "Vertices"), verts, 12)
        wire(in_sock(n, "Radius Top", "VALUE"), dims[0])
        wire(in_sock(n, "Radius Bottom", "VALUE"), dims[1])
        wire(in_sock(n, "Depth", "VALUE"), dims[2])
        sm = g.n("GeometryNodeSetShadeSmooth")
        g.l(out_sock(n, "Mesh"), sm.inputs[0])
        g.l(out_sock(n, "Side"), in_sock(sm, "Selection"))
        in_sock(sm, "Shade Smooth").default_value = True
        geo = out_sock(sm, "Mesh")
    else:  # sphere
        n = g.n("GeometryNodeMeshUVSphere")
        wire_verts(in_sock(n, "Segments"), verts, 10)
        if verts is not None and hasattr(verts, "is_linked"):
            half = g.math("MAXIMUM", g.math("MULTIPLY", verts, 0.5), 4.0)
            g.l(half, in_sock(n, "Rings"))
        else:
            in_sock(n, "Rings").default_value = max(4, (verts or 10) // 2)
        wire(in_sock(n, "Radius", "VALUE"), dims[0])
        sm = g.n("GeometryNodeSetShadeSmooth")
        g.l(out_sock(n, "Mesh"), sm.inputs[0])
        in_sock(sm, "Shade Smooth").default_value = True
        geo = out_sock(sm, "Mesh")
    if rot is not None or trans is not None:
        t = g.n("GeometryNodeTransform")
        g.l(geo, t.inputs[0])
        if rot is not None:
            in_sock(t, "Rotation").default_value = rot
        if trans is not None:
            tv = g.n("ShaderNodeCombineXYZ")
            for i in range(3):
                wire(tv.inputs[i], trans[i])
            g.l(tv.outputs[0], in_sock(t, "Translation"))
        geo = out_sock(t, "Geometry")
    if material is not None:
        m = g.n("GeometryNodeSetMaterial")
        g.l(geo, m.inputs[0])
        in_sock(m, "Material").default_value = material
        geo = out_sock(m, "Geometry")
    return geo


def mat(name, rgb, rough=0.6, metal=0.7, emissive=None, estrength=3.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emissive:
        b.inputs["Emission Color"].default_value = (*emissive, 1.0)
        b.inputs["Emission Strength"].default_value = estrength
    m.diffuse_color = (*(emissive or rgb), 1.0)  # workbench/viewport colour
    m.asset_mark()
    return m


def _shader_wear(m, base_fn, wear=0.5, grime=0.35, wear_col=(0.16, 0.16, 0.17),
                 bump_scale=40.0, bump_str=0.05, rough=0.6, metal=0.2,
                 wear_metal=0.9, seam=0.0, emit=None):
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(b.outputs[0], out.inputs[0])
    base_col, base_rough, base_metal = base_fn(nt)

    # edge mask: 1 - dot(Bevel(N), N) -- her dual-bevel trick, cleaned up
    bev = nt.nodes.new("ShaderNodeBevel")
    bev.samples = 4
    bev.inputs["Radius"].default_value = 0.10
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(bev.outputs["Normal"], dot.inputs[0])
    nt.links.new(geo.outputs["Normal"], dot.inputs[1])
    inv = nt.nodes.new("ShaderNodeMath")
    inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    nt.links.new(dot.outputs["Value"], inv.inputs[1])
    edge = nt.nodes.new("ShaderNodeMapRange")
    edge.inputs["From Min"].default_value = 0.03
    edge.inputs["From Max"].default_value = 0.30
    nt.links.new(inv.outputs[0], edge.inputs["Value"])
    brk = nt.nodes.new("ShaderNodeTexNoise")
    brk.inputs["Scale"].default_value = 9.0
    brk_gt = nt.nodes.new("ShaderNodeMath")
    brk_gt.operation = "GREATER_THAN"
    brk_gt.inputs[1].default_value = 0.42
    nt.links.new(brk.outputs["Fac"], brk_gt.inputs[0])
    wf = nt.nodes.new("ShaderNodeMath")
    wf.operation = "MULTIPLY"
    nt.links.new(edge.outputs["Result"], wf.inputs[0])
    nt.links.new(brk_gt.outputs[0], wf.inputs[1])
    wf2 = nt.nodes.new("ShaderNodeMath")
    wf2.operation = "MULTIPLY"
    nt.links.new(wf.outputs[0], wf2.inputs[0])
    wf2.inputs[1].default_value = wear

    # grime: inverted AO x streak noise
    ao = nt.nodes.new("ShaderNodeAmbientOcclusion")
    ao.inputs["Distance"].default_value = 1.2
    ao_inv = nt.nodes.new("ShaderNodeMath")
    ao_inv.operation = "SUBTRACT"
    ao_inv.inputs[0].default_value = 1.0
    nt.links.new(ao.outputs["AO"], ao_inv.inputs[1])
    tc = nt.nodes.new("ShaderNodeTexCoord")
    streak_map = nt.nodes.new("ShaderNodeMapping")
    streak_map.inputs["Scale"].default_value = (0.5, 4.0, 4.0)
    nt.links.new(tc.outputs["Object"], streak_map.inputs["Vector"])
    streak = nt.nodes.new("ShaderNodeTexNoise")
    streak.inputs["Scale"].default_value = 1.0
    nt.links.new(streak_map.outputs[0], streak.inputs["Vector"])
    gf = nt.nodes.new("ShaderNodeMath")
    gf.operation = "MULTIPLY"
    nt.links.new(ao_inv.outputs[0], gf.inputs[0])
    nt.links.new(streak.outputs["Fac"], gf.inputs[1])
    gf2 = nt.nodes.new("ShaderNodeMath")
    gf2.operation = "MULTIPLY"
    nt.links.new(gf.outputs[0], gf2.inputs[0])
    gf2.inputs[1].default_value = grime

    # colour: base -> wear reveal -> grime darken
    mix_w = nt.nodes.new("ShaderNodeMix")
    mix_w.data_type = "RGBA"
    nt.links.new(wf2.outputs[0], mix_w.inputs["Factor"])
    nt.links.new(base_col, mix_w.inputs[6])
    mix_w.inputs[7].default_value = (*wear_col, 1.0)
    mix_g = nt.nodes.new("ShaderNodeMix")
    mix_g.data_type = "RGBA"
    nt.links.new(gf2.outputs[0], mix_g.inputs["Factor"])
    nt.links.new(mix_w.outputs[2], mix_g.inputs[6])
    mix_g.inputs[7].default_value = (0.05, 0.05, 0.05, 1.0)
    col_out = mix_g.outputs[2]
    if seam > 0.0:
        # panel-seam paint shadow: darken by the raw edge mask (before
        # the wear noise breakup) at low strength
        sf = nt.nodes.new("ShaderNodeMath")
        sf.operation = "MULTIPLY"
        nt.links.new(edge.outputs["Result"], sf.inputs[0])
        sf.inputs[1].default_value = seam
        mix_s = nt.nodes.new("ShaderNodeMix")
        mix_s.data_type = "RGBA"
        nt.links.new(sf.outputs[0], mix_s.inputs["Factor"])
        nt.links.new(col_out, mix_s.inputs[6])
        mix_s.inputs[7].default_value = (0.04, 0.04, 0.05, 1.0)
        col_out = mix_s.outputs[2]
    nt.links.new(col_out, b.inputs["Base Color"])

    # roughness / metallic respond to wear (base may come from a pack map)
    def scalar_mix(base_src, base_const, worn_const):
        n = nt.nodes.new("ShaderNodeMix")
        n.data_type = "FLOAT"
        nt.links.new(wf2.outputs[0], n.inputs["Factor"])
        a = next(s for s in n.inputs if s.name == "A" and s.type == "VALUE")
        bs = next(s for s in n.inputs if s.name == "B" and s.type == "VALUE")
        if base_src is not None:
            nt.links.new(base_src, a)
        else:
            a.default_value = base_const
        bs.default_value = worn_const
        return next(s for s in n.outputs
                    if s.name == "Result" and s.type == "VALUE")
    nt.links.new(scalar_mix(base_rough, rough, 0.32),
                 b.inputs["Roughness"])
    nt.links.new(scalar_mix(base_metal, metal, wear_metal),
                 b.inputs["Metallic"])

    # micro bump
    bnoise = nt.nodes.new("ShaderNodeTexNoise")
    bnoise.inputs["Scale"].default_value = bump_scale
    bnoise.inputs["Detail"].default_value = 3.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = bump_str
    nt.links.new(bnoise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])

    if emit is not None:
        # emit = (colour_rgb, strength): running-light dot rows masked by
        # the per-point "fi_light" band attr x an object-space X pulse,
        # plus lit-window strips masked by per-face "fi_glowpanel" x a
        # finer window grid. Bakes into the emissive map.
        e_col, e_str = emit
        tc2 = nt.nodes.new("ShaderNodeTexCoord")
        so2 = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(tc2.outputs["Object"], so2.inputs[0])

        def pulse(src_sock, spacing, duty):
            d = nt.nodes.new("ShaderNodeMath")
            d.operation = "DIVIDE"
            nt.links.new(src_sock, d.inputs[0])
            d.inputs[1].default_value = spacing
            fr = nt.nodes.new("ShaderNodeMath")
            fr.operation = "FRACT"
            nt.links.new(d.outputs[0], fr.inputs[0])
            lt = nt.nodes.new("ShaderNodeMath")
            lt.operation = "LESS_THAN"
            nt.links.new(fr.outputs[0], lt.inputs[0])
            lt.inputs[1].default_value = duty
            return lt.outputs[0]

        al = nt.nodes.new("ShaderNodeAttribute")
        al.attribute_name = "fi_light"
        lsharp = nt.nodes.new("ShaderNodeMath")
        lsharp.operation = "GREATER_THAN"
        nt.links.new(al.outputs["Fac"], lsharp.inputs[0])
        lsharp.inputs[1].default_value = 0.45
        ldots = nt.nodes.new("ShaderNodeMath")
        ldots.operation = "MULTIPLY"
        nt.links.new(lsharp.outputs[0], ldots.inputs[0])
        nt.links.new(pulse(so2.outputs[0], 3.0, 0.35), ldots.inputs[1])

        aw = nt.nodes.new("ShaderNodeAttribute")
        aw.attribute_name = "fi_glowpanel"
        wgrid = nt.nodes.new("ShaderNodeMath")
        wgrid.operation = "MULTIPLY"
        nt.links.new(pulse(so2.outputs[0], 1.4, 0.55), wgrid.inputs[0])
        nt.links.new(pulse(so2.outputs[2], 1.1, 0.45), wgrid.inputs[1])
        wmask = nt.nodes.new("ShaderNodeMath")
        wmask.operation = "MULTIPLY"
        nt.links.new(aw.outputs["Fac"], wmask.inputs[0])
        nt.links.new(wgrid.outputs[0], wmask.inputs[1])
        wdim = nt.nodes.new("ShaderNodeMath")
        wdim.operation = "MULTIPLY"
        nt.links.new(wmask.outputs[0], wdim.inputs[0])
        wdim.inputs[1].default_value = 0.45
        etot = nt.nodes.new("ShaderNodeMath")
        etot.operation = "ADD"
        nt.links.new(ldots.outputs[0], etot.inputs[0])
        nt.links.new(wdim.outputs[0], etot.inputs[1])
        estr = nt.nodes.new("ShaderNodeMath")
        estr.operation = "MULTIPLY"
        nt.links.new(etot.outputs[0], estr.inputs[0])
        estr.inputs[1].default_value = e_str
        b.inputs["Emission Color"].default_value = (*e_col, 1.0)
        nt.links.new(estr.outputs[0], b.inputs["Emission Strength"])
    return b


def _base_brick(nt, c1, c2, mortar, map_scale=0.25, breakup=0.12):
    """Her panel-grid base: object-space Brick cells + Musgrave breakup."""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (map_scale, map_scale, map_scale)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    brick = nt.nodes.new("ShaderNodeTexBrick")
    brick.inputs["Color1"].default_value = (*c1, 1.0)
    brick.inputs["Color2"].default_value = (*c2, 1.0)
    brick.inputs["Mortar"].default_value = (*mortar, 1.0)
    brick.inputs["Mortar Size"].default_value = 0.02
    brick.inputs["Scale"].default_value = 1.0
    nt.links.new(mp.outputs[0], brick.inputs["Vector"])
    mus = nt.nodes.new("ShaderNodeTexNoise")
    mus.inputs["Scale"].default_value = 3.0
    mus.inputs["Detail"].default_value = 4.0
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["Factor"].default_value = breakup
    nt.links.new(brick.outputs["Color"], mix.inputs[6])
    nt.links.new(mus.outputs["Fac"], mix.inputs[7])
    return mix.outputs[2], None, None


def _base_flat(nt, rgb):
    rgbn = nt.nodes.new("ShaderNodeRGB")
    rgbn.outputs[0].default_value = (*rgb, 1.0)
    return rgbn.outputs[0], None, None


def _base_patchwork(nt, pal):
    """FI_FleetKit bright patchwork v2 (Homeworld register): per-face
    "fi_tint" float attr -> CONSTANT 4-stop ramp (base / light / dark /
    cream pop) -> "fi_hue" attr hue-jitters the result (the refs'
    greenish/bluish panel drift; the knob scales the ATTR, the shader
    applies full range) -> "fi_accent" mixes to the accent-field colour
    with the ramp variation kept at 0.22 inside accents (no flat orange)
    -> "fi_deckmark" paints object-space runway dashes decal-white.
    Face attrs bake to albedo natively; wear/grime stack via
    _shader_wear."""
    at = nt.nodes.new("ShaderNodeAttribute")
    at.attribute_name = "fi_tint"
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = "CONSTANT"
    base = pal["base"]
    light = tuple(min(1.0, c * 1.22) for c in base)
    dark = tuple(c * 0.78 for c in base)
    cr.elements[0].position = 0.0
    cr.elements[0].color = (*base, 1.0)
    cr.elements[1].position = 0.52
    cr.elements[1].color = (*light, 1.0)
    e2 = cr.elements.new(0.80)
    e2.color = (*dark, 1.0)
    e3 = cr.elements.new(0.94)
    e3.color = (*pal["accent2"], 1.0)
    nt.links.new(at.outputs["Fac"], ramp.inputs["Fac"])
    # hue jitter: fi_hue in [0, knob] -> hue offset centred on 0.5
    ah = nt.nodes.new("ShaderNodeAttribute")
    ah.attribute_name = "fi_hue"
    hmap = nt.nodes.new("ShaderNodeMapRange")
    hmap.inputs["From Min"].default_value = 0.0
    hmap.inputs["From Max"].default_value = 1.0
    hmap.inputs["To Min"].default_value = 0.46
    hmap.inputs["To Max"].default_value = 0.54
    nt.links.new(ah.outputs["Fac"], hmap.inputs["Value"])
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    nt.links.new(hmap.outputs["Result"], hsv.inputs["Hue"])
    nt.links.new(ramp.outputs["Color"], hsv.inputs["Color"])
    panel_col = hsv.outputs["Color"]
    # accent fields keep 22% of the panel variation (no flat orange)
    accent_var = nt.nodes.new("ShaderNodeMix")
    accent_var.data_type = "RGBA"
    accent_var.inputs["Factor"].default_value = 0.78
    nt.links.new(panel_col, accent_var.inputs[6])
    accent_var.inputs[7].default_value = (*pal["accent"], 1.0)
    aac = nt.nodes.new("ShaderNodeAttribute")
    aac.attribute_name = "fi_accent"
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    nt.links.new(aac.outputs["Fac"], mix.inputs["Factor"])
    nt.links.new(panel_col, mix.inputs[6])
    nt.links.new(accent_var.outputs[2], mix.inputs[7])
    # deck markings: object-space dashes on fi_deckmark faces
    adm = nt.nodes.new("ShaderNodeAttribute")
    adm.attribute_name = "fi_deckmark"
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sepo = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sepo.inputs[0])
    dash = nt.nodes.new("ShaderNodeMath")
    dash.operation = "FRACT"
    dx = nt.nodes.new("ShaderNodeMath")
    dx.operation = "DIVIDE"
    nt.links.new(sepo.outputs[0], dx.inputs[0])
    dx.inputs[1].default_value = 6.0
    nt.links.new(dx.outputs[0], dash.inputs[0])
    dwin = nt.nodes.new("ShaderNodeMath")
    dwin.operation = "LESS_THAN"
    nt.links.new(dash.outputs[0], dwin.inputs[0])
    dwin.inputs[1].default_value = 0.55
    dmask = nt.nodes.new("ShaderNodeMath")
    dmask.operation = "MULTIPLY"
    nt.links.new(adm.outputs["Fac"], dmask.inputs[0])
    nt.links.new(dwin.outputs[0], dmask.inputs[1])
    mix2 = nt.nodes.new("ShaderNodeMix")
    mix2.data_type = "RGBA"
    nt.links.new(dmask.outputs[0], mix2.inputs["Factor"])
    nt.links.new(mix.outputs[2], mix2.inputs[6])
    mix2.inputs[7].default_value = (*pal["decal"], 1.0)
    return mix2.outputs[2], None, None


_TEXDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "textures")


def _base_panels(nt, stem, tint, map_scale=0.25, lift=0.0):
    """Tiling PBR panel packs: box-projected set as the base layer;
    wear/grime stack on top. stem e.g. 'solarpanel003' or 'fabric048'."""
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (map_scale, map_scale, map_scale)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])

    def img_node(suffix, noncolor):
        path = None
        for sep in ("-", "_"):
            cand = os.path.join(_TEXDIR, f"{stem}{sep}{suffix}.png")
            if os.path.exists(cand):
                path = cand
                break
        if path is None:
            return None
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(path, check_existing=True)
        n.projection = "BOX"
        n.projection_blend = 0.25
        if noncolor:
            n.image.colorspace_settings.name = "Non-Color"
        nt.links.new(mp.outputs[0], n.inputs["Vector"])
        return n

    alb = img_node("albedo", False)
    tint_mix = nt.nodes.new("ShaderNodeMix")
    tint_mix.data_type = "RGBA"
    tint_mix.blend_type = "MULTIPLY"
    tint_mix.inputs["Factor"].default_value = 1.0
    nt.links.new(alb.outputs["Color"], tint_mix.inputs[6])
    tint_mix.inputs[7].default_value = (*tint, 1.0)
    col_out = tint_mix.outputs[2]
    if lift:
        bc = nt.nodes.new("ShaderNodeBrightContrast")
        bc.inputs["Bright"].default_value = lift
        nt.links.new(col_out, bc.inputs["Color"])
        col_out = bc.outputs["Color"]
    rough = img_node("roughness", True)
    metal = img_node("metallic", True)
    return (col_out,
            rough.outputs["Color"] if rough else None,
            metal.outputs["Color"] if metal else None)



def build_engine_cluster(mats):
    """Ring of engines, thrust axis +X, exhaust openings aft (-X).
    Type 0 = classic bells, 1 = aerospike (annular ring + centre spike),
    2 = ion/Hall array (flat housing, glowing annulus).
    GN Mesh Cone: Radius Bottom at local -Z -> Ry(+90 deg) puts the wide
    opening at -X (the -90 sign shipped v1's bells BACKWARDS)."""
    g = G("FI_EngineCluster")
    g.sock_in("Count", "NodeSocketInt", 3, 1, 9)
    g.sock_in("Ring Radius", "NodeSocketFloat", 3.0, 0.0, 50.0)
    g.sock_in("Bell Radius", "NodeSocketFloat", 1.2, 0.05, 20.0)
    g.sock_in("Bell Length", "NodeSocketFloat", 3.0, 0.1, 40.0)
    g.sock_out("Geometry", "NodeSocketGeometry")
    # ADDITIVE (engine-variety wave): appended after the original contract
    g.sock_in("Type", "NodeSocketInt", 0, 0, 2)
    g.sock_in("Segments", "NodeSocketInt", 12, 6, 48)

    AFT = (0.0, math.pi / 2.0, 0.0)     # wide/open end -> -X
    R = group_in(g, "Bell Radius")
    BL = group_in(g, "Bell Length")
    SEG = group_in(g, "Segments")

    def cone(r_top, r_bot, depth, verts=12):
        n = g.n("GeometryNodeMeshCone")
        g.l(SEG, in_sock(n, "Vertices"))
        for s, v in (("Radius Top", r_top), ("Radius Bottom", r_bot),
                     ("Depth", depth)):
            sock = in_sock(n, s, "VALUE")
            if hasattr(v, "is_linked"):
                g.l(v, sock)
            else:
                sock.default_value = v
        sm = g.n("GeometryNodeSetShadeSmooth")
        g.l(out_sock(n, "Mesh"), sm.inputs[0])
        g.l(out_sock(n, "Side"), in_sock(sm, "Selection"))
        in_sock(sm, "Shade Smooth").default_value = True
        return out_sock(sm, "Mesh")

    def cyl(radius, depth, verts=12):
        n = g.n("GeometryNodeMeshCylinder")
        g.l(SEG, in_sock(n, "Vertices"))
        for s, v in (("Radius", radius), ("Depth", depth)):
            sock = in_sock(n, s, "VALUE")
            if hasattr(v, "is_linked"):
                g.l(v, sock)
            else:
                sock.default_value = v
        sm = g.n("GeometryNodeSetShadeSmooth")
        g.l(out_sock(n, "Mesh"), sm.inputs[0])
        g.l(out_sock(n, "Side"), in_sock(sm, "Selection"))
        in_sock(sm, "Shade Smooth").default_value = True
        return out_sock(sm, "Mesh")

    def placed(node_out, rot, x_off, material):
        t = g.n("GeometryNodeTransform")
        g.l(node_out, t.inputs[0])
        in_sock(t, "Rotation").default_value = rot
        if x_off is not None:
            v = g.n("ShaderNodeCombineXYZ")
            if hasattr(x_off, "is_linked"):
                g.l(x_off, v.inputs[0])
            else:
                v.inputs[0].default_value = x_off
            g.l(v.outputs[0], in_sock(t, "Translation"))
        m = g.n("GeometryNodeSetMaterial")
        g.l(out_sock(t, "Geometry"), m.inputs[0])
        in_sock(m, "Material").default_value = material
        return out_sock(m, "Geometry")

    # -- type 0: classic bell + glow disc + housing -------------------------
    bell0 = cone(g.math("MULTIPLY", R, 0.35), R, BL)
    j0 = g.n("GeometryNodeJoinGeometry")
    g.l(placed(bell0, AFT, None, mats["engine"]),
        j0.inputs[0])
    disc0 = cyl(g.math("MULTIPLY", R, 0.92), 0.05)
    g.l(placed(disc0, AFT,
               g.math("MULTIPLY", BL, -0.45), mats["glow"]), j0.inputs[0])
    halo0 = cyl(g.math("MULTIPLY", R, 1.12), 0.03)
    g.l(placed(halo0, AFT,
               g.math("MULTIPLY", BL, -0.52), mats["glowhalo"]),
        j0.inputs[0])
    hous0 = cyl(g.math("MULTIPLY", R, 0.75), g.math("MULTIPLY", BL, 0.9), 10)
    g.l(placed(hous0, AFT,
               g.math("MULTIPLY", BL, 0.8), mats["metal"]), j0.inputs[0])

    # -- type 1: aerospike — annular shroud + centre spike aft --------------
    shroud = cone(R, g.math("MULTIPLY", R, 0.8),
                  g.math("MULTIPLY", BL, 0.45))
    j1 = g.n("GeometryNodeJoinGeometry")
    g.l(placed(shroud, AFT, None, mats["engine"]),
        j1.inputs[0])
    spike = cone(g.math("MULTIPLY", R, 0.55), 0.02,
                 g.math("MULTIPLY", BL, 0.85), 10)
    g.l(placed(spike,
               (0.0, -math.pi / 2.0, 0.0),   # taper points aft
               g.math("MULTIPLY", BL, -0.35), mats["metal"]), j1.inputs[0])
    ring1 = cyl(g.math("MULTIPLY", R, 0.88), 0.06)
    g.l(placed(ring1, AFT,
               g.math("MULTIPLY", BL, -0.18), mats["glow"]), j1.inputs[0])
    halo1 = cyl(g.math("MULTIPLY", R, 1.08), 0.03)
    g.l(placed(halo1, AFT,
               g.math("MULTIPLY", BL, -0.26), mats["glowhalo"]),
        j1.inputs[0])
    hous1 = cyl(g.math("MULTIPLY", R, 0.9), g.math("MULTIPLY", BL, 0.7), 10)
    g.l(placed(hous1, AFT,
               g.math("MULTIPLY", BL, 0.55), mats["metal"]), j1.inputs[0])

    # -- type 2: ion/Hall — squat drum, recessed glowing annulus ------------
    drum = cyl(R, g.math("MULTIPLY", BL, 0.35), 14)
    j2 = g.n("GeometryNodeJoinGeometry")
    g.l(placed(drum, AFT, None, mats["dark"]), j2.inputs[0])
    halo = cyl(g.math("MULTIPLY", R, 0.85), 0.05, 14)
    g.l(placed(halo, AFT,
               g.math("MULTIPLY", BL, -0.20), mats["glow"]), j2.inputs[0])
    halo2b = cyl(g.math("MULTIPLY", R, 1.05), 0.03, 14)
    g.l(placed(halo2b, AFT,
               g.math("MULTIPLY", BL, -0.28), mats["glowhalo"]),
        j2.inputs[0])
    core2 = cyl(g.math("MULTIPLY", R, 0.35),
                g.math("MULTIPLY", BL, 0.42), 10)
    g.l(placed(core2, AFT,
               g.math("MULTIPLY", BL, -0.1), mats["engine"]), j2.inputs[0])

    # -- pick the engine style (geometry switches: non-field bool = [1]) ----
    is1 = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
    g.l(group_in(g, "Type"), in_sock(is1, "A", "INT"))
    in_sock(is1, "B", "INT").default_value = 1
    is2 = g.n("FunctionNodeCompare", data_type="INT", operation="EQUAL")
    g.l(group_in(g, "Type"), in_sock(is2, "A", "INT"))
    in_sock(is2, "B", "INT").default_value = 2
    sw1 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(out_sock(is1, "Result"), in_sock(sw1, "Switch"))
    g.l(out_sock(j0, "Geometry"), in_sock(sw1, "False", "GEOMETRY"))
    g.l(out_sock(j1, "Geometry"), in_sock(sw1, "True", "GEOMETRY"))
    sw2 = g.n("GeometryNodeSwitch", input_type="GEOMETRY")
    g.l(out_sock(is2, "Result"), in_sock(sw2, "Switch"))
    g.l(out_sock(sw1, "Output", "GEOMETRY"), in_sock(sw2, "False", "GEOMETRY"))
    g.l(out_sock(j2, "Geometry"), in_sock(sw2, "True", "GEOMETRY"))

    # ring of points in the local YZ plane
    pts = g.n("GeometryNodePoints")
    g.l(group_in(g, "Count"), in_sock(pts, "Count"))
    idx = g.n("GeometryNodeInputIndex")
    ang = g.math("MULTIPLY",
                 g.math("DIVIDE", out_sock(idx, "Index"),
                        group_in(g, "Count")), TAU)
    py = g.math("MULTIPLY", g.math("COSINE", ang), group_in(g, "Ring Radius"))
    pz = g.math("MULTIPLY", g.math("SINE", ang), group_in(g, "Ring Radius"))
    pos = g.n("ShaderNodeCombineXYZ")
    g.l(py, pos.inputs[1])
    g.l(pz, pos.inputs[2])
    g.l(pos.outputs[0], in_sock(pts, "Position"))

    inst = g.n("GeometryNodeInstanceOnPoints")
    g.l(out_sock(pts, "Points"), inst.inputs[0])
    g.l(out_sock(sw2, "Output", "GEOMETRY"), in_sock(inst, "Instance"))
    real = g.n("GeometryNodeRealizeInstances")
    g.l(out_sock(inst, "Instances"), real.inputs[0])
    return g.finish(out_sock(real, "Geometry"))


# ------------------------------------------------------ FI dep groups ------
# Native re-expressions of the six vendor deformer/selection groups the
# war/fleet builders used to append. Socket names, ranges and defaults are
# kept call-site-compatible (e.g. U/V Ratio and Limit Distance stay FACTOR
# 0-1 sockets so out-of-range constants clamp identically). Groups are not
# asset-marked: they are internals, not kit surface.


def _vmath(g, op, a, b=None):
    """Vector math; returns the Vector output (or Value for scalar ops)."""
    node = g.n("ShaderNodeVectorMath", operation=op)

    def wire(sock, v):
        if hasattr(v, "is_linked"):
            g.l(v, sock)
        else:
            sock.default_value = v
    wire(node.inputs[0], a)
    if b is not None:
        if op == "SCALE":
            wire(in_sock(node, "Scale", "VALUE"), b)
        else:
            wire(node.inputs[1], b)
    if op in ("DOT_PRODUCT", "DISTANCE", "LENGTH"):
        return out_sock(node, "Value", "VALUE")
    return out_sock(node, "Vector", "VECTOR")


def _vmix(g, fac, a, b):
    """Per-component vector lerp a->b by scalar factor."""
    node = g.n("ShaderNodeMix", data_type="VECTOR")
    g.l(fac, in_sock(node, "Factor", "VALUE"))
    g.l(a, in_sock(node, "A", "VECTOR"))
    g.l(b, in_sock(node, "B", "VECTOR"))
    return out_sock(node, "Result", "VECTOR")


def _imath(g, op, a, b):
    node = g.n("FunctionNodeIntegerMath", operation=op)
    for sock, v in ((node.inputs[0], a), (node.inputs[1], b)):
        if hasattr(v, "is_linked"):
            g.l(v, sock)
        else:
            sock.default_value = v
    return node.outputs[0]


def _icmp(g, op, a, b):
    node = g.n("FunctionNodeCompare", data_type="INT", operation=op)
    for nm, v in (("A", a), ("B", b)):
        sock = in_sock(node, nm, "INT")
        if hasattr(v, "is_linked"):
            g.l(v, sock)
        else:
            sock.default_value = v
    return out_sock(node, "Result")


def _bmath(g, op, a, b=None):
    node = g.n("FunctionNodeBooleanMath", operation=op)
    g.l(a, node.inputs[0])
    if b is not None:
        g.l(b, node.inputs[1])
    return node.outputs[0]


def _switch(g, input_type, cond, false_v, true_v):
    node = g.n("GeometryNodeSwitch", input_type=input_type)
    stype = {"FLOAT": "VALUE"}.get(input_type, input_type)
    g.l(cond, in_sock(node, "Switch"))
    for nm, v in (("False", false_v), ("True", true_v)):
        sock = in_sock(node, nm, stype)
        if hasattr(v, "is_linked"):
            g.l(v, sock)
        else:
            sock.default_value = v
    return out_sock(node, "Output")


def build_fi_mesh_relax():
    """Laplacian hull softening: native Blur Attribute on position.
    Boundary points get weight 1 unless Pin Boundary (interior points get
    the Weight knob) -- on the closed war hulls everything is interior."""
    g = G("FI_MeshRelax")
    g.sock_in("Mesh", "NodeSocketGeometry")
    g.sock_in("Iterations", "NodeSocketInt", 5, 0)
    g.sock_in("Weight", "NodeSocketFloat", 1.0, 0.0, 1.0)
    g.sock_in("Pin Boundary", "NodeSocketBool", False)
    g.sock_in("Selection", "NodeSocketBool", True)
    g.sock_out("Mesh", "NodeSocketGeometry")

    en = g.n("GeometryNodeInputMeshEdgeNeighbors")
    bnd_e = _icmp(g, "EQUAL", out_sock(en, "Face Count"), 1)
    bnd_dom = g.n("GeometryNodeFieldOnDomain", domain="EDGE",
                  data_type="BOOLEAN")
    g.l(bnd_e, in_sock(bnd_dom, "Value"))
    vn = g.n("GeometryNodeInputMeshVertexNeighbors")
    lone = _icmp(g, "NOT_EQUAL", out_sock(vn, "Vertex Count"), 1)
    interior = _bmath(g, "AND",
                      _bmath(g, "NOT", out_sock(bnd_dom, "Value")), lone)
    unpinned = _bmath(g, "NOT", group_in(g, "Pin Boundary"))
    w = _switch(g, "FLOAT", interior, unpinned, group_in(g, "Weight"))

    pos = g.n("GeometryNodeInputPosition")
    blur = g.n("GeometryNodeBlurAttribute", data_type="FLOAT_VECTOR")
    g.l(out_sock(pos, "Position"), in_sock(blur, "Value", "VECTOR"))
    g.l(group_in(g, "Iterations"), in_sock(blur, "Iterations"))
    g.l(w, in_sock(blur, "Weight"))
    sp = g.n("GeometryNodeSetPosition")
    g.l(group_in(g, "Mesh"), sp.inputs[0])
    g.l(group_in(g, "Selection"), in_sock(sp, "Selection"))
    g.l(out_sock(blur, "Value", "VECTOR"), in_sock(sp, "Position"))
    return g.finish(out_sock(sp, "Geometry"), mark=False)


def build_fi_checker():
    """Periodic index selection: every (Selected + Deselected) elements,
    the first Selected are true. On divider panel islands this reads as a
    deterministic accent scatter."""
    g = G("FI_CheckerSelection")
    g.sock_in("Selected", "NodeSocketInt", 1, 1)
    g.sock_in("Deselected", "NodeSocketInt", 1, 1)
    g.sock_in("Offset", "NodeSocketInt", 0)
    g.sock_in("Start Index", "NodeSocketInt", 0)
    g.sock_out("Selection", "NodeSocketBool")

    idx = g.n("GeometryNodeInputIndex")
    rel = _imath(g, "SUBTRACT",
                 _imath(g, "SUBTRACT", out_sock(idx, "Index"),
                        group_in(g, "Start Index")),
                 group_in(g, "Offset"))
    period = _imath(g, "ADD", group_in(g, "Selected"),
                    group_in(g, "Deselected"))
    m = _imath(g, "FLOORED_MODULO", rel, period)
    res = _icmp(g, "LESS_THAN", m, group_in(g, "Selected"))
    return g.finish(res, mark=False)


def build_fi_mirror():
    """Sequential origin mirror about X/Y/Z: scaled copy + flipped faces
    joined in, optional weld. X defaults ON (the war hull was built with
    the vendor default and ships a full X-mirrored shell -- keep parity)."""
    g = G("FI_Mirror")
    g.sock_in("Geometry", "NodeSocketGeometry")
    g.sock_in("X", "NodeSocketBool", True)
    g.sock_in("Y", "NodeSocketBool", False)
    g.sock_in("Z", "NodeSocketBool", False)
    g.sock_in("Merge By Distance", "NodeSocketBool", False)
    g.sock_in("Distance", "NodeSocketFloat", 0.001, 0.0)
    g.sock_out("Geometry", "NodeSocketGeometry")

    geo = group_in(g, "Geometry")
    for axis, scale in (("X", (-1.0, 1.0, 1.0)),
                        ("Y", (1.0, -1.0, 1.0)),
                        ("Z", (1.0, 1.0, -1.0))):
        pos = g.n("GeometryNodeInputPosition")
        mpos = _vmath(g, "MULTIPLY", out_sock(pos, "Position"), scale)
        sp = g.n("GeometryNodeSetPosition")
        g.l(geo, sp.inputs[0])
        g.l(mpos, in_sock(sp, "Position"))
        ff = g.n("GeometryNodeFlipFaces")
        g.l(out_sock(sp, "Geometry"), ff.inputs[0])
        # element order is part of the contract (index-seeded randomness
        # runs downstream). The retired vendor group emits
        # [mirrored, original] on the X stage but [original, mirrored] on
        # Y/Z (hand-authored quirk); multi-input joins concatenate in
        # reverse link-creation order, hence the per-axis link order.
        j = g.n("GeometryNodeJoinGeometry")
        if axis == "X":
            g.l(geo, j.inputs[0])
            g.l(out_sock(ff, "Mesh"), j.inputs[0])
        else:
            g.l(out_sock(ff, "Mesh"), j.inputs[0])
            g.l(geo, j.inputs[0])
        geo = _switch(g, "GEOMETRY", group_in(g, axis), geo,
                      out_sock(j, "Geometry"))

    mrg = g.n("GeometryNodeMergeByDistance")
    g.l(geo, mrg.inputs[0])
    g.l(group_in(g, "Distance"), in_sock(mrg, "Distance"))
    out = _switch(g, "GEOMETRY", group_in(g, "Merge By Distance"), geo,
                  out_sock(mrg, "Geometry"))
    return g.finish(out, mark=False)


def build_fi_taper():
    """Scale the components perpendicular to Axis, lerped along the axial
    extent: bottom gets Lower Factor + 1, top gets Upper Factor + 1 (the
    +1 offset is the shipped vendor semantic the call sites rely on)."""
    g = G("FI_Taper")
    g.sock_in("Geometry", "NodeSocketGeometry")
    g.sock_in("Upper Factor", "NodeSocketFloat", 0.0)
    g.sock_in("Lower Factor", "NodeSocketFloat", 0.0)
    g.sock_in("Axis", "NodeSocketVector", (0.0, 0.0, 1.0))
    g.sock_out("Geometry", "NodeSocketGeometry")

    n = _vmath(g, "NORMALIZE", group_in(g, "Axis"))
    pos = g.n("GeometryNodeInputPosition")
    z = _vmath(g, "DOT_PRODUCT", out_sock(pos, "Position"), n)
    st = g.n("GeometryNodeAttributeStatistic", domain="POINT")
    g.l(group_in(g, "Geometry"), st.inputs[0])
    g.l(z, in_sock(st, "Attribute"))
    s = g.n("ShaderNodeMapRange", clamp=True)
    g.l(z, in_sock(s, "Value", "VALUE"))
    g.l(out_sock(st, "Min", "VALUE"), in_sock(s, "From Min", "VALUE"))
    g.l(out_sock(st, "Max", "VALUE"), in_sock(s, "From Max", "VALUE"))
    g.l(g.math("ADD", group_in(g, "Lower Factor"), 1.0),
        in_sock(s, "To Min", "VALUE"))
    g.l(g.math("ADD", group_in(g, "Upper Factor"), 1.0),
        in_sock(s, "To Max", "VALUE"))
    axial = _vmath(g, "SCALE", n, z)
    radial = _vmath(g, "SUBTRACT", out_sock(pos, "Position"), axial)
    newpos = _vmath(g, "ADD",
                    _vmath(g, "SCALE", radial,
                           out_sock(s, "Result", "VALUE")), axial)
    sp = g.n("GeometryNodeSetPosition")
    g.l(group_in(g, "Geometry"), sp.inputs[0])
    g.l(newpos, in_sock(sp, "Position"))
    return g.finish(out_sock(sp, "Geometry"), mark=False)


def build_fi_bend():
    """Classic bend deformer in the frame whose local Z aligns to Axis:
    arc radius = -extent/Angle, theta proportional to local z. Zero-angle
    passthrough guard (the formula degenerates at Angle == 0)."""
    g = G("FI_Bend")
    g.sock_in("Geometry", "NodeSocketGeometry")
    g.sock_in("Angle", "NodeSocketFloat", 0.0)
    g.sock_in("Axis", "NodeSocketVector", (1.0, 0.0, 0.0))
    g.sock_out("Geometry", "NodeSocketGeometry")

    # the vendor semantic: Axis is the arc's rotation axis -- local X
    # aligns to it, theta runs along local Z, displacement in local Y/Z
    al = g.n("FunctionNodeAlignRotationToVector", axis="X",
             pivot_axis="AUTO")
    g.l(group_in(g, "Axis"), in_sock(al, "Vector"))
    inv = g.n("FunctionNodeInvertRotation")
    g.l(out_sock(al, "Rotation"), inv.inputs[0])
    pos = g.n("GeometryNodeInputPosition")
    toloc = g.n("FunctionNodeRotateVector")
    g.l(out_sock(pos, "Position"), in_sock(toloc, "Vector"))
    g.l(out_sock(inv, "Rotation"), in_sock(toloc, "Rotation"))
    sep = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(toloc, "Vector"), sep.inputs[0])

    st = g.n("GeometryNodeAttributeStatistic", domain="POINT")
    g.l(group_in(g, "Geometry"), st.inputs[0])
    g.l(sep.outputs[2], in_sock(st, "Attribute"))
    ext = g.math("MAXIMUM",
                 g.math("SUBTRACT", out_sock(st, "Max", "VALUE"),
                        out_sock(st, "Min", "VALUE")), 1e-9)
    k = g.math("DIVIDE", g.math("MULTIPLY", group_in(g, "Angle"), -1.0),
               ext)
    rc = g.math("DIVIDE", 1.0, k)
    theta = g.math("MULTIPLY", k, sep.outputs[2])
    rmy = g.math("SUBTRACT", rc, sep.outputs[1])
    y2 = g.math("SUBTRACT", rc,
                g.math("MULTIPLY", rmy, g.math("COSINE", theta)))
    z2 = g.math("MULTIPLY", rmy, g.math("SINE", theta))
    comb = g.n("ShaderNodeCombineXYZ")
    g.l(sep.outputs[0], comb.inputs[0])
    g.l(y2, comb.inputs[1])
    g.l(z2, comb.inputs[2])
    toworld = g.n("FunctionNodeRotateVector")
    g.l(comb.outputs[0], in_sock(toworld, "Vector"))
    g.l(out_sock(al, "Rotation"), in_sock(toworld, "Rotation"))

    iszero = g.n("FunctionNodeCompare", data_type="FLOAT",
                 operation="EQUAL")
    g.l(group_in(g, "Angle"), in_sock(iszero, "A", "VALUE"))
    in_sock(iszero, "B", "VALUE").default_value = 0.0
    in_sock(iszero, "Epsilon", "VALUE").default_value = 1e-3
    newpos = _switch(g, "VECTOR", out_sock(iszero, "Result"),
                     out_sock(toworld, "Vector"), out_sock(pos, "Position"))
    sp = g.n("GeometryNodeSetPosition")
    g.l(group_in(g, "Geometry"), sp.inputs[0])
    g.l(newpos, in_sock(sp, "Position"))
    return g.finish(out_sock(sp, "Geometry"), mark=False)


def build_fi_face_divider():
    """Seeded recursive panel divider. Each pass, selected tri/quad faces
    are probabilistically cut in two by a straight chord; children are
    DETACHED islands whose borders coincide with their neighbours
    (conforming T-junctions -- the downstream 2 mm weld re-fuses them).
    Limit Distance is PARAMETRIC: the cut fraction is uniform in
    [LD/2, 1 - LD/2] (the war/fleet call sites feed B-scaled values that
    clamp at 1.0 -- shipped behaviour, keep it). Distortion skews the far
    edge's fraction; 0 keeps cuts parallel."""
    g = G("FI_FaceDivider")
    g.sock_in("Mesh", "NodeSocketGeometry")
    g.sock_in("Iterations", "NodeSocketInt", 4, 1, 10)
    g.sock_in("U/V Ratio", "NodeSocketFloat", 0.5, 0.0, 1.0)
    g.sock_in("Divide Probability", "NodeSocketFloat", 1.0, 0.0, 1.0)
    g.sock_in("Even Probability", "NodeSocketFloat", 0.3, 0.0, 1.0)
    g.sock_in("Limit Distance", "NodeSocketFloat", 0.2, 0.0, 1.0)
    g.sock_in("Distortion", "NodeSocketFloat", 0.0, 0.0, 1.0)
    g.sock_in("Seed", "NodeSocketInt", 0, -10000, 10000)
    g.sock_in("Selection", "NodeSocketBool", True)
    g.sock_out("Mesh", "NodeSocketGeometry")

    # pre-pass: only selected tris/quads enter the divider; the rest
    # bypasses untouched (selection is evaluated once, on the input mesh)
    fn = g.n("GeometryNodeInputMeshFaceNeighbors")
    nc = out_sock(fn, "Vertex Count")
    quad_or_tri = _bmath(g, "OR", _icmp(g, "EQUAL", nc, 4),
                         _icmp(g, "EQUAL", nc, 3))
    eligible = _bmath(g, "AND", group_in(g, "Selection"), quad_or_tri)
    pre = g.n("GeometryNodeSeparateGeometry", domain="FACE")
    g.l(group_in(g, "Mesh"), pre.inputs[0])
    g.l(eligible, in_sock(pre, "Selection"))

    ri = g.n("GeometryNodeRepeatInput")
    ro = g.n("GeometryNodeRepeatOutput")
    ri.pair_with_output(ro)
    g.l(group_in(g, "Iterations"), in_sock(ri, "Iterations"))
    g.l(out_sock(pre, "Selection", "GEOMETRY"), in_sock(ri, "Geometry"))
    seed_i = g.math("ADD", group_in(g, "Seed"),
                    g.math("MULTIPLY", out_sock(ri, "Iteration"), 31.0))

    # which faces get cut this pass
    cut = g.n("FunctionNodeRandomValue", data_type="BOOLEAN")
    g.l(group_in(g, "Divide Probability"),
        in_sock(cut, "Probability", "VALUE"))
    g.l(g.math("ADD", seed_i, 756.0), in_sock(cut, "Seed"))
    sep = g.n("GeometryNodeSeparateGeometry", domain="FACE")
    g.l(out_sock(ri, "Geometry"), sep.inputs[0])
    g.l(out_sock(cut, "Value", "BOOLEAN"), in_sock(sep, "Selection"))

    # per-face cut parameters, captured before duplication ----------------
    fidx = g.n("GeometryNodeInputIndex")
    fn2 = g.n("GeometryNodeInputMeshFaceNeighbors")
    nc2 = out_sock(fn2, "Vertex Count")
    corner_pos = []
    for kk in range(4):
        sort = (_imath(g, "MINIMUM", 3, _imath(g, "SUBTRACT", nc2, 1))
                if kk == 3 else kk)
        cof = g.n("GeometryNodeCornersOfFace")
        g.l(out_sock(fidx, "Index"), in_sock(cof, "Face Index"))
        if kk == 3:
            g.l(sort, in_sock(cof, "Sort Index"))
        else:
            in_sock(cof, "Sort Index").default_value = kk
        fai = g.n("GeometryNodeFieldAtIndex", domain="CORNER",
                  data_type="FLOAT_VECTOR")
        p = g.n("GeometryNodeInputPosition")
        g.l(out_sock(p, "Position"), in_sock(fai, "Value", "VECTOR"))
        g.l(out_sock(cof, "Corner Index"), in_sock(fai, "Index"))
        corner_pos.append(out_sock(fai, "Value", "VECTOR"))
    p0, p1, p2, p3 = corner_pos

    du = g.math("MULTIPLY",
                g.math("ADD", _vmath(g, "DISTANCE", p0, p1),
                       _vmath(g, "DISTANCE", p3, p2)), 0.5)
    dv = g.math("MULTIPLY",
                g.math("ADD", _vmath(g, "DISTANCE", p1, p2),
                       _vmath(g, "DISTANCE", p0, p3)), 0.5)
    aspect = g.math("DIVIDE", g.math("MINIMUM", du, dv),
                    g.math("MAXIMUM", g.math("MAXIMUM", du, dv), 1e-9))
    forced = g.math("LESS_THAN", aspect, group_in(g, "Even Probability"))
    dir_forced = g.math("GREATER_THAN", du, dv)
    # the retired vendor group's U/V Ratio picks the OPPOSITE axis from
    # our U convention (all shipped call sites clamp it to 1.0, so the
    # polarity decides every unforced cut) -- invert the random branch
    dir_rand = g.n("FunctionNodeRandomValue", data_type="BOOLEAN")
    g.l(group_in(g, "U/V Ratio"), in_sock(dir_rand, "Probability", "VALUE"))
    g.l(g.math("ADD", seed_i, 13.0), in_sock(dir_rand, "Seed"))
    dir_rand_u = _bmath(g, "NOT", out_sock(dir_rand, "Value", "BOOLEAN"))
    diru = _switch(g, "BOOLEAN", forced, dir_rand_u, dir_forced)

    ldh = g.math("MULTIPLY", group_in(g, "Limit Distance"), 0.5)
    lo = g.n("ShaderNodeCombineXYZ")
    g.l(ldh, lo.inputs[0])
    g.l(ldh, lo.inputs[1])
    hi = g.n("ShaderNodeCombineXYZ")
    onem = g.math("SUBTRACT", 1.0, ldh)
    g.l(onem, hi.inputs[0])
    g.l(onem, hi.inputs[1])
    rv = g.n("FunctionNodeRandomValue", data_type="FLOAT_VECTOR")
    g.l(lo.outputs[0], in_sock(rv, "Min", "VECTOR"))
    g.l(hi.outputs[0], in_sock(rv, "Max", "VECTOR"))
    g.l(g.math("ADD", seed_i, 117.0), in_sock(rv, "Seed"))
    rsep = g.n("ShaderNodeSeparateXYZ")
    g.l(out_sock(rv, "Value", "VECTOR"), rsep.inputs[0])
    ta = rsep.outputs[0]
    tb = g.math("ADD", ta,
                g.math("MULTIPLY",
                       g.math("SUBTRACT", rsep.outputs[1], ta),
                       group_in(g, "Distortion")))
    isq = _icmp(g, "EQUAL", nc2, 4)

    cap = g.n("GeometryNodeCaptureAttribute", domain="FACE")
    g.l(out_sock(sep, "Selection", "GEOMETRY"), cap.inputs[0])
    cap_fields = {}
    for name, dtype, src in (("P0", "FLOAT_VECTOR", p0),
                             ("P1", "FLOAT_VECTOR", p1),
                             ("P2", "FLOAT_VECTOR", p2),
                             ("P3", "FLOAT_VECTOR", p3),
                             ("TA", "FLOAT", ta), ("TB", "FLOAT", tb),
                             ("DIRU", "BOOLEAN", diru),
                             ("QUAD", "BOOLEAN", isq)):
        item = cap.capture_items.new("FLOAT", name)
        item.data_type = dtype
        g.l(src, in_sock(cap, name))
        cap_fields[name] = out_sock(cap, name)

    dup = g.n("GeometryNodeDuplicateElements", domain="FACE")
    g.l(out_sock(cap, "Geometry"), dup.inputs[0])
    in_sock(dup, "Amount").default_value = 2

    # per-point: which duplicate / which corner am I -> snapped position
    vidx = g.n("GeometryNodeInputIndex")
    cov = g.n("GeometryNodeCornersOfVertex")
    g.l(out_sock(vidx, "Index"), in_sock(cov, "Vertex Index"))
    foc = g.n("GeometryNodeFaceOfCorner")
    g.l(out_sock(cov, "Corner Index"), in_sock(foc, "Corner Index"))
    face_i = out_sock(foc, "Face Index")
    s_in_face = out_sock(foc, "Index in Face")

    def face_val(field_src, dtype):
        fai = g.n("GeometryNodeFieldAtIndex", domain="FACE",
                  data_type=dtype)
        stype = {"FLOAT_VECTOR": "VECTOR", "FLOAT": "VALUE",
                 "BOOLEAN": "BOOLEAN", "INT": "INT"}[dtype]
        g.l(field_src, in_sock(fai, "Value", stype))
        g.l(face_i, in_sock(fai, "Index"))
        return out_sock(fai, "Value", stype)

    P0 = face_val(cap_fields["P0"], "FLOAT_VECTOR")
    P1 = face_val(cap_fields["P1"], "FLOAT_VECTOR")
    P2 = face_val(cap_fields["P2"], "FLOAT_VECTOR")
    P3 = face_val(cap_fields["P3"], "FLOAT_VECTOR")
    TA = face_val(cap_fields["TA"], "FLOAT")
    TB = face_val(cap_fields["TB"], "FLOAT")
    DIRU = face_val(cap_fields["DIRU"], "BOOLEAN")
    QUAD = face_val(cap_fields["QUAD"], "BOOLEAN")
    DNUM = face_val(out_sock(dup, "Duplicate Index"), "INT")

    qa_u = _vmix(g, TA, P0, P1)
    qb_u = _vmix(g, TB, P3, P2)
    qa_v = _vmix(g, TA, P0, P3)
    qb_v = _vmix(g, TB, P1, P2)
    kcase = _imath(g, "ADD", _imath(g, "MULTIPLY", DNUM, 4), s_in_face)

    def isw8(items):
        node = g.n("GeometryNodeIndexSwitch", data_type="VECTOR")
        while len(node.index_switch_items) < 8:
            node.index_switch_items.new()
        g.l(kcase, in_sock(node, "Index"))
        for i, src in enumerate(items):
            g.l(src, in_sock(node, str(i)))
        return out_sock(node, "Output")

    # child 0 keeps the low corners, child 1 the high ones; the chord
    # (qa -> qb) is shared verbatim so islands conform
    pos_u = isw8([P0, qa_u, qb_u, P3, qa_u, P1, P2, qb_u])
    pos_v = isw8([P0, P1, qb_v, qa_v, qa_v, qb_v, P2, P3])
    pos_t = isw8([P0, qa_u, P2, P2, qa_u, P1, P2, P2])
    pos_q = _switch(g, "VECTOR", DIRU, pos_v, pos_u)
    pos_f = _switch(g, "VECTOR", QUAD, pos_t, pos_q)

    spd = g.n("GeometryNodeSetPosition")
    g.l(out_sock(dup, "Geometry"), spd.inputs[0])
    g.l(pos_f, in_sock(spd, "Position"))

    # element order is part of the contract: uncut/original geometry must
    # PRECEDE cut children, so the downstream 2 mm weld keeps the original
    # verts (and their deliberately stale attributes, e.g. the fleet's
    # pristine-loft fi_u driving the light bands). Multi-input joins
    # concatenate in reverse link-creation order.
    jz = g.n("GeometryNodeJoinGeometry")
    g.l(out_sock(spd, "Geometry"), jz.inputs[0])
    g.l(out_sock(sep, "Inverted", "GEOMETRY"), jz.inputs[0])
    g.l(out_sock(jz, "Geometry"), in_sock(ro, "Geometry"))

    jout = g.n("GeometryNodeJoinGeometry")
    g.l(out_sock(ro, "Geometry"), jout.inputs[0])
    g.l(out_sock(pre, "Inverted", "GEOMETRY"), jout.inputs[0])
    return g.finish(out_sock(jout, "Geometry"), mark=False)


FI_DEP_BUILDERS = {
    "Mirror": build_fi_mirror,
    "Taper": build_fi_taper,
    "Bend": build_fi_bend,
    "Mesh Relax": build_fi_mesh_relax,
    "Checker Selection": build_fi_checker,
    "Mesh Face Divider": build_fi_face_divider,
}


def fi_deps(want=None):
    """Build the native FI replacements for the retired vendor groups.
    Returns the same {legacy-name: node_group} dict shape the old vendor
    append returned, so gcall sites keyed by legacy names need no change."""
    return {name: FI_DEP_BUILDERS[name]() for name in
            (want or FI_DEP_BUILDERS)}
