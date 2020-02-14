import bpy
import itertools
import os
import os.path
import re

from . import FmdlFile, PesSkeletonData


class UnsupportedFmdl(Exception):
	pass

def setActiveObject(context, blenderObject):
	if 'view_layer' in dir(context):
		context.view_layer.objects.active = blenderObject
	else:
		context.scene.objects.active = blenderObject



def importFmdl(context, fmdl, filename):
	UV_MAP_COLOR = 'UVMap'
	UV_MAP_NORMALS = 'normal_map'
	
	def findTexture(texture, textureSearchPath):
		textureFilename = texture.directory.replace('\\', '/').rstrip('/') + '/' + texture.filename.replace('\\', '/').lstrip('/')
		textureFilenameComponents = tuple(filter(None, textureFilename.split('/')))
		
		for searchDirectory in textureSearchPath:
			for componentCount in range(1, len(textureFilenameComponents)):
				textureFilenameSuffix = textureFilenameComponents[len(textureFilenameComponents) - componentCount :]
				filename = os.path.join(searchDirectory, *textureFilenameSuffix)
				if os.path.isfile(filename):
					return filename
		
		if texture.filename == 'kit.dds':
			for searchDirectory in textureSearchPath:
				for componentCount in range(0, len(textureFilenameComponents)):
					try:
						textureDirectorySuffix = textureFilenameComponents[len(textureFilenameComponents) - componentCount - 1: -1]
						directory = os.path.join(searchDirectory, *textureDirectorySuffix)
						
						if not os.path.isdir(directory):
							continue
						
						filenames = os.listdir(directory)
						for filename in filenames:
							if re.match('^u[0-9]{4}p1\.dds$', filename):
								fullName = os.path.join(directory, filename)
								if os.path.isfile(fullName):
									return fullName
					except:
						pass
		
		return None
	
	def addTexture(blenderMaterial, textureRole, texture, textureIDs, uvMapColor, uvMapNormals, textureSearchPath):
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
			
			filename = findTexture(texture, textureSearchPath)
			if filename == None:
				blenderImage.filepath = texture.directory + texture.filename
			else:
				blenderImage.filepath = filename
				blenderImage.reload()
			
			blenderTexture = bpy.data.textures.new(texture.filename, type = 'IMAGE')
			blenderTexture.image = blenderImage
			
			if '_NRM' in textureRole:
				blenderTexture.use_normal_map = True
			
			textureIDs[identifier] = blenderImage.name
		
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
			blenderTextureSlot.use_map_specular = True
			blenderTextureSlot.use_map_color_spec = True
			blenderTextureSlot.use = True
		else:
			blenderTextureSlot.use = False
		
		blenderTexture.fmdl_texture_path = texture.directory + texture.filename
		blenderTexture.fmdl_texture_role = textureRole
	
	def materialHasSeparateUVMaps(materialInstance, fmdl):
		for mesh in fmdl.meshes:
			if mesh.materialInstance == materialInstance:
				if mesh.vertexFields.uvCount >= 1 and 1 not in mesh.vertexFields.uvEqualities[0]:
					return True
		return False
	
	def importMaterials(fmdl, textureSearchPath):
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
			
			for (role, texture) in materialInstance.textures:
				addTexture(blenderMaterial, role, texture, textureIDs, uvMapColor, uvMapNormals, textureSearchPath)
		
		return materialIDs
	
	def addBone(blenderArmature, bone, boneIDs, bonesByName):
		if bone in boneIDs:
			return boneIDs[bone]
		
		if bone.name in PesSkeletonData.bones:
			pesBone = PesSkeletonData.bones[bone.name]
			tail = (pesBone["x"], -pesBone["z"], pesBone["y"])
			parentName = pesBone["parent"]
			if parentName == None:
				head = (tail[0], tail[1], tail[2] + 0.00001)
				parentBone = None
			else:
				parentPesBone = PesSkeletonData.bones[parentName]
				head = (parentPesBone["x"], -parentPesBone["z"], parentPesBone["y"])
				if bone.parent != None and bone.parent.name == parentName:
					parentBone = bone.parent
				elif parentName in bonesByName:
					parentBone = bonesByName[parentName]
				else:
					parentBone = None
		else:
			tail = (bone.globalPosition.x, -bone.globalPosition.z, bone.globalPosition.y)
			head = (bone.localPosition.x, -bone.localPosition.z, bone.localPosition.y)
			parentBone = bone.parent
		
		if parentBone != None:
			parentBoneID = addBone(blenderArmature, parentBone, boneIDs, bonesByName)
			head = tuple(blenderArmature.edit_bones[parentBoneID].tail[i] for i in range(3))
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
			blenderEditBone.use_connect = True
		
		return boneID
	
	def importSkeleton(context, fmdl):
		blenderArmature = bpy.data.armatures.new("fmdl skeleton")
		blenderArmature.show_names = True
		
		blenderArmatureObject = bpy.data.objects.new("fmdl skeleton", blenderArmature)
		armatureObjectID = blenderArmatureObject.name
		
		context.scene.objects.link(blenderArmatureObject)
		setActiveObject(context, blenderArmatureObject)
		
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
	
	def importMesh(mesh, name, fmdl, materialIDs, armatureObjectID, boneIDs):
		blenderMesh = bpy.data.meshes.new(name)
		
		vertexIndices = {}
		for i in range(len(mesh.vertices)):
			vertexIndices[mesh.vertices[i]] = i
		
		loopVertices = list(itertools.chain.from_iterable([reversed(face.vertices) for face in mesh.faces]))
		
		blenderMesh.vertices.add(len(mesh.vertices))
		blenderMesh.vertices.foreach_set("co", tuple(itertools.chain.from_iterable([
			(vertex.position.x, -vertex.position.z, vertex.position.y) for vertex in mesh.vertices
		])))
		
		blenderMesh.loops.add(len(mesh.faces) * 3)
		blenderMesh.loops.foreach_set("vertex_index", tuple([vertexIndices[vertex] for vertex in loopVertices]))
		
		blenderMesh.polygons.add(len(mesh.faces))
		blenderMesh.polygons.foreach_set("loop_start", tuple(range(0, 3 * len(mesh.faces), 3)))
		blenderMesh.polygons.foreach_set("loop_total", [3 for face in mesh.faces])
		
		blenderMesh.update(calc_edges = True)
		
		if mesh.vertexFields.hasNormal:
			def normalize(vector):
				(x, y, z) = vector
				size = (x ** 2 + y ** 2 + z ** 2) ** 0.5
				q = (x / size, y / size, z / size)
				return (x / size, y / size, z / size)
			blenderMesh.normals_split_custom_set_from_vertices([
				normalize((vertex.normal.x, -vertex.normal.z, vertex.normal.y)) for vertex in mesh.vertices
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
			if 'uv_textures' in dir(blenderMesh):
				uvTexture = blenderMesh.uv_textures.new(name = UV_MAP_COLOR)
				uvLayer = blenderMesh.uv_layers[uvTexture.name]
			else:
				uvLayer = blenderMesh.uv_layers.new(name = UV_MAP_COLOR, do_init = False)
				uvTexture = uvLayer
			
			uvLayer.data.foreach_set("uv", tuple(itertools.chain.from_iterable([
				(vertex.uv[0].u, 1.0 - vertex.uv[0].v) for vertex in loopVertices
			])))
			uvTexture.active = True
			uvTexture.active_clone = True
			uvTexture.active_render = True
		
		if mesh.vertexFields.uvCount >= 2 and 0 not in mesh.vertexFields.uvEqualities[1]:
			if 'uv_textures' in dir(blenderMesh):
				uvTexture = blenderMesh.uv_textures.new(name = UV_MAP_NORMALS)
				uvLayer = blenderMesh.uv_layers[uvTexture.name]
			else:
				uvLayer = blenderMesh.uv_layers.new(name = UV_MAP_NORMALS, do_init = False)
				uvTexture = uvLayer
			
			uvLayer.data.foreach_set("uv", tuple(itertools.chain.from_iterable([
				(vertex.uv[1].u, 1.0 - vertex.uv[1].v) for vertex in loopVertices
			])))
		
		if mesh.vertexFields.uvCount >= 3:
			raise UnsupportedFmdl("No support for fmdl files with more than 2 UV maps")
		
		blenderMesh.materials.append(bpy.data.materials[materialIDs[mesh.materialInstance]])
		
		blenderMesh.fmdl_alpha_enum = mesh.alphaEnum
		blenderMesh.fmdl_shadow_enum = mesh.shadowEnum
		
		blenderMeshObject = bpy.data.objects.new(blenderMesh.name, blenderMesh)
		meshObjectID = blenderMeshObject.name
		context.scene.objects.link(blenderMeshObject)
		
		if mesh.vertexFields.hasBoneMapping:
			vertexGroupIDs = addSkeletonMeshModifier(blenderMeshObject, mesh.boneGroup, armatureObjectID, boneIDs)
			for i in range(len(mesh.vertices)):
				for bone in mesh.vertices[i].boneMapping:
					weight = mesh.vertices[i].boneMapping[bone]
					blenderMeshObject.vertex_groups[vertexGroupIDs[bone]].add((i, ), weight, 'REPLACE')
		
		return meshObjectID
	
	def importMeshes(context, fmdl, materialIDs, armatureObjectID, boneIDs):
		def addMeshNames(meshGroup, meshNames):
			for mesh in meshGroup.meshes:
				meshNames[mesh] = meshGroup.name
			for child in meshGroup.children:
				addMeshNames(child, meshNames)
		
		meshNames = {}
		for meshGroup in fmdl.meshGroups:
			addMeshNames(meshGroup, meshNames)
		for i in range(len(fmdl.meshes)):
			mesh = fmdl.meshes[i]
			if mesh in meshNames:
				baseName = meshNames[mesh]
			else:
				baseName = "mesh"
			meshNames[mesh] = "%s %s" % (baseName, i)
		
		meshObjectIDs = {}
		for mesh in fmdl.meshes:
			meshObjectIDs[mesh] = importMesh(mesh, meshNames[mesh], fmdl, materialIDs, armatureObjectID, boneIDs)
		
		return meshObjectIDs
	
	def addMeshGroup(context, meshGroup, meshObjectIDs):
		if len(meshGroup.meshes) == 1:
			blenderMeshGroupObject = bpy.data.objects[meshObjectIDs[meshGroup.meshes[0]]]
		else:
			blenderMeshGroupObject = bpy.data.objects.new(meshGroup.name, None)
			context.scene.objects.link(blenderMeshGroupObject)
			
			for mesh in meshGroup.meshes:
				bpy.data.objects[meshObjectIDs[mesh]].parent = blenderMeshGroupObject
		
		meshGroupID = blenderMeshGroupObject.name
		for child in meshGroup.children:
			childID = addMeshGroup(context, child, meshObjectIDs)
			bpy.data.objects[childID].parent = bpy.data.objects[meshGroupID]
		
		return meshGroupID
	
	def importMeshTree(context, fmdl, meshObjectIDs, armatureObjectID, filename):
		rootMeshGroups = []
		for meshGroup in fmdl.meshGroups:
			if meshGroup.parent == None:
				rootMeshGroups.append(meshGroup)
		
		basename = os.path.basename(filename)
		position = basename.rfind('.')
		if position == -1:
			name = basename
		else:
			name = basename[:position]
		
		rootMeshGroup = FmdlFile.FmdlFile.MeshGroup()
		rootMeshGroup.name = name
		rootMeshGroup.parent = None
		rootMeshGroup.children = rootMeshGroups
		rootMeshGroup.meshes = []
		
		blenderMeshGroupID = addMeshGroup(context, rootMeshGroup, meshObjectIDs)
		
		if armatureObjectID != None:
			bpy.data.objects[armatureObjectID].parent = bpy.data.objects[blenderMeshGroupID]
		
		return blenderMeshGroupID
	
	
	
	if context.active_object == None:
		activeObjectID = None
	else:
		activeObjectID = bpy.data.objects.find(context.active_object.name)
		bpy.ops.object.mode_set(context.copy(), mode = 'OBJECT')
	
	
	
	baseDir = os.path.dirname(filename)
	textureSearchPath = [
		baseDir,
		os.path.dirname(baseDir),
		os.path.dirname(os.path.dirname(baseDir)),
		os.path.join(baseDir, 'Common'),
		os.path.join(os.path.dirname(baseDir), 'Common'),
		os.path.join(os.path.dirname(os.path.dirname(baseDir)), 'Common'),
		os.path.join(baseDir, 'Kit Textures'),
		os.path.join(os.path.dirname(baseDir), 'Kit Textures'),
		os.path.join(os.path.dirname(os.path.dirname(baseDir)), 'Kit Textures'),
	]
	materialIDs = importMaterials(fmdl, textureSearchPath)
	
	if len(fmdl.bones) > 0:
		(armatureObjectID, boneIDs) = importSkeleton(context, fmdl)
	else:
		(armatureObjectID, boneIDs) = (None, [])
	
	meshObjectIDs = importMeshes(context, fmdl, materialIDs, armatureObjectID, boneIDs)
	
	importMeshTree(context, fmdl, meshObjectIDs, armatureObjectID, filename)
	
	
	
	if activeObjectID != None:
		setActiveObject(context, bpy.data.objects[activeObjectID])


def exportFmdl(context):
	def exportMaterial(blenderMaterial, textureFmdlObjects):
		materialInstance = FmdlFile.FmdlFile.MaterialInstance()
		
		for slot in blenderMaterial.texture_slots:
			if slot == None:
				continue
			blenderTexture = slot.texture
			if blenderTexture not in textureFmdlObjects:
				path = blenderTexture.fmdl_texture_path.replace('\\', '/')
				texture = FmdlFile.FmdlFile.Texture()
				position = path.rfind('/')
				if position == -1:
					texture.filename = path
					texture.directory = ''
				else:
					texture.filename = path[position + 1:]
					texture.directory = path[:position + 1]
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
				if blenderMaterial not in blenderMaterials:
					blenderMaterials.append(blenderMaterial)
		
		materialInstances = []
		materialFmdlObjects = {}
		textureFmdlObjects = {}
		for blenderMaterial in blenderMaterials:
			materialInstance = exportMaterial(blenderMaterial, textureFmdlObjects)
			materialInstances.append(materialInstance)
			materialFmdlObjects[blenderMaterial] = materialInstance
		
		return (materialInstances, materialFmdlObjects)
	
	def exportBone(blenderBone):
		bone = FmdlFile.FmdlFile.Bone()
		bone.name = blenderBone.name
		# Fill in bone.boundingBox later
		
		if blenderBone.name in PesSkeletonData.bones:
			pesBone = PesSkeletonData.bones[blenderBone.name]
			bone.globalPosition = FmdlFile.FmdlFile.Vector4(
				pesBone["x"],
				pesBone["y"],
				pesBone["z"],
				1.0,
			)
			if pesBone["parent"] != None:
				pesParentBone = PesSkeletonData.bones[pesBone["parent"]]
				bone.localPosition = FmdlFile.FmdlFile.Vector4(
					pesParentBone["x"],
					pesParentBone["y"],
					pesParentBone["z"],
					0.0,
				)
			else:
				bone.localPosition = FmdlFile.FmdlFile.Vector4(
					pesBone["x"],
					pesBone["y"],
					pesBone["z"],
					0.0,
				)
			parentName = pesBone["parent"]
		else:
			(tailX, tailY, tailZ) = blenderBone.tail_local
			(headX, headY, headZ) = blenderBone.head_local
			bone.globalPosition = FmdlFile.FmdlFile.Vector4(
				tailX,
				tailZ,
				-tailY,
				1.0,
			)
			bone.localPosition = FmdlFile.FmdlFile.Vector4(
				headX,
				headZ,
				-headY,
				0.0,
			)
			if blenderBone.parent == None:
				parentName = None
			else:
				parentName = blenderBone.parent.name
		
		return (bone, parentName)
	
	def exportBones(blenderMeshObjects):
		blenderArmatures = []
		for blenderMeshObject in blenderMeshObjects:
			for modifier in blenderMeshObject.modifiers:
				if modifier.type == 'ARMATURE':
					blenderArmature = modifier.object.data
					if blenderArmature not in blenderArmatures:
						blenderArmatures.append(blenderArmature)
		
		bones = []
		bonesByName = {}
		boneParentNames = {}
		boneArmatureNames = {}
		for blenderArmature in blenderArmatures:
			for blenderBone in blenderArmature.bones:
				(bone, parentName) = exportBone(blenderBone)
				if bone.name in boneArmatureNames:
					raise InvalidFmdl("Bone '%s' present in multiple armatures '%s' and '%s'" % (
						bone.name,
						boneArmatureNames[boneFmdlObject.name],
						blenderArmature.name
					))
				
				bones.append(bone)
				bonesByName[bone.name] = bone
				boneParentNames[bone.name] = parentName
				boneArmatureNames[bone.name] = blenderArmature.name
		
		for bone in bones:
			parentName = boneParentNames[bone.name]
			if parentName is not None and parentName in bonesByName:
				parent = bonesByName[parentName]
				bone.parent = parent
				parent.children.append(bone)
		
		orderedBones = []
		def addOrderedBone(bone):
			if bone in orderedBones:
				return
			if bone.parent != None:
				addOrderedBone(bone.parent)
			orderedBones.append(bone)
		for bone in bones:
			addOrderedBone(bone)
		
		return (orderedBones, bonesByName)
	
	def exportVertices(blenderMeshObject, blenderColorLayer, uvLayerColor, uvLayerNormal, boneVector):
		blenderMesh = blenderMeshObject.data
		transformedBlenderMesh = blenderMesh.copy()
		transformedBlenderMesh.transform(blenderMeshObject.matrix_world)
		transformedBlenderMesh.calc_tangents(uvLayerColor)
		
		class Vertex:
			def __init__(self):
				self.position = None
				self.boneMapping = {}
				self.loops = []
		
		class Loop:
			def __init__(self):
				self.normal = None
				self.tangent = None
				self.color = None
				self.uv = []
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
				normalDotProduct = (
					self.normal.x * other.normal.x +
					self.normal.y * other.normal.y +
					self.normal.z * other.normal.z
				)
				if normalDotProduct < 0.999:
					return False
				# The tangent is based on the normal and UV map.
				# If the uvs are equal and the normals are approximately equal,
				# consider the tangents sufficiently equal, and recompute later.
				return True
			
			def add(self, other):
				self.loopIndices += other.loopIndices
				self.normal = self.normal.slerp(other.normal, 1.0 / len(self.loopIndices))
				#self.tangent = self.tangent.slerp(other.tangent, 1.0 / len(self.loopIndices))
		
		vertices = []
		for i in range(len(transformedBlenderMesh.vertices)):
			blenderVertex = transformedBlenderMesh.vertices[i]
			vertex = Vertex()
			vertex.position = FmdlFile.FmdlFile.Vector3(
				blenderVertex.co.x,
				blenderVertex.co.z,
				-blenderVertex.co.y,
			)
			for group in blenderVertex.groups:
				vertex.boneMapping[boneVector[group.group]] = group.weight
			vertices.append(vertex)
		
		for i in range(len(transformedBlenderMesh.loops)):
			blenderLoop = transformedBlenderMesh.loops[i]
			vertex = vertices[blenderLoop.vertex_index]
			
			loop = Loop()
			loop.normal = blenderLoop.normal
			loop.tangent = blenderLoop.tangent
			
			if blenderColorLayer != None:
				loop.color = [c for c in blenderColorLayer.data[i].color] + [1.0]
			loop.uv.append(FmdlFile.FmdlFile.Vector2(
				transformedBlenderMesh.uv_layers[uvLayerColor].data[i].uv[0],
				1.0 - transformedBlenderMesh.uv_layers[uvLayerColor].data[i].uv[1],
			))
			if uvLayerNormal != None:
				loop.uv.append(FmdlFile.FmdlFile.Vector2(
					transformedBlenderMesh.uv_layers[uvLayerNormal].data[i].uv[0],
					1.0 - transformedBlenderMesh.uv_layers[uvLayerNormal].data[i].uv[1],
				))
			loop.loopIndices = [i]
			
			found = False
			for otherLoop in vertex.loops:
				if otherLoop.matches(loop):
					otherLoop.add(loop)
					found = True
					break
			if not found:
				vertex.loops.append(loop)
		
		fmdlVertices = []
		fmdlVerticesByLoopIndex = {}
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
				fmdlVertex.tangent = FmdlFile.FmdlFile.Vector4(
					# TODO: This is definitely extremely broken.
					# Figure out what to do here properly.
					#loop.tangent.x,
					#loop.tangent.z,
					#-loop.tangent.y,
					0.0,
					0.0,
					0.0,
					1.0,
				)
				fmdlVertex.color = loop.color
				fmdlVertex.uv = loop.uv
				fmdlVertices.append(fmdlVertex)
				for loopIndex in loop.loopIndices:
					fmdlVerticesByLoopIndex[loopIndex] = fmdlVertex
		
		return (fmdlVertices, fmdlVerticesByLoopIndex)
	
	def exportMesh(blenderMeshObject, materialFmdlObjects, bonesByName):
		blenderMesh = blenderMeshObject.data
		name = blenderMeshObject.name
		
		loopTotals = [0 for i in range(len(blenderMesh.polygons))]
		blenderMesh.polygons.foreach_get("loop_total", loopTotals)
		if max(loopTotals) != 3:
			#
			# TODO: optionally triangulate
			#
			raise InvalidFmdl("Mesh '%s' contains non-triangle polygons." % name)
		
		vertexFields = FmdlFile.FmdlFile.VertexFields()
		vertexFields.hasNormal = True
		vertexFields.hasTangent = True
		
		if len(blenderMesh.vertex_colors) == 0:
			blenderColorLayer = None
			vertexFields.hasColor = False
		elif len(blenderMesh.vertex_colors) == 1:
			blenderColorLayer = blenderMesh.vertex_colors[0]
			vertexFields.hasColor = True
		else:
			raise InvalidFmdl("Mesh '%s' has more than one color layer." % name)
		
		if len(blenderMesh.materials) == 0:
			raise InvalidFmdl("Mesh '%s' does not have an associated material.")
		if len(blenderMesh.materials) > 1:
			raise InvalidFmdl("Mesh '%s' has multiple associated materials.")
		blenderMaterial = blenderMesh.materials[0]
		
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
			raise InvalidFmdl("Mesh '%s' does not have a primary UV map set.")
		if len(colorUvMaps) > 1:
			raise InvalidFmdl("Mesh '%s' has conflicting primary UV maps '%s' and '%s' set." % (colorUvMaps[0], colorUvMaps[1]))
		if len(normalUvMaps) == 0:
			raise InvalidFmdl("Mesh '%s' does not have a normals UV map set.")
		if len(normalUvMaps) > 1:
			raise InvalidFmdl("Mesh '%s' has conflicting normals UV maps '%s' and '%s' set." % (normalUvMaps[0], normalUvMaps[1]))
		
		uvLayerColor = colorUvMaps[0]
		vertexFields.uvCount = 1
		
		if normalUvMaps[0] == uvLayerColor:
			uvLayerNormal = None
		else:
			uvLayerNormal = normalUvMaps[0]
			vertexFields.uvCount += 1
		
		boneVector = [bonesByName[vertexGroup.name] for vertexGroup in blenderMeshObject.vertex_groups]
		if len(boneVector) > 0:
			vertexFields.hasBoneMapping = True
		
		(vertices, fmdlVerticesByLoopIndex) = exportVertices(blenderMeshObject, blenderColorLayer, uvLayerColor, uvLayerNormal, boneVector)
		
		faces = []
		for i in range(len(blenderMesh.polygons)):
			loopStart = blenderMesh.polygons[i].loop_start
			faces.append(FmdlFile.FmdlFile.Face(
				fmdlVerticesByLoopIndex[loopStart + 2],
				fmdlVerticesByLoopIndex[loopStart + 1],
				fmdlVerticesByLoopIndex[loopStart + 0]
			))
		
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
	
	def exportMeshGroupAncestors(blenderObject, meshFmdlObjects, rootObject, meshGroups, meshGroupFmdlObjects):
		if blenderObject in meshGroupFmdlObjects:
			return
		
		parentBlenderObject = blenderObject.parent
		while parentBlenderObject != None:
			if parentBlenderObject == rootObject:
				parentBlenderObject = None
			elif parentBlenderObject.type in ['MESH', 'EMPTY']:
				break
			else:
				parentBlenderObject = parentBlenderObject.parent
		
		if parentBlenderObject != None:
			exportMeshGroupAncestors(parentBlenderObject, meshFmdlObjects, rootObject, meshGroups, meshGroupFmdlObjects)
			parentMeshGroup = meshGroupFmdlObjects[parentBlenderObject]
		else:
			parentMeshGroup = None
		
		meshGroup = FmdlFile.FmdlFile.MeshGroup()
		meshGroup.name = blenderObject.name
		# Fill in meshGroup.boundingBox later
		meshGroup.visible = True
		
		if blenderObject.type == 'MESH':
			meshGroup.meshes.append(meshFmdlObjects[blenderObject])
		
		if parentMeshGroup != None:
			meshGroup.parent = parentMeshGroup
			parentMeshGroup.children.append(meshGroup)
		
		meshGroups.append(meshGroup)
		meshGroupFmdlObjects[blenderObject] = meshGroup
	
	def exportMeshGroups(blenderMeshObjects, meshFmdlObjects):
		blenderArmatureObjects = []
		for blenderMeshObject in blenderMeshObjects:
			for modifier in blenderMeshObject.modifiers:
				if modifier.type == 'ARMATURE':
					blenderArmatureObject = modifier.object
					if blenderArmatureObject not in blenderArmatureObjects:
						blenderArmatureObjects.append(blenderArmatureObject)
		if (
			len(blenderArmatureObjects) == 1 and
			blenderArmatureObjects[0].parent != None and
			blenderArmatureObjects[0].parent.parent == None
		):
			rootObject = blenderArmatureObjects[0].parent
		else:
			rootObject = None
		
		meshGroups = []
		meshGroupFmdlObjects = {}
		for blenderMeshObjects in meshFmdlObjects:
			exportMeshGroupAncestors(blenderMeshObjects, meshFmdlObjects, rootObject, meshGroups, meshGroupFmdlObjects)
		
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
	
	def calculateMeshBoundingBox(mesh):
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
	
	def calculateMeshGroupBoundingBox(meshGroup):
		boundingBoxes = []
		for mesh in meshGroup.meshes:
			boundingBox = calculateMeshBoundingBox(mesh)
			if boundingBox != None:
				boundingBoxes.append(boundingBox)
		for child in meshGroup.children:
			boundingBox = calculateMeshGroupBoundingBox(child)
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
				min(box.min.z for box in boundingBoxes),
				min(box.min.z for box in boundingBoxes),
				1.0
			),
			FmdlFile.FmdlFile.Vector4(
				max(box.max.x for box in boundingBoxes),
				max(box.max.z for box in boundingBoxes),
				max(box.max.z for box in boundingBoxes),
				1.0
			)
		)
		return meshGroup.boundingBox
	
	def calculateBoundingBoxes(meshGroups, bones, meshes):
		calculateBoneBoundingBoxes(bones, meshes)
		
		for meshGroup in meshGroups:
			if meshGroup.parent == None:
				calculateMeshGroupBoundingBox(meshGroup)
	
	if context.active_object == None:
		activeObjectID = None
	else:
		activeObjectID = bpy.data.objects.find(context.active_object.name)
		bpy.ops.object.mode_set(context.copy(), mode = 'OBJECT')
	
	
	
	blenderMeshObjects = []
	for object in context.scene.objects:
		if object.type == 'MESH':
			blenderMeshObjects.append(object)
	
	(materialInstances, materialFmdlObjects) = exportMaterials(blenderMeshObjects)
	
	(bones, bonesByName) = exportBones(blenderMeshObjects)
	
	meshFmdlObjects = {}
	for blenderMeshObject in blenderMeshObjects:
		mesh = exportMesh(blenderMeshObject, materialFmdlObjects, bonesByName)
		meshFmdlObjects[blenderMeshObject] = mesh
	
	meshGroups = exportMeshGroups(blenderMeshObjects, meshFmdlObjects)
	
	meshes = sortMeshes(meshGroups)
	
	calculateBoundingBoxes(meshGroups, bones, meshes)
	
	fmdlFile = FmdlFile.FmdlFile()
	fmdlFile.bones = bones
	fmdlFile.materialInstances = materialInstances
	fmdlFile.meshes = meshes
	fmdlFile.meshGroups = meshGroups
	
	
	
	if activeObjectID != None:
		setActiveObject(context, bpy.data.objects[activeObjectID])
	
	return fmdlFile
