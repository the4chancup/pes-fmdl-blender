from . import FmdlFile, PesSkeletonData
import numpy

#
# FMDL meshes have a maximum number of vertices and faces in them, and the
# bone groups they reference have a maximum number of bones in them. All these
# limits are strict enough to hit them frequently in practice.
#
# This extension will transparently cut any meshes that surpass those limits
# into multiple meshes that together contain the same faces and vertices in
# them. This will usually render identically as a single large mesh. This
# extension will also reassemble such a split mesh back into a single large
# mesh when importing.
#
# The extension will try to construct split meshes that, if viewed in an editor
# that cannot reassemble split meshes, look like reasonable meshes cut into
# pieces at reasonable points. Ideally, meshes split by this extension should
# approximate as well as possible the split that a human editor would make when
# trying to create a model that hits the mesh limits.
#
# Split meshes do not necessary render exactly as expected in all cases. The
# splitting logic creates split meshes that do not have their faces in the same
# order the original mesh did; this would not generally be possible while also
# constructing reasonable-looking split meshes. Because of this modified face
# order, meshes whose correct rendering depends on their face order, such as
# meshes whose shading relies on clever alpha blending tricks, may be adversely
# affected by the transformation. The mesh splitting logic also rearranges the
# order of the vertices in a mesh, but this is not expected to cause problems.
#
# Split meshes are stored using the following encoding:
#
# Each source mesh that was split into multiple component meshes is encoded in
# the fmdl file as a mesh group containing the component meshes. This mesh group
# does not have any children. The fmdl file contains a
# `Split-Mesh-Group: <groups>` extension header, where <groups> is a comma-
# separated list of mesh group IDs. Each mesh group marked using such an ID
# represents a single mesh in the source fmdl file. The fmdl file also contains
# the `X-FMDL-Extensions: mesh-splitting` feature extension header.
#
# A vertex in the source mesh may occur in multiple of its component split
# meshes. If meshes A and B are component split meshes of a single source mesh,
# and vertices X and Y are vertices of A and B respectively, X and Y describe
# the same vertex in the source mesh if and only if (1) X and Y are encoded
# using the same vertex byte encoding in the fmdl vertex buffer, except for the
# differences caused by A and B using a different bone group, and therefore
# encode the same bone mapping using a different bone index encoding; and
# (2) if X and Y are both the Nth vertex in their respective meshes to use that
# same vertex byte encoding. That is to say, if meshes A and B contain vertices
# F, G, H and F', G', H' respectively, in increasing vertex order, all of which
# are encoded using the same vertex byte encoding, then F and F' represent the
# same vertex in the source mesh, as do G and G', and H and H'.
#



#
# For each item, the hard limit is the maximum that can be saved in an fmdl
# file, and the soft limit is the limit a split-off submesh will try to stay
# below, as to ensure that editors without mesh splitting support have some
# room to work with.
#

BONE_LIMIT_HARD = 32
BONE_LIMIT_SOFT = 30

VERTEX_LIMIT_HARD = 65535
VERTEX_LIMIT_SOFT = 63000

FACE_LIMIT_HARD = 21845
FACE_LIMIT_SOFT = 20000



#
# Two vertices are encoding-identical if they have the same byte encoding in
# the fmdl vertex buffer, modulo bone indices in different bone groups.
# If a mesh contains encoding-identical vertices, each split submesh contains
# the entire set of these vertices in the same order. This allows the
# reconstruction to distinguish them, and interpret faces that refer to one of
# them.
#
def indistinguishableEncoding(encodedVertex, vertexFields):
	encoding = bytearray()
	if True:
		encoding += encodedVertex.position
	if vertexFields.hasNormal:
		encoding += encodedVertex.normal
	if vertexFields.hasColor:
		encoding += encodedVertex.color
	for i in range(4):
		if vertexFields.uvCount > i:
			encoding += encodedVertex.uv[i]
	if vertexFields.hasTangent:
		encoding += encodedVertex.tangent
	
	if vertexFields.hasBoneMapping:
		return (bytes(encoding), tuple(encodedVertex.boneMapping))
	else:
		return bytes(encoding)



