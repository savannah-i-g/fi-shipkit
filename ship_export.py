#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 Savannah (FI ShipKit)
# ship_export.py -- deterministic Blender -> .glb export for game engines.
#
# Convention (README): ships are authored nose = +X, up = +Z in Blender.
# Blender's glTF exporter converts to Y-up as (x, z, -y); an engine that
# reads glTF coordinates verbatim gets the body frame: +X nose, +Y up,
# +Z starboard. Pure rotation -- no mirror.
#
# Usage (always foreground, always through blender -b):
#   blender -b --python ship_export.py -- --probe --out out/probe.glb
#   blender -b <ship.blend> --python ship_export.py -- --out out/ship.glb \
#       [--collection FI_EXPORT] [--objects "Corvette,Engine*"] \
#       [--auto-orient] [--join-per-material] [--max-tris 40000]
#
# The source .blend is NEVER saved. All work happens on in-memory copies.

import bpy
import bmesh
import fnmatch
import math
import os
import sys
from mathutils import Matrix, Vector


def parse_args():
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []
    opts = {
        "out": None, "probe": False, "collection": "FI_EXPORT",
        "objects": None, "auto_orient": False, "join_per_material": False,
        "max_tris": 0,
    }
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--probe":
            opts["probe"] = True
        elif a == "--out":
            i += 1; opts["out"] = argv[i]
        elif a == "--collection":
            i += 1; opts["collection"] = argv[i]
        elif a == "--objects":
            i += 1; opts["objects"] = argv[i]
        elif a == "--auto-orient":
            opts["auto_orient"] = True
        elif a == "--join-per-material":
            opts["join_per_material"] = True
        elif a == "--max-tris":
            i += 1; opts["max_tris"] = int(argv[i])
        else:
            fail(f"unknown arg {a}")
        i += 1
    if not opts["out"]:
        fail("--out is required")
    return opts


def fail(msg):
    print(f"ship_export: FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------- probe ----

def make_material(name, rgba, emissive=None):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value = 0.6
    if emissive:
        bsdf.inputs["Emission Color"].default_value = emissive
        bsdf.inputs["Emission Strength"].default_value = 2.0
    return m


def add_box(name, center, size, mat):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=center)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (size[0], size[1], size[2])  # primitive size=1.0 -> edge 1 m
    ob.data.materials.append(mat)
    return ob


def build_probe():
    """Asymmetric chirality probe, authored directly in convention:
    nose +X, up +Z, starboard marker on Blender -Y. 12 m long."""
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    body = make_material("probe_body", (0.55, 0.57, 0.60, 1.0))
    fin = make_material("probe_fin", (0.10, 0.25, 0.85, 1.0))
    stbd = make_material("stbd_marker", (0.90, 0.08, 0.08, 1.0),
                         emissive=(1.0, 0.1, 0.1, 1.0))
    # fuselage: x -5..+5
    add_box("fuselage", (0, 0, 0), (10, 2, 2), body)
    # nose cone pointing +X: x +5..+7
    bpy.ops.mesh.primitive_cone_add(vertices=8, radius1=1.0, radius2=0.0,
                                    depth=2.0, location=(6, 0, 0),
                                    rotation=(0, math.radians(90), 0))
    nose = bpy.context.active_object
    nose.name = "nose"
    nose.data.materials.append(body)
    # tail fin: thin plate UP (+Z) at the rear
    add_box("tail_fin", (-4, 0, 2.0), (1.6, 0.2, 2.0), fin)
    # starboard marker: block on Blender -Y (must land engine +Z)
    add_box("stbd_marker", (2, -1.4, 0), (1.0, 0.8, 1.0), stbd)
    return [bpy.data.objects[n] for n in
            ("fuselage", "nose", "tail_fin", "stbd_marker")]


# ------------------------------------------------------------- realize -----

