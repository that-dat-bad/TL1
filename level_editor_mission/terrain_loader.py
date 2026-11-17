# -*- coding: utf-8 -*-
"""
Mission Editor - 40km x 40km 全地形チャンク高速結合ローダー＆対地高度スナップ機構
Resources/terrains/demo/chunks_info.json の全100チャンクを高速結合メッシュとして一括ロードし、レイキャスト接地を提供します。
"""

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
import bpy
import bmesh
from bpy.types import Context, Object, Scene
from mathutils import Matrix, Vector

from .constants import (
    CollectionNames,
    ColorPalette,
    EnemyDefaults,
    EntityRoles,
    MathConstants,
    PathConstants,
    TerrainDefaults,
    Zadanie00MarkerKinds,
)
from .mesh_factory import CollectionHelper, EntityMeshFactory
from .properties import RepoPathResolver


class TerrainChunkLoader:
    """40km x 40km 全地形チャンクの一括結合インポートとレイキャスト高度スナップを担うクラス"""

    TERRAIN_MAT_NAME = "Mission_Mat_TerrainSlate"
    CHUNK_OBJ_PREFIX = "Terrain_"

    @classmethod
    def load_chunks_for_mode(cls, context: Context, terrain_info_path: Optional[str] = None) -> Tuple[int, int, str]:
        """
        ゲーム側指定（未指定時は PathConstants.TERRAIN_INFO_REL_PATH）から全地形チャンクを読み込み、
        00_Terrain コレクション内の単一結合メッシュ (Terrain_FullMap) として構築する。
        """
        scene = context.scene
        if terrain_info_path:
            p = Path(terrain_info_path)
            info_path = p if p.is_absolute() else RepoPathResolver.resolve_path(scene, terrain_info_path)
            terrain_dir = info_path.parent
        else:
            info_path = RepoPathResolver.resolve_path(scene, PathConstants.TERRAIN_INFO_REL_PATH)
            terrain_dir = RepoPathResolver.resolve_path(scene, PathConstants.TERRAIN_DIR_REL)

        if not info_path.exists():
            return (
                MathConstants.ZERO_INT,
                MathConstants.ZERO_INT,
                f"chunks_info.json が見つかりません: {info_path}",
            )

        hierarchy = CollectionHelper.ensure_mission_hierarchy(scene)
        terrain_col = hierarchy[CollectionNames.TERRAIN]

        # 既に同一パスの結合済み全地形が存在する場合はスキップ（別地形なら差し替え）
        existing_full = terrain_col.objects.get(TerrainDefaults.FULL_TERRAIN_OBJECT_NAME)
        if existing_full is not None and existing_full.type == "MESH" and existing_full.data is not None:
            loaded_src = existing_full.get("tl1_mission_terrain_path", "")
            if len(existing_full.data.vertices) > MathConstants.ZERO_INT and (not loaded_src or loaded_src == str(info_path)):
                return (
                    MathConstants.ZERO_INT,
                    MathConstants.ONE_INT,
                    "全地形メッシュ (Terrain_FullMap) は既にロード済みです",
                )
            bpy.data.objects.remove(existing_full, do_unlink=True)

        with open(info_path, "r", encoding="utf-8") as fp:
            manifest = json.load(fp)

        all_entries = manifest.get("chunks", [])
        selected_entries = cls._filter_entries(scene, all_entries)
        terrain_mat = cls._get_or_create_terrain_material()

        combined_bm = bmesh.new()
        loaded_count = MathConstants.ZERO_INT
        transform_mat: Optional[Matrix] = None

        try:
            for entry in selected_entries:
                rel_file = entry.get("file", "")
                if not rel_file:
                    continue
                obj_filepath = terrain_dir / rel_file
                if not obj_filepath.exists():
                    continue

                imported_objs = cls._import_single_obj(obj_filepath)
                if not imported_objs:
                    continue

                for imp_obj in imported_objs:
                    if transform_mat is None:
                        transform_mat = imp_obj.matrix_world.copy()
                    if imp_obj.data is not None:
                        combined_bm.from_mesh(imp_obj.data)
                    mdata = imp_obj.data
                    bpy.data.objects.remove(imp_obj, do_unlink=True)
                    if mdata is not None and mdata.users == MathConstants.ZERO_INT:
                        bpy.data.meshes.remove(mdata)

                loaded_count += MathConstants.ONE_INT

            if loaded_count == MathConstants.ZERO_INT or len(combined_bm.verts) == MathConstants.ZERO_INT:
                return (MathConstants.ZERO_INT, MathConstants.ZERO_INT, "地形チャンクの読み込みに失敗しました")

            if transform_mat is not None:
                bmesh.ops.transform(combined_bm, matrix=transform_mat, verts=combined_bm.verts)

            cls.clear_terrain(scene)

            full_mesh = bpy.data.meshes.new(TerrainDefaults.FULL_TERRAIN_MESH_NAME)
            combined_bm.to_mesh(full_mesh)
            full_mesh.update()
        finally:
            combined_bm.free()

        full_obj = bpy.data.objects.new(TerrainDefaults.FULL_TERRAIN_OBJECT_NAME, full_mesh)
        full_obj["tl1_mission_terrain_path"] = str(info_path)
        CollectionHelper.link_exclusively(full_obj, terrain_col)
        cls._style_and_lock_terrain_object(full_obj, terrain_mat)
        context.view_layer.update()

        msg = f"全地形ロード完了: {loaded_count} チャンク結合 ({len(full_mesh.vertices)} 頂点)"
        return (loaded_count, MathConstants.ZERO_INT, msg)

    @classmethod
    def clear_terrain(cls, scene: Scene) -> int:
        """00_Terrain コレクション内の地形オブジェクトをすべて削除する"""
        terrain_col = bpy.data.collections.get(CollectionNames.TERRAIN)
        if terrain_col is None:
            return MathConstants.ZERO_INT

        removed = MathConstants.ZERO_INT
        for obj in list(terrain_col.objects):
            mesh_data = obj.data if obj.type == "MESH" else None
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh_data is not None and mesh_data.users == MathConstants.ZERO_INT:
                bpy.data.meshes.remove(mesh_data)
            removed += MathConstants.ONE_INT
        return removed

    @classmethod
    def snap_objects_to_terrain(cls, context: Context, targets: Iterable[Object]) -> int:
        """
        指定されたオブジェクト群（および CURVE の各制御点）を 00_Terrain メッシュへ垂直レイキャストして高度合わせする。
        地上目標・第4監視所は地面 (0m AGL) に接地し、航空機・経路・ゲートは snap_agl_offset を加算する。
        """
        scene = context.scene
        context.view_layer.update()
        terrain_objs = cls._get_loaded_terrain_meshes(scene)
        if not terrain_objs:
            return MathConstants.ZERO_INT

        air_agl = scene.mission_settings.snap_agl_offset
        snapped_count = MathConstants.ZERO_INT

        for obj in targets:
            if obj in terrain_objs:
                continue

            role = obj.mission_obj.entity_role if hasattr(obj, "mission_obj") else EntityRoles.NONE

            # ウェイポイント経路 (CURVE) の場合は全スプライン制御点を個別に地形追従スナップ
            if obj.type == "CURVE" and obj.data is not None and role == EntityRoles.WAYPOINT_PATH:
                mw = obj.matrix_world
                mw_inv = mw.inverted_safe()
                point_hit = False
                for spline in obj.data.splines:
                    for pt in spline.points:
                        world_pt = mw @ Vector((pt.co.x, pt.co.y, pt.co.z))
                        ground_z = cls.sample_terrain_height(terrain_objs, world_pt.x, world_pt.y)
                        if ground_z is not None:
                            world_pt.z = ground_z + air_agl
                            local_pt = mw_inv @ world_pt
                            pt.co = (
                                local_pt.x,
                                local_pt.y,
                                local_pt.z,
                                EnemyDefaults.SPLINE_CO_HOMOGENEOUS_W,
                            )
                            point_hit = True
                if point_hit:
                    snapped_count += MathConstants.ONE_INT
                continue

            # 通常オブジェクト（機体・地上目標・監視所・目標・トリガー）
            ground_z = cls.sample_terrain_height(terrain_objs, obj.location.x, obj.location.y)
            if ground_z is None:
                continue

            agl = cls._resolve_object_agl(obj, air_agl)
            obj.location.z = ground_z + agl
            snapped_count += MathConstants.ONE_INT

        return snapped_count

    @classmethod
    def sample_terrain_height(cls, terrain_objs: List[Object], world_x: float, world_y: float) -> Optional[float]:
        """指定された Blender ワールド (X, Y) 座標直下の最高地形 Z 座標を返す（格子境界エッジ抜け対策込み）"""
        hit_z = cls._raycast_terrain_vertical(terrain_objs, world_x, world_y)
        if hit_z is not None:
            return hit_z
        return cls._raycast_terrain_vertical(
            terrain_objs,
            world_x + MathConstants.EPSILON,
            world_y + MathConstants.EPSILON,
        )

    @staticmethod
    def _raycast_terrain_vertical(terrain_objs: List[Object], world_x: float, world_y: float) -> Optional[float]:
        ray_origin_world = Vector((world_x, world_y, TerrainDefaults.RAYCAST_START_Z))
        ray_target_world = Vector(
            (world_x, world_y, TerrainDefaults.RAYCAST_START_Z - TerrainDefaults.RAYCAST_MAX_DIST)
        )

        best_z: Optional[float] = None
        for t_obj in terrain_objs:
            if t_obj.type != "MESH" or t_obj.data is None:
                continue
            inv = t_obj.matrix_world.inverted_safe()
            local_origin = inv @ ray_origin_world
            local_target = inv @ ray_target_world
            local_vec = local_target - local_origin
            max_dist = local_vec.length
            if max_dist <= MathConstants.EPSILON:
                continue
            local_dir = local_vec.normalized()
            hit, hit_loc_local, _hit_norm, _face_idx = t_obj.ray_cast(
                local_origin, local_dir, distance=max_dist
            )
            if hit:
                world_hit = t_obj.matrix_world @ hit_loc_local
                if best_z is None or world_hit.z > best_z:
                    best_z = world_hit.z

        return best_z

    @staticmethod
    def _resolve_object_agl(obj: Object, configured_air_agl: float) -> float:
        if not hasattr(obj, "mission_obj"):
            return configured_air_agl
        props = obj.mission_obj
        if props.entity_role == EntityRoles.GROUND_ENEMY:
            return TerrainDefaults.DEFAULT_SNAP_AGL_GROUND
        if (
            props.entity_role == EntityRoles.ZADANIE00_MARKER
            and props.z00_marker_kind == Zadanie00MarkerKinds.OUTPOST_04
        ):
            return TerrainDefaults.DEFAULT_SNAP_AGL_GROUND
        return configured_air_agl

    @staticmethod
    def _get_loaded_terrain_meshes(scene: Scene) -> List[Object]:
        terrain_col = bpy.data.collections.get(CollectionNames.TERRAIN)
        if terrain_col is not None:
            return [o for o in terrain_col.objects if o.type == "MESH"]
        return [o for o in scene.objects if o.type == "MESH" and o.name.startswith(TerrainChunkLoader.CHUNK_OBJ_PREFIX)]

    @classmethod
    def _filter_entries(cls, _scene: Scene, entries: List[Dict]) -> List[Dict]:
        # ミッションで使用する全地形を常に一括ロード
        return list(entries)

    @staticmethod
    def _import_single_obj(obj_filepath: Path) -> List[Object]:
        before = set(bpy.data.objects)
        filepath_str = str(obj_filepath)
        try:
            if hasattr(bpy.ops.wm, "obj_import"):
                bpy.ops.wm.obj_import(
                    filepath=filepath_str,
                    forward_axis="NEGATIVE_Z",
                    up_axis="Y",
                )
            elif hasattr(bpy.ops.import_scene, "obj"):
                bpy.ops.import_scene.obj(
                    filepath=filepath_str,
                    axis_forward="-Z",
                    axis_up="Y",
                )
        except Exception as exc:
            print(f"[Mission Editor] OBJ import failed ({filepath_str}): {exc}")
            return []

        return [o for o in bpy.data.objects if o not in before and o.type == "MESH"]

    @classmethod
    def _get_or_create_terrain_material(cls):
        mat = EntityMeshFactory.get_or_create_material(cls.TERRAIN_MAT_NAME, ColorPalette.TERRAIN_SLATE)
        if mat.use_nodes and mat.node_tree:
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf is not None and "Roughness" in bsdf.inputs:
                bsdf.inputs["Roughness"].default_value = ColorPalette.MATERIAL_ROUGHNESS_TERRAIN
                if "Metallic" in bsdf.inputs:
                    bsdf.inputs["Metallic"].default_value = MathConstants.ZERO
        return mat

    @staticmethod
    def _style_and_lock_terrain_object(mesh_obj: Object, terrain_mat) -> None:
        mesh_obj.color = ColorPalette.TERRAIN_SLATE
        if mesh_obj.data is not None:
            mesh_obj.data.materials.clear()
            mesh_obj.data.materials.append(terrain_mat)
        # 誤ドラッグ防止のためビューポート選択のみロック（レイキャストと表示は維持）
        mesh_obj.hide_select = True
