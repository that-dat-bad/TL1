# -*- coding: utf-8 -*-
import bpy  # type: ignore

def detect_biome(prompt, user_choice='AUTO'):
    """プロンプトまたはユーザー選択からバイオームを判定"""
    if user_choice and user_choice != 'AUTO':
        return user_choice
        
    p = prompt.lower()
    if any(k in p for k in ['砂漠', '砂', 'desert', 'sand', 'オアシス', 'oasis', 'デューン', 'dune', 'サハラ']):
        return 'DESERT'
    elif any(k in p for k in ['雪', '氷', 'snow', 'winter', 'ice', '寒冷', 'ツンドラ', 'tundra', '雪原']):
        return 'SNOW'
    elif any(k in p for k in ['岩', '峡谷', 'キャニオン', 'canyon', '荒野', 'badlands', '赤土', 'グランドキャニオン']):
        return 'CANYON'
    elif any(k in p for k in ['火山', '溶岩', 'volcano', 'lava', 'マグマ', '玄武岩', 'dark']):
        return 'VOLCANO'
    else:
        return 'PLAINS'


def get_or_create_terrain_material(biome='PLAINS'):
    """バイオームに応じた傾斜対応プロシージャルシェーダーマテリアルを構築"""
    mat_name = f"Terrain_Biome_{biome}"
    mat = bpy.data.materials.get(mat_name)
    if mat:
        return mat

    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # 出力ノード
    node_out = nodes.new('ShaderNodeOutputMaterial')
    node_out.location = (800, 0)

    # Principled BSDF
    node_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    node_bsdf.location = (550, 0)
    links.new(node_bsdf.outputs['BSDF'], node_out.inputs['Surface'])

    # 1. 傾斜（Normal Z成分）の取得用ノード
    node_geom = nodes.new('ShaderNodeNewGeometry')
    node_geom.location = (-600, 200)

    node_sep = nodes.new('ShaderNodeSeparateXYZ')
    node_sep.location = (-400, 200)
    links.new(node_geom.outputs['Normal'], node_sep.inputs['Vector'])

    # 傾斜用 ColorRamp (Z=1.0が平坦、Z=0.0が急峻な崖)
    ramp_slope = nodes.new('ShaderNodeValToRGB')
    ramp_slope.location = (-150, 200)
    links.new(node_sep.outputs['Z'], ramp_slope.inputs['Fac'])

    # 2. 質感用の微小ノイズテクスチャ
    node_texcoord = nodes.new('ShaderNodeTexCoord')
    node_texcoord.location = (-600, -200)

    node_noise = nodes.new('ShaderNodeTexNoise')
    node_noise.location = (-400, -200)
    node_noise.inputs['Scale'].default_value = 0.05
    node_noise.inputs['Detail'].default_value = 4.0
    node_noise.inputs['Roughness'].default_value = 0.6
    links.new(node_texcoord.outputs['Object'], node_noise.inputs['Vector'])

    # ノイズ用 ColorRamp
    ramp_noise = nodes.new('ShaderNodeValToRGB')
    ramp_noise.location = (-150, -200)
    links.new(node_noise.outputs['Fac'], ramp_noise.inputs['Fac'])

    # 3. 平坦部のカラーミックス
    mix_flat = nodes.new('ShaderNodeMix')
    try:
        mix_flat.data_type = 'RGBA'
    except AttributeError:
        pass
    mix_flat.location = (150, -100)
    
    # 4. 崖と平坦部の最終カラーミックス
    mix_final = nodes.new('ShaderNodeMix')
    try:
        mix_final.data_type = 'RGBA'
    except AttributeError:
        pass
    mix_final.location = (350, 50)

    # 互換性ソケット取得
    def get_socket(node, *names):
        for n in names:
            if n in node.inputs:
                return node.inputs[n]
        return node.inputs[0]

    def get_output_socket(node, *names):
        for n in names:
            if n in node.outputs:
                return node.outputs[n]
        return node.outputs[0]

    # --- バイオーム別のカラーパレット設定 ---
    if biome == 'DESERT':
        # 砂漠: オレンジ・黄色の砂紋 + 崖は赤褐色の岩肌
        # 平坦部の砂 (イエローサンド 〜 オレンジサンド)
        c_sand1 = (0.88, 0.72, 0.42, 1.0) # 明るい砂
        c_sand2 = (0.76, 0.52, 0.28, 1.0) # オレンジがかった砂
        c_cliff = (0.50, 0.28, 0.16, 1.0) # 赤褐色の崖・岩
        mat.diffuse_color = (0.86, 0.70, 0.40, 1.0)

        ramp_noise.color_ramp.elements[0].color = c_sand1
        ramp_noise.color_ramp.elements[1].color = c_sand2

        ramp_slope.color_ramp.elements[0].position = 0.70  # 急斜面
        ramp_slope.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0) # 崖カラー側
        ramp_slope.color_ramp.elements[1].position = 0.88  # なだらか
        ramp_slope.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0) # 平坦側

        node_bsdf.inputs['Roughness'].default_value = 0.85

    elif biome == 'SNOW':
        # 雪山: 純白の雪原 + 崖は冷たい青灰色の岩壁
        c_snow1 = (0.95, 0.97, 1.0, 1.0)
        c_snow2 = (0.82, 0.88, 0.95, 1.0)
        c_cliff = (0.28, 0.32, 0.38, 1.0)
        mat.diffuse_color = (0.92, 0.95, 0.98, 1.0)

        ramp_noise.color_ramp.elements[0].color = c_snow1
        ramp_noise.color_ramp.elements[1].color = c_snow2

        ramp_slope.color_ramp.elements[0].position = 0.75
        ramp_slope.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
        ramp_slope.color_ramp.elements[1].position = 0.90
        ramp_slope.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)

        node_bsdf.inputs['Roughness'].default_value = 0.4

    elif biome == 'CANYON':
        # 峡谷: 赤土・テラコッタ層
        c_layer1 = (0.78, 0.45, 0.28, 1.0)
        c_layer2 = (0.65, 0.35, 0.20, 1.0)
        c_cliff = (0.45, 0.22, 0.14, 1.0)
        mat.diffuse_color = (0.75, 0.42, 0.25, 1.0)

        ramp_noise.color_ramp.elements[0].color = c_layer1
        ramp_noise.color_ramp.elements[1].color = c_layer2

        ramp_slope.color_ramp.elements[0].position = 0.65
        ramp_slope.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
        ramp_slope.color_ramp.elements[1].position = 0.85
        ramp_slope.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)

        node_bsdf.inputs['Roughness'].default_value = 0.8

    elif biome == 'VOLCANO':
        # 火山: 黒い玄武岩・灰 + 赤黒い崖
        c_ash1 = (0.15, 0.15, 0.16, 1.0)
        c_ash2 = (0.25, 0.22, 0.22, 1.0)
        c_cliff = (0.35, 0.12, 0.08, 1.0)
        mat.diffuse_color = (0.22, 0.20, 0.20, 1.0)

        ramp_noise.color_ramp.elements[0].color = c_ash1
        ramp_noise.color_ramp.elements[1].color = c_ash2

        ramp_slope.color_ramp.elements[0].position = 0.70
        ramp_slope.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
        ramp_slope.color_ramp.elements[1].position = 0.88
        ramp_slope.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)

        node_bsdf.inputs['Roughness'].default_value = 0.7

    else: # PLAINS (草原)
        # 草原: 豊かなグリーン + 崖は茶褐色の岩壁
        c_grass1 = (0.20, 0.52, 0.15, 1.0)
        c_grass2 = (0.32, 0.62, 0.20, 1.0)
        c_cliff = (0.38, 0.32, 0.26, 1.0)
        mat.diffuse_color = (0.26, 0.55, 0.18, 1.0)

        ramp_noise.color_ramp.elements[0].color = c_grass1
        ramp_noise.color_ramp.elements[1].color = c_grass2

        ramp_slope.color_ramp.elements[0].position = 0.72
        ramp_slope.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
        ramp_slope.color_ramp.elements[1].position = 0.88
        ramp_slope.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)

        node_bsdf.inputs['Roughness'].default_value = 0.65

    # ノード配線
    fac_in = get_socket(mix_final, 'Factor', 'Fac')
    links.new(ramp_slope.outputs['Color'], fac_in)

    # A: 平坦カラー (ノイズグラデーション)
    a_in = get_socket(mix_final, 'A', 'Color1')
    links.new(ramp_noise.outputs['Color'], a_in)

    # B: 崖カラー
    b_in = get_socket(mix_final, 'B', 'Color2')
    if hasattr(b_in, 'default_value'):
        b_in.default_value = c_cliff

    res_out = get_output_socket(mix_final, 'Result', 'Color')
    links.new(res_out, node_bsdf.inputs['Base Color'])

    return mat