#
# Sets of equipresent vertices are lists, which cannot be hashed.
# A container object for it CAN be hashed, and therefore stored in sets.
#
class VertexSet:
	def __init__(self, vertices):
		self.vertices = vertices

#
# Stores a face as a sequence of *encoded* vertices
#
class EncodedFace:
	def __init__(self, vertices):
		self.vertices = vertices

class StorableItems:
	def __init__(self):
		self.faces = set()
		self.looseVertices = set()

#
# Maintains, for each bone, the set of faces and the set of looseVertexSets
# that contain a bone that is a descendent of $bone.
#
class BoneDescendentStorableItems:
	def __init__(self, parentBones, encodedFaceIndices, looseVertexSets):
		self.itemsPerBone = {}
		
		# None functions as the root bone.
		self.itemsPerBone[None] = StorableItems()
		self.itemsPerBone[None].faces = set(encodedFaceIndices.keys())
		self.itemsPerBone[None].looseVertices = looseVertexSets.copy()
		if parentBones is not None:
			for bone in parentBones.keys():
				self.itemsPerBone[bone] = StorableItems()
			
			for face in encodedFaceIndices.keys():
				for vertex in face.vertices:
					for (bone, weight) in vertex.boneMapping:
						currentBone = bone
						while currentBone is not None:
							if face in self.itemsPerBone[currentBone].faces:
								break
							self.itemsPerBone[currentBone].faces.add(face)
							currentBone = parentBones[currentBone]
			
			for vertexSet in looseVertexSets:
				#
				# All vertices in a vertexSet have the same bone
				# mapping, so we can just take one at random.
				#
				vertex = vertexSet.vertices[0]
				for (bone, weight) in vertex.boneMapping:
					currentBone = bone
					while currentBone is not None:
						if vertexSet in self.itemsPerBone[currentBone].looseVertices:
							break
						self.itemsPerBone[currentBone].looseVertices.add(vertexSet)
						currentBone = parentBones[currentBone]
	
	def get(self, bone):
		items = StorableItems()
		items.faces = self.itemsPerBone[bone].faces.copy()
		items.looseVertices = self.itemsPerBone[bone].looseVertices.copy()
		return items
	
	def remove(self, storedItems):
		for key in self.itemsPerBone.keys():
			self.itemsPerBone[key].faces -= storedItems.faces
			self.itemsPerBone[key].looseVertices -= storedItems.looseVertices

#
# Vertex sequences with the same splitVertexKey need to preserve their relative
# order and sequentiality, in order not to break split vertex encoding.
#
def splitVertexKey(encodedVertex, vertexFields):
	if vertexFields.hasBoneMapping:
		return (encodedVertex.position, tuple(encodedVertex.boneMapping))
	else:
		return encodedVertex.position

#
# If a submesh of a mesh includes a vertex X, it also needs to include all
# vertices that have an identical bytestring encoding as X. Moreover, in order
# to not break split vertex encoding, it also needs to include all vertices with
# the same splitVertexKey(), which is a strictly weaker relation. This function
# partitions the vertices of a mesh using the transitive closure of this
# relation. Because the splitVertexKey() partitioning is strictly weaker than
# the identicalEncoding() relation, we can just partition by splitVertexKey().
#
def computeEquipresentVertexSets(mesh):
	equipresentVertices = {}
	#
	# output[vertexEncoding] stores a VertexSet for a _mutable_ list of
	# vertexEncodings, which will be filled in by the loop below.
	#
	output = {}
	
	for vertexEncoding in mesh.vertexEncoding:
		encoding = splitVertexKey(vertexEncoding, mesh.vertexFields)
		if encoding not in equipresentVertices:
			equipresentVertices[encoding] = [vertexEncoding]
			output[vertexEncoding] = VertexSet(equipresentVertices[encoding])
		else:
			equipresentVertices[encoding].append(vertexEncoding)
			output[vertexEncoding] = output[equipresentVertices[encoding][0]]
	
	return output

