# -*- coding: utf-8 -*-
"""
Pure NumPy による 40km/20km 地形ハイトマップ生成 ＆ 侵食シミュレーションエンジン。
外部ライブラリ不要（Blender 標準搭載の numpy のみで動作）。
"""
import math
import os
import json
import time
import numpy as np  # type: ignore

# モジュール内キャッシュ（同じシーン内での stats 取得・ベイク・エクスポートで共有）
_HEIGHTMAP_CACHE = {}


def get_cached_heightmap(key="Terrain"):
    """キャッシュされた (heightmap, flow_map, meta) を返す"""
    return _HEIGHTMAP_CACHE.get(key)


def set_cached_heightmap(heightmap, flow_map, meta, key="Terrain"):
    """ハイトマップと流路マップをキャッシュに保存する"""
    _HEIGHTMAP_CACHE[key] = (heightmap, flow_map, meta)


def _fade(t):
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _build_perm_table(seed):
    rng = np.random.default_rng(int(seed) & 0xFFFFFFFF)
    p = rng.permutation(256).astype(np.int32)
    return np.concatenate([p, p])


def _value_noise_2d(x, y, perm):
    """ベクトル化された 2D Value Noise (値域 [-1, 1])"""
    xi = np.floor(x).astype(np.int32) & 255
    yi = np.floor(y).astype(np.int32) & 255
    xf = x - np.floor(x)
    yf = y - np.floor(y)

    u = _fade(xf)
    v = _fade(yf)

    aa = perm[perm[xi] + yi]
    ab = perm[perm[xi] + yi + 1]
    ba = perm[perm[xi + 1] + yi]
    bb = perm[perm[xi + 1] + yi + 1]

    # 0..255 -> [-1, 1]
    x1 = (aa * (2.0 / 255.0) - 1.0) * (1.0 - u) + (ba * (2.0 / 255.0) - 1.0) * u
    x2 = (ab * (2.0 / 255.0) - 1.0) * (1.0 - u) + (bb * (2.0 / 255.0) - 1.0) * u
    return x1 * (1.0 - v) + x2 * v


def _fbm_and_ridged(wx, wy, base_freq, octaves=6, ridge_sharpness=0.5, seed=1):
    """ドメインワープ付き FBM + Ridged Multifractal 合成"""
    perm = _build_perm_table(seed)
    perm_warp = _build_perm_table(seed + 101)

    # 緩やかなドメインワープで尾根を自然なうねりにする
    warp_freq = base_freq * 0.45
    wx_w = wx + _value_noise_2d(wx * warp_freq + 11.3, wy * warp_freq + 5.7, perm_warp) * (0.35 / max(base_freq, 1e-6))
    wy_w = wy + _value_noise_2d(wx * warp_freq + 23.1, wy * warp_freq + 17.9, perm_warp) * (0.35 / max(base_freq, 1e-6))

    fbm = np.zeros_like(wx, dtype=np.float32)
    ridged = np.zeros_like(wx, dtype=np.float32)
    amp = 0.5
    freq = base_freq
    norm_sum = 0.0
    ridge_weight = 1.0

    for oct_idx in range(octaves):
        ox = oct_idx * 37.13
        oy = oct_idx * 71.89
        n = _value_noise_2d(wx_w * freq + ox, wy_w * freq + oy, perm).astype(np.float32)
        fbm += n * amp

        r = 1.0 - np.abs(n)
        r = r * r * ridge_weight
        ridge_weight = np.clip(r * 1.6, 0.25, 1.0)
        ridged += r * amp

        norm_sum += amp
        freq *= 2.05
        amp *= 0.5

    fbm = fbm / max(norm_sum, 1e-6)
    ridged = (ridged / max(norm_sum, 1e-6)) * 2.0 - 0.85

    sharp = float(np.clip(ridge_sharpness, 0.0, 1.0))
    return fbm * (1.0 - sharp * 0.72) + ridged * (sharp * 0.72)


def _extract_spline_pt(pt):
    """{"co": [x, y, z], ...} / {"x": ..., "y": ...} / [x, y, z] の全形式から (x, y, radius, tilt) を抽出"""
    if isinstance(pt, dict):
        if "co" in pt:
            co = pt["co"]
            x, y = float(co[0]), float(co[1])
        else:
            x, y = float(pt.get("x", 0.0)), float(pt.get("y", 0.0))
        return x, y, float(pt.get("radius", 1.0)), float(pt.get("tilt", 0.0))
    elif isinstance(pt, (list, tuple)) and len(pt) >= 2:
        return float(pt[0]), float(pt[1]), 1.0, 0.0
    return 0.0, 0.0, 1.0, 0.0


