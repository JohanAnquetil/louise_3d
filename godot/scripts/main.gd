extends Node3D
## Charge les zones .glb exportées par Blender (res://zones), génère les collisions
## à partir des maillages du décor, place le joueur et règle le soleil de fin de journée.
##
## Mode vérification (sans interaction) :
##   godot --path . -- --capture=/chemin/vers/dossier
## -> teste la physique, enregistre une capture par point de vue de world.json, puis quitte.

@export var zones_dir := "res://zones"
## Azimut du soleil en degrés (0 = nord, 90 = est, 180 = sud, 270 = ouest).
@export_range(0.0, 360.0) var sun_azimuth_deg := 243.0
## Hauteur du soleil au-dessus de l'horizon.
@export_range(0.0, 90.0) var sun_elevation_deg := 13.0

@onready var sun: DirectionalLight3D = $Sun
@onready var world: Node3D = $World
@onready var player: CharacterBody3D = $Player

## Nombre de réverbères réellement éclairants autour du joueur (les autres ne font que briller).
@export_range(0, 8) var lamp_lights := 8

## Décor de la Commune de 1871 (drapeaux, affiches, étalages, barricades) : affiché au départ ? Touche C pour basculer.
@export var show_commune := true
## Scène de l'autre quartier (touche Tab pour y aller).
@export_file("*.tscn") var other_scene := ""

## Les zones à moins de cette distance du départ sont chargées avant de jouer (le sol sous les pieds).
@export var preload_radius := 320.0
## Au-delà de cette distance, une zone est masquée (le brouillard la cache de toute façon).
@export var view_distance := 1100.0

var info := {}
var _only_views := ""
var _pending: Array = []
var _zones: Array = []
var _bodies := 0
var _invisible := StandardMaterial3D.new()
var _materials := {}
var _lamps := PackedVector3Array()
var _lights: Array[OmniLight3D] = []
var _lamp_timer := 0.0


func _ready() -> void:
	_invisible.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_invisible.albedo_color = Color(0, 0, 0, 0)
	_invisible.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	_setup_sun()
	info = _read_world_json()
	_make_materials()
	# Zones : les plus proches du départ sont chargées tout de suite, les autres en arrière-plan.
	var s0: Array = info.get("spawn", [0.0, 131.0, 0.0])
	var start := Vector3(s0[0], 0.0, s0[2])
	for z in info.get("zones", []):
		var c: Array = z["center"]
		var far_zone: bool = z["name"] == "lointain"
		var d := 0.0 if far_zone else start.distance_to(Vector3(c[0], 0.0, c[2]))
		_pending.append({"name": z["name"], "path": "%s/%s" % [zones_dir, z["file"]], "center": Vector3(c[0], 0.0, c[2]), "dist": d, "always": far_zone})
	_pending.sort_custom(func(a, b): return a["dist"] < b["dist"])
	while not _pending.is_empty() and _pending[0]["dist"] < preload_radius:
		_add_zone(_pending.pop_front(), null)
	for z in _pending:
		ResourceLoader.load_threaded_request(z["path"])
	print("Zones chargées au départ : %d, en arrière-plan : %d" % [world.get_child_count(), _pending.size()])

	_setup_lamps()
	var s: Array = info.get("spawn", [0.0, 131.0, 0.0])
	player.global_position = Vector3(s[0], s[1], s[2])
	player.rotation.y = deg_to_rad(-70.0)  # regarde vers l'est (Sacré-Cœur)
	_spawn_louise(player.global_position + Vector3(0.94, 0.0, -0.34) * 4.5 + Vector3(0.0, -0.18, 0.0))

	var capture_dir := ""
	for a in OS.get_cmdline_user_args():
		if a.begins_with("--capture="):
			capture_dir = a.trim_prefix("--capture=")
		elif a.begins_with("--views="):  # ne capturer que les vues dont le nom contient ce texte
			_only_views = a.trim_prefix("--views=")
	if capture_dir != "":
		_run_capture(capture_dir)
	else:
		get_tree().create_timer(8.0).timeout.connect(func(): $HUD/Aide.hide())


