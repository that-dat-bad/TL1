# -*- coding: utf-8 -*-
"""
Blender 4.5.x および Blender 5.2.x 互換 Geometry Nodes モディファイア入出力ユーティリティ
"""
import bpy


def find_input_identifier(mod, name_or_id):
    """
    ソケット名（例: 'Mountain Collection'）または識別子（例: 'Socket_2'）から
    実際のノードグループのソケット identifier を解決する
    """
    group = getattr(mod, 'node_group', None)
    if not group:
        return name_or_id

    if hasattr(group, 'interface'):
        for item in group.interface.items_tree:
            if getattr(item, 'item_type', '') == 'SOCKET' and getattr(item, 'in_out', '') == 'INPUT':
                if item.name == name_or_id or item.identifier == name_or_id:
                    return item.identifier
    elif hasattr(group, 'inputs'):
        for inp in group.inputs:
            if inp.name == name_or_id or getattr(inp, 'identifier', '') == name_or_id:
                return getattr(inp, 'identifier', inp.name)

    return name_or_id


def get_modifier_input(mod, name_or_id):
    """
    Geometry Nodes モディファイアから入力値を取得（Blender 4.x / 5.x 両対応）
    """
    if not mod:
        return None

    identifier = find_input_identifier(mod, name_or_id)

    # Blender 5.x: mod.properties.inputs
    if hasattr(mod, 'properties') and hasattr(mod.properties, 'inputs'):
        inputs = mod.properties.inputs
        target = None
        if identifier in dir(inputs):
            target = getattr(inputs, identifier)
        elif hasattr(inputs, '__contains__') and identifier in inputs:
            target = inputs[identifier]
        elif name_or_id in dir(inputs):
            target = getattr(inputs, name_or_id)
        elif hasattr(inputs, '__contains__') and name_or_id in inputs:
            target = inputs[name_or_id]

        if target is not None:
            # ポインタ型（Collection, Object等）は target['value'] に格納されている
            if hasattr(target, 'keys') and 'value' in target.keys():
                return target['value']
            # 基本型（Float, Int, Vector等）
            return target

    # Blender 4.x 以前: mod[identifier] または mod[name_or_id] (IDProperties)
    try:
        if hasattr(mod, '__contains__') and identifier in mod:
            return mod[identifier]
    except Exception:
        pass

    try:
        if hasattr(mod, '__contains__') and name_or_id in mod:
            return mod[name_or_id]
    except Exception:
        pass

    try:
        return mod[identifier]
    except Exception:
        pass

    try:
        return mod[name_or_id]
    except Exception:
        pass

    return None


def set_modifier_input(mod, name_or_id, value):
    """
    Geometry Nodes モディファイアに入力値を設定（Blender 4.x / 5.x 両対応）
    """
    if not mod:
        return False

    def _tag_update(m):
        id_data = getattr(m, 'id_data', None)
        if id_data is not None and hasattr(id_data, 'update_tag'):
            try:
                id_data.update_tag()
            except Exception:
                pass

    identifier = find_input_identifier(mod, name_or_id)

    # Blender 5.x: mod.properties.inputs
    if hasattr(mod, 'properties') and hasattr(mod.properties, 'inputs'):
        inputs = mod.properties.inputs
        target = None
        if identifier in dir(inputs):
            target = getattr(inputs, identifier)
        elif hasattr(inputs, '__contains__') and identifier in inputs:
            target = inputs[identifier]

        if target is not None:
            if hasattr(target, 'value'):
                try:
                    target.value = value
                    _tag_update(mod)
                    return True
                except Exception:
                    pass
            if hasattr(target, 'keys') and 'value' in target.keys():
                try:
                    target['value'] = value
                    _tag_update(mod)
                    return True
                except Exception:
                    pass
            else:
                try:
                    setattr(inputs, identifier, value)
                    _tag_update(mod)
                    return True
                except Exception:
                    try:
                        inputs[identifier] = value
                        _tag_update(mod)
                        return True
                    except Exception:
                        pass

    # Blender 4.x 以前: mod[identifier] = value または mod[name_or_id] = value
    try:
        mod[identifier] = value
        _tag_update(mod)
        return True
    except Exception:
        pass

    try:
        mod[name_or_id] = value
        _tag_update(mod)
        return True
    except Exception:
        pass

    return False


def get_modifier_input_items(mod):
    """
    全入力ソケットの (name, identifier, value) のリストを取得（Blender 4.x / 5.x 両対応）
    """
    items = []
    group = getattr(mod, 'node_group', None)
    if not group:
        return items

    if hasattr(group, 'interface'):
        for item in group.interface.items_tree:
            if getattr(item, 'item_type', '') == 'SOCKET' and getattr(item, 'in_out', '') == 'INPUT':
                name = item.name
                ident = item.identifier
                val = get_modifier_input(mod, ident)
                items.append((name, ident, val))
    elif hasattr(group, 'inputs'):
        for inp in group.inputs:
            name = inp.name
            ident = getattr(inp, 'identifier', name)
            val = get_modifier_input(mod, ident)
            items.append((name, ident, val))

    return items
