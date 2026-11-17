# -*- coding: utf-8 -*-
"""
Mission Editor - 定数一元管理モジュール (マジックナンバー完全禁止)
すべての数値・識別子・色・既定パラメータをクラス定数として定義します。
"""


class AddonMeta:
    """Blender アドオンメタデータ定数"""
    BL_NAME = "レベルエディタ (Mission)"
    BL_AUTHOR = "Daiki Takanaga"
    BL_DESCRIPTION = (
        "会話・チュートリアル進行以外の全ミッション要素（地形・機体・地上目標・経路・目標・トリガー・ZADANIE 00配置）"
        "を構築し、DirectX実機とHTTPライブ同期するエディタ"
    )
    BL_CATEGORY = "Object"
    VERSION_MAJOR = 1
    VERSION_MINOR = 0
    VERSION_PATCH = 0
    BLENDER_MIN_MAJOR = 3
    BLENDER_MIN_MINOR = 6
    BLENDER_MIN_PATCH = 0


class MathConstants:
    """基本数学・変換定数"""
    ZERO_INT = 0
    ONE_INT = 1
    TWO_INT = 2
    THREE_INT = 3
    FOUR_INT = 4
    NEGATIVE_ONE_INT = -1

    ZERO = 0.0
    HALF = 0.5
    UNIT = 1.0
    NEGATIVE_UNIT = -1.0
    TWO = 2.0
    DEG_HALF_CIRCLE = 180.0
    DEG_FULL_CIRCLE = 360.0
    EPSILON = 0.0001
    ROUND_DIGITS = 3


class CoordConstants:
    """
    Blender (右手系 Z-up, -Y前方) ⇔ DirectX Engine (左手系 Y-up, +Z前方) 変換定数
    TerrainChunkManager.cpp および Model.cpp の実装と完全一致:
      ex = -bx, ey = bz, ez = -by
      bx = -ex, by = -ez, bz = ey
      engine_yaw_rad = -blender_rot_z_rad
    """
    SIGN_FLIP = -1.0
    SIGN_KEEP = 1.0
    IDX_X = 0
    IDX_Y = 1
    IDX_Z = 2


class PathConstants:
    """プロジェクト相対パス・ファイル名定数"""
    PARENT_TRAVERSAL_COUNT = 2
    KNOWN_WORKSPACE_ROOT = "C:/Users/gamer/source/repos/25B_GE_CG"
    MISSIONS_DIR_REL = "Resources/missions"
    MANIFEST_REL_PATH = "Resources/missions/missions.json"
    MISSION_00_REL_PATH = "Resources/missions/mission00.json"
    MISSION_01_REL_PATH = "Resources/missions/mission01.json"
    TERRAIN_INFO_REL_PATH = "Resources/terrains/demo2/chunks_info.json"
    TERRAIN_DIR_REL = "Resources/terrains/demo2"
    MODEL_M21_REL = "Resources/models/m21.gltf"
    MODEL_M15_REL = "Resources/models/m15.gltf"
    DEFAULT_BLEND_FILENAME = "Zadanie00_MissionEditor.blend"
    MANIFEST_VERSION = "1.0"
    JSON_INDENT = 4


class CollectionNames:
    """3Dシーン階層コレクション名定数"""
    ROOT = "Mission_Root"
    TERRAIN = "00_Terrain"
    PLAYER_AND_ALLIES = "01_Player_And_Allies"
    WAYPOINT_ROUTES = "02_Waypoint_Routes"
    AIR_ENEMIES = "03_Air_Enemies"
    GROUND_TARGETS = "04_Ground_Targets"
    OBJECTIVES_AND_TRIGGERS = "05_Objectives_And_Triggers"
    ZADANIE00_EVENTS = "06_Zadanie00_Events"
    TEMPLATES_HIDDEN = "_Mission_Model_Templates"


class EntityRoles:
    """オブジェクトのミッション内ロール識別子"""
    NONE = "NONE"
    PLAYER_START = "PLAYER_START"
    AIR_ENEMY = "AIR_ENEMY"
    GROUND_ENEMY = "GROUND_ENEMY"
    WAYPOINT_PATH = "WAYPOINT_PATH"
    OBJECTIVE_NODE = "OBJECTIVE_NODE"
    TRIGGER_NODE = "TRIGGER_NODE"
    ZADANIE00_MARKER = "ZADANIE00_MARKER"


