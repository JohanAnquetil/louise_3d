"""OSM -> décor low-poly stylisé de Montmartre -> .glb par zones pour Godot 4.

Génère : terrain en pente (butte), rues pavées avec trottoirs, escaliers avec rampes,
immeubles (façades à fenêtres, rez-de-chaussée à devantures, toits en zinc mansardés ou en
tuiles, cheminées), monuments (building:part, dômes), murs, arbres, réverbères, bancs,
fontaines, moulins, manège, parasols de la place du Tertre, horizon lointain.

Usage (Blender 4.x / 5.x, sans interface) :
    blender -b -P generate_montmartre.py -- --osm ../data/montmartre.osm --out ../godot/zones
    # ou avec le module pip "bpy" :
    python generate_montmartre.py --osm ../data/montmartre.osm --out ../godot/zones

Options : --preview image.png, --year 1871 (ignore les bâtiments dont start_date est postérieur),
--zone-size 200, --cell 3, --summit lat,lon, --alt-base 70, --alt-top 130.

Repères : Blender x = est, y = nord, z = altitude (m). Godot : x = est, y = altitude, -z = nord.
Les objets suffixés "_NOCOL" ne reçoivent pas de collision dans Godot.
Les textures sont écrites dans <out>/../materiaux et les matériaux sont décrits dans world.json :
Godot les reconstruit une seule fois et les partage entre toutes les zones.
"""
import bpy, sys, os, math, json, argparse, random, shutil
import numpy as np
import xml.etree.ElementTree as ET
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

HERE = os.path.dirname(os.path.abspath(__file__))

def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    p = argparse.ArgumentParser()
    p.add_argument("--osm", nargs="+", default=[os.path.join(HERE, "..", "data", "montmartre.osm")],
                   help="un ou plusieurs exports OSM (fusionnés ; les zones non couvertes restent vides)")
    p.add_argument("--out", default=os.path.join(HERE, "..", "godot", "zones"))
    p.add_argument("--preview", default="")
    p.add_argument("--year", type=int, default=0)
    p.add_argument("--zone-size", type=float, default=200.0)
    p.add_argument("--cell", type=float, default=3.0)
    p.add_argument("--summit", default="48.88672,2.34053")
    p.add_argument("--hill-radius", default="400,240")
    p.add_argument("--alt-base", type=float, default=70.0)
    p.add_argument("--alt-top", type=float, default=130.0)
    p.add_argument("--spawn", default="48.88650,2.34080")
    p.add_argument("--seed", type=int, default=1871)
    p.add_argument("--commune", action="store_true", help="décor de la Commune de 1871 : drapeaux rouges, affiches, banderoles, étalages, barricades")
    p.add_argument("--textures", default=os.path.join(HERE, "..", "data", "textures"), help="dossier des textures photo (facultatif)")
    return p.parse_args(argv)

HIGHWAY_WIDTH = {"motorway": 16, "trunk": 16, "primary": 14, "secondary": 12, "tertiary": 10,
                 "unclassified": 8, "residential": 8, "living_street": 7, "pedestrian": 6,
                 "service": 4, "footway": 2.5, "path": 2, "cycleway": 2.5, "steps": 3, "track": 3}
PEDESTRIAN = {"pedestrian", "footway", "path", "living_street"}
GREEN_TAGS = {("leisure", "park"), ("leisure", "garden"), ("leisure", "playground"), ("landuse", "grass"),
              ("landuse", "vineyard"), ("landuse", "cemetery"), ("landuse", "village_green"),
              ("landuse", "meadow"), ("natural", "wood"), ("natural", "scrub"), ("amenity", "grave_yard")}
LEVEL_H, BAY_W, STEP_LEN = 3.0, 3.2, 0.6

# ---------------------------------------------------------------------------------------------
# Palette (sRGB)
# ---------------------------------------------------------------------------------------------
WALLS_IMM = [(0.90, 0.86, 0.76), (0.93, 0.91, 0.86), (0.84, 0.82, 0.78), (0.90, 0.80, 0.72)]
WALLS_VIL = [(0.92, 0.80, 0.58), (0.92, 0.70, 0.66), (0.94, 0.92, 0.86), (0.93, 0.87, 0.65)]
SHUTTERS = [(0.62, 0.66, 0.64), (0.40, 0.50, 0.62), (0.86, 0.86, 0.84), (0.42, 0.52, 0.46),
            (0.36, 0.50, 0.40), (0.35, 0.45, 0.62), (0.50, 0.34, 0.28), (0.30, 0.42, 0.50)]
SHOPS = [(0.45, 0.12, 0.14), (0.10, 0.30, 0.22), (0.12, 0.18, 0.35), (0.70, 0.50, 0.18), (0.20, 0.20, 0.22), (0.50, 0.30, 0.16)]
FLAT = {"pierre": (0.93, 0.91, 0.86), "trottoir": (0.66, 0.64, 0.62), "marche": (0.64, 0.61, 0.57),
        "sol": (0.60, 0.55, 0.48), "herbe": (0.42, 0.56, 0.30), "vigne": (0.52, 0.58, 0.26),
        "tronc": (0.36, 0.27, 0.22), "feuille_a": (0.36, 0.52, 0.26), "feuille_b": (0.80, 0.58, 0.22),
        "fer": (0.12, 0.14, 0.13), "lanterne": (1.0, 0.85, 0.55), "vert_paris": (0.14, 0.30, 0.22),
        "mur": (0.74, 0.70, 0.63), "toile_rouge": (0.72, 0.16, 0.14), "toile_creme": (0.93, 0.88, 0.74),
        "moulin": (0.34, 0.25, 0.19), "eau": (0.30, 0.50, 0.62), "lointain_a": (0.50, 0.45, 0.47),
        "lointain_b": (0.58, 0.52, 0.51), "plaine": (0.36, 0.32, 0.34),
        "ardoise": (0.30, 0.33, 0.38), "brique": (0.62, 0.33, 0.26), "bronze": (0.17, 0.23, 0.20), "affiches": (0.92, 0.89, 0.80)}
# Textures photo facultatives (CC0, Poly Haven) : matériau -> (fichier dans --textures, largeur réelle estimée en m).
# Si le fichier manque, le matériau garde sa couleur unie ou sa texture dessinée.
# Essayées puis écartées (trop sombres / trop brunes) : "dalle": ("pavement_03_diff_1k.jpg", 2.0), "herbe": ("leafy_grass_diff_1k.jpg", 3.0).
PHOTOS = {"pave": ("blue_floor_tiles_01_diff_1k.jpg", 1.8), "trottoir": ("plastered_wall_05_diff_1k.jpg", 2.0),
          "mur": ("stone_wall_04_diff_1k.jpg", 2.2), "ardoise": ("roof_slates_03_diff_1k.jpg", 3.0),
          "brique": ("red_brick_wall_006_diff_1k.jpg", 5.0), "affiches": ("affiches.png", 1.6)}
UVU = 1.6   # les UV "au mètre" valent mètres / 1,6 ; Godot applique ensuite uv_scale = 1,6 / largeur de la texture
DOUBLE_SIDED = {"marche", "feuille_a", "feuille_b", "fer", "toile_rouge", "toile_creme", "moulin", "affiches"}
EMISSIVE = {"lanterne": 1.8}
TEXTURED = {"facades": ("facades.png", "facades_lum.png"), "toits": ("toits.png", None),
            "pave": ("pave.png", None), "dalle": ("dalle.png", None)}
FAC_ROWS = 48                      # atlas façades : 4 teintes x 8 rangées (immeuble) + 4 x 4 (village)
ROOF_ROW = lambda r: ((r + 0.03) / 4.0, (r + 0.97) / 4.0)   # atlas toits : 0 lucarne, 1 zinc, 2 tuiles, 3 brique
def srgb(c): return tuple(pow(v, 2.2) for v in c)

# ---------------------------------------------------------------------------------------------
# Textures (dessinées en numpy ; ligne 0 = bas de l'image)
# ---------------------------------------------------------------------------------------------
class Canvas:
    def __init__(self, w, h, fill=(0, 0, 0)):
        self.a = np.zeros((h, w, 3), np.float32); self.a[:] = fill; self.w, self.h = w, h
    def box(self, x0, y0, x1, y1, col):                      # coordonnées en pixels
        self.a[max(0, int(round(y0))):int(round(y1)), max(0, int(round(x0))):int(round(x1))] = col
    def save(self, path):
        rgba = np.concatenate([np.clip(self.a, 0, 1), np.ones((self.h, self.w, 1), np.float32)], 2)
        im = bpy.data.images.new(os.path.basename(path), self.w, self.h); im.pixels.foreach_set(rgba.ravel())
        im.filepath_raw = path; im.file_format = "PNG"; im.save(); return im

def mul(c, k): return tuple(min(1.0, v * k) for v in c)
WARM, GLASS, GLASS_HI = (1.0, 0.80, 0.45), (0.17, 0.21, 0.28), (0.30, 0.35, 0.43)

def draw_facades(rng):
    C = 128; alb = Canvas(4 * C, FAC_ROWS * C); lum = Canvas(4 * C, FAC_ROWS * C)
    def cell(col, row):
        ox, oy = col * C, row * C
        def b(x0, y0, x1, y1, c, light=None):
            alb.box(ox + x0 * C, oy + y0 * C, ox + x1 * C, oy + y1 * C, c)
            if light is not None: lum.box(ox + x0 * C, oy + y0 * C, ox + x1 * C, oy + y1 * C, light)
        return b
    def window(b, x0, y0, x1, y1, wall, lit, bars=True):
        b(x0 - 0.03, y0 - 0.03, x1 + 0.03, y1 + 0.03, mul(wall, 1.08))
        if lit: b(x0, y0, x1, y1, WARM, WARM)
        else:
            b(x0, y0, x1, y1, GLASS); b(x0, y0 + (y1 - y0) * 0.62, x1, y1, GLASS_HI)
        if bars:
            xm = (x0 + x1) / 2; b(xm - 0.012, y0, xm + 0.012, y1, (0.88, 0.87, 0.83)); b(x0, y0 + (y1 - y0) * 0.6, x1, y0 + (y1 - y0) * 0.6 + 0.02, (0.88, 0.87, 0.83))
    def shutters(b, x0, y0, x1, y1, col):
        for xa, xb in ((x0 - 0.115, x0 - 0.025), (x1 + 0.025, x1 + 0.115)):
            b(xa, y0, xb, y1, col)
            for k in range(1, 9): b(xa, y0 + (y1 - y0) * k / 9, xb, y0 + (y1 - y0) * k / 9 + 0.012, mul(col, 0.8))
    def rail(b, x0, x1, y0, y1):
        x = x0
        while x < x1: b(x, y0, x + 0.012, y1, (0.10, 0.11, 0.12)); x += 0.045
        b(x0, y1 - 0.02, x1, y1, (0.10, 0.11, 0.12)); b(x0, y0, x1, y0 + 0.015, (0.10, 0.11, 0.12))
    def shop(b, wall, sc, awning, lit):
        b(0.10, 0, 1.0, 0.88, sc); b(0.10, 0, 1.0, 0.15, mul(sc, 0.7))
        g = (1.0, 0.86, 0.58) if lit else (0.20, 0.24, 0.30)
        b(0.17, 0.18, 0.60, 0.66, g, g if lit else None); b(0.66, 0.05, 0.93, 0.66, g, g if lit else None)
        b(0.66, 0.05, 0.93, 0.09, mul(sc, 0.6)); b(0.10, 0.72, 1.0, 0.86, mul(sc, 1.5))
        b(0.2, 0.765, 0.9, 0.815, (0.93, 0.88, 0.70))
        if awning:
            for k in range(9): b(0.10 + k * 0.1, 0.56, 0.20 + k * 0.1, 0.70, (0.75, 0.18, 0.15) if k % 2 == 0 else (0.94, 0.90, 0.80))
    def door(b, x0, x1, y1, col):
        b(x0 - 0.03, 0, x1 + 0.03, y1 + 0.03, mul(col, 1.6)); b(x0, 0, x1, y1, col)
        xm = (x0 + x1) / 2; b(xm - 0.008, 0, xm + 0.008, y1, mul(col, 0.6))
        for xa, xb in ((x0 + 0.03, xm - 0.03), (xm + 0.03, x1 - 0.03)):
            b(xa, 0.08, xb, y1 * 0.45, mul(col, 1.25)); b(xa, y1 * 0.52, xb, y1 - 0.06, mul(col, 1.25))
    for style, walls, nrow, base in (("imm", WALLS_IMM, 8, 0), ("vil", WALLS_VIL, 4, 32)):
        for ci, wall in enumerate(walls):
            r0 = base + ci * nrow
            alb.box(0, r0 * C, 4 * C, (r0 + nrow) * C, wall)
            sh = SHUTTERS[ci + (0 if style == "imm" else 4)]
            for col in range(4):                                   # --- rez-de-chaussée
                b = cell(col, r0); sc = SHOPS[(ci * 2 + col + (0 if style == "imm" else 3)) % len(SHOPS)]
                lit = rng.random() < 0.7
                if style == "imm":
                    if col == 0: shop(b, wall, sc, False, lit)
                    elif col == 1: b(0, 0, 1, 0.10, mul(wall, 0.8)); door(b, 0.30, 0.70, 0.80, (0.13, 0.22, 0.18))
                    elif col == 2: shop(b, wall, sc, True, lit)
                    else: b(0, 0, 1, 0.20, mul(wall, 0.8)); window(b, 0.34, 0.32, 0.66, 0.80, wall, rng.random() < 0.3); rail(b, 0.34, 0.66, 0.32, 0.50)
                else:
                    b(0, 0, 1, 0.12, mul(wall, 0.82))
                    if col == 0: door(b, 0.16, 0.40, 0.70, sh); window(b, 0.58, 0.32, 0.84, 0.70, wall, rng.random() < 0.4); shutters(b, 0.58, 0.32, 0.84, 0.70, sh)
                    elif col == 1: window(b, 0.36, 0.30, 0.64, 0.72, wall, rng.random() < 0.4); shutters(b, 0.36, 0.30, 0.64, 0.72, sh)
                    elif col == 2: shop(b, wall, sc, True, lit)
                    else: door(b, 0.38, 0.62, 0.72, mul(sh, 0.7))
                b(0, 0.955, 1, 1.0, mul(wall, 0.86))               # bandeau au-dessus du rez-de-chaussée
            for k in range(1, nrow):                               # --- étages
                for col in range(4):
                    b = cell(col, r0 + k); lit = rng.random() < 0.32
                    b(0, 0, 1, 0.03, mul(wall, 0.9))
                    if style == "imm":
                        balcony = k in (2, 5)
                        y0, y1 = (0.17, 0.80) if k < nrow - 1 else (0.24, 0.72)
                        if balcony: b(0, 0.10, 1, 0.15, mul(wall, 0.72))
                        window(b, 0.34, y0, 0.66, y1, wall, lit); shutters(b, 0.34, y0, 0.66, y1, sh)
                        if balcony: rail(b, 0.0, 1.0, 0.15, 0.36)
                        else: rail(b, 0.31, 0.69, y0, y0 + 0.17)
                    else:
                        window(b, 0.37, 0.26, 0.63, 0.74, wall, lit); shutters(b, 0.37, 0.26, 0.63, 0.74, sh)
                        b(0.33, 0.22, 0.67, 0.25, mul(wall, 0.8))
            alb.box(0, (r0 + nrow) * C - 5, 4 * C, (r0 + nrow) * C, mul(wall, 0.78))   # corniche
    return alb, lum

