from . import FmdlFile

#
# FMDL files store mesh geometry as vertices, and faces that are sequences of
# vertices.
#
# Blender, and many other mesh editors, support a richer notion of geometry,
# consisting of vertices, faces, and loops. A vertex is a combination of a
# position and position transformation behavior (in FMDL context: vertex
# position, and bone mapping), and a loop is a vertex as it occurs in a 
# particular face, adding rendering information such as normals, tangents,
# colors, and UV coordinates. Faces are a sequence of loops, not a sequence of
# vertices.
#
# If a vertex is rendered in different ways in different faces it occurs in,
# the vertex/face/loop geometry expresses this as a single vertex with multiple
# different loops; the vertex/face geometry would express multiple different
# vertices with identical position and transformation behavior instead. The
# advantage of vertex/face/loop geometry while editing a mesh is that the
# different loops making up a vertex can be edited as a unit, being able to be
# moved and transformed and such as a unit; whereas the vertex/face geometry
# would make it easy to accidentally move only one loop of a vertex, and create
# an inconsistent geometry thereby.
#
# The FMDL format natively stores vertex/face geometry only. This module
# implements a nonstandard FMDL encoding, compatible with native FMDL, that can
# preserve the vertex/loop relation. This information is encoded in the order
# of different vertices in a mesh.
#
# The encoding is defined as follows:
#
# Two vertices in a mesh of an FMDL file are considered *topologically
# equivalent* if they have the same vertex position, bone indices and bone
# weights. The values are compared as byte sequences as they are stored in the
# FMDL vertex buffer.
#
# The *nontopological encoding* of a vertex in an FMDL file is a summary of all
# vertex data stored in the FMDL file other than the three values that determine
# topological equivalence. It consists of the concatenation of the byte
# sequences encoding these vertex data points, in order of increasing data point
# type enum. For currently known FMDL versions, those are (in order) the vertex
# normal, color, UV coordinates in increasing order, and tangent.
#
# If vertices X and Y are topologically equivalent, X is considered less than Y,
# denoted X < Y, if the nontopological encoding of X is strictly less than the
# nontopological order of Y, in lexicographical order. X < Y is not defined when
# X and Y are not topologically equivalent.
#
# The vertex/loop relation is encoded as follows: two vertices X and Y in a mesh
# of an FMDL file are loops of the same vertex if and only if:
# - X and Y are topolotically equivalent; and
# - X < Y; and
# - vertex Y comes immediately after vertex X in the vertex buffer. That is, the
#   vertex index of Y is 1 + the vertex index of X.
#
# A mesh consisting of vertex/face/loop geometry can be stored using this
# encoding by first making a list of all vertices and loops in the geometry,
# and computing the FMDL bytewise encoding of each loop; collapsing identical
# loops for a vertex to a single loop; ordering the different loops of a vertex
# in order of increasing nontopological encoding; ordering different vertices
# that happen to be topologically equivalent in order of nonincreasing
# topological encoding, to avoid accidentally combining distinct vertices;
# and then adding these vertices to the FMDL vertex buffer in such a way that
# the loops making up a vertex make a contiguous block respecting this ordering.
#
# FMDL files whose vertex buffers implement vertex/loop structure are marked by
# the `X-FMDL-Extensions: vertex-loop-preservation` extension header.
#

def topologicalKey(encodedVertex, vertexFields):
	if vertexFields.hasBoneMapping:
		return (encodedVertex.position, tuple(encodedVertex.boneMapping))
	else:
		return encodedVertex.position

def nontopologicalEncoding(encodedVertex, vertexFields):
	encoding = bytearray()
	if vertexFields.hasNormal:
		encoding += encodedVertex.normal
	if vertexFields.hasColor:
		encoding += encodedVertex.color
	for i in range(4):
		if vertexFields.uvCount > i:
			encoding += encodedVertex.uv[i]
	if vertexFields.hasTangent:
		encoding += encodedVertex.tangent
	return bytes(encoding)

