# -*- coding: utf-8 -*-
"""
レベルエディタ (Mission) - Blender 常駐アドオン エントリポイント
空のBlenderプロジェクト起動時はシーンを汚さず HTTP ライブ同期待機 (Port 8766) のみ開始し、
ゲーム (25B_GE_CG.exe) が起動してミッションに入った瞬間に全地形(100チャンク)と対象ミッションを自動展開します。
"""

bl_info = {
    "name": "レベルエディタ (Mission)",
    "author": "Daiki Takanaga",
    "version": (1, 0, 0),
    "blender": (3, 6, 0),
    "location": "Topbar > ミッション編集(Mission) / 3D Viewport Header / Properties",
    "description": (
        "空のBlenderを開いた後にゲームを起動すると、接続検知時に全地形(100チャンク)とミッションを自動展開するエディタ"
    ),
    "category": "Object",
}

from typing import Optional
import bpy
from bpy.app.handlers import persistent
from bpy.props import PointerProperty

from .constants import (
    LiveSyncDefaults,
    MathConstants,
)
from .live_sync_server import LiveSyncServerManager
from .operators import (
    MYADDON_OT_ClearTerrainChunks,
    MYADDON_OT_Configure40kmViewport,
    MYADDON_OT_EnsureZadanie00Markers,
    MYADDON_OT_EnterMissionEditorMode,
    MYADDON_OT_ExitMissionEditorMode,
    MYADDON_OT_ExportMissionJson,
    MYADDON_OT_GenerateWatchtowerChain,
    MYADDON_OT_ImportMissionFile,
    MYADDON_OT_LoadMission01,
    MYADDON_OT_LoadTerrainChunks,
    MYADDON_OT_LoadZadanie00,
    MYADDON_OT_NewStandardMission,
    MYADDON_OT_PushAndRestartGame,
    MYADDON_OT_PushLiveSyncNow,
    MYADDON_OT_RefreshProxyVisuals,
    MYADDON_OT_SnapSelectedToTerrain,
    MYADDON_OT_SpawnAirEnemy,
    MYADDON_OT_SpawnGroundEnemy,
    MYADDON_OT_SpawnObjectiveNode,
    MYADDON_OT_SpawnPlayerStart,
    MYADDON_OT_SpawnTriggerNode,
    MYADDON_OT_SpawnWatchtower,
    MYADDON_OT_SpawnWaypointRoute,
    MYADDON_OT_StartLiveSync,
    MYADDON_OT_StopLiveSync,
    WorkspaceModeHelper,
)
from .properties import MISSION_Settings, MISSION_ObjectProps, RepoPathResolver
from .ui_panel import (
    OBJECT_PT_mission_control,
    OBJECT_PT_mission_selected_inspector,
    SCENE_PT_mission_control,
    TOPBAR_MT_mission_menu,
    VIEW3D_MT_mission_add_submenu,
    draw_view3d_header_toolbar,
)

CLASSES = (
    MISSION_Settings,
    MISSION_ObjectProps,
    MYADDON_OT_EnterMissionEditorMode,
    MYADDON_OT_ExitMissionEditorMode,
    MYADDON_OT_LoadZadanie00,
    MYADDON_OT_LoadMission01,
    MYADDON_OT_NewStandardMission,
    MYADDON_OT_ImportMissionFile,
    MYADDON_OT_ExportMissionJson,
    MYADDON_OT_LoadTerrainChunks,
    MYADDON_OT_ClearTerrainChunks,
    MYADDON_OT_SnapSelectedToTerrain,
    MYADDON_OT_Configure40kmViewport,
    MYADDON_OT_SpawnPlayerStart,
    MYADDON_OT_SpawnAirEnemy,
    MYADDON_OT_SpawnGroundEnemy,
    MYADDON_OT_SpawnWaypointRoute,
    MYADDON_OT_SpawnObjectiveNode,
    MYADDON_OT_SpawnTriggerNode,
    MYADDON_OT_SpawnWatchtower,
    MYADDON_OT_GenerateWatchtowerChain,
    MYADDON_OT_EnsureZadanie00Markers,
    MYADDON_OT_RefreshProxyVisuals,
    MYADDON_OT_StartLiveSync,
    MYADDON_OT_StopLiveSync,
    MYADDON_OT_PushLiveSyncNow,
    MYADDON_OT_PushAndRestartGame,
    TOPBAR_MT_mission_menu,
    VIEW3D_MT_mission_add_submenu,
    OBJECT_PT_mission_selected_inspector,
    OBJECT_PT_mission_control,
    SCENE_PT_mission_control,
)


def _auto_initialize_sync_standby() -> Optional[float]:
    """
    Blender 起動時または新規プロジェクト作成時は地形やミッションを勝手にロードせず、
    リポジトリパス設定と HTTP ライブ同期サーバーの待受 (Port 8766) のみ開始する。
    ゲーム側が起動して接続された瞬間に LiveSyncServerManager が全地形＋ミッションを自動ロードする。
    """
    if bpy.app.background:
        return None
    if len(bpy.data.scenes) == MathConstants.ZERO_INT:
        return None

    scene = getattr(bpy.context, "scene", None) or bpy.data.scenes[MathConstants.ZERO_INT]
    if not hasattr(scene, "mission_settings"):
        return None

    default_root = RepoPathResolver.detect_default_repo_root()
    if not scene.mission_settings.repo_root or not RepoPathResolver.resolve_repo_root(scene).exists():
        scene.mission_settings.repo_root = default_root

    WorkspaceModeHelper.ensure_mission_workspace(keep_current_active=True)

    mgr = LiveSyncServerManager.instance()
    mgr.reset_for_new_blend_session(scene)
    mgr.start(scene)
    return None


@persistent
def _on_blend_file_loaded(_dummy) -> None:
    if not bpy.app.background:
        bpy.app.timers.register(
            _auto_initialize_sync_standby,
            first_interval=LiveSyncDefaults.TIMER_INTERVAL_SEC,
        )


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.mission_settings = PointerProperty(type=MISSION_Settings)
    bpy.types.Object.mission_obj = PointerProperty(type=MISSION_ObjectProps)

    bpy.types.TOPBAR_MT_editor_menus.append(TOPBAR_MT_mission_menu.submenu)
    bpy.types.VIEW3D_HT_header.append(draw_view3d_header_toolbar)
    bpy.types.VIEW3D_MT_add.append(VIEW3D_MT_mission_add_submenu.add_menu_entry)

    if _on_blend_file_loaded not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(_on_blend_file_loaded)

    if not bpy.app.background:
        bpy.app.timers.register(
            _auto_initialize_sync_standby,
            first_interval=LiveSyncDefaults.TIMER_INTERVAL_SEC,
        )
    print("レベルエディタ(Mission)が有効化されました。")


def unregister() -> None:
    LiveSyncServerManager.instance().stop()
    if _on_blend_file_loaded in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(_on_blend_file_loaded)

    bpy.types.VIEW3D_MT_add.remove(VIEW3D_MT_mission_add_submenu.add_menu_entry)
    bpy.types.VIEW3D_HT_header.remove(draw_view3d_header_toolbar)
    bpy.types.TOPBAR_MT_editor_menus.remove(TOPBAR_MT_mission_menu.submenu)

    if hasattr(bpy.types.Object, "mission_obj"):
        del bpy.types.Object.mission_obj
    if hasattr(bpy.types.Scene, "mission_settings"):
        del bpy.types.Scene.mission_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
    print("レベルエディタ(Mission)が無効化されました。")