def draw_roofs(rng):
    C = 128; t = Canvas(2 * C, 4 * C)
    zinc, tile, brick = (0.47, 0.52, 0.58), (0.72, 0.38, 0.26), (0.62, 0.33, 0.26)
    t.box(0, 0, 2 * C, 2 * C, zinc)
    for k in range(8):
        t.box(k * 32, 0, k * 32 + 2, 2 * C, mul(zinc, 0.82)); t.box(k * 32 + 2, 0, k * 32 + 4, 2 * C, mul(zinc, 1.12))
    for ox in (0, C):                                             # lucarne (rangée 0)
        t.box(ox + 40, 16, ox + 88, 100, (0.86, 0.85, 0.80)); t.box(ox + 46, 22, ox + 82, 88, GLASS)
        t.box(ox + 46, 62, ox + 82, 88, GLASS_HI); t.box(ox + 63, 22, ox + 65, 88, (0.86, 0.85, 0.80))
        t.box(ox + 36, 100, ox + 92, 108, mul(zinc, 0.7))
    for j in range(8):                                            # tuiles (rangée 2)
        for i in range(16):
            t.box(i * 16 + (8 if j % 2 else 0) - 8, 2 * C + j * 16, i * 16 + (8 if j % 2 else 0) + 8, 2 * C + j * 16 + 16, mul(tile, rng.uniform(0.86, 1.1)))
        t.box(0, 2 * C + j * 16, 2 * C, 2 * C + j * 16 + 2, mul(tile, 0.6))
    t.box(0, 3 * C, 2 * C, 4 * C, (0.80, 0.76, 0.70))             # brique (rangée 3)
    for j in range(13):
        for i in range(9):
            x = i * 32 - (16 if j % 2 else 0)
            t.box(x + 1, 3 * C + j * 8 + 1, x + 31, 3 * C + j * 8 + 7, mul(brick, rng.uniform(0.85, 1.12)))
    t.box(0, 3 * C + 104, 2 * C, 3 * C + 112, (0.80, 0.76, 0.70)); t.box(0, 3 * C + 112, 2 * C, 4 * C, (0.55, 0.30, 0.22))
    return t

def draw_ground(rng):
    N = 256; pave = Canvas(N, N, (0.24, 0.23, 0.23))
    for j in range(8):
        for i in range(-1, 8):
            x = i * 32 + (16 if j % 2 else 0); g = rng.uniform(0.36, 0.50)
            for xx in (x, x + N if x < 0 else x):
                pave.box(xx + 2, j * 32 + 2, min(N, xx + 30), j * 32 + 30, (g, g * 0.97, g * 0.95))
    dalle = Canvas(N, N, (0.55, 0.52, 0.47))
    for j in range(4):
        for i in range(-1, 4):
            x = i * 64 + (32 if j % 2 else 0); g = rng.uniform(0.92, 1.06)
            for xx in (x, x + N if x < 0 else x):
                dalle.box(xx + 1, j * 64 + 1, min(N, xx + 63), j * 64 + 63, mul((0.74, 0.70, 0.63), g))
    return pave, dalle

def make_materials(matdir, rng, texdir=""):
    os.makedirs(matdir, exist_ok=True)
    alb, lum = draw_facades(rng); pave, dalle = draw_ground(rng)
    imgs = {"facades.png": alb, "facades_lum.png": lum, "toits.png": draw_roofs(rng), "pave.png": pave, "dalle.png": dalle}
    imgs = {k: v.save(os.path.join(matdir, k)) for k, v in imgs.items()}
    photos = {}
    for name, (fn, width) in PHOTOS.items():                      # copie des photos vers godot/materiaux
        src = os.path.join(texdir, fn) if texdir else ""
        if src and os.path.isfile(src):
            if name == "ardoise":                                     # retire la bande de faîtage en haut de la photo
                im = bpy.data.images.load(src); w, h = im.size
                px = np.array(im.pixels[:], np.float32).reshape(h, w, 4)[:int(h * 0.955)]
                img = bpy.data.images.new(name + "_photo", px.shape[1], px.shape[0]); img.pixels.foreach_set(px.ravel())
                fn = name + "_photo.png"; img.filepath_raw = os.path.join(matdir, fn); img.file_format = "PNG"; img.save()
                photos[name] = (img, fn, width * px.shape[0] / h)
            else:                                                     # copie telle quelle
                fn = name + "_photo" + os.path.splitext(src)[1].lower(); shutil.copyfile(src, os.path.join(matdir, fn))
                photos[name] = (bpy.data.images.load(os.path.join(matdir, fn)), fn, width)
    mats, table = {}, []
    def base(name):
        m = bpy.data.materials.new(name); m.use_nodes = True
        b = m.node_tree.nodes["Principled BSDF"]; b.inputs["Roughness"].default_value = 0.9
        m.use_backface_culling = name not in DOUBLE_SIDED
        mats[name] = m; return m, b
    def textured(m, b, img, scale=1.0):
        nt = m.node_tree; t = nt.nodes.new("ShaderNodeTexImage"); t.image = img
        if scale != 1.0:
            tc = nt.nodes.new("ShaderNodeTexCoord"); mp = nt.nodes.new("ShaderNodeMapping"); mp.inputs["Scale"].default_value = (scale, scale, scale)
            nt.links.new(tc.outputs["UV"], mp.inputs["Vector"]); nt.links.new(mp.outputs["Vector"], t.inputs["Vector"])
        nt.links.new(t.outputs["Color"], b.inputs["Base Color"]); return t
    for name, col in FLAT.items():
        m, b = base(name)
        if name in photos:
            img, fn, width = photos[name]; textured(m, b, img, UVU / width)
            table.append(dict(name=name, color=[1, 1, 1], albedo=fn, uv_scale=UVU / width, double_sided=name in DOUBLE_SIDED)); continue
        b.inputs["Base Color"].default_value = (*srgb(col), 1); m.diffuse_color = (*srgb(col), 1)
        e = dict(name=name, color=list(col), double_sided=name in DOUBLE_SIDED)
        if name == "eau": b.inputs["Roughness"].default_value = 0.12; e["roughness"] = 0.12
        if name in EMISSIVE:
            b.inputs["Emission Color"].default_value = (*srgb(col), 1); b.inputs["Emission Strength"].default_value = EMISSIVE[name]
            e.update(emission_color=list(col), emission_energy=EMISSIVE[name])
        table.append(e)
    for name, (a, l) in TEXTURED.items():
        m, b = base(name)
        if name in photos:
            img, fn, width = photos[name]; textured(m, b, img, UVU / width)
            table.append(dict(name=name, color=[1, 1, 1], albedo=fn, uv_scale=UVU / width, double_sided=False)); continue
        textured(m, b, imgs[a])
        e = dict(name=name, color=[1, 1, 1], albedo=a, double_sided=False)
        if l:
            t2 = m.node_tree.nodes.new("ShaderNodeTexImage"); t2.image = imgs[l]
            m.node_tree.links.new(t2.outputs["Color"], b.inputs["Emission Color"]); b.inputs["Emission Strength"].default_value = 1.5
            e.update(emission=l, emission_energy=0.9)
        table.append(e)
    return mats, table

# ---------------------------------------------------------------------------------------------
# Lecture OSM et petits outils géométriques
# ---------------------------------------------------------------------------------------------
def parse_osm(path):
    nodes, node_tags, ways, rels, bounds = {}, {}, {}, {}, None
    for _, el in ET.iterparse(path, events=("end",)):
        if el.tag == "bounds":
            bounds = tuple(float(el.get(k)) for k in ("minlat", "minlon", "maxlat", "maxlon"))
        elif el.tag == "node":
            i = int(el.get("id")); nodes[i] = (float(el.get("lat")), float(el.get("lon")))
            t = {c.get("k"): c.get("v") for c in el if c.tag == "tag"}
            if t: node_tags[i] = t
            el.clear()
        elif el.tag == "way":
            ways[int(el.get("id"))] = ([int(c.get("ref")) for c in el if c.tag == "nd"],
                                       {c.get("k"): c.get("v") for c in el if c.tag == "tag"})
            el.clear()
        elif el.tag == "relation":
            rels[int(el.get("id"))] = ([(c.get("type"), int(c.get("ref")), c.get("role")) for c in el if c.tag == "member"],
                                       {c.get("k"): c.get("v") for c in el if c.tag == "tag"})
            el.clear()
    if bounds is None:
        la = [v[0] for v in nodes.values()]; lo = [v[1] for v in nodes.values()]
        bounds = (min(la), min(lo), max(la), max(lo))
    return nodes, node_tags, ways, rels, bounds

def parse_many(paths):
    """Fusionne plusieurs exports (mêmes identifiants = mêmes objets). Renvoie aussi l'emprise de chaque export."""
    N, NT, W, R, covers = {}, {}, {}, {}, []
    for p in paths:
        n, nt, w, r, b = parse_osm(p); N.update(n); NT.update(nt); R.update(r); covers.append(b)
        for k, v in w.items():
            if k not in W or len(v[0]) > len(W[k][0]): W[k] = v
    b = (min(c[0] for c in covers), min(c[1] for c in covers), max(c[2] for c in covers), max(c[3] for c in covers))
    return N, NT, W, list(R.values()), b, covers

def num(s, default=None):
    try: return float(str(s).replace(",", ".").split()[0].rstrip("m"))
    except Exception: return default

def pip(P, poly):
    x, y = P[:, 0], P[:, 1]; inside = np.zeros(len(P), bool)
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i + 1) % len(poly)]
        if y1 == y2: continue
        inside ^= ((y1 > y) != (y2 > y)) & (x < (x2 - x1) * (y - y1) / (y2 - y1) + x1)
    return inside

def area2(poly):
    x, y = poly[:, 0], poly[:, 1]
    return float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))

def is_convex(poly):
    d1 = np.roll(poly, -1, 0) - poly; d2 = np.roll(d1, -1, 0)
    return bool(np.all(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0] > -1e-6))

