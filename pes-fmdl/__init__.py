bl_info = {
	"name": "PES FMDL format",
	"author": "foreground",
	"blender": (2, 79, 0),
	"category": "Import-Export",
	"version": (0, 3, 0),
}

import bpy
import bpy.props

from . import Operators, UI

class MaterialParameter(bpy.types.PropertyGroup):
	name = bpy.props.StringProperty(name = "Parameter Name")
	parameters = bpy.props.FloatVectorProperty(name = "Parameter Values", size = 4, default = [0.0, 0.0, 0.0, 0.0])

def register():
	bpy.utils.register_class(MaterialParameter)
	
	bpy.types.Mesh.fmdl_alpha_enum = bpy.props.IntProperty(name = "Alpha Enum", default = 0, min = 0, max = 255)
	bpy.types.Mesh.fmdl_shadow_enum = bpy.props.IntProperty(name = "Shadow Enum", default = 0, min = 0, max = 255)
	
	bpy.types.Material.fmdl_material_shader = bpy.props.StringProperty(name = "Shader")
	bpy.types.Material.fmdl_material_technique = bpy.props.StringProperty(name = "Technique")
	bpy.types.Material.fmdl_material_parameters = bpy.props.CollectionProperty(name = "Material Parameters", type = MaterialParameter)
	bpy.types.Material.fmdl_material_parameter_active = bpy.props.IntProperty(name = "FMDL_Material_Parameter_Name_List index", default = -1)
	
	bpy.types.Texture.fmdl_texture_filename = bpy.props.StringProperty(name = "Texture Filename")
	bpy.types.Texture.fmdl_texture_directory = bpy.props.StringProperty(name = "Texture Directory")
	bpy.types.Texture.fmdl_texture_role = bpy.props.StringProperty(name = "Texture Role")
	
	bpy.types.Object.fmdl_file = bpy.props.BoolProperty(name = "Is FMDL file")
	bpy.types.Object.fmdl_filename = bpy.props.StringProperty(name = "FMDL filename")
	
	Operators.register()
	UI.register()

def unregister():
	UI.unregister()
	Operators.unregister()
	
	bpy.utils.unregister_class(MaterialParameter)