#
# Makes a list of Face objects referring to encoded vertices, and a set of
# equipresentVertices that do not occur in any faces.
#
def makeStorableItems(encodedVertices, equipresentVertices, faces):
	vertexEncoding = {}
	for encodedVertex in encodedVertices:
		vertexEncoding[encodedVertex.vertex] = encodedVertex
	
	equipresentVerticesRemaining = set(equipresentVertices.values())
	encodedFaces = {}
	for face in faces:
		encodedFace = EncodedFace([vertexEncoding[vertex] for vertex in face.vertices])
		encodedFaces[encodedFace] = len(encodedFaces)
		for encodedVertex in encodedFace.vertices:
			equipresentVerticesRemaining.discard(equipresentVertices[encodedVertex])
	
	return (encodedFaces, equipresentVerticesRemaining)

#
# Select a bone from which to construct a submesh.
# The submesh will consist of all storable items that reference a descendent
# bone of the selected bone, if possible; or a (hopefully connected and
# disjoint) fragment if not possible
#
def selectSubmeshBaseBone(parentBones, storableItemsPerBone):
	baseBoneLists = [
		[
			'sk_foot_l',
			'sk_foot_r',
			'sk_hand_l',
			'sk_hand_r',
			'skf_jaw',
		],
		parentBones.keys()
	]
	
	namedBones = {}
	for bone in parentBones.keys():
		namedBones[bone.name] = bone
	
	triedBones = set()
	for baseBoneList in baseBoneLists:
		queue = list(baseBoneList)
		while len(queue) > 0:
			boneEntry = queue[0]
			queue[0:1] = []
			
			if isinstance(boneEntry, str):
				if boneEntry not in namedBones:
					parentBoneName = PesSkeletonData.bones[boneEntry].renderParent
					queue.append(parentBoneName)
					continue
				bone = namedBones[boneEntry]
			else:
				bone = boneEntry
			
			if bone is None:
				continue
			if bone in triedBones:
				continue
			triedBones.add(bone)
			
			storableItems = storableItemsPerBone.get(bone)
			if len(storableItems.faces) == 0 and len(storableItems.looseVertices) == 0:
				queue.append(parentBones[bone])
				continue
			
			return bone
	
	return None

def fitsInSubmesh(storableItems, equipresentVertices, vertexFields):
	if len(storableItems.faces) > FACE_LIMIT_SOFT:
		return False
	equipresentVertices = set(equipresentVertices[vertex] for face in storableItems.faces for vertex in face.vertices) | storableItems.looseVertices
	if sum(len(vertexSet.vertices) for vertexSet in equipresentVertices) > VERTEX_LIMIT_SOFT:
		return False
	if vertexFields.hasBoneMapping:
		bones = set(bone for vertexSet in equipresentVertices for (bone, weight) in vertexSet.vertices[0].boneMapping)
		if len(bones) > BONE_LIMIT_SOFT:
			return False
	return True

def computeSortVector(storableItems, bone):
	#
	# Perform a principal component analysis on the set of vertices in
	# storableItems, and order vertices on distance along this vector.
	#
	encodedVertices = (
		  [vertex for face in storableItems.faces for vertex in face.vertices]
		+ [vertexSet.vertices[0] for vertexSet in storableItems.looseVertices]
	)
	coordinates = numpy.array([(v.vertex.position.x, v.vertex.position.y, v.vertex.position.z) for v in encodedVertices])
	coordinateMeans = numpy.mean(coordinates, axis = 0)
	coordinateDeviation = coordinates - coordinateMeans
	covariance = numpy.cov(coordinateDeviation.T)
	(eigenvalues, eigenvectors) = numpy.linalg.eig(covariance)
	
	maxIndex = 0
	for i in range(1, len(eigenvalues)):
		if eigenvalues[i] > eigenvalues[maxIndex]:
			maxIndex = i
	sortVector = eigenvectors.T[i]
	
	#
	# sortVector can have either polarity.
	# Have it point from the bone position, to the center of the vertex cloud.
	#
	if bone is None:
		bonePosition = (0, 0, 0)
	else:
		bonePosition = (bone.globalPosition.x, bone.globalPosition.y, bone.globalPosition.z)
	
	boneToCenter = tuple(coordinateMeans[i] - bonePosition[i] for i in range(len(bonePosition)))
	dotProduct = sum(boneToCenter[i] * sortVector[i] for i in range(len(boneToCenter)))
	if dotProduct < 0:
		sortVector = tuple(-sortVector[i] for i in range(len(sortVector)))
	else:
		sortVector = tuple(sortVector[i] for i in range(len(sortVector)))
	
	return sortVector

