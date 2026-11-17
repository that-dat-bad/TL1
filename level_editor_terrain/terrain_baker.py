# -*- coding: utf-8 -*-
"""
Pure NumPy + 標準 zlib による地形テクスチャベイクモジュール。
ハイトマップ・傾斜・曲率・流路マスクから Albedo / Normal / SplatMap (RGBA PNG) を生成する。
外部画像ライブラリ（Pillow等）不要。
"""
import os
import struct
import zlib
import numpy as np  # type: ignore


def write_png_rgba(filepath, rgba_uint8):
    """
    (H, W, 4) uint8 配列を標準ライブラリ zlib のみで RGBA PNG として保存する。
    """
    h, w, c = rgba_uint8.shape
    assert c == 4, "rgba_uint8 must have 4 channels"

    # PNG の各行先頭にフィルタタイプ 0 (None) を付与
    raw_rows = np.zeros((h, w * 4 + 1), dtype=np.uint8)
    raw_rows[:, 1:] = rgba_uint8.reshape(h, w * 4)
    compressed = zlib.compress(raw_rows.tobytes(), level=6)

    def _chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)  # 8bit RGBA
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", compressed)
        + _chunk(b"IEND", b"")
    )

    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(png_bytes)
    return filepath


def compute_normals_and_curvature(heightmap, cell_size):
    """
    ハイトマップから法線ベクトル (nx, ny, nz) と曲率 (curvature) を算出する。
    """
    gy, gx = np.gradient(heightmap.astype(np.float32), float(cell_size))
    nx = -gx
    ny = -gy
    nz = np.ones_like(gx, dtype=np.float32)
    inv_len = 1.0 / np.sqrt(nx * nx + ny * ny + nz * nz)
    nx *= inv_len
    ny *= inv_len
    nz *= inv_len

    # 簡易ラプラシアン曲率（正=凸/尾根、負=凹/谷）
    lap = (
        np.roll(heightmap, 1, axis=0)
        + np.roll(heightmap, -1, axis=0)
        + np.roll(heightmap, 1, axis=1)
        + np.roll(heightmap, -1, axis=1)
        - 4.0 * heightmap
    ) / max(float(cell_size), 1.0)
    lap[0, :] = 0.0
    lap[-1, :] = 0.0
    lap[:, 0] = 0.0
    lap[:, -1] = 0.0

    return nx, ny, nz, np.clip(lap * 1.5, -1.0, 1.0)


def _biome_palette(biome):
    """バイオームごとの (平地色, 崖/岩色, 山頂/雪色, 湿潤/谷底色)"""
    b = (biome or "PLAINS").upper()
    palettes = {
        "PLAINS": (
            np.array([0.22, 0.36, 0.14], dtype=np.float32),  # 草原
            np.array([0.36, 0.31, 0.26], dtype=np.float32),  # 岩壁
            np.array([0.88, 0.91, 0.95], dtype=np.float32),  # 雪
            np.array([0.16, 0.24, 0.12], dtype=np.float32),  # 湿潤谷底
        ),
        "DESERT": (
            np.array([0.76, 0.56, 0.34], dtype=np.float32),  # 砂丘
            np.array([0.52, 0.28, 0.18], dtype=np.float32),  # 赤岩崖
            np.array([0.82, 0.68, 0.48], dtype=np.float32),  # 乾燥高地
            np.array([0.46, 0.38, 0.24], dtype=np.float32),  # 枯れ川ワジ
        ),
        "SNOW": (
            np.array([0.84, 0.88, 0.94], dtype=np.float32),  # 雪原
            np.array([0.24, 0.28, 0.36], dtype=np.float32),  # 氷岩壁
            np.array([0.96, 0.98, 1.00], dtype=np.float32),  # 新雪山頂
            np.array([0.52, 0.62, 0.72], dtype=np.float32),  # 氷河谷
        ),
        "CANYON": (
            np.array([0.66, 0.34, 0.20], dtype=np.float32),  # 赤土台地
            np.array([0.44, 0.20, 0.14], dtype=np.float32),  # テラコッタ崖
            np.array([0.78, 0.52, 0.36], dtype=np.float32),  # 乾燥尾根
            np.array([0.32, 0.22, 0.16], dtype=np.float32),  # 峡谷底
        ),
        "VOLCANO": (
            np.array([0.14, 0.14, 0.15], dtype=np.float32),  # 玄武岩灰
            np.array([0.24, 0.16, 0.14], dtype=np.float32),  # 溶岩崖
            np.array([0.38, 0.22, 0.18], dtype=np.float32),  # 火山礫山頂
            np.array([0.09, 0.09, 0.10], dtype=np.float32),  # 溶岩流路
        ),
    }
    return palettes.get(b, palettes["PLAINS"])


