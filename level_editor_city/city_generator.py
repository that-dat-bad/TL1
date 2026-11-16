# -*- coding: utf-8 -*-
import math
import random

"""
プロシージャル都市・道路ネットワークジェネレータ。
ユーザーの厳格な要件に完全対応：
1. 「直線を多用しすぎ」-> 直線セグメントを完全撤廃。すべての道路が緩やかなS字や円弧を描く自然な曲線（All-Curved Winding Roads）。
2. 「中途半端な道を創るな」-> 外側の出っ張りやヒゲ、行き止まりを完全撤廃。すべての道路が幹線・バイパス間または大通り同士を完全に結び抜ける完全貫通ネットワーク。
3. 「対称性を持たせるな」-> 卵型・有機的非対称レイアウト（東西南北で広がり・曲率が異なる）。
4. 「90度の四角を作るな」-> 斜め貫通大通りと曲線街路による不規則な多角形・台形・三角形街区。
"""

BOUND_LIMIT = 18000.0

def clamp(val, min_v, max_v):
    return max(min_v, min(max_v, val))

def clamp_point(p, bound=BOUND_LIMIT):
    return [clamp(p[0], -bound, bound), clamp(p[1], -bound, bound), p[2]]

def pseudo_noise2d(x, y, seed=0):
    v = math.sin(x * 0.00065 + y * 0.00038 + seed * 1.7) * 0.55
    v += math.sin(x * 0.00142 - y * 0.00118 + seed * 3.3) * 0.30
    v += math.cos(x * 0.00285 + y * 0.00241 + seed * 5.1) * 0.15
    return v

def catmull_rom_spline(p0, p1, p2, p3, num_points=8):
    """4つの制御点から Catmull-Rom スプライン補間点を生成"""
    pts = []
    for i in range(num_points):
        t = i / float(num_points)
        t2 = t * t
        t3 = t2 * t
        f0 = -0.5 * t3 + t2 - 0.5 * t
        f1 =  1.5 * t3 - 2.5 * t2 + 1.0
        f2 = -1.5 * t3 + 2.0 * t2 + 0.5 * t
        f3 =  0.5 * t3 - 0.5 * t2
        x = p0[0] * f0 + p1[0] * f1 + p2[0] * f2 + p3[0] * f3
        y = p0[1] * f0 + p1[1] * f1 + p2[1] * f2 + p3[1] * f3
        z = p0[2] * f0 + p1[2] * f1 + p2[2] * f2 + p3[2] * f3
        pts.append([x, y, z])
    return pts

def smooth_curve(points, max_seg_len=12.0, bound=BOUND_LIMIT, chaikin_iters=3, min_dist=5.0, max_turn_deg=15.0):
    """
    制御点列に対して Chaikin コーナーカッティング (3回反復) + Catmull-Rom 補間を適用し、
    12m 間隔へのリサンプリング・5m 未満の重複頂点マージ・折れ角 15度超の急折れ平滑化を行って
    直角折れやV字自己交差による Z-fighting を完全に解消する。
    """
    if len(points) < 2:
        return [clamp_point(p, bound) for p in points]

    def _dedup(seq, md):
        if not seq:
            return []
        out = [clamp_point(seq[0], bound)]
        for p in seq[1:]:
            q = clamp_point(p, bound)
            if math.hypot(q[0] - out[-1][0], q[1] - out[-1][1]) >= md:
                out.append(q)
        if len(out) == 1 and len(seq) >= 2:
            out.append(clamp_point(seq[-1], bound))
        elif len(seq) >= 2:
            end_p = clamp_point(seq[-1], bound)
            if math.hypot(end_p[0] - out[-1][0], end_p[1] - out[-1][1]) < md and len(out) >= 2:
                out[-1] = end_p
            elif math.hypot(end_p[0] - out[-1][0], end_p[1] - out[-1][1]) >= 1e-3:
                out.append(end_p)
        return out

    pts = _dedup(points, min_dist)
    if len(pts) < 2:
        return pts

    # Chaikin コーナーカッティング (3回反復) で角を大半径カーブ (R >= 150m) に丸める
    if len(pts) >= 3:
        for _ in range(max(1, int(chaikin_iters))):
            next_pts = [list(pts[0])]
            for i in range(len(pts) - 1):
                p0, p1 = pts[i], pts[i + 1]
                q = [0.75 * p0[0] + 0.25 * p1[0], 0.75 * p0[1] + 0.25 * p1[1], 0.75 * p0[2] + 0.25 * p1[2]]
                r = [0.25 * p0[0] + 0.75 * p1[0], 0.25 * p0[1] + 0.75 * p1[1], 0.25 * p0[2] + 0.75 * p1[2]]
                next_pts.append(q)
                next_pts.append(r)
            next_pts.append(list(pts[-1]))
            pts = next_pts

    # Catmull-Rom 補間 + 等間隔 (12m) リサンプリング
    if len(pts) == 2:
        p1, p2 = pts[0], pts[1]
        dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        n = max(2, int(math.ceil(dist / max(5.0, max_seg_len))))
        smoothed = [
            clamp_point([p1[0] + (p2[0] - p1[0]) * i / n, p1[1] + (p2[1] - p1[1]) * i / n, p1[2] + (p2[2] - p1[2]) * i / n], bound)
            for i in range(n + 1)
        ]
    else:
        p_start = [2 * pts[0][0] - pts[1][0], 2 * pts[0][1] - pts[1][1], pts[0][2]]
        p_end = [2 * pts[-1][0] - pts[-2][0], 2 * pts[-1][1] - pts[-2][1], pts[-1][2]]
        ext = [p_start] + pts + [p_end]
        smoothed = []
        for i in range(len(pts) - 1):
            p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
            chord = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            n_sub = max(2, int(math.ceil(chord / max(5.0, max_seg_len))))
            sub = catmull_rom_spline(p0, p1, p2, p3, n_sub)
            smoothed.extend([clamp_point(p, bound) for p in sub])
        smoothed.append(clamp_point(pts[-1], bound))

    smoothed = _dedup(smoothed, min_dist)

    # 折れ角 > 15度 の急折れ点を反復平滑化
    cos_lim = math.cos(math.radians(max_turn_deg))
    for _ in range(10):
        if len(smoothed) < 3:
            break
        changed = False
        upd = [list(p) for p in smoothed]
        for i in range(1, len(smoothed) - 1):
            pa, pb, pc = smoothed[i - 1], smoothed[i], smoothed[i + 1]
            ux, uy = pb[0] - pa[0], pb[1] - pa[1]
            vx, vy = pc[0] - pb[0], pc[1] - pb[1]
            lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
            if lu < 1e-4 or lv < 1e-4:
                continue
            if (ux * vx + uy * vy) / (lu * lv) < cos_lim:
                upd[i][0] = clamp(0.30 * pa[0] + 0.40 * pb[0] + 0.30 * pc[0], -bound, bound)
                upd[i][1] = clamp(0.30 * pa[1] + 0.40 * pb[1] + 0.30 * pc[1], -bound, bound)
                upd[i][2] = 0.30 * pa[2] + 0.40 * pb[2] + 0.30 * pc[2]
                changed = True
        smoothed = _dedup(upd, min_dist)
        if not changed:
            break

    return smoothed

