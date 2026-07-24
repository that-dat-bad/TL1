import bpy
from .create_terrain import MYADDON_OT_create_terrain, MYADDON_OT_create_mountain_along_spline, MYADDON_OT_create_valley_along_spline
from .ai_terrain import MYADDON_OT_ai_generate_terrain

class TOPBAR_MT_terrain_menu(bpy.types.Menu):
    bl_idname = "TOPBAR_MT_terrain_menu"
    bl_label = "地形生成(Terrain)"
    bl_description = "地形生成メニュー"

    def draw(self, context):
        self.layout.operator(MYADDON_OT_create_terrain.bl_idname, text=MYADDON_OT_create_terrain.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_create_mountain_along_spline.bl_idname, text=MYADDON_OT_create_mountain_along_spline.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_create_valley_along_spline.bl_idname, text=MYADDON_OT_create_valley_along_spline.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_ai_generate_terrain.bl_idname, text=MYADDON_OT_ai_generate_terrain.bl_label)

    def submenu(self, context):
        self.layout.menu(TOPBAR_MT_terrain_menu.bl_idname)
