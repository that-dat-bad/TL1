# -*- coding: utf-8 -*-
import bpy  # type: ignore
import bpy_extras
import sys
import io
import os
import math
import gpu
import gpu_extras.batch

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
        vertices ={"pos":[[0,0,0],[2,2,2]]}
        
        #インデックスデータ
        indices =[[0,1]]

        #ビルトインのシェーダーを取得
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")

        #バッチを作成
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