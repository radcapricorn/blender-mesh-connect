bl_info = {
    "name" : "Connect",
    "author" : "Stanislav Blinov",
    "version" : (1, 1, 0),
    "blender" : (2, 80, 0),
    "description" : "Connect and Deselect Boundary operators",
    "category" : "Mesh",}

import bpy
import bmesh
from bmesh.types import BMEdge, BMVert

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

def radial_loops(loop):
    next = loop.link_loop_radial_next
    while next != loop:
        result, next = next, next.link_loop_radial_next
        yield result

def walk_loops(loop):
    next = loop.link_loop_next
    while next != loop:
        result, next = next, next.link_loop_next
        yield result

def loop_distance(lfrom, lto):
    result = 0
    while lfrom != lto:
        lfrom = lfrom.link_loop_next
        result += 1
    return result

def get_inner_selected_edges(edges, keep_caps = True):
    result = [None] * len(edges)
    count = 0

    for e in edges:
        num_sel_faces = sum(l.face.select for l in e.link_loops)
        if num_sel_faces > 1:
            # if more than one adjacent face is selected, done, keep edge
            result[count] = e
            count += 1
        elif num_sel_faces == 1 and keep_caps:
            (loop,) = (l for l in e.link_loops if l.face.select)
            rank = len(loop.face.verts)
            # only keep this edge if the only other selected face adjacent to this one
            # is over the opposite edge; opposite edges are only defined in even n-gons
            if not rank & 1:
                adj_sel_faces = set(c for c in walk_loops(loop) for l in radial_loops(c) if l.face.select)
                if len(adj_sel_faces) == 1 and loop_distance(loop, next(iter(adj_sel_faces))) == (rank >> 1):
                    result[count] = e
                    count += 1
    return result[:count]

class MESH_xOT_deselect_boundary(bpy.types.Operator):
    """Deselect boundary edges of selected faces"""
    bl_idname = "mesh.ext_deselect_boundary"
    bl_label = "Deselect Boundary"
    bl_options = {'REGISTER', 'UNDO'}

    keep_cap_edges: bpy.props.BoolProperty(
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
            edges = get_inner_selected_edges([e for e in bm.edges if e.select], keep_caps = self.keep_cap_edges)
            if not edges:
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

class MESH_xOT_connect(bpy.types.Operator):
    """Cut selected faces, connecting through their adjacent edges; or cut through selected edge rings"""
    bl_idname = "mesh.ext_connect"
    bl_label = "Connect"
    bl_options = {'REGISTER', 'UNDO'}

    # from bmesh_operators.h
    SUBD_INNERVERT    = 0
    SUBD_PATH         = 1
    SUBD_FAN          = 2
    SUBD_STRAIGHT_CUT = 3

    num_cuts: bpy.props.IntProperty(
        name    = "Number of Cuts",
        default = 1,
        min     = 1,
        max     = 100,
        subtype = 'UNSIGNED')

    use_single_edge: bpy.props.BoolProperty(
        name        = "Boundary n-gons",
        description = "Create n-gons on selection boundary",
        default     = True)

    corner_type: bpy.props.EnumProperty(
        items = [('INNER_VERT', "Inner Vert", ""),
                 ('PATH', "Path", ""),
                 ('FAN', "Fan", ""),
                 ('STRAIGHT_CUT', "Straight Cut", ""),],
        name = "Quad Corner Type",
        description = "How to subdivide quad corners",
        default = 'STRAIGHT_CUT')

    use_grid_fill: bpy.props.BoolProperty(
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
            edges = [e for e in bm.edges if e.select]
            if context.tool_settings.mesh_select_mode[2]:
                edges = get_inner_selected_edges(edges, keep_caps = True)
            else:
                edges = [e for e in edges if sum(l.edge.select for loop in e.link_loops for l in walk_loops(loop)) > 0]
            if not edges:
                return False

            result = bmesh.ops.subdivide_edges(
                bm,
                edges = edges,
                cuts = int(self.num_cuts),
                use_grid_fill = bool(self.use_grid_fill),
                use_single_edge = not bool(self.use_single_edge),
                quad_corner_type = str(self.corner_type))

            bpy.ops.mesh.select_all(action='DESELECT')
            bm.select_mode = {'EDGE'}

            # For some reason, not all edges are reported in 'geom_inner', so instead,
            # select all edges linked to vertices in 'geom_inner', that do not also belong to 'geom_split' edges
            split_edges = set(e for e in result['geom_split'] if isinstance(e, BMEdge))
            inner_edges = set(e for v in result['geom_inner'] if isinstance(v, BMVert) for e in v.link_edges)
            for edge in inner_edges.difference(split_edges):
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
        return {'FINISHED'}

def menu_deselect_boundary(self, context):
    self.layout.operator(MESH_xOT_deselect_boundary.bl_idname)

def menu_connect(self, context):
    self.layout.operator(MESH_xOT_connect.bl_idname)

def register():
    bpy.utils.register_class(MESH_xOT_deselect_boundary)
    bpy.utils.register_class(MESH_xOT_connect)

    bpy.types.VIEW3D_MT_select_edit_mesh.append(menu_deselect_boundary)
    bpy.types.VIEW3D_MT_edit_mesh_edges.append(menu_connect)
    bpy.types.VIEW3D_MT_edit_mesh_faces.append(menu_connect)

def unregister():
    bpy.utils.unregister_class(MESH_xOT_deselect_boundary)
    bpy.utils.unregister_class(MESH_xOT_connect)

    bpy.types.VIEW3D_MT_select_edit_mesh.remove(menu_deselect_boundary)
    bpy.types.VIEW3D_MT_edit_mesh_faces.remove(menu_connect)
    bpy.types.VIEW3D_MT_edit_mesh_edges.remove(menu_connect)
