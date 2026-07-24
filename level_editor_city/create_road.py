import bpy
import mathutils
import math

# オペレータ スプライン道路生成
class MYADDON_OT_create_road_along_spline(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_create_road_along_spline"
    bl_label = "スプライン道路生成"
    bl_description = "スプライン曲線に沿って道路メッシュを生成します"
    bl_options = {'REGISTER', 'UNDO'}

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
        total_width = self.lane_count * self.lane_width

        # マテリアルの作成（既存があれば再利用）
        mat_road = bpy.data.materials.get("Road_Asphalt")
        if mat_road is None:
            mat_road = bpy.data.materials.new("Road_Asphalt")
            mat_road.use_nodes = True
            mat_road.diffuse_color = (0.12, 0.12, 0.12, 1.0)  # Solidモード用
            bsdf = mat_road.node_tree.nodes.get("Principled BSDF")
            if bsdf is None:  # Blenderバージョン互換フォールバック
                for node in mat_road.node_tree.nodes:
                    if node.type == 'BSDF_PRINCIPLED':
                        bsdf = node
                        break
            if bsdf:
                bsdf.inputs["Base Color"].default_value = (0.12, 0.12, 0.12, 1.0)
                bsdf.inputs["Roughness"].default_value = 0.85

        mat_line = bpy.data.materials.get("Road_LaneLine")
        if mat_line is None:
            mat_line = bpy.data.materials.new("Road_LaneLine")
            mat_line.use_nodes = True
            mat_line.diffuse_color = (0.95, 0.95, 0.95, 1.0)  # Solidモード用
            bsdf = mat_line.node_tree.nodes.get("Principled BSDF")
            if bsdf is None:
                for node in mat_line.node_tree.nodes:
                    if node.type == 'BSDF_PRINCIPLED':
                        bsdf = node
                        break
            if bsdf:
                bsdf.inputs["Base Color"].default_value = (0.95, 0.95, 0.95, 1.0)
                bsdf.inputs["Roughness"].default_value = 0.5

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

        # マテリアルスロットに追加
        curve_obj.data.materials.append(mat_road)
        curve_obj.data.materials.append(mat_line)
        
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
        base_radius.outputs[0].default_value = total_width * 1.0
        
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
        profile_line.inputs['Start'].default_value = (total_width / 2.0, 0, 0)
        profile_line.inputs['End'].default_value = (-total_width / 2.0, 0, 0)

        links.new(set_radius.outputs[0], curve_to_mesh.inputs['Curve'])
        links.new(profile_line.outputs[0], curve_to_mesh.inputs['Profile Curve'])

        # 道路面にマテリアルを割り当て
        set_mat_road = nodes.new('GeometryNodeSetMaterial')
        set_mat_road.inputs['Material'].default_value = mat_road
        links.new(curve_to_mesh.outputs[0], set_mat_road.inputs['Geometry'])

        # ── 車線マーキング ──
        line_w = self.line_width
        z_up = 0.005  # 道路面からの微小オフセット（Z-fighting防止）

        # マーキング位置を計算
        marking_positions = []
        # 端線（道路の両端、少し内側）
        marking_positions.append(-total_width / 2.0 + line_w / 2.0)
        marking_positions.append( total_width / 2.0 - line_w / 2.0)
        # 車線区分線（車線間の区切り）
        for i in range(1, self.lane_count):
            marking_positions.append(-total_width / 2.0 + i * self.lane_width)

        # 各マーキング位置にラインプロファイルを作成して結合
        join_profiles = nodes.new('GeometryNodeJoinGeometry')
        for pos in marking_positions:
            ln = nodes.new('GeometryNodeCurvePrimitiveLine')
            ln.inputs['Start'].default_value = (pos + line_w / 2.0, 0, 0)
            ln.inputs['End'].default_value   = (pos - line_w / 2.0, 0, 0)
            links.new(ln.outputs[0], join_profiles.inputs['Geometry'])

        # 車線マーキングメッシュを生成
        curve_to_mesh_lines = nodes.new('GeometryNodeCurveToMesh')
        links.new(set_radius.outputs[0], curve_to_mesh_lines.inputs['Curve'])
        links.new(join_profiles.outputs[0], curve_to_mesh_lines.inputs['Profile Curve'])

        # マーキングをZ+方向に直接移動（オフセットの確実な適用）
        transform_lines = nodes.new('GeometryNodeTransform')
        transform_lines.inputs['Translation'].default_value = (0, 0, z_up)
        links.new(curve_to_mesh_lines.outputs[0], transform_lines.inputs['Geometry'])

        # マーキングにマテリアルを割り当て
        set_mat_line = nodes.new('GeometryNodeSetMaterial')
        set_mat_line.inputs['Material'].default_value = mat_line
        links.new(transform_lines.outputs[0], set_mat_line.inputs['Geometry'])

        # 道路面とマーキングを結合
        join_all = nodes.new('GeometryNodeJoinGeometry')
        links.new(set_mat_road.outputs[0], join_all.inputs['Geometry'])
        links.new(set_mat_line.outputs[0], join_all.inputs['Geometry'])

        # 重なった頂点を自動マージ（角・分岐点のZ-fighting軽減）
        merge = nodes.new('GeometryNodeMergeByDistance')
        merge.inputs['Distance'].default_value = 0.001

        links.new(join_all.outputs[0], merge.inputs['Geometry'])
        links.new(merge.outputs[0], node_out.inputs[0])
        
        # アクティブオブジェクトをメインのカーブに戻す
        context.view_layer.objects.active = curve_obj
        curve_obj.select_set(True)

        print("スプライン道路を生成しました。")
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