def generate_baked_maps(heightmap, flow_map, cell_size, biome="MULTI", sub_biomes=None):
    """
    ハイトマップと流路マップから (splat_rgba, albedo_rgba, normal_rgba) の uint8 配列を生成する。
    """
    res_y, res_x = heightmap.shape
    nx, ny, nz, curv = compute_normals_and_curvature(heightmap, cell_size)

    # 傾斜度 (0=平坦, 1=垂直崖)
    slope = np.clip((1.0 - nz) * 4.5, 0.0, 1.0)
    rock_mask = np.clip((slope - 0.18) * 2.4, 0.0, 1.0)

    h_min = float(np.min(heightmap))
    h_max = float(np.max(heightmap))
    h_span = max(h_max - h_min, 1.0)
    h_norm = np.clip((heightmap - h_min) / h_span, 0.0, 1.0)

    # 雪・山頂マスク（標高が高く、かつ急すぎない斜面）
    snow_mask = np.clip((h_norm - 0.68) * 4.0, 0.0, 1.0) * np.clip(1.0 - rock_mask * 0.75, 0.0, 1.0)

    # 湿潤・流路マスク
    if flow_map is not None and flow_map.shape == heightmap.shape:
        wet_mask = np.clip(flow_map * 1.15, 0.0, 1.0) * (1.0 - rock_mask * 0.6)
    else:
        wet_mask = np.zeros_like(heightmap, dtype=np.float32)

    # 地表ベース（草/砂）
    ground_mask = np.clip(1.0 - np.maximum(rock_mask, snow_mask), 0.0, 1.0)
    w_sum = np.maximum(ground_mask + rock_mask + snow_mask + wet_mask, 1e-4)
    r_ch = ground_mask / w_sum
    g_ch = rock_mask / w_sum
    b_ch = snow_mask / w_sum
    a_ch = wet_mask / w_sum

    splat_rgba = np.stack([r_ch, g_ch, b_ch, a_ch], axis=-1)
    splat_uint8 = np.clip(splat_rgba * 255.0, 0, 255).astype(np.uint8)

    # Albedo カラー合成
    b_key = (biome or "MULTI").upper()
    if b_key == "MULTI":
        # 複合大陸: 空間座標で PLAINS / DESERT / CANYON を緩やかにブレンド
        ys = np.linspace(-1.0, 1.0, res_y, dtype=np.float32)[:, None]
        xs = np.linspace(-1.0, 1.0, res_x, dtype=np.float32)[None, :]
        region_val = 0.5 + 0.5 * np.sin(xs * 2.3 + 0.4) * np.cos(ys * 2.1 - 0.3)

        p_pl = _biome_palette("PLAINS")
        p_ds = _biome_palette("DESERT")
        p_cn = _biome_palette("CANYON")

        t_dry = np.clip((region_val - 0.35) * 2.5, 0.0, 1.0)[:, :, None]
        t_can = np.clip((region_val - 0.68) * 3.5, 0.0, 1.0)[:, :, None]

        c_ground = p_pl[0] * (1.0 - t_dry) + p_ds[0] * t_dry
        c_ground = c_ground * (1.0 - t_can) + p_cn[0] * t_can
        c_rock = p_pl[1] * (1.0 - t_dry) + p_cn[1] * t_dry
        c_snow = p_pl[2]
        c_wet = p_pl[3] * (1.0 - t_dry) + p_ds[3] * t_dry
    else:
        c_ground, c_rock, c_snow, c_wet = _biome_palette(b_key)

    albedo = (
        c_ground * r_ch[:, :, None]
        + c_rock * g_ch[:, :, None]
        + c_snow * b_ch[:, :, None]
        + c_wet * a_ch[:, :, None]
    )

    # 曲率による微細明暗（尾根をわずかに明るく、溝を暗くして立体感を強調）
    ao_shade = np.clip(1.0 + curv * 0.18, 0.72, 1.20)[:, :, None]
    albedo = np.clip(albedo * ao_shade, 0.0, 1.0)

    albedo_rgba = np.ones((res_y, res_x, 4), dtype=np.float32)
    albedo_rgba[:, :, :3] = albedo
    albedo_uint8 = np.clip(albedo_rgba * 255.0, 0, 255).astype(np.uint8)

    # Normal Map (RGBA)
    normal_rgba = np.ones((res_y, res_x, 4), dtype=np.float32)
    normal_rgba[:, :, 0] = nx * 0.5 + 0.5
    normal_rgba[:, :, 1] = ny * 0.5 + 0.5
    normal_rgba[:, :, 2] = nz * 0.5 + 0.5
    normal_uint8 = np.clip(normal_rgba * 255.0, 0, 255).astype(np.uint8)

    return splat_uint8, albedo_uint8, normal_uint8