def _rasterize_splines_to_field(
    splines,
    resolution,
    half_x,
    half_y,
    base_radius,
    amplitude,
    is_mountain=True,
):
    """
    スプライン制御点リストを 2D 距離場としてハイト加算値配列へラスタライズする。
    各線分のバウンディングボックスのみ計算するため高速。
    """
    field = np.zeros((resolution, resolution), dtype=np.float32)
    if not splines or abs(amplitude) < 1e-4:
        return field

    dx_cell = (2.0 * half_x) / float(resolution - 1)
    dy_cell = (2.0 * half_y) / float(resolution - 1)

    for sp in splines:
        if not sp or len(sp) < 2:
            continue
        sp_field = np.zeros((resolution, resolution), dtype=np.float32)
        for i in range(len(sp) - 1):
            x0, y0, r0_mul, t0 = _extract_spline_pt(sp[i])
            x1, y1, r1_mul, t1 = _extract_spline_pt(sp[i + 1])
            r0 = r0_mul * base_radius
            r1 = r1_mul * base_radius

            max_r = max(r0, r1, 10.0)
            min_wx = min(x0, x1) - max_r
            max_wx = max(x0, x1) + max_r
            min_wy = min(y0, y1) - max_r
            max_wy = max(y0, y1) + max_r

            ix0 = max(0, int(math.floor((min_wx + half_x) / dx_cell)))
            ix1 = min(resolution - 1, int(math.ceil((max_wx + half_x) / dx_cell)))
            iy0 = max(0, int(math.floor((min_wy + half_y) / dy_cell)))
            iy1 = min(resolution - 1, int(math.ceil((max_wy + half_y) / dy_cell)))
            if ix1 < ix0 or iy1 < iy0:
                continue

            xs = -half_x + np.arange(ix0, ix1 + 1, dtype=np.float32) * dx_cell
            ys = -half_y + np.arange(iy0, iy1 + 1, dtype=np.float32) * dy_cell
            gx, gy = np.meshgrid(xs, ys, indexing="xy")  # shape (ny, nx)

            vx = x1 - x0
            vy = y1 - y0
            seg_len2 = vx * vx + vy * vy
            if seg_len2 < 1e-4:
                proj = np.zeros_like(gx)
            else:
                proj = np.clip(((gx - x0) * vx + (gy - y0) * vy) / seg_len2, 0.0, 1.0)

            cx = x0 + vx * proj
            cy = y0 + vy * proj
            dist = np.hypot(gx - cx, gy - cy)

            r_local = np.maximum(r0 + (r1 - r0) * proj, 10.0)
            u = np.clip(1.0 - dist / r_local, 0.0, 1.0)
            # C2 連続な滑らかなプロファイル
            falloff = u * u * u * (u * (u * 6.0 - 15.0) + 10.0)

            tilt_local = t0 + (t1 - t0) * proj
            if is_mountain:
                h_mult = np.clip(1.0 + tilt_local * 0.65, 0.05, 2.2)
            else:
                h_mult = np.clip(1.0 + tilt_local * 0.55, 0.05, 2.0)

            contrib = falloff * h_mult * amplitude
            sub = sp_field[iy0:iy1 + 1, ix0:ix1 + 1]
            np.maximum(sub, contrib, out=sub)

        np.maximum(field, sp_field, out=field)

    return field


def _grade_roads_into_heightmap(
    heightmap,
    road_splines,
    half_x,
    half_y,
    flat_radius=42.0,
    blend_radius=150.0,
):
    """
    幹線道路スプラインの周辺をハイトマップ上で滑らかに慣らし、
    道路が斜面に突き刺さったり過剰に浮いたりするのを防ぐ。
    """
    h = heightmap.copy()
    res_y, res_x = h.shape
    dx_cell = (2.0 * half_x) / float(res_x - 1)
    dy_cell = (2.0 * half_y) / float(res_y - 1)
    max_r = flat_radius + blend_radius

    weight_sum = np.zeros((res_y, res_x), dtype=np.float32)
    target_sum = np.zeros((res_y, res_x), dtype=np.float32)

    for sp in road_splines:
        if len(sp) < 2:
            continue
        # 間引いて高速化（50m間隔程度）
        pts = sp[::2] if len(sp) > 12 else sp
        if pts[-1] is not sp[-1]:
            pts = list(pts) + [sp[-1]]

        # 各制御点の現在標高をサンプリング
        pt_coords = []
        for p in pts:
            px, py, _, _ = _extract_spline_pt(p)
            ix = int(np.clip(round((px + half_x) / dx_cell), 0, res_x - 1))
            iy = int(np.clip(round((py + half_y) / dy_cell), 0, res_y - 1))
            pt_coords.append((px, py, float(heightmap[iy, ix])))

        # 急激な凹凸を抑えるため1D移動平均で道路目標標高を平滑化
        zs = [c[2] for c in pt_coords]
        smooth_zs = list(zs)
        for _ in range(2):
            nxt = list(smooth_zs)
            for k in range(1, len(smooth_zs) - 1):
                nxt[k] = 0.25 * smooth_zs[k - 1] + 0.5 * smooth_zs[k] + 0.25 * smooth_zs[k + 1]
            smooth_zs = nxt

        for i in range(len(pt_coords) - 1):
            x0, y0, _ = pt_coords[i]
            x1, y1, _ = pt_coords[i + 1]
            z0 = smooth_zs[i]
            z1 = smooth_zs[i + 1]

            ix0 = max(0, int(math.floor((min(x0, x1) - max_r + half_x) / dx_cell)))
            ix1 = min(res_x - 1, int(math.ceil((max(x0, x1) + max_r + half_x) / dx_cell)))
            iy0 = max(0, int(math.floor((min(y0, y1) - max_r + half_y) / dy_cell)))
            iy1 = min(res_y - 1, int(math.ceil((max(y0, y1) + max_r + half_y) / dy_cell)))
            if ix1 < ix0 or iy1 < iy0:
                continue

            xs = -half_x + np.arange(ix0, ix1 + 1, dtype=np.float32) * dx_cell
            ys = -half_y + np.arange(iy0, iy1 + 1, dtype=np.float32) * dy_cell
            gx, gy = np.meshgrid(xs, ys, indexing="xy")

            vx = x1 - x0
            vy = y1 - y0
            seg_len2 = vx * vx + vy * vy
            if seg_len2 < 1e-4:
                proj = np.zeros_like(gx)
            else:
                proj = np.clip(((gx - x0) * vx + (gy - y0) * vy) / seg_len2, 0.0, 1.0)

            dist = np.hypot(gx - (x0 + vx * proj), gy - (y0 + vy * proj))
            u = np.clip((dist - flat_radius) / max(blend_radius, 1.0), 0.0, 1.0)
            w = 1.0 - (u * u * (3.0 - 2.0 * u))
            z_seg = z0 + (z1 - z0) * proj

            # 深い谷（橋梁区間）では地面を持ち上げすぎないよう抑制
            sub_h = heightmap[iy0:iy1 + 1, ix0:ix1 + 1]
            bridge_damp = np.where((z_seg - sub_h) > 35.0, 0.15, 1.0)
            w = w * bridge_damp

            weight_sum[iy0:iy1 + 1, ix0:ix1 + 1] += w
            target_sum[iy0:iy1 + 1, ix0:ix1 + 1] += z_seg * w

    mask = weight_sum > 1e-4
    avg_target = np.where(mask, target_sum / np.maximum(weight_sum, 1e-4), h)
    blend = np.clip(weight_sum, 0.0, 1.0)
    return h * (1.0 - blend) + avg_target * blend


