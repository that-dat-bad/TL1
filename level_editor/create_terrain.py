# -*- coding: utf-8 -*-
import bpy  # type: ignore

class MYADDON_OT_create_terrain(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_create_terrain"
    bl_label = "地形生成"
    bl_description = "ジオメトリノードを使用して起伏や道路平坦化を施した地形を生成します"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 1. 空の地形用メッシュオブジェクトの作成 (サイズや分割数はジオメトリノード側で動的に制御します)
        mesh_data = bpy.data.meshes.new("TerrainMesh")
        terrain_obj = bpy.data.objects.new("Terrain", mesh_data)
        context.collection.objects.link(terrain_obj)

        # 2. Geometry Nodes モディファイアの追加
        gn_mod = terrain_obj.modifiers.new(name="TerrainGen", type='NODES')
        group = bpy.data.node_groups.new("TerrainGenTree", 'GeometryNodeTree')
        gn_mod.node_group = group

        # 3. 入出力ソケットの定義 (Blender 4.0+ と 3.x 以前の互換性)
        if hasattr(group, "interface"):
            # Geometry (入力は空だが、ノード仕様として残す)
            group.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
            # Road Object
            road_socket = group.interface.new_socket('Road Object', in_out='INPUT', socket_type='NodeSocketObject')
            # Terrain Size X / Y
            size_x_socket = group.interface.new_socket('Grid Size X', in_out='INPUT', socket_type='NodeSocketFloat')
            size_x_socket.default_value = 100.0
            size_y_socket = group.interface.new_socket('Grid Size Y', in_out='INPUT', socket_type='NodeSocketFloat')
            size_y_socket.default_value = 100.0
            # Subdivisions X / Y
            sub_x_socket = group.interface.new_socket('Subdivisions X', in_out='INPUT', socket_type='NodeSocketInt')
            sub_x_socket.default_value = 100
            sub_x_socket.min_value = 2
            sub_x_socket.max_value = 1000
            sub_y_socket = group.interface.new_socket('Subdivisions Y', in_out='INPUT', socket_type='NodeSocketInt')
            sub_y_socket.default_value = 100
            sub_y_socket.min_value = 2
            sub_y_socket.max_value = 1000
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
            hole_size_socket.default_value = 0.0 # 初期値は穴なし

            # Outputs
            group.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
            buildable_socket = group.interface.new_socket('Buildable Area', in_out='OUTPUT', socket_type='NodeSocketFloat')
        else:
            # 3.x 互換
            group.inputs.new('NodeSocketGeometry', 'Geometry')
            group.inputs.new('NodeSocketObject', 'Road Object')
            group.inputs.new('NodeSocketFloat', 'Grid Size X').default_value = 100.0
            group.inputs.new('NodeSocketFloat', 'Grid Size Y').default_value = 100.0
            group.inputs.new('NodeSocketInt', 'Subdivisions X').default_value = 100
            group.inputs.new('NodeSocketInt', 'Subdivisions Y').default_value = 100
            group.inputs.new('NodeSocketFloat', 'Noise Scale').default_value = 0.05
            group.inputs.new('NodeSocketFloat', 'Terrain Height').default_value = 10.0
            group.inputs.new('NodeSocketFloat', 'Flat Radius').default_value = 3.0
            group.inputs.new('NodeSocketFloat', 'Flat Blend').default_value = 2.0
            group.inputs.new('NodeSocketVector', 'Hole Location').default_value = (0.0, 0.0, 0.0)
            group.inputs.new('NodeSocketFloat', 'Hole Size').default_value = 0.0
            
            group.outputs.new('NodeSocketGeometry', 'Geometry')
            group.outputs.new('NodeSocketFloat', 'Buildable Area')

        nodes = group.nodes
        links = group.links

        # 入出力基本ノードの配置
        node_in = nodes.new('NodeGroupInput')
        node_in.location = (-1100, 0)
        node_out = nodes.new('NodeGroupOutput')
        node_out.location = (1400, 0)

        # ==========================================
        # (A) ベースの高さ生成 (ノイズ起伏)
        # ==========================================
        # 0. Grid Primitive ノード (ジオメトリノード側でグリッドサイズをリアルタイムに制御)
        node_grid = nodes.new('GeometryNodeMeshGrid')
        node_grid.location = (-800, 100)
        links.new(node_in.outputs['Grid Size X'], node_grid.inputs['Size X'])
        links.new(node_in.outputs['Grid Size Y'], node_grid.inputs['Size Y'])
        links.new(node_in.outputs['Subdivisions X'], node_grid.inputs['Vertices X'])
        links.new(node_in.outputs['Subdivisions Y'], node_grid.inputs['Vertices Y'])

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

        # 6. Set Position: ベース高さを適用 (Gridノードの出力を接続)
        node_set_height = nodes.new('GeometryNodeSetPosition')
        node_set_height.location = (200, 100)
        links.new(node_grid.outputs['Mesh'], node_set_height.inputs['Geometry'])
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

        # 8. 道路オブジェクトが存在するか判定 (要素数 > 0)
        # Mesh要素数
        try:
            node_dom_mesh = nodes.new('GeometryNodeAttributeDomainSize')
        except RuntimeError:
            node_dom_mesh = nodes.new('GeometryNodeDomainSize')
        node_dom_mesh.component = 'MESH'
        node_dom_mesh.location = (600, 600)
        links.new(node_road_info.outputs['Geometry'], node_dom_mesh.inputs['Geometry'])

        # Curve要素数
        try:
            node_dom_curve = nodes.new('GeometryNodeAttributeDomainSize')
        except RuntimeError:
            node_dom_curve = nodes.new('GeometryNodeDomainSize')
        node_dom_curve.component = 'CURVE'
        node_dom_curve.location = (600, 750)
        links.new(node_road_info.outputs['Geometry'], node_dom_curve.inputs['Geometry'])

        # 要素数合計
        node_dom_sum = nodes.new('ShaderNodeMath')
        node_dom_sum.operation = 'ADD'
        node_dom_sum.location = (800, 670)
        mesh_count_out = node_dom_mesh.outputs['Point Count'] if 'Point Count' in node_dom_mesh.outputs else node_dom_mesh.outputs[0]
        curve_count_out = node_dom_curve.outputs['Point Count'] if 'Point Count' in node_dom_curve.outputs else node_dom_curve.outputs[0]
        links.new(mesh_count_out, node_dom_sum.inputs[0])
        links.new(curve_count_out, node_dom_sum.inputs[1])

        # 比較: 合計 > 0
        try:
            node_comp_exist = nodes.new('FunctionNodeCompare')
            node_comp_exist.data_type = 'INT'
            node_comp_exist.operation = 'GREATER_THAN'
        except RuntimeError:
            node_comp_exist = nodes.new('ShaderNodeMath')
            node_comp_exist.operation = 'GREATER_THAN'
        node_comp_exist.location = (950, 670)
        links.new(node_dom_sum.outputs[0], node_comp_exist.inputs[0])
        node_comp_exist.inputs[1].default_value = 0

        # Switchノードで道路がある場合のみ平坦化した座標を適用
        node_switch_pos = nodes.new('GeometryNodeSwitch')
        try:
            node_switch_pos.input_type = 'VECTOR'
        except AttributeError:
            try:
                node_switch_pos.data_type = 'VECTOR'
            except AttributeError:
                pass
        node_switch_pos.location = (1100, 500)
        comp_exist_out = node_comp_exist.outputs['Result'] if 'Result' in node_comp_exist.outputs else node_comp_exist.outputs[0]
        links.new(comp_exist_out, node_switch_pos.inputs['Switch'])
        
        # Falseのとき: 元の位置(ノイズによる起伏がある状態)
        node_pos_f = nodes.new('GeometryNodeInputPosition')
        node_pos_f.location = (950, 500)
        links.new(node_pos_f.outputs['Position'], node_switch_pos.inputs['False'])
        
        # Trueのとき: 平坦化座標
        links.new(node_comb_flat.outputs['Vector'], node_switch_pos.inputs['True'])

        # 9. Set Position: 位置を適用
        node_set_flat = nodes.new('GeometryNodeSetPosition')
        node_set_flat.location = (1250, 100)
        links.new(node_set_height.outputs['Geometry'], node_set_flat.inputs['Geometry'])
        links.new(node_switch_pos.outputs['Output'] if 'Output' in node_switch_pos.outputs else node_switch_pos.outputs[0], node_set_flat.inputs['Position'])



        # ==========================================
        # (C) 穴あけの基礎 (Mesh Boolean による滑らかな球状カット)
        # ==========================================
        # 1. Ico Sphere ノード (穴用の球体をノード内で生成)
        node_ico = nodes.new('GeometryNodeMeshIcoSphere')
        node_ico.location = (500, -100)
        node_ico.inputs['Subdivisions'].default_value = 3
        links.new(node_in.outputs['Hole Size'], node_ico.inputs['Radius'])

        # 2. Transform Geometry (球体を Hole Location に配置)
        node_trans = nodes.new('GeometryNodeTransform')
        node_trans.location = (700, -100)
        ico_mesh_out = node_ico.outputs['Mesh'] if 'Mesh' in node_ico.outputs else node_ico.outputs[0]
        links.new(ico_mesh_out, node_trans.inputs['Geometry'])
        
        # Translationソケットの接続 (Blender 4.0+ 互換)
        if 'Translation' in node_trans.inputs:
            links.new(node_in.outputs['Hole Location'], node_trans.inputs['Translation'])

        # 3. Mesh Boolean (地形から球体を差し引いて綺麗な円形の穴を作る)
        node_boolean = nodes.new('GeometryNodeMeshBoolean')
        node_boolean.operation = 'DIFFERENCE'
        node_boolean.location = (950, -100)
        links.new(node_set_flat.outputs['Geometry'], node_boolean.inputs['Mesh 1'])
        trans_geo_out = node_trans.outputs['Geometry'] if 'Geometry' in node_trans.outputs else node_trans.outputs[0]
        links.new(trans_geo_out, node_boolean.inputs['Mesh 2'])

        # 出力を最終的なGeometryに接続
        boolean_mesh_out = node_boolean.outputs['Mesh'] if 'Mesh' in node_boolean.outputs else node_boolean.outputs[0]
        links.new(boolean_mesh_out, node_out.inputs['Geometry'])


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
