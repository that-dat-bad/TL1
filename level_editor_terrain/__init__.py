# -*- coding: utf-8 -*-
import bpy

from .create_terrain import MYADDON_OT_create_terrain, MYADDON_OT_create_mountain_along_spline, MYADDON_OT_create_valley_along_spline
from .ai_terrain import MYADDON_OT_ai_generate_terrain
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
