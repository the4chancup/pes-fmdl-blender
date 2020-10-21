import math
from struct import pack, pack_into, unpack, unpack_from

class InvalidFmdl(Exception):
	pass

class FmdlContainer:
	MAGIC = b'FMDL'
	VERSION_2_03 = 0x4001eb85
	
	SECTION0_BLOCK_ENTRY_SIZES = {
		0: 48,
		1: 8,
		2: 32,
		3: 48,
		4: 16,
		5: 68,
		6: 4,
		7: 4,
		8: 4,
		9: 8,
		10: 8,
		11: 4,
		12: 8,
		13: 32,
		14: 16,
		16: 16,
		17: 8,
		18: 8,
		20: 128,
	}
	
	def __init__(self):
		self.version = self.VERSION_2_03
		self.segment0Blocks = {}
		self.segment1Blocks = {}
	
	def readStream(self, stream):
		header = bytearray(56)
		if stream.readinto(header) != len(header):
			raise InvalidFmdl("Incomplete header")
		(
			magic,
			version,
			descriptorsOffset,
			section0Bitmap,
			section1Bitmap,
			section0BlockCount,
			section1BlockCount,
			section0Offset,
			section0Length,
			section1Offset,
			section1Length,
		) = unpack('< 4s I Q QQ II II II', header)
		
		if magic != self.MAGIC:
			raise InvalidFmdl("Unexpected magic number")
		
		self.version = version
		
		stream.seek(descriptorsOffset)
		
		section0Descriptors = []
		for i in range(section0BlockCount):
			descriptor = bytearray(8)
			if stream.readinto(descriptor) != len(descriptor):
				raise InvalidFmdl("Incomplete block descriptor")
			(
				blockID,
				entryCount,
				blockOffset,
			) = unpack('< H H I', descriptor)
			section0Descriptors.append((blockID, entryCount, blockOffset))
		
		section1Descriptors = []
		for i in range(section1BlockCount):
			descriptor = bytearray(12)
			if stream.readinto(descriptor) != len(descriptor):
				raise InvalidFmdl("Incomplete block descriptor")
			(
				blockID,
				blockOffset,
				length,
			) = unpack('< I I I', descriptor)
			section1Descriptors.append((blockID, blockOffset, length))
		
		for (blockID, entryCount, sectionOffset) in section0Descriptors:
			if blockID not in self.SECTION0_BLOCK_ENTRY_SIZES:
				continue
			entrySize = self.SECTION0_BLOCK_ENTRY_SIZES[blockID]
			
			if blockID in self.segment0Blocks:
				raise InvalidFmdl("Duplicate segment 0 block %d" % blockID)
			
			stream.seek(sectionOffset + section0Offset)
			
			block = []
			for i in range(entryCount):
				entry = bytearray(entrySize)
				if stream.readinto(entry) != len(entry):
					raise InvalidFmdl("Unexpected end of file reading section 0 block %d entry" % blockID)
				block.append(entry)
			self.segment0Blocks[blockID] = block
		
		stream.seek(0, 2)
		fileLength = stream.tell()
		
		for (blockID, sectionOffset, length) in section1Descriptors:
			if blockID in self.segment1Blocks:
				raise InvalidFmdl("Duplicate segment 1 block %d" % blockID)
			
			# These block lengths are occasionally set to slightly wrong values.
			# Interpret them liberally.
			remainingLength = fileLength - (sectionOffset + section1Offset)
			if length > remainingLength or blockID == 3:
				length = remainingLength
			
			stream.seek(sectionOffset + section1Offset)
			
			block = bytearray(length)
			if stream.readinto(block) != len(block):
				raise InvalidFmdl("Unexpected end of file reading section 1 block %d" % blockID)
				pass
			self.segment1Blocks[blockID] = block
	
	def readFile(self, filename):
		with open(filename, 'rb') as stream:
			self.readStream(stream)
	
	def writeStream(self, stream):
		section0Bitmap = 0
		section1Bitmap = 0
		
		section0Descriptors = []
		section1Descriptors = []
		
		section0Blocks = []
		section1Blocks = []
		
		offset = 0
		for i in range(64):
			if i not in self.segment0Blocks:
				continue
			
			entries = self.segment0Blocks[i]
			block = bytearray(0).join(entries)
			descriptor = pack('< H H I', i, len(entries), offset)
			if len(block) % 16:
				# This is more padding than used by some PES fmdl files, but certainly safe.
				padding = 16 - (len(block) % 16)
				block += bytearray(padding)
			
			section0Bitmap |= (1 << i)
			section0Descriptors.append(descriptor)
			section0Blocks.append(block)
			offset += len(block)
		section0Length = offset
		if section0Length % 16:
			padding = 16 - (section0Length % 16)
			section0Blocks.append(bytearray(padding))
			section0Length += padding
		
		offset = 0
		for i in range(64):
			if i not in self.segment1Blocks:
				continue
			
			block = self.segment1Blocks[i]
			descriptor = pack('< I I I', i, offset, len(block))
			
			section1Bitmap |= (1 << i)
			section1Descriptors.append(descriptor)
			section1Blocks.append(block)
			offset += len(block)
		section1Length = offset
		
		descriptors = bytearray(0).join(section0Descriptors + section1Descriptors)
		if len(descriptors) % 16:
			padding = 16 - (len(descriptors) % 16)
			descriptors += bytearray(padding)
		
		headerSize = 64
		section0Offset = headerSize + len(descriptors)
		section1Offset = section0Offset + section0Length
		
		header = pack('< 4s I Q QQ II II II Q',
			self.MAGIC,
			self.version,
			headerSize,
			section0Bitmap,
			section1Bitmap,
			len(section0Descriptors),
			len(section1Descriptors),
			section0Offset,
			section0Length,
			section1Offset,
			section1Length,
			0,
		)
		
		totalContent = [header] + [descriptors] + section0Blocks + section1Blocks
		for chunk in totalContent:
			stream.write(chunk)
	
	def writeFile(self, filename):
		with open(filename, 'wb') as stream:
			self.writeStream(stream)

