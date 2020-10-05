import bpy
import mathutils
import itertools
import os
import os.path
import re

from . import FmdlFile, FmdlMeshSplitting, FmdlSplitVertexEncoding, Ftex, PesSkeletonData


class UnsupportedFmdl(Exception):
	pass

class FmdlExportError(Exception):
	def __init__(self, errors):
		if isinstance(errors, list):
			self.errors = errors
		else:
			self.errors = [errors]

class ImportSettings:
	def __init__(self):
		self.enableExtensions = True
		self.enableVertexLoopPreservation = True
		self.enableMeshSplitting = True
		self.enableLoadTextures = True
		self.enableImportAllBoundingBoxes = False

class ExportSettings:
	def __init__(self):
		self.enableExtensions = True
		self.enableVertexLoopPreservation = True
		self.enableMeshSplitting = True



def createBoundingBox(context, meshObject, min, max):
	name = "Bounding box for %s" % meshObject.data.name
	objectID = meshObject.name
	
	blenderLattice = bpy.data.lattices.new(name)
	blenderLattice.points_u = 2
	blenderLattice.points_v = 2
	blenderLattice.points_w = 2
	# The default constructed (2,2,2)-lattice has a size of 1x1x1 centered around the origin.
	# Scale and translate this to the desired coordinates using a transformation matrix.
	# This translation matrix has a scaling factors on the diagonal, and translation offsets
	# on the bottom row, applied _after_ scaling.
	matrix = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 1]]
	for i in range(3):
		size = max[i] - min[i]
		if size < 0.000001:
			size = 0.000001
		matrix[i][i] = size
		basePosition = -size / 2
		matrix[3][i] = min[i] - basePosition
	blenderLattice.transform(matrix)
	
	blenderLatticeObject = bpy.data.objects.new(name, blenderLattice)
	blenderLatticeObject.parent = bpy.data.objects[objectID]
	context.scene.objects.link(blenderLatticeObject)
	context.scene.update()

def createFittingBoundingBox(context, meshObject):
	transformedMesh = meshObject.data.copy()
	transformedMesh.transform(meshObject.matrix_world)
	transformedMeshObject = bpy.data.objects.new('measurement', transformedMesh)
	boundingBox = transformedMeshObject.bound_box
	minCoordinates = tuple(min([boundingBox[j][i] for j in range(8)]) for i in range(3))
	maxCoordinates = tuple(max([boundingBox[j][i] for j in range(8)]) for i in range(3))
	bpy.data.objects.remove(transformedMeshObject)
	bpy.data.meshes.remove(transformedMesh)
	
	createBoundingBox(context, meshObject, minCoordinates, maxCoordinates)

