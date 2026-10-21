# -*- coding: utf-8 -*-
import bpy  # type: ignore

def detect_biomes(prompt, user_choice='AUTO'):
    """プロンプトまたはユーザー選択から1つ以上のバイオームを判定し、リストで返す"""
    if user_choice and user_choice != 'AUTO':
        if user_choice == 'MULTI':
            return ['MULTI']
        return [user_choice]
        
    p = (prompt or "").lower()
    
    # 明示的な複合キーワード
    if any(k in p for k in ['複合', 'マルチ', 'multiple', 'multi', '多様', 'various', '大陸', 'continent']):
        return ['MULTI']

    found = []
    # 砂漠系
    if any(k in p for k in ['砂漠', '砂', 'desert', 'sand', 'オアシス', 'oasis', 'デューン', 'dune', 'サハラ']):
        found.append('DESERT')
    # 雪山・氷河系
    if any(k in p for k in ['雪', '氷', 'snow', 'winter', 'ice', '寒冷', 'ツンドラ', 'tundra', '雪原', '雪山']):
        found.append('SNOW')
    # 峡谷・岩山系
    if any(k in p for k in ['岩', '峡谷', 'キャニオン', 'canyon', '荒野', 'badlands', '赤土', 'グランドキャニオン']):
        found.append('CANYON')
    # 火山・溶岩系
    if any(k in p for k in ['火山', '溶岩', 'volcano', 'lava', 'マグマ', '玄武岩', 'dark']):
        found.append('VOLCANO')
    # 草原・緑系
    if any(k in p for k in ['草原', '平原', '緑', 'plains', 'grass', 'forest', '森', '林', '木々', '田園']):
        found.append('PLAINS')

    if len(found) >= 2:
        return found
    elif len(found) == 1:
        return found
    else:
        return ['PLAINS']


def detect_biome(prompt, user_choice='AUTO'):
    """プロンプトまたはユーザー選択から代表バイオームを判定（後方互換性用）"""
    biomes = detect_biomes(prompt, user_choice)
    if len(biomes) >= 2 or biomes[0] == 'MULTI':
        return 'MULTI'
    return biomes[0]


