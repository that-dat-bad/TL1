# -*- coding: utf-8 -*-
import bpy  # type: ignore
import bpy_extras
import sys
import io
import os
import math
import gpu
import gpu_extras.batch
import copy

# Blenderのコンソール出力をUTF-8に設定（Windows文字化け対策）
os.environ['PYTHONIOENCODING'] = 'utf-8'

if sys.platform == 'win32':
    try:
        import ctypes
        # Windowsコンソールの出力コードページをUTF-8(65001)に変更
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass

# stdout/stderrのエンコーディングをUTF-8に再設定
try:
    if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    elif sys.stdout and hasattr(sys.stdout, 'buffer'):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass
try:
    if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    elif sys.stderr and hasattr(sys.stderr, 'buffer'):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass

# ブレンダーに登録するアドオン情報
bl_info = {
    "name": "レベルエディタ",
    "author": "Daiki Takanaga",
    "version": (1, 0),
    "blender": (4, 5, 7),
    "location": "",
    "description": "レベルエディタ",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Object"
}

# トップバーの拡張メニュー
class TOPBAR_MT_my_menu(bpy.types.Menu):
    bl_idname = "TOPBAR_MT_my_menu"
    bl_label = "MyMenu"
    bl_description = "閣僚メニュー by" + bl_info["author"]
    
    def draw(self, context):
        self.layout.operator("wm.url_open_preset", text="Manual", icon='HELP')
        self.layout.separator()
        self.layout.operator(MYADDON_OT_strech_vertex.bl_idname, text=MYADDON_OT_strech_vertex.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_create_ico_sphere.bl_idname, text=MYADDON_OT_create_ico_sphere.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_create_road_along_spline.bl_idname, text=MYADDON_OT_create_road_along_spline.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_export_scene.bl_idname, text=MYADDON_OT_export_scene.bl_label)

    def submenu(self, context):
        self.layout.menu(TOPBAR_MT_my_menu.bl_idname)


