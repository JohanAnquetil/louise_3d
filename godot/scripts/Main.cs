using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using Godot;

/// <summary>
/// Charge les zones .glb d'un quartier (dossier ZonesDir), construit les matériaux partagés,
/// génère les collisions depuis le décor, place le joueur et Louise, règle le soleil de fin de journée.
///
/// Mode vérification (sans interaction) :
///   godot --path . -- --capture=/chemin/vers/dossier [--views=nom1,nom2]
/// teste la physique, enregistre une capture par point de vue de world.json, puis quitte.
/// </summary>
public partial class Main : Node3D
{
    /// <summary>Dossier des zones du quartier (contient world.json et les .glb).</summary>
    [Export] public string ZonesDir { get; set; } = "res://zones";

    /// <summary>Azimut du soleil en degrés (0 = nord, 90 = est, 180 = sud, 270 = ouest).</summary>
    [Export(PropertyHint.Range, "0,360")] public float SunAzimuthDeg { get; set; } = 243.0f;

    /// <summary>Hauteur du soleil au-dessus de l'horizon, en degrés.</summary>
    [Export(PropertyHint.Range, "0,90")] public float SunElevationDeg { get; set; } = 13.0f;

    /// <summary>Nombre de réverbères réellement éclairants autour du joueur (les autres ne font que briller).</summary>
    [Export(PropertyHint.Range, "0,8")] public int LampLights { get; set; } = 8;

    /// <summary>Décor de la Commune de 1871 affiché au départ ? Touche C pour basculer.</summary>
    [Export] public bool ShowCommune { get; set; } = true;

    /// <summary>Scène de l'autre quartier (touche Tab pour y aller).</summary>
    [Export(PropertyHint.File, "*.tscn")] public string OtherScene { get; set; } = "";

    /// <summary>Les zones à moins de cette distance du départ sont chargées avant de jouer.</summary>
    [Export] public float PreloadRadius { get; set; } = 320.0f;

    /// <summary>Au-delà de cette distance, une zone est masquée (le brouillard la cache de toute façon).</summary>
    [Export] public float ViewDistance { get; set; } = 1100.0f;

    private sealed class PendingZone
    {
        public string Name;
        public string Path;
        public Vector3 Center;
        public float Distance;
        public bool AlwaysVisible;
    }

    private sealed class LoadedZone
    {
        public Node3D Node;
        public Vector3 Center;
        public bool AlwaysVisible;
    }