## Louise Michel (personnage statique, modèle res://personnages/louise_michel.glb), tournée vers le joueur.
func _spawn_louise(pos: Vector3) -> void:
	var path := "res://personnages/louise_michel.glb"
	if not ResourceLoader.exists(path):
		return
	var louise: Node3D = (load(path) as PackedScene).instantiate()
	louise.name = "LouiseMichel"
	add_child(louise)
	louise.global_position = pos
	var d := player.global_position - pos
	louise.rotation.y = atan2(d.x, d.z)
	var body := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.36
	capsule.height = 1.65
	shape.shape = capsule
	shape.position = Vector3(0.0, 0.83, 0.0)
	body.add_child(shape)
	louise.add_child(body)


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and event.physical_keycode == KEY_TAB and other_scene != "":
		get_tree().change_scene_to_file(other_scene)
	elif event is InputEventKey and event.pressed and not event.echo and event.physical_keycode == KEY_C:
		show_commune = not show_commune
		for z in _zones:
			_apply_commune(z["node"])


## Affiche ou masque les objets du décor de la Commune (et leurs collisions : barricades).
func _apply_commune(node: Node) -> void:
	if node is MeshInstance3D and String(node.name).contains("commune"):
		node.visible = show_commune
		for c in node.get_children():
			if c is StaticBody3D:
				c.collision_layer = 1 if show_commune else 0
	for c in node.get_children():
		_apply_commune(c)


func _setup_sun() -> void:
	var az := deg_to_rad(sun_azimuth_deg)
	var el := deg_to_rad(sun_elevation_deg)
	# x = est, y = haut, -z = nord
	var to_sun := Vector3(sin(az) * cos(el), sin(el), -cos(az) * cos(el))
	sun.look_at_from_position(to_sun, Vector3.ZERO, Vector3.UP)


func _read_world_json() -> Dictionary:
	var f := FileAccess.open(zones_dir + "/world.json", FileAccess.READ)
	if f == null:
		push_error("world.json absent : lancez d'abord blender/generate_montmartre.py")
		return {}
	var data = JSON.parse_string(f.get_as_text())
	return data if data is Dictionary else {}


## Matériaux : décrits dans world.json, construits une seule fois et partagés par toutes les zones
## (les .glb ne contiennent que la géométrie, les UV et le nom des matériaux).
func _make_materials() -> void:
	var dir: String = info.get("materials_dir", "res://materiaux")
	for m in info.get("materials", []):
		var mat := StandardMaterial3D.new()
		mat.resource_name = m["name"]
		var c: Array = m["color"]
		mat.albedo_color = Color(c[0], c[1], c[2])
		mat.roughness = m.get("roughness", 0.9)
		mat.metallic_specular = 0.2
		mat.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
		if m.has("albedo"):
			mat.albedo_texture = _texture(dir + "/" + m["albedo"])
		if m.has("uv_scale"):
			var k: float = m["uv_scale"]
			mat.uv1_scale = Vector3(k, k, k)
		if m.has("emission"):
			mat.emission_enabled = true
			mat.emission_texture = _texture(dir + "/" + m["emission"])
			mat.emission_energy_multiplier = m.get("emission_energy", 1.0)
		elif m.has("emission_color"):
			var e: Array = m["emission_color"]
			mat.emission_enabled = true
			mat.emission = Color(e[0], e[1], e[2])
			mat.emission_energy_multiplier = m.get("emission_energy", 1.0)
		if m.get("double_sided", false):
			mat.cull_mode = BaseMaterial3D.CULL_DISABLED
		_materials[m["name"]] = mat


func _texture(path: String) -> Texture2D:
	var t: Texture2D = load(path)
	if t == null:
		push_error("Texture introuvable : " + path)
		return null
	var img := t.get_image()
	if img.is_compressed():
		img.decompress()
	img.generate_mipmaps()
	return ImageTexture.create_from_image(img)


func _share_materials(node: Node) -> void:
	if node is MeshInstance3D and node.mesh != null:
		for i in node.mesh.get_surface_count():
			var m: Material = node.mesh.surface_get_material(i)
			if m != null and _materials.has(m.resource_name):
				node.mesh.surface_set_material(i, _materials[m.resource_name])
	for c in node.get_children():
		_share_materials(c)


