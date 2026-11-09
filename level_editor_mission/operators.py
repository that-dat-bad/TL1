# -*- coding: utf-8 -*-
"""
Mission Editor - Blender オペレータ群
ミッション入出力・地形ロード＆接地・ワンクリック配置・40kmビューポート最適化・実機HTTPライブ同期を提供します。
"""

from typing import List, Tuple
import bpy
from bpy.props import StringProperty
from bpy.types import Context, Object, Operator
from bpy_extras.io_utils import ImportHelper
from mathutils import Vector

from .constants import (
    ColorPalette,
    EnemyDefaults,
    EntityRoles,
    GroundDefaults,
    MathConstants,
    MissionDefaults,
    ObjectiveDefaults,
    PathConstants,
    TerrainDefaults,
    TriggerDefaults,
    ViewportDefaults,
    WorkspaceDefaults,
    Zadanie00MarkerKinds,
)
from .coords import CoordinateTransformer
from .live_sync_server import LiveSyncServerManager
from .mesh_factory import EntityMeshFactory
from .properties import RepoPathResolver
from .serializer import MissionSceneSerializer
from .terrain_loader import TerrainChunkLoader


class WorkspaceModeHelper:
    """『レイアウト (Layout)』の操作・画面分割を完全継承した専用『ミッション編集』ワークスペース管理クラス"""

    @classmethod
    def ensure_mission_workspace(cls, keep_current_active: bool = True) -> None:
        if bpy.app.background:
            return
        existing = bpy.data.workspaces.get(WorkspaceDefaults.MISSION_WORKSPACE_NAME)
        if existing is not None:
            return

        wm = getattr(bpy.context, "window_manager", None)
        if wm is None or len(wm.windows) == MathConstants.ZERO_INT:
            return

        win = wm.windows[MathConstants.ZERO_INT]
        orig_ws = win.workspace

        before_ws = set(bpy.data.workspaces)
        try:
            bpy.ops.workspace.duplicate()
        except Exception:
            return

        created = [w for w in bpy.data.workspaces if w not in before_ws]
        if not created:
            return

        mission_ws = created[MathConstants.ZERO_INT]
        mission_ws.name = WorkspaceDefaults.MISSION_WORKSPACE_NAME

        if keep_current_active and orig_ws is not None:
            def _restore_prev_ws():
                if wm is not None and len(wm.windows) > MathConstants.ZERO_INT:
                    wm.windows[MathConstants.ZERO_INT].workspace = orig_ws
                return None

            bpy.app.timers.register(
                _restore_prev_ws,
                first_interval=WorkspaceDefaults.RESTORE_LAYOUT_DELAY_SEC,
            )

    @classmethod
    def is_mission_editor_mode(cls, context: Context) -> bool:
        ws = getattr(context, "workspace", None)
        if ws is None:
            win = getattr(context, "window", None)
            if win is not None:
                ws = win.workspace
        if ws is not None:
            if ws.name == WorkspaceDefaults.MISSION_WORKSPACE_NAME:
                return True
            if bpy.data.workspaces.get(WorkspaceDefaults.MISSION_WORKSPACE_NAME) is not None:
                return False

        scene = getattr(context, "scene", None)
        if scene is not None and hasattr(scene, "mission_settings"):
            return bool(scene.mission_settings.is_mission_mode_active)
        return False

    @classmethod
    def activate_mission_workspace(cls, context: Context) -> None:
        scene = getattr(context, "scene", None)
        if scene is not None and hasattr(scene, "mission_settings"):
            scene.mission_settings.is_mission_mode_active = True

        if bpy.app.background:
            return

        mission_ws = bpy.data.workspaces.get(WorkspaceDefaults.MISSION_WORKSPACE_NAME)
        if mission_ws is None:
            cls.ensure_mission_workspace(keep_current_active=False)
            mission_ws = bpy.data.workspaces.get(WorkspaceDefaults.MISSION_WORKSPACE_NAME)

        if mission_ws is not None:
            win = getattr(context, "window", None)
            if win is not None:
                win.workspace = mission_ws
            else:
                wm = getattr(context, "window_manager", None)
                if wm is not None and len(wm.windows) > MathConstants.ZERO_INT:
                    wm.windows[MathConstants.ZERO_INT].workspace = mission_ws

    @classmethod
    def activate_layout_workspace(cls, context: Context) -> None:
        scene = getattr(context, "scene", None)
        if scene is not None and hasattr(scene, "mission_settings"):
            scene.mission_settings.is_mission_mode_active = False

        if bpy.app.background:
            return

        target_ws = None
        for cand_name in WorkspaceDefaults.LAYOUT_WORKSPACE_CANDIDATES:
            target_ws = bpy.data.workspaces.get(cand_name)
            if target_ws is not None:
                break
        if target_ws is None:
            for ws in bpy.data.workspaces:
                if ws.name != WorkspaceDefaults.MISSION_WORKSPACE_NAME:
                    target_ws = ws
                    break

        if target_ws is not None:
            win = getattr(context, "window", None)
            if win is not None:
                win.workspace = target_ws


