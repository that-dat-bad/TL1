# -*- coding: utf-8 -*-
"""
UI (ai_terrain.py) と MCP (mcp_server.py) の両方から呼び出される
ブループリント適用・ハイトマップ生成・ベイク・Blenderメッシュ構築の共通パイプライン。
"""
import os
import tempfile
import numpy as np  # type: ignore

try:
    from .blueprint_store import load_blueprint, save_blueprint, apply_blueprint_patch, normalize_blueprint
    from .terrain_blueprint import compile_blueprint
    from .heightmap_engine import (
        generate_heightmap,
        save_heightmap_bundle,
        heightmap_to_blender_image,
    )
    from .terrain_baker import bake_terrain_textures, apply_baked_textures_to_blender_material
    from .terrain_materials import detect_biomes, detect_biome, detect_road_type
    from .water_mesh_builder import build_river_mesh, build_ocean_mesh, sync_river_curves_to_scene
except ImportError:
    from blueprint_store import load_blueprint, save_blueprint, apply_blueprint_patch, normalize_blueprint
    from terrain_blueprint import compile_blueprint
    from heightmap_engine import (
        generate_heightmap,
        save_heightmap_bundle,
        heightmap_to_blender_image,
    )
    from terrain_baker import bake_terrain_textures, apply_baked_textures_to_blender_material
    from terrain_materials import detect_biomes, detect_biome, detect_road_type
    from water_mesh_builder import build_river_mesh, build_ocean_mesh, sync_river_curves_to_scene


def get_terrain_cache_dir():
    """ハイトマップ・ベイクテクスチャの保存先ディレクトリを返す"""
    import bpy  # type: ignore

    if bpy.data.filepath:
        base = os.path.dirname(bpy.data.filepath)
    else:
        base = tempfile.gettempdir()
    cache_dir = os.path.join(base, "tl1_terrain_cache")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def build_terrain_mesh_from_heightmap(context, heightmap, meta, preview_res=384, obj_name="Terrain"):
    """
    2D float32 ハイトマップから軽量ビューポート用プレビューメッシュ (UV付き) を高速生成する。
    """
    import bpy  # type: ignore

    full_res = heightmap.shape[0]
    step = max(1, full_res // int(preview_res))
    sub_h = heightmap[::step, ::step]
    ny, nx = sub_h.shape

    size_x = float(meta.get("terrain_size_x", 40000.0))
    size_y = float(meta.get("terrain_size_y", size_x))
    half_x = size_x * 0.5
    half_y = size_y * 0.5

    xs = np.linspace(-half_x, half_x, nx, dtype=np.float32)
    ys = np.linspace(-half_y, half_y, ny, dtype=np.float32)
    gx, gy = np.meshgrid(xs, ys, indexing="xy")

    verts_arr = np.column_stack([gx.ravel(), gy.ravel(), sub_h.ravel()])

    # クワッドインデックスをベクトル化生成
    ix = np.arange(nx - 1, dtype=np.int32)
    iy = np.arange(ny - 1, dtype=np.int32)
    grid_x, grid_y = np.meshgrid(ix, iy, indexing="xy")
    v0 = grid_y * nx + grid_x
    v1 = v0 + 1
    v2 = v0 + nx + 1
    v3 = v0 + nx
    faces_arr = np.column_stack([v0.ravel(), v1.ravel(), v2.ravel(), v3.ravel()])

    # 既存 Terrain オブジェクトがあれば再利用/差し替え
    terrain_obj = bpy.data.objects.get(obj_name)
    mesh = bpy.data.meshes.new(f"{obj_name}Mesh")
    mesh.from_pydata(verts_arr.tolist(), [], faces_arr.tolist())
    mesh.update(calc_edges=True)

    # UV レイヤー生成 (ワールド [0, 1] x [0, 1])
    uv_layer = mesh.uv_layers.new(name="UVMap")
    u_coords = (gx.ravel() + half_x) / max(size_x, 1.0)
    v_coords = (gy.ravel() + half_y) / max(size_y, 1.0)
    loop_verts = faces_arr.ravel()
    uvs = np.column_stack([u_coords[loop_verts], v_coords[loop_verts]]).astype(np.float32)
    uv_layer.data.foreach_set("uv", uvs.ravel())

    # スムーズシェーディング
    poly_count = len(mesh.polygons)
    if poly_count > 0:
        mesh.polygons.foreach_set("use_smooth", [True] * poly_count)

    if terrain_obj is None:
        terrain_obj = bpy.data.objects.new(obj_name, mesh)
        context.collection.objects.link(terrain_obj)
    else:
        old_mesh = terrain_obj.data
        terrain_obj.data = mesh
        # 既存の TerrainGen モディファイアがあれば無効化（二重変位防止）
        gn_mod = terrain_obj.modifiers.get("TerrainGen")
        if gn_mod:
            gn_mod.show_viewport = False
            gn_mod.show_render = False
        if old_mesh and old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)

    return terrain_obj


