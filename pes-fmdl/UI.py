import bpy
import bpy.props
import bpy_extras.io_utils

from . import FmdlFile, Ftex, IO, PesSkeletonData



vertexGroupSummaryCache = {}

def vertexGroupSummaryGet(objectName):
	global vertexGroupSummaryCache
	if objectName not in vertexGroupSummaryCache:
		return None
	return vertexGroupSummaryCache[objectName]

def vertexGroupSummarySet(objectName, value):
	global vertexGroupSummaryCache
	vertexGroupSummaryCache[objectName] = value

def vertexGroupSummaryRemove(objectName):
	global vertexGroupSummaryCache
	if objectName in vertexGroupSummaryCache:
		del vertexGroupSummaryCache[objectName]

def vertexGroupSummaryCleanup(objectNames):
	global vertexGroupSummaryCache
	for objectName in list(vertexGroupSummaryCache.keys()):
		if objectName not in objectNames:
			del vertexGroupSummaryCache[objectName]

inActiveUpdate = False
latestObjectTree = ()
latestMeshObjectList = ()

def exportSummaryTextName(objectName):
	return "Export Summary for %s" % objectName

def updateSummaries(scene):
	textNames = set()
	for object in scene.objects:
		objectName = object.name
		parent = object.parent
		while parent is not None:
			objectName = "%s/%s" % (parent.name, objectName)
			parent = parent.parent
		
		textName = exportSummaryTextName(objectName)
		if object.fmdl_file:
			textNames.add(textName)
			summary = IO.exportSummary(bpy.context, object.name)
			if textName in bpy.data.texts:
				text = bpy.data.texts[textName]
				if text.as_string() != summary:
					text.from_string(summary)
			else:
				text = bpy.data.texts.new(textName)
				text.user_clear() # blender bug: texts start as users=1 instead of users=0
				text.from_string(summary)
				c = bpy.context.copy()
				c['edit_text'] = text
				bpy.ops.text.make_internal(c)
				bpy.ops.text.jump(c, line=1)
	removeList = []
	for textName in bpy.data.texts.keys():
		if textName.startswith("Export Summary for ") and textName not in textNames:
			removeList.append(textName)
	for textName in removeList:
		bpy.data.texts.remove(bpy.data.texts[textName])

def synchronizeMeshOrder(scene):
	objectNames = {o.name for o in scene.objects}
	rootObjectNames = [o.name for o in scene.objects if o.parent is None or o.parent.name not in objectNames]
	
	meshObjects = []
	def findMeshObjects(object):
		if object.type == 'MESH':
			meshObjects.append(object.name)
		childNames = [child.name for child in object.children if child.name in objectNames]
		for childName in sorted(childNames):
			findMeshObjects(bpy.data.objects[childName])
	for objectName in sorted(rootObjectNames):
		findMeshObjects(bpy.data.objects[objectName])
	
	for objectName in reversed(meshObjects):
		scene.objects.unlink(bpy.data.objects[objectName])
		scene.objects.link(bpy.data.objects[objectName])

@bpy.app.handlers.persistent
def FMDL_Util_TrackChanges(scene):
	#
	# This function does three separate things:
	# - it keeps vertexGroupSummaryCache up to date, with help of latestMeshObjectList
	# - it keeps the list of export summaries up to date, with help of latestObjectTree
	# - it keeps the scene mesh order sorted, with help of latestObjectTree
	# These different jobs are merged into this single handler for efficiency,
	# as this handler is called very often and needs to be tight.
	#
	#
	global inActiveUpdate
	if bpy.context.mode != 'OBJECT':
		return
	if inActiveUpdate:
		return
	objectTree = []
	meshObjectList = []
	objectChanged = False
	objectListChanged = False
	for object in scene.objects:
		objectTree.append((object.name, object.parent.name if object.parent is not None else None))	
		if object.is_updated or object.is_updated_data:
			objectChanged = True
		if object.type == 'MESH':
			if object.is_updated_data:
				vertexGroupSummaryRemove(object.name)
			else:
				meshObjectList.append(object.name)
	
	global latestObjectTree
	objectTreeTuple = tuple(objectTree)
	if objectTreeTuple != latestObjectTree:
		latestObjectTree = objectTreeTuple
		objectChanged = True
		objectListChanged = True
	
	global latestMeshObjectList
	meshObjectListTuple = tuple(meshObjectList)
	if meshObjectListTuple != latestMeshObjectList:
		latestMeshObjectList = meshObjectListTuple
		vertexGroupSummaryCleanup(latestMeshObjectList)
	
	if objectChanged:
		updateSummaries(scene)
	
	if objectListChanged:
		inActiveUpdate = True
		synchronizeMeshOrder(scene)
		inActiveUpdate = False



class FMDL_Util_window_set_screen(bpy.types.Operator):
	"""Set window screen"""
	bl_idname = "fmdl.window_set_screen"
	bl_label = "Set window screen"
	bl_options = {'INTERNAL'}
	
	screenName = bpy.props.StringProperty(name = "Screen name")
	
	def execute(self, context):
		context.window.screen = bpy.data.screens[self.screenName]
		return {'FINISHED'}

def createTextEditWindow(context):
	originalWindow = context.window
	
	bpy.ops.screen.area_dupli('INVOKE_DEFAULT')
	screen = context.window_manager.windows[-1].screen
	
	# This must happen before the window is destroyed.
	screen.areas[0].type = 'TEXT_EDITOR'
	
	screen.name = "Export Summaries"
	screenName = screen.name
	c = context.copy()
	c['window'] = context.window_manager.windows[-1]
	bpy.ops.wm.window_close(c)
	
	c = context.copy()
	c['window'] = originalWindow
	bpy.ops.wm.window_duplicate(c)
	oldScreenName = context.window_manager.windows[-1].screen.name
	
	c = context.copy()
	c['window'] = context.window_manager.windows[-1]
	c['screen'] = bpy.data.screens[oldScreenName]
	bpy.ops.screen.delete(c)
	
	c = context.copy()
	c['window'] = context.window_manager.windows[-1]
	bpy.ops.fmdl.window_set_screen(c, screenName = screen.name)
	
	return screen.areas[0]

