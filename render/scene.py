"""
LIGHTS OUT — procedural scene for the onboard background plates.

Builds a Singapore-style night street-circuit start grid seen from the
driver's eye of the car on grid slot P2, and renders it with Cycles.

Run with the `bpy` Python module (Blender as a module):
    python render/scene.py --aspect landscape --width 2400 --samples 256 --out out/landscape.exr

Two passes per camera, each written as one EXR per render pass (<out><Pass>.exr):
  --pass plate : Image (denoised, start lights dark) + Mist (depth for haze)
  --pass lamps : Combined_col1..5 — camera-visible emission of each light column,
                 rendered only in the light unit's region and never denoised
render/post.py adds the columns onto the plate and crops the five light states.
"""

from __future__ import annotations

import argparse
import math
import os
import random
import sys
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)

import bpy
import bmesh
from mathutils import Vector

# ----------------------------------------------------------------------------
# Scene constants (metres). Track centreline is x = 0, cars face +y.
# Camera = our driver's eye, standing on grid slot P2 (right-hand side).
# ----------------------------------------------------------------------------
OUR_X = 2.6
P1_X = -2.6
P1_Y = 8.0  # grid slots are staggered 8 m apart
EYE_Z = 0.86
START_LINE_Y = 23.0
GANTRY_Y = 25.0
LIGHT_Z = 5.3
TRACK_HALF = 7.4
WALL_H = 1.15

rng = random.Random(7)
LAMPS: list = []  # emissive start-light discs, filled by build_gantry


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def reset() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def link(obj: bpy.types.Object) -> bpy.types.Object:
    bpy.context.scene.collection.objects.link(obj)
    return obj


def mesh_obj(name: str, verts, faces, mat=None, smooth=False) -> bpy.types.Object:
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.validate()
    me.update()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    if mat is not None:
        me.materials.append(mat)
    return link(ob)


def box(name, center, size, mat=None, bevel=0.0, segments=2, rot=(0, 0, 0)):
    cx, cy, cz = center
    sx, sy, sz = (s / 2 for s in size)
    v = [
        (cx - sx, cy - sy, cz - sz), (cx + sx, cy - sy, cz - sz),
        (cx + sx, cy + sy, cz - sz), (cx - sx, cy + sy, cz - sz),
        (cx - sx, cy - sy, cz + sz), (cx + sx, cy - sy, cz + sz),
        (cx + sx, cy + sy, cz + sz), (cx - sx, cy + sy, cz + sz),
    ]
    f = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    ob = mesh_obj(name, v, f, mat)
    if any(rot):
        # rotate around the box centre
        for vert in ob.data.vertices:
            p = vert.co - Vector(center)
            p.rotate(__import__("mathutils").Euler(rot, "XYZ"))
            vert.co = p + Vector(center)
    if bevel > 0:
        m = ob.modifiers.new("bevel", "BEVEL")
        m.width = bevel
        m.segments = segments
        m.limit_method = "NONE"
        for p in ob.data.polygons:
            p.use_smooth = True
        try:
            ob.data.set_sharp_from_angle(angle=math.radians(40))
        except Exception:
            pass
    return ob


def superellipse(hw, hh, n, count=24, bottom_flat=0.0):
    pts = []
    for i in range(count):
        t = 2 * math.pi * i / count
        c, s = math.cos(t), math.sin(t)
        x = hw * math.copysign(abs(c) ** (2 / n), c)
        z = hh * math.copysign(abs(s) ** (2 / n), s)
        if bottom_flat and z < -hh * (1 - bottom_flat):
            z = -hh * (1 - bottom_flat)
        pts.append((x, z))
    return pts


def loft(name, sections, mat=None, count=28, cap=True, smooth=True, subsurf=1):
    """sections: list of (y, cx, cz, hw, hh, n)."""
    verts, faces = [], []
    for (y, cx, cz, hw, hh, n) in sections:
        for (x, z) in superellipse(hw, hh, n, count):
            verts.append((cx + x, y, cz + z))
    ns = len(sections)
    for s in range(ns - 1):
        for i in range(count):
            a = s * count + i
            b = s * count + (i + 1) % count
            c = (s + 1) * count + (i + 1) % count
            d = (s + 1) * count + i
            faces.append((a, b, c, d))
    if cap:
        faces.append(tuple(reversed(range(count))))
        faces.append(tuple((ns - 1) * count + i for i in range(count)))
    ob = mesh_obj(name, verts, faces, mat, smooth=smooth)
    if subsurf:
        m = ob.modifiers.new("sub", "SUBSURF")
        m.levels = subsurf
        m.render_levels = subsurf
    return ob


def tube(name, points, radius, mat=None, resolution=12, profile_scale=(1, 1), tilt=None):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = resolution // 4
    cu.use_fill_caps = True
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(points) - 1)
    for bp, p in zip(sp.bezier_points, points):
        bp.co = p
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
        if tilt is not None:
            bp.tilt = tilt
    ob = bpy.data.objects.new(name, cu)
    ob.scale = (1, 1, 1)
    if mat:
        cu.materials.append(mat)
    link(ob)
    return ob


def cylinder(name, center, radius, depth, axis="X", mat=None, verts=48, bevel=0.0):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth, location=center)
    ob = bpy.context.active_object
    ob.name = name
    if axis == "X":
        ob.rotation_euler = (0, math.radians(90), 0)
    elif axis == "Y":
        ob.rotation_euler = (math.radians(90), 0, 0)
    if mat:
        ob.data.materials.append(mat)
    for p in ob.data.polygons:
        p.use_smooth = True
    if bevel:
        m = ob.modifiers.new("bevel", "BEVEL")
        m.width = bevel
        m.segments = 3
        m.limit_method = "ANGLE"
    return ob


def set_visibility(ob, camera=True, diffuse=True, glossy=True, transmission=True, shadow=True):
    ob.visible_camera = camera
    ob.visible_diffuse = diffuse
    ob.visible_glossy = glossy
    ob.visible_transmission = transmission
    ob.visible_shadow = shadow


# ----------------------------------------------------------------------------
# Materials
# ----------------------------------------------------------------------------
def principled(name, color, rough=0.5, metal=0.0, coat=0.0, coat_rough=0.03, spec=0.5,
               emission=None, strength=0.0, aniso=0.0):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Specular IOR Level"].default_value = spec
    if coat:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = coat_rough
    if aniso:
        b.inputs["Anisotropic"].default_value = aniso
    if emission is not None:
        b.inputs["Emission Color"].default_value = (*emission, 1)
        b.inputs["Emission Strength"].default_value = strength
    return m


def node_mat(name):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    return m, nt, nt.nodes, nt.links, nt.nodes["Principled BSDF"]


