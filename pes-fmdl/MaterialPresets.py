class Texture:
	def __init__(self, role, directory, filename, required):
		self.role = role
		self.directory = directory
		self.filename = filename
		self.required = required

class Parameter:
	def __init__(self, name, defaultValues, valuesRequired):
		self.name = name
		self.defaultValues = defaultValues
		if type(valuesRequired) == bool:
			self.valuesRequired = [valuesRequired, valuesRequired, valuesRequired, valuesRequired]
		else:
			self.valuesRequired = valuesRequired

class Preset:
	def __init__(self, name, description,
		shader, technique,
		antiBlurDefault, antiBlurRequired,
		alphaFlagsDefault, alphaFlagsBitMask,
		shadowFlagsDefault, shadowFlagsBitMask,
		textures,
		parameters
	):
		self.name = name
		self.description = description
		self.shader = shader
		self.technique = technique
		self.antiBlurDefault = antiBlurDefault
		self.antiBlurRequired = antiBlurRequired
		self.alphaFlagsDefault = alphaFlagsDefault
		self.alphaFlagsBitMask = alphaFlagsBitMask
		self.shadowFlagsDefault = shadowFlagsDefault
		self.shadowFlagsBitMask = shadowFlagsBitMask
		self.textures = textures
		self.parameters = parameters



blinBasic = Preset(
	'blin -- basic', 'Blin shader, preconfigured with the most common settings',
	'fox3ddf_blin', 'fox3DDF_Blin',
	False, True,
	128, 255 & ~32,
	128, 255 & ~1 & ~2,
	[
		Texture('Base_Tex_SRGB', '', '_bsm.dds', False),
		Texture('NormalMap_Tex_NRM', '/Assets/pes16/model/character/common/sourceimages/', 'dummy_nrm.dds', True),
		Texture('SpecularMap_Tex_LIN', '/Assets/pes16/model/character/common/sourceimages/', 'dummy_srm.dds', True),
	],
	[
		Parameter('MatParamIndex_0', [0, 0, 0, 0], True),
	]
)
blin = Preset(
	'blin -- custom', 'Blin shader, custom settings',
	'fox3ddf_blin', 'fox3DDF_Blin',
	False, True,
	128, 255 & ~32 & ~128,
	0, 255 & ~1 & ~2,
	[
		Texture('Base_Tex_SRGB', '', '_bsm.dds', False),
		Texture('NormalMap_Tex_NRM', '/Assets/pes16/model/character/common/sourceimages/', 'dummy_nrm.dds', False),
		Texture('SpecularMap_Tex_LIN', '/Assets/pes16/model/character/common/sourceimages/', 'dummy_srm.dds', False),
	],
	[
		Parameter('MatParamIndex_0', [0, 0, 0, 0], False),
	]
)

constant = Preset(
	'constant', 'Constant shader',
	'fox3dfw_constant_srgb_ndr_solid', 'fox3DFW_ConstantSRGB_NDR_Solid',
	True, True,
	16, 255 & ~32,
	5, 255 & ~1 & ~2,
	[
		Texture('Base_Tex_SRGB', '', '_bsm.dds', False),
	],
	[]
)
constantOriginal = Preset(
	'constant -- original', 'Constant shader, original version',
	'fox3dfw_constant_srgb_ndr', 'fox3DFW_ConstantSRGB_NDR',
	True, True,
	16, 255 & ~32,
	5, 255 & ~1 & ~2,
	[
		Texture('Base_Tex_SRGB', '', '_bsm.dds', False),
	],
	[]
)

metalic = Preset(
	'metalic', 'Metal shader',
	'fox3ddf_ggx', 'fox3DDF_GGX',
	False, True,
	128, 255 & ~32,
	0, 255 & ~1 & ~2,
	[
		Texture('Base_Tex_SRGB', '', '_bsm.dds', False),
		Texture('NormalMap_Tex_NRM', '/Assets/pes16/model/character/common/sourceimages/', 'dummy_nrm.dds', False),
		Texture('SpecularMap_Tex_LIN', '', '_srm.dds', False),
		Texture('MetalnessMap_Tex_LIN', '', '_mtl.dds', False),
	],
	[
		Parameter('MatParamIndex_0', [0, 0, 0, 0], False),
	]
)
glass = Preset(
	'glass', 'Glass shader',
	'pes3dfw_glass2', 'pes3DFW_Glass2',
	False, False,
	16, 255 & ~32,
	5, 255 & ~1 & ~2,
	[
		Texture('Base_Tex_SRGB', '', '_bsm.dds', False),
		Texture('NormalMap_Tex_NRM', '/Assets/pes16/model/character/common/sourceimages/', 'dummy_nrm.dds', False),
		Texture('GlassReflection_Tex_SRGB', '', '_cbm.dds', False),
		Texture('GlassReflectionMask_Tex_LIN', '', '_rfm.dds', False),
	],
	[
		Parameter('MatParamIndex_0', [54, 0, 0, 0], False),
		Parameter('ReflectionIntensity', [1, 0, 0, 0], False),
		Parameter('GlassRoughness', [0, 0, 0, 0], False),
		Parameter('GlassFlatness', [0, 0, 0, 0], False),
		Parameter('PCBoxCenter', [0, 15, 0, 0], False),
		Parameter('PCBoxSize', [250, 80, 250, 0], False),
	]
)

presets = [
	blinBasic,
	blin,
	constant,
	constantOriginal,
	metalic,
	glass,
]