def make_curved_link(p1, p2, curve_amp=0.08, s_curve_amp=0.05, seed=1, bound=BOUND_LIMIT):
    """
    2点間を「直線」ではなく、有機的に曲がりくねるS字・弧の道路に変換。
    「直線を多用しすぎ」を完全解消。
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < 20.0:
        return [clamp_point(p1, bound), clamp_point(p2, bound)]

    nx = -dy / dist
    ny =  dx / dist

    num_mid = 3
    pts = [p1]
    sign = 1.0 if pseudo_noise2d(p1[0], p1[1], seed) > 0 else -1.0

    for k in range(1, num_mid + 1):
        t = k / float(num_mid + 1)
        bx = p1[0] + dx * t
        by = p1[1] + dy * t

        arc = math.sin(math.pi * t) * (dist * curve_amp) * sign
        s_curve = math.sin(2.0 * math.pi * t) * (dist * s_curve_amp) * (-sign)
        noise = pseudo_noise2d(bx, by, seed=seed+5) * (dist * 0.04)

        offset = arc + s_curve + noise
        pts.append([bx + nx * offset, by + ny * offset, 0.0])

    pts.append(p2)
    return smooth_curve(pts, max_seg_len=40.0, bound=bound)

class ProceduralCityGenerator:
    def __init__(self, terrain_size_x=40000, terrain_size_y=40000, seed: int = None, city_style: str = "ORGANIC"):
        self.size_x = float(terrain_size_x)
        self.size_y = float(terrain_size_y)
        self.bound = min(self.size_x, self.size_y) * 0.44
        self.scale_factor = self.size_x / 20000.0
        self.seed = int(seed) if seed is not None else 2026
        self.city_style = (city_style or "ORGANIC").upper()
        if self.city_style not in ("GRID", "RADIAL", "ORGANIC", "LINEAR", "TWIN_CITY", "HARBOR"):
            self.city_style = "ORGANIC"
        self.rng = random.Random(self.seed)
        self.all_points = []
        self.generated_splines = []
        self.spline_metadata = []
        self.city_blocks = []
        self.city_center = (self.size_x * 0.12, -200.0, 0.0)
        self.cbd_center = self.city_center

    def _clamp_point(self, p):
        return clamp_point(p, self.bound)

    def _add_spline(self, pts, is_main=False, road_type="STREET", cyclic=False):
        if len(pts) < 2:
            return
        self.generated_splines.append(pts)
        self.spline_metadata.append({'is_main': is_main, 'type': road_type, 'cyclic': cyclic})
        self.all_points.extend(pts)

    @staticmethod
    def _build_mt_segments(mountains):
        segs = []
        if not mountains:
            return segs
        for mt in mountains:
            if not mt or len(mt) < 2:
                continue
            for j in range(len(mt) - 1):
                a, b = mt[j], mt[j + 1]
                if isinstance(a, dict):
                    ca = a.get("co", [0.0, 0.0, 0.0])
                    x1, y1, r1 = float(ca[0]), float(ca[1]), float(a.get("radius", 1.0))
                else:
                    x1, y1, r1 = float(a[0]), float(a[1]), (float(a[3]) if len(a) >= 4 else 1.0)
                if isinstance(b, dict):
                    cb = b.get("co", [0.0, 0.0, 0.0])
                    x2, y2, r2 = float(cb[0]), float(cb[1]), float(b.get("radius", 1.0))
                else:
                    x2, y2, r2 = float(b[0]), float(b[1]), (float(b[3]) if len(b) >= 4 else 1.0)
                segs.append((x1, y1, r1, x2, y2, r2))
        return segs

    @staticmethod
    def _dist_to_mt_segments(px, py, mt_segs, base_radius):
        if not mt_segs or base_radius <= 0.0:
            return 1e18, base_radius
        best_d = 1e18
        best_r = base_radius
        for x1, y1, r1, x2, y2, r2 in mt_segs:
            dx, dy = x2 - x1, y2 - y1
            len_sq = dx * dx + dy * dy
            if len_sq < 1e-6:
                t = 0.0
                cx_m, cy_m = x1, y1
            else:
                t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / len_sq))
                cx_m, cy_m = x1 + t * dx, y1 + t * dy
            d = math.hypot(px - cx_m, py - cy_m)
            if d < best_d:
                best_d = d
                best_r = base_radius * max(0.35, r1 + (r2 - r1) * t)
        return best_d, best_r

    def _truncate_street_at_mountains(self, pts, mt_segs, mt_radius):
        """
        山麓に突入する街路を山裾ライン (mt_radius * 1.05) で打ち切り、
        境界点を収集して山麓外周コレクター道路へ接続できるようにする。
        """
        if not mt_segs or mt_radius <= 0.0:
            return [pts], []
        kept_segments = []
        current = []
        boundary_pts = []
        for p in pts:
            d, eff_r = self._dist_to_mt_segments(p[0], p[1], mt_segs, mt_radius)
            if d >= eff_r * 1.05:
                current.append(p)
            else:
                if len(current) >= 2:
                    kept_segments.append(current)
                    boundary_pts.append(current[-1])
                elif len(current) == 1:
                    boundary_pts.append(current[0])
                current = []
        if len(current) >= 2:
            kept_segments.append(current)
        return kept_segments, boundary_pts

    def generate_road_network(self, base_roads, terrain_data=None):
        """
        現実の都市計画に基づく3階層ネットワークを生成:
          Tier 1: マップを横断する2〜3本の緩やかな蛇行幹線道路（中心1点集中を回避）
          Tier 2: 複数地区（角度の異なる街区グリッド: 120m〜250m間隔）による矩形・台形ブロック網
          Tier 3: 山麓・谷沿い外周コレクターによる打ち切り・接続
        """
        self.generated_splines = []
        self.spline_metadata = []
        self.all_points = []
        self.city_blocks = []

        active_seed = self.seed
        style = self.city_style
        mountains = []
        mountain_radius = 0.0
        valleys = []
        valley_radius = 0.0
        prompt_text = ""

        if isinstance(terrain_data, dict):
            if terrain_data.get("seed") is not None:
                try:
                    active_seed = int(terrain_data["seed"])
                except (TypeError, ValueError):
                    pass
            if terrain_data.get("city_style"):
                s_cand = str(terrain_data["city_style"]).upper()
                if s_cand in ("GRID", "RADIAL", "ORGANIC", "LINEAR", "TWIN_CITY", "HARBOR"):
                    style = s_cand
            mountains = terrain_data.get("mountains", []) or []
            mountain_radius = float(terrain_data.get("mountain_radius", 0.0) or 0.0)
            valleys = terrain_data.get("valleys", []) or []
            valley_radius = float(terrain_data.get("valley_radius", 0.0) or 0.0)
            prompt_text = str(terrain_data.get("prompt", "") or "").lower()

        self.seed = active_seed
        self.city_style = style
        self.rng = random.Random(active_seed)
        rng = self.rng

        # プロンプトやシードから都市形態（単核/双子/谷沿い細長/港湾）を決定
        if any(k in prompt_text for k in ("双子", "twin", "両岸")):
            morphology = "TWIN_CITY"
        elif style == "LINEAR" or any(k in prompt_text for k in ("宿場", "細長", "谷沿", "街道", "corridor", "linear")):
            morphology = "LINEAR"
        elif style == "HARBOR" or any(k in prompt_text for k in ("港", "海岸", "湾", "harbor", "port", "coastal")):
            morphology = "HARBOR"
        else:
            morph_choices = ("MONOCENTRIC", "MONOCENTRIC", "TWIN_CITY", "LINEAR")
            morphology = morph_choices[rng.randint(0, len(morph_choices) - 1)] if style == "ORGANIC" else "MONOCENTRIC"

        b = self.bound
        sf = self.scale_factor
        mt_segs = self._build_mt_segments(mountains)
        vl_segs = self._build_mt_segments(valleys)

        raw_city_scale = float(terrain_data.get("city_scale", 1.0)) if isinstance(terrain_data, dict) else 1.0
        is_full_map = bool(terrain_data.get("is_full_map_city", False)) if isinstance(terrain_data, dict) else False
        # 通常時 (is_full_map == False) は 40km マップで都市半径 3,000m 〜 5,000m (直径 6km〜10km) に収める
        city_scale = (8.0 if is_full_map else clamp(raw_city_scale, 0.75, 1.45) * sf)
        self.city_scale = city_scale
        self.is_full_map_city = is_full_map

        # 0. 方角 (orientation) を最優先で反映
        orientation_str = str(terrain_data.get("orientation", "") or "").upper() if isinstance(terrain_data, dict) else ""
        orient_map = {
            "EAST_WEST": 0.0,
            "WEST_TO_EAST": 0.0,
            "EAST_TO_WEST": 0.0,
            "NORTH_SOUTH": math.pi * 0.5,
            "NORTH_TO_SOUTH": math.pi * 0.5,
            "SOUTH_TO_NORTH": math.pi * 0.5,
            "NW_SE": -math.pi * 0.25,
            "NE_SW": math.pi * 0.25,
        }
        if orientation_str in orient_map:
            base_ang = orient_map[orientation_str] + rng.uniform(-0.08, 0.08)
        else:
            base_ang = rng.uniform(-0.55, 0.55)

        # 1. 都市中心座標および複数都市ゾーン (city_zones) の決定
        city_lim = b * 0.82
        raw_zones = terrain_data.get("city_zones") if isinstance(terrain_data, dict) else None
        resolved_zones = []
        if isinstance(raw_zones, list) and len(raw_zones) > 0:
            for z_item in raw_zones:
                if not isinstance(z_item, dict):
                    continue
                zc = z_item.get("center", [0.0, 0.0, 0.0])
                zsc = clamp(float(z_item.get("scale", raw_city_scale)), 0.75, 1.45)
                jit_scale = 0.0 if is_full_map else 250.0
                zx = clamp(float(zc[0]) + rng.uniform(-jit_scale, jit_scale), -city_lim, city_lim)
                zy = clamp(float(zc[1]) + rng.uniform(-jit_scale, jit_scale), -city_lim, city_lim)
                resolved_zones.append({
                    "cx": zx,
                    "cy": zy,
                    "scale": 8.0 if is_full_map else max(0.75, zsc * sf),
                    "region": str(z_item.get("region", "CENTER")).upper(),
                })

        if not resolved_zones:
            if isinstance(terrain_data, dict) and terrain_data.get("city_center"):
                tc = terrain_data["city_center"]
                jit_x = 0.0 if is_full_map else rng.uniform(-350.0, 350.0)
                jit_y = 0.0 if is_full_map else rng.uniform(-350.0, 350.0)
                zx = clamp(float(tc[0]) + jit_x, -city_lim, city_lim)
                zy = clamp(float(tc[1]) + jit_y, -city_lim, city_lim)
            else:
                zx = 0.0 if is_full_map else rng.uniform(-2200.0, 2200.0)
                zy = 0.0 if is_full_map else rng.uniform(-1800.0, 1800.0)
            resolved_zones.append({
                "cx": zx,
                "cy": zy,
                "scale": city_scale,
                "region": "CENTER",
            })

        self.city_center = (resolved_zones[0]["cx"], resolved_zones[0]["cy"], 0.0)
        cx, cy, _ = self.city_center
        self.cbd_center = (cx, cy, 0.0)
        self.cbd_centers = [(z["cx"], z["cy"]) for z in resolved_zones]

        # =====================================================================
        # Tier 1: 広域幹線道路（複数都市間を結ぶ東西/南北コリドー + 各都市の幹線）
        # =====================================================================
        if len(resolved_zones) >= 2:
            # 複数都市（例: 東西の2都市）を直結するメインハイウェイを最優先で生成
            z_sorted = sorted(resolved_zones, key=lambda z: z["cx"] * math.cos(base_ang) + z["cy"] * math.sin(base_ang))
            p_first = (z_sorted[0]["cx"], z_sorted[0]["cy"])
            p_last = (z_sorted[-1]["cx"], z_sorted[-1]["cy"])
            dx_ew = p_last[0] - p_first[0]
            dy_ew = p_last[1] - p_first[1]
            len_ew = max(1.0, math.hypot(dx_ew, dy_ew))
            ux_ew, uy_ew = dx_ew / len_ew, dy_ew / len_ew
            nx_ew, ny_ew = -uy_ew, ux_ew
            for lane_off in (-260.0 * sf, 260.0 * sf):
                corridor_pts = [
                    [clamp(p_first[0] - ux_ew * 3500.0 * sf + nx_ew * lane_off, -b, b),
                     clamp(p_first[1] - uy_ew * 3500.0 * sf + ny_ew * lane_off, -b, b), 0.0],
                    [clamp(p_first[0] + nx_ew * lane_off, -b, b),
                     clamp(p_first[1] + ny_ew * lane_off, -b, b), 0.0],
                    [clamp(0.5 * (p_first[0] + p_last[0]) + nx_ew * (lane_off + rng.uniform(-350.0, 350.0)), -b, b),
                     clamp(0.5 * (p_first[1] + p_last[1]) + ny_ew * (lane_off + rng.uniform(-350.0, 350.0)), -b, b), 0.0],
                    [clamp(p_last[0] + nx_ew * lane_off, -b, b),
                     clamp(p_last[1] + ny_ew * lane_off, -b, b), 0.0],
                    [clamp(p_last[0] + ux_ew * 3500.0 * sf + nx_ew * lane_off, -b, b),
                     clamp(p_last[1] + uy_ew * 3500.0 * sf + ny_ew * lane_off, -b, b), 0.0],
                ]
                self._add_spline(
                    smooth_curve(corridor_pts, max_seg_len=15.0, bound=b),
                    is_main=True,
                    road_type='ARTERIAL_HIGHWAY',
                )
        else:
            num_highways = 4 if is_full_map else 2
            for h_idx in range(num_highways):
                ang = base_ang + h_idx * (math.pi / num_highways) + rng.uniform(-0.12, 0.12)
                cos_h, sin_h = math.cos(ang), math.sin(ang)
                nx_h, ny_h = -sin_h, cos_h
                shift_perp = (0.0 if h_idx == 0 else rng.uniform(-520.0, 520.0) * sf)
                bend1 = rng.uniform(-1100.0, 1100.0) * sf
                bend2 = rng.uniform(-1100.0, 1100.0) * sf

                def hw_pt(along, perp_extra):
                    px = cx + along * cos_h + nx_h * (shift_perp + perp_extra)
                    py = cy + along * sin_h + ny_h * (shift_perp + perp_extra)
                    return [clamp(px, -b, b), clamp(py, -b, b), 0.0]

                pts = [
                    hw_pt(-b * 0.98, bend1 * 0.55),
                    hw_pt(-5600.0 * sf, bend1 * 0.35),
                    hw_pt(-1800.0, -bend2 * 0.12),
                    hw_pt(0.0, rng.uniform(-90.0, 90.0)),
                    hw_pt(1800.0, bend2 * 0.12),
                    hw_pt(5600.0 * sf, -bend1 * 0.35),
                    hw_pt(b * 0.98, bend2 * 0.55),
                ]
                self._add_spline(
                    smooth_curve(pts, max_seg_len=15.0, bound=b),
                    is_main=True,
                    road_type='ARTERIAL_HIGHWAY',
                )

        # 2.5 有機的都市領域マスク（通常時は40kmマップで半径 3,000m〜5,000m に厳格制限、全域都市モードのみ全域 1.0）
        hub_centers = []
        for z_info in resolved_zones:
            zx, zy, zsc = z_info["cx"], z_info["cy"], z_info["scale"]
            # 40km時 sf=2.0 でも都市半径が 3,000m〜5,000m（直径6km〜10km）に収まるよう有効スケールをクランプ
            eff_sc = clamp(zsc, 0.85 * sf, 1.15 * sf) if not is_full_map else 8.0
            if morphology == "TWIN_CITY" and len(resolved_zones) == 1 and not is_full_map:
                sep_tmp = rng.uniform(1100.0, 1450.0) * sf
                hub_centers.append((zx - math.cos(base_ang) * sep_tmp * 0.5, zy - math.sin(base_ang) * sep_tmp * 0.5, eff_sc))
                hub_centers.append((zx + math.cos(base_ang) * sep_tmp * 0.5, zy + math.sin(base_ang) * sep_tmp * 0.5, eff_sc))
            else:
                hub_centers.append((zx, zy, eff_sc))

        max_urban_radius = 4800.0 * (sf / 2.0)  # 40km時に中心から最大 4,800m でハードカット

        def _urban_mask_score(px, py):
            if is_full_map:
                return 1.0
            best_s = 0.0
            for hx, hy, h_sc in hub_centers:
                dx_u = px - hx
                dy_u = py - hy
                dist = math.hypot(dx_u, dy_u)
                if dist > max_urban_radius:
                    continue
                ang_u = math.atan2(dy_u, dx_u)
                base_r = clamp(1850.0 * h_sc, 3000.0 * (sf / 2.0), 4400.0 * (sf / 2.0))
                sprawl_r = min(
                    max_urban_radius,
                    base_r * (
                        1.0
                        + 0.14 * math.cos(2.0 * (ang_u - base_ang))
                        + 0.10 * math.sin(3.0 * ang_u + active_seed * 0.13)
                        + 0.10 * pseudo_noise2d(px * 0.8, py * 0.8, seed=active_seed)
                    ),
                )
                if morphology == "LINEAR":
                    along = abs(dx_u * math.cos(base_ang) + dy_u * math.sin(base_ang))
                    perp = abs(-dx_u * math.sin(base_ang) + dy_u * math.cos(base_ang))
                    eff_d = math.hypot(along * 0.65, perp * 1.35)
                else:
                    eff_d = dist
                s = max(0.0, 1.0 - eff_d / max(600.0, sprawl_r))
                if s > best_s:
                    best_s = s
            return best_s

        # =====================================================================
        # Tier 2: 多段階の都市街区グリッド（通常時は半径 3,000m〜5,000m 以内に厳格配置）
        # =====================================================================
        districts = []
        theta0 = base_ang + rng.uniform(-0.08, 0.08)

        if is_full_map:
            # 全域メガシティ: マップ全体 (-b*0.92 〜 +b*0.92) を覆う広域グリッド
            districts.append({
                'cx': 0.0, 'cy': 0.0,
                'angle': theta0,
                'half_u': b * 0.92, 'half_v': b * 0.92,
                'is_cbd': True,
                'is_full_map': True,
            })
            # 都心ハブを複数配置してスカイラインに抑揚をつける
            self.cbd_centers = [
                (0.0, 0.0),
                (-b * 0.45, -b * 0.35),
                (b * 0.45, b * 0.35),
                (-b * 0.40, b * 0.40),
                (b * 0.40, -b * 0.40),
            ]
        else:
            for z_idx, z_info in enumerate(resolved_zones):
                zx, zy, zsc = z_info["cx"], z_info["cy"], z_info["scale"]
                eff_sc = clamp(zsc, 0.85 * sf, 1.15 * sf)
                z_theta = theta0 + z_idx * rng.uniform(-0.12, 0.12)
                if morphology == "TWIN_CITY" and len(resolved_zones) == 1:
                    districts.append({
                        'cx': hub_centers[0][0], 'cy': hub_centers[0][1],
                        'angle': z_theta + rng.uniform(-0.12, 0.12),
                        'half_u': 1400.0 * eff_sc, 'half_v': 1300.0 * eff_sc,
                        'is_cbd': True,
                    })
                    districts.append({
                        'cx': hub_centers[1][0], 'cy': hub_centers[1][1],
                        'angle': z_theta + rng.uniform(0.22, 0.45),
                        'half_u': 1250.0 * eff_sc, 'half_v': 1150.0 * eff_sc,
                        'is_cbd': True,
                    })
                elif morphology == "LINEAR":
                    for k, offset_u in enumerate((-950.0 * eff_sc, 0.0, 950.0 * eff_sc)):
                        d_ang = z_theta + (k - 1) * rng.uniform(-0.10, 0.10)
                        districts.append({
                            'cx': zx + math.cos(z_theta) * offset_u,
                            'cy': zy + math.sin(z_theta) * offset_u + rng.uniform(-100.0, 100.0) * eff_sc,
                            'angle': d_ang,
                            'half_u': 950.0 * eff_sc,
                            'half_v': 800.0 * eff_sc,
                            'is_cbd': (k == 1),
                        })
                elif morphology == "HARBOR":
                    districts.append({
                        'cx': zx, 'cy': zy,
                        'angle': z_theta,
                        'half_u': 1500.0 * eff_sc, 'half_v': 1200.0 * eff_sc,
                        'is_cbd': True,
                    })
                    inland_ang = z_theta + rng.uniform(0.25, 0.50)
                    districts.append({
                        'cx': zx - math.sin(z_theta) * 750.0 * eff_sc,
                        'cy': zy + math.cos(z_theta) * 750.0 * eff_sc,
                        'angle': inland_ang,
                        'half_u': 1200.0 * eff_sc, 'half_v': 1050.0 * eff_sc,
                        'is_cbd': False,
                    })
                else:
                    districts.append({
                        'cx': zx, 'cy': zy,
                        'angle': z_theta,
                        'half_u': 1600.0 * eff_sc, 'half_v': 1500.0 * eff_sc,
                        'is_cbd': True,
                    })
                    for side_idx in range(rng.randint(1, 2)):
                        d_theta = z_theta + (1 if side_idx == 0 else -1) * rng.uniform(0.25, 0.52)
                        off_ang = z_theta + side_idx * 2.2 + rng.uniform(-0.30, 0.30)
                        off_dist = rng.uniform(750.0, 1050.0) * eff_sc
                        districts.append({
                            'cx': zx + math.cos(off_ang) * off_dist,
                            'cy': zy + math.sin(off_ang) * off_dist,
                            'angle': d_theta,
                            'half_u': 1150.0 * eff_sc, 'half_v': 1050.0 * eff_sc,
                            'is_cbd': False,
                        })

        for dist_cfg in districts:
            self._build_district_grid(dist_cfg, b, rng, mt_segs, mountain_radius, vl_segs, valley_radius, _urban_mask_score)

        return self.generated_splines

    def _clip_street_to_urban_and_mt(self, pts, mt_segs, mt_radius, vl_segs, vl_radius, urban_mask_fn):
        """
        街路を「有機的都市マスク内（score > 0.22）」、「山麓外側（d_mt >= eff_r * 1.05）」、
        かつ「谷領域外側（d_vl >= eff_vr * 0.95）」の区間だけにクリップして返す。
        これにより細街路が谷の上を横断して白い橋脚を大量発生させる現象を完全に防止する。
        """
        kept_segments = []
        current = []
        for p in pts:
            in_urban = urban_mask_fn(p[0], p[1]) > 0.22
            out_mt = True
            if mt_segs and mt_radius > 0.0:
                d_mt, eff_r = self._dist_to_mt_segments(p[0], p[1], mt_segs, mt_radius)
                out_mt = (d_mt >= eff_r * 1.05)
            out_vl = True
            if vl_segs and vl_radius > 0.0:
                d_vl, eff_vr = self._dist_to_mt_segments(p[0], p[1], vl_segs, vl_radius)
                out_vl = (d_vl >= eff_vr * 0.95)
            if in_urban and out_mt and out_vl:
                current.append(p)
            else:
                if len(current) >= 2:
                    kept_segments.append(current)
                current = []
        if len(current) >= 2:
            kept_segments.append(current)
        return kept_segments

    def _build_district_grid(self, cfg, b, rng, mt_segs, mt_radius, vl_segs, vl_radius, urban_mask_fn):
        """
        1つの都市地区内に細街路・補助幹線グリッドと街区ブロック（self.city_blocks）を構築する。
        全域都市モード（is_full_map / city_scale >= 4.0）では 350m〜550m 間隔で40km全域を覆う。
        """
        dcx, dcy = cfg['cx'], cfg['cy']
        ang = cfg['angle']
        cos_a, sin_a = math.cos(ang), math.sin(ang)
        half_u, half_v = cfg['half_u'], cfg['half_v']
        is_full = bool(cfg.get('is_full_map', False)) or bool(getattr(self, 'is_full_map_city', False))

        def to_world(u, v):
            return [clamp(dcx + u * cos_a - v * sin_a, -b, b), clamp(dcy + u * sin_a + v * cos_a, -b, b), 0.0]

        step_min = 380.0 if is_full else 85.0
        step_max = 540.0 if is_full else 135.0
        seg_res = 24.0 if is_full else 15.0

        u_coords = [-half_u]
        cur = -half_u
        while cur < half_u - step_min * 0.8:
            step = rng.uniform(step_min, step_max)
            if cur + step > half_u:
                break
            cur += step
            u_coords.append(cur)
        if half_u - u_coords[-1] >= step_min * 0.5:
            u_coords.append(half_u)

        v_coords = [-half_v]
        cur = -half_v
        while cur < half_v - step_min * 0.8:
            step = rng.uniform(step_min, step_max)
            if cur + step > half_v:
                break
            cur += step
            v_coords.append(cur)
        if half_v - v_coords[-1] >= step_min * 0.5:
            v_coords.append(half_v)

        # わずかな地形追従の湾曲
        warp_u = rng.uniform(-28.0, 28.0)
        warp_v = rng.uniform(-28.0, 28.0)

        def warped_world(u, v):
            tu = u / max(1.0, half_u)
            tv = v / max(1.0, half_v)
            du = math.sin(tv * math.pi * 0.7) * warp_u
            dv = math.sin(tu * math.pi * 0.7) * warp_v
            return to_world(u + du, v + dv)

        # U方向街路（外周の四角い枠線強調はせず、中央・3本おきに補助幹線を配置）
        for iv, v0 in enumerate(v_coords):
            raw_pts = [warped_world(u0, v0) for u0 in u_coords]
            is_ave = (iv % 4 == 2)
            segs = self._clip_street_to_urban_and_mt(raw_pts, mt_segs, mt_radius, vl_segs, vl_radius, urban_mask_fn)
            for seg in segs:
                self._add_spline(smooth_curve(seg, max_seg_len=seg_res, bound=b), is_main=is_ave, road_type='URBAN_AVENUE' if is_ave else 'URBAN_STREET')

        # V方向街路
        for iu, u0 in enumerate(u_coords):
            raw_pts = [warped_world(u0, v0) for v0 in v_coords]
            is_ave = (iu % 4 == 2)
            segs = self._clip_street_to_urban_and_mt(raw_pts, mt_segs, mt_radius, vl_segs, vl_radius, urban_mask_fn)
            for seg in segs:
                self._add_spline(smooth_curve(seg, max_seg_len=seg_res, bound=b), is_main=is_ave, road_type='URBAN_AVENUE' if is_ave else 'URBAN_STREET')

        # 有機的都市マスク内、かつ山麓・谷領域の外側にある街区ブロックのみを記録
        for iu in range(len(u_coords) - 1):
            u1, u2 = u_coords[iu], u_coords[iu + 1]
            for iv in range(len(v_coords) - 1):
                v1, v2 = v_coords[iv], v_coords[iv + 1]
                p00 = warped_world(u1, v1)
                p10 = warped_world(u2, v1)
                p11 = warped_world(u2, v2)
                p01 = warped_world(u1, v2)
                bcx = 0.25 * (p00[0] + p10[0] + p11[0] + p01[0])
                bcy = 0.25 * (p00[1] + p10[1] + p11[1] + p01[1])
                mask_s = urban_mask_fn(bcx, bcy)
                if mask_s <= 0.24:
                    continue
                if mt_segs and mt_radius > 0.0:
                    d_mt, eff_r = self._dist_to_mt_segments(bcx, bcy, mt_segs, mt_radius)
                    if d_mt < eff_r * 1.05:
                        continue
                if vl_segs and vl_radius > 0.0:
                    d_vl, eff_vr = self._dist_to_mt_segments(bcx, bcy, vl_segs, vl_radius)
                    if d_vl < eff_vr * 0.95:
                        continue
                self.city_blocks.append({
                    'cx': bcx,
                    'cy': bcy,
                    'u_len': abs(u2 - u1),
                    'v_len': abs(v2 - v1),
                    'angle': ang,
                    'cos_a': cos_a,
                    'sin_a': sin_a,
                    'is_cbd_district': cfg['is_cbd'],
                    'urban_score': mask_s,
                })

    def get_road_splines_with_metadata(self):
        result = []
        for i, pts in enumerate(self.generated_splines):
            meta = self.spline_metadata[i] if i < len(self.spline_metadata) else {'is_main': False}
            result.append((pts, meta))
        return result

    def _is_colliding_with_roads(self, lx, ly, b_width, b_depth, road_segments, margin=4.0, angle=0.0):
        hw = b_width / 2.0
        hh = b_depth / 2.0
        bldg_radius = math.sqrt(hw * hw + hh * hh)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
        points_to_check = [(lx + dx * cos_a - dy * sin_a, ly + dx * sin_a + dy * cos_a) for dx, dy in corners]
        points_to_check.append((lx, ly))

        for seg in road_segments:
            x1, y1, x2, y2, road_half_w = seg
            clearance = road_half_w + margin

            dx = x2 - x1
            dy = y2 - y1
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq < 1e-6:
                if (lx - x1)**2 + (ly - y1)**2 < (clearance + bldg_radius)**2:
                    return True
                continue

            t = max(0.0, min(1.0, ((lx - x1) * dx + (ly - y1) * dy) / seg_len_sq))
            px = x1 + t * dx
            py = y1 + t * dy
            center_dist_sq = (lx - px)**2 + (ly - py)**2

            if center_dist_sq >= (clearance + bldg_radius)**2:
                continue

            if center_dist_sq < (clearance + min(hw, hh) * 0.7)**2:
                return True

            for cx_pt, cy_pt in points_to_check:
                ct = max(0.0, min(1.0, ((cx_pt - x1) * dx + (cy_pt - y1) * dy) / seg_len_sq))
                cpx = x1 + ct * dx
                cpy = y1 + ct * dy
                if (cx_pt - cpx)**2 + (cy_pt - cpy)**2 < clearance * clearance:
                    return True

        return False

    def generate_building_lots(self):
        """
        街区ブロック（city_blocks）の内側を区画分割し、CBD中心からの距離に応じた
        現実的なスカイライン（高層80〜220m → 中層25〜60m → 低層8〜18m）で建物を配置する。
        """
        building_lots = []
        rng = self.rng
        cbd_x, cbd_y, _ = self.cbd_center
        cbd_list = getattr(self, 'cbd_centers', None) or [(cbd_x, cbd_y)]
        c_scale = max(1.0, float(getattr(self, 'city_scale', 1.0)))
        is_full = bool(getattr(self, 'is_full_map_city', False))
        thresh_scale = 2.6 if is_full else min(2.2, c_scale)

        def _nearest_cbd_dist(px, py):
            return min(math.hypot(px - cx_i, py - cy_i) for cx_i, cy_i in cbd_list)

        road_segments = []
        for i, spline in enumerate(self.generated_splines):
            meta = self.spline_metadata[i] if i < len(self.spline_metadata) else {}
            is_main = meta.get('is_main', False)
            road_half_w = 12.0 if is_main else 6.0
            for j in range(len(spline) - 1):
                p1 = spline[j]
                p2 = spline[j + 1]
                road_segments.append((p1[0], p1[1], p2[0], p2[1], road_half_w))

        def _try_place_lot(lx, ly, bw, bd, bh, ang, b_type):
            bldg_r = math.sqrt((bw * 0.5) ** 2 + (bd * 0.5) ** 2)
            if not is_full:
                for eb in building_lots:
                    eb_r = math.sqrt((eb['w'] * 0.5) ** 2 + (eb['h'] * 0.5) ** 2)
                    if (lx - eb['x']) ** 2 + (ly - eb['y']) ** 2 < (bldg_r + eb_r + 3.0) ** 2:
                        return False
                if self._is_colliding_with_roads(lx, ly, bw, bd, road_segments, margin=3.0, angle=ang):
                    return False
            building_lots.append({
                'x': lx, 'y': ly,
                'w': bw, 'h': bd,
                'z_height': bh,
                'angle': ang,
                'type': b_type,
            })
            return True

        def _sample_building_spec(dist_cbd, urban_score):
            if dist_cbd < 580.0 * thresh_scale:
                # 都心・商業業務地区 (CBD): 幅 35m〜75m × 奥行 35m〜75m、高さ 60m〜220m
                return (
                    rng.uniform(42.0, 85.0) if is_full else rng.uniform(35.0, 75.0),
                    rng.uniform(42.0, 85.0) if is_full else rng.uniform(35.0, 75.0),
                    rng.uniform(60.0, 220.0),
                    'SKYSCRAPER',
                    0.85 if is_full else 0.90,
                    115.0 if is_full else 56.0,
                )
            elif dist_cbd < 1350.0 * thresh_scale:
                # 中層市街地 (Mixed Use): 幅 22m〜45m × 奥行 22m〜45m、高さ 20m〜55m
                return (
                    rng.uniform(32.0, 65.0) if is_full else rng.uniform(22.0, 45.0),
                    rng.uniform(32.0, 65.0) if is_full else rng.uniform(22.0, 45.0),
                    rng.uniform(22.0, 60.0),
                    'MIDRISE',
                    0.78 if is_full else 0.82,
                    105.0 if is_full else 36.0,
                )
            else:
                # 郊外住宅・工業地区: 都市マスクに応じて自然にフェードアウト
                fill_p = 0.72 if is_full else max(0.25, min(0.72, urban_score * 1.15))
                if rng.random() < (0.35 if is_full else 0.25):
                    # 工場・倉庫・大型商業棟: 幅 45m〜90m、奥行 30m〜60m、高さ 12m〜28m
                    return (
                        rng.uniform(48.0, 95.0),
                        rng.uniform(36.0, 68.0),
                        rng.uniform(14.0, 28.0),
                        'LOWRISE',
                        fill_p * 0.85,
                        125.0 if is_full else 64.0,
                    )
                return (
                    rng.uniform(26.0, 48.0) if is_full else rng.uniform(14.0, 24.0),
                    rng.uniform(24.0, 44.0) if is_full else rng.uniform(12.0, 22.0),
                    rng.uniform(10.0, 22.0) if is_full else rng.uniform(7.0, 14.0),
                    'LOWRISE',
                    fill_p,
                    95.0 if is_full else 22.0,
                )

        # 1. 街区ブロック内の区画分割（Lot Subdivision）
        for blk in self.city_blocks:
            bcx, bcy = blk['cx'], blk['cy']
            u_len, v_len = blk['u_len'], blk['v_len']
            cos_a, sin_a = blk['cos_a'], blk['sin_a']
            ang = blk['angle']
            u_score = blk.get('urban_score', 0.5)

            margin_uv = 28.0 if is_full else 18.0
            usable_u = u_len - margin_uv
            usable_v = v_len - margin_uv
            if usable_u < 16.0 or usable_v < 16.0:
                continue

            dist_cbd = _nearest_cbd_dist(bcx, bcy)
            _, _, _, _, base_fill, target_cell = _sample_building_spec(dist_cbd, u_score)

            max_sub = 4 if is_full else 5
            n_cols = max(1, min(max_sub, int(round(usable_u / target_cell))))
            n_rows = max(1, min(max_sub, int(round(usable_v / target_cell))))
            cell_u = usable_u / n_cols
            cell_v = usable_v / n_rows

            for ci in range(n_cols):
                for ri in range(n_rows):
                    if rng.random() > base_fill:
                        continue

                    lu = -usable_u * 0.5 + (ci + 0.5) * cell_u + rng.uniform(-2.5, 2.5)
                    lv = -usable_v * 0.5 + (ri + 0.5) * cell_v + rng.uniform(-2.5, 2.5)
                    wx = bcx + lu * cos_a - lv * sin_a
                    wy = bcy + lu * sin_a + lv * cos_a

                    d_lot = _nearest_cbd_dist(wx, wy)
                    bw, bd, bh, b_type, _, _ = _sample_building_spec(d_lot, u_score)
                    bw = min(bw, cell_u * 0.88)
                    bd = min(bd, cell_v * 0.88)
                    if bw < 10.0 or bd < 10.0:
                        continue
                    _try_place_lot(wx, wy, bw, bd, bh, ang + rng.uniform(-0.04, 0.04), b_type)

        return building_lots
