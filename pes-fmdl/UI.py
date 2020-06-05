import bpy
import bpy.props
import bpy_extras.io_utils

from . import FmdlFile, Ftex, IO

class FMDL_Scene_Import(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
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

class FMDL_Scene_Export_Scene(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
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

class FMDL_Scene_Export_Object(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
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

class FMDL_Scene_Panel_FMDL_Compose(bpy.types.Operator):
	"""Enable separate exporting of the active object"""
	bl_idname = "fmdl.compose_exportable"
	bl_label = "Compose Fmdl"
	bl_options = {'UNDO', 'INTERNAL'}
	
	@classmethod
	def poll(cls, context):
		return context.active_object != None and not context.active_object.fmdl_file
	
	def execute(self, context):
		context.active_object.fmdl_file = True
		context.active_object.fmdl_filename = ""
		return {'FINISHED'}

class FMDL_Scene_Panel_FMDL_Remove(bpy.types.Operator):
	"""Disable separate exporting"""
	bl_idname = "fmdl.remove_exportable"
	bl_label = "Remove"
	bl_options = {'UNDO', 'INTERNAL'}
	
	objectName = bpy.props.StringProperty(name = "Object to remove")
	
	def execute(self, context):
		context.scene.objects[self.objectName].fmdl_file = False
		return {'FINISHED'}

class FMDL_Scene_Panel_FMDL_Export(bpy.types.Operator):
	"""Export as PES FMDL file"""
	bl_idname = "fmdl.export_listed_object"
	bl_label = "Export Fmdl"
	bl_options = {'INTERNAL'}
	
	objectName = bpy.props.StringProperty(name = "Object to export")
	
	def execute(self, context):
		return bpy.ops.export_scene.fmdl_object(
			context.copy(),
			objectName = self.objectName,
			filepath = context.scene.objects[self.objectName].fmdl_filename
		)

class FMDL_Scene_Panel_FMDL_Select_Filename(bpy.types.Operator):
	"""Select a filename to export this FMDL file"""
	bl_idname = "fmdl.exportable_select_filename"
	bl_label = "Select Filename"
	bl_options = {'UNDO', 'INTERNAL'}
	
	objectName = bpy.props.StringProperty(name = "Object to export")
	filepath = bpy.props.StringProperty(subtype = 'FILE_PATH')
	check_existing = bpy.props.BoolProperty(default = True)
	filter_glob = bpy.props.StringProperty(default = "*.fmdl")
	
	def invoke(self, context, event):
		context.window_manager.fileselect_add(self)
		return {'RUNNING_MODAL'}
	
	def check(self, context):
		return True
	
	def execute(self, context):
		context.scene.objects[self.objectName].fmdl_filename = self.filepath
		return {'FINISHED'}

def FMDL_Scene_FMDL_Import_MenuItem(self, context):
	self.layout.operator(FMDL_Scene_Import.bl_idname, text=FMDL_Scene_Import.import_label)

def FMDL_Scene_FMDL_Export_MenuItem(self, context):
	self.layout.operator(FMDL_Scene_Export_Scene.bl_idname, text=FMDL_Scene_Export_Scene.export_label)

class FMDL_Scene_Panel(bpy.types.Panel):
	bl_label = "FMDL I/O"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "scene"
	
	@classmethod
	def poll(cls, context):
		return context.scene != None
	
	def draw(self, context):
		scene = context.scene
		
		fmdlFileObjects = []
		for object in context.scene.objects:
			if object.fmdl_file:
				fmdlFileObjects.append(object)
		fmdlFileObjects.sort(key = lambda object: object.name)
		
		mainColumn = self.layout.column()
		mainColumn.operator(FMDL_Scene_Import.bl_idname)
		mainColumn.operator(FMDL_Scene_Panel_FMDL_Compose.bl_idname)
		for object in fmdlFileObjects:
			box = mainColumn.box()
			column = box.column()
			
			row1 = column.row()
			row1.label("Object: %s" % object.name)
			row1.operator(FMDL_Scene_Panel_FMDL_Remove.bl_idname, text = "", icon = 'X').objectName = object.name
			
			row2 = column.row(align = True)
			row2.prop(object, 'fmdl_filename', text = "Export Path")
			row2.operator(FMDL_Scene_Panel_FMDL_Select_Filename.bl_idname, text = "", icon = 'FILESEL').objectName = object.name
			
			row3 = column.row()
			row3.operator(FMDL_Scene_Panel_FMDL_Export.bl_idname).objectName = object.name
			if object.fmdl_filename == "":
				row3.enabled = False



class FMDL_Mesh_Panel(bpy.types.Panel):
	bl_label = "FMDL Mesh Settings"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "data"
	
	@classmethod
	def poll(cls, context):
		return context.mesh != None
	
	def draw(self, context):
		mesh = context.mesh
		
		mainColumn = self.layout.column()
		mainColumn.prop(mesh, "fmdl_shadow_enum")
		mainColumn.prop(mesh, "fmdl_alpha_enum")



class FMDL_Material_Parameter_List_Add(bpy.types.Operator):
	bl_idname = "fmdl.material_parameter_add"
	bl_label = "Add Parameter"
	
	@classmethod
	def poll(cls, context):
		return context.material != None
	
	def execute(self, context):
		material = context.material
		parameter = material.fmdl_material_parameters.add()
		parameter.name = "new_parameter"
		parameter.parameters = [0.0, 0.0, 0.0, 0.0]
		material.fmdl_material_parameter_active = len(material.fmdl_material_parameters) - 1
		return {'FINISHED'}

class FMDL_Material_Parameter_List_Remove(bpy.types.Operator):
	bl_idname = "fmdl.material_parameter_remove"
	bl_label = "Remove Parameter"
	
	@classmethod
	def poll(cls, context):
		return (context.material != None and
			0 <= context.material.fmdl_material_parameter_active < len(context.material.fmdl_material_parameters)
		)
	
	def execute(self, context):
		material = context.material
		material.fmdl_material_parameters.remove(material.fmdl_material_parameter_active)
		if material.fmdl_material_parameter_active >= len(material.fmdl_material_parameters):
			material.fmdl_material_parameter_active = len(material.fmdl_material_parameters) - 1
		return {'FINISHED'}

class FMDL_Material_Parameter_List_MoveUp(bpy.types.Operator):
	bl_idname = "fmdl.material_parameter_moveup"
	bl_label = "Move Parameter Up"
	
	@classmethod
	def poll(cls, context):
		return (context.material != None and
			1 <= context.material.fmdl_material_parameter_active < len(context.material.fmdl_material_parameters)
		)
	
	def execute(self, context):
		material = context.material
		material.fmdl_material_parameters.move(
			material.fmdl_material_parameter_active,
			material.fmdl_material_parameter_active - 1
		)
		material.fmdl_material_parameter_active -= 1
		return {'FINISHED'}

class FMDL_Material_Parameter_List_MoveDown(bpy.types.Operator):
	bl_idname = "fmdl.material_parameter_movedown"
	bl_label = "Move Parameter Down"
	
	@classmethod
	def poll(cls, context):
		return (context.material != None and
			0 <= context.material.fmdl_material_parameter_active < len(context.material.fmdl_material_parameters) - 1
		)
	
	def execute(self, context):
		material = context.material
		material.fmdl_material_parameters.move(
			material.fmdl_material_parameter_active,
			material.fmdl_material_parameter_active + 1
		)
		material.fmdl_material_parameter_active += 1
		return {'FINISHED'}

class FMDL_Material_Parameter_Name_List(bpy.types.UIList):
	def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
		row = layout.row(align = True)
		row.alignment = 'EXPAND'
		row.prop(item, 'name', text = "", emboss = False)

class FMDL_Material_Panel(bpy.types.Panel):
	bl_label = "FMDL Material Settings"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "material"
	
	@classmethod
	def poll(cls, context):
		return context.material != None
	
	def draw(self, context):
		material = context.material
		
		mainColumn = self.layout.column(align = True)
		mainColumn.prop(material, "fmdl_material_shader")
		mainColumn.prop(material, "fmdl_material_technique")
		
		mainColumn.separator()
		mainColumn.label("Material Parameters")
		parameterListRow = mainColumn.row()
		parameterListRow.template_list(
			FMDL_Material_Parameter_Name_List.__name__,
			"FMDL_Material_Parameter_Name_List",
			material,
			"fmdl_material_parameters",
			material,
			"fmdl_material_parameter_active"
		)
		
		listButtonColumn = parameterListRow.column(align = True)
		listButtonColumn.operator("fmdl.material_parameter_add", icon = 'ZOOMIN', text = "")
		listButtonColumn.operator("fmdl.material_parameter_remove", icon = 'ZOOMOUT', text = "")
		listButtonColumn.separator()
		listButtonColumn.operator("fmdl.material_parameter_moveup", icon = 'TRIA_UP', text = "")
		listButtonColumn.operator("fmdl.material_parameter_movedown", icon = 'TRIA_DOWN', text = "")
		
		if 0 <= material.fmdl_material_parameter_active < len(material.fmdl_material_parameters):
			valuesColumn = mainColumn.column()
			parameter = material.fmdl_material_parameter_active
			valuesColumn.prop(
				material.fmdl_material_parameters[material.fmdl_material_parameter_active],
				"parameters"
			)



class FMDL_Texture_Load_Ftex(bpy.types.Operator):
	"""Load the FTEX texture"""
	bl_idname = "fmdl.load_ftex"
	bl_label = "Load FTEX texture"
	
	@classmethod
	def poll(cls, context):
		texture = context.texture
		return (
			texture != None and
			texture.type == 'IMAGE' and
			texture.image != None and
			texture.image.filepath.lower().endswith('.ftex')
		)
	
	def execute(self, context):
		# Avoids a blender bug in which an invalid image can't be replaced with a valid one
		context.texture.image_user.use_auto_refresh = context.texture.image_user.use_auto_refresh
		
		Ftex.blenderImageLoadFtex(context.texture.image, bpy.app.tempdir)
		return {'FINISHED'}

def FMDL_Texture_Load_Ftex_Button(self, context):
	self.layout.operator(FMDL_Texture_Load_Ftex.bl_idname)

class FMDL_Texture_Panel(bpy.types.Panel):
	bl_label = "FMDL Texture Settings"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "texture"
	
	@classmethod
	def poll(cls, context):
		return context.texture != None
	
	def draw(self, context):
		texture = context.texture
		
		mainColumn = self.layout.column()
		mainColumn.prop(texture, "fmdl_texture_role", text = "Role")
		mainColumn.prop(texture, "fmdl_texture_filename", text = "Filename")
		mainColumn.prop(texture, "fmdl_texture_directory", text = "Directory")



classes = [
	FMDL_Scene_Import,
	FMDL_Scene_Export_Scene,
	FMDL_Scene_Export_Object,
	FMDL_Scene_Panel_FMDL_Compose,
	FMDL_Scene_Panel_FMDL_Remove,
	FMDL_Scene_Panel_FMDL_Export,
	FMDL_Scene_Panel_FMDL_Select_Filename,
	FMDL_Scene_Panel,
	
	FMDL_Mesh_Panel,
	
	FMDL_Material_Parameter_List_Add,
	FMDL_Material_Parameter_List_Remove,
	FMDL_Material_Parameter_List_MoveUp,
	FMDL_Material_Parameter_List_MoveDown,
	FMDL_Material_Parameter_Name_List,
	FMDL_Material_Panel,
	
	FMDL_Texture_Load_Ftex,
	FMDL_Texture_Panel,
]

def register():
	bpy.types.Object.fmdl_file = bpy.props.BoolProperty(name = "Is FMDL file", options = {'SKIP_SAVE'})
	bpy.types.Object.fmdl_filename = bpy.props.StringProperty(name = "FMDL filename", options = {'SKIP_SAVE'})
	bpy.types.Material.fmdl_material_parameter_active = bpy.props.IntProperty(name = "FMDL_Material_Parameter_Name_List index", default = -1, options = {'SKIP_SAVE'})
	
	for c in classes:
		bpy.utils.register_class(c)
	
	bpy.types.INFO_MT_file_import.append(FMDL_Scene_FMDL_Import_MenuItem)
	bpy.types.INFO_MT_file_export.append(FMDL_Scene_FMDL_Export_MenuItem)
	bpy.types.TEXTURE_PT_image.append(FMDL_Texture_Load_Ftex_Button)

def unregister():
	bpy.types.TEXTURE_PT_image.remove(FMDL_Texture_Load_Ftex_Button)
	bpy.types.INFO_MT_file_export.remove(FMDL_Scene_FMDL_Export_MenuItem)
	bpy.types.INFO_MT_file_import.remove(FMDL_Scene_FMDL_Import_MenuItem)
	
	for c in classes[::-1]:
		bpy.utils.unregister_class(c)
