# -*- coding: utf-8 -*-
import bpy  # type: ignore

class MYADDON_OT_create_terrain(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_create_terrain"
    bl_label = "地形生成"
    bl_description = "ジオメトリノードを使用して起伏、道路平坦化、スプライン山脈/谷を施した地形を生成します"
    bl_options = {'REGISTER', 'UNDO'}

    preset: bpy.props.EnumProperty(
        name="起伏プリセット",
        description="ベースとなる起伏タイプを選択",
        items=[
            ('FLAT', "平野 / 街 (Flat / City)", "ベース起伏を抑えてほぼ平坦にし、都市や道路に適した地面にします"),
            ('HILLS', "丘陵 (Hills)", "適度な起伏のある自然な地形にします"),
            ('MOUNTAINS', "山岳 (Mountains)", "起伏の大きな険しい山岳地形にします"),
        ],
        default='FLAT',
    ) # type: ignore

    biome: bpy.props.EnumProperty(
        name="環境 (バイオーム)",
        description="地形のマテリアル・環境タイプを選択",
        items=[
            ('MULTI', "複合大陸 (Multi-Biome)", "標高連動の雪山山頂＋大域ノイズによる草原・砂漠・峡谷の複合バイオーム"),
            ('PLAINS', "草原 / 平原 (Plains)", "豊かなグリーンと茶褐色の崖"),
            ('DESERT', "砂漠 (Desert)", "温かみのあるオレンジ〜黄色の砂地と赤褐色の岩肌"),
            ('SNOW', "雪山 / 氷河 (Snow)", "白銀の雪原と冷たい青暗い岩肌"),
            ('CANYON', "峡谷 / 荒野 (Canyon)", "赤土やテラコッタ層の雄大な岩盤"),
            ('VOLCANO', "火山 (Volcano)", "黒い溶岩石と灰の大地"),
        ],
        default='MULTI',
    ) # type: ignore

    terrain_scale: bpy.props.EnumProperty(
        name="地形スケール",
        description="地形の全体サイズ（幅×奥行）を選択",
        items=[
            ('40KM', "40km 四方 (40,000m × 40,000m: 超広大)", "40kmオープンワールドスケール（推奨）"),
            ('20KM', "20km 四方 (20,000m × 20,000m: 標準)", "従来の20kmオープンワールドスケール"),
        ],
        default='40KM',
    ) # type: ignore

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=340)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "terrain_scale")
        layout.prop(self, "preset")
        layout.prop(self, "biome")

    def execute(self, context):
        is_40km = (self.terrain_scale == '40KM')
        target_size = 40000.0 if is_40km else 20000.0

        # プリセットに応じたベース起伏とノイズスケール (40km / 20kmスケール対応)
        if self.preset == 'FLAT':
            preset_height = 5.0
            preset_noise = 0.0001 if is_40km else 0.0002
        elif self.preset == 'HILLS':
            preset_height = 100.0 if is_40km else 80.0
            preset_noise = 0.00025 if is_40km else 0.0005
        else: # MOUNTAINS
            preset_height = 350.0 if is_40km else 300.0
            preset_noise = 0.0004 if is_40km else 0.0008

        mt_height = 550.0 if is_40km else 400.0
        mt_radius = 2200.0 if is_40km else 1200.0
        val_depth = 450.0 if is_40km else 350.0
        val_radius = 2200.0 if is_40km else 1500.0

        # 1. 空の地形用メッシュオブジェクトの作成 (サイズや分割数はジオメトリノード側で動的に制御します)
        mesh_data = bpy.data.meshes.new("TerrainMesh")
        terrain_obj = bpy.data.objects.new("Terrain", mesh_data)
        context.collection.objects.link(terrain_obj)

        # 2. Geometry Nodes モディファイアの追加
        gn_mod = terrain_obj.modifiers.new(name="TerrainGen", type='NODES')
        group = bpy.data.node_groups.new("TerrainGenTree", 'GeometryNodeTree')

        # 3. 入出力ソケットの定義 (Blender 4.0+ と 3.x 以前の互換性)
        if hasattr(group, "interface"):
            # Geometry
            group.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
            # Road / Mountain / Valley Objects
            group.interface.new_socket('Road Object', in_out='INPUT', socket_type='NodeSocketObject')
            group.interface.new_socket('Mountain Collection', in_out='INPUT', socket_type='NodeSocketCollection')
            group.interface.new_socket('Valley Collection', in_out='INPUT', socket_type='NodeSocketCollection')
            # Grid Dimensions (40km: 40000.0m / 20km: 20000.0m)
            group.interface.new_socket('Grid Size X', in_out='INPUT', socket_type='NodeSocketFloat').default_value = target_size
            group.interface.new_socket('Grid Size Y', in_out='INPUT', socket_type='NodeSocketFloat').default_value = target_size

            # Height and Noise Settings
            group.interface.new_socket('Noise Scale', in_out='INPUT', socket_type='NodeSocketFloat').default_value = preset_noise
            group.interface.new_socket('Noise Offset', in_out='INPUT', socket_type='NodeSocketVector').default_value = (0.0, 0.0, 0.0)
            group.interface.new_socket('Terrain Height', in_out='INPUT', socket_type='NodeSocketFloat').default_value = preset_height
            group.interface.new_socket('City Center', in_out='INPUT', socket_type='NodeSocketVector').default_value = (0.0, 0.0, 0.0)
            group.interface.new_socket('City Grade Radius', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 0.0
            sock_ridge = group.interface.new_socket('Ridge Sharpness', in_out='INPUT', socket_type='NodeSocketFloat')
            sock_ridge.default_value = 0.5
            if hasattr(sock_ridge, 'min_value'):
                sock_ridge.min_value = 0.0
                sock_ridge.max_value = 1.0
            sock_detail = group.interface.new_socket('Detail Strength', in_out='INPUT', socket_type='NodeSocketFloat')
            sock_detail.default_value = 0.35
            if hasattr(sock_detail, 'min_value'):
                sock_detail.min_value = 0.0
                sock_detail.max_value = 1.0
            # Mountain Parameters
            group.interface.new_socket('Mountain Height', in_out='INPUT', socket_type='NodeSocketFloat').default_value = mt_height
            group.interface.new_socket('Mountain Radius', in_out='INPUT', socket_type='NodeSocketFloat').default_value = mt_radius
            # Valley Parameters
            group.interface.new_socket('Valley Depth', in_out='INPUT', socket_type='NodeSocketFloat').default_value = val_depth
            group.interface.new_socket('Valley Radius', in_out='INPUT', socket_type='NodeSocketFloat').default_value = val_radius
            # Flat Parameters
            group.interface.new_socket('Flat Radius', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 65.0
            group.interface.new_socket('Flat Blend', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 180.0
            # Hole Parameters
            group.interface.new_socket('Hole Location', in_out='INPUT', socket_type='NodeSocketVector').default_value = (0.0, 0.0, 0.0)
            group.interface.new_socket('Hole Size', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 0.0
            group.interface.new_socket('Tunnel Cutters', in_out='INPUT', socket_type='NodeSocketCollection')

            # Outputs
            group.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
            group.interface.new_socket('Buildable Area', in_out='OUTPUT', socket_type='NodeSocketFloat')
        else:
            # 3.x 互換
            group.inputs.new('NodeSocketGeometry', 'Geometry')
            group.inputs.new('NodeSocketObject', 'Road Object')
            group.inputs.new('NodeSocketCollection', 'Mountain Collection')
            group.inputs.new('NodeSocketCollection', 'Valley Collection')
            group.inputs.new('NodeSocketFloat', 'Grid Size X').default_value = target_size
            group.inputs.new('NodeSocketFloat', 'Grid Size Y').default_value = target_size

            group.inputs.new('NodeSocketFloat', 'Noise Scale').default_value = preset_noise
            group.inputs.new('NodeSocketVector', 'Noise Offset').default_value = (0.0, 0.0, 0.0)
            group.inputs.new('NodeSocketFloat', 'Terrain Height').default_value = preset_height
            group.inputs.new('NodeSocketVector', 'City Center').default_value = (0.0, 0.0, 0.0)
            group.inputs.new('NodeSocketFloat', 'City Grade Radius').default_value = 0.0
            group.inputs.new('NodeSocketFloat', 'Ridge Sharpness').default_value = 0.5
            group.inputs.new('NodeSocketFloat', 'Detail Strength').default_value = 0.35
            group.inputs.new('NodeSocketFloat', 'Mountain Height').default_value = mt_height
            group.inputs.new('NodeSocketFloat', 'Mountain Radius').default_value = mt_radius
            group.inputs.new('NodeSocketFloat', 'Valley Depth').default_value = val_depth
            group.inputs.new('NodeSocketFloat', 'Valley Radius').default_value = val_radius
            group.inputs.new('NodeSocketFloat', 'Flat Radius').default_value = 65.0
            group.inputs.new('NodeSocketFloat', 'Flat Blend').default_value = 180.0
            group.inputs.new('NodeSocketVector', 'Hole Location').default_value = (0.0, 0.0, 0.0)
            group.inputs.new('NodeSocketFloat', 'Hole Size').default_value = 0.0
            group.inputs.new('NodeSocketCollection', 'Tunnel Cutters')
            
            group.outputs.new('NodeSocketGeometry', 'Geometry')
            group.outputs.new('NodeSocketFloat', 'Buildable Area')

        # (ノードとリンクの構築完了後に割り当てるよう、最後尾に移動します)

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
            # Domain Size (Curve の Point数)
            try:
                node_dom = nodes.new('GeometryNodeAttributeDomainSize')
            except RuntimeError:
                node_dom = nodes.new('GeometryNodeDomainSize')
            node_dom.component = 'CURVE'
            node_dom.location = (loc_x, loc_y + 150)
            links.new(obj_geo_output, node_dom.inputs['Geometry'])

            # Compare (Point Count > 0)
            node_comp = nodes.new('ShaderNodeMath')
            node_comp.operation = 'GREATER_THAN'
            node_comp.location = (loc_x + 200, loc_y + 150)
            point_count_out = node_dom.outputs['Point Count'] if 'Point Count' in node_dom.outputs else node_dom.outputs[0]
            links.new(point_count_out, node_comp.inputs[0])
            node_comp.inputs[1].default_value = 0.0

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
        # Is Viewport ノード (ビューポートでのみ分割数を減らして動作を軽くする)
        try:
            node_is_viewport = nodes.new('GeometryNodeIsViewport')
        except RuntimeError:
            # 古いBlenderバージョン用のフォールバック（存在しない場合は常にフル解像度）
            node_is_viewport = None

        # ベース分割数計算 (Size / 20.0m 間隔: 20kmなら1000分割)
        math_step_x = nodes.new('ShaderNodeMath')
        math_step_x.operation = 'DIVIDE'
        math_step_x.inputs[1].default_value = 20.0
        links.new(node_in.outputs['Grid Size X'], math_step_x.inputs[0])

        math_step_y = nodes.new('ShaderNodeMath')
        math_step_y.operation = 'DIVIDE'
        math_step_y.inputs[1].default_value = 20.0
        links.new(node_in.outputs['Grid Size Y'], math_step_y.inputs[0])

        # ビューポート時の分割数計算 (40km時 2000/1.8 ≈ 1111分割、20km時 1000/1.8 ≈ 555分割)
        math_div_x = nodes.new('ShaderNodeMath')
        math_div_x.operation = 'DIVIDE'
        math_div_x.inputs[1].default_value = 1.8
        links.new(math_step_x.outputs[0], math_div_x.inputs[0])

        math_div_y = nodes.new('ShaderNodeMath')
        math_div_y.operation = 'DIVIDE'
        math_div_y.inputs[1].default_value = 1.8
        links.new(math_step_y.outputs[0], math_div_y.inputs[0])

        # スイッチノード (Viewport なら /4、Render なら そのまま)
        switch_res_x = nodes.new('GeometryNodeSwitch')
        try:
            switch_res_x.input_type = 'FLOAT'
        except AttributeError:
            pass # 3.x compatibility
        if node_is_viewport:
            links.new(node_is_viewport.outputs[0], switch_res_x.inputs[0])
        links.new(math_step_x.outputs[0], switch_res_x.inputs['False'])
        links.new(math_div_x.outputs[0], switch_res_x.inputs['True'])

        switch_res_y = nodes.new('GeometryNodeSwitch')
        try:
            switch_res_y.input_type = 'FLOAT'
        except AttributeError:
            pass
        if node_is_viewport:
            links.new(node_is_viewport.outputs[0], switch_res_y.inputs[0])
        links.new(math_step_y.outputs[0], switch_res_y.inputs['False'])
        links.new(math_div_y.outputs[0], switch_res_y.inputs['True'])

        # X方向の分割数計算: clamp(floor(Res) + 1, 2, 1500)
        math_floor_x = nodes.new('ShaderNodeMath')
        math_floor_x.operation = 'FLOOR'
        links.new(switch_res_x.outputs['Output'] if 'Output' in switch_res_x.outputs else switch_res_x.outputs[0], math_floor_x.inputs[0])
        
        math_add_x = nodes.new('ShaderNodeMath')
        math_add_x.operation = 'ADD'
        math_add_x.inputs[1].default_value = 1.0
        links.new(math_floor_x.outputs[0], math_add_x.inputs[0])
        
        math_max_x = nodes.new('ShaderNodeMath')
        math_max_x.operation = 'MAXIMUM'
        math_max_x.inputs[1].default_value = 2.0
        links.new(math_add_x.outputs[0], math_max_x.inputs[0])

        math_clamp_x = nodes.new('ShaderNodeMath')
        math_clamp_x.operation = 'MINIMUM'
        math_clamp_x.inputs[1].default_value = 1500.0
        links.new(math_max_x.outputs[0], math_clamp_x.inputs[0])
        
        links.new(math_clamp_x.outputs[0], node_grid.inputs['Vertices X'])

        # Y方向の分割数計算: clamp(floor(Res) + 1, 2, 1500)
        math_floor_y = nodes.new('ShaderNodeMath')
        math_floor_y.operation = 'FLOOR'
        links.new(switch_res_y.outputs['Output'] if 'Output' in switch_res_y.outputs else switch_res_y.outputs[0], math_floor_y.inputs[0])
        
        math_add_y = nodes.new('ShaderNodeMath')
        math_add_y.operation = 'ADD'
        math_add_y.inputs[1].default_value = 1.0
        links.new(math_floor_y.outputs[0], math_add_y.inputs[0])
        
        math_max_y = nodes.new('ShaderNodeMath')
        math_max_y.operation = 'MAXIMUM'
        math_max_y.inputs[1].default_value = 2.0
        links.new(math_add_y.outputs[0], math_max_y.inputs[0])

        math_clamp_y = nodes.new('ShaderNodeMath')
        math_clamp_y.operation = 'MINIMUM'
        math_clamp_y.inputs[1].default_value = 1500.0
        links.new(math_max_y.outputs[0], math_clamp_y.inputs[0])
        
        links.new(math_clamp_y.outputs[0], node_grid.inputs['Vertices Y'])

        # 1. Position ノード + Noise Offset (シードごとに異なる地形パターンを生成)
        node_pos = nodes.new('GeometryNodeInputPosition')
        node_pos.location = (-1450, -200)

        node_noise_pos = nodes.new('ShaderNodeVectorMath')
        node_noise_pos.operation = 'ADD'
        node_noise_pos.location = (-1300, -200)
        links.new(node_pos.outputs['Position'], node_noise_pos.inputs[0])
        links.new(node_in.outputs['Noise Offset'], node_noise_pos.inputs[1])

        # 2-A. 大域ノイズ (Macro): Scale = Noise Scale * 0.5, Detail = 4.0
        node_macro_scale = nodes.new('ShaderNodeMath')
        node_macro_scale.operation = 'MULTIPLY'
        node_macro_scale.inputs[1].default_value = 0.5
        node_macro_scale.location = (-1250, -180)
        links.new(node_in.outputs['Noise Scale'], node_macro_scale.inputs[0])

        try:
            node_noise = nodes.new('FunctionNodeNoiseTexture')
        except RuntimeError:
            node_noise = nodes.new('ShaderNodeTexNoise')
        node_noise.location = (-1100, -200)
        if 'Detail' in node_noise.inputs:
            node_noise.inputs['Detail'].default_value = 4.0
        if 'Roughness' in node_noise.inputs:
            node_noise.inputs['Roughness'].default_value = 0.5
        links.new(node_noise_pos.outputs['Vector'], node_noise.inputs['Vector'])
        links.new(node_macro_scale.outputs[0], node_noise.inputs['Scale'])

        # 2-B. 尾根ノイズ (Ridged Mountain): Scale = Noise Scale * 1.8, Detail = 8.0, Roughness = 0.6
        node_ridge_scale = nodes.new('ShaderNodeMath')
        node_ridge_scale.operation = 'MULTIPLY'
        node_ridge_scale.inputs[1].default_value = 1.8
        node_ridge_scale.location = (-1250, -320)
        links.new(node_in.outputs['Noise Scale'], node_ridge_scale.inputs[0])

        try:
            node_detail_noise = nodes.new('FunctionNodeNoiseTexture')
        except RuntimeError:
            node_detail_noise = nodes.new('ShaderNodeTexNoise')
        node_detail_noise.location = (-1100, -350)
        if 'Detail' in node_detail_noise.inputs:
            node_detail_noise.inputs['Detail'].default_value = 8.0
        if 'Roughness' in node_detail_noise.inputs:
            node_detail_noise.inputs['Roughness'].default_value = 0.6
        links.new(node_noise_pos.outputs['Vector'], node_detail_noise.inputs['Vector'])
        links.new(node_ridge_scale.outputs[0], node_detail_noise.inputs['Scale'])

        # Ridged Noise: power(1.0 - abs(2*n - 1), 1.7) -> 鋭い山稜と浸食谷 (0.0 ~ 1.0)
        detail_out = node_detail_noise.outputs['Factor'] if 'Factor' in node_detail_noise.outputs else node_detail_noise.outputs[0]
        node_det_mul2 = nodes.new('ShaderNodeMath')
        node_det_mul2.operation = 'MULTIPLY'
        node_det_mul2.inputs[1].default_value = 2.0
        node_det_mul2.location = (-950, -350)
        links.new(detail_out, node_det_mul2.inputs[0])

        node_det_sub = nodes.new('ShaderNodeMath')
        node_det_sub.operation = 'SUBTRACT'
        node_det_sub.inputs[1].default_value = 1.0
        node_det_sub.location = (-840, -350)
        links.new(node_det_mul2.outputs[0], node_det_sub.inputs[0])

        node_det_abs = nodes.new('ShaderNodeMath')
        node_det_abs.operation = 'ABSOLUTE'
        node_det_abs.location = (-730, -350)
        links.new(node_det_sub.outputs[0], node_det_abs.inputs[0])

        node_ridged_raw = nodes.new('ShaderNodeMath')
        node_ridged_raw.operation = 'SUBTRACT'
        node_ridged_raw.inputs[0].default_value = 1.0
        node_ridged_raw.location = (-620, -350)
        links.new(node_det_abs.outputs[0], node_ridged_raw.inputs[1])

        node_ridged = nodes.new('ShaderNodeMath')
        node_ridged.operation = 'POWER'
        node_ridged.use_clamp = True
        node_ridged.inputs[1].default_value = 1.7
        node_ridged.location = (-510, -350)
        links.new(node_ridged_raw.outputs[0], node_ridged.inputs[0])

        # 2-C. 微細ディテールノイズ (Micro Rock/Erosion): Scale = Noise Scale * 8.0, Detail = 10.0, Roughness = 0.65
        node_micro_scale = nodes.new('ShaderNodeMath')
        node_micro_scale.operation = 'MULTIPLY'
        node_micro_scale.inputs[1].default_value = 8.0
        node_micro_scale.location = (-1250, -480)
        links.new(node_in.outputs['Noise Scale'], node_micro_scale.inputs[0])

        try:
            node_micro_noise = nodes.new('FunctionNodeNoiseTexture')
        except RuntimeError:
            node_micro_noise = nodes.new('ShaderNodeTexNoise')
        node_micro_noise.location = (-1100, -480)
        if 'Detail' in node_micro_noise.inputs:
            node_micro_noise.inputs['Detail'].default_value = 10.0
        if 'Roughness' in node_micro_noise.inputs:
            node_micro_noise.inputs['Roughness'].default_value = 0.65
        links.new(node_noise_pos.outputs['Vector'], node_micro_noise.inputs['Vector'])
        links.new(node_micro_scale.outputs[0], node_micro_noise.inputs['Scale'])

        micro_out = node_micro_noise.outputs['Factor'] if 'Factor' in node_micro_noise.outputs else node_micro_noise.outputs[0]
        node_micro_sub = nodes.new('ShaderNodeMath')
        node_micro_sub.operation = 'SUBTRACT'
        node_micro_sub.inputs[1].default_value = 0.5
        node_micro_sub.location = (-900, -480)
        links.new(micro_out, node_micro_sub.inputs[0])

        # Micro * (0.12 + Detail Strength * 0.22)
        node_micro_str_mul = nodes.new('ShaderNodeMath')
        node_micro_str_mul.operation = 'MULTIPLY'
        node_micro_str_mul.inputs[1].default_value = 0.22
        node_micro_str_mul.location = (-900, -560)
        links.new(node_in.outputs['Detail Strength'], node_micro_str_mul.inputs[0])

        node_micro_str = nodes.new('ShaderNodeMath')
        node_micro_str.operation = 'ADD'
        node_micro_str.inputs[1].default_value = 0.12
        node_micro_str.location = (-780, -560)
        links.new(node_micro_str_mul.outputs[0], node_micro_str.inputs[0])

        node_micro_amp = nodes.new('ShaderNodeMath')
        node_micro_amp.operation = 'MULTIPLY'
        node_micro_amp.location = (-660, -480)
        links.new(node_micro_sub.outputs[0], node_micro_amp.inputs[0])
        links.new(node_micro_str.outputs[0], node_micro_amp.inputs[1])

        # 3. 3層合成: Macro(0.85) + Ridged(0.4 + Ridge Sharpness * 0.75) + Micro
        node_sub = nodes.new('ShaderNodeMath')
        node_sub.operation = 'SUBTRACT'
        node_sub.inputs[1].default_value = 0.5
        node_sub.location = (-900, -200)
        noise_out = node_noise.outputs['Factor'] if 'Factor' in node_noise.outputs else node_noise.outputs[0]
        links.new(noise_out, node_sub.inputs[0])

        node_macro_amp = nodes.new('ShaderNodeMath')
        node_macro_amp.operation = 'MULTIPLY'
        node_macro_amp.inputs[1].default_value = 0.85
        node_macro_amp.location = (-780, -200)
        links.new(node_sub.outputs[0], node_macro_amp.inputs[0])

        # (ridged - 0.30) * (0.35 + Ridge Sharpness * 0.65)
        node_rid_center = nodes.new('ShaderNodeMath')
        node_rid_center.operation = 'SUBTRACT'
        node_rid_center.inputs[1].default_value = 0.30
        node_rid_center.location = (-400, -350)
        links.new(node_ridged.outputs[0], node_rid_center.inputs[0])

        node_rid_w_mul = nodes.new('ShaderNodeMath')
        node_rid_w_mul.operation = 'MULTIPLY'
        node_rid_w_mul.inputs[1].default_value = 0.65
        node_rid_w_mul.location = (-400, -430)
        links.new(node_in.outputs['Ridge Sharpness'], node_rid_w_mul.inputs[0])

        node_rid_w = nodes.new('ShaderNodeMath')
        node_rid_w.operation = 'ADD'
        node_rid_w.inputs[1].default_value = 0.35
        node_rid_w.location = (-290, -430)
        links.new(node_rid_w_mul.outputs[0], node_rid_w.inputs[0])

        node_rid_amp = nodes.new('ShaderNodeMath')
        node_rid_amp.operation = 'MULTIPLY'
        node_rid_amp.location = (-240, -350)
        links.new(node_rid_center.outputs[0], node_rid_amp.inputs[0])
        links.new(node_rid_w.outputs[0], node_rid_amp.inputs[1])

        node_mac_rid = nodes.new('ShaderNodeMath')
        node_mac_rid.operation = 'ADD'
        node_mac_rid.location = (-660, -200)
        links.new(node_macro_amp.outputs[0], node_mac_rid.inputs[0])
        links.new(node_rid_amp.outputs[0], node_mac_rid.inputs[1])

        node_base_combined = nodes.new('ShaderNodeMath')
        node_base_combined.operation = 'ADD'
        node_base_combined.location = (-540, -200)
        links.new(node_mac_rid.outputs[0], node_base_combined.inputs[0])
        links.new(node_micro_amp.outputs[0], node_base_combined.inputs[1])

        # 4. Math: Multiply by Terrain Height
        node_mult = nodes.new('ShaderNodeMath')
        node_mult.operation = 'MULTIPLY'
        node_mult.location = (-420, -200)
        links.new(node_base_combined.outputs[0], node_mult.inputs[0])
        links.new(node_in.outputs['Terrain Height'], node_mult.inputs[1])

        # 4.5 都市エリア地盤整地（グレーディング）マスク
        # City Grade Radius > 0 の場合、街の中心周囲のベース起伏を緩やかに抑制する
        node_sep_pos_xy = nodes.new('ShaderNodeSeparateXYZ')
        node_sep_pos_xy.location = (-420, -640)
        links.new(node_pos.outputs['Position'], node_sep_pos_xy.inputs['Vector'])

        node_sep_city_xy = nodes.new('ShaderNodeSeparateXYZ')
        node_sep_city_xy.location = (-420, -760)
        links.new(node_in.outputs['City Center'], node_sep_city_xy.inputs['Vector'])

        node_comb_pos2d = nodes.new('ShaderNodeCombineXYZ')
        node_comb_pos2d.location = (-280, -640)
        links.new(node_sep_pos_xy.outputs['X'], node_comb_pos2d.inputs['X'])
        links.new(node_sep_pos_xy.outputs['Y'], node_comb_pos2d.inputs['Y'])

        node_comb_city2d = nodes.new('ShaderNodeCombineXYZ')
        node_comb_city2d.location = (-280, -760)
        links.new(node_sep_city_xy.outputs['X'], node_comb_city2d.inputs['X'])
        links.new(node_sep_city_xy.outputs['Y'], node_comb_city2d.inputs['Y'])

        node_city_dist = nodes.new('ShaderNodeVectorMath')
        node_city_dist.operation = 'DISTANCE'
        node_city_dist.location = (-140, -700)
        links.new(node_comb_pos2d.outputs['Vector'], node_city_dist.inputs[0])
        links.new(node_comb_city2d.outputs['Vector'], node_city_dist.inputs[1])

        node_city_r_min = nodes.new('ShaderNodeMath')
        node_city_r_min.operation = 'MULTIPLY'
        node_city_r_min.inputs[1].default_value = 0.55
        node_city_r_min.location = (-140, -820)
        links.new(node_in.outputs['City Grade Radius'], node_city_r_min.inputs[0])

        node_city_r_max = nodes.new('ShaderNodeMath')
        node_city_r_max.operation = 'MULTIPLY'
        node_city_r_max.inputs[1].default_value = 1.45
        node_city_r_max.location = (-140, -900)
        links.new(node_in.outputs['City Grade Radius'], node_city_r_max.inputs[0])

        node_city_map = nodes.new('ShaderNodeMapRange')
        node_city_map.interpolation_type = 'SMOOTHSTEP'
        node_city_map.inputs['To Min'].default_value = 0.15
        node_city_map.inputs['To Max'].default_value = 1.0
        node_city_map.location = (20, -750)
        links.new(node_city_dist.outputs['Value'], node_city_map.inputs['Value'])
        links.new(node_city_r_min.outputs[0], node_city_map.inputs['From Min'])
        links.new(node_city_r_max.outputs[0], node_city_map.inputs['From Max'])

        node_city_active = nodes.new('ShaderNodeMath')
        node_city_active.operation = 'GREATER_THAN'
        node_city_active.inputs[1].default_value = 1.0
        node_city_active.location = (20, -920)
        links.new(node_in.outputs['City Grade Radius'], node_city_active.inputs[0])

        node_city_switch = nodes.new('GeometryNodeSwitch')
        try:
            node_city_switch.input_type = 'FLOAT'
        except AttributeError:
            pass
        node_city_switch.location = (180, -780)
        links.new(node_city_active.outputs[0], node_city_switch.inputs['Switch'])
        node_city_switch.inputs['False'].default_value = 1.0
        links.new(node_city_map.outputs['Result'], node_city_switch.inputs['True'])

        node_base_graded = nodes.new('ShaderNodeMath')
        node_base_graded.operation = 'MULTIPLY'
        node_base_graded.location = (-280, -200)
        links.new(node_mult.outputs[0], node_base_graded.inputs[0])
        links.new(node_city_switch.outputs['Output'] if 'Output' in node_city_switch.outputs else node_city_switch.outputs[0], node_base_graded.inputs[1])


        # ==========================================
        # 1. Collection Info (山コレクション情報)
        node_mt_info = nodes.new('GeometryNodeCollectionInfo')
        node_mt_info.transform_space = 'RELATIVE'
        node_mt_info.location = (-1300, 600)
        node_mt_info.inputs['Separate Children'].default_value = True
        node_mt_info.inputs['Reset Children'].default_value = False
        links.new(node_in.outputs['Mountain Collection'], node_mt_info.inputs['Collection'])

        # Realize Instances
        node_mt_realize = nodes.new('GeometryNodeRealizeInstances')
        node_mt_realize.location = (-1150, 600)
        links.new(node_mt_info.outputs['Instances'], node_mt_realize.inputs['Geometry'])

        # 1.5. Curve to Mesh バイパス
        # (Sample Nearest / Sample Index による custom_radius・custom_tilt の不連続ボロノイサンプリングを廃止し、
        #  純粋なエッジ連続距離 GeometryNodeProximity + SMOOTHSTEP のみで構成して垂直断層を物理的にゼロにする)
        mt_geometry_processed = add_curve_to_mesh_bypass(node_mt_realize.outputs['Geometry'], -1000, 650)

        # 2. Geometry Proximity (山スプラインエッジへの連続距離: 空間内で常に C0 連続)
        node_mt_prox = nodes.new('GeometryNodeProximity')
        node_mt_prox.target_element = 'EDGES'
        node_mt_prox.location = (-600, 600)
        links.new(mt_geometry_processed, node_mt_prox.inputs['Target'])

        # 2.5. 距離フィールドへのノイズ変調 (Domain Warping: 階段状ジャギーの解消)
        try:
            node_warp_noise = nodes.new('FunctionNodeNoiseTexture')
        except RuntimeError:
            node_warp_noise = nodes.new('ShaderNodeTexNoise')
        if hasattr(node_warp_noise, 'noise_dimensions'):
            node_warp_noise.noise_dimensions = '3D'
        if 'Scale' in node_warp_noise.inputs:
            node_warp_noise.inputs['Scale'].default_value = 0.0012
        if 'Detail' in node_warp_noise.inputs:
            node_warp_noise.inputs['Detail'].default_value = 4.0
        node_warp_noise.location = (-780, 520)
        links.new(node_noise_pos.outputs['Vector'], node_warp_noise.inputs['Vector'])

        warp_noise_out = (
            node_warp_noise.outputs['Fac']
            if 'Fac' in node_warp_noise.outputs
            else (node_warp_noise.outputs['Factor'] if 'Factor' in node_warp_noise.outputs else node_warp_noise.outputs[0])
        )
        node_warp_mul = nodes.new('ShaderNodeMath')
        node_warp_mul.operation = 'MULTIPLY'
        node_warp_mul.inputs[1].default_value = 220.0
        node_warp_mul.location = (-620, 520)
        links.new(warp_noise_out, node_warp_mul.inputs[0])

        node_mt_dist_warp = nodes.new('ShaderNodeMath')
        node_mt_dist_warp.operation = 'ADD'
        node_mt_dist_warp.location = (-500, 600)
        links.new(node_mt_prox.outputs['Distance'], node_mt_dist_warp.inputs[0])
        links.new(node_warp_mul.outputs[0], node_mt_dist_warp.inputs[1])

        # 3. Map Range (純粋な連続距離を SMOOTHSTEP でウェイト 0.0 ~ 1.0 にマッピング)
        node_mt_map = nodes.new('ShaderNodeMapRange')
        node_mt_map.interpolation_type = 'SMOOTHSTEP'
        node_mt_map.inputs['From Min'].default_value = 0.0
        node_mt_map.inputs['To Min'].default_value = 1.0
        node_mt_map.inputs['To Max'].default_value = 0.0
        node_mt_map.location = (-400, 600)
        links.new(node_mt_dist_warp.outputs[0], node_mt_map.inputs['Value'])
        links.new(node_in.outputs['Mountain Radius'], node_mt_map.inputs['From Max'])

        # 4. 山のオブジェクト存在判定 (バイパス処理)
        try:
            node_mt_dom_mesh = nodes.new('GeometryNodeAttributeDomainSize')
        except RuntimeError:
            node_mt_dom_mesh = nodes.new('GeometryNodeDomainSize')
        node_mt_dom_mesh.component = 'MESH'
        node_mt_dom_mesh.location = (-1300, 900)
        links.new(node_mt_realize.outputs['Geometry'], node_mt_dom_mesh.inputs['Geometry'])

        try:
            node_mt_dom_curve = nodes.new('GeometryNodeAttributeDomainSize')
        except RuntimeError:
            node_mt_dom_curve = nodes.new('GeometryNodeDomainSize')
        node_mt_dom_curve.component = 'CURVE'
        node_mt_dom_curve.location = (-1300, 1050)
        links.new(node_mt_realize.outputs['Geometry'], node_mt_dom_curve.inputs['Geometry'])

        node_mt_sum = nodes.new('ShaderNodeMath')
        node_mt_sum.operation = 'ADD'
        node_mt_sum.location = (-1100, 950)
        mt_mesh_count = node_mt_dom_mesh.outputs['Point Count'] if 'Point Count' in node_mt_dom_mesh.outputs else node_mt_dom_mesh.outputs[0]
        mt_curve_count = node_mt_dom_curve.outputs['Point Count'] if 'Point Count' in node_mt_dom_curve.outputs else node_mt_dom_curve.outputs[0]
        links.new(mt_mesh_count, node_mt_sum.inputs[0])
        links.new(mt_curve_count, node_mt_sum.inputs[1])

        node_mt_exist = nodes.new('ShaderNodeMath')
        node_mt_exist.operation = 'GREATER_THAN'
        node_mt_exist.location = (-900, 950)
        links.new(node_mt_sum.outputs[0], node_mt_exist.inputs[0])
        node_mt_exist.inputs[1].default_value = 0.0

        # 山の合計隆起高さの算出 (clamp 等のステップ関数を使わず SMOOTHSTEP と連続乗算のみで構成)
        node_mt_exp_mul = nodes.new('ShaderNodeMath')
        node_mt_exp_mul.operation = 'MULTIPLY'
        node_mt_exp_mul.inputs[1].default_value = 0.75
        node_mt_exp_mul.location = (-380, 560)
        links.new(node_in.outputs['Ridge Sharpness'], node_mt_exp_mul.inputs[0])

        node_mt_exp = nodes.new('ShaderNodeMath')
        node_mt_exp.operation = 'ADD'
        node_mt_exp.inputs[1].default_value = 1.0
        node_mt_exp.location = (-280, 560)
        links.new(node_mt_exp_mul.outputs[0], node_mt_exp.inputs[0])

        node_mt_pow = nodes.new('ShaderNodeMath')
        node_mt_pow.operation = 'POWER'
        node_mt_pow.use_clamp = False
        node_mt_pow.location = (-180, 560)
        links.new(node_mt_map.outputs['Result'], node_mt_pow.inputs[0])
        links.new(node_mt_exp.outputs[0], node_mt_pow.inputs[1])

        # 山の尾根・浸食ガリーディテール: 1.0 + (ridged - 0.35) * Ridge Sharpness * 1.10
        node_mt_rid_sub = nodes.new('ShaderNodeMath')
        node_mt_rid_sub.operation = 'SUBTRACT'
        node_mt_rid_sub.inputs[1].default_value = 0.35
        node_mt_rid_sub.location = (-380, 680)
        links.new(node_ridged.outputs[0], node_mt_rid_sub.inputs[0])

        node_mt_rid_mul1 = nodes.new('ShaderNodeMath')
        node_mt_rid_mul1.operation = 'MULTIPLY'
        node_mt_rid_mul1.location = (-280, 680)
        links.new(node_mt_rid_sub.outputs[0], node_mt_rid_mul1.inputs[0])
        links.new(node_in.outputs['Ridge Sharpness'], node_mt_rid_mul1.inputs[1])

        node_mt_rid_mul2 = nodes.new('ShaderNodeMath')
        node_mt_rid_mul2.operation = 'MULTIPLY'
        node_mt_rid_mul2.inputs[1].default_value = 1.10
        node_mt_rid_mul2.location = (-180, 680)
        links.new(node_mt_rid_mul1.outputs[0], node_mt_rid_mul2.inputs[0])

        node_mt_rid_fac = nodes.new('ShaderNodeMath')
        node_mt_rid_fac.operation = 'ADD'
        node_mt_rid_fac.inputs[1].default_value = 1.0
        node_mt_rid_fac.location = (-80, 680)
        links.new(node_mt_rid_mul2.outputs[0], node_mt_rid_fac.inputs[0])

        node_mt_shaped = nodes.new('ShaderNodeMath')
        node_mt_shaped.operation = 'MULTIPLY'
        node_mt_shaped.location = (-80, 560)
        links.new(node_mt_pow.outputs[0], node_mt_shaped.inputs[0])
        links.new(node_mt_rid_fac.outputs[0], node_mt_shaped.inputs[1])

        # 山ごとの高さバリエーションは 3D 空間の連続ノイズ変調 (SMOOTHSTEP: 0.70 ~ 1.30) で表現
        try:
            node_mt_var_noise = nodes.new('FunctionNodeNoiseTexture')
        except RuntimeError:
            node_mt_var_noise = nodes.new('ShaderNodeTexNoise')
        if hasattr(node_mt_var_noise, 'noise_dimensions'):
            node_mt_var_noise.noise_dimensions = '3D'
        if 'Scale' in node_mt_var_noise.inputs:
            node_mt_var_noise.inputs['Scale'].default_value = 0.00018
        if 'Detail' in node_mt_var_noise.inputs:
            node_mt_var_noise.inputs['Detail'].default_value = 2.0
        node_mt_var_noise.location = (-520, 440)
        links.new(node_noise_pos.outputs['Vector'], node_mt_var_noise.inputs['Vector'])

        mt_var_out = (
            node_mt_var_noise.outputs['Fac']
            if 'Fac' in node_mt_var_noise.outputs
            else (node_mt_var_noise.outputs['Factor'] if 'Factor' in node_mt_var_noise.outputs else node_mt_var_noise.outputs[0])
        )
        node_mt_var_map = nodes.new('ShaderNodeMapRange')
        node_mt_var_map.interpolation_type = 'SMOOTHSTEP'
        node_mt_var_map.inputs['From Min'].default_value = 0.0
        node_mt_var_map.inputs['From Max'].default_value = 1.0
        node_mt_var_map.inputs['To Min'].default_value = 0.70
        node_mt_var_map.inputs['To Max'].default_value = 1.30
        node_mt_var_map.location = (-360, 440)
        links.new(mt_var_out, node_mt_var_map.inputs['Value'])

        node_mt_height_mult = nodes.new('ShaderNodeMath')
        node_mt_height_mult.operation = 'MULTIPLY'
        node_mt_height_mult.location = (-200, 450)
        links.new(node_in.outputs['Mountain Height'], node_mt_height_mult.inputs[0])
        links.new(node_mt_var_map.outputs['Result'], node_mt_height_mult.inputs[1])

        node_mt_mult1 = nodes.new('ShaderNodeMath')
        node_mt_mult1.operation = 'MULTIPLY'
        node_mt_mult1.location = (-200, 600)
        links.new(node_mt_shaped.outputs[0], node_mt_mult1.inputs[0])
        links.new(node_mt_height_mult.outputs[0], node_mt_mult1.inputs[1])

        node_mt_height_final = nodes.new('ShaderNodeMath')
        node_mt_height_final.operation = 'MULTIPLY'
        node_mt_height_final.location = (-50, 600)
        links.new(node_mt_mult1.outputs[0], node_mt_height_final.inputs[0])
        mt_exist_out = node_mt_exist.outputs['Result'] if 'Result' in node_mt_exist.outputs else node_mt_exist.outputs[0]
        links.new(mt_exist_out, node_mt_height_final.inputs[1])


        # ==========================================
        # (C) スプライン谷 (Valley Object)
        # ==========================================
        # 1. Collection Info (谷コレクション情報)
        node_vl_info = nodes.new('GeometryNodeCollectionInfo')
        node_vl_info.transform_space = 'RELATIVE'
        node_vl_info.location = (-1300, -400)
        node_vl_info.inputs['Separate Children'].default_value = True
        node_vl_info.inputs['Reset Children'].default_value = False
        links.new(node_in.outputs['Valley Collection'], node_vl_info.inputs['Collection'])

        # Realize Instances
        node_vl_realize = nodes.new('GeometryNodeRealizeInstances')
        node_vl_realize.location = (-1150, -400)
        links.new(node_vl_info.outputs['Instances'], node_vl_realize.inputs['Geometry'])

        # 1.5. Curve to Mesh バイパス (Sample Nearest による不連続サンプリングを廃止)
        vl_geometry_processed = add_curve_to_mesh_bypass(node_vl_realize.outputs['Geometry'], -1000, -350)

        # 2. Geometry Proximity (谷スプラインエッジへの連続距離)
        node_vl_prox = nodes.new('GeometryNodeProximity')
        node_vl_prox.target_element = 'EDGES'
        node_vl_prox.location = (-600, -400)
        links.new(vl_geometry_processed, node_vl_prox.inputs['Target'])

        # 2.5. 谷の距離フィールドへのノイズ変調 (Domain Warping: 階段状ジャギーの解消)
        node_vl_dist_warp = nodes.new('ShaderNodeMath')
        node_vl_dist_warp.operation = 'ADD'
        node_vl_dist_warp.location = (-500, -400)
        links.new(node_vl_prox.outputs['Distance'], node_vl_dist_warp.inputs[0])
        links.new(node_warp_mul.outputs[0], node_vl_dist_warp.inputs[1])

        # 3. Map Range (純粋な連続距離を SMOOTHSTEP でウェイトにマッピング)
        node_vl_map = nodes.new('ShaderNodeMapRange')
        node_vl_map.interpolation_type = 'SMOOTHSTEP'
        node_vl_map.inputs['From Min'].default_value = 0.0
        node_vl_map.inputs['To Min'].default_value = 1.0
        node_vl_map.inputs['To Max'].default_value = 0.0
        node_vl_map.location = (-400, -400)
        links.new(node_vl_dist_warp.outputs[0], node_vl_map.inputs['Value'])
        links.new(node_in.outputs['Valley Radius'], node_vl_map.inputs['From Max'])

        # 4. 谷のオブジェクト存在判定 (バイパス処理)
        try:
            node_vl_dom_mesh = nodes.new('GeometryNodeAttributeDomainSize')
        except RuntimeError:
            node_vl_dom_mesh = nodes.new('GeometryNodeDomainSize')
        node_vl_dom_mesh.component = 'MESH'
        node_vl_dom_mesh.location = (-1300, -600)
        links.new(node_vl_realize.outputs['Geometry'], node_vl_dom_mesh.inputs['Geometry'])

        try:
            node_vl_dom_curve = nodes.new('GeometryNodeAttributeDomainSize')
        except RuntimeError:
            node_vl_dom_curve = nodes.new('GeometryNodeDomainSize')
        node_vl_dom_curve.component = 'CURVE'
        node_vl_dom_curve.location = (-1300, -750)
        links.new(node_vl_realize.outputs['Geometry'], node_vl_dom_curve.inputs['Geometry'])

        node_vl_sum = nodes.new('ShaderNodeMath')
        node_vl_sum.operation = 'ADD'
        node_vl_sum.location = (-1100, -650)
        vl_mesh_count = node_vl_dom_mesh.outputs['Point Count'] if 'Point Count' in node_vl_dom_mesh.outputs else node_vl_dom_mesh.outputs[0]
        vl_curve_count = node_vl_dom_curve.outputs['Point Count'] if 'Point Count' in node_vl_dom_curve.outputs else node_vl_dom_curve.outputs[0]
        links.new(vl_mesh_count, node_vl_sum.inputs[0])
        links.new(vl_curve_count, node_vl_sum.inputs[1])

        node_vl_exist = nodes.new('ShaderNodeMath')
        node_vl_exist.operation = 'GREATER_THAN'
        node_vl_exist.location = (-900, -650)
        links.new(node_vl_sum.outputs[0], node_vl_exist.inputs[0])
        node_vl_exist.inputs[1].default_value = 0.0

        # 谷の合計沈下量の算出 (SMOOTHSTEP と連続乗算のみで構成)
        node_vl_exp_mul = nodes.new('ShaderNodeMath')
        node_vl_exp_mul.operation = 'MULTIPLY'
        node_vl_exp_mul.inputs[1].default_value = 0.65
        node_vl_exp_mul.location = (-380, -450)
        links.new(node_in.outputs['Ridge Sharpness'], node_vl_exp_mul.inputs[0])

        node_vl_exp = nodes.new('ShaderNodeMath')
        node_vl_exp.operation = 'ADD'
        node_vl_exp.inputs[1].default_value = 1.0
        node_vl_exp.location = (-280, -450)
        links.new(node_vl_exp_mul.outputs[0], node_vl_exp.inputs[0])

        node_vl_pow = nodes.new('ShaderNodeMath')
        node_vl_pow.operation = 'POWER'
        node_vl_pow.use_clamp = False
        node_vl_pow.location = (-180, -450)
        links.new(node_vl_map.outputs['Result'], node_vl_pow.inputs[0])
        links.new(node_vl_exp.outputs[0], node_vl_pow.inputs[1])

        # 谷壁の岩肌変調: 1.0 + (ridged - 0.45) * Detail Strength * 0.5
        node_vl_rid_sub = nodes.new('ShaderNodeMath')
        node_vl_rid_sub.operation = 'SUBTRACT'
        node_vl_rid_sub.inputs[1].default_value = 0.45
        node_vl_rid_sub.location = (-380, -350)
        links.new(node_ridged.outputs[0], node_vl_rid_sub.inputs[0])

        node_vl_rid_mul1 = nodes.new('ShaderNodeMath')
        node_vl_rid_mul1.operation = 'MULTIPLY'
        node_vl_rid_mul1.location = (-280, -350)
        links.new(node_vl_rid_sub.outputs[0], node_vl_rid_mul1.inputs[0])
        links.new(node_in.outputs['Detail Strength'], node_vl_rid_mul1.inputs[1])

        node_vl_rid_mul2 = nodes.new('ShaderNodeMath')
        node_vl_rid_mul2.operation = 'MULTIPLY'
        node_vl_rid_mul2.inputs[1].default_value = 0.5
        node_vl_rid_mul2.location = (-180, -350)
        links.new(node_vl_rid_mul1.outputs[0], node_vl_rid_mul2.inputs[0])

        node_vl_rid_fac = nodes.new('ShaderNodeMath')
        node_vl_rid_fac.operation = 'ADD'
        node_vl_rid_fac.inputs[1].default_value = 1.0
        node_vl_rid_fac.location = (-80, -350)
        links.new(node_vl_rid_mul2.outputs[0], node_vl_rid_fac.inputs[0])

        node_vl_shaped = nodes.new('ShaderNodeMath')
        node_vl_shaped.operation = 'MULTIPLY'
        node_vl_shaped.location = (-80, -450)
        links.new(node_vl_pow.outputs[0], node_vl_shaped.inputs[0])
        links.new(node_vl_rid_fac.outputs[0], node_vl_shaped.inputs[1])

        # 谷の深さバリエーションも 3D 空間の連続ノイズ変調 (SMOOTHSTEP: 0.75 ~ 1.25) で表現
        node_vl_var_map = nodes.new('ShaderNodeMapRange')
        node_vl_var_map.interpolation_type = 'SMOOTHSTEP'
        node_vl_var_map.inputs['From Min'].default_value = 0.0
        node_vl_var_map.inputs['From Max'].default_value = 1.0
        node_vl_var_map.inputs['To Min'].default_value = 0.75
        node_vl_var_map.inputs['To Max'].default_value = 1.25
        node_vl_var_map.location = (-360, -550)
        links.new(mt_var_out, node_vl_var_map.inputs['Value'])

        node_vl_depth_mult = nodes.new('ShaderNodeMath')
        node_vl_depth_mult.operation = 'MULTIPLY'
        node_vl_depth_mult.location = (-200, -550)
        links.new(node_in.outputs['Valley Depth'], node_vl_depth_mult.inputs[0])
        links.new(node_vl_var_map.outputs['Result'], node_vl_depth_mult.inputs[1])

        node_vl_mult1 = nodes.new('ShaderNodeMath')
        node_vl_mult1.operation = 'MULTIPLY'
        node_vl_mult1.location = (-200, -400)
        links.new(node_vl_shaped.outputs[0], node_vl_mult1.inputs[0])
        links.new(node_vl_depth_mult.outputs[0], node_vl_mult1.inputs[1])

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
        links.new(node_base_graded.outputs[0], node_add_mt.inputs[0])
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

        # Realize Instances
        node_road_realize = nodes.new('GeometryNodeRealizeInstances')
        node_road_realize.location = (200, 400)
        links.new(node_road_info.outputs['Geometry'], node_road_realize.inputs['Geometry'])

        # 1.5. Curve to Mesh バイパス
        road_geometry_processed = add_curve_to_mesh_bypass(node_road_realize.outputs['Geometry'], 350, 450)

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
        node_map_range.interpolation_type = 'SMOOTHSTEP'
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

        # 5.5. トンネル区間内では Flat Radius 平坦化を無効化（山の上の表面を維持）
        node_tun_col_info = nodes.new('GeometryNodeCollectionInfo')
        node_tun_col_info.transform_space = 'RELATIVE'
        node_tun_col_info.location = (500, 820)
        links.new(node_in.outputs['Tunnel Cutters'], node_tun_col_info.inputs['Collection'])

        node_tun_realize = nodes.new('GeometryNodeRealizeInstances')
        node_tun_realize.location = (650, 820)
        links.new(node_tun_col_info.outputs['Instances'], node_tun_realize.inputs['Geometry'])

        try:
            node_tun_dom = nodes.new('GeometryNodeAttributeDomainSize')
        except RuntimeError:
            node_tun_dom = nodes.new('GeometryNodeDomainSize')
        node_tun_dom.component = 'MESH'
        node_tun_dom.location = (800, 920)
        links.new(node_tun_realize.outputs['Geometry'], node_tun_dom.inputs['Geometry'])

        node_tun_exist = nodes.new('ShaderNodeMath')
        node_tun_exist.operation = 'GREATER_THAN'
        node_tun_exist.inputs[1].default_value = 0.0
        node_tun_exist.location = (950, 920)
        tun_pt_out = node_tun_dom.outputs['Point Count'] if 'Point Count' in node_tun_dom.outputs else node_tun_dom.outputs[0]
        links.new(tun_pt_out, node_tun_exist.inputs[0])

        node_tun_prox = nodes.new('GeometryNodeProximity')
        node_tun_prox.target_element = 'FACES'
        node_tun_prox.location = (800, 800)
        links.new(node_tun_realize.outputs['Geometry'], node_tun_prox.inputs['Target'])

        node_tun_mask = nodes.new('ShaderNodeMapRange')
        node_tun_mask.interpolation_type = 'SMOOTHSTEP'
        node_tun_mask.inputs['From Min'].default_value = 32.0
        node_tun_mask.inputs['From Max'].default_value = 75.0
        node_tun_mask.inputs['To Min'].default_value = 0.0
        node_tun_mask.inputs['To Max'].default_value = 1.0
        node_tun_mask.location = (950, 800)
        links.new(node_tun_prox.outputs['Distance'], node_tun_mask.inputs['Value'])

        # トンネルが無い場合は 1.0、ある場合は node_tun_mask（Blender全バージョン互換の Math 構成）
        node_tun_inv = nodes.new('ShaderNodeMath')
        node_tun_inv.operation = 'SUBTRACT'
        node_tun_inv.inputs[0].default_value = 1.0
        node_tun_inv.location = (1050, 920)
        links.new(node_tun_exist.outputs[0], node_tun_inv.inputs[1])

        node_tun_mix = nodes.new('ShaderNodeMath')
        node_tun_mix.operation = 'MAXIMUM'
        node_tun_mix.location = (1100, 820)
        links.new(node_tun_inv.outputs[0], node_tun_mix.inputs[0])
        links.new(node_tun_mask.outputs['Result'], node_tun_mix.inputs[1])

        node_flat_masked = nodes.new('ShaderNodeMath')
        node_flat_masked.operation = 'MULTIPLY'
        node_flat_masked.location = (1150, 620)
        links.new(node_map_range.outputs['Result'], node_flat_masked.inputs[0])
        links.new(node_tun_mix.outputs[0], node_flat_masked.inputs[1])

        # 6. 線形補間(Lerp)の計算 (Mix Float ノードの互換性対策)
        # Z-fightingおよび道路が埋まるのを防ぐため、道路より地形を1.2m下げる
        node_offset_z = nodes.new('ShaderNodeMath')
        node_offset_z.operation = 'SUBTRACT'
        node_offset_z.location = (1000, 400)
        links.new(node_sep_prox.outputs['Z'], node_offset_z.inputs[0])
        node_offset_z.inputs[1].default_value = 1.2

        # MixZ = CurrZ + ((ProxZ - 0.1) - CurrZ) * Factor
        # (A) (ProxZ - 0.1) - CurrZ
        node_diff = nodes.new('ShaderNodeMath')
        node_diff.operation = 'SUBTRACT'
        node_diff.location = (1150, 400)
        links.new(node_offset_z.outputs[0], node_diff.inputs[0])
        links.new(node_sep_curr.outputs['Z'], node_diff.inputs[1])

        # (B) (ProxZ - CurrZ) * Factor
        node_mult_factor = nodes.new('ShaderNodeMath')
        node_mult_factor.operation = 'MULTIPLY'
        node_mult_factor.location = (1250, 400)
        links.new(node_diff.outputs[0], node_mult_factor.inputs[0])
        links.new(node_flat_masked.outputs[0], node_mult_factor.inputs[1])

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
        links.new(node_road_realize.outputs['Geometry'], node_dom.inputs['Geometry'])

        try:
            node_dom_curve = nodes.new('GeometryNodeAttributeDomainSize')
        except RuntimeError:
            node_dom_curve = nodes.new('GeometryNodeDomainSize')
        node_dom_curve.component = 'CURVE'
        node_dom_curve.location = (1250, 750)
        links.new(node_road_realize.outputs['Geometry'], node_dom_curve.inputs['Geometry'])

        node_dom_sum = nodes.new('ShaderNodeMath')
        node_dom_sum.operation = 'ADD'
        node_dom_sum.location = (1450, 670)
        mesh_count_out = node_dom.outputs['Point Count'] if 'Point Count' in node_dom.outputs else node_dom.outputs[0]
        curve_count_out = node_dom_curve.outputs['Point Count'] if 'Point Count' in node_dom_curve.outputs else node_dom_curve.outputs[0]
        links.new(mesh_count_out, node_dom_sum.inputs[0])
        links.new(curve_count_out, node_dom_sum.inputs[1])

        node_comp_exist = nodes.new('ShaderNodeMath')
        node_comp_exist.operation = 'GREATER_THAN'
        node_comp_exist.location = (1600, 670)
        links.new(node_dom_sum.outputs[0], node_comp_exist.inputs[0])
        node_comp_exist.inputs[1].default_value = 0.0

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
        # (E) トンネル坑口の穴あけ (Delete Geometry: FACE ドメイン)
        # ==========================================
        # 厚みゼロの平面グリッドで破綻する Mesh Boolean を廃止し、
        # TunnelCutters との距離が 32.0m 未満の FACE を Delete Geometry で確実に削除する
        node_tun_del_lt = nodes.new('ShaderNodeMath')
        node_tun_del_lt.operation = 'LESS_THAN'
        node_tun_del_lt.inputs[1].default_value = 32.0
        node_tun_del_lt.location = (1350, -100)
        links.new(node_tun_prox.outputs['Distance'], node_tun_del_lt.inputs[0])

        node_tun_del_sel = nodes.new('ShaderNodeMath')
        node_tun_del_sel.operation = 'MULTIPLY'
        node_tun_del_sel.location = (1480, -100)
        links.new(node_tun_del_lt.outputs[0], node_tun_del_sel.inputs[0])
        links.new(node_tun_exist.outputs[0], node_tun_del_sel.inputs[1])

        node_del_geo = nodes.new('GeometryNodeDeleteGeometry')
        node_del_geo.domain = 'FACE'
        node_del_geo.mode = 'ALL'
        node_del_geo.location = (1600, -100)
        links.new(node_set_flat.outputs['Geometry'], node_del_geo.inputs['Geometry'])
        links.new(node_tun_del_sel.outputs[0], node_del_geo.inputs['Selection'])

        # スムースシェーディングの適用（カクカクしたローポリ表示を解消）
        node_shade_smooth = nodes.new('GeometryNodeSetShadeSmooth')
        node_shade_smooth.location = (1680, -100)
        if 'Shade Smooth' in node_shade_smooth.inputs:
            node_shade_smooth.inputs['Shade Smooth'].default_value = True
        links.new(node_del_geo.outputs['Geometry'], node_shade_smooth.inputs['Geometry'])

        # 出力を最終的なGeometryに接続 (Set Material ノードを通してマテリアルを確実に反映)
        node_set_mat = nodes.new('GeometryNodeSetMaterial')
        node_set_mat.location = (1850, -100)
        links.new(node_shade_smooth.outputs['Geometry'], node_set_mat.inputs['Geometry'])
        links.new(node_set_mat.outputs['Geometry'], node_out.inputs['Geometry'])


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
        node_comp_slope = nodes.new('ShaderNodeMath')
        node_comp_slope.operation = 'GREATER_THAN'
        node_comp_slope.location = (1500, -350)
        links.new(node_sep_normal.outputs['Z'], node_comp_slope.inputs[0])
        node_comp_slope.inputs[1].default_value = 0.899

        # 4. 道路からの距離判定 (2.5 <= Distance <= 12.0)
        node_comp_dist_min = nodes.new('ShaderNodeMath')
        node_comp_dist_min.operation = 'GREATER_THAN'
        node_comp_dist_min.location = (1330, -550)
        links.new(node_proximity.outputs['Distance'], node_comp_dist_min.inputs[0])
        node_comp_dist_min.inputs[1].default_value = 2.499

        node_comp_dist_max = nodes.new('ShaderNodeMath')
        node_comp_dist_max.operation = 'LESS_THAN'
        node_comp_dist_max.location = (1500, -550)
        links.new(node_proximity.outputs['Distance'], node_comp_dist_max.inputs[0])
        node_comp_dist_max.inputs[1].default_value = 12.001

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

        # 全てのノードとリンクの構築が完了した後にノードグループを割り当てる
        # （これにより依存関係が正常にアップデートされ、オブジェクトアサイン等も正常に機能します）
        gn_mod.node_group = group

        # モディファイア入力値にプリセット値および既存コレクションを明示的に反映
        def set_gn_input(m, grp, name, val):
            if val is None or m is None:
                return False
            # 1. Blender 5.x+: m.properties.inputs[identifier].value = val
            if hasattr(m, 'properties') and hasattr(m.properties, 'inputs'):
                inputs_obj = m.properties.inputs
                if grp and hasattr(grp, "interface"):
                    for item in grp.interface.items_tree:
                        if getattr(item, 'item_type', '') == 'SOCKET' and item.in_out == 'INPUT' and item.name == name:
                            ident = getattr(item, 'identifier', '')
                            if ident and hasattr(inputs_obj, ident):
                                try:
                                    sock = getattr(inputs_obj, ident)
                                    if hasattr(sock, 'value'):
                                        sock.value = val
                                        return True
                                except Exception:
                                    pass
            # 2. Blender 4.x / 3.x: m[identifier] = val
            if grp and hasattr(grp, "interface"):
                for item in grp.interface.items_tree:
                    if getattr(item, 'item_type', '') == 'SOCKET' and item.in_out == 'INPUT' and item.name == name:
                        try:
                            m[item.identifier] = val
                            return True
                        except Exception:
                            pass
            elif grp and hasattr(grp, "inputs"):
                for item in grp.inputs:
                    if item.name == name:
                        try:
                            m[item.identifier] = val
                            return True
                        except Exception:
                            pass
            # 3. Fallback
            try:
                m[name] = val
                return True
            except Exception:
                pass
            return False

        default_ridge = 0.25 if self.preset == 'FLAT' else (0.75 if self.preset == 'MOUNTAINS' else 0.45)
        default_detail = 0.20 if self.preset == 'FLAT' else (0.50 if self.preset == 'MOUNTAINS' else 0.35)
        set_gn_input(gn_mod, group, 'Terrain Height', preset_height)
        set_gn_input(gn_mod, group, 'Noise Scale', preset_noise)
        set_gn_input(gn_mod, group, 'Ridge Sharpness', default_ridge)
        set_gn_input(gn_mod, group, 'Detail Strength', default_detail)
        set_gn_input(gn_mod, group, 'Grid Size X', target_size)
        set_gn_input(gn_mod, group, 'Grid Size Y', target_size)
        set_gn_input(gn_mod, group, 'Mountain Height', mt_height)
        set_gn_input(gn_mod, group, 'Mountain Radius', mt_radius)
        set_gn_input(gn_mod, group, 'Valley Depth', val_depth)
        set_gn_input(gn_mod, group, 'Valley Radius', val_radius)
        set_gn_input(gn_mod, group, 'Flat Radius', 65.0)
        set_gn_input(gn_mod, group, 'Flat Blend', 180.0)
        
        # 既存コレクション・オブジェクトの自動アサイン
        val_col = bpy.data.collections.get("Valleys")
        mt_col = bpy.data.collections.get("Mountains")
        road_obj = bpy.data.objects.get("RoadPath_AI") or bpy.data.objects.get("RoadPath")
        
        if val_col:
            set_gn_input(gn_mod, group, 'Valley Collection', val_col)
        if mt_col:
            set_gn_input(gn_mod, group, 'Mountain Collection', mt_col)
        if road_obj:
            set_gn_input(gn_mod, group, 'Road Object', road_obj)

        # バイオームマテリアルの自動適用
        try:
            from .terrain_materials import apply_biome_material_to_terrain
            apply_biome_material_to_terrain(terrain_obj, biome=self.biome)
        except Exception as e:
            print(f"マテリアル適用エラー: {e}")

        # 3Dビューポートのクリップ距離をスケールに合わせて拡張 (奥が消えないように)
        try:
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.clip_end = max(space.clip_end, 80000.0)
        except:
            pass

        print(f"ジオメトリノード地形生成システムが構築されました ({target_size/1000.0:.0f}kmスケール)。")
        return {'FINISHED'}


# オペレータ スプライン山脈生成
class MYADDON_OT_create_mountain_along_spline(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_create_mountain_along_spline"
    bl_label = "スプライン山脈生成"
    bl_description = "山脈の起伏を生成するためのスプライン曲線を生成し、地形にアサインします"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 0. 山脈コレクションを取得、または新規作成してシーンに登録
        mountain_col = bpy.data.collections.get("Mountains")
        if not mountain_col:
            mountain_col = bpy.data.collections.new("Mountains")
            context.scene.collection.children.link(mountain_col)

        # 1. 山脈用のスプライン(POLY)を作成
        curve_data = bpy.data.curves.new("MountainPath", 'CURVE')
        curve_data.dimensions = '3D'
        curve_data.twist_mode = 'Z_UP'

        spline = curve_data.splines.new('BEZIER')
        spline.bezier_points.add(1)  # デフォルトで1点あるので、計2点にする
        spline.bezier_points[0].co = (-20.0, 20.0, 0.0)
        spline.bezier_points[0].handle_left_type = 'AUTO'
        spline.bezier_points[0].handle_right_type = 'AUTO'
        spline.bezier_points[1].co = (20.0, 20.0, 0.0)
        spline.bezier_points[1].handle_left_type = 'AUTO'
        spline.bezier_points[1].handle_right_type = 'AUTO'

        curve_obj = bpy.data.objects.new("MountainPath", curve_data)
        mountain_col.objects.link(curve_obj)

        # アクティブを新しく作ったカーブにして、編集しやすくする
        context.view_layer.objects.active = curve_obj
        curve_obj.select_set(True)

        print("スプライン山脈を生成し、コレクション「Mountains」に追加しました。")
        return {'FINISHED'}


# オペレータ スプライン谷生成
class MYADDON_OT_create_valley_along_spline(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_create_valley_along_spline"
    bl_label = "スプライン谷生成"
    bl_description = "谷の起伏を生成するためのスプライン曲線を生成し、地形にアサインします"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 0. 谷コレクションを取得、または新規作成してシーンに登録
        valley_col = bpy.data.collections.get("Valleys")
        if not valley_col:
            valley_col = bpy.data.collections.new("Valleys")
            context.scene.collection.children.link(valley_col)

        # 1. 谷用のスプライン(POLY)を作成
        curve_data = bpy.data.curves.new("ValleyPath", 'CURVE')
        curve_data.dimensions = '3D'
        curve_data.twist_mode = 'Z_UP'

        spline = curve_data.splines.new('BEZIER')
        spline.bezier_points.add(1)  # デフォルトで1点あるので、計2点にする
        spline.bezier_points[0].co = (-20.0, -20.0, 0.0)
        spline.bezier_points[0].handle_left_type = 'AUTO'
        spline.bezier_points[0].handle_right_type = 'AUTO'
        spline.bezier_points[1].co = (20.0, -20.0, 0.0)
        spline.bezier_points[1].handle_left_type = 'AUTO'
        spline.bezier_points[1].handle_right_type = 'AUTO'

        curve_obj = bpy.data.objects.new("ValleyPath", curve_data)
        valley_col.objects.link(curve_obj)

        # アクティブを新しく作ったカーブにして、編集しやすくする
        context.view_layer.objects.active = curve_obj
        curve_obj.select_set(True)

        print("スプライン谷を生成し、コレクション「Valleys」に追加しました。")
        return {'FINISHED'}