def findTextEditArea(context):
	for window in context.window_manager.windows:
		if window.screen is not None:
			for area in window.screen.areas:
				if area.type == 'TEXT_EDITOR':
					return area
	return None

def showExportSummary(area, objectName):
	textName = exportSummaryTextName(objectName)
	if textName in bpy.data.texts:
		for space in area.spaces:
			if space.type == 'TEXT_EDITOR':
				space.text = bpy.data.texts[textName]
				break



class FMDL_Scene_Import(bpy.types.Operator, bpy_extras.io_utils.ImportHelper):
	"""Load a PES FMDL file"""
	bl_idname = "import_scene.fmdl"
	bl_label = "Import Fmdl"
	bl_options = {'REGISTER', 'UNDO'}
	
	extensions_enabled = bpy.props.BoolProperty(name = "Enable blender-pes-fmdl extensions", default = True)
	loop_preservation = bpy.props.BoolProperty(name = "Preserve split vertices", default = True)
	mesh_splitting = bpy.props.BoolProperty(name = "Autosplit overlarge meshes", default = True)
	load_textures = bpy.props.BoolProperty(name = "Load textures", default = True)
	import_all_bounding_boxes = bpy.props.BoolProperty(name = "Import all bounding boxes", default = False)
	
	import_label = "PES FMDL (.fmdl)"
	
	filename_ext = ".fmdl"
	filter_glob = bpy.props.StringProperty(default="*.fmdl", options={'HIDDEN'})
	
	def invoke(self, context, event):
		self.extensions_enabled = context.scene.fmdl_import_extensions_enabled
		self.loop_preservation = context.scene.fmdl_import_loop_preservation
		self.mesh_splitting = context.scene.fmdl_import_mesh_splitting
		self.load_textures = context.scene.fmdl_import_load_textures
		self.import_all_bounding_boxes = context.scene.fmdl_import_all_bounding_boxes
		return bpy_extras.io_utils.ImportHelper.invoke(self, context, event)
	
	def execute(self, context):
		filename = self.filepath
		
		importSettings = IO.ImportSettings()
		importSettings.enableExtensions = self.extensions_enabled
		importSettings.enableVertexLoopPreservation = self.loop_preservation
		importSettings.enableMeshSplitting = self.mesh_splitting
		importSettings.enableLoadTextures = self.load_textures
		importSettings.enableImportAllBoundingBoxes = self.import_all_bounding_boxes
		
		fmdlFile = FmdlFile.FmdlFile()
		fmdlFile.readFile(filename)
		
		rootObject = IO.importFmdl(context, fmdlFile, filename, importSettings)
		
		rootObject.fmdl_export_extensions_enabled = importSettings.enableExtensions
		rootObject.fmdl_export_loop_preservation = importSettings.enableVertexLoopPreservation
		rootObject.fmdl_export_mesh_splitting = importSettings.enableMeshSplitting
		
		return {'FINISHED'}