def execute_blueprint_pipeline(
    context,
    blueprint_or_patch,
    preset="AUTO",
    terrain_scale="40KM",
    biome="AUTO",
    prompt="",
    seed=0,
    resolution=1024,
    is_patch=False,
    operator=None,
):
    """
    ブループリント（新規または差分パッチ）から
    コンパイル -> スプライン生成 -> NumPyハイトマップ＆侵食 -> ベイク -> メッシュ構築
    までを一気通貫で実行する。
    """
    import bpy  # type: ignore

    scene = context.scene
    if is_patch or (isinstance(blueprint_or_patch, dict) and "operations" in blueprint_or_patch):
        current_bp, current_meta = load_blueprint(scene)
        final_bp = apply_blueprint_patch(current_bp or {}, blueprint_or_patch)
        if not prompt and current_meta:
            prompt = current_meta.get("prompt", "")
        if seed <= 0 and current_meta:
            seed = int(current_meta.get("seed", 1) or 1)
        if biome == "AUTO" and current_meta and current_meta.get("biome"):
            biome = current_meta.get("biome", "AUTO")
        if terrain_scale == "40KM" and current_meta and current_meta.get("terrain_scale"):
            terrain_scale = current_meta.get("terrain_scale", "40KM")
    else:
        final_bp = normalize_blueprint(blueprint_or_patch)

    active_seed = int(seed) if int(seed) > 0 else 1
    meta_to_save = {
        "preset": preset,
        "terrain_scale": terrain_scale,
        "biome": biome,
        "prompt": prompt,
        "seed": active_seed,
        "resolution": int(resolution),
    }
    save_blueprint(scene, final_bp, meta_to_save)

    compiled = compile_blueprint(
        final_bp,
        preset=preset,
        terrain_scale=terrain_scale,
        prompt=prompt,
        seed=active_seed,
    )

    if operator is not None and hasattr(operator, "generate_splines"):
        operator.generate_splines(context, compiled)

    # ハイトマップ & 侵食計算
    droplets = 24000 if resolution <= 1024 else 42000
    heightmap, flow_map, hm_meta, shore_sdf = generate_heightmap(
        compiled,
        resolution=int(resolution),
        seed=active_seed,
        hydraulic_droplets=droplets,
        thermal_iterations=18,
    )

    cache_dir = get_terrain_cache_dir()
    save_heightmap_bundle(cache_dir, heightmap, flow_map, hm_meta)
    heightmap_to_blender_image(heightmap, name="Terrain_Heightmap")

    # バイオーム判定 & テクスチャベイク
    sub_biomes = detect_biomes(prompt, biome)
    detected_biome = detect_biome(prompt, biome)
    tex_paths = bake_terrain_textures(
        cache_dir,
        heightmap,
        flow_map,
        hm_meta,
        biome=detected_biome,
        sub_biomes=sub_biomes,
        shore_sdf=shore_sdf,
    )

    # 水面メッシュ（川・海）& 編集用川カーブ生成
    compiled_rivers = hm_meta.get("rivers", [])
    sync_river_curves_to_scene(context, compiled_rivers)
    build_river_mesh(context, compiled_rivers)
    build_ocean_mesh(
        context,
        hm_meta.get("water_level"),
        size_x=float(hm_meta.get("terrain_size_x", 40000.0)),
    )

    # 軽量ビューポートメッシュ生成 & ベイクマテリアル適用
    terrain_obj = build_terrain_mesh_from_heightmap(
        context,
        heightmap,
        hm_meta,
        preview_res=512,
        obj_name="Terrain",
    )
    terrain_obj["tl1_heightmap_dir"] = cache_dir
    terrain_obj["tl1_biome"] = detected_biome
    apply_baked_textures_to_blender_material(
        terrain_obj,
        albedo_path=tex_paths.get("albedo"),
        normal_path=tex_paths.get("normal"),
    )

    context.view_layer.update()
    context.evaluated_depsgraph_get().update()

    # 道路投影・建物配置（operator が渡されている場合）
    if operator is not None:
        road_obj = bpy.data.objects.get("RoadPath_AI")
        if road_obj and hasattr(operator, "project_road_to_terrain"):
            operator.project_road_to_terrain(
                context,
                road_obj,
                terrain_obj,
                water_level=compiled.get("water_level"),
                valley_radius=compiled.get("valley_radius", 1500.0),
                mountain_radius=compiled.get("mountain_radius", 1400.0),
                has_tunnels=compiled.get("has_tunnels", False),
            )
        if compiled.get("has_city") and getattr(operator, "_generator", None):
            try:
                lots = operator._generator.generate_building_lots()
                if lots and hasattr(operator, "spawn_buildings"):
                    operator.spawn_buildings(context, lots, terrain_obj, detected_biome, sub_biomes=sub_biomes)
            except Exception as e:
                print(f"[TerrainPipeline] Building generation skipped: {e}")
        else:
            b_col = bpy.data.collections.get("Buildings")
            if b_col and hasattr(operator, "clear_ai_objects"):
                operator.clear_ai_objects(b_col)

    return final_bp, hm_meta, tex_paths