def realize_group():
    """One-node GN group: realize instances (no-op on plain meshes)."""
    name = "FI_ExportRealize"
    if name in bpy.data.node_groups:
        return bpy.data.node_groups[name]
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT",
                            socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT",
                            socket_type="NodeSocketGeometry")
    n_in = ng.nodes.new("NodeGroupInput")
    n_real = ng.nodes.new("GeometryNodeRealizeInstances")
    n_out = ng.nodes.new("NodeGroupOutput")
    ng.links.new(n_in.outputs[0], n_real.inputs[0])
    ng.links.new(n_real.outputs[0], n_out.inputs[0])
    return ng


def evaluated_copy(ob, depsgraph, into_collection):
    """World-space evaluated mesh copy (modifiers applied, instances realized)."""
    mod = ob.modifiers.new("FI_ExportRealize", "NODES")
    mod.node_group = realize_group()
    depsgraph.update()
    ob_eval = ob.evaluated_get(depsgraph)
    me = bpy.data.meshes.new_from_object(
        ob_eval, preserve_all_data_layers=True, depsgraph=depsgraph)
    me.transform(ob_eval.matrix_world)  # bake world transform into verts
    # Blender 5.x: use_auto_smooth is gone — mark edges sharp by angle,
    # smooth-shaded faces stay smooth between sharps (same visual result)
    if hasattr(me, "set_sharp_from_angle"):
        me.set_sharp_from_angle(angle=0.56)   # ~32 deg
    new = bpy.data.objects.new(f"X_{ob.name}", me)
    into_collection.objects.link(new)
    ob.modifiers.remove(mod)
    return new


# ---------------------------------------------------------- orientation ----

def union_bbox(objects):
    lo = Vector((1e30, 1e30, 1e30))
    hi = Vector((-1e30, -1e30, -1e30))
    for ob in objects:
        for v in ob.data.vertices:
            for k in range(3):
                lo[k] = min(lo[k], v.co[k])
                hi[k] = max(hi[k], v.co[k])
    return lo, hi


def auto_orient(objects):
    """Rotate about Z so the longest horizontal extent lies on X, nose to +X
    (lighter/pointier half = nose, like normalize_obj.py), then center."""
    lo, hi = union_bbox(objects)
    ext = hi - lo
    rot = Matrix.Identity(4)
    if ext.y > ext.x:
        rot = Matrix.Rotation(math.radians(-90), 4, "Z")
        for ob in objects:
            ob.data.transform(rot)
        lo, hi = union_bbox(objects)
    cx = (lo.x + hi.x) / 2.0
    front = back = 0
    for ob in objects:
        for v in ob.data.vertices:
            if v.co.x > cx:
                front += 1
            else:
                back += 1
    if front > back:  # dense end is the stern -> flip nose to +X
        flip = Matrix.Rotation(math.radians(180), 4, "Z")
        for ob in objects:
            ob.data.transform(flip)
        lo, hi = union_bbox(objects)
    center = (lo + hi) / 2.0
    tr = Matrix.Translation(-center)
    for ob in objects:
        ob.data.transform(tr)


# ------------------------------------------------------------ join/tris ----