## Réverbères : toutes les lanternes brillent (matériau émissif) ; seules les plus proches du joueur
## portent une vraie lumière, déplacée au fil de la marche, pour rester fluide.
func _setup_lamps() -> void:
	for l in info.get("lamps", []):
		_lamps.append(Vector3(l[0], l[1], l[2]))
	for i in lamp_lights:
		var o := OmniLight3D.new()
		o.light_color = Color(1.0, 0.78, 0.5)
		o.light_energy = 2.2
		o.omni_range = 13.0
		o.omni_attenuation = 1.4
		o.shadow_enabled = false
		add_child(o)
		_lights.append(o)
	_place_lamp_lights()


func _place_lamp_lights() -> void:
	if _lights.is_empty() or _lamps.is_empty():
		return
	var cam := get_viewport().get_camera_3d()
	var p: Vector3 = cam.global_position if cam != null else player.global_position
	var near: Array = []
	for l in _lamps:
		var d := p.distance_squared_to(l)
		if d < 90.0 * 90.0:
			near.append([d, l])
	near.sort_custom(func(a, b): return a[0] < b[0])
	for i in _lights.size():
		_lights[i].visible = i < near.size()
		if i < near.size():
			_lights[i].global_position = near[i][1]


func _add_zone(z: Dictionary, scene: PackedScene) -> void:
	if scene == null:
		scene = load(z["path"])
	if scene == null:
		push_error("Zone introuvable : %s" % z["path"])
		return
	var inst: Node3D = scene.instantiate()
	inst.name = z["name"]
	world.add_child(inst)
	_share_materials(inst)
	_bodies += _add_collisions(inst)
	_apply_commune(inst)
	_zones.append({"node": inst, "center": z["center"], "always": z["always"]})


func all_zones_loaded() -> bool:
	return _pending.is_empty()


func _process(delta: float) -> void:
	# une zone au plus par image, dès que son chargement en arrière-plan est terminé
	if not _pending.is_empty():
		var z: Dictionary = _pending[0]
		var st := ResourceLoader.load_threaded_get_status(z["path"])
		if st == ResourceLoader.THREAD_LOAD_LOADED:
			_pending.pop_front()
			_add_zone(z, ResourceLoader.load_threaded_get(z["path"]))
		elif st != ResourceLoader.THREAD_LOAD_IN_PROGRESS:
			_pending.pop_front()
			_add_zone(z, null)
	_lamp_timer -= delta
	if _lamp_timer <= 0.0:
		_lamp_timer = 0.4
		_place_lamp_lights()
		var cam := get_viewport().get_camera_3d()
		if cam != null:
			var p := Vector3(cam.global_position.x, 0.0, cam.global_position.z)
			for zz in _zones:
				zz["node"].visible = zz["always"] or p.distance_to(zz["center"]) < view_distance


## Collisions générées depuis le décor : un StaticBody3D + forme "trimesh" par maillage.
## Les objets dont le nom contient "NOCOL" (rues posées sur le terrain, marches, arbres) sont ignorés :
## on marche sur le terrain, qui épouse déjà la pente des rues et des escaliers.
func _add_collisions(node: Node) -> int:
	var n := 0
	if node is MeshInstance3D and not String(node.name).contains("NOCOL"):
		node.create_trimesh_collision()
		n += 1
		if String(node.name).contains("COLONLY"):  # rampe invisible (escaliers de passerelle, tabliers)
			node.set_surface_override_material(0, _invisible)
	for c in node.get_children():
		n += _add_collisions(c)
	return n


