# -*- coding: utf-8 -*-
"""
Mission Editor - ミッションJSON ⇔ Blender 3Dシーン 双方向シリアライザ
会話・チュートリアル進行ロジックを保護しつつ、全空間オブジェクト・敵編成・経路・目標・トリガー・ZADANIE 00配置を入出力します。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import bpy
from bpy.types import Context, Object, Scene
from mathutils import Vector

from .constants import (
    CollectionNames,
    ColorPalette,
    EnemyDefaults,
    EntityRoles,
    GizmoDimensions,
    GroundDefaults,
    MathConstants,
    MissionDefaults,
    ObjectiveDefaults,
    PathConstants,
    TriggerDefaults,
    WatchtowerDefaults,
    Zadanie00MarkerKinds,
)
from .coords import CoordinateTransformer
from .mesh_factory import CollectionHelper, EntityMeshFactory
from .properties import RepoPathResolver
from .terrain_loader import TerrainChunkLoader


class MissionSceneSerializer:
    """Blender 3Dシーンと C++ MissionData / missions.json 間の完全双方向変換クラス"""

    ENTITY_COLLECTIONS = (
        CollectionNames.PLAYER_AND_ALLIES,
        CollectionNames.WAYPOINT_ROUTES,
        CollectionNames.AIR_ENEMIES,
        CollectionNames.GROUND_TARGETS,
        CollectionNames.OBJECTIVES_AND_TRIGGERS,
        CollectionNames.ZADANIE00_EVENTS,
    )

    Z00_MARKER_SPECS = {
        Zadanie00MarkerKinds.CORAX_START: (
            "Z00_Corax_Start",
            CollectionNames.PLAYER_AND_ALLIES,
            ColorPalette.ALLY_CORAX_GREEN,
            MissionDefaults.DEFAULT_CORAX_ENGINE_POS,
        ),
        Zadanie00MarkerKinds.OUTPOST_04: (
            "Z00_Outpost04_Watchtower",
            CollectionNames.ZADANIE00_EVENTS,
            ColorPalette.OUTPOST_FIRE,
            MissionDefaults.DEFAULT_OUTPOST_ENGINE_POS,
        ),
        Zadanie00MarkerKinds.TRAINING_DRONE: (
            "Z00_Phase5_TrainingDrone",
            CollectionNames.ZADANIE00_EVENTS,
            ColorPalette.DRONE_ORANGE,
            MissionDefaults.DEFAULT_DRONE_ENGINE_POS,
        ),
        Zadanie00MarkerKinds.WESTERN_DIVE_START: (
            "Z00_Phase6_Western_01_DiveStart",
            CollectionNames.ZADANIE00_EVENTS,
            ColorPalette.WESTERN_AMBUSH_CRIMSON,
            MissionDefaults.DEFAULT_WEST_START_ENGINE_POS,
        ),
        Zadanie00MarkerKinds.WESTERN_DIVE_MID: (
            "Z00_Phase6_Western_02_FlybyMid",
            CollectionNames.ZADANIE00_EVENTS,
            ColorPalette.WESTERN_AMBUSH_CRIMSON,
            MissionDefaults.DEFAULT_WEST_MID_ENGINE_POS,
        ),
        Zadanie00MarkerKinds.WESTERN_PULLUP: (
            "Z00_Phase6_Western_03_PullUpEngage",
            CollectionNames.ZADANIE00_EVENTS,
            ColorPalette.WESTERN_AMBUSH_CRIMSON,
            MissionDefaults.DEFAULT_WEST_PULLUP_ENGINE_POS,
        ),
        Zadanie00MarkerKinds.EXIT_BOUNDARY: (
            "Z00_Phase7_ExitBoundary",
            CollectionNames.ZADANIE00_EVENTS,
            ColorPalette.EXIT_BOUNDARY_SKY,
            MissionDefaults.DEFAULT_EXIT_ENGINE_POS,
        ),
    }

    # =========================================================================
    # シーン初期化・クリア
    # =========================================================================

    @classmethod
    def clear_mission_entities(cls, scene: Scene) -> None:
        """00_Terrain を残したまま、全ミッション配置オブジェクトをクリーン削除する"""
        hierarchy = CollectionHelper.ensure_mission_hierarchy(scene)
        to_remove = set()
        for col_name in cls.ENTITY_COLLECTIONS:
            col = hierarchy.get(col_name)
            if col is not None:
                for obj in col.objects:
                    to_remove.add(obj)

        for obj in list(scene.objects):
            if hasattr(obj, "mission_obj") and obj.mission_obj.entity_role != EntityRoles.NONE:
                to_remove.add(obj)
            elif obj.name == GizmoDimensions.AMBUSH_PREVIEW_NAME:
                to_remove.add(obj)

        for obj in to_remove:
            data_block = obj.data
            obj_type = obj.type
            bpy.data.objects.remove(obj, do_unlink=True)
            if obj_type == "CURVE" and data_block is not None and data_block.users == MathConstants.ZERO_INT:
                bpy.data.curves.remove(data_block)

    # =========================================================================
    # 3D エンティティ生成ヘルパー
    # =========================================================================

    @classmethod
    def spawn_player_start(
        cls,
        scene: Scene,
        blender_pos: Tuple[float, float, float],
        engine_yaw_deg: float = MathConstants.ZERO,
    ) -> Object:
        hierarchy = CollectionHelper.ensure_mission_hierarchy(scene)
        for existing in list(scene.objects):
            if hasattr(existing, "mission_obj") and existing.mission_obj.entity_role == EntityRoles.PLAYER_START:
                existing.location = blender_pos
                existing.rotation_euler.z = CoordinateTransformer.engine_yaw_deg_to_blender_rot_z(engine_yaw_deg)
                return existing

        mesh = EntityMeshFactory.get_or_build_fighter_mesh(scene, PathConstants.MODEL_M21_REL)
        obj = bpy.data.objects.new("Player_Start_M21A", mesh)
        CollectionHelper.link_exclusively(obj, hierarchy[CollectionNames.PLAYER_AND_ALLIES])
        obj.location = blender_pos
        obj.rotation_euler = (
            MathConstants.ZERO,
            MathConstants.ZERO,
            CoordinateTransformer.engine_yaw_deg_to_blender_rot_z(engine_yaw_deg),
        )
        obj.mission_obj.entity_role = EntityRoles.PLAYER_START
        obj.show_name = True
        EntityMeshFactory.apply_visual_color(obj, "Mission_Mat_PlayerCyan", ColorPalette.PLAYER_CYAN)
        return obj

    @classmethod
    def spawn_air_enemy(
        cls,
        scene: Scene,
        obj_name: str,
        blender_pos: Tuple[float, float, float],
        model_path: str = PathConstants.MODEL_M15_REL,
        health: float = EnemyDefaults.DEFAULT_HEALTH,
        ai_type: str = EnemyDefaults.AI_CHASE_ATTACK,
        waypoint_path_name: str = "",
        spawn_trigger_name: str = "",
    ) -> Object:
        hierarchy = CollectionHelper.ensure_mission_hierarchy(scene)
        mesh = EntityMeshFactory.get_or_build_fighter_mesh(scene, model_path)
        obj = bpy.data.objects.new(obj_name, mesh)
        CollectionHelper.link_exclusively(obj, hierarchy[CollectionNames.AIR_ENEMIES])
        obj.location = blender_pos
        obj.show_name = True

        props = obj.mission_obj
        props.entity_role = EntityRoles.AIR_ENEMY
        if model_path in (PathConstants.MODEL_M15_REL, PathConstants.MODEL_M21_REL):
            props.air_model_preset = model_path
        else:
            props.air_model_preset = "CUSTOM"
        props.air_custom_model_path = model_path
        props.air_health = health
        if ai_type in (
            EnemyDefaults.AI_CHASE_ATTACK,
            EnemyDefaults.AI_CRUISE_EVADE,
            EnemyDefaults.AI_FOLLOW_WAYPOINT,
        ):
            props.air_ai_type = ai_type
        else:
            props.air_ai_type = EnemyDefaults.AI_CHASE_ATTACK
        props.waypoint_path_name = waypoint_path_name
        props.spawn_trigger_name = spawn_trigger_name

        if spawn_trigger_name.strip():
            EntityMeshFactory.apply_visual_color(obj, "Mission_Mat_AirReinforce", ColorPalette.AIR_REINFORCE_MAGENTA)
        else:
            EntityMeshFactory.apply_visual_color(obj, "Mission_Mat_AirEnemyRed", ColorPalette.AIR_ENEMY_RED)
        return obj

    @classmethod
    def spawn_ground_enemy(
        cls,
        scene: Scene,
        obj_name: str,
        blender_pos: Tuple[float, float, float],
        ground_ai_type: str = GroundDefaults.AI_TURRET,
        health: Optional[float] = None,
        param_dict: Optional[Dict[str, Any]] = None,
        waypoint_path_name: str = "",
        spawn_trigger_name: str = "",
    ) -> Object:
        hierarchy = CollectionHelper.ensure_mission_hierarchy(scene)
        valid_type = (
            ground_ai_type
            if ground_ai_type in (GroundDefaults.AI_TURRET, GroundDefaults.AI_STRUCTURE, GroundDefaults.AI_PATROL_VEHICLE)
            else GroundDefaults.AI_TURRET
        )
        mesh = EntityMeshFactory.get_or_build_ground_mesh(valid_type)
        obj = bpy.data.objects.new(obj_name, mesh)
        CollectionHelper.link_exclusively(obj, hierarchy[CollectionNames.GROUND_TARGETS])
        obj.location = blender_pos
        obj.show_name = True

        props = obj.mission_obj
        props.entity_role = EntityRoles.GROUND_ENEMY
        props.ground_ai_type = valid_type
        if health is not None:
            props.ground_health = float(health)
        elif valid_type == GroundDefaults.AI_STRUCTURE:
            props.ground_health = GroundDefaults.STRUCTURE_HEALTH
        elif valid_type == GroundDefaults.AI_PATROL_VEHICLE:
            props.ground_health = GroundDefaults.VEHICLE_HEALTH
        else:
            props.ground_health = GroundDefaults.TURRET_HEALTH

        props.waypoint_path_name = waypoint_path_name
        props.spawn_trigger_name = spawn_trigger_name

        if param_dict:
            props.collision_radius = float(param_dict.get("collisionRadius", GroundDefaults.COLLISION_RADIUS))
            props.fire_range = float(param_dict.get("fireRange", GroundDefaults.FIRE_RANGE))
            props.min_elevation_deg = float(param_dict.get("minElevationDeg", GroundDefaults.MIN_ELEVATION_DEG))
            props.max_elevation_deg = float(param_dict.get("maxElevationDeg", GroundDefaults.MAX_ELEVATION_DEG))
            props.turn_speed_deg = float(param_dict.get("turnSpeedDeg", GroundDefaults.TURN_SPEED_DEG))
            props.bullet_speed = float(param_dict.get("bulletSpeed", GroundDefaults.BULLET_SPEED))
            props.bullet_damage = float(param_dict.get("bulletDamage", GroundDefaults.BULLET_DAMAGE))
            props.fire_interval = float(param_dict.get("fireInterval", GroundDefaults.FIRE_INTERVAL))
            props.burst_count = int(param_dict.get("burstCount", GroundDefaults.BURST_COUNT))
            props.burst_cooldown = float(param_dict.get("burstCooldown", GroundDefaults.BURST_COOLDOWN))
            props.move_speed = float(param_dict.get("moveSpeed", GroundDefaults.MOVE_SPEED))
            props.patrol_distance = float(param_dict.get("patrolDistance", GroundDefaults.PATROL_DISTANCE))

        if spawn_trigger_name.strip():
            EntityMeshFactory.apply_visual_color(obj, "Mission_Mat_GroundReinforce", ColorPalette.AIR_REINFORCE_MAGENTA)
        elif valid_type == GroundDefaults.AI_STRUCTURE:
            EntityMeshFactory.apply_visual_color(obj, "Mission_Mat_GroundStruct", ColorPalette.GROUND_STRUCT_AMBER)
        elif valid_type == GroundDefaults.AI_PATROL_VEHICLE:
            EntityMeshFactory.apply_visual_color(obj, "Mission_Mat_GroundVehicle", ColorPalette.GROUND_VEHICLE_OLIVE)
        else:
            EntityMeshFactory.apply_visual_color(obj, "Mission_Mat_GroundTurret", ColorPalette.GROUND_TURRET_ORANGE)
        return obj

    @classmethod
    def spawn_waypoint_route(
        cls,
        scene: Scene,
        route_name: str,
        is_loop: bool,
        blender_points_and_speeds: List[Tuple[Tuple[float, float, float], float]],
    ) -> Object:
        hierarchy = CollectionHelper.ensure_mission_hierarchy(scene)
        curve_data = bpy.data.curves.new(name=f"Curve_{route_name}", type="CURVE")
        curve_data.dimensions = "3D"
        curve_data.bevel_depth = EnemyDefaults.CURVE_BEVEL_DEPTH
        curve_data.resolution_u = EnemyDefaults.CURVE_RESOLUTION_U
        curve_data.extrude = EnemyDefaults.CURVE_EXTRUDE

        mat = EntityMeshFactory.get_or_create_material("Mission_Mat_WaypointEmerald", ColorPalette.WAYPOINT_EMERALD)
        curve_data.materials.append(mat)

        base_speed = EnemyDefaults.DEFAULT_WAYPOINT_SPEED_KMH
        if blender_points_and_speeds:
            first_spd = blender_points_and_speeds[MathConstants.ZERO_INT][MathConstants.ONE_INT]
            if first_spd > MathConstants.ZERO:
                base_speed = first_spd

        spline = curve_data.splines.new(type="POLY")
        spline.use_cyclic_u = is_loop
        if blender_points_and_speeds:
            extra_pts = len(blender_points_and_speeds) - MathConstants.ONE_INT
            if extra_pts > MathConstants.ZERO_INT:
                spline.points.add(extra_pts)
            for idx, (bpos, spd) in enumerate(blender_points_and_speeds):
                pt = spline.points[idx]
                pt.co = (
                    bpos[MathConstants.ZERO_INT],
                    bpos[MathConstants.ONE_INT],
                    bpos[MathConstants.TWO_INT],
                    EnemyDefaults.SPLINE_CO_HOMOGENEOUS_W,
                )
                pt.weight = spd / base_speed if base_speed > MathConstants.EPSILON else EnemyDefaults.DEFAULT_SPLINE_WEIGHT

        obj = bpy.data.objects.new(f"Route_{route_name}", curve_data)
        CollectionHelper.link_exclusively(obj, hierarchy[CollectionNames.WAYPOINT_ROUTES])
        obj.color = ColorPalette.WAYPOINT_EMERALD
        obj.show_name = True

        props = obj.mission_obj
        props.entity_role = EntityRoles.WAYPOINT_PATH
        props.path_name = route_name
        props.path_is_loop = is_loop
        props.default_point_speed_kmh = base_speed
        return obj

    @classmethod
    def spawn_objective_node(
        cls,
        scene: Scene,
        sort_order: int,
        blender_pos: Tuple[float, float, float],
        obj_data: Optional[Dict[str, Any]] = None,
    ) -> Object:
        hierarchy = CollectionHelper.ensure_mission_hierarchy(scene)
        src = obj_data or {}
        title = str(src.get("name", f"Objective_{sort_order:02d}"))
        obj = bpy.data.objects.new(f"Obj_{sort_order:02d}_{title}", None)
        CollectionHelper.link_exclusively(obj, hierarchy[CollectionNames.OBJECTIVES_AND_TRIGGERS])
        obj.location = blender_pos
        obj.color = ColorPalette.OBJECTIVE_GOLD
        obj.show_name = True

        props = obj.mission_obj
        props.entity_role = EntityRoles.OBJECTIVE_NODE
        props.obj_sort_order = sort_order
        props.obj_name = title
        props.obj_description = str(src.get("description", ""))

        otype = str(src.get("type", ObjectiveDefaults.TYPE_DESTROY_ALL))
        props.obj_type = otype if otype in (
            ObjectiveDefaults.TYPE_DESTROY_ALL,
            ObjectiveDefaults.TYPE_DESTROY_COUNT,
            ObjectiveDefaults.TYPE_DESTROY_TARGET,
            ObjectiveDefaults.TYPE_REACH_AREA,
            ObjectiveDefaults.TYPE_SURVIVE,
            ObjectiveDefaults.TYPE_ESCORT_PROTECT,
        ) else ObjectiveDefaults.TYPE_DESTROY_ALL

        ostatus = str(src.get("status", ObjectiveDefaults.STATUS_ACTIVE))
        props.obj_status = (
            ostatus
            if ostatus in (ObjectiveDefaults.STATUS_ACTIVE, ObjectiveDefaults.STATUS_INACTIVE)
            else ObjectiveDefaults.STATUS_ACTIVE
        )
        props.obj_is_primary = bool(src.get("isPrimary", True))
        props.obj_is_hidden = bool(src.get("isHidden", False))
        props.obj_required_kills = int(src.get("requiredKills", MathConstants.ZERO_INT))
        props.obj_fallback_target_index = int(src.get("targetIndex", ObjectiveDefaults.NO_TARGET_INDEX))
        props.obj_area_radius = float(src.get("areaRadius", ObjectiveDefaults.DEFAULT_AREA_RADIUS))
        props.obj_duration = float(src.get("duration", ObjectiveDefaults.DEFAULT_SURVIVE_DURATION))
        props.obj_min_hp = float(src.get("minHP", MathConstants.ZERO))

        if props.obj_type == ObjectiveDefaults.TYPE_REACH_AREA:
            obj.empty_display_type = "SPHERE"
            obj.empty_display_size = max(ObjectiveDefaults.MIN_AREA_RADIUS, props.obj_area_radius)
        else:
            obj.empty_display_type = "PLAIN_AXES"
            obj.empty_display_size = ObjectiveDefaults.ICON_DISPLAY_SIZE
        return obj

    @classmethod
    def spawn_trigger_node(
        cls,
        scene: Scene,
        sort_order: int,
        blender_pos: Tuple[float, float, float],
        trig_data: Optional[Dict[str, Any]] = None,
    ) -> Object:
        hierarchy = CollectionHelper.ensure_mission_hierarchy(scene)
        src = trig_data or {}
        tname = str(src.get("name", f"Trigger_{sort_order:02d}"))
        obj = bpy.data.objects.new(f"Trig_{sort_order:02d}_{tname}", None)
        CollectionHelper.link_exclusively(obj, hierarchy[CollectionNames.OBJECTIVES_AND_TRIGGERS])
        obj.location = blender_pos
        obj.color = ColorPalette.TRIGGER_VIOLET
        obj.show_name = True

        props = obj.mission_obj
        props.entity_role = EntityRoles.TRIGGER_NODE
        props.trig_sort_order = sort_order
        props.trig_name = tname

        cond = str(src.get("condition", TriggerDefaults.COND_AREA_ENTER))
        props.trig_condition = cond if cond in (
            TriggerDefaults.COND_MISSION_START,
            TriggerDefaults.COND_TIMER,
            TriggerDefaults.COND_AREA_ENTER,
            TriggerDefaults.COND_AREA_LEAVE,
            TriggerDefaults.COND_ENEMY_DESTROYED,
            TriggerDefaults.COND_KILL_COUNT,
            TriggerDefaults.COND_PLAYER_DAMAGED,
            TriggerDefaults.COND_OBJECTIVE_COMPLETE,
        ) else TriggerDefaults.COND_AREA_ENTER

        props.trig_enabled = bool(src.get("isEnabled", True))
        props.trig_repeatable = bool(src.get("isRepeatable", False))
        props.trig_timer_seconds = float(src.get("timerSeconds", TriggerDefaults.DEFAULT_TIMER_SECONDS))
        props.trig_area_radius = float(src.get("areaRadius", TriggerDefaults.DEFAULT_AREA_RADIUS))
        props.trig_fallback_enemy_index = int(src.get("enemyIndex", TriggerDefaults.NO_INDEX))
        props.trig_kill_count = int(src.get("killCount", TriggerDefaults.DEFAULT_KILL_COUNT))
        props.trig_hp_threshold = float(src.get("hpThreshold", TriggerDefaults.DEFAULT_HP_THRESHOLD))
        props.trig_fallback_objective_index = int(src.get("objectiveIndex", TriggerDefaults.NO_INDEX))

        if props.trig_condition in (TriggerDefaults.COND_AREA_ENTER, TriggerDefaults.COND_AREA_LEAVE):
            obj.empty_display_type = "SPHERE"
            obj.empty_display_size = max(ObjectiveDefaults.MIN_AREA_RADIUS, props.trig_area_radius)
        else:
            obj.empty_display_type = "CUBE"
            obj.empty_display_size = TriggerDefaults.ICON_DISPLAY_SIZE
        return obj

    @staticmethod
    def evaluate_canyon_center_engine_x(engine_z: float) -> float:
        """TutorialMissionDirector::EvaluateCanyonCenterX と完全一致する峡谷中心線X座標評価"""
        ctrl_z = WatchtowerDefaults.CANYON_CONTROL_Z
        ctrl_x = WatchtowerDefaults.CANYON_CONTROL_X
        if engine_z <= ctrl_z[MathConstants.ZERO_INT]:
            return ctrl_x[MathConstants.ZERO_INT]
        last_idx = len(ctrl_z) - MathConstants.ONE_INT
        for i in range(last_idx):
            z0 = ctrl_z[i]
            z1 = ctrl_z[i + MathConstants.ONE_INT]
            if engine_z <= z1:
                span = z1 - z0
                t = (engine_z - z0) / span if span > MathConstants.EPSILON else MathConstants.ZERO
                t = max(MathConstants.ZERO, min(MathConstants.UNIT, t))
                smooth_t = t * t * (float(MathConstants.THREE_INT) - MathConstants.TWO * t)
                x0 = ctrl_x[i]
                x1 = ctrl_x[i + MathConstants.ONE_INT]
                return x0 + (x1 - x0) * smooth_t
        return ctrl_x[last_idx]

    @classmethod
    def spawn_watchtower(
        cls,
        scene: Scene,
        obj_name: str,
        blender_pos: Tuple[float, float, float],
        is_incident_tower: bool = False,
    ) -> Object:
        """峡谷監視塔 (OUTPOST_04 種別) を生成し、06_Zadanie00_Events コレクションへ配置する"""
        hierarchy = CollectionHelper.ensure_mission_hierarchy(scene)
        mesh = EntityMeshFactory.get_or_build_outpost_tower_mesh()
        obj = bpy.data.objects.new(obj_name, mesh)
        CollectionHelper.link_exclusively(obj, hierarchy[CollectionNames.ZADANIE00_EVENTS])
        obj.location = blender_pos
        obj.mission_obj.entity_role = EntityRoles.ZADANIE00_MARKER
        obj.mission_obj.z00_marker_kind = Zadanie00MarkerKinds.OUTPOST_04
        obj.show_name = True
        rgba = ColorPalette.OUTPOST_FIRE if is_incident_tower else ColorPalette.OUTPOST_INTACT_TEAL
        mat_name = "Mission_Mat_Z00_OUTPOST_04" if is_incident_tower else "Mission_Mat_Z00_OUTPOST_INTACT"
        EntityMeshFactory.apply_visual_color(obj, mat_name, rgba)
        return obj

    @classmethod
    def generate_canyon_watchtowers(
        cls,
        context: Optional[Context],
        scene: Scene,
    ) -> List[Object]:
        """
        レベルエディタの設定値（watchtower_count, watchtower_lateral_offset, watchtower_alternate_banks）に基づき、
        峡谷ルート沿いの左右の崖へ監視塔群を一括自動配置し、Terrain_FullMap の地面へ自動接地させる。
        """
        settings = scene.mission_settings
        count = max(WatchtowerDefaults.MIN_COUNT, int(settings.watchtower_count))
        lateral_offset = float(settings.watchtower_lateral_offset)
        alternate_banks = bool(settings.watchtower_alternate_banks)

        # 既存の監視塔オブジェクトを一旦削除
        existing_towers = [
            obj
            for obj in list(scene.objects)
            if hasattr(obj, "mission_obj")
            and obj.mission_obj.entity_role == EntityRoles.ZADANIE00_MARKER
            and obj.mission_obj.z00_marker_kind == Zadanie00MarkerKinds.OUTPOST_04
        ]
        for old_obj in existing_towers:
            bpy.data.objects.remove(old_obj, do_unlink=True)

        start_z = WatchtowerDefaults.DEFAULT_START_ENGINE_Z
        end_z = WatchtowerDefaults.DEFAULT_END_ENGINE_Z
        created_towers: List[Object] = []

        for idx in range(count):
            if count == MathConstants.ONE_INT:
                ez = end_z
            else:
                ratio = float(idx) / float(count - MathConstants.ONE_INT)
                ez = start_z + (end_z - start_z) * ratio

            center_x = cls.evaluate_canyon_center_engine_x(ez)
            if alternate_banks:
                bank_sign = (
                    MathConstants.UNIT
                    if (idx % MathConstants.TWO_INT == MathConstants.ZERO_INT)
                    else MathConstants.NEGATIVE_UNIT
                )
            else:
                bank_sign = MathConstants.UNIT

            ex = center_x + bank_sign * lateral_offset
            ey = WatchtowerDefaults.FALLBACK_GROUND_ENGINE_Y
            bx, by, bz = CoordinateTransformer.engine_to_blender_pos(ex, ey, ez)

            if context is not None:
                ground_z = TerrainChunkLoader.sample_terrain_height(context, bx, by)
                if ground_z is not None:
                    bz = ground_z

            is_last = idx == (count - MathConstants.ONE_INT)
            tower_num = idx + MathConstants.ONE_INT
            tower_name = (
                f"Z00_Outpost_{tower_num:02d}_IncidentTower"
                if is_last
                else f"Z00_Outpost_{tower_num:02d}_Watchtower"
            )
            tower_obj = cls.spawn_watchtower(scene, tower_name, (bx, by, bz), is_incident_tower=is_last)
            created_towers.append(tower_obj)

        cls._update_scene_matrices(scene)
        return created_towers

    @classmethod
    def ensure_zadanie00_markers(
        cls,
        scene: Scene,
        layout_dict: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Object]:
        """ZADANIE 00 (Obuchenie) の全空間配置マーカー＆複数監視塔群を生成または更新する"""
        hierarchy = CollectionHelper.ensure_mission_hierarchy(scene)
        existing_by_kind: Dict[str, Object] = {}
        existing_watchtowers: List[Object] = []
        for obj in list(scene.objects):
            if hasattr(obj, "mission_obj") and obj.mission_obj.entity_role == EntityRoles.ZADANIE00_MARKER:
                kind = obj.mission_obj.z00_marker_kind
                if kind == Zadanie00MarkerKinds.OUTPOST_04:
                    existing_watchtowers.append(obj)
                else:
                    existing_by_kind[kind] = obj

        # 1. 複数監視塔 (outpostPositions) の展開
        outpost_eng_list: List[Tuple[float, float, float]] = []
        if layout_dict and "outpostPositions" in layout_dict and layout_dict["outpostPositions"]:
            for pos_d in layout_dict["outpostPositions"]:
                outpost_eng_list.append(
                    (
                        float(pos_d.get("x", MathConstants.ZERO)),
                        float(pos_d.get("y", WatchtowerDefaults.FALLBACK_GROUND_ENGINE_Y)),
                        float(pos_d.get("z", WatchtowerDefaults.DEFAULT_END_ENGINE_Z)),
                    )
                )
        elif layout_dict and "outpostPosition" in layout_dict:
            pos_d = layout_dict["outpostPosition"]
            outpost_eng_list = [
                MissionDefaults.DEFAULT_OUTPOST_01_ENGINE_POS,
                MissionDefaults.DEFAULT_OUTPOST_02_ENGINE_POS,
                MissionDefaults.DEFAULT_OUTPOST_03_ENGINE_POS,
                (
                    float(pos_d.get("x", MissionDefaults.DEFAULT_OUTPOST_ENGINE_POS[MathConstants.ZERO_INT])),
                    float(pos_d.get("y", MissionDefaults.DEFAULT_OUTPOST_ENGINE_POS[MathConstants.ONE_INT])),
                    float(pos_d.get("z", MissionDefaults.DEFAULT_OUTPOST_ENGINE_POS[MathConstants.TWO_INT])),
                ),
            ]
        else:
            outpost_eng_list = list(MissionDefaults.DEFAULT_OUTPOST_POSITIONS)

        for old_wt in existing_watchtowers:
            bpy.data.objects.remove(old_wt, do_unlink=True)

        created_or_found: Dict[str, Object] = {}
        total_wt = len(outpost_eng_list)
        ctx = bpy.context
        for idx, eng_pos in enumerate(outpost_eng_list):
            bx, by, bz = CoordinateTransformer.engine_to_blender_pos(*eng_pos)
            if ctx is not None and getattr(ctx, "scene", None) == scene:
                ground_z = TerrainChunkLoader.sample_terrain_height(ctx, bx, by)
                if ground_z is not None:
                    bz = ground_z
            is_last = idx == (total_wt - MathConstants.ONE_INT)
            tower_num = idx + MathConstants.ONE_INT
            wt_name = (
                f"Z00_Outpost_{tower_num:02d}_IncidentTower"
                if is_last
                else f"Z00_Outpost_{tower_num:02d}_Watchtower"
            )
            wt_obj = cls.spawn_watchtower(scene, wt_name, (bx, by, bz), is_incident_tower=is_last)
            if is_last:
                created_or_found[Zadanie00MarkerKinds.OUTPOST_04] = wt_obj

        if hasattr(scene, "mission_settings") and total_wt >= WatchtowerDefaults.MIN_COUNT:
            scene.mission_settings["_suppress_watchtower_callback"] = True
            scene.mission_settings.watchtower_count = min(WatchtowerDefaults.MAX_COUNT, total_wt)
            scene.mission_settings["_suppress_watchtower_callback"] = False

        # 2. その他の ZADANIE 00 マーカー
        json_key_map = {
            Zadanie00MarkerKinds.CORAX_START: "coraxStartPos",
            Zadanie00MarkerKinds.TRAINING_DRONE: "droneSpawnPosition",
            Zadanie00MarkerKinds.WESTERN_DIVE_START: "westernDiveStart",
            Zadanie00MarkerKinds.WESTERN_DIVE_MID: "westernDiveMid",
            Zadanie00MarkerKinds.WESTERN_PULLUP: "westernPullUp",
            Zadanie00MarkerKinds.EXIT_BOUNDARY: "exitBoundaryPosition",
        }

        for kind, (obj_name, col_name, rgba, default_eng_pos) in cls.Z00_MARKER_SPECS.items():
            if kind == Zadanie00MarkerKinds.OUTPOST_04:
                continue
            json_key = json_key_map[kind]
            if layout_dict and json_key in layout_dict:
                bpos = CoordinateTransformer.engine_dict_to_blender_pos(layout_dict[json_key])
            else:
                bpos = CoordinateTransformer.engine_to_blender_pos(*default_eng_pos)

            marker_obj = existing_by_kind.get(kind)
            if marker_obj is None:
                mesh = cls._build_z00_marker_mesh(scene, kind)
                marker_obj = bpy.data.objects.new(obj_name, mesh)
                CollectionHelper.link_exclusively(marker_obj, hierarchy[col_name])
                marker_obj.mission_obj.entity_role = EntityRoles.ZADANIE00_MARKER
                marker_obj.mission_obj.z00_marker_kind = kind
                marker_obj.show_name = True
                if kind == Zadanie00MarkerKinds.TRAINING_DRONE:
                    s = GizmoDimensions.DRONE_SCALE
                    marker_obj.scale = (s, s, s)
                EntityMeshFactory.apply_visual_color(marker_obj, f"Mission_Mat_Z00_{kind}", rgba)

            if layout_dict is not None or marker_obj.name not in scene.objects:
                marker_obj.location = bpos

            created_or_found[kind] = marker_obj

        cls.refresh_zadanie00_ambush_curve(scene)
        return created_or_found

    @staticmethod
    def _build_z00_marker_mesh(scene: Scene, kind: str):
        if kind == Zadanie00MarkerKinds.CORAX_START:
            return EntityMeshFactory.get_or_build_fighter_mesh(scene, PathConstants.MODEL_M21_REL)
        if kind == Zadanie00MarkerKinds.OUTPOST_04:
            return EntityMeshFactory.get_or_build_outpost_tower_mesh()
        if kind == Zadanie00MarkerKinds.EXIT_BOUNDARY:
            return EntityMeshFactory.get_or_build_ring_gate_mesh(
                GizmoDimensions.EXIT_GATE_RADIUS, "Mission_Zadanie00_ExitGate_Mesh"
            )
        return EntityMeshFactory.get_or_build_fighter_mesh(scene, PathConstants.MODEL_M15_REL)

    @staticmethod
    def _update_scene_matrices(scene: Scene) -> None:
        """obj.location 変更直後でも matrix_world が最新値を返すよう全 ViewLayer を同期する"""
        for vl in scene.view_layers:
            vl.update()

    @classmethod
    def refresh_zadanie00_ambush_curve(cls, scene: Scene) -> None:
        """
        ZADANIE 00 Phase 6 西側機急襲ベジェパス (DiveStart -> FlybyMid -> PullUp) の3Dプレビュー曲線を更新する。
        TutorialMissionDirector.cpp と同一の2次ベジェ曲線で描画する。
        """
        cls._update_scene_matrices(scene)
        markers: Dict[str, Object] = {}
        for obj in scene.objects:
            if hasattr(obj, "mission_obj") and obj.mission_obj.entity_role == EntityRoles.ZADANIE00_MARKER:
                markers[obj.mission_obj.z00_marker_kind] = obj

        req_kinds = (
            Zadanie00MarkerKinds.WESTERN_DIVE_START,
            Zadanie00MarkerKinds.WESTERN_DIVE_MID,
            Zadanie00MarkerKinds.WESTERN_PULLUP,
        )
        if not scene.mission_settings.is_zadanie_00_mode or not all(k in markers for k in req_kinds):
            preview = bpy.data.objects.get(GizmoDimensions.AMBUSH_PREVIEW_NAME)
            if preview is not None:
                cdata = preview.data
                bpy.data.objects.remove(preview, do_unlink=True)
                if cdata is not None and cdata.users == MathConstants.ZERO_INT:
                    bpy.data.curves.remove(cdata)
            return

        p0 = markers[Zadanie00MarkerKinds.WESTERN_DIVE_START].matrix_world.translation
        p1 = markers[Zadanie00MarkerKinds.WESTERN_DIVE_MID].matrix_world.translation
        p2 = markers[Zadanie00MarkerKinds.WESTERN_PULLUP].matrix_world.translation

        hierarchy = CollectionHelper.ensure_mission_hierarchy(scene)
        preview_obj = bpy.data.objects.get(GizmoDimensions.AMBUSH_PREVIEW_NAME)
        seg_count = GizmoDimensions.CYLINDER_SEGMENTS
        total_pts = seg_count + MathConstants.ONE_INT

        if preview_obj is None or preview_obj.type != "CURVE":
            curve_data = bpy.data.curves.new(GizmoDimensions.AMBUSH_PREVIEW_NAME, type="CURVE")
            curve_data.dimensions = "3D"
            curve_data.bevel_depth = GizmoDimensions.AMBUSH_PREVIEW_BEVEL
            mat = EntityMeshFactory.get_or_create_material(
                "Mission_Mat_Z00_AmbushCurve", ColorPalette.WESTERN_AMBUSH_CRIMSON
            )
            curve_data.materials.append(mat)
            spline = curve_data.splines.new(type="POLY")
            spline.points.add(seg_count)
            preview_obj = bpy.data.objects.new(GizmoDimensions.AMBUSH_PREVIEW_NAME, curve_data)
            CollectionHelper.link_exclusively(preview_obj, hierarchy[CollectionNames.ZADANIE00_EVENTS])
            preview_obj.hide_select = True
            preview_obj.color = ColorPalette.WESTERN_AMBUSH_CRIMSON

        spline = preview_obj.data.splines[MathConstants.ZERO_INT]
        if len(spline.points) != total_pts:
            preview_obj.data.splines.clear()
            spline = preview_obj.data.splines.new(type="POLY")
            spline.points.add(seg_count)

        for idx in range(total_pts):
            t = float(idx) / float(seg_count)
            omt = MathConstants.UNIT - t
            pos = (omt * omt) * p0 + (MathConstants.TWO * omt * t) * p1 + (t * t) * p2
            spline.points[idx].co = (pos.x, pos.y, pos.z, EnemyDefaults.SPLINE_CO_HOMOGENEOUS_W)

    # =========================================================================
    # JSON インポート (missionXX.json -> Blender Scene)
    # =========================================================================

    @classmethod
    def import_mission_json(cls, context: Context, filepath: str) -> Tuple[bool, str]:
        scene = context.scene
        settings = scene.mission_settings
        resolved_file = RepoPathResolver.resolve_path(scene, filepath)
        if not resolved_file.exists():
            return (False, f"ミッションJSONが存在しません: {resolved_file}")

        with open(resolved_file, "r", encoding="utf-8") as fp:
            data = json.load(fp)

        cls.clear_mission_entities(scene)

        repo_root = RepoPathResolver.resolve_repo_root(scene)
        try:
            rel_str = str(resolved_file.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            rel_str = str(resolved_file).replace("\\", "/")
        settings.mission_file_path = rel_str

        # missions.json から ID・ロック状態を同期
        manifest_entry = cls._find_manifest_entry(scene, rel_str)
        if manifest_entry is not None:
            settings.mission_id = str(manifest_entry.get("id", settings.mission_id))
            settings.is_locked = bool(manifest_entry.get("isLocked", False))

        settings.mission_name = str(data.get("name", MissionDefaults.ZADANIE_00_NAME))
        settings.alias_name = str(data.get("aliasName", ""))
        settings.sub_title = str(data.get("subTitle", ""))
        diff = str(data.get("difficulty", MissionDefaults.NEW_MISSION_DIFFICULTY))
        settings.difficulty = (
            diff if diff in ("TUTORIAL", "EASY", "NORMAL", "HARD", "EXPERT") else MissionDefaults.NEW_MISSION_DIFFICULTY
        )
        settings.area_name = str(data.get("areaName", ""))
        settings.description = str(data.get("description", ""))
        settings.player_hp = float(data.get("playerHP", MissionDefaults.DEFAULT_PLAYER_HP))
        settings.time_limit = float(data.get("timeLimit", MissionDefaults.UNLIMITED_TIME_LIMIT))

        # ZADANIE 00 判定
        tut_layout = data.get("tutorialLayout", {})
        is_z00 = (
            bool(tut_layout.get("useCustomLayout", False))
            or settings.alias_name == MissionDefaults.ZADANIE_00_ALIAS
            or settings.mission_name in (MissionDefaults.ZADANIE_00_NAME, MissionDefaults.LEGACY_TUTORIAL_NAME)
            or rel_str.endswith("mission00.json")
        )
        settings.is_zadanie_00_mode = is_z00

        # 1. プレイヤー初期位置・方位
        player_bpos = CoordinateTransformer.engine_dict_to_blender_pos(
            data.get(
                "playerPosition",
                {
                    "x": MissionDefaults.DEFAULT_PLAYER_ENGINE_POS[MathConstants.ZERO_INT],
                    "y": MissionDefaults.DEFAULT_PLAYER_ENGINE_POS[MathConstants.ONE_INT],
                    "z": MissionDefaults.DEFAULT_PLAYER_ENGINE_POS[MathConstants.TWO_INT],
                },
            )
        )
        player_yaw = float(data.get("playerYawDeg", MathConstants.ZERO))
        cls.spawn_player_start(scene, player_bpos, player_yaw)

        # 2. ウェイポイント経路
        for wp_path in data.get("waypointPaths", []):
            pname = str(wp_path.get("name", "Patrol_Route"))
            is_loop = bool(wp_path.get("isLoop", False))
            pts_bl: List[Tuple[Tuple[float, float, float], float]] = []
            for pt in wp_path.get("points", []):
                bpos = CoordinateTransformer.engine_dict_to_blender_pos(pt.get("position", {}))
                spd = float(pt.get("speed", EnemyDefaults.DEFAULT_WAYPOINT_SPEED_KMH))
                pts_bl.append((bpos, spd))
            cls.spawn_waypoint_route(scene, pname, is_loop, pts_bl)

        # 3. 初期配置の空中敵 & 地上敵
        initial_air_objs: List[Object] = []
        for idx, air in enumerate(data.get("enemies", [])):
            bpos = CoordinateTransformer.engine_dict_to_blender_pos(air.get("position", {}))
            obj = cls.spawn_air_enemy(
                scene=scene,
                obj_name=f"AirEnemy_{idx:02d}",
                blender_pos=bpos,
                model_path=str(air.get("modelPath", PathConstants.MODEL_M15_REL)),
                health=float(air.get("health", EnemyDefaults.DEFAULT_HEALTH)),
                ai_type=str(air.get("aiType", EnemyDefaults.AI_CHASE_ATTACK)),
                waypoint_path_name=str(air.get("waypointPathName", "")),
                spawn_trigger_name="",
            )
            initial_air_objs.append(obj)

        initial_ground_objs: List[Object] = []
        for idx, gnd in enumerate(data.get("groundEnemies", [])):
            bpos = CoordinateTransformer.engine_dict_to_blender_pos(gnd.get("position", {}))
            gtype = str(gnd.get("aiType", GroundDefaults.AI_TURRET))
            obj = cls.spawn_ground_enemy(
                scene=scene,
                obj_name=f"GroundTarget_{idx:02d}_{gtype}",
                blender_pos=bpos,
                ground_ai_type=gtype,
                health=float(gnd.get("health", GroundDefaults.TURRET_HEALTH)),
                param_dict=gnd.get("param"),
                waypoint_path_name=str(gnd.get("waypointPathName", "")),
                spawn_trigger_name="",
            )
            initial_ground_objs.append(obj)

        initial_units = initial_air_objs + initial_ground_objs

        # 4. ミッション目標
        objective_objs: List[Object] = []
        for idx, odict in enumerate(data.get("objectives", [])):
            bpos = CoordinateTransformer.engine_dict_to_blender_pos(odict.get("areaCenter", {}))
            o_obj = cls.spawn_objective_node(scene, idx, bpos, odict)
            t_idx = int(odict.get("targetIndex", ObjectiveDefaults.NO_TARGET_INDEX))
            if MathConstants.ZERO_INT <= t_idx < len(initial_units):
                o_obj.mission_obj.obj_target_unit = initial_units[t_idx]
            objective_objs.append(o_obj)

        # 5. ゲームプレイトリガー（増援ユニット展開 + 既存 PlayRadioDialogue の無劣化キャッシュ）
        preserved_radio_map: Dict[str, List[Dict[str, Any]]] = {}
        trigger_objs: List[Tuple[Object, Dict[str, Any]]] = []
        for idx, tdict in enumerate(data.get("triggers", [])):
            bpos = CoordinateTransformer.engine_dict_to_blender_pos(tdict.get("areaCenter", {}))
            t_obj = cls.spawn_trigger_node(scene, idx, bpos, tdict)
            tname = t_obj.mission_obj.trig_name

            e_idx = int(tdict.get("enemyIndex", TriggerDefaults.NO_INDEX))
            if MathConstants.ZERO_INT <= e_idx < len(initial_units):
                t_obj.mission_obj.trig_target_enemy = initial_units[e_idx]

            o_idx = int(tdict.get("objectiveIndex", TriggerDefaults.NO_INDEX))
            if MathConstants.ZERO_INT <= o_idx < len(objective_objs):
                t_obj.mission_obj.trig_target_objective = objective_objs[o_idx]

            radio_actions: List[Dict[str, Any]] = []
            primary_gameplay_assigned = False
            for act_idx, act in enumerate(tdict.get("actions", [])):
                atype = str(act.get("type", TriggerDefaults.ACT_SHOW_MESSAGE))
                if atype == TriggerDefaults.ACT_PLAY_RADIO_PRESERVED:
                    radio_actions.append(act)
                    continue

                if atype == TriggerDefaults.ACT_SPAWN_ENEMIES:
                    for s_idx, sair in enumerate(act.get("spawnEnemies", [])):
                        sbpos = CoordinateTransformer.engine_dict_to_blender_pos(sair.get("position", {}))
                        cls.spawn_air_enemy(
                            scene=scene,
                            obj_name=f"ReinforceAir_{tname}_{s_idx:02d}",
                            blender_pos=sbpos,
                            model_path=str(sair.get("modelPath", PathConstants.MODEL_M15_REL)),
                            health=float(sair.get("health", EnemyDefaults.DEFAULT_HEALTH)),
                            ai_type=str(sair.get("aiType", EnemyDefaults.AI_CHASE_ATTACK)),
                            waypoint_path_name=str(sair.get("waypointPathName", "")),
                            spawn_trigger_name=tname,
                        )
                    for g_idx, sgnd in enumerate(act.get("spawnGroundEnemies", [])):
                        gbpos = CoordinateTransformer.engine_dict_to_blender_pos(sgnd.get("position", {}))
                        gtype = str(sgnd.get("aiType", GroundDefaults.AI_TURRET))
                        cls.spawn_ground_enemy(
                            scene=scene,
                            obj_name=f"ReinforceGnd_{tname}_{g_idx:02d}",
                            blender_pos=gbpos,
                            ground_ai_type=gtype,
                            health=float(sgnd.get("health", GroundDefaults.TURRET_HEALTH)),
                            param_dict=sgnd.get("param"),
                            waypoint_path_name=str(sgnd.get("waypointPathName", "")),
                            spawn_trigger_name=tname,
                        )

                if not primary_gameplay_assigned:
                    t_obj.mission_obj.trig_action_type = atype
                    t_obj.mission_obj.trig_hud_message = str(act.get("message", ""))
                    t_obj.mission_obj.trig_hud_message_duration = float(
                        act.get("messageDuration", TriggerDefaults.DEFAULT_MSG_DURATION)
                    )
                    t_obj.mission_obj.trig_set_obj_fallback_index = int(
                        act.get("objectiveIndex", TriggerDefaults.NO_INDEX)
                    )
                    nstatus = str(act.get("newStatus", ObjectiveDefaults.STATUS_ACTIVE))
                    if nstatus in (
                        ObjectiveDefaults.STATUS_ACTIVE,
                        ObjectiveDefaults.STATUS_COMPLETED,
                        ObjectiveDefaults.STATUS_FAILED,
                    ):
                        t_obj.mission_obj.trig_set_obj_status = nstatus
                    t_obj.mission_obj.trig_activate_fallback_index = int(
                        act.get("activateTriggerIndex", TriggerDefaults.NO_INDEX)
                    )
                    set_oidx = t_obj.mission_obj.trig_set_obj_fallback_index
                    if MathConstants.ZERO_INT <= set_oidx < len(objective_objs):
                        t_obj.mission_obj.trig_set_obj_target = objective_objs[set_oidx]
                    primary_gameplay_assigned = True

            if radio_actions:
                preserved_radio_map[tname] = radio_actions
            trigger_objs.append((t_obj, tdict))

        # ActivateTrigger の後続トリガー Pointer 解決
        all_trig_list = [pair[MathConstants.ZERO_INT] for pair in trigger_objs]
        for t_obj, _raw in trigger_objs:
            act_idx = t_obj.mission_obj.trig_activate_fallback_index
            if MathConstants.ZERO_INT <= act_idx < len(all_trig_list):
                t_obj.mission_obj.trig_activate_target = all_trig_list[act_idx]

        settings.preserved_radio_json = json.dumps(preserved_radio_map, ensure_ascii=False)

        # 6. ZADANIE 00 専用マーカー展開
        if is_z00:
            cls.ensure_zadanie00_markers(scene, tut_layout if tut_layout else {})

        return (True, f"インポート完了: {settings.alias_name or settings.mission_name} ({rel_str})")

    # =========================================================================
    # シーン -> MissionData Dict 構築 (Live Sync & JSON Export 共通)
    # =========================================================================

    @classmethod
    def build_mission_dict(cls, scene: Scene) -> Dict[str, Any]:
        cls._update_scene_matrices(scene)
        settings = scene.mission_settings

        player_obj: Optional[Object] = None
        initial_air_objs: List[Object] = []
        initial_ground_objs: List[Object] = []
        reinforce_air_by_trig: Dict[str, List[Object]] = {}
        reinforce_gnd_by_trig: Dict[str, List[Object]] = {}
        route_objs: List[Object] = []
        objective_objs: List[Object] = []
        trigger_objs: List[Object] = []
        z00_markers: Dict[str, Object] = {}
        watchtower_objs: List[Object] = []

        for obj in scene.objects:
            if not hasattr(obj, "mission_obj"):
                continue
            role = obj.mission_obj.entity_role
            if role == EntityRoles.NONE:
                continue
            if role == EntityRoles.PLAYER_START:
                player_obj = obj
            elif role == EntityRoles.AIR_ENEMY:
                trig_key = obj.mission_obj.spawn_trigger_name.strip()
                if trig_key:
                    reinforce_air_by_trig.setdefault(trig_key, []).append(obj)
                else:
                    initial_air_objs.append(obj)
            elif role == EntityRoles.GROUND_ENEMY:
                trig_key = obj.mission_obj.spawn_trigger_name.strip()
                if trig_key:
                    reinforce_gnd_by_trig.setdefault(trig_key, []).append(obj)
                else:
                    initial_ground_objs.append(obj)
            elif role == EntityRoles.WAYPOINT_PATH and obj.type == "CURVE":
                route_objs.append(obj)
            elif role == EntityRoles.OBJECTIVE_NODE:
                objective_objs.append(obj)
            elif role == EntityRoles.TRIGGER_NODE:
                trigger_objs.append(obj)
            elif role == EntityRoles.ZADANIE00_MARKER:
                mkind = obj.mission_obj.z00_marker_kind
                if mkind == Zadanie00MarkerKinds.OUTPOST_04:
                    watchtower_objs.append(obj)
                z00_markers[mkind] = obj

        # 監視塔を南から北（DirectX Engine Z昇順 ＝ Blender Y降順）にソート
        watchtower_objs.sort(key=lambda o: (-o.matrix_world.translation.y, o.name))
        if watchtower_objs:
            z00_markers[Zadanie00MarkerKinds.OUTPOST_04] = watchtower_objs[MathConstants.NEGATIVE_ONE_INT]

        initial_air_objs.sort(key=lambda o: o.name)
        initial_ground_objs.sort(key=lambda o: o.name)
        route_objs.sort(key=lambda o: o.name)
        objective_objs.sort(key=lambda o: (o.mission_obj.obj_sort_order, o.name))
        trigger_objs.sort(key=lambda o: (o.mission_obj.trig_sort_order, o.name))

        # ユニット・目標・トリガーのインデックス解決マップ
        initial_units = initial_air_objs + initial_ground_objs
        unit_index_map = {obj: idx for idx, obj in enumerate(initial_units)}
        obj_index_map = {obj: idx for idx, obj in enumerate(objective_objs)}
        trig_index_map = {obj: idx for idx, obj in enumerate(trigger_objs)}

        # 自機座標・方位
        if player_obj is not None:
            pw = player_obj.matrix_world.translation
            player_pos_dict = CoordinateTransformer.blender_to_engine_dict(pw.x, pw.y, pw.z)
            player_yaw = CoordinateTransformer.blender_rot_z_to_engine_yaw_deg(player_obj.rotation_euler.z)
        else:
            def_px, def_py, def_pz = MissionDefaults.DEFAULT_PLAYER_ENGINE_POS
            player_pos_dict = {"x": def_px, "y": def_py, "z": def_pz}
            player_yaw = MathConstants.ZERO

        enemies_json = [cls._serialize_air_enemy(o) for o in initial_air_objs]
        ground_json = [cls._serialize_ground_enemy(o) for o in initial_ground_objs]
        waypoints_json = [cls._serialize_waypoint_route(o) for o in route_objs]
        objectives_json = [cls._serialize_objective(o, unit_index_map) for o in objective_objs]

        try:
            preserved_radio_map = json.loads(settings.preserved_radio_json or "{}")
        except Exception:
            preserved_radio_map = {}

        triggers_json = [
            cls._serialize_trigger(
                t_obj,
                unit_index_map=unit_index_map,
                obj_index_map=obj_index_map,
                trig_index_map=trig_index_map,
                reinforce_air=reinforce_air_by_trig.get(t_obj.mission_obj.trig_name.strip(), []),
                reinforce_gnd=reinforce_gnd_by_trig.get(t_obj.mission_obj.trig_name.strip(), []),
                preserved_radios=preserved_radio_map.get(t_obj.mission_obj.trig_name.strip(), []),
            )
            for t_obj in trigger_objs
        ]

        mission_dict: Dict[str, Any] = {
            "name": settings.mission_name,
            "aliasName": settings.alias_name,
            "subTitle": settings.sub_title,
            "difficulty": settings.difficulty,
            "areaName": settings.area_name,
            "description": settings.description,
            "playerHP": round(settings.player_hp, MathConstants.ROUND_DIGITS),
            "playerPosition": player_pos_dict,
            "playerYawDeg": player_yaw,
            "timeLimit": round(settings.time_limit, MathConstants.ROUND_DIGITS),
            "enemies": enemies_json,
            "groundEnemies": ground_json,
            "objectives": objectives_json,
            "triggers": triggers_json,
            "waypointPaths": waypoints_json,
        }

        if settings.is_zadanie_00_mode:
            mission_dict["tutorialLayout"] = cls._serialize_z00_layout(z00_markers, watchtower_objs)

        return mission_dict

    # =========================================================================
    # JSON エクスポート & missions.json 更新
    # =========================================================================

    @classmethod
    def export_mission_json(cls, context: Context, filepath: Optional[str] = None) -> Tuple[bool, str]:
        scene = context.scene
        settings = scene.mission_settings
        target_rel_or_abs = filepath if filepath else settings.mission_file_path
        resolved_out = RepoPathResolver.resolve_path(scene, target_rel_or_abs)
        resolved_out.parent.mkdir(parents=True, exist_ok=True)

        mission_dict = cls.build_mission_dict(scene)
        with open(resolved_out, "w", encoding="utf-8") as fp:
            json.dump(mission_dict, fp, indent=PathConstants.JSON_INDENT, ensure_ascii=False)
            fp.write("\n")

        repo_root = RepoPathResolver.resolve_repo_root(scene)
        try:
            rel_str = str(resolved_out.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            rel_str = str(resolved_out).replace("\\", "/")
        settings.mission_file_path = rel_str

        if settings.update_manifest:
            cls._upsert_manifest_entry(scene, rel_str)

        return (True, f"エクスポート完了: {rel_str}")

    # =========================================================================
    # 個別要素シリアライズ内部メソッド
    # =========================================================================

    @staticmethod
    def _serialize_air_enemy(obj: Object) -> Dict[str, Any]:
        props = obj.mission_obj
        loc = obj.matrix_world.translation
        model_path = (
            props.air_custom_model_path
            if props.air_model_preset == "CUSTOM"
            else props.air_model_preset
        )
        return {
            "position": CoordinateTransformer.blender_to_engine_dict(loc.x, loc.y, loc.z),
            "modelPath": model_path,
            "health": round(props.air_health, MathConstants.ROUND_DIGITS),
            "aiType": props.air_ai_type,
            "waypointPathName": props.waypoint_path_name.strip(),
        }

    @staticmethod
    def _serialize_ground_enemy(obj: Object) -> Dict[str, Any]:
        props = obj.mission_obj
        loc = obj.matrix_world.translation
        hp = round(props.ground_health, MathConstants.ROUND_DIGITS)
        return {
            "position": CoordinateTransformer.blender_to_engine_dict(loc.x, loc.y, loc.z),
            "aiType": props.ground_ai_type,
            "health": hp,
            "waypointPathName": props.waypoint_path_name.strip(),
            "param": {
                "maxHealth": hp,
                "collisionRadius": round(props.collision_radius, MathConstants.ROUND_DIGITS),
                "fireRange": round(props.fire_range, MathConstants.ROUND_DIGITS),
                "minElevationDeg": round(props.min_elevation_deg, MathConstants.ROUND_DIGITS),
                "maxElevationDeg": round(props.max_elevation_deg, MathConstants.ROUND_DIGITS),
                "turnSpeedDeg": round(props.turn_speed_deg, MathConstants.ROUND_DIGITS),
                "bulletSpeed": round(props.bullet_speed, MathConstants.ROUND_DIGITS),
                "bulletDamage": round(props.bullet_damage, MathConstants.ROUND_DIGITS),
                "fireInterval": round(props.fire_interval, MathConstants.ROUND_DIGITS),
                "burstCount": int(props.burst_count),
                "burstCooldown": round(props.burst_cooldown, MathConstants.ROUND_DIGITS),
                "moveSpeed": round(props.move_speed, MathConstants.ROUND_DIGITS),
                "patrolDistance": round(props.patrol_distance, MathConstants.ROUND_DIGITS),
            },
        }

    @staticmethod
    def _serialize_waypoint_route(obj: Object) -> Dict[str, Any]:
        props = obj.mission_obj
        mw = obj.matrix_world
        base_spd = props.default_point_speed_kmh
        points_out: List[Dict[str, Any]] = []
        is_loop = props.path_is_loop

        if obj.data is not None and len(obj.data.splines) > MathConstants.ZERO_INT:
            spline = obj.data.splines[MathConstants.ZERO_INT]
            is_loop = bool(props.path_is_loop or spline.use_cyclic_u)
            if spline.type == "BEZIER":
                for bp in spline.bezier_points:
                    wco = mw @ bp.co
                    points_out.append(
                        {
                            "position": CoordinateTransformer.blender_to_engine_dict(wco.x, wco.y, wco.z),
                            "speed": round(base_spd, MathConstants.ROUND_DIGITS),
                        }
                    )
            else:
                for pt in spline.points:
                    wco = mw @ Vector((pt.co.x, pt.co.y, pt.co.z))
                    w_factor = pt.weight if pt.weight > MathConstants.EPSILON else EnemyDefaults.DEFAULT_SPLINE_WEIGHT
                    points_out.append(
                        {
                            "position": CoordinateTransformer.blender_to_engine_dict(wco.x, wco.y, wco.z),
                            "speed": round(base_spd * w_factor, MathConstants.ROUND_DIGITS),
                        }
                    )

        return {
            "name": props.path_name.strip() or obj.name,
            "isLoop": is_loop,
            "points": points_out,
        }

    @staticmethod
    def _serialize_objective(obj: Object, unit_index_map: Dict[Object, int]) -> Dict[str, Any]:
        props = obj.mission_obj
        loc = obj.matrix_world.translation
        if props.obj_target_unit is not None and props.obj_target_unit in unit_index_map:
            resolved_target = unit_index_map[props.obj_target_unit]
        else:
            resolved_target = props.obj_fallback_target_index

        return {
            "name": props.obj_name,
            "description": props.obj_description,
            "type": props.obj_type,
            "status": props.obj_status,
            "isPrimary": bool(props.obj_is_primary),
            "isHidden": bool(props.obj_is_hidden),
            "requiredKills": int(props.obj_required_kills),
            "targetIndex": int(resolved_target),
            "areaCenter": CoordinateTransformer.blender_to_engine_dict(loc.x, loc.y, loc.z),
            "areaRadius": round(props.obj_area_radius, MathConstants.ROUND_DIGITS),
            "duration": round(props.obj_duration, MathConstants.ROUND_DIGITS),
            "minHP": round(props.obj_min_hp, MathConstants.ROUND_DIGITS),
        }

    @classmethod
    def _serialize_trigger(
        cls,
        obj: Object,
        unit_index_map: Dict[Object, int],
        obj_index_map: Dict[Object, int],
        trig_index_map: Dict[Object, int],
        reinforce_air: List[Object],
        reinforce_gnd: List[Object],
        preserved_radios: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        props = obj.mission_obj
        loc = obj.matrix_world.translation

        enemy_idx = (
            unit_index_map[props.trig_target_enemy]
            if props.trig_target_enemy in unit_index_map
            else props.trig_fallback_enemy_index
        )
        cond_obj_idx = (
            obj_index_map[props.trig_target_objective]
            if props.trig_target_objective in obj_index_map
            else props.trig_fallback_objective_index
        )
        act_set_obj_idx = (
            obj_index_map[props.trig_set_obj_target]
            if props.trig_set_obj_target in obj_index_map
            else props.trig_set_obj_fallback_index
        )
        act_next_trig_idx = (
            trig_index_map[props.trig_activate_target]
            if props.trig_activate_target in trig_index_map
            else props.trig_activate_fallback_index
        )

        reinforce_air_sorted = sorted(reinforce_air, key=lambda o: o.name)
        reinforce_gnd_sorted = sorted(reinforce_gnd, key=lambda o: o.name)

        gameplay_action: Dict[str, Any] = {
            "type": props.trig_action_type,
            "message": props.trig_hud_message,
            "messageDuration": round(props.trig_hud_message_duration, MathConstants.ROUND_DIGITS),
            "objectiveIndex": int(act_set_obj_idx),
            "newStatus": props.trig_set_obj_status,
            "activateTriggerIndex": int(act_next_trig_idx),
        }
        if props.trig_action_type == TriggerDefaults.ACT_SPAWN_ENEMIES or reinforce_air_sorted or reinforce_gnd_sorted:
            if reinforce_air_sorted:
                gameplay_action["spawnEnemies"] = [cls._serialize_air_enemy(o) for o in reinforce_air_sorted]
            if reinforce_gnd_sorted:
                gameplay_action["spawnGroundEnemies"] = [cls._serialize_ground_enemy(o) for o in reinforce_gnd_sorted]

        actions_list = [gameplay_action]
        for r_act in preserved_radios:
            actions_list.append(r_act)

        return {
            "name": props.trig_name.strip() or obj.name,
            "condition": props.trig_condition,
            "isEnabled": bool(props.trig_enabled),
            "isRepeatable": bool(props.trig_repeatable),
            "timerSeconds": round(props.trig_timer_seconds, MathConstants.ROUND_DIGITS),
            "areaCenter": CoordinateTransformer.blender_to_engine_dict(loc.x, loc.y, loc.z),
            "areaRadius": round(props.trig_area_radius, MathConstants.ROUND_DIGITS),
            "enemyIndex": int(enemy_idx),
            "killCount": int(props.trig_kill_count),
            "hpThreshold": round(props.trig_hp_threshold, MathConstants.ROUND_DIGITS),
            "objectiveIndex": int(cond_obj_idx),
            "actions": actions_list,
        }

    @classmethod
    def _serialize_z00_layout(
        cls,
        z00_markers: Dict[str, Object],
        watchtower_objs: Optional[List[Object]] = None,
    ) -> Dict[str, Any]:
        def _resolve_marker(kind: str, fallback_eng: Tuple[float, float, float]) -> Dict[str, float]:
            m_obj = z00_markers.get(kind)
            if m_obj is not None:
                loc = m_obj.matrix_world.translation
                return CoordinateTransformer.blender_to_engine_dict(loc.x, loc.y, loc.z)
            return {
                "x": fallback_eng[MathConstants.ZERO_INT],
                "y": fallback_eng[MathConstants.ONE_INT],
                "z": fallback_eng[MathConstants.TWO_INT],
            }

        outpost_positions_list: List[Dict[str, float]] = []
        if watchtower_objs:
            for wt_obj in watchtower_objs:
                wloc = wt_obj.matrix_world.translation
                outpost_positions_list.append(CoordinateTransformer.blender_to_engine_dict(wloc.x, wloc.y, wloc.z))
        else:
            for def_pos in MissionDefaults.DEFAULT_OUTPOST_POSITIONS:
                outpost_positions_list.append(
                    {
                        "x": def_pos[MathConstants.ZERO_INT],
                        "y": def_pos[MathConstants.ONE_INT],
                        "z": def_pos[MathConstants.TWO_INT],
                    }
                )

        primary_outpost = (
            outpost_positions_list[MathConstants.NEGATIVE_ONE_INT]
            if outpost_positions_list
            else _resolve_marker(Zadanie00MarkerKinds.OUTPOST_04, MissionDefaults.DEFAULT_OUTPOST_ENGINE_POS)
        )

        return {
            "useCustomLayout": True,
            "coraxStartPos": _resolve_marker(
                Zadanie00MarkerKinds.CORAX_START, MissionDefaults.DEFAULT_CORAX_ENGINE_POS
            ),
            "outpostPosition": primary_outpost,
            "outpostPositions": outpost_positions_list,
            "droneSpawnPosition": _resolve_marker(
                Zadanie00MarkerKinds.TRAINING_DRONE, MissionDefaults.DEFAULT_DRONE_ENGINE_POS
            ),
            "westernDiveStart": _resolve_marker(
                Zadanie00MarkerKinds.WESTERN_DIVE_START, MissionDefaults.DEFAULT_WEST_START_ENGINE_POS
            ),
            "westernDiveMid": _resolve_marker(
                Zadanie00MarkerKinds.WESTERN_DIVE_MID, MissionDefaults.DEFAULT_WEST_MID_ENGINE_POS
            ),
            "westernPullUp": _resolve_marker(
                Zadanie00MarkerKinds.WESTERN_PULLUP, MissionDefaults.DEFAULT_WEST_PULLUP_ENGINE_POS
            ),
            "exitBoundaryPosition": _resolve_marker(
                Zadanie00MarkerKinds.EXIT_BOUNDARY, MissionDefaults.DEFAULT_EXIT_ENGINE_POS
            ),
        }

    # =========================================================================
    # missions.json マニフェスト同期
    # =========================================================================

    @staticmethod
    def _find_manifest_entry(scene: Scene, rel_filepath: str) -> Optional[Dict[str, Any]]:
        manifest_path = RepoPathResolver.resolve_path(scene, PathConstants.MANIFEST_REL_PATH)
        if not manifest_path.exists():
            return None
        try:
            with open(manifest_path, "r", encoding="utf-8") as fp:
                manifest = json.load(fp)
            norm_target = rel_filepath.replace("\\", "/")
            for entry in manifest.get("missions", []):
                if str(entry.get("filePath", "")).replace("\\", "/") == norm_target:
                    return entry
        except Exception:
            return None
        return None

    @staticmethod
    def _upsert_manifest_entry(scene: Scene, rel_filepath: str) -> None:
        settings = scene.mission_settings
        manifest_path = RepoPathResolver.resolve_path(scene, PathConstants.MANIFEST_REL_PATH)
        manifest_data: Dict[str, Any] = {"version": PathConstants.MANIFEST_VERSION, "missions": []}
        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as fp:
                    manifest_data = json.load(fp)
            except Exception:
                pass

        entries: List[Dict[str, Any]] = manifest_data.setdefault("missions", [])
        norm_target = rel_filepath.replace("\\", "/")
        new_entry = {
            "id": settings.mission_id,
            "filePath": norm_target,
            "title": settings.mission_name,
            "aliasName": settings.alias_name,
            "subTitle": settings.sub_title,
            "isLocked": bool(settings.is_locked),
        }

        updated = False
        for idx, entry in enumerate(entries):
            if (
                str(entry.get("filePath", "")).replace("\\", "/") == norm_target
                or str(entry.get("id", "")) == settings.mission_id
            ):
                entries[idx] = new_entry
                updated = True
                break

        if not updated:
            entries.append(new_entry)
            entries.sort(key=lambda item: str(item.get("id", "")))

        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(manifest_path, "w", encoding="utf-8") as fp:
            json.dump(manifest_data, fp, indent=PathConstants.JSON_INDENT, ensure_ascii=False)
            fp.write("\n")