# オペレータ 頂点を伸ばす
class MYADDON_OT_strech_vertex(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_strech_vertex"
    bl_label = "頂点を伸ばす"
    bl_description = "選択した頂点を引っ張って伸ばします"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.data.objects['Cube'].data.vertices[0].co.x += 1.0
        print("頂点を伸ばしました。")
        return {'FINISHED'}


# オペレータ ICO球生成
class MYADDON_OT_create_ico_sphere(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_create_object"
    bl_label = "ICO球生成"
    bl_description = "ICO球を生成します"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.ops.mesh.primitive_ico_sphere_add()
        print("ICO球を生成しました。")
        return {'FINISHED'}


# オペレータ スプライン道路生成
class MYADDON_OT_create_road_along_spline(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_create_road_along_spline"
    bl_label = "スプライン道路生成"
    bl_description = "スプライン曲線に沿って道路メッシュを生成します"
    bl_options = {'REGISTER', 'UNDO'}

    road_width: bpy.props.FloatProperty(
        name="道路の幅",
        description="道路メッシュの横幅を指定します",
        default=2.0,
        min=0.1,
    )

    def execute(self, context):
        # 1. 曲線の作成
        bpy.ops.curve.primitive_bezier_curve_add(enter_editmode=False, align='WORLD', location=(0, 0, 0), scale=(1, 1, 1))
        curve_obj = context.active_object
        curve_obj.name = "RoadPath"
        
        # 道路がねじれたり反転したりするのを防ぐため、Twist Modeを Z-Up に固定
        curve_obj.data.twist_mode = 'Z_UP'
        
        # メッシュが曲線の端からはみ出すのを防ぐため、伸縮（Stretch）と境界クランプ（Bounds Clamp）を有効化
        curve_obj.data.use_stretch = True
        curve_obj.data.use_deform_bounds = True
        
        # 曲線の原点を始点にぴったり合わせる（X=0から開始）
        spline = curve_obj.data.splines[0]
        spline.bezier_points[0].co = (0.0, 0.0, 0.0)
        spline.bezier_points[0].handle_left = (-1.0, 0.0, 0.0)
        spline.bezier_points[0].handle_right = (1.0, 0.0, 0.0)
        spline.bezier_points[1].co = (4.0, 0.0, 0.0)
        spline.bezier_points[1].handle_left = (3.0, 0.0, 0.0)
        spline.bezier_points[1].handle_right = (5.0, 0.0, 0.0)
        
        # 2. 道路メッシュ(Plane)の作成
        bpy.ops.mesh.primitive_plane_add(size=2.0, enter_editmode=False, align='WORLD', location=(0, 0, 0))
        mesh_obj = context.active_object
        mesh_obj.name = "RoadMesh"
        
        # メッシュの原点を端（X=0）に合わせるため、頂点自体をズラす
        for v in mesh_obj.data.vertices:
            v.co.x += 1.0 # -1.0~1.0 を 0.0~2.0 に移動
        
        # X軸方向に伸ばすため、Planeのスケールを調整
        mesh_obj.scale[0] = 0.5 # 長さ (進行方向: 1.0になる)
        mesh_obj.scale[1] = self.road_width / 2.0 # 幅
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

        # ※注意: ここでCurveを親にすると、Objectモードで回転・拡大した際にCurveモディファイアが二重にかかる
        # (Double Transform) 問題が発生してメッシュが飛んでいくため、親子付けは行いません。

        # 3. Arrayモディファイアの追加
        array_mod = mesh_obj.modifiers.new(name="Array", type='ARRAY')
        array_mod.fit_type = 'FIT_CURVE'
        array_mod.curve = curve_obj
        array_mod.use_relative_offset = True
        array_mod.relative_offset_displace[0] = 1.0
        # 道路の継ぎ目を滑らかにつなぐ（マージ）
        array_mod.use_merge_vertices = True
        # 編集モードでもモディファイアの結果を表示・編集ケージに適用
        array_mod.show_in_editmode = True
        array_mod.show_on_cage = True
        
        # 4. Curveモディファイアの追加
        curve_mod = mesh_obj.modifiers.new(name="Curve", type='CURVE')
        curve_mod.object = curve_obj
        curve_mod.deform_axis = 'POS_X'
        # 編集モードでもモディファイアの結果を表示・編集ケージに適用
        curve_mod.show_in_editmode = True
        curve_mod.show_on_cage = True

        print("スプライン道路を生成しました。")
        return {'FINISHED'}


# オペレータ シーン出力
class MYADDON_OT_export_scene(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    bl_idname = "myaddon.myaddon_ot_export_scene"
    bl_label = "シーン出力"
    bl_description = "シーン情報をエクスポートします"
    filename_ext = ".scene"

    def execute(self, context):
        print("シーン情報をexportします")
        self.export()
        print("シーン情報をexportしました")
        self.report({'INFO'}, "シーン情報をexportしました")
        return {'FINISHED'}

    def parse_scene_recursive(self, file, object, level):
        """シーン解析用再帰関数"""
        
        # 深さ分インデントする（タブを挿入）
        indent = ''
        for i in range(level):
            indent += "\t"

        # オブジェクト名書き込み
        self.write_and_print(file, indent + object.type + " - " + object.name)
        
        trans, rot, scale = object.matrix_local.decompose()
        # 回転を Quternion から Euler （3軸での回転角）に変換
        rot = rot.to_euler()
        # ラジアンから度数法に変換
        rot.x = math.degrees(rot.x)
        rot.y = math.degrees(rot.y)
        rot.z = math.degrees(rot.z)
        
        #トランスフォーム情報を表示
        self.write_and_print(file, indent + "T %f %f %f" % (trans.x, trans.y, trans.z) )
        self.write_and_print(file, indent + "R %f %f %f" % (rot.x, rot.y, rot.z) )
        self.write_and_print(file, indent + "S %f %f %f" % (scale.x, scale.y, scale.z) )
        #カスタムプロパティ 'file_name'
        if "file_name" in object:
            self.write_and_print(file, indent + "N %s" % object["file_name"])
        self.write_and_print(file, indent + 'END')
        self.write_and_print(file, '')

        # 子ノードへ進む（深さが1上がる）
        for child in object.children:
            self.parse_scene_recursive(file, child, level + 1)

    def export(self):
        """ファイル出力"""
        print("シーン情報をファイルに出力...%r" % self.filepath)

        # 保存先ディレクトリが存在しない場合は作成する
        dirname = os.path.dirname(self.filepath)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        # ファイルをテキスト形式で開く
        with open(self.filepath, 'w', encoding='utf-8') as file:
            file.write("SCENE\n")
            
            # シーン内の全オブジェクトについて
            for object in bpy.context.scene.objects:
                
                # 親オブジェクトがあるものはスキップ（代わりに親から呼び出すから）
                if (object.parent):
                    continue
                
                # シーン直下のオブジェクトをルートノード（深さ0）とし、再帰関数で走査
                self.parse_scene_recursive(file, object, 0)

    def write_and_print(self, file, text_str):
        print(text_str)
        file.write(text_str)
        file.write("\n")


class OBJECT_PT_file_name(bpy.types.Panel):
    """オブジェクトのファイルネームパネル"""
    bl_idname = "OBJECT_PT_file_name"
    bl_label = "FileName"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    #サブメニューの描画
    def draw(self, context):

        # パネルに項目を追加
        if "file_name" in context.object:
            #すでにプロパティがあれば、プロパティを表示
            self.layout.prop(context.object,'["file_name"]',text=self.bl_label)
        else:
            #プロパティがなければ、プロパティ追加ボタンを表示
            self.layout.operator(MYADDON_OT_add_filename.bl_idname)


class MYADDON_OT_add_filename(bpy.types.Operator):
    bl_idname="myaddon.myaddon_ot_add_filename"
    bl_label="FileName 追加"
    bl_description ="['file_name']カスタムプロパティを追加します"
    bl_options={"REGISTER","UNDO"}

    def execute(self,context):

        #['file_name']カスタムプロパティを追加
        context.object["file_name"]=""

        return{"FINISHED"}


#コライダー描画
class DrawCollider:
    #描画ハンドル
    handle =None

    #3Dビューに登録する描画関数
    def draw_collider():
        #頂点データ
        vertices ={"pos":[]}
        
        #インデックスデータ
        indices =[]

        #各頂点の、オブジェクト中心からのオフセット
        offsets =[
            [-0.5,-0.5,-0.5], #左下前
            [+0.5,-0.5,-0.5], #右下前
            [+0.5,+0.5,-0.5], #右上手前
            [-0.5,+0.5,-0.5], #左上手前
            [-0.5,-0.5,+0.5], #左下奥
            [+0.5,-0.5,+0.5], #右下奥
            [+0.5,+0.5,+0.5], #右上奥
            [-0.5,+0.5,+0.5], #左上手前
        ]

        #現在シーンのオブジェクトリストを走査
        for obj in bpy.context.scene.objects:
            #追加前の頂点数
            start = len(vertices['pos'])

            #Boxの8頂点分回す
            for offset in offsets:
                #オブジェクトの中心座標とスケールをコピー
                pos = [obj.location[0], obj.location[1], obj.location[2]]
                size = [obj.scale[0], obj.scale[1], obj.scale[2]]

                # オフセットを適用
                pos[0]+=offset[0]*size[0]
                pos[1]+=offset[1]*size[1]
                pos[2]+=offset[2]*size[2]
                
                #頂点データリストに座標を追加
                vertices['pos'].append(pos)
                
            #前面を構成する辺の頂点インデックス
            indices.append([start+0, start+1]) #下
            indices.append([start+2, start+3]) #上
            indices.append([start+0, start+3]) #左
            indices.append([start+1, start+2]) #右
            #奥面を構成する辺の頂点インデックス
            indices.append([start+4, start+5]) #下
            indices.append([start+6, start+7]) #上
            indices.append([start+4, start+7]) #左
            indices.append([start+5, start+6]) #右
            #手前と奥を繋ぐ辺の頂点インデックス
            indices.append([start+0, start+4])
            indices.append([start+1, start+5])
            indices.append([start+2, start+6])
            indices.append([start+3, start+7])

        #ビルトインのシェーダーを取得
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")

        #バッチを作成 (必ず頂点・インデックスを追加し終わってから作成する)
        batch = gpu_extras.batch.batch_for_shader(shader, "LINES", vertices, indices=indices)

        #描画
        shader.bind()
        shader.uniform_float("color", (0.5, 1.0, 1.0, 1.0)) 
        batch.draw(shader)


# メニュー項目描画
def draw_menu_manual(self, context):
    self.layout.operator("wm.url_open_preset", text="Manual", icon='HELP')


# ブレンダに登録するクラスリスト
classes = [
    TOPBAR_MT_my_menu,
    MYADDON_OT_strech_vertex,
    MYADDON_OT_create_ico_sphere,
    MYADDON_OT_create_road_along_spline,
    MYADDON_OT_export_scene,
    MYADDON_OT_add_filename,
    OBJECT_PT_file_name
]


# Add-On有効化時コールバック
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    #メニューに項目を追加
    bpy.types.TOPBAR_MT_editor_menus.append(TOPBAR_MT_my_menu.submenu)
    
    #描画ハンドルの登録
    DrawCollider.handle = bpy.types.SpaceView3D.draw_handler_add(DrawCollider.draw_collider, (), 'WINDOW', 'POST_VIEW')
    
    print("レベルエディタが有効化されました。")


# Add-On無効化時コールバック
def unregister():
    bpy.types.TOPBAR_MT_editor_menus.remove(TOPBAR_MT_my_menu.submenu)
    #描画ハンドルの解除
    if DrawCollider.handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(DrawCollider.handle, 'WINDOW')
    #blenderからクラスを削除
    for cls in classes:
        bpy.utils.unregister_class(cls)
    print("レベルエディタが無効化されました。")
    
# テスト実行用
if __name__ == "__main__":
    register()