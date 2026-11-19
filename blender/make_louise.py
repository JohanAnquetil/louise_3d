"""Louise Michel en low-poly stylisé (statique, sans squelette) -> godot/personnages/louise_michel.glb

    blender -b -P make_louise.py -- --out ../godot/personnages/louise_michel.glb --preview ../captures/louise_michel.png
    # ou : python make_louise.py ...   (module pip "bpy")

Taille 1,62 m, pieds à l'origine, regard vers -Y dans Blender (= +Z dans Godot).
Deux objets : "louise" (le personnage) et "drapeau" (hampe + drapeau rouge, supprimable).
Palette du GDD : noir, rouge, sépia.
"""
import bpy, sys, os, math, argparse
import numpy as np
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
COL = {"robe": (0.09, 0.09, 0.11), "robe_clair": (0.16, 0.15, 0.17), "peau": (0.86, 0.68, 0.56), "cheveux": (0.20, 0.13, 0.09),
       "rouge": (0.70, 0.10, 0.10), "blanc": (0.90, 0.87, 0.80), "noir": (0.04, 0.04, 0.05), "bois": (0.36, 0.25, 0.16),
       "levres": (0.62, 0.36, 0.32)}
DOUBLE = {"rouge"}

class MB:
    def __init__(self): self.v, self.f, self.m, self.mats = [], [], [], []
    def face(self, pts, mat):
        n = len(self.v); self.v.extend([tuple(p) for p in pts]); self.f.append(tuple(range(n, n + len(pts))))
        if mat not in self.mats: self.mats.append(mat)
        self.m.append(self.mats.index(mat))

def ring(c, rx, ry, n=8, rot=0.0, ax=(1, 0, 0), ay=(0, 1, 0)):
    c, ax, ay = np.array(c, float), np.array(ax, float), np.array(ay, float)
    return [c + ax * rx * math.cos(rot + 2 * math.pi * i / n) + ay * ry * math.sin(rot + 2 * math.pi * i / n) for i in range(n)]

def skin(mb, rings, mat, cap_start=False, cap_end=False):
    for a, b in zip(rings[:-1], rings[1:]):
        n = len(a)
        for i in range(n):
            j = (i + 1) % n
            mb.face([a[i], a[j], b[j], b[i]], mat)
    if cap_start: mb.face(rings[0][::-1], mat)
    if cap_end: mb.face(rings[-1], mat)

def lathe(mb, prof, mat, n=8, cx=0.0, cy=0.0, caps=(False, False)):
    """prof : liste (z, rx, ry) du bas vers le haut."""
    skin(mb, [ring((cx, cy, z), rx, ry, n, math.pi / n) for z, rx, ry in prof], mat, *caps)

def tube(mb, pts, radii, mat, n=6, caps=(True, True)):
    pts = [np.array(p, float) for p in pts]; rings = []
    for i, p in enumerate(pts):
        t = pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)]; t /= np.linalg.norm(t)
        up = np.array((0, 1, 0.0)) if abs(t[1]) < 0.9 else np.array((1, 0, 0.0))
        ax = np.cross(up, t); ax /= np.linalg.norm(ax); ay = np.cross(t, ax)
        rings.append(ring(p, radii[i], radii[i], n, 0.0, ax, ay))
    skin(mb, rings, mat, *caps)

def ellipsoid(mb, c, rx, ry, rz, mat, n=8, m=6):
    prof = []
    for k in range(m + 1):
        a = -math.pi / 2 + math.pi * k / m
        prof.append((c[2] + rz * math.sin(a), max(1e-4, rx * math.cos(a)), max(1e-4, ry * math.cos(a))))
    lathe(mb, prof, mat, n, c[0], c[1])

def box(mb, c, sx, sy, sz, mat):
    x, y, z = c
    P = lambda a, b, d: (x + a * sx / 2, y + b * sy / 2, z + d * sz / 2)
    for q in ([P(-1, -1, -1), P(1, -1, -1), P(1, -1, 1), P(-1, -1, 1)], [P(1, 1, -1), P(-1, 1, -1), P(-1, 1, 1), P(1, 1, 1)],
              [P(-1, 1, -1), P(-1, -1, -1), P(-1, -1, 1), P(-1, 1, 1)], [P(1, -1, -1), P(1, 1, -1), P(1, 1, 1), P(1, -1, 1)],
              [P(-1, -1, 1), P(1, -1, 1), P(1, 1, 1), P(-1, 1, 1)], [P(-1, 1, -1), P(1, 1, -1), P(1, -1, -1), P(-1, -1, -1)]):
        mb.face(q, mat)

