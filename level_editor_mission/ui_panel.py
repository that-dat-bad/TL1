# -*- coding: utf-8 -*-
"""
Mission Editor - エディタ専用UIモジュール (Nパネル不使用)
1. トップバーメニュー『ミッション編集(Mission)』(TOPBAR_MT_editor_menus)
2. 3Dビュー上部ヘッダー常駐ツールバー (VIEW3D_HT_header)
3. Shift+A 追加メニュー『ミッション要素 (Mission)』(VIEW3D_MT_add)
4. 右下標準プロパティエディタ (PROPERTIES > Object / Scene) 常駐インスペクタ＆設定パネル
"""

import bpy
from bpy.types import Context, Menu, Panel, UILayout

from .constants import (
    EnemyDefaults,
    EntityRoles,
    GroundDefaults,
    MathConstants,
    ObjectiveDefaults,
    TriggerDefaults,
    UILayoutConstants,
)
from .coords import CoordinateTransformer
from .live_sync_server import LiveSyncServerManager
from .operators import WorkspaceModeHelper


# =============================================================================
# 1. トップバーメニュー: 『ミッション編集(Mission)』 (レベルエディタ横)
# =============================================================================


class TOPBAR_MT_mission_menu(Menu):
    """Blender 最上部メニューバーに常駐するミッションエディタ統合メニュー"""

    bl_idname = "TOPBAR_MT_mission_menu"
    bl_label = "ミッション編集(Mission)"
    bl_description = "会話・チュートリアル以外の全ミッション構築＆DirectX実機ライブ同期メニュー"

    def draw(self, context: Context) -> None:
        layout = self.layout
        settings = context.scene.mission_settings
        mgr = LiveSyncServerManager.instance()

        if WorkspaceModeHelper.is_mission_editor_mode(context):
            layout.operator("mission.exit_mission_editor_mode", text="通常『レイアウト』へ戻る", icon="BACK")
        else:
            layout.operator(
                "mission.enter_mission_editor_mode",
                text="専用モード『ミッション編集』へ切替 (操作はレイアウト継承)",
                icon="WORKSPACE",
            )
        layout.separator()

        layout.label(text="ミッション切替・読込", icon="BOOKMARKS")
        layout.operator("mission.load_zadanie00", text="ZADANIE 00 (Obuchenie) を開く", icon="PLAY")
        layout.operator("mission.load_mission01", text="Mission 01 (通常戦闘サンプル) を開く", icon="IMPORT")
        layout.operator("mission.new_standard_mission", text="新規ミッションを作成", icon="FILE_NEW")
        layout.operator("mission.import_mission_file", text="任意の missionXX.json を開く...", icon="FILE_FOLDER")

        layout.separator()
        layout.label(text="保存・出力", icon="EXPORT")
        layout.operator("mission.export_mission_json", text="JSONへ保存 (missions.json 同期)", icon="FILE_TICK")

        layout.separator()
        if mgr.is_running:
            layout.label(
                text=f"実機ライブ同期: 稼働中 (Port {mgr.bound_port} / Rev {mgr.revision} / 受信 {mgr.client_poll_count})",
                icon="CHECKMARK",
            )
            layout.operator("mission.push_live_sync_now", text="今すぐ実機へ反映 (Push)", icon="FILE_REFRESH")
            layout.operator(
                "mission.push_and_restart_game",
                text="反映して実機ステージを最初から再開始",
                icon="RECOVER_LAST",
            )
            layout.operator("mission.stop_live_sync", text="Live Sync サーバー停止", icon="PAUSE")
        else:
            layout.label(text="実機ライブ同期: 停止中", icon="RADIOBUT_OFF")
            layout.operator("mission.start_live_sync", text="Live Sync サーバー開始 (Port 8766)", icon="PLAY")

        layout.separator()
        layout.label(text="全地形 & 高度スナップ", icon="MESH_GRID")
        layout.operator("mission.load_terrain_chunks", text="ミッション全地形 (100チャンク) をロード", icon="MESH_GRID")
        layout.operator("mission.snap_selected_to_terrain", text="選択要素を地形高度へスナップ", icon="SNAP_ON")
        layout.operator("mission.configure_40km_viewport", text="40km広域ビューポート設定を適用", icon="VIEW3D")

        layout.separator()
        layout.label(text="3Dカーソル位置へ要素追加", icon="ADD")
        layout.operator("mission.spawn_player_start", text="自機初期位置 (M-21A)", icon="ORIENTATION_GLOBAL")
        layout.operator("mission.spawn_waypoint_route", text="ウェイポイント経路 (Curve)", icon="CURVE_PATH")

        op_air_chase = layout.operator("mission.spawn_air_enemy", text="空中敵: 追尾攻撃機 (ChaseAttack)", icon="OUTLINER_OB_ARMATURE")
        op_air_chase.ai_type = EnemyDefaults.AI_CHASE_ATTACK
        op_air_wp = layout.operator("mission.spawn_air_enemy", text="空中敵: 経路哨戒機 (FollowWaypoint)", icon="OUTLINER_OB_ARMATURE")
        op_air_wp.ai_type = EnemyDefaults.AI_FOLLOW_WAYPOINT
        op_air_evade = layout.operator("mission.spawn_air_enemy", text="空中敵: 巡航回避機 (CruiseEvade)", icon="OUTLINER_OB_ARMATURE")
        op_air_evade.ai_type = EnemyDefaults.AI_CRUISE_EVADE

        op_gnd_turret = layout.operator("mission.spawn_ground_enemy", text="地上目標: 対空砲台 (Turret)", icon="MESH_ICOSPHERE")
        op_gnd_turret.ground_type = GroundDefaults.AI_TURRET
        op_gnd_struct = layout.operator("mission.spawn_ground_enemy", text="地上目標: レーダー施設 (Structure)", icon="MESH_ICOSPHERE")
        op_gnd_struct.ground_type = GroundDefaults.AI_STRUCTURE
        op_gnd_veh = layout.operator("mission.spawn_ground_enemy", text="地上目標: 対空装甲車両 (PatrolVehicle)", icon="MESH_ICOSPHERE")
        op_gnd_veh.ground_type = GroundDefaults.AI_PATROL_VEHICLE

        op_obj_all = layout.operator("mission.spawn_objective_node", text="目標ノード: 全敵殲滅", icon="EMPTY_AXIS")
        op_obj_all.obj_type = ObjectiveDefaults.TYPE_DESTROY_ALL
        op_obj_area = layout.operator("mission.spawn_objective_node", text="目標ノード: エリア到達", icon="EMPTY_AXIS")
        op_obj_area.obj_type = ObjectiveDefaults.TYPE_REACH_AREA

        op_trig_spawn = layout.operator("mission.spawn_trigger_node", text="トリガー: 増援出現 (SpawnEnemies)", icon="FORCE_VORTEX")
        op_trig_spawn.action_type = TriggerDefaults.ACT_SPAWN_ENEMIES
        op_trig_obj = layout.operator("mission.spawn_trigger_node", text="トリガー: 目標切替 (SetObjective)", icon="FORCE_VORTEX")
        op_trig_obj.action_type = TriggerDefaults.ACT_SET_OBJECTIVE

        if settings.is_zadanie_00_mode:
            layout.separator()
            layout.label(text="峡谷監視塔 一括自動配置", icon="MOD_ARRAY")
            layout.prop(settings, "watchtower_count")
            layout.prop(settings, "watchtower_lateral_offset")
            layout.prop(settings, "watchtower_alternate_banks")
            layout.operator(
                "mission.generate_watchtower_chain",
                text="監視塔を峡谷ルート沿いに一括自動配置",
                icon="MOD_ARRAY",
            )
            layout.operator("mission.spawn_watchtower", text="監視塔を3Dカーソルに1基追加", icon="MESH_CYLINDER")
            layout.operator("mission.ensure_zadanie00_markers", text="ZADANIE 00 全空間マーカーを生成/整列", icon="SHADING_RENDERED")

    @staticmethod
    def submenu(menu_self, _context: Context) -> None:
        menu_self.layout.menu(TOPBAR_MT_mission_menu.bl_idname)


