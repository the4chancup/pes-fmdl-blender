import bpy
import bpy.props

from . import Operators

def importMenu():
	if 'TOPBAR_MT_file_import' in dir(bpy.types):
		return bpy.types.TOPBAR_MT_file_import
	else:
		return bpy.types.INFO_MT_file_import
def exportMenu():
	if 'TOPBAR_MT_file_export' in dir(bpy.types):
		return bpy.types.TOPBAR_MT_file_export
	else:
		return bpy.types.INFO_MT_file_export



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

class Material_Parameter_List_add(bpy.types.Operator):
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

class Material_Parameter_List_remove(bpy.types.Operator):
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

class Material_Parameter_List_moveup(bpy.types.Operator):
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

class Material_Parameter_List_movedown(bpy.types.Operator):
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

class Material_Parameter_Name_List(bpy.types.UIList):
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
			Material_Parameter_Name_List.__name__,
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

class FMDL_Scene_Panel_FMDL_Compose(bpy.types.Operator):
	"""Enable separate exporting of the active object"""
	bl_idname = "fmdl.compose_exportable"
	bl_label = "Compose Fmdl"
	bl_options = {'PRESET', 'UNDO'}
	
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
	bl_options = {'PRESET', 'UNDO'}
	
	objectName = bpy.props.StringProperty(name = "Object to export")
	
	def execute(self, context):
		context.scene.objects[self.objectName].fmdl_file = False
		return {'FINISHED'}

class FMDL_Scene_Panel_FMDL_Export(bpy.types.Operator):
	"""Export as PES FMDL file"""
	bl_idname = "fmdl.export_listed_object"
	bl_label = "Export Fmdl"
	bl_options = {'PRESET'}
	
	objectName = bpy.props.StringProperty(name = "Object to export")
	
	def execute(self, context):
		return Operators.ExportFmdl.do_execute(
			self,
			context,
			self.objectName,
			context.scene.objects[self.objectName].fmdl_filename
		)

class FMDL_Scene_Panel_FMDL_Select_Filename(bpy.types.Operator):
	"""Select a filename to export this FMDL file"""
	bl_idname = "fmdl.select_filename"
	bl_label = "Select Filename"
	bl_options = {'PRESET', 'UNDO'}
	
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
		mainColumn.operator(Operators.ImportFmdl.bl_idname)
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

def FMDL_Import_MenuItem(self, context):
	self.layout.operator(Operators.ImportFmdl.bl_idname, text=Operators.ImportFmdl.import_label)

def FMDL_Export_MenuItem(self, context):
	self.layout.operator(Operators.ExportSceneFmdl.bl_idname, text=Operators.ExportSceneFmdl.export_label)



classes = [
	FMDL_Mesh_Panel,
	Material_Parameter_List_add,
	Material_Parameter_List_remove,
	Material_Parameter_List_moveup,
	Material_Parameter_List_movedown,
	Material_Parameter_Name_List,
	FMDL_Material_Panel,
	FMDL_Texture_Panel,
	FMDL_Scene_Panel_FMDL_Compose,
	FMDL_Scene_Panel_FMDL_Remove,
	FMDL_Scene_Panel_FMDL_Export,
	FMDL_Scene_Panel_FMDL_Select_Filename,
	FMDL_Scene_Panel,
]

def register():
	for c in classes:
		bpy.utils.register_class(c)
	importMenu().append(FMDL_Import_MenuItem)
	exportMenu().append(FMDL_Export_MenuItem)

def unregister():
	exportMenu().remove(FMDL_Export_MenuItem)
	importMenu().remove(FMDL_Import_MenuItem)
	for c in classes[::-1]:
		bpy.utils.unregister_class(c)