class Zadanie00MarkerKinds:
    """ZADANIE 00 (Obuchenie) 専用 3D空間イベントマーカー種別"""
    CORAX_START = "CORAX_START"
    OUTPOST_04 = "OUTPOST_04"
    TRAINING_DRONE = "TRAINING_DRONE"
    WESTERN_DIVE_START = "WESTERN_DIVE_START"
    WESTERN_DIVE_MID = "WESTERN_DIVE_MID"
    WESTERN_PULLUP = "WESTERN_PULLUP"
    EXIT_BOUNDARY = "EXIT_BOUNDARY"


class ColorPalette:
    """ビューポート識別用RGBAカラー定数"""
    TERRAIN_SLATE = (0.16, 0.19, 0.23, 1.0)
    PLAYER_CYAN = (0.15, 0.92, 1.00, 1.0)
    ALLY_CORAX_GREEN = (0.30, 1.00, 0.68, 1.0)
    AIR_ENEMY_RED = (1.00, 0.24, 0.22, 1.0)
    AIR_REINFORCE_MAGENTA = (1.00, 0.32, 0.78, 1.0)
    GROUND_TURRET_ORANGE = (1.00, 0.56, 0.12, 1.0)
    GROUND_STRUCT_AMBER = (0.95, 0.78, 0.20, 1.0)
    GROUND_VEHICLE_OLIVE = (0.52, 0.82, 0.28, 1.0)
    WAYPOINT_EMERALD = (0.20, 1.00, 0.58, 1.0)
    OBJECTIVE_GOLD = (1.00, 0.88, 0.24, 0.65)
    TRIGGER_VIOLET = (0.68, 0.38, 1.00, 0.55)
    OUTPOST_FIRE = (1.00, 0.40, 0.08, 1.0)
    OUTPOST_INTACT_TEAL = (0.36, 0.82, 0.72, 1.0)
    DRONE_ORANGE = (1.00, 0.48, 0.06, 1.0)
    WESTERN_AMBUSH_CRIMSON = (1.00, 0.16, 0.30, 1.0)
    EXIT_BOUNDARY_SKY = (0.28, 0.92, 1.00, 1.0)

    MATERIAL_ROUGHNESS_TERRAIN = 0.88
    MATERIAL_ROUGHNESS_UNIT = 0.42
    MATERIAL_METALLIC_UNIT = 0.35


