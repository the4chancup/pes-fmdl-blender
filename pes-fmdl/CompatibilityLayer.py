import posixpath
from collections import defaultdict

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
	def setEmission(cls, blenderMaterial):
		pass

	@classmethod
	def findTexture(cls, texture, textureSearchPath):
		pass

	@classmethod
	def addTexture(cls, blenderMaterial, textureRole, texture, textureIDs, uvMapColor, uvMapNormals, textureSearchPath,
				   loadTextures):
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
	def findUvMapImage(cls, blenderMaterial, uvMapName, rolePrefix):
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
	def setEmission(cls, blenderMaterial):
		blenderMaterial.emit = 1.0
		blenderMaterial.alpha = 0.0
		blenderMaterial.use_transparency = True

	@classmethod
	def findTexture(cls, texture, textureSearchPath):
		textureFilename = texture.directory.replace('\\', '/').rstrip('/') + '/' + texture.filename.replace('\\',
																											'/').lstrip(
			'/')
		textureFilenameComponents = tuple(filter(None, textureFilename.split('/')))
		if len(textureFilenameComponents) == 0:
			return None
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
	def addTexture(cls, blenderMaterial, textureRole, texture, textureIDs, uvMapColor, uvMapNormals, textureSearchPath,
				   loadTextures):
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

			if loadTextures:
				filename = cls.findTexture(texture, textureSearchPath)
				if filename is None:
					blenderImage.filepath = texture.directory + texture.filename
				elif filename.lower().endswith('.ftex'):
					blenderImage.filepath = filename
					Ftex.blenderImageLoadFtex(blenderImage, bpy.app.tempdir, bpy.context.preferences.addons[__package__].preferences.texconv_path)
				else:
					blenderImage.filepath = filename
					blenderImage.reload()

			textureName = "[%s] %s" % (textureRole, texture.filename)
			blenderTexture = bpy.data.textures.new(textureName, type='IMAGE')
			blenderTexture.image = blenderImage
			blenderTexture.use_alpha = True

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
			blenderTextureSlot.use_map_alpha = True
			blenderTextureSlot.use = True
		else:
			blenderTextureSlot.use = False

		blenderTexture.fmdl_texture_filename = texture.filename
		blenderTexture.fmdl_texture_directory = texture.directory
		blenderTexture.fmdl_texture_role = textureRole

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
	def findUvMapImage(cls, blenderMaterial, uvMapName, rolePrefix):
		options = []
		for slot in blenderMaterial.texture_slots:
			if slot is None:
				continue
			if slot.uv_layer != uvMapName:
				continue
			if (
					slot.texture is not None
					and slot.texture.type == 'IMAGE'
					and slot.texture.image is not None
					and slot.texture.image.size[0] != 0
			):
				image = slot.texture.image
			else:
				image = None
			options.append((image, slot.texture.fmdl_texture_role))
		
		for (image, role) in options:
			if role.lower().startswith(rolePrefix.lower()):
				return image
		if len(options) > 0:
			return options[0][0]
		return None

	@classmethod
	def ExportUVMaps(cls, blenderMaterial, blenderMesh, name, vertexFields) -> (str, str):
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
		return uvLayerColor, uvLayerNormal

	@classmethod
	def TriangulateMesh(cls, modifiedBlenderMesh, scene):
		modifiedBlenderObject = bpy.data.objects.new('triangulation', modifiedBlenderMesh)
		modifiedBlenderObject.modifiers.new('triangulation', 'TRIANGULATE')
		newBlenderMesh = modifiedBlenderObject.to_mesh(scene, True, 'PREVIEW', calc_undeformed=True)
		bpy.data.objects.remove(modifiedBlenderObject)
		bpy.data.meshes.remove(modifiedBlenderMesh)
		return newBlenderMesh
	
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

	@classmethod
	def unlinkObjectFromScene(cls, objectID):
		bpy.data.objects[objectID].users_scene[0].objects.unlink(bpy.data.objects[objectID])

	def __init__(self):
		super().__init__()