def get_or_create_multi_biome_material(sub_biomes=None):
    """標高・大域ノイズ・傾斜を統合したプロシージャル・マルチバイオームマテリアルを構築"""
    if sub_biomes and 'MULTI' not in sub_biomes:
        sub_str = "_".join(sorted(sub_biomes))
        mat_name = f"Terrain_Biome_MULTI_{sub_str}"
    else:
        mat_name = "Terrain_Biome_MULTI"

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
    node_out.location = (1100, 0)

    # Principled BSDF
    node_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    node_bsdf.location = (850, 0)
    links.new(node_bsdf.outputs['BSDF'], node_out.inputs['Surface'])
    mat.diffuse_color = (0.35, 0.52, 0.28, 1.0) # 複合ビューポートカラー

    # 互換性ソケット取得
    def get_socket(node, *names):
        for n in names:
            if n in node.inputs:
                return node.inputs[n]
        for i in node.inputs:
            if getattr(i, 'enabled', True):
                return i
        return node.inputs[0]

    def get_output_socket(node, *names):
        for n in names:
            if n in node.outputs:
                return node.outputs[n]
        for o in node.outputs:
            if getattr(o, 'enabled', True):
                return o
        return node.outputs[0]

    def create_mix_rgba(loc, name="MixRGBA"):
        m = nodes.new('ShaderNodeMix')
        try:
            m.data_type = 'RGBA'
        except AttributeError:
            pass
        m.location = loc
        m.name = name
        return m

    def create_mix_float(loc, name="MixFloat"):
        m = nodes.new('ShaderNodeMix')
        try:
            m.data_type = 'FLOAT'
        except AttributeError:
            pass
        m.location = loc
        m.name = name
        return m

    def link_mix_rgba(mix_node, fac_out=None, a_out=None, b_out=None, a_col=None, b_col=None):
        fac_in = get_socket(mix_node, 'Factor', 'Fac')
        a_in = get_socket(mix_node, 'A', 'Color1', 6)
        b_in = get_socket(mix_node, 'B', 'Color2', 7)
        if fac_out is not None:
            links.new(fac_out, fac_in)
        if a_out is not None:
            links.new(a_out, a_in)
        elif a_col is not None and hasattr(a_in, 'default_value'):
            a_in.default_value = a_col
        if b_out is not None:
            links.new(b_out, b_in)
        elif b_col is not None and hasattr(b_in, 'default_value'):
            b_in.default_value = b_col

    def link_mix_float(mix_node, fac_out=None, a_out=None, b_out=None, a_val=None, b_val=None):
        fac_in = get_socket(mix_node, 'Factor', 'Fac')
        a_in = get_socket(mix_node, 'A', 'Value', 2)
        b_in = get_socket(mix_node, 'B', 'Value', 3)
        if fac_out is not None:
            links.new(fac_out, fac_in)
        if a_out is not None:
            links.new(a_out, a_in)
        elif a_val is not None and hasattr(a_in, 'default_value'):
            a_in.default_value = a_val
        if b_out is not None:
            links.new(b_out, b_in)
        elif b_val is not None and hasattr(b_in, 'default_value'):
            b_in.default_value = b_val

    # 1. 幾何情報 (Normal, Position)
    node_geom = nodes.new('ShaderNodeNewGeometry')
    node_geom.location = (-1250, 250)

    # 1a. 傾斜取得: Normal -> SeparateXYZ -> Z
    node_sep_norm = nodes.new('ShaderNodeSeparateXYZ')
    node_sep_norm.location = (-1000, 350)
    links.new(node_geom.outputs['Normal'], node_sep_norm.inputs['Vector'])

    # 傾斜用 ColorRamp (Z=1.0: 平坦, Z=0.0: 急峻な崖)
    ramp_slope = nodes.new('ShaderNodeValToRGB')
    ramp_slope.location = (-750, 350)
    ramp_slope.color_ramp.elements[0].position = 0.70  # 急斜面 (Cliff側)
    ramp_slope.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
    ramp_slope.color_ramp.elements[1].position = 0.88  # なだらか (Flat側)
    ramp_slope.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)
    links.new(node_sep_norm.outputs['Z'], ramp_slope.inputs['Fac'])

    # 1b. 標高取得: Position -> SeparateXYZ -> Z
    node_sep_pos = nodes.new('ShaderNodeSeparateXYZ')
    node_sep_pos.location = (-1000, 100)
    links.new(node_geom.outputs['Position'], node_sep_pos.inputs['Vector'])

    # 2. テクスチャ座標 (Object)
    node_texcoord = nodes.new('ShaderNodeTexCoord')
    node_texcoord.location = (-1250, -250)

    # 2a. 微小ノイズ (地面表面の細やかなテクスチャ質感)
    node_noise_micro = nodes.new('ShaderNodeTexNoise')
    node_noise_micro.location = (-1000, -100)
    node_noise_micro.inputs['Scale'].default_value = 0.05
    node_noise_micro.inputs['Detail'].default_value = 4.0
    node_noise_micro.inputs['Roughness'].default_value = 0.6
    links.new(node_texcoord.outputs['Object'], node_noise_micro.inputs['Vector'])

    # 2b. 大域マクロノイズ (X/Y平面での広域気候・地域分布: 20kmスケール対応)
    node_noise_macro = nodes.new('ShaderNodeTexNoise')
    node_noise_macro.location = (-1000, -350)
    node_noise_macro.inputs['Scale'].default_value = 0.00025  # 約4km〜6km周期の広大な気候帯
    node_noise_macro.inputs['Detail'].default_value = 2.0
    node_noise_macro.inputs['Roughness'].default_value = 0.5
    links.new(node_texcoord.outputs['Object'], node_noise_macro.inputs['Vector'])

    # 3. 標高＋微小ノイズによる自然な雪線 (Snow Line)
    math_snow_noise = nodes.new('ShaderNodeMath')
    math_snow_noise.operation = 'MULTIPLY'
    math_snow_noise.location = (-750, 120)
    math_snow_noise.inputs[1].default_value = 35.0  # ノイズ振幅35mでギザギザの雪線
    links.new(node_noise_micro.outputs['Fac'], math_snow_noise.inputs[0])

    math_snow_z = nodes.new('ShaderNodeMath')
    math_snow_z.operation = 'ADD'
    math_snow_z.location = (-550, 120)
    links.new(node_sep_pos.outputs['Z'], math_snow_z.inputs[0])
    links.new(math_snow_noise.outputs['Value'], math_snow_z.inputs[1])

    # Map Range で標高 80m〜160m にかけて雪山(SNOW)へグラデーション
    node_snow_map = nodes.new('ShaderNodeMapRange')
    node_snow_map.location = (-350, 120)
    node_snow_map.inputs['From Min'].default_value = 80.0
    node_snow_map.inputs['From Max'].default_value = 160.0
    node_snow_map.inputs['To Min'].default_value = 0.0
    node_snow_map.inputs['To Max'].default_value = 1.0
    node_snow_map.clamp = True
    links.new(math_snow_z.outputs['Value'], node_snow_map.inputs['Value'])

    # --- 各バイオームのカラーパレット定義 ---
    # 草原 (PLAINS)
    c_plains_flat1 = (0.20, 0.52, 0.15, 1.0)
    c_plains_flat2 = (0.32, 0.62, 0.20, 1.0)
    c_plains_cliff  = (0.38, 0.32, 0.26, 1.0)

    # 砂漠 (DESERT)
    c_desert_flat1 = (0.88, 0.72, 0.42, 1.0)
    c_desert_flat2 = (0.76, 0.52, 0.28, 1.0)
    c_desert_cliff  = (0.50, 0.28, 0.16, 1.0)

    # 峡谷 (CANYON)
    c_canyon_flat1 = (0.78, 0.45, 0.28, 1.0)
    c_canyon_flat2 = (0.65, 0.35, 0.20, 1.0)
    c_canyon_cliff  = (0.45, 0.22, 0.14, 1.0)

    # 火山 (VOLCANO)
    c_volcano_flat1 = (0.15, 0.15, 0.16, 1.0)
    c_volcano_flat2 = (0.25, 0.22, 0.22, 1.0)
    c_volcano_cliff  = (0.35, 0.12, 0.08, 1.0)

    # 雪山 (SNOW)
    c_snow_flat1 = (0.95, 0.97, 1.0, 1.0)
    c_snow_flat2 = (0.82, 0.88, 0.95, 1.0)
    c_snow_cliff  = (0.28, 0.32, 0.38, 1.0)

    # 微小ノイズによる各バイオーム平坦部のグラデーション生成
    mix_plains_flat = create_mix_rgba((-750, -50), "MixPlainsFlat")
    link_mix_rgba(mix_plains_flat, fac_out=node_noise_micro.outputs['Fac'], a_col=c_plains_flat1, b_col=c_plains_flat2)

    mix_desert_flat = create_mix_rgba((-750, -180), "MixDesertFlat")
    link_mix_rgba(mix_desert_flat, fac_out=node_noise_micro.outputs['Fac'], a_col=c_desert_flat1, b_col=c_desert_flat2)

    mix_canyon_flat = create_mix_rgba((-750, -310), "MixCanyonFlat")
    link_mix_rgba(mix_canyon_flat, fac_out=node_noise_micro.outputs['Fac'], a_col=c_canyon_flat1, b_col=c_canyon_flat2)

    mix_volcano_flat = create_mix_rgba((-750, -440), "MixVolcanoFlat")
    link_mix_rgba(mix_volcano_flat, fac_out=node_noise_micro.outputs['Fac'], a_col=c_volcano_flat1, b_col=c_volcano_flat2)

    mix_snow_flat = create_mix_rgba((-750, 20), "MixSnowFlat")
    link_mix_rgba(mix_snow_flat, fac_out=node_noise_micro.outputs['Fac'], a_col=c_snow_flat1, b_col=c_snow_flat2)

    # 4. 大域マクロノイズによる平野〜中標高バイオームの地域ブレンド
    has_volcano = sub_biomes and ('VOLCANO' in sub_biomes)
    has_canyon = sub_biomes and ('CANYON' in sub_biomes)
    has_desert = (sub_biomes is None) or ('DESERT' in sub_biomes) or ('MULTI' in sub_biomes)
    has_plains = (sub_biomes is None) or ('PLAINS' in sub_biomes) or ('MULTI' in sub_biomes)

    # 地域第1段階: 草原 vs 砂漠（または火山/峡谷）
    mix_reg1_flat = create_mix_rgba((-450, -150), "MixReg1Flat")
    mix_reg1_cliff = create_mix_rgba((-450, -280), "MixReg1Cliff")
    mix_reg1_rough = create_mix_float((-450, -410), "MixReg1Rough")

    base_a_flat = get_output_socket(mix_plains_flat, 'Result', 'Color') if has_plains else (get_output_socket(mix_canyon_flat, 'Result', 'Color') if has_canyon else get_output_socket(mix_volcano_flat, 'Result', 'Color'))
    base_a_cliff = c_plains_cliff if has_plains else (c_canyon_cliff if has_canyon else c_volcano_cliff)
    base_a_rough = 0.65 if has_plains else 0.80

    base_b_flat = get_output_socket(mix_desert_flat, 'Result', 'Color') if has_desert else (get_output_socket(mix_volcano_flat, 'Result', 'Color') if has_volcano else get_output_socket(mix_canyon_flat, 'Result', 'Color'))
    base_b_cliff = c_desert_cliff if has_desert else (c_volcano_cliff if has_volcano else c_canyon_cliff)
    base_b_rough = 0.85 if has_desert else 0.70

    link_mix_rgba(mix_reg1_flat, fac_out=node_noise_macro.outputs['Fac'], a_out=base_a_flat, b_out=base_b_flat)
    link_mix_rgba(mix_reg1_cliff, fac_out=node_noise_macro.outputs['Fac'], a_col=base_a_cliff, b_col=base_b_cliff)
    link_mix_float(mix_reg1_rough, fac_out=node_noise_macro.outputs['Fac'], a_val=base_a_rough, b_val=base_b_rough)

    # 地域第2段階: 峡谷または火山の局所展開
    cur_flat_out = get_output_socket(mix_reg1_flat, 'Result', 'Color')
    cur_cliff_out = get_output_socket(mix_reg1_cliff, 'Result', 'Color')
    cur_rough_out = get_output_socket(mix_reg1_rough, 'Result')

    if has_canyon or has_volcano or (sub_biomes is None) or ('MULTI' in sub_biomes):
        sub_special_flat = get_output_socket(mix_volcano_flat, 'Result', 'Color') if has_volcano else get_output_socket(mix_canyon_flat, 'Result', 'Color')
        sub_special_cliff = c_volcano_cliff if has_volcano else c_canyon_cliff
        sub_special_rough = 0.70 if has_volcano else 0.80

        map_special = nodes.new('ShaderNodeMapRange')
        map_special.location = (-450, -540)
        map_special.inputs['From Min'].default_value = 0.62
        map_special.inputs['From Max'].default_value = 0.88
        map_special.inputs['To Min'].default_value = 0.0
        map_special.inputs['To Max'].default_value = 1.0
        map_special.clamp = True
        links.new(node_noise_macro.outputs['Fac'], map_special.inputs['Value'])

        mix_reg2_flat = create_mix_rgba((-200, -150), "MixReg2Flat")
        mix_reg2_cliff = create_mix_rgba((-200, -280), "MixReg2Cliff")
        mix_reg2_rough = create_mix_float((-200, -410), "MixReg2Rough")

        link_mix_rgba(mix_reg2_flat, fac_out=map_special.outputs['Result'], a_out=cur_flat_out, b_out=sub_special_flat)
        link_mix_rgba(mix_reg2_cliff, fac_out=map_special.outputs['Result'], a_out=cur_cliff_out, b_col=sub_special_cliff)
        link_mix_float(mix_reg2_rough, fac_out=map_special.outputs['Result'], a_out=cur_rough_out, b_val=sub_special_rough)

        cur_flat_out = get_output_socket(mix_reg2_flat, 'Result', 'Color')
        cur_cliff_out = get_output_socket(mix_reg2_cliff, 'Result', 'Color')
        cur_rough_out = get_output_socket(mix_reg2_rough, 'Result')

    # 5. 高標高（山頂部）の雪山(SNOW)へのブレンド
    has_snow = (sub_biomes is None) or ('SNOW' in sub_biomes) or ('MULTI' in sub_biomes)
    if has_snow:
        mix_snow_blend_flat = create_mix_rgba((100, -50), "MixSnowBlendFlat")
        mix_snow_blend_cliff = create_mix_rgba((100, -180), "MixSnowBlendCliff")
        mix_snow_blend_rough = create_mix_float((100, -310), "MixSnowBlendRough")

        link_mix_rgba(mix_snow_blend_flat, fac_out=node_snow_map.outputs['Result'], a_out=cur_flat_out, b_out=get_output_socket(mix_snow_flat, 'Result', 'Color'))
        link_mix_rgba(mix_snow_blend_cliff, fac_out=node_snow_map.outputs['Result'], a_out=cur_cliff_out, b_col=c_snow_cliff)
        link_mix_float(mix_snow_blend_rough, fac_out=node_snow_map.outputs['Result'], a_out=cur_rough_out, b_val=0.40)

        final_flat = get_output_socket(mix_snow_blend_flat, 'Result', 'Color')
        final_cliff = get_output_socket(mix_snow_blend_cliff, 'Result', 'Color')
        final_rough = get_output_socket(mix_snow_blend_rough, 'Result')
    else:
        final_flat = cur_flat_out
        final_cliff = cur_cliff_out
        final_rough = cur_rough_out

    # 6. 崖と平坦部の最終カラーミックス (傾斜 ramp_slope による)
    mix_final = create_mix_rgba((400, 50), "MixFinal")
    fac_slope_in = get_socket(mix_final, 'Factor', 'Fac')
    links.new(ramp_slope.outputs['Color'], fac_slope_in)

    a_in = get_socket(mix_final, 'A', 'Color1', 6)
    links.new(final_flat, a_in)

    b_in = get_socket(mix_final, 'B', 'Color2', 7)
    links.new(final_cliff, b_in)

    # Principled BSDF へ配線
    res_out = get_output_socket(mix_final, 'Result', 'Color')
    links.new(res_out, node_bsdf.inputs['Base Color'])
    links.new(final_rough, node_bsdf.inputs['Roughness'])

    print(f"マルチバイオームマテリアル '{mat_name}' を構築しました。")
    return mat