class MissionDefaults:
    """ミッション基本設定の既定値定数"""
    DEFAULT_ID = "[00]"
    ZADANIE_00_NAME = "Obuchenie"
    ZADANIE_00_ALIAS = "ZADANIE 00"
    ZADANIE_00_SUBTITLE = "オブチェーニエ：訓練・教程 — 極夜の異変 —"
    ZADANIE_00_DIFFICULTY = "TUTORIAL"
    ZADANIE_00_AREA = "VERNA OUTER CANYON (POLAR DUSK)"
    ZADANIE_00_DESC = (
        "定期哨戒と基礎訓練（Obuchenie）から、監視所炎上・西側機との遭遇へ突入する導入。"
        "飛行隊長『Corax』の誘導に従い、M-21A（STAR-BORDER-04 // CALLSIGN: ROOKIE）の"
        "基本機動と峡谷低空哨戒ルートを習得せよ。"
    )
    LEGACY_TUTORIAL_NAME = "Operation Halcyon Days"
    ZADANIE_00_PATROL_ROUTE_NAME = "Obuchenie_Patrol"

    NEW_MISSION_ID = "[02]"
    NEW_MISSION_FILE = "Resources/missions/mission02.json"
    NEW_MISSION_NAME = "INTERCEPT OPERATION"
    NEW_MISSION_ALIAS = "ZADANIE 02"
    NEW_MISSION_SUBTITLE = "外縁防空迎撃任務"
    NEW_MISSION_DIFFICULTY = "NORMAL"
    NEW_MISSION_AREA = "VERNA SECTOR 04"
    NEW_MISSION_DESC = "作戦空域に侵入した敵航空部隊および地上拠点を撃破せよ。"

    DEFAULT_PLAYER_HP = 100.0
    MIN_PLAYER_HP = 1.0
    MAX_PLAYER_HP = 10000.0
    DEFAULT_TIME_LIMIT = 300.0
    UNLIMITED_TIME_LIMIT = 0.0
    MAX_TIME_LIMIT = 7200.0

    DEFAULT_PLAYER_ENGINE_POS = (220.0, -290.0, 800.0)
    DEFAULT_CORAX_ENGINE_POS = (244.0, -278.0, 935.0)
    DEFAULT_GATE_0_ENGINE_POS = (195.0, -340.0, 2850.0)
    DEFAULT_GATE_1_ENGINE_POS = (55.0, -348.0, 3500.0)
    DEFAULT_GATE_2_ENGINE_POS = (-95.0, -355.0, 4150.0)
    DEFAULT_OUTPOST_01_ENGINE_POS = (338.0, -455.0, 1950.0)
    DEFAULT_OUTPOST_02_ENGINE_POS = (78.0, -468.0, 2920.0)
    DEFAULT_OUTPOST_03_ENGINE_POS = (172.0, -478.0, 3880.0)
    DEFAULT_OUTPOST_ENGINE_POS = (-52.0, -510.1, 4950.0)
    DEFAULT_OUTPOST_POSITIONS = (
        DEFAULT_OUTPOST_01_ENGINE_POS,
        DEFAULT_OUTPOST_02_ENGINE_POS,
        DEFAULT_OUTPOST_03_ENGINE_POS,
        DEFAULT_OUTPOST_ENGINE_POS,
    )
    DEFAULT_DRONE_ENGINE_POS = (-260.0, -328.0, 5450.0)
    DEFAULT_WEST_START_ENGINE_POS = (-110.0, -25.0, 5950.0)
    DEFAULT_WEST_MID_ENGINE_POS = (-380.0, -295.0, 5860.0)
    DEFAULT_WEST_PULLUP_ENGINE_POS = (-480.0, -310.0, 6220.0)
    DEFAULT_EXIT_ENGINE_POS = (-680.0, -325.0, 7800.0)


class EnemyDefaults:
    """空中敵の既定値定数"""
    AI_CHASE_ATTACK = "ChaseAttack"
    AI_CRUISE_EVADE = "CruiseEvade"
    AI_FOLLOW_WAYPOINT = "FollowWaypoint"

    DEFAULT_HEALTH = 60.0
    MIN_HEALTH = 1.0
    MAX_HEALTH = 10000.0

    DEFAULT_WAYPOINT_SPEED_KMH = 300.0
    MIN_WAYPOINT_SPEED_KMH = 50.0
    MAX_WAYPOINT_SPEED_KMH = 2400.0
    CURVE_BEVEL_DEPTH = 3.5
    CURVE_RESOLUTION_U = 12
    CURVE_EXTRUDE = 0.0
    SPLINE_CO_HOMOGENEOUS_W = 1.0
    DEFAULT_SPLINE_WEIGHT = 1.0
    NEW_ROUTE_POINT_COUNT = 3
    NEW_ROUTE_FORWARD_STEP_BLENDER_Y = -600.0


class GroundDefaults:
    """地上敵の既定値定数（GroundEnemyParam完全準拠）"""
    AI_TURRET = "Turret"
    AI_STRUCTURE = "Structure"
    AI_PATROL_VEHICLE = "PatrolVehicle"

    TURRET_HEALTH = 60.0
    STRUCTURE_HEALTH = 100.0
    VEHICLE_HEALTH = 50.0

    COLLISION_RADIUS = 8.0
    FIRE_RANGE = 1500.0
    MIN_ELEVATION_DEG = -5.0
    MAX_ELEVATION_DEG = 85.0
    TURN_SPEED_DEG = 60.0
    BULLET_SPEED = 600.0
    BULLET_DAMAGE = 8.0
    FIRE_INTERVAL = 0.08
    BURST_COUNT = 6
    BURST_COOLDOWN = 2.0
    MOVE_SPEED = 15.0
    PATROL_DISTANCE = 200.0

    MAX_FIRE_RANGE = 15000.0
    MIN_PITCH_LIMIT_DEG = -45.0
    MAX_PITCH_LIMIT_DEG = 90.0
    MAX_TURN_SPEED_DEG = 360.0
    MAX_BULLET_SPEED = 3000.0
    MAX_MOVE_SPEED = 200.0
    MAX_PATROL_DIST = 5000.0
    MAX_BURST_COUNT = 60
    MAX_BURST_COOLDOWN = 30.0