class FmdlFile:
	class Vector2:
		def __init__(self):
			self.u = None
			self.v = None
		
		def __init__(self, u, v):
			self.u = u
			self.v = v
	
	class Vector3:
		def __init__(self):
			self.x = None
			self.y = None
			self.z = None
		
		def __init__(self, x, y, z):
			self.x = x
			self.y = y
			self.z = z
	
	class Vector4:
		def __init__(self):
			self.x = None
			self.y = None
			self.z = None
			self.w = None
		
		def __init__(self, x, y, z, w):
			self.x = x
			self.y = y
			self.z = z
			self.w = w
	
	class BoundingBox:
		def __init__(self):
			self.min = None
			self.max = None
		
		def __init__(self, min, max):
			self.min = min
			self.max = max
	
	class Bone:
		def __init__(self):
			self.name = None
			self.parent = None
			self.children = []
			self.boundingBox = None
			#
			# The names of these two fields are definitely misleading.
			# Their exact semantics seem to vary across different
			# games using FMDL, and even across different bones in the
			# same model. Caveat lector.
			#
			self.localPosition = None
			self.globalPosition = None
	
	class BoneGroup:
		def __init__(self):
			self.bones = []
	
	class Texture:
		def __init__(self):
			self.filename = None
			self.directory = None
	
	class MaterialInstance:
		def __init__(self):
			self.name = None
			self.technique = None
			self.shader = None
			self.textures = []
			self.parameters = []
	
	class Vertex:
		def __init__(self):
			self.position = None
			self.normal = None
			self.tangent = None
			self.color = None
			self.boneMapping = None
			self.uv = []
	
	class Face:
		def __init__(self, v1, v2, v3):
			self.vertices = [v1, v2, v3]
	
	class VertexFields:
		def __init__(self):
			self.hasNormal = False
			self.hasTangent = False
			self.hasColor = False
			self.hasBoneMapping = False
			self.uvCount = 0
			self.uvEqualities = {}
	
	class VertexEncoding:
		def __init__(self):
			self.vertex = None
			self.position = None
			self.normal = None
			self.tangent = None
			self.color = None
			self.boneMapping = None
			self.uv = []
	
	class Mesh:
		extensionHeaders = {
			'Custom-Bounding-Box-Meshes',
		}
		
		def __init__(self):
			self.vertices = []
			self.faces = []
			self.boneGroup = None
			self.materialInstance = None
			self.alphaEnum = None
			self.shadowEnum = None
			self.vertexFields = None
			# extension fields
			self.extensionHeaders = set()
			self.vertexEncoding = None
	
	class MeshGroup:
		extensionHeaders = {
			'Split-Mesh-Groups',
		}
		
		def __init__(self):
			self.name = None
			self.parent = None
			self.children = []
			self.meshes = []
			self.boundingBox = None
			self.visible = None
			# extension fields
			self.extensionHeaders = set()
	
	
	
	class FmdlVertexDatumType:
		position = 0
		boneWeights = 1
		normal = 2
		color = 3
		boneIndices = 7
		uv0 = 8
		uv1 = 9
		uv2 = 10
		uv3 = 11
		#boneWeights2 = 12
		#boneIndices2 = 13
		tangent = 14
	
	class FmdlVertexDatumFormat:
		tripleFloat32 = 1
		#??int16? = 4
		quadFloat16 = 6
		doubleFloat16 = 7
		quadFloat8 = 8
		quadInt8 = 9
	
	
	
	def __init__(self):
		self.bones = []
		self.materialInstances = []
		self.meshes = []
		self.meshGroups = []
		self.extensionHeaders = {}
	
	
	
	@staticmethod
	def parseFloat16(int16):
		exponentBits = 5
		exponentBias = 15
		mantissaBits = 10
		
		sign = ((int16 >> (exponentBits + mantissaBits)) & 1) != 0
		biasedExponent = (int16 >> mantissaBits) & ~(~0 << exponentBits)
		mantissa = int16 & ~(~0 << mantissaBits)
		
		if biasedExponent == (1 << exponentBits) - 1:
			if mantissa == 0:
				value = float('inf')
			else:
				value = float('nan')
		elif biasedExponent == 0:
			value = math.ldexp(mantissa, 1 - mantissaBits - exponentBias)
		else:
			value = math.ldexp(mantissa + (1 << mantissaBits), biasedExponent - mantissaBits - exponentBias)
		
		if sign:
			return -value
		else:
			return value
	
	@staticmethod
	def encodeFloat16(floatValue):
		exponentBits = 5
		exponentBias = 15
		mantissaBits = 10
		
		sign = 1 if (floatValue < 0.0) else 0
		absValue = -floatValue if (floatValue < 0.0) else floatValue
		if math.isnan(floatValue):
			biasedExponent = 31
			mantissa = ~(~0 << mantissaBits)
		elif math.isinf(floatValue):
			biasedExponent = 31
			mantissa = 0
		else:
			(candidateMantissa, exponent) = math.frexp(absValue)
			if candidateMantissa < 0.1:
				biasedExponent = 0
				mantissa = 0
			elif exponent < -exponentBias + 2:
				biasedExponent = 0
				mantissa = int(candidateMantissa * 2 ** (exponentBias + mantissaBits - 1 + exponent))
			elif exponent > exponentBias + 1:
				biasedExponent = 31
				mantissa = 0
			else:
				biasedExponent = exponent - 1 + exponentBias
				normalizedMantissa = (candidateMantissa * 2.0) - 1.0
				mantissa = int(normalizedMantissa * 2 ** mantissaBits)
		
		return (sign << (exponentBits + mantissaBits)) | (biasedExponent << mantissaBits) | (mantissa)
	
	
	
	@staticmethod
	def parseBones(fmdl, strings, boundingBoxes):
		if 0 not in fmdl.segment0Blocks:
			return []
		
		bones = []
		for definition in fmdl.segment0Blocks[0]:
			(
				nameStringID,
				parentBoneID,
				boundingBoxID,
				unknown,
				padding,
				localX,
				localY,
				localZ,
				localW,
				worldX,
				worldY,
				worldZ,
				worldW,
			) = unpack('< H h H H Q 4f 4f', definition)
			
			if not nameStringID < len(strings):
				raise InvalidFmdl("Invalid string %d referenced by bone" % nameStringID)
			name = strings[nameStringID]
			
			if not boundingBoxID < len(boundingBoxes):
				raise InvalidFmdl("Invalid bounding box %d referenced by bone" % boundingBoxID)
			boundingBox = boundingBoxes[boundingBoxID]
			
			bone = FmdlFile.Bone()
			bone.name = name
			bone.boundingBox = boundingBox
			bone.localPosition = FmdlFile.Vector4(localX, localY, localZ, localW)
			bone.globalPosition = FmdlFile.Vector4(worldX, worldY, worldZ, worldW)
			bone.parentID = parentBoneID
			bones.append(bone)
		
		for bone in bones:
			parentID = bone.parentID
			del bone.parentID
			
			if parentID >= 0:
				if not parentID < len(bones):
					raise InvalidFmdl("Invalid bone parent ID %d referenced by bone" % parentID)
				bone.parent = bones[parentID]
				bones[parentID].children.append(bone)
		
		# Check for parent loops
		for bone in bones:
			seen = []
			while bone.parent is not None:
				if bone in seen:
					# bone is a (direct or indirect) ancestor of bone.
					# PES does not seem to care about this; if present in real world models,
					# see if we can remove this check.
					raise InvalidFmdl("Invalid bone parent loop detected for bone")
				seen.append(bone)
				bone = bone.parent
		
		return bones
	
	@staticmethod
	def parseMeshGroups(fmdl, strings, boundingBoxes, meshes, extensionHeaders):
		if 1 in fmdl.segment0Blocks:
			block = fmdl.segment0Blocks[1]
		else:
			block = []
		
		meshGroups = []
		for definition in block:
			(
				nameStringID,
				invisible,
				parentID,
				unknown,
			) = unpack('< H H h h', definition)
			
			if not nameStringID < len(strings):
				raise InvalidFmdl("Invalid string %d referenced by mesh group" % (nameStringID))
			name = strings[nameStringID]
			
			meshGroup = FmdlFile.MeshGroup()
			meshGroup.name = name
			meshGroup.visible = (invisible == 0)
			meshGroup.parentID = parentID
			meshGroup.extensionHeaders = FmdlFile.parseObjectExtensionHeaders(extensionHeaders, FmdlFile.MeshGroup.extensionHeaders, len(meshGroups))
			meshGroups.append(meshGroup)
		
		for meshGroup in meshGroups:
			parentID = meshGroup.parentID
			del meshGroup.parentID
			
			if parentID >= 0:
				if not parentID < len(meshGroups):
					raise InvalidFmdl("Invalid mesh group parent ID %d referenced by mesh group" % parentID)
				meshGroup.parent = meshGroups[parentID]
				meshGroups[parentID].children.append(meshGroup)
		
		# Check for parent loops
		for meshGroup in meshGroups:
			seen = []
			while meshGroup.parent is not None:
				if meshGroup in seen:
					raise InvalidFmdl("Invalid mesh group parent loop detected for mesh group")
				seen.append(meshGroup)
				meshGroup = meshGroup.parent
		
		meshGroupAssignments = FmdlFile.parseMeshGroupAssignments(fmdl)
		assignments = [None for mesh in meshes]
		for (meshGroupID, firstMeshIndex, meshCount, boundingBoxID) in meshGroupAssignments:
			if not meshGroupID < len(meshGroups):
				raise InvalidFmdl("Invalid mesh group ID %d referenced by mesh group assignment" % meshGroupID)
			if not firstMeshIndex + meshCount <= len(meshes):
				raise InvalidFmdl("Invalid mesh ID %d referenced by mesh group assignment" % (firstMeshIndex + meshCount))
			if not boundingBoxID < len(boundingBoxes):
				raise InvalidFmdl("Invalid bounding box ID %d referenced by mesh group assignment" % boundingBoxID)
			
			for i in range(firstMeshIndex, firstMeshIndex + meshCount):
				if assignments[i] != None:
					raise InvalidFmdl("Invalid double mesh group assignment: mesh %d already assigned" % i)
				assignments[i] = meshGroupID
			if meshGroups[meshGroupID].boundingBox != None and meshGroups[meshGroupID].boundingBox != boundingBoxes[boundingBoxID]:
				raise InvalidFmdl("Invalid double bounding box assignment for mesh group %d" % meshGroupID)
			meshGroups[meshGroupID].boundingBox = boundingBoxes[boundingBoxID]
		
		if None in assignments:
			raise InvalidFmdl("Mesh not assigned to mesh group")
		
		for i in range(len(assignments)):
			meshGroups[assignments[i]].meshes.append(meshes[i])
		
		return meshGroups
	
	@staticmethod
	def parseMeshGroupAssignments(fmdl):
		if 2 not in fmdl.segment0Blocks:
			return []
		
		assignments = []
		for definition in fmdl.segment0Blocks[2]:
			(
				meshGroupID,
				meshCount,
				firstMeshIndex,
				boundingBoxID,
				unknown,
			) = unpack('< 4x HHHH 4x H 14x', definition)
			
			assignments.append((meshGroupID, firstMeshIndex, meshCount, boundingBoxID))
		return assignments
	
	@staticmethod
	def parseMeshes(fmdl, bones, materialInstances, extensionHeaders):
		if 3 not in fmdl.segment0Blocks:
			return []
		
		boneGroups = FmdlFile.parseBoneGroups(fmdl, bones)
		levelsOfDetail = FmdlFile.parseLevelsOfDetail(fmdl)
		faceIndices = FmdlFile.parseFaceIndices(fmdl)
		bufferOffsets = FmdlFile.parseBufferOffsets(fmdl)
		meshFormats = FmdlFile.parseMeshFormatAssignments(fmdl, bufferOffsets)
		
		if len(bufferOffsets) < 3:
			raise InvalidFmdl("Missing face buffer")
		
		meshes = []
		for definition in fmdl.segment0Blocks[3]:
			(
				alphaEnum,
				shadowEnum,
				materialInstanceID,
				boneGroupID,
				meshFormatID,
				vertexCount,
				firstFaceVertexIndex,
				faceVertexCount,
				firstFaceIndexID,
			) = unpack('< BB 2x HHHH 4x IIQ 16x', definition)
			
			if not meshFormatID < len(meshFormats):
				raise InvalidFmdl("Invalid mesh format ID %d referenced by mesh" % meshFormatID)
			
			vertexFields = FmdlFile.VertexFields()
			formatFields = []
			uv0 = False
			uv1 = False
			uv2 = False
			uv3 = False
			boneWeights = False
			boneIndices = False
			uvOffsets = {}
			for (datumType, datumFormat, offset, increment) in meshFormats[meshFormatID]:
				if datumType in formatFields:
					raise InvalidFmdl("Duplicate vertex field %d found in vertex format definition" % datumType)
				formatFields.append(datumType)
				
				if datumType == FmdlFile.FmdlVertexDatumType.normal:
					vertexFields.hasNormal = True
				if datumType == FmdlFile.FmdlVertexDatumType.color:
					vertexFields.hasColor = True
				if datumType == FmdlFile.FmdlVertexDatumType.tangent:
					vertexFields.hasTangent = True
				if datumType == FmdlFile.FmdlVertexDatumType.uv0:
					uv0 = True
					uvOffsets[0] = offset
					vertexFields.uvCount += 1
				if datumType == FmdlFile.FmdlVertexDatumType.uv1:
					uv1 = True
					uvOffsets[1] = offset
					vertexFields.uvCount += 1
				if datumType == FmdlFile.FmdlVertexDatumType.uv2:
					uv2 = True
					uvOffsets[2] = offset
					vertexFields.uvCount += 1
				if datumType == FmdlFile.FmdlVertexDatumType.uv3:
					uv3 = True
					uvOffsets[3] = offset
					vertexFields.uvCount += 1
				if datumType == FmdlFile.FmdlVertexDatumType.boneWeights:
					boneWeights = True
					vertexFields.hasBoneMapping = True
				if datumType == FmdlFile.FmdlVertexDatumType.boneIndices:
					boneIndices = True
					vertexFields.hasBoneMapping = True
			if uv3 and not uv2:
				raise InvalidFmdl("Non-monotonic UV map in vertex format definition: has uv3 but not uv2")
			if uv2 and not uv1:
				raise InvalidFmdl("Non-monotonic UV map in vertex format definition: has uv2 but not uv1")
			if uv1 and not uv0:
				raise InvalidFmdl("Non-monotonic UV map in vertex format definition: has uv1 but not uv0")
			if boneWeights != boneIndices:
				raise InvalidFmdl("Invalid vertex format specification: contains one of (bone weights, bone indices) but not the other")
			
			for i in range(vertexFields.uvCount):
				vertexFields.uvEqualities[i] = []
				for j in range(vertexFields.uvCount):
					if i != j and uvOffsets[i] == uvOffsets[j]:
						vertexFields.uvEqualities[i].append(j)
			
			if not materialInstanceID < len(materialInstances):
				raise InvalidFmdl("Invalid material instance ID %d referenced by mesh" % materialInstanceID)
			materialInstance = materialInstances[materialInstanceID]
			
			if not boneIndices:
				boneGroup = None
			elif not boneGroupID < len(boneGroups):
				raise InvalidFmdl("Invalid bone group ID %d referenced by mesh" % boneGroupID)
			else:
				boneGroup = boneGroups[boneGroupID]
			
			if not firstFaceIndexID < len(faceIndices):
				raise InvalidFmdl("Invalid face index ID %d referenced by mesh" % firstFaceIndexID)
			(lodFirstFaceVertexIndex, lodFaceVertexCount) = faceIndices[firstFaceIndexID]
			
			(vertices, vertexEncodings) = FmdlFile.parseVertices(fmdl, meshFormats[meshFormatID], boneGroup, vertexCount)
			faces = FmdlFile.parseFaces(fmdl, bufferOffsets[2], firstFaceVertexIndex + lodFirstFaceVertexIndex, lodFaceVertexCount, vertices)
			
			mesh = FmdlFile.Mesh()
			mesh.vertices = vertices
			mesh.faces = faces
			mesh.boneGroup = boneGroup
			mesh.materialInstance = materialInstance
			mesh.alphaEnum = alphaEnum
			mesh.shadowEnum = shadowEnum
			mesh.vertexFields = vertexFields
			mesh.vertexEncoding = vertexEncodings
			mesh.extensionHeaders = FmdlFile.parseObjectExtensionHeaders(extensionHeaders, FmdlFile.Mesh.extensionHeaders, len(meshes))
			meshes.append(mesh)
		return meshes
	
	@staticmethod
	def parseMaterialInstances(fmdl, strings):
		if 4 not in fmdl.segment0Blocks:
			return []
		
		materials = FmdlFile.parseMaterials(fmdl, strings)
		textures = FmdlFile.parseTextures(fmdl, strings)
		materialParameters = FmdlFile.parseMaterialParameters(fmdl)
		assignments = FmdlFile.parseTextureMaterialParameterAssignments(fmdl, strings)
		
		materialInstances = []
		for definition in fmdl.segment0Blocks[4]:
			(
				nameStringID,
				padding0,
				materialID,
				textureCount,
				materialParameterCount,
				firstTextureID,
				firstMaterialParameterID,
				padding1
			) = unpack('< H H H BB H H I', definition)
			
			if not nameStringID < len(strings):
				raise InvalidFmdl("Invalid string ID %d referenced by material instance" % nameStringID)
			instanceName = strings[nameStringID]
			
			if not materialID < len(materials):
				raise InvalidFmdl("Invalid material ID %d referenced by material instance" % materialID)
			(instanceTechnique, instanceShader) = materials[materialID]
			
			instanceTextures = []
			for i in range(firstTextureID, firstTextureID + textureCount):
				if not i < len(assignments):
					raise InvalidFmdl("Invalid texture / material parameter assignment %d referenced by material instance" % i)
				(textureName, textureID) = assignments[i]
				
				if not textureID < len(textures):
					raise InvalidFmdl("Invalid texture %d referenced by texture assignment" % textureID)
				texture = textures[textureID]
				
				if textureName in instanceTextures:
					raise InvalidFmdl("Duplicate texture name '%s' used by material instance" % textureName)
				
				instanceTextures.append((textureName, texture))
			
			instanceMaterialParameters = []
			for i in range(firstMaterialParameterID, firstMaterialParameterID + materialParameterCount):
				if not i < len(assignments):
					raise InvalidFmdl("Invalid texture / material parameter assignment %d referenced by material instance" % i)
				(materialParameterName, materialParameterID) = assignments[i]
				
				if not materialParameterID < len(materialParameters):
					raise InvalidFmdl("Invalid material parameter %d referenced by material parameter assignment" % materialParameterID)
				parameters = materialParameters[materialParameterID]
				
				if materialParameterName in instanceMaterialParameters:
					raise InvalidFmdl("Duplicate material parameters '%s' used by material instance" % materialParameterName)
				
				instanceMaterialParameters.append((materialParameterName, parameters))
			
			materialInstance = FmdlFile.MaterialInstance()
			materialInstance.name = instanceName
			materialInstance.technique = instanceTechnique
			materialInstance.shader = instanceShader
			materialInstance.textures = instanceTextures
			materialInstance.parameters = instanceMaterialParameters
			materialInstances.append(materialInstance)
		return materialInstances
	
	@staticmethod
	def parseBoneGroups(fmdl, bones):
		if 5 not in fmdl.segment0Blocks:
			return []
		
		boneGroups = []
		for definition in fmdl.segment0Blocks[5]:
			(
				unknown,
				entryCount,
			) = unpack_from('< H H', definition, 0)
			if entryCount > 32:
				entryCount = 32
			boneGroup = FmdlFile.BoneGroup()
			for i in range(entryCount):
				(boneID, ) = unpack_from('< H', definition, i * 2 + 4)
				if not boneID < len(bones):
					raise InvalidFmdl("Invalid bone ID %d referenced by bone group" % boneID)
				boneGroup.bones.append(bones[boneID])
			boneGroups.append(boneGroup)
		return boneGroups
	
	@staticmethod
	def parseTextures(fmdl, strings):
		if 6 not in fmdl.segment0Blocks:
			return []
		
		textures = []
		for definition in fmdl.segment0Blocks[6]:
			(
				filenameStringID,
				directoryStringID,
			) = unpack('< H H', definition)
			if not filenameStringID < len(strings):
				raise InvalidFdml("Invalid string ID %d referenced by texture" % filenameStringID)
			if not directoryStringID < len(strings):
				raise InvalidFdml("Invalid string ID %d referenced by texture" % directoryStringID)
			
			texture = FmdlFile.Texture()
			texture.filename = strings[filenameStringID]
			texture.directory = strings[directoryStringID]
			textures.append(texture)
		return textures
	
	@staticmethod
	def parseTextureMaterialParameterAssignments(fmdl, strings):
		if 7 not in fmdl.segment0Blocks:
			return []
		
		assignments = []
		for definition in fmdl.segment0Blocks[7]:
			(
				parameterStringID,
				referenceID,
			) = unpack('< H H', definition)
			if not parameterStringID < len(strings):
				raise InvalidFmdl("Invalid string ID %d referenced by texture / material parameter assignment" % parameterStringID)
			assignments.append((strings[parameterStringID], referenceID))
		return assignments
	
	@staticmethod
	def parseMaterials(fmdl, strings):
		if 8 not in fmdl.segment0Blocks:
			return []
		
		materials = []
		for definition in fmdl.segment0Blocks[8]:
			(
				shaderStringID,
				techniqueStringID,
			) = unpack('< H H', definition)
			if not shaderStringID < len(strings):
				raise InvalidFmdl("Invalid string ID %d referenced by material" % shaderStringID)
			if not techniqueStringID < len(strings):
				raise InvalidFmdl("Invalid string ID %d referenced by material" % techniqueStringID)
			materials.append((strings[techniqueStringID], strings[shaderStringID]))
		return materials
	
	@staticmethod
	def parseMeshFormatAssignments(fmdl, bufferOffsets):
		if 9 not in fmdl.segment0Blocks:
			return []
		
		meshFormatDefinitions = FmdlFile.parseMeshFormats(fmdl)
		vertexFormatDefinitions = FmdlFile.parseVertexFormats(fmdl)
		
		meshFormatAssignments = []
		for definition in fmdl.segment0Blocks[9]:
			(
				meshFormatEntryCount,
				vertexFormatEntryCount,
				firstUvIndex,
				uvIndexCount,
				firstMeshFormatID,
				firstVertexFormatID,
			) = unpack('< BB BB HH', definition)
			
			if not firstMeshFormatID + meshFormatEntryCount <= len(meshFormatDefinitions):
				raise InvalidFmdl("Invalid mesh format entry %d referenced by mesh format assignment" % (firstMeshFormatID + meshFormatEntryCount))
			if not firstVertexFormatID + vertexFormatEntryCount <= len(vertexFormatDefinitions):
				raise InvalidFmdl("Invalid vertex format entry %d referenced by mesh format assignment" % (firstVertexFormatID + vertexFormatEntryCount))
			
			vertexFormatOffsets = []
			vertexFormatIncrements = []
			for i in range(firstMeshFormatID, firstMeshFormatID + meshFormatEntryCount):
				(bufferID, bufferOffset, bufferOffsetIncrement, vertexEntryCount) = meshFormatDefinitions[i]
				if not bufferID < len(bufferOffsets):
					raise InvalidFmdl("Invalid buffer offset ID %d referenced by mesh format definition" % bufferID)
				
				offset = bufferOffsets[bufferID] + bufferOffset
				for i in range(vertexEntryCount):
					vertexFormatOffsets.append(bufferOffsets[bufferID] + bufferOffset)
					vertexFormatIncrements.append(bufferOffsetIncrement)
			
			if len(vertexFormatOffsets) != vertexFormatEntryCount:
				raise InvalidFmdl("Incorrect number of mesh format definitions: found %d, expected %d" % (len(vertexFormatOffsets), vertexFormatEntryCount))
			
			meshVertexFormatEntries = []
			for i in range(vertexFormatEntryCount):
				blockOffset = vertexFormatOffsets[i]
				increment = vertexFormatIncrements[i]
				(datumType, datumFormat, vertexOffset) = vertexFormatDefinitions[i + firstVertexFormatID]
				meshVertexFormatEntries.append((datumType, datumFormat, blockOffset + vertexOffset, increment))
			meshFormatAssignments.append(meshVertexFormatEntries)
		return meshFormatAssignments
	
	@staticmethod
	def parseMeshFormats(fmdl):
		if 10 not in fmdl.segment0Blocks:
			return []
		
		formatEntries = []
		for definition in fmdl.segment0Blocks[10]:
			(
				bufferID,
				vertexFormatEntryCount,
				bufferOffsetIncrement,
				meshFormatType,
				bufferOffset,
			) = unpack('< BBBB I', definition)
			
			formatEntries.append((bufferID, bufferOffset, bufferOffsetIncrement, vertexFormatEntryCount))
		return formatEntries
	
	@staticmethod
	def parseVertexFormats(fmdl):
		if 11 not in fmdl.segment0Blocks:
			return []
		
		formatEntries = []
		for definition in fmdl.segment0Blocks[11]:
			(
				datumType,
				datumFormat,
				offset,
			) = unpack('< B B H', definition)
			
			if datumType not in [
				FmdlFile.FmdlVertexDatumType.position,
				FmdlFile.FmdlVertexDatumType.boneWeights,
				FmdlFile.FmdlVertexDatumType.normal,
				FmdlFile.FmdlVertexDatumType.color,
				FmdlFile.FmdlVertexDatumType.boneIndices,
				FmdlFile.FmdlVertexDatumType.uv0,
				FmdlFile.FmdlVertexDatumType.uv1,
				FmdlFile.FmdlVertexDatumType.uv2,
				FmdlFile.FmdlVertexDatumType.uv3,
				FmdlFile.FmdlVertexDatumType.tangent,
			]:
				raise InvalidFmdl("Invalid vertex datum type %s" % datumType)
			
			if datumFormat not in [
				FmdlFile.FmdlVertexDatumFormat.tripleFloat32,
				FmdlFile.FmdlVertexDatumFormat.quadFloat16,
				FmdlFile.FmdlVertexDatumFormat.doubleFloat16,
				FmdlFile.FmdlVertexDatumFormat.quadFloat8,
				FmdlFile.FmdlVertexDatumFormat.quadInt8,
			]:
				raise InvalidFmdl("Invalid vertex datum format %s" % datumFormat)
			
			formatEntries.append((datumType, datumFormat, offset))
		return formatEntries
	
	@staticmethod
	def parseStrings(fmdl):
		if 12 not in fmdl.segment0Blocks:
			return []
		
		lastStringPosition = 0
		strings = []
		for definition in fmdl.segment0Blocks[12]:
			(
				blockID,
				length,
				offset,
			) = unpack('< H H I', definition)
			
			if blockID not in fmdl.segment1Blocks:
				raise InvalidFmdl("Invalid block %d referenced by string" % blockID)
			block = fmdl.segment1Blocks[blockID]
			
			if offset + length > len(block):
				raise InvalidFmdl("Invalid block location %d+%d referenced by string" % (offset, length))
			bytestring = block[offset : offset + length]
			
			try:
				string = str(bytestring, 'utf-8')
			except UnicodeError:
				raise InvalidFmdl("Invalid unicode in string at location %d" % offset)
			
			strings.append(string)
			
			if blockID == 3 and lastStringPosition < length + offset:
				lastStringPosition = length + offset
		
		extensionHeaderPosition = lastStringPosition + 1
		extensionHeaders = None
		if extensionHeaderPosition < len(fmdl.segment1Blocks[3]):
			#
			# Read nul-terminated extension header.
			#
			block = fmdl.segment1Blocks[3]
			extensionHeaderEnd = extensionHeaderPosition
			while extensionHeaderEnd < len(block) and block[extensionHeaderEnd] != 0:
				extensionHeaderEnd += 1
			extensionHeaderString = str(block[extensionHeaderPosition : extensionHeaderEnd], 'utf-8')
			recognitionString = 'X-FMDL-Extensions:'
			if extensionHeaderString[0:len(recognitionString)].lower() == recognitionString.lower():
				#
				# HTTP-style headers, no continuations.
				# key:value pairs, separated by newlines, optional whitespace separation
				#
				# value is parsed to a comma-separated list, further parsing elsewhere
				#
				extensionHeaders = {}
				lines = extensionHeaderString.split('\n')
				for line in lines:
					position = line.find(':')
					if position == -1:
						continue
					key = line[0:position].strip().lower()
					value = line[position + 1:].strip()
					if ' ' in key or '\n' in key or '\r' in key or '\t' in key:
						continue
					if key in extensionHeaders:
						continue
					extensionHeaders[key] = []
					for v in value.split(','):
						extensionHeaders[key].append(v.strip())
		return (strings, extensionHeaders)
	
	@staticmethod
	def parseBoundingBoxes(fmdl):
		if 13 not in fmdl.segment0Blocks:
			return []
		
		boundingBoxes = []
		for definition in fmdl.segment0Blocks[13]:
			(
				maxX, maxY, maxZ, maxW,
				minX, minY, minZ, minW,
			) = unpack('< 8f', definition)
			boundingBoxes.append(
				FmdlFile.BoundingBox(
					FmdlFile.Vector4(minX, minY, minZ, minW),
					FmdlFile.Vector4(maxX, maxY, maxZ, maxW),
				)
			)
		return boundingBoxes
	
	@staticmethod
	def parseBufferOffsets(fmdl):
		if 14 not in fmdl.segment0Blocks:
			return []
		
		bufferOffsets = []
		for definition in fmdl.segment0Blocks[14]:
			(
				eof,
				length,
				offset,
				padding,
			) = unpack('< I I I I', definition)
			
			bufferOffsets.append(offset)
		return bufferOffsets
	
	@staticmethod
	def parseLevelsOfDetail(fmdl):
		if 16 not in fmdl.segment0Blocks:
			raise InvalidFmdl("Level Of Detail specification missing")
		
		if len(fmdl.segment0Blocks[16]) != 1:
			raise InvalidFmdl("Unexpected Level Of Detail specification, expected 1 record, found %s" % len(fmdl.segment0Blocks[16]))
		
		definition = fmdl.segment0Blocks[16][0]
		(
			lodCount,
			unknown0,
			unknown1,
			unknown2,
		) = unpack('< I 3f', definition)
		
		return lodCount
	
	@staticmethod
	def parseFaceIndices(fmdl):
		if 17 not in fmdl.segment0Blocks:
			return []
		
		faceIndices = []
		for definition in fmdl.segment0Blocks[17]:
			(
				firstFaceVertexIndex,
				faceVertexCount,
			) = unpack('< I I', definition)
			faceIndices.append((firstFaceVertexIndex, faceVertexCount))
		return faceIndices
	
	@staticmethod
	def parseMaterialParameters(fmdl):
		if 0 not in fmdl.segment1Blocks:
			return []
		
		materialParametersBlock = fmdl.segment1Blocks[0]
		materialParameters = []
		for index in range(len(materialParametersBlock) // 16):
			offset = index * 16
			parameters = unpack_from('< 4f', materialParametersBlock, offset)
			materialParameters.append(parameters)
		return materialParameters
	
	@staticmethod
	def parseVertices(fmdl, format, boneGroup, vertexCount):
		#
		# This function assumes that:
		# - no datum type in format occurs more than once;
		# - each uv field is present only if all preceeding ones are also present;
		# - boneWeights is present if and only if boneIndices is present.
		#
		
		if 2 not in fmdl.segment1Blocks:
			raise InvalidFmdl("Vertex block not found")
		
		vertexBuffer = fmdl.segment1Blocks[2]
		
		vertices = []
		vertexEncodings = []
		for vertexIndex in range(vertexCount):
			vertex = FmdlFile.Vertex()
			vertexEncoding = FmdlFile.VertexEncoding()
			vertexEncoding.vertex = vertex
			
			uvEncoding = [None for i in range(4)]
			uv = [None for i in range(4)]
			boneWeights = None
			boneIndices = None
			
			for (datumType, datumFormat, offset, increment) in format:
				position = offset + vertexIndex * increment
				
				if datumType == FmdlFile.FmdlVertexDatumType.position:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.tripleFloat32:
						raise InvalidFmdl("Unexpected format %d for vertex position data" % datumFormat)
					vertexEncoding.position = vertexBuffer[position : position + 12]
					value = unpack('< 3f', vertexEncoding.position)
					vertex.position = FmdlFile.Vector3(value[0], value[1], value[2])
				elif datumType == FmdlFile.FmdlVertexDatumType.boneWeights:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.quadFloat8:
						raise InvalidFmdl("Unexpected format %d for vertex bone weight data" % datumFormat)
					boneWeights = unpack('< 4B', vertexBuffer[position : position + 4])
				elif datumType == FmdlFile.FmdlVertexDatumType.normal:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.quadFloat16:
						raise InvalidFmdl("Unexpected format %d for vertex normal data" % datumFormat)
					vertexEncoding.normal = vertexBuffer[position : position + 8]
					value = [FmdlFile.parseFloat16(x) for x in unpack('< 4H', vertexEncoding.normal)]
					vertex.normal = FmdlFile.Vector4(value[0], value[1], value[2], value[3])
				elif datumType == FmdlFile.FmdlVertexDatumType.color:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.quadFloat8:
						raise InvalidFmdl("Unexpected format %d for vertex color data" % datumFormat)
					vertexEncoding.color = vertexBuffer[position : position + 4]
					vertex.color = [x / 255.0 for x in unpack('< 4B', vertexEncoding.color)]
				elif datumType == FmdlFile.FmdlVertexDatumType.boneIndices:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.quadInt8:
						raise InvalidFmdl("Unexpected format %d for vertex bone index data" % datumFormat)
					boneIndices = unpack('< 4B', vertexBuffer[position : position + 4])
				elif datumType == FmdlFile.FmdlVertexDatumType.uv0:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.doubleFloat16:
						raise InvalidFmdl("Unexpected format %d for vertex uv data" % datumFormat)
					uvEncoding[0] = vertexBuffer[position : position + 4]
					value = [FmdlFile.parseFloat16(x) for x in unpack('< 2H', uvEncoding[0])]
					uv[0] = FmdlFile.Vector2(value[0], value[1])
				elif datumType == FmdlFile.FmdlVertexDatumType.uv1:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.doubleFloat16:
						raise InvalidFmdl("Unexpected format %d for vertex uv data" % datumFormat)
					uvEncoding[1] = vertexBuffer[position : position + 4]
					value = [FmdlFile.parseFloat16(x) for x in unpack('< 2H', uvEncoding[1])]
					uv[1] = FmdlFile.Vector2(value[0], value[1])
				elif datumType == FmdlFile.FmdlVertexDatumType.uv2:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.doubleFloat16:
						raise InvalidFmdl("Unexpected format %d for vertex uv data" % datumFormat)
					uvEncoding[2] = vertexBuffer[position : position + 4]
					value = [FmdlFile.parseFloat16(x) for x in unpack('< 2H', uvEncoding[2])]
					uv[2] = FmdlFile.Vector2(value[0], value[1])
				elif datumType == FmdlFile.FmdlVertexDatumType.uv3:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.doubleFloat16:
						raise InvalidFmdl("Unexpected format %d for vertex uv data" % datumFormat)
					uvEncoding[3] = vertexBuffer[position : position + 4]
					value = [FmdlFile.parseFloat16(x) for x in unpack('< 2H', uvEncoding[3])]
					uv[3] = FmdlFile.Vector2(value[0], value[1])
				elif datumType == FmdlFile.FmdlVertexDatumType.tangent:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.quadFloat16:
						raise InvalidFmdl("Unexpected format %d for vertex tangent data" % datumFormat)
					vertexEncoding.tangent = vertexBuffer[position : position + 8]
					value = [FmdlFile.parseFloat16(x) for x in unpack('< 4H', vertexEncoding.tangent)]
					vertex.tangent = FmdlFile.Vector4(value[0], value[1], value[2], value[3])
				else:
					raise InvalidFmdl("Unexpected vertex datum type %d" % datumType)
			
			for i in range(4):
				if uv[i] != None:
					vertex.uv.append(uv[i])
					vertexEncoding.uv.append(uvEncoding[i])
			
			if boneWeights != None:
				vertex.boneMapping = {}
				vertexEncoding.boneMapping = []
				for i in range(4):
					if boneWeights[i] > 0:
						if not boneIndices[i] < len(boneGroup.bones):
							#
							# This happens a fair few times in real models.
							# Let's just ignore the bone weighting instead.
							#
							# WARNING
							#raise InvalidFmdl("Invalid bone ID %d referenced by vertex" % boneIndices[i])
							continue
						
						vertex.boneMapping[boneGroup.bones[boneIndices[i]]] = boneWeights[i] / 255.0
						vertexEncoding.boneMapping.append((boneGroup.bones[boneIndices[i]], boneWeights[i]))
			
			vertices.append(vertex)
			vertexEncodings.append(vertexEncoding)
		return (vertices, vertexEncodings)
	
	@staticmethod
	def parseFaces(fmdl, vertexBufferOffset, firstFaceVertexIndex, faceVertexCount, vertices):
		if 2 not in fmdl.segment1Blocks:
			raise InvalidFmdl("Vertex block not found")
		
		vertexBuffer = fmdl.segment1Blocks[2]
		
		faces = []
		for faceVertexIndex in range(firstFaceVertexIndex, firstFaceVertexIndex + faceVertexCount, 3):
			position = faceVertexIndex * 2 + vertexBufferOffset
			(index1, index2, index3) = unpack_from('< HHH', vertexBuffer, position)
			if not index1 < len(vertices) and index2 < len(vertices) and index3 < len(vertices):
				raise InvalidFmdl("Invalid vertex referenced by face")
			faces.append(FmdlFile.Face(vertices[index1], vertices[index2], vertices[index3]))
		return faces
	
	@staticmethod
	def parseObjectExtensionHeaders(extensionHeaders, headerList, objectID):
		output = set()
		for header in headerList:
			key = header.lower()
			if extensionHeaders is not None and key in extensionHeaders and str(objectID) in extensionHeaders[key]:
				output.add(key)
		return output
	
	def readFile(self, filename):
		fmdl = FmdlContainer()
		fmdl.readFile(filename)
		
		(strings, extensionHeaders) = self.parseStrings(fmdl)
		boundingBoxes = self.parseBoundingBoxes(fmdl)
		bones = self.parseBones(fmdl, strings, boundingBoxes)
		materialInstances = self.parseMaterialInstances(fmdl, strings)
		meshes = self.parseMeshes(fmdl, bones, materialInstances, extensionHeaders)
		meshGroups = self.parseMeshGroups(fmdl, strings, boundingBoxes, meshes, extensionHeaders)
		
		self.bones = bones
		self.materialInstances = materialInstances
		self.meshes = meshes
		self.meshGroups = meshGroups
		self.extensionHeaders = extensionHeaders
	
	
	
	@staticmethod
	def newSegment0BlockDescriptorID(fmdl, blockID):
		if blockID not in fmdl.segment0Blocks:
			fmdl.segment0Blocks[blockID] = []
		return len(fmdl.segment0Blocks[blockID])
	
	@staticmethod
	def addSegment0Block(fmdl, blockID, block):
		ID = FmdlFile.newSegment0BlockDescriptorID(fmdl, blockID)
		fmdl.segment0Blocks[blockID].append(block)
		return ID
	
	@staticmethod
	def addBone(fmdl, stringIndices, bone, boneIndices):
		if bone.parent != None and bone.parent in boneIndices:
			parentBoneID = boneIndices[bone.parent]
		else:
			parentBoneID = -1
		
		return FmdlFile.addSegment0Block(fmdl, 0, pack('< H h H H Q 4f 4f',
			FmdlFile.addString(fmdl, stringIndices, bone.name),
			parentBoneID,
			FmdlFile.addBoundingBox(fmdl, bone.boundingBox),
			1, #unknown
			0, #padding
			bone.localPosition.x, bone.localPosition.y, bone.localPosition.z, bone.localPosition.w,
			bone.globalPosition.x, bone.globalPosition.y, bone.globalPosition.z, bone.globalPosition.w,
		))
	
	@staticmethod
	def addMeshGroup(fmdl, stringIndices, meshGroup, meshGroupIndices, meshIndices):
		if meshGroup.parent == None:
			parentMeshGroupID = -1
		else:
			parentMeshGroupID = meshGroupIndices[meshGroup.parent]
		
		meshGroupID = FmdlFile.addSegment0Block(fmdl, 1, pack('< H H h h',
			FmdlFile.addString(fmdl, stringIndices, meshGroup.name),
			1 if meshGroup.visible is False else 0,
			parentMeshGroupID,
			-1,
		))
		
		boundingBoxID = FmdlFile.addBoundingBox(fmdl, meshGroup.boundingBox)
		
		meshGroupAssignments = []
		for mesh in meshGroup.meshes:
			meshID = meshIndices[mesh]
			if len(meshGroupAssignments) > 0:
				(firstMeshID, meshCount) = meshGroupAssignments[len(meshGroupAssignments) - 1]
				if meshID == firstMeshID + meshCount:
					meshGroupAssignments[len(meshGroupAssignments) - 1] = (firstMeshID, meshCount + 1)
				else:
					meshGroupAssignments.append((meshID, 1))
			else:
				meshGroupAssignments.append((meshID, 1))
		
		for (firstMeshID, meshCount) in meshGroupAssignments:
			FmdlFile.addMeshGroupAssignment(fmdl, meshGroupID, firstMeshID, meshCount, boundingBoxID)
		
		if len(meshGroupAssignments) == 0:
			FmdlFile.addMeshGroupAssignment(fmdl, meshGroupID, 0, 0, boundingBoxID)
		
		return meshGroupID
	
	@staticmethod
	def addMeshGroupAssignment(fmdl, meshGroupID, firstMeshID, meshCount, boundingBoxID):
		return FmdlFile.addSegment0Block(fmdl, 2, pack('< 4x HHHH 4x H 14x',
			meshGroupID,
			meshCount,
			firstMeshID,
			boundingBoxID,
			0,
		))
	
	@staticmethod
	def addMesh(fmdl, mesh, boneIndices, materialInstanceID, levelsOfDetail, vertexPositionBuffer, vertexDataBuffer, faceBuffer):
		if mesh.vertexEncoding == None:
			vertexEncoding = FmdlFile.encodeVertices(mesh.vertices, mesh.vertexFields)
		else:
			vertexEncoding = mesh.vertexEncoding
		
		if mesh.vertexFields.hasBoneMapping:
			(boneGroupID, boneGroupIndices) = FmdlFile.addBoneGroup(fmdl, mesh.boneGroup, boneIndices)
		else:
			boneGroupID = 0
			boneGroupIndices = {}
		
		(
			meshFormatAssignmentID,
			vertexFormatEntries,
			positionBufferEntrySize,
			dataBufferEntrySize,
		) = FmdlFile.addMeshFormatAssignment(fmdl, mesh.vertexFields, len(vertexPositionBuffer), len(vertexDataBuffer))
		
		vertexIndices = FmdlFile.addVertices(
			vertexEncoding,
			vertexFormatEntries,
			positionBufferEntrySize,
			dataBufferEntrySize,
			boneGroupIndices,
			vertexPositionBuffer,
			vertexDataBuffer,
		)
		
		firstFaceIndexID = FmdlFile.newSegment0BlockDescriptorID(fmdl, 17)
		for i in range(levelsOfDetail):
			FmdlFile.addFaceIndex(fmdl, mesh.faces)
		
		firstFaceVertexID = FmdlFile.addFaces(fmdl, mesh.faces, faceBuffer, vertexIndices)
		
		return FmdlFile.addSegment0Block(fmdl, 3, pack('< BB 2x HHHH 4x IIQ 16x',
			mesh.alphaEnum,
			mesh.shadowEnum,
			materialInstanceID,
			boneGroupID,
			meshFormatAssignmentID,
			len(mesh.vertices),
			firstFaceVertexID,
			len(mesh.faces) * 3,
			firstFaceIndexID,
		))
	
	@staticmethod
	def addMaterialInstance(fmdl, stringIndices, materialInstance):
		nameStringID = FmdlFile.addString(fmdl, stringIndices, materialInstance.name)
		materialID = FmdlFile.addMaterial(fmdl, stringIndices, materialInstance.shader, materialInstance.technique)
		
		firstTextureAssignmentID = FmdlFile.newSegment0BlockDescriptorID(fmdl, 7)
		textureCount = len(materialInstance.textures)
		for (role, texture) in materialInstance.textures:
			textureID = FmdlFile.addTexture(fmdl, stringIndices, texture.filename, texture.directory)
			FmdlFile.addTextureMaterialParameterAssignment(fmdl, stringIndices, role, textureID)
		
		firstMaterialParameterAssignmentID = FmdlFile.newSegment0BlockDescriptorID(fmdl, 7)
		materialParameterCount = len(materialInstance.parameters)
		for (parameter, values) in materialInstance.parameters:
			materialParameterValuesID = FmdlFile.addMaterialParameterValues(fmdl, values)
			FmdlFile.addTextureMaterialParameterAssignment(fmdl, stringIndices, parameter, materialParameterValuesID)
		
		return FmdlFile.addSegment0Block(fmdl, 4, pack('< H H H BB H H I',
			nameStringID,
			0, #padding
			materialID,
			textureCount,
			materialParameterCount,
			firstTextureAssignmentID,
			firstMaterialParameterAssignmentID,
			0, #padding
		))
	
	@staticmethod
	def addBoneGroup(fmdl, boneGroup, boneIndices):
		if len(boneGroup.bones) > 32:
			raise InvalidFmdl("Too many bones in bone group")
		descriptor = bytearray(68)
		pack_into('< HH', descriptor, 0,
			4, #unknown
			len(boneGroup.bones),
		)
		
		boneGroupIndices = {}
		for i in range(len(boneGroup.bones)):
			boneIndex = boneIndices[boneGroup.bones[i]]
			pack_into('< H', descriptor, i * 2 + 4, boneIndex)
			boneGroupIndices[boneGroup.bones[i]] = i
		
		boneGroupID = FmdlFile.addSegment0Block(fmdl, 5, descriptor)
		return (boneGroupID, boneGroupIndices)
	
	@staticmethod
	def addTexture(fmdl, stringIndices, filename, directory):
		return FmdlFile.addSegment0Block(fmdl, 6, pack('< H H',
			FmdlFile.addString(fmdl, stringIndices, filename),
			FmdlFile.addString(fmdl, stringIndices, directory),
		))
	
	@staticmethod
	def addTextureMaterialParameterAssignment(fmdl, stringIndices, parameterName, valueID):
		return FmdlFile.addSegment0Block(fmdl, 7, pack('< H H',
			FmdlFile.addString(fmdl, stringIndices, parameterName),
			valueID,
		))
	
	@staticmethod
	def addMaterial(fmdl, stringIndices, shader, technique):
		return FmdlFile.addSegment0Block(fmdl, 8, pack('< H H',
			FmdlFile.addString(fmdl, stringIndices, shader),
			FmdlFile.addString(fmdl, stringIndices, technique),
		))
	
	@staticmethod
	def addMeshFormatAssignment(fmdl, vertexFields, vertexPositionBufferOffset, vertexDataBufferOffset):
		formatEntries = []
		
		firstMeshFormatID = FmdlFile.newSegment0BlockDescriptorID(fmdl, 10)
		firstVertexFormatID = FmdlFile.newSegment0BlockDescriptorID(fmdl, 11)
		
		bufferOffsets = { 0: 0, 1: 0 }
		typeEntries = { 0: 0, 1: 0, 2: 0, 3: 0 }
		
		if True:
			# position is always present
			FmdlFile.addVertexFormat(fmdl, FmdlFile.FmdlVertexDatumType.position, FmdlFile.FmdlVertexDatumFormat.tripleFloat32, bufferOffsets[0])
			formatEntries.append((0, FmdlFile.FmdlVertexDatumType.position, FmdlFile.FmdlVertexDatumFormat.tripleFloat32, bufferOffsets[0]))
			bufferOffsets[0] += 12
			typeEntries[0] += 1
		
		if vertexFields.hasNormal:
			FmdlFile.addVertexFormat(fmdl, FmdlFile.FmdlVertexDatumType.normal, FmdlFile.FmdlVertexDatumFormat.quadFloat16, bufferOffsets[1])
			formatEntries.append((1, FmdlFile.FmdlVertexDatumType.normal, FmdlFile.FmdlVertexDatumFormat.quadFloat16, bufferOffsets[1]))
			bufferOffsets[1] += 8
			typeEntries[1] += 1
		
		if vertexFields.hasTangent:
			FmdlFile.addVertexFormat(fmdl, FmdlFile.FmdlVertexDatumType.tangent, FmdlFile.FmdlVertexDatumFormat.quadFloat16, bufferOffsets[1])
			formatEntries.append((1, FmdlFile.FmdlVertexDatumType.tangent, FmdlFile.FmdlVertexDatumFormat.quadFloat16, bufferOffsets[1]))
			bufferOffsets[1] += 8
			typeEntries[1] += 1
		
		if vertexFields.hasColor:
			FmdlFile.addVertexFormat(fmdl, FmdlFile.FmdlVertexDatumType.color, FmdlFile.FmdlVertexDatumFormat.quadFloat8, bufferOffsets[1])
			formatEntries.append((1, FmdlFile.FmdlVertexDatumType.color, FmdlFile.FmdlVertexDatumFormat.quadFloat8, bufferOffsets[1]))
			bufferOffsets[1] += 4
			typeEntries[2] += 1
		
		if vertexFields.hasBoneMapping:
			FmdlFile.addVertexFormat(fmdl, FmdlFile.FmdlVertexDatumType.boneWeights, FmdlFile.FmdlVertexDatumFormat.quadFloat8, bufferOffsets[1])
			formatEntries.append((1, FmdlFile.FmdlVertexDatumType.boneWeights, FmdlFile.FmdlVertexDatumFormat.quadFloat8, bufferOffsets[1]))
			bufferOffsets[1] += 4
			FmdlFile.addVertexFormat(fmdl, FmdlFile.FmdlVertexDatumType.boneIndices, FmdlFile.FmdlVertexDatumFormat.quadInt8, bufferOffsets[1])
			formatEntries.append((1, FmdlFile.FmdlVertexDatumType.boneIndices, FmdlFile.FmdlVertexDatumFormat.quadInt8, bufferOffsets[1]))
			bufferOffsets[1] += 4
			typeEntries[3] += 2
		
		uvOffsets = {}
		uvTypes = [
			FmdlFile.FmdlVertexDatumType.uv0,
			FmdlFile.FmdlVertexDatumType.uv1,
			FmdlFile.FmdlVertexDatumType.uv2,
			FmdlFile.FmdlVertexDatumType.uv3,
		]
		for i in range(vertexFields.uvCount):
			equalUv = None
			equalities = vertexFields.uvEqualities[i] if i in vertexFields.uvEqualities else []
			for uv in equalities:
				if uv in uvOffsets:
					equalUv = uv
					break
			
			if equalUv != None:
				FmdlFile.addVertexFormat(fmdl, uvTypes[i], FmdlFile.FmdlVertexDatumFormat.doubleFloat16, uvOffsets[equalUv])
			else:
				FmdlFile.addVertexFormat(fmdl, uvTypes[i], FmdlFile.FmdlVertexDatumFormat.doubleFloat16, bufferOffsets[1])
				formatEntries.append((1, uvTypes[i], FmdlFile.FmdlVertexDatumFormat.doubleFloat16, bufferOffsets[1]))
				uvOffsets[i] = bufferOffsets[1]
				bufferOffsets[1] += 4
			typeEntries[3] += 1
		
		FmdlFile.addMeshFormat(fmdl, 0, typeEntries[0], bufferOffsets[0], 0, vertexPositionBufferOffset)
		for i in [1, 2, 3]:
			if typeEntries[i] > 0:
				FmdlFile.addMeshFormat(fmdl, 1, typeEntries[i], bufferOffsets[1], i, vertexDataBufferOffset)
		
		meshFormatCount = FmdlFile.newSegment0BlockDescriptorID(fmdl, 10) - firstMeshFormatID
		vertexFormatCount = FmdlFile.newSegment0BlockDescriptorID(fmdl, 11) - firstVertexFormatID
		
		meshFormatAssignmentID = FmdlFile.addSegment0Block(fmdl, 9, pack('< BBBB HH',
			meshFormatCount,
			vertexFormatCount,
			0,
			vertexFields.uvCount,
			firstMeshFormatID,
			firstVertexFormatID,
		))
		
		return (meshFormatAssignmentID, formatEntries, bufferOffsets[0], bufferOffsets[1])
	
	@staticmethod
	def addMeshFormat(fmdl, bufferID, vertexFormatEntryCount, bufferOffsetIncrement, meshFormatType, bufferOffset):
		return FmdlFile.addSegment0Block(fmdl, 10, pack('< BBBB I',
			bufferID, vertexFormatEntryCount, bufferOffsetIncrement, meshFormatType, bufferOffset,
		))
	
	@staticmethod
	def addVertexFormat(fmdl, datumType, datumFormat, offset):
		return FmdlFile.addSegment0Block(fmdl, 11, pack('< BB H',
			datumType, datumFormat, offset,
		))
	
	@staticmethod
	def addString(fmdl, stringIndices, string):
		if 3 not in fmdl.segment1Blocks:
			fmdl.segment1Blocks[3] = bytearray()
		
		if string in stringIndices:
			return stringIndices[string]
		
		encoded = bytes(string, 'utf-8')
		offset = len(fmdl.segment1Blocks[3])
		
		fmdl.segment1Blocks[3] += encoded
		fmdl.segment1Blocks[3] += b'\0'
		
		index = FmdlFile.addSegment0Block(fmdl, 12, pack('< H H I',
			3,
			len(encoded),
			offset,
		))
		stringIndices[string] = index
		return index
	
	@staticmethod
	def addBoundingBox(fmdl, boundingBox):
		return FmdlFile.addSegment0Block(fmdl, 13, pack('< 8f',
			boundingBox.max.x, boundingBox.max.y, boundingBox.max.z, boundingBox.max.w,
			boundingBox.min.x, boundingBox.min.y, boundingBox.min.z, boundingBox.min.w,
		))
	
	@staticmethod
	def addBufferOffset(fmdl, last, length, offset):
		return FmdlFile.addSegment0Block(fmdl, 14, pack('< III 4x',
			1 if last else 0,
			length,
			offset,
		))
	
	@staticmethod
	def addLevelsOfDetail(fmdl, levels):
		FmdlFile.addSegment0Block(fmdl, 16, pack('< I fff',
			levels,
			1.0, 1.0, 1.0,
		))
	
	@staticmethod
	def addFaceIndex(fmdl, faces):
		return FmdlFile.addSegment0Block(fmdl, 17, pack('< II',
			0,
			len(faces) * 3,
		))
	
	@staticmethod
	def addMaterialParameterValues(fmdl, parameterValues):
		if 0 not in fmdl.segment1Blocks:
			fmdl.segment1Blocks[0] = bytearray()
		
		index = len(fmdl.segment1Blocks[0]) // 16
		fmdl.segment1Blocks[0] += pack('< 4f', *parameterValues)
		return index
	
	@staticmethod
	def encodeVertices(vertices, vertexFields):
		vertexEncodings = []
		for vertexIndex in range(len(vertices)):
			vertexEncoding = FmdlFile.VertexEncoding()
			vertex = vertices[vertexIndex]
			vertexEncoding.vertex = vertex
			if True:
				# position is always present
				vertexEncoding.position = pack('< 3f', vertex.position.x, vertex.position.y, vertex.position.z)
			if vertexFields.hasNormal:
				vertexEncoding.normal = pack('< 4H', *(FmdlFile.encodeFloat16(x) for x in
					(vertex.normal.x, vertex.normal.y, vertex.normal.z, vertex.normal.w)
				))
			if vertexFields.hasTangent:
				vertexEncoding.tangent = pack('< 4H', *(FmdlFile.encodeFloat16(x) for x in
					(vertex.tangent.x, vertex.tangent.y, vertex.tangent.z, vertex.tangent.w)
				))
			if vertexFields.hasColor:
				vertexEncoding.color = pack('< 4B', *(int(x * 255 + 0.5) for x in vertex.color[0:4]))
			for i in range(4):
				if i < vertexFields.uvCount:
					vertexEncoding.uv.append(pack('< 2H', *(FmdlFile.encodeFloat16(x) for x in
						(vertex.uv[i].u, vertex.uv[i].v)
					)))
			if vertexFields.hasBoneMapping:
				#
				# fmdl bone mappings support at most 4 bones, and store weights as 8-bit integers.
				# Pack the desired bone mapping into this constraint as accurately as possible:
				# - If the desired bone mapping contains more than 4 bones, simplify it
				#   down to 4 bones, keeping the total weight identical
				# - Round bone weights to units of N/255, in such a way that the total bone weight
				#   does not change more than one rounding error. In particular, a rounded total weight
				#   of 1 must remain a total weight of 1 after elementwise rounding.
				#
				orderedBones = sorted(vertex.boneMapping.items(), key = (lambda pair: (pair[1], pair[0].name)), reverse = True)
				totalWeight = sum([weight for (boneIndex, weight) in orderedBones])
				integralTotalWeight = int((totalWeight * 255) + 0.5)
				
				if len(orderedBones) > 4:
					print("Vertex with more than 4 bones assigned")
				
				selectedBones = orderedBones[0:4]
				selectedWeight = sum([weight for (boneIndex, weight) in selectedBones])
				
				remainingIntegralWeight = integralTotalWeight
				remainingSelectedWeight = selectedWeight
				vertexEncoding.boneMapping = []
				for i in range(len(selectedBones)):
					(bone, weight) = selectedBones[i]
					if i == len(selectedBones) - 1:
						boneWeight = max(0, min(255, remainingIntegralWeight))
					elif remainingSelectedWeight <= 0:
						boneWeight = 0
					else:
						boneWeight = int((weight / remainingSelectedWeight) * remainingIntegralWeight + 0.5)
						boneWeight = max(0, min(255, boneWeight))
						remainingIntegralWeight -= boneWeight
						remainingSelectedWeight -= weight
					
					if boneWeight > 0:
						vertexEncoding.boneMapping.append((bone, boneWeight))
			vertexEncodings.append(vertexEncoding)
		return vertexEncodings
	
	@staticmethod
	def addVertices(encodedVertices, formatEntries, positionBufferEntrySize, dataBufferEntrySize, boneGroupIndices, vertexPositionBuffer, vertexDataBuffer):
		positionBuffer = bytearray(len(encodedVertices) * positionBufferEntrySize)
		dataBuffer = bytearray(len(encodedVertices) * dataBufferEntrySize)
		buffers = [positionBuffer, dataBuffer]
		entrySizes = [positionBufferEntrySize, dataBufferEntrySize]
		
		vertexIndices = {}
		
		for vertexIndex in range(len(encodedVertices)):
			vertexEncoding = encodedVertices[vertexIndex]
			vertexIndices[vertexEncoding.vertex] = vertexIndex
			
			for (bufferID, datumType, datumFormat, offset) in formatEntries:
				if datumType == FmdlFile.FmdlVertexDatumType.position:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.tripleFloat32:
						raise InvalidFmdl("Unexpected format %d for vertex position data" % datumFormat)
					value = vertexEncoding.position
				elif datumType == FmdlFile.FmdlVertexDatumType.boneWeights:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.quadFloat8:
						raise InvalidFmdl("Unexpected format %d for vertex bone weight data" % datumFormat)
					boneWeights = [weight for (bone, weight) in vertexEncoding.boneMapping]
					if len(boneWeights) < 4:
						boneWeights += ((0,) * (4 - len(boneWeights)))
					value = pack('< 4B', *boneWeights)
				elif datumType == FmdlFile.FmdlVertexDatumType.normal:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.quadFloat16:
						raise InvalidFmdl("Unexpected format %d for vertex normal data" % datumFormat)
					value = vertexEncoding.normal
				elif datumType == FmdlFile.FmdlVertexDatumType.color:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.quadFloat8:
						raise InvalidFmdl("Unexpected format %d for vertex color data" % datumFormat)
					value = vertexEncoding.color
				elif datumType == FmdlFile.FmdlVertexDatumType.boneIndices:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.quadInt8:
						raise InvalidFmdl("Unexpected format %d for vertex bone index data" % datumFormat)
					boneIndices = [boneGroupIndices[bone] for (bone, weight) in vertexEncoding.boneMapping]
					if len(boneIndices) < 4:
						boneIndices += ((0,) * (4 - len(boneIndices)))
					value = pack('< 4B', *boneIndices)
				elif datumType == FmdlFile.FmdlVertexDatumType.uv0:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.doubleFloat16:
						raise InvalidFmdl("Unexpected format %d for vertex uv data" % datumFormat)
					value = vertexEncoding.uv[0]
				elif datumType == FmdlFile.FmdlVertexDatumType.uv1:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.doubleFloat16:
						raise InvalidFmdl("Unexpected format %d for vertex uv data" % datumFormat)
					value = vertexEncoding.uv[1]
				elif datumType == FmdlFile.FmdlVertexDatumType.uv2:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.doubleFloat16:
						raise InvalidFmdl("Unexpected format %d for vertex uv data" % datumFormat)
					value = vertexEncoding.uv[2]
				elif datumType == FmdlFile.FmdlVertexDatumType.uv3:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.doubleFloat16:
						raise InvalidFmdl("Unexpected format %d for vertex uv data" % datumFormat)
					value = vertexEncoding.uv[3]
				elif datumType == FmdlFile.FmdlVertexDatumType.tangent:
					if datumFormat != FmdlFile.FmdlVertexDatumFormat.quadFloat16:
						raise InvalidFmdl("Unexpected format %d for vertex tangent data" % datumFormat)
					value = vertexEncoding.tangent
				else:
					raise InvalidFmdl("Unexpected vertex datum type %d" % datumType)
				
				position = entrySizes[bufferID] * vertexIndex + offset
				buffer = buffers[bufferID]
				buffer[position : position + len(value)] = value
		
		if len(positionBuffer) % 16:
			positionBuffer += bytearray(16 - (len(positionBuffer) % 16))
		if len(dataBuffer) % 16:
			dataBuffer += bytearray(16 - (len(dataBuffer) % 16))
		
		vertexPositionBuffer += positionBuffer
		vertexDataBuffer += dataBuffer
		
		return vertexIndices
	
	@staticmethod
	def addFaces(fmdl, faces, faceBuffer, vertexIndices):
		meshFaceBuffer = bytearray(len(faces) * 6)
		
		for i in range(len(faces)):
			pack_into('< 3H', meshFaceBuffer, 6 * i,
				vertexIndices[faces[i].vertices[0]],
				vertexIndices[faces[i].vertices[1]],
				vertexIndices[faces[i].vertices[2]],
			)
		
		firstFaceVertexID = len(faceBuffer) // 2
		faceBuffer += meshFaceBuffer
		return firstFaceVertexID
	
	@staticmethod
	def addExtensionHeaders(fmdl, fmdlFile, extensionHeaders, meshIndices, meshGroupIndices):
		extensionsHeader = 'X-FMDL-Extensions'
		flattenedExtensions = []
		otherHeaders = {}
		headerNames = {}
		def addHeader(key, values):
			if key.lower() in otherHeaders:
				otherHeaders[key.lower()] += values
			else:
				otherHeaders[key.lower()] = values
				headerNames[key.lower()] = key
		for key in extensionHeaders:
			if key.lower() == extensionsHeader.lower():
				flattenedExtensions += extensionHeaders[key]
			else:
				addHeader(key, extensionHeaders[key])
		for i in range(len(fmdlFile.meshes)):
			for key in fmdlFile.meshes[i].extensionHeaders:
				addHeader(key, str(i))
		for i in range(len(fmdlFile.meshGroups)):
			for key in fmdlFile.meshGroups[i].extensionHeaders:
				addHeader(key, str(i))
		
		if len(otherHeaders) == 0 and len(flattenedExtensions) == 0:
			return
		
		extensionString = ''
		extensionString += extensionsHeader + ": " + ', '.join(flattenedExtensions) + "\n"
		for key in otherHeaders:
			extensionString += headerNames[key] + ": " + ', '.join(otherHeaders[key]) + "\n"
		
		encoded = bytes(extensionString, 'utf-8')
		fmdl.segment1Blocks[3] += encoded
		fmdl.segment1Blocks[3] += b'\0'
	
	@staticmethod
	def storeBones(fmdl, stringIndices, bones):
		boneIndices = {}
		#
		# If there are no bones, do not create an empty bone table.
		#
		if len(bones) == 0:
			return boneIndices
		
		boneIndex = FmdlFile.newSegment0BlockDescriptorID(fmdl, 0)
		for bone in bones:
			boneIndices[bone] = boneIndex
			boneIndex += 1
		
		for bone in bones:
			FmdlFile.addBone(fmdl, stringIndices, bone, boneIndices)
		
		return boneIndices
	
	@staticmethod
	def storeMaterialInstances(fmdl, stringIndices, materialInstances):
		materialInstanceIndices = {}
		for materialInstance in materialInstances:
			materialInstanceIndices[materialInstance] = FmdlFile.addMaterialInstance(fmdl, stringIndices, materialInstance)
		return materialInstanceIndices
	
	@staticmethod
	def storeMeshes(fmdl, meshes, boneIndices, materialInstanceIndices):
		levelsOfDetail = 1
		FmdlFile.addLevelsOfDetail(fmdl, levelsOfDetail)
		
		vertexPositionBuffer = bytearray()
		vertexDataBuffer = bytearray()
		faceBuffer = bytearray()
		
		meshIndices = {}
		
		for mesh in meshes:
			meshID = FmdlFile.addMesh(
				fmdl,
				mesh,
				boneIndices,
				materialInstanceIndices[mesh.materialInstance],
				levelsOfDetail,
				vertexPositionBuffer,
				vertexDataBuffer,
				faceBuffer,
			)
			meshIndices[mesh] = meshID
		
		FmdlFile.addBufferOffset(fmdl, False, len(vertexPositionBuffer), 0)
		FmdlFile.addBufferOffset(fmdl, False, len(vertexDataBuffer), len(vertexPositionBuffer))
		FmdlFile.addBufferOffset(fmdl, True, len(faceBuffer), len(vertexPositionBuffer) + len(vertexDataBuffer))
		fmdl.segment1Blocks[2] = vertexPositionBuffer + vertexDataBuffer + faceBuffer
		
		return meshIndices
	
	@staticmethod
	def storeMeshGroups(fmdl, stringIndices, meshGroups, meshIndices):
		meshGroupIndices = {}
		meshGroupIndex = FmdlFile.newSegment0BlockDescriptorID(fmdl, 1)
		for meshGroup in meshGroups:
			meshGroupIndices[meshGroup] = meshGroupIndex
			meshGroupIndex += 1
		
		for meshGroup in meshGroups:
			FmdlFile.addMeshGroup(fmdl, stringIndices, meshGroup, meshGroupIndices, meshIndices)
		
		return meshGroupIndices
	
	def precomputeVertexEncoding(self):
		for mesh in self.meshes:
			if mesh.vertexEncoding == None:
				mesh.vertexEncoding = self.encodeVertices(mesh.vertices, mesh.vertexFields)
	
	def freeVertexEncoding(self):
		for mesh in self.meshes:
			mesh.vertexEncoding = None
	
	def writeFile(self, filename):
		fmdl = FmdlContainer()
		
		stringIndices = {}
		self.addString(fmdl, stringIndices, '')
		boneIndices = self.storeBones(fmdl, stringIndices, self.bones)
		materialInstanceIndices = self.storeMaterialInstances(fmdl, stringIndices, self.materialInstances)
		meshIndices = self.storeMeshes(fmdl, self.meshes, boneIndices, materialInstanceIndices)
		meshGroupIndices = self.storeMeshGroups(fmdl, stringIndices, self.meshGroups, meshIndices)
		self.addExtensionHeaders(fmdl, self, self.extensionHeaders, meshIndices, meshGroupIndices)
		
		# Unknown purpose
		self.addSegment0Block(fmdl, 18, pack('< 8x'))
		self.addSegment0Block(fmdl, 20, pack('< ffff IIIi 96x',
			0.0, 1.0, 1.0, 1.0,
			0, 0, 0, -1,
		))
		
		# The old plugin needs all segment 1 blocks to be there, even if empty.
		# Except for segment 1 block 1, which must be there if and only if there is a bone table.
		for i in [0, 2, 3]:
			if i not in fmdl.segment1Blocks:
				fmdl.segment1Blocks[i] = bytearray()
		if len(self.bones) > 0:
			if 1 not in fmdl.segment1Blocks:
				fmdl.segment1Blocks[1] = bytearray()
		
		fmdl.writeFile(filename)