def bake_terrain_textures(output_dir, heightmap, flow_map, meta, biome="MULTI", sub_biomes=None, shore_sdf=None):
    """
    Splat / Albedo / Normal (+ 任意で Shore SDF) の PNG を出力し、パス辞書を返す。
    """
    cell_size = float(meta.get("cell_size", 40.0))
    splat_u8, albedo_u8, normal_u8 = generate_baked_maps(
        heightmap,
        flow_map,
        cell_size=cell_size,
        biome=biome,
        sub_biomes=sub_biomes,
    )

    os.makedirs(output_dir, exist_ok=True)
    splat_path = write_png_rgba(os.path.join(output_dir, "terrain_splat.png"), splat_u8)
    albedo_path = write_png_rgba(os.path.join(output_dir, "terrain_albedo.png"), albedo_u8)
    normal_path = write_png_rgba(os.path.join(output_dir, "terrain_normal.png"), normal_u8)

    result = {
        "splat": splat_path,
        "albedo": albedo_path,
        "normal": normal_path,
    }
    if shore_sdf is not None:
        sdf_u8 = np.zeros((shore_sdf.shape[0], shore_sdf.shape[1], 4), dtype=np.uint8)
        val = np.clip(shore_sdf * 255.0, 0, 255).astype(np.uint8)
        sdf_u8[:, :, 0] = val
        sdf_u8[:, :, 1] = val
        sdf_u8[:, :, 2] = val
        sdf_u8[:, :, 3] = 255
        result["shore_sdf"] = write_png_rgba(os.path.join(output_dir, "shore_sdf.png"), sdf_u8)
    return result


def apply_baked_textures_to_blender_material(terrain_obj, albedo_path, normal_path=None):
    """
    ベイク済み Albedo / Normal PNG を Blender マテリアルとして Terrain に適用する。
    .obj / .mtl エクスポート時にもテクスチャ参照がそのまま出力される。
    """
    import bpy  # type: ignore

    mat_name = "Terrain_Baked_PBR"
    mat = bpy.data.materials.get(mat_name)
    if not mat:
        mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    if "Roughness" in bsdf.inputs:
        bsdf.inputs["Roughness"].default_value = 0.88
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-450, 0)

    if albedo_path and os.path.exists(albedo_path):
        img_alb = bpy.data.images.load(albedo_path, check_existing=True)
        tex_alb = nodes.new("ShaderNodeTexImage")
        tex_alb.location = (-150, 150)
        tex_alb.image = img_alb
        links.new(tex_coord.outputs["UV"], tex_alb.inputs["Vector"])
        links.new(tex_alb.outputs["Color"], bsdf.inputs["Base Color"])

    if normal_path and os.path.exists(normal_path):
        img_nrm = bpy.data.images.load(normal_path, check_existing=True)
        try:
            img_nrm.colorspace_settings.name = "Non-Color"
        except Exception:
            pass
        tex_nrm = nodes.new("ShaderNodeTexImage")
        tex_nrm.location = (-150, -180)
        tex_nrm.image = img_nrm
        nrm_map = nodes.new("ShaderNodeNormalMap")
        nrm_map.location = (90, -180)
        nrm_map.inputs["Strength"].default_value = 0.85
        links.new(tex_coord.outputs["UV"], tex_nrm.inputs["Vector"])
        links.new(tex_nrm.outputs["Color"], nrm_map.inputs["Color"])
        links.new(nrm_map.outputs["Normal"], bsdf.inputs["Normal"])

    if terrain_obj and terrain_obj.data:
        terrain_obj.data.materials.clear()
        terrain_obj.data.materials.append(mat)
    return mat
