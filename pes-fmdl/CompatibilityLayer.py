import bpy
import os
import bmesh
import re
from . import Ftex


class FmdlExportError(Exception):
	def __init__(self, errors):
		if isinstance(errors, list):
			self.errors = errors
		else:
			self.errors = [errors]


class CompatibilityLayerBase(object):
	@classmethod
	def setEmission(cls, blenderMaterial, value):
		pass

	@classmethod
	def findTexture(cls, texture, textureSearchPath):
		pass

	@classmethod
	def addTexture(cls, blenderMaterial, textureRole, texture, textureIDs, uvMapColor, uvMapNormals, textureSearchPath):
		pass

	@classmethod
	def linkObjectToScene(cls, blenderArmatureObject):
		pass

	@classmethod
	def GetColorFromVertex(cls, vertex):
		pass

	@classmethod
	def iterateTextureSlots(cls, blenderMaterial):
		pass

	@classmethod
	def ExportUVMaps(cls, blenderMaterial, blenderMesh, name, vertexFields):
		pass

	@classmethod
	def TriangulateMesh(cls, modifiedBlenderMesh, scene):
		pass
	
	@classmethod
	def AppendToImportMenu(cls, newMenuItem):
		pass
	
	@classmethod
	def AppendToExportMenu(cls, newMenuItem):
		pass
		
	@classmethod
	def AppendScenePostUpdateEvent(cls, event):
		pass

	@classmethod
	def RemoveSceneUpdatePostEvent(cls, eventHandler):
		pass
	
	def __init__(self):
		pass


