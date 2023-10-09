from . import FmdlFile

def encodeFmdlAntiBlur(fmdl):
	output = FmdlFile.FmdlFile()
	output.bones = fmdl.bones.copy()
	output.materialInstances = fmdl.materialInstances.copy()
	output.extensionHeaders = fmdl.extensionHeaders.copy()
	
	antiBlurMaterials = {}
	antiBlurMeshes = {}
	
	def isUvscrollMaterial(material):
		for (parameterName, parameterValues) in material.parameters:
			if parameterName in ["UV0_Speed_U", "UV0_Speed_V"]:
				return True
		return False
	
	def antiBlurMaterial(material, outputFmdl):
		if material in antiBlurMaterials:
			return antiBlurMaterials[material]
		
		output = FmdlFile.FmdlFile.MaterialInstance()
		output.name = material.name + " antiblur"
		if isUvscrollMaterial(material):
			output.technique = "fox3DDF_Blin_Fuzzblock_UVScroll"
			output.shader = "fox3ddf_blin_fuzzblock_uvscroll"
			output.parameters = [("MatParamIndex_0", (0, 0, 0, 0))]
			for (parameterName, parameterValues) in material.parameters:
				if parameterName in ["UV0_Speed_U", "UV0_Speed_V", "Offset"]:
					output.parameters.append((parameterName, parameterValues))
		else:
			output.technique = "fox3DDF_Blin_Fuzzblock"
			output.shader = "fox3ddf_blin_fuzzblock"
			output.parameters = [("MatParamIndex_0", (0, 0, 0, 0))]
		
		output.textures = []
		for (role, texture) in material.textures:
			if role == 'Base_Tex_SRGB':
				output.textures.append(('Base_Tex_SRGB', texture))
				break
		if len(output.textures) == 0:
			for (role, texture) in material.textures:
				if 'base' in role.lower():
					output.textures.append(('Base_Tex_SRGB', texture))
					break
		if len(output.textures) == 0:
			for (role, texture) in material.textures:
				output.textures.append(('Base_Tex_SRGB', texture))
				break
		normalMap = FmdlFile.FmdlFile.Texture()
		normalMap.filename = 'dummy_nrm.ftex'
		normalMap.directory = '/Assets/pes16/model/character/common/sourceimages/'
		output.textures.append(('NormalMap_Tex_NRM', normalMap))
		specularMap = FmdlFile.FmdlFile.Texture()
		specularMap.filename = 'dummy_srm.ftex'
		specularMap.directory = '/Assets/pes16/model/character/common/sourceimages/'
		output.textures.append(('SpecularMap_Tex_LIN', normalMap))
		
		antiBlurMaterials[material] = output
		outputFmdl.materialInstances.append(output)
		
		return output
	
	def makeAntiBlurMesh(mesh, outputFmdl):
		output = FmdlFile.FmdlFile.Mesh()
		output.vertices = mesh.vertices.copy()
		output.faces = mesh.faces.copy()
		output.boneGroup = mesh.boneGroup
		output.alphaFlags = 128 | (mesh.alphaFlags & 32)
		output.shadowFlags = 1
		output.vertexFields = mesh.vertexFields
		
		output.extensionHeaders = mesh.extensionHeaders.copy()
		if 'Has-Antiblur-Meshes' in output.extensionHeaders:
			output.extensionHeaders.remove('Has-Antiblur-Meshes')
		output.extensionHeaders.add('Is-Antiblur-Meshes')
		
		output.materialInstance = antiBlurMaterial(mesh.materialInstance, outputFmdl)
		
		return output
	
	output.meshes = []
	for mesh in fmdl.meshes:
		output.meshes.append(mesh)
		if 'Has-Antiblur-Meshes' in mesh.extensionHeaders:
			antiBlurMesh = makeAntiBlurMesh(mesh, output)
			output.meshes.append(antiBlurMesh)
			antiBlurMeshes[mesh] = antiBlurMesh
	
	output.meshGroups = fmdl.meshGroups.copy()
	for meshGroup in output.meshGroups:
		meshes = meshGroup.meshes
		meshGroup.meshes = []
		for mesh in meshes:
			meshGroup.meshes.append(mesh)
			if mesh in antiBlurMeshes:
				meshGroup.meshes.append(antiBlurMeshes[mesh])
	
	if 'X-FMDL-Extensions' not in output.extensionHeaders:
		output.extensionHeaders['X-FMDL-Extensions'] = []
	output.extensionHeaders['X-FMDL-Extensions'].append("antiblur")
	
	return output

def decodeFmdlAntiBlur(fmdl):
	if fmdl.extensionHeaders == None or "antiblur" not in fmdl.extensionHeaders['x-fmdl-extensions']:
		return fmdl
	
	output = FmdlFile.FmdlFile()
	output.bones = fmdl.bones.copy()
	output.extensionHeaders = fmdl.extensionHeaders.copy()
	
	removedMeshes = set()
	removableMaterials = set()
	
	output.meshes = []
	for mesh in fmdl.meshes:
		if 'is-antiblur-meshes' in mesh.extensionHeaders:
			removedMeshes.add(mesh)
			removableMaterials.add(mesh.materialInstance)
		else:
			output.meshes.append(mesh)
	
	for mesh in output.meshes:
		if mesh.materialInstance in removableMaterials:
			removableMaterials.remove(mesh.materialInstance)
	
	output.meshGroups = fmdl.meshGroups.copy()
	for meshGroup in output.meshGroups:
		meshes = meshGroup.meshes
		meshGroup.meshes = []
		for mesh in meshes:
			if mesh not in removedMeshes:
				meshGroup.meshes.append(mesh)
	
	output.materialInstances = []
	for materialInstance in fmdl.materialInstances:
		if materialInstance not in removableMaterials:
			output.materialInstances.append(materialInstance)
	
	return output
