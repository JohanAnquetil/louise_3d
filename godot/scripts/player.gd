extends CharacterBody3D
## Joueur à la première personne. Les touches sont lues par position physique :
## ZQSD sur un clavier AZERTY, WASD sur un QWERTY, plus les flèches.

@export var walk_speed := 4.0
@export var sprint_speed := 8.0
@export var jump_velocity := 4.5
@export var mouse_sensitivity := 0.0025
@export var acceleration := 12.0

var auto_move := Vector2.ZERO  # utilisé par le mode --capture pour tester les collisions
var enabled := true

@onready var head: Node3D = $Head
@onready var _gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	elif event is InputEventKey and event.pressed and event.physical_keycode == KEY_ESCAPE:
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	elif event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		rotate_y(-event.relative.x * mouse_sensitivity)
		head.rotation.x = clampf(head.rotation.x - event.relative.y * mouse_sensitivity, -1.5, 1.5)


func _axis(neg: Array, pos: Array) -> float:
	var v := 0.0
	for k in neg:
		if Input.is_physical_key_pressed(k):
			v -= 1.0
	for k in pos:
		if Input.is_physical_key_pressed(k):
			v += 1.0
	return clampf(v, -1.0, 1.0)


func _physics_process(delta: float) -> void:
	if not enabled:
		return
	if not is_on_floor():
		velocity.y -= _gravity * delta
	elif Input.is_physical_key_pressed(KEY_SPACE):
		velocity.y = jump_velocity

	var input := Vector2(_axis([KEY_A, KEY_LEFT], [KEY_D, KEY_RIGHT]), _axis([KEY_W, KEY_UP], [KEY_S, KEY_DOWN]))
	if auto_move != Vector2.ZERO:
		input = auto_move
	var dir := (global_transform.basis * Vector3(input.x, 0.0, input.y))
	dir.y = 0.0
	dir = dir.normalized() if dir.length() > 0.01 else Vector3.ZERO
	var speed := sprint_speed if Input.is_physical_key_pressed(KEY_SHIFT) else walk_speed
	var k := minf(1.0, acceleration * delta)
	velocity.x = lerpf(velocity.x, dir.x * speed, k)
	velocity.z = lerpf(velocity.z, dir.z * speed, k)
	move_and_slide()
