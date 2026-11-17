# -*- coding: utf-8 -*-
"""
Mission Editor - DirectX 実機 HTTP ライブ同期サーバー
空のBlenderプロジェクトでは待機状態 (Port 8766) のみ開始し、
ゲーム (25B_GE_CG.exe) が起動して接続された瞬間に全地形(100チャンク)とアクティブなミッションJSONを自動展開します。
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Tuple
from urllib.parse import parse_qs, urlparse
import bpy
from bpy.types import Object, Scene

from .constants import (
    EntityRoles,
    LiveSyncDefaults,
    MathConstants,
    PathConstants,
    TerrainDefaults,
    ViewportDefaults,
    WorkspaceDefaults,
    Zadanie00MarkerKinds,
)
from .properties import RepoPathResolver
from .serializer import MissionSceneSerializer
from .terrain_loader import TerrainChunkLoader


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class LiveSyncServerManager:
    """Blender ⇔ DirectX HTTP ライブ同期サーバーのシングルトン管理クラス"""

    _instance: Optional["LiveSyncServerManager"] = None

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._httpd: Optional[_ReusableThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._bound_port = LiveSyncDefaults.DEFAULT_PORT

        self._revision = LiveSyncDefaults.ZERO_REVISION
        self._reset_revision = LiveSyncDefaults.ZERO_REVISION
        self._client_poll_count = MathConstants.ZERO_INT
        self._requested_mission_file = ""
        self._last_synced_game_file = ""
        self._last_mission_signature = ""
        self._last_ambush_coords: Optional[Tuple] = None
        self._cached_payload_bytes = self._build_empty_payload_bytes()

    @staticmethod
    def _build_empty_payload_bytes() -> bytes:
        return json.dumps(
            {
                "revision": LiveSyncDefaults.ZERO_REVISION,
                "resetRevision": LiveSyncDefaults.ZERO_REVISION,
                "missionFilePath": "",
                "missionData": {},
            }
        ).encode("utf-8")

    @classmethod
    def instance(cls) -> "LiveSyncServerManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @staticmethod
    def has_any_mission_entities(scene: Scene) -> bool:
        for obj in scene.objects:
            if hasattr(obj, "mission_obj") and obj.mission_obj.entity_role != EntityRoles.NONE:
                return True
        return False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def bound_port(self) -> int:
        return self._bound_port

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    @property
    def reset_revision(self) -> int:
        with self._lock:
            return self._reset_revision

    @property
    def client_poll_count(self) -> int:
        with self._lock:
            return self._client_poll_count

    def reset_for_new_blend_session(self, scene: Scene) -> None:
        """新規空プロジェクト起動時または .blend 読込時に待機状態をリセットする"""
        if self.has_any_mission_entities(scene):
            with self._lock:
                self._last_synced_game_file = scene.mission_settings.mission_file_path
            self.push_now(scene, request_restart=False)
        else:
            with self._lock:
                self._revision = LiveSyncDefaults.ZERO_REVISION
                self._reset_revision = LiveSyncDefaults.ZERO_REVISION
                self._client_poll_count = MathConstants.ZERO_INT
                self._requested_mission_file = ""
                self._last_synced_game_file = ""
                self._last_mission_signature = ""
                self._last_ambush_coords = None
                self._cached_payload_bytes = self._build_empty_payload_bytes()

    def notify_manual_mission_loaded(self, scene: Scene) -> None:
        """ユーザーがBlender上で手動でミッションを開いた/保存した際に同期基準を更新する"""
        with self._lock:
            fp = scene.mission_settings.mission_file_path
            self._last_synced_game_file = str(RepoPathResolver.resolve_path(scene, fp)) if fp else ""
        if self._running:
            self.push_now(scene, request_restart=False)

    def start(self, scene: Scene) -> Tuple[bool, str]:
        port = int(scene.mission_settings.live_sync_port)
        if self._running and self._bound_port == port:
            if self.has_any_mission_entities(scene):
                self.push_now(scene, request_restart=False)
            return (True, f"Live Sync 稼働中 (http://{LiveSyncDefaults.HOST}:{port}{LiveSyncDefaults.ENDPOINT_LIVE})")

        if self._running:
            self.stop()

        manager_ref = self

        class _LiveSyncRequestHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                if parsed.path == LiveSyncDefaults.ENDPOINT_LIVE:
                    q_params = parse_qs(parsed.query)
                    file_list = q_params.get(LiveSyncDefaults.QUERY_KEY_FILE, [""])
                    req_file = file_list[MathConstants.ZERO_INT].strip() if file_list else ""
                    terrain_list = q_params.get("terrain", [""])
                    req_terrain = terrain_list[MathConstants.ZERO_INT].strip() if terrain_list else ""
                    if req_terrain:
                        with manager_ref._lock:
                            manager_ref._requested_terrain_path = req_terrain
                    body = manager_ref._on_client_poll_live(req_file)
                    self.send_response(LiveSyncDefaults.HTTP_OK)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    self.wfile.write(body)
                elif parsed.path == LiveSyncDefaults.ENDPOINT_HEALTH:
                    health_bytes = json.dumps(
                        {"status": "ok", "revision": manager_ref.revision}
                    ).encode("utf-8")
                    self.send_response(LiveSyncDefaults.HTTP_OK)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(health_bytes)))
                    self.end_headers()
                    self.wfile.write(health_bytes)
                else:
                    self.send_response(LiveSyncDefaults.HTTP_NOT_FOUND)
                    self.end_headers()

            def log_message(self, _format: str, *_args) -> None:
                return

        try:
            self._httpd = _ReusableThreadingHTTPServer((LiveSyncDefaults.HOST, port), _LiveSyncRequestHandler)
        except OSError as exc:
            self._httpd = None
            return (False, f"ポート {port} のバインドに失敗しました: {exc}")

        self._bound_port = port
        self._running = True
        if self.has_any_mission_entities(scene):
            self.push_now(scene, request_restart=False)

        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name="MissionLiveSyncHTTP",
            daemon=True,
        )
        self._thread.start()

        if not bpy.app.timers.is_registered(_live_sync_timer_callback):
            bpy.app.timers.register(
                _live_sync_timer_callback,
                first_interval=LiveSyncDefaults.TIMER_INTERVAL_SEC,
                persistent=True,
            )

        return (
            True,
            f"Live Sync 開始: http://{LiveSyncDefaults.HOST}:{port}{LiveSyncDefaults.ENDPOINT_LIVE}",
        )

    def stop(self) -> None:
        self._running = False
        if bpy.app.timers.is_registered(_live_sync_timer_callback):
            try:
                bpy.app.timers.unregister(_live_sync_timer_callback)
            except ValueError:
                pass

        if self._httpd is not None:
            try:
                self._httpd.shutdown()
                self._httpd.server_close()
            except Exception:
                pass
            self._httpd = None
        self._thread = None

    def push_now(self, scene: Scene, request_restart: bool = False) -> int:
        """現在の Blender シーン状態を即時シリアライズし、リビジョンを進めて配信キャッシュを更新する"""
        if not self.has_any_mission_entities(scene):
            return self.revision

        self._sync_ambush_curve_if_moved(scene)
        mission_dict = MissionSceneSerializer.build_mission_dict(scene)
        sig = json.dumps(mission_dict, sort_keys=True, ensure_ascii=False)
        rel_path = scene.mission_settings.mission_file_path

        with self._lock:
            self._last_mission_signature = sig
            self._revision += MathConstants.ONE_INT
            if request_restart:
                self._reset_revision += MathConstants.ONE_INT
            envelope = {
                "revision": self._revision,
                "resetRevision": self._reset_revision,
                "missionFilePath": rel_path,
                "missionData": mission_dict,
            }
            self._cached_payload_bytes = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
            return self._revision

    def tick_from_main_thread(self) -> Optional[float]:
        """bpy.app.timers から定期実行されるメインスレッド監視コールバック"""
        if not self._running:
            return None

        scene = getattr(bpy.context, "scene", None)
        if scene is None and len(bpy.data.scenes) > MathConstants.ZERO_INT:
            scene = bpy.data.scenes[MathConstants.ZERO_INT]
        if scene is None or not hasattr(scene, "mission_settings"):
            return LiveSyncDefaults.TIMER_INTERVAL_SEC

        with self._lock:
            polls = self._client_poll_count
            req_file = self._requested_mission_file
            last_synced_file = self._last_synced_game_file
            req_terrain = getattr(self, "_requested_terrain_path", "")
            last_terrain = getattr(self, "_last_synced_terrain_path", "")

        has_entities = self.has_any_mission_entities(scene)

        # ゲームが未起動 (polls == 0) かつ空のシーンの場合は何もせず待機 (勝手に地形を開かない)
        if not has_entities and polls == MathConstants.ZERO_INT:
            return LiveSyncDefaults.TIMER_INTERVAL_SEC

        # ゲームが起動・接続された瞬間 (polls > 0):
        # シーンが空の場合、またはゲーム側で別ミッション/別地形に切り替わった場合に全地形＋ミッションを自動展開
        if polls > MathConstants.ZERO_INT:
            needs_initial_load = not has_entities
            try:
                req_resolved = str(RepoPathResolver.resolve_path(scene, req_file)) if req_file else ""
                last_resolved = str(RepoPathResolver.resolve_path(scene, last_synced_file)) if last_synced_file else ""
                cur_resolved = str(RepoPathResolver.resolve_path(scene, scene.mission_settings.mission_file_path)) if scene.mission_settings.mission_file_path else ""
            except Exception:
                req_resolved, last_resolved, cur_resolved = req_file, last_synced_file, scene.mission_settings.mission_file_path

            needs_mission_switch = bool(
                req_resolved
                and req_resolved != last_resolved
                and req_resolved != cur_resolved
            )
            needs_terrain_switch = bool(req_terrain and req_terrain != last_terrain)
            if needs_initial_load or needs_mission_switch or needs_terrain_switch:
                self._auto_load_mission_on_game_connect(scene, req_file, req_terrain)
                return LiveSyncDefaults.TIMER_INTERVAL_SEC

        if not self.has_any_mission_entities(scene):
            return LiveSyncDefaults.TIMER_INTERVAL_SEC

        self._sync_ambush_curve_if_moved(scene)

        if not scene.mission_settings.live_sync_auto_push:
            return LiveSyncDefaults.TIMER_INTERVAL_SEC

        mission_dict = MissionSceneSerializer.build_mission_dict(scene)
        sig = json.dumps(mission_dict, sort_keys=True, ensure_ascii=False)
        if sig != self._last_mission_signature:
            rel_path = scene.mission_settings.mission_file_path
            with self._lock:
                self._last_mission_signature = sig
                self._revision += MathConstants.ONE_INT
                envelope = {
                    "revision": self._revision,
                    "resetRevision": self._reset_revision,
                    "missionFilePath": rel_path,
                    "missionData": mission_dict,
                }
                self._cached_payload_bytes = json.dumps(envelope, ensure_ascii=False).encode("utf-8")

        return LiveSyncDefaults.TIMER_INTERVAL_SEC

    def _auto_load_mission_on_game_connect(self, scene: Scene, requested_file: str, requested_terrain: str = "") -> None:
        """ゲーム接続検知時に専用『ミッション編集』ワークスペースへ切り替え、ゲーム側と同一の地形とミッションJSONを自動展開する"""
        for default_name in TerrainDefaults.DEFAULT_STARTUP_OBJECTS:
            obj = bpy.data.objects.get(default_name)
            if obj is not None:
                bpy.data.objects.remove(obj, do_unlink=True)

        scene.mission_settings.is_mission_mode_active = True
        self._activate_mission_workspace()

        target_mission_path = requested_file if requested_file else PathConstants.MISSION_00_REL_PATH
        scene.mission_settings.terrain_load_mode = TerrainDefaults.MODE_ALL_CHUNKS
        TerrainChunkLoader.load_chunks_for_mode(bpy.context, terrain_info_path=(requested_terrain or None))
        if requested_terrain:
            with self._lock:
                self._last_synced_terrain_path = requested_terrain
        MissionSceneSerializer.import_mission_json(bpy.context, target_mission_path)

        player_obj: Optional[Object] = None
        for obj in scene.objects:
            if hasattr(obj, "mission_obj") and obj.mission_obj.entity_role == EntityRoles.PLAYER_START:
                player_obj = obj
                break

        self._configure_viewports_and_selection(player_obj)

        self._sync_ambush_curve_if_moved(scene)
        mission_dict = MissionSceneSerializer.build_mission_dict(scene)
        sig = json.dumps(mission_dict, sort_keys=True, ensure_ascii=False)

        with self._lock:
            self._last_synced_game_file = str(RepoPathResolver.resolve_path(scene, target_mission_path))
            self._last_mission_signature = sig

        self._tag_redraw_all_windows()

    @staticmethod
    def _activate_mission_workspace() -> None:
        wm = bpy.context.window_manager
        if wm is None:
            return
        mission_ws = bpy.data.workspaces.get(WorkspaceDefaults.MISSION_WORKSPACE_NAME)
        if mission_ws is None:
            return
        for win in wm.windows:
            if win.workspace != mission_ws:
                win.workspace = mission_ws

    @staticmethod
    def _configure_viewports_and_selection(focus_target: Optional[Object]) -> None:
        screens = set()
        wm = bpy.context.window_manager
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

    @staticmethod
    def _tag_redraw_all_windows() -> None:
        wm = bpy.context.window_manager
        if wm is None:
            return
        for win in wm.windows:
            scr = win.screen
            if scr is None:
                continue
            for area in scr.areas:
                area.tag_redraw()

    def _on_client_poll_live(self, requested_file: str) -> bytes:
        with self._lock:
            self._client_poll_count += MathConstants.ONE_INT
            if requested_file:
                self._requested_mission_file = requested_file.replace("\\", "/")
            return self._cached_payload_bytes

    def _sync_ambush_curve_if_moved(self, scene: Scene) -> None:
        if not scene.mission_settings.is_zadanie_00_mode:
            if self._last_ambush_coords is not None:
                self._last_ambush_coords = None
                MissionSceneSerializer.refresh_zadanie00_ambush_curve(scene)
            return

        coords = []
        for obj in scene.objects:
            if hasattr(obj, "mission_obj") and obj.mission_obj.entity_role == EntityRoles.ZADANIE00_MARKER:
                if obj.mission_obj.z00_marker_kind in (
                    Zadanie00MarkerKinds.WESTERN_DIVE_START,
                    Zadanie00MarkerKinds.WESTERN_DIVE_MID,
                    Zadanie00MarkerKinds.WESTERN_PULLUP,
                ):
                    loc = obj.matrix_world.translation
                    coords.append(
                        (
                            obj.mission_obj.z00_marker_kind,
                            round(loc.x, MathConstants.ROUND_DIGITS),
                            round(loc.y, MathConstants.ROUND_DIGITS),
                            round(loc.z, MathConstants.ROUND_DIGITS),
                        )
                    )
        coords.sort()
        coords_tuple = tuple(coords)
        if coords_tuple != self._last_ambush_coords:
            self._last_ambush_coords = coords_tuple
            MissionSceneSerializer.refresh_zadanie00_ambush_curve(scene)


def _live_sync_timer_callback() -> Optional[float]:
    return LiveSyncServerManager.instance().tick_from_main_thread()