#
# Split off a subset of storable items into a new mesh object.
#
def buildSubmesh(mesh, parentBones, storableItemsPerBone, equipresentVertices, encodedFaceIndices):
	baseBone = selectSubmeshBaseBone(parentBones, storableItemsPerBone)
	storableItems = storableItemsPerBone.get(baseBone)
	
	if fitsInSubmesh(storableItems, equipresentVertices, mesh.vertexFields):
		#
		# Find the highest up ancestor bone that still fits a single submesh
		#
		while baseBone is not None:
			childBone = parentBones[baseBone]
			childStorableItems = storableItemsPerBone.get(childBone)
			if not fitsInSubmesh(childStorableItems, equipresentVertices, mesh.vertexFields):
				break
			baseBone = childBone
			storableItems = childStorableItems
		
		storedItems = storableItems
		selectedEquipresentVertices = set(equipresentVertices[vertex] for face in storedItems.faces for vertex in face.vertices) | storedItems.looseVertices
		if mesh.vertexFields.hasBoneMapping:
			selectedBones = set(bone for vertexSet in selectedEquipresentVertices for (bone, weight) in vertexSet.vertices[0].boneMapping)
		else:
			selectedBones = set()
	else:
		#
		# Build a fragment of the storable items.
		#
		selectedFaces = set()
		selectedLooseVertices = set()
		selectedBones = set()
		selectedEquipresentVertices = set()
		totalVertexCount = 0
		
		sortVector = computeSortVector(storableItems, baseBone)
		def vectorScore(encodedVertex):
			vector = (encodedVertex.vertex.position.x, encodedVertex.vertex.position.y, encodedVertex.vertex.position.z)
			return sum(vector[i] * sortVector[i] for i in range(len(vector)))
		
		for face in sorted(storableItems.faces, reverse = True, key = lambda face :
			max(vectorScore(v) for v in face.vertices)
		):
			if len(selectedFaces) >= FACE_LIMIT_SOFT:
				break
			
			addedBones = set()
			addedEquipresentVertices = set()
			addedVertexCount = 0
			for encodedVertex in face.vertices:
				equipresentVertex = equipresentVertices[encodedVertex]
				if (
					    equipresentVertex not in selectedEquipresentVertices
					and equipresentVertex not in addedEquipresentVertices
				):
					addedEquipresentVertices.add(equipresentVertex)
					addedVertexCount += len(equipresentVertex.vertices)
					for (bone, weight) in (encodedVertex.boneMapping or []):
						if bone not in selectedBones:
							addedBones.add(bone)
			
			if (
				    len(selectedBones) + len(addedBones) <= BONE_LIMIT_SOFT
				and totalVertexCount + addedVertexCount <= VERTEX_LIMIT_SOFT
			):
				selectedFaces.add(face)
				selectedBones |= addedBones
				selectedEquipresentVertices |= addedEquipresentVertices
				totalVertexCount += addedVertexCount
		
		for looseVertex in sorted(storableItems.looseVertices, reverse = True, key = lambda vertex : vectorScore(vertex)):
			if totalVertexCount >= VERTEX_LIMIT_SOFT:
				break
			
			encodedVertex = looseVertex.vertices[0]
			
			addedBones = set()
			for (bone, weight) in (encodedVertex.boneMapping or []):
				if bone not in selectedBones:
					addedBones.add(bone)
			addedVertexCount = len(looseVertex.vertices)
			
			if (
				    len(selectedBones) + len(addedBones) <= BONE_LIMIT_SOFT
				and totalVertexCount + addedVertexCount <= VERTEX_LIMIT_SOFT
			):
				selectedLooseVertices.add(looseVertex)
				selectedBones |= addedBones
				selectedEquipresentVertices.add(looseVertex)
				totalVertexCount += addedVertexCount
		
		storedItems = StorableItems()
		storedItems.faces = selectedFaces
		storedItems.looseVertices = selectedLooseVertices
	
	submesh = FmdlFile.FmdlFile.Mesh()
	submesh.materialInstance = mesh.materialInstance
	submesh.alphaEnum = mesh.alphaEnum
	submesh.shadowEnum = mesh.shadowEnum
	submesh.vertexFields = mesh.vertexFields
	submesh.extensionHeaders = mesh.extensionHeaders.copy()
	submesh.boneGroup = FmdlFile.FmdlFile.BoneGroup()
	submesh.boneGroup.bones = [bone for bone in mesh.boneGroup.bones if bone in selectedBones]
	submesh.vertexEncoding = [vertex for vertexSet in selectedEquipresentVertices for vertex in vertexSet.vertices]
	submesh.vertices = [encodedVertex.vertex for encodedVertex in submesh.vertexEncoding]
	submesh.faces = [
		FmdlFile.FmdlFile.Face(*(encodedVertex.vertex for encodedVertex in face.vertices))
		for face in sorted(storedItems.faces, key = lambda face : encodedFaceIndices[face])
	]
	
	return (submesh, storedItems)

