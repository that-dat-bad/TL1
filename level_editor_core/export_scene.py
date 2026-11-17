import bpy
import bpy_extras
import json
import math
import os
import mathutils
import subprocess
import sys

# オペレータ シーン出力
class MYADDON_OT_export_scene(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    bl_idname = "myaddon.myaddon_ot_export_scene"
    bl_label = "シーン出力"
    bl_description = "シーン情報をエクスポートします"
    filename_ext = ".json"

    def execute(self, context):
        print("シーン情報をexportします")
        self.export_json()
        print("シーン情報をexportしました")
        self.report({'INFO'}, "シーン情報をexportしました")
        return {'FINISHED'}

    def parse_scene_recursive(self, file, object, level):
        """シーン解析用再帰関数"""
        
        # 深さ分インデントする（タブを挿入）
        indent = ''
        for i in range(level):
            indent += "\t"

        # オブジェクト名書き込み
        self.write_and_print(file, indent + object.type + " - " + object.name)
        
        trans, rot, scale = object.matrix_local.decompose()
        # 回転を Quternion から Euler （3軸での回転角）に変換
        rot = rot.to_euler()
        # ラジアンから度数法に変換
        rot.x = math.degrees(rot.x)
        rot.y = math.degrees(rot.y)
        rot.z = math.degrees(rot.z)
        
        #トランスフォーム情報を表示
        self.write_and_print(file, indent + "T %f %f %f" % (trans.x, trans.y, trans.z) )
        self.write_and_print(file, indent + "R %f %f %f" % (rot.x, rot.y, rot.z) )
        self.write_and_print(file, indent + "S %f %f %f" % (scale.x, scale.y, scale.z) )
        #カスタムプロパティ 'file_name'
        if "file_name" in object:
            self.write_and_print(file, indent + "N %s" % object["file_name"])
        self.write_and_print(file, indent + 'END')
        self.write_and_print(file, '')

        # 子ノードへ進む（深さが1上がる）
        for child in object.children:
            self.parse_scene_recursive(file, child, level + 1)

    def parse_scene_recursive_json(self,data_parent,object,level):
        #シーンのオブジェクト一個分のjsonオブジェクト生成
        json_object = dict()
        #オブジェクト種類
        json_object["type"] = object.type
        #オブジェクト名
        json_object["name"] = object.name
        
        #オブジェクトのローカルトランスフォームから
        #平行移動、回転、スケールを抽出
        trans , rot , scale =object.matrix_local.decompose()
        #回転を Quaternion から Euler （3軸での回転角）に変換
        rot = rot.to_euler()
        # ラジアンから度数法に変換
        rot.x = math.degrees(rot.x)
        rot.y = math.degrees(rot.y)
        rot.z = math.degrees(rot.z)

        #トランスフォーム情報をディクショナリに登録
        transform=dict()
        transform["location"] = [trans.x,trans.y,trans.z]
        transform["rotation"] = [rot.x,rot.y,rot.z]
        transform["scale"] = [scale.x,scale.y,scale.z]
        #まとめて一個分のjsonオブジェクトに登録
        json_object["transform"]=transform
        
        #カスタムプロパティ'無効オプション'
        if "disabled" in object:
            json_object["disabled"] = object["disabled"]

        #カスタムプロパティ'file_name'
        if "file_name" in object:
            json_object["file_name"] = object["file_name"]
        
        #カスタムプロパティ'collider'
        if "collider" in object:
            collider=dict()
            collider["type"] = object["collider"]
            collider["center"]=object["collider_center"].to_list()
            collider["size"]=object["collider_size"].to_list()
            json_object["collider"]=collider



        #一個分のjsonオブジェクトを親オブジェクトに登録
        data_parent.append(json_object)

        #子ノードがあれば
        if len(object.children) >0:
            #子ノードリストを作成
            json_object["children"]=list()
            #子ノードへ進む
            for child in object.children:
                self.parse_scene_recursive_json(json_object["children"],child,level+1)

    def export(self):
        """ファイル出力"""
        print("シーン情報をファイルに出力...%r" % self.filepath)

        # 保存先ディレクトリが存在しない場合は作成する
        dirname = os.path.dirname(self.filepath)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        # ファイルをテキスト形式で開く
        with open(self.filepath, 'w', encoding='utf-8') as file:
            file.write("SCENE\n")
            
            # シーン内の全オブジェクトについて
            for object in bpy.context.scene.objects:
                
                # 親オブジェクトがあるものはスキップ（代わりに親から呼び出すから）
                if (object.parent):
                    continue
                
                # シーン直下のオブジェクトをルートノード（深さ0）とし、再帰関数で走査
                self.parse_scene_recursive(file, object, 0)
    
    def export_json(self):
        """JSON形式でファイルに出力"""

        #保存する情報をまとめるdict
        json_object_root=dict()

        #ノード名
        json_object_root["name"] = "scene"
        #オブジェクトリストを作成
        json_object_root["objects"]=list()
        
        #シーン内の全オブジェクトについて
        for object in bpy.context.scene.objects:
            #親オブジェクトがあるものはスキップ(代わりに親から呼び出すから)
            if (object.parent):
                continue

            # シーン直下のオブジェクトをルートノード（深さ0）とし、再帰関数で走査
            self.parse_scene_recursive_json(json_object_root["objects"], object, 0)

        #オブジェクトをJSON文字列にエンコード
        json_text =json.dumps(json_object_root,ensure_ascii=False,cls=json.JSONEncoder,indent=4)
        #コンソールに表示してみる
        print(json_text)

        #ファイルをテキスト形式で書き出し用にオープン
        #スコープを抜けると自動的にクローズされる
        with open(self.filepath, "wt",encoding="utf-8") as file:
            #ファイルに文字列を書き込む
            file.write(json_text)

    def write_and_print(self, file, text_str):
        print(text_str)
        file.write(text_str)
        file.write("\n")


# オペレータ チャンクエクスポート
class MYADDON_OT_export_chunks(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
    bl_idname = "myaddon.myaddon_ot_export_chunks"
    bl_label = "チャンクエクスポート (OBJ)"
    bl_description = "メッシュを指定サイズのチャンクに分割してOBJエクスポートします"
    filename_ext = ""

    # チャンクサイズ（従来の500mから荒くした2000mをデフォルトに設定）
    chunk_size: bpy.props.FloatProperty(
        name="チャンクサイズ (m)",
        description="1チャンクの一辺の長さ (m)。従来の500mから荒くした2000m推奨",
        default=2000.0,
        min=100.0,
        max=40000.0,
    ) # type: ignore

    export_lod: bpy.props.BoolProperty(
        name="LODを出力",
        description="LOD0〜LOD3のポリゴン削減モデルを生成して出力するかどうか",
        default=True,
    ) # type: ignore

    use_heightmap_chunks: bpy.props.BoolProperty(
        name="ハイトマップからシームレス分割",
        description="AIハイトマップが存在する場合、境界隙間なし・高速LOD0-3・ベイクテクスチャ付きで直接チャンク出力します",
        default=True,
    ) # type: ignore

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "chunk_size")
        layout.prop(self, "export_lod")
        layout.prop(self, "use_heightmap_chunks")

    def execute(self, context):
        print(f"チャンク並行エクスポートを開始します (サイズ: {self.chunk_size}m, LOD: {self.export_lod})")
        
        export_dir = os.path.dirname(self.filepath)
        if not export_dir:
            export_dir = self.filepath
            
        os.makedirs(export_dir, exist_ok=True)

        # ハイトマップキャッシュが存在する場合はシームレス高速出力を優先
        terrain_obj = bpy.data.objects.get("Terrain")
        if self.use_heightmap_chunks and terrain_obj and "tl1_heightmap_dir" in terrain_obj:
            hm_dir = terrain_obj["tl1_heightmap_dir"]
            hm_path = os.path.join(hm_dir, "heightmap.npy")
            meta_path = os.path.join(hm_dir, "heightmap_meta.json")
            if os.path.exists(hm_path) and os.path.exists(meta_path):
                count = self._export_seamless_heightmap_chunks(hm_dir, export_dir)
                self.report({'INFO'}, f"シームレスチャンク出力完了: {count}チャンク")
                return {'FINISHED'}
        
        # 1. チャンクの全体範囲を決定
        mesh_objs = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH' and obj.visible_get()]
        if not mesh_objs:
            self.report({'WARNING'}, "エクスポートするメッシュがありません")
            return {'CANCELLED'}
            
        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')
        
        for obj in mesh_objs:
            for corner in obj.bound_box:
                world_corner = obj.matrix_world @ mathutils.Vector(corner)
                if world_corner.x < min_x: min_x = world_corner.x
                if world_corner.x > max_x: max_x = world_corner.x
                if world_corner.y < min_y: min_y = world_corner.y
                if world_corner.y > max_y: max_y = world_corner.y
                
        if min_x == float('inf'):
            min_x = 0; max_x = 0; min_y = 0; max_y = 0
            
        start_cx = math.floor(min_x / self.chunk_size)
        end_cx = math.floor(max_x / self.chunk_size)
        start_cy = math.floor(min_y / self.chunk_size)
        end_cy = math.floor(max_y / self.chunk_size)
        
        # 2. チャンク一覧を作成し、バッチ分割
        all_chunks = []
        for cx in range(start_cx, end_cx + 1):
            for cy in range(start_cy, end_cy + 1):
                all_chunks.append((cx, cy))
                
        num_cores = os.cpu_count() or 4
        batches = [[] for _ in range(num_cores)]
        for i, chunk in enumerate(all_chunks):
            batches[i % num_cores].append(chunk)
            
        batches = [b for b in batches if b] # 空のバッチを削除
        
        # 3. 現在のシーンをテンポラリに保存
        tmp_blend = os.path.join(export_dir, "temp_export.blend")
        bpy.ops.wm.save_as_mainfile(filepath=tmp_blend, copy=True)
        
        # 4. ワーカー用スクリプトを生成
        worker_script_path = os.path.join(export_dir, "worker_export.py")
        self.write_worker_script(worker_script_path)
        
        # 5. 各バッチのJSON保存と並列プロセス起動
        processes = []
        batch_files = []
        
        for i, batch in enumerate(batches):
            batch_json = os.path.join(export_dir, f"batch_{i}.json")
            with open(batch_json, 'w') as f:
                json.dump(batch, f)
            batch_files.append(batch_json)
            
            cmd = [
                bpy.app.binary_path, 
                "-b", tmp_blend, 
                "-P", worker_script_path, 
                "--", 
                batch_json, 
                export_dir, 
                str(self.chunk_size), 
                str(start_cx), 
                str(start_cy),
                str(self.export_lod)
            ]
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            processes.append(p)
            
        # 6. プロセスの完了を待機
        for p in processes:
            p.wait()
            
        # 7. 結果JSONのマージ
        all_chunk_info = []
        for bf in batch_files:
            res_json = bf.replace(".json", "_result.json")
            if os.path.exists(res_json):
                with open(res_json, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    all_chunk_info.extend(data.get("chunks", []))
                os.remove(res_json)
            os.remove(bf) # バッチファイル削除
            
        final_json = os.path.join(export_dir, "chunks_info.json")
        with open(final_json, 'w', encoding='utf-8') as f:
            json.dump({"chunks": all_chunk_info}, f, ensure_ascii=False, indent=4)
            
        # 8. クリーンアップ
        if os.path.exists(tmp_blend):
            os.remove(tmp_blend)
        if os.path.exists(worker_script_path):
            os.remove(worker_script_path)
            
        self.report({'INFO'}, f"チャンク分割エクスポート完了: {len(all_chunk_info)}チャンク処理")
        return {'FINISHED'}
        
    def write_worker_script(self, path):
        code = """import bpy
import sys
import os
import json

argv = sys.argv
if "--" not in argv:
    sys.exit(1)
    
argv = argv[argv.index("--") + 1:]
batch_json = argv[0]
export_dir = argv[1]
chunk_size = float(argv[2])
start_cx = int(argv[3])
start_cy = int(argv[4])
export_lod = (argv[5].lower() == 'true') if len(argv) > 5 else False

with open(batch_json, 'r') as f:
    chunks = json.load(f)

mesh_objs = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH' and obj.visible_get()]

group = bpy.data.node_groups.new("TempChunkMask", 'GeometryNodeTree')
if hasattr(group, "interface"):
    group.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    group.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
else:
    group.inputs.new('NodeSocketGeometry', 'Geometry')
    group.outputs.new('NodeSocketGeometry', 'Geometry')
    
nodes = group.nodes
links = group.links
node_in = nodes.new('NodeGroupInput')
node_out = nodes.new('NodeGroupOutput')
pos = nodes.new('GeometryNodeInputPosition')
sep = nodes.new('ShaderNodeSeparateXYZ')
links.new(pos.outputs[0], sep.inputs[0])

cmp_x_min = nodes.new('ShaderNodeMath')
cmp_x_min.operation = 'GREATER_THAN'
links.new(sep.outputs['X'], cmp_x_min.inputs[0])
cmp_x_max = nodes.new('ShaderNodeMath')
cmp_x_max.operation = 'LESS_THAN'
links.new(sep.outputs['X'], cmp_x_max.inputs[0])
cmp_y_min = nodes.new('ShaderNodeMath')
cmp_y_min.operation = 'GREATER_THAN'
links.new(sep.outputs['Y'], cmp_y_min.inputs[0])
cmp_y_max = nodes.new('ShaderNodeMath')
cmp_y_max.operation = 'LESS_THAN'
links.new(sep.outputs['Y'], cmp_y_max.inputs[0])

and1 = nodes.new('ShaderNodeMath')
and1.operation = 'MULTIPLY'
links.new(cmp_x_min.outputs[0], and1.inputs[0])
links.new(cmp_x_max.outputs[0], and1.inputs[1])

and2 = nodes.new('ShaderNodeMath')
and2.operation = 'MULTIPLY'
links.new(cmp_y_min.outputs[0], and2.inputs[0])
links.new(cmp_y_max.outputs[0], and2.inputs[1])

and3 = nodes.new('ShaderNodeMath')
and3.operation = 'MULTIPLY'
links.new(and1.outputs[0], and3.inputs[0])
links.new(and2.outputs[0], and3.inputs[1])

not_node = nodes.new('ShaderNodeMath')
not_node.operation = 'SUBTRACT'
not_node.inputs[0].default_value = 1.0
links.new(and3.outputs[0], not_node.inputs[1])

delete_geo = nodes.new('GeometryNodeDeleteGeometry')
delete_geo.domain = 'FACE'
links.new(node_in.outputs[0], delete_geo.inputs['Geometry'])
links.new(not_node.outputs[0], delete_geo.inputs['Selection'])
links.new(delete_geo.outputs[0], node_out.inputs[0])

modifiers = []
lod_modifiers = []
for obj in mesh_objs:
    if export_lod:
        lod_mod = obj.modifiers.new(name="TempLOD", type='DECIMATE')
        lod_modifiers.append((obj, lod_mod))
    mod = obj.modifiers.new(name="TempChunkSplitter", type='NODES')
    mod.node_group = group
    modifiers.append((obj, mod))
    
depsgraph = bpy.context.evaluated_depsgraph_get()

chunk_info_list = []
if export_lod:
    lods_config = [(0, 1.0), (1, 0.5), (2, 0.2), (3, 0.05)]
else:
    lods_config = [(0, 1.0)]

for cx, cy in chunks:
    chunk_min_x = cx * chunk_size
    chunk_max_x = (cx + 1) * chunk_size
    chunk_min_y = cy * chunk_size
    chunk_max_y = (cy + 1) * chunk_size
    
    normalized_x = cx - start_cx
    normalized_y = cy - start_cy
    
    cmp_x_min.inputs[1].default_value = chunk_min_x
    cmp_x_max.inputs[1].default_value = chunk_max_x
    cmp_y_min.inputs[1].default_value = chunk_min_y
    cmp_y_max.inputs[1].default_value = chunk_max_y
    
    bpy.context.view_layer.update()
    
    is_empty = True
    for obj in mesh_objs:
        eval_obj = obj.evaluated_get(depsgraph)
        if eval_obj.data and len(eval_obj.data.vertices) > 0:
            if len(eval_obj.data.polygons) > 0:
                is_empty = False
                break
                
    if is_empty: continue
    
    bpy.ops.object.select_all(action='DESELECT')
    for obj in mesh_objs: obj.select_set(True)
    
    chunk_files = []
    for lod_idx, lod_ratio in lods_config:
        for obj, lod_mod in lod_modifiers:
            lod_mod.ratio = lod_ratio
            lod_mod.show_viewport = (lod_ratio < 1.0)
            lod_mod.show_render = (lod_ratio < 1.0)
            
        bpy.context.view_layer.update()
        
        out_path = os.path.join(export_dir, f"chunk{normalized_x}-{normalized_y}_LOD{lod_idx}.obj")
        chunk_files.append(os.path.basename(out_path))
        
        if hasattr(bpy.ops.wm, "obj_export"):
            bpy.ops.wm.obj_export(filepath=out_path, export_selected_objects=True, export_triangulated_mesh=False, export_materials=True, apply_modifiers=True)
        else:
            bpy.ops.export_scene.obj(filepath=out_path, use_selection=True, use_mesh_modifiers=True, use_materials=True, use_triangles=False)
            
    chunk_info_list.append({
        "grid_x": normalized_x, "grid_y": normalized_y,
        "world_cx": cx, "world_cy": cy,
        "min_x": chunk_min_x, "max_x": chunk_max_x,
        "min_y": chunk_min_y, "max_y": chunk_max_y,
        "center": [(chunk_min_x + chunk_max_x) / 2.0, (chunk_min_y + chunk_max_y) / 2.0, 0.0],
        "lod_files": chunk_files,
        "file": chunk_files[0] if chunk_files else ""
    })

res_json = batch_json.replace(".json", "_result.json")
with open(res_json, 'w', encoding='utf-8') as f:
    json.dump({"chunks": chunk_info_list}, f, ensure_ascii=False)
"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write(code)

    def _export_seamless_heightmap_chunks(self, hm_dir, export_dir):
        """
        NumPyハイトマップから境界頂点・法線を厳密共有したシームレスチャンクOBJ＋MTL＋LOD0〜3を出力する。
        """
        import shutil
        import numpy as np  # type: ignore

        heightmap = np.load(os.path.join(hm_dir, "heightmap.npy"))
        with open(os.path.join(hm_dir, "heightmap_meta.json"), "r", encoding="utf-8") as f:
            meta = json.load(f)

        res_y, res_x = heightmap.shape
        size_x = float(meta.get("terrain_size_x", 40000.0))
        size_y = float(meta.get("terrain_size_y", size_x))
        half_x = size_x * 0.5
        half_y = size_y * 0.5
        cell_x = size_x / float(res_x - 1)
        cell_y = size_y / float(res_y - 1)

        # 全体ハイトマップ上で法線を一括計算（チャンク境界での法線継ぎ目をゼロにする）
        gy, gx = np.gradient(heightmap.astype(np.float32), cell_y, cell_x)
        nx_all = -gx
        ny_all = -gy
        nz_all = np.ones_like(gx, dtype=np.float32)
        inv_len = 1.0 / np.sqrt(nx_all * nx_all + ny_all * ny_all + nz_all * nz_all)
        nx_all *= inv_len
        ny_all *= inv_len
        nz_all *= inv_len

        # ベイクテクスチャを出力先へコピーし、共通 MTL を生成
        for tex_name in ("terrain_albedo.png", "terrain_normal.png", "terrain_splat.png", "shore_sdf.png"):
            src_tex = os.path.join(hm_dir, tex_name)
            if os.path.exists(src_tex):
                shutil.copy2(src_tex, os.path.join(export_dir, tex_name))

        mtl_name = "terrain_chunks.mtl"
        mtl_path = os.path.join(export_dir, mtl_name)
        with open(mtl_path, "w", encoding="utf-8") as mf:
            mf.write("newmtl TerrainBakedMat\n")
            mf.write("Ka 0.15 0.15 0.15\n")
            mf.write("Kd 1.0 1.0 1.0\n")
            mf.write("Ks 0.05 0.05 0.05\n")
            mf.write("Ns 16.0\n")
            if os.path.exists(os.path.join(export_dir, "terrain_albedo.png")):
                mf.write("map_Kd terrain_albedo.png\n")
            if os.path.exists(os.path.join(export_dir, "terrain_normal.png")):
                mf.write("map_Bump terrain_normal.png\n")

        start_cx = math.floor(-half_x / self.chunk_size)
        end_cx = math.ceil(half_x / self.chunk_size) - 1
        start_cy = math.floor(-half_y / self.chunk_size)
        end_cy = math.ceil(half_y / self.chunk_size) - 1

        lod_steps = [(0, 1), (1, 2), (2, 4), (3, 8)] if self.export_lod else [(0, 1)]
        all_chunk_info = []

        for cx in range(start_cx, end_cx + 1):
            for cy in range(start_cy, end_cy + 1):
                c_min_x = cx * self.chunk_size
                c_max_x = (cx + 1) * self.chunk_size
                c_min_y = cy * self.chunk_size
                c_max_y = (cy + 1) * self.chunk_size

                ix0 = max(0, int(round((c_min_x + half_x) / cell_x)))
                ix1 = min(res_x - 1, int(round((c_max_x + half_x) / cell_x)))
                iy0 = max(0, int(round((c_min_y + half_y) / cell_y)))
                iy1 = min(res_y - 1, int(round((c_max_y + half_y) / cell_y)))
                if ix1 <= ix0 or iy1 <= iy0:
                    continue

                norm_x = cx - start_cx
                norm_y = cy - start_cy
                chunk_files = []

                for lod_idx, step in lod_steps:
                    xs_idx = np.arange(ix0, ix1 + 1, step, dtype=np.int32)
                    if xs_idx[-1] != ix1:
                        xs_idx = np.append(xs_idx, ix1)
                    ys_idx = np.arange(iy0, iy1 + 1, step, dtype=np.int32)
                    if ys_idx[-1] != iy1:
                        ys_idx = np.append(ys_idx, iy1)

                    sub_h = heightmap[np.ix_(ys_idx, xs_idx)]
                    sub_nx = nx_all[np.ix_(ys_idx, xs_idx)]
                    sub_ny = ny_all[np.ix_(ys_idx, xs_idx)]
                    sub_nz = nz_all[np.ix_(ys_idx, xs_idx)]

                    wx = -half_x + xs_idx.astype(np.float32) * cell_x
                    wy = -half_y + ys_idx.astype(np.float32) * cell_y
                    gx_m, gy_m = np.meshgrid(wx, wy, indexing="xy")

                    u_m = (gx_m + half_x) / max(size_x, 1.0)
                    v_m = (gy_m + half_y) / max(size_y, 1.0)

                    ny_c, nx_c = sub_h.shape
                    obj_name = f"chunk{norm_x}-{norm_y}_LOD{lod_idx}.obj"
                    chunk_files.append(obj_name)
                    obj_path = os.path.join(export_dir, obj_name)

                    with open(obj_path, "w", encoding="utf-8") as of:
                        of.write(f"mtllib {mtl_name}\n")
                        of.write(f"o chunk_{norm_x}_{norm_y}_LOD{lod_idx}\n")
                        of.write("usemtl TerrainBakedMat\n")

                        # 頂点 (v), UV (vt), 法線 (vn) - Blender標準obj_exportと同一の Y-up (X, Z, -Y) に変換
                        vx_f = gx_m.ravel()
                        vy_f = sub_h.ravel()
                        vz_f = -gy_m.ravel()
                        u_f = u_m.ravel()
                        v_f = v_m.ravel()
                        nx_f = sub_nx.ravel()
                        ny_f = sub_nz.ravel()
                        nz_f = -sub_ny.ravel()

                        v_lines = [f"v {vx_f[i]:.3f} {vy_f[i]:.3f} {vz_f[i]:.3f}\n" for i in range(vx_f.size)]
                        vt_lines = [f"vt {u_f[i]:.5f} {v_f[i]:.5f}\n" for i in range(u_f.size)]
                        vn_lines = [f"vn {nx_f[i]:.4f} {ny_f[i]:.4f} {nz_f[i]:.4f}\n" for i in range(nx_f.size)]
                        of.writelines(v_lines)
                        of.writelines(vt_lines)
                        of.writelines(vn_lines)

                        f_lines = []
                        for r in range(ny_c - 1):
                            row_base = r * nx_c + 1
                            next_base = (r + 1) * nx_c + 1
                            for c in range(nx_c - 1):
                                i0 = row_base + c
                                i1 = i0 + 1
                                i2 = next_base + c + 1
                                i3 = next_base + c
                                f_lines.append(
                                    f"f {i0}/{i0}/{i0} {i1}/{i1}/{i1} {i2}/{i2}/{i2} {i3}/{i3}/{i3}\n"
                                )
                        of.writelines(f_lines)

                all_chunk_info.append({
                    "grid_x": norm_x,
                    "grid_y": norm_y,
                    "world_cx": cx,
                    "world_cy": cy,
                    "min_x": c_min_x,
                    "max_x": c_max_x,
                    "min_y": c_min_y,
                    "max_y": c_max_y,
                    "center": [(c_min_x + c_max_x) / 2.0, (c_min_y + c_max_y) / 2.0, 0.0],
                    "lod_files": chunk_files,
                    "file": chunk_files[0] if chunk_files else "",
                    "textures": {
                        "albedo": "terrain_albedo.png",
                        "normal": "terrain_normal.png",
                        "splat": "terrain_splat.png",
                    },
                })

        # 水面メッシュ (RiverMesh_AI / WaterPlane_AI) の個別エクスポート
        def _export_single_obj(obj_name, out_filename):
            w_obj = bpy.data.objects.get(obj_name)
            if not w_obj or w_obj.type != 'MESH':
                return None
            out_p = os.path.join(export_dir, out_filename)
            bpy.ops.object.select_all(action='DESELECT')
            w_obj.select_set(True)
            if hasattr(bpy.ops.wm, "obj_export"):
                bpy.ops.wm.obj_export(filepath=out_p, export_selected_objects=True, export_triangulated_mesh=True, export_materials=True, apply_modifiers=True)
            else:
                bpy.ops.export_scene.obj(filepath=out_p, use_selection=True, use_mesh_modifiers=True, use_materials=True, use_triangles=True)
            return out_filename if os.path.exists(out_p) else None

        river_mesh_file = _export_single_obj("RiverMesh_AI", "river_mesh.obj")
        ocean_mesh_file = _export_single_obj("WaterPlane_AI", "ocean_plane.obj")
        if ocean_mesh_file and os.path.exists(os.path.join(export_dir, "shore_sdf.png")):
            ocean_mtl = os.path.join(export_dir, "ocean_plane.mtl")
            if os.path.exists(ocean_mtl):
                with open(ocean_mtl, "a", encoding="utf-8") as omf:
                    omf.write("\nmap_Kd shore_sdf.png\n")

        final_json = os.path.join(export_dir, "chunks_info.json")
        out_payload = {
            "chunks": all_chunk_info,
            "water_level": meta.get("water_level"),
            "has_ocean": bool(meta.get("has_ocean", False)),
            "shore_sdf": "shore_sdf.png" if os.path.exists(os.path.join(export_dir, "shore_sdf.png")) else None,
            "river_mesh": river_mesh_file,
            "ocean_mesh": ocean_mesh_file,
            "rivers": meta.get("rivers", []),
        }
        with open(final_json, "w", encoding="utf-8") as jf:
            json.dump(out_payload, jf, ensure_ascii=False, indent=4)

        return len(all_chunk_info)
