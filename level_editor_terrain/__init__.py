# -*- coding: utf-8 -*-
import bpy

from .create_terrain import MYADDON_OT_create_terrain, MYADDON_OT_create_mountain_along_spline, MYADDON_OT_create_valley_along_spline
from .ai_terrain import MYADDON_OT_ai_generate_terrain
from .menu import TOPBAR_MT_terrain_menu

bl_info = {
    "name": "レベルエディタ (Terrain)",
    "author": "Daiki Takanaga",
    "version": (1, 0),
    "blender": (4, 5, 7),
    "location": "",
    "description": "地形・山・谷の生成およびAI地形生成",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Object"
}

classes = [
    TOPBAR_MT_terrain_menu,
    MYADDON_OT_create_terrain,
    MYADDON_OT_create_mountain_along_spline,
    MYADDON_OT_create_valley_along_spline,
    MYADDON_OT_ai_generate_terrain
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_editor_menus.append(TOPBAR_MT_terrain_menu.submenu)
    print("レベルエディタ(Terrain)が有効化されました。")

def unregister():
    bpy.types.TOPBAR_MT_editor_menus.remove(TOPBAR_MT_terrain_menu.submenu)
    for cls in classes:
        bpy.utils.unregister_class(cls)
    print("レベルエディタ(Terrain)が無効化されました。")
    
if __name__ == "__main__":
    register()
