import bpy
import bpy.props
import bpy_extras.io_utils

from . import FmdlFile, IO

class ImportFmdl(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
	"""Load a PES FMDL file"""
	bl_idname = "import_scene.fmdl"
	bl_label = "Import Fmdl"
	bl_options = {'REGISTER', 'UNDO'}
	
	import_label = "PES FMDL (.fmdl)"
	
	filename_ext = ".fmdl"
	filter_glob = bpy.props.StringProperty(default="*.fmdl", options={'HIDDEN'})
	
	def execute(self, context):
		filename = self.filepath
		
		fmdlFile = FmdlFile.FmdlFile()
		fmdlFile.readFile(filename)
		
		IO.importFmdl(context, fmdlFile, filename)
		
		return {'FINISHED'}

class ExportSceneFmdl(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
	"""Export the entire scene as a single PES FMDL file"""
	bl_idname = "export_scene.fmdl"
	bl_label = "Export Fmdl"
	bl_options = {'REGISTER'}
	
	export_label = "PES FMDL (.fmdl)"
	
	filename_ext = ".fmdl"
	filter_glob = bpy.props.StringProperty(default="*.fmdl", options={'HIDDEN'})
	
	def execute(self, context):
		fmdlFile = IO.exportFmdl(context, None)
		fmdlFile.writeFile(self.filepath)
		
		self.report({'INFO'}, "Fmdl exported successfully.") 
		
		return {'FINISHED'}

class ExportFmdl(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
	"""Export an individual object as a PES FMDL file"""
	bl_idname = "export_scene.fmdl_object"
	bl_label = "Export Fmdl"
	bl_options = {'REGISTER'}
	
	objectName = bpy.props.StringProperty("Object to export")
	
	export_label = "PES FMDL (.fmdl)"
	
	filename_ext = ".fmdl"
	filter_glob = bpy.props.StringProperty(default="*.fmdl", options={'HIDDEN'})
	
	@classmethod
	def poll(cls, context):
		return context.active_object != None
	
	def invoke(self, context, event):
		self.objectName = context.active_object.name
		return bpy_extras.io_utils.ExportHelper.invoke(self, context, event)
	
	def execute(self, context):
		fmdlFile = IO.exportFmdl(context, self.objectName)
		fmdlFile.writeFile(self.filepath)
		
		self.report({'INFO'}, "Fmdl exported successfully.") 
		
		return {'FINISHED'}



classes = [
	ImportFmdl,
	ExportSceneFmdl,
	ExportFmdl,
]

def register():
	for c in classes:
		bpy.utils.register_class(c)

def unregister():
	for c in classes[::-1]:
		bpy.utils.unregister_class(c)