class ObjectiveDefaults:
    """ミッション目標の既定値定数"""
    TYPE_DESTROY_ALL = "DestroyAll"
    TYPE_DESTROY_COUNT = "DestroyCount"
    TYPE_DESTROY_TARGET = "DestroyTarget"
    TYPE_REACH_AREA = "ReachArea"
    TYPE_SURVIVE = "Survive"
    TYPE_ESCORT_PROTECT = "EscortProtect"

    STATUS_ACTIVE = "Active"
    STATUS_INACTIVE = "Inactive"
    STATUS_COMPLETED = "Completed"
    STATUS_FAILED = "Failed"

    DEFAULT_AREA_RADIUS = 120.0
    MIN_AREA_RADIUS = 10.0
    MAX_AREA_RADIUS = 10000.0
    DEFAULT_SURVIVE_DURATION = 180.0
    DEFAULT_REQUIRED_KILLS = 1
    NO_TARGET_INDEX = -1
    ICON_DISPLAY_SIZE = 32.0


class TriggerDefaults:
    """ミッショントリガー（会話以外の全ゲームプレイ制御）既定値定数"""
    COND_MISSION_START = "OnMissionStart"
    COND_TIMER = "OnTimer"
    COND_AREA_ENTER = "OnAreaEnter"
    COND_AREA_LEAVE = "OnAreaLeave"
    COND_ENEMY_DESTROYED = "OnEnemyDestroyed"
    COND_KILL_COUNT = "OnKillCount"
    COND_PLAYER_DAMAGED = "OnPlayerDamaged"
    COND_OBJECTIVE_COMPLETE = "OnObjectiveComplete"

    ACT_SPAWN_ENEMIES = "SpawnEnemies"
    ACT_SET_OBJECTIVE = "SetObjective"
    ACT_MISSION_COMPLETE = "MissionComplete"
    ACT_MISSION_FAIL = "MissionFail"
    ACT_ACTIVATE_TRIGGER = "ActivateTrigger"
    ACT_SHOW_MESSAGE = "ShowMessage"
    ACT_PLAY_RADIO_PRESERVED = "PlayRadioDialogue"

    DEFAULT_AREA_RADIUS = 200.0
    DEFAULT_TIMER_SECONDS = 30.0
    DEFAULT_HP_THRESHOLD = 50.0
    DEFAULT_KILL_COUNT = 1
    DEFAULT_MSG_DURATION = 3.0
    MAX_MSG_DURATION = 30.0
    NO_INDEX = -1
    ICON_DISPLAY_SIZE = 28.0


class TerrainDefaults:
    """40km x 40km チャンク地形ロード＆スナップ定数"""
    MODE_CANYON_CORRIDOR = "CANYON_CORRIDOR"
    MODE_AROUND_CURSOR = "AROUND_CURSOR"
    MODE_ALL_CHUNKS = "ALL_CHUNKS"

    FULL_TERRAIN_OBJECT_NAME = "Terrain_FullMap"
    FULL_TERRAIN_MESH_NAME = "Terrain_FullMap_Mesh"
    DEFAULT_STARTUP_OBJECTS = ("Cube", "Light", "Camera")

    # ZADANIE 00 ヴェールナ外縁峡谷回廊をカバーする Blender チャンク格子範囲
    CANYON_GRID_X_MIN = 4
    CANYON_GRID_X_MAX = 5
    CANYON_GRID_Y_MIN = 2
    CANYON_GRID_Y_MAX = 4

    DEFAULT_CURSOR_LOAD_RADIUS = 4500.0
    MIN_CURSOR_LOAD_RADIUS = 1000.0
    MAX_CURSOR_LOAD_RADIUS = 25000.0

    DEFAULT_SNAP_AGL_AIR = 140.0
    DEFAULT_SNAP_AGL_GROUND = 0.0
    MIN_SNAP_AGL = -50.0
    MAX_SNAP_AGL = 5000.0

    RAYCAST_START_Z = 15000.0
    RAYCAST_MAX_DIST = 30000.0


