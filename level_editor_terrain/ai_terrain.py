# -*- coding: utf-8 -*-
import bpy  # type: ignore
import json
import os
import urllib.request
import urllib.error
import textwrap

try:
    from .terrain_materials import detect_biome, apply_biome_material_to_terrain, detect_road_type, get_or_create_road_material
except ImportError:
    import sys
    sys.path.append(os.path.dirname(__file__))
    from terrain_materials import detect_biome, apply_biome_material_to_terrain, detect_road_type, get_or_create_road_material

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
        default="中央に南北の谷があり、東側の平坦地に道路と街が広がっている20km四方の地形",
        maxlen=1024,
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
        description="地形のマテリアル・環境タイプ（砂漠、雪原、峡谷、火山、草原など）",
        items=[
            ('AUTO', "バイオーム: 自動判別 (Auto)", "プロンプトから砂漠・雪原・峡谷・火山・草原を自動判別"),
            ('DESERT', "砂漠 (Desert)", "オレンジ・黄色の砂紋と赤褐色の崖"),
            ('PLAINS', "草原 (Plains)", "緑豊かな大地と土岩の崖"),
            ('SNOW', "雪原 / 氷河 (Snow)", "白銀の雪原と青暗い岩壁"),
            ('CANYON', "峡谷 (Canyon)", "テラコッタ層の赤土と崖"),
            ('VOLCANO', "火山 / 荒野 (Volcano)", "玄武岩の黒灰と赤黒い岩"),
        ],
        default='AUTO'
    ) # type: ignore

    _timer = None
    _thread = None
    _result = None
    _error = None

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
        row.prop(self, "preset", text="")
        row.prop(self, "biome", text="")
        layout.prop(self, "prompt", text="指示")
        layout.label(text="※ バックグラウンドで処理され、完了時に地形・マテリアルが生成されます。", icon='INFO')

    def execute(self, context):
        import threading
        self._result = None
        self._error = None

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
                args=(self.gemini_model, key, self.prompt, self.preset)
            )
        else:
            self._thread = threading.Thread(
                target=self.run_ollama_request,
                args=(self.model_name, self.prompt, self.preset)
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
                    p_lower = (self.prompt or "").lower()
                    has_valley = any(k in p_lower for k in ["谷", "キャニオン", "canyon", "valley", "渓谷"])
                    has_mountain = any(k in p_lower for k in ["山", "mountain", "峰", "丘", "連峰"])
                    has_city = any(k in p_lower for k in ["平", "フラット", "flat", "plain", "都市", "街", "city"])

                    # プリセットまたはAI解析値からTerrain Heightと初期プリセットを決定 (20kmスケール)
                    if self.preset == 'FLAT':
                        exec_preset = 'FLAT'
                        target_height = 25.0 if has_valley else 5.0
                    elif self.preset == 'HILLS':
                        exec_preset = 'HILLS'
                        target_height = 100.0
                    elif self.preset == 'MOUNTAINS':
                        exec_preset = 'MOUNTAINS'
                        target_height = 350.0
                    else: # AUTO
                        if has_valley and has_city:
                            # 谷と街の複合：街は平坦にしつつ谷底との落差を際立たせるため適度な起伏を設定
                            target_height = 45.0
                            exec_preset = 'HILLS'
                        elif has_city:
                            target_height = 10.0
                            exec_preset = 'FLAT'
                        elif has_mountain:
                            target_height = 350.0
                            exec_preset = 'MOUNTAINS'
                        else:
                            target_height = 80.0
                            exec_preset = 'HILLS'

                    self.generate_splines(context, self._result)
                    bpy.ops.myaddon.myaddon_ot_create_terrain(preset=exec_preset)
                    
                    terrain_obj = bpy.data.objects.get("Terrain")
                    road_obj = bpy.data.objects.get("RoadPath_AI")
                    
                    # バイオーム（質感・マテリアル）の判定と適用
                    detected_biome = detect_biome(self.prompt, self.biome)
                    if terrain_obj:
                        apply_biome_material_to_terrain(terrain_obj, detected_biome)

                    if terrain_obj:
                        mod = terrain_obj.modifiers.get("TerrainGen")
                        if mod:
                            def set_mod_input(m, name, val):
                                if val is None:
                                    return False
                                if name in m:
                                    try:
                                        m[name] = val
                                        return True
                                    except:
                                        pass
                                if hasattr(m, "node_group") and m.node_group:
                                    if hasattr(m.node_group, "interface"):
                                        for item in m.node_group.interface.items_tree:
                                            if getattr(item, 'item_type', '') == 'SOCKET' and item.in_out == 'INPUT' and item.name == name:
                                                try:
                                                    m[item.identifier] = val
                                                    return True
                                                except:
                                                    pass
                                    elif hasattr(m.node_group, "inputs"):
                                        for item in m.node_group.inputs:
                                            if item.name == name:
                                                try:
                                                    m[item.identifier] = val
                                                    return True
                                                except:
                                                    pass
                                return False

                            set_mod_input(mod, 'Grid Size X', self._result.get("terrain_size_x", 20000.0))
                            set_mod_input(mod, 'Grid Size Y', self._result.get("terrain_size_y", 20000.0))
                            set_mod_input(mod, 'Terrain Height', target_height)
                            
                            # 谷コレクションと山岳コレクションを確実に接続
                            val_col = bpy.data.collections.get("Valleys")
                            if val_col:
                                set_mod_input(mod, 'Valley Collection', val_col)
                                set_mod_input(mod, 'Valley Depth', 400.0)   # 20kmスケールの深さ400m
                                set_mod_input(mod, 'Valley Radius', 1800.0) # 谷の幅 3.6km

                            mt_col = bpy.data.collections.get("Mountains")
                            if mt_col:
                                set_mod_input(mod, 'Mountain Collection', mt_col)
                                set_mod_input(mod, 'Mountain Height', 450.0)
                                set_mod_input(mod, 'Mountain Radius', 1400.0)

                            # Roadの割り当てを一時解除（Terrain本来の高さを取得するため）
                            road_input_key = None
                            for key in mod.keys():
                                try:
                                    if mod[key] == road_obj:
                                        road_input_key = key
                                        mod[key] = None
                                except:
                                    pass
                                    
                            # Terrainの高さをRoadに投影
                            if road_obj:
                                self.project_road_to_terrain(context, road_obj, terrain_obj)
                                # 道路を20kmスケールに見合う幅(幹線24m / 街路12m)でGeometry Nodes立体メッシュ化
                                road_obj.data.dimensions = '3D'
                                road_obj.data.bevel_depth = 0.0
                                road_obj.data.bevel_resolution = 0
                                
                                # 混在道路ノードが未設定の場合のフォールバック
                                if not road_obj.modifiers.get("RoadGen") and setup_mixed_road_geometry_nodes:
                                    sub_road_type = detect_road_type(self.prompt, detected_biome)
                                    setup_mixed_road_geometry_nodes(
                                        curve_obj=road_obj,
                                        primary_type='ASPHALT',
                                        secondary_type=sub_road_type,
                                        main_width=24.0,
                                        sub_width=12.0
                                    )
                                
                            # --- Procedural City Generation (Step 2: City Districts & Blocks) ---
                            if hasattr(self, '_generator') and self._generator:
                                try:
                                    lots = self._generator.generate_building_lots()
                                    if lots:
                                        self.spawn_buildings(context, lots, terrain_obj, detected_biome)
                                except Exception as e:
                                    print(f"Building lot generation failed: {e}")
                            # ----------------------------------------------------------------
                                
                            # RoadをTerrainに割り当て直す
                            if road_input_key:
                                mod[road_input_key] = road_obj
                            else:
                                try:
                                    mod["Socket_1"] = road_obj
                                except:
                                    try:
                                        mod["Road Object"] = road_obj
                                    except:
                                        pass

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

    def _add_cube_to_bmesh(self, bm, cx, cy, hw, hh, z_min, z_max, angle=0.0):
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
        
        bm.faces.new((v1, v4, v3, v2)) # Bottom
        bm.faces.new((v5, v6, v7, v8)) # Top
        bm.faces.new((v1, v2, v6, v5)) # Front
        bm.faces.new((v2, v3, v7, v6)) # Right
        bm.faces.new((v3, v4, v8, v7)) # Back
        bm.faces.new((v4, v1, v5, v8)) # Left

    def spawn_buildings(self, context, lots, terrain_obj, biome='PLAINS'):
        import bmesh
        import mathutils
        import random
        
        # 既存のBuildingsコレクションとオブジェクトをクリア
        build_col = self.get_or_create_collection(context, "Buildings")
        self.clear_ai_objects(build_col)
        
        mesh = bpy.data.meshes.new("Buildings_AI")
        obj = bpy.data.objects.new("Buildings_AI", mesh)
        build_col.objects.link(obj)
        
        bm = bmesh.new()
        
        context.view_layer.update()
        depsgraph = context.evaluated_depsgraph_get()
        
        for lot in lots:
            x, y = lot['x'], lot['y']
            w, h, z_height = lot['w'], lot['h'], lot['z_height']
            b_type = lot.get('type', 'MIDRISE')
            angle = lot.get('angle', 0.0)
            
            # Terrainへのレイキャスト
            origin = mathutils.Vector((x, y, 1000.0))
            dir_world = mathutils.Vector((0.0, 0.0, -1.0))
            
            hit_z = 0
            current_origin = origin
            for _ in range(10):
                success, loc, _, _, hit_obj, _ = context.scene.ray_cast(depsgraph, current_origin, dir_world)
                if success:
                    if hit_obj and hit_obj.name == terrain_obj.name:
                        hit_z = loc.z
                        break
                    else:
                        current_origin = loc + dir_world * 0.01
                else:
                    break
                
            # 建物のキューブを作成
            z_min = hit_z - 3.0 # 地面に確実に埋め込む
            z_max = hit_z + z_height
            
            hw = w / 2.0
            hh = h / 2.0
            
            # 高層摩天楼（高さ75m以上）の場合は上部セットバック（段差タワー）を造形
            if z_height >= 75.0 and b_type == 'SKYSCRAPER':
                base_z = hit_z + z_height * 0.58
                self._add_cube_to_bmesh(bm, x, y, hw, hh, z_min, base_z, angle=angle)
                
                # 上層タワー（60%幅）
                tower_hw = hw * 0.62
                tower_hh = hh * 0.62
                self._add_cube_to_bmesh(bm, x, y, tower_hw, tower_hh, base_z, z_max, angle=angle)
                
                # 屋上尖塔・アンテナ
                if random.random() < 0.6:
                    spire_z = z_max + random.uniform(15.0, 35.0)
                    self._add_cube_to_bmesh(bm, x, y, 2.5, 2.5, z_max, spire_z, angle=angle)
            else:
                self._add_cube_to_bmesh(bm, x, y, hw, hh, z_min, z_max, angle=angle)
            
        bm.to_mesh(mesh)
        bm.free()
        
        # マテリアル設定（バイオームに応じた建造物カラー）
        mat_name = f"Building_Biome_{biome}"
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(mat_name)
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                if biome == 'DESERT':
                    # 砂漠の街並み: 砂岩・土壁風の明るいベージュ・サンドストーン
                    bsdf.inputs["Base Color"].default_value = (0.86, 0.74, 0.58, 1.0)
                    bsdf.inputs["Roughness"].default_value = 0.8
                    mat.diffuse_color = (0.86, 0.74, 0.58, 1.0)
                elif biome == 'CANYON':
                    # 峡谷の街: 赤土・テラコッタレンガ調
                    bsdf.inputs["Base Color"].default_value = (0.75, 0.48, 0.36, 1.0)
                    bsdf.inputs["Roughness"].default_value = 0.75
                    mat.diffuse_color = (0.75, 0.48, 0.36, 1.0)
                elif biome == 'SNOW':
                    # 雪原都市: 寒冷地コンクリート・白藍色
                    bsdf.inputs["Base Color"].default_value = (0.78, 0.82, 0.88, 1.0)
                    bsdf.inputs["Roughness"].default_value = 0.35
                    mat.diffuse_color = (0.78, 0.82, 0.88, 1.0)
                elif biome == 'VOLCANO':
                    # 火山・荒野: 玄武岩・ダークスレート調
                    bsdf.inputs["Base Color"].default_value = (0.28, 0.28, 0.30, 1.0)
                    bsdf.inputs["Roughness"].default_value = 0.6
                    mat.diffuse_color = (0.28, 0.28, 0.30, 1.0)
                else: # PLAINS
                    # 草原・一般: クリーンホワイトモックアップ
                    bsdf.inputs["Base Color"].default_value = (0.85, 0.85, 0.88, 1.0)
                    bsdf.inputs["Roughness"].default_value = 0.25
                    mat.diffuse_color = (0.85, 0.85, 0.88, 1.0)
        obj.data.materials.append(mat)

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

    def project_road_to_terrain(self, context, road_obj, terrain_obj):
        """
        道路スプラインを地形に投影。谷（Valley）や深い窪みでは空中の橋梁デッキ（Bridge Deck）として
        水平に維持し、巨大橋脚（Piers）およびガードレールを自動架橋する
        """
        import mathutils
        import math
        context.view_layer.update()
        depsgraph = context.evaluated_depsgraph_get()
        
        road_mat_inv = road_obj.matrix_world.inverted()
        road_curve = road_obj.data

        bridge_piers_data = []
        guardrails_data = []

        for spline in road_curve.splines:
            points = spline.bezier_points if spline.type == 'BEZIER' else spline.points
            if len(points) < 2:
                continue

            # 1. 各点の地面標高 (raw_ground_z) をレイキャストで取得
            raw_ground_z = []
            coords_local = []
            for pt in points:
                co = pt.co[:3] if spline.type == 'POLY' else pt.co
                coords_local.append(co)
                co_world = road_obj.matrix_world @ mathutils.Vector(co)
                
                origin_world = mathutils.Vector((co_world.x, co_world.y, 1000.0))
                dir_world = mathutils.Vector((0.0, 0.0, -1.0))
                
                hit_z = 0.0
                current_origin = origin_world
                for _ in range(10):
                    success, location, normal, index, obj, matrix = context.scene.ray_cast(depsgraph, current_origin, dir_world)
                    if success:
                        if obj and obj.name == terrain_obj.name:
                            hit_local = road_mat_inv @ location
                            hit_z = hit_local.z
                            break
                        else:
                            current_origin = location + dir_world * 0.01
                    else:
                        break
                raw_ground_z.append(hit_z)

            # 2. 谷（Valley）や深い窪みの上を通る橋梁区間 (bridge_spans) の検出
            bridge_spans = []
            n_pts = len(points)
            in_bridge = False
            b_start = 0

            for i in range(n_pts):
                x = coords_local[i][0]
                gz = raw_ground_z[i]
                
                # 中央の谷の判定（|x| < 2400 かつ 地面標高が低くなっている）
                is_valley_area = (abs(x) < 2400.0 and gz < 8.0)
                
                if is_valley_area:
                    if not in_bridge:
                        in_bridge = True
                        b_start = max(0, i - 1)
                else:
                    if in_bridge:
                        in_bridge = False
                        b_end = min(n_pts - 1, i)
                        if b_end - b_start >= 3:
                            bridge_spans.append((b_start, b_end))

            # 3. 橋梁区間の Z 座標を、両岸の標高を維持した空中高架デッキ（Bridge Deck）に設定
            deck_z_list = list(raw_ground_z)
            for s_idx, e_idx in bridge_spans:
                z_start = raw_ground_z[s_idx]
                z_end = raw_ground_z[e_idx]
                bridge_level = max(z_start, z_end) + 1.2
                for k in range(s_idx, e_idx + 1):
                    deck_z_list[k] = bridge_level

            # 4. 各点に Z 座標を適用
            for i, pt in enumerate(points):
                co = coords_local[i]
                is_in_bridge = any(s <= i <= e for s, e in bridge_spans)
                if is_in_bridge:
                    target_z = deck_z_list[i]
                else:
                    target_z = raw_ground_z[i] + 0.35

                if spline.type == 'POLY':
                    pt.co = (co[0], co[1], target_z, pt.co[3])
                else:
                    pt.co = (co[0], co[1], target_z)

            # 5. 橋脚およびガードレールのデータ収集
            is_main = (spline.points[0].radius >= 0.8) if len(spline.points) > 0 else True
            half_w = 12.0 if is_main else 6.0

            for s_idx, e_idx in bridge_spans:
                dist_acc = 0.0
                last_pier_dist = 0.0
                for k in range(s_idx, e_idx):
                    p1 = coords_local[k]
                    p2 = coords_local[k+1]
                    seg_len = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
                    dist_acc += seg_len
                    
                    if dist_acc - last_pier_dist >= 95.0:
                        last_pier_dist = dist_acc
                        dz = deck_z_list[k]
                        gz = raw_ground_z[k]
                        if (dz - gz) >= 8.0:
                            bridge_piers_data.append((p1[0], p1[1], dz, gz, half_w))

                    # ガードレール
                    z1 = deck_z_list[k]
                    z2 = deck_z_list[k+1]
                    guardrails_data.append(((p1[0], p1[1], z1), (p2[0], p2[1], z2), half_w))

        # 6. 橋梁構造物のメッシュ生成
        if bridge_piers_data or guardrails_data:
            try:
                self.spawn_bridge_structures(context, bridge_piers_data, guardrails_data)
            except Exception as e:
                print(f"Bridge structure generation failed: {e}")

    def run_gemini_request(self, model_name, api_key, prompt, preset='AUTO'):
        preset_hint = ""
        if preset == 'FLAT':
            preset_hint = "\n【ユーザー指定: 平野/街プリセット】terrain_heightは2.0〜10.0の極小値にし、中央を平坦にして街（roads）を広げてください。"
        elif preset == 'HILLS':
            preset_hint = "\n【ユーザー指定: 丘陵プリセット】terrain_heightは50.0〜120.0程度にしてください。"
        elif preset == 'MOUNTAINS':
            preset_hint = "\n【ユーザー指定: 山岳プリセット】terrain_heightは200.0〜500.0程度にしてください。"
            
        user_content = prompt + preset_hint
        
        system_instruction = textwrap.dedent("""\
            あなたはBlenderの3D地形・都市生成AIアシスタントです。
            全体サイズはデフォルトで20km四方 (20,000m × 20,000m) のオープンワールド規模です。
            ユーザーの要望に基づき、山脈(mountains)、谷(valleys)、道路(roads)、ベース起伏の強さ(terrain_height)の座標データをJSON形式で出力してください。
            
            [座標系 (20km四方)]
            - X: 左右 (西がマイナス [-10000..0], 東がプラス [0..10000])
            - Y: 前後 (南がマイナス [-10000..0], 北がプラス [0..10000])
            - Z: 高さ (通常は0)
            
            [重要ルール]
            1. 街・都市・建物群: 街や建物は道路(roads)の周囲に自動生成されます。ユーザーが「東側に街」「中央にビル街」のように特定エリアに街や建物を求めた場合、必ずそのエリアに道路(roads)を配置してください（例: 東側なら X: 2000〜8000 の範囲に道路を引く）。
            2. 谷・山脈: 「中央」に谷や山を置く場合は座標の X または Y を 0 付近に配置してください。東西南北の指定があれば座標系に従って配置してください。
            3. terrain_height (ベース起伏の強さ):
               - 平野、街、都市、広場: 2.0 〜 10.0 (街のエリアを山や谷で分断しないこと)
               - なだらかな丘陵: 50.0 〜 120.0
               - 険しい山岳・深い渓谷: 200.0 〜 500.0
            4. 道路・山脈・谷は直線ではなく、自然に曲がりくねった形状になるよう1本あたり4〜6点の制御点を持たせてください。
            5. 不要な要素（平野で谷がない場合など）は空リスト [] としてください。
            
            [出力JSONスキーマ例 (20km規模)]
            {
              "terrain_size_x": 20000.0,
              "terrain_size_y": 20000.0,
              "terrain_height": 5.0,
              "mountains": [
                [[-4000, 3000, 0], [-1500, 4500, 0], [1000, 2500, 0], [3500, 4000, 0]]
              ],
              "valleys": [
                [[-2000, -4000, 0], [-500, -2000, 0], [1500, -3500, 0], [4000, -1500, 0]]
              ],
              "roads": [
                [[-10000, 1000, 0], [-4000, -1000, 0], [0, 500, 0], [5000, -500, 0], [10000, 0, 0]]
              ]
            }
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

    def run_ollama_request(self, model_name, prompt, preset='AUTO'):
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
            prompt += "\n[Requirement: The user selected FLAT / CITY preset. Keep terrain_height very low (0.0 to 1.5). Do not place mountains in the central area.]"
        elif preset == 'HILLS':
            prompt += "\n[Requirement: The user selected HILLS preset. Keep terrain_height moderate (50.0 to 120.0).]"
        elif preset == 'MOUNTAINS':
            prompt += "\n[Requirement: The user selected MOUNTAINS preset. Keep terrain_height high (200.0 to 500.0).]"
        
        system_prompt = textwrap.dedent("""\
            You are a terrain generation assistant for Blender.
            The default terrain size is 20km x 20km (20,000m x 20,000m) open-world scale.
            Output the placement of terrain elements (mountains, valleys, roads) and base roughness in JSON format based on the user's request.
            Coordinate system (20km scale):
            - X: Left/Right (West is negative X [-10000..0], East is positive X [0..10000])
            - Y: Front/Back (South is negative Y [-10000..0], North is positive Y [0..10000])
            - Z: Height (Base Z is usually 0)
            
            [Output Format and Rules]
            - Output ONLY valid JSON. Do NOT include markdown formatting (like ```json), explanations, or conversational text.
            - Cities and Buildings: Cities and buildings are automatically constructed around roads. When the user asks for a "city", "town", or "buildings" in a specific area (e.g., "east side"), you MUST place the road(s) in that area (e.g. X: 2000..8000 for East) so that the procedural city generator can spawn buildings there.
            - Valleys & Mountains: When placing a valley or mountain in the "center", keep its X or Y coordinates near 0. For north/south/east/west, align coordinates accordingly.
            - terrain_height: Controls the overall base elevation/roughness.
              * Flat plains, city, plaza, or buildable space: 2.0 - 10.0. Avoid placing mountains/valleys directly through the city area.
              * Rolling hills: 50.0 - 120.0.
              * Rugged mountains or deep canyons: 200.0 - 500.0.
            - To avoid unnatural straight lines, ensure the coordinates for roads, mountains, and valleys are naturally curved or zig-zagged.
            - Provide about 4 to 6 control points per curve to express natural winding shapes.
            - If an element is not needed, provide an empty list [].
            
            [Example 1: Flat City / Plains (20km)]
            {
              "terrain_size_x": 20000.0,
              "terrain_size_y": 20000.0,
              "terrain_height": 5.0,
              "mountains": [],
              "valleys": [],
              "roads": [
                [[-10000, 1000, 0], [-4000, -1000, 0], [0, 500, 0], [5000, -500, 0], [10000, 0, 0]]
              ]
            }

            [Example 2: Mountainous Valley (20km)]
            {
              "terrain_size_x": 20000.0,
              "terrain_size_y": 20000.0,
              "terrain_height": 250.0,
              "mountains": [
                [[-4000, 3000, 0], [-1500, 4500, 0], [1000, 2500, 0], [3500, 4000, 0]]
              ],
              "valleys": [
                [[-2000, -4000, 0], [-500, -2000, 0], [1500, -3500, 0], [4000, -1500, 0]]
              ],
              "roads": [
                [[-10000, 1000, 0], [-5000, -2000, 0], [0, 1500, 0], [6000, -1000, 0], [10000, 0, 0]]
              ]
            }
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

    def generate_splines(self, context, terrain_data):
        import random
        # 既存のコレクションを取得または作成
        mountain_col = self.get_or_create_collection(context, "Mountains")
        valley_col = self.get_or_create_collection(context, "Valleys")
        road_col = self.get_or_create_collection(context, "Roads")

        # 既存のAI生成オブジェクトをクリア(名前で判定)
        self.clear_ai_objects(mountain_col)
        self.clear_ai_objects(valley_col)
        self.clear_ai_objects(road_col)
        
        p_lower = (self.prompt or "").lower()

        # --- 谷データの取得とプロンプトスマート補完 ---
        valleys = terrain_data.get("valleys", [])
        # プロンプトに谷が指定されていてデータが空、または短すぎる場合は高精度スプラインを自動補完
        if any(k in p_lower for k in ["谷", "キャニオン", "canyon", "valley", "渓谷"]):
            if not valleys or len(valleys[0]) < 2:
                if "南北" in p_lower or "中央" in p_lower:
                    # 中央を南北に蛇行して縦断する雄大な大峡谷スプライン (20kmスケール, 区域内クランプ)
                    valleys = [[
                        [-250.0, -8800.0, 0.0],
                        [400.0,  -5500.0, 0.0],
                        [-300.0, -2000.0, 0.0],
                        [350.0,   2500.0, 0.0],
                        [-200.0,  6000.0, 0.0],
                        [100.0,   8800.0, 0.0]
                    ]]
                elif "東西" in p_lower:
                    valleys = [[
                        [-8800.0, -250.0, 0.0],
                        [-5500.0,  400.0, 0.0],
                        [-2000.0, -300.0, 0.0],
                        [ 2500.0,  350.0, 0.0],
                        [ 6000.0, -200.0, 0.0],
                        [ 8800.0,  100.0, 0.0]
                    ]]

        # --- 道路データの取得とプロンプトスマート補完 ---
        roads = terrain_data.get("roads", [])
        if any(k in p_lower for k in ["街", "都市", "道", "道路", "city", "road"]):
            if not roads or len(roads[0]) < 2:
                if "東" in p_lower:
                    # 東側 (X: 3500〜4500) に幹線大通り
                    roads = [[
                        [4000.0, -8500.0, 0.0],
                        [4200.0, -3500.0, 0.0],
                        [3900.0,  2500.0, 0.0],
                        [4100.0,  8500.0, 0.0]
                    ]]
                elif "西" in p_lower:
                    roads = [[
                        [-4000.0, -8500.0, 0.0],
                        [-4200.0, -3500.0, 0.0],
                        [-3900.0,  2500.0, 0.0],
                        [-4100.0,  8500.0, 0.0]
                    ]]
                else:
                    roads = [[
                        [-8500.0, 500.0, 0.0],
                        [-3000.0, -200.0, 0.0],
                        [ 3000.0,  400.0, 0.0],
                        [ 8500.0, -100.0, 0.0]
                    ]]

        # --- Procedural City Generation (Step 1: City District & Grid Roads) ---
        if roads:
            try:
                from level_editor_city.city_generator import ProceduralCityGenerator
                self._generator = ProceduralCityGenerator(
                    terrain_size_x=terrain_data.get("terrain_size_x", 20000.0),
                    terrain_size_y=terrain_data.get("terrain_size_y", 20000.0)
                )
                roads = self._generator.generate_road_network(roads, terrain_data=terrain_data)
            except Exception as e:
                print(f"Road network generation failed: {e}")
        # ----------------------------------------------------------------------

        if roads:
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

            detected_biome = detect_biome(self.prompt)
            # 街路・小道の道路タイプを自動判定（砂漠なら砂道、プロンプトで砂利道なら砂利道）
            sub_road_type = detect_road_type(self.prompt, detected_biome)
            if sub_road_type == 'ASPHALT':
                # ユーザーの「混在させて」の要望に応え、街路・小道に砂道または砂利道を混在
                if detected_biome == 'DESERT':
                    sub_road_type = 'SAND_DIRT'
                elif any(k in (self.prompt or "").lower() for k in ["砂道", "砂利", "ダート"]):
                    sub_road_type = 'SAND_DIRT'
                else:
                    sub_road_type = 'GRAVEL' # 通常平原でも幹線アスファルト＋小道砂利道で混在

            # スプラインメタデータ（幹線: radius=1.0, 街路: radius=0.5）を取得
            spline_items = []
            if hasattr(self, '_generator') and hasattr(self._generator, 'get_road_splines_with_metadata'):
                spline_items = self._generator.get_road_splines_with_metadata()
            
            if not spline_items:
                spline_items = [(pts, {'is_main': True}) for pts in roads]

            for pts, meta in spline_items:
                if len(pts) < 2: continue
                # 長すぎる直線セグメントを75mごとに細分化し、地面起伏への追従精度を最大化（埋没完全防止）
                sub_pts = self._subdivide_spline(pts, max_seg_len=75.0)
                spline = road_data.splines.new('POLY')
                spline.points.add(len(sub_pts) - 1)
                is_main = meta.get('is_main', False)
                rad = 1.0 if is_main else 0.5
                for i, p in enumerate(sub_pts):
                    spline.points[i].co = (p[0], p[1], p[2], 1.0)
                    spline.points[i].radius = rad

            # 既存のcreate_roadと同様のGeometry Nodes (RoadGen) を適用（幹線アスファルト+白線 と 街路砂道/砂利道 の混在）
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

        # 山脈
        mountains = terrain_data.get("mountains", [])
        for idx, pts in enumerate(mountains):
            if len(pts) < 2: continue
            curve = bpy.data.curves.new(f"MountainPath_AI_{idx}", 'CURVE')
            curve.dimensions = '3D'
            curve.twist_mode = 'Z_UP'
            obj = bpy.data.objects.new(f"MountainPath_AI_{idx}", curve)
            mountain_col.objects.link(obj)
            spline = curve.splines.new('BEZIER')
            spline.bezier_points.add(len(pts) - 1)
            for i, p in enumerate(pts):
                cx = max(-8800.0, min(8800.0, p[0]))
                cy = max(-8800.0, min(8800.0, p[1]))
                spline.bezier_points[i].co = (cx, cy, p[2])
                spline.bezier_points[i].handle_left_type = 'AUTO'
                spline.bezier_points[i].handle_right_type = 'AUTO'

        # 谷
        for idx, pts in enumerate(valleys):
            if len(pts) < 2: continue
            curve = bpy.data.curves.new(f"ValleyPath_AI_{idx}", 'CURVE')
            curve.dimensions = '3D'
            curve.twist_mode = 'Z_UP'
            obj = bpy.data.objects.new(f"ValleyPath_AI_{idx}", curve)
            valley_col.objects.link(obj)
            spline = curve.splines.new('BEZIER')
            spline.bezier_points.add(len(pts) - 1)
            for i, p in enumerate(pts):
                cx = max(-8800.0, min(8800.0, p[0]))
                cy = max(-8800.0, min(8800.0, p[1]))
                spline.bezier_points[i].co = (cx, cy, p[2])
                spline.bezier_points[i].handle_left_type = 'AUTO'
                spline.bezier_points[i].handle_right_type = 'AUTO'


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
