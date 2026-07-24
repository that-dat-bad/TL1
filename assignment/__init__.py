# -*- coding: utf-8 -*-
import bpy

from .vertex_stretch import MYADDON_OT_strech_vertex
from .create_ico_sphere import MYADDON_OT_create_ico_sphere
from .menu import TOPBAR_MT_assignment_menu

bl_info = {
    "name": "課題ツール (Assignment)",
    "author": "Daiki Takanaga",
    "version": (1, 0),
    "blender": (4, 5, 7),
    "location": "",
    "description": "授業課題で作成したツール群",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Object"
}

classes = [
    TOPBAR_MT_assignment_menu,
    MYADDON_OT_strech_vertex,
    MYADDON_OT_create_ico_sphere
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_editor_menus.append(TOPBAR_MT_assignment_menu.submenu)
    print("課題ツールが有効化されました。")

def unregister():
    bpy.types.TOPBAR_MT_editor_menus.remove(TOPBAR_MT_assignment_menu.submenu)
    for cls in classes:
        bpy.utils.unregister_class(cls)
    print("課題ツールが無効化されました。")
    
if __name__ == "__main__":
    register()
