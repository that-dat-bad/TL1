# -*- coding: utf-8 -*-

import bpy  # type: ignore
import json
import queue
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# グローバルサーバーインスタンス
_mcp_server_instance = None
_mcp_server_thread = None

# メインスレッドへのディスパッチ用キュー
_dispatch_queue = queue.Queue()


# ======================================================================
# メインスレッド ディスパッチ機構
# ======================================================================

class _DispatchRequest:
    """ワーカースレッドからメインスレッドへ処理を委譲するためのリクエスト"""
    def __init__(self, func, args=()):
        self.func = func
        self.args = args
        self.result = None
        self.error = None
        self.done = threading.Event()

    def execute(self):
        try:
            self.result = self.func(*self.args)
        except Exception as e:
            self.error = e
        finally:
            self.done.set()

    def wait(self, timeout=5.0):
        self.done.wait(timeout)
        if self.error is not None:
            raise self.error
        return self.result


def _dispatch_to_main_thread(func, *args, timeout=5.0):
    """関数をメインスレッドで実行し、結果を返す（最大timeout秒待機）"""
    request = _DispatchRequest(func, args)
    _dispatch_queue.put(request)
    return request.wait(timeout)


def _mcp_timer_callback():
    """bpy.app.timers に登録されるコールバック。
    メインスレッドで呼ばれ、キューに積まれた処理を実行する。
    """
    try:
        while True:
            request = _dispatch_queue.get_nowait()
            request.execute()
    except queue.Empty:
        pass

    # サーバーがまだ起動中ならタイマーを継続（0.05秒間隔）
    if _mcp_server_instance is not None:
        return 0.05
    return None  # タイマーを停止


# ======================================================================
# bpy API を呼び出す関数群（メインスレッドで実行される）
# ======================================================================

def _get_status():
    """サーバーのステータスを取得（メインスレッド専用）"""
    terrain_obj = bpy.data.objects.get("Terrain")
    return {
        "status": "running",
        "terrain_exists": terrain_obj is not None,
        "blender_version": ".".join(str(v) for v in bpy.app.version),
        "scene_name": bpy.context.scene.name
    }


def _get_terrain_params():
    """現在の地形パラメータを取得（メインスレッド専用）"""
    terrain_obj = bpy.data.objects.get("Terrain")
    if not terrain_obj:
        return {"error": "Terrain object not found", "params": None}

    mod = terrain_obj.modifiers.get("TerrainGen")
    if not mod:
        return {"error": "TerrainGen modifier not found", "params": None}

    params = _read_modifier_params(mod)
    mountains = _get_spline_data("Mountains")
    valleys = _get_spline_data("Valleys")

    return {
        "params": params,
        "mountains": mountains,
        "valleys": valleys,
        "transform": {
            "location": list(terrain_obj.location),
            "rotation": [terrain_obj.rotation_euler.x,
                         terrain_obj.rotation_euler.y,
                         terrain_obj.rotation_euler.z],
            "scale": list(terrain_obj.scale)
        }
    }


def _post_terrain_params(data):
    """パラメータを更新（メインスレッド専用）"""
    terrain_obj = bpy.data.objects.get("Terrain")
    if not terrain_obj:
        return {"error": "Terrain object not found", "code": 404}

    mod = terrain_obj.modifiers.get("TerrainGen")
    if not mod:
        return {"error": "TerrainGen modifier not found", "code": 404}

    updated_keys = []
    params = data.get("params", {})
    for key, value in params.items():
        try:
            if key in mod:
                mod[key] = value
                updated_keys.append(key)
        except Exception as e:
            print(f"[MCP] Failed to set {key}: {e}")

    return {"status": "ok", "updated": updated_keys}


def _read_modifier_params(mod):
    """モディファイアからパラメータを辞書に読み取る"""
    params = {}
    known_keys = [
        'Grid Size X', 'Grid Size Y',
        'Subdivisions X', 'Subdivisions Y',
        'Noise Scale', 'Terrain Height',
        'Mountain Height', 'Mountain Radius',
        'Valley Depth', 'Valley Radius',
        'Flat Radius', 'Flat Blend',
        'Hole Size'
    ]
    for key in known_keys:
        try:
            if key in mod:
                val = mod[key]
                if hasattr(val, '__iter__'):
                    params[key] = list(val)
                else:
                    params[key] = val
        except Exception:
            pass

    # Hole Location (Vector型)
    try:
        if 'Hole Location' in mod:
            loc = mod['Hole Location']
            params['Hole Location'] = [loc[0], loc[1], loc[2]]
    except Exception:
        pass

    return params


def _get_spline_data(collection_name):
    """指定コレクション内のスプラインカーブの制御点データを取得"""
    col = bpy.data.collections.get(collection_name)
    if not col:
        return []

    splines_data = []
    for obj in col.objects:
        if obj.type != 'CURVE':
            continue
        obj_data = {
            "name": obj.name,
            "location": list(obj.location),
            "splines": []
        }
        for spline in obj.data.splines:
            points = []
            if spline.type == 'BEZIER':
                for bp in spline.bezier_points:
                    points.append(list(bp.co))
            elif spline.type == 'POLY':
                for pt in spline.points:
                    points.append([pt.co[0], pt.co[1], pt.co[2]])
            obj_data["splines"].append({
                "type": spline.type,
                "points": points
            })
        splines_data.append(obj_data)
    return splines_data


