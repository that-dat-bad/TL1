import bpy

# オペレータ スプライン道路生成
class MYADDON_OT_create_road_along_spline(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_create_road_along_spline"
    bl_label = "スプライン道路生成"
    bl_description = "スプライン曲線に沿って道路メッシュを生成します"
    bl_options = {'REGISTER', 'UNDO'}

    road_width: bpy.props.FloatProperty(  # type: ignore
        name="道路の幅",
        description="道路メッシュの横幅を指定します",
        default=2.0,
        min=0.1,
    )

    def execute(self, context):
        # 1. POLY曲線の作成（Fillet CurveのPOLYモードと相性が良く、Alt+Sも確実に動作する）
        curve_data = bpy.data.curves.new("RoadPath", 'CURVE')
        curve_data.dimensions = '3D'
        
        # 道路がねじれたり反転したりするのを防ぐため、Twist Modeを Z-Up に固定
        curve_data.twist_mode = 'Z_UP'

        
        spline = curve_data.splines.new('POLY')
        spline.points.add(1)  # デフォルトで1点あるので、計2点になる
        spline.points[0].co = (0.0, 0.0, 0.0, 1.0)  # (x, y, z, w)
        spline.points[1].co = (4.0, 0.0, 0.0, 1.0)
        
        curve_obj = bpy.data.objects.new("RoadPath", curve_data)
        context.collection.objects.link(curve_obj)
        context.view_layer.objects.active = curve_obj
        curve_obj.select_set(True)
        
        # 2. Geometry Nodesで道路メッシュを生成
        gn_mod = curve_obj.modifiers.new(name="RoadGen", type='NODES')
        group = bpy.data.node_groups.new("RoadGenTree", 'GeometryNodeTree')
        gn_mod.node_group = group
        
        # バージョン互換性（Blender 4.0以降と3.x以前）
        if hasattr(group, "interface"):
            group.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
            group.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
        else:
            group.inputs.new('NodeSocketGeometry', 'Geometry')
            group.outputs.new('NodeSocketGeometry', 'Geometry')
            
        nodes = group.nodes
        links = group.links
        
        node_in = nodes.new('NodeGroupInput')
        node_out = nodes.new('NodeGroupOutput')
        
        # Fillet Curve: 角を自動的に丸める（Z-fighting防止）
        # 各頂点のradius属性（Alt+S）をフィレット半径の倍率として使用
        # → radius=1.0（デフォルト）：通常通り角が丸まる
        # → radius=0.0（Alt+S → 0）：丸めなし＝道路がその点を必ず通過する
        fillet_curve = nodes.new('GeometryNodeFilletCurve')
        fillet_curve.mode = 'POLY'
        fillet_curve.inputs['Count'].default_value = 16
        # S字カーブなどで隣り合うフィレット同士が重ならないように半径を自動制限
        fillet_curve.inputs['Limit Radius'].default_value = True
        
        # 基本フィレット半径 × 各頂点のradius属性（フィレット前に読み取る）
        base_radius = nodes.new('ShaderNodeValue')
        base_radius.outputs[0].default_value = self.road_width * 1.0
        
        radius_attr = nodes.new('GeometryNodeInputRadius')
        
        multiply = nodes.new('ShaderNodeMath')
        multiply.operation = 'MULTIPLY'
        
        links.new(base_radius.outputs[0], multiply.inputs[0])
        links.new(radius_attr.outputs[0], multiply.inputs[1])
        links.new(multiply.outputs[0], fillet_curve.inputs['Radius'])
        
        links.new(node_in.outputs[0], fillet_curve.inputs['Curve'])
        
        # フィレット後、全頂点の半径を1.0に統一（道路幅を一定に保つ）
        set_radius = nodes.new('GeometryNodeSetCurveRadius')
        set_radius.inputs['Radius'].default_value = 1.0
        
        links.new(fillet_curve.outputs[0], set_radius.inputs['Curve'])
        
        # 道路本体 (Curve to Mesh)
        curve_to_mesh = nodes.new('GeometryNodeCurveToMesh')
        profile_line = nodes.new('GeometryNodeCurvePrimitiveLine')
        profile_line.inputs['Start'].default_value = (-self.road_width / 2.0, 0, 0)
        profile_line.inputs['End'].default_value = (self.road_width / 2.0, 0, 0)
        
        links.new(set_radius.outputs[0], curve_to_mesh.inputs['Curve'])
        links.new(profile_line.outputs[0], curve_to_mesh.inputs['Profile Curve'])
        
        # 重なった頂点を自動マージ（角・分岐点のZ-fighting軽減）
        merge = nodes.new('GeometryNodeMergeByDistance')
        merge.inputs['Distance'].default_value = 0.001
        
        links.new(curve_to_mesh.outputs[0], merge.inputs['Geometry'])
        links.new(merge.outputs[0], node_out.inputs[0])
        
        # アクティブオブジェクトをメインのカーブに戻す
        context.view_layer.objects.active = curve_obj
        curve_obj.select_set(True)

        print("スプライン道路を生成しました。")
        return {'FINISHED'}


