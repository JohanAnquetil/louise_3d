import bpy
import glob
import os
import sys

# Choisir le quartier
quartier = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "montmartre"

root = os.getcwd()

dossiers = {
    "montmartre": "godot/zones",
    "belleville": "godot/zones_belleville"
}

dossier = os.path.join(root, dossiers[quartier])

# Nettoyer la scène
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)

# Importer toutes les zones GLB
fichiers = sorted(glob.glob(os.path.join(dossier, "*.glb")))

if not fichiers:
    raise RuntimeError(f"Aucun GLB trouvé dans {dossier}")

for i, fichier in enumerate(fichiers):
    print(f"[{i+1}/{len(fichiers)}] {os.path.basename(fichier)}")
    bpy.ops.import_scene.gltf(filepath=fichier)

# Enregistrer le quartier complet
sortie = os.path.join(root, f"{quartier}.blend")
bpy.ops.wm.save_as_mainfile(filepath=sortie)

print(f"Quartier enregistré : {sortie}")