def read_splines_from_collection(collection_name):
    """
    Blender シーン内の指定コレクションから、ユーザーが編集したカーブの
    ワールド座標制御点リスト（co, radius, tilt）を読み取る。
    """
    import bpy  # type: ignore

    col = bpy.data.collections.get(collection_name)
    if not col:
        return []

    splines_out = []
    for obj in col.objects:
        if obj.type != 'CURVE' or not obj.data:
            continue
        mw = obj.matrix_world
        for sp in obj.data.splines:
            pts = []
            if sp.type == 'BEZIER':
                for bp in sp.bezier_points:
                    wco = mw @ bp.co
                    pts.append({
                        "co": [float(wco.x), float(wco.y), float(wco.z)],
                        "radius": float(bp.radius),
                        "tilt": float(bp.tilt),
                    })
            elif sp.type == 'POLY':
                for pt in sp.points:
                    wco = mw @ pt.co.xyz
                    pts.append({
                        "co": [float(wco.x), float(wco.y), float(wco.z)],
                        "radius": float(pt.radius),
                        "tilt": float(pt.tilt),
                    })
            if len(pts) >= 2:
                splines_out.append(pts)
    return splines_out


def rebuild_heightmap_from_scene_curves(context, resolution=None):
    """
    シーン上で手動編集された Mountains / Valleys / Roads カーブを読み取り、
    ハイトマップ・侵食・テクスチャベイク・Terrainメッシュを再構築する。
    """
    import bpy  # type: ignore

    scene = context.scene
    bp, meta = load_blueprint(scene)
    if not bp:
        raise RuntimeError("シーンにブループリントが保存されていません。先にAI地形生成を実行してください。")

    preset = meta.get("preset", "AUTO")
    terrain_scale = meta.get("terrain_scale", "40KM")
    biome = meta.get("biome", "AUTO")
    prompt = meta.get("prompt", "")
    seed = int(meta.get("seed", 1) or 1)
    res = int(resolution or meta.get("resolution", 1024) or 1024)

    compiled = compile_blueprint(
        bp,
        preset=preset,
        terrain_scale=terrain_scale,
        prompt=prompt,
        seed=seed,
    )

    # シーン上のカーブ（ユーザー移動・編集後）で山脈・谷・道路・川を上書き
    scene_mt = read_splines_from_collection("Mountains")
    scene_vl = read_splines_from_collection("Valleys")
    scene_rd = read_splines_from_collection("Roads")
    scene_rv = read_splines_from_collection("Rivers")
    if scene_mt is not None:
        compiled["mountains"] = scene_mt
    if scene_vl is not None:
        compiled["valleys"] = scene_vl
    if scene_rd:
        compiled["roads"] = scene_rd
    if scene_rv:
        compiled["rivers"] = [{"pts": sp, "width": 120.0, "depth": 18.0} for sp in scene_rv]

    droplets = 24000 if res <= 1024 else 42000
    heightmap, flow_map, hm_meta, shore_sdf = generate_heightmap(
        compiled,
        resolution=res,
        seed=seed,
        hydraulic_droplets=droplets,
        thermal_iterations=18,
    )

    cache_dir = get_terrain_cache_dir()
    save_heightmap_bundle(cache_dir, heightmap, flow_map, hm_meta)
    heightmap_to_blender_image(heightmap, name="Terrain_Heightmap")

    sub_biomes = detect_biomes(prompt, biome)
    detected_biome = detect_biome(prompt, biome)
    tex_paths = bake_terrain_textures(
        cache_dir,
        heightmap,
        flow_map,
        hm_meta,
        biome=detected_biome,
        sub_biomes=sub_biomes,
        shore_sdf=shore_sdf,
    )

    compiled_rivers = hm_meta.get("rivers", [])
    build_river_mesh(context, compiled_rivers)
    build_ocean_mesh(
        context,
        hm_meta.get("water_level"),
        size_x=float(hm_meta.get("terrain_size_x", 40000.0)),
    )

    terrain_obj = build_terrain_mesh_from_heightmap(
        context,
        heightmap,
        hm_meta,
        preview_res=512,
        obj_name="Terrain",
    )
    terrain_obj["tl1_heightmap_dir"] = cache_dir
    terrain_obj["tl1_biome"] = detected_biome
    apply_baked_textures_to_blender_material(
        terrain_obj,
        albedo_path=tex_paths.get("albedo"),
        normal_path=tex_paths.get("normal"),
    )

    context.view_layer.update()
    context.evaluated_depsgraph_get().update()
    return hm_meta, tex_paths
