import gpu
import gpu_extras.batch
import copy
import mathutils
import bpy

class MYADDON_OT_add_collider(bpy.types.Operator):
    bl_idname="myaddon.myaddon_ot_add_collider"
    bl_label="コライダー追加"
    bl_description ="['collider']カスタムプロパティを追加します"
    bl_options={"REGISTER","UNDO"}

    def execute(self,context):

        #['collider']カスタムプロパティを追加
        context.object["collider"]="BOX"
        context.object["collider_center"]=mathutils.Vector((0,0,0))
        context.object["collider_size"]=mathutils.Vector((2,2,2))       

        return{"FINISHED"}

class OBJECT_PT_collider(bpy.types.Panel):
    """
    コライダーのカスタムプロパティパネル
    """
    bl_idname = "OBJECT_PT_collider"
    bl_label = "Collider"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"

    # サブメニューの描画
    def draw(self, context):

        # パネルに項目を追加
        if "collider" in context.object:
            # すでにプロパティがあれば、プロパティを表示
            self.layout.prop(context.object, '["collider"]', text="Type")
            self.layout.prop(context.object, '["collider_center"]', text="Center")
            self.layout.prop(context.object, '["collider_size"]', text="Size")
        else:
            # プロパティがなければ、プロパティ追加ボタンを表示
            self.layout.operator(MYADDON_OT_add_collider.bl_idname)

#コライダー描画
class DrawCollider:
    #描画ハンドル
    handle =None

    #3Dビューに登録する描画関数
    def draw_collider():
        #頂点データ
        vertices ={"pos":[]}
        
        #インデックスデータ
        indices =[]

        #各頂点の、オブジェクト中心からのオフセット
        offsets =[
            [-0.5,-0.5,-0.5], #左下前
            [+0.5,-0.5,-0.5], #右下前
            [+0.5,+0.5,-0.5], #右上手前
            [-0.5,+0.5,-0.5], #左上手前
            [-0.5,-0.5,+0.5], #左下奥
            [+0.5,-0.5,+0.5], #右下奥
            [+0.5,+0.5,+0.5], #右上奥
            [-0.5,+0.5,+0.5], #左上手前
        ]

        #現在シーンのオブジェクトリストを走査
        for object in bpy.context.scene.objects:
            #コライダーがなければ描画をスキップ
            if not "collider" in object:
                continue
            
            #中心点、サイズの変数を宣言
            center = mathutils. Vector((0,0,0))
            size = mathutils. Vector((2,2,2))
            #プロパティから値を取得
            center[0]=object["collider_center"][0]
            center[1]=object["collider_center"] [1]
            center[2]=object["collider_center"] [2]
            size[0]=object["collider_size"][0]
            size[1]=object["collider_size"][1]
            size[2]=object["collider_size"] [2]
            #追加前の頂点数
            start = len(vertices['pos'])

            #Boxの8頂点分回す
            for offset in offsets:
                #オブジェクトの中心座標とスケールをコピー
                pos =copy.copy(center)
                size = copy.copy(size)
                # オフセットを適用
                pos[0]+=offset[0]*size[0]
                pos[1]+=offset[1]*size[1]
                pos[2]+=offset[2]*size[2]
                #ローカル座標からワールド座標に変換
                pos = object.matrix_world @ pos
                #頂点データリストに座標を追加
                vertices['pos'].append(pos)
                
            #前面を構成する辺の頂点インデックス
            indices.append([start+0, start+1]) #下
            indices.append([start+2, start+3]) #上
            indices.append([start+0, start+3]) #左
            indices.append([start+1, start+2]) #右
            #奥面を構成する辺の頂点インデックス
            indices.append([start+4, start+5]) #下
            indices.append([start+6, start+7]) #上
            indices.append([start+4, start+7]) #左
            indices.append([start+5, start+6]) #右
            #手前と奥を繋ぐ辺の頂点インデックス
            indices.append([start+0, start+4])
            indices.append([start+1, start+5])
            indices.append([start+2, start+6])
            indices.append([start+3, start+7])

        #ビルトインのシェーダーを取得
        shader = gpu.shader.from_builtin("UNIFORM_COLOR")

        #バッチを作成 (必ず頂点・インデックスを追加し終わってから作成する)
        batch = gpu_extras.batch.batch_for_shader(shader, "LINES", vertices, indices=indices)

        #描画
        shader.bind()
        shader.uniform_float("color", (0.5, 1.0, 1.0, 1.0)) 
        batch.draw(shader)

# 描画ハンドルの登録
def register_draw_handler():
    DrawCollider.handle = bpy.types.SpaceView3D.draw_handler_add(
        DrawCollider.draw_collider, (), 'WINDOW', 'POST_VIEW'
    )

# 描画ハンドルの解除
def unregister_draw_handler():
    if DrawCollider.handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(DrawCollider.handle, 'WINDOW')
        DrawCollider.handle = None