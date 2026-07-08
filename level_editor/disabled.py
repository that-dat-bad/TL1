import bpy

#オペレータ 無効オプションを追加する
class MYADDON_OT_disable_operator(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_disable_operator"
    bl_label = "Add Disabled"
    bl_description = "['disabled']カスタムプロパティを追加します"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        #カスタムプロパティ"disabled"を追加
        context.object["disabled"] = True
        return {"FINISHED"}

#パネル 無効オプション
class OBJECT_PT_disabled(bpy.types.Panel):
    """オブジェクトの無効化パネル"""
    bl_idname = "OBJECT_PT_disabled"
    bl_label = "Disabled "
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    #サブメニューの描画
    def draw(self, context):
        # パネルに項目を追加
        if "disabled" in context.object:
            #すでにプロパティがあれば、プロパティを表示
            self.layout.prop(context.object, '["disabled"]', text="disabled")
        else:
            #プロパティがなければ、プロパティ追加ボタンを表示
            self.layout.operator(MYADDON_OT_disable_operator.bl_idname)

