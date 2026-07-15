# -*- coding: utf-8 -*-
import bpy  # type: ignore
import math

class MYADDON_OT_create_building(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_create_building"
    bl_label = "建物生成"
    bl_description = "ジオメトリノードを使用して一般住宅、高層ビル、雑居ビル、タワーなどの建物を生成します"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 1. デフォルトマテリアルの用意 (Wall, Window, Roof)
        self.get_or_create_material("Wall", (0.5, 0.5, 0.5, 1.0))
        self.get_or_create_material("Window", (0.2, 0.6, 0.8, 1.0), roughness=0.1, metallic=0.9)
        self.get_or_create_material("Roof", (0.6, 0.2, 0.1, 1.0))

        # 2. 空のメッシュオブジェクトを作成
        mesh_data = bpy.data.meshes.new("BuildingMesh")
        building_obj = bpy.data.objects.new("Building", mesh_data)
        context.collection.objects.link(building_obj)
        context.view_layer.objects.active = building_obj
        building_obj.select_set(True)

        # 3. Geometry Nodes モディファイアの追加
        gn_mod = building_obj.modifiers.new(name="BuildingGen", type='NODES')

        # 4. セクション生成用のカスタムノードグループの作成 (階層の簡略化のため)
        section_group = self.get_or_create_section_group()

        # 5. メインの Geometry Nodes ツリーの作成
        group = bpy.data.node_groups.new("BuildingGenTree", 'GeometryNodeTree')

        nodes = group.nodes
        links = group.links

        # 6. 入出力インターフェースの定義 (Blender 4.0+ と 3.x 互換)
        if hasattr(group, "interface"):
            group.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
            
            # パラメータ定義
            type_socket = group.interface.new_socket('Building Type', in_out='INPUT', socket_type='NodeSocketInt')
            type_socket.default_value = 1  # デフォルト: 高層ビル
            type_socket.min_value = 0
            type_socket.max_value = 3

            floors_socket = group.interface.new_socket('Floors', in_out='INPUT', socket_type='NodeSocketInt')
            floors_socket.default_value = 6
            floors_socket.min_value = 1
            floors_socket.max_value = 100

            w_socket = group.interface.new_socket('Width', in_out='INPUT', socket_type='NodeSocketFloat')
            w_socket.default_value = 5.0
            w_socket.min_value = 1.0

            d_socket = group.interface.new_socket('Depth', in_out='INPUT', socket_type='NodeSocketFloat')
            d_socket.default_value = 5.0
            d_socket.min_value = 1.0

            fh_socket = group.interface.new_socket('Floor Height', in_out='INPUT', socket_type='NodeSocketFloat')
            fh_socket.default_value = 3.0
            fh_socket.min_value = 1.0

            wx_socket = group.interface.new_socket('Window Grid X', in_out='INPUT', socket_type='NodeSocketInt')
            wx_socket.default_value = 4
            wx_socket.min_value = 1

            wy_socket = group.interface.new_socket('Window Grid Y', in_out='INPUT', socket_type='NodeSocketInt')
            wy_socket.default_value = 1
            wy_socket.min_value = 1

            roof_socket = group.interface.new_socket('Roof Style', in_out='INPUT', socket_type='NodeSocketInt')
            roof_socket.default_value = 0  # 0=切妻, 1=寄棟, 2=フラット
            roof_socket.min_value = 0
            roof_socket.max_value = 2

            sb_f_socket = group.interface.new_socket('Setback Floors', in_out='INPUT', socket_type='NodeSocketInt')
            sb_f_socket.default_value = 4
            sb_f_socket.min_value = 1

            sb_s_socket = group.interface.new_socket('Setback Scale', in_out='INPUT', socket_type='NodeSocketFloat')
            sb_s_socket.default_value = 0.75
            sb_s_socket.min_value = 0.1
            sb_s_socket.max_value = 1.0

            # 出力
            group.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
        else:
            group.inputs.new('NodeSocketGeometry', 'Geometry')
            group.inputs.new('NodeSocketInt', 'Building Type').default_value = 1
            group.inputs.new('NodeSocketInt', 'Floors').default_value = 6
            group.inputs.new('NodeSocketFloat', 'Width').default_value = 5.0
            group.inputs.new('NodeSocketFloat', 'Depth').default_value = 5.0
            group.inputs.new('NodeSocketFloat', 'Floor Height').default_value = 3.0
            group.inputs.new('NodeSocketInt', 'Window Grid X').default_value = 4
            group.inputs.new('NodeSocketInt', 'Window Grid Y').default_value = 1
            group.inputs.new('NodeSocketInt', 'Roof Style').default_value = 0
            group.inputs.new('NodeSocketInt', 'Setback Floors').default_value = 4
            group.inputs.new('NodeSocketFloat', 'Setback Scale').default_value = 0.75
            group.outputs.new('NodeSocketGeometry', 'Geometry')

        node_in = nodes.new('NodeGroupInput')
        node_in.location = (-1000, 0)
        node_out = nodes.new('NodeGroupOutput')
        node_out.location = (1200, 0)

        # 共通の計算ノード
        # Height = Floors * Floor Height
        node_height = nodes.new('ShaderNodeMath')
        node_height.operation = 'MULTIPLY'
        node_height.location = (-800, -100)
        links.new(node_in.outputs['Floors'], node_height.inputs[0])
        links.new(node_in.outputs['Floor Height'], node_height.inputs[1])

        # Height_half = Height * 0.5
        node_h_half = nodes.new('ShaderNodeMath')
        node_h_half.operation = 'MULTIPLY'
        node_h_half.inputs[1].default_value = 0.5
        node_h_half.location = (-650, -100)
        links.new(node_height.outputs[0], node_h_half.inputs[0])

        # ==========================================
        # 1. 一般住宅の生成 (Option 0)
        # ==========================================
        # 土台となるCube
        node_house_cube = nodes.new('GeometryNodeMeshCube')
        node_house_cube.location = (-400, 400)
        
        node_house_cube_size = nodes.new('ShaderNodeCombineXYZ')
        node_house_cube_size.location = (-550, 400)
        links.new(node_in.outputs['Width'], node_house_cube_size.inputs[0])
        links.new(node_in.outputs['Depth'], node_house_cube_size.inputs[1])
        links.new(node_height.outputs[0], node_house_cube_size.inputs[2])
        links.new(node_house_cube_size.outputs[0], node_house_cube.inputs['Size'])

        # 土台のZ位置合わせ
        node_house_cube_pos = nodes.new('GeometryNodeSetPosition')
        node_house_cube_pos.location = (-250, 400)
        node_house_cube_offset = nodes.new('ShaderNodeCombineXYZ')
        node_house_cube_offset.location = (-400, 300)
        links.new(node_h_half.outputs[0], node_house_cube_offset.inputs[2])
        links.new(node_house_cube.outputs['Mesh'], node_house_cube_pos.inputs['Geometry'])
        links.new(node_house_cube_offset.outputs[0], node_house_cube_pos.inputs['Offset'])

        # 土台マテリアル設定
        node_house_cube_mat = nodes.new('GeometryNodeSetMaterial')
        node_house_cube_mat.location = (-100, 400)
        node_house_cube_mat.inputs['Material'].default_value = bpy.data.materials.get("Wall")
        links.new(node_house_cube_pos.outputs['Geometry'], node_house_cube_mat.inputs['Geometry'])

        # 切妻屋根 (Gable Roof)
        node_gable_grid = nodes.new('GeometryNodeMeshGrid')
        node_gable_grid.location = (-700, 700)
        node_gable_grid.inputs['Vertices X'].default_value = 3
        node_gable_grid.inputs['Vertices Y'].default_value = 2
        
        node_gable_size_x = nodes.new('ShaderNodeMath')
        node_gable_size_x.operation = 'ADD'
        node_gable_size_x.inputs[1].default_value = 0.6
        node_gable_size_x.location = (-850, 750)
        links.new(node_in.outputs['Width'], node_gable_size_x.inputs[0])
        links.new(node_gable_size_x.outputs[0], node_gable_grid.inputs['Size X'])

        node_gable_size_y = nodes.new('ShaderNodeMath')
        node_gable_size_y.operation = 'ADD'
        node_gable_size_y.inputs[1].default_value = 0.6
        node_gable_size_y.location = (-850, 650)
        links.new(node_in.outputs['Depth'], node_gable_size_y.inputs[0])
        links.new(node_gable_size_y.outputs[0], node_gable_grid.inputs['Size Y'])

        # 切妻リッジ（中央）の持ち上げ
        node_gable_pos = nodes.new('GeometryNodeSetPosition')
        node_gable_pos.location = (-550, 700)
        
        node_gable_input_pos = nodes.new('GeometryNodeInputPosition')
        node_gable_input_pos.location = (-850, 550)
        node_gable_sep_pos = nodes.new('ShaderNodeSeparateXYZ')
        node_gable_sep_pos.location = (-700, 550)
        links.new(node_gable_input_pos.outputs['Position'], node_gable_sep_pos.inputs['Vector'])

        # X座標の絶対値が 0.1 未満（中央）の頂点を選択
        node_gable_abs = nodes.new('ShaderNodeMath')
        node_gable_abs.operation = 'ABSOLUTE'
        node_gable_abs.location = (-550, 550)
        links.new(node_gable_sep_pos.outputs['X'], node_gable_abs.inputs[0])

        node_gable_comp = nodes.new('ShaderNodeMath')
        node_gable_comp.operation = 'LESS_THAN'
        node_gable_comp.inputs[1].default_value = 0.1
        node_gable_comp.location = (-400, 550)
        links.new(node_gable_abs.outputs[0], node_gable_comp.inputs[0])

        node_gable_offset = nodes.new('ShaderNodeCombineXYZ')
        node_gable_offset.inputs[2].default_value = 1.8  # 屋根高さ
        node_gable_offset.location = (-400, 450)

        links.new(node_gable_grid.outputs['Mesh'], node_gable_pos.inputs['Geometry'])
        links.new(node_gable_comp.outputs[0], node_gable_pos.inputs['Selection'])
        links.new(node_gable_offset.outputs[0], node_gable_pos.inputs['Offset'])

        # 厚み付け (Extrude Mesh)
        node_gable_ext = nodes.new('GeometryNodeExtrudeMesh')
        node_gable_ext.location = (-400, 700)
        node_gable_ext.inputs['Offset Scale'].default_value = -0.15
        node_gable_ext.inputs['Individual'].default_value = False
        links.new(node_gable_pos.outputs['Geometry'], node_gable_ext.inputs['Mesh'])

        # 寄棟屋根 (Hip Roof)
        node_hip_grid = nodes.new('GeometryNodeMeshGrid')
        node_hip_grid.location = (-700, 950)
        node_hip_grid.inputs['Vertices X'].default_value = 3
        node_hip_grid.inputs['Vertices Y'].default_value = 3
        links.new(node_gable_size_x.outputs[0], node_hip_grid.inputs['Size X'])
        links.new(node_gable_size_y.outputs[0], node_hip_grid.inputs['Size Y'])

        node_hip_pos = nodes.new('GeometryNodeSetPosition')
        node_hip_pos.location = (-550, 950)

        # XかつYが中央(X=0, Y=0)の頂点を選択
        node_hip_abs_x = nodes.new('ShaderNodeMath')
        node_hip_abs_x.operation = 'ABSOLUTE'
        node_hip_abs_x.location = (-850, 850)
        links.new(node_gable_sep_pos.outputs['X'], node_hip_abs_x.inputs[0])

        node_hip_comp_x = nodes.new('ShaderNodeMath')
        node_hip_comp_x.operation = 'LESS_THAN'
        node_hip_comp_x.inputs[1].default_value = 0.1
        node_hip_comp_x.location = (-700, 850)
        links.new(node_hip_abs_x.outputs[0], node_hip_comp_x.inputs[0])

        node_hip_abs_y = nodes.new('ShaderNodeMath')
        node_hip_abs_y.operation = 'ABSOLUTE'
        node_hip_abs_y.location = (-850, 780)
        links.new(node_gable_sep_pos.outputs['Y'], node_hip_abs_y.inputs[0])

        node_hip_comp_y = nodes.new('ShaderNodeMath')
        node_hip_comp_y.operation = 'LESS_THAN'
        node_hip_comp_y.inputs[1].default_value = 0.1
        node_hip_comp_y.location = (-700, 780)
        links.new(node_hip_abs_y.outputs[0], node_hip_comp_y.inputs[0])

        node_hip_and = nodes.new('ShaderNodeMath')
        node_hip_and.operation = 'MULTIPLY'
        node_hip_and.location = (-550, 850)
        links.new(node_hip_comp_x.outputs[0], node_hip_and.inputs[0])
        links.new(node_hip_comp_y.outputs[0], node_hip_and.inputs[1])

        links.new(node_hip_grid.outputs['Mesh'], node_hip_pos.inputs['Geometry'])
        links.new(node_hip_and.outputs[0], node_hip_pos.inputs['Selection'])
        links.new(node_gable_offset.outputs[0], node_hip_pos.inputs['Offset'])

        node_hip_ext = nodes.new('GeometryNodeExtrudeMesh')
        node_hip_ext.location = (-400, 950)
        node_hip_ext.inputs['Offset Scale'].default_value = -0.15
        node_hip_ext.inputs['Individual'].default_value = False
        links.new(node_hip_pos.outputs['Geometry'], node_hip_ext.inputs['Mesh'])

        # 陸屋根 (Flat Roof)
        node_flat_cube = nodes.new('GeometryNodeMeshCube')
        node_flat_cube.location = (-400, 1150)
        node_flat_cube_size = nodes.new('ShaderNodeCombineXYZ')
        node_flat_cube_size.inputs[2].default_value = 0.2
        node_flat_cube_size.location = (-550, 1150)
        links.new(node_gable_size_x.outputs[0], node_flat_cube_size.inputs[0])
        links.new(node_gable_size_y.outputs[0], node_flat_cube_size.inputs[1])
        links.new(node_flat_cube_size.outputs[0], node_flat_cube.inputs['Size'])

        # 各屋根の合成前Z移動 (Gable, Hip, Flat)
        # 移動先 Z = Height
        node_roof_trans_gable = nodes.new('GeometryNodeSetPosition')
        node_roof_trans_gable.location = (-200, 700)
        node_roof_offset = nodes.new('ShaderNodeCombineXYZ')
        node_roof_offset.location = (-350, 600)
        links.new(node_height.outputs[0], node_roof_offset.inputs[2])
        links.new(node_gable_ext.outputs['Mesh'], node_roof_trans_gable.inputs['Geometry'])
        links.new(node_roof_offset.outputs[0], node_roof_trans_gable.inputs['Offset'])

        node_roof_trans_hip = nodes.new('GeometryNodeSetPosition')
        node_roof_trans_hip.location = (-200, 950)
        links.new(node_hip_ext.outputs['Mesh'], node_roof_trans_hip.inputs['Geometry'])
        links.new(node_roof_offset.outputs[0], node_roof_trans_hip.inputs['Offset'])

        node_roof_trans_flat = nodes.new('GeometryNodeSetPosition')
        node_roof_trans_flat.location = (-200, 1150)
        node_flat_offset = nodes.new('ShaderNodeCombineXYZ')
        node_flat_offset.location = (-350, 1100)
        node_flat_offset_z = nodes.new('ShaderNodeMath')
        node_flat_offset_z.operation = 'ADD'
        node_flat_offset_z.inputs[1].default_value = 0.1
        node_flat_offset_z.location = (-500, 1100)
        links.new(node_height.outputs[0], node_flat_offset_z.inputs[0])
        links.new(node_flat_offset_z.outputs[0], node_flat_offset.inputs[2])
        links.new(node_flat_cube.outputs['Mesh'], node_roof_trans_flat.inputs['Geometry'])
        links.new(node_flat_offset.outputs[0], node_roof_trans_flat.inputs['Offset'])

        # 屋根切り替えスイッチ
        # Switch 1: Hip (True) vs Gable (False)
        node_roof_switch1 = nodes.new('GeometryNodeSwitch')
        self.set_switch_type_geometry(node_roof_switch1)
        node_roof_switch1.location = (0, 850)
        
        node_roof_style_is_1 = self.build_equality_check_node(group, node_in.outputs['Roof Style'], 1, (0, 750))
        links.new(node_roof_style_is_1.outputs[0], node_roof_switch1.inputs['Switch'])
        links.new(node_roof_trans_gable.outputs['Geometry'], node_roof_switch1.inputs['False'])
        links.new(node_roof_trans_hip.outputs['Geometry'], node_roof_switch1.inputs['True'])

        # Switch 2: Flat (True) vs Switch1 (False)
        node_roof_switch2 = nodes.new('GeometryNodeSwitch')
        self.set_switch_type_geometry(node_roof_switch2)
        node_roof_switch2.location = (150, 950)
        
        node_roof_style_is_2 = self.build_equality_check_node(group, node_in.outputs['Roof Style'], 2, (150, 850))
        links.new(node_roof_style_is_2.outputs[0], node_roof_switch2.inputs['Switch'])
        links.new(node_roof_switch1.outputs['Output'], node_roof_switch2.inputs['False'])
        links.new(node_roof_trans_flat.outputs['Geometry'], node_roof_switch2.inputs['True'])

        # 屋根マテリアル設定
        node_roof_mat = nodes.new('GeometryNodeSetMaterial')
        node_roof_mat.location = (300, 950)
        node_roof_mat.inputs['Material'].default_value = bpy.data.materials.get("Roof")
        links.new(node_roof_switch2.outputs['Output'], node_roof_mat.inputs['Geometry'])

        # 土台と屋根を結合
        node_house_join = nodes.new('GeometryNodeJoinGeometry')
        node_house_join.location = (450, 400)
        links.new(node_house_cube_mat.outputs['Geometry'], node_house_join.inputs[0])
        links.new(node_roof_mat.outputs['Geometry'], node_house_join.inputs[0])

        # ==========================================
        # 2. 高層ビルの生成 (Option 1)
        # ==========================================
        # セットバック判定: Floors > Setback Floors
        node_sb_check = nodes.new('ShaderNodeMath')
        node_sb_check.operation = 'GREATER_THAN'
        node_sb_check.location = (-750, -250)
        links.new(node_in.outputs['Floors'], node_sb_check.inputs[0])
        links.new(node_in.outputs['Setback Floors'], node_sb_check.inputs[1])

        # Flow A: セットバックなし (通常ビル)
        node_flow_a = nodes.new('GeometryNodeGroup')
        node_flow_a.node_tree = section_group
        node_flow_a.location = (-400, -200)
        links.new(node_in.outputs['Width'], node_flow_a.inputs['Width'])
        links.new(node_in.outputs['Depth'], node_flow_a.inputs['Depth'])
        links.new(node_in.outputs['Floors'], node_flow_a.inputs['Floors'])
        links.new(node_in.outputs['Floor Height'], node_flow_a.inputs['Floor Height'])
        links.new(node_in.outputs['Window Grid X'], node_flow_a.inputs['Window Grid X'])
        links.new(node_in.outputs['Window Grid Y'], node_flow_a.inputs['Window Grid Y'])

        # Flow B: セットバックあり (下部+上部)
        # 下部セクション
        node_flow_b_lower = nodes.new('GeometryNodeGroup')
        node_flow_b_lower.node_tree = section_group
        node_flow_b_lower.location = (-400, -450)
        links.new(node_in.outputs['Width'], node_flow_b_lower.inputs['Width'])
        links.new(node_in.outputs['Depth'], node_flow_b_lower.inputs['Depth'])
        links.new(node_in.outputs['Setback Floors'], node_flow_b_lower.inputs['Floors'])
        links.new(node_in.outputs['Floor Height'], node_flow_b_lower.inputs['Floor Height'])
        links.new(node_in.outputs['Window Grid X'], node_flow_b_lower.inputs['Window Grid X'])
        links.new(node_in.outputs['Window Grid Y'], node_flow_b_lower.inputs['Window Grid Y'])

        # 上部セクションパラメータ計算
        node_sb_w = nodes.new('ShaderNodeMath')
        node_sb_w.operation = 'MULTIPLY'
        node_sb_w.location = (-750, -450)
        links.new(node_in.outputs['Width'], node_sb_w.inputs[0])
        links.new(node_in.outputs['Setback Scale'], node_sb_w.inputs[1])

        node_sb_d = nodes.new('ShaderNodeMath')
        node_sb_d.operation = 'MULTIPLY'
        node_sb_d.location = (-750, -550)
        links.new(node_in.outputs['Depth'], node_sb_d.inputs[0])
        links.new(node_in.outputs['Setback Scale'], node_sb_d.inputs[1])

        node_sb_floors = nodes.new('ShaderNodeMath')
        node_sb_floors.operation = 'SUBTRACT'
        node_sb_floors.location = (-750, -650)
        links.new(node_in.outputs['Floors'], node_sb_floors.inputs[0])
        links.new(node_in.outputs['Setback Floors'], node_sb_floors.inputs[1])

        # 上部セクション
        node_flow_b_upper = nodes.new('GeometryNodeGroup')
        node_flow_b_upper.node_tree = section_group
        node_flow_b_upper.location = (-400, -650)
        links.new(node_sb_w.outputs[0], node_flow_b_upper.inputs['Width'])
        links.new(node_sb_d.outputs[0], node_flow_b_upper.inputs['Depth'])
        links.new(node_sb_floors.outputs[0], node_flow_b_upper.inputs['Floors'])
        links.new(node_in.outputs['Floor Height'], node_flow_b_upper.inputs['Floor Height'])
        links.new(node_in.outputs['Window Grid X'], node_flow_b_upper.inputs['Window Grid X'])
        links.new(node_in.outputs['Window Grid Y'], node_flow_b_upper.inputs['Window Grid Y'])

        # 上部セクションをZ方向に移動 (下部セクションの高さ分)
        # Lower Height = Setback Floors * Floor Height
        node_lower_height = nodes.new('ShaderNodeMath')
        node_lower_height.operation = 'MULTIPLY'
        node_lower_height.location = (-550, -750)
        links.new(node_in.outputs['Setback Floors'], node_lower_height.inputs[0])
        links.new(node_in.outputs['Floor Height'], node_lower_height.inputs[1])

        node_sb_upper_trans = nodes.new('GeometryNodeSetPosition')
        node_sb_upper_trans.location = (-200, -650)
        node_sb_upper_offset = nodes.new('ShaderNodeCombineXYZ')
        node_sb_upper_offset.location = (-350, -750)
        links.new(node_lower_height.outputs[0], node_sb_upper_offset.inputs[2])
        links.new(node_flow_b_upper.outputs['Geometry'], node_sb_upper_trans.inputs['Geometry'])
        links.new(node_sb_upper_offset.outputs[0], node_sb_upper_trans.inputs['Offset'])

        # 上下セクション結合
        node_sb_join = nodes.new('GeometryNodeJoinGeometry')
        node_sb_join.location = (0, -450)
        links.new(node_flow_b_lower.outputs['Geometry'], node_sb_join.inputs[0])
        links.new(node_sb_upper_trans.outputs['Geometry'], node_sb_join.inputs[0])

        # 高層ビルのセットバックスイッチ
        node_highrise_switch = nodes.new('GeometryNodeSwitch')
        self.set_switch_type_geometry(node_highrise_switch)
        node_highrise_switch.location = (150, -200)
        links.new(node_sb_check.outputs[0], node_highrise_switch.inputs['Switch'])
        links.new(node_flow_a.outputs['Geometry'], node_highrise_switch.inputs['False'])
        links.new(node_sb_join.outputs['Geometry'], node_highrise_switch.inputs['True'])

        # ==========================================
        # 3. 雑居ビルの生成 (Option 2)
        # ==========================================
        # 通常のビルにペントハウス、パラペット、看板を追加
        node_comm_base = nodes.new('GeometryNodeGroup')
        node_comm_base.node_tree = section_group
        node_comm_base.location = (-400, -900)
        links.new(node_in.outputs['Width'], node_comm_base.inputs['Width'])
        links.new(node_in.outputs['Depth'], node_comm_base.inputs['Depth'])
        links.new(node_in.outputs['Floors'], node_comm_base.inputs['Floors'])
        links.new(node_in.outputs['Floor Height'], node_comm_base.inputs['Floor Height'])
        links.new(node_in.outputs['Window Grid X'], node_comm_base.inputs['Window Grid X'])
        links.new(node_in.outputs['Window Grid Y'], node_comm_base.inputs['Window Grid Y'])

        # ペントハウス (階段室/エレベーター室)
        node_ph_cube = nodes.new('GeometryNodeMeshCube')
        node_ph_cube.location = (-400, -1100)
        
        node_ph_size = nodes.new('ShaderNodeCombineXYZ')
        node_ph_size.inputs[2].default_value = 3.0
        node_ph_size.location = (-550, -1100)
        node_ph_w = nodes.new('ShaderNodeMath')
        node_ph_w.operation = 'MULTIPLY'
        node_ph_w.inputs[1].default_value = 0.4
        node_ph_w.location = (-700, -1100)
        links.new(node_in.outputs['Width'], node_ph_w.inputs[0])
        links.new(node_ph_w.outputs[0], node_ph_size.inputs[0])

        node_ph_d = nodes.new('ShaderNodeMath')
        node_ph_d.operation = 'MULTIPLY'
        node_ph_d.inputs[1].default_value = 0.4
        node_ph_d.location = (-700, -1200)
        links.new(node_in.outputs['Depth'], node_ph_d.inputs[0])
        links.new(node_ph_d.outputs[0], node_ph_size.inputs[1])
        links.new(node_ph_size.outputs[0], node_ph_cube.inputs['Size'])

        # ペントハウス移動 (Z = Height + 1.5)
        node_ph_trans = nodes.new('GeometryNodeSetPosition')
        node_ph_trans.location = (-250, -1100)
        node_ph_offset = nodes.new('ShaderNodeCombineXYZ')
        node_ph_offset.location = (-400, -1200)
        node_ph_offset_z = nodes.new('ShaderNodeMath')
        node_ph_offset_z.operation = 'ADD'
        node_ph_offset_z.inputs[1].default_value = 1.5
        node_ph_offset_z.location = (-550, -1200)
        links.new(node_height.outputs[0], node_ph_offset_z.inputs[0])
        links.new(node_ph_offset_z.outputs[0], node_ph_offset.inputs[2])
        links.new(node_ph_cube.outputs['Mesh'], node_ph_trans.inputs['Geometry'])
        links.new(node_ph_offset.outputs[0], node_ph_trans.inputs['Offset'])

        node_ph_mat = nodes.new('GeometryNodeSetMaterial')
        node_ph_mat.location = (-100, -1100)
        node_ph_mat.inputs['Material'].default_value = bpy.data.materials.get("Wall")
        links.new(node_ph_trans.outputs['Geometry'], node_ph_mat.inputs['Geometry'])

        # パラペット (手すり壁) - 四隅をCubeで構成
        node_para_join = nodes.new('GeometryNodeJoinGeometry')
        node_para_join.location = (-250, -1350)

        # パラペットの基本サイズ計算
        node_para_h_offset = nodes.new('ShaderNodeMath')
        node_para_h_offset.operation = 'ADD'
        node_para_h_offset.inputs[1].default_value = 0.3 # 高さ中央
        node_para_h_offset.location = (-550, -1350)
        links.new(node_height.outputs[0], node_para_h_offset.inputs[0])

        # Width_half
        node_w_half_p = nodes.new('ShaderNodeMath')
        node_w_half_p.operation = 'MULTIPLY'
        node_w_half_p.inputs[1].default_value = 0.5
        node_w_half_p.location = (-850, -1300)
        links.new(node_in.outputs['Width'], node_w_half_p.inputs[0])

        node_w_half_p_offset = nodes.new('ShaderNodeMath')
        node_w_half_p_offset.operation = 'SUBTRACT'
        node_w_half_p_offset.inputs[1].default_value = 0.075
        node_w_half_p_offset.location = (-700, -1300)
        links.new(node_w_half_p.outputs[0], node_w_half_p_offset.inputs[0])

        node_w_half_p_offset_neg = nodes.new('ShaderNodeMath')
        node_w_half_p_offset_neg.operation = 'MULTIPLY'
        node_w_half_p_offset_neg.inputs[1].default_value = -1.0
        node_w_half_p_offset_neg.location = (-550, -1300)
        links.new(node_w_half_p_offset.outputs[0], node_w_half_p_offset_neg.inputs[0])

        # Depth_half
        node_d_half_p = nodes.new('ShaderNodeMath')
        node_d_half_p.operation = 'MULTIPLY'
        node_d_half_p.inputs[1].default_value = 0.5
        node_d_half_p.location = (-850, -1450)
        links.new(node_in.outputs['Depth'], node_d_half_p.inputs[0])

        node_d_half_p_offset = nodes.new('ShaderNodeMath')
        node_d_half_p_offset.operation = 'SUBTRACT'
        node_d_half_p_offset.inputs[1].default_value = 0.075
        node_d_half_p_offset.location = (-700, -1450)
        links.new(node_d_half_p.outputs[0], node_d_half_p_offset.inputs[0])

        node_d_half_p_offset_neg = nodes.new('ShaderNodeMath')
        node_d_half_p_offset_neg.operation = 'MULTIPLY'
        node_d_half_p_offset_neg.inputs[1].default_value = -1.0
        node_d_half_p_offset_neg.location = (-550, -1450)
        links.new(node_d_half_p_offset.outputs[0], node_d_half_p_offset_neg.inputs[0])

        # 前後パラペット (X方向の梁)
        node_para_fb_cube = nodes.new('GeometryNodeMeshCube')
        node_para_fb_cube.location = (-400, -1350)
        node_para_fb_size = nodes.new('ShaderNodeCombineXYZ')
        node_para_fb_size.inputs[1].default_value = 0.15
        node_para_fb_size.inputs[2].default_value = 0.6
        node_para_fb_size.location = (-550, -1350)
        links.new(node_in.outputs['Width'], node_para_fb_size.inputs[0])
        links.new(node_para_fb_size.outputs[0], node_para_fb_cube.inputs['Size'])

        # Front
        node_para_f_trans = nodes.new('GeometryNodeSetPosition')
        node_para_f_trans.location = (-250, -1450)
        node_para_f_offset = nodes.new('ShaderNodeCombineXYZ')
        node_para_f_offset.location = (-400, -1450)
        links.new(node_d_half_p_offset_neg.outputs[0], node_para_f_offset.inputs[1])
        links.new(node_para_h_offset.outputs[0], node_para_f_offset.inputs[2])
        links.new(node_para_fb_cube.outputs['Mesh'], node_para_f_trans.inputs['Geometry'])
        links.new(node_para_f_offset.outputs[0], node_para_f_trans.inputs['Offset'])
        links.new(node_para_f_trans.outputs['Geometry'], node_para_join.inputs[0])

        # Back
        node_para_b_trans = nodes.new('GeometryNodeSetPosition')
        node_para_b_trans.location = (-250, -1550)
        node_para_b_offset = nodes.new('ShaderNodeCombineXYZ')
        node_para_b_offset.location = (-400, -1550)
        links.new(node_d_half_p_offset.outputs[0], node_para_b_offset.inputs[1])
        links.new(node_para_h_offset.outputs[0], node_para_b_offset.inputs[2])
        links.new(node_para_fb_cube.outputs['Mesh'], node_para_b_trans.inputs['Geometry'])
        links.new(node_para_b_offset.outputs[0], node_para_b_trans.inputs['Offset'])
        links.new(node_para_b_trans.outputs['Geometry'], node_para_join.inputs[0])

        # 左右パラペット (Y方向の梁)
        node_para_lr_cube = nodes.new('GeometryNodeMeshCube')
        node_para_lr_cube.location = (-400, -1650)
        node_para_lr_size = nodes.new('ShaderNodeCombineXYZ')
        node_para_lr_size.inputs[0].default_value = 0.15
        node_para_lr_size.inputs[2].default_value = 0.6
        node_para_lr_size.location = (-550, -1650)
        
        node_para_lr_d = nodes.new('ShaderNodeMath')
        node_para_lr_d.operation = 'SUBTRACT'
        node_para_lr_d.inputs[1].default_value = 0.3
        node_para_lr_d.location = (-700, -1650)
        links.new(node_in.outputs['Depth'], node_para_lr_d.inputs[0])
        links.new(node_para_lr_d.outputs[0], node_para_lr_size.inputs[1])
        links.new(node_para_lr_size.outputs[0], node_para_lr_cube.inputs['Size'])

        # Left
        node_para_l_trans = nodes.new('GeometryNodeSetPosition')
        node_para_l_trans.location = (-250, -1650)
        node_para_l_offset = nodes.new('ShaderNodeCombineXYZ')
        node_para_l_offset.location = (-400, -1750)
        links.new(node_w_half_p_offset_neg.outputs[0], node_para_l_offset.inputs[0])
        links.new(node_para_h_offset.outputs[0], node_para_l_offset.inputs[2])
        links.new(node_para_lr_cube.outputs['Mesh'], node_para_l_trans.inputs['Geometry'])
        links.new(node_para_l_offset.outputs[0], node_para_l_trans.inputs['Offset'])
        links.new(node_para_l_trans.outputs['Geometry'], node_para_join.inputs[0])

        # Right
        node_para_r_trans = nodes.new('GeometryNodeSetPosition')
        node_para_r_trans.location = (-250, -1750)
        node_para_r_offset = nodes.new('ShaderNodeCombineXYZ')
        node_para_r_offset.location = (-400, -1850)
        links.new(node_w_half_p_offset.outputs[0], node_para_r_offset.inputs[0])
        links.new(node_para_h_offset.outputs[0], node_para_r_offset.inputs[2])
        links.new(node_para_lr_cube.outputs['Mesh'], node_para_r_trans.inputs['Geometry'])
        links.new(node_para_r_offset.outputs[0], node_para_r_trans.inputs['Offset'])
        links.new(node_para_r_trans.outputs['Geometry'], node_para_join.inputs[0])

        node_para_mat = nodes.new('GeometryNodeSetMaterial')
        node_para_mat.location = (-100, -1350)
        node_para_mat.inputs['Material'].default_value = bpy.data.materials.get("Wall")
        links.new(node_para_join.outputs['Geometry'], node_para_mat.inputs['Geometry'])

        # 看板/ビルボード (壁の側面に設置)
        node_billboard_cube = nodes.new('GeometryNodeMeshCube')
        node_billboard_cube.location = (-400, -1950)
        
        node_bill_size = nodes.new('ShaderNodeCombineXYZ')
        node_bill_size.inputs[0].default_value = 0.15
        node_bill_size.location = (-550, -1950)
        
        node_bill_d = nodes.new('ShaderNodeMath')
        node_bill_d.operation = 'MULTIPLY'
        node_bill_d.inputs[1].default_value = 0.3
        node_bill_d.location = (-700, -1950)
        links.new(node_in.outputs['Depth'], node_bill_d.inputs[0])
        links.new(node_bill_d.outputs[0], node_bill_size.inputs[1])

        node_bill_h = nodes.new('ShaderNodeMath')
        node_bill_h.operation = 'MULTIPLY'
        node_bill_h.inputs[1].default_value = 0.5
        node_bill_h.location = (-700, -2050)
        links.new(node_height.outputs[0], node_bill_h.inputs[0])
        links.new(node_bill_h.outputs[0], node_bill_size.inputs[2])
        links.new(node_bill_size.outputs[0], node_billboard_cube.inputs['Size'])

        # 看板の位置合わせ
        # X: Width_half + 0.1, Y: 0.0, Z: Height_half
        node_bill_trans = nodes.new('GeometryNodeSetPosition')
        node_bill_trans.location = (-250, -1950)
        
        node_bill_offset = nodes.new('ShaderNodeCombineXYZ')
        node_bill_offset.location = (-400, -2050)
        node_bill_x = nodes.new('ShaderNodeMath')
        node_bill_x.operation = 'ADD'
        node_bill_x.inputs[1].default_value = 0.1
        node_bill_x.location = (-550, -2050)
        links.new(node_w_half_p.outputs[0], node_bill_x.inputs[0])
        links.new(node_bill_x.outputs[0], node_bill_offset.inputs[0])
        links.new(node_h_half.outputs[0], node_bill_offset.inputs[2])

        links.new(node_billboard_cube.outputs['Mesh'], node_bill_trans.inputs['Geometry'])
        links.new(node_bill_offset.outputs[0], node_bill_trans.inputs['Offset'])

        # 看板マテリアル (Windowマテリアルを利用して光る看板にする)
        node_bill_mat = nodes.new('GeometryNodeSetMaterial')
        node_bill_mat.location = (-100, -1950)
        node_bill_mat.inputs['Material'].default_value = bpy.data.materials.get("Window")
        links.new(node_bill_trans.outputs['Geometry'], node_bill_mat.inputs['Geometry'])

        # 雑居ビルの全要素結合
        node_comm_join = nodes.new('GeometryNodeJoinGeometry')
        node_comm_join.location = (150, -900)
        links.new(node_comm_base.outputs['Geometry'], node_comm_join.inputs[0])
        links.new(node_ph_mat.outputs['Geometry'], node_comm_join.inputs[0])
        links.new(node_para_mat.outputs['Geometry'], node_comm_join.inputs[0])
        links.new(node_bill_mat.outputs['Geometry'], node_comm_join.inputs[0])

        # ==========================================
        # 4. 円柱タワーの生成 (Option 3)
        # ==========================================
        # シリンダー
        node_cyl = nodes.new('GeometryNodeMeshCylinder')
        node_cyl.location = (-400, -2200)
        
        # Vertices = Window Grid X * 4
        node_cyl_v = nodes.new('ShaderNodeMath')
        node_cyl_v.operation = 'MULTIPLY'
        node_cyl_v.inputs[1].default_value = 4.0
        node_cyl_v.location = (-700, -2200)
        links.new(node_in.outputs['Window Grid X'], node_cyl_v.inputs[0])
        links.new(node_cyl_v.outputs[0], node_cyl.inputs['Vertices'])

        # Segments = Floors * Window Grid Y
        node_cyl_seg = nodes.new('ShaderNodeMath')
        node_cyl_seg.operation = 'MULTIPLY'
        node_cyl_seg.location = (-700, -2300)
        links.new(node_in.outputs['Floors'], node_cyl_seg.inputs[0])
        links.new(node_in.outputs['Window Grid Y'], node_cyl_seg.inputs[1])
        links.new(node_cyl_seg.outputs[0], node_cyl.inputs['Side Segments'])

        # Radius = Width / 2
        links.new(node_w_half_p.outputs[0], node_cyl.inputs['Radius'])
        links.new(node_height.outputs[0], node_cyl.inputs['Depth'])

        # シリンダーZ位置合わせ (Z = Height / 2)
        node_cyl_pos = nodes.new('GeometryNodeSetPosition')
        node_cyl_pos.location = (-250, -2200)
        links.new(node_cyl.outputs['Mesh'], node_cyl_pos.inputs['Geometry'])
        links.new(node_house_cube_offset.outputs[0], node_cyl_pos.inputs['Offset'])

        # 壁マテリアル設定
        node_cyl_wall_mat = nodes.new('GeometryNodeSetMaterial')
        node_cyl_wall_mat.location = (-100, -2200)
        node_cyl_wall_mat.inputs['Material'].default_value = bpy.data.materials.get("Wall")
        links.new(node_cyl_pos.outputs['Geometry'], node_cyl_wall_mat.inputs['Geometry'])

        # シリンダーの側面窓生成 (Normal Zが0の面を選択)
        # Normal
        node_cyl_normal = nodes.new('GeometryNodeInputNormal')
        node_cyl_normal.location = (-700, -2450)
        node_cyl_sep = nodes.new('ShaderNodeSeparateXYZ')
        node_cyl_sep.location = (-550, -2450)
        links.new(node_cyl_normal.outputs['Normal'], node_cyl_sep.inputs['Vector'])

        node_cyl_abs_z = nodes.new('ShaderNodeMath')
        node_cyl_abs_z.operation = 'ABSOLUTE'
        node_cyl_abs_z.location = (-400, -2450)
        links.new(node_cyl_sep.outputs['Z'], node_cyl_abs_z.inputs[0])

        node_cyl_side_sel = nodes.new('ShaderNodeMath')
        node_cyl_side_sel.operation = 'LESS_THAN'
        node_cyl_side_sel.inputs[1].default_value = 0.1
        node_cyl_side_sel.location = (-250, -2450)
        links.new(node_cyl_abs_z.outputs[0], node_cyl_side_sel.inputs[0])

        # Extrude 1 (窓の枠組み)
        node_cyl_ext1 = nodes.new('GeometryNodeExtrudeMesh')
        node_cyl_ext1.location = (50, -2200)
        node_cyl_ext1.inputs['Offset Scale'].default_value = 0.0
        node_cyl_ext1.inputs['Individual'].default_value = True
        links.new(node_cyl_wall_mat.outputs['Geometry'], node_cyl_ext1.inputs['Mesh'])
        links.new(node_cyl_side_sel.outputs[0], node_cyl_ext1.inputs['Selection'])

        # Scale Elements
        node_cyl_scale = nodes.new('GeometryNodeScaleElements')
        node_cyl_scale.inputs['Scale'].default_value = 0.8
        node_cyl_scale.location = (200, -2200)
        links.new(node_cyl_ext1.outputs['Mesh'], node_cyl_scale.inputs['Geometry'])
        links.new(node_cyl_ext1.outputs['Top'], node_cyl_scale.inputs['Selection'])

        # Extrude 2 (凹み)
        node_cyl_ext2 = nodes.new('GeometryNodeExtrudeMesh')
        node_cyl_ext2.location = (350, -2200)
        node_cyl_ext2.inputs['Offset Scale'].default_value = -0.06
        node_cyl_ext2.inputs['Individual'].default_value = True
        links.new(node_cyl_scale.outputs['Geometry'], node_cyl_ext2.inputs['Mesh'])
        links.new(node_cyl_ext1.outputs['Top'], node_cyl_ext2.inputs['Selection'])

        # 窓マテリアル設定
        node_cyl_win_mat = nodes.new('GeometryNodeSetMaterial')
        node_cyl_win_mat.location = (500, -2200)
        node_cyl_win_mat.inputs['Material'].default_value = bpy.data.materials.get("Window")
        links.new(node_cyl_ext2.outputs['Mesh'], node_cyl_win_mat.inputs['Geometry'])
        links.new(node_cyl_ext2.outputs['Top'], node_cyl_win_mat.inputs['Selection'])

        # 内部コアシリンダー (凹み部分の裏当て)
        node_cyl_core = nodes.new('GeometryNodeMeshCylinder')
        node_cyl_core.location = (-250, -2600)
        node_cyl_core.inputs['Vertices'].default_value = 12
        node_cyl_core.inputs['Side Segments'].default_value = 1
        node_cyl_core_r = nodes.new('ShaderNodeMath')
        node_cyl_core_r.operation = 'SUBTRACT'
        node_cyl_core_r.inputs[1].default_value = 0.02
        node_cyl_core_r.location = (-400, -2600)
        links.new(node_w_half_p.outputs[0], node_cyl_core_r.inputs[0])
        links.new(node_cyl_core_r.outputs[0], node_cyl_core.inputs['Radius'])
        links.new(node_height.outputs[0], node_cyl_core.inputs['Depth'])

        # コア移動
        node_cyl_core_pos = nodes.new('GeometryNodeSetPosition')
        node_cyl_core_pos.location = (-100, -2600)
        links.new(node_cyl_core.outputs['Mesh'], node_cyl_core_pos.inputs['Geometry'])
        links.new(node_house_cube_offset.outputs[0], node_cyl_core_pos.inputs['Offset'])

        # コアマテリアル設定 (Wall)
        node_cyl_core_mat = nodes.new('GeometryNodeSetMaterial')
        node_cyl_core_mat.location = (50, -2600)
        node_cyl_core_mat.inputs['Material'].default_value = bpy.data.materials.get("Wall")
        links.new(node_cyl_core_pos.outputs['Geometry'], node_cyl_core_mat.inputs['Geometry'])

        # タワー全体結合
        node_cyl_join = nodes.new('GeometryNodeJoinGeometry')
        node_cyl_join.location = (650, -2200)
        links.new(node_cyl_win_mat.outputs['Geometry'], node_cyl_join.inputs[0])
        links.new(node_cyl_core_mat.outputs['Geometry'], node_cyl_join.inputs[0])


        # ==========================================
        # 5. タイプ切り替えスイッチ
        # ==========================================
        # Switch 1: Cylinder (3) vs Commercial (2)
        node_switch1 = nodes.new('GeometryNodeSwitch')
        self.set_switch_type_geometry(node_switch1)
        node_switch1.location = (700, -900)
        
        node_is_3 = self.build_equality_check_node(group, node_in.outputs['Building Type'], 3, (700, -1000))
        links.new(node_is_3.outputs[0], node_switch1.inputs['Switch'])
        links.new(node_comm_join.outputs['Geometry'], node_switch1.inputs['False'])
        links.new(node_cyl_join.outputs['Geometry'], node_switch1.inputs['True'])

        # Switch 2: Switch1 vs HighRise (1)
        node_switch2 = nodes.new('GeometryNodeSwitch')
        self.set_switch_type_geometry(node_switch2)
        node_switch2.location = (850, -400)
        
        node_is_1 = self.build_equality_check_node(group, node_in.outputs['Building Type'], 1, (850, -500))
        links.new(node_is_1.outputs[0], node_switch2.inputs['Switch'])
        links.new(node_switch1.outputs['Output'], node_switch2.inputs['False'])
        links.new(node_highrise_switch.outputs['Output'], node_switch2.inputs['True'])

        # Switch 3: Switch2 vs House (0)
        node_switch3 = nodes.new('GeometryNodeSwitch')
        self.set_switch_type_geometry(node_switch3)
        node_switch3.location = (1000, 100)
        
        node_is_0 = self.build_equality_check_node(group, node_in.outputs['Building Type'], 0, (1000, 0))
        links.new(node_is_0.outputs[0], node_switch3.inputs['Switch'])
        links.new(node_switch2.outputs['Output'], node_switch3.inputs['False'])
        links.new(node_house_join.outputs['Geometry'], node_switch3.inputs['True'])

        # 最終出力に接続
        links.new(node_switch3.outputs['Output'], node_out.inputs['Geometry'])

        # 全てのノードとリンクの構築が完了した後にノードグループを割り当てる
        # (これにより、デフォルト値がモディファイアのプロパティに正常に反映されます)
        gn_mod.node_group = group

        return {'FINISHED'}

    def get_or_create_material(self, name, color, roughness=0.5, metallic=0.0):
        """指定したマテリアルを取得するか、存在しなければ新規作成するヘルパー"""
        mat = bpy.data.materials.get(name)
        if not mat:
            mat = bpy.data.materials.new(name=name)
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                bsdf.inputs['Base Color'].default_value = color
                bsdf.inputs['Roughness'].default_value = roughness
                bsdf.inputs['Metallic'].default_value = metallic
        return mat

    def set_switch_type_geometry(self, node_switch):
        """GeometryNodeSwitch のタイプを GEOMETRY に設定する（互換性確保）"""
        try:
            node_switch.input_type = 'GEOMETRY'
        except AttributeError:
            try:
                node_switch.data_type = 'GEOMETRY'
            except AttributeError:
                pass

    def build_equality_check_node(self, group, val_socket, target_int, location):
        """val_socket == target_int を判定するBooleanを出力するノードグループ"""
        nodes = group.nodes
        links = group.links
        
        # Subtraction: val - target
        node_sub = nodes.new('ShaderNodeMath')
        node_sub.operation = 'SUBTRACT'
        node_sub.inputs[1].default_value = float(target_int)
        node_sub.location = (location[0] - 300, location[1])
        links.new(val_socket, node_sub.inputs[0])

        # Absolute: abs(val - target)
        node_abs = nodes.new('ShaderNodeMath')
        node_abs.operation = 'ABSOLUTE'
        node_abs.location = (location[0] - 150, location[1])
        links.new(node_sub.outputs[0], node_abs.inputs[0])

        # Less Than: abs(...) < 0.1
        node_comp = nodes.new('ShaderNodeMath')
        node_comp.operation = 'LESS_THAN'
        node_comp.inputs[1].default_value = 0.1
        node_comp.location = location
        links.new(node_abs.outputs[0], node_comp.inputs[0])

        return node_comp

    def get_or_create_section_group(self):
        """ビル各部の基本ブロック（ファサード窓＋内部コア）を生成するノードグループ"""
        group_name = "SectionGen"
        if group_name in bpy.data.node_groups:
            return bpy.data.node_groups[group_name]

        group = bpy.data.node_groups.new(group_name, 'GeometryNodeTree')
        
        if hasattr(group, "interface"):
            group.interface.new_socket('Width', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 5.0
            group.interface.new_socket('Depth', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 5.0
            group.interface.new_socket('Floors', in_out='INPUT', socket_type='NodeSocketInt').default_value = 3
            group.interface.new_socket('Floor Height', in_out='INPUT', socket_type='NodeSocketFloat').default_value = 3.0
            group.interface.new_socket('Window Grid X', in_out='INPUT', socket_type='NodeSocketInt').default_value = 4
            group.interface.new_socket('Window Grid Y', in_out='INPUT', socket_type='NodeSocketInt').default_value = 1
            group.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
        else:
            group.inputs.new('NodeSocketFloat', 'Width').default_value = 5.0
            group.inputs.new('NodeSocketFloat', 'Depth').default_value = 5.0
            group.inputs.new('NodeSocketInt', 'Floors').default_value = 3
            group.inputs.new('NodeSocketFloat', 'Floor Height').default_value = 3.0
            group.inputs.new('NodeSocketInt', 'Window Grid X').default_value = 4
            group.inputs.new('NodeSocketInt', 'Window Grid Y').default_value = 1
            group.outputs.new('NodeSocketGeometry', 'Geometry')

        nodes = group.nodes
        links = group.links

        node_in = nodes.new('NodeGroupInput')
        node_in.location = (-1200, 0)
        node_out = nodes.new('NodeGroupOutput')
        node_out.location = (800, 0)

        # 1. 寸法計算
        # Width half
        node_w_half = nodes.new('ShaderNodeMath')
        node_w_half.operation = 'MULTIPLY'
        node_w_half.inputs[1].default_value = 0.5
        node_w_half.location = (-1000, 200)
        links.new(node_in.outputs['Width'], node_w_half.inputs[0])

        node_w_half_neg = nodes.new('ShaderNodeMath')
        node_w_half_neg.operation = 'MULTIPLY'
        node_w_half_neg.inputs[1].default_value = -1.0
        node_w_half_neg.location = (-850, 200)
        links.new(node_w_half.outputs[0], node_w_half_neg.inputs[0])

        # Depth half
        node_d_half = nodes.new('ShaderNodeMath')
        node_d_half.operation = 'MULTIPLY'
        node_d_half.inputs[1].default_value = 0.5
        node_d_half.location = (-1000, 50)
        links.new(node_in.outputs['Depth'], node_d_half.inputs[0])

        node_d_half_neg = nodes.new('ShaderNodeMath')
        node_d_half_neg.operation = 'MULTIPLY'
        node_d_half_neg.inputs[1].default_value = -1.0
        node_d_half_neg.location = (-850, 50)
        links.new(node_d_half.outputs[0], node_d_half_neg.inputs[0])

        # Total Height
        node_height = nodes.new('ShaderNodeMath')
        node_height.operation = 'MULTIPLY'
        node_height.location = (-1000, -100)
        links.new(node_in.outputs['Floors'], node_height.inputs[0])
        links.new(node_in.outputs['Floor Height'], node_height.inputs[1])

        # Height half
        node_h_half = nodes.new('ShaderNodeMath')
        node_h_half.operation = 'MULTIPLY'
        node_h_half.inputs[1].default_value = 0.5
        node_h_half.location = (-850, -100)
        links.new(node_height.outputs[0], node_h_half.inputs[0])

        # Grid 分割数計算
        # Vertices X = Window Grid X + 1
        node_vx = nodes.new('ShaderNodeMath')
        node_vx.operation = 'ADD'
        node_vx.inputs[1].default_value = 1.0
        node_vx.location = (-1000, 350)
        links.new(node_in.outputs['Window Grid X'], node_vx.inputs[0])

        # Vertices Y = Floors * Window Grid Y + 1
        node_vy_mul = nodes.new('ShaderNodeMath')
        node_vy_mul.operation = 'MULTIPLY'
        node_vy_mul.location = (-1000, 500)
        links.new(node_in.outputs['Floors'], node_vy_mul.inputs[0])
        links.new(node_in.outputs['Window Grid Y'], node_vy_mul.inputs[1])

        node_vy = nodes.new('ShaderNodeMath')
        node_vy.operation = 'ADD'
        node_vy.inputs[1].default_value = 1.0
        node_vy.location = (-850, 500)
        links.new(node_vy_mul.outputs[0], node_vy.inputs[0])

        # 4面のウォールを格納する結合ノード
        node_wall_join = nodes.new('GeometryNodeJoinGeometry')
        node_wall_join.location = (-200, 0)

        # FRONT ウォール
        node_grid_f = nodes.new('GeometryNodeMeshGrid')
        node_grid_f.location = (-700, 300)
        links.new(node_in.outputs['Width'], node_grid_f.inputs['Size X'])
        links.new(node_height.outputs[0], node_grid_f.inputs['Size Y'])
        links.new(node_vx.outputs[0], node_grid_f.inputs['Vertices X'])
        links.new(node_vy.outputs[0], node_grid_f.inputs['Vertices Y'])

        node_trans_f = nodes.new('GeometryNodeSetPosition')
        node_trans_f.location = (-500, 300)
        node_offset_f = nodes.new('ShaderNodeCombineXYZ')
        node_offset_f.location = (-700, 150)
        links.new(node_d_half_neg.outputs[0], node_offset_f.inputs[1])
        links.new(node_h_half.outputs[0], node_offset_f.inputs[2])
        links.new(node_grid_f.outputs['Mesh'], node_trans_f.inputs['Geometry'])
        links.new(node_offset_f.outputs[0], node_trans_f.inputs['Offset'])
        
        node_tf_f = nodes.new('GeometryNodeTransform')
        node_tf_f.inputs['Rotation'].default_value = (1.57079, 0.0, 0.0) # X=90 deg
        node_tf_f.location = (-350, 300)
        links.new(node_trans_f.outputs['Geometry'], node_tf_f.inputs['Geometry'])
        links.new(node_tf_f.outputs['Geometry'], node_wall_join.inputs[0])

        # BACK ウォール
        node_grid_b = nodes.new('GeometryNodeMeshGrid')
        node_grid_b.location = (-700, -100)
        links.new(node_in.outputs['Width'], node_grid_b.inputs['Size X'])
        links.new(node_height.outputs[0], node_grid_b.inputs['Size Y'])
        links.new(node_vx.outputs[0], node_grid_b.inputs['Vertices X'])
        links.new(node_vy.outputs[0], node_grid_b.inputs['Vertices Y'])

        node_trans_b = nodes.new('GeometryNodeSetPosition')
        node_trans_b.location = (-500, -100)
        node_offset_b = nodes.new('ShaderNodeCombineXYZ')
        node_offset_b.location = (-700, -250)
        links.new(node_d_half.outputs[0], node_offset_b.inputs[1])
        links.new(node_h_half.outputs[0], node_offset_b.inputs[2])
        links.new(node_grid_b.outputs['Mesh'], node_trans_b.inputs['Geometry'])
        links.new(node_offset_b.outputs[0], node_trans_b.inputs['Offset'])

        node_tf_b = nodes.new('GeometryNodeTransform')
        node_tf_b.inputs['Rotation'].default_value = (-1.57079, 0.0, 0.0) # X=-90 deg
        node_tf_b.location = (-350, -100)
        links.new(node_trans_b.outputs['Geometry'], node_tf_b.inputs['Geometry'])
        links.new(node_tf_b.outputs['Geometry'], node_wall_join.inputs[0])

        # LEFT ウォール
        node_grid_l = nodes.new('GeometryNodeMeshGrid')
        node_grid_l.location = (-700, -500)
        links.new(node_in.outputs['Depth'], node_grid_l.inputs['Size X'])
        links.new(node_height.outputs[0], node_grid_l.inputs['Size Y'])
        links.new(node_vx.outputs[0], node_grid_l.inputs['Vertices X'])
        links.new(node_vy.outputs[0], node_grid_l.inputs['Vertices Y'])

        node_trans_l = nodes.new('GeometryNodeSetPosition')
        node_trans_l.location = (-500, -500)
        node_offset_l = nodes.new('ShaderNodeCombineXYZ')
        node_offset_l.location = (-700, -650)
        links.new(node_w_half_neg.outputs[0], node_offset_l.inputs[0])
        links.new(node_h_half.outputs[0], node_offset_l.inputs[2])
        links.new(node_grid_l.outputs['Mesh'], node_trans_l.inputs['Geometry'])
        links.new(node_offset_l.outputs[0], node_trans_l.inputs['Offset'])

        node_tf_l = nodes.new('GeometryNodeTransform')
        node_tf_l.inputs['Rotation'].default_value = (1.57079, 0.0, -1.57079) # X=90, Z=-90
        node_tf_l.location = (-350, -500)
        links.new(node_trans_l.outputs['Geometry'], node_tf_l.inputs['Geometry'])
        links.new(node_tf_l.outputs['Geometry'], node_wall_join.inputs[0])

        # RIGHT ウォール
        node_grid_r = nodes.new('GeometryNodeMeshGrid')
        node_grid_r.location = (-700, -900)
        links.new(node_in.outputs['Depth'], node_grid_r.inputs['Size X'])
        links.new(node_height.outputs[0], node_grid_r.inputs['Size Y'])
        links.new(node_vx.outputs[0], node_grid_r.inputs['Vertices X'])
        links.new(node_vy.outputs[0], node_grid_r.inputs['Vertices Y'])

        node_trans_r = nodes.new('GeometryNodeSetPosition')
        node_trans_r.location = (-500, -900)
        node_offset_r = nodes.new('ShaderNodeCombineXYZ')
        node_offset_r.location = (-700, -1050)
        links.new(node_w_half.outputs[0], node_offset_r.inputs[0])
        links.new(node_h_half.outputs[0], node_offset_r.inputs[2])
        links.new(node_grid_r.outputs['Mesh'], node_trans_r.inputs['Geometry'])
        links.new(node_offset_r.outputs[0], node_trans_r.inputs['Offset'])

        node_tf_r = nodes.new('GeometryNodeTransform')
        node_tf_r.inputs['Rotation'].default_value = (1.57079, 0.0, 1.57079) # X=90, Z=90
        node_tf_r.location = (-350, -900)
        links.new(node_trans_r.outputs['Geometry'], node_tf_r.inputs['Geometry'])
        links.new(node_tf_r.outputs['Geometry'], node_wall_join.inputs[0])

        # 2. 壁全体の初期マテリアルを設定 (Wall)
        node_set_wall_mat = nodes.new('GeometryNodeSetMaterial')
        node_set_wall_mat.location = (-50, 0)
        node_set_wall_mat.inputs['Material'].default_value = bpy.data.materials.get("Wall")
        links.new(node_wall_join.outputs['Geometry'], node_set_wall_mat.inputs['Geometry'])

        # 3. 窓グリッド凹凸処理 (Extrude 1 -> Scale Elements -> Extrude 2)
        node_ext1 = nodes.new('GeometryNodeExtrudeMesh')
        node_ext1.mode = 'FACES'
        node_ext1.inputs['Offset Scale'].default_value = 0.0
        node_ext1.inputs['Individual'].default_value = True
        node_ext1.location = (100, 0)
        links.new(node_set_wall_mat.outputs['Geometry'], node_ext1.inputs['Mesh'])

        # Scale Elements
        node_scale = nodes.new('GeometryNodeScaleElements')
        node_scale.inputs['Scale'].default_value = 0.82
        node_scale.location = (250, 0)
        links.new(node_ext1.outputs['Mesh'], node_scale.inputs['Geometry'])
        links.new(node_ext1.outputs['Top'], node_scale.inputs['Selection'])

        # Extrude 2
        node_ext2 = nodes.new('GeometryNodeExtrudeMesh')
        node_ext2.mode = 'FACES'
        node_ext2.inputs['Offset Scale'].default_value = -0.06
        node_ext2.inputs['Individual'].default_value = True
        node_ext2.location = (400, 0)
        links.new(node_scale.outputs['Geometry'], node_ext2.inputs['Mesh'])
        links.new(node_ext1.outputs['Top'], node_ext2.inputs['Selection'])

        # 窓ガラス面のマテリアル設定 (Window)
        node_set_win_mat = nodes.new('GeometryNodeSetMaterial')
        node_set_win_mat.location = (550, 0)
        node_set_win_mat.inputs['Material'].default_value = bpy.data.materials.get("Window")
        links.new(node_ext2.outputs['Mesh'], node_set_win_mat.inputs['Geometry'])
        links.new(node_ext2.outputs['Top'], node_set_win_mat.inputs['Selection'])

        # 4. 内部コア (裏当て用Cube) の作成
        node_core_cube = nodes.new('GeometryNodeMeshCube')
        node_core_cube.location = (-100, -350)
        
        node_core_size = nodes.new('ShaderNodeCombineXYZ')
        node_core_size.location = (-250, -350)
        links.new(node_height.outputs[0], node_core_size.inputs[2])

        node_core_w = nodes.new('ShaderNodeMath')
        node_core_w.operation = 'SUBTRACT'
        node_core_w.inputs[1].default_value = 0.02
        node_core_w.location = (-400, -350)
        links.new(node_in.outputs['Width'], node_core_w.inputs[0])
        links.new(node_core_w.outputs[0], node_core_size.inputs[0])

        node_core_d = nodes.new('ShaderNodeMath')
        node_core_d.operation = 'SUBTRACT'
        node_core_d.inputs[1].default_value = 0.02
        node_core_d.location = (-400, -450)
        links.new(node_in.outputs['Depth'], node_core_d.inputs[0])
        links.new(node_core_d.outputs[0], node_core_size.inputs[1])
        links.new(node_core_size.outputs[0], node_core_cube.inputs['Size'])

        node_core_pos = nodes.new('GeometryNodeSetPosition')
        node_core_pos.location = (50, -350)
        node_core_offset = nodes.new('ShaderNodeCombineXYZ')
        node_core_offset.location = (-100, -450)
        links.new(node_h_half.outputs[0], node_core_offset.inputs[2])
        links.new(node_core_cube.outputs['Mesh'], node_core_pos.inputs['Geometry'])
        links.new(node_core_offset.outputs[0], node_core_pos.inputs['Offset'])

        node_core_mat = nodes.new('GeometryNodeSetMaterial')
        node_core_mat.location = (200, -350)
        node_core_mat.inputs['Material'].default_value = bpy.data.materials.get("Wall")
        links.new(node_core_pos.outputs['Geometry'], node_core_mat.inputs['Geometry'])

        # 5. ファサードとコアを結合
        node_section_join = nodes.new('GeometryNodeJoinGeometry')
        node_section_join.location = (650, -150)
        links.new(node_set_win_mat.outputs['Geometry'], node_section_join.inputs[0])
        links.new(node_core_mat.outputs['Geometry'], node_section_join.inputs[0])

        # 最終出力
        links.new(node_section_join.outputs['Geometry'], node_out.inputs['Geometry'])

        return group