class ViewportConfigHelper:
    """40km広域マップ用に3Dビューポートのクリッピング・シェーディング・カメラ視点を整えるヘルパー"""

    @staticmethod
    def configure_viewports(context: Context, focus_target: Object = None) -> None:
        screens = set()
        wm = context.window_manager
        if wm is not None:
            for win in wm.windows:
                if win.screen is not None:
                    screens.add(win.screen)
        mission_ws = bpy.data.workspaces.get(WorkspaceDefaults.MISSION_WORKSPACE_NAME)
        if mission_ws is not None:
            for scr in mission_ws.screens:
                screens.add(scr)

        for scr in screens:
            for area in scr.areas:
                if area.type != "VIEW_3D":
                    continue
                for space in area.spaces:
                    if space.type != "VIEW_3D":
                        continue
                    space.clip_start = ViewportDefaults.CLIP_START
                    space.clip_end = ViewportDefaults.CLIP_END
                    if hasattr(space, "overlay"):
                        space.overlay.grid_scale = ViewportDefaults.GRID_SCALE
                    if hasattr(space, "shading"):
                        space.shading.type = "SOLID"
                        space.shading.color_type = "OBJECT"
                    if focus_target is not None and space.region_3d is not None:
                        space.region_3d.view_location = focus_target.location.copy()
                        space.region_3d.view_distance = ViewportDefaults.INITIAL_VIEW_DISTANCE

    @staticmethod
    def select_exclusively(context: Context, obj: Object) -> None:
        view_layer = context.view_layer
        view_layer.update()
        for existing in list(view_layer.objects):
            if existing is not None:
                existing.select_set(False)
        if obj is not None and obj.name in view_layer.objects:
            obj.select_set(True)
            view_layer.objects.active = obj


def _find_player_object(scene) -> Object:
    for obj in scene.objects:
        if hasattr(obj, "mission_obj") and obj.mission_obj.entity_role == EntityRoles.PLAYER_START:
            return obj
    return None


def _count_role(scene, role: str) -> int:
    return sum(
        MathConstants.ONE_INT
        for o in scene.objects
        if hasattr(o, "mission_obj") and o.mission_obj.entity_role == role
    )


def _remove_default_startup_objects() -> None:
    for default_name in TerrainDefaults.DEFAULT_STARTUP_OBJECTS:
        obj = bpy.data.objects.get(default_name)
        if obj is not None:
            bpy.data.objects.remove(obj, do_unlink=True)


# =============================================================================
# 1. 専用モード切替 & ミッション プリセット / JSON 入出力オペレータ
# =============================================================================