class CompatibilityLayer27(CompatibilityLayerBase):
	@classmethod
	def setEmission(cls, blenderMaterial, value):
		blenderMaterial.emit = value

	@classmethod
	def findTexture(cls, texture, textureSearchPath):
		textureFilename = texture.directory.replace('\\', '/').rstrip('/') + '/' + texture.filename.replace('\\',
																											'/').lstrip(
			'/')
		textureFilenameComponents = tuple(filter(None, textureFilename.split('/')))
		filename = textureFilenameComponents[-1]
		directory = textureFilenameComponents[:-1]
		directorySuffixes = [directory[i:] for i in range(len(directory) + 1)]

		if filename == 'kit.dds':
			filenames = []
		else:
			filenames = [filename]
			position = filename.rfind('.')
			if position >= 0:
				for extension in ['dds', 'tga', 'ftex']:
					modifiedFilename = filename[:position + 1] + extension
					if modifiedFilename not in filenames:
						filenames.append(modifiedFilename)

		for searchDirectory in textureSearchPath:
			for suffix in directorySuffixes:
				for filename in filenames:
					fullFilename = os.path.join(searchDirectory, *suffix, filename)
					if os.path.isfile(fullFilename):
						return fullFilename

				if len(filenames) == 0:
					directory = os.path.join(searchDirectory, *suffix)
					if not os.path.isdir(directory):
						continue

					try:
						entries = os.listdir(directory)
					except:
						continue
					for entry in entries:
						if re.match('^u[0-9]{4}p1\.dds$', entry, flags=re.IGNORECASE):
							fullFilename = os.path.join(directory, entry)
							if os.path.isfile(fullFilename):
								return fullFilename

		return None

	@classmethod
	def addTexture(cls, blenderMaterial, textureRole, texture, textureIDs, uvMapColor, uvMapNormals, textureSearchPath):
		identifier = (textureRole, texture)
		if identifier in textureIDs:
			blenderTexture = bpy.data.textures[textureIDs[identifier]]
		else:
			blenderImage = bpy.data.images.new(texture.filename, width=0, height=0)
			blenderImage.source = 'FILE'

			if '_SRGB' in textureRole:
				blenderImage.colorspace_settings.name = 'sRGB'
			elif '_LIN' in textureRole:
				blenderImage.colorspace_settings.name = 'Linear'
			else:
				blenderImage.colorspace_settings.name = 'Non-Color'

			filename = cls.findTexture(texture, textureSearchPath)
			hasAlpha = True
			if filename == None:
				blenderImage.filepath = texture.directory + texture.filename
			elif filename.lower().endswith('.ftex'):
				blenderImage.filepath = filename
				Ftex.blenderImageLoadFtex(blenderImage, bpy.app.tempdir)
				# Many (all?) ftex files in PES have nonsensical alpha data.
				hasAlpha = False
			else:
				blenderImage.filepath = filename
				blenderImage.reload()

			textureName = "[%s] %s" % (textureRole, texture.filename)
			blenderTexture = bpy.data.textures.new(textureName, type='IMAGE')
			blenderTexture.image = blenderImage
			blenderTexture.use_alpha = hasAlpha

			if '_NRM' in textureRole:
				blenderTexture.use_normal_map = True

			textureIDs[identifier] = blenderTexture.name

		blenderTextureSlot = blenderMaterial.texture_slots.add()
		blenderTextureSlot.texture = blenderTexture
		blenderTextureSlot.texture_coords = 'UV'
		if '_NRM' in textureRole:
			blenderTextureSlot.uv_layer = uvMapNormals
		else:
			blenderTextureSlot.uv_layer = uvMapColor

		if textureRole == 'Base_Tex_SRGB' or textureRole == 'Base_Tex_LIN':
			blenderTextureSlot.use_map_diffuse = True
			blenderTextureSlot.use_map_color_diffuse = True
			blenderTextureSlot.use = True
		else:
			blenderTextureSlot.use = False

	@classmethod
	def linkObjectToScene(cls, blenderArmatureObject):
		bpy.context.scene.objects.link(blenderArmatureObject)

	@classmethod
	def GetColorFromVertex(cls, vertex):
		return vertex.color[0:3]

	@classmethod
	def iterateTextureSlots(cls, blenderMaterial):
		for slot in blenderMaterial.texture_slots:
			if slot is None:
				continue
			yield slot.texture

	@classmethod
	def ExportUVMaps(cls, blenderMaterial, blenderMesh, name, vertexFields):
		allUvMaps = []
		colorUvMaps = []
		normalUvMaps = []
		for slot in blenderMaterial.texture_slots:
			if slot == None:
				continue
			uvLayerName = slot.uv_layer
			if uvLayerName not in blenderMesh.uv_layers:
				continue
			if '_NRM' in slot.texture.fmdl_texture_role:
				uvMaps = normalUvMaps
			else:
				uvMaps = colorUvMaps
			if uvLayerName not in allUvMaps:
				allUvMaps.append(uvLayerName)
			if uvLayerName not in uvMaps:
				uvMaps.append(uvLayerName)
		if len(allUvMaps) == 1:
			if len(colorUvMaps) == 0:
				colorUvMaps.append(allUvMaps[0])
			if len(normalUvMaps) == 0:
				normalUvMaps.append(allUvMaps[0])
		elif len(allUvMaps) == 2:
			if len(colorUvMaps) == 1 and len(normalUvMaps) == 2:
				if allUvMaps[0] == colorUvMaps[0]:
					normalUvMaps = [allUvMaps[1]]
				else:
					normalUvMaps = [allUvMaps[0]]
			elif len(colorUvMaps) == 2 and len(normalUvMaps) == 1:
				if allUvMaps[0] == normalUvMaps[0]:
					colorUvMaps = [allUvMaps[1]]
				else:
					colorUvMaps = [allUvMaps[0]]

		if len(colorUvMaps) == 0:
			raise FmdlExportError("Mesh '%s' does not have a primary UV map set." % name)
		if len(colorUvMaps) > 1:
			raise FmdlExportError(
				"Mesh '%s' has conflicting primary UV maps '%s' and '%s' set." % (name, colorUvMaps[0], colorUvMaps[1]))
		if len(normalUvMaps) == 0:
			raise FmdlExportError("Mesh '%s' does not have a normals UV map set." % name)
		if len(normalUvMaps) > 1:
			raise FmdlExportError("Mesh '%s' has conflicting normals UV maps '%s' and '%s' set." % (
				name, normalUvMaps[0], normalUvMaps[1]))

		uvLayerColor = colorUvMaps[0]
		vertexFields.uvCount = 1

		if normalUvMaps[0] == uvLayerColor:
			uvLayerNormal = None
		else:
			uvLayerNormal = normalUvMaps[0]
			vertexFields.uvCount += 1

	@classmethod
	def TriangulateMesh(cls, modifiedBlenderMesh, scene):
		modifiedBlenderObject = bpy.data.objects.new('triangulation', modifiedBlenderMesh)
		modifiedBlenderObject.modifiers.new('triangulation', 'TRIANGULATE')
		newBlenderMesh = modifiedBlenderObject.to_mesh(scene, True, 'PREVIEW', calc_undeformed=True)
		bpy.data.objects.remove(modifiedBlenderObject)
		bpy.data.meshes.remove(modifiedBlenderMesh)
		modifiedBlenderMesh = newBlenderMesh
	
	@classmethod
	def AppendToImportMenu(cls, newMenuItem):
		bpy.types.INFO_MT_file_import.append(newMenuItem)
	
	@classmethod
	def AppendToExportMenu(cls, newMenuItem):
		bpy.types.INFO_MT_file_export.append(newMenuItem)
	
	@classmethod
	def AppendScenePostUpdateEvent(cls, eventHandler):
		bpy.app.handlers.scene_update_post.append(eventHandler)
		
	@classmethod
	def RemoveSceneUpdatePostEvent(cls, eventHandler):
		bpy.app.handlers.scene_update_post.remove(eventHandler)

	@classmethod
	def RemoveFromExportMenu(cls, menuItem):
		bpy.types.INFO_MT_file_export.remove(menuItem)

	@classmethod
	def RemoveFromImportMenu(cls, menuItem):
		bpy.types.INFO_MT_file_import.remove(menuItem)
	
	def __init__(self):
		super().__init__()


