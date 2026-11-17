# -*- coding: utf-8 -*-
"""
地形ブループリント（設計仕様JSON）のシーン永続化と差分パッチ適用を行うモジュール。
Blender UI と MCP サーバーの両方から共通利用される。
"""
import copy
import json

SCENE_BLUEPRINT_KEY = "ai_terrain_blueprint_json"
SCENE_META_KEY = "ai_terrain_meta_json"


def normalize_blueprint(bp):
    """ブループリントのゾーンに安定した ID を付与し、正規化されたコピーを返す"""
    out = copy.deepcopy(bp) if isinstance(bp, dict) else {}
    zones = out.get("zones")
    if not isinstance(zones, list):
        zones = []
        out["zones"] = zones

    used_ids = set()
    for idx, z in enumerate(zones):
        if not isinstance(z, dict):
            continue
        zid = z.get("id")
        if not zid or zid in used_ids:
            z_type = str(z.get("type", "ZONE")).lower()
            z_reg = str(z.get("region", "center")).lower()
            base_id = f"{z_type}_{z_reg}"
            cand = base_id
            suffix = 1
            while cand in used_ids:
                cand = f"{base_id}_{suffix}"
                suffix += 1
            z["id"] = cand
        used_ids.add(z["id"])
    return out


def save_blueprint(scene, blueprint, meta=None):
    """現在のブループリントとメタデータを Blender シーンに永続化する"""
    if scene is None:
        return
    norm_bp = normalize_blueprint(blueprint)
    scene[SCENE_BLUEPRINT_KEY] = json.dumps(norm_bp, ensure_ascii=False)
    if meta is not None:
        scene[SCENE_META_KEY] = json.dumps(meta, ensure_ascii=False)


def load_blueprint(scene):
    """Blender シーンから永続化されたブループリントとメタデータを読み込む"""
    if scene is None:
        return None, {}
    raw_bp = scene.get(SCENE_BLUEPRINT_KEY)
    if not raw_bp:
        return None, {}
    try:
        bp = json.loads(raw_bp)
    except Exception:
        return None, {}

    meta = {}
    raw_meta = scene.get(SCENE_META_KEY)
    if raw_meta:
        try:
            meta = json.loads(raw_meta)
        except Exception:
            meta = {}
    return normalize_blueprint(bp), meta


def _zone_matches(zone, match):
    """ゾーンが match 条件（id または type/region）に一致するか判定"""
    if not isinstance(zone, dict) or not isinstance(match, dict):
        return False
    if "id" in match and match["id"]:
        return zone.get("id") == match["id"]
    for k, v in match.items():
        if str(zone.get(k, "")).upper() != str(v).upper():
            return False
    return bool(match)


def apply_blueprint_patch(current_bp, patch_payload):
    """
    現在のブループリントに対して差分パッチまたは全体置換を適用する。

    patch_payload 形式:
    1) 差分パッチ:
       {
         "operations": [
           {"op": "update_params", "params": {"relief_level": 4.5, ...}},
           {"op": "add_zone", "zone": {"type": "MOUNTAIN_RANGE", "region": "NORTH_EAST", ...}},
           {"op": "modify_zone", "match": {"id": "..."}, "updates": {"height_scale": 2.0}},
           {"op": "remove_zone", "match": {"type": "CITY", "region": "CENTER"}}
         ]
       }
    2) 全体置換:
       {"archetype": "...", "zones": [...], ...}
    """
    if not isinstance(patch_payload, dict):
        return normalize_blueprint(current_bp or {})

    ops = patch_payload.get("operations")
    if not isinstance(ops, list):
        # 全体置換として扱う
        return normalize_blueprint(patch_payload)

    bp = normalize_blueprint(current_bp or {})
    zones = bp.setdefault("zones", [])

    allowed_param_keys = {
        "archetype",
        "orientation",
        "relief_level",
        "ridge_sharpness",
        "noise_scale_factor",
        "water_level",
        "road_topology",
        "has_tunnels",
    }

    for op_item in ops:
        if not isinstance(op_item, dict):
            continue
        op = str(op_item.get("op", "")).lower().strip()

        if op == "update_params":
            params = op_item.get("params", {})
            if isinstance(params, dict):
                for k, v in params.items():
                    if k in allowed_param_keys:
                        bp[k] = v

        elif op == "add_zone":
            new_zone = op_item.get("zone")
            if isinstance(new_zone, dict) and new_zone.get("type"):
                zones.append(copy.deepcopy(new_zone))

        elif op == "modify_zone":
            match = op_item.get("match")
            if not match and op_item.get("id"):
                match = {"id": op_item["id"]}
            updates = op_item.get("updates", {})
            if isinstance(match, dict) and isinstance(updates, dict):
                for z in zones:
                    if _zone_matches(z, match):
                        for uk, uv in updates.items():
                            if uk != "id":
                                z[uk] = uv

        elif op == "remove_zone":
            match = op_item.get("match")
            if not match and op_item.get("id"):
                match = {"id": op_item["id"]}
            if isinstance(match, dict):
                zones[:] = [z for z in zones if not _zone_matches(z, match)]

    return normalize_blueprint(bp)
