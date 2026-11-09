# -*- coding: utf-8 -*-
"""
Mission Editor - 3Dギズモ＆実機モデルメッシュ生成ファクトリ
機体 (.gltf)・対空砲台・レーダー施設・装甲車両・監視塔・境界ゲートを色分けされた3Dオブジェクトとして生成します。
"""

import math
from pathlib import Path
from typing import Optional, Tuple
import bpy
import bmesh
from bpy.types import Collection, Material, Mesh, Object, Scene
from mathutils import Matrix

from .constants import (
    CollectionNames,
    ColorPalette,
    GizmoDimensions,
    GroundDefaults,
    MathConstants,
)
from .properties import RepoPathResolver


class CollectionHelper:
    """シーン内コレクション階層の整理・生成を担当するクラス"""

    @staticmethod
    def ensure_collection(
        scene: Scene,
        name: str,
        parent: Optional[Collection] = None,
        hide_viewport: bool = False,
    ) -> Collection:
        target_parent = parent if parent is not None else scene.collection
        col = bpy.data.collections.get(name)
        if col is None:
            col = bpy.data.collections.new(name)
        if col.name not in target_parent.children:
            target_parent.children.link(col)
        col.hide_viewport = hide_viewport
        return col

    @classmethod
    def ensure_mission_hierarchy(cls, scene: Scene) -> dict:
        root = cls.ensure_collection(scene, CollectionNames.ROOT, scene.collection)
        return {
            CollectionNames.ROOT: root,
            CollectionNames.TERRAIN: cls.ensure_collection(scene, CollectionNames.TERRAIN, root),
            CollectionNames.PLAYER_AND_ALLIES: cls.ensure_collection(scene, CollectionNames.PLAYER_AND_ALLIES, root),
            CollectionNames.WAYPOINT_ROUTES: cls.ensure_collection(scene, CollectionNames.WAYPOINT_ROUTES, root),
            CollectionNames.AIR_ENEMIES: cls.ensure_collection(scene, CollectionNames.AIR_ENEMIES, root),
            CollectionNames.GROUND_TARGETS: cls.ensure_collection(scene, CollectionNames.GROUND_TARGETS, root),
            CollectionNames.OBJECTIVES_AND_TRIGGERS: cls.ensure_collection(
                scene, CollectionNames.OBJECTIVES_AND_TRIGGERS, root
            ),
            CollectionNames.ZADANIE00_EVENTS: cls.ensure_collection(scene, CollectionNames.ZADANIE00_EVENTS, root),
        }

    @staticmethod
    def link_exclusively(obj: Object, target_col: Collection) -> None:
        for col in list(obj.users_collection):
            col.objects.unlink(obj)
        target_col.objects.link(obj)