def seg_dist(P, A, extra=None, cutoff=None):
    """Distance de chaque point (N,2) au plus proche segment de A (S,4) ; extra (S,) est soustrait (demi-largeur).
    cutoff : on ne s'intéresse qu'aux distances inférieures (les segments lointains sont ignorés -> bien plus rapide)."""
    out = np.full(len(P), 1e9)
    if not len(A) or not len(P): return out
    if cutoff is not None:
        pad = cutoff + (float(extra.max()) if extra is not None else 0.0) + 0.5
        lo, hi = np.minimum(A[:, 0:2], A[:, 2:4]) - pad, np.maximum(A[:, 0:2], A[:, 2:4]) + pad
    for i0 in range(0, len(P), 1500):
        Pc = P[i0:i0 + 1500]; As, ex = A, extra
        if cutoff is not None:
            pmin, pmax = Pc.min(0), Pc.max(0)
            m = (hi[:, 0] >= pmin[0]) & (lo[:, 0] <= pmax[0]) & (hi[:, 1] >= pmin[1]) & (lo[:, 1] <= pmax[1])
            if not m.any(): continue
            As = A[m]; ex = extra[m] if extra is not None else None
        ax, ay, bx, by = As[:, 0], As[:, 1], As[:, 2], As[:, 3]
        dx, dy = bx - ax, by - ay; L2 = np.maximum(dx * dx + dy * dy, 1e-9); C = max(16, 1_500_000 // len(As))
        for i in range(0, len(Pc), C):
            px, py = Pc[i:i + C, 0, None], Pc[i:i + C, 1, None]
            t = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0, 1)
            d = np.hypot(px - ax - t * dx, py - ay - t * dy)
            if ex is not None: d = d - ex
            dm = d.min(1); out[i0 + i:i0 + i + len(dm)] = dm
    return out

def resample(pts, step):
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        L = float(np.hypot(*(b - a))); n = max(1, int(math.ceil(L / step)))
        out.extend(a + (b - a) * (k / n) for k in range(1, n + 1))
    return np.array(out)

def normals2d(P):
    T = np.gradient(P, axis=0) if len(P) > 2 else np.repeat((P[-1] - P[0])[None], len(P), 0)
    T = T / np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9)
    return np.stack([-T[:, 1], T[:, 0]], 1)

def ngon(x, y, r, n, rot=0.0):
    return np.array([(x + r * math.cos(rot + 6.2832 * i / n), y + r * math.sin(rot + 6.2832 * i / n)) for i in range(n)])

def obox(x, y, hl, hw, ang):
    c, s = math.cos(ang), math.sin(ang)
    return np.array([(x + c * a - s * b, y + s * a + c * b) for a, b in ((-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw))])

# ---------------------------------------------------------------------------------------------
# Relief
# ---------------------------------------------------------------------------------------------
class Ground:
    MARGIN, BLEND = 4.5, 7.0
    def __init__(self, summit_xy, radius, base, top):
        self.c, self.r, self.base, self.top = summit_xy, radius, base, top
        self.segs, self.plazas, self.pits, self.A = [], [], [], None
    def nat(self, x, y):
        d = np.hypot((x - self.c[0]) / self.r[0], (y - self.c[1]) / self.r[1])
        t = np.clip((d - 0.15) / 1.35, 0, 1)
        return self.base + (self.top - self.base) * 0.5 * (1 + np.cos(np.pi * t))
    def add_line(self, pts, hw):
        for a, b in zip(pts[:-1], pts[1:]): self.segs.append((a[0], a[1], b[0], b[1], hw, np.nan, 1.0))
    def add_plaza(self, poly):
        c = poly.mean(0); h = float(self.nat(c[0], c[1])); self.plazas.append((poly, h))
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            self.segs.append((a[0], a[1], b[0], b[1], 0.0, h, 50.0))
        return h
    def h(self, P):
        P = np.asarray(P, float).reshape(-1, 2)
        hn = self.nat(P[:, 0], P[:, 1])
        if not self.segs: return hn
        if self.A is None or len(self.A) != len(self.segs):
            self.A = np.array(self.segs, float); A = self.A; pad = A[:, 4:5] + self.MARGIN + self.BLEND + 6.0
            self.lo, self.hi = np.minimum(A[:, 0:2], A[:, 2:4]) - pad, np.maximum(A[:, 0:2], A[:, 2:4]) + pad
        out = hn.copy(); lo, hi = self.lo, self.hi
        for i0 in range(0, len(P), 1500):                                  # seuls les segments proches du paquet de points comptent
            Pc = P[i0:i0 + 1500]; pmin, pmax = Pc.min(0), Pc.max(0)
            m = (hi[:, 0] >= pmin[0]) & (lo[:, 0] <= pmax[0]) & (hi[:, 1] >= pmin[1]) & (lo[:, 1] <= pmax[1])
            if not m.any(): continue
            ax, ay, bx, by, hw, fx, wm = self.A[m].T
            dx, dy = bx - ax, by - ay; L2 = np.maximum(dx * dx + dy * dy, 1e-9); C = max(32, 1_500_000 // len(ax))
            for i in range(0, len(Pc), C):
                px, py = Pc[i:i + C, 0, None], Pc[i:i + C, 1, None]
                t = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0, 1)
                qx, qy = ax + t * dx, ay + t * dy
                de = np.maximum(np.hypot(px - qx, py - qy) - hw, 0)
                hs = np.where(np.isnan(fx), self.nat(qx, qy), fx)
                w = wm / (de + 0.5) ** 4
                havg = (w * hs).sum(1) / w.sum(1)
                k = np.clip((de.min(1) - self.MARGIN) / self.BLEND, 0, 1); k = k * k * (3 - 2 * k)
                j0 = i0 + i; j1 = j0 + len(havg)
                out[j0:j1] = havg * (1 - k) + hn[j0:j1] * k
        polys = self.plazas + self.pits                                    # places plates, puis bassins creusés sous le quai
        if polys:
            if getattr(self, "_nb", -1) != len(polys):
                self._nb = len(polys)
                self._plo = np.array([q.min(0) for q, _ in polys]); self._phi = np.array([q.max(0) for q, _ in polys])
            pmin, pmax = P.min(0), P.max(0)
            for k in np.where((self._phi[:, 0] >= pmin[0]) & (self._plo[:, 0] <= pmax[0]) & (self._phi[:, 1] >= pmin[1]) & (self._plo[:, 1] <= pmax[1]))[0]:
                poly, hp = polys[k]
                sel = np.where((P[:, 0] >= self._plo[k, 0]) & (P[:, 0] <= self._phi[k, 0]) & (P[:, 1] >= self._plo[k, 1]) & (P[:, 1] <= self._phi[k, 1]))[0]
                if len(sel): out[sel[pip(P[sel], poly)]] = hp
        return out

# ---------------------------------------------------------------------------------------------
# Maillages
# ---------------------------------------------------------------------------------------------
class MB:
    def __init__(self): self.v, self.f, self.m, self.uv, self.mats = [], [], [], [], []
    def face(self, pts, mat, uv=None):
        n = len(self.v); self.v.extend(pts); self.f.append(tuple(range(n, n + len(pts))))
        if mat not in self.mats: self.mats.append(mat)
        self.m.append(self.mats.index(mat)); self.uv.append(uv or [(0.5, 0.5)] * len(pts))
    def tris(self): return sum(len(f) - 2 for f in self.f)

def wuv(pts, s=UVU): return [(p[0] / s, p[1] / s) for p in pts]

def cap(mb, ring, z, mat, uvf=None):
    for tri in tessellate_polygon([[Vector((p[0], p[1], 0)) for p in ring]]):
        a, b, c = (ring[i] for i in tri)
        if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) < 0: tri = (tri[0], tri[2], tri[1])
        pts = [(ring[i][0], ring[i][1], z) for i in tri]
        mb.face(pts, mat, uvf(pts) if uvf else None)

def ring_walls(mb, r0, z0, r1, z1, mat, uvf=None):
    n = len(r0)
    for i in range(n):
        j = (i + 1) % n
        uv = uvf(i, float(np.hypot(*(r0[j] - r0[i])))) if uvf else None
        mb.face([(r0[i][0], r0[i][1], z0), (r0[j][0], r0[j][1], z0), (r1[j][0], r1[j][1], z1), (r1[i][0], r1[i][1], z1)], mat, uv)

def cone(mb, ring, z0, apex, mat):
    for i in range(len(ring)):
        j = (i + 1) % len(ring)
        mb.face([(ring[i][0], ring[i][1], z0), (ring[j][0], ring[j][1], z0), apex], mat if isinstance(mat, str) else mat[i % len(mat)])

def prism(mb, ring, z0, z1, mat, top=True, uvf=None):
    ring_walls(mb, ring, z0, ring, z1, mat, uvf)
    if top: cap(mb, ring, z1, mat)

def add_monument(mb, poly, g, bd):
    c = poly.mean(0); gref = float(g.mean()); top = gref + bd["h"]; mat = bd["mat"]
    if bd["minh"] > 0: z0 = gref + bd["minh"]
    else: z0 = gref; ring_walls(mb, poly, float(g.min()) - 2.0, poly, gref, mat)
    roof, rh = bd["roof"], bd["roofh"]
    if roof in ("dome", "pyramidal", "onion", "cone") and rh > 0:
        wt = max(z0, top - rh); ring_walls(mb, poly, z0, poly, wt, mat)
        steps = 5 if roof in ("dome", "onion") else 1
        prev, pz = poly, wt
        for k in range(1, steps):
            a = k / steps * math.pi / 2
            cur, cz = c + (poly - c) * math.cos(a), wt + rh * math.sin(a)
            ring_walls(mb, prev, pz, cur, cz, mat); prev, pz = cur, cz
        cone(mb, prev, pz, (c[0], c[1], wt + rh), mat)
    else:
        ring_walls(mb, poly, z0, poly, top, mat); cap(mb, poly, top, mat)

