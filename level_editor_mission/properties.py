# -*- coding: utf-8 -*-
"""
Mission Editor - Blender シーン＆オブジェクト PropertyGroup 定義
"""

import os
from pathlib import Path
import bpy
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Object, PropertyGroup, Scene

from .constants import (
    EnemyDefaults,
    EntityRoles,
    GroundDefaults,
    LiveSyncDefaults,
    MathConstants,
    MissionDefaults,
    ObjectiveDefaults,
    PathConstants,
    TerrainDefaults,
    TriggerDefaults,
    WatchtowerDefaults,
    Zadanie00MarkerKinds,
)


class RepoPathResolver:
    """リポジトリルートパスの自動検出とパス結合を担うユーティリティクラス"""

    @staticmethod
    def detect_default_repo_root() -> str:
        here = Path(__file__).resolve()
        parents = here.parents
        if len(parents) > PathConstants.PARENT_TRAVERSAL_COUNT:
            candidate = parents[PathConstants.PARENT_TRAVERSAL_COUNT]
            if (candidate / PathConstants.MISSIONS_DIR_REL).exists():
                return str(candidate).replace("\\", "/")

        blend_path = getattr(bpy.data, "filepath", "")
        if blend_path:
            cur = Path(blend_path).resolve().parent
            for anc in [cur] + list(cur.parents):
                if (anc / PathConstants.MISSIONS_DIR_REL).exists():
                    return str(anc).replace("\\", "/")

        cwd = Path(os.getcwd()).resolve()
        if (cwd / PathConstants.MISSIONS_DIR_REL).exists():
            return str(cwd).replace("\\", "/")

        known_ws = Path(PathConstants.KNOWN_WORKSPACE_ROOT)
        if (known_ws / PathConstants.MISSIONS_DIR_REL).exists():
            return str(known_ws).replace("\\", "/")

        return str(cwd).replace("\\", "/")

    @classmethod
    def resolve_repo_root(cls, scene: Scene) -> Path:
        raw = getattr(scene.mission_settings, "repo_root", "").strip()
        if raw:
            resolved = Path(bpy.path.abspath(raw)).resolve()
            if resolved.exists():
                return resolved
        return Path(cls.detect_default_repo_root())

    @classmethod
    def resolve_path(cls, scene: Scene, rel_or_abs: str) -> Path:
        p = Path(rel_or_abs)
        if p.is_absolute():
            return p
        return (cls.resolve_repo_root(scene) / rel_or_abs).resolve()


def _on_objective_radius_update(self, _context):
    owner = self.id_data
    if isinstance(owner, Object) and owner.type == "EMPTY":
        if self.obj_type == ObjectiveDefaults.TYPE_REACH_AREA:
            owner.empty_display_type = "SPHERE"
            owner.empty_display_size = max(ObjectiveDefaults.MIN_AREA_RADIUS, self.obj_area_radius)
        else:
            owner.empty_display_type = "PLAIN_AXES"
            owner.empty_display_size = ObjectiveDefaults.ICON_DISPLAY_SIZE


def _on_trigger_radius_update(self, _context):
    owner = self.id_data
    if isinstance(owner, Object) and owner.type == "EMPTY":
        if self.trig_condition in (TriggerDefaults.COND_AREA_ENTER, TriggerDefaults.COND_AREA_LEAVE):
            owner.empty_display_type = "SPHERE"
            owner.empty_display_size = max(ObjectiveDefaults.MIN_AREA_RADIUS, self.trig_area_radius)
        else:
            owner.empty_display_type = "CUBE"
            owner.empty_display_size = TriggerDefaults.ICON_DISPLAY_SIZE


def _poll_enemy_object(_self, obj: Object) -> bool:
    if not hasattr(obj, "mission_obj"):
        return False
    return obj.mission_obj.entity_role in (EntityRoles.AIR_ENEMY, EntityRoles.GROUND_ENEMY)


def _poll_objective_object(_self, obj: Object) -> bool:
    if not hasattr(obj, "mission_obj"):
        return False
    return obj.mission_obj.entity_role == EntityRoles.OBJECTIVE_NODE