def replaceFaceVertices(faces, replacedVertices):
	return [
		FmdlFile.FmdlFile.Face(*[
			(replacedVertices[vertex] if vertex in replacedVertices else vertex) for vertex in face.vertices
		]) for face in faces
	]

#
# Consider all FMDL vertices to be loops of the same vertex when they share a
# position object pointer.
#
def encodeMeshVertexLoopPreservation(mesh):
	#
	# Map from topological keys to lists of position objects
	#
	topologicallyEquivalentVertices = {}
	#
	# Map from position objects to lists of encoded vertices
	#
	splitVertices = {}
	
	for encodedVertex in mesh.vertexEncoding:
		key = topologicalKey(encodedVertex, mesh.vertexFields)
		
		if encodedVertex.vertex.position not in splitVertices:
			splitVertices[encodedVertex.vertex.position] = []
			
			if key not in topologicallyEquivalentVertices:
				topologicallyEquivalentVertices[key] = []
			topologicallyEquivalentVertices[key].append(encodedVertex.vertex.position)
		splitVertices[encodedVertex.vertex.position].append(encodedVertex)
	
	#
	# Sort splitVertices by nontopological encoding, and remove duplicates.
	#
	replacedVertices = {}
	for key in splitVertices:
		loops = {}
		for encodedVertex in splitVertices[key]:
			encoding = nontopologicalEncoding(encodedVertex, mesh.vertexFields)
			if encoding in loops:
				replacedVertices[encodedVertex.vertex] = loops[encoding].vertex
			else:
				loops[encoding] = encodedVertex
		splitVertices[key] = [loops[encoding] for encoding in sorted(loops.keys())]
	
	#
	# Sort topologicallyEquivalentVertices by nontopological encoding of
	# the first element, in descending order.
	#
	for (key, positions) in topologicallyEquivalentVertices.items():
		topologicallyEquivalentVertices[key] = sorted(positions, reverse = True, key = (
			lambda position : nontopologicalEncoding(splitVertices[position][0], mesh.vertexFields)
		))
	
	encodedVertices = []
	addedTopologicalKeys = set()
	for encodedVertex in mesh.vertexEncoding:
		key = topologicalKey(encodedVertex, mesh.vertexFields)
		if key not in addedTopologicalKeys:
			addedTopologicalKeys.add(key)
			
			for position in topologicallyEquivalentVertices[key]:
				encodedVertices += splitVertices[position]
	
	output = FmdlFile.FmdlFile.Mesh()
	output.boneGroup = mesh.boneGroup
	output.materialInstance = mesh.materialInstance
	output.alphaEnum = mesh.alphaEnum
	output.shadowEnum = mesh.shadowEnum
	output.vertexFields = mesh.vertexFields
	output.vertices = [encodedVertex.vertex for encodedVertex in encodedVertices]
	output.faces = replaceFaceVertices(mesh.faces, replacedVertices)
	output.vertexEncoding = encodedVertices
	output.extensionHeaders = mesh.extensionHeaders.copy()
	
	return output

def encodeFmdlVertexLoopPreservation(fmdl):
	fmdl.precomputeVertexEncoding()
	
	output = FmdlFile.FmdlFile()
	output.bones = fmdl.bones
	output.materialInstances = fmdl.materialInstances
	output.meshes = []
	meshMap = {}
	for mesh in fmdl.meshes:
		encodedMesh = encodeMeshVertexLoopPreservation(mesh)
		output.meshes.append(encodedMesh)
		meshMap[mesh] = encodedMesh
	output.meshGroups = []
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
		if meshGroup.parent == None:
			encodedMeshGroup.parent = None
		else:
			encodedMeshGroup.parent = meshGroupMap[meshGroup.parent]
		encodedMeshGroup.children = []
		for child in meshGroup.children:
			encodedMeshGroup.children.append(meshGroupMap[child])
		encodedMeshGroup.meshes = []
		for mesh in meshGroup.meshes:
			encodedMeshGroup.meshes.append(meshMap[mesh])
	output.extensionHeaders = {}
	for (key, value) in fmdl.extensionHeaders.items():
		output.extensionHeaders[key] = value[:]
	if 'X-FMDL-Extensions' not in output.extensionHeaders:
		output.extensionHeaders['X-FMDL-Extensions'] = []
	output.extensionHeaders['X-FMDL-Extensions'].append("vertex-loop-preservation")
	return output