class CompatibilityLayer29(CompatibilityLayerBase):

	@classmethod
	def findTexture(cls, texture, textureSearchPath):
		textureFilename = texture.directory.replace('\\', '/').rstrip('/') + '/' + texture.filename.replace('\\',
																											'/').lstrip(
			'/')
		textureFilenameComponents = tuple(filter(None, textureFilename.split('/')))
		filename = textureFilenameComponents[-1]
		directory = textureFilenameComponents[:-1]
		directorySuffixes = [directory[i:] for i in range(len(directory) + 1)]

		if filename == 'kit.dds':
			filenames = []
		else:
			filenames = [filename]
			position = filename.rfind('.')
			if position >= 0:
				for extension in ['dds', 'tga', 'ftex']:
					modifiedFilename = filename[:position + 1] + extension
					if modifiedFilename not in filenames:
						filenames.append(modifiedFilename)

		for searchDirectory in textureSearchPath:
			for suffix in directorySuffixes:
				for filename in filenames:
					fullFilename = os.path.join(searchDirectory, *suffix, filename)
					if os.path.isfile(fullFilename):
						return fullFilename

				if len(filenames) == 0:
					directory = os.path.join(searchDirectory, *suffix)
					if not os.path.isdir(directory):
						continue

					try:
						entries = os.listdir(directory)
					except:
						continue
					for entry in entries:
						if re.match(r'^u[0-9]{4}p1\.dds$', entry, flags=re.IGNORECASE):
							fullFilename = os.path.join(directory, entry)
							if os.path.isfile(fullFilename):
								return fullFilename

		return None

	@classmethod
	def setEmission(cls, blenderMaterial, value):
		pass

	@classmethod
	def addTexture(cls, blenderMaterial, textureRole, texture, textureIDs, uvMapColor, uvMapNormals, textureSearchPath):
		blenderMaterial.use_nodes = True
		identifier = (textureRole, texture)
		textureName = "[%s] %s" % (textureRole, texture.filename)
		if identifier in textureIDs:
			blenderTexture = blenderMaterial.node_tree.get(textureIDs[identifier])
		else:
			blenderImage = bpy.data.images.new(texture.filename, width=0, height=0)
			blenderImage.source = 'FILE'

			if '_SRGB' in textureRole:
				blenderImage.colorspace_settings.name = 'sRGB'
			elif '_LIN' in textureRole:
				blenderImage.colorspace_settings.name = 'Linear'
			else:
				blenderImage.colorspace_settings.name = 'Non-Color'

			filename = cls.findTexture(texture, textureSearchPath)
			hasAlpha = True
			if filename is None:
				blenderImage.filepath = texture.directory + texture.filename
			elif filename.lower().endswith('.ftex'):
				blenderImage.filepath = filename
				Ftex.blenderImageLoadFtex(blenderImage, bpy.app.tempdir)
				# Many (all?) ftex files in PES have nonsensical alpha data.
				hasAlpha = False
			else:
				blenderImage.filepath = filename
				blenderImage.reload()

			blenderTexture = blenderMaterial.node_tree.nodes.new("ShaderNodeTexImage")
			blenderTexture.fmdl_texture_filename = blenderImage.filepath
			blenderTexture.fmdl_texture_directory = texture.directory
			blenderTexture.fmdl_texture_role = textureRole
			blenderTexture.name = textureName
			blenderTexture.image = blenderImage
			principled = blenderMaterial.node_tree.nodes['Principled BSDF']
			if '_SRGB' in textureRole:
				blenderMaterial.node_tree.links.new(blenderTexture.outputs['Color'], principled.inputs['Base Color'])
				if hasAlpha:
					blenderImage.alpha_mode = 'STRAIGHT'
					blenderMaterial.blend_method = 'BLEND'
					blenderMaterial.node_tree.links.new(blenderTexture.outputs['Alpha'], principled.inputs['Alpha'])
			else:
				blenderImage.alpha_mode = 'NONE'
				if '_NRM' in textureRole:
					blenderMaterial.node_tree.links.new(blenderTexture.outputs['Color'], principled.inputs['Normal'])

			textureIDs[identifier] = blenderTexture.name
		return blenderTexture

	@classmethod
	def linkObjectToScene(cls, blenderArmatureObject):
		bpy.data.scenes[0].collection.objects.link(blenderArmatureObject)

	@classmethod
	def GetColorFromVertex(cls, vertex):
		return vertex.color[0:4]

	@classmethod
	def iterateTextureSlots(cls, blenderMaterial):
		for slot in blenderMaterial.node_tree.nodes:
			if slot is None or slot.type != "TEX_IMAGE":
				continue
			yield slot

	@classmethod
	def ExportUVMaps(cls, blenderMaterial, blenderMesh, name, vertexFields):
		pass

	@classmethod
	def TriangulateMesh(cls, modifiedBlenderMesh, scene):
		blenderBmesh = bmesh.new()
		blenderBmesh.from_mesh(modifiedBlenderMesh, face_normals=False)
		# quad_method ['BEAUTY', 'FIXED', 'ALTERNATE', 'SHORT_EDGE'], default 'BEAUTY') – Undocumented.
		#               ngon_method ['BEAUTY', 'EAR_CLIP'], default 'BEAUTY') – Undocumented.
		bmesh.ops.triangulate(blenderBmesh, faces=blenderBmesh.faces[:], quad_method='BEAUTY',
							  ngon_method='BEAUTY')
		blenderBmesh.to_mesh(modifiedBlenderMesh)
		blenderBmesh.free()

	@classmethod
	def AppendToImportMenu(cls, newMenuItem):
		bpy.types.TOPBAR_MT_file_import.append(newMenuItem)
	
	@classmethod
	def AppendToExportMenu(cls, newMenuItem):
		bpy.types.TOPBAR_MT_file_export.append(newMenuItem)
	
	@classmethod
	def AppendSceneUpdatePostEvent(cls, eventHandler):
		bpy.app.handlers.depsgraph_update_post.append(eventHandler)
	
	@classmethod
	def RemoveSceneUpdatePostEvent(cls, eventHandler):
		bpy.app.handlers.depsgraph_update_post.remove(eventHandler)

	@classmethod
	def RemoveFromExportMenu(cls, menuItem):
		bpy.types.TOPBAR_MT_file_export.remove(menuItem)

	@classmethod
	def RemoveFromImportMenu(cls, menuItem):
		bpy.types.TOPBAR_MT_file_import.remove(menuItem)

	def __init__(self):
		super().__init__()


