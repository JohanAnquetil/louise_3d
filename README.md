# Montmartre – décor 3D low-poly (Blender → Godot 4)

Balade à la première personne autour de la place du Tertre : butte en pente (70 → 130 m),
rues, escaliers, immeubles en volumes simples, square Louise Michel, Sacré-Cœur.

## Contenu
- `data/montmartre.osm` — export OpenStreetMap du quartier (© les contributeurs d'OpenStreetMap, licence ODbL :
  mention obligatoire si le jeu est publié). C'est lui qui a servi à générer `godot/zones`.
- `data/montmartre_approx.osm` + `blender/make_osm_approx.py` — ancien plan approximatif fait à la main (secours, plus utilisé).
- `blender/generate_montmartre.py` — script Blender (bpy) : OSM → terrain, rues, escaliers, bâtiments → `.glb` par zones + `world.json`.
- `godot/` — projet Godot 4 (ouvrir `godot/project.godot`), joueur FPS, collisions, lumière de fin de journée.
- `captures/` — rendus de contrôle.

## Régénérer le décor
`blender -b -P blender/generate_montmartre.py -- --osm data/montmartre.osm --out godot/zones`
(ou `pip install bpy` puis `python blender/generate_montmartre.py --osm data/montmartre.osm --out godot/zones`).
Compter 2 à 3 minutes. Rouvrir ensuite le projet Godot : les `.glb` sont réimportés automatiquement.

Options : `--year 1871` (retire les bâtiments dont `start_date` est postérieur, dont le Sacré-Cœur),
`--preview image.png`, `--zone-size 200`, `--cell 3`, `--summit lat,lon`, `--alt-base 70 --alt-top 130`.

Le relief est un modèle mathématique (butte elliptique aplanie le long des rues), pas un relevé d'altitude.

## Ce que le script fabrique
- Immeubles : façades à fenêtres, volets et balcons, rez-de-chaussée à devantures et portes cochères,
  mansardes en zinc avec lucarnes, cheminées ; maisons basses à toit de tuiles. Fenêtres et vitrines éclairées.
- Monuments (Sacré-Cœur, églises) à partir des `building:part` d'OSM, dômes compris.
- Rues pavées dont la largeur est mesurée entre les façades, trottoirs, escaliers avec mains courantes, murs et grilles.
- Arbres, réverbères, bancs, fontaines, moulins, manège, parasols place du Tertre, funiculaire (rails).
- Horizon : plaine et silhouette de ville autour du quartier (zone `lointain.glb`).

## Matériaux
Les `.glb` ne contiennent que la géométrie et le nom des matériaux. Les textures sont dans `godot/materiaux/*.png`
(retouchables dans un éditeur d'images) et les matériaux sont décrits dans `godot/zones/world.json` :
Godot les construit une seule fois et les partage entre toutes les zones.

## Godot
- ZQSD / WASD / flèches, souris, Maj pour courir, Espace pour sauter, Échap pour libérer la souris.
- Soleil réglable sur le nœud `Main` (`sun_azimuth_deg`, `sun_elevation_deg`) ; `lamp_lights` = nombre de réverbères éclairants.
- Collisions créées au chargement depuis les maillages (terrain + bâtiments + murs) ; les objets `_NOCOL` sont ignorés.
- Vérification automatique : `godot --path godot -- --capture=/chemin/dossier`.

## Louise Michel
`blender/make_louise.py` fabrique `godot/personnages/louise_michel.glb` : personnage low-poly statique (environ 1 000 triangles,
sans squelette ni animation), robe noire, écharpe rouge, livre et drapeau rouge (objet `drapeau` séparé, supprimable).
Elle est placée devant le joueur place du Tertre par `SpawnLouise()` dans `godot/scripts/Main.cs`.

## Textures photo (facultatif)
Les textures de `data/textures/` (Poly Haven, CC0) remplacent les sols dessinés : pavés, dalles, herbe, trottoirs,
murs, ardoise des maisons basses, brique des cheminées. La table `PHOTOS` en tête de `blender/generate_montmartre.py`
associe chaque matériau à un fichier et à sa largeur réelle en mètres (à ajuster). Un fichier absent = retour au rendu dessiné.

## Deuxième quartier : Belleville – Ménilmontant – République
Trois exports fusionnés (`data/belleville.osm`, `belleville_ouest.osm`, `belleville_centre.osm`) : de la place de la
République et des deux rives du canal Saint-Martin jusqu'à la rue des Pyrénées, Oberkampf compris.

    python blender/generate_montmartre.py --osm data/belleville.osm data/belleville_ouest.osm data/belleville_centre.osm \
        --out godot/zones_belleville --summit 48.8755,2.3985 --hill-radius 1700,2600 --alt-base 38 --alt-top 128 --spawn 48.8722,2.3767

Compter 3 à 4 minutes. Scène Godot : `belleville.tscn` (la touche Tab passe d'un quartier à l'autre).
Les coins non couverts par les exports restent un sol sombre vide. Le script gère les plans d'eau (canal creusé sous
le niveau des quais), les ponts et passerelles (tablier `ponts_NOCOL` + rampe de collision invisible `ponts_COLONLY`).
Godot charge d'abord les zones proches du départ, puis les autres en arrière-plan (`preload_radius`, `view_distance` sur `Main`).
Le relief reste une butte calculée.

## Décor de la Commune (1871)
Option `--commune` du script : drapeaux rouges aux façades, affiches placardées, banderoles « Vive la Commune »,
étalages de marché et barricades de pavés (avec un passage sur le côté). Ces objets sont dans des maillages nommés
`commune` : dans Godot, la touche C les affiche ou les masque (propriété `show_commune` du nœud `Main`).
Les affiches et la banderole viennent de `data/textures/affiches.png`, modifiable dans un éditeur d'images.
Les deux quartiers livrés ont été générés avec `--commune`.

## Code du jeu (C#)
Le jeu est écrit en C# (Godot 4.5 version .NET, SDK .NET 8 ou plus récent) :
- `godot/scripts/Main.cs` : chargement d'un quartier (zones, matériaux, réverbères, Louise, décor de la Commune, touches Tab et C, mode `--capture`).
- `godot/scripts/Player.cs` : joueur à la première personne.
- `godot/scripts/WorldInfo.cs` : structure du fichier `world.json` écrit par le générateur.
Godot compile tout seul au lancement (F5). Les scripts Python de `blender/` restent en Python.
