#!/usr/bin/env python3
"""Fabrique un fichier .osm APPROXIMATIF de Montmartre (autour de la place du Tertre).

A n'utiliser que si l'on n'a pas de vrai export OpenStreetMap : le tracé des rues et
des escaliers est reconstitué à la main (positions à quelques mètres / dizaines de
mètres près) et les immeubles sont générés automatiquement le long des rues.
Le fichier produit est du XML OSM standard : generate_montmartre.py le lit comme
n'importe quel vrai export.

    python3 make_osm_approx.py ../data/montmartre_approx.osm
"""
import math, random, sys

REF_LAT, REF_LON = 48.88650, 2.34080          # centre de la place du Tertre
M_LAT, M_LON = 111200.0, 73130.0              # mètres par degré à cette latitude
XMIN, XMAX, YMIN, YMAX = -400, 400, -300, 300 # emprise en mètres (x = est, y = nord)

# --- Rues : (nom, type highway, largeur totale façade à façade, points) -----------------
S = [
 ("Rue Norvins", "pedestrian", 7, [(48,22),(24,20),(-20,22),(-60,36),(-110,52),(-150,62),(-200,78),(-240,92)]),
 ("Place du Tertre", "pedestrian", 6, [(22,0),(50,-2)]),
 ("Rue du Mont-Cenis", "residential", 7, [(50,-2),(48,22),(46,60),(42,110),(40,135)]),
 ("Rue du Mont-Cenis", "steps", 5, [(40,135),(37,195)]),
 ("Rue du Mont-Cenis", "residential", 8, [(37,195),(30,245),(25,300)]),
 ("Rue Azaïs", "pedestrian", 8, [(135,-80),(105,-86),(90,-68),(75,-45)]),
 ("Rue Saint-Éleuthère", "residential", 7, [(75,-45),(60,-20),(50,-2)]),
 ("Rue du Cardinal Dubois", "pedestrian", 9, [(135,-80),(190,-62),(245,-52)]),
 ("Rue du Cardinal Guibert", "residential", 7, [(135,-80),(130,0),(125,81)]),
 ("Rue du Calvaire", "pedestrian", 4, [(-22,-18),(-24,-45)]),
 ("Rue du Calvaire", "steps", 3.5, [(-24,-45),(-28,-98)]),
 ("Place du Calvaire", "pedestrian", 5, [(-24,-45),(10,-50),(40,-40),(60,-20)]),
 ("Rue Poulbot", "pedestrian", 5, [(-60,36),(-68,5),(-55,-30),(-24,-45)]),
 ("Rue Saint-Rustique", "pedestrian", 4, [(46,60),(0,70),(-50,80),(-100,88)]),
 ("Rue des Saules", "residential", 7, [(-110,52),(-100,88),(-105,135),(-112,180),(-120,222),(-130,300)]),
 ("Rue Cortot", "residential", 6, [(42,110),(-30,122),(-105,135)]),
 ("Rue de l'Abreuvoir", "residential", 6, [(-105,135),(-160,140),(-215,152)]),
 ("Rue Girardon", "residential", 7, [(-255,68),(-240,92),(-232,125),(-215,152),(-205,200),(-200,300)]),
 ("Rue Saint-Vincent", "residential", 6, [(-120,222),(-40,208),(37,195),(100,180),(170,185)]),
 ("Rue de la Bonne", "residential", 6, [(155,85),(160,130),(170,185)]),
 ("Rue du Chevalier de la Barre", "residential", 6, [(46,60),(100,78),(125,81),(155,85),(215,80),(250,62)]),
 ("Rue du Chevalier de la Barre", "steps", 5, [(250,62),(300,45)]),
 ("Rue Lamarck", "tertiary", 11, [(245,-52),(262,10),(250,62),(225,130),(170,185),(100,225),(30,245),(-60,270),(-130,292)]),
 ("Rue Foyatier", "steps", 6, [(105,-222),(105,-150),(105,-110),(105,-86)]),
 ("Rue Gabrielle", "residential", 7, [(105,-110),(60,-108),(-28,-98),(-40,-98),(-110,-92),(-165,-80),(-185,-70)]),
 ("Rue Chappe", "steps", 5, [(60,-108),(60,-150)]),
 ("Rue Chappe", "residential", 7, [(60,-150),(58,-215),(55,-292)]),
 ("Rue André Barsacq", "residential", 7, [(105,-150),(60,-150),(-42,-142)]),
 ("Rue Berthe", "residential", 7, [(-42,-142),(-120,-132),(-200,-120)]),
 ("Rue Drevet", "steps", 3.5, [(-40,-98),(-42,-142),(-45,-172)]),
 ("Rue des Trois Frères", "residential", 8, [(150,-298),(100,-255),(58,-215),(-45,-172),(-120,-150),(-203,-138)]),
 ("Rue Tardieu", "residential", 8, [(190,-228),(105,-222),(58,-215)]),
 ("Place Saint-Pierre", "residential", 9, [(190,-228),(250,-232)]),
 ("Rue Ronsard", "residential", 7, [(250,-232),(256,-150),(258,-80),(245,-52)]),
 ("Rue Maurice Utrillo", "steps", 5, [(258,-80),(320,-88)]),
 ("Rue Paul Albert", "residential", 7, [(300,45),(328,-20),(320,-88),(326,-160)]),
 ("Rue Muller", "residential", 8, [(256,-150),(326,-160),(400,-172)]),
 ("Rue Feutrier", "residential", 7, [(326,-160),(362,-60),(350,40),(300,45)]),
 ("Rue de Steinkerque", "pedestrian", 8, [(190,-228),(185,-300)]),
 ("Rue d'Orsel", "residential", 9, [(-170,-292),(55,-292),(150,-298),(185,-300),(400,-304)]),
 ("Rue Yvonne Le Tac", "residential", 8, [(58,-215),(-60,-225),(-170,-233)]),
 ("Rue des Abbesses", "tertiary", 10, [(-170,-233),(-230,-228),(-330,-205),(-400,-185)]),
 ("Rue La Vieuville", "residential", 7, [(-170,-233),(-170,-292)]),
 ("Rue Ravignan", "residential", 7, [(-230,-228),(-212,-170),(-203,-138),(-200,-120),(-190,-95),(-185,-70),(-165,-25),(-140,20),(-110,52)]),
 ("Rue Lepic", "residential", 9, [(-140,20),(-200,45),(-255,68),(-320,50),(-370,0),(-400,-60)]),
 ("Rue Tholozé", "residential", 7, [(-330,-205),(-325,-100),(-320,50)]),
 ("Rue Durantin", "residential", 7, [(-203,-138),(-260,-125),(-325,-100),(-400,-80)]),
 ("Rue Burq", "residential", 7, [(-260,-125),(-262,-221)]),
 ("Rue d'Orchampt", "residential", 5, [(-190,-95),(-250,-60),(-275,20),(-255,68)]),
 ("Square Louise Michel", "steps", 4, [(140,-222),(140,-88)]),
 ("Square Louise Michel", "steps", 8, [(190,-226),(190,-64)]),
 ("Square Louise Michel", "steps", 4, [(238,-228),(240,-56)]),
]

