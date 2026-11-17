# -*- coding: utf-8 -*-
import bpy  # type: ignore
import json
import os
import urllib.request
import urllib.error
import textwrap

try:
    from .terrain_materials import detect_biomes, detect_biome, apply_biome_material_to_terrain, detect_road_type, get_or_create_road_material
    from .terrain_blueprint import compile_blueprint, route_road_around_mountains, smooth_and_resample_road
    from .gn_utils import set_modifier_input
    from .blueprint_store import load_blueprint
    from .terrain_pipeline import execute_blueprint_pipeline
except ImportError:
    import sys
    sys.path.append(os.path.dirname(__file__))
    from terrain_materials import detect_biomes, detect_biome, apply_biome_material_to_terrain, detect_road_type, get_or_create_road_material
    from terrain_blueprint import compile_blueprint, route_road_around_mountains, smooth_and_resample_road
    from gn_utils import set_modifier_input
    from blueprint_store import load_blueprint
    from terrain_pipeline import execute_blueprint_pipeline

try:
    from level_editor_city.create_road import setup_mixed_road_geometry_nodes, setup_road_geometry_nodes
except ImportError:
    try:
        from ..level_editor_city.create_road import setup_mixed_road_geometry_nodes, setup_road_geometry_nodes
    except ImportError:
        setup_mixed_road_geometry_nodes = None
        setup_road_geometry_nodes = None

CONFIG_PATH = os.path.join(os.path.dirname(__file__), ".ai_terrain_config.json")

def load_ai_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_ai_config(key, val):
    try:
        data = load_ai_config()
        data[key] = val
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

_cached_models = None

def get_ollama_models(self, context):
    global _cached_models
    if _cached_models is not None:
        return _cached_models
        
    url = "http://localhost:11434/api/tags"
    items = []
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=1.0) as response:
            data = json.loads(response.read().decode('utf-8'))
            for m in data.get('models', []):
                name = m.get('name', 'unknown')
                items.append((name, name, f"{name} を使用"))
    except Exception:
        items.append(('error', "通信エラー(Ollama未起動)", "Ollamaが起動していません"))
        
    if not items:
        items.append(('none', "モデルが見つかりません", "Ollamaにモデルがありません"))
        
    _cached_models = items
    return _cached_models

