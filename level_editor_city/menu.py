import bpy
from .create_road import MYADDON_OT_create_road_along_spline, MYADDON_OT_add_road_intersection
from .create_building import MYADDON_OT_create_building

class TOPBAR_MT_city_menu(bpy.types.Menu):
    bl_idname = "TOPBAR_MT_city_menu"
    bl_label = "都市・道路生成(City)"
    bl_description = "都市・道路生成メニュー"

    def draw(self, context):
        self.layout.operator(MYADDON_OT_create_road_along_spline.bl_idname, text=MYADDON_OT_create_road_along_spline.bl_label)
        self.layout.operator(MYADDON_OT_add_road_intersection.bl_idname, text=MYADDON_OT_add_road_intersection.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_create_building.bl_idname, text=MYADDON_OT_create_building.bl_label)

    def submenu(self, context):
        self.layout.menu(TOPBAR_MT_city_menu.bl_idname)
