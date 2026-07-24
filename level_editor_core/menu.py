import bpy
from .export_scene import MYADDON_OT_export_scene, MYADDON_OT_export_chunks

class TOPBAR_MT_core_menu(bpy.types.Menu):
    bl_idname = "TOPBAR_MT_core_menu"
    bl_label = "レベルエディタ(Core)"
    bl_description = "レベルエディタ基本メニュー"
    
    def draw(self, context):
        self.layout.operator("wm.url_open_preset", text="Manual", icon='HELP')
        self.layout.separator()
        self.layout.operator(MYADDON_OT_export_scene.bl_idname, text=MYADDON_OT_export_scene.bl_label)
        self.layout.separator()
        self.layout.operator(MYADDON_OT_export_chunks.bl_idname, text=MYADDON_OT_export_chunks.bl_label)

    def submenu(self, context):
        self.layout.menu(TOPBAR_MT_core_menu.bl_idname)