class MYADDON_OT_ai_generate_terrain(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_ai_generate_terrain"
    bl_label = "AIによる地形自動生成 (Gemini / Ollama)"
    bl_description = "GeminiまたはOllamaを使用して、テキストプロンプトから地形・道・街・山・谷を自動生成します"
    bl_options = {'REGISTER', 'UNDO'}

    ai_provider: bpy.props.EnumProperty(
        name="AIプロバイダ",
        description="使用するAIサービスを選択",
        items=[
            ('GEMINI', "Google Gemini (推奨)", "クラウドAPI。日本語ネイティブ理解・超高速・高品質"),
            ('OLLAMA', "Ollama (ローカル)", "PCローカルで動作するオープンモデル"),
        ],
        default='GEMINI'
    ) # type: ignore

    gemini_api_key: bpy.props.StringProperty(
        name="Gemini API Key",
        description="Google AI Studioで取得したAPIキーを入力してください",
        default="",
        subtype='PASSWORD'
    ) # type: ignore

    gemini_model: bpy.props.EnumProperty(
        name="Geminiモデル",
        description="使用するGeminiモデルを選択",
        items=[
            ('gemini-3.5-flash', "Gemini 3.5 Flash (推奨・安定・超高速)", "Google公式の高速・高精度主力モデル"),
            ('gemini-2.5-flash', "Gemini 2.5 Flash (安定版)", "実績のある標準Flashモデル"),
            ('gemini-3-flash-preview', "Gemini 3 Flash Preview", "次世代Flashプレビュー版"),
            ('gemini-3.8-flash', "Gemini 3.8 Flash (混雑時503あり)", "最新世代Flashモデル（高負荷時あり）"),
            ('gemini-flash-latest', "Gemini Flash Latest (混雑時503あり)", "常に最新版のFlashエイリアス"),
            ('gemini-3.1-pro-preview', "Gemini 3.1 Pro (最新推論モデル)", "高度推論Proモデル"),
        ],
        default='gemini-3.5-flash'
    ) # type: ignore

    prompt: bpy.props.StringProperty(
        name="プロンプト",
        description="どのような地形を作りたいか入力してください",
        default="中央に南北の谷があり、東側の平坦地に道路と街が広がっている40km四方の地形",
        maxlen=1024,
    ) # type: ignore

    terrain_scale: bpy.props.EnumProperty(
        name="地形スケール",
        description="地形の全体サイズ（幅×奥行）を選択",
        items=[
            ('40KM', "40km 四方 (40,000m × 40,000m: 超広大)", "戦闘機や広域オープンワールド向け広大スケール（推奨）"),
            ('20KM', "20km 四方 (20,000m × 20,000m: 標準)", "従来の20kmオープンワールドスケール"),
        ],
        default='40KM',
    ) # type: ignore

    model_name: bpy.props.EnumProperty(
        name="Ollamaモデル",
        description="Ollamaで使用するモデルを選択",
        items=get_ollama_models
    ) # type: ignore

    preset: bpy.props.EnumProperty(
        name="起伏プリセット",
        description="ベースとなる地形の起伏タイプ",
        items=[
            ('AUTO', "起伏: 自動判別 (Auto)", "プロンプトからAIが自動的に起伏の強さを判定"),
            ('FLAT', "平野 / 街 (Flat / City)", "ベース起伏を平坦にし、都市や道路に適した地面にします"),
            ('HILLS', "丘陵 (Hills)", "なだらかな起伏のある自然な地形にします"),
            ('MOUNTAINS', "山岳 (Mountains)", "起伏の激しい山地・渓谷にします"),
        ],
        default='AUTO'
    ) # type: ignore

    biome: bpy.props.EnumProperty(
        name="バイオーム (質感)",
        description="地形のマテリアル・環境タイプ（砂漠、雪原、峡谷、火山、草原、複合など）",
        items=[
            ('AUTO', "バイオーム: 自動判別 (Auto)", "プロンプトから単一または複合バイオームを自動判別"),
            ('MULTI', "複合大陸 (Multi-Biome)", "標高連動の雪山山頂＋大域ノイズによる草原・砂漠・峡谷の複合バイオーム"),
            ('PLAINS', "草原 (Plains)", "緑豊かな大地と土岩の崖"),
            ('DESERT', "砂漠 (Desert)", "オレンジ・黄色の砂紋と赤褐色の崖"),
            ('SNOW', "雪原 / 氷河 (Snow)", "白銀の雪原と青暗い岩壁"),
            ('CANYON', "峡谷 (Canyon)", "テラコッタ層の赤土と崖"),
            ('VOLCANO', "火山 / 荒野 (Volcano)", "玄武岩の黒灰と赤黒い岩"),
        ],
        default='AUTO'
    ) # type: ignore

    seed: bpy.props.IntProperty(
        name="シード値 (0=自動ランダム)",
        description="地形と街並みのランダムシード（0を指定すると実行ごとに自動変更）",
        default=0,
        min=0,
        max=999999
    ) # type: ignore

    edit_mode: bpy.props.EnumProperty(
        name="生成モード",
        description="新規に地形を作成するか、現在のブループリントを部分修正するかを選択",
        items=[
            ('NEW', "新規生成", "現在の地形を置き換えて新しく生成します"),
            ('PATCH', "現在の地形を部分修正", "現在のブループリントを保持したまま差分パッチで部分修正します"),
        ],
        default='NEW'
    ) # type: ignore

    heightmap_resolution: bpy.props.EnumProperty(
        name="ハイトマップ解像度",
        description="NumPyハイトマップ＆侵食シミュレーションの解像度",
        items=[
            ('1024', "1024×1024 (標準・高速)", "約1〜2秒で生成・侵食・ベイク完了"),
            ('2048', "2048×2048 (高精細)", "40kmで約19.5m間隔の高精細ハイトマップ"),
        ],
        default='1024'
    ) # type: ignore

    use_heightmap_engine: bpy.props.BoolProperty(
        name="ハイトマップ＋侵食エンジンを使用",
        description="NumPyによる水食・熱侵食とAlbedo/Normal/Splatマップベイクを有効にします",
        default=True
    ) # type: ignore

    _timer = None
    _thread = None
    _result = None
    _error = None
    _active_seed = 0
    _current_blueprint = None

    def invoke(self, context, event):
        global _cached_models
        _cached_models = None

        # 設定ファイルの読み込み
        cfg = load_ai_config()
        if 'api_key' in cfg and not self.gemini_api_key:
            self.gemini_api_key = cfg['api_key']
        elif not self.gemini_api_key:
            self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
        if 'ai_provider' in cfg:
            self.ai_provider = cfg['ai_provider']
        if 'gemini_model' in cfg:
            saved_m = cfg['gemini_model']
            valid_models = {'gemini-3.5-flash', 'gemini-2.5-flash', 'gemini-3-flash-preview', 'gemini-3.8-flash', 'gemini-flash-latest', 'gemini-3.1-pro-preview'}
            if saved_m in valid_models:
                self.gemini_model = saved_m
            else:
                self.gemini_model = 'gemini-3.5-flash'
                save_ai_config("gemini_model", 'gemini-3.5-flash')

        return context.window_manager.invoke_props_dialog(self, width=460)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "ai_provider", expand=True)

        box = layout.box()
        if self.ai_provider == 'GEMINI':
            box.prop(self, "gemini_model")
            box.prop(self, "gemini_api_key")
            if not self.gemini_api_key.strip():
                box.label(text="※ aistudio.google.com で無料APIキーを取得できます", icon='INFO')
        else:
            box.prop(self, "model_name")

        row = layout.row(align=True)
        row.prop(self, "terrain_scale", text="")
        row.prop(self, "preset", text="")
        row.prop(self, "biome", text="")
        row2 = layout.row(align=True)
        row2.prop(self, "edit_mode", text="")
        row2.prop(self, "heightmap_resolution", text="")
        layout.prop(self, "use_heightmap_engine")
        layout.prop(self, "seed")
        layout.prop(self, "prompt", text="指示")
        layout.label(text="※ バックグラウンドで処理され、完了時に地形・マテリアルが生成されます。", icon='INFO')

    def execute(self, context):
        import threading
        import time
        self._result = None
        self._error = None
        self._active_seed = self.seed if self.seed > 0 else (int(time.time() * 1000) % 1000000 or 1)
        self._current_blueprint = None

        if self.edit_mode == 'PATCH':
            bp, meta = load_blueprint(context.scene)
            if not bp:
                self.report({'WARNING'}, "既存のブループリントが見つからないため新規生成として実行します")
            else:
                self._current_blueprint = bp
                if self.seed == 0 and meta.get("seed"):
                    self._active_seed = int(meta["seed"])

        # 設定の保存
        save_ai_config("ai_provider", self.ai_provider)
        if self.ai_provider == 'GEMINI':
            key = self.gemini_api_key.strip()
            if not key:
                key = os.environ.get("GEMINI_API_KEY", "")
            if not key:
                self.report({'ERROR'}, "Gemini APIキーを入力してください (Google AI Studioで取得可能)")
                return {'CANCELLED'}
            save_ai_config("api_key", key)
            save_ai_config("gemini_model", self.gemini_model)
            self._thread = threading.Thread(
                target=self.run_gemini_request,
                args=(self.gemini_model, key, self.prompt, self.preset, self.terrain_scale, self._current_blueprint)
            )
        else:
            self._thread = threading.Thread(
                target=self.run_ollama_request,
                args=(self.model_name, self.prompt, self.preset, self.terrain_scale, self._current_blueprint)
            )

        self._thread.start()
        
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        
        self.report({'INFO'}, f"{self.ai_provider} にリクエストを送信中... しばらくお待ちください")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            if not self._thread.is_alive():
                context.window_manager.event_timer_remove(self._timer)
                
                if self._error:
                    self.report({'ERROR'}, self._error)
                    return {'CANCELLED'}
                    
                if self._result:
                    if self.use_heightmap_engine:
                        final_bp, hm_meta, tex_paths = execute_blueprint_pipeline(
                            context,
                            self._result,
                            preset=self.preset,
                            terrain_scale=self.terrain_scale,
                            biome=self.biome,
                            prompt=self.prompt,
                            seed=getattr(self, '_active_seed', 1),
                            resolution=int(self.heightmap_resolution),
                            is_patch=(self._current_blueprint is not None),
                            operator=self,
                        )
                        try:
                            for area in context.screen.areas:
                                if area.type == 'VIEW_3D':
                                    for space in area.spaces:
                                        if space.type == 'VIEW_3D':
                                            space.shading.type = 'MATERIAL'
                        except Exception:
                            pass
                        stats = hm_meta.get("stats", {})
                        self.report(
                            {'INFO'},
                            f"AIハイトマップ地形生成完了 ({hm_meta.get('resolution')}px / 標高 {stats.get('min_height')}m〜{stats.get('max_height')}m)",
                        )
                        return {'FINISHED'}

                    compiled = compile_blueprint(
                        self._result,
                        preset=self.preset,
                        terrain_scale=self.terrain_scale,
                        prompt=self.prompt,
                        seed=getattr(self, '_active_seed', 0),
                    )
                    target_height = compiled["terrain_height"]
                    if target_height < 25.0:
                        exec_preset = 'FLAT'
                    elif target_height < 200.0:
                        exec_preset = 'HILLS'
                    else:
                        exec_preset = 'MOUNTAINS'

                    self.generate_splines(context, compiled)
                    init_biome = self.biome if self.biome != 'AUTO' else 'MULTI'
                    bpy.ops.myaddon.myaddon_ot_create_terrain(preset=exec_preset, biome=init_biome, terrain_scale=self.terrain_scale)
                    
                    terrain_obj = bpy.data.objects.get("Terrain")
                    road_obj = bpy.data.objects.get("RoadPath_AI")
                    
                    # バイオーム（質感・マテリアル）の判定と適用
                    sub_biomes = detect_biomes(self.prompt, self.biome)
                    detected_biome = detect_biome(self.prompt, self.biome)
                    if terrain_obj:
                        apply_biome_material_to_terrain(terrain_obj, detected_biome, sub_biomes=sub_biomes)

                    if terrain_obj:
                        mod = terrain_obj.modifiers.get("TerrainGen")
                        if mod:
                            set_modifier_input(mod, 'Grid Size X', compiled["terrain_size_x"])
                            set_modifier_input(mod, 'Grid Size Y', compiled["terrain_size_y"])
                            set_modifier_input(mod, 'Terrain Height', compiled["terrain_height"])
                            set_modifier_input(mod, 'Noise Scale', compiled["noise_scale"])
                            set_modifier_input(mod, 'Ridge Sharpness', compiled["ridge_sharpness"])
                            set_modifier_input(mod, 'Detail Strength', 0.20 + compiled["ridge_sharpness"] * 0.45)
                            set_modifier_input(mod, 'Noise Offset', tuple(compiled.get("noise_offset", (0.0, 0.0, 0.0))))
                            set_modifier_input(mod, 'City Center', tuple(compiled.get("city_center", (0.0, 0.0, 0.0))))
                            set_modifier_input(mod, 'City Grade Radius', float(compiled.get("city_grade_radius", 0.0)))
                            set_modifier_input(mod, 'Flat Radius', 65.0)
                            set_modifier_input(mod, 'Flat Blend', 180.0)
                            
                            # 谷コレクションと山岳コレクションを確実に接続（コンパイル済みパラメータを反映）
                            val_col = bpy.data.collections.get("Valleys")
                            if val_col:
                                set_modifier_input(mod, 'Valley Collection', val_col)
                                set_modifier_input(mod, 'Valley Depth', compiled["valley_depth"])
                                set_modifier_input(mod, 'Valley Radius', compiled["valley_radius"])

                            mt_col = bpy.data.collections.get("Mountains")
                            if mt_col:
                                set_modifier_input(mod, 'Mountain Collection', mt_col)
                                set_modifier_input(mod, 'Mountain Height', compiled["mountain_height"])
                                set_modifier_input(mod, 'Mountain Radius', compiled["mountain_radius"])

                            # RoadおよびTunnelCuttersの割り当てを一時解除し、 intact な地形メッシュでレイキャストを行う
                            set_modifier_input(mod, 'Road Object', None)
                            set_modifier_input(mod, 'Tunnel Cutters', None)
                            tun_cut_col = self.get_or_create_collection(context, "TunnelCutters")
                            self.clear_ai_objects(tun_cut_col)
                            tun_col = self.get_or_create_collection(context, "Tunnels")
                            self.clear_ai_objects(tun_col)
                            terrain_obj.update_tag()
                            context.view_layer.update()
                            context.evaluated_depsgraph_get().update()
                                    
                            # Terrainの高さをRoadに投影（橋梁＋山岳トンネル自動生成・地上/トンネル道路分離）
                            if road_obj:
                                self.project_road_to_terrain(
                                    context,
                                    road_obj,
                                    terrain_obj,
                                    water_level=compiled.get("water_level"),
                                    valley_radius=compiled.get("valley_radius", 1500.0),
                                    mountain_radius=compiled.get("mountain_radius", 1400.0),
                                    has_tunnels=compiled.get("has_tunnels", False),
                                )
                                tun_cut_col = bpy.data.collections.get("TunnelCutters")
                                if tun_cut_col and len(tun_cut_col.objects) > 0:
                                    set_modifier_input(mod, 'Tunnel Cutters', tun_cut_col)
                                # 道路をスケールに見合う幅(幹線24m / 街路12m)でGeometry Nodes立体メッシュ化
                                road_obj.data.dimensions = '3D'
                                road_obj.data.bevel_depth = 0.0
                                road_obj.data.bevel_resolution = 0
                                
                                sub_road_type = detect_road_type(self.prompt, detected_biome)
                                # 混在道路ノードが未設定の場合のフォールバック
                                if not road_obj.modifiers.get("RoadGen") and setup_mixed_road_geometry_nodes:
                                    setup_mixed_road_geometry_nodes(
                                        curve_obj=road_obj,
                                        primary_type='ASPHALT',
                                        secondary_type=sub_road_type,
                                        main_width=24.0,
                                        sub_width=12.0
                                    )
                                # 分離されたトンネル内道路オブジェクトにも道路Geometry Nodesを適用（TerrainGenのRoad Objectには渡さない）
                                tun_road_obj = bpy.data.objects.get("RoadPath_Tunnel_AI")
                                if tun_road_obj and setup_mixed_road_geometry_nodes:
                                    if not tun_road_obj.modifiers.get("RoadGen"):
                                        setup_mixed_road_geometry_nodes(
                                            curve_obj=tun_road_obj,
                                            primary_type='ASPHALT',
                                            secondary_type=sub_road_type,
                                            main_width=24.0,
                                            sub_width=12.0,
                                            main_lanes=4,
                                            line_width=0.15,
                                        )
                                
                            # --- Procedural City Generation (Step 2: City Districts & Blocks) ---
                            if compiled.get("has_city") and hasattr(self, '_generator') and self._generator:
                                try:
                                    lots = self._generator.generate_building_lots()
                                    if lots:
                                        self.spawn_buildings(context, lots, terrain_obj, detected_biome, sub_biomes=sub_biomes)
                                except Exception as e:
                                    print(f"Building lot generation failed: {e}")
                            # ----------------------------------------------------------------
                                
                            # RoadをTerrainに割り当て直す
                            if road_obj:
                                set_modifier_input(mod, 'Road Object', road_obj)
                            terrain_obj.update_tag()
                            context.view_layer.update()

                    # 3Dビューポートをマテリアルプレビューに切り替え、美しい景観を即座に表示
                    try:
                        for area in context.screen.areas:
                            if area.type == 'VIEW_3D':
                                for space in area.spaces:
                                    if space.type == 'VIEW_3D':
                                        space.shading.type = 'MATERIAL'
                    except:
                        pass
                                        
                    self.report({'INFO'}, f"AIによる地形生成が完了しました (起伏: {exec_preset} / 環境: {detected_biome})")
                    return {'FINISHED'}
                    
                return {'CANCELLED'}
        return {'PASS_THROUGH'}

    def _add_cube_to_bmesh(self, bm, cx, cy, hw, hh, z_min, z_max, angle=0.0, mat_index=0):
        import math
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        
        # 4隅のローカル座標を回転させて配置
        corners = [
            (-hw, -hh),
            (hw, -hh),
            (hw, hh),
            (-hw, hh)
        ]
        rc = []
        for dx, dy in corners:
            rx = cx + dx * cos_a - dy * sin_a
            ry = cy + dx * sin_a + dy * cos_a
            rc.append((rx, ry))
            
        v1 = bm.verts.new((rc[0][0], rc[0][1], z_min))
        v2 = bm.verts.new((rc[1][0], rc[1][1], z_min))
        v3 = bm.verts.new((rc[2][0], rc[2][1], z_min))
        v4 = bm.verts.new((rc[3][0], rc[3][1], z_min))
        
        v5 = bm.verts.new((rc[0][0], rc[0][1], z_max))
        v6 = bm.verts.new((rc[1][0], rc[1][1], z_max))
        v7 = bm.verts.new((rc[2][0], rc[2][1], z_max))
        v8 = bm.verts.new((rc[3][0], rc[3][1], z_max))
        
        faces = [
            bm.faces.new((v1, v4, v3, v2)), # Bottom
            bm.faces.new((v5, v6, v7, v8)), # Top
            bm.faces.new((v1, v2, v6, v5)), # Front
            bm.faces.new((v2, v3, v7, v6)), # Right
            bm.faces.new((v3, v4, v8, v7)), # Back
            bm.faces.new((v4, v1, v5, v8)), # Left
        ]
        if mat_index > 0:
            for f in faces:
                f.material_index = mat_index

    def spawn_buildings(self, context, lots, terrain_obj, biome='PLAINS', sub_biomes=None):
        import bmesh
        import mathutils
        import random
        import math
        
        # 既存のBuildingsコレクションとオブジェクトをクリア
        build_col = self.get_or_create_collection(context, "Buildings")
        self.clear_ai_objects(build_col)
        
        mesh = bpy.data.meshes.new("Buildings_AI")
        obj = bpy.data.objects.new("Buildings_AI", mesh)
        build_col.objects.link(obj)

        # マテリアル設定（バイオームに応じた建造物カラー）
        # MULTIの場合は複数のバイオーム用マテリアルを登録し、立地（標高・位置）に応じて面ごとに割り当て
        building_palette = {
            'PLAINS': ((0.85, 0.85, 0.88, 1.0), 0.25),
            'DESERT': ((0.86, 0.74, 0.58, 1.0), 0.80),
            'SNOW': ((0.78, 0.82, 0.88, 1.0), 0.35),
            'CANYON': ((0.75, 0.48, 0.36, 1.0), 0.75),
            'VOLCANO': ((0.28, 0.28, 0.30, 1.0), 0.60),
        }

        def get_or_create_building_mat(b_key):
            mat_name = f"Building_Biome_{b_key}"
            b_mat = bpy.data.materials.get(mat_name)
            if not b_mat:
                b_mat = bpy.data.materials.new(mat_name)
                b_mat.use_nodes = True
                bsdf = b_mat.node_tree.nodes.get("Principled BSDF")
                col, rough = building_palette.get(b_key, building_palette['PLAINS'])
                if bsdf:
                    bsdf.inputs["Base Color"].default_value = col
                    bsdf.inputs["Roughness"].default_value = rough
                b_mat.diffuse_color = col
            return b_mat

        is_multi = (biome == 'MULTI') or (sub_biomes and len(sub_biomes) >= 2)
        if is_multi:
            # 0: PLAINS, 1: DESERT, 2: SNOW, 3: CANYON, 4: VOLCANO
            mat_order = ['PLAINS', 'DESERT', 'SNOW', 'CANYON', 'VOLCANO']
            for k in mat_order:
                obj.data.materials.append(get_or_create_building_mat(k))
        else:
            obj.data.materials.append(get_or_create_building_mat(biome))
        
        bm = bmesh.new()
        
        context.view_layer.update()
        depsgraph = context.evaluated_depsgraph_get()
        
        for lot in lots:
            x, y = lot['x'], lot['y']
            w, h, z_height = lot['w'], lot['h'], lot['z_height']
            b_type = lot.get('type', 'MIDRISE')
            angle = lot.get('angle', 0.0)
            
            # 建物の中心＋四隅の5点に対してTerrainへレイキャスト（傾斜地での片側めり込み・浮きを防止）
            hw = w / 2.0
            hh = h / 2.0
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            sample_points = [
                (x, y),
                (x + hw * cos_a - hh * sin_a, y + hw * sin_a + hh * cos_a),
                (x - hw * cos_a - hh * sin_a, y - hw * sin_a + hh * cos_a),
                (x - hw * cos_a + hh * sin_a, y - hw * sin_a - hh * cos_a),
                (x + hw * cos_a + hh * sin_a, y + hw * sin_a - hh * cos_a),
            ]
            dir_world = mathutils.Vector((0.0, 0.0, -1.0))
            hit_zs = []
            center_normal_z = 1.0
            for idx_pt, (px, py) in enumerate(sample_points):
                current_origin = mathutils.Vector((px, py, 3000.0))
                for _ in range(10):
                    success, loc, norm, _, hit_obj, _ = context.scene.ray_cast(depsgraph, current_origin, dir_world)
                    if success:
                        if hit_obj and hit_obj.name == terrain_obj.name:
                            hit_zs.append(loc.z)
                            if idx_pt == 0:
                                center_normal_z = abs(norm.z)
                            break
                        else:
                            current_origin = loc + dir_world * 0.01
                    else:
                        break

            if len(hit_zs) < 3:
                continue

            min_z = min(hit_zs)
            max_z = max(hit_zs)
            hit_z = max_z

            # 急斜面（slope >= 18度）の区画には建物を配置しない
            normal_slope_deg = math.degrees(math.acos(max(0.0, min(1.0, center_normal_z))))
            geom_slope_deg = math.degrees(math.atan2(max_z - min_z, max(1.0, math.hypot(w, h))))
            if normal_slope_deg >= 18.0 or geom_slope_deg >= 18.0:
                continue

            # 建物のキューブを作成（基礎を最下点より深く埋め込み、屋根基準を最高点に合わせる）
            z_min = min_z - 10.0
            z_max = max_z + z_height

            # 立地（標高・位置）に基づくバイオームマテリアルインデックスの決定
            mat_idx = 0
            if is_multi:
                if hit_z >= 80.0:
                    mat_idx = 2 # SNOW
                else:
                    pos_val = math.sin(x * 0.00025) * math.cos(y * 0.00025)
                    if pos_val > 0.1:
                        mat_idx = 1 # DESERT
                    elif pos_val < -0.35:
                        mat_idx = 3 # CANYON
                    else:
                        mat_idx = 0 # PLAINS
            
            # 高層摩天楼（高さ75m以上）の場合は上部セットバック（段差タワー）を造形
            if z_height >= 75.0 and b_type == 'SKYSCRAPER':
                base_z = hit_z + z_height * 0.58
                self._add_cube_to_bmesh(bm, x, y, hw, hh, z_min, base_z, angle=angle, mat_index=mat_idx)
                
                # 上層タワー（60%幅）
                tower_hw = hw * 0.62
                tower_hh = hh * 0.62
                self._add_cube_to_bmesh(bm, x, y, tower_hw, tower_hh, base_z, z_max, angle=angle, mat_index=mat_idx)
                
                # 屋上尖塔・アンテナ
                if random.random() < 0.6:
                    spire_z = z_max + random.uniform(15.0, 35.0)
                    self._add_cube_to_bmesh(bm, x, y, 2.5, 2.5, z_max, spire_z, angle=angle, mat_index=mat_idx)
            else:
                self._add_cube_to_bmesh(bm, x, y, hw, hh, z_min, z_max, angle=angle, mat_index=mat_idx)
            
        bm.to_mesh(mesh)
        bm.free()
    def _subdivide_spline(self, pts, max_seg_len=75.0):
        """長すぎる直線セグメントを均等に細分化し、地面への吸着精度を向上させる"""
        import math
        if len(pts) < 2:
            return pts
        new_pts = [pts[0]]
        for i in range(len(pts) - 1):
            p1 = pts[i]
            p2 = pts[i+1]
            dx = p2[0] - p1[0]
            dy = p2[1] - p1[1]
            dist = math.sqrt(dx * dx + dy * dy)
            if dist > max_seg_len:
                num_sub = int(math.ceil(dist / max_seg_len))
                for k in range(1, num_sub):
                    t = k / num_sub
                    nx = p1[0] + dx * t
                    ny = p1[1] + dy * t
                    new_pts.append([nx, ny, 0.0])
            new_pts.append(p2)
        return new_pts

    def spawn_bridge_structures(self, context, piers_data, guardrails_data):
        """
        谷を渡る大橋の橋脚（Bridge Piers）および欄干・ガードレール（Guardrails）を3Dメッシュとして生成
        """
        import bmesh
        import bpy
        import math
        
        bridge_col = self.get_or_create_collection(context, "Bridges")
        self.clear_ai_objects(bridge_col)
        
        mesh = bpy.data.meshes.new("Bridges_AI")
        obj = bpy.data.objects.new("Bridges_AI", mesh)
        bridge_col.objects.link(obj)
        
        bm = bmesh.new()
        
        # 1. コンクリート橋脚（Bridge Piers）の生成
        for px, py, dz, gz, hw in piers_data:
            pier_w = 7.5
            pier_d = 7.5
            z_min = gz - 6.0 # 谷底の地面に確実に埋め込む
            z_max = dz - 0.2 # 道路デッキの下面に合わせる
            if z_max > z_min:
                self._add_cube_to_bmesh(bm, px, py, pier_w / 2.0, pier_d / 2.0, z_min, z_max, angle=0.0)

        # 2. ガードレール・防護壁（Guardrails）の生成
        for p1, p2, half_w in guardrails_data:
            x1, y1, z1 = p1
            x2, y2, z2 = p2
            dx = x2 - x1
            dy = y2 - y1
            seg_len = math.sqrt(dx * dx + dy * dy)
            if seg_len < 1.0:
                continue
            norm_x = -dy / seg_len
            norm_y =  dx / seg_len
            rail_angle = math.atan2(dy, dx)
            
            mid_x = (x1 + x2) / 2.0
            mid_y = (y1 + y2) / 2.0
            mid_z = (z1 + z2) / 2.0
            
            rail_h = 1.3
            rail_th = 0.35
            
            # 左側ガードレール
            lx = mid_x + norm_x * (half_w + 0.3)
            ly = mid_y + norm_y * (half_w + 0.3)
            self._add_cube_to_bmesh(bm, lx, ly, seg_len / 2.0, rail_th / 2.0, mid_z, mid_z + rail_h, angle=rail_angle)
            
            # 右側ガードレール
            rx = mid_x - norm_x * (half_w + 0.3)
            ry = mid_y - norm_y * (half_w + 0.3)
            self._add_cube_to_bmesh(bm, rx, ry, seg_len / 2.0, rail_th / 2.0, mid_z, mid_z + rail_h, angle=rail_angle)

        bm.to_mesh(mesh)
        bm.free()

        # コンクリートマテリアルの適用
        mat_name = "Material_Bridge_Concrete"
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(mat_name)
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                bsdf.inputs["Base Color"].default_value = (0.72, 0.73, 0.75, 1.0)
                bsdf.inputs["Roughness"].default_value = 0.7
                mat.diffuse_color = (0.72, 0.73, 0.75, 1.0)
        obj.data.materials.append(mat)

    def project_road_to_terrain(
        self,
        context,
        road_obj,
        terrain_obj,
        water_level=None,
        valley_radius=1500.0,
        mountain_radius=1400.0,
        has_tunnels=False,
    ):
        """
        道路スプラインを地形に投影。
        - レイキャストは z=5000.0 (distance=10000.0) から行い、ミス点は前後から線形補間。
        - トンネル区間 (tunnel_spans) は以下の3条件をすべて満たす区間のみに厳格制限:
            1. Mountains コレクション内の山脈スプラインから Mountain Radius * 0.85 以内
            2. 隆起後の地表標高 ground_z がその道路の平地基準標高より +80.0m 以上高い
            3. 条件1・2を満たす連続区間長が 250.0m 以上ある
        - 上記を満たさない平地・丘陵では道路Z座標を絶対に地面の下へ潜らせない (必ず ground_z + 1.2m 以上)。
        - トンネル区間およびその前後 100m 以内では橋梁 (bridge_spans / 橋脚生成) を排他制御で禁止。
        - 地上道路は RoadPath_AI に残し、トンネル区間道路は別オブジェクト RoadPath_Tunnel_AI に分離して
          トンネル真上の山脈が Road Object 平坦化で削り取られるバグを完全に防止する。
        """
        import mathutils
        import math
        try:
            from .gn_utils import get_modifier_input
        except ImportError:
            from gn_utils import get_modifier_input

        context.view_layer.update()
        depsgraph = context.evaluated_depsgraph_get()
        
        road_mat_inv = road_obj.matrix_world.inverted()
        road_curve = road_obj.data

        # Valleys コレクションから谷セグメントを抽出（ワールドXY）
        valley_segs = []
        val_col = bpy.data.collections.get("Valleys")
        if val_col:
            for v_obj in val_col.objects:
                if v_obj.type != 'CURVE' or not v_obj.data:
                    continue
                for v_sp in v_obj.data.splines:
                    v_pts = v_sp.bezier_points if v_sp.type == 'BEZIER' else v_sp.points
                    if len(v_pts) < 2:
                        continue
                    w_pts = []
                    for vp in v_pts:
                        co_v = vp.co[:3] if v_sp.type == 'POLY' else vp.co
                        wp = v_obj.matrix_world @ mathutils.Vector(co_v)
                        w_pts.append((wp.x, wp.y))
                    for j in range(len(w_pts) - 1):
                        valley_segs.append((w_pts[j][0], w_pts[j][1], w_pts[j + 1][0], w_pts[j + 1][1]))

        # Mountains コレクションから山脈セグメントを抽出（ワールドXY + 制御点radius）
        mountain_segs = []
        mt_col = bpy.data.collections.get("Mountains")
        if mt_col:
            for m_obj in mt_col.objects:
                if m_obj.type != 'CURVE' or not m_obj.data:
                    continue
                for m_sp in m_obj.data.splines:
                    m_pts = m_sp.bezier_points if m_sp.type == 'BEZIER' else m_sp.points
                    if len(m_pts) < 2:
                        continue
                    w_pts = []
                    for mp in m_pts:
                        co_m = mp.co[:3] if m_sp.type == 'POLY' else mp.co
                        wp = m_obj.matrix_world @ mathutils.Vector(co_m)
                        r_m = max(0.6, min(1.8, float(getattr(mp, "radius", 1.0))))
                        w_pts.append((wp.x, wp.y, r_m))
                    for j in range(len(w_pts) - 1):
                        mountain_segs.append((
                            w_pts[j][0], w_pts[j][1], w_pts[j][2],
                            w_pts[j + 1][0], w_pts[j + 1][1], w_pts[j + 1][2],
                        ))

        water_obj = bpy.data.objects.get("WaterPlane_AI")
        valley_check_radius = float(valley_radius) * 0.85
        mt_base_radius = max(200.0, float(mountain_radius))

        def _dist_to_valley(wx, wy):
            best_d_sq = 1e36
            for x1, y1, x2, y2 in valley_segs:
                dx = x2 - x1
                dy = y2 - y1
                len_sq = dx * dx + dy * dy
                if len_sq < 1e-6:
                    d_sq = (wx - x1) ** 2 + (wy - y1) ** 2
                else:
                    t = max(0.0, min(1.0, ((wx - x1) * dx + (wy - y1) * dy) / len_sq))
                    px = x1 + t * dx
                    py = y1 + t * dy
                    d_sq = (wx - px) ** 2 + (wy - py) ** 2
                if d_sq < best_d_sq:
                    best_d_sq = d_sq
            return math.sqrt(best_d_sq)

        def _is_within_mountain_85(wx, wy):
            if not mountain_segs:
                return False
            for x1, y1, r1, x2, y2, r2 in mountain_segs:
                dx = x2 - x1
                dy = y2 - y1
                len_sq = dx * dx + dy * dy
                if len_sq < 1e-6:
                    t = 0.0
                    px, py = x1, y1
                else:
                    t = max(0.0, min(1.0, ((wx - x1) * dx + (wy - y1) * dy) / len_sq))
                    px = x1 + t * dx
                    py = y1 + t * dy
                d = math.hypot(wx - px, wy - py)
                eff_r = mt_base_radius * (r1 + (r2 - r1) * t)
                if d <= max(mt_base_radius * 0.85, eff_r * 0.85):
                    return True
            return False

        bridge_piers_data = []
        guardrails_data = []
        tunnels_data = []
        surface_splines_spec = []
        tunnel_splines_spec = []

        # 地形サイズを取得して探索窓スケールを決定
        size_ref = 20000.0
        if terrain_obj and terrain_obj.modifiers.get("TerrainGen"):
            val = get_modifier_input(terrain_obj.modifiers.get("TerrainGen"), 'Grid Size X')
            if val:
                try:
                    size_ref = float(val)
                except Exception:
                    pass
        max_half_span = 2800.0 * (size_ref / 20000.0)

        for spline in list(road_curve.splines):
            points = spline.bezier_points if spline.type == 'BEZIER' else spline.points
            n_pts = len(points)
            if n_pts < 2:
                continue

            is_cyclic = bool(spline.use_cyclic_u)
            is_main = (spline.points[0].radius >= 0.8) if (spline.type == 'POLY' and len(spline.points) > 0) else True
            pt_rad = 1.0 if is_main else 0.5

            # 1. 各点の地面標高 (raw_ground_z) を z=5000.0 / distance=10000.0 でレイキャスト取得
            raw_ground_z = [0.0] * n_pts
            hit_valid = [False] * n_pts
            coords_local = []
            coords_world_xy = []
            for idx_pt, pt in enumerate(points):
                co = pt.co[:3] if spline.type == 'POLY' else pt.co
                coords_local.append((float(co[0]), float(co[1]), float(co[2])))
                co_world = road_obj.matrix_world @ mathutils.Vector(co)
                coords_world_xy.append((co_world.x, co_world.y))
                
                origin_world = mathutils.Vector((co_world.x, co_world.y, 5000.0))
                dir_world = mathutils.Vector((0.0, 0.0, -1.0))
                
                current_origin = origin_world
                for _ in range(10):
                    success, location, normal, index, obj, matrix = context.scene.ray_cast(
                        depsgraph, current_origin, dir_world, distance=10000.0
                    )
                    if success:
                        if obj and obj.name == terrain_obj.name:
                            hit_local = road_mat_inv @ location
                            raw_ground_z[idx_pt] = hit_local.z
                            hit_valid[idx_pt] = True
                            break
                        else:
                            current_origin = location + dir_world * 0.01
                    else:
                        break

            # ミス点の線形補間フォールバック（0.0 への垂直落ちを防止）
            valid_indices = [idx for idx, ok in enumerate(hit_valid) if ok]
            if valid_indices:
                first_v = valid_indices[0]
                for idx in range(0, first_v):
                    raw_ground_z[idx] = raw_ground_z[first_v]
                last_v = valid_indices[-1]
                for idx in range(last_v + 1, n_pts):
                    raw_ground_z[idx] = raw_ground_z[last_v]
                for k_v in range(len(valid_indices) - 1):
                    i_a = valid_indices[k_v]
                    i_b = valid_indices[k_v + 1]
                    if i_b - i_a > 1:
                        za, zb = raw_ground_z[i_a], raw_ground_z[i_b]
                        for m in range(i_a + 1, i_b):
                            t_m = (m - i_a) / float(i_b - i_a)
                            raw_ground_z[m] = za + (zb - za) * t_m

            # 2. スプライン沿いの累積距離および理想縦断高度ライン (ideal_grade_z: 移動平均窓幅600m) を算出
            cum_dist = [0.0] * n_pts
            for i in range(1, n_pts):
                dx = coords_local[i][0] - coords_local[i - 1][0]
                dy = coords_local[i][1] - coords_local[i - 1][1]
                cum_dist[i] = cum_dist[i - 1] + math.hypot(dx, dy)

            ideal_grade_z = [0.0] * n_pts
            local_base_z = [0.0] * n_pts
            for i in range(n_pts):
                w0 = max(0, i - 20)
                w1 = min(n_pts - 1, i + 20)
                ideal_grade_z[i] = sum(raw_ground_z[k] for k in range(w0, w1 + 1)) / float(w1 - w0 + 1)

                lb0 = max(0, i - 60)
                lb1 = min(n_pts - 1, i + 60)
                win_sorted = sorted(raw_ground_z[lb0 : lb1 + 1])
                local_base_z[i] = win_sorted[min(len(win_sorted) - 1, int(len(win_sorted) * 0.20))]

            # 2.5. 山岳トンネル区間 (tunnel_spans) の検出（人間らしい土木基準）
            # 地表標高 raw_ground_z が前後の山麓・平地基準ラインより +45.0m 以上高く隆起し、
            # 長さ 180.0m 以上連続する山岳横断区間をトンネルとする
            in_mt_85 = [_is_within_mountain_85(wx, wy) for wx, wy in coords_world_xy]
            plain_samples = [raw_ground_z[i] for i in range(n_pts) if not in_mt_85[i]]
            if plain_samples:
                sorted_plain = sorted(plain_samples)
                base_plain_z = sorted_plain[min(len(sorted_plain) - 1, int(len(sorted_plain) * 0.35))]
            else:
                base_plain_z = min(raw_ground_z) if raw_ground_z else 0.0

            is_high_mt_pt = [
                (
                    in_mt_85[i]
                    and (
                        raw_ground_z[i] >= base_plain_z + 45.0
                        or raw_ground_z[i] >= local_base_z[i] + 45.0
                    )
                )
                for i in range(n_pts)
            ]

            tunnel_spans = []
            if (is_main or has_tunnels) and mountain_segs and not is_cyclic:
                raw_mt_runs = []
                run_s = None
                for i in range(n_pts):
                    if is_high_mt_pt[i]:
                        if run_s is None:
                            run_s = i
                    else:
                        if run_s is not None:
                            run_e = i - 1
                            if (cum_dist[run_e] - cum_dist[run_s]) >= 180.0:
                                raw_mt_runs.append((run_s, run_e))
                            run_s = None
                if run_s is not None:
                    run_e = n_pts - 1
                    if (cum_dist[run_e] - cum_dist[run_s]) >= 180.0:
                        raw_mt_runs.append((run_s, run_e))

                for r_s, r_e in raw_mt_runs:
                    # 坑口位置を山麓側 (Mountain Radius * 0.85 内かつ平地基準 +12m 以上) へ自然に広げる
                    s_idx = r_s
                    while s_idx > 1 and in_mt_85[s_idx - 1] and raw_ground_z[s_idx - 1] >= (base_plain_z + 12.0) and raw_ground_z[s_idx - 1] <= raw_ground_z[s_idx] + 1.5:
                        s_idx -= 1
                    e_idx = r_e
                    while e_idx < n_pts - 2 and in_mt_85[e_idx + 1] and raw_ground_z[e_idx + 1] >= (base_plain_z + 12.0) and raw_ground_z[e_idx + 1] <= raw_ground_z[e_idx] + 1.5:
                        e_idx += 1

                    # 内部点がトンネル路面より確実な土被り (>= 4.0m) を持つように坑口端を微調整
                    while s_idx < r_s:
                        span_l = max(1.0, cum_dist[e_idx] - cum_dist[s_idx])
                        zs_cand = raw_ground_z[s_idx] + 1.8
                        ze_cand = raw_ground_z[e_idx] + 1.8
                        if raw_ground_z[s_idx + 1] - (zs_cand + (ze_cand - zs_cand) * ((cum_dist[s_idx + 1] - cum_dist[s_idx]) / span_l)) < 4.0:
                            s_idx += 1
                        else:
                            break
                    while e_idx > r_e:
                        span_l = max(1.0, cum_dist[e_idx] - cum_dist[s_idx])
                        zs_cand = raw_ground_z[s_idx] + 1.8
                        ze_cand = raw_ground_z[e_idx] + 1.8
                        if raw_ground_z[e_idx - 1] - (zs_cand + (ze_cand - zs_cand) * ((cum_dist[e_idx - 1] - cum_dist[s_idx]) / span_l)) < 4.0:
                            e_idx -= 1
                        else:
                            break

                    if (cum_dist[e_idx] - cum_dist[s_idx]) >= 180.0 and (e_idx - s_idx) >= 4:
                        if tunnel_spans and s_idx <= tunnel_spans[-1][1] + 4:
                            tunnel_spans[-1] = (tunnel_spans[-1][0], max(tunnel_spans[-1][1], e_idx))
                        else:
                            tunnel_spans.append((s_idx, e_idx))

            # トンネル区間およびその前後 100m 以内では橋梁判定を排他制御で完全禁止
            tunnel_exclusion = [False] * n_pts
            for ts, te in tunnel_spans:
                d_min = cum_dist[ts] - 100.0
                d_max = cum_dist[te] + 100.0
                for i in range(n_pts):
                    if d_min <= cum_dist[i] <= d_max:
                        tunnel_exclusion[i] = True

            # 2.8. 橋梁区間 (bridge_spans) の検出（人間らしい土木基準）:
            # 条件①: Valleys コレクションの谷 (valley_radius * 0.85 以内) を横断し、深さ 22.0m 以上落ち込んでいる区間
            # 条件②: 山裾・丘陵の沢や凹地で raw_ground_z が理想高度ライン ideal_grade_z より 18.0m 以上低く落ち込んでいる区間 (長さ 90.0m 以上)
            candidate_bridges = []
            if not is_cyclic:
                # 条件①: Valleys 谷スプライン横断区間
                if valley_segs:
                    in_valley_check = [False] * n_pts
                    for i in range(n_pts):
                        if tunnel_exclusion[i]:
                            continue
                        wx, wy = coords_world_xy[i]
                        if _dist_to_valley(wx, wy) <= valley_check_radius:
                            in_valley_check[i] = True

                    valley_runs = []
                    v_start = None
                    for i in range(n_pts):
                        if in_valley_check[i]:
                            if v_start is None:
                                v_start = i
                        else:
                            if v_start is not None:
                                valley_runs.append((v_start, i - 1))
                                v_start = None
                    if v_start is not None:
                        valley_runs.append((v_start, n_pts - 1))

                    for v_s, v_e in valley_runs:
                        if v_s <= 0 or v_e >= n_pts - 1:
                            continue
                        bank_l_idx = max(0, v_s - 1)
                        bank_r_idx = min(n_pts - 1, v_e + 1)
                        if tunnel_exclusion[bank_l_idx] or tunnel_exclusion[bank_r_idx]:
                            continue
                        both_banks_z = min(raw_ground_z[bank_l_idx], raw_ground_z[bank_r_idx])
                        valley_bottom_z = min(raw_ground_z[k] for k in range(v_s, v_e + 1))
                        if (both_banks_z - valley_bottom_z) >= 22.0 and (cum_dist[bank_r_idx] - cum_dist[bank_l_idx]) >= 60.0:
                            candidate_bridges.append((bank_l_idx, bank_r_idx))

                # 条件②: 理想高度ライン (ideal_grade_z) より 18.0m 以上低い沢・凹地横断区間
                in_depr = [
                    (not tunnel_exclusion[i]) and (raw_ground_z[i] <= ideal_grade_z[i] - 18.0)
                    for i in range(n_pts)
                ]
                depr_runs = []
                d_start = None
                for i in range(n_pts):
                    if in_depr[i]:
                        if d_start is None:
                            d_start = i
                    else:
                        if d_start is not None:
                            depr_runs.append((d_start, i - 1))
                            d_start = None
                if d_start is not None:
                    depr_runs.append((d_start, n_pts - 1))

                for r_s, r_e in depr_runs:
                    if r_s <= 0 or r_e >= n_pts - 1:
                        continue
                    bank_l_idx = max(0, r_s - 1)
                    bank_r_idx = min(n_pts - 1, r_e + 1)
                    if tunnel_exclusion[bank_l_idx] or tunnel_exclusion[bank_r_idx]:
                        continue
                    max_drop = max(ideal_grade_z[k] - raw_ground_z[k] for k in range(r_s, r_e + 1))
                    if max_drop >= 18.0 and (cum_dist[bank_r_idx] - cum_dist[bank_l_idx]) >= 90.0:
                        candidate_bridges.append((bank_l_idx, bank_r_idx))

            bridge_spans = []
            for b_s, b_e in sorted(candidate_bridges, key=lambda x: (x[0], x[1])):
                if bridge_spans and b_s <= bridge_spans[-1][1] + 1:
                    bridge_spans[-1] = (bridge_spans[-1][0], max(bridge_spans[-1][1], b_e))
                else:
                    bridge_spans.append((b_s, b_e))

            # 3. 橋梁・トンネル・地上通常区間のZ座標を計算
            # 地上区間では路面が斜面に食い込まないよう +1.8m オフセットで確実に接地させる
            target_z_list = [raw_ground_z[i] + 1.8 for i in range(n_pts)]
            is_tunnel_interior = [False] * n_pts

            for s_idx, e_idx in bridge_spans:
                z_start = raw_ground_z[s_idx] + 1.8
                z_end = raw_ground_z[e_idx] + 1.8
                span_total = max(1.0, cum_dist[e_idx] - cum_dist[s_idx])
                for k in range(s_idx, e_idx + 1):
                    t_k = (cum_dist[k] - cum_dist[s_idx]) / span_total
                    deck_z = z_start + (z_end - z_start) * t_k
                    target_z_list[k] = max(deck_z, raw_ground_z[k] + 1.8)

            for s_idx, e_idx in tunnel_spans:
                z_start = raw_ground_z[s_idx] + 1.8
                z_end = raw_ground_z[e_idx] + 1.8
                span_total = max(1.0, cum_dist[e_idx] - cum_dist[s_idx])
                tun_pts_w = []
                for k in range(s_idx, e_idx + 1):
                    t_k = (cum_dist[k] - cum_dist[s_idx]) / span_total
                    tun_z = z_start + (z_end - z_start) * t_k
                    if s_idx < k < e_idx:
                        # トンネル内部のみ地下高度を許容、入口・出口端点は地上道路 (raw_ground_z + 1.8m) と完全一致
                        tun_z = min(tun_z, raw_ground_z[k] - 4.0)
                        is_tunnel_interior[k] = True
                    target_z_list[k] = tun_z
                    co_l = coords_local[k]
                    wp = road_obj.matrix_world @ mathutils.Vector((co_l[0], co_l[1], tun_z))
                    gp = road_obj.matrix_world @ mathutils.Vector((co_l[0], co_l[1], raw_ground_z[k]))
                    tun_pts_w.append((wp.x, wp.y, wp.z, gp.z))
                tunnels_data.append((tun_pts_w, 12.0 if is_main else 6.0))

            # 地上区間ではすべての制御点で target_z >= raw_ground_z + 1.8m を保証（路面めり込みを完全防止）
            for i in range(n_pts):
                if not is_tunnel_interior[i] and not any(bs <= i <= be for bs, be in bridge_spans):
                    target_z_list[i] = raw_ground_z[i] + 1.8

            # 4. 道路を「地上区間 (RoadPath_AI)」と「トンネル区間 (RoadPath_Tunnel_AI)」に分離
            pts_3d = [(coords_local[i][0], coords_local[i][1], target_z_list[i]) for i in range(n_pts)]
            if not tunnel_spans:
                surface_splines_spec.append((pts_3d, pt_rad, is_cyclic))
            else:
                curr_s = 0
                for ts, te in tunnel_spans:
                    if ts >= curr_s + 1:
                        surface_splines_spec.append((pts_3d[curr_s : ts + 1], pt_rad, False))
                    tunnel_splines_spec.append((pts_3d[ts : te + 1], pt_rad, False))
                    curr_s = te
                if curr_s < n_pts - 1:
                    surface_splines_spec.append((pts_3d[curr_s:n_pts], pt_rad, False))

            # 5. 橋脚およびガードレールのデータ収集（トンネル前後 100m 排他済み）
            half_w = 12.0 if is_main else 6.0

            for s_idx, e_idx in bridge_spans:
                dist_acc = 0.0
                last_pier_dist = 0.0
                for k in range(s_idx, e_idx):
                    if tunnel_exclusion[k] or tunnel_exclusion[k + 1]:
                        continue
                    p1 = coords_local[k]
                    p2 = coords_local[k + 1]
                    seg_len = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                    dist_acc += seg_len
                    
                    if dist_acc - last_pier_dist >= 95.0:
                        last_pier_dist = dist_acc
                        dz = target_z_list[k]
                        gz = raw_ground_z[k]
                        if (dz - gz) >= 8.0:
                            bridge_piers_data.append((p1[0], p1[1], dz, gz, half_w))

                    z1 = target_z_list[k]
                    z2 = target_z_list[k + 1]
                    guardrails_data.append(((p1[0], p1[1], z1), (p2[0], p2[1], z2), half_w))

        # RoadPath_AI を地上区間のみのスプラインで再構築（トンネル真上の山が Flat Radius で削られるのを完全防止）
        road_curve.splines.clear()
        for s_pts, s_rad, s_cyc in surface_splines_spec:
            if len(s_pts) < 2:
                continue
            sp = road_curve.splines.new('POLY')
            sp.points.add(len(s_pts) - 1)
            sp.use_cyclic_u = s_cyc
            for idx_p, p in enumerate(s_pts):
                sp.points[idx_p].co = (p[0], p[1], p[2], 1.0)
                sp.points[idx_p].radius = s_rad

        # トンネル区間の道路は別オブジェクト RoadPath_Tunnel_AI に分離生成
        road_col = self.get_or_create_collection(context, "Roads")
        old_tun_road = bpy.data.objects.get("RoadPath_Tunnel_AI")
        if old_tun_road:
            old_data = old_tun_road.data
            bpy.data.objects.remove(old_tun_road, do_unlink=True)
            if old_data and old_data.users == 0:
                bpy.data.curves.remove(old_data)

        if tunnel_splines_spec:
            tun_curve = bpy.data.curves.new("RoadPath_Tunnel_AI", 'CURVE')
            tun_curve.dimensions = '3D'
            tun_curve.twist_mode = 'Z_UP'
            tun_curve.bevel_depth = 0.0
            tun_curve.bevel_resolution = 0
            for t_pts, t_rad, t_cyc in tunnel_splines_spec:
                if len(t_pts) < 2:
                    continue
                sp = tun_curve.splines.new('POLY')
                sp.points.add(len(t_pts) - 1)
                sp.use_cyclic_u = t_cyc
                for idx_p, p in enumerate(t_pts):
                    sp.points[idx_p].co = (p[0], p[1], p[2], 1.0)
                    sp.points[idx_p].radius = t_rad
            tun_road_obj = bpy.data.objects.new("RoadPath_Tunnel_AI", tun_curve)
            road_col.objects.link(tun_road_obj)

        # 6. 橋梁構造物のメッシュ生成
        if bridge_piers_data or guardrails_data:
            try:
                self.spawn_bridge_structures(context, bridge_piers_data, guardrails_data)
            except Exception as e:
                print(f"Bridge structure generation failed: {e}")

        # 7. 山岳トンネル構造物（坑口 Delete Geometry 用カッター＋覆工・箱型アーチ坑門）のメッシュ生成
        if tunnels_data:
            try:
                self.spawn_tunnel_structures(context, tunnels_data)
            except Exception as e:
                print(f"Tunnel structure generation failed: {e}")

    def spawn_tunnel_structures(self, context, tunnels_data):
        """
        山岳トンネル区間に対して:
          1. TunnelCutters コレクション (TunnelCutter_AI):
             トンネル突入区間 (0..d_start+2) および脱出区間 (d_end-2..-1) の全アプローチに沿って
             幅44m × 高さ40mの連続スイープカッターメッシュを生成し、create_terrain.py 側で
             Geometry Proximity < 32.0m の地形FACEを確実にくり抜いて坑口を開口する。
          2. Tunnels コレクション (Tunnels_AI):
             削除した穴の縁を外から完全に隠す大型コンクリート坑門 (幅±38m・高さ+32m・奥行45m) を
             土被り 8m〜14m 地点に配置し、tun_pts[0] から tun_pts[-1] まで全区間にわたって
             内壁・外壁アーチチューブを途切れなく貫通生成する。
        """
        import bmesh
        import math

        cutter_col = self.get_or_create_collection(context, "TunnelCutters")
        self.clear_ai_objects(cutter_col)
        tunnel_col = self.get_or_create_collection(context, "Tunnels")
        self.clear_ai_objects(tunnel_col)

        bm_cut = bmesh.new()
        bm_tun = bmesh.new()

        in_hw = 13.0
        in_h = 13.5
        out_hw = 14.2
        out_h = 14.8

        arch_angles = [math.pi * a / 6.0 for a in range(7)]
        inner_prof = [(in_hw, -0.2), (-in_hw, -0.2)]
        outer_prof = [(out_hw, -1.2), (-out_hw, -1.2)]
        for ang_a in reversed(arch_angles):
            inner_prof.append((math.cos(ang_a) * in_hw, 4.0 + math.sin(ang_a) * (in_h - 4.0)))
            outer_prof.append((math.cos(ang_a) * out_hw, 4.0 + math.sin(ang_a) * (out_h - 4.0)))

        def _tangent_xy(pts, idx):
            if idx == 0:
                dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
            elif idx == len(pts) - 1:
                dx, dy = pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1]
            else:
                dx, dy = pts[idx + 1][0] - pts[idx - 1][0], pts[idx + 1][1] - pts[idx - 1][1]
            l_xy = max(1e-4, math.hypot(dx, dy))
            return dx / l_xy, dy / l_xy

        def _add_swept_cutter_span(bm, pts_slice, half_w=22.0, height=40.0, extend_start=0.0, extend_end=0.0):
            """
            坑口前後アプローチ区間に沿って幅 44m (±22m) × 高さ 40m の連続スイープカッターを生成し、
            40km地形グリッドのポリゴンを1枚残らず確実に開口する。
            """
            if not pts_slice or len(pts_slice) < 2:
                return
            work = list(pts_slice)
            if extend_start > 0.0:
                tx0, ty0 = _tangent_xy(work, 0)
                p0 = work[0]
                work.insert(0, (p0[0] - tx0 * extend_start, p0[1] - ty0 * extend_start, p0[2], p0[3]))
            if extend_end > 0.0:
                tx1, ty1 = _tangent_xy(work, len(work) - 1)
                p1 = work[-1]
                work.append((p1[0] + tx1 * extend_end, p1[1] + ty1 * extend_end, p1[2], p1[3]))

            w_steps = (-half_w, -half_w * 0.5, 0.0, half_w * 0.5, half_w)
            rings = []
            for idx, p in enumerate(work):
                tx, ty = _tangent_xy(work, idx)
                rx, ry = ty, -tx
                z_bot = p[2] - 4.0
                z_top = max(p[3] + 6.0, z_bot + height)
                ring = []
                for wy in w_steps:
                    ring.append(bm.verts.new((p[0] + rx * wy, p[1] + ry * wy, z_bot)))
                for wy in reversed(w_steps):
                    ring.append(bm.verts.new((p[0] + rx * wy, p[1] + ry * wy, z_top)))
                rings.append(ring)

            n_r = len(rings[0])
            for idx in range(len(rings) - 1):
                ra, rb = rings[idx], rings[idx + 1]
                for k in range(n_r):
                    k2 = (k + 1) % n_r
                    bm.faces.new((ra[k], ra[k2], rb[k2], rb[k]))

            # 前後端キャップ (bottom i..i+1 と top (9-i-1)..(9-i) を結ぶ)
            r_front = rings[0]
            r_back = rings[-1]
            for i in range(4):
                bm.faces.new((r_front[i], r_front[9 - i], r_front[8 - i], r_front[i + 1]))
                bm.faces.new((r_back[i], r_back[i + 1], r_back[8 - i], r_back[9 - i]))

        def _add_portal_box(bm, px, py, pz, gz, tx, ty):
            """
            削除した地形穴 (半径32m) の縁を外から完全に隠す大型コンクリート坑門 (Portal Box)。
            左右幅 ±38m、高さ +32m、奥行き 45m（山肌へ深くめり込む擁壁ウイング＋アーチ開口部）。
            """
            rx, ry = ty, -tx
            box_hw = 38.0
            box_h = max(32.0, min(gz - pz + 6.0, 38.0))
            box_floor = -4.5
            half_len = 22.5

            # 外周を囲む箱型プロファイル（inner_prof と同じ頂点数 9 で1対1対応させ、前面・背面の額縁壁を貼る）
            box_prof = [
                (box_hw, box_floor),
                (-box_hw, box_floor),
                (-box_hw, 6.0),
                (-box_hw, box_h * 0.68),
                (-box_hw, box_h),
                (0.0, box_h),
                (box_hw, box_h),
                (box_hw, box_h * 0.68),
                (box_hw, 6.0),
            ]

            in_front, in_back = [], []
            out_front, out_back = [], []
            for (ipr, ipz), (opr, opz) in zip(inner_prof, box_prof):
                in_front.append(bm.verts.new((px - tx * half_len + rx * ipr, py - ty * half_len + ry * ipr, pz + ipz)))
                in_back.append(bm.verts.new((px + tx * half_len + rx * ipr, py + ty * half_len + ry * ipr, pz + ipz)))
                out_front.append(bm.verts.new((px - tx * half_len + rx * opr, py - ty * half_len + ry * opr, pz + opz)))
                out_back.append(bm.verts.new((px + tx * half_len + rx * opr, py + ty * half_len + ry * opr, pz + opz)))

            n_p = len(inner_prof)
            for k in range(n_p):
                k2 = (k + 1) % n_p
                # 内向きアーチ内壁・床
                bm.faces.new((in_front[k2], in_front[k], in_back[k], in_back[k2]))
                # 外向き箱型外壁・天端
                bm.faces.new((out_front[k], out_front[k2], out_back[k2], out_back[k]))
                # 前面および背面の坑門額縁壁（床下〜左右翼壁〜アーチ上部）
                bm.faces.new((out_front[k], in_front[k], in_front[k2], out_front[k2]))
                bm.faces.new((in_back[k], out_back[k], out_back[k2], in_back[k2]))

        def _pick_portal_idx(pts, search_indices, fallback_idx):
            best_idx = fallback_idx
            best_score = 1e18
            for idx in search_indices:
                cover = pts[idx][3] - pts[idx][2]
                if 8.0 <= cover <= 14.0:
                    score = abs(cover - 11.0)
                    if score < best_score:
                        best_score = score
                        best_idx = idx
            if best_score < 1e17:
                return best_idx
            for idx in search_indices:
                cover = pts[idx][3] - pts[idx][2]
                if cover >= 4.0:
                    score = abs(cover - 11.0)
                    if score < best_score:
                        best_score = score
                        best_idx = idx
            return best_idx

        for tun_pts, _half_w in tunnels_data:
            if len(tun_pts) < 2:
                continue

            deep_indices = [
                idx for idx, p in enumerate(tun_pts)
                if (p[2] + out_h) <= (p[3] - 3.0)
            ]
            if len(deep_indices) < 2:
                deep_indices = [
                    idx for idx, p in enumerate(tun_pts)
                    if (p[3] - p[2]) >= 8.0
                ]
            if len(deep_indices) < 2:
                continue

            d_start = deep_indices[0]
            d_end = deep_indices[-1]
            if d_end - d_start < 1:
                continue

            # 1. 入口 (0 .. d_start+2) および出口 (d_end-2 .. -1) の突入区間全体を覆う連続スイープカッターを生成
            enter_cut_end = min(len(tun_pts), d_start + 3)
            _add_swept_cutter_span(
                bm_cut,
                tun_pts[0:enter_cut_end],
                half_w=22.0,
                height=40.0,
                extend_start=15.0,
                extend_end=0.0,
            )

            exit_cut_start = max(0, d_end - 2)
            _add_swept_cutter_span(
                bm_cut,
                tun_pts[exit_cut_start:len(tun_pts)],
                half_w=22.0,
                height=40.0,
                extend_start=0.0,
                extend_end=15.0,
            )

            # 2. 土被り 8m〜14m 地点に大型コンクリート坑門 (Portal Box) を配置
            p_in_idx = _pick_portal_idx(tun_pts, range(0, min(len(tun_pts), d_start + 3)), d_start)
            p_enter = tun_pts[p_in_idx]
            tx_s, ty_s = _tangent_xy(tun_pts, p_in_idx)
            _add_portal_box(bm_tun, p_enter[0], p_enter[1], p_enter[2], p_enter[3], tx_s, ty_s)

            p_out_idx = _pick_portal_idx(tun_pts, range(max(0, d_end - 2), len(tun_pts)), d_end)
            p_exit = tun_pts[p_out_idx]
            tx_e, ty_e = _tangent_xy(tun_pts, p_out_idx)
            _add_portal_box(bm_tun, p_exit[0], p_exit[1], p_exit[2], p_exit[3], tx_e, ty_e)

            # 3. tun_pts[0] から tun_pts[-1] まで全区間にわたって内壁・外壁アーチチューブを途切れなく貫通生成
            rings_in = []
            rings_out = []
            for idx, p in enumerate(tun_pts):
                tx, ty = _tangent_xy(tun_pts, idx)
                rx, ry = ty, -tx
                rings_in.append([
                    bm_tun.verts.new((p[0] + rx * pr, p[1] + ry * pr, p[2] + pz))
                    for pr, pz in inner_prof
                ])
                rings_out.append([
                    bm_tun.verts.new((p[0] + rx * pr, p[1] + ry * pr, p[2] + pz))
                    for pr, pz in outer_prof
                ])

            n_tun = len(inner_prof)
            for idx in range(len(tun_pts) - 1):
                ia, ib = rings_in[idx], rings_in[idx + 1]
                oa, ob = rings_out[idx], rings_out[idx + 1]
                for k in range(n_tun):
                    k2 = (k + 1) % n_tun
                    bm_tun.faces.new((ia[k2], ia[k], ib[k], ib[k2]))
                    bm_tun.faces.new((oa[k], oa[k2], ob[k2], ob[k]))
            # 始端・終端の内壁と外壁の厚み縁をキャップ
            for k in range(n_tun):
                k2 = (k + 1) % n_tun
                bm_tun.faces.new((rings_out[0][k], rings_in[0][k], rings_in[0][k2], rings_out[0][k2]))
                bm_tun.faces.new((rings_in[-1][k], rings_out[-1][k], rings_out[-1][k2], rings_in[-1][k2]))

        if len(bm_cut.faces) > 0:
            bmesh.ops.recalc_face_normals(bm_cut, faces=bm_cut.faces)
            mesh_cut = bpy.data.meshes.new("TunnelCutter_AI")
            bm_cut.to_mesh(mesh_cut)
            obj_cut = bpy.data.objects.new("TunnelCutter_AI", mesh_cut)
            cutter_col.objects.link(obj_cut)
            obj_cut.hide_viewport = True
            obj_cut.hide_render = True
        bm_cut.free()

        if len(bm_tun.faces) > 0:
            mesh_tun = bpy.data.meshes.new("Tunnels_AI")
            bm_tun.to_mesh(mesh_tun)
            obj_tun = bpy.data.objects.new("Tunnels_AI", mesh_tun)
            tunnel_col.objects.link(obj_tun)

            mat_tun = bpy.data.materials.get("Concrete_Tunnel_AI")
            if not mat_tun:
                mat_tun = bpy.data.materials.new("Concrete_Tunnel_AI")
                mat_tun.use_nodes = True
                bsdf = mat_tun.node_tree.nodes.get("Principled BSDF")
                if bsdf:
                    bsdf.inputs["Base Color"].default_value = (0.24, 0.25, 0.27, 1.0)
                    bsdf.inputs["Roughness"].default_value = 0.85
                mat_tun.diffuse_color = (0.24, 0.25, 0.27, 1.0)
            obj_tun.data.materials.append(mat_tun)
        bm_tun.free()

    def run_gemini_request(self, model_name, api_key, prompt, preset='AUTO', terrain_scale='40KM', current_blueprint=None):
        is_40km = (terrain_scale == '40KM')
        scale_str = "40km四方 (40,000m × 40,000m)" if is_40km else "20km四方 (20,000m × 20,000m)"

        preset_hint = ""
        if preset == 'FLAT':
            preset_hint = "\n【ユーザー指定: 平野/街プリセット】relief_level は 1〜2、都市や平坦地を中心に設計してください。"
        elif preset == 'HILLS':
            preset_hint = "\n【ユーザー指定: 丘陵プリセット】relief_level は 2〜3 程度にしてください。"
        elif preset == 'MOUNTAINS':
            preset_hint = "\n【ユーザー指定: 山岳プリセット】relief_level は 4〜5、ridge_sharpness は 0.65〜0.95 にしてください。"

        if current_blueprint is not None:
            bp_str = json.dumps(current_blueprint, ensure_ascii=False)
            user_content = f"【現在のブループリント】\n{bp_str}\n\n【修正指示】\n{prompt}{preset_hint}"
        else:
            user_content = prompt + preset_hint
        
        if current_blueprint is not None:
            system_instruction = textwrap.dedent(f"""\
                あなたはBlenderの3D地形・都市設計AIアーキテクトです。
                全体サイズは{scale_str}です。
                ユーザーから提示された【現在のブループリント】に対し、【修正指示】を満たすための「差分パッチJSON」のみを出力してください。
                関係ない既存ゾーンは変更しないでください。

                [出力JSON仕様]
                {{
                  "operations": [
                    {{"op": "update_params", "params": {{"relief_level": 4.2, "ridge_sharpness": 0.8}}}},
                    {{"op": "add_zone", "zone": {{"type": "MOUNTAIN_RANGE", "region": "NORTH_EAST", "height_scale": 1.6, "width_scale": 1.2}}}},
                    {{"op": "modify_zone", "match": {{"id": "<既存zoneのid>"}}, "updates": {{"height_scale": 1.8}}}},
                    {{"op": "remove_zone", "match": {{"id": "<既存zoneのid>"}}}}
                  ]
                }}
            """)
        else:
            system_instruction = textwrap.dedent(f"""\
            あなたはBlenderの3D地形・都市設計AIアーキテクトです。
            全体サイズは{scale_str}のオープンワールド規模です。
            生の3D座標配列は出力せず、地形の「意味・構図ベースの設計仕様（ブループリントJSON）」のみを出力してください。
            Python側の空間コンパイラがこのブループリントを曲線スプラインとGeometry Nodesパラメータへ変換します。

            [フィールド仕様]
            - "archetype": 地形の全体構造タイプ
              "BASIN_CITY" (盆地都市), "CANYON_HIGHWAY" (大峡谷ハイウェイ), "ALPINE_VALLEY" (アルプス山岳渓谷),
              "COASTAL_RIDGE" (海岸/平野と山稜), "VOLCANIC_CALDERA" (火山カルデラ), "PLAINS_METROPOLIS" (大平原都市), "PLATEAU_MESA" (台地・メサ)
            - "orientation": 主要軸の向き
              "NORTH_SOUTH", "EAST_WEST", "NW_SE", "NE_SW", "RADIAL"
            - "relief_level": 全体の起伏の強さ (1.0=極平坦 .. 3.0=丘陵 .. 5.0=険峻な山岳)
            - "ridge_sharpness": 尾根の鋭さ・浸食ディテール (0.0=丸い丘 .. 1.0=鋭利な岩稜)
            - "noise_scale_factor": ベースノイズの細かさ倍率 (0.5=大らか .. 1.0=標準 .. 2.0=細かい起伏)
            - "water_level": 水面の標高m (川・海・湖が不要な場合は null、必要な場合は例: -20.0 や 0.0)
            - "zones": 地形を構成する要素のリスト。各要素は以下の形式:
              * 都市: {{"type": "CITY", "region": "<地域>", "scale": 0.6〜8.0（全域都市・すべて街の場合は 8.0, region: "CENTER"）}}
              * 山脈: {{"type": "MOUNTAIN_RANGE", "region": "<地域>", "height_scale": 0.5〜2.2, "width_scale": 0.5〜2.0}}
              * 谷/峡谷: {{"type": "VALLEY", "region": "<地域>", "depth_scale": 0.5〜2.2, "width_scale": 0.5〜2.0}}
              * 川: {{"type": "RIVER", "region": "<地域>", "width_scale": 0.5〜2.5, "depth_scale": 0.5〜2.0}}
              * 海・海岸線: {{"type": "COASTLINE", "region": "NORTH"|"SOUTH"|"EAST"|"WEST", "depth_scale": 0.8〜1.5}}
              <地域>の選択肢: "CENTER", "NORTH", "SOUTH", "EAST", "WEST", "NORTH_EAST", "NORTH_WEST", "SOUTH_EAST", "SOUTH_WEST",
              "PERIMETER", "NORTH_TO_SOUTH", "EAST_TO_WEST", "SOUTH_TO_CENTER", "NORTH_TO_CENTER", "EAST_TO_CENTER", "WEST_TO_CENTER", "NW_TO_SE", "NE_TO_SW"
              ※ ユーザーが街や都市を求めていない純粋な自然地形の場合は CITY ゾーンを入れないでください。
              ※ 逆に「すべて街」「全域が都市」「一面メガシティ」等の場合は archetype を "PLAINS_METROPOLIS", relief_level を 1.0, CITY の scale を 8.0 とし、MOUNTAIN_RANGE や VALLEY ゾーンは出力しないでください。
              ※ 「東西に街」など複数拠点が指定された場合は CITY ゾーンを複数（例: region: "EAST" と "WEST"）出力し orientation を "EAST_WEST" にしてください。
            - "road_topology": 道路ネットワークのトポロジ
              "RING_AND_SPOKE" (環状＋放射道路), "CROSS_VALLEY" (谷越え橋梁幹線), "COASTAL_CORRIDOR" (沿線回廊),
              "MOUNTAIN_PASS" (山岳峠道), "TUNNEL_HIGHWAY" (山岳貫通トンネル幹線), "GRID_ORGANIC" (有機的都市街路), "HIGHWAY_SPINE" (貫通高速道路)
            - "has_tunnels": true/false (山脈分断やトンネル・地下道が求められる場合は true)

            [出力JSON例]
            {{
              "archetype": "BASIN_CITY",
              "orientation": "NORTH_SOUTH",
              "relief_level": 4,
              "ridge_sharpness": 0.75,
              "noise_scale_factor": 1.0,
              "water_level": null,
              "zones": [
                {{"type": "CITY", "region": "CENTER", "scale": 1.2}},
                {{"type": "MOUNTAIN_RANGE", "region": "NORTH", "height_scale": 1.6, "width_scale": 1.2}},
                {{"type": "VALLEY", "region": "SOUTH_TO_CENTER", "depth_scale": 1.3, "width_scale": 0.8}}
              ],
              "road_topology": "RING_AND_SPOKE"
            }}
        """)

        payload = {
            "system_instruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [
                {
                    "parts": [{"text": user_content}]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.4
            }
        }

        # 安定稼働モデルのスマートフォールバックチェーン（503や429が発生しても自動で別の安定モデルを試行）
        fallback_pool = ['gemini-3.5-flash', 'gemini-3-flash-preview', 'gemini-2.5-flash', 'gemini-3.1-flash-lite-preview']
        candidates_to_try = [model_name]
        for fb in fallback_pool:
            if fb not in candidates_to_try:
                candidates_to_try.append(fb)

        import time

        for current_model in candidates_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{current_model}:generateContent?key={api_key}"
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )

            try:
                print(f"--- Gemini API ({current_model}) にリクエスト送信中 ---")
                with urllib.request.urlopen(req, timeout=60.0) as response:
                    resp_json = json.loads(response.read().decode('utf-8'))
                    
                    candidates = resp_json.get('candidates', [])
                    if not candidates:
                        self._error = "Geminiからの応答が空でした。"
                        return
                        
                    text_part = candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                    print(f"\n--- Gemini応答受信完了 ({current_model}) ---\n{text_part}")
                    
                    self._result = json.loads(text_part)
                    if not self._result:
                        self._error = "Geminiが空のデータを返しました。"
                    else:
                        self._error = None
                        return
                        
            except urllib.error.HTTPError as e:
                err_body = e.read().decode('utf-8', errors='ignore')
                print(f"\nGemini HTTPエラー ({current_model}): {e.code} {err_body}")
                # 404, 503 (一時障害/High Demand), 429 (一時レート制限) でフォールバック候補がある場合は自動再試行
                if current_model != candidates_to_try[-1] and e.code in (404, 429, 503):
                    next_model = candidates_to_try[candidates_to_try.index(current_model) + 1]
                    print(f"モデル '{current_model}' (HTTP {e.code}: サーバー混雑または制限) のため、安定モデル '{next_model}' で自動再試行します...")
                    time.sleep(1.2) # 短時間待機して過負荷を回避
                    continue

                if e.code == 503:
                    self._error = "Geminiサーバー混雑(503): Google側で高負荷が発生しています。約1分後に再試行するか、'Gemini 3.5 Flash' を選択してください。"
                elif e.code == 429:
                    self._error = "Gemini利用枠一時制限(429): 短時間でのリクエスト過多です。約1分間待ってから再度お試しください。"
                elif e.code == 404:
                    self._error = f"Geminiモデルが見つかりません(404: {current_model})。'Gemini 3.5 Flash' を選択してください。"
                elif e.code == 400:
                    self._error = "Geminiリクエストエラー(400): APIキーまたはモデル設定が無効です。"
                elif e.code == 403:
                    self._error = "Gemini認証エラー(403): APIキーが無効か権限がありません。"
                else:
                    self._error = f"Gemini通信エラー ({e.code}): {e.reason}"
                return
            except (urllib.error.URLError, TimeoutError) as e:
                print(f"\nGemini 接続/タイムアウトエラー ({current_model}): {e}")
                if current_model != candidates_to_try[-1]:
                    next_model = candidates_to_try[candidates_to_try.index(current_model) + 1]
                    print(f"モデル '{current_model}' でタイムアウトしたため、別モデル '{next_model}' で再試行します...")
                    time.sleep(1.0)
                    continue
                self._error = f"ネットワーク接続/タイムアウトエラー: {e}"
                return
            except json.JSONDecodeError as e:
                self._error = f"Geminiの応答をJSONとして解析できませんでした: {e}"
                return
            except Exception as e:
                self._error = f"エラーが発生しました: {e}"
                return

    def run_ollama_request(self, model_name, prompt, preset='AUTO', terrain_scale='40KM', current_blueprint=None):
        is_40km = (terrain_scale == '40KM')
        scale_str = "40km x 40km (40,000m x 40,000m)" if is_40km else "20km x 20km (20,000m x 20,000m)"
        coord_min = -20000 if is_40km else -10000
        coord_max = 20000 if is_40km else 10000
        size_val = 40000.0 if is_40km else 20000.0
        r_step = 2.0 if is_40km else 1.0

        url = "http://localhost:11434/api/generate"
        
        # --- 自動翻訳処理 ---
        print("--- 日本語プロンプトを英語に翻訳中 ---")
        trans_data = {
            "model": model_name,
            "prompt": (
                "Translate the following Japanese text describing a 3D terrain into English. "
                "Important: translate words like '平面' or '平地' or '平原' as 'flat land' or 'flat plains' (NOT airplane, NOT mathematical flat plane). "
                f"Output ONLY the English translation, no quotes, no explanations:\n{prompt}"
            ),
            "stream": False
        }
        try:
            req_trans = urllib.request.Request(url, data=json.dumps(trans_data).encode('utf-8'), method='POST')
            req_trans.add_header('Content-Type', 'application/json')
            with urllib.request.urlopen(req_trans) as response:
                trans_resp = json.loads(response.read().decode('utf-8'))
                translated_prompt = trans_resp.get('response', '').strip()
                if translated_prompt:
                    print(f"翻訳結果: {translated_prompt}")
                    prompt = translated_prompt
        except Exception as e:
            print(f"翻訳に失敗しました。元のプロンプトを使用します: {e}")
        # -------------------

        # プリセットが指定されている場合はヒントを付与
        if preset == 'FLAT':
            prompt += "\n[Requirement: FLAT / CITY preset. Use relief_level 1 to 2 and include a CITY zone.]"
        elif preset == 'HILLS':
            prompt += "\n[Requirement: HILLS preset. Use relief_level 2 to 3.]"
        elif preset == 'MOUNTAINS':
            prompt += "\n[Requirement: MOUNTAINS preset. Use relief_level 4 to 5 and ridge_sharpness 0.7 to 0.95.]"
        
        if current_blueprint is not None:
            bp_str = json.dumps(current_blueprint, ensure_ascii=False)
            prompt = f"Current Blueprint:\n{bp_str}\n\nEdit Request:\n{prompt}"
            system_prompt = textwrap.dedent(f"""\
                You are a 3D terrain architect ({scale_str}).
                Output ONLY a valid JSON diff patch with "operations" to modify the Current Blueprint according to the Edit Request.
                Format:
                {{
                  "operations": [
                    {{"op": "update_params", "params": {{"relief_level": 4.2, "ridge_sharpness": 0.8}}}},
                    {{"op": "add_zone", "zone": {{"type": "MOUNTAIN_RANGE", "region": "NORTH_EAST", "height_scale": 1.6, "width_scale": 1.2}}}},
                    {{"op": "modify_zone", "match": {{"id": "<zone_id>"}}, "updates": {{"height_scale": 1.8}}}},
                    {{"op": "remove_zone", "match": {{"id": "<zone_id>"}}}}
                  ]
                }}
            """)
        else:
            system_prompt = textwrap.dedent(f"""\
                You are a 3D terrain and level-design architect for Blender ({scale_str} open-world scale).
            Do NOT output raw 3D coordinate arrays. Instead, output ONLY a semantic terrain blueprint JSON that describes the composition and parameters.
            A spatial compiler will generate curved splines and Geometry Nodes parameters from your blueprint.

            [Blueprint Schema]
            - "archetype": "BASIN_CITY" | "CANYON_HIGHWAY" | "ALPINE_VALLEY" | "COASTAL_RIDGE" | "VOLCANIC_CALDERA" | "PLAINS_METROPOLIS" | "PLATEAU_MESA"
            - "orientation": "NORTH_SOUTH" | "EAST_WEST" | "NW_SE" | "NE_SW" | "RADIAL"
            - "relief_level": number 1.0 (very flat) to 5.0 (steep alpine mountains)
            - "ridge_sharpness": number 0.0 (smooth hills) to 1.0 (sharp rocky ridges)
            - "noise_scale_factor": number 0.5 (broad) to 2.0 (detailed), default 1.0
            - "water_level": null or elevation number (e.g. -20.0)
            - "zones": array of zone objects:
              * {{"type": "CITY", "region": "<REGION>", "scale": 0.6..8.0 (use 8.0 and region "CENTER" if the user requests a full-map city / all city)}}
              * {{"type": "MOUNTAIN_RANGE", "region": "<REGION>", "height_scale": 0.5..2.2, "width_scale": 0.5..2.0}}
              * {{"type": "VALLEY", "region": "<REGION>", "depth_scale": 0.5..2.2, "width_scale": 0.5..2.0}}
              Valid <REGION>: "CENTER", "NORTH", "SOUTH", "EAST", "WEST", "NORTH_EAST", "NORTH_WEST", "SOUTH_EAST", "SOUTH_WEST",
              "PERIMETER", "NORTH_TO_SOUTH", "EAST_TO_WEST", "SOUTH_TO_CENTER", "NORTH_TO_CENTER", "EAST_TO_CENTER", "WEST_TO_CENTER", "NW_TO_SE", "NE_TO_SW"
              Omit CITY zone if the user asks for pure nature without cities.
              Omit MOUNTAIN_RANGE and VALLEY zones if the user asks for the entire map to be a city (set archetype="PLAINS_METROPOLIS", relief_level=1.0, scale=8.0).
              If the user asks for cities in the East and West, output two CITY zones ("EAST" and "WEST") and set orientation="EAST_WEST".
            - "road_topology": "RING_AND_SPOKE" | "CROSS_VALLEY" | "COASTAL_CORRIDOR" | "MOUNTAIN_PASS" | "GRID_ORGANIC" | "HIGHWAY_SPINE" | "TUNNEL_HIGHWAY"
            - "has_tunnels": true | false (set true if tunnels, underground passages, or highways piercing mountains are requested)

            [Output Rules]
            - Output ONLY valid JSON. Do NOT include markdown formatting (like ```json) or explanations.

            [Example 1: Basin City]
            {{
              "archetype": "BASIN_CITY",
              "orientation": "NORTH_SOUTH",
              "relief_level": 4,
              "ridge_sharpness": 0.75,
              "noise_scale_factor": 1.0,
              "water_level": null,
              "zones": [
                {{"type": "CITY", "region": "CENTER", "scale": 1.2}},
                {{"type": "MOUNTAIN_RANGE", "region": "NORTH", "height_scale": 1.6, "width_scale": 1.2}},
                {{"type": "VALLEY", "region": "SOUTH_TO_CENTER", "depth_scale": 1.3, "width_scale": 0.8}}
              ],
              "road_topology": "RING_AND_SPOKE"
            }}

            [Example 2: Canyon Highway]
            {{
              "archetype": "CANYON_HIGHWAY",
              "orientation": "EAST_WEST",
              "relief_level": 4.5,
              "ridge_sharpness": 0.85,
              "noise_scale_factor": 1.2,
              "water_level": null,
              "zones": [
                {{"type": "VALLEY", "region": "NORTH_TO_SOUTH", "depth_scale": 1.8, "width_scale": 1.0}},
                {{"type": "MOUNTAIN_RANGE", "region": "WEST", "height_scale": 1.4, "width_scale": 1.1}},
                {{"type": "CITY", "region": "EAST", "scale": 1.0}}
              ],
              "road_topology": "CROSS_VALLEY"
            }}
        """)

        data = {
            "model": model_name,
            "prompt": prompt,
            "system": system_prompt,
            "stream": True
        }

        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), method='POST')
        req.add_header('Content-Type', 'application/json')

        try:
            print(f"--- Ollama API ({model_name}) にリクエスト送信中 ---")
            with urllib.request.urlopen(req) as response:
                ai_response = ""
                for line in response:
                    if line:
                        chunk_data = json.loads(line.decode('utf-8'))
                        content = chunk_data.get('response', '')
                        print(content, end='', flush=True)
                        ai_response += content
                
                print("\n--- AI生成完了 ---")
                
                import re
                try:
                    # マークダウンからJSON部分だけを抽出する
                    match = re.search(r'```(?:json)?\s*({.*?})\s*```', ai_response, re.DOTALL)
                    if match:
                        clean_json = match.group(1)
                    else:
                        # マークダウンがない場合は全体を{}で囲まれているか探す
                        match = re.search(r'({[\s\S]*})', ai_response)
                        if match:
                            clean_json = match.group(1)
                        else:
                            clean_json = ai_response

                    self._result = json.loads(clean_json)
                    
                    # 万が一空の辞書 {} が返ってきた場合のエラーハンドリング
                    if not self._result:
                        self._error = "AIが空のデータを返しました。もう一度実行してください。"
                        
                except json.JSONDecodeError:
                    self._error = "AIの返答をJSONとして解析できませんでした。"
                    print("\n解析エラー対象:", ai_response)

        except urllib.error.URLError as e:
            self._error = f"Ollamaとの通信に失敗しました。({e})"
            print(f"\nAPI接続エラー: {e}")

    def _smooth_90deg_cranks_chaikin_15m(self, pts, is_cyclic=False, clamp_limit=18000.0):
        """
        単一パイプラインによるスプライン全体平滑化:
          1. 40m 間隔のアンカー抽出
          2. Chaikin コーナーカッティング 2回
          3. ラプラシアン中点緩和（両端固定）で隣接セグメント折れ角を <= 12° に収める
          4. 15.0m 間隔の均一リサンプリング
        """
        return smooth_and_resample_road(
            pts,
            spacing=15.0,
            chaikin_iters=2,
            max_turn_deg=12.0,
            min_dist=5.0,
            is_cyclic=is_cyclic,
            clamp_limit=clamp_limit,
        )

    def _create_bezier_feature_curve(self, collection, name, pts, clamp_limit):
        """山脈・谷用の3Dベジェカーブを生成し、制御点ごとの radius / tilt を設定する"""
        if len(pts) < 2:
            return None
        curve = bpy.data.curves.new(name, 'CURVE')
        curve.dimensions = '3D'
        curve.twist_mode = 'Z_UP'
        obj = bpy.data.objects.new(name, curve)
        collection.objects.link(obj)
        spline = curve.splines.new('BEZIER')
        spline.bezier_points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            if isinstance(p, dict):
                co = p.get("co", [0.0, 0.0, 0.0])
                rad = float(p.get("radius", 1.0))
                tilt = float(p.get("tilt", 0.0))
            else:
                co = p
                rad = 1.0
                tilt = 0.0
            cx = max(-clamp_limit, min(clamp_limit, float(co[0])))
            cy = max(-clamp_limit, min(clamp_limit, float(co[1])))
            cz = float(co[2]) if len(co) >= 3 else 0.0
            bp = spline.bezier_points[i]
            bp.co = (cx, cy, cz)
            bp.radius = rad
            bp.tilt = tilt
            bp.handle_left_type = 'AUTO'
            bp.handle_right_type = 'AUTO'
        return obj

    def generate_splines(self, context, terrain_data):
        # 既存のコレクションを取得または作成
        mountain_col = self.get_or_create_collection(context, "Mountains")
        valley_col = self.get_or_create_collection(context, "Valleys")
        road_col = self.get_or_create_collection(context, "Roads")

        # 既存のAI生成オブジェクトをクリア(名前で判定)
        self.clear_ai_objects(mountain_col)
        self.clear_ai_objects(valley_col)
        self.clear_ai_objects(road_col)
        self._generator = None

        # もし未コンパイルの生辞書が直接渡された場合はコンパイルする
        if "ridge_sharpness" not in terrain_data and "archetype" in terrain_data:
            terrain_data = compile_blueprint(
                terrain_data,
                preset=getattr(self, 'preset', 'AUTO'),
                terrain_scale=getattr(self, 'terrain_scale', '40KM'),
                prompt=getattr(self, 'prompt', ''),
            )

        # スケール係数の取得 (40km / 20km)
        size_x = float(terrain_data.get("terrain_size_x", 40000.0 if getattr(self, 'terrain_scale', '40KM') == '40KM' else 20000.0))
        size_y = float(terrain_data.get("terrain_size_y", size_x))
        clamp_limit = (size_x / 2.0) * 0.88

        valleys = terrain_data.get("valleys", [])
        roads = terrain_data.get("roads", [])
        extra_roads = terrain_data.get("extra_roads", [])
        extra_road_metadata = terrain_data.get("extra_road_metadata", [])
        has_city = terrain_data.get("has_city", bool(roads))

        # --- Procedural City Generation (Step 1: City District & Grid Roads) ---
        if roads and has_city:
            try:
                from level_editor_city.city_generator import ProceduralCityGenerator
                self._generator = ProceduralCityGenerator(
                    terrain_size_x=size_x,
                    terrain_size_y=size_y,
                    seed=terrain_data.get("seed"),
                    city_style=terrain_data.get("city_style", "ORGANIC"),
                )
                roads = self._generator.generate_road_network(roads, terrain_data=terrain_data)
            except Exception as e:
                print(f"Road network generation failed: {e}")
        # ----------------------------------------------------------------------

        mountains = terrain_data.get("mountains", [])
        mountain_radius = float(terrain_data.get("mountain_radius", 1400.0))
        has_tunnels = bool(terrain_data.get("has_tunnels", False))
        allow_mountain_pass = any(
            k in (getattr(self, 'prompt', '') or "").lower()
            for k in ("峠", "山越え", "mountain pass", "switchback")
        )

        if roads or extra_roads:
            # 道路カーブオブジェクトの作成
            road_data = bpy.data.curves.new("RoadPath_AI", 'CURVE')
            road_data.dimensions = '3D'
            road_data.twist_mode = 'Z_UP'
            road_data.bevel_depth = 0.0 # create_roadのGeometry Nodesで立体化
            road_data.bevel_resolution = 0
            
            road_obj = bpy.data.objects.new("RoadPath_AI", road_data)
            road_col.objects.link(road_obj)
            context.view_layer.objects.active = road_obj
            road_obj.select_set(True)

            sub_biomes = detect_biomes(self.prompt, self.biome)
            detected_biome = detect_biome(self.prompt, self.biome)
            # 街路・小道の道路タイプを自動判定（砂漠なら砂道、プロンプトで砂利道なら砂利道）
            sub_road_type = detect_road_type(self.prompt, detected_biome)
            if sub_road_type == 'ASPHALT':
                if detected_biome == 'DESERT' or (sub_biomes and 'DESERT' in sub_biomes):
                    sub_road_type = 'SAND_DIRT'
                elif any(k in (self.prompt or "").lower() for k in ["砂道", "砂利", "ダート"]):
                    sub_road_type = 'SAND_DIRT'
                else:
                    sub_road_type = 'GRAVEL'

            # スプラインメタデータ（幹線: radius=1.0, 街路: radius=0.5）を取得し、単一パイプラインで平滑化 (15m間隔, 折れ角<=12度)
            # 広域幹線道路 (ARTERIAL_HIGHWAY / is_main=True) は山麓迂回させず、トンネル・橋梁で滑らかに貫通させる
            spline_items = []
            if self._generator and hasattr(self._generator, 'get_road_splines_with_metadata'):
                gen_items = list(self._generator.get_road_splines_with_metadata())
                for g_idx, (pts, meta) in enumerate(gen_items):
                    if len(pts) < 2:
                        spline_items.append((pts, meta))
                        continue
                    is_cyc = bool(meta.get('cyclic', False))
                    is_arterial = bool(meta.get('is_main', False)) or (meta.get('type') == 'ARTERIAL_HIGHWAY')
                    if is_arterial or not mountains:
                        routed_p = smooth_and_resample_road(
                            pts,
                            spacing=15.0,
                            chaikin_iters=2,
                            max_turn_deg=12.0,
                            min_dist=5.0,
                            is_cyclic=is_cyc,
                            clamp_limit=clamp_limit,
                        )
                    else:
                        routed_p = route_road_around_mountains(
                            pts,
                            mountains=mountains,
                            mountain_radius=mountain_radius,
                            allow_mountain_pass=False,
                            is_cyclic=is_cyc,
                            clamp_limit=clamp_limit,
                        )
                    self._generator.generated_splines[g_idx] = routed_p
                    spline_items.append((routed_p, meta))
            elif roads:
                for pts in roads:
                    if not allow_mountain_pass:
                        routed_p = smooth_and_resample_road(
                            pts,
                            spacing=15.0,
                            chaikin_iters=2,
                            max_turn_deg=12.0,
                            min_dist=5.0,
                            is_cyclic=False,
                            clamp_limit=clamp_limit,
                        )
                    else:
                        routed_p = route_road_around_mountains(
                            pts,
                            mountains=mountains,
                            mountain_radius=mountain_radius,
                            allow_mountain_pass=allow_mountain_pass,
                            is_cyclic=False,
                            clamp_limit=clamp_limit,
                        )
                    spline_items.append((routed_p, {'is_main': True}))

            # 都市外独立道路（峠道・海岸線・自然地形道路）は ProceduralCityGenerator を通さず直接追加
            for e_idx, e_pts in enumerate(extra_roads):
                e_meta = extra_road_metadata[e_idx] if e_idx < len(extra_road_metadata) else {'is_main': True}
                is_cyc = bool(e_meta.get('cyclic', False))
                e_type = str(e_meta.get('type', '')).upper()
                is_pass_route = allow_mountain_pass or (e_type == 'MOUNTAIN_PASS')
                if is_pass_route and mountains:
                    routed_p = route_road_around_mountains(
                        e_pts,
                        mountains=mountains,
                        mountain_radius=mountain_radius,
                        allow_mountain_pass=True,
                        is_cyclic=is_cyc,
                        clamp_limit=clamp_limit,
                    )
                else:
                    routed_p = smooth_and_resample_road(
                        e_pts,
                        spacing=15.0,
                        chaikin_iters=2,
                        max_turn_deg=12.0,
                        min_dist=5.0,
                        is_cyclic=is_cyc,
                        clamp_limit=clamp_limit,
                    )
                spline_items.append((routed_p, e_meta))

            for item_idx, (sub_pts, meta) in enumerate(spline_items):
                if len(sub_pts) < 2:
                    continue
                is_cyclic = bool(meta.get('cyclic', False))
                is_main = meta.get('is_main', False)
                spline = road_data.splines.new('POLY')
                spline.points.add(len(sub_pts) - 1)
                spline.use_cyclic_u = is_cyclic
                rad = 1.0 if is_main else 0.5
                for i, p in enumerate(sub_pts):
                    spline.points[i].co = (p[0], p[1], p[2], 1.0)
                    spline.points[i].radius = rad

            if setup_mixed_road_geometry_nodes:
                setup_mixed_road_geometry_nodes(
                    curve_obj=road_obj,
                    primary_type='ASPHALT',
                    secondary_type=sub_road_type,
                    main_width=24.0,
                    sub_width=12.0,
                    main_lanes=4,
                    line_width=0.15
                )
            else:
                road_mat = get_or_create_road_material(sub_road_type)
                road_data.materials.append(road_mat)

        # 山脈（custom_radius / custom_tilt 付きベジェカーブ）
        mountains = terrain_data.get("mountains", [])
        for idx, pts in enumerate(mountains):
            self._create_bezier_feature_curve(mountain_col, f"MountainPath_AI_{idx}", pts, clamp_limit)

        # 谷（custom_radius / custom_tilt 付きベジェカーブ）
        for idx, pts in enumerate(valleys):
            self._create_bezier_feature_curve(valley_col, f"ValleyPath_AI_{idx}", pts, clamp_limit)


    def get_or_create_collection(self, context, name):
        col = bpy.data.collections.get(name)
        if not col:
            col = bpy.data.collections.new(name)
            context.scene.collection.children.link(col)
        return col

    def clear_ai_objects(self, collection):
        objs_to_remove = [obj for obj in collection.objects if "_AI" in obj.name]
        for obj in objs_to_remove:
            bpy.data.objects.remove(obj, do_unlink=True)


