import bpy
from .vertex_stretch import MYADDON_OT_strech_vertex
from .create_ico_sphere import MYADDON_OT_create_ico_sphere
from .create_building import MYADDON_OT_create_building
from .export_scene import MYADDON_OT_export_scene, MYADDON_OT_export_chunks
from .create_road import MYADDON_OT_create_road_along_spline, MYADDON_OT_add_road_intersection
from .create_terrain import MYADDON_OT_create_terrain, MYADDON_OT_create_mountain_along_spline, MYADDON_OT_create_valley_along_spline

# トップバーの拡張メニュー
class TOPBAR_MT_my_menu(bpy.types.Menu):
    bl_idname = "TOPBAR_MT_my_menu"
    bl_label = "MyMenu"
    bl_description = "拡張メニュー by Daiki Takanaga"
    
    def draw(self, context):
        self.layout.operator("wm.url_open_preset", text="Manual", icon='HELP')
        self.layout.separator()
        self.layout.operator(MYADDON_OT_strech_vertex.bl_idname, text=MYADDON_OT_strech_vertex.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_create_ico_sphere.bl_idname, text=MYADDON_OT_create_ico_sphere.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_create_building.bl_idname, text=MYADDON_OT_create_building.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_export_scene.bl_idname, text=MYADDON_OT_export_scene.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_export_chunks.bl_idname, text=MYADDON_OT_export_chunks.bl_label)

    def submenu(self, context):
        self.layout.menu(TOPBAR_MT_my_menu.bl_idname)

#トップバーの拡張メニュー(地形生成)
class TOPBAR_MT_terrain(bpy.types.Menu):
    bl_idname = "TOPBAR_MT_terrain"
    bl_label = "地形生成"
    bl_description = "地形生成メニュー"

    def draw(self, context):
        self.layout.operator(MYADDON_OT_create_road_along_spline.bl_idname, text=MYADDON_OT_create_road_along_spline.bl_label)
        self.layout.operator(MYADDON_OT_add_road_intersection.bl_idname, text=MYADDON_OT_add_road_intersection.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_create_terrain.bl_idname, text=MYADDON_OT_create_terrain.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_create_mountain_along_spline.bl_idname, text=MYADDON_OT_create_mountain_along_spline.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_create_valley_along_spline.bl_idname, text=MYADDON_OT_create_valley_along_spline.bl_label)
        self.layout.separator()
        from .ai_terrain import MYADDON_OT_ai_generate_terrain
        self.layout.operator(MYADDON_OT_ai_generate_terrain.bl_idname, text=MYADDON_OT_ai_generate_terrain.bl_label)

    def submenu(self, context):
        self.layout.menu(TOPBAR_MT_terrain.bl_idname)