def add_building(mb, poly, g, bd, rng):
    """Immeuble parisien (>= 4 niveaux : mansarde en zinc, lucarnes) ou maison de village (toit de tuiles)."""
    n = len(poly); c = poly.mean(0); gref = float(g.mean()); top = gref + bd["h"]
    village = bd["h"] <= 10.6
    rad = float(np.linalg.norm(poly - c, axis=1).mean())
    inset = lambda d: c + (poly - c) * max(0.35, 1 - d / max(1.0, rad))
    edges = np.linalg.norm(np.roll(poly, -1, 0) - poly, axis=1)
    convex = is_convex(poly)
    rr = 0.0
    if village:
        minw = 2 * abs(area2(poly)) / 2 / max(1e-3, edges.sum() / 2) if n != 4 else min(edges[0] + edges[2], edges[1] + edges[3]) / 2
        if convex and n <= 8 and bd["h"] > 4.5: rr = float(np.clip(0.32 * minw, 1.2, 3.2))
        wt = top - rr
    else: wt = top - 2.6
    nrow = 4 if village else 8
    lv = int(np.clip(round((wt - gref) / LEVEL_H), 1, nrow))
    r0 = (32 + bd["ci"] * 4) if village else bd["ci"] * 8
    v0, v1 = r0 / FAC_ROWS, (r0 + lv) / FAC_ROWS
    offs = [rng.randrange(4) for _ in range(n)]
    pv = ((r0 + 1.87) / FAC_ROWS, (r0 + 1.93) / FAC_ROWS)
    ring_walls(mb, poly, float(g.min()) - 2.0, poly, gref, "facades",
               lambda i, L: [((offs[i] + .02) / 4, pv[0]), ((offs[i] + .08) / 4, pv[0]), ((offs[i] + .08) / 4, pv[1]), ((offs[i] + .02) / 4, pv[1])])
    def fuv(i, L):
        nb = max(1, round(L / BAY_W)); k = offs[i]
        u0, u1 = ((k + .015) / 4, (k + .085) / 4) if L < 1.8 else (k / 4, (k + nb) / 4)
        return [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
    ring_walls(mb, poly, gref, poly, wt, "facades", fuv)
    zl, zh = ROOF_ROW(1); zmid = (zl + zh) / 2
    zinc_cap = lambda pts: [(p[0] / 2.4, zmid) for p in pts]
    if not village:                                               # mansarde + terrasson en zinc
        r1 = inset(0.9); lo, hi = ROOF_ROW(0)
        def muv(i, L):
            nb = max(1, round(L / BAY_W)) if L >= 1.8 else 0.2
            return [(0, lo), (nb, lo), (nb, hi), (0, hi)]
        ring_walls(mb, poly, wt, r1, top, "toits", muv); cap(mb, r1, top, "toits", zinc_cap)
        chim_base, chim_top = top - 0.2, top + rng.uniform(1.0, 1.6)
    elif rr > 0:                                                  # toit d'ardoise à croupes
        def slope_face(pts3):
            """UV au mètre : u le long de l'égout, v le long de la pente (rangs d'ardoise horizontaux)."""
            p0, p1 = np.array(pts3[0]), np.array(pts3[1]); e = (p1 - p0)[:2]; L = max(1e-6, float(np.hypot(*e))); e = e / L
            uv = []
            for q in pts3:
                d = np.array(q) - p0; u = float(d[0] * e[0] + d[1] * e[1]); hd = abs(float(d[0] * -e[1] + d[1] * e[0]))
                uv.append((u / UVU, float(np.hypot(hd, d[2])) / UVU))
            mb.face(pts3, "ardoise", uv)
        P3 = lambda q, z: (q[0], q[1], z)
        if n == 4:
            p = poly if edges[0] + edges[2] >= edges[1] + edges[3] else np.roll(poly, -1, 0)
            m1, m3 = (p[1] + p[2]) / 2, (p[3] + p[0]) / 2
            a, b = m3 + (m1 - m3) * 0.22, m3 + (m1 - m3) * 0.78; zr = wt + rr
            slope_face([P3(p[0], wt), P3(p[1], wt), P3(b, zr), P3(a, zr)]); slope_face([P3(p[2], wt), P3(p[3], wt), P3(a, zr), P3(b, zr)])
            slope_face([P3(p[1], wt), P3(p[2], wt), P3(b, zr)]); slope_face([P3(p[3], wt), P3(p[0], wt), P3(a, zr)])
        else:
            r1 = c + (poly - c) * 0.3
            for i in range(n):
                j = (i + 1) % n
                slope_face([P3(poly[i], wt), P3(poly[j], wt), P3(r1[j], wt + rr), P3(r1[i], wt + rr)])
            cap(mb, r1, wt + rr, "ardoise", wuv)
        chim_base, chim_top = wt - 0.2, wt + rr + rng.uniform(0.5, 1.0)
    else:
        cap(mb, poly, top, "toits", zinc_cap); chim_base, chim_top = top - 0.2, top + 1.0
    blo, bhi = ROOF_ROW(3)                                        # cheminées
    if abs(area2(poly)) / 2 > 35:
        for _ in range(rng.choice([1, 1, 2, 2, 3]) if not village else rng.choice([0, 1, 1])):
            i = max(range(n), key=lambda k: edges[k] * rng.uniform(0.5, 1.0))
            a, b = poly[i], poly[(i + 1) % n]; t = rng.uniform(0.25, 0.75); m = a + (b - a) * t
            d = c - m; d = d / max(1e-6, float(np.hypot(*d)))
            q = obox(*(m + d * 1.3), 0.6, 0.28, math.atan2(b[1] - a[1], b[0] - a[0]))
            cu = rng.uniform(0, 3)
            ring_walls(mb, q, chim_base, q, chim_top, "brique", lambda k, L: [(cu, 0), (cu + L / UVU, 0), (cu + L / UVU, (chim_top - chim_base) / UVU), (cu, (chim_top - chim_base) / UVU)])
            cap(mb, q, chim_top, "brique", wuv)

def add_tree(mb, x, y, z, rng):
    s = rng.uniform(0.8, 1.35); rot = rng.uniform(0, 6.28); leaf = "feuille_a" if rng.random() < 0.6 else "feuille_b"
    prism(mb, ngon(x, y, 0.28 * s, 5, rot), z - 0.5, z + 2.6 * s, "tronc", top=False)
    a, b = ngon(x, y, 0.9 * s, 6, rot), ngon(x, y, 2.3 * s, 6, rot)
    ring_walls(mb, a, z + 2.3 * s, b, z + 3.9 * s, leaf); cone(mb, b, z + 3.9 * s, (x, y, z + 7.0 * s), leaf)

def add_lamp(mb, x, y, z):
    prism(mb, ngon(x, y, 0.07, 4, 0.785), z - 0.3, z + 3.4, "fer", top=False)
    ring_walls(mb, ngon(x, y, 0.13, 4, 0.785), z + 3.4, ngon(x, y, 0.24, 4, 0.785), z + 3.85, "lanterne")
    cone(mb, ngon(x, y, 0.30, 4, 0.785), z + 3.85, (x, y, z + 4.1), "fer")

def add_bench(mb, x, y, z, ang):
    prism(mb, obox(x, y, 0.85, 0.22, ang), z + 0.38, z + 0.46, "vert_paris")
    bx, by = x - math.sin(ang) * 0.22, y + math.cos(ang) * 0.22
    prism(mb, obox(bx, by, 0.85, 0.035, ang), z + 0.46, z + 0.92, "vert_paris")
    for s in (-0.7, 0.7):
        prism(mb, obox(x + math.cos(ang) * s, y + math.sin(ang) * s, 0.04, 0.2, ang), z - 0.2, z + 0.38, "fer", top=False)

def add_wallace(mb, x, y, z):
    prism(mb, ngon(x, y, 0.38, 6), z - 0.2, z + 0.9, "vert_paris"); prism(mb, ngon(x, y, 0.12, 6), z + 0.9, z + 1.9, "vert_paris", top=False)
    cone(mb, ngon(x, y, 0.42, 6), z + 1.9, (x, y, z + 2.5), "vert_paris")

def add_fountain(mb, x, y, z):
    prism(mb, ngon(x, y, 2.0, 10), z - 0.3, z + 0.55, "pierre", top=False); cap(mb, ngon(x, y, 2.0, 10), z + 0.45, "eau")
    prism(mb, ngon(x, y, 0.3, 6), z + 0.45, z + 1.4, "pierre")

def add_carousel(mb, x, y, z):
    prism(mb, ngon(x, y, 5.0, 12), z - 0.3, z + 0.35, "toile_creme")
    for p in ngon(x, y, 4.6, 12): prism(mb, ngon(p[0], p[1], 0.07, 4), z + 0.35, z + 3.3, "lanterne", top=False)
    prism(mb, ngon(x, y, 1.0, 8), z + 0.35, z + 3.3, "toile_rouge", top=False)
    ring_walls(mb, ngon(x, y, 5.4, 12), z + 3.0, ngon(x, y, 5.4, 12), z + 3.5, "toile_rouge")
    cone(mb, ngon(x, y, 5.4, 12), z + 3.5, (x, y, z + 6.0), ["toile_rouge", "toile_creme"])

def add_windmill(mb, x, y, z, rng):
    ring_walls(mb, ngon(x, y, 3.2, 8), z - 1.0, ngon(x, y, 2.3, 8), z + 9.0, "moulin")
    cone(mb, ngon(x, y, 2.7, 8), z + 9.0, (x, y, z + 11.5), "tronc")
    ang = rng.uniform(0, 6.28); dx, dy = math.cos(ang), math.sin(ang); hx, hy, hz = x - dy * 2.6, y + dx * 2.6, z + 9.0
    for k in range(4):
        a = 0.6 + k * math.pi / 2; ca, sa = math.cos(a), math.sin(a)
        P = lambda r, w: (hx + dx * (ca * r - sa * w), hy + dy * (ca * r - sa * w), hz + sa * r + ca * w)
        mb.face([P(0.8, 0.0), P(7.5, 0.0), P(7.5, 1.3), P(0.8, 1.3)], "toile_creme")
        mb.face([P(0, -0.08), P(7.5, -0.08), P(7.5, 0.08), P(0, 0.08)], "moulin")

def add_parasol(mb, x, y, z, k):
    prism(mb, ngon(x, y, 0.04, 4), z, z + 2.45, "fer", top=False)
    cone(mb, ngon(x, y, 1.6, 8, k), z + 2.05, (x, y, z + 2.6), ["toile_rouge", "toile_creme"] if k % 2 else "toile_creme" if k % 4 else "toile_rouge")
    prism(mb, ngon(x + 0.7, y + 0.2, 0.38, 6), z + 0.68, z + 0.74, "pierre"); prism(mb, ngon(x + 0.7, y + 0.2, 0.04, 4), z, z + 0.68, "fer", top=False)

def figure(mb, x, y, z, k, ang, mat, arm_up=True):
    """Personnage debout stylisé de hauteur ~10*k (drapé, tête, bras), tourné vers l'angle ang."""
    fx, fy = math.cos(ang), math.sin(ang); rx, ry = fy, -fx                 # avant, et côté droit du personnage
    prof = [(1.5, 0), (1.35, 1.5), (1.1, 3.2), (0.95, 4.6), (1.15, 5.6), (1.2, 6.6), (0.45, 7.0), (0.62, 7.5), (0.6, 8.1), (0.36, 8.5)]
    for (r0, z0), (r1, z1) in zip(prof[:-1], prof[1:]):
        ring_walls(mb, ngon(x, y, r0 * k, 8, ang), z + z0 * k, ngon(x, y, r1 * k, 8, ang), z + z1 * k, mat)
    cone(mb, ngon(x, y, 0.36 * k, 8, ang), z + 8.5 * k, (x - fx * 0.15 * k, y - fy * 0.15 * k, z + 8.85 * k), mat)
    def limb(pts):                                                         # pts : (côté, avant, hauteur, rayon)
        rings = [(ngon(x + rx * a * k + fx * b * k, y + ry * a * k + fy * b * k, r * k, 5, ang), z + h * k) for a, b, h, r in pts]
        for (q0, z0), (q1, z1) in zip(rings[:-1], rings[1:]): ring_walls(mb, q0, z0, q1, z1, mat)
        cap(mb, rings[-1][0], rings[-1][1], mat)
    if arm_up:
        limb([(1.05, 0.0, 6.5, 0.34), (1.75, 0.25, 7.5, 0.28), (2.0, 0.5, 8.9, 0.22)])        # bras droit levé
        hx, hy = x + rx * 2.0 * k + fx * 0.5 * k, y + ry * 2.0 * k + fy * 0.5 * k
        cone(mb, ngon(hx, hy, 0.1 * k, 4), z + 8.9 * k, (hx, hy, z + 9.7 * k), mat)             # rameau d'olivier
        cone(mb, ngon(hx, hy, 0.42 * k, 5, 0.3), z + 9.5 * k, (hx + rx * 0.2 * k, hy + ry * 0.2 * k, z + 10.4 * k), mat)
    else: limb([(1.05, 0.0, 6.5, 0.34), (1.35, 0.3, 5.4, 0.28), (1.2, 0.8, 4.6, 0.22)])
    limb([(-1.05, 0.0, 6.5, 0.34), (-1.45, 0.2, 5.4, 0.28), (-1.55, 0.45, 4.7, 0.22)])        # bras gauche vers la tablette
    prism(mb, obox(x - rx * 1.75 * k + fx * 0.45 * k, y - ry * 1.75 * k + fy * 0.45 * k, 0.5 * k, 0.1 * k, ang + 1.2), z + 3.0 * k, z + 4.9 * k, mat)

def add_statue(mb, x, y, z, rng):
    """Statue ordinaire : socle de pierre et personnage de bronze."""
    ang = rng.uniform(0, 6.28); prism(mb, ngon(x, y, 0.9, 6, ang), z - 0.3, z + 1.6, "pierre")
    figure(mb, x, y, z + 1.6, 0.22, ang, "bronze", arm_up=False)

def add_republique(mb, x, y, z, radius, ang):
    """Monument à la République (Morice, 1883), évocation low-poly : gradins, tambour à frise de bronze,
    fût avec les trois figures assises, lion de bronze, Marianne au rameau d'olivier au sommet (~24 m)."""
    k = max(1.05, radius / 11.0); R = lambda r, n=20: ngon(x, y, r * k, n, ang)      # ~25 m de haut comme l'original
    for r, h in ((11.0, 0.35), (10.0, 0.7), (9.0, 1.05)): prism(mb, R(r), z - 0.4, z + h * k, "marche")
    prism(mb, R(6.3), z + 1.05 * k, z + 4.2 * k, "pierre", top=False)
    ring_walls(mb, R(6.38), z + 1.7 * k, R(6.38), z + 3.0 * k, "bronze")                       # frise de bas-reliefs
    prism(mb, R(6.7), z + 4.2 * k, z + 4.55 * k, "pierre")
    prism(mb, R(2.7, 14), z + 4.55 * k, z + 11.5 * k, "pierre", top=False)
    for i in range(3):                                                    # Liberté, Égalité, Fraternité assises autour du fût
        a = ang + math.pi + i * 2 * math.pi / 3; cx, cy = x + math.cos(a) * 3.5 * k, y + math.sin(a) * 3.5 * k
        ring_walls(mb, ngon(cx, cy, 1.35 * k, 7, a), z + 4.55 * k, ngon(cx, cy, 0.85 * k, 7, a), z + 7.3 * k, "pierre")
        ring_walls(mb, ngon(cx, cy, 0.85 * k, 7, a), z + 7.3 * k, ngon(cx, cy, 0.3 * k, 7, a), z + 7.7 * k, "pierre")
        prism(mb, ngon(cx, cy, 0.42 * k, 6, a), z + 7.7 * k, z + 8.5 * k, "pierre")
    prism(mb, R(3.2, 14), z + 11.5 * k, z + 12.1 * k, "pierre")
    prism(mb, R(2.95, 14), z + 12.1 * k, z + 12.8 * k, "bronze")                               # guirlande
    prism(mb, R(2.3, 14), z + 12.8 * k, z + 13.3 * k, "bronze")
    figure(mb, x, y, z + 13.3 * k, k, ang, "bronze")
    fx, fy = math.cos(ang), math.sin(ang); lx, ly = x + fx * 8.3 * k, y + fy * 8.3 * k        # lion devant, face à la place
    prism(mb, obox(lx, ly, 1.7 * k, 0.6 * k, ang), z + 1.6 * k, z + 2.7 * k, "bronze")
    for sgn in (-1, 1):
        for t in (-1.2, 1.2): prism(mb, obox(lx + fx * t * k - fy * sgn * 0.4 * k, ly + fy * t * k + fx * sgn * 0.4 * k, 0.22 * k, 0.2 * k, ang), z + 0.7 * k, z + 1.6 * k, "bronze", top=False)
    prism(mb, ngon(lx + fx * 1.9 * k, ly + fy * 1.9 * k, 0.85 * k, 7, ang), z + 2.0 * k, z + 3.5 * k, "bronze")   # tête et crinière

# ---- décor de la Commune (1871) --------------------------------------------------------------
def add_flag(mb, p, n, z, rng):
    """Drapeau rouge sur hampe inclinée, fixé à une façade (p : point du mur, n : normale sortante)."""
    L = rng.uniform(2.2, 2.8); tip = p + n * L; z1 = z + 1.1; t = np.array([-n[1], n[0]]) * 0.03
    mb.face([(p[0] - t[0], p[1] - t[1], z), (p[0] + t[0], p[1] + t[1], z), (tip[0] + t[0], tip[1] + t[1], z1), (tip[0] - t[0], tip[1] - t[1], z1)], "moulin")
    mb.face([(p[0], p[1], z - 0.03), (p[0], p[1], z + 0.03), (tip[0], tip[1], z1 + 0.03), (tip[0], tip[1], z1 - 0.03)], "moulin")
    a = p + n * L * 0.3; za = z + 0.27; m = p + n * L * 0.65 + t * rng.uniform(-7, 7); zm = z + 0.585; d = rng.uniform(1.4, 1.8)
    mb.face([(a[0], a[1], za), (m[0], m[1], zm), (m[0], m[1], zm - d), (a[0], a[1], za - d)], "toile_rouge")
    mb.face([(m[0], m[1], zm), (tip[0], tip[1], z1), (tip[0] - t[0] * 4, tip[1] - t[1] * 4, z1 - d), (m[0], m[1], zm - d)], "toile_rouge")

def add_posters(mb, q, d, n, z, rng):
    """1 à 3 affiches placardées côte à côte sur un mur (q : point du mur, d : direction du mur, n : normale)."""
    k = rng.choice([1, 2, 2, 3, 4]); w, h = 0.95, 1.27
    for i in range(k):
        c = q + d * (i - (k - 1) / 2) * (w + 0.08) + n * 0.05; z0 = z + 1.0 + rng.uniform(-0.05, 0.1); j = rng.randrange(4)
        a, b = c - d * w / 2, c + d * w / 2; u0, u1 = j * 0.1875 + 0.002, (j + 1) * 0.1875 - 0.002
        mb.face([(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z0 + h), (a[0], a[1], z0 + h)], "affiches", [(u0, 0.505), (u1, 0.505), (u1, 0.995), (u0, 0.995)])

def add_stall(mb, x, y, z, ang, rng):
    """Étal de marché : table, caisses de légumes, auvent rayé. L'avant (côté clients) est du côté +perp."""
    ca, sa = math.cos(ang), math.sin(ang); P = lambda a, b: (x + ca * a - sa * b, y + sa * a + ca * b)
    prism(mb, obox(x, y, 1.15, 0.45, ang), z + 0.76, z + 0.84, "moulin")
    for a, b in ((-1.05, -0.38), (1.05, -0.38), (-1.05, 0.38), (1.05, 0.38)):
        px, py = P(a, b); prism(mb, ngon(px, py, 0.04, 4), z - 0.1, z + (2.3 if b < 0 else 1.95), "moulin", top=False)
    for i in range(6):                                                   # auvent rayé rouge et crème
        a0, a1 = -1.2 + i * 0.4, -0.8 + i * 0.4
        q = [P(a0, 0.7), P(a1, 0.7), P(a1, -0.5), P(a0, -0.5)]
        mb.face([(q[0][0], q[0][1], z + 1.9), (q[1][0], q[1][1], z + 1.9), (q[2][0], q[2][1], z + 2.32), (q[3][0], q[3][1], z + 2.32)], "toile_rouge" if i % 2 else "toile_creme")
    for i, m in enumerate(rng.sample(["feuille_a", "feuille_b", "toile_rouge", "brique", "feuille_a", "toile_creme"], 3)):
        cx, cy = P(-0.72 + i * 0.72, 0.0); prism(mb, obox(cx, cy, 0.3, 0.3, ang), z + 0.84, z + 1.0, "moulin", top=False)
        cap(mb, obox(cx, cy, 0.27, 0.27, ang), z + 0.97 + rng.uniform(0, 0.08), m)

def add_barricade(mb, c, d, n, hw, z, rng):
    """Barricade de pavés en travers de la rue (c : point de l'axe, d : sens de la rue, n : travers), passage laissé d'un côté."""
    gap = 1.6; half = max(1.2, (2 * hw - gap) / 2); cc = c - n * (gap / 2); ang = math.atan2(n[1], n[0])
    bot, top = obox(cc[0], cc[1], half, 1.45, ang), obox(cc[0], cc[1], half * 0.93, 0.45, ang)
    ring_walls(mb, bot, z - 0.3, top, z + 1.55, "pave", lambda i, L: [(0, 0), (L / UVU, 0), (L / UVU, 1.2), (0, 1.2)]); cap(mb, top, z + 1.55, "pave", wuv)
    for k in range(rng.choice([2, 3, 4])):                                 # tonneaux et caisses au pied
        t = rng.uniform(-half * 0.85, half * 0.85); sd = rng.choice([-1, 1]) * rng.uniform(1.7, 2.1); q = cc + n * t + d * sd
        if rng.random() < 0.6: prism(mb, ngon(q[0], q[1], 0.36, 8), z - 0.1, z + 0.95, "moulin")
        else: prism(mb, obox(q[0], q[1], 0.45, 0.35, rng.uniform(0, 3.14)), z - 0.1, z + 0.6, "moulin")
    f = cc + n * rng.uniform(-half * 0.4, half * 0.4)
    prism(mb, ngon(f[0], f[1], 0.045, 4), z + 1.5, z + 4.3, "moulin", top=False)
    e = f + n * 1.5
    mb.face([(f[0], f[1], z + 3.3), (e[0], e[1], z + 3.2), (e[0], e[1], z + 4.2), (f[0], f[1], z + 4.3)], "toile_rouge")

def add_banner(mb, c, n, hw, z):
    """Banderole « Vive la Commune » tendue entre deux mâts en travers de la rue."""
    a, b = c + n * (hw - 0.4), c - n * (hw - 0.4)
    for q in (a, b): prism(mb, ngon(q[0], q[1], 0.07, 6), z - 0.3, z + 6.2, "moulin", top=False)
    mb.face([(a[0], a[1], z + 4.9), (b[0], b[1], z + 4.9), (b[0], b[1], z + 5.85), (a[0], a[1], z + 5.85)], "affiches", [(0.0, 0.02), (1.0, 0.02), (1.0, 0.48), (0.0, 0.48)])

def add_rail(mb, P, Z, h=0.95):
    """Main courante : barre + potelets (faces fines double face)."""
    for i in range(len(P) - 1):
        a, b = P[i], P[i + 1]
        mb.face([(a[0], a[1], Z[i] + h - 0.06), (b[0], b[1], Z[i + 1] + h - 0.06), (b[0], b[1], Z[i + 1] + h), (a[0], a[1], Z[i] + h)], "fer")
        d = (b - a) / max(1e-6, float(np.hypot(*(b - a)))) * 0.04
        mb.face([(a[0] - d[0], a[1] - d[1], Z[i] - 0.1), (a[0] + d[0], a[1] + d[1], Z[i] - 0.1), (a[0] + d[0], a[1] + d[1], Z[i] + h), (a[0] - d[0], a[1] - d[1], Z[i] + h)], "fer")

def to_object(name, mb, mats):
    me = bpy.data.meshes.new(name); me.from_pydata(mb.v, [], mb.f)
    for mn in mb.mats: me.materials.append(mats[mn])
    me.polygons.foreach_set("material_index", mb.m)
    uv = me.uv_layers.new(name="UVMap"); uv.data.foreach_set("uv", [c for f in mb.uv for p in f for c in p])
    me.update()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob); return ob