    private static readonly JsonSerializerOptions JsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
    };

    private DirectionalLight3D _sun;
    private Node3D _world;
    private Player _player;

    private WorldInfo _info = new();
    private string _onlyViews = "";
    private readonly List<PendingZone> _pending = new();
    private readonly List<LoadedZone> _zones = new();
    private int _bodies;
    private readonly StandardMaterial3D _invisible = new();
    private readonly Dictionary<string, StandardMaterial3D> _materials = new();
    private readonly List<Vector3> _lamps = new();
    private readonly List<OmniLight3D> _lights = new();
    private double _lampTimer;

    public override void _Ready()
    {
        _sun = GetNode<DirectionalLight3D>("Sun");
        _world = GetNode<Node3D>("World");
        _player = GetNode<Player>("Player");

        _invisible.Transparency = BaseMaterial3D.TransparencyEnum.Alpha;
        _invisible.AlbedoColor = new Color(0, 0, 0, 0);
        _invisible.ShadingMode = BaseMaterial3D.ShadingModeEnum.Unshaded;

        SetupSun();
        _info = ReadWorldJson();
        MakeMaterials();

        // Zones : les plus proches du départ sont chargées tout de suite, les autres en arrière-plan.
        Vector3 spawn = _info.Spawn is { Length: >= 3 } s ? new Vector3(s[0], s[1], s[2]) : new Vector3(0, 131, 0);
        var start = new Vector3(spawn.X, 0, spawn.Z);
        foreach (ZoneInfo z in _info.Zones)
        {
            var center = new Vector3(z.Center[0], 0, z.Center[2]);
            bool far = z.Name == "lointain";
            _pending.Add(new PendingZone
            {
                Name = z.Name,
                Path = $"{ZonesDir}/{z.File}",
                Center = center,
                Distance = far ? 0 : start.DistanceTo(center),
                AlwaysVisible = far,
            });
        }
        _pending.Sort((a, b) => a.Distance.CompareTo(b.Distance));
        while (_pending.Count > 0 && _pending[0].Distance < PreloadRadius)
        {
            PendingZone z = _pending[0];
            _pending.RemoveAt(0);
            AddZone(z, null);
        }
        foreach (PendingZone z in _pending) ResourceLoader.LoadThreadedRequest(z.Path);
        GD.Print($"Zones chargées au départ : {_world.GetChildCount()}, en arrière-plan : {_pending.Count}");

        SetupLamps();
        _player.GlobalPosition = spawn;
        _player.Rotation = new Vector3(0, Mathf.DegToRad(-70), 0); // regarde vers l'est (Sacré-Cœur)
        SpawnLouise(_player.GlobalPosition + new Vector3(0.94f, 0, -0.34f) * 4.5f + new Vector3(0, -0.18f, 0));

        string captureDir = "";
        foreach (string arg in OS.GetCmdlineUserArgs())
        {
            if (arg.StartsWith("--capture=")) captureDir = arg["--capture=".Length..];
            else if (arg.StartsWith("--views=")) _onlyViews = arg["--views=".Length..]; // morceaux de noms séparés par des virgules
        }
        if (captureDir != "")
        {
            _ = RunCapture(captureDir);
        }
        else
        {
            GetTree().CreateTimer(8.0).Timeout += () => GetNode<Label>("HUD/Aide").Hide();
        }
    }

    /// <summary>Louise Michel (personnage statique, res://personnages/louise_michel.glb), tournée vers le joueur.</summary>
    private void SpawnLouise(Vector3 position)
    {
        const string path = "res://personnages/louise_michel.glb";
        if (!ResourceLoader.Exists(path)) return;
        var louise = GD.Load<PackedScene>(path).Instantiate<Node3D>();
        louise.Name = "LouiseMichel";
        AddChild(louise);
        louise.GlobalPosition = position;
        Vector3 toPlayer = _player.GlobalPosition - position;
        louise.Rotation = new Vector3(0, Mathf.Atan2(toPlayer.X, toPlayer.Z), 0);

        var body = new StaticBody3D();
        var shape = new CollisionShape3D
        {
            Shape = new CapsuleShape3D { Radius = 0.36f, Height = 1.65f },
            Position = new Vector3(0, 0.83f, 0),
        };
        body.AddChild(shape);
        louise.AddChild(body);
    }

    public override void _UnhandledInput(InputEvent @event)
    {
        if (@event is not InputEventKey key || !key.Pressed) return;
        if (key.PhysicalKeycode == Key.Tab && OtherScene != "")
        {
            GetTree().ChangeSceneToFile(OtherScene);
        }
        else if (key.PhysicalKeycode == Key.C && !key.Echo)
        {
            ShowCommune = !ShowCommune;
            foreach (LoadedZone z in _zones) ApplyCommune(z.Node);
        }
    }

    /// <summary>Affiche ou masque les objets du décor de la Commune (et leurs collisions : barricades).</summary>
    private void ApplyCommune(Node node)
    {
        if (node is MeshInstance3D mesh && mesh.Name.ToString().Contains("commune"))
        {
            mesh.Visible = ShowCommune;
            foreach (Node child in mesh.GetChildren())
            {
                if (child is StaticBody3D body) body.CollisionLayer = ShowCommune ? 1u : 0u;
            }
        }
        foreach (Node child in node.GetChildren()) ApplyCommune(child);
    }

    private void SetupSun()
    {
        float az = Mathf.DegToRad(SunAzimuthDeg);
        float el = Mathf.DegToRad(SunElevationDeg);
        // x = est, y = haut, -z = nord
        var toSun = new Vector3(Mathf.Sin(az) * Mathf.Cos(el), Mathf.Sin(el), -Mathf.Cos(az) * Mathf.Cos(el));
        _sun.LookAtFromPosition(toSun, Vector3.Zero, Vector3.Up);
    }

    private WorldInfo ReadWorldJson()
    {
        using var file = FileAccess.Open($"{ZonesDir}/world.json", FileAccess.ModeFlags.Read);
        if (file == null)
        {
            GD.PushError("world.json absent : lancez d'abord blender/generate_montmartre.py");
            return new WorldInfo();
        }
        return JsonSerializer.Deserialize<WorldInfo>(file.GetAsText(), JsonOptions) ?? new WorldInfo();
    }

    /// <summary>
    /// Matériaux : décrits dans world.json, construits une seule fois et partagés par toutes les zones
    /// (les .glb ne contiennent que la géométrie, les UV et le nom des matériaux).
    /// </summary>
    private void MakeMaterials()
    {
        string dir = _info.MaterialsDir ?? "res://materiaux";
        foreach (MaterialInfo m in _info.Materials)
        {
            var mat = new StandardMaterial3D
            {
                ResourceName = m.Name,
                AlbedoColor = new Color(m.Color[0], m.Color[1], m.Color[2]),
                Roughness = m.Roughness,
                MetallicSpecular = 0.2f,
                TextureFilter = BaseMaterial3D.TextureFilterEnum.LinearWithMipmapsAnisotropic,
            };
            if (m.Albedo != null) mat.AlbedoTexture = LoadTexture($"{dir}/{m.Albedo}");
            if (m.UvScale is float k) mat.Uv1Scale = new Vector3(k, k, k);
            if (m.Emission != null)
            {
                mat.EmissionEnabled = true;
                mat.EmissionTexture = LoadTexture($"{dir}/{m.Emission}");
                mat.EmissionEnergyMultiplier = m.EmissionEnergy;
            }
            else if (m.EmissionColor != null)
            {
                mat.EmissionEnabled = true;
                mat.Emission = new Color(m.EmissionColor[0], m.EmissionColor[1], m.EmissionColor[2]);
                mat.EmissionEnergyMultiplier = m.EmissionEnergy;
            }
            if (m.DoubleSided) mat.CullMode = BaseMaterial3D.CullModeEnum.Disabled;
            _materials[m.Name] = mat;
        }
    }

    private static Texture2D LoadTexture(string path)
    {
        var texture = GD.Load<Texture2D>(path);
        if (texture == null)
        {
            GD.PushError($"Texture introuvable : {path}");
            return null;
        }
        Image image = texture.GetImage();
        if (image.IsCompressed()) image.Decompress();
        image.GenerateMipmaps();
        return ImageTexture.CreateFromImage(image);
    }

    private void ShareMaterials(Node node)
    {
        if (node is MeshInstance3D meshInstance && meshInstance.Mesh != null)
        {
            Mesh mesh = meshInstance.Mesh;
            for (int i = 0; i < mesh.GetSurfaceCount(); i++)
            {
                Material current = mesh.SurfaceGetMaterial(i);
                if (current != null && _materials.TryGetValue(current.ResourceName, out StandardMaterial3D shared))
                {
                    mesh.SurfaceSetMaterial(i, shared);
                }
            }
        }
        foreach (Node child in node.GetChildren()) ShareMaterials(child);
    }

    /// <summary>
    /// Réverbères : toutes les lanternes brillent (matériau émissif) ; seules les plus proches du joueur
    /// portent une vraie lumière, déplacée au fil de la marche, pour rester fluide.
    /// </summary>
    private void SetupLamps()
    {
        foreach (float[] l in _info.Lamps) _lamps.Add(new Vector3(l[0], l[1], l[2]));
        for (int i = 0; i < LampLights; i++)
        {
            var light = new OmniLight3D
            {
                LightColor = new Color(1.0f, 0.78f, 0.5f),
                LightEnergy = 2.2f,
                OmniRange = 13.0f,
                OmniAttenuation = 1.4f,
                ShadowEnabled = false,
            };
            AddChild(light);
            _lights.Add(light);
        }
        PlaceLampLights();
    }

    private void PlaceLampLights()
    {
        if (_lights.Count == 0 || _lamps.Count == 0) return;
        Camera3D camera = GetViewport().GetCamera3D();
        Vector3 p = camera?.GlobalPosition ?? _player.GlobalPosition;
        List<Vector3> nearest = _lamps
            .Where(l => p.DistanceSquaredTo(l) < 90f * 90f)
            .OrderBy(l => p.DistanceSquaredTo(l))
            .Take(_lights.Count)
            .ToList();
        for (int i = 0; i < _lights.Count; i++)
        {
            _lights[i].Visible = i < nearest.Count;
            if (i < nearest.Count) _lights[i].GlobalPosition = nearest[i];
        }
    }

    private void AddZone(PendingZone z, PackedScene scene)
    {
        scene ??= GD.Load<PackedScene>(z.Path);
        if (scene == null)
        {
            GD.PushError($"Zone introuvable : {z.Path}");
            return;
        }
        var instance = scene.Instantiate<Node3D>();
        instance.Name = z.Name;
        _world.AddChild(instance);
        ShareMaterials(instance);
        _bodies += AddCollisions(instance);
        ApplyCommune(instance);
        _zones.Add(new LoadedZone { Node = instance, Center = z.Center, AlwaysVisible = z.AlwaysVisible });
    }

    public bool AllZonesLoaded() => _pending.Count == 0;

    public override void _Process(double delta)
    {
        // une zone au plus par image, dès que son chargement en arrière-plan est terminé
        if (_pending.Count > 0)
        {
            PendingZone z = _pending[0];
            ResourceLoader.ThreadLoadStatus status = ResourceLoader.LoadThreadedGetStatus(z.Path);
            if (status == ResourceLoader.ThreadLoadStatus.Loaded)
            {
                _pending.RemoveAt(0);
                AddZone(z, ResourceLoader.LoadThreadedGet(z.Path) as PackedScene);
            }
            else if (status != ResourceLoader.ThreadLoadStatus.InProgress)
            {
                _pending.RemoveAt(0);
                AddZone(z, null);
            }
        }

        _lampTimer -= delta;
        if (_lampTimer <= 0)
        {
            _lampTimer = 0.4;
            PlaceLampLights();
            Camera3D camera = GetViewport().GetCamera3D();
            if (camera != null)
            {
                var p = new Vector3(camera.GlobalPosition.X, 0, camera.GlobalPosition.Z);
                foreach (LoadedZone z in _zones) z.Node.Visible = z.AlwaysVisible || p.DistanceTo(z.Center) < ViewDistance;
            }
        }
    }

    /// <summary>
    /// Collisions générées depuis le décor : un StaticBody3D + forme "trimesh" par maillage.
    /// Les objets dont le nom contient "NOCOL" (rues posées sur le terrain, marches, arbres) sont ignorés :
    /// on marche sur le terrain, qui épouse déjà la pente des rues et des escaliers.
    /// </summary>
    private int AddCollisions(Node node)
    {
        int count = 0;
        if (node is MeshInstance3D mesh && !mesh.Name.ToString().Contains("NOCOL"))
        {
            mesh.CreateTrimeshCollision();
            count++;
            if (mesh.Name.ToString().Contains("COLONLY")) // rampe invisible (escaliers de passerelle, tabliers)
            {
                mesh.SetSurfaceOverrideMaterial(0, _invisible);
            }
        }
        foreach (Node child in node.GetChildren()) count += AddCollisions(child);
        return count;
    }

    // ---------------------------------------------------------------------------------------------
    // Mode vérification (--capture)
    // ---------------------------------------------------------------------------------------------

    private SignalAwaiter NextFrame() => ToSignal(GetTree(), SceneTree.SignalName.ProcessFrame);
    private SignalAwaiter NextPhysicsFrame() => ToSignal(GetTree(), SceneTree.SignalName.PhysicsFrame);

    private async Task RunCapture(string dir)
    {
        GetNode<CanvasLayer>("HUD").Hide();
        DirAccess.MakeDirRecursiveAbsolute(dir);
        while (!AllZonesLoaded()) await NextFrame();
        GD.Print($"Zones chargées : {_world.GetChildCount()}, corps de collision : {_bodies}");
        if (_onlyViews != "")
        {
            await CaptureViews(dir);
            return;
        }

        // 1) le joueur tombe-t-il bien sur le sol ?
        Vector3 start = _player.GlobalPosition;
        for (int i = 0; i < 120; i++) await NextPhysicsFrame();
        GD.Print($"[test] sol : départ y={start.Y:F2} -> y={_player.GlobalPosition.Y:F2}, is_on_floor={_player.IsOnFloor()}");
        await Shot(dir, "00_joueur_depart");

        var louise = GetNodeOrNull<Node3D>("LouiseMichel");
        if (louise != null)
        {
            var louiseCamera = new Camera3D { Fov = 45 };
            AddChild(louiseCamera);
            Vector3 front = louise.GlobalTransform.Basis.Z;
            louiseCamera.LookAtFromPosition(
                louise.GlobalPosition + front * 4.2f + front.Cross(Vector3.Up) * 1.2f + new Vector3(0, 1.5f, 0),
                louise.GlobalPosition + new Vector3(0, 1.35f, 0), Vector3.Up);
            louiseCamera.MakeCurrent();
            await Shot(dir, "00b_louise_michel");
            louiseCamera.QueueFree();
            _player.GetNode<Camera3D>("Head/Camera3D").MakeCurrent();
        }

        // 2) marche 20 s vers l'est (pente + façades) : il doit avancer puis buter contre une façade
        Vector3 p0 = _player.GlobalPosition;
        _player.AutoMove = new Vector2(0, -1);
        int wallFrames = 0;
        for (int i = 0; i < 1200; i++)
        {
            await NextPhysicsFrame();
            if (_player.IsOnWall()) wallFrames++;
        }
        _player.AutoMove = Vector2.Zero;
        Vector3 p1 = _player.GlobalPosition;
        GD.Print($"[test] marche : {new Vector2(p1.X - p0.X, p1.Z - p0.Z).Length():F1} m parcourus, " +
                 $"dénivelé {p1.Y - p0.Y:F2} m, images au contact d'un mur={wallFrames}, is_on_floor={_player.IsOnFloor()}");
        await Shot(dir, "01_joueur_apres_marche");

        // 2b) passerelles : lâché au milieu du tablier, le joueur doit s'y poser (et non tomber dans l'eau)
        foreach (ViewInfo v in _info.Views.Where(v => v.Name.StartsWith("passerelle")))
        {
            _player.Velocity = Vector3.Zero;
            _player.GlobalPosition = new Vector3(v.Target[0], v.Target[1] + 5.0f, v.Target[2]);
            for (int i = 0; i < 150; i++) await NextPhysicsFrame();
            GD.Print($"[test] {v.Name} : posé à y={_player.GlobalPosition.Y:F2} (tablier attendu vers {v.Target[1] + 1.5f:F2}, " +
                     $"eau vers {v.Target[1] - 2.8f:F2}), is_on_floor={_player.IsOnFloor()}");
        }
        await CaptureViews(dir);
    }

    private async Task CaptureViews(string dir)
    {
        // 3) points de vue
        _player.Enabled = false;
        var camera = new Camera3D { Fov = 70, Far = 9000 };
        AddChild(camera);
        camera.MakeCurrent();
        string[] filters = _onlyViews == "" ? System.Array.Empty<string>() : _onlyViews.Split(',');
        int index = 2;
        foreach (ViewInfo v in _info.Views)
        {
            if (filters.Length > 0 && !filters.Any(f => v.Name.Contains(f))) continue;
            var from = new Vector3(v.Pos[0], v.Pos[1], v.Pos[2]);
            var to = new Vector3(v.Target[0], v.Target[1], v.Target[2]);
            if (v.Ground is { Length: >= 2 } ground) // vue sans altitude : posée sur le sol par lancer de rayon
            {
                from.Y = GroundY(from) + ground[0];
                to.Y = GroundY(to) + ground[1];
            }
            camera.LookAtFromPosition(from, to, Vector3.Up);
            PlaceLampLights();
            foreach (LoadedZone z in _zones) z.Node.Visible = true;
            await Shot(dir, $"{index:00}_{v.Name}");
            index++;
        }
        GD.Print($"[test] captures enregistrées dans {dir}");
        GetTree().Quit();
    }

    private float GroundY(Vector3 p)
    {
        var query = PhysicsRayQueryParameters3D.Create(new Vector3(p.X, 400, p.Z), new Vector3(p.X, -50, p.Z));
        Godot.Collections.Dictionary hit = GetWorld3D().DirectSpaceState.IntersectRay(query);
        return hit.ContainsKey("position") ? hit["position"].AsVector3().Y : 0f;
    }

    private async Task Shot(string dir, string name)
    {
        for (int i = 0; i < 4; i++) await NextFrame();
        await ToSignal(RenderingServer.Singleton, RenderingServer.SignalName.FramePostDraw);
        GetViewport().GetTexture().GetImage().SavePng($"{dir}/{name}.png");
    }
}
