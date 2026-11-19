using System.Collections.Generic;

/// <summary>
/// Contenu de world.json, écrit par blender/generate_montmartre.py pour chaque quartier.
/// Les noms des champs JSON sont en snake_case (spawn, materials_dir, uv_scale...) :
/// la conversion est faite par JsonNamingPolicy.SnakeCaseLower dans Main.cs.
/// </summary>
public class WorldInfo
{
    public float[] Spawn { get; set; }
    public string MaterialsDir { get; set; } = "res://materiaux";
    public List<ZoneInfo> Zones { get; set; } = new();
    public List<ViewInfo> Views { get; set; } = new();
    public List<float[]> Lamps { get; set; } = new();
    public List<MaterialInfo> Materials { get; set; } = new();
}

/// <summary>Une zone de décor (un fichier .glb d'environ 200 m de côté).</summary>
public class ZoneInfo
{
    public string Name { get; set; }
    public string File { get; set; }
    public float[] Center { get; set; }
}

/// <summary>Un point de vue de contrôle, utilisé par le mode --capture.</summary>
public class ViewInfo
{
    public string Name { get; set; }
    public float[] Pos { get; set; }
    public float[] Target { get; set; }
    /// <summary>Facultatif : hauteurs au-dessus du sol (caméra, cible) quand la vue n'a pas d'altitude.</summary>
    public float[] Ground { get; set; }
}

/// <summary>Un matériau partagé par toutes les zones.</summary>
public class MaterialInfo
{
    public string Name { get; set; }
    public float[] Color { get; set; }
    public string Albedo { get; set; }
    public float? UvScale { get; set; }
    public string Emission { get; set; }
    public float[] EmissionColor { get; set; }
    public float EmissionEnergy { get; set; } = 1.0f;
    public float Roughness { get; set; } = 0.9f;
    public bool DoubleSided { get; set; }
}
