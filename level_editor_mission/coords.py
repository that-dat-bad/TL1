# -*- coding: utf-8 -*-
"""
Mission Editor - 座標系・方位角 双方向変換クラス
Blender (右手系 Z-up, -Y前方) ⇔ DirectX Engine (左手系 Y-up, +Z前方)
"""

import math
from typing import Dict, Tuple
from .constants import CoordConstants, MathConstants


class CoordinateTransformer:
    """
    TerrainChunkManager.cpp および Model.cpp の頂点変換規約と完全一致する座標変換器。
      Engine (ex, ey, ez) -> Blender (bx = -ex, by = -ez, bz = ey)
      Blender (bx, by, bz) -> Engine (ex = -bx, ey = bz, ez = -by)
      Engine Yaw (0度 = +Z北向き, 時計回り) <-> Blender Z回転 (-Y前方基準)
    """

    @staticmethod
    def engine_to_blender_pos(ex: float, ey: float, ez: float) -> Tuple[float, float, float]:
        bx = ex * CoordConstants.SIGN_FLIP
        by = ez * CoordConstants.SIGN_FLIP
        bz = ey * CoordConstants.SIGN_KEEP
        return (bx, by, bz)

    @classmethod
    def engine_dict_to_blender_pos(cls, vec_dict: Dict[str, float]) -> Tuple[float, float, float]:
        ex = float(vec_dict.get("x", MathConstants.ZERO))
        ey = float(vec_dict.get("y", MathConstants.ZERO))
        ez = float(vec_dict.get("z", MathConstants.ZERO))
        return cls.engine_to_blender_pos(ex, ey, ez)

    @staticmethod
    def blender_to_engine_pos(bx: float, by: float, bz: float) -> Tuple[float, float, float]:
        ex = round(bx * CoordConstants.SIGN_FLIP, MathConstants.ROUND_DIGITS)
        ey = round(bz * CoordConstants.SIGN_KEEP, MathConstants.ROUND_DIGITS)
        ez = round(by * CoordConstants.SIGN_FLIP, MathConstants.ROUND_DIGITS)
        # -0.0 を 0.0 に正規化
        if abs(ex) < MathConstants.EPSILON:
            ex = MathConstants.ZERO
        if abs(ey) < MathConstants.EPSILON:
            ey = MathConstants.ZERO
        if abs(ez) < MathConstants.EPSILON:
            ez = MathConstants.ZERO
        return (ex, ey, ez)

    @classmethod
    def blender_to_engine_dict(cls, bx: float, by: float, bz: float) -> Dict[str, float]:
        ex, ey, ez = cls.blender_to_engine_pos(bx, by, bz)
        return {"x": ex, "y": ey, "z": ez}

    @staticmethod
    def engine_yaw_deg_to_blender_rot_z(yaw_deg: float) -> float:
        return math.radians(yaw_deg * CoordConstants.SIGN_FLIP)

    @staticmethod
    def blender_rot_z_to_engine_yaw_deg(rot_z_rad: float) -> float:
        raw_deg = math.degrees(rot_z_rad * CoordConstants.SIGN_FLIP)
        half = MathConstants.DEG_HALF_CIRCLE
        full = MathConstants.DEG_FULL_CIRCLE
        normalized = ((raw_deg + half) % full) - half
        if abs(normalized) < MathConstants.EPSILON:
            normalized = MathConstants.ZERO
        return round(normalized, MathConstants.ROUND_DIGITS)