def apply_thermal_erosion(heightmap, cell_size, iterations=20, talus_angle_deg=38.0, rate=0.35):
    """
    Pure NumPy 熱侵食（崖崩れ・崖錐形成）。
    安息角を超える斜面から隣接セルへ土砂を移動させる。
    """
    if iterations <= 0:
        return heightmap

    h = heightmap.copy()
    talus_diff = math.tan(math.radians(talus_angle_deg)) * cell_size
    talus_diag = talus_diff * 1.41421356

    shifts_cardinal = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    shifts_diag = [(-1, -1), (-1, 1), (1, -1), (1, 1)]

    for _ in range(iterations):
        delta = np.zeros_like(h)
        for dy, dx in shifts_cardinal:
            nb = np.roll(np.roll(h, -dy, axis=0), -dx, axis=1)
            diff = h - nb
            excess = np.maximum(0.0, diff - talus_diff)
            move = excess * (rate * 0.125)
            delta -= move
            delta += np.roll(np.roll(move, dy, axis=0), dx, axis=1)

        for dy, dx in shifts_diag:
            nb = np.roll(np.roll(h, -dy, axis=0), -dx, axis=1)
            diff = h - nb
            excess = np.maximum(0.0, diff - talus_diag)
            move = excess * (rate * 0.09)
            delta -= move
            delta += np.roll(np.roll(move, dy, axis=0), dx, axis=1)

        # 端のラップアラウンドを抑制
        delta[0, :] = 0.0
        delta[-1, :] = 0.0
        delta[:, 0] = 0.0
        delta[:, -1] = 0.0
        h += delta

    return h


