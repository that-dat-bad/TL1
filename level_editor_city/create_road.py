import bpy
import mathutils
import math
import os
import sys

# マテリアルヘルパーのインポート（terrain_materials との連携）
def get_or_create_road_material_helper(road_type='ASPHALT'):
    """道路マテリアルを取得または作成（ASPHALT, GRAVEL, SAND_DIRT）"""
    try:
        from level_editor_terrain.terrain_materials import get_or_create_road_material
        return get_or_create_road_material(road_type)
    except Exception:
        pass
    
    # フォールバック処理
    mat_name = f"Road_Material_{road_type}" if road_type != 'ASPHALT' else "Road_Asphalt"
    mat = bpy.data.materials.get(mat_name)
    if mat:
        return mat
    mat = bpy.data.materials.new(mat_name)
    mat.use_nodes = True
    if road_type == 'SAND_DIRT':
        col = (0.80, 0.64, 0.40, 1.0)
    elif road_type == 'GRAVEL':
        col = (0.52, 0.48, 0.42, 1.0)
    else:
        col = (0.12, 0.12, 0.12, 1.0)
    mat.diffuse_color = col
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = col
        bsdf.inputs["Roughness"].default_value = 0.85
    return mat


def setup_road_geometry_nodes(curve_obj, road_type='ASPHALT', lane_count=2, lane_width=1.0, line_width=0.08):
    """
    スプラインカーブオブジェクトに道路生成 Geometry Nodes (RoadGen) を構築・適用します。
    - ASPHALT: 道路面 + 白線車線マーキング + フィレット
    - GRAVEL / SAND_DIRT: 砂利道・砂道マテリアル + フィレット（未舗装のため白線なし）
    """
    total_width = lane_count * lane_width

    mat_road = get_or_create_road_material_helper(road_type)
    mat_line = None
    if road_type == 'ASPHALT':
        mat_line = bpy.data.materials.get("Road_LaneLine")
        if mat_line is None:
            mat_line = bpy.data.materials.new("Road_LaneLine")
            mat_line.use_nodes = True
            mat_line.diffuse_color = (0.95, 0.95, 0.95, 1.0)
            bsdf = mat_line.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 0.95, 1.0)
                bsdf.inputs["Roughness"].default_value = 0.5

    # マテリアルスロット更新
    curve_obj.data.materials.clear()
    curve_obj.data.materials.append(mat_road)
    if mat_line:
        curve_obj.data.materials.append(mat_line)

    # Geometry Nodes モディファイア
    gn_mod = curve_obj.modifiers.get("RoadGen")
    if not gn_mod:
        gn_mod = curve_obj.modifiers.new(name="RoadGen", type='NODES')
    group = bpy.data.node_groups.new(f"RoadGenTree_{road_type}", 'GeometryNodeTree')
    gn_mod.node_group = group

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
    node_in.location = (-600, 0)
    node_out.location = (800, 0)

    # Fillet Curve
    fillet_curve = nodes.new('GeometryNodeFilletCurve')
    fillet_curve.mode = 'POLY'
    fillet_curve.inputs['Count'].default_value = 16
    fillet_curve.inputs['Limit Radius'].default_value = True
    fillet_curve.location = (-400, 100)

    base_radius = nodes.new('ShaderNodeValue')
    base_radius.outputs[0].default_value = total_width * 1.0
    base_radius.location = (-600, 200)

    radius_attr = nodes.new('GeometryNodeInputRadius')
    radius_attr.location = (-600, 300)

    multiply = nodes.new('ShaderNodeMath')
    multiply.operation = 'MULTIPLY'
    multiply.location = (-450, 250)
    links.new(base_radius.outputs[0], multiply.inputs[0])
    links.new(radius_attr.outputs[0], multiply.inputs[1])
    links.new(multiply.outputs[0], fillet_curve.inputs['Radius'])
    links.new(node_in.outputs[0], fillet_curve.inputs['Curve'])

    # Set Radius
    set_radius = nodes.new('GeometryNodeSetCurveRadius')
    set_radius.inputs['Radius'].default_value = 1.0
    set_radius.location = (-250, 100)
    links.new(fillet_curve.outputs[0], set_radius.inputs['Curve'])

    # Curve to Mesh (道路面)
    curve_to_mesh = nodes.new('GeometryNodeCurveToMesh')
    curve_to_mesh.location = (-50, 100)
    profile_line = nodes.new('GeometryNodeCurvePrimitiveLine')
    profile_line.inputs['Start'].default_value = (total_width / 2.0, 0, 0)
    profile_line.inputs['End'].default_value = (-total_width / 2.0, 0, 0)
    profile_line.location = (-250, -50)
    links.new(set_radius.outputs[0], curve_to_mesh.inputs['Curve'])
    links.new(profile_line.outputs[0], curve_to_mesh.inputs['Profile Curve'])

    # 道路面を地面から確実に浮かせる (Z +0.20m)
    transform_road = nodes.new('GeometryNodeTransform')
    transform_road.inputs['Translation'].default_value = (0, 0, 0.20)
    transform_road.location = (150, 100)
    links.new(curve_to_mesh.outputs[0], transform_road.inputs['Geometry'])

    set_mat_road = nodes.new('GeometryNodeSetMaterial')
    set_mat_road.inputs['Material'].default_value = mat_road
    set_mat_road.location = (300, 100)
    links.new(transform_road.outputs[0], set_mat_road.inputs['Geometry'])

    if road_type == 'ASPHALT' and mat_line:
        # 白線マーキング
        marking_positions = []
        marking_positions.append(-total_width / 2.0 + line_width / 2.0)
        marking_positions.append( total_width / 2.0 - line_width / 2.0)
        for i in range(1, lane_count):
            marking_positions.append(-total_width / 2.0 + i * lane_width)

        join_profiles = nodes.new('GeometryNodeJoinGeometry')
        join_profiles.location = (-50, -200)
        for pos in marking_positions:
            ln = nodes.new('GeometryNodeCurvePrimitiveLine')
            ln.inputs['Start'].default_value = (pos + line_width / 2.0, 0, 0)
            ln.inputs['End'].default_value   = (pos - line_width / 2.0, 0, 0)
            links.new(ln.outputs[0], join_profiles.inputs['Geometry'])

        curve_to_mesh_lines = nodes.new('GeometryNodeCurveToMesh')
        curve_to_mesh_lines.location = (150, -200)
        links.new(set_radius.outputs[0], curve_to_mesh_lines.inputs['Curve'])
        links.new(join_profiles.outputs[0], curve_to_mesh_lines.inputs['Profile Curve'])

        # 白線を道路面よりさらに8mm浮かせる (Z +0.208m)
        transform_lines = nodes.new('GeometryNodeTransform')
        transform_lines.inputs['Translation'].default_value = (0, 0, 0.208)
        transform_lines.location = (300, -200)
        links.new(curve_to_mesh_lines.outputs[0], transform_lines.inputs['Geometry'])

        set_mat_line = nodes.new('GeometryNodeSetMaterial')
        set_mat_line.inputs['Material'].default_value = mat_line
        set_mat_line.location = (450, -200)
        links.new(transform_lines.outputs[0], set_mat_line.inputs['Geometry'])

        join_all = nodes.new('GeometryNodeJoinGeometry')
        join_all.location = (550, 0)
        links.new(set_mat_road.outputs[0], join_all.inputs['Geometry'])
        links.new(set_mat_line.outputs[0], join_all.inputs['Geometry'])
        last_geom = join_all.outputs[0]
    else:
        last_geom = set_mat_road.outputs[0]

    merge = nodes.new('GeometryNodeMergeByDistance')
    merge.inputs['Distance'].default_value = 0.001
    merge.location = (700, 0)
    links.new(last_geom, merge.inputs['Geometry'])
    links.new(merge.outputs[0], node_out.inputs[0])

    return gn_mod