def triangulate(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.triangulate(bm, faces=bm.faces[:],
                          quad_method="BEAUTY", ngon_method="BEAUTY")
    bm.to_mesh(ob.data)
    bm.free()


def join_per_material(objects, into_collection):
    """Split every object by material slot, regroup by material name."""
    buckets = {}
    for ob in objects:
        me = ob.data
        mats = [m.name if m else "default" for m in me.materials] or ["default"]
        if len(mats) == 1:
            buckets.setdefault(mats[0], []).append(ob)
            continue
        # split multi-material objects with bmesh per material index
        for mi, mname in enumerate(mats):
            bm = bmesh.new()
            bm.from_mesh(me)
            drop = [f for f in bm.faces if f.material_index != mi]
            bmesh.ops.delete(bm, geom=drop, context="FACES")
            if not bm.faces:
                bm.free()
                continue
            part = bpy.data.meshes.new(f"{ob.name}_{mname}")
            bm.to_mesh(part)
            bm.free()
            part.materials.append(me.materials[mi])
            new = bpy.data.objects.new(f"X_{mname}", part)
            into_collection.objects.link(new)
            buckets.setdefault(mname, []).append(new)
        into_collection.objects.unlink(ob)
        objects = [o for o in objects if o is not ob]
    out = []
    for mname, obs in sorted(buckets.items()):
        base = obs[0]
        if len(obs) > 1:
            with bpy.context.temp_override(active_object=base,
                                           selected_editable_objects=obs):
                bpy.ops.object.join()
        base.name = mname
        out.append(base)
    return out


# ---------------------------------------------------------------- main -----

def main():
    opts = parse_args()
    out_path = os.path.abspath(opts["out"])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    if opts["probe"]:
        sources = build_probe()
    else:
        coll = bpy.data.collections.get(opts["collection"])
        if opts["objects"]:
            pats = [p.strip() for p in opts["objects"].split(",")]
            sources = [ob for ob in bpy.data.objects if ob.type == "MESH"
                       and any(fnmatch.fnmatch(ob.name, p) for p in pats)]
        elif coll:
            sources = [ob for ob in coll.all_objects if ob.type == "MESH"]
        else:
            sources = [ob for ob in bpy.data.objects if ob.type == "MESH"]
        if not sources:
            fail("no source mesh objects matched")

    exp_coll = bpy.data.collections.new("FI_STAGING")
    bpy.context.scene.collection.children.link(exp_coll)
    depsgraph = bpy.context.evaluated_depsgraph_get()
    copies = [evaluated_copy(ob, depsgraph, exp_coll) for ob in sources]

    if opts["auto_orient"]:
        auto_orient(copies)
    if opts["join_per_material"]:
        copies = join_per_material(copies, exp_coll)
    else:
        for c in copies:
            c.name = c.name[2:] if c.name.startswith("X_") else c.name
    for c in copies:
        triangulate(c)

    # ---- report ---------------------------------------------------------
    lo, hi = union_bbox(copies)
    ext = hi - lo
    total = 0
    lines = []
    lines.append(f"export: {out_path}")
    lines.append(f"bbox metres: L(x)={ext.x:.2f}  H(z->engineY)={ext.z:.2f}"
                 f"  W(y->engineZ)={ext.y:.2f}")
    warn = []
    for c in sorted(copies, key=lambda o: o.name):
        tris = len(c.data.polygons)
        total += tris
        mats = [m.name if m else "?" for m in c.data.materials]
        for m in c.data.materials:
            if m and m.use_nodes:
                bsdf = next((n for n in m.node_tree.nodes
                             if n.type == "BSDF_PRINCIPLED"), None)
                if bsdf and not bsdf.inputs["Base Color"].links:
                    warn.append(f"material '{m.name}' has no baseColor "
                                f"texture (flat colour will export)")
        lines.append(f"  part {c.name:24s} tris={tris:6d}  mats={mats}")
    lines.append(f"  TOTAL tris={total}")
    # nose heuristic: front half should be lighter (pointier) than back
    cx = (lo.x + hi.x) / 2.0
    front = sum(1 for c in copies for v in c.data.vertices if v.co.x > cx)
    back = sum(len(c.data.vertices) for c in copies) - front
    lines.append(f"  nose-at-+X heuristic: front verts={front} back={back}"
                 f" ({'OK' if front <= back else 'SUSPECT — check nose'})")
    for w in sorted(set(warn)):
        lines.append(f"  WARN: {w}")
    if opts["max_tris"] and total > opts["max_tris"]:
        lines.append(f"  FAIL: total {total} > budget {opts['max_tris']}")
    report = "\n".join(lines)
    print(report)
    with open(os.path.splitext(out_path)[0] + "_report.txt", "w") as f:
        f.write(report + "\n")
    if opts["max_tris"] and total > opts["max_tris"]:
        sys.exit(1)

    # ---- export ---------------------------------------------------------
    for ob in bpy.data.objects:
        ob.select_set(False)
    for c in copies:
        c.select_set(True)
    bpy.context.view_layer.objects.active = copies[0]
    bpy.ops.export_scene.gltf(
        filepath=out_path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_image_format="AUTO",
        export_animations=False,
        export_skins=False,
        export_morph=False,
        export_tangents=False,
    )
    print(f"ship_export: OK -> {out_path}")
    # NOTE: deliberately no bpy.ops.wm.save_mainfile() anywhere.


main()