class CompatibilityLayer:
	shim = None

	def __init__(self):
		(major, minor, build) = bpy.app.version
		if minor < 80:
			self.shim = CompatibilityLayer27()
		else:
			self.shim = CompatibilityLayer29()

	def findTexture(self, texture, textureSearchPath):
		return self.shim.findTexture(texture, textureSearchPath)

	def setEmission(self, blenderMaterial, value):
		return self.shim.setEmission(blenderMaterial, value)

	def addTexture(self, blenderMaterial, textureRole, texture, textureIDs, uvMapColor, uvMapNormals,
				   textureSearchPath):
		return self.shim.addTexture(blenderMaterial, textureRole, texture, textureIDs, uvMapColor, uvMapNormals,
									textureSearchPath)

	def linkObjectToScene(self, blenderObject):
		self.shim.linkObjectToScene(blenderObject)

	def GetColorFromVertex(self, vertex):
		return self.shim.GetColorFromVertex(vertex)

	def iterateTextureSlots(self, blenderMaterial):
		for slot in self.shim.iterateTextureSlots(blenderMaterial):
			yield slot

	def ExportUVMaps(self, blenderMaterial, blenderMesh, name, vertexFields):
		self.shim.ExportUVMaps(blenderMaterial, blenderMesh, name, vertexFields)

	def TriangulateMesh(self, modifiedBlenderMesh, scene):
		self.shim.TriangulateMesh(modifiedBlenderMesh, scene)
	
	def AppendToImportMenu(self, newMenuItem):
		self.shim.AppendToImportMenu(newMenuItem)
	
	def AppendToExportMenu(self, newMenuItem):
		self.shim.AppendToExportMenu(newMenuItem)
	
	def AppendSceneUpdatePostEvent(self, eventHandler):
		self.shim.AppendSceneUpdatePostEvent(eventHandler)
		
	def RemoveSceneUpdatePostEvent(self, eventHandler):
		self.shim.RemoveSceneUpdatePostEvent(eventHandler)
	
	def RemoveFromExportMenu(self, menuItem):
		self.shim.RemoveFromExportMenu(menuItem)
	
	def RemoveFromImportMenu(self, menuItem):
		self.shim.RemoveFromImportMenu(menuItem)