def decodeMeshVertexLoopPreservation(mesh):
	vertexEncoding = []
	vertices = []
	replacedVertices = {}
	
	previousEncodedVertex = None
	for encodedVertex in mesh.vertexEncoding:
		if (
			       previousEncodedVertex != None
			and    topologicalKey(encodedVertex, mesh.vertexFields)
			    == topologicalKey(previousEncodedVertex, mesh.vertexFields)
			and    nontopologicalEncoding(previousEncodedVertex, mesh.vertexFields)
			    <  nontopologicalEncoding(encodedVertex, mesh.vertexFields)
		):
			vertex = FmdlFile.FmdlFile.Vertex()
			vertex.position = previousEncodedVertex.vertex.position
			vertex.normal = encodedVertex.vertex.normal
			vertex.tangent = encodedVertex.vertex.tangent
			vertex.color = encodedVertex.vertex.color
			vertex.boneMapping = previousEncodedVertex.vertex.boneMapping
			vertex.uv = encodedVertex.vertex.uv[:]
			
			encoding = FmdlFile.FmdlFile.VertexEncoding()
			encoding.vertex = vertex
			encoding.position = encodedVertex.position
			encoding.normal = encodedVertex.normal
			encoding.tangent = encodedVertex.tangent
			encoding.color = encodedVertex.color
			encoding.boneMapping = encodedVertex.boneMapping
			encoding.uv = encodedVertex.uv[:]
			
			vertexEncoding.append(encoding)
			vertices.append(vertex)
			replacedVertices[encodedVertex.vertex] = vertex
			previousEncodedVertex = encoding
		else:
			vertexEncoding.append(encodedVertex)
			vertices.append(encodedVertex.vertex)
			previousEncodedVertex = encodedVertex
	
	output = FmdlFile.FmdlFile.Mesh()
	output.boneGroup = mesh.boneGroup
	output.materialInstance = mesh.materialInstance
	output.alphaEnum = mesh.alphaEnum
	output.shadowEnum = mesh.shadowEnum
	output.vertexFields = mesh.vertexFields
	output.vertices = vertices
	output.faces = replaceFaceVertices(mesh.faces, replacedVertices)
	output.vertexEncoding = vertexEncoding
	output.extensionHeaders = mesh.extensionHeaders.copy()
	
	return output

def decodeFmdlVertexLoopPreservation(fmdl):
	if fmdl.extensionHeaders == None or "vertex-loop-preservation" not in fmdl.extensionHeaders['x-fmdl-extensions']:
		return fmdl
	
	output = FmdlFile.FmdlFile()
	output.bones = fmdl.bones
	output.materialInstances = fmdl.materialInstances
	output.meshes = []
	meshMap = {}
	for mesh in fmdl.meshes:
		encodedMesh = decodeMeshVertexLoopPreservation(mesh)
		output.meshes.append(encodedMesh)
		meshMap[mesh] = encodedMesh
	output.meshGroups = []
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
		if meshGroup.parent == None:
			encodedMeshGroup.parent = None
		else:
			encodedMeshGroup.parent = meshGroupMap[meshGroup.parent]
		encodedMeshGroup.children = []
		for child in meshGroup.children:
			encodedMeshGroup.children.append(meshGroupMap[child])
		encodedMeshGroup.meshes = []
		for mesh in meshGroup.meshes:
			encodedMeshGroup.meshes.append(meshMap[mesh])
	return output