def _poll_trigger_object(_self, obj: Object) -> bool:
    if not hasattr(obj, "mission_obj"):
        return False
    return obj.mission_obj.entity_role == EntityRoles.TRIGGER_NODE


def _on_watchtower_layout_update(self, context):
    if getattr(self, "_suppress_watchtower_callback", False):
        return
    try:
        from .serializer import MissionSceneSerializer
        from .live_sync_server import LiveSyncServerManager

        scene = getattr(context, "scene", None) or self.id_data
        if isinstance(scene, Scene):
            MissionSceneSerializer.generate_canyon_watchtowers(context, scene)
            if self.live_sync_auto_push and LiveSyncServerManager.instance().is_running:
                LiveSyncServerManager.instance().push_now(scene, request_restart=False)
    except Exception:
        pass


class MISSION_Settings(PropertyGroup):
    """シーン単位で保持するミッション全体設定"""

    repo_root: StringProperty(
        name="Project Root",
        description="25B_GE_CG リポジトリのルートフォルダ（Resources/ が存在するディレクトリ）",
        default=RepoPathResolver.detect_default_repo_root(),
        subtype="DIR_PATH",
    )

    mission_id: StringProperty(
        name="Mission ID",
        description="missions.json に登録するID（例: [00], [01], [02]）",
        default=MissionDefaults.DEFAULT_ID,
    )

    mission_file_path: StringProperty(
        name="JSON Path",
        description="出力先のミッションJSON相対パス（例: Resources/missions/mission00.json）",
        default=PathConstants.MISSION_00_REL_PATH,
    )

    update_manifest: BoolProperty(
        name="missions.json も同時更新",
        description="エクスポート時に Resources/missions/missions.json の一覧エントリを自動更新・追加します",
        default=True,
    )

    is_locked: BoolProperty(
        name="初期ロック状態",
        description="ミッション選択画面で初期ロック状態にするか",
        default=False,
    )

    mission_name: StringProperty(
        name="作戦名 (Title)",
        default=MissionDefaults.ZADANIE_00_NAME,
    )

    alias_name: StringProperty(
        name="コードネーム (Alias)",
        default=MissionDefaults.ZADANIE_00_ALIAS,
    )

    sub_title: StringProperty(
        name="サブタイトル",
        default=MissionDefaults.ZADANIE_00_SUBTITLE,
    )

    difficulty: EnumProperty(
        name="難易度",
        items=[
            ("TUTORIAL", "TUTORIAL", "訓練・教程ミッション"),
            ("EASY", "EASY", "低難度"),
            ("NORMAL", "NORMAL", "標準難度"),
            ("HARD", "HARD", "高難度"),
            ("EXPERT", "EXPERT", "熟練者向け最高難度"),
        ],
        default="TUTORIAL",
    )

    area_name: StringProperty(
        name="作戦空域",
        default=MissionDefaults.ZADANIE_00_AREA,
    )

    description: StringProperty(
        name="作戦概要",
        default=MissionDefaults.ZADANIE_00_DESC,
    )

    player_hp: FloatProperty(
        name="自機初期HP",
        default=MissionDefaults.DEFAULT_PLAYER_HP,
        min=MissionDefaults.MIN_PLAYER_HP,
        max=MissionDefaults.MAX_PLAYER_HP,
    )

    time_limit: FloatProperty(
        name="制限時間 (秒 / 0=無制限)",
        default=MissionDefaults.UNLIMITED_TIME_LIMIT,
        min=MissionDefaults.UNLIMITED_TIME_LIMIT,
        max=MissionDefaults.MAX_TIME_LIMIT,
    )

    is_zadanie_00_mode: BoolProperty(
        name="ZADANIE 00 (Obuchenie) 空間配置モード",
        description="有効時、Corax初期位置・第4監視所・ドローン・西側機急襲パス・帰投境界ラインを tutorialLayout として出力します（会話・チュートリアル進行ロジックは壊しません）",
        default=True,
    )

    preserved_radio_json: StringProperty(
        name="Preserved Radio JSON",
        description="インポート時に既存トリガー内の PlayRadioDialogue アクションを保持し、再エクスポート時に無劣化で復元する内部キャッシュ",
        default="{}",
    )

    # --- 地形チャンクローダー設定 ---
    terrain_load_mode: EnumProperty(
        name="地形ロード範囲",
        items=[
            (
                TerrainDefaults.MODE_ALL_CHUNKS,
                "全地形一括ロード (40km x 40km 全100チャンク結合)",
                "ミッションで使用する全地形チャンクを1つの高速メッシュに結合して一括ロードします",
            ),
            (
                TerrainDefaults.MODE_CANYON_CORRIDOR,
                "峡谷回廊のみ (6チャンク)",
                "ヴェールナ外縁峡谷の哨戒ルート周辺のみロードします",
            ),
            (
                TerrainDefaults.MODE_AROUND_CURSOR,
                "3Dカーソル周辺 (半径指定)",
                "現在の3Dカーソル周辺のチャンクのみロードします",
            ),
        ],
        default=TerrainDefaults.MODE_ALL_CHUNKS,
    )

    terrain_radius_meters: FloatProperty(
        name="ロード半径 (m)",
        default=TerrainDefaults.DEFAULT_CURSOR_LOAD_RADIUS,
        min=TerrainDefaults.MIN_CURSOR_LOAD_RADIUS,
        max=TerrainDefaults.MAX_CURSOR_LOAD_RADIUS,
    )

    snap_agl_offset: FloatProperty(
        name="対地高度 AGL (m)",
        description="航空機・ゲートを地形へスナップする際の地面からの高度オフセット（地上目標は自動で0m接地）",
        default=TerrainDefaults.DEFAULT_SNAP_AGL_AIR,
        min=TerrainDefaults.MIN_SNAP_AGL,
        max=TerrainDefaults.MAX_SNAP_AGL,
    )

    # --- HTTP ライブ同期設定 ---
    live_sync_port: IntProperty(
        name="Live Sync Port",
        description="実行中の DirectX ゲーム (MissionSyncManager) がポーリングするローカルHTTPポート",
        default=LiveSyncDefaults.DEFAULT_PORT,
        min=LiveSyncDefaults.MIN_PORT,
        max=LiveSyncDefaults.MAX_PORT,
    )

    live_sync_auto_push: BoolProperty(
        name="ドラッグ変更を自動ライブ反映",
        description="有効時、Blender上でオブジェクトを移動・編集すると自動で実機へホット同期します",
        default=True,
    )

    is_mission_mode_active: BoolProperty(
        name="ミッション編集モード有効",
        description="専用ワークスペース『ミッション編集』またはミッション編集モードが有効か",
        default=False,
    )

    # --- 監視塔 (Watchtower) 峡谷ルート一括自動配置パラメータ ---
    watchtower_count: IntProperty(
        name="監視塔の数 (基)",
        description="峡谷の哨戒ルート沿いに自動配置する監視塔の総数（変更すると即座に再配置＆地形接地します）",
        default=WatchtowerDefaults.DEFAULT_COUNT,
        min=WatchtowerDefaults.MIN_COUNT,
        max=WatchtowerDefaults.MAX_COUNT,
        update=_on_watchtower_layout_update,
    )

    watchtower_lateral_offset: FloatProperty(
        name="峡谷崖オフセット幅 (m)",
        description="峡谷ルート中心線から左右の崖棚へ配置する距離（メートル）",
        default=WatchtowerDefaults.DEFAULT_LATERAL_OFFSET_M,
        min=WatchtowerDefaults.MIN_LATERAL_OFFSET_M,
        max=WatchtowerDefaults.MAX_LATERAL_OFFSET_M,
        update=_on_watchtower_layout_update,
    )

    watchtower_alternate_banks: BoolProperty(
        name="左右の崖に交互配置",
        description="有効時は峡谷の左右の崖へ交互に配置し、無効時は片側の崖に揃えて配置します",
        default=True,
        update=_on_watchtower_layout_update,
    )