def apply_biome_material_to_terrain(terrain_obj, biome='PLAINS'):
    """地形オブジェクトにバイオームマテリアルを適用"""
    mat = get_or_create_terrain_material(biome)
    if not terrain_obj or not terrain_obj.data:
        return mat

    if not terrain_obj.data.materials:
        terrain_obj.data.materials.append(mat)
    else:
        terrain_obj.data.materials[0] = mat

    # Geometry Nodes モディファイア側の Set Material にも割り当て
    mod = terrain_obj.modifiers.get("TerrainGen")
    if mod and hasattr(mod, "node_group") and mod.node_group:
        nodes = mod.node_group.nodes
        set_mat_node = None
        for n in nodes:
            if n.type == 'SET_MATERIAL':
                set_mat_node = n
                break
        if set_mat_node:
            set_mat_node.inputs['Material'].default_value = mat

    print(f"バイオームマテリアル [{biome}] を地形 '{terrain_obj.name}' に適用しました。")
    return mat


def detect_road_type(prompt, biome='PLAINS'):
    """プロンプトまたはバイオームから最適な道路タイプ（砂道・砂利道・アスファルト）を判定"""
    p = (prompt or "").lower()
    # 1. 砂利道・小石道を先に判定（「砂利」に「砂」が含まれるため）
    if any(k in p for k in ['砂利', '砂利道', 'gravel', '石畳', 'cobble', '小石']):
        return 'GRAVEL'
    # 2. 砂道・ダート判定（砂漠バイオーム、砂道、ダート、未舗装など）
    elif any(k in p for k in ['砂道', '砂の道', '砂道？', 'sand road', 'dirt', 'ダート', '未舗装', '砂路', '土道', '土の道', 'オフロード']) or biome == 'DESERT':
        return 'SAND_DIRT'
    else:
        return 'ASPHALT'