def setup_mixed_road_geometry_nodes(curve_obj, primary_type='ASPHALT', secondary_type='SAND_DIRT',
                                    main_width=24.0, sub_width=12.0, main_lanes=4, line_width=0.15):
    """
    幹線道路（アスファルト＋白線）と街路・小道（砂道または砂利道）を
    スプラインの radius 属性 (幹線 > 0.75, 街路 <= 0.75) に応じて1つのオブジェクト内で混在生成します。
    """
    mat_main = get_or_create_road_material_helper(primary_type)
    mat_sub = get_or_create_road_material_helper(secondary_type)
    mat_line = bpy.data.materials.get("Road_LaneLine")
    if mat_line is None:
        mat_line = bpy.data.materials.new("Road_LaneLine")
        mat_line.use_nodes = True
        mat_line.diffuse_color = (0.95, 0.95, 0.95, 1.0)
        bsdf = mat_line.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 0.95, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.5

    curve_obj.data.materials.clear()
    curve_obj.data.materials.append(mat_main)
    curve_obj.data.materials.append(mat_line)
    curve_obj.data.materials.append(mat_sub)

    gn_mod = curve_obj.modifiers.get("RoadGen")
    if not gn_mod:
        gn_mod = curve_obj.modifiers.new(name="RoadGen", type='NODES')
    group = bpy.data.node_groups.new("RoadGenTree_Mixed", 'GeometryNodeTree')
    gn_mod.node_group = group

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
    node_in.location = (-1000, 0)
    node_out.location = (1100, 0)

    # 1. 頂点Radiusによる幹線と街路の分離 (radius > 0.75 -> 幹線)
    radius_attr = nodes.new('GeometryNodeInputRadius')
    radius_attr.location = (-900, 300)

    compare_node = nodes.new('ShaderNodeMath')
    compare_node.operation = 'GREATER_THAN'
    compare_node.location = (-750, 300)
    compare_node.inputs[1].default_value = 0.75
    links.new(radius_attr.outputs[0], compare_node.inputs[0])

    sep_geom = nodes.new('GeometryNodeSeparateGeometry')
    sep_geom.location = (-550, 0)
    links.new(node_in.outputs['Geometry'], sep_geom.inputs['Geometry'])
    links.new(compare_node.outputs[0], sep_geom.inputs['Selection'])

    # 2. 幹線（Selection: radius > 0.75）の処理
    fillet_main = nodes.new('GeometryNodeFilletCurve')
    fillet_main.mode = 'POLY'
    fillet_main.inputs['Count'].default_value = 16
    fillet_main.inputs['Limit Radius'].default_value = True
    fillet_main.inputs['Radius'].default_value = main_width * 0.8
    fillet_main.location = (-350, 200)
    links.new(sep_geom.outputs['Selection'], fillet_main.inputs['Curve'])

    curve_to_mesh_main = nodes.new('GeometryNodeCurveToMesh')
    curve_to_mesh_main.location = (-100, 200)
    prof_line_main = nodes.new('GeometryNodeCurvePrimitiveLine')
    prof_line_main.inputs['Start'].default_value = (main_width / 2.0, 0, 0)
    prof_line_main.inputs['End'].default_value = (-main_width / 2.0, 0, 0)
    prof_line_main.location = (-300, 50)
    links.new(fillet_main.outputs[0], curve_to_mesh_main.inputs['Curve'])
    links.new(prof_line_main.outputs[0], curve_to_mesh_main.inputs['Profile Curve'])

    # 幹線道路面を地面から確実に浮かせる (Z +0.22m)
    transform_road_main = nodes.new('GeometryNodeTransform')
    transform_road_main.inputs['Translation'].default_value = (0, 0, 0.22)
    transform_road_main.location = (50, 200)
    links.new(curve_to_mesh_main.outputs[0], transform_road_main.inputs['Geometry'])

    set_mat_main = nodes.new('GeometryNodeSetMaterial')
    set_mat_main.inputs['Material'].default_value = mat_main
    set_mat_main.location = (200, 200)
    links.new(transform_road_main.outputs[0], set_mat_main.inputs['Geometry'])

    # 幹線の車線マーキング（白線: Z +0.228m でアスファルトの8mm上に配置）
    join_profiles_main = nodes.new('GeometryNodeJoinGeometry')
    join_profiles_main.location = (-300, -150)
    marking_positions = [-main_width / 2.0 + line_width / 2.0, main_width / 2.0 - line_width / 2.0]
    lane_w = main_width / main_lanes
    for i in range(1, main_lanes):
        marking_positions.append(-main_width / 2.0 + i * lane_w)
    for pos in marking_positions:
        ln = nodes.new('GeometryNodeCurvePrimitiveLine')
        ln.inputs['Start'].default_value = (pos + line_width / 2.0, 0, 0)
        ln.inputs['End'].default_value   = (pos - line_width / 2.0, 0, 0)
        links.new(ln.outputs[0], join_profiles_main.inputs['Geometry'])

    mesh_lines_main = nodes.new('GeometryNodeCurveToMesh')
    mesh_lines_main.location = (-100, -100)
    links.new(fillet_main.outputs[0], mesh_lines_main.inputs['Curve'])
    links.new(join_profiles_main.outputs[0], mesh_lines_main.inputs['Profile Curve'])

    transform_lines = nodes.new('GeometryNodeTransform')
    transform_lines.inputs['Translation'].default_value = (0, 0, 0.228)
    transform_lines.location = (100, -100)
    links.new(mesh_lines_main.outputs[0], transform_lines.inputs['Geometry'])

    set_mat_line = nodes.new('GeometryNodeSetMaterial')
    set_mat_line.inputs['Material'].default_value = mat_line
    set_mat_line.location = (250, -100)
    links.new(transform_lines.outputs[0], set_mat_line.inputs['Geometry'])

    join_main_all = nodes.new('GeometryNodeJoinGeometry')
    join_main_all.location = (450, 150)
    links.new(set_mat_main.outputs[0], join_main_all.inputs['Geometry'])
    links.new(set_mat_line.outputs[0], join_main_all.inputs['Geometry'])

    # 3. 街路・小道（Inverted: radius <= 0.75）の処理
    fillet_sub = nodes.new('GeometryNodeFilletCurve')
    fillet_sub.mode = 'POLY'
    fillet_sub.inputs['Count'].default_value = 16
    fillet_sub.inputs['Limit Radius'].default_value = True
    fillet_sub.inputs['Radius'].default_value = sub_width * 0.8
    fillet_sub.location = (-350, -350)
    links.new(sep_geom.outputs['Inverted'], fillet_sub.inputs['Curve'])

    curve_to_mesh_sub = nodes.new('GeometryNodeCurveToMesh')
    curve_to_mesh_sub.location = (-100, -350)
    prof_line_sub = nodes.new('GeometryNodeCurvePrimitiveLine')
    prof_line_sub.inputs['Start'].default_value = (sub_width / 2.0, 0, 0)
    prof_line_sub.inputs['End'].default_value = (-sub_width / 2.0, 0, 0)
    prof_line_sub.location = (-300, -500)
    links.new(fillet_sub.outputs[0], curve_to_mesh_sub.inputs['Curve'])
    links.new(prof_line_sub.outputs[0], curve_to_mesh_sub.inputs['Profile Curve'])

    # 街路・小道面も地面から確実に浮かせる (Z +0.20m)
    transform_sub = nodes.new('GeometryNodeTransform')
    transform_sub.inputs['Translation'].default_value = (0, 0, 0.20)
    transform_sub.location = (50, -350)
    links.new(curve_to_mesh_sub.outputs[0], transform_sub.inputs['Geometry'])

    set_mat_sub = nodes.new('GeometryNodeSetMaterial')
    set_mat_sub.inputs['Material'].default_value = mat_sub
    set_mat_sub.location = (200, -350)
    links.new(transform_sub.outputs[0], set_mat_sub.inputs['Geometry'])

    # 4. 全体の結合とマージ
    join_final = nodes.new('GeometryNodeJoinGeometry')
    join_final.location = (650, 0)
    links.new(join_main_all.outputs[0], join_final.inputs['Geometry'])
    links.new(set_mat_sub.outputs[0], join_final.inputs['Geometry'])

    merge_final = nodes.new('GeometryNodeMergeByDistance')
    merge_final.inputs['Distance'].default_value = 0.005
    merge_final.location = (850, 0)
    links.new(join_final.outputs[0], merge_final.inputs['Geometry'])
    links.new(merge_final.outputs[0], node_out.inputs[0])

    return gn_mod


