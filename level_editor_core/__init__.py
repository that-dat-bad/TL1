# -*- coding: utf-8 -*-
import bpy

from .export_scene import MYADDON_OT_export_scene, MYADDON_OT_export_chunks
from .collider import MYADDON_OT_add_collider, OBJECT_PT_collider, DrawCollider, register_draw_handler, unregister_draw_handler
from .file_name import MYADDON_OT_add_filename, OBJECT_PT_file_name
from .disabled import MYADDON_OT_disable_operator, OBJECT_PT_disabled
from .console_setup import setup_console_encoding
from .menu import TOPBAR_MT_core_menu

setup_console_encoding()

bl_info = {
    "name": "レベルエディタ (Core)",
    "author": "Daiki Takanaga",
    "version": (1, 0),
    "blender": (4, 5, 7),
    "location": "",
    "description": "レベル構築の基盤ツール群",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Object"
}

classes = [
    TOPBAR_MT_core_menu,
    MYADDON_OT_export_scene,
    MYADDON_OT_export_chunks,
    MYADDON_OT_add_filename,
    OBJECT_PT_file_name,
    MYADDON_OT_add_collider,
    OBJECT_PT_collider,
    MYADDON_OT_disable_operator,
    OBJECT_PT_disabled
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_editor_menus.append(TOPBAR_MT_core_menu.submenu)
    register_draw_handler()
    print("レベルエディタ(Core)が有効化されました。")

def unregister():
    bpy.types.TOPBAR_MT_editor_menus.remove(TOPBAR_MT_core_menu.submenu)
    unregister_draw_handler()
    for cls in classes:
        bpy.utils.unregister_class(cls)
    print("レベルエディタ(Core)が無効化されました。")
    
if __name__ == "__main__":
    register()