class MYADDON_OT_EnterMissionEditorMode(Operator):
    """『レイアウト』の操作系と画面構成を継承した専用『ミッション編集』モードへ切り替えます"""

    bl_idname = "mission.enter_mission_editor_mode"
    bl_label = "専用モード『ミッション編集』へ切替"
    bl_options = {"REGISTER"}

    def execute(self, context: Context):
        WorkspaceModeHelper.activate_mission_workspace(context)
        self.report({"INFO"}, "専用モード『ミッション編集』へ切り替えました（操作系はレイアウトを継承）")
        return {"FINISHED"}


class MYADDON_OT_ExitMissionEditorMode(Operator):
    """通常の『レイアウト』モードへ戻ります"""

    bl_idname = "mission.exit_mission_editor_mode"
    bl_label = "通常『レイアウト』へ戻る"
    bl_options = {"REGISTER"}

    def execute(self, context: Context):
        WorkspaceModeHelper.activate_layout_workspace(context)
        self.report({"INFO"}, "通常の『レイアウト』へ戻りました")
        return {"FINISHED"}


class MYADDON_OT_LoadZadanie00(Operator):
    """ZADANIE 00: Obuchenie (mission00.json) をシーンへ読み込みます"""

    bl_idname = "mission.load_zadanie00"
    bl_label = "ZADANIE 00 (Obuchenie) を開く"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        WorkspaceModeHelper.activate_mission_workspace(context)
        _remove_default_startup_objects()
        TerrainChunkLoader.load_chunks_for_mode(context)
        ok, msg = MissionSceneSerializer.import_mission_json(context, PathConstants.MISSION_00_REL_PATH)
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
        player_obj = _find_player_object(context.scene)
        ViewportConfigHelper.configure_viewports(context, focus_target=player_obj)
        LiveSyncServerManager.instance().notify_manual_mission_loaded(context.scene)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class MYADDON_OT_LoadMission01(Operator):
    """Mission 01: COMBINED STRIKE (mission01.json) をシーンへ読み込みます"""

    bl_idname = "mission.load_mission01"
    bl_label = "Mission 01 (通常戦闘サンプル) を開く"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        WorkspaceModeHelper.activate_mission_workspace(context)
        _remove_default_startup_objects()
        TerrainChunkLoader.load_chunks_for_mode(context)
        ok, msg = MissionSceneSerializer.import_mission_json(context, PathConstants.MISSION_01_REL_PATH)
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
        player_obj = _find_player_object(context.scene)
        ViewportConfigHelper.configure_viewports(context, focus_target=player_obj)
        LiveSyncServerManager.instance().notify_manual_mission_loaded(context.scene)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class MYADDON_OT_NewStandardMission(Operator):
    """会話・チュートリアルを含まない新規フリー戦闘ミッションのテンプレートを構築します"""

    bl_idname = "mission.new_standard_mission"
    bl_label = "新規ミッション作成"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        WorkspaceModeHelper.activate_mission_workspace(context)
        scene = context.scene
        settings = scene.mission_settings
        _remove_default_startup_objects()
        TerrainChunkLoader.load_chunks_for_mode(context)
        MissionSceneSerializer.clear_mission_entities(scene)

        settings.mission_id = MissionDefaults.NEW_MISSION_ID
        settings.mission_file_path = MissionDefaults.NEW_MISSION_FILE
        settings.mission_name = MissionDefaults.NEW_MISSION_NAME
        settings.alias_name = MissionDefaults.NEW_MISSION_ALIAS
        settings.sub_title = MissionDefaults.NEW_MISSION_SUBTITLE
        settings.difficulty = MissionDefaults.NEW_MISSION_DIFFICULTY
        settings.area_name = MissionDefaults.NEW_MISSION_AREA
        settings.description = MissionDefaults.NEW_MISSION_DESC
        settings.player_hp = MissionDefaults.DEFAULT_PLAYER_HP
        settings.time_limit = MissionDefaults.DEFAULT_TIME_LIMIT
        settings.is_zadanie_00_mode = False
        settings.preserved_radio_json = "{}"

        start_bpos = CoordinateTransformer.engine_to_blender_pos(*MissionDefaults.DEFAULT_PLAYER_ENGINE_POS)
        player_obj = MissionSceneSerializer.spawn_player_start(scene, start_bpos, MathConstants.ZERO)
        MissionSceneSerializer.spawn_objective_node(
            scene,
            MathConstants.ZERO_INT,
            start_bpos,
            {
                "name": "Eliminate All Hostile Forces",
                "description": MissionDefaults.NEW_MISSION_DESC,
                "type": ObjectiveDefaults.TYPE_DESTROY_ALL,
                "status": ObjectiveDefaults.STATUS_ACTIVE,
                "isPrimary": True,
            },
        )
        ViewportConfigHelper.configure_viewports(context, focus_target=player_obj)
        ViewportConfigHelper.select_exclusively(context, player_obj)
        LiveSyncServerManager.instance().notify_manual_mission_loaded(scene)
        self.report({"INFO"}, f"新規ミッションテンプレートを作成しました ({settings.mission_file_path})")
        return {"FINISHED"}


