bl_info = {
    "name" : "Cut Faces",
    "author" : "Stanislav Blinov",
    "version" : (1, 0, 0),
    "blender" : (2, 72, 0),
    "description" : "Cut Faces and Deselect Boundary operators",
    "category" : "Mesh",}

import bpy
import bmesh

def bmesh_from_object(object):
    mesh = object.data
    if object.mode == 'EDIT':
        bm = bmesh.from_edit_mesh(mesh)
    else:
        bm = bmesh.new()
        bm.from_mesh(mesh)
    return bm

def bmesh_release(bm, object):
    mesh = object.data
    bm.select_flush_mode()
    if object.mode == 'EDIT':
        bmesh.update_edit_mesh(mesh, True)
    else:
        bm.to_mesh(mesh)
        bm.free()

def face_adjacent_selected_edges(face, tags, keep_caps=True):

    def radial_loops(loop):
        next = loop.link_loop_radial_next
        while next != loop:
            result, next = next, next.link_loop_radial_next
            yield result

    result = []
    selected = []

    for loop in face.loops:
        old_tag = loop.edge[tags]
        # Iterate over selected adjacent faces
        for radial_loop in filter(lambda l: l.face.select, radial_loops(loop)):
            loop.edge[tags] += 1

        new_tag = loop.edge[tags]

        if new_tag:
            # No one else has tagged this edge?
            if not old_tag:
                result.append(loop.edge.index)
            selected.append(loop)

    # Select opposite edge in quads
    if keep_caps and len(selected) == 1 and len(face.verts) == 4:
        result.append(selected[0].link_loop_next.link_loop_next.edge.index)

    return result

def get_edge_rings(bm, faces, keep_caps=True):

    # Make sure we're dealing with valid indices
    bm.edges.index_update()
    tags = bm.edges.layers.int.new("etl_data")

    edges = []

    try:
        # generate a list of edges to select
        for face in faces: edges += face_adjacent_selected_edges(face, tags, keep_caps)
    finally:
        # housekeeping: remove our custom data
        bm.edges.layers.int.remove(tags)
        # Removing custom data modifies the contents of bm.edges,
        # so we need to update lookup table
        bm.edges.ensure_lookup_table()

    # Convert from indices to edges
    edges[:] = [ bm.edges[i] for i in edges ]
    return edges

class MESH_xOT_deselect_boundary(bpy.types.Operator):
    """Deselect boundary edges of selected faces"""
    bl_idname = "mesh.ext_deselect_boundary"
    bl_label = "Deselect Boundary"
    bl_options = {'REGISTER', 'UNDO'}

    keep_cap_edges = bpy.props.BoolProperty(
        name        = "Keep Cap Edges",
        description = "Keep quad strip cap edges selected",
        default     = False)

    @classmethod
    def poll(cls, context):
        active_object = context.active_object
        return active_object and active_object.type == 'MESH' and active_object.mode == 'EDIT'

    def execute(self, context):
        object = context.active_object
        bm = bmesh_from_object(object)

        try:
            faces = [ face for face in bm.faces if face.select ]
            edges = get_edge_rings(bm, faces, keep_caps = self.keep_cap_edges)
            if not edges:
                self.report({'WARNING'}, "No suitable selection found")
                return {'CANCELLED'}

            bpy.ops.mesh.select_all(action='DESELECT')
            bm.select_mode = {'EDGE'}

            for edge in edges:
                edge.select = True
            context.tool_settings.mesh_select_mode[:] = False, True, False
        except Exception as error:
            self.report({'ERROR'}, str(error))
        finally:
            bmesh_release(bm, object)
            pass

        return {'FINISHED'}

class MESH_xOT_cut_faces(bpy.types.Operator):
    """Cut selected faces, connecting through their adjacent edges"""
    bl_idname = "mesh.ext_cut_faces"
    bl_label = "Cut Faces"
    bl_options = {'REGISTER', 'UNDO'}

    # from bmesh_operators.h
    SUBD_INNERVERT    = 0
    SUBD_PATH         = 1
    SUBD_FAN          = 2
    SUBD_STRAIGHT_CUT = 3

    num_cuts = bpy.props.IntProperty(
        name    = "Number of Cuts",
        default = 1,
        min     = 1,
        max     = 100,
        subtype = 'UNSIGNED')

    use_single_edge = bpy.props.BoolProperty(
        name        = "Quad/Tri Mode",
        description = "Cut boundary faces",
        default     = False)

    corner_type = bpy.props.EnumProperty(
        items = [('SUBD_INNERVERT', "Inner Vert", ""),
                 ('SUBD_PATH', "Path", ""),
                 ('SUBD_FAN', "Fan", ""),
                 ('SUBD_STRAIGHT_CUT', "Straight Cut", ""),],
        name = "Quad Corner Type",
        description = "How to subdivide quad corners",
        default = 'SUBD_STRAIGHT_CUT')

    use_grid_fill = bpy.props.BoolProperty(
        name        = "Use Grid Fill",
        description = "Fill fully enclosed faces with a grid",
        default     = True)

    @classmethod
    def poll(cls, context):
        active_object = context.active_object
        return active_object and active_object.type == 'MESH' and active_object.mode == 'EDIT'

    def cut_edges(self, context):
        object = context.active_object
        bm = bmesh_from_object(object)

        try:
            faces = [ face for face in bm.faces if face.select ]
            edges = get_edge_rings(bm, faces, keep_caps = True)
            if not edges:
                self.report({'WARNING'}, "No suitable selection found")
                return False

            result = bmesh.ops.subdivide_edges(
                bm,
                edges = edges,
                cuts = int(self.num_cuts),
                use_grid_fill = bool(self.use_grid_fill),
                use_single_edge = bool(self.use_single_edge),
                quad_corner_type = eval("self."+self.corner_type))

            bpy.ops.mesh.select_all(action='DESELECT')
            bm.select_mode = {'EDGE'}

            inner = result['geom_inner']
            for edge in filter(lambda e: isinstance(e, bmesh.types.BMEdge), inner):
                edge.select = True
        except Exception as error:
            self.report({'ERROR'}, str(error))
        finally:
            bmesh_release(bm, object)

        return True

    def execute(self, context):

        if not self.cut_edges(context):
            return {'CANCELLED'}

        context.tool_settings.mesh_select_mode[:] = False, True, False
        # Try to select all possible loops
        bpy.ops.mesh.loop_multi_select(ring=False)
        return {'FINISHED'}

def menu_deselect_boundary(self, context):
    self.layout.operator(MESH_xOT_deselect_boundary.bl_idname)

def menu_cut_faces(self, context):
    self.layout.operator(MESH_xOT_cut_faces.bl_idname)

def register():
    bpy.utils.register_class(MESH_xOT_deselect_boundary)
    bpy.utils.register_class(MESH_xOT_cut_faces)

    if __name__ != "__main__":
        bpy.types.VIEW3D_MT_select_edit_mesh.append(menu_deselect_boundary)
        bpy.types.VIEW3D_MT_edit_mesh_faces.append(menu_cut_faces)

def unregister():
    bpy.utils.unregister_class(MESH_xOT_deselect_boundary)
    bpy.utils.unregister_class(MESH_xOT_cut_faces)

    if __name__ != "__main__":
        bpy.types.VIEW3D_MT_select_edit_mesh.remove(menu_deselect_boundary)
        bpy.types.VIEW3D_MT_edit_mesh_faces.remove(menu_cut_faces)

if __name__ == "__main__":
    register()
