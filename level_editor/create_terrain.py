# -*- coding: utf-8 -*-
import bpy  # type: ignore

class MYADDON_OT_create_terrain(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_create_terrain"
    bl_label = "地形生成"
    bl_description = "ジオメトリノードを使用して起伏や道路平坦化を施した地形を生成します"
    bl_options = {'REGISTER', 'UNDO'}

    grid_size: bpy.props.FloatProperty(  # type: ignore
        name="グリッドサイズ",
        description="地形グリッドの一辺の長さ(m)を指定します",
        default=100.0,
        min=1.0,
    )

    grid_subdivisions: bpy.props.IntProperty(  # type: ignore
        name="グリッド分割数",
        description="地形グリッドの分割数を指定します（多いほど精細になります）",
        default=100,
        min=2,
        max=1000,
    )

    def execute(self, context):
        # 1. 地形用グリッドメッシュの作成
        bpy.ops.mesh.primitive_grid_add(
            size=self.grid_size,
            x_subdivisions=self.grid_subdivisions,
            y_subdivisions=self.grid_subdivisions,
            location=(0.0, 0.0, 0.0)
        )
        terrain_obj = context.active_object
        terrain_obj.name = "Terrain"

        # 2. Geometry Nodes モディファイアの追加
        gn_mod = terrain_obj.modifiers.new(name="TerrainGen", type='NODES')
        group = bpy.data.node_groups.new("TerrainGenTree", 'GeometryNodeTree')
        gn_mod.node_group = group

        # 3. 入出力ソケットの定義 (Blender 4.0+ と 3.x 以前の互換性)
        if hasattr(group, "interface"):
            # Geometry
            group.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
            # Road Object
            road_socket = group.interface.new_socket('Road Object', in_out='INPUT', socket_type='NodeSocketObject')
            # Noise Scale
            noise_scale_socket = group.interface.new_socket('Noise Scale', in_out='INPUT', socket_type='NodeSocketFloat')
            noise_scale_socket.default_value = 0.05
            # Terrain Height
            height_socket = group.interface.new_socket('Terrain Height', in_out='INPUT', socket_type='NodeSocketFloat')
            height_socket.default_value = 10.0
            # Flat Radius
            flat_radius_socket = group.interface.new_socket('Flat Radius', in_out='INPUT', socket_type='NodeSocketFloat')
            flat_radius_socket.default_value = 3.0
            # Flat Blend
            flat_blend_socket = group.interface.new_socket('Flat Blend', in_out='INPUT', socket_type='NodeSocketFloat')
            flat_blend_socket.default_value = 2.0
            # Hole Location
            hole_loc_socket = group.interface.new_socket('Hole Location', in_out='INPUT', socket_type='NodeSocketVector')
            hole_loc_socket.default_value = (0.0, 0.0, 0.0)
            # Hole Size
            hole_size_socket = group.interface.new_socket('Hole Size', in_out='INPUT', socket_type='NodeSocketFloat')
            hole_size_socket.default_value = 3.0

            # Outputs
            group.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
            buildable_socket = group.interface.new_socket('Buildable Area', in_out='OUTPUT', socket_type='NodeSocketFloat')
        else:
            # 3.x 互換
            group.inputs.new('NodeSocketGeometry', 'Geometry')
            group.inputs.new('NodeSocketObject', 'Road Object')
            group.inputs.new('NodeSocketFloat', 'Noise Scale').default_value = 0.05
            group.inputs.new('NodeSocketFloat', 'Terrain Height').default_value = 10.0
            group.inputs.new('NodeSocketFloat', 'Flat Radius').default_value = 3.0
            group.inputs.new('NodeSocketFloat', 'Flat Blend').default_value = 2.0
            group.inputs.new('NodeSocketVector', 'Hole Location').default_value = (0.0, 0.0, 0.0)
            group.inputs.new('NodeSocketFloat', 'Hole Size').default_value = 3.0

            group.outputs.new('NodeSocketGeometry', 'Geometry')
            group.outputs.new('NodeSocketFloat', 'Buildable Area')

        nodes = group.nodes
        links = group.links

        # 入出力基本ノードの配置
        node_in = nodes.new('NodeGroupInput')
        node_in.location = (-800, 0)
        node_out = nodes.new('NodeGroupOutput')
        node_out.location = (1400, 0)

        # ==========================================
        # (A) ベースの高さ生成 (ノイズ起伏)
        # ==========================================
        # 1. Position ノード
        node_pos = nodes.new('GeometryNodeInputPosition')
        node_pos.location = (-800, -300)

        # 2. Noise Texture ノード
        try:
            node_noise = nodes.new('FunctionNodeNoiseTexture')
        except RuntimeError:
            node_noise = nodes.new('ShaderNodeTexNoise')
        node_noise.location = (-600, -300)
        links.new(node_pos.outputs['Position'], node_noise.inputs['Vector'])
        links.new(node_in.outputs['Noise Scale'], node_noise.inputs['Scale'])

        # 3. Math: Subtract 0.5 (ノイズ高さを±に振る)
        node_sub = nodes.new('ShaderNodeMath')
        node_sub.operation = 'SUBTRACT'
        node_sub.inputs[1].default_value = 0.5
        node_sub.location = (-400, -300)
        noise_out = node_noise.outputs['Factor'] if 'Factor' in node_noise.outputs else node_noise.outputs[0]
        links.new(noise_out, node_sub.inputs[0])

        # 4. Math: Multiply by Terrain Height
        node_mult = nodes.new('ShaderNodeMath')
        node_mult.operation = 'MULTIPLY'
        node_mult.location = (-200, -300)
        links.new(node_sub.outputs[0], node_mult.inputs[0])
        links.new(node_in.outputs['Terrain Height'], node_mult.inputs[1])

        # 5. Combine XYZ
        node_comb_height = nodes.new('ShaderNodeCombineXYZ')
        node_comb_height.location = (0, -300)
        links.new(node_mult.outputs[0], node_comb_height.inputs['Z'])

        # 6. Set Position: ベース高さを適用
        node_set_height = nodes.new('GeometryNodeSetPosition')
        node_set_height.location = (200, 100)
        links.new(node_in.outputs['Geometry'], node_set_height.inputs['Geometry'])
        links.new(node_comb_height.outputs['Vector'], node_set_height.inputs['Offset'])


        # ==========================================
        # (B) 道路まわりの平坦化 (Geometry Proximity)
        # ==========================================
        # 1. Object Info (道路オブジェクト情報)
        node_road_info = nodes.new('GeometryNodeObjectInfo')
        node_road_info.transform_space = 'RELATIVE'
        node_road_info.location = (-200, 400)
        links.new(node_in.outputs['Road Object'], node_road_info.inputs['Object'])

        # 2. Geometry Proximity (道路メッシュへの近接)
        node_proximity = nodes.new('GeometryNodeProximity')
        node_proximity.target_element = 'FACES'
        node_proximity.location = (50, 400)
        links.new(node_road_info.outputs['Geometry'], node_proximity.inputs['Target'])

        # 3. Separate XYZ: 道路近接点のZ座標
        node_sep_prox = nodes.new('ShaderNodeSeparateXYZ')
        node_sep_prox.location = (250, 450)
        links.new(node_proximity.outputs['Position'], node_sep_prox.inputs['Vector'])

        # 4. Separate XYZ: 現在の頂点のZ座標 (高さ変更後)
        node_curr_pos = nodes.new('GeometryNodeInputPosition')
        node_curr_pos.location = (50, 200)
        node_sep_curr = nodes.new('ShaderNodeSeparateXYZ')
        node_sep_curr.location = (250, 200)
        links.new(node_curr_pos.outputs['Position'], node_sep_curr.inputs['Vector'])

        # 5. Map Range: 距離を平坦化のウェイト(Factor: 0.0 ~ 1.0)にマッピング
        # 距離が Flat Radius 以下なら 1.0 (道路高さ), Flat Radius + Flat Blend 以上なら 0.0 (元の地形)
        node_map_range = nodes.new('ShaderNodeMapRange')
        node_map_range.location = (250, 650)
        node_map_range.interpolation_type = 'LINEAR'
        node_map_range.inputs['To Min'].default_value = 1.0
        node_map_range.inputs['To Max'].default_value = 0.0
        links.new(node_proximity.outputs['Distance'], node_map_range.inputs['Value'])
        links.new(node_in.outputs['Flat Radius'], node_map_range.inputs['From Min'])

        # Flat Radius + Flat Blend の計算
        node_add_blend = nodes.new('ShaderNodeMath')
        node_add_blend.operation = 'ADD'
        node_add_blend.location = (50, 650)
        links.new(node_in.outputs['Flat Radius'], node_add_blend.inputs[0])
        links.new(node_in.outputs['Flat Blend'], node_add_blend.inputs[1])
        links.new(node_add_blend.outputs[0], node_map_range.inputs['From Max'])

        # 6. 線形補間(Lerp)の計算 (Mix Float ノードの互換性対策)
        # MixZ = CurrZ + (ProxZ - CurrZ) * Factor
        # (A) ProxZ - CurrZ
        node_diff = nodes.new('ShaderNodeMath')
        node_diff.operation = 'SUBTRACT'
        node_diff.location = (450, 400)
        links.new(node_sep_prox.outputs['Z'], node_diff.inputs[0])
        links.new(node_sep_curr.outputs['Z'], node_diff.inputs[1])

        # (B) (ProxZ - CurrZ) * Factor
        node_mult_factor = nodes.new('ShaderNodeMath')
        node_mult_factor.operation = 'MULTIPLY'
        node_mult_factor.location = (600, 400)
        links.new(node_diff.outputs[0], node_mult_factor.inputs[0])
        links.new(node_map_range.outputs['Result'], node_mult_factor.inputs[1])

        # (C) CurrZ + ...
        node_mix_z = nodes.new('ShaderNodeMath')
        node_mix_z.operation = 'ADD'
        node_mix_z.location = (750, 400)
        links.new(node_sep_curr.outputs['Z'], node_mix_z.inputs[0])
        links.new(node_mult_factor.outputs[0], node_mix_z.inputs[1])

        # 7. Combine XYZ: 平坦化後の位置を作成 (XYは元の位置を維持)
        node_comb_flat = nodes.new('ShaderNodeCombineXYZ')
        node_comb_flat.location = (900, 300)
        links.new(node_sep_curr.outputs['X'], node_comb_flat.inputs['X'])
        links.new(node_sep_curr.outputs['Y'], node_comb_flat.inputs['Y'])
        links.new(node_mix_z.outputs[0], node_comb_flat.inputs['Z'])

        # 8. Set Position: 平坦化位置を適用
        node_set_flat = nodes.new('GeometryNodeSetPosition')
        node_set_flat.location = (1100, 100)
        links.new(node_set_height.outputs['Geometry'], node_set_flat.inputs['Geometry'])
        links.new(node_comb_flat.outputs['Vector'], node_set_flat.inputs['Position'])


        # ==========================================
        # (C) 穴あけの基礎 (指定座標からの距離による削除)
        # ==========================================
        # 1. Vector Distance (Hole Location と各頂点の距離)
        node_hole_dist = nodes.new('ShaderNodeVectorMath')
        node_hole_dist.operation = 'DISTANCE'
        node_hole_dist.location = (500, -100)
        links.new(node_in.outputs['Hole Location'], node_hole_dist.inputs[0])

        # 現在のPositionを入力
        node_pos_c = nodes.new('GeometryNodeInputPosition')
        node_pos_c.location = (300, -100)
        links.new(node_pos_c.outputs['Position'], node_hole_dist.inputs[1])

        # 2. Compare: Distance < Hole Size
        try:
            node_comp_hole = nodes.new('FunctionNodeCompare')
            node_comp_hole.data_type = 'FLOAT'
            node_comp_hole.operation = 'LESS_THAN'
        except RuntimeError:
            node_comp_hole = nodes.new('ShaderNodeMath')
            node_comp_hole.operation = 'LESS_THAN'
        node_comp_hole.location = (700, -100)
        dist_out = node_hole_dist.outputs['Value'] if 'Value' in node_hole_dist.outputs else node_hole_dist.outputs[0]
        links.new(dist_out, node_comp_hole.inputs[0])
        links.new(node_in.outputs['Hole Size'], node_comp_hole.inputs[1])

        # 3. Delete Geometry: 条件を満たす頂点/面を削除
        node_delete_geo = nodes.new('GeometryNodeDeleteGeometry')
        node_delete_geo.domain = 'POINT'
        node_delete_geo.location = (900, -100)
        links.new(node_set_flat.outputs['Geometry'], node_delete_geo.inputs['Geometry'])
        comp_hole_out = node_comp_hole.outputs['Result'] if 'Result' in node_comp_hole.outputs else node_comp_hole.outputs[0]
        links.new(comp_hole_out, node_delete_geo.inputs['Selection'])

        # 出力を最終的なGeometryに接続
        links.new(node_delete_geo.outputs['Geometry'], node_out.inputs['Geometry'])


        # ==========================================
        # (D) 建築可能エリアの出力属性判定
        # ==========================================
        # 1. Normal ノード
        node_normal = nodes.new('GeometryNodeInputNormal')
        node_normal.location = (500, -350)

        # 2. Separate XYZ: 法線のZ成分を取り出す (1.0に近いほど平ら)
        node_sep_normal = nodes.new('ShaderNodeSeparateXYZ')
        node_sep_normal.location = (680, -350)
        links.new(node_normal.outputs['Normal'], node_sep_normal.inputs['Vector'])

        # 3. Compare: Slope Z >= 0.9 (約25度以下のなだらかな傾斜)
        try:
            node_comp_slope = nodes.new('FunctionNodeCompare')
            node_comp_slope.data_type = 'FLOAT'
            node_comp_slope.operation = 'GREATER_EQUAL'
        except RuntimeError:
            node_comp_slope = nodes.new('ShaderNodeMath')
            node_comp_slope.operation = 'GREATER_THAN'
        node_comp_slope.location = (850, -350)
        links.new(node_sep_normal.outputs['Z'], node_comp_slope.inputs[0])
        node_comp_slope.inputs[1].default_value = 0.9

        # 4. 道路からの距離判定 (道路の上は除外、道路の近く)
        # (A) Distance >= 2.5m (道路上を避ける)
        try:
            node_comp_dist_min = nodes.new('FunctionNodeCompare')
            node_comp_dist_min.data_type = 'FLOAT'
            node_comp_dist_min.operation = 'GREATER_EQUAL'
        except RuntimeError:
            node_comp_dist_min = nodes.new('ShaderNodeMath')
            node_comp_dist_min.operation = 'GREATER_THAN'
        node_comp_dist_min.location = (680, -550)
        links.new(node_proximity.outputs['Distance'], node_comp_dist_min.inputs[0])
        node_comp_dist_min.inputs[1].default_value = 2.5

        # (B) Distance <= 12.0m (道路の近く)
        try:
            node_comp_dist_max = nodes.new('FunctionNodeCompare')
            node_comp_dist_max.data_type = 'FLOAT'
            node_comp_dist_max.operation = 'LESS_EQUAL'
        except RuntimeError:
            node_comp_dist_max = nodes.new('ShaderNodeMath')
            node_comp_dist_max.operation = 'LESS_THAN'
        node_comp_dist_max.location = (850, -550)
        links.new(node_proximity.outputs['Distance'], node_comp_dist_max.inputs[0])
        node_comp_dist_max.inputs[1].default_value = 12.0

        # (C) 距離の積 (AND条件)
        node_and_dist = nodes.new('ShaderNodeMath')
        node_and_dist.operation = 'MULTIPLY'
        node_and_dist.location = (1020, -550)
        comp_min_out = node_comp_dist_min.outputs['Result'] if 'Result' in node_comp_dist_min.outputs else node_comp_dist_min.outputs[0]
        comp_max_out = node_comp_dist_max.outputs['Result'] if 'Result' in node_comp_dist_max.outputs else node_comp_dist_max.outputs[0]
        links.new(comp_min_out, node_and_dist.inputs[0])
        links.new(comp_max_out, node_and_dist.inputs[1])

        # (D) 傾斜判定 ＆ 距離判定の積 (すべてを満たすエリア)
        node_and_all = nodes.new('ShaderNodeMath')
        node_and_all.operation = 'MULTIPLY'
        node_and_all.location = (1200, -350)
        comp_slope_out = node_comp_slope.outputs['Result'] if 'Result' in node_comp_slope.outputs else node_comp_slope.outputs[0]
        links.new(comp_slope_out, node_and_all.inputs[0])
        links.new(node_and_dist.outputs[0], node_and_all.inputs[1])

        # 出力の 'Buildable Area' に接続
        links.new(node_and_all.outputs[0], node_out.inputs['Buildable Area'])

        # 4. 作成した地形オブジェクトをアクティブにする
        context.view_layer.objects.active = terrain_obj
        terrain_obj.select_set(True)

        print("ジオメトリノード地形生成システムが構築されました。")
        return {'FINISHED'}