class GizmoDimensions:
    """プロシージャル識別メッシュ・ギズモ寸法定数（メートル）"""
    FIGHTER_LENGTH = 15.0
    FIGHTER_WINGSPAN = 9.0
    FIGHTER_HEIGHT = 3.2
    NOSE_ARROW_LENGTH = 26.0

    TURRET_BASE_RADIUS = 6.0
    TURRET_HEIGHT = 4.2
    STRUCTURE_RADIUS = 14.0
    STRUCTURE_HEIGHT = 10.0
    VEHICLE_LENGTH = 8.0
    VEHICLE_WIDTH = 4.5
    VEHICLE_HEIGHT = 2.6

    OUTPOST_RADIUS = 9.5
    OUTPOST_HEIGHT = 28.0
    GATE_RING_RADIUS = 46.0
    EXIT_GATE_RADIUS = 64.0
    GATE_RING_SEGMENTS = 32
    CYLINDER_SEGMENTS = 16
    DRONE_SCALE = 0.65
    AMBUSH_PREVIEW_BEVEL = 2.2
    AMBUSH_PREVIEW_NAME = "Z00_Western_Ambush_CurvePreview"


class LiveSyncDefaults:
    """Blender ⇔ DirectX HTTP ライブ同期定数"""
    HOST = "127.0.0.1"
    DEFAULT_PORT = 8766
    MIN_PORT = 1024
    MAX_PORT = 65535
    TIMER_INTERVAL_SEC = 0.25
    HTTP_OK = 200
    HTTP_NOT_FOUND = 404
    ENDPOINT_LIVE = "/mission/live"
    ENDPOINT_HEALTH = "/health"
    QUERY_KEY_FILE = "file"
    INITIAL_REVISION = 1
    ZERO_REVISION = 0


class ViewportDefaults:
    """広域40kmマップ向け3Dビューポート設定定数"""
    CLIP_START = 1.0
    CLIP_END = 60000.0
    GRID_SCALE = 100.0
    INITIAL_VIEW_DISTANCE = 2200.0
    INITIAL_CAMERA_OFFSET_X = -320.0
    INITIAL_CAMERA_OFFSET_Y = 650.0
    INITIAL_CAMERA_OFFSET_Z = 420.0


class WorkspaceDefaults:
    """『レイアウト』の操作系・画面構成を完全継承する専用ワークスペースモード定数"""
    MISSION_WORKSPACE_NAME = "ミッション編集"
    LAYOUT_WORKSPACE_JA = "レイアウト"
    LAYOUT_WORKSPACE_EN = "Layout"
    LAYOUT_WORKSPACE_CANDIDATES = ("レイアウト", "Layout")
    RESTORE_LAYOUT_DELAY_SEC = 0.08



class UILayoutConstants:
    """Blender NパネルUIレイアウト比率・スケール定数"""
    LARGE_BUTTON_SCALE_Y = 1.35
    PRIMARY_BUTTON_SCALE_Y = 1.25
    COMPACT_BUTTON_SCALE_Y = 1.1
    SPLIT_HALF = 0.5


class WatchtowerDefaults:
    """峡谷監視塔一括自動配置・整列パラメータ定数"""
    DEFAULT_COUNT = 4
    MIN_COUNT = 1
    MAX_COUNT = 24
    DEFAULT_LATERAL_OFFSET_M = 118.0
    MIN_LATERAL_OFFSET_M = 20.0
    MAX_LATERAL_OFFSET_M = 600.0
    DEFAULT_START_ENGINE_Z = 1950.0
    DEFAULT_END_ENGINE_Z = 4950.0
    FALLBACK_GROUND_ENGINE_Y = -485.0
    CANYON_CONTROL_Z = (500.0, 2500.0, 4500.0, 6500.0, 9000.0, 11500.0, 14000.0, 16500.0, 18500.0)
    CANYON_CONTROL_X = (220.0, 220.0, -150.0, -450.0, -750.0, -750.0, -500.0, -150.0, -100.0)