class MYADDON_OT_ImportMissionFile(Operator, ImportHelper):
    """任意の missionXX.json ファイルをダイアログから選択してインポートします"""

    bl_idname = "mission.import_mission_file"
    bl_label = "JSONファイルを選択して読込"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def invoke(self, context: Context, event):
        missions_dir = RepoPathResolver.resolve_path(context.scene, PathConstants.MISSIONS_DIR_REL)
        if missions_dir.exists():
            self.filepath = str(missions_dir) + "/"
        return super().invoke(context, event)

    def execute(self, context: Context):
        WorkspaceModeHelper.activate_mission_workspace(context)
        _remove_default_startup_objects()
        TerrainChunkLoader.load_chunks_for_mode(context)
        ok, msg = MissionSceneSerializer.import_mission_json(context, self.filepath)
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
        player_obj = _find_player_object(context.scene)
        ViewportConfigHelper.configure_viewports(context, focus_target=player_obj)
        LiveSyncServerManager.instance().notify_manual_mission_loaded(context.scene)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class MYADDON_OT_ExportMissionJson(Operator):
    """現在の3Dシーン構成をミッションJSON（および missions.json）へ保存します"""

    bl_idname = "mission.export_mission_json"
    bl_label = "JSONへ保存 (Export)"
    bl_options = {"REGISTER"}

    def execute(self, context: Context):
        MissionSceneSerializer.refresh_zadanie00_ambush_curve(context.scene)
        ok, msg = MissionSceneSerializer.export_mission_json(context)
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
        if LiveSyncServerManager.instance().is_running:
            LiveSyncServerManager.instance().push_now(context.scene, request_restart=False)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


# =============================================================================
# 2. 地形チャンクローダー & 高度スナップ & ビューポート設定
# =============================================================================


class MYADDON_OT_LoadTerrainChunks(Operator):
    """Resources/terrains/demo/chunks_info.json から指定範囲の地形OBJチャンクを読み込みます"""

    bl_idname = "mission.load_terrain_chunks"
    bl_label = "地形チャンクをロード"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        ViewportConfigHelper.configure_viewports(context)
        _loaded, _skipped, msg = TerrainChunkLoader.load_chunks_for_mode(context)
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class MYADDON_OT_ClearTerrainChunks(Operator):
    """シーン内の地形チャンクメッシュのみアンロードします（配置済みユニットは保持）"""

    bl_idname = "mission.clear_terrain_chunks"
    bl_label = "地形をクリア"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        removed = TerrainChunkLoader.clear_terrain(context.scene)
        self.report({"INFO"}, f"地形チャンクを {removed} 個アンロードしました")
        return {"FINISHED"}


