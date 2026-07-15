#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# bake_ship.py -- PRODUCTION bake: procedural shaders -> textures -> .glb.
#
#   blender -b shipgen_playground.blend --python bake_ship.py -- \
#       --object frame_skiff --out out/frame_skiff_baked.glb \
#       [--res 2048] [--samples 8] [--detail-lo 0]
#
# HI->LO pipeline: a HI copy at Detail 2 (smooth-shaded, full curve
# resolution) is the bake SOURCE for normal + AO (selected-to-active); the
# LO copy at --detail-lo is what ships. Smart UV Project on LO (GN emits no
# UVs). Albedo/rough/emissive bake from LO's own procedural shaders (Bevel
# wear + AO grime are Cycles-only, so bakes carry the detail). Metallic is
# baked via the emission-swap trick. ORM packs R=AO, G=rough, B=metal.
# Cycles denoising is ALWAYS off (some GPU stacks render black with it).
# Never saves the source .blend.

import bpy
import json
import os
import sys
import numpy as np

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    if name in argv:
        return argv[argv.index(name) + 1]
    return default


OBJ = arg("--object") or sys.exit("need --object")
OUT = os.path.abspath(arg("--out") or sys.exit("need --out"))
RES = int(arg("--res", "2048"))
SAMPLES = int(arg("--samples", "8"))
DETAIL_LO = int(arg("--detail-lo", "0"))
STEM = os.path.splitext(OUT)[0]
HERE = os.path.dirname(os.path.abspath(__file__))

src_ob = bpy.data.objects.get(OBJ) or sys.exit(f"no object {OBJ}")
CONTRACT = {}
for _cf in ("kit_contract.json", "war_contract.json",
            "fleet_contract.json"):
    try:
        with open(os.path.join(HERE, _cf)) as f:
            CONTRACT.update(json.load(f))
    except OSError:
        pass


def ident(group, name):
    for it in CONTRACT.get(group, []):
        if it["name"] == name and it["in_out"] == "INPUT":
            return it["identifier"]
    return None