# --- Places (surfaces piétonnes), espaces verts ------------------------------------------
PLAZAS = [
 ("Place du Tertre", [(-22,-18),(22,-20),(24,16),(-20,18)]),
 ("Parvis du Sacré-Cœur", [(148,-58),(232,-46),(230,-30),(146,-34)]),
 ("Place des Abbesses", [(-200,-215),(-150,-220),(-150,-250),(-205,-248)]),
 ("Place Émile Goudeau", [(-215,-132),(-185,-128),(-183,-105),(-212,-108)]),
 ("Place Jean-Baptiste Clément", [(-155,5),(-125,15),(-130,35),(-158,28)]),
]
GREENS = [
 ("Square Louise Michel", "leisure", "park", [(125,-222),(246,-226),(250,-62),(128,-84)]),
 ("Clos Montmartre", "landuse", "vineyard", [(-98,150),(-45,140),(-42,200),(-105,212)]),
 ("Parc de la Turlure", "leisure", "park", [(195,92),(225,86),(222,118),(200,125)]),
 ("Square Jehan Rictus", "leisure", "park", [(-200,-205),(-160,-208),(-162,-185),(-198,-180)]),
 ("Cimetière Saint-Vincent", "landuse", "cemetery", [(-195,205),(-130,228),(-135,275),(-195,255)]),
 ("Square Suzanne Buisson", "leisure", "park", [(-300,95),(-268,100),(-262,150),(-296,145)]),
]

def rect(cx, cy, w, h):
    return [(cx-w/2, cy-h/2), (cx+w/2, cy-h/2), (cx+w/2, cy+h/2), (cx-w/2, cy+h/2)]
def ngon(cx, cy, r, n):
    return [(cx+r*math.cos(2*math.pi*i/n), cy+r*math.sin(2*math.pi*i/n)) for i in range(n)]

