using Godot;

/// <summary>
/// Joueur à la première personne. Les touches sont lues par position physique :
/// ZQSD sur un clavier AZERTY, WASD sur un QWERTY, plus les flèches.
/// </summary>
public partial class Player : CharacterBody3D
{
    [Export] public float WalkSpeed { get; set; } = 4.0f;
    [Export] public float SprintSpeed { get; set; } = 8.0f;
    [Export] public float JumpVelocity { get; set; } = 4.5f;
    [Export] public float MouseSensitivity { get; set; } = 0.0025f;
    [Export] public float Acceleration { get; set; } = 12.0f;

    /// <summary>Déplacement imposé, utilisé par le mode --capture pour tester les collisions.</summary>
    public Vector2 AutoMove { get; set; } = Vector2.Zero;

    /// <summary>Quand false, le joueur ne bouge plus (prises de vue automatiques).</summary>
    public bool Enabled { get; set; } = true;

    private Node3D _head;
    private float _gravity;

    public override void _Ready()
    {
        _head = GetNode<Node3D>("Head");
        _gravity = ProjectSettings.GetSetting("physics/3d/default_gravity").AsSingle();
    }

    public override void _UnhandledInput(InputEvent @event)
    {
        if (@event is InputEventMouseButton mouseButton && mouseButton.Pressed)
        {
            Input.MouseMode = Input.MouseModeEnum.Captured;
        }
        else if (@event is InputEventKey key && key.Pressed && key.PhysicalKeycode == Key.Escape)
        {
            Input.MouseMode = Input.MouseModeEnum.Visible;
        }
        else if (@event is InputEventMouseMotion motion && Input.MouseMode == Input.MouseModeEnum.Captured)
        {
            RotateY(-motion.Relative.X * MouseSensitivity);
            Vector3 headRotation = _head.Rotation;
            headRotation.X = Mathf.Clamp(headRotation.X - motion.Relative.Y * MouseSensitivity, -1.5f, 1.5f);
            _head.Rotation = headRotation;
        }
    }

    private static float Axis(Key[] negative, Key[] positive)
    {
        float value = 0.0f;
        foreach (Key k in negative)
        {
            if (Input.IsPhysicalKeyPressed(k)) value -= 1.0f;
        }
        foreach (Key k in positive)
        {
            if (Input.IsPhysicalKeyPressed(k)) value += 1.0f;
        }
        return Mathf.Clamp(value, -1.0f, 1.0f);
    }

    public override void _PhysicsProcess(double delta)
    {
        if (!Enabled) return;
        float dt = (float)delta;
        Vector3 velocity = Velocity;

        if (!IsOnFloor())
        {
            velocity.Y -= _gravity * dt;
        }
        else if (Input.IsPhysicalKeyPressed(Key.Space))
        {
            velocity.Y = JumpVelocity;
        }

        var input = new Vector2(
            Axis(new[] { Key.A, Key.Left }, new[] { Key.D, Key.Right }),
            Axis(new[] { Key.W, Key.Up }, new[] { Key.S, Key.Down }));
        if (AutoMove != Vector2.Zero) input = AutoMove;

        Vector3 direction = GlobalTransform.Basis * new Vector3(input.X, 0.0f, input.Y);
        direction.Y = 0.0f;
        direction = direction.Length() > 0.01f ? direction.Normalized() : Vector3.Zero;

        float speed = Input.IsPhysicalKeyPressed(Key.Shift) ? SprintSpeed : WalkSpeed;
        float blend = Mathf.Min(1.0f, Acceleration * dt);
        velocity.X = Mathf.Lerp(velocity.X, direction.X * speed, blend);
        velocity.Z = Mathf.Lerp(velocity.Z, direction.Z * speed, blend);

        Velocity = velocity;
        MoveAndSlide();
    }
}