def importFmdl(context, fmdl, filename, importSettings = None):
	UV_MAP_COLOR = 'UVMap'
	UV_MAP_NORMALS = 'normal_map'
	
	def findTexture(texture, textureSearchPath):
		textureFilename = texture.directory.replace('\\', '/').rstrip('/') + '/' + texture.filename.replace('\\', '/').lstrip('/')
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
						if re.match('^u[0-9]{4}p1\.dds$', entry, flags = re.IGNORECASE):
							fullFilename = os.path.join(directory, entry)
							if os.path.isfile(fullFilename):
								return fullFilename
		
		return None
	
	def addTexture(blenderMaterial, textureRole, texture, textureIDs, uvMapColor, uvMapNormals, textureSearchPath, loadTextures):
		identifier = (textureRole, texture)
		if identifier in textureIDs:
			blenderTexture = bpy.data.textures[textureIDs[identifier]]
		else:
			blenderImage = bpy.data.images.new(texture.filename, width = 0, height = 0)
			blenderImage.source = 'FILE'
			
			if '_SRGB' in textureRole:
				blenderImage.colorspace_settings.name = 'sRGB'
			elif '_LIN' in textureRole:
				blenderImage.colorspace_settings.name = 'Linear'
			else:
				blenderImage.colorspace_settings.name = 'Non-Color'
			
			if loadTextures:
				filename = findTexture(texture, textureSearchPath)
				if filename == None:
					blenderImage.filepath = texture.directory + texture.filename
				elif filename.lower().endswith('.ftex'):
					blenderImage.filepath = filename
					Ftex.blenderImageLoadFtex(blenderImage, bpy.app.tempdir)
				else:
					blenderImage.filepath = filename
					blenderImage.reload()
			
			textureName = "[%s] %s" % (textureRole, texture.filename)
			blenderTexture = bpy.data.textures.new(textureName, type = 'IMAGE')
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
	
	def materialHasSeparateUVMaps(materialInstance, fmdl):
		for mesh in fmdl.meshes:
			if mesh.materialInstance == materialInstance:
				if mesh.vertexFields.uvCount >= 1 and 1 not in mesh.vertexFields.uvEqualities[0]:
					return True
		return False
	
	def importMaterials(fmdl, textureSearchPath, loadTextures):
		materialIDs = {}
		textureIDs = {}
		
		for materialInstance in fmdl.materialInstances:
			blenderMaterial = bpy.data.materials.new(materialInstance.name)
			materialIDs[materialInstance] = blenderMaterial.name
			
			blenderMaterial.fmdl_material_shader = materialInstance.shader
			blenderMaterial.fmdl_material_technique = materialInstance.technique
			
			for (name, values) in materialInstance.parameters:
				blenderMaterialParameter = blenderMaterial.fmdl_material_parameters.add()
				blenderMaterialParameter.name = name
				blenderMaterialParameter.parameters = [v for v in values]
			
			uvMapColor = UV_MAP_COLOR
			if materialHasSeparateUVMaps(materialInstance, fmdl):
				uvMapNormals = UV_MAP_NORMALS
			else:
				uvMapNormals = UV_MAP_COLOR
			
			blenderMaterial.emit = 1.0
			blenderMaterial.alpha = 0.0
			blenderMaterial.use_transparency = True
			
			for (role, texture) in materialInstance.textures:
				addTexture(blenderMaterial, role, texture, textureIDs, uvMapColor, uvMapNormals, textureSearchPath, loadTextures)
		
		return materialIDs
	
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
	
	def importSkeleton(context, fmdl):
		blenderArmature = bpy.data.armatures.new("Skeleton")
		blenderArmature.show_names = True
		
		blenderArmatureObject = bpy.data.objects.new("Skeleton", blenderArmature)
		armatureObjectID = blenderArmatureObject.name
		
		context.scene.objects.link(blenderArmatureObject)
		context.scene.objects.active = blenderArmatureObject
		
		bpy.ops.object.mode_set(context.copy(), mode = 'EDIT')
		
		bonesByName = {}
		for bone in fmdl.bones:
			bonesByName[bone.name] = bone
		
		boneIDs = {}
		for bone in fmdl.bones:
			addBone(blenderArmature, bone, boneIDs, bonesByName)
		
		bpy.ops.object.mode_set(context.copy(), mode = 'OBJECT')
		
		return (armatureObjectID, boneIDs)
	
	def addSkeletonMeshModifier(blenderMeshObject, boneGroup, armatureObjectID, boneIDs):
		blenderArmatureObject = bpy.data.objects[armatureObjectID]
		blenderArmature = blenderArmatureObject.data
		
		blenderModifier = blenderMeshObject.modifiers.new("fmdl skeleton", type = 'ARMATURE')
		blenderModifier.object = blenderArmatureObject
		blenderModifier.use_vertex_groups = True
		
		vertexGroupIDs = {}
		for bone in boneGroup.bones:
			blenderBone = blenderArmature.bones[boneIDs[bone]]
			blenderVertexGroup = blenderMeshObject.vertex_groups.new(blenderBone.name)
			vertexGroupIDs[bone] = blenderVertexGroup.name
		return vertexGroupIDs
	
	def findUvMapImage(blenderMaterial, uvMapName, rolePrefix):
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
	
	def importMesh(mesh, name, fmdl, materialIDs, armatureObjectID, boneIDs):
		blenderMesh = bpy.data.meshes.new(name)
		
		#
		# mesh.vertices does not correspond either to the blenderMesh.vertices
		# nor the blenderMesh.loops, but rather the unique values of blenderMesh.loops.
		# The blenderMesh.vertices correspond to the unique vertex.position values in mesh.vertices.
		#
		
		vertexIndices = {}
		vertexVertices = []
		for vertex in mesh.vertices:
			if vertex.position not in vertexIndices:
				vertexIndices[vertex.position] = len(vertexIndices)
				vertexVertices.append(vertex)
		loopVertices = list(itertools.chain.from_iterable([reversed(face.vertices) for face in mesh.faces]))
		
		blenderMesh.vertices.add(len(vertexVertices))
		blenderMesh.vertices.foreach_set("co", tuple(itertools.chain.from_iterable([
			(vertex.position.x, -vertex.position.z, vertex.position.y) for vertex in vertexVertices
		])))
		
		blenderMesh.loops.add(len(mesh.faces) * 3)
		blenderMesh.loops.foreach_set("vertex_index", tuple([vertexIndices[vertex.position] for vertex in loopVertices]))
		
		blenderMesh.polygons.add(len(mesh.faces))
		blenderMesh.polygons.foreach_set("loop_start", tuple(range(0, 3 * len(mesh.faces), 3)))
		blenderMesh.polygons.foreach_set("loop_total", [3 for face in mesh.faces])
		
		blenderMesh.update(calc_edges = True)
		
		blenderMaterial = bpy.data.materials[materialIDs[mesh.materialInstance]]
		
		if mesh.vertexFields.hasNormal:
			def normalize(vector):
				(x, y, z) = vector
				size = (x ** 2 + y ** 2 + z ** 2) ** 0.5
				if size < 0.01:
					return (x, y, z)
				return (x / size, y / size, z / size)
			blenderMesh.normals_split_custom_set([
				normalize((vertex.normal.x, -vertex.normal.z, vertex.normal.y)) for vertex in loopVertices
			])
			blenderMesh.use_auto_smooth = True
		
		if mesh.vertexFields.hasColor:
			colorLayer = blenderMesh.vertex_colors.new()
			colorLayer.data.foreach_set("color", tuple(itertools.chain.from_iterable([
				vertex.color[0:3] for vertex in loopVertices
			])))
			colorLayer.active = True
			colorLayer.active_render = True
		
		if mesh.vertexFields.uvCount >= 1:
			uvTexture = blenderMesh.uv_textures.new(name = UV_MAP_COLOR)
			uvLayer = blenderMesh.uv_layers[uvTexture.name]
			
			uvLayer.data.foreach_set("uv", tuple(itertools.chain.from_iterable([
				(vertex.uv[0].u, 1.0 - vertex.uv[0].v) for vertex in loopVertices
			])))
			uvTexture.active = True
			uvTexture.active_clone = True
			uvTexture.active_render = True
			
			image = findUvMapImage(blenderMaterial, UV_MAP_COLOR, 'Base_Tex_')
			if image is not None:
				for i in range(len(uvTexture.data)):
					uvTexture.data[i].image = image
		
		if mesh.vertexFields.uvCount >= 2 and 0 not in mesh.vertexFields.uvEqualities[1]:
			uvTexture = blenderMesh.uv_textures.new(name = UV_MAP_NORMALS)
			uvLayer = blenderMesh.uv_layers[uvTexture.name]
			
			uvLayer.data.foreach_set("uv", tuple(itertools.chain.from_iterable([
				(vertex.uv[1].u, 1.0 - vertex.uv[1].v) for vertex in loopVertices
			])))
			
			image = findUvMapImage(blenderMaterial, UV_MAP_NORMALS, 'NormalMap_Tex_')
			if image is not None:
				for i in range(len(uvTexture.data)):
					uvTexture.data[i].image = image
		
		if mesh.vertexFields.uvCount >= 3:
			raise UnsupportedFmdl("No support for fmdl files with more than 2 UV maps")
		
		blenderMesh.materials.append(blenderMaterial)
		
		blenderMesh.fmdl_alpha_enum = mesh.alphaEnum
		blenderMesh.fmdl_shadow_enum = mesh.shadowEnum
		
		blenderMeshObject = bpy.data.objects.new(blenderMesh.name, blenderMesh)
		meshObjectID = blenderMeshObject.name
		context.scene.objects.link(blenderMeshObject)
		
		if mesh.vertexFields.hasBoneMapping:
			vertexGroupIDs = addSkeletonMeshModifier(blenderMeshObject, mesh.boneGroup, armatureObjectID, boneIDs)
			for i in range(len(vertexVertices)):
				for bone in vertexVertices[i].boneMapping:
					weight = vertexVertices[i].boneMapping[bone]
					blenderMeshObject.vertex_groups[vertexGroupIDs[bone]].add((i, ), weight, 'REPLACE')
		
		return meshObjectID
	
	def importMeshes(context, fmdl, materialIDs, armatureObjectID, boneIDs):
		meshNames = {}
		for meshGroup in fmdl.meshGroups:
			if len(meshGroup.meshes) == 1 and meshGroup.name != "":
				meshNames[meshGroup.meshes[0]] = meshGroup.name
		nextIndex = 0
		for mesh in fmdl.meshes:
			if mesh not in meshNames:
				meshNames[mesh] = "mesh_id %s" % nextIndex
				nextIndex += 1
		
		meshObjectIDs = {}
		for mesh in fmdl.meshes:
			meshObjectIDs[mesh] = importMesh(mesh, meshNames[mesh], fmdl, materialIDs, armatureObjectID, boneIDs)
		
		return meshObjectIDs
	
	def addMeshGroup(context, meshGroup, meshObjectIDs, importBoundingBoxMode):
		if len(meshGroup.meshes) == 0 and len(meshGroup.children) == 1 and meshGroup.name == "":
			return addMeshGroup(context, meshGroup.children[0], meshObjectIDs, importBoundingBoxMode)
		
		if len(meshGroup.meshes) == 1:
			blenderMeshGroupObject = bpy.data.objects[meshObjectIDs[meshGroup.meshes[0]]]
		else:
			blenderMeshGroupObject = bpy.data.objects.new(meshGroup.name, None)
			context.scene.objects.link(blenderMeshGroupObject)
			
			for mesh in meshGroup.meshes:
				bpy.data.objects[meshObjectIDs[mesh]].parent = blenderMeshGroupObject
		
		for mesh in meshGroup.meshes:
			if (
				   importBoundingBoxMode == 'ALL'
				or (importBoundingBoxMode == 'CUSTOM' and 'custom-bounding-box-meshes' in mesh.extensionHeaders)
			):
				minCoordinates = (
					meshGroup.boundingBox.min.x,
					-meshGroup.boundingBox.max.z,
					meshGroup.boundingBox.min.y,
				)
				maxCoordinates = (
					meshGroup.boundingBox.max.x,
					-meshGroup.boundingBox.min.z,
					meshGroup.boundingBox.max.y,
				)
				createBoundingBox(context, bpy.data.objects[meshObjectIDs[mesh]], minCoordinates, maxCoordinates)
		
		meshGroupID = blenderMeshGroupObject.name
		for child in meshGroup.children:
			childID = addMeshGroup(context, child, meshObjectIDs, importBoundingBoxMode)
			bpy.data.objects[childID].parent = bpy.data.objects[meshGroupID]
		
		return meshGroupID
	
	def importMeshTree(context, fmdl, meshObjectIDs, armatureObjectID, filename, importBoundingBoxMode):
		rootMeshGroups = []
		for meshGroup in fmdl.meshGroups:
			if meshGroup.parent == None:
				rootMeshGroups.append(meshGroup)
		
		dirname = os.path.basename(os.path.dirname(filename))
		basename = os.path.basename(filename)
		position = basename.rfind('.')
		if position == -1:
			name = os.path.join(dirname, basename)
		else:
			name = os.path.join(dirname, basename[:position])
		
		rootMeshGroup = FmdlFile.FmdlFile.MeshGroup()
		rootMeshGroup.name = name
		rootMeshGroup.parent = None
		rootMeshGroup.children = rootMeshGroups
		rootMeshGroup.meshes = []
		
		blenderMeshGroupID = addMeshGroup(context, rootMeshGroup, meshObjectIDs, importBoundingBoxMode)
		
		if armatureObjectID != None:
			bpy.data.objects[armatureObjectID].parent = bpy.data.objects[blenderMeshGroupID]
		
		bpy.data.objects[blenderMeshGroupID].fmdl_file = True
		bpy.data.objects[blenderMeshGroupID].fmdl_filename = filename
		
		return blenderMeshGroupID
	
	
	
	if importSettings == None:
		importSettings = ImportSettings()
	
	if context.active_object == None:
		activeObjectID = None
	else:
		activeObjectID = bpy.data.objects.find(context.active_object.name)
	if context.mode != 'OBJECT':
		bpy.ops.object.mode_set(context.copy(), mode = 'OBJECT')
	
	
	
	if importSettings.enableExtensions and importSettings.enableMeshSplitting:
		fmdl = FmdlMeshSplitting.decodeFmdlSplitMeshes(fmdl)
	if importSettings.enableExtensions and importSettings.enableVertexLoopPreservation:
		fmdl = FmdlSplitVertexEncoding.decodeFmdlVertexLoopPreservation(fmdl)
	
	if importSettings.enableImportAllBoundingBoxes:
		importBoundingBoxMode = 'ALL'
	elif importSettings.enableExtensions:
		importBoundingBoxMode = 'CUSTOM'
	else:
		importBoundingBoxMode = 'NONE'
	
	baseDir = os.path.dirname(filename)
	textureSearchPath = []
	for directory in [
		baseDir,
		os.path.dirname(baseDir),
		os.path.dirname(os.path.dirname(baseDir)),
		os.path.join(baseDir, 'Common'),
		os.path.join(os.path.dirname(baseDir), 'Common'),
		os.path.join(os.path.dirname(os.path.dirname(baseDir)), 'Common'),
		os.path.join(baseDir, 'Kit Textures'),
		os.path.join(os.path.dirname(baseDir), 'Kit Textures'),
		os.path.join(os.path.dirname(os.path.dirname(baseDir)), 'Kit Textures'),
	]:
		if os.path.isdir(directory):
			textureSearchPath.append(directory)
	materialIDs = importMaterials(fmdl, textureSearchPath, importSettings.enableLoadTextures)
	
	if len(fmdl.bones) > 0:
		(armatureObjectID, boneIDs) = importSkeleton(context, fmdl)
	else:
		(armatureObjectID, boneIDs) = (None, [])
	
	meshObjectIDs = importMeshes(context, fmdl, materialIDs, armatureObjectID, boneIDs)
	
	rootMeshGroupID = importMeshTree(context, fmdl, meshObjectIDs, armatureObjectID, filename, importBoundingBoxMode)
	
	
	
	if context.mode != 'OBJECT':
		bpy.ops.object.mode_set(context.copy(), mode = 'OBJECT')
	if activeObjectID != None:
		blenderArmatureObject = bpy.data.objects[activeObjectID]
	
	return bpy.data.objects[rootMeshGroupID]