# --- Monuments : (points, tags) en "building:part" (Simple 3D Buildings) ------------------
SC = (168, 22)   # Sacré-Cœur, axe nord-sud, entrée au sud
LANDMARKS = [
 (rect(SC[0], SC[1], 36, 84), {"building:part":"yes","building":"church","height":"32","name":"Basilique du Sacré-Cœur"}),
 (rect(SC[0], SC[1]-48, 26, 12), {"building:part":"yes","building":"church","height":"20"}),
 (ngon(SC[0], SC[1]-8, 10.5, 12), {"building:part":"yes","building":"church","min_height":"32","height":"83","roof:shape":"dome","roof:height":"24"}),
 (rect(SC[0], SC[1]+50, 10, 10), {"building:part":"yes","building":"church","height":"84","roof:shape":"pyramidal","roof:height":"14"}),
 (rect(84, 30, 46, 18), {"building":"church","height":"15","name":"Église Saint-Pierre de Montmartre"}),
 (rect(84-18, 30, 8, 8), {"building:part":"yes","building":"church","height":"24","roof:shape":"pyramidal","roof:height":"5"}),
]
for dx, dy in ((-11,-19),(11,-19),(-11,3),(11,3)):
    LANDMARKS.append((ngon(SC[0]+dx, SC[1]-8+dy, 4.5, 8), {"building:part":"yes","building":"church","min_height":"32","height":"54","roof:shape":"dome","roof:height":"10"}))
for _pts, _tags in LANDMARKS:          # le Sacré-Cœur (1875-1914) n'existait pas pendant la Commune
    if _pts[0][0] > 120: _tags["start_date"] = "1914"

# --- Géométrie -----------------------------------------------------------------------------
def nat_h(x, y):
    """Même modèle d'altitude que generate_montmartre.py (sert à choisir le nb d'étages)."""
    d = math.hypot((x+20)/400.0, (y-25)/240.0)
    t = min(1.0, max(0.0, (d-0.15)/1.35))
    return 70 + 60*0.5*(1+math.cos(math.pi*t))

def seg_dist(p, a, b):
    ax, ay = a; bx, by = b; px, py = p
    dx, dy = bx-ax, by-ay
    L2 = dx*dx+dy*dy
    t = 0 if L2 == 0 else max(0, min(1, ((px-ax)*dx+(py-ay)*dy)/L2))
    return math.hypot(px-ax-t*dx, py-ay-t*dy)

def in_poly(p, poly):
    x, y = p; c = False
    for i in range(len(poly)):
        x1, y1 = poly[i]; x2, y2 = poly[(i+1) % len(poly)]
        if (y1 > y) != (y2 > y) and x < (x2-x1)*(y-y1)/(y2-y1)+x1:
            c = not c
    return c

def convex_overlap(A, B):
    for poly in (A, B):
        for i in range(len(poly)):
            x1, y1 = poly[i]; x2, y2 = poly[(i+1) % len(poly)]
            nx, ny = y2-y1, x1-x2
            a = [nx*x+ny*y for x, y in A]; b = [nx*x+ny*y for x, y in B]
            if max(a) <= min(b) or max(b) <= min(a):
                return False
    return True

def shrink(poly, d):
    cx = sum(p[0] for p in poly)/len(poly); cy = sum(p[1] for p in poly)/len(poly)
    out = []
    for x, y in poly:
        L = math.hypot(x-cx, y-cy) or 1
        out.append((x-(x-cx)/L*d, y-(y-cy)/L*d))
    return out

def gen_buildings(rng):
    segs = [(pts[i], pts[i+1], w/2) for _, _, w, pts in S for i in range(len(pts)-1)]
    keepout = [p for _, p in PLAZAS] + [g[3] for g in GREENS]
    done = [(shrink(p, -3), None) for p, _ in LANDMARKS]      # (polygone, tags)
    out = []
    def ok(q):
        cx = sum(p[0] for p in q)/4; cy = sum(p[1] for p in q)/4
        if not (XMIN+4 < cx < XMAX-4 and YMIN+4 < cy < YMAX-4): return False
        samples = q + [((q[i][0]+q[(i+1)%4][0])/2, (q[i][1]+q[(i+1)%4][1])/2) for i in range(4)] + [(cx, cy)]
        for a, b, hw in segs:
            for s in samples:
                if seg_dist(s, a, b) < hw + 1.2: return False
        for poly in keepout:
            if any(in_poly(s, poly) for s in samples): return False
        qs = shrink(q, 0.35)
        for poly, _ in done:
            if abs(poly[0][0]-cx) < 60 and abs(poly[0][1]-cy) < 60 and convex_overlap(qs, poly): return False
        return True
    for _, _, w, pts in S:
        cum = [0]
        for i in range(len(pts)-1):
            cum.append(cum[-1]+math.dist(pts[i], pts[i+1]))
        def at(s):
            for i in range(len(pts)-1):
                if s <= cum[i+1] or i == len(pts)-2:
                    t = (s-cum[i])/max(1e-6, cum[i+1]-cum[i])
                    return (pts[i][0]+t*(pts[i+1][0]-pts[i][0]), pts[i][1]+t*(pts[i+1][1]-pts[i][1]))
        for side in (1, -1):
            s = 2.0
            while s < cum[-1]-6:
                f = rng.uniform(8, 15); depth = rng.uniform(9, 14)
                f = min(f, cum[-1]-s)
                a, b = at(s), at(s+f)
                L = math.dist(a, b)
                placed = False
                if L > 5:
                    nx, ny = -(b[1]-a[1])/L*side, (b[0]-a[0])/L*side
                    o1 = w/2 + 1.6
                    q = [(a[0]+nx*o1, a[1]+ny*o1), (b[0]+nx*o1, b[1]+ny*o1),
                         (b[0]+nx*(o1+depth), b[1]+ny*(o1+depth)), (a[0]+nx*(o1+depth), a[1]+ny*(o1+depth))]
                    if side < 0: q.reverse()
                    if ok(q):
                        alt = nat_h(sum(p[0] for p in q)/4, sum(p[1] for p in q)/4)
                        lv = rng.choice([2,3,3,4]) if alt > 121 else rng.choice([3,4,4,5]) if alt > 104 else rng.choice([5,6,6,7])
                        done.append((q, None)); out.append((q, {"building":"apartments", "building:levels":str(lv)}))
                        placed = True
                s += f if placed else 3.0
    return out