# オペレータ スプライン道路生成
class MYADDON_OT_create_road_along_spline(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_create_road_along_spline"
    bl_label = "スプライン道路生成"
    bl_description = "スプライン曲線に沿って道路メッシュを生成します（アスファルト・砂利道・砂道選択可）"
    bl_options = {'REGISTER', 'UNDO'}

    road_type: bpy.props.EnumProperty(  # type: ignore
        name="道路タイプ",
        description="道路の路面種類（アスファルト、砂利道、砂道）",
        items=[
            ('ASPHALT', 'アスファルト（舗装・白線あり）', '通常の舗装道路（車線マーキングあり）'),
            ('GRAVEL', '砂利道（未舗装・小石）', '小石・砂利が混ざった未舗装路（白線なし）'),
            ('SAND_DIRT', '砂道（未舗装・ダート）', '砂や土のダート道（白線なし）'),
        ],
        default='ASPHALT',
    )

    lane_count: bpy.props.IntProperty(  # type: ignore
        name="車線数",
        description="道路の車線数（幅は 車線数×車線幅 で決まります）",
        default=2,
        min=1,
        max=6,
    )

    lane_width: bpy.props.FloatProperty(  # type: ignore
        name="車線幅",
        description="1車線あたりの幅",
        default=1.0,
        min=0.3,
    )

    line_width: bpy.props.FloatProperty(  # type: ignore
        name="線の幅",
        description="車線マーキングの幅",
        default=0.08,
        min=0.02,
        max=0.3,
    )

    def execute(self, context):
        # 1. POLY曲線の作成
        curve_data = bpy.data.curves.new("RoadPath", 'CURVE')
        curve_data.dimensions = '3D'
        curve_data.twist_mode = 'Z_UP'

        spline = curve_data.splines.new('POLY')
        spline.points.add(1)
        spline.points[0].co = (0.0, 0.0, 0.0, 1.0)
        spline.points[1].co = (4.0, 0.0, 0.0, 1.0)

        curve_obj = bpy.data.objects.new("RoadPath", curve_data)
        context.collection.objects.link(curve_obj)
        context.view_layer.objects.active = curve_obj
        curve_obj.select_set(True)

        # 2. Geometry Nodesで道路メッシュを構築
        setup_road_geometry_nodes(
            curve_obj=curve_obj,
            road_type=self.road_type,
            lane_count=self.lane_count,
            lane_width=self.lane_width,
            line_width=self.line_width
        )

        context.view_layer.objects.active = curve_obj
        curve_obj.select_set(True)

        print(f"スプライン道路を生成しました（タイプ: {self.road_type}）。")
        return {'FINISHED'}


# オペレータ 交差点を追加
class MYADDON_OT_add_road_intersection(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_add_road_intersection"
    bl_label = "交差点を追加"
    bl_description = "選択した制御点から分岐道路を追加します（十字路/T字路/Y字路）"
    bl_options = {'REGISTER', 'UNDO'}

    intersection_type: bpy.props.EnumProperty(  # type: ignore
        name="交差点タイプ",
        description="追加する交差点の種類を選択します",
        items=[
            ('CROSS', '十字路', '左右に道路を追加（+型）'),
            ('T_RIGHT', 'T字路（右）', '右方向に道路を追加'),
            ('T_LEFT', 'T字路（左）', '左方向に道路を追加'),
            ('Y', 'Y字路', '指定角度で左右に分岐'),
        ],
        default='T_RIGHT',
    )

    branch_length: bpy.props.FloatProperty(  # type: ignore
        name="分岐の長さ",
        description="分岐道路の長さ",
        default=4.0,
        min=0.5,
    )

    branch_angle: bpy.props.FloatProperty(  # type: ignore
        name="分岐角度",
        description="Y字路の分岐角度（度）",
        default=45.0,
        min=5.0,
        max=85.0,
    )

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj is None or obj.type != 'CURVE':
            return False
        if obj.mode != 'EDIT':
            return False
        return True

    def execute(self, context):
        obj = context.active_object
        curve_data = obj.data

        # Edit Mode → Object Mode に一時的に切り替えて選択状態を確定させる
        bpy.ops.object.mode_set(mode='OBJECT')

        # 選択中の制御点を探す
        selected_point = None
        selected_spline = None
        selected_index = None

        for spline in curve_data.splines:
            points = spline.bezier_points if spline.type == 'BEZIER' else spline.points
            for i, pt in enumerate(points):
                if pt.select:
                    if selected_point is not None:
                        # 複数選択されている場合はエラー
                        bpy.ops.object.mode_set(mode='EDIT')
                        self.report({'WARNING'}, "制御点を1つだけ選択してください")
                        return {'CANCELLED'}
                    selected_point = pt
                    selected_spline = spline
                    selected_index = i

        if selected_point is None:
            bpy.ops.object.mode_set(mode='EDIT')
            self.report({'WARNING'}, "分岐元の制御点を1つ選択してください")
            return {'CANCELLED'}

        # 選択点の座標を取得（POLYは4D: x,y,z,w）
        if selected_spline.type == 'POLY':
            origin = mathutils.Vector(selected_point.co[:3])
        else:
            origin = mathutils.Vector(selected_point.co)

        # ワールド座標に変換
        origin = obj.matrix_world @ origin

        # 道路の方向ベクトルを前後の制御点から算出
        points = selected_spline.bezier_points if selected_spline.type == 'BEZIER' else selected_spline.points
        num_points = len(points)

        if num_points < 2:
            bpy.ops.object.mode_set(mode='EDIT')
            self.report({'WARNING'}, "スプラインに制御点が2つ以上必要です")
            return {'CANCELLED'}

        # 前後の点から方向を決める
        if selected_index == 0:
            # 始点：次の点への方向
            next_pt = points[1]
            next_co = mathutils.Vector(next_pt.co[:3]) if selected_spline.type == 'POLY' else mathutils.Vector(next_pt.co)
            next_co = obj.matrix_world @ next_co
            tangent = (next_co - origin).normalized()
        elif selected_index == num_points - 1:
            # 終点：前の点からの方向
            prev_pt = points[selected_index - 1]
            prev_co = mathutils.Vector(prev_pt.co[:3]) if selected_spline.type == 'POLY' else mathutils.Vector(prev_pt.co)
            prev_co = obj.matrix_world @ prev_co
            tangent = (origin - prev_co).normalized()
        else:
            # 中間点：前後の平均方向
            prev_pt = points[selected_index - 1]
            next_pt = points[selected_index + 1]
            prev_co = mathutils.Vector(prev_pt.co[:3]) if selected_spline.type == 'POLY' else mathutils.Vector(prev_pt.co)
            next_co = mathutils.Vector(next_pt.co[:3]) if selected_spline.type == 'POLY' else mathutils.Vector(next_pt.co)
            prev_co = obj.matrix_world @ prev_co
            next_co = obj.matrix_world @ next_co
            tangent = (next_co - prev_co).normalized()

        # 道路の右方向（Z-Up前提で外積）
        up = mathutils.Vector((0.0, 0.0, 1.0))
        right = tangent.cross(up).normalized()
        # tangentが真上を向いている場合のフォールバック
        if right.length < 0.001:
            up = mathutils.Vector((0.0, 1.0, 0.0))
            right = tangent.cross(up).normalized()

        left = -right

        # ローカル座標に戻すための逆行列
        inv_matrix = obj.matrix_world.inverted()

        # 分岐方向を計算してスプラインを追加
        branches = []  # (方向ベクトル, ) のリスト

        if self.intersection_type == 'CROSS':
            # 十字路：左右に1本ずつ
            branches.append(right)
            branches.append(left)
        elif self.intersection_type == 'T_RIGHT':
            # T字路（右）
            branches.append(right)
        elif self.intersection_type == 'T_LEFT':
            # T字路（左）
            branches.append(left)
        elif self.intersection_type == 'Y':
            # Y字路：tangent方向から左右に分岐
            angle_rad = math.radians(self.branch_angle)
            # Z軸周りの回転（2D平面想定）
            rot_right = mathutils.Matrix.Rotation(-angle_rad, 3, 'Z')
            rot_left = mathutils.Matrix.Rotation(angle_rad, 3, 'Z')
            branches.append((rot_right @ tangent).normalized())
            branches.append((rot_left @ tangent).normalized())

        # ローカル座標での分岐元
        local_origin = inv_matrix @ origin

        for direction in branches:
            # 分岐先の座標（ワールド→ローカル）
            end_world = origin + direction * self.branch_length
            local_end = inv_matrix @ end_world

            # 新しいスプラインを追加
            new_spline = curve_data.splines.new('POLY')
            new_spline.points.add(1)  # デフォルト1点 + 追加1点 = 計2点

            # 始点（分岐元）：radius=0 でフィレットを無効化 → 交差点が確実に接合
            new_spline.points[0].co = (local_origin.x, local_origin.y, local_origin.z, 1.0)
            new_spline.points[0].radius = 0.0

            # 終点（分岐先）：通常の radius=1.0
            new_spline.points[1].co = (local_end.x, local_end.y, local_end.z, 1.0)
            new_spline.points[1].radius = 1.0

        # 分岐元の制御点も radius=0 にする（元スプライン側のフィレットも無効化）
        selected_point.radius = 0.0

        # Edit Mode に戻す
        bpy.ops.object.mode_set(mode='EDIT')

        branch_count = len(branches)
        self.report({'INFO'}, f"交差点を追加しました（分岐{branch_count}本）")
        print(f"交差点を追加しました: {self.intersection_type}, 分岐{branch_count}本")
        return {'FINISHED'}