def exportFmdl(context, rootObjectName, exportSettings = None):
	def exportMaterial(blenderMaterial, textureFmdlObjects):
		materialInstance = FmdlFile.FmdlFile.MaterialInstance()
		
		for slot in blenderMaterial.texture_slots:
			if slot == None:
				continue
			blenderTexture = slot.texture
			if blenderTexture not in textureFmdlObjects:
				texture = FmdlFile.FmdlFile.Texture()
				texture.filename = blenderTexture.fmdl_texture_filename
				texture.directory = blenderTexture.fmdl_texture_directory
				textureFmdlObjects[blenderTexture] = texture
			materialInstance.textures.append((blenderTexture.fmdl_texture_role, textureFmdlObjects[blenderTexture]))
		
		for parameter in blenderMaterial.fmdl_material_parameters:
			materialInstance.parameters.append((parameter.name, [v for v in parameter.parameters]))
		
		materialInstance.name = blenderMaterial.name
		materialInstance.shader = blenderMaterial.fmdl_material_shader
		materialInstance.technique = blenderMaterial.fmdl_material_technique
		
		return materialInstance
	
	def exportMaterials(blenderMeshObjects):
		blenderMaterials = []
		for blenderMeshObject in blenderMeshObjects:
			blenderMesh = blenderMeshObject.data
			for blenderMaterial in blenderMesh.materials:
				if blenderMaterial is not None and blenderMaterial not in blenderMaterials:
					blenderMaterials.append(blenderMaterial)
		
		materialInstances = []
		materialFmdlObjects = {}
		textureFmdlObjects = {}
		for blenderMaterial in blenderMaterials:
			materialInstance = exportMaterial(blenderMaterial, textureFmdlObjects)
			materialInstances.append(materialInstance)
			materialFmdlObjects[blenderMaterial] = materialInstance
		
		return (materialInstances, materialFmdlObjects)
	
	def exportBone(name, parent, location):
		bone = FmdlFile.FmdlFile.Bone()
		bone.name = name
		bone.parent = parent
		if parent is not None:
			parent.children.append(bone)
		(x, y, z) = location
		bone.globalPosition = FmdlFile.FmdlFile.Vector4(x, y, z, 1.0)
		bone.localPosition = FmdlFile.FmdlFile.Vector4(0.0, 0.0, 0.0, 0.0)
		# Fill in bone.boundingBox later
		return bone
	
	def exportBones(blenderMeshObjects):
		def findBone(boneName, armatures):
			if boneName in PesSkeletonData.bones:
				pesBone = PesSkeletonData.bones[boneName]
				return (boneName, pesBone.sklParent, pesBone.startPosition)
			
			for armature in armatures:
				for blenderBone in armature.bones:
					if blenderBone.name == boneName:
						if blenderBone.parent is None:
							parentName = None
						else:
							parentName = blenderBone.parent.name
						(headX, headY, headZ) = blenderBone.head_local
						return (boneName, parentName, (headX, headZ, -headY))
			
			return (boneName, None, (0, 0, 0))
		
		blenderArmatures = []
		blenderMeshArmatures = {}
		for blenderMeshObject in blenderMeshObjects:
			blenderMeshArmatures[blenderMeshObject] = []
			for modifier in blenderMeshObject.modifiers:
				if modifier.type == 'ARMATURE':
					blenderArmature = modifier.object.data
					blenderArmatures.append(blenderArmature)
					blenderMeshArmatures[blenderMeshObject].append(blenderArmature)
		
		bones = {}
		for blenderMeshObject in blenderMeshObjects:
			boneNames = [vertexGroup.name for vertexGroup in blenderMeshObject.vertex_groups]
			armatures = (
				blenderMeshArmatures[blenderMeshObject] +
				[armature for armature in blenderArmatures if armature not in blenderMeshArmatures[blenderMeshObject]]
			)
			for boneName in boneNames:
				if boneName not in bones:
					bones[boneName] = findBone(boneName, armatures)
		for blenderArmature in blenderArmatures:
			for blenderBone in blenderArmature.bones:
				boneName = blenderBone.name
				if boneName not in bones:
					bones[boneName] = findBone(boneName, [blenderArmature])
		
		orderedBones = []
		bonesByName = {}
		def addOrderedBone(boneName):
			if boneName in bonesByName:
				return
			(name, parentName, location) = bones[boneName]
			if parentName is not None and parentName not in bones:
				parentName = None
			if parentName is not None:
				addOrderedBone(parentName)
				parent = bonesByName[parentName]
			else:
				parent = None
			bone = exportBone(name, parent, location)
			orderedBones.append(bone)
			bonesByName[boneName] = bone
		for boneName in bones.keys():
			addOrderedBone(boneName)
		
		return (orderedBones, bonesByName)
	
	def exportMeshGeometry(blenderMeshObject, colorLayer, uvLayerColor, uvLayerNormal, boneVector, scene):
		#
		# Setup a modified version of the mesh data that can be fiddled with.
		#
		modifiedBlenderMesh = blenderMeshObject.data.copy()
		
		#
		# Apply mesh-object position and orientation
		#
		modifiedBlenderMesh.transform(blenderMeshObject.matrix_world)
		
		loopTotals = [0 for i in range(len(modifiedBlenderMesh.polygons))]
		modifiedBlenderMesh.polygons.foreach_get("loop_total", loopTotals)
		if max(loopTotals) != 3:
			#
			# calc_tangents() only works on triangulated meshes
			#
			
			modifiedBlenderObject = bpy.data.objects.new('triangulation', modifiedBlenderMesh)
			modifiedBlenderObject.modifiers.new('triangulation', 'TRIANGULATE')
			newBlenderMesh = modifiedBlenderObject.to_mesh(scene, True, 'PREVIEW', calc_undeformed = True)
			bpy.data.objects.remove(modifiedBlenderObject)
			bpy.data.meshes.remove(modifiedBlenderMesh)
			modifiedBlenderMesh = newBlenderMesh
		
		modifiedBlenderMesh.use_auto_smooth = True
		if uvLayerNormal is None:
			uvLayerTangent = uvLayerColor
		else:
			uvLayerTangent = uvLayerNormal
		modifiedBlenderMesh.calc_tangents(uvLayerTangent)
		
		
		
		class Vertex:
			def __init__(self):
				self.position = None
				self.boneMapping = {}
				self.loops = []
		
		class Loop:
			def __init__(self):
				self.normal = None
				self.color = None
				self.uv = []
				
				self.tangents = []
				self.loopIndices = []
			
			def matches(self, other):
				if (self.color != None) != (other.color != None):
					return False
				if self.color != None and tuple(self.color) != tuple(other.color):
					return False
				if len(self.uv) != len(other.uv):
					return False
				for i in range(len(self.uv)):
					if self.uv[i].u != other.uv[i].u:
						return False
					if self.uv[i].v != other.uv[i].v:
						return False
				# Do an approximate check for normals.
				if self.normal.dot(other.normal) < 0.99:
					return False
				return True
			
			def add(self, other):
				self.tangents += other.tangents
				self.loopIndices += other.loopIndices
				self.normal = self.normal.slerp(other.normal, 1.0 / len(self.loopIndices))
			
			def computeTangent(self):
				# Filter out zero tangents
				nonzeroTangents = []
				for tangent in self.tangents:
					if tangent.length_squared > 0.1:
						nonzeroTangents.append(tangent)
				
				if len(nonzeroTangents) == 0:
					# Make up a tangent to avoid crashes
					# Cross product the loop normal with any vector that is not parallel with it.
					bestVector = None
					for v in [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]:
						vector = mathutils.Vector(v)
						if bestVector == None or abs(vector.dot(self.normal)) < abs(bestVector.dot(self.normal)):
							bestVector = vector
					return bestVector.cross(self.normal)
				
				# Average out the different tangents.
				# In case of conflicts, bias towards the first entry in the list.
				averageTangent = nonzeroTangents[0]
				weight = 1
				remaining = nonzeroTangents[1:]
				while len(remaining) > 0:
					skipped = []
					for tangent in remaining:
						if averageTangent.dot(tangent) < -0.9:
							skipped.append(tangent)
						else:
							weight += 1
							averageTangent = averageTangent.slerp(tangent, 1.0 / weight)
					if len(skipped) == len(remaining):
						break
					remaining = skipped
				return averageTangent
		
		vertices = []
		for i in range(len(modifiedBlenderMesh.vertices)):
			blenderVertex = modifiedBlenderMesh.vertices[i]
			vertex = Vertex()
			vertex.position = FmdlFile.FmdlFile.Vector3(
				blenderVertex.co.x,
				blenderVertex.co.z,
				-blenderVertex.co.y,
			)
			for group in blenderVertex.groups:
				vertex.boneMapping[boneVector[group.group]] = group.weight
			vertices.append(vertex)
		
		for i in range(len(modifiedBlenderMesh.loops)):
			blenderLoop = modifiedBlenderMesh.loops[i]
			vertex = vertices[blenderLoop.vertex_index]
			
			loop = Loop()
			loop.normal = blenderLoop.normal
			loop.tangents = [blenderLoop.tangent]
			loop.loopIndices = [i]
			
			if colorLayer is not None:
				loop.color = [c for c in modifiedBlenderMesh.vertex_colors[colorLayer].data[i].color] + [1.0]
			loop.uv.append(FmdlFile.FmdlFile.Vector2(
				modifiedBlenderMesh.uv_layers[uvLayerColor].data[i].uv[0],
				1.0 - modifiedBlenderMesh.uv_layers[uvLayerColor].data[i].uv[1],
			))
			if uvLayerNormal != None:
				loop.uv.append(FmdlFile.FmdlFile.Vector2(
					modifiedBlenderMesh.uv_layers[uvLayerNormal].data[i].uv[0],
					1.0 - modifiedBlenderMesh.uv_layers[uvLayerNormal].data[i].uv[1],
				))
			
			found = False
			for otherLoop in vertex.loops:
				if otherLoop.matches(loop):
					otherLoop.add(loop)
					found = True
					break
			if not found:
				vertex.loops.append(loop)
		
		fmdlVertices = []
		fmdlLoopVertices = {}
		for vertex in vertices:
			for loop in vertex.loops:
				fmdlVertex = FmdlFile.FmdlFile.Vertex()
				fmdlVertex.position = vertex.position
				fmdlVertex.boneMapping = vertex.boneMapping
				fmdlVertex.normal = FmdlFile.FmdlFile.Vector4(
					loop.normal.x,
					loop.normal.z,
					-loop.normal.y,
					1.0,
				)
				tangent = loop.computeTangent()
				fmdlVertex.tangent = FmdlFile.FmdlFile.Vector4(
					tangent.x,
					tangent.z,
					-tangent.y,
					1.0,
				)
				fmdlVertex.color = loop.color
				fmdlVertex.uv = loop.uv
				fmdlVertices.append(fmdlVertex)
				for loopIndex in loop.loopIndices:
					fmdlLoopVertices[loopIndex] = fmdlVertex
		
		fmdlFaces = []
		for face in modifiedBlenderMesh.polygons:
			fmdlFaces.append(FmdlFile.FmdlFile.Face(
				fmdlLoopVertices[face.loop_start + 2],
				fmdlLoopVertices[face.loop_start + 1],
				fmdlLoopVertices[face.loop_start + 0],
			))
		
		bpy.data.meshes.remove(modifiedBlenderMesh)
		return (fmdlVertices, fmdlFaces)
	
	def exportMesh(blenderMeshObject, materialFmdlObjects, bonesByName, scene):
		blenderMesh = blenderMeshObject.data
		name = blenderMeshObject.name
		
		vertexFields = FmdlFile.FmdlFile.VertexFields()
		vertexFields.hasNormal = True
		vertexFields.hasTangent = True
		
		if len(blenderMesh.vertex_colors) == 0:
			colorLayer = None
			vertexFields.hasColor = False
		elif len(blenderMesh.vertex_colors) == 1:
			colorLayer = 0
			vertexFields.hasColor = True
		else:
			raise FmdlExportError("Mesh '%s' has more than one color layer." % name)
		
		materials = [material for material in blenderMesh.materials if material is not None]
		if len(materials) == 0:
			raise FmdlExportError("Mesh '%s' does not have an associated material." % name)
		if len(materials) > 1:
			raise FmdlExportError("Mesh '%s' has multiple associated materials, including '%s' and '%s'." % (name, materials[0].name, materials[1].name))
		blenderMaterial = materials[0]
		
		if len(blenderMesh.uv_layers) == 0:
			raise FmdlExportError("Mesh '%s' does not have a UV map." % name)
		elif len(blenderMesh.uv_layers) == 1:
			uvLayerColor = blenderMesh.uv_layers[0].name
			uvLayerNormal = None
			vertexFields.uvCount = 1
		else:
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
				if uvLayerName not in uvMaps:
					uvMaps.append(uvLayerName)
			
			if len(colorUvMaps) > 1:
				raise FmdlExportError("Mesh '%s' has ambiguous UV maps: multiple UV maps configured as primary UV map." % name)
			if len(normalUvMaps) > 1:
				raise FmdlExportError("Mesh '%s' has ambiguous UV maps: multiple UV maps configured as normals UV map." % name)
			
			if len(colorUvMaps) == 0 and 'UVMap' in blenderMesh.uv_layers and 'UVMap' not in normalUvMaps:
				colorUvMaps.append('UVMap')
			if len(normalUvMaps) == 0 and 'normal_map' in blenderMesh.uv_layers and 'normal_map' not in colorUvMaps:
				normalUvMaps.append('normal_map')
			if len(colorUvMaps) == 0 and len(normalUvMaps) == 1 and len(blenderMesh.uv_layers) == 2:
				for layer in blenderMesh.uv_layers:
					if layer.name != normalUvMaps[0]:
						colorUvMaps.append(layer.name)
						break
			
			if len(colorUvMaps) == 0:
				raise FmdlExportError("Mesh '%s' has ambiguous UV maps: found %s UV maps, but no primary UV map is configured." % (name, len(blenderMesh.uv_layers)))
			if len(normalUvMaps) == 0:
				raise FmdlExportError("Mesh '%s' has ambiguous UV maps: found %s UV maps, but no normals UV map is configured." % (name, len(blenderMesh.uv_layers)))
			
			uvLayerColor = colorUvMaps[0]
			if colorUvMaps[0] == normalUvMaps[0]:
				uvLayerNormal = None
				vertexFields.uvCount = 1
			else:
				uvLayerNormal = normalUvMaps[0]
				vertexFields.uvCount = 2
		
		boneVector = [bonesByName[vertexGroup.name] for vertexGroup in blenderMeshObject.vertex_groups]
		if len(boneVector) > 0:
			vertexFields.hasBoneMapping = True
		
		(vertices, faces) = exportMeshGeometry(blenderMeshObject, colorLayer, uvLayerColor, uvLayerNormal, boneVector, scene)
		
		mesh = FmdlFile.FmdlFile.Mesh()
		mesh.vertices = vertices
		mesh.faces = faces
		mesh.boneGroup = FmdlFile.FmdlFile.BoneGroup()
		mesh.boneGroup.bones = boneVector
		mesh.materialInstance = materialFmdlObjects[blenderMaterial]
		mesh.alphaEnum = blenderMesh.fmdl_alpha_enum
		mesh.shadowEnum = blenderMesh.fmdl_shadow_enum
		mesh.vertexFields = vertexFields
		
		return mesh
	
	def exportCustomBoundingBox(blenderMeshObject, fmdlMeshObject):
		latticeObject = None
		for child in blenderMeshObject.children:
			if child.type == 'LATTICE':
				if latticeObject is not None:
					raise FmdlExportError("Mesh '%s' has multiple conflicting custom bounding boxes." % blenderMeshObject.name)
				latticeObject = child
		
		if latticeObject is None:
			return None
		
		fmdlMeshObject.extensionHeaders.add("Custom-Bounding-Box-Meshes")
		
		transformedLattice = latticeObject.data.copy()
		transformedLattice.transform(latticeObject.matrix_world)
		transformedLatticeObject = bpy.data.objects.new('measurement', transformedLattice)
		boundingBox = transformedLatticeObject.bound_box
		boundingBoxFmdlNotation = [(boundingBox[i][0], boundingBox[i][2], -boundingBox[i][1]) for i in range(8)]
		minCoordinates = tuple(min([boundingBoxFmdlNotation[j][i] for j in range(8)]) for i in range(3))
		maxCoordinates = tuple(max([boundingBoxFmdlNotation[j][i] for j in range(8)]) for i in range(3))
		bpy.data.objects.remove(transformedLatticeObject)
		bpy.data.lattices.remove(transformedLattice)
		
		return FmdlFile.FmdlFile.BoundingBox(
			FmdlFile.FmdlFile.Vector4(
				minCoordinates[0],
				minCoordinates[1],
				minCoordinates[2],
				1.0
			),
			FmdlFile.FmdlFile.Vector4(
				maxCoordinates[0],
				maxCoordinates[1],
				maxCoordinates[2],
				1.0
			)
		)
	
	def determineParentBlenderObject(blenderObject, blenderRootObject, parentBlenderObjects):
		if blenderObject in parentBlenderObjects:
			return
		
		parentBlenderObject = blenderObject.parent
		while parentBlenderObject != None:
			if parentBlenderObject == blenderRootObject:
				parentBlenderObject = None
			elif parentBlenderObject.type in ['MESH', 'EMPTY']:
				break
			else:
				parentBlenderObject = parentBlenderObject.parent
		
		if parentBlenderObject != None:
			determineParentBlenderObject(parentBlenderObject, blenderRootObject, parentBlenderObjects)
		
		parentBlenderObjects[blenderObject] = parentBlenderObject
	
	def createMeshGroup(blenderObject, name, parentMeshGroup, meshGroups, meshGroupFmdlObjects):
		meshGroup = FmdlFile.FmdlFile.MeshGroup()
		meshGroup.name = name
		# Fill in meshGroup.boundingBox later
		meshGroup.visible = True
		
		if parentMeshGroup != None:
			meshGroup.parent = parentMeshGroup
			parentMeshGroup.children.append(meshGroup)
		
		meshGroups.append(meshGroup)
		meshGroupFmdlObjects[blenderObject] = meshGroup
		
		return meshGroup
	
	def exportMeshGroup(blenderObject, parentBlenderObjects, meshGroups, meshGroupFmdlObjects):
		if blenderObject in meshGroupFmdlObjects:
			return meshGroupFmdlObjects[blenderObject]
		
		if parentBlenderObjects[blenderObject] != None:
			parentMeshGroup = exportMeshGroup(parentBlenderObjects[blenderObject], parentBlenderObjects, meshGroups, meshGroupFmdlObjects)
		else:
			parentMeshGroup = None
		
		return createMeshGroup(blenderObject, blenderObject.name, parentMeshGroup, meshGroups, meshGroupFmdlObjects)
	
	def exportMeshMeshGroup(blenderMeshObject, meshFmdlObjects, parentBlenderObjects, meshGroups, meshGroupFmdlObjects):
		if (
			    blenderMeshObject.name.startswith('mesh_id ')
			and blenderMeshObject not in parentBlenderObjects.values()
		):
			if parentBlenderObjects[blenderMeshObject] is not None:
				parentMeshGroup = exportMeshGroup(parentBlenderObjects[blenderMeshObject], parentBlenderObjects, meshGroups, meshGroupFmdlObjects)
			else:
				parentMeshGroup = None
			meshGroup = createMeshGroup(blenderMeshObject, '', parentMeshGroup, meshGroups, meshGroupFmdlObjects)
		else:
			meshGroup = exportMeshGroup(blenderMeshObject, parentBlenderObjects, meshGroups, meshGroupFmdlObjects)
		
		meshGroup.meshes.append(meshFmdlObjects[blenderMeshObject])
	
	def exportMeshGroups(blenderMeshObjects, meshFmdlObjects, blenderRootObject):
		parentBlenderObjects = {}
		for blenderMeshObject in blenderMeshObjects:
			determineParentBlenderObject(blenderMeshObject, blenderRootObject, parentBlenderObjects)
		
		meshGroups = []
		meshGroupFmdlObjects = {}
		for blenderMeshObject in blenderMeshObjects:
			exportMeshMeshGroup(blenderMeshObject, meshFmdlObjects, parentBlenderObjects, meshGroups, meshGroupFmdlObjects)
		
		return meshGroups
	
	def sortMeshes(meshGroups):
		return [mesh for meshGroup in meshGroups for mesh in meshGroup.meshes]
	
	def calculateBoneBoundingBoxes(bones, meshes):
		boneVertexPositions = {}
		for bone in bones:
			boneVertexPositions[bone] = []
		
		for mesh in meshes:
			if not mesh.vertexFields.hasBoneMapping:
				continue
			
			for vertex in mesh.vertices:
				for bone in vertex.boneMapping:
					boneVertexPositions[bone].append(vertex.position)
		
		for bone in bones:
			vertexPositions = boneVertexPositions[bone]
			if len(vertexPositions) == 0:
				bone.boundingBox = FmdlFile.FmdlFile.BoundingBox(
					FmdlFile.FmdlFile.Vector4(0.0, 0.0, 0.0, 1.0),
					FmdlFile.FmdlFile.Vector4(0.0, 0.0, 0.0, 1.0)
				)
			else:
				bone.boundingBox = FmdlFile.FmdlFile.BoundingBox(
					FmdlFile.FmdlFile.Vector4(
						min(position.x for position in vertexPositions),
						min(position.y for position in vertexPositions),
						min(position.z for position in vertexPositions),
						1.0
					),
					FmdlFile.FmdlFile.Vector4(
						max(position.x for position in vertexPositions),
						max(position.y for position in vertexPositions),
						max(position.z for position in vertexPositions),
						1.0
					)
				)
	
	def calculateMeshBoundingBox(mesh, meshCustomBoundingBoxes):
		if mesh in meshCustomBoundingBoxes:
			return meshCustomBoundingBoxes[mesh]
		
		vertices = mesh.vertices
		if len(vertices) == 0:
			return None
		
		return FmdlFile.FmdlFile.BoundingBox(
			FmdlFile.FmdlFile.Vector4(
				min(vertex.position.x for vertex in vertices),
				min(vertex.position.y for vertex in vertices),
				min(vertex.position.z for vertex in vertices),
				1.0
			),
			FmdlFile.FmdlFile.Vector4(
				max(vertex.position.x for vertex in vertices),
				max(vertex.position.y for vertex in vertices),
				max(vertex.position.z for vertex in vertices),
				1.0
			)
		)
	
	def calculateMeshGroupBoundingBox(meshGroup, meshCustomBoundingBoxes):
		boundingBoxes = []
		for mesh in meshGroup.meshes:
			boundingBox = calculateMeshBoundingBox(mesh, meshCustomBoundingBoxes)
			if boundingBox != None:
				boundingBoxes.append(boundingBox)
		for child in meshGroup.children:
			boundingBox = calculateMeshGroupBoundingBox(child, meshCustomBoundingBoxes)
			if boundingBox != None:
				boundingBoxes.append(boundingBox)
		
		if len(boundingBoxes) == 0:
			meshGroup.boundingBox = FmdlFile.FmdlFile.BoundingBox(
				FmdlFile.FmdlFile.Vector4(0.0, 0.0, 0.0, 1.0),
				FmdlFile.FmdlFile.Vector4(0.0, 0.0, 0.0, 1.0)
			)
			return None
		
		meshGroup.boundingBox = FmdlFile.FmdlFile.BoundingBox(
			FmdlFile.FmdlFile.Vector4(
				min(box.min.x for box in boundingBoxes),
				min(box.min.y for box in boundingBoxes),
				min(box.min.z for box in boundingBoxes),
				1.0
			),
			FmdlFile.FmdlFile.Vector4(
				max(box.max.x for box in boundingBoxes),
				max(box.max.y for box in boundingBoxes),
				max(box.max.z for box in boundingBoxes),
				1.0
			)
		)
		
		return meshGroup.boundingBox
	
	def calculateBoundingBoxes(meshGroups, bones, meshes, meshCustomBoundingBoxes):
		calculateBoneBoundingBoxes(bones, meshes)
		
		for meshGroup in meshGroups:
			if meshGroup.parent == None:
				calculateMeshGroupBoundingBox(meshGroup, meshCustomBoundingBoxes)
	
	def listMeshObjects(context, rootObjectName):
		if rootObjectName != None and rootObjectName not in context.scene.objects:
			rootObjectName = None
		
		blenderMeshObjects = []
		def findMeshObjects(blenderObject, blenderMeshObjects):
			if blenderObject.type == 'MESH' and len(blenderObject.data.polygons) > 0:
				blenderMeshObjects.append(blenderObject)
			childNames = [child.name for child in blenderObject.children]
			for childName in sorted(childNames):
				findMeshObjects(bpy.data.objects[childName], blenderMeshObjects)
		if rootObjectName == None:
			blenderMeshObjects = []
			blenderArmatureObjects = []
			for object in context.scene.objects:
				if object.parent is None:
					findMeshObjects(object, blenderMeshObjects)
				if object.type == 'MESH' and len(object.data.polygons) > 0:
					for modifier in object.modifiers:
						if modifier.type == 'ARMATURE':
							blenderArmatureObject = modifier.object
							if blenderArmatureObject not in blenderArmatureObjects:
								blenderArmatureObjects.append(blenderArmatureObject)
			if (
				len(blenderArmatureObjects) == 1 and
				blenderArmatureObjects[0].parent != None and
				blenderArmatureObjects[0].parent.parent == None
			):
				blenderRootObject = blenderArmatureObjects[0].parent
			else:
				blenderRootObject = None
		else:
			blenderRootObject = context.scene.objects[rootObjectName]
			findMeshObjects(blenderRootObject, blenderMeshObjects)
			
			if blenderRootObject.type == 'MESH' and len(blenderRootObject.data.polygons) > 0:
				blenderRootObject = blenderRootObject.parent
		
		return (blenderMeshObjects, blenderRootObject)
	
	
	
	if exportSettings == None:
		exportSettings = ExportSettings()
	
	if context.mode != 'OBJECT':
		bpy.ops.object.mode_set(context.copy(), mode = 'OBJECT')
	
	
	
	(blenderMeshObjects, blenderRootObject) = listMeshObjects(context, rootObjectName)
	
	(materialInstances, materialFmdlObjects) = exportMaterials(blenderMeshObjects)
	
	(bones, bonesByName) = exportBones(blenderMeshObjects)
	
	meshFmdlObjects = {}
	meshCustomBoundingBoxes = {}
	for blenderMeshObject in blenderMeshObjects:
		mesh = exportMesh(blenderMeshObject, materialFmdlObjects, bonesByName, context.scene)
		meshFmdlObjects[blenderMeshObject] = mesh
		
		boundingBox = exportCustomBoundingBox(blenderMeshObject, mesh)
		if boundingBox is not None:
			meshCustomBoundingBoxes[mesh] = boundingBox
	
	meshGroups = exportMeshGroups(blenderMeshObjects, meshFmdlObjects, blenderRootObject)
	
	meshes = sortMeshes(meshGroups)
	
	calculateBoundingBoxes(meshGroups, bones, meshes, meshCustomBoundingBoxes)
	
	fmdlFile = FmdlFile.FmdlFile()
	fmdlFile.bones = bones
	fmdlFile.materialInstances = materialInstances
	fmdlFile.meshes = meshes
	fmdlFile.meshGroups = meshGroups
	
	if exportSettings.enableExtensions and exportSettings.enableVertexLoopPreservation:
		fmdlFile = FmdlSplitVertexEncoding.encodeFmdlVertexLoopPreservation(fmdlFile)
	if exportSettings.enableExtensions and exportSettings.enableMeshSplitting:
		fmdlFile = FmdlMeshSplitting.encodeFmdlSplitMeshes(fmdlFile)
	
	errors = []
	for mesh in fmdlFile.meshes:
		meshName = None
		for meshGroup in fmdlFile.meshGroups:
			if len(meshGroup.meshes) == 1 and meshGroup.meshes[0] == mesh:
				if meshGroup.name != "":
					meshName = meshGroup.name
				break
		if meshName is None:
			meshIndex = fmdlFile.meshes.index(mesh)
			meshName = "mesh_id %s" % meshIndex
		
		if len(mesh.vertices) > 65535:
			errors.append("Mesh '%s' contains %s vertices out of a maximum of 65535" % (meshName, len(mesh.vertices)))
		if len(mesh.faces) > 21845:
			errors.append("Mesh '%s' contains %s faces out of a maximum of 21845" % (meshName, len(mesh.faces)))
		if mesh.boneGroup is not None and len(mesh.boneGroup.bones) > 32:
			errors.append("Mesh '%s' bone group contains %s bones out of a maximum of 32" % (meshName, len(mesh.boneGroup.bones)))
	if len(errors) > 0:
		raise FmdlExportError(errors)
	
	return fmdlFile

