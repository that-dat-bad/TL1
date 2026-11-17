# -*- coding: utf-8 -*-
import importlib
import sys
import bpy

_SUBMODULES = (
    "blueprint_store",
    "terrain_materials",
    "terrain_blueprint",
    "heightmap_engine",
    "terrain_baker",
    "water_mesh_builder",
    "terrain_pipeline",
    "create_terrain",
    "ai_terrain",
    "mcp_server",
    "menu",
)
for _sub in _SUBMODULES:
    _full = f"{__name__}.{_sub}"
    if _full in sys.modules:
        importlib.reload(sys.modules[_full])

from .create_terrain import MYADDON_OT_create_terrain, MYADDON_OT_create_mountain_along_spline, MYADDON_OT_create_valley_along_spline
from .ai_terrain import MYADDON_OT_ai_generate_terrain, MYADDON_OT_rebuild_from_curves, VIEW3D_PT_tl1_terrain_sync
from .mcp_server import MYADDON_OT_start_mcp_server, MYADDON_OT_stop_mcp_server
from .menu import TOPBAR_MT_terrain_menu

bl_info = {
    "name": "レベルエディタ (Terrain)",
    "author": "Daiki Takanaga",
    "version": (1, 0),
    "blender": (4, 5, 7),
    "location": "",
    "description": "地形・山・谷の生成およびAI地形生成、MCP連携",
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
    MYADDON_OT_ai_generate_terrain,
    MYADDON_OT_rebuild_from_curves,
    VIEW3D_PT_tl1_terrain_sync,
    MYADDON_OT_start_mcp_server,
    MYADDON_OT_stop_mcp_server
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_editor_menus.append(TOPBAR_MT_terrain_menu.submenu)
    print("レベルエディタ(Terrain)が有効化されました。")

def unregister():
    # MCPサーバーが起動中なら停止する
    from . import mcp_server
    if mcp_server._mcp_server_instance is not None:
        mcp_server._mcp_server_instance.shutdown()
        mcp_server._mcp_server_instance = None
        mcp_server._mcp_server_thread = None
        # キューに残ったリクエストを解放
        import queue as _q
        try:
            while True:
                request = mcp_server._dispatch_queue.get_nowait()
                request.error = RuntimeError("Server shutting down")
                request.done.set()
        except _q.Empty:
            pass
        print("[MCP] アドオン無効化に伴いサーバーを停止しました")

    bpy.types.TOPBAR_MT_editor_menus.remove(TOPBAR_MT_terrain_menu.submenu)
    for cls in classes:
        bpy.utils.unregister_class(cls)
    print("レベルエディタ(Terrain)が無効化されました。")
    
if __name__ == "__main__":
    register()