# =============================================================================
# 2. Shift+A (オブジェクト追加) メニュー統合
# =============================================================================


class VIEW3D_MT_mission_add_submenu(Menu):
    """3Dビューの Shift+A (Add) メニューからワンクリックでミッション要素を配置するサブメニュー"""

    bl_idname = "VIEW3D_MT_mission_add_submenu"
    bl_label = "ミッション要素 (Mission)"

    def draw(self, _context: Context) -> None:
        layout = self.layout
        layout.operator("mission.spawn_player_start", text="自機初期位置 (M-21A)", icon="ORIENTATION_GLOBAL")
        layout.operator("mission.spawn_waypoint_route", text="ウェイポイント経路 (Curve)", icon="CURVE_PATH")
        layout.separator()

        op_chase = layout.operator("mission.spawn_air_enemy", text="空中敵: 追尾攻撃機", icon="OUTLINER_OB_ARMATURE")
        op_chase.ai_type = EnemyDefaults.AI_CHASE_ATTACK
        op_wp = layout.operator("mission.spawn_air_enemy", text="空中敵: 経路哨戒機", icon="OUTLINER_OB_ARMATURE")
        op_wp.ai_type = EnemyDefaults.AI_FOLLOW_WAYPOINT
        op_evade = layout.operator("mission.spawn_air_enemy", text="空中敵: 巡航回避機", icon="OUTLINER_OB_ARMATURE")
        op_evade.ai_type = EnemyDefaults.AI_CRUISE_EVADE
        layout.separator()

        op_turret = layout.operator("mission.spawn_ground_enemy", text="地上目標: 対空砲台 AAA", icon="MESH_ICOSPHERE")
        op_turret.ground_type = GroundDefaults.AI_TURRET
        op_struct = layout.operator("mission.spawn_ground_enemy", text="地上目標: レーダー施設", icon="MESH_ICOSPHERE")
        op_struct.ground_type = GroundDefaults.AI_STRUCTURE
        op_veh = layout.operator("mission.spawn_ground_enemy", text="地上目標: 対空装甲車両", icon="MESH_ICOSPHERE")
        op_veh.ground_type = GroundDefaults.AI_PATROL_VEHICLE
        layout.separator()

        op_oa = layout.operator("mission.spawn_objective_node", text="目標ノード (Objective)", icon="EMPTY_AXIS")
        op_oa.obj_type = ObjectiveDefaults.TYPE_DESTROY_ALL
        op_ts = layout.operator("mission.spawn_trigger_node", text="イベントトリガー (Trigger)", icon="FORCE_VORTEX")
        op_ts.action_type = TriggerDefaults.ACT_SPAWN_ENEMIES
        layout.separator()
        layout.operator("mission.spawn_watchtower", text="峡谷監視塔を1基追加", icon="MESH_CYLINDER")
        layout.operator("mission.generate_watchtower_chain", text="監視塔を峡谷ルート沿いに一括自動配置", icon="MOD_ARRAY")

    @staticmethod
    def add_menu_entry(menu_self, context: Context) -> None:
        if not WorkspaceModeHelper.is_mission_editor_mode(context):
            return
        menu_self.layout.separator()
        menu_self.layout.menu(VIEW3D_MT_mission_add_submenu.bl_idname, icon="OUTLINER_OB_ARMATURE")