class MYADDON_OT_rebuild_from_curves(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_rebuild_from_curves"
    bl_label = "カーブ変更を地形に反映"
    bl_description = "Mountains / Valleys / Roads コレクションの手動編集をハイトマップ・侵食・テクスチャへ再反映します"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            from .terrain_pipeline import rebuild_heightmap_from_scene_curves
        except ImportError:
            from terrain_pipeline import rebuild_heightmap_from_scene_curves

        try:
            hm_meta, _ = rebuild_heightmap_from_scene_curves(context)
            stats = hm_meta.get("stats", {})
            self.report(
                {'INFO'},
                f"カーブ変更を反映しました ({stats.get('generation_seconds')}s / 標高 {stats.get('min_height')}m〜{stats.get('max_height')}m)",
            )
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"再反映に失敗しました: {e}")
            return {'CANCELLED'}


class VIEW3D_PT_tl1_terrain_sync(bpy.types.Panel):
    bl_label = "TL1 AI地形ツール"
    bl_idname = "VIEW3D_PT_tl1_terrain_sync"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TL1 Terrain'

    def draw(self, context):
        layout = self.layout
        layout.operator(MYADDON_OT_ai_generate_terrain.bl_idname, text="AI地形生成 / 部分修正", icon='SHADERFX')
        layout.operator(MYADDON_OT_rebuild_from_curves.bl_idname, text="カーブ変更を地形に反映", icon='FILE_REFRESH')
