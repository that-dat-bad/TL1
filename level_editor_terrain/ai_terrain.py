# -*- coding: utf-8 -*-
import bpy  # type: ignore
import json
import urllib.request
import urllib.error
import textwrap

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
    bl_label = "AIによる地形自動生成 (Ollama)"
    bl_description = "Ollamaを使用して、テキストプロンプトから地形と道・山・谷を自動生成します"
    bl_options = {'REGISTER', 'UNDO'}

    prompt: bpy.props.StringProperty(
        name="プロンプト",
        description="どのような地形を作りたいか日本語で入力してください（自動で英語に翻訳されて処理されます）",
        default="中央を曲がりくねった道路が横断し、その北側と南側にそれぞれ大きな山がある地形",
        maxlen=1024,
    ) # type: ignore

    model_name: bpy.props.EnumProperty(
        name="モデル",
        description="Ollamaで使用するモデルを選択",
        items=get_ollama_models
    ) # type: ignore

    _timer = None
    _thread = None
    _result = None
    _error = None

    def invoke(self, context, event):
        global _cached_models
        _cached_models = None
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "model_name")
        layout.prop(self, "prompt", text="指示")
        layout.label(text="※ 生成には数十秒かかる場合があります。バックグラウンドで処理されます。", icon='INFO')

    def execute(self, context):
        import threading
        self._result = None
        self._error = None
        
        self._thread = threading.Thread(target=self.run_ollama_request, args=(self.model_name, self.prompt))
        self._thread.start()
        
        self._timer = context.window_manager.event_timer_add(0.5, window=context.window)
        context.window_manager.modal_handler_add(self)
        
        self.report({'INFO'}, "AIにリクエストを送信中... しばらくお待ちください")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'TIMER':
            if not self._thread.is_alive():
                context.window_manager.event_timer_remove(self._timer)
                
                if self._error:
                    self.report({'ERROR'}, self._error)
                    return {'CANCELLED'}
                    
                if self._result:
                    self.generate_splines(context, self._result)
                    bpy.ops.myaddon.myaddon_ot_create_terrain()
                    
                    terrain_obj = bpy.data.objects.get("Terrain")
                    road_obj = bpy.data.objects.get("RoadPath_AI")
                    
                    if terrain_obj:
                        mod = terrain_obj.modifiers.get("TerrainGen")
                        if mod:
                            if 'Grid Size X' in mod:
                                mod['Grid Size X'] = self._result.get("terrain_size_x", 200.0)
                            if 'Grid Size Y' in mod:
                                mod['Grid Size Y'] = self._result.get("terrain_size_y", 200.0)
                            
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
                                
                            # --- Procedural City Generation (Step 2: BSP Building Lots) ---
                            if hasattr(self, '_generator') and self._generator:
                                try:
                                    lots = self._generator.generate_building_lots()
                                    if lots:
                                        self.spawn_buildings(context, lots, terrain_obj)
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
                                    # Blenderのバージョンによっては "Road Object" の名前でアクセス可能
                                    try:
                                        mod["Road Object"] = road_obj
                                    except:
                                        pass
                                        
                    self.report({'INFO'}, "AIによる地形生成が完了しました")
                    return {'FINISHED'}
                    
                return {'CANCELLED'}
        return {'PASS_THROUGH'}

    def spawn_buildings(self, context, lots, terrain_obj):
        import bmesh
        import mathutils
        
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
            z_min = hit_z - 2.0 # 地面に少し埋め込む
            z_max = hit_z + z_height
            
            hw = w / 2.0
            hh = h / 2.0
            
            v1 = bm.verts.new((x - hw, y - hh, z_min))
            v2 = bm.verts.new((x + hw, y - hh, z_min))
            v3 = bm.verts.new((x + hw, y + hh, z_min))
            v4 = bm.verts.new((x - hw, y + hh, z_min))
            
            v5 = bm.verts.new((x - hw, y - hh, z_max))
            v6 = bm.verts.new((x + hw, y - hh, z_max))
            v7 = bm.verts.new((x + hw, y + hh, z_max))
            v8 = bm.verts.new((x - hw, y + hh, z_max))
            
            # 面の作成（法線が外を向くように順序指定）
            bm.faces.new((v1, v4, v3, v2)) # Bottom
            bm.faces.new((v5, v6, v7, v8)) # Top
            bm.faces.new((v1, v2, v6, v5)) # Front
            bm.faces.new((v2, v3, v7, v6)) # Right
            bm.faces.new((v3, v4, v8, v7)) # Back
            bm.faces.new((v4, v1, v5, v8)) # Left
            
        bm.to_mesh(mesh)
        bm.free()
        
        # マテリアル設定（モックアップ風）
        mat = bpy.data.materials.get("Building_Mockup")
        if not mat:
            mat = bpy.data.materials.new("Building_Mockup")
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                bsdf.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1.0)
                bsdf.inputs["Roughness"].default_value = 0.2
        obj.data.materials.append(mat)

    def project_road_to_terrain(self, context, road_obj, terrain_obj):
        import mathutils
        context.view_layer.update()
        depsgraph = context.evaluated_depsgraph_get()
        
        road_mat_inv = road_obj.matrix_world.inverted()
        
        # Raycastをより確実にするためScene全体のray_castを使用
        road_curve = road_obj.data
        for spline in road_curve.splines:
            points = spline.bezier_points if spline.type == 'BEZIER' else spline.points
            for pt in points:
                co = pt.co[:3] if spline.type == 'POLY' else pt.co
                co_world = road_obj.matrix_world @ mathutils.Vector(co)
                
                # Z軸上空から下に向けてレイキャスト
                origin_world = mathutils.Vector((co_world.x, co_world.y, 1000.0))
                dir_world = mathutils.Vector((0.0, 0.0, -1.0))
                
                # 複数回レイキャストしてTerrainに当たるまで探す（他のオブジェクトを貫通させる）
                hit = False
                current_origin = origin_world
                
                for _ in range(10): # 最大10回まで貫通
                    success, location, normal, index, obj, matrix = context.scene.ray_cast(depsgraph, current_origin, dir_world)
                    if success:
                        if obj and obj.name == terrain_obj.name:
                            hit_local_road = road_mat_inv @ location
                            if spline.type == 'POLY':
                                pt.co = (co[0], co[1], hit_local_road.z, pt.co[3])
                            else:
                                pt.co = (co[0], co[1], hit_local_road.z)
                            hit = True
                            break
                        else:
                            # 別のオブジェクトに当たった場合は、少し下から再度レイを飛ばす
                            current_origin = location + dir_world * 0.01
                    else:
                        break

    def run_ollama_request(self, model_name, prompt):
        url = "http://localhost:11434/api/generate"
        
        # --- 自動翻訳処理 ---
        print("--- 日本語プロンプトを英語に翻訳中 ---")
        trans_data = {
            "model": model_name,
            "prompt": f"Translate the following Japanese text to English. Output ONLY the English translation, no quotes, no explanations:\n{prompt}",
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
        
        system_prompt = textwrap.dedent("""\
            You are a terrain generation assistant for Blender.
            Output the placement of terrain elements (mountains, valleys, roads) based on the user's request in JSON format.
            Coordinate system: X (Left/Right), Y (Front/Back), Z (Height). Base Z is usually 0.
            
            [Output Format and Rules]
            - Output ONLY valid JSON. Do NOT include markdown formatting (like ```json), explanations, or conversational text.
            - To avoid unnatural straight lines, ensure the coordinates for roads and mountains are naturally curved or zig-zagged.
            - Provide about 4 to 6 control points per curve to express natural winding shapes.
            - If an element is not needed, provide an empty list [].
            
            {
              "terrain_size_x": 200.0,
              "terrain_size_y": 200.0,
              "mountains": [
                [[-40, 30, 0], [-15, 45, 0], [10, 25, 0], [35, 40, 0]]
              ],
              "valleys": [
                [[-20, -40, 0], [-5, -20, 0], [15, -35, 0], [40, -15, 0]]
              ],
              "roads": [
                [[-100, 10, 0], [-50, -20, 0], [0, 15, 0], [60, -10, 0], [100, 0, 0]]
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
        # 既存のコレクションを取得または作成
        mountain_col = self.get_or_create_collection(context, "Mountains")
        valley_col = self.get_or_create_collection(context, "Valleys")
        road_col = self.get_or_create_collection(context, "Roads")

        # 既存のAI生成オブジェクトをクリア(名前で判定)
        self.clear_ai_objects(mountain_col)
        self.clear_ai_objects(valley_col)
        self.clear_ai_objects(road_col)
        
        # またはcreate_terrain.pyの仕様に合わせて単一のRoadオブジェクトを作成
        roads = terrain_data.get("roads", [])
        
        # --- Procedural City Generation (Step 1: Road Growth) ---
        if roads:
            try:
                from level_editor_city.city_generator import ProceduralCityGenerator
                self._generator = ProceduralCityGenerator(
                    terrain_size_x=terrain_data.get("terrain_size_x", 200.0),
                    terrain_size_y=terrain_data.get("terrain_size_y", 200.0)
                )
                roads = self._generator.generate_road_network(roads)
            except Exception as e:
                print(f"Road network generation failed: {e}")
        # --------------------------------------------------------

        if roads:
            # 道路作成オペレーターを呼び出して、マテリアルやモディファイアが設定済みの道路オブジェクトを生成
            bpy.ops.myaddon.myaddon_ot_create_road_along_spline()
            road_obj = context.active_object
            road_obj.name = "RoadPath_AI"
            road_obj.data.name = "RoadPath_AI"
            
            # 現在のコレクションから外し、Roadsコレクションにリンクする
            for col in road_obj.users_collection:
                col.objects.unlink(road_obj)
            road_col.objects.link(road_obj)
            
            # デフォルトのスプラインをクリア
            road_curve = road_obj.data
            road_curve.splines.clear()
            
            for pts in roads:
                if len(pts) < 2: continue
                # 道路ジェネレータと相性の良いPOLY曲線を使用
                spline = road_curve.splines.new('POLY')
                spline.points.add(len(pts) - 1)
                for i, p in enumerate(pts):
                    spline.points[i].co = (p[0], p[1], p[2], 1.0)
                    spline.points[i].radius = 1.0

        # 山脈
        mountains = terrain_data.get("mountains", [])
        for idx, pts in enumerate(mountains):
            if len(pts) < 2: continue
            curve = bpy.data.curves.new(f"MountainPath_AI_{idx}", 'CURVE')
            curve.dimensions = '3D'
            obj = bpy.data.objects.new(f"MountainPath_AI_{idx}", curve)
            mountain_col.objects.link(obj)
            spline = curve.splines.new('BEZIER')
            spline.bezier_points.add(len(pts) - 1)
            for i, p in enumerate(pts):
                spline.bezier_points[i].co = (p[0], p[1], p[2])
                spline.bezier_points[i].handle_left_type = 'AUTO'
                spline.bezier_points[i].handle_right_type = 'AUTO'

        # 谷
        valleys = terrain_data.get("valleys", [])
        for idx, pts in enumerate(valleys):
            if len(pts) < 2: continue
            curve = bpy.data.curves.new(f"ValleyPath_AI_{idx}", 'CURVE')
            curve.dimensions = '3D'
            obj = bpy.data.objects.new(f"ValleyPath_AI_{idx}", curve)
            valley_col.objects.link(obj)
            spline = curve.splines.new('BEZIER')
            spline.bezier_points.add(len(pts) - 1)
            for i, p in enumerate(pts):
                spline.bezier_points[i].co = (p[0], p[1], p[2])
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
