# -*- coding: utf-8 -*-
import bpy

from .create_road import MYADDON_OT_create_road_along_spline, MYADDON_OT_add_road_intersection
from .create_building import MYADDON_OT_create_building
from .menu import TOPBAR_MT_city_menu

bl_info = {
    "name": "レベルエディタ (City)",
    "author": "Daiki Takanaga",
    "version": (1, 0),
    "blender": (4, 5, 7),
    "location": "",
    "description": "都市・道路・建物の生成",
    "warning": "",
    "wiki_url": "",
    "tracker_url": "",
    "category": "Object"
}

classes = [
    TOPBAR_MT_city_menu,
    MYADDON_OT_create_road_along_spline,
    MYADDON_OT_add_road_intersection,
    MYADDON_OT_create_building
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_editor_menus.append(TOPBAR_MT_city_menu.submenu)
    print("レベルエディタ(City)が有効化されました。")

def unregister():
    bpy.types.TOPBAR_MT_editor_menus.remove(TOPBAR_MT_city_menu.submenu)
    for cls in classes:
        bpy.utils.unregister_class(cls)
    print("レベルエディタ(City)が無効化されました。")
    
if __name__ == "__main__":
    register()
