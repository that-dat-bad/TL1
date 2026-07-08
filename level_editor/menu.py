import bpy
from .vertex_stretch import MYADDON_OT_strech_vertex
from .create_ico_sphere import MYADDON_OT_create_ico_sphere
from .export_scene import MYADDON_OT_export_scene
from .create_road import MYADDON_OT_create_road_along_spline
from .create_terrain import MYADDON_OT_create_terrain

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
        self.layout.operator(MYADDON_OT_create_road_along_spline.bl_idname, text=MYADDON_OT_create_road_along_spline.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_create_terrain.bl_idname, text=MYADDON_OT_create_terrain.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_export_scene.bl_idname, text=MYADDON_OT_export_scene.bl_label)

    def submenu(self, context):
        self.layout.menu(TOPBAR_MT_my_menu.bl_idname)

