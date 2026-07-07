import bpy

# オペレータ 頂点を伸ばす
class MYADDON_OT_strech_vertex(bpy.types.Operator):
    bl_idname = "myaddon.myaddon_ot_strech_vertex"
    bl_label = "頂点を伸ばす"
    bl_description = "選択した頂点を引っ張って伸ばします"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        bpy.data.objects['Cube'].data.vertices[0].co.x += 1.0
        print("頂点を伸ばしました。")
        return {'FINISHED'}