# =============================================================================
# 3. 3Dビューポート上部ヘッダー常駐ツールバー (専用『ミッション編集』モード時のみ展開)
# =============================================================================


def draw_view3d_header_toolbar(header_self, context: Context) -> None:
    """
    通常『レイアウト』ではごちゃつかないよう単一のモード切替ボタンのみ表示し、
    専用『ミッション編集』モード（ワークスペース）でのみ全ミッション構築ツールバーを展開する。
    """
    scene = getattr(context, "scene", None)
    if scene is None or not hasattr(scene, "mission_settings"):
        return

    layout = header_self.layout

    if not WorkspaceModeHelper.is_mission_editor_mode(context):
        layout.separator_spacer()
        layout.operator("mission.enter_mission_editor_mode", text="ミッション編集モード", icon="WORKSPACE")
        return

    mgr = LiveSyncServerManager.instance()

    layout.separator_spacer()

    layout.operator("mission.exit_mission_editor_mode", text="レイアウトへ戻る", icon="BACK")

    # 同期ステータス & 切替
    row_sync = layout.row(align=True)
    if mgr.is_running:
        polls = mgr.client_poll_count
        status_label = f"実機接続中(Rev{mgr.revision})" if polls > MathConstants.ZERO_INT else f"Sync待受:{mgr.bound_port}"
        row_sync.operator("mission.push_live_sync_now", text=status_label, icon="CHECKMARK" if polls > MathConstants.ZERO_INT else "URL")
        row_sync.operator("mission.push_and_restart_game", text="実機再開始", icon="RECOVER_LAST")
    else:
        row_sync.operator("mission.start_live_sync", text="Sync開始", icon="PLAY")

    # ミッション切替
    row_mission = layout.row(align=True)
    row_mission.operator("mission.load_zadanie00", text="ZADANIE 00", icon="BOOKMARKS")
    row_mission.operator("mission.load_mission01", text="M01")
    row_mission.operator("mission.new_standard_mission", text="新規", icon="FILE_NEW")

    # ワンクリック配置 & 監視塔一括自動配置
    row_spawn = layout.row(align=True)
    row_spawn.operator("mission.spawn_waypoint_route", text="+経路", icon="CURVE_PATH")
    op_air = row_spawn.operator("mission.spawn_air_enemy", text="+空中敵", icon="OUTLINER_OB_ARMATURE")
    op_air.ai_type = EnemyDefaults.AI_CHASE_ATTACK
    op_tur = row_spawn.operator("mission.spawn_ground_enemy", text="+砲台", icon="MESH_ICOSPHERE")
    op_tur.ground_type = GroundDefaults.AI_TURRET
    op_str = row_spawn.operator("mission.spawn_ground_enemy", text="+施設")
    op_str.ground_type = GroundDefaults.AI_STRUCTURE
    op_veh = row_spawn.operator("mission.spawn_ground_enemy", text="+車両")
    op_veh.ground_type = GroundDefaults.AI_PATROL_VEHICLE

    row_wt = layout.row(align=True)
    row_wt.prop(scene.mission_settings, "watchtower_count", text="監視塔数")
    row_wt.operator("mission.generate_watchtower_chain", text="監視塔一括配置", icon="MOD_ARRAY")
    row_wt.operator("mission.spawn_watchtower", text="+監視塔", icon="MESH_CYLINDER")

    # 接地 & 保存
    row_act = layout.row(align=True)
    row_act.operator("mission.snap_selected_to_terrain", text="地形スナップ", icon="SNAP_ON")
    row_act.operator("mission.export_mission_json", text="JSON保存", icon="FILE_TICK")