class MISSION_ObjectProps(PropertyGroup):
    """各3Dオブジェクトに付与するミッション要素プロパティ"""

    entity_role: EnumProperty(
        name="要素種別",
        items=[
            (EntityRoles.NONE, "通常オブジェクト (対象外)", "ミッション出力対象外"),
            (EntityRoles.PLAYER_START, "自機スタート位置", "プレイヤー機 (M-21A) 初期位置・方位"),
            (EntityRoles.AIR_ENEMY, "空中敵 (戦闘機)", "敵航空機スポーン"),
            (EntityRoles.GROUND_ENEMY, "地上目標 (砲台・施設・車両)", "地上敵スポーン"),
            (EntityRoles.WAYPOINT_PATH, "ウェイポイント経路 (Curve)", "巡回ルート / ZADANIE 00 峡谷ゲート列"),
            (EntityRoles.OBJECTIVE_NODE, "ミッション目標ノード", "達成目標（殲滅・特定撃破・エリア到達・生存）"),
            (EntityRoles.TRIGGER_NODE, "ゲームプレイトリガー", "会話以外のイベント発火（増援出現・目標切替・クリア判定等）"),
            (EntityRoles.ZADANIE00_MARKER, "ZADANIE 00 専用マーカー", "Corax・第4監視所・ドローン・西側機急襲・帰投ライン"),
        ],
        default=EntityRoles.NONE,
    )

    # --- 共通: トリガー経由の増援スポーン紐付け ---
    spawn_trigger_name: StringProperty(
        name="増援トリガー名 (空欄=初期配置)",
        description="特定の Trigger 名を入力すると、ミッション開始時ではなく該当トリガー発火時 (SpawnEnemies) に出現します",
        default="",
    )

    waypoint_path_name: StringProperty(
        name="追従ルート名",
        description="FollowWaypoint または PatrolVehicle が辿る WaypointPath の名前",
        default="",
    )

    # --- 空中敵設定 ---
    air_model_preset: EnumProperty(
        name="機体モデル",
        items=[
            (PathConstants.MODEL_M15_REL, "M-15 (西側ジェット戦闘機)", "Resources/models/m15.gltf"),
            (PathConstants.MODEL_M21_REL, "M-21A (条約軍戦闘機)", "Resources/models/m21.gltf"),
            ("CUSTOM", "カスタムパス指定", "任意のモデルパスを入力"),
        ],
        default=PathConstants.MODEL_M15_REL,
    )

    air_custom_model_path: StringProperty(
        name="カスタムモデルパス",
        default=PathConstants.MODEL_M15_REL,
    )

    air_health: FloatProperty(
        name="機体HP",
        default=EnemyDefaults.DEFAULT_HEALTH,
        min=EnemyDefaults.MIN_HEALTH,
        max=EnemyDefaults.MAX_HEALTH,
    )

    air_ai_type: EnumProperty(
        name="AI挙動",
        items=[
            (EnemyDefaults.AI_CHASE_ATTACK, "ChaseAttack (追尾・偏差射撃)", "積極的に自機を追尾して機銃攻撃"),
            (EnemyDefaults.AI_CRUISE_EVADE, "CruiseEvade (巡航・接近回避)", "巡航飛行し、自機接近時に全力回避"),
            (EnemyDefaults.AI_FOLLOW_WAYPOINT, "FollowWaypoint (経路飛行→交戦)", "指定ウェイポイント経路を飛行"),
        ],
        default=EnemyDefaults.AI_CHASE_ATTACK,
    )

    # --- 地上敵設定 ---
    ground_ai_type: EnumProperty(
        name="地上ユニット種別",
        items=[
            (GroundDefaults.AI_TURRET, "Turret (対空砲台 AAA)", "自機を見越し追尾して連装対空砲火を撃つ砲台"),
            (GroundDefaults.AI_STRUCTURE, "Structure (レーダー・司令施設)", "攻撃を行わない大型重要施設ターゲット"),
            (GroundDefaults.AI_PATROL_VEHICLE, "PatrolVehicle (対空装甲車両)", "地上ルートまたは往復移動しながら対空射撃"),
        ],
        default=GroundDefaults.AI_TURRET,
    )

    ground_health: FloatProperty(
        name="耐久値 (HP)",
        default=GroundDefaults.TURRET_HEALTH,
        min=EnemyDefaults.MIN_HEALTH,
        max=EnemyDefaults.MAX_HEALTH,
    )

    collision_radius: FloatProperty(
        name="当たり判定半径 (m)",
        default=GroundDefaults.COLLISION_RADIUS,
        min= float(MathConstants.ONE_INT),
        max=ObjectiveDefaults.DEFAULT_AREA_RADIUS,
    )

    fire_range: FloatProperty(
        name="対空射程 (m)",
        default=GroundDefaults.FIRE_RANGE,
        min=MathConstants.ZERO,
        max=GroundDefaults.MAX_FIRE_RANGE,
    )

    min_elevation_deg: FloatProperty(
        name="最低仰角 (deg)",
        default=GroundDefaults.MIN_ELEVATION_DEG,
        min=GroundDefaults.MIN_PITCH_LIMIT_DEG,
        max=GroundDefaults.MAX_PITCH_LIMIT_DEG,
    )

    max_elevation_deg: FloatProperty(
        name="最高仰角 (deg)",
        default=GroundDefaults.MAX_ELEVATION_DEG,
        min=GroundDefaults.MIN_PITCH_LIMIT_DEG,
        max=GroundDefaults.MAX_PITCH_LIMIT_DEG,
    )

    turn_speed_deg: FloatProperty(
        name="砲塔旋回速度 (deg/s)",
        default=GroundDefaults.TURN_SPEED_DEG,
        min=MathConstants.ZERO,
        max=GroundDefaults.MAX_TURN_SPEED_DEG,
    )

    bullet_speed: FloatProperty(
        name="対空弾速 (m/s)",
        default=GroundDefaults.BULLET_SPEED,
        min=MathConstants.ZERO,
        max=GroundDefaults.MAX_BULLET_SPEED,
    )

    bullet_damage: FloatProperty(
        name="弾丸ダメージ",
        default=GroundDefaults.BULLET_DAMAGE,
        min=MathConstants.ZERO,
        max=EnemyDefaults.MAX_HEALTH,
    )

    fire_interval: FloatProperty(
        name="連射間隔 (秒)",
        default=GroundDefaults.FIRE_INTERVAL,
        min=MathConstants.EPSILON,
        max= float(MathConstants.FOUR_INT),
    )

    burst_count: IntProperty(
        name="1バースト発射数",
        default=GroundDefaults.BURST_COUNT,
        min=MathConstants.ONE_INT,
        max=GroundDefaults.MAX_BURST_COUNT,
    )

    burst_cooldown: FloatProperty(
        name="バースト間隔 (秒)",
        default=GroundDefaults.BURST_COOLDOWN,
        min=MathConstants.ZERO,
        max=GroundDefaults.MAX_BURST_COOLDOWN,
    )

    move_speed: FloatProperty(
        name="車両移動速度 (m/s)",
        default=GroundDefaults.MOVE_SPEED,
        min=MathConstants.ZERO,
        max=GroundDefaults.MAX_MOVE_SPEED,
    )

    patrol_distance: FloatProperty(
        name="往復距離 (m / ルート未指定時)",
        default=GroundDefaults.PATROL_DISTANCE,
        min=MathConstants.ZERO,
        max=GroundDefaults.MAX_PATROL_DIST,
    )

    # --- ウェイポイント経路設定 (CURVE オブジェクト用) ---
    path_name: StringProperty(
        name="ルート識別名",
        default=MissionDefaults.ZADANIE_00_PATROL_ROUTE_NAME,
    )

    path_is_loop: BoolProperty(
        name="終点から始点へループ",
        default=False,
    )

    default_point_speed_kmh: FloatProperty(
        name="標準通過速度 (km/h)",
        description="各制御点の weight (1.0基準) を掛ける基準目標速度",
        default=EnemyDefaults.DEFAULT_WAYPOINT_SPEED_KMH,
        min=EnemyDefaults.MIN_WAYPOINT_SPEED_KMH,
        max=EnemyDefaults.MAX_WAYPOINT_SPEED_KMH,
    )

    # --- ミッション目標設定 ---
    obj_sort_order: IntProperty(
        name="目標順序",
        default=MathConstants.ZERO_INT,
        min=MathConstants.ZERO_INT,
    )

    obj_name: StringProperty(
        name="目標タイトル",
        default="Eliminate Hostile Forces",
    )

    obj_description: StringProperty(
        name="目標説明文",
        default="作戦空域内の敵部隊を撃破せよ。",
    )

    obj_type: EnumProperty(
        name="達成条件タイプ",
        items=[
            (ObjectiveDefaults.TYPE_DESTROY_ALL, "DestroyAll (全敵殲滅)", "空中・地上の全敵撃破で達成"),
            (ObjectiveDefaults.TYPE_DESTROY_COUNT, "DestroyCount (規定数撃破)", "requiredKills 以上の撃破で達成"),
            (ObjectiveDefaults.TYPE_DESTROY_TARGET, "DestroyTarget (特定ユニット撃破)", "指定した敵オブジェクトの撃破で達成"),
            (ObjectiveDefaults.TYPE_REACH_AREA, "ReachArea (指定エリア到達)", "このオブジェクトの球体範囲内に進入で達成"),
            (ObjectiveDefaults.TYPE_SURVIVE, "Survive (一定時間生存)", "duration 秒間の生存で達成"),
            (ObjectiveDefaults.TYPE_ESCORT_PROTECT, "EscortProtect (護衛対象防衛)", "護衛目標の防衛"),
        ],
        default=ObjectiveDefaults.TYPE_DESTROY_ALL,
        update=_on_objective_radius_update,
    )

    obj_status: EnumProperty(
        name="初期状態",
        items=[
            (ObjectiveDefaults.STATUS_ACTIVE, "Active (開始時から有効)", "ミッション開始時から進行中"),
            (ObjectiveDefaults.STATUS_INACTIVE, "Inactive (トリガーで後から有効化)", "SetObjective アクションで有効化されるまで待機"),
        ],
        default=ObjectiveDefaults.STATUS_ACTIVE,
    )

    obj_is_primary: BoolProperty(
        name="主目標 (Primary)",
        description="全主目標が Completed になるとステージクリアになります",
        default=True,
    )

    obj_is_hidden: BoolProperty(
        name="達成までHUD非表示",
        default=False,
    )

    obj_required_kills: IntProperty(
        name="必要撃破数",
        default=ObjectiveDefaults.DEFAULT_REQUIRED_KILLS,
        min=MathConstants.ZERO_INT,
    )

    obj_target_unit: PointerProperty(
        name="撃破対象ユニット (3D選択)",
        description="DestroyTarget 対象の敵オブジェクトを直接ピッカーで指定します（インデックス自動解決）",
        type=Object,
        poll=_poll_enemy_object,
    )

    obj_fallback_target_index: IntProperty(
        name="対象インデックス (手動予備)",
        default=ObjectiveDefaults.NO_TARGET_INDEX,
        min=ObjectiveDefaults.NO_TARGET_INDEX,
    )

    obj_area_radius: FloatProperty(
        name="到達判定半径 (m)",
        default=ObjectiveDefaults.DEFAULT_AREA_RADIUS,
        min=ObjectiveDefaults.MIN_AREA_RADIUS,
        max=ObjectiveDefaults.MAX_AREA_RADIUS,
        update=_on_objective_radius_update,
    )

    obj_duration: FloatProperty(
        name="生存秒数",
        default=ObjectiveDefaults.DEFAULT_SURVIVE_DURATION,
        min=MathConstants.ZERO,
        max=MissionDefaults.MAX_TIME_LIMIT,
    )

    obj_min_hp: FloatProperty(
        name="最低維持HP",
        default=MathConstants.ZERO,
        min=MathConstants.ZERO,
        max=EnemyDefaults.MAX_HEALTH,
    )

    # --- トリガー設定 (会話以外のゲームプレイロジック) ---
    trig_sort_order: IntProperty(
        name="評価順序",
        default=MathConstants.ZERO_INT,
        min=MathConstants.ZERO_INT,
    )

    trig_name: StringProperty(
        name="トリガー名",
        description="増援敵の『増援トリガー名』から参照する一意識別名",
        default="Wave_Trigger_01",
    )

    trig_condition: EnumProperty(
        name="発火条件",
        items=[
            (TriggerDefaults.COND_AREA_ENTER, "OnAreaEnter (エリア進入)", "自機がこのトリガー球体に入った時"),
            (TriggerDefaults.COND_AREA_LEAVE, "OnAreaLeave (エリア離脱)", "自機がこのトリガー球体から出た時"),
            (TriggerDefaults.COND_TIMER, "OnTimer (経過時間)", "ミッション開始から指定秒数が経過した時"),
            (TriggerDefaults.COND_KILL_COUNT, "OnKillCount (累計撃破数)", "撃破数が閾値に達した時"),
            (TriggerDefaults.COND_ENEMY_DESTROYED, "OnEnemyDestroyed (特定敵撃破)", "指定ユニットが撃破された時"),
            (TriggerDefaults.COND_OBJECTIVE_COMPLETE, "OnObjectiveComplete (特定目標達成)", "指定目標が達成された時"),
            (TriggerDefaults.COND_PLAYER_DAMAGED, "OnPlayerDamaged (自機HP低下)", "自機HPが閾値以下になった時"),
            (TriggerDefaults.COND_MISSION_START, "OnMissionStart (開始直後)", "ミッション開始直後に1回発火"),
        ],
        default=TriggerDefaults.COND_AREA_ENTER,
        update=_on_trigger_radius_update,
    )

    trig_enabled: BoolProperty(
        name="開始時から有効",
        default=True,
    )

    trig_repeatable: BoolProperty(
        name="繰り返し発火を許可",
        default=False,
    )

    trig_timer_seconds: FloatProperty(
        name="発火秒数",
        default=TriggerDefaults.DEFAULT_TIMER_SECONDS,
        min=MathConstants.ZERO,
        max=MissionDefaults.MAX_TIME_LIMIT,
    )

    trig_area_radius: FloatProperty(
        name="検知エリア半径 (m)",
        default=TriggerDefaults.DEFAULT_AREA_RADIUS,
        min=ObjectiveDefaults.MIN_AREA_RADIUS,
        max=ObjectiveDefaults.MAX_AREA_RADIUS,
        update=_on_trigger_radius_update,
    )

    trig_target_enemy: PointerProperty(
        name="監視対象ユニット",
        type=Object,
        poll=_poll_enemy_object,
    )

    trig_fallback_enemy_index: IntProperty(
        name="監視敵インデックス (予備)",
        default=TriggerDefaults.NO_INDEX,
        min=TriggerDefaults.NO_INDEX,
    )

    trig_kill_count: IntProperty(
        name="必要撃破数",
        default=TriggerDefaults.DEFAULT_KILL_COUNT,
        min=MathConstants.ZERO_INT,
    )

    trig_hp_threshold: FloatProperty(
        name="自機HP閾値",
        default=TriggerDefaults.DEFAULT_HP_THRESHOLD,
        min=MathConstants.ZERO,
        max=MissionDefaults.MAX_PLAYER_HP,
    )

    trig_target_objective: PointerProperty(
        name="監視対象目標",
        type=Object,
        poll=_poll_objective_object,
    )

    trig_fallback_objective_index: IntProperty(
        name="監視目標インデックス (予備)",
        default=TriggerDefaults.NO_INDEX,
        min=TriggerDefaults.NO_INDEX,
    )

    trig_action_type: EnumProperty(
        name="実行アクション",
        items=[
            (
                TriggerDefaults.ACT_SPAWN_ENEMIES,
                "SpawnEnemies (紐付けた増援ユニットを出現)",
                "『増援トリガー名』にこのトリガー名が設定された空中敵・地上敵を一斉出現させます",
            ),
            (
                TriggerDefaults.ACT_SET_OBJECTIVE,
                "SetObjective (目標の状態を変更)",
                "指定した目標を Active / Completed / Failed に切り替えます",
            ),
            (
                TriggerDefaults.ACT_ACTIVATE_TRIGGER,
                "ActivateTrigger (別トリガーを有効化)",
                "無効状態で待機している後続トリガーを有効化します",
            ),
            (
                TriggerDefaults.ACT_SHOW_MESSAGE,
                "ShowMessage (システム通知テキスト表示)",
                "画面上部に短い戦術システム通知を表示します（※キャラクター会話ではありません）",
            ),
            (
                TriggerDefaults.ACT_MISSION_COMPLETE,
                "MissionComplete (即時ミッション成功)",
                "ミッションクリア演出を開始します",
            ),
            (
                TriggerDefaults.ACT_MISSION_FAIL,
                "MissionFail (即時ミッション失敗)",
                "ミッション失敗演出を開始します",
            ),
        ],
        default=TriggerDefaults.ACT_SPAWN_ENEMIES,
    )

    trig_set_obj_target: PointerProperty(
        name="状態変更する目標",
        type=Object,
        poll=_poll_objective_object,
    )

    trig_set_obj_fallback_index: IntProperty(
        name="変更目標インデックス (予備)",
        default=TriggerDefaults.NO_INDEX,
        min=TriggerDefaults.NO_INDEX,
    )

    trig_set_obj_status: EnumProperty(
        name="変更先ステータス",
        items=[
            (ObjectiveDefaults.STATUS_ACTIVE, "Active (有効化)", ""),
            (ObjectiveDefaults.STATUS_COMPLETED, "Completed (達成済みにする)", ""),
            (ObjectiveDefaults.STATUS_FAILED, "Failed (失敗にする)", ""),
        ],
        default=ObjectiveDefaults.STATUS_ACTIVE,
    )

    trig_activate_target: PointerProperty(
        name="有効化する後続トリガー",
        type=Object,
        poll=_poll_trigger_object,
    )

    trig_activate_fallback_index: IntProperty(
        name="有効化トリガーインデックス (予備)",
        default=TriggerDefaults.NO_INDEX,
        min=TriggerDefaults.NO_INDEX,
    )

    trig_hud_message: StringProperty(
        name="通知テキスト",
        default="WARNING: HOSTILE REINFORCEMENTS DETECTED",
    )

    trig_hud_message_duration: FloatProperty(
        name="表示秒数",
        default=TriggerDefaults.DEFAULT_MSG_DURATION,
        min=MathConstants.HALF,
        max=TriggerDefaults.MAX_MSG_DURATION,
    )

    # --- ZADANIE 00 専用 3D空間マーカー種別 ---
    z00_marker_kind: EnumProperty(
        name="ZADANIE 00 役割",
        items=[
            (Zadanie00MarkerKinds.CORAX_START, "Corax 隊長機 初期位置", "Phase 1 開始時の飛行隊長 M-21A 配置座標"),
            (Zadanie00MarkerKinds.OUTPOST_04, "第4監視所 (炎上監視塔)", "Phase 4 で黒煙と炎を上げる監視塔の接地座標"),
            (Zadanie00MarkerKinds.TRAINING_DRONE, "暴走訓練ドローン 出現位置", "Phase 5 リード射撃標的ドローンの出現座標"),
            (Zadanie00MarkerKinds.WESTERN_DIVE_START, "西側機 急襲開始点 (高空)", "Phase 6 ベジェ急降下パスの開始座標"),
            (Zadanie00MarkerKinds.WESTERN_DIVE_MID, "西側機 頭上フライバイ通過点", "Phase 6 機関砲掃射フライバイの中間制御点"),
            (Zadanie00MarkerKinds.WESTERN_PULLUP, "西側機 引き起こし・交戦開始点", "Phase 6 ドッグファイト移行座標"),
            (Zadanie00MarkerKinds.EXIT_BOUNDARY, "緊急帰投 峡谷境界ライン", "Phase 7 クリア離脱リングの座標"),
        ],
        default=Zadanie00MarkerKinds.OUTPOST_04,
    )