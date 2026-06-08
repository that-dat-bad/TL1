# -*- coding: utf-8 -*-
import bpy  # type: ignore
import sys
import io
import os
import math
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

#ブレンダーに登録するアドオン情報
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

#トップバーの拡張メニュー
class TOPBAR_MT_my_menu(bpy.types.Menu):
    #Blenderがクラスを識別するための固有の文字列
    bl_idname = "TOPBAR_MT_my_menu"
    #メニューのラベル
    bl_label = "MyMenu"
    #著者表示用の文字列
    bl_description = "閣僚メニュー by" + bl_info["author"]
    
    #サブメニューの描画
    def draw(self, context):
       
       self.layout.operator("wm.url_open_preset", text="Manual", icon='HELP')
        
        # セパレーター(横線)
       self.layout.separator()

       self.layout.operator(MYADDON_OT_strech_vertex.bl_idname, text=MYADDON_OT_strech_vertex.bl_label)
       
       self.layout.separator()

       self.layout.operator(MYADDON_OT_create_ico_sphere.bl_idname, text=MYADDON_OT_create_ico_sphere.bl_label)

       self.layout.separator()

       self.layout.operator(MYADDON_OT_export_scene.bl_idname, text=MYADDON_OT_export_scene.bl_label)

    #既存のメニューにサブメニューを追加
    def submenu(self, context):
       
       self.layout.menu(TOPBAR_MT_my_menu.bl_idname)



#オペレータ 頂点を伸ばす
class MYADDON_OT_strech_vertex(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_strech_vertex"
    bl_label = "頂点を伸ばす"
    bl_description = "選択した頂点を引っ張って伸ばします"
    # redo undo可能オプション
    bl_options = {'REGISTER', 'UNDO'}

    #メニューを実行したときに呼ばれるコールバック関数
    def execute(self, context):
        bpy.data.objects['Cube'].data.vertices[0].co.x += 1.0
        print("頂点を伸ばしました。")

        #オペレーターの命令終了を通知
        return {'FINISHED'}

#オペレータ ICO球生成
class MYADDON_OT_create_ico_sphere(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_create_object"
    bl_label = "ICO球生成"
    bl_description = "ICO球を生成します"
    # redo undo可能オプション
    bl_options = {'REGISTER', 'UNDO'}

    #メニューを実行したときに呼ばれるコールバック関数
    def execute(self, context):
        bpy.ops.mesh.primitive_ico_sphere_add()
        print("ICO球を生成しました。")

        #オペレーターの命令終了を通知
        return {'FINISHED'}

#オペレータ シーン出力
class MYADDON_OT_export_scene(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_export_scene"
    bl_label = "シーン出力"
    bl_description = "シーン情報をエクスポートします"
   

    def execute(self, context):
        print("シーン情報をexportします")

        #シーン内の全オブジェクトについて
        for object in bpy.context.scene.objects:
            print(object.type + " - " + object.name)
            #ローカルトランスフォーム行列から平行移動、回転、スケーリングを抽出
            #型は Vector, Quaternion, Vector
            trans, rot, scale = object.matrix_local.decompose()
            #回転を Quaternion から Euler（3軸での回転角）に変換
            rot = rot.to_euler()
            #ラジアンから度数法に変換
            rot.x = math.degrees(rot.x)
            rot.y = math.degrees(rot.y)
            rot.z = math.degrees(rot.z)
            #トランスフォーム情報を表示
            print("Trans(%f,%f,%f)" % (trans.x, trans.y, trans.z) )
            print("Rot(%f,%f,%f)" % (rot.x, rot.y, rot.z) )
            print("Scale(%f,%f,%f)" % (scale.x, scale.y, scale.z) )
            #親オブジェクトの名前を表示
            if object.parent:
                print("Parent:" + object.parent.name)
            print()

        print("シーン情報をexportしました")
        self.report({'INFO'}, "シーン情報をexportしました")
        
        #オペレーターの命令終了を通知
        return {'FINISHED'}

#メニュー項目描画
def draw_menu_manual(self,context):
    #self : 呼び出し元のクラスインスタンス C++でいうthis
    #context : カーソルを合わせたときのポップアップのカスタマイズなどに使用

    #トップバーのエディタメニューに項目を追加
    self.layout.operator("wm.url_open_preset",text ="Manual", icon ='HELP')



#ブレンダに登録するクラスリスト
classes = [
    TOPBAR_MT_my_menu,
    MYADDON_OT_strech_vertex,
    MYADDON_OT_create_ico_sphere,
    MYADDON_OT_export_scene
]


#Add-On有効化時コールバック
def register():
    #blenderにクラスを登録
    for cls in classes:
        bpy.utils.register_class(cls)
    #メニューに項目を追加
    bpy.types.TOPBAR_MT_editor_menus.append(TOPBAR_MT_my_menu.submenu)
    print("レベルエディタが有効化されました。")


#Add-On無効化時コールバック
def unregister():
    #メニューから項目を削除
    bpy.types.TOPBAR_MT_editor_menus.remove(TOPBAR_MT_my_menu.submenu)
    #blenderからクラスを削除
    for cls in classes:
        bpy.utils.unregister_class(cls)
    print("レベルエディタが無効化されました。")
    
#テスト実行用
if __name__ == "__main__":
    register()