def build():
    b, f = MB(), MB()
    # robe : jupe longue évasée, taille marquée, corsage boutonné
    lathe(b, [(0.0, 0.36, 0.33), (0.06, 0.37, 0.34), (0.50, 0.29, 0.26), (0.86, 0.19, 0.15), (0.97, 0.125, 0.10)], "robe", 10, caps=(True, False))
    lathe(b, [(0.97, 0.125, 0.10), (1.00, 0.13, 0.105), (1.16, 0.165, 0.118), (1.30, 0.175, 0.10), (1.365, 0.075, 0.07)], "robe", 10)
    lathe(b, [(0.0, 0.372, 0.342), (0.05, 0.372, 0.342)], "robe_clair", 10)                     # ourlet
    lathe(b, [(0.955, 0.132, 0.107), (0.99, 0.134, 0.109)], "noir", 10)                         # ceinture
    for k in range(5): box(b, (0, -0.108 - 0.004 * k, 1.03 + 0.06 * k), 0.022, 0.012, 0.022, "robe_clair")   # boutons
    # col blanc, écharpe rouge nouée, pan qui tombe
    lathe(b, [(1.355, 0.08, 0.075), (1.385, 0.062, 0.06)], "blanc", 10)
    lathe(b, [(1.315, 0.115, 0.095), (1.345, 0.118, 0.098), (1.37, 0.085, 0.078)], "rouge", 10)
    b.face([(-0.035, -0.10, 1.34), (0.03, -0.102, 1.34), (0.05, -0.125, 1.10), (-0.02, -0.123, 1.08)], "rouge")
    b.face([(0.0, -0.103, 1.34), (0.055, -0.10, 1.335), (0.10, -0.118, 1.16), (0.05, -0.12, 1.15)], "rouge")
    # cou, tête, visage
    lathe(b, [(1.37, 0.045, 0.045), (1.45, 0.043, 0.045)], "peau", 8)
    H = (0.0, -0.005, 1.535)
    ellipsoid(b, H, 0.082, 0.095, 0.112, "peau", 10, 6)
    b.face([(-0.012, -0.098, 1.545), (0.012, -0.098, 1.545), (0.0, -0.122, 1.515)], "peau")       # nez
    b.face([(-0.012, -0.098, 1.545), (0.0, -0.122, 1.515), (-0.014, -0.096, 1.505)], "peau")
    b.face([(0.0, -0.122, 1.515), (0.012, -0.098, 1.545), (0.014, -0.096, 1.505)], "peau")
    for s in (-1, 1):
        box(b, (s * 0.034, -0.090, 1.552), 0.022, 0.012, 0.012, "noir")                           # yeux
        box(b, (s * 0.035, -0.090, 1.572), 0.034, 0.010, 0.007, "cheveux")                        # sourcils
    box(b, (0.0, -0.090, 1.482), 0.034, 0.010, 0.008, "levres")
    # cheveux : raie au milieu, tirés en arrière, chignon bas
    for s in (-1, 1):
        ellipsoid(b, (s * 0.022, 0.022, 1.565), 0.074, 0.098, 0.100, "cheveux", 8, 5)
    ellipsoid(b, (0.0, 0.035, 1.52), 0.080, 0.085, 0.095, "cheveux", 8, 5)
    ellipsoid(b, (0.0, 0.118, 1.50), 0.048, 0.045, 0.048, "cheveux", 8, 4)
    # bras gauche le long du corps, tenant un livre (l'institutrice)
    tube(b, [(-0.185, 0.0, 1.30), (-0.225, -0.01, 1.08), (-0.215, -0.07, 0.87)], [0.052, 0.045, 0.036], "robe")
    box(b, (-0.213, -0.085, 0.835), 0.05, 0.06, 0.07, "peau")
    box(b, (-0.245, -0.085, 0.80), 0.035, 0.15, 0.20, "bois"); box(b, (-0.2455, -0.085, 0.80), 0.027, 0.154, 0.185, "blanc")
    # bras droit levé, main sur la hampe
    hand = np.array((0.30, -0.16, 1.30))
    tube(b, [(0.185, 0.0, 1.30), (0.27, -0.03, 1.12), tuple(hand - (0.01, -0.02, 0.03))], [0.052, 0.045, 0.036], "robe")
    box(b, tuple(hand), 0.055, 0.06, 0.07, "peau")
    # drapeau rouge : hampe + étoffe ondulée (double face)
    px, py = hand[0] + 0.005, hand[1] - 0.005
    tube(f, [(px, py, 0.0), (px, py, 2.55)], [0.016, 0.014], "bois", 6)
    ellipsoid(f, (px, py, 2.57), 0.03, 0.03, 0.04, "bois", 6, 4)
    nseg, L, Ht = 6, 1.05, 0.72
    top = lambda k: (px + L * k / nseg, py + 0.07 * math.sin(k * 1.4), 2.50 - 0.05 * (k / nseg) ** 2 * 3)
    bot = lambda k: (px + L * k / nseg * 0.96, py + 0.09 * math.sin(k * 1.4 + 0.6), 2.50 - Ht - 0.10 * (k / nseg))
    for k in range(nseg):
        f.face([bot(k), bot(k + 1), top(k + 1), top(k)], "rouge")
    return b, f