class MYADDON_OT_SnapSelectedToTerrain(Operator):
    """選択中の機体・地上目標・監視所・ウェイポイント経路を直下の地形高度（+AGL）に合わせます"""

    bl_idname = "mission.snap_selected_to_terrain"
    bl_label = "選択要素を地形高度へスナップ"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        targets = list(context.selected_objects)
        if not targets and context.active_object is not None:
            targets = [context.active_object]
        if not targets:
            self.report({"WARNING"}, "スナップ対象のオブジェクトを選択してください")
            return {"CANCELLED"}

        snapped = TerrainChunkLoader.snap_objects_to_terrain(context, targets)
        if snapped == MathConstants.ZERO_INT:
            self.report(
                {"WARNING"},
                "直下に地形チャンクが見つかりません。先に『地形チャンクをロード』を実行してください",
            )
            return {"CANCELLED"}

        MissionSceneSerializer.refresh_zadanie00_ambush_curve(context.scene)
        self.report({"INFO"}, f"{snapped} 個の要素を地形高度へスナップしました")
        return {"FINISHED"}


class MYADDON_OT_Configure40kmViewport(Operator):
    """40km広域マップが見切れないよう3DビューのClip End (60km) と色分け表示を設定します"""

    bl_idname = "mission.configure_40km_viewport"
    bl_label = "40km広域ビューポート設定を適用"
    bl_options = {"REGISTER"}

    def execute(self, context: Context):
        player_obj = _find_player_object(context.scene)
        ViewportConfigHelper.configure_viewports(context, focus_target=player_obj)
        self.report({"INFO"}, "3Dビューポートの Clip End を 60km に最適化しました")
        return {"FINISHED"}


# =============================================================================
# 3. ワンクリック3D配置ツールパレット (3Dカーソル位置へ生成)
# =============================================================================


class MYADDON_OT_SpawnPlayerStart(Operator):
    """3Dカーソル位置に自機スタート位置 (M-21A) を配置または移動します"""

    bl_idname = "mission.spawn_player_start"
    bl_label = "自機スタート位置"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        c = context.scene.cursor.location
        obj = MissionSceneSerializer.spawn_player_start(context.scene, (c.x, c.y, c.z), MathConstants.ZERO)
        ViewportConfigHelper.select_exclusively(context, obj)
        return {"FINISHED"}


class MYADDON_OT_SpawnAirEnemy(Operator):
    """3Dカーソル位置に空中敵戦闘機を配置します"""

    bl_idname = "mission.spawn_air_enemy"
    bl_label = "空中敵を追加"
    bl_options = {"REGISTER", "UNDO"}

    ai_type: StringProperty(default=EnemyDefaults.AI_CHASE_ATTACK)

    def execute(self, context: Context):
        scene = context.scene
        c = scene.cursor.location
        idx = _count_role(scene, EntityRoles.AIR_ENEMY)
        obj = MissionSceneSerializer.spawn_air_enemy(
            scene=scene,
            obj_name=f"AirEnemy_{idx:02d}",
            blender_pos=(c.x, c.y, c.z),
            model_path=PathConstants.MODEL_M15_REL,
            health=EnemyDefaults.DEFAULT_HEALTH,
            ai_type=self.ai_type,
        )
        ViewportConfigHelper.select_exclusively(context, obj)
        return {"FINISHED"}


class MYADDON_OT_SpawnGroundEnemy(Operator):
    """3Dカーソル位置に地上目標（対空砲台・レーダー施設・装甲車両）を配置します"""

    bl_idname = "mission.spawn_ground_enemy"
    bl_label = "地上目標を追加"
    bl_options = {"REGISTER", "UNDO"}

    ground_type: StringProperty(default=GroundDefaults.AI_TURRET)

    def execute(self, context: Context):
        scene = context.scene
        c = scene.cursor.location
        idx = _count_role(scene, EntityRoles.GROUND_ENEMY)
        obj = MissionSceneSerializer.spawn_ground_enemy(
            scene=scene,
            obj_name=f"GroundTarget_{idx:02d}_{self.ground_type}",
            blender_pos=(c.x, c.y, c.z),
            ground_ai_type=self.ground_type,
        )
        # 地形がロード済みなら自動で地面 (0m AGL) へ接地
        TerrainChunkLoader.snap_objects_to_terrain(context, [obj])
        ViewportConfigHelper.select_exclusively(context, obj)
        return {"FINISHED"}