#
# Splits a mesh into a collection of submeshes that each fit within an fmdl
# mesh object.
#
def splitMesh(mesh, parentBones, descendentBones):
	equipresentVertices = computeEquipresentVertexSets(mesh)
	(encodedFaceIndices, looseVertexSets) = makeStorableItems(mesh.vertexEncoding, equipresentVertices, mesh.faces)
	
	storableItemsPerBone = BoneDescendentStorableItems(parentBones if mesh.vertexFields.hasBoneMapping else None, encodedFaceIndices, looseVertexSets)
	
	submeshes = []
	while len(storableItemsPerBone.get(None).faces) > 0 or len(storableItemsPerBone.get(None).looseVertices) > 0:
		(submesh, storedItems) = buildSubmesh(mesh, parentBones, storableItemsPerBone, equipresentVertices, encodedFaceIndices)
		storableItemsPerBone.remove(storedItems)
		submeshes.append(submesh)
	
	return submeshes

#
# Compute the effective parent bone for each bone in the model, used for
# splitting a mesh into meaningful submeshes.
# The effective parent bone is based on the bone parent stored in the model,
# extended with PesSkeletonData if necessary, transitively extended, and
# edited if necessary to ensure that there are no parent loops.
#
def computeParentBones(bones):
	namedBones = {}
	for bone in bones:
		namedBones[bone.name] = bone
	
	parents = {}
	for bone in bones:
		if bone.parent != None:
			parent = bone.parent
		elif bone.name in PesSkeletonData.bones:
			parentName = PesSkeletonData.bones[bone.name].renderParent
			while parentName != None and parentName not in namedBones:
				parentName = PesSkeletonData.bones[parentName].renderParent
			if parentName is None:
				parent = None
			else:
				parent = namedBones[parentName]
		else:
			parent = None
		
		if parent != None:
			#
			# Check for a parent loop
			#
			ancestor = parent
			while ancestor != None and ancestor != bone:
				if ancestor in parents:
					ancestor = parents[ancestor]
				else:
					ancestor = None
			if ancestor != None:
				parent = None
		
		parents[bone] = parent
	
	#
	# Invert the chest->belly->hip bone structure to make sk_chest
	# the effective root bone. This avoids strange geometries in
	# the common case where the shirt is in a separate mesh.
	#
	names = ['sk_chest', 'sk_belly', 'dsk_hip']
	invertChain = [namedBones[name] for name in names if name in namedBones]
	isChain = True
	for i in range(len(invertChain)):
		if i == len(invertChain) - 1:
			if parents[invertChain[i]] is not None:
				isChain = False
				break
		else:
			if parents[invertChain[i]] != invertChain[i + 1]:
				isChain = False
				break
	if isChain:
		for i in range(len(invertChain)):
			if i == 0:
				parents[invertChain[i]] = None
			else:
				parents[invertChain[i]] = invertChain[i - 1]
	
	return parents

