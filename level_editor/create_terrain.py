# -*- coding: utf-8 -*-
import bpy  # type: ignore

class MYADDON_OT_create_terrain(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_create_terrain"
    bl_label = "地形生成"
    bl_description = "ジオメトリノードを使用して起伏、道路平坦化、スプライン山脈/谷を施した地形を生成します"
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
            # Geometry
            group.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
            # Road / Mountain / Valley Objects
            group.interface.new_socket('Road Object', in_out='INPUT', socket_type='NodeSocketObject')
            group.interface.new_socket('Mountain Object', in_out='INPUT', socket_type='NodeSocketObject')
            group.interface.new_socket('Valley Object', in_out='INPUT', socket_type='NodeSocketObject')
            # Grid Dimensions
            group.interface.new_socket('Grid Size X', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 100.0
            group.interface.new_socket('Grid Size Y', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 100.0
            sub_x = group.interface.new_socket('Subdivisions X', in_out='INPUT', socket_type='NodeSocketInt')
            sub_x.default_value = 100
            sub_x.min_value = 2
            sub_x.max_value = 1000
            sub_y = group.interface.new_socket('Subdivisions Y', in_out='INPUT', socket_type='NodeSocketInt')
            sub_y.default_value = 100
            sub_y.min_value = 2
            sub_y.max_value = 1000
            # Height and Noise Settings
            group.interface.new_socket('Noise Scale', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 0.05
            group.interface.new_socket('Terrain Height', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 10.0
            # Mountain Parameters
            group.interface.new_socket('Mountain Height', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 15.0
            group.interface.new_socket('Mountain Radius', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 10.0
            # Valley Parameters
            group.interface.new_socket('Valley Depth', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 8.0
            group.interface.new_socket('Valley Radius', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 8.0
            # Flat Parameters
            group.interface.new_socket('Flat Radius', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 3.0
            group.interface.new_socket('Flat Blend', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 2.0
            # Hole Parameters
            group.interface.new_socket('Hole Location', in_out='INPUT', socket_type='NodeSocketVector').default_value = (0.0, 0.0, 0.0)
            group.interface.new_socket('Hole Size', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 0.0

            # Outputs
            group.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
            group.interface.new_socket('Buildable Area', in_out='OUTPUT', socket_type='NodeSocketFloat')
        else:
            # 3.x 互換
            group.inputs.new('NodeSocketGeometry', 'Geometry')
            group.inputs.new('NodeSocketObject', 'Road Object')
            group.inputs.new('NodeSocketObject', 'Mountain Object')
            group.inputs.new('NodeSocketObject', 'Valley Object')
            group.inputs.new('NodeSocketFloat', 'Grid Size X').default_value = 100.0
            group.inputs.new('NodeSocketFloat', 'Grid Size Y').default_value = 100.0
            group.inputs.new('NodeSocketInt', 'Subdivisions X').default_value = 100
            group.inputs.new('NodeSocketInt', 'Subdivisions Y').default_value = 100
            group.inputs.new('NodeSocketFloat', 'Noise Scale').default_value = 0.05
            group.inputs.new('NodeSocketFloat', 'Terrain Height').default_value = 10.0
            group.inputs.new('NodeSocketFloat', 'Mountain Height').default_value = 15.0
            group.inputs.new('NodeSocketFloat', 'Mountain Radius').default_value = 10.0
            group.inputs.new('NodeSocketFloat', 'Valley Depth').default_value = 8.0
            group.inputs.new('NodeSocketFloat', 'Valley Radius').default_value = 8.0
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
        node_in.location = (-1500, 0)
        node_out = nodes.new('NodeGroupOutput')
        node_out.location = (1700, 0)

        # ==========================================
        # ヘルパー関数: カーブオブジェクトをメッシュへ安全に変換するSwitchノードの構築
        # (Geometry Proximityがカーブを非サポートであるエラーを回避するため)
        # ==========================================
        def add_curve_to_mesh_bypass(obj_geo_output, loc_x, loc_y):
            # Domain Size (Curve の Spline数)
            try:
                node_dom = nodes.new('GeometryNodeAttributeDomainSize')
            except RuntimeError:
                node_dom = nodes.new('GeometryNodeDomainSize')
            node_dom.component = 'CURVE'
            node_dom.location = (loc_x, loc_y + 150)
            links.new(obj_geo_output, node_dom.inputs['Geometry'])

            # Compare (Spline Count > 0)
            try:
                node_comp = nodes.new('FunctionNodeCompare')
                node_comp.data_type = 'INT'
                node_comp.operation = 'GREATER_THAN'
            except RuntimeError:
                node_comp = nodes.new('ShaderNodeMath')
                node_comp.operation = 'GREATER_THAN'
            node_comp.location = (loc_x + 200, loc_y + 150)
            spline_count_out = node_dom.outputs['Spline Count'] if 'Spline Count' in node_dom.outputs else node_dom.outputs[0]
            links.new(spline_count_out, node_comp.inputs[0])
            node_comp.inputs[1].default_value = 0

            # Curve to Mesh
            node_c2m = nodes.new('GeometryNodeCurveToMesh')
            node_c2m.location = (loc_x, loc_y)
            links.new(obj_geo_output, node_c2m.inputs['Curve'])

            # Switch (Geometry型)
            node_switch = nodes.new('GeometryNodeSwitch')
            try:
                node_switch.input_type = 'GEOMETRY'
            except AttributeError:
                try:
                    node_switch.data_type = 'GEOMETRY'
                except AttributeError:
                    pass
            node_switch.location = (loc_x + 400, loc_y + 50)
            comp_out = node_comp.outputs['Result'] if 'Result' in node_comp.outputs else node_comp.outputs[0]
            links.new(comp_out, node_switch.inputs['Switch'])
            links.new(obj_geo_output, node_switch.inputs['False'])
            links.new(node_c2m.outputs['Mesh'], node_switch.inputs['True'])

            return node_switch.outputs['Output'] if 'Output' in node_switch.outputs else node_switch.outputs[0]


        # ==========================================
        # (A) 土台グリッドの生成とベース起伏
        # ==========================================
        # 0. Grid Primitive ノード (サイズと分割数をいつでも変更可能)
        node_grid = nodes.new('GeometryNodeMeshGrid')
        node_grid.location = (-1300, 200)
        links.new(node_in.outputs['Grid Size X'], node_grid.inputs['Size X'])
        links.new(node_in.outputs['Grid Size Y'], node_grid.inputs['Size Y'])
        links.new(node_in.outputs['Subdivisions X'], node_grid.inputs['Vertices X'])
        links.new(node_in.outputs['Subdivisions Y'], node_grid.inputs['Vertices Y'])

        # 1. Position ノード
        node_pos = nodes.new('GeometryNodeInputPosition')
        node_pos.location = (-1300, -200)

        # 2. Noise Texture ノード
        try:
            node_noise = nodes.new('FunctionNodeNoiseTexture')
        except RuntimeError:
            node_noise = nodes.new('ShaderNodeTexNoise')
        node_noise.location = (-1100, -200)
        links.new(node_pos.outputs['Position'], node_noise.inputs['Vector'])
        links.new(node_in.outputs['Noise Scale'], node_noise.inputs['Scale'])

        # 3. Math: Subtract 0.5 (ノイズ高さを中央基準にする)
        node_sub = nodes.new('ShaderNodeMath')
        node_sub.operation = 'SUBTRACT'
        node_sub.inputs[1].default_value = 0.5
        node_sub.location = (-900, -200)
        noise_out = node_noise.outputs['Factor'] if 'Factor' in node_noise.outputs else node_noise.outputs[0]
        links.new(noise_out, node_sub.inputs[0])

        # 4. Math: Multiply by Terrain Height
        node_mult = nodes.new('ShaderNodeMath')
        node_mult.operation = 'MULTIPLY'
        node_mult.location = (-700, -200)
        links.new(node_sub.outputs[0], node_mult.inputs[0])
        links.new(node_in.outputs['Terrain Height'], node_mult.inputs[1])


        # ==========================================
        # (B) スプライン山脈 (Mountain Object)
        # ==========================================
        # 1. Object Info (山オブジェクト情報)
        node_mt_info = nodes.new('GeometryNodeObjectInfo')
        node_mt_info.transform_space = 'RELATIVE'
        node_mt_info.location = (-1300, 600)
        links.new(node_in.outputs['Mountain Object'], node_mt_info.inputs['Object'])

        # 1.5. Curve to Mesh バイパス
        mt_geometry_processed = add_curve_to_mesh_bypass(node_mt_info.outputs['Geometry'], -1100, 650)

        # 2. Geometry Proximity (山への近接距離)
        node_mt_prox = nodes.new('GeometryNodeProximity')
        node_mt_prox.target_element = 'EDGES'
        node_mt_prox.location = (-600, 600)
        links.new(mt_geometry_processed, node_mt_prox.inputs['Target'])

        # 3. Map Range (距離をウェイト 0.0 ~ 1.0 にマッピング)
        node_mt_map = nodes.new('ShaderNodeMapRange')
        node_mt_map.interpolation_type = 'SMOOTHSTEP'
        node_mt_map.inputs['From Min'].default_value = 0.0
        node_mt_map.inputs['To Min'].default_value = 1.0
        node_mt_map.inputs['To Max'].default_value = 0.0
        node_mt_map.location = (-400, 600)
        links.new(node_mt_prox.outputs['Distance'], node_mt_map.inputs['Value'])
        links.new(node_in.outputs['Mountain Radius'], node_mt_map.inputs['From Max'])

        # 4. 山のオブジェクト存在判定 (バイパス処理)
        try:
            node_mt_dom_mesh = nodes.new('GeometryNodeAttributeDomainSize')
        except RuntimeError:
            node_mt_dom_mesh = nodes.new('GeometryNodeDomainSize')
        node_mt_dom_mesh.component = 'MESH'
        node_mt_dom_mesh.location = (-1300, 900)
        links.new(node_mt_info.outputs['Geometry'], node_mt_dom_mesh.inputs['Geometry'])

        try:
            node_mt_dom_curve = nodes.new('GeometryNodeAttributeDomainSize')
        except RuntimeError:
            node_mt_dom_curve = nodes.new('GeometryNodeDomainSize')
        node_mt_dom_curve.component = 'CURVE'
        node_mt_dom_curve.location = (-1300, 1050)
        links.new(node_mt_info.outputs['Geometry'], node_mt_dom_curve.inputs['Geometry'])

        node_mt_sum = nodes.new('ShaderNodeMath')
        node_mt_sum.operation = 'ADD'
        node_mt_sum.location = (-1100, 950)
        mt_mesh_count = node_mt_dom_mesh.outputs['Point Count'] if 'Point Count' in node_mt_dom_mesh.outputs else node_mt_dom_mesh.outputs[0]
        mt_curve_count = node_mt_dom_curve.outputs['Point Count'] if 'Point Count' in node_mt_dom_curve.outputs else node_mt_dom_curve.outputs[0]
        links.new(mt_mesh_count, node_mt_sum.inputs[0])
        links.new(mt_curve_count, node_mt_sum.inputs[1])

        try:
            node_mt_exist = nodes.new('FunctionNodeCompare')
            node_mt_exist.data_type = 'INT'
            node_mt_exist.operation = 'GREATER_THAN'
        except RuntimeError:
            node_mt_exist = nodes.new('ShaderNodeMath')
            node_mt_exist.operation = 'GREATER_THAN'
        node_mt_exist.location = (-900, 950)
        links.new(node_mt_sum.outputs[0], node_mt_exist.inputs[0])
        node_mt_exist.inputs[1].default_value = 0

        # 山の合計隆起高さの算出
        node_mt_mult1 = nodes.new('ShaderNodeMath')
        node_mt_mult1.operation = 'MULTIPLY'
        node_mt_mult1.location = (-200, 600)
        links.new(node_mt_map.outputs['Result'], node_mt_mult1.inputs[0])
        links.new(node_in.outputs['Mountain Height'], node_mt_mult1.inputs[1])

        node_mt_height_final = nodes.new('ShaderNodeMath')
        node_mt_height_final.operation = 'MULTIPLY'
        node_mt_height_final.location = (-50, 600)
        links.new(node_mt_mult1.outputs[0], node_mt_height_final.inputs[0])
        mt_exist_out = node_mt_exist.outputs['Result'] if 'Result' in node_mt_exist.outputs else node_mt_exist.outputs[0]
        links.new(mt_exist_out, node_mt_height_final.inputs[1])


        # ==========================================
        # (C) スプライン谷 (Valley Object)
        # ==========================================
        # 1. Object Info (谷オブジェクト情報)
        node_vl_info = nodes.new('GeometryNodeObjectInfo')
        node_vl_info.transform_space = 'RELATIVE'
        node_vl_info.location = (-1300, -400)
        links.new(node_in.outputs['Valley Object'], node_vl_info.inputs['Object'])

        # 1.5. Curve to Mesh バイパス
        vl_geometry_processed = add_curve_to_mesh_bypass(node_vl_info.outputs['Geometry'], -1100, -350)

        # 2. Geometry Proximity (谷への近接距離)
        node_vl_prox = nodes.new('GeometryNodeProximity')
        node_vl_prox.target_element = 'EDGES'
        node_vl_prox.location = (-600, -400)
        links.new(vl_geometry_processed, node_vl_prox.inputs['Target'])

        # 3. Map Range (距離をウェイトにマッピング)
        node_vl_map = nodes.new('ShaderNodeMapRange')
        node_vl_map.interpolation_type = 'SMOOTHSTEP'
        node_vl_map.inputs['From Min'].default_value = 0.0
        node_vl_map.inputs['To Min'].default_value = 1.0
        node_vl_map.inputs['To Max'].default_value = 0.0
        node_vl_map.location = (-400, -400)
        links.new(node_vl_prox.outputs['Distance'], node_vl_map.inputs['Value'])
        links.new(node_in.outputs['Valley Radius'], node_vl_map.inputs['From Max'])

        # 4. 谷のオブジェクト存在判定 (バイパス処理)
        try:
            node_vl_dom_mesh = nodes.new('GeometryNodeAttributeDomainSize')
        except RuntimeError:
            node_vl_dom_mesh = nodes.new('GeometryNodeDomainSize')
        node_vl_dom_mesh.component = 'MESH'
        node_vl_dom_mesh.location = (-1300, -600)
        links.new(node_vl_info.outputs['Geometry'], node_vl_dom_mesh.inputs['Geometry'])

        try:
            node_vl_dom_curve = nodes.new('GeometryNodeAttributeDomainSize')
        except RuntimeError:
            node_vl_dom_curve = nodes.new('GeometryNodeDomainSize')
        node_vl_dom_curve.component = 'CURVE'
        node_vl_dom_curve.location = (-1300, -750)
        links.new(node_vl_info.outputs['Geometry'], node_vl_dom_curve.inputs['Geometry'])

        node_vl_sum = nodes.new('ShaderNodeMath')
        node_vl_sum.operation = 'ADD'
        node_vl_sum.location = (-1100, -650)
        vl_mesh_count = node_vl_dom_mesh.outputs['Point Count'] if 'Point Count' in node_vl_dom_mesh.outputs else node_vl_dom_mesh.outputs[0]
        vl_curve_count = node_vl_dom_curve.outputs['Point Count'] if 'Point Count' in node_vl_dom_curve.outputs else node_vl_dom_curve.outputs[0]
        links.new(vl_mesh_count, node_vl_sum.inputs[0])
        links.new(vl_curve_count, node_vl_sum.inputs[1])

        try:
            node_vl_exist = nodes.new('FunctionNodeCompare')
            node_vl_exist.data_type = 'INT'
            node_vl_exist.operation = 'GREATER_THAN'
        except RuntimeError:
            node_vl_exist = nodes.new('ShaderNodeMath')
            node_vl_exist.operation = 'GREATER_THAN'
        node_vl_exist.location = (-900, -650)
        links.new(node_vl_sum.outputs[0], node_vl_exist.inputs[0])
        node_vl_exist.inputs[1].default_value = 0

        # 谷の合計沈下量の算出
        node_vl_mult1 = nodes.new('ShaderNodeMath')
        node_vl_mult1.operation = 'MULTIPLY'
        node_vl_mult1.location = (-200, -400)
        links.new(node_vl_map.outputs['Result'], node_vl_mult1.inputs[0])
        links.new(node_in.outputs['Valley Depth'], node_vl_mult1.inputs[1])

        node_vl_depth_final = nodes.new('ShaderNodeMath')
        node_vl_depth_final.operation = 'MULTIPLY'
        node_vl_depth_final.location = (-50, -400)
        links.new(node_vl_mult1.outputs[0], node_vl_depth_final.inputs[0])
        vl_exist_out = node_vl_exist.outputs['Result'] if 'Result' in node_vl_exist.outputs else node_vl_exist.outputs[0]
        links.new(vl_exist_out, node_vl_depth_final.inputs[1])


        # ==========================================
        # 高度合成: (ベースノイズ) + (山脈の高さ) - (谷の深さ)
        # ==========================================
        # 1. (ベースノイズ) + (山脈の高さ)
        node_add_mt = nodes.new('ShaderNodeMath')
        node_add_mt.operation = 'ADD'
        node_add_mt.location = (150, -200)
        links.new(node_mult.outputs[0], node_add_mt.inputs[0])
        links.new(node_mt_height_final.outputs[0], node_add_mt.inputs[1])

        # 2. 上記 - (谷の深さ)
        node_sub_vl = nodes.new('ShaderNodeMath')
        node_sub_vl.operation = 'SUBTRACT'
        node_sub_vl.location = (300, -200)
        links.new(node_add_mt.outputs[0], node_sub_vl.inputs[0])
        links.new(node_vl_depth_final.outputs[0], node_sub_vl.inputs[1])

        # Z高度に結合
        node_comb_height = nodes.new('ShaderNodeCombineXYZ')
        node_comb_height.location = (450, -200)
        links.new(node_sub_vl.outputs[0], node_comb_height.inputs['Z'])

        # Set Position: 最終高度を適用
        node_set_height = nodes.new('GeometryNodeSetPosition')
        node_set_height.location = (600, 100)
        links.new(node_grid.outputs['Mesh'], node_set_height.inputs['Geometry'])
        links.new(node_comb_height.outputs['Vector'], node_set_height.inputs['Offset'])


        # ==========================================
        # (D) 道路まわりの平坦化 (Geometry Proximity)
        # ==========================================
        # 1. Object Info (道路オブジェクト情報)
        node_road_info = nodes.new('GeometryNodeObjectInfo')
        node_road_info.transform_space = 'RELATIVE'
        node_road_info.location = (50, 400)
        links.new(node_in.outputs['Road Object'], node_road_info.inputs['Object'])

        # 1.5. Curve to Mesh バイパス
        road_geometry_processed = add_curve_to_mesh_bypass(node_road_info.outputs['Geometry'], 250, 450)

        # 2. Geometry Proximity (道路メッシュへの近接)
        node_proximity = nodes.new('GeometryNodeProximity')
        node_proximity.target_element = 'FACES'
        node_proximity.location = (700, 400)
        links.new(road_geometry_processed, node_proximity.inputs['Target'])

        # 3. Separate XYZ: 道路近接点のZ座標
        node_sep_prox = nodes.new('ShaderNodeSeparateXYZ')
        node_sep_prox.location = (900, 450)
        links.new(node_proximity.outputs['Position'], node_sep_prox.inputs['Vector'])

        # 4. Separate XYZ: 現在の頂点のZ座標 (高さ変更後)
        node_curr_pos = nodes.new('GeometryNodeInputPosition')
        node_curr_pos.location = (700, 200)
        node_sep_curr = nodes.new('ShaderNodeSeparateXYZ')
        node_sep_curr.location = (900, 200)
        links.new(node_curr_pos.outputs['Position'], node_sep_curr.inputs['Vector'])

        # 5. Map Range: 距離を平坦化のウェイト(Factor: 0.0 ~ 1.0)にマッピング
        node_map_range = nodes.new('ShaderNodeMapRange')
        node_map_range.location = (900, 650)
        node_map_range.interpolation_type = 'LINEAR'
        node_map_range.inputs['To Min'].default_value = 1.0
        node_map_range.inputs['To Max'].default_value = 0.0
        links.new(node_proximity.outputs['Distance'], node_map_range.inputs['Value'])
        links.new(node_in.outputs['Flat Radius'], node_map_range.inputs['From Min'])

        # Flat Radius + Flat Blend の計算
        node_add_blend = nodes.new('ShaderNodeMath')
        node_add_blend.operation = 'ADD'
        node_add_blend.location = (700, 650)
        links.new(node_in.outputs['Flat Radius'], node_add_blend.inputs[0])
        links.new(node_in.outputs['Flat Blend'], node_add_blend.inputs[1])
        links.new(node_add_blend.outputs[0], node_map_range.inputs['From Max'])

        # 6. 線形補間(Lerp)の計算 (Mix Float ノードの互換性対策)
        # MixZ = CurrZ + (ProxZ - CurrZ) * Factor
        # (A) ProxZ - CurrZ
        node_diff = nodes.new('ShaderNodeMath')
        node_diff.operation = 'SUBTRACT'
        node_diff.location = (1100, 400)
        links.new(node_sep_prox.outputs['Z'], node_diff.inputs[0])
        links.new(node_sep_curr.outputs['Z'], node_diff.inputs[1])

        # (B) (ProxZ - CurrZ) * Factor
        node_mult_factor = nodes.new('ShaderNodeMath')
        node_mult_factor.operation = 'MULTIPLY'
        node_mult_factor.location = (1250, 400)
        links.new(node_diff.outputs[0], node_mult_factor.inputs[0])
        links.new(node_map_range.outputs['Result'], node_mult_factor.inputs[1])

        # (C) CurrZ + ...
        node_mix_z = nodes.new('ShaderNodeMath')
        node_mix_z.operation = 'ADD'
        node_mix_z.location = (1400, 400)
        links.new(node_sep_curr.outputs['Z'], node_mix_z.inputs[0])
        links.new(node_mult_factor.outputs[0], node_mix_z.inputs[1])

        # 7. Combine XYZ: 平坦化後の位置を作成 (XYは元の位置を維持)
        node_comb_flat = nodes.new('ShaderNodeCombineXYZ')
        node_comb_flat.location = (1550, 300)
        links.new(node_sep_curr.outputs['X'], node_comb_flat.inputs['X'])
        links.new(node_sep_curr.outputs['Y'], node_comb_flat.inputs['Y'])
        links.new(node_mix_z.outputs[0], node_comb_flat.inputs['Z'])

        # 8. 道路オブジェクトが存在するか判定 (要素数 > 0)
        try:
            node_dom = nodes.new('GeometryNodeAttributeDomainSize')
        except RuntimeError:
            node_dom = nodes.new('GeometryNodeDomainSize')
        node_dom.component = 'MESH'
        node_dom.location = (1250, 600)
        links.new(node_road_info.outputs['Geometry'], node_dom.inputs['Geometry'])

        try:
            node_dom_curve = nodes.new('GeometryNodeAttributeDomainSize')
        except RuntimeError:
            node_dom_curve = nodes.new('GeometryNodeDomainSize')
        node_dom_curve.component = 'CURVE'
        node_dom_curve.location = (1250, 750)
        links.new(node_road_info.outputs['Geometry'], node_dom_curve.inputs['Geometry'])

        node_dom_sum = nodes.new('ShaderNodeMath')
        node_dom_sum.operation = 'ADD'
        node_dom_sum.location = (1450, 670)
        mesh_count_out = node_dom.outputs['Point Count'] if 'Point Count' in node_dom.outputs else node_dom.outputs[0]
        curve_count_out = node_dom_curve.outputs['Point Count'] if 'Point Count' in node_dom_curve.outputs else node_dom_curve.outputs[0]
        links.new(mesh_count_out, node_dom_sum.inputs[0])
        links.new(curve_count_out, node_dom_sum.inputs[1])

        try:
            node_comp_exist = nodes.new('FunctionNodeCompare')
            node_comp_exist.data_type = 'INT'
            node_comp_exist.operation = 'GREATER_THAN'
        except RuntimeError:
            node_comp_exist = nodes.new('ShaderNodeMath')
            node_comp_exist.operation = 'GREATER_THAN'
        node_comp_exist.location = (1600, 670)
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
        node_switch_pos.location = (1750, 500)
        comp_exist_out = node_comp_exist.outputs['Result'] if 'Result' in node_comp_exist.outputs else node_comp_exist.outputs[0]
        links.new(comp_exist_out, node_switch_pos.inputs['Switch'])
        
        node_pos_f = nodes.new('GeometryNodeInputPosition')
        node_pos_f.location = (1600, 500)
        links.new(node_pos_f.outputs['Position'], node_switch_pos.inputs['False'])
        links.new(node_comb_flat.outputs['Vector'], node_switch_pos.inputs['True'])

        # 9. Set Position: 位置を適用
        node_set_flat = nodes.new('GeometryNodeSetPosition')
        node_set_flat.location = (1900, 100)
        links.new(node_set_height.outputs['Geometry'], node_set_flat.inputs['Geometry'])
        links.new(node_switch_pos.outputs['Output'] if 'Output' in node_switch_pos.outputs else node_switch_pos.outputs[0], node_set_flat.inputs['Position'])


        # ==========================================
        # (E) 穴あけの基礎 (Mesh Boolean)
        # ==========================================
        # 1. Ico Sphere ノード
        node_ico = nodes.new('GeometryNodeMeshIcoSphere')
        node_ico.location = (1150, -100)
        node_ico.inputs['Subdivisions'].default_value = 3
        links.new(node_in.outputs['Hole Size'], node_ico.inputs['Radius'])

        # 2. Transform Geometry
        node_trans = nodes.new('GeometryNodeTransform')
        node_trans.location = (1350, -100)
        ico_mesh_out = node_ico.outputs['Mesh'] if 'Mesh' in node_ico.outputs else node_ico.outputs[0]
        links.new(ico_mesh_out, node_trans.inputs['Geometry'])
        
        if 'Translation' in node_trans.inputs:
            links.new(node_in.outputs['Hole Location'], node_trans.inputs['Translation'])

        # 3. Mesh Boolean
        node_boolean = nodes.new('GeometryNodeMeshBoolean')
        node_boolean.operation = 'DIFFERENCE'
        node_boolean.location = (1600, -100)
        links.new(node_set_flat.outputs['Geometry'], node_boolean.inputs['Mesh 1'])
        trans_geo_out = node_trans.outputs['Geometry'] if 'Geometry' in node_trans.outputs else node_trans.outputs[0]
        links.new(trans_geo_out, node_boolean.inputs['Mesh 2'])

        # 出力を最終的なGeometryに接続
        boolean_mesh_out = node_boolean.outputs['Mesh'] if 'Mesh' in node_boolean.outputs else node_boolean.outputs[0]
        links.new(boolean_mesh_out, node_out.inputs['Geometry'])


        # ==========================================
        # (F) 建築可能エリアの出力属性判定
        # ==========================================
        # 1. Normal ノード
        node_normal = nodes.new('GeometryNodeInputNormal')
        node_normal.location = (1150, -350)

        # 2. Separate XYZ
        node_sep_normal = nodes.new('ShaderNodeSeparateXYZ')
        node_sep_normal.location = (1330, -350)
        links.new(node_normal.outputs['Normal'], node_sep_normal.inputs['Vector'])

        # 3. Compare: Slope Z >= 0.9 (約25度以下の傾斜)
        try:
            node_comp_slope = nodes.new('FunctionNodeCompare')
            node_comp_slope.data_type = 'FLOAT'
            node_comp_slope.operation = 'GREATER_EQUAL'
        except RuntimeError:
            node_comp_slope = nodes.new('ShaderNodeMath')
            node_comp_slope.operation = 'GREATER_THAN'
        node_comp_slope.location = (1500, -350)
        links.new(node_sep_normal.outputs['Z'], node_comp_slope.inputs[0])
        node_comp_slope.inputs[1].default_value = 0.9

        # 4. 道路からの距離判定 (2.5 <= Distance <= 12.0)
        try:
            node_comp_dist_min = nodes.new('FunctionNodeCompare')
            node_comp_dist_min.data_type = 'FLOAT'
            node_comp_dist_min.operation = 'GREATER_EQUAL'
        except RuntimeError:
            node_comp_dist_min = nodes.new('ShaderNodeMath')
            node_comp_dist_min.operation = 'GREATER_THAN'
        node_comp_dist_min.location = (1330, -550)
        links.new(node_proximity.outputs['Distance'], node_comp_dist_min.inputs[0])
        node_comp_dist_min.inputs[1].default_value = 2.5

        try:
            node_comp_dist_max = nodes.new('FunctionNodeCompare')
            node_comp_dist_max.data_type = 'FLOAT'
            node_comp_dist_max.operation = 'LESS_EQUAL'
        except RuntimeError:
            node_comp_dist_max = nodes.new('ShaderNodeMath')
            node_comp_dist_max.operation = 'LESS_THAN'
        node_comp_dist_max.location = (1500, -550)
        links.new(node_proximity.outputs['Distance'], node_comp_dist_max.inputs[0])
        node_comp_dist_max.inputs[1].default_value = 12.0

        # AND結合 (距離の範囲)
        node_and_dist = nodes.new('ShaderNodeMath')
        node_and_dist.operation = 'MULTIPLY'
        node_and_dist.location = (1670, -550)
        comp_min_out = node_comp_dist_min.outputs['Result'] if 'Result' in node_comp_dist_min.outputs else node_comp_dist_min.outputs[0]
        comp_max_out = node_comp_dist_max.outputs['Result'] if 'Result' in node_comp_dist_max.outputs else node_comp_dist_max.outputs[0]
        links.new(comp_min_out, node_and_dist.inputs[0])
        links.new(comp_max_out, node_and_dist.inputs[1])

        # すべてを乗算してAND条件にする
        node_and_all = nodes.new('ShaderNodeMath')
        node_and_all.operation = 'MULTIPLY'
        node_and_all.location = (1850, -350)
        comp_slope_out = node_comp_slope.outputs['Result'] if 'Result' in node_comp_slope.outputs else node_comp_slope.outputs[0]
        links.new(comp_slope_out, node_and_all.inputs[0])
        links.new(node_and_dist.outputs[0], node_and_all.inputs[1])

        # 出力
        links.new(node_and_all.outputs[0], node_out.inputs['Buildable Area'])

        # 4. 作成した地形オブジェクトをアクティブにする
        context.view_layer.objects.active = terrain_obj
        terrain_obj.select_set(True)

        print("ジオメトリノード地形生成システムが構築されました。")
        return {'FINISHED'}