def exportSummary(context, rootObjectName):
	def objectName(blenderObject, rootObject):
		name = blenderObject.name
		parent = blenderObject.parent
		while parent is not None and parent != rootObject:
			name = "%s/%s" % (parent.name, name)
			parent = parent.parent
		return name
	
	def splittingSummary(vertices, faces, bones):
		output = ""
		if vertices > FmdlMeshSplitting.VERTEX_LIMIT_HARD:
			output += "\t\tvertices > %s\n" % FmdlMeshSplitting.VERTEX_LIMIT_HARD
		if faces > FmdlMeshSplitting.FACE_LIMIT_HARD:
			output += "\t\tfaces > %s\n" % FmdlMeshSplitting.FACE_LIMIT_HARD
		if bones > FmdlMeshSplitting.BONE_LIMIT_HARD:
			output += "\t\tbones > %s\n" % FmdlMeshSplitting.BONE_LIMIT_HARD
		if len(output) > 0:
			output = "\tMesh will be split to fit within fmdl limitations:\n" + output
		return output
	
	def materialSummary(material):
		output = "\tMaterial [%s]:\n" % material.name
		output += "\t\tshader \"%s\"\n" % material.fmdl_material_shader
		output += "\t\ttechnique \"%s\"\n" % material.fmdl_material_technique
		for parameter in material.fmdl_material_parameters:
			output += "\t\tparameter [%s] = [%.2f, %.2f, %.2f, %.2f]\n" % (parameter.name, *parameter.parameters)
		for slot in material.texture_slots:
			if slot == None:
				continue
			output += "\t\ttexture [%s] = \n" % slot.texture.fmdl_texture_role
			output += "\t\t\t\"%s\"\n" % slot.texture.fmdl_texture_directory
			output += "\t\t\t\t\"%s\"\n" % slot.texture.fmdl_texture_filename
		return output
	
	def skeletonSummary(bones):
		bodyPartAllBones = {}
		for pesVersion in PesSkeletonData.skeletonBones:
			for bodyPart in PesSkeletonData.skeletonBones[pesVersion]:
				if bodyPart not in bodyPartAllBones:
					bodyPartAllBones[bodyPart] = set()
				bodyPartAllBones[bodyPart].update(PesSkeletonData.skeletonBones[pesVersion][bodyPart])
		bodyPartUniqueBones = {}
		for bodyPart in bodyPartAllBones:
			bodyPartUniqueBones[bodyPart] = bodyPartAllBones[bodyPart].copy()
			for otherBodyPart in bodyPartAllBones:
				if otherBodyPart != bodyPart:
					bodyPartUniqueBones[bodyPart].difference_update(bodyPartAllBones[otherBodyPart])
		
		bones = sorted(bones)
		requiredBodyParts = set()
		for bone in bones:
			for bodyPart in bodyPartUniqueBones:
				if bone in bodyPartUniqueBones[bodyPart]:
					requiredBodyParts.add(bodyPart)
		
		bodyPartVersions = {}
		unknownBones = []
		for bone in bones:
			selectedBodyPart = None
			for bodyPart in requiredBodyParts:
				if bone in bodyPartAllBones[bodyPart]:
					selectedBodyPart = bodyPart
					break
			if selectedBodyPart is None:
				for bodyPart in sorted(list(bodyPartAllBones.keys()), reverse=True):
					if bone in bodyPartAllBones[bodyPart]:
						selectedBodyPart = bodyPart
						break
			
			if selectedBodyPart is None:
				unknownBones.append(bone)
			else:
				for pesVersion in PesSkeletonData.skeletonBones:
					if bone in PesSkeletonData.skeletonBones[pesVersion][selectedBodyPart]:
						minimumPesVersion = pesVersion
						break
				# minimumPesVersion MUST be set at this point
				if selectedBodyPart not in bodyPartVersions or bodyPartVersions[selectedBodyPart] < minimumPesVersion:
					bodyPartVersions[selectedBodyPart] = minimumPesVersion
		
		output = ""
		if len(bodyPartVersions) == 0 and len(unknownBones) == 0:
			output += "\tSkeleton: none\n"
		elif len(bodyPartVersions) == 1 and len(unknownBones) == 0:
			bodyPart = list(bodyPartVersions.keys())[0]
			output += "\tSkeleton: %s %s\n" % (bodyPartVersions[bodyPart], bodyPart)
		else:
			output += "\tSkeleton:\n"
			for bodyPart in sorted(list(bodyPartVersions.keys())):
				output += "\t\tFound bones for %s %s\n" % (bodyPartVersions[bodyPart], bodyPart)
			if len(unknownBones) > 0:
				chunks = [[]]
				for bone in unknownBones:
					if len(chunks[-1]) >= 6:
						chunks.append([])
					chunks[-1].append('"%s"' % bone)
				output += "\t\tFound unknown bones:\n"
				for boneChunk in chunks:
					output += "\t\t\t%s\n" % ", ".join(boneChunk)
		return output
	
	def meshSummary(blenderMeshObject, rootObject):
		mesh = blenderMeshObject.data
		lattices = [child for child in blenderMeshObject.children if child.type == 'LATTICE']
		bones = [name for name in blenderMeshObject.vertex_groups.keys()]
		
		output = "Mesh [%s]\n" % objectName(blenderMeshObject, rootObject)
		output += "\tVertices: %s\n" % len(mesh.vertices)
		output += "\tFaces: %s\n" % len(mesh.polygons)
		output += "\tBones: %s\n" % len(bones)
		output += "\tAlpha Enum: %s\n" % mesh.fmdl_alpha_enum
		output += "\tShadow Enum: %s\n" % mesh.fmdl_shadow_enum
		if len(mesh.vertex_colors) == 1:
			output += "\tMesh has vertex color information\n"
		elif len(mesh.vertex_colors) > 1:
			output += "\tMesh has inconsistent vertex color information\n"
		if len(lattices) == 1:
			output += "\tMesh has custom bounding box\n"
		elif len(lattices) > 1:
			output += "\tMesh has inconsistent bounding box\n"
		output += splittingSummary(len(mesh.vertices), len(mesh.polygons), len(bones))
		if len(mesh.materials) == 0:
			output += "\tMaterial: none\n"
		elif len(mesh.materials) == 1:
			output += materialSummary(mesh.materials[0])
		else:
			output += "\tMaterial: inconsistent\n"
		output += skeletonSummary(bones)
		return output
	
	meshObjects = {}
	if rootObjectName is None:
		rootObject = None
		output = "Export summary\n"
		for blenderObject in context.scene.objects:
			if blenderObject.type == 'MESH' and len(blenderObject.data.polygons) > 0:
				meshObjects[objectName(blenderObject, rootObject)] = blenderObject
	else:
		rootObject = bpy.data.objects[rootObjectName]
		output = "Export summary for %s\n" % objectName(rootObject, None)
		def findMeshObjects(blenderObject):
			if blenderObject.type == 'MESH' and len(blenderObject.data.polygons) > 0:
				meshObjects[objectName(blenderObject, rootObject)] = blenderObject
			for child in blenderObject.children:
				findMeshObjects(child)
		findMeshObjects(rootObject)
	output += "------------------------------\n"
	for key in sorted(list(meshObjects.keys())):
		output += meshSummary(meshObjects[key], rootObject)
	return output