def computeDescendentBones(parentBones):
	childBones = {}
	for (child, parent) in parentBones.items():
		if parent not in childBones:
			childBones[parent] = set()
		childBones[parent].add(child)
	
	descendentBones = {}
	def descendents(bone, descendentBones):
		if bone in descendentBones:
			return descendentBones[bone]
		if bone not in childBones:
			descendentBones[bone] = set()
			return descendentBones[bone]
		descendentSet = childBones[bone].copy()
		for child in childBones[bone]:
			descendentSet |= descendents(child, descendentBones)
		descendentBones[bone] = descendentSet
		return descendentBones[bone]
	for bone in parentBones.keys():
		descendents(bone, descendentBones)
	
	return descendentBones

def meshNeedsSplitting(mesh):
	return (
		   len(mesh.boneGroup.bones) > BONE_LIMIT_HARD
		or len(mesh.vertices) > VERTEX_LIMIT_HARD
		or len(mesh.faces) > FACE_LIMIT_HARD
	)

def encodeFmdlSplitMeshes(fmdl):
	fmdl.precomputeVertexEncoding()
	
	didSplitFmdl = False
	parentBones = computeParentBones(fmdl.bones)
	descendentBones = computeDescendentBones(parentBones)
	replacedMeshes = {}
	
	output = FmdlFile.FmdlFile()
	output.bones = fmdl.bones
	output.materialInstances = fmdl.materialInstances
	output.extensionHeaders = fmdl.extensionHeaders.copy()
	output.meshes = []
	for mesh in fmdl.meshes:
		if not meshNeedsSplitting(mesh):
			output.meshes.append(mesh)
			continue
		
		didSplitFmdl = True
		meshes = splitMesh(mesh, parentBones, descendentBones)
		output.meshes += meshes
		replacedMeshes[mesh] = meshes
	
	if not didSplitFmdl:
		return fmdl
	
	meshGroupMap = {}
	for meshGroup in fmdl.meshGroups:
		encodedMeshGroup = FmdlFile.FmdlFile.MeshGroup()
		output.meshGroups.append(encodedMeshGroup)
		meshGroupMap[meshGroup] = encodedMeshGroup
	for meshGroup in fmdl.meshGroups:
		encodedMeshGroup = meshGroupMap[meshGroup]
		encodedMeshGroup.name = meshGroup.name
		encodedMeshGroup.boundingBox = meshGroup.boundingBox
		encodedMeshGroup.visible = meshGroup.visible
		if meshGroup.parent is None:
			encodedMeshGroup.parent = None
		else:
			encodedMeshGroup.parent = meshGroupMap[meshGroup.parent]
		encodedMeshGroup.children = []
		for child in meshGroup.children:
			encodedMeshGroup.children.append(meshGroupMap[child])
		encodedMeshGroup.meshes = []
		for mesh in meshGroup.meshes:
			if mesh in replacedMeshes:
				newMeshGroup = FmdlFile.FmdlFile.MeshGroup()
				newMeshGroup.name = 'split-mesh'
				newMeshGroup.boundingBox = meshGroup.boundingBox
				newMeshGroup.visible = meshGroup.visible
				newMeshGroup.parent = encodedMeshGroup
				encodedMeshGroup.children.append(newMeshGroup)
				newMeshGroup.meshes = replacedMeshes[mesh]
				newMeshGroup.extensionHeaders = { 'Split-Mesh-Groups' }
				output.meshGroups.append(newMeshGroup)
			else:
				encodedMeshGroup.meshes.append(mesh)
	
	if 'X-FMDL-Extensions' not in output.extensionHeaders:
		output.extensionHeaders['X-FMDL-Extensions'] = []
	output.extensionHeaders['X-FMDL-Extensions'].append("mesh-splitting")
	
	return output