# =============================================================================
# 4. 右下標準プロパティエディタ (PROPERTIES) 常駐インスペクタ＆設定パネル
# =============================================================================


def _draw_selected_entity_inspector(layout: UILayout, context: Context) -> None:
    obj = context.active_object
    if obj is None or not hasattr(obj, "mission_obj"):
        layout.label(text="3Dビューでミッション要素を選択してください", icon="INFO")
        return

    props = obj.mission_obj
    loc = obj.matrix_world.translation
    ex, ey, ez = CoordinateTransformer.blender_to_engine_pos(loc.x, loc.y, loc.z)
    eyaw = CoordinateTransformer.blender_rot_z_to_engine_yaw_deg(obj.rotation_euler.z)

    coord_box = layout.box()
    coord_box.label(text=f"選択中: {obj.name}", icon="ORIENTATION_GLOBAL")
    coord_box.label(text=f"DirectX 実機座標: X={ex:.1f}, Y={ey:.1f}, Z={ez:.1f}  (方位 {eyaw:.1f}°)")
    row_role = coord_box.row(align=True)
    row_role.prop(props, "entity_role")
    row_role.operator("mission.snap_selected_to_terrain", text="地形スナップ", icon="SNAP_ON")

    role = props.entity_role
    if role == EntityRoles.NONE:
        return

    if role == EntityRoles.PLAYER_START:
        layout.label(text="Z回転 (R -> Z) で自機初期機首方位を変更できます", icon="INFO")

    elif role == EntityRoles.AIR_ENEMY:
        box = layout.box()
        box.prop(props, "air_model_preset")
        if props.air_model_preset == "CUSTOM":
            box.prop(props, "air_custom_model_path")
        box.prop(props, "air_health")
        box.prop(props, "air_ai_type")
        if props.air_ai_type == EnemyDefaults.AI_FOLLOW_WAYPOINT:
            box.prop(props, "waypoint_path_name")
        box.separator()
        box.prop(props, "spawn_trigger_name")
        box.operator("mission.refresh_proxy_visuals", icon="SHADING_RENDERED")

    elif role == EntityRoles.GROUND_ENEMY:
        box = layout.box()
        box.prop(props, "ground_ai_type")
        box.prop(props, "ground_health")
        box.prop(props, "collision_radius")

        if props.ground_ai_type != GroundDefaults.AI_STRUCTURE:
            fire_col = box.column(align=True)
            fire_col.label(text="対空射撃パラメータ:")
            fire_col.prop(props, "fire_range")
            row_el = fire_col.row(align=True)
            row_el.prop(props, "min_elevation_deg")
            row_el.prop(props, "max_elevation_deg")
            fire_col.prop(props, "turn_speed_deg")
            row_bl = fire_col.row(align=True)
            row_bl.prop(props, "bullet_speed")
            row_bl.prop(props, "bullet_damage")
            row_br = fire_col.row(align=True)
            row_br.prop(props, "burst_count")
            row_br.prop(props, "fire_interval")
            fire_col.prop(props, "burst_cooldown")

        if props.ground_ai_type == GroundDefaults.AI_PATROL_VEHICLE:
            veh_col = box.column(align=True)
            veh_col.label(text="車両移動ルート設定:")
            veh_col.prop(props, "move_speed")
            veh_col.prop(props, "waypoint_path_name")
            if not props.waypoint_path_name.strip():
                veh_col.prop(props, "patrol_distance")

        box.separator()
        box.prop(props, "spawn_trigger_name")
        box.operator("mission.refresh_proxy_visuals", icon="SHADING_RENDERED")

    elif role == EntityRoles.WAYPOINT_PATH:
        box = layout.box()
        box.prop(props, "path_name")
        box.prop(props, "path_is_loop")
        box.prop(props, "default_point_speed_kmh")
        box.label(text="Tabキー(編集モード)で各頂点の追加・移動が可能です", icon="CURVE_PATH")
        if context.scene.mission_settings.is_zadanie_00_mode:
            box.label(text="※ZADANIE 00ではこの頂点列がPhase 3の峡谷ゲートになります", icon="INFO")

    elif role == EntityRoles.OBJECTIVE_NODE:
        box = layout.box()
        row_ord = box.row(align=True)
        row_ord.prop(props, "obj_sort_order")
        row_ord.prop(props, "obj_is_primary")
        row_ord.prop(props, "obj_is_hidden")
        box.prop(props, "obj_name")
        box.prop(props, "obj_description")
        box.prop(props, "obj_type")
        box.prop(props, "obj_status")

        if props.obj_type == ObjectiveDefaults.TYPE_DESTROY_COUNT:
            box.prop(props, "obj_required_kills")
        elif props.obj_type in (ObjectiveDefaults.TYPE_DESTROY_TARGET, ObjectiveDefaults.TYPE_ESCORT_PROTECT):
            box.prop(props, "obj_target_unit")
            if props.obj_target_unit is None:
                box.prop(props, "obj_fallback_target_index")
            if props.obj_type == ObjectiveDefaults.TYPE_ESCORT_PROTECT:
                box.prop(props, "obj_min_hp")
        elif props.obj_type == ObjectiveDefaults.TYPE_REACH_AREA:
            box.prop(props, "obj_area_radius")
        elif props.obj_type == ObjectiveDefaults.TYPE_SURVIVE:
            box.prop(props, "obj_duration")

    elif role == EntityRoles.TRIGGER_NODE:
        box = layout.box()
        row_t = box.row(align=True)
        row_t.prop(props, "trig_sort_order")
        row_t.prop(props, "trig_enabled")
        row_t.prop(props, "trig_repeatable")
        box.prop(props, "trig_name")
        box.prop(props, "trig_condition")

        cond = props.trig_condition
        if cond == TriggerDefaults.COND_TIMER:
            box.prop(props, "trig_timer_seconds")
        elif cond in (TriggerDefaults.COND_AREA_ENTER, TriggerDefaults.COND_AREA_LEAVE):
            box.prop(props, "trig_area_radius")
        elif cond == TriggerDefaults.COND_ENEMY_DESTROYED:
            box.prop(props, "trig_target_enemy")
            if props.trig_target_enemy is None:
                box.prop(props, "trig_fallback_enemy_index")
        elif cond == TriggerDefaults.COND_KILL_COUNT:
            box.prop(props, "trig_kill_count")
        elif cond == TriggerDefaults.COND_PLAYER_DAMAGED:
            box.prop(props, "trig_hp_threshold")
        elif cond == TriggerDefaults.COND_OBJECTIVE_COMPLETE:
            box.prop(props, "trig_target_objective")
            if props.trig_target_objective is None:
                box.prop(props, "trig_fallback_objective_index")

        act_box = layout.box()
        act_box.label(text="発火時ゲームプレイアクション:", icon="PLAY")
        act_box.prop(props, "trig_action_type")
        atype = props.trig_action_type
        if atype == TriggerDefaults.ACT_SPAWN_ENEMIES:
            act_box.label(
                text=f"増援トリガー名に『{props.trig_name}』を設定した敵が出現します",
                icon="INFO",
            )
        elif atype == TriggerDefaults.ACT_SET_OBJECTIVE:
            act_box.prop(props, "trig_set_obj_target")
            if props.trig_set_obj_target is None:
                act_box.prop(props, "trig_set_obj_fallback_index")
            act_box.prop(props, "trig_set_obj_status")
        elif atype == TriggerDefaults.ACT_ACTIVATE_TRIGGER:
            act_box.prop(props, "trig_activate_target")
            if props.trig_activate_target is None:
                act_box.prop(props, "trig_activate_fallback_index")
        elif atype == TriggerDefaults.ACT_SHOW_MESSAGE:
            act_box.prop(props, "trig_hud_message")
            act_box.prop(props, "trig_hud_message_duration")

    elif role == EntityRoles.ZADANIE00_MARKER:
        box = layout.box()
        box.prop(props, "z00_marker_kind")
        box.label(
            text="Gキーで移動すると ZADANIE 00 の該当イベント座標に即時反映されます",
            icon="INFO",
        )
        row_wt_insp = box.row(align=True)
        row_wt_insp.operator("mission.generate_watchtower_chain", text="監視塔ルート一括再配置", icon="MOD_ARRAY")
        row_wt_insp.operator("mission.spawn_watchtower", text="+監視塔追加", icon="MESH_CYLINDER")