# ---------------------------------------------------------------------------------------------
def main():
    a = parse_args(); rng = random.Random(a.seed)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    out = os.path.abspath(a.out); os.makedirs(out, exist_ok=True)
    matdir = os.path.join(os.path.dirname(out), "materiaux")
    for f in os.listdir(out):
        if f.endswith(".glb") or f.endswith(".glb.import"): os.remove(os.path.join(out, f))

    nodes, node_tags, ways, rels, (la0, lo0, la1, lo1), covers = parse_many(a.osm)
    latc, lonc = (la0 + la1) / 2, (lo0 + lo1) / 2
    kx, ky = 111320.0 * math.cos(math.radians(latc)), 110574.0
    proj = lambda lat, lon: ((lon - lonc) * kx, (lat - latc) * ky)
    xmin, ymin = proj(la0, lo0); xmax, ymax = proj(la1, lo1)
    inb = lambda x, y, m=0.0: xmin - m <= x <= xmax + m and ymin - m <= y <= ymax + m
    wpts = lambda refs: np.array([proj(*nodes[r]) for r in refs if r in nodes])
    cover_m = [(*proj(c[0], c[1]), *proj(c[2], c[3])) for c in covers]
    def closed(refs):
        if len(refs) < 4 or refs[0] != refs[-1]: return None
        p = wpts(refs[:-1])
        if len(p) < 3: return None
        p = p[[i for i in range(len(p)) if np.hypot(*(p[i] - p[i - 1])) > 0.05]]
        if len(p) < 3 or abs(area2(p)) < 2: return None
        return p[::-1].copy() if area2(p) < 0 else p

    slat, slon = map(float, a.summit.split(",")); rx, ry = map(float, a.hill_radius.split(","))
    G = Ground(proj(slat, slon), (rx, ry), a.alt_base, a.alt_top)

    # ---- tri des éléments OSM ----------------------------------------------------------------
    streets, plazas, greens, blds, barriers, rails, props, waters = [], [], [], [], [], [], [], []
    def building(poly, t, wid):
        if poly is None: return
        # couloirs et salles de métro cartographiés en sous-sol : rien à construire en surface
        if t.get("location") == "underground" or (num(t.get("layer"), 0) or 0) < 0 or t.get("tunnel") == "yes": return
        if t.get("building:part") in ("corridor", "room", "verticalpassage") and t.get("building") is None: return
        year = num(t.get("start_date", "")[:4])
        if a.year and year and year > a.year: return
        c = poly.mean(0)
        if not inb(c[0], c[1]): return
        kind = t.get("building", t.get("building:part", "yes"))
        monument = kind in ("church", "cathedral", "basilica", "chapel", "temple") or t.get("amenity") == "place_of_worship"
        h = num(t.get("height")); lv = num(t.get("building:levels")); hr = random.Random(wid)
        if h is None:
            if lv is not None: h = (lv + (num(t.get("roof:levels")) or 0)) * LEVEL_H + 0.6
            elif abs(area2(poly)) / 2 < 30: h = 3.2
            else: h = hr.choice([4, 5, 5, 6]) * LEVEL_H + 0.6
        minh = num(t.get("min_height")) or (num(t.get("building:min_level")) or 0) * LEVEL_H
        blds.append(dict(poly=poly, h=max(2.5, h), minh=minh, part="building:part" in t, id=wid,
                         roof=t.get("roof:shape", "flat"), roofh=num(t.get("roof:height"), 0) or 0,
                         facade=not monument, mat="pierre", ci=hr.randrange(4)))
    for wid, (refs, t) in ways.items():
        hw = t.get("highway")
        if "building" in t or "building:part" in t:
            building(closed(refs), t, wid); continue
        if t.get("tourism") == "artwork" and t.get("artwork_type") in ("statue", "sculpture", "bust") and "building" not in t:
            p = wpts(refs)
            if len(p) and inb(*p.mean(0), -5):
                c = p.mean(0)
                if "Monument à la République" in t.get("name", ""):
                    props.append(("republique", c[0], c[1], wid, float(np.clip(np.linalg.norm(p - c, axis=1).mean(), 8, 16))))
                else: props.append(("statue", c[0], c[1], wid))
            continue
        if t.get("man_made") == "windmill" or t.get("attraction") == "carousel" or t.get("amenity") == "fountain":
            p = wpts(refs)
            if len(p): props.append(("windmill" if t.get("man_made") else "carousel" if t.get("attraction") else "fountain", *p.mean(0), wid))
            continue
        if t.get("natural") == "water" and t.get("tunnel") != "yes":
            p = closed(refs)
            if p is not None and inb(*p.mean(0)): waters.append((p, t.get("water") in ("canal", "river", "basin", "lock")))
            continue
        if t.get("barrier") in ("wall", "retaining_wall", "fence", "city_wall"):
            p = wpts(refs)
            if len(p) >= 2: barriers.append((p, t["barrier"]))
            continue
        if t.get("railway") == "funicular" and t.get("tunnel") != "yes":
            p = wpts(refs)
            if len(p) >= 2: rails.append(p)
            continue
        is_area = t.get("area") == "yes" or t.get("place") == "square"
        if (hw in PEDESTRIAN and is_area) or t.get("place") == "square":
            p = closed(refs)
            if p is not None:
                hh = G.nat(p[:, 0], p[:, 1])
                if hh.max() - hh.min() < 2.0: plazas.append(p)
                else: greens.append((p, "dalle"))
            continue
        if any((k, t.get(k)) in GREEN_TAGS for k in ("leisure", "landuse", "natural", "amenity")):
            p = closed(refs)
            if p is not None: greens.append((p, "vigne" if t.get("landuse") == "vineyard" else "herbe"))
            continue
        if hw in HIGHWAY_WIDTH and t.get("tunnel") not in ("yes", "building_passage") \
                and t.get("footway") not in ("sidewalk", "crossing") and t.get("layer", "0") not in ("-1", "-2"):
            p = wpts(refs)
            if len(p) >= 2:
                ok = [r for r in refs if r in nodes]
                streets.append(dict(pts=p, w=num(t.get("width")), dw=HIGHWAY_WIDTH[hw], steps=hw == "steps", name=t.get("name", ""),
                                    bridge=t.get("bridge", "no") != "no", ends=(ok[0], ok[-1]),
                                    hw=hw, mat="marche" if hw == "steps" else "dalle" if hw in PEDESTRIAN else "pave"))
    for members, t in rels:
        if t.get("type") != "multipolygon": continue
        if "building" in t or "building:part" in t:
            for typ, ref, role in members:
                if typ == "way" and role in ("outer", "") and ref in ways: building(closed(ways[ref][0]), t, ref)
        elif any((k, t.get(k)) in GREEN_TAGS for k in ("leisure", "landuse", "natural", "amenity")):
            for typ, ref, role in members:
                if typ == "way" and role in ("outer", "") and ref in ways:
                    p = closed(ways[ref][0])
                    if p is not None: greens.append((p, "vigne" if t.get("landuse") == "vineyard" else "herbe"))
    for mon in [b for b in blds if not b["facade"] and not b["part"]]:
        for b in blds:
            if b["part"] and b["facade"] and pip(b["poly"].mean(0)[None], mon["poly"])[0]: b["facade"] = False
    parts = np.array([b["poly"].mean(0) for b in blds if b["part"]]).reshape(-1, 2)
    if len(parts): blds = [b for b in blds if b["part"] or not pip(parts, b["poly"]).any()]
    for b in blds:
        if b["part"] or b["minh"] > 0 or b["roof"] in ("dome", "onion", "pyramidal", "cone"): b["facade"] = False if not b["facade"] else b["facade"] and not (b["minh"] > 0 or b["roof"] in ("dome", "onion", "pyramidal", "cone"))
    trees = []
    for i, t in node_tags.items():
        if i not in nodes: continue
        x, y = proj(*nodes[i])
        if not inb(x, y, -3): continue
        if t.get("natural") == "tree": trees.append((x, y))
        elif t.get("highway") == "street_lamp": props.append(("lamp", x, y, i))
        elif t.get("amenity") == "bench": props.append(("bench", x, y, i, math.radians(90 - (num(t.get("direction"), None) or random.Random(i).uniform(0, 360)))))
        elif t.get("amenity") == "drinking_water": props.append(("wallace", x, y, i))
        elif t.get("amenity") == "fountain": props.append(("fountain", x, y, i))
        elif t.get("man_made") == "windmill": props.append(("windmill", x, y, i))
        elif t.get("attraction") == "carousel": props.append(("carousel", x, y, i))
        elif t.get("tourism") == "artwork" and t.get("artwork_type") in ("statue", "bust"): props.append(("statue", x, y, i))

    # ---- largeur réelle des rues : distance aux façades les plus proches ----------------------
    BE = np.array([(*b["poly"][i], *b["poly"][(i + 1) % len(b["poly"])]) for b in blds if b["minh"] == 0 for i in range(len(b["poly"]))]).reshape(-1, 4)
    for s in streets:
        if s["w"] is None:
            s["w"] = s["dw"]
            if len(BE) and s["hw"] not in ("footway", "path", "cycleway", "steps", "service"):
                d = seg_dist(resample(s["pts"], 8.0), BE, cutoff=s["dw"] * 1.7)
                d = d[d < s["dw"] * 1.6]
                if len(d) >= 2: s["w"] = float(np.clip(2 * np.percentile(d, 30) - 0.3, 3.0, s["dw"] * 2.2))
        s["w"] = max(1.5, s["w"])
    for s in streets: G.add_line(s["pts"], s["w"] / 2)
    plaza_h = [G.add_plaza(p) for p in plazas]
    water_lvl = []                                                        # eau : niveau = quai - 1 m (canal) ou - 0,15 m (bassin)
    for poly, canal in waters:
        q = float(G.h(poly).min()); water_lvl.append(q - (1.0 if canal else 0.15))
    for (poly, canal), lvl in zip(waters, water_lvl): G.pits.append((poly, lvl - (1.2 if canal else 0.35)))
    # ponts et passerelles : les nœuds qui ne touchent aucune voie "au sol" sont en hauteur (tablier de passerelle)
    ground_nodes = {r for s in streets if not s["bridge"] for r in s["ends"]} | {r for s in streets if not s["bridge"] for r in ()}
    for wid_, (refs_, t_) in ways.items():
        if t_.get("highway") in HIGHWAY_WIDTH and t_.get("bridge", "no") == "no": ground_nodes.update(refs_)
    def elev(ref):
        x, y = proj(*nodes[ref]); return float(G.h([(x, y)])[0]) + (0.0 if ref in ground_nodes else 3.2)
    # segments de chaussée, pour savoir si un point tombe sur une AUTRE rue (carrefours)
    SA = np.array([(*p0, *p1, s["w"] / 2, i) for i, s in enumerate(streets) if not s["steps"] and s["w"] >= 3
                   for p0, p1 in zip(s["pts"][:-1], s["pts"][1:])]).reshape(-1, 6)
    def on_other_street(P, sid, margin=0.3):
        A = SA[SA[:, 5] != sid]
        return seg_dist(P, A[:, :4], A[:, 4], cutoff=1.0) < -margin
    BLO = np.array([b["poly"].min(0) - 0.3 for b in blds]).reshape(-1, 2); BHI = np.array([b["poly"].max(0) + 0.3 for b in blds]).reshape(-1, 2)
    def in_building(P):
        P = np.asarray(P, float).reshape(-1, 2); m = np.zeros(len(P), bool)
        if not len(P) or not len(blds): return m
        d = seg_dist(P, BE, cutoff=4.5); idx = np.where(d < 4.0)[0]
        for i0 in range(0, len(idx), 400):                                # par paquets : seuls les bâtiments voisins sont testés
            sub = idx[i0:i0 + 400]; pmin, pmax = P[sub].min(0), P[sub].max(0)
            for bi in np.where((BHI[:, 0] > pmin[0]) & (BLO[:, 0] < pmax[0]) & (BHI[:, 1] > pmin[1]) & (BLO[:, 1] < pmax[1]))[0]:
                sel = sub[(P[sub, 0] > BLO[bi, 0]) & (P[sub, 0] < BHI[bi, 0]) & (P[sub, 1] > BLO[bi, 1]) & (P[sub, 1] < BHI[bi, 1])]
                if len(sel): m[sel] |= pip(P[sel], blds[bi]["poly"])
        return m | (d < 0.35)

    # ---- zones ---------------------------------------------------------------------------------
    nzx = max(1, round((xmax - xmin) / a.zone_size)); nzy = max(1, round((ymax - ymin) / a.zone_size))
    zw, zh = (xmax - xmin) / nzx, (ymax - ymin) / nzy
    zone = lambda x, y: (min(nzx - 1, max(0, int((x - xmin) / zw))), min(nzy - 1, max(0, int((y - ymin) / zh))))
    zname = lambda z: f"zone_{chr(65 + z[0])}{z[1] + 1}"
    builders = {}
    mb = lambda z, cat: builders.setdefault((z, cat), MB())

    # ---- terrain -------------------------------------------------------------------------------
    nx, ny = int(math.ceil((xmax - xmin) / a.cell)), int(math.ceil((ymax - ymin) / a.cell))
    xs, ys = np.linspace(xmin, xmax, nx + 1), np.linspace(ymin, ymax, ny + 1)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    H = G.h(np.stack([X.ravel(), Y.ravel()], 1)).reshape(nx + 1, ny + 1)
    cc = np.stack([(X[:-1, :-1] + X[1:, 1:]).ravel() / 2, (Y[:-1, :-1] + Y[1:, 1:]).ravel() / 2], 1)
    names = ["sol", "herbe", "vigne", "dalle", "trottoir"]; cmat = np.zeros(len(cc), int)
    if len(SA): cmat[seg_dist(cc, SA[:, :4], SA[:, 4], cutoff=5.5) < 5.0] = 4          # abords des rues : asphalte jusqu'aux façades, pas de terre nue
    for poly, m in greens: cmat[pip(cc, poly)] = names.index(m)
    covered = np.zeros(len(cc), bool)                                     # hors de tout export : sol neutre "plaine"
    for x0_, y0_, x1_, y1_ in cover_m: covered |= (cc[:, 0] >= x0_) & (cc[:, 0] <= x1_) & (cc[:, 1] >= y0_) & (cc[:, 1] <= y1_)
    names.append("plaine"); cmat[~covered] = len(names) - 1
    cmat = cmat.reshape(nx, ny)
    for i in range(nx):
        for j in range(ny):
            b = mb(zone(*cc[i * ny + j]), "terrain"); m = names[cmat[i, j]]
            p = [(xs[i], ys[j], H[i, j]), (xs[i + 1], ys[j], H[i + 1, j]), (xs[i + 1], ys[j + 1], H[i + 1, j + 1]), (xs[i], ys[j + 1], H[i, j + 1])]
            for tri in (((0, 1, 2), (0, 2, 3)) if (i + j) % 2 else ((0, 1, 3), (1, 2, 3))):
                q = [p[k] for k in tri]; b.face(q, m, wuv(q))

    # ---- rues, trottoirs, escaliers, réverbères ---------------------------------------------------
    lamps = [(p[1], p[2]) for p in props if p[0] == "lamp"]
    for si, s in enumerate(streets):
        hw = s["w"] / 2
        if s["bridge"]:
            P = resample(s["pts"], STEP_LEN if s["steps"] else 3.0); n = len(P)
            if n < 2 or not all(inb(*q) for q in P): continue
            d = np.r_[0, np.cumsum(np.hypot(*np.diff(P, axis=0).T))]; e0, e1 = elev(s["ends"][0]), elev(s["ends"][1])
            Z = e0 + (e1 - e0) * d / max(1e-6, d[-1]) + 0.12
            N = normals2d(P); bw = max(hw, 1.0); L, R = P + N * bw, P - N * bw
            zz = zone(*P[n // 2]); bv, bc = mb(zz, "ponts_NOCOL"), mb(zz, "ponts_COLONLY")
            mat = "vert_paris" if (s["hw"] in PEDESTRIAN or s["steps"]) else "trottoir"
            for i in range(n - 1):
                zt = max(Z[i], Z[i + 1]); q = np.array([L[i], R[i], R[i + 1], L[i + 1]])
                if area2(q) < 0: q = q[::-1]
                prism(bv, q, zt - 0.25, zt, mat); bv.face([(p_[0], p_[1], zt - 0.25) for p_ in q[::-1]], mat)
                bc.face([(L[i][0], L[i][1], Z[i]), (R[i][0], R[i][1], Z[i]), (R[i + 1][0], R[i + 1][1], Z[i + 1]), (L[i + 1][0], L[i + 1][1], Z[i + 1])], "fer")
            Q = resample(s["pts"], 2.0); dq = np.r_[0, np.cumsum(np.hypot(*np.diff(Q, axis=0).T))]; ZQ = e0 + (e1 - e0) * dq / max(1e-6, dq[-1]) + 0.12
            NQ = normals2d(Q)
            for o in (bw - 0.05, -(bw - 0.05)): add_rail(bv, Q + NQ * o, ZQ, 1.05)
            continue
        if s["steps"]:
            P = resample(s["pts"], STEP_LEN); N = normals2d(P)
            if len(P) < 2: continue
            hc = G.h(P); L, R = P + N * hw, P - N * hw; prev = None
            for i in range(len(P) - 1):
                if not inb(*P[i]): prev = None; continue
                z = max(hc[i], hc[i + 1]) + 0.07; b = mb(zone(*P[i]), "sol_NOCOL")
                b.face([(L[i][0], L[i][1], z), (R[i][0], R[i][1], z), (R[i + 1][0], R[i + 1][1], z), (L[i + 1][0], L[i + 1][1], z)], "marche")
                if prev is not None and abs(prev - z) > 0.01:
                    b.face([(L[i][0], L[i][1], prev), (R[i][0], R[i][1], prev), (R[i][0], R[i][1], z), (L[i][0], L[i][1], z)], "marche")
                prev = z
            if s["w"] >= 2.5:                                          # mains courantes
                Q = resample(s["pts"], 2.4); NQ = normals2d(Q); offs = [hw - 0.15, -(hw - 0.15)] + ([0.0] if s["w"] >= 5 else [])
                for o in offs:
                    R2 = Q + NQ * o; keep = np.array([inb(*q) for q in R2])
                    if keep.all() and len(R2) >= 2: add_rail(mb(zone(*R2[len(R2) // 2]), "decor_NOCOL"), R2, G.h(R2) + 0.25)
            continue
        P = resample(s["pts"], 3.0); N = normals2d(P)
        L, R = P + N * hw, P - N * hw
        off = 0.08 + 0.0015 * (si % 7)
        zl, zc, zr = G.h(L) + off, G.h(P) + off, G.h(R) + off
        V = lambda A, Z, i: (A[i][0], A[i][1], Z[i])
        sw = float(np.clip(hw * 0.28, 0.9, 2.2)) if (s["mat"] == "pave" and hw >= 3.0 and s["hw"] != "service") else 0.0
        if sw:
            SL, SR = P + N * (hw - sw), P - N * (hw - sw)
            zsl, zsr = G.h(SL) + off, G.h(SR) + off
            okL = ~on_other_street((L + SL) / 2, si); okR = ~on_other_street((R + SR) / 2, si)
        for i in range(len(P) - 1):
            mid = (P[i] + P[i + 1]) / 2
            if not inb(*mid): continue
            b = mb(zone(*mid), "sol_NOCOL")
            for q in ([V(L, zl, i), V(P, zc, i), V(P, zc, i + 1), V(L, zl, i + 1)], [V(P, zc, i), V(R, zr, i), V(R, zr, i + 1), V(P, zc, i + 1)]):
                b.face(q, s["mat"], wuv(q))
            if sw:
                k = 0.13
                if okL[i] and okL[i + 1]:
                    q = [(L[i][0], L[i][1], zl[i] + k), (SL[i][0], SL[i][1], zsl[i] + k), (SL[i + 1][0], SL[i + 1][1], zsl[i + 1] + k), (L[i + 1][0], L[i + 1][1], zl[i + 1] + k)]; b.face(q, "trottoir", wuv(q))
                    q = [(SL[i][0], SL[i][1], zsl[i] + k), (SL[i][0], SL[i][1], zsl[i]), (SL[i + 1][0], SL[i + 1][1], zsl[i + 1]), (SL[i + 1][0], SL[i + 1][1], zsl[i + 1] + k)]; b.face(q, "trottoir", wuv(q))
                if okR[i] and okR[i + 1]:
                    q = [(SR[i][0], SR[i][1], zsr[i] + k), (R[i][0], R[i][1], zr[i] + k), (R[i + 1][0], R[i + 1][1], zr[i + 1] + k), (SR[i + 1][0], SR[i + 1][1], zsr[i + 1] + k)]; b.face(q, "trottoir", wuv(q))
                    q = [(SR[i + 1][0], SR[i + 1][1], zsr[i + 1] + k), (SR[i + 1][0], SR[i + 1][1], zsr[i + 1]), (SR[i][0], SR[i][1], zsr[i]), (SR[i][0], SR[i][1], zsr[i] + k)]; b.face(q, "trottoir", wuv(q))
        if s["hw"] not in ("footway", "path", "cycleway", "service") and s["w"] >= 3.5:   # réverbères tous les ~28 m, en quinconce
            Q = resample(s["pts"], 28.0); NQ = normals2d(Q)
            C = np.array([Q[i] + NQ[i] * (hw - 0.55) * (1 if i % 2 else -1) for i in range(len(Q))])
            bad = on_other_street(C, si, 0.0) | in_building(C)
            for c, bd_ in zip(C, bad):
                if not bd_ and inb(*c, -2) and all((c[0] - l[0]) ** 2 + (c[1] - l[1]) ** 2 > 144 for l in lamps[-400:]): lamps.append((c[0], c[1]))
    for poly, h in zip(plazas, plaza_h):
        c = poly.mean(0)
        if inb(*c): cap(mb(zone(*c), "sol_NOCOL"), poly, h + 0.12, "dalle", wuv)
    for (poly, canal), lvl in zip(waters, water_lvl):                       # plans d'eau
        cap(mb(zone(*poly.mean(0)), "eau"), poly, lvl, "eau")
    for p in rails:                                                     # funiculaire : deux rails sombres
        P = resample(p, 3.0); N = normals2d(P)
        for o in (-0.75, 0.75):
            Aa, Bb = P + N * (o - 0.08), P + N * (o + 0.08); za, zb = G.h(Aa) + 0.2, G.h(Bb) + 0.2
            for i in range(len(P) - 1):
                if inb(*P[i]): mb(zone(*P[i]), "sol_NOCOL").face([(Aa[i][0], Aa[i][1], za[i]), (Bb[i][0], Bb[i][1], zb[i]), (Bb[i + 1][0], Bb[i + 1][1], zb[i + 1]), (Aa[i + 1][0], Aa[i + 1][1], za[i + 1])], "fer")

    # ---- bâtiments, murs --------------------------------------------------------------------------
    for bd in blds:
        c = bd["poly"].mean(0); b = mb(zone(*c), "batiments"); g = G.h(bd["poly"])
        bd["gref"] = float(g.mean())
        if bd["facade"]: add_building(b, bd["poly"], g, bd, random.Random(bd["id"]))
        else: add_monument(b, bd["poly"], g, bd)
    for p, kind in barriers:
        P = resample(p, 4.0)
        if not all(inb(*q) for q in P): continue
        Z = G.h(P)
        if kind == "fence": add_rail(mb(zone(*P[len(P) // 2]), "decor_NOCOL"), P, Z, 1.3); continue
        N = normals2d(P); A_, B_ = P + N * 0.2, P - N * 0.2; hgt = 2.4 if kind == "retaining_wall" else 1.9
        b = mb(zone(*P[len(P) // 2]), "batiments")
        for i in range(len(P) - 1):
            z0, z1 = min(Z[i], Z[i + 1]) - 0.6, max(Z[i], Z[i + 1]) + hgt
            q = np.array([B_[i], B_[i + 1], A_[i + 1], A_[i]]); prism(b, q if area2(q) > 0 else q[::-1], z0, z1, "mur", uvf=lambda k, L, z0=z0, z1=z1, o=i * 4.0: [(o / UVU, z0 / UVU), ((o + L) / UVU, z0 / UVU), ((o + L) / UVU, z1 / UVU), (o / UVU, z1 / UVU)])

    # ---- décor de la Commune (option --commune) : objets "commune" masquables dans Godot ---------------
    barricades, spots = [], {}
    if a.commune and len(SA):
        crng = random.Random(a.seed + 71)
        M, Nn, Dd, Zz, Ll = [], [], [], [], []                              # arêtes de façade donnant sur une rue
        for bd in blds:
            if not bd["facade"] or bd["minh"] > 0 or "gref" not in bd: continue
            p = bd["poly"]; q = np.roll(p, -1, 0); e = q - p; L = np.linalg.norm(e, axis=1); ok = L >= 4.0
            if not ok.any(): continue
            dd = e[ok] / L[ok, None]; M.append((p[ok] + q[ok]) / 2); Dd.append(dd); Nn.append(np.stack([dd[:, 1], -dd[:, 0]], 1))
            Zz.append(np.full(int(ok.sum()), bd["gref"])); Ll.append(L[ok])
        if M:
            M, Nn, Dd, Zz, Ll = (np.concatenate(v) for v in (M, Nn, Dd, Zz, Ll))
            good = (seg_dist(M + Nn * 2.0, SA[:, :4], SA[:, 4], cutoff=2.5) < 1.5) & ~in_building(M + Nn * 0.8)
            for i in np.where(good)[0]:
                if not inb(*M[i], -3): continue
                b = mb(zone(*M[i]), "commune_NOCOL")
                for k in range(max(1, int(Ll[i] // 7))):                    # un emplacement tous les ~7 m de façade
                    r = crng.random(); q = M[i] + Dd[i] * ((k + 0.5) / max(1, int(Ll[i] // 7)) - 0.5) * Ll[i] * 0.9
                    if r < 0.16: add_flag(b, q, Nn[i], Zz[i] + crng.choice([4.3, 4.6, 7.4]), crng)
                    elif r < 0.44:
                        add_posters(b, q, Dd[i], Nn[i], Zz[i], crng); spots.setdefault("affiches", (q, Nn[i]))
        for si, s in enumerate(streets):
            if s["steps"] or s["bridge"] or s["hw"] in ("footway", "path", "cycleway", "service"): continue
            P = resample(s["pts"], 2.0); n_ = len(P)
            if n_ < 8: continue
            N = normals2d(P); hw = s["w"] / 2; ped = s["mat"] == "dalle"; length = 2.0 * (n_ - 1)
            for i in range(4, n_ - 4, 7):                                    # étalages, tous les ~14 m
                if crng.random() < (0.45 if ped else 0.10):
                    sd = crng.choice([-1, 1]); c = P[i] + N[i] * sd * max(0.8, hw - (1.3 if ped else 0.9))
                    if inb(*c, -3) and not on_other_street(c[None], si, 0.0)[0] and not in_building(c[None])[0]:
                        ang = math.atan2(N[i][1] * -sd, N[i][0] * -sd) - math.pi / 2
                        add_stall(mb(zone(*c), "commune_NOCOL"), c[0], c[1], float(G.h(c[None])[0]) + 0.1, ang, crng)
                        if ped: spots.setdefault("etalage", (c, -N[i] * sd))
            if length > 90 and s["w"] >= 5 and crng.random() < 0.22:        # banderole
                i = int(n_ * crng.uniform(0.3, 0.7))
                if inb(*P[i], -6) and not on_other_street(P[i][None], si, -3.0)[0]:
                    add_banner(mb(zone(*P[i]), "commune_NOCOL"), P[i], N[i], min(hw, 7.0), float(G.h(P[i][None])[0]))
                    t_ = P[i + 1] - P[i - 1]; spots.setdefault("banderole", (P[i], t_ / max(1e-6, float(np.hypot(*t_)))))
            if length > 110 and not ped and 5 <= s["w"] <= 22 and crng.random() < 0.16 and len(barricades) < 60:   # barricade près d'un bout de rue
                i = 6 if crng.random() < 0.5 else n_ - 7
                if inb(*P[i], -8) and not on_other_street(P[i][None], si, -4.0)[0] and all(np.hypot(*(P[i] - q)) > 70 for q, _ in barricades):
                    d_ = P[i + 1] - P[i - 1]; d_ = d_ / max(1e-6, float(np.hypot(*d_)))
                    add_barricade(mb(zone(*P[i]), "commune"), P[i], d_, N[i], min(hw, 9.0), float(G.h(P[i][None])[0]), crng)
                    barricades.append((P[i], d_))

    # ---- arbres et mobilier ----------------------------------------------------------------------
    if trees:
        T = np.array(trees); keep = ~in_building(T)
        for (x, y), z in zip(T[keep], G.h(T[keep])): add_tree(mb(zone(x, y), "decor_NOCOL"), x, y, z, rng)
    tx, ty = proj(48.88650, 2.34080)                                    # parasols de la place du Tertre
    if inb(tx, ty, -20):
        placed = []
        for k in range(400):
            r, an = rng.uniform(3, 13), rng.uniform(0, 6.28); p = (tx + r * math.cos(an), ty + r * math.sin(an))
            if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 > 12 for q in placed + trees) and len(placed) < 14: placed.append(p)
        props += [("parasol", p[0], p[1], i) for i, p in enumerate(placed)]
    props += [("lamp_gen", x, y, 0) for x, y in lamps[sum(1 for p in props if p[0] == "lamp"):]]
    lamp_pos = []
    if props:
        PP = np.array([(p[1], p[2]) for p in props]); PZ = G.h(PP); inside = in_building(PP)
        for p, z, ib in zip(props, PZ, inside):
            kind, x, y = p[0], p[1], p[2]; b = mb(zone(x, y), "decor_NOCOL")
            if ib and kind not in ("windmill",): continue
            if kind in ("lamp", "lamp_gen"): add_lamp(b, x, y, z); lamp_pos.append([round(x, 2), round(float(z) + 3.6, 2), round(-y, 2)])
            elif kind == "bench": add_bench(b, x, y, z, p[4])
            elif kind == "wallace": add_wallace(b, x, y, z)
            elif kind == "fountain": add_fountain(b, x, y, z)
            elif kind == "carousel": add_carousel(b, x, y, z)
            elif kind == "windmill": add_windmill(b, x, y, z + 6.0 if ib else z, random.Random(p[3]))
            elif kind == "parasol": add_parasol(b, x, y, z + 0.12, p[3])
            elif kind == "statue": add_statue(mb(zone(x, y), "batiments"), x, y, z, random.Random(p[3]))
            elif kind == "republique": add_republique(mb(zone(x, y), "batiments"), x, y, z + 0.1, p[4], math.radians(250))   # tournée vers le sud-ouest (approx.)

    # ---- horizon : tablier autour du terrain, plaine, silhouette lointaine --------------------------
    far, sky = MB(), MB(); zf = a.alt_base - 0.4; D = 45.0
    for i in range(nx):
        far.face([(xs[i], ymin - D, zf), (xs[i + 1], ymin - D, zf), (xs[i + 1], ymin, H[i + 1, 0]), (xs[i], ymin, H[i, 0])], "plaine")
        far.face([(xs[i], ymax, H[i, ny]), (xs[i + 1], ymax, H[i + 1, ny]), (xs[i + 1], ymax + D, zf), (xs[i], ymax + D, zf)], "plaine")
    for j in range(ny):
        far.face([(xmin - D, ys[j], zf), (xmin, ys[j], H[0, j]), (xmin, ys[j + 1], H[0, j + 1]), (xmin - D, ys[j + 1], zf)], "plaine")
        far.face([(xmax, ys[j], H[nx, j]), (xmax + D, ys[j], zf), (xmax + D, ys[j + 1], zf), (xmax, ys[j + 1], H[nx, j + 1])], "plaine")
    for (cx, cy, hx, hy) in ((xmin, ymin, H[0, 0], 0), (xmax, ymin, H[nx, 0], 0), (xmax, ymax, H[nx, ny], 0), (xmin, ymax, H[0, ny], 0)):
        sx, sy = (-1 if cx == xmin else 1), (-1 if cy == ymin else 1)
        q = [(cx, cy, hx), (cx + sx * D, cy, zf), (cx + sx * D, cy + sy * D, zf), (cx, cy + sy * D, zf)]
        far.face(q if sx * sy > 0 else q[::-1], "plaine")
    E = 7000.0; x0, x1, y0, y1 = xmin - D, xmax + D, ymin - D, ymax + D
    for q in ([(x0 - E, y0 - E), (x1 + E, y0 - E), (x1 + E, y0), (x0 - E, y0)], [(x0 - E, y1), (x1 + E, y1), (x1 + E, y1 + E), (x0 - E, y1 + E)],
              [(x0 - E, y0), (x0, y0), (x0, y1), (x0 - E, y1)], [(x1, y0), (x1 + E, y0), (x1 + E, y1), (x1, y1)]):
        far.face([(p[0], p[1], zf) for p in q], "plaine")
    for k in range(900):
        d = D + 30 + rng.random() ** 1.5 * 2200; side = rng.randrange(4); t = rng.uniform(-0.6, 1.6)
        x = (xmin + t * (xmax - xmin)) if side < 2 else (xmin - d if side == 2 else xmax + d)
        y = (ymin - d if side == 0 else ymax + d) if side < 2 else (ymin + t * (ymax - ymin))
        wdt, dpt, hgt = rng.uniform(18, 60), rng.uniform(14, 40), rng.uniform(14, 26) + (rng.uniform(10, 30) if rng.random() < 0.06 else 0)
        m = "lointain_a" if k % 2 else "lointain_b"
        prism(sky, obox(x, y, wdt / 2, dpt / 2, rng.uniform(0, 3.14)), zf - 1, zf + hgt * (0.55 if side in (1,) else 1.0), m)

    # ---- objets Blender + export .glb --------------------------------------------------------------
    mats, mat_table = make_materials(matdir, random.Random(a.seed), os.path.abspath(a.textures))
    zones, total = [], 0
    def export(name, objs):
        bpy.ops.object.select_all(action="DESELECT")
        for ob in objs: ob.select_set(True)
        path = os.path.join(out, name + ".glb")
        bpy.ops.export_scene.gltf(filepath=path, export_format="GLB", use_selection=True, export_yup=True, export_apply=True, export_image_format="NONE")
        return os.path.getsize(path) // 1024
    for z in sorted({k[0] for k in builders}):
        obs = [to_object(f"{zname(z)}_{cat}", b, mats) for (zz, cat), b in builders.items() if zz == z and b.f]
        tr = sum(b.tris() for (zz, _), b in builders.items() if zz == z); total += tr
        kb = export(zname(z), obs)
        zones.append(dict(name=zname(z), file=zname(z) + ".glb", triangles=tr, center=[xmin + (z[0] + .5) * zw, 0, -(ymin + (z[1] + .5) * zh)], size=[zw, zh]))
        print(f"  {zname(z)}.glb  {tr} triangles  {kb} Ko")
    export("lointain", [to_object("lointain_sol", far, mats), to_object("lointain_horizon_NOCOL", sky, mats)])
    zones.append(dict(name="lointain", file="lointain.glb", triangles=far.tris() + sky.tris(), center=[0, 0, 0], size=[0, 0]))
    total += far.tris() + sky.tris()

    # ---- world.json -----------------------------------------------------------------------------------
    views = []
    def view(name, fx, fy, tx_, ty_, up_from=1.7, up_to=1.7):
        if not inb(tx_, ty_): return
        fz = float(G.h([(fx, fy)])[0]) + up_from; tz = float(G.h([(tx_, ty_)])[0]) + up_to
        views.append(dict(name=name, pos=[fx, fz, -fy], target=[tx_, tz, -ty_]))
    view_ll = lambda name, frm, to, uf=1.7, ut=1.7: view(name, *proj(*frm), *proj(*to), uf, ut)
    def view_street(name, street, uphill=True, skip=2):
        c = [st["pts"] for st in streets if st["name"] == street and len(st["pts"]) >= 2 and inb(*st["pts"][0]) and inb(*st["pts"][-1])]
        if not c: return
        P = resample(max(c, key=lambda q: float(np.hypot(*np.diff(q, axis=0).T).sum())), 2.0)
        if (G.h(P[:1])[0] > G.h(P[-1:])[0]) == uphill: P = P[::-1]
        i = min(skip, len(P) - 2); j = min(len(P) - 1, i + 15)
        view(name, P[i][0], P[i][1], P[j][0], P[j][1], 1.7, 3.0)
    view_ll("place_du_tertre", (48.88645, 2.34055), (48.88670, 2.34200), 1.7, 12)
    view_ll("parvis_vue_sur_paris", (48.88600, 2.34300), (48.88380, 2.34320), 1.7, 0)
    view_ll("square_louise_michel", (48.88440, 2.34325), (48.88680, 2.34300), 1.7, 50)
    for nm, st, up in [("rue_du_chevalier_de_la_barre", "Rue du Chevalier de la Barre", True), ("rue_foyatier", "Rue Foyatier", True),
                       ("rue_des_saules", "Rue des Saules", True), ("rue_norvins", "Rue Norvins", True), ("rue_lepic", "Rue Lepic", True),
                       ("rue_des_abbesses", "Rue des Abbesses", True), ("rue_de_l_abreuvoir", "Rue de l'Abreuvoir", True)]:
        view_street(nm, st, up)
    for nm, st in [("rue_de_belleville", "Rue de Belleville"), ("rue_de_menilmontant", "Rue de Ménilmontant"), ("rue_des_couronnes", "Rue des Couronnes"),
                   ("boulevard_de_belleville", "Boulevard de Belleville"), ("rue_du_faubourg_du_temple", "Rue du Faubourg du Temple"),
                   ("rue_piat", "Rue Piat"), ("quai_de_jemmapes", "Quai de Jemmapes"), ("quai_de_valmy", "Quai de Valmy"),
                   ("rue_oberkampf", "Rue Oberkampf"), ("avenue_de_la_republique", "Avenue de la République"),
                   ("rue_jean_pierre_timbaud", "Rue Jean-Pierre Timbaud")]:
        view_street(nm, st, True, 8)
    view_ll("belvedere_de_belleville", (48.87165, 2.38535), (48.86950, 2.37300), 1.7, 0)
    nb = 0
    for st in streets:                                                    # contrôle visuel des passerelles
        if st["bridge"] and not st["steps"] and st["hw"] in PEDESTRIAN and nb < 2 and len(st["pts"]) >= 2:
            a0, a1 = st["pts"][0], st["pts"][-1]; mid = (a0 + a1) / 2; d = a1 - a0; L_ = float(np.hypot(*d))
            if L_ < 8 or not inb(*mid, -40): continue
            d = d / L_; perp = np.array([-d[1], d[0]]); nb += 1
            view("passerelle_%d" % nb, *(mid + perp * 24 - d * 6), *mid, 5.0, 4.0)
    if plazas:                                                            # vues sur la plus grande place (en hauteur, puis à pied)
        p = max(plazas, key=lambda q: abs(area2(q))); c = p.mean(0)
        if abs(area2(p)) / 2 > 4000:
            ax = np.linalg.svd(p - c)[2][0]; ext = float(np.abs((p - c) @ ax).max())
            view("grande_place_haut", *(c - ax * ext * 0.95), *(c + ax * ext * 0.2), 16.0, 1.0)
            view("grande_place_sol", *(c - ax * ext * 0.6), *(c + ax * ext * 0.5), 1.7, 6.0)
    for nm, (q, n_) in spots.items():                                         # contrôle visuel : affiches, étal, banderole
        dist, up = {"affiches": (4.5, 1.6), "etalage": (6.0, 1.3), "banderole": (14.0, 5.2)}[nm]
        view("commune_" + nm, *(q + n_ * dist), *q, 1.7, up)
    for i, (q, d_) in enumerate(barricades[:2]):                             # contrôle visuel des barricades
        view("barricade_%d" % (i + 1), *(q + d_ * 11 + np.array([-d_[1], d_[0]]) * 1.5), *q, 1.7, 1.6)
    for pr in props:
        if pr[0] == "republique":                                         # le monument, vu de face à hauteur d'homme
            a_ = math.radians(250); view("monument_republique", pr[1] + math.cos(a_ - 0.45) * 27, pr[2] + math.sin(a_ - 0.45) * 27, pr[1], pr[2], 1.7, 12.5)
            view("monument_republique_loin", pr[1] + math.cos(a_ + 0.9) * 60, pr[2] + math.sin(a_ + 0.9) * 60, pr[1], pr[2], 6.0, 12.0)
    canals = [p for p, c in waters if c]
    if canals:                                                            # vue le long du plus grand bassin
        p = max(canals, key=lambda q: abs(area2(q))); c = p.mean(0)
        ax = np.linalg.svd(p - c)[2][0]; ext = float(np.abs((p - c) @ ax).max())
        view("canal", *(c - ax * ext * 0.9), *(c + ax * ext * 0.6), 4.5, 1.0)
    view_ll("toits_vers_le_sacre_coeur", (48.88560, 2.33900), (48.88680, 2.34300), 38, 25)
    view_ll("vue_aerienne", (48.88230, 2.33700), (48.88640, 2.34150), 240, 0)
    view("vue_generale", xmin + 0.1 * (xmax - xmin), ymin - 380, (xmin + xmax) / 2, (ymin + ymax) / 2, 300, 0)
    def gd(lat, lon, up):
        x, y = proj(lat, lon)
        return [round(x, 2), round(float(G.h([(x, y)])[0]) + up, 2), round(-y, 2)] if inb(x, y, -2) else None
    sla, slo = map(float, a.spawn.split(","))
    world = dict(source=", ".join(os.path.basename(f) for f in a.osm), origin_latlon=[latc, lonc], bounds_m=[xmin, ymin, xmax, ymax],
                 altitude=[float(H.min()), float(H.max())], spawn=gd(sla, slo, 0.3) or [0.0, float(G.h([(0, 0)])[0]) + 0.3, 0.0],
                 zones=zones, views=views, lamps=lamp_pos, materials=mat_table, materials_dir="res://materiaux",
                 stats=dict(triangles=total, batiments=len(blds), rues=len(streets), arbres=len(trees), reverberes=len(lamp_pos)))
    with open(os.path.join(out, "world.json"), "w") as f: json.dump(world, f, indent=1)
    print(f"OK : {len(zones)} zones, {total} triangles, {len(blds)} bâtiments, {len(streets)} rues/escaliers, "
          f"{len(trees)} arbres, {len(lamp_pos)} réverbères, altitude {H.min():.0f}-{H.max():.0f} m")
    if a.preview: render_preview(a.preview, views)

def render_preview(path, views):
    sc = bpy.context.scene; sc.render.engine = "CYCLES"; sc.cycles.samples = 24; sc.cycles.device = "CPU"
    try: sc.cycles.use_denoising = True
    except Exception: pass
    sc.render.resolution_x, sc.render.resolution_y = 1280, 720
    w = bpy.data.worlds.new("ciel"); sc.world = w
    if not w.node_tree: w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.55, 0.45, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    sun = bpy.data.objects.new("soleil", bpy.data.lights.new("soleil", "SUN")); sc.collection.objects.link(sun)
    sun.data.energy = 4.0; sun.data.color = (1.0, 0.72, 0.5); sun.data.angle = 0.03
    sun.rotation_euler = Vector((-0.84, -0.48, 0.25)).normalized().to_track_quat("Z", "Y").to_euler()
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
    cam.data.lens = 28; cam.data.clip_end = 20000
    v = next((v for v in views if v["name"] == "toits_vers_le_sacre_coeur"), None) or next((v for v in views if v["name"] in ("vue_aerienne", "vue_generale")), None)
    pos = Vector((v["pos"][0], -v["pos"][2], v["pos"][1])) if v else Vector((-300, -500, 350))
    tgt = Vector((v["target"][0], -v["target"][2], v["target"][1])) if v else Vector((0, 0, 100))
    cam.location = pos; cam.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.abspath(path); bpy.ops.render.render(write_still=True)
    print("Aperçu :", sc.render.filepath)

if __name__ == "__main__":
    main()