class CompatibilityLayer29(CompatibilityLayerBase):

	@classmethod
	def findTexture(cls, texture, textureSearchPath):
		# Paths inside FMDL are POSIX, likely.
		textureDirectory = posixpath.normpath(texture.directory)
		textureFilename = posixpath.normpath(texture.filename)
		directory = textureDirectory.split(posixpath.sep)
		directorySuffixes = [directory[i:] for i in range(len(directory) + 1)]
		
		# Let's add some PES2020 logic
		# Face model for Messi is '/Assets/pes16/model/character/face/real/7511/#Win' but
		# it's real path is *without* the pes16 part
		# Also, when extracting an FPK, tools usually put it inside a "face_fpk" directory
		# So we have a base path like '7511/#Win/face_fpk' and textures are inside '7511/sourceimages/#windx11'
		# We add a relative path for that case.
		
		fixedDir = [name for name in directory if 'pes16' not in name]
		if fixedDir[-1] == 'sourceimages':
			fixedDir.append('#windx11')
		if fixedDir != directory:
			for i in range(len(fixedDir) + 1):
				directorySuffixes.insert(0, fixedDir[i:])

		filenames = []
		(fwo, ext) = posixpath.splitext(textureFilename)
		for extension in ['.ftex', '.tga', '.png', '.dds']:
			modifiedFilename = fwo + extension
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
	def setEmission(cls, blenderMaterial):
		pass

	@classmethod
	def addTexture(cls, blenderMaterial, textureRole, texture, textureIDs, uvMapColor, uvMapNormals, textureSearchPath,
				   loadTextures):
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
			if filename is None:
				blenderImage.filepath = texture.directory + texture.filename
			elif filename.lower().endswith('.ftex'):
				blenderImage.filepath = filename
				Ftex.blenderImageLoadFtex(blenderImage, bpy.app.tempdir, bpy.context.preferences.addons[__package__].preferences.texconv_path)
			else:
				blenderImage.filepath = filename
				blenderImage.reload()
			
			blenderMaterial.blend_method = 'BLEND'
			blenderMaterial.show_transparent_back = False
			
			blenderTexture = blenderMaterial.node_tree.nodes.new("ShaderNodeTexImage")
			blenderTexture.fmdl_texture_filename = blenderImage.filepath
			
			## HAAAAACCKKKK
			# texture.directory = texture.directory.replace('7511', '40425')
			blenderTexture.fmdl_texture_directory = texture.directory

			blenderTexture.fmdl_texture_role = textureRole
			blenderTexture.name = textureName
			blenderTexture.image = blenderImage
			principled = blenderMaterial.node_tree.nodes['Principled BSDF']
			
			blenderImage.alpha_mode = 'STRAIGHT'
			if blenderMaterial.fmdl_material_shader == 'pes_3ddf_skin_face':
				blenderImage.alpha_mode = 'NONE'
				
			print(f"Texture: {texture.directory} {textureName}")
				
			if 'Base_Tex_' in textureRole:
				blenderMaterial.node_tree.links.new(blenderTexture.outputs['Color'], principled.inputs['Base Color'])
				if blenderImage.alpha_mode != 'NONE':
					blenderMaterial.node_tree.links.new(blenderTexture.outputs['Alpha'], principled.inputs['Alpha'])
			elif 'NormalMap_Tex_' in textureRole:
				blenderMaterial.node_tree.links.new(blenderTexture.outputs['Color'], principled.inputs['Normal'])
			elif 'SpecularMap_Tex_' in textureRole:
				blenderMaterial.node_tree.links.new(blenderTexture.outputs['Color'], principled.inputs['Specular'])
			elif 'RoughnessMap_Tex_' in textureRole:
				blenderMaterial.node_tree.links.new(blenderTexture.outputs['Color'], principled.inputs['Roughness'])
			else:
				print(f"Unsupported texture role for '{textureName}': {textureRole}")
				for mp in blenderMaterial.fmdl_material_parameters:
					print(mp.name)
					for parm in mp.parameters:
						print(f"\t - {parm}")

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
		if blenderMaterial.node_tree is not None:
			for slot in blenderMaterial.node_tree.nodes:
				if slot is None or slot.type != "TEX_IMAGE":
					continue
				print(f"{blenderMaterial.name}: {slot.image.filepath}")
				yield slot
		else:
			print(f"Material {blenderMaterial.name} has no nodes")
			return None

	@classmethod
	def findUvMapImage(cls, blenderMaterial, uvMapName, rolePrefix):
		return None
	
	@classmethod
	def ExportUVMaps(cls, blenderMaterial, blenderMesh, name, vertexFields):
		colorUvMaps = defaultdict(int)
		normalUvMaps = defaultdict(int)
		for uv in blenderMesh.uv_layers:
			if uv.name == 'UVMap':
				colorUvMaps[uv.name] = 1
			else:
				normalUvMaps[uv.name] = 1
				
		
		if blenderMaterial.node_tree:
			for x in blenderMaterial.node_tree.nodes:
				if x.type == 'TEX_IMAGE':
					if 'fmdl_texture_role' in dir(x):
						if '_SRGB' in x.fmdl_texture_role:
							pass
						elif '_NRM' in x.fmdl_texture_role:
							pass
		# if len(colorUvMaps) == 0:
		# 	colorUvMaps = current_maps
		if len(normalUvMaps) == 0:
			normalUvMaps = colorUvMaps

		if len(colorUvMaps) == 0:
			raise FmdlExportError("Mesh '%s' does not have a primary UV map set." % name)
		if len(colorUvMaps) > 1:
			raise FmdlExportError(
				f"Mesh '{name}' has more than one primary UV maps: {colorUvMaps}")
		if len(normalUvMaps) == 0:
			raise FmdlExportError("Mesh '%s' does not have a normals UV map set." % name)
		if len(normalUvMaps) > 1:
			raise FmdlExportError(f"Mesh '{name}' has more than one normals UV map set: {normalUvMaps}")
		
		uvLayerColor = [*colorUvMaps][0]
		uvLayerNormal = [*normalUvMaps][0]
		vertexFields.uvCount = 1
		
		if uvLayerNormal == uvLayerColor:
			uvLayerNormal = None
		else:
			vertexFields.uvCount += 1
		return uvLayerColor, uvLayerNormal
	
	@classmethod
	def TriangulateMesh(cls, modifiedBlenderMesh, scene):
		blenderBmesh = bmesh.new()
		blenderBmesh.from_mesh(modifiedBlenderMesh, face_normals=False)
		# quad_method ['BEAUTY', 'FIXED', 'ALTERNATE', 'SHORT_EDGE'], default 'BEAUTY') – Undocumented.
		# ngon_method ['BEAUTY', 'EAR_CLIP'], default 'BEAUTY') – Undocumented.
		bmesh.ops.triangulate(blenderBmesh, faces=blenderBmesh.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
		blenderBmesh.to_mesh(modifiedBlenderMesh)
		blenderBmesh.free()
		return modifiedBlenderMesh

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

	@classmethod
	def unlinkObjectFromScene(cls, objectID):
		bpy.context.scene.objects.unlink(bpy.data.objects[objectID])

	@classmethod
	def setActiveObject(cls, blenderArmatureObject):
		bpy.context.view_layer.objects.active = blenderArmatureObject

	@classmethod
	def sceneUpdate(cls, context):
		context.view_layer.update()

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

	def findUvMapImage(self, blenderMaterial, uvMapName, rolePrefix):
		return self.shim.findUvMapImage(blenderMaterial, uvMapName, rolePrefix)
	
	def setEmission(self, blenderMaterial):
		return self.shim.setEmission(blenderMaterial)

	def addTexture(self, blenderMaterial, textureRole, texture, textureIDs, uvMapColor, uvMapNormals,
				   textureSearchPath, loadTextures):
		return self.shim.addTexture(blenderMaterial, textureRole, texture, textureIDs, uvMapColor, uvMapNormals,
									textureSearchPath, loadTextures)

	def linkObjectToScene(self, blenderObject):
		self.shim.linkObjectToScene(blenderObject)

	def GetColorFromVertex(self, vertex):
		return self.shim.GetColorFromVertex(vertex)

	def iterateTextureSlots(self, blenderMaterial):
		for slot in self.shim.iterateTextureSlots(blenderMaterial):
			yield slot

	def ExportUVMaps(self, blenderMaterial, blenderMesh, name, vertexFields):
		return self.shim.ExportUVMaps(blenderMaterial, blenderMesh, name, vertexFields)

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

	def unlinkObjectFromScene(self, objectID):
		self.shim.unlinkObjectFromScene(objectID)
	
	def setActiveObject(self, blenderArmatureObject):
		self.shim.setActiveObject(blenderArmatureObject)
	
	def sceneUpdate(self, c):
		self.shim.sceneUpdate(c)