def realized_copy(tag, detail):
    """Evaluated+realized mesh copy of src_ob at a given Detail level."""
    mod0 = src_ob.modifiers[0] if src_ob.modifiers else None
    det_id = ident(mod0.node_group.name, "Detail") \
        if mod0 and mod0.node_group else None
    old_det = None
    if det_id is not None:
        old_det = mod0.get(det_id, 0)
        mod0[det_id] = detail
        src_ob.update_tag()
    rg = bpy.data.node_groups.get("BakeRealize")
    if rg is None:
        rg = bpy.data.node_groups.new("BakeRealize", "GeometryNodeTree")
        rg.interface.new_socket("Geometry", in_out="INPUT",
                                socket_type="NodeSocketGeometry")
        rg.interface.new_socket("Geometry", in_out="OUTPUT",
                                socket_type="NodeSocketGeometry")
        gi = rg.nodes.new("NodeGroupInput")
        rl = rg.nodes.new("GeometryNodeRealizeInstances")
        go = rg.nodes.new("NodeGroupOutput")
        rg.links.new(gi.outputs[0], rl.inputs[0])
        rg.links.new(rl.outputs[0], go.inputs[0])
    mod = src_ob.modifiers.new("BakeRealize", "NODES")
    mod.node_group = rg
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    me = bpy.data.meshes.new_from_object(
        src_ob.evaluated_get(dg), preserve_all_data_layers=True,
        depsgraph=dg)
    src_ob.modifiers.remove(mod)
    if det_id is not None:
        mod0[det_id] = old_det
        src_ob.update_tag()
    # Blender 5.x: use_auto_smooth is gone — mark edges sharp by angle,
    # smooth-shaded faces stay smooth between sharps (same visual result)
    if hasattr(me, "set_sharp_from_angle"):
        me.set_sharp_from_angle(angle=0.56)   # ~32 deg
    ob = bpy.data.objects.new(f"{OBJ}_{tag}", me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


lo = realized_copy("lo", DETAIL_LO)
hi = realized_copy("hi", 2)

# LO materials must be LOCAL (kit materials arrive library-linked and their
# node trees silently refuse bake-target nodes); empty slots get fillers.
for slot in lo.material_slots:
    if slot.material is None:
        m = bpy.data.materials.new("bake_empty")
        m.use_nodes = True
        slot.material = m
    else:
        slot.material = slot.material.copy()

# ---- reliable UVs on LO ------------------------------------------------------
for o in bpy.data.objects:
    o.select_set(False)
lo.select_set(True)
bpy.context.view_layer.objects.active = lo
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(island_margin=0.02)
bpy.ops.object.mode_set(mode="OBJECT")

# ---- bake setup ---------------------------------------------------------------
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = SAMPLES
scene.render.bake.margin = 6
scene.cycles.use_denoising = False   # her machine: denoiser => black output

images = {}
for key, colorspace in (("albedo", "sRGB"), ("rough", "Non-Color"),
                        ("normal", "Non-Color"), ("ao", "Non-Color"),
                        ("metal", "Non-Color"), ("emissive", "sRGB")):
    img = bpy.data.images.new(f"bake_{key}", RES, RES, alpha=False)
    img.colorspace_settings.name = colorspace
    images[key] = img


def set_bake_target(img):
    for slot in lo.material_slots:
        m = slot.material
        if not m or not m.use_nodes:
            continue
        nt = m.node_tree
        node = nt.nodes.get("BAKE_TARGET")
        if node is None:
            node = nt.nodes.new("ShaderNodeTexImage")
            node.name = "BAKE_TARGET"
        node.image = img
        nt.nodes.active = node


def bake(key, bake_type, s2a=False, extra=None):
    set_bake_target(images[key])
    for o in bpy.data.objects:
        o.select_set(False)
    if s2a:
        hi.select_set(True)
    lo.select_set(True)
    bpy.context.view_layer.objects.active = lo
    kw = dict(type=bake_type, use_selected_to_active=s2a)
    if s2a:
        dim = max(lo.dimensions)
        kw["cage_extrusion"] = dim * 0.01
        kw["max_ray_distance"] = dim * 0.05
    if extra:
        kw.update(extra)
    print(f"bake_ship: baking {key} ({RES}px, s2a={s2a})...")
    bpy.ops.object.bake(**kw)
    path = f"{STEM}_{key}.png"
    images[key].filepath_raw = path
    images[key].file_format = "PNG"
    images[key].save()


bake("albedo", "DIFFUSE", extra={"pass_filter": {"COLOR"}})
bake("rough", "ROUGHNESS")
bake("normal", "NORMAL", s2a=True)   # hi-detail curvature onto lo
bake("ao", "AO", s2a=True)

# metallic via emission swap: reroute each material's metallic into Emission
swaps = []
for slot in lo.material_slots:
    m = slot.material
    if not m or not m.use_nodes:
        continue
    nt = m.node_tree
    outn = next((n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"), None)
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if not outn or not bsdf or not outn.inputs["Surface"].links:
        continue
    old_from = outn.inputs["Surface"].links[0].from_socket
    em = nt.nodes.new("ShaderNodeEmission")
    em.name = "METAL_SWAP"
    msock = bsdf.inputs["Metallic"]
    if msock.links:
        nt.links.new(msock.links[0].from_socket, em.inputs["Color"])
    else:
        v = msock.default_value
        em.inputs["Color"].default_value = (v, v, v, 1.0)
    nt.links.new(em.outputs[0], outn.inputs["Surface"])
    swaps.append((nt, outn, old_from, em))
bake("metal", "EMIT")
for nt, outn, old_from, em in swaps:
    nt.links.new(old_from, outn.inputs["Surface"])
    nt.nodes.remove(em)

bake("emissive", "EMIT")

# ---- ORM pack (engine mr map: R=AO, G=rough, B=metal) --------------------------
def chan(img):
    return np.array(img.pixels[:]).reshape(-1, 4)[:, 0]


orm = np.ones((RES * RES, 4), dtype=np.float32)
orm[:, 0] = chan(images["ao"])
orm[:, 1] = chan(images["rough"])
orm[:, 2] = chan(images["metal"])
orm_img = bpy.data.images.new("bake_orm", RES, RES, alpha=False)
orm_img.colorspace_settings.name = "Non-Color"
orm_img.pixels = orm.ravel().tolist()
orm_img.filepath_raw = f"{STEM}_orm.png"
orm_img.file_format = "PNG"
orm_img.save()
print(f"bake_ship: wrote {STEM}_orm.png")

# ---- baked export material ------------------------------------------------------
mat = bpy.data.materials.new(f"{OBJ}_baked")
mat.use_nodes = True
nt = mat.node_tree
b = nt.nodes["Principled BSDF"]


def tex(img):
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = img
    return n


nt.links.new(tex(images["albedo"]).outputs["Color"], b.inputs["Base Color"])
orm_tex = tex(orm_img)
sep = nt.nodes.new("ShaderNodeSeparateColor")
nt.links.new(orm_tex.outputs["Color"], sep.inputs[0])
nt.links.new(sep.outputs["Green"], b.inputs["Roughness"])
nt.links.new(sep.outputs["Blue"], b.inputs["Metallic"])
nm_tex = tex(images["normal"])
nm = nt.nodes.new("ShaderNodeNormalMap")
nt.links.new(nm_tex.outputs["Color"], nm.inputs["Color"])
nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
nt.links.new(tex(images["emissive"]).outputs["Color"],
             b.inputs["Emission Color"])
b.inputs["Emission Strength"].default_value = 1.0

lo.data.materials.clear()
lo.data.materials.append(mat)

# ---- export ----------------------------------------------------------------------
for o in bpy.data.objects:
    o.select_set(False)
lo.select_set(True)
bpy.context.view_layer.objects.active = lo
bpy.ops.export_scene.gltf(
    filepath=OUT, export_format="GLB", use_selection=True,
    export_apply=True, export_yup=True, export_image_format="AUTO",
    export_animations=False, export_skins=False, export_morph=False)
tris = sum(len(p.vertices) - 2 for p in lo.data.polygons)
print(f"bake_ship: OK -> {OUT} (lo tris={tris})")