def get_or_create_road_material(road_type='ASPHALT'):
    """道路タイプに応じた質感マテリアルを生成（砂道・砂利道・アスファルト）"""
    mat_name = f"Road_Material_{road_type}"
    mat = bpy.data.materials.get(mat_name)
    if mat:
        return mat

    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    # 出力ノード
    node_out = nodes.new('ShaderNodeOutputMaterial')
    node_out.location = (600, 0)

    # Principled BSDF
    node_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    node_bsdf.location = (350, 0)
    links.new(node_bsdf.outputs['BSDF'], node_out.inputs['Surface'])

    # ノイズテクスチャ（地面・砂利・土の質感）
    node_texcoord = nodes.new('ShaderNodeTexCoord')
    node_texcoord.location = (-600, 0)

    node_noise = nodes.new('ShaderNodeTexNoise')
    node_noise.location = (-400, 0)
    node_noise.inputs['Scale'].default_value = 0.5
    node_noise.inputs['Detail'].default_value = 6.0
    node_noise.inputs['Roughness'].default_value = 0.7
    links.new(node_texcoord.outputs['Object'], node_noise.inputs['Vector'])

    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.location = (-150, 0)
    links.new(node_noise.outputs['Fac'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], node_bsdf.inputs['Base Color'])

    if road_type == 'SAND_DIRT':
        # 砂漠の砂道・ダート街道: オレンジ〜黄土色の砂と轍
        c1 = (0.82, 0.66, 0.42, 1.0) # 明るい砂
        c2 = (0.68, 0.48, 0.28, 1.0) # 濃い砂・轍
        ramp.color_ramp.elements[0].color = c1
        ramp.color_ramp.elements[1].color = c2
        node_bsdf.inputs['Roughness'].default_value = 0.95
        mat.diffuse_color = (0.80, 0.64, 0.40, 1.0)

    elif road_type == 'GRAVEL':
        # 砂利道・未舗装路: 灰褐色と小石の混ざった道
        c1 = (0.55, 0.50, 0.45, 1.0)
        c2 = (0.38, 0.35, 0.32, 1.0)
        ramp.color_ramp.elements[0].color = c1
        ramp.color_ramp.elements[1].color = c2
        node_bsdf.inputs['Roughness'].default_value = 0.90
        mat.diffuse_color = (0.52, 0.48, 0.42, 1.0)

    else: # ASPHALT
        # 現代アスファルト舗装
        c1 = (0.18, 0.18, 0.20, 1.0)
        c2 = (0.11, 0.11, 0.12, 1.0)
        ramp.color_ramp.elements[0].color = c1
        ramp.color_ramp.elements[1].color = c2
        node_bsdf.inputs['Roughness'].default_value = 0.85
        mat.diffuse_color = (0.15, 0.15, 0.18, 1.0)

    return mat