def apply_hydraulic_erosion(
    heightmap,
    num_droplets=24000,
    max_steps=32,
    inertia=0.25,
    sediment_capacity=4.0,
    min_slope=0.01,
    erode_speed=0.35,
    deposit_speed=0.35,
    evaporate_speed=0.04,
    gravity=4.0,
    seed=1,
):
    """
    Pure NumPy バッチ粒子水食シミュレーション。
    数千個の雨粒を同時に流下させて、樹枝状の谷と扇状地を彫り込む。
    戻り値: (eroded_heightmap, flow_map)
    """
    h = heightmap.astype(np.float32, copy=True)
    res_y, res_x = h.shape
    flow_map = np.zeros((res_y, res_x), dtype=np.float32)
    if num_droplets <= 0 or res_x < 4 or res_y < 4:
        return h, flow_map

    rng = np.random.default_rng(int(seed) + 777)
    batch_size = min(6000, num_droplets)
    num_batches = max(1, (num_droplets + batch_size - 1) // batch_size)

    for _ in range(num_batches):
        px = rng.uniform(1.0, res_x - 2.001, size=batch_size).astype(np.float32)
        py = rng.uniform(1.0, res_y - 2.001, size=batch_size).astype(np.float32)
        dx = np.zeros(batch_size, dtype=np.float32)
        dy = np.zeros(batch_size, dtype=np.float32)
        speed = np.ones(batch_size, dtype=np.float32)
        water = np.ones(batch_size, dtype=np.float32)
        sediment = np.zeros(batch_size, dtype=np.float32)
        active = np.ones(batch_size, dtype=bool)

        for _step in range(max_steps):
            if not np.any(active):
                break

            ix = np.clip(px.astype(np.int32), 0, res_x - 2)
            iy = np.clip(py.astype(np.int32), 0, res_y - 2)
            fx = px - ix
            fy = py - iy

            h00 = h[iy, ix]
            h10 = h[iy, ix + 1]
            h01 = h[iy + 1, ix]
            h11 = h[iy + 1, ix + 1]

            grad_x = (h10 - h00) * (1.0 - fy) + (h11 - h01) * fy
            grad_y = (h01 - h00) * (1.0 - fx) + (h11 - h10) * fx
            h_old = h00 * (1.0 - fx) * (1.0 - fy) + h10 * fx * (1.0 - fy) + h01 * (1.0 - fx) * fy + h11 * fx * fy

            dx = dx * inertia - grad_x * (1.0 - inertia)
            dy = dy * inertia - grad_y * (1.0 - inertia)
            glen = np.hypot(dx, dy)
            valid_dir = glen > 1e-6
            dx = np.where(valid_dir, dx / np.maximum(glen, 1e-6), 0.0)
            dy = np.where(valid_dir, dy / np.maximum(glen, 1e-6), 0.0)

            nx = px + dx
            ny = py + dy

            in_bounds = active & valid_dir & (nx >= 1.0) & (nx < res_x - 2.0) & (ny >= 1.0) & (ny < res_y - 2.0)
            active &= in_bounds
            if not np.any(active):
                break

            nix = np.clip(nx.astype(np.int32), 0, res_x - 2)
            niy = np.clip(ny.astype(np.int32), 0, res_y - 2)
            nfx = nx - nix
            nfy = ny - niy
            h_new = (
                h[niy, nix] * (1.0 - nfx) * (1.0 - nfy)
                + h[niy, nix + 1] * nfx * (1.0 - nfy)
                + h[niy + 1, nix] * (1.0 - nfx) * nfy
                + h[niy + 1, nix + 1] * nfx * nfy
            )

            diff_h = h_new - h_old
            cap = np.maximum(-diff_h, min_slope) * speed * water * sediment_capacity

            # 堆積または侵食量
            is_deposit = (sediment > cap) | (diff_h > 0.0)
            deposit_amt = np.where(
                diff_h > 0.0,
                np.minimum(diff_h, sediment),
                (sediment - cap) * deposit_speed,
            )
            erode_amt = np.minimum((cap - sediment) * erode_speed, np.maximum(-diff_h, 0.0) + 0.5)
            delta_sed = np.where(is_deposit, -deposit_amt, erode_amt)
            delta_sed = np.where(active, delta_sed, 0.0)

            sediment += delta_sed

            # 4近傍へバイリニア重みで地形変更を反映
            w00 = (1.0 - fx) * (1.0 - fy)
            w10 = fx * (1.0 - fy)
            w01 = (1.0 - fx) * fy
            w11 = fx * fy

            np.add.at(h, (iy, ix), -delta_sed * w00)
            np.add.at(h, (iy, ix + 1), -delta_sed * w10)
            np.add.at(h, (iy + 1, ix), -delta_sed * w01)
            np.add.at(h, (iy + 1, ix + 1), -delta_sed * w11)

            # 流路マスク蓄積
            w_act = np.where(active, water * 0.05, 0.0)
            np.add.at(flow_map, (iy, ix), w_act)

            speed = np.sqrt(np.maximum(0.1, speed * speed + np.maximum(-diff_h, 0.0) * gravity))
            water *= (1.0 - evaporate_speed)
            px = nx
            py = ny

    # 流路マップを [0, 1] 付近へ対数正規化
    if np.max(flow_map) > 0:
        flow_map = np.log1p(flow_map) / max(float(np.log1p(np.percentile(flow_map, 99.5))), 1e-4)
        flow_map = np.clip(flow_map, 0.0, 1.0)

    return h, flow_map


def generate_heightmap(
    compiled_blueprint,
    resolution=1024,
    seed=1,
    hydraulic_droplets=24000,
    thermal_iterations=18,
):
    """
    コンパイル済みブループリントから 2D ハイトマップ（単位: m）と流路マスクを生成する。
    """
    t0 = time.time()
    size_x = float(compiled_blueprint.get("terrain_size_x", 40000.0))
    size_y = float(compiled_blueprint.get("terrain_size_y", size_x))
    half_x = size_x * 0.5
    half_y = size_y * 0.5
    cell_size = size_x / float(resolution - 1)

    terrain_height = float(compiled_blueprint.get("terrain_height", 120.0))
    noise_scale = float(compiled_blueprint.get("noise_scale", 0.00025))
    ridge_sharpness = float(compiled_blueprint.get("ridge_sharpness", 0.5))
    noise_offset = compiled_blueprint.get("noise_offset", (0.0, 0.0, 0.0))

    xs = np.linspace(-half_x, half_x, resolution, dtype=np.float32)
    ys = np.linspace(-half_y, half_y, resolution, dtype=np.float32)
    wx, wy = np.meshgrid(xs, ys, indexing="xy")

    base_n = _fbm_and_ridged(
        wx + float(noise_offset[0]),
        wy + float(noise_offset[1]),
        base_freq=noise_scale * 1.4,
        octaves=6,
        ridge_sharpness=ridge_sharpness,
        seed=seed,
    )
    height = base_n * terrain_height

    # 山脈・谷スプラインの合成
    mt_height = float(compiled_blueprint.get("mountain_height", 500.0))
    mt_radius = float(compiled_blueprint.get("mountain_radius", 2000.0))
    vl_depth = float(compiled_blueprint.get("valley_depth", 350.0))
    vl_radius = float(compiled_blueprint.get("valley_radius", 1800.0))

    mt_field = _rasterize_splines_to_field(
        compiled_blueprint.get("mountains", []),
        resolution,
        half_x,
        half_y,
        base_radius=mt_radius,
        amplitude=mt_height,
        is_mountain=True,
    )
    vl_field = _rasterize_splines_to_field(
        compiled_blueprint.get("valleys", []),
        resolution,
        half_x,
        half_y,
        base_radius=vl_radius,
        amplitude=vl_depth,
        is_mountain=False,
    )

    # 山脈上にも岩稜ディテールを乗せる
    if np.max(mt_field) > 1.0:
        ridge_detail = _fbm_and_ridged(
            wx + float(noise_offset[0]) + 400.0,
            wy + float(noise_offset[1]) - 300.0,
            base_freq=noise_scale * 2.8,
            octaves=4,
            ridge_sharpness=max(0.65, ridge_sharpness),
            seed=seed + 33,
        )
        mt_field = mt_field * (0.78 + 0.35 * np.clip(ridge_detail, -0.5, 1.0))

    height = height + mt_field - vl_field

    # 都市平坦化マスク（有機的な境界＋緩やかな起伏を残す）
    city_radius = float(compiled_blueprint.get("city_grade_radius", 0.0))
    if city_radius > 50.0:
        cc = compiled_blueprint.get("city_center", (0.0, 0.0, 0.0))
        dx_c = wx - float(cc[0])
        dy_c = wy - float(cc[1])
        dist_city = np.hypot(dx_c, dy_c)

        # 境界を低周波ノイズで歪ませて真円を防止
        perm_city = _build_perm_table(seed + 503)
        warp_n = _value_noise_2d(wx * 0.00018 + 3.1, wy * 0.00018 + 7.7, perm_city)
        eff_radius = city_radius * (0.95 + 0.32 * warp_n)

        u = np.clip((dist_city - eff_radius * 0.35) / np.maximum(eff_radius * 0.90, 1.0), 0.0, 1.0)
        city_mask = u * u * (3.0 - 2.0 * u)

        # 都市中心の目標標高（完全に真っ平らにせず、元の緩やかな起伏を22%残す）
        in_core = dist_city < city_radius * 0.55
        center_z = float(np.median(height[in_core])) if np.any(in_core) else 0.0
        center_z = max(-20.0, min(80.0, center_z))
        gentle_target = center_z + (height - center_z) * 0.22
        height = gentle_target * (1.0 - city_mask) + height * city_mask

    # 幹線道路沿いの緩やかな平坦化（不要な浮き・過剰な橋脚を抑制）
    road_splines = []
    for r_pts in (compiled_blueprint.get("roads", []) or []):
        if r_pts and len(r_pts) >= 2:
            road_splines.append(r_pts)
    for r_pts in (compiled_blueprint.get("extra_roads", []) or []):
        if r_pts and len(r_pts) >= 2:
            road_splines.append(r_pts)
    if road_splines:
        height = _grade_roads_into_heightmap(
            height,
            road_splines,
            half_x=half_x,
            half_y=half_y,
            flat_radius=42.0,
            blend_radius=150.0,
        )

    # 熱侵食 ＆ 水食シミュレーション
    if thermal_iterations > 0:
        height = apply_thermal_erosion(
            height,
            cell_size=cell_size,
            iterations=thermal_iterations,
            talus_angle_deg=36.0,
            rate=0.35,
        )

    height, flow_map = apply_hydraulic_erosion(
        height,
        num_droplets=hydraulic_droplets,
        max_steps=32,
        seed=seed,
    )

    # 海・海岸線の適用（water_level / ocean 指定時）
    water_level = compiled_blueprint.get("water_level")
    ocean_cfg = compiled_blueprint.get("ocean")
    if ocean_cfg is not None:
        if water_level is None:
            water_level = 0.0
        height = _apply_ocean_coastline(height, ocean_cfg, float(water_level), wx, wy, half_x, seed)

    # 川（Rivers）の谷筋探索 ＋ 河床彫り込み ＋ 下流単調減少水面座標の算出
    compiled_rivers = []
    raw_rivers = compiled_blueprint.get("rivers", []) or []
    if raw_rivers:
        height, flow_map, compiled_rivers = _carve_rivers_into_heightmap(
            height,
            flow_map,
            raw_rivers,
            half_x=half_x,
            half_y=half_y,
            water_level=float(water_level) if water_level is not None else None,
        )

    # Shore Distance Field (Dagor Engine 準拠の浅瀬・白波用距離場)
    shore_sdf = None
    if water_level is not None:
        shore_sdf = compute_shore_distance_field(height, float(water_level), max_dist_px=48)

    elapsed = time.time() - t0
    stats = compute_heightmap_stats(height, cell_size)
    stats["generation_seconds"] = round(elapsed, 3)

    meta = {
        "resolution": int(resolution),
        "terrain_size_x": size_x,
        "terrain_size_y": size_y,
        "cell_size": cell_size,
        "seed": int(seed),
        "water_level": float(water_level) if water_level is not None else None,
        "has_ocean": ocean_cfg is not None,
        "rivers": compiled_rivers,
        "min_height": stats["min_height"],
        "max_height": stats["max_height"],
        "stats": stats,
    }
    set_cached_heightmap(height, flow_map, meta, key="Terrain")
    print(f"[HeightmapEngine] Generated {resolution}x{resolution} ({size_x:.0f}m) in {elapsed:.2f}s | H=[{stats['min_height']:.1f}, {stats['max_height']:.1f}]m | rivers={len(compiled_rivers)}")
    return height, flow_map, meta, shore_sdf


def compute_heightmap_stats(heightmap, cell_size):
    """ハイトマップの標高・勾配・平坦地率などの統計情報を算出する"""
    gy, gx = np.gradient(heightmap, cell_size)
    slope_rad = np.arctan(np.hypot(gx, gy))
    slope_deg = np.degrees(slope_rad)

    return {
        "resolution": int(heightmap.shape[0]),
        "cell_size_m": round(float(cell_size), 2),
        "min_height": round(float(np.min(heightmap)), 2),
        "max_height": round(float(np.max(heightmap)), 2),
        "mean_height": round(float(np.mean(heightmap)), 2),
        "std_height": round(float(np.std(heightmap)), 2),
        "mean_slope_deg": round(float(np.mean(slope_deg)), 2),
        "max_slope_deg": round(float(np.max(slope_deg)), 2),
        "flat_ratio_under_10deg": round(float(np.mean(slope_deg < 10.0)), 4),
    }


def save_heightmap_bundle(output_dir, heightmap, flow_map, meta):
    """ワーカープロセスや外部ツール用に .npy とメタデータ JSON を保存する"""
    os.makedirs(output_dir, exist_ok=True)
    hm_path = os.path.join(output_dir, "heightmap.npy")
    fl_path = os.path.join(output_dir, "flowmap.npy")
    meta_path = os.path.join(output_dir, "heightmap_meta.json")
    np.save(hm_path, heightmap.astype(np.float32))
    np.save(fl_path, flow_map.astype(np.float32))
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return hm_path, fl_path, meta_path


def heightmap_to_blender_image(heightmap, name="Terrain_Heightmap"):
    """
    NumPy ハイトマップを Blender の 32bit Float Image (bpy.data.images) に書き込む。
    値域は [min_h, max_h] を [0, 1] に正規化して格納する。
    """
    import bpy  # type: ignore

    res_y, res_x = heightmap.shape
    h_min = float(np.min(heightmap))
    h_max = float(np.max(heightmap))
    span = max(h_max - h_min, 1e-3)
    norm = np.clip((heightmap - h_min) / span, 0.0, 1.0).astype(np.float32)

    img = bpy.data.images.get(name)
    if img and (img.size[0] != res_x or img.size[1] != res_y):
        bpy.data.images.remove(img)
        img = None
    if not img:
        img = bpy.data.images.new(name=name, width=res_x, height=res_y, alpha=False, float_buffer=True)

    rgba = np.ones((res_y, res_x, 4), dtype=np.float32)
    rgba[:, :, 0] = norm
    rgba[:, :, 1] = norm
    rgba[:, :, 2] = norm
    img.pixels.foreach_set(rgba.ravel())
    img.pack()
    return img, h_min, h_max


def _apply_ocean_coastline(heightmap, ocean_cfg, water_level, wx, wy, half_x, seed):
    """指定方角（または ISLAND で周囲360°）へ有機的な海岸線・浅瀬・海底を形成する"""
    h = heightmap.copy()
    region = str(ocean_cfg.get("region", "SOUTH")).upper()
    depth = float(ocean_cfg.get("depth", 75.0))
    shore_offset = float(ocean_cfg.get("shore_offset", 0.32))

    perm_c = _build_perm_table(seed + 911)
    coast_warp = (
        _value_noise_2d(wx * 0.00014 + 4.2, wy * 0.00014 + 9.1, perm_c) * (half_x * 0.16)
        + _value_noise_2d(wx * 0.00045 + 1.7, wy * 0.00045 + 2.3, perm_c) * (half_x * 0.05)
    )

    if region in ("ISLAND", "PERIMETER", "SURROUND"):
        # 絶海の孤島: 中心から放射状に海岸線を作り、外周360°を海底へ沈める
        r_dist = np.hypot(wx, wy) + coast_warp * 0.85
        island_r = half_x * 0.36
        shelf_w = half_x * 0.24
        t_sea = np.clip((r_dist - island_r) / max(shelf_w, 100.0), 0.0, 1.0)
        s_sea = t_sea * t_sea * (3.0 - 2.0 * t_sea)

        # 島内部を海面より少し持ち上げて安定した陸地にする
        land_boost = (1.0 - s_sea) * 45.0
        h = h + land_boost

        seabed_z = water_level - depth
        sea_target = seabed_z + np.clip(h - water_level, -20.0, 20.0) * 0.15
        return h * (1.0 - s_sea) + sea_target * s_sea

    # 海岸線の方向軸（正側が海）
    dir_map = {
        "NORTH": (0.0, 1.0),
        "SOUTH": (0.0, -1.0),
        "EAST": (1.0, 0.0),
        "WEST": (-1.0, 0.0),
        "NORTH_EAST": (0.707, 0.707),
        "NORTH_WEST": (-0.707, 0.707),
        "SOUTH_EAST": (0.707, -0.707),
        "SOUTH_WEST": (-0.707, -0.707),
    }
    dx, dy = dir_map.get(region, (0.0, -1.0))

    proj = wx * dx + wy * dy + coast_warp
    shore_line = half_x * shore_offset

    # 岸から海へ向かって 0 -> 1
    shelf_width = half_x * 0.28
    t_sea = np.clip((proj - shore_line) / max(shelf_width, 100.0), 0.0, 1.0)
    s_sea = t_sea * t_sea * (3.0 - 2.0 * t_sea)

    seabed_z = water_level - depth
    # 海側では元の地形を海底へ引き下げる（島や浅瀬を残すため少量の起伏を維持）
    sea_target = seabed_z + np.clip(h - water_level, -30.0, 30.0) * 0.22
    h = h * (1.0 - s_sea) + sea_target * s_sea
    return h


def _carve_rivers_into_heightmap(
    heightmap,
    flow_map,
    rivers,
    half_x,
    half_y,
    water_level=None,
):
    """
    川スプラインを地形の低い谷筋へ少し寄せつつ、下流へ向かって単調非増加な
    水面標高とU字型河床をハイトマップへ彫り込む。
    """
    h = heightmap.copy()
    fl = flow_map.copy() if flow_map is not None else np.zeros_like(h)
    res_y, res_x = h.shape
    dx_cell = (2.0 * half_x) / float(res_x - 1)
    dy_cell = (2.0 * half_y) / float(res_y - 1)

    compiled_rivers = []

    for r_spec in rivers:
        raw_pts = r_spec.get("pts", []) if isinstance(r_spec, dict) else r_spec
        if not raw_pts or len(raw_pts) < 2:
            continue
        base_width = float(r_spec.get("width", 120.0)) if isinstance(r_spec, dict) else 120.0
        base_depth = float(r_spec.get("depth", 18.0)) if isinstance(r_spec, dict) else 18.0

        # 高密度リサンプリング（約180mピッチ）
        dense_xy = []
        for i in range(len(raw_pts) - 1):
            x0, y0, _, _ = _extract_spline_pt(raw_pts[i])
            x1, y1, _, _ = _extract_spline_pt(raw_pts[i + 1])
            seg_len = math.hypot(x1 - x0, y1 - y0)
            n_sub = max(1, int(math.ceil(seg_len / 180.0)))
            for s in range(n_sub):
                t = s / float(n_sub)
                dense_xy.append([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t])
        x_last, y_last, _, _ = _extract_spline_pt(raw_pts[-1])
        dense_xy.append([x_last, y_last])

        # 谷筋方向への軽い誘導（端点を除く中間点を周囲の低い方へ寄せる）
        for _ in range(2):
            for i in range(1, len(dense_xy) - 1):
                px, py = dense_xy[i]
                best_x, best_y = px, py
                ix = int(np.clip(round((px + half_x) / dx_cell), 1, res_x - 2))
                iy = int(np.clip(round((py + half_y) / dy_cell), 1, res_y - 2))
                best_h = float(h[iy, ix])
                for ox, oy in ((-4, 0), (4, 0), (0, -4), (0, 4)):
                    nx_i = int(np.clip(ix + ox, 0, res_x - 1))
                    ny_i = int(np.clip(iy + oy, 0, res_y - 1))
                    nh = float(h[ny_i, nx_i])
                    if nh < best_h:
                        best_h = nh
                        best_x = -half_x + nx_i * dx_cell
                        best_y = -half_y + ny_i * dy_cell
                dense_xy[i][0] = px * 0.72 + best_x * 0.28
                dense_xy[i][1] = py * 0.72 + best_y * 0.28

        # 平滑化
        for _ in range(2):
            sm = [list(dense_xy[0])]
            for i in range(1, len(dense_xy) - 1):
                sm.append([
                    0.25 * dense_xy[i - 1][0] + 0.5 * dense_xy[i][0] + 0.25 * dense_xy[i + 1][0],
                    0.25 * dense_xy[i - 1][1] + 0.5 * dense_xy[i][1] + 0.25 * dense_xy[i + 1][1],
                ])
            sm.append(list(dense_xy[-1]))
            dense_xy = sm

        # 各点での水面標高をサンプリングし、下流へ向かって単調非増加にする
        water_zs = []
        for idx_p, (px, py) in enumerate(dense_xy):
            ix = int(np.clip(round((px + half_x) / dx_cell), 0, res_x - 1))
            iy = int(np.clip(round((py + half_y) / dy_cell), 0, res_y - 1))
            gz = float(h[iy, ix])
            # 下流に向かって川幅が少し広がる
            if water_level is not None:
                gz = max(gz, float(water_level))
            if idx_p == 0:
                water_zs.append(gz - 2.0)
            else:
                # 谷を登らないよう、前点以下へクランプしつつ緩やかに下る
                prev_z = water_zs[-1]
                target_z = min(prev_z - 0.15, gz - 2.0)
                if water_level is not None:
                    target_z = max(float(water_level), target_z)
                water_zs.append(target_z)

        # 河床の彫り込み（U字プロファイル）
        river_points_out = []
        n_pts = len(dense_xy)
        for i in range(n_pts - 1):
            x0, y0 = dense_xy[i]
            x1, y1 = dense_xy[i + 1]
            wz0 = water_zs[i]
            wz1 = water_zs[i + 1]
            t_prog = i / max(1.0, float(n_pts - 1))
            w_local = base_width * (0.65 + 0.75 * t_prog)

            if i == 0:
                river_points_out.append([round(x0, 2), round(y0, 2), round(wz0, 2), round(w_local, 2)])
            river_points_out.append([round(x1, 2), round(y1, 2), round(wz1, 2), round(w_local, 2)])

            half_w = w_local * 0.5
            bank_w = w_local * 1.45
            max_r = half_w + bank_w

            ix0 = max(0, int(math.floor((min(x0, x1) - max_r + half_x) / dx_cell)))
            ix1 = min(res_x - 1, int(math.ceil((max(x0, x1) + max_r + half_x) / dx_cell)))
            iy0 = max(0, int(math.floor((min(y0, y1) - max_r + half_y) / dy_cell)))
            iy1 = min(res_y - 1, int(math.ceil((max(y0, y1) + max_r + half_y) / dy_cell)))
            if ix1 < ix0 or iy1 < iy0:
                continue

            xs = -half_x + np.arange(ix0, ix1 + 1, dtype=np.float32) * dx_cell
            ys = -half_y + np.arange(iy0, iy1 + 1, dtype=np.float32) * dy_cell
            gx, gy = np.meshgrid(xs, ys, indexing="xy")

            vx = x1 - x0
            vy = y1 - y0
            seg_len2 = vx * vx + vy * vy
            proj = np.zeros_like(gx) if seg_len2 < 1e-4 else np.clip(((gx - x0) * vx + (gy - y0) * vy) / seg_len2, 0.0, 1.0)
            dist = np.hypot(gx - (x0 + vx * proj), gy - (y0 + vy * proj))

            wz_seg = wz0 + (wz1 - wz0) * proj
            bed_z = wz_seg - base_depth

            # 中心は bed_z まで彫り、岸辺で周辺地形へ滑らかに接続
            u = np.clip((dist - half_w) / max(bank_w, 1.0), 0.0, 1.0)
            carve_w = 1.0 - (u * u * (3.0 - 2.0 * u))

            sub_h = h[iy0:iy1 + 1, ix0:ix1 + 1]
            carved = np.minimum(sub_h, bed_z + (sub_h - bed_z) * (1.0 - carve_w))
            h[iy0:iy1 + 1, ix0:ix1 + 1] = carved

            sub_fl = fl[iy0:iy1 + 1, ix0:ix1 + 1]
            np.maximum(sub_fl, carve_w * 0.95, out=sub_fl)

        compiled_rivers.append({
            "width": round(base_width, 2),
            "points": river_points_out,
        })

    return h, fl, compiled_rivers


def compute_shore_distance_field(heightmap, water_level, max_dist_px=48):
    """
    Pure NumPy 2パス Chamfer 距離変換により、海岸線からのオフショア距離場 [0, 1] を算出する。
    陸地=0.0, 岸辺=0.0付近, 深海=1.0。
    """
    res_y, res_x = heightmap.shape
    is_water = heightmap <= float(water_level)
    dist = np.where(is_water, float(max_dist_px), 0.0).astype(np.float32)

    # Forward & Backward 2-pass Chamfer propagation
    for _ in range(2):
        # Down-Right
        for r in range(1, res_y):
            dist[r, 1:-1] = np.minimum(dist[r, 1:-1], dist[r - 1, 1:-1] + 1.0)
            dist[r, 1:-1] = np.minimum(dist[r, 1:-1], dist[r - 1, :-2] + 1.414)
            dist[r, 1:-1] = np.minimum(dist[r, 1:-1], dist[r - 1, 2:] + 1.414)
        for c in range(1, res_x):
            dist[:, c] = np.minimum(dist[:, c], dist[:, c - 1] + 1.0)
        # Up-Left
        for r in range(res_y - 2, -1, -1):
            dist[r, 1:-1] = np.minimum(dist[r, 1:-1], dist[r + 1, 1:-1] + 1.0)
            dist[r, 1:-1] = np.minimum(dist[r, 1:-1], dist[r + 1, :-2] + 1.414)
            dist[r, 1:-1] = np.minimum(dist[r, 1:-1], dist[r + 1, 2:] + 1.414)
        for c in range(res_x - 2, -1, -1):
            dist[:, c] = np.minimum(dist[:, c], dist[:, c + 1] + 1.0)

    return np.clip(dist / max(float(max_dist_px), 1.0), 0.0, 1.0).astype(np.float32)