# ======================================================================
# HTTP リクエストハンドラ
# ======================================================================

class TerrainMCPHandler(BaseHTTPRequestHandler):
    """地形パラメータを提供するHTTPリクエストハンドラ

    注意: このクラスのメソッドはワーカースレッドから呼ばれるため、
    bpy API を直接呼んではいけません。_dispatch_to_main_thread() を使用してください。
    """

    def log_message(self, format, *args):
        """コンソールログを制御（Blenderのコンソールに出力）"""
        print(f"[MCP] {args[0]}")

    def do_GET(self):
        """GETリクエストの処理"""
        if self.path == "/terrain/params":
            self._handle_get_terrain_params()
        elif self.path == "/terrain/status":
            self._handle_get_status()
        elif self.path == "/":
            self._handle_root()
        else:
            self._send_error(404, "Not Found")

    def do_POST(self):
        """POSTリクエストの処理"""
        if self.path == "/terrain/params":
            self._handle_post_terrain_params()
        else:
            self._send_error(404, "Not Found")

    def _handle_root(self):
        """ルートエンドポイント - サーバー情報を返す（bpy不使用なのでスレッドセーフ）"""
        info = {
            "server": "Blender Terrain MCP Server",
            "version": "1.0.0",
            "protocol": "MCP",
            "endpoints": [
                "GET /terrain/params",
                "GET /terrain/status",
                "POST /terrain/params"
            ]
        }
        self._send_json(info)

    def _handle_get_status(self):
        """サーバーのステータスを返す"""
        try:
            result = _dispatch_to_main_thread(_get_status)
            self._send_json(result)
        except Exception as e:
            self._send_error(500, f"Internal error: {e}")

    def _handle_get_terrain_params(self):
        """現在の地形パラメータをJSONで返す"""
        try:
            result = _dispatch_to_main_thread(_get_terrain_params)
            self._send_json(result)
        except Exception as e:
            self._send_error(500, f"Internal error: {e}")

    def _handle_post_terrain_params(self):
        """POSTされたパラメータで地形モディファイアを更新する"""
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self._send_error(400, "Empty request body")
            return

        body = self.rfile.read(content_length)
        try:
            data = json.loads(body.decode('utf-8'))
        except json.JSONDecodeError:
            self._send_error(400, "Invalid JSON")
            return

        try:
            result = _dispatch_to_main_thread(_post_terrain_params, data)
            if "error" in result:
                self._send_error(result.get("code", 500), result["error"])
            else:
                self._send_json(result)
        except Exception as e:
            self._send_error(500, f"Internal error: {e}")

    def _send_json(self, data):
        """JSONレスポンスを送信"""
        response = json.dumps(data, ensure_ascii=False, indent=2)
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(response.encode('utf-8'))

    def _send_error(self, code, message):
        """エラーレスポンスを送信"""
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        error_data = json.dumps({"error": message})
        self.wfile.write(error_data.encode('utf-8'))


# ======================================================================
# オペレータ
# ======================================================================

class MYADDON_OT_start_mcp_server(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_start_mcp_server"
    bl_label = "MCPサーバー開始"
    bl_description = "地形パラメータ同期用のMCPサーバーを開始します (ポート 8765)"

    def execute(self, context):
        global _mcp_server_instance, _mcp_server_thread

        if _mcp_server_instance is not None:
            self.report({'WARNING'}, "MCPサーバーは既に起動中です")
            return {'CANCELLED'}

        port = 8765
        try:
            _mcp_server_instance = HTTPServer(('localhost', port), TerrainMCPHandler)
            _mcp_server_thread = threading.Thread(
                target=_mcp_server_instance.serve_forever,
                daemon=True
            )
            _mcp_server_thread.start()

            # メインスレッドのディスパッチタイマーを開始
            bpy.app.timers.register(_mcp_timer_callback, first_interval=0.05)

            self.report({'INFO'}, f"MCPサーバーを開始しました (localhost:{port})")
            print(f"[MCP] サーバー開始: http://localhost:{port}")
        except OSError as e:
            self.report({'ERROR'}, f"MCPサーバーの起動に失敗しました: {e}")
            _mcp_server_instance = None
            return {'CANCELLED'}

        return {'FINISHED'}


class MYADDON_OT_stop_mcp_server(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_stop_mcp_server"
    bl_label = "MCPサーバー停止"
    bl_description = "MCPサーバーを停止します"

    def execute(self, context):
        global _mcp_server_instance, _mcp_server_thread

        if _mcp_server_instance is None:
            self.report({'WARNING'}, "MCPサーバーは起動していません")
            return {'CANCELLED'}

        _mcp_server_instance.shutdown()
        _mcp_server_instance = None
        _mcp_server_thread = None
        
        # キューに残ったリクエストを解放する
        try:
            while True:
                request = _dispatch_queue.get_nowait()
                request.error = RuntimeError("Server shutting down")
                request.done.set()
        except queue.Empty:
            pass

        self.report({'INFO'}, "MCPサーバーを停止しました")
        print("[MCP] サーバー停止")
        return {'FINISHED'}