def mat_asphalt():
    m, nt, n, l, b = node_mat("asphalt")
    tc = n.new("ShaderNodeTexCoord")
    # fine aggregate
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 900.0
    noise.inputs["Detail"].default_value = 2.0
    vor = n.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 420.0
    l.new(tc.outputs["Object"], noise.inputs["Vector"])
    l.new(tc.outputs["Object"], vor.inputs["Vector"])
    # large-scale patches + rubber laid down along the racing line
    big = n.new("ShaderNodeTexNoise")
    big.inputs["Scale"].default_value = 0.6
    big.inputs["Detail"].default_value = 6.0
    l.new(tc.outputs["Object"], big.inputs["Vector"])
    mapping = n.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.0, 0.04, 1.0)
    l.new(tc.outputs["Object"], mapping.inputs["Vector"])
    streak = n.new("ShaderNodeTexNoise")
    streak.inputs["Scale"].default_value = 2.2
    streak.inputs["Detail"].default_value = 4.0
    l.new(mapping.outputs["Vector"], streak.inputs["Vector"])

    ramp = n.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.035, 0.035, 0.037, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.085, 0.084, 0.082, 1)
    mix1 = n.new("ShaderNodeMath")
    mix1.operation = "MULTIPLY_ADD"
    l.new(noise.outputs["Fac"], mix1.inputs[0])
    mix1.inputs[1].default_value = 0.6
    l.new(vor.outputs["Distance"], mix1.inputs[2])
    l.new(mix1.outputs[0], ramp.inputs["Fac"])

    darken = n.new("ShaderNodeMix")
    darken.data_type = "RGBA"
    darken.blend_type = "MULTIPLY"
    srm = n.new("ShaderNodeMapRange")
    srm.inputs["From Min"].default_value = 0.45
    srm.inputs["From Max"].default_value = 0.75
    srm.inputs["To Min"].default_value = 0.0
    srm.inputs["To Max"].default_value = 0.55
    l.new(streak.outputs["Fac"], srm.inputs["Value"])
    l.new(srm.outputs["Result"], darken.inputs["Factor"])
    l.new(ramp.outputs["Color"], darken.inputs["A"])
    darken.inputs["B"].default_value = (0.35, 0.35, 0.36, 1)
    bigm = n.new("ShaderNodeMix")
    bigm.data_type = "RGBA"
    bigm.blend_type = "MULTIPLY"
    bigm.inputs["Factor"].default_value = 0.35
    l.new(darken.outputs["Result"], bigm.inputs["A"])
    l.new(big.outputs["Color"], bigm.inputs["B"])
    l.new(bigm.outputs["Result"], b.inputs["Base Color"])

    rr = n.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value = 0.62
    rr.inputs["To Max"].default_value = 0.9
    l.new(noise.outputs["Fac"], rr.inputs["Value"])
    l.new(rr.outputs["Result"], b.inputs["Roughness"])
    b.inputs["Specular IOR Level"].default_value = 0.45

    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.002
    l.new(vor.outputs["Distance"], bump.inputs["Height"])
    l.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_paint_line():
    m, nt, n, l, b = node_mat("line_paint")
    tc = n.new("ShaderNodeTexCoord")
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 60.0
    l.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = n.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.45, 0.45, 0.44, 1)
    ramp.color_ramp.elements[1].color = (0.78, 0.78, 0.76, 1)
    l.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    l.new(ramp.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.55
    return m


def mat_carbon(name="carbon", tint=(0.02, 0.02, 0.022), gloss=0.25, coat=0.6):
    m, nt, n, l, b = node_mat(name)
    tc = n.new("ShaderNodeTexCoord")
    chk = n.new("ShaderNodeTexChecker")
    chk.inputs["Scale"].default_value = 160.0
    chk.inputs["Color1"].default_value = (*tint, 1)
    chk.inputs["Color2"].default_value = tuple(c * 1.9 for c in tint) + (1,)
    l.new(tc.outputs["Object"], chk.inputs["Vector"])
    l.new(chk.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = gloss
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Coat Roughness"].default_value = 0.05
    b.inputs["Anisotropic"].default_value = 0.4
    return m


def mat_windows(name, scale=(14, 30), lit=0.55, strength=3.0, warm=True, base=(0.03, 0.035, 0.045)):
    """Building facade with a random grid of lit windows."""
    m, nt, n, l, b = node_mat(name)
    tc = n.new("ShaderNodeTexCoord")
    mapping = n.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (scale[0], scale[0], scale[1])
    l.new(tc.outputs["Object"], mapping.inputs["Vector"])
    brick = n.new("ShaderNodeTexBrick")
    brick.offset = 0.0
    brick.inputs["Mortar Size"].default_value = 0.12
    brick.inputs["Brick Width"].default_value = 1.0
    brick.inputs["Row Height"].default_value = 1.0
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Color1"].default_value = (1, 1, 1, 1)
    brick.inputs["Color2"].default_value = (0, 0, 0, 1)
    brick.inputs["Mortar"].default_value = (0, 0, 0, 1)
    l.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    # random per-window value: use white noise on snapped coords
    snap = n.new("ShaderNodeVectorMath")
    snap.operation = "SNAP"
    snap.inputs[1].default_value = (1, 1, 1)
    l.new(mapping.outputs["Vector"], snap.inputs[0])
    wn = n.new("ShaderNodeTexWhiteNoise")
    wn.noise_dimensions = "3D"
    l.new(snap.outputs["Vector"], wn.inputs["Vector"])
    gt = n.new("ShaderNodeMath")
    gt.operation = "GREATER_THAN"
    gt.inputs[1].default_value = 1 - lit
    l.new(wn.outputs["Value"], gt.inputs[0])
    mask = n.new("ShaderNodeMath")
    mask.operation = "MULTIPLY"
    l.new(gt.outputs[0], mask.inputs[0])
    l.new(brick.outputs["Fac"], mask.inputs[1])
    # window colour varies warm/cool
    cr = n.new("ShaderNodeValToRGB")
    if warm:
        cr.color_ramp.elements[0].color = (1.0, 0.72, 0.42, 1)
        cr.color_ramp.elements[1].color = (0.85, 0.9, 1.0, 1)
    else:
        cr.color_ramp.elements[0].color = (0.75, 0.85, 1.0, 1)
        cr.color_ramp.elements[1].color = (1.0, 0.95, 0.85, 1)
    l.new(wn.outputs["Color"], cr.inputs["Fac"])  # color output, first channel used
    em = n.new("ShaderNodeMath")
    em.operation = "MULTIPLY"
    em.inputs[1].default_value = strength
    l.new(mask.outputs[0], em.inputs[0])
    l.new(cr.outputs["Color"], b.inputs["Emission Color"])
    l.new(em.outputs[0], b.inputs["Emission Strength"])
    b.inputs["Base Color"].default_value = (*base, 1)
    b.inputs["Roughness"].default_value = 0.25
    b.inputs["Metallic"].default_value = 0.4
    return m


def mat_glazing(name, color, strength, mullion=(0.5, 0.5)):
    """Lit glazing behind a dark mullion grid, with soft brightness variation between bays."""
    m, nt, n, l, b = node_mat(name)
    tc = n.new("ShaderNodeTexCoord")
    mapping = n.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (mullion[0], mullion[0], mullion[1])
    l.new(tc.outputs["Object"], mapping.inputs["Vector"])
    brick = n.new("ShaderNodeTexBrick")
    brick.offset = 0.0
    brick.inputs["Mortar Size"].default_value = 0.04
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Brick Width"].default_value = 1.0
    brick.inputs["Row Height"].default_value = 1.0
    brick.inputs["Color1"].default_value = (1, 1, 1, 1)
    brick.inputs["Color2"].default_value = (0.75, 0.75, 0.75, 1)
    brick.inputs["Mortar"].default_value = (0, 0, 0, 1)
    l.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 0.08
    l.new(tc.outputs["Object"], noise.inputs["Vector"])
    mul = n.new("ShaderNodeMix")
    mul.data_type = "RGBA"
    mul.blend_type = "MULTIPLY"
    mul.inputs["Factor"].default_value = 0.7
    l.new(brick.outputs["Color"], mul.inputs["A"])
    l.new(noise.outputs["Color"], mul.inputs["B"])
    tint = n.new("ShaderNodeMix")
    tint.data_type = "RGBA"
    tint.blend_type = "MULTIPLY"
    tint.inputs["Factor"].default_value = 1.0
    l.new(mul.outputs["Result"], tint.inputs["A"])
    tint.inputs["B"].default_value = (*color, 1)
    l.new(tint.outputs["Result"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = strength
    b.inputs["Base Color"].default_value = (0.02, 0.02, 0.02, 1)
    b.inputs["Roughness"].default_value = 0.1
    return m


def mat_crowd():
    """Spectators: dense multicoloured speckle on dark terraces."""
    m, nt, n, l, b = node_mat("crowd")
    tc = n.new("ShaderNodeTexCoord")
    vor = n.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 16.0
    l.new(tc.outputs["Object"], vor.inputs["Vector"])
    hsv = n.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value = 0.4
    hsv.inputs["Value"].default_value = 0.22
    l.new(vor.outputs["Color"], hsv.inputs["Color"])
    l.new(hsv.outputs["Color"], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.85
    return m


def mat_emit(name, color, strength):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


def mat_fence():
    """Debris fence: a fine wire grid, mostly transparent."""
    m, nt, n, l, b = node_mat("fence")
    tc = n.new("ShaderNodeTexCoord")
    mapping = n.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (14, 14, 14)
    l.new(tc.outputs["Object"], mapping.inputs["Vector"])
    brick = n.new("ShaderNodeTexBrick")
    brick.offset = 0.0
    brick.inputs["Mortar Size"].default_value = 0.06
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Brick Width"].default_value = 1.0
    brick.inputs["Row Height"].default_value = 1.0
    brick.inputs["Color1"].default_value = (0, 0, 0, 1)
    brick.inputs["Color2"].default_value = (0, 0, 0, 1)
    brick.inputs["Mortar"].default_value = (1, 1, 1, 1)
    l.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    b.inputs["Base Color"].default_value = (0.08, 0.085, 0.09, 1)
    b.inputs["Metallic"].default_value = 0.5
    b.inputs["Roughness"].default_value = 0.35
    l.new(brick.outputs["Color"], b.inputs["Alpha"])
    return m


# ----------------------------------------------------------------------------
# Car
# ----------------------------------------------------------------------------
class Livery:
    def __init__(self, body, accent, halo):
        self.body = body
        self.accent = accent
        self.halo = halo


def wheel(name, center, radius, width, rubber, rim, band):
    x, y, z = center
    t = cylinder(name + "_tyre", center, radius, width, "X", rubber, verts=72)
    b = t.modifiers.new("bevel", "BEVEL")
    b.width = 0.07
    b.segments = 6
    b.limit_method = "ANGLE"
    side = 1 if x > 0 else -1
    # coloured compound band on the outer sidewall
    bpy.ops.mesh.primitive_torus_add(major_radius=radius * 0.78, minor_radius=0.008,
                                     location=(x + side * (width / 2 + 0.001), y, z),
                                     rotation=(0, math.radians(90), 0))
    ring = bpy.context.active_object
    ring.name = name + "_band"
    ring.scale = (1, 1, 0.4)
    ring.data.materials.append(band)
    # wheel cover / rim
    cylinder(name + "_rim", (x + side * (width / 2 - 0.005), y, z), radius * 0.62, 0.03, "X", rim, verts=48)
    return t


def build_car(prefix, ox, oy, liv: Livery, mats, our_car=False):
    """Car-local frame: origin on the ground under the driver's eye, +y forward."""
    paint = liv.body
    accent = liv.accent
    carbon = mats["carbon"]
    rubber = mats["rubber"]
    rim = mats["rim"]
    band = mats["band"]

    def P(x, y, z):
        return (ox + x, oy + y, z)

    objs = []
    # floor / plank
    objs.append(box(prefix + "floor", P(0, -0.2, 0.06), (1.6, 3.4, 0.03), carbon, bevel=0.01))
    # monocoque, closed forward of the cockpit opening
    if our_car:
        mono_secs = [
            (0.42, 0, 0.42, 0.36, 0.24, 3.0),
            (0.80, 0, 0.42, 0.33, 0.215, 3.0),
            (1.30, 0, 0.40, 0.28, 0.19, 2.8),
            (1.80, 0, 0.37, 0.22, 0.15, 2.6),
            (2.40, 0, 0.32, 0.15, 0.11, 2.4),
            (3.10, 0, 0.26, 0.10, 0.07, 2.4),
            (3.80, 0, 0.21, 0.065, 0.045, 2.2),
            (4.05, 0, 0.19, 0.04, 0.025, 2.0),
        ]
    else:
        mono_secs = [
            (-0.45, 0, 0.40, 0.30, 0.22, 3.0),
            (0.42, 0, 0.42, 0.36, 0.24, 3.0),
            (1.30, 0, 0.40, 0.28, 0.19, 2.8),
            (2.40, 0, 0.32, 0.15, 0.11, 2.4),
            (3.10, 0, 0.26, 0.10, 0.07, 2.4),
            (4.05, 0, 0.19, 0.04, 0.025, 2.0),
        ]
    objs.append(loft(prefix + "mono", [(oy + y, ox + cx, cz, hw, hh, n) for (y, cx, cz, hw, hh, n) in mono_secs], paint))

    # cockpit rims (our car: thin sides with padded tops), the opening is between them
    for s in (-1, 1):
        rim_secs = [
            (-0.55, s * 0.40, 0.55, 0.09, 0.05, 2.6),
            (-0.10, s * 0.41, 0.585, 0.10, 0.055, 2.6),
            (0.30, s * 0.40, 0.575, 0.09, 0.05, 2.6),
            (0.62, s * 0.34, 0.52, 0.07, 0.04, 2.4),
        ]
        objs.append(loft(prefix + f"rim{s}", [(oy + y, ox + cx, cz, hw, hh, n) for (y, cx, cz, hw, hh, n) in rim_secs], paint))
        # sidepods
        sp = [
            (-1.10, s * 0.55, 0.30, 0.10, 0.12, 2.6),
            (-0.40, s * 0.62, 0.36, 0.20, 0.20, 3.2),
            (0.20, s * 0.66, 0.37, 0.22, 0.20, 3.6),
            (0.62, s * 0.68, 0.36, 0.20, 0.17, 3.6),
            (0.70, s * 0.68, 0.36, 0.19, 0.16, 3.6),
        ]
        objs.append(loft(prefix + f"pod{s}", [(oy + y, ox + cx, cz, hw, hh, n) for (y, cx, cz, hw, hh, n) in sp], paint))
        # sidepod inlet (black)
        objs.append(box(prefix + f"inlet{s}", P(s * 0.68, 0.71, 0.38), (0.32, 0.02, 0.24), mats["black"], bevel=0.04))
    # engine cover + shark fin
    ec = [
        (0.10, 0, 0.62, 0.20, 0.24, 2.4),
        (-0.30, 0, 0.66, 0.24, 0.30, 2.6),
        (-0.80, 0, 0.60, 0.22, 0.26, 2.4),
        (-1.40, 0, 0.48, 0.14, 0.18, 2.2),
        (-1.95, 0, 0.40, 0.06, 0.10, 2.0),
    ]
    if not our_car:
        objs.append(loft(prefix + "engine", [(oy + y, ox + cx, cz, hw, hh, n) for (y, cx, cz, hw, hh, n) in ec], paint))
        objs.append(box(prefix + "fin", P(0, -1.10, 0.80), (0.012, 1.1, 0.22), paint, bevel=0.004))
        # airbox above the driver's head
        objs.append(loft(prefix + "airbox", [(oy + y, ox + cx, cz, hw, hh, n) for (y, cx, cz, hw, hh, n) in [
            (-0.12, 0, 0.98, 0.10, 0.10, 2.2), (-0.30, 0, 0.94, 0.12, 0.13, 2.4),
            (-0.70, 0, 0.82, 0.10, 0.12, 2.2)]], paint))
        objs.append(box(prefix + "airbox_in", P(0, -0.115, 0.98), (0.17, 0.01, 0.16), mats["black"], bevel=0.04))
        # helmet + HANS of the P1 driver
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.135, location=P(0, 0.02, 0.86), segments=48, ring_count=24)
        helm = bpy.context.active_object
        helm.name = prefix + "helmet"
        helm.scale = (0.95, 1.12, 1.0)
        helm.data.materials.append(mats["helmet"])
        for p in helm.data.polygons:
            p.use_smooth = True
        # headrest
        for s in (-1, 1):
            objs.append(box(prefix + f"headrest{s}", P(s * 0.22, -0.05, 0.70), (0.14, 0.40, 0.14), mats["black"], bevel=0.04))
        # rear wing: endplates, main plane, flap
        for s in (-1, 1):
            objs.append(box(prefix + f"ep{s}", P(s * 0.50, -1.95, 0.72), (0.012, 0.55, 0.52), paint, bevel=0.004))
        objs.append(box(prefix + "rw_main", P(0, -1.90, 0.86), (1.0, 0.30, 0.028), carbon, bevel=0.01, rot=(math.radians(-8), 0, 0)))
        objs.append(box(prefix + "rw_flap", P(0, -2.05, 0.97), (1.0, 0.22, 0.02), paint, bevel=0.008, rot=(math.radians(-32), 0, 0)))
        objs.append(box(prefix + "beam", P(0, -1.98, 0.42), (0.95, 0.12, 0.05), carbon, bevel=0.01))
        objs.append(box(prefix + "pylon", P(0, -1.95, 0.62), (0.03, 0.12, 0.42), carbon, bevel=0.008))
        # diffuser
        objs.append(box(prefix + "diffuser", P(0, -1.75, 0.16), (1.0, 0.55, 0.22), carbon, bevel=0.02,
                        rot=(math.radians(16), 0, 0)))
        for k in range(5):
            objs.append(box(prefix + f"dstrake{k}", P(-0.4 + k * 0.2, -1.85, 0.18), (0.008, 0.45, 0.2), carbon))
        # rain light (off) + gearbox
        objs.append(box(prefix + "rainlight", P(0, -2.0, 0.40), (0.06, 0.02, 0.06), mats["redlens"], bevel=0.005))
        objs.append(box(prefix + "gearbox", P(0, -1.40, 0.32), (0.28, 0.9, 0.24), carbon, bevel=0.03))
        # rear suspension
        for s in (-1, 1):
            for dz, dy in ((0.22, 0.0), (0.42, 0.1), (0.30, -0.15)):
                tube(prefix + f"rsus{s}{dz}", [P(s * 0.15, -1.30 + dy, dz), P(s * 0.72, -1.55, dz + 0.05)], 0.018, carbon)
    # front wing
    fw_y = 4.10
    for k, (dz, dy, w, rot) in enumerate([(0.10, 0.0, 0.30, -4), (0.15, -0.16, 0.17, -14), (0.20, -0.27, 0.12, -24), (0.245, -0.34, 0.09, -34)]):
        objs.append(box(prefix + f"fw{k}", P(0, fw_y + dy, dz), (1.95, w, 0.012), paint if k == 0 else carbon, bevel=0.004,
                        rot=(math.radians(rot), 0, 0)))
    for s in (-1, 1):
        objs.append(box(prefix + f"fwep{s}", P(s * 0.98, fw_y - 0.15, 0.17), (0.012, 0.55, 0.20), paint, bevel=0.004))
    # front suspension
    for s in (-1, 1):
        for dz, dy in ((0.22, 0.0), (0.36, 0.08), (0.30, -0.12)):
            tube(prefix + f"fsus{s}{dz}", [P(s * 0.12, 2.90 + dy, dz + 0.05), P(s * 0.70, 2.95, dz)], 0.016, carbon)
        tube(prefix + f"track{s}", [P(s * 0.10, 2.70, 0.30), P(s * 0.70, 2.80, 0.26)], 0.014, carbon)
    # wheels (18" tyres: 0.72 m diameter)
    for s in (-1, 1):
        wheel(prefix + f"fw{s}", P(s * 0.80, 2.95, 0.36), 0.36, 0.30, rubber, rim, band)
        wheel(prefix + f"rw{s}", P(s * 0.78, -1.55, 0.36), 0.36, 0.405, rubber, rim, band)
    # mirrors: rounded housings on a single faired strut rising from the sidepod shoulder
    for s_ in (-1, 1):
        mx, my, mz = s_ * 0.58, 1.0, 0.64
        objs.append(loft(prefix + f"mirror{s_}", [(oy + y, ox + cx, cz, hw, hh, n) for (y, cx, cz, hw, hh, n) in [
            (my - 0.04, mx, mz, 0.10, 0.045, 3.2), (my + 0.0, mx, mz, 0.105, 0.048, 3.2),
            (my + 0.05, mx, mz - 0.004, 0.085, 0.036, 2.6), (my + 0.075, mx, mz - 0.008, 0.04, 0.016, 2.2)]], paint))
        objs.append(box(prefix + f"mirrorglass{s_}", P(mx, my - 0.041, mz), (0.18, 0.004, 0.07), mats["mirror"], bevel=0.012))
        tube(prefix + f"mstrut{s_}", [P(mx + s_ * 0.03, my + 0.02, 0.44), P(mx + s_ * 0.01, my + 0.015, 0.54),
                                       P(mx, my + 0.01, mz - 0.03)], 0.015, paint)
    # halo: hoop + centre pillar
    halo_mat = liv.halo
    hoop = [P(-0.40, -0.42, 0.66), P(-0.37, -0.05, 0.90), P(-0.22, 0.30, 1.0),
            P(0.0, 0.40, 1.02), P(0.22, 0.30, 1.0), P(0.37, -0.05, 0.90), P(0.40, -0.42, 0.66)]
    h = tube(prefix + "halo", hoop, 0.034, halo_mat, resolution=16)
    h.data.bevel_mode = "ROUND"
    pillar = [P(0, 0.40, 1.0), P(0, 0.66, 0.85), P(0, 0.92, 0.66)]
    pil = tube(prefix + "halo_pillar", pillar, 0.03, halo_mat, resolution=16)
    pil.scale = (1, 1, 1)
    # flatten the pillar to an aero blade: separate thin vertical fairing
    objs.append(loft(prefix + "pillar_fair", [
        (oy + 0.44, ox, 0.97, 0.024, 0.045, 2.2),
        (oy + 0.66, ox, 0.845, 0.026, 0.05, 2.2),
        (oy + 0.90, ox, 0.68, 0.03, 0.06, 2.2),
    ], halo_mat))
    # halo fairing (body colour) over the hoop's front
    # roll hoop / airbox not present for our car (behind the camera)
    return objs


def build_cockpit(ox, oy, mats):
    """Interior of our car: steering wheel, gloves, dash, padding."""
    P = lambda x, y, z: (ox + x, oy + y, z)  # noqa: E731
    carbon = mats["carbon"]
    black = mats["black"]
    # dark interior tub / driver's body below the rim line
    box("tub", P(0, 0.0, 0.30), (0.62, 1.4, 0.5), mats["suede"])
    loft("dash", [(oy + y, ox + cx, cz, hw, hh, n) for (y, cx, cz, hw, hh, n) in [
        (0.44, 0, 0.52, 0.30, 0.10, 3.0), (0.62, 0, 0.55, 0.28, 0.10, 3.0)]], carbon)
    # driver's legs/knees under the dash (barely visible)
    for s in (-1, 1):
        loft(f"leg{s}", [(oy + y, ox + cx, cz, hw, hh, n) for (y, cx, cz, hw, hh, n) in [
            (-0.1, s * 0.12, 0.36, 0.08, 0.09, 2.2), (0.40, s * 0.11, 0.44, 0.075, 0.08, 2.2)]], mats["suit"])

    # steering wheel: wheel centre ~0.44 m ahead, tilted towards the driver
    wc = Vector(P(0, 0.40, 0.60))
    tilt = math.radians(-24)  # top leaning towards driver

    def W(x, y, z):
        # local wheel frame: x right, y out of the wheel face (towards driver = -y), z up
        v = Vector((x, y, z))
        v.rotate(__import__("mathutils").Euler((tilt, 0, 0), "XYZ"))
        return tuple(wc + v)

    # main body: a flat rounded slab
    body_pts = []
    outline = [(-0.135, -0.075), (-0.09, -0.10), (0.09, -0.10), (0.135, -0.075),
               (0.15, 0.03), (0.13, 0.085), (-0.13, 0.085), (-0.15, 0.03)]
    vs, fs = [], []
    for (x, z) in outline:
        vs.append(W(x, 0.018, z))
    for (x, z) in outline:
        vs.append(W(x, -0.018, z))
    k = len(outline)
    fs.append(tuple(range(k)))
    fs.append(tuple(reversed(range(k, 2 * k))))
    for i in range(k):
        j = (i + 1) % k
        fs.append((i, j, j + k, i + k))
    sw = mesh_obj("wheel_body", vs, fs, carbon)
    m = sw.modifiers.new("bevel", "BEVEL")
    m.width = 0.012
    m.segments = 4
    m.limit_method = "NONE"
    sub = sw.modifiers.new("sub", "SUBSURF")
    sub.levels = 1
    sub.render_levels = 1
    for p in sw.data.polygons:
        p.use_smooth = True
    # grips
    for s in (-1, 1):
        g = loft(f"grip{s}", [], None) if False else None  # placeholder for readability
        pts = [W(s * 0.155, -0.005, -0.075), W(s * 0.175, -0.01, -0.01), W(s * 0.168, -0.008, 0.065)]
        tube(f"grip{s}", pts, 0.026, mats["grip"], resolution=12)
    # display (emissive texture applied by the caller)
    disp = box("wheel_display", W(0, -0.0195, 0.005), (0.105, 0.002, 0.062), mats["display"],
               rot=(tilt, 0, 0))
    # uv for display
    me = disp.data
    if not me.uv_layers:
        me.uv_layers.new()
    uv = me.uv_layers.active.data
    for poly in me.polygons:
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            u = (v.x - (wc.x - 0.0525)) / 0.105
            # vertical from local z
            lv = Vector(v) - wc
            lv.rotate(__import__("mathutils").Euler((-tilt, 0, 0), "XYZ"))
            vv = (lv.z - (0.005 - 0.031)) / 0.062
            uv[li].uv = (u, vv)
    # rev LEDs (off) above the display
    for i in range(15):
        x = -0.056 + i * 0.008
        col = mats["led_g"] if i < 5 else (mats["led_r"] if i < 10 else mats["led_b"])
        box(f"led{i}", W(x, -0.0195, 0.052), (0.0045, 0.004, 0.0045), col, rot=(tilt, 0, 0))
    # buttons & rotaries
    btn_layout = [(-0.11, 0.05, "btn_r"), (-0.11, 0.015, "btn_y"), (-0.085, -0.02, "btn_w"),
                  (0.11, 0.05, "btn_b"), (0.11, 0.015, "btn_g"), (0.085, -0.02, "btn_w"),
                  (-0.075, 0.06, "btn_k"), (0.075, 0.06, "btn_k"), (-0.03, -0.06, "btn_k"), (0.03, -0.06, "btn_k")]
    for i, (x, z, mk) in enumerate(btn_layout):
        c = cylinder(f"btn{i}", W(x, -0.021, z), 0.0062, 0.008, "Y", mats[mk], verts=24, bevel=0.002)
        c.rotation_euler = (math.radians(90) + tilt, 0, 0)
    for i, (x, z) in enumerate([(-0.055, -0.075), (0.0, -0.08), (0.055, -0.075), (-0.10, -0.055), (0.10, -0.055)]):
        c = cylinder(f"rot{i}", W(x, -0.024, z), 0.0105, 0.014, "Y", mats["rotary"], verts=32, bevel=0.002)
        c.rotation_euler = (math.radians(90) + tilt, 0, 0)
    # paddles behind
    for s in (-1, 1):
        box(f"paddle{s}", W(s * 0.11, 0.03, 0.03), (0.07, 0.006, 0.05), carbon, bevel=0.004, rot=(tilt, 0, 0))
    # steering column
    tube("column", [W(0, 0.03, 0), P(0, 0.85, 0.50)], 0.022, carbon)

    # gloves on the grips: simple padded mitts with knuckle volume and forearms
    for s in (-1, 1):
        gc = Vector(W(s * 0.168, -0.035, 0.0))
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.04, location=gc, segments=32, ring_count=16)
        gl = bpy.context.active_object
        gl.name = f"glove{s}"
        gl.scale = (0.9, 0.85, 1.3)
        gl.rotation_euler = (tilt, 0, s * math.radians(-12))
        gl.data.materials.append(mats["glove"])
        for p in gl.data.polygons:
            p.use_smooth = True
        # thumb wrapping the front of the wheel
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.014, location=tuple(Vector(W(s * 0.14, -0.03, 0.03))), segments=20, ring_count=10)
        th = bpy.context.active_object
        th.scale = (1.6, 0.9, 0.9)
        th.rotation_euler = (0, 0, s * math.radians(20))
        th.data.materials.append(mats["glove"])
        for p in th.data.polygons:
            p.use_smooth = True
        # cuff + forearm going back/down out of view
        loft(f"arm{s}", [(y, x, z, hw, hh, n) for (y, x, z, hw, hh, n) in [
            (gc.y - 0.04, gc.x + s * 0.005, gc.z - 0.06, 0.035, 0.04, 2.0),
            (gc.y - 0.20, gc.x + s * 0.02, gc.z - 0.14, 0.045, 0.05, 2.0),
            (gc.y - 0.40, gc.x + s * 0.03, gc.z - 0.22, 0.05, 0.055, 2.0)]], mats["suit"])
    # cockpit padding (suede) on the inner rim
    for s in (-1, 1):
        loft(f"pad{s}", [(oy + y, ox + cx, cz, hw, hh, n) for (y, cx, cz, hw, hh, n) in [
            (-0.40, s * 0.30, 0.62, 0.03, 0.06, 2.2), (0.25, s * 0.30, 0.62, 0.03, 0.06, 2.2)]], mats["suede"])


# ----------------------------------------------------------------------------
# Environment
# ----------------------------------------------------------------------------
def build_track(mats):
    # asphalt
    mesh_obj("asphalt", [(-TRACK_HALF - 0.5, -60, 0), (TRACK_HALF + 0.5, -60, 0), (TRACK_HALF + 0.5, 420, 0),
                         (-TRACK_HALF - 0.5, 420, 0)], [(0, 1, 2, 3)], mats["asphalt"])
    # ground beyond the walls
    mesh_obj("ground", [(-400, -200, -0.02), (400, -200, -0.02), (400, 900, -0.02), (-400, 900, -0.02)], [(0, 1, 2, 3)],
             mats["ground"])
    line = mats["line"]

    def stripe(name, x0, x1, y0, y1):
        mesh_obj(name, [(x0, y0, 0.002), (x1, y0, 0.002), (x1, y1, 0.002), (x0, y1, 0.002)], [(0, 1, 2, 3)], line)

    # track edge lines
    for s in (-1, 1):
        stripe(f"edge{s}", s * (TRACK_HALF - 0.35) - 0.06, s * (TRACK_HALF - 0.35) + 0.06, -60, 420)
    # start line (thick) and grid slots (staggered), front wheels on the slot line
    stripe("startline", -TRACK_HALF + 0.35, TRACK_HALF - 0.35, START_LINE_Y - 0.2, START_LINE_Y + 0.2)
    # grid slot marks: transverse bar + short longitudinal ticks
    for k in range(-3, 3):
        y_front = 2.95 + 0.38 + k * 16.0  # just in front of our front tyres for k=0
        for side, x in ((1, OUR_X), (-1, P1_X)):
            yf = y_front + (8.0 if side == -1 else 0.0)
            stripe(f"slot{k}{side}", x - 1.05, x + 1.05, yf, yf + 0.12)
            stripe(f"slotl{k}{side}", x - 1.05, x - 0.93, yf - 1.0, yf + 0.12)
            stripe(f"slotr{k}{side}", x + 0.93, x + 1.05, yf - 1.0, yf + 0.12)
    # concrete walls with sponsor-free hoarding panels
    for s in (-1, 1):
        x = s * (TRACK_HALF + 0.25)
        box(f"wall{s}", (x, 180, WALL_H / 2), (0.5, 480, WALL_H), mats["concrete"], bevel=0.03)
        # hoarding panels on the track-facing side
        y = -40.0
        i = 0
        while y < 400:
            length = 12.0
            mk = "board_a" if (i % 3) else "board_b"
            box(f"board{s}{i}", (x - s * 0.26, y + length / 2, WALL_H * 0.52), (0.02, length - 0.05, WALL_H * 0.82), mats[mk])
            y += length
            i += 1
        # debris fence on top: posts + mesh panel + cables
        fence_h = 3.6
        mesh_obj(f"fence{s}", [(x, -40, WALL_H), (x, 400, WALL_H), (x, 400, WALL_H + fence_h), (x, -40, WALL_H + fence_h)],
                 [(0, 1, 2, 3)], mats["fence"])
        y = -40.0
        while y < 400:
            box(f"post{s}{y}", (x, y, WALL_H + fence_h / 2), (0.08, 0.08, fence_h), mats["steel"], bevel=0.01)
            box(f"postarm{s}{y}", (x - s * 0.35, y, WALL_H + fence_h - 0.05), (0.7, 0.06, 0.06), mats["steel"],
                rot=(0, s * math.radians(-25), 0))
            y += 4.0
        for zc in (WALL_H + 0.6, WALL_H + 1.7, WALL_H + 2.8):
            box(f"cable{s}{zc}", (x - s * 0.04, 180, zc), (0.015, 440, 0.015), mats["steel"])


def floodlight(i, x, y, side, mats):
    """Track lighting: lattice pole with an arm of luminaires aimed at the track."""
    h = 11.5 + rng.uniform(-0.5, 0.8)
    box(f"fl_pole{i}", (x, y, h / 2), (0.28, 0.28, h), mats["steel_dark"], bevel=0.02)
    arm_len = 3.2
    ax = x - side * arm_len / 2
    box(f"fl_arm{i}", (ax, y, h), (arm_len, 0.22, 0.22), mats["steel_dark"], bevel=0.02)
    for k in range(4):
        lx = x - side * (0.5 + k * 0.8)
        lz = h - 0.25
        box(f"fl_lum{i}_{k}", (lx, y, lz + 0.05), (0.6, 0.42, 0.18), mats["steel_dark"], bevel=0.02,
            rot=(0, side * math.radians(-28), 0))
        face = box(f"fl_face{i}_{k}", (lx - side * 0.04, y, lz - 0.035), (0.54, 0.36, 0.01), mats["flood_face"],
                   rot=(0, side * math.radians(-28), 0))
        set_visibility(face, diffuse=False, glossy=True, shadow=False, transmission=False)
    # the actual light emitters
    ld = bpy.data.lights.new(f"flood{i}", "AREA")
    ld.shape = "RECTANGLE"
    ld.size = 3.0
    ld.size_y = 0.4
    ld.energy = 4500
    ld.color = (1.0, 0.97, 0.92)
    ld.spread = math.radians(110)
    lo = bpy.data.objects.new(f"flood{i}", ld)
    lo.location = (x - side * 1.8, y, h - 0.4)
    lo.rotation_euler = (0, side * math.radians(-30), 0)
    link(lo)


def build_lighting(mats):
    i = 0
    for s in (-1, 1):
        y = -24.0 + (9 if s > 0 else 0)
        while y < 330:
            floodlight(i, s * (TRACK_HALF + 1.6), y, s, mats)
            i += 1
            y += 18.0


def build_gantry(mats):
    """Start-light gantry spanning the track at the start line with the main light unit."""
    steel = mats["steel_dark"]
    span_x = TRACK_HALF + 1.2
    top = LIGHT_Z + 1.3
    for s in (-1, 1):
        box(f"g_leg{s}", (s * span_x, GANTRY_Y, top / 2), (0.45, 0.45, top), steel, bevel=0.03)
    # truss: two chords + diagonals
    for dz in (0.0, 0.7):
        for dy in (-0.25, 0.25):
            box(f"g_chord{dz}{dy}", (0, GANTRY_Y + dy, top + dz - 0.35), (2 * span_x, 0.07, 0.07), steel)
    nx = 26
    for k in range(nx):
        x0 = -span_x + k * (2 * span_x / nx)
        x1 = x0 + 2 * span_x / nx
        for dy in (-0.25, 0.25):
            tube(f"g_diag{k}{dy}", [(x0, GANTRY_Y + dy, top - 0.35), (x1, GANTRY_Y + dy, top + 0.35)], 0.02, steel)
    # light unit: five pods, each with 4 lamps (2x2); the lower 2 rows are the red start lights
    # offset left of the track centre so that, from P2, no column hides behind the halo pillar
    unit_x = -2.1
    pod_w, pod_h = 0.62, 1.8
    gap = 0.2
    total = 5 * pod_w + 4 * gap
    box("g_unit_back", (unit_x, GANTRY_Y + 0.02, LIGHT_Z + 0.25), (total + 0.3, 0.25, pod_h + 0.6), mats["housing"], bevel=0.03)
    box("g_hanger", (unit_x, GANTRY_Y, top - 0.35), (0.3, 0.2, 0.5), steel)
    lamp_r = 0.17
    for c in range(5):
        cx = unit_x - total / 2 + pod_w / 2 + c * (pod_w + gap)
        box(f"pod{c}", (cx, GANTRY_Y - 0.12, LIGHT_Z), (pod_w, 0.12, pod_h), mats["housing"], bevel=0.035)
        for r in range(4):
            lz = LIGHT_Z + 0.6 - r * 0.4
            # visor above each lamp
            box(f"visor{c}{r}", (cx, GANTRY_Y - 0.26, lz + lamp_r + 0.012), (0.42, 0.22, 0.016), mats["housing"],
                rot=(math.radians(8), 0, 0))
            lens_mat = mats["lens_red"] if r >= 2 else mats["lens_dark"]
            lens = cylinder(f"lens{c}{r}", (cx, GANTRY_Y - 0.185, lz), lamp_r, 0.02, "Y", lens_mat, verts=40, bevel=0.004)
            if r >= 2:
                # emissive LED disc — its own light group per column, visible to the camera only
                em = cylinder(f"lamp{c}{r}", (cx, GANTRY_Y - 0.197, lz), lamp_r * 0.93, 0.004, "Y", mats["lamp_on"], verts=40)
                set_visibility(em, diffuse=False, glossy=False, transmission=False, shadow=False)
                em.lightgroup = f"col{c + 1}"
                LAMPS.append(em)
    # small repeater panel on the right gantry leg (lower, closer to the cars)
    return total


def build_paddock(mats):
    face = -TRACK_HALF - 14.0
    # pit building: garages at ground level, two floors of hospitality glazing, deep roof canopy
    box("pit_building", (face - 8, 120, 7.0), (16, 320, 14), mats["pit_wall"])
    y = -40.0
    while y < 280:
        box(f"garage{y}", (face + 0.01, y + 2.7, 2.1), (0.05, 5.0, 3.6), mats["garage"])
        y += 6.0
    for k, zc in enumerate((5.6, 9.2)):
        box(f"glazing{k}", (face + 0.01, 120, zc), (0.05, 318, 2.6), mats["glazing"])
        box(f"slab{k}", (face + 0.6, 120, zc - 1.5), (1.2, 320, 0.25), mats["concrete"])
    box("pit_roof", (face - 6, 120, 14.2), (20, 322, 0.7), mats["steel_dark"], bevel=0.05)
    # pit lane floor
    mesh_obj("pitlane", [(face, -60, 0.005), (-TRACK_HALF - 0.5, -60, 0.005), (-TRACK_HALF - 0.5, 420, 0.005), (face, 420, 0.005)],
             [(0, 1, 2, 3)], mats["asphalt"])
    # grandstand on the right: stepped terraces with spectators, roof with light strips
    for r in range(14):
        box(f"stand{r}", (TRACK_HALF + 12 + r * 0.9, 120, 1.8 + r * 0.5), (0.9, 220, 0.5), mats["crowd"])
    box("stand_roof", (TRACK_HALF + 19, 120, 12.5), (16, 222, 0.4), mats["steel_dark"])
    for k in range(4):
        for j in range(24):
            box(f"stand_lamp{k}_{j}", (TRACK_HALF + 13 + k * 3.5, 10 + j * 9.0, 12.25), (0.35, 0.35, 0.04), mats["stand_lamp"])


def build_city(mats):
    # distant skyline beyond the end of the straight and to both sides
    towers = []
    for i in range(70):
        side = rng.choice([-1, 1])
        x = side * rng.uniform(40, 260)
        y = rng.uniform(260, 820)
        if abs(x) < 60 and y < 380:
            continue
        w = rng.uniform(18, 46)
        d = rng.uniform(18, 46)
        h = rng.uniform(30, 120) * (1.0 + (y - 260) / 700)
        if rng.random() < 0.18:
            h *= 1.8
        towers.append((x, y, w, d, h))
    # a cluster ahead-left and ahead-right (where the straight leads into the city)
    for i in range(18):
        x = rng.uniform(-160, 160)
        y = rng.uniform(450, 900)
        towers.append((x, y, rng.uniform(25, 50), rng.uniform(25, 50), rng.uniform(80, 240)))
    for i, (x, y, w, d, h) in enumerate(towers):
        mk = rng.choice(["win_a", "win_b", "win_c"])
        box(f"tower{i}", (x, y, h / 2), (w, d, h), mats[mk])
        if rng.random() < 0.35:
            # aircraft warning light
            bpy.ops.mesh.primitive_uv_sphere_add(radius=0.6, location=(x, y, h + 0.6))
            ob = bpy.context.active_object
            ob.data.materials.append(mats["warn_red"])
    # observation wheel (Singapore-style), far right
    cx, cy, r = 150.0, 520.0, 75.0
    bpy.ops.mesh.primitive_torus_add(major_radius=r, minor_radius=0.9, location=(cx, cy, r + 15),
                                     rotation=(math.radians(90), 0, math.radians(-35)), major_segments=128)
    ob = bpy.context.active_object
    ob.data.materials.append(mats["wheel_lights"])
    bpy.ops.mesh.primitive_torus_add(major_radius=r - 3, minor_radius=0.35, location=(cx, cy, r + 15),
                                     rotation=(math.radians(90), 0, math.radians(-35)), major_segments=128)
    bpy.context.active_object.data.materials.append(mats["steel_dark"])
    for k in range(28):
        a = 2 * math.pi * k / 28
        ex = math.cos(a) * r
        ez = math.sin(a) * r
        d = Vector((math.cos(math.radians(-35)), math.sin(math.radians(-35)), 0))
        p1 = Vector((cx, cy, r + 15)) + d * ex + Vector((0, 0, ez))
        tube(f"spoke{k}", [(cx, cy, r + 15), tuple(p1)], 0.2, mats["steel_dark"])
        bpy.ops.mesh.primitive_cube_add(size=3.2, location=tuple(p1))
        bpy.context.active_object.data.materials.append(mats["capsule"])
    for s in (-1, 1):
        tube(f"wheel_leg{s}", [(cx + s * 18, cy, 0), (cx, cy, r + 15)], 1.2, mats["steel_dark"])


def build_world():
    w = bpy.data.worlds.new("night")
    bpy.context.scene.world = w
    try:
        w.use_nodes = True
    except Exception:
        pass
    nt = w.node_tree
    bg = nt.nodes["Background"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Generated"], sep.inputs[0])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    # glow of the city near the horizon, deep blue-black above
    e = ramp.color_ramp.elements
    e[0].position = 0.0
    e[0].color = (0.09, 0.06, 0.045, 1)
    e[1].position = 0.22
    e[1].color = (0.008, 0.011, 0.022, 1)
    e.new(0.05).color = (0.05, 0.04, 0.045, 1)
    nt.links.new(sep.outputs["Z"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    w.mist_settings.start = 6.0
    w.mist_settings.depth = 600.0
    w.mist_settings.falloff = "QUADRATIC"
    w.lightgroup = "env"


def make_display_texture(path):
    """Steering wheel display: dark telemetry screen as seen on the grid (gear 1, neutral data)."""
    from PIL import Image, ImageDraw, ImageFont

    W_, H_ = 512, 300
    im = Image.new("RGB", (W_, H_), (4, 6, 9))
    d = ImageDraw.Draw(im)
    fb = ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Bold.otf", 170)
    fs = ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Bold.otf", 30)
    fx = ImageFont.truetype("/usr/share/fonts/opentype/inter/Inter-Bold.otf", 22)
    d.rectangle([0, 0, W_ - 1, 40], fill=(10, 14, 20))
    d.text((W_ / 2, 150), "1", font=fb, fill=(235, 235, 235), anchor="mm")
    for i, (lbl, val, col) in enumerate([("BBAL", "56.0", (120, 200, 255)), ("DIFF", "6", (230, 230, 230)),
                                          ("SOC", "98%", (110, 230, 140)), ("TYRE", "88°", (255, 190, 90))]):
        x = 18 if i < 2 else W_ - 18
        y = 80 + (i % 2) * 95
        a = "la" if i < 2 else "ra"
        d.text((x, y), lbl, font=fx, fill=(120, 130, 140), anchor=a)
        d.text((x, y + 28), val, font=fs, fill=col, anchor=a)
    d.text((W_ / 2, 22), "LAP 0   START", font=fx, fill=(170, 175, 180), anchor="mm")
    im.save(path)


def materials(tex_dir):
    M = {}
    M["asphalt"] = mat_asphalt()
    M["line"] = mat_paint_line()
    M["ground"] = principled("ground", (0.02, 0.02, 0.02), 0.9)
    M["concrete"] = principled("concrete", (0.2, 0.2, 0.195), 0.85)
    M["board_a"] = principled("board_a", (0.02, 0.05, 0.16), 0.35, coat=0.3)
    M["board_b"] = principled("board_b", (0.55, 0.55, 0.56), 0.4, coat=0.3)
    M["fence"] = mat_fence()
    M["steel"] = principled("steel", (0.45, 0.46, 0.47), 0.35, metal=1.0)
    M["steel_dark"] = principled("steel_dark", (0.08, 0.085, 0.09), 0.45, metal=0.8)
    M["housing"] = principled("housing", (0.022, 0.022, 0.024), 0.5)
    M["lens_dark"] = principled("lens_dark", (0.01, 0.01, 0.012), 0.08, spec=0.8)
    M["lens_red"] = principled("lens_red", (0.03, 0.004, 0.004), 0.08, spec=0.8)
    M["lamp_on"] = mat_emit("lamp_on", (1.0, 0.035, 0.012), 140.0)
    M["flood_face"] = mat_emit("flood_face", (1.0, 0.97, 0.93), 900.0)
    M["strip_white"] = mat_emit("strip_white", (1.0, 0.96, 0.9), 6.0)
    M["stand_lamp"] = mat_emit("stand_lamp", (1.0, 0.96, 0.9), 60.0)
    M["pit_wall"] = principled("pit_wall", (0.05, 0.055, 0.06), 0.4, metal=0.3)
    M["garage"] = mat_glazing("garage", (1.0, 0.98, 0.95), 3.5, mullion=(0.5, 0.5))
    M["glazing"] = mat_glazing("glazing", (1.0, 0.82, 0.6), 1.3, mullion=(0.6, 0.3))
    M["win_a"] = mat_windows("win_a", scale=(0.33, 0.28), lit=0.35, strength=1.6)
    M["win_b"] = mat_windows("win_b", scale=(0.25, 0.30), lit=0.25, strength=2.0, warm=False)
    M["win_c"] = mat_windows("win_c", scale=(0.5, 0.32), lit=0.45, strength=1.2)
    M["crowd"] = mat_crowd()
    M["warn_red"] = mat_emit("warn_red", (1.0, 0.05, 0.02), 60.0)
    M["wheel_lights"] = mat_emit("wheel_lights", (0.85, 0.9, 1.0), 30.0)
    M["capsule"] = mat_emit("capsule", (1.0, 0.92, 0.8), 6.0)

    M["carbon"] = mat_carbon()
    M["black"] = principled("black", (0.006, 0.006, 0.006), 0.6)
    M["suede"] = principled("suede", (0.01, 0.01, 0.011), 0.95, spec=0.2)
    M["suit"] = principled("suit", (0.03, 0.035, 0.06), 0.75, spec=0.3)
    M["glove"] = principled("glove", (0.025, 0.027, 0.032), 0.55, spec=0.4)
    M["grip"] = principled("grip", (0.03, 0.03, 0.03), 0.7)
    M["rubber"] = principled("rubber", (0.022, 0.022, 0.022), 0.72, spec=0.35)
    M["rim"] = principled("rim", (0.03, 0.03, 0.032), 0.35, metal=0.6)
    M["band"] = principled("band", (0.55, 0.02, 0.02), 0.6)
    M["mirror"] = principled("mirror", (0.9, 0.9, 0.9), 0.02, metal=1.0)
    M["redlens"] = principled("redlens", (0.25, 0.0, 0.0), 0.1)
    M["helmet"] = principled("helmet", (0.75, 0.75, 0.78), 0.15, coat=1.0)
    for name, col in [("btn_r", (0.6, 0.02, 0.02)), ("btn_y", (0.7, 0.5, 0.02)), ("btn_w", (0.7, 0.7, 0.7)),
                      ("btn_b", (0.02, 0.15, 0.6)), ("btn_g", (0.02, 0.4, 0.1)), ("btn_k", (0.03, 0.03, 0.03))]:
        M[name] = principled(name, tuple(c * 0.6 for c in col), 0.4, coat=0.3)
    M["rotary"] = principled("rotary", (0.25, 0.25, 0.27), 0.3, metal=1.0)
    M["led_g"] = principled("led_g", (0.0, 0.05, 0.01), 0.1, spec=0.8)
    M["led_r"] = principled("led_r", (0.06, 0.0, 0.0), 0.1, spec=0.8)
    M["led_b"] = principled("led_b", (0.0, 0.01, 0.06), 0.1, spec=0.8)

    disp_path = f"{tex_dir}/display.png"
    make_display_texture(disp_path)
    m, nt, n, l, b = node_mat("display")
    img = n.new("ShaderNodeTexImage")
    img.image = bpy.data.images.load(disp_path)
    l.new(img.outputs["Color"], b.inputs["Emission Color"])
    b.inputs["Emission Strength"].default_value = 1.6
    b.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1)
    b.inputs["Roughness"].default_value = 0.05
    M["display"] = m

    # liveries — fictional teams, no real sponsor marks
    M["our_paint"] = principled("our_paint", (0.012, 0.014, 0.018), 0.32, metal=0.25, coat=1.0, coat_rough=0.03)
    M["our_halo"] = mat_carbon("our_halo", tint=(0.012, 0.012, 0.014), gloss=0.35, coat=0.8)
    M["p1_paint"] = principled("p1_paint", (0.30, 0.31, 0.33), 0.28, metal=0.8, coat=1.0, coat_rough=0.04)
    M["p1_halo"] = principled("p1_halo", (0.02, 0.02, 0.022), 0.3, coat=0.8)
    return M


def setup_camera(aspect):
    cam_d = bpy.data.cameras.new("onboard")
    cam_d.sensor_width = 36.0
    cam_d.clip_start = 0.05
    cam_d.clip_end = 2000.0
    if aspect == "landscape":
        cam_d.sensor_fit = "HORIZONTAL"
        cam_d.lens = 16.0
        pitch = -4.5
    else:
        cam_d.sensor_fit = "VERTICAL"
        cam_d.sensor_height = 24.0
        cam_d.lens = 13.5
        pitch = -1.0
    cam = bpy.data.objects.new("onboard", cam_d)
    cam.location = (OUR_X, -0.08, EYE_Z)
    cam.rotation_euler = (math.radians(90 + pitch), 0, 0)
    link(cam)
    bpy.context.scene.camera = cam
    return cam


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    ap = argparse.ArgumentParser()
    ap.add_argument("--aspect", default="landscape", choices=["landscape", "portrait"])
    ap.add_argument("--width", type=int, default=960)
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--out", default="out/test.exr")
    ap.add_argument("--tex", default="out")
    ap.add_argument("--blend", default="")
    ap.add_argument("--pass", dest="mode", default="plate", choices=["plate", "lamps"],
                    help="plate: full denoised frame with the start lights dark; "
                         "lamps: only the light unit region, emission per column, no denoising")
    a = ap.parse_args(argv)

    reset()
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = a.samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    sc.cycles.max_bounces = 6
    sc.cycles.glossy_bounces = 3
    sc.cycles.transparent_max_bounces = 8
    sc.cycles.sample_clamp_indirect = 8.0
    sc.cycles.light_sampling_threshold = 0.01
    sc.cycles.use_light_tree = True
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.look = "None"
    if a.aspect == "landscape":
        sc.render.resolution_x = a.width
        sc.render.resolution_y = round(a.width * 9 / 16)
    else:
        sc.render.resolution_x = a.width
        sc.render.resolution_y = round(a.width * 19.5 / 9)
    sc.render.resolution_percentage = 100

    vl = sc.view_layers[0]
    vl.use_pass_mist = True
    for name in ["env", "col1", "col2", "col3", "col4", "col5"]:
        vl.lightgroups.add(name=name)

    mats = materials(a.tex)
    build_world()
    build_track(mats)
    build_lighting(mats)
    build_gantry(mats)
    build_paddock(mats)
    build_city(mats)
    build_car("our_", OUR_X, 0.0, Livery(mats["our_paint"], mats["carbon"], mats["our_halo"]), mats, our_car=True)
    build_cockpit(OUR_X, 0.0, mats)
    build_car("p1_", P1_X, P1_Y, Livery(mats["p1_paint"], mats["carbon"], mats["p1_halo"]), mats, our_car=False)
    setup_camera(a.aspect)
    fill = bpy.data.lights.new("cockpit_fill", "AREA")
    fill.shape = "DISK"
    fill.size = 2.5
    fill.energy = 40
    fill.color = (1.0, 0.97, 0.93)
    fo_ = bpy.data.objects.new("cockpit_fill", fill)
    fo_.location = (OUR_X, -1.6, 2.6)
    fo_.rotation_euler = (math.radians(38), 0, 0)
    link(fo_)

    if a.mode == "plate":
        # Lamps are rendered separately so the denoiser can't smear their emission into the plate.
        for ob in LAMPS:
            ob.hide_render = True
        passes = ["Image", "Mist"]
    else:
        # Camera-only emitters: the column passes are pure primary-ray emission (anti-aliased only).
        sc.cycles.use_denoising = False
        sc.cycles.use_adaptive_sampling = False
        sc.cycles.samples = 64
        from bpy_extras.object_utils import world_to_camera_view
        bpy.context.view_layer.update()
        pts = []
        for ob in LAMPS:
            for c in ob.bound_box:
                pts.append(world_to_camera_view(sc, sc.camera, ob.matrix_world @ Vector(c)))
        mx = 0.03
        sc.render.use_border = True
        sc.render.use_crop_to_border = False
        sc.render.border_min_x = max(min(p.x for p in pts) - mx, 0)
        sc.render.border_max_x = min(max(p.x for p in pts) + mx, 1)
        sc.render.border_min_y = max(min(p.y for p in pts) - mx, 0)
        sc.render.border_max_y = min(max(p.y for p in pts) + mx, 1)
        passes = [f"Combined_col{k}" for k in range(1, 6)]

    # Blender 5's still-image writer drops extra passes; route them through a File Output node.
    ng = bpy.data.node_groups.new("comp", "CompositorNodeTree")
    sc.compositing_node_group = ng
    rl = ng.nodes.new("CompositorNodeRLayers")
    fo = ng.nodes.new("CompositorNodeOutputFile")
    fo.format.media_type = "IMAGE"
    fo.format.file_format = "OPEN_EXR"
    fo.format.color_depth = "32"
    fo.format.exr_codec = "ZIP"
    fo.directory = os.path.dirname(os.path.abspath(a.out)) + "/"
    fo.file_name = os.path.basename(a.out)
    for pass_name in passes:
        fo.file_output_items.new("FLOAT" if pass_name == "Mist" else "RGBA", pass_name)
        ng.links.new(rl.outputs[pass_name], fo.inputs[pass_name])
    sc.render.use_compositing = True
    sc.render.compositor_device = "CPU"
    sc.render.use_sequencer = False
    if a.blend:
        bpy.ops.wm.save_as_mainfile(filepath=a.blend)
    bpy.ops.render.render(write_still=False)
    print("WROTE", a.out)


if __name__ == "__main__":
    main()
