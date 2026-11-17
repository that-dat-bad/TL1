# -*- coding: utf-8 -*-
"""
海面メッシュ (WaterPlane_AI) および 流水リボンメッシュ (RiverMesh_AI) 生成モジュール。
また、Rivers コレクションへの編集可能カーブ配置も行う。
"""
import math
import bpy  # type: ignore


def _get_or_create_water_material(name="Material_Water_Surface", is_river=False):
    mat = bpy.data.materials.get(name)
    if mat and mat.use_nodes and any(n.type == 'BUMP' for n in mat.node_tree.nodes):
        return mat
    if not mat:
        mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    if is_river:
        bsdf.inputs["Base Color"].default_value = (0.03, 0.24, 0.38, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.28
        mat.diffuse_color = (0.03, 0.24, 0.38, 0.96)
    else:
        bsdf.inputs["Base Color"].default_value = (0.015, 0.11, 0.28, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.32
        mat.diffuse_color = (0.015, 0.11, 0.28, 0.96)

    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.25
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = 0.96

    # 軽量プロシージャル波バンプ（HDRI鏡面白飛び防止）
    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-500, -180)
    tex_noise = nodes.new("ShaderNodeTexNoise")
    tex_noise.location = (-250, -180)
    tex_noise.inputs["Scale"].default_value = 0.04 if is_river else 0.015
    tex_noise.inputs["Detail"].default_value = 5.0
    links.new(tex_coord.outputs["Object"], tex_noise.inputs["Vector"])

    bump = nodes.new("ShaderNodeBump")
    bump.location = (30, -180)
    bump.inputs["Strength"].default_value = 0.22
    bump.inputs["Distance"].default_value = 1.5
    links.new(tex_noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    return mat


def _get_or_create_collection(context, name):
    col = bpy.data.collections.get(name)
    if not col:
        col = bpy.data.collections.new(name)
        context.scene.collection.children.link(col)
    return col


def _clear_ai_objects(col):
    for obj in [o for o in col.objects if "_AI" in o.name]:
        bpy.data.objects.remove(obj, do_unlink=True)


def sync_river_curves_to_scene(context, compiled_rivers):
    """生成された川ルートを編集可能なベジェカーブとして Rivers コレクションに配置"""
    col = _get_or_create_collection(context, "Rivers")
    _clear_ai_objects(col)

    for idx, r_data in enumerate(compiled_rivers or []):
        pts = r_data.get("points", [])
        if len(pts) < 2:
            continue
        # 適度に間引いて編集しやすくする
        step = max(1, len(pts) // 24)
        sampled = pts[::step]
        if sampled[-1] != pts[-1]:
            sampled.append(pts[-1])

        curve = bpy.data.curves.new(f"RiverPath_AI_{idx}", 'CURVE')
        curve.dimensions = '3D'
        obj = bpy.data.objects.new(f"RiverPath_AI_{idx}", curve)
        col.objects.link(obj)
        sp = curve.splines.new('BEZIER')
        sp.bezier_points.add(len(sampled) - 1)
        for i, p in enumerate(sampled):
            bp = sp.bezier_points[i]
            bp.co = (float(p[0]), float(p[1]), float(p[2]))
            bp.radius = float(p[3]) / max(float(r_data.get("width", 120.0)), 1.0)
            bp.handle_left_type = 'AUTO'
            bp.handle_right_type = 'AUTO'


def build_river_mesh(context, compiled_rivers, obj_name="RiverMesh_AI"):
    """
    上流 -> 下流方向へ V 座標が伸びるリボンメッシュを生成する。
    U: [0, 1] (左岸 -> 右岸), V: 累積距離 / 川幅
    """
    col = _get_or_create_collection(context, "Water")
    old = bpy.data.objects.get(obj_name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)

    if not compiled_rivers:
        return None

    verts = []
    faces = []
    uvs = []
    v_offset = 0

    for r_data in compiled_rivers:
        pts = r_data.get("points", [])
        if len(pts) < 2:
            continue

        cum_dist = 0.0
        n_pts = len(pts)
        for i in range(n_pts):
            x, y, wz, w = float(pts[i][0]), float(pts[i][1]), float(pts[i][2]), float(pts[i][3])
            if i > 0:
                px, py = float(pts[i - 1][0]), float(pts[i - 1][1])
                cum_dist += math.hypot(x - px, y - py)

            if i == 0:
                tx = float(pts[1][0]) - x
                ty = float(pts[1][1]) - y
            elif i == n_pts - 1:
                tx = x - float(pts[i - 1][0])
                ty = y - float(pts[i - 1][1])
            else:
                tx = float(pts[i + 1][0]) - float(pts[i - 1][0])
                ty = float(pts[i + 1][1]) - float(pts[i - 1][1])

            tlen = max(math.hypot(tx, ty), 1e-4)
            nx = -ty / tlen
            ny = tx / tlen
            half_w = w * 0.62  # 河床の岸辺へ少し潜り込ませて隙間を防ぐ

            verts.append((x - nx * half_w, y - ny * half_w, wz))
            verts.append((x + nx * half_w, y + ny * half_w, wz))
            v_coord = cum_dist / max(w, 20.0)
            uvs.append((0.0, v_coord))
            uvs.append((1.0, v_coord))

        for i in range(n_pts - 1):
            i0 = v_offset + i * 2
            i1 = i0 + 1
            i2 = i0 + 3
            i3 = i0 + 2
            faces.append((i0, i1, i2, i3))

        v_offset += n_pts * 2

    if not faces:
        return None

    mesh = bpy.data.meshes.new(f"{obj_name}Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)

    uv_layer = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for loop_idx in poly.loop_indices:
            vert_idx = mesh.loops[loop_idx].vertex_index
            uv_layer.data[loop_idx].uv = uvs[vert_idx]
        poly.use_smooth = True

    obj = bpy.data.objects.new(obj_name, mesh)
    col.objects.link(obj)
    obj.color = (0.06, 0.34, 0.48, 0.86)
    obj.data.materials.append(_get_or_create_water_material("Material_River_Water", is_river=True))
    return obj


def build_ocean_mesh(context, water_level, size_x=40000.0, horizon_size=160000.0, grid_n=96, obj_name="WaterPlane_AI"):
    """
    水平線まで広がる海面メッシュを生成する（中心付近が高密度、外周が広大）。
    """
    col = _get_or_create_collection(context, "Water")
    old = bpy.data.objects.get(obj_name)
    if old:
        bpy.data.objects.remove(old, do_unlink=True)

    if water_level is None:
        return None

    import numpy as np  # type: ignore

    # 非線形グリッド: 中心(プレイエリア)は密に、外周(水平線)は粗く広げる
    t = np.linspace(-1.0, 1.0, grid_n, dtype=np.float32)
    half_h = horizon_size * 0.5
    coords = np.sign(t) * (0.35 * np.abs(t) + 0.65 * (np.abs(t) ** 2.4)) * half_h

    gx, gy = np.meshgrid(coords, coords, indexing="xy")
    gz = np.full_like(gx, float(water_level), dtype=np.float32)
    verts = np.column_stack([gx.ravel(), gy.ravel(), gz.ravel()]).tolist()

    ix = np.arange(grid_n - 1, dtype=np.int32)
    iy = np.arange(grid_n - 1, dtype=np.int32)
    mx, my = np.meshgrid(ix, iy, indexing="xy")
    v0 = my * grid_n + mx
    faces = np.column_stack([v0.ravel(), (v0 + 1).ravel(), (v0 + grid_n + 1).ravel(), (v0 + grid_n).ravel()]).tolist()

    mesh = bpy.data.meshes.new(f"{obj_name}Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update(calc_edges=True)

    half_play = size_x * 0.5
    uv_layer = mesh.uv_layers.new(name="UVMap")
    u_arr = (gx.ravel() + half_play) / max(size_x, 1.0)
    v_arr = (gy.ravel() + half_play) / max(size_x, 1.0)
    faces_flat = np.array(faces, dtype=np.int32).ravel()
    uvs = np.column_stack([u_arr[faces_flat], v_arr[faces_flat]]).astype(np.float32)
    uv_layer.data.foreach_set("uv", uvs.ravel())

    for p in mesh.polygons:
        p.use_smooth = True

    obj = bpy.data.objects.new(obj_name, mesh)
    col.objects.link(obj)
    obj.color = (0.04, 0.22, 0.42, 0.86)
    obj.data.materials.append(_get_or_create_water_material("Material_Ocean_Water", is_river=False))
    return obj