func _run_capture(dir: String) -> void:
	$HUD.hide()
	DirAccess.make_dir_recursive_absolute(dir)
	while not all_zones_loaded():
		await get_tree().process_frame
	print("Zones chargées : %d, corps de collision : %d" % [world.get_child_count(), _bodies])
	if _only_views != "":
		await _capture_views(dir)
		return
	# 1) le joueur tombe-t-il bien sur le sol ?
	var start := player.global_position
	for i in 120:
		await get_tree().physics_frame
	print("[test] sol : départ y=%.2f -> y=%.2f, is_on_floor=%s" % [start.y, player.global_position.y, player.is_on_floor()])
	await _shot(dir, "00_joueur_depart")
	var louise := get_node_or_null("LouiseMichel") as Node3D
	if louise != null:
		var lc := Camera3D.new()
		lc.fov = 45.0
		add_child(lc)
		var front := louise.global_transform.basis.z
		lc.look_at_from_position(louise.global_position + front * 4.2 + front.cross(Vector3.UP) * 1.2 + Vector3(0, 1.5, 0), louise.global_position + Vector3(0, 1.35, 0), Vector3.UP)
		lc.make_current()
		await _shot(dir, "00b_louise_michel")
		lc.queue_free()
		player.get_node("Head/Camera3D").make_current()
	# 2) marche 20 s vers l'est (pente + façades) : il doit avancer puis buter contre une façade
	var p0 := player.global_position
	player.auto_move = Vector2(0, -1)
	var wall_frames := 0
	for i in 1200:
		await get_tree().physics_frame
		if player.is_on_wall():
			wall_frames += 1
	player.auto_move = Vector2.ZERO
	var p1 := player.global_position
	print("[test] marche : %.1f m parcourus, dénivelé %.2f m, images au contact d'un mur=%d, is_on_floor=%s" % [
		Vector2(p1.x - p0.x, p1.z - p0.z).length(), p1.y - p0.y, wall_frames, player.is_on_floor()])
	await _shot(dir, "01_joueur_apres_marche")
	# 2b) passerelles : lâché au milieu du tablier, le joueur doit s'y poser (et non tomber dans l'eau)
	for v in info.get("views", []):
		if String(v["name"]).begins_with("passerelle"):
			var t: Array = v["target"]
			player.velocity = Vector3.ZERO
			player.global_position = Vector3(t[0], t[1] + 5.0, t[2])
			for i in 150:
				await get_tree().physics_frame
			print("[test] %s : posé à y=%.2f (tablier attendu vers %.2f, eau vers %.2f), is_on_floor=%s" % [
				v["name"], player.global_position.y, t[1] + 1.5, t[1] - 2.8, player.is_on_floor()])
	await _capture_views(dir)


func _capture_views(dir: String) -> void:
	# 3) points de vue
	player.enabled = false
	var cam := Camera3D.new()
	cam.fov = 70.0
	cam.far = 9000.0
	add_child(cam)
	cam.make_current()
	var i := 2
	for v in info.get("views", []):
		if _only_views != "":  # liste de morceaux de noms séparés par des virgules
			var keep := false
			for part in _only_views.split(","):
				if String(v["name"]).contains(part):
					keep = true
			if not keep:
				continue
		var p: Array = v["pos"]
		var t: Array = v["target"]
		var from := Vector3(p[0], p[1], p[2])
		var to := Vector3(t[0], t[1], t[2])
		if v.has("ground"):  # vue ajoutée sans altitude : on la pose sur le sol par lancer de rayon
			var gofs: Array = v["ground"]
			from.y = _ground_y(from) + gofs[0]
			to.y = _ground_y(to) + gofs[1]
		cam.look_at_from_position(from, to, Vector3.UP)
		_place_lamp_lights()
		for zz in _zones:
			zz["node"].visible = true
		await _shot(dir, "%02d_%s" % [i, v["name"]])
		i += 1
	print("[test] captures enregistrées dans ", dir)
	get_tree().quit()


func _ground_y(p: Vector3) -> float:
	var q := PhysicsRayQueryParameters3D.create(Vector3(p.x, 400.0, p.z), Vector3(p.x, -50.0, p.z))
	var hit := get_world_3d().direct_space_state.intersect_ray(q)
	return hit["position"].y if hit.has("position") else 0.0


func _shot(dir: String, shot_name: String) -> void:
	for i in 4:
		await get_tree().process_frame
	await RenderingServer.frame_post_draw
	get_viewport().get_texture().get_image().save_png("%s/%s.png" % [dir, shot_name])