class MYADDON_OT_SpawnWaypointRoute(Operator):
    """3Dカーソル位置を起点とする3Dウェイポイント経路 (Curve) を新規作成します"""

    bl_idname = "mission.spawn_waypoint_route"
    bl_label = "ウェイポイント経路 (Curve)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        scene = context.scene
        c = scene.cursor.location
        idx = _count_role(scene, EntityRoles.WAYPOINT_PATH)
        route_name = (
            MissionDefaults.ZADANIE_00_PATROL_ROUTE_NAME
            if (scene.mission_settings.is_zadanie_00_mode and idx == MathConstants.ZERO_INT)
            else f"Patrol_Route_{idx:02d}"
        )

        pts: List[Tuple[Tuple[float, float, float], float]] = []
        for i in range(EnemyDefaults.NEW_ROUTE_POINT_COUNT):
            by = c.y + float(i) * EnemyDefaults.NEW_ROUTE_FORWARD_STEP_BLENDER_Y
            pts.append(((c.x, by, c.z), EnemyDefaults.DEFAULT_WAYPOINT_SPEED_KMH))

        obj = MissionSceneSerializer.spawn_waypoint_route(scene, route_name, False, pts)
        ViewportConfigHelper.select_exclusively(context, obj)
        return {"FINISHED"}


class MYADDON_OT_SpawnObjectiveNode(Operator):
    """3Dカーソル位置にミッション目標ノードを追加します"""

    bl_idname = "mission.spawn_objective_node"
    bl_label = "ミッション目標ノード"
    bl_options = {"REGISTER", "UNDO"}

    obj_type: StringProperty(default=ObjectiveDefaults.TYPE_DESTROY_ALL)

    def execute(self, context: Context):
        scene = context.scene
        c = scene.cursor.location
        idx = _count_role(scene, EntityRoles.OBJECTIVE_NODE)
        obj = MissionSceneSerializer.spawn_objective_node(
            scene,
            idx,
            (c.x, c.y, c.z),
            {
                "name": f"Objective_{idx:02d}_{self.obj_type}",
                "description": "作戦目標を達成せよ",
                "type": self.obj_type,
                "status": ObjectiveDefaults.STATUS_ACTIVE,
                "isPrimary": True,
            },
        )
        ViewportConfigHelper.select_exclusively(context, obj)
        return {"FINISHED"}


class MYADDON_OT_SpawnTriggerNode(Operator):
    """3Dカーソル位置に会話以外のゲームプレイトリガー（増援・目標切替・クリア判定等）を追加します"""

    bl_idname = "mission.spawn_trigger_node"
    bl_label = "ゲームプレイトリガー"
    bl_options = {"REGISTER", "UNDO"}

    action_type: StringProperty(default=TriggerDefaults.ACT_SPAWN_ENEMIES)

    def execute(self, context: Context):
        scene = context.scene
        c = scene.cursor.location
        idx = _count_role(scene, EntityRoles.TRIGGER_NODE)
        obj = MissionSceneSerializer.spawn_trigger_node(
            scene,
            idx,
            (c.x, c.y, c.z),
            {
                "name": f"Wave_Trigger_{idx:02d}",
                "condition": TriggerDefaults.COND_AREA_ENTER,
                "areaRadius": TriggerDefaults.DEFAULT_AREA_RADIUS,
            },
        )
        obj.mission_obj.trig_action_type = self.action_type
        ViewportConfigHelper.select_exclusively(context, obj)
        return {"FINISHED"}