class EntityMeshFactory:
    """視認性の高い戦術ユニット用3Dメッシュおよびマテリアルを生成・キャッシュするクラス"""

    @staticmethod
    def get_or_create_material(name: str, rgba: Tuple[float, float, float, float]) -> Material:
        mat = bpy.data.materials.get(name)
        if mat is None:
            mat = bpy.data.materials.new(name=name)
            mat.use_nodes = True
        mat.diffuse_color = rgba
        if mat.use_nodes and mat.node_tree:
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf is not None:
                bsdf.inputs["Base Color"].default_value = rgba
                if "Roughness" in bsdf.inputs:
                    bsdf.inputs["Roughness"].default_value = ColorPalette.MATERIAL_ROUGHNESS_UNIT
                if "Metallic" in bsdf.inputs:
                    bsdf.inputs["Metallic"].default_value = ColorPalette.MATERIAL_METALLIC_UNIT
        return mat

    @classmethod
    def apply_visual_color(
        cls,
        obj: Object,
        mat_name: str,
        rgba: Tuple[float, float, float, float],
    ) -> None:
        obj.color = rgba
        if obj.type == "MESH" and obj.data is not None:
            mat = cls.get_or_create_material(mat_name, rgba)
            if len(obj.data.materials) == MathConstants.ZERO_INT:
                obj.data.materials.append(mat)
            else:
                obj.data.materials[MathConstants.ZERO_INT] = mat

    @classmethod
    def get_or_build_fighter_mesh(cls, scene: Scene, model_rel_path: str) -> Mesh:
        """
        実機の .gltf メッシュを読み込んで結合メッシュ化、失敗時はデルタ翼戦闘機シルエットを生成。
        ローカル -Y 軸が機首前方（DirectX +Z 前方と完全一致）になります。
        """
        safe_key = Path(model_rel_path).stem if model_rel_path else "fighter"
        mesh_name = f"Mission_ProxyMesh_{safe_key}"
        existing = bpy.data.meshes.get(mesh_name)
        if existing is not None and len(existing.vertices) > MathConstants.ZERO_INT:
            return existing

        gltf_path = RepoPathResolver.resolve_path(scene, model_rel_path)
        if gltf_path.exists() and gltf_path.suffix.lower() in (".gltf", ".glb"):
            imported_mesh = cls._try_load_combined_gltf_mesh(gltf_path, mesh_name)
            if imported_mesh is not None:
                return imported_mesh

        return cls._build_procedural_fighter_mesh(mesh_name)

    @staticmethod
    def _try_load_combined_gltf_mesh(gltf_path: Path, target_mesh_name: str) -> Optional[Mesh]:
        before_objs = set(bpy.data.objects)
        try:
            bpy.ops.import_scene.gltf(filepath=str(gltf_path))
        except Exception:
            return None

        new_objs = [o for o in bpy.data.objects if o not in before_objs]
        if not new_objs:
            return None

        bm = bmesh.new()
        depsgraph = bpy.context.evaluated_depsgraph_get()
        try:
            for obj in new_objs:
                if obj.type != "MESH":
                    continue
                eval_obj = obj.evaluated_get(depsgraph)
                temp_mesh = eval_obj.to_mesh()
                if temp_mesh is not None:
                    temp_bm = bmesh.new()
                    temp_bm.from_mesh(temp_mesh)
                    # glTF (+Z forward in engine -> Blender import時 +Y または -Y を確認しつつワールド行列適用)
                    bmesh.ops.transform(temp_bm, matrix=obj.matrix_world, verts=temp_bm.verts)
                    # Engine Model.cpp は X反転で +Z前方になるため Blender側では Z軸180度回転で -Y前方へ揃える
                    rot_pi = Matrix((
                        (-MathConstants.UNIT, MathConstants.ZERO, MathConstants.ZERO, MathConstants.ZERO),
                        (MathConstants.ZERO, -MathConstants.UNIT, MathConstants.ZERO, MathConstants.ZERO),
                        (MathConstants.ZERO, MathConstants.ZERO, MathConstants.UNIT, MathConstants.ZERO),
                        (MathConstants.ZERO, MathConstants.ZERO, MathConstants.ZERO, MathConstants.UNIT),
                    ))
                    bmesh.ops.transform(temp_bm, matrix=rot_pi, verts=temp_bm.verts)
                    vert_offset = len(bm.verts)
                    for v in temp_bm.verts:
                        bm.verts.new(v.co)
                    bm.verts.ensure_lookup_table()
                    for f in temp_bm.faces:
                        try:
                            bm.faces.new([bm.verts[vert_offset + v.index] for v in f.verts])
                        except ValueError:
                            pass
                    temp_bm.free()
                    eval_obj.to_mesh_clear()

            # 前方方向を示すノーズガイドライン頂点も付与せずクリーンな実機メッシュを作成
            if len(bm.verts) == MathConstants.ZERO_INT:
                bm.free()
                return None

            out_mesh = bpy.data.meshes.new(target_mesh_name)
            bm.to_mesh(out_mesh)
            out_mesh.update()
            bm.free()
            return out_mesh
        finally:
            for obj in new_objs:
                bpy.data.objects.remove(obj, do_unlink=True)

    @staticmethod
    def _build_procedural_fighter_mesh(mesh_name: str) -> Mesh:
        """ローカル -Y が機首前方のシャープなデルタ翼ジェット戦闘機プロキシメッシュ"""
        mesh = bpy.data.meshes.new(mesh_name)
        bm = bmesh.new()

        half_len = GizmoDimensions.FIGHTER_LENGTH * MathConstants.HALF
        half_span = GizmoDimensions.FIGHTER_WINGSPAN * MathConstants.HALF
        tail_h = GizmoDimensions.FIGHTER_HEIGHT

        nose = bm.verts.new((MathConstants.ZERO, -half_len, MathConstants.ZERO))
        wing_l = bm.verts.new((-half_span, half_len * MathConstants.HALF, MathConstants.ZERO))
        wing_r = bm.verts.new((half_span, half_len * MathConstants.HALF, MathConstants.ZERO))
        tail_c = bm.verts.new((MathConstants.ZERO, half_len, MathConstants.ZERO))
        spine = bm.verts.new((MathConstants.ZERO, MathConstants.ZERO, tail_h * MathConstants.HALF))
        fin_top = bm.verts.new((MathConstants.ZERO, half_len, tail_h))

        bm.faces.new((nose, wing_r, spine))
        bm.faces.new((nose, spine, wing_l))
        bm.faces.new((spine, wing_r, tail_c))
        bm.faces.new((spine, tail_c, wing_l))
        bm.faces.new((nose, wing_l, tail_c, wing_r))
        bm.faces.new((spine, tail_c, fin_top))

        bm.normal_update()
        bm.to_mesh(mesh)
        bm.free()
        return mesh

    @staticmethod
    def get_or_build_ground_mesh(ground_ai_type: str) -> Mesh:
        mesh_name = f"Mission_GroundProxy_{ground_ai_type}"
        existing = bpy.data.meshes.get(mesh_name)
        if existing is not None:
            return existing

        mesh = bpy.data.meshes.new(mesh_name)
        bm = bmesh.new()

        if ground_ai_type == GroundDefaults.AI_STRUCTURE:
            bmesh.ops.create_cone(
                bm,
                cap_ends=True,
                cap_tris=False,
                segments=GizmoDimensions.CYLINDER_SEGMENTS,
                radius1=GizmoDimensions.STRUCTURE_RADIUS,
                radius2=GizmoDimensions.STRUCTURE_RADIUS * MathConstants.HALF,
                depth=GizmoDimensions.STRUCTURE_HEIGHT,
            )
            bmesh.ops.translate(
                bm,
                verts=bm.verts,
                vec=(MathConstants.ZERO, MathConstants.ZERO, GizmoDimensions.STRUCTURE_HEIGHT * MathConstants.HALF),
            )
        elif ground_ai_type == GroundDefaults.AI_PATROL_VEHICLE:
            bmesh.ops.create_cube(bm, size=MathConstants.UNIT)
            bmesh.ops.scale(
                bm,
                verts=bm.verts,
                vec=(
                    GizmoDimensions.VEHICLE_WIDTH,
                    GizmoDimensions.VEHICLE_LENGTH,
                    GizmoDimensions.VEHICLE_HEIGHT,
                ),
            )
            bmesh.ops.translate(
                bm,
                verts=bm.verts,
                vec=(MathConstants.ZERO, MathConstants.ZERO, GizmoDimensions.VEHICLE_HEIGHT * MathConstants.HALF),
            )
        else:
            bmesh.ops.create_cone(
                bm,
                cap_ends=True,
                cap_tris=False,
                segments=GizmoDimensions.CYLINDER_SEGMENTS,
                radius1=GizmoDimensions.TURRET_BASE_RADIUS,
                radius2=GizmoDimensions.TURRET_BASE_RADIUS * MathConstants.HALF,
                depth=GizmoDimensions.TURRET_HEIGHT,
            )
            bmesh.ops.translate(
                bm,
                verts=bm.verts,
                vec=(MathConstants.ZERO, MathConstants.ZERO, GizmoDimensions.TURRET_HEIGHT * MathConstants.HALF),
            )

        bm.normal_update()
        bm.to_mesh(mesh)
        bm.free()
        return mesh

    @staticmethod
    def get_or_build_outpost_tower_mesh() -> Mesh:
        mesh_name = "Mission_Zadanie00_Outpost04_Mesh"
        existing = bpy.data.meshes.get(mesh_name)
        if existing is not None:
            return existing

        mesh = bpy.data.meshes.new(mesh_name)
        bm = bmesh.new()
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=False,
            segments=GizmoDimensions.CYLINDER_SEGMENTS,
            radius1=GizmoDimensions.OUTPOST_RADIUS,
            radius2=GizmoDimensions.OUTPOST_RADIUS * MathConstants.HALF,
            depth=GizmoDimensions.OUTPOST_HEIGHT,
        )
        bmesh.ops.translate(
            bm,
            verts=bm.verts,
            vec=(MathConstants.ZERO, MathConstants.ZERO, GizmoDimensions.OUTPOST_HEIGHT * MathConstants.HALF),
        )
        bm.normal_update()
        bm.to_mesh(mesh)
        bm.free()
        return mesh

    @staticmethod
    def get_or_build_ring_gate_mesh(radius: float, mesh_name: str) -> Mesh:
        existing = bpy.data.meshes.get(mesh_name)
        if existing is not None:
            return existing

        mesh = bpy.data.meshes.new(mesh_name)
        bm = bmesh.new()
        seg = GizmoDimensions.GATE_RING_SEGMENTS
        thickness = GizmoDimensions.AMBUSH_PREVIEW_BEVEL
        inner_r = max(MathConstants.UNIT, radius - thickness)

        outer_verts = []
        inner_verts = []
        for i in range(seg):
            ang = (MathConstants.TWO * math.pi * float(i)) / float(seg)
            cx = math.cos(ang)
            cz = math.sin(ang)
            outer_verts.append(bm.verts.new((cx * radius, MathConstants.ZERO, cz * radius)))
            inner_verts.append(bm.verts.new((cx * inner_r, MathConstants.ZERO, cz * inner_r)))

        for i in range(seg):
            nxt = (i + MathConstants.ONE_INT) % seg
            bm.faces.new((outer_verts[i], outer_verts[nxt], inner_verts[nxt], inner_verts[i]))

        bm.normal_update()
        bm.to_mesh(mesh)
        bm.free()
        return mesh