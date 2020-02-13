bl_info = {
	"name": "PES FMDL format",
	"author": "foreground",
	"blender": (2, 79, 0),
	"category": "Import-Export",
	"version": (0, 1, 0),
	"warning": "EARLY TEST VERSION",
}

import bpy
import bpy.props
import bpy_extras.io_utils

from . import FmdlFile, IO, UI



class ImportFmdl(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
	"""Load a PES FMDL file"""
	bl_idname = "import_scene.fmdl"
	bl_label = "Import Fmdl"
	bl_options = {'PRESET', 'UNDO'}
	
	import_label = "PES FMDL (.fmdl)"
	
	filename_ext = ".fmdl"
	filter_glob = bpy.props.StringProperty(default="*.fmdl", options={'HIDDEN'})
	
	def execute(self, context):
		
		filename = self.filepath
		
		fmdlFile = FmdlFile.FmdlFile()
		fmdlFile.readFile(filename)
		
		IO.importFmdl(context, fmdlFile, filename)
		
		return {'FINISHED'}

def importFmdlMenuItem(self, context):
	self.layout.operator(ImportFmdl.bl_idname, text=ImportFmdl.import_label)

def importMenu():
	if 'TOPBAR_MT_file_import' in dir(bpy.types):
		return bpy.types.TOPBAR_MT_file_import
	else:
		return bpy.types.INFO_MT_file_import



class ExportFmdl(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
	"""Load a PES FMDL file"""
	bl_idname = "export_scene.fmdl"
	bl_label = "Export Fmdl"
	bl_options = {'PRESET'}
	
	export_label = "PES FMDL (.fmdl)"
	
	filename_ext = ".fmdl"
	filter_glob = bpy.props.StringProperty(default="*.fmdl", options={'HIDDEN'})
	
	def execute(self, context):
		
		filename = self.filepath
		
		fmdlFile = IO.exportFmdl(context)
		fmdlFile.writeFile(filename)
		
		return {'FINISHED'}

def exportFmdlMenuItem(self, context):
	self.layout.operator(ExportFmdl.bl_idname, text=ExportFmdl.export_label)

def exportMenu():
	if 'TOPBAR_MT_file_export' in dir(bpy.types):
		return bpy.types.TOPBAR_MT_file_export
	else:
		return bpy.types.INFO_MT_file_export



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
	
	bpy.types.Texture.fmdl_texture_path = bpy.props.StringProperty(name = "Texture Path")
	bpy.types.Texture.fmdl_texture_role = bpy.props.StringProperty(name = "Texture Role")
	
	bpy.utils.register_class(ImportFmdl)
	importMenu().append(importFmdlMenuItem)
	
	bpy.utils.register_class(ExportFmdl)
	exportMenu().append(exportFmdlMenuItem)
	
	UI.register()

def unregister():
	UI.unregister()
	
	exportMenu().remove(exportFmdlMenuItem)
	bpy.utils.unregister_class(ExportFmdl)
	
	importMenu().remove(importFmdlMenuItem)
	bpy.utils.unregister_class(ImportFmdl)
	
	bpy.utils.unregister_class(MaterialParameter)