class MYADDON_OT_EnsureZadanie00Markers(Operator):
    """ZADANIE 00 (Obuchenie) 専用の7種の空間配置マーカーと急襲ベジェ曲線を生成・復元します"""

    bl_idname = "mission.ensure_zadanie00_markers"
    bl_label = "ZADANIE 00 全空間マーカーを生成/整列"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        scene = context.scene
        scene.mission_settings.is_zadanie_00_mode = True
        markers = MissionSceneSerializer.ensure_zadanie00_markers(scene, layout_dict=None)
        self.report({"INFO"}, f"ZADANIE 00 空間マーカー ({len(markers)} 点) を準備しました")
        return {"FINISHED"}


class MYADDON_OT_GenerateWatchtowerChain(Operator):
    """峡谷哨戒ルートに沿って複数基の監視塔を一括自動配置し、地形高度へ自動接地させます"""

    bl_idname = "mission.generate_watchtower_chain"
    bl_label = "監視塔を峡谷ルート沿いに一括自動配置"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        scene = context.scene
        scene.mission_settings.is_zadanie_00_mode = True
        towers = MissionSceneSerializer.generate_canyon_watchtowers(context, scene)
        if towers:
            ViewportConfigHelper.select_exclusively(context, towers[MathConstants.NEGATIVE_ONE_INT])
        if LiveSyncServerManager.instance().is_running:
            LiveSyncServerManager.instance().push_now(scene, request_restart=False)
        self.report({"INFO"}, f"峡谷ルート沿いに監視塔を {len(towers)} 基自動配置＆地形接地しました")
        return {"FINISHED"}


class MYADDON_OT_SpawnWatchtower(Operator):
    """3Dカーソル位置に監視塔を1基追加し、地形高度へ自動接地させます"""

    bl_idname = "mission.spawn_watchtower"
    bl_label = "監視塔を追加"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        scene = context.scene
        c = scene.cursor.location
        existing_wt = [
            o
            for o in scene.objects
            if hasattr(o, "mission_obj")
            and o.mission_obj.entity_role == EntityRoles.ZADANIE00_MARKER
            and o.mission_obj.z00_marker_kind == Zadanie00MarkerKinds.OUTPOST_04
        ]
        tower_num = len(existing_wt) + MathConstants.ONE_INT
        obj = MissionSceneSerializer.spawn_watchtower(
            scene=scene,
            obj_name=f"Z00_Outpost_{tower_num:02d}_Watchtower",
            blender_pos=(c.x, c.y, c.z),
            is_incident_tower=False,
        )
        TerrainChunkLoader.snap_objects_to_terrain(context, [obj])
        ViewportConfigHelper.select_exclusively(context, obj)
        if LiveSyncServerManager.instance().is_running:
            LiveSyncServerManager.instance().push_now(scene, request_restart=False)
        return {"FINISHED"}