def to_object(name, mb, mats):
    me = bpy.data.meshes.new(name); me.from_pydata(mb.v, [], mb.f)
    for mn in mb.mats: me.materials.append(mats[mn])
    me.polygons.foreach_set("material_index", mb.m); me.update()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob); return ob

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--out", default=os.path.join(HERE, "..", "godot", "personnages", "louise_michel.glb"))
    p.add_argument("--preview", default="")
    a = p.parse_args(argv)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = {}
    for name, c in COL.items():
        m = bpy.data.materials.new("louise_" + name); m.use_nodes = True
        bs = m.node_tree.nodes["Principled BSDF"]; lin = tuple(v ** 2.2 for v in c)
        bs.inputs["Base Color"].default_value = (*lin, 1); bs.inputs["Roughness"].default_value = 0.85
        m.use_backface_culling = name not in DOUBLE; mats[name] = m
    b, f = build()
    obs = [to_object("louise", b, mats), to_object("drapeau", f, mats)]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    for ob in obs: ob.select_set(True)
    bpy.ops.export_scene.gltf(filepath=os.path.abspath(a.out), export_format="GLB", use_selection=True, export_yup=True, export_apply=True)
    tris = sum(len(q) - 2 for mb in (b, f) for q in mb.f)
    print(f"OK : {os.path.abspath(a.out)}  {tris} triangles")
    if a.preview:
        sc = bpy.context.scene; sc.render.engine = "CYCLES"; sc.cycles.samples = 48; sc.cycles.device = "CPU"
        try: sc.cycles.use_denoising = True
        except Exception: pass
        w = bpy.data.worlds.new("fond"); sc.world = w
        if not w.node_tree: w.use_nodes = True
        w.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.52, 0.42, 1)
        w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
        g = bpy.data.meshes.new("sol"); g.from_pydata([(-8, -8, 0), (8, -8, 0), (8, 8, 0), (-8, 8, 0)], [], [(0, 1, 2, 3)])
        gm = bpy.data.materials.new("sol"); gm.use_nodes = True
        gm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.42, 0.33, 0.25, 1); g.materials.append(gm)
        sc.collection.objects.link(bpy.data.objects.new("sol", g))
        sun = bpy.data.objects.new("soleil", bpy.data.lights.new("soleil", "SUN")); sc.collection.objects.link(sun)
        sun.data.energy = 3.5; sun.data.color = (1.0, 0.85, 0.7); sun.data.angle = 0.1
        sun.rotation_euler = Vector((-0.5, -0.7, 0.6)).normalized().to_track_quat("Z", "Y").to_euler()
        cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
        cam.data.lens = 50
        base, ext = os.path.splitext(os.path.abspath(a.preview)); shots = []
        for tag, pos, tgt, res in (("", (1.9, -4.4, 1.6), (0.3, 0, 1.25), (720, 960)), ("_visage", (0.35, -1.15, 1.58), (0.02, 0, 1.47), (720, 720))):
            sc.render.resolution_x, sc.render.resolution_y = res
            cam.location = pos; cam.rotation_euler = (Vector(tgt) - Vector(pos)).to_track_quat("-Z", "Y").to_euler()
            sc.render.filepath = base + tag + ext; bpy.ops.render.render(write_still=True); shots.append(sc.render.filepath)
        print("Aperçus :", shots)

if __name__ == "__main__":
    main()