def get_or_create_terrain_material(biome='PLAINS', sub_biomes=None):
    """バイオームに応じた傾斜対応プロシージャルシェーダーマテリアルを構築"""
    if biome == 'MULTI' or (sub_biomes and len(sub_biomes) >= 2):
        return get_or_create_multi_biome_material(sub_biomes)

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
        c_sand1 = (0.88, 0.72, 0.42, 1.0)
        c_sand2 = (0.76, 0.52, 0.28, 1.0)
        c_cliff = (0.50, 0.28, 0.16, 1.0)
        mat.diffuse_color = (0.86, 0.70, 0.40, 1.0)

        ramp_noise.color_ramp.elements[0].color = c_sand1
        ramp_noise.color_ramp.elements[1].color = c_sand2

        ramp_slope.color_ramp.elements[0].position = 0.70
        ramp_slope.color_ramp.elements[0].color = (1.0, 1.0, 1.0, 1.0)
        ramp_slope.color_ramp.elements[1].position = 0.88
        ramp_slope.color_ramp.elements[1].color = (0.0, 0.0, 0.0, 1.0)

        node_bsdf.inputs['Roughness'].default_value = 0.85

    elif biome == 'SNOW':
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

    else: # PLAINS
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

    a_in = get_socket(mix_final, 'A', 'Color1')
    links.new(ramp_noise.outputs['Color'], a_in)

    b_in = get_socket(mix_final, 'B', 'Color2')
    if hasattr(b_in, 'default_value'):
        b_in.default_value = c_cliff

    res_out = get_output_socket(mix_final, 'Result', 'Color')
    links.new(res_out, node_bsdf.inputs['Base Color'])

    return mat


def apply_biome_material_to_terrain(terrain_obj, biome='PLAINS', sub_biomes=None):
    """地形オブジェクトにバイオームマテリアルを適用"""
    if biome == 'MULTI' or (sub_biomes and len(sub_biomes) >= 2):
        mat = get_or_create_multi_biome_material(sub_biomes)
    else:
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

    print(f"バイオームマテリアル [{mat.name}] を地形 '{terrain_obj.name}' に適用しました。")
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