def _draw_mission_control_body(layout: UILayout, context: Context) -> None:
    settings = context.scene.mission_settings
    mgr = LiveSyncServerManager.instance()

    # ライブ同期ステータス
    sync_box = layout.box()
    if mgr.is_running:
        polls = mgr.client_poll_count
        if polls > MathConstants.ZERO_INT:
            sync_box.label(
                text=f"実機ライブ同期: 接続中! (Port {mgr.bound_port} / Rev {mgr.revision} / 受信 {polls})",
                icon="CHECKMARK",
            )
        else:
            sync_box.label(
                text=f"実機ライブ同期: 待機中 (Port {mgr.bound_port} - ゲーム起動で自動接続)",
                icon="URL",
            )
        row_s = sync_box.row(align=True)
        row_s.operator("mission.push_live_sync_now", text="今すぐ実機へ反映", icon="FILE_REFRESH")
        row_s.operator("mission.push_and_restart_game", text="実機ステージ再開始", icon="RECOVER_LAST")
        row_s.operator("mission.stop_live_sync", text="", icon="PAUSE")
    else:
        sync_box.operator("mission.start_live_sync", text="Live Sync サーバー開始 (Port 8766)", icon="PLAY")
    sync_box.prop(settings, "live_sync_auto_push")

    # ミッション切替 & 保存
    io_box = layout.box()
    row_q = io_box.row(align=True)
    row_q.scale_y = UILayoutConstants.PRIMARY_BUTTON_SCALE_Y
    row_q.operator("mission.load_zadanie00", text="ZADANIE 00", icon="PLAY")
    row_q.operator("mission.load_mission01", text="Mission 01", icon="IMPORT")
    row_q.operator("mission.new_standard_mission", text="新規作成", icon="FILE_NEW")

    row_id = io_box.row(align=True)
    row_id.prop(settings, "mission_id", text="ID")
    row_id.prop(settings, "alias_name", text="Alias")
    io_box.prop(settings, "mission_name")
    io_box.prop(settings, "sub_title")
    row_meta = io_box.row(align=True)
    row_meta.prop(settings, "difficulty")
    row_meta.prop(settings, "player_hp")
    row_meta.prop(settings, "time_limit")
    io_box.prop(settings, "mission_file_path", text="保存先")
    io_box.prop(settings, "is_zadanie_00_mode")

    row_exp = io_box.row(align=True)
    row_exp.scale_y = UILayoutConstants.LARGE_BUTTON_SCALE_Y
    row_exp.operator("mission.export_mission_json", text="JSONへ保存 (missions.json 同期)", icon="FILE_TICK")

    # 地形 & 高度スナップ
    ter_box = layout.box()
    row_ter = ter_box.row(align=True)
    row_ter.operator("mission.load_terrain_chunks", text="全地形(100区画)を再ロード", icon="MESH_GRID")
    row_ter.operator("mission.snap_selected_to_terrain", text="地形スナップ", icon="SNAP_ON")
    ter_box.prop(settings, "snap_agl_offset")

    # 峡谷監視塔 一括自動配置・調整
    wt_box = layout.box()
    wt_box.label(text="峡谷監視塔 一括自動配置 (スライダー変更で即時反映)", icon="MOD_ARRAY")
    row_wt_params = wt_box.row(align=True)
    row_wt_params.prop(settings, "watchtower_count")
    row_wt_params.prop(settings, "watchtower_lateral_offset")
    wt_box.prop(settings, "watchtower_alternate_banks")
    row_wt_ops = wt_box.row(align=True)
    row_wt_ops.operator("mission.generate_watchtower_chain", text="監視塔を峡谷ルート沿いに一括自動配置", icon="MOD_ARRAY")
    row_wt_ops.operator("mission.spawn_watchtower", text="+1基追加", icon="MESH_CYLINDER")


