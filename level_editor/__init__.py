# -*- coding: utf-8 -*-
import bpy  # type: ignore

#分離モジュールのインポート
from .vertex_stretch import MYADDON_OT_strech_vertex
from .create_ico_sphere import MYADDON_OT_create_ico_sphere
from .export_scene import MYADDON_OT_export_scene
from .collider import MYADDON_OT_add_collider, OBJECT_PT_collider, DrawCollider, register_draw_handler, unregister_draw_handler
from .file_name import MYADDON_OT_add_filename, OBJECT_PT_file_name
from .create_road import MYADDON_OT_create_road_along_spline
from .create_terrain import MYADDON_OT_create_terrain
from .menu import TOPBAR_MT_my_menu
from .disabled import MYADDON_OT_disable_operator, OBJECT_PT_disabled
from .console_setup import setup_console_encoding


setup_console_encoding()# Windows文字化け対策（エンコード設定）を実行


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


# ブレンダに登録するクラスリスト
classes = [
    TOPBAR_MT_my_menu,#済み
    MYADDON_OT_strech_vertex,#済み
    MYADDON_OT_create_ico_sphere,#済み
    MYADDON_OT_create_road_along_spline,#済み
    MYADDON_OT_create_terrain,#済み
    MYADDON_OT_export_scene,#済み
    MYADDON_OT_add_filename,#済み
    OBJECT_PT_file_name,#済み
    MYADDON_OT_add_collider,#済み
    OBJECT_PT_collider,#済み
    MYADDON_OT_disable_operator,#済み
    OBJECT_PT_disabled#済み
]


# Add-On有効化時コールバック
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    #メニューに項目を追加
    bpy.types.TOPBAR_MT_editor_menus.append(TOPBAR_MT_my_menu.submenu)
    
    #描画ハンドルの登録
    register_draw_handler()
    
    print("レベルエディタが有効化されました。")


# Add-On無効化時コールバック
def unregister():
    bpy.types.TOPBAR_MT_editor_menus.remove(TOPBAR_MT_my_menu.submenu)
    #描画ハンドルの解除
    unregister_draw_handler()
    #blenderからクラスを削除
    for cls in classes:
        bpy.utils.unregister_class(cls)
    print("レベルエディタが無効化されました。")
    
# テスト実行用
if __name__ == "__main__":
    register()
