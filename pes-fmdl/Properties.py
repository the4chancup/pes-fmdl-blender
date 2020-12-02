import bpy
from .Preferences import PesFmdlPreferences

class FMDL_MaterialParameter(bpy.types.PropertyGroup):
	name = bpy.props.StringProperty(name = "Parameter Name")
	parameters = bpy.props.FloatVectorProperty(name = "Parameter Values", size = 4, default = [0.0, 0.0, 0.0, 0.0])


class Properties:
	def __init__(self):
		pass
	
	@staticmethod
	def Register():
		bpy.utils.register_class(FMDL_MaterialParameter)
		bpy.utils.register_class(PesFmdlPreferences)
		
		bpy.types.Mesh.fmdl_alpha_enum = bpy.props.IntProperty(name = "Alpha Enum", default = 0, min = 0, max = 255)
		bpy.types.Mesh.fmdl_shadow_enum = bpy.props.IntProperty(name = "Shadow Enum", default = 0, min = 0, max = 255)
		
		bpy.types.Material.fmdl_material_shader = bpy.props.StringProperty(name = "Shader")
		bpy.types.Material.fmdl_material_technique = bpy.props.StringProperty(name = "Technique")
		bpy.types.Material.fmdl_material_parameters = bpy.props.CollectionProperty(name = "Material Parameters",
																				   type = FMDL_MaterialParameter)

		bpy.types.Object.fmdl_file = bpy.props.BoolProperty(name = "Is this an FMDL object?")
		bpy.types.Object.fmdl_filename = bpy.props.StringProperty(name = "FMDL file name")

		(major, minor, build) = bpy.app.version
		if minor >= 80:
			bpy.types.ShaderNodeTexImage.fmdl_texture_filename = bpy.props.StringProperty(name = "Texture Filename")
			bpy.types.ShaderNodeTexImage.fmdl_texture_directory = bpy.props.StringProperty(name = "Texture Directory")
			bpy.types.ShaderNodeTexImage.fmdl_texture_role = bpy.props.StringProperty(name = "Texture Role")
		else:
			bpy.types.Texture.fmdl_texture_filename = bpy.props.StringProperty(name = "Texture Filename")
			bpy.types.Texture.fmdl_texture_directory = bpy.props.StringProperty(name = "Texture Directory")
			bpy.types.Texture.fmdl_texture_role = bpy.props.StringProperty(name = "Texture Role")
	
	@staticmethod
	def Unregister():
		bpy.utils.unregister_class(PesFmdlPreferences)
		bpy.utils.unregister_class(FMDL_MaterialParameter)