def combineMesh(outputMesh, inputMesh, mergedEncodedVertices):
	vertexEncodings = {}
	encodingIndices = {}
	
	for encodedVertex in inputMesh.vertexEncoding:
		encoding = indistinguishableEncoding(encodedVertex, outputMesh.vertexFields)
		if encoding not in encodingIndices:
			encodingIndices[encoding] = 0
		index = encodingIndices[encoding]
		encodingIndices[encoding] += 1
		
		if encoding not in mergedEncodedVertices:
			mergedEncodedVertices[encoding] = []
		if index < len(mergedEncodedVertices[encoding]):
			replacement = mergedEncodedVertices[encoding][index]
		else:
			mergedEncodedVertices[encoding].append(encodedVertex)
			outputMesh.vertexEncoding.append(encodedVertex)
			outputMesh.vertices.append(encodedVertex.vertex)
			replacement = encodedVertex
		
		vertexEncodings[encodedVertex.vertex] = replacement
	
	for face in inputMesh.faces:
		outputMesh.faces.append(FmdlFile.FmdlFile.Face(
			*(vertexEncodings[vertex].vertex for vertex in face.vertices)
		))

def combineMeshes(meshes, bones):
	output = FmdlFile.FmdlFile.Mesh()
	output.materialInstance = meshes[0].materialInstance
	output.alphaEnum = meshes[0].alphaEnum
	output.shadowEnum = meshes[0].shadowEnum
	output.vertexFields = meshes[0].vertexFields
	output.extensionHeaders = meshes[0].extensionHeaders.copy()
	
	output.vertexEncoding = []
	output.vertices = []
	output.faces = []
	
	#
	# Maintain, for each indistinguishableEncoding, the sequence of
	# encodedVertices in the outpush mesh using this encoding.
	#
	mergedEncodedVertices = {}
	for mesh in meshes:
		combineMesh(output, mesh, mergedEncodedVertices)
	
	output.boneGroup = FmdlFile.FmdlFile.BoneGroup()
	if output.vertexFields.hasBoneMapping:
		selectedBones = set(bone for encodedVertex in output.vertexEncoding for (bone, weight) in encodedVertex.boneMapping)
		output.boneGroup.bones = [bone for bone in bones if bone in selectedBones]
	return output

def decodeFmdlSplitMeshes(fmdl):
	if fmdl.extensionHeaders == None or "mesh-splitting" not in fmdl.extensionHeaders['x-fmdl-extensions']:
		return fmdl
	splitMeshes = {}
	for meshGroup in fmdl.meshGroups:
		if 'split-mesh-groups' in meshGroup.extensionHeaders:
			for mesh in meshGroup.meshes:
				splitMeshes[mesh] = meshGroup
	combinedMeshes = {}
	
	if len(splitMeshes) == 0:
		return fmdl
	
	output = FmdlFile.FmdlFile()
	output.bones = fmdl.bones
	output.materialInstances = fmdl.materialInstances
	output.extensionHeaders = fmdl.extensionHeaders
	output.meshes = []
	for mesh in fmdl.meshes:
		if mesh in splitMeshes:
			splitMeshGroup = splitMeshes[mesh]
			if splitMeshGroup not in combinedMeshes:
				combinedMesh = combineMeshes(splitMeshGroup.meshes, output.bones)
				output.meshes.append(combinedMesh)
				combinedMeshes[splitMeshGroup] = combinedMesh
		else:
			output.meshes.append(mesh)
	
	meshGroupMap = {}
	for meshGroup in fmdl.meshGroups:
		if meshGroup in combinedMeshes:
			continue
		
		encodedMeshGroup = FmdlFile.FmdlFile.MeshGroup()
		output.meshGroups.append(encodedMeshGroup)
		meshGroupMap[meshGroup] = encodedMeshGroup
	for meshGroup in fmdl.meshGroups:
		if meshGroup in combinedMeshes:
			continue
		
		encodedMeshGroup = meshGroupMap[meshGroup]
		encodedMeshGroup.name = meshGroup.name
		encodedMeshGroup.boundingBox = meshGroup.boundingBox
		encodedMeshGroup.visible = meshGroup.visible
		encodedMeshGroup.meshes = meshGroup.meshes.copy()
		if meshGroup.parent is None:
			encodedMeshGroup.parent = None
		else:
			encodedMeshGroup.parent = meshGroupMap[meshGroup.parent]
		encodedMeshGroup.children = []
		for child in meshGroup.children:
			if child in combinedMeshes:
				encodedMeshGroup.meshes.append(combinedMeshes[child])
			else:
				encodedMeshGroup.children.append(meshGroupMap[child])
	
	return output
