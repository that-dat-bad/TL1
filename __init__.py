# -*- coding: utf-8 -*-
from bl_ui import properties_object
from bl_ui import properties_object
from bl_ui import properties_object
import contextlib
import contextlib
import bpy  # type: ignore
import bpy_extras
import sys
import io
import os
import math
import gpu
import gpu_extras.batch
import copy
import mathutils
import json

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


# オペレータ シーン出力
class MYADDON_OT_export_scene(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    bl_idname = "myaddon.myaddon_ot_export_scene"
    bl_label = "シーン出力"
    bl_description = "シーン情報をエクスポートします"
    filename_ext = ".json"

    def execute(self, context):
        print("シーン情報をexportします")
        self.export_json()
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

    def parse_scene_recursive_json(self,data_parent,object,level):
        #シーンのオブジェクト一個分のjsonオブジェクト生成
        json_object = dict()
        #オブジェクト種類
        json_object["type"] = object.type
        #オブジェクト名
        json_object["name"] = object.name
        
        #オブジェクトのローカルトランスフォームから
        #平行移動、回転、スケールを抽出
        trans , rot , scale =object.matrix_local.decompose()
        #回転を Quaternion から Euler （3軸での回転角）に変換
        rot = rot.to_euler()
        # ラジアンから度数法に変換
        rot.x = math.degrees(rot.x)
        rot.y = math.degrees(rot.y)
        rot.z = math.degrees(rot.z)

        #トランスフォーム情報をディクショナリに登録
        transform=dict()
        transform["location"] = [trans.x,trans.y,trans.z]
        transform["rotation"] = [rot.x,rot.y,rot.z]
        transform["scale"] = [scale.x,scale.y,scale.z]
        #まとめて一個分のjsonオブジェクトに登録
        json_object["transform"]=transform
        
        #カスタムプロパティ'file_name'
        if "file_name" in object:
            json_object["file_name"] = object["file_name"]
        
        #カスタムプロパティ'collider'
        if "collider" in object:
            collider=dict()
            collider["type"] = object["collider"]
            collider["center"]=object["collider_center"].to_list()
            collider["size"]=object["collider_size"].to_list()
            json_object["collider"]=collider



        #一個分のjsonオブジェクトを親オブジェクトに登録
        data_parent.append(json_object)

        #子ノードがあれば
        if len(object.children) >0:
            #子ノードリストを作成
            json_object["children"]=list()
            #子ノードへ進む
            for child in object.children:
                self.parse_scene_recursive_json(json_object["children"],child,level+1)

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
    
    def export_json(self):
        """JSON形式でファイルに出力"""

        #保存する情報をまとめるdict
        json_object_root=dict()

        #ノード名
        json_object_root["name"] = "scene"
        #オブジェクトリストを作成
        json_object_root["objects"]=list()
        
        #シーン内の全オブジェクトについて
        for object in bpy.context.scene.objects:
            #親オブジェクトがあるものはスキップ(代わりに親から呼び出すから)
            if (object.parent):
                continue

            # シーン直下のオブジェクトをルートノード（深さ0）とし、再帰関数で走査
            self.parse_scene_recursive_json(json_object_root["objects"], object, 0)

        #オブジェクトをJSON文字列にエンコード
        json_text =json.dumps(json_object_root,ensure_ascii=False,cls=json.JSONEncoder,indent=4)
        #コンソールに表示してみる
        print(json_text)

        #ファイルをテキスト形式で書き出し用にオープン
        #スコープを抜けると自動的にクローズされる
        with open(self.filepath, "wt",encoding="utf-8") as file:
            #ファイルに文字列を書き込む
            file.write(json_text)

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

class MYADDON_OT_add_collider(bpy.types.Operator):
    bl_idname="myaddon.myaddon_ot_add_collider"
    bl_label="コライダー追加"
    bl_description ="['collider']カスタムプロパティを追加します"
    bl_options={"REGISTER","UNDO"}

    def execute(self,context):

        #['collider']カスタムプロパティを追加
        context.object["collider"]="BOX"
        context.object["collider_center"]=mathutils.Vector((0,0,0))
        context.object["collider_size"]=mathutils.Vector((2,2,2))       

        return{"FINISHED"}

class OBJECT_PT_collider(bpy.types.Panel):
    """
    コライダーのカスタムプロパティパネル
    """
    bl_idname = "OBJECT_PT_collider"
    bl_label = "Collider"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    # サブメニューの描画
    def draw(self, context):

        # パネルに項目を追加
        if "collider" in context.object:
            # すでにプロパティがあれば、プロパティを表示
            self.layout.prop(context.object, '["collider"]', text="Type")
            self.layout.prop(context.object, '["collider_center"]', text="Center")
            self.layout.prop(context.object, '["collider_size"]', text="Size")
        else:
            # プロパティがなければ、プロパティ追加ボタンを表示
            self.layout.operator(MYADDON_OT_add_collider.bl_idname)

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
        for object in bpy.context.scene.objects:
            #コライダーがなければ描画をスキップ
            if not "collider" in object:
                continue
            
            #中心点、サイズの変数を宣言
            center = mathutils. Vector((0,0,0))
            size = mathutils. Vector((2,2,2))
            #プロパティから値を取得
            center[0]=object["collider_center"][0]
            center[1]=object["collider_center"] [1]
            center[2]=object["collider_center"] [2]
            size[0]=object["collider_size"][0]
            size[1]=object["collider_size"][1]
            size[2]=object["collider_size"] [2]
            #追加前の頂点数
            start = len(vertices['pos'])

            #Boxの8頂点分回す
            for offset in offsets:
                #オブジェクトの中心座標とスケールをコピー
                pos =copy.copy(center)
                size = copy.copy(size)
                # オフセットを適用
                pos[0]+=offset[0]*size[0]
                pos[1]+=offset[1]*size[1]
                pos[2]+=offset[2]*size[2]
                #ローカル座標からワールド座標に変換
                pos = object.matrix_world @ pos
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
    OBJECT_PT_file_name,
    MYADDON_OT_add_collider,
    OBJECT_PT_collider
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