class OBJECT_PT_mission_selected_inspector(Panel):
    """右下 Properties > Object タブ最上部に常時表示される選択ミッション要素インスペクタ"""

    bl_idname = "OBJECT_PT_mission_selected_inspector"
    bl_label = "選択ミッション要素インスペクタ"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    bl_order = MathConstants.ZERO_INT

    @classmethod
    def poll(cls, context: Context) -> bool:
        return WorkspaceModeHelper.is_mission_editor_mode(context)

    def draw(self, context: Context) -> None:
        _draw_selected_entity_inspector(self.layout, context)


class OBJECT_PT_mission_control(Panel):
    """右下 Properties > Object タブに常時表示されるミッション全体設定＆実機同期パネル"""

    bl_idname = "OBJECT_PT_mission_control"
    bl_label = "ミッション設定 & 実機ライブ同期"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "object"
    bl_order = MathConstants.ONE_INT

    @classmethod
    def poll(cls, context: Context) -> bool:
        return WorkspaceModeHelper.is_mission_editor_mode(context)

    def draw(self, context: Context) -> None:
        _draw_mission_control_body(self.layout, context)


class SCENE_PT_mission_control(Panel):
    """右下 Properties > Scene タブにも常時表示されるミッション全体設定＆実機同期パネル"""

    bl_idname = "SCENE_PT_mission_control"
    bl_label = "ミッションエディタ & 実機ライブ同期"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_order = MathConstants.ZERO_INT

    @classmethod
    def poll(cls, context: Context) -> bool:
        return WorkspaceModeHelper.is_mission_editor_mode(context)

    def draw(self, context: Context) -> None:
        _draw_mission_control_body(self.layout, context)
        self.layout.separator()
        _draw_selected_entity_inspector(self.layout, context)