class MYADDON_OT_RefreshProxyVisuals(Operator):
    """選択オブジェクトのプロパティ変更（種別・増援トリガー有無等）に合わせて3D見た目と色を更新します"""

    bl_idname = "mission.refresh_proxy_visuals"
    bl_label = "3Dプロキシ形状・色を更新"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context: Context):
        obj = context.active_object
        if obj is None or not hasattr(obj, "mission_obj"):
            return {"CANCELLED"}
        props = obj.mission_obj
        is_reinforce = bool(props.spawn_trigger_name.strip())

        if props.entity_role == EntityRoles.AIR_ENEMY:
            model_path = (
                props.air_custom_model_path if props.air_model_preset == "CUSTOM" else props.air_model_preset
            )
            obj.data = EntityMeshFactory.get_or_build_fighter_mesh(context.scene, model_path)
            rgba = ColorPalette.AIR_REINFORCE_MAGENTA if is_reinforce else ColorPalette.AIR_ENEMY_RED
            mat_name = "Mission_Mat_AirReinforce" if is_reinforce else "Mission_Mat_AirEnemyRed"
            EntityMeshFactory.apply_visual_color(obj, mat_name, rgba)
        elif props.entity_role == EntityRoles.GROUND_ENEMY:
            obj.data = EntityMeshFactory.get_or_build_ground_mesh(props.ground_ai_type)
            if is_reinforce:
                EntityMeshFactory.apply_visual_color(obj, "Mission_Mat_GroundReinforce", ColorPalette.AIR_REINFORCE_MAGENTA)
            elif props.ground_ai_type == GroundDefaults.AI_STRUCTURE:
                EntityMeshFactory.apply_visual_color(obj, "Mission_Mat_GroundStruct", ColorPalette.GROUND_STRUCT_AMBER)
            elif props.ground_ai_type == GroundDefaults.AI_PATROL_VEHICLE:
                EntityMeshFactory.apply_visual_color(obj, "Mission_Mat_GroundVehicle", ColorPalette.GROUND_VEHICLE_OLIVE)
            else:
                EntityMeshFactory.apply_visual_color(obj, "Mission_Mat_GroundTurret", ColorPalette.GROUND_TURRET_ORANGE)

        MissionSceneSerializer.refresh_zadanie00_ambush_curve(context.scene)
        return {"FINISHED"}


# =============================================================================
# 4. DirectX 実機 HTTP ライブ同期オペレータ
# =============================================================================


class MYADDON_OT_StartLiveSync(Operator):
    """実行中の 25B_GE_CG.exe とリアルタイム連携するローカルHTTPサーバー (Port 8766) を起動します"""

    bl_idname = "mission.start_live_sync"
    bl_label = "Live Sync 開始"
    bl_options = {"REGISTER"}

    def execute(self, context: Context):
        ok, msg = LiveSyncServerManager.instance().start(context.scene)
        if not ok:
            self.report({"ERROR"}, msg)
            return {"CANCELLED"}
        self.report({"INFO"}, msg)
        return {"FINISHED"}


class MYADDON_OT_StopLiveSync(Operator):
    """実機 HTTP ライブ同期サーバーを停止します"""

    bl_idname = "mission.stop_live_sync"
    bl_label = "Live Sync 停止"
    bl_options = {"REGISTER"}

    def execute(self, context: Context):
        LiveSyncServerManager.instance().stop()
        self.report({"INFO"}, "Live Sync サーバーを停止しました")
        return {"FINISHED"}


class MYADDON_OT_PushLiveSyncNow(Operator):
    """現在の Blender シーン構成を即時実機へホット送信します"""

    bl_idname = "mission.push_live_sync_now"
    bl_label = "今すぐ実機へ反映"
    bl_options = {"REGISTER"}

    def execute(self, context: Context):
        mgr = LiveSyncServerManager.instance()
        if not mgr.is_running:
            ok, msg = mgr.start(context.scene)
            if not ok:
                self.report({"ERROR"}, msg)
                return {"CANCELLED"}
        rev = mgr.push_now(context.scene, request_restart=False)
        self.report({"INFO"}, f"実機へライブ送信しました (Revision {rev})")
        return {"FINISHED"}


class MYADDON_OT_PushAndRestartGame(Operator):
    """現在の配置を送信し、実行中の実機ステージを初期フェーズからリモートリスタートさせます"""

    bl_idname = "mission.push_and_restart_game"
    bl_label = "反映して実機ミッションを最初から再開始"
    bl_options = {"REGISTER"}

    def execute(self, context: Context):
        mgr = LiveSyncServerManager.instance()
        if not mgr.is_running:
            ok, msg = mgr.start(context.scene)
            if not ok:
                self.report({"ERROR"}, msg)
                return {"CANCELLED"}
        rev = mgr.push_now(context.scene, request_restart=True)
        self.report({"INFO"}, f"実機へリスタート要求を送信しました (Revision {rev})")
        return {"FINISHED"}