def gen_trees(rng):
    trees = [(-12,-8),(-4,-10),(6,-9),(14,-7),(-11,6),(-2,8),(8,7),(15,5)]   # place du Tertre
    segs = [(pts[i], pts[i+1], w/2) for _, hw, w, pts in S for i in range(len(pts)-1)]
    for name, _, kind, poly in GREENS:
        if kind == "vineyard": continue
        xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
        area = (max(xs)-min(xs))*(max(ys)-min(ys))
        n, tries = int(area/130), 0
        while n > 0 and tries < 5000:
            tries += 1
            p = (rng.uniform(min(xs), max(xs)), rng.uniform(min(ys), max(ys)))
            if in_poly(p, poly) and all(seg_dist(p, a, b) > hw+2 for a, b, hw in segs) and all(math.dist(p, t) > 6 for t in trees):
                trees.append(p); n -= 1
    return trees

# --- Ecriture XML ----------------------------------------------------------------------------
def main(path):
    rng = random.Random(1871)
    nid = [0]; out = []
    ll = lambda x, y: (REF_LAT + y/M_LAT, REF_LON + x/M_LON)
    esc = lambda s: s.replace("&", "&amp;").replace('"', "&quot;")
    nodes, ways = [], []
    def node(x, y, tags=None):
        nid[0] += 1
        lat, lon = ll(x, y)
        t = "".join(f'<tag k="{k}" v="{esc(v)}"/>' for k, v in (tags or {}).items())
        nodes.append(f'<node id="{nid[0]}" lat="{lat:.7f}" lon="{lon:.7f}" version="1">{t}</node>' if t else
                     f'<node id="{nid[0]}" lat="{lat:.7f}" lon="{lon:.7f}" version="1"/>')
        return nid[0]
    def way(pts, tags, closed=False):
        refs = [node(x, y) for x, y in pts]
        if closed: refs.append(refs[0])
        nid[0] += 1
        ways.append(f'<way id="{nid[0]}" version="1">' + "".join(f'<nd ref="{r}"/>' for r in refs) +
                    "".join(f'<tag k="{k}" v="{esc(v)}"/>' for k, v in tags.items()) + "</way>")
    for name, hw, w, pts in S:
        way(pts, {"highway": hw, "name": name, "width": str(w)})
    for name, pts in PLAZAS:
        way(pts, {"highway": "pedestrian", "area": "yes", "name": name}, True)
    for name, k, v, pts in GREENS:
        way(pts, {k: v, "name": name}, True)
    for pts, tags in LANDMARKS:
        way(pts, tags, True)
    b = gen_buildings(rng)
    for pts, tags in b:
        way(pts, tags, True)
    t = gen_trees(rng)
    for x, y in t:
        node(x, y, {"natural": "tree"})
    (la0, lo0), (la1, lo1) = ll(XMIN, YMIN), ll(XMAX, YMAX)
    with open(path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="make_osm_approx.py (donnees approximatives, PAS OpenStreetMap)">\n')
        f.write(f'<bounds minlat="{la0:.7f}" minlon="{lo0:.7f}" maxlat="{la1:.7f}" maxlon="{lo1:.7f}"/>\n')
        f.write("\n".join(nodes)); f.write("\n"); f.write("\n".join(ways)); f.write("\n</osm>\n")
    print(f"{path}: {len(S)} rues/escaliers, {len(b)} immeubles, {len(t)} arbres")

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "montmartre_approx.osm")
