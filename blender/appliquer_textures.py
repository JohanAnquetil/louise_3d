import bpy
import json
import os
import re

ROOT = os.getcwd()
WORLD = os.path.join(ROOT, "godot/zones/world.json")
TEXTURES = os.path.join(ROOT, "godot/materiaux")

with open(WORLD, encoding="utf-8") as f:
    world = json.load(f)

configs = {m["name"]: m for m in world["materials"]}

count = 0
missing = set()

for mat in bpy.data.materials:
    # Enlever les suffixes Blender : .001, .002...
    name = re.sub(r"\.\d{3}$", "", mat.name)

    if name not in configs:
        continue

    cfg = configs[name]
    color = cfg.get("color", [1, 1, 1])
    texture = cfg.get("albedo")

    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    bsdf = nodes.get("Principled BSDF")

    if bsdf is None:
        continue

    base = bsdf.inputs["Base Color"]

    for link in list(base.links):
        links.remove(link)

    base.default_value = (*color[:3], 1.0)
    mat.diffuse_color = (*color[:3], 1.0)
    mat.use_backface_culling = not cfg.get("double_sided", False)

    if texture:
        path = os.path.join(TEXTURES, texture)

        if not os.path.exists(path):
            missing.add(texture)
            continue

        image = bpy.data.images.load(path, check_existing=True)

        tex = nodes.new("ShaderNodeTexImage")
        tex.image = image

        uv_scale = cfg.get("uv_scale", 1.0)

        if uv_scale != 1.0:
            uv = nodes.new("ShaderNodeTexCoord")
            mapping = nodes.new("ShaderNodeMapping")
            mapping.inputs["Scale"].default_value = (
                uv_scale, uv_scale, 1.0
            )
            links.new(uv.outputs["UV"], mapping.inputs["Vector"])
            links.new(mapping.outputs["Vector"], tex.inputs["Vector"])

        links.new(tex.outputs["Color"], base)

    count += 1

print(f"Matériaux configurés : {count}")

if missing:
    print("Textures introuvables :", sorted(missing))

bpy.ops.wm.save_as_mainfile(
    filepath=os.path.join(ROOT, "montmartre_texture.blend")
)