class FMDL_Scene_Export_Scene(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
	"""Export the entire scene as a single PES FMDL file"""
	bl_idname = "export_scene.fmdl"
	bl_label = "Export Fmdl"
	bl_options = {'REGISTER'}
	
	extensions_enabled = bpy.props.BoolProperty(name = "Enable blender-pes-fmdl extensions", default = True)
	loop_preservation = bpy.props.BoolProperty(name = "Preserve split vertices", default = True)
	mesh_splitting = bpy.props.BoolProperty(name = "Autosplit overlarge meshes", default = True)
	
	export_label = "PES FMDL (.fmdl)"
	
	filename_ext = ".fmdl"
	filter_glob = bpy.props.StringProperty(default="*.fmdl", options={'HIDDEN'})
	
	@classmethod
	def poll(cls, context):
		return context.mode == 'OBJECT'
	
	def execute(self, context):
		exportSettings = IO.ExportSettings()
		exportSettings.enableExtensions = self.extensions_enabled
		exportSettings.enableVertexLoopPreservation = self.loop_preservation
		exportSettings.enableMeshSplitting = self.mesh_splitting
		
		try:
			fmdlFile = IO.exportFmdl(context, None, exportSettings)
		except IO.FmdlExportError as error:
			self.report({'ERROR'}, "Error exporting Fmdl: " + "; ".join(error.errors))
			print("Error exporting Fmdl:\n" + "\n".join(error.errors))
			return {'CANCELLED'}
		
		fmdlFile.writeFile(self.filepath)
		
		self.report({'INFO'}, "Fmdl exported successfully.") 
		
		return {'FINISHED'}

class FMDL_Scene_Export_Object(bpy.types.Operator, bpy_extras.io_utils.ExportHelper):
	"""Export an individual object as a PES FMDL file"""
	bl_idname = "export_scene.fmdl_object"
	bl_label = "Export Fmdl"
	bl_options = {'REGISTER'}
	
	objectName = bpy.props.StringProperty("Object to export")
	extensions_enabled = bpy.props.BoolProperty(name = "Enable blender-pes-fmdl extensions", default = True)
	loop_preservation = bpy.props.BoolProperty(name = "Preserve split vertices", default = True)
	mesh_splitting = bpy.props.BoolProperty(name = "Autosplit overlarge meshes", default = True)
	
	export_label = "PES FMDL (.fmdl)"
	
	filename_ext = ".fmdl"
	filter_glob = bpy.props.StringProperty(default="*.fmdl", options={'HIDDEN'})
	
	@classmethod
	def poll(cls, context):
		return context.mode == 'OBJECT' and context.active_object != None
	
	def invoke(self, context, event):
		self.objectName = context.active_object.name
		self.extensions_enabled = context.active_object.fmdl_export_extensions_enabled
		self.loop_preservation = context.active_object.fmdl_export_loop_preservation
		self.mesh_splitting = context.active_object.fmdl_export_mesh_splitting
		if context.active_object.fmdl_filename != "":
			self.filepath = context.active_object.fmdl_filename
		return bpy_extras.io_utils.ExportHelper.invoke(self, context, event)
	
	def execute(self, context):
		summaryArea = findTextEditArea(context)
		if summaryArea is not None:
			showExportSummary(summaryArea, self.objectName)
		
		exportSettings = IO.ExportSettings()
		exportSettings.enableExtensions = self.extensions_enabled
		exportSettings.enableVertexLoopPreservation = self.loop_preservation
		exportSettings.enableMeshSplitting = self.mesh_splitting
		
		try:
			fmdlFile = IO.exportFmdl(context, self.objectName, exportSettings)
		except IO.FmdlExportError as error:
			self.report({'ERROR'}, "Error exporting Fmdl: " + "; ".join(error.errors))
			print("Error exporting Fmdl:\n" + "\n".join(error.errors))
			return {'CANCELLED'}
		
		fmdlFile.writeFile(self.filepath)
		
		self.report({'INFO'}, "Fmdl exported successfully.") 
		
		return {'FINISHED'}

class FMDL_Scene_Export_Object_Summary(bpy.types.Operator):
	"""Show a summary for a PES FMDL export of an invidual object"""
	bl_idname = "fmdl.export_summary_object"
	bl_label = "Export Summary"
	bl_options = {'REGISTER'}
	
	objectName = bpy.props.StringProperty("Object to export")
	
	@classmethod
	def poll(cls, context):
		return context.mode == 'OBJECT' and context.active_object != None
	
	def execute(self, context):
		area = findTextEditArea(context)
		if area is None:
			area = createTextEditWindow(context)
		showExportSummary(area, self.objectName)
		return {'FINISHED'}

class FMDL_Scene_Panel_FMDL_Import_Settings(bpy.types.Menu):
	"""Import Settings"""
	bl_label = "Import settings"
	
	def draw(self, context):
		self.layout.prop(context.scene, 'fmdl_import_extensions_enabled')
		
		row = self.layout.row()
		row.prop(context.scene, 'fmdl_import_loop_preservation')
		row.enabled = context.scene.fmdl_import_extensions_enabled
		
		row = self.layout.row()
		row.prop(context.scene, 'fmdl_import_mesh_splitting')
		row.enabled = context.scene.fmdl_import_extensions_enabled
		
		row = self.layout.row()
		row.prop(context.scene, 'fmdl_import_load_textures')
		
		row = self.layout.row()
		row.prop(context.scene, 'fmdl_import_all_bounding_boxes')

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

class FMDL_Scene_Panel_FMDL_Export_Settings(bpy.types.Menu):
	"""Export Settings"""
	bl_label = "Export settings"
	
	def draw(self, context):
		self.layout.prop(context.active_object, 'fmdl_export_extensions_enabled')
		row = self.layout.row()
		row.prop(context.active_object, 'fmdl_export_loop_preservation')
		row.enabled = context.active_object.fmdl_export_extensions_enabled
		row = self.layout.row()
		row.prop(context.active_object, 'fmdl_export_mesh_splitting')
		row.enabled = context.active_object.fmdl_export_extensions_enabled

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
		importRow = mainColumn.row()
		buttonColumn = importRow.column()
		buttonColumn.operator(FMDL_Scene_Import.bl_idname)
		buttonColumn.operator(FMDL_Scene_Panel_FMDL_Compose.bl_idname)
		importRow.menu(FMDL_Scene_Panel_FMDL_Import_Settings.__name__, icon = 'DOWNARROW_HLT', text = "")
		for object in fmdlFileObjects:
			box = mainColumn.box()
			column = box.column()
			
			row = column.row()
			row.label("Object: %s" % object.name)
			row.operator(FMDL_Scene_Panel_FMDL_Remove.bl_idname, text = "", icon = 'X').objectName = object.name
			
			row = column.row(align = True)
			row.prop(object, 'fmdl_filename', text = "Export Path")
			row.operator(FMDL_Scene_Panel_FMDL_Select_Filename.bl_idname, text = "", icon = 'FILESEL').objectName = object.name
			
			row = column.row()
			row.operator_context = 'EXEC_DEFAULT'
			row.context_pointer_set('active_object', object)
			subrow = row.row()
			exportSettings = subrow.operator(FMDL_Scene_Export_Object.bl_idname)
			exportSettings.objectName = object.name
			exportSettings.filepath = object.fmdl_filename
			exportSettings.extensions_enabled = object.fmdl_export_extensions_enabled
			exportSettings.loop_preservation = object.fmdl_export_loop_preservation
			exportSettings.mesh_splitting = object.fmdl_export_mesh_splitting
			if object.fmdl_filename == "":
				subrow.enabled = False
			row.operator(FMDL_Scene_Export_Object_Summary.bl_idname, text = "", icon = 'INFO').objectName = object.name
			row.menu(FMDL_Scene_Panel_FMDL_Export_Settings.__name__, icon = 'DOWNARROW_HLT', text = "")



def pesBoneList(skeletonType):
	parts = skeletonType.split('_', 1)
	if len(parts) != 2:
		return None
	pesVersion = parts[0]
	bodyPart = parts[1]
	if pesVersion not in PesSkeletonData.skeletonBones:
		return None
	if bodyPart not in PesSkeletonData.skeletonBones[pesVersion]:
		return None
	return PesSkeletonData.skeletonBones[pesVersion][bodyPart]

def armatureIsPesSkeleton(armature, skeletonType):
	boneNames = pesBoneList(skeletonType)
	if boneNames is None:
		return False
	boneNames = set(boneNames)
	
	if armature.is_editmode:
		blenderBoneNames = [bone.name for bone in armature.edit_bones]
	else:
		blenderBoneNames = [bone.name for bone in armature.bones]
	for boneName in blenderBoneNames:
		if boneName not in boneNames:
			return False
	return True

def FMDL_Scene_Skeleton_update_type(scene, context):
	newType = scene.fmdl_skeleton_type
	for object in scene.objects:
		if object.type == 'ARMATURE':
			if object.fmdl_skeleton_replace_type != newType:
				object.fmdl_skeleton_replace = armatureIsPesSkeleton(object.data, newType)
				object.fmdl_skeleton_replace_type = newType

def FMDL_Scene_Skeleton_get_replace(armatureObject):
	skeletonType = bpy.context.scene.fmdl_skeleton_type
	if (
		   'fmdl_skeleton_replace' not in armatureObject
		or 'fmdl_skeleton_replace_type' not in armatureObject
		or armatureObject.fmdl_skeleton_replace_type != skeletonType
	):
		return armatureIsPesSkeleton(armatureObject.data, bpy.context.scene.fmdl_skeleton_type)
	return armatureObject.fmdl_skeleton_replace

def FMDL_Scene_Skeleton_set_replace(armatureObject, enabled):
	armatureObject.fmdl_skeleton_replace_type = bpy.context.scene.fmdl_skeleton_type
	armatureObject.fmdl_skeleton_replace = enabled

class FMDL_Scene_Skeleton_List(bpy.types.UIList):
	def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
		row = layout.row(align = True)
		row.prop(item, 'fmdl_skeleton_replace_effective', text = '')
		row.label(text = FMDL_Scene_Skeleton_List.objectName(item))
	
	def filter_items(self, context, data, propname):
		filterList = []
		names = {}
		
		for blenderObject in data.objects:
			if blenderObject.type == 'ARMATURE':
				filterList.append(self.bitflag_filter_item)
				names[blenderObject] = FMDL_Scene_Skeleton_List.objectName(blenderObject)
			else:
				filterList.append(0)
		
		indices = {}
		for name in sorted(list(names.values())):
			indices[name] = len(indices)
		
		sortList = []
		for blenderObject in data.objects:
			if blenderObject in names:
				sortList.append(indices[names[blenderObject]])
			else:
				sortList.append(-1)
		
		return (filterList, sortList)
	
	def objectName(blenderObject):
		if blenderObject.parent is None:
			return blenderObject.name
		else:
			return "%s :: %s" % (FMDL_Scene_Skeleton_List.objectName(blenderObject.parent), blenderObject.name)

def addBone(blenderArmature, bone, boneIDs, bonesByName):
	if bone in boneIDs:
		return boneIDs[bone]
	
	useConnect = False
	if bone.name in PesSkeletonData.bones:
		pesBone = PesSkeletonData.bones[bone.name]
		(headX, headY, headZ) = pesBone.startPosition
		(tailX, tailY, tailZ) = pesBone.endPosition
		head = (headX, -headZ, headY)
		tail = (tailX, -tailZ, tailY)
		parentBoneName = pesBone.renderParent
		while parentBoneName is not None and parentBoneName not in bonesByName:
			parentBoneName = PesSkeletonData.bones[parentBoneName].renderParent
		if parentBoneName is None:
			parentBone = None
		else:
			parentBone = bonesByName[parentBoneName]
			parentDistanceSquared = sum(((PesSkeletonData.bones[parentBoneName].endPosition[i] - pesBone.startPosition[i]) ** 2 for i in range(3)))
			if parentBoneName == pesBone.renderParent and parentDistanceSquared < 0.0000000001:
				useConnect = True
	else:
		tail = (bone.globalPosition.x, -bone.globalPosition.z, bone.globalPosition.y)
		head = (bone.localPosition.x, -bone.localPosition.z, bone.localPosition.y)
		parentBone = bone.parent
	
	if parentBone != None:
		parentBoneID = addBone(blenderArmature, parentBone, boneIDs, bonesByName)
	else:
		parentBoneID = None
	
	if sum(((tail[i] - head[i]) ** 2 for i in range(3))) < 0.0000000001:
		tail = (head[0], head[1], head[2] - 0.00001)
	
	blenderEditBone = blenderArmature.edit_bones.new(bone.name)
	boneID = blenderEditBone.name
	boneIDs[bone] = boneID
	
	blenderEditBone.head = head
	blenderEditBone.tail = tail
	blenderEditBone.hide = False
	if parentBoneID != None:
		blenderEditBone.parent = blenderArmature.edit_bones[parentBoneID]
		blenderEditBone.use_connect = useConnect
	
	return boneID

def createPesBone(blenderArmature, boneName, boneNames):
	if boneName not in PesSkeletonData.bones:
		return
	if boneName in blenderArmature.edit_bones:
		return
	
	pesBone = PesSkeletonData.bones[boneName]
	parentBoneName = pesBone.renderParent
	while parentBoneName is not None and parentBoneName not in boneNames:
		parentBoneName = PesSkeletonData.bones[parentBoneName].renderParent
	if parentBoneName is not None:
		parentDistanceSquared = sum(((PesSkeletonData.bones[parentBoneName].endPosition[i] - pesBone.startPosition[i]) ** 2 for i in range(3)))
		useConnect = (parentBoneName == pesBone.renderParent and parentDistanceSquared < 0.0000000001)
		createPesBone(blenderArmature, parentBoneName, boneNames)
	
	(headX, headY, headZ) = pesBone.startPosition
	(tailX, tailY, tailZ) = pesBone.endPosition
	head = (headX, -headZ, headY)
	tail = (tailX, -tailZ, tailY)
	if sum(((tail[i] - head[i]) ** 2 for i in range(3))) < 0.0000000001:
		tail = (head[0], head[1], head[2] - 0.00001)
	
	blenderEditBone = blenderArmature.edit_bones.new(boneName)
	blenderEditBone.head = head
	blenderEditBone.tail = tail
	blenderEditBone.hide = False
	if parentBoneName is not None:
		blenderEditBone.parent = blenderArmature.edit_bones[parentBoneName]
		blenderEditBone.use_connect = useConnect

def createPesSkeleton(context, skeletonType):
	boneNames = pesBoneList(skeletonType)
	
	armatureName = "Skeleton"
	for enumItem in bpy.types.Scene.bl_rna.properties['fmdl_skeleton_type'].enum_items:
		if enumItem.identifier == skeletonType:
			armatureName = enumItem.name
			break
	blenderArmature = bpy.data.armatures.new(armatureName)
	blenderArmature.show_names = True
	
	blenderArmatureObject = bpy.data.objects.new(armatureName, blenderArmature)
	armatureObjectID = blenderArmatureObject.name
	
	context.scene.objects.link(blenderArmatureObject)
	context.scene.objects.active = blenderArmatureObject
	bpy.ops.object.mode_set(context.copy(), mode = 'EDIT')
	
	boneIDs = {}
	for boneName in boneNames:
		createPesBone(blenderArmature, boneName, boneNames)
	
	bpy.ops.object.mode_set(context.copy(), mode = 'OBJECT')
	context.scene.update()
	return (armatureObjectID, armatureName)

def replaceArmatures(context, armatureObjectID, preferredName):
	remapList = []
	for object in bpy.data.objects:
		if (
			    object.type == 'ARMATURE'
			and object.fmdl_skeleton_replace_effective
			and object.name != armatureObjectID
		):
			remapList.append(object.name)
	
	parentObjectID = None
	if len(remapList) == 1:
		preferredName = remapList[0]
		parent = bpy.data.objects[remapList[0]].parent
		if parent is not None:
			parentObjectID = parent.name
	
	for objectID in remapList:
		oldArmatureObject = bpy.data.objects[objectID]
		oldArmature = oldArmatureObject.data
		
		oldArmature.user_remap(bpy.data.objects[armatureObjectID].data)
		bpy.data.armatures.remove(oldArmature)
		
		context.scene.objects.unlink(oldArmatureObject)
		oldArmatureObject.user_remap(bpy.data.objects[armatureObjectID])
		bpy.data.objects.remove(oldArmatureObject)
	if parentObjectID is not None:
		bpy.data.objects[armatureObjectID].parent = bpy.data.objects[parentObjectID]
	bpy.data.objects[armatureObjectID].name = preferredName
	context.scene.update()

class FMDL_Scene_Skeleton_Create(bpy.types.Operator):
	"""Create PES skeleton"""
	bl_idname = "fmdl.skeleton_create"
	bl_label = "Create Skeleton"
	bl_options = {'REGISTER', 'UNDO'}
	
	@classmethod
	def poll(cls, context):
		return context.mode == 'OBJECT'
	
	def execute(self, context):
		createPesSkeleton(context, context.scene.fmdl_skeleton_type)
		return {'FINISHED'}

class FMDL_Scene_Skeleton_CreateReplace(bpy.types.Operator):
	"""Create PES skeleton and replace existing"""
	bl_idname = "fmdl.skeleton_create_replace"
	bl_label = "Create and replace existing:"
	bl_options = {'REGISTER', 'UNDO'}
	
	@classmethod
	def poll(cls, context):
		return context.mode == 'OBJECT'
	
	def execute(self, context):
		(newArmatureObjectID, preferredName) = createPesSkeleton(context, context.scene.fmdl_skeleton_type)
		replaceArmatures(context, newArmatureObjectID, preferredName)
		return {'FINISHED'}

class FMDL_Scene_Skeleton_Panel(bpy.types.Panel):
	bl_label = "FMDL Skeleton"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "scene"
	
	@classmethod
	def poll(cls, context):
		return context.scene != None
	
	def draw(self, context):
		scene = context.scene
		self.layout.prop(scene, 'fmdl_skeleton_type', text = "Skeleton Type")
		self.layout.operator(FMDL_Scene_Skeleton_Create.bl_idname)
		self.layout.operator(FMDL_Scene_Skeleton_CreateReplace.bl_idname)
		self.layout.template_list(
			FMDL_Scene_Skeleton_List.__name__,
			"FMDL_Scene_Skeleton",
			scene,
			"objects",
			scene,
			"fmdl_skeleton_replace_active",
			rows = 5
		)



class FMDL_Object_BoundingBox_Create(bpy.types.Operator):
	"""Create custom bounding box"""
	bl_idname = "fmdl.boundingbox_create"
	bl_label = "Create custom bounding box"
	bl_options = {'REGISTER', 'UNDO'}
	
	@classmethod
	def poll(cls, context):
		if not (
			    context.mode == 'OBJECT'
			and context.object is not None
			and context.object.type == 'MESH'
		):
			return False
		for child in context.object.children:
			if child.type == 'LATTICE':
				return False
		return True
	
	def execute(self, context):
		IO.createFittingBoundingBox(context, context.object)
		return {'FINISHED'}

class FMDL_Object_BoundingBox_Remove(bpy.types.Operator):
	"""Remove custom bounding box"""
	bl_idname = "fmdl.boundingbox_remove"
	bl_label = "Remove custom bounding box"
	bl_options = {'REGISTER', 'UNDO'}
	
	@classmethod
	def poll(cls, context):
		if not (
			    context.mode == 'OBJECT'
			and context.object is not None
			and context.object.type == 'MESH'
		):
			return False
		for child in context.object.children:
			if child.type == 'LATTICE':
				return True
		return False
	
	def execute(self, context):
		removeList = []
		for child in context.object.children:
			if child.type == 'LATTICE':
				removeList.append(child.name)
		for objectID in removeList:
			latticeID = bpy.data.objects[objectID].data.name
			while len(bpy.data.objects[objectID].users_scene) > 0:
				bpy.data.objects[objectID].users_scene[0].objects.unlink(bpy.data.objects[objectID])
			if bpy.data.objects[objectID].users == 0:
				bpy.data.objects.remove(bpy.data.objects[objectID])
			if bpy.data.lattices[latticeID].users == 0:
				bpy.data.lattices.remove(bpy.data.lattices[latticeID])
		return {'FINISHED'}

class FMDL_Object_BoundingBox_Panel(bpy.types.Panel):
	bl_label = "FMDL Bounding Box"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "object"
	
	@classmethod
	def poll(cls, context):
		return (
			    context.object is not None
			and context.object.type == 'MESH'
		)
	
	def draw(self, context):
		self.layout.operator(FMDL_Object_BoundingBox_Create.bl_idname)
		self.layout.operator(FMDL_Object_BoundingBox_Remove.bl_idname)



def FMDL_Mesh_BoneGroup_Bone_get_enabled(bone):
	return bone.name in bpy.context.active_object.vertex_groups

def FMDL_Mesh_BoneGroup_Bone_set_enabled(bone, enabled):
	vertex_groups = bpy.context.active_object.vertex_groups
	if enabled and bone.name not in vertex_groups:
		vertex_groups.new(bone.name)
		vertexGroupSummaryRemove(bpy.context.active_object.name)
	if not enabled and bone.name in vertex_groups:
		vertex_groups.remove(vertex_groups[bone.name])
		vertexGroupSummaryRemove(bpy.context.active_object.name)

class VertexGroupUsageSummary:
	def __init__(self):
		self.vertices = {}
		self.totalWeights = {}
	
	@staticmethod
	def meshObjectActiveArmature(meshObject):
		activeArmature = None
		for modifier in meshObject.modifiers:
			if modifier.type == 'ARMATURE':
				if activeArmature != None:
					return None
				activeArmature = modifier.object.data
		return activeArmature
	
	@staticmethod
	def compute(meshObject, armature):
		if vertexGroupSummaryGet(meshObject.name) != None:
			return
		summary = VertexGroupUsageSummary()
		for bone in armature.bones:
			summary.vertices[bone.name] = 0
			summary.totalWeights[bone.name] = 0.0
		vertexGroupNames = {}
		for vertexGroup in meshObject.vertex_groups:
			vertexGroupNames[vertexGroup.index] = vertexGroup.name
		for vertex in meshObject.data.vertices:
			for groupElement in vertex.groups:
				if groupElement.group not in vertexGroupNames:
					continue
				groupName = vertexGroupNames[groupElement.group]
				if groupName not in summary.vertices:
					continue
				summary.vertices[groupName] += 1
				summary.totalWeights[groupName] += groupElement.weight
		vertexGroupSummarySet(meshObject.name, summary)

class FMDL_Mesh_BoneGroup_List(bpy.types.UIList):
	def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
		armature = data
		meshObject = active_data
		
		row = layout.row(align = True)
		if meshObject.mode == 'OBJECT' and meshObject.data.fmdl_show_vertex_group_details:
			vertexGroupSummary = vertexGroupSummaryGet(meshObject.name)
			vertexCount = vertexGroupSummary.vertices[item.name]
			totalWeight = vertexGroupSummary.totalWeights[item.name]
			
			if meshObject.data.fmdl_show_vertex_group_vertices and meshObject.data.fmdl_show_vertex_group_weights:
				mainRow = row.split(percentage = 0.55, align = True)
			elif meshObject.data.fmdl_show_vertex_group_vertices or meshObject.data.fmdl_show_vertex_group_weights:
				mainRow = row.split(percentage = 0.7, align = True)
			else:
				mainRow = row.split(percentage = 1.0, align = True)
			
			checkboxNameRow = mainRow.row(align = True)
			checkboxRow = checkboxNameRow.row()
			checkboxRow.enabled = (not meshObject.data.fmdl_lock_nonempty_vertex_groups or vertexCount == 0)
			checkboxRow.prop(item, 'fmdl_bone_in_active_mesh', text = '')
			checkboxNameRow.label(text = item.name)
			
			if meshObject.data.fmdl_show_vertex_group_vertices and meshObject.data.fmdl_show_vertex_group_weights:
				verticesRow = mainRow.split(percentage = 0.45, align = True)
				verticesRow.alignment = 'RIGHT'
			elif meshObject.data.fmdl_show_vertex_group_vertices or meshObject.data.fmdl_show_vertex_group_weights:
				verticesRow = mainRow.split(percentage = 1.0, align = True)
				verticesRow.alignment = 'RIGHT'
			
			if meshObject.data.fmdl_show_vertex_group_vertices:
				verticesRow.label("%d v" % vertexCount)
			if meshObject.data.fmdl_show_vertex_group_weights:
				verticesRow.label("%.1f w" % totalWeight)
		else:
			row.prop(item, 'fmdl_bone_in_active_mesh', text = '')
			row.label(text = item.name)
	
	def filter_items(self, context, data, propname):
		boneNames = [bone.name for bone in data.bones]
		indices = {}
		for name in sorted(boneNames):
			indices[name] = len(indices)
		order = [indices[name] for name in boneNames]
		return ([], order)

class FMDL_Mesh_BoneGroup_RemoveUnused(bpy.types.Operator):
	"""Remove bones not bound to any vertices"""
	bl_idname = "fmdl.bonegroup_remove_unused"
	bl_label = "Remove Unused"
	bl_options = {'UNDO'}
	
	@classmethod
	def poll(cls, context):
		return (
			    context.active_object != None
			and context.active_object.type == 'MESH'
			and context.active_object.mode == 'OBJECT'
			and VertexGroupUsageSummary.meshObjectActiveArmature(context.active_object) != None
		)
	
	def execute(self, context):
		armature = VertexGroupUsageSummary.meshObjectActiveArmature(context.active_object)
		VertexGroupUsageSummary.compute(context.active_object, armature)
		vertexGroupSummary = vertexGroupSummaryGet(context.active_object.name)
		for (boneName, vertexCount) in vertexGroupSummary.vertices.items():
			if vertexCount == 0 and boneName in context.active_object.vertex_groups:
				context.active_object.vertex_groups.remove(context.active_object.vertex_groups[boneName])
		vertexGroupSummaryRemove(context.active_object.name)
		return {'FINISHED'}

class FMDL_Mesh_BoneGroup_Refresh(bpy.types.Operator):
	"""Refresh bone usage details"""
	bl_idname = "fmdl.bonegroup_refresh"
	bl_label = "Refresh"
	bl_options = set()
	
	@classmethod
	def poll(cls, context):
		return (
			    context.active_object != None
			and context.active_object.type == 'MESH'
			and context.active_object.mode == 'OBJECT'
		)
	
	def execute(self, context):
		vertexGroupSummaryRemove(context.active_object.name)
		return {'FINISHED'}

class FMDL_Mesh_BoneGroup_CopyFromSelected(bpy.types.Operator):
	"""Copy bone group from selected mesh"""
	bl_idname = "fmdl.bonegroup_copy_from_selected"
	bl_label = "Copy Bone Group from Selected"
	bl_options = {'UNDO'}
	
	@staticmethod
	def selectedObject(context, requiredType):
		differentObject = None
		for object in context.selected_objects:
			if object.name != context.active_object.name and object.type == requiredType:
				if differentObject != None:
					return None
				differentObject = object
		return differentObject
	
	@classmethod
	def poll(cls, context):
		return (
			    context.active_object != None
			and context.active_object.type == 'MESH'
			and context.active_object.mode == 'OBJECT'
			and VertexGroupUsageSummary.meshObjectActiveArmature(context.active_object) != None
			and FMDL_Mesh_BoneGroup_CopyFromSelected.selectedObject(context, 'MESH') != None
		)
	
	def execute(self, context):
		selectedMeshObject = FMDL_Mesh_BoneGroup_CopyFromSelected.selectedObject(context, 'MESH')
		desiredBones = selectedMeshObject.vertex_groups.keys()
		armature = VertexGroupUsageSummary.meshObjectActiveArmature(context.active_object)
		VertexGroupUsageSummary.compute(context.active_object, armature)
		vertexGroupSummary = vertexGroupSummaryGet(context.active_object.name)
		for boneName in context.active_object.vertex_groups.keys():
			if (
				    boneName in vertexGroupSummary.vertices
				and vertexGroupSummary.vertices[boneName] == 0
				and boneName not in desiredBones
			):
				context.active_object.vertex_groups.remove(context.active_object.vertex_groups[boneName])
		for boneName in desiredBones:
			if (
				    boneName not in context.active_object.vertex_groups
				and boneName in armature.bones
			):
				context.active_object.vertex_groups.new(boneName)
		vertexGroupSummaryRemove(context.active_object.name)
		return {'FINISHED'}

class FMDL_Mesh_BoneGroup_Specials(bpy.types.Menu):
	bl_label = "Bone Group operations"
	
	def draw(self, context):
		self.layout.operator(FMDL_Mesh_BoneGroup_RemoveUnused.bl_idname, icon = 'X')
		self.layout.operator(FMDL_Mesh_BoneGroup_Refresh.bl_idname, icon = 'FILE_REFRESH')
		self.layout.operator(FMDL_Mesh_BoneGroup_CopyFromSelected.bl_idname, icon = 'LINK_AREA')

class FMDL_Mesh_BoneGroup_Panel(bpy.types.Panel):
	bl_label = "FMDL Bone Group"
	bl_space_type = "PROPERTIES"
	bl_region_type = "WINDOW"
	bl_context = "data"
	
	@classmethod
	def poll(cls, context):
		return (
			    context.mesh != None
			and context.object != None
			and VertexGroupUsageSummary.meshObjectActiveArmature(context.object) != None
		)
	
	def draw(self, context):
		meshObject = context.object
		mesh = meshObject.data
		armature = VertexGroupUsageSummary.meshObjectActiveArmature(meshObject)
		
		computeDetails = (meshObject.mode == 'OBJECT' and mesh.fmdl_show_vertex_group_details)
		if computeDetails:
			VertexGroupUsageSummary.compute(meshObject, armature)
		
		self.layout.template_list(
			FMDL_Mesh_BoneGroup_List.__name__,
			"FMDL_Mesh_BoneGroups",
			armature,
			"bones",
			meshObject,
			"fmdl_bone_active",
			rows = 8
		)
		
		groupSize = len(meshObject.vertex_groups)
		
		summaryRow = self.layout.row()
		summaryRow.label("Bone group size: %s/32%s" % (groupSize, ' (!!)' if groupSize > 32 else ''))
		summaryRow.menu(FMDL_Mesh_BoneGroup_Specials.__name__, icon = 'DOWNARROW_HLT', text = "")
		
		detailLayout = self.layout.row()
		detailLayoutSplit = detailLayout.split(percentage = 0.6)
		leftColumn = detailLayoutSplit.column()
		rightColumn = detailLayoutSplit.column()
		
		detailRow = leftColumn.row()
		detailRow.enabled = (meshObject.mode == 'OBJECT')
		detailRow.prop(mesh, 'fmdl_show_vertex_group_details')
		lockRow = leftColumn.row()
		lockRow.enabled = computeDetails
		lockRow.prop(mesh, 'fmdl_lock_nonempty_vertex_groups')
		
		verticesRow = rightColumn.row()
		verticesRow.enabled = computeDetails
		verticesRow.prop(mesh, 'fmdl_show_vertex_group_vertices')
		weightsRow = rightColumn.row()
		weightsRow.enabled = computeDetails
		weightsRow.prop(mesh, 'fmdl_show_vertex_group_weights')

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
			"FMDL_Material_Parameter_Names",
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
	FMDL_Util_window_set_screen,
	
	FMDL_Scene_Import,
	FMDL_Scene_Export_Scene,
	FMDL_Scene_Export_Object,
	FMDL_Scene_Export_Object_Summary,
	FMDL_Scene_Panel_FMDL_Import_Settings,
	FMDL_Scene_Panel_FMDL_Compose,
	FMDL_Scene_Panel_FMDL_Remove,
	FMDL_Scene_Panel_FMDL_Export_Settings,
	FMDL_Scene_Panel_FMDL_Select_Filename,
	FMDL_Scene_Panel,
	
	FMDL_Scene_Skeleton_List,
	FMDL_Scene_Skeleton_Create,
	FMDL_Scene_Skeleton_CreateReplace,
	FMDL_Scene_Skeleton_Panel,
	
	FMDL_Object_BoundingBox_Create,
	FMDL_Object_BoundingBox_Remove,
	FMDL_Object_BoundingBox_Panel,
	
	FMDL_Mesh_BoneGroup_List,
	FMDL_Mesh_BoneGroup_RemoveUnused,
	FMDL_Mesh_BoneGroup_Refresh,
	FMDL_Mesh_BoneGroup_CopyFromSelected,
	FMDL_Mesh_BoneGroup_Specials,
	FMDL_Mesh_BoneGroup_Panel,
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
	skeletonTypes = []
	for pesVersion in PesSkeletonData.skeletonBones:
		for skeletonType in PesSkeletonData.skeletonBones[pesVersion]:
			skeletonTypes.append(('%s_%s' % (pesVersion, skeletonType), '%s %s' % (pesVersion, skeletonType), '%s %s' % (pesVersion, skeletonType)))
	skeletonTypes.reverse()
	defaultPesVersion = list(PesSkeletonData.skeletonBones.keys())[-1]
	defaultType = list(PesSkeletonData.skeletonBones[defaultPesVersion].keys())[0]
	defaultSkeletonType = '%s_%s' % (defaultPesVersion, defaultType)
	
	bpy.types.Object.fmdl_file = bpy.props.BoolProperty(name = "Is FMDL file", options = {'SKIP_SAVE'})
	bpy.types.Object.fmdl_filename = bpy.props.StringProperty(name = "FMDL filename", options = {'SKIP_SAVE'})
	bpy.types.Object.fmdl_export_extensions_enabled = bpy.props.BoolProperty(name = "Enable blender-pes-fmdl extensions", default = True)
	bpy.types.Object.fmdl_export_loop_preservation = bpy.props.BoolProperty(name = "Preserve split vertices", default = True)
	bpy.types.Object.fmdl_export_mesh_splitting = bpy.props.BoolProperty(name = "Autosplit overlarge meshes", default = True)
	bpy.types.Scene.fmdl_import_extensions_enabled = bpy.props.BoolProperty(name = "Enable blender-pes-fmdl extensions", default = True)
	bpy.types.Scene.fmdl_import_loop_preservation = bpy.props.BoolProperty(name = "Preserve split vertices", default = True)
	bpy.types.Scene.fmdl_import_mesh_splitting = bpy.props.BoolProperty(name = "Autosplit overlarge meshes", default = True)
	bpy.types.Scene.fmdl_import_load_textures = bpy.props.BoolProperty(name = "Load textures", default = True)
	bpy.types.Scene.fmdl_import_all_bounding_boxes = bpy.props.BoolProperty(name = "Import all bounding boxes", default = False)
	bpy.types.Scene.fmdl_skeleton_type = bpy.props.EnumProperty(name = "Skeleton type",
		items = skeletonTypes,
		default = defaultSkeletonType,
		update = FMDL_Scene_Skeleton_update_type,
		options = {'SKIP_SAVE'}
	)
	bpy.types.Object.fmdl_skeleton_replace = bpy.props.BoolProperty(name = "Replace skeleton", default = False, options = {'SKIP_SAVE'})
	bpy.types.Object.fmdl_skeleton_replace_type = bpy.props.EnumProperty(name = "Skeleton replacement target", items = skeletonTypes, options = {'SKIP_SAVE'})
	bpy.types.Object.fmdl_skeleton_replace_effective = bpy.props.BoolProperty(name = "Replace skeleton",
		get = FMDL_Scene_Skeleton_get_replace,
		set = FMDL_Scene_Skeleton_set_replace,
		options = {'SKIP_SAVE'}
	)
	bpy.types.Scene.fmdl_skeleton_replace_active = bpy.props.IntProperty(name = "FMDL_Scene_Skeleton_List index", default = -1, options = {'SKIP_SAVE'})
	bpy.types.Bone.fmdl_bone_in_active_mesh = bpy.props.BoolProperty(name = "Enabled",
		get = FMDL_Mesh_BoneGroup_Bone_get_enabled,
		set = FMDL_Mesh_BoneGroup_Bone_set_enabled,
		options = {'SKIP_SAVE'}
	)
	bpy.types.Object.fmdl_bone_active = bpy.props.IntProperty(name = "FMDL_Mesh_BoneGroup_List index", default = -1, options = {'SKIP_SAVE'})
	bpy.types.Mesh.fmdl_show_vertex_group_details = bpy.props.BoolProperty(name = "Show usage details", default = False, options = {'SKIP_SAVE'})
	bpy.types.Mesh.fmdl_lock_nonempty_vertex_groups = bpy.props.BoolProperty(name = "Lock in-use bone groups", default = True, options = {'SKIP_SAVE'})
	bpy.types.Mesh.fmdl_show_vertex_group_vertices = bpy.props.BoolProperty(name = "Show vertices [v]", default = True, options = {'SKIP_SAVE'})
	bpy.types.Mesh.fmdl_show_vertex_group_weights = bpy.props.BoolProperty(name = "Show weights [w]", default = True, options = {'SKIP_SAVE'})
	bpy.types.Material.fmdl_material_parameter_active = bpy.props.IntProperty(name = "FMDL_Material_Parameter_Name_List index", default = -1, options = {'SKIP_SAVE'})
	
	for c in classes:
		bpy.utils.register_class(c)
	
	bpy.types.INFO_MT_file_import.append(FMDL_Scene_FMDL_Import_MenuItem)
	bpy.types.INFO_MT_file_export.append(FMDL_Scene_FMDL_Export_MenuItem)
	bpy.types.TEXTURE_PT_image.append(FMDL_Texture_Load_Ftex_Button)
	
	bpy.app.handlers.scene_update_post.append(FMDL_Util_TrackChanges)

def unregister():
	bpy.app.handlers.scene_update_post.remove(FMDL_Util_TrackChanges)
	
	bpy.types.TEXTURE_PT_image.remove(FMDL_Texture_Load_Ftex_Button)
	bpy.types.INFO_MT_file_export.remove(FMDL_Scene_FMDL_Export_MenuItem)
	bpy.types.INFO_MT_file_import.remove(FMDL_Scene_FMDL_Import_MenuItem)
	
	for c in classes[::-1]:
		bpy.utils.unregister_class(